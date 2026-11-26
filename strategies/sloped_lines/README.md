# Sloped Lines execution timing

Signals and fills are separate events. The engine evaluates historical candles in
order and queues signals that require a completed candle for execution at the next
available candle's open, including any gap. It does not fill those orders at the
signal candle's earlier open, line price, or close.

| Signal mode | Fill |
| --- | --- |
| Body-only boundaries (`use_wick=False`) | Next open |
| Close breakout (`full_candle=True`) | Next open |
| Candle-color filter (`inverse_color_trigger=True`) | Next open |
| Additional entry confirmation (`confirm_candles>0`) | Open after final confirmation |
| Stop using current-candle ATR | Next open |
| Unfiltered wick touch | Line/barrier price, or opening price when gapped beyond it |

These rules apply to ordinary entries, re-entries, support exits, pre-line stops,
and short reversals as applicable. A next-open entry can generate a protection
signal on its fill candle. No next candle means no fill: final-bar entry signals
produce no trade, and final-bar exit signals leave the position marked at the last
close with `exit_reason="end_of_data"`.

Trade dates and prices describe executions. `entry_signal_date` and
`exit_signal_date` identify the decision candles. End-of-data marks have no exit
signal date. Trendlines retain the signal's `break_bar`/`break_date` and separately
expose `fill_bar`/`fill_date`; `break_price` is the actual fill price, or null for an
unfilled signal. The conviction analysis uses signal dates for candle features and
fill dates to associate trades with lines.

Saved backtests and parameter-performance summaries predate this correction and
must be rerun before comparison. This change does not validate the remaining stop,
line-selection, parameter-selection, or performance-accounting assumptions.
