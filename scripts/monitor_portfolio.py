#!/usr/bin/env python3
"""
Alpaca Paper Portfolio Monitor — zero external deps, pure stdlib.

Hits Alpaca's REST API directly via urllib so it works without
`alpaca-trade-api` installed. Reads credentials from .env.

Runs every 15 min during market hours via crontab. Reports full
position/order state on every run; exits early with just a clock
check when the market is closed.

Crontab:
  */15 9-16 * * 1-5 cd /home/claude/workspace && python3 scripts/monitor_portfolio.py >> logs/portfolio.log 2>&1

Manual:
  python3 scripts/monitor_portfolio.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _get(base: str, path: str, key: str, secret: str):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    _load_env(root / ".env")

    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        print("ALPACA_API_KEY / ALPACA_API_SECRET not set in .env", file=sys.stderr)
        return 2

    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    base = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        clock = _get(base, "/v2/clock", key, secret)
    except urllib.error.HTTPError as e:
        print(f"[{now}] Alpaca clock request failed: {e}", file=sys.stderr)
        return 1

    if not clock.get("is_open"):
        print(f"[{now}] Market closed. Next open: {clock.get('next_open')}")
        return 0

    account = _get(base, "/v2/account", key, secret)
    positions = _get(base, "/v2/positions", key, secret)
    orders = _get(base, "/v2/orders?status=open", key, secret)

    equity = float(account["equity"])
    cash = float(account["cash"])
    bp = float(account["buying_power"])

    mode = "PAPER" if paper else "LIVE"
    print(f"\n[{now}] === PORTFOLIO STATUS ({mode}) ===")
    print(f"Equity: ${equity:,.2f}  Cash: ${cash:,.2f}  BP: ${bp:,.2f}")

    if positions:
        print(
            f"\n{'Symbol':<8} {'Qty':>8} {'Entry':>10} {'Mark':>10} "
            f"{'P&L %':>8} {'P&L $':>10} {'Mkt Val':>12} {'Side':>6}"
        )
        print("-" * 82)
        total_pl = 0.0
        total_mv = 0.0
        for p in positions:
            pl_pct = float(p["unrealized_plpc"]) * 100
            pl = float(p["unrealized_pl"])
            mv = float(p["market_value"])
            total_pl += pl
            total_mv += mv
            print(
                f"{p['symbol']:<8} {p['qty']:>8} "
                f"{float(p['avg_entry_price']):>10.2f} "
                f"{float(p['current_price']):>10.2f} "
                f"{pl_pct:>+7.2f}% {pl:>+10.2f} "
                f"{mv:>12.2f} {p['side']:>6}"
            )
        print("-" * 82)
        print(
            f"{'TOTAL':<8} {'':>8} {'':>10} {'':>10} {'':>8} "
            f"{total_pl:>+10.2f} {total_mv:>12.2f}"
        )
    else:
        print("\nNo positions.")

    if orders:
        print(f"\nPending orders: {len(orders)}")
        for o in orders:
            limit = f" @ {o['limit_price']}" if o.get("limit_price") else ""
            print(f"  {o['side'].upper()} {o['qty']} {o['symbol']} {o['type']}{limit} [{o['status']}]")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
