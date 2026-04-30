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

2. Run the `server.py` file strictly wrapped in `uv run`:
   ```bash
   uv run python src/tradingview_mcp/ui/server.py
   ```

3. Open a browser and navigate to the local dashboard address:
   [http://127.0.0.1:8000](http://127.0.0.1:8000)

*(The server will stay active until manually killed with `Ctrl + C` in the shell).*
