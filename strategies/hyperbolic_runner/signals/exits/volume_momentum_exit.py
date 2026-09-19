"""
Volume Momentum Exit — exit fast on a high-volume panic bar.

Fires when:
  1. Single-bar price drop >= 3.5% (sharp reversal)
  2. Volume >= 2.5x average (institutional distribution / panic selling)
  3. Close in bottom 25% of the bar's high-low range (price couldn't recover intraday)
  4. Either: unrealized gain >= 0% OR bars held >= 10 (don't exit bad entries immediately)

This fires BEFORE the trailing stop — it's more decisive for single-session
capitulation events that the wide 20x ATR stop would miss entirely.

Returns: (bool, str)
"""
from __future__ import annotations

METADATA = {
    "name": "volume_momentum_exit",
    "description": "Exit on single-bar panic drop with heavy volume (distribution signal)",
    "type": "exit",
    "drop_pct": 3.5,           # Single-bar drop threshold
    "volume_mult": 2.5,        # Volume must be >= this x vol MA
    "close_range_pct": 0.25,   # Close must be in bottom X% of bar range
    "min_bars_held": 10,       # If in loss, require at least this many bars held
}


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    closes = ctx["closes"]
    candles = ctx["candles"]
    vol_sma_vals = ctx["vol_sma_vals"]
    entry_price = ctx.get("weighted_entry_price") or ctx.get("entry_price")
    trades = ctx.get("trades", [])

    p = ctx.get("params", {})
    drop_pct = p.get("vol_exit_drop_pct", METADATA["drop_pct"])
    vol_mult = p.get("vol_exit_volume_mult", METADATA["volume_mult"])
    close_range = p.get("vol_exit_close_range_pct", METADATA["close_range_pct"])
    min_bars = p.get("vol_exit_min_bars_held", METADATA["min_bars_held"])

    if i < 2:
        return False, ""

    close = closes[i]
    prev_close = closes[i - 1]
    candle = candles[i]

    # 1. Sharp single-bar drop
    bar_drop = (prev_close - close) / prev_close * 100
    if bar_drop < drop_pct:
        return False, ""

    # 2. Heavy volume on the drop
    vol = candle["volume"]
    vol_ma = vol_sma_vals[i]
    if vol_ma is None or vol_ma <= 0 or vol < vol_ma * vol_mult:
        return False, ""

    # 3. Close near the low of the bar (no intraday recovery — real selling pressure)
    bar_range = candle["high"] - candle["low"]
    if bar_range > 0:
        close_position = (candle["high"] - close) / bar_range  # 0 = closed at high, 1 = closed at low
        if close_position < (1.0 - close_range):  # Close is NOT in bottom 25%
            return False, ""

    # 4. Either profitable OR held long enough (avoid exiting bad entries immediately)
    if entry_price is not None and entry_price > 0:
        unrealized_gain = (close - entry_price) / entry_price * 100
        # Count bars held using trade count vs total bar index
        bars_held = i - next(
            (j for j, c in enumerate(candles) if c["date"] == ctx.get("entry_date", "")),
            i - min_bars
        )
        if unrealized_gain < 0 and bars_held < min_bars:
            return False, ""

    return True, "volume_momentum_exit"
