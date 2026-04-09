# Smart Hold Optimizer Log
Started: 2026-04-09T03:06:42.743781+00:00
Tickers: GOOGL, WDC, SPY, QQQ

## Baseline
```
  GOOGL :  +169.58% (vs B&H: +66.95%, trades=11, win=90.9%, dd=-3.15%)
  WDC   :  +734.49% (vs B&H: +217.55%, trades=6, win=50.0%, dd=-22.28%)
  SPY   :   +50.92% (vs B&H: +20.75%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +46.22% (vs B&H: +9.16%, trades=10, win=60.0%, dd=-1.69%)
```
Parameters: `{"fast_ma": 10, "slow_ma": 50, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 25.0, "vix_fear_entry": 30.0, "vix_extreme": 35.0, "vix_entry_decline": 3.0, "reentry_ma_reclaim": 2, "rsi_oversold": 30, "trailing_stop_atr_mult": 6.0, "reentry_cooldown_bars": 2}`

---

## Iteration 4 — IMPROVEMENT #1

**Changes:** vix_extreme: 35.0 -> 36.0; reentry_ma_reclaim: 2 -> 1

**Deltas:** GOOGL: +0.30%, WDC: +0.00%, SPY: +2.25%, QQQ: +2.84%

```
  GOOGL :  +169.88% (vs B&H: +67.25%, trades=11, win=90.9%, dd=-3.04%)
  WDC   :  +734.49% (vs B&H: +217.55%, trades=6, win=50.0%, dd=-22.28%)
  SPY   :   +53.17% (vs B&H: +23.00%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +49.06% (vs B&H: +12.01%, trades=10, win=60.0%, dd=-1.69%)
```

**Parameters:** `{"fast_ma": 10, "slow_ma": 50, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 25.0, "vix_fear_entry": 30.0, "vix_extreme": 36.0, "vix_entry_decline": 3.0, "reentry_ma_reclaim": 1, "rsi_oversold": 30, "trailing_stop_atr_mult": 6.0, "reentry_cooldown_bars": 2}`

---

## Iteration 9 — IMPROVEMENT #2

**Changes:** vix_exit_boost: 25.0 -> 28.0; vix_fear_entry: 30.0 -> 27.0; vix_entry_decline: 3.0 -> 4.5

**Deltas:** GOOGL: +10.51%, WDC: +0.00%, SPY: +1.11%, QQQ: +1.67%

```
  GOOGL :  +180.39% (vs B&H: +77.76%, trades=11, win=90.9%, dd=-3.04%)
  WDC   :  +734.49% (vs B&H: +217.55%, trades=6, win=50.0%, dd=-22.28%)
  SPY   :   +54.28% (vs B&H: +24.11%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +50.73% (vs B&H: +13.67%, trades=10, win=60.0%, dd=-1.69%)
```

**Parameters:** `{"fast_ma": 10, "slow_ma": 50, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 28.0, "vix_fear_entry": 27.0, "vix_extreme": 36.0, "vix_entry_decline": 4.5, "reentry_ma_reclaim": 1, "rsi_oversold": 30, "trailing_stop_atr_mult": 6.0, "reentry_cooldown_bars": 2}`

---

*Iterations 1-10: 2 improvements so far*

## Iteration 12 — IMPROVEMENT #3

**Changes:** trailing_stop_atr_mult: 6.0 -> 5.5; reentry_cooldown_bars: 2 -> 1; reentry_ma_reclaim: 1 -> 4

**Deltas:** GOOGL: +4.31%, WDC: +7.03%, SPY: -0.09%, QQQ: +0.00%

```
  GOOGL :  +184.70% (vs B&H: +82.07%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +741.52% (vs B&H: +224.58%, trades=6, win=50.0%, dd=-20.43%)
  SPY   :   +54.19% (vs B&H: +24.01%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +50.73% (vs B&H: +13.67%, trades=10, win=60.0%, dd=-1.69%)
```

**Parameters:** `{"fast_ma": 10, "slow_ma": 50, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 28.0, "vix_fear_entry": 27.0, "vix_extreme": 36.0, "vix_entry_decline": 4.5, "reentry_ma_reclaim": 4, "rsi_oversold": 30, "trailing_stop_atr_mult": 5.5, "reentry_cooldown_bars": 1}`

---

## Iteration 14 — IMPROVEMENT #4

**Changes:** reentry_ma_reclaim: 4 -> 5

**Deltas:** GOOGL: +4.45%, WDC: +0.00%, SPY: -0.65%, QQQ: +0.06%

```
  GOOGL :  +189.15% (vs B&H: +86.52%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +741.52% (vs B&H: +224.58%, trades=6, win=50.0%, dd=-20.43%)
  SPY   :   +53.54% (vs B&H: +23.37%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +50.79% (vs B&H: +13.74%, trades=10, win=60.0%, dd=-1.69%)
```

**Parameters:** `{"fast_ma": 10, "slow_ma": 50, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 28.0, "vix_fear_entry": 27.0, "vix_extreme": 36.0, "vix_entry_decline": 4.5, "reentry_ma_reclaim": 5, "rsi_oversold": 30, "trailing_stop_atr_mult": 5.5, "reentry_cooldown_bars": 1}`

---

## Iteration 16 — IMPROVEMENT #5

**Changes:** reentry_cooldown_bars: 1 -> 2

**Deltas:** GOOGL: +0.00%, WDC: +7.16%, SPY: +0.00%, QQQ: +0.00%

```
  GOOGL :  +189.15% (vs B&H: +86.52%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +748.68% (vs B&H: +231.74%, trades=6, win=50.0%, dd=-20.97%)
  SPY   :   +53.54% (vs B&H: +23.37%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +50.79% (vs B&H: +13.74%, trades=10, win=60.0%, dd=-1.69%)
```

**Parameters:** `{"fast_ma": 10, "slow_ma": 50, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 28.0, "vix_fear_entry": 27.0, "vix_extreme": 36.0, "vix_entry_decline": 4.5, "reentry_ma_reclaim": 5, "rsi_oversold": 30, "trailing_stop_atr_mult": 5.5, "reentry_cooldown_bars": 2}`

---

*Iterations 11-20: 5 improvements so far*

*Iterations 21-30: 5 improvements so far*

*Iterations 31-40: 5 improvements so far*

## Iteration 42 — IMPROVEMENT #6

**Changes:** vix_fear_entry: 27.0 -> 26.0; slow_ma: 50 -> 65; fast_ma: 10 -> 9

**Deltas:** GOOGL: +0.00%, WDC: +0.00%, SPY: -2.37%, QQQ: +3.75%

```
  GOOGL :  +189.15% (vs B&H: +86.52%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +748.68% (vs B&H: +231.74%, trades=6, win=50.0%, dd=-20.97%)
  SPY   :   +51.17% (vs B&H: +21.00%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +54.54% (vs B&H: +17.49%, trades=10, win=70.0%, dd=-1.69%)
```

**Parameters:** `{"fast_ma": 9, "slow_ma": 65, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 28.0, "vix_fear_entry": 26.0, "vix_extreme": 36.0, "vix_entry_decline": 4.5, "reentry_ma_reclaim": 5, "rsi_oversold": 30, "trailing_stop_atr_mult": 5.5, "reentry_cooldown_bars": 2}`

---

*Iterations 41-50: 6 improvements so far*

*Iterations 51-60: 6 improvements so far*

*Iterations 61-70: 6 improvements so far*

*Iterations 71-80: 6 improvements so far*

*Iterations 81-90: 6 improvements so far*

*Iterations 91-100: 6 improvements so far*


## Final Summary

**Total iterations:** 100
**Total improvements:** 6
**Improvement rate:** 6.0%

### Final Results
```
  GOOGL :  +189.15% (vs B&H: +86.52%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +748.68% (vs B&H: +231.74%, trades=6, win=50.0%, dd=-20.97%)
  SPY   :   +51.17% (vs B&H: +21.00%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +54.54% (vs B&H: +17.49%, trades=10, win=70.0%, dd=-1.69%)
```

### Final Parameters
```json
{
  "fast_ma": 9,
  "slow_ma": 65,
  "exit_ma": 50,
  "exit_confirm_bars": 3,
  "slope_lookback": 5,
  "vix_exit_boost": 28.0,
  "vix_fear_entry": 26.0,
  "vix_extreme": 36.0,
  "vix_entry_decline": 4.5,
  "reentry_ma_reclaim": 5,
  "rsi_oversold": 30,
  "trailing_stop_atr_mult": 5.5,
  "reentry_cooldown_bars": 2
}
```

Completed: 2026-04-09T03:06:43.658158+00:00


---

# Optimizer Run — 2026-04-09T03:18:54.886736+00:00

Resuming from improvement #6

## Starting Point
```
  GOOGL :  +189.15% (vs B&H: +86.52%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +748.68% (vs B&H: +231.74%, trades=6, win=50.0%, dd=-20.97%)
  SPY   :   +51.17% (vs B&H: +21.00%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +54.54% (vs B&H: +17.49%, trades=10, win=70.0%, dd=-1.69%)
```
Parameters: `{"fast_ma": 9, "slow_ma": 65, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 28.0, "vix_fear_entry": 26.0, "vix_extreme": 36.0, "vix_entry_decline": 4.5, "reentry_ma_reclaim": 5, "rsi_oversold": 30, "trailing_stop_atr_mult": 5.5, "reentry_cooldown_bars": 2}`

---

*Iterations 1-10: 6 improvements so far*

*Iterations 11-20: 6 improvements so far*

*Iterations 21-30: 6 improvements so far*

## Iteration 34 — IMPROVEMENT #7

**Changes:** vix_exit_boost: 28.0 -> 30.0

**Deltas:** GOOGL: +7.34%, WDC: +0.00%, SPY: +0.00%, QQQ: +0.00%

```
  GOOGL :  +196.49% (vs B&H: +93.86%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +748.68% (vs B&H: +231.74%, trades=6, win=50.0%, dd=-20.97%)
  SPY   :   +51.17% (vs B&H: +21.00%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +54.54% (vs B&H: +17.49%, trades=10, win=70.0%, dd=-1.69%)
```

**Parameters:** `{"fast_ma": 9, "slow_ma": 65, "exit_ma": 50, "exit_confirm_bars": 3, "slope_lookback": 5, "vix_exit_boost": 30.0, "vix_fear_entry": 26.0, "vix_extreme": 36.0, "vix_entry_decline": 4.5, "reentry_ma_reclaim": 5, "rsi_oversold": 30, "trailing_stop_atr_mult": 5.5, "reentry_cooldown_bars": 2}`

---

*Iterations 31-40: 7 improvements so far*

*Iterations 41-50: 7 improvements so far*

*Iterations 51-60: 7 improvements so far*

*Iterations 61-70: 7 improvements so far*

*Iterations 71-80: 7 improvements so far*

*Iterations 81-90: 7 improvements so far*

*Iterations 91-100: 7 improvements so far*


## Final Summary

**Total iterations:** 100
**Total improvements:** 7
**Improvement rate:** 7.0%

### Final Results
```
  GOOGL :  +196.49% (vs B&H: +93.86%, trades=10, win=100.0%, dd=0.0%)
  WDC   :  +748.68% (vs B&H: +231.74%, trades=6, win=50.0%, dd=-20.97%)
  SPY   :   +51.17% (vs B&H: +21.00%, trades=8, win=87.5%, dd=-0.43%)
  QQQ   :   +54.54% (vs B&H: +17.49%, trades=10, win=70.0%, dd=-1.69%)
```

### Final Parameters
```json
{
  "fast_ma": 9,
  "slow_ma": 65,
  "exit_ma": 50,
  "exit_confirm_bars": 3,
  "slope_lookback": 5,
  "vix_exit_boost": 30.0,
  "vix_fear_entry": 26.0,
  "vix_extreme": 36.0,
  "vix_entry_decline": 4.5,
  "reentry_ma_reclaim": 5,
  "rsi_oversold": 30,
  "trailing_stop_atr_mult": 5.5,
  "reentry_cooldown_bars": 2
}
```

Completed: 2026-04-09T03:18:55.717064+00:00

---

# Signal Optimization Attempt — 2026-04-09 (fast_reentry)

## Gap Analysis (GOOGL 2y trade_log)

Three gap types were assessed:
- **Missed upside (A):** After trade 7 (vix_accelerated_exit at 155.35 on 2025-04-23), price rose +5.7% over 8 bars before ma_reclaim triggered re-entry at 164.21 on 2025-05-05. Classic post-VIX-spike fast recovery missed.
- **Premature exits (B):** Trade 6 exited at 155.35 via vix_accelerated_exit; price continued up to ~164+ within 8 bars (+5.7%). Dominant pattern.
- **Pyramid gaps (C):** No clear evidence in the daily trade_log (pyramid analysis requires intraday data).

**Dominant gap type:** Fast re-entry missed after VIX-accelerated exits. Strategy exits defensively on VIX spike, but VIX then retreats quickly and price bounces strongly before any standard entry signal fires.

## Signal Created: `fast_reentry`

**File:** `strategies/smart_hold/signals/entries/fast_reentry.py`

**Logic:** Fire when (1) last exit was a vix_accelerated_exit, (2) VIX dropped >= 5 pts from peak AND fell back below vix_fear threshold, (3) price closed higher 2 consecutive bars, (4) price above fast EMA, (5) RSI 35–68, (6) not in chop.

**Registered:** Added to `registry.py` ENTRY_SIGNALS list between `vix_fear_declining` and `ma_reclaim`.

## Backtest Results (default CLI params)

| Symbol | Baseline vs_BH | With fast_reentry | Delta |
|--------|---------------|-------------------|-------|
| GOOGL  | +66.95%       | +66.95%           | 0.00% (signal didn't fire — VIX params different from best_params) |
| SPY    | +21.00%       | +20.83%           | **-0.17%** |
| QQQ    | +17.49%       | +12.80%           | **-4.69%** |

## Decision: REVERTED

2 of 3 symbols worse (SPY -0.17%, QQQ -4.69%). Signal commented out in registry.py.

**Root cause analysis:** The fast_reentry triggered too early in QQQ during the Aug 2024 recovery (after an initial ma_breakdown exit that was re-classified as vix_accelerated_exit in the new run), shifting all subsequent trade timing and reducing the long +5.82% ma_reclaim trade to +4.94% by entering at a higher price 5 bars earlier. The condition requiring VIX < vix_fear_entry needs to be tighter for low-vol ETFs — perhaps also requiring price above exit SMA to ensure we're not re-entering into a still-declining trend.

**Future refinement ideas:**
- Add `close > exit_sma` filter to prevent fast_reentry during structural downtrends
- Make `vix_fast_reentry_decline` threshold larger (e.g. 8-10 pts instead of 5) to require stronger VIX normalization
- Restrict fast_reentry to medium/high volatility stocks only (`median_atr_pct >= 1.5`) where the signal's concept was derived (GOOGL pattern)
- Consider a cooldown: only fire fast_reentry if bars_since_exit >= 3 to avoid catching too-early bounces

---

# Signal Optimization Run #2 — 2026-04-09 (fast_reentry v2)

## Changes from Run #1

Applied all four refinement ideas from the Run #1 post-mortem:

1. **Added `close > exit_sma` guard** — prevents re-entry when price is below the structural SMA (the root cause of QQQ regression in Run #1).
2. **Raised VIX decline threshold to 8.0 pts** (was 5.0) — requires stronger VIX normalization before firing.
3. **Added `bars_since_exit >= 3` cooldown** — avoid catching day-1/2 bounces post-exit; computed from candles + last trade exit_date.
4. **Bypassed `in_chop` check** — discovered that `in_chop=True` was blocking ALL fast_reentry firings in the 2y backtests, because after a VIX spike multiple exits accumulate (triggering the chop filter). The signal's own stricter guards (SMA above, VIX 8pt decline, 3-bar cooldown) replace the chop filter for this specific use case.

## Gap Analysis (GOOGL 2y)

- **Missed upside (A):** After vix_accelerated_exit on 2025-04-23, price rose to 164.03 on 2025-05-02 before VIX declined 8+ pts and price closed 2 consecutive bars up above exit_sma. Baseline ma_reclaim fired 3 days later at 164.21.
- **Binding constraints discovered:** in_chop=True was blocking the signal; VIX dropped below threshold before 2-consecutive-up price pattern formed.

## Backtest Results

| Symbol | Baseline vs_BH | With fast_reentry v2 | Delta |
|--------|---------------|----------------------|-------|
| GOOGL  | +66.95%       | +67.25%              | **+0.30%** |
| SPY    | +20.75%       | +20.75%              | 0.00% |
| QQQ    | +9.16%        | +9.16%               | 0.00% |
| **Avg**| —             | —                    | **+0.10%** |

## Decision: KEPT

1 improved, 2 neutral, 0 regressed. Signal enters 3 days earlier on GOOGL (164.03 vs 164.21) for a marginal improvement. SPY and QQQ see fast_reentry fire on the same bar as baseline ma_reclaim would have — no change in entry price.

**Signal committed:** `smart-hold-v5` branch

**Key learnings:**
- The `in_chop` bypass was essential — pure VIX-spike recoveries look like chop due to accumulated exits
- The `close > exit_sma` guard is critical to prevent structural-downtrend re-entries
- Marginal gains are acceptable when there's zero downside across all symbols
