"""Exit signal: MA Breakdown — exit on confirmed close below SMA with declining slope.

Adaptive to volatility (more confirmation bars for volatile stocks).
Returns 'vix_accelerated_exit' as the reason when VIX accelerates the exit.
"""

METADATA = {
    "name": "ma_breakdown",
    "abbrev": "MA-BRK",
    "label": "MA Breakdown",
    "desc": "Confirmed close below SMA with declining slope + EMA below SMA. Adaptive to volatility.",
    "color": "#ef5350",
}


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    if i < ctx["warmup"]:
        return False, ""

    exit_sma = ctx["exit_sma"]
    if exit_sma[i] is None:
        return False, ""

    close = ctx["close"]
    bars_below_ma = ctx["bars_below_ma"]

    if close >= exit_sma[i]:
        return False, ""

    # Close is below SMA — check if enough bars have confirmed
    exit_confirm = ctx["exit_confirm"]
    vix_val = ctx["vix_val"]
    vix_exit_boost = ctx["vix_exit_boost"]

    needed = exit_confirm
    if vix_val is not None and vix_val >= vix_exit_boost:
        needed = max(2, needed - 1)

    if bars_below_ma < needed:
        return False, ""

    # Confirm: SMA slope is declining
    slope_lb = ctx["slope_lb"]
    if i < slope_lb or exit_sma[i - slope_lb] is None:
        return False, ""

    slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
    slope_threshold = ctx["slope_threshold"]
    if slope >= slope_threshold:
        return False, ""

    # Fast EMA must be below SMA
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None or fast_ema[i] >= exit_sma[i]:
        return False, ""

    # For high-vol stocks: also require 200 SMA declining
    vol_label = ctx["vol_label"]
    if vol_label == "high":
        sma_200 = ctx["sma_200"]
        if sma_200[i] is not None and i >= 10 and sma_200[i - 10] is not None:
            sma200_slope = sma_200[i] - sma_200[i - 10]
            if sma200_slope >= 0:
                return False, ""

    # Determine reason
    if vix_val is not None and vix_val >= vix_exit_boost and needed < exit_confirm:
        return True, "vix_accelerated_exit"
    return True, "ma_breakdown"
