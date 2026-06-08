"""Core BTC 5-minute lifecycle strategy (buy-only construction).

Faithful to the STEP-2 spec (§4-§7) with the user's clarifications. Per tick, the
first matching rule fires (one maker action/tick); the runner executes it, updates
the position, and re-evaluates next tick.

  ENTRY (pure signal)   take the SIGNAL side at window open, any price.
  1. PROFIT-LOCK (§5)   if buying the cheaper outcome makes min(up,down) shares >
                        cost, buy it -> guaranteed-positive payoff, market DONE.
  2. HEDGE / STOP-LOSS (§4)   the entry went against us: the OPPOSITE-of-entry rose
                        to >= hedge_opposite_price (~0.52) -> buy it once to start
                        the backup (config.enable_loss_hedge, default ON).
  3. FAVORITE (§6)      whichever side is the market FAVORITE (>= favorite_threshold,
                        ~0.80) -> top it up until a win on that side profits at
                        least favorite_min_profit_usd (recovers a wrong entry).
  4. INSURANCE (§7)     whichever side is almost dead (<= insurance_threshold,
                        ~0.10) and we hold fewer of it than the other -> buy it to
                        EQUALIZE both sides.

Favorite/insurance act on the *market* side (by price), not a hard-coded UP — so
they fire whether the favorite is our entry side or the opposite (the recovery
case). Hedge uses the entry side to know which way is "adverse".
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .config import Config
from .logging_setup import get_logger
from .models import Direction, MarketRef, OrderRequest, Position, Side
from .order_manager import floor_shares

log = get_logger("strategy")


def lock_buy(pos: Position, up_price: float, down_price: float, min_size: float,
             margin: float) -> Optional[Tuple[Direction, float, float]]:
    """If buying the deficit (fewer-shares) outcome can make
    ``min(up,down) shares > cost + margin``, return (side, shares, price); else
    None. We never buy a side that already has >= the other's shares (buying past
    equalization only raises cost)."""
    best: Optional[Tuple[Direction, float, float, float]] = None
    for side, price, shares, other in (
        (Direction.UP, up_price, pos.up_shares, pos.down_shares),
        (Direction.DOWN, down_price, pos.down_shares, pos.up_shares),
    ):
        if price <= 0 or price >= 1 or other <= shares:
            continue
        need = (pos.total_cost + margin - shares) / (1.0 - price)
        d = max(math.ceil(need + 1e-9), int(math.ceil(min_size)))
        if shares + d > other:
            continue
        new_min = min(shares + d, other)
        new_cost = pos.total_cost + d * price
        if new_min > new_cost + margin:
            profit = new_min - new_cost
            if best is None or profit > best[3]:
                best = (side, float(d), price, profit)
    return None if best is None else (best[0], best[1], best[2])


class Strategy:
    def __init__(self, config: Config) -> None:
        self.config = config

    def decide(self, market: MarketRef, position: Position, signal: Direction,
               up_price: float, down_price: float,
               seconds_remaining: float) -> List[OrderRequest]:
        cfg = self.config

        if position.done or position.locked:
            return []
        if seconds_remaining <= cfg.min_action_buffer_sec:
            return []

        price: Dict[Direction, float] = {Direction.UP: up_price, Direction.DOWN: down_price}
        has_pos = position.up_shares > 0 or position.down_shares > 0

        # ENTRY: pure signal, any price (one entry per window) -----------------
        if not has_pos:
            if signal not in (Direction.UP, Direction.DOWN):
                return []
            if seconds_remaining <= cfg.entry_stop_buffer_sec:
                log.debug("entry skipped: %.0fs left (< %.0fs buffer)",
                          seconds_remaining, cfg.entry_stop_buffer_sec)
                return []
            p = price[signal]
            size = floor_shares(cfg.base_notional_usd, p, market.min_order_size,
                                cfg.min_notional_usd)
            log.debug("ENTRY signal=%s @ %.3f size=%.0f", signal.value, p, size)
            return [self._buy(market, signal, size, p, "entry")]

        entry = position.entry_direction
        if entry is None:
            return []
        opp = entry.opposite
        cost = position.total_cost

        # 1. PROFIT-LOCK (favorable) ------------------------------------------
        lock = lock_buy(position, up_price, down_price, market.min_order_size,
                        cfg.lock_margin_usd)
        if lock is not None:
            side, shares, p = lock
            log.debug("LOCK-BUY %s %.0f @ %.3f (cost $%.2f -> guaranteed profit)",
                      side.value, shares, p, cost)
            return [self._buy(market, side, shares, p, "lock")]

        # 2. HEDGE / STOP-LOSS (adverse): opposite-of-entry rose -> buy it once
        if (cfg.enable_loss_hedge and not position.hedged
                and price[opp] >= cfg.hedge_opposite_price - cfg.price_tolerance):
            size = floor_shares(cfg.base_notional_usd, price[opp],
                                market.min_order_size, cfg.min_notional_usd)
            log.debug("HEDGE: opp %s @ %.3f -> buy %.0f", opp.value, price[opp], size)
            return [self._buy(market, opp, size, price[opp], "hedge")]

        # 3. FAVORITE: market favorite (>= threshold) -> ensure a win there profits
        fav = self._side_at_or_above(price, cfg.favorite_threshold)
        if fav is not None:
            p_fav, fav_sh = price[fav], position.shares(fav)
            if (fav_sh - cost) < cfg.favorite_min_profit_usd:
                need = (cfg.favorite_min_profit_usd + cost - fav_sh) / max(1e-6, 1.0 - p_fav)
                d = max(math.ceil(need + 1e-9), market.min_order_size)
                log.debug("FAVORITE %s @ %.3f: profit-if-win %.2f < %.2f -> buy %.0f",
                          fav.value, p_fav, fav_sh - cost, cfg.favorite_min_profit_usd, d)
                return [self._buy(market, fav, d, p_fav, "favorite")]

        # 4. INSURANCE: dying side (<= threshold), we hold fewer -> equalize ---
        weak = self._side_at_or_below(price, cfg.insurance_threshold)
        if weak is not None:
            weak_sh, other_sh = position.shares(weak), position.shares(weak.opposite)
            if weak_sh < other_sh:
                d = max(other_sh - weak_sh, market.min_order_size)
                log.debug("INSURANCE %s @ %.3f: %.0f < %.0f -> equalize buy %.0f",
                          weak.value, price[weak], weak_sh, other_sh, d)
                return [self._buy(market, weak, d, price[weak], "insurance")]

        return []  # hold

    @staticmethod
    def _side_at_or_above(price: Dict[Direction, float], thr: float) -> Optional[Direction]:
        if price[Direction.UP] >= thr:
            return Direction.UP
        if price[Direction.DOWN] >= thr:
            return Direction.DOWN
        return None

    @staticmethod
    def _side_at_or_below(price: Dict[Direction, float], thr: float) -> Optional[Direction]:
        if price[Direction.UP] <= thr:
            return Direction.UP
        if price[Direction.DOWN] <= thr:
            return Direction.DOWN
        return None

    def _buy(self, market: MarketRef, direction: Direction, size: float,
             ref_price: float, reason: str) -> OrderRequest:
        return OrderRequest(
            token_id=market.token_id(direction), direction=direction, side=Side.BUY,
            price=ref_price, size=size, reason_tag=reason,
        )
