"""Exit signal: EMA/SMA Death Cross Exit — protect profits when fast EMA crosses below SMA.

When the fast EMA crosses below the exit SMA on a profitable trade, this is an early
trend-reversal signal. Standard ma_breakdown waits for 3-5 confirmed closes below the SMA —
by the time that completes, the position has already given back 2-3% from the EMA cross.

This signal fires at the EMA/SMA death cross itself (EMA just dropped below SMA), capturing
the exit 1-3 bars before ma_breakdown confirmation, protecting accumulated gains.

Cross-symbol gap analysis (Run #19):
  GOOGL T4 (ema_momentum 161.49): trailed at peak 206.49, then trailing_stop fired at 179.66
    (only +10.95%). When EMA crossed below SMA near the 195-200 area, MACD was negative —
    an ema_sma_cross_exit at ~195 would capture +20%+ vs 10.95%. However this is bounded by
    the same gap-down risk as peak_gain_trail (prices can gap through the trigger).
  SPY T2 (vix_recovery_below_sma 533.27): ma_breakdown at 594.18 (+11.12%). When EMA crossed
    below SMA during the Feb 2025 decline, firing 1-2 bars earlier saves 0.5-1%.
  QQQ: Most exits have gain < 8% — this signal's min_gain guard keeps them untouched.

Trigger conditions (ALL must pass):
  1. unrealized_gain_pct >= min_gain (default: 8.0%) — only protect meaningful winners
  2. bars_held >= min_bars (default: 20) — avoid whipsaws on fresh entries
  3. EMA just crossed below SMA: fast_ema[i] < exit_sma[i] AND fast_ema[i-1] >= exit_sma[i-1]
     — the EXACT crossover bar (not already crossed)
  4. MACD histogram is negative (bearish momentum confirmed)
  5. MACD histogram is declining vs prior bar (momentum deteriorating, not just dipping)
  6. RSI < 50 — price losing upward momentum
  7. SMA is flat or declining (slope_lb bars slope <= 0.001) — not just a normal dip in uptrend
  8. bars_below_ma >= 1 — price already closed below SMA at least once (confirming real break)

Priority: Placed after macd_reversal_exit and before ma_breakdown in the exit signal list.
This ensures macd_reversal_exit still handles 18%+ gain trades with clear MACD crossovers,
while ema_sma_cross_exit handles 8-17% gain trades and edge cases where SMA slope guard
prevented macd_reversal_exit from firing.
"""

METADATA = {
    "name": "ema_sma_cross_exit",
    "abbrev": "EMA-X",
    "label": "EMA/SMA Death Cross Exit",
    "desc": "Exit on EMA/SMA death cross with negative MACD on profitable trade (8%+ gain, 20+ bars).",
    "color": "#9C27B0",
}

# Minimum unrealized gain to activate — protects only meaningful winners
EMA_CROSS_MIN_GAIN = 8.0    # percent
EMA_CROSS_MIN_BARS = 20     # min bars held before this exit can fire


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    if i < 3:
        return False, ""

    # Must have entry price context (in position)
    entry_price = ctx.get("entry_price")
    if entry_price is None or entry_price <= 0:
        return False, ""

    close = ctx["close"]

    # Condition 1: sufficient unrealized gain
    unrealized_gain_pct = (close - entry_price) / entry_price * 100
    min_gain = ctx.get("params", {}).get("ema_cross_min_gain", EMA_CROSS_MIN_GAIN)
    if unrealized_gain_pct < min_gain:
        return False, ""

    # Condition 2: held long enough to avoid whipsaw
    trades = ctx.get("trades", [])
    min_bars = ctx.get("params", {}).get("ema_cross_min_bars", EMA_CROSS_MIN_BARS)
    if trades:
        candles = ctx["candles"]
        last_exit_date = trades[-1].get("exit_date", "")
        bars_held = 0
        for j in range(i, max(0, i - 400), -1):
            if candles[j]["date"] <= last_exit_date:
                break
            bars_held += 1
    else:
        # First trade (initial_entry) — count from bar 1
        bars_held = i

    if bars_held < min_bars:
        return False, ""

    # Condition 3: EMA just crossed BELOW SMA (the exact crossover bar)
    fast_ema = ctx["fast_ema"]
    exit_sma = ctx["exit_sma"]
    if fast_ema[i] is None or exit_sma[i] is None:
        return False, ""
    if fast_ema[i - 1] is None or exit_sma[i - 1] is None:
        return False, ""

    # EMA must be below SMA NOW but was at or above SMA last bar
    if fast_ema[i] >= exit_sma[i]:
        return False, ""  # EMA still above SMA — no cross yet
    if fast_ema[i - 1] < exit_sma[i - 1]:
        return False, ""  # EMA was already below SMA — not a fresh cross (ma_breakdown handles this)

    # Condition 4 + 5: MACD histogram is negative AND declining
    macd_line = ctx.get("macd_line")
    macd_signal = ctx.get("macd_signal")
    if macd_line is None or macd_signal is None:
        return False, ""
    if macd_line[i] is None or macd_signal[i] is None:
        return False, ""
    if macd_line[i - 1] is None or macd_signal[i - 1] is None:
        return False, ""

    hist_now = macd_line[i] - macd_signal[i]
    hist_prev = macd_line[i - 1] - macd_signal[i - 1]

    if hist_now >= 0:
        return False, ""  # MACD histogram not negative — momentum still bullish
    if hist_now >= hist_prev:
        return False, ""  # MACD not declining (worsening) — not clear deterioration

    # Condition 6: RSI below 50 (price losing upward momentum)
    rsi = ctx.get("rsi")
    if rsi is None or rsi[i] is None:
        return False, ""
    if rsi[i] >= 50:
        return False, ""

    # Condition 7: SMA is flat or declining — not a dip in a strong uptrend
    slope_lb = ctx.get("slope_lb", 5)
    if i < slope_lb or exit_sma[i - slope_lb] is None:
        return False, ""
    sma_slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
    if sma_slope > 0.001:
        return False, ""  # SMA still rising strongly — EMA dip is likely temporary

    # Condition 8: At least 1 bar already closed below SMA (price has already breached SMA)
    bars_below_ma = ctx.get("bars_below_ma", 0)
    if bars_below_ma < 1:
        return False, ""  # Price hasn't even closed below SMA yet — too early

    return True, "ema_sma_cross_exit"
