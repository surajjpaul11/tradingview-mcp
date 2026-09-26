#!/usr/bin/env bash
# Reconcile the local trade database against Alpaca.
#
# Corrects entry prices to actual fills, closes rows whose position is gone at the
# broker, and flags open positions left with no resting stop/target.
# Designed to be run daily by launchd (see scripts/com.suraj.tradingview-sync.plist),
# or by hand: ./scripts/sync_alpaca_trades.sh
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

# launchd starts with a bare PATH — add the usual homes of uv
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

LOG_DIR="$PROJECT_DIR/data"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/alpaca_sync.log"

{
  echo "──────── $(date '+%Y-%m-%d %H:%M:%S %Z') ────────"
  if [ ! -f "$PROJECT_DIR/.env" ]; then
      echo "ERROR: no .env in $PROJECT_DIR — cannot reach Alpaca."
      exit 1
  fi
  uv run python -c "
import os, sys, json
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ[k.strip()] = v.split('#')[0].strip()
sys.path.insert(0, 'src')
from tradingview_mcp.core.services.execution_service import sync_broker_trades
r = sync_broker_trades('alpaca')
if r.get('error'):
    print('ERROR:', r['error']); raise SystemExit(1)
bare = r.get('unprotected_positions') or []
for u in bare:
    print(f\"UNPROTECTED: {u['symbol']} {u.get('quantity')} sh open with no resting stop/target \"
          f\"(recorded stop {u.get('recorded_stop_loss')}, target {u.get('recorded_take_profit')})\")
for m in r.get('entry_price_mismatches') or []:
    print(f\"entry corrected: {m['symbol']} {m['recorded_entry']} -> {m['actual_fill']}\")
for c in r.get('closed_at_broker') or []:
    print(f\"closed at broker: {c['symbol']} exit ~{c['exit_price']} ({c['exit_reason']})\")
for u in r.get('unresolved') or []:
    print('unresolved:', u)
if not (bare or r.get('entry_price_mismatches') or r.get('closed_at_broker') or r.get('unresolved')):
    print(f\"clean — {r.get('open_trades_checked', 0)} open trade(s) checked, nothing to correct\")
"
  echo "exit: $?"
} >> "$LOG" 2>&1
