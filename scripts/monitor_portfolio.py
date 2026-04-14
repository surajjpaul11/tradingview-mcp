#!/usr/bin/env python3
"""
Alpaca Paper Portfolio Monitor
Runs every 15 min during market hours via crontab.
Only reports when market is open.

Crontab entry (add with: crontab -e):
  */15 9-16 * * 1-5 cd /home/claude/workspace && python3 scripts/monitor_portfolio.py >> logs/portfolio.log 2>&1

Or run manually:
  python3 scripts/monitor_portfolio.py
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    print("alpaca-trade-api not installed. Run: pip install alpaca-trade-api")
    sys.exit(1)

api = tradeapi.REST(
    os.environ["ALPACA_API_KEY"],
    os.environ["ALPACA_API_SECRET"],
    "https://paper-api.alpaca.markets",
    api_version="v2",
)

clock = api.get_clock()
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

if not clock.is_open:
    print(f"[{now}] Market closed. Next open: {clock.next_open}")
    sys.exit(0)

account = api.get_account()
equity = float(account.equity)
cash = float(account.cash)

print(f"\n[{now}] === PORTFOLIO STATUS ===")
print(f"Equity: ${equity:,.2f}  Cash: ${cash:,.2f}")

positions = api.list_positions()
if positions:
    print(f"\n{'Symbol':8s}  {'Qty':>6s}  {'Entry':>10s}  {'Current':>10s}  {'P&L %':>8s}  {'P&L $':>8s}  {'Mkt Val':>10s}")
    print("-" * 72)
    total_pnl = 0.0
    total_val = 0.0
    for p in positions:
        pnl_pct = float(p.unrealized_plpc) * 100
        pnl_usd = float(p.unrealized_pl)
        mkt_val = float(p.market_value)
        total_pnl += pnl_usd
        total_val += mkt_val
        print(
            f"{p.symbol:8s}  {p.qty:>6s}  ${float(p.avg_entry_price):>8,.2f}  "
            f"${float(p.current_price):>8,.2f}  {pnl_pct:>+7.2f}%  "
            f"${pnl_usd:>+7.2f}  ${mkt_val:>8,.2f}"
        )
    print("-" * 72)
    print(f"{'TOTAL':8s}  {'':>6s}  {'':>10s}  {'':>10s}  {'':>8s}  ${total_pnl:>+7.2f}  ${total_val:>8,.2f}")
else:
    print("No positions.")

orders = api.list_orders(status="open")
if orders:
    print(f"\nPending orders: {len(orders)}")
    for o in orders:
        print(f"  {o.side.upper()} {o.qty} {o.symbol} — {o.status}")

print()
