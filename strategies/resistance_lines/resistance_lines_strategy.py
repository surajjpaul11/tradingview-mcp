"""
Resistance Lines Strategy — Standalone Python Implementation
=============================================================

Horizontal support/resistance bounce strategy (long only).

Level detection (no lookahead):
  1. Detect swing highs and swing lows with pivot logic (confirmed `pivot_lookback`
     bars after the pivot, so a level is only known once it could have been seen).
  2. Take every confirmed swing high AND low inside the last `level_lookback` bars
     and cluster them by price: pivots within `zone_atr_mult` x ATR of a cluster's
     mean join that cluster.
  3. A cluster with >= `min_touches` pivots is a horizontal level. Its zone is
     level +/- zone_atr_mult x ATR. Levels below price act as support, levels above
     price act as resistance (a broken support naturally becomes resistance).

Entry — support bounce (BUY):
  - Bar's low enters a support zone (low <= level + zone) AND the bar closes back
    above the level, with the previous close also above the level (price came
    down into the level, not up from below it).
  - The bar forms a bullish reversal candle: hammer or bullish engulfing.
  - Risk/reward check: (target - entry) / (entry - stop) >= `min_rr`.
  - Signal on the bar's close, fill on the next bar's open.

Exits:
  - Stop loss:  level - stop_atr_mult x ATR (frozen at entry). A close through the
                level means it failed; the stop is where the idea is wrong.
  - Target:     bottom of the next resistance zone above the entry.
  - Resistance bounce (SELL): bar's high enters a resistance zone, closes back
                below the level, with a bearish reversal candle (shooting star or
                bearish engulfing). Signal on close, exit on next bar's open.
  - End of data.
  Intrabar order is conservative: if a bar touches both stop and target, the stop
  is assumed to fill first. Gaps through stop/target fill at the open.

Usage:
  python resistance_lines_strategy.py                           # defaults: SPY, 5y, 1d
  python resistance_lines_strategy.py --symbol BTC-USD --period 1y
  python resistance_lines_strategy.py --symbol AAPL --interval 1h --period 2y
  python resistance_lines_strategy.py --symbol QQQ --min-touches 3 --min-rr 2

Requires: no external dependencies (pure stdlib + Yahoo Finance API)
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ==============================================================================
# STRATEGY PARAMETERS
# ==============================================================================

PIVOT_LOOKBACK     = 5       # bars left/right for swing point detection
LEVEL_LOOKBACK     = 500     # only pivots from the last N bars form levels
MIN_TOUCHES        = 2       # pivots needed in a cluster to form a level
ZONE_ATR_MULT      = 0.75    # level zone half-width, in ATR (also the cluster radius)
STOP_ATR_MULT      = 1.0     # stop distance beyond the level, in ATR
MIN_RR             = 1.5     # minimum reward/risk to take a trade (0 disables)
ATR_PERIOD         = 14
HAMMER_WICK_RATIO  = 2.0     # hammer / shooting star: long wick >= ratio x body
INTERVAL           = "1d"    # 1h tested: costs erase the edge (see STRATEGIES.md)
PERIOD             = "5y"
INITIAL_CAPITAL    = 10_000.0
COMMISSION_PCT     = 0.1
SLIPPAGE_PCT       = 0.05


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1h") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "resistance-lines-strategy/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d %H:%M" if interval in ("1h", "30m", "15m", "5m") else "%Y-%m-%d"

    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
            "open": round(o, 4), "high": round(h, 4),
            "low": round(l, 4), "close": round(c, 4),
            "volume": v or 0,
        })
    return candles


# ==============================================================================
# INDICATORS
# ==============================================================================

def calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Optional[float]]:
    """Wilder ATR. Returns None until enough bars exist."""
    n = len(closes)
    atr: list[Optional[float]] = [None] * n
    if n <= period:
        return atr
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr[period] = sum(trs[1:period + 1]) / period
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + trs[i]) / period
    return atr


def find_swings(highs: list[float], lows: list[float], lookback: int = 5
                ) -> tuple[list[tuple[int, float, int]], list[tuple[int, float, int]]]:
    """
    Pivot swing detection.

    Returns (swing_highs, swing_lows), each a list of (bar_index, price, confirmed_at_bar).
    A pivot at bar i is only usable from bar i + lookback onward.
    """
    n = len(highs)
    swing_highs: list[tuple[int, float, int]] = []
    swing_lows: list[tuple[int, float, int]] = []
    for i in range(lookback, n - lookback):
        window = range(i - lookback, i + lookback + 1)
        if all(highs[i] >= highs[j] for j in window):
            swing_highs.append((i, highs[i], i + lookback))
        if all(lows[i] <= lows[j] for j in window):
            swing_lows.append((i, lows[i], i + lookback))
    return swing_highs, swing_lows


# ==============================================================================
# LEVELS
# ==============================================================================

def cluster_levels(prices: list[float], radius: float, min_touches: int) -> list[dict]:
    """
    Greedy 1-D clustering of pivot prices.

    Sorted prices join the current cluster while within `radius` of its running mean.
    Returns levels sorted by price: {"price": mean, "touches": count}.
    """
    if not prices or radius <= 0:
        return []
    levels = []
    cluster = []
    for p in sorted(prices):
        if cluster and p - (sum(cluster) / len(cluster)) > radius:
            if len(cluster) >= min_touches:
                levels.append({"price": sum(cluster) / len(cluster), "touches": len(cluster)})
            cluster = []
        cluster.append(p)
    if len(cluster) >= min_touches:
        levels.append({"price": sum(cluster) / len(cluster), "touches": len(cluster)})
    return levels


# ==============================================================================
# CANDLE PATTERNS
# ==============================================================================

def is_bullish_reversal(o: float, h: float, l: float, c: float,
                        po: float, pc: float, wick_ratio: float) -> Optional[str]:
    """Hammer or bullish engulfing. Returns the pattern name or None."""
    rng = h - l
    if rng <= 0:
        return None
    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    # Hammer: long lower wick, small upper wick, close in the upper 40% of the range
    if (lower_wick >= wick_ratio * max(body, rng * 0.05)
            and upper_wick <= max(body, rng * 0.1)
            and (c - l) / rng >= 0.6):
        return "hammer"
    # Bullish engulfing: previous bar red, this bar green and its body covers the previous body
    if pc < po and c > o and c >= po and o <= pc:
        return "bullish_engulfing"
    return None


def is_bearish_reversal(o: float, h: float, l: float, c: float,
                        po: float, pc: float, wick_ratio: float) -> Optional[str]:
    """Shooting star or bearish engulfing. Returns the pattern name or None."""
    rng = h - l
    if rng <= 0:
        return None
    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    if (upper_wick >= wick_ratio * max(body, rng * 0.05)
            and lower_wick <= max(body, rng * 0.1)
            and (h - c) / rng >= 0.6):
        return "shooting_star"
    if pc > po and c < o and c <= po and o >= pc:
        return "bearish_engulfing"
    return None


# ==============================================================================
# STRATEGY
# ==============================================================================

def run_resistance_lines(
    candles: list[dict],
    pivot_lookback: int = PIVOT_LOOKBACK,
    level_lookback: int = LEVEL_LOOKBACK,
    min_touches: int = MIN_TOUCHES,
    zone_atr_mult: float = ZONE_ATR_MULT,
    stop_atr_mult: float = STOP_ATR_MULT,
    min_rr: float = MIN_RR,
    atr_period: int = ATR_PERIOD,
    hammer_wick_ratio: float = HAMMER_WICK_RATIO,
    **_,
) -> list[dict]:
    """
    Run the Resistance Lines strategy. Returns a list of closed trades
    (long only; every trade carries side="long").
    """
    n = len(candles)
    if n < max(atr_period, pivot_lookback * 2) + 5:
        return []

    opens  = [c["open"] for c in candles]
    highs  = [c["high"] for c in candles]
    lows   = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    atr    = calc_atr(highs, lows, closes, atr_period)

    swing_highs, swing_lows = find_swings(highs, lows, pivot_lookback)
    pivots = sorted(
        [(b, p, conf) for b, p, conf in swing_highs] + [(b, p, conf) for b, p, conf in swing_lows],
        key=lambda x: x[2],
    )

    trades: list[dict] = []
    position: Optional[dict] = None
    pending_entry: Optional[dict] = None   # signal from the previous bar, fills at this bar's open
    pending_exit: Optional[str] = None     # exit reason from the previous bar, fills at this bar's open
    known: list[tuple[int, float]] = []    # confirmed pivots (bar, price)
    p_idx = 0

    for i in range(1, n):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        # --- 1. Fill orders queued on the previous bar's close (at this bar's open) ---
        if pending_exit and position is not None:
            trades.append(_close(position, candles[i]["date"], o, pending_exit))
            position = None
        pending_exit = None

        if pending_entry and position is None:
            sig = pending_entry
            entry = o
            risk = entry - sig["stop"]
            reward = (sig["target"] - entry) if sig["target"] is not None else None
            ok = risk > 0 and (reward is None or reward > 0)
            if ok and min_rr > 0 and reward is not None:
                ok = reward / risk >= min_rr
            if ok:
                position = {
                    "entry_date": candles[i]["date"], "entry_price": entry,
                    "stop": sig["stop"], "target": sig["target"],
                    "level": sig["level"], "touches": sig["touches"],
                    "pattern": sig["pattern"],
                }
        pending_entry = None

        # --- 2. Intrabar stop / target for an open position (stop first = conservative) ---
        if position is not None:
            stop, target = position["stop"], position["target"]
            if o <= stop:
                trades.append(_close(position, candles[i]["date"], o, "stop_loss"))
                position = None
            elif l <= stop:
                trades.append(_close(position, candles[i]["date"], stop, "stop_loss"))
                position = None
            elif target is not None and o >= target:
                trades.append(_close(position, candles[i]["date"], o, "target"))
                position = None
            elif target is not None and h >= target:
                trades.append(_close(position, candles[i]["date"], target, "target"))
                position = None

        # --- 3. Update the level map using only pivots confirmed by this bar ---
        while p_idx < len(pivots) and pivots[p_idx][2] <= i:
            known.append((pivots[p_idx][0], pivots[p_idx][1]))
            p_idx += 1
        a = atr[i]
        if a is None or a <= 0 or i == n - 1:
            continue
        zone = zone_atr_mult * a
        window_prices = [p for b, p in known if b >= i - level_lookback]
        levels = cluster_levels(window_prices, zone, min_touches)
        if not levels:
            continue

        po, pc = opens[i - 1], closes[i - 1]

        # --- 4. Signals on this bar's close ---
        if position is None:
            # Support bounce: nearest qualifying support first
            supports = [lv for lv in levels if lv["price"] < c]
            for lv in sorted(supports, key=lambda x: -x["price"]):
                L = lv["price"]
                touched = min(l, lows[i - 1]) <= L + zone
                came_from_above = pc > L
                if not (touched and came_from_above and c > L):
                    continue
                pattern = is_bullish_reversal(o, h, l, c, po, pc, hammer_wick_ratio)
                if not pattern:
                    break  # nearest touched level had no reversal candle: no signal this bar
                stop = L - stop_atr_mult * a
                above = [r["price"] - zone for r in levels if r["price"] - zone > c]
                target = min(above) if above else None
                pending_entry = {"level": round(L, 4), "touches": lv["touches"],
                                 "stop": stop, "target": target, "pattern": pattern}
                break
        else:
            # Resistance bounce: sell signal
            resistances = [lv for lv in levels if lv["price"] > c]
            for lv in sorted(resistances, key=lambda x: x["price"]):
                L = lv["price"]
                touched = max(h, highs[i - 1]) >= L - zone
                came_from_below = pc < L
                if not (touched and came_from_below):
                    continue
                if is_bearish_reversal(o, h, l, c, po, pc, hammer_wick_ratio):
                    pending_exit = "resistance_bounce"
                break

    if position is not None:
        trades.append(_close(position, candles[-1]["date"], closes[-1], "end_of_data"))
    return trades


def _close(position: dict, date: str, price: float, reason: str) -> dict:
    return {
        "entry_date":  position["entry_date"],
        "entry_price": round(position["entry_price"], 4),
        "exit_date":   date,
        "exit_price":  round(price, 4),
        "side":        "long",
        "exit_reason": reason,
        "level":       position["level"],
        "touches":     position["touches"],
        "pattern":     position["pattern"],
        "stop":        round(position["stop"], 4),
        "target":      round(position["target"], 4) if position["target"] is not None else None,
        "strategy":    "resistance_lines",
    }


# ==============================================================================
# METRICS & REPORTING
# ==============================================================================

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply round-trip commission + slippage to each trade."""
    total_cost = (commission_pct + slippage_pct) * 2
    result = []
    for t in trades:
        if t.get("side") == "short":
            gross = (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100
        else:
            gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net = round(gross - total_cost, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3), "cost_pct": round(-total_cost, 3)})
    return result


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1h") -> dict:
    """Backtest metrics (compounded, full capital per trade)."""
    reasons = ("stop_loss", "target", "resistance_bounce", "end_of_data")
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                **{f"{r}_exits": 0 for r in reasons},
                "win_rate_pct": 0, "total_return_pct": 0, "final_capital": initial_capital,
                "max_drawdown_pct": 0, "avg_gain_pct": 0, "avg_loss_pct": 0,
                "sharpe_ratio": 0, "profit_factor": 0, "expectancy_pct": 0}

    ann = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}.get(interval, 252 * 6)
    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]

    capital = peak = initial_capital
    max_dd = 0.0
    returns = []
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak * 100)

    total_ret = (capital - initial_capital) / initial_capital * 100
    avg_gain = sum(t["return_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["return_pct"] for t in losers) / len(losers) if losers else 0
    gp = sum(t["return_pct"] for t in winners)
    gl = abs(sum(t["return_pct"] for t in losers))
    pf = round(gp / gl, 2) if gl > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        sd = statistics.stdev(returns)
        if sd > 0:
            sharpe = round((statistics.mean(returns) - 0.04 / ann) / sd * math.sqrt(ann), 2)

    wr = len(winners) / len(trades)
    return {
        "total_trades":     len(trades),
        "winning_trades":   len(winners),
        "losing_trades":    len(losers),
        **{f"{r}_exits": sum(1 for t in trades if t.get("exit_reason") == r) for r in reasons},
        "win_rate_pct":     round(wr * 100, 1),
        "final_capital":    round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "avg_gain_pct":     round(avg_gain, 2),
        "avg_loss_pct":     round(avg_loss, 2),
        "max_drawdown_pct": round(-max_dd, 2),
        "profit_factor":    pf,
        "sharpe_ratio":     sharpe,
        "expectancy_pct":   round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }


def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    **params,
) -> dict:
    """Full pipeline: fetch data -> run strategy -> costs -> metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    trades = apply_costs(run_resistance_lines(candles, **params), commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)
    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
    p = {
        "pivot_lookback": params.get("pivot_lookback", PIVOT_LOOKBACK),
        "level_lookback": params.get("level_lookback", LEVEL_LOOKBACK),
        "min_touches": params.get("min_touches", MIN_TOUCHES),
        "zone_atr_mult": params.get("zone_atr_mult", ZONE_ATR_MULT),
        "stop_atr_mult": params.get("stop_atr_mult", STOP_ATR_MULT),
        "min_rr": params.get("min_rr", MIN_RR),
        "atr_period": params.get("atr_period", ATR_PERIOD),
        "hammer_wick_ratio": params.get("hammer_wick_ratio", HAMMER_WICK_RATIO),
    }
    return {
        "symbol": symbol.upper(),
        "strategy": "resistance_lines",
        "strategy_label": (f"Resistance Lines (touches>={p['min_touches']}, zone={p['zone_atr_mult']}ATR, "
                           f"stop={p['stop_atr_mult']}ATR, RR>={p['min_rr']})"),
        "parameters": p,
        "period": period,
        "interval": interval,
        "candles_analyzed": len(candles),
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "initial_capital": initial_capital,
        "commission_pct": commission_pct,
        "slippage_pct": slippage_pct,
        **metrics,
        "buy_and_hold_return_pct": bnh,
        "vs_buy_and_hold_pct": round(metrics["total_return_pct"] - bnh, 2),
        "trade_log": trades,
        "data_source": "Yahoo Finance",
        "disclaimer": "Past performance does not guarantee future results. For educational use only.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    ap = argparse.ArgumentParser(description="Resistance Lines (Horizontal S/R Bounce) Strategy Backtester")
    ap.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    ap.add_argument("--period", default=PERIOD, help="Data period (default: 5y)")
    ap.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size (default: 1d)")
    ap.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    ap.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per side")
    ap.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per side")
    ap.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK)
    ap.add_argument("--level-lookback", type=int, default=LEVEL_LOOKBACK, help="Bars of pivots used for levels")
    ap.add_argument("--min-touches", type=int, default=MIN_TOUCHES, help="Pivots needed to form a level")
    ap.add_argument("--zone-atr", type=float, default=ZONE_ATR_MULT, help="Zone half-width in ATR")
    ap.add_argument("--stop-atr", type=float, default=STOP_ATR_MULT, help="Stop distance beyond level in ATR")
    ap.add_argument("--min-rr", type=float, default=MIN_RR, help="Minimum reward/risk (0 disables)")
    ap.add_argument("--no-save", action="store_true", help="Do not write the JSON result file")
    args = ap.parse_args()

    print(f"\n{'='*64}")
    print(f"  Resistance Lines Strategy — {args.symbol}  ({args.interval}, {args.period})")
    print(f"  Touches>={args.min_touches} | Zone {args.zone_atr} ATR | Stop {args.stop_atr} ATR | RR>={args.min_rr}")
    print(f"{'='*64}\n")

    r = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital, commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_lookback=args.pivot_lookback, level_lookback=args.level_lookback,
        min_touches=args.min_touches, zone_atr_mult=args.zone_atr,
        stop_atr_mult=args.stop_atr, min_rr=args.min_rr,
    )

    print(f"  Period:          {r['date_from']} -> {r['date_to']} ({r['candles_analyzed']} bars)")
    print(f"  Final Capital:   ${r['final_capital']:,.2f}  (from ${r['initial_capital']:,.2f})")
    print(f"  Total Return:    {r['total_return_pct']:+.2f}%   B&H: {r['buy_and_hold_return_pct']:+.2f}%   "
          f"vs B&H: {r['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Trades:          {r['total_trades']}   Win rate: {r['win_rate_pct']}%   PF: {r['profit_factor']}   "
          f"Sharpe: {r['sharpe_ratio']}")
    print(f"  Max Drawdown:    {r['max_drawdown_pct']}%")
    print(f"  Exits:           stop {r['stop_loss_exits']} | target {r['target_exits']} | "
          f"resistance bounce {r['resistance_bounce_exits']} | EOD {r['end_of_data_exits']}")
    print("\n  Trade Log:")
    for t in r["trade_log"]:
        print(f"    {t['entry_date']} -> {t['exit_date']}  ${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  lvl {t['level']:,.2f} ({t['touches']}x, {t['pattern']})  [{t['exit_reason']}]")
    print(f"\n{'='*64}\n")

    if not args.no_save:
        fname = Path(__file__).resolve().parent / (
            f"resistance_lines_backtest_{args.symbol.replace('-', '_')}_{args.period}.json")
        with open(fname, "w") as f:
            json.dump(r, f, indent=2)
        print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
