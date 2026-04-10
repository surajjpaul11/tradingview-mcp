"""Exit signal: MA Breakdown — exit on confirmed close below SMA with declining slope.

Adaptive to volatility (more confirmation bars for volatile stocks).
Returns 'vix_accelerated_exit' as the reason when VIX accelerates the exit.

Guard: MACD histogram positive-momentum suppressor (two conditions, either is sufficient).

Condition 1 (v11): hist > 1.0 AND dist > -3%
  Blocks exits when MACD momentum is strongly bullish — price is near SMA but MACD is
  accelerating hard upward, indicating a short-term dip in a recovering market.
  - SPY 2026-04-06: hist=+1.14 (blocked — +3.5% improvement)
  - GOOGL 2026-04-07: hist=+1.78 (blocked — +4.8% improvement)
  - QQQ 2025-04-15: hist=+1.54, dist=-6.67% — NOT blocked (dist<-3%, genuine crash)

Condition 2 (v12): hist > 0 AND hist_prev < 0 AND dist > -3%
  Blocks exits when MACD histogram just crossed from negative to positive (fresh momentum
  crossover) while price is near SMA. The crossover signals the start of a new bullish
  momentum cycle — exiting during bar-1 of a MACD-positive phase is premature.
  - QQQ 2026-04-06: hist=+0.698, hist_prev=-0.242 (blocked — +4.06% improvement)
  - GOOGL 2026-03-17: hist=+0.930, hist_prev=+0.463 — NOT blocked (already positive, no crossover)
  - All other exits: hist_prev >= 0 or dist < -3% — unaffected
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

    # MACD histogram positive-momentum suppressor (two conditions, OR logic).
    # Both require: close > exit_sma * 0.97 (price within 3% of SMA)
    # When price is far below SMA (>3% down), the breakdown IS real even with positive MACD
    # (e.g. QQQ Apr 2025 tariff shock: hist=+1.54, dist=-6.7% — correctly not blocked).
    #
    # Condition 1 (v11): hist > 1.0
    #   Strongly positive MACD — price is near SMA but momentum is hard upward.
    #
    # Condition 2 (v12): hist > 0 AND hist_prev < 0
    #   MACD histogram just crossed from negative to positive (fresh momentum crossover).
    #   Bar-1 of a positive MACD cycle after a bearish phase — exiting now is premature.
    #   QQQ 2026-04-06: hist=+0.698, hist_prev=-0.242 → next 3 bars +3.69% (correctly blocked)
    macd_line = ctx["macd_line"]
    macd_signal = ctx["macd_signal"]
    if macd_line[i] is not None and macd_signal[i] is not None:
        macd_hist = macd_line[i] - macd_signal[i]
        sma_val = exit_sma[i]
        if sma_val is not None and close > sma_val * 0.97:
            # Condition 1: strongly positive MACD (v11 rule)
            if macd_hist > 1.0:
                return False, ""
            # Condition 2: fresh MACD histogram crossover negative->positive (v12 rule)
            if macd_hist > 0 and i > 0 and macd_line[i - 1] is not None and macd_signal[i - 1] is not None:
                macd_hist_prev = macd_line[i - 1] - macd_signal[i - 1]
                if macd_hist_prev < 0:
                    return False, ""

    # Determine reason
    if vix_val is not None and vix_val >= vix_exit_boost and needed < exit_confirm:
        return True, "vix_accelerated_exit"
    return True, "ma_breakdown"
