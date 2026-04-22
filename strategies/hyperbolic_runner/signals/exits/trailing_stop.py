"""Exit signal: ATR Trailing Stop — 20x ATR from peak (very wide, for hyperbolic runners)."""

METADATA = {
    "name": "trailing_stop",
    "abbrev": "TRAIL",
    "label": "Trailing Stop (20x ATR)",
    "desc": "Very wide trailing stop: 20x ATR from peak price. Only triggers on catastrophic reversal.",
    "color": "#FF5722",
}


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    atr = ctx["atr_vals"]
    params = ctx["params"]

    if atr[i] is None or atr[i] <= 0:
        return False, ""

    atr_mult = params.get("atr_mult", 20.0)
    trail_dist = atr[i] * atr_mult

    if ctx["closes"][i] < ctx["peak_price"] - trail_dist:
        return True, "trailing_stop"

    return False, ""
