"""Exit signal: Peak-Gain Trail — tighter trailing protection for medium winners.

When a position has ever reached a substantial peak gain (>= 20%) and price then
retraces >= 12% from its peak_price, exit to protect the accumulated profit.
This fires BEFORE the standard ATR trailing stop, which uses a wide 6x-ATR distance
that can give back 10-17pp from peak on medium winners.

Rationale:
  The ATR trailing stop (6x ATR, very wide) is designed for catastrophic drawdown
  protection — it accepts large peak-to-current drawdowns in exchange for staying in
  strong uptrends. For medium winners (20-40% peak gain), this leaves too much profit
  on the table: the position can peak at +27% but the ATR stop fires with only +11%.

  Dominant gap identified (GOOGL T4, 2024-09-25 to 2025-02-21):
    - Entry 161.49 → peak ~206.49 (+27.8% peak gain)
    - ATR trailing stop fired at 179.66 (+10.95% net)
    - Peak-to-exit drop: (206.49 - 179.66) / 206.49 = 13.0%
    - A 12% from-peak threshold would have fired at ~181.71 — capturing
      more profit before the ATR stop was hit.

  Key distinctions from existing exits:
    - profit_lock: fires when CURRENT gain >= 50% AND SMA slope just turns negative.
      Does not help for medium winners where SMA slope hasn't fully turned.
    - macd_reversal_exit: fires when CURRENT gain >= 18% AND 40+ bars AND MACD crosses.
      Requires a specific MACD histogram crossover, which may not yet have occurred.
    - trailing_stop: fires when close < peak - ATR * 6.0. Wide enough to let medium
      winners give back 10-17pp from peak — this signal fills that gap.
    - ma_breakdown: fires after 3+ bars below SMA. Lagging — fires after this signal.

  Safety guards:
    - min_peak_gain check (20% default): only activates if position EVER reached 20%+
      peak gain. Prevents firing on small 1-15% trades where ATR stop is appropriate.
    - max_peak_gain check (45% default): above this, profit_lock and macd_reversal_exit
      are better equipped (they have SMA/MACD context for precision).
    - min_bars_held check (20 default): prevents firing on fast-moving early entries
      that haven't had time to build a real peak.
    - The 12% from-peak threshold: at GOOGL's ~1.5-2% ATR, a 12% peak drop requires
      6+ unfavorable ATR moves — a genuine multi-week trend change, not daily noise.

  Why "peak gain" (not "current gain"):
    - By the time a 20%+ winner pulls back 12% from peak, current gain may only be
      8-12% — well below any "current gain >= X" threshold.
    - Example: entry 161.49, peak 206.49 (+27.8%), trailing stop at 179.66 (+11.25%)
      A "current gain >= 15%" check would MISS this scenario because current gain at
      exit is only 11.25%.
    - "Peak gain" captures the true intent: this position WAS a good winner and we
      should protect that profit on significant reversal.

  Zero impact on:
    - Small/medium trades with < 20% peak gain: min_peak_gain guard
    - Large mega-winners (GOOGL T8 at +92%): profit_lock fires first (slope crossover)
    - Fast exits (< 20 bars): min_bars_held guard
    - SPY/QQQ large sustained winners (T6/T7): their continuous uptrends never
      produce a 12% from-peak drop before macd_reversal_exit fires.

Trigger conditions (all must pass):
  1. Peak gain from entry >= peak_gain_min_pct (default: 20.0%) — position had a big win
  2. Peak gain from entry < peak_gain_max_pct (default: 45.0%) — not mega-winner range
  3. Bars held >= peak_gain_min_bars (default: 20) — position must be established
  4. Price dropped >= peak_gain_trail_pct (default: 12.0%) from peak_price
"""

METADATA = {
    "name": "peak_gain_trail",
    "abbrev": "PK-TRAIL",
    "label": "Peak Gain Trail",
    "desc": "Exit when position peaked at 20-45% gain and price drops 12%+ from its peak.",
    "color": "#FF7043",
}

PEAK_GAIN_MIN_PCT = 20.0    # minimum PEAK gain ever reached to activate (%)
PEAK_GAIN_MAX_PCT = 45.0    # maximum PEAK gain (above this, leave to profit_lock/macd_rev)
PEAK_GAIN_TRAIL_PCT = 12.0  # exit when price drops >= this % from peak_price
PEAK_GAIN_MIN_BARS = 20     # minimum bars held before this exit can activate


def check(ctx: dict) -> tuple[bool, str]:
    i = ctx["i"]
    if i < 2:
        return False, ""

    # Must have entry price context
    entry_price = ctx.get("entry_price")
    if entry_price is None or entry_price <= 0:
        return False, ""

    # Must have peak price context (tracked by engine — max close since entry)
    peak_price = ctx.get("peak_price")
    if peak_price is None or peak_price <= 0:
        return False, ""

    # Compute peak gain from entry (how much the position ever gained at best)
    peak_gain_pct = (peak_price - entry_price) / entry_price * 100

    # Check peak gain bounds — must be in the medium-winner range
    p = ctx.get("params", {})
    min_peak = p.get("peak_gain_min_pct", PEAK_GAIN_MIN_PCT)
    max_peak = p.get("peak_gain_max_pct", PEAK_GAIN_MAX_PCT)
    if peak_gain_pct < min_peak:
        return False, ""
    if peak_gain_pct >= max_peak:
        return False, ""  # Large winners handled by profit_lock / macd_reversal_exit

    # Check minimum bars held — require established position
    min_bars = p.get("peak_gain_min_bars", PEAK_GAIN_MIN_BARS)
    candles = ctx["candles"]
    trades = ctx.get("trades", [])
    if trades:
        last_exit_date = trades[-1].get("exit_date", "")
        bars_held = 0
        for j in range(i, max(0, i - 500), -1):
            if candles[j]["date"] <= last_exit_date:
                break
            bars_held += 1
    else:
        bars_held = i  # First trade: count from bar 1

    if bars_held < min_bars:
        return False, ""

    # Check peak-to-current drawdown
    close = ctx["close"]
    trail_pct = p.get("peak_gain_trail_pct", PEAK_GAIN_TRAIL_PCT)
    drop_from_peak_pct = (peak_price - close) / peak_price * 100

    if drop_from_peak_pct < trail_pct:
        return False, ""

    return True, "peak_gain_trail"
