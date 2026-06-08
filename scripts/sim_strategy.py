#!/usr/bin/env python3
"""scripts/sim_strategy.py - offline, deterministic strategy validation.

Drives the REAL Strategy / OrderManager / PositionManager through a scripted price
path (no network, DRY_RUN optimistic fills), then runs targeted checks of the
favorite, insurance, and lock rules. This is how we prove the Phase 3 lifecycle
behaves before wiring the live loop. Run: python scripts/sim_strategy.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import Config  # noqa: E402
from bot.logging_setup import setup_logging  # noqa: E402
from bot.models import (BookLevel, Direction, MarketRef, OrderBook,  # noqa: E402
                        Position)
from bot.order_manager import OrderManager  # noqa: E402
from bot.polymarket_client import PolymarketClient  # noqa: E402
from bot.position_manager import PositionManager  # noqa: E402
from bot.strategy import Strategy  # noqa: E402

TICK = 0.01
SLUG = "btc-updown-5m-SIM"
MARKET = MarketRef(slug=SLUG, condition_id="0xSIM", up_token_id="UP_TOK",
                   down_token_id="DOWN_TOK", tick_size=str(TICK),
                   window_start=0, window_end=300, min_order_size=5.0)


def book(ask: float) -> OrderBook:
    """Synthetic 1-level book with best_ask=ask, best_bid=ask-tick."""
    return OrderBook(token_id="x",
                     bids=[BookLevel(round(ask - TICK, 2), 1000)],
                     asks=[BookLevel(round(ask, 2), 1000)])


def main() -> int:
    cfg = Config.from_env()
    log = setup_logging(cfg.log_level, cfg.logs_dir)
    poly = PolymarketClient(cfg)
    om = OrderManager(cfg, poly)
    pm = PositionManager(cfg)
    strat = Strategy(cfg)

    log.info("=================  PRICE-PATH SIM (entry -> hedge -> favorite)  =================")
    # (label, up_ask, seconds_remaining); down_ask is derived as 1 - up_ask.
    path = [
        ("open  ", 0.58, 280),
        ("dip   ", 0.50, 250),
        ("adverse", 0.47, 220),
        ("recover", 0.84, 150),
        ("strong ", 0.90, 90),
    ]
    for label, up, secs in path:
        down = round(1.0 - up, 2)
        log.info("--- %s  UP=%.2f DOWN=%.2f  %ds left ---", label, up, down, secs)
        pm.check_lock(SLUG)
        pos = pm.get(SLUG)
        for order in strat.decide(MARKET, pos, Direction.UP, up, down, secs):
            b = book(up) if order.direction is Direction.UP else book(down)
            fill = om.execute(order, b, TICK, dry_run=True)
            if fill:
                pm.apply_fill(SLUG, fill)

    pos = pm.get(SLUG)
    log.info("RESULT: UP %.0f sh / $%.2f   DOWN %.0f sh / $%.2f   cost $%.2f   locked=%s",
             pos.up_shares, pos.up_cost, pos.down_shares, pos.down_cost,
             pos.total_cost, pos.locked)
    log.info("   PnL if UP wins   = %+.2f", pm.realized_pnl(pos, Direction.UP))
    log.info("   PnL if DOWN wins = %+.2f", pm.realized_pnl(pos, Direction.DOWN))

    # --- targeted rule checks -------------------------------------------------
    log.info("=================  RULE CHECKS  =================")

    # FAVORITE: entry UP, hedged, UP @ 0.84, shares(5) <= cost(5.45) -> buy more UP
    fav = Position(slug=SLUG, up_shares=5, up_cost=2.85, down_shares=5,
                   down_cost=2.60, entry_direction=Direction.UP, hedged=True)
    orders = strat.decide(MARKET, fav, Direction.UP, 0.84, 0.16, 120)
    log.info("FAVORITE check -> %s", [(o.reason_tag, o.direction.value, o.size) for o in orders])
    assert orders and orders[0].reason_tag == "favorite" and orders[0].direction is Direction.UP

    # INSURANCE: entry UP @ 0.08, UP shares(3) < DOWN shares(8) -> buy UP to equalize
    ins = Position(slug=SLUG, up_shares=3, up_cost=1.74, down_shares=8,
                   down_cost=4.16, entry_direction=Direction.UP, hedged=True)
    orders = strat.decide(MARKET, ins, Direction.UP, 0.08, 0.92, 60)
    log.info("INSURANCE check -> %s", [(o.reason_tag, o.direction.value, o.size) for o in orders])
    assert orders and orders[0].reason_tag == "insurance" and orders[0].size == 5  # max(8-3, min5)

    # LOCK: both sides cheap enough that min(shares) > cost -> guaranteed profit
    lock = Position(slug="LOCKTEST", up_shares=10, up_cost=4.0, down_shares=10,
                    down_cost=4.5, entry_direction=Direction.UP, hedged=True)
    pm._positions["LOCKTEST"] = lock
    locked = pm.check_lock("LOCKTEST")
    log.info("LOCK check -> locked=%s (min 10 sh > $8.50 cost)", locked)
    assert locked and lock.done

    log.info("=================  ALL CHECKS PASSED  =================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
