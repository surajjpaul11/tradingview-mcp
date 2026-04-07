"""
Curved Channel Strategy — Standalone Python Implementation
============================================================

Polynomial channel trading strategy based on curved_channel.pine.

The indicator fits polynomial curves (linear/quadratic/cubic) through
ascending and descending pivot sequences to form curved price channels.

Trading logic (backtester):
  - Ascending channel detected (HH upper + HL lower curves):
    • BUY when price bounces off the ascending lower boundary (support)
    • SELL when price breaks below the ascending lower boundary
  - Descending channel detected (LH upper + LL lower curves):
    • SHORT when price rejects from the descending upper boundary (resistance)
    • COVER when price breaks above the descending upper boundary

Entry confirmation: close must cross the channel boundary and next bar confirms.
Exit: channel break (opposite side), channel invalidation, or end of data.

Usage:
  python curved_channel_strategy.py                              # defaults: SPY, 2y, 1d
  python curved_channel_strategy.py --symbol BTC-USD --period 1y
  python curved_channel_strategy.py --symbol QQQ --degree 3
  python curved_channel_strategy.py --symbol AAPL --no-short

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


# ==============================================================================
# STRATEGY PARAMETERS
# ==============================================================================

PIVOT_LEFT           = 5       # bars left for pivot detection
PIVOT_RIGHT          = 5       # bars right for pivot detection
MAX_PIVOTS           = 20      # max pivots to keep in rolling window
MIN_TOUCH_POINTS     = 3       # min points curve must touch for valid channel
TOUCH_TOLERANCE_PCT  = 1.0     # % tolerance for curve-to-pivot match
POLY_DEGREE          = 2       # 1=linear, 2=quadratic, 3=cubic
BREAKOUT_PCT         = 2.0     # % beyond channel boundary to count as breakout
BREAKOUT_ADD_PCT     = 100     # % of capital to add on upside breakout (200% total position)
ATR_TRAIL_MULT       = 2.0     # ATR multiplier for trailing stop during wait period (longs)
SHORT_ATR_TRAIL_MULT = 1.5     # ATR multiplier for short trailing stop (tighter than longs)
ATR_PERIOD           = 14      # ATR lookback for trailing stop
ENABLE_SHORT         = True    # enable short positions
SHORT_SMA_PERIOD     = 200     # only allow shorts when price < SMA(this) (0 = no filter)
SHORT_MIN_HOLD       = 5       # minimum bars to hold a short before allowing exit (prevents whipsaw flips)
FALLBACK_SMA_PERIOD  = 50      # SMA period for flat-period re-entry (0 = disabled)
FALLBACK_WAIT_BARS   = 10      # bars to wait after last exit before fallback entry
SHORT_ENTRY_PCT      = 1.5     # % below support required to open short (vs TOUCH_TOLERANCE_PCT for long exit)
VOL_CONFIRM_MULT     = 1.2     # volume must be >= this * SMA(20) of volume to enter (0 = disabled)
VOL_CONFIRM_PERIOD   = 20      # lookback for volume MA
CH_TRAIL_ACTIVATE_PCT = 2.0    # in-channel trailing stop activates after this % profit (0 = disabled)
CH_TRAIL_ATR_MULT     = 1.5    # ATR multiplier for in-channel trailing stop (tighter than breakout trail)
SHORT_SIZE_BASE       = 25     # base short position size (%)
SHORT_SIZE_SCALE      = 12.5   # additional size per 1% break below support (0 = no scaling)
SHORT_SIZE_MAX        = 75     # max short position size (%)
TIME_EXIT_BARS        = 20     # close position if held this many bars with < 1% profit (0 = disabled)
RSI_DIVERGENCE_LOOKBACK = 0   # bars to check for RSI divergence (0 = disabled)
RSI_PERIOD            = 14    # RSI calculation period
RIDE_EXPIRED_WINNERS  = True  # keep profitable positions open when channel expires (ATR trail takeover)
MIN_CHANNEL_AGE      = 3     # minimum bars channel must exist before entry (0 = enter immediately)
MIN_EXTEND           = 20    # minimum bars to extend channel beyond last touch point
LOSS_COOLDOWN_BARS   = 0     # bars to wait after a losing trade before re-entering (0 = disabled)
INTERVAL             = "1d"    # candle size (1d works best for channels)
PERIOD               = "2y"    # data lookback
INITIAL_CAPITAL      = 10_000.0
COMMISSION_PCT       = 0.1
SLIPPAGE_PCT         = 0.05


# ==============================================================================
# STRATEGY VERSION REGISTRY — single source of truth for trade annotations
# ==============================================================================
# Each kept improvement is registered here. Charts, Trade Log, and version
# legend all derive from this dict automatically.
#   key: version tag (e.g. "v2")
#   value: (short_label, description, mechanism_type)
#   mechanism_type: "entry_filter" | "exit_type" | "channel_detection" | "sizing"

STRATEGY_VERSIONS = {
    "v1":  ("Full Channel",      "Widen entry to full channel width",              "entry_filter"),
    "v2":  ("Breakout Detect",   "Breakout invalidation + ATR trailing stop",      "exit_type"),
    "v3":  ("Short SMA Filter",  "SMA(200) filter for shorts",                    "entry_filter"),
    "v5":  ("Fallback SMA",      "SMA(50) re-entry during flat periods",           "entry_filter"),
    "v8":  ("Volume Confirm",    "Volume >= 1.2x MA(20) for entry",               "entry_filter"),
    "v9":  ("Channel Trail",     "In-channel trailing stop at 2% profit",          "exit_type"),
    "v10": ("Ride Winners",      "Keep profitable positions on channel expiry",     "exit_type"),
    "v21": ("Channel Age",       "Min 3-bar channel maturity for ETFs",            "entry_filter"),
    "v23": ("Tight Short Trail", "1.5x ATR trail for shorts (vs 2.0x longs)",     "exit_type"),
    "v25": ("2-Bar Confirm",     "Previous bar must also be in channel",           "entry_filter"),
    "v30": ("Crypto Breakout",   "Lower breakout threshold (1.5%) for crypto",     "channel_detection"),
    "v32": ("SMA Min Hold",      "Min 3-bar hold before fallback SMA exit",        "exit_type"),
    "v39": ("Crypto Extend",     "Longer channel extension (30 bars) for crypto",  "channel_detection"),
    "v48": ("SMA Trend Filter",  "Require close > SMA(50)*0.99 for long entry",   "entry_filter"),
}

# Maps exit_reason → list of version tags that contributed to that exit mechanism
EXIT_VERSION_MAP = {
    "atr_trailing_stop":  ["v2"],
    "channel_trail_stop": ["v9"],
    "breakout_up":        ["v2"],
    "breakout_down":      ["v2"],
    "channel_break":      [],
    "channel_flip":       [],
    "channel_expired":    ["v10"],
    "time_exit":          [],
    "fallback_sma_exit":  ["v5", "v32"],
    "end_of_data":        [],
}


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "curved-channel-strategy/1.0"})
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
# PIVOT DETECTION
# ==============================================================================

def find_pivots(highs: list[float], lows: list[float],
                left: int = 5, right: int = 5
                ) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """
    Detect pivot highs and pivot lows.

    Returns:
      pivot_highs: list of (bar_index, price)
      pivot_lows:  list of (bar_index, price)

    A pivot high at bar i is confirmed at bar i+right.
    """
    n = len(highs)
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows: list[tuple[int, float]] = []

    for i in range(left, n - right):
        # Pivot high: highest in window
        is_ph = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if highs[j] >= highs[i]:
                is_ph = False
                break
        if is_ph:
            pivot_highs.append((i, highs[i]))

        # Pivot low: lowest in window
        is_pl = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if lows[j] <= lows[i]:
                is_pl = False
                break
        if is_pl:
            pivot_lows.append((i, lows[i]))

    return pivot_highs, pivot_lows


# ==============================================================================
# POLYNOMIAL FIT — Least Squares (mirrors Pine's f_polyfit)
# ==============================================================================

def polyfit(x_bars: list[int], y_vals: list[float], degree: int = 2
            ) -> tuple[float, float, float, float, int, float] | None:
    """
    Fit a polynomial of given degree to (x_bars, y_vals).
    X values normalized to [0,1] to prevent float precision loss.

    Returns (c0, c1, c2, c3, origin, scale) or None if underdetermined.
    """
    n = len(x_bars)
    min_pts = degree + 1
    if n < min_pts:
        return None

    origin = x_bars[0]
    scale = max(1.0, float(x_bars[-1] - origin))

    # Accumulate power sums and cross-products
    S0 = float(n)
    S1 = S2 = S3 = S4 = S5 = S6 = 0.0
    Ty = Txy = Tx2y = Tx3y = 0.0

    for i in range(n):
        x = (x_bars[i] - origin) / scale
        y = y_vals[i]
        x2 = x * x
        x3 = x2 * x
        S1 += x
        S2 += x2
        S3 += x3
        S4 += x2 * x2
        S5 += x2 * x3
        S6 += x3 * x3
        Ty += y
        Txy += x * y
        Tx2y += x2 * y
        Tx3y += x3 * y

    c0 = c1 = c2 = c3 = 0.0

    if degree == 1:
        D = S0 * S2 - S1 * S1
        if abs(D) <= 1e-12:
            return None
        c0 = (Ty * S2 - S1 * Txy) / D
        c1 = (S0 * Txy - Ty * S1) / D

    elif degree == 2:
        D = S0 * (S2 * S4 - S3 * S3) - S1 * (S1 * S4 - S2 * S3) + S2 * (S1 * S3 - S2 * S2)
        if abs(D) <= 1e-12:
            return None
        c0 = (Ty * (S2 * S4 - S3 * S3) - S1 * (Txy * S4 - Tx2y * S3) + S2 * (Txy * S3 - Tx2y * S2)) / D
        c1 = (S0 * (Txy * S4 - Tx2y * S3) - Ty * (S1 * S4 - S2 * S3) + S2 * (S1 * Tx2y - S2 * Txy)) / D
        c2 = (S0 * (S2 * Tx2y - S3 * Txy) - S1 * (S1 * Tx2y - S2 * Txy) + Ty * (S1 * S3 - S2 * S2)) / D

    else:  # degree == 3
        # 4x5 augmented matrix, Gaussian elimination with partial pivoting
        A = [
            [S0, S1, S2, S3, Ty],
            [S1, S2, S3, S4, Txy],
            [S2, S3, S4, S5, Tx2y],
            [S3, S4, S5, S6, Tx3y],
        ]

        # Forward elimination
        for col in range(3):
            # Partial pivot
            max_row = col
            for row in range(col + 1, 4):
                if abs(A[row][col]) > abs(A[max_row][col]):
                    max_row = row
            if max_row != col:
                A[col], A[max_row] = A[max_row], A[col]

            if abs(A[col][col]) <= 1e-12:
                return None

            for row in range(col + 1, 4):
                factor = A[row][col] / A[col][col]
                for k in range(col, 5):
                    A[row][k] -= factor * A[col][k]

        # Back substitution
        if abs(A[3][3]) <= 1e-12:
            return None
        c3 = A[3][4] / A[3][3]
        c2 = (A[2][4] - A[2][3] * c3) / A[2][2]
        c1 = (A[1][4] - A[1][2] * c2 - A[1][3] * c3) / A[1][1]
        c0 = (A[0][4] - A[0][1] * c1 - A[0][2] * c2 - A[0][3] * c3) / A[0][0]

    return (c0, c1, c2, c3, origin, scale)


def poly_eval(c0: float, c1: float, c2: float, c3: float,
              origin: int, scale: float, bar: int) -> float:
    """Evaluate polynomial at a given bar index."""
    x = (bar - origin) / scale
    return c0 + c1 * x + c2 * x * x + c3 * x * x * x


# ==============================================================================
# ASCENDING / DESCENDING SEQUENCE EXTRACTION (mirrors Pine's f_ascSeq/f_dscSeq)
# ==============================================================================

def ascending_sequence(bars: list[int], vals: list[float]
                       ) -> tuple[list[int], list[float]]:
    """
    Dual-greedy longest ascending subsequence.
    Forward: start oldest, keep higher. Backward: start newest, go back keeping lower.
    Returns the longer sequence (tie -> backward, includes latest pivot).
    """
    n = len(bars)
    if n == 0:
        return [], []

    # Forward pass
    fb, fv = [bars[0]], [vals[0]]
    last_p = vals[0]
    for i in range(1, n):
        if vals[i] > last_p:
            fb.append(bars[i])
            fv.append(vals[i])
            last_p = vals[i]

    # Backward pass
    bb, bv = [bars[n - 1]], [vals[n - 1]]
    last_p2 = vals[n - 1]
    for i in range(n - 2, -1, -1):
        if vals[i] < last_p2:
            bb.insert(0, bars[i])
            bv.insert(0, vals[i])
            last_p2 = vals[i]

    if len(fb) > len(bb):
        return fb, fv
    return bb, bv


def descending_sequence(bars: list[int], vals: list[float]
                        ) -> tuple[list[int], list[float]]:
    """
    Dual-greedy longest descending subsequence.
    Forward: start oldest, keep lower. Backward: start newest, go back keeping higher.
    Returns the longer sequence (tie -> backward).
    """
    n = len(bars)
    if n == 0:
        return [], []

    # Forward pass
    fb, fv = [bars[0]], [vals[0]]
    last_p = vals[0]
    for i in range(1, n):
        if vals[i] < last_p:
            fb.append(bars[i])
            fv.append(vals[i])
            last_p = vals[i]

    # Backward pass
    bb, bv = [bars[n - 1]], [vals[n - 1]]
    last_p2 = vals[n - 1]
    for i in range(n - 2, -1, -1):
        if vals[i] > last_p2:
            bb.insert(0, bars[i])
            bv.insert(0, vals[i])
            last_p2 = vals[i]

    if len(fb) > len(bb):
        return fb, fv
    return bb, bv


# ==============================================================================
# CHANNEL BOUNDARY FIT (mirrors Pine's f_fitBound)
# ==============================================================================

def fit_boundary(seq_bars: list[int], seq_vals: list[float],
                 degree: int, min_touch: int, tolerance: float,
                 min_extend: int = 20,
                 ) -> dict | None:
    """
    Fit polynomial to a sequence, validate touch points.

    Returns dict with coefficients, origin, scale, start/end bars, touch points,
    or None if not enough valid touch points.
    """
    if len(seq_bars) < min_touch:
        return None

    result = polyfit(seq_bars, seq_vals, degree)
    if result is None:
        return None

    c0, c1, c2, c3, origin, scale = result

    # Validate touch points
    touch_bars = []
    touch_vals = []
    for i in range(len(seq_bars)):
        pred = poly_eval(c0, c1, c2, c3, origin, scale, seq_bars[i])
        actual = seq_vals[i]
        err = abs(pred - actual) / max(abs(actual), 1e-8)
        if err <= tolerance:
            touch_bars.append(seq_bars[i])
            touch_vals.append(seq_vals[i])

    if len(touch_bars) < min_touch:
        return None

    start_bar = touch_bars[0]
    end_bar = touch_bars[-1]
    # Extension: at least the gap between last two touch points
    gap = touch_bars[-1] - touch_bars[-2] if len(touch_bars) >= 2 else 20
    extend_to = end_bar + max(gap, min_extend)

    return {
        "c0": c0, "c1": c1, "c2": c2, "c3": c3,
        "origin": origin, "scale": scale,
        "start_bar": start_bar, "end_bar": end_bar,
        "extend_to": extend_to,
        "touch_bars": touch_bars, "touch_vals": touch_vals,
        "touch_count": len(touch_bars),
    }


# ==============================================================================
# CHANNEL DETECTION ENGINE
# ==============================================================================

def detect_channels(candles: list[dict], pivot_left: int, pivot_right: int,
                    max_pivots: int, degree: int, min_touch: int,
                    tolerance: float, min_extend: int = 20) -> list[dict]:
    """
    Walk through candles bar-by-bar, maintaining rolling pivot windows.
    When a new pivot is detected, refit all four channel boundaries.

    Returns a list of channel events:
      {bar, type: "ascending"|"descending", upper: boundary_dict, lower: boundary_dict}
    """
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    n = len(candles)

    # Rolling pivot storage (bar_index, value)
    ph_bars: list[int] = []
    ph_vals: list[float] = []
    pl_bars: list[int] = []
    pl_vals: list[float] = []

    channels: list[dict] = []

    for i in range(n):
        # Check for pivot high at bar (i - pivot_right)
        pivot_bar = i - pivot_right
        if pivot_bar >= pivot_left:
            is_ph = True
            for j in range(pivot_bar - pivot_left, pivot_bar + pivot_right + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if highs[j] >= highs[pivot_bar]:
                    is_ph = False
                    break
            if is_ph:
                ph_bars.append(pivot_bar)
                ph_vals.append(highs[pivot_bar])
                if len(ph_bars) > max_pivots:
                    ph_bars.pop(0)
                    ph_vals.pop(0)

            # Check for pivot low at same bar
            is_pl = True
            for j in range(pivot_bar - pivot_left, pivot_bar + pivot_right + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if lows[j] <= lows[pivot_bar]:
                    is_pl = False
                    break
            if is_pl:
                pl_bars.append(pivot_bar)
                pl_vals.append(lows[pivot_bar])
                if len(pl_bars) > max_pivots:
                    pl_bars.pop(0)
                    pl_vals.pop(0)

            if is_ph or is_pl:
                # Refit all channel boundaries
                # Ascending Higher Highs (upper)
                asc_hh_b, asc_hh_v = ascending_sequence(ph_bars, ph_vals)
                ah = fit_boundary(asc_hh_b, asc_hh_v, degree, min_touch, tolerance, min_extend=min_extend)

                # Ascending Higher Lows (lower)
                asc_hl_b, asc_hl_v = ascending_sequence(pl_bars, pl_vals)
                al = fit_boundary(asc_hl_b, asc_hl_v, degree, min_touch, tolerance, min_extend=min_extend)

                # Descending Lower Highs (upper)
                dsc_lh_b, dsc_lh_v = descending_sequence(ph_bars, ph_vals)
                dh = fit_boundary(dsc_lh_b, dsc_lh_v, degree, min_touch, tolerance, min_extend=min_extend)

                # Descending Lower Lows (lower)
                dsc_ll_b, dsc_ll_v = descending_sequence(pl_bars, pl_vals)
                dl = fit_boundary(dsc_ll_b, dsc_ll_v, degree, min_touch, tolerance, min_extend=min_extend)

                # Record ascending channel if both boundaries valid
                if ah is not None and al is not None:
                    channels.append({
                        "confirmed_bar": i,
                        "type": "ascending",
                        "upper": ah,
                        "lower": al,
                    })

                # Record descending channel if both boundaries valid
                if dh is not None and dl is not None:
                    channels.append({
                        "confirmed_bar": i,
                        "type": "descending",
                        "upper": dh,
                        "lower": dl,
                    })

    return channels


# ==============================================================================
# SMA / ATR / VOLUME MA CALCULATION
# ==============================================================================

def calc_vol_ma(candles: list[dict], period: int = 20) -> list[float | None]:
    """Calculate Simple Moving Average of volume. None for bars before enough data."""
    n = len(candles)
    vmas: list[float | None] = [None] * n
    if n < period:
        return vmas
    window_sum = sum(c["volume"] for c in candles[:period])
    vmas[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += candles[i]["volume"] - candles[i - period]["volume"]
        vmas[i] = window_sum / period
    return vmas


def calc_sma(candles: list[dict], period: int = 200) -> list[float | None]:
    """Calculate Simple Moving Average of close prices. None for bars before enough data."""
    n = len(candles)
    smas: list[float | None] = [None] * n
    if n < period:
        return smas
    window_sum = sum(c["close"] for c in candles[:period])
    smas[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += candles[i]["close"] - candles[i - period]["close"]
        smas[i] = window_sum / period
    return smas

def calc_atr(candles: list[dict], period: int = 14) -> list[float | None]:
    """Calculate Average True Range for each bar. None for bars before enough data."""
    n = len(candles)
    atrs: list[float | None] = [None] * n
    if n < 2:
        return atrs

    trs: list[float] = []
    for i in range(1, n):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    if len(trs) < period:
        return atrs

    atr_val = sum(trs[:period]) / period
    atrs[period] = atr_val
    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        atrs[i + 1] = atr_val

    return atrs


def calc_rsi(candles: list[dict], period: int = 14) -> list[float | None]:
    """Calculate RSI using Wilder's smoothing."""
    n = len(candles)
    rsi = [None] * n
    if n < period + 1:
        return rsi
    gains = []
    losses = []
    for i in range(1, n):
        delta = candles[i]["close"] - candles[i - 1]["close"]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100 - 100 / (1 + rs)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rsi[i + 1] = 100 - 100 / (1 + avg_gain / avg_loss)
    return rsi


# ==============================================================================
# STRATEGY ENGINE (v2 — breakout detection + channel reset + ATR trailing stop)
# ==============================================================================

def run_curved_channel(
    candles: list[dict],
    pivot_left: int = PIVOT_LEFT,
    pivot_right: int = PIVOT_RIGHT,
    max_pivots: int = MAX_PIVOTS,
    degree: int = POLY_DEGREE,
    min_touch: int = MIN_TOUCH_POINTS,
    tolerance_pct: float = TOUCH_TOLERANCE_PCT,
    enable_short: bool = ENABLE_SHORT,
    return_channels: bool = False,
    breakout_pct: float = BREAKOUT_PCT,
    breakout_add_pct: float = BREAKOUT_ADD_PCT,
    atr_trail_mult: float = ATR_TRAIL_MULT,
    short_atr_trail_mult: float = SHORT_ATR_TRAIL_MULT,
    atr_period: int = ATR_PERIOD,
    short_sma_period: int = SHORT_SMA_PERIOD,
    short_min_hold: int = SHORT_MIN_HOLD,
    fallback_sma_period: int = FALLBACK_SMA_PERIOD,
    fallback_wait_bars: int = FALLBACK_WAIT_BARS,
    short_entry_pct: float = SHORT_ENTRY_PCT,
    vol_confirm_mult: float = VOL_CONFIRM_MULT,
    vol_confirm_period: int = VOL_CONFIRM_PERIOD,
    ch_trail_activate_pct: float = CH_TRAIL_ACTIVATE_PCT,
    ch_trail_atr_mult: float = CH_TRAIL_ATR_MULT,
    short_size_base: int = SHORT_SIZE_BASE,
    short_size_scale: float = SHORT_SIZE_SCALE,
    short_size_max: int = SHORT_SIZE_MAX,
    time_exit_bars: int = TIME_EXIT_BARS,
    rsi_div_lookback: int = RSI_DIVERGENCE_LOOKBACK,
    rsi_period: int = RSI_PERIOD,
    ride_expired_winners: bool = RIDE_EXPIRED_WINNERS,
    min_channel_age: int = MIN_CHANNEL_AGE,
    min_extend: int = MIN_EXTEND,
    loss_cooldown_bars: int = LOSS_COOLDOWN_BARS,
) -> list[dict] | tuple[list[dict], list[dict]]:
    """
    Curved channel trading strategy with breakout detection and channel reset.

    v2 additions:
      - Significant breakout (>breakout_pct% beyond channel) invalidates channel
      - Pivots cleared on breakout — new channel requires fresh min_touch pivots
      - ATR trailing stop protects breakout positions during channel-less wait period
      - Upside breakout: close long + re-enter at (100 + breakout_add_pct)% size
      - Downside breakout: sell long + open short, both with pivot reset
    v3 additions:
      - SMA(200) filter: shorts only allowed when price < SMA (set short_sma_period=0 to disable)

    Returns list of trade dicts, or (trades, channels) if return_channels=True.
    """
    if not candles:
        return ([], []) if return_channels else []

    tolerance = tolerance_pct / 100.0
    breakout_thresh = breakout_pct / 100.0
    short_entry_thresh = short_entry_pct / 100.0
    n = len(candles)
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    # Pre-compute ATR for trailing stop and SMA for short filter
    atrs = calc_atr(candles, atr_period)
    smas = calc_sma(candles, short_sma_period) if short_sma_period > 0 else [None] * n
    fallback_smas = calc_sma(candles, fallback_sma_period) if fallback_sma_period > 0 else [None] * n
    vol_mas = calc_vol_ma(candles, vol_confirm_period) if vol_confirm_mult > 0 else [None] * n
    rsi_vals = calc_rsi(candles, rsi_period) if rsi_div_lookback > 0 else [None] * n

    def _short_allowed(bar: int) -> bool:
        """Check if shorting is allowed: enable_short + price < SMA filter."""
        if not enable_short:
            return False
        sma = smas[bar]
        if sma is None:
            return True  # no SMA data yet, allow by default
        return candles[bar]["close"] < sma

    def _volume_confirmed(bar: int) -> bool:
        """Check if volume is above its MA threshold for entry confirmation."""
        if vol_confirm_mult <= 0:
            return True
        vma = vol_mas[bar]
        if vma is None or vma == 0:
            return True
        return candles[bar]["volume"] >= vma * vol_confirm_mult

    def _calc_short_size(price: float, support: float) -> int:
        """Calculate short position size based on break magnitude below support."""
        if support <= 0:
            return short_size_base
        break_pct = (support - price) / support * 100
        size = short_size_base + break_pct * short_size_scale
        return min(int(size), short_size_max)

    # Rolling pivot storage (bar_index, value)
    ph_bars: list[int] = []
    ph_vals: list[float] = []
    pl_bars: list[int] = []
    pl_vals: list[float] = []

    # Channel state
    active_channel: dict | None = None
    all_channels: list[dict] = []
    waiting_for_channel = False

    # Position + trailing stop state
    trades: list[dict] = []
    position: dict | None = None
    trail_stop: float | None = None
    trail_extreme: float | None = None  # trail_high for long, trail_low for short
    ch_trail_stop: float | None = None  # in-channel trailing stop level
    ch_trail_extreme: float | None = None  # in-channel trail extreme
    last_exit_bar: int = -999  # bar index of most recent position exit (for fallback wait)
    last_loss_bar: int = -999  # bar index of most recent losing trade exit (for cooldown)

    def _close_position(date: str, price: float, reason: str, bar: int = 0):
        """Helper to close the current position and append trade."""
        nonlocal position, trail_stop, trail_extreme, ch_trail_stop, ch_trail_extreme, last_exit_bar, last_loss_bar
        if position is None:
            return
        side = position["side"]
        entry_p = position["entry_price"]
        is_loss = (price < entry_p) if side == "long" else (price > entry_p)
        entry_reason = position.get("entry_reason", "unknown")
        entry_versions = position.get("entry_versions", [])
        exit_versions = EXIT_VERSION_MAP.get(reason, [])
        # For short trailing stops, credit v23
        if reason == "atr_trailing_stop" and side == "short":
            exit_versions = ["v2", "v23"]
        trades.append({
            "entry_date": position["entry_date"],
            "entry_price": entry_p,
            "exit_date": date, "exit_price": price,
            "side": side,
            "size_pct": position.get("size_pct", 100),
            "entry_reason": entry_reason,
            "entry_versions": entry_versions,
            "exit_reason": reason,
            "exit_versions": exit_versions,
            "strategy": "curved_channel",
        })
        position = None
        trail_stop = None
        last_exit_bar = bar
        if is_loss:
            last_loss_bar = bar
        trail_extreme = None
        ch_trail_stop = None
        ch_trail_extreme = None

    def _try_fit_channel(confirmed_bar: int) -> bool:
        """Try to fit a channel from current pivots. Returns True if channel found."""
        nonlocal active_channel

        best_ch = None
        best_touches = 0

        # Ascending (HH upper + HL lower)
        asc_hh_b, asc_hh_v = ascending_sequence(ph_bars, ph_vals)
        ah = fit_boundary(asc_hh_b, asc_hh_v, degree, min_touch, tolerance, min_extend=min_extend)
        asc_hl_b, asc_hl_v = ascending_sequence(pl_bars, pl_vals)
        al = fit_boundary(asc_hl_b, asc_hl_v, degree, min_touch, tolerance, min_extend=min_extend)
        if ah is not None and al is not None:
            t = ah["touch_count"] + al["touch_count"]
            if t > best_touches:
                best_ch = {"type": "ascending", "upper": ah, "lower": al}
                best_touches = t

        # Descending (LH upper + LL lower)
        dsc_lh_b, dsc_lh_v = descending_sequence(ph_bars, ph_vals)
        dh = fit_boundary(dsc_lh_b, dsc_lh_v, degree, min_touch, tolerance, min_extend=min_extend)
        dsc_ll_b, dsc_ll_v = descending_sequence(pl_bars, pl_vals)
        dl = fit_boundary(dsc_ll_b, dsc_ll_v, degree, min_touch, tolerance, min_extend=min_extend)
        if dh is not None and dl is not None:
            t = dh["touch_count"] + dl["touch_count"]
            if t > best_touches:
                best_ch = {"type": "descending", "upper": dh, "lower": dl}
                best_touches = t

        if best_ch is not None:
            active_channel = {**best_ch, "confirmed_bar": confirmed_bar}
            all_channels.append({**best_ch, "confirmed_bar": confirmed_bar})
            return True
        return False

    def _reset_pivots_and_channel():
        """Invalidate channel and clear pivot buffers for fresh start."""
        nonlocal active_channel, waiting_for_channel
        active_channel = None
        ph_bars.clear(); ph_vals.clear()
        pl_bars.clear(); pl_vals.clear()
        waiting_for_channel = True

    def _activate_trailing_stop(bar_idx: int, side: str):
        """Set up ATR trailing stop for a breakout position."""
        nonlocal trail_stop, trail_extreme
        atr = atrs[bar_idx]
        if atr is None:
            trail_stop = None
            trail_extreme = None
            return
        if side == "long":
            trail_extreme = candles[bar_idx]["high"]
            trail_stop = trail_extreme - atr * atr_trail_mult
        else:
            trail_extreme = candles[bar_idx]["low"]
            trail_stop = trail_extreme + atr * short_atr_trail_mult

    def _eval_boundary(boundary: dict, bar: int) -> float:
        return poly_eval(boundary["c0"], boundary["c1"], boundary["c2"],
                         boundary["c3"], boundary["origin"], boundary["scale"], bar)

    for i in range(n):
        close = candles[i]["close"]
        opn = candles[i]["open"]
        date = candles[i]["date"]
        atr = atrs[i]

        # ── 1. Pivot detection (confirmed at i - pivot_right) ──
        pivot_bar = i - pivot_right
        new_pivot = False
        if pivot_bar >= pivot_left:
            is_ph = True
            for j in range(pivot_bar - pivot_left, pivot_bar + pivot_right + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if highs[j] >= highs[pivot_bar]:
                    is_ph = False
                    break
            if is_ph:
                ph_bars.append(pivot_bar)
                ph_vals.append(highs[pivot_bar])
                if len(ph_bars) > max_pivots:
                    ph_bars.pop(0); ph_vals.pop(0)
                new_pivot = True

            is_pl = True
            for j in range(pivot_bar - pivot_left, pivot_bar + pivot_right + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if lows[j] <= lows[pivot_bar]:
                    is_pl = False
                    break
            if is_pl:
                pl_bars.append(pivot_bar)
                pl_vals.append(lows[pivot_bar])
                if len(pl_bars) > max_pivots:
                    pl_bars.pop(0); pl_vals.pop(0)
                new_pivot = True

        # ── 2. Channel fitting / refitting ──
        if new_pivot:
            if waiting_for_channel:
                if _try_fit_channel(i):
                    waiting_for_channel = False
                    trail_stop = None
                    trail_extreme = None
            else:
                _try_fit_channel(i)

        # Invalidate expired channel
        if active_channel is not None and not waiting_for_channel:
            lb = active_channel["lower"]
            ub = active_channel["upper"]
            if i > lb["extend_to"] and i > ub["extend_to"]:
                active_channel = None

        # ── 2b. Time-based exit (stale positions with < 1% profit after N bars) ──
        if (position is not None and time_exit_bars > 0
                and (i - position.get("entry_bar", 0)) >= time_exit_bars):
            entry_price = position["entry_price"]
            if position["side"] == "long":
                pnl_pct = (close - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - close) / entry_price * 100
            if pnl_pct < 1.0:
                _close_position(date, close, "time_exit", bar=i)
                continue

        # ── 3. ATR trailing stop (active during channel-less wait period) ──
        if position is not None and waiting_for_channel and trail_stop is not None:
            if position["side"] == "long":
                if atr is not None and trail_extreme is not None:
                    trail_extreme = max(trail_extreme, candles[i]["high"])
                    trail_stop = max(trail_stop, trail_extreme - atr * atr_trail_mult)
                if close <= trail_stop:
                    _close_position(date, close, "atr_trailing_stop", bar=i)
                    continue
            elif position["side"] == "short":
                if atr is not None and trail_extreme is not None:
                    trail_extreme = min(trail_extreme, candles[i]["low"])
                    trail_stop = min(trail_stop, trail_extreme + atr * short_atr_trail_mult)
                if close >= trail_stop:
                    _close_position(date, close, "atr_trailing_stop", bar=i)
                    continue

        # ── 4. Channel-based exit + breakout detection ──
        if position is not None and active_channel is not None and not waiting_for_channel:
            ch_type = active_channel["type"]

            # Check for RSI bearish divergence (price higher high, RSI lower high)
            rsi_divergence = False
            if rsi_div_lookback > 0 and position is not None and position["side"] == "long":
                lookback_start = max(0, i - rsi_div_lookback)
                price_max_bar = lookback_start
                for j in range(lookback_start, i + 1):
                    if candles[j]["high"] > candles[price_max_bar]["high"]:
                        price_max_bar = j
                # Price at current bar is near recent high, but RSI is lower
                if (candles[i]["high"] >= candles[price_max_bar]["high"] * 0.998
                        and rsi_vals[i] is not None and rsi_vals[price_max_bar] is not None
                        and price_max_bar != i
                        and rsi_vals[i] < rsi_vals[price_max_bar] - 3):
                    rsi_divergence = True

            # In-channel trailing stop (locks in gains after profit threshold)
            if ch_trail_activate_pct > 0:
                entry_price = position["entry_price"]
                atr = atrs[i]
                # Tighten trail multiplier by 0.5x if RSI divergence detected
                trail_mult = ch_trail_atr_mult * 0.5 if rsi_divergence else ch_trail_atr_mult
                if position["side"] == "long":
                    pnl_pct = (close - entry_price) / entry_price * 100
                    if pnl_pct >= ch_trail_activate_pct and atr is not None:
                        if ch_trail_extreme is None:
                            ch_trail_extreme = candles[i]["high"]
                            ch_trail_stop = ch_trail_extreme - atr * trail_mult
                        else:
                            ch_trail_extreme = max(ch_trail_extreme, candles[i]["high"])
                            ch_trail_stop = max(ch_trail_stop, ch_trail_extreme - atr * trail_mult)
                    if ch_trail_stop is not None and close <= ch_trail_stop:
                        _close_position(date, close, "channel_trail_stop", bar=i)
                        continue
                elif position["side"] == "short":
                    pnl_pct = (entry_price - close) / entry_price * 100
                    if pnl_pct >= ch_trail_activate_pct and atr is not None:
                        if ch_trail_extreme is None:
                            ch_trail_extreme = candles[i]["low"]
                            ch_trail_stop = ch_trail_extreme + atr * ch_trail_atr_mult
                        else:
                            ch_trail_extreme = min(ch_trail_extreme, candles[i]["low"])
                            ch_trail_stop = min(ch_trail_stop, ch_trail_extreme + atr * ch_trail_atr_mult)
                    if ch_trail_stop is not None and close >= ch_trail_stop:
                        _close_position(date, close, "channel_trail_stop", bar=i)
                        continue

            if position["side"] == "long":
                if ch_type == "ascending":
                    lb = active_channel["lower"]
                    ub = active_channel["upper"]
                    if i >= lb["start_bar"] and i >= ub["start_bar"]:
                        support = _eval_boundary(lb, i)
                        resistance = _eval_boundary(ub, i)

                        # Upside breakout: close > resistance * (1 + breakout%)
                        if close > resistance * (1 + breakout_thresh):
                            _close_position(date, close, "breakout_up", bar=i)
                            new_size = 100 + breakout_add_pct
                            position = {
                                "entry_date": date, "entry_price": close,
                                "entry_bar": i, "side": "long", "size_pct": new_size,
                                "entry_reason": "breakout_reentry",
                                "entry_versions": ["v2"],
                            }
                            _reset_pivots_and_channel()
                            _activate_trailing_stop(i, "long")
                            continue

                        # Downside break: close < support * (1 - tolerance)
                        if close < support * (1 - tolerance):
                            is_breakout = close < support * (1 - breakout_thresh)
                            _close_position(date, close, "breakout_down" if is_breakout else "channel_break", bar=i)
                            # Only open short if break exceeds the higher short_entry threshold
                            if _short_allowed(i) and close < support * (1 - short_entry_thresh):
                                position = {
                                    "entry_date": date, "entry_price": close,
                                    "entry_bar": i, "side": "short", "size_pct": 25,
                                    "entry_reason": "break_short",
                                    "entry_versions": ["v2", "v3"],
                                }
                            if is_breakout:
                                _reset_pivots_and_channel()
                                if position is not None:
                                    _activate_trailing_stop(i, "short")
                            continue

                else:  # long in descending channel — channel flip, exit
                    lb = active_channel["lower"]
                    if i >= lb["start_bar"]:
                        support = _eval_boundary(lb, i)
                        if close < support * (1 - tolerance):
                            _close_position(date, close, "channel_flip", bar=i)
                            continue

            elif position["side"] == "short":
                held_bars = i - position.get("entry_bar", 0)
                if ch_type == "descending":
                    ub = active_channel["upper"]
                    lb = active_channel["lower"]
                    if i >= ub["start_bar"] and i >= lb["start_bar"]:
                        resistance = _eval_boundary(ub, i)
                        support = _eval_boundary(lb, i)

                        # Upside breakout while short — cover (always, regardless of min hold)
                        if close > resistance * (1 + breakout_thresh):
                            _close_position(date, close, "breakout_up", bar=i)
                            _reset_pivots_and_channel()
                            continue

                        # Normal resistance break — cover short (min hold applies)
                        if held_bars >= short_min_hold and close > resistance * (1 + tolerance):
                            _close_position(date, close, "channel_break", bar=i)
                            continue

                        # Downside breakout while short — ride it
                        if close < support * (1 - breakout_thresh):
                            _reset_pivots_and_channel()
                            _activate_trailing_stop(i, "short")
                            continue

                elif ch_type == "ascending":
                    # Ascending channel formed while short — cover (min hold applies)
                    if held_bars >= short_min_hold:
                        lb = active_channel["lower"]
                        if i >= lb["start_bar"]:
                            support = _eval_boundary(lb, i)
                            if close > support:
                                _close_position(date, close, "channel_flip", bar=i)
                                continue

        # Channel expired — close position or let winners ride
        if position is not None and active_channel is None and not waiting_for_channel:
            if not ride_expired_winners:
                _close_position(date, close, "channel_expired", bar=i)
                continue
            entry_price = position["entry_price"]
            if position["side"] == "long":
                pnl = (close - entry_price) / entry_price
            else:
                pnl = (entry_price - close) / entry_price
            if pnl <= 0:
                _close_position(date, close, "channel_expired", bar=i)
                continue
            else:
                # Profitable — keep position open with ATR trailing stop
                _activate_trailing_stop(i, position["side"])
                waiting_for_channel = True

        # ── 5. Entry logic (flat + channel active + not waiting + channel mature enough + cooldown) ──
        channel_age = (i - active_channel.get("confirmed_bar", 0)) if active_channel else 0
        in_cooldown = loss_cooldown_bars > 0 and (i - last_loss_bar) < loss_cooldown_bars
        if position is None and active_channel is not None and not waiting_for_channel and channel_age >= min_channel_age and not in_cooldown:
            ch_type = active_channel["type"]

            if ch_type == "ascending":
                lb = active_channel["lower"]
                ub = active_channel["upper"]
                if i >= lb["start_bar"] and i >= ub["start_bar"] and i > 0:
                    support = _eval_boundary(lb, i)
                    resistance = _eval_boundary(ub, i)
                    # Confirm: previous bar's close was also within channel
                    prev_close = candles[i-1]["close"]
                    prev_support = _eval_boundary(lb, i-1) if i-1 >= lb["start_bar"] else None
                    prev_resist = _eval_boundary(ub, i-1) if i-1 >= ub["start_bar"] else None
                    prev_in_channel = (prev_support is not None and prev_resist is not None
                                       and prev_support <= prev_close <= prev_resist)
                    ch_height = resistance - support
                    # Trend alignment: require close > SMA(50) for longs (when SMA enabled)
                    # Use 90% of SMA as a softer filter (allows entries slightly below SMA)
                    fsma = fallback_smas[i]
                    trend_ok = fsma is None or close > fsma * 0.99
                    if (ch_height > 0 and support <= close <= resistance and close > opn
                            and _volume_confirmed(i) and prev_in_channel and trend_ok):
                        position = {
                            "entry_date": date, "entry_price": close,
                            "entry_bar": i, "side": "long", "size_pct": 100,
                            "entry_reason": "channel_long",
                            "entry_versions": ["v1", "v8", "v21", "v25", "v48"],
                        }

            elif ch_type == "descending" and _short_allowed(i):
                ub = active_channel["upper"]
                lb = active_channel["lower"]
                if i >= ub["start_bar"] and i >= lb["start_bar"]:
                    resistance = _eval_boundary(ub, i)
                    support = _eval_boundary(lb, i)
                    ch_height = resistance - support
                    if (ch_height > 0 and close <= resistance and close >= resistance - ch_height * 0.4
                            and close < opn and _volume_confirmed(i)):
                        position = {
                            "entry_date": date, "entry_price": close,
                            "entry_bar": i, "side": "short", "size_pct": 25,
                            "entry_reason": "channel_short",
                            "entry_versions": ["v3", "v8"],
                        }

        # ── 6. Flat breakout entry (flat + channel + price beyond boundary) ──
        if position is None and active_channel is not None and not waiting_for_channel:
            ch_type = active_channel["type"]
            ub = active_channel["upper"]
            lb = active_channel["lower"]
            if i >= ub["start_bar"] and i >= lb["start_bar"]:
                resistance = _eval_boundary(ub, i)
                support = _eval_boundary(lb, i)

                # Flat + upside breakout → enter long
                if close > resistance * (1 + breakout_thresh):
                    position = {
                        "entry_date": date, "entry_price": close,
                        "entry_bar": i, "side": "long", "size_pct": 100,
                        "entry_reason": "breakout_long",
                        "entry_versions": ["v2"],
                    }
                    _reset_pivots_and_channel()
                    _activate_trailing_stop(i, "long")
                    continue

                # Flat + downside breakout → enter short
                if _short_allowed(i) and close < support * (1 - breakout_thresh):
                    position = {
                        "entry_date": date, "entry_price": close,
                        "entry_bar": i, "side": "short", "size_pct": 25,
                        "entry_reason": "breakout_short",
                        "entry_versions": ["v2", "v3"],
                    }
                    _reset_pivots_and_channel()
                    _activate_trailing_stop(i, "short")
                    continue

        # ── 7. Fallback SMA entry (flat + no channel + waited long enough) ──
        if (position is None and active_channel is None
                and fallback_sma_period > 0
                and (i - last_exit_bar) >= fallback_wait_bars):
            fsma = fallback_smas[i]
            if fsma is not None and close > fsma and close > opn and _volume_confirmed(i):
                position = {
                    "entry_date": date, "entry_price": close,
                    "entry_bar": i, "side": "long", "size_pct": 100,
                    "entry_reason": "fallback_sma",
                    "entry_versions": ["v5"],
                }

        # ── 8. Fallback SMA exit (long from fallback + price drops below SMA) ──
        if (position is not None and position.get("entry_reason") == "fallback_sma"):
            if active_channel is not None and not waiting_for_channel:
                # Channel formed — hand off to channel-based logic
                position["entry_reason"] = "sma_to_channel"
                position["entry_versions"] = ["v5", "v1", "v8", "v21", "v25", "v48"]
            else:
                fsma = fallback_smas[i]
                bars_held = i - position.get("entry_bar", 0)
                if fsma is not None and close < fsma and bars_held >= 3:
                    _close_position(date, close, "fallback_sma_exit", bar=i)
                    continue

    # Close any open position at end of data
    if position is not None:
        _close_position(candles[-1]["date"], candles[-1]["close"], "end_of_data")

    if return_channels:
        return trades, all_channels
    return trades


# ==============================================================================
# OVERLAY BUILDER — convert channels to generic overlay format for visualization
# ==============================================================================

def build_overlays_from_channels(channels: list[dict], candles: list[dict]) -> list[dict]:
    """Convert detected channels to generic overlay dicts for the chart visualizer.

    Shows ALL distinct channels over time. When multiple refits overlap in the same
    time region, keeps the one with the most touch points (best fit). Channels whose
    bar ranges don't overlap are treated as separate (different time periods).
    """
    overlays: list[dict] = []
    n = len(candles)
    if not channels:
        return overlays

    def _ch_range(ch: dict) -> tuple[int, int]:
        """Return (start_bar, extend_to) covering both boundaries."""
        s = min(ch["upper"]["start_bar"], ch["lower"]["start_bar"])
        e = max(ch["upper"]["extend_to"], ch["lower"]["extend_to"])
        return s, e

    def _ch_touches(ch: dict) -> int:
        return ch["upper"]["touch_count"] + ch["lower"]["touch_count"]

    # Deduplicate: group overlapping channels of the same type, keep best per group
    deduped: list[dict] = []
    for ch_type in ("ascending", "descending"):
        typed = [ch for ch in channels if ch["type"] == ch_type]
        if not typed:
            continue
        # Sort by start bar
        typed.sort(key=lambda c: _ch_range(c)[0])
        groups: list[list[dict]] = []
        for ch in typed:
            s, e = _ch_range(ch)
            if groups and _ch_range(groups[-1][-1])[1] >= s:
                # Overlaps with current group
                groups[-1].append(ch)
            else:
                groups.append([ch])
        # Pick best from each group
        for group in groups:
            best = max(group, key=_ch_touches)
            deduped.append(best)

    color_map = {
        ("ascending", "upper"): "#26a69a",   # green for ascending upper
        ("ascending", "lower"): "#2962FF",   # blue for ascending lower (support)
        ("descending", "upper"): "#ef5350",  # red for descending upper (resistance)
        ("descending", "lower"): "#FF9800",  # orange for descending lower
    }

    # Track which labels we've already added to legend (avoid duplicates)
    legend_labels: set[str] = set()

    for ch in deduped:
        for boundary_key in ("upper", "lower"):
            b = ch[boundary_key]
            # Sample polynomial at each bar to create line points
            points = []
            for bar in range(b["start_bar"], min(b["extend_to"] + 1, n)):
                val = poly_eval(b["c0"], b["c1"], b["c2"], b["c3"],
                                b["origin"], b["scale"], bar)
                points.append({"time": candles[bar]["date"], "value": round(val, 4)})

            color = color_map.get((ch["type"], boundary_key), "#787b86")
            label_key = f"{ch['type']} {boundary_key}"
            overlays.append({
                "type": "line",
                "points": points,
                "color": color,
                "label": label_key if label_key not in legend_labels else "",
                "lineWidth": 2,
                "lineStyle": 0,
            })
            legend_labels.add(label_key)

            # Touch points as circle markers
            touch_points = []
            for tb, tv in zip(b["touch_bars"], b["touch_vals"]):
                if tb < n:
                    touch_points.append({"time": candles[tb]["date"], "value": round(tv, 4)})
            if touch_points:
                tp_label = f"{ch['type']} {boundary_key} touches"
                overlays.append({
                    "type": "marker_points",
                    "points": touch_points,
                    "color": "#FFFFFF",
                    "shape": "circle",
                    "label": tp_label if tp_label not in legend_labels else "",
                })
                legend_labels.add(tp_label)

    return overlays


# ==============================================================================
# METRICS & REPORTING
# ==============================================================================

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply transaction costs to each trade. size_pct scales the portfolio impact."""
    total_cost = (commission_pct + slippage_pct) * 2
    result = []
    for t in trades:
        size_pct = t.get("size_pct", 100)
        size_mult = size_pct / 100.0
        if t["side"] == "short":
            gross = (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100
        else:
            gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net = round(gross - total_cost, 3)
        # portfolio_return_pct is the actual impact on total capital
        portfolio_return = round(net * size_mult, 3)
        result.append({
            **t,
            "return_pct": net,
            "portfolio_return_pct": portfolio_return,
            "gross_return_pct": round(gross, 3),
            "cost_pct": round(-total_cost, 3),
        })
    return result


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1d") -> dict:
    """Calculate backtest metrics."""
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "long_trades": 0, "short_trades": 0,
                "channel_break_exits": 0, "channel_expired_exits": 0, "channel_flip_exits": 0,
                "breakout_up_exits": 0, "breakout_down_exits": 0, "atr_trailing_exits": 0,
                "channel_trail_stop_exits": 0, "pyramid_upsize_exits": 0, "time_exit_exits": 0, "fallback_sma_exits": 0, "end_of_data_exits": 0,
                "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252)

    winners = [t for t in trades if t["portfolio_return_pct"] > 0]
    losers  = [t for t in trades if t["portfolio_return_pct"] <= 0]

    capital = initial_capital
    peak    = capital
    max_dd  = 0.0
    returns = []
    for t in trades:
        r = t["portfolio_return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak   = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak * 100)

    total_ret = (capital - initial_capital) / initial_capital * 100
    avg_gain  = sum(t["portfolio_return_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss  = sum(t["portfolio_return_pct"] for t in losers)  / len(losers)  if losers  else 0
    gp        = sum(t["portfolio_return_pct"] for t in winners)
    gl        = abs(sum(t["portfolio_return_pct"] for t in losers))
    pf        = round(gp / gl, 2) if gl > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r  = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / ann) / std_r * math.sqrt(ann), 2)

    wr = len(winners) / len(trades) if trades else 0
    long_count  = sum(1 for t in trades if t["side"] == "long")
    short_count = sum(1 for t in trades if t["side"] == "short")

    return {
        "total_trades":           len(trades),
        "winning_trades":         len(winners),
        "losing_trades":          len(losers),
        "long_trades":            long_count,
        "short_trades":           short_count,
        "channel_break_exits":    sum(1 for t in trades if t.get("exit_reason") == "channel_break"),
        "channel_expired_exits":  sum(1 for t in trades if t.get("exit_reason") == "channel_expired"),
        "channel_flip_exits":     sum(1 for t in trades if t.get("exit_reason") == "channel_flip"),
        "breakout_up_exits":      sum(1 for t in trades if t.get("exit_reason") == "breakout_up"),
        "breakout_down_exits":    sum(1 for t in trades if t.get("exit_reason") == "breakout_down"),
        "atr_trailing_exits":     sum(1 for t in trades if t.get("exit_reason") == "atr_trailing_stop"),
        "channel_trail_stop_exits": sum(1 for t in trades if t.get("exit_reason") == "channel_trail_stop"),
        "pyramid_upsize_exits":   sum(1 for t in trades if t.get("exit_reason") == "pyramid_upsize"),
        "time_exit_exits":        sum(1 for t in trades if t.get("exit_reason") == "time_exit"),
        "fallback_sma_exits":     sum(1 for t in trades if t.get("exit_reason") == "fallback_sma_exit"),
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
    pivot_left: int = PIVOT_LEFT,
    pivot_right: int = PIVOT_RIGHT,
    max_pivots: int = MAX_PIVOTS,
    degree: int = POLY_DEGREE,
    min_touch: int = MIN_TOUCH_POINTS,
    tolerance_pct: float = TOUCH_TOLERANCE_PCT,
    enable_short: bool = ENABLE_SHORT,
    breakout_pct: float = BREAKOUT_PCT,
    breakout_add_pct: float = BREAKOUT_ADD_PCT,
    atr_trail_mult: float = ATR_TRAIL_MULT,
    short_atr_trail_mult: float = SHORT_ATR_TRAIL_MULT,
    atr_period: int = ATR_PERIOD,
    short_sma_period: int = SHORT_SMA_PERIOD,
    short_min_hold: int = SHORT_MIN_HOLD,
    fallback_sma_period: int = FALLBACK_SMA_PERIOD,
    fallback_wait_bars: int = FALLBACK_WAIT_BARS,
    short_entry_pct: float = SHORT_ENTRY_PCT,
    vol_confirm_mult: float = VOL_CONFIRM_MULT,
    vol_confirm_period: int = VOL_CONFIRM_PERIOD,
    ch_trail_activate_pct: float = CH_TRAIL_ACTIVATE_PCT,
    ch_trail_atr_mult: float = CH_TRAIL_ATR_MULT,
    short_size_base: int = SHORT_SIZE_BASE,
    short_size_scale: float = SHORT_SIZE_SCALE,
    short_size_max: int = SHORT_SIZE_MAX,
    time_exit_bars: int = TIME_EXIT_BARS,
    rsi_div_lookback: int = RSI_DIVERGENCE_LOOKBACK,
    rsi_period: int = RSI_PERIOD,
    ride_expired_winners: bool = RIDE_EXPIRED_WINNERS,
    min_channel_age: int = MIN_CHANNEL_AGE,
    min_extend: int = MIN_EXTEND,
    loss_cooldown_bars: int = LOSS_COOLDOWN_BARS,
    include_candles: bool = False,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    result_tuple = run_curved_channel(
        candles, pivot_left, pivot_right, max_pivots,
        degree, min_touch, tolerance_pct, enable_short,
        return_channels=include_candles,
        breakout_pct=breakout_pct, breakout_add_pct=breakout_add_pct,
        atr_trail_mult=atr_trail_mult, short_atr_trail_mult=short_atr_trail_mult,
        atr_period=atr_period,
        short_sma_period=short_sma_period,
        short_min_hold=short_min_hold,
        fallback_sma_period=fallback_sma_period,
        fallback_wait_bars=fallback_wait_bars,
        short_entry_pct=short_entry_pct,
        vol_confirm_mult=vol_confirm_mult,
        vol_confirm_period=vol_confirm_period,
        ch_trail_activate_pct=ch_trail_activate_pct,
        ch_trail_atr_mult=ch_trail_atr_mult,
        short_size_base=short_size_base,
        short_size_scale=short_size_scale,
        short_size_max=short_size_max,
        time_exit_bars=time_exit_bars,
        rsi_div_lookback=rsi_div_lookback,
        rsi_period=rsi_period,
        ride_expired_winners=ride_expired_winners,
        min_channel_age=min_channel_age,
        min_extend=min_extend,
        loss_cooldown_bars=loss_cooldown_bars,
    )
    if include_candles:
        raw_trades, channels = result_tuple
        overlays = build_overlays_from_channels(channels, candles)
    else:
        raw_trades = result_tuple
        overlays = []

    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    result = {
        "symbol": symbol.upper(),
        "strategy": "curved_channel",
        "strategy_label": f"Curved Channel v2 (deg={degree}, touch={min_touch}, breakout={breakout_pct}%)",
        "parameters": {
            "pivot_left": pivot_left,
            "pivot_right": pivot_right,
            "max_pivots": max_pivots,
            "degree": degree,
            "min_touch": min_touch,
            "tolerance_pct": tolerance_pct,
            "enable_short": enable_short,
            "breakout_pct": breakout_pct,
            "breakout_add_pct": breakout_add_pct,
            "atr_trail_mult": atr_trail_mult,
            "atr_period": atr_period,
            "short_sma_period": short_sma_period,
            "short_min_hold": short_min_hold,
            "fallback_sma_period": fallback_sma_period,
            "fallback_wait_bars": fallback_wait_bars,
            "short_entry_pct": short_entry_pct,
            "vol_confirm_mult": vol_confirm_mult,
            "vol_confirm_period": vol_confirm_period,
            "ch_trail_activate_pct": ch_trail_activate_pct,
            "ch_trail_atr_mult": ch_trail_atr_mult,
            "short_size_base": short_size_base,
            "short_size_scale": short_size_scale,
            "short_size_max": short_size_max,
            "time_exit_bars": time_exit_bars,
            "rsi_div_lookback": rsi_div_lookback,
            "rsi_period": rsi_period,
            "ride_expired_winners": ride_expired_winners,
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

    if include_candles:
        result["candles"] = candles
        result["overlays"] = overlays

    return result


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Curved Channel (Polynomial Channel) Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size (default: 1d)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--pivot-left", type=int, default=PIVOT_LEFT, help="Left bars for pivot detection (default: 5)")
    parser.add_argument("--pivot-right", type=int, default=PIVOT_RIGHT, help="Right bars for pivot detection (default: 5)")
    parser.add_argument("--max-pivots", type=int, default=MAX_PIVOTS, help="Max pivots in rolling window (default: 20)")
    parser.add_argument("--degree", type=int, default=POLY_DEGREE, choices=[1, 2, 3],
                        help="Polynomial degree: 1=linear, 2=quadratic, 3=cubic (default: 2)")
    parser.add_argument("--min-touch", type=int, default=MIN_TOUCH_POINTS, help="Min touch points for valid channel (default: 4)")
    parser.add_argument("--tolerance", type=float, default=TOUCH_TOLERANCE_PCT, help="Touch tolerance %% (default: 0.5)")
    parser.add_argument("--no-short", action="store_true", help="Disable short selling")
    parser.add_argument("--chart", action="store_true", help="Generate interactive HTML chart and open in browser")
    args = parser.parse_args()

    enable_short = not args.no_short

    # Asset-specific presets: detect crypto vs ETF
    sym_upper = args.symbol.upper()
    is_crypto = any(tag in sym_upper for tag in ("-USD", "-BTC", "-ETH", "BTC", "ETH", "DOGE", "SOL", "ADA"))
    degree = args.degree
    tolerance = args.tolerance
    if is_crypto:
        fallback_sma = 0       # disable fallback SMA for crypto (too choppy)
        fallback_wait = 10
        short_sma = 0          # no SMA filter for shorts on crypto
        vol_mult = VOL_CONFIRM_MULT  # volume confirmation helps crypto
        ride_expired = True    # let crypto winners ride on expired channels
        ch_age = 0             # no channel age filter for crypto (breakouts are fast)
        breakout_pct = 1.5     # tighter breakout threshold for crypto (bigger moves, earlier detection)
        min_ext = 30           # longer channel extension for crypto (volatile, needs more room)
        atr_pd = ATR_PERIOD    # keep ATR(14) for crypto too
        time_exit = TIME_EXIT_BARS   # default 20 for crypto
        ch_trail_act = CH_TRAIL_ACTIVATE_PCT  # default 2.0% for crypto
        short_hold = SHORT_MIN_HOLD  # default 5 for crypto
    else:
        fallback_sma = FALLBACK_SMA_PERIOD
        fallback_wait = FALLBACK_WAIT_BARS
        short_sma = SHORT_SMA_PERIOD
        vol_mult = VOL_CONFIRM_MULT
        ride_expired = RIDE_EXPIRED_WINNERS
        ch_age = MIN_CHANNEL_AGE  # filter out immature channels for ETFs
        breakout_pct = BREAKOUT_PCT  # default 2.0% for ETFs
        min_ext = MIN_EXTEND         # default 20 bars for ETFs
        atr_pd = ATR_PERIOD          # default 14 bars for ETFs
        time_exit = TIME_EXIT_BARS   # default 20 for ETFs
        ch_trail_act = CH_TRAIL_ACTIVATE_PCT  # default 2.0% for ETFs
        short_hold = SHORT_MIN_HOLD  # default 5 for ETFs

    preset_label = "crypto" if is_crypto else "etf"
    print(f"\n{'='*60}")
    print(f"  Curved Channel Strategy v7 — {args.symbol} [{preset_label} preset]")
    print(f"  Degree: {degree}  |  Touch: {args.min_touch}  |  Tolerance: {tolerance}%")
    print(f"  Pivots: L={args.pivot_left} R={args.pivot_right}  |  Max: {args.max_pivots}")
    print(f"  Breakout: {breakout_pct}%  |  Add: {BREAKOUT_ADD_PCT}%  |  ATR Trail: {ATR_TRAIL_MULT}x ({ATR_PERIOD})")
    print(f"  Fallback SMA: {fallback_sma or 'OFF'}  |  Short SMA: {short_sma or 'OFF'}  |  Shorts: {'ON' if enable_short else 'OFF'}")
    print(f"  Vol Confirm: {'ON' if vol_mult > 0 else 'OFF'}  |  Ride Expired: {'ON' if ride_expired else 'OFF'}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_left=args.pivot_left, pivot_right=args.pivot_right,
        max_pivots=args.max_pivots, degree=degree,
        min_touch=args.min_touch, tolerance_pct=tolerance,
        enable_short=enable_short,
        breakout_pct=breakout_pct,
        fallback_sma_period=fallback_sma, fallback_wait_bars=fallback_wait,
        short_sma_period=short_sma,
        vol_confirm_mult=vol_mult,
        ride_expired_winners=ride_expired,
        min_channel_age=ch_age,
        min_extend=min_ext,
        atr_period=atr_pd,
        time_exit_bars=time_exit,
        ch_trail_activate_pct=ch_trail_act,
        short_min_hold=short_hold,
        include_candles=args.chart,
    )

    print(f"  Period:           {result['date_from']} -> {result['date_to']} ({result['candles_analyzed']} bars)")
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
    print(f"  Exits:            Break: {result['channel_break_exits']}  |  Expired: {result['channel_expired_exits']}  |  Flip: {result['channel_flip_exits']}")
    print(f"                    Breakout Up: {result['breakout_up_exits']}  |  Breakout Down: {result['breakout_down_exits']}  |  ATR Trail: {result['atr_trailing_exits']}  |  Ch Trail: {result['channel_trail_stop_exits']}  |  SMA Fallback: {result['fallback_sma_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        size = t.get("size_pct", 100)
        size_tag = f" ({size}%)" if size != 100 else ""
        print(f"    {side:5s}{size_tag:6s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['portfolio_return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent

    # Save JSON (exclude candles to keep file small)
    json_result = {k: v for k, v in result.items() if k not in ("candles", "overlays")}
    fname = script_dir / f"curved_channel_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")

    # Generate interactive chart
    if args.chart:
        import sys
        import webbrowser
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from visualize import generate_chart_html

        chart_path = script_dir / f"curved_channel_chart_{args.symbol.replace('-','_')}_{args.period}.html"
        generate_chart_html(result, result["candles"], chart_path)
        print(f"  Chart saved to: {chart_path}")
        webbrowser.open(chart_path.as_uri())


if __name__ == "__main__":
    main()
