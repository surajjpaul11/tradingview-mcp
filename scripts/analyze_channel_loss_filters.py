"""Re-run Enhanced Channel with historical, same-bar entry confirmations.

Run: PYTHONPATH=src python scripts/analyze_channel_loss_filters.py
This is exploratory research on a frozen five-stock snapshot, not validation.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tradingview_mcp.core.services import backtest_service as bt


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/returns_baseline_completed_2026-09-18.json"
OUTPUT = ROOT / "docs/enhanced_channel_loss_filters.json"


def active_mask(candles, runner):
    """True while a second strategy holds a long at that bar's close."""
    try:
        trades = runner(candles, include_open=True)
    except TypeError as exc:
        if "include_open" not in str(exc):
            raise
        trades = runner(candles)
    return [any(t.get("side", "long") == "long" and
                t["entry_date"] <= c["date"] and
                (t.get("exit_date") is None or t.get("exit_reason") == "end_of_data"
                 or c["date"] < t["exit_date"])
                for t in trades) for c in candles]


def recent_volume_mask(candles, lookback=5):
    trades = bt._STRATEGY_MAP["volume_price_breakout"](candles, include_open=True)
    signal_dates = {t.get("signal_date", t["entry_date"]) for t in trades}
    signals = [c["date"] in signal_dates for c in candles]
    return [any(signals[max(0, i - lookback + 1):i + 1]) for i in range(len(candles))]


def summarise(raw, split_date):
    # Channel's end_of_data event is an open position marked to the last bar.
    closed = [t for t in raw if t.get("exit_reason") != "end_of_data"]
    net = bt._apply_costs(closed, 0.1, 0.05)
    metrics = bt._calc_metrics(net, 10_000, "1d")
    def counts(rows):
        return {"trades": len(rows), "losses": sum(t["return_pct"] <= 0 for t in rows),
                "wins": sum(t["return_pct"] > 0 for t in rows)}
    return {**counts(net), "total_return_pct": metrics["total_return_pct"],
            "early": counts([t for t in net if t["entry_date"] < split_date]),
            "later": counts([t for t in net if t["entry_date"] >= split_date]),
            "exit_reasons": dict(sorted((reason, sum(t["exit_reason"] == reason for t in net))
                                        for reason in {t["exit_reason"] for t in net})),
            "largest_win_pct": max((t["return_pct"] for t in net), default=None),
            "worst_loss_pct": min((t["return_pct"] for t in net), default=None)}


def main():
    snapshot = json.loads(SNAPSHOT.read_text())
    names = ("baseline", "rsi_active", "bollinger_active", "rsi_or_bollinger",
             "rsi_and_bollinger", "bollinger_below_middle", "bollinger_lower_reclaim",
             "enhanced_lines_active", "volume_breakout_recent_5")
    results = {name: {} for name in names}
    for symbol, item in snapshot["data"].items():
        candles = item["candles"]
        closes = [c["close"] for c in candles]
        bb = bt.calc_bollinger(closes, 20, 2.0)
        rsi = active_mask(candles, bt._run_rsi)
        bollinger = active_mask(candles, bt._run_bollinger)
        lines = active_mask(candles, bt._STRATEGY_MAP["enhanced_lines"])
        volume = recent_volume_mask(candles)
        below_middle = [m is not None and c < m for c, m in zip(closes, bb["middle"])]
        lower_reclaim = [False] + [bb["lower"][i - 1] is not None and
                                     closes[i - 1] < bb["lower"][i - 1] and
                                     bb["lower"][i] is not None and closes[i] > bb["lower"][i]
                                     for i in range(1, len(candles))]
        masks = {
            "rsi_active": rsi,
            "bollinger_active": bollinger,
            "rsi_or_bollinger": [a or b for a, b in zip(rsi, bollinger)],
            "rsi_and_bollinger": [a and b for a, b in zip(rsi, bollinger)],
            "bollinger_below_middle": below_middle,
            "bollinger_lower_reclaim": lower_reclaim,
            "enhanced_lines_active": lines,
            "volume_breakout_recent_5": volume,
        }
        split_date = candles[int(len(candles) * .7)]["date"]
        for name in names:
            kwargs = {} if name == "baseline" else {"long_entry_mask": masks[name]}
            raw = bt._STRATEGY_MAP["enhanced_channel"](candles, **kwargs)
            results[name][symbol] = summarise(raw, split_date)
        # Confirm the most promising secondary state at every observed entry.
        entry_dates = {t["entry_date"] for name in names
                       for t in bt._STRATEGY_MAP["enhanced_channel"](
                           candles, **({} if name == "baseline" else {"long_entry_mask": masks[name]}))}
        for i, candle in enumerate(candles):
            if candle["date"] in entry_dates:
                prefix = bt._run_bollinger(candles[:i + 1], include_open=True)
                prefix_active = bool(prefix and prefix[-1].get("exit_date") is None)
                if prefix_active != bollinger[i]:
                    raise AssertionError(f"Bollinger state changed with future data: {symbol} {candle['date']}")
    report = {
        "snapshot": str(SNAPSHOT.relative_to(ROOT)),
        "method": "Rerun Channel state machine with same-close entry masks; exclude end-of-data marks; 0.1% commission and 0.05% slippage each side.",
        "limitations": "Exploratory five-symbol historical comparison. The later 30% is a date slice, not an untouched holdout. Channel still assumes same-close fills. Do not interpret as a calibrated probability or live recommendation.",
        "results": results,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    for name, stocks in results.items():
        total = sum(x["trades"] for x in stocks.values())
        losses = sum(x["losses"] for x in stocks.values())
        mean = sum(x["total_return_pct"] for x in stocks.values()) / len(stocks)
        print(f"{name:28} trades={total:2} losses={losses:2} mean_stock_return={mean:.2f}%")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
