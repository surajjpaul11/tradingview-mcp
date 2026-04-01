"""
Enhanced Lines Strategy — Standalone Python Implementation
==========================================================

Channel-based trendline bounce strategy with volume-weighted position sizing.

Unlike Straight Line (which trades trendline *breaks*), Enhanced Lines trades
trendline *bounces* within a channel:

Uptrend channel (higher lows + higher highs):
  1. Bounce UP from support (higher lows line) -> BUY (volume-weighted sizing)
  2. Bounce DOWN from resistance (higher highs line) -> PARTIAL SELL (FIFO)

Downtrend channel (lower highs + lower lows):
  1. Bounce DOWN from resistance (lower highs line) -> SHORT (volume-weighted sizing)
  2. Bounce UP from support (lower lows line) -> PARTIAL COVER (FIFO)

Regime change (trend flips): close ALL positions immediately (100%).

Position sizing: volume ratio (recent volume / vol SMA) * base_pct, clamped
to [floor_pct, ceiling_pct] of available capacity (buys) or current position
(sells).

Usage:
  python enhanced_lines_strategy.py                                 # defaults: SPY, 2y, 1h
  python enhanced_lines_strategy.py --symbol BTC-USD --period 1y
  python enhanced_lines_strategy.py --symbol QQQ --no-short
  python enhanced_lines_strategy.py --symbol AAPL --min-touches 2

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

PIVOT_LOOKBACK    = 5        # bars left/right for swing point detection
MIN_TOUCHES       = 3        # points needed to confirm a trendline (last N)
TOLERANCE         = 0.015    # 1.5% tolerance for "touching" the trendline
CONFIRM_BARS      = 2        # consecutive bars to confirm a bounce
VOL_MA_PERIOD     = 20       # lookback for volume moving average
VOL_BASE_PCT      = 0.25     # base position size as fraction of capacity
VOL_FLOOR_PCT     = 0.20     # minimum position size fraction
VOL_CEILING_PCT   = 0.80     # maximum position size fraction
ENABLE_SHORT      = True     # enable short positions in downtrends
INTERVAL          = "1h"     # candle size
PERIOD            = "2y"     # data lookback
INITIAL_CAPITAL   = 10_000.0
COMMISSION_PCT    = 0.1
SLIPPAGE_PCT      = 0.05


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1h") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "enhanced-lines-strategy/1.0"})
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
# SWING POINT DETECTION
# ==============================================================================

def find_swings(highs: list[float], lows: list[float], lookback: int = 5
                ) -> tuple[list[tuple[int, float, int]], list[tuple[int, float, int]]]:
    """
    Detect swing highs and swing lows via pivot logic.

    Returns:
      swing_highs: list of (bar_index, price, confirmed_at_bar)
      swing_lows:  list of (bar_index, price, confirmed_at_bar)
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
# VOLUME SMA
# ==============================================================================

def calc_vol_sma(volumes: list[float], period: int) -> list[Optional[float]]:
    """Simple moving average of volume. Returns None for bars before period is filled."""
    result: list[Optional[float]] = [None] * len(volumes)
    for i in range(period - 1, len(volumes)):
        result[i] = sum(volumes[i - period + 1: i + 1]) / period
    return result


# ==============================================================================
# TRENDLINE LOGIC
# ==============================================================================

def trendline_value(p1: tuple[int, float], p2: tuple[int, float], bar: int) -> float:
    """Calculate the projected trendline value at a given bar index."""
    b1, pr1 = p1
    b2, pr2 = p2
    if b2 == b1:
        return pr1
    slope = (pr2 - pr1) / (b2 - b1)
    return pr1 + slope * (bar - b1)


def trendline_slope_per_bar(p1: tuple[int, float], p2: tuple[int, float]) -> Optional[float]:
    """Slope of the trendline in price/bar. Returns None if anchors coincide."""
    b1, pr1 = p1
    b2, pr2 = p2
    if b2 == b1:
        return None
    return (pr2 - pr1) / (b2 - b1)


def fit_trendline(
    points: list[tuple[int, float]],
    min_touches: int,
    tolerance: float,
    direction: str,
) -> Optional[dict]:
    """
    Fit a trendline using the LAST min_touches points.

    Validates:
      - Enough points available
      - Points are collinear within tolerance (all intermediate points near the
        line drawn from first to last of the selected points)
      - Direction matches: "ascending" means slope > 0, "descending" means slope < 0

    Returns dict with anchor1, anchor2, slope_per_bar, all_points, last_bar — or None.
    """
    if len(points) < min_touches:
        return None

    # Take the last min_touches points
    selected = points[-min_touches:]
    anchor1 = selected[0]
    anchor2 = selected[-1]

    slope = trendline_slope_per_bar(anchor1, anchor2)
    if slope is None:
        return None

    # Check direction
    if direction == "ascending" and slope <= 0:
        return None
    if direction == "descending" and slope >= 0:
        return None

    # Check collinearity: all intermediate points must be within tolerance
    for pt in selected[1:-1]:
        projected = trendline_value(anchor1, anchor2, pt[0])
        if projected <= 0:
            return None
        deviation = abs(pt[1] - projected) / projected
        if deviation > tolerance:
            return None

    return {
        "anchor1": anchor1,
        "anchor2": anchor2,
        "slope_per_bar": slope,
        "all_points": selected,
        "last_bar": anchor2[0],
    }


def build_channel(
    confirmed_highs: list[tuple[int, float]],
    confirmed_lows: list[tuple[int, float]],
    min_touches: int,
    tolerance: float,
) -> dict:
    """
    Build all 4 trendline types from confirmed swing points.

    Returns dict with keys: higher_highs, higher_lows, lower_highs, lower_lows.
    Each value is a trendline dict or None.
    """
    return {
        "higher_highs": fit_trendline(confirmed_highs, min_touches, tolerance, "ascending"),
        "higher_lows":  fit_trendline(confirmed_lows, min_touches, tolerance, "ascending"),
        "lower_highs":  fit_trendline(confirmed_highs, min_touches, tolerance, "descending"),
        "lower_lows":   fit_trendline(confirmed_lows, min_touches, tolerance, "descending"),
    }


# ==============================================================================
# TREND DETERMINATION & BOUNCE DETECTION
# ==============================================================================

def determine_trend(
    support_slope: Optional[float],
    resistance_slope: Optional[float],
    avg_price: float,
    flat_threshold_pct: float = 0.0002,
) -> str:
    """
    Determine trend from support and resistance slopes.

    Both slopes up -> "uptrend"
    Both slopes down -> "downtrend"
    Disagree or both flat -> "neutral"
    None slopes -> "neutral"
    """
    if support_slope is None or resistance_slope is None:
        return "neutral"

    # Normalize slopes relative to price to make threshold meaningful
    flat = flat_threshold_pct * avg_price

    sup_up = support_slope > flat
    sup_dn = support_slope < -flat
    res_up = resistance_slope > flat
    res_dn = resistance_slope < -flat

    if sup_up and res_up:
        return "uptrend"
    if sup_dn and res_dn:
        return "downtrend"
    return "neutral"


def detect_bounce(
    candles: list[dict],
    bar_idx: int,
    trendline: dict,
    direction: str,
    tolerance: float,
    confirm_bars: int,
) -> bool:
    """
    Detect a bounce off a trendline.

    - direction "up": price near trendline from above, then confirm_bars bullish closes
    - direction "down": price near trendline from below, then confirm_bars bearish closes

    Price must be within tolerance of projected trendline value.
    For "up" bounces, also checks if low is in tolerance zone.
    For "down" bounces, also checks if high is in tolerance zone.

    Returns True if bounce confirmed.
    """
    if bar_idx < confirm_bars:
        return False
    if bar_idx >= len(candles):
        return False

    projected = trendline_value(trendline["anchor1"], trendline["anchor2"], bar_idx)
    if projected <= 0:
        return False

    c = candles[bar_idx]

    # Check if price is in the tolerance zone
    close_dev = abs(c["close"] - projected) / projected
    if direction == "up":
        low_dev = abs(c["low"] - projected) / projected
        in_zone = close_dev <= tolerance or low_dev <= tolerance
    else:
        high_dev = abs(c["high"] - projected) / projected
        in_zone = close_dev <= tolerance or high_dev <= tolerance

    if not in_zone:
        return False

    # Check confirm_bars consecutive candles close in the bounce direction
    # We look at the bars ending at bar_idx (the current bar and preceding bars)
    start = bar_idx - confirm_bars + 1
    if start < 0:
        return False

    for k in range(start, bar_idx + 1):
        if direction == "up":
            # Bullish: close > open
            if candles[k]["close"] <= candles[k]["open"]:
                return False
        else:
            # Bearish: close < open
            if candles[k]["close"] >= candles[k]["open"]:
                return False

    return True


def calc_trade_pct(
    candles: list[dict],
    bar_idx: int,
    vol_sma: list[Optional[float]],
    confirm_bars: int,
    base_pct: float,
    floor_pct: float,
    ceiling_pct: float,
) -> float:
    """
    Calculate trade size as fraction of available capacity (buys) or position (sells).

    avg_vol of last confirm_bars candles / vol_sma -> vol_ratio
    trade_pct = clamp(vol_ratio * base_pct, floor_pct, ceiling_pct)
    """
    if vol_sma[bar_idx] is None or vol_sma[bar_idx] == 0:
        return base_pct

    start = max(0, bar_idx - confirm_bars + 1)
    recent_vols = [candles[k]["volume"] for k in range(start, bar_idx + 1)]
    avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 0

    vol_ratio = avg_vol / vol_sma[bar_idx] if vol_sma[bar_idx] > 0 else 1.0
    trade_pct = vol_ratio * base_pct
    return max(floor_pct, min(ceiling_pct, trade_pct))


# ==============================================================================
# FIFO PARTIAL CLOSE HELPER
# ==============================================================================

def _fifo_partial_close(
    position_entries: list[dict],
    shares_to_close: float,
    date: str,
    price: float,
    side: str,
    exit_reason: str,
    trade_pct: float,
    trades_list: list[dict],
) -> list[dict]:
    """
    Walk position_entries FIFO, closing up to shares_to_close shares.

    Appends completed trade dicts to trades_list.
    Returns the updated position_entries (with partially/fully consumed entries removed).
    """
    remaining = shares_to_close
    new_entries: list[dict] = []
    for entry in position_entries:
        if remaining <= 0.001:
            new_entries.append(entry)
            continue
        close_from_this = min(entry["shares"], remaining)
        trades_list.append({
            "entry_date": entry["date"],
            "entry_price": entry["price"],
            "exit_date": date,
            "exit_price": price,
            "side": side,
            "exit_reason": exit_reason,
            "strategy": "enhanced_lines",
            "shares": close_from_this,
            "trade_pct": trade_pct,
        })
        remaining -= close_from_this
        leftover = entry["shares"] - close_from_this
        if leftover > 0.001:
            new_entries.append({
                "date": entry["date"],
                "price": entry["price"],
                "shares": leftover,
            })
    return new_entries


# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_enhanced_lines(
    candles: list[dict],
    pivot_lookback: int = PIVOT_LOOKBACK,
    min_touches: int = MIN_TOUCHES,
    tolerance: float = TOLERANCE,
    confirm_bars: int = CONFIRM_BARS,
    vol_ma_period: int = VOL_MA_PERIOD,
    vol_base_pct: float = VOL_BASE_PCT,
    vol_floor_pct: float = VOL_FLOOR_PCT,
    vol_ceiling_pct: float = VOL_CEILING_PCT,
    enable_short: bool = ENABLE_SHORT,
    initial_capital: float = INITIAL_CAPITAL,
) -> list[dict]:
    """
    Enhanced Lines channel bounce strategy.

    Trades bounces within trendline channels with volume-weighted position sizing.
    Closes all positions on regime (trend) changes.

    Returns list of trade dicts.
    """
    if not candles:
        return []

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]

    vol_sma = calc_vol_sma(volumes, vol_ma_period)

    # Find all swings
    swing_highs, swing_lows = find_swings(highs, lows, pivot_lookback)

    # Progressive confirmation tracking
    confirmed_highs: list[tuple[int, float]] = []
    confirmed_lows: list[tuple[int, float]] = []
    sh_ptr = sl_ptr = 0

    # State
    trades: list[dict] = []
    position_shares: float = 0.0  # positive = long, negative = short
    position_entries: list[dict] = []  # FIFO: [{date, price, shares}, ...]
    prev_trend: str = "neutral"

    # I-4: dynamic capital tracking — max_shares scales with realized PnL
    current_capital: float = initial_capital
    initial_price: float = candles[0]["close"] if candles else 1.0
    max_shares: float = initial_capital / initial_price if initial_price > 0 else 0.0

    def _update_capital_from_trades(trades_before: int) -> None:
        """Update current_capital from trades appended since trades_before index."""
        nonlocal current_capital
        for t in trades[trades_before:]:
            if t["side"] == "short":
                pnl = t["shares"] * (t["entry_price"] - t["exit_price"])
            else:
                pnl = t["shares"] * (t["exit_price"] - t["entry_price"])
            current_capital += pnl

    for i in range(len(candles)):
        date = candles[i]["date"]
        price = closes[i]

        # Confirm new swing points progressively
        while sh_ptr < len(swing_highs) and swing_highs[sh_ptr][2] <= i:
            confirmed_highs.append(swing_highs[sh_ptr][:2])
            sh_ptr += 1
        while sl_ptr < len(swing_lows) and swing_lows[sl_ptr][2] <= i:
            confirmed_lows.append(swing_lows[sl_ptr][:2])
            sl_ptr += 1

        # Build channel from confirmed swings
        channel = build_channel(confirmed_highs, confirmed_lows, min_touches, tolerance)

        # Select best support/resistance pair
        support = None
        resistance = None

        # Prefer higher_lows + higher_highs (uptrend channel)
        if channel["higher_lows"] is not None and channel["higher_highs"] is not None:
            support = channel["higher_lows"]
            resistance = channel["higher_highs"]
        # Then lower_lows + lower_highs (downtrend channel)
        elif channel["lower_lows"] is not None and channel["lower_highs"] is not None:
            support = channel["lower_lows"]
            resistance = channel["lower_highs"]
        # Mixed: take whatever is available
        else:
            support = channel["higher_lows"] or channel["lower_lows"]
            resistance = channel["higher_highs"] or channel["lower_highs"]

        # Determine trend from slope agreement
        sup_slope = support["slope_per_bar"] if support else None
        res_slope = resistance["slope_per_bar"] if resistance else None
        avg_price = price  # Use current price as reference
        trend = determine_trend(sup_slope, res_slope, avg_price)

        # --- REGIME CHANGE: close ALL positions ---
        if trend != prev_trend and prev_trend != "neutral" and position_shares != 0.0:
            side = "long" if position_shares > 0 else "short"
            trades_before = len(trades)
            # Close all entries FIFO
            for entry in position_entries:
                trades.append({
                    "entry_date": entry["date"],
                    "entry_price": entry["price"],
                    "exit_date": date,
                    "exit_price": price,
                    "side": side,
                    "exit_reason": "trend_flip",
                    "strategy": "enhanced_lines",
                    "shares": entry["shares"],
                    "trade_pct": 1.0,  # full exit
                })
            position_shares = 0.0
            position_entries = []
            # I-4: update running capital and max_shares
            _update_capital_from_trades(trades_before)
            if price > 0:
                max_shares = current_capital / price

        prev_trend = trend

        # --- UPTREND: bounce logic ---
        if trend == "uptrend":
            # Bounce UP from support -> BUY
            if support is not None and position_shares >= 0:
                if detect_bounce(candles, i, support, "up", tolerance, confirm_bars):
                    available_capacity = max_shares - position_shares
                    if available_capacity > 0.01:
                        trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                                   vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                        shares_to_buy = available_capacity * trade_pct
                        if shares_to_buy > 0.01:
                            position_shares += shares_to_buy
                            position_entries.append({
                                "date": date,
                                "price": price,
                                "shares": shares_to_buy,
                            })

            # Bounce DOWN from resistance -> PARTIAL SELL (FIFO)
            elif resistance is not None and position_shares > 0.01:
                if detect_bounce(candles, i, resistance, "down", tolerance, confirm_bars):
                    trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                               vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                    shares_to_sell = position_shares * trade_pct
                    if shares_to_sell > 0.01:
                        trades_before = len(trades)
                        position_entries = _fifo_partial_close(
                            position_entries, shares_to_sell, date, price,
                            "long", "resistance_bounce", trade_pct, trades,
                        )
                        position_shares -= shares_to_sell
                        if position_shares < 0.001:
                            position_shares = 0.0
                        # I-4: update running capital and max_shares
                        _update_capital_from_trades(trades_before)
                        if price > 0:
                            max_shares = current_capital / price

        # --- DOWNTREND: bounce logic (short) ---
        elif trend == "downtrend" and enable_short:
            # Bounce DOWN from resistance -> SHORT
            if resistance is not None and position_shares <= 0:
                if detect_bounce(candles, i, resistance, "down", tolerance, confirm_bars):
                    available_capacity = max_shares - abs(position_shares)
                    if available_capacity > 0.01:
                        trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                                   vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                        shares_to_short = available_capacity * trade_pct
                        if shares_to_short > 0.01:
                            position_shares -= shares_to_short
                            position_entries.append({
                                "date": date,
                                "price": price,
                                "shares": shares_to_short,
                            })

            # Bounce UP from support -> CLOSE SHORT (partial, FIFO)
            elif support is not None and position_shares < -0.01:
                if detect_bounce(candles, i, support, "up", tolerance, confirm_bars):
                    trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                               vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                    shares_to_cover = abs(position_shares) * trade_pct
                    if shares_to_cover > 0.01:
                        trades_before = len(trades)
                        position_entries = _fifo_partial_close(
                            position_entries, shares_to_cover, date, price,
                            "short", "support_bounce", trade_pct, trades,
                        )
                        position_shares += shares_to_cover
                        if abs(position_shares) < 0.001:
                            position_shares = 0.0
                        # I-4: update running capital and max_shares
                        _update_capital_from_trades(trades_before)
                        if price > 0:
                            max_shares = current_capital / price

    # End of data: close all open positions
    if position_shares != 0.0 and position_entries:
        side = "long" if position_shares > 0 else "short"
        for entry in position_entries:
            trades.append({
                "entry_date": entry["date"],
                "entry_price": entry["price"],
                "exit_date": candles[-1]["date"],
                "exit_price": candles[-1]["close"],
                "side": side,
                "exit_reason": "end_of_data",
                "strategy": "enhanced_lines",
                "shares": entry["shares"],
                "trade_pct": 1.0,
            })

    return trades


# ==============================================================================
# METRICS & REPORTING
# ==============================================================================

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply transaction costs to each trade. Handles shares-weighted PnL."""
    total_cost_pct = (commission_pct + slippage_pct) * 2  # round-trip
    result = []
    for t in trades:
        if t["side"] == "short":
            gross = (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100
        else:
            gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net = round(gross - total_cost_pct, 3)
        result.append({
            **t,
            "return_pct": net,
            "gross_return_pct": round(gross, 3),
            "cost_pct": round(-total_cost_pct, 3),
        })
    return result


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1h") -> dict:
    """
    Calculate backtest metrics with shares-weighted PnL.

    PnL per trade = shares * (exit_price - entry_price) - costs
    (adjusted for side: shorts reverse the price direction)
    """
    empty = {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "long_trades": 0, "short_trades": 0,
        "trend_flip_exits": 0, "resistance_bounce_exits": 0,
        "support_bounce_exits": 0, "end_of_data_exits": 0,
        "win_rate_pct": 0, "total_return_pct": 0,
        "final_capital": initial_capital, "max_drawdown_pct": 0,
        "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
        "profit_factor": 0, "expectancy_pct": 0,
    }
    if not trades:
        return empty

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252 * 6)

    # Calculate PnL per trade using shares-weighted approach
    # return_pct already includes costs (from apply_costs), so we derive PnL from it
    capital = initial_capital
    peak = capital
    max_dd = 0.0
    returns = []

    for t in trades:
        shares = t.get("shares", 1.0)
        # PnL = shares * entry_price * (return_pct / 100)
        # return_pct is the net % return after costs
        pnl = shares * t["entry_price"] * (t["return_pct"] / 100)
        r = pnl / capital if capital > 0 else 0
        capital += pnl
        returns.append(r)
        peak = max(peak, capital)
        dd = (peak - capital) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    total_ret = (capital - initial_capital) / initial_capital * 100

    # I-1: Dollar-weighted metrics — weight gains/losses by actual dollar PnL
    def _dollar_pnl(t: dict) -> float:
        shares = t.get("shares", 1.0)
        return shares * t["entry_price"] * (t["return_pct"] / 100)

    winners = [t for t in trades if t["return_pct"] > 0]
    losers = [t for t in trades if t["return_pct"] <= 0]

    winner_pnls = [_dollar_pnl(t) for t in winners]
    loser_pnls = [_dollar_pnl(t) for t in losers]

    gross_gains = sum(winner_pnls)
    gross_losses = abs(sum(loser_pnls))

    avg_gain = (gross_gains / len(winners)) if winners else 0
    avg_loss = (sum(loser_pnls) / len(losers)) if losers else 0  # negative value
    pf = round(gross_gains / gross_losses, 2) if gross_losses > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / ann) / std_r * math.sqrt(ann), 2)

    wr = len(winners) / len(trades) if trades else 0
    long_count = sum(1 for t in trades if t["side"] == "long")
    short_count = sum(1 for t in trades if t["side"] == "short")

    return {
        "total_trades": len(trades),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "long_trades": long_count,
        "short_trades": short_count,
        "trend_flip_exits": sum(1 for t in trades if t.get("exit_reason") == "trend_flip"),
        "resistance_bounce_exits": sum(1 for t in trades if t.get("exit_reason") == "resistance_bounce"),
        "support_bounce_exits": sum(1 for t in trades if t.get("exit_reason") == "support_bounce"),
        "end_of_data_exits": sum(1 for t in trades if t.get("exit_reason") == "end_of_data"),
        "win_rate_pct": round(wr * 100, 1),
        "final_capital": round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "avg_gain_pct": round(avg_gain, 2),   # dollar-weighted avg gain
        "avg_loss_pct": round(avg_loss, 2),   # dollar-weighted avg loss
        "max_drawdown_pct": round(-max_dd, 2),
        "profit_factor": pf,
        "sharpe_ratio": sharpe,
        "expectancy_pct": round(wr * avg_gain + (1 - wr) * avg_loss, 2),  # dollar-weighted
    }


def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    pivot_lookback: int = PIVOT_LOOKBACK,
    min_touches: int = MIN_TOUCHES,
    tolerance: float = TOLERANCE,
    confirm_bars: int = CONFIRM_BARS,
    vol_ma_period: int = VOL_MA_PERIOD,
    vol_base_pct: float = VOL_BASE_PCT,
    vol_floor_pct: float = VOL_FLOOR_PCT,
    vol_ceiling_pct: float = VOL_CEILING_PCT,
    enable_short: bool = ENABLE_SHORT,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    raw_trades = run_enhanced_lines(
        candles, pivot_lookback, min_touches, tolerance, confirm_bars,
        vol_ma_period, vol_base_pct, vol_floor_pct, vol_ceiling_pct, enable_short,
        initial_capital,
    )
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "enhanced_lines",
        "strategy_label": (
            f"Enhanced Lines (pivot={pivot_lookback}, touches={min_touches}, "
            f"tol={tolerance*100:.1f}%, confirm={confirm_bars})"
        ),
        "parameters": {
            "pivot_lookback": pivot_lookback,
            "min_touches": min_touches,
            "tolerance": tolerance,
            "confirm_bars": confirm_bars,
            "vol_ma_period": vol_ma_period,
            "vol_base_pct": vol_base_pct,
            "vol_floor_pct": vol_floor_pct,
            "vol_ceiling_pct": vol_ceiling_pct,
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
    parser = argparse.ArgumentParser(
        description="Enhanced Lines (Channel Bounce) Strategy Backtester"
    )
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["30m", "1h", "1d"],
                        help="Candle size (default: 1h)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT,
                        help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT,
                        help="Slippage %% per trade")
    parser.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK,
                        help="Bars left/right for swing detection (default: 5)")
    parser.add_argument("--min-touches", type=int, default=MIN_TOUCHES, choices=[2, 3],
                        help="Points for trendline fit (default: 3)")
    parser.add_argument("--tolerance", type=float, default=TOLERANCE,
                        help="Tolerance for trendline proximity (default: 0.015 = 1.5%%)")
    parser.add_argument("--confirm-bars", type=int, default=CONFIRM_BARS,
                        help="Consecutive bars to confirm bounce (default: 2)")
    parser.add_argument("--vol-ma-period", type=int, default=VOL_MA_PERIOD,
                        help="Volume SMA period (default: 20)")
    parser.add_argument("--vol-base-pct", type=float, default=VOL_BASE_PCT,
                        help="Base position size fraction (default: 0.25)")
    parser.add_argument("--vol-floor-pct", type=float, default=VOL_FLOOR_PCT,
                        help="Minimum position size fraction (default: 0.20)")
    parser.add_argument("--vol-ceiling-pct", type=float, default=VOL_CEILING_PCT,
                        help="Maximum position size fraction (default: 0.80)")
    parser.add_argument("--no-short", action="store_true",
                        help="Disable short selling")
    args = parser.parse_args()

    enable_short = not args.no_short

    print(f"\n{'='*60}")
    print(f"  Enhanced Lines Strategy — {args.symbol}")
    print(f"  Pivots: {args.pivot_lookback}  |  Touches: {args.min_touches}  |  Tolerance: {args.tolerance*100:.1f}%")
    print(f"  Confirm: {args.confirm_bars} bars  |  Shorts: {'ON' if enable_short else 'OFF'}")
    print(f"  Vol sizing: base={args.vol_base_pct:.0%} floor={args.vol_floor_pct:.0%} ceiling={args.vol_ceiling_pct:.0%}")
    print(f"  Interval: {args.interval}  |  Period: {args.period}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_lookback=args.pivot_lookback, min_touches=args.min_touches,
        tolerance=args.tolerance, confirm_bars=args.confirm_bars,
        vol_ma_period=args.vol_ma_period, vol_base_pct=args.vol_base_pct,
        vol_floor_pct=args.vol_floor_pct, vol_ceiling_pct=args.vol_ceiling_pct,
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
    print(f"  Exits:            Trend Flip: {result['trend_flip_exits']}  |  Resistance Bounce: {result['resistance_bounce_exits']}  |  Support Bounce: {result['support_bounce_exits']}  |  EOD: {result['end_of_data_exits']}")

    if result["trade_log"]:
        print(f"\n  Trade Log:")
        for t in result["trade_log"]:
            side = t["side"].upper()
            shares_str = f"{t.get('shares', 0):.2f}sh" if "shares" in t else ""
            print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
                  f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
                  f"{t['return_pct']:+7.2f}%  {shares_str:>10s}  [{t.get('exit_reason', 'n/a')}]")
    else:
        print(f"\n  No trades generated.")

    print(f"\n{'='*60}\n")

    fname = f"enhanced_lines_backtest_{args.symbol.replace('-', '_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
