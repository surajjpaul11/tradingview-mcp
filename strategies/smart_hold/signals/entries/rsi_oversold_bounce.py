"""Entry signal: RSI Oversold Bounce — buy when RSI crosses back above oversold level with bullish candle."""

METADATA = {
    "name": "rsi_oversold_bounce",
    "abbrev": "RSI-BNC",
    "label": "RSI Oversold Bounce",
    "desc": "RSI crossed back above oversold level with bullish candle.",
    "side": "long",
    "color": "#2196F3",
}


def check(ctx: dict) -> bool:
    i = ctx["i"]
    if i < 1:
        return False
    rsi = ctx["rsi"]
    if rsi[i] is None or rsi[i - 1] is None:
        return False
    rsi_oversold = ctx["params"].get("rsi_oversold", 30)
    c = ctx["candle"]
    return rsi[i - 1] < rsi_oversold and rsi[i] >= rsi_oversold and c["close"] > c["open"]
