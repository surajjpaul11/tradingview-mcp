# Strategy Map — Which Strategy for Which Market?

A practical guide for selecting the right backtest strategy based on current market conditions. Use this as a decision map before running backtests or deploying strategies.

---

## How to Identify Market Conditions

Before picking a strategy, classify the market. These four regimes cover ~95% of conditions.

### 1. Bullish Trending

**What it looks like:** Price makes higher highs and higher lows. Moving averages are stacked (20 > 50 > 200). Pullbacks are shallow and get bought.

**How to detect programmatically:**
- Price > SMA(200) AND SMA(50) > SMA(200)
- Kaufman Efficiency Ratio > 0.3 (directional, not noisy)
- ADX > 25 (strong trend)
- Higher Highs structure: 3+ consecutive HH/HL on daily or 4H chart

**Real examples:** SPY 2023-2024 rally, NVDA 2024, PLTR 2024-2025

---

### 2. Bearish Trending

**What it looks like:** Price makes lower highs and lower lows. Moving averages are inverted (20 < 50 < 200). Rallies get sold.

**How to detect programmatically:**
- Price < SMA(200) AND SMA(50) < SMA(200)
- Kaufman ER > 0.3 (directional, but down)
- ADX > 25
- Lower Lows structure: 3+ consecutive LL/LH

**Real examples:** BTC Jan-Mar 2025 decline, SPY tariff selloff Mar 2025, MSFT mid-2025 correction

---

### 3. Sideways / Range-Bound

**What it looks like:** Price oscillates between clear support and resistance levels. Moving averages flatten and overlap. RSI bounces between 40-60.

**How to detect programmatically:**
- Price crossing SMA(200) repeatedly (no sustained direction)
- Kaufman ER < 0.2 (price movement is inefficient / noisy)
- ADX < 20 (weak trend)
- Bollinger Bands narrowing (low volatility squeeze)
- No HH/HL or LL/LH structure — mixed swings

**Real examples:** BTC summer 2024 ($58K-$70K range), SPY consolidation periods

---

### 4. Choppy / Volatile

**What it looks like:** Large swings in both directions with no follow-through. Stop losses get hit frequently. High volume on reversals. News-driven whipsaws.

**How to detect programmatically:**
- ATR > 2x its 50-period moving average (abnormal volatility)
- Kaufman ER < 0.15 (lots of movement, no net direction)
- VIX > 25 (for US equities)
- Rapid direction changes — structure breaks within days of forming
- High volume on both up and down bars

**Real examples:** BTC early 2025, meme stocks (GME, AMC), any asset during earnings season

---

## Strategy Selection Matrix

| Condition | Best Strategies | Acceptable | Avoid |
|-----------|----------------|------------|-------|
| **Bullish trending** | Buy & Protect, Higher Highs, EMA Cross, Supertrend | Straight Line (long), VWMA 17, Donchian | RSI, Bollinger (exit too early) |
| **Bearish trending** | Higher Highs (short), VWMA 17 (short), Straight Line (short enabled) | Supertrend, EMA Cross (will short/exit) | Buy & Protect (forced exit, re-entry lag), RSI (catches falling knives) |
| **Sideways / range** | RSI, Bollinger | MACD (slow but catches edges) | EMA Cross (whipsaws), Supertrend (whipsaws), Donchian (false breakouts) |
| **Choppy / volatile** | Buy & Protect (stays invested unless 2+ signals), Bollinger (wide bands adapt) | RSI (if range holds) | Higher Highs (structure breaks constantly), Straight Line (false breaks), EMA Cross, Donchian |

---

## Strategy Profiles

### Trend-Following Strategies

These make money when the market picks a direction and sticks with it. They bleed in sideways markets.

#### EMA Cross
- **Best in:** Sustained multi-month trends
- **Mechanism:** EMA(20) crossing EMA(50) — classic golden/death cross
- **Strength:** Simple, reliable, low trade count — lets winners run
- **Weakness:** Late entries (waits for crossover), death by whipsaw in ranging markets
- **When to use:** You see a clear trend forming and want a set-and-forget signal
- **Trade frequency:** Low (2-6 trades/year on daily)

#### Supertrend
- **Best in:** Trending markets with measurable volatility
- **Mechanism:** ATR-based trend flip — faster than EMA cross at catching reversals
- **Strength:** Adapts stop distance to volatility (wider stops in volatile markets)
- **Weakness:** Gives back profits in choppy consolidation
- **When to use:** You want trend-following but with volatility-adjusted exits
- **Trade frequency:** Low-medium (4-10 trades/year on daily)

#### VWMA 17
- **Best in:** Markets transitioning between trending and choppy
- **Mechanism:** VWMA(17) crossover with adaptive Kaufman ER filter — automatically switches between SMA(200) in trends and SMA(100) in chop
- **Strength:** Only strategy with built-in regime detection. Volume weighting gives better signals than pure price MAs
- **Weakness:** ATR-based SL/TP (1.5x/2.0x) can be tight on explosive movers. Supports both long and short
- **When to use:** You're unsure if the market is trending or choppy and want the strategy to decide
- **Trade frequency:** Medium-high (10-30 trades/year on daily)

#### Straight Line
- **Best in:** Markets with clean swing structures and clear trendlines
- **Mechanism:** Draws trendlines through 4+ confirmed swing points, trades the break
- **Strength:** Intuitive — mirrors how manual traders draw trendlines. Catches reversals when support/resistance finally gives way
- **Weakness:** Needs well-formed swing points. 4-point confirmation delays entries. False breaks in noisy markets
- **When to use:** Asset has clear ascending lows or descending highs visible on the chart
- **Trade frequency:** Medium (7-16 trades/year on hourly)
- **Comparison data (23 symbols, 2y):** +67.38% avg. Beats B&H on reversal-heavy assets (META +20%, MELI +29%, NVTS +78%)

---

### Mean-Reversion Strategies

These profit from prices returning to the mean. They get destroyed in strong trends.

#### RSI
- **Best in:** Range-bound markets with defined overbought/oversold zones
- **Mechanism:** Buy RSI < 40, sell RSI > 60
- **Strength:** Clear, objective signals. Works well on assets that oscillate (utilities, bonds, stable ETFs)
- **Weakness:** In a trend, RSI can stay overbought for weeks — selling at RSI 60 in a bull run exits way too early
- **When to use:** Asset is bouncing between support/resistance, RSI is actually oscillating (not trending above 50)
- **Trade frequency:** Medium (5-15 trades/year on daily)

#### Bollinger Bands
- **Best in:** Mean-reverting markets with normal volatility distribution
- **Mechanism:** Buy at lower band, sell at middle band (SMA)
- **Strength:** Bands adapt to volatility — wider in volatile markets, narrower in calm. Catches extreme deviations
- **Weakness:** In strong trends, price rides the upper band — you never get a buy signal. Exits at middle band leave money on the table
- **When to use:** Bollinger Band Width is stable (not contracting into a squeeze), price is oscillating between bands
- **Trade frequency:** Medium (5-15 trades/year on daily)

---

### Momentum & Breakout Strategies

These catch the beginning of new moves. They pay the price of false signals for the chance to ride big swings.

#### MACD
- **Best in:** Momentum shifts, especially after consolidation
- **Mechanism:** MACD golden cross (MACD > signal line) / death cross
- **Strength:** Histogram shows momentum acceleration — not just direction but conviction
- **Weakness:** Lagging indicator by design (uses EMA 12/26). In choppy markets, crossovers happen constantly and signal nothing
- **When to use:** You see a potential momentum shift (histogram flipping) after a period of low momentum
- **Trade frequency:** Medium (6-12 trades/year on daily)

#### Donchian Channel
- **Best in:** Breakout after tight consolidation (volatility expansion)
- **Mechanism:** Buy on new 20-bar high, sell on new 20-bar low (Turtle Trader style)
- **Strength:** Catches every genuine breakout — you will be in every major move
- **Weakness:** Most breakouts fail. High false-signal rate means you need a few big winners to cover many small losses
- **When to use:** Bollinger Bands are squeezing (low BB Width), consolidation is tightening — a breakout is likely
- **Trade frequency:** Medium-high (8-20 trades/year on daily)

---

### Structure & Protective Strategies

These are more sophisticated — they use market structure, multiple timeframes, or signal confluence rather than a single indicator.

#### Higher Highs
- **Best in:** Markets with clear multi-timeframe trends (HTF structure visible)
- **Mechanism:** Detects 3+ consecutive HH/HL (bullish) or LL/LH (bearish) on 4H, enters on 1H pullback confirmations. Exits via structure flip or exhaustion (RSI divergence + volume dry-up + ATR spike, 2/3 needed)
- **Strength:** Multi-timeframe alignment filters noise. Exhaustion detector catches blow-off tops before the crash. 3% tolerance avoids premature structure breaks
- **Weakness:** Requires significant data history (6+ months). Structure detection lags — by the time 3 HH/HL confirm, you've missed the early move. Choppy markets destroy structure constantly
- **When to use:** Clear swing highs and lows are visible on the 4H chart. Asset is trending with defined pullbacks
- **Trade frequency:** Low-medium (4-10 trades/year)
- **Comparison data (2y, long-only):** SPY +7.56%, DIA +6.18%, QQQ +10.65% with struct+exhaust exits

#### Buy and Protect
- **Best in:** Long-term bullish markets with occasional sharp crashes
- **Mechanism:** Always long (enters immediately). Only exits when 2+ of 3 danger signals fire: rapid 8% decline from rolling peak, price below SMA(200), ATR > 3x average
- **Strength:** Captures ~86% of B&H returns while protecting against crashes. 2-signal confluence virtually eliminates whipsaw exits. Only 1-8 trades per symbol over 2 years
- **Weakness:** Cannot profit from or protect against slow, grinding declines (death by a thousand cuts). Re-entry via SMA reclaim can be slow — misses sharp V-recoveries. Cannot short
- **When to use:** You believe the asset is generally going up long-term but want protection against sudden crashes (crypto, growth stocks)
- **Trade frequency:** Very low (1-8 trades over 2 years)
- **Comparison data (23 symbols, 2y):** +151.92% avg vs B&H +176.23%. Beats B&H on crash-heavy assets (BTC +8.53% vs -4.67%, MSFT +1.36% vs -15.20%)

---

## Decision Flowchart

```
START: What is the market doing?
│
├─ Trending? (ER > 0.3, ADX > 25, clear HH/HL or LL/LH)
│   │
│   ├─ Bullish trend?
│   │   ├─ Want maximum exposure (ride the trend): Buy & Protect
│   │   ├─ Want active management with entries/exits: Higher Highs, EMA Cross
│   │   ├─ Want volatility-adjusted stops: Supertrend
│   │   └─ Want trendline-based timing: Straight Line (long only)
│   │
│   └─ Bearish trend?
│       ├─ Can short: Higher Highs (short), VWMA 17 (short)
│       ├─ Can short + clear trendline: Straight Line (--enable-short)
│       └─ Long only: Stay in cash (or Buy & Protect will auto-exit)
│
├─ Ranging? (ER < 0.2, ADX < 20, price oscillating)
│   │
│   ├─ Clean range with defined S/R: RSI, Bollinger
│   ├─ Narrowing range (squeeze forming): Donchian (breakout coming)
│   └─ Wide range with momentum shifts: MACD
│
├─ Choppy / volatile? (ATR spike, VIX > 25, no follow-through)
│   │
│   ├─ Want to trade the extremes (mean reversion): Volatility Harvester (ER gate + ATR Z-Score)
│   ├─ Want to stay invested with protection: Buy & Protect
│   ├─ Want to trade the extremes: Bollinger (bands widen with vol)
│   └─ Want to sit out: Stay in cash — most strategies bleed here
│
└─ Transitioning / uncertain?
    │
    ├─ Let the strategy decide: VWMA 17 (ER auto-selects regime)
    ├─ Wait for structure to form: Higher Highs (needs 3+ swings)
    └─ Compare all: Run `compare_strategies` to let data decide
```

---

## Regime-Adaptive Strategy Stacking

For users who want to combine strategies rather than picking one:

### Conservative Portfolio Approach
1. **Base position:** Buy & Protect (always long, crash-protected)
2. **Overlay signal:** Use Higher Highs structure detection to size up during confirmed trends
3. **Exit enhancement:** When Buy & Protect and Higher Highs both signal danger, conviction is highest

### Active Trading Approach
1. **Regime detection:** VWMA 17's Efficiency Ratio classifies the market
2. **Trending regime (ER > 0.3):** Run EMA Cross or Supertrend
3. **Choppy regime (ER < 0.3):** Run RSI or Bollinger
4. **Transition:** Use Straight Line for timing the regime shift (trendline break = new regime)

### Breakout Hunter Approach
1. **Wait:** Bollinger Band Width narrowing (squeeze)
2. **Enter:** Donchian breakout confirms direction
3. **Manage:** Supertrend for trailing stops
4. **Exit:** Higher Highs exhaustion detector for blow-off top detection

---

## Quick Reference: Strategy vs Market Condition Scores

Scores from 1 (poor) to 5 (excellent) based on backtesting results and strategy design.

| Strategy | Bull Trend | Bear Trend | Sideways | Choppy | Transitions |
|----------|-----------|-----------|----------|--------|-------------|
| RSI | 2 | 2 | 5 | 3 | 2 |
| Bollinger | 2 | 2 | 5 | 4 | 2 |
| MACD | 3 | 3 | 2 | 1 | 4 |
| EMA Cross | 5 | 3 | 1 | 1 | 3 |
| Supertrend | 5 | 3 | 1 | 2 | 3 |
| Donchian | 4 | 3 | 1 | 2 | 4 |
| VWMA 17 | 4 | 4 | 2 | 2 | 5 |
| Higher Highs | 4 | 4 | 1 | 1 | 3 |
| Buy & Protect | 5 | 2 | 3 | 4 | 3 |
| Straight Line | 4 | 3 | 2 | 1 | 4 |
| Vol. Harvester | 1 | 2 | 3 | 5 | 3 |

**Reading the table:**
- **5 = sweet spot** — strategy was designed for this condition
- **4 = strong** — works well, minor limitations
- **3 = acceptable** — usable but not optimal
- **2 = weak** — expect underperformance, use only if no better option
- **1 = avoid** — strategy will bleed money in this condition

---

## Using This Map with the MCP Server

```bash
# Step 1: Identify the current regime
# Check ER, trend direction, volatility
backtest_strategy(symbol="SPY", strategy="vwma17", period="6mo")
# Look at the ER value in the output to classify regime

# Step 2: Run the recommended strategy
# Bullish trend detected → use buy_and_protect or higher_highs
backtest_strategy(symbol="SPY", strategy="buy_and_protect", period="2y")

# Step 3: Compare all strategies to validate
compare_strategies(symbol="SPY", period="2y")
# The top performer confirms (or overrides) your regime classification

# Step 4: For standalone strategies
python strategies/straight_line_strategy.py --symbol SPY --period 2y
python strategies/higher_highs_strategy.py --symbol SPY --period 2y --long-only
python strategies/buy_and_protect_strategy.py --symbol SPY --period 2y
```
