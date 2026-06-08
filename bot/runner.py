"""Orchestration loop.

OUTER loop rolls to the new market on every 300s boundary; INNER loop ticks about
every ``inner_tick_sec`` within a window:
  - at window START: discover the market (Gamma) and compute the signal ONCE
    (the 5m direction for the whole window).
  - each TICK: read the UP/DOWN order books, run the strategy, execute any maker
    order, update the position + CSVs, and check for a guaranteed-profit lock.
  - at window END: resolve the outcome (Binance 5m candle as a Chainlink proxy)
    and record realized PnL.

Resilient: a failing tick is logged and skipped, not fatal. State (done windows +
positions) is persisted so a restart doesn't double-act on a handled window.
"""

from __future__ import annotations

import time
from typing import Optional, Set

from . import market_clock
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

        if self.state is not None:
            self._restore()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #
    def request_stop(self) -> None:
        self._stop = True

    def run(self, max_seconds: Optional[float] = None) -> None:
        started = time.time()
        log.info("runner start: mode=%s inner_tick=%.1fs%s", self.config.mode,
                 self.config.inner_tick_sec,
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
            except Exception as e:  # never let one bad cycle kill the loop
                log.exception("tick error: %s", e)

            if max_seconds is not None and (time.time() - started) >= max_seconds:
                log.info("max_seconds reached; stopping")
                break
            time.sleep(self.config.inner_tick_sec)

        self.shutdown()

    def shutdown(self) -> None:
        self._save_state()
        log.info("runner stopped. done_windows=%d", len(self._done))

    # ------------------------------------------------------------------ #
    # Window transitions                                                 #
    # ------------------------------------------------------------------ #
    def _on_window_start(self, window: Window) -> None:
        self.active_window = window
        self.market = None
        self.direction = Direction.NO_TRADE
        if window.slug in self._done:
            log.info("window %s already finalized this session; idling", window.slug)
            return
        self.market = self._discover(window)
        try:
            klines = self.binance.get_recent_klines_5m(closed_only=True)
            self.direction = self.signal.pick_direction(klines)
        except Exception as e:
            log.warning("signal fetch failed: %s", e)
            self.direction = Direction.NO_TRADE
        log.info(">>> WINDOW %s | signal=%s | market=%s | ends %s", window.slug,
                 self.direction.value, "found" if self.market else "MISSING",
                 window.end_dt.isoformat())

    def _on_window_end(self, window: Window) -> None:
        winner = self._resolve_winner(window)
        self.finalize(window, winner)

    def finalize(self, window: Window, winner: Direction) -> None:
        """Record realized PnL for a finished window. Public so the offline
        sim can drive it with an explicit winner (no network)."""
        slug = window.slug
        if slug in self._done:
            return
        pos = self.positions.get(slug)
        if pos.up_shares == 0 and pos.down_shares == 0:
            self._done.add(slug)
            self._save_state()
            return
        if winner not in (Direction.UP, Direction.DOWN):
            log.warning("window %s winner unknown; marking done without PnL", slug)
            self.positions.mark_done(slug, locked=pos.locked)
            self._done.add(slug)
            self._save_state()
            return
        realized = self.positions.realized_pnl(pos, winner)
        self.pnl.record_resolution(pos, winner.value, realized)
        self.positions.mark_done(slug, locked=pos.locked)
        self._done.add(slug)
        self._save_state()
        log.info("<<< RESOLVED %s winner=%s realized=%+.2f", slug, winner.value, realized)

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
        """Run the strategy for one tick and execute any resulting maker order.
        Reused by both the live loop and the offline sim."""
        pos = self.positions.get(window.slug)
        orders = self.strategy.decide(self.market, pos, self.direction, up_price,
                                      down_price, seconds_remaining)
        if not orders:
            log.debug("tick %s: hold (UP=%.3f DOWN=%.3f %.0fs left)",
                      window.slug, up_price, down_price, seconds_remaining)
            return
        tick = float(self.market.tick_size)
        dry = not self.config.is_live
        for order in orders:
            book = up_book if order.direction is Direction.UP else down_book
            fill = self.orders.execute(order, book, tick, dry_run=dry)
            if fill is None:
                continue
            self.positions.apply_fill(window.slug, fill)
            self.pnl.record_trade(window.slug, order, fill.shares, fill.price,
                                  self.config.mode, fill.order_id)
            self.positions.check_lock(window.slug)
        self.pnl.record_position(self.positions.get(window.slug))

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
        """Proxy resolution: the Binance 5m candle whose open_time == window start.
        close >= open -> UP, else DOWN. (Polymarket itself resolves on Chainlink.)"""
        try:
            klines = self.binance.get_recent_klines_5m(limit=12)
            target_ms = window.start * 1000
            for k in klines:
                if k.open_time == target_ms:
                    return Direction.UP if k.close >= k.open else Direction.DOWN
            log.warning("no Binance candle for window start %d", window.start)
        except Exception as e:
            log.warning("winner resolution failed: %s", e)
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
