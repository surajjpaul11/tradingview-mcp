"""
EMA Sweep Test — Test EMA price crossover from EMA(7) to EMA(50)
================================================================

For each EMA period, buys when price crosses above the EMA and sells when
price crosses below.  Tests on SPY and QQQ over 2 years and reports the
top 3 returns.

Usage:
    python strategies/ema_sweep_test.py
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Optional


# =============================================================================
# DATA
# =============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "ema-sweep/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval in ("1h", "30m", "15m", "5m") else "%Y-%m-%d"
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
            "open": round(o, 4), "high": round(h, 4),
            "low": round(l, 4), "close": round(c, 4),
            "volume": v or 0,
        })
    return candles


# =============================================================================
# EMA INDICATOR
# =============================================================================

def calc_ema(closes: list[float], period: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return result
    k = 2 / (period + 1)
    sma = sum(closes[:period]) / period
    result[period - 1] = sma
    for i in range(period, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


# =============================================================================
# EMA PRICE CROSSOVER STRATEGY
# =============================================================================

def run_ema_strategy(candles: list[dict], ema_period: int) -> list[dict]:
    """Buy when price crosses above EMA, sell when price crosses below."""
    closes = [c["close"] for c in candles]
    ema = calc_ema(closes, ema_period)
    trades = []
    position = None

    for i in range(1, len(candles)):
        if ema[i] is None or ema[i - 1] is None:
            continue
        price = closes[i]
        prev_price = closes[i - 1]
        date = candles[i]["date"]

        # Price crosses above EMA -> buy
        if position is None and prev_price < ema[i - 1] and price >= ema[i]:
            position = {"entry_date": date, "entry_price": price}

        # Price crosses below EMA -> sell
        elif position is not None and prev_price > ema[i - 1] and price <= ema[i]:
            trades.append({
                **position,
                "exit_date": date,
                "exit_price": price,
                "side": "long",
                "strategy": f"ema_{ema_period}",
            })
            position = None

    # Close open position at end of data
    if position is not None:
        trades.append({
            **position,
            "exit_date": candles[-1]["date"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "strategy": f"ema_{ema_period}",
        })

    return trades


# =============================================================================
# METRICS
# =============================================================================

def calc_return(trades: list[dict], initial_capital: float = 10_000.0,
                commission_pct: float = 0.1, slippage_pct: float = 0.05) -> dict:
    total_cost_pct = (commission_pct + slippage_pct) * 2  # round-trip
    capital = initial_capital
    wins = 0
    for t in trades:
        gross_pct = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net_pct = gross_pct - total_cost_pct
        pnl = capital * (net_pct / 100)
        capital += pnl
        if net_pct > 0:
            wins += 1

    total_return = (capital - initial_capital) / initial_capital * 100
    win_rate = (wins / len(trades) * 100) if trades else 0

    return {
        "total_return_pct": round(total_return, 2),
        "total_trades": len(trades),
        "win_rate_pct": round(win_rate, 1),
        "final_capital": round(capital, 2),
    }


# =============================================================================
# MAIN — SWEEP EMA 7..50 ON SPY AND QQQ
# =============================================================================

def main():
    symbols = ["SPY", "QQQ"]
    ema_range = range(7, 51)  # EMA 7 through EMA 50
    results = []

    for symbol in symbols:
        print(f"Fetching {symbol} 2y daily data...")
        candles = fetch_ohlcv(symbol, "2y", "1d")
        bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
        print(f"  {len(candles)} bars | B&H: {bnh:+.2f}%")

        for period in ema_range:
            trades = run_ema_strategy(candles, period)
            metrics = calc_return(trades)
            results.append({
                "symbol": symbol,
                "ema_period": period,
                "buy_and_hold_pct": bnh,
                **metrics,
            })

    # Sort by total return and show top 3
    results.sort(key=lambda x: x["total_return_pct"], reverse=True)
    top3 = results[:3]

    print(f"\n{'='*70}")
    print(f"  TOP 3 EMA STRATEGIES (EMA 7-50, SPY + QQQ, 2y daily)")
    print(f"{'='*70}")
    print(f"  {'Rank':<5} {'Symbol':<7} {'EMA':<6} {'Return':>9} {'B&H':>9} {'vs B&H':>9} {'Trades':>7} {'Win%':>7}")
    print(f"  {'-'*60}")
    for rank, r in enumerate(top3, 1):
        vs_bnh = round(r["total_return_pct"] - r["buy_and_hold_pct"], 2)
        print(f"  {rank:<5} {r['symbol']:<7} {r['ema_period']:<6} "
              f"{r['total_return_pct']:>+8.2f}% {r['buy_and_hold_pct']:>+8.2f}% "
              f"{vs_bnh:>+8.2f}% {r['total_trades']:>6} {r['win_rate_pct']:>6.1f}%")
    print(f"{'='*70}\n")

    # Also show full table for reference
    print(f"  FULL RESULTS (sorted by return):")
    print(f"  {'Symbol':<7} {'EMA':<6} {'Return':>9} {'Trades':>7} {'Win%':>7}")
    print(f"  {'-'*40}")
    for r in results[:20]:  # top 20
        print(f"  {r['symbol']:<7} {r['ema_period']:<6} "
              f"{r['total_return_pct']:>+8.2f}% {r['total_trades']:>6} {r['win_rate_pct']:>6.1f}%")
    if len(results) > 20:
        print(f"  ... ({len(results) - 20} more)")
    print()


if __name__ == "__main__":
    main()
