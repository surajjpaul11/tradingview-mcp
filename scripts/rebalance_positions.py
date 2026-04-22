#!/usr/bin/env python3
"""
Rebalance Alpaca paper positions by re-running each ticker's associated strategy.

For every open Alpaca position (and every ticker in the map), we run its
strategy on fresh Yahoo candles through the latest bar, infer whether the
strategy currently wants to be long or flat, and emit an action:

  OPEN  - strategy is long, Alpaca holds 0 shares     -> buy
  HOLD  - strategy is long, Alpaca already holds      -> no-op
  CLOSE - strategy is flat, Alpaca holds              -> liquidate
  SKIP  - strategy is flat, Alpaca holds 0            -> nothing to do

State inference: strategies force-close any open position at the last
candle with `exit_reason == "end_of_data"`. So trades[-1].exit_reason ==
"end_of_data" means the strategy is currently long. Any other exit_reason
on the final trade with exit_date == last candle date means the strategy
just exited today. Older exit_date means it's been flat.

Cron: `0 */4 * * *`  (every 4 hours)
  0 */4 * * * cd /home/claude/workspace && python3 scripts/rebalance_positions.py >> logs/rebalance.log 2>&1

Usage:
  python3 scripts/rebalance_positions.py                 # dry-run report
  python3 scripts/rebalance_positions.py --only PLTR     # one ticker
  # --execute is intentionally not implemented yet; add after reviewing output
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


# --- Alpaca helpers (pattern reused from monitor_portfolio.py) ---

def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _alpaca_get(base: str, path: str, key: str, secret: str):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


# --- Strategy registry ---
# Each entry: (module path relative to workspace root, run-function name, needs_vix)

STRATEGY_REGISTRY = {
    "smart_hold": (
        "strategies.smart_hold.smart_hold_strategy",
        "run_smart_hold",
        True,
    ),
    "hyperbolic_runner": (
        "strategies.hyperbolic_runner.hyperbolic_runner_strategy",
        "run_hyperbolic_runner",
        False,
    ),
    "reversal_channel": (
        "strategies.reversal_channel.reversal_channel_strategy",
        "run_reversal_channel",
        False,
    ),
    "buy_and_protect": (
        "strategies.buy_and_protect.buy_and_protect_strategy",
        "run_buy_and_protect",
        False,
    ),
    "curved_channel": (
        "strategies.curves.curved_channel_strategy",
        "run_curved_channel",
        False,
    ),
    "straight_line": (
        "strategies.straight_line.straight_line_strategy",
        "run_straight_line",
        False,
    ),
    "smart_hold_rc": (
        "strategies.smart_hold_rc.smart_hold_rc_strategy",
        "run_smart_hold_rc",
        True,
    ),
}


def _load_strategy(name: str):
    if name not in STRATEGY_REGISTRY:
        return None
    mod_path, func, needs_vix = STRATEGY_REGISTRY[name]
    sys.path.insert(0, str(ROOT))
    try:
        mod = importlib.import_module(mod_path)
    except Exception as e:
        print(f"  ! failed to import {mod_path}: {e}", file=sys.stderr)
        return None
    return mod, getattr(mod, func), needs_vix


def infer_state(strategy_name: str, symbol: str, period: str = "2y") -> dict:
    """Run the strategy on fresh candles and infer current position state."""
    loaded = _load_strategy(strategy_name)
    if loaded is None:
        return {"state": "UNKNOWN", "error": f"strategy '{strategy_name}' not registered"}
    mod, run_fn, needs_vix = loaded

    try:
        candles = mod.fetch_ohlcv(symbol, period, "1d")
    except Exception as e:
        return {"state": "UNKNOWN", "error": f"fetch_ohlcv failed: {e}"}

    if not candles:
        return {"state": "UNKNOWN", "error": "no candles returned"}

    try:
        if needs_vix:
            try:
                vix = mod.fetch_ohlcv("^VIX", period, "1d")
            except Exception:
                vix = None
            result = run_fn(candles, vix_candles=vix)
        else:
            result = run_fn(candles)
    except Exception as e:
        return {"state": "UNKNOWN", "error": f"strategy run failed: {e}"}

    if isinstance(result, list):
        trades = result
    elif isinstance(result, dict):
        trades = result.get("trade_log") or result.get("trades") or []
    else:
        trades = []
    last_candle_date = candles[-1]["date"]

    if not trades:
        return {
            "state": "FLAT",
            "last_candle_date": last_candle_date,
            "reason": "no trades in history",
        }

    last = trades[-1]
    exit_reason = last.get("exit_reason")
    exit_date = last.get("exit_date")

    if exit_reason == "end_of_data":
        return {
            "state": "LONG",
            "last_candle_date": last_candle_date,
            "entry_date": last.get("entry_date"),
            "entry_price": last.get("entry_price"),
            "pyramid_adds": last.get("pyramid_adds", 0),
        }

    if exit_date == last_candle_date:
        return {
            "state": "JUST_EXITED",
            "last_candle_date": last_candle_date,
            "exit_reason": exit_reason,
        }

    return {
        "state": "FLAT",
        "last_candle_date": last_candle_date,
        "last_exit_date": exit_date,
        "last_exit_reason": exit_reason,
    }


def decide(strategy_state: str, alpaca_qty: float) -> str:
    holding = alpaca_qty > 0
    if strategy_state == "LONG":
        return "HOLD" if holding else "OPEN"
    if strategy_state in ("FLAT", "JUST_EXITED"):
        return "CLOSE" if holding else "SKIP"
    return "UNKNOWN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Restrict to a single ticker (e.g. PLTR)")
    ap.add_argument("--period", default="2y", help="Yahoo period for fresh data (default 2y)")
    args = ap.parse_args()

    _load_env(ROOT / ".env")

    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        print("ALPACA_API_KEY / ALPACA_API_SECRET not set in .env", file=sys.stderr)
        return 2

    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    base = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
    mode = "PAPER" if paper else "LIVE"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[{now}] === REBALANCE CHECK ({mode}) ===")

    # Load ticker -> strategy map
    map_path = ROOT / "scripts" / "ticker_strategy_map.json"
    if not map_path.exists():
        print(f"ticker map missing: {map_path}", file=sys.stderr)
        return 2
    ticker_map = json.loads(map_path.read_text())["map"]

    try:
        positions = _alpaca_get(base, "/v2/positions", key, secret)
    except urllib.error.HTTPError as e:
        print(f"Alpaca positions request failed: {e}", file=sys.stderr)
        return 1

    alpaca_qty = {p["symbol"]: float(p["qty"]) for p in positions}

    # Universe: union of held symbols and mapped symbols, filtered by --only
    universe = sorted(set(alpaca_qty) | set(ticker_map))
    if args.only:
        universe = [s for s in universe if s == args.only]
        if not universe:
            print(f"ticker {args.only} not in positions or map")
            return 1

    print(
        f"\n{'Symbol':<8} {'Strategy':<20} {'Qty':>8} {'StrategyState':<14} "
        f"{'Action':<8} {'Note':<40}"
    )
    print("-" * 106)

    for symbol in universe:
        strategy = ticker_map.get(symbol)
        qty = alpaca_qty.get(symbol, 0.0)

        if not strategy:
            # Held but unmapped — flag, don't act
            print(
                f"{symbol:<8} {'(unmapped)':<20} {qty:>8.2f} {'-':<14} "
                f"{'SKIP':<8} {'no strategy in ticker_strategy_map.json':<40}"
            )
            continue

        info = infer_state(strategy, symbol, args.period)
        state = info.get("state", "UNKNOWN")
        action = decide(state, qty)

        note_parts = []
        if "error" in info:
            note_parts.append(info["error"])
        elif state == "LONG" and info.get("pyramid_adds"):
            note_parts.append(f"pyramid_adds={info['pyramid_adds']}")
        elif state == "JUST_EXITED":
            note_parts.append(f"exit={info.get('exit_reason')}")
        elif state == "FLAT" and info.get("last_exit_date"):
            note_parts.append(f"last_exit={info['last_exit_date']}")
        note = " ".join(note_parts)[:40]

        print(
            f"{symbol:<8} {strategy:<20} {qty:>8.2f} {state:<14} "
            f"{action:<8} {note:<40}"
        )

    print()
    print("Dry-run only; no orders submitted. Add execution logic after review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
