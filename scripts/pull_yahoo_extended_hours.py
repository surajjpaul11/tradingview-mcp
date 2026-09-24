#!/usr/bin/env python3
"""Pull timestamped Yahoo pre-market, regular, and after-hours candles."""
from __future__ import annotations

import argparse
import json
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


def session_for(timestamp: pd.Timestamp, timezone_name: str) -> str:
    local = timestamp.to_pydatetime().astimezone(ZoneInfo(timezone_name))
    clock = local.time().replace(tzinfo=None)
    if time(4, 0) <= clock < time(9, 30):
        return "pre-market"
    if time(9, 30) <= clock < time(16, 0):
        return "regular market"
    if time(16, 0) <= clock < time(20, 0):
        return "after hours"
    return "overnight"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "NVDA", "AMD", "SPY"])
    parser.add_argument("--period", default="5d")
    parser.add_argument("--interval", default="30m")
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument("--output-dir", type=Path, default=Path("analysis/yahoo_extended_hours"))
    args = parser.parse_args()

    frames: list[pd.DataFrame] = []
    summary: dict[str, dict] = {}
    for symbol in args.symbols:
        data = yf.Ticker(symbol).history(period=args.period, interval=args.interval, prepost=True)
        if data.empty:
            summary[symbol] = {"rows": 0, "sessions": {}}
            continue
        data = data.reset_index()
        timestamp_column = "Datetime" if "Datetime" in data.columns else "Date"
        data = data.rename(columns={timestamp_column: "timestamp"})
        data.insert(0, "symbol", symbol.upper())
        data["timestamp_ny"] = data["timestamp"].map(
            lambda value: value.to_pydatetime().astimezone(ZoneInfo(args.timezone)).isoformat()
        )
        data["session"] = data["timestamp"].map(lambda value: session_for(value, args.timezone))
        data["volume_nonzero"] = pd.to_numeric(data["Volume"], errors="coerce").fillna(0).gt(0)
        frames.append(data)
        session_summary = {}
        for session, group in data.groupby("session"):
            session_summary[session] = {
                "candles": int(len(group)),
                "candles_with_nonzero_volume": int(group["volume_nonzero"].sum()),
            }
        summary[symbol.upper()] = {
            "rows": int(len(data)),
            "first_timestamp_ny": data["timestamp_ny"].iloc[0],
            "last_timestamp_ny": data["timestamp_ny"].iloc[-1],
            "sessions": session_summary,
        }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    output_columns = [
        "symbol", "timestamp_ny", "session", "Open", "High", "Low", "Close", "Volume",
        "Dividends", "Stock Splits", "volume_nonzero",
    ]
    combined[[column for column in output_columns if column in combined.columns]].to_csv(
        args.output_dir / f"yahoo_extended_{args.interval}_{args.period}.csv", index=False
    )
    metadata = {
        "source": "Yahoo Finance via yfinance",
        "period": args.period,
        "interval": args.interval,
        "timezone": args.timezone,
        "prepost": True,
        "symbols": summary,
    }
    (args.output_dir / f"yahoo_extended_{args.interval}_{args.period}_summary.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
