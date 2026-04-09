"""Entry signal: MACD Crossover — buy when MACD(12,26) crosses above signal(9).

Catches momentum inflection points during recoveries — fires when short-term
momentum turns positive relative to medium-term, often before price fully
reclaims the SMA. Filters out chop and overbought conditions.
"""

METADATA = {
    "name": "macd_crossover",
    "abbrev": "MACD-X",
    "label": "MACD Crossover",
    "desc": "MACD(12,26) crossed above signal(9) — momentum turning positive.",
    "side": "long",
    "color": "#9C27B0",
}


def check(ctx: dict) -> bool:
    if ctx["in_chop"]:
        return False
    i = ctx["i"]
    if i < 1:
        return False

    macd_line = ctx.get("macd_line")
    macd_signal = ctx.get("macd_signal")
    if macd_line is None or macd_signal is None:
        return False
    if macd_line[i] is None or macd_signal[i] is None:
        return False
    if macd_line[i - 1] is None or macd_signal[i - 1] is None:
        return False

    # Bullish crossover: MACD crosses above signal line
    crossed_up = macd_line[i] > macd_signal[i] and macd_line[i - 1] <= macd_signal[i - 1]
    if not crossed_up:
        return False

    # Price must be ABOVE exit SMA — no MACD entries during downtrends/corrections
    exit_sma = ctx["exit_sma"]
    close = ctx["close"]
    if exit_sma[i] is not None and close < exit_sma[i]:
        return False

    # SMA slope guard — reject entries when SMA is declining sharply
    slope_lb = ctx.get("slope_lb", 5)
    if i >= slope_lb and exit_sma[i] is not None and exit_sma[i - slope_lb] is not None:
        sma_slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
        if sma_slope < -0.005:
            return False

    # Fast EMA must also be rising — confirm momentum is genuinely recovering
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None or fast_ema[i - 1] is None:
        return False
    if fast_ema[i] <= fast_ema[i - 1]:
        return False

    # RSI must not be overbought — avoid late entries at peaks
    rsi = ctx["rsi"]
    if rsi[i] is not None and rsi[i] > 75:
        return False

    return True
