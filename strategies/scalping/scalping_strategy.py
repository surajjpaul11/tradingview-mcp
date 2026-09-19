"""
Daily Scalping Strategy for 1-Hour Charts
==========================================
Iterative development: starts with EMA 9/21 crossover, progressively
adds RSI+BB, MACD histogram, and Stochastic signals.

Iteration 2: Wider stops, cooldown, volume filter, confluence mode.
Tested on 1h charts, long + short.

Usage:
    python3 strategies/scalping/scalping_strategy.py --symbol SPY --period 60d
    python3 strategies/scalping/scalping_strategy.py --symbol BTC-USD --period 60d --long-only
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

# EMA crossover
EMA_FAST     = 9
EMA_SLOW     = 21
EMA_TREND    = 50    # Trend filter

# ATR-based exits
ATR_PERIOD   = 14
ATR_SL_MULT  = 1.5   # Stop loss = 1.5x ATR (widened from 1.0 in iter 2)
ATR_TP_MULT  = 2.5   # Take profit = 2.5x ATR (widened from 1.5 in iter 2)

# Trade management
COOLDOWN     = 5     # Minimum bars between trades
VOLUME_FILTER = True  # Require volume > 1.5x 20-bar average
VOLUME_MULT  = 1.5
VOLUME_MA    = 20
CONFLUENCE   = 1     # Minimum signals that must agree (1=any, 2=confluence)

# ADX trend strength filter
ADX_PERIOD   = 14
ADX_MIN      = 20    # Skip trades when ADX < 20 (no trend)

# RSI + Bollinger Band mean reversion (layer 2)
RSI_PERIOD   = 14
RSI_OB       = 70    # Overbought
RSI_OS       = 30    # Oversold
BB_PERIOD    = 20
BB_STD       = 2.0

# Stochastic (layer 3)
STOCH_K      = 14
STOCH_D      = 3
STOCH_SMOOTH = 3

# Mode flags
ENABLE_EMA_CROSS   = True
ENABLE_RSI_BB      = True
ENABLE_MACD_HIST   = True
ENABLE_STOCHASTIC  = True

COMMISSION  = 0.001
SLIPPAGE    = 0.001
INITIAL_CAPITAL = 10_000.0
PERIOD   = "60d"
INTERVAL = "1h"


# ── Indicators ──────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "60d", interval: str = "1h") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "scalping/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval in ("1h", "30m", "15m", "5m") else "%Y-%m-%d"
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


def calc_atr(candles: list[dict], period: int = 14) -> list[float | None]:
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["high"] - c["low"])
        else:
            prev = candles[i - 1]["close"]
            trs.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))
    return ema(trs, period)


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


def calc_adx(candles: list[dict], period: int = 14) -> list[float | None]:
    """Compute ADX (Average Directional Index)."""
    n = len(candles)
    out: list[float | None] = [None] * n
    if n < period * 2 + 1:
        return out

    plus_dm = []
    minus_dm = []
    tr_list = []
    for i in range(n):
        if i == 0:
            plus_dm.append(0.0)
            minus_dm.append(0.0)
            tr_list.append(candles[i]["high"] - candles[i]["low"])
        else:
            h, l = candles[i]["high"], candles[i]["low"]
            ph, pl = candles[i-1]["high"], candles[i-1]["low"]
            pc = candles[i-1]["close"]
            up = h - ph
            dn = pl - l
            plus_dm.append(up if up > dn and up > 0 else 0.0)
            minus_dm.append(dn if dn > up and dn > 0 else 0.0)
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))

    # Smoothed sums (Wilder's smoothing)
    atr_s = sum(tr_list[1:period + 1])
    pdm_s = sum(plus_dm[1:period + 1])
    mdm_s = sum(minus_dm[1:period + 1])

    dx_vals = []
    for i in range(period, n):
        if i == period:
            pass
        else:
            atr_s = atr_s - atr_s / period + tr_list[i]
            pdm_s = pdm_s - pdm_s / period + plus_dm[i]
            mdm_s = mdm_s - mdm_s / period + minus_dm[i]

        pdi = (pdm_s / atr_s * 100) if atr_s > 0 else 0
        mdi = (mdm_s / atr_s * 100) if atr_s > 0 else 0
        dx = abs(pdi - mdi) / (pdi + mdi) * 100 if (pdi + mdi) > 0 else 0
        dx_vals.append(dx)

        if len(dx_vals) == period:
            adx = sum(dx_vals) / period
            out[i] = adx
        elif len(dx_vals) > period:
            out[i] = (out[i - 1] * (period - 1) + dx) / period if out[i - 1] is not None else dx

    return out


def calc_bollinger(closes: list[float], period: int = 20, std_mult: float = 2.0):
    """Returns (upper, middle, lower) band lists."""
    n = len(closes)
    upper = [None] * n
    middle = [None] * n
    lower = [None] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1:i + 1]
        m = sum(window) / period
        std = (sum((x - m) ** 2 for x in window) / period) ** 0.5
        middle[i] = m
        upper[i] = m + std_mult * std
        lower[i] = m - std_mult * std
    return upper, middle, lower


def calc_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram) lists."""
    ema_f = ema(closes, fast)
    ema_s = ema(closes, slow)
    n = len(closes)
    macd_line = [None] * n
    for i in range(n):
        if ema_f[i] is not None and ema_s[i] is not None:
            macd_line[i] = ema_f[i] - ema_s[i]

    # Signal line = EMA of MACD line
    macd_vals = [v if v is not None else 0.0 for v in macd_line]
    sig = ema(macd_vals, signal)
    signal_line = [None] * n
    histogram = [None] * n
    for i in range(n):
        if macd_line[i] is not None and i >= slow - 1 + signal - 1:
            signal_line[i] = sig[i]
            histogram[i] = macd_line[i] - sig[i]
    return macd_line, signal_line, histogram


def calc_stochastic(candles: list[dict], k_period: int = 14, d_period: int = 3,
                    smooth: int = 3) -> tuple[list[float | None], list[float | None]]:
    """Returns (%K smoothed, %D) lists."""
    n = len(candles)
    raw_k: list[float | None] = [None] * n
    for i in range(k_period - 1, n):
        window_h = [candles[j]["high"] for j in range(i - k_period + 1, i + 1)]
        window_l = [candles[j]["low"] for j in range(i - k_period + 1, i + 1)]
        hh, ll = max(window_h), min(window_l)
        if hh != ll:
            raw_k[i] = (candles[i]["close"] - ll) / (hh - ll) * 100
        else:
            raw_k[i] = 50.0

    # Smooth %K with SMA
    smooth_k: list[float | None] = [None] * n
    for i in range(n):
        if i >= k_period - 1 + smooth - 1:
            vals = [raw_k[j] for j in range(i - smooth + 1, i + 1) if raw_k[j] is not None]
            if len(vals) == smooth:
                smooth_k[i] = sum(vals) / smooth

    # %D = SMA of smooth %K
    pct_d: list[float | None] = [None] * n
    for i in range(n):
        if i >= k_period - 1 + smooth - 1 + d_period - 1:
            vals = [smooth_k[j] for j in range(i - d_period + 1, i + 1) if smooth_k[j] is not None]
            if len(vals) == d_period:
                pct_d[i] = sum(vals) / d_period

    return smooth_k, pct_d


# ── Strategy Engine ─────────────────────────────────────────────────

def run_scalping(candles: list[dict], params: dict | None = None) -> dict:
    p = params or {}
    ema_fast_p    = p.get("ema_fast", EMA_FAST)
    ema_slow_p    = p.get("ema_slow", EMA_SLOW)
    ema_trend_p   = p.get("ema_trend", EMA_TREND)
    atr_period    = p.get("atr_period", ATR_PERIOD)
    atr_sl        = p.get("atr_sl_mult", ATR_SL_MULT)
    atr_tp        = p.get("atr_tp_mult", ATR_TP_MULT)
    adx_min       = p.get("adx_min", ADX_MIN)
    long_only     = p.get("long_only", False)
    cooldown      = p.get("cooldown", COOLDOWN)
    vol_filter    = p.get("volume_filter", VOLUME_FILTER)
    vol_mult      = p.get("volume_mult", VOLUME_MULT)
    vol_ma        = p.get("volume_ma", VOLUME_MA)
    confluence    = p.get("confluence", CONFLUENCE)
    enable_ema    = p.get("enable_ema_cross", ENABLE_EMA_CROSS)
    enable_rsi_bb = p.get("enable_rsi_bb", ENABLE_RSI_BB)
    enable_macd   = p.get("enable_macd_hist", ENABLE_MACD_HIST)
    enable_stoch  = p.get("enable_stochastic", ENABLE_STOCHASTIC)
    commission    = p.get("commission", COMMISSION)
    slippage      = p.get("slippage", SLIPPAGE)
    initial_cap   = p.get("initial_capital", INITIAL_CAPITAL)

    n = len(candles)
    closes = [c["close"] for c in candles]
    cost_pct = (commission + slippage) * 100

    # Compute indicators
    ema_f = ema(closes, ema_fast_p)
    ema_s = ema(closes, ema_slow_p)
    ema_t = ema(closes, ema_trend_p)
    atr_vals = calc_atr(candles, atr_period)
    adx_vals = calc_adx(candles, ADX_PERIOD)
    rsi_vals = calc_rsi(closes, RSI_PERIOD)
    bb_upper, bb_mid, bb_lower = calc_bollinger(closes, BB_PERIOD, BB_STD)
    macd_line, macd_sig, macd_hist = calc_macd(closes)
    stoch_k, stoch_d = calc_stochastic(candles, STOCH_K, STOCH_D, STOCH_SMOOTH)

    # Volume moving average for filter
    volumes = [c["volume"] for c in candles]
    vol_sma = sma([float(v) for v in volumes], vol_ma)

    # State
    in_position = False
    side = ""
    entry_price = 0.0
    entry_date = ""
    stop_loss = 0.0
    take_profit = 0.0
    entry_signal = ""
    bars_since_exit = cooldown  # Start ready

    trades: list[dict] = []
    capital = initial_cap
    signal_counts: dict[str, int] = {}

    warmup = max(ema_trend_p, BB_PERIOD, 26 + 9, STOCH_K + STOCH_SMOOTH + 3, ADX_PERIOD * 2) + 1

    for i in range(warmup, n):
        close = closes[i]
        date = candles[i]["date"]
        atr = atr_vals[i]

        if atr is None or atr == 0:
            continue

        # ── Exit check ──────────────────────────────────────────────
        if in_position:
            exit_reason = ""
            if side == "long":
                if close <= stop_loss:
                    exit_reason = "stop_loss"
                elif close >= take_profit:
                    exit_reason = "take_profit"
            else:  # short
                if close >= stop_loss:
                    exit_reason = "stop_loss"
                elif close <= take_profit:
                    exit_reason = "take_profit"

            if i == n - 1 and not exit_reason:
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
                    "side": side, "entry_reason": entry_signal, "signal": entry_signal,
                    "return_pct": round(net_ret, 2),
                    "gross_return_pct": round(gross_ret, 2),
                    "exit_reason": exit_reason,
                    "strategy": "scalping",
                })
                in_position = False
                bars_since_exit = 0
                continue

        # ── Entry signals ───────────────────────────────────────────
        if in_position:
            continue

        bars_since_exit += 1
        if bars_since_exit < cooldown:
            continue

        # Volume filter: skip if volume below threshold
        if vol_filter and vol_sma[i] is not None and volumes[i] < vol_mult * vol_sma[i]:
            continue

        adx = adx_vals[i]

        # Collect all signals that fire on this bar
        long_signals: list[str] = []
        short_signals: list[str] = []

        # Signal 1: EMA 9/21 crossover
        if enable_ema and ema_f[i] is not None and ema_s[i] is not None and ema_t[i] is not None:
            prev_f = ema_f[i - 1]
            prev_s = ema_s[i - 1]
            if prev_f is not None and prev_s is not None:
                if prev_f <= prev_s and ema_f[i] > ema_s[i] and close > ema_t[i]:
                    if adx is None or adx >= adx_min:
                        long_signals.append("ema_cross")
                if not long_only and prev_f >= prev_s and ema_f[i] < ema_s[i] and close < ema_t[i]:
                    if adx is None or adx >= adx_min:
                        short_signals.append("ema_cross")

        # Signal 2: RSI + Bollinger Band mean reversion
        if enable_rsi_bb:
            rsi = rsi_vals[i]
            if rsi is not None and bb_lower[i] is not None:
                if rsi < RSI_OS and close <= bb_lower[i]:
                    long_signals.append("rsi_bb")
                if not long_only and rsi > RSI_OB and close >= bb_upper[i]:
                    short_signals.append("rsi_bb")

        # Signal 3: MACD histogram reversal
        if enable_macd:
            h0 = macd_hist[i]
            h1 = macd_hist[i - 1] if i > 0 else None
            h2 = macd_hist[i - 2] if i > 1 else None
            if h0 is not None and h1 is not None and h2 is not None and ema_t[i] is not None:
                if h2 < 0 and h1 < h2 and h0 > h1 and close > ema_t[i]:
                    long_signals.append("macd_hist")
                if not long_only and h2 > 0 and h1 > h2 and h0 < h1 and close < ema_t[i]:
                    short_signals.append("macd_hist")

        # Signal 4: Stochastic crossover from extremes
        if enable_stoch:
            sk, sd = stoch_k[i], stoch_d[i]
            prev_sk = stoch_k[i - 1] if i > 0 else None
            prev_sd = stoch_d[i - 1] if i > 0 else None
            if sk is not None and sd is not None and prev_sk is not None and prev_sd is not None:
                if ema_t[i] is not None:
                    if prev_sk <= prev_sd and sk > sd and sk < 20 and close > ema_t[i]:
                        long_signals.append("stochastic")
                    if not long_only and prev_sk >= prev_sd and sk < sd and sk > 80 and close < ema_t[i]:
                        short_signals.append("stochastic")

        # Check confluence and enter
        signal = ""
        sig_side = ""
        if len(long_signals) >= confluence:
            signal = "+".join(long_signals)
            sig_side = "long"
        elif len(short_signals) >= confluence:
            signal = "+".join(short_signals)
            sig_side = "short"

        if signal and sig_side:
            entry_price = close
            entry_date = date
            side = sig_side
            entry_signal = signal
            in_position = True
            signal_counts[signal] = signal_counts.get(signal, 0) + 1

            if side == "long":
                stop_loss = close - atr_sl * atr
                take_profit = close + atr_tp * atr
            else:
                stop_loss = close + atr_sl * atr
                take_profit = close - atr_tp * atr

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
        tpy = 252 * 6.5 / max(1, n / len(trades))  # ~6.5 trading hours/day
        sharpe = round(statistics.mean(rets) / std_r * math.sqrt(tpy), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # Count time in market
    bars_in = 0
    for t in trades:
        ei = next((j for j, c in enumerate(candles) if c["date"] == t["entry_date"]), 0)
        xi = next((j for j, c in enumerate(candles) if c["date"] == t["exit_date"]), 0)
        bars_in += xi - ei
    time_in = round(bars_in / n * 100, 1) if n > 0 else 0.0

    # Build overlays for chart
    ema_f_overlay = [{"time": candles[j]["date"], "value": round(ema_f[j], 4)}
                     for j in range(n) if ema_f[j] is not None]
    ema_s_overlay = [{"time": candles[j]["date"], "value": round(ema_s[j], 4)}
                     for j in range(n) if ema_s[j] is not None]
    ema_t_overlay = [{"time": candles[j]["date"], "value": round(ema_t[j], 4)}
                     for j in range(n) if ema_t[j] is not None]
    bb_u_overlay = [{"time": candles[j]["date"], "value": round(bb_upper[j], 4)}
                    for j in range(n) if bb_upper[j] is not None]
    bb_l_overlay = [{"time": candles[j]["date"], "value": round(bb_lower[j], 4)}
                    for j in range(n) if bb_lower[j] is not None]

    # RSI overlay
    rsi_overlay = [{"time": candles[j]["date"], "value": round(rsi_vals[j], 2)}
                   for j in range(n) if rsi_vals[j] is not None]

    enabled = []
    if enable_ema: enabled.append("EMA")
    if enable_rsi_bb: enabled.append("RSI+BB")
    if enable_macd: enabled.append("MACD")
    if enable_stoch: enabled.append("Stoch")

    result = {
        "symbol": p.get("symbol", ""),
        "strategy": "scalping",
        "strategy_label": f"Scalping ({'+'.join(enabled)}) EMA {ema_fast_p}/{ema_slow_p}/{ema_trend_p}",
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
            {"label": f"EMA({ema_fast_p})", "color": "#00BCD4", "type": "line", "points": ema_f_overlay},
            {"label": f"EMA({ema_slow_p})", "color": "#FFC107", "type": "line", "points": ema_s_overlay},
            {"label": f"EMA({ema_trend_p})", "color": "#FF5722", "type": "line", "points": ema_t_overlay},
            {"label": f"BB Upper({BB_PERIOD})", "color": "rgba(156,39,176,0.4)", "type": "line", "points": bb_u_overlay},
            {"label": f"BB Lower({BB_PERIOD})", "color": "rgba(156,39,176,0.4)", "type": "line", "points": bb_l_overlay},
            {"label": "RSI(14)", "color": "#E040FB", "type": "rsi_panel", "points": rsi_overlay},
        ],
        "data_source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Daily Scalping Strategy — 1h charts")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--period", default=PERIOD)
    parser.add_argument("--interval", default=INTERVAL, choices=["5m", "15m", "30m", "1h"])
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--no-ema", action="store_true", help="Disable EMA cross signal")
    parser.add_argument("--no-rsi-bb", action="store_true", help="Disable RSI+BB signal")
    parser.add_argument("--no-macd", action="store_true", help="Disable MACD histogram signal")
    parser.add_argument("--no-stoch", action="store_true", help="Disable Stochastic signal")
    parser.add_argument("--ema-only", action="store_true", help="Only EMA cross signal")
    parser.add_argument("--cooldown", type=int, default=COOLDOWN, help="Min bars between trades")
    parser.add_argument("--no-vol-filter", action="store_true", help="Disable volume filter")
    parser.add_argument("--confluence", type=int, default=CONFLUENCE, help="Min signals to agree (1=any, 2=confluence)")
    parser.add_argument("--atr-sl", type=float, default=ATR_SL_MULT, help="ATR stop loss multiplier")
    parser.add_argument("--atr-tp", type=float, default=ATR_TP_MULT, help="ATR take profit multiplier")
    parser.add_argument("--chart", action="store_true")
    args = parser.parse_args()

    enable_ema = not args.no_ema
    enable_rsi_bb = not args.no_rsi_bb
    enable_macd = not args.no_macd
    enable_stoch = not args.no_stoch

    if args.ema_only:
        enable_rsi_bb = False
        enable_macd = False
        enable_stoch = False

    enabled = []
    if enable_ema: enabled.append("EMA")
    if enable_rsi_bb: enabled.append("RSI+BB")
    if enable_macd: enabled.append("MACD")
    if enable_stoch: enabled.append("Stoch")

    print(f"\n{'='*60}")
    print(f"  Daily Scalping — {args.symbol} ({args.interval})")
    print(f"  Signals: {', '.join(enabled)}  Confluence: {args.confluence}")
    print(f"  SL: {args.atr_sl}x ATR  TP: {args.atr_tp}x ATR  Cooldown: {args.cooldown}")
    print(f"  Volume filter: {'ON' if not args.no_vol_filter else 'OFF'}  Mode: {'Long only' if args.long_only else 'Long + Short'}")
    print(f"{'='*60}")

    candles = fetch_ohlcv(args.symbol, args.period, args.interval)
    print(f"\n  Fetched {len(candles)} candles ({candles[0]['date']} -> {candles[-1]['date']})\n")

    params = {
        "symbol": args.symbol, "period": args.period, "interval": args.interval,
        "initial_capital": args.initial_capital, "long_only": args.long_only,
        "cooldown": args.cooldown, "volume_filter": not args.no_vol_filter,
        "confluence": args.confluence,
        "atr_sl_mult": args.atr_sl, "atr_tp_mult": args.atr_tp,
        "enable_ema_cross": enable_ema, "enable_rsi_bb": enable_rsi_bb,
        "enable_macd_hist": enable_macd, "enable_stochastic": enable_stoch,
    }
    result = run_scalping(candles, params)

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
    print(f"  Signals used:    {result['signal_counts']}")

    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        print(f"    {t['side'].upper():5s} [{t['signal']:12s}] "
              f"{t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>9,.2f} -> ${t['exit_price']:>9,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t['exit_reason']}]")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    json_out = {k: v for k, v in result.items() if k != "overlays"}
    fname = script_dir / f"scalping_backtest_{safe_sym}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html
        chart_path = script_dir / f"scalping_chart_{safe_sym}_{args.period}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
