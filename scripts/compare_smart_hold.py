"""Compare Smart Hold variants to their exact pre-change Git sources.

This reconstructs the baseline from the commit recorded in the frozen MCP
snapshot and uses the same ticker/VIX candles for both source versions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import types
from datetime import datetime, timezone
from pathlib import Path

from tradingview_mcp.core.services.backtest_service import _fetch_ohlcv

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "smart_hold": ("strategies/smart_hold/smart_hold_strategy.py", "run_smart_hold"),
    "smart_hold_rc": ("strategies/smart_hold_rc/smart_hold_rc_strategy.py", "run_smart_hold_rc"),
}


def _source(commit: str, relative: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT, text=True
    )


def _load(name: str, source: str, relative: str):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / relative)
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compare(snapshot_path: Path, output_path: Path, vix_source: Path | None = None):
    baseline = json.loads(snapshot_path.read_text())
    for symbol, item in baseline["data"].items():
        if _hash(item["candles"]) != item["sha256"]:
            raise ValueError(f"Frozen ticker candles changed for {symbol}")

    if output_path.exists():
        previous = json.loads(output_path.read_text())
        vix_candles = previous["vix_candles"]
        if _hash(vix_candles) != previous["vix_sha256"]:
            raise ValueError("VIX context candles changed")
    elif vix_source is not None:
        previous = json.loads(vix_source.read_text())
        vix_candles = previous["vix_candles"]
        if _hash(vix_candles) != previous["vix_sha256"]:
            raise ValueError("VIX source candles changed")
    else:
        vix_candles = _fetch_ohlcv("^VIX", baseline["period"], baseline["interval"])
    last_scored_date = min(item["last_date"] for item in baseline["data"].values())
    vix_candles = [c for c in vix_candles if c["date"] <= last_scored_date]

    rows = []
    source_hashes = {}
    for family, (relative, function_name) in FAMILIES.items():
        before_source = _source(baseline["commit"], relative)
        after_source = (ROOT / relative).read_text()
        source_hashes[family] = {
            "before_sha256": hashlib.sha256(before_source.encode()).hexdigest(),
            "after_sha256": hashlib.sha256(after_source.encode()).hexdigest(),
        }
        before_fn = getattr(_load(f"{family}_before", before_source, relative), function_name)
        after_fn = getattr(_load(f"{family}_after", after_source, relative), function_name)
        for symbol, item in baseline["data"].items():
            candles = item["candles"]
            settings = {"symbol": symbol, "period": baseline["period"]}
            old = before_fn(candles, vix_candles, settings)
            new = after_fn(candles, vix_candles, settings)
            rows.append({
                "symbol": symbol,
                "strategy": family,
                "before_return_pct": old["total_return_pct"],
                "after_return_pct": new["total_return_pct"],
                "change_percentage_points": round(new["total_return_pct"] - old["total_return_pct"], 2),
                "before_trades": old["total_trades"],
                "after_trades": new["total_trades"],
                "before_reentry_mode": old.get("reentry_mode"),
                "after_reentry_mode": new.get("reentry_mode"),
            })
    output = {
        "compared_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": baseline["commit"],
        "source_note": "The pre-change source is reconstructed from the baseline Git commit; both versions use identical frozen ticker and VIX candles.",
        "ticker_snapshot": str(snapshot_path),
        "vix_sha256": _hash(vix_candles),
        "vix_first_date": vix_candles[0]["date"],
        "vix_last_date": vix_candles[-1]["date"],
        "vix_candles": vix_candles,
        "source_hashes": source_hashes,
        "rows": rows,
    }
    output_path.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    for row in rows:
        print(row["symbol"], row["strategy"], row["before_return_pct"], row["after_return_pct"], row["change_percentage_points"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vix-source", type=Path)
    args = parser.parse_args()
    compare(args.snapshot, args.output, args.vix_source)
