#!/usr/bin/env python3
"""scripts/sim_runner.py - offline end-to-end Phase 4 validation.

Drives the REAL Runner.process_tick + finalize over a scripted price path (no
network) and writes real trades/positions/pnl CSVs into data/sim/, then prints
them. Proves the loop + PnL + CSV wiring without depending on live trades.
Run: python scripts/sim_runner.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import Config  # noqa: E402
from bot.logging_setup import setup_logging  # noqa: E402
from bot.market_clock import Window  # noqa: E402
from bot.models import BookLevel, Direction, MarketRef, OrderBook  # noqa: E402
from bot.order_manager import OrderManager  # noqa: E402
from bot.pnl_tracker import PnlTracker  # noqa: E402
from bot.polymarket_client import PolymarketClient  # noqa: E402
from bot.position_manager import PositionManager  # noqa: E402
from bot.runner import Runner  # noqa: E402
from bot.signal_engine import build_signal  # noqa: E402
from bot.strategy import Strategy  # noqa: E402

TICK = 0.01
WINDOW = Window(start=1780000000, end=1780000300, slug="btc-updown-5m-1780000000")
MARKET = MarketRef(slug=WINDOW.slug, condition_id="0xSIM", up_token_id="UP_TOK",
                   down_token_id="DOWN_TOK", tick_size=str(TICK),
                   window_start=WINDOW.start, window_end=WINDOW.end, min_order_size=5.0)


def book(ask: float) -> OrderBook:
    return OrderBook(token_id="x", bids=[BookLevel(round(ask - TICK, 2), 1000)],
                     asks=[BookLevel(round(ask, 2), 1000)])


def main() -> int:
    cfg = Config.from_env()
    cfg.data_dir = os.path.join("data", "sim")  # keep sim output separate from live
    os.makedirs(cfg.data_dir, exist_ok=True)
    for name in ("trades.csv", "positions.csv", "pnl.csv"):  # fresh each run
        try:
            os.remove(os.path.join(cfg.data_dir, name))
        except FileNotFoundError:
            pass

    log = setup_logging(cfg.log_level, cfg.logs_dir)
    poly = PolymarketClient(cfg)
    runner = Runner(cfg, binance=None, polymarket=poly, signal=build_signal(cfg),
                    strategy=Strategy(cfg), positions=PositionManager(cfg),
                    orders=OrderManager(cfg, poly), pnl=PnlTracker(cfg), state=None)
    # Inject the per-window context the live loop sets at window start.
    runner.active_window = WINDOW
    runner.market = MARKET
    runner.direction = Direction.UP

    log.info("=== sim_runner: scripted window %s (resolves UP) ===", WINDOW.slug)
    for up, secs in [(0.58, 280), (0.50, 250), (0.47, 220), (0.84, 150), (0.90, 90)]:
        down = round(1.0 - up, 2)
        runner.process_tick(WINDOW, book(up), book(down), up, down, secs)
    runner.finalize(WINDOW, Direction.UP)  # window closed higher -> UP wins

    log.info("=== CSV output (data/sim) ===")
    for name in ("trades.csv", "positions.csv", "pnl.csv"):
        path = os.path.join(cfg.data_dir, name)
        log.info("---- %s ----", path)
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                log.info("  %s", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
