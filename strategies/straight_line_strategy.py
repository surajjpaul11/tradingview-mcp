"""
Straight Line Strategy — Standalone Python Implementation
==========================================================

Trendline break strategy with 4-point confirmation.

Uptrend (support trendline):
  1. Find 2 ascending swing lows as anchor points, draw a straight line
  2. Require 2+ more swing lows within tolerance of the projected line
  3. When price closes below the trendline → SELL

Downtrend (resistance trendline):
  1. Find 2 descending swing highs as anchor points, draw a straight line
  2. Require 2+ more swing highs within tolerance of the projected line
  3. When price closes above the trendline → BUY

Initial position: long if recent swing lows are ascending, else wait.
After a sell, waits for a resistance trendline break to buy back in.
After a buy, builds a new support trendline to protect the position.

Usage:
  python straight_line_strategy.py                                # defaults: SPY, 2y, 1h
  python straight_line_strategy.py --symbol BTC-USD --period 1y
  python straight_line_strategy.py --symbol QQQ --enable-short
  python straight_line_strategy.py --symbol AAPL --trendline-tolerance 0.01

Requires: no external dependencies (pure stdlib + Yahoo Finance API)
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import urllib.request
from datetime import datetime, timezone
from typing import Optional


# ==============================================================================
# STRATEGY PARAMETERS
# ==============================================================================

PIVOT_LOOKBACK       = 5       # bars left/right for swing point detection
MIN_CONFIRMATIONS    = 2       # additional points near trendline to confirm (total = 2 anchor + this)
TRENDLINE_TOLERANCE  = 0.015   # 1.5% tolerance for "touching" the trendline
ENABLE_SHORT         = False   # enable short positions on support break
INTERVAL             = "1h"    # candle size
PERIOD               = "2y"    # data lookback
INITIAL_CAPITAL      = 10_000.0
COMMISSION_PCT       = 0.1
SLIPPAGE_PCT         = 0.05


# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1h") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "straight-line-strategy/1.0"})
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
# SWING POINT DETECTION
# ==============================================================================

def find_swings(highs: list[float], lows: list[float], lookback: int = 5
                ) -> tuple[list[tuple[int, float, int]], list[tuple[int, float, int]]]:
    """
    Detect swing highs and swing lows via pivot logic.

    Returns:
      swing_highs: list of (bar_index, price, confirmed_at_bar)
      swing_lows:  list of (bar_index, price, confirmed_at_bar)
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
# TRENDLINE LOGIC
# ==============================================================================

def trendline_value(anchor1: tuple[int, float], anchor2: tuple[int, float], bar: int) -> float:
    """Calculate the projected trendline value at a given bar index."""
    b1, p1 = anchor1
    b2, p2 = anchor2
    if b2 == b1:
        return p1
    slope = (p2 - p1) / (b2 - b1)
    return p1 + slope * (bar - b1)


def try_build_support_trendline(
    confirmed_lows: list[tuple[int, float]],
    tolerance: float,
    min_confirmations: int,
) -> dict | None:
    """
    Try to build a support trendline from confirmed swing lows.

    Looks for 2 ascending anchor lows, then checks if min_confirmations additional
    lows land within tolerance of the projected line.

    Returns trendline dict or None.
    """
    if len(confirmed_lows) < 2 + min_confirmations:
        return None

    # Try pairs of ascending lows as anchors, starting from the earliest
    for i in range(len(confirmed_lows) - 1):
        for j in range(i + 1, len(confirmed_lows)):
            a1 = confirmed_lows[i]
            a2 = confirmed_lows[j]

            # Anchors must be ascending
            if a2[1] <= a1[1]:
                continue

            # Count how many subsequent lows are within tolerance of the line
            confirmations = 0
            last_confirm_bar = a2[0]
            for k in range(j + 1, len(confirmed_lows)):
                bar_k, price_k = confirmed_lows[k]
                projected = trendline_value(a1, a2, bar_k)
                if projected <= 0:
                    continue
                deviation = abs(price_k - projected) / projected
                if deviation <= tolerance:
                    confirmations += 1
                    last_confirm_bar = bar_k

            if confirmations >= min_confirmations:
                return {
                    "type": "support",
                    "anchor1": a1,
                    "anchor2": a2,
                    "confirmations": confirmations,
                    "confirmed_at_bar": last_confirm_bar,
                }

    return None


def try_build_resistance_trendline(
    confirmed_highs: list[tuple[int, float]],
    tolerance: float,
    min_confirmations: int,
) -> dict | None:
    """
    Try to build a resistance trendline from confirmed swing highs.

    Looks for 2 descending anchor highs, then checks if min_confirmations additional
    highs land within tolerance of the projected line.

    Returns trendline dict or None.
    """
    if len(confirmed_highs) < 2 + min_confirmations:
        return None

    for i in range(len(confirmed_highs) - 1):
        for j in range(i + 1, len(confirmed_highs)):
            a1 = confirmed_highs[i]
            a2 = confirmed_highs[j]

            # Anchors must be descending
            if a2[1] >= a1[1]:
                continue

            confirmations = 0
            last_confirm_bar = a2[0]
            for k in range(j + 1, len(confirmed_highs)):
                bar_k, price_k = confirmed_highs[k]
                projected = trendline_value(a1, a2, bar_k)
                if projected <= 0:
                    continue
                deviation = abs(price_k - projected) / projected
                if deviation <= tolerance:
                    confirmations += 1
                    last_confirm_bar = bar_k

            if confirmations >= min_confirmations:
                return {
                    "type": "resistance",
                    "anchor1": a1,
                    "anchor2": a2,
                    "confirmations": confirmations,
                    "confirmed_at_bar": last_confirm_bar,
                }

    return None


# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_straight_line(
    candles: list[dict],
    pivot_lookback: int = PIVOT_LOOKBACK,
    min_confirmations: int = MIN_CONFIRMATIONS,
    trendline_tolerance: float = TRENDLINE_TOLERANCE,
    enable_short: bool = ENABLE_SHORT,
) -> list[dict]:
    """
    Trendline break strategy.

    States:
      - "long": holding, watching support trendline for break → sell
      - "out": not in market, watching resistance trendline for break → buy
      - "short": (if enabled) holding short, watching resistance trendline for break → cover

    Returns list of trade dicts.
    """
    if not candles:
        return []

    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    closes = [c["close"] for c in candles]

    # --- Find all swings ---
    swing_highs, swing_lows = find_swings(highs, lows, pivot_lookback)

    # --- Progressive confirmation tracking ---
    confirmed_highs: list[tuple[int, float]] = []
    confirmed_lows:  list[tuple[int, float]] = []
    sh_ptr = sl_ptr = 0

    # --- State ---
    trades: list[dict] = []
    position: dict | None = None
    active_trendline: dict | None = None
    # After a trendline breaks, we need to build a new one from swings AFTER the break
    # Track the bar after which to start looking for new trendlines
    search_after_bar: int = 0

    # Track if we already attempted initial entry
    initial_entry_done = False
    # Track bar where break was confirmed (for 1-bar confirmation)
    pending_break: dict | None = None

    for i in range(len(candles)):
        date  = candles[i]["date"]
        price = closes[i]

        # Confirm new swing points
        while sh_ptr < len(swing_highs) and swing_highs[sh_ptr][2] <= i:
            confirmed_highs.append(swing_highs[sh_ptr][:2])
            sh_ptr += 1
        while sl_ptr < len(swing_lows) and swing_lows[sl_ptr][2] <= i:
            confirmed_lows.append(swing_lows[sl_ptr][:2])
            sl_ptr += 1

        # --- Execute pending break (1-bar confirmation) ---
        if pending_break is not None:
            if pending_break["action"] == "sell":
                # Close long position
                if position is not None and position["side"] == "long":
                    trades.append({
                        "entry_date":  position["entry_date"],
                        "entry_price": position["entry_price"],
                        "exit_date":   date,
                        "exit_price":  price,
                        "side":        "long",
                        "exit_reason": "support_break",
                        "strategy":    "straight_line",
                    })
                    position = None

                # Open short if enabled
                if enable_short and position is None:
                    position = {
                        "entry_date":  date,
                        "entry_price": price,
                        "entry_bar":   i,
                        "side":        "short",
                    }

                active_trendline = None
                search_after_bar = pending_break["break_bar"]

            elif pending_break["action"] == "buy":
                # Close short if in one
                if position is not None and position["side"] == "short":
                    trades.append({
                        "entry_date":  position["entry_date"],
                        "entry_price": position["entry_price"],
                        "exit_date":   date,
                        "exit_price":  price,
                        "side":        "short",
                        "exit_reason": "resistance_break",
                        "strategy":    "straight_line",
                    })
                    position = None

                # Open long
                if position is None:
                    position = {
                        "entry_date":  date,
                        "entry_price": price,
                        "entry_bar":   i,
                        "side":        "long",
                    }

                active_trendline = None
                search_after_bar = pending_break["break_bar"]

            pending_break = None

        # --- Check for trendline break ---
        if active_trendline is not None and pending_break is None:
            tl = active_trendline
            projected = trendline_value(tl["anchor1"], tl["anchor2"], i)

            if tl["type"] == "support" and position is not None and position["side"] == "long":
                # Support break: close must be below trendline
                if price < projected:
                    pending_break = {"action": "sell", "break_bar": i}

            elif tl["type"] == "resistance":
                if position is None or (position is not None and position["side"] == "short"):
                    # Resistance break: close must be above trendline
                    if price > projected:
                        pending_break = {"action": "buy", "break_bar": i}

        # --- Try to build trendlines ---
        if active_trendline is None and pending_break is None:
            # Filter swings to only those after search_after_bar
            recent_lows  = [(b, p) for b, p in confirmed_lows  if b >= search_after_bar]
            recent_highs = [(b, p) for b, p in confirmed_highs if b >= search_after_bar]

            if position is not None and position["side"] == "long":
                # We're long → build support trendline
                tl = try_build_support_trendline(recent_lows, trendline_tolerance, min_confirmations)
                if tl and tl["confirmed_at_bar"] <= i:
                    active_trendline = tl

            elif position is not None and position["side"] == "short":
                # We're short → build resistance trendline
                tl = try_build_resistance_trendline(recent_highs, trendline_tolerance, min_confirmations)
                if tl and tl["confirmed_at_bar"] <= i:
                    active_trendline = tl

            elif position is None:
                # Not in market → build resistance trendline for buy signal
                tl = try_build_resistance_trendline(recent_highs, trendline_tolerance, min_confirmations)
                if tl and tl["confirmed_at_bar"] <= i:
                    active_trendline = tl

        # --- Initial entry: determine trend direction ---
        if not initial_entry_done:
            # Ascending swing lows (higher lows) = bullish
            asc_lows = False
            if len(confirmed_lows) >= 3:
                last3 = confirmed_lows[-3:]
                asc_lows = all(last3[k+1][1] > last3[k][1] for k in range(2))

            # Ascending swing highs (higher highs) = bullish
            asc_highs = False
            if len(confirmed_highs) >= 3:
                last3h = confirmed_highs[-3:]
                asc_highs = all(last3h[k+1][1] > last3h[k][1] for k in range(2))

            # Descending swing highs (lower highs) = bearish
            desc_highs = False
            if len(confirmed_highs) >= 3:
                last3h = confirmed_highs[-3:]
                desc_highs = all(last3h[k+1][1] < last3h[k][1] for k in range(2))

            # Descending swing lows (lower lows) = bearish
            desc_lows = False
            if len(confirmed_lows) >= 3:
                last3 = confirmed_lows[-3:]
                desc_lows = all(last3[k+1][1] < last3[k][1] for k in range(2))

            if asc_lows or asc_highs:
                position = {
                    "entry_date":  date,
                    "entry_price": price,
                    "entry_bar":   i,
                    "side":        "long",
                }
                search_after_bar = 0  # build support from all available lows
                initial_entry_done = True
            elif enable_short and (desc_highs or desc_lows):
                position = {
                    "entry_date":  date,
                    "entry_price": price,
                    "entry_bar":   i,
                    "side":        "short",
                }
                search_after_bar = 0  # build resistance from all available highs
                initial_entry_done = True

    # Close any open position at end of data
    if position is not None:
        side = position["side"]
        trades.append({
            "entry_date":  position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date":   candles[-1]["date"],
            "exit_price":  candles[-1]["close"],
            "side":        side,
            "exit_reason": "end_of_data",
            "strategy":    "straight_line",
        })

    return trades


# ==============================================================================
# METRICS & REPORTING
# ==============================================================================

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply transaction costs to each trade."""
    total_cost = (commission_pct + slippage_pct) * 2
    result = []
    for t in trades:
        if t["side"] == "short":
            gross = (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100
        else:
            gross = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
        net = round(gross - total_cost, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3), "cost_pct": round(-total_cost, 3)})
    return result


def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1h") -> dict:
    """Calculate backtest metrics."""
    if not trades:
        return {"total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "long_trades": 0, "short_trades": 0,
                "support_break_exits": 0, "resistance_break_exits": 0, "end_of_data_exits": 0,
                "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252 * 6)

    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]

    capital = initial_capital
    peak    = capital
    max_dd  = 0.0
    returns = []
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak   = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak * 100)

    total_ret = (capital - initial_capital) / initial_capital * 100
    avg_gain  = sum(t["return_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss  = sum(t["return_pct"] for t in losers)  / len(losers)  if losers  else 0
    gp        = sum(t["return_pct"] for t in winners)
    gl        = abs(sum(t["return_pct"] for t in losers))
    pf        = round(gp / gl, 2) if gl > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r  = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / ann) / std_r * math.sqrt(ann), 2)

    wr = len(winners) / len(trades) if trades else 0
    long_count  = sum(1 for t in trades if t["side"] == "long")
    short_count = sum(1 for t in trades if t["side"] == "short")

    return {
        "total_trades":           len(trades),
        "winning_trades":         len(winners),
        "losing_trades":          len(losers),
        "long_trades":            long_count,
        "short_trades":           short_count,
        "support_break_exits":    sum(1 for t in trades if t.get("exit_reason") == "support_break"),
        "resistance_break_exits": sum(1 for t in trades if t.get("exit_reason") == "resistance_break"),
        "end_of_data_exits":      sum(1 for t in trades if t.get("exit_reason") == "end_of_data"),
        "win_rate_pct":           round(wr * 100, 1),
        "final_capital":          round(capital, 2),
        "total_return_pct":       round(total_ret, 2),
        "avg_gain_pct":           round(avg_gain, 2),
        "avg_loss_pct":           round(avg_loss, 2),
        "max_drawdown_pct":       round(-max_dd, 2),
        "profit_factor":          pf,
        "sharpe_ratio":           sharpe,
        "expectancy_pct":         round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }


def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    pivot_lookback: int = PIVOT_LOOKBACK,
    min_confirmations: int = MIN_CONFIRMATIONS,
    trendline_tolerance: float = TRENDLINE_TOLERANCE,
    enable_short: bool = ENABLE_SHORT,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    raw_trades = run_straight_line(candles, pivot_lookback, min_confirmations,
                                    trendline_tolerance, enable_short)
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "straight_line",
        "strategy_label": f"Straight Line (pivot={pivot_lookback}, confirm={min_confirmations}, tol={trendline_tolerance*100:.1f}%)",
        "parameters": {
            "pivot_lookback": pivot_lookback,
            "min_confirmations": min_confirmations,
            "trendline_tolerance": trendline_tolerance,
            "enable_short": enable_short,
        },
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
    parser = argparse.ArgumentParser(description="Straight Line (Trendline Break) Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size (default: 1h)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK, help="Bars left/right for swing detection (default: 5)")
    parser.add_argument("--min-confirmations", type=int, default=MIN_CONFIRMATIONS, help="Extra trendline confirmations needed (default: 2)")
    parser.add_argument("--trendline-tolerance", type=float, default=TRENDLINE_TOLERANCE, help="Tolerance for trendline touch (default: 0.015 = 1.5%%)")
    parser.add_argument("--enable-short", action="store_true", default=ENABLE_SHORT, help="Enable short selling on support break")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Straight Line Strategy — {args.symbol}")
    print(f"  Pivots: {args.pivot_lookback}  |  Confirmations: {args.min_confirmations}  |  Tolerance: {args.trendline_tolerance*100:.1f}%")
    print(f"  Interval: {args.interval}  |  Shorts: {'ON' if args.enable_short else 'OFF'}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_lookback=args.pivot_lookback, min_confirmations=args.min_confirmations,
        trendline_tolerance=args.trendline_tolerance, enable_short=args.enable_short,
    )

    print(f"  Period:           {result['date_from']} -> {result['date_to']} ({result['candles_analyzed']} bars)")
    print(f"  Initial Capital:  ${result['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${result['final_capital']:,.2f}")
    print(f"  Total Return:     {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:     {result['total_trades']} (L:{result['long_trades']} S:{result['short_trades']})")
    print(f"  Win Rate:         {result['win_rate_pct']}%")
    print(f"  Profit Factor:    {result['profit_factor']}")
    print(f"  Sharpe Ratio:     {result['sharpe_ratio']}")
    print(f"  Max Drawdown:     {result['max_drawdown_pct']}%")
    print(f"  Exits:            Support Break: {result['support_break_exits']}  |  Resistance Break: {result['resistance_break_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    fname = f"straight_line_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
