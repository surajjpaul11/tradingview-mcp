"""
Reversal Channel Breakout Strategy
====================================
Detects downtrend → uptrend reversals using market structure.

Entry sequence (state machine):
  1. DOWNTREND:  2+ consecutive lower highs AND lower lows confirmed (swing pivots)
  2. FIRST_HH:   A swing high forms ABOVE the last lower high (breaks the sequence)
  3. WAIT_HL:    Price pulls back — waiting for a Higher Low (above last swing low)
  4. BUY:        Enter on the close of the Higher Low bar

Exit conditions (first fires):
  - ATR trailing stop: close < peak - (8x ATR) — wide, lets explosive moves breathe
  - Reversal failed:   New swing high forms LOWER than the entry HH → trend didn't hold
  - End of data:       Force-close on final bar

Designed for hyperbolic runner stocks (WULF, PLTR, SNDK) where catching
the reversal bottom is worth more than trend-following.

Usage:
    python3 strategies/reversal_channel/reversal_channel_strategy.py --symbol WULF --period 2y --chart
    python3 strategies/reversal_channel/reversal_channel_strategy.py --symbol PLTR --period 2y --chart
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

PIVOT_LEFT  = 5     # Bars to the left of a swing pivot
PIVOT_RIGHT = 3     # Bars to the right (smaller = faster confirmation)
MIN_SWINGS  = 1     # Consecutive LH+LL required to confirm downtrend
TOLERANCE   = 0.03  # 3% — how much a lower high/low can "drift" and still count
STALENESS   = 60    # Max bars between pivots before resetting downtrend state
ATR_TRAIL   = 5.0   # ATR multiplier for trailing stop
ATR_PERIOD  = 14
RSI_PERIOD  = 14
COOLDOWN    = 10    # Bars to wait after a failed/closed trade before re-scanning

COMMISSION  = 0.001
SLIPPAGE    = 0.001
INITIAL_CAPITAL = 10_000.0
PERIOD   = "2y"
INTERVAL = "1d"


# ── Helpers ──────────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "reversal-channel/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval in ("1h", "30m") else "%Y-%m-%d"
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({"date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
                         "open": round(o, 4), "high": round(h, 4),
                         "low": round(l, 4), "close": round(c, 4), "volume": v or 0})
    return candles


def sma(values: list[float], period: int) -> list[float | None]:
    out = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out = [None] * len(values)
    k = 2.0 / (period + 1)
    for i in range(len(values)):
        if i == 0:
            out[i] = values[i]
        elif i < period - 1:
            out[i] = values[i] * k + out[i - 1] * (1 - k)
        elif i == period - 1:
            out[i] = sum(values[:period]) / period
        else:
            out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def calc_atr(candles: list[dict], period: int = 14) -> list[float | None]:
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["high"] - c["low"])
        else:
            prev = candles[i - 1]["close"]
            trs.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))
    return ema(trs, period)


def calc_rsi(values: list[float], period: int = 14) -> list[float | None]:
    out = [None] * len(values)
    if len(values) < period + 1:
        return out
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


def find_pivots(highs: list[float], lows: list[float],
                left: int = 5, right: int = 3
                ) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Return confirmed pivot highs and lows as (bar_index, price) lists.
    A pivot at bar i is confirmed when we reach bar i+right."""
    n = len(highs)
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows:  list[tuple[int, float]] = []
    for i in range(left, n - right):
        # Pivot high: strictly highest in window
        if all(highs[j] < highs[i] for j in range(i - left, i + right + 1) if j != i):
            pivot_highs.append((i, highs[i]))
        # Pivot low: strictly lowest in window
        if all(lows[j] > lows[i]  for j in range(i - left, i + right + 1) if j != i):
            pivot_lows.append((i, lows[i]))
    return pivot_highs, pivot_lows


# ── Strategy Engine ──────────────────────────────────────────────────

# Phase constants
PHASE_SCAN     = "scan"       # Looking for a downtrend
PHASE_DOWNTREND = "downtrend" # Downtrend confirmed, waiting for breakout HH
PHASE_WAIT_HL  = "wait_hl"    # HH confirmed, waiting for first Higher Low
PHASE_POSITION = "position"   # In trade


def run_reversal_channel(candles: list[dict], params: dict | None = None) -> dict:
    p = params or {}
    pivot_left   = p.get("pivot_left",   PIVOT_LEFT)
    pivot_right  = p.get("pivot_right",  PIVOT_RIGHT)
    min_swings   = p.get("min_swings",   MIN_SWINGS)
    tolerance    = p.get("tolerance",    TOLERANCE)
    staleness    = p.get("staleness",    STALENESS)
    atr_trail    = p.get("atr_trail",    ATR_TRAIL)
    atr_period   = p.get("atr_period",   ATR_PERIOD)
    cooldown     = p.get("cooldown",     COOLDOWN)
    commission   = p.get("commission",   COMMISSION)
    slippage     = p.get("slippage",     SLIPPAGE)
    initial_cap  = p.get("initial_capital", INITIAL_CAPITAL)

    n       = len(candles)
    closes  = [c["close"] for c in candles]
    highs   = [c["high"]  for c in candles]
    lows    = [c["low"]   for c in candles]
    cost_pct = (commission + slippage) * 100

    atr_vals = calc_atr(candles, atr_period)
    rsi_vals = calc_rsi(closes, 14)

    # Pre-compute all pivot positions (confirmed at bar i+pivot_right)
    all_ph, all_pl = find_pivots(highs, lows, pivot_left, pivot_right)
    # Index by confirmation bar: ph_at[bar] = pivot price
    ph_at: dict[int, float] = {idx + pivot_right: price for idx, price in all_ph}
    pl_at: dict[int, float] = {idx + pivot_right: price for idx, price in all_pl}

    # State
    phase = PHASE_SCAN
    # Downtrend tracking
    swing_highs: list[tuple[int, float]] = []  # (bar_idx, price) in current downtrend
    swing_lows:  list[tuple[int, float]] = []
    # HH/HL tracking
    hh_price   = 0.0
    hh_bar     = 0
    last_ll_price = 0.0  # The last LL in the downtrend — HL must be above this
    # Position state
    entry_price = 0.0
    entry_date  = ""
    peak_price  = 0.0
    bars_since_close = cooldown  # Start ready
    # Chart annotations
    phase_log: list[dict] = []  # {bar, phase, note}

    trades: list[dict] = []
    capital = initial_cap
    exit_counts = {"atr_trailing_stop": 0, "reversal_failed": 0, "end_of_data": 0}

    def log_phase(i: int, new_phase: str, note: str = ""):
        phase_log.append({"bar": i, "date": candles[i]["date"], "phase": new_phase, "note": note})

    warmup = pivot_left + pivot_right + 1

    for i in range(warmup, n):
        close = closes[i]
        date  = candles[i]["date"]

        # ── New pivot confirmations at this bar ──────────────────────
        new_ph = ph_at.get(i)  # swing HIGH confirmed at bar i
        new_pl = pl_at.get(i)  # swing LOW confirmed at bar i

        # ── Phase: SCAN / DOWNTREND ─ build downtrend structure ─────
        if phase in (PHASE_SCAN, PHASE_DOWNTREND):
            # Absorb confirmed pivots into downtrend tracking
            if new_ph is not None:
                # Check staleness (gap between pivots)
                if swing_highs and (i - swing_highs[-1][0]) > staleness:
                    swing_highs.clear()
                    swing_lows.clear()
                    phase = PHASE_SCAN
                    log_phase(i, PHASE_SCAN, "stale — reset")

                # Extend swing high list
                if swing_highs:
                    prev_h = swing_highs[-1][1]
                    if new_ph <= prev_h * (1 + tolerance):
                        # Still within LH tolerance — extend the downtrend
                        swing_highs.append((i, new_ph))
                    else:
                        # New high breaks the LH sequence
                        if phase == PHASE_DOWNTREND:
                            # This IS the First Higher High — transition to waiting for HL
                            last_lh = swing_highs[-1][1]
                            hh_price = new_ph
                            hh_bar   = i
                            last_ll_price = swing_lows[-1][1] if swing_lows else 0.0
                            phase = PHASE_WAIT_HL
                            log_phase(i, PHASE_WAIT_HL,
                                      f"HH={hh_price:.2f} > last_LH={last_lh:.2f} last_LL={last_ll_price:.2f}")
                        else:
                            # In SCAN phase — reset and start fresh from this high
                            swing_highs = [(i, new_ph)]
                            swing_lows.clear()
                            phase = PHASE_SCAN
                else:
                    swing_highs.append((i, new_ph))

            if new_pl is not None and phase in (PHASE_SCAN, PHASE_DOWNTREND):
                if swing_lows and (i - swing_lows[-1][0]) > staleness:
                    swing_lows.clear()

                if swing_lows:
                    prev_l = swing_lows[-1][1]
                    if new_pl <= prev_l * (1 + tolerance):  # LL or near-LL
                        swing_lows.append((i, new_pl))
                    else:
                        swing_lows = [(i, new_pl)]  # reset
                else:
                    swing_lows.append((i, new_pl))

            # Check if downtrend now confirmed (enough LH + LL pairs)
            if (len(swing_highs) >= min_swings + 1 and
                    len(swing_lows) >= min_swings + 1 and
                    phase == PHASE_SCAN):
                phase = PHASE_DOWNTREND
                log_phase(i, PHASE_DOWNTREND,
                          f"LH={len(swing_highs)} LL={len(swing_lows)}")

        # ── Phase: WAIT_HL — look for Higher Low ────────────────────
        elif phase == PHASE_WAIT_HL:
            if bars_since_close < cooldown:
                bars_since_close += 1

            # If price drops significantly below the last LL, the reversal failed → reset
            if last_ll_price > 0 and close < last_ll_price * (1 - 0.05):
                phase = PHASE_SCAN
                swing_highs.clear()
                swing_lows.clear()
                log_phase(i, PHASE_SCAN, "pullback below last LL — reversal invalidated")
                continue

            # New swing low confirmed at this bar
            if new_pl is not None and bars_since_close >= cooldown:
                # Is it a Higher Low? Must be above the last LL in the downtrend
                if new_pl > last_ll_price * (1 + 0.0):  # strict: above last LL
                    # Enter on this bar's close
                    entry_price = close
                    entry_date  = date
                    peak_price  = close
                    phase = PHASE_POSITION
                    log_phase(i, PHASE_POSITION,
                              f"HL={new_pl:.2f} > last_LL={last_ll_price:.2f} → BUY @ {close:.2f}")
                else:
                    # Lower low again — still in downtrend, update LL and keep waiting
                    swing_lows.append((i, new_pl))
                    last_ll_price = new_pl
                    log_phase(i, PHASE_WAIT_HL, f"new LL={new_pl:.2f} — still waiting")

            # Timeout: if we've been waiting too long (50 bars) without an HL, reset
            if phase == PHASE_WAIT_HL and (i - hh_bar) > 50:
                phase = PHASE_SCAN
                swing_highs.clear()
                swing_lows.clear()
                log_phase(i, PHASE_SCAN, "HH timeout — reset")

        # ── Phase: IN POSITION ───────────────────────────────────────
        elif phase == PHASE_POSITION:
            if close > peak_price:
                peak_price = close

            atr = atr_vals[i]
            exit_reason = ""

            # Exit 1: ATR trailing stop
            if atr is not None and close < peak_price - atr_trail * atr:
                exit_reason = "atr_trailing_stop"

            # Exit 2: Reversal failed — new swing HIGH forms LOWER than entry HH
            if not exit_reason and new_ph is not None and new_ph < hh_price * (1 - tolerance):
                exit_reason = "reversal_failed"

            # Exit 3: End of data
            if not exit_reason and i == n - 1:
                exit_reason = "end_of_data"

            if exit_reason:
                gross_ret = (close - entry_price) / entry_price * 100
                net_ret   = gross_ret - cost_pct * 2
                capital  *= (1 + net_ret / 100)

                trades.append({
                    "entry_date":  entry_date,
                    "entry_price": round(entry_price, 4),
                    "exit_date":   date,
                    "exit_price":  round(close, 4),
                    "hh_price":    round(hh_price, 4),
                    "side":        "long",
                    "return_pct":  round(net_ret, 2),
                    "gross_return_pct": round(gross_ret, 2),
                    "cost_pct":    round(-cost_pct * 2, 2),
                    "exit_reason": exit_reason,
                    "strategy":    "reversal_channel",
                })
                exit_counts[exit_reason] = exit_counts.get(exit_reason, 0) + 1
                log_phase(i, PHASE_SCAN,
                          f"EXIT [{exit_reason}] ret={net_ret:.1f}%")

                phase = PHASE_SCAN
                bars_since_close = 0
                swing_highs.clear()
                swing_lows.clear()
                peak_price = 0.0

    # ── Metrics ──────────────────────────────────────────────────────
    bh_ret   = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100
    total_ret = (capital - initial_cap) / initial_cap * 100

    winning = [t for t in trades if t["return_pct"] > 0]
    losing  = [t for t in trades if t["return_pct"] <= 0]
    win_rate = round(len(winning) / len(trades) * 100, 1) if trades else 0.0
    avg_gain = round(statistics.mean([t["return_pct"] for t in winning]), 2) if winning else 0.0
    avg_loss = round(statistics.mean([t["return_pct"] for t in losing]),  2) if losing  else 0.0
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
        tpy = 252 / max(1, n / len(trades))
        sharpe = round(statistics.mean(rets) / std_r * math.sqrt(tpy), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    bars_in = 0
    for t in trades:
        ei = next((j for j, c in enumerate(candles) if c["date"] == t["entry_date"]), 0)
        xi = next((j for j, c in enumerate(candles) if c["date"] == t["exit_date"]),  0)
        bars_in += xi - ei
    time_in = round(bars_in / n * 100, 1) if n > 0 else 0.0

    # Build overlays
    atr_trail_line = []
    peak_tracker = 0.0
    in_pos = False
    for j in range(n):
        if j < len(trades):
            pass  # handled below
    # Rebuild peak for ATR trail overlay
    pos_start = None
    pk = 0.0
    for t in trades:
        ei = next((j for j, c in enumerate(candles) if c["date"] == t["entry_date"]), None)
        xi = next((j for j, c in enumerate(candles) if c["date"] == t["exit_date"]),  None)
        if ei is None or xi is None:
            continue
        pk = candles[ei]["close"]
        for j in range(ei, xi + 1):
            if candles[j]["close"] > pk:
                pk = candles[j]["close"]
            atr = atr_vals[j]
            if atr is not None:
                trail = pk - atr_trail * atr
                atr_trail_line.append({"time": candles[j]["date"], "value": round(trail, 4)})

    # Pivot markers for chart
    ph_overlay = [{"time": candles[idx]["date"], "value": round(price, 4)} for idx, price in all_ph
                  if idx + pivot_right < n]
    pl_overlay = [{"time": candles[idx]["date"], "value": round(price, 4)} for idx, price in all_pl
                  if idx + pivot_right < n]

    result = {
        "symbol": p.get("symbol", ""),
        "strategy": "reversal_channel",
        "strategy_label": (
            f"Reversal Channel (pivot L={pivot_left}/R={pivot_right}, "
            f"min_swings={min_swings}, ATR trail={atr_trail}x)"
        ),
        "parameters": {k: v for k, v in p.items()},
        "period": p.get("period", PERIOD),
        "interval": p.get("interval", INTERVAL),
        "candles_analyzed": n,
        "date_from": candles[0]["date"],
        "date_to":   candles[-1]["date"],
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
        "time_in_market_pct": time_in,
        "atr_trailing_stop_exits": exit_counts.get("atr_trailing_stop", 0),
        "reversal_failed_exits": exit_counts.get("reversal_failed", 0),
        "end_of_data_exits": exit_counts.get("end_of_data", 0),
        "trade_log": trades,
        "phase_log": phase_log,
        "overlays": [
            {"label": "ATR Trail Stop", "color": "#FF5252", "type": "line",
             "points": atr_trail_line},
            {"label": "Pivot Highs", "color": "#FF9800", "type": "scatter",
             "points": ph_overlay},
            {"label": "Pivot Lows", "color": "#4CAF50", "type": "scatter",
             "points": pl_overlay},
        ],
        "data_source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reversal Channel Breakout Strategy")
    parser.add_argument("--symbol", default="WULF")
    parser.add_argument("--period", default=PERIOD)
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"])
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--pivot-left",  type=int,   default=PIVOT_LEFT)
    parser.add_argument("--pivot-right", type=int,   default=PIVOT_RIGHT)
    parser.add_argument("--min-swings",  type=int,   default=MIN_SWINGS)
    parser.add_argument("--tolerance",   type=float, default=TOLERANCE)
    parser.add_argument("--atr-trail",   type=float, default=ATR_TRAIL)
    parser.add_argument("--cooldown",    type=int,   default=COOLDOWN)
    parser.add_argument("--chart", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Reversal Channel Breakout — {args.symbol}")
    print(f"  Pivot L={args.pivot_left}/R={args.pivot_right}  "
          f"Min swings={args.min_swings}  Tol={args.tolerance*100:.0f}%")
    print(f"  ATR trail={args.atr_trail}x  Cooldown={args.cooldown} bars")
    print(f"{'='*60}")

    candles = fetch_ohlcv(args.symbol, args.period, args.interval)
    print(f"\n  Fetched {len(candles)} candles ({candles[0]['date']} → {candles[-1]['date']})\n")

    params = {
        "symbol": args.symbol, "period": args.period, "interval": args.interval,
        "initial_capital": args.initial_capital,
        "pivot_left": args.pivot_left, "pivot_right": args.pivot_right,
        "min_swings": args.min_swings, "tolerance": args.tolerance,
        "atr_trail": args.atr_trail, "cooldown": args.cooldown,
    }
    result = run_reversal_channel(candles, params)

    print(f"  Period:          {result['date_from']} → {result['date_to']}")
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
    print(f"  Time in Market:  {result['time_in_market_pct']}%")
    print(f"  Exits:           ATR trail={result['atr_trailing_stop_exits']}  "
          f"Reversal failed={result['reversal_failed_exits']}  "
          f"EOD={result['end_of_data_exits']}")

    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        print(f"    LONG  {t['entry_date']} → {t['exit_date']}  "
              f"${t['entry_price']:>9,.2f} → ${t['exit_price']:>9,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t['exit_reason']}]")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    json_out = {k: v for k, v in result.items() if k not in ("overlays", "phase_log")}
    fname = script_dir / f"reversal_channel_backtest_{safe_sym}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html
        chart_path = script_dir / f"reversal_channel_chart_{safe_sym}_{args.period}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
