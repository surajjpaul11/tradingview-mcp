"""Entry signal: EMA Reclaim — buy when price reclaims fast EMA, outside consolidation, in explosive cluster."""

METADATA = {
    "name": "ema_reclaim",
    "abbrev": "EMA-RCL",
    "label": "EMA Reclaim",
    "desc": "Price reclaims fast EMA outside consolidation zone (or in confirmed explosive cluster).",
    "side": "long",
    "color": "#4CAF50",
}


def _is_consolidating(ctx: dict) -> bool:
    """Return True if market is in consolidation: RSI stuck 35-65 for 5+ bars AND ATR < 0.7x median for 5+ bars."""
    i = ctx["i"]
    rsi = ctx["rsi_vals"]
    atr = ctx["atr_vals"]
    params = ctx["params"]

    rsi_low = params.get("consolidation_rsi_low", 35)
    rsi_high = params.get("consolidation_rsi_high", 65)
    rsi_bars = params.get("consolidation_rsi_bars", 5)
    atr_ratio = params.get("consolidation_atr_ratio", 0.7)
    atr_bars = params.get("consolidation_atr_bars", 5)
    median_atr = ctx.get("median_atr", None)

    # Check RSI stuck in mid-zone
    rsi_stuck_count = 0
    for j in range(max(0, i - rsi_bars + 1), i + 1):
        if rsi[j] is not None and rsi_low <= rsi[j] <= rsi_high:
            rsi_stuck_count += 1

    # Check ATR below threshold
    atr_low_count = 0
    if median_atr is not None and median_atr > 0:
        for j in range(max(0, i - atr_bars + 1), i + 1):
            if atr[j] is not None and atr[j] < atr_ratio * median_atr:
                atr_low_count += 1

    return rsi_stuck_count >= rsi_bars and atr_low_count >= atr_bars


def _in_explosive_cluster(ctx: dict) -> bool:
    """Return True if in explosive cluster: rolling count of 10%+ moves in last 30 bars >= 2."""
    i = ctx["i"]
    closes = ctx["closes"]
    params = ctx["params"]

    window = params.get("cluster_window", 30)
    move_pct = params.get("cluster_move_pct", 10.0)
    min_count = params.get("cluster_min_count", 2)

    count = 0
    start = max(1, i - window + 1)
    for j in range(start, i + 1):
        if closes[j - 1] > 0:
            bar_move = abs(closes[j] - closes[j - 1]) / closes[j - 1] * 100
            if bar_move >= move_pct:
                count += 1
    return count >= min_count


def check(ctx: dict) -> bool:
    i = ctx["i"]
    if i < 2:
        return False

    fast_ema = ctx["fast_ema_vals"]
    closes = ctx["closes"]

    if fast_ema[i] is None or fast_ema[i - 1] is None:
        return False

    # EMA reclaim: prev close was below EMA, current close is above
    prev_below = closes[i - 1] < fast_ema[i - 1]
    curr_above = closes[i] > fast_ema[i]
    if not (prev_below and curr_above):
        return False

    # Only enter if NOT consolidating, OR in explosive cluster
    consolidating = _is_consolidating(ctx)
    in_cluster = _in_explosive_cluster(ctx)

    if consolidating and not in_cluster:
        return False

    return True
