"""
Sloped Lines Strategy — Standalone Python Implementation
==========================================================

Alternating trendline breakout strategy.

The idea is simple:
  - When price is falling, draw a DESCENDING line connecting two recent
    swing highs (lower highs). As long as price stays below, stay out.
    When price BREAKS ABOVE this line → BUY.

  - When holding, draw an ASCENDING line connecting two recent swing lows
    (higher lows). As long as price stays above, keep holding.
    When price BREAKS BELOW this line → SELL.

Visual reference:
  Green lines = descending resistance (lower highs) — break above = buy
  Blue lines  = ascending support (higher lows) — break below = sell

Usage:
  python sloped_lines_strategy.py                                 # defaults: SPY, 2y, 1h
  python sloped_lines_strategy.py --symbol BTC-USD --period 1y
  python sloped_lines_strategy.py --symbol AAPL --enable-short
  python sloped_lines_strategy.py --symbol NVDA --trendline-tolerance 0.01

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

PIVOT_LOOKBACK       = 5       # bars left/right for swing point detection
TRENDLINE_TOLERANCE  = 0.015   # 1.5% tolerance for validation (nothing breaks through)
CONFIRM_BARS         = 1       # consecutive bars to confirm a breakout
ENABLE_SHORT         = False   # enable short positions on support break
USE_WICK             = False   # use wicks for line contacts (default False: body only)
INTERVAL             = "1h"    # candle size
PERIOD               = "2y"    # data lookback
INITIAL_CAPITAL      = 10_000.0
COMMISSION_PCT       = 0.1
SLIPPAGE_PCT         = 0.05
DEFAULT_LINE_ANGLE   = 3.0     # default minimum percentage angle/slope threshold
DEFAULT_STOP_LOSS_MODE = "exit_peak_reclaim"  # default stop loss behavior
DEFAULT_FULL_CANDLE  = False   # default breakout confirmation (default False: touch break)


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1h") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    fetch_interval = "1h" if interval == "12h" else interval
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={fetch_interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "sloped-lines-strategy/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval in ("1h", "4h", "12h", "30m", "15m", "5m") else "%Y-%m-%d"

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

    # Synthesize 12h if requested
    if interval == "12h" and candles:
        grouped = []
        chunk = []
        for c in candles:
            chunk.append(c)
            if len(chunk) == 12:
                grouped.append({
                    "date": chunk[0]["date"],
                    "open": chunk[0]["open"],
                    "high": max(x["high"] for x in chunk),
                    "low": min(x["low"] for x in chunk),
                    "close": chunk[-1]["close"],
                    "volume": sum(x["volume"] for x in chunk),
                })
                chunk = []
        if chunk:
            grouped.append({
                "date": chunk[0]["date"],
                "open": chunk[0]["open"],
                "high": max(x["high"] for x in chunk),
                "low": min(x["low"] for x in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(x["volume"] for x in chunk),
            })
        candles = grouped

    return candles


# ==============================================================================
# SWING POINT DETECTION
# ==============================================================================

def find_swings(highs: list[float], lows: list[float], lookback: int = 5
                ) -> tuple[list[tuple[int, float, int]], list[tuple[int, float, int]]]:
    """
    Detect swing highs and swing lows via pivot logic.

    Returns:
      swing_highs: list of (bar_index, price, confirmed_at_bar)
      swing_lows:  list of (bar_index, price, confirmed_at_bar)

    A swing high at bar i is confirmed once we've seen `lookback` bars after it.
    """
    n = len(highs)
    swing_highs: list[tuple[int, float, int]] = []
    swing_lows: list[tuple[int, float, int]] = []

    for i in range(lookback, n - lookback):
        window = range(i - lookback, i + lookback + 1)

        if all(highs[i] >= highs[j] for j in window):
            swing_highs.append((i, highs[i], i + lookback))

        if all(lows[i] <= lows[j] for j in window):
            swing_lows.append((i, lows[i], i + lookback))

    return swing_highs, swing_lows


# ==============================================================================
# TRENDLINE HELPERS
# ==============================================================================

def trendline_value(anchor1: tuple[int, float], anchor2: tuple[int, float], bar: int) -> float:
    """Calculate the projected trendline value at a given bar index."""
    b1, p1 = anchor1
    b2, p2 = anchor2
    if b2 == b1:
        return p1
    slope = (p2 - p1) / (b2 - b1)
    return p1 + slope * (bar - b1)


def is_green_candle(c: dict) -> bool:
    """Return True if candle is green/bullish (close >= open)."""
    return c["close"] >= c["open"]

def is_red_candle(c: dict) -> bool:
    """Return True if candle is red/bearish (close < open)."""
    return c["close"] < c["open"]


def calc_atr(candles: list[dict], period: int = 14) -> list[float]:
    """Calculate Average True Range (ATR) across candles."""
    if not candles:
        return []
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    tr = [highs[0] - lows[0]]
    for i in range(1, len(candles)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr = []
    for i in range(len(candles)):
        if i < period:
            atr.append(sum(tr[:i + 1]) / (i + 1))
        else:
            atr.append((atr[-1] * (period - 1) + tr[i]) / period)
    return atr


# ==============================================================================
# LINE CONSTRUCTION WITH VALIDATION
# ==============================================================================

def build_descending_resistance(
    confirmed_highs: list[tuple[int, float]],
    closes: list[float],
    search_after_bar: int = 0,
    exit_point: tuple[int, float] | None = None,
    candidate_highs: list[tuple[int, float]] | None = None,
    current_bar: int | None = None,
    tolerance: float = TRENDLINE_TOLERANCE,
    min_anchor_bars: int = 4,
    candles: list[dict] | None = None,
    inverse_color_trigger: bool = False,
    line_angle: float = 3.0,
) -> dict | None:
    """
    Build a descending resistance line from two swing highs (lower highs) or candle tops.
    If exit_point (sell_bar, high_price) is provided, it serves as the initial resistance anchor (Anchor 1).
    Anchor 2 can be formed by confirmed swing highs or subsequent candle tops.

    If inverse_color_trigger is True:
      - Anchor 1 (start) MUST be a red candle (close <= open).
      - Anchor 2 (end) MUST be a green candle (close >= open).

    If line_angle > 0.0:
      - Anchor percentage drop ( (a1[1] - a2[1]) / a1[1] * 100 ) must be >= line_angle.

    Validation: no candle close between anchor1 and anchor2 is above the line
    (within tolerance). This ensures the line truly acts as resistance that
    nothing has broken through.

    Returns trendline dict with anchor points, or None if no valid line found.
    """
    # If exit_point is provided, Anchor 1 is fixed at the sell candle high (if red or if not inverse_color)
    if exit_point is not None:
        a1 = exit_point
        is_a1_valid = True
        if inverse_color_trigger and candles is not None and a1[0] < len(candles):
            if not is_red_candle(candles[a1[0]]):
                is_a1_valid = False

        if is_a1_valid:
            eligible_a2 = [p for p in confirmed_highs if p[0] >= a1[0] + min_anchor_bars and p[1] < a1[1]]
            if candidate_highs:
                for p in candidate_highs:
                    if p[0] >= a1[0] + min_anchor_bars and p[1] < a1[1] and p not in eligible_a2:
                        eligible_a2.append(p)
            eligible_a2.sort(key=lambda x: x[0])

            best = None
            for a2 in eligible_a2:
                # Must be descending (lower highs)
                if a2[1] >= a1[1]:
                    continue

                # Must meet minimum line angle (percentage fall from anchor1 to anchor2)
                if line_angle > 0.0 and (a1[1] - a2[1]) / a1[1] * 100.0 < line_angle:
                    continue

                # Anchor 2 must be green if inverse_color_trigger
                if inverse_color_trigger and candles is not None and a2[0] < len(candles):
                    if not is_green_candle(candles[a2[0]]):
                        continue

                # Validate: no close between a1 and a2 is above the line
                valid = True
                for bar in range(a1[0] + 1, min(a2[0], len(closes))):
                    if bar < 0 or bar >= len(closes):
                        continue
                    projected = trendline_value(a1, a2, bar)
                    if projected <= 0:
                        continue
                    if closes[bar] > projected * (1 + tolerance):
                        valid = False
                        break

                # Line must still hold at the current evaluation bar
                if valid and current_bar is not None and current_bar < len(closes):
                    p_now = trendline_value(a1, a2, current_bar)
                    if p_now > 0 and closes[current_bar] > p_now * (1 + tolerance):
                        valid = False

                if valid:
                    line = {
                        "type": "resistance",
                        "direction": "descending",
                        "anchor1": a1,
                        "anchor2": a2,
                        "confirmed_at_bar": a2[0],
                    }
                    if best is None or a2[0] > best["anchor2"][0]:
                        best = line

            if best is not None:
                return best

    # Otherwise, search across confirmed / candidate highs after search point
    eligible = [(b, p) for b, p in confirmed_highs if b >= search_after_bar]
    if candidate_highs:
        for p in candidate_highs:
            if p[0] >= search_after_bar and p not in eligible:
                eligible.append(p)
    eligible.sort(key=lambda x: x[0])
    if len(eligible) < 2:
        return None

    best = None
    for i in range(len(eligible) - 2, -1, -1):
        a1 = eligible[i]
        if inverse_color_trigger and candles is not None and a1[0] < len(candles):
            if not is_red_candle(candles[a1[0]]):
                continue

        for j in range(i + 1, len(eligible)):
            a2 = eligible[j]

            if a2[0] < a1[0] + min_anchor_bars:
                continue

            if a2[1] >= a1[1]:
                continue

            # Must meet minimum line angle (percentage fall from anchor1 to anchor2)
            if line_angle > 0.0 and (a1[1] - a2[1]) / a1[1] * 100.0 < line_angle:
                continue

            if inverse_color_trigger and candles is not None and a2[0] < len(candles):
                if not is_green_candle(candles[a2[0]]):
                    continue

            valid = True
            for bar in range(a1[0] + 1, min(a2[0], len(closes))):
                if bar < 0 or bar >= len(closes):
                    continue
                projected = trendline_value(a1, a2, bar)
                if projected <= 0:
                    continue
                if closes[bar] > projected * (1 + tolerance):
                    valid = False
                    break

            if valid and current_bar is not None and current_bar < len(closes):
                p_now = trendline_value(a1, a2, current_bar)
                if p_now > 0 and closes[current_bar] > p_now * (1 + tolerance):
                    valid = False

            if valid:
                line = {
                    "type": "resistance",
                    "direction": "descending",
                    "anchor1": a1,
                    "anchor2": a2,
                    "confirmed_at_bar": a2[0],
                }
                if best is None:
                    best = line
                else:
                    if line["anchor2"][0] > best["anchor2"][0]:
                        best = line
                    elif line["anchor2"][0] == best["anchor2"][0] and line["anchor1"][0] > best["anchor1"][0]:
                        best = line

            if best is not None and best["anchor1"] == eligible[i]:
                break

    return best


def build_ascending_support(
    confirmed_lows: list[tuple[int, float]],
    closes: list[float],
    search_after_bar: int = 0,
    entry_point: tuple[int, float] | None = None,
    candidate_lows: list[tuple[int, float]] | None = None,
    current_bar: int | None = None,
    tolerance: float = TRENDLINE_TOLERANCE,
    min_anchor_bars: int = 4,
    candles: list[dict] | None = None,
    inverse_color_trigger: bool = False,
    line_angle: float = 3.0,
) -> dict | None:
    """
    Build an ascending support line from two swing lows (higher lows) or candle bottoms.
    If entry_point (buy_bar, low_price) is provided, it serves as the initial support anchor (Anchor 1).
    Anchor 2 can be formed by confirmed swing lows or subsequent candle bottoms.

    If inverse_color_trigger is True:
      - Anchor 1 (start) MUST be a green candle (close >= open).
      - Anchor 2 (end) MUST be a red candle (close < open). "Let's not use green candles to end the blue support line."

    If line_angle > 0.0:
      - Anchor percentage rise ( (a2[1] - a1[1]) / a1[1] * 100 ) must be >= line_angle.

    Validation: no candle close between anchor1 and anchor2 is below the line
    (within tolerance). This ensures the line truly acts as support that
    nothing has broken through.

    Returns trendline dict with anchor points, or None if no valid line found.
    """
    # If entry_point is provided, Anchor 1 is fixed at the buy candle low (if green or if not inverse_color)
    if entry_point is not None:
        a1 = entry_point
        is_a1_valid = True
        if inverse_color_trigger and candles is not None and a1[0] < len(candles):
            if not is_green_candle(candles[a1[0]]):
                is_a1_valid = False

        if is_a1_valid:
            eligible_a2 = [p for p in confirmed_lows if p[0] >= a1[0] + min_anchor_bars and p[1] > a1[1]]
            if candidate_lows:
                for p in candidate_lows:
                    if p[0] >= a1[0] + min_anchor_bars and p[1] > a1[1] and p not in eligible_a2:
                        eligible_a2.append(p)
            eligible_a2.sort(key=lambda x: x[0])

            best = None
            for a2 in eligible_a2:
                # Must be ascending (higher lows)
                if a2[1] <= a1[1]:
                    continue

                # Must meet minimum line angle (percentage rise from anchor1 to anchor2)
                if line_angle > 0.0 and (a2[1] - a1[1]) / a1[1] * 100.0 < line_angle:
                    continue

                # Anchor 2 must be red if inverse_color_trigger
                if inverse_color_trigger and candles is not None and a2[0] < len(candles):
                    if not is_red_candle(candles[a2[0]]):
                        continue

                # Validate: no close between a1 and a2 is below the line
                valid = True
                for bar in range(a1[0] + 1, min(a2[0], len(closes))):
                    if bar < 0 or bar >= len(closes):
                        continue
                    projected = trendline_value(a1, a2, bar)
                    if projected <= 0:
                        continue
                    if closes[bar] < projected * (1 - tolerance):
                        valid = False
                        break

                # Line must still hold at the current evaluation bar
                if valid and current_bar is not None and current_bar < len(closes):
                    p_now = trendline_value(a1, a2, current_bar)
                    if p_now > 0 and closes[current_bar] < p_now * (1 - tolerance):
                        valid = False

                if valid:
                    line = {
                        "type": "support",
                        "direction": "ascending",
                        "anchor1": a1,
                        "anchor2": a2,
                        "confirmed_at_bar": a2[0],
                    }
                    if best is None or a2[0] > best["anchor2"][0]:
                        best = line

            if best is not None:
                return best

    # Otherwise, search across confirmed / candidate lows after search point
    eligible = [(b, p) for b, p in confirmed_lows if b >= search_after_bar]
    if candidate_lows:
        for p in candidate_lows:
            if p[0] >= search_after_bar and p not in eligible:
                eligible.append(p)
    eligible.sort(key=lambda x: x[0])
    if len(eligible) < 2:
        return None

    best = None
    for i in range(len(eligible) - 2, -1, -1):
        a1 = eligible[i]
        if inverse_color_trigger and candles is not None and a1[0] < len(candles):
            if not is_green_candle(candles[a1[0]]):
                continue

        for j in range(i + 1, len(eligible)):
            a2 = eligible[j]

            if a2[0] < a1[0] + min_anchor_bars:
                continue

            if a2[1] <= a1[1]:
                continue

            # Must meet minimum line angle (percentage rise from anchor1 to anchor2)
            if line_angle > 0.0 and (a2[1] - a1[1]) / a1[1] * 100.0 < line_angle:
                continue

            if inverse_color_trigger and candles is not None and a2[0] < len(candles):
                if not is_red_candle(candles[a2[0]]):
                    continue

            valid = True
            for bar in range(a1[0] + 1, min(a2[0], len(closes))):
                if bar < 0 or bar >= len(closes):
                    continue
                projected = trendline_value(a1, a2, bar)
                if projected <= 0:
                    continue
                if closes[bar] < projected * (1 - tolerance):
                    valid = False
                    break

            if valid and current_bar is not None and current_bar < len(closes):
                p_now = trendline_value(a1, a2, current_bar)
                if p_now > 0 and closes[current_bar] < p_now * (1 - tolerance):
                    valid = False

            if valid:
                line = {
                    "type": "support",
                    "direction": "ascending",
                    "anchor1": a1,
                    "anchor2": a2,
                    "confirmed_at_bar": a2[0],
                }
                if best is None:
                    best = line
                else:
                    if line["anchor2"][0] > best["anchor2"][0]:
                        best = line
                    elif line["anchor2"][0] == best["anchor2"][0] and line["anchor1"][0] > best["anchor1"][0]:
                        best = line

            if best is not None and best["anchor1"] == eligible[i]:
                break

    return best


# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_sloped_lines(
    candles: list[dict],
    pivot_lookback: int = PIVOT_LOOKBACK,
    trendline_tolerance: float = TRENDLINE_TOLERANCE,
    confirm_bars: int = CONFIRM_BARS,
    enable_short: bool = ENABLE_SHORT,
    full_candle: bool = DEFAULT_FULL_CANDLE,
    use_wick: bool = False,
    confirm_candles: int = 0,
    inverse_color_trigger: bool = False,
    line_angle: float = 3.0,
    stop_loss_mode: str = "exit_peak_reclaim",
) -> tuple[list[dict], list[dict]]:
    """
    Sloped Lines strategy — alternating trendline breakout.

    States:
      - "waiting_for_buy": out of market, watching descending resistance for
                           upward break → buy
      - "holding":         long position, watching ascending support for
                           downward break → sell
      - "short" (optional): short position, watching descending resistance for
                             upward break → cover + buy

    Parameters:
      - full_candle: If True, requires the candle to CLOSE across the trendline (close breakout).
                     If False, touching/piercing with high/low triggers the breakout (wick/touch break).
      - use_wick: If True, uses candle wicks (high/low) for line contact points.
                  If False (default), uses ONLY candle bodies (max/min of open/close).
      - confirm_candles: Number of additional supporting candles in the same direction required
                         to confirm the breakout buy (0 = immediate buy on breakout, 1, 2, 3).
      - inverse_color_trigger: If True, ascending support lines can only start on a green candle
                               and end on a red candle; descending resistance lines can only start
                               on a red candle and end on a green candle.
      - line_angle: Minimum percentage slope/angle threshold between anchors (0.0, 2.0, 3.0, 5.0, 8.0).
                    Lines with anchor rise/fall below this threshold are not formed.
      - stop_loss_mode: "none" (default), "exit_peak_reclaim", "barrier_trap_reentry", "atr_stop_buffer".

    Returns:
      (trades, trendlines) — trades is a list of trade dicts,
                              trendlines is a list of line dicts for visualization
    """
    if not candles:
        return [], []

    highs  = [c["high"] if use_wick else max(c["open"], c["close"]) for c in candles]
    lows   = [c["low"] if use_wick else min(c["open"], c["close"]) for c in candles]
    closes = [c["close"] for c in candles]
    atr    = calc_atr(candles, 14)

    # --- Find all swings ---
    swing_highs, swing_lows = find_swings(highs, lows, pivot_lookback)

    # --- Progressive confirmation tracking ---
    confirmed_highs: list[tuple[int, float]] = []
    confirmed_lows:  list[tuple[int, float]] = []
    sh_ptr = sl_ptr = 0

    # --- State ---
    trades: list[dict] = []
    trendlines: list[dict] = []  # for visualization
    position: dict | None = None
    active_trendline: dict | None = None

    # After a trendline breaks, look for new swings after this bar
    search_after_bar: int = 0

    # Track breakout confirmation candles
    break_start_bar: int | None = None
    confirm_count: int = 0

    # State: "waiting_for_buy", "holding", "short"
    state: str = "waiting_for_buy"
    last_sell_point: tuple[int, float] | None = None
    trap_info: dict | None = None

    for i in range(len(candles)):
        date  = candles[i]["date"]
        price = closes[i]

        # --- Confirm new swing points ---
        while sh_ptr < len(swing_highs) and swing_highs[sh_ptr][2] <= i:
            confirmed_highs.append(swing_highs[sh_ptr][:2])
            sh_ptr += 1
        while sl_ptr < len(swing_lows) and swing_lows[sl_ptr][2] <= i:
            confirmed_lows.append(swing_lows[sl_ptr][:2])
            sl_ptr += 1

        # --- Check special stop-loss re-entry modes when out of position ---
        if state == "waiting_for_buy":
            # 1. Exit Peak Reclaim: price breaks above the peak of the recent sell candle
            if stop_loss_mode == "exit_peak_reclaim" and last_sell_point is not None and i > last_sell_point[0]:
                sell_peak = last_sell_point[1]
                is_reclaim = (price > sell_peak) if full_candle else (highs[i] > sell_peak)
                if is_reclaim:
                    exec_price = price if full_candle else max(sell_peak, candles[i]["open"])
                    position = {
                        "entry_date":  date,
                        "entry_price": exec_price,
                        "entry_bar":   i,
                        "entry_low":   lows[i],
                        "side":        "long",
                    }
                    state = "holding"
                    active_trendline = None
                    search_after_bar = i
                    last_sell_point = None
                    trap_info = None
                    break_start_bar = None
                    confirm_count = 0
                    continue

            # 2. Barrier Trap Reentry: price recovers back above entry price within 5 bars
            if stop_loss_mode == "barrier_trap_reentry" and trap_info is not None:
                if i <= trap_info["exit_bar"] + 5:
                    is_trap_recovery = (price >= trap_info["entry_price"]) if full_candle else (highs[i] >= trap_info["entry_price"])
                    if is_trap_recovery:
                        exec_price = price if full_candle else max(trap_info["entry_price"], candles[i]["open"])
                        position = {
                            "entry_date":  date,
                            "entry_price": exec_price,
                            "entry_bar":   i,
                            "entry_low":   lows[i],
                            "side":        "long",
                        }
                        state = "holding"
                        active_trendline = None
                        search_after_bar = i
                        last_sell_point = None
                        trap_info = None
                        break_start_bar = None
                        confirm_count = 0
                        continue
                else:
                    trap_info = None

        # --- Check for trendline break confirmation ---
        if active_trendline is not None:
            tl = active_trendline
            projected = trendline_value(tl["anchor1"], tl["anchor2"], i)

            if state == "waiting_for_buy" or state == "short":
                # Watching descending resistance — break ABOVE = buy signal
                is_break = (price > projected) if full_candle else (highs[i] > projected)
                if tl["type"] == "resistance":
                    if break_start_bar is None:
                        if is_break:
                            if confirm_candles == 0:
                                exec_price = price if full_candle else max(round(projected, 4), candles[i]["open"])
                                trendlines.append({
                                    **tl,
                                    "break_bar": i,
                                    "break_price": exec_price,
                                    "break_date": date,
                                })

                                # Close short if in one
                                if position is not None and position["side"] == "short":
                                    trades.append({
                                        "entry_date":  position["entry_date"],
                                        "entry_price": position["entry_price"],
                                        "exit_date":   date,
                                        "exit_price":  exec_price,
                                        "side":        "short",
                                        "exit_reason": "resistance_break",
                                        "strategy":    "sloped_lines",
                                    })
                                    position = None

                                # Open long
                                position = {
                                    "entry_date":  date,
                                    "entry_price": exec_price,
                                    "entry_bar":   i,
                                    "entry_low":   lows[i],
                                    "side":        "long",
                                }
                                state = "holding"
                                active_trendline = None
                                search_after_bar = i
                                last_sell_point = None
                                continue
                            else:
                                break_start_bar = i
                                confirm_count = 0
                    else:
                        # In confirmation phase: must be above trendline AND moving in upward direction
                        is_supporting = is_break and (price > closes[i-1] or price >= candles[i]["open"])
                        if is_supporting:
                            confirm_count += 1
                            if confirm_count >= confirm_candles:
                                exec_price = price if full_candle else max(round(projected, 4), candles[i]["open"])
                                entry_low = min([lows[b] for b in range(break_start_bar, i + 1)])
                                trendlines.append({
                                    **tl,
                                    "break_bar": i,
                                    "break_price": exec_price,
                                    "break_date": date,
                                })

                                # Close short if in one
                                if position is not None and position["side"] == "short":
                                    trades.append({
                                        "entry_date":  position["entry_date"],
                                        "entry_price": position["entry_price"],
                                        "exit_date":   date,
                                        "exit_price":  exec_price,
                                        "side":        "short",
                                        "exit_reason": "resistance_break",
                                        "strategy":    "sloped_lines",
                                    })
                                    position = None

                                # Open long
                                position = {
                                    "entry_date":  date,
                                    "entry_price": exec_price,
                                    "entry_bar":   i,
                                    "entry_low":   entry_low,
                                    "side":        "long",
                                }
                                state = "holding"
                                active_trendline = None
                                search_after_bar = i
                                last_sell_point = None
                                break_start_bar = None
                                confirm_count = 0
                                continue
                        else:
                            # Reversal / drop below line: false breakout aborted
                            break_start_bar = None
                            confirm_count = 0

            elif state == "holding":
                # Watching ascending support — break BELOW = sell signal
                is_break = (price < projected) if full_candle else (lows[i] < projected)
                if tl["type"] == "support" and is_break:
                    exec_price = price if full_candle else min(round(projected, 4), candles[i]["open"])
                    # Record trendline for visualization
                    trendlines.append({
                        **tl,
                        "break_bar": i,
                        "break_price": exec_price,
                        "break_date": date,
                    })

                    # Close long
                    if position is not None and position["side"] == "long":
                        trades.append({
                            "entry_date":  position["entry_date"],
                            "entry_price": position["entry_price"],
                            "exit_date":   date,
                            "exit_price":  exec_price,
                            "side":        "long",
                            "exit_reason": "support_break",
                            "strategy":    "sloped_lines",
                        })
                        trap_info = {"exit_bar": i, "entry_price": position["entry_price"]}
                        position = None

                    # Open short if enabled
                    if enable_short:
                        position = {
                            "entry_date":  date,
                            "entry_price": exec_price,
                            "entry_bar":   i,
                            "entry_high":  highs[i],
                            "side":        "short",
                        }
                        state = "short"
                    else:
                        state = "waiting_for_buy"

                    active_trendline = None
                    search_after_bar = i
                    last_sell_point = (i, highs[i])
                    break_start_bar = None
                    confirm_count = 0
                    continue

        # --- Try to build trendlines if we don't have an active one ---
        if active_trendline is None:
            if state == "waiting_for_buy" or state == "short":
                # Build descending resistance starting with sell candle high as anchor1!
                cand_highs = None
                if last_sell_point is not None:
                    cand_highs = [(b, highs[b]) for b in range(last_sell_point[0] + 4, i + 1)]
                tl = build_descending_resistance(
                    confirmed_highs, closes,
                    search_after_bar=search_after_bar,
                    exit_point=last_sell_point,
                    candidate_highs=cand_highs,
                    current_bar=i,
                    tolerance=trendline_tolerance,
                    candles=candles,
                    inverse_color_trigger=inverse_color_trigger,
                    line_angle=line_angle,
                )
                if tl is not None and tl["confirmed_at_bar"] <= i:
                    active_trendline = tl
                    break_count = 0

            elif state == "holding" and position is not None:
                # Before line forms, if price breaks below entry candle low, stop out!
                entry_low = position["entry_low"]
                stop_barrier = entry_low - (atr[i] if stop_loss_mode == "atr_stop_buffer" else 0.0)
                entry_break = (price < stop_barrier) if full_candle else (lows[i] < stop_barrier)
                if entry_break and i > position["entry_bar"]:
                    exec_price = price if full_candle else min(stop_barrier, candles[i]["open"])
                    # Record support trendline so the breakdown line is visible on chart
                    a2_bar = max(i, position["entry_bar"] + 1)
                    allow_fallback_tl = True
                    if line_angle > 0.0:
                        allow_fallback_tl = False
                    if inverse_color_trigger:
                        if not is_green_candle(candles[position["entry_bar"]]) or not is_red_candle(candles[a2_bar]):
                            allow_fallback_tl = False
                    if allow_fallback_tl:
                        trendlines.append({
                            "type": "support",
                            "direction": "ascending",
                            "anchor1": (position["entry_bar"], entry_low),
                            "anchor2": (a2_bar, entry_low),
                            "confirmed_at_bar": position["entry_bar"],
                            "break_bar": i,
                            "break_price": exec_price,
                            "break_date": date,
                        })
                    trades.append({
                        "entry_date":  position["entry_date"],
                        "entry_price": position["entry_price"],
                        "exit_date":   date,
                        "exit_price":  exec_price,
                        "side":        "long",
                        "exit_reason": "support_break",
                        "strategy":    "sloped_lines",
                    })
                    trap_info = {"exit_bar": i, "entry_price": position["entry_price"]}
                    position = None
                    state = "waiting_for_buy"
                    search_after_bar = i
                    last_sell_point = (i, highs[i])
                    continue

                # If price pulls back before line forms without breaking stop, adjust entry base
                if lows[i] < position["entry_low"]:
                    position["entry_low"] = lows[i]
                    if not inverse_color_trigger or is_green_candle(candles[i]):
                        position["entry_bar"] = i

                # Build ascending support starting with entry candle low as anchor1!
                entry_pt = (position["entry_bar"], position["entry_low"])
                cand_lows = [(b, lows[b]) for b in range(position["entry_bar"] + 4, i + 1)]
                tl = build_ascending_support(
                    confirmed_lows, closes,
                    search_after_bar=position["entry_bar"],
                    entry_point=entry_pt,
                    candidate_lows=cand_lows,
                    current_bar=i,
                    tolerance=trendline_tolerance,
                    candles=candles,
                    inverse_color_trigger=inverse_color_trigger,
                    line_angle=line_angle,
                )
                if tl is not None and tl["confirmed_at_bar"] <= i:
                    active_trendline = tl
                    break_count = 0

    # --- Close any open position at end of data ---
    if position is not None:
        side = position["side"]
        trades.append({
            "entry_date":  position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date":   candles[-1]["date"],
            "exit_price":  candles[-1]["close"],
            "side":        side,
            "exit_reason": "end_of_data",
            "strategy":    "sloped_lines",
        })

    # If there's a still-active (unbroken) trendline, record it too
    if active_trendline is not None:
        trendlines.append({
            **active_trendline,
            "break_bar": None,  # still active
            "break_price": None,
            "break_date": None,
        })

    return trades, trendlines


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


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1h") -> dict:
    """Calculate backtest metrics."""
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "long_trades": 0, "short_trades": 0,
                "support_break_exits": 0, "resistance_break_exits": 0, "end_of_data_exits": 0,
                "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252 * 6)

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
        "support_break_exits":    sum(1 for t in trades if t.get("exit_reason") == "support_break"),
        "resistance_break_exits": sum(1 for t in trades if t.get("exit_reason") == "resistance_break"),
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


# ==============================================================================
# TRENDLINE -> OVERLAY CONVERSION (for interactive chart)
# ==============================================================================

def trendlines_to_overlays(trendlines: list[dict], candles: list[dict]) -> list[dict]:
    """
    Convert trendline dicts into overlay line series for visualize.py.

    Each trendline becomes a separate line overlay with just 2 points
    (start and end) — Lightweight Charts draws a straight line between them.

    Colors:
      - Descending resistance (lower highs) = green (#3fb950)
      - Ascending support (higher lows) = blue (#58a6ff)
    """
    overlays = []
    res_count = 0
    sup_count = 0

    for tl in trendlines:
        a1_bar, a1_price = tl["anchor1"]
        a2_bar, a2_price = tl["anchor2"]

        # Determine end bar for the line
        break_bar = tl.get("break_bar")
        if break_bar is not None:
            end_bar = min(break_bar + 1, len(candles) - 1)
        else:
            end_bar = len(candles) - 1

        # Compute slope
        if a2_bar == a1_bar:
            continue
        slope = (a2_price - a1_price) / (a2_bar - a1_bar)

        # Just 2 points: start and end of the line
        if a1_bar < 0 or a1_bar >= len(candles) or end_bar < 0 or end_bar >= len(candles):
            continue

        start_price = a1_price
        end_price = a1_price + slope * (end_bar - a1_bar)

        points = [
            {"time": candles[a1_bar]["date"], "value": round(start_price, 4)},
            {"time": candles[end_bar]["date"], "value": round(end_price, 4)},
        ]

        # Color: green for descending resistance, blue for ascending support
        direction = tl.get("direction", "")
        if direction == "descending":
            res_count += 1
            color = "#3fb950"  # green
            # Only label the first one to avoid legend spam
            label = "▼ Resistance (lower highs)" if res_count == 1 else ""
        else:
            sup_count += 1
            color = "#58a6ff"  # blue
            label = "▲ Support (higher lows)" if sup_count == 1 else ""

        overlays.append({
            "label": label,
            "color": color,
            "type": "line",
            "lineWidth": 2,
            "lineStyle": 0,  # solid
            "points": points,
        })

    return overlays


def run_sloped_lines_trades(candles: list[dict], **kwargs) -> list[dict]:
    """
    Backtesting service compatibility runner.
    Takes OHLCV candles, returns trade list.
    """
    pivot_lookback = kwargs.get("pivot_lookback", PIVOT_LOOKBACK)
    trendline_tolerance = kwargs.get("trendline_tolerance", TRENDLINE_TOLERANCE)
    confirm_bars = kwargs.get("confirm_bars", CONFIRM_BARS)
    enable_short = kwargs.get("enable_short", ENABLE_SHORT)
    full_candle = kwargs.get("full_candle", DEFAULT_FULL_CANDLE)
    use_wick = kwargs.get("use_wick", USE_WICK)
    confirm_candles = kwargs.get("confirm_candles", 0)
    inverse_color_trigger = kwargs.get("inverse_color_trigger", False)
    line_angle = kwargs.get("line_angle", DEFAULT_LINE_ANGLE)
    stop_loss_mode = kwargs.get("stop_loss_mode", DEFAULT_STOP_LOSS_MODE)
    trades, _ = run_sloped_lines(
        candles,
        pivot_lookback=pivot_lookback,
        trendline_tolerance=trendline_tolerance,
        confirm_bars=confirm_bars,
        enable_short=enable_short,
        full_candle=full_candle,
        use_wick=use_wick,
        confirm_candles=confirm_candles,
        inverse_color_trigger=inverse_color_trigger,
        line_angle=line_angle,
        stop_loss_mode=stop_loss_mode,
    )
    return trades


def run_sloped_lines_with_trendlines(candles: list[dict], **kwargs) -> dict:
    """
    Run sloped_lines and return both trades and structured trendline overlays
    ready for frontend visualization.
    """
    pivot_lookback = kwargs.get("pivot_lookback", PIVOT_LOOKBACK)
    trendline_tolerance = kwargs.get("trendline_tolerance", TRENDLINE_TOLERANCE)
    confirm_bars = kwargs.get("confirm_bars", CONFIRM_BARS)
    enable_short = kwargs.get("enable_short", ENABLE_SHORT)
    full_candle = kwargs.get("full_candle", DEFAULT_FULL_CANDLE)
    use_wick = kwargs.get("use_wick", USE_WICK)
    confirm_candles = kwargs.get("confirm_candles", 0)
    inverse_color_trigger = kwargs.get("inverse_color_trigger", False)
    line_angle = kwargs.get("line_angle", DEFAULT_LINE_ANGLE)
    stop_loss_mode = kwargs.get("stop_loss_mode", DEFAULT_STOP_LOSS_MODE)

    trades, raw_trendlines = run_sloped_lines(
        candles,
        pivot_lookback=pivot_lookback,
        trendline_tolerance=trendline_tolerance,
        confirm_bars=confirm_bars,
        enable_short=enable_short,
        full_candle=full_candle,
        use_wick=use_wick,
        confirm_candles=confirm_candles,
        inverse_color_trigger=inverse_color_trigger,
        line_angle=line_angle,
        stop_loss_mode=stop_loss_mode,
    )

    formatted_trendlines = []
    for tl in raw_trendlines:
        a1_bar, a1_price = tl["anchor1"]
        a2_bar, a2_price = tl["anchor2"]
        break_bar = tl.get("break_bar")

        if break_bar is not None:
            end_bar = max(a1_bar + 1, min(break_bar, len(candles) - 1))
        else:
            end_bar = len(candles) - 1

        if a2_bar == a1_bar or a1_bar < 0 or a1_bar >= len(candles) or end_bar < 0 or end_bar >= len(candles):
            continue

        slope = (a2_price - a1_price) / (a2_bar - a1_bar)
        end_price = a1_price + slope * (end_bar - a1_bar)

        is_res = (tl.get("type") == "resistance" or tl.get("direction") == "descending")
        color = "#10B981" if is_res else "#3B82F6"
        label = "▼ Resistance (Breakout = Buy)" if is_res else "▲ Support (Breakdown = Sell)"

        formatted_trendlines.append({
            "type": "resistance" if is_res else "support",
            "direction": "descending" if is_res else "ascending",
            "start_date": candles[a1_bar]["date"],
            "start_time": candles[a1_bar].get("time"),
            "start_price": round(a1_price, 4),
            "end_date": candles[end_bar]["date"],
            "end_time": candles[end_bar].get("time"),
            "end_price": round(end_price, 4),
            "break_date": tl.get("break_date"),
            "break_price": tl.get("break_price"),
            "slope_per_bar": round(slope, 6),
            "color": color,
            "label": label,
        })

    return {
        "trades": trades,
        "trendlines": formatted_trendlines,
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
    pivot_lookback: int = PIVOT_LOOKBACK,
    trendline_tolerance: float = TRENDLINE_TOLERANCE,
    confirm_bars: int = CONFIRM_BARS,
    enable_short: bool = ENABLE_SHORT,
    full_candle: bool = DEFAULT_FULL_CANDLE,
    use_wick: bool = False,
    confirm_candles: int = 0,
    inverse_color_trigger: bool = False,
    line_angle: float = DEFAULT_LINE_ANGLE,
    stop_loss_mode: str = DEFAULT_STOP_LOSS_MODE,
    candles: list[dict] = None,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    if candles is None:
        candles = fetch_ohlcv(symbol, period, interval)
    if not candles:
        return {
            "symbol": symbol.upper(),
            "strategy": "sloped_lines",
            "total_trades": 0,
            "final_capital": initial_capital,
            "total_return_pct": 0.0,
            "buy_and_hold_return_pct": 0.0,
            "win_rate_pct": 0.0,
            "trade_log": [],
        }
    raw_trades, trendlines = run_sloped_lines(
        candles, pivot_lookback, trendline_tolerance, confirm_bars, enable_short, full_candle, use_wick, confirm_candles=confirm_candles, inverse_color_trigger=inverse_color_trigger, line_angle=line_angle, stop_loss_mode=stop_loss_mode,
    )
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    # Serialize trendlines for JSON output
    serialized_trendlines = []
    for tl in trendlines:
        serialized_trendlines.append({
            "type": tl["type"],
            "direction": tl["direction"],
            "anchor1_bar": tl["anchor1"][0],
            "anchor1_price": tl["anchor1"][1],
            "anchor2_bar": tl["anchor2"][0],
            "anchor2_price": tl["anchor2"][1],
            "break_bar": tl.get("break_bar"),
            "break_price": tl.get("break_price"),
            "break_date": tl.get("break_date"),
        })

    return {
        "symbol": symbol.upper(),
        "strategy": "sloped_lines",
        "strategy_label": f"Sloped Lines (pivot={pivot_lookback}, tol={trendline_tolerance*100:.1f}%, confirm_candles={confirm_candles}, angle={line_angle}%, stop={stop_loss_mode})",
        "parameters": {
            "pivot_lookback": pivot_lookback,
            "trendline_tolerance": trendline_tolerance,
            "confirm_bars": confirm_bars,
            "enable_short": enable_short,
            "full_candle": full_candle,
            "use_wick": use_wick,
            "confirm_candles": confirm_candles,
            "inverse_color_trigger": inverse_color_trigger,
            "line_angle": line_angle,
            "stop_loss_mode": stop_loss_mode,
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
        "trendlines": serialized_trendlines,
        "overlays": trendlines_to_overlays(trendlines, candles),
        "trade_log": trades,
        "candles": candles,  # include for visualization
        "data_source": "Yahoo Finance",
        "disclaimer": "Past performance does not guarantee future results. For educational use only.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Sloped Lines (Trendline Breakout) Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size (default: 1h)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK, help="Bars left/right for swing detection (default: 5)")
    parser.add_argument("--trendline-tolerance", type=float, default=TRENDLINE_TOLERANCE, help="Tolerance for trendline validation (default: 0.015 = 1.5%%)")
    parser.add_argument("--confirm-bars", type=int, default=CONFIRM_BARS, help="Consecutive bars beyond trendline to confirm break (default: 1)")
    parser.add_argument("--confirm-candles", type=int, default=0, choices=[0, 1, 2, 3], help="Number of additional supporting confirmation candles before buy (default: 0)")
    parser.add_argument("--inverse-color", "--inverse-color-trigger", action="store_true", default=False, dest="inverse_color_trigger", help="Require ascending support to start green/end red, and descending resistance to start red/end green")
    parser.add_argument("--line-angle", type=float, default=DEFAULT_LINE_ANGLE, choices=[0.0, 2.0, 3.0, 5.0, 8.0], help="Minimum percentage angle/slope threshold between line anchors (0, 2, 3, 5, 8, default: 3.0)")
    parser.add_argument("--stop-loss-mode", default=DEFAULT_STOP_LOSS_MODE, choices=["none", "exit_peak_reclaim", "barrier_trap_reentry", "atr_stop_buffer"], help="Stop loss mode (none, exit_peak_reclaim, barrier_trap_reentry, atr_stop_buffer, default: exit_peak_reclaim)")
    parser.add_argument("--enable-short", action="store_true", default=ENABLE_SHORT, help="Enable short selling on support break")
    parser.add_argument("--full-candle", action="store_true", default=DEFAULT_FULL_CANDLE, help="Require candle to close across trendline for breakout (default: False)")
    parser.add_argument("--touch-break", action="store_false", dest="full_candle", help="Allow intrabar touch/wick to break trendline (default)")
    parser.add_argument("--use-wick", action="store_true", default=False, help="Use candle wicks instead of body for trendline contact points (default: False)")
    parser.add_argument("--chart", action="store_true", help="Generate interactive HTML chart with trendlines")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Sloped Lines Strategy — {args.symbol}")
    print(f"  Pivots: {args.pivot_lookback}  |  Tolerance: {args.trendline_tolerance*100:.1f}%  |  Confirm Candles: {args.confirm_candles}  |  Line Angle: {args.line_angle}%")
    print(f"  Interval: {args.interval}  |  Full Candle: {'ON' if args.full_candle else 'OFF (Touch)'}  |  Wick: {'ON' if args.use_wick else 'OFF (Body)'}  |  Inverse Color: {'ON' if args.inverse_color_trigger else 'OFF'}  |  Stop Loss: {args.stop_loss_mode}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_lookback=args.pivot_lookback, trendline_tolerance=args.trendline_tolerance,
        confirm_bars=args.confirm_bars, enable_short=args.enable_short,
        full_candle=args.full_candle,
        use_wick=args.use_wick,
        confirm_candles=args.confirm_candles,
        inverse_color_trigger=args.inverse_color_trigger,
        line_angle=args.line_angle,
        stop_loss_mode=args.stop_loss_mode,
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
    print(f"  Trendlines:       {len(result['trendlines'])} drawn")
    print(f"  Exits:            Support Break: {result['support_break_exits']}  |  Resistance Break: {result['resistance_break_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    # Save results (without candles to keep file size manageable)
    output = {k: v for k, v in result.items() if k != "candles"}
    script_dir = Path(__file__).resolve().parent
    fname = script_dir / f"sloped_lines_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Full results saved to: {fname}\n")

    # Generate interactive chart if requested
    if args.chart:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from visualize import generate_chart_html

        chart_path = script_dir / f"sloped_lines_chart_{args.symbol.replace('-','_')}_{args.period}.html"
        generate_chart_html(
            result=result,
            candles=result["candles"],
            output_path=chart_path,
        )
        print(f"  Interactive chart saved to: {chart_path}")
        print(f"  Open with: open '{chart_path}'\n")


if __name__ == "__main__":
    main()
