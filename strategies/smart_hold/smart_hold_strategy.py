"""
Smart Buy & Hold Strategy v4
=============================
Stay long almost all the time (like buy & hold), but:
  - EXIT only on confirmed downturns (adaptive to stock volatility)
  - RE-ENTER at peak fear (VIX spike) or when trend resumes
  - Goal: capture 95%+ of upside, avoid the big drawdowns

Adapts exit sensitivity to each stock's volatility:
  - Calm stocks (SPY): exit quickly on breakdown
  - Volatile stocks (STX, PAAS): require more confirmation to avoid whipsaws

Uses VIX (^VIX) as a fear/greed gauge alongside price-based signals.

Usage:
    python strategies/smart_hold/smart_hold_strategy.py --symbol GOOGL
    python strategies/smart_hold/smart_hold_strategy.py --symbol QQQ --period 2y
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

PERIOD = "2y"
INTERVAL = "1d"
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05

# Trend detection
FAST_MA = 10          # fast EMA for momentum
SLOW_MA = 50          # slow SMA — primary trend filter

# Exit signals — deliberately insensitive; we only want to exit on REAL downturns
EXIT_MA = 50          # exit when price breaks below this SMA
EXIT_CONFIRM_BARS = 3 # BASE consecutive closes below MA (adapted by volatility)
SLOPE_LOOKBACK = 5    # bars to compute SMA slope

# VIX-based signals
VIX_EXIT_BOOST = 25.0     # if VIX > this during MA breakdown, exit faster
VIX_FEAR_ENTRY = 30.0     # VIX above this = fear, look to buy on reversal
VIX_EXTREME = 35.0        # extreme fear — enter on any bullish candle
VIX_ENTRY_DECLINE = 3.0   # VIX must drop this much from peak to confirm fear peaking

# Re-entry signals
REENTRY_MA_RECLAIM = 2    # consecutive closes above SMA to confirm reclaim
RSI_OVERSOLD = 30         # RSI oversold level for bounce entry
CAPITULATION_BARS = 3     # consecutive bars of price decline + volume increase to trigger
CAPITULATION_VOL_MULT = 2.0  # final bar volume must be >= this * volume MA

# Risk management
TRAILING_STOP_ATR_MULT = 6.0   # trailing stop = peak - N * ATR (very wide)
REENTRY_COOLDOWN_BARS = 2      # min bars after exit before re-entry
MACD_REV_EXIT_COOLDOWN = 20    # bars to block ALL re-entries after a macd_reversal_exit
VIX_REGIME_THRESHOLD = 28.0    # VIX level that signals a sustained fear regime
VIX_REGIME_BARS = 3            # block ALL entries when this many consecutive bars have VIX >= threshold


# ── Data Fetching ────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "smart-hold/4.0"})
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


def calc_macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list, list]:
    """MACD(fast, slow, signal). Returns (macd_line, signal_line), values are None before warmup."""
    n = len(closes)
    fast_ema_vals = ema(closes, fast)
    slow_ema_vals = ema(closes, slow)

    macd_line: list[float | None] = [None] * n
    for i in range(slow - 1, n):
        if fast_ema_vals[i] is not None and slow_ema_vals[i] is not None:
            macd_line[i] = fast_ema_vals[i] - slow_ema_vals[i]

    # EMA of macd_line for signal — pad Nones with 0 then mask out early bars
    macd_fill = [v if v is not None else 0.0 for v in macd_line]
    signal_raw = ema(macd_fill, signal)
    signal_line: list[float | None] = [None] * n
    first_valid = slow - 1 + signal - 1  # first bar where signal is meaningful
    for i in range(first_valid, n):
        signal_line[i] = signal_raw[i]

    return macd_line, signal_line


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


# ── Strategy Engine ──────────────────────────────────────────────────

def run_smart_hold(
    candles: list[dict],
    vix_candles: list[dict] | None = None,
    params: dict | None = None,
) -> dict:
    p = params or {}
    fast_ma_period = p.get("fast_ma", FAST_MA)
    slow_ma_period = p.get("slow_ma", SLOW_MA)
    exit_ma_period = p.get("exit_ma", EXIT_MA)
    exit_confirm_base = p.get("exit_confirm_bars", EXIT_CONFIRM_BARS)
    slope_lb = p.get("slope_lookback", SLOPE_LOOKBACK)
    vix_exit_boost = p.get("vix_exit_boost", VIX_EXIT_BOOST)
    vix_fear = p.get("vix_fear_entry", VIX_FEAR_ENTRY)
    vix_extreme = p.get("vix_extreme", VIX_EXTREME)
    vix_decline = p.get("vix_entry_decline", VIX_ENTRY_DECLINE)
    reclaim_bars = p.get("reentry_ma_reclaim", REENTRY_MA_RECLAIM)
    trail_atr_mult = p.get("trailing_stop_atr_mult", TRAILING_STOP_ATR_MULT)
    cooldown = p.get("reentry_cooldown_bars", REENTRY_COOLDOWN_BARS)
    macd_rev_cooldown = p.get("macd_rev_exit_cooldown", MACD_REV_EXIT_COOLDOWN)
    vix_regime_threshold = p.get("vix_regime_threshold", VIX_REGIME_THRESHOLD)
    vix_regime_bars = p.get("vix_regime_bars", VIX_REGIME_BARS)
    commission = p.get("commission_pct", COMMISSION_PCT)
    slippage = p.get("slippage_pct", SLIPPAGE_PCT)
    initial_capital = p.get("initial_capital", INITIAL_CAPITAL)
    rsi_oversold = p.get("rsi_oversold", RSI_OVERSOLD)
    cap_bars = p.get("capitulation_bars", CAPITULATION_BARS)
    cap_vol_mult = p.get("capitulation_vol_mult", CAPITULATION_VOL_MULT)

    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    n = len(candles)

    # Compute indicators
    fast_ema_vals = ema(closes, fast_ma_period)
    slow_sma_vals = sma(closes, slow_ma_period)
    exit_sma_vals = sma(closes, exit_ma_period)
    rsi_vals = calc_rsi(closes, 14)
    vol_sma_vals = sma(volumes, 20)  # 20-bar volume MA for capitulation detection
    atr_vals = calc_atr(candles, 14)
    macd_line_vals, macd_signal_vals = calc_macd(closes, 12, 26, 9)

    # Compute ATR as % of price (rolling) for adaptive exit sensitivity
    atr_pct = [None] * n
    for i in range(n):
        if atr_vals[i] is not None and closes[i] > 0:
            atr_pct[i] = atr_vals[i] / closes[i] * 100

    # Compute historical volatility bucket (median ATR% over first 100 bars)
    warmup_atr_pcts = [a for a in atr_pct[:min(100, n)] if a is not None]
    if warmup_atr_pcts:
        median_atr_pct = sorted(warmup_atr_pcts)[len(warmup_atr_pcts) // 2]
    else:
        median_atr_pct = 1.5

    # Adaptive exit: volatile stocks need more bars to confirm breakdown
    # Low vol (<1.5% ATR): use base confirm bars, slope < 0
    # Med vol (1.5-3%): add 2 bars, slope < 0
    # High vol (>3%): add 4 bars, require stronger slope decline + EMA well below SMA
    # For high-vol stocks: require much more confirmation AND the 200 SMA to be declining
    # This prevents exiting during normal pullbacks in strong uptrends
    sma_200_vals = sma(closes, 200) if median_atr_pct > 3.0 else [None] * n

    if median_atr_pct > 3.0:
        vol_extra_bars = 5
        vol_label = "high"
        slope_threshold = -0.01  # SMA must decline 1%+ over lookback
        trail_atr_mult_adj = trail_atr_mult + 2  # wider trailing stop for volatile stocks
    elif median_atr_pct > 1.5:
        vol_extra_bars = 2
        vol_label = "medium"
        slope_threshold = 0.0
        trail_atr_mult_adj = trail_atr_mult
    else:
        vol_extra_bars = 0
        vol_label = "low"
        slope_threshold = 0.0
        trail_atr_mult_adj = trail_atr_mult
    exit_confirm = exit_confirm_base + vol_extra_bars

    # Build VIX lookup by date + rolling VIX peak
    vix_by_date: dict[str, float] = {}
    vix_peak_by_date: dict[str, float] = {}
    if vix_candles:
        vix_rolling_peak = 0.0
        for vc in vix_candles:
            v = vc["close"]
            vix_by_date[vc["date"]] = v
            vix_rolling_peak = max(vix_rolling_peak, v)
            vix_rolling_peak = max(v, vix_rolling_peak * 0.97)
            vix_peak_by_date[vc["date"]] = vix_rolling_peak

    # State — enter IMMEDIATELY on first bar (buy and hold style)
    warmup = slow_ma_period
    in_position = True
    entry_price = candles[0]["close"]
    entry_date = candles[0]["date"]
    entry_reason = "initial_entry"
    peak_price = entry_price
    bars_since_exit = 999
    bars_below_ma = 0
    macd_rev_cooldown_remaining = 0  # bars remaining before entries allowed after macd_reversal_exit
    vix_regime_count = 0             # rolling count of recent bars with VIX >= vix_regime_threshold

    trades: list[dict] = []
    capital = initial_capital
    cost_pct = commission + slippage

    exit_counts = {
        "ma_breakdown": 0,
        "vix_accelerated_exit": 0,
        "trailing_stop": 0,
        "profit_lock": 0,
        "macd_reversal_exit": 0,
        "end_of_data": 0,
    }

    # Import signal registry (support both direct execution and package import)
    try:
        from strategies.smart_hold.signals.registry import ENTRY_SIGNALS, EXIT_SIGNALS
    except ImportError:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from strategies.smart_hold.signals.registry import ENTRY_SIGNALS, EXIT_SIGNALS

    for i in range(1, n):
        c = candles[i]
        close = c["close"]
        date = c["date"]
        vix_val = vix_by_date.get(date)
        vix_peak = vix_peak_by_date.get(date)

        # Update VIX regime consecutive counter (strict: resets to 0 on any bar below threshold)
        # This distinguishes sustained bear regimes (many consecutive days above VIX threshold)
        # from brief spikes (1-2 days above then recovery), preventing false blocks on V-recoveries.
        if vix_val is not None and vix_val >= vix_regime_threshold:
            vix_regime_count += 1
        else:
            vix_regime_count = 0

        # Build context dict for signal evaluation
        in_chop = False
        if not in_position and median_atr_pct < 2.5:
            recent_exits = sum(1 for t in trades if t["exit_date"] >= candles[max(0, i - 30)]["date"])
            in_chop = recent_exits >= 2

        ctx = {
            "i": i, "n": n,
            "candle": c, "close": close,
            "closes": closes, "volumes": volumes, "candles": candles,
            "fast_ema": fast_ema_vals, "exit_sma": exit_sma_vals,
            "rsi": rsi_vals, "atr": atr_vals, "vol_sma": vol_sma_vals,
            "sma_200": sma_200_vals,
            "macd_line": macd_line_vals, "macd_signal": macd_signal_vals,
            "vix_val": vix_val, "vix_peak": vix_peak,
            "params": p, "warmup": warmup,
            "in_chop": in_chop, "median_atr_pct": median_atr_pct, "vol_label": vol_label,
            "trades": trades,
            "peak_price": peak_price, "bars_below_ma": bars_below_ma,
            "exit_confirm": exit_confirm, "slope_threshold": slope_threshold,
            "trail_atr_mult_adj": trail_atr_mult_adj, "slope_lb": slope_lb,
            "vix_exit_boost": vix_exit_boost,
            "entry_price": entry_price if in_position else None,
        }

        if not in_position:
            bars_since_exit += 1
            if bars_since_exit < cooldown:
                continue

            # Post-macd_reversal_exit architectural gate: block all entries for N bars
            if macd_rev_cooldown_remaining > 0:
                macd_rev_cooldown_remaining -= 1
                continue

            # VIX persistence regime gate: block trend-following re-entry signals when
            # VIX has been persistently elevated (sustained bear market / fear regime).
            # Only blocks non-VIX signals (ma_reclaim, rsi_oversold_bounce, ema_momentum,
            # macd_crossover) — VIX-specific signals are exempt since they are designed
            # for high-VIX environments. Avoids signal-hop by blocking at engine level.
            _VIX_REGIME_EXEMPT = frozenset({
                "vix_extreme_fear", "vix_fear_declining", "fast_reentry",
            })
            in_vix_regime = vix_regime_count >= vix_regime_bars

            # Evaluate entry signals (first match wins)
            for sig in ENTRY_SIGNALS:
                sig_name = sig.METADATA["name"]
                if in_vix_regime and sig_name not in _VIX_REGIME_EXEMPT:
                    continue
                if sig.check(ctx):
                    in_position = True
                    entry_price = close
                    entry_date = date
                    entry_reason = sig_name
                    peak_price = close
                    bars_below_ma = 0
                    break

        else:
            # Update peak
            if close > peak_price:
                peak_price = close

            # Update bars_below_ma counter (engine state, not signal logic)
            if exit_sma_vals[i] is not None:
                if close < exit_sma_vals[i]:
                    bars_below_ma += 1
                else:
                    bars_below_ma = 0
            ctx["bars_below_ma"] = bars_below_ma

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
                gross_ret = (close - entry_price) / entry_price * 100
                net_ret = gross_ret - cost_pct * 2
                capital *= (1 + net_ret / 100)

                trades.append({
                    "entry_date": entry_date,
                    "entry_price": round(entry_price, 2),
                    "exit_date": date,
                    "exit_price": round(close, 2),
                    "side": "long",
                    "entry_reason": entry_reason,
                    "exit_reason": exit_reason,
                    "return_pct": round(net_ret, 2),
                    "gross_return_pct": round(gross_ret, 2),
                    "cost_pct": round(-cost_pct * 2, 2),
                    "strategy": "smart_hold",
                })
                exit_counts[exit_reason] = exit_counts.get(exit_reason, 0) + 1

                in_position = False
                bars_since_exit = 0
                bars_below_ma = 0
                if exit_reason == "macd_reversal_exit":
                    macd_rev_cooldown_remaining = macd_rev_cooldown

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
        "strategy": "smart_hold",
        "strategy_label": f"Smart Hold v4 (Exit MA={exit_ma_period}, confirm={exit_confirm}[{vol_label} vol], VIX fear={vix_fear})",
        "parameters": {
            "fast_ma": fast_ma_period,
            "slow_ma": slow_ma_period,
            "exit_ma": exit_ma_period,
            "exit_confirm_bars_base": exit_confirm_base,
            "exit_confirm_bars_actual": exit_confirm,
            "volatility_class": vol_label,
            "median_atr_pct": round(median_atr_pct, 2),
            "slope_lookback": slope_lb,
            "vix_exit_boost": vix_exit_boost,
            "vix_fear_entry": vix_fear,
            "vix_extreme": vix_extreme,
            "trailing_stop_atr_mult": trail_atr_mult,
            "reentry_cooldown_bars": cooldown,
            "macd_rev_exit_cooldown": macd_rev_cooldown,
            "vix_regime_threshold": vix_regime_threshold,
            "vix_regime_bars": vix_regime_bars,
        },
        "period": p.get("period", PERIOD),
        "interval": p.get("interval", INTERVAL),
        "candles_analyzed": n,
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "initial_capital": initial_capital,
        "commission_pct": commission,
        "slippage_pct": slippage,
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
        "ma_breakdown_exits": exit_counts.get("ma_breakdown", 0),
        "vix_accelerated_exits": exit_counts.get("vix_accelerated_exit", 0),
        "trailing_stop_exits": exit_counts.get("trailing_stop", 0),
        "profit_lock_exits": exit_counts.get("profit_lock", 0),
        "macd_reversal_exits": exit_counts.get("macd_reversal_exit", 0),
        "end_of_data_exits": exit_counts.get("end_of_data", 0),
        "trade_log": trades,
        "overlays": [
            {"label": f"SMA({exit_ma_period})", "color": "#FF9800", "type": "line", "points": sma_overlay},
            {"label": f"EMA({fast_ma_period})", "color": "#2196F3", "type": "line", "points": ema_overlay},
            {"label": "RSI(14)", "color": "#E040FB", "type": "rsi_panel", "points": rsi_overlay},
        ],
        "data_source": "Yahoo Finance",
        "disclaimer": "Past performance does not guarantee future results. For educational use only.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Smart Buy & Hold Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["1h", "1d"], help="Candle size")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT)
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT)
    parser.add_argument("--exit-ma", type=int, default=EXIT_MA, help="Exit SMA period")
    parser.add_argument("--exit-confirm", type=int, default=EXIT_CONFIRM_BARS, help="Base bars below MA to confirm exit")
    parser.add_argument("--vix-fear", type=float, default=VIX_FEAR_ENTRY, help="VIX fear entry threshold")
    parser.add_argument("--vix-extreme", type=float, default=VIX_EXTREME, help="VIX extreme fear threshold")
    parser.add_argument("--trail-atr", type=float, default=TRAILING_STOP_ATR_MULT, help="ATR trailing stop multiplier")
    parser.add_argument("--cooldown", type=int, default=REENTRY_COOLDOWN_BARS, help="Bars to wait after exit")
    parser.add_argument("--macd-rev-cooldown", type=int, default=MACD_REV_EXIT_COOLDOWN, help="Bars to block all entries after macd_reversal_exit")
    parser.add_argument("--vix-regime-threshold", type=float, default=VIX_REGIME_THRESHOLD, help="VIX level marking a sustained fear regime (default: 25.0)")
    parser.add_argument("--vix-regime-bars", type=int, default=VIX_REGIME_BARS, help="Number of consecutive elevated-VIX bars to trigger regime gate (default: 5)")
    parser.add_argument("--chart", action="store_true", help="Generate interactive HTML chart")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Smart Buy & Hold Strategy v4 — {args.symbol}")
    print(f"  Exit MA: SMA({args.exit_ma})  |  Base Confirm: {args.exit_confirm} bars")
    print(f"  VIX fear: {args.vix_fear}  |  VIX extreme: {args.vix_extreme}")
    print(f"  ATR Trail: {args.trail_atr}x  |  Cooldown: {args.cooldown} bars")
    print(f"{'='*60}")
    print(f"\n  Fetching {args.symbol} data...")

    candles = fetch_ohlcv(args.symbol, args.period, args.interval)
    print(f"  Fetched {len(candles)} candles")

    print(f"  Fetching ^VIX data...")
    try:
        vix_candles = fetch_ohlcv("^VIX", args.period, args.interval)
        print(f"  Fetched {len(vix_candles)} VIX candles")
    except Exception as e:
        print(f"  Warning: Could not fetch VIX data ({e}), proceeding without VIX signals")
        vix_candles = None

    params = {
        "symbol": args.symbol,
        "period": args.period,
        "interval": args.interval,
        "initial_capital": args.initial_capital,
        "commission_pct": args.commission,
        "slippage_pct": args.slippage,
        "exit_ma": args.exit_ma,
        "exit_confirm_bars": args.exit_confirm,
        "vix_fear_entry": args.vix_fear,
        "vix_extreme": args.vix_extreme,
        "trailing_stop_atr_mult": args.trail_atr,
        "reentry_cooldown_bars": args.cooldown,
        "macd_rev_exit_cooldown": args.macd_rev_cooldown,
        "vix_regime_threshold": args.vix_regime_threshold,
        "vix_regime_bars": args.vix_regime_bars,
    }

    result = run_smart_hold(candles, vix_candles, params)

    print(f"\n  Volatility:       {result['parameters']['volatility_class']} (median ATR: {result['parameters']['median_atr_pct']}%)")
    print(f"  Exit Confirm:     {result['parameters']['exit_confirm_bars_actual']} bars (base {args.exit_confirm} + vol adjustment)")
    print(f"  Period:           {result['date_from']} -> {result['date_to']} ({result['candles_analyzed']} bars)")
    print(f"  Initial Capital:  ${result['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${result['final_capital']:,.2f}")
    print(f"  Total Return:     {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Time in Market:   {result['time_in_market_pct']}%")
    print(f"  Total Trades:     {result['total_trades']}")
    print(f"  Win Rate:         {result['win_rate_pct']}%")
    print(f"  Profit Factor:    {result['profit_factor']}")
    print(f"  Sharpe Ratio:     {result['sharpe_ratio']}")
    print(f"  Max Drawdown:     {result['max_drawdown_pct']}%")
    print(f"  Exits:            MA Break: {result['ma_breakdown_exits']}  |  VIX Accel: {result['vix_accelerated_exits']}  |  Trail Stop: {result['trailing_stop_exits']}  |  P-Lock: {result['profit_lock_exits']}  |  MACD-Rev: {result['macd_reversal_exits']}  |  EOD: {result['end_of_data_exits']}")
    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        print(f"    LONG  {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t['exit_reason']}] ({t['entry_reason']})")

    print(f"\n{'='*60}\n")

    script_dir = Path(__file__).resolve().parent
    # Exclude overlays from JSON (too large)
    json_result = {k: v for k, v in result.items() if k != "overlays"}
    fname = script_dir / f"smart_hold_backtest_{args.symbol.replace('-', '_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")

    # Save VIX data locally for reuse across strategies
    if vix_candles:
        vix_data_dir = script_dir.parent / "data"
        vix_data_dir.mkdir(exist_ok=True)
        vix_path = vix_data_dir / f"vix_{args.period}.json"
        with open(vix_path, "w") as f:
            json.dump(vix_candles, f, indent=2)
        print(f"  VIX data saved to: {vix_path}")

    if args.chart:
        # Import the shared visualizer
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html

        chart_path = script_dir / f"smart_hold_chart_{args.symbol.replace('-', '_')}_{args.period}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path, vix_candles=vix_candles)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
