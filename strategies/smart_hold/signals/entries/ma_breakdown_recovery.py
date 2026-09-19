"""Entry signal: MA Breakdown Recovery — re-enter below the exit SMA after an
ma_breakdown exit when the fast EMA has clearly turned upward, signaling a
false breakdown where the SMA confirmation was premature.

Rationale:
  `ma_reclaim` (and `false_breakdown_reclaim`) both require price to close
  ABOVE the exit SMA for N consecutive bars before re-entering. This means
  the strategy misses the early part of the recovery when price is rising
  strongly but hasn't yet crossed the SMA.

  Analogous to `vix_recovery_below_sma` (which fires after vix_accel exits
  while price is still below SMA), this signal fires after ma_breakdown exits
  when the fast EMA reverses upward and price is rising toward the SMA but
  hasn't yet reclaimed it.

  Key distinction from ma_reclaim / false_breakdown_reclaim:
    - ma_reclaim: requires close > exit_sma for reclaim_bars (confirmed above SMA)
    - false_breakdown_reclaim: requires 2 closes above exit_sma (also above SMA)
    - This signal: close <= exit_sma — EMA-led recovery before SMA reclaim

  These are mutually exclusive by design (above vs below SMA), preventing
  signal-hop: whichever fires first is correct for that regime.

  Dominant pattern identified in QQQ 2y backtest (2026-04-10):
    - QQQ T2 exits 2024-09-05 via ma_breakdown @ 461.04 (SMA ~471).
      By Sep 11-12 (bars 4-5), fast EMA has turned upward, price above EMA
      (~468-471), RSI ~50, but price still below SMA.
      Current ma_reclaim fires Sep 13 @ 475.34 — 1-2 bars later, +2.4% worse.

Conditions (all must pass):
  1. Last completed trade was an ma_breakdown exit.
  2. bars_since_exit in [3, 7] — brief window: false breakdown resolves quickly;
     real breakdowns stay below EMA for longer.
  3. Price is BELOW exit SMA — if above, ma_reclaim or false_breakdown_reclaim fire.
  4. Price is ABOVE fast EMA — short-term trend has already reversed.
  5. fast EMA rising for 3 consecutive bars — confirms sustained recovery, not a spike.
  6. SMA slope over 5 bars > -0.008 — prevents firing when SMA is in steep decline
     (genuine bear market, not a temporary false breakdown).
  7. Price net higher over 3 bars: close[i] > close[i-3] — trending toward SMA.
  8. RSI in [38, 65] — recovery zone: not deeply oversold (real panic) or overbought.
  9. in_chop intentionally bypassed — tight bars_since_exit window + EMA 3-bar
     confirmation + SMA slope guard provide equivalent protection.

Safety notes:
  - The 3-bar EMA rising requirement (vs 2 bars in vix_recovery_below_sma) provides
    extra protection since ma_breakdown exits don't have the same VIX confirmation
    that vix_recovery_below_sma uses.
  - SMA slope guard (-0.008 threshold) blocks entry when the SMA is genuinely declining,
    distinguishing false breakdowns from real downtrends.
  - max_bars=7 ensures the signal expires well before a real breakdown fully develops.
  - Bear market regime gate (engine-level) provides additional protection.
"""

METADATA = {
    "name": "ma_breakdown_recovery",
    "abbrev": "MBR",
    "label": "MA Breakdown Recovery",
    "desc": "Re-enter below SMA after ma_breakdown when fast EMA reverses up — false breakdown detected.",
    "side": "long",
    "color": "#00897B",
}

_DEBUG = False
_DEBUG_WINDOW = ("2024-09-05", "2024-09-15")


def check(ctx: dict) -> bool:
    i = ctx["i"]
    warmup = ctx["warmup"]
    if i < warmup:
        return False

    candles = ctx["candles"]
    date = candles[i]["date"]

    def _dbg(msg):
        if _DEBUG and _DEBUG_WINDOW[0] <= date <= _DEBUG_WINDOW[1]:
            print(f"  [MBR {date}] {msg}")

    # NOTE: Intentionally bypass in_chop. The tight bars_since_exit window,
    # 3-bar EMA rising confirmation, and SMA slope guard provide protection.

    # Must have at least one completed trade
    trades = ctx.get("trades", [])
    if not trades:
        _dbg("SKIP: no trades")
        return False

    last_trade = trades[-1]
    if last_trade.get("exit_reason") != "ma_breakdown":
        _dbg(f"SKIP: last_exit={last_trade.get('exit_reason')} (need ma_breakdown)")
        return False

    # Compute bars since exit — must be within the false-breakdown window
    last_exit_date = last_trade.get("exit_date", "")
    bars_since = 0
    for j in range(i, max(0, i - 30), -1):
        if candles[j]["date"] <= last_exit_date:
            break
        bars_since += 1

    p = ctx["params"]
    max_bars = p.get("ma_breakdown_recovery_max_bars", 7)
    if bars_since > max_bars:
        _dbg(f"SKIP: bars_since={bars_since} > max={max_bars}")
        return False
    if bars_since < 3:
        _dbg(f"SKIP: bars_since={bars_since} < 3 (too soon)")
        return False

    closes = ctx["closes"]
    close = closes[i]

    # Price must be BELOW exit SMA — if above, ma_reclaim / false_breakdown_reclaim fire
    exit_sma = ctx["exit_sma"]
    if exit_sma[i] is None:
        _dbg("SKIP: exit_sma is None")
        return False
    if close > exit_sma[i]:
        _dbg(f"SKIP: close={close:.2f} > sma={exit_sma[i]:.2f} (ma_reclaim handles this)")
        return False

    # SMA slope guard — block when SMA is in genuine steep decline (real bear, not false breakdown)
    slope_lb = ctx.get("slope_lb", 5)
    if i >= slope_lb and exit_sma[i - slope_lb] is not None:
        sma_slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
        if sma_slope < -0.008:
            _dbg(f"SKIP: sma_slope={sma_slope:.5f} < -0.008 (genuine downtrend)")
            return False

    # Fast EMA must be rising for 3 consecutive bars — sustained recovery, not a dead cat
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None or fast_ema[i - 1] is None or fast_ema[i - 2] is None or fast_ema[i - 3] is None:
        _dbg("SKIP: fast_ema not available")
        return False
    if not (fast_ema[i] > fast_ema[i - 1] > fast_ema[i - 2] > fast_ema[i - 3]):
        _dbg(f"SKIP: fast_ema not rising 3 bars ({fast_ema[i-3]:.2f}->{fast_ema[i-2]:.2f}->{fast_ema[i-1]:.2f}->{fast_ema[i]:.2f})")
        return False

    # Price must be above fast EMA (short-term trend has reversed)
    if close <= fast_ema[i]:
        _dbg(f"SKIP: close={close:.2f} <= fast_ema={fast_ema[i]:.2f}")
        return False

    # Price net higher over 3 bars — confirms trending toward SMA (not stalling)
    if i < 3 or close <= closes[i - 3]:
        _dbg(f"SKIP: close not higher than 3 bars ago ({closes[i-3]:.2f} -> {close:.2f})")
        return False

    # RSI in recovery zone [38, 65]
    rsi = ctx["rsi"]
    if rsi[i] is None:
        _dbg("SKIP: rsi is None")
        return False
    rsi_val = rsi[i]
    if rsi_val < 38 or rsi_val > 65:
        _dbg(f"SKIP: rsi={rsi_val:.0f} out of [38, 65]")
        return False

    _dbg(f"FIRE: bars_since={bars_since}, close={close:.2f}, sma={exit_sma[i]:.2f}, "
         f"ema={fast_ema[i]:.2f}, rsi={rsi_val:.0f}, sma_slope={sma_slope:.5f}")
    return True
