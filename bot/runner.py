"""Orchestration loop.

OUTER loop rolls to the new market on every 300s boundary; INNER loop ticks about
every ``inner_tick_sec`` within a window:
  - at window START: discover the market (Gamma) and compute the signal ONCE.
  - each TICK: read the UP/DOWN books, run the strategy, execute any maker order,
    update the position, and report the trade.
  - at window END: the window is queued for DELAYED resolution. After
    ``resolve_delay_sec`` (~2.5 min) we read the REAL settled outcome from
    Polymarket (`outcomePrices`), falling back to the Binance 5m candle only if
    it isn't settled yet, then record realized + running session P&L.

Console output is the clean trade blotter (via ``bot.report``); full internals are
in logs/bot.log. Resilient: a failing cycle is logged and skipped, never fatal.
"""

from __future__ import annotations

import time
from typing import List, Optional, Set, Tuple

from . import market_clock, report
from .config import Config
from .logging_setup import get_logger
from .market_clock import Window
from .models import Direction, MarketRef, OrderBook

log = get_logger("runner")


class Runner:
    def __init__(self, config: Config, binance, polymarket, signal, strategy,
                 positions, orders, pnl, state=None) -> None:
        self.config = config
        self.binance = binance
        self.polymarket = polymarket
        self.signal = signal
        self.strategy = strategy
        self.positions = positions
        self.orders = orders
        self.pnl = pnl
        self.state = state

        self._stop = False
        self.active_window: Optional[Window] = None
        self.market: Optional[MarketRef] = None
        self.direction: Direction = Direction.NO_TRADE
        self._done: Set[str] = set()
        self._pending: List[Tuple[Window, float]] = []  # (window, resolve_at_epoch)

        if self.state is not None:
            self._restore()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #
    def request_stop(self) -> None:
        self._stop = True

    def run(self, max_seconds: Optional[float] = None) -> None:
        started = time.time()
        log.info("runner start: mode=%s inner_tick=%.1fs resolve_delay=%.0fs%s",
                 self.config.mode, self.config.inner_tick_sec,
                 self.config.resolve_delay_sec,
                 f" max_seconds={max_seconds}" if max_seconds else "")
        while not self._stop:
            try:
                now = time.time()
                window = market_clock.current_window(now)
                if self.active_window is None or window.slug != self.active_window.slug:
                    if self.active_window is not None:
                        self._on_window_end(self.active_window)
                    self._on_window_start(window)
                self._tick(window, now)
                self._process_pending(now)
            except Exception as e:  # never let one bad cycle kill the loop
                log.exception("tick error: %s", e)

            if max_seconds is not None and (time.time() - started) >= max_seconds:
                log.info("max_seconds reached; stopping")
                break
            time.sleep(self.config.inner_tick_sec)

        self.shutdown()

    def shutdown(self) -> None:
        # Best-effort: resolve anything still pending so no P&L is lost on exit.
        for window, _ in list(self._pending):
            self.finalize(window, self._resolve_winner(window))
        self._pending = []
        self._save_state()
        report.session_summary(self.pnl.session_realized, self.pnl.session_count)

    # ------------------------------------------------------------------ #
    # Window transitions                                                 #
    # ------------------------------------------------------------------ #
    def _on_window_start(self, window: Window) -> None:
        self.active_window = window
        self.market = None
        self.direction = Direction.NO_TRADE
        if window.slug in self._done:
            log.debug("window %s already finalized; idling", window.slug)
            return
        self.market = self._discover(window)
        try:
            klines = self.binance.get_recent_klines_5m(closed_only=True)
            self.direction = self.signal.pick_direction(klines)
        except Exception as e:
            log.warning("signal fetch failed: %s", e)
            self.direction = Direction.NO_TRADE
        title = self.market.title if self.market else ""
        report.window_header(title, window.slug, self.direction.value,
                             window.end_dt.strftime("%H:%M:%S UTC"))
        if self.market is None:
            log.warning("  market not found yet for %s (will retry)", window.slug)

    def _on_window_end(self, window: Window) -> None:
        """Queue the finished window for DELAYED resolution (don't resolve now)."""
        slug = window.slug
        if slug in self._done:
            return
        pos = self.positions.get(slug)
        if pos.up_shares == 0 and pos.down_shares == 0:
            self._done.add(slug)
            self._save_state()
            return
        resolve_at = window.end + self.config.resolve_delay_sec
        self._pending.append((window, resolve_at))
        log.debug("window %s closed; resolving in ~%ds", slug,
                  int(self.config.resolve_delay_sec))

    def _process_pending(self, now: float) -> None:
        if not self._pending:
            return
        still: List[Tuple[Window, float]] = []
        for window, resolve_at in self._pending:
            if now >= resolve_at:
                self.finalize(window, self._resolve_winner(window))
            else:
                still.append((window, resolve_at))
        self._pending = still

    def finalize(self, window: Window, winner: Direction) -> None:
        """Record realized PnL for a finished window. Public so the offline sim can
        drive it with an explicit winner (no network)."""
        slug = window.slug
        if slug in self._done:
            return
        pos = self.positions.get(slug)
        if pos.up_shares == 0 and pos.down_shares == 0:
            self._done.add(slug)
            self._save_state()
            return
        if winner not in (Direction.UP, Direction.DOWN):
            log.warning("window %s winner unknown; marking done without P&L", slug)
            self.positions.mark_done(slug, locked=pos.locked)
            self.pnl.record_position(pos)
            self._done.add(slug)
            self._save_state()
            return
        realized = self.positions.realized_pnl(pos, winner)
        self.pnl.record_resolution(pos, winner.value, realized)
        self.positions.mark_done(slug, locked=pos.locked)
        self.pnl.record_position(pos)
        self._done.add(slug)
        self._save_state()
        ret = pos.up_shares if winner is Direction.UP else pos.down_shares
        report.resolution(slug, winner.value, pos.total_cost, ret, realized,
                          self.pnl.session_realized, self.pnl.session_count)

    # ------------------------------------------------------------------ #
    # Per-tick trading                                                   #
    # ------------------------------------------------------------------ #
    def _tick(self, window: Window, now: float) -> None:
        if window.slug in self._done:
            return
        if self.market is None:
            self.market = self._discover(window)
            if self.market is None:
                return
        if self.positions.check_lock(window.slug) or self.positions.get(window.slug).done:
            return
        try:
            up_book = self.polymarket.get_orderbook(self.market.up_token_id)
            down_book = self.polymarket.get_orderbook(self.market.down_token_id)
        except Exception as e:
            log.warning("book fetch failed: %s", e)
            return
        up_price = up_book.best_ask.price if up_book.best_ask else None
        down_price = down_book.best_ask.price if down_book.best_ask else None
        if up_price is None or down_price is None:
            log.debug("incomplete book (up=%s down=%s); skip tick", up_price, down_price)
            return
        self.process_tick(window, up_book, down_book, up_price, down_price,
                          window.seconds_remaining(now))

    def process_tick(self, window: Window, up_book: OrderBook, down_book: OrderBook,
                     up_price: float, down_price: float, seconds_remaining: float) -> None:
        """Run the strategy for one tick and execute any maker order. Reused by the
        live loop and the offline sim."""
        slug = window.slug
        pos = self.positions.get(slug)
        was_locked = pos.locked
        orders = self.strategy.decide(self.market, pos, self.direction, up_price,
                                      down_price, seconds_remaining)
        if not orders:
            log.debug("tick %s: hold (UP=%.3f DOWN=%.3f %.0fs left)",
                      slug, up_price, down_price, seconds_remaining)
            return
        tick = float(self.market.tick_size)
        dry = not self.config.is_live
        for order in orders:
            book = up_book if order.direction is Direction.UP else down_book
            fill = self.orders.execute(order, book, tick, dry_run=dry)
            if fill is None:
                continue
            self.positions.apply_fill(slug, fill)
            self.pnl.record_trade(slug, order, fill.shares, fill.price,
                                  self.config.mode, fill.order_id)
            report.trade(order.reason_tag, fill, self.positions.get(slug))
            self.positions.check_lock(slug)
        pos = self.positions.get(slug)
        if pos.locked and not was_locked:
            report.lock(pos, min(pos.up_shares, pos.down_shares) - pos.total_cost)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _discover(self, window: Window) -> Optional[MarketRef]:
        try:
            return self.polymarket.get_current_btc_5m_market(window.start + 1)
        except Exception as e:
            log.warning("market discovery failed for %s: %s", window.slug, e)
            return None

    def _resolve_winner(self, window: Window) -> Direction:
        """Prefer the REAL Polymarket settlement; fall back to the Binance 5m
        candle (close >= open -> UP) only if Polymarket isn't settled yet."""
        try:
            winner = self.polymarket.get_resolved_outcome(window.slug)
            if winner in (Direction.UP, Direction.DOWN):
                log.debug("resolved %s via Polymarket: %s", window.slug, winner.value)
                return winner
        except Exception as e:
            log.debug("polymarket resolve failed: %s", e)
        try:
            if self.binance is not None:
                klines = self.binance.get_recent_klines_5m(limit=12)
                target_ms = window.start * 1000
                for k in klines:
                    if k.open_time == target_ms:
                        proxy = Direction.UP if k.close >= k.open else Direction.DOWN
                        log.debug("resolved %s via Binance proxy: %s", window.slug, proxy.value)
                        return proxy
        except Exception as e:
            log.warning("winner resolution failed: %s", e)
        log.warning("no resolution available for %s", window.slug)
        return Direction.NO_TRADE

    def _save_state(self) -> None:
        if self.state is None:
            return
        self.state.save({
            "done_slugs": sorted(self._done),
            "positions": self.positions.snapshot(),
        })

    def _restore(self) -> None:
        data = self.state.load()
        self._done = set(data.get("done_slugs", []))
        self.positions.restore(data.get("positions", {}))
        if self._done:
            log.info("restored state: %d finalized windows", len(self._done))
