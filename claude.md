# TradingView MCP — Project Context

## What This Is

A fork of [atilaahmettaner/tradingview-mcp](https://github.com/atilaahmettaner/tradingview-mcp) — a Python FastMCP server providing TradingView market analysis tools to AI assistants. We are extending it with backtesting, and eventually paper trading and live trade execution.

Owner: Suraj Paul (suraj.j.paul@gmail.com)
Fork: https://github.com/surajjpaul11/tradingview-mcp.git

## Architecture

- **Language:** Python 3.10+, pure stdlib (zero external deps for indicators/backtest)
- **Framework:** FastMCP (tools registered via `@mcp.tool()` decorators in `server.py`)
- **Data source:** Yahoo Finance (free, no API key) for historical OHLCV
- **Transport:** stdio (default) or streamable-http

### Key Directories

```
src/tradingview_mcp/
  server.py                              # All MCP tool definitions
  core/services/
    backtest_service.py                  # Backtest engine (run_backtest, compare_strategies, walk_forward_backtest)
    indicators_calc.py                   # Pure Python indicators (EMA, SMA, RSI, MACD, ATR, Bollinger, Supertrend, Donchian, VWMA)
    screener_provider.py                 # Real-time TradingView screener data
    yahoo_finance_service.py             # Yahoo Finance price data
    indicators.py                        # Bollinger band analysis logic
    coinlist.py                          # Exchange symbol management
  core/utils/
    validators.py                        # Input validation (timeframe, exchange)

strategies/                              # Strategy pairs: same name, .py + .pine extensions
  vwma17_strategy.py                     # Standalone Python backtester (can run independently)
  vwma17_strategy.pine                   # TradingView Pine Script v6 equivalent
```

### Strategy Convention

Every strategy gets two files with the **same filename**, different extensions:
- `.py` — Standalone Python implementation (runs independently, includes own indicators + data fetching + CLI)
- `.pine` — TradingView Pine Script v6 equivalent (for use in TradingView's native platform)

## What Has Been Done

### Phase 1: VWMA 17 Strategy + Backtesting (COMPLETE)

1. **Added `calc_vwma()` to `indicators_calc.py`**
   - Volume Weighted Moving Average: `sum(close * volume, period) / sum(volume, period)`
   - Pure Python, zero dependencies, fallback to SMA when volume is zero

2. **Added `_run_vwma17()` to `backtest_service.py`**
   - First strategy in the codebase that supports BOTH long and short positions
   - Entry: close crosses above VWMA → long; close crosses below VWMA → short
   - Exit: ATR-based stop loss (1.5x ATR) and take profit (2.0x ATR)
   - Registered in `_STRATEGY_MAP` and `_STRATEGY_LABELS`

3. **Fixed short trade cost calculation bug in `_apply_costs()`**
   - The original formula `(exit - entry) / entry` only works for longs
   - Added `side` check: shorts use `(entry - exit) / entry`
   - Backward compatible: trades without `side` key default to long behavior
   - All 6 original strategies are unaffected

4. **Updated `server.py`** tool docstrings to list `vwma17` as available strategy

5. **Created `strategies/vwma17_strategy.py`** — standalone backtester with CLI:
   ```bash
   python strategies/vwma17_strategy.py --symbol BTC-USD --period 2y
   ```

6. **Created `strategies/vwma17_strategy.pine`** — Pine Script v6 version

### Available Backtest Strategies (7 total)

| Strategy | Type | Sides | Description |
|----------|------|-------|-------------|
| rsi | Mean reversion | Long only | Buy RSI<40, sell RSI>60 |
| bollinger | Mean reversion | Long only | Buy at lower band, sell at middle |
| macd | Momentum | Long only | Buy golden cross, sell death cross |
| ema_cross | Trend following | Long only | EMA 20/50 crossover |
| supertrend | Trend following | Long only | ATR-based trend flip |
| donchian | Breakout | Long only | Donchian channel breakout (Turtle Trader) |
| **vwma17** | **Trend following** | **Long + Short** | **VWMA(17) crossover, ATR SL/TP** |

## What Needs To Be Done

### Phase 2: Execution Layer (HIGH PRIORITY)

Add paper trading and live trade execution so backtested strategies can actually trade.

**Architecture decision made:** Build a broker-agnostic execution router. Same strategy code runs in backtest, paper, or live mode — only the data feed and broker differ.

**Execution targets researched:**

| Asset Class | Data Source | Execution Broker | MCP Server Exists? |
|---|---|---|---|
| Crypto (107+ exchanges) | CCXT | CCXT (Binance, KuCoin, Bybit) | Yes: [Nayshins/mcp-server-ccxt](https://github.com/Nayshins/mcp-server-ccxt) |
| US Stocks, ETFs, Options | Alpaca / yfinance | Alpaca (commission-free) | Yes: [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server) |
| Global (stocks, futures, forex, bonds) | Interactive Brokers | Interactive Brokers | Yes: [rcontesti/IB_MCP](https://github.com/rcontesti/IB_MCP) (alpha) |

**Recommended MVP:** Start with CCXT for crypto (Suraj's primary focus is BTC/altcoins). Add Alpaca for US stocks as Phase 2b.

**New MCP tools to add:**
- `paper_trade_strategy` — Start strategy on paper trading (CCXT testnet / Alpaca sandbox)
- `live_trade_strategy` — Execute with real funds (requires explicit confirmation)
- `strategy_status` — Check running strategy, open positions, PnL
- `stop_strategy` — Halt a running strategy

**Key libraries:**
- `ccxt` — 107+ exchange unified API (pip install ccxt)
- `alpaca-py` — Alpaca Python SDK (pip install alpaca-py)

### Phase 2b: HTML Report Generator

Add visual backtest reports with equity curve charts and trade markers.
- Use Plotly or Chart.js embedded in single-file HTML
- New tool: `backtest_report` that returns an HTML file path

### Phase 3: More Strategies

Add more strategies following the paired `.py` + `.pine` convention:
- Moving average crossover variants (SMA, HMA, WMA with configurable lengths)
- RSI divergence
- Ichimoku Cloud
- Volume profile-based strategies

## Key Design Decisions

1. **Python-only for execution, Pine Script preserved for TradingView portability.** Claude can translate between the two. The `.pine` file lets users paste into TradingView; the `.py` file runs backtests and live trades.

2. **Zero external dependencies for core indicators/backtest.** The entire backtest engine uses only Python stdlib. This keeps the MCP server lightweight and avoids dependency conflicts.

3. **Yahoo Finance for historical data.** Free, no API key, supports stocks + crypto + ETFs + indices. Limitation: rate limits and occasional downtime.

4. **Short trade support requires `side` field in trade dicts.** Any new strategy that supports shorts must include `"side": "short"` in its trade output for `_apply_costs()` to calculate returns correctly.

## How To Run

```bash
# Install
uv sync

# Start MCP server (stdio)
uv run tradingview-mcp stdio

# Start MCP server (HTTP)
uv run tradingview-mcp streamable-http --host 127.0.0.1 --port 8000

# Run standalone VWMA17 backtest
python strategies/vwma17_strategy.py --symbol BTC-USD --period 2y
```

## Inspiration

Architecture inspired by [DaviddTech's video](https://youtu.be/uOC9vLRipsg) showing Claude + custom MCP server for TradingView backtesting. Our fork goes further by adding execution capability.