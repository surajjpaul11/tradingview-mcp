"""
Volume Surge Pyramid — scale into a winning position on momentum acceleration.

Fires when:
  1. Already in a profitable position (unrealized gain >= 5%)
  2. Single-bar price surge >= 3% with volume >= 2x average
  3. Fast EMA is trending up (EMA[i] > EMA[i-3])
  4. RSI > 45 (not a dead-cat bounce off a low)
  5. At least 5 bars since last pyramid add (cooldown)
  6. Position not already at max size (total_size < max_pyramid_size)

This is a PYRAMID signal — it fires when in_position is True (unlike normal
entry signals which fire when not in position). The engine evaluates PYRAMID_SIGNALS
separately before the exit signal check.

Returns: bool
"""
from __future__ import annotations

METADATA = {
    "name": "volume_surge_pyramid",
    "description": "Scale in on high-volume momentum surge while in profitable position",
    "type": "pyramid",
    "min_gain_pct": 5.0,       # Must be at least 5% up before adding
    "surge_pct": 3.0,          # Single-bar price gain threshold
    "volume_mult": 2.0,        # Volume must be >= this x vol MA
    "rsi_min": 45,             # RSI must be above this (not a bounce off a low)
    "ema_lookback": 3,         # EMA must be rising over this many bars
    "cooldown_bars": 5,        # Bars to wait between pyramid adds
    "max_pyramid_size": 2.0,   # Maximum total_size (base 1.0 + max 1 add of 0.5 → 1.5)
}


def check(ctx: dict) -> bool:
    i = ctx["i"]
    closes = ctx["closes"]
    candles = ctx["candles"]
    fast_ema_vals = ctx["fast_ema_vals"]
    rsi_vals = ctx["rsi_vals"]
    vol_sma_vals = ctx["vol_sma_vals"]
    entry_price = ctx.get("weighted_entry_price") or ctx.get("entry_price")
    total_size = ctx.get("total_size", 1.0)
    bars_since_pyramid = ctx.get("bars_since_pyramid", 999)

    p = ctx.get("params", {})
    min_gain = p.get("pyramid_min_gain_pct", METADATA["min_gain_pct"])
    surge_pct = p.get("pyramid_surge_pct", METADATA["surge_pct"])
    vol_mult = p.get("pyramid_volume_mult", METADATA["volume_mult"])
    rsi_min = p.get("pyramid_rsi_min", METADATA["rsi_min"])
    ema_lb = p.get("pyramid_ema_lookback", METADATA["ema_lookback"])
    cooldown = p.get("pyramid_cooldown_bars", METADATA["cooldown_bars"])
    max_size = p.get("max_pyramid_size", METADATA["max_pyramid_size"])

    # Must be in position (engine only calls PYRAMID_SIGNALS when in_position)
    if not ctx.get("in_position", False):
        return False

    # Already at max position size
    if total_size >= max_size:
        return False

    # Cooldown between pyramid adds
    if bars_since_pyramid < cooldown:
        return False

    # Need enough bars for indicators
    if i < max(ema_lb + 1, 2):
        return False

    close = closes[i]
    prev_close = closes[i - 1]

    # 1. Already profitable (unrealized gain threshold)
    if entry_price is None or entry_price <= 0:
        return False
    unrealized_gain = (close - entry_price) / entry_price * 100
    if unrealized_gain < min_gain:
        return False

    # 2. Single-bar price surge
    bar_gain = (close - prev_close) / prev_close * 100
    if bar_gain < surge_pct:
        return False

    # 3. High volume on the surge
    vol = candles[i]["volume"]
    vol_ma = vol_sma_vals[i]
    if vol_ma is None or vol_ma <= 0 or vol < vol_ma * vol_mult:
        return False

    # 4. RSI above minimum (not a dead-cat bounce)
    rsi = rsi_vals[i]
    if rsi is None or rsi < rsi_min:
        return False

    # 5. Fast EMA trending up over lookback
    if fast_ema_vals[i] is None or fast_ema_vals[i - ema_lb] is None:
        return False
    if fast_ema_vals[i] <= fast_ema_vals[i - ema_lb]:
        return False

    return True
