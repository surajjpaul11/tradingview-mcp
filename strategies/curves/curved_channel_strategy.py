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
ENABLE_SHORT         = True    # enable short positions
INTERVAL             = "1d"    # candle size (1d works best for channels)
PERIOD               = "2y"    # data lookback
INITIAL_CAPITAL      = 10_000.0
COMMISSION_PCT       = 0.1
SLIPPAGE_PCT         = 0.05


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
                 degree: int, min_touch: int, tolerance: float
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
    extend_to = end_bar + max(gap, 10)

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
                    tolerance: float) -> list[dict]:
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
                ah = fit_boundary(asc_hh_b, asc_hh_v, degree, min_touch, tolerance)

                # Ascending Higher Lows (lower)
                asc_hl_b, asc_hl_v = ascending_sequence(pl_bars, pl_vals)
                al = fit_boundary(asc_hl_b, asc_hl_v, degree, min_touch, tolerance)

                # Descending Lower Highs (upper)
                dsc_lh_b, dsc_lh_v = descending_sequence(ph_bars, ph_vals)
                dh = fit_boundary(dsc_lh_b, dsc_lh_v, degree, min_touch, tolerance)

                # Descending Lower Lows (lower)
                dsc_ll_b, dsc_ll_v = descending_sequence(pl_bars, pl_vals)
                dl = fit_boundary(dsc_ll_b, dsc_ll_v, degree, min_touch, tolerance)

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
# STRATEGY ENGINE
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
) -> list[dict]:
    """
    Curved channel trading strategy.

    States:
      - "flat": no position — look for channel bounce entry
      - "long": holding long — watch for ascending lower boundary break to exit
      - "short": (if enabled) holding short — watch for descending upper boundary break to exit

    Entry signals:
      - Long: price near ascending lower boundary AND bouncing up (close > open)
      - Short: price near descending upper boundary AND rejecting down (close < open)

    Exit signals:
      - Long exit: close breaks below ascending lower boundary by > tolerance
      - Short exit: close breaks above descending upper boundary by > tolerance
      - Channel invalidation (extend_to bar passed)
      - End of data

    Returns list of trade dicts.
    """
    if not candles:
        return []

    tolerance = tolerance_pct / 100.0
    n = len(candles)

    # Build channel state: for each bar, track the latest valid channel
    channels = detect_channels(candles, pivot_left, pivot_right, max_pivots,
                               degree, min_touch, tolerance)

    # Index channels by confirmed_bar for quick lookup
    # Keep track of latest ascending and descending channels
    latest_asc: dict | None = None
    latest_dsc: dict | None = None
    ch_idx = 0

    trades: list[dict] = []
    position: dict | None = None

    for i in range(n):
        close = candles[i]["close"]
        opn = candles[i]["open"]
        high = candles[i]["high"]
        low = candles[i]["low"]
        date = candles[i]["date"]

        # Update latest channels
        while ch_idx < len(channels) and channels[ch_idx]["confirmed_bar"] <= i:
            ch = channels[ch_idx]
            if ch["type"] == "ascending":
                latest_asc = ch
            else:
                latest_dsc = ch
            ch_idx += 1

        # Invalidate expired channels
        if latest_asc is not None:
            if i > latest_asc["lower"]["extend_to"] and i > latest_asc["upper"]["extend_to"]:
                latest_asc = None
        if latest_dsc is not None:
            if i > latest_dsc["lower"]["extend_to"] and i > latest_dsc["upper"]["extend_to"]:
                latest_dsc = None

        # --- Exit logic ---
        if position is not None:
            if position["side"] == "long" and latest_asc is not None:
                lb = latest_asc["lower"]
                if i >= lb["start_bar"] and i <= lb["extend_to"]:
                    support = poly_eval(lb["c0"], lb["c1"], lb["c2"], lb["c3"],
                                        lb["origin"], lb["scale"], i)
                    # Break below support
                    if close < support * (1 - tolerance):
                        trades.append({
                            "entry_date": position["entry_date"],
                            "entry_price": position["entry_price"],
                            "exit_date": date,
                            "exit_price": close,
                            "side": "long",
                            "exit_reason": "channel_break",
                            "strategy": "curved_channel",
                        })
                        position = None

            elif position["side"] == "long" and latest_asc is None:
                # Channel expired — exit
                trades.append({
                    "entry_date": position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date": date,
                    "exit_price": close,
                    "side": "long",
                    "exit_reason": "channel_expired",
                    "strategy": "curved_channel",
                })
                position = None

            elif position["side"] == "short" and latest_dsc is not None:
                ub = latest_dsc["upper"]
                if i >= ub["start_bar"] and i <= ub["extend_to"]:
                    resistance = poly_eval(ub["c0"], ub["c1"], ub["c2"], ub["c3"],
                                           ub["origin"], ub["scale"], i)
                    # Break above resistance
                    if close > resistance * (1 + tolerance):
                        trades.append({
                            "entry_date": position["entry_date"],
                            "entry_price": position["entry_price"],
                            "exit_date": date,
                            "exit_price": close,
                            "side": "short",
                            "exit_reason": "channel_break",
                            "strategy": "curved_channel",
                        })
                        position = None

            elif position["side"] == "short" and latest_dsc is None:
                trades.append({
                    "entry_date": position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date": date,
                    "exit_price": close,
                    "side": "short",
                    "exit_reason": "channel_expired",
                    "strategy": "curved_channel",
                })
                position = None

        # --- Entry logic (only if flat) ---
        if position is None:
            # Long entry: ascending channel — price inside channel, above support
            if latest_asc is not None:
                lb = latest_asc["lower"]
                ub = latest_asc["upper"]
                in_lower = i >= lb["start_bar"] and i <= lb["extend_to"]
                in_upper = i >= ub["start_bar"] and i <= ub["extend_to"]
                if in_lower and in_upper:
                    support = poly_eval(lb["c0"], lb["c1"], lb["c2"], lb["c3"],
                                        lb["origin"], lb["scale"], i)
                    resistance = poly_eval(ub["c0"], ub["c1"], ub["c2"], ub["c3"],
                                           ub["origin"], ub["scale"], i)
                    channel_height = resistance - support
                    # Enter long when price is in lower third of channel and bullish
                    if channel_height > 0 and close >= support and close <= support + channel_height * 0.4 and close > opn:
                        position = {
                            "entry_date": date,
                            "entry_price": close,
                            "entry_bar": i,
                            "side": "long",
                        }

            # Short entry: descending channel — price in upper third and bearish
            if position is None and enable_short and latest_dsc is not None:
                ub = latest_dsc["upper"]
                lb = latest_dsc["lower"]
                in_upper = i >= ub["start_bar"] and i <= ub["extend_to"]
                in_lower = i >= lb["start_bar"] and i <= lb["extend_to"]
                if in_upper and in_lower:
                    resistance = poly_eval(ub["c0"], ub["c1"], ub["c2"], ub["c3"],
                                           ub["origin"], ub["scale"], i)
                    support = poly_eval(lb["c0"], lb["c1"], lb["c2"], lb["c3"],
                                        lb["origin"], lb["scale"], i)
                    channel_height = resistance - support
                    if channel_height > 0 and close <= resistance and close >= resistance - channel_height * 0.4 and close < opn:
                        position = {
                            "entry_date": date,
                            "entry_price": close,
                            "entry_bar": i,
                            "side": "short",
                        }

    # Close any open position at end of data
    if position is not None:
        trades.append({
            "entry_date": position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date": candles[-1]["date"],
            "exit_price": candles[-1]["close"],
            "side": position["side"],
            "exit_reason": "end_of_data",
            "strategy": "curved_channel",
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
        if t["side"] == "short":
            gross = (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100
        else:
            gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net = round(gross - total_cost, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3), "cost_pct": round(-total_cost, 3)})
    return result


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1d") -> dict:
    """Calculate backtest metrics."""
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "long_trades": 0, "short_trades": 0,
                "channel_break_exits": 0, "channel_expired_exits": 0, "end_of_data_exits": 0,
                "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252)

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
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    raw_trades = run_curved_channel(
        candles, pivot_left, pivot_right, max_pivots,
        degree, min_touch, tolerance_pct, enable_short,
    )
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "curved_channel",
        "strategy_label": f"Curved Channel (deg={degree}, touch={min_touch}, tol={tolerance_pct}%)",
        "parameters": {
            "pivot_left": pivot_left,
            "pivot_right": pivot_right,
            "max_pivots": max_pivots,
            "degree": degree,
            "min_touch": min_touch,
            "tolerance_pct": tolerance_pct,
            "enable_short": enable_short,
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
    args = parser.parse_args()

    enable_short = not args.no_short

    print(f"\n{'='*60}")
    print(f"  Curved Channel Strategy — {args.symbol}")
    print(f"  Degree: {args.degree}  |  Touch: {args.min_touch}  |  Tolerance: {args.tolerance}%")
    print(f"  Pivots: L={args.pivot_left} R={args.pivot_right}  |  Max: {args.max_pivots}")
    print(f"  Interval: {args.interval}  |  Shorts: {'ON' if enable_short else 'OFF'}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_left=args.pivot_left, pivot_right=args.pivot_right,
        max_pivots=args.max_pivots, degree=args.degree,
        min_touch=args.min_touch, tolerance_pct=args.tolerance,
        enable_short=enable_short,
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
    print(f"  Exits:            Channel Break: {result['channel_break_exits']}  |  Expired: {result['channel_expired_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    fname = script_dir / f"curved_channel_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
