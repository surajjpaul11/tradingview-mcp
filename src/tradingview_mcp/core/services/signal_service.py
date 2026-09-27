"""
Signal Detection Service — tradingview-mcp

Detects live trading signals on the most recent bar by reusing
the existing strategy engines from backtest_service.

Usage:
    from tradingview_mcp.core.services.signal_service import get_live_signal
    signal = get_live_signal("BTC-USD", "vwma17")
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.backtest_service import (
    _fetch_ohlcv,
    _completed_candles,
    _STRATEGY_MAP,
    _STRATEGY_LABELS,
    _VALID_INTERVALS,
)


# Strategies that produce SL/TP on their trades
_SL_TP_STRATEGIES = {"vwma17"}
_OPEN_STATE_STRATEGIES = {
    "rsi", "bollinger", "macd", "ema_cross", "supertrend", "donchian",
    "vwma17", "higher_highs", "ema21", "volume_price_breakout",
}


def get_live_signal(
    symbol: str,
    strategy: str,
    interval: str = "1d",
    trading_window: str | None = None,
) -> dict:
    """
    Run a strategy on recent data and detect whether the latest bar triggers
    an entry signal (long/short), an exit, or nothing.

    Returns:
        {
            "signal": "long" | "short" | "exit" | "none",
            "symbol": str,
            "strategy": str,
            "strategy_label": str,
            "price": float,
            "stop_loss": float | None,
            "take_profit": float | None,
            "interval": str,
            "candles_fetched": int,
            "latest_bar_date": str,
            "timestamp": str,
        }

    The detection works by running the same strategy function on the most
    recent candles and checking:
      - Does the strategy open a NEW position on the last bar? → long/short
      - Does the strategy close a position on the last bar?    → exit
      - Neither?                                                → none
    """
    strategy = strategy.lower().strip()
    interval = interval.lower().strip()

    if strategy not in _STRATEGY_MAP:
        return {"error": f"Unknown strategy '{strategy}'. Choose: {', '.join(_STRATEGY_MAP)}"}
    if interval not in _VALID_INTERVALS:
        return {"error": f"Invalid interval '{interval}'. Choose: {', '.join(_VALID_INTERVALS)}"}

    from tradingview_mcp.core.services.market_hours import load_market_config, normalize_trading_window
    market_config = load_market_config()
    selected_window = normalize_trading_window(trading_window, market_config)

    # Fetch enough bars for indicator warm-up (300 daily bars, more for intraday)
    warmup_period = "2y" if interval == "1d" else "3mo"
    try:
        candles = _completed_candles(
            _fetch_ohlcv(symbol, warmup_period, interval, selected_window), symbol, interval
        )
    except Exception as e:
        return {"error": f"Failed to fetch data for '{symbol}': {e}"}

    if len(candles) < 50:
        return {"error": f"Not enough data ({len(candles)} bars). Need at least 50."}

    fn = _STRATEGY_MAP[strategy]
    latest_price = candles[-1]["close"]
    latest_date = candles[-1]["date"]

    # Engines in this set can expose their still-open position. Other engines
    # return a synthetic end_of_data trade, which is useful for research but
    # must never be interpreted as a live exit.
    kwargs = {"include_open": True} if strategy in _OPEN_STATE_STRATEGIES else {}
    try:
        all_trades = fn(candles, **kwargs)
        prev_trades = fn(candles[:-1], **kwargs)
    except Exception as e:
        return {"error": f"Strategy evaluation failed for '{strategy}': {e}"}

    # Determine signal
    signal = "none"
    stop_loss = None
    take_profit = None
    exit_reason = None
    signal_context = None

    previous_entries = {
        (t.get("entry_date"), t.get("entry_price"), t.get("side", "long"))
        for t in prev_trades
    }
    new_entries = [
        t for t in all_trades
        if t.get("entry_date") == latest_date
        and (t.get("entry_date"), t.get("entry_price"), t.get("side", "long"))
        not in previous_entries
    ]
    if strategy == "volume_price_breakout":
        # A historical fill occurs the day after its signal. Only a pending
        # order from today's completed bar is a *new* actionable signal.
        new_entries = [t for t in new_entries if t.get("pending_entry")]
    if new_entries:
        latest = new_entries[-1]
        signal = latest.get("side", "long")
        if strategy == "volume_price_breakout":
            signal_context = {"price_gain_pct": latest["signal_gain_pct"],
                              "volume_ratio": latest["signal_volume_ratio"]}
        if strategy in _SL_TP_STRATEGIES:
            stop_loss = latest.get("stop_loss")
            take_profit = latest.get("take_profit")
    else:
        previous_exits = {
            (t.get("entry_date"), t.get("exit_date"), t.get("exit_reason"))
            for t in prev_trades if t.get("exit_date") is not None
        }
        real_exits = [
            t for t in all_trades
            if t.get("exit_date") == latest_date
            and t.get("exit_reason") != "end_of_data"
            and (t.get("entry_date"), t.get("exit_date"), t.get("exit_reason"))
            not in previous_exits
        ]
        if real_exits:
            signal = "exit"
            exit_reason = real_exits[-1].get("exit_reason")

    return {
        "signal": signal,
        "symbol": symbol.upper(),
        "strategy": strategy,
        "strategy_label": _STRATEGY_LABELS.get(strategy, strategy),
        "price": latest_price,
        "stop_loss": round(stop_loss, 4) if stop_loss is not None else None,
        "take_profit": round(take_profit, 4) if take_profit is not None else None,
        "exit_reason": exit_reason,
        "signal_context": signal_context,
        "interval": interval,
        "trading_window": selected_window,
        "candles_fetched": len(candles),
        "latest_bar_date": latest_date,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Signals are for informational purposes only. Not financial advice.",
    }


def check_all_strategies(
    symbol: str,
    interval: str = "1d",
) -> dict:
    """
    Check all available strategies for signals on a single symbol.
    Returns a summary with any active signals highlighted.
    """
    results = []
    active_signals = []

    for strat in _STRATEGY_MAP:
        sig = get_live_signal(symbol, strat, interval)
        if "error" in sig:
            results.append({"strategy": strat, "signal": "error", "error": sig["error"]})
            continue
        results.append({
            "strategy": strat,
            "strategy_label": sig["strategy_label"],
            "signal": sig["signal"],
            "price": sig["price"],
            "stop_loss": sig.get("stop_loss"),
            "take_profit": sig.get("take_profit"),
        })
        if sig["signal"] in ("long", "short"):
            active_signals.append(sig)

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "strategies_checked": len(results),
        "active_signals": len(active_signals),
        "results": results,
        "active_signal_details": active_signals,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
