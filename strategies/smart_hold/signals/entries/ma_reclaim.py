"""Entry signal: MA Reclaim — buy when price reclaims SMA with consecutive closes above + rising EMA."""

METADATA = {
    "name": "ma_reclaim",
    "abbrev": "MA-RCL",
    "label": "MA Reclaim",
    "desc": "Price reclaimed SMA with consecutive closes above + rising fast EMA.",
    "side": "long",
    "color": "#4CAF50",
}


def check(ctx: dict) -> bool:
    i = ctx["i"]
    warmup = ctx["warmup"]
    if i < warmup:
        return False
    exit_sma = ctx["exit_sma"]
    if exit_sma[i] is None:
        return False
    closes = ctx["closes"]
    fast_ema = ctx["fast_ema"]
    reclaim_bars = ctx["params"].get("reentry_ma_reclaim", 2)

    above_count = 0
    for j in range(max(0, i - reclaim_bars + 1), i + 1):
        if exit_sma[j] is not None and closes[j] > exit_sma[j]:
            above_count += 1
    if above_count >= reclaim_bars:
        if fast_ema[i] is not None and fast_ema[i - 1] is not None:
            if fast_ema[i] > fast_ema[i - 1]:
                return True
    return False
