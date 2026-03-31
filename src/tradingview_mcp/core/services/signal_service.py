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
    _STRATEGY_MAP,
    _STRATEGY_LABELS,
    _VALID_INTERVALS,
)


# Strategies that produce SL/TP on their trades
_SL_TP_STRATEGIES = {"vwma17"}


def get_live_signal(
    symbol: str,
    strategy: str,
    interval: str = "1d",
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

    # Fetch enough bars for indicator warm-up (300 daily bars, more for intraday)
    warmup_period = "2y" if interval == "1d" else "3mo"
    try:
        candles = _fetch_ohlcv(symbol, warmup_period, interval)
    except Exception as e:
        return {"error": f"Failed to fetch data for '{symbol}': {e}"}

    if len(candles) < 50:
        return {"error": f"Not enough data ({len(candles)} bars). Need at least 50."}

    fn = _STRATEGY_MAP[strategy]
    latest_price = candles[-1]["close"]
    latest_date = candles[-1]["date"]

    # === Strategy A: run on ALL candles, check if last bar triggers entry ===
    all_trades = fn(candles)

    # === Strategy B: run on all-but-last candle to see prior state ===
    prev_trades = fn(candles[:-1])

    # Determine signal
    signal = "none"
    stop_loss = None
    take_profit = None
    exit_reason = None

    # Case 1: new trade appeared on the last bar (entry signal)
    if len(all_trades) > len(prev_trades):
        last_trade = all_trades[-1]
        # If the trade was entered on the last bar
        if last_trade.get("entry_date") == latest_date:
            signal = last_trade.get("side", "long")
            stop_loss = last_trade.get("stop_loss")
            take_profit = last_trade.get("take_profit")
        # If the trade was CLOSED on the last bar (exit)
        elif last_trade.get("exit_date") == latest_date:
            signal = "exit"
            exit_reason = last_trade.get("exit_reason")
    elif len(all_trades) == len(prev_trades) and len(all_trades) > 0:
        last_all = all_trades[-1]
        last_prev = prev_trades[-1]
        # A trade that was open in prev got closed in all → exit on last bar
        if (last_all.get("exit_date") == latest_date and
                last_prev.get("exit_date") != latest_date):
            signal = "exit"
            exit_reason = last_all.get("exit_reason")

    # For strategies with SL/TP, try to extract from the open position state
    # by running on full data and checking if there's an unterminated position
    if signal in ("long", "short") and strategy in _SL_TP_STRATEGIES:
        # Re-extract SL/TP from the strategy's internal position
        # The _run_vwma17 function stores SL/TP in the trade dict
        for t in reversed(all_trades):
            if t.get("entry_date") == latest_date:
                stop_loss = t.get("stop_loss", stop_loss)
                take_profit = t.get("take_profit", take_profit)
                break

    return {
        "signal": signal,
        "symbol": symbol.upper(),
        "strategy": strategy,
        "strategy_label": _STRATEGY_LABELS.get(strategy, strategy),
        "price": latest_price,
        "stop_loss": round(stop_loss, 4) if stop_loss is not None else None,
        "take_profit": round(take_profit, 4) if take_profit is not None else None,
        "exit_reason": exit_reason,
        "interval": interval,
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
