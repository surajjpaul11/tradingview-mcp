# EMA 21 Crossover Strategy — Design Spec

**Date:** 2026-04-01
**Status:** Approved
**Type:** Built-in strategy (backtest_service.py)
**Strategy key:** `ema21`

## Overview

Simple trend-following strategy that trades price crossovers of the 21-period EMA. Supports both long and short positions. Default exits use crossover flips; optional ATR-based stop loss and take profit can be enabled via flag.

## Entry Logic

- **Long entry:** Previous bar's close was below EMA(21), current bar's close is above EMA(21)
- **Short entry:** Previous bar's close was above EMA(21), current bar's close is below EMA(21)
- Positions flip — a long entry signal closes any open short (and vice versa)

## Exit Logic

### Default: Simple Crossover

- Long exits when price crosses below EMA(21) — this same signal opens a short
- Short exits when price crosses above EMA(21) — this same signal opens a long
- No separate stop loss or take profit

### Optional: ATR Stops (use_atr_exits=True)

- On entry, compute ATR(14) and set:
  - **Stop loss:** entry_price -/+ (atr_sl_mult * ATR) depending on side
  - **Take profit:** entry_price +/- (atr_tp_mult * ATR) depending on side
- ATR exits close the position WITHOUT flipping to the opposite side
- If ATR doesn't trigger, the crossover flip still works as a fallback exit

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ema_period` | 21 | EMA lookback period |
| `use_atr_exits` | False | Enable ATR-based stop loss and take profit |
| `atr_period` | 14 | ATR lookback period (only used when use_atr_exits=True) |
| `atr_sl_mult` | 1.5 | ATR stop loss multiplier |
| `atr_tp_mult` | 2.0 | ATR take profit multiplier |

## Trade Dict Structure

```python
{
    "entry_date": "2024-01-15",
    "entry_price": 150.25,
    "exit_date": "2024-01-22",
    "exit_price": 148.50,
    "strategy": "ema21",
    "side": "long"  # or "short" — required for _apply_costs()
}
```

## Files to Change

1. **`src/tradingview_mcp/core/services/backtest_service.py`**
   - Add `_run_ema21()` function
   - Add `"ema21"` to `_STRATEGY_LABELS`
   - Add `"ema21"` to `_STRATEGY_MAP`

2. **`src/tradingview_mcp/server.py`**
   - Add `'ema21'` to `backtest_strategy()` docstring strategy list

3. **`CLAUDE.md`**
   - Add ema21 row to the strategy table

## Dependencies

- `calc_ema()` — already exists in `indicators_calc.py`
- `calc_atr()` — already exists in `indicators_calc.py` (used only when ATR exits enabled)
- No new indicators or external dependencies needed
