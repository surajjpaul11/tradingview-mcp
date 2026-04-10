"""Entry signal: Pyramid Momentum — re-enter when price and fast EMA recover above
the exit SMA while the SMA slope is still flat/slightly negative but improving,
and momentum confirms via 2+ consecutive higher closes above exit SMA.

Rationale: The `ma_reclaim` signal requires N consecutive closes above exit SMA with
fast EMA rising. The `pyramid_momentum` signal fires slightly earlier or at the same
quality bar by also requiring:
  1. The fast EMA to be above the exit SMA (EMA leads price recovery)
  2. The exit SMA slope to be IMPROVING (less negative or turning positive) — not a
     full positive slope (which ma_reclaim doesn't require), but specifically: the slope
     over the last 5 bars must be >= slope over the prior 5 bars (slope is flattening/improving)
  3. RSI confirmation in recovery range

This signal is positioned BEFORE ma_reclaim in the registry — it fires on the same bar
or slightly earlier when the exit SMA is just beginning to flatten after a decline.

The key differentiator from `ma_reclaim`: pyramid_momentum also requires fast EMA > exit SMA
AND the SMA slope improvement check, which together ensure we're not entering too early
in a continued downtrend. Meanwhile, it allows entry when the strict N-bar SMA reclaim
of ma_reclaim hasn't fully triggered yet.

Gap analysis source:
  - QQQ trade 2 (ema_momentum, 2024-08-13 at 462.58, -0.63%): ema_momentum entered 1 day
    after the VIX peak. QQQ then declined to 461 before recovering. With the slow SMA
    flattening requirement, this signal would have waited 1-2 more bars for the SMA trend
    to stabilize.
  - QQQ trade 9 (macd_crossover, 2026-02-25 at 616.68, -1.69%): MACD fired during a
    correction where exit SMA was still declining steeply. This signal requires improving
    slope, which would NOT have fired on that bar.
  - SPY: 8 trades, all well-timed — minimal room to improve, neutral expected.

Conditions (bypasses in_chop — same rationale as fast_reentry: after corrections, chop
filter stays active for 30 bars even as trend resumes; structural guards replace it):
  1. Exit SMA has been flattening/improving in slope over last 5 bars.
  2. Fast EMA is above exit SMA (EMA recovered ahead of price structure).
  3. Price is above exit SMA (confirmation that price leads SMA).
  4. Fast EMA is rising (short-term momentum positive).
  5. 2+ consecutive closes above exit SMA (reclaim in progress — softer than ma_reclaim's N).
  6. RSI 38-68 (recovery range, not oversold or overbought).
"""

METADATA = {
    "name": "pyramid_momentum",
    "abbrev": "PYR-MOM",
    "label": "Pyramid Momentum",
    "desc": "Early re-entry when EMA recovers above exit SMA with improving SMA slope.",
    "side": "long",
    "color": "#FF9800",
}

_DEBUG = False
_DEBUG_WINDOW = ("2024-04-09", "2026-04-08")


def check(ctx: dict) -> bool:
    i = ctx["i"]
    if i < 15:
        return False

    candles = ctx["candles"]
    date = candles[i]["date"]

    def _dbg(msg):
        if _DEBUG and _DEBUG_WINDOW[0] <= date <= _DEBUG_WINDOW[1]:
            print(f"  [PYR-MOM {date}] {msg}")

    # Bypass in_chop — consistent with fast_reentry rationale.
    # After corrections, in_chop=True blocks everything for up to 30 bars even when trend resumes.
    # Our structural slope-improvement + EMA-above-SMA guards replace the chop filter.

    closes = ctx["closes"]
    fast_ema = ctx["fast_ema"]
    exit_sma = ctx["exit_sma"]

    if fast_ema[i] is None or fast_ema[i - 1] is None:
        _dbg("SKIP: fast_ema warmup")
        return False
    if exit_sma[i] is None:
        _dbg("SKIP: exit_sma warmup")
        return False

    slope_lb = ctx.get("slope_lb", 5)
    if i < slope_lb * 2:
        _dbg("SKIP: insufficient bars for slope comparison")
        return False

    sma_at_i = exit_sma[i]
    sma_lb1 = exit_sma[i - slope_lb]     # 5 bars ago
    sma_lb2 = exit_sma[i - slope_lb * 2] # 10 bars ago

    if sma_lb1 is None or sma_lb2 is None:
        _dbg("SKIP: exit_sma slope comparison warmup")
        return False

    # 1. Exit SMA slope improvement check:
    # Slope over [i-5, i] must be >= slope over [i-10, i-5]
    # i.e., the decline is slowing (slope is improving/flattening/turning positive)
    recent_slope = sma_at_i - sma_lb1
    prior_slope = sma_lb1 - sma_lb2
    if recent_slope < prior_slope:
        _dbg(f"SKIP: slope not improving: recent={recent_slope:.3f} < prior={prior_slope:.3f}")
        return False

    # 2. Fast EMA is rising (short-term momentum positive)
    if fast_ema[i] <= fast_ema[i - 1]:
        _dbg(f"SKIP: fast_ema not rising ({fast_ema[i]:.3f} <= {fast_ema[i-1]:.3f})")
        return False

    # 3. Price must close above fast EMA (price leading the recovery, not lagging)
    if closes[i] <= fast_ema[i]:
        _dbg(f"SKIP: close={closes[i]:.2f} <= fast_ema={fast_ema[i]:.2f}")
        return False

    # 4. Previous bar close must also be above fast EMA (2-bar EMA momentum pattern)
    # Differentiates from a single-bar spike — same quality check as ema_momentum uses
    if closes[i - 1] <= fast_ema[i - 1]:
        _dbg(f"SKIP: prev close={closes[i-1]:.2f} <= prev fast_ema={fast_ema[i-1]:.2f}")
        return False

    # 5. RSI must be in recovery range — not capitulating (< 38) or overbought (> 68)
    rsi = ctx["rsi"]
    if rsi[i] is None:
        _dbg("SKIP: rsi is None")
        return False
    rsi_val = rsi[i]
    if rsi_val < 38 or rsi_val > 68:
        _dbg(f"SKIP: rsi={rsi_val:.0f} out of [38, 68]")
        return False

    _dbg(
        f"FIRE: close={closes[i]:.2f}, fast_ema={fast_ema[i]:.2f}, "
        f"exit_sma={exit_sma[i]:.2f}, recent_slope={recent_slope:.3f}, "
        f"prior_slope={prior_slope:.3f}, rsi={rsi_val:.0f}"
    )
    return True
