"""Per-market position tracking + the one-entry-cycle-per-window lifecycle.

Holds shares/cost-basis per market slug, applies fills, marks the entry side and
hedge flag, and detects the guaranteed-profit LOCK condition. In-memory; optional
persistence (state_store) is wired in Phase 4 so a restart mid-window is safe.
"""

from __future__ import annotations

from typing import Dict

from .config import Config
from .logging_setup import get_logger
from .models import Direction, Fill, Position, Side

log = get_logger("positions")


class PositionManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._positions: Dict[str, Position] = {}

    def get(self, slug: str) -> Position:
        pos = self._positions.get(slug)
        if pos is None:
            pos = Position(slug=slug)
            self._positions[slug] = pos
        return pos

    def all(self) -> Dict[str, Position]:
        return dict(self._positions)

    def apply_fill(self, slug: str, fill: Fill) -> Position:
        """Update holdings + cost basis after a (real or simulated) fill."""
        pos = self.get(slug)

        if fill.side is Side.BUY:
            if fill.direction is Direction.UP:
                pos.up_shares += fill.shares
                pos.up_cost += fill.shares * fill.price
            else:
                pos.down_shares += fill.shares
                pos.down_cost += fill.shares * fill.price
            if pos.entry_direction is None:
                pos.entry_direction = fill.direction
            elif fill.direction is pos.entry_direction.opposite:
                pos.hedged = True
        else:  # SELL reduces shares + cost at the running average price
            self._apply_sell(pos, fill)

        log.debug("FILL %s %s %.0f @ %.3f [%s] -> UP %.0f/$%.2f  DOWN %.0f/$%.2f  cost $%.2f",
                 fill.side.value, fill.direction.value, fill.shares, fill.price,
                 fill.reason_tag, pos.up_shares, pos.up_cost, pos.down_shares,
                 pos.down_cost, pos.total_cost)
        return pos

    @staticmethod
    def _apply_sell(pos: Position, fill: Fill) -> None:
        if fill.direction is Direction.UP and pos.up_shares > 0:
            avg = pos.up_cost / pos.up_shares
            sold = min(fill.shares, pos.up_shares)
            pos.up_shares -= sold
            pos.up_cost -= avg * sold
        elif fill.direction is Direction.DOWN and pos.down_shares > 0:
            avg = pos.down_cost / pos.down_shares
            sold = min(fill.shares, pos.down_shares)
            pos.down_shares -= sold
            pos.down_cost -= avg * sold

    def check_lock(self, slug: str) -> bool:
        """Mark the market locked + done when ``min(up, down) shares > cost``
        (+ margin): a guaranteed-positive payoff regardless of which side wins.

        Returns True if (now or already) locked.
        """
        pos = self.get(slug)
        if pos.locked:
            return True
        if pos.done:
            return False
        if pos.up_shares > 0 and pos.down_shares > 0:
            guaranteed = min(pos.up_shares, pos.down_shares)
            if guaranteed > pos.total_cost + self.config.lock_margin_usd + 1e-9:
                pos.locked = True
                pos.done = True
                log.debug("LOCKED %s: min(up=%.0f, down=%.0f)=%.0f > cost $%.2f "
                         "-> guaranteed >= $%.2f either way", slug, pos.up_shares,
                         pos.down_shares, guaranteed, pos.total_cost,
                         guaranteed - pos.total_cost)
                return True
        return False

    def mark_done(self, slug: str, locked: bool = False) -> None:
        pos = self.get(slug)
        pos.done = True
        if locked:
            pos.locked = True
        log.debug("market %s marked done (locked=%s)", slug, pos.locked)

    def snapshot(self) -> Dict[str, dict]:
        """Serialize all positions to plain dicts (for state_store)."""
        out: Dict[str, dict] = {}
        for slug, p in self._positions.items():
            out[slug] = {
                "up_shares": p.up_shares, "down_shares": p.down_shares,
                "up_cost": p.up_cost, "down_cost": p.down_cost,
                "entry_direction": p.entry_direction.value if p.entry_direction else None,
                "hedged": p.hedged, "locked": p.locked, "done": p.done,
            }
        return out

    def restore(self, data: Dict[str, dict]) -> None:
        """Rebuild positions from a snapshot() dict (restart safety)."""
        for slug, d in (data or {}).items():
            ed = d.get("entry_direction")
            self._positions[slug] = Position(
                slug=slug,
                up_shares=float(d.get("up_shares", 0.0)),
                down_shares=float(d.get("down_shares", 0.0)),
                up_cost=float(d.get("up_cost", 0.0)),
                down_cost=float(d.get("down_cost", 0.0)),
                entry_direction=Direction(ed) if ed else None,
                hedged=bool(d.get("hedged", False)),
                locked=bool(d.get("locked", False)),
                done=bool(d.get("done", False)),
            )

    @staticmethod
    def realized_pnl(pos: Position, winning: Direction) -> float:
        """PnL if `winning` resolves true: winning shares pay $1 each, minus cost."""
        payout = pos.up_shares if winning is Direction.UP else pos.down_shares
        return payout - pos.total_cost
