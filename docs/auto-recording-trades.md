# Auto-Recording Trades — Integration Guide

> How to make every strategy execution automatically log trades to the database.

---

## What's Already Wired Up

The `execute_trade` MCP tool **already auto-records** every trade. The flow is:

```
execute_trade(symbol, strategy, capital_usd, broker, dry_run)
       │
       ├── 1. check signal via signal_service.py
       ├── 2. place order via execution_service.py
       └── 3. auto-log to trades.db via trade_db.log_trade()  ← automatic
```

**Any trade placed through `execute_trade` is recorded.** You don't need to do anything extra for that path.

---

## What's NOT Yet Auto-Recorded

The **standalone strategy scripts** in `strategies/` (e.g. `vwma17_strategy.py`, `higher_highs_strategy.py`) and the **backtest tools** (`run_backtest`, `compare_strategies`) — these run simulations but don't log to the trade database because they produce historical backtests, not live executions.

If you want those to also record, here are the integration options:

---

## Option 1: Use MCP Tools (Recommended — No Code Changes)

Just ask Claude to use the built-in tools. Every trade goes through the pipeline and gets recorded automatically:

```
"Check all strategies for VXX and execute any active signals with $500 on Alpaca"

"Every day, check VWMA17 on BTC-USD and execute with $1000 on Bitget if there's a signal"

"Run VWMA17 on SPY, AAPL, MSFT — execute any buy signals with $500 each on Alpaca"
```

The `execute_trade` tool handles: signal check → order → DB log — all in one call.

---

## Option 2: Add Recording to Standalone Strategy Scripts

If you run strategies directly via `python strategies/vwma17_strategy.py`, add logging at the trade entry/exit points.

### Step 1: Import trade_db

```python
# At the top of any strategy script
import sys
sys.path.insert(0, "src")
from tradingview_mcp.core.services.trade_db import log_trade, close_trade
```

### Step 2: Log on entry

When the strategy generates a buy/sell signal:

```python
# After detecting a new trade entry
trade_id = log_trade(
    symbol="BTC-USD",
    side="buy",                    # or "sell"
    strategy="vwma17",             # strategy name
    broker="bitget",               # or "alpaca"
    quantity=0.007,
    entry_price=current_price,
    capital_usd=500.0,
    mode="dry_run",                # or "live"
    stop_loss=stop_loss_price,     # optional
    take_profit=take_profit_price, # optional
)
print(f"Trade logged: {trade_id}")
```

### Step 3: Log on exit

When the strategy closes a position:

```python
# After detecting a trade exit
result = close_trade(
    trade_id=trade_id,
    exit_price=exit_price,
    exit_reason="stop_loss",  # or "take_profit", "signal_flip", "manual"
)
print(f"P&L: ${result['pnl_usd']:+.2f} ({result['pnl_pct']:+.2f}%)")
```

---

## Option 3: Wrap Backtest Results into Trade Records

After running a backtest, bulk-import the simulated trades:

```python
from tradingview_mcp.core.services.backtest_service import run_backtest
from tradingview_mcp.core.services.trade_db import log_trade, close_trade

# Run backtest
result = run_backtest("SPY", "vwma17", period="2y", interval="1d")

# Import each trade into the DB
for trade in result.get("trades", []):
    trade_id = log_trade(
        symbol="SPY",
        side=trade["type"],         # "long" or "short"
        strategy="vwma17",
        broker="backtest",          # mark as backtest source
        quantity=1.0,
        entry_price=trade["entry_price"],
        capital_usd=trade["entry_price"],
        mode="backtest",
        stop_loss=trade.get("stop_loss"),
        take_profit=trade.get("take_profit"),
    )

    if trade.get("exit_price"):
        close_trade(
            trade_id=trade_id,
            exit_price=trade["exit_price"],
            exit_reason=trade.get("exit_reason", "signal"),
        )
```

---

## Querying Your Trade History

After trades are recorded, use MCP tools or Python directly:

### Via Claude (MCP tools)
```
"Show my trade history"
"Show P&L summary for VWMA17"
"Show equity curve for all my Alpaca trades"
"Close trade <trade_id> at $42.50 reason take_profit"
```

### Via Python
```python
from tradingview_mcp.core.services.trade_db import (
    get_trade_history, get_pnl_summary, get_equity_curve
)

# All trades
trades = get_trade_history()

# Filter by strategy
vwma_trades = get_trade_history(strategy="vwma17")

# P&L summary
summary = get_pnl_summary(strategy="vwma17")
print(f"Win rate: {summary['win_rate_pct']}%")
print(f"Total P&L: ${summary['total_pnl_usd']}")

# Equity curve (for charting)
curve = get_equity_curve(strategy="vwma17")
# curve = [{"date": ..., "pnl_usd": ..., "cumulative_pnl_usd": ...}, ...]
```

---

## Database Location

- **File:** `data/trades.db` (SQLite, auto-created)
- **Gitignored:** Yes — each user has their own trade journal
- **Tables:** `trades`, `trade_exits`, `strategy_snapshots`
- **Full schema:** See `trading-readme.md`
