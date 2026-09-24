#!/usr/bin/env python3
"""Analyze whether completed-bar features distinguish Sloped Lines trade outcomes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategies.sloped_lines.sloped_lines_strategy import fetch_ohlcv, run_backtest


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.where(avg_loss.ne(0), 100.0)


def add_indicators(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles).copy()
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["rsi14"] = rsi_wilder(df["close"])
    df["volume_ma20_prior"] = df["volume"].shift(1).rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma20_prior"]
    df["volume_percentile60"] = [
        np.nan if i < 20 else float((df.loc[max(0, i - 60):i - 1, "volume"] <= df.loc[i, "volume"]).mean())
        for i in range(len(df))
    ]
    prior_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prior_close).abs(),
        (df["low"] - prior_close).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["atr_pct"] = df["atr14"] / df["close"] * 100
    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    df["above_sma200"] = df["close"] > df["sma200"]
    df["sma50_over_200"] = df["sma50"] > df["sma200"]
    df["return_5d"] = df["close"].pct_change(5) * 100
    df["return_20d"] = df["close"].pct_change(20) * 100
    df["body_pct"] = (df["close"] - df["open"]) / df["open"] * 100
    candle_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["close_location"] = (df["close"] - df["low"]) / candle_range
    return df


def line_features(result: dict, entry_date: str) -> dict:
    candidates = [
        line for line in result["trendlines"]
        if line.get("direction") == "descending" and line.get("break_date") == entry_date
    ]
    if not candidates:
        return {}
    line = candidates[-1]
    a1_bar = line["anchor1_bar"]
    a2_bar = line["anchor2_bar"]
    a1_price = line["anchor1_price"]
    a2_price = line["anchor2_price"]
    break_bar = line["break_bar"]
    slope = (a2_price - a1_price) / (a2_bar - a1_bar)
    projected = a1_price + slope * (break_bar - a1_bar)
    return {
        "anchor_span": a2_bar - a1_bar,
        "bars_after_anchor": break_bar - a2_bar,
        "line_drop_pct": (a1_price - a2_price) / a1_price * 100,
        "breakout_pct": (line["break_price"] - projected) / projected * 100 if projected else np.nan,
    }


def build_rows(period: str) -> tuple[pd.DataFrame, dict]:
    config = json.loads((ROOT / "strategies/best_parameters.json").read_text())
    tickers = config["strategies"]["sloped_lines"]["tickers"]
    rows: list[dict] = []
    summaries = {}
    for ticker, ticker_config in tickers.items():
        candles = fetch_ohlcv(ticker, period=period, interval="1d")
        params = ticker_config["parameters"]
        result = run_backtest(ticker, period, "1d", candles=candles, **params)
        frame = add_indicators(candles)
        by_date = {date: i for i, date in enumerate(frame["date"])}
        completed = [trade for trade in result["trade_log"] if trade.get("exit_reason") != "end_of_data"]
        summaries[ticker] = {
            "candles": len(candles),
            "date_from": candles[0]["date"],
            "date_to": candles[-1]["date"],
            "trades": len(completed),
            "win_rate": 100 * sum(t["return_pct"] > 0 for t in completed) / len(completed) if completed else 0,
            "return_pct": 100 * (np.prod([1 + t["return_pct"] / 100 for t in completed]) - 1),
        }
        for trade_number, trade in enumerate(completed, start=1):
            i = by_date[trade["entry_date"]]
            current = frame.iloc[i]
            previous = frame.iloc[i - 1] if i else current
            row = {
                "ticker": ticker,
                "trade_number": trade_number,
                "entry_date": trade["entry_date"],
                "exit_date": trade["exit_date"],
                "return_pct": trade["return_pct"],
                "winner": int(trade["return_pct"] > 0),
                "rsi14_signal": current["rsi14"],
                "volume_ratio_signal": current["volume_ratio"],
                "volume_percentile60_signal": current["volume_percentile60"],
                "rsi14_prior": previous["rsi14"],
                "volume_ratio_prior": previous["volume_ratio"],
                "volume_percentile60_prior": previous["volume_percentile60"],
                "atr_pct_prior": previous["atr_pct"],
                "above_sma200_prior": int(previous["above_sma200"]),
                "sma50_over_200_prior": int(previous["sma50_over_200"]),
                "return_5d_prior": previous["return_5d"],
                "return_20d_prior": previous["return_20d"],
                "body_pct_signal": current["body_pct"],
                "close_location_signal": current["close_location"],
            }
            row.update(line_features(result, trade["entry_date"]))
            rows.append(row)
    return pd.DataFrame(rows), summaries


def group_metrics(frame: pd.DataFrame, mask: pd.Series) -> dict:
    group = frame.loc[mask]
    if group.empty:
        return {"n": 0}
    returns = group["return_pct"]
    return {
        "n": len(group),
        "wins": int(group["winner"].sum()),
        "win_rate": round(group["winner"].mean() * 100, 1),
        "mean_return": round(returns.mean(), 3),
        "median_return": round(returns.median(), 3),
        "compounded_return": round((np.prod(1 + returns / 100) - 1) * 100, 2),
        "worst_return": round(returns.min(), 3),
    }


def threshold_tables(frame: pd.DataFrame) -> dict:
    specs = {
        "prior_rsi_lt_50": frame["rsi14_prior"] < 50,
        "prior_rsi_50_60": frame["rsi14_prior"].between(50, 60, inclusive="left"),
        "prior_rsi_ge_60": frame["rsi14_prior"] >= 60,
        "signal_rsi_lt_50": frame["rsi14_signal"] < 50,
        "signal_rsi_50_60": frame["rsi14_signal"].between(50, 60, inclusive="left"),
        "signal_rsi_ge_60": frame["rsi14_signal"] >= 60,
        "prior_volume_lt_0_8": frame["volume_ratio_prior"] < 0.8,
        "prior_volume_0_8_1_2": frame["volume_ratio_prior"].between(0.8, 1.2, inclusive="left"),
        "prior_volume_ge_1_2": frame["volume_ratio_prior"] >= 1.2,
        "signal_volume_lt_0_8": frame["volume_ratio_signal"] < 0.8,
        "signal_volume_0_8_1_2": frame["volume_ratio_signal"].between(0.8, 1.2, inclusive="left"),
        "signal_volume_ge_1_2": frame["volume_ratio_signal"] >= 1.2,
        "prior_rsi_ge_50_and_volume_ge_1_2": (frame["rsi14_prior"] >= 50) & (frame["volume_ratio_prior"] >= 1.2),
        "signal_rsi_ge_50_and_volume_ge_1_2": (frame["rsi14_signal"] >= 50) & (frame["volume_ratio_signal"] >= 1.2),
        "above_sma200_prior": frame["above_sma200_prior"] == 1,
        "below_sma200_prior": frame["above_sma200_prior"] == 0,
    }
    return {name: group_metrics(frame, mask.fillna(False)) for name, mask in specs.items()}


def chronological_validation(frame: pd.DataFrame) -> dict:
    out = {}
    for ticker, group in frame.groupby("ticker"):
        group = group.sort_values("entry_date")
        cut = max(1, int(len(group) * 0.7))
        group = group.assign(segment=["train"] * cut + ["test"] * (len(group) - cut))
        out[ticker] = {}
        for segment, segment_group in group.groupby("segment"):
            out[ticker][segment] = {
                "all": group_metrics(segment_group, pd.Series(True, index=segment_group.index)),
                "prior_rsi_ge_50": group_metrics(segment_group, segment_group["rsi14_prior"] >= 50),
                "prior_volume_ge_1_2": group_metrics(segment_group, segment_group["volume_ratio_prior"] >= 1.2),
                "prior_combo": group_metrics(segment_group, (segment_group["rsi14_prior"] >= 50) & (segment_group["volume_ratio_prior"] >= 1.2)),
                "signal_combo": group_metrics(segment_group, (segment_group["rsi14_signal"] >= 50) & (segment_group["volume_ratio_signal"] >= 1.2)),
            }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="5y")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis/sloped_lines_conviction")
    args = parser.parse_args()
    frame, summaries = build_rows(args.period)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_dir / "entry_features.csv", index=False)
    report = {
        "period": args.period,
        "summaries": summaries,
        "all_trades": group_metrics(frame, pd.Series(True, index=frame.index)),
        "thresholds": threshold_tables(frame),
        "by_ticker": {ticker: threshold_tables(group) for ticker, group in frame.groupby("ticker")},
        "chronological_validation": chronological_validation(frame),
        "feature_correlations": frame.select_dtypes(include=["number"]).corr(method="spearman")["return_pct"].sort_values(ascending=False).round(3).to_dict(),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
