"""
Volatility Harvester Strategy — Standalone Python Implementation
================================================================

Mean-reversion strategy optimized for choppy, range-bound markets.

Core idea: in low-trending (choppy) regimes, price tends to revert toward
its mean. When price deviates significantly from SMA AND volume spikes
(confirming participation), fade the move and hold until price returns
to the mean.

Regime detection:
  - Kaufman Efficiency Ratio (ER) over 50 bars measures trend efficiency
  - ER near 1.0 = strongly trending  →  stay flat, don't trade
  - ER near 0.0 = choppy/range-bound →  mean-reversion entries active

Entry logic (only when ER < threshold):
  - Deviation exceeds deviation_mult * ATR(14) from SMA(20)
  - Volume spike: current volume >= vol_spike_mult * vol_ma(20)     [optional]
  - Close < SMA  →  Long (price below mean, expect bounce)
  - Close > SMA  →  Short (price above mean, expect reversion)      [if not long_only]

Triple-layer exit (checked before entries each bar):
  1. Mean reversion: close >= SMA (long) or close <= SMA (short)
  2. Time exit:      bars held >= max_hold_bars (stale trade)
  3. Stop loss:      ATR-based, frozen at entry — 2x ATR from entry price

Usage:
  python volatility_harvester_strategy.py                               # defaults: SPY, 2y, 1h
  python volatility_harvester_strategy.py --symbol BTC-USD --period 1y
  python volatility_harvester_strategy.py --interval 1d --long-only
  python volatility_harvester_strategy.py --er-threshold 0.3 --deviation-mult 2.5

Requires: no external dependencies (pure stdlib + Yahoo Finance API)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import math
import statistics
import urllib.request
from datetime import datetime, timezone
from typing import Optional


# ==============================================================================
# STRATEGY PARAMETERS
# ==============================================================================

ATR_PERIOD       = 14      # ATR period for deviation threshold and stop loss
SMA_PERIOD       = 20      # SMA period for mean calculation
DEVIATION_MULT   = 3.0     # entry when |close - sma| > deviation_mult * atr
STOP_MULT        = 2.0     # stop loss = entry ± stop_mult * entry_atr (frozen)
MAX_HOLD_BARS    = 15      # time-based exit after this many bars
VOL_MA_PERIOD    = 20      # volume moving average period for spike detection
VOL_SPIKE_MULT   = 1.5     # volume must be >= vol_spike_mult * vol_ma to enter
ER_PERIOD        = 50      # Efficiency Ratio lookback (choppy vs trending regime)
ER_THRESHOLD     = 0.25    # ER below this = choppy regime (entries allowed)
VOLUME_FILTER    = True    # require volume spike to enter
LONG_ONLY        = False   # if True, disable short entries
INTERVAL         = "1h"    # candle size
PERIOD           = "2y"    # data lookback
INITIAL_CAPITAL  = 10_000.0
COMMISSION_PCT   = 0.1
SLIPPAGE_PCT     = 0.05


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1h") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "volatility-harvester/1.0"})
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
            "date":   datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
            "open":   round(o, 4),
            "high":   round(h, 4),
            "low":    round(l, 4),
            "close":  round(c, 4),
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
    """Average True Range using Wilder's smoothing."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period + 1:
        return result
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[:period]) / period
    result[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + trs[i - 1]) / period
        result[i] = atr
    return result


def calc_er(closes: list[float], period: int) -> list[Optional[float]]:
    """
    Kaufman Efficiency Ratio.

    ER = |net change over period| / sum(|bar-to-bar changes| over period)

    Near 1.0 = strongly trending (straight line movement).
    Near 0.0 = choppy/oscillating (lots of back-and-forth).
    """
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    for i in range(period, n):
        net_change = abs(closes[i] - closes[i - period])
        path_length = sum(abs(closes[j] - closes[j - 1]) for j in range(i - period + 1, i + 1))
        if path_length > 0:
            result[i] = net_change / path_length
        else:
            result[i] = 0.0
    return result


def calc_volume_ma(volumes: list[float], period: int) -> list[Optional[float]]:
    """Volume moving average — delegates to calc_sma."""
    return calc_sma(volumes, period)


# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_volatility_harvester(
    candles: list[dict],
    atr_period: int = ATR_PERIOD,
    sma_period: int = SMA_PERIOD,
    deviation_mult: float = DEVIATION_MULT,
    stop_mult: float = STOP_MULT,
    max_hold_bars: int = MAX_HOLD_BARS,
    vol_ma_period: int = VOL_MA_PERIOD,
    vol_spike_mult: float = VOL_SPIKE_MULT,
    er_period: int = ER_PERIOD,
    er_threshold: float = ER_THRESHOLD,
    volume_filter: bool = VOLUME_FILTER,
    long_only: bool = LONG_ONLY,
) -> list[dict]:
    """
    Volatility Harvester — mean-reversion engine.

    Single pass through candles:
      - Exits are checked BEFORE entries on each bar.
      - Entries only allowed when ER < er_threshold (choppy regime).
      - Stop loss ATR is frozen at entry time.

    Returns list of trade dicts.
    """
    if not candles:
        return []

    closes  = [c["close"]  for c in candles]
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    volumes = [float(c["volume"]) for c in candles]

    # --- Compute indicators upfront ---
    sma    = calc_sma(closes, sma_period)
    atr    = calc_atr(highs, lows, closes, atr_period)
    er     = calc_er(closes, er_period)
    vol_ma = calc_volume_ma(volumes, vol_ma_period)

    # --- State ---
    trades: list[dict] = []
    position: dict | None = None

    regime_active_bars = 0
    total_bars = len(candles)

    for i in range(len(candles)):
        date  = candles[i]["date"]
        close = closes[i]

        # Track regime active bars (choppy regime)
        if er[i] is not None and er[i] < er_threshold:
            regime_active_bars += 1

        # --- Exits (checked before entries) ---
        if position is not None:
            bars_held   = i - position["entry_bar"]
            entry_price = position["entry_price"]
            entry_atr   = position["entry_atr"]
            side        = position["side"]
            exit_reason = None

            # Exit 1: Mean reversion — price returned to SMA
            if sma[i] is not None:
                if side == "long"  and close >= sma[i]:
                    exit_reason = "mean_reversion"
                elif side == "short" and close <= sma[i]:
                    exit_reason = "mean_reversion"

            # Exit 2: Time exit — trade has been open too long
            if exit_reason is None and bars_held >= max_hold_bars:
                exit_reason = "time_exit"

            # Exit 3: Stop loss — ATR frozen at entry
            if exit_reason is None:
                if side == "long"  and close <= entry_price - stop_mult * entry_atr:
                    exit_reason = "stop_loss"
                elif side == "short" and close >= entry_price + stop_mult * entry_atr:
                    exit_reason = "stop_loss"

            if exit_reason:
                trades.append({
                    "entry_date":  position["entry_date"],
                    "entry_price": entry_price,
                    "exit_date":   date,
                    "exit_price":  close,
                    "side":        side,
                    "exit_reason": exit_reason,
                    "bars_held":   bars_held,
                })
                position = None

        # --- Entries (only when flat AND in choppy regime) ---
        if position is None:
            # Regime gate: ER must be below threshold
            if er[i] is None or er[i] >= er_threshold:
                continue

            # Indicators must be ready
            if sma[i] is None or atr[i] is None:
                continue

            deviation = abs(close - sma[i])
            threshold = deviation_mult * atr[i]

            if deviation <= threshold:
                continue  # Not deviated enough — skip

            # Volume spike check
            if volume_filter:
                if vol_ma[i] is None or volumes[i] < vol_spike_mult * vol_ma[i]:
                    continue

            # Determine side
            if close < sma[i]:
                side = "long"
            elif not long_only:
                side = "short"
            else:
                continue  # Would be short but long_only mode — skip

            position = {
                "entry_date":  date,
                "entry_price": close,
                "entry_bar":   i,
                "entry_atr":   atr[i],   # frozen ATR for stop loss
                "side":        side,
            }

    # Close any open position at end of data
    if position is not None:
        bars_held = (len(candles) - 1) - position["entry_bar"]
        trades.append({
            "entry_date":  position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date":   candles[-1]["date"],
            "exit_price":  candles[-1]["close"],
            "side":        position["side"],
            "exit_reason": "end_of_data",
            "bars_held":   bars_held,
        })

    # Attach regime metadata to all trades (for calc_metrics)
    for t in trades:
        t["_regime_active_bars"] = regime_active_bars
        t["_total_bars"] = total_bars

    return trades


# ==============================================================================
# COSTS & METRICS
# ==============================================================================

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply transaction costs to each trade, handling both long and short sides."""
    total_cost = (commission_pct + slippage_pct) * 2
    result = []
    for t in trades:
        entry = t["entry_price"]
        exit_ = t["exit_price"]
        side  = t.get("side", "long")

        if side == "short":
            gross = (entry - exit_) / entry * 100
        else:
            gross = (exit_ - entry) / entry * 100

        net = round(gross - total_cost, 3)
        result.append({
            **t,
            "return_pct":       net,
            "gross_return_pct": round(gross, 3),
            "cost_pct":         round(-total_cost, 3),
        })
    return result


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1h") -> dict:
    """Calculate backtest performance metrics."""
    if not trades:
        return {
            "total_trades":           0,
            "long_trades":            0,
            "short_trades":           0,
            "winning_trades":         0,
            "losing_trades":          0,
            "mean_reversion_exits":   0,
            "time_exits":             0,
            "stop_loss_exits":        0,
            "end_of_data_exits":      0,
            "regime_active_pct":      0.0,
            "win_rate_pct":           0.0,
            "total_return_pct":       0.0,
            "final_capital":          initial_capital,
            "max_drawdown_pct":       0.0,
            "avg_gain_pct":           0.0,
            "avg_loss_pct":           0.0,
            "profit_factor":          0.0,
            "sharpe_ratio":           0.0,
            "expectancy_pct":         0.0,
        }

    ann_map = {
        "5m":  252 * 78,
        "15m": 252 * 26,
        "30m": 252 * 13,
        "1h":  252 * 6,
        "1d":  252,
    }
    ann = ann_map.get(interval, 252)

    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]
    longs   = [t for t in trades if t.get("side", "long") == "long"]
    shorts  = [t for t in trades if t.get("side") == "short"]

    # Regime active percentage (from metadata on any trade)
    regime_active_bars = trades[0].get("_regime_active_bars", 0)
    total_bars         = trades[0].get("_total_bars", 1)
    regime_active_pct  = round(regime_active_bars / total_bars * 100, 1) if total_bars > 0 else 0.0

    # Equity curve + drawdown
    capital      = initial_capital
    peak_capital = capital
    max_dd       = 0.0
    returns      = []
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak_capital = max(peak_capital, capital)
        max_dd = max(max_dd, (peak_capital - capital) / peak_capital * 100)

    total_ret = (capital - initial_capital) / initial_capital * 100
    avg_gain  = sum(t["return_pct"] for t in winners) / len(winners) if winners else 0.0
    avg_loss  = sum(t["return_pct"] for t in losers)  / len(losers)  if losers  else 0.0
    gp        = sum(t["return_pct"] for t in winners)
    gl        = abs(sum(t["return_pct"] for t in losers))
    pf        = round(gp / gl, 2) if gl > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r  = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / ann) / std_r * math.sqrt(ann), 2)

    wr = len(winners) / len(trades) if trades else 0.0

    return {
        "total_trades":           len(trades),
        "long_trades":            len(longs),
        "short_trades":           len(shorts),
        "winning_trades":         len(winners),
        "losing_trades":          len(losers),
        "mean_reversion_exits":   sum(1 for t in trades if t.get("exit_reason") == "mean_reversion"),
        "time_exits":             sum(1 for t in trades if t.get("exit_reason") == "time_exit"),
        "stop_loss_exits":        sum(1 for t in trades if t.get("exit_reason") == "stop_loss"),
        "end_of_data_exits":      sum(1 for t in trades if t.get("exit_reason") == "end_of_data"),
        "regime_active_pct":      regime_active_pct,
        "win_rate_pct":           round(wr * 100, 1),
        "total_return_pct":       round(total_ret, 2),
        "final_capital":          round(capital, 2),
        "max_drawdown_pct":       round(-max_dd, 2),
        "avg_gain_pct":           round(avg_gain, 2),
        "avg_loss_pct":           round(avg_loss, 2),
        "profit_factor":          pf,
        "sharpe_ratio":           sharpe,
        "expectancy_pct":         round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }


# ==============================================================================
# BACKTEST PIPELINE
# ==============================================================================

def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    **strategy_params,
) -> dict:
    """
    Full backtest pipeline: fetch data → run engine → apply costs → compute metrics.

    Returns a comprehensive result dict with metrics, trade log, and metadata.
    """
    candles = fetch_ohlcv(symbol, period, interval)

    raw_trades = run_volatility_harvester(candles, **strategy_params)
    trades     = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics    = calc_metrics(trades, initial_capital, interval)

    bnh = round(
        (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2
    )

    # Resolve effective strategy params (defaults filled in)
    eff = {
        "atr_period":     strategy_params.get("atr_period",     ATR_PERIOD),
        "sma_period":     strategy_params.get("sma_period",     SMA_PERIOD),
        "deviation_mult": strategy_params.get("deviation_mult", DEVIATION_MULT),
        "stop_mult":      strategy_params.get("stop_mult",      STOP_MULT),
        "max_hold_bars":  strategy_params.get("max_hold_bars",  MAX_HOLD_BARS),
        "vol_ma_period":  strategy_params.get("vol_ma_period",  VOL_MA_PERIOD),
        "vol_spike_mult": strategy_params.get("vol_spike_mult", VOL_SPIKE_MULT),
        "er_period":      strategy_params.get("er_period",      ER_PERIOD),
        "er_threshold":   strategy_params.get("er_threshold",   ER_THRESHOLD),
        "volume_filter":  strategy_params.get("volume_filter",  VOLUME_FILTER),
        "long_only":      strategy_params.get("long_only",      LONG_ONLY),
    }

    label = (
        f"Volatility Harvester "
        f"(SMA {eff['sma_period']}, ATR {eff['atr_period']}, "
        f"Dev {eff['deviation_mult']}x, ER<{eff['er_threshold']})"
    )

    return {
        "symbol":                  symbol.upper(),
        "strategy":                "volatility_harvester",
        "strategy_label":          label,
        "parameters":              eff,
        "period":                  period,
        "interval":                interval,
        "candles_analyzed":        len(candles),
        "date_from":               candles[0]["date"],
        "date_to":                 candles[-1]["date"],
        "initial_capital":         initial_capital,
        "commission_pct":          commission_pct,
        "slippage_pct":            slippage_pct,
        **metrics,
        "buy_and_hold_return_pct": bnh,
        "vs_buy_and_hold_pct":     round(metrics["total_return_pct"] - bnh, 2),
        "trade_log":               trades,
        "data_source":             "Yahoo Finance",
        "disclaimer":              "Past performance does not guarantee future results. For educational use only.",
        "timestamp":               datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Volatility Harvester Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["5m", "15m", "30m", "1h", "1d"],
                        help="Candle size (default: 1h)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--atr-period", type=int, default=ATR_PERIOD, help="ATR period (default: 14)")
    parser.add_argument("--sma-period", type=int, default=SMA_PERIOD, help="SMA period for mean (default: 20)")
    parser.add_argument("--deviation-mult", type=float, default=DEVIATION_MULT,
                        help="ATR multiples from SMA to trigger entry (default: 2.0)")
    parser.add_argument("--stop-mult", type=float, default=STOP_MULT,
                        help="ATR multiples for stop loss (default: 3.0)")
    parser.add_argument("--max-hold-bars", type=int, default=MAX_HOLD_BARS,
                        help="Max bars to hold a position (default: 20)")
    parser.add_argument("--vol-ma-period", type=int, default=VOL_MA_PERIOD,
                        help="Volume MA period (default: 20)")
    parser.add_argument("--vol-spike-mult", type=float, default=VOL_SPIKE_MULT,
                        help="Volume spike multiplier (default: 1.5)")
    parser.add_argument("--er-period", type=int, default=ER_PERIOD, help="ER lookback (default: 50)")
    parser.add_argument("--er-threshold", type=float, default=ER_THRESHOLD,
                        help="ER threshold: below = choppy (default: 0.25)")
    parser.add_argument("--no-volume-filter", action="store_true",
                        help="Disable volume confirmation for entries")
    parser.add_argument("--long-only", action="store_true",
                        help="Disable short positions")
    args = parser.parse_args()

    vol_filter = not args.no_volume_filter
    vol_label = "ON" if vol_filter else "OFF"
    shorts_label = "OFF" if args.long_only else "ON"

    print(f"\n{'='*60}")
    print(f"  Volatility Harvester — {args.symbol}")
    print(f"  Entry: {args.deviation_mult} ATR  |  Stop: {args.stop_mult} ATR  |  Hold: {args.max_hold_bars} bars")
    print(f"  ER < {args.er_threshold}  |  Volume: {vol_label}  |  Shorts: {shorts_label}")
    print(f"  Interval: {args.interval}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        atr_period=args.atr_period, sma_period=args.sma_period,
        deviation_mult=args.deviation_mult, stop_mult=args.stop_mult,
        max_hold_bars=args.max_hold_bars,
        vol_ma_period=args.vol_ma_period, vol_spike_mult=args.vol_spike_mult,
        er_period=args.er_period, er_threshold=args.er_threshold,
        volume_filter=vol_filter, long_only=args.long_only,
    )

    m = result
    print(f"  Period:           {m['date_from']} -> {m['date_to']} ({m['candles_analyzed']} bars)")
    print(f"  Regime Active:    {m['regime_active_pct']}% of bars (ER < {args.er_threshold})")
    print(f"  Initial Capital:  ${m['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${m['final_capital']:,.2f}")
    print(f"  Total Return:     {m['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {m['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {m['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:     {m['total_trades']} (L:{m['long_trades']} S:{m['short_trades']})")
    print(f"  Win Rate:         {m['win_rate_pct']}%")
    print(f"  Profit Factor:    {m['profit_factor']}")
    print(f"  Sharpe Ratio:     {m['sharpe_ratio']}")
    print(f"  Max Drawdown:     {m['max_drawdown_pct']}%")
    print(f"  Exits:            Reversion: {m['mean_reversion_exits']}  |  Time: {m['time_exits']}  |  Stop: {m['stop_loss_exits']}  |  EOD: {m['end_of_data_exits']}")

    print(f"\n  Trade Log:")
    for t in m["trade_log"]:
        side_label = "LONG " if t["side"] == "long" else "SHORT"
        print(f"    {side_label} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    fname = script_dir / f"volatility_harvester_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
