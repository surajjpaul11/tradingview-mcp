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
    close = closes[i]

    # SMA slope guard: when price is barely above the exit SMA but SMA is declining sharply,
    # this is a false breakout into a correction — block the entry.
    # Only applies when price > exit_sma (below-SMA ema_momentum entries are legitimate
    # recoveries where fast EMA leads SMA, e.g. GOOGL 2024-09-25 +10.95%).
    exit_sma = ctx["exit_sma"]
    slope_lb = ctx.get("slope_lb", 5)
    if exit_sma[i] is not None and close > exit_sma[i]:
        if i >= slope_lb and exit_sma[i - slope_lb] is not None:
            sma_slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
            if sma_slope < -0.002:
                return False  # Price above declining SMA — false breakout, not a real recovery

    return (
        close > fast_ema[i]
        and closes[i - 1] > fast_ema[i - 1]
        and fast_ema[i] > fast_ema[i - 1]
        and fast_ema[i - 1] > fast_ema[i - 2]
    )
