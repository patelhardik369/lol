"""Entrypoint for the Polymarket BTC 5-minute maker bot.

Loads config, wires the components, and runs the 5-minute trading loop. Defaults
to DRY_RUN (paper, no orders). LIVE order posting is enabled in Phase 5; selecting
--live before then is refused with a clear message rather than half-trading.

Usage:
    python main.py                      # DRY_RUN loop (Ctrl-C to stop)
    python main.py --dry-run            # explicit DRY_RUN
    python main.py --max-seconds 30     # bounded DRY_RUN run (handy for testing)
    python main.py --live               # refused until Phase 5
    python main.py --log-level DEBUG
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

from bot import __version__, market_clock
from bot.binance_client import BinanceClient
from bot.config import DRY_RUN, LIVE, Config
from bot.logging_setup import setup_logging
from bot.order_manager import OrderManager
from bot.pnl_tracker import PnlTracker
from bot.polymarket_client import PolymarketClient
from bot.position_manager import PositionManager
from bot.runner import Runner
from bot.signal_engine import build_signal
from bot.state_store import StateStore
from bot.strategy import Strategy


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Polymarket BTC 5-minute maker bot")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="paper mode (default)")
    mode.add_argument("--live", action="store_true",
                      help="LIVE mode (requires creds; enabled in Phase 5)")
    p.add_argument("--log-level", default=None, help="override LOG_LEVEL, e.g. DEBUG")
    p.add_argument("--max-seconds", type=float, default=None,
                   help="stop after N seconds (bounded run for testing)")
    p.add_argument("--reset", action="store_true",
                   help="delete prior run data (trades/positions/pnl CSVs + state.json) before starting")
    return p.parse_args(argv)


def reset_data(config: Config, log) -> None:
    """Delete prior run artifacts so the session starts from a clean slate."""
    removed = 0
    for name in ("trades.csv", "positions.csv", "pnl.csv", "state.json"):
        path = os.path.join(config.data_dir, name)
        try:
            os.remove(path)
            removed += 1
            log.info("reset: removed %s", path)
        except FileNotFoundError:
            pass
    if removed == 0:
        log.info("reset: no prior data files to remove")


def main(argv=None) -> int:
    args = parse_args(argv)

    config = Config.from_env()
    if args.live:
        config.mode = LIVE
    elif args.dry_run:
        config.mode = DRY_RUN
    if args.log_level:
        config.log_level = args.log_level

    log = setup_logging(config.log_level, config.logs_dir)
    log.info("=" * 70)
    log.info("Polymarket BTC 5m maker bot v%s | mode=%s | signal=Binance SPOT %s %s",
             __version__, config.mode, config.binance_symbol, config.binance_interval)

    if args.reset:
        reset_data(config, log)

    for problem in config.validate():
        log.warning("config: %s", problem)

    # LIVE order posting arrives in Phase 5; refuse rather than crash mid-trade.
    if config.is_live:
        log.error("LIVE trading is not enabled until Phase 5. Re-run in DRY_RUN "
                  "(default) — no orders were sent.")
        return 2

    cur = market_clock.current_window()
    log.info("starting at window %s (ends %s)", cur.slug, cur.end_dt.isoformat())

    # Wire components.
    binance = BinanceClient(config)
    polymarket = PolymarketClient(config)
    runner = Runner(
        config=config,
        binance=binance,
        polymarket=polymarket,
        signal=build_signal(config),
        strategy=Strategy(config),
        positions=PositionManager(config),
        orders=OrderManager(config, polymarket),
        pnl=PnlTracker(config),
        state=StateStore(config),
    )

    # Graceful shutdown on Ctrl-C / SIGTERM -> flush state in runner.shutdown().
    def _handle(signum, _frame):
        log.info("signal %s received; stopping after this tick...", signum)
        runner.request_stop()

    signal.signal(signal.SIGINT, _handle)
    try:
        signal.signal(signal.SIGTERM, _handle)
    except (AttributeError, ValueError):  # SIGTERM may be unavailable on Windows
        pass

    runner.run(max_seconds=args.max_seconds)
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
