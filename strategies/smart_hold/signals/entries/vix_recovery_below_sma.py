"""Entry signal: VIX Recovery Below SMA — re-enter below the exit SMA after a
VIX-spike exit when the fast EMA has turned upward and fear is subsiding.

Rationale:
  `fast_reentry` targets the same VIX-spike recovery pattern but requires price
  to have already reclaimed the exit SMA. This signal fills the gap for cases where
  price is still below the SMA but the fast EMA has clearly reversed upward — indicating
  the short-term trend has turned before the slower SMA catches up.

  Dominant pattern identified in the 2y backtest:
    - QQQ T1 exits 2024-08-06 via vix_accel at 439.53 (SMA=473).
      By Aug 12, fast EMA is rising, price above EMA (451.38), RSI=43, VIX=20.7.
      Current ema_momentum fires Aug 13 at 462.58 — 1 bar later, +2.4% worse entry.
    - GOOGL T7 exits 2025-04-23 via vix_accel at 155.35 (SMA~164).
      By Apr 28, EMA rising, price above EMA (160.61), RSI=53, VIX=25.
      Current fast_reentry fires May 2 at 164.03 (above SMA) — 3 bars later, +2.1% worse entry.
    - SPY T1 exits 2024-08-07 via vix_accel. EMA recovers Aug 12 → fires at same
      price/bar as ema_momentum (neutral for SPY).

  Key distinction from fast_reentry:
    - fast_reentry: close > exit_sma (SMA already reclaimed — confirmed structural recovery)
    - This signal: close <= exit_sma (EMA leading before SMA reclaim — early entry)
    Because these are complementary by the SMA condition, they cannot both fire on
    the same bar for the same symbol.

Conditions (all must pass):
  1. Last completed trade was a vix_accelerated_exit.
  2. bars_since_exit >= 3 — avoid too-early bounces on day 1-2 post exit.
  3. VIX dropped >= 8pt from peak (strong normalization — same threshold as fast_reentry).
  4. VIX is now below vix_fear_entry (fear genuinely subsiding).
  5. close <= exit_sma — price still below SMA (if above, fast_reentry fires first).
  6. close > fast_ema — price above fast EMA (short-term momentum has reversed).
  7. fast EMA is rising for 2 consecutive bars — sustained momentum recovery, not a spike.
  8. RSI in [40, 65] — recovery zone: not in oversold panic, not yet overbought.
  9. in_chop intentionally bypassed — same rationale as fast_reentry: after a VIX spike,
     multiple VIX-driven exits naturally trigger in_chop, but these are not true chop.
     Tighter guards (VIX 8pt decline, 2-bar EMA, RSI ceiling) replace the chop filter.

Safety notes:
  - The EMA-rising-2-bars condition prevents firing on single-bar bounces (dead cats).
  - The RSI ceiling at 65 prevents chasing if recovery has already run far.
  - The VIX < vix_fear_entry condition prevents firing when fear is still elevated (> 30).
  - No SMA guard needed (close <= exit_sma already limits this to sub-SMA entries).
"""

METADATA = {
    "name": "vix_recovery_below_sma",
    "abbrev": "VIX-RSMA",
    "label": "VIX Recovery Below SMA",
    "desc": "Re-enter below SMA after vix_accel exit when fast EMA reverses up and VIX normalizes.",
    "side": "long",
    "color": "#AB47BC",
}


def check(ctx: dict) -> bool:
    i = ctx["i"]
    if i < 4:
        return False

    # Intentionally bypass in_chop — same rationale as fast_reentry.
    # Multiple VIX-driven exits cause in_chop=True but this is not structural chop.

    # Must have at least one completed trade
    trades = ctx.get("trades", [])
    if not trades:
        return False

    last_trade = trades[-1]
    if last_trade.get("exit_reason") != "vix_accelerated_exit":
        return False

    # bars_since_exit >= 3 — avoid catching too-early bounces day 1-2 post exit
    last_exit_date = last_trade.get("exit_date", "")
    candles = ctx["candles"]
    bars_since = 0
    for j in range(i, max(0, i - 30), -1):
        if candles[j]["date"] <= last_exit_date:
            break
        bars_since += 1
    if bars_since < 3:
        return False

    # VIX must be available and declining from its peak by at least 8pts
    vix_val = ctx["vix_val"]
    vix_peak = ctx["vix_peak"]
    if vix_val is None or vix_peak is None:
        return False

    p = ctx["params"]
    vix_decline_needed = p.get("vix_fast_reentry_decline", 8.0)
    if vix_peak - vix_val < vix_decline_needed:
        return False

    # VIX must be below fear threshold (fear genuinely subsiding, not just briefly dipping)
    vix_fear = p.get("vix_fear_entry", 30.0)
    if vix_val >= vix_fear:
        return False

    # Price must be BELOW the exit SMA — if above, fast_reentry already fires
    closes = ctx["closes"]
    close = closes[i]
    exit_sma = ctx["exit_sma"]
    if exit_sma[i] is None:
        return False
    if close > exit_sma[i]:
        return False  # fast_reentry handles above-SMA recovery

    # Fast EMA must be rising for 2 consecutive bars — sustained momentum reversal
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None or fast_ema[i - 1] is None or fast_ema[i - 2] is None:
        return False
    if not (fast_ema[i] > fast_ema[i - 1] > fast_ema[i - 2]):
        return False

    # Price must be above the fast EMA (short-term trend has turned)
    if close <= fast_ema[i]:
        return False

    # RSI must be in recovery zone [40, 65] — recovering but not overbought
    rsi = ctx["rsi"]
    if rsi[i] is None:
        return False
    rsi_val = rsi[i]
    if rsi_val < 40 or rsi_val > 65:
        return False

    return True
