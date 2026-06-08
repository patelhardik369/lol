"""Core BTC 5-minute lifecycle strategy (buy-only construction).

Per the STEP-2 spec + clarifications (2026-06-08):

  ENTRY (pure signal)   take the SIGNAL side at window open, ANY price. One entry
                        per window.
  PROFIT-LOCK (primary, §5)   the moment buying the *cheaper* outcome makes
                        min(up,down) shares > cost, buy exactly that and let it
                        lock -> a guaranteed-positive payoff either way, market
                        marked DONE. This is the profit engine.
  FAVORITE (§6, fallback)   only when a lock is NOT achievable and the entry side
                        is a heavy favorite (>= favorite_threshold) with shares
                        <= cost: top it up until shares > cost.
  INSURANCE (§7)        entry side almost dead (<= insurance_threshold) and we
                        hold fewer of it than the opposite -> buy it to EQUALIZE.
  SMART HEDGE           we do NOT add a guaranteed-loss leg. The opposite side is
                        bought only when it LOCKS profit (the profit-lock). The
                        literal ~0.52 adverse hedge is OFF by default
                        (config.enable_loss_hedge) because it raises cost and
                        blocks the lock.

Everything keys off a favorite-side variable (the entry side), so the logic is
symmetric whether we first bet UP or DOWN. One maker action per tick; the runner
executes it, updates the position, and re-evaluates next tick.
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
    None. Buying past equalization only raises cost, so we never buy a side that
    already has >= the other side's shares.
    """
    best: Optional[Tuple[Direction, float, float, float]] = None
    for side, price, shares, other in (
        (Direction.UP, up_price, pos.up_shares, pos.down_shares),
        (Direction.DOWN, down_price, pos.down_shares, pos.up_shares),
    ):
        if price <= 0 or price >= 1 or other <= shares:
            continue
        # smallest whole Δ with (shares+Δ) > cost + Δ*price, capped at equalize.
        need = (pos.total_cost + margin - shares) / (1.0 - price)
        d = max(math.ceil(need + 1e-9), int(math.ceil(min_size)))
        if shares + d > other:           # can't lock within the equalize range
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
        p_entry, p_opp = price[entry], price[opp]
        entry_sh, opp_sh = position.shares(entry), position.shares(opp)
        cost = position.total_cost

        # PROFIT-LOCK (primary) -----------------------------------------------
        lock = lock_buy(position, up_price, down_price, market.min_order_size,
                        cfg.lock_margin_usd)
        if lock is not None:
            side, shares, p = lock
            log.debug("LOCK-BUY %s %.0f @ %.3f (cost $%.2f -> guaranteed profit)",
                      side.value, shares, p, cost)
            return [self._buy(market, side, shares, p, "lock")]

        # FAVORITE (fallback: lock not achievable, entry side heavy favorite) --
        if p_entry >= cfg.favorite_threshold and entry_sh <= cost + cfg.favorite_margin_usd:
            denom = max(1e-6, 1.0 - p_entry)
            need = (cost + cfg.favorite_margin_usd - entry_sh) / denom
            d = max(math.ceil(need + 1e-9), market.min_order_size)
            log.debug("FAVORITE %s @ %.3f: shares %.0f <= cost $%.2f -> buy %.0f",
                      entry.value, p_entry, entry_sh, cost, d)
            return [self._buy(market, entry, d, p_entry, "favorite")]

        # INSURANCE (entry side almost dead, hold less than opposite) ----------
        if p_entry <= cfg.insurance_threshold and entry_sh < opp_sh:
            d = max(opp_sh - entry_sh, market.min_order_size)
            log.debug("INSURANCE %s @ %.3f: %.0f < opp %.0f -> equalize buy %.0f",
                      entry.value, p_entry, entry_sh, opp_sh, d)
            return [self._buy(market, entry, d, p_entry, "insurance")]

        # OPTIONAL literal-spec adverse loss-hedge (OFF by default) -----------
        if (cfg.enable_loss_hedge and not position.hedged
                and p_opp >= cfg.hedge_opposite_price - cfg.price_tolerance):
            size = floor_shares(cfg.base_notional_usd, p_opp, market.min_order_size,
                                cfg.min_notional_usd)
            log.debug("HEDGE: opp %s @ %.3f -> buy %.0f", opp.value, p_opp, size)
            return [self._buy(market, opp, size, p_opp, "hedge")]

        return []  # hold

    def _buy(self, market: MarketRef, direction: Direction, size: float,
             ref_price: float, reason: str) -> OrderRequest:
        return OrderRequest(
            token_id=market.token_id(direction), direction=direction, side=Side.BUY,
            price=ref_price, size=size, reason_tag=reason,
        )
