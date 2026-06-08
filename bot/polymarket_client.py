"""Polymarket client: Gamma market discovery + CLOB market data + maker orders.

Read paths (Gamma + CLOB) are public GETs and implemented here (Phase 2). LIVE
order build/sign/post via py-clob-client is deferred to Phase 5; in DRY_RUN we log
the fully-formed maker request instead of sending it.

DISCOVERY is deterministic: ``market_clock`` computes the active slug
``btc-updown-5m-<ts>``, then Gamma ``GET /events?slug=`` returns the event whose
single market carries ``conditionId`` + ``clobTokenIds`` (a JSON-encoded array)
aligned to ``outcomes`` (``["Up","Down"]``). We map Up/Down by LABEL, not index.

PRICING note (confirmed against the live API): Gamma's ``bestBid``/``bestAsk`` can
be stale — always trust the CLOB ``/book`` / ``/price`` / ``/midpoint`` for live
quotes. The ``/book`` lists are not reliably sorted, so we sort them ourselves
(bids high→low, asks low→high) and expose best-first.
"""

from __future__ import annotations

import json as _json
from typing import List, Optional

from . import market_clock
from .config import Config
from .logging_setup import get_logger
from .models import BookLevel, MarketRef, OrderBook, OrderRequest
from .net import get_json

log = get_logger("polymarket")


class PolymarketClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        # CLOB client + signer are constructed lazily, LIVE only (Phase 5), so
        # DRY_RUN never needs credentials or signing libraries.
        self._clob = None

    # ------------------------------------------------------------------ #
    # Discovery (Gamma, public)                                          #
    # ------------------------------------------------------------------ #
    def get_current_btc_5m_market(self, now: Optional[float] = None) -> Optional[MarketRef]:
        """Resolve the active btc-updown-5m-<ts> market into a MarketRef."""
        window = market_clock.current_window(now)
        return self.get_market_by_slug(window.slug, window.start, window.end)

    def get_market_by_slug(self, slug: str, window_start: int,
                           window_end: int) -> Optional[MarketRef]:
        events = get_json(f"{self.config.gamma_base_url}/events", {"slug": slug})
        if isinstance(events, dict):  # tolerate a paginated wrapper
            events = events.get("data") or events.get("events") or []
        if not events:
            log.info("no Gamma event for slug=%s (not listed yet?)", slug)
            return None

        market = (events[0].get("markets") or [None])[0]
        if not market:
            log.warning("event %s has no markets", slug)
            return None

        outcomes = self._loads_list(market.get("outcomes"))
        token_ids = self._loads_list(market.get("clobTokenIds"))
        if not token_ids or len(token_ids) != len(outcomes):
            log.error("slug=%s outcomes/clobTokenIds mismatch: %s / %s",
                      slug, outcomes, token_ids)
            return None

        up_id = self._token_for(outcomes, token_ids, "up")
        down_id = self._token_for(outcomes, token_ids, "down")
        if up_id is None or down_id is None:
            log.error("slug=%s could not map Up/Down from outcomes=%s", slug, outcomes)
            return None

        ref = MarketRef(
            slug=slug,
            condition_id=str(market.get("conditionId", "")),
            up_token_id=str(up_id),
            down_token_id=str(down_id),
            tick_size=str(market.get("orderPriceMinTickSize", self.config.default_tick_size)),
            window_start=window_start,
            window_end=window_end,
            min_order_size=float(market.get("orderMinSize", self.config.min_shares)),
            neg_risk=bool(market.get("negRisk", False)),
        )
        log.info("market %s cond=%s... tick=%s min=%.0f accepting=%s",
                 slug, ref.condition_id[:10], ref.tick_size, ref.min_order_size,
                 market.get("acceptingOrders"))
        return ref

    @staticmethod
    def _loads_list(value) -> list:
        """Gamma returns clobTokenIds/outcomes as JSON-encoded strings."""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                return _json.loads(value)
            except _json.JSONDecodeError:
                return []
        return list(value)

    @staticmethod
    def _token_for(outcomes, token_ids, label: str) -> Optional[str]:
        for outcome, token in zip(outcomes, token_ids):
            if str(outcome).strip().lower() == label:
                return str(token)
        return None

    # ------------------------------------------------------------------ #
    # Market data (CLOB, public)                                         #
    # ------------------------------------------------------------------ #
    def get_orderbook(self, token_id: str) -> OrderBook:
        raw = get_json(f"{self.config.clob_base_url}/book", {"token_id": token_id})
        bids = self._levels(raw.get("bids"))
        asks = self._levels(raw.get("asks"))
        # Best price first regardless of how the server happened to order them.
        bids.sort(key=lambda lv: lv.price, reverse=True)
        asks.sort(key=lambda lv: lv.price)
        return OrderBook(token_id=str(token_id), bids=bids, asks=asks)

    @staticmethod
    def _levels(rows) -> List[BookLevel]:
        out: List[BookLevel] = []
        for r in rows or []:
            try:
                out.append(BookLevel(price=float(r["price"]), size=float(r["size"])))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def get_price(self, token_id: str, side: str = "buy") -> Optional[float]:
        """CLOB /price for a token + side ("buy" or "sell")."""
        raw = get_json(f"{self.config.clob_base_url}/price",
                       {"token_id": token_id, "side": side})
        return float(raw["price"]) if isinstance(raw, dict) and "price" in raw else None

    def get_midpoint(self, token_id: str) -> Optional[float]:
        raw = get_json(f"{self.config.clob_base_url}/midpoint", {"token_id": token_id})
        return float(raw["mid"]) if isinstance(raw, dict) and "mid" in raw else None

    # ------------------------------------------------------------------ #
    # Trading (DRY_RUN logs here; LIVE posting -> Phase 5)               #
    # ------------------------------------------------------------------ #
    def place_limit_order_maker(self, order: OrderRequest, dry_run: bool) -> Optional[str]:
        """Place a maker-only limit order.

        DRY_RUN: log the fully-formed request and return None (no network).
        LIVE: real CLOB build/sign/post with post_only — implemented in Phase 5.
        """
        if dry_run or not self.config.is_live:
            log.info("[DRY_RUN] MAKER %s %s size=%.0f @ %.3f tok=%s... reason=%s post_only=%s",
                     order.side.value, order.direction.value, order.size, order.price,
                     order.token_id[:8], order.reason_tag, self.config.post_only)
            return None
        raise NotImplementedError("LIVE order posting -> Phase 5")

    def cancel_order(self, order_id: str, dry_run: bool) -> bool:
        if dry_run or not self.config.is_live:
            log.info("[DRY_RUN] CANCEL order_id=%s", order_id)
            return True
        raise NotImplementedError("LIVE cancel -> Phase 5")

    def get_positions(self) -> List[dict]:
        raise NotImplementedError("get_positions -> Phase 5")
