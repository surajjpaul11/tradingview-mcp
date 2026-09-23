# Enhanced Channel losing-trade review

Data: the frozen 499-bar daily snapshot for GOOGL, AAPL, MELI, SPY, and NVDA, from 2024-09-23 through 2026-09-18. Each strategy is rerun with the same historical candles, $10,000 initial capital, 0.1% commission and 0.05% slippage per side. Returns below are the arithmetic **mean of five separate stock backtests**, not the return of a portfolio. The [machine-readable results](enhanced_channel_loss_filters.json) and [reproduction script](../scripts/analyze_channel_loss_filters.py) contain the stock-level detail.

The earlier count of 41 losses in 73 Channel trade rows included two end-of-data marks of positions that had not closed. Excluding both marks leaves **40 losses in 71 actual closed trades**. Of these, the stopgap exit accounted for 20 losses in 20 trades. Channel inflection entries lost 13 of 20 times and had a negative sum of net trade returns. These are useful investigation targets, but the exit label itself is only known after entry and cannot serve as an entry filter.

| Channel entry condition | Closed trades | Losses | Mean stock return |
| --- | ---: | ---: | ---: |
| Unfiltered Channel | 71 | 40 | +4.26% |
| RSI strategy already long | 37 | 19 | +7.87% |
| Bollinger strategy already long | 26 | 12 | +13.81% |
| RSI **or** Bollinger already long | 41 | 22 | +9.59% |
| RSI **and** Bollinger already long | 22 | 9 | +12.19% |
| Close below Bollinger middle band | 36 | 17 | +11.73% |
| Reclaim from below Bollinger lower band | 9 | 3 | +9.10% |
| Enhanced Lines already long | 5 | 3 | +0.02% |
| Volume/price breakout in past five bars | 1 | 0 | +0.23% |

The strongest exploratory result is requiring the Bollinger strategy to hold a long position at the Channel entry close. The Channel was rerun with this restriction, so skipping a trade could change which later trades it took. Its stock returns were GOOGL +16.66% (6 trades, 3 losses), AAPL +15.01% (5, 3), MELI -1.73% (5, 3), SPY +2.06% (4, 2), and NVDA +37.03% (6, 1). The unfiltered returns on the same closed-trade basis were +17.56%, +14.72%, -14.12%, +1.93%, and +1.22%, respectively. Much of the apparent improvement comes from NVDA. Bollinger confirmation removed **45 of 71** Channel trades and still left **12 losing closes**.

For a date-based diagnostic, unfiltered Channel had 21 losses in 37 early entries and 19 in 34 later entries. Bollinger confirmation had 2 losses in 8 early entries and 10 in 18 later entries. The later portion is **not untouched out-of-sample data**: these five symbols have already been used for strategy research, and several filters were tried here. The script verifies that Bollinger's active/flat state at every tested Channel entry matches a rerun using only candles through that date. This checks for future-data leakage in that confirmation, not predictive validity.

The current Channel engine still models an entry at the same close that confirms its signal, which may be an unfillable price in live use. Until entries are modeled at the next executable price and this specific filter is tested on fresh dates and additional stocks, **keep the production Channel rule unchanged**. The implementation includes an optional `long_entry_mask` for reproducible research; the default remains unrestricted. Further work should compare net return, drawdown, and the trades lost to the filter, then evaluate a predeclared Bollinger rule on genuinely unseen data. No tested combination eliminated all losses, and the Volume Breakout and Enhanced Lines overlaps were too rare to judge.
