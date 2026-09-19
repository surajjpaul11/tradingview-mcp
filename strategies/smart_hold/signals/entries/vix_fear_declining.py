"""Entry signal: VIX Fear Declining — buy when VIX is elevated but declining from peak."""

METADATA = {
    "name": "vix_fear_declining",
    "abbrev": "VIX-DEC",
    "label": "VIX Fear Declining",
    "desc": "VIX >= fear threshold but declining from peak — fear is peaking, enter on reversal.",
    "side": "long",
    "color": "#B388FF",
}


def check(ctx: dict) -> bool:
    vix_val = ctx["vix_val"]
    vix_peak = ctx["vix_peak"]
    if vix_val is None or vix_peak is None:
        return False
    p = ctx["params"]
    vix_fear = p.get("vix_fear_entry", 30.0)
    vix_decline = p.get("vix_entry_decline", 3.0)
    c = ctx["candle"]
    i = ctx["i"]
    rsi = ctx["rsi"]
    if vix_val >= vix_fear and vix_peak - vix_val >= vix_decline:
        if c["close"] > c["open"] and rsi[i] is not None and rsi[i] < 45:
            return True
    return False
