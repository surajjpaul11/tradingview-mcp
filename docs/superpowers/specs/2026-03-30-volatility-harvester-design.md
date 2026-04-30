# Volatility Harvester Strategy — Design Spec

**Date:** 2026-03-30
**Status:** Approved
**Type:** New strategy (standalone Python backtester)
**Gap filled:** Choppy/volatile markets (scored 1/5 in strategy_map.md)

---

## Problem

Every strategy in the project bleeds money in choppy/volatile markets. Buy & Protect survives (stays invested), Bollinger barely copes, but nothing is designed to actually profit from chop. The strategy map scores this condition 1/5 — our worst gap.

## Solution

A mean-reversion strategy that profits from short-term overreactions in directionless markets. Buys panic dips and shorts sharp rips, betting that extreme moves in choppy markets snap back to the mean. Uses a Kaufman Efficiency Ratio gate to sit in cash during trending markets where mean-reversion fails.

## Design

### Regime Gate

The strategy only opens new positions when the market is classified as choppy:

```
ER = |price[i] - price[i - er_period]| / sum(|price[j] - price[j-1]| for j in range)

ER < 0.25  →  choppy  →  ACTIVE (open new positions)
ER >= 0.25 →  trending →  INACTIVE (cash only, no new positions)
```

- Recalculated every bar
- If already in a position when ER flips above 0.25, the position's own exit rules handle the close — no forced exit from regime change
- ER period: 50 bars (same as VWMA 17)

### Entry Signals (ATR Z-Score + Volume Confirmation)

**Long entry (buy panic dip):**
1. Price deviation: `SMA(20) - close >= 3.0 * ATR(14)` — price has dropped 3+ normal daily ranges below its mean
2. Volume confirmation: `volume >= 1.5 * volume_MA(20)` — elevated volume confirms panic selling
3. Regime gate: ER(50) < 0.25
4. No existing position open

**Short entry (sell sharp rip):**
1. Price deviation: `close - SMA(20) >= 3.0 * ATR(14)` — price has risen 3+ normal daily ranges above its mean
2. Volume confirmation: `volume >= 1.5 * volume_MA(20)` — elevated volume confirms euphoric buying
3. Regime gate: ER(50) < 0.25
4. No existing position open

Volume confirmation is on by default. Disabled with `--no-volume-filter` for assets with unreliable volume data. When disabled, only the ATR deviation check is required for entry.

### Exit Rules (Triple Layer)

Three exit mechanisms checked every bar. First to fire closes the position:

| Priority | Exit Type | Long Condition | Short Condition | Rationale |
|----------|-----------|---------------|-----------------|-----------|
| 1 | Mean reversion | Close >= SMA(20) | Close <= SMA(20) | Thesis complete — price reverted to mean |
| 2 | Time exit | Bars held >= 15 | Bars held >= 15 | Thesis expired — no reversion, close at market |
| 3 | Stop loss | Close <= entry - 2.0 * ATR(14) | Close >= entry + 2.0 * ATR(14) | Thesis wrong — cut losses |

The ATR value used for stop loss is the ATR at entry time (frozen), not recalculated. This prevents the stop from widening during a volatility spike.

### Parameters

| Parameter | Default | CLI Flag | Description |
|-----------|---------|----------|-------------|
| `atr_period` | 14 | `--atr-period` | ATR calculation period |
| `sma_period` | 20 | `--sma-period` | Mean for deviation and reversion target |
| `deviation_mult` | 3.0 | `--deviation-mult` | ATR multiples from SMA to trigger entry |
| `stop_mult` | 2.0 | `--stop-mult` | ATR multiples for stop loss (from entry) |
| `max_hold_bars` | 15 | `--max-hold-bars` | Time exit cap |
| `vol_ma_period` | 20 | `--vol-ma-period` | Volume MA period for spike detection |
| `vol_spike_mult` | 1.5 | `--vol-spike-mult` | Volume >= this * vol MA to confirm |
| `er_period` | 50 | `--er-period` | Kaufman ER lookback |
| `er_threshold` | 0.25 | `--er-threshold` | Below = choppy (trade), above = trending (cash) |
| `volume_filter` | true | `--no-volume-filter` | Disable volume confirmation |
| `long_only` | false | `--long-only` | Disable short positions |
| `interval` | 1h | `--interval` | Candle size |
| `period` | 2y | `--period` | Data lookback |

### File Structure

```
strategies/
  volatility_harvester_strategy.py    # Standalone Python backtester with CLI
  compare_volatility_harvester.py     # vs B&H comparison across 23 symbols
```

Pine Script deferred (TBD).

### Code Structure (within volatility_harvester_strategy.py)

Following project conventions (pure stdlib, Yahoo Finance, same output format):

1. **Indicator functions:** `calc_atr()`, `calc_sma()`, `calc_er()`, `calc_volume_ma()` — reuse patterns from existing strategies
2. **`run_volatility_harvester(candles, **params) -> list[dict]`** — main engine, returns list of trade dicts
3. **`apply_costs(trades, commission, slippage) -> list[dict]`** — commission + slippage simulation
4. **`calc_metrics(trades, capital, interval) -> dict`** — performance metrics including exit breakdown by type
5. **`run_backtest(symbol, period, interval, **params) -> dict`** — fetch data + run + metrics
6. **`main()`** — CLI entry point with argparse

### Trade Dict Format

```python
{
    "entry_date": "2025-01-15 14:00",
    "exit_date": "2025-01-17 10:00",
    "entry_price": 580.50,
    "exit_price": 590.20,
    "side": "long",          # or "short"
    "exit_reason": "mean_reversion",  # or "time_exit" or "stop_loss"
    "bars_held": 12,
    "return_pct": 1.67
}
```

### Output

Console output matches existing strategies:
- Header with strategy name, parameters, symbol
- Summary metrics: total return, B&H comparison, win rate, profit factor, Sharpe, max drawdown
- Exit breakdown: mean reversion / time exit / stop loss counts
- Trade log with entry/exit dates, prices, return %, exit reason
- JSON file saved for programmatic use

### Metrics

Standard set (same as all strategies) plus:
- `mean_reversion_exits`: count of trades closed by reversion to SMA
- `time_exits`: count of trades closed by time expiry
- `stop_loss_exits`: count of trades closed by stop loss
- `regime_active_pct`: percentage of bars where ER < threshold (strategy was active)

### What This Strategy Does NOT Do

- Does not trade in trending markets (ER gate prevents it)
- Does not use trailing stops (positions are short-lived, max 20 bars)
- Does not scale in or pyramid positions (one position at a time)
- Does not use different parameters for longs vs shorts (symmetric by design)

### Expected Behavior

- **Choppy markets (BTC summer 2024, meme stocks):** Frequent trades, high win rate (~60-70%), small gains per trade
- **Trending markets (SPY 2023-2024 rally):** Sits in cash almost entirely. Few or zero trades. Near-zero return.
- **Crash events:** May catch the initial snap-back from a panic dip, but stop loss limits damage if the crash continues
- **Ideal asset profile:** High-volume assets that oscillate — crypto, volatile ETFs (VXX), momentum stocks in consolidation
