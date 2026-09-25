# Sloped Lines market-hours audit

Audit date: 2026-09-24

The configured active trading window is `regular market`, defined as 09:30 through 16:00 in `America/New_York`. The current daily Yahoo request excludes extended-hours data.

## Current one-year dashboard configurations

The configured AAPL, AMD, NVDA, and SPY Sloped Lines parameters were rerun on daily Yahoo candles from 2025-09-24 through 2026-09-23.

| Stock | Buy signals | Actual sell signals | Still open at end of data |
|---|---:|---:|---:|
| AAPL | 38 | 37 | 1 |
| AMD | 22 | 22 | 0 |
| NVDA | 27 | 27 | 0 |
| SPY | 13 | 12 | 1 |
| **Total** | **100** | **98** | **2** |

| Session classification | Buys | Sells |
|---|---:|---:|
| Derived from regular-session candles | 100 | 98 |
| Derived from after-hours candles | 0 | 0 |
| Derived from pre-market or overnight candles | 0 | 0 |

Daily bars store a session date without a clock time. These counts prove that every signal was derived from regular-session OHLCV and that no extended-hours candle was used. They do not prove the precise intraday time at which a daily signal became actionable. The two end-of-data marks are open positions, not sell signals.

## Saved one-hour backtests with exact timestamps

The older one-hour NVDA and SPY backtests store UTC timestamps. After conversion to New York time, every entry and exit falls within 09:30 through 16:00.

| Stock | Regular-hours buys | Regular-hours sells | After-hours buys | After-hours sells |
|---|---:|---:|---:|---:|
| NVDA | 30 | 30 | 0 | 0 |
| SPY | 27 | 27 | 0 | 0 |
| **Total** | **57** | **57** | **0** | **0** |

There were also zero pre-market and zero overnight events in these timestamped backtests.

## Execution database

The local database contains 105 Sloped Lines positions, all with broker and mode set to `backtest`; it contains no live or paper Sloped Lines executions. Of those records, 57 are the timestamped hourly positions above and 48 are daily positions without a genuine execution time. These database rows overlap saved backtests and should not be added to the current-dashboard totals.

The daily database importer currently turns a date-only buy into `09:30+00:00` and a date-only sell into `16:00+00:00`. Those values are synthetic placeholders intended to represent the session open and close, but the `+00:00` suffix incorrectly labels them as UTC. Interpreting them literally would make some daily markers appear pre-market in New York. They must remain classified as `daily/no exact time` until the importer localizes them to `America/New_York` correctly.

## Conclusion

No genuine after-hours Sloped Lines buy or sell was found. The current daily dashboard generated 100 buys and 98 actual sells from regular-session data, with two positions still open. The independently timestamped hourly sample confirms 57 regular-hours buys and 57 regular-hours sells with zero extended-hours events.
