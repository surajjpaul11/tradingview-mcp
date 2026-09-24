# Potential Issues Found by Claude

Review date: 2026-09-21, branch `claude` (base `f9b047f`). Read-only review — nothing below has been fixed.
"Confirmed" = reproduced by running the code. Others are from reading the code.

Scope reviewed: `backtest_service.py`, `execution_service.py`, `ui/server.py`, `trade_db.py`, launchers, repo hygiene.
Not reviewed in depth: `indicators.py`, screener/news/sentiment services, `ui/static/app.js`, standalone strategy internals.

---

## A. Critical — backtest numbers are wrong

### 1. VWMA17 short trades are costed as longs — CONFIRMED
- **Where:** `src/tradingview_mcp/core/services/backtest_service.py` → `_run_vwma17()` exit branches.
- **What:** short exits append `"short": True` but no `"side": "short"`. `_apply_costs()` checks `t.get("side") == "short"`, so every short is scored as a long; a winning short shows as a loss.
- **Evidence:** SPY 2y 1d — 3 of the first 8 trades had `side=None, short=True`.
- **Note:** CLAUDE.md says the short-cost bug was fixed; the fix never covered this path.
- **Fix idea:** emit `"side": "short"` (and `"side": "long"`) on every exit; add a test.

### 2. Partial-position strategies compounded as full-capital trades — CONFIRMED
- **Where:** `_calc_metrics()` / `_build_equity_curve()` in `backtest_service.py`; affects `enhanced_lines` (emits one row per lot with `shares` / `trade_pct`), probably `enhanced_channel`.
- **What:** every lot is compounded as if it used 100% of capital, sequentially, even when lots overlap.
- **Evidence (2y, 1h):** MCP `run_backtest` SPY −83.08% (478 trades) vs standalone saved −15.28% (452); NVDA −53.33% vs −8.11%.
- **Fix idea:** strategies return a position-weighted trade list or an equity series; metrics use weights.

### 3. Sharpe ratio (and Calmar) wrong for every strategy
- **Where:** `_calc_metrics()` in `backtest_service.py` (same pattern copied into standalone `calc_metrics()` functions).
- **What:** per-*trade* returns are annualized with per-*bar* factors (`sqrt(252)` / `sqrt(252*6)`), and the risk-free rate is subtracted per bar. A strategy with 26 trades in 2 years is scaled as if it had 1,512 per year (e.g. SPY resistance_lines 1h showed Sharpe −9.9).
- **Fix idea:** compute Sharpe from a bar-level (or daily) equity curve, or annualize by trades-per-year.

### 4. "Walk-forward" is not walk-forward — PARTLY FIXED on develop (per-bar rates, None for inactive folds, INSUFFICIENT EVIDENCE verdict); no parameter search and no indicator warm-up on test slices
- **Where:** `walk_forward_backtest()` in `backtest_service.py`.
- **What:** no parameters are optimized on the train slice — fixed defaults run on both slices. Robustness = test return / train return, comparing a 30% window to a 70% window, so scores are biased toward "WEAK/OVERFITTED". Each slice starts cold, so strategies needing 200-bar warmup (vwma17, buy_and_protect) get few/no test trades.
- **Fix idea:** warm indicators on prior data, compare per-bar or annualized returns, optionally add real parameter search on train.

### 5. Built-in strategies fill on the signal bar's close
- **Where:** `_run_rsi`, `_run_bollinger`, `_run_macd`, `_run_ema_cross`, `_run_supertrend`, `_run_donchian`, `_run_vwma17` entries.
- **What:** signal and fill happen at the same close — mild look-ahead; real orders fill at the next open.
- **Fix idea:** queue signals and fill at next bar's open (as `straight_line` / `resistance_lines` do).

---

## B. Live-trading risks (real money when `dry_run=False`)

### 6. Bitget SL and TP are independent orders, not OCO
- **Where:** `execution_service.py` → `BitgetAdapter.place_market_order()`.
- **What:** stop and limit are placed separately; when one fills the other remains live and can sell coins no longer held (or error). If SL placement fails, the position is left unprotected and the error is only nested in `sl_order`.
- **Fix idea:** use exchange-native TP/SL or OCO params; cancel/rollback or fail loudly if protection can't be placed.

### 7. Alpaca bracket orders likely rejected (unverified) — FIXED 2026-09-23
- **Where:** `AlpacaAdapter.place_market_order()`; quantity rounding in `execute_order()`.
- **What:** qty rounded to 2 decimals (fractional) — Alpaca doesn't allow fractional brackets; bracket also needs both SL and TP (only one → use `oto`).
- **Fix idea:** whole shares for bracket/oto, choose `oto` when only one leg is given; test against paper.

### 8. Logged entry price is the pre-trade quote; dry run uses stale price — PARTLY FIXED 2026-09-23
Live orders now poll for the fill and record the filled price; `sync_broker_trades` reports rows whose
recorded entry still differs from the fill (it reports, it does not rewrite the entry price).
Dry runs still price from the last Yahoo daily close.
- **Where:** `execute_order()` → `_log_trade(entry_price=price)`; dry-run price = last *daily* close from Yahoo.
- **Fix idea:** log fill price; use a live quote for dry runs.

### 9. MCP HTTP server has no authentication
- **Where:** `server.py` streamable-http; Docker `CMD` binds `0.0.0.0`; `execute_order` tool exposed.
- **What:** anyone who can reach the port can call tools, including live orders if broker keys are set.
- **Fix idea:** bearer-token auth, bind to 127.0.0.1 by default, or disable execution tools on HTTP transport.

---

## C. Dashboard (`src/tradingview_mcp/ui/server.py`)

### 10. Auto-backtested shorts saved as buys
- `_save_backtest_trades()` reads `side` / `exit_reason` from `run_backtest()`'s `trade_log`, but `_build_trade_log()` doesn't include them → every trade stored as `buy`, short PnL sign wrong, exit reason always `signal_exit`.

### 11. Dashboard metrics inconsistent with backtests
- Trades sized at $1,000 but return computed as `total_pnl / 10000` (`trade_db.get_pnl_summary`); `pnl_usd` excludes the stored `fees_usd` while `pnl_pct` is net of costs; wins/losses counted on `pnl_usd`.

### 12. Backtest results cached forever
- First on-the-fly backtest per symbol/strategy is written to `trades.db` and never refreshed — strategy code or parameter changes don't show until the DB is cleared.

### 13. Smaller dashboard issues
- Always `period="2y"`; every trade labelled `interval='1d'` even for 1h strategies.
- `uvicorn reload=True` by default (now `--no-reload` flag exists, default still on).
- `_ensure_seeded()` runs on every `/api/filters` call and `rglob`s all backtest JSONs.

---

## D. Tests, repo, docs

### 14. No real tests / CI
- `test_*.py` are print scripts, network-dependent, no assertions, no `.github/workflows`.
- `test_strategies.py` places dry-run orders rather than testing strategies; `start.bat` runs it on every launch, seeding fake trades.
- `sys.path.insert(0, Path(__file__).parent.parent / "src")` points outside the repo.
- **Fix idea:** pytest suite on frozen OHLCV fixtures covering costs (long/short), metrics, no-lookahead.

### 15. Repo hygiene
- 342 generated `*_backtest_*.json` files tracked; empty `trades.db` / `trade_db.sqlite` at root; stray `vwma17_changes.patch`; `loops.json` tracked (only `loops.example.json` should be).

### 16. Misc
- CLAUDE.md says "zero external dependencies", but `ccxt`, `alpaca-trade-api`, `yfinance`, `fastapi` are required deps.
- `_get_dynamic_runner()` re-imports the strategy module from disk on every call; runners get only `candles` (no way to pass parameters).
- `backtest_strategy` tool docstring in `server.py` lists 9 of 14 strategies.
- `1h` + `5y` accepted by validation but Yahoo only serves ~730 days of hourly data → unhelpful error.
- Standalone strategies duplicate `fetch_ohlcv` / `apply_costs` / `calc_metrics` (bugs 1/3 are copied into each).

---

## Suggested fix order
1. A1–A3 — every reported number (incl. `STRATEGIES.md` tables) depends on them.
2. B6, B7, B9 — before any live trading.
3. C10–C12 — dashboard consistency.
4. D14 — regression tests on fixed data so A1–A3 stay fixed; then re-run comparisons and update `STRATEGIES.md`.


---

## Fixed since this review (2026-09-23, branch `claude`)

- **Alpaca sizing (was item 7):** orders carrying a stop or take-profit are rounded down to whole shares;
  an order too small for one share is refused with the required capital. Unprotected orders stay fractional.
- **Market hours (new gap 3):** `execute_order` / `execute_trade` refuse live Alpaca orders while the market
  is closed and report the next open; `allow_closed_market=True` queues one deliberately.
- **Fills (was item 8):** live orders poll until terminal state and record the actual fill price.
- **Real exits (was item 2 of the Alpaca gaps):** new `close_position` MCP tool cancels the symbol's resting
  stop/target orders, flattens at market, and records the exit. `close_open_trade` remains database-only.
- **Reconciliation:** new `sync_broker_trades` MCP tool closes database rows whose position is gone at the
  broker (stop/target fired, or a manual sale) and flags entry-price mismatches.

Still open from the Alpaca list: guardrails (size caps, duplicate-order protection), the deprecated
`alpaca-trade-api` SDK, and the two parallel implementations (`scripts/active_trader.py` vs the MCP path).
