"""Minimal stdlib HTTP helper (urllib) with retry/backoff + JSON parsing.

Used by all read paths (Binance klines, Polymarket Gamma/CLOB market data) and by
DRY_RUN. Keeping this dependency-free means everything through Phase 4 runs without
`pip install`; the signing stack (py-clob-client) is only pulled in for LIVE order
posting in Phase 5.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from .logging_setup import get_logger

log = get_logger("net")

DEFAULT_TIMEOUT = 12.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 0.5
_UA = "polybot/0.2 (read-only market data)"


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status
        self.url = url
        self.body = body


def get_json(url: str, params: Optional[dict] = None, *,
             timeout: float = DEFAULT_TIMEOUT,
             retries: int = DEFAULT_RETRIES,
             backoff: float = DEFAULT_BACKOFF,
             headers: Optional[dict] = None) -> Any:
    """GET `url` (+ query params) and parse JSON, retrying transient failures.

    Retries on connection errors, timeouts, 429, and 5xx. Raises HttpError
    immediately on other 4xx (a bug, not a blip).
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    hdrs = {"User-Agent": _UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)

    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            if e.code == 429 or 500 <= e.code < 600:
                last_exc = HttpError(e.code, url, body)
                log.warning("GET %s -> %s (attempt %d/%d), retrying", url, e.code, attempt, retries)
            else:
                raise HttpError(e.code, url, body) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_exc = e
            log.warning("GET %s failed: %s (attempt %d/%d), retrying", url, e, attempt, retries)
        if attempt < retries:
            time.sleep(backoff * attempt)

    assert last_exc is not None
    raise last_exc
