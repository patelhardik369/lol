#!/usr/bin/env python3
"""scripts/smoke_clients.py - exercise the Phase 2 clients (read-only + DRY_RUN).

Fetches Binance 5m klines, discovers the current BTC 5m Polymarket market, reads
its order book / prices, and LOGS one hypothetical maker order through the DRY_RUN
path. No credentials, no real orders. Run: python scripts/smoke_clients.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.binance_client import BinanceClient  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.logging_setup import setup_logging  # noqa: E402
from bot.models import Direction, OrderRequest, Side  # noqa: E402
from bot.polymarket_client import PolymarketClient  # noqa: E402


def main() -> int:
    config = Config.from_env()
    log = setup_logging(config.log_level, config.logs_dir)
    log.info("=== Phase 2 smoke (DRY_RUN, read-only) ===")

    # --- Binance signal source ------------------------------------------------
    binance = BinanceClient(config)
    klines = binance.get_recent_klines_5m(limit=6, closed_only=True)
    log.info("Binance: %d closed klines; last 3 closes=%s", len(klines),
             [round(k.close, 1) for k in klines[-3:]])

    # --- Polymarket discovery + market data ----------------------------------
    poly = PolymarketClient(config)
    market = poly.get_current_btc_5m_market()
    if market is None:
        log.warning("No current BTC 5m market resolved; skipping CLOB reads.")
        return 0

    up_book = poly.get_orderbook(market.up_token_id)
    down_book = poly.get_orderbook(market.down_token_id)
    bb = up_book.best_bid.price if up_book.best_bid else None
    ba = up_book.best_ask.price if up_book.best_ask else None
    log.info("UP book: best_bid=%s best_ask=%s (%d bids / %d asks)",
             bb, ba, len(up_book.bids), len(up_book.asks))
    log.info("UP /price buy=%s sell=%s mid=%s",
             poly.get_price(market.up_token_id, "buy"),
             poly.get_price(market.up_token_id, "sell"),
             poly.get_midpoint(market.up_token_id))
    log.info("DOWN best_bid=%s best_ask=%s",
             down_book.best_bid.price if down_book.best_bid else None,
             down_book.best_ask.price if down_book.best_ask else None)

    # Hypothetical maker BUY on UP, one tick below best ask (non-crossing). This
    # previews Phase 3 maker-price logic; here we only LOG it via the DRY_RUN path.
    if ba is not None:
        tick = float(market.tick_size)
        demo = OrderRequest(
            token_id=market.up_token_id, direction=Direction.UP, side=Side.BUY,
            price=round(ba - tick, 4), size=market.min_order_size,
            reason_tag="smoke_demo",
        )
        poly.place_limit_order_maker(demo, dry_run=True)

    log.info("=== smoke OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
