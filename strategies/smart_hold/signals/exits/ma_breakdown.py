"""Exit signal: MA Breakdown — exit on confirmed close below SMA with declining slope.

Adaptive to volatility (more confirmation bars for volatile stocks).
Returns 'vix_accelerated_exit' as the reason when VIX accelerates the exit.

Guard: MACD histogram positive-momentum suppressor.
When MACD histogram > 1.0 (strongly bullish momentum), the exit is suppressed — price is
below SMA but MACD is accelerating upward, indicating a short-term dip during a recovery,
not a genuine structural breakdown. Threshold 1.0 was calibrated on 2y backtest:
  - SPY 2026-04-06: hist=+1.14 (blocked — +3.5% improvement)
  - GOOGL 2026-04-07: hist=+1.78 (blocked — +4.8% improvement)
  - All other exits: hist < 1.0 (unblocked — preserves correct protective exits)
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

    # MACD histogram positive-momentum suppressor.
    # When MACD is strongly accelerating upward (hist > 1.0) AND price is within 3% of SMA,
    # the dip below SMA is a short-term pullback in a recovering market, NOT a genuine
    # structural breakdown. Block exit to avoid premature exits during recoveries.
    # Two conditions required to avoid false suppression:
    #   1. hist > 1.0 — filters out mild positive readings during VIX-spike dead-cat bounces
    #   2. close > exit_sma * 0.97 — when price is far below SMA (>3%), the breakdown IS real
    #      even with positive MACD (e.g. QQQ Apr 2025 tariff shock: hist=+1.54, dist=-6.7%)
    macd_line = ctx["macd_line"]
    macd_signal = ctx["macd_signal"]
    if macd_line[i] is not None and macd_signal[i] is not None:
        macd_hist = macd_line[i] - macd_signal[i]
        sma_val = exit_sma[i]
        if macd_hist > 1.0 and sma_val is not None and close > sma_val * 0.97:
            return False, ""

    # Determine reason
    if vix_val is not None and vix_val >= vix_exit_boost and needed < exit_confirm:
        return True, "vix_accelerated_exit"
    return True, "ma_breakdown"
