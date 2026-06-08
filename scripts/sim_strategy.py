#!/usr/bin/env python3
"""scripts/sim_strategy.py - offline strategy validation (no network).

Drives the REAL Strategy / OrderManager / PositionManager through scripted price
paths showing BOTH a favorable lock and an adverse recovery (entry -> hedge ->
favorite), then runs targeted lock / hedge / favorite / insurance checks.
Run: python scripts/sim_strategy.py
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


def run_path(cfg, log, label, signal, path):
    poly = PolymarketClient(cfg)
    om = OrderManager(cfg, poly)
    pm = PositionManager(cfg)
    strat = Strategy(cfg)
    log.info("=====  %s  =====", label)
    for up, secs in path:
        down = round(1.0 - up, 2)
        log.info("--- UP=%.2f DOWN=%.2f  %ds left ---", up, down, secs)
        pm.check_lock(SLUG)
        for order in strat.decide(MARKET, pm.get(SLUG), signal, up, down, secs):
            b = book(up) if order.direction is Direction.UP else book(down)
            fill = om.execute(order, b, TICK, dry_run=True)
            if fill:
                pm.apply_fill(SLUG, fill)
                pm.check_lock(SLUG)
    pos = pm.get(SLUG)
    log.info("RESULT: UP %.0f/$%.2f DOWN %.0f/$%.2f cost $%.2f locked=%s | "
             "PnL UP %+.2f / DOWN %+.2f", pos.up_shares, pos.up_cost,
             pos.down_shares, pos.down_cost, pos.total_cost, pos.locked,
             pm.realized_pnl(pos, Direction.UP), pm.realized_pnl(pos, Direction.DOWN))
    return pos


def main() -> int:
    cfg = Config.from_env()
    log = setup_logging(cfg.log_level, cfg.logs_dir)
    strat = Strategy(cfg)

    # Favorable: enter UP, UP rises -> buy cheap DOWN to LOCK guaranteed profit.
    fav = run_path(cfg, log, "FAVORABLE: entry UP -> LOCK", Direction.UP,
                   [(0.55, 280), (0.66, 240)])
    assert fav.locked

    # Adverse: enter DOWN, market goes UP -> HEDGE UP -> FAVORITE UP (the backup).
    adv = run_path(cfg, log, "ADVERSE: entry DOWN -> HEDGE -> FAVORITE", Direction.DOWN,
                   [(0.56, 280), (0.62, 250), (0.82, 200)])
    assert adv.up_shares >= 10 and adv.down_shares == 5  # 5 hedge + 5 favorite on UP

    log.info("=========  RULE CHECKS  =========")

    # LOCK: one-sided UP, opposite cheap -> buy DOWN.
    p = Position(slug=SLUG, up_shares=5, up_cost=2.75, entry_direction=Direction.UP)
    o = strat.decide(MARKET, p, Direction.UP, 0.70, 0.30, 120)
    log.info("LOCK      -> %s", tags(o))
    assert o and o[0].reason_tag == "lock" and o[0].direction is Direction.DOWN

    # HEDGE: entered DOWN, opposite UP rose past 0.52, no lock yet -> buy UP.
    p = Position(slug=SLUG, down_shares=5, down_cost=2.20, entry_direction=Direction.DOWN)
    o = strat.decide(MARKET, p, Direction.DOWN, 0.60, 0.40, 200)
    log.info("HEDGE     -> %s", tags(o))
    assert o and o[0].reason_tag == "hedge" and o[0].direction is Direction.UP

    # FAVORITE: market favorite UP >= 0.80, a UP win doesn't profit enough -> buy UP.
    p = Position(slug=SLUG, up_shares=5, up_cost=3.00, down_shares=5, down_cost=2.20,
                 entry_direction=Direction.DOWN, hedged=True)
    o = strat.decide(MARKET, p, Direction.DOWN, 0.84, 0.16, 120)
    log.info("FAVORITE  -> %s", tags(o))
    assert o and o[0].reason_tag == "favorite" and o[0].direction is Direction.UP

    # INSURANCE: DOWN almost dead, we hold fewer, and equalizing does NOT lock.
    p = Position(slug=SLUG, up_shares=15, up_cost=13.0, down_shares=5, down_cost=1.30,
                 entry_direction=Direction.DOWN, hedged=True)
    o = strat.decide(MARKET, p, Direction.DOWN, 0.92, 0.08, 60)
    log.info("INSURANCE -> %s", tags(o))
    assert o and o[0].reason_tag == "insurance" and o[0].direction is Direction.DOWN

    log.info("=========  ALL CHECKS PASSED  =========")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
