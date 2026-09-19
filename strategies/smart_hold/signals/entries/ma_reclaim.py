"""Entry signal: MA Reclaim — buy when price reclaims SMA with consecutive closes above + rising EMA.

SMA200 macro-trend guard for high-volatility stocks (median ATR% > 1.3):
High-vol stocks (e.g. GOOGL, ATR%=1.48) exhibit large bear market rallies that briefly push
price above SMA50 without crossing SMA200. All historical ma_reclaim losses for GOOGL occurred
when price was BELOW SMA200 — bear rallies in the 2022 bear market (Mar, Jul, Dec 2022).
The one winning ma_reclaim for GOOGL (Sep 2024) occurred with price ABOVE SMA200.

ETFs (SPY, QQQ with ATR% <= 1.3): NO SMA200 guard applied. The 2022 ETF bear market showed
that blocking sub-SMA200 ma_reclaim causes cascades to ema_momentum 1-5 days later with
similar or worse results. The ETF bear market losses are more interconnected and cascade-prone.

ATR-adaptive approach mirrors the v19 bear gate SMA50 threshold (tighter for high-vol stocks,
unchanged for ETFs).
"""

METADATA = {
    "name": "ma_reclaim",
    "abbrev": "MA-RCL",
    "label": "MA Reclaim",
    "desc": "Price reclaimed SMA with consecutive closes above + rising fast EMA.",
    "side": "long",
    "color": "#4CAF50",
}


def check(ctx: dict) -> bool:
    i = ctx["i"]
    warmup = ctx["warmup"]
    if i < warmup:
        return False
    exit_sma = ctx["exit_sma"]
    if exit_sma[i] is None:
        return False
    closes = ctx["closes"]
    fast_ema = ctx["fast_ema"]
    reclaim_bars = ctx["params"].get("reentry_ma_reclaim", 2)

    # SMA200 macro-trend guard: for high-volatility stocks (median ATR% > 1.3) only.
    # High-vol stocks have dramatic bear market rallies that push price above SMA50 but not SMA200.
    # In these cases, ma_reclaim fires into dead-cat bounces (GOOGL 2022: -4.86%, -8.45%, -7.88%).
    # Requiring close > SMA200 blocks these false bear-rally reclaims while preserving genuine
    # recovery entries (GOOGL Sep 2024: price clearly above SMA200, +8.03%).
    # ETFs are exempt: their 2022 cascades showed blocking sub-SMA200 ma_reclaim leads to
    # a worse ema_momentum entry 1-5 days later, negating any benefit.
    median_atr_pct = ctx.get("median_atr_pct", 1.5)
    if median_atr_pct > 1.3:
        sma_200 = ctx["sma_200"]
        if sma_200[i] is not None and closes[i] <= sma_200[i]:
            return False  # High-vol stock with price below SMA200 — bear rally, not recovery

    above_count = 0
    for j in range(max(0, i - reclaim_bars + 1), i + 1):
        if exit_sma[j] is not None and closes[j] > exit_sma[j]:
            above_count += 1
    if above_count >= reclaim_bars:
        if fast_ema[i] is not None and fast_ema[i - 1] is not None:
            if fast_ema[i] > fast_ema[i - 1]:
                return True
    return False
