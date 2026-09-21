"""
Enhanced Channel Strategy — Standalone Python Implementation
=============================================================

Multi-Timeframe (MTF) Channel Strategy combining:
  - Tactical Channel (3-Month / ~63 bars): Generates short-term tactical buy & sell signals.
  - Intermediate Channel (1-Year / ~252 bars): Trend filter & cyclical swing boundaries.
  - Macro Channel (5-Year / ~1260 bars): Secular regime & accumulation/distribution filter.

Strategy Rules:
  1. Channel Boundaries:
     - Built using rolling Linear Regression with Standard Error envelopes (Raff style).
     - Upper Channel = LinReg + (mult * StdError)
     - Lower Channel = LinReg - (mult * StdError)
     - Midline       = LinReg Centerline
  2. Leeway Zones (5% default):
     - Bottom Leeway Zone: [Lower Channel, Lower Channel + (5% * Channel Height)]
     - Top Leeway Zone:    [Upper Channel - (5% * Channel Height), Upper Channel]
  3. Tactical Buy Entry:
     - Price enters the Bottom Leeway Zone (within 5% of channel lower boundary).
     - Upward bounce is confirmed (bullish rebound candle: close > open and close > prev_close).
     - HTF Filter (optional): 1-Year slope is positive or price is in lower half of 1-Year channel.
  4. Tactical Sell Exit (Take Profit):
     - Price enters the Top Leeway Zone (within 5% of channel upper boundary).
     - Downward rejection is confirmed (bearish reversal candle: close < open or close < prev_close).
  5. Stopgap Risk Management:
     - If price breaks below the channel bottom by more than the leeway tolerance
       (close < Lower Channel - leeway), immediately close trade to protect capital.

Usage:
  python strategies/enhanced_channel/enhanced_channel_strategy.py --symbol SPY --period 5y --chart
  python strategies/enhanced_channel/enhanced_channel_strategy.py --symbol AAPL --period 2y --chart
  python strategies/enhanced_channel/enhanced_channel_strategy.py --symbol BTC-USD --period 2y

Requires: pure stdlib (no external packages required) + Yahoo Finance API
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
from typing import Optional, List, Dict, Any, Tuple


# ==============================================================================
# DEFAULT STRATEGY PARAMETERS
# ==============================================================================

TACTICAL_LOOKBACK    = 50     # ~2.5 months (50 bars) optimal swing channel
INTERMEDIATE_LOOKBACK = 200    # ~200 daily trading bars (institutional trendline)
MACRO_LOOKBACK       = 1000   # ~1000 daily trading bars (~4 years)
CHANNEL_MULT         = 1.7    # standard error multiplier for upper/lower bounds
LEEWAY_PCT           = 0.05   # 5% leeway band at channel edges
STOPGAP_PCT          = 0.05   # 5% buffer below lower line before stop loss fires
HTF_FILTER           = True   # use 1Y trend / regime filter
CONFLUENCE_BOOST     = True   # scale conviction when 3M and 1Y channels align
LONG_ONLY            = True   # long-only trades
INTERVAL             = "1d"   # daily candles recommended for multi-month/year channels
PERIOD               = "5y"   # lookback period for data fetch
INITIAL_CAPITAL      = 10_000.0
COMMISSION_PCT       = 0.1    # 0.1% per trade
SLIPPAGE_PCT         = 0.05   # 0.05% per trade


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "5y", interval: str = "1d") -> List[Dict[str, Any]]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "enhanced-channel-strategy/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval in ("1h", "30m", "15m", "5m") else "%Y-%m-%d"

    candles: List[Dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        o = q["open"][i]
        h = q["high"][i]
        l = q["low"][i]
        c = q["close"][i]
        v = q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(l, 4),
            "close": round(c, 4),
            "volume": v or 0,
        })
    return candles


# ==============================================================================
# LINEAR REGRESSION CHANNEL CALCULATOR
# ==============================================================================

def calc_linear_regression_channel(
    prices: List[float],
    lookback: int,
    mult: float = 2.0
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    Calculate rolling linear regression channel (Midline, Upper, Lower, Slope).
    No lookahead: at index i, uses prices[i - lookback + 1 : i + 1].

    Returns:
      midlines: [None, ..., float]
      uppers:   [None, ..., float]
      lowers:   [None, ..., float]
      slopes:   [None, ..., float]
    """
    n = len(prices)
    midlines: List[Optional[float]] = [None] * n
    uppers: List[Optional[float]] = [None] * n
    lowers: List[Optional[float]] = [None] * n
    slopes: List[Optional[float]] = [None] * n

    if n < 5:
        return midlines, uppers, lowers, slopes

    # Precompute x terms for window length L
    # We allow lookback to adapt if fewer bars exist, but require at least 15 bars
    for i in range(n):
        curr_len = lookback if (i + 1) >= lookback else (i + 1)
        if curr_len < 10:
            continue

        window = prices[i - curr_len + 1 : i + 1]
        L = curr_len
        mean_x = (L - 1) / 2.0
        mean_y = sum(window) / L

        s_xx = (L * (L * L - 1)) / 12.0
        s_xy = sum((j - mean_x) * (window[j] - mean_y) for j in range(L))

        slope = s_xy / s_xx if s_xx != 0 else 0.0
        intercept = mean_y - slope * mean_x

        # Current bar value at x = L - 1
        curr_mid = intercept + slope * (L - 1)

        # Standard error of the regression
        residuals_sq = sum(
            (window[j] - (intercept + slope * j)) ** 2 for j in range(L)
        )
        std_err = math.sqrt(residuals_sq / max(1, L - 2)) if L > 2 else 0.0

        half_width = mult * std_err
        midlines[i] = round(curr_mid, 4)
        uppers[i] = round(curr_mid + half_width, 4)
        lowers[i] = round(curr_mid - half_width, 4)
        slopes[i] = round(slope, 6)

    return midlines, uppers, lowers, slopes


def calc_ema(values: List[float], period: int) -> List[Optional[float]]:
    """Calculates Exponential Moving Average."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    out[period - 1] = sum(values[:period]) / period
    k = 2.0 / (period + 1)
    for i in range(period, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1.0 - k)
    return out


def calc_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[Optional[float]]:
    """Calculates Average True Range."""
    n = len(closes)
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return calc_ema(trs, period)


def calc_donchian_channel(
    highs: List[float],
    lows: List[float],
    lookback: int
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Calculates Rolling Donchian Range Channel."""
    n = len(highs)
    midlines: List[Optional[float]] = [None] * n
    uppers: List[Optional[float]] = [None] * n
    lowers: List[Optional[float]] = [None] * n
    slopes: List[Optional[float]] = [None] * n

    for i in range(n):
        curr_len = lookback if (i + 1) >= lookback else (i + 1)
        if curr_len < 5:
            continue
        window_highs = highs[i - curr_len + 1 : i + 1]
        window_lows = lows[i - curr_len + 1 : i + 1]
        u = max(window_highs)
        d = min(window_lows)
        m = (u + d) / 2.0
        uppers[i] = round(u, 4)
        lowers[i] = round(d, 4)
        midlines[i] = round(m, 4)
        prev_m = midlines[i - 1] if i > 0 and midlines[i - 1] is not None else m
        slopes[i] = round(m - prev_m, 6)

    return midlines, uppers, lowers, slopes


def calc_keltner_channel(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    lookback: int,
    mult: float = 2.0
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Calculates Adaptive Keltner (EMA + ATR) Channel."""
    n = len(closes)
    ema_vals = calc_ema(closes, min(lookback, max(5, n // 4)))
    atr_vals = calc_atr(highs, lows, closes, min(lookback, max(5, n // 4)))

    midlines: List[Optional[float]] = [None] * n
    uppers: List[Optional[float]] = [None] * n
    lowers: List[Optional[float]] = [None] * n
    slopes: List[Optional[float]] = [None] * n

    for i in range(n):
        e = ema_vals[i]
        a = atr_vals[i]
        if e is None or a is None:
            continue
        midlines[i] = round(e, 4)
        uppers[i] = round(e + mult * a, 4)
        lowers[i] = round(e - mult * a, 4)
        prev_e = ema_vals[i - 1] if i > 0 and ema_vals[i - 1] is not None else e
        slopes[i] = round(e - prev_e, 6)

    return midlines, uppers, lowers, slopes


def calc_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Calculates Relative Strength Index."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n <= period:
        return out
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    out[period] = 100.0 if avg_loss == 0 else round(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)), 2)
    for i in range(period + 1, n):
        diff = closes[i] - closes[i - 1]
        g = max(diff, 0.0)
        l = max(-diff, 0.0)
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = 100.0 if avg_loss == 0 else round(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)), 2)
    return out


# ==============================================================================
# STRATEGY CORE & BACKTEST ENGINE
# ==============================================================================

def run_enhanced_channel(
    candles: List[Dict[str, Any]],
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executes the Enhanced Channel Strategy over historical candles.
    """
    if params is None:
        params = {}

    n = len(candles)
    if n < 20:
        raise ValueError(f"Insufficient candle count ({n}) for channel backtesting.")

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    opens = [c["open"] for c in candles]

    tactical_lb = params.get("tactical_lookback", TACTICAL_LOOKBACK)
    intermediate_lb = params.get("intermediate_lookback", INTERMEDIATE_LOOKBACK)
    macro_lb = params.get("macro_lookback", MACRO_LOOKBACK)
    mult = params.get("channel_mult", CHANNEL_MULT)
    leeway_pct = params.get("leeway_pct", LEEWAY_PCT)
    stopgap_pct = params.get("stopgap_pct", STOPGAP_PCT)
    htf_filter = params.get("htf_filter", HTF_FILTER)
    confluence_boost = params.get("confluence_boost", CONFLUENCE_BOOST)
    long_only = params.get("long_only", LONG_ONLY)
    channel_type = params.get("channel_type", "linreg")
    bounce_type = params.get("bounce_type", "2bar")
    stopgap_type = params.get("stopgap_type", "close")
    dynamic_sizing = params.get("dynamic_sizing", False)
    use_stop_loss = params.get("use_stop_loss", True)
    midline_reentry = params.get("midline_reentry", False)
    midline_cross = params.get("midline_cross", False) or midline_reentry
    channel_inflection = params.get("channel_inflection", True)
    lower_reclaim = params.get("lower_reclaim", True)
    rsi_vals = calc_rsi(closes, 14) if bounce_type == "rsi" else []
    atr_vals_stop = calc_atr(highs, lows, closes, 14) if stopgap_type == "atr" else []

    # 1. Calculate Channels based on selected geometry
    if channel_type == "donchian":
        mid_3m, up_3m, low_3m, slope_3m = calc_donchian_channel(highs, lows, tactical_lb)
        mid_1y, up_1y, low_1y, slope_1y = calc_donchian_channel(highs, lows, intermediate_lb)
        mid_5y, up_5y, low_5y, slope_5y = calc_donchian_channel(highs, lows, macro_lb)
    elif channel_type == "keltner":
        mid_3m, up_3m, low_3m, slope_3m = calc_keltner_channel(closes, highs, lows, tactical_lb, mult)
        mid_1y, up_1y, low_1y, slope_1y = calc_keltner_channel(closes, highs, lows, intermediate_lb, mult)
        mid_5y, up_5y, low_5y, slope_5y = calc_keltner_channel(closes, highs, lows, macro_lb, mult)
    else:
        mid_3m, up_3m, low_3m, slope_3m = calc_linear_regression_channel(closes, tactical_lb, mult)
        mid_1y, up_1y, low_1y, slope_1y = calc_linear_regression_channel(closes, intermediate_lb, mult)
        mid_5y, up_5y, low_5y, slope_5y = calc_linear_regression_channel(closes, macro_lb, mult)

    trades: List[Dict[str, Any]] = []
    position: Optional[Dict[str, Any]] = None

    # Overlays for visualization
    tactical_upper_overlay = []
    tactical_mid_overlay = []
    tactical_lower_overlay = []
    intermediate_mid_overlay = []
    macro_mid_overlay = []

    # Warm-up requirement
    min_warmup = min(tactical_lb, n // 3)

    for i in range(min_warmup, n):
        date = candles[i]["date"]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        prev_c = closes[i - 1]

        u3 = up_3m[i]
        m3 = mid_3m[i]
        d3 = low_3m[i]

        if u3 is not None:
            tactical_upper_overlay.append({"time": date, "value": u3})
            tactical_mid_overlay.append({"time": date, "value": m3})
            tactical_lower_overlay.append({"time": date, "value": d3})

        if mid_1y[i] is not None:
            intermediate_mid_overlay.append({"time": date, "value": mid_1y[i]})
        if mid_5y[i] is not None:
            macro_mid_overlay.append({"time": date, "value": mid_5y[i]})

        if d3 is None or u3 is None or u3 <= d3:
            continue

        ch_height = u3 - d3
        bottom_leeway = d3 + leeway_pct * ch_height

        if stopgap_type == "atr" and i < len(atr_vals_stop) and atr_vals_stop[i] is not None:
            stopgap_margin = 1.5 * atr_vals_stop[i]
        else:
            stopgap_margin = stopgap_pct * ch_height

        stopgap_level = d3 - stopgap_margin
        top_leeway = u3 - leeway_pct * ch_height

        # Higher Timeframe Metrics
        pos_1y_pct = 0.5
        if up_1y[i] is not None and low_1y[i] is not None and up_1y[i] > low_1y[i]:
            pos_1y_pct = (c - low_1y[i]) / (up_1y[i] - low_1y[i])

        s_1y = slope_1y[i] or 0.0

        # -------------------------------------------------------------
        # 1. MANAGE ACTIVE POSITION
        # -------------------------------------------------------------
        if position is not None:
            side = position["side"]
            if side == "long":
                # Ratchet stopgap level upward if channel rises (never let stop loss lower)
                if stopgap_level > position["stop_level"]:
                    position["stop_level"] = stopgap_level

                # Check Stopgap: Price dropped below the ratcheted stopgap level
                is_stop_hit = (c < position["stop_level"]) if stopgap_type == "close" else (c < position["stop_level"] or l < position["stop_level"])
                if use_stop_loss and is_stop_hit:
                    exit_price = c if stopgap_type == "close" else min(c, position["stop_level"])
                    exit_type = "stopgap_exit" if exit_price <= position["entry_price"] else "trailing_channel_exit"
                    trades.append({
                        "side": "long",
                        "entry_date": position["entry_date"],
                        "entry_price": position["entry_price"],
                        "entry_bar": position["entry_bar"],
                        "entry_reason": position["entry_reason"],
                        "exit_date": date,
                        "exit_price": round(exit_price, 4),
                        "exit_bar": i,
                        "exit_reason": exit_type,
                        "bars_held": i - position["entry_bar"],
                        "tier": position["tier"],
                        "size_pct": position.get("size_pct", 1.0),
                        "strategy": "enhanced_channel",
                    })
                    position = None
                    continue

                # Track whether price has reached or traded above the tactical midline
                if m3 is not None and (h >= m3 or c >= m3 or position.get("entry_reason") == "midline_reclaim"):
                    position["reached_mid"] = True

                # Check Midline Cross Exit:
                # If midline_cross is enabled, price crossing down below the midline triggers an immediate exit
                if midline_cross and m3 is not None:
                    prev_m = mid_3m[i - 1] if (i > 0 and mid_3m[i - 1] is not None) else m3
                    crossed_below_mid = (prev_c >= prev_m or opens[i] >= m3) and (c < m3)
                    if crossed_below_mid:
                        trades.append({
                            "side": "long",
                            "entry_date": position["entry_date"],
                            "entry_price": position["entry_price"],
                            "entry_bar": position["entry_bar"],
                            "entry_reason": position["entry_reason"],
                            "exit_date": date,
                            "exit_price": round(c, 4),
                            "exit_bar": i,
                            "exit_reason": "midline_cross_exit",
                            "bars_held": i - position["entry_bar"],
                            "tier": position["tier"],
                            "size_pct": position.get("size_pct", 1.0),
                            "strategy": "enhanced_channel",
                        })
                        position = None
                        continue

                # Check Midline Stop Loss:
                # If price reached above the midline and is now crossing below in the negative direction,
                # sell immediately to cut loss and preserve capital (e.g. 3 June 2026).
                if not midline_cross and use_stop_loss and position.get("reached_mid", False) and m3 is not None:
                    prev_m = mid_3m[i - 1] if (i > 0 and mid_3m[i - 1] is not None) else m3
                    crossed_below_mid = (prev_c >= prev_m) and (c < m3)
                    going_down = (c < o) and (c < prev_c)
                    if crossed_below_mid and going_down:
                        trades.append({
                            "side": "long",
                            "entry_date": position["entry_date"],
                            "entry_price": position["entry_price"],
                            "entry_bar": position["entry_bar"],
                            "entry_reason": position["entry_reason"],
                            "exit_date": date,
                            "exit_price": round(c, 4),
                            "exit_bar": i,
                            "exit_reason": "midline_stop_exit",
                            "bars_held": i - position["entry_bar"],
                            "tier": position["tier"],
                            "size_pct": position.get("size_pct", 1.0),
                            "strategy": "enhanced_channel",
                        })
                        position = None
                        continue

                # Track whether price has reached the upper channel zone
                if h >= top_leeway or c >= top_leeway:
                    position["target_reached"] = True

                # Check Channel Top Rejection (Take Profit):
                downward_rejection = (c < o) and (c < prev_c)
                if position.get("target_reached", False) and downward_rejection:
                    trades.append({
                        "side": "long",
                        "entry_date": position["entry_date"],
                        "entry_price": position["entry_price"],
                        "entry_bar": position["entry_bar"],
                        "entry_reason": position["entry_reason"],
                        "exit_date": date,
                        "exit_price": round(c, 4),
                        "exit_bar": i,
                        "exit_reason": "channel_top_exit",
                        "bars_held": i - position["entry_bar"],
                        "tier": position["tier"],
                        "size_pct": position.get("size_pct", 1.0),
                        "strategy": "enhanced_channel",
                    })
                    position = None
                    continue

            elif side == "short":
                # Short stopgap is above upper line
                short_stop_level = u3 + stopgap_margin
                # Ratchet stopgap downward if channel falls (never let stop loss increase)
                if short_stop_level < position["stop_level"]:
                    position["stop_level"] = short_stop_level

                is_stop_hit = (c > position["stop_level"]) if stopgap_type == "close" else (c > position["stop_level"] or h > position["stop_level"])
                if use_stop_loss and is_stop_hit:
                    exit_price = c if stopgap_type == "close" else max(c, position["stop_level"])
                    exit_type = "stopgap_exit" if exit_price >= position["entry_price"] else "trailing_channel_exit"
                    trades.append({
                        "side": "short",
                        "entry_date": position["entry_date"],
                        "entry_price": position["entry_price"],
                        "entry_bar": position["entry_bar"],
                        "entry_reason": position["entry_reason"],
                        "exit_date": date,
                        "exit_price": round(exit_price, 4),
                        "exit_bar": i,
                        "exit_reason": exit_type,
                        "bars_held": i - position["entry_bar"],
                        "tier": position["tier"],
                        "size_pct": position.get("size_pct", 1.0),
                        "strategy": "enhanced_channel",
                    })
                    position = None
                    continue

                # Track whether price has reached or traded below the tactical midline
                if m3 is not None and (l <= m3 or c <= m3):
                    position["reached_mid"] = True

                # Check Midline Stop Loss (Short cover if price crosses above midline in positive direction)
                if use_stop_loss and position.get("reached_mid", False) and m3 is not None:
                    prev_m = mid_3m[i - 1] if (i > 0 and mid_3m[i - 1] is not None) else m3
                    crossed_above_mid = (prev_c <= prev_m) and (c > m3)
                    going_up = (c > o) and (c > prev_c)
                    if crossed_above_mid and going_up:
                        trades.append({
                            "side": "short",
                            "entry_date": position["entry_date"],
                            "entry_price": position["entry_price"],
                            "entry_bar": position["entry_bar"],
                            "entry_reason": position["entry_reason"],
                            "exit_date": date,
                            "exit_price": round(c, 4),
                            "exit_bar": i,
                            "exit_reason": "midline_stop_exit",
                            "bars_held": i - position["entry_bar"],
                            "tier": position["tier"],
                            "size_pct": position.get("size_pct", 1.0),
                            "strategy": "enhanced_channel",
                        })
                        position = None
                        continue

                # Track if price reached bottom leeway zone
                if l <= bottom_leeway or c <= bottom_leeway:
                    position["target_reached"] = True

                # Channel Bottom Rebound (Cover Short for Profit):
                upward_bounce = (c > o) and (c > prev_c)
                if position.get("target_reached", False) and upward_bounce:
                    trades.append({
                        "side": "short",
                        "entry_date": position["entry_date"],
                        "entry_price": position["entry_price"],
                        "entry_bar": position["entry_bar"],
                        "entry_reason": position["entry_reason"],
                        "exit_date": date,
                        "exit_price": round(c, 4),
                        "exit_bar": i,
                        "exit_reason": "channel_bottom_exit",
                        "bars_held": i - position["entry_bar"],
                        "tier": position["tier"],
                        "size_pct": position.get("size_pct", 1.0),
                        "strategy": "enhanced_channel",
                    })
                    position = None
                    continue

        # -------------------------------------------------------------
        # 2. EVALUATE ENTRY CONDITIONS (IF FLAT)
        # -------------------------------------------------------------
        if position is None:
            # --- LONG ENTRY EVALUATION ---
            recent_touch_bottom = False
            for look_idx in range(max(0, i - 2), i + 1):
                if low_3m[look_idx] is not None and up_3m[look_idx] is not None:
                    ch_h = up_3m[look_idx] - low_3m[look_idx]
                    bot_lee = low_3m[look_idx] + leeway_pct * ch_h
                    if lower_reclaim:
                        # Any touch or breach into/below lower channel leeway zone qualifies as a bottom contact
                        if lows[look_idx] <= bot_lee or closes[look_idx] <= low_3m[look_idx]:
                            recent_touch_bottom = True
                            break
                    else:
                        stp_lvl = low_3m[look_idx] - stopgap_pct * ch_h
                        if lows[look_idx] <= bot_lee and lows[look_idx] >= stp_lvl:
                            recent_touch_bottom = True
                            break

            if bounce_type == "rsi":
                rsi_now = rsi_vals[i] if i < len(rsi_vals) else None
                rsi_prev = rsi_vals[i - 1] if (i - 1) < len(rsi_vals) else None
                rsi_turn = (rsi_now is not None and rsi_prev is not None and rsi_now > rsi_prev and rsi_prev <= 45 and c > o)
                bounce_confirmed = bool(rsi_turn and (c > d3))
            elif bounce_type == "2bar":
                b_conf = (c > o) and (c > prev_c) and (c > d3)
                if i >= 2:
                    classic_2bar = (prev_c > opens[i - 1]) and (prev_c > closes[i - 2])
                    bullish_engulfing = (c > highs[i - 1]) and (max(c - o, c - prev_c) >= 0.015 * prev_c)
                    bounce_confirmed = b_conf and (classic_2bar or bullish_engulfing)
                else:
                    bounce_confirmed = b_conf
            else:  # "1bar"
                bounce_confirmed = (c > o) and (c > prev_c) and (c > d3)

            # Lower Channel Reclaim: Price moved from below/at lower band to above it on a confirmed bullish candle
            prev_d3 = low_3m[i - 1] if (i > 0 and low_3m[i - 1] is not None) else d3
            was_below_channel = (prev_c <= prev_d3) or (opens[i] <= d3) or (lows[i] <= d3)
            reclaimed_channel = lower_reclaim and was_below_channel and (c > d3) and (c > o) and (c > prev_c)

            should_enter_bottom = (recent_touch_bottom and bounce_confirmed) or (reclaimed_channel and bounce_confirmed)

            if should_enter_bottom:
                allowed = True
                if htf_filter:
                    htf_cap = 0.75 if reclaimed_channel else 0.60
                    if s_1y < -0.05 and pos_1y_pct > htf_cap:
                        allowed = False

                if allowed:
                    tier = "tactical_3m"
                    entry_reason = "channel_reclaim" if reclaimed_channel else "bottom_bounce"
                    size_pct = 0.5 if dynamic_sizing else 1.0
                    if confluence_boost and pos_1y_pct <= 0.30:
                        tier = "confluence_grade_a"
                        entry_reason = "confluence_bounce"
                        size_pct = 1.0

                    position = {
                        "side": "long",
                        "entry_date": date,
                        "entry_price": round(c, 4),
                        "entry_bar": i,
                        "entry_reason": entry_reason,
                        "tier": tier,
                        "size_pct": size_pct,
                        "stop_level": stopgap_level,
                        "target_reached": False,
                        "reached_mid": False,
                    }
                    continue

            # --- TACTICAL MIDLINE CROSS BUY ---
            if midline_cross and mid_3m[i] is not None and position is None:
                prev_m = mid_3m[i - 1] if (i > 0 and mid_3m[i - 1] is not None) else mid_3m[i]
                crossed_above_mid = (prev_c <= prev_m or opens[i] <= mid_3m[i]) and (c > mid_3m[i])
                bullish_mid = (c > o) and (c > prev_c)
                if crossed_above_mid and bullish_mid:
                    allowed = not (htf_filter and s_1y < -0.05 and pos_1y_pct > 0.70)
                    if allowed:
                        position = {
                            "side": "long",
                            "entry_date": date,
                            "entry_price": round(c, 4),
                            "entry_bar": i,
                            "entry_reason": "midline_cross",
                            "tier": "tactical_midline",
                            "size_pct": 0.5 if dynamic_sizing else 1.0,
                            "stop_level": stopgap_level,
                            "target_reached": False,
                            "reached_mid": True,
                        }
                        continue

            # --- CHANNEL INFLECTION / VALLEY CURL (TURNING HORIZONTAL TO UPWARD) ---
            if channel_inflection and position is None:
                m0 = mid_3m[i]
                m1 = mid_3m[i - 1] if i >= 1 else None
                m2 = mid_3m[i - 2] if i >= 2 else None
                m3_prev = mid_3m[i - 3] if i >= 3 else None

                if None not in (m0, m1, m2, m3_prev):
                    # Was declining previously (channel was going downwards)
                    was_declining = (m2 < m3_prev) or (m1 < m3_prev)
                    # Flattens and curls strictly upward (rate of increase >= 0.3% of channel height)
                    is_turning_up = (m0 > m1) and ((m0 - m1) >= 0.003 * ch_height)
                    # Price confirmation: green candle closing at or above curling midline
                    price_above_mid = (c >= m0) and (c > o) and (c > prev_c)
                    if was_declining and is_turning_up and price_above_mid:
                        allowed = not (htf_filter and s_1y < -0.05 and pos_1y_pct > 0.60)
                        if allowed:
                            position = {
                                "side": "long",
                                "entry_date": date,
                                "entry_price": round(c, 4),
                                "entry_bar": i,
                                "entry_reason": "channel_inflection",
                                "tier": "tactical_inflection",
                                "size_pct": 0.5 if dynamic_sizing else 1.0,
                                "stop_level": stopgap_level,
                                "target_reached": False,
                                "reached_mid": True,
                            }
                            continue

            # --- SHORT ENTRY EVALUATION (IF NOT LONG-ONLY) ---
            if not long_only:
                recent_touch_top = False
                for look_idx in range(max(0, i - 2), i + 1):
                    if low_3m[look_idx] is not None and up_3m[look_idx] is not None:
                        ch_h = up_3m[look_idx] - low_3m[look_idx]
                        top_lee = up_3m[look_idx] - leeway_pct * ch_h
                        stp_lvl_top = up_3m[look_idx] + stopgap_pct * ch_h
                        if highs[look_idx] >= top_lee and highs[look_idx] <= stp_lvl_top:
                            recent_touch_top = True
                            break

                if bounce_type == "rsi":
                    rsi_now = rsi_vals[i] if i < len(rsi_vals) else None
                    rsi_prev = rsi_vals[i - 1] if (i - 1) < len(rsi_vals) else None
                    rsi_turn_down = (rsi_now is not None and rsi_prev is not None and rsi_now < rsi_prev and rsi_prev >= 55 and c < o)
                    rejection_confirmed = bool(rsi_turn_down and (c < u3))
                elif bounce_type == "2bar":
                    r_conf = (c < o) and (c < prev_c) and (c < u3)
                    if i >= 2:
                        classic_2bar = (prev_c < opens[i - 1]) and (prev_c < closes[i - 2])
                        bearish_engulfing = (c < lows[i - 1]) and ((o - c) > 0.015 * c)
                        rejection_confirmed = r_conf and (classic_2bar or bearish_engulfing)
                    else:
                        rejection_confirmed = r_conf
                else:
                    rejection_confirmed = (c < o) and (c < prev_c) and (c < u3)

                if recent_touch_top and rejection_confirmed:
                    allowed_short = True
                    if htf_filter:
                        # Don't short if 1Y is strongly uptrending and price is near 1Y bottom
                        if s_1y > 0.05 and pos_1y_pct < 0.40:
                            allowed_short = False

                    if allowed_short:
                        tier = "tactical_3m_short"
                        entry_reason = "top_rejection_short"
                        position = {
                            "side": "short",
                            "entry_date": date,
                            "entry_price": round(c, 4),
                            "entry_bar": i,
                            "entry_reason": entry_reason,
                            "tier": tier,
                            "stop_level": u3 + stopgap_margin,
                            "target_reached": False,
                            "reached_mid": False,
                        }

    # Close open position on last bar
    if position is not None:
        last_c = candles[-1]["close"]
        trades.append({
            "side": position["side"],
            "entry_date": position["entry_date"],
            "entry_price": position["entry_price"],
            "entry_bar": position["entry_bar"],
            "entry_reason": position["entry_reason"],
            "exit_date": candles[-1]["date"],
            "exit_price": round(last_c, 4),
            "exit_bar": n - 1,
            "exit_reason": "end_of_data",
            "bars_held": n - 1 - position["entry_bar"],
            "tier": position["tier"],
            "size_pct": position.get("size_pct", 1.0),
            "strategy": "enhanced_channel",
        })

    return {
        "raw_trades": trades,
        "overlays": [
            {"label": "Tactical Upper (3M)", "color": "#2196F3", "type": "line", "points": tactical_upper_overlay},
            {"label": "Tactical Mid (3M)", "color": "#90CAF9", "type": "line", "points": tactical_mid_overlay},
            {"label": "Tactical Lower (3M)", "color": "#2196F3", "type": "line", "points": tactical_lower_overlay},
            {"label": "Intermediate Mid (200b)", "color": "#FF9800", "type": "line", "points": intermediate_mid_overlay},
            {"label": "Macro Mid (1000b)", "color": "#9C27B0", "type": "line", "points": macro_mid_overlay},
        ]
    }


def run_enhanced_channel_trades(candles: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
    """Standard runner for backtest_service and UI integration."""
    res = run_enhanced_channel(candles, params=kwargs if kwargs else None)
    return res["raw_trades"]


# ==============================================================================
# PERFORMANCE METRICS & COST MODELING
# ==============================================================================

def apply_costs(
    raw_trades: List[Dict[str, Any]],
    commission_pct: float,
    slippage_pct: float
) -> List[Dict[str, Any]]:
    """Deducts trading friction (commission + slippage) from trade execution."""
    cost_factor = 1.0 - (commission_pct + slippage_pct) / 100.0
    processed: List[Dict[str, Any]] = []

    for t in raw_trades:
        en = t["entry_price"]
        ex = t["exit_price"]
        side = t.get("side", "long")
        if side == "long":
            gross_ret = (ex - en) / en if en > 0 else 0.0
        else:
            gross_ret = (en - ex) / en if en > 0 else 0.0
        # Net return after round-trip slippage and commissions
        net_ret = (1.0 + gross_ret) * (cost_factor ** 2) - 1.0

        t_copy = dict(t)
        t_copy["gross_return_pct"] = round(gross_ret * 100.0, 2)
        t_copy["return_pct"] = round(net_ret * 100.0, 2)
        processed.append(t_copy)

    return processed


def calc_metrics(
    trades: List[Dict[str, Any]],
    initial_capital: float
) -> Dict[str, Any]:
    """Calculates quantitative performance metrics for the strategy."""
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "initial_capital": initial_capital,
            "final_capital": initial_capital,
            "total_return_pct": 0.0,
            "total_trades": 0,
            "long_trades": 0,
            "short_trades": 0,
            "win_rate_pct": 0.0,
            "avg_gain_pct": 0.0,
            "avg_loss_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "channel_top_exits": 0,
            "channel_bottom_exits": 0,
            "trailing_channel_exits": 0,
            "stopgap_exits": 0,
            "end_of_data_exits": 0,
        }

    wins = [t["return_pct"] for t in trades if t["return_pct"] > 0]
    losses = [t["return_pct"] for t in trades if t["return_pct"] <= 0]

    win_rate = round(len(wins) / total_trades * 100.0, 2)
    avg_gain = round(statistics.mean(wins), 2) if wins else 0.0
    avg_loss = round(statistics.mean(losses), 2) if losses else 0.0

    sum_gain = sum(wins)
    sum_loss = abs(sum(losses))
    profit_factor = round(sum_gain / sum_loss, 2) if sum_loss > 0 else (999.0 if sum_gain > 0 else 0.0)

    # Equity curve and drawdown calculation
    cap = initial_capital
    peak = initial_capital
    max_dd = 0.0
    daily_returns: List[float] = []

    for t in trades:
        ret = t["return_pct"] / 100.0
        sz = t.get("size_pct", 1.0)
        pnl = cap * sz * ret
        cap += pnl
        if cap > peak:
            peak = cap
        dd = (peak - cap) / peak * 100.0
        if dd > max_dd:
            max_dd = dd
        daily_returns.append(sz * ret)

    final_capital = round(cap, 2)
    total_return_pct = round((final_capital - initial_capital) / initial_capital * 100.0, 2)

    # Annualized Sharpe approximation
    sharpe = 0.0
    if len(daily_returns) > 1:
        avg_r = statistics.mean(daily_returns)
        std_r = statistics.stdev(daily_returns)
        if std_r > 1e-8:
            # Assumes ~10-15 trades per year on daily
            sharpe = round((avg_r / std_r) * math.sqrt(min(252, max(4, total_trades))), 2)

    exit_counts = {
        "channel_top_exit": sum(1 for t in trades if t["exit_reason"] == "channel_top_exit"),
        "channel_bottom_exit": sum(1 for t in trades if t["exit_reason"] == "channel_bottom_exit"),
        "trailing_channel_exit": sum(1 for t in trades if t["exit_reason"] == "trailing_channel_exit"),
        "stopgap_exit": sum(1 for t in trades if t["exit_reason"] == "stopgap_exit"),
        "midline_stop_exit": sum(1 for t in trades if t["exit_reason"] == "midline_stop_exit"),
        "end_of_data": sum(1 for t in trades if t["exit_reason"] == "end_of_data"),
    }

    long_trades = sum(1 for t in trades if t.get("side", "long") == "long")
    short_trades = sum(1 for t in trades if t.get("side", "long") == "short")

    return {
        "initial_capital": initial_capital,
        "final_capital": final_capital,
        "total_return_pct": total_return_pct,
        "total_trades": total_trades,
        "long_trades": long_trades,
        "short_trades": short_trades,
        "win_rate_pct": win_rate,
        "avg_gain_pct": avg_gain,
        "avg_loss_pct": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": round(max_dd, 2),
        "channel_top_exits": exit_counts["channel_top_exit"],
        "channel_bottom_exits": exit_counts["channel_bottom_exit"],
        "trailing_channel_exits": exit_counts["trailing_channel_exit"],
        "stopgap_exits": exit_counts["stopgap_exit"],
        "midline_stop_exits": exit_counts["midline_stop_exit"],
        "end_of_data_exits": exit_counts["end_of_data"],
    }


def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    tactical_lookback: int = TACTICAL_LOOKBACK,
    intermediate_lookback: int = INTERMEDIATE_LOOKBACK,
    macro_lookback: int = MACRO_LOOKBACK,
    channel_mult: float = CHANNEL_MULT,
    leeway_pct: float = LEEWAY_PCT,
    stopgap_pct: float = STOPGAP_PCT,
    htf_filter: bool = HTF_FILTER,
    confluence_boost: bool = CONFLUENCE_BOOST,
    long_only: bool = LONG_ONLY,
    confirm_bars: int = 2,
    channel_type: str = "linreg",
    bounce_type: str = "2bar",
    stopgap_type: str = "close",
    dynamic_sizing: bool = False,
    use_stop_loss: bool = True,
    midline_reentry: bool = False,
    midline_cross: bool = False,
    channel_inflection: bool = True,
    lower_reclaim: bool = True,
) -> Dict[str, Any]:
    """Complete backtest runner."""
    candles = fetch_ohlcv(symbol, period, interval)
    params = {
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "tactical_lookback": tactical_lookback,
        "intermediate_lookback": intermediate_lookback,
        "macro_lookback": macro_lookback,
        "channel_mult": channel_mult,
        "leeway_pct": leeway_pct,
        "stopgap_pct": stopgap_pct,
        "htf_filter": htf_filter,
        "confluence_boost": confluence_boost,
        "long_only": long_only,
        "confirm_bars": confirm_bars,
        "channel_type": channel_type,
        "bounce_type": bounce_type,
        "stopgap_type": stopgap_type,
        "dynamic_sizing": dynamic_sizing,
        "use_stop_loss": use_stop_loss,
        "midline_reentry": midline_reentry,
        "midline_cross": midline_cross,
        "channel_inflection": channel_inflection,
        "lower_reclaim": lower_reclaim,
    }

    strat_output = run_enhanced_channel(candles, params)
    trades = apply_costs(strat_output["raw_trades"], commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital)

    # Calculate Buy & Hold return from the strategy's first entry (or full candle span if no trades)
    if trades:
        first_entry = trades[0]["entry_price"]
        bnh = round((candles[-1]["close"] - first_entry) / first_entry * 100.0, 2)
    else:
        bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100.0, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "enhanced_channel",
        "strategy_label": f"Enhanced Channel ({channel_type.upper()}: 3M Tactical + 1Y Intermediate + 5Y Macro)",
        "parameters": params,
        "period": period,
        "interval": interval,
        "candles_analyzed": len(candles),
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "buy_and_hold_return_pct": bnh,
        "vs_buy_and_hold_pct": round(metrics["total_return_pct"] - bnh, 2),
        **metrics,
        "trade_log": trades,
        "overlays": strat_output["overlays"],
        "candles": candles,
        "data_source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Enhanced Channel Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Lookback period: 1y, 2y, 5y, max (default: 5y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1d", "1h"], help="Candle size (default: 1d)")
    parser.add_argument("--channel-type", default="linreg", choices=["linreg", "donchian", "keltner"], help="Channel geometry (default: linreg)")
    parser.add_argument("--bounce-type", default="2bar", choices=["1bar", "2bar", "rsi"], help="Bounce confirmation (default: 2bar)")
    parser.add_argument("--stopgap-type", default="close", choices=["low", "close", "atr"], help="Stopgap trigger (default: close)")
    parser.add_argument("--dynamic-sizing", action="store_true", help="Enable multi-tier sizing (50%% tactical, 100%% confluence) for lowest drawdown")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--tactical-lb", type=int, default=TACTICAL_LOOKBACK, help="Tactical lookback bars (default: 50 = ~2.5m)")
    parser.add_argument("--intermediate-lb", type=int, default=INTERMEDIATE_LOOKBACK, help="Intermediate lookback bars (default: 200)")
    parser.add_argument("--macro-lb", type=int, default=MACRO_LOOKBACK, help="Macro lookback bars (default: 1000)")
    parser.add_argument("--channel-mult", type=float, default=CHANNEL_MULT, help="Std error multiplier (default: 1.7)")
    parser.add_argument("--leeway", type=float, default=LEEWAY_PCT, help="Leeway tolerance fraction (default: 0.05 = 5%%)")
    parser.add_argument("--stopgap", type=float, default=STOPGAP_PCT, help="Stopgap margin below lower channel (default: 0.05 = 5%%)")
    parser.add_argument("--confirm-bars", type=int, default=2, choices=[1, 2], help="Bounce confirmation bars required (default: 2)")
    parser.add_argument("--allow-short", action="store_true", help="Enable short trades on channel top rejection")
    parser.add_argument("--no-htf-filter", action="store_true", help="Disable higher timeframe 1Y trend filter")
    parser.add_argument("--no-confluence", action="store_true", help="Disable confluence detection")
    parser.add_argument("--no-stop-loss", action="store_true", help="Disable stopgap and trailing stop loss")
    parser.add_argument("--midline-reentry", action="store_true", help="Enable tactical midline reclaim cash re-entry")
    parser.add_argument("--chart", action="store_true", help="Generate interactive HTML chart")
    args = parser.parse_args()

    side_label = "LONG + SHORT" if args.allow_short else "LONG-ONLY"
    sl_label = "OFF" if args.no_stop_loss else "ON"
    mid_label = "ON" if args.midline_reentry else "OFF"
    print(f"\n{'='*65}")
    print(f"  Enhanced Channel Strategy — {args.symbol.upper()} ({side_label}) [Stop Loss: {sl_label}] [Midline Re-entry: {mid_label}]")
    print(f"  Geometry: {args.channel_type.upper()}  |  Bounce Confirm: {args.bounce_type.upper()}  |  Stopgap: {args.stopgap_type.upper()}")
    print(f"  Timeframes: Tactical ({args.tactical_lb}b) | Intermediate ({args.intermediate_lb}b) | Macro ({args.macro_lb}b)")
    print(f"  Channel Mult: {args.channel_mult}x  |  Leeway: {args.leeway*100:.1f}%  |  Stopgap: {args.stopgap*100:.1f}%")
    print(f"{'='*65}\n")

    result = run_backtest(
        symbol=args.symbol,
        period=args.period,
        interval=args.interval,
        initial_capital=args.initial_capital,
        tactical_lookback=args.tactical_lb,
        intermediate_lookback=args.intermediate_lb,
        macro_lookback=args.macro_lb,
        channel_mult=args.channel_mult,
        leeway_pct=args.leeway,
        stopgap_pct=args.stopgap,
        htf_filter=not args.no_htf_filter,
        confluence_boost=not args.no_confluence,
        long_only=not args.allow_short,
        confirm_bars=args.confirm_bars,
        channel_type=args.channel_type,
        bounce_type=args.bounce_type,
        stopgap_type=args.stopgap_type,
        dynamic_sizing=args.dynamic_sizing,
        use_stop_loss=not args.no_stop_loss,
        midline_reentry=args.midline_reentry,
    )

    print(f"  Period:           {result['date_from']} -> {result['date_to']} ({result['candles_analyzed']} bars)")
    print(f"  Initial Capital:  ${result['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${result['final_capital']:,.2f}")
    print(f"  Total Return:     {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:     {result['total_trades']} (L: {result['long_trades']} | S: {result['short_trades']})")
    print(f"  Win Rate:         {result['win_rate_pct']}%")
    print(f"  Avg Gain:         {result['avg_gain_pct']:+.2f}%")
    print(f"  Avg Loss:         {result['avg_loss_pct']:+.2f}%")
    print(f"  Profit Factor:    {result['profit_factor']}")
    print(f"  Sharpe Ratio:     {result['sharpe_ratio']}")
    print(f"  Max Drawdown:     {result['max_drawdown_pct']}%")
    print(f"  Exits:            Take Profit: {result['channel_top_exits']} | Trailing SL: {result.get('trailing_channel_exits', 0)} | Stopgap SL: {result['stopgap_exits']} | EOD: {result['end_of_data_exits']}")

    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        tier_label = t.get("tier", "tactical")
        print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>9,.2f} -> ${t['exit_price']:>9,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t['exit_reason']}] ({tier_label})")

    print(f"\n{'='*65}\n")

    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    json_out = {k: v for k, v in result.items() if k not in ("overlays", "candles")}
    fname = script_dir / f"enhanced_channel_backtest_{safe_sym}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        try:
            repo_root = script_dir.parent.parent
            sys.path.insert(0, str(repo_root))
            from strategies.visualize import generate_chart_html
            chart_path = script_dir / f"enhanced_channel_chart_{safe_sym}_{args.period}.html"
            generate_chart_html(result=result, candles=result["candles"], output_path=chart_path)
            print(f"  Chart saved to: {chart_path}\n")
        except Exception as e:
            print(f"  Could not generate HTML chart: {e}\n")


if __name__ == "__main__":
    main()
