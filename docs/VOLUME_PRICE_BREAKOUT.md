# Volume-confirmed price breakout

This new research strategy looks for a completed bar that closes at least **3% above the prior close**, at least **2× the average volume of the preceding 20 bars**, and **above the preceding 20-bar high**. These are fixed initial defaults drawn from the project's existing volume breakout scanner, with a prior-high check to require a price breakout. The strategy is registered as `volume_price_breakout` for MCP backtests, live-signal checks, and the Opportunity research watchlist.

A signal on the last completed bar is **pending**, not filled. In historical runs, an order enters at the next bar's open. The exit is a two-ATR stop, a four-ATR target, or the next open after ten bars. Gaps through the stop or target use the open. If daily OHLC touches both thresholds, the stop wins in the simulation. Standard MCP fees of 0.1% commission and 0.05% slippage per side are applied by the backtest service. These are model assumptions, not broker fills.

## First fixed-snapshot check

The table below uses the existing [499-bar completed snapshot](returns_baseline_completed_2026-09-18.json), ending September 18, 2026. The later slice is the final 30% of each symbol's bars, using trade entries in that slice. This is a **diagnostic time slice**, not a fresh independent holdout: the five symbols were already used in project research. Open positions are excluded from total return. There is no pre-change return for this newly added strategy.

| Stock | Closed trades | Total return after costs | Win rate | Later-slice trades | Later-slice return |
|---|---:|---:|---:|---:|---:|
| GOOGL | 4 | 14.99% | 75.0% | 1 | 3.55% |
| AAPL | 2 | 2.64% | 50.0% | 0 | 0.00% |
| MELI | 2 | −2.12% | 50.0% | 0 | 0.00% |
| SPY | 0 | 0.00% | — | 0 | 0.00% |
| NVDA | 1 | −7.39% | 0.0% | 1 | −7.39% |

Only **nine closed trades** occurred across these stocks, so this run cannot support a calibrated gain probability or a capital-allocation ranking. The result does not establish an improvement over buy-and-hold or over the project's other strategies. The next evaluation should use more untouched symbols and dates, check split-adjusted volume/price data, and then test the signal with a portfolio-level fill model.
