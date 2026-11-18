# Persistent candle history

Yahoo Finance supplies stock/ETF history and most backtest data. Hyperliquid
supplies crypto history; its browser WebSocket continues providing live updates.
TradingView Screener remains a separate source for screening and indicators.

Historical requests from both chart pages and shared MCP backtest/scanner code
are automatically stored in SQLite. No ticker registration is required. A new
resolution creates a separate series; wider ranges download missing coverage.
Adjusted Yahoo chart data and raw research prices are deliberately isolated.
Standalone strategy scripts with their own download functions are unchanged.

## Location and schema

The default is `data/market_data.sqlite3` relative to the checkout. Set
`MARKET_DATA_DB_PATH` to an absolute path to share a database across UI/MCP
processes or worktrees. Keep SQLite on a local filesystem: WAL is not intended
for network filesystems. Docker Compose mounts a named volume at `/app/market-data`,
separate from `trades.db`. Back up the database using SQLite's backup API or the
SQLite CLI `.backup`; copying only the main file while WAL is active is unsafe.

| Table | Identity / purpose |
|---|---|
| `candle_series` | Provider, symbol, interval, session and price basis; active generation and provider timezone |
| `candles` | `(series_id, generation, time)`; OHLCV, finality, fetch time and original normalized payload |
| `fetch_coverage` | Successful query intervals, check times and provider limitations |
| `fetch_state` | Durable refresh leases, error/cooldown state and last attempts/successes |
| `candle_snapshots` | Content-addressed immutable datasets with source/window/origin provenance |
| `snapshot_candles` | Independent copies of the snapshot's candles |
| `saved_best_runs` | Preset fingerprint, snapshot, engine revision, costs and expected/observed results |

A period such as `1y` is a request window, not a series key. Times are true UTC
Unix seconds; exchange-local `date` labels remain compatible with the existing
strategy engines. Prices use SQLite REAL, retaining existing adapter rounding.

## Refresh and failure behavior

Current history becomes stale after 60 seconds; closed windows after one day.
Covered reads return immediately while background workers refresh overlapping
recent bars. Wider chart requests can return explicitly incomplete history while
fetching the missing range. Strategy calculations reject incomplete coverage.
Identical cold requests share a cross-process lease. Yahoo downloads are serialized
across processes using the same database. Crashed leases expire after 180 seconds.

Failures preserve previously published data and create a provider cooldown,
starting at 60 seconds and increasing to 15 minutes; numeric Retry-After values
are honored. Cold failures return HTTP 503 with Retry-After instead of empty
successful charts. Explicitly closed US sessions can have successful empty
coverage; an entirely empty backtest window is rejected. Hyperliquid's retention
limits are reported and incomplete backtests are refused.

Every publication creates an immutable generation. A completed adjusted overlap
that changes triggers a full covered-range rebuild before publication. Accessed
series receive a full audit at least weekly. Refreshes are demand driven while
the application is running, not a separate scheduled process. Revisions are
currently retained; monitor database size if retaining years of minute history.

Existing candle response shapes and query parameters remain available. Responses
add `data_status` with source, last refresh, data-through time, completeness,
staleness, refresh state, errors and a `data_revision`. Pass that revision to
statistics/trades/overlay endpoints to use the same immutable dataset. Revision
and snapshot IDs must match the requested source, symbol, interval and session.

## Saved Best

Explicit Saved Best loading requests `capture_snapshot=true` on the existing
best-parameters endpoint. Legacy presets receive a **reconstructed** snapshot on
first explicit load, using available candles and their recorded window (or the
current requested period when no original window exists). The original recorded
performance is preserved alongside the new observed result. A reconstruction
cannot recover missing original provider data.

New `set_best_parameters` calls with performance require the original `candles`
and `backtest_window` and capture an **original** snapshot before publishing the
preset. Supply `observed` metrics and `costs` from the run as well. Parameter-only
records without supplied candles fetch current history and are marked reconstructed. Loading passes `snapshot_id` and captured dates
through candles and strategy requests; background refreshes cannot change it.
A strategy-source hash identifies the engine; the UI flags later engine changes.
Snapshots freeze inputs, not strategy code or its outputs.
