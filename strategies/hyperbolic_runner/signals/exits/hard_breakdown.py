"""Exit signal: Hard Breakdown — close < 20-period low for 2+ bars AND RSI < 40."""

METADATA = {
    "name": "hard_breakdown",
    "abbrev": "HARD-BRK",
    "label": "Hard Breakdown",
    "desc": "Close below 20-period low for 2+ consecutive bars AND RSI < 40.",
    "color": "#ef5350",
}


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    closes = ctx["closes"]
    rsi = ctx["rsi_vals"]
    params = ctx["params"]

    if i < 2:
        return False, ""

    rsi_breakdown = params.get("rsi_breakdown", 40)
    low_period = params.get("breakdown_low_period", 20)

    # Check RSI condition
    if rsi[i] is None or rsi[i] >= rsi_breakdown:
        return False, ""

    # Compute 20-period low (looking back from i-1, so not including current bar)
    start = max(0, i - low_period)
    period_low = min(closes[j] for j in range(start, i))

    # Must be below 20-period low for current AND previous bar
    curr_below = closes[i] < period_low
    prev_below = closes[i - 1] < period_low

    if curr_below and prev_below:
        return True, "hard_breakdown"

    return False, ""
