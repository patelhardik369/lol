"""PnL accounting + CSV persistence.

Appends to three CSVs under ``data/``:
  - trades.csv    : every (real or DRY_RUN) fill, with its reason_tag
  - positions.csv : a position snapshot after each fill
  - pnl.csv       : realized PnL per resolved market

Every row is timestamped (UTC ISO-8601) so a whole session is reconstructable.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

from .config import Config
from .logging_setup import get_logger
from .models import OrderRequest, Position

log = get_logger("pnl")

TRADES_HEADER = ["timestamp", "slug", "direction", "side", "price", "shares",
                 "notional", "mode", "reason_tag", "order_id"]
POSITIONS_HEADER = ["timestamp", "slug", "up_shares", "down_shares", "up_cost",
                    "down_cost", "total_cost", "locked", "done"]
PNL_HEADER = ["timestamp_resolved", "slug", "resolved_outcome", "up_shares",
              "down_shares", "total_invested", "total_return", "realized_pnl"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PnlTracker:
    def __init__(self, config: Config) -> None:
        self.config = config
        os.makedirs(config.data_dir, exist_ok=True)
        self.trades_path = os.path.join(config.data_dir, "trades.csv")
        self.positions_path = os.path.join(config.data_dir, "positions.csv")
        self.pnl_path = os.path.join(config.data_dir, "pnl.csv")
        self._ensure(self.trades_path, TRADES_HEADER)
        self._ensure(self.positions_path, POSITIONS_HEADER)
        self._ensure(self.pnl_path, PNL_HEADER)
        # Running session P&L = sum of all rows already in pnl.csv, so a resumed
        # run continues the total (a --reset wipes pnl.csv -> starts at 0).
        self.session_realized = 0.0
        self.session_count = 0
        self._load_totals()

    @staticmethod
    def _ensure(path: str, header: list) -> None:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(header)

    @staticmethod
    def _append(path: str, row: list) -> None:
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def _load_totals(self) -> None:
        try:
            with open(self.pnl_path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        self.session_realized += float(row.get("realized_pnl") or 0.0)
                        self.session_count += 1
                    except ValueError:
                        continue
        except FileNotFoundError:
            pass

    def record_trade(self, slug: str, order: OrderRequest, shares: float,
                     price: float, mode: str, order_id=None) -> None:
        notional = shares * price
        self._append(self.trades_path, [
            _now_iso(), slug, order.direction.value, order.side.value,
            f"{price:.4f}", f"{shares:.4f}", f"{notional:.4f}", mode,
            order.reason_tag, order_id or "",
        ])
        log.debug("trade logged: %s %s %.0f@%.3f [%s]", order.side.value,
                  order.direction.value, shares, price, order.reason_tag)

    def record_position(self, pos: Position) -> None:
        self._append(self.positions_path, [
            _now_iso(), pos.slug, f"{pos.up_shares:.4f}", f"{pos.down_shares:.4f}",
            f"{pos.up_cost:.4f}", f"{pos.down_cost:.4f}", f"{pos.total_cost:.4f}",
            int(pos.locked), int(pos.done),
        ])

    def record_resolution(self, pos: Position, resolved_outcome: str,
                          realized_pnl: float) -> None:
        if resolved_outcome == "UP":
            total_return = pos.up_shares
        elif resolved_outcome == "DOWN":
            total_return = pos.down_shares
        else:
            total_return = 0.0
        self._append(self.pnl_path, [
            _now_iso(), pos.slug, resolved_outcome, f"{pos.up_shares:.4f}",
            f"{pos.down_shares:.4f}", f"{pos.total_cost:.4f}",
            f"{total_return:.4f}", f"{realized_pnl:.4f}",
        ])
        self.session_realized += realized_pnl
        self.session_count += 1
        log.debug("PNL %s outcome=%s invested=$%.2f return=$%.2f realized=%+.2f",
                  pos.slug, resolved_outcome, pos.total_cost, total_return, realized_pnl)
