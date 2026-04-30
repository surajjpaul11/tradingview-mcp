"""
Higher Highs Strategy — Standalone Python Implementation
=========================================================

Multi-timeframe market structure strategy with re-entry and trailing stop.

Higher timeframe (4H default):
  Detects trend via swing point structure:
    Bullish = 3+ consecutive higher highs AND higher lows
    Bearish = 3+ consecutive lower highs AND lower lows

Lower timeframe (1h default):
  Times entries on pullbacks:
    Long  entry = LTF higher low confirmed while HTF is bullish
    Short entry = LTF lower high confirmed while HTF is bearish

  Exits (default: structure + exhaustion only):
    1. HTF structure flip — exit long when HTF flips bearish (3+ LL/LH), exit short when bullish
    2. Trend exhaustion — composite detector (RSI divergence + volume dry-up + ATR spike), 2/3 needed
    3. ATR trailing stop — optional safety net (disabled by default, enable with --trail-enabled)

  Re-entry: after exit, can re-enter if HTF structure re-establishes.

Usage:
  python higher_highs_strategy.py                              # defaults: BTC-USD, 6mo, 1h
  python higher_highs_strategy.py --symbol ETH-USD --period 1y
  python higher_highs_strategy.py --symbol AAPL --period 6mo
  python higher_highs_strategy.py --interval 1d --htf-mult 5   # daily entries, weekly structure

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

PIVOT_LOOKBACK   = 5       # bars left/right to confirm a swing point
MIN_SWINGS       = 3       # consecutive HH/HL or LL/LH to confirm trend + trigger exit
HTF_MULTIPLIER   = 4       # LTF bars per HTF bar (4 x 1h = 4h)
STRUCT_TOLERANCE = 0.03    # 3% tolerance for HH/HL/LL/LH detection (filters noise)
INTERVAL         = "1h"    # lower timeframe candle size
PERIOD           = "6mo"   # data lookback
TRAIL_ENABLED    = False    # V3: trailing stop disabled by default (struct+exhaust exits only)
TRAIL_ATR_PERIOD = 14      # ATR period for trailing stop (when enabled)
TRAIL_ATR_MULT   = 5.0     # trailing stop distance (ATR multiplier, when enabled)
RSI_PERIOD       = 14      # RSI for exhaustion detection
VOL_MA_PERIOD    = 20      # volume moving average for divergence
ATR_SPIKE_MULT   = 2.0     # ATR spike = current ATR > this * avg ATR
EXHAUST_LOOKBACK = 50      # bars to look back for divergence
EXHAUST_MIN      = 2       # signals needed out of 3 to trigger exit
INITIAL_CAPITAL  = 10_000.0
COMMISSION_PCT   = 0.1
SLIPPAGE_PCT     = 0.05


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "1mo", interval: str = "30m") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "higher-highs-strategy/1.0"})
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


def calc_rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    """Relative Strength Index (Wilder's smoothing)."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period + 1:
        return result
    gains = []
    losses = []
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100.0
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        result[i] = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100.0
    return result


def calc_vol_ma(volumes: list[float], period: int = 20) -> list[Optional[float]]:
    """Simple moving average of volume."""
    n = len(volumes)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    for i in range(period - 1, n):
        result[i] = sum(volumes[i - period + 1 : i + 1]) / period
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


# ==============================================================================
# SWING POINT DETECTION
# ==============================================================================

def find_swings(highs: list[float], lows: list[float], lookback: int = 5
                ) -> tuple[list[tuple[int, float, int]], list[tuple[int, float, int]]]:
    """
    Detect swing highs and swing lows via pivot logic.

    A swing high at bar i: high[i] is the max of [i-lookback .. i+lookback]
    A swing low  at bar i: low[i]  is the min of [i-lookback .. i+lookback]

    Returns:
      swing_highs: list of (bar_index, price, confirmed_at_bar)
      swing_lows:  list of (bar_index, price, confirmed_at_bar)

    confirmed_at_bar = bar_index + lookback (we need lookback bars to the right)
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
# HTF CANDLE AGGREGATION
# ==============================================================================

def aggregate_candles(candles: list[dict], factor: int = 8) -> list[dict]:
    """
    Aggregate lower-timeframe candles into higher-timeframe bars.

    E.g. factor=8: every 8 x 30-min candles → one 4-hour bar.
    """
    htf: list[dict] = []
    for start in range(0, len(candles), factor):
        chunk = candles[start : start + factor]
        if not chunk:
            continue
        htf.append({
            "date":   chunk[0]["date"],
            "open":   chunk[0]["open"],
            "high":   max(c["high"] for c in chunk),
            "low":    min(c["low"] for c in chunk),
            "close":  chunk[-1]["close"],
            "volume": sum(c["volume"] for c in chunk),
        })
    return htf


# ==============================================================================
# STRUCTURE ASSESSMENT
# ==============================================================================

def get_structure(confirmed_highs: list[tuple[int, float]],
                  confirmed_lows: list[tuple[int, float]],
                  min_swings: int = 2,
                  tolerance: float = 0.0) -> str:
    """
    Assess market structure from confirmed swing points.

    Need min_swings consecutive higher/lower readings (min_swings+1 total points).
    Tolerance: a swing low is still "higher" if it's within tolerance % of the previous.
      e.g. tolerance=0.03 means $100 → $97 still counts as a higher low (within 3%).

    Returns: "bullish", "bearish", or "neutral"
    """
    need = min_swings + 1
    if len(confirmed_highs) < need or len(confirmed_lows) < need:
        return "neutral"

    rh = [p for _, p in confirmed_highs[-need:]]
    rl = [p for _, p in confirmed_lows[-need:]]

    # With tolerance: "higher" means current >= prev * (1 - tolerance)
    # "lower" means current <= prev * (1 + tolerance)
    hh = all(rh[j + 1] >= rh[j] * (1 - tolerance) for j in range(min_swings))
    hl = all(rl[j + 1] >= rl[j] * (1 - tolerance) for j in range(min_swings))
    lh = all(rh[j + 1] <= rh[j] * (1 + tolerance) for j in range(min_swings))
    ll = all(rl[j + 1] <= rl[j] * (1 + tolerance) for j in range(min_swings))

    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "neutral"


# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_higher_highs(
    candles: list[dict],
    pivot_lookback: int = PIVOT_LOOKBACK,
    min_swings: int = MIN_SWINGS,
    htf_multiplier: int = HTF_MULTIPLIER,
    long_only: bool = False,
    trail_atr_period: int = TRAIL_ATR_PERIOD,
    trail_atr_mult: float = TRAIL_ATR_MULT,
    rsi_period: int = RSI_PERIOD,
    vol_ma_period: int = VOL_MA_PERIOD,
    atr_spike_mult: float = ATR_SPIKE_MULT,
    exhaust_lookback: int = EXHAUST_LOOKBACK,
    exhaust_min: int = EXHAUST_MIN,
    struct_tolerance: float = STRUCT_TOLERANCE,
    trail_enabled: bool = TRAIL_ENABLED,
    min_profit_to_trail: float = 0.0,
    min_hold_bars: int = 0,
) -> list[dict]:
    """
    Multi-timeframe market structure strategy with trailing stop, re-entry,
    and trend exhaustion detection.

    Extra exit controls:
      trail_enabled: if False, trailing stop is disabled entirely (structure + exhaustion only)
      min_profit_to_trail: only start checking trailing stop after trade is up this % (e.g. 2.0)
      min_hold_bars: don't check trailing stop for the first N bars of a trade

    Returns list of trade dicts.
    """
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]

    # --- Indicators ---
    atr    = calc_atr(highs, lows, closes, trail_atr_period)
    rsi    = calc_rsi(closes, rsi_period)
    vol_ma = calc_vol_ma(volumes, vol_ma_period)
    atr_ma = calc_atr_ma(atr, exhaust_lookback)

    # --- HTF: aggregate and find swings ---
    htf_candles = aggregate_candles(candles, htf_multiplier)
    htf_highs   = [c["high"] for c in htf_candles]
    htf_lows    = [c["low"]  for c in htf_candles]
    htf_sh, htf_sl = find_swings(htf_highs, htf_lows, pivot_lookback)

    # Convert HTF confirmed_at to LTF bar index
    htf_sh_ltf = [(idx, price, (conf + 1) * htf_multiplier - 1) for idx, price, conf in htf_sh]
    htf_sl_ltf = [(idx, price, (conf + 1) * htf_multiplier - 1) for idx, price, conf in htf_sl]

    # --- LTF: find swings ---
    ltf_sh, ltf_sl = find_swings(highs, lows, pivot_lookback)

    # --- Main loop: iterate LTF bars ---
    trades: list[dict]   = []
    position: dict | None = None

    # Progressive tracking of confirmed swings
    htf_confirmed_highs: list[tuple[int, float]] = []
    htf_confirmed_lows:  list[tuple[int, float]] = []
    ltf_confirmed_highs: list[tuple[int, float]] = []
    ltf_confirmed_lows:  list[tuple[int, float]] = []

    htf_sh_ptr = htf_sl_ptr = ltf_sh_ptr = ltf_sl_ptr = 0

    for i in range(len(candles)):
        date  = candles[i]["date"]
        price = closes[i]
        high  = highs[i]
        low   = lows[i]

        # Confirm new HTF swings
        while htf_sh_ptr < len(htf_sh_ltf) and htf_sh_ltf[htf_sh_ptr][2] <= i:
            htf_confirmed_highs.append(htf_sh_ltf[htf_sh_ptr][:2])
            htf_sh_ptr += 1
        while htf_sl_ptr < len(htf_sl_ltf) and htf_sl_ltf[htf_sl_ptr][2] <= i:
            htf_confirmed_lows.append(htf_sl_ltf[htf_sl_ptr][:2])
            htf_sl_ptr += 1

        # Confirm new LTF swings
        new_ltf_high = new_ltf_low = False
        while ltf_sh_ptr < len(ltf_sh) and ltf_sh[ltf_sh_ptr][2] <= i:
            ltf_confirmed_highs.append(ltf_sh[ltf_sh_ptr][:2])
            ltf_sh_ptr += 1
            new_ltf_high = True
        while ltf_sl_ptr < len(ltf_sl) and ltf_sl[ltf_sl_ptr][2] <= i:
            ltf_confirmed_lows.append(ltf_sl[ltf_sl_ptr][:2])
            ltf_sl_ptr += 1
            new_ltf_low = True

        # --- Check exits ---
        if position is not None:
            htf_struct = get_structure(htf_confirmed_highs, htf_confirmed_lows, min_swings, struct_tolerance)
            exit_reason = None

            if position["side"] == "long":
                # Update trailing stop
                if high > position["peak"]:
                    position["peak"] = high
                    position["peak_bar"] = i
                    if atr[i] is not None and trail_enabled:
                        position["trail_stop"] = max(position["trail_stop"], high - atr[i] * trail_atr_mult)
                    # Track RSI at peak price for divergence
                    if rsi[i] is not None:
                        position["peak_rsi"] = rsi[i]
                    if vol_ma[i] is not None:
                        position["peak_vol_ma"] = vol_ma[i]

                # Exit 1: trailing stop hit (respects trail_enabled, min_profit_to_trail, min_hold_bars)
                bars_held = i - position["entry_bar"]
                unrealized_pct = (price - position["entry_price"]) / position["entry_price"] * 100
                trail_active = (trail_enabled
                                and bars_held >= min_hold_bars
                                and unrealized_pct >= min_profit_to_trail)
                if trail_active and low <= position["trail_stop"]:
                    exit_reason = "trailing_stop"
                    exit_price = position["trail_stop"]
                else:
                    # Exit 2: trend exhaustion (2/3 signals)
                    exhaust_signals = 0

                    # Signal A: Bearish RSI divergence — price at/near peak but RSI lower
                    if (rsi[i] is not None and position.get("peak_rsi") is not None
                            and high >= position["peak"] * 0.99
                            and rsi[i] < position["peak_rsi"] - 5):
                        exhaust_signals += 1

                    # Signal B: Volume dry-up — vol MA declining while price rising
                    if (vol_ma[i] is not None and position.get("peak_vol_ma") is not None
                            and vol_ma[i] < position["peak_vol_ma"] * 0.8):
                        exhaust_signals += 1

                    # Signal C: ATR spike — blow-off top volatility
                    if (atr[i] is not None and atr_ma[i] is not None
                            and atr[i] > atr_ma[i] * atr_spike_mult):
                        exhaust_signals += 1

                    if exhaust_signals >= exhaust_min:
                        exit_reason = "exhaustion"
                        exit_price = price
                    # Exit 3: HTF structure flips bearish (3+ LL/LH confirmed)
                    elif htf_struct == "bearish":
                        exit_reason = "htf_structure_flip"
                        exit_price = price

            elif position["side"] == "short":
                # Update trailing stop
                if low < position["trough"]:
                    position["trough"] = low
                    position["trough_bar"] = i
                    if atr[i] is not None and trail_enabled:
                        position["trail_stop"] = min(position["trail_stop"], low + atr[i] * trail_atr_mult)
                    if rsi[i] is not None:
                        position["trough_rsi"] = rsi[i]
                    if vol_ma[i] is not None:
                        position["trough_vol_ma"] = vol_ma[i]

                # Exit 1: trailing stop hit
                bars_held = i - position["entry_bar"]
                unrealized_pct = (position["entry_price"] - price) / position["entry_price"] * 100
                trail_active = (trail_enabled
                                and bars_held >= min_hold_bars
                                and unrealized_pct >= min_profit_to_trail)
                if trail_active and high >= position["trail_stop"]:
                    exit_reason = "trailing_stop"
                    exit_price = position["trail_stop"]
                else:
                    # Exit 2: trend exhaustion (bullish divergence on shorts)
                    exhaust_signals = 0

                    # Signal A: Bullish RSI divergence — price at/near trough but RSI higher
                    if (rsi[i] is not None and position.get("trough_rsi") is not None
                            and low <= position["trough"] * 1.01
                            and rsi[i] > position["trough_rsi"] + 5):
                        exhaust_signals += 1

                    # Signal B: Volume dry-up on down move
                    if (vol_ma[i] is not None and position.get("trough_vol_ma") is not None
                            and vol_ma[i] < position["trough_vol_ma"] * 0.8):
                        exhaust_signals += 1

                    # Signal C: ATR spike
                    if (atr[i] is not None and atr_ma[i] is not None
                            and atr[i] > atr_ma[i] * atr_spike_mult):
                        exhaust_signals += 1

                    if exhaust_signals >= exhaust_min:
                        exit_reason = "exhaustion"
                        exit_price = price
                    # Exit 3: HTF structure flips bullish (3+ HH/HL confirmed)
                    elif htf_struct == "bullish":
                        exit_reason = "htf_structure_flip"
                        exit_price = price

            if exit_reason:
                trades.append({
                    "entry_date":  position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date":   date,
                    "exit_price":  exit_price,
                    "side":        position["side"],
                    "exit_reason": exit_reason,
                    "strategy":    "higher_highs",
                })
                position = None

        # --- Check entries (LTF pullback aligned with HTF structure) ---
        if position is None:
            htf_struct = get_structure(htf_confirmed_highs, htf_confirmed_lows, min_swings, struct_tolerance)

            # Long: HTF bullish + LTF higher low just confirmed
            if htf_struct == "bullish" and new_ltf_low and len(ltf_confirmed_lows) >= 2:
                if ltf_confirmed_lows[-1][1] >= ltf_confirmed_lows[-2][1] * (1 - struct_tolerance):
                    if trail_enabled and atr[i] is not None:
                        initial_stop = low - atr[i] * trail_atr_mult
                    elif trail_enabled:
                        initial_stop = low * 0.95
                    else:
                        initial_stop = -float("inf")
                    position = {
                        "entry_date":  date,
                        "entry_price": price,
                        "entry_bar":   i,
                        "side":        "long",
                        "peak":        high,
                        "peak_bar":    i,
                        "peak_rsi":    rsi[i],
                        "peak_vol_ma": vol_ma[i],
                        "trail_stop":  initial_stop,
                    }

            # Short: HTF bearish + LTF lower high just confirmed
            elif not long_only and htf_struct == "bearish" and new_ltf_high and len(ltf_confirmed_highs) >= 2:
                if ltf_confirmed_highs[-1][1] <= ltf_confirmed_highs[-2][1] * (1 + struct_tolerance):
                    if trail_enabled and atr[i] is not None:
                        initial_stop = high + atr[i] * trail_atr_mult
                    elif trail_enabled:
                        initial_stop = high * 1.05
                    else:
                        initial_stop = float("inf")
                    position = {
                        "entry_date":    date,
                        "entry_price":   price,
                        "entry_bar":     i,
                        "side":          "short",
                        "trough":        low,
                        "trough_bar":    i,
                        "trough_rsi":    rsi[i],
                        "trough_vol_ma": vol_ma[i],
                        "trail_stop":    initial_stop,
                    }

    # Close any open position at end of data
    if position is not None:
        trades.append({
            "entry_date":  position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date":   candles[-1]["date"],
            "exit_price":  candles[-1]["close"],
            "side":        position["side"],
            "exit_reason": "end_of_data",
            "strategy":    "higher_highs",
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


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "30m") -> dict:
    """Calculate backtest metrics."""
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "long_trades": 0, "short_trades": 0, "structure_exits": 0,
                "trailing_exits": 0, "exhaustion_exits": 0, "end_of_data_exits": 0, "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252 * 13)

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

    wr = len(winners) / len(trades)
    long_count  = sum(1 for t in trades if t["side"] == "long")
    short_count = sum(1 for t in trades if t["side"] == "short")
    struct_exits  = sum(1 for t in trades if t.get("exit_reason") == "htf_structure_flip")
    trail_exits   = sum(1 for t in trades if t.get("exit_reason") == "trailing_stop")
    exhaust_exits = sum(1 for t in trades if t.get("exit_reason") == "exhaustion")
    eod_exits     = sum(1 for t in trades if t.get("exit_reason") == "end_of_data")

    return {
        "total_trades":       len(trades),
        "winning_trades":     len(winners),
        "losing_trades":      len(losers),
        "long_trades":        long_count,
        "short_trades":       short_count,
        "structure_exits":    struct_exits,
        "trailing_exits":     trail_exits,
        "exhaustion_exits":   exhaust_exits,
        "end_of_data_exits":  eod_exits,
        "win_rate_pct":       round(wr * 100, 1),
        "final_capital":      round(capital, 2),
        "total_return_pct":   round(total_ret, 2),
        "avg_gain_pct":       round(avg_gain, 2),
        "avg_loss_pct":       round(avg_loss, 2),
        "max_drawdown_pct":   round(-max_dd, 2),
        "profit_factor":      pf,
        "sharpe_ratio":       sharpe,
        "expectancy_pct":     round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }


def run_backtest(
    symbol: str = "BTC-USD",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    pivot_lookback: int = PIVOT_LOOKBACK,
    min_swings: int = MIN_SWINGS,
    htf_multiplier: int = HTF_MULTIPLIER,
    long_only: bool = False,
    trail_atr_period: int = TRAIL_ATR_PERIOD,
    trail_atr_mult: float = TRAIL_ATR_MULT,
    rsi_period: int = RSI_PERIOD,
    vol_ma_period: int = VOL_MA_PERIOD,
    atr_spike_mult: float = ATR_SPIKE_MULT,
    exhaust_lookback: int = EXHAUST_LOOKBACK,
    exhaust_min: int = EXHAUST_MIN,
    struct_tolerance: float = STRUCT_TOLERANCE,
    trail_enabled: bool = TRAIL_ENABLED,
    min_profit_to_trail: float = 0.0,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    raw_trades = run_higher_highs(candles, pivot_lookback, min_swings, htf_multiplier,
                                  long_only, trail_atr_period, trail_atr_mult,
                                  rsi_period, vol_ma_period, atr_spike_mult,
                                  exhaust_lookback, exhaust_min, struct_tolerance,
                                  trail_enabled, min_profit_to_trail)
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    htf_label = {
        8: "4H", 4: "4H", 2: "2x", 5: "Weekly", 10: "10x",
    }.get(htf_multiplier, f"{htf_multiplier}x")

    return {
        "symbol": symbol.upper(),
        "strategy": "higher_highs",
        "strategy_label": f"Higher Highs / Lower Lows (MTF: {interval} + {htf_label})",
        "parameters": {
            "pivot_lookback": pivot_lookback,
            "min_swings": min_swings,
            "htf_multiplier": htf_multiplier,
            "interval": interval,
            "struct_tolerance": struct_tolerance,
        },
        "period": period,
        "interval": interval,
        "candles_analyzed": len(candles),
        "htf_bars": len(candles) // htf_multiplier,
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
    parser = argparse.ArgumentParser(description="Higher Highs / Lower Lows Strategy Backtester")
    parser.add_argument("--symbol", default="BTC-USD", help="Yahoo Finance symbol (default: BTC-USD)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 1mo). Use 5d/1mo for 30m, longer for 1h/1d")
    parser.add_argument("--interval", default=INTERVAL, choices=["30m", "1h", "1d"], help="LTF candle size (default: 30m)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK, help="Bars left/right for swing detection (default: 5)")
    parser.add_argument("--min-swings", type=int, default=MIN_SWINGS, help="Consecutive HH/HL or LL/LH for trend (default: 2)")
    parser.add_argument("--htf-mult", type=int, default=HTF_MULTIPLIER, help="LTF bars per HTF bar (default: 8, i.e. 8x30m=4h)")
    parser.add_argument("--long-only", action="store_true", help="Only take long trades (no shorts)")
    parser.add_argument("--trail-atr-period", type=int, default=TRAIL_ATR_PERIOD, help="ATR period for trailing stop (default: 14)")
    parser.add_argument("--trail-atr-mult", type=float, default=TRAIL_ATR_MULT, help="Trailing stop ATR multiplier (default: 5.0)")
    parser.add_argument("--struct-tolerance", type=float, default=STRUCT_TOLERANCE, help="Structure tolerance %% (default: 0.03 = 3%%)")
    parser.add_argument("--trail-enabled", action="store_true", default=TRAIL_ENABLED, help="Enable trailing stop (default: off)")
    parser.add_argument("--min-profit-to-trail", type=float, default=0.0, help="Min unrealized profit %% before trailing activates (default: 0)")
    args = parser.parse_args()

    htf_label = {
        8: "4H", 4: "4H", 2: "2x", 5: "Weekly",
    }.get(args.htf_mult, f"{args.htf_mult}x")

    print(f"\n{'='*60}")
    print(f"  Higher Highs Strategy — {args.symbol}")
    print(f"  LTF: {args.interval}  |  HTF: {htf_label}  |  Pivots: {args.pivot_lookback}L/{args.pivot_lookback}R")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_lookback=args.pivot_lookback, min_swings=args.min_swings,
        htf_multiplier=args.htf_mult, long_only=args.long_only,
        trail_atr_period=args.trail_atr_period, trail_atr_mult=args.trail_atr_mult,
        struct_tolerance=args.struct_tolerance,
        trail_enabled=args.trail_enabled,
        min_profit_to_trail=args.min_profit_to_trail,
    )

    print(f"  Period:           {result['date_from']} -> {result['date_to']} ({result['candles_analyzed']} LTF bars, {result['htf_bars']} HTF bars)")
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
    print(f"  Exits:            Exhaust: {result['exhaustion_exits']}  |  Trail: {result['trailing_exits']}  |  Struct: {result['structure_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    fname = script_dir / f"higher_highs_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
