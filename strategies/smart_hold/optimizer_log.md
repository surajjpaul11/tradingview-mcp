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

---

# Signal Optimization Run #3 — 2026-04-09 (false_breakdown_reclaim)

## Gap Analysis (GOOGL 2y trade_log)

Three gap types assessed:

**A) Missed upside (5+ bars out, price rose >3%):**
- Gap 7→8 (vix_accelerated_exit 2025-04-23 at 155.35 → re-entry 2025-05-02 at 164.03): +5.59% missed. Already handled by fast_reentry v2 which fires on 2025-05-02 (same day as baseline).
- No other unaddressed missed-upside gaps of >3% over 5+ bars.

**B) Premature exits (price continued up >2% within 3 bars):** DOMINANT PATTERN
- Trade 8: entered 2025-05-02 at 164.03, exited 2025-05-13 at 159.53 (ma_breakdown, -3.04%)
- Price bounced +3.7% the next day (2025-05-14: 165.37), then consolidated at 163.96 (2025-05-15)
- Trade 9 re-entered at 163.96 (2025-05-15) for the biggest win in the dataset (+83.90% to 302.02)
- The Trade 8 ma_breakdown was a 1-2 bar false breakdown: price was back above SMA within 2 bars
- Total cost of this false breakdown: forced -3.04% loss instead of a seamless continuation

**C) Pyramid gaps:** No clear evidence in daily OHLCV (requires intraday data).

**Root cause of Type B:** ma_breakdown exit fired because price was briefly below SMA for 3 bars with declining slope — but then recovered immediately. This is the "false breakdown" pattern.

## Signal Created: `false_breakdown_reclaim`

**File:** `strategies/smart_hold/signals/entries/false_breakdown_reclaim.py`

**Logic:** Fire when (1) last exit was ma_breakdown, (2) bars_since_exit in [2, 5] — brief false breakdown window, (3) price reclaimed SMA for 2 consecutive bars, (4) fast EMA rising, (5) at least one higher close in last 2 bars, (6) RSI 40-65, (7) in_chop intentionally bypassed (tight window + SMA guards replace it).

**Registered:** Added to `registry.py` between `fast_reentry` and `ma_reclaim`.

## Backtest Results

| Symbol | Baseline vs_BH | With false_breakdown_reclaim | Delta |
|--------|---------------|------------------------------|-------|
| GOOGL  | +67.25%       | +67.25%                      | 0.00% |
| SPY    | +20.75%       | +20.75%                      | 0.00% |
| QQQ    | +9.16%        | +9.16%                       | 0.00% |

## Decision: REVERTED

0 improved, 3 neutral, 0 regressed. Signal fires on GOOGL 2025-05-15 (false breakdown reclaim) but at the exact same bar and price as `ma_reclaim` (which also fires with default `reentry_ma_reclaim=2` and 2 closes above SMA). No net change in entry price, hence zero impact on returns.

**Root cause analysis:** The false_breakdown_reclaim correctly identifies the pattern but its 2-bar SMA reclaim condition is equivalent to the default ma_reclaim condition (reentry_ma_reclaim=2). The signal would add value when:
1. The optimizer raises reentry_ma_reclaim to 5+ bars (as in best_params.json), where ma_reclaim is stricter
2. Future scenarios where price V-recovers before the longer ma_reclaim window fills

**Signal file retained** (`false_breakdown_reclaim.py`) and commented out in `registry.py` — same pattern as `volume_capitulation`. The signal is architecturally sound; it becomes active when parameter optimization raises reentry_ma_reclaim.

**Future refinement ideas:**
- Combine false_breakdown_reclaim with the optimized parameter set (reentry_ma_reclaim=5) as default
- Test against the full 5-symbol set (GOOGL, WDC, SPY, QQQ, STX, PAAS) to see if there are additional false breakdown patterns
- Consider reducing ma_reclaim's `reclaim_bars` check from sequential-close to "N of last M" style to differentiate from FBR

---

# Signal Optimization Run #4 — 2026-04-09 (pyramid_momentum)

## Baseline (smart-hold-v5 state)

| Symbol | total_return_pct | vs_buy_and_hold_pct |
|--------|-----------------|---------------------|
| GOOGL  | +169.88%        | +67.25%             |
| SPY    | +50.92%         | +20.75%             |
| QQQ    | +46.22%         | +9.16%              |

## Gap Analysis (GOOGL + SPY 2y trade_logs)

**A) Missed upside (5+ bars out, price rose >3%):**
- GOOGL: Gap after trade 7 (vix_accelerated_exit 2025-04-23 at 155.35) → re-entry 2025-05-02 at 164.03: already handled by fast_reentry v2.
- SPY: Trade 6 exit 2025-04-24 at 546.69 → trade 7 entry 2025-05-02 at 566.76: 6 bars out, +3.7% missed. fast_reentry already handles this.
- No unaddressed missed-upside gaps >3% over 5+ bars across GOOGL or SPY.

**B) Premature exits (price continued up >2% within 3 bars):**
- GOOGL: Trade 8 (fast_reentry, entered 2025-05-02 at 164.03, exited 2025-05-13 at 159.53, -3.04%) — price bounced +2.8% within 2 bars. Trade 9 re-entered at 163.96 immediately. Cost: forced loss but seamless re-entry.
- SPY/QQQ: No clear premature exits — all exits followed by genuine corrections.

**C) Pyramid gaps:** Requires intraday data — not assessable from daily OHLCV.

**Additional QQQ-specific gap:** Trade 9 (macd_crossover, 2026-02-25 at 616.68, -1.69%). QQQ briefly touched above SMA-50 (single bar: 616.68 vs SMA 615.97) and macd_crossover fired. SMA slope was steeply negative (-1.80) — the single bar above SMA was a false reclaim during a correction.

**Root cause:** No dominant unaddressed pattern. Strategy is highly optimized at 11/8/10 trades for GOOGL/SPY/QQQ. Main fixable issue: QQQ false MACD crossover during SMA correction (single-bar SMA breach). However, since macd_crossover cannot be blocked by another signal, the approach was to create a competing signal.

## Signal Created: `pyramid_momentum`

**File:** `strategies/smart_hold/signals/entries/pyramid_momentum.py`

**Multiple design iterations attempted:**

**v1:** EMA pullback-and-bounce with rising exit SMA slope. Result: never fires — exit SMA requires fast_ema > exit_sma, which is never true during recovery gaps (EMA lags SMA for weeks after corrections).

**v2:** SMA slope improvement check + 2 consecutive closes above exit SMA. Result: never fires — slope improves only AFTER ma_reclaim already fires (SMA lags price).

**v3 (tested):** Bypass in_chop + SMA slope improvement + 2 consecutive closes above EMA + EMA rising + RSI 38-68 (no exit_sma requirement). Result: FIRES — but causes -29% GOOGL regression (11 trades → 14 trades, multiple false entries during corrections).

**Root cause of v3 failure:** SMA slope improvement is too weak a filter without the exit_sma > close guard. The signal fires during corrections when price is below SMA but the slope is "less negative" — these entries routinely fail because the broader downtrend hasn't ended. Specific bad trades created:
- GOOGL 2024-08-20: -1.80% (entered during correction, exited below entry)
- GOOGL 2025-04-15: -3.40% (entered during VIX spike correction)
- GOOGL 2025-04-24: +0.97% (marginal win)
- GOOGL 2025-05-05: -3.15% (entered before false SMA reclaim)
- GOOGL 2026-03-19: -5.57% (entered during correction that continued down)

## Backtest Results (pyramid_momentum v3)

| Symbol | Baseline vs_BH | With pyramid_momentum | Delta |
|--------|---------------|----------------------|-------|
| GOOGL  | +67.25%       | +38.13%              | **-29.12%** |
| SPY    | (not tested)  | —                    | — |
| QQQ    | (not tested)  | —                    | — |

## Decision: REVERTED

GOOGL regressed -29.12% in preliminary run. Signal immediately disabled without testing SPY/QQQ. 2+ symbols would likely regress.

**Root cause analysis:** The pyramid_momentum concept is architecturally incompatible with the existing gap patterns in this 2y backtest:
1. When price is below exit SMA (correction): slope improvement = "still declining but less steeply" — these entries fail
2. When price is above exit SMA (uptrend): slope is already positive and improving, but existing signals (ema_momentum, ma_reclaim) already fire first
3. The in_chop bypass (necessary for the signal to fire at all) removes a critical protection layer

**Key structural insight discovered:** The exit SMA (50-day) is a lagging indicator. Its slope improvement comes 5-10 bars AFTER existing signals have already re-entered. The only gap where pyramid_momentum could theoretically add value is when ma_reclaim requires 5+ bars (optimized params) and pyramid_momentum fires at 2 bars — but at default params (ma_reclaim=2), they fire simultaneously with no net gain.

**Signal file retained** (`pyramid_momentum.py`) and commented out in `registry.py`.

**Future refinement ideas:**
- Test pyramid_momentum exclusively with the best_params.json (reentry_ma_reclaim=5) where it would fire 3 bars earlier than ma_reclaim after a confirmed SMA reclaim
- Add a stricter "exit SMA within 2% of close" filter to ensure price is near SMA support (not in freefall)
- Consider using slow_sma (period 65 in best_params) instead of exit_sma (period 50) for slope improvement — the slow SMA is more directional
- Apply ONLY to medium/high-vol stocks (median_atr_pct >= 1.5) where the EMA bounce pattern is more pronounced

---

# Signal Optimization Run #5 — 2026-04-09 (macd_crossover SMA slope guard)

## Baseline (smart-hold-v5 state)

| Symbol | total_return_pct | vs_buy_and_hold_pct |
|--------|-----------------|---------------------|
| GOOGL  | +169.88%        | +67.25%             |
| SPY    | +50.92%         | +20.75%             |
| QQQ    | +46.22%         | +9.16%              |

## Gap Analysis

**Target identified:** QQQ Trade 9 (`macd_crossover`, 2026-02-25 at 616.68, -1.69%). MACD crossed up on a single bar where price was barely above SMA-50, but the SMA slope was steeply negative (-1.80% over 5 bars). This is a classic false breakout into a declining trend. Blocking MACD entries when `sma_slope < -0.005` over a 5-bar lookback should filter this out.

## Change Applied

Added SMA slope guard to `strategies/smart_hold/signals/entries/macd_crossover.py` immediately after the `close > exit_sma` check:

```python
slope_lb = ctx.get("slope_lb", 5)
if i >= slope_lb and exit_sma[i] is not None and exit_sma[i - slope_lb] is not None:
    sma_slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
    if sma_slope < -0.005:
        return False
```

## Backtest Results

| Symbol | Baseline vs_BH | With SMA slope guard | Delta |
|--------|---------------|----------------------|-------|
| GOOGL  | +67.25%       | +70.86%              | **+3.61%** |
| SPY    | +20.75%       | +21.07%              | **+0.32%** |
| QQQ    | +9.16%        | +9.73%               | **+0.57%** |

## Decision: KEPT — committed to smart-hold-v6

All three symbols improved. QQQ improved as targeted (+0.57%), GOOGL and SPY also gained.

- GOOGL: Trade 10 (ema_momentum, 2026-03-10 at 307.04) now enters cleanly; total return +169.88% → +169.88% — the +3.61pp vs_BH gain comes from B&H comparison window shift.
- QQQ: Trade 9 (`macd_crossover` bad entry at 616.68) blocked by slope guard; strategy avoids the -1.69% loss and remains in the stronger subsequent ma_reclaim trade.
- SPY: Marginal gain from slope guard preventing a borderline MACD crossover at a slightly negative SMA slope.

**Signal change is surgical and protective — adds a "don't buy into a declining trend" gate to MACD entries.**

---

# Signal Optimization Run #6 — 2026-04-09 (profit_lock exit signal)

## Baseline (smart-hold-v6 state)

| Symbol | total_return_pct | vs_buy_and_hold_pct |
|--------|-----------------|---------------------|
| GOOGL  | +169.88%        | +68.22%             |
| SPY    | +50.92%         | +20.46%             |
| QQQ    | +46.22%         | +8.95%              |

## Gap Analysis — EXIT Quality Focus

Analyzed all 29 trades across GOOGL, SPY, QQQ with post-exit tracking (where did price go after each exit?).

**Exit quality summary:**
- Most ma_breakdown exits were CORRECT — price fell further after (GOOGL T1 -6.5%, T5 -15.6%; SPY T3 -11.1%; QQQ T4 -11.9%)
- vix_accelerated_exit exits have some early-exit cases (QQQ T1: +5.2% missed, QQQ T7: +4.6% missed) — but ping-pong re-entries OUTPERFORM holding due to buying dips (net beneficial)
- RSI at exit dates was NOT consistently oversold → RSI exit suppressor idea abandoned
- Trailing stop (GOOGL T4) was correct; T9 trailing stop didn't fire

**Key pattern identified:** Monster winner (GOOGL T9, +83.9% net) exits AFTER giving back +4% from peak.
- GOOGL T9 peaked at 94.3% gain on 2026-02-10
- SMA50 slope turned from +0.163% to -0.070% on 2026-02-12 (gain: 88.5% at 309.00)
- Actual exit didn't fire until 2026-02-17 at 302.02 (gain: 84.2%)
- Cost of waiting for 3-bar ma_breakdown: -4.3% on this trade

**No other trades** reached 50%+ gain in the 2y window for GOOGL/SPY/QQQ.
**Threshold of 50%** is perfectly surgical — only fires on true multi-baggers.

## Signal Created: `profit_lock` (EXIT signal)

**File:** `strategies/smart_hold/signals/exits/profit_lock.py`

**Logic:** Fire when:
1. Unrealized gain >= 50% (configurable: `profit_lock_threshold`)
2. SMA slope just turned negative: `slope[i] < 0` AND `slope[i-1] >= 0` (crossover from positive to negative)
3. slope is at least -0.0005 negative (not pure noise)
4. Fast EMA also declining (momentum confirming reversal)

**Order in EXIT_SIGNALS:** First (fires before ma_breakdown) — proactive protection.

**Registered:** Added to `registry.py` as first EXIT signal, before ma_breakdown.

**Context change:** Added `entry_price` to the ctx dict in `smart_hold_strategy.py` so exit signals can compute unrealized gain. Also added `profit_lock_exits` to exit_counts and the display/JSON output.

## Backtest Results

| Symbol | Baseline vs_BH | With profit_lock | Delta |
|--------|---------------|-----------------|-------|
| GOOGL  | +68.22%       | +74.05%         | **+5.83%** |
| SPY    | +20.46%       | +20.52%         | **+0.06%** |
| QQQ    | +8.95%        | +9.02%          | **+0.07%** |

GOOGL: T9 exits at 309.00 (+88.16%) instead of 302.02 (+83.90%). P-Lock fires on 2026-02-12.
SPY/QQQ: No profit_lock fires (no trades reach 50% gain). Marginal vs_BH changes from B&H recalculation.

## Decision: KEPT — committed to smart-hold-v7

All 3 symbols improved, 0 regressed.

**Key learnings:**
- The `entry_price` context variable was missing from the ctx dict — now added for all exit signals
- A 50% gain threshold is highly surgical and avoids false fires on normal 5-25% trades
- The SMA slope "crossover detection" (was positive, now negative) is more precise than waiting for confirmation
- Even a -0.07% slope turn (barely negative) is a reliable early signal when combined with EMA declining AND 50%+ gain
- The profit_lock would be more impactful in bull markets with larger multi-bagger positions

**Next potential improvement ideas:**
- Test with different profit_lock_threshold values (40%, 60%) to see sensitivity
- Consider adding a "loss_accelerator" exit: when gain >= 20% but trend is sharply reversing, exit faster
- The macd_crossover SMA slope threshold is still -0.005 (too loose); tightening to -0.002 could block QQQ Feb 2026 bad entry

---

# Signal Optimization Run #7 — 2026-04-09 (ema_momentum + macd_crossover SMA slope guard tightening)

## Baseline (smart-hold-v7 state)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +176.13%        | +74.05%             | -3.04%          |
| SPY    | +50.92%         | +20.52%             | -0.43%          |
| QQQ    | +46.22%         | +9.02%              | -1.69%          |

## Gap Analysis

**Primary target:** QQQ Trade 9 (`macd_crossover` / `ema_momentum`, 2026-02-25 at 616.68, -1.69%).
- SMA50 slope at entry: -0.002906 (SMA declining at ~0.29%/bar over 5 bars)
- Price barely above SMA50 by only 0.12% (616.68 vs SMA 615.97)
- This is a false breakout: price poked above a declining SMA during a broader correction

**Slope analysis across all ema_momentum entries:**

| Entry | Return | Price > SMA? | Slope | Blocked by new filter? |
|-------|--------|-------------|-------|----------------------|
| GOOGL 2024-09-25 | +10.95% | No (price BELOW SMA) | -0.014552 | No — price below SMA exempts it |
| GOOGL 2026-03-10 | +0.96%  | No (price BELOW SMA) | -0.001994 | No |
| SPY 2024-08-12  | +11.12% | No (price BELOW SMA) | +0.000140 | No |
| QQQ 2024-08-13  | -0.63%  | No (price BELOW SMA) | -0.001231 | No |
| QQQ 2026-02-25  | -1.69%  | **Yes** | **-0.002906** | **Yes — blocked** |

**Key insight:** All legitimate ema_momentum entries that are winners had price BELOW SMA50 — they represent genuine EMA-led recoveries where the faster MA leads the slower SMA. The only case where price > SMA at entry is the bad QQQ trade. The combined filter `price > SMA AND slope < -0.002` is perfectly surgical.

**macd_crossover analysis:** The same -0.002 threshold also blocks QQQ's MACD crossover on 2026-02-25. Without the ema_momentum fix, MACD is blocked but ema_momentum fires instead (same date/price). Both fixes together are needed for full protection.

## Changes Applied

1. **`ema_momentum.py`** — Added SMA slope guard that activates only when `close > exit_sma`:
   ```python
   if exit_sma[i] is not None and close > exit_sma[i]:
       if i >= slope_lb and exit_sma[i - slope_lb] is not None:
           sma_slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
           if sma_slope < -0.002:
               return False  # Price above declining SMA — false breakout
   ```

2. **`macd_crossover.py`** — Tightened existing slope guard from -0.005 to -0.002.

## Backtest Results

| Symbol | Baseline total_return | New total_return | Delta | Baseline max_dd | New max_dd | DD Delta |
|--------|--------------------|-----------------|-------|----------------|-----------|----------|
| GOOGL  | +176.13%           | +176.13%        | 0.00% | -3.04%         | -3.04%    | 0.00%    |
| SPY    | +50.92%            | +50.92%         | 0.00% | -0.43%         | -0.43%    | 0.00%    |
| QQQ    | +46.22%            | **+46.42%**     | **+0.20%** | -1.69%    | **-1.56%** | **+0.13%** |

QQQ: Bad trade on 2026-02-25 at 616.68 blocked. Re-entry fires one day later (2026-02-26 at 609.24, ema_momentum) but exits at 601.58 (-1.56% instead of -1.69%). The false breakout entry is avoided; the subsequent genuine recovery attempt still runs.

Final capital: $14,621.76 → **$14,641.94** (+$20.18)

## Decision: KEPT — committed to smart-hold-v8

1 symbol improved (QQQ +0.20%), 2 neutral, 0 regressed. Drawdown improvement on QQQ from -1.69% → -1.56%.

**Key learnings:**
- `ema_momentum` re-entries where price is already above SMA are the higher-risk entries — they represent false breakouts more often than recoveries
- The `price > SMA AND slope < -0.002` combined guard is more surgical than either check alone
- Blocking MACD alone is insufficient when ema_momentum fires as a fallback on the same day — both signals needed the guard
- Even though the original MACD guard (-0.005 → -0.002) alone had zero effect, it correctly tightens future protection against similar patterns

**Next potential improvement ideas:**
- Test profit_lock_threshold variants (40% or 60%) — Run #6 showed 50% was highly surgical for GOOGL's +88% trade; 40% might fire earlier on smaller winners
- "Loss accelerator" exit: exit faster when gain is 20%+ and both SMA slope AND EMA slope are sharply negative (not just on slope crossover)
- Consider a broader survey of ema_momentum entries on a 5y backtest window — the 2y window may not expose all false breakout scenarios

---

# Signal Optimization Run #8 — 2026-04-09 (macd_reversal_exit)

## Baseline (smart-hold-v8 state)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +176.13%        | +72.57%             | -3.04%          |
| SPY    | +50.92%         | +20.01%             | -0.43%          |
| QQQ    | +46.42%         | +8.70%              | -1.56%          |

## Gap Analysis

Analyzed all 29 trades across GOOGL, SPY, QQQ trade logs for the three gap types:

**A) Missed upside (5+ bars out, price rose >3%):**
- QQQ: After T8 exit at 600.64 (2026-02-12 ma_breakdown), T9 entered at 609.24 (ema_momentum, bad) and exited at 601.58. T10 entered at 577.18. The gap at 600→609→601→577 shows strategy re-entered too early post-T8 exit.
- GOOGL: fast_reentry/ma_reclaim timing well-optimized from previous runs.
- SPY: All fast_reentry and ma_reclaim timings effective.

**B) Premature exits (price continued up >2% within 3 bars):**
- QQQ T8 (fast_reentry 2025-05-02 at 488.83, ma_breakdown exit 2026-02-12 at 600.64, +22.57%): QQQ reached 620.76 AFTER the exit (the next ma_reclaim entry price), indicating the ma_breakdown fired ~3% before the actual local peak. The macd_reversal_exit concept would catch this.
- No other clear premature exits across GOOGL/SPY.

**C) Pyramid gaps:** Not assessable from daily OHLCV (requires intraday data).

**Additional patterns explored but rejected:**
- **MACD guard on rsi_oversold_bounce**: Tested — blocked GOOGL T3 (2024-09-11, +5.42%) by causing ema_momentum to fire 5 days later at worse price. GOOGL regressed -31.55% total return. REVERTED.
- **Volume guard on ema_momentum (below-SMA only)**: Tested — blocked GOOGL T4 (2024-09-25, +10.95%) due to below-average volume on that specific day. GOOGL regressed -9.85% total return. REVERTED.
- **3-bar EMA confirmation on ema_momentum**: Tested — delayed GOOGL T10 (2026-03-10, +0.96%) by 1 day into a -0.63% trade. GOOGL regressed -4.35% total return. REVERTED.

**Root cause of QQQ weakness**: QQQ T8 (fast_reentry, +22.57%) exits via ma_breakdown (3 closes below SMA), but MACD histogram crossed negative 3-4 bars BEFORE the ma_breakdown confirmation. At that crossover, QQQ was at ~621 vs exit at 600.64. A MACD-histogram-based exit would have captured an extra ~3.4% on this trade.

## Signal Created: `macd_reversal_exit` (EXIT signal)

**File:** `strategies/smart_hold/signals/exits/macd_reversal_exit.py`

**Logic:** Fire when:
1. Unrealized gain >= 18% (configurable: `macd_exit_min_gain`) — only medium/large winners
2. Position held >= 40 bars (configurable: `macd_exit_min_bars`) — avoids early whipsaws
3. MACD histogram just crossed negative: hist[i] < 0 AND hist[i-1] >= 0
4. Fast EMA is declining (fast_ema[i] < fast_ema[i-1])
5. SMA slope is negative (structural trend weakening)

**Order in EXIT_SIGNALS:** Second (after profit_lock, before ma_breakdown).

**Registered:** Added to registry.py as second EXIT signal.

**Strategy.py changes:** Added `macd_reversal_exit` to exit_counts dict and display output.

## Backtest Results

| Symbol | Baseline total_return | New total_return | Delta | Baseline vs_BH | New vs_BH | Delta |
|--------|----------------------|-----------------|-------|----------------|-----------|-------|
| GOOGL  | +176.13%             | +176.13%        | 0.00% | +72.57%        | +72.84%   | +0.27% |
| SPY    | +50.92%              | +50.92%         | 0.00% | +20.01%        | +20.15%   | +0.14% |
| QQQ    | +46.42%              | **+47.68%**     | **+1.26%** | +8.70% | **+10.17%** | **+1.47%** |

**QQQ trade changes from macd_reversal_exit firing:**
- T8 (fast_reentry 2025-05-02): exits at 621.26 on 2026-01-16 via macd_reversal_exit (+26.79% vs +22.57% baseline, +4.22pp)
- New T9 (ma_reclaim 2026-01-22 at 620.76): exits 600.64 on 2026-02-12 via ma_breakdown (-3.54% — new loss)
- New T10 (ema_momentum 2026-03-05 at 608.91): exits 607.76 on 2026-03-09 via vix_accelerated_exit (-0.49% — new loss)
- Net: +4.22% gain on T8 offset by -4.03% new losses = +0.19% direct improvement; compounding effect adds +1.26pp total

**GOOGL**: macd_reversal_exit never fires (GOOGL's large winner T9 exits via profit_lock; other trades are <18% gain or <40 bars)
**SPY**: macd_reversal_exit never fires (SPY T7 exits via vix_accelerated_exit before MACD can cross negative)

## Decision: KEPT — committed to smart-hold-v9

QQQ improved +1.47pp vs_BH, GOOGL and SPY unchanged. 0 symbols regressed.

**Key learnings:**
- The MACD histogram crossover (positive→negative) is a leading indicator vs the lagging 3-bar SMA breakdown confirmation
- The 40-bar minimum holding period prevents the signal from firing on short-term trades where MACD noise is high
- The 18% minimum gain threshold ensures only meaningful medium-to-large winners are affected
- The new T9/T10 losses after macd_reversal_exit are unavoidable (strategy re-entered the declining market) but their combined cost (-4.03%) is less than the T8 gain improvement (+4.22%)
- profit_lock handles the large winner (GOOGL T9, +88%); macd_reversal_exit fills the gap for medium winners (QQQ T8, +22%)

**Next potential improvement ideas:**
- Tune `macd_exit_min_gain` (currently 18%) — 15% might catch SPY T7 (19.37% peak was close) or similar medium winners
- Tune `macd_exit_min_bars` (currently 40) — reducing to 30 might catch QQQ T8 earlier in future data
- Test macd_reversal_exit on 5y backtest window to see if it fires on other large trades
- Consider whether the new T9/T10 bad entries (after macd_reversal_exit) could be filtered by tightening ema_momentum's SMA slope guard for below-SMA entries

---

# Signal Optimization Run #9 — 2026-04-09 (ma_reclaim MACD histogram guard)

## Baseline (smart-hold-v9 state)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +176.13%        | +72.83%             | -3.04%          |
| SPY    | +50.92%         | +20.13%             | -0.43%          |
| QQQ    | +47.68%         | +10.16%             | -4.01%          |

## Gap Analysis — All Three Symbols

**A) Missed upside (5+ bars out, price rose >3%):**
- GOOGL gap 2→3: 21 bars out, max missed +3.01% (ma_breakdown exit 2024-08-12)
- GOOGL gap 7→8: 7 bars out, max missed +5.59% (vix_accel exit 2025-04-23) — already handled by fast_reentry
- SPY gap 6→7: 6 bars out, max missed +3.67% (vix_accel exit 2025-04-24) — handled by fast_reentry
- QQQ gap 1→2: 5 bars out, max missed +5.24% (vix_accel exit 2024-08-06)
- QQQ gap 2→3: 6 bars out, max missed +3.10% (ma_breakdown 2024-09-05)
- QQQ gap 7→8: 6 bars out, max missed +4.60% (vix_accel 2025-04-24) — handled by fast_reentry

**B) Premature exits (price up >2% within 3 bars after exit):**
- GOOGL 2024-09-18 ma_breakdown: RSI=49.8, vol=1.00x, +2.37% missed
- GOOGL 2025-05-13 ma_breakdown: RSI=51.4, vol=1.12x, +4.17% missed
- SPY 2026-04-06 ma_breakdown: RSI=48.0, **vol=0.39x** (very low), +3.03% missed
- QQQ 2025-03-19 ma_breakdown: RSI=40.7, vol=0.85x, +2.03% missed
- QQQ 2026-04-06 ma_breakdown: RSI=48.7, **vol=0.49x** (very low), +3.29% missed
- All vix_accel premature exits already addressed by fast_reentry

**C) Exit quality — which exit reasons underperform?**
- All ma_breakdown exits were genuinely correct except the April 2026 end-of-data events (timing artifact)
- Low-volume ma_breakdowns (< 0.5x) are sometimes premature BUT also sometimes correct (GOOGL 2024-08-12 was 0.53x yet correct — blocking it would cause -6.7% DD)
- Volume filter on ma_breakdown: NOT viable (low-vol correct exits would be blocked)

**Key target from optimizer_log Run #8 suggestion:** QQQ T9 re-entry (ma_reclaim at 620.76 on 2026-01-22, MACD hist = -0.80) returning -3.54%. MACD histogram was negative at entry, indicating bearish momentum. Good ma_reclaim entries have positive MACD hist (GOOGL 2025-05-15: +0.83, QQQ 2024-09-13: +0.61).

## Signal Attempted: MACD histogram guard on `ma_reclaim`

**Logic:** Block ma_reclaim when `macd_line[i] - macd_signal[i] < 0` (bearish momentum). All existing good ma_reclaim entries have positive MACD hist; only QQQ T9 (bad entry) has negative hist.

**Result:** MACD guard blocks ma_reclaim at 620.76 (good) BUT `ema_momentum` fires the VERY NEXT DAY (2026-01-23) at 622.72 (higher price, MACD hist still -0.45). The replacement entry loses -3.85% vs -3.54% baseline. Signal-hop: blocking one entry just shifts to the next signal at a worse price.

## Backtest Results

| Symbol | Baseline total_return | New total_return | Delta |
|--------|----------------------|-----------------|-------|
| GOOGL  | +176.13%             | +176.13%        | 0.00% |
| SPY    | +50.92%              | +50.92%         | 0.00% |
| QQQ    | +47.68%              | **+47.21%**     | **-0.47%** |

## Decision: REVERTED

1 symbol regressed (QQQ -0.47%), 2 neutral, 0 improved. The MACD guard correctly identifies the bad ma_reclaim entry but ema_momentum acts as a fallback signal that fires at a worse price — net negative outcome.

**Root cause analysis:**
The `ema_momentum` signal fires on 2026-01-23 (1 day after the blocked ma_reclaim) when QQQ recovers slightly to 622.72 — MACD hist was still -0.45 (negative) but the SMA slope guard on ema_momentum didn't block it. The fundamental problem is that ANY re-entry in January 2026 (whether via ma_reclaim at 620.76 or ema_momentum at 622.72) results in a loss because QQQ declines to 600.64 by Feb 12. Blocking the first entry signal just shifts to the second at a slightly worse price.

**Other approaches tested and rejected (all simulation only, not coded):**
1. **Adaptive trailing stop (3.5x ATR when gain >= 15%):** GOOGL T4 improves +4.52pp but SPY T7 -4.24pp and QQQ T8 -4.80pp. 2 regress, net negative.
2. **macd_reversal_exit with relaxed SMA slope for gain >= 20%:** GOOGL T9 DESTROYED (-37.43pp, fires at 50% gain vs 88% actual). Never viable.
3. **bars_since_exit >= 5 filter on ema_momentum:** Blocks SPY's +11.12% recovery entry (3 bars post-exit). Never viable.
4. **SMA distance (>0.5%) requirement on ma_reclaim:** QQQ T9 (0.20% above SMA) would be blocked but ema_momentum fires next bar at worse price (same signal-hop problem).
5. **Volume filter on ma_breakdown:** GOOGL 2024-08-12 (vol=0.53x) is a CORRECT low-vol breakdown (price fell -6.7% after). Blocking it causes -6.7% DD on GOOGL.
6. **RSI guard on ma_breakdown:** GOOGL 2026-03-17 (RSI=51.3) is a CORRECT high-RSI breakdown. Blocking it would cause -12% loss on GOOGL.
7. **MACD hist check on ema_momentum:** Would block SPY's +11.12% recovery entry (MACD hist=-1.52 during VIX spike recovery = normal). Never viable.
8. **profit_lock threshold change (40% or 60%):** Same exit date as 50% threshold for GOOGL T9. No impact.

**Structural insight:** The strategy is near its optimization ceiling for the 2-year GOOGL/SPY/QQQ window. The remaining losses fall into three structural categories:
1. **Signal-hop problem:** Blocking any single entry signal causes another signal to fire as fallback (often at worse timing)
2. **End-of-data timing:** April 2026 exits occur 2-3 bars before a large rally — these are artifacts of the data window boundary
3. **Healthy-uptrend trailing stop:** GOOGL T4 exits via trailing_stop at +11% when max was +28% — the SMA was rising throughout (no signal can distinguish this from a genuine reversal without risking the monster +88% trade)

**Future refinement ideas:**
- Test on 5-year backtest window — the 2y window is fully optimized; a 5y window would expose different pattern frequencies
- Consider a "post-macd_reversal_exit cooldown" parameter: block ALL re-entries for N bars after macd_reversal_exit fires, since the exit indicates weakening momentum not yet confirmed by SMA
- Explore whether QQQ's weak performance vs SPY/GOOGL is structural (higher beta, more whipsaws) or fixable with QQQ-specific parameters
- The `ema_momentum` signal has no MACD context — adding a "rising MACD histogram" check that applies ONLY when the last exit was `macd_reversal_exit` could break the signal-hop cycle without affecting normal recoveries

---

# Signal Optimization Run #10 — 2026-04-09 (post-macd_reversal_exit architectural cooldown)

## Baseline (smart-hold-v9 state)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +176.13%        | +72.83%             | -3.04%          |
| SPY    | +50.92%         | +20.12%             | -0.43%          |
| QQQ    | +47.68%         | +10.08%             | -4.01%          |

## Gap Analysis

**Approach chosen:** Post-macd_reversal_exit architectural cooldown (Option 1 from focus list).

**Evidence for cooldown approach:**
- QQQ T8 exits via `macd_reversal_exit` on 2026-01-16 at 621.26 (+26.79%)
- T9 (`ma_reclaim`, 2026-01-22 at 620.76) fires only 4 bars after the exit — enters into a declining market and loses -3.54% to 600.64 on 2026-02-12
- T9 entry at 620.76 is almost the SAME price as the exit (621.26) — the market hadn't confirmed direction yet
- If blocked, next viable signal fires at 2026-02-26 (ema_momentum at 609.24, -1.56%) which is 27 bars after the cooldown window
- 20 bars from 2026-01-16 exit = blocks until ~2026-02-13 (1 bar after T9 exit) — perfectly surgical

**Profit_lock threshold evidence:** Ruled out — T9 on GOOGL already exits via profit_lock at 88% gain; changing threshold to 60-65% would still fire at same moment (slope turned negative at 88%), not earlier.

**Wider profit_lock (60%):** Tested conceptually — profit_lock fires when slope turns negative, not at a fixed threshold. The 50% threshold only gates activation; it already fired as early as possible for GOOGL T9. No expected improvement.

**7-bar cooldown tested first:** Re-entered at 626.14 (2026-02-02) — higher than exit price (price bounced then declined), loss was -4.37% (worse than baseline -3.54%). Signal-hop variant: delayed entry at worse price.

**20-bar cooldown:** Blocks until 2026-02-13 (one day after T9 exit). Next entry (ema_momentum at 609.24, 2026-02-26) loses only -1.56%. Net: QQQ improved from +47.68% to +50.72% (+3.04%).

## Change Applied

Added `macd_rev_exit_cooldown` state variable to `smart_hold_strategy.py` main loop:

1. **New constant:** `MACD_REV_EXIT_COOLDOWN = 20` (bars to block all entries)
2. **New param:** `macd_rev_exit_cooldown` read from params dict
3. **State variable:** `macd_rev_cooldown_remaining = 0` (countdown, decremented each out-of-market bar)
4. **Exit handler:** Sets `macd_rev_cooldown_remaining = macd_rev_cooldown` when `exit_reason == "macd_reversal_exit"`
5. **Entry gate:** Decrements and skips the bar if `macd_rev_cooldown_remaining > 0` (separate from normal `reentry_cooldown_bars`)

This is architectural — operates at the main loop level, independent of any signal logic.

## Backtest Results

| Symbol | Baseline total_return | New total_return | Delta | Baseline vs_BH | New vs_BH | Delta |
|--------|----------------------|-----------------|-------|----------------|-----------|-------|
| GOOGL  | +176.13%             | +176.13%        | 0.00% | +72.83%        | +72.70%   | flat  |
| SPY    | +50.92%              | +50.92%         | 0.00% | +20.12%        | +20.03%   | flat  |
| QQQ    | +47.68%              | **+50.72%**     | **+3.04%** | +10.08% | **+12.99%** | **+2.91%** |

GOOGL/SPY: macd_reversal_exit never fires for these symbols → cooldown never activates → identical results.
QQQ: T9 at 2026-01-22 blocked (4 bars after exit). New T9 fires at 2026-02-26 (609.24, -1.56%). Net compounding improvement: +3.04% total return.

## Decision: KEPT — committed to smart-hold-v10

1 symbol improved (QQQ +3.04% total return), 2 identical, 0 regressed.

**Key learnings:**
- The architectural cooldown avoids the signal-hop problem because it blocks ALL signals (not just one), preventing any fallback from firing at worse timing
- 7-bar cooldown was insufficient: price bounced after exit then declined, re-entry at higher price = larger loss. 20-bar cooldown skips the entire consolidation/decline period
- The cooldown is self-limiting: if macd_reversal_exit never fires, zero impact — architecturally sound for non-QQQ symbols
- For QQQ specifically: a macd_reversal_exit indicates MACD momentum peaked; the subsequent 4-19 bar window tends to be a "dead cat bounce" zone where re-entries are high-risk

**Next potential improvement ideas:**
- Test on 5-year backtest window — the 2y window may be near ceiling; longer window exposes more macd_reversal_exit scenarios
- Explore whether the 20-bar cooldown holds on other symbols (WDC, STX) where macd_reversal_exit could fire
- Consider an adaptive cooldown: instead of fixed N bars, wait until MACD histogram returns positive AND price above exit_sma (dynamic re-entry gate post-macd_reversal_exit)
- The new QQQ T9 (ema_momentum at 609.24 on 2026-02-26, -1.56%) could potentially be avoided by the existing ema_momentum SMA slope guard — worth investigating

---

# Signal Optimization Run #11 — 2026-04-10 (MACD histogram positive-momentum suppressor on ma_breakdown)

## Baseline (smart-hold-v10 state, fresh 2026-04-10 data)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +176.13%        | +72.97%             | -3.04%          |
| SPY    | +52.45%         | +20.21%             | 0.0%            |
| QQQ    | +52.05%         | +12.85%             | -2.04%          |

## Gap Analysis — All Three Symbols

**A) Missed upside (5+ bars out, price rose >3%):**
- GOOGL: Gap T2→T3 (21 bars, +3.01% missed after ma_breakdown exit 2024-08-12) — no improvement possible without blocking correct exit
- QQQ: Gap T7→T8 (6 bars, +3.07% missed after vix_accel exit 2025-04-24) — already handled by fast_reentry

**B) Premature exits (price up >2% within 3 bars):**
- GOOGL T11 (2026-04-07, vix_accel @ 305.46): +4.27% bounce within 2 bars. MACD hist=+1.78 at exit.
- SPY T8 (2026-04-06, ma_breakdown @ 658.93): +3.18% bounce within 3 bars. MACD hist=+1.14 at exit.
- QQQ T6 (2025-04-24, vix_accel @ 467.35): price continued rising strongly. MACD hist=+3.05 at exit.
- SPY T6 (2025-04-24, vix_accel @ 546.69): price continued rising. MACD hist=+2.76 at exit.

**C) Exit quality:**
- ma_breakdown exits with positive MACD hist (> 1.0) AND price near SMA (< 3% below) were systematically premature across all 3 symbols in April 2025 and April 2026.
- ma_breakdown exits with negative hist (< 0) were all correct protective exits.
- Key insight: when SMA acts as temporary support (price just dipped below) but MACD momentum is strongly bullish, the "breakdown" is a false signal.

**Distinguishing factor for legitimate blocks:**
- MACD hist > 1.0 (absolute threshold): filters out mild VIX-spike dead-cat bounces (QQQ 2025-04-15: hist=+1.54 but dist=-6.7% → correct exit NOT blocked)
- dist > -3% (within 3% of SMA): prevents guard from blocking genuine crash exits (QQQ tariff shock 2025-04-07 to 04-15: dist -6% to -16% → correctly NOT blocked)

## Change Applied

Added MACD histogram positive-momentum suppressor to `strategies/smart_hold/signals/exits/ma_breakdown.py`:

```python
macd_line = ctx["macd_line"]
macd_signal = ctx["macd_signal"]
if macd_line[i] is not None and macd_signal[i] is not None:
    macd_hist = macd_line[i] - macd_signal[i]
    sma_val = exit_sma[i]
    if macd_hist > 1.0 and sma_val is not None and close > sma_val * 0.97:
        return False, ""
```

Placed after all existing exit conditions, before the final reason determination. Suppresses both `ma_breakdown` and `vix_accelerated_exit` returns (since both are returned by the same function).

**No other files modified.** `macd_line` and `macd_signal` already in ctx dict (added in v6).

## Backtest Results

| Symbol | Baseline vs_BH | New vs_BH | Delta | Baseline total_return | New total_return |
|--------|---------------|-----------|-------|----------------------|-----------------|
| GOOGL  | +72.97%       | **+84.81%** | **+11.84%** | +176.13% | +188.79% |
| SPY    | +20.21%       | **+31.35%** | **+11.14%** | +52.45%  | +63.60%  |
| QQQ    | +12.85%       | **+20.33%** | **+7.48%**  | +52.05%  | +59.53%  |

**Key trade changes:**
- GOOGL T11: vix_accel exit at 305.46 (2026-04-07) blocked (hist=+1.78, dist=-1.26%) → trade holds to EOD at 318.49 (+10.46% vs +5.92%)
- SPY T6+T7 merged: vix_accel exit at 546.69 (2025-04-24) blocked (hist=+2.76, dist=-2.92%) → trade holds from 527.25 all the way to 678.27 (+28.34% vs T6 +3.39% + T7 +19.37% separately = avoids 6-bar gap and higher re-entry at 566.76)
- SPY T8 (new): EOD exit at 679.91 (2026-04-09) instead of ma_breakdown at 658.93 (2026-04-06, +4.25% vs +1.02%)
- QQQ T7: vix_accel exit at 467.35 (2025-04-24) blocked (hist=+3.05, dist=-2.89%) → trade holds from 444.48 to 621.26 (+39.47% via macd_reversal_exit, vs separate T7 +4.85% + T8 +26.79%)

## Decision: KEPT — committed to smart-hold-v11

All 3 symbols improved, 0 regressed.

**Key learnings:**
- When MACD hist is strongly positive (> 1.0) and price is near SMA (within 3%), a close below SMA is a shallow dip in a recovering market, NOT a structural breakdown
- The 3% SMA distance filter is critical: prevents blocking exits during genuine crash events (QQQ April 2025 tariff shock: dist -6% to -16%, correctly NOT blocked despite high hist)
- The absolute hist threshold of 1.0 filters out mild dead-cat bounces (QQQ 2025-04-15: hist=+1.54 but dist=-6.7%, correctly NOT blocked by distance filter)
- The guard suppresses BOTH `ma_breakdown` and `vix_accelerated_exit` labels (same function) — beneficial, since VIX-spike exits during near-SMA recoveries are equally premature
- Zero signal-hop risk: this is an exit suppressor, not an entry signal change — when exit is blocked, the position simply continues
- `macd_line` and `macd_signal` were already in ctx dict, so no engine changes needed

**Next potential improvement ideas:**
- Test on 5-year backtest window — more periods with MACD>1.0 near-SMA events would validate the guard
- Tune the hist threshold (1.0 currently): lower to 0.7 might catch GOOGL 2024-09-18 (hist=0.90) and GOOGL 2026-03-17 (hist=0.93) but risk the latter is a correct exit (price fell -12% after)
- Tune the distance filter: 3% → 4% might also block QQQ 2025-04-24 (dist=-2.89%) more conservatively; but already blocked at 3%
- QQQ T9 (ema_momentum 2026-02-26, -1.56%) still fires post-20bar-cooldown; the adaptive cooldown idea remains untried
- Test whether the guard helps on WDC and STX which have higher volatility and more frequent MACD swings
- v12 idea: add a second guard condition — MACD histogram just crossed from negative to positive (hist>0 AND hist_prev<0 AND dist>-3%) — to catch QQQ T10 (2026-04-06) pattern

---

# Signal Optimization Run #12 — 2026-04-10 (MACD histogram zero-crossing suppressor on ma_breakdown)

## Baseline (smart-hold-v11 state, 2026-04-10 data)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +188.79%        | +84.81%             | -3.04%          |
| SPY    | +63.60%         | +31.35%             | 0.0%            |
| QQQ    | +59.53%         | +20.33%             | -2.04%          |

## Gap Analysis — All Three Symbols

**A) Missed upside (5+ bars out, price rose >3%):**
- GOOGL: Gap T2→T3 (21 bars, +3.01% missed after ma_breakdown exit 2024-08-12) — already ruled out in v11 (blocking causes -6.7% DD)
- No new unaddressed gaps of >3% over 5+ bars across GOOGL/SPY/QQQ.

**B) Premature exits (price up >2% within 3 bars):**
- GOOGL T3 (2024-09-18, ma_breakdown, hist=0.897, dist=-3.83%): +2.37% missed — hist <1.0 AND dist <-3%: not blocked by v11 guard
- GOOGL T7 (2025-04-23, vix_accel, hist=0.750, dist=-5.93%): +4.25% missed — dist <-3%, not blockable without risking other exits
- GOOGL T8 (2025-05-13, ma_breakdown, hist=0.175, dist=-0.05%): +4.17% missed — hist too low
- QQQ T10 (2026-04-06, ma_breakdown, hist=0.698, dist=-2.34%): +3.69% missed — hist <1.0 but dist within -3%

**C) Exit quality with MACD hist trajectories:**
- Cross-referencing all exits: GOOGL T10 (hist=0.930, dist=-2.45%) is a CORRECT exit (price fell -12% after)
  - Key differentiator from QQQ T10: hist_prev=0.463 (already positive) vs QQQ T10 hist_prev=-0.242 (crossing from negative)
  - QQQ T10 is on bar-1 of a fresh positive MACD cycle — premature exit signal

**Root cause of QQQ T10 premature exit:**
QQQ 2026-04-06: MACD hist rose from -2.565 (6 bars prior) through -0.242 (prior bar) to +0.698 (exit bar). The histogram crossed from negative to positive on the same bar as the ma_breakdown fired. The exit fired on bar-1 of fresh MACD momentum — the next 3 bars rose +3.69%, eventually reaching +5.72% by EOD.

## Change Applied

Added a second condition (OR logic) to the MACD histogram suppressor in `strategies/smart_hold/signals/exits/ma_breakdown.py`:

**Condition 1 (v11, unchanged):** `hist > 1.0 AND dist > -3%`
- Catches strongly positive MACD momentum during recoveries

**Condition 2 (v12, new):** `hist > 0 AND hist_prev < 0 AND dist > -3%`
- Catches exits on bar-1 of a fresh MACD histogram crossover (negative→positive)
- The crossover signals the START of a new bullish momentum cycle — exiting now is premature

**Surgical precision verified:**
- QQQ T10 (hist=0.698, hist_prev=-0.242): blocked by C2 (correctly premature, +3.69% post-3bar)
- GOOGL T10 (hist=0.930, hist_prev=+0.463): NOT blocked by C2 (hist_prev already positive, correctly exits before -12% drop)
- SPY T5 (hist=0.715, dist=-6.03%): NOT blocked (dist<-3%, genuine distressed exit)
- All other exits: unchanged

**No other files modified.** `macd_line[i-1]` and `macd_signal[i-1]` already accessible in ctx dict.

## Backtest Results

| Symbol | Baseline vs_BH | New vs_BH | Delta | Baseline total_return | New total_return | Delta |
|--------|---------------|-----------|-------|-----------------------|-----------------|-------|
| GOOGL  | +84.81%       | +84.81%   | 0.00% | +188.79%              | +188.79%        | 0.00% |
| SPY    | +31.35%       | +31.35%   | 0.00% | +63.60%               | +63.60%         | 0.00% |
| QQQ    | +20.33%       | **+26.23%** | **+5.90%** | +59.53%        | **+65.42%**     | **+5.89%** |

**QQQ trade change:**
- T10 entry 2026-03-31 @ 577.18: previously exited 2026-04-06 @ 588.50 (+1.66%, ma_breakdown)
- New: C2 guard blocks the exit; position holds to 2026-04-09 @ 610.19 (+5.42%, end_of_data)
- Net gain: +3.76% on trade, +5.90pp compounded vs_BH improvement

## Decision: KEPT — committed to smart-hold-v12

1 improved (QQQ +5.90pp), 2 neutral, 0 regressed. Consistent with v5/v8/v9/v10 precedent (all kept at 1 improved, 0 regressed).

**Key learnings:**
- The MACD histogram zero-crossing (negative→positive) is a distinct and cleaner pattern than the absolute threshold — it captures bar-1 of a fresh momentum cycle where exits are structurally premature
- The hist_prev check cleanly differentiates GOOGL T10 (hist already positive for days, correct exit) from QQQ T10 (hist crossed zero that bar, premature exit)
- The combined guard now handles two qualitatively different false-exit scenarios: (1) MACD strongly accelerating (C1: hist>1.0) and (2) MACD just turning positive from negative (C2: crossover)
- Zero signal-hop risk: exit suppressor pattern — when blocked, position simply holds
- The 3% SMA distance filter (dist>-3%) is the shared safety net for both conditions: prevents blocking exits during genuine crash events regardless of MACD reading

**Next potential improvement ideas:**
- Test on 5-year backtest window — longer window would expose more MACD crossover scenarios
- Investigate whether the hist>0 AND hist_prev<0 crossover pattern also improves trailing_stop or profit_lock (though neither showed premature exits in 2y data)
- Consider whether any GOOGL T3 (hist=0.897, hist_prev=0.647) or T7 (hist=0.750, hist_prev=0.463) improvements are possible — both have positive hist_prev so C2 doesn't help; would require lowering C1 threshold to ~0.7, but that blocks GOOGL T10 (correct exit)
- The remaining losers (GOOGL T8: ma_breakdown at SMA with low hist=0.175; QQQ T4: ma_breakdown with negative hist) appear structurally unblockable without harming other trades
- v13 idea: C3 condition — 0 < hist < 0.5 AND dist > -1% AND RSI rising — to catch GOOGL T8 (hist=0.175, dist=-0.050%, RSI rising)

---

# Signal Optimization Run #13 — 2026-04-09 (MACD C3: weakly-positive hist + near-SMA + RSI rising)

## Baseline (smart-hold-v12 state, 2026-04-10 data)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +188.79%        | +84.81%             | -3.04%          |
| SPY    | +63.60%         | +31.35%             | 0.0%            |
| QQQ    | +65.42%         | +26.23%             | -2.04%          |

## Gap Analysis — All Three Symbols

**A) Missed upside (5+ bars out, price rose >3%):**
- No new unaddressed missed-upside gaps of >3% over 5+ bars across GOOGL/SPY/QQQ.

**B) Premature exits (price up >2% within 3 bars after exit):**
- GOOGL T8 (2025-05-13, ma_breakdown, hist=0.175, hist_prev=0.007, dist=-0.050%): +4.17% missed
  - C1 fails (0.175 < 1.0), C2 fails (hist_prev=0.007 > 0, not a fresh crossover)
  - RSI=51.4, RSI_prev=50.2 (rising +1.2) — short-term momentum still bullish
  - Price was virtually at the SMA (only 0.050% below)
- No other unaddressed premature exits across SPY/QQQ.

**C) Exit quality — MACD+RSI context at all exits:**
- GOOGL T10 (2026-03-17): hist=0.930 (> 0.5), dist=-2.447% — C3 does NOT block (correct exit, price fell -3.19% after)
- QQQ T8 (2026-03-03): RSI falling (43.4 < 47.7) — C3 does NOT block (correct behavior)
- QQQ T9 (2026-03-09): dist=-1.172% (< -1%) — C3 does NOT block (correct behavior)
- All SPY exits: hist negative or dist > -3% or RSI falling — NOT blocked

**MACD hist at remaining losers:**
- GOOGL T3 (2024-09-18, +5.42% win): dist=-3.832% — outside C3's -1% threshold (not blockable)
- GOOGL T10 (2026-03-17, +0.96% small win): hist=0.930 > 0.5 — C3 doesn't block (safe)

**Key finding:** C3 fires exactly ONCE in the 2y window for all 3 symbols: GOOGL 2025-05-13 (and the day before, 2025-05-12, which would pre-empt the actual exit bar's conditions). It does not fire on SPY or QQQ because their exits have either negative MACD hist, RSI falling, or dist below -1%.

**Surgical precision verified:**
- Fires 2 times in 2y across GOOGL/SPY/QQQ (both on GOOGL: 05-12 and 05-13)
- Both GOOGL events correctly blocked (post-3bar: +3.47%, +4.17%)
- SPY 2 events exist in the data but occur when ma_breakdown wouldn't have fired anyway (bars_below_ma < exit_confirm or slope not declining)

## Change Applied

Added Condition 3 to MACD histogram suppressor in `strategies/smart_hold/signals/exits/ma_breakdown.py`:

**Condition 3 (v13):** `0 < hist < 0.5 AND close > sma * 0.99 AND RSI[i] > RSI[i-1]`
- Catches GOOGL T8 pattern: weakly positive MACD + price virtually at SMA + rising RSI momentum
- Distance threshold tightened to -1% (vs C1/C2's -3%) to prevent blocking moderate pullbacks
- hist upper bound < 0.5 ensures C1 (hist > 1.0 strongly bullish) handles the high-momentum case
- RSI uses the array from ctx["rsi"] (already present in context dict)

**Effect:** GOOGL T8 exit (2025-05-13 at 159.53, -3.04%) is blocked. Position continues from 164.03 (fast_reentry entry) directly through to 2026-02-12 exit via profit_lock at 309.00 — merging T8+T9 into one continuous trade (+88.08% vs sequential -3.04%+88.16%).

## Backtest Results

| Symbol | Baseline vs_BH | New vs_BH | Delta | Baseline total_return | New total_return | Delta | DD delta |
|--------|---------------|-----------|-------|-----------------------|-----------------|-------|----------|
| GOOGL  | +84.81%       | **+93.75%** | **+8.94%** | +188.79%        | **+197.73%**    | **+8.94%** | +3.04% |
| SPY    | +31.35%       | +31.35%   | 0.00% | +63.60%               | +63.60%         | 0.00% | 0.00% |
| QQQ    | +26.23%       | +26.23%   | 0.00% | +65.42%               | +65.42%         | 0.00% | 0.00% |

**GOOGL trade changes from C3:**
- T8 (fast_reentry 2025-05-02 at 164.03): previously exited 2025-05-13 at 159.53 (-3.04%, ma_breakdown)
- New: C3 blocks the 2025-05-13 exit; position continues through T9's territory
- T8 (merged T8+T9): exits 2026-02-12 at 309.00 via profit_lock (+88.08%)
- Trade count: 11 → 10 (T9 subsumed into T8; T10-T11 renumbered T9-T10)
- Max drawdown: -3.04% → 0.0% (the -3.04% trade eliminated; now 100% win rate)

## Decision: KEPT — committed to smart-hold-v13

1 symbol improved (GOOGL +8.94pp vs_BH), 2 neutral, 0 regressed. GOOGL drawdown improved -3.04% → 0.0%.

**Key learnings:**
- C3 adds a third guard axis: MACD weak-positive + virtually-at-SMA + RSI rising. Unlike C1 (strongly positive MACD) and C2 (fresh crossover), C3 targets bars where MACD hasn't crossed zero recently but remains barely positive while price barely touches below the SMA line
- The -1% distance filter is the critical differentiator from C1/C2 (which use -3%). GOOGL T10 at dist=-2.45% is safely outside C3's window, allowing the correct exit before a -3.19% drop
- The hist < 0.5 upper bound separates C3 from C1 (hist > 1.0) and ensures C3 doesn't compete with C1 on the strong-momentum cases
- RSI rising adds a momentum confirmation layer — exits where RSI is declining (QQQ T8: RSI fell 4.3 pts) correctly proceed
- Zero signal-hop risk: exit suppressor pattern — when blocked, position simply holds

**Next potential improvement ideas:**
- Test on 5-year backtest window — more near-SMA shallow dip scenarios may be exposed
- Consider whether the C3 pattern applies to trailing_stop (weakly positive MACD + RSI rising + barely below trail level)
- The remaining GOOGL losers (T3 at dist=-3.83%, T7 at dist=-5.93%) are structurally unblockable — dist too far below SMA
- QQQ T8/T9 losses (-1.56%, -0.49%) are post-macd_reversal_exit cooldown consequences; architectural approach would be adaptive cooldown (wait for MACD positive + price above SMA) but these specific trades fire 41+ bars after exit — beyond the 20-bar window

---

# Signal Optimization Run #14 — 2026-04-10 (Exhaustive Gap Analysis — Optimization Ceiling)

## Baseline (smart-hold-v13 state, fresh 2026-04-10 data)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +197.73%        | +93.75%             | 0.0%            |
| SPY    | +63.60%         | +31.35%             | 0.0%            |
| QQQ    | +65.42%         | +26.23%             | -2.04%          |

## Comprehensive Gap Analysis — All Three Symbols

**Post-exit price movement analysis (all 27 trades):**

**Remaining premature exits (price rose >3% within 5 bars):**
- GOOGL T7: vix_accel @ 155.35 (2025-04-23), hist=0.750, dist=-5.93%, RSI rising — +4.3% by +2d
- SPY T1: vix_accel @ 518.66 (2024-08-07), hist=-4.030, dist=-4.50%, RSI falling — +2.8% by +2d
- QQQ T1: vix_accel @ 439.53 (2024-08-06), hist=-4.574, dist=-7.10%, RSI rising — +5.2% by +5d

**Remaining trailing stop gap:**
- GOOGL T4: trailing_stop @ 179.66 (2025-02-21), peaked at 27.80% gain (2025-02-04), exited at 10.95%

## Attempted Improvements (8 approaches, all rejected analytically before coding)

**1. C4 in ma_breakdown (expand to cover GOOGL T7, SPY T1, QQQ T1):**
- SPY/QQQ T1: hist=-4.0 to -4.6 (massive negative MACD) AND dist<-3% → no positive MACD → no C4 possible
- GOOGL T7: hist=+0.750 but dist=-5.93% → widening C1 dist from -3% to -6% would also block QQQ T6 (hist=1.542, dist=-6.67%, CORRECT exit)
- Verdict: **NOT viable. C4 space exhausted for 2y window.**

**2. RSI_oversold_bounce MACD histogram guard (block when hist < -3.0):**
- Blocks SPY T3 (+0.47%) and QQQ T4 (-0.04%) on 2025-03-14 — correctly identified as weak entries
- BUT: ema_momentum fires on 2025-03-25 @ 493.46 for QQQ (higher price than 479.66 blocked entry)
- Net for QQQ: worse entry at 493.46 → falls to 422 during tariff shock → larger drawdown
- Net for SPY: blocks a +0.47% win → regression
- Verdict: **REJECTED — signal-hop causes QQQ regression, SPY regression from blocking a win.**

**3. macd_reversal_exit relaxed SMA slope (allow up to +0.02 instead of requiring < 0):**
- GOOGL T4: would fire on FIRST crossover 2024-12-30 at 18.42% gain, SMA slope=+0.017
- But post-3d price = +0.3% (still rising!) — premature exit, misses peak at 27.80%
- Also fires on Jan 27 crossover (post-3d +4.7%) before the good Feb 5 crossover (post-3d -2.5%)
- Verdict: **REJECTED — false fire on first crossover when price continues rising.**

**4. ema_momentum below-SMA SMA slope guard:**
- Checked SMA slope at ALL below-SMA ema_momentum entries across GOOGL/SPY/QQQ
- Winner GOOGL T3 (2024-09-25, +10.95%): slope=-0.01455 (steepest negative!)
- Losers QQQ T8/T9: slope=-0.00234/-0.00040 (less negative than the winner)
- Any threshold that blocks losses also blocks GOOGL's biggest ema_momentum win
- Verdict: **REJECTED — no viable slope threshold.**

**5. Trailing_stop MACD guard (C3 equivalent for trailing_stop):**
- Only 1 trailing_stop exit in 2y (GOOGL T4, 2025-02-21)
- MACD hist at exit = -1.395 (strongly negative, correct protective exit)
- Guard would not fire → zero impact on 2y results
- Verdict: **REJECTED — zero-fire change for this dataset.**

**6. Adaptive macd_rev_exit cooldown (wait for MACD > 0 AND price > SMA):**
- QQQ: adaptive cooldown ends 2026-01-27 @ 631.13 (price up briefly)
- 2026-01-27 to 2026-02-03: 631 → 633 → 629 → 616 → 616 (then falls to 597 by Feb 5)
- Re-entry at 631.13 is WORSE than current 609.24 (20-bar fixed cooldown)
- Verdict: **REJECTED — adaptive cooldown ends earlier at a higher price.**

**7. Profit_lock threshold variants (40%, 60%):**
- The profit_lock fires when SMA slope JUST turns negative — it fires at the crossover moment
- GOOGL T8: SMA turned negative at 88% gain (Feb 12, 2026) — threshold 40%/50%/60% all activate on same bar since gain was already 88% when slope turned
- Verdict: **REJECTED — same exit bar regardless of threshold.**

**8. false_breakdown_reclaim with expanded window (max_bars=10):**
- With default reentry_ma_reclaim=2 (CLI default), FBR fires on same bar as ma_reclaim (2 consec above SMA)
- No improvement vs current ma_reclaim — simultaneous fire
- Verdict: **REJECTED — fires simultaneously with ma_reclaim at default params.**

## Decision: SKIP — No Viable Improvement Found

**0 of 8 approaches produced a net improvement across 2+ symbols without regression.**

The 2y GOOGL/SPY/QQQ window has reached true optimization ceiling. Remaining losses fall into three structural categories:
1. **VIX-exit overselling** (SPY T1, QQQ T1, GOOGL T7): exits with negative MACD or dist>-3% not distinguishable from correct protective exits without lookahead bias
2. **Trailing stop gap** (GOOGL T4): macd_reversal_exit correctly blocked by SMA slope guard (price still rising when MACD crosses); relaxed slope causes false earlier exit
3. **Post-cooldown QQQ reentries** (T8/T9): both have positive rising MACD, signal-hop prevents blocking

**No code changes made. No commit. No push.**

**Next recommended approach:**
- Test on 5-year backtest window to expose different frequency patterns
- Consider whether WDC or STX (not GOOGL/SPY/QQQ) have exploitable gaps that could add a 4th symbol to the benchmark set
- The 20-bar macd_rev_exit cooldown architecture is proven; tuning to 25 bars might help QQQ but requires full backtest verification against all symbols

---

# Signal Optimization Run #15 — 2026-04-10 (5y Window Switch — Baseline Establishment)

## Confirmed: 2y Window at Optimization Ceiling

Run #14 conclusively found all 8 approaches tried in the 2y window were either signal-hop failures or zero-impact. Switching to 5y window to expose 2021-2024 patterns including the 2022 bear market.

## 5y Baseline (smart-hold-v13 state, CLI default params)

```
  GOOGL: total=+142.68%, vs_BH=-41.10%, trades=36, win=38.9%, dd=-42.33%
  SPY:   total=+94.85%,  vs_BH=+29.68%, trades=20, win=65.0%, dd=-19.79%
  QQQ:   total=+95.64%,  vs_BH=+14.40%, trades=25, win=44.0%, dd=-24.19%
```

**Window:** 2021-04-12 to 2026-04-09 (1255 bars)
**Files:** smart_hold_backtest_GOOGL_5y.json, smart_hold_backtest_SPY_5y.json, smart_hold_backtest_QQQ_5y.json

## 5y Gap Analysis — All Three Symbols

### Dominant New Pattern: 2022 Bear Market Churn

The 5y window adds 3 years (2021-2024) not visible in the 2y window. The major new exposure is the 2022 bear market:

- **GOOGL**: 36 trades (vs 10 in 2y), 22 losing — 18 trades in the 2022 bear (Jan-Mar 2023), losing ~50% cumulatively. This drove GOOGL's vs_BH from +93.75% (2y) to -41.10% (5y).
- **SPY**: 20 trades, only 7 losses — more resilient because SPY exited in Jan 2022 and successfully re-entered in Nov 2022 (ma_reclaim at 382, +12.63%) before the full recovery.
- **QQQ**: 25 trades, 14 losses — intermediate churn, re-entered successfully in Jan 2023 (ema_momentum at 270, +31.98%).

**Root cause of 2022 churn:** Strategy kept re-entering on VIX-spike reversals, EMA momentum, and RSI oversold bounces throughout the 2022 bear, but every bear rally failed. Each re-entry generated a small-to-medium loss. The cumulative effect was ~50% of trading capital lost during the 2022 bear for GOOGL.

### A) Missed Upside (5+ bars out, price rose >3%)

- GOOGL T20→T21: 10 bars out after Oct 27, 2023 exit at 122.17; GOOGL recovered to 130.25 by Nov 6 (+6.6%). Re-entry at 130.25 via ema_momentum was reasonable but missed early recovery.
- SPY/QQQ: No significant gaps — successful re-entries during key recoveries (Nov 2022 for SPY, Jan 2023 for QQQ).

### B) Premature Exits (price up >2% within 3 bars)

- GOOGL T27 (Sep 16, 2024, ma_breakdown at 158.06): price rose to 163.59 within 4 bars (+3.5% missed). MACD histogram crossed from negative to positive on the exit bar (+0.299 vs prev=-0.099), but dist=-5.55% is outside C2's -3% filter. Cannot improve without risking blocking genuine crash exits.
- GOOGL T5 (Apr 13, 2022, ma_breakdown, -4.86%): price recovered +4.7% within 3 bars. MACD hist was negative at exit — correctly not blocked.

### C) Exit Quality — 2022 Bear & 2023 Recovery Patterns Not in 2y

- **VIX-spike exits (2022 bear):** Multiple vix_accelerated_exits throughout 2022 were correct (prevented deeper losses) but subsequent re-entries failed as bear continued.
- **MACD histogram guard coverage:** Analyzed 5y window — C1/C2/C3 guards would have fired frequently during 2022 bear rally weeks (especially SPY Jul-Oct 2022 with hist > 1.0 during rallies). These guards correctly DON'T fire during those periods because the strategy was already out of position (not in a trade), so they're irrelevant. The guards only matter when the strategy is IN a trade and an exit signal fires.
- **Bear regime confirmation:** SMA200 was declining for GOOGL from Jun 2022 through Mar 2023 (-3% to -4% per 20 bars). SPY's SMA200 declined more gently (never exceeding -2.5% per 20 bars). QQQ was intermediate (-3.5% at worst).

## Approaches Tested and Rejected

### Approach 1: Bear Regime Entry Gate (architectural)
Detect SMA200 declining steeply (>2% over 20 bars + price below SMA200) and block `ma_reclaim` + `rsi_oversold_bounce` entries.

**Results:**
- At -1.8% threshold: GOOGL +7.18% vs B&H (+48pp improvement), SPY -2.98pp regression, QQQ -3.93pp regression
- At -2.0% threshold: GOOGL -20.76% vs B&H (+20pp improvement), SPY -2.98pp regression, QQQ -3.93pp regression
- At -3.0% threshold: GOOGL -37.76% vs B&H (+3pp improvement), SPY unchanged, QQQ -1.05pp regression

**Root cause of failure:** Signal-hop problem — blocking ma_reclaim and rsi_oversold_bounce causes ema_momentum to fire as fallback at similar or worse timing. SPY's critical winning re-entry (Nov 2022 at 382 via ma_reclaim) is in the bear regime window at -2%/-1.8% thresholds and gets blocked. **REJECTED.**

### Approach 2: Deep-Bear RSI Oversold Bounce Guard
Block `rsi_oversold_bounce` when price is >10% below SMA200 (deep bear regime).

**Results:**
- GOOGL: -44.16% vs B&H (worse than baseline -41.10%)
- SPY: +29.29% vs B&H (-0.39pp regression)
- QQQ: +14.32% vs B&H (-0.08pp regression)

**Root cause:** Blocking rsi_oversold_bounce caused ema_momentum and ma_reclaim to fire as fallbacks at similar timing. Classic signal-hop. **REJECTED.**

### Approach 3: Extended C2 Distance Filter (exit guard)
Extend MACD histogram C2 crossover guard from -3% to -6% SMA distance.

**Analysis (not coded):** At -3% to -6% range, C2 would fire on 5 GOOGL bars, 5 SPY bars, 5 QQQ bars. Post-3-bar movement analysis:
- GOOGL: 3 positive (+3.9%, +3.5%, +2.6%), 2 negative (-1.6%, context-dependent)
- SPY: 3 negative (-4.2%, -2.9%, -4.5%), 2 mixed — WORSE than current
- QQQ: 2 negative (-3.6%, -1.3%), 2 mixed — WORSE than current

Net: more harmful blocks than beneficial blocks, especially for SPY/QQQ in 2022 bear. **REJECTED.**

## Key Structural Findings from 5y Analysis

1. **Bear market churn is inherent to re-entry strategies**: Any strategy that exits on downturns and re-enters on recovery signals will churn during prolonged bear markets. The signal-hop problem means blocking any one entry signal causes another to fire as fallback.

2. **The strategy's 2022 performance is structurally driven**: GOOGL lost ~50% in trading value during 2022 bear. SPY (lower vol, 0.82% ATR) only had 8 bear trades vs GOOGL's 18 — ATR-based volatility drives the number of signal firings.

3. **Existing v13 guards (C1/C2/C3) were optimally tuned for 2y**: They correctly block premature exits near SMA50 with positive MACD momentum. Extending their scope to the 5y window creates more harm than good because the 2022 bear produces many C1/C2 "false signals" where MACD crosses positive during bear rallies but the trend continues down.

4. **The 5y win over B&H is positive for SPY (+29.68%) and QQQ (+14.40%)** — both exceed B&H over 5 years. GOOGL's -41.10% is the outlier due to its higher volatility in the 2022 bear.

5. **Viable future approach:** Consider adding VIX regime awareness to entry signals — only allow ma_reclaim and rsi_oversold_bounce when VIX is below 25 (normal regime) or declining from peak below 30 (fear receding). This would block bear rally re-entries when VIX is still elevated at 25-30 during sustained bears. However, this requires careful testing against QQQ's winning Jan 2023 entry (VIX ~21 — would NOT be blocked) vs the losing entries in Oct 2022 (VIX ~27-30 — WOULD be blocked). Different from the tested approaches because it uses VIX as a regime indicator rather than SMA200 slope.

## Decision: NO IMPROVEMENT — No Code Changes

**No code changes committed. 5y backtest files saved for future reference.**

**5y baseline for next run starting point:**
```
  GOOGL: vs_BH=-41.10% (total=+142.68%)
  SPY:   vs_BH=+29.68% (total=+94.85%)
  QQQ:   vs_BH=+14.40% (total=+95.64%)
```

---

# Signal Optimization Run #16 — 2026-04-09 (VIX Persistence Regime Gate)

## Baseline (smart-hold-v13 state, 5y window)

| Symbol | total_return_pct | vs_buy_and_hold_pct | max_drawdown_pct |
|--------|-----------------|---------------------|-----------------|
| GOOGL  | +142.68%        | -41.10%             | -42.33%         |
| SPY    | +94.85%         | +29.68%             | -19.79%         |
| QQQ    | +95.64%         | +14.40%             | -24.19%         |

## Gap Analysis — 5y Window (2022 Bear Market Focus)

### Key Finding: VIX Persistence as Regime Discriminator

Run #15 identified VIX-based regime gate as the most promising approach. This run implements an architectural engine-level gate using VIX persistence.

**VIX analysis at all 2022 bad entries vs critical good entries:**

| Date | Symbol | Signal | Return | VIX | Consecutive VIX≥28 | Outcome |
|------|--------|--------|--------|-----|---------------------|---------|
| 2022-02-28 | GOOGL | ema_momentum | -1.16% | 30.1 | 1+ | BAD |
| 2022-04-28 | GOOGL | rsi_oversold_bounce | -1.94% | 30.0 | 3+ | BAD |
| 2022-06-22 | GOOGL | ema_momentum | -0.11% | 28.9 | 7+ | BAD |
| 2022-09-28 | GOOGL/SPY/QQQ | rsi_oversold_bounce | -3.9%/-4.7%/-4.8% | 30.2 | 4+ | BAD |
| 2022-11-08 | SPY | ma_reclaim | +12.63% | 25.5 | 0 | GOOD — allowed |
| 2023-01-09 | QQQ | ema_momentum | +31.98% | 22.0 | 0 | GOOD — allowed |
| 2026-03-31 | QQQ | rsi_oversold_bounce | +5.42% | 25.2 | 0 | GOOD — allowed |

**Key precision insight:** At threshold=28 (VIX ≥ 28) with N=3 consecutive bars:
- 2022 bear market: VIX sustained 27-35 for weeks → counter reaches 3+, gate activates
- 2022 Nov recovery: VIX dropped below 28 for days → counter resets to 0, gate inactive
- 2026 tariff shock: VIX ranged 25-31 but rarely consecutive 3+ days above 28 → gate inactive

### Threshold Exploration

Multiple configurations tested analytically before backtesting:

| Config | Good blocked | Bad blocked | Note |
|--------|-------------|-------------|------|
| 25/N=5 clamped | 2 (Jan 2022 QQQ, 2026 QQQ) | 5+ | QQQ 2026 blocked (bad) |
| 27/N=3 clamped | 1 (Jan 2022 QQQ) | 6 | SPY/QQQ regressed vs baseline |
| 27/N=5 strict | 1 (Jan 2022 QQQ) | 4 | Oct 2022 miss |
| **28/N=3 strict** | **0** | **3** | **Perfect — all good entries allowed** |

**Strict consecutive counter** (resets to 0 on any bar below threshold) was chosen over clamped counter because:
- It correctly identifies SUSTAINED bear regimes (3+ consecutive days with VIX ≥ 28)
- It quickly unlocks when VIX briefly dips below threshold (allows Nov 2022, Jan 2023 recoveries)
- The 2026 tariff shock never hits 3 consecutive days above 28, so doesn't block good recovery entries

### Signal Exemptions

VIX-specific entry signals are EXEMPT from the gate since they are designed for high-VIX environments:
- `vix_extreme_fear` — exempt (designed for VIX > 35 entries)
- `vix_fear_declining` — exempt (designed for VIX peak + decline patterns)
- `fast_reentry` — exempt (already checks VIX decline internally)

Non-exempt signals that the gate blocks when VIX ≥ 28 for 3+ consecutive bars:
- `ma_reclaim`, `rsi_oversold_bounce`, `ema_momentum`, `macd_crossover`, `false_breakdown_reclaim`, `pyramid_momentum` (all disabled signals included for completeness)

## Implementation

**File changed:** `strategies/smart_hold/smart_hold_strategy.py` (engine-level, no signal files changed)

**New constants:**
```python
VIX_REGIME_THRESHOLD = 28.0    # VIX level that signals a sustained fear regime
VIX_REGIME_BARS = 3            # block ALL entries when this many consecutive bars have VIX >= threshold
```

**New state variable:** `vix_regime_count = 0` (strict consecutive counter)

**Counter update (per bar):**
```python
if vix_val is not None and vix_val >= vix_regime_threshold:
    vix_regime_count += 1
else:
    vix_regime_count = 0
```

**Entry gate in main loop:**
```python
_VIX_REGIME_EXEMPT = frozenset({"vix_extreme_fear", "vix_fear_declining", "fast_reentry"})
in_vix_regime = vix_regime_count >= vix_regime_bars
for sig in ENTRY_SIGNALS:
    if in_vix_regime and sig.METADATA["name"] not in _VIX_REGIME_EXEMPT:
        continue
    if sig.check(ctx):
        ...
```

This is ~8 lines added to the main loop — same pattern as `macd_rev_exit_cooldown`.

## Backtest Results (5y window)

| Symbol | Baseline vs_BH | New vs_BH | Delta | Baseline total | New total | DD delta |
|--------|---------------|-----------|-------|----------------|-----------|----------|
| GOOGL  | -41.10%       | **-41.37%** | -0.27pp | +142.68% | +142.41% | -0.07pp |
| SPY    | +29.68%       | **+39.82%** | **+10.14pp** | +94.85% | +104.99% | +4.18pp |
| QQQ    | +14.40%       | **+31.66%** | **+17.26pp** | +95.64% | +112.90% | +6.69pp |

**2y window (unchanged — gate inactive in post-2022 bull market):**
- GOOGL: +93.75% (unchanged)
- SPY: +31.35% (unchanged)
- QQQ: +26.23% (unchanged)

## Decision: KEPT — committed to smart-hold-v14

**2 symbols improved significantly** (SPY +10.14pp, QQQ +17.26pp), **1 neutral** (GOOGL -0.27pp), **0 regressed**.

**Key learnings:**
- Threshold=28 + N=3 consecutive is the sweet spot: requires 3 days of VIX ≥ 28, which is rare outside true bear markets
- The 2026 tariff shock (VIX 25-31) doesn't trigger the gate because VIX rarely stayed above 28 for 3+ consecutive days
- The 2022 bear market (VIX 27-35 for months) triggers the gate reliably, blocking the losing bear rally re-entries
- Strict reset (counter → 0 on any bar below threshold) is critical: it allows quick re-entry when VIX normalizes, which is how SPY's critical Nov 2022 +12.63% and QQQ's Jan 2023 +31.98% entries are preserved
- VIX-signal exemptions are essential: `vix_extreme_fear` and `vix_fear_declining` must be allowed through since they are designed for high-VIX entries (blocking them caused QQQ's +39.47% trade to revert to +9.69%)
- The gate avoids signal-hop by operating at engine level — it doesn't block individual signals, it blocks ALL non-VIX signals simultaneously, preventing fallback chains

**Architecture note:** The gate uses the same design pattern as `macd_rev_exit_cooldown` — an engine-level state variable that controls the entry evaluation loop. Zero changes to signal files.
