"""Pluggable directional signal.

Given recent Binance 5m candles, decide UP / DOWN / NO_TRADE. This is the ONLY
intentionally swappable, somewhat-generic piece — isolated behind one method so it
can be replaced without touching strategy, order, or position logic.

Default = short-term momentum. All thresholds/lookback come from Config.
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from .config import Config
from .logging_setup import get_logger
from .models import Direction, Kline

log = get_logger("signal")


@runtime_checkable
class SignalEngine(Protocol):
    """Anything with this shape can drive direction selection."""

    def pick_direction(self, candles: List[Kline]) -> Direction: ...


class MomentumSignal:
    """Compare the latest close to the close ``signal_lookback`` candles earlier.

    Up-move -> UP, down-move -> DOWN, flat (within ``signal_min_pct``) -> NO_TRADE.
    Expects CLOSED candles (caller passes ``closed_only=True``); the in-progress
    candle would otherwise make the signal flap intra-window.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

    def pick_direction(self, candles: List[Kline]) -> Direction:
        lb = max(1, self.config.signal_lookback)
        if len(candles) < lb + 1:
            log.debug("signal: only %d candles (<%d) -> NO_TRADE", len(candles), lb + 1)
            return Direction.NO_TRADE

        recent = candles[-1].close
        past = candles[-1 - lb].close
        if past <= 0:
            return Direction.NO_TRADE

        change = (recent - past) / past
        if change > self.config.signal_min_pct:
            direction = Direction.UP
        elif change < -self.config.signal_min_pct:
            direction = Direction.DOWN
        else:
            direction = Direction.NO_TRADE

        log.debug("signal: past=%.2f recent=%.2f chg=%+.4f%% -> %s",
                  past, recent, change * 100, direction.value)
        return direction


def build_signal(config: Config) -> SignalEngine:
    """Factory mapping config.signal_name -> a SignalEngine implementation."""
    name = (config.signal_name or "momentum").lower()
    if name != "momentum":
        log.warning("unknown signal_name=%r; using momentum", config.signal_name)
    return MomentumSignal(config)
