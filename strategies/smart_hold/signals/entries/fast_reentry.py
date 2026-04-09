"""Entry signal: Fast Re-entry — re-enter quickly after a VIX-accelerated exit when
fear is subsiding and price shows immediate momentum recovery.

Rationale: When the strategy exits early due to a VIX spike (vix_accelerated_exit),
the sell is defensive — but if VIX then retreats and price bounces strongly (2+
consecutive bullish closes above the fast EMA), re-entering earlier than standard
signals would capture the fast recovery move. This was the dominant missed-upside
pattern in the GOOGL 2y backtest: after VIX-driven exits, price often recovered
3-6% within 5-8 bars before any other entry signal fired.

Conditions:
  1. Last completed trade was a vix_accelerated_exit (defensive panic sell).
  2. VIX has dropped >= vix_fast_reentry_decline pts from peak (fear subsiding).
  3. Price closed higher for 2 consecutive bars (immediate recovery momentum).
  4. Price is above the fast EMA (short-term trend turning positive).
  5. Price is above the exit SMA (structural uptrend — prevents re-entry in downtrend).
  6. RSI is between 35-68 (recovering, not oversold or overbought).
  7. bars_since_exit >= 3 (avoid catching too-early bounces on day 1-2 post exit).
  8. in_chop intentionally bypassed — after a VIX spike, multiple exits are VIX-driven
     (not true chop). Tighter VIX decline + SMA guards replace the chop filter.

Fix vs Run #1: Added condition 5 (close > exit_sma). In Run #1 this guard was absent,
causing bad re-entries during structural downtrends (QQQ -4.69% vs_BH regression).
"""

METADATA = {
    "name": "fast_reentry",
    "abbrev": "FAST-RE",
    "label": "Fast Re-entry",
    "desc": "Re-enter after VIX-accelerated exit when VIX declining + 2 bullish closes above fast EMA.",
    "side": "long",
    "color": "#FF6F00",
}


_DEBUG = False  # Set to True to enable verbose tracing
_DEBUG_WINDOW = ("2025-04-23", "2025-05-07")


def check(ctx: dict) -> bool:
    i = ctx["i"]
    candles = ctx["candles"]
    date = candles[i]["date"]

    if i < 5:
        return False

    def _dbg(msg):
        if _DEBUG and _DEBUG_WINDOW[0] <= date <= _DEBUG_WINDOW[1]:
            print(f"  [FAST-RE {date}] {msg}")

    # Require last exit was a VIX-accelerated exit
    # NOTE: We intentionally do NOT check in_chop here — after a VIX spike there will
    # naturally be multiple recent exits (causing in_chop=True), but these are
    # VIX-driven exits, not true chop. We apply tighter VIX normalization and SMA
    # guards instead to ensure quality.
    trades = ctx.get("trades", [])
    if not trades:
        _dbg("SKIP: no trades")
        return False
    last_trade = trades[-1]
    if last_trade.get("exit_reason") != "vix_accelerated_exit":
        _dbg(f"SKIP: last_exit={last_trade.get('exit_reason')}")
        return False

    # Estimate bars since last exit — require at least 3 bars to avoid too-early re-entry
    last_exit_date = last_trade.get("exit_date", "")
    bars_since = 0
    for j in range(i, max(0, i - 30), -1):
        if candles[j]["date"] <= last_exit_date:
            break
        bars_since += 1
    if bars_since < 3:
        _dbg(f"SKIP: bars_since={bars_since} < 3")
        return False

    # VIX must be available and declining from its peak
    vix_val = ctx["vix_val"]
    vix_peak = ctx["vix_peak"]
    if vix_val is None or vix_peak is None:
        _dbg("SKIP: no VIX")
        return False

    p = ctx["params"]
    # Require strong VIX normalization (8 pts vs 5 pts in Run #1) for cleaner signals
    vix_decline_needed = p.get("vix_fast_reentry_decline", 8.0)
    if vix_peak - vix_val < vix_decline_needed:
        _dbg(f"SKIP: vix_decline={vix_peak - vix_val:.1f} < {vix_decline_needed}")
        return False

    # VIX must have come back below the fear threshold (fear is genuinely subsiding)
    vix_fear = p.get("vix_fear_entry", 30.0)
    if vix_val >= vix_fear:
        _dbg(f"SKIP: vix={vix_val:.1f} >= fear={vix_fear}")
        return False

    # Price must close higher for 2 consecutive bars (immediate recovery momentum)
    closes = ctx["closes"]
    if closes[i] <= closes[i - 1] or closes[i - 1] <= closes[i - 2]:
        _dbg(f"SKIP: not 2 consecutive up (c[-2]={closes[i-2]:.2f}, c[-1]={closes[i-1]:.2f}, c[0]={closes[i]:.2f})")
        return False

    # --- KEY FIX vs Run #1 ---
    # Price must be above exit SMA (structural uptrend guard).
    exit_sma = ctx["exit_sma"]
    if exit_sma[i] is None:
        _dbg("SKIP: exit_sma is None")
        return False
    if closes[i] <= exit_sma[i]:
        _dbg(f"SKIP: close={closes[i]:.2f} <= exit_sma={exit_sma[i]:.2f}")
        return False

    # Price must be above the fast EMA (short-term trend turning positive)
    fast_ema = ctx["fast_ema"]
    if fast_ema[i] is None:
        _dbg("SKIP: fast_ema is None")
        return False
    if closes[i] <= fast_ema[i]:
        _dbg(f"SKIP: close={closes[i]:.2f} <= fast_ema={fast_ema[i]:.2f}")
        return False

    # RSI must be in recovery range — not oversold (capitulation not over) or overbought (missed it)
    rsi = ctx["rsi"]
    if rsi[i] is None:
        _dbg("SKIP: rsi is None")
        return False
    rsi_val = rsi[i]
    if rsi_val < 35 or rsi_val > 68:
        _dbg(f"SKIP: rsi={rsi_val:.0f} out of [35, 68]")
        return False

    _dbg(f"FIRE: vix={vix_val:.1f}, decline={vix_peak-vix_val:.1f}, close={closes[i]:.2f}, rsi={rsi_val:.0f}")
    return True
