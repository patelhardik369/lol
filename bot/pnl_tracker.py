"""PnL accounting + CSV persistence.

Writes data/trades.csv, data/positions.csv, data/pnl.csv. Every trade (real or
DRY_RUN) is appended with its reason_tag so the session is fully auditable.

INTERFACE STUB — implemented in Phase 4.
"""

from __future__ import annotations

from typing import Optional

from .config import Config
from .models import OrderRequest, Position


class PnlTracker:
    def __init__(self, config: Config) -> None:
        self.config = config

    def record_trade(self, slug: str, order: OrderRequest, shares: float,
                     price: float, mode: str, order_id: Optional[str]) -> None:
        """Append one row to data/trades.csv."""
        raise NotImplementedError("record_trade -> Phase 4")

    def record_resolution(self, position: Position, resolved_outcome: str) -> float:
        """Compute & persist realized PnL for a resolved market; return it."""
        raise NotImplementedError("record_resolution -> Phase 4")
