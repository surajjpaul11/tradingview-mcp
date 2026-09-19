"""Exit signal: ATR Trailing Stop — catastrophic drop protection."""

METADATA = {
    "name": "trailing_stop",
    "abbrev": "TRAIL",
    "label": "Trailing Stop",
    "desc": "ATR trailing stop hit — catastrophic drop protection.",
    "color": "#FF5722",
}


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    atr = ctx["atr"]
    if atr[i] is None or atr[i] <= 0:
        return False, ""
    trail_dist = atr[i] * ctx["trail_atr_mult_adj"]
    if ctx["close"] < ctx["peak_price"] - trail_dist:
        return True, "trailing_stop"
    return False, ""
