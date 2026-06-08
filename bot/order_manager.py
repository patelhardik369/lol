"""Maker-only order placement with the 3-second fill-or-requote loop.

MAKER GUARANTEE — two independent safeguards (both implemented in Phase 3):
  1. Non-crossing price math: a BUY is priced at or below the best bid (never at or
     above the best ask), so it RESTS on the book instead of crossing the spread;
     symmetric for SELL. This alone keeps us a maker even if a venue flag were
     ignored.
  2. post_only flag: orders are posted with post_only=True so the matching engine
     REJECTS (rather than executes) anything that would take liquidity.

FILL-OR-REQUOTE (per the locked Q4 decision): place -> wait up to
``unfilled_timeout_sec`` (3s) -> if not filled, cancel and re-quote at the nearest
current non-crossing price ("nearest new odd"); repeat until filled or the
window's entry buffer closes.

INTERFACE STUB — implemented in Phase 3. No orders are sent here yet.
"""

from __future__ import annotations

from typing import Optional

from .config import Config
from .models import OrderBook, OrderRequest, Side


class OrderManager:
    def __init__(self, config: Config, client) -> None:
        self.config = config
        self.client = client  # PolymarketClient

    def shares_for_notional(self, notional_usd: float, price: float) -> float:
        """Convert a target USD notional at `price` into a share count that
        respects BOTH Polymarket floors (>= 5 shares AND >= $1 notional)."""
        raise NotImplementedError("shares_for_notional -> Phase 3")

    def maker_price(self, book: OrderBook, side: Side) -> float:
        """Compute a non-crossing limit price from the book (see module docs)."""
        raise NotImplementedError("maker_price -> Phase 3")

    def place_maker(self, order: OrderRequest, dry_run: bool) -> Optional[str]:
        """Place one maker order whose price is already validated non-crossing."""
        raise NotImplementedError("place_maker -> Phase 3")

    def place_with_requote(self, order: OrderRequest, dry_run: bool) -> Optional[str]:
        """Full 3s fill-or-requote loop around place_maker / cancel."""
        raise NotImplementedError("place_with_requote -> Phase 3")
