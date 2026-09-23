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
    last_updated: Optional[str] = None
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
    
    tickers[sym_key] = record
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
        
    return record
