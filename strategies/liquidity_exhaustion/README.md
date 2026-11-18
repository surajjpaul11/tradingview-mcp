# Liquidity & Capitulation Exhaustion Strategy

A macro cycle strategy that identifies market tops (exuberance, narrow breadth, credit deterioration) and bottoms (forced margin liquidations, VIX term-structure backwardation, and capitulation exhaustion).

## Key Principles

1. **Top / Exuberance Detection:**
   - **Narrow Breadth:** S&P 500 Equal Weight vs Cap Weight (`RSP/SPY`) collapses as only a handful of mega-caps prop up the index while the median stock quietly rolls over.
   - **Credit Spread Warning:** High Yield vs Investment Grade (`HYG/LQD`) breaks downward 2–4 weeks ahead of equities.
   - **Complacency:** VIX compressed below 14.5.
   - **Action:** Protect profits, tighten stops, or exit to cash when price breaks below its 20-day SMA.

2. **Bottom / Margin Capitulation Reversal:**
   - **Forced Liquidation Inversion:** When leverage unwinds and margin calls occur, institutional desks panic-bid near-term put options, inverting the term structure: $\text{VTR} = \frac{\text{VIX}}{\text{VIX3M}} \ge 0.98\text{ to }1.00+$.
   - **The Inflection Trigger:** The bottom occurs when VTR peaks and eases back **below 0.98** (or below its 5-day EMA) accompanied by a positive reversal candle.
   - **Execution:** Next bar's Open (zero lookahead).

## 5-Year Backtest Comparison (2021–2026)

| Symbol | Trades | Win Rate | Strategy Return | Max Drawdown | Buy & Hold Return | Alpha vs B&H |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **SPY** | 15 | **60.0%** | **+64.81%** | **-10.17%** | +55.75% | **+9.06%** |
| **IWM** | 16 | **56.2%** | **+49.43%** | **-15.62%** | +15.74% | **+33.69%** |
| **BTC-USD** | 20 | **45.0%** | **+28.81%** | **-51.48%** | +10.74% | **+18.07%** |
| **DIA** | 15 | **66.7%** | **+33.00%** | **-11.54%** | +40.01% | -7.01% |
| **QQQ** | 19 | **42.1%** | **+46.25%** | **-16.08%** | +64.13% | -17.88% |

> **Key takeaway:** On SPY, the strategy beats Buy & Hold (+64.81% vs +55.75%) while slashing maximum drawdown by **over 63%** (-10.17% vs -27.5% in the 2022 bear market).

## Running the Strategy

```bash
# Run SPY 5-year backtest
python strategies/liquidity_exhaustion/liquidity_exhaustion_strategy.py --symbol SPY --period 5y

# Run 10-year backtest
python strategies/liquidity_exhaustion/liquidity_exhaustion_strategy.py --symbol SPY --period 10y

# Run full cross-asset comparison
python strategies/liquidity_exhaustion/compare_liquidity_exhaustion.py --period 5y
```
