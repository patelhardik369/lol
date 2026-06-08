"""Binance SPOT BTCUSDT 5m kline client — the directional signal source.

Endpoint (confirmed via docs): ``GET {base}/api/v3/klines?symbol&interval&limit``.
Response is an array of arrays; index layout:
``[openTime, open, high, low, close, volume, closeTime, ...]``.

Note: Binance returns the still-forming candle as the LAST element. Callers that
need only completed candles should use ``closed_only=True``.
"""

from __future__ import annotations

import time
from typing import List, Optional

from .config import Config
from .logging_setup import get_logger
from .models import Kline
from .net import get_json

log = get_logger("binance")


class BinanceClient:
    def __init__(self, config: Config) -> None:
        self.config = config

    def get_recent_klines_5m(self, limit: Optional[int] = None,
                             closed_only: bool = False) -> List[Kline]:
        """Return recent 5m candles, oldest first.

        If ``closed_only`` is True, drop a trailing in-progress candle (one whose
        close time is still in the future).
        """
        limit = int(limit or self.config.binance_klines_limit)
        url = f"{self.config.binance_base_url}/api/v3/klines"
        rows = get_json(url, {
            "symbol": self.config.binance_symbol,
            "interval": self.config.binance_interval,
            "limit": limit,
        })
        klines = [self._parse(r) for r in rows]

        if closed_only and klines:
            now_ms = int(time.time() * 1000)
            if klines[-1].close_time > now_ms:
                klines = klines[:-1]

        if klines:
            log.debug("fetched %d %s %s klines; last close=%.2f",
                      len(klines), self.config.binance_symbol,
                      self.config.binance_interval, klines[-1].close)
        return klines

    @staticmethod
    def _parse(row: list) -> Kline:
        return Kline(
            open_time=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            close_time=int(row[6]),
        )
