"""Core BTC 5-minute lifecycle strategy (buy-only construction).

Emits AT MOST ONE maker OrderRequest per tick (the highest-priority action). The
runner executes it, updates the position, and re-evaluates next tick — so the
sequence entry -> hedge -> favorite/insurance -> lock unfolds deterministically
across ticks without intra-tick ordering hazards.

Everything keys off a *favorite-side variable* = the entry side (the side we first
bet, from the signal). That makes the >=0.80 / <=0.10 logic symmetric whether we
entered UP or DOWN — nothing is hard-coded to literal UP.

Priority each tick (first match wins):
  R0  guards     : done/locked, or too close to window end -> no action
  R1  entry      : no position + signal side priced in [entry_min, entry_max]
  R2  favorite   : entry side >= 0.80 and its shares <= cost -> top up entry side
                   until shares > cost (so a win actually profits)
  R3  insurance  : entry side <= 0.10 and entry shares < opposite shares ->
                   buy entry side up to EQUALIZE both sides (full insurance)
  R4  hedge      : opposite side >= 0.52 (we moved against the entry), once ->
                   buy opposite side at base size (caps the adverse outcome)
  else           : hold

Why no separate "sell to take profit" leg: the PRD's concrete thresholds
(0.58/0.52/0.80/0.10) construct the desired payoffs by BUYING only. The guaranteed
both-way LOCK (min(up,down) shares > cost) is detected in PositionManager and stops
further trading when it ever arises; favorite is a directional profit-ensure and
insurance is an equalizing floor, exactly as specified.
"""

from __future__ import annotations

import math
from typing import Dict, List

from .config import Config
from .logging_setup import get_logger
from .models import Direction, MarketRef, OrderRequest, Position, Side
from .order_manager import floor_shares

log = get_logger("strategy")


class Strategy:
    def __init__(self, config: Config) -> None:
        self.config = config

    def decide(self, market: MarketRef, position: Position, signal: Direction,
               up_price: float, down_price: float,
               seconds_remaining: float) -> List[OrderRequest]:
        """Return 0 or 1 maker OrderRequests. `up_price`/`down_price` are the
        current BUY (best-ask) prices for each outcome."""
        cfg = self.config

        # R0 guards -----------------------------------------------------------
        if position.done or position.locked:
            return []
        if seconds_remaining <= cfg.min_action_buffer_sec:
            return []

        price: Dict[Direction, float] = {Direction.UP: up_price, Direction.DOWN: down_price}
        has_pos = position.up_shares > 0 or position.down_shares > 0

        # R1 initial entry ----------------------------------------------------
        if not has_pos:
            if signal not in (Direction.UP, Direction.DOWN):
                return []
            if seconds_remaining <= cfg.entry_stop_buffer_sec:
                log.debug("entry skipped: %.0fs left (< %.0fs entry buffer)",
                          seconds_remaining, cfg.entry_stop_buffer_sec)
                return []
            p_entry = price[signal]
            if cfg.entry_min_price <= p_entry <= cfg.entry_price:
                size = floor_shares(cfg.base_notional_usd, p_entry,
                                    market.min_order_size, cfg.min_notional_usd)
                log.debug("ENTRY: signal=%s priced %.3f in band [%.2f, %.2f] -> buy %.0f",
                         signal.value, p_entry, cfg.entry_min_price, cfg.entry_price, size)
                return [self._buy(market, signal, size, p_entry, "entry")]
            log.debug("no entry: %s %.3f outside band [%.2f, %.2f]",
                      signal.value, p_entry, cfg.entry_min_price, cfg.entry_price)
            return []

        # Have a position: anchor on the entry (favorite) side ----------------
        entry = position.entry_direction
        if entry is None:  # defensive; entry_direction is set on the first fill
            return []
        opp = entry.opposite
        p_entry, p_opp = price[entry], price[opp]
        entry_sh, opp_sh = position.shares(entry), position.shares(opp)
        cost = position.total_cost

        # R2 favorite (entry side >= 0.80): top up until entry_sh > cost -------
        if p_entry >= cfg.favorite_threshold and entry_sh <= cost + cfg.favorite_margin_usd:
            # Solve (entry_sh + d) > (cost + d*p_entry) + margin
            #   ->  d > (cost + margin - entry_sh) / (1 - p_entry)
            denom = max(1e-6, 1.0 - p_entry)
            need = (cost + cfg.favorite_margin_usd - entry_sh) / denom
            d = max(math.ceil(need + 1e-9), market.min_order_size)
            log.debug("FAVORITE %s @ %.3f: shares %.0f <= cost $%.2f -> buy %.0f more",
                     entry.value, p_entry, entry_sh, cost, d)
            return [self._buy(market, entry, d, p_entry, "favorite")]

        # R3 insurance (entry side <= 0.10): equalize entry up to opposite -----
        if p_entry <= cfg.insurance_threshold and entry_sh < opp_sh:
            d = max(opp_sh - entry_sh, market.min_order_size)
            log.debug("INSURANCE %s @ %.3f: %.0f < opposite %.0f -> buy %.0f to equalize",
                     entry.value, p_entry, entry_sh, opp_sh, d)
            return [self._buy(market, entry, d, p_entry, "insurance")]

        # R4 hedge (opposite side >= 0.52, once): cap the adverse outcome ------
        if not position.hedged and p_opp >= cfg.hedge_opposite_price - cfg.price_tolerance:
            size = floor_shares(cfg.base_notional_usd, p_opp, market.min_order_size,
                                cfg.min_notional_usd)
            log.debug("HEDGE: opposite %s rose to %.3f (>= %.2f) -> buy %.0f",
                     opp.value, p_opp, cfg.hedge_opposite_price, size)
            return [self._buy(market, opp, size, p_opp, "hedge")]

        return []  # hold

    def _buy(self, market: MarketRef, direction: Direction, size: float,
             ref_price: float, reason: str) -> OrderRequest:
        """Build a BUY OrderRequest. `ref_price` is the current ask; the
        OrderManager recomputes the actual non-crossing maker price at execution."""
        return OrderRequest(
            token_id=market.token_id(direction), direction=direction, side=Side.BUY,
            price=ref_price, size=size, reason_tag=reason,
        )
