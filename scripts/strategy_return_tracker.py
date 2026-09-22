"""Capture and compare strategy returns on an immutable OHLCV snapshot.

Run from the repository root with PYTHONPATH=src. The capture command is meant
to run before implementation changes. Compare always reads capture's candles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingview_mcp.core.services import backtest_service as bt

SYMBOLS = ("GOOGL", "AAPL", "MELI", "SPY", "NVDA")
PERIOD = "2y"
INTERVAL = "1d"
CAPITAL = 10_000.0
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05


def _safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _sha(candles):
    payload = json.dumps(candles, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _git_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _strategy_code_diff_sha():
    diff = subprocess.check_output(["git", "diff", "--", "src", "strategies"])
    return hashlib.sha256(diff).hexdigest()


def measure(snapshot):
    rows = []
    for symbol, item in snapshot["data"].items():
        candles = item["candles"]
        for strategy, fn in bt._STRATEGY_MAP.items():
            row = {"symbol": symbol, "strategy": strategy}
            try:
                raw = fn(candles)
                trades = bt._apply_costs(raw, COMMISSION_PCT, SLIPPAGE_PCT)
                metrics = bt._calc_metrics(trades, CAPITAL, INTERVAL)
                row.update({
                    "total_return_pct": metrics["total_return_pct"],
                    "final_capital": metrics["final_capital"],
                    "total_trades": metrics["total_trades"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "buy_and_hold_return_pct": bt._buy_and_hold_return(candles),
                })
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(_safe(row))
    return rows


def capture(path):
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite an existing baseline: {path}")
    snapshot = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit": _git_commit(),
        "source": "Yahoo Finance chart API through _fetch_ohlcv",
        "period": PERIOD,
        "interval": INTERVAL,
        "initial_capital": CAPITAL,
        "commission_pct_per_side": COMMISSION_PCT,
        "slippage_pct_per_side": SLIPPAGE_PCT,
        "data": {},
    }
    for symbol in SYMBOLS:
        candles = bt._fetch_ohlcv(symbol, PERIOD, INTERVAL)
        # Yahoo can return today's evolving daily candle during market hours.
        # Wait for the regular 4 p.m. ET close plus a small provider buffer.
        market_now = datetime.now(ZoneInfo("America/New_York"))
        if (INTERVAL == "1d" and candles
                and candles[-1]["date"] == market_now.date().isoformat()
                and (market_now.hour, market_now.minute) < (16, 15)):
            candles = candles[:-1]
        if not candles:
            raise RuntimeError(f"No candles for {symbol}")
        snapshot["data"][symbol] = {
            "sha256": _sha(candles),
            "first_date": candles[0]["date"],
            "last_date": candles[-1]["date"],
            "bar_count": len(candles),
            "candles": candles,
        }
    snapshot["baseline"] = measure(snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, allow_nan=False) + "\n")
    print(f"Saved {len(snapshot['baseline'])} baseline rows to {path}")
    for symbol in SYMBOLS:
        item = snapshot["data"][symbol]
        print(symbol, item["bar_count"], item["first_date"], item["last_date"], item["sha256"])


def compare(path, output):
    snapshot = json.loads(path.read_text())
    if (snapshot["interval"] != INTERVAL or snapshot["initial_capital"] != CAPITAL
            or snapshot["commission_pct_per_side"] != COMMISSION_PCT
            or snapshot["slippage_pct_per_side"] != SLIPPAGE_PCT):
        raise ValueError("Tracker settings differ from the frozen baseline")
    for symbol, item in snapshot["data"].items():
        if _sha(item["candles"]) != item["sha256"]:
            raise ValueError(f"Frozen candles changed for {symbol}")
    after = measure(snapshot)
    before_map = {(r["symbol"], r["strategy"]): r for r in snapshot["baseline"]}
    rows = []
    for current in after:
        old = before_map[(current["symbol"], current["strategy"])]
        row = {
            "symbol": current["symbol"],
            "strategy": current["strategy"],
            "before_return_pct": old.get("total_return_pct"),
            "after_return_pct": current.get("total_return_pct"),
            "before_trades": old.get("total_trades"),
            "after_trades": current.get("total_trades"),
            "buy_and_hold_return_pct": current.get("buy_and_hold_return_pct"),
        }
        if row["before_return_pct"] is not None and row["after_return_pct"] is not None:
            row["change_percentage_points"] = round(row["after_return_pct"] - row["before_return_pct"], 2)
        if "error" in old:
            row["before_error"] = old["error"]
        if "error" in current:
            row["after_error"] = current["error"]
        rows.append(row)
    report = {
        "compared_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": snapshot["commit"],
        "after_commit": _git_commit(),
        "after_strategy_code_diff_sha256": _strategy_code_diff_sha(),
        "snapshot": str(path),
        "same_frozen_candles": True,
        "settings": {
            "interval": INTERVAL,
            "initial_capital": CAPITAL,
            "commission_pct_per_side": COMMISSION_PCT,
            "slippage_pct_per_side": SLIPPAGE_PCT,
        },
        "interpretation": "A positive difference is a higher measured return under the changed engine; it does not establish better predictive performance.",
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Saved {len(rows)} comparison rows to {output}")
    for row in rows:
        if row["symbol"] in ("GOOGL", "AAPL", "MELI"):
            print(row["symbol"], row["strategy"], row["before_return_pct"], row["after_return_pct"], row.get("change_percentage_points"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("capture", "compare"))
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.snapshot)
    else:
        if not args.output:
            parser.error("--output is required for compare")
        compare(args.snapshot, args.output)
