"""Clean, human-readable console reporting — the trade "blotter".

These lines are logged at INFO so they appear on the tidy console (and in the
detailed file log). All verbose component internals are logged at DEBUG, so the
console shows only: a spaced market header, one line per fill (side / direction /
shares / price / totals / total cost), locks, and per-market + session P&L.
"""

from __future__ import annotations

from .logging_setup import get_logger
from .models import Fill, Position

log = get_logger("report")

_BAR = "=" * 68
_TAG = {"entry": "ENTRY", "lock": "LOCK", "hedge": "HEDGE", "favorite": "FAVOR",
        "insurance": "INSUR"}


def window_header(title: str, slug: str, signal: str, ends: str) -> None:
    log.info("")
    log.info("")
    log.info(_BAR)
    log.info("  %s", title or slug)
    log.info("  %s  |  signal=%s  |  ends %s", slug, signal, ends)
    log.info(_BAR)


def trade(reason: str, fill: Fill, pos: Position) -> None:
    tag = _TAG.get(reason, reason.upper()[:5])
    log.info("  %-5s  %s %-4s  %g sh @ $%.3f ($%.2f)   |   UP %g / DOWN %g   cost $%.2f",
             tag, fill.side.value, fill.direction.value, fill.shares, fill.price,
             fill.shares * fill.price, pos.up_shares, pos.down_shares, pos.total_cost)


def lock(pos: Position, guaranteed: float) -> None:
    log.info("  LOCK   profit locked: guaranteed >= $%.2f either way  "
             "(UP %g / DOWN %g, cost $%.2f)", guaranteed, pos.up_shares,
             pos.down_shares, pos.total_cost)


def resolution(slug: str, winner: str, invested: float, ret: float, realized: float,
               session_total: float, n_markets: int) -> None:
    log.info("  RESOLVED %s  winner=%s   invested $%.2f -> return $%.2f   realized %+.2f",
             slug, winner, invested, ret, realized)
    log.info("  ==> SESSION P&L: %+.2f  over %d market(s)", session_total, n_markets)


def session_summary(session_total: float, n_markets: int) -> None:
    log.info("")
    log.info(_BAR)
    log.info("  SESSION COMPLETE   total realized P&L: %+.2f  over %d market(s)",
             session_total, n_markets)
    log.info(_BAR)
