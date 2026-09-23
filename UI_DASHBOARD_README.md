# TradingView MCP UI Dashboard

This README documents the changes made to integrate new strategies, enable centralized database logging for all trades, and provide a premium frontend UI for visualization.

## 1. Core Changes and Implementations

### Strategy Integrations & Database Logging
- **New Strategies Mapped:** Added support for four new custom strategies to be executed as live triggers:
  - `straight_line`
  - `enhanced_lines`
  - `buy_and_protect`
  - `volatility_harvester`
  - *Plus dynamic integration for any other strategies added in the future using our lazy-load dictionary approach.*
- **Trade Logging:** Configured `execution_service.py` to seamlessly and automatically log incoming live or simulated trades precisely into `trades.db` via `trade_db.py`.

### Premium Visualizer Dashboard
A fully customized, high-performance HTML/JS/FastAPI dashboard was engineered to let you interactively view simulated and live historical trades on a Native TradingView Lightweight Chart.
- **Backend (`src/tradingview_mcp/ui/server.py`)**: A dedicated FastAPI endpoint server fetching localized historical candlestick data with `yfinance` (`/api/candles`) and rendering `trade.db` operations dynamically through (`/api/trades`, `/api/stats`, and `/api/filters`).
- **Frontend (`src/tradingview_mcp/ui/static/`)**:
    - Includes `index.html`, `style.css` (premium dark mode aesthetics), and `app.js` (native vanilla JS with dynamic UI state handling).
    - Lightweight charts automatically pull historical candles and sequentially plot explicit **buy (green upward arrows)** and **sell (red downward arrows)** markers at their exact historical execution times.
    - Statistics Cards dynamically rerender their contents strictly based on the currently filtered strategy and ticker.

## 2. Running the UI Dashboard

It is highly recommended that you run the dashboard using **`uv run`**. This properly activates the isolated virtual environment managed by `uv`, ensuring no global python namespace collisions or `ModuleNotFoundError` issues occur for dependencies like `fastapi` and `yfinance`.

### To spin up the UI Dashboard locally:

1. Open a system terminal and navigate to the project's root directly:
   ```bash
   cd /Users/spaul11/Projects/tradingview-mcp
   ```

2. Run the dashboard launcher with `uv run`:
   ```bash
   uv run python -m tradingview_mcp.ui.launcher --open-browser
   ```

3. The launcher prints and opens the dashboard address. It starts at port 8000 and tries the next free port if
   another copy is already running, so several copies (e.g. one per git worktree) can run side by side.
   Set `PORT` or `--port N` to change the starting port, and `--strict-port` (or `PORT_STRICT=1`) to fail
   instead of moving to another port. The same selection applies to the MCP HTTP server
   (`uv run tradingview-mcp streamable-http`).

The dashboard's **Opportunity research** link opens an editable cross-stock watchlist scanner. It highlights current completed-bar buys and their historical long-trade outcomes. The displayed win rates are not calibrated probabilities; see [the scanner groundwork](docs/OPPORTUNITY_SCANNER.md) for its present limits.

### Yahoo Finance refresh schedule

The dashboard loads Yahoo Finance data when it first opens and whenever the ticker, strategy, or chart range changes. While the configured market session is open, it also refreshes the visible chart every 30 minutes. A header indicator shows whether the market is open and when automatic refresh will resume.

Edit `config/market_hours.json` to change the schedule:

- `timezone`, `open_time`, and `close_time` define the regular session.
- `weekdays` uses Python weekday numbers (`0` is Monday and `6` is Sunday).
- `refresh_minutes` controls the live dashboard interval.
- `holidays` accepts closed dates such as `"2026-12-25"`.
- `early_closes` maps a date to its close time, such as `"2026-11-27": "13:00"`.
- `yahoo_cache_seconds` prevents the dashboard's candle, trade, stats, and overlay requests from downloading the same Yahoo data repeatedly during one refresh.

The checked-in holiday and early-close dates cover the NYSE calendar through 2028 and should be updated when NYSE publishes later years. The `calendar_source` field records the official schedule used.

Set `MARKET_HOURS_CONFIG` to use a different JSON file. The schedule is reread by the server, so a restart is not normally required after editing it.

The scanner includes [Volume-Confirmed Price Breakout](docs/VOLUME_PRICE_BREAKOUT.md), which checks for a new price high with an unusually large price gain and volume surge. Its pending signals and earlier closed trades appear alongside the other supported strategies.

*(The server will stay active until manually killed with `Ctrl + C` in the shell).*
