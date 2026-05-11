# Curved Channel Backtest Report (SNDK, PLTR, WDC)

Generated from latest backtest JSON outputs in `strategies/curves/`.


## Executive Summary
- **SNDK**: Strategy **+832.15%** vs Buy & Hold **+4239.83%** (delta **-3407.68%**)
- **PLTR**: Strategy **+63.59%** vs Buy & Hold **+551.84%** (delta **-488.25%**)
- **WDC**: Strategy **+241.33%** vs Buy & Hold **+780.90%** (delta **-539.57%**)

## Detailed Results
### SNDK
- Period: `2025-02-13 -> 2026-05-08` (310 bars)
- Final Capital: `$93,214.90` (start: $10,000)
- Strategy Return: **+832.15%**
- Buy & Hold Return: **+4239.83%**
- Relative vs B&H: **-3407.68%**
- Total Trades: 7 (Long: 7, Short: 0)
- Win Rate: 71.4%
- Profit Factor: 133.94
- Sharpe Ratio: 12.64
- Max Drawdown: -2.46%

### PLTR
- Period: `2024-05-09 -> 2026-05-08` (501 bars)
- Final Capital: `$16,359.25` (start: $10,000)
- Strategy Return: **+63.59%**
- Buy & Hold Return: **+551.84%**
- Relative vs B&H: **-488.25%**
- Total Trades: 12 (Long: 11, Short: 1)
- Win Rate: 58.3%
- Profit Factor: 3.21
- Sharpe Ratio: 6.11
- Max Drawdown: -24.09%

### WDC
- Period: `2024-05-09 -> 2026-05-08` (501 bars)
- Final Capital: `$34,133.11` (start: $10,000)
- Strategy Return: **+241.33%**
- Buy & Hold Return: **+780.90%**
- Relative vs B&H: **-539.57%**
- Total Trades: 13 (Long: 11, Short: 2)
- Win Rate: 53.8%
- Profit Factor: 6.08
- Sharpe Ratio: 6.67
- Max Drawdown: -22.58%

## Notes
- SNDK has a shorter available history window than 2 full years in Yahoo Finance data.
- Returns and risk metrics are those produced by `strategies/curves/curved_channel_strategy.py` with current defaults.