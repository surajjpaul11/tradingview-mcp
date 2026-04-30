# Enhanced Straight Lines Strategy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a channel-based trend-following strategy that tracks support/resistance trendlines using the last N touches, determines trend via slope agreement, trades bounces with volume-weighted position sizing, and handles partial sells for tax optimization in uptrends.

**Architecture:** Standalone Python script (`strategies/enhanced_lines_strategy.py`) following the same pattern as `strategies/straight_line_strategy.py` — self-contained with data fetching, indicators, strategy engine, metrics, and CLI. Also integrate into the backtest engine (`backtest_service.py`) and update MCP tool registration in `server.py`.

**Tech Stack:** Python 3.10+ stdlib only (no external deps). Yahoo Finance for OHLCV data.

**Spec:** `docs/superpowers/specs/2026-04-01-enhanced-lines-strategy-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `strategies/enhanced_lines_strategy.py` | Create | Standalone strategy: data fetch, swing detection, trendline fitting, bounce detection, trend determination, position manager, volume sizing, metrics, CLI |
| `src/tradingview_mcp/core/services/backtest_service.py` | Modify (lines 38-47, 485-494) | Add `_run_enhanced_lines()`, register in `_STRATEGY_MAP` and `_STRATEGY_LABELS` |
| `src/tradingview_mcp/server.py` | Modify (line ~2994) | Add `enhanced_lines` to strategy docstring |
| `strategies/compare_enhanced_lines.py` | Create | Comparison script: enhanced_lines vs straight_line vs B&H |
| `strategies/STRATEGIES.md` | Modify | Add Enhanced Lines strategy documentation |

---

### Task 1: Core Indicators and Swing Detection

**Files:**
- Create: `strategies/enhanced_lines_strategy.py`

Build the foundation: data fetching, swing detection, SMA for volume baseline.

- [ ] **Step 1: Create file with module docstring, imports, and constants**

```python
"""
Enhanced Straight Lines Strategy — Standalone Python Implementation
===================================================================

Channel-based trend following with volume-weighted position sizing.

Logic:
  - Track support (higher lows / lower lows) and resistance (higher highs / lower highs)
    trendlines using the last N touches (default 3, configurable to 2)
  - Determine trend by relative agreement of both trendline slopes
  - Trade bounces within the channel with volume-weighted sizing (20-80%)
  - Tax-optimized: partial sells in uptrend, full exit only on regime change
  - Short on confirmed resistance bounce in downtrend channel

Bounce detection:
  - Price enters tolerance zone (1.5%) near trendline
  - 2 consecutive candles confirm the reversal direction
  - Volume of those 2 bars determines position size

Usage:
  python enhanced_lines_strategy.py                                    # defaults: SPY, 2y, 1h
  python enhanced_lines_strategy.py --symbol BTC-USD --period 1y
  python enhanced_lines_strategy.py --symbol QQQ --min-touches 2
  python enhanced_lines_strategy.py --symbol AAPL --no-short

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

PIVOT_LOOKBACK       = 5       # bars left/right for swing point detection
MIN_TOUCHES          = 3       # swing points to fit trendline (2 or 3)
TOLERANCE            = 0.015   # 1.5% zone for bounce detection
CONFIRM_BARS         = 2       # consecutive candles to confirm bounce
VOL_MA_PERIOD        = 20      # volume MA baseline period
VOL_BASE_PCT         = 0.25    # trade_pct = vol_ratio * this
VOL_FLOOR_PCT        = 0.20    # minimum trade size
VOL_CEILING_PCT      = 0.80    # maximum trade size
ENABLE_SHORT         = True    # enable short positions in downtrend
INTERVAL             = "1h"    # candle size
PERIOD               = "2y"    # data lookback
INITIAL_CAPITAL      = 10_000.0
COMMISSION_PCT       = 0.1
SLIPPAGE_PCT         = 0.05
```

- [ ] **Step 2: Add data fetching function**

```python
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
```

- [ ] **Step 3: Add swing detection function**

Same pivot logic as `straight_line_strategy.py` — reused pattern.

```python
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
```

- [ ] **Step 4: Add volume SMA helper**

```python
# ==============================================================================
# VOLUME HELPERS
# ==============================================================================

def calc_vol_sma(volumes: list[float], period: int = 20) -> list[Optional[float]]:
    """Simple Moving Average of volume."""
    n = len(volumes)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    for i in range(period - 1, n):
        result[i] = sum(volumes[i - period + 1 : i + 1]) / period
    return result
```

- [ ] **Step 5: Verify file runs without errors**

Run: `python strategies/enhanced_lines_strategy.py` — should fail with "no main" but no import errors. Add a temporary `if __name__ == "__main__": print("OK")` at bottom and run.

- [ ] **Step 6: Commit**

```bash
git add strategies/enhanced_lines_strategy.py
git commit -m "feat(enhanced-lines): add data fetching, swing detection, and volume SMA"
```

---

### Task 2: Trendline Fitting with Last-N-Touches

**Files:**
- Modify: `strategies/enhanced_lines_strategy.py`

Build the trendline engine that uses only the last N swing points.

- [ ] **Step 1: Add trendline_value helper**

```python
# ==============================================================================
# TRENDLINE LOGIC
# ==============================================================================

def trendline_value(p1: tuple[int, float], p2: tuple[int, float], bar: int) -> float:
    """Calculate projected trendline value at a given bar index."""
    b1, v1 = p1
    b2, v2 = p2
    if b2 == b1:
        return v1
    slope = (v2 - v1) / (b2 - b1)
    return v1 + slope * (bar - b1)


def trendline_slope_per_bar(p1: tuple[int, float], p2: tuple[int, float]) -> float:
    """Price change per bar (slope) of a trendline."""
    b1, v1 = p1
    b2, v2 = p2
    if b2 == b1:
        return 0.0
    return (v2 - v1) / (b2 - b1)
```

- [ ] **Step 2: Add fit_trendline using last N touches**

This is the core difference from straight_line — we only use the last `min_touches` points and require them to be roughly collinear (within tolerance).

```python
def fit_trendline(
    points: list[tuple[int, float]],
    min_touches: int = 3,
    tolerance: float = 0.015,
    direction: str = "ascending",
) -> dict | None:
    """
    Fit a trendline through the last `min_touches` swing points.

    Only uses the most recent points. Validates that all points are within
    tolerance of the line drawn through the first and last of the N points.
    Direction must be "ascending" (each point higher) or "descending" (each lower).

    Returns dict with anchor1, anchor2, slope_per_bar, all_points, or None if no fit.
    """
    if len(points) < min_touches:
        return None

    # Take only the last min_touches points
    recent = points[-min_touches:]

    # Check direction
    if direction == "ascending":
        if not all(recent[i + 1][1] > recent[i][1] for i in range(len(recent) - 1)):
            return None
    elif direction == "descending":
        if not all(recent[i + 1][1] < recent[i][1] for i in range(len(recent) - 1)):
            return None

    # Use first and last of the N points as anchors
    anchor1 = recent[0]
    anchor2 = recent[-1]

    # Validate all intermediate points are within tolerance of the line
    for pt in recent[1:-1]:
        projected = trendline_value(anchor1, anchor2, pt[0])
        if projected <= 0:
            return None
        deviation = abs(pt[1] - projected) / projected
        if deviation > tolerance:
            return None

    return {
        "anchor1": anchor1,
        "anchor2": anchor2,
        "slope_per_bar": trendline_slope_per_bar(anchor1, anchor2),
        "all_points": recent,
        "last_bar": anchor2[0],
    }
```

- [ ] **Step 3: Add function to build all 4 trendline types from current swings**

```python
def build_channel(
    confirmed_highs: list[tuple[int, float]],
    confirmed_lows: list[tuple[int, float]],
    min_touches: int = 3,
    tolerance: float = 0.015,
) -> dict:
    """
    Attempt to build all 4 trendline types from confirmed swing points.

    Returns dict with keys: higher_highs, higher_lows, lower_highs, lower_lows.
    Each value is a trendline dict or None.
    """
    return {
        "higher_highs": fit_trendline(confirmed_highs, min_touches, tolerance, "ascending"),
        "higher_lows":  fit_trendline(confirmed_lows, min_touches, tolerance, "ascending"),
        "lower_highs":  fit_trendline(confirmed_highs, min_touches, tolerance, "descending"),
        "lower_lows":   fit_trendline(confirmed_lows, min_touches, tolerance, "descending"),
    }
```

- [ ] **Step 4: Quick sanity test — run Python and call fit_trendline with test data**

Add a temporary test at the bottom:

```python
if __name__ == "__main__":
    # Ascending: 3 points going up, roughly collinear
    pts = [(10, 100.0), (20, 105.0), (30, 110.0)]
    result = fit_trendline(pts, 3, 0.015, "ascending")
    assert result is not None, "Should fit ascending trendline"
    assert abs(result["slope_per_bar"] - 0.5) < 0.01

    # Descending
    pts2 = [(10, 110.0), (20, 105.0), (30, 100.0)]
    result2 = fit_trendline(pts2, 3, 0.015, "descending")
    assert result2 is not None, "Should fit descending trendline"

    # Direction mismatch — ascending points but asking for descending
    result3 = fit_trendline(pts, 3, 0.015, "descending")
    assert result3 is None, "Direction mismatch should return None"

    # Not enough points
    result4 = fit_trendline(pts[:2], 3, 0.015, "ascending")
    assert result4 is None, "Too few points should return None"

    print("All trendline tests passed!")
```

Run: `python strategies/enhanced_lines_strategy.py`
Expected: `All trendline tests passed!`

- [ ] **Step 5: Commit**

```bash
git add strategies/enhanced_lines_strategy.py
git commit -m "feat(enhanced-lines): add trendline fitting with last-N-touches"
```

---

### Task 3: Trend Determination and Bounce Detection

**Files:**
- Modify: `strategies/enhanced_lines_strategy.py`

- [ ] **Step 1: Add trend determination function**

```python
# ==============================================================================
# TREND DETERMINATION
# ==============================================================================

def determine_trend(
    support_slope: float | None,
    resistance_slope: float | None,
    avg_price: float,
    flat_threshold_pct: float = 0.0002,
) -> str:
    """
    Determine trend from support and resistance trendline slopes.

    Uses relative agreement:
      Both up    → "uptrend"
      Both down  → "downtrend"
      Disagree or both flat → "neutral"

    flat_threshold_pct: slope per bar as fraction of avg price considered "flat".
    Default 0.02% of price per bar.

    Returns: "uptrend", "downtrend", or "neutral"
    """
    if support_slope is None or resistance_slope is None:
        return "neutral"

    # Normalize slopes to percentage of price per bar
    flat_thresh = avg_price * flat_threshold_pct

    sup_up   = support_slope > flat_thresh
    sup_down = support_slope < -flat_thresh
    sup_flat = not sup_up and not sup_down

    res_up   = resistance_slope > flat_thresh
    res_down = resistance_slope < -flat_thresh
    res_flat = not res_up and not res_down

    if sup_up and res_up:
        return "uptrend"
    if sup_down and res_down:
        return "downtrend"
    return "neutral"
```

- [ ] **Step 2: Add bounce detection function**

```python
# ==============================================================================
# BOUNCE DETECTION
# ==============================================================================

def detect_bounce(
    candles: list[dict],
    bar_idx: int,
    trendline: dict,
    direction: str,
    tolerance: float = 0.015,
    confirm_bars: int = 2,
) -> bool:
    """
    Detect a confirmed bounce at bar_idx.

    1. Price at bar_idx must be within tolerance zone of the trendline.
    2. The previous `confirm_bars` candles (ending at bar_idx) must all close
       in the bounce direction.

    Args:
        candles: full candle list
        bar_idx: current bar to check
        trendline: dict with anchor1, anchor2 keys
        direction: "up" (bounce up from support) or "down" (bounce down from resistance)
        tolerance: zone width as fraction (0.015 = 1.5%)
        confirm_bars: consecutive confirming candles required

    Returns: True if bounce confirmed at bar_idx.
    """
    if bar_idx < confirm_bars:
        return False

    projected = trendline_value(trendline["anchor1"], trendline["anchor2"], bar_idx)
    if projected <= 0:
        return False

    # Check: price is in the tolerance zone
    price = candles[bar_idx]["close"]
    deviation = abs(price - projected) / projected
    if deviation > tolerance:
        # Also check if the low (for up bounce) or high (for down bounce) entered the zone
        if direction == "up":
            low_dev = abs(candles[bar_idx]["low"] - projected) / projected
            if low_dev > tolerance and candles[bar_idx]["low"] > projected * (1 + tolerance):
                return False
        elif direction == "down":
            high_dev = abs(candles[bar_idx]["high"] - projected) / projected
            if high_dev > tolerance and candles[bar_idx]["high"] < projected * (1 - tolerance):
                return False

    # Check: confirm_bars consecutive candles in the bounce direction
    for j in range(bar_idx - confirm_bars + 1, bar_idx + 1):
        if j < 0:
            return False
        c = candles[j]
        if direction == "up" and c["close"] <= c["open"]:
            return False  # need bullish candle
        if direction == "down" and c["close"] >= c["open"]:
            return False  # need bearish candle

    return True
```

- [ ] **Step 3: Add volume-weighted position sizing function**

```python
# ==============================================================================
# VOLUME-WEIGHTED POSITION SIZING
# ==============================================================================

def calc_trade_pct(
    candles: list[dict],
    bar_idx: int,
    vol_sma: list[Optional[float]],
    confirm_bars: int = 2,
    base_pct: float = 0.25,
    floor_pct: float = 0.20,
    ceiling_pct: float = 0.80,
) -> float:
    """
    Calculate volume-weighted trade size as fraction of position.

    Uses the average volume of the last `confirm_bars` candles compared
    to the volume SMA baseline.

    Returns: fraction between floor_pct and ceiling_pct.
    """
    # Average volume of confirmation bars
    vols = []
    for j in range(bar_idx - confirm_bars + 1, bar_idx + 1):
        if 0 <= j < len(candles):
            vols.append(candles[j]["volume"])
    if not vols:
        return floor_pct

    avg_vol = sum(vols) / len(vols)

    # Get volume SMA at current bar
    sma_val = vol_sma[bar_idx] if bar_idx < len(vol_sma) else None
    if sma_val is None or sma_val <= 0:
        return floor_pct

    vol_ratio = avg_vol / sma_val
    trade_pct = vol_ratio * base_pct
    return max(floor_pct, min(ceiling_pct, trade_pct))
```

- [ ] **Step 4: Add inline tests and run**

Replace the temporary test block at the bottom:

```python
if __name__ == "__main__":
    # --- Trendline tests ---
    pts = [(10, 100.0), (20, 105.0), (30, 110.0)]
    result = fit_trendline(pts, 3, 0.015, "ascending")
    assert result is not None

    # --- Trend determination tests ---
    assert determine_trend(0.5, 0.3, 100.0) == "uptrend"
    assert determine_trend(-0.5, -0.3, 100.0) == "downtrend"
    assert determine_trend(0.5, -0.3, 100.0) == "neutral"
    assert determine_trend(0.001, 0.001, 100.0) == "neutral"  # both flat
    assert determine_trend(None, 0.5, 100.0) == "neutral"

    # --- Volume sizing tests ---
    # Mock: vol_sma = 1000, confirm bars both have vol = 2000 → ratio=2.0 → pct=50%
    mock_candles = [{"volume": 2000, "open": 100, "high": 102, "low": 99, "close": 101}] * 5
    mock_vol_sma = [1000.0] * 5
    pct = calc_trade_pct(mock_candles, 4, mock_vol_sma, 2, 0.25, 0.20, 0.80)
    assert abs(pct - 0.50) < 0.01, f"Expected ~0.50, got {pct}"

    # Floor test: very low volume
    mock_candles_low = [{"volume": 100, "open": 100, "high": 102, "low": 99, "close": 101}] * 5
    pct_low = calc_trade_pct(mock_candles_low, 4, mock_vol_sma, 2, 0.25, 0.20, 0.80)
    assert pct_low == 0.20, f"Expected floor 0.20, got {pct_low}"

    print("All trend + bounce + volume tests passed!")
```

Run: `python strategies/enhanced_lines_strategy.py`
Expected: `All trend + bounce + volume tests passed!`

- [ ] **Step 5: Commit**

```bash
git add strategies/enhanced_lines_strategy.py
git commit -m "feat(enhanced-lines): add trend determination, bounce detection, volume sizing"
```

---

### Task 4: Strategy Engine — Position Manager and Trade Logic

**Files:**
- Modify: `strategies/enhanced_lines_strategy.py`

This is the core engine. Manages positions with fractional sizing, processes signals per bar.

- [ ] **Step 1: Add the main strategy engine function**

```python
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
) -> list[dict]:
    """
    Enhanced Straight Lines strategy engine.

    Tracks channel trendlines, determines trend via slope agreement,
    trades bounces with volume-weighted sizing.

    Returns list of trade dicts with keys:
        entry_date, entry_price, exit_date, exit_price, side,
        exit_reason, strategy, shares, trade_pct
    """
    if not candles or len(candles) < pivot_lookback * 2 + 10:
        return []

    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]

    # Precompute
    swing_highs, swing_lows = find_swings(highs, lows, pivot_lookback)
    vol_sma = calc_vol_sma(volumes, vol_ma_period)

    # Progressive confirmation tracking
    confirmed_highs: list[tuple[int, float]] = []
    confirmed_lows:  list[tuple[int, float]] = []
    sh_ptr = sl_ptr = 0

    # Position state
    # position_shares: positive = long shares, negative = short shares
    # Each trade records the fractional entry/exit
    trades: list[dict] = []
    position_shares: float = 0.0  # current shares held (negative = short)
    position_entries: list[dict] = []  # open sub-positions for tracking
    max_shares: float = 0.0  # track max position for sizing
    prev_trend: str = "neutral"
    initial_capital = 10_000.0  # used for share calculation

    # Average price for slope normalization
    avg_price = sum(closes) / len(closes)

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

        # --- Build channel from current swings ---
        channel = build_channel(confirmed_highs, confirmed_lows, min_touches, tolerance)

        # --- Determine active support and resistance ---
        # Uptrend channel: higher_lows (support) + higher_highs (resistance)
        # Downtrend channel: lower_lows (support) + lower_highs (resistance)
        # Pick the pair that is most recently confirmed
        support = None
        resistance = None

        if channel["higher_lows"] and channel["higher_highs"]:
            support = channel["higher_lows"]
            resistance = channel["higher_highs"]
        elif channel["lower_lows"] and channel["lower_highs"]:
            support = channel["lower_lows"]
            resistance = channel["lower_highs"]
        elif channel["higher_lows"] and channel["lower_highs"]:
            support = channel["higher_lows"]
            resistance = channel["lower_highs"]
        elif channel["lower_lows"] and channel["higher_highs"]:
            support = channel["lower_lows"]
            resistance = channel["higher_highs"]
        elif channel["higher_lows"]:
            support = channel["higher_lows"]
        elif channel["lower_lows"]:
            support = channel["lower_lows"]
        elif channel["higher_highs"]:
            resistance = channel["higher_highs"]
        elif channel["lower_highs"]:
            resistance = channel["lower_highs"]

        # --- Determine trend ---
        sup_slope = support["slope_per_bar"] if support else None
        res_slope = resistance["slope_per_bar"] if resistance else None
        trend = determine_trend(sup_slope, res_slope, avg_price)

        # --- REGIME CHANGE: trend flip → full exit ---
        if trend != prev_trend and prev_trend != "neutral":
            # Close all longs
            if position_shares > 0:
                for entry in position_entries:
                    trades.append({
                        "entry_date":  entry["date"],
                        "entry_price": entry["price"],
                        "exit_date":   date,
                        "exit_price":  price,
                        "side":        "long",
                        "exit_reason": "trend_flip",
                        "strategy":    "enhanced_lines",
                        "shares":      entry["shares"],
                        "trade_pct":   1.0,
                    })
                position_shares = 0.0
                position_entries = []
                max_shares = 0.0

            # Close all shorts
            elif position_shares < 0:
                for entry in position_entries:
                    trades.append({
                        "entry_date":  entry["date"],
                        "entry_price": entry["price"],
                        "exit_date":   date,
                        "exit_price":  price,
                        "side":        "short",
                        "exit_reason": "trend_flip",
                        "strategy":    "enhanced_lines",
                        "shares":      entry["shares"],
                        "trade_pct":   1.0,
                    })
                position_shares = 0.0
                position_entries = []
                max_shares = 0.0

        prev_trend = trend

        # --- UPTREND SIGNALS ---
        if trend == "uptrend":
            # Bounce UP from support (higher lows) → BUY
            if support and detect_bounce(candles, i, support, "up", tolerance, confirm_bars):
                trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                           vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                if position_shares == 0:
                    # Fresh buy — trade_pct of full capital
                    buy_shares = (initial_capital * trade_pct) / price
                    max_shares = initial_capital / price  # reference: full position
                elif position_shares > 0 and max_shares > 0:
                    # Buy back after partial sell
                    available = max_shares - position_shares
                    buy_shares = available * trade_pct if available > 0 else 0
                else:
                    buy_shares = 0

                if buy_shares > 0.0001:
                    position_shares += buy_shares
                    position_entries.append({
                        "date": date, "price": price, "shares": buy_shares,
                    })

            # Bounce DOWN from resistance (higher highs) → PARTIAL SELL
            elif resistance and detect_bounce(candles, i, resistance, "down", tolerance, confirm_bars):
                if position_shares > 0:
                    trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                               vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                    sell_shares = position_shares * trade_pct
                    if sell_shares > 0.0001:
                        # Close oldest entries first (FIFO)
                        remaining_to_sell = sell_shares
                        while remaining_to_sell > 0.0001 and position_entries:
                            entry = position_entries[0]
                            if entry["shares"] <= remaining_to_sell:
                                trades.append({
                                    "entry_date":  entry["date"],
                                    "entry_price": entry["price"],
                                    "exit_date":   date,
                                    "exit_price":  price,
                                    "side":        "long",
                                    "exit_reason": "resistance_bounce",
                                    "strategy":    "enhanced_lines",
                                    "shares":      entry["shares"],
                                    "trade_pct":   trade_pct,
                                })
                                remaining_to_sell -= entry["shares"]
                                position_entries.pop(0)
                            else:
                                trades.append({
                                    "entry_date":  entry["date"],
                                    "entry_price": entry["price"],
                                    "exit_date":   date,
                                    "exit_price":  price,
                                    "side":        "long",
                                    "exit_reason": "resistance_bounce",
                                    "strategy":    "enhanced_lines",
                                    "shares":      remaining_to_sell,
                                    "trade_pct":   trade_pct,
                                })
                                entry["shares"] -= remaining_to_sell
                                remaining_to_sell = 0
                        position_shares -= sell_shares

        # --- DOWNTREND SIGNALS ---
        elif trend == "downtrend" and enable_short:
            # Bounce DOWN from resistance (lower highs) → SHORT
            if resistance and detect_bounce(candles, i, resistance, "down", tolerance, confirm_bars):
                trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                           vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                if position_shares == 0:
                    short_shares = (initial_capital * trade_pct) / price
                    max_shares = initial_capital / price
                elif position_shares < 0 and max_shares > 0:
                    available = max_shares - abs(position_shares)
                    short_shares = available * trade_pct if available > 0 else 0
                else:
                    short_shares = 0

                if short_shares > 0.0001:
                    position_shares -= short_shares
                    position_entries.append({
                        "date": date, "price": price, "shares": short_shares,
                    })

            # Bounce UP from support (lower lows) → CLOSE SHORT
            elif support and detect_bounce(candles, i, support, "up", tolerance, confirm_bars):
                if position_shares < 0:
                    trade_pct = calc_trade_pct(candles, i, vol_sma, confirm_bars,
                                               vol_base_pct, vol_floor_pct, vol_ceiling_pct)
                    cover_shares = abs(position_shares) * trade_pct
                    if cover_shares > 0.0001:
                        remaining_to_cover = cover_shares
                        while remaining_to_cover > 0.0001 and position_entries:
                            entry = position_entries[0]
                            if entry["shares"] <= remaining_to_cover:
                                trades.append({
                                    "entry_date":  entry["date"],
                                    "entry_price": entry["price"],
                                    "exit_date":   date,
                                    "exit_price":  price,
                                    "side":        "short",
                                    "exit_reason": "support_bounce",
                                    "strategy":    "enhanced_lines",
                                    "shares":      entry["shares"],
                                    "trade_pct":   trade_pct,
                                })
                                remaining_to_cover -= entry["shares"]
                                position_entries.pop(0)
                            else:
                                trades.append({
                                    "entry_date":  entry["date"],
                                    "entry_price": entry["price"],
                                    "exit_date":   date,
                                    "exit_price":  price,
                                    "side":        "short",
                                    "exit_reason": "support_bounce",
                                    "strategy":    "enhanced_lines",
                                    "shares":      remaining_to_cover,
                                    "trade_pct":   trade_pct,
                                })
                                entry["shares"] -= remaining_to_cover
                                remaining_to_cover = 0
                        position_shares += cover_shares

    # --- Close any open position at end of data ---
    if position_shares > 0:
        for entry in position_entries:
            trades.append({
                "entry_date":  entry["date"],
                "entry_price": entry["price"],
                "exit_date":   candles[-1]["date"],
                "exit_price":  candles[-1]["close"],
                "side":        "long",
                "exit_reason": "end_of_data",
                "strategy":    "enhanced_lines",
                "shares":      entry["shares"],
                "trade_pct":   1.0,
            })
    elif position_shares < 0:
        for entry in position_entries:
            trades.append({
                "entry_date":  entry["date"],
                "entry_price": entry["price"],
                "exit_date":   candles[-1]["date"],
                "exit_price":  candles[-1]["close"],
                "side":        "short",
                "exit_reason": "end_of_data",
                "strategy":    "enhanced_lines",
                "shares":      entry["shares"],
                "trade_pct":   1.0,
            })

    return trades
```

- [ ] **Step 2: Commit**

```bash
git add strategies/enhanced_lines_strategy.py
git commit -m "feat(enhanced-lines): add strategy engine with channel trading and partial position management"
```

---

### Task 5: Metrics, Reporting, and CLI

**Files:**
- Modify: `strategies/enhanced_lines_strategy.py`

- [ ] **Step 1: Add cost application function**

This handles the `shares` field for weighted return calculation:

```python
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
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3),
                        "cost_pct": round(-total_cost, 3)})
    return result
```

- [ ] **Step 2: Add metrics calculation**

```python
def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1h") -> dict:
    """Calculate backtest metrics accounting for partial position sizes."""
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "long_trades": 0, "short_trades": 0,
                "trend_flip_exits": 0, "resistance_bounce_exits": 0,
                "support_bounce_exits": 0, "end_of_data_exits": 0,
                "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252 * 6)

    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]
    long_count  = sum(1 for t in trades if t["side"] == "long")
    short_count = sum(1 for t in trades if t["side"] == "short")

    # Weighted return: each trade's return is weighted by its share of capital
    capital = initial_capital
    peak = capital
    max_dd = 0
    returns_list = []

    for t in trades:
        # Approximate: shares * price_change
        if t["side"] == "short":
            pnl = t["shares"] * (t["entry_price"] - t["exit_price"])
        else:
            pnl = t["shares"] * (t["exit_price"] - t["entry_price"])
        # Subtract costs
        cost_pct = abs(t.get("cost_pct", 0)) / 100
        cost_val = t["shares"] * t["entry_price"] * cost_pct
        pnl -= cost_val
        capital += pnl
        peak = max(peak, capital)
        dd = (peak - capital) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
        ret_pct = (pnl / (t["shares"] * t["entry_price"])) * 100 if t["shares"] * t["entry_price"] > 0 else 0
        returns_list.append(ret_pct)

    total_ret = (capital - initial_capital) / initial_capital * 100
    wr = len(winners) / len(trades) if trades else 0
    avg_gain = statistics.mean([t["return_pct"] for t in winners]) if winners else 0
    avg_loss = statistics.mean([t["return_pct"] for t in losers]) if losers else 0

    gross_gains = sum(r for r in returns_list if r > 0)
    gross_losses = abs(sum(r for r in returns_list if r < 0))
    pf = round(gross_gains / gross_losses, 2) if gross_losses > 0 else float("inf")

    if len(returns_list) >= 2:
        mean_r = statistics.mean(returns_list)
        std_r = statistics.stdev(returns_list)
        sharpe = round((mean_r / std_r) * math.sqrt(ann), 2) if std_r > 0 else 0
    else:
        sharpe = 0

    return {
        "total_trades":             len(trades),
        "winning_trades":           len(winners),
        "losing_trades":            len(losers),
        "long_trades":              long_count,
        "short_trades":             short_count,
        "trend_flip_exits":         sum(1 for t in trades if t.get("exit_reason") == "trend_flip"),
        "resistance_bounce_exits":  sum(1 for t in trades if t.get("exit_reason") == "resistance_bounce"),
        "support_bounce_exits":     sum(1 for t in trades if t.get("exit_reason") == "support_bounce"),
        "end_of_data_exits":        sum(1 for t in trades if t.get("exit_reason") == "end_of_data"),
        "win_rate_pct":             round(wr * 100, 1),
        "final_capital":            round(capital, 2),
        "total_return_pct":         round(total_ret, 2),
        "avg_gain_pct":             round(avg_gain, 2),
        "avg_loss_pct":             round(avg_loss, 2),
        "max_drawdown_pct":         round(max_dd * 100, 2),
        "profit_factor":            pf,
        "sharpe_ratio":             sharpe,
        "expectancy_pct":           round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }
```

- [ ] **Step 3: Add run_backtest wrapper and CLI**

```python
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
    )
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "enhanced_lines",
        "strategy_label": f"Enhanced Lines (touches={min_touches}, tol={tolerance*100:.1f}%, shorts={'ON' if enable_short else 'OFF'})",
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
    parser = argparse.ArgumentParser(description="Enhanced Straight Lines Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size (default: 1h)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK, help="Bars left/right for swing detection")
    parser.add_argument("--min-touches", type=int, default=MIN_TOUCHES, choices=[2, 3], help="Trendline touch points (2 or 3)")
    parser.add_argument("--tolerance", type=float, default=TOLERANCE, help="Zone width for bounce detection (default: 0.015)")
    parser.add_argument("--confirm-bars", type=int, default=CONFIRM_BARS, help="Consecutive candles to confirm bounce")
    parser.add_argument("--vol-ma-period", type=int, default=VOL_MA_PERIOD, help="Volume MA period")
    parser.add_argument("--vol-base-pct", type=float, default=VOL_BASE_PCT, help="Base pct multiplier for volume ratio")
    parser.add_argument("--vol-floor-pct", type=float, default=VOL_FLOOR_PCT, help="Minimum trade size fraction")
    parser.add_argument("--vol-ceiling-pct", type=float, default=VOL_CEILING_PCT, help="Maximum trade size fraction")
    parser.add_argument("--no-short", action="store_true", help="Disable short selling")
    args = parser.parse_args()

    enable_short = not args.no_short

    print(f"\n{'='*65}")
    print(f"  Enhanced Straight Lines Strategy — {args.symbol}")
    print(f"  Touches: {args.min_touches}  |  Tolerance: {args.tolerance*100:.1f}%  |  Confirm: {args.confirm_bars} bars")
    print(f"  Vol sizing: {args.vol_floor_pct*100:.0f}%-{args.vol_ceiling_pct*100:.0f}%  |  Shorts: {'ON' if enable_short else 'OFF'}")
    print(f"  Interval: {args.interval}  |  Period: {args.period}")
    print(f"{'='*65}\n")

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
    print(f"  Exits:            Trend Flip: {result['trend_flip_exits']}  |  Res Bounce: {result['resistance_bounce_exits']}  |  Sup Bounce: {result['support_bounce_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        shares = t.get("shares", 0)
        pct = t.get("trade_pct", 0)
        print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]  "
              f"({shares:.2f} shares, {pct*100:.0f}% sizing)")

    print(f"\n{'='*65}\n")

    fname = f"enhanced_lines_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Remove any leftover inline tests from earlier tasks**

Make sure the `if __name__ == "__main__":` block only calls `main()`.

- [ ] **Step 5: Run the strategy on SPY to verify end-to-end**

Run: `python strategies/enhanced_lines_strategy.py --symbol SPY --period 1y --interval 1d`
Expected: Strategy runs, prints metrics and trade log, saves JSON file. May have 0 trades initially — that's OK, we'll tune in Task 7.

- [ ] **Step 6: Commit**

```bash
git add strategies/enhanced_lines_strategy.py
git commit -m "feat(enhanced-lines): add metrics, reporting, and CLI entry point"
```

---

### Task 6: Backtest Engine Integration and MCP Registration

**Files:**
- Modify: `src/tradingview_mcp/core/services/backtest_service.py` (lines 38-47, 485-494)
- Modify: `src/tradingview_mcp/server.py` (line ~2994)

- [ ] **Step 1: Add `_run_enhanced_lines()` to `backtest_service.py`**

Add this function before `_STRATEGY_MAP` (around line 483):

```python
def _run_enhanced_lines(candles, pivot_lookback=5, min_touches=3, tolerance=0.015,
                        confirm_bars=2, vol_ma_period=20, vol_base_pct=0.25,
                        vol_floor_pct=0.20, vol_ceiling_pct=0.80, enable_short=True, **_):
    """
    Enhanced Straight Lines — channel-based trend following.

    Tracks support/resistance trendlines using last N touches.
    Determines trend via slope agreement. Trades bounces with
    volume-weighted position sizing. Partial sells in uptrend
    for tax optimization, full exit on regime change.
    """
    if not candles or len(candles) < pivot_lookback * 2 + 10:
        return []

    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]

    # --- Swing detection ---
    n = len(highs)
    swing_highs = []
    swing_lows = []
    for i in range(pivot_lookback, n - pivot_lookback):
        window = range(i - pivot_lookback, i + pivot_lookback + 1)
        if all(highs[i] >= highs[j] for j in window):
            swing_highs.append((i, highs[i], i + pivot_lookback))
        if all(lows[i] <= lows[j] for j in window):
            swing_lows.append((i, lows[i], i + pivot_lookback))

    # --- Volume SMA ---
    vol_sma = [None] * n
    for i in range(vol_ma_period - 1, n):
        vol_sma[i] = sum(volumes[i - vol_ma_period + 1 : i + 1]) / vol_ma_period

    # --- Helpers (inline to keep backtest_service self-contained) ---
    def _tl_value(p1, p2, bar):
        b1, v1 = p1
        b2, v2 = p2
        if b2 == b1:
            return v1
        return v1 + (v2 - v1) / (b2 - b1) * (bar - b1)

    def _tl_slope(p1, p2):
        b1, v1 = p1
        b2, v2 = p2
        return (v2 - v1) / (b2 - b1) if b2 != b1 else 0.0

    def _fit_line(points, direction):
        if len(points) < min_touches:
            return None
        recent = points[-min_touches:]
        if direction == "asc" and not all(recent[k+1][1] > recent[k][1] for k in range(len(recent)-1)):
            return None
        if direction == "desc" and not all(recent[k+1][1] < recent[k][1] for k in range(len(recent)-1)):
            return None
        a1, a2 = recent[0], recent[-1]
        for pt in recent[1:-1]:
            proj = _tl_value(a1, a2, pt[0])
            if proj <= 0 or abs(pt[1] - proj) / proj > tolerance:
                return None
        return {"a1": a1, "a2": a2, "slope": _tl_slope(a1, a2)}

    def _in_zone(candle_idx, tl, direction):
        proj = _tl_value(tl["a1"], tl["a2"], candle_idx)
        if proj <= 0:
            return False
        price = closes[candle_idx]
        if abs(price - proj) / proj <= tolerance:
            return True
        if direction == "up" and abs(lows[candle_idx] - proj) / proj <= tolerance:
            return True
        if direction == "down" and abs(highs[candle_idx] - proj) / proj <= tolerance:
            return True
        return False

    def _bounce(idx, tl, direction):
        if idx < confirm_bars:
            return False
        if not _in_zone(idx, tl, direction):
            return False
        for j in range(idx - confirm_bars + 1, idx + 1):
            c_open, c_close = candles[j]["open"], candles[j]["close"]
            if direction == "up" and c_close <= c_open:
                return False
            if direction == "down" and c_close >= c_open:
                return False
        return True

    def _vol_pct(idx):
        vols = [volumes[j] for j in range(max(0, idx - confirm_bars + 1), idx + 1)]
        if not vols:
            return vol_floor_pct
        avg_v = sum(vols) / len(vols)
        sma_v = vol_sma[idx]
        if sma_v is None or sma_v <= 0:
            return vol_floor_pct
        return max(vol_floor_pct, min(vol_ceiling_pct, (avg_v / sma_v) * vol_base_pct))

    avg_price = sum(closes) / len(closes)
    flat_thresh = avg_price * 0.0002

    def _trend(sup_slope, res_slope):
        if sup_slope is None or res_slope is None:
            return "neutral"
        su = sup_slope > flat_thresh
        sd = sup_slope < -flat_thresh
        ru = res_slope > flat_thresh
        rd = res_slope < -flat_thresh
        if su and ru:
            return "uptrend"
        if sd and rd:
            return "downtrend"
        return "neutral"

    # --- Main loop ---
    confirmed_highs = []
    confirmed_lows = []
    sh_ptr = sl_ptr = 0
    trades = []
    pos_shares = 0.0
    pos_entries = []
    max_sh = 0.0
    prev_trend = "neutral"
    init_cap = 10_000.0

    def _close_all(side, reason, date, price):
        nonlocal pos_shares, pos_entries, max_sh
        for e in pos_entries:
            trades.append({
                "entry_date": e["date"], "entry_price": e["price"],
                "exit_date": date, "exit_price": price,
                "side": side, "exit_reason": reason, "strategy": "enhanced_lines",
            })
        pos_shares = 0.0
        pos_entries = []
        max_sh = 0.0

    def _partial_close(side, reason, date, price, pct):
        nonlocal pos_shares, pos_entries
        target = abs(pos_shares) * pct
        remaining = target
        while remaining > 0.0001 and pos_entries:
            e = pos_entries[0]
            take = min(e["shares"], remaining)
            trades.append({
                "entry_date": e["date"], "entry_price": e["price"],
                "exit_date": date, "exit_price": price,
                "side": side, "exit_reason": reason, "strategy": "enhanced_lines",
            })
            remaining -= take
            e["shares"] -= take
            if e["shares"] < 0.0001:
                pos_entries.pop(0)
        if side == "long":
            pos_shares -= target
        else:
            pos_shares += target

    for i in range(n):
        date = candles[i]["date"]
        price = closes[i]

        while sh_ptr < len(swing_highs) and swing_highs[sh_ptr][2] <= i:
            confirmed_highs.append(swing_highs[sh_ptr][:2])
            sh_ptr += 1
        while sl_ptr < len(swing_lows) and swing_lows[sl_ptr][2] <= i:
            confirmed_lows.append(swing_lows[sl_ptr][:2])
            sl_ptr += 1

        hh = _fit_line(confirmed_highs, "asc")
        hl = _fit_line(confirmed_lows, "asc")
        lh = _fit_line(confirmed_highs, "desc")
        ll = _fit_line(confirmed_lows, "desc")

        sup = hl or ll
        res = hh or lh
        s_slope = sup["slope"] if sup else None
        r_slope = res["slope"] if res else None
        trend = _trend(s_slope, r_slope)

        if trend != prev_trend and prev_trend != "neutral":
            if pos_shares > 0:
                _close_all("long", "trend_flip", date, price)
            elif pos_shares < 0:
                _close_all("short", "trend_flip", date, price)
        prev_trend = trend

        if trend == "uptrend":
            if sup and _bounce(i, sup, "up"):
                pct = _vol_pct(i)
                if pos_shares == 0:
                    sh = (init_cap * pct) / price
                    max_sh = init_cap / price
                elif pos_shares > 0 and max_sh > 0:
                    sh = max(0, (max_sh - pos_shares) * pct)
                else:
                    sh = 0
                if sh > 0.0001:
                    pos_shares += sh
                    pos_entries.append({"date": date, "price": price, "shares": sh})
            elif res and _bounce(i, res, "down") and pos_shares > 0:
                _partial_close("long", "resistance_bounce", date, price, _vol_pct(i))

        elif trend == "downtrend" and enable_short:
            if res and _bounce(i, res, "down"):
                pct = _vol_pct(i)
                if pos_shares == 0:
                    sh = (init_cap * pct) / price
                    max_sh = init_cap / price
                elif pos_shares < 0 and max_sh > 0:
                    sh = max(0, (max_sh - abs(pos_shares)) * pct)
                else:
                    sh = 0
                if sh > 0.0001:
                    pos_shares -= sh
                    pos_entries.append({"date": date, "price": price, "shares": sh})
            elif sup and _bounce(i, sup, "up") and pos_shares < 0:
                _partial_close("short", "support_bounce", date, price, _vol_pct(i))

    if pos_shares > 0:
        _close_all("long", "end_of_data", candles[-1]["date"], candles[-1]["close"])
    elif pos_shares < 0:
        _close_all("short", "end_of_data", candles[-1]["date"], candles[-1]["close"])

    return trades
```

- [ ] **Step 2: Register in `_STRATEGY_LABELS` (line 47)**

Add after the `"higher_highs"` entry:

```python
    "enhanced_lines": "Enhanced Straight Lines (Channel + Volume Sizing)",
```

- [ ] **Step 3: Register in `_STRATEGY_MAP` (line 494)**

Add after the `"higher_highs"` entry:

```python
    "enhanced_lines": _run_enhanced_lines,
```

- [ ] **Step 4: Update MCP tool docstring in `server.py`**

Find the `backtest_strategy` tool docstring (around line 2994) and add to the strategy list:

```
                                'enhanced_lines' — Channel trend following with volume-weighted bounce trading
```

Also add `'higher_highs'` if it's missing from the docstring.

- [ ] **Step 5: Verify the backtest engine integration**

Run: `uv run tradingview-mcp stdio` and test with a backtest call, or simply verify imports:

```bash
cd /Users/spaul11/Projects/tradingview-mcp
python -c "from tradingview_mcp.core.services.backtest_service import _STRATEGY_MAP; print('enhanced_lines' in _STRATEGY_MAP)"
```

Expected: `True`

- [ ] **Step 6: Commit**

```bash
git add src/tradingview_mcp/core/services/backtest_service.py src/tradingview_mcp/server.py
git commit -m "feat(enhanced-lines): integrate into backtest engine and MCP tool registry"
```

---

### Task 7: Run Backtest, Tune, and Fix Issues

**Files:**
- Modify: `strategies/enhanced_lines_strategy.py` (if tuning needed)

- [ ] **Step 1: Run on SPY 2y with 1h candles**

```bash
python strategies/enhanced_lines_strategy.py --symbol SPY --period 2y --interval 1h
```

Review output: does it produce trades? Are the exit reasons sensible? If 0 trades, the tolerance or lookback may need adjustment.

- [ ] **Step 2: Run on SPY with daily candles**

```bash
python strategies/enhanced_lines_strategy.py --symbol SPY --period 2y --interval 1d
```

- [ ] **Step 3: Run on BTC-USD**

```bash
python strategies/enhanced_lines_strategy.py --symbol BTC-USD --period 2y --interval 1h
```

- [ ] **Step 4: Run with min_touches=2 to compare**

```bash
python strategies/enhanced_lines_strategy.py --symbol SPY --period 2y --interval 1h --min-touches 2
```

- [ ] **Step 5: Fix any issues found and commit**

```bash
git add strategies/enhanced_lines_strategy.py
git commit -m "fix(enhanced-lines): tuning and bug fixes from initial backtests"
```

---

### Task 8: Comparison Script and Documentation

**Files:**
- Create: `strategies/compare_enhanced_lines.py`
- Modify: `strategies/STRATEGIES.md`

- [ ] **Step 1: Create comparison script**

```python
"""
Compare Enhanced Lines vs Straight Line vs Buy & Hold across symbols.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

# Import from sibling strategies
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from enhanced_lines_strategy import (
    fetch_ohlcv, run_enhanced_lines, apply_costs, calc_metrics,
)
from straight_line_strategy import (
    run_straight_line,
    apply_costs as sl_apply_costs,
    calc_metrics as sl_calc_metrics,
)


SYMBOLS = ["SPY", "QQQ", "BTC-USD", "AAPL", "NVDA", "GDX", "DIA"]
PERIOD = "2y"
INTERVAL = "1h"
CAPITAL = 10_000.0
COMMISSION = 0.1
SLIPPAGE = 0.05


def main():
    print(f"\n{'='*90}")
    print(f"  Enhanced Lines vs Straight Line vs Buy & Hold")
    print(f"  Period: {PERIOD}  |  Interval: {INTERVAL}  |  Capital: ${CAPITAL:,.0f}")
    print(f"{'='*90}\n")

    header = f"{'Symbol':<12} {'Enhanced':<14} {'Straight':<14} {'B&H':<14} {'Enh vs B&H':<14} {'Enh Trades':<12} {'SL Trades':<12}"
    print(header)
    print("-" * len(header))

    for sym in SYMBOLS:
        try:
            candles = fetch_ohlcv(sym, PERIOD, INTERVAL)
            bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

            # Enhanced Lines
            el_trades = run_enhanced_lines(candles)
            el_trades = apply_costs(el_trades, COMMISSION, SLIPPAGE)
            el_metrics = calc_metrics(el_trades, CAPITAL, INTERVAL)

            # Straight Line
            sl_trades = run_straight_line(candles)
            sl_trades = sl_apply_costs(sl_trades, COMMISSION, SLIPPAGE)
            sl_metrics = sl_calc_metrics(sl_trades, CAPITAL, INTERVAL)

            el_ret = el_metrics["total_return_pct"]
            sl_ret = sl_metrics["total_return_pct"]
            vs_bnh = round(el_ret - bnh, 2)

            print(f"{sym:<12} {el_ret:>+10.2f}%   {sl_ret:>+10.2f}%   {bnh:>+10.2f}%   {vs_bnh:>+10.2f}%   {el_metrics['total_trades']:>8}     {sl_metrics['total_trades']:>8}")
        except Exception as e:
            print(f"{sym:<12} ERROR: {e}")

    print(f"\n{'='*90}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the comparison**

```bash
python strategies/compare_enhanced_lines.py
```

- [ ] **Step 3: Add Enhanced Lines section to `strategies/STRATEGIES.md`**

Add documentation following the same format as existing strategies (overview, parameters table, trading rules, comparison results).

- [ ] **Step 4: Commit**

```bash
git add strategies/compare_enhanced_lines.py strategies/STRATEGIES.md
git commit -m "feat(enhanced-lines): add comparison script and strategy documentation"
```

---

### Task 9: Update Project Documentation

**Files:**
- Modify: `claude.md`
- Modify: `strategies/strategy_map.md`

- [ ] **Step 1: Add Enhanced Lines to claude.md**

Add to the Key Directories section, the Available Backtest Strategies table, and the How To Run section.

- [ ] **Step 2: Add to `strategies/strategy_map.md`**

Add the enhanced_lines entry.

- [ ] **Step 3: Commit**

```bash
git add claude.md strategies/strategy_map.md
git commit -m "docs: add Enhanced Straight Lines to project documentation"
```
