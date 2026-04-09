"""Exit signal: Profit Lock — protect large unrealized gains on trend reversal.

When a position has accumulated a large unrealized gain (>= PROFIT_LOCK_THRESHOLD%)
and the exit SMA slope just turns negative (was positive, now declining), exit
proactively before the full ma_breakdown confirmation fires.

Rationale:
  - Monster winners (>50% gain) take months to build, but can give back 5-15% before
    the standard 3-bar ma_breakdown confirmation fires.
  - The first bar where SMA slope turns negative (after a sustained positive slope)
    is the earliest reliable signal that the trend is reversing.
  - Regular trades (<50% gain) are not affected — they let the normal exit run.

Trigger conditions:
  1. Unrealized gain >= profit_lock_threshold (default: 50.0%)
  2. SMA slope was non-negative last bar, is now negative (trend turning point)
  3. Close is below fast EMA (momentum also declining)
  4. SMA slope must be at least -0.001 negative (not just noise)

Safety: trailing_stop is still active as catastrophic protection.
"""

METADATA = {
    "name": "profit_lock",
    "abbrev": "P-LOCK",
    "label": "Profit Lock",
    "desc": "Exit proactively when gain >= threshold and SMA slope just turns negative.",
    "color": "#FF9800",
}

# Default threshold — only trigger on large positions
PROFIT_LOCK_THRESHOLD = 50.0  # percent unrealized gain required


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    if i < 2:
        return False, ""

    # Get entry price from context
    entry_price = ctx.get("entry_price")
    if entry_price is None or entry_price <= 0:
        return False, ""

    close = ctx["close"]

    # Check unrealized gain
    unrealized_gain_pct = (close - entry_price) / entry_price * 100
    threshold = ctx.get("params", {}).get("profit_lock_threshold", PROFIT_LOCK_THRESHOLD)
    if unrealized_gain_pct < threshold:
        return False, ""

    # SMA slope just turned negative: slope[i] < 0 and slope[i-1] >= 0
    exit_sma = ctx["exit_sma"]
    slope_lb = ctx["slope_lb"]
    if exit_sma[i] is None or exit_sma[i - 1] is None:
        return False, ""
    if i < slope_lb + 1:
        return False, ""
    prev_i = i - 1
    if exit_sma[prev_i - slope_lb] is None or exit_sma[i - slope_lb] is None:
        return False, ""

    slope_now = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
    slope_prev = (exit_sma[prev_i] - exit_sma[prev_i - slope_lb]) / exit_sma[prev_i - slope_lb]

    # Slope must have just turned negative (crossover from >= 0 to < 0)
    if slope_prev < 0:
        return False, ""  # Already declining — ma_breakdown handles this
    if slope_now >= 0:
        return False, ""  # Still positive — no reversal yet
    if slope_now > -0.0005:
        return False, ""  # Too small a decline — noise, not a real reversal

    # Fast EMA should be declining too (confirm momentum is turning)
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None or fast_ema[i - 1] is None:
        return False, ""
    if fast_ema[i] >= fast_ema[i - 1]:
        return False, ""  # EMA still rising — divergence from SMA, not a clean reversal

    return True, "profit_lock"
