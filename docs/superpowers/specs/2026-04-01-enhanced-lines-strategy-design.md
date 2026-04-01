# Enhanced Straight Lines Strategy — Design Spec

## Overview

A channel-based trend-following strategy that tracks both support and resistance trendlines simultaneously, using only the **last N touches** (default 3, configurable to 2) and discarding older points. Trend is determined by **relative agreement of both trendline slopes**. Position sizing on all swing trades is **volume-weighted** based on the 2-bar bounce confirmation candles.

Builds on the existing `straight_line_strategy.py` concepts but is a fundamentally different strategy — channel trading with partial position management vs. simple trendline break detection.

## Trendline Construction

- Detect swing highs and swing lows using pivot logic (configurable lookback, default 5 bars)
- From confirmed swings, always use only the **last `min_touches`** points (default 3) that form a valid line within tolerance
- Discard older points — trendlines are always "fresh" and represent current market structure
- Track 4 potential lines: higher highs, higher lows, lower highs, lower lows
- Active channel = the best-fit support + resistance pair based on current swing structure
- `min_touches` is configurable (2 or 3) — 2 touches is more aggressive (earlier signals, more noise), 3 is the default

## Bounce Detection (Zone + 2-bar Reversal)

1. Price enters a tolerance zone near the trendline (default 1.5% of trendline value)
2. Two consecutive candles close in the bounce direction:
   - Bounce UP: 2 consecutive bullish closes (close > open)
   - Bounce DOWN: 2 consecutive bearish closes (close < open)
3. Signal fires on the close of the 2nd confirmation candle, execution on next bar's open

## Trend Determination (Relative Agreement)

Trend is determined by whether the support and resistance trendline slopes agree:

| Support Slope | Resistance Slope | Trend |
|---------------|------------------|-------|
| Up | Up | **UPTREND** |
| Down | Down | **DOWNTREND** |
| Up | Down | **NEUTRAL** (converging wedge) |
| Down | Up | **NEUTRAL** (diverging wedge) |
| Flat | Flat | **NEUTRAL** (range-bound) |
| Up | Flat | **NEUTRAL** (ascending wedge) |
| Flat | Down | **NEUTRAL** (descending wedge) |

"Flat" is defined as slope angle within a configurable threshold (e.g., ±2° or equivalent price-per-bar threshold). The exact threshold will need tuning — start with a reasonable default and expose as a parameter.

## Trading Rules

### Uptrend (both lines slope up)

| Signal | Action | Sizing |
|--------|--------|--------|
| Bounce UP from higher lows (support) | BUY | Volume-weighted 20-80% |
| Bounce DOWN from higher highs (resistance) | PARTIAL SELL | Volume-weighted 20-80% |
| Bounce UP from support after partial sell | BUY BACK | Volume-weighted 20-80% |

The partial sell during uptrend is **tax-optimized** — we never fully exit a working uptrend, just take profit on channel swings.

### Trend Flip (regime change)

| Signal | Action | Sizing |
|--------|--------|--------|
| Trend changes from UP → DOWN or HORIZONTAL | SELL 100% | Full exit (ignore volume) |
| Trend changes from DOWN → UP or HORIZONTAL | CLOSE ALL SHORTS | Full exit (ignore volume) |

Trend flips are the **only** time we ignore volume-weighted sizing. This is a regime change, not a conviction trade.

### Downtrend (both lines slope down)

After a trend flip to downtrend, we do NOT short immediately. We wait for:
1. A clear downtrend channel to form (both lines confirmed sloping down with `min_touches` points each)
2. A confirmed bounce DOWN from the resistance (lower highs) line

| Signal | Action | Sizing |
|--------|--------|--------|
| Bounce DOWN from lower highs (resistance) | SHORT | Volume-weighted 20-80% |
| Bounce UP from lower lows (support) | CLOSE SHORT | Volume-weighted 20-80% |
| Bounce DOWN from resistance after cover | RE-SHORT | Volume-weighted 20-80% |

### Neutral / No Clear Trend

- If holding longs → SELL 100%
- If holding shorts → CLOSE ALL SHORTS
- Stay flat until a clear trend re-establishes

## Volume-Weighted Position Sizing

Uses the 2 confirmation candles from the bounce detection. Higher volume = more conviction = larger trade size.

```
avg_vol   = mean(vol[confirm_bar_1], vol[confirm_bar_2])
vol_ratio = avg_vol / SMA(volume, vol_ma_period)
trade_pct = clamp(vol_ratio * vol_base_pct, vol_floor_pct, vol_ceiling_pct)
```

| Volume Ratio | Trade % | Interpretation |
|-------------|---------|----------------|
| < 0.8x | 20% (floor) | Low conviction |
| 1.0x | 25% | Average volume |
| 2.0x | 50% | Double average |
| 3.0x | 75% | High conviction |
| > 3.2x | 80% (ceiling) | Max conviction |

**Exception:** Trend flip → always 100% regardless of volume.

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_touches` | 3 | Swing points to fit trendline (2 or 3) |
| `tolerance` | 0.015 | Zone width for bounce detection (1.5%) |
| `pivot_lookback` | 5 | Bars left/right for swing detection |
| `vol_ma_period` | 20 | Volume MA baseline period |
| `vol_base_pct` | 0.25 | Base multiplier for volume ratio |
| `vol_floor_pct` | 0.20 | Minimum trade size (20%) |
| `vol_ceiling_pct` | 0.80 | Maximum trade size (80%) |
| `confirm_bars` | 2 | Consecutive candles to confirm bounce |
| `enable_short` | True | Enable short positions in downtrend |
| `interval` | "1h" | Candle interval |
| `period` | "2y" | Data lookback period |
| `initial_capital` | 10000 | Starting capital |
| `commission_pct` | 0.1 | Commission per trade (%) |
| `slippage_pct` | 0.05 | Slippage per trade (%) |

## File Outputs

Following the project convention:

- `strategies/enhanced_lines_strategy.py` — Standalone Python implementation with CLI
- `strategies/enhanced_lines_strategy.pine` — TradingView Pine Script v6 equivalent
- `strategies/enhanced_lines_strategy.html` — Interactive visual guide (already created)
- `strategies/compare_enhanced_lines.py` — Comparison script vs B&H and straight_line

Backtest engine integration:
- Add `_run_enhanced_lines()` to `backtest_service.py`
- Register in `_STRATEGY_MAP` and `_STRATEGY_LABELS`

## Key Design Differences from straight_line_strategy

| Aspect | Straight Line | Enhanced Lines |
|--------|--------------|----------------|
| Trendlines | Uses all historical points, 4-point confirmation | Last 3 (or 2) touches only, discards older |
| Trading | Break-only (sell when line breaks) | Bounce + break (trade within channel) |
| Position sizing | All-in / all-out | Volume-weighted partial (20-80%) |
| Trend detection | Implicit (ascending/descending swings) | Explicit (slope agreement of both lines) |
| Shorts | Optional, on break only | On confirmed resistance bounce in downtrend |
| Tax optimization | None | Partial sells in uptrend preserve long-term gains |

## Future Enhancements (Not in Baseline)

These are identified improvements to explore after the baseline is working and backtested:

- **Ascending wedge handling:** Support rising + resistance falling (converging up) — could signal a buy opportunity as price compresses before breakout
- **Descending wedge handling:** Support falling + resistance rising (converging down) — could signal increased sell pressure, sell more aggressively
- **Prolonged flat trading:** When both lines are flat for extended periods (range-bound), could implement mean-reversion trades (buy at support, sell at resistance) within the range
- **Wedge breakout detection:** After ascending/descending wedges resolve, detect breakout direction and enter aggressively
- **Adaptive tolerance:** Adjust the 1.5% zone width based on ATR — tighter in low-vol, wider in high-vol
- **Multi-timeframe confirmation:** Use HTF trendlines to filter LTF signals (similar to higher_highs strategy)
