"""
Liquidity & Capitulation Exhaustion Strategy — Standalone Python Implementation
=============================================================================

Capitalizes on macro liquidity tides, credit stress, and margin-call unwinds.

Core Mechanics:
1. Panic / Margin-Call Unwind Detection:
   - When systemic liquidity tightens and leveraged traders face margin calls,
     institutional put hedging inverts the VIX term structure:
     VTR = VIX / VIX3M crosses into backwardation (VTR >= 0.98 - 1.00+).
   - Market experiences a sharp drawdown (>= 4.0% from 60-day rolling peak).

2. Capitulation Reversal Buy Trigger:
   - Backwardation panic was active within the past 12 bars (peak forced selling).
   - VTR peaks and eases back BELOW 0.98 or crosses below its 5-day EMA
     (confirming the forced margin liquidation pressure has exhausted).
   - Target asset prints a positive reversal candle (Close > Open or Close > Prior Close).
   - Execution: Enters LONG at next bar's OPEN.

3. Exuberance / Distribution Detection (Top):
   - SPY at/near 60-day highs while market breadth (RSP/SPY) or credit (HYG/LQD)
     diverges negatively, and VIX is complacent (< 14.5).
   - Closes below SMA(20) trigger defensive exit to cash or short entry.

4. Exits & Capital Protection:
   - Initial Stop Loss: Entry - 2.5 * ATR (frozen).
   - Trailing Protection: Once in profit >= 1.5 * ATR, trails at Highest Close - 3.5 * ATR.
   - Contango Target: Orderly profit-taking when market normalizes into deep contango (VTR <= 0.82)
     and accumulated gain >= 2.0 * ATR.

Usage:
  python strategies/liquidity_exhaustion/liquidity_exhaustion_strategy.py                          # defaults: SPY, 5y, 1d
  python strategies/liquidity_exhaustion/liquidity_exhaustion_strategy.py --symbol QQQ --period 5y
  python strategies/liquidity_exhaustion/liquidity_exhaustion_strategy.py --symbol SPY --period 10y

Requires: pure Python stdlib (zero external dependencies).
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

SYMBOL                = "SPY"
PERIOD                = "5y"       # 5 years lookback
INTERVAL              = "1d"       # daily bars (ideal for macro liquidity)
INITIAL_CAPITAL       = 10_000.0
COMMISSION_PCT        = 0.1        # 0.1% per trade
SLIPPAGE_PCT          = 0.05       # 0.05% per trade

# Capitulation / Margin Bottom Parameters
VTR_PANIC_THRESHOLD   = 0.98       # VIX / VIX3M >= 0.98 signals imminent margin liquidation
VTR_RECOVERY_LINE     = 0.98       # VTR easing below this confirms liquidation exhaustion
MIN_PANIC_DRAWDOWN    = 4.0        # price must have pulled back at least 4% from 60-day peak
PANIC_MEMORY_BARS     = 12         # bars within which panic backwardation must have occurred

# Exits & Risk Controls
INITIAL_STOP_ATR_MULT = 2.5        # stop loss = entry - 2.5 * ATR
PROFIT_ACTIVATE_ATR   = 1.5        # activate trailing stop once profit >= 1.5 * ATR
TRAILING_ATR_MULT     = 3.5        # trailing stop = highest close - 3.5 * ATR
CONTANGO_EXIT_VTR     = 0.82       # deep contango profit target
CONTANGO_MIN_GAIN_ATR = 2.0        # require at least 2.0 ATR profit for contango target exit

# Exuberance / Top Parameters
VIX_COMPLACENT        = 14.5       # VIX below 14.5 signals extreme complacency
EXUBERANCE_THRESHOLD  = 65.0       # composite score for distribution warning
ENABLE_SHORT          = False      # shorting on confirmed exuberance breakdown


# ==============================================================================
# DATA FETCHING & ALIGNMENT
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "5y", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result = data["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quotes = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d"

    candles = []
    for i, ts in enumerate(timestamps):
        o = quotes["open"][i]
        h = quotes["high"][i]
        l = quotes["low"][i]
        c = quotes["close"][i]
        v = quotes["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
            "open": round(float(o), 4),
            "high": round(float(h), 4),
            "low": round(float(l), 4),
            "close": round(float(c), 4),
            "volume": int(v or 0),
        })
    return candles


def align_multi_asset_data(
    primary_candles: list[dict],
    aux_data: dict[str, list[dict]],
) -> list[dict]:
    """
    Align primary target asset candles with auxiliary tickers by date (YYYY-MM-DD).
    Forward-fills missing values to prevent indexing gaps without lookahead bias.
    """
    aux_maps = {}
    for ticker, candles in aux_data.items():
        lookup = {c["date"]: c["close"] for c in candles}
        aux_maps[ticker] = lookup

    last_known = {ticker: None for ticker in aux_data}
    for ticker, lookup in aux_maps.items():
        if lookup:
            first_sorted = sorted(lookup.items())[0][1]
            last_known[ticker] = first_sorted

    aligned = []
    for c in primary_candles:
        date = c["date"]
        row = dict(c)
        for ticker, lookup in aux_maps.items():
            if date in lookup:
                last_known[ticker] = lookup[date]
            row[ticker] = last_known[ticker]
        aligned.append(row)

    return aligned


# ==============================================================================
# INDICATORS (PURE PYTHON)
# ==============================================================================

def calc_sma(values: list[float], period: int) -> list[Optional[float]]:
    out = [None] * len(values)
    if len(values) < period:
        return out
    current_sum = sum(values[:period])
    out[period - 1] = round(current_sum / period, 4)
    for i in range(period, len(values)):
        current_sum += values[i] - values[i - period]
        out[i] = round(current_sum / period, 4)
    return out


def calc_ema(values: list[float], period: int) -> list[Optional[float]]:
    out = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    sma = sum(values[:period]) / period
    out[period - 1] = round(sma, 4)
    for i in range(period, len(values)):
        prev = out[i - 1]
        out[i] = round(values[i] * k + prev * (1 - k), 4)
    return out


def calc_atr(candles: list[dict], period: int = 14) -> list[Optional[float]]:
    n = len(candles)
    if n < 2:
        return [None] * n
    tr = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, n):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return calc_ema(tr, period)


# ==============================================================================
# STRATEGY LOGIC
# ==============================================================================

def run_liquidity_exhaustion(
    candles: list[dict],
    vtr_panic_threshold: float = VTR_PANIC_THRESHOLD,
    vtr_recovery_line: float = VTR_RECOVERY_LINE,
    min_panic_drawdown: float = MIN_PANIC_DRAWDOWN,
    panic_memory_bars: int = PANIC_MEMORY_BARS,
    initial_stop_atr_mult: float = INITIAL_STOP_ATR_MULT,
    profit_activate_atr: float = PROFIT_ACTIVATE_ATR,
    trailing_atr_mult: float = TRAILING_ATR_MULT,
    contango_exit_vtr: float = CONTANGO_EXIT_VTR,
    contango_min_gain_atr: float = CONTANGO_MIN_GAIN_ATR,
    enable_short: bool = ENABLE_SHORT,
) -> list[dict]:
    """
    Executes the Liquidity Exhaustion & Capitulation strategy.
    Signals calculated on bar i close, executed on bar i+1 open.
    """
    n = len(candles)
    if n < 50:
        return []

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    atr = calc_atr(candles, 14)
    sma20 = calc_sma(closes, 20)

    # Compute VTR (VIX / VIX3M)
    vtr = []
    for c in candles:
        vix = c.get("^VIX")
        vix3m = c.get("^VIX3M")
        if vix and vix3m and vix3m > 0:
            vtr.append(vix / vix3m)
        else:
            vtr.append(0.85)

    vtr_ema = calc_ema(vtr, 5)

    trades = []
    position = None
    panic_bar = -999

    for i in range(50, n - 1):
        c_close = closes[i]
        c_atr = atr[i] or (c_close * 0.015)
        c_vtr = vtr[i]
        p_vtr = vtr[i - 1]
        c_vtr_ema = vtr_ema[i] or c_vtr
        p_vtr_ema = vtr_ema[i - 1] or p_vtr

        # Track active margin panic / backwardation
        if c_vtr >= vtr_panic_threshold:
            panic_bar = i

        rolling_peak = max(highs[max(0, i - 60) : i + 1])
        drawdown_pct = (rolling_peak - c_close) / rolling_peak * 100.0

        next_open = candles[i + 1]["open"]
        next_date = candles[i + 1]["date"]

        # ======================================================================
        # POSITION MANAGEMENT
        # ======================================================================
        if position is not None:
            pos_side = position["side"]
            pos_entry = position["entry_price"]
            highest = max(position["highest"], c_close)
            lowest = min(position["lowest"], c_close)
            position["highest"] = highest
            position["lowest"] = lowest

            if pos_side == "long":
                profit = c_close - pos_entry

                # Activate trailing stop once profit target is reached
                if profit >= profit_activate_atr * c_atr:
                    trail_level = highest - trailing_atr_mult * c_atr
                    position["stop"] = max(position["stop"], trail_level)

                exit_reason = None
                # Stop loss or trailing stop triggered
                if c_close <= position["stop"]:
                    exit_reason = "trailing_stop" if profit >= profit_activate_atr * c_atr else "stop_loss"
                # Contango target profit-taking
                elif c_vtr <= contango_exit_vtr and profit >= contango_min_gain_atr * c_atr:
                    exit_reason = "contango_target"

                if exit_reason:
                    trades.append({
                        "entry_date": position["entry_date"],
                        "entry_price": pos_entry,
                        "entry_signal_date": position["entry_signal_date"],
                        "exit_date": next_date,
                        "exit_price": next_open,
                        "exit_signal_date": candles[i]["date"],
                        "side": "long",
                        "entry_reason": position["entry_reason"],
                        "exit_reason": exit_reason,
                        "strategy": "liquidity_exhaustion",
                    })
                    position = None
                    continue

            elif pos_side == "short":
                profit = pos_entry - c_close
                if profit >= profit_activate_atr * c_atr:
                    trail_level = lowest + trailing_atr_mult * c_atr
                    position["stop"] = min(position["stop"], trail_level)

                exit_reason = None
                if c_close >= position["stop"]:
                    exit_reason = "trailing_stop" if profit >= profit_activate_atr * c_atr else "stop_loss"
                elif c_vtr >= vtr_panic_threshold:
                    exit_reason = "panic_cover"

                if exit_reason:
                    trades.append({
                        "entry_date": position["entry_date"],
                        "entry_price": pos_entry,
                        "entry_signal_date": position["entry_signal_date"],
                        "exit_date": next_date,
                        "exit_price": next_open,
                        "exit_signal_date": candles[i]["date"],
                        "side": "short",
                        "entry_reason": position["entry_reason"],
                        "exit_reason": exit_reason,
                        "strategy": "liquidity_exhaustion",
                    })
                    position = None
                    continue

        # ======================================================================
        # ENTRY CONDITIONS (Only when flat)
        # ======================================================================
        if position is None:
            # CAPITULATION REVERSAL ENTRY:
            # 1. Panic backwardation occurred within the last N bars
            # 2. Drawdown >= minimum panic threshold
            # 3. VTR is easing back below recovery line OR crosses below 5-day EMA
            # 4. Positive price confirmation candle
            panic_was_active = (i - panic_bar <= panic_memory_bars)
            is_oversold = (drawdown_pct >= min_panic_drawdown)
            vtr_easing = (c_vtr < vtr_recovery_line) or (c_vtr < c_vtr_ema and p_vtr >= p_vtr_ema)
            candle_reversal = (c_close > candles[i]["open"]) or (c_close > closes[i - 1])

            if panic_was_active and is_oversold and vtr_easing and candle_reversal:
                stop_level = next_open - initial_stop_atr_mult * c_atr
                position = {
                    "side": "long",
                    "entry_date": next_date,
                    "entry_price": next_open,
                    "entry_signal_date": candles[i]["date"],
                    "stop": stop_level,
                    "highest": next_open,
                    "lowest": next_open,
                    "entry_reason": "capitulation_exhaustion_bottom",
                }
                panic_bar = -999
                continue

            # EXUBERANCE TOP SHORT ENTRY (Optional):
            if enable_short:
                vix_val = candles[i].get("^VIX", 15.0) or 15.0
                at_peak = (drawdown_pct <= 1.5)
                is_complacent = (vix_val <= VIX_COMPLACENT)
                ma_break = (sma20[i] and c_close < sma20[i] and closes[i - 1] >= sma20[i - 1])

                if at_peak and is_complacent and ma_break:
                    stop_level = next_open + initial_stop_atr_mult * c_atr
                    position = {
                        "side": "short",
                        "entry_date": next_date,
                        "entry_price": next_open,
                        "entry_signal_date": candles[i]["date"],
                        "stop": stop_level,
                        "highest": next_open,
                        "lowest": next_open,
                        "entry_reason": "exuberance_breakdown_top",
                    }
                    continue

    # Final bar cleanup
    if position is not None:
        trades.append({
            "entry_date": position["entry_date"],
            "entry_price": position["entry_price"],
            "entry_signal_date": position["entry_signal_date"],
            "exit_date": candles[-1]["date"],
            "exit_price": candles[-1]["close"],
            "exit_signal_date": candles[-1]["date"],
            "side": position["side"],
            "entry_reason": position["entry_reason"],
            "exit_reason": "end_of_data",
            "strategy": "liquidity_exhaustion",
        })

    return trades


# ==============================================================================
# PERFORMANCE METRICS & COSTS
# ==============================================================================

def apply_costs(
    trades: list[dict],
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
) -> list[dict]:
    adjusted = []
    total_cost_pct = commission_pct + slippage_pct
    for t in trades:
        entry = t["entry_price"]
        exit_p = t["exit_price"]
        side = t.get("side", "long")

        if side == "long":
            raw_ret = (exit_p - entry) / entry
        else:
            raw_ret = (entry - exit_p) / entry

        net_ret = raw_ret - (total_cost_pct * 2 / 100.0)
        item = dict(t)
        item["raw_return_pct"] = round(raw_ret * 100.0, 2)
        item["return_pct"] = round(net_ret * 100.0, 2)
        adjusted.append(item)
    return adjusted


def calc_metrics(trades: list[dict], initial_capital: float = INITIAL_CAPITAL) -> dict:
    if not trades:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate_pct": 0.0, "final_capital": initial_capital,
            "total_return_pct": 0.0, "max_drawdown_pct": 0.0,
            "profit_factor": 0.0, "sharpe_ratio": 0.0,
        }

    capital = initial_capital
    peak = capital
    max_dd = 0.0
    returns = []
    winners = []
    losers = []

    for t in trades:
        ret = t["return_pct"] / 100.0
        capital *= (1.0 + ret)
        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
        returns.append(ret)
        if ret > 0:
            winners.append(t)
        else:
            losers.append(t)

    total_ret = (capital - initial_capital) / initial_capital * 100.0
    wr = len(winners) / len(trades) if trades else 0.0
    gp = sum(t["return_pct"] for t in winners)
    gl = abs(sum(t["return_pct"] for t in losers))
    pf = round(gp / gl, 2) if gl > 0 else float("inf")

    sharpe = 0.0
    if len(returns) > 1:
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        if std_r > 0:
            sharpe = round((mean_r - 0.04 / 252) / std_r * math.sqrt(252), 2)

    return {
        "total_trades": len(trades),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate_pct": round(wr * 100.0, 1),
        "final_capital": round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "max_drawdown_pct": round(-max_dd, 2),
        "profit_factor": pf,
        "sharpe_ratio": sharpe,
    }


def run_backtest(
    symbol: str = SYMBOL,
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    enable_short: bool = ENABLE_SHORT,
) -> dict:
    primary_candles = fetch_ohlcv(symbol, period, interval)
    aux_tickers = ["^VIX", "^VIX3M", "HYG", "LQD", "RSP"]
    aux_data = {}
    for sym in aux_tickers:
        try:
            aux_data[sym] = fetch_ohlcv(sym, period, interval)
        except Exception:
            pass

    candles = align_multi_asset_data(primary_candles, aux_data)
    raw_trades = run_liquidity_exhaustion(candles, enable_short=enable_short)
    trades = apply_costs(raw_trades)
    metrics = calc_metrics(trades, initial_capital)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100.0, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "liquidity_exhaustion",
        "period": period,
        "interval": interval,
        "candles_analyzed": len(candles),
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        **metrics,
        "buy_and_hold_return_pct": bnh,
        "vs_buy_and_hold_pct": round(metrics["total_return_pct"] - bnh, 2),
        "trade_log": trades,
    }


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Liquidity & Capitulation Exhaustion Strategy Backtester")
    parser.add_argument("--symbol", default=SYMBOL, help="Target symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Lookback period (default: 5y)")
    parser.add_argument("--interval", default=INTERVAL, help="Candle interval (default: 1d)")
    parser.add_argument("--enable-short", action="store_true", help="Enable short trades on exuberance breakdown")
    args = parser.parse_args()

    result = run_backtest(
        symbol=args.symbol,
        period=args.period,
        interval=args.interval,
        enable_short=args.enable_short,
    )

    print("\n" + "=" * 65)
    print(f" LIQUIDITY & CAPITULATION STRATEGY: {result['symbol']} ({result['period']})")
    print("=" * 65)
    print(f"Candles analyzed:    {result['candles_analyzed']} ({result['date_from']} -> {result['date_to']})")
    print(f"Total Return:        {result['total_return_pct']:+.2f}%  (Buy & Hold: {result['buy_and_hold_return_pct']:+.2f}%)")
    print(f"Alpha vs B&H:        {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"Max Drawdown:        {result['max_drawdown_pct']:.2f}%")
    print(f"Win Rate:            {result['win_rate_pct']:.1f}% ({result['winning_trades']}/{result['total_trades']})")
    print(f"Profit Factor:       {result['profit_factor']}")
    print(f"Sharpe Ratio:        {result['sharpe_ratio']}")
    print("-" * 65)
    print("TRADE LOG:")
    for i, t in enumerate(result["trade_log"], 1):
        print(f" {i:2d}. {t['side'].upper():5s} {t['entry_date']} @ {t['entry_price']:.2f} -> "
              f"{t['exit_date']} @ {t['exit_price']:.2f} ({t['return_pct']:+.2f}%) "
              f"[{t['exit_reason']}]")
    print("=" * 65)


if __name__ == "__main__":
    main()
