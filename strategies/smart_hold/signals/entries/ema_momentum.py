"""Entry signal: EMA Momentum — buy when price is above rising fast EMA for 2+ bars.

Disabled during chop (2+ exits in 30 bars for low/mid-vol stocks) to avoid whipsaws.
"""

METADATA = {
    "name": "ema_momentum",
    "abbrev": "EMA-MOM",
    "label": "EMA Momentum",
    "desc": "Price above rising fast EMA for 2+ bars — momentum re-entry.",
    "side": "long",
    "color": "#00BCD4",
}


def check(ctx: dict) -> bool:
    if ctx["in_chop"]:
        return False
    i = ctx["i"]
    if i < 3:
        return False
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None:
        return False
    closes = ctx["closes"]
    return (
        closes[i] > fast_ema[i]
        and closes[i - 1] > fast_ema[i - 1]
        and fast_ema[i] > fast_ema[i - 1]
        and fast_ema[i - 1] > fast_ema[i - 2]
    )
