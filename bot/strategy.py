"""Core BTC 5m lifecycle strategy.

Consumes the signal + live odds + current position and emits maker OrderRequests
for the current window. INTERFACE STUB — the entry / hedge / profit-lock /
favorite / insurance logic is implemented in Phase 3.

The "favorite" and "insurance" rules operate on a *favorite-side variable*, not a
hard-coded UP, so the behavior is symmetric whether we first entered UP or DOWN.
"""

from __future__ import annotations

from typing import List

from .config import Config
from .models import Direction, MarketRef, OrderRequest, Position


class Strategy:
    def __init__(self, config: Config) -> None:
        self.config = config

    def decide(
        self,
        market: MarketRef,
        position: Position,
        direction: Direction,
        up_price: float,
        down_price: float,
        seconds_remaining: float,
    ) -> List[OrderRequest]:
        """Return the maker orders to place this tick (possibly empty).

        Phase 3 implements, in priority order:
          1. lifecycle guard — skip if position.done or position.locked
          2. entry near entry_price on the signal side
          3. hedge near hedge_opposite_price if the market moved against us
          4. profit-lock — construct a guaranteed-positive payoff, then mark done
          5. favorite (>= favorite_threshold) — add until shares > total cost basis
          6. insurance (<= insurance_threshold) — equalize fav-side up to other side
        """
        raise NotImplementedError("Strategy.decide -> Phase 3")
