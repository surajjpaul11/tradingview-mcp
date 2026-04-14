#!/usr/bin/env python3
"""
Adaptive Smart Hold — Wrapper
===============================
Dispatches to the right strategy based on stock volatility:
  - High vol (ATR% > 6%): Smart Hold + RC re-entry
  - Low vol (ATR% <= 6%): Original Smart Hold (unchanged)

This avoids reimplementing Smart Hold's full signal suite —
just routes to the correct engine.

Usage:
    python3 strategies/smart_hold_rc/run_adaptive.py --symbol SPY --period 2y --chart
    python3 strategies/smart_hold_rc/run_adaptive.py --symbol SNDK --period 2y --chart
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

VOL_THRESHOLD = 10.0  # ATR% threshold — empirically optimal


def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "adaptive/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
                         "open": round(o, 4), "high": round(h, 4),
                         "low": round(l, 4), "close": round(c, 4), "volume": v or 0})
    return candles


def calc_median_atr_pct(candles: list[dict]) -> float:
    """Compute median ATR% over first 100 bars."""
    closes = [c["close"] for c in candles]
    # Simple ATR calculation
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["high"] - c["low"])
        else:
            prev = candles[i-1]["close"]
            trs.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))

    # EMA of TR
    period = 14
    atr_vals = [None] * len(candles)
    k = 2.0 / (period + 1)
    for i in range(len(trs)):
        if i == 0: atr_vals[i] = trs[i]
        elif i < period - 1: atr_vals[i] = trs[i] * k + atr_vals[i-1] * (1-k)
        elif i == period - 1: atr_vals[i] = sum(trs[:period]) / period
        else: atr_vals[i] = trs[i] * k + atr_vals[i-1] * (1-k)

    pcts = []
    for i in range(min(100, len(candles))):
        if atr_vals[i] is not None and closes[i] > 0:
            pcts.append(atr_vals[i] / closes[i] * 100)
    return sorted(pcts)[len(pcts) // 2] if pcts else 1.5


def main():
    parser = argparse.ArgumentParser(description="Adaptive Smart Hold")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--initial-capital", type=float, default=10_000.0)
    parser.add_argument("--vol-threshold", type=float, default=VOL_THRESHOLD)
    parser.add_argument("--chart", action="store_true")
    args = parser.parse_args()

    candles = fetch_ohlcv(args.symbol, args.period)
    vix_candles = fetch_ohlcv("^VIX", args.period)
    median_atr = calc_median_atr_pct(candles)

    use_rc = median_atr > args.vol_threshold

    print(f"\n{'='*65}")
    print(f"  Adaptive Smart Hold — {args.symbol}")
    print(f"  Median ATR%: {median_atr:.2f}%  Threshold: {args.vol_threshold}%")
    print(f"  Selected mode: {'REVERSAL CHANNEL re-entry' if use_rc else 'STANDARD Smart Hold'}")
    print(f"{'='*65}")

    if use_rc:
        from strategies.smart_hold_rc.smart_hold_rc_strategy import run_smart_hold_rc
        result = run_smart_hold_rc(candles, vix_candles, {
            "symbol": args.symbol, "period": args.period,
            "initial_capital": args.initial_capital,
            "force_rc": True,
        })
    else:
        from strategies.smart_hold.smart_hold_strategy import run_smart_hold
        result = run_smart_hold(candles, vix_candles, {
            "symbol": args.symbol, "period": args.period,
            "initial_capital": args.initial_capital,
        })

    # Annotate result
    result["adaptive_mode"] = "reversal_channel" if use_rc else "standard"
    result["median_atr_pct"] = round(median_atr, 2)

    print(f"\n  Mode:            {'RC re-entry' if use_rc else 'Standard re-entry'} (ATR%={median_atr:.2f}%)")
    print(f"  Period:          {result['date_from']} -> {result['date_to']}")
    print(f"  Total Return:    {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:      {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:          {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:    {result['total_trades']}")
    print(f"  Win Rate:        {result['win_rate_pct']}%")
    pf = result.get('profit_factor', 0)
    print(f"  Profit Factor:   {pf}")
    print(f"  Max Drawdown:    {result['max_drawdown_pct']}%")

    print(f"\n  Trade Log:")
    for t in result.get("trade_log", []):
        er = t.get("entry_reason", "?")
        xr = t.get("exit_reason", "?")
        ret = t.get("return_pct", 0)
        print(f"    {er:28s}  {t['entry_date']} -> {t['exit_date']}  {ret:+7.2f}%  [{xr}]")

    print(f"\n{'='*65}\n")

    # Save
    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    fname = script_dir / f"adaptive_backtest_{safe_sym}_{args.period}.json"
    json_out = {k: v for k, v in result.items() if k != "overlays"}
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        from strategies.visualize import generate_chart_html
        chart_path = script_dir / f"adaptive_chart_{safe_sym}_{args.period}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path,
                           vix_candles=vix_candles)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
