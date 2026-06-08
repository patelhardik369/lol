#!/usr/bin/env python3
"""scripts/sim_strategy.py - offline, deterministic strategy validation.

Drives the REAL Strategy / OrderManager / PositionManager through a scripted price
path (no network, DRY_RUN optimistic fills) showing the PROFIT-LOCK flow, then runs
targeted checks of lock / favorite / insurance. Run: python scripts/sim_strategy.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import Config  # noqa: E402
from bot.logging_setup import setup_logging  # noqa: E402
from bot.models import BookLevel, Direction, MarketRef, OrderBook, Position  # noqa: E402
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
    return OrderBook(token_id="x", bids=[BookLevel(round(ask - TICK, 2), 1000)],
                     asks=[BookLevel(round(ask, 2), 1000)])


def tags(orders):
    return [(o.reason_tag, o.direction.value, o.size) for o in orders]


def main() -> int:
    cfg = Config.from_env()
    log = setup_logging(cfg.log_level, cfg.logs_dir)
    poly = PolymarketClient(cfg)
    om = OrderManager(cfg, poly)
    pm = PositionManager(cfg)
    strat = Strategy(cfg)

    log.info("=========  PATH SIM: entry -> favorable move -> LOCK & exit  =========")
    for up, secs in [(0.55, 280), (0.66, 240)]:
        down = round(1.0 - up, 2)
        log.info("--- UP=%.2f DOWN=%.2f  %ds left ---", up, down, secs)
        pm.check_lock(SLUG)
        for order in strat.decide(MARKET, pm.get(SLUG), Direction.UP, up, down, secs):
            b = book(up) if order.direction is Direction.UP else book(down)
            fill = om.execute(order, b, TICK, dry_run=True)
            if fill:
                pm.apply_fill(SLUG, fill)
                pm.check_lock(SLUG)
    pos = pm.get(SLUG)
    log.info("RESULT: UP %.0f/$%.2f  DOWN %.0f/$%.2f  cost $%.2f  locked=%s",
             pos.up_shares, pos.up_cost, pos.down_shares, pos.down_cost,
             pos.total_cost, pos.locked)
    log.info("  guaranteed PnL: UP wins %+.2f | DOWN wins %+.2f",
             pm.realized_pnl(pos, Direction.UP), pm.realized_pnl(pos, Direction.DOWN))
    assert pos.locked, "favorable move should lock guaranteed profit"

    log.info("=========  RULE CHECKS  =========")

    # LOCK: one-sided UP, opposite cheap -> buy DOWN to lock guaranteed profit.
    p = Position(slug=SLUG, up_shares=5, up_cost=2.75, entry_direction=Direction.UP)
    o = strat.decide(MARKET, p, Direction.UP, 0.70, 0.30, 120)
    log.info("LOCK check -> %s", tags(o))
    assert o and o[0].reason_tag == "lock" and o[0].direction is Direction.DOWN

    # FAVORITE: equal sides + high cost (no lock) + entry side heavy favorite.
    p = Position(slug=SLUG, up_shares=5, up_cost=4.20, down_shares=5, down_cost=3.80,
                 entry_direction=Direction.UP, hedged=True)
    o = strat.decide(MARKET, p, Direction.UP, 0.84, 0.16, 120)
    log.info("FAVORITE check -> %s", tags(o))
    assert o and o[0].reason_tag == "favorite" and o[0].direction is Direction.UP

    # INSURANCE: entry side dying, fewer than opposite, equalize does NOT lock.
    p = Position(slug=SLUG, up_shares=3, up_cost=1.00, down_shares=8, down_cost=8.00,
                 entry_direction=Direction.UP, hedged=True)
    o = strat.decide(MARKET, p, Direction.UP, 0.08, 0.92, 60)
    log.info("INSURANCE check -> %s", tags(o))
    assert o and o[0].reason_tag == "insurance" and o[0].size == 5

    log.info("=========  ALL CHECKS PASSED  =========")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
