"""Entry signal: VIX Extreme Fear — buy on bullish candle when VIX >= extreme threshold."""

METADATA = {
    "name": "vix_extreme_fear",
    "abbrev": "VIX-FEAR",
    "label": "VIX Extreme Fear",
    "desc": "VIX >= extreme threshold + bullish candle. Peak panic buy signal.",
    "side": "long",
    "color": "#7C4DFF",
}


def check(ctx: dict) -> bool:
    vix_val = ctx["vix_val"]
    if vix_val is None:
        return False
    threshold = ctx["params"].get("vix_extreme", 35.0)
    c = ctx["candle"]
    return vix_val >= threshold and c["close"] > c["open"]
