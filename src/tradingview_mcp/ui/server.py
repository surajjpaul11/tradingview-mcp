import sqlite3
import asyncio
import json
import math
import os
import sys
import threading
import time
import uuid
import urllib.request
from functools import wraps
from contextvars import ContextVar
from pathlib import Path
from datetime import date as calendar_date, datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
import yfinance as yf

# Import existing DB queries and backtesting service
from tradingview_mcp.core.services.trade_db import get_trade_history, get_pnl_summary, _get_db_path, _get_connection, init_db
from tradingview_mcp.core.services.backtest_service import run_backtest, _STRATEGY_MAP
from tradingview_mcp.core.services.seed_backtests import seed_backtest_data, _format_iso_datetime
from tradingview_mcp.core.services.opportunity_service import DEFAULT_WATCHLIST, scan_opportunities
from tradingview_mcp.core.services.market_hours import (
    get_market_status,
    load_market_config,
    market_session_label,
    market_config_path,
    normalize_trading_window,
    timestamp_in_trading_window,
)

from tradingview_mcp.core.services.market_data_store import (
    Series, Download, History, MarketDataUnavailable, get_market_store, request_bounds, yahoo_request_bounds,
)

_history_context = ContextVar('history_context', default=None)


def history_endpoint(fn):
    """Run blocking provider/strategy work off the ASGI loop and report data provenance."""
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        costs = {k: kwargs[k] for k in ('commission_pct', 'slippage_pct') if kwargs.get(k) is not None}
        if any(not math.isfinite(v) or v < 0 for v in costs.values()):
            raise HTTPException(422, 'Commission and slippage must be finite and nonnegative')
        context = {'costs': costs, 'snapshot_id': kwargs.get('snapshot_id'), 'data_revision': kwargs.get('data_revision'),
                   'require_complete': fn.__name__ not in ('api_candles', 'api_chart_candles')}
        def run():
            token = _history_context.set(context)
            try:
                result = asyncio.run(fn(*args, **kwargs))
                if context.get('failure'):
                    raise context['failure']
                if isinstance(result, dict) and context.get('status'):
                    result['data_status'] = context['status']
                return result
            except Exception:
                if context.get('failure'):
                    raise context['failure']
                raise
            finally:
                _history_context.reset(token)
        try:
            return await asyncio.to_thread(run)
        except MarketDataUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': str(exc.retry_after)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return wrapped


def _engine_revision():
    import hashlib
    root = Path(__file__).resolve().parents[3]
    paths = [root / 'strategies/sloped_lines/sloped_lines_strategy.py',
             Path(__file__).resolve().parents[1] / 'core/services/backtest_service.py']
    return hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()


def _stored_history(series, start, end, fetch):
    context = _history_context.get()
    try:
        result = get_market_store().history(series, start, end, fetch,
            require_complete=context.get('require_complete', True) if context else True,
            revision=context.get('data_revision') if context else None,
            snapshot_id=context.get('snapshot_id') if context else None)
        if context is not None:
            context['status'] = result.status
            context['history'] = result
            context['series'] = series
        return result.candles
    except (MarketDataUnavailable, ValueError) as exc:
        if context is not None:
            context['failure'] = exc
        raise


app = FastAPI(title="TradingView MCP Trade Visualizer")

_market_config_lock = threading.Lock()

# Mount static directory directly
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

def _format_trade_candle_datetime(date_value, candles: list[dict], default_time: str) -> str:
    """Return the exact UTC candle time for an intraday backtest trade marker."""
    target = str(date_value or "").strip()
    for candle in candles:
        if str(candle.get("date", "")).strip() == target and candle.get("time") is not None:
            return datetime.fromtimestamp(int(candle["time"]), tz=timezone.utc).isoformat()
    return _format_iso_datetime(target, default_time)


def _ensure_seeded():
    """Ensure database has historical backtest trades loaded."""
    init_db()
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM trades WHERE mode = 'backtest'").fetchone()[0]
        existing_strats = {r[0] for r in conn.execute("SELECT DISTINCT strategy FROM trades WHERE mode = 'backtest'").fetchall()}
    except Exception:
        count = 0
        existing_strats = set()
    finally:
        conn.close()

    base_dir = Path(__file__).resolve().parents[3]
    strategies_dir = base_dir / "strategies"
    json_files = list(strategies_dir.rglob("*backtest*.json"))

    needs_seeding = (count == 0)
    if not needs_seeding and json_files:
        for jf in json_files:
            strat_name = jf.stem.split("_backtest_")[0]
            if strat_name and strat_name not in existing_strats:
                needs_seeding = True
                break

    if needs_seeding:
        seed_backtest_data()

def _save_backtest_trades(symbol: str, strategy: str, trade_log: list[dict]):
    """Persist newly generated backtest trades into trades.db."""
    conn = _get_connection()
    for t in trade_log:
        trade_id = str(uuid.uuid4())
        side_raw = (t.get("side") or "long").lower()
        side = "buy" if side_raw in ("long", "buy") else "sell"
        entry_price = float(t.get("entry_price", 0))
        exit_price = float(t.get("exit_price", entry_price))
        entry_date = str(t.get("entry_date", ""))
        exit_date = str(t.get("exit_date", entry_date))
        
        created_at = _format_iso_datetime(entry_date, "09:30:00")
        closed_at = _format_iso_datetime(exit_date, "16:00:00")
        
        capital_usd = 1000.0
        quantity = round(capital_usd / entry_price, 4) if entry_price > 0 else 1.0
        return_pct = float(t.get("return_pct", 0.0))
        pnl_usd = round((exit_price - entry_price) * quantity if side == "buy" else (entry_price - exit_price) * quantity, 2)
        
        try:
            conn.execute(
                """INSERT INTO trades
                   (trade_id, symbol, side, strategy, broker, quantity, entry_price,
                    capital_usd, mode, order_id, status, interval, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'backtest', ?, ?, ?, 'backtest', 'AUTO_BACKTEST',
                           'closed', '1d', ?, ?, ?)""",
                (trade_id, symbol.upper(), side, strategy.lower(), quantity, entry_price,
                 capital_usd, f"Auto-backtest {strategy}", created_at, closed_at)
            )
            conn.execute(
                """INSERT INTO trade_exits
                   (trade_id, exit_price, exit_reason, pnl_usd, pnl_pct, holding_seconds, fees_usd, closed_at)
                   VALUES (?, ?, ?, ?, ?, 86400, 3.0, ?)""",
                (trade_id, exit_price, str(t.get("exit_reason", "signal_exit")), pnl_usd, return_pct, closed_at)
            )
        except Exception as e:
            print(f"Error saving auto-backtest trade: {e}")
            
    conn.commit()
    conn.close()

@app.on_event("startup")
async def startup_event():
    _ensure_seeded()

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the single page application."""
    html_file = static_path / "index.html"
    return html_file.read_text()


@app.get("/charts", response_class=HTMLResponse)
async def read_charts():
    """Serve the independently built React multi-pane chart workspace."""
    html_file = static_path / "charts" / "index.html"
    if not html_file.exists():
        raise HTTPException(status_code=503, detail="Charts workspace is not built. Run npm run charts:build.")
    return html_file.read_text(encoding="utf-8")


@app.get("/opportunities", response_class=HTMLResponse)
async def read_opportunities():
    """Show the research-only, cross-stock signal scanner."""
    return (static_path / "opportunities.html").read_text()


@app.get("/api/opportunities")
async def api_opportunities(symbols: str = ",".join(DEFAULT_WATCHLIST)):
    """Scan completed daily bars without placing trades or asserting probabilities."""
    try:
        return await asyncio.to_thread(scan_opportunities, symbols.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/filters")
async def get_filters():
    """Returns available symbols and strategies dynamically from DB and strategy registry."""
    _ensure_seeded()
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db_symbols = [
        r["symbol"]
        for r in conn.execute(
            "SELECT DISTINCT symbol FROM trades WHERE symbol NOT IN ('PORTFOLIO', 'TOTAL') AND symbol NOT LIKE '%PORTFOLIO%'"
        ).fetchall()
    ]
    db_strategies = [r["strategy"] for r in conn.execute("SELECT DISTINCT strategy FROM trades").fetchall()]
    conn.close()
    
    # Merge with registry strategies
    all_strategies = sorted(list(set(db_strategies + list(_STRATEGY_MAP.keys()))))
    
    # Priority sort symbols: common first
    priority = ["AAPL", "SPY", "QQQ", "BTC-USD", "NVDA", "DIA", "GDX", "VXX"]
    symbols = sorted(db_symbols, key=lambda s: (priority.index(s) if s in priority else 99, s))
    
    return {"symbols": symbols, "strategies": all_strategies}


@app.get("/api/best-parameters")
@history_endpoint
async def api_best_parameters(strategy: str = None, symbol: str = None, capture_snapshot: bool = False):
    """Retrieve optimal strategy parameters and historical performance metrics."""
    from tradingview_mcp.core.services.strategy_config import load_best_parameters, get_best_parameters
    if strategy and symbol:
        cfg = get_best_parameters(strategy, symbol)
        if not cfg:
            return {"found": False, "strategy": strategy, "symbol": symbol, "data": None}
        cfg = dict(cfg)
        preset_record = dict(cfg)
        store = get_market_store()
        run = store.saved_run(cfg, strategy, symbol)
        if capture_snapshot and not run:
            window = cfg.get('backtest_window') or {}
            tf, period = cfg.get('timeframe', '1d'), cfg.get('period', '1y')
            if not window.get('start_date') or not window.get('end_date'):
                a, b = request_bounds(period)
                window = {'start_date': datetime.fromtimestamp(a, timezone.utc).date().isoformat(),
                          'end_date': datetime.fromtimestamp(b - 1, timezone.utc).date().isoformat(),
                          'trading_window': 'regular market'}
            source = cfg.get('source', 'yahoo')
            session = window.get('trading_window', 'regular market') if source == 'yahoo' else '24/7'
            candles, _, _ = fetch_backtest_candles(source, symbol, tf, period, session, window['start_date'], window['end_date'])
            context = _history_context.get()
            start, end = request_bounds(period, window['start_date'], window['end_date'])
            history = context['history']
            snapshot_id = store.save_snapshot(context['series'], start, end, history, origin='reconstructed',
                                             provenance={'legacy_record': cfg, 'data_status': history.status})
            observed = {}
            if strategy == 'sloped_lines':
                strategy_dir = Path(__file__).resolve().parents[3] / 'strategies' / 'sloped_lines'
                if str(strategy_dir) not in sys.path:
                    sys.path.insert(0, str(strategy_dir))
                from sloped_lines_strategy import run_backtest as run_sl_backtest
                observed = run_sl_backtest(symbol=symbol, period=period, interval=tf, candles=candles, **{**cfg.get('parameters', {}), **cfg.get('costs', {})})
                observed = {k: v for k, v in observed.items() if k not in ('trade_log', 'equity_curve', 'candles', 'trendlines')}
            store.bind_saved_run(preset_record, strategy, symbol, snapshot_id, engine_revision=_engine_revision(), observed=observed,
                                 costs=cfg.get('costs') or {'commission_pct': 0.1, 'slippage_pct': 0.05})
            run = store.saved_run(cfg, strategy, symbol)
        if run:
            if not cfg.get('backtest_window'):
                cfg['backtest_window'] = {
                    'start_date': datetime.fromtimestamp(run['snapshot_start'], timezone.utc).date().isoformat(),
                    'end_date': datetime.fromtimestamp(run['snapshot_end'] - 1, timezone.utc).date().isoformat(),
                    'trading_window': json.loads(run['series_identity'])[3]}
            cfg['snapshot_id'] = run['snapshot_id']
            cfg['snapshot_origin'] = run['origin']
            cfg['snapshot_engine_revision'] = run['engine_revision']
            cfg['engine_changed'] = run['engine_revision'] != _engine_revision()
            cfg['snapshot_observed'] = json.loads(run['observed'])
        return {"found": True, "strategy": strategy, "symbol": symbol, "data": cfg}
    return load_best_parameters()


@app.get("/api/market-status")
async def api_market_status(trading_window: str = None):
    """Return the configured market session and automatic refresh state."""
    try:
        return get_market_status(trading_window=trading_window)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=500, detail=f"Invalid market-hours configuration: {exc}") from exc


@app.post("/api/trading-window")
async def api_set_trading_window(trading_window: str):
    """Persist the dashboard's selected trading window as the server default."""
    try:
        with _market_config_lock:
            config = load_market_config()
            selected_window = normalize_trading_window(trading_window, config)
            config["active_trading_window"] = selected_window
            config_path = market_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        return get_market_status(config=config, trading_window=selected_window)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def validate_backtest_window(start_date=None, end_date=None):
    """Captured windows use inclusive market dates, with both bounds required."""
    if start_date is None and end_date is None:
        return
    try:
        start = calendar_date.fromisoformat(start_date)
        end = calendar_date.fromisoformat(end_date)
        if start > end:
            raise ValueError("start_date must be on or before end_date")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Provide both start_date and end_date as YYYY-MM-DD, in chronological order") from exc


def _download_market_candles(yf_symbol: str, timeframe: str = "1d", period: str = "1y", trading_window: str = None, start_date: str = None, end_date: str = None) -> tuple[list[dict], str, str]:
    """
    Fetch OHLCV candles via yfinance with automatic range clamping & resampling:
      - 30m: max 60d
      - 1h, 4h, 12h: max 2y
      - 12h: resampled from 1h
      - 1d, 5d: up to max
    Returns (candles, actual_timeframe, actual_period)
    """
    import math
    validate_backtest_window(start_date, end_date)
    tf = timeframe.lower().strip()
    if tf in ("daily", "1day"):
        tf = "1d"
    elif tf in ("weekly", "1week"):
        tf = "5d"
    elif tf in ("hourly", "60m"):
        tf = "1h"

    req_period = period.lower().strip()
    actual_period = req_period

    if tf == "30m" and req_period in ("3mo", "6mo", "1y", "2y", "5y", "max"):
        actual_period = "60d"
    elif tf in ("1h", "4h", "12h") and req_period in ("5y", "max"):
        actual_period = "2y"

    fetch_tf = "1h" if tf in ("4h", "12h") else tf

    market_config = load_market_config()
    selected_window = normalize_trading_window(trading_window, market_config)
    candles = []
    try:
        ticker = yf.Ticker(yf_symbol)
        include_extended_hours = selected_window != "regular market"
        if start_date:
            # Yahoo end is exclusive; UI captured dates are inclusive.
            exclusive_end = (calendar_date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
            df = ticker.history(start=start_date, end=exclusive_end, interval=fetch_tf, prepost=include_extended_hours, auto_adjust=True)
        else:
            df = ticker.history(period=actual_period, interval=fetch_tf, prepost=include_extended_hours, auto_adjust=True)
        if df is not None and not df.empty:
            if tf in ("4h", "12h"):
                df = df.resample(tf).agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()

            fmt = "%Y-%m-%d %H:%M" if tf in ("30m", "1h", "4h", "12h") else "%Y-%m-%d"
            for date, row in df.iterrows():
                if start_date and not (start_date <= date.strftime("%Y-%m-%d") <= end_date):
                    continue
                if tf in ("30m", "1h", "4h", "12h"):
                    candle_time = date.to_pydatetime() if hasattr(date, "to_pydatetime") else date
                    if not timestamp_in_trading_window(candle_time, selected_window, market_config):
                        continue
                o = float(row["Open"])
                h = float(row["High"])
                l = float(row["Low"])
                c = float(row["Close"])
                v = float(row.get("Volume", 0.0))
                if any(math.isnan(x) for x in (o, h, l, c)):
                    continue
                candles.append({
                    "time": int(date.timestamp()),
                    "exchange_timezone": str(getattr(date, "tzinfo", None) or "UTC"),
                    "date": date.strftime(fmt),
                    "open": round(o, 4),
                    "high": round(h, 4),
                    "low": round(l, 4),
                    "close": round(c, 4),
                    "volume": round(v, 2),
                    "session": market_session_label(candle_time, market_config) if tf in ("30m", "1h", "4h", "12h") else "regular market",
                })
    except Exception:
        raise

    if not candles:
        raise MarketDataUnavailable(f"Yahoo returned no usable candles for {yf_symbol}; it may be rate limited or the requested window has no data")
    return candles, tf, actual_period


def _closed_yahoo_window(symbol, start, end):
    # Only apply the configured US holiday calendar to US equities. Crypto and
    # international symbols must retain their own provider/calendar behavior.
    if symbol.upper().endswith('-USD') or '.' in symbol or '=' in symbol or (symbol.startswith('^') and symbol not in {'^GSPC','^VIX','^DJI','^IXIC','^RUT'}):
        return False
    config = load_market_config()
    day = datetime.fromtimestamp(start, timezone.utc).date()
    last = datetime.fromtimestamp(end - 1, timezone.utc).date()
    if (last - day).days > 10:
        return False
    holidays = set(config.get('holidays', []))
    while day <= last:
        if day.weekday() in config['weekdays'] and day.isoformat() not in holidays:
            return False
        day += timedelta(days=1)
    return True


def fetch_market_candles(yf_symbol: str, timeframe: str = "1d", period: str = "1y", trading_window: str = None, start_date: str = None, end_date: str = None):
    validate_backtest_window(start_date, end_date)
    tf = {'daily': '1d', '1day': '1d', 'weekly': '5d', '1week': '5d', 'hourly': '1h', '60m': '1h'}.get(timeframe.lower().strip(), timeframe.lower().strip())
    actual_period = period.lower().strip()
    if tf == '30m' and actual_period in ('3mo', '6mo', '1y', '2y', '5y', 'max'):
        actual_period = '60d'
    elif tf in ('1h', '4h', '12h') and actual_period in ('5y', 'max'):
        actual_period = '2y'
    session = normalize_trading_window(trading_window, load_market_config())
    start, end = yahoo_request_bounds(yf_symbol, actual_period, session, start_date, end_date)
    series = Series('yahoo', yf_symbol.upper(), tf, session, 'adjusted')
    def download(a, b):
        # Closed sessions are successful empty coverage, not provider failures.
        if _closed_yahoo_window(yf_symbol, a, b):
            return Download([], allow_empty=True)
        first = datetime.fromtimestamp(a, timezone.utc).date().isoformat()
        last = datetime.fromtimestamp(b - 1, timezone.utc).date().isoformat()
        return _download_market_candles(yf_symbol, tf, actual_period, session, first, last)[0]
    return _stored_history(series, start, end, download), tf, actual_period


_HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
_PERIOD_SECONDS = {
    "1d": 86_400, "5d": 5 * 86_400, "1mo": 30 * 86_400,
    "3mo": 90 * 86_400, "6mo": 180 * 86_400, "1y": 365 * 86_400,
    "2y": 2 * 365 * 86_400, "5y": 5 * 365 * 86_400,
}


def _aggregate_candles(candles: list[dict], seconds: int) -> list[dict]:
    """Aggregate normalized OHLCV candles into deterministic UTC buckets."""
    buckets: dict[int, dict] = {}
    for candle in sorted(candles, key=lambda item: item["time"]):
        bucket_time = int(candle["time"]) // seconds * seconds
        bucket = buckets.get(bucket_time)
        if bucket is None:
            buckets[bucket_time] = {
                "time": bucket_time,
                "date": datetime.fromtimestamp(bucket_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "open": candle["open"], "high": candle["high"], "low": candle["low"],
                "close": candle["close"], "volume": candle.get("volume", 0.0),
                "session": "24/7",
            }
        else:
            bucket["high"] = max(bucket["high"], candle["high"])
            bucket["low"] = min(bucket["low"], candle["low"])
            bucket["close"] = candle["close"]
            bucket["volume"] += candle.get("volume", 0.0)
    return list(buckets.values())


def _download_hyperliquid_candles(coin: str, timeframe: str = "1m", period: str = "1d", range_start=None, range_end=None) -> tuple[list[dict], str, str]:
    """Fetch normalized Hyperliquid candle history using candleSnapshot."""
    tf = timeframe.lower().strip()
    requested_period = period.lower().strip()
    base_tf = "1d" if tf == "5d" else tf
    supported = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d"}
    if base_tf not in supported:
        raise ValueError(f"Unsupported Hyperliquid timeframe: {timeframe}")
    end_ms = int(time.time() * 1000)
    seconds = _PERIOD_SECONDS.get(requested_period)
    start_ms = 0 if seconds is None else end_ms - seconds * 1000
    if range_start is not None:
        start_ms, end_ms = range_start * 1000, range_end * 1000 - 1
    payload = json.dumps({
        "type": "candleSnapshot",
        "req": {"coin": coin.upper(), "interval": base_tf, "startTime": start_ms, "endTime": end_ms},
    }).encode("utf-8")
    request = urllib.request.Request(
        _HYPERLIQUID_INFO_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "tradingview-mcp/0.7"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = json.loads(response.read().decode("utf-8"))
    candles = []
    for item in raw:
        try:
            timestamp = int(item.get("t", item.get("T", 0))) // 1000
            candles.append({
                "time": timestamp,
                "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "open": float(item["o"]), "high": float(item["h"]),
                "low": float(item["l"]), "close": float(item["c"]),
                "volume": float(item.get("v", 0.0)), "session": "24/7",
            })
        except (KeyError, TypeError, ValueError):
            continue
    deduped = {candle["time"]: candle for candle in candles}
    normalized = [deduped[key] for key in sorted(deduped)]
    if tf == "5d":
        normalized = _aggregate_candles(normalized, 5 * 86_400)
    return normalized, tf, requested_period


def fetch_hyperliquid_candles(coin: str, timeframe: str = '1m', period: str = '1d', start_date=None, end_date=None):
    tf, period = timeframe.lower().strip(), period.lower().strip()
    validate_backtest_window(start_date, end_date)
    start, end = request_bounds(period, start_date, end_date)
    series = Series('hyperliquid', coin.upper(), tf, '24/7', 'raw', 'UTC')
    def download(a, b):
        rows = _download_hyperliquid_candles(coin, tf, period, a, b)[0]
        # Hyperliquid retains approximately the most recent 5000 base candles.
        # Never label a truncated multi-year minute query as a complete backtest.
        base_seconds = 86400 if tf == '5d' else int(tf[:-1]) * {'m': 60, 'h': 3600, 'd': 86400}[tf[-1]]
        limited = rows and rows[0]['time'] > a + base_seconds and len(rows) >= (990 if tf == '5d' else 4990)
        return Download(rows, 'Provider retention limit' if limited else None,
                        coverage_start=rows[0]['time'] if limited else None)
    return _stored_history(series, start, end, download), tf, period


def fetch_source_candles(source: str, symbol: str, timeframe: str, period: str, trading_window: str = None):
    """Dispatch a normalized candle request without changing legacy Yahoo defaults."""
    selected_source = (source or "yahoo").lower().strip()
    if selected_source == "hyperliquid":
        return fetch_hyperliquid_candles(symbol, timeframe, period)
    if selected_source != "yahoo":
        raise ValueError(f"Unsupported chart source: {source}")
    return fetch_market_candles(symbol, timeframe, period, trading_window)


def fetch_backtest_candles(source, symbol, timeframe, period, trading_window=None, start_date=None, end_date=None):
    validate_backtest_window(start_date, end_date)
    if not start_date:
        return fetch_source_candles(source, symbol, timeframe, period, trading_window)
    if (source or "yahoo").lower() == "hyperliquid":
        return fetch_hyperliquid_candles(symbol, timeframe, period, start_date, end_date)
    return fetch_market_candles(symbol, timeframe, period, trading_window, start_date, end_date)


_SLOPED_PIVOT_LOOKBACK_OPTIONS = {2, 3, 4, 5, 6, 7, 8, 10}
_SLOPED_ANCHOR_SOURCE_OPTIONS = {"confirmed_pivots", "any_valid_candle"}
_SLOPED_VALIDATION_BOUNDARY_OPTIONS = {"body", "close", "wick"}
_SLOPED_TOLERANCE_OPTIONS = {0.0, 0.005, 0.01, 0.015, 0.02}
_SLOPED_REENTRY_MODE_OPTIONS = {"none", "any", "any_two", "any_three", "all"}


def _resolve_sloped_params(symbol: str, full_candle=None, use_wick=None, confirm_candles=None, pivot_lookback=None, inverse_color_trigger=None, line_angle=None, stop_loss_mode=None, min_anchor_bars=None, anchor_source=None, validation_boundary=None, trendline_tolerance=None, gap_up=None, gap_down=None, staggered_lines=None, reentry_mode=None, reentry_rsi=None, reentry_ema=None, reentry_price_breakout=None, reentry_volume=None, line_breakout_buy=None, entry_barrier_sell=None, compounding=None, initial_capital=None, peak_reclaim_full_candle=None):
    from tradingview_mcp.core.services.strategy_config import get_best_parameters
    cfg = get_best_parameters("sloped_lines", symbol)
    bp = (cfg or {}).get("parameters", {})
    selected_pivot_lookback = pivot_lookback if pivot_lookback is not None else bp.get("pivot_lookback", 5)
    selected_pivot_lookback = int(selected_pivot_lookback)
    if selected_pivot_lookback not in _SLOPED_PIVOT_LOOKBACK_OPTIONS:
        raise ValueError(f"pivot_lookback must be one of {sorted(_SLOPED_PIVOT_LOOKBACK_OPTIONS)}")
    selected_anchor_source = anchor_source or bp.get("anchor_source", "confirmed_pivots")
    if selected_anchor_source not in _SLOPED_ANCHOR_SOURCE_OPTIONS:
        raise ValueError(f"anchor_source must be one of {sorted(_SLOPED_ANCHOR_SOURCE_OPTIONS)}")
    selected_validation_boundary = validation_boundary or bp.get("validation_boundary", "body")
    if selected_validation_boundary not in _SLOPED_VALIDATION_BOUNDARY_OPTIONS:
        raise ValueError(f"validation_boundary must be one of {sorted(_SLOPED_VALIDATION_BOUNDARY_OPTIONS)}")
    selected_tolerance = float(
        trendline_tolerance if trendline_tolerance is not None else bp.get("trendline_tolerance", 0.0)
    )
    if selected_tolerance not in _SLOPED_TOLERANCE_OPTIONS:
        raise ValueError(f"trendline_tolerance must be one of {sorted(_SLOPED_TOLERANCE_OPTIONS)}")
    selected_reentry_mode = reentry_mode or bp.get("reentry_mode", "none")
    if selected_reentry_mode not in _SLOPED_REENTRY_MODE_OPTIONS:
        raise ValueError(f"reentry_mode must be one of {sorted(_SLOPED_REENTRY_MODE_OPTIONS)}")
    selected_capital = float(initial_capital if initial_capital is not None else bp.get("initial_capital", 10000.0))
    if not math.isfinite(selected_capital) or selected_capital <= 0:
        raise HTTPException(status_code=422, detail="initial_capital must be finite and greater than zero")
    return {
        **((_history_context.get() or {}).get("costs", {})),
        "peak_reclaim_full_candle": peak_reclaim_full_candle if peak_reclaim_full_candle is not None else bp.get("peak_reclaim_full_candle", False),
        "compounding": compounding if compounding is not None else bp.get("compounding", True),
        "initial_capital": selected_capital,
        "full_candle": full_candle if full_candle is not None else bp.get("full_candle", False),
        "use_wick": use_wick if use_wick is not None else bp.get("use_wick", False),
        "confirm_candles": confirm_candles if confirm_candles is not None else bp.get("confirm_candles", 0),
        "pivot_lookback": selected_pivot_lookback,
        "anchor_source": selected_anchor_source,
        "validation_boundary": selected_validation_boundary,
        "trendline_tolerance": selected_tolerance,
        "inverse_color_trigger": inverse_color_trigger if inverse_color_trigger is not None else bp.get("inverse_color_trigger", False),
        "line_angle": line_angle if line_angle is not None else bp.get("line_angle", 3.0),
        "stop_loss_mode": stop_loss_mode if stop_loss_mode is not None else bp.get("stop_loss_mode", "exit_peak_reclaim"),
        "min_anchor_bars": min_anchor_bars if min_anchor_bars is not None else bp.get("min_anchor_bars", 2),
        "gap_up": gap_up if gap_up is not None else bp.get("gap_up", False),
        "gap_down": gap_down if gap_down is not None else bp.get("gap_down", False),
        "line_breakout_buy": line_breakout_buy if line_breakout_buy is not None else bp.get("line_breakout_buy", False),
        "entry_barrier_sell": entry_barrier_sell if entry_barrier_sell is not None else bp.get("entry_barrier_sell", False),
        "staggered_lines": staggered_lines if staggered_lines is not None else bp.get("staggered_lines", False),
        "reentry_mode": selected_reentry_mode,
        "reentry_rsi": reentry_rsi if reentry_rsi is not None else bp.get("reentry_rsi", False),
        "reentry_ema": reentry_ema if reentry_ema is not None else bp.get("reentry_ema", False),
        "reentry_price_breakout": reentry_price_breakout if reentry_price_breakout is not None else bp.get("reentry_price_breakout", False),
        "reentry_volume": reentry_volume if reentry_volume is not None else bp.get("reentry_volume", False),
    }


@app.get("/api/trades")
@history_endpoint
async def api_trades(symbol: str, source: str = "yahoo", strategy: str = None, timeframe: str = "1d", period: str = "1y", trading_window: str = None, channel_mult: float = None, lookback: int = None, use_stop_loss: bool = True, midline_reentry: bool = False, midline_cross: bool = False, lower_reclaim: bool = True, channel_inflection: bool = True, channel_curl_mode: str = "both", full_candle: bool = None, use_wick: bool = None, confirm_candles: int = None, pivot_lookback: int = None, inverse_color_trigger: bool = None, line_angle: float = None, stop_loss_mode: str = None, min_anchor_bars: int = None, anchor_source: str = None, validation_boundary: str = None, trendline_tolerance: float = None, gap_up: bool = None, gap_down: bool = None, staggered_lines: bool = None, reentry_mode: str = None, reentry_rsi: bool = None, reentry_ema: bool = None, reentry_price_breakout: bool = None, reentry_volume: bool = None, line_breakout_buy: bool = None, entry_barrier_sell: bool = None, start_date: str = None, end_date: str = None, compounding: bool = None, initial_capital: float = None, peak_reclaim_full_candle: bool = None, snapshot_id: str = None, data_revision: str = None, commission_pct: float = None, slippage_pct: float = None):
    """Fetch the trade markers to overlay on the chart, auto-generating on demand if needed."""
    if initial_capital is not None and (not math.isfinite(initial_capital) or initial_capital <= 0):
        raise HTTPException(status_code=422, detail="initial_capital must be finite and greater than zero")
    validate_backtest_window(start_date, end_date)
    if strategy == "all" or not strategy:
        strategy = None

    if strategy in ("sloped_lines", "slope_lines"):
        try:
            base_dir = Path(__file__).resolve().parents[3]
            strategy_dir = base_dir / "strategies" / "sloped_lines"
            if str(strategy_dir) not in sys.path:
                sys.path.insert(0, str(strategy_dir))
            from sloped_lines_strategy import run_backtest as run_sl_backtest

            clean_sym = symbol.strip().upper()
            if clean_sym in ("PORTFOLIO", "TOTAL"):
                clean_sym = "SPY"
            yf_sym = clean_sym.replace("/USDT", "-USD").replace("/USD", "-USD").replace("_USDT", "-USD").replace("_USD", "-USD").replace("/", "-").replace("_", "-")
            candles, actual_tf, actual_period = fetch_backtest_candles(source, clean_sym if source == "hyperliquid" else yf_sym, timeframe, period, trading_window, start_date, end_date)

            p = _resolve_sloped_params(clean_sym, full_candle, use_wick, confirm_candles, pivot_lookback, inverse_color_trigger, line_angle, stop_loss_mode, min_anchor_bars, anchor_source, validation_boundary, trendline_tolerance, gap_up, gap_down, staggered_lines, reentry_mode, reentry_rsi, reentry_ema, reentry_price_breakout, reentry_volume, line_breakout_buy, entry_barrier_sell, compounding, initial_capital, peak_reclaim_full_candle)
            res = run_sl_backtest(symbol=clean_sym, period=actual_period, interval=actual_tf, candles=candles, **p)
            trades = []
            for t in res.get("trade_log", []):
                entry_d = t.get("entry_date", "")
                exit_d = t.get("exit_date", "")
                created_at = _format_trade_candle_datetime(entry_d, candles, "09:30:00")
                closed_at = _format_trade_candle_datetime(exit_d, candles, "16:00:00") if exit_d else None
                entry_p = float(t.get("entry_price", 0))
                exit_p = float(t.get("exit_price", entry_p)) if exit_d else None
                ret_pct = float(t.get("return_pct", 0.0))
                side_raw = (t.get("side") or "long").lower()
                side = "buy" if side_raw in ("long", "buy") else "sell"
                trades.append({
                    "trade_id": str(uuid.uuid4()),
                    "symbol": clean_sym,
                    "side": side,
                    "strategy": "sloped_lines",
                    "status": "closed" if exit_d else "open",
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "exit_reason": t.get("exit_reason", ""),
                    "entry_reason": t.get("entry_reason", "breakout"),
                    "entry_signals": t.get("entry_signals", []),
                    "signal_date": t.get("signal_date"),
                    "quantity": t.get("quantity"),
                    "position_value": t.get("position_value"),
                    "balance_before": t.get("balance_before"),
                    "balance_after": t.get("balance_after"),
                    "costs_usd": t.get("costs_usd"),
                    "pnl_usd": t.get("pnl_usd", 0.0),
                    "pnl_pct": ret_pct,
                    "created_at": created_at,
                    "closed_at": closed_at,
                })
            return {"trades": trades, "timeframe": actual_tf, "period": actual_period}
        except Exception as e:
            print(f"On-the-fly sloped_lines trades error for {symbol}: {e}")

    # If enhanced_channel with custom parameters is requested, recalculate on the fly!
    if strategy == "enhanced_channel":
        ec_kwargs = {}
        if channel_mult is not None and channel_mult > 0:
            ec_kwargs["channel_mult"] = channel_mult
        if lookback is not None and lookback > 0:
            ec_kwargs["tactical_lookback"] = lookback
        if use_stop_loss is not None:
            ec_kwargs["use_stop_loss"] = use_stop_loss
        is_mid_cross = midline_cross or midline_reentry
        if is_mid_cross is not None:
            ec_kwargs["midline_cross"] = is_mid_cross
            ec_kwargs["midline_reentry"] = is_mid_cross
        if lower_reclaim is not None:
            ec_kwargs["lower_reclaim"] = lower_reclaim
        if channel_curl_mode is not None:
            ec_kwargs["channel_curl_mode"] = channel_curl_mode
        elif channel_inflection is not None:
            ec_kwargs["channel_inflection"] = channel_inflection

        if ec_kwargs:
            try:
                base_dir = Path(__file__).resolve().parents[3]
                strategy_dir = base_dir / "strategies" / "enhanced_channel"
                if str(strategy_dir) not in sys.path:
                    sys.path.insert(0, str(strategy_dir))
                from enhanced_channel_strategy import run_backtest as run_ec_backtest

                clean_sym = symbol.strip().upper()
                if clean_sym in ("PORTFOLIO", "TOTAL"):
                    clean_sym = "SPY"
                yf_sym = clean_sym.replace("/USDT", "-USD").replace("/USD", "-USD").replace("_USDT", "-USD").replace("_USD", "-USD").replace("/", "-").replace("_", "-")
                candles, actual_tf, actual_period = fetch_backtest_candles(source, clean_sym if source == "hyperliquid" else yf_sym, timeframe, period, trading_window, start_date, end_date)
                res = run_ec_backtest(
                    symbol=clean_sym,
                    period=actual_period,
                    interval=actual_tf,
                    candles=candles,
                    **ec_kwargs,
                )
                trades = []
                for t in res.get("trade_log", []):
                    entry_d = t.get("entry_date", "")
                    exit_d = t.get("exit_date", "")
                    created_at = _format_iso_datetime(entry_d, "09:30:00")
                    closed_at = _format_iso_datetime(exit_d, "16:00:00") if exit_d else None
                    entry_p = float(t.get("entry_price", 0))
                    exit_p = float(t.get("exit_price", entry_p)) if exit_d else None
                    ret_pct = float(t.get("return_pct", 0.0))
                    side_raw = (t.get("side") or "long").lower()
                    side = "buy" if side_raw in ("long", "buy") else "sell"
                    pnl_u = round((exit_p - entry_p) * (1000.0 / entry_p), 2) if (exit_p and entry_p > 0) else 0.0
                    trades.append({
                        "trade_id": str(uuid.uuid4()),
                        "symbol": clean_sym,
                        "side": side,
                        "strategy": "enhanced_channel",
                        "status": "closed" if exit_d else "open",
                        "entry_price": entry_p,
                        "exit_price": exit_p,
                        "exit_reason": t.get("exit_reason", ""),
                        "entry_reason": t.get("entry_reason", ""),
                        "pnl_usd": pnl_u,
                        "pnl_pct": ret_pct,
                        "created_at": created_at,
                        "closed_at": closed_at,
                    })
                return {"trades": trades, "timeframe": actual_tf, "period": actual_period}
            except Exception as e:
                print(f"On-the-fly enhanced_channel trades error: {e}")

    trades = get_trade_history(symbol=symbol, strategy=strategy, limit=5000)
    if not trades:
        # Try alternate symbol formats (e.g. BTC_USD vs BTC-USD)
        alt_sym = symbol.replace("-", "_") if "-" in symbol else symbol.replace("_", "-")
        trades = get_trade_history(symbol=alt_sym, strategy=strategy, limit=5000)
    
    # If no trades found for a specific strategy, run a backtest on the fly!
    if not trades and strategy and strategy in _STRATEGY_MAP:
        try:
            res = run_backtest(symbol=symbol, strategy=strategy, period="2y", include_trade_log=True)
            if res and "trade_log" in res and res["trade_log"]:
                _save_backtest_trades(symbol, strategy, res["trade_log"])
                trades = get_trade_history(symbol=symbol, strategy=strategy, limit=5000)
        except Exception as e:
            print(f"On-the-fly backtest error for {symbol} {strategy}: {e}")
            
    return {"trades": trades}

@app.get("/api/stats")
@history_endpoint
async def api_stats(symbol: str = "PORTFOLIO", source: str = "yahoo", strategy: str = None, timeframe: str = "1d", period: str = "1y", trading_window: str = None, channel_mult: float = None, lookback: int = None, use_stop_loss: bool = True, midline_reentry: bool = False, midline_cross: bool = False, lower_reclaim: bool = True, channel_inflection: bool = True, channel_curl_mode: str = "both", full_candle: bool = None, use_wick: bool = None, confirm_candles: int = None, pivot_lookback: int = None, inverse_color_trigger: bool = None, line_angle: float = None, stop_loss_mode: str = None, min_anchor_bars: int = None, anchor_source: str = None, validation_boundary: str = None, trendline_tolerance: float = None, gap_up: bool = None, gap_down: bool = None, staggered_lines: bool = None, reentry_mode: str = None, reentry_rsi: bool = None, reentry_ema: bool = None, reentry_price_breakout: bool = None, reentry_volume: bool = None, line_breakout_buy: bool = None, entry_barrier_sell: bool = None, start_date: str = None, end_date: str = None, compounding: bool = None, initial_capital: float = None, peak_reclaim_full_candle: bool = None, snapshot_id: str = None, data_revision: str = None, commission_pct: float = None, slippage_pct: float = None):
    """Fetch summary stats (Win Rate, PnL) based on current filters."""
    if initial_capital is not None and (not math.isfinite(initial_capital) or initial_capital <= 0):
        raise HTTPException(status_code=422, detail="initial_capital must be finite and greater than zero")
    validate_backtest_window(start_date, end_date)
    if strategy == "all" or not strategy:
        strategy = None

    if strategy in ("sloped_lines", "slope_lines"):
        try:
            base_dir = Path(__file__).resolve().parents[3]
            strategy_dir = base_dir / "strategies" / "sloped_lines"
            if str(strategy_dir) not in sys.path:
                sys.path.insert(0, str(strategy_dir))
            from sloped_lines_strategy import run_backtest as run_sl_backtest

            clean_sym = symbol.strip().upper()
            if clean_sym in ("PORTFOLIO", "TOTAL"):
                clean_sym = "SPY"
            yf_sym = clean_sym.replace("/USDT", "-USD").replace("/USD", "-USD").replace("_USDT", "-USD").replace("_USD", "-USD").replace("/", "-").replace("_", "-")
            candles, actual_tf, actual_period = fetch_backtest_candles(source, clean_sym if source == "hyperliquid" else yf_sym, timeframe, period, trading_window, start_date, end_date)

            p = _resolve_sloped_params(clean_sym, full_candle, use_wick, confirm_candles, pivot_lookback, inverse_color_trigger, line_angle, stop_loss_mode, min_anchor_bars, anchor_source, validation_boundary, trendline_tolerance, gap_up, gap_down, staggered_lines, reentry_mode, reentry_rsi, reentry_ema, reentry_price_breakout, reentry_volume, line_breakout_buy, entry_barrier_sell, compounding, initial_capital, peak_reclaim_full_candle)
            res = run_sl_backtest(symbol=clean_sym, period=actual_period, interval=actual_tf, candles=candles, **p)
            tot_trades = res.get("total_trades", 0)
            tot_pnl_usd = round(res.get("final_capital", p["initial_capital"]) - p["initial_capital"], 2)
            wr = res.get("win_rate_pct", 0.0)
            return {
                "total_trades": tot_trades,
                "total_pnl_usd": tot_pnl_usd,
                "initial_capital": res.get("initial_capital", p["initial_capital"]),
                "final_capital": res.get("final_capital", p["initial_capital"]),
                "compounding": p["compounding"],
                "total_pnl_pct": res.get("total_return_pct", 0.0),
                "buy_and_hold_pct": res.get("buy_and_hold_return_pct", 0.0),
                "win_rate_pct": wr,
                "winning_trades": int(tot_trades * (wr / 100.0)),
                "losing_trades": tot_trades - int(tot_trades * (wr / 100.0)),
                "filters": {"strategy": "sloped_lines", "symbol": clean_sym, **p,
                            "timeframe": actual_tf, "period": actual_period},
            }
        except Exception as e:
            print(f"On-the-fly sloped_lines stats error for {symbol}: {e}")

    # If enhanced_channel with custom parameters is requested, recalculate stats on the fly!
    if strategy == "enhanced_channel":
        ec_kwargs = {}
        if channel_mult is not None and channel_mult > 0:
            ec_kwargs["channel_mult"] = channel_mult
        if lookback is not None and lookback > 0:
            ec_kwargs["tactical_lookback"] = lookback
        if use_stop_loss is not None:
            ec_kwargs["use_stop_loss"] = use_stop_loss
        is_mid_cross = midline_cross or midline_reentry
        if is_mid_cross is not None:
            ec_kwargs["midline_cross"] = is_mid_cross
            ec_kwargs["midline_reentry"] = is_mid_cross
        if lower_reclaim is not None:
            ec_kwargs["lower_reclaim"] = lower_reclaim
        if channel_curl_mode is not None:
            ec_kwargs["channel_curl_mode"] = channel_curl_mode
        elif channel_inflection is not None:
            ec_kwargs["channel_inflection"] = channel_inflection

        try:
            base_dir = Path(__file__).resolve().parents[3]
            strategy_dir = base_dir / "strategies" / "enhanced_channel"
            if str(strategy_dir) not in sys.path:
                sys.path.insert(0, str(strategy_dir))
            from enhanced_channel_strategy import run_backtest as run_ec_backtest

            clean_sym = symbol.strip().upper()
            if clean_sym in ("PORTFOLIO", "TOTAL"):
                clean_sym = "SPY"
            yf_sym = clean_sym.replace("/USDT", "-USD").replace("/USD", "-USD").replace("_USDT", "-USD").replace("_USD", "-USD").replace("/", "-").replace("_", "-")
            candles, actual_tf, actual_period = fetch_backtest_candles(source, clean_sym if source == "hyperliquid" else yf_sym, timeframe, period, trading_window, start_date, end_date)

            res = run_ec_backtest(
                symbol=clean_sym,
                period=actual_period,
                interval=actual_tf,
                candles=candles,
                **ec_kwargs,
            )
            tot_trades = res.get("total_trades", 0)
            tot_pnl_usd = round(res.get("final_capital", 10000.0) - 10000.0, 2)
            wr = res.get("win_rate_pct", 0.0)
            return {
                "total_trades": tot_trades,
                "total_pnl_usd": tot_pnl_usd,
                "total_pnl_pct": res.get("total_return_pct", 0.0),
                "buy_and_hold_pct": res.get("buy_and_hold_return_pct", 0.0),
                "win_rate_pct": wr,
                "winning_trades": int(tot_trades * (wr / 100.0)),
                "losing_trades": tot_trades - int(tot_trades * (wr / 100.0)),
                "filters": {
                    "strategy": "enhanced_channel",
                    "symbol": clean_sym,
                    "channel_mult": ec_kwargs.get("channel_mult"),
                    "lookback": ec_kwargs.get("tactical_lookback"),
                    "use_stop_loss": ec_kwargs.get("use_stop_loss", True),
                    "midline_reentry": ec_kwargs.get("midline_reentry", False),
                    "midline_cross": ec_kwargs.get("midline_cross", False),
                    "lower_reclaim": ec_kwargs.get("lower_reclaim", True),
                    "channel_curl_mode": ec_kwargs.get("channel_curl_mode", "both"),
                    "timeframe": actual_tf,
                    "period": actual_period,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            print(f"On-the-fly EC stats error for {symbol}: {e}")

    stats = get_pnl_summary(symbol=symbol, strategy=strategy)
    if not stats or stats.get("total_trades", 0) == 0:
        alt_sym = symbol.replace("-", "_") if "-" in symbol else symbol.replace("_", "-")
        alt_stats = get_pnl_summary(symbol=alt_sym, strategy=strategy)
        if alt_stats and alt_stats.get("total_trades", 0) > 0:
            stats = alt_stats
    return stats

@app.get("/api/candles")
@history_endpoint
async def api_candles(symbol: str = "PORTFOLIO", timeframe: str = "1d", period: str = "1y", trading_window: str = None, start_date: str = None, end_date: str = None, snapshot_id: str = None, data_revision: str = None):
    """Fetch raw candle data for TradingView chart using yfinance."""
    validate_backtest_window(start_date, end_date)
    clean_sym = symbol.strip().upper()
    if clean_sym in ("PORTFOLIO", "TOTAL"):
        clean_sym = "SPY"

    yf_symbol = (
        clean_sym.replace("/USDT", "-USD")
        .replace("/USD", "-USD")
        .replace("_USDT", "-USD")
        .replace("_USD", "-USD")
        .replace("/", "-")
        .replace("_", "-")
    )
    
    candles, actual_tf, actual_period = fetch_backtest_candles("yahoo", yf_symbol, timeframe, period, trading_window, start_date, end_date)
    return {"candles": candles, "timeframe": actual_tf, "period": actual_period,
            "trading_window": normalize_trading_window(trading_window, load_market_config())}

@app.get("/api/chart/candles")
@history_endpoint
async def api_chart_candles(source: str = "yahoo", symbol: str = "SPY", timeframe: str = "1d", period: str = "1y", trading_window: str = None, start_date: str = None, end_date: str = None, snapshot_id: str = None, data_revision: str = None):
    """Return normalized OHLCV candles for the React chart workspace."""
    validate_backtest_window(start_date, end_date)
    clean_symbol = symbol.strip().upper()
    if source.lower() == "yahoo":
        clean_symbol = clean_symbol.replace("/USDT", "-USD").replace("/USD", "-USD").replace("_USDT", "-USD").replace("_USD", "-USD").replace("/", "-").replace("_", "-")
    try:
        candles, actual_tf, actual_period = await asyncio.to_thread(
            fetch_backtest_candles, source, clean_symbol, timeframe, period, trading_window, start_date, end_date
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{source} candle request failed: {exc}") from exc
    return {
        "source": source.lower(), "symbol": clean_symbol, "candles": candles,
        "timeframe": actual_tf, "period": actual_period,
        "trading_window": "24/7" if source.lower() == "hyperliquid" else normalize_trading_window(trading_window, load_market_config()),
    }


@app.get("/api/trendlines")
@history_endpoint
async def api_trendlines(symbol: str, source: str = "yahoo", strategy: str = "enhanced_lines", timeframe: str = "1d", period: str = "1y", trading_window: str = None, full_candle: bool = None, use_wick: bool = None, confirm_candles: int = None, pivot_lookback: int = None, inverse_color_trigger: bool = None, line_angle: float = None, stop_loss_mode: str = None, min_anchor_bars: int = None, anchor_source: str = None, validation_boundary: str = None, trendline_tolerance: float = None, gap_up: bool = None, gap_down: bool = None, staggered_lines: bool = None, reentry_mode: str = None, reentry_rsi: bool = None, reentry_ema: bool = None, reentry_price_breakout: bool = None, reentry_volume: bool = None, line_breakout_buy: bool = None, entry_barrier_sell: bool = None, start_date: str = None, end_date: str = None, compounding: bool = None, initial_capital: float = None, peak_reclaim_full_candle: bool = None, snapshot_id: str = None, data_revision: str = None, commission_pct: float = None, slippage_pct: float = None):
    """
    Run trendline strategy (sloped_lines or enhanced_lines) on OHLCV data
    and return trendline segments for chart overlay.
    """
    if initial_capital is not None and (not math.isfinite(initial_capital) or initial_capital <= 0):
        raise HTTPException(status_code=422, detail="initial_capital must be finite and greater than zero")
    validate_backtest_window(start_date, end_date)
    import sys
    from pathlib import Path as PurePath

    clean_sym = symbol.strip().upper()
    if clean_sym in ("PORTFOLIO", "TOTAL"):
        clean_sym = "SPY"

    yf_symbol = (
        clean_sym.replace("/USDT", "-USD")
        .replace("/USD", "-USD")
        .replace("_USDT", "-USD")
        .replace("_USD", "-USD")
        .replace("/", "-")
        .replace("_", "-")
    )

    base_dir = Path(__file__).resolve().parents[3]

    try:
        candles, actual_tf, actual_period = fetch_backtest_candles(source, clean_sym if source == "hyperliquid" else yf_symbol, timeframe, period, trading_window, start_date, end_date)
        if not candles:
            return {"trendlines": [], "error": "No candle data available"}

        if strategy in ("sloped_lines", "slope_lines"):
            strategy_dir = base_dir / "strategies" / "sloped_lines"
            if str(strategy_dir) not in sys.path:
                sys.path.insert(0, str(strategy_dir))
            from sloped_lines_strategy import run_sloped_lines_with_trendlines
            p = _resolve_sloped_params(clean_sym, full_candle, use_wick, confirm_candles, pivot_lookback, inverse_color_trigger, line_angle, stop_loss_mode, min_anchor_bars, anchor_source, validation_boundary, trendline_tolerance, gap_up, gap_down, staggered_lines, reentry_mode, reentry_rsi, reentry_ema, reentry_price_breakout, reentry_volume, line_breakout_buy, entry_barrier_sell, compounding, initial_capital, peak_reclaim_full_candle)
            result = run_sloped_lines_with_trendlines(candles, **p)
            return {"trendlines": result.get("trendlines", []), "timeframe": actual_tf, "period": actual_period}

        else:
            strategy_dir = base_dir / "strategies" / "enhanced_lines"
            if str(strategy_dir) not in sys.path:
                sys.path.insert(0, str(strategy_dir))

            from enhanced_lines_strategy import run_enhanced_lines_with_trendlines
            result = run_enhanced_lines_with_trendlines(candles)
            return {"trendlines": result.get("trendlines", []), "timeframe": actual_tf, "period": actual_period}

    except Exception as e:
        print(f"Trendlines error for {symbol} ({strategy}): {e}")
        import traceback
        traceback.print_exc()
        return {"trendlines": [], "error": str(e)}

@app.get("/api/channels")
@history_endpoint
async def api_channels(symbol: str, source: str = "yahoo", timeframe: str = "1d", period: str = "5y", trading_window: str = None, channel_mult: float = 1.7, lookback: int = 50, start_date: str = None, end_date: str = None, snapshot_id: str = None, data_revision: str = None):
    """
    Run the enhanced_channel strategy on OHLCV data and return channel overlays
    (Tactical Upper, Tactical Lower, Tactical Mid, Intermediate Mid, Macro Mid)
    for chart overlay.
    """
    validate_backtest_window(start_date, end_date)
    clean_sym = symbol.strip().upper()
    if clean_sym in ("PORTFOLIO", "TOTAL"):
        clean_sym = "SPY"

    yf_symbol = (
        clean_sym.replace("/USDT", "-USD")
        .replace("/USD", "-USD")
        .replace("_USDT", "-USD")
        .replace("_USD", "-USD")
        .replace("/", "-")
        .replace("_", "-")
    )

    try:
        base_dir = Path(__file__).resolve().parents[3]
        strategy_dir = base_dir / "strategies" / "enhanced_channel"
        if str(strategy_dir) not in sys.path:
            sys.path.insert(0, str(strategy_dir))

        from enhanced_channel_strategy import run_enhanced_channel
        candles, actual_tf, actual_period = fetch_backtest_candles(source, clean_sym if source == "hyperliquid" else yf_symbol, timeframe, period, trading_window, start_date, end_date)
        if not candles:
            return {"overlays": [], "error": "No candle data available"}

        params = {"channel_mult": channel_mult}
        if lookback is not None and lookback > 0:
            params["tactical_lookback"] = lookback
        result = run_enhanced_channel(candles, params=params)
        raw_overlays = result.get("overlays", [])

        # Format points as unix timestamps for Lightweight Charts
        formatted_overlays = []
        for ov in raw_overlays:
            pts = []
            for p in ov.get("points", []):
                t_str = p.get("time")
                if not t_str:
                    continue
                try:
                    if " " in t_str:
                        dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                    else:
                        dt = datetime.strptime(t_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    pts.append({"time": int(dt.timestamp()), "value": round(float(p["value"]), 2)})
                except Exception:
                    continue

            label = ov.get("label", "")
            color = ov.get("color", "#3b82f6")
            line_style = 0  # Solid
            line_width = 2
            channel_type = "mid"

            if "Upper" in label:
                color = "rgba(239, 68, 68, 0.85)"  # Red / Resistance / Take Profit
                line_width = 2
                channel_type = "upper"
            elif "Lower" in label:
                color = "rgba(16, 185, 129, 0.85)"  # Green / Support / Buy Zone
                line_width = 2
                channel_type = "lower"
            elif "Tactical Mid" in label:
                color = "rgba(59, 130, 246, 0.55)"  # Blue / Tactical regression centerline
                line_style = 2  # Dashed
                line_width = 1
                channel_type = "tactical_mid"
            elif "Intermediate" in label:
                color = "rgba(245, 158, 11, 0.6)"  # Amber / 1Y Trend Baseline
                line_style = 1  # Dotted
                line_width = 1
                channel_type = "intermediate_mid"
            elif "Macro" in label:
                color = "rgba(168, 85, 247, 0.6)"  # Purple / 5Y Macro Baseline
                line_style = 1  # Dotted
                line_width = 1
                channel_type = "macro_mid"

            formatted_overlays.append({
                "label": label,
                "color": color,
                "lineWidth": line_width,
                "lineStyle": line_style,
                "channelType": channel_type,
                "points": pts,
            })

        return {"overlays": formatted_overlays, "timeframe": actual_tf, "period": actual_period}

    except Exception as e:
        print(f"Channels error for {symbol}: {e}")
        return {"overlays": [], "error": str(e)}

if __name__ == "__main__":
    from tradingview_mcp.ui.launcher import main
    main()
