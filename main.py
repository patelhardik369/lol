"""Entrypoint for the Polymarket BTC 5-minute maker bot.

Phase 1 status: SCAFFOLDING ONLY. Running this performs a safe self-check — it
loads config, sets up logging, and prints the deterministic current/next market
slug computed purely from the clock. It does NOT contact Binance or Polymarket and
does NOT place orders. The trading loop (Runner) arrives in Phase 4.

Usage:
    python main.py                 # DRY_RUN self-check (default)
    python main.py --dry-run       # explicit DRY_RUN
    python main.py --live          # selects LIVE mode (inert until Phase 5)
    python main.py --log-level DEBUG
"""

from __future__ import annotations

import argparse
import sys
import time

from bot import __version__, market_clock
from bot.config import DRY_RUN, LIVE, Config
from bot.logging_setup import setup_logging


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Polymarket BTC 5-minute maker bot")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="paper mode (default)")
    mode.add_argument("--live", action="store_true",
                      help="LIVE mode (requires creds; inert until Phase 5)")
    p.add_argument("--log-level", default=None,
                   help="override LOG_LEVEL, e.g. DEBUG")
    return p.parse_args(argv)


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
    log.info("Polymarket BTC 5m maker bot v%s  |  mode=%s", __version__, config.mode)
    log.info("Signal source: Binance SPOT %s %s",
             config.binance_symbol, config.binance_interval)

    # Deterministic market identity straight from the clock — no network involved.
    now = time.time()
    cur = market_clock.current_window(now)
    nxt = market_clock.next_window(now)
    log.info("Active window : %s", cur.slug)
    log.info("  starts %s  ends %s  (%.0fs in, %.0fs left)",
             cur.start_dt.isoformat(), cur.end_dt.isoformat(),
             cur.seconds_into(now), cur.seconds_remaining(now))
    log.info("Next window   : %s (starts %s)", nxt.slug, nxt.start_dt.isoformat())

    for problem in config.validate():
        log.warning("config: %s", problem)

    if config.is_live:
        log.warning("LIVE selected, but live trading is not enabled until Phase 5. "
                    "No orders will be sent.")

    log.info("Phase 1 scaffolding OK. Trading loop (Runner) arrives in Phase 4 - exiting.")
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
