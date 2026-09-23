import sqlite3
import asyncio
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import yfinance as yf

# Import existing DB queries and backtesting service
from tradingview_mcp.core.services.trade_db import get_trade_history, get_pnl_summary, _get_db_path, _get_connection, init_db
from tradingview_mcp.core.services.backtest_service import run_backtest, _STRATEGY_MAP
from tradingview_mcp.core.services.seed_backtests import seed_backtest_data, _format_iso_datetime
from tradingview_mcp.core.services.opportunity_service import DEFAULT_WATCHLIST, scan_opportunities

app = FastAPI(title="TradingView MCP Trade Visualizer")

# Mount static directory directly
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

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

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the single page application."""
    html_file = static_path / "index.html"
    return html_file.read_text()


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
async def api_best_parameters(strategy: str = None, symbol: str = None):
    """Retrieve optimal strategy parameters and historical performance metrics."""
    from tradingview_mcp.core.services.strategy_config import load_best_parameters, get_best_parameters
    if strategy and symbol:
        cfg = get_best_parameters(strategy, symbol)
        if not cfg:
            return {"found": False, "strategy": strategy, "symbol": symbol, "data": None}
        return {"found": True, "strategy": strategy, "symbol": symbol, "data": cfg}
    return load_best_parameters()


def fetch_market_candles(yf_symbol: str, timeframe: str = "1d", period: str = "1y") -> tuple[list[dict], str, str]:
    """
    Fetch OHLCV candles via yfinance with automatic range clamping & resampling:
      - 30m: max 60d
      - 1h, 4h, 12h: max 2y
      - 12h: resampled from 1h
      - 1d, 5d: up to max
    Returns (candles, actual_timeframe, actual_period)
    """
    import math
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

    candles = []
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=actual_period, interval=fetch_tf)
        if df is not None and not df.empty:
            if tf in ("4h", "12h"):
                df = df.resample(tf).agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()

            fmt = "%Y-%m-%d %H:%M" if tf in ("30m", "1h", "4h", "12h") else "%Y-%m-%d"
            for date, row in df.iterrows():
                o = float(row["Open"])
                h = float(row["High"])
                l = float(row["Low"])
                c = float(row["Close"])
                v = float(row.get("Volume", 0.0))
                if any(math.isnan(x) for x in (o, h, l, c)):
                    continue
                candles.append({
                    "time": int(date.timestamp()),
                    "date": date.strftime(fmt),
                    "open": round(o, 4),
                    "high": round(h, 4),
                    "low": round(l, 4),
                    "close": round(c, 4),
                    "volume": round(v, 2),
                })
    except Exception as e:
        print(f"fetch_market_candles error for {yf_symbol} ({tf}, {actual_period}): {e}")

    return candles, tf, actual_period


def _resolve_sloped_params(symbol: str, full_candle=None, use_wick=None, confirm_candles=None, inverse_color_trigger=None, line_angle=None, stop_loss_mode=None, min_anchor_bars=None):
    from tradingview_mcp.core.services.strategy_config import get_best_parameters
    cfg = get_best_parameters("sloped_lines", symbol)
    bp = (cfg or {}).get("parameters", {})
    return {
        "full_candle": full_candle if full_candle is not None else bp.get("full_candle", False),
        "use_wick": use_wick if use_wick is not None else bp.get("use_wick", False),
        "confirm_candles": confirm_candles if confirm_candles is not None else bp.get("confirm_candles", 0),
        "inverse_color_trigger": inverse_color_trigger if inverse_color_trigger is not None else bp.get("inverse_color_trigger", False),
        "line_angle": line_angle if line_angle is not None else bp.get("line_angle", 3.0),
        "stop_loss_mode": stop_loss_mode if stop_loss_mode is not None else bp.get("stop_loss_mode", "exit_peak_reclaim"),
        "min_anchor_bars": min_anchor_bars if min_anchor_bars is not None else bp.get("min_anchor_bars", 2),
    }


@app.get("/api/trades")
async def api_trades(symbol: str, strategy: str = None, timeframe: str = "1d", period: str = "1y", channel_mult: float = None, lookback: int = None, use_stop_loss: bool = True, midline_reentry: bool = False, midline_cross: bool = False, lower_reclaim: bool = True, channel_inflection: bool = True, channel_curl_mode: str = "both", full_candle: bool = None, use_wick: bool = None, confirm_candles: int = None, inverse_color_trigger: bool = None, line_angle: float = None, stop_loss_mode: str = None, min_anchor_bars: int = None):
    """Fetch the trade markers to overlay on the chart, auto-generating on demand if needed."""
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
            candles, actual_tf, actual_period = fetch_market_candles(yf_sym, timeframe, period)

            p = _resolve_sloped_params(clean_sym, full_candle, use_wick, confirm_candles, inverse_color_trigger, line_angle, stop_loss_mode, min_anchor_bars)
            res = run_sl_backtest(symbol=clean_sym, period=actual_period, interval=actual_tf, full_candle=p["full_candle"], use_wick=p["use_wick"], confirm_candles=p["confirm_candles"], inverse_color_trigger=p["inverse_color_trigger"], line_angle=p["line_angle"], stop_loss_mode=p["stop_loss_mode"], min_anchor_bars=p["min_anchor_bars"], candles=candles)
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
                    "strategy": "sloped_lines",
                    "status": "closed" if exit_d else "open",
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "exit_reason": t.get("exit_reason", ""),
                    "entry_reason": "breakout",
                    "pnl_usd": pnl_u,
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
                candles, actual_tf, actual_period = fetch_market_candles(yf_sym, timeframe, period)
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
async def api_stats(symbol: str = "PORTFOLIO", strategy: str = None, timeframe: str = "1d", period: str = "1y", channel_mult: float = None, lookback: int = None, use_stop_loss: bool = True, midline_reentry: bool = False, midline_cross: bool = False, lower_reclaim: bool = True, channel_inflection: bool = True, channel_curl_mode: str = "both", full_candle: bool = None, use_wick: bool = None, confirm_candles: int = None, inverse_color_trigger: bool = None, line_angle: float = None, stop_loss_mode: str = None, min_anchor_bars: int = None):
    """Fetch summary stats (Win Rate, PnL) based on current filters."""
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
            candles, actual_tf, actual_period = fetch_market_candles(yf_sym, timeframe, period)

            p = _resolve_sloped_params(clean_sym, full_candle, use_wick, confirm_candles, inverse_color_trigger, line_angle, stop_loss_mode, min_anchor_bars)
            res = run_sl_backtest(symbol=clean_sym, period=actual_period, interval=actual_tf, full_candle=p["full_candle"], use_wick=p["use_wick"], confirm_candles=p["confirm_candles"], inverse_color_trigger=p["inverse_color_trigger"], line_angle=p["line_angle"], stop_loss_mode=p["stop_loss_mode"], min_anchor_bars=p["min_anchor_bars"], candles=candles)
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
            candles, actual_tf, actual_period = fetch_market_candles(yf_sym, timeframe, period)

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
async def api_candles(symbol: str = "PORTFOLIO", timeframe: str = "1d", period: str = "1y"):
    """Fetch raw candle data for TradingView chart using yfinance."""
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
    
    candles, actual_tf, actual_period = fetch_market_candles(yf_symbol, timeframe, period)
    return {"candles": candles, "timeframe": actual_tf, "period": actual_period}

@app.get("/api/trendlines")
async def api_trendlines(symbol: str, strategy: str = "enhanced_lines", timeframe: str = "1d", period: str = "1y", full_candle: bool = None, use_wick: bool = None, confirm_candles: int = None, inverse_color_trigger: bool = None, line_angle: float = None, stop_loss_mode: str = None, min_anchor_bars: int = None):
    """
    Run trendline strategy (sloped_lines or enhanced_lines) on OHLCV data
    and return trendline segments for chart overlay.
    """
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
        candles, actual_tf, actual_period = fetch_market_candles(yf_symbol, timeframe, period)
        if not candles:
            return {"trendlines": [], "error": "No candle data available"}

        if strategy in ("sloped_lines", "slope_lines"):
            strategy_dir = base_dir / "strategies" / "sloped_lines"
            if str(strategy_dir) not in sys.path:
                sys.path.insert(0, str(strategy_dir))
            from sloped_lines_strategy import run_sloped_lines_with_trendlines
            p = _resolve_sloped_params(clean_sym, full_candle, use_wick, confirm_candles, inverse_color_trigger, line_angle, stop_loss_mode, min_anchor_bars)
            result = run_sloped_lines_with_trendlines(candles, full_candle=p["full_candle"], use_wick=p["use_wick"], confirm_candles=p["confirm_candles"], inverse_color_trigger=p["inverse_color_trigger"], line_angle=p["line_angle"], stop_loss_mode=p["stop_loss_mode"], min_anchor_bars=p["min_anchor_bars"])
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
async def api_channels(symbol: str, timeframe: str = "1d", period: str = "5y", channel_mult: float = 1.7, lookback: int = 50):
    """
    Run the enhanced_channel strategy on OHLCV data and return channel overlays
    (Tactical Upper, Tactical Lower, Tactical Mid, Intermediate Mid, Macro Mid)
    for chart overlay.
    """
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

        from enhanced_channel_strategy import fetch_ohlcv, run_enhanced_channel
        candles = fetch_ohlcv(yf_symbol, period=period, interval=timeframe)
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

        return {"overlays": formatted_overlays}

    except Exception as e:
        print(f"Channels error for {symbol}: {e}")
        return {"overlays": [], "error": str(e)}

if __name__ == "__main__":
    from tradingview_mcp.ui.launcher import main
    main()
