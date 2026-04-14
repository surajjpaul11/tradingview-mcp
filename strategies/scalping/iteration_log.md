# Scalping Strategy — Iteration Log

## Iteration 1 (2026-04-12) — Baseline: All 4 signals combined

**Signals:** EMA 9/21 crossover + RSI+BB mean reversion + MACD histogram reversal + Stochastic crossover
**Params:** EMA 9/21/50, ATR SL=1.0x TP=1.5x, ADX>=20 filter, BB(20,2.0), RSI 30/70, Stoch(14,3,3)
**Interval:** 1h | **Period:** 60d

### Combined Results (all 4 signals)

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | PF | Sharpe |
|--------|--------|-----|--------|--------|----------|----|--------|
| SPY | -8.83% | -1.35% | -7.48% | 23 | 39.1% | 0.45 | -3.49 |
| QQQ | -18.72% | -1.31% | -17.41% | 22 | 18.2% | 0.23 | -6.47 |
| BTC-USD | -27.84% | +5.06% | -32.91% | 90 | 46.7% | 0.58 | -2.51 |

### Individual Signal Breakdown — SPY

| Signal | Return | vs B&H | Trades | Win Rate | PF |
|--------|--------|--------|--------|----------|----|
| EMA only | -5.02% | -3.67% | 11 | 36.4% | 0.28 |
| RSI+BB only | -1.30% | +0.05% | 6 | 50.0% | 0.65 |
| MACD only | -4.65% | -3.30% | 11 | 36.4% | 0.46 |
| Stoch only | -0.25% | +1.10% | 2 | 50.0% | 0.70 |

### Individual Signal Breakdown — BTC-USD

| Signal | Return | vs B&H | Trades | Win Rate | PF |
|--------|--------|--------|--------|----------|----|
| EMA only | -3.42% | -8.48% | 14 | 42.9% | 0.69 |
| RSI+BB only | -20.31% | -25.37% | 30 | 30.0% | 0.34 |
| MACD only | -18.73% | -23.79% | 59 | 47.5% | 0.56 |
| Stoch only | -6.50% | -11.56% | 13 | 38.5% | 0.44 |

### Analysis

- **All signals lose money** — the 1.0x ATR stop loss is too tight relative to 1.5x ATR take profit on 1h charts
- **RSI+BB is least bad on SPY** (near breakeven, 50% win rate) — mean reversion works better in choppy equity markets
- **MACD generates too many trades on BTC** (59 trades in 60 days) — needs a cooldown or stronger filter
- **EMA crossover is the best single signal on BTC** (-3.42%) — lowest trade count, best selectivity
- **Combining all signals makes things worse** — low-quality signals dilute good ones

### Next iteration ideas

1. ~~**Widen stops:** Try ATR SL=1.5x, TP=2.5x~~ → Done in Iter 2
2. ~~**Add cooldown:** Minimum 5-10 bars~~ → Done in Iter 2
3. ~~**Signal confluence:** Require 2+ signals to agree~~ → Done (0 trades — too strict)
4. ~~**Volume filter:** Only trade when volume > 1.5x average~~ → Done in Iter 2
5. **Time filter for BTC:** Skip low-volume hours (e.g., 00:00-06:00 UTC)
6. ~~**Try RSI+BB only on SPY**~~ → Done in Iter 2

---

## Iteration 2 (2026-04-12) — Wider stops, cooldown, volume filter

**Changes from Iter 1:**
- SL widened: 1.0x → 1.5x ATR
- TP widened: 1.5x → 2.5x ATR
- Added 5-bar cooldown between trades
- Added volume filter (volume > 1.5x 20-bar SMA)
- Added confluence mode (min N signals must agree)
- Refactored signal collection to support confluence

### Combined Results — Iter 2 defaults (all 4 signals, vol filter ON)

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | PF | Sharpe |
|--------|--------|-----|--------|--------|----------|----|--------|
| SPY | -2.79% | -1.35% | -1.44% | 10 | 40.0% | 0.62 | -1.38 |
| QQQ | -3.96% | -1.31% | -2.65% | 9 | 33.3% | 0.58 | -1.51 |
| BTC-USD | -20.29% | +5.06% | -25.40% | 28 | 35.7% | 0.43 | -2.14 |

**vs Iter 1:** SPY improved -8.83% → -2.79%, QQQ -18.72% → -3.96%, BTC -27.84% → -20.29%. Trade counts slashed: SPY 23→10, QQQ 22→9, BTC 90→28.

### Confluence=2 — Too strict

| Symbol | Trades | Note |
|--------|--------|------|
| SPY | 0 | No bar had 2+ signals fire simultaneously |
| BTC-USD | 0 | Same — signals are too independent |

### Parameter Sweep — SPY

| Config | Return | vs B&H | Trades | Win Rate | PF |
|--------|--------|--------|--------|----------|----|
| Defaults (SL=1.5 TP=2.5) | -2.79% | -1.44% | 10 | 40.0% | 0.62 |
| No vol filter | -2.45% | -1.09% | 14 | 42.9% | 0.79 |
| Tight SL=1.0 TP=2.0 | -5.57% | -4.22% | 11 | 27.3% | 0.35 |
| Wide SL=2.0 TP=3.0 | -5.97% | -4.62% | 8 | 25.0% | 0.39 |
| Long-only | -1.48% | -0.13% | 8 | 37.5% | 0.77 |
| RSI+BB only | +1.28% | +2.63% | 6 | 50.0% | 1.38 |
| RSI+BB only, long-only | +2.50% | +3.85% | 5 | 60.0% | 2.11 |
| **RSI+BB + MACD, no vol filter** | **+6.10%** | **+7.45%** | **11** | **63.6%** | **2.14** |

### Parameter Sweep — BTC-USD

| Config | Return | vs B&H | Trades | Win Rate | PF |
|--------|--------|--------|--------|----------|----|
| Defaults | -20.29% | -25.40% | 28 | 35.7% | 0.43 |
| No vol filter | -19.06% | -24.19% | 50 | 44.0% | 0.66 |
| SL=2.0 TP=3.0 | -14.78% | -19.92% | 23 | 39.1% | 0.56 |
| Cooldown=10 | -21.76% | -26.90% | 27 | 33.3% | 0.38 |
| EMA only | -4.21% | -9.34% | 7 | 42.9% | 0.49 |
| Long-only | -16.68% | -21.82% | 18 | 33.3% | 0.38 |
| EMA+MACD only | -13.03% | -18.16% | 17 | 35.3% | 0.44 |

### Best Config: RSI+BB + MACD (no vol filter) on equities

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | PF | Sharpe |
|--------|--------|-----|--------|--------|----------|----|--------|
| **SPY** | **+6.10%** | -1.35% | **+7.45%** | 11 | 63.6% | 2.14 | 2.34 |
| QQQ | -5.20% | -1.31% | -3.89% | 9 | 33.3% | 0.55 | -1.61 |
| AAPL | -2.89% | +0.28% | -3.17% | 12 | 41.7% | 0.83 | -0.59 |
| MSFT | -6.23% | -20.19% | +13.96% | 13 | 46.2% | 0.77 | -0.69 |
| NVDA | -6.72% | +3.83% | -10.55% | 14 | 42.9% | 0.75 | -0.95 |

### Analysis — Iteration 2

- **Wider stops + cooldown dramatically reduced losses** across all symbols
- **RSI+BB + MACD (no vol filter) is the clear winner on SPY**: +6.10% return, 63.6% win rate, PF=2.14, Sharpe=2.34
- **RSI+BB provides high-quality entries** (mean reversion at BB extremes), **MACD adds directional momentum trades**
- **Volume filter hurts on equities** — filters out the panic/squeeze bars that RSI+BB is designed to catch
- **BTC remains unprofitable** across all configs — 1h scalping on BTC is tough due to 24/7 noise
- **MSFT is interesting**: -6.23% return but +13.96% vs B&H (MSFT dropped -20% in this period)
- **Confluence=2 is too strict** — need signals that overlap more by design

### Next iteration ideas

1. **Make RSI+BB + MACD the default config** for equities
2. **Add trailing stop**: Once TP is 50% reached, move SL to breakeven (lock in profit)
3. **Add a time-of-day filter**: Only trade first 2h and last 1h of session (highest volume/movement)
4. **Tune RSI thresholds**: Try RSI 25/75 (stricter) to reduce bad entries
5. **Test on longer period**: Run 6mo or 1y backtest for more statistical significance (Yahoo 1h data goes back ~730 days)
6. **For BTC**: Try different interval (15m or 30m) or completely different approach
