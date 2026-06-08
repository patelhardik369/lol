"""Binance SPOT BTCUSDT 5m kline client (the signal source).

INTERFACE STUB — the HTTP implementation lands in Phase 2; no network calls here
yet. Scope lock: spot BTCUSDT, interval 5m, via ``GET {base}/api/v3/klines``.
"""

from __future__ import annotations

from typing import List, Optional

from .config import Config
from .models import Kline


class BinanceClient:
    """Fetches recent closed 5-minute candles for BTCUSDT spot.

    Phase 2: implement with ``GET /api/v3/klines?symbol=BTCUSDT&interval=5m``
    plus simple retry/backoff, mapping each row to a Kline.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

    def get_recent_klines_5m(self, limit: Optional[int] = None) -> List[Kline]:
        """Return the most recent `limit` closed 5m candles, oldest first."""
        raise NotImplementedError("BinanceClient.get_recent_klines_5m -> Phase 2")
