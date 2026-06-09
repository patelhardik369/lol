"""Core BTC 5-minute lifecycle strategy (buy-only construction).

Hedging is governed by the PER-PAIR COST = (total_cost + equalize_cost) / shares,
i.e. what we'd pay for a guaranteed $1 payout if we equalize both sides now. This
is the (0.58, 0.32, 0.52) rule from the spec: enter at ~0.58, then

  - LOCK      when per-pair cost <= lock_sum (0.90)   -> equalize the deficit side
              for a GUARANTEED profit (>= $0.10 / pair), market DONE.
  - STOP-LOSS when per-pair cost >= stoploss_sum (1.10) -> equalize to cap the loss
              at a fixed ~$0.10 / pair (instead of risking the whole entry).
  - HOLD      in between (0.90 < cost < 1.10): adding the opposite would only lock
              a loss, so we wait. (This is why a "hedge" no longer bleeds.)

Then the spec escalations on the MARKET side (by price, not entry side):
  - FAVORITE  (>= favorite_threshold ~0.80): top up the favored side until a win
              there profits >= favorite_min_profit_usd (recovers a wrong entry).
  - INSURANCE (<= insurance_threshold ~0.10): equalize the almost-dead side.

EVERY order is sized through floors so it is never under 5 shares or under $1 (the
Polymarket minimums) — see order_manager.floor_shares / enforce_floors.

One maker action per tick; the runner executes it and re-evaluates next tick.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from .config import Config
from .logging_setup import get_logger
from .models import Direction, MarketRef, OrderRequest, Position, Side
from .order_manager import enforce_floors, floor_shares

log = get_logger("strategy")


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
        min_size = max(market.min_order_size, cfg.min_shares)

        # ENTRY: pure signal, any price (one entry per window) -----------------
        if not has_pos:
            if signal not in (Direction.UP, Direction.DOWN):
                return []
            if seconds_remaining <= cfg.entry_stop_buffer_sec:
                log.debug("entry skipped: %.0fs left", seconds_remaining)
                return []
            p = price[signal]
            size = floor_shares(cfg.base_notional_usd, p, market.min_order_size,
                                cfg.min_notional_usd)
            log.debug("ENTRY signal=%s @ %.3f size=%.0f", signal.value, p, size)
            return [self._buy(market, signal, size, p, "entry")]

        up_sh, down_sh, cost = position.up_shares, position.down_shares, position.total_cost

        # EQUALIZE the deficit side -> LOCK (cheap) or STOP-LOSS (expensive) ----
        if up_sh != down_sh:
            if up_sh > down_sh:
                deficit, d_price, d_have, other = Direction.DOWN, down_price, down_sh, up_sh
            else:
                deficit, d_price, d_have, other = Direction.UP, up_price, up_sh, down_sh
            d = enforce_floors(other - d_have, d_price, min_size, cfg.min_notional_usd)
            new_min = min(other, d_have + d)
            new_cost = cost + d * d_price
            per_pair = (new_cost / new_min) if new_min > 0 else 99.0
            if per_pair <= cfg.lock_sum:
                log.debug("LOCK %s %.0f @ %.3f (per-pair $%.3f)", deficit.value, d, d_price, per_pair)
                return [self._buy(market, deficit, d, d_price, "lock")]
            if cfg.enable_loss_hedge and not position.hedged and per_pair >= cfg.stoploss_sum:
                log.debug("STOPLOSS %s %.0f @ %.3f (per-pair $%.3f)", deficit.value, d, d_price, per_pair)
                return [self._buy(market, deficit, d, d_price, "stoploss")]
            # otherwise per-pair is in (lock_sum, stoploss_sum): HOLD (no losing leg)

        # FAVORITE: market favorite (>= threshold) -> ensure a win there profits
        fav = self._side_at_or_above(price, cfg.favorite_threshold)
        if fav is not None:
            p_fav, fav_sh = price[fav], position.shares(fav)
            if (fav_sh - cost) < cfg.favorite_min_profit_usd:
                need = (cfg.favorite_min_profit_usd + cost - fav_sh) / max(1e-6, 1.0 - p_fav)
                d = enforce_floors(need, p_fav, min_size, cfg.min_notional_usd)
                log.debug("FAVORITE %s %.0f @ %.3f", fav.value, d, p_fav)
                return [self._buy(market, fav, d, p_fav, "favorite")]

        # INSURANCE: dying side (<= threshold), we hold fewer -> equalize -------
        weak = self._side_at_or_below(price, cfg.insurance_threshold)
        if weak is not None:
            weak_sh, other_sh = position.shares(weak), position.shares(weak.opposite)
            if weak_sh < other_sh:
                d = enforce_floors(other_sh - weak_sh, price[weak], min_size, cfg.min_notional_usd)
                log.debug("INSURANCE %s %.0f @ %.3f", weak.value, d, price[weak])
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
