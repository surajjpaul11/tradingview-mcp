"""Exit signal: End of Data — force-close at final bar."""

METADATA = {
    "name": "end_of_data",
    "abbrev": "EOD",
    "label": "End of Data",
    "desc": "Backtest ended with open position. Force-closed at final price.",
    "color": "#BDBDBD",
}


def check(ctx: dict) -> tuple[bool, str]:
    if ctx["i"] == ctx["n"] - 1:
        return True, "end_of_data"
    return False, ""
