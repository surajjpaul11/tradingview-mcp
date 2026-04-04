import sqlite3
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import yfinance as yf

# Import the existing DB queries so we don't rewrite code
from tradingview_mcp.core.services.trade_db import get_trade_history, get_pnl_summary, _get_db_path

app = FastAPI(title="TradingView MCP Trade Visualizer")

# Mount static directory directly
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the single page application."""
    html_file = static_path / "index.html"
    return html_file.read_text()

@app.get("/api/filters")
async def get_filters():
    """Returns available symbols and strategies dynamically from DB."""
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    symbols = [r["symbol"] for r in conn.execute("SELECT DISTINCT symbol FROM trades").fetchall()]
    strategies = [r["strategy"] for r in conn.execute("SELECT DISTINCT strategy FROM trades").fetchall()]
    conn.close()
    return {"symbols": symbols, "strategies": strategies}

@app.get("/api/trades")
async def api_trades(symbol: str, strategy: str = None):
    """Fetch the trade markers to overlay on the chart."""
    if strategy == "all" or not strategy:
        strategy = None
    trades = get_trade_history(symbol=symbol, strategy=strategy, limit=5000)
    return {"trades": trades}

@app.get("/api/stats")
async def api_stats(symbol: str, strategy: str = None):
    """Fetch summary stats (Win Rate, PnL) based on current filters."""
    if strategy == "all" or not strategy:
        strategy = None
    stats = get_pnl_summary(symbol=symbol, strategy=strategy)
    return stats

@app.get("/api/candles")
async def api_candles(symbol: str, timeframe: str = "1d"):
    """Fetch OHLCV data directly via yfinance since the lightweight chart needs long historical bounds."""
    # Yahoo Finance translation (BTC/USDT -> BTC-USD)
    yf_symbol = symbol.replace("/USDT", "-USD").replace("/USD", "-USD")
    
    ticker = yf.Ticker(yf_symbol)
    df = ticker.history(period="1y", interval=timeframe)
    
    candles = []
    # yfinance indices are datetime aware. Lightweight charts uses string "yyyy-mm-dd" or unix timestamp
    for date, row in df.iterrows():
        candles.append({
            "time": int(date.timestamp()),  # Unix timestamp for more precision 
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"])
        })
    return {"candles": candles}

if __name__ == "__main__":
    import uvicorn
    # Allow running with `uv run python src/tradingview_mcp/ui/server.py`
    uvicorn.run("tradingview_mcp.ui.server:app", host="127.0.0.1", port=8000, reload=True)
