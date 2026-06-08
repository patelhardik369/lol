"""Pluggable directional signal.

Given recent Binance 5m candles, decide UP / DOWN / NO_TRADE. This is the ONLY
intentionally swappable, somewhat-generic piece — isolated behind one method so it
can be replaced without touching strategy, order, or position logic.

INTERFACE STUB — the default momentum logic lands in Phase 3.
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from .config import Config
from .models import Direction, Kline


@runtime_checkable
class SignalEngine(Protocol):
    """Anything with this shape can drive direction selection."""

    def pick_direction(self, candles: List[Kline]) -> Direction: ...


class MomentumSignal:
    """Default signal (Phase 3): short-term momentum over `signal_lookback`
    candles. All thresholds/lookback come from Config so it stays tunable."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def pick_direction(self, candles: List[Kline]) -> Direction:
        raise NotImplementedError("MomentumSignal.pick_direction -> Phase 3")


def build_signal(config: Config) -> SignalEngine:
    """Factory mapping config.signal_name -> a SignalEngine implementation.

    Phase 3 wires additional engines; for now it returns the momentum stub.
    """
    return MomentumSignal(config)
