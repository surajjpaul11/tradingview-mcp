"""
Sloped Lines Strategy — Standalone Python Implementation
==========================================================

Alternating trendline breakout strategy.

The idea is simple:
  - When price is falling, draw a DESCENDING line connecting two recent
    swing highs (lower highs). As long as price stays below, stay out.
    When price BREAKS ABOVE this line → BUY.

  - When holding, draw an ASCENDING line connecting two recent swing lows
    (higher lows). As long as price stays above, keep holding.
    When price BREAKS BELOW this line → SELL.

Visual reference:
  Green lines = descending resistance (lower highs) — break above = buy
  Blue lines  = ascending support (higher lows) — break below = sell

Usage:
  python sloped_lines_strategy.py                                 # defaults: SPY, 2y, 1h
  python sloped_lines_strategy.py --symbol BTC-USD --period 1y
  python sloped_lines_strategy.py --symbol AAPL --enable-short
  python sloped_lines_strategy.py --symbol NVDA --trendline-tolerance 0.01

Requires: no external dependencies (pure stdlib + Yahoo Finance API)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import math
import statistics
import urllib.request
from datetime import datetime, timezone
from typing import Optional


# ==============================================================================
# STRATEGY PARAMETERS
# ==============================================================================

PIVOT_LOOKBACK       = 5       # bars left/right for swing point detection
TRENDLINE_TOLERANCE  = 0.015   # 1.5% tolerance for validation (nothing breaks through)
CONFIRM_BARS         = 1       # consecutive bars to confirm a breakout
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
    req = urllib.request.Request(url, headers={"User-Agent": "sloped-lines-strategy/1.0"})
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

    A swing high at bar i is confirmed once we've seen `lookback` bars after it.
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
# TRENDLINE HELPERS
# ==============================================================================

def trendline_value(anchor1: tuple[int, float], anchor2: tuple[int, float], bar: int) -> float:
    """Calculate the projected trendline value at a given bar index."""
    b1, p1 = anchor1
    b2, p2 = anchor2
    if b2 == b1:
        return p1
    slope = (p2 - p1) / (b2 - b1)
    return p1 + slope * (bar - b1)


# ==============================================================================
# LINE CONSTRUCTION WITH VALIDATION
# ==============================================================================

def build_descending_resistance(
    confirmed_highs: list[tuple[int, float]],
    closes: list[float],
    search_after_bar: int = 0,
    tolerance: float = TRENDLINE_TOLERANCE,
) -> dict | None:
    """
    Build a descending resistance line from two swing highs (lower highs).

    Validation: no candle close between anchor1 and anchor2 is above the line
    (within tolerance). This ensures the line truly acts as resistance that
    nothing has broken through.

    Returns trendline dict with anchor points, or None if no valid line found.
    """
    # Filter to highs after the search point
    eligible = [(b, p) for b, p in confirmed_highs if b >= search_after_bar]

    if len(eligible) < 2:
        return None

    # Try pairs starting from the most recent (we want the freshest line)
    # Iterate in reverse to prioritize recent swing highs
    best = None
    for i in range(len(eligible) - 2, -1, -1):
        for j in range(i + 1, len(eligible)):
            a1 = eligible[i]   # earlier point
            a2 = eligible[j]   # later point

            # Must be descending (lower highs)
            if a2[1] >= a1[1]:
                continue

            # Validate: no close between a1 and a2 is above the line
            valid = True
            for bar in range(a1[0] + 1, min(a2[0], len(closes))):
                if bar < 0 or bar >= len(closes):
                    continue
                projected = trendline_value(a1, a2, bar)
                if projected <= 0:
                    continue
                # Allow tolerance: close can be slightly above
                if closes[bar] > projected * (1 + tolerance):
                    valid = False
                    break

            if valid:
                line = {
                    "type": "resistance",
                    "direction": "descending",
                    "anchor1": a1,
                    "anchor2": a2,
                    "confirmed_at_bar": a2[0],  # line is drawable once we have both anchors confirmed
                }
                # Prefer the most recent line (earliest i in reverse means latest)
                if best is None:
                    best = line
                else:
                    # Prefer the line with the later anchor2 (most recent)
                    if line["anchor2"][0] > best["anchor2"][0]:
                        best = line
                    elif line["anchor2"][0] == best["anchor2"][0] and line["anchor1"][0] > best["anchor1"][0]:
                        best = line

            if best is not None and best["anchor1"] == eligible[i]:
                break  # found a good line with this i, no need to try more j's

    return best


def build_ascending_support(
    confirmed_lows: list[tuple[int, float]],
    closes: list[float],
    search_after_bar: int = 0,
    tolerance: float = TRENDLINE_TOLERANCE,
) -> dict | None:
    """
    Build an ascending support line from two swing lows (higher lows).

    Validation: no candle close between anchor1 and anchor2 is below the line
    (within tolerance). This ensures the line truly acts as support that
    nothing has broken through.

    Returns trendline dict with anchor points, or None if no valid line found.
    """
    # Filter to lows after the search point
    eligible = [(b, p) for b, p in confirmed_lows if b >= search_after_bar]

    if len(eligible) < 2:
        return None

    # Try pairs starting from the most recent
    best = None
    for i in range(len(eligible) - 2, -1, -1):
        for j in range(i + 1, len(eligible)):
            a1 = eligible[i]   # earlier point
            a2 = eligible[j]   # later point

            # Must be ascending (higher lows)
            if a2[1] <= a1[1]:
                continue

            # Validate: no close between a1 and a2 is below the line
            valid = True
            for bar in range(a1[0] + 1, min(a2[0], len(closes))):
                if bar < 0 or bar >= len(closes):
                    continue
                projected = trendline_value(a1, a2, bar)
                if projected <= 0:
                    continue
                # Allow tolerance: close can be slightly below
                if closes[bar] < projected * (1 - tolerance):
                    valid = False
                    break

            if valid:
                line = {
                    "type": "support",
                    "direction": "ascending",
                    "anchor1": a1,
                    "anchor2": a2,
                    "confirmed_at_bar": a2[0],
                }
                if best is None:
                    best = line
                else:
                    if line["anchor2"][0] > best["anchor2"][0]:
                        best = line
                    elif line["anchor2"][0] == best["anchor2"][0] and line["anchor1"][0] > best["anchor1"][0]:
                        best = line

            if best is not None and best["anchor1"] == eligible[i]:
                break

    return best


# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_sloped_lines(
    candles: list[dict],
    pivot_lookback: int = PIVOT_LOOKBACK,
    trendline_tolerance: float = TRENDLINE_TOLERANCE,
    confirm_bars: int = CONFIRM_BARS,
    enable_short: bool = ENABLE_SHORT,
) -> tuple[list[dict], list[dict]]:
    """
    Sloped Lines strategy — alternating trendline breakout.

    States:
      - "waiting_for_buy": out of market, watching descending resistance for
                           upward break → buy
      - "holding":         long position, watching ascending support for
                           downward break → sell
      - "short" (optional): short position, watching descending resistance for
                             upward break → cover + buy

    Returns:
      (trades, trendlines) — trades is a list of trade dicts,
                              trendlines is a list of line dicts for visualization
    """
    if not candles:
        return [], []

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
    trendlines: list[dict] = []  # for visualization
    position: dict | None = None
    active_trendline: dict | None = None

    # After a trendline breaks, look for new swings after this bar
    search_after_bar: int = 0

    # Track consecutive bars beyond the trendline for confirmation
    break_count: int = 0
    pending_break_action: str | None = None  # "buy" or "sell"
    pending_break_bar: int = 0

    # State: "waiting_for_buy", "holding", "short"
    state: str = "waiting_for_buy"

    for i in range(len(candles)):
        date  = candles[i]["date"]
        price = closes[i]

        # --- Confirm new swing points ---
        while sh_ptr < len(swing_highs) and swing_highs[sh_ptr][2] <= i:
            confirmed_highs.append(swing_highs[sh_ptr][:2])
            sh_ptr += 1
        while sl_ptr < len(swing_lows) and swing_lows[sl_ptr][2] <= i:
            confirmed_lows.append(swing_lows[sl_ptr][:2])
            sl_ptr += 1

        # --- Check for trendline break confirmation ---
        if active_trendline is not None:
            tl = active_trendline
            projected = trendline_value(tl["anchor1"], tl["anchor2"], i)

            if state == "waiting_for_buy" or state == "short":
                # Watching descending resistance — break ABOVE = buy signal
                if tl["type"] == "resistance" and price > projected:
                    break_count += 1
                    if break_count >= confirm_bars:
                        # Record trendline for visualization (mark it as broken)
                        trendlines.append({
                            **tl,
                            "break_bar": i,
                            "break_price": price,
                            "break_date": date,
                        })

                        # Close short if in one
                        if position is not None and position["side"] == "short":
                            trades.append({
                                "entry_date":  position["entry_date"],
                                "entry_price": position["entry_price"],
                                "exit_date":   date,
                                "exit_price":  price,
                                "side":        "short",
                                "exit_reason": "resistance_break",
                                "strategy":    "sloped_lines",
                            })
                            position = None

                        # Open long
                        position = {
                            "entry_date":  date,
                            "entry_price": price,
                            "entry_bar":   i,
                            "side":        "long",
                        }
                        state = "holding"
                        active_trendline = None
                        search_after_bar = i
                        break_count = 0
                        pending_break_action = None
                        continue
                else:
                    break_count = 0

            elif state == "holding":
                # Watching ascending support — break BELOW = sell signal
                if tl["type"] == "support" and price < projected:
                    break_count += 1
                    if break_count >= confirm_bars:
                        # Record trendline for visualization
                        trendlines.append({
                            **tl,
                            "break_bar": i,
                            "break_price": price,
                            "break_date": date,
                        })

                        # Close long
                        if position is not None and position["side"] == "long":
                            trades.append({
                                "entry_date":  position["entry_date"],
                                "entry_price": position["entry_price"],
                                "exit_date":   date,
                                "exit_price":  price,
                                "side":        "long",
                                "exit_reason": "support_break",
                                "strategy":    "sloped_lines",
                            })
                            position = None

                        # Open short if enabled
                        if enable_short:
                            position = {
                                "entry_date":  date,
                                "entry_price": price,
                                "entry_bar":   i,
                                "side":        "short",
                            }
                            state = "short"
                        else:
                            state = "waiting_for_buy"

                        active_trendline = None
                        search_after_bar = i
                        break_count = 0
                        pending_break_action = None
                        continue
                else:
                    break_count = 0

        # --- Try to build trendlines if we don't have an active one ---
        if active_trendline is None:
            if state == "waiting_for_buy" or state == "short":
                # Build descending resistance from recent swing highs
                tl = build_descending_resistance(
                    confirmed_highs, closes,
                    search_after_bar=search_after_bar,
                    tolerance=trendline_tolerance,
                )
                if tl is not None and tl["confirmed_at_bar"] <= i:
                    active_trendline = tl
                    break_count = 0

            elif state == "holding":
                # Build ascending support from recent swing lows
                tl = build_ascending_support(
                    confirmed_lows, closes,
                    search_after_bar=search_after_bar,
                    tolerance=trendline_tolerance,
                )
                if tl is not None and tl["confirmed_at_bar"] <= i:
                    active_trendline = tl
                    break_count = 0

    # --- Close any open position at end of data ---
    if position is not None:
        side = position["side"]
        trades.append({
            "entry_date":  position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date":   candles[-1]["date"],
            "exit_price":  candles[-1]["close"],
            "side":        side,
            "exit_reason": "end_of_data",
            "strategy":    "sloped_lines",
        })

    # If there's a still-active (unbroken) trendline, record it too
    if active_trendline is not None:
        trendlines.append({
            **active_trendline,
            "break_bar": None,  # still active
            "break_price": None,
            "break_date": None,
        })

    return trades, trendlines


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


# ==============================================================================
# BACKTEST PIPELINE
# ==============================================================================

def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    pivot_lookback: int = PIVOT_LOOKBACK,
    trendline_tolerance: float = TRENDLINE_TOLERANCE,
    confirm_bars: int = CONFIRM_BARS,
    enable_short: bool = ENABLE_SHORT,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    raw_trades, trendlines = run_sloped_lines(
        candles, pivot_lookback, trendline_tolerance, confirm_bars, enable_short,
    )
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    # Serialize trendlines for JSON output
    serialized_trendlines = []
    for tl in trendlines:
        serialized_trendlines.append({
            "type": tl["type"],
            "direction": tl["direction"],
            "anchor1_bar": tl["anchor1"][0],
            "anchor1_price": tl["anchor1"][1],
            "anchor2_bar": tl["anchor2"][0],
            "anchor2_price": tl["anchor2"][1],
            "break_bar": tl.get("break_bar"),
            "break_price": tl.get("break_price"),
            "break_date": tl.get("break_date"),
        })

    return {
        "symbol": symbol.upper(),
        "strategy": "sloped_lines",
        "strategy_label": f"Sloped Lines (pivot={pivot_lookback}, tol={trendline_tolerance*100:.1f}%, confirm={confirm_bars})",
        "parameters": {
            "pivot_lookback": pivot_lookback,
            "trendline_tolerance": trendline_tolerance,
            "confirm_bars": confirm_bars,
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
        "trendlines": serialized_trendlines,
        "trade_log": trades,
        "candles": candles,  # include for visualization
        "data_source": "Yahoo Finance",
        "disclaimer": "Past performance does not guarantee future results. For educational use only.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Sloped Lines (Trendline Breakout) Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size (default: 1h)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--pivot-lookback", type=int, default=PIVOT_LOOKBACK, help="Bars left/right for swing detection (default: 5)")
    parser.add_argument("--trendline-tolerance", type=float, default=TRENDLINE_TOLERANCE, help="Tolerance for trendline validation (default: 0.015 = 1.5%%)")
    parser.add_argument("--confirm-bars", type=int, default=CONFIRM_BARS, help="Consecutive bars beyond trendline to confirm break (default: 1)")
    parser.add_argument("--enable-short", action="store_true", default=ENABLE_SHORT, help="Enable short selling on support break")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Sloped Lines Strategy — {args.symbol}")
    print(f"  Pivots: {args.pivot_lookback}  |  Tolerance: {args.trendline_tolerance*100:.1f}%  |  Confirm: {args.confirm_bars}")
    print(f"  Interval: {args.interval}  |  Shorts: {'ON' if args.enable_short else 'OFF'}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        pivot_lookback=args.pivot_lookback, trendline_tolerance=args.trendline_tolerance,
        confirm_bars=args.confirm_bars, enable_short=args.enable_short,
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
    print(f"  Trendlines:       {len(result['trendlines'])} drawn")
    print(f"  Exits:            Support Break: {result['support_break_exits']}  |  Resistance Break: {result['resistance_break_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        side = t["side"].upper()
        print(f"    {side:5s} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    # Save results (without candles to keep file size manageable)
    output = {k: v for k, v in result.items() if k != "candles"}
    script_dir = Path(__file__).resolve().parent
    fname = script_dir / f"sloped_lines_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
