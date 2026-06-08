"""Deterministic clock math for Polymarket BTC 5-minute "Up or Down" markets.

Polymarket lists these markets at a slug of the form::

    btc-updown-5m-<unix_ts>

where ``<unix_ts>`` is the UNIX epoch second at which the 5-minute window
*starts*, always divisible by 300 (5 minutes). Because the boundary is anchored
to the UNIX epoch (00:00:00 UTC, 1970-01-01) and 300 divides one hour, every
window start lands on a UTC time whose minute is a multiple of 5 and whose second
is 0 — exactly aligned with Binance 5m klines.

This module is PURE: only arithmetic on timestamps. No network, no orders, no
strategy. It answers "which market are we on right now?" offline and is trivially
unit-testable by injecting `now`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

WINDOW_SECONDS = 300  # 5 minutes — the only interval this bot ever trades.
SLUG_PREFIX = "btc-updown-5m-"


@dataclass(frozen=True)
class Window:
    """A single 5-minute BTC up/down market window."""

    start: int  # unix epoch second of window open (divisible by 300)
    end: int    # unix epoch second of window close (start + 300)
    slug: str   # Polymarket event slug, e.g. "btc-updown-5m-1780971000"

    @property
    def start_dt(self) -> datetime:
        return datetime.fromtimestamp(self.start, tz=timezone.utc)

    @property
    def end_dt(self) -> datetime:
        return datetime.fromtimestamp(self.end, tz=timezone.utc)

    def contains(self, ts: float) -> bool:
        return self.start <= ts < self.end

    def seconds_into(self, now: float) -> float:
        return max(0.0, now - self.start)

    def seconds_remaining(self, now: float) -> float:
        return max(0.0, self.end - now)


def floor_to_window(ts: float) -> int:
    """Largest 300-second boundary <= ts."""
    t = int(ts)
    return t - (t % WINDOW_SECONDS)


def slug_for_start(start: int) -> str:
    return f"{SLUG_PREFIX}{int(start)}"


def window_for_start(start: int) -> Window:
    start = int(start)
    return Window(start=start, end=start + WINDOW_SECONDS, slug=slug_for_start(start))


def current_window(now: float | None = None) -> Window:
    """The window the given (or current) instant falls in."""
    now = time.time() if now is None else now
    return window_for_start(floor_to_window(now))


def next_window(now: float | None = None) -> Window:
    """The window immediately after the current one."""
    now = time.time() if now is None else now
    return window_for_start(floor_to_window(now) + WINDOW_SECONDS)


def current_slug(now: float | None = None) -> str:
    return current_window(now).slug


def parse_start_from_slug(slug: str) -> int:
    """Inverse of slug_for_start. Raises ValueError on a non-matching slug."""
    if not slug.startswith(SLUG_PREFIX):
        raise ValueError(f"not a btc 5m slug: {slug!r}")
    return int(slug[len(SLUG_PREFIX):])
