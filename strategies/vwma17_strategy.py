"""
VWMA 17 Strategy — Standalone Python Implementation
====================================================

Mirrors the Pine Script v6 strategy (vwma17_strategy.pine) exactly.

Logic:
  - Long entry:  close crosses above VWMA(17)
  - Short entry: close crosses below VWMA(17)
  - Exit:        ATR-based stop loss (1.5x ATR) and take profit (2.0x ATR)

Usage:
  python vwma17_strategy.py                          # defaults: BTC-USD, 1y, daily
  python vwma17_strategy.py --symbol ETH-USD --period 2y
  python vwma17_strategy.py --symbol AAPL --period 1y --initial-capital 25000

Requires: no external dependencies (pure stdlib + Yahoo Finance API)
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import urllib.request
from datetime import datetime, timezone
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY PARAMETERS (match Pine Script inputs)
# ═══════════════════════════════════════════════════════════════════════════════

VWMA_LENGTH     = 17
ATR_LENGTH      = 14
ATR_MULTIPLIER  = 1.5
TP_MULTIPLIER   = 2.0
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.1    # per trade, percent
SLIPPAGE_PCT    = 0.05   # per trade, percent


# ═══════════════════════════════════════════════════════════════════════════════
# INDICATORS (pure Python, zero dependencies)
# ═══════════════════════════════════════════════════════════════════════════════

def calc_vwma(closes: list[float], volumes: list[float], period: int = 17) -> list[Optional[float]]:
    """Volume Weighted Moving Average = sum(close*volume, period) / sum(volume, period)"""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    for i in range(period - 1, n):
        wc = closes[i - period + 1 : i + 1]
        wv = volumes[i - period + 1 : i + 1]
        vol_sum = sum(wv)
        result[i] = sum(c * v for c, v in zip(wc, wv)) / vol_sum if vol_sum else sum(wc) / period
    return result


def calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Optional[float]]:
    """Average True Range (Wilder's smoothing)"""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period + 1:
        return result
    trs = []
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    result[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + trs[i - 1]) / period
        result[i] = atr
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING (Yahoo Finance, no API key needed)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_ohlcv(symbol: str, period: str = "1y", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "vwma17-strategy/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval == "1h" else "%Y-%m-%d"

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


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_vwma17(
    candles: list[dict],
    vwma_length: int = VWMA_LENGTH,
    atr_length: int = ATR_LENGTH,
    atr_multiplier: float = ATR_MULTIPLIER,
    tp_multiplier: float = TP_MULTIPLIER,
) -> list[dict]:
    """
    Run VWMA 17 strategy on OHLCV candles. Returns list of completed trades.

    Each trade dict contains:
      entry_date, entry_price, exit_date, exit_price,
      side (long/short), exit_reason (stop_loss/take_profit), strategy
    """
    closes  = [c["close"]  for c in candles]
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    volumes = [c["volume"] for c in candles]

    vwma = calc_vwma(closes, volumes, vwma_length)
    atr  = calc_atr(highs, lows, closes, atr_length)

    trades   = []
    position = None

    for i in range(1, len(candles)):
        if vwma[i] is None or vwma[i - 1] is None or atr[i] is None:
            continue

        price = candles[i]["close"]
        high  = candles[i]["high"]
        low   = candles[i]["low"]
        date  = candles[i]["date"]

        # ── Check exits (SL/TP) ──
        if position is not None:
            hit_sl = hit_tp = False
            if position["side"] == "long":
                hit_sl = low <= position["stop_loss"]
                hit_tp = high >= position["take_profit"]
            else:
                hit_sl = high >= position["stop_loss"]
                hit_tp = low <= position["take_profit"]

            if hit_sl or hit_tp:
                exit_price = position["stop_loss"] if hit_sl else position["take_profit"]
                exit_reason = "stop_loss" if hit_sl else "take_profit"
                trades.append({
                    "entry_date":  position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date":   date,
                    "exit_price":  exit_price,
                    "side":        position["side"],
                    "exit_reason": exit_reason,
                    "strategy":    "vwma17",
                })
                position = None

        # ── Check entries (crossover / crossunder) ──
        if position is None:
            if closes[i - 1] <= vwma[i - 1] and closes[i] > vwma[i]:
                position = {
                    "entry_date": date, "entry_price": price, "side": "long",
                    "stop_loss":   price - atr[i] * atr_multiplier,
                    "take_profit": price + atr[i] * tp_multiplier,
                }
            elif closes[i - 1] >= vwma[i - 1] and closes[i] < vwma[i]:
                position = {
                    "entry_date": date, "entry_price": price, "side": "short",
                    "stop_loss":   price + atr[i] * atr_multiplier,
                    "take_profit": price - atr[i] * tp_multiplier,
                }

    return trades


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS & REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply transaction costs to each trade."""
    total_cost = (commission_pct + slippage_pct) * 2  # entry + exit
    result = []
    for t in trades:
        if t["side"] == "short":
            gross = (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100
        else:
            gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net = round(gross - total_cost, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3), "cost_pct": round(-total_cost, 3)})
    return result


def calc_metrics(trades: list[dict], initial_capital: float) -> dict:
    """Calculate institutional-grade backtest metrics."""
    if not trades:
        return {"total_trades": 0, "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "sharpe_ratio": 0, "profit_factor": 0}

    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]

    capital = initial_capital
    peak    = capital
    max_dd  = 0.0
    returns = []
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak   = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak * 100)

    total_ret  = (capital - initial_capital) / initial_capital * 100
    avg_gain   = sum(t["return_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss   = sum(t["return_pct"] for t in losers)  / len(losers)  if losers  else 0
    gp         = sum(t["return_pct"] for t in winners)
    gl         = abs(sum(t["return_pct"] for t in losers))
    pf         = round(gp / gl, 2) if gl > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r  = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / 252) / std_r * math.sqrt(252), 2)

    wr = len(winners) / len(trades)

    # Count SL vs TP exits
    sl_count = sum(1 for t in trades if t.get("exit_reason") == "stop_loss")
    tp_count = sum(1 for t in trades if t.get("exit_reason") == "take_profit")
    long_count  = sum(1 for t in trades if t.get("side") == "long")
    short_count = sum(1 for t in trades if t.get("side") == "short")

    return {
        "total_trades":     len(trades),
        "winning_trades":   len(winners),
        "losing_trades":    len(losers),
        "long_trades":      long_count,
        "short_trades":     short_count,
        "sl_exits":         sl_count,
        "tp_exits":         tp_count,
        "win_rate_pct":     round(wr * 100, 1),
        "final_capital":    round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "avg_gain_pct":     round(avg_gain, 2),
        "avg_loss_pct":     round(avg_loss, 2),
        "max_drawdown_pct": round(-max_dd, 2),
        "profit_factor":    pf,
        "sharpe_ratio":     sharpe,
        "expectancy_pct":   round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }


def run_backtest(
    symbol: str = "BTC-USD",
    period: str = "1y",
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    vwma_length: int = VWMA_LENGTH,
    atr_length: int = ATR_LENGTH,
    atr_multiplier: float = ATR_MULTIPLIER,
    tp_multiplier: float = TP_MULTIPLIER,
) -> dict:
    """Full backtest pipeline: fetch data → run strategy → compute metrics."""
    candles = fetch_ohlcv(symbol, period)
    raw_trades = run_vwma17(candles, vwma_length, atr_length, atr_multiplier, tp_multiplier)
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "vwma17",
        "strategy_label": "VWMA 17 Crossover (ATR Stop/TP)",
        "parameters": {
            "vwma_length": vwma_length,
            "atr_length": atr_length,
            "atr_multiplier": atr_multiplier,
            "tp_multiplier": tp_multiplier,
        },
        "period": period,
        "candles_analyzed": len(candles),
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "initial_capital": initial_capital,
        "commission_pct": commission_pct,
        "slippage_pct": slippage_pct,
        **metrics,
        "buy_and_hold_return_pct": bnh,
        "vs_buy_and_hold_pct": round(metrics["total_return_pct"] - bnh, 2),
        "trade_log": trades,
        "data_source": "Yahoo Finance",
        "disclaimer": "Past performance does not guarantee future results. For educational use only.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="VWMA 17 Strategy Backtester")
    parser.add_argument("--symbol", default="BTC-USD", help="Yahoo Finance symbol (default: BTC-USD)")
    parser.add_argument("--period", default="1y", choices=["1mo", "3mo", "6mo", "1y", "2y"], help="Data period")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--vwma-length", type=int, default=VWMA_LENGTH)
    parser.add_argument("--atr-length", type=int, default=ATR_LENGTH)
    parser.add_argument("--atr-mult", type=float, default=ATR_MULTIPLIER)
    parser.add_argument("--tp-mult", type=float, default=TP_MULTIPLIER)
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  VWMA 17 Strategy Backtest — {args.symbol}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        vwma_length=args.vwma_length, atr_length=args.atr_length,
        atr_multiplier=args.atr_mult, tp_multiplier=args.tp_mult,
    )

    # Summary
    print(f"  Period:           {result['date_from']} → {result['date_to']} ({result['candles_analyzed']} bars)")
    print(f"  Initial Capital:  ${result['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${result['final_capital']:,.2f}")
    print(f"  Total Return:     {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:     {result['total_trades']} (L:{result['long_trades']} S:{result['short_trades']})")
    print(f"  Win Rate:         {result['win_rate_pct']}%")
    print(f"  Profit Factor:    {result['profit_factor']}")
    print(f"  Sharpe Ratio:     {result['sharpe_ratio']}")
    print(f"  Max Drawdown:     {result['max_drawdown_pct']}%")
    print(f"  SL Exits:         {result['sl_exits']}  |  TP Exits: {result['tp_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t.get("side", "long").upper()
        print(f"    {side:5s} {t['entry_date']} → {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} → ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    # Also dump JSON for programmatic use
    with open(f"vwma17_backtest_{args.symbol.replace('-','_')}_{args.period}.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: vwma17_backtest_{args.symbol.replace('-','_')}_{args.period}.json\n")


if __name__ == "__main__":
    main()
