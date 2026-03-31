"""
Buy and Protect Strategy — Standalone Python Implementation
============================================================

Long-only buy-and-hold-with-protection strategy.

Enters long immediately on bar 1. Stays invested like B&H, but exits
on danger signals to protect capital during sudden downturns:

  Exit triggers (any one fires → sell):
    1. Rapid decline: price drops X% from recent peak within Y bars
    2. MA breakdown: price closes below SMA(50)
    3. Volatility spike: ATR > 2.5x its average (crash signature)

  Re-entry modes:
    - ma_reclaim: price crosses back above the SMA (default)
    - higher_low: a new swing low forms above the previous swing low

Usage:
  python buy_and_protect_strategy.py                              # defaults: SPY, 2y, 1d
  python buy_and_protect_strategy.py --symbol QQQ --period 5y
  python buy_and_protect_strategy.py --symbol BTC-USD --period 2y --interval 1h
  python buy_and_protect_strategy.py --ma-period 200 --rapid-decline-pct 8

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


# ==============================================================================
# STRATEGY PARAMETERS
# ==============================================================================

MA_PERIOD          = 200      # SMA period for trend / re-entry
RAPID_DECLINE_PCT  = 8.0      # exit if price drops this % from recent peak
RAPID_DECLINE_BARS = 10       # rolling window for peak tracking
ATR_PERIOD         = 14       # ATR period
ATR_SPIKE_MULT     = 3.0      # exit if ATR > this * avg ATR
ATR_MA_PERIOD      = 50       # period for average ATR (spike baseline)
REENTRY_MODE       = "ma_reclaim"  # "ma_reclaim" or "higher_low"
PIVOT_LOOKBACK     = 5        # bars left/right for swing detection (higher_low mode)
INTERVAL           = "1d"     # candle size (position-level strategy)
PERIOD             = "2y"     # data lookback
INITIAL_CAPITAL    = 10_000.0
COMMISSION_PCT     = 0.1
SLIPPAGE_PCT       = 0.05


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "buy-and-protect-strategy/1.0"})
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


# ==============================================================================
# INDICATORS
# ==============================================================================

def calc_sma(values: list[float], period: int) -> list[Optional[float]]:
    """Simple Moving Average."""
    n = len(values)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    for i in range(period - 1, n):
        result[i] = sum(values[i - period + 1 : i + 1]) / period
    return result


def calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Optional[float]]:
    """Average True Range (Wilder's smoothing)."""
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


def calc_atr_ma(atr_values: list[Optional[float]], period: int = 50) -> list[Optional[float]]:
    """Moving average of ATR values (for spike detection)."""
    n = len(atr_values)
    result: list[Optional[float]] = [None] * n
    buf: list[float] = []
    for i in range(n):
        if atr_values[i] is not None:
            buf.append(atr_values[i])
            if len(buf) >= period:
                result[i] = sum(buf[-period:]) / period
    return result


def calc_rolling_peak(highs: list[float], lookback: int) -> list[float]:
    """Rolling max of highs over the last `lookback` bars."""
    result: list[float] = []
    for i in range(len(highs)):
        start = max(0, i - lookback + 1)
        result.append(max(highs[start : i + 1]))
    return result


def find_swing_lows(lows: list[float], lookback: int = 5) -> list[tuple[int, float, int]]:
    """
    Detect swing lows via pivot logic.
    Returns: list of (bar_index, price, confirmed_at_bar)
    """
    n = len(lows)
    swings: list[tuple[int, float, int]] = []
    for i in range(lookback, n - lookback):
        window = range(i - lookback, i + lookback + 1)
        if all(lows[i] <= lows[j] for j in window):
            swings.append((i, lows[i], i + lookback))
    return swings


# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_buy_and_protect(
    candles: list[dict],
    ma_period: int = MA_PERIOD,
    rapid_decline_pct: float = RAPID_DECLINE_PCT,
    rapid_decline_bars: int = RAPID_DECLINE_BARS,
    atr_period: int = ATR_PERIOD,
    atr_spike_mult: float = ATR_SPIKE_MULT,
    atr_ma_period: int = ATR_MA_PERIOD,
    reentry_mode: str = REENTRY_MODE,
    pivot_lookback: int = PIVOT_LOOKBACK,
) -> list[dict]:
    """
    Buy-and-hold with protection.

    Enters long immediately on bar 0. Exits on danger signals.
    Re-enters when conditions stabilize.

    Returns list of trade dicts.
    """
    if not candles:
        return []

    closes = [c["close"] for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]

    # --- Indicators ---
    sma     = calc_sma(closes, ma_period)
    atr     = calc_atr(highs, lows, closes, atr_period)
    atr_avg = calc_atr_ma(atr, atr_ma_period)
    peak    = calc_rolling_peak(highs, rapid_decline_bars)

    # For higher_low re-entry mode
    swing_lows = find_swing_lows(lows, pivot_lookback)
    sl_ptr = 0
    confirmed_lows: list[tuple[int, float]] = []

    # --- State ---
    trades: list[dict] = []
    position: dict | None = {
        "entry_date":  candles[0]["date"],
        "entry_price": closes[0],
        "entry_bar":   0,
    }
    last_exit_low: float | None = None  # last swing low at time of exit (for higher_low re-entry)

    for i in range(len(candles)):
        date  = candles[i]["date"]
        price = closes[i]

        # Progressively confirm swing lows
        while sl_ptr < len(swing_lows) and swing_lows[sl_ptr][2] <= i:
            confirmed_lows.append(swing_lows[sl_ptr][:2])
            sl_ptr += 1

        # --- Check exits ---
        if position is not None:
            exit_reason = None

            # Count danger signals (need 2+ to exit)
            danger_signals = 0
            primary_reason = None

            # Signal 1: Rapid decline — price dropped X% from recent peak
            decline_threshold = peak[i] * (1 - rapid_decline_pct / 100)
            if price <= decline_threshold:
                danger_signals += 1
                if not primary_reason:
                    primary_reason = "rapid_decline"

            # Signal 2: MA breakdown — close below SMA
            if sma[i] is not None and price < sma[i]:
                danger_signals += 1
                if not primary_reason:
                    primary_reason = "ma_breakdown"

            # Signal 3: Volatility spike — ATR > mult * avg ATR
            if (atr[i] is not None and atr_avg[i] is not None
                    and atr[i] > atr_spike_mult * atr_avg[i]):
                danger_signals += 1
                if not primary_reason:
                    primary_reason = "volatility_spike"

            # Need 2+ signals to exit (confluence)
            if danger_signals >= 2:
                exit_reason = primary_reason

            if exit_reason:
                trades.append({
                    "entry_date":  position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date":   date,
                    "exit_price":  price,
                    "side":        "long",
                    "exit_reason": exit_reason,
                    "strategy":    "buy_and_protect",
                })
                # Remember the last confirmed swing low for higher_low re-entry
                if confirmed_lows:
                    last_exit_low = confirmed_lows[-1][1]
                position = None

        # --- Check re-entry ---
        elif position is None:
            reenter = False

            if reentry_mode == "ma_reclaim":
                # Re-enter when price crosses back above SMA
                if sma[i] is not None and price > sma[i]:
                    reenter = True

            elif reentry_mode == "higher_low":
                # Re-enter when a new confirmed swing low is above the previous
                if (len(confirmed_lows) >= 2
                        and confirmed_lows[-1][1] > confirmed_lows[-2][1]):
                    # Also require price to be above SMA as confirmation
                    if sma[i] is not None and price > sma[i]:
                        reenter = True
                elif (last_exit_low is not None and confirmed_lows
                        and confirmed_lows[-1][1] > last_exit_low):
                    if sma[i] is not None and price > sma[i]:
                        reenter = True

            if reenter:
                position = {
                    "entry_date":  date,
                    "entry_price": price,
                    "entry_bar":   i,
                }

    # Close any open position at end of data
    if position is not None:
        trades.append({
            "entry_date":  position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date":   candles[-1]["date"],
            "exit_price":  candles[-1]["close"],
            "side":        "long",
            "exit_reason": "end_of_data",
            "strategy":    "buy_and_protect",
        })

    return trades


# ==============================================================================
# METRICS & REPORTING
# ==============================================================================

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply transaction costs to each trade."""
    total_cost = (commission_pct + slippage_pct) * 2
    result = []
    for t in trades:
        gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net = round(gross - total_cost, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3), "cost_pct": round(-total_cost, 3)})
    return result


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1d") -> dict:
    """Calculate backtest metrics."""
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "rapid_decline_exits": 0, "ma_breakdown_exits": 0,
                "volatility_spike_exits": 0, "end_of_data_exits": 0,
                "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252)

    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]

    capital = initial_capital
    peak_capital = capital
    max_dd  = 0.0
    returns = []
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak_capital = max(peak_capital, capital)
        max_dd = max(max_dd, (peak_capital - capital) / peak_capital * 100)

    total_ret = (capital - initial_capital) / initial_capital * 100
    avg_gain  = sum(t["return_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss  = sum(t["return_pct"] for t in losers)  / len(losers)  if losers  else 0
    gp        = sum(t["return_pct"] for t in winners)
    gl        = abs(sum(t["return_pct"] for t in losers))
    pf        = round(gp / gl, 2) if gl > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r  = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / ann) / std_r * math.sqrt(ann), 2)

    wr = len(winners) / len(trades) if trades else 0

    return {
        "total_trades":           len(trades),
        "winning_trades":         len(winners),
        "losing_trades":          len(losers),
        "rapid_decline_exits":    sum(1 for t in trades if t.get("exit_reason") == "rapid_decline"),
        "ma_breakdown_exits":     sum(1 for t in trades if t.get("exit_reason") == "ma_breakdown"),
        "volatility_spike_exits": sum(1 for t in trades if t.get("exit_reason") == "volatility_spike"),
        "end_of_data_exits":      sum(1 for t in trades if t.get("exit_reason") == "end_of_data"),
        "win_rate_pct":           round(wr * 100, 1),
        "final_capital":          round(capital, 2),
        "total_return_pct":       round(total_ret, 2),
        "avg_gain_pct":           round(avg_gain, 2),
        "avg_loss_pct":           round(avg_loss, 2),
        "max_drawdown_pct":       round(-max_dd, 2),
        "profit_factor":          pf,
        "sharpe_ratio":           sharpe,
        "expectancy_pct":         round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }


def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    ma_period: int = MA_PERIOD,
    rapid_decline_pct: float = RAPID_DECLINE_PCT,
    rapid_decline_bars: int = RAPID_DECLINE_BARS,
    atr_period: int = ATR_PERIOD,
    atr_spike_mult: float = ATR_SPIKE_MULT,
    atr_ma_period: int = ATR_MA_PERIOD,
    reentry_mode: str = REENTRY_MODE,
    pivot_lookback: int = PIVOT_LOOKBACK,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    raw_trades = run_buy_and_protect(candles, ma_period, rapid_decline_pct,
                                      rapid_decline_bars, atr_period, atr_spike_mult,
                                      atr_ma_period, reentry_mode, pivot_lookback)
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "buy_and_protect",
        "strategy_label": f"Buy and Protect (SMA {ma_period}, Decline {rapid_decline_pct}%, Re-entry: {reentry_mode})",
        "parameters": {
            "ma_period": ma_period,
            "rapid_decline_pct": rapid_decline_pct,
            "rapid_decline_bars": rapid_decline_bars,
            "atr_period": atr_period,
            "atr_spike_mult": atr_spike_mult,
            "atr_ma_period": atr_ma_period,
            "reentry_mode": reentry_mode,
        },
        "period": period,
        "interval": interval,
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


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Buy and Protect Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size (default: 1d)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--ma-period", type=int, default=MA_PERIOD, help="SMA period for trend/re-entry (default: 50)")
    parser.add_argument("--rapid-decline-pct", type=float, default=RAPID_DECLINE_PCT, help="Exit if price drops this %% from peak (default: 5.0)")
    parser.add_argument("--rapid-decline-bars", type=int, default=RAPID_DECLINE_BARS, help="Rolling peak lookback bars (default: 10)")
    parser.add_argument("--atr-period", type=int, default=ATR_PERIOD, help="ATR period (default: 14)")
    parser.add_argument("--atr-spike-mult", type=float, default=ATR_SPIKE_MULT, help="Volatility spike threshold (default: 2.5)")
    parser.add_argument("--atr-ma-period", type=int, default=ATR_MA_PERIOD, help="ATR moving avg period (default: 50)")
    parser.add_argument("--reentry-mode", default=REENTRY_MODE, choices=["ma_reclaim", "higher_low"],
                        help="Re-entry trigger (default: ma_reclaim)")
    parser.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK, help="Swing detection lookback for higher_low mode (default: 5)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Buy and Protect Strategy — {args.symbol}")
    print(f"  SMA({args.ma_period})  |  Decline: {args.rapid_decline_pct}%/{args.rapid_decline_bars}bars  |  ATR spike: {args.atr_spike_mult}x")
    print(f"  Re-entry: {args.reentry_mode}  |  Interval: {args.interval}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        ma_period=args.ma_period, rapid_decline_pct=args.rapid_decline_pct,
        rapid_decline_bars=args.rapid_decline_bars, atr_period=args.atr_period,
        atr_spike_mult=args.atr_spike_mult, atr_ma_period=args.atr_ma_period,
        reentry_mode=args.reentry_mode, pivot_lookback=args.pivot_lookback,
    )

    print(f"  Period:           {result['date_from']} -> {result['date_to']} ({result['candles_analyzed']} bars)")
    print(f"  Initial Capital:  ${result['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${result['final_capital']:,.2f}")
    print(f"  Total Return:     {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:     {result['total_trades']}")
    print(f"  Win Rate:         {result['win_rate_pct']}%")
    print(f"  Profit Factor:    {result['profit_factor']}")
    print(f"  Sharpe Ratio:     {result['sharpe_ratio']}")
    print(f"  Max Drawdown:     {result['max_drawdown_pct']}%")
    print(f"  Exits:            Decline: {result['rapid_decline_exits']}  |  MA Break: {result['ma_breakdown_exits']}  |  Vol Spike: {result['volatility_spike_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        print(f"    LONG  {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    fname = f"buy_and_protect_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
