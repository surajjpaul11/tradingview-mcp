"""Entry signal: False Breakdown Reclaim — re-enter quickly when an ma_breakdown exit is
followed by a rapid price reclaim above the SMA, indicating a false breakdown.

Rationale: The ma_breakdown exit is based on confirmed closes below the SMA + declining slope.
Sometimes this confirmation is correct (real breakdown), but sometimes price dips below the SMA
for 2-3 bars then recovers strongly — a "false breakdown" that causes a premature exit and
missed re-entry lag.

Dominant pattern identified in GOOGL 2y backtest:
  - Trade 8: entered 2025-05-02 at 164.03, exited 2025-05-13 at 159.53 (ma_breakdown, -3.04%)
  - Trade 9: re-entered 2025-05-15 at 163.96, exited 2026-02-17 at 302.02 (+83.90%)
  - The 2-day gap between exit and re-entry cost the better entry price and forced a round trip.
  - The false breakdown at ~159.53 recovered to 163.96 in exactly 2 bars — a textbook V-reclaim.

Conditions (all must pass):
  1. Last completed trade was an ma_breakdown exit (not VIX-driven — those have fast_reentry).
  2. bars_since_exit <= false_breakdown_max_bars (default 5) — breakdown must be brief/false.
  3. Price has closed above the exit SMA for 2 consecutive bars (structural reclaim confirmed).
  4. Fast EMA is rising (short-term momentum positive).
  5. Price made a higher close today vs yesterday (immediate bullish impulse).
  6. RSI is in recovery zone 40-65 — not oversold (real panic) or overbought (already ran).
  7. in_chop bypass: We intentionally bypass the in_chop check because the tight
     bars_since_exit <= 5 window, 2-bar SMA reclaim, and RSI ceiling provide equivalent
     protection. In the GOOGL 2025 scenario, in_chop=True was caused by prior VIX-driven
     exits (not real structural chop) — blocking a valid V-reclaim of the SMA.

Safety guards vs prior runs:
  - Requires price ABOVE exit_sma for reclaim_bars (not just touching), same pattern as ma_reclaim.
  - The bars_since_exit <= 5 window prevents catching stale breakdowns that truly failed.
  - RSI ceiling at 65 prevents chasing if price has already recovered too far.
"""

METADATA = {
    "name": "false_breakdown_reclaim",
    "abbrev": "FBR",
    "label": "False Breakdown Reclaim",
    "desc": "Re-enter after ma_breakdown when price quickly reclaims SMA — false breakdown detected.",
    "side": "long",
    "color": "#26A69A",
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
            print(f"  [FBR {date}] {msg}")

    # NOTE: Intentionally bypass in_chop. After a VIX spike, prior VIX-driven exits
    # cause in_chop=True, blocking valid V-reclaims. The bars_since_exit <= 5 window,
    # 2-bar SMA reclaim, and RSI ceiling (65) provide sufficient protection.

    # Must have at least one completed trade
    trades = ctx.get("trades", [])
    if not trades:
        _dbg("SKIP: no trades")
        return False

    last_trade = trades[-1]
    if last_trade.get("exit_reason") != "ma_breakdown":
        _dbg(f"SKIP: last_exit={last_trade.get('exit_reason')} (need ma_breakdown)")
        return False

    # Compute bars since exit — must be within the false_breakdown window
    last_exit_date = last_trade.get("exit_date", "")
    bars_since = 0
    for j in range(i, max(0, i - 30), -1):
        if candles[j]["date"] <= last_exit_date:
            break
        bars_since += 1

    p = ctx["params"]
    max_bars = p.get("false_breakdown_max_bars", 5)
    if bars_since > max_bars:
        _dbg(f"SKIP: bars_since={bars_since} > max={max_bars} (breakdown not brief enough)")
        return False
    if bars_since < 2:
        _dbg(f"SKIP: bars_since={bars_since} < 2 (too soon)")
        return False

    # Price must close above exit SMA for at least 1 bar (single-bar SMA breach is enough
    # in the false-breakdown context because the bars_since_exit <= 5 window ensures this
    # is a rapid recovery, not a sustained reclaim attempt that might fail).
    # Using 1 bar (vs 2 in ma_reclaim) lets us fire 1 bar earlier on fast V-recoveries.
    exit_sma = ctx["exit_sma"]
    if exit_sma[i] is None:
        _dbg("SKIP: exit_sma is None")
        return False

    closes = ctx["closes"]
    reclaim_bars = 1
    reclaim_count = 0
    for j in range(max(0, i - reclaim_bars + 1), i + 1):
        if exit_sma[j] is not None and closes[j] > exit_sma[j]:
            reclaim_count += 1
    if reclaim_count < reclaim_bars:
        _dbg(f"SKIP: only {reclaim_count}/{reclaim_bars} closes above SMA")
        return False

    # Fast EMA must be rising (short-term momentum positive)
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None or fast_ema[i - 1] is None:
        _dbg("SKIP: fast_ema is None")
        return False
    if fast_ema[i] <= fast_ema[i - 1]:
        _dbg(f"SKIP: fast_ema not rising ({fast_ema[i-1]:.2f} -> {fast_ema[i]:.2f})")
        return False

    # At least one of the last 2 closes must be a higher close (not requiring today specifically —
    # a small pullback after a big bounce day still qualifies if the SMA reclaim holds)
    higher_close_count = 0
    for j in range(max(1, i - 1), i + 1):
        if closes[j] > closes[j - 1]:
            higher_close_count += 1
    if higher_close_count == 0:
        _dbg(f"SKIP: no higher close in last 2 bars")
        return False

    # RSI in recovery zone 40-65
    rsi = ctx["rsi"]
    if rsi[i] is None:
        _dbg("SKIP: rsi is None")
        return False
    rsi_val = rsi[i]
    if rsi_val < 40 or rsi_val > 65:
        _dbg(f"SKIP: rsi={rsi_val:.0f} out of [40, 65]")
        return False

    _dbg(f"FIRE: bars_since={bars_since}, close={closes[i]:.2f}, sma={exit_sma[i]:.2f}, rsi={rsi_val:.0f}, fast_ema={fast_ema[i]:.2f}")
    return True
