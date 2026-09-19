"""
RSI Volume Watch Strategy
==========================
Combines RSI momentum with volume confirmation for high-conviction entries.

Bullish signal:
  - RSI(14) crosses ABOVE 50 (momentum shifting bullish)
  - Volume is INCREASING (current bar volume > 20-bar volume SMA * 1.3)
  - Confirms real buying pressure, not just a weak drift above 50

Bearish signal:
  - RSI(14) crosses BELOW 50 (momentum shifting bearish)
  - Volume is INCREASING (selling pressure confirmed)

Exit conditions:
  - Long exit: RSI drops below 40 (momentum fading) OR ATR trailing stop
  - Short exit: RSI rises above 60 OR ATR trailing stop
  - Max hold: 40 bars

The key insight: RSI crossing 50 alone is noisy. Adding volume confirmation
filters out weak crossings and keeps only the ones backed by real money flow.

Usage:
    python3 strategies/rsi_volume_watch/rsi_volume_watch_strategy.py --symbol SPY --period 2y --chart
    python3 strategies/rsi_volume_watch/rsi_volume_watch_strategy.py --symbol AMD --period 2y --long-only
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Parameters ───────────────────────────────────────────────────────

RSI_PERIOD       = 14
RSI_BULL_CROSS   = 50    # RSI crosses above this = bullish
RSI_BEAR_CROSS   = 50    # RSI crosses below this = bearish
RSI_BULL_EXIT    = 40    # Exit long when RSI drops below this
RSI_BEAR_EXIT    = 60    # Exit short when RSI rises above this

VOL_MA_PERIOD    = 20    # Volume moving average period
VOL_MULT         = 1.3   # Volume must be >= 1.3x its MA

ATR_PERIOD       = 14
ATR_TRAIL_MULT   = 3.0   # Trailing stop = 3x ATR from peak/trough
MAX_HOLD_BARS    = 40    # Max bars in a trade

COOLDOWN         = 5     # Bars between trades
COMMISSION       = 0.001
SLIPPAGE         = 0.001
INITIAL_CAPITAL  = 10_000.0
PERIOD   = "2y"
INTERVAL = "1d"


# ── Indicators ──────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "rsi-vol-watch/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval in ("1h", "30m") else "%Y-%m-%d"
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
                         "open": round(o, 4), "high": round(h, 4),
                         "low": round(l, 4), "close": round(c, 4), "volume": v or 0})
    return candles


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    k = 2.0 / (period + 1)
    for i in range(len(values)):
        if i == 0:
            out[i] = values[i]
        elif i < period - 1:
            out[i] = values[i] * k + out[i - 1] * (1 - k)
        elif i == period - 1:
            out[i] = sum(values[:period]) / period
        else:
            out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out


def calc_rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period + 1:
        return out
    gains = [max(values[i] - values[i-1], 0) for i in range(1, period + 1)]
    losses = [max(values[i-1] - values[i], 0) for i in range(1, period + 1)]
    ag, al = sum(gains) / period, sum(losses) / period
    out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def calc_atr(candles: list[dict], period: int = 14) -> list[float | None]:
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["high"] - c["low"])
        else:
            prev = candles[i - 1]["close"]
            trs.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))
    return ema(trs, period)


# ── Strategy Engine ─────────────────────────────────────────────────

def run_rsi_volume_watch(candles: list[dict], params: dict | None = None) -> dict:
    p = params or {}
    rsi_period     = p.get("rsi_period", RSI_PERIOD)
    rsi_bull       = p.get("rsi_bull_cross", RSI_BULL_CROSS)
    rsi_bear       = p.get("rsi_bear_cross", RSI_BEAR_CROSS)
    rsi_bull_exit  = p.get("rsi_bull_exit", RSI_BULL_EXIT)
    rsi_bear_exit  = p.get("rsi_bear_exit", RSI_BEAR_EXIT)
    vol_ma_period  = p.get("vol_ma_period", VOL_MA_PERIOD)
    vol_mult       = p.get("vol_mult", VOL_MULT)
    atr_period     = p.get("atr_period", ATR_PERIOD)
    atr_trail      = p.get("atr_trail_mult", ATR_TRAIL_MULT)
    max_hold       = p.get("max_hold_bars", MAX_HOLD_BARS)
    cooldown       = p.get("cooldown", COOLDOWN)
    long_only      = p.get("long_only", False)
    disable_exit   = p.get("disable_exit", False)
    commission     = p.get("commission", COMMISSION)
    slippage       = p.get("slippage", SLIPPAGE)
    initial_cap    = p.get("initial_capital", INITIAL_CAPITAL)

    n = len(candles)
    closes = [c["close"] for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    cost_pct = (commission + slippage) * 100

    # Compute indicators
    rsi_vals = calc_rsi(closes, rsi_period)
    vol_sma = sma(volumes, vol_ma_period)
    atr_vals = calc_atr(candles, atr_period)

    # State
    in_position = False
    side = ""
    entry_price = 0.0
    entry_date = ""
    entry_bar = 0
    peak_price = 0.0
    trough_price = float("inf")
    entry_signal = ""
    bars_since_exit = cooldown

    trades: list[dict] = []
    capital = initial_cap
    signal_counts: dict[str, int] = {}

    warmup = max(rsi_period, vol_ma_period, atr_period) + 2

    for i in range(warmup, n):
        close = closes[i]
        date = candles[i]["date"]
        rsi = rsi_vals[i]
        prev_rsi = rsi_vals[i - 1]
        vol = volumes[i]
        vol_avg = vol_sma[i]
        atr = atr_vals[i]

        if rsi is None or prev_rsi is None or vol_avg is None or atr is None:
            continue
        if atr == 0:
            continue

        vol_confirmed = vol >= vol_avg * vol_mult

        # ── Exit check ──────────────────────────────────────────
        if in_position:
            if close > peak_price:
                peak_price = close
            if close < trough_price:
                trough_price = close

            days_held = i - entry_bar
            exit_reason = ""

            if disable_exit:
                if i == n - 1:
                    exit_reason = "end_of_data"
            else:
                if side == "long":
                    # RSI fading
                    if rsi < rsi_bull_exit:
                        exit_reason = "rsi_momentum_fade"
                    # ATR trailing stop
                    elif close < peak_price - atr_trail * atr:
                        exit_reason = "atr_trailing_stop"
                    elif days_held >= max_hold:
                        exit_reason = "max_hold"
                    elif i == n - 1:
                        exit_reason = "end_of_data"
                else:  # short
                    if rsi > rsi_bear_exit:
                        exit_reason = "rsi_momentum_fade"
                    elif close > trough_price + atr_trail * atr:
                        exit_reason = "atr_trailing_stop"
                    elif days_held >= max_hold:
                        exit_reason = "max_hold"
                    elif i == n - 1:
                        exit_reason = "end_of_data"

            if exit_reason:
                if side == "long":
                    gross_ret = (close - entry_price) / entry_price * 100
                else:
                    gross_ret = (entry_price - close) / entry_price * 100
                net_ret = gross_ret - cost_pct * 2
                capital *= (1 + net_ret / 100)

                trades.append({
                    "entry_date": entry_date, "entry_price": round(entry_price, 4),
                    "exit_date": date, "exit_price": round(close, 4),
                    "side": side, "entry_reason": entry_signal,
                    "return_pct": round(net_ret, 2),
                    "gross_return_pct": round(gross_ret, 2),
                    "exit_reason": exit_reason,
                    "days_held": days_held,
                    "rsi_at_entry": round(rsi_vals[entry_bar], 1) if rsi_vals[entry_bar] else 0,
                    "rsi_at_exit": round(rsi, 1),
                    "vol_ratio_at_entry": round(volumes[entry_bar] / (vol_sma[entry_bar] or 1), 1),
                    "strategy": "rsi_volume_watch",
                })
                in_position = False
                bars_since_exit = 0
                continue

        # ── Entry signals ───────────────────────────────────────
        if in_position:
            continue

        bars_since_exit += 1
        if bars_since_exit < cooldown:
            continue

        signal = ""
        sig_side = ""

        # Bullish: RSI crosses above 50 on rising volume
        if prev_rsi <= rsi_bull and rsi > rsi_bull and vol_confirmed:
            signal = "rsi_vol_bullish"
            sig_side = "long"

        # Bearish: RSI crosses below 50 on rising volume
        if not signal and not long_only:
            if prev_rsi >= rsi_bear and rsi < rsi_bear and vol_confirmed:
                signal = "rsi_vol_bearish"
                sig_side = "short"

        if signal and sig_side:
            entry_price = close
            entry_date = date
            entry_bar = i
            side = sig_side
            entry_signal = signal
            in_position = True
            peak_price = close
            trough_price = close
            signal_counts[signal] = signal_counts.get(signal, 0) + 1

    # ── Metrics ─────────────────────────────────────────────────────
    bh_ret = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100
    total_ret = (capital - initial_cap) / initial_cap * 100

    winning = [t for t in trades if t["return_pct"] > 0]
    losing = [t for t in trades if t["return_pct"] <= 0]
    win_rate = round(len(winning) / len(trades) * 100, 1) if trades else 0.0
    avg_gain = round(statistics.mean([t["return_pct"] for t in winning]), 2) if winning else 0.0
    avg_loss = round(statistics.mean([t["return_pct"] for t in losing]), 2) if losing else 0.0
    gw = sum(t["return_pct"] for t in winning)
    gl = abs(sum(t["return_pct"] for t in losing))
    profit_factor = round(gw / gl, 2) if gl > 0 else float("inf")

    equity, peak_eq, max_dd = initial_cap, initial_cap, 0.0
    for t in trades:
        equity *= (1 + t["return_pct"] / 100)
        if equity > peak_eq:
            peak_eq = equity
        dd = (equity - peak_eq) / peak_eq * 100
        if dd < max_dd:
            max_dd = dd

    if len(trades) >= 2:
        rets = [t["return_pct"] for t in trades]
        std_r = statistics.stdev(rets)
        sharpe = round(statistics.mean(rets) / std_r * math.sqrt(252 / max(1, max_hold)), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    bars_in = sum(t.get("days_held", 0) for t in trades)
    time_in = round(bars_in / n * 100, 1) if n > 0 else 0.0

    # Build overlays
    rsi_overlay = [{"time": candles[j]["date"], "value": round(rsi_vals[j], 2)}
                   for j in range(n) if rsi_vals[j] is not None]

    result = {
        "symbol": p.get("symbol", ""),
        "strategy": "rsi_volume_watch",
        "strategy_label": (
            f"RSI Volume Watch (RSI cross {rsi_bull}, vol>{vol_mult}x, "
            f"ATR trail {atr_trail}x)"
        ),
        "period": p.get("period", PERIOD),
        "interval": p.get("interval", INTERVAL),
        "candles_analyzed": n,
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "initial_capital": initial_cap,
        "final_capital": round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "buy_and_hold_return_pct": round(bh_ret, 2),
        "vs_buy_and_hold_pct": round(total_ret - bh_ret, 2),
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate_pct": win_rate,
        "avg_gain_pct": avg_gain,
        "avg_loss_pct": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": round(max_dd, 2),
        "time_in_market_pct": time_in,
        "signal_counts": signal_counts,
        "trade_log": trades,
        "overlays": [
            {"label": "RSI(14)", "color": "#E040FB", "type": "rsi_panel", "points": rsi_overlay},
        ],
        "data_source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RSI Volume Watch Strategy")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--period", default=PERIOD)
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"])
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--disable-exit", action="store_true")
    parser.add_argument("--vol-mult", type=float, default=VOL_MULT)
    parser.add_argument("--atr-trail", type=float, default=ATR_TRAIL_MULT)
    parser.add_argument("--chart", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  RSI Volume Watch — {args.symbol} ({args.interval})")
    print(f"  RSI cross 50 + volume>{args.vol_mult}x  ATR trail={args.atr_trail}x")
    print(f"  Mode: {'Long only' if args.long_only else 'Long + Short'}")
    print(f"{'='*60}")

    candles = fetch_ohlcv(args.symbol, args.period, args.interval)
    print(f"\n  Fetched {len(candles)} candles ({candles[0]['date']} -> {candles[-1]['date']})\n")

    params = {
        "symbol": args.symbol, "period": args.period, "interval": args.interval,
        "initial_capital": args.initial_capital, "long_only": args.long_only,
        "disable_exit": args.disable_exit,
        "vol_mult": args.vol_mult, "atr_trail_mult": args.atr_trail,
    }
    result = run_rsi_volume_watch(candles, params)

    print(f"  Period:          {result['date_from']} -> {result['date_to']}")
    print(f"  Total Return:    {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:      {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:          {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:    {result['total_trades']}")
    print(f"  Win Rate:        {result['win_rate_pct']}%")
    print(f"  Avg Gain:        {result['avg_gain_pct']:+.2f}%")
    print(f"  Avg Loss:        {result['avg_loss_pct']:+.2f}%")
    print(f"  Profit Factor:   {result['profit_factor']}")
    print(f"  Sharpe:          {result['sharpe_ratio']}")
    print(f"  Max Drawdown:    {result['max_drawdown_pct']}%")
    print(f"  Time in Market:  {result['time_in_market_pct']}%")
    print(f"  Signals:         {result['signal_counts']}")

    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        print(f"    {t['side'].upper():5s} [{t['entry_reason']:18s}] "
              f"{t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>9,.2f} -> ${t['exit_price']:>9,.2f}  "
              f"{t['return_pct']:+7.2f}%  RSI {t['rsi_at_entry']:>4.0f}->{t['rsi_at_exit']:>4.0f}  "
              f"vol={t['vol_ratio_at_entry']}x  [{t['exit_reason']}]  {t['days_held']}d")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    json_out = {k: v for k, v in result.items() if k != "overlays"}
    fname = script_dir / f"rsi_vol_backtest_{safe_sym}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html
        chart_path = script_dir / f"rsi_vol_chart_{safe_sym}_{args.period}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
