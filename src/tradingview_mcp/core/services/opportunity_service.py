"""Research-only watchlist scan for current, completed-bar buy signals.

Historical win rates are descriptive evidence, not calibrated probabilities.
The scanner never places orders or assigns a buy recommendation.
"""

from __future__ import annotations

import math
import re
import statistics
from datetime import datetime, timezone

from tradingview_mcp.core.services.backtest_service import (
    _STRATEGY_LABELS,
    _STRATEGY_MAP,
    _apply_costs,
    _completed_candles,
    _fetch_ohlcv,
)
from tradingview_mcp.core.services.signal_service import _OPEN_STATE_STRATEGIES


DEFAULT_WATCHLIST = ("GOOGL", "AAPL", "MELI", "SPY", "NVDA")
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.^=-]{0,19}$")


def _wilson_interval(wins: int, count: int) -> tuple[float, float] | None:
    """95% Wilson interval for the observed profitable-trade fraction."""
    if count == 0:
        return None
    z = 1.96
    p = wins / count
    z2 = z * z
    center = (p + z2 / (2 * count)) / (1 + z2 / count)
    radius = z * math.sqrt(p * (1 - p) / count + z2 / (4 * count * count)) / (1 + z2 / count)
    return round(max(0.0, center - radius) * 100, 1), round(min(1.0, center + radius) * 100, 1)


def _trade_evidence(trades: list[dict], latest_date: str) -> dict:
    """Summarize closed, cost-adjusted trades known before the current bar."""
    closed = [t for t in trades if t.get("exit_date") and t["exit_date"] < latest_date
              and t.get("side", "long") == "long"
              and t.get("exit_reason") != "end_of_data"]
    net = _apply_costs(closed, commission_pct=0.1, slippage_pct=0.05)
    returns = [t["return_pct"] for t in net]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    interval = _wilson_interval(len(wins), len(returns))
    return {
        "closed_trades": len(returns),
        "profitable_trades": len(wins),
        "observed_win_rate_pct": round(len(wins) / len(returns) * 100, 1) if returns else None,
        "observed_win_rate_95pct_interval": list(interval) if interval else None,
        "average_net_trade_return_pct": round(statistics.mean(returns), 2) if returns else None,
        "average_win_pct": round(statistics.mean(wins), 2) if wins else None,
        "average_loss_pct": round(statistics.mean(losses), 2) if losses else None,
        "worst_trade_pct": round(min(returns), 2) if returns else None,
        "evidence_status": "limited_history" if len(returns) < 20 else "historical_only",
        "calibrated_gain_probability_pct": None,
    }


def scan_symbol_candles(symbol: str, candles: list[dict], strategies: dict | None = None) -> list[dict]:
    """Evaluate supported strategy runners on one fixed, completed candle series."""
    if len(candles) < 50:
        raise ValueError(f"Only {len(candles)} completed bars; at least 50 are required")
    runners = strategies if strategies is not None else {
        name: _STRATEGY_MAP[name] for name in sorted(_OPEN_STATE_STRATEGIES)
    }
    latest = candles[-1]
    rows = []
    for name, runner in runners.items():
        try:
            all_trades = runner(candles, include_open=True)
            prior_trades = runner(candles[:-1], include_open=True)
            prior_entries = {
                (t.get("entry_date"), t.get("entry_price"), t.get("side", "long"))
                for t in prior_trades
            }
            new_buys = [t for t in all_trades
                        if t.get("entry_date") == latest["date"]
                        and t.get("side", "long") == "long"
                        and (name != "volume_price_breakout" or t.get("pending_entry"))
                        and (t.get("entry_date"), t.get("entry_price"), "long") not in prior_entries]
            rows.append({
                "symbol": symbol,
                "strategy": name,
                "strategy_label": _STRATEGY_LABELS.get(name, name),
                "signal": "buy" if new_buys else "none",
                "signal_date": latest["date"] if new_buys else None,
                "signal_price": latest["close"] if new_buys else None,
                "signal_context": ({"price_gain_pct": new_buys[-1]["signal_gain_pct"],
                                    "volume_ratio": new_buys[-1]["signal_volume_ratio"]}
                                   if new_buys and name == "volume_price_breakout" else None),
                **_trade_evidence(all_trades, latest["date"]),
            })
        except Exception as exc:
            rows.append({"symbol": symbol, "strategy": name, "signal": "error", "error": str(exc)})
    return rows


def scan_opportunities(symbols: list[str] | None = None, fetcher=None) -> dict:
    """Scan up to 20 stocks, fetching each stock only once.

    The two-year daily window matches get_live_signal's completed-bar input.
    No numeric probability or automatic recommendation is emitted yet.
    """
    requested = symbols if symbols is not None else list(DEFAULT_WATCHLIST)
    cleaned = list(dict.fromkeys(s.strip().upper() for s in requested if s.strip()))
    if not cleaned or len(cleaned) > 20:
        raise ValueError("Choose between 1 and 20 stock symbols")
    if any(not _SYMBOL_RE.fullmatch(s) for s in cleaned):
        raise ValueError("Symbols may contain letters, numbers, dots, dashes, carets, or equals signs")
    get_candles = fetcher or _fetch_ohlcv
    rows, errors, as_of = [], [], {}
    for symbol in cleaned:
        try:
            candles = _completed_candles(get_candles(symbol, "2y", "1d"), symbol, "1d")
            as_of[symbol] = candles[-1]["date"] if candles else None
            rows.extend(scan_symbol_candles(symbol, candles))
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
    rows.sort(key=lambda r: (r["signal"] != "buy", r["symbol"], r["strategy"]))
    active = [r for r in rows if r["signal"] == "buy"]
    return {
        "watchlist": cleaned,
        "interval": "1d",
        "history_period": "2y",
        "as_of_completed_bar": as_of,
        "strategies_scanned": sorted(_OPEN_STATE_STRATEGIES),
        "active_buy_signals": active,
        "rows": rows,
        "errors": errors,
        "calibration_status": "not_available",
        "note": "Observed closed-trade win rates are descriptive, not probabilities for the current buy. No order is placed or stock recommended.",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
