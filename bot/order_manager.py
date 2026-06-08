"""Maker-only order placement: sizing floors, non-crossing price math, and the
3-second fill-or-requote loop.

MAKER GUARANTEE (two independent safeguards):
  1. Non-crossing price: a BUY is placed at ``best_ask - tick`` (or lower), never
     at/above ``best_ask``, so it RESTS on the book instead of crossing. Symmetric
     for SELL (``best_bid + tick``). This alone keeps us a maker.
  2. post_only flag on the live order (Phase 5) — the matching engine rejects
     anything that would still take liquidity.

DRY_RUN fills optimistically at the computed maker price, so a whole window can be
paper-traded end to end. The real 3-second fill-or-requote loop runs in LIVE
(Phase 5): place -> wait 3s -> if unfilled, cancel and re-quote at the nearest new
non-crossing price -> repeat until filled or the window's action buffer closes.

The free functions below are pure (no I/O) and unit-testable in isolation.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Optional

from .config import Config
from .logging_setup import get_logger
from .models import Fill, OrderBook, OrderRequest, Side

log = get_logger("orders")


def floor_shares(notional_usd: float, price: float, min_shares: float,
                 min_notional_usd: float) -> float:
    """Whole-share size satisfying BOTH Polymarket floors (>= min_shares AND
    >= $min_notional). Rounds UP so neither floor is ever violated.

    Note: at typical 5m prices the 5-share floor dominates a ~$1 target (5 shares
    at $0.58 ≈ $2.90), so "exchange minimum" entries are effectively 5 shares.
    """
    if price <= 0:
        return float(min_shares)
    shares = max(notional_usd / price, min_notional_usd / price, float(min_shares))
    return float(math.ceil(shares))


def round_to_tick(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    return round(round(price / tick) * tick, 10)


def maker_limit_price(best_bid: Optional[float], best_ask: Optional[float],
                      tick: float, side: Side,
                      cap: Optional[float] = None) -> Optional[float]:
    """Most competitive NON-CROSSING maker price, tick-aligned.

    BUY  -> one tick below best_ask (becomes/join the best bid); never >= best_ask.
    SELL -> one tick above best_bid; never <= best_bid.
    Falls back to the opposite side, then `cap`, if a side is missing. `cap` bounds
    a BUY from above / a SELL from below (e.g., don't pay past a target). Returns
    None when there's nothing to anchor to.
    """
    if side is Side.BUY:
        anchor = (best_ask - tick) if best_ask is not None else best_bid
        if anchor is None:
            anchor = cap
        if anchor is None:
            return None
        if cap is not None:
            anchor = min(anchor, cap)
        price = round_to_tick(anchor, tick)
        if best_ask is not None and price >= best_ask:  # never cross
            price = round_to_tick(best_ask - tick, tick)
        return max(price, tick)  # strictly > 0

    # SELL
    anchor = (best_bid + tick) if best_bid is not None else best_ask
    if anchor is None:
        anchor = cap
    if anchor is None:
        return None
    if cap is not None:
        anchor = max(anchor, cap)
    price = round_to_tick(anchor, tick)
    if best_bid is not None and price <= best_bid:  # never cross
        price = round_to_tick(best_bid + tick, tick)
    return min(price, round_to_tick(1.0 - tick, tick))  # strictly < 1


class OrderManager:
    def __init__(self, config: Config, client) -> None:
        self.config = config
        self.client = client  # PolymarketClient

    def shares_for_notional(self, notional_usd: float, price: float) -> float:
        return floor_shares(notional_usd, price, self.config.min_shares,
                            self.config.min_notional_usd)

    def maker_price(self, book: OrderBook, side: Side, tick: float,
                    cap: Optional[float] = None) -> Optional[float]:
        bb = book.best_bid.price if book.best_bid else None
        ba = book.best_ask.price if book.best_ask else None
        return maker_limit_price(bb, ba, tick, side, cap)

    def execute(self, order: OrderRequest, book: OrderBook, tick: float,
                dry_run: bool) -> Optional[Fill]:
        """Price the order as a maker against the live book and place it.

        DRY_RUN: log the request + return an optimistic Fill at the maker price.
        LIVE: delegate to the 3s fill-or-requote loop (Phase 5).
        """
        price = self.maker_price(book, order.side, tick)
        if price is None:
            log.warning("no maker price for %s %s (empty book) - skipping",
                        order.side.value, order.direction.value)
            return None
        priced = dataclasses.replace(order, price=price)

        if dry_run or not self.config.is_live:
            self.client.place_limit_order_maker(priced, dry_run=True)  # logs the request
            return Fill(token_id=priced.token_id, direction=priced.direction,
                        side=priced.side, price=price, shares=priced.size,
                        reason_tag=priced.reason_tag, order_id=None)
        return self.place_with_requote(priced, book, tick)

    def place_with_requote(self, order: OrderRequest, book: OrderBook,
                           tick: float) -> Optional[Fill]:
        """LIVE 3-second fill-or-requote loop — implemented in Phase 5.

        Intended behavior:
          1. post maker order (post_only) at maker_price(book)
          2. poll fill status for `unfilled_timeout_sec` (3s)
          3. filled -> return Fill; partial -> account + requote the remainder
          4. unfilled -> cancel, refetch book, recompute maker price, repeat
          5. stop when filled or the window's action buffer closes
        """
        raise NotImplementedError("LIVE fill-or-requote loop -> Phase 5")
