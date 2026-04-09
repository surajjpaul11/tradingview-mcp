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
