"""
Strategy best parameters configuration service.
Manages optimal parameters and performance metrics for each strategy and ticker combination.
"""

import json
from pathlib import Path
from typing import Any, Optional


def get_config_path() -> Path:
    """Returns absolute path to strategies/best_parameters.json."""
    # Base directory is tradingview-mcp root (4 levels up from this file)
    base_dir = Path(__file__).resolve().parents[4]
    config_path = base_dir / "strategies" / "best_parameters.json"
    if not config_path.exists():
        # Fallback to local cwd or strategies relative path
        alt_path = Path("strategies/best_parameters.json").resolve()
        if alt_path.exists():
            return alt_path
    return config_path


def load_best_parameters() -> dict[str, Any]:
    """Load the complete best parameters configuration."""
    path = get_config_path()
    if not path.exists():
        return {"version": "1.0.0", "strategies": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_best_parameters(strategy: str, symbol: str) -> Optional[dict[str, Any]]:
    """
    Retrieve optimal parameters and performance metadata for a given strategy and symbol.
    Returns None if no configuration is recorded for the pair.
    """
    config = load_best_parameters()
    strategies = config.get("strategies", {})

    # Normalize keys
    strat_key = strategy.lower().strip()
    sym_key = symbol.upper().strip()

    strat_entry = strategies.get(strat_key)
    if not strat_entry:
        return None

    tickers = strat_entry.get("tickers", {})
    return tickers.get(sym_key)


def set_best_parameters(
    strategy: str,
    symbol: str,
    parameters: dict[str, Any],
    performance: Optional[dict[str, Any]] = None,
    timeframe: str = "1d",
    period: str = "1y",
    notes: str = "",
    last_updated: Optional[str] = None,
    backtest_window: Optional[dict[str, Any]] = None,
    candles: Optional[list[dict]] = None,
    source: str = 'yahoo',
    observed: Optional[dict[str, Any]] = None,
    costs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Update or insert optimal parameters for a given strategy and ticker combination.
    """
    from datetime import datetime, timezone
    path = get_config_path()
    config = load_best_parameters()

    strategies = config.setdefault("strategies", {})
    strat_key = strategy.lower().strip()
    sym_key = symbol.upper().strip()

    strat_entry = strategies.setdefault(strat_key, {
        "name": strategy.replace("_", " ").title(),
        "tickers": {}
    })

    tickers = strat_entry.setdefault("tickers", {})

    updated_date = last_updated or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    record = {
        "timeframe": timeframe,
        "period": period,
        "parameters": parameters,
        "performance": performance or {},
        "notes": notes,
        "last_updated": updated_date
    }

    # Capture the exact input dataset before making a new Saved Best visible.
    # Callers supplying candles must supply the window used for that run.
    from tradingview_mcp.core.services.market_data_store import Series, History, get_market_store, request_bounds
    from tradingview_mcp.ui.server import fetch_market_candles, fetch_hyperliquid_candles, _engine_revision
    supplied_candles = candles is not None
    if performance and not supplied_candles:
        raise ValueError('Supply the original candles and backtest_window when recording performance; refetching cannot preserve a completed run exactly')
    window = dict(backtest_window or {})
    if candles is not None and not window:
        raise ValueError('Provide backtest_window when saving supplied candles')
    if not window:
        a, b = request_bounds(period)
        window = {'start_date': datetime.fromtimestamp(a, timezone.utc).date().isoformat(),
                  'end_date': datetime.fromtimestamp(b - 1, timezone.utc).date().isoformat(),
                  'trading_window': 'regular market'}
    a, b = request_bounds(period, window['start_date'], window['end_date'])
    session = window.get('trading_window', 'regular market') if source == 'yahoo' else '24/7'
    series = Series(source, sym_key, timeframe, session, 'adjusted' if source == 'yahoo' else 'raw')
    if candles is None:
        if source == 'yahoo':
            candles = fetch_market_candles(sym_key, timeframe, period, session, window['start_date'], window['end_date'])[0]
        else:
            candles = fetch_hyperliquid_candles(sym_key, timeframe, period, window['start_date'], window['end_date'])[0]
    candles = get_market_store()._validate(candles, a, b)
    record['backtest_window'] = window
    record['source'] = source
    record['costs'] = costs or {'commission_pct': parameters.get('commission_pct', .1), 'slippage_pct': parameters.get('slippage_pct', .05)}
    history = History(candles, {'complete': True})
    snapshot = get_market_store().save_snapshot(series, a, b, history, origin='original' if supplied_candles else 'reconstructed', provenance={'strategy': strat_key})
    get_market_store().bind_saved_run(record, strat_key, sym_key, snapshot,
        engine_revision=_engine_revision(), observed=observed, costs=record['costs'])
    tickers[sym_key] = record

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    return record
