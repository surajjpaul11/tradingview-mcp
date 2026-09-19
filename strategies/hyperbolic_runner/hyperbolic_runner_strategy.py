"""
Hyperbolic Runner Strategy v2
==============================
Designed for stocks making explosive multi-hundred-percent moves (e.g., SNDK, WULF).

Key insight: "Hyperbolic runner" stocks make 2+ explosive 50%+ moves per year.
Smart Hold catastrophically fails these because:
  - 15-25% retraces are just "breaths" between explosive legs
  - profit_lock at 50% exits before the 500%+ continuation
  - Re-entries during consolidation cause 3+ consecutive losses

This strategy:
  - DETECTS explosive cluster regimes (rolling 10%+ moves)
  - ENTERS on EMA reclaim or RSI bounce, only outside consolidation zones
  - HOLDS aggressively with 20x ATR trailing stop (no profit lock)
  - EXITS only on CONFIRMED reversal (2+ bars below 20-period low + RSI < 40)
  - AVOIDS re-entry during consolidation (cooldown + zone filter)

Usage:
    python strategies/hyperbolic_runner/hyperbolic_runner_strategy.py --symbol SNDK
    python strategies/hyperbolic_runner/hyperbolic_runner_strategy.py --symbol WULF --period 2y --chart
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

# ── Strategy Parameters ──────────────────────────────────────────────

FAST_EMA = 9
SLOW_SMA = 50
ATR_MULT = 20.0            # Very wide trailing stop
ATR_PERIOD = 14
RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_BREAKDOWN = 40         # RSI threshold for hard breakdown exit
BREAKDOWN_LOW_PERIOD = 20  # Period for 20-bar low check

CONSOLIDATION_RSI_LOW = 35
CONSOLIDATION_RSI_HIGH = 65
CONSOLIDATION_RSI_BARS = 5
CONSOLIDATION_ATR_RATIO = 0.7
CONSOLIDATION_ATR_BARS = 5

COOLDOWN_AFTER_LOSS = 20
COOLDOWN_AFTER_WIN = 5

# Pyramid parameters (v2)
PYRAMID_ADD_SIZE = 0.5     # Each pyramid add = 50% of base allocation
MAX_PYRAMID_SIZE = 1.5     # Max total_size (base 1.0 + one add of 0.5)
PYRAMID_COOLDOWN = 5       # Bars between pyramid adds

CLUSTER_MOVE_PCT = 10.0    # What counts as a "big move" for cluster detection
CLUSTER_WINDOW = 30        # Bars to look back for cluster detection
CLUSTER_MIN_COUNT = 2      # Min big moves to be in explosive cluster

COMMISSION = 0.001
SLIPPAGE = 0.001
INITIAL_CAPITAL = 10000.0
PERIOD = "2y"
INTERVAL = "1d"


# ── Data Fetching ────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "hyperbolic-runner/1.0"})
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


# ── Indicators ───────────────────────────────────────────────────────

def sma(values: list[float], period: int) -> list[float | None]:
    out = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1 : i + 1]) / period
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
            prev_c = candles[i - 1]["close"]
            trs.append(max(c["high"] - c["low"], abs(c["high"] - prev_c), abs(c["low"] - prev_c)))
    return ema(trs, period)


def calc_rsi(values: list[float], period: int = 14) -> list[float | None]:
    out = [None] * len(values)
    if len(values) < period + 1:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        out[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0)) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def calc_macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list, list]:
    """MACD(fast, slow, signal). Returns (macd_line, signal_line)."""
    n = len(closes)
    fast_ema_vals = ema(closes, fast)
    slow_ema_vals = ema(closes, slow)

    macd_line: list[float | None] = [None] * n
    for i in range(slow - 1, n):
        if fast_ema_vals[i] is not None and slow_ema_vals[i] is not None:
            macd_line[i] = fast_ema_vals[i] - slow_ema_vals[i]

    macd_fill = [v if v is not None else 0.0 for v in macd_line]
    signal_raw = ema(macd_fill, signal)
    signal_line: list[float | None] = [None] * n
    first_valid = slow - 1 + signal - 1
    for i in range(first_valid, n):
        signal_line[i] = signal_raw[i]

    return macd_line, signal_line


# ── Strategy Engine ──────────────────────────────────────────────────

def run_hyperbolic_runner(
    candles: list[dict],
    params: dict | None = None,
) -> dict:
    p = params or {}

    fast_ema_period = p.get("fast_ema", FAST_EMA)
    slow_sma_period = p.get("slow_sma", SLOW_SMA)
    atr_period = p.get("atr_period", ATR_PERIOD)
    rsi_period = p.get("rsi_period", RSI_PERIOD)
    commission = p.get("commission", COMMISSION)
    slippage = p.get("slippage", SLIPPAGE)
    initial_capital = p.get("initial_capital", INITIAL_CAPITAL)
    cooldown_loss = p.get("cooldown_after_loss", COOLDOWN_AFTER_LOSS)
    cooldown_win = p.get("cooldown_after_win", COOLDOWN_AFTER_WIN)

    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    n = len(candles)

    # Compute indicators
    fast_ema_vals = ema(closes, fast_ema_period)
    exit_sma_vals = sma(closes, slow_sma_period)
    rsi_vals = calc_rsi(closes, rsi_period)
    atr_vals = calc_atr(candles, atr_period)
    macd_line_vals, macd_signal_vals = calc_macd(closes, 12, 26, 9)
    vol_sma_vals = sma(volumes, 20)  # 20-bar volume MA for pyramid/exit signals

    # Compute median ATR for consolidation detection
    valid_atrs = [a for a in atr_vals if a is not None]
    if valid_atrs:
        sorted_atrs = sorted(valid_atrs)
        median_atr = sorted_atrs[len(sorted_atrs) // 2]
    else:
        median_atr = 1.0

    pyramid_add_size = p.get("pyramid_add_size", PYRAMID_ADD_SIZE)
    max_pyramid_size = p.get("max_pyramid_size", MAX_PYRAMID_SIZE)
    pyramid_cooldown = p.get("pyramid_cooldown", PYRAMID_COOLDOWN)

    # State — do NOT enter on first bar (unlike Smart Hold)
    warmup = max(fast_ema_period, slow_sma_period, rsi_period) + 1
    in_position = False
    entry_price = 0.0
    entry_date = ""
    entry_reason = ""
    peak_price = 0.0
    bars_since_exit = 999
    last_trade_was_win = False

    # Pyramid state (v2)
    total_size = 1.0           # Current position size multiplier (1.0 = base)
    weighted_entry_price = 0.0 # Weighted average cost basis (used for trailing stop reference)
    pyramid_lots: list[dict] = []  # Each lot: {"size": float, "price": float}
    pyramid_count = 0          # Adds fired this trade
    bars_since_pyramid = 999   # Bars since last pyramid add (for cooldown)

    trades: list[dict] = []
    capital = initial_capital
    cost_pct = (commission + slippage) * 100  # as percent

    exit_counts = {
        "hard_breakdown": 0,
        "trailing_stop": 0,
        "volume_momentum_exit": 0,
        "end_of_data": 0,
    }

    # Import signal registry
    try:
        from strategies.hyperbolic_runner.signals.registry import ENTRY_SIGNALS, EXIT_SIGNALS, PYRAMID_SIGNALS
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from strategies.hyperbolic_runner.signals.registry import ENTRY_SIGNALS, EXIT_SIGNALS, PYRAMID_SIGNALS

    for i in range(1, n):
        c = candles[i]
        close = c["close"]
        date = c["date"]

        # Build context dict for signal evaluation
        ctx = {
            "i": i, "n": n,
            "candle": c, "close": close,
            "closes": closes, "candles": candles,
            "fast_ema_vals": fast_ema_vals,
            "exit_sma_vals": exit_sma_vals,
            "rsi_vals": rsi_vals,
            "atr_vals": atr_vals,
            "vol_sma_vals": vol_sma_vals,
            "macd_line": macd_line_vals,
            "macd_signal": macd_signal_vals,
            "params": p,
            "warmup": warmup,
            "median_atr": median_atr,
            "peak_price": peak_price,
            "in_position": in_position,
            "entry_price": entry_price if in_position else None,
            "entry_date": entry_date if in_position else "",
            "weighted_entry_price": weighted_entry_price if in_position else None,
            "total_size": total_size,
            "pyramid_count": pyramid_count,
            "bars_since_pyramid": bars_since_pyramid,
            "bars_since_exit": bars_since_exit,
            "trades": trades,
        }

        if not in_position:
            bars_since_exit += 1

            # Adaptive cooldown based on last trade result
            cooldown = cooldown_win if last_trade_was_win else cooldown_loss
            if bars_since_exit < cooldown:
                continue

            if i < warmup:
                continue

            # Consolidation check: no re-entry in consolidation zone
            # (handled inside each signal's check() — signals self-filter)

            # Evaluate entry signals (first match wins)
            for sig in ENTRY_SIGNALS:
                if sig.check(ctx):
                    in_position = True
                    entry_price = close
                    entry_date = date
                    entry_reason = sig.METADATA["name"]
                    peak_price = close
                    # Reset pyramid state for new trade
                    total_size = 1.0
                    weighted_entry_price = close
                    pyramid_lots = [{"size": 1.0, "price": close}]
                    pyramid_count = 0
                    bars_since_pyramid = 999
                    break

        else:
            # Update peak
            if close > peak_price:
                peak_price = close

            ctx["peak_price"] = peak_price
            bars_since_pyramid += 1

            # Pyramid evaluation — scale into position on momentum surges (v2)
            if total_size < max_pyramid_size:
                ctx["bars_since_pyramid"] = bars_since_pyramid
                ctx["weighted_entry_price"] = weighted_entry_price
                ctx["total_size"] = total_size
                for sig in PYRAMID_SIGNALS:
                    if sig.check(ctx):
                        # Add new lot: track it separately for correct P&L
                        pyramid_lots.append({"size": pyramid_add_size, "price": close})
                        new_size = total_size + pyramid_add_size
                        weighted_entry_price = (weighted_entry_price * total_size + close * pyramid_add_size) / new_size
                        total_size = new_size
                        pyramid_count += 1
                        bars_since_pyramid = 0
                        ctx["weighted_entry_price"] = weighted_entry_price
                        ctx["total_size"] = total_size
                        break

            # Evaluate exit signals (first match wins)
            exit_signal = False
            exit_reason = ""
            for sig in EXIT_SIGNALS:
                fired, reason = sig.check(ctx)
                if fired:
                    exit_signal = True
                    exit_reason = reason
                    break

            if exit_signal:
                # P&L sums each lot's profit relative to the base (first lot) capital.
                # This correctly credits pyramid adds as ADDITIONAL profit on top of the base:
                #   base lot: (exit - entry) / entry * 100%
                #   pyramid lot (size 0.5): 0.5 * (exit - add_price) / entry * 100%
                # So a profitable pyramid add INCREASES total return (as expected).
                base_price = pyramid_lots[0]["price"] if pyramid_lots else entry_price
                gross_ret = sum(
                    lot["size"] * (close - lot["price"]) / base_price * 100
                    for lot in pyramid_lots
                ) if pyramid_lots else (close - entry_price) / entry_price * 100
                # Costs: 2x commission/slippage for base entry+exit, plus 1x per pyramid add (open only)
                total_cost = cost_pct * 2 + pyramid_count * cost_pct
                net_ret = gross_ret - total_cost
                capital *= (1 + net_ret / 100)

                last_trade_was_win = net_ret > 0

                trades.append({
                    "entry_date": entry_date,
                    "entry_price": round(entry_price, 2),
                    "weighted_entry_price": round(weighted_entry_price, 2),
                    "exit_date": date,
                    "exit_price": round(close, 2),
                    "side": "long",
                    "entry_reason": entry_reason,
                    "exit_reason": exit_reason,
                    "return_pct": round(net_ret, 2),
                    "gross_return_pct": round(gross_ret, 2),
                    "cost_pct": round(-total_cost, 2),
                    "pyramid_adds": pyramid_count,
                    "final_size": round(total_size, 2),
                    "strategy": "hyperbolic_runner_v2",
                })
                exit_counts[exit_reason] = exit_counts.get(exit_reason, 0) + 1

                in_position = False
                bars_since_exit = 0
                # Reset pyramid state
                total_size = 1.0
                weighted_entry_price = 0.0
                pyramid_lots = []
                pyramid_count = 0
                bars_since_pyramid = 999

    # ── Compute metrics ──
    bh_ret = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100
    total_ret = (capital - initial_capital) / initial_capital * 100

    winning = [t for t in trades if t["return_pct"] > 0]
    losing = [t for t in trades if t["return_pct"] <= 0]
    win_rate = round(len(winning) / len(trades) * 100, 1) if trades else 0.0

    avg_gain = round(statistics.mean([t["return_pct"] for t in winning]), 2) if winning else 0.0
    avg_loss = round(statistics.mean([t["return_pct"] for t in losing]), 2) if losing else 0.0

    gross_wins = sum(t["return_pct"] for t in winning)
    gross_losses = abs(sum(t["return_pct"] for t in losing))
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else float("inf")

    # Max drawdown from equity curve
    equity = initial_capital
    peak_equity = equity
    max_dd = 0.0
    for t in trades:
        equity *= (1 + t["return_pct"] / 100)
        if equity > peak_equity:
            peak_equity = equity
        dd = (equity - peak_equity) / peak_equity * 100
        if dd < max_dd:
            max_dd = dd

    # Sharpe ratio
    if len(trades) >= 2:
        rets = [t["return_pct"] for t in trades]
        avg_r = statistics.mean(rets)
        std_r = statistics.stdev(rets)
        trades_per_year = 252 / max(1, n / len(trades))
        sharpe = round(avg_r / std_r * math.sqrt(trades_per_year), 2) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # Time in market
    bars_in = 0
    for t in trades:
        entry_idx = next((j for j, c in enumerate(candles) if c["date"] == t["entry_date"]), 0)
        exit_idx = next((j for j, c in enumerate(candles) if c["date"] == t["exit_date"]), 0)
        bars_in += (exit_idx - entry_idx)
    time_in_market = round(bars_in / n * 100, 1) if n > 0 else 0.0

    # Build overlays for charting
    sma_overlay = []
    ema_overlay = []
    rsi_overlay = []
    for j in range(n):
        if exit_sma_vals[j] is not None:
            sma_overlay.append({"time": candles[j]["date"], "value": round(exit_sma_vals[j], 4)})
        if fast_ema_vals[j] is not None:
            ema_overlay.append({"time": candles[j]["date"], "value": round(fast_ema_vals[j], 4)})
        if rsi_vals[j] is not None:
            rsi_overlay.append({"time": candles[j]["date"], "value": round(rsi_vals[j], 2)})

    result = {
        "symbol": p.get("symbol", ""),
        "strategy": "hyperbolic_runner_v2",
        "strategy_label": (
            f"Hyperbolic Runner v2 (EMA={fast_ema_period}, SMA={slow_sma_period}, "
            f"ATR trail={p.get('atr_mult', ATR_MULT)}x, "
            f"Pyramid add={pyramid_add_size}x up to {max_pyramid_size}x, "
            f"Cooldown loss={cooldown_loss}/win={cooldown_win})"
        ),
        "parameters": {
            "fast_ema": fast_ema_period,
            "slow_sma": slow_sma_period,
            "atr_mult": p.get("atr_mult", ATR_MULT),
            "atr_period": atr_period,
            "rsi_period": rsi_period,
            "rsi_oversold": p.get("rsi_oversold", RSI_OVERSOLD),
            "rsi_breakdown": p.get("rsi_breakdown", RSI_BREAKDOWN),
            "breakdown_low_period": p.get("breakdown_low_period", BREAKDOWN_LOW_PERIOD),
            "consolidation_rsi_low": p.get("consolidation_rsi_low", CONSOLIDATION_RSI_LOW),
            "consolidation_rsi_high": p.get("consolidation_rsi_high", CONSOLIDATION_RSI_HIGH),
            "consolidation_rsi_bars": p.get("consolidation_rsi_bars", CONSOLIDATION_RSI_BARS),
            "consolidation_atr_ratio": p.get("consolidation_atr_ratio", CONSOLIDATION_ATR_RATIO),
            "consolidation_atr_bars": p.get("consolidation_atr_bars", CONSOLIDATION_ATR_BARS),
            "cooldown_after_loss": cooldown_loss,
            "cooldown_after_win": cooldown_win,
            "cluster_move_pct": p.get("cluster_move_pct", CLUSTER_MOVE_PCT),
            "cluster_window": p.get("cluster_window", CLUSTER_WINDOW),
            "cluster_min_count": p.get("cluster_min_count", CLUSTER_MIN_COUNT),
            "median_atr": round(median_atr, 4),
        },
        "period": p.get("period", PERIOD),
        "interval": p.get("interval", INTERVAL),
        "candles_analyzed": n,
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "initial_capital": initial_capital,
        "commission": commission,
        "slippage": slippage,
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
        "time_in_market_pct": time_in_market,
        "hard_breakdown_exits": exit_counts.get("hard_breakdown", 0),
        "volume_momentum_exits": exit_counts.get("volume_momentum_exit", 0),
        "trailing_stop_exits": exit_counts.get("trailing_stop", 0),
        "end_of_data_exits": exit_counts.get("end_of_data", 0),
        "trade_log": trades,
        "overlays": [
            {"label": f"SMA({slow_sma_period})", "color": "#FF9800", "type": "line", "points": sma_overlay},
            {"label": f"EMA({fast_ema_period})", "color": "#2196F3", "type": "line", "points": ema_overlay},
            {"label": "RSI(14)", "color": "#E040FB", "type": "rsi_panel", "points": rsi_overlay},
        ],
        "data_source": "Yahoo Finance",
        "disclaimer": "Past performance does not guarantee future results. For educational use only.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hyperbolic Runner Strategy Backtester")
    parser.add_argument("--symbol", default="SNDK", help="Yahoo Finance symbol (default: SNDK)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION)
    parser.add_argument("--slippage", type=float, default=SLIPPAGE)
    parser.add_argument("--fast-ema", type=int, default=FAST_EMA, help="Fast EMA period")
    parser.add_argument("--slow-sma", type=int, default=SLOW_SMA, help="Slow SMA period")
    parser.add_argument("--atr-mult", type=float, default=ATR_MULT, help="ATR trailing stop multiplier")
    parser.add_argument("--cooldown-loss", type=int, default=COOLDOWN_AFTER_LOSS, help="Bars to wait after a loss")
    parser.add_argument("--cooldown-win", type=int, default=COOLDOWN_AFTER_WIN, help="Bars to wait after a win")
    parser.add_argument("--chart", action="store_true", help="Generate interactive HTML chart")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Hyperbolic Runner Strategy v2 — {args.symbol}")
    print(f"  Fast EMA: {args.fast_ema}  |  Slow SMA: {args.slow_sma}")
    print(f"  ATR Trail: {args.atr_mult}x  |  Cooldown: loss={args.cooldown_loss} / win={args.cooldown_win} bars")
    print(f"{'='*60}")
    print(f"\n  Fetching {args.symbol} data...")

    candles = fetch_ohlcv(args.symbol, args.period, args.interval)
    print(f"  Fetched {len(candles)} candles")

    params = {
        "symbol": args.symbol,
        "period": args.period,
        "interval": args.interval,
        "initial_capital": args.initial_capital,
        "commission": args.commission,
        "slippage": args.slippage,
        "fast_ema": args.fast_ema,
        "slow_sma": args.slow_sma,
        "atr_mult": args.atr_mult,
        "cooldown_after_loss": args.cooldown_loss,
        "cooldown_after_win": args.cooldown_win,
        # Defaults for all other params (can be overridden)
        "rsi_oversold": RSI_OVERSOLD,
        "rsi_breakdown": RSI_BREAKDOWN,
        "breakdown_low_period": BREAKDOWN_LOW_PERIOD,
        "consolidation_rsi_low": CONSOLIDATION_RSI_LOW,
        "consolidation_rsi_high": CONSOLIDATION_RSI_HIGH,
        "consolidation_rsi_bars": CONSOLIDATION_RSI_BARS,
        "consolidation_atr_ratio": CONSOLIDATION_ATR_RATIO,
        "consolidation_atr_bars": CONSOLIDATION_ATR_BARS,
        "cluster_move_pct": CLUSTER_MOVE_PCT,
        "cluster_window": CLUSTER_WINDOW,
        "cluster_min_count": CLUSTER_MIN_COUNT,
    }

    result = run_hyperbolic_runner(candles, params)

    print(f"\n  Period:           {result['date_from']} -> {result['date_to']} ({result['candles_analyzed']} bars)")
    print(f"  Initial Capital:  ${result['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${result['final_capital']:,.2f}")
    print(f"  Total Return:     {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Time in Market:   {result['time_in_market_pct']}%")
    print(f"  Total Trades:     {result['total_trades']}")
    print(f"  Win Rate:         {result['win_rate_pct']}%")
    print(f"  Avg Gain:         {result['avg_gain_pct']:+.2f}%")
    print(f"  Avg Loss:         {result['avg_loss_pct']:+.2f}%")
    print(f"  Profit Factor:    {result['profit_factor']}")
    print(f"  Sharpe Ratio:     {result['sharpe_ratio']}")
    print(f"  Max Drawdown:     {result['max_drawdown_pct']}%")
    print(f"  Exits:            Hard Breakdown: {result['hard_breakdown_exits']}  |  Vol Momentum: {result['volume_momentum_exits']}  |  Trailing Stop: {result['trailing_stop_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        pyramid_tag = f" [+{t['pyramid_adds']}x pyramid]" if t.get("pyramid_adds", 0) > 0 else ""
        print(f"    LONG  {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t['exit_reason']}] ({t['entry_reason']}){pyramid_tag}")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    json_result = {k: v for k, v in result.items() if k != "overlays"}
    fname = script_dir / f"hyperbolic_runner_backtest_{args.symbol.replace('-', '_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")

    if args.chart:
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html

        vix_candles = fetch_ohlcv("^VIX", args.period, args.interval)
        print(f"  Fetched {len(vix_candles)} VIX candles")

        chart_path = script_dir / f"hyperbolic_runner_chart_{args.symbol.replace('-', '_')}_{args.period}.html"
        generate_chart_html(
            result=result,
            candles=candles,
            output_path=chart_path,
            vix_candles=vix_candles,
        )
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
