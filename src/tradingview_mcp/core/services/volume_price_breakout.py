"""Price breakout confirmed by unusually high volume.

Signals are evaluated only after a bar closes. Historical entries use the
following bar's open; a last-bar signal is pending, not a filled trade.
"""

from __future__ import annotations

from tradingview_mcp.core.services.indicators_calc import calc_atr


def run_volume_price_breakout(
    candles: list[dict],
    price_gain_pct: float = 3.0,
    volume_multiplier: float = 2.0,
    lookback: int = 20,
    atr_period: int = 14,
    stop_atr: float = 2.0,
    target_atr: float = 4.0,
    max_hold_bars: int = 10,
    include_open: bool = False,
) -> list[dict]:
    """Buy a new high on a strong up bar with a volume surge.

    The breakout and volume baselines use preceding bars. A signal fills at
    the next bar's open. Gap exits use the actual open; when both stop and
    target are touched inside one bar, the stop is assumed to fill first.
    """
    if lookback < 2 or atr_period < 2 or max_hold_bars < 1:
        raise ValueError("lookback and ATR period must be at least 2; max hold at least 1")
    if price_gain_pct <= 0 or volume_multiplier <= 1 or stop_atr <= 0 or target_atr <= 0:
        raise ValueError("Breakout, volume, stop, and target thresholds must be positive")
    if len(candles) < max(lookback, atr_period) + 1:
        return []

    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    atr = calc_atr(highs, lows, closes, atr_period)

    def qualifying_signal(i: int) -> dict | None:
        if i < max(lookback, atr_period) or atr[i] is None or closes[i - 1] <= 0:
            return None
        prior_volume = sum(volumes[i - lookback:i]) / lookback
        if prior_volume <= 0:
            return None
        gain_pct = (closes[i] / closes[i - 1] - 1) * 100
        volume_ratio = volumes[i] / prior_volume
        if (gain_pct < price_gain_pct or volume_ratio < volume_multiplier
                or closes[i] <= max(highs[i - lookback:i])):
            return None
        return {
            "signal_date": candles[i]["date"],
            "signal_price": closes[i],
            "signal_atr": atr[i],
            "signal_gain_pct": round(gain_pct, 2),
            "signal_volume_ratio": round(volume_ratio, 2),
        }

    trades: list[dict] = []
    position: dict | None = None
    pending: dict | None = None
    for i, candle in enumerate(candles):
        open_price = float(candle["open"])
        if pending is not None:
            position = {
                **pending,
                "entry_date": candle["date"],
                "entry_price": open_price,
                "entry_bar": i,
                "stop_loss": open_price - stop_atr * pending["signal_atr"],
                "take_profit": open_price + target_atr * pending["signal_atr"],
                "side": "long",
            }
            pending = None

        if position is not None:
            stop = position["stop_loss"]
            target = position["take_profit"]
            exit_price = None
            reason = None
            if i - position["entry_bar"] >= max_hold_bars:
                exit_price, reason = open_price, "time_exit_next_open"
            elif open_price <= stop:
                exit_price, reason = open_price, "gap_stop"
            elif open_price >= target:
                exit_price, reason = open_price, "gap_target"
            elif lows[i] <= stop:
                exit_price, reason = stop, "stop_loss"
            elif highs[i] >= target:
                exit_price, reason = target, "take_profit"
            if reason is not None:
                trades.append({
                    **{k: v for k, v in position.items() if k != "entry_bar"},
                    "exit_date": candle["date"],
                    "exit_price": exit_price,
                    "exit_reason": reason,
                    "strategy": "volume_price_breakout",
                })
                position = None

        # A closed bar can generate an order for the next bar, never a fill on
        # this same close. Do not stack entries while a position is open.
        if position is None:
            pending = qualifying_signal(i)

    if include_open:
        if position is not None:
            trades.append({**{k: v for k, v in position.items() if k != "entry_bar"},
                           "exit_date": None, "strategy": "volume_price_breakout"})
        elif pending is not None:
            trades.append({
                **pending,
                "entry_date": pending["signal_date"],
                "entry_price": pending["signal_price"],
                "exit_date": None,
                "side": "long",
                "pending_entry": True,
                "strategy": "volume_price_breakout",
            })
    return trades
