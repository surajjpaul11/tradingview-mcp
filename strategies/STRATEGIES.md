# Trading Strategies

Detailed documentation for all backtest strategies in this project.

Every custom strategy gets two files with the **same filename**, different extensions:
- `.py` — Standalone Python implementation (runs independently, includes own indicators + data fetching + CLI)
- `.pine` — TradingView Pine Script v6 equivalent (for use in TradingView's native platform)

---

## Built-in Strategies (6 total, MCP server)

These ship with the upstream project and live in `backtest_service.py`. All are **long-only**.

| Strategy | Type | Description |
|----------|------|-------------|
| `rsi` | Mean reversion | Buy RSI < 40, sell RSI > 60 |
| `bollinger` | Mean reversion | Buy at lower band, sell at middle band |
| `macd` | Momentum | Buy MACD golden cross, sell death cross |
| `ema_cross` | Trend following | EMA 20/50 crossover |
| `supertrend` | Trend following | ATR-based Supertrend trend flip |
| `donchian` | Breakout | Donchian channel breakout (Turtle Trader style) |

---

## VWMA 17 Strategy

**Files:** `strategies/vwma17_strategy.py` | `strategies/vwma17_strategy.pine`
**Type:** Trend following | **Sides:** Long + Short | **MCP key:** `vwma17`

### How It Works

Uses a 17-period Volume Weighted Moving Average with an adaptive trend filter based on the Kaufman Efficiency Ratio.

**Entry:**
- Long: close crosses above VWMA(17) AND close is above the active SMA
- Short: close crosses below VWMA(17) AND close is below the active SMA

**Exit:** ATR-based stop loss (1.5x ATR) and take profit (2.0x ATR)

**Adaptive Trend Filter (Efficiency Ratio):**
The Kaufman ER measures how "efficient" price movement is: `|net change| / sum(|bar-to-bar changes|)`. A value near 1.0 means strongly trending; near 0.0 means choppy/sideways.

- ER > 0.3 (trending) -> uses SMA(200) as trend filter (slower, avoids whipsaws)
- ER <= 0.3 (choppy) -> uses SMA(100) as trend filter (faster, catches shorter moves)

### Default Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `vwma_length` | 17 | VWMA period |
| `atr_length` | 14 | ATR period for SL/TP |
| `atr_multiplier` | 1.5 | Stop loss = entry +/- ATR * this |
| `tp_multiplier` | 2.0 | Take profit = entry +/- ATR * this |
| `er_period` | 50 | Efficiency Ratio lookback |
| `er_threshold` | 0.3 | Above = trending regime |
| `sma_trending` | 200 | SMA period in trending regime |
| `sma_choppy` | 100 | SMA period in choppy regime |

### Usage

```bash
# Via MCP
backtest_strategy(symbol="BTC-USD", strategy="vwma17", period="2y")

# Standalone
python strategies/vwma17_strategy.py --symbol BTC-USD --period 2y
python strategies/vwma17_strategy.py --symbol GDX --period 1y --er-period 50 --er-threshold 0.3
```

---

## Higher Highs Strategy

**Files:** `strategies/higher_highs_strategy.py` | `strategies/higher_highs_strategy.pine`
**Type:** Multi-timeframe structure | **Sides:** Long + Short (or long-only with `--long-only`) | **MCP key:** `higher_highs`

### How It Works

A multi-timeframe market structure strategy that detects trends via swing point analysis on a higher timeframe and times entries on lower timeframe pullbacks.

**Structure Detection (HTF):**
- Bullish = 3+ consecutive higher highs AND higher lows
- Bearish = 3+ consecutive lower highs AND lower lows
- A 3% tolerance is applied so minor noise dips don't break structure (e.g., a swing low that dips 2% below the prior still counts as a "higher low")

**Entry (LTF pullback confirmation):**
- Long: HTF is bullish + a new LTF higher low is confirmed
- Short: HTF is bearish + a new LTF lower high is confirmed

**Exit Mechanisms (3 layers, structure + exhaustion by default):**

1. **HTF Structure Flip** — Exit long when HTF flips to bearish (3+ LL/LH confirmed), exit short when bullish. This is a full structure flip, not a single break.

2. **Trend Exhaustion Detector** — A composite signal requiring 2 out of 3:
   - *RSI Divergence:* Price makes new high but RSI makes a lower high (bearish divergence for longs; inverted for shorts)
   - *Volume Dry-up:* Volume MA drops below 80% of the peak volume MA during the move
   - *ATR Spike:* Current ATR exceeds 2x the average ATR (blow-off top / capitulation)

3. **ATR Trailing Stop** (optional, disabled by default) — When enabled, an ATR-based trailing stop that only activates after a configurable profit threshold. Enable with `--trail-enabled`, optionally with `--min-profit-to-trail 5.0` to only trail after 5% profit.

**Re-entry:** After any exit, the strategy can re-enter if HTF structure re-establishes.

### Exit Variant Comparison (SPY/DIA/QQQ, 2y, long-only)

| Variant | SPY | DIA | QQQ | Avg |
|---------|-----|-----|-----|-----|
| 5x ATR trailing stop | -0.79% | +1.98% | +8.13% | +3.11% |
| Trail after 2% profit | +1.83% | +4.95% | +7.20% | +4.66% |
| **No trail (struct+exhaust) [DEFAULT]** | **+7.56%** | **+6.18%** | **+10.65%** | **+8.13%** |
| No trail, activate at 5% | +6.30% | +6.18% | +11.71% | +8.06% |

The no-trailing default lets winners ride and avoids death-by-a-thousand-cuts from premature stop-outs in grinding bull markets.

### Default Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `pivot_lookback` | 5 | Bars left/right for swing point detection |
| `min_swings` | 3 | Consecutive HH/HL or LL/LH to confirm trend |
| `htf_multiplier` | 4 | LTF bars per HTF bar (4 x 1h = 4h) |
| `interval` | 1h | Lower timeframe candle size |
| `struct_tolerance` | 0.03 | 3% tolerance for structure detection |
| `trail_enabled` | false | Trailing stop disabled by default |
| `trail_atr_period` | 14 | ATR period (when trailing enabled) |
| `trail_atr_mult` | 5.0 | Trailing stop distance in ATR multiples |
| `rsi_period` | 14 | RSI period for exhaustion detection |
| `vol_ma_period` | 20 | Volume MA period for exhaustion |
| `atr_spike_mult` | 2.0 | ATR spike threshold (current > 2x avg) |
| `exhaust_min` | 2 | Signals needed (out of 3) for exhaustion exit |

### Usage

```bash
# Standalone (defaults: struct+exhaust exits, no trailing stop)
python strategies/higher_highs_strategy.py --symbol BTC-USD --period 2y
python strategies/higher_highs_strategy.py --symbol SPY --period 2y --long-only

# With trailing stop enabled (activate after 5% profit)
python strategies/higher_highs_strategy.py --symbol AAPL --period 1y --trail-enabled --min-profit-to-trail 5.0

# Custom structure parameters
python strategies/higher_highs_strategy.py --symbol ETH-USD --period 6mo --pivot-lookback 3 --min-swings 2

# Daily timeframe with weekly HTF
python strategies/higher_highs_strategy.py --symbol MSFT --period 2y --interval 1d --htf-mult 5
```

### Pine Script Notes

The Pine Script version (`higher_highs_strategy.pine`) implements the core multi-timeframe structure detection and LTF entry logic using `request.security()` for HTF data. It does **not** yet include the exhaustion detector or trailing stop — those are only in the Python version. The Pine Script is useful for visual confirmation on TradingView charts.

---

## Buy and Protect Strategy

**Files:** `strategies/buy_and_protect_strategy.py` (Pine Script TBD)
**Type:** Buy-and-hold with downside protection | **Sides:** Long only

### How It Works

Designed to closely match buy-and-hold returns while protecting against sudden downturns. Enters long immediately on bar 1 and stays invested unless danger signals fire.

**Key Innovation: Signal Confluence**
Unlike traditional stop-loss strategies that exit on a single signal (causing whipsaws), Buy and Protect requires **2 out of 3 danger signals to fire simultaneously** before exiting. This dramatically reduces false exits and keeps you invested through normal pullbacks.

**Danger Signals (need 2+ to exit):**
1. **Rapid Decline:** Price drops X% from its rolling peak within Y bars (detects sharp crashes, not slow corrections)
2. **MA Breakdown:** Price closes below SMA(200) (long-term trend broken)
3. **Volatility Spike:** ATR exceeds 3.0x its moving average (crash-level volatility)

**Re-entry Modes:**
- `ma_reclaim` (default): Re-enter when price crosses back above the SMA
- `higher_low`: Re-enter when a new confirmed swing low forms above the previous swing low, AND price is above SMA

### Performance Comparison (2y, daily, 23 symbols)

| Metric | Buy & Protect | Buy & Hold |
|--------|--------------|------------|
| Avg Return | +151.92% | +176.23% |
| Gap vs B&H | -24.32% | — |
| Beat B&H | 5/23 symbols | — |
| Trades | 1-8 per symbol | 1 |

**Outperforms B&H on:**
- Assets with crashes: BTC-USD (+8.53% vs -4.67%), MSFT (+1.36% vs -15.20%), VXX (+28.41% vs -24.04%)
- Volatile momentum: PLTR (+583.53% vs +521.73%), SMR (+281.75% vs +93.97%)

**Near-identical to B&H on:** KGC (-0.30% gap), MU (-0.01% gap), AAPL (-6.09% gap)

**Trails B&H on:** Explosive movers where dip-exits cost upside (BE, NVTS, UUUU)

### Default Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `ma_period` | 200 | SMA period for trend / re-entry |
| `rapid_decline_pct` | 8.0 | Exit if price drops this % from rolling peak |
| `rapid_decline_bars` | 10 | Rolling window for peak tracking |
| `atr_period` | 14 | ATR calculation period |
| `atr_spike_mult` | 3.0 | Volatility spike threshold (ATR > 3x avg) |
| `atr_ma_period` | 50 | Period for average ATR baseline |
| `reentry_mode` | ma_reclaim | Re-entry trigger: "ma_reclaim" or "higher_low" |
| `pivot_lookback` | 5 | Swing detection lookback (higher_low mode) |
| `interval` | 1d | Daily candles (position-level strategy) |

### Parameter Variant Comparison (10 symbols, 2y, 2+ signal confluence)

| Variant | Avg Return | B&H Avg | vs B&H | Trades |
|---------|-----------|---------|--------|--------|
| SMA50 / 5% / 2.5x | +111.9% | +159.3% | -47.5% | 3-20 |
| SMA100 / 7% / 2.5x | +116.0% | +159.3% | -43.3% | 2-10 |
| **SMA200 / 8% / 3.0x [DEFAULT]** | **+154.3%** | **+159.3%** | **-5.0%** | **1-6** |
| SMA200 / 10% / 3.0x | +151.6% | +159.3% | -7.7% | 1-5 |

### Usage

```bash
# Default (SPY, 2y, daily, SMA200, 8% decline, 3.0x ATR spike)
python strategies/buy_and_protect_strategy.py

# Different symbol and period
python strategies/buy_and_protect_strategy.py --symbol QQQ --period 5y

# Hourly candles for crypto
python strategies/buy_and_protect_strategy.py --symbol BTC-USD --period 2y --interval 1h

# Tighter protection
python strategies/buy_and_protect_strategy.py --symbol NVDA --ma-period 100 --rapid-decline-pct 5

# Higher-low re-entry mode
python strategies/buy_and_protect_strategy.py --symbol AAPL --reentry-mode higher_low
```

---

## Straight Line Strategy

**Files:** `strategies/straight_line_strategy.py` (Pine Script TBD)
**Type:** Trendline break | **Sides:** Long only (short optional via `--enable-short`) | **MCP key:** `straight_line`

### How It Works

A trendline-based strategy that draws support and resistance lines connecting swing points, then trades the breaks.

**Core Concept:**
- In an **uptrend**, draw a support trendline connecting ascending swing lows. When price closes below this line, the trend is considered broken — sell.
- In a **downtrend**, draw a resistance trendline connecting descending swing highs. When price closes above this line, the trend is considered reversing — buy.

**Trendline Construction (4-point confirmation):**
1. Find two prominent swing lows (for support) or swing highs (for resistance) as anchor points
2. Draw a straight line through these two points and extend it forward
3. Require 2+ additional swing points to land **near** the trendline (within a configurable tolerance, e.g. 1.5%) to confirm validity
4. A trendline is only active/tradeable once it has 4+ touching points (2 anchor + 2 confirmations)

**Trendline Anchoring:**
- Anchored from the first point and extended indefinitely
- The line is NOT redrawn when new points form — it maintains its original slope
- A new trendline is constructed only after the previous one breaks

**Break Confirmation:**
- The candle must **close** below (support) or above (resistance) the trendline
- Requires 1 bar confirmation: the break bar's close triggers the signal on the next bar's open

**Initial Trend Detection:**
- Determined by whether the most recent swing lows are ascending (bullish → start long) or descending (bearish → start in cash or short)

**Proximity Tolerance:**
- A swing point is considered "touching" the trendline if it's within X% of the projected trendline value at that bar
- This handles real-world price action where swings rarely land exactly on a mathematical line

### Default Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `pivot_lookback` | 5 | Bars left/right for swing point detection |
| `min_confirmations` | 2 | Additional points near trendline to confirm (total 4 = 2 anchor + 2 confirm) |
| `trendline_tolerance` | 0.015 | 1.5% tolerance for "touching" the trendline |
| `enable_short` | false | Enable short positions on support break (default: long only) |
| `interval` | 1h | Hourly candles |
| `period` | 2y | Data lookback |

### Usage

```bash
# Default (SPY, 2y, 1h, long-only)
python strategies/straight_line_strategy.py

# Different symbol
python strategies/straight_line_strategy.py --symbol BTC-USD --period 1y

# Enable short selling
python strategies/straight_line_strategy.py --symbol QQQ --enable-short

# Tighter trendline tolerance (stricter point matching)
python strategies/straight_line_strategy.py --symbol AAPL --trendline-tolerance 0.01

# More confirmation points required
python strategies/straight_line_strategy.py --symbol NVDA --min-confirmations 3
```

### Visual Example

```
Uptrend support trendline (sell when price closes below):

    Price
     |        *
     |      *   *
     |    *  HL3  *     * ← price closes below trendline = SELL
     |  *  HL2      *  /
     | * HL1      ----*--- trendline projected
     |*-----------
     +---------------------- Time
      ^anchor    ^confirm

Downtrend resistance trendline (buy when price closes above):

     Price
     |*
     | * LH1
     |   *-----------
     |  LH2 *       ---- trendline projected
     |     *  LH3  *  \
     |       *   *      * ← price closes above trendline = BUY
     |         *
     +---------------------- Time
```

---

## Volatility Harvester Strategy

**Files:** `strategies/volatility_harvester_strategy.py` (Pine Script TBD)
**Type:** Mean reversion (choppy markets) | **Sides:** Long + Short (or long-only with `--long-only`) | **MCP key:** `volatility_harvester`

### How It Works

A counter-trend strategy designed specifically for choppy/volatile markets. Uses a Kaufman Efficiency Ratio gate to detect when the market is directionless, then buys panic dips and shorts sharp rips, betting on mean reversion.

**Regime Gate (Kaufman Efficiency Ratio):**
The ER measures how "efficient" price movement is. ER < 0.25 means lots of movement but no net direction (choppy) — the strategy only opens new positions in this regime. When ER >= 0.25 (trending), the strategy sits in cash.

**Entry (ATR Z-Score + Volume Confirmation):**
- Long: close is >= 3.0 ATR below SMA(20) AND volume >= 1.5x its MA (panic dip)
- Short: close is >= 3.0 ATR above SMA(20) AND volume >= 1.5x its MA (sharp rip)

**Exit (Triple Layer — first to fire wins):**
1. **Mean Reversion:** Price returns to SMA(20) — thesis complete
2. **Time Exit:** Position held for 15 bars — thesis expired
3. **Stop Loss:** Price moves 2.0 ATR against entry (ATR frozen at entry) — thesis wrong

### Default Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `atr_period` | 14 | ATR calculation period |
| `sma_period` | 20 | Mean for deviation + reversion target |
| `deviation_mult` | 3.0 | ATR multiples from SMA to trigger entry |
| `stop_mult` | 2.0 | ATR multiples for stop loss |
| `max_hold_bars` | 15 | Max bars to hold a position |
| `vol_ma_period` | 20 | Volume MA period |
| `vol_spike_mult` | 1.5 | Volume spike multiplier for confirmation |
| `er_period` | 50 | Efficiency Ratio lookback |
| `er_threshold` | 0.25 | Below = choppy (trade), above = trending (cash) |
| `volume_filter` | true | Require volume confirmation |
| `long_only` | false | Disable short positions |

### Usage

```bash
# Default (SPY, 2y, 1h, long+short)
python strategies/volatility_harvester_strategy.py

# Crypto (high choppiness expected)
python strategies/volatility_harvester_strategy.py --symbol BTC-USD --period 2y

# Long-only mode
python strategies/volatility_harvester_strategy.py --symbol QQQ --long-only

# Without volume filter (for thin-volume assets)
python strategies/volatility_harvester_strategy.py --symbol UUUU --no-volume-filter

# Wider entry threshold (fewer but higher-conviction trades)
python strategies/volatility_harvester_strategy.py --symbol VXX --deviation-mult 2.5
```
