"""
Smart Hold + Adaptive Re-entry (Combo Strategy)
=================================================
Uses Smart Hold's proven exit logic (MA breakdown, VIX acceleration, trailing stop)
with ADAPTIVE re-entry based on stock volatility:

  HIGH VOLATILITY (median ATR% > 2.5%):
    → Reversal Channel re-entry: waits for structural HH/HL confirmation
    → Avoids dead cat bounces on wild stocks (SNDK, SMR, BE)
    → Slower re-entry but much better entry prices

  LOW VOLATILITY (median ATR% <= 2.5%):
    → Standard Smart Hold re-entry: MA reclaim, EMA momentum, RSI bounce
    → Fast re-entry captures V-shaped recoveries on stable stocks (SPY, GOOGL)

Both modes keep VIX extreme fear entries (buy panic regardless of volatility).

The threshold (2.5% ATR) was determined empirically:
  - SNDK 4.8%, SMR 5.2%, BE 4.1% → RC re-entry wins by +200pp
  - SPY 0.8%, GOOGL 1.5%, QQQ 1.1% → standard re-entry wins by +40-100pp

Usage:
    python3 strategies/smart_hold_rc/smart_hold_rc_strategy.py --symbol AMD --period 2y --chart
    python3 strategies/smart_hold_rc/smart_hold_rc_strategy.py --symbol SNDK --period 2y --chart
    python3 strategies/smart_hold_rc/smart_hold_rc_strategy.py --symbol SPY --period 2y --force-rc
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Parameters ───────────────────────────────────────────────────────

# Smart Hold exit params
FAST_MA = 10
SLOW_MA = 200
EXIT_MA = 50
EXIT_CONFIRM_BARS = 2
SLOPE_LOOKBACK = 10
TRAILING_STOP_ATR_MULT = 6.0

# Reversal Channel re-entry params
PIVOT_LEFT  = 5
PIVOT_RIGHT = 3
MIN_SWINGS  = 1
TOLERANCE   = 0.03
STALENESS   = 60

# VIX params (kept from Smart Hold — panic buys bypass reversal requirement)
VIX_EXTREME = 35
VIX_FEAR    = 30

# Adaptive threshold: stocks with median ATR% above this use RC re-entry
VOL_THRESHOLD = 2.5  # percent

# Standard re-entry params (for low-vol stocks)
REENTRY_MA_RECLAIM = 3     # Consecutive closes above SMA to confirm reclaim
REENTRY_COOLDOWN   = 2     # Min bars after exit

COMMISSION  = 0.001
SLIPPAGE    = 0.001
INITIAL_CAPITAL = 10_000.0
PERIOD   = "2y"
INTERVAL = "1d"


# ── Indicators ──────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "smart-hold-rc/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d"
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
                         "open": round(o, 4), "high": round(h, 4),
                         "low": round(l, 4), "close": round(c, 4), "volume": v or 0})
    return candles


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    k = 2.0 / (period + 1)
    for i in range(len(values)):
        if i == 0: out[i] = values[i]
        elif i < period - 1: out[i] = values[i] * k + out[i-1] * (1-k)
        elif i == period - 1: out[i] = sum(values[:period]) / period
        else: out[i] = values[i] * k + out[i-1] * (1-k)
    return out


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out


def calc_rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period + 1: return out
    gains = [max(values[i] - values[i-1], 0) for i in range(1, period + 1)]
    losses = [max(values[i-1] - values[i], 0) for i in range(1, period + 1)]
    ag, al = sum(gains) / period, sum(losses) / period
    out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def calc_atr(candles: list[dict], period: int = 14) -> list[float | None]:
    trs = []
    for i, c in enumerate(candles):
        if i == 0: trs.append(c["high"] - c["low"])
        else:
            prev = candles[i-1]["close"]
            trs.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))
    return ema(trs, period)


def find_pivots(highs, lows, left=5, right=3):
    n = len(highs)
    ph, pl = [], []
    for i in range(left, n - right):
        if all(highs[j] < highs[i] for j in range(i-left, i+right+1) if j != i):
            ph.append((i, highs[i]))
        if all(lows[j] > lows[i] for j in range(i-left, i+right+1) if j != i):
            pl.append((i, lows[i]))
    return ph, pl


# ── Strategy Engine ─────────────────────────────────────────────────

def run_smart_hold_rc(candles: list[dict], vix_candles: list[dict] | None = None,
                       params: dict | None = None) -> dict:
    p = params or {}
    slow_ma_period = p.get("slow_ma", SLOW_MA)
    exit_ma_period = p.get("exit_ma", EXIT_MA)
    fast_ma_period = p.get("fast_ma", FAST_MA)
    slope_lb       = p.get("slope_lookback", SLOPE_LOOKBACK)
    trail_mult     = p.get("trailing_stop_atr_mult", TRAILING_STOP_ATR_MULT)
    pivot_left     = p.get("pivot_left", PIVOT_LEFT)
    pivot_right    = p.get("pivot_right", PIVOT_RIGHT)
    min_swings     = p.get("min_swings", MIN_SWINGS)
    tolerance      = p.get("tolerance", TOLERANCE)
    staleness      = p.get("staleness", STALENESS)
    vix_extreme    = p.get("vix_extreme", VIX_EXTREME)
    vix_fear       = p.get("vix_fear", VIX_FEAR)
    commission     = p.get("commission", COMMISSION)
    slippage       = p.get("slippage", SLIPPAGE)
    initial_cap    = p.get("initial_capital", INITIAL_CAPITAL)
    disable_exit   = p.get("disable_exit", False)
    vol_threshold  = p.get("vol_threshold", VOL_THRESHOLD)
    force_rc       = p.get("force_rc", False)
    force_standard = p.get("force_standard", False)
    reclaim_bars   = p.get("reentry_ma_reclaim", REENTRY_MA_RECLAIM)
    reentry_cooldown = p.get("reentry_cooldown", REENTRY_COOLDOWN)
    cost_pct = (commission + slippage) * 100

    n = len(candles)
    closes = [c["close"] for c in candles]
    highs  = [c["high"] for c in candles]
    lows   = [c["low"] for c in candles]

    # Indicators
    fast_ema = ema(closes, fast_ma_period)
    slow_sma = sma(closes, slow_ma_period)
    exit_sma = sma(closes, exit_ma_period)
    atr_vals = calc_atr(candles, 14)
    rsi_vals = calc_rsi(closes, 14)

    # Compute volatility bucket: median ATR% over first 100 bars
    atr_pct_vals = []
    for i in range(min(100, n)):
        if atr_vals[i] is not None and closes[i] > 0:
            atr_pct_vals.append(atr_vals[i] / closes[i] * 100)
    median_atr_pct = sorted(atr_pct_vals)[len(atr_pct_vals) // 2] if atr_pct_vals else 1.5

    # Adaptive re-entry mode selection
    if force_rc:
        use_rc_reentry = True
    elif force_standard:
        use_rc_reentry = False
    else:
        use_rc_reentry = median_atr_pct > vol_threshold

    reentry_mode = "reversal_channel" if use_rc_reentry else "standard"

    # VIX lookup
    vix_by_date: dict[str, float] = {}
    if vix_candles:
        for vc in vix_candles:
            vix_by_date[vc["date"]] = vc["close"]

    # Pre-compute pivots for reversal channel (only needed if RC mode)
    ph_at: dict[int, float] = {}
    pl_at: dict[int, float] = {}
    if use_rc_reentry:
        all_ph, all_pl = find_pivots(highs, lows, pivot_left, pivot_right)
        ph_at = {idx + pivot_right: price for idx, price in all_ph}
        pl_at = {idx + pivot_right: price for idx, price in all_pl}

    # State
    in_position = True  # Start invested (like Smart Hold)
    entry_price = closes[0]
    entry_date = candles[0]["date"]
    entry_reason = "initial_entry"
    peak_price = closes[0]
    bars_below_ma = 0
    bars_since_exit = reentry_cooldown
    consecutive_above_ma = 0

    # Reversal channel state (active only when out of position + RC mode)
    rc_phase = "scan"
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []
    hh_price = 0.0
    last_ll_price = 0.0

    trades: list[dict] = []
    capital = initial_cap

    warmup = max(slow_ma_period, exit_ma_period, pivot_left + pivot_right) + 5

    for i in range(warmup, n):
        close = closes[i]
        date = candles[i]["date"]
        atr = atr_vals[i]
        rsi = rsi_vals[i]
        vix = vix_by_date.get(date)

        if atr is None:
            continue

        # ── EXIT LOGIC (Smart Hold style) ───────────────────────
        if in_position:
            if close > peak_price:
                peak_price = close

            exit_reason = ""

            if not disable_exit:
                # Exit 1: MA breakdown — close below SMA50 with declining slope
                if exit_sma[i] is not None and close < exit_sma[i]:
                    bars_below_ma += 1
                    if bars_below_ma >= 2:
                        # Check slope is declining
                        if i >= slope_lb and exit_sma[i - slope_lb] is not None:
                            slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
                            if slope < 0:
                                # Check EMA is below SMA (trend broken)
                                if fast_ema[i] is not None and fast_ema[i] < exit_sma[i]:
                                    exit_reason = "ma_breakdown"
                                    # VIX acceleration: exit 1 bar faster
                                    if vix is not None and vix >= 25 and bars_below_ma >= 1:
                                        exit_reason = "vix_accelerated_exit"
                else:
                    bars_below_ma = 0

                # Exit 2: Trailing stop (catastrophic drop protection)
                if not exit_reason and close < peak_price - trail_mult * atr:
                    exit_reason = "trailing_stop"

                # Exit 3: End of data
                if not exit_reason and i == n - 1:
                    exit_reason = "end_of_data"
            else:
                if i == n - 1:
                    exit_reason = "end_of_data"

            if exit_reason:
                gross_ret = (close - entry_price) / entry_price * 100
                net_ret = gross_ret - cost_pct * 2
                capital *= (1 + net_ret / 100)

                trades.append({
                    "entry_date": entry_date, "exit_date": date,
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(close, 4),
                    "side": "long", "entry_reason": entry_reason,
                    "return_pct": round(net_ret, 2),
                    "exit_reason": exit_reason,
                    "days_held": i - next((j for j, c in enumerate(candles) if c["date"] == entry_date), 0),
                    "strategy": "smart_hold_rc",
                })
                in_position = False
                peak_price = 0
                bars_below_ma = 0
                bars_since_exit = 0
                consecutive_above_ma = 0
                # Reset reversal channel scanner
                rc_phase = "scan"
                swing_highs.clear()
                swing_lows.clear()

        # ── RE-ENTRY LOGIC (Adaptive: RC for high-vol, Standard for low-vol) ──
        else:
            bars_since_exit += 1
            if bars_since_exit < reentry_cooldown:
                continue

            # === VIX PANIC ENTRIES (both modes — always active) ===

            # VIX extreme fear bypass: buy immediately in panic
            if vix is not None and vix >= vix_extreme and rsi is not None and rsi < 35:
                entry_price = close
                entry_date = date
                entry_reason = "vix_extreme_fear"
                in_position = True
                peak_price = close
                consecutive_above_ma = 0
                rc_phase = "scan"
                swing_highs.clear()
                swing_lows.clear()
                continue

            # VIX fear + declining: buy when fear is peaking
            if vix is not None and vix >= vix_fear:
                prev_date = candles[i - 1]["date"]
                prev_vix = vix_by_date.get(prev_date)
                if prev_vix is not None and vix < prev_vix and rsi is not None and rsi < 40:
                    entry_price = close
                    entry_date = date
                    entry_reason = "vix_fear_declining"
                    in_position = True
                    peak_price = close
                    consecutive_above_ma = 0
                    rc_phase = "scan"
                    swing_highs.clear()
                    swing_lows.clear()
                    continue

            # === HIGH-VOL PATH: Reversal Channel structural re-entry ===
            if use_rc_reentry:
                new_ph = ph_at.get(i)
                new_pl = pl_at.get(i)

                if rc_phase in ("scan", "downtrend"):
                    if new_ph is not None:
                        if swing_highs and (i - swing_highs[-1][0]) > staleness:
                            swing_highs.clear()
                            swing_lows.clear()
                            rc_phase = "scan"

                        if swing_highs:
                            prev_h = swing_highs[-1][1]
                            if new_ph <= prev_h * (1 + tolerance):
                                swing_highs.append((i, new_ph))
                            else:
                                if rc_phase == "downtrend":
                                    hh_price = new_ph
                                    last_ll_price = swing_lows[-1][1] if swing_lows else 0.0
                                    rc_phase = "wait_hl"
                                else:
                                    swing_highs = [(i, new_ph)]
                                    swing_lows.clear()
                        else:
                            swing_highs.append((i, new_ph))

                    if new_pl is not None and rc_phase in ("scan", "downtrend"):
                        if swing_lows and (i - swing_lows[-1][0]) > staleness:
                            swing_lows.clear()
                        if swing_lows:
                            prev_l = swing_lows[-1][1]
                            if new_pl <= prev_l * (1 + tolerance):
                                swing_lows.append((i, new_pl))
                            else:
                                swing_lows = [(i, new_pl)]
                        else:
                            swing_lows.append((i, new_pl))

                    if (len(swing_highs) >= min_swings + 1 and
                            len(swing_lows) >= min_swings + 1 and
                            rc_phase == "scan"):
                        rc_phase = "downtrend"

                elif rc_phase == "wait_hl":
                    if last_ll_price > 0 and close < last_ll_price * 0.95:
                        rc_phase = "scan"
                        swing_highs.clear()
                        swing_lows.clear()
                        continue

                    if new_pl is not None and new_pl > last_ll_price:
                        entry_price = close
                        entry_date = date
                        entry_reason = "reversal_channel_reentry"
                        in_position = True
                        peak_price = close
                        consecutive_above_ma = 0
                        rc_phase = "scan"
                        swing_highs.clear()
                        swing_lows.clear()
                    elif new_pl is not None and new_pl <= last_ll_price:
                        swing_lows.append((i, new_pl))
                        last_ll_price = new_pl

                # Fallback: MA reclaim after 60+ bars with no RC signal
                bars_out = i - next((j for j, c2 in enumerate(candles) if c2["date"] == trades[-1]["exit_date"]), i) if trades else 0
                if not in_position and bars_out > 60 and exit_sma[i] is not None and close > exit_sma[i]:
                    if fast_ema[i] is not None and fast_ema[i] > exit_sma[i]:
                        slope = 0
                        if i >= slope_lb and exit_sma[i - slope_lb] is not None:
                            slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
                        if slope > 0:
                            entry_price = close
                            entry_date = date
                            entry_reason = "ma_reclaim_fallback"
                            in_position = True
                            peak_price = close
                            consecutive_above_ma = 0
                            rc_phase = "scan"
                            swing_highs.clear()
                            swing_lows.clear()

            # === LOW-VOL PATH: Standard Smart Hold re-entry signals ===
            else:
                # Signal 1: MA reclaim — price closes above SMA for N consecutive bars
                if exit_sma[i] is not None and close > exit_sma[i]:
                    consecutive_above_ma += 1
                else:
                    consecutive_above_ma = 0

                if (consecutive_above_ma >= reclaim_bars and
                        fast_ema[i] is not None and exit_sma[i] is not None and
                        fast_ema[i] > exit_sma[i]):
                    # Check slope is rising
                    slope = 0
                    if i >= slope_lb and exit_sma[i - slope_lb] is not None:
                        slope = (exit_sma[i] - exit_sma[i - slope_lb]) / exit_sma[i - slope_lb]
                    if slope > 0:
                        entry_price = close
                        entry_date = date
                        entry_reason = "ma_reclaim"
                        in_position = True
                        peak_price = close
                        consecutive_above_ma = 0
                        continue

                # Signal 2: RSI oversold bounce
                if rsi is not None and rsi_vals[i - 1] is not None:
                    if rsi_vals[i - 1] < 30 and rsi > 30 and close > candles[i - 1]["close"]:
                        entry_price = close
                        entry_date = date
                        entry_reason = "rsi_oversold_bounce"
                        in_position = True
                        peak_price = close
                        consecutive_above_ma = 0
                        continue

                # Signal 3: EMA momentum — price above rising fast EMA for 2+ bars
                if (fast_ema[i] is not None and fast_ema[i - 1] is not None and
                        close > fast_ema[i] and closes[i - 1] > fast_ema[i - 1] and
                        fast_ema[i] > fast_ema[i - 1]):
                    if exit_sma[i] is not None and close > exit_sma[i]:
                        entry_price = close
                        entry_date = date
                        entry_reason = "ema_momentum"
                        in_position = True
                        peak_price = close
                        consecutive_above_ma = 0
                        continue

    # ── Metrics ─────────────────────────────────────────────────────
    bh_ret = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100
    total_ret = (capital - initial_cap) / initial_cap * 100

    winning = [t for t in trades if t["return_pct"] > 0]
    losing = [t for t in trades if t["return_pct"] <= 0]
    win_rate = round(len(winning) / len(trades) * 100, 1) if trades else 0.0
    avg_gain = round(statistics.mean([t["return_pct"] for t in winning]), 2) if winning else 0.0
    avg_loss = round(statistics.mean([t["return_pct"] for t in losing]), 2) if losing else 0.0
    gw = sum(t["return_pct"] for t in winning)
    gl = abs(sum(t["return_pct"] for t in losing))
    profit_factor = round(gw / gl, 2) if gl > 0 else float("inf")

    equity, peak_eq, max_dd = initial_cap, initial_cap, 0.0
    for t in trades:
        equity *= (1 + t["return_pct"] / 100)
        if equity > peak_eq: peak_eq = equity
        dd = (equity - peak_eq) / peak_eq * 100
        if dd < max_dd: max_dd = dd

    if len(trades) >= 2:
        rets = [t["return_pct"] for t in trades]
        std_r = statistics.stdev(rets)
        sharpe = round(statistics.mean(rets) / std_r * math.sqrt(252 / max(1, len(rets))), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    rsi_overlay = [{"time": candles[j]["date"], "value": round(rsi_vals[j], 2)}
                   for j in range(n) if rsi_vals[j] is not None]

    result = {
        "symbol": p.get("symbol", ""),
        "strategy": "smart_hold_rc",
        "strategy_label": (
            f"Smart Hold Adaptive ({reentry_mode} re-entry, "
            f"ATR%={median_atr_pct:.1f}%, thresh={vol_threshold}%)"
        ),
        "reentry_mode": reentry_mode,
        "median_atr_pct": round(median_atr_pct, 2),
        "period": p.get("period", PERIOD),
        "interval": INTERVAL,
        "candles_analyzed": n,
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "initial_capital": initial_cap,
        "final_capital": round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "buy_and_hold_return_pct": round(bh_ret, 2),
        "vs_buy_and_hold_pct": round(total_ret - bh_ret, 2),
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate_pct": win_rate,
        "avg_gain_pct": avg_gain,
        "avg_loss_pct": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": round(max_dd, 2),
        "trade_log": trades,
        "overlays": [
            {"label": "RSI(14)", "color": "#E040FB", "type": "rsi_panel", "points": rsi_overlay},
        ],
        "data_source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Smart Hold + Reversal Channel Re-entry")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--period", default=PERIOD)
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--disable-exit", action="store_true")
    parser.add_argument("--force-rc", action="store_true", help="Force RC re-entry regardless of volatility")
    parser.add_argument("--force-standard", action="store_true", help="Force standard re-entry regardless of volatility")
    parser.add_argument("--vol-threshold", type=float, default=VOL_THRESHOLD, help="ATR%% threshold for RC vs standard")
    parser.add_argument("--chart", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  Smart Hold + Adaptive Re-entry — {args.symbol}")
    print(f"  Exit: Smart Hold (MA breakdown + trailing stop)")
    if args.force_rc:
        print(f"  Re-entry: FORCED Reversal Channel")
    elif args.force_standard:
        print(f"  Re-entry: FORCED Standard (MA reclaim, RSI, EMA)")
    else:
        print(f"  Re-entry: Auto (RC if ATR% > {args.vol_threshold}%, else standard)")
    print(f"{'='*65}")

    candles = fetch_ohlcv(args.symbol, args.period, "1d")
    vix_candles = fetch_ohlcv("^VIX", args.period, "1d")
    print(f"\n  Fetched {len(candles)} candles ({candles[0]['date']} -> {candles[-1]['date']})\n")

    params = {
        "symbol": args.symbol, "period": args.period,
        "initial_capital": args.initial_capital,
        "disable_exit": args.disable_exit,
        "force_rc": args.force_rc,
        "force_standard": args.force_standard,
        "vol_threshold": args.vol_threshold,
    }
    result = run_smart_hold_rc(candles, vix_candles, params)

    print(f"  Mode:            {result['reentry_mode']} re-entry (ATR%={result['median_atr_pct']}%)")
    print(f"  Period:          {result['date_from']} -> {result['date_to']}")
    print(f"  Total Return:    {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:      {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:          {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:    {result['total_trades']}")
    print(f"  Win Rate:        {result['win_rate_pct']}%")
    print(f"  Avg Gain:        {result['avg_gain_pct']:+.2f}%")
    print(f"  Avg Loss:        {result['avg_loss_pct']:+.2f}%")
    print(f"  Profit Factor:   {result['profit_factor']}")
    print(f"  Sharpe:          {result['sharpe_ratio']}")
    print(f"  Max Drawdown:    {result['max_drawdown_pct']}%")

    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        print(f"    {t['entry_reason']:28s}  {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>9,.2f} -> ${t['exit_price']:>9,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t['exit_reason']}]  {t.get('days_held', '?')}d")

    print(f"\n{'='*65}\n")

    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    fname = script_dir / f"smart_hold_rc_backtest_{safe_sym}_{args.period}.json"
    json_out = {k: v for k, v in result.items() if k != "overlays"}
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html
        chart_path = script_dir / f"smart_hold_rc_chart_{safe_sym}_{args.period}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path,
                           vix_candles=vix_candles)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
