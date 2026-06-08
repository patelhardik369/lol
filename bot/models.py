"""Shared, logic-free data structures used across the bot.

Pure containers and enums only — no network, no strategy, no side effects. Having
these in one place keeps the client/strategy/manager interfaces honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class Direction(str, Enum):
    """Which side of the BTC 5m market. NO_TRADE means the signal abstains."""

    UP = "UP"
    DOWN = "DOWN"
    NO_TRADE = "NO_TRADE"

    @property
    def opposite(self) -> "Direction":
        if self is Direction.UP:
            return Direction.DOWN
        if self is Direction.DOWN:
            return Direction.UP
        return Direction.NO_TRADE


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Kline:
    """One Binance 5m candle (spot BTCUSDT)."""

    open_time: int  # ms since epoch
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int  # ms since epoch


@dataclass(frozen=True)
class MarketRef:
    """Resolved identity of the active BTC 5m market.

    up_token_id / down_token_id are the two CLOB outcome token IDs for the single
    binary market (price_up + price_down ~= 1).
    """

    slug: str
    condition_id: str
    up_token_id: str
    down_token_id: str
    tick_size: str
    window_start: int
    window_end: int

    def token_id(self, direction: Direction) -> str:
        if direction is Direction.UP:
            return self.up_token_id
        if direction is Direction.DOWN:
            return self.down_token_id
        raise ValueError("NO_TRADE has no token id")


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBook:
    token_id: str
    bids: List[BookLevel]  # best (highest price) first
    asks: List[BookLevel]  # best (lowest price) first

    @property
    def best_bid(self) -> Optional[BookLevel]:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[BookLevel]:
        return self.asks[0] if self.asks else None


@dataclass
class OrderRequest:
    """A maker order the strategy wants placed.

    reason_tag explains *why* (entry / hedge / profit_lock / favorite /
    insurance) and is carried into the trade audit trail.
    """

    token_id: str
    direction: Direction
    side: Side
    price: float
    size: float
    reason_tag: str


@dataclass
class Position:
    """Per-market holdings, owned by PositionManager."""

    slug: str
    up_shares: float = 0.0
    down_shares: float = 0.0
    up_cost: float = 0.0    # USD spent acquiring UP
    down_cost: float = 0.0  # USD spent acquiring DOWN
    locked: bool = False        # profit locked -> market considered done
    max_loss_hit: bool = False  # reserved; per-market cap disabled by default
    done: bool = False          # no further entries this window

    @property
    def total_cost(self) -> float:
        return self.up_cost + self.down_cost

    def shares(self, direction: Direction) -> float:
        return self.up_shares if direction is Direction.UP else self.down_shares

    def cost(self, direction: Direction) -> float:
        return self.up_cost if direction is Direction.UP else self.down_cost

    def avg_price(self, direction: Direction) -> Optional[float]:
        sh = self.shares(direction)
        return (self.cost(direction) / sh) if sh > 0 else None
