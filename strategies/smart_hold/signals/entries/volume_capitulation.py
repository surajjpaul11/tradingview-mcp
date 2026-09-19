"""Entry signal: Volume Capitulation — buy after selling climax (price decline + volume spike + RSI weak + reversal).

Status: DISABLED in registry.py — catches false bottoms in 2y backtest (March 2025 trap).
Kept as a standalone file for future re-evaluation with longer datasets or additional filters.
"""

METADATA = {
    "name": "volume_capitulation",
    "abbrev": "VOL-CAP",
    "label": "Volume Capitulation",
    "desc": "Consecutive bars of declining price with volume spike + RSI weakness + bullish reversal.",
    "side": "long",
    "color": "#E040FB",
}


def check(ctx: dict) -> bool:
    i = ctx["i"]
    p = ctx["params"]
    cap_bars = p.get("capitulation_bars", 3)
    cap_vol_mult = p.get("capitulation_vol_mult", 2.0)

    if i < cap_bars + 1:
        return False
    vol_sma = ctx["vol_sma"]
    if vol_sma[i - 1] is None:
        return False

    closes = ctx["closes"]
    volumes = ctx["volumes"]
    rsi = ctx["rsi"]
    c = ctx["candle"]
    close = ctx["close"]

    # Check PREVIOUS bar(s) for the climax pattern
    price_decline = closes[i - 1] < closes[i - 1 - cap_bars]
    down_bars = sum(1 for j in range(i - cap_bars, i) if closes[j] < closes[j - 1])
    mostly_down = down_bars >= cap_bars - 1
    vol_spike = volumes[i - 1] >= vol_sma[i - 1] * cap_vol_mult

    if price_decline and mostly_down and vol_spike:
        rsi_weak = rsi[i] is not None and rsi[i] < 40
        if rsi_weak and close > c["open"] and close > closes[i - 1]:
            return True
    return False
