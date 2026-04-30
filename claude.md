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
  STRATEGIES.md                          # Full strategy documentation (parameters, usage, comparisons)
  vwma17_strategy.py                     # VWMA 17 with adaptive ER filter — standalone Python backtester
  vwma17_strategy.pine                   # VWMA 17 — TradingView Pine Script v6 equivalent
  higher_highs_strategy.py               # Higher Highs MTF structure — standalone Python backtester
  higher_highs_strategy.pine             # Higher Highs — Pine Script v6 (core logic only)
  buy_and_protect_strategy.py            # Buy and Protect — B&H with downside protection
  straight_line_strategy.py              # Straight Line — trendline break strategy
  straight_line_visual.html              # Interactive visual of trendline break concept
  compare_exit_variants.py               # Exit mechanism comparison script
  compare_buy_and_protect.py             # Buy and Protect vs B&H comparison script
  compare_bp_variants.py                 # Buy and Protect parameter variant comparison
  compare_min_swings.py                  # Higher Highs min_swings comparison
  compare_straight_line.py               # Straight Line vs B&H comparison script
  volatility_harvester_strategy.py        # Volatility Harvester — mean reversion for choppy markets
  compare_volatility_harvester.py         # Volatility Harvester vs B&H comparison script
  enhanced_lines_strategy.py             # Enhanced Lines — channel bounce trading, volume-weighted sizing
  enhanced_lines_strategy.html           # Interactive visual of channel bounce concept
  compare_enhanced_lines.py             # Enhanced Lines vs Straight Line vs B&H comparison script
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

3. **Added adaptive Kaufman Efficiency Ratio trend filter**
   - ER measures trend efficiency: `|net change| / sum(|bar-to-bar changes|)`
   - ER > 0.3 (trending) → SMA(200) filter | ER <= 0.3 (choppy) → SMA(100) filter
   - Prevents whipsaws in choppy markets, rides trends in strong ones

4. **Fixed short trade cost calculation bug in `_apply_costs()`**
   - The original formula `(exit - entry) / entry` only works for longs
   - Added `side` check: shorts use `(entry - exit) / entry`
   - Backward compatible: trades without `side` key default to long behavior

5. **Updated `server.py`** tool docstrings to list `vwma17` as available strategy

6. **Created `strategies/vwma17_strategy.py`** and `strategies/vwma17_strategy.pine`

### Phase 1b: Higher Highs Strategy (COMPLETE)

1. **Created `strategies/higher_highs_strategy.py`** — Multi-timeframe market structure strategy
   - HTF (4H): Detects 3+ consecutive HH/HL (bullish) or LL/LH (bearish) with 3% tolerance
   - LTF (1H): Enters on pullback confirmations (higher low for longs, lower high for shorts)
   - Exits: HTF structure flip + trend exhaustion detector (RSI divergence, volume dry-up, ATR spike — 2/3 needed)
   - Optional trailing stop (disabled by default — tested variants showed struct+exhaust exits outperform)
   - Supports `--long-only` flag, re-entry after exits
   - Full CLI with configurable parameters

2. **Created `strategies/higher_highs_strategy.pine`** — Pine Script v6 with `request.security()` for MTF

3. **Added `_run_higher_highs()` to `backtest_service.py`** with supporting functions:
   - `_aggregate_candles()`, `_find_swings()`, `_get_structure()`
   - Added "30m" to valid intervals, "5d" to valid periods

### Phase 1c: Buy and Protect Strategy (COMPLETE)

1. **Created `strategies/buy_and_protect_strategy.py`** — Buy-and-hold with downside protection
   - Enters long immediately on bar 1, stays invested like B&H
   - Exits only when 2+ danger signals fire simultaneously (confluence):
     - Rapid decline (price drops 8% from rolling peak)
     - MA breakdown (price closes below SMA 200)
     - Volatility spike (ATR > 3x average)
   - Re-entry via `ma_reclaim` (default) or `higher_low` mode
   - Tested 6 parameter variants — SMA200/8%/3.0x with 2+ confluence chosen as default
   - Captures ~86% of B&H returns with significantly lower drawdowns

### Phase 1d: Straight Line Strategy (COMPLETE)

1. **Created `strategies/straight_line_strategy.py`** — Trendline break strategy
   - Draws support trendlines connecting ascending swing lows (uptrend) and resistance trendlines connecting descending swing highs (downtrend)
   - Requires 4-point confirmation: 2 anchor points + 2 additional points within 1.5% tolerance
   - Trades the break: sells when price closes below support trendline, buys when price closes above resistance trendline
   - 1-bar break confirmation (signal on close, execute on next bar's open)
   - Long-only by default, optional `--enable-short` flag
   - Tested across 23 symbols: +67.38% avg return, beats B&H on reversal-heavy assets

2. **Created `strategies/straight_line_visual.html`** — Interactive HTML visualization of trendline break concept

### Phase 1e: Volatility Harvester Strategy (COMPLETE)

1. **Created `strategies/volatility_harvester_strategy.py`** — Mean reversion for choppy markets
   - Kaufman ER < 0.25 regime gate — only trades when market is choppy/directionless
   - ATR Z-Score entries: buy when price >= 3.0 ATR below SMA(20), short when >= 3.0 ATR above
   - Volume confirmation: volume >= 1.5x its MA (optional, enabled by default)
   - Triple-layer exits: mean reversion to SMA, 15-bar time limit, 2.0 ATR stop loss (frozen at entry)
   - Supports long + short, with `--long-only` flag
   - Tuned defaults: dev=3.0, stop=2.0, hold=15 (tested 8 variants across 23 symbols)
   - Long-only mode: +1.40% avg across 23 symbols, best on high-vol assets (VXX +25.73% vs B&H)

Full strategy documentation: [`strategies/STRATEGIES.md`](strategies/STRATEGIES.md)

### Available Backtest Strategies (12 total)

| Strategy | Type | Sides | Description |
|----------|------|-------|-------------|
| rsi | Mean reversion | Long only | Buy RSI<40, sell RSI>60 |
| bollinger | Mean reversion | Long only | Buy at lower band, sell at middle |
| macd | Momentum | Long only | Buy golden cross, sell death cross |
| ema_cross | Trend following | Long only | EMA 20/50 crossover |
| supertrend | Trend following | Long only | ATR-based trend flip |
| donchian | Breakout | Long only | Donchian channel breakout (Turtle Trader) |
| **vwma17** | **Trend following** | **Long + Short** | **VWMA(17) crossover + adaptive ER filter, ATR SL/TP** |
| **higher_highs** | **MTF structure** | **Long + Short** | **3+ HH/HL detection, exhaustion exits, 3% tolerance** |
| **buy_and_protect** | **B&H + protection** | **Long only** | **SMA200 + 8% decline + ATR spike, 2+ signal confluence** |
| **straight_line** | **Trendline break** | **Long (+ optional short)** | **4-point trendline confirmation, 1.5% tolerance, 1-bar break confirm** |
| **volatility_harvester** | **Mean reversion** | **Long + Short** | **ATR Z-Score + volume entries, ER regime gate, triple-layer exits** |
| **enhanced_lines** | **Channel trend** | **Long + Short** | **Channel bounce trading, volume-weighted sizing, tax-optimized partial sells** |

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
- RSI divergence (standalone, not the exhaustion sub-signal in higher_highs)
- Ichimoku Cloud
- Volume profile-based strategies

## Key Design Decisions

1. **Python-only for execution, Pine Script preserved for TradingView portability.** Claude can translate between the two. The `.pine` file lets users paste into TradingView; the `.py` file runs backtests and live trades.

2. **Zero external dependencies for core indicators/backtest.** The entire backtest engine uses only Python stdlib. This keeps the MCP server lightweight and avoids dependency conflicts.

3. **Yahoo Finance for historical data.** Free, no API key, supports stocks + crypto + ETFs + indices. Limitation: rate limits and occasional downtime.

4. **Short trade support requires `side` field in trade dicts.** Any new strategy that supports shorts must include `"side": "short"` in its trade output for `_apply_costs()` to calculate returns correctly. Currently `vwma17`, `higher_highs`, and `straight_line` (when `--enable-short`) support shorts.

5. **Strategy exit testing matters.** Exit mechanism variants should be compared empirically before setting defaults. The higher_highs strategy tested 5 exit variants — structure+exhaustion (no trailing stop) outperformed all trailing stop variants on index ETFs. See `strategies/STRATEGIES.md` for the comparison table.

6. **Signal confluence reduces false exits.** Buy and Protect tested single-signal vs multi-signal exits — requiring 2+ danger signals to fire simultaneously reduced whipsaws dramatically and captured ~97% of B&H returns on the best variant (SMA200/8%/3.0x).

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

# Run standalone Higher Highs backtest
python strategies/higher_highs_strategy.py --symbol SPY --period 2y --long-only

# Run standalone Buy and Protect backtest
python strategies/buy_and_protect_strategy.py --symbol SPY --period 2y

# Run standalone Straight Line backtest
python strategies/straight_line_strategy.py --symbol SPY --period 2y
python strategies/straight_line_strategy.py --symbol QQQ --period 2y --enable-short

# Run standalone Volatility Harvester backtest
python strategies/volatility_harvester_strategy.py --symbol SPY --period 2y
python strategies/volatility_harvester_strategy.py --symbol BTC-USD --no-volume-filter

# Run standalone Enhanced Lines backtest
python strategies/enhanced_lines_strategy.py --symbol SPY --period 2y
python strategies/enhanced_lines_strategy.py --symbol QQQ --no-short
```

## Inspiration

Architecture inspired by [DaviddTech's video](https://youtu.be/uOC9vLRipsg) showing Claude + custom MCP server for TradingView backtesting. Our fork goes further by adding execution capability.