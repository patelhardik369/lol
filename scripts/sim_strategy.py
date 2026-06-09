#!/usr/bin/env python3
"""scripts/sim_strategy.py - offline strategy validation (no network).

Validates the per-pair-cost hedging rule (LOCK <= 0.90, STOP-LOSS >= 1.10, HOLD in
between), the $1 / 5-share order floor, and the favorite / insurance escalations.
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
        log.info("--- UP=%.2f DOWN=%.2f  %ds ---", up, down, secs)
        pm.check_lock(SLUG)
        for order in strat.decide(MARKET, pm.get(SLUG), signal, up, down, secs):
            b = book(up) if order.direction is Direction.UP else book(down)
            fill = om.execute(order, b, TICK, dry_run=True)
            if fill:
                pm.apply_fill(SLUG, fill)
                pm.check_lock(SLUG)
    pos = pm.get(SLUG)
    log.info("RESULT: UP %.0f/$%.2f DOWN %.0f/$%.2f cost $%.2f locked=%s | "
             "PnL UP %+.2f / DOWN %+.2f", pos.up_shares, pos.up_cost, pos.down_shares,
             pos.down_cost, pos.total_cost, pos.locked,
             pm.realized_pnl(pos, Direction.UP), pm.realized_pnl(pos, Direction.DOWN))
    return pos


def main() -> int:
    cfg = Config.from_env()
    log = setup_logging(cfg.log_level, cfg.logs_dir)
    strat = Strategy(cfg)

    # Favorable: entry UP, DOWN cheapens so per-pair <= 0.90 -> LOCK & exit.
    fav = run_path(cfg, log, "FAVORABLE: entry UP -> LOCK (per-pair <= 0.90)",
                   Direction.UP, [(0.55, 280), (0.70, 240)])
    assert fav.locked

    # Adverse: entry UP, DOWN reaches per-pair 1.10 -> STOP-LOSS equalize (bounded).
    adv = run_path(cfg, log, "ADVERSE: entry UP -> STOP-LOSS (per-pair >= 1.10)",
                   Direction.UP, [(0.55, 280), (0.44, 240)])
    assert adv.hedged and not adv.locked and adv.up_shares == adv.down_shares

    log.info("=========  RULE CHECKS  =========")

    # HOLD ZONE: per-pair between 0.90 and 1.10 -> no action.
    p = Position(slug=SLUG, up_shares=5, up_cost=2.70, entry_direction=Direction.UP)
    o = strat.decide(MARKET, p, Direction.UP, 0.60, 0.40, 200)  # equalize DOWN -> per-pair ~0.94
    log.info("HOLD ZONE -> %s", tags(o))
    assert o == []

    # $1 FLOOR: a tiny cheap equalize must FILL at >= $1 even at the maker price
    # (ask 0.08 -> maker 0.07), which is where the earlier sub-$1 orders slipped.
    om = OrderManager(cfg, PolymarketClient(cfg))
    p = Position(slug=SLUG, up_shares=5, up_cost=2.70, entry_direction=Direction.UP)
    o = strat.decide(MARKET, p, Direction.UP, 0.92, 0.08, 120)
    fill = om.execute(o[0], book(0.08), TICK, dry_run=True)
    log.info("$1 FLOOR  -> fill %s %.0f @ $%.3f = $%.2f", fill.direction.value,
             fill.shares, fill.price, fill.shares * fill.price)
    assert fill is not None and fill.shares * fill.price >= 1.0

    # FAVORITE: market favorite UP >= 0.80, a UP win doesn't profit enough -> buy UP.
    p = Position(slug=SLUG, up_shares=5, up_cost=2.70, down_shares=5, down_cost=2.75,
                 entry_direction=Direction.UP, hedged=True)
    o = strat.decide(MARKET, p, Direction.UP, 0.84, 0.16, 120)
    log.info("FAVORITE  -> %s", tags(o))
    assert o and o[0].reason_tag == "favorite" and o[0].direction is Direction.UP

    # INSURANCE: DOWN almost dead, we hold fewer, favorite satisfied, no lock.
    p = Position(slug=SLUG, up_shares=15, up_cost=13.0, down_shares=5, down_cost=1.30,
                 entry_direction=Direction.DOWN, hedged=True)
    o = strat.decide(MARKET, p, Direction.DOWN, 0.92, 0.08, 60)
    log.info("INSURANCE -> %s", tags(o))
    assert o and o[0].reason_tag == "insurance" and o[0].direction is Direction.DOWN

    log.info("=========  ALL CHECKS PASSED  =========")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
