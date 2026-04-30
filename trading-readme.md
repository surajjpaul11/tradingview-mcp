# Live Trade Execution — Implementation Reference

> **For coding agents:** This document describes the live trading feature added to tradingview-mcp. Use it to understand the architecture, extend it, or build on top of it.

---

## Architecture Overview

```
Claude / MCP Client
       │
       ▼
server.py  (7 new MCP tools)
       │
       ├── signal_service.py     ← detects live buy/sell signal on latest bar
       │         │
       │         └── backtest_service.py  (reuses existing strategy engines)
       │
       ├── execution_service.py  ← places orders via broker adapter
       │         ├── BitgetAdapter   (crypto, via ccxt)
       │         └── AlpacaAdapter  (stocks/ETFs, via alpaca-trade-api)
       │
       └── trade_db.py           ← SQLite trade journal (auto-logged)
                 └── data/trades.db
```

---

## New Files

### `src/tradingview_mcp/core/services/signal_service.py`

Detects whether a strategy has an active signal on the **latest bar** — no new indicator logic, reuses `_STRATEGY_MAP` from `backtest_service.py`.

**Key functions:**
```python
get_live_signal(symbol: str, strategy: str, interval: str = "1d") -> dict
check_all_strategies(symbol: str, interval: str = "1d") -> dict
```

**Signal detection logic:** Runs the strategy on all candles, then on all-but-last candles. If a new trade appeared on the last bar → entry signal. If a trade closed on the last bar → exit signal.

**Return schema:**
```python
{
    "signal": "long" | "short" | "exit" | "none",
    "symbol": str,
    "strategy": str,
    "strategy_label": str,
    "price": float,
    "stop_loss": float | None,    # populated for vwma17; None for other strategies
    "take_profit": float | None,  # populated for vwma17; None for other strategies
    "exit_reason": str | None,
    "interval": str,
    "candles_fetched": int,
    "latest_bar_date": str,
    "timestamp": str,
}
```

**Strategies that emit SL/TP:** only `vwma17` (stored in `_SL_TP_STRATEGIES` set). To add SL/TP for other strategies, add the name to `_SL_TP_STRATEGIES` and ensure the strategy's trade dicts include `stop_loss`/`take_profit` keys.

---

### `src/tradingview_mcp/core/services/execution_service.py`

Broker adapter pattern. **All real orders require valid credentials in `.env`.**

**Key function:**
```python
execute_order(
    symbol: str,          # "BTC-USD" (Yahoo format, auto-converted in dry_run)
    side: str,            # "buy" | "sell"
    capital_usd: float,
    stop_loss: float | None,
    take_profit: float | None,
    broker: str,          # "bitget" | "alpaca"
    dry_run: bool = True,
    strategy: str = "manual",
) -> dict
```

**Position sizing:** `quantity = capital_usd / current_price`
- Bitget: 8 decimal places (crypto precision)
- Alpaca: 2 decimal places (fractional shares supported)

**Dry run behavior:** In `dry_run=True`, price is fetched from Yahoo Finance (no broker credentials needed). In `dry_run=False`, price is fetched from the live exchange.

**Auto-logging:** Every call to `execute_order()` (dry_run or live) is automatically logged to the SQLite trade database. The returned dict includes a `trade_id` UUID for later reference.

**Adding a new broker:** Create a class inheriting `BrokerAdapter` ABC, implement `place_market_order`, `get_current_price`, `get_account_balance`, and register in `_get_adapter()`.

---

### `src/tradingview_mcp/core/services/trade_db.py`

SQLite-based trade journal. DB file: `data/trades.db` (auto-created, gitignored).

**Schema (3 tables):**
```
trades (1) ──── (0..1) trade_exits
   └── strategy ──── strategy_snapshots
```

- **trades**: trade_id (UUID), symbol, side, strategy, broker, quantity, entry_price, stop_loss, take_profit, capital_usd, mode (dry_run/live), status (open/closed)
- **trade_exits**: exit_price, exit_reason, pnl_usd, pnl_pct, holding_seconds, fees_usd
- **strategy_snapshots**: cumulative_pnl, total_trades, winning_trades, losing_trades, win_rate_pct (per strategy/broker/symbol)

**Key functions:**
```python
log_trade(...)         -> str           # Returns trade_id UUID
close_trade(trade_id, exit_price, exit_reason) -> dict  # Computes P&L
get_trade_history(strategy?, symbol?, broker?, status?, limit) -> list[dict]
get_pnl_summary(strategy?, symbol?, broker?) -> dict    # Aggregated stats
get_equity_curve(strategy?, symbol?, broker?) -> list[dict]  # For charting
```

**P&L calculation (in `close_trade`):**
- Buy side: `(exit_price - entry_price) * quantity - fees`
- Sell side: `(entry_price - exit_price) * quantity - fees`
- Percentage: `pnl_usd / capital_usd * 100`

---

## MCP Tools (in `server.py`)

### Signal Detection
| Tool | Description | Credentials needed |
|------|-------------|-------------------|
| `check_signal(symbol, strategy, interval)` | Read-only signal check on latest bar | ❌ None |
| `check_all_signals(symbol, interval)` | Checks all 8 strategies, highlights active ones | ❌ None |

### Trade Execution
| Tool | Description | Credentials needed |
|------|-------------|-------------------|
| `execute_trade(symbol, strategy, capital_usd, broker, interval, dry_run)` | Signal check → order (dry_run by default) | ✅ Only if `dry_run=False` |

### Trade Tracking
| Tool | Description | Credentials needed |
|------|-------------|-------------------|
| `trade_history(strategy, symbol, broker, status, limit)` | Query past trades with filters | ❌ None |
| `trade_pnl_summary(strategy, symbol, broker)` | Aggregated P&L, win rate, best/worst trade | ❌ None |
| `trade_equity_curve(strategy, symbol, broker)` | Cumulative P&L series for plotting | ❌ None |
| `close_open_trade(trade_id, exit_price, exit_reason)` | Close a trade, compute P&L | ❌ None |

**`execute_trade` symbol conversion:**
- Bitget: `BTC-USD` → `BTC/USDT` (auto-converted via `.replace("-USD", "/USDT")`)
- Alpaca: uses the left part of the ticker (`AAPL`, `SPY`, etc.)

---

## Configuration

Add to `.env` (see `.env.example` for template):

```bash
# Bitget (crypto)
BITGET_API_KEY=...
BITGET_API_SECRET=...
BITGET_PASSPHRASE=...
BITGET_SANDBOX=true   # true = testnet

# Alpaca (stocks/ETFs)
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_PAPER=true     # true = paper trading endpoint
```

---

## Dependencies

In `pyproject.toml`:
```
ccxt>=4.3            # Bitget (and 100+ other exchanges)
alpaca-trade-api>=3.0  # Alpaca stocks/ETFs
```

Install: `uv sync`

---

## Test Scripts

```bash
# Signal detection — no credentials needed
uv run python test_signal_service.py

# Order execution — dry_run only, no credentials needed
uv run python test_execution_service.py

# Trade database — uses temp file SQLite, no credentials needed
uv run python test_trade_db.py
```

---

## Extension Points

### Add SL/TP to more strategies
1. In the strategy function inside `backtest_service.py`, populate `stop_loss` and `take_profit` keys in the trade dict.
2. Add the strategy name to `_SL_TP_STRATEGIES` in `signal_service.py`.

### Add a new broker (e.g. Binance, IBKR)
1. Create a new class `BinanceAdapter(BrokerAdapter)` in `execution_service.py`.
2. Add it to `_get_adapter()` factory.
3. Add credentials to `.env.example`.

### Add scheduled/polling execution
Run `get_live_signal()` on a schedule (e.g. via `APScheduler` or a cron job). When signal is `"long"` or `"short"`, call `execute_order(..., dry_run=False)`. Consider adding a state file to avoid duplicate orders within the same signal bar.

### Build P&L charts
Use `get_equity_curve()` to get time-series data. Each point has `date`, `pnl_usd`, `cumulative_pnl_usd`, `strategy`, `symbol`. Feed this into any charting library (matplotlib, plotly, etc.).

---

## Example Claude Prompts (in Claude Desktop)

```
"Check if VWMA17 has an active signal on BTC-USD"
"Check all strategies for signals on SPY"
"Execute a dry-run trade for BTC-USD using VWMA17 with $500 on Bitget"
"Execute a paper trade for AAPL using EMA Cross with $1000 on Alpaca"
"Show my trade history"
"Show P&L summary for VWMA17 strategy"
"Show equity curve for my Bitget trades"
"Close trade <trade_id> at $70000 with reason take_profit"
```
