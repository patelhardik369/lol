#!/usr/bin/env python3
"""scripts/probe_market.py - research utility (NOT part of the live bot).

Read-only probe of the live Polymarket Gamma + CLOB APIs to confirm the exact
JSON field names this bot depends on for BTC 5-minute market discovery. It sends
NO credentials and places NO orders - just public GETs. Uses only the Python
standard library (urllib) so it runs without installing anything.

Usage:
    python scripts/probe_market.py            # probe the current 5m window
    python scripts/probe_market.py 1780971000 # probe a specific window start ts
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Allow `import bot...` when run as `python scripts/probe_market.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot import market_clock  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def get(url, params=None, timeout=15):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "polybot-probe/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _unwrap(events):
    """Gamma usually returns a bare list; tolerate a paginated dict too."""
    if isinstance(events, dict):
        return events.get("data") or events.get("events") or []
    return events or []


def probe_slug(slug):
    print(f"# probing slug: {slug}")
    events = _unwrap(get(f"{GAMMA}/events", {"slug": slug}))
    print(f"# events returned: {len(events)}")
    return events


def main():
    if len(sys.argv) > 1:
        start = market_clock.floor_to_window(int(sys.argv[1]))
        slug = market_clock.slug_for_start(start)
    else:
        slug = market_clock.current_slug()

    try:
        events = probe_slug(slug)
        if not events:
            nxt = market_clock.next_window().slug
            print(f"No event for {slug}; trying next window {nxt} ...")
            events = probe_slug(nxt)
    except urllib.error.URLError as e:
        print("Gamma request failed:", e)
        return 1

    if not events:
        print("No event found for current or next window slug.")
        return 0

    ev = events[0]
    print("## event top-level keys:", sorted(ev.keys()))
    for k in ("id", "slug", "title", "active", "closed", "startDate", "endDate"):
        print(f"   event.{k} =", ev.get(k))

    markets = ev.get("markets") or []
    print(f"## markets in event: {len(markets)}")
    if not markets:
        return 0
    m = markets[0]
    print("### market keys:", sorted(m.keys()))
    for k in ("id", "question", "conditionId", "clobTokenIds", "outcomes",
              "outcomePrices", "bestBid", "bestAsk", "orderMinSize",
              "orderPriceMinTickSize", "active", "closed", "acceptingOrders"):
        print(f"   market.{k} =", m.get(k))

    # clobTokenIds / outcomes commonly come back as JSON-encoded strings.
    raw_tokens = m.get("clobTokenIds")
    raw_outs = m.get("outcomes")
    tokens = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
    outs = json.loads(raw_outs) if isinstance(raw_outs, str) else raw_outs
    print("### parsed outcomes:", outs)
    print("### parsed token ids:", tokens)

    if tokens:
        tid = tokens[0]
        label = outs[0] if outs else "?"
        print(f"\n# CLOB reads for outcome[0]={label} token={tid}")
        try:
            book = get(f"{CLOB}/book", {"token_id": tid})
            print("## book keys:", sorted(book.keys()))
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            print(f"   bids: {len(bids)} sample={bids[:2]}")
            print(f"   asks: {len(asks)} sample={asks[:2]}")
            print("## /price?side=buy  =>", get(f"{CLOB}/price", {"token_id": tid, "side": "buy"}))
            print("## /price?side=sell =>", get(f"{CLOB}/price", {"token_id": tid, "side": "sell"}))
            print("## /midpoint        =>", get(f"{CLOB}/midpoint", {"token_id": tid}))
        except urllib.error.URLError as e:
            print("CLOB request failed:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
