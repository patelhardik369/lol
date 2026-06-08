"""Tracks per-market positions and enforces the one-entry-cycle-per-window
lifecycle so we never re-enter a closed/resolved market.

INTERFACE STUB — implemented in Phase 3, with optional persistence via
state_store so a restart mid-window doesn't double-trade.
"""

from __future__ import annotations

from typing import Dict

from .config import Config
from .models import Direction, Position, Side


class PositionManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._positions: Dict[str, Position] = {}  # slug -> Position

    def get(self, slug: str) -> Position:
        """Return (creating if needed) the Position for a market slug."""
        raise NotImplementedError("PositionManager.get -> Phase 3")

    def apply_fill(self, slug: str, direction: Direction, side: Side,
                   price: float, shares: float) -> Position:
        """Update holdings + cost basis after a (real or simulated) fill."""
        raise NotImplementedError("PositionManager.apply_fill -> Phase 3")

    def mark_done(self, slug: str, locked: bool) -> None:
        """Close the entry lifecycle for a market (profit locked or finished)."""
        raise NotImplementedError("PositionManager.mark_done -> Phase 3")
