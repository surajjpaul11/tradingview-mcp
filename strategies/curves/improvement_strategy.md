# Curved Channel Strategy — Improvement Process

Systematic approach to iterating on the curved channel strategy. Designed to be run in a loop: tweak, backtest, record, evaluate, repeat.

## Process

```
┌─────────────────┐
│ 1. Identify Issue│ ← Review chart, trade log, missed signals
└────────┬────────┘
         v
┌─────────────────┐
│ 2. Propose Tweak │ ← Single variable change (entry, exit, sizing, filters)
└────────┬────────┘
         v
┌─────────────────┐
│ 3. Backtest      │ ← Run across all test symbols (SPY, BTC-USD, QQQ)
└────────┬────────┘
         v
┌─────────────────┐
│ 4. Record Results│ ← Append to improvement_log.md with delta from previous
└────────┬────────┘
         v
┌─────────────────┐
│ 5. Evaluate      │ ← Keep if net positive, revert if net negative
└────────┬────────┘
         v
┌─────────────────┐
│ 6. Next Issue    │ ← Back to step 1
└─────────────────┘
```

## Rules

1. **One change at a time.** Never combine two tweaks in a single version — makes it impossible to attribute improvement.
2. **Test across all symbols.** A change that helps SPY but destroys BTC-USD is not an improvement.
3. **Record everything.** Even failed experiments are valuable — they eliminate search space.
4. **Version numbers are sequential.** v0, v1, v2... Each has exactly one change from the previous.
5. **Revert bad changes.** If a version is net negative across symbols, revert and try a different approach.

## How to Run a Backtest Cycle

```bash
# Run all three test symbols
python3 strategies/curves/curved_channel_strategy.py --symbol SPY --period 2y --chart
python3 strategies/curves/curved_channel_strategy.py --symbol BTC-USD --period 2y --chart
python3 strategies/curves/curved_channel_strategy.py --symbol QQQ --period 2y --chart
```

## How to Record Results

Append a new section to `improvement_log.md` with this template:

```markdown
## vN — Short description (YYYY-MM-DD)

**Change:** One sentence describing what was modified and why.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | | | | | | | |
| BTC-USD | | | | | | | |
| QQQ | | | | | | | |

**Delta from v(N-1):**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | | | |
| BTC-USD | | | |
| QQQ | | | |

**Verdict:** Keep / Revert. Reason.
```

## Improvement Ideas Backlog

Potential tweaks to try, ordered by expected impact:

### Entry
- [ ] Remove bullish bar requirement (close > open) — enter on any bar inside channel
- [ ] Add volume confirmation — only enter when volume > MA(20)
- [ ] Prefer entries near lower boundary — weight position size by proximity to support

### Exit
- [ ] Add trailing stop inside channel (e.g., 2x ATR from high)
- [ ] Partial profit taking at upper boundary (sell 50%, hold rest)
- [ ] Time-based exit — close if no channel break after N bars

### Sizing
- [ ] Scale short size by channel break magnitude (bigger break = larger short)
- [ ] Increase short from 25% to 50% for stronger breaks (close > 2% below support)
- [ ] Pyramid into longs — add to position on each bounce off lower boundary

### Filters
- [ ] Only trade ascending channels with positive slope (rising support)
- [ ] Require minimum channel width (resistance - support > X%)
- [ ] Add trend filter — only long when price > SMA(200)

### Channel Detection
- [ ] Increase max_pivots from 20 to 30 for more robust channel fits
- [ ] Try degree=3 (cubic) for better curve fit on longer channels
- [ ] Lower min_touch from 3 to 2 for earlier channel detection

## Files

| File | Purpose |
|------|---------|
| `curved_channel_strategy.py` | Strategy implementation |
| `curved_channel.pine` | Pine Script equivalent (TradingView) |
| `improvement_log.md` | Running backtest results log |
| `improvement_strategy.md` | This file — process documentation |
| `curved_channel_chart_*.html` | Visual backtest charts |
| `curved_channel_backtest_*.json` | Raw backtest results |
