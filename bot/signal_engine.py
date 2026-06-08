"""Pluggable directional signal.

Given recent Binance 5m candles, decide UP / DOWN / NO_TRADE. This is the ONLY
intentionally swappable, somewhat-generic piece — isolated behind one method.

Default = short-term momentum with a configurable NEUTRAL zone: if the move over
the lookback is smaller than ``signal_min_pct`` we abstain (NO_TRADE) rather than
forcing a coin-flip side. After each call the human-readable basis is stored on
``last_basis`` so the runner can show *why* a side was picked.
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

    last_basis: str

    def pick_direction(self, candles: List[Kline]) -> Direction: ...


class MomentumSignal:
    """Compare the latest CLOSED 5m close to the close ``signal_lookback`` candles
    earlier. Up-move beyond ``signal_min_pct`` -> UP, down-move -> DOWN, otherwise
    NO_TRADE (flat). ``signal_min_pct`` is a fraction (0.001 = 0.1%)."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.last_basis = ""

    def pick_direction(self, candles: List[Kline]) -> Direction:
        lb = max(1, self.config.signal_lookback)
        if len(candles) < lb + 1:
            self.last_basis = f"only {len(candles)} candles (<{lb + 1})"
            return Direction.NO_TRADE

        recent = candles[-1].close
        past = candles[-1 - lb].close
        if past <= 0:
            self.last_basis = "bad candle data"
            return Direction.NO_TRADE

        change = (recent - past) / past
        self.last_basis = f"{change * 100:+.3f}% over {lb * 5}m"
        threshold = self.config.signal_min_pct
        if change > threshold:
            direction = Direction.UP
        elif change < -threshold:
            direction = Direction.DOWN
        else:
            self.last_basis += " (flat->NO_TRADE)"
            direction = Direction.NO_TRADE

        log.debug("signal: past=%.2f recent=%.2f -> %s [%s]",
                  past, recent, direction.value, self.last_basis)
        return direction


def build_signal(config: Config) -> SignalEngine:
    """Factory mapping config.signal_name -> a SignalEngine implementation."""
    name = (config.signal_name or "momentum").lower()
    if name != "momentum":
        log.warning("unknown signal_name=%r; using momentum", config.signal_name)
    return MomentumSignal(config)
