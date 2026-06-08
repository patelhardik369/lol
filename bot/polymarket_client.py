"""Polymarket client: market discovery (Gamma), order book / prices (CLOB), and
maker-only order placement / cancellation (CLOB via py-clob-client).

INTERFACE STUB — read paths land in Phase 2, live order paths in Phase 5. Nothing
here touches the network or sends orders yet.

Market discovery is DETERMINISTIC: the active market's slug is computed from the
clock by ``market_clock`` and then resolved via Gamma ``GET /events?slug=...``.
No scraping.
"""

from __future__ import annotations

from typing import List, Optional

from .config import Config
from .models import MarketRef, OrderBook, OrderRequest


class PolymarketClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        # The CLOB client + signer are constructed lazily, in LIVE only (Phase 5),
        # so DRY_RUN never needs credentials or signing libraries.
        self._clob = None

    # --- discovery (Phase 2, read-only) ------------------------------------
    def get_current_btc_5m_market(self) -> Optional[MarketRef]:
        """Resolve the active btc-updown-5m-<ts> market into a MarketRef
        (condition id + UP/DOWN token ids + tick size + window bounds)."""
        raise NotImplementedError("get_current_btc_5m_market -> Phase 2")

    # --- market data (Phase 2, read-only) ----------------------------------
    def get_orderbook(self, token_id: str) -> OrderBook:
        raise NotImplementedError("get_orderbook -> Phase 2")

    def get_price(self, token_id: str) -> float:
        raise NotImplementedError("get_price -> Phase 2")

    # --- trading (Phase 5 LIVE; DRY_RUN logs instead of sending) -----------
    def place_limit_order_maker(self, order: OrderRequest, dry_run: bool) -> Optional[str]:
        """Place a maker-only limit order. In DRY_RUN: log and return None. In
        LIVE: post via CLOB with post_only=True and a non-crossing price."""
        raise NotImplementedError("place_limit_order_maker -> Phase 2/5")

    def cancel_order(self, order_id: str, dry_run: bool) -> bool:
        raise NotImplementedError("cancel_order -> Phase 2/5")

    def get_positions(self) -> List[dict]:
        raise NotImplementedError("get_positions -> Phase 5")
