# Volatility Harvester Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mean-reversion strategy for choppy/volatile markets that buys panic dips and shorts sharp rips, with a Kaufman ER regime gate to sit in cash during trends.

**Architecture:** Single standalone Python file following the project convention (pure stdlib + Yahoo Finance). Indicators (ATR, SMA, ER, Volume MA) computed upfront as arrays, then a single-pass engine loop checks regime gate, entries, and triple-layer exits. A separate comparison script runs across 23 symbols.

**Tech Stack:** Python 3.10+ stdlib only (no external dependencies). Yahoo Finance API for OHLCV data. argparse for CLI.

**Spec:** `docs/superpowers/specs/2026-03-30-volatility-harvester-design.md`

---

### Task 1: Create strategy file with parameters, data fetching, and indicators

**Files:**
- Create: `strategies/volatility_harvester_strategy.py`

This task builds the foundation: module docstring, parameter constants, `fetch_ohlcv()`, and all four indicator functions. No strategy logic yet.

- [ ] **Step 1: Create the file with docstring, imports, and parameter constants**

```python
"""
Volatility Harvester Strategy — Standalone Python Implementation
=================================================================

Mean-reversion strategy for choppy/volatile markets.

Buys panic dips (price far below mean) and shorts sharp rips (price far
above mean), betting that extreme moves in directionless markets snap back.
Uses a Kaufman Efficiency Ratio gate to sit in cash during trending markets.

Entry (B+C hybrid — ATR Z-Score + Volume Confirmation):
  Long:  SMA(20) - close >= 2.0 * ATR(14) AND volume >= 1.5 * vol_MA(20) AND ER < 0.25
  Short: close - SMA(20) >= 2.0 * ATR(14) AND volume >= 1.5 * vol_MA(20) AND ER < 0.25

Exit (triple layer — first to fire wins):
  1. Mean reversion: price returns to SMA(20)
  2. Time exit: held for 20 bars
  3. Stop loss: price moves 3 ATR against entry (ATR frozen at entry)

Usage:
  python volatility_harvester_strategy.py                              # defaults: SPY, 2y, 1h
  python volatility_harvester_strategy.py --symbol BTC-USD --period 1y
  python volatility_harvester_strategy.py --symbol VXX --no-volume-filter
  python volatility_harvester_strategy.py --symbol QQQ --long-only --deviation-mult 2.5

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

ATR_PERIOD       = 14       # ATR calculation period
SMA_PERIOD       = 20       # mean for deviation measurement + reversion target
DEVIATION_MULT   = 2.0      # ATR multiples from SMA to trigger entry
STOP_MULT        = 3.0      # ATR multiples for stop loss (from entry price)
MAX_HOLD_BARS    = 20       # time exit — max bars to hold a position
VOL_MA_PERIOD    = 20       # volume moving average period
VOL_SPIKE_MULT   = 1.5      # volume must be >= this * vol MA to confirm entry
ER_PERIOD        = 50       # Kaufman Efficiency Ratio lookback
ER_THRESHOLD     = 0.25     # below = choppy (trade), above = trending (cash)
VOLUME_FILTER    = True     # require volume confirmation for entries
LONG_ONLY        = False    # when True, disable short positions
INTERVAL         = "1h"     # candle size
PERIOD           = "2y"     # data lookback
INITIAL_CAPITAL  = 10_000.0
COMMISSION_PCT   = 0.1
SLIPPAGE_PCT     = 0.05
```

- [ ] **Step 2: Add `fetch_ohlcv()` function**

Copy the exact pattern from `buy_and_protect_strategy.py`, changing only the User-Agent string:

```python
# ==============================================================================
# DATA FETCHING
# ==============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1h") -> list[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "volatility-harvester/1.0"})
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
```

- [ ] **Step 3: Add indicator functions**

Four indicators needed. `calc_sma` and `calc_atr` follow the exact pattern from `buy_and_protect_strategy.py`. `calc_er` and `calc_volume_ma` are new.

```python
# ==============================================================================
# INDICATORS
# ==============================================================================

def calc_sma(values: list[float], period: int) -> list[Optional[float]]:
    """Simple Moving Average."""
    n = len(values)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    for i in range(period - 1, n):
        result[i] = sum(values[i - period + 1 : i + 1]) / period
    return result


def calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Optional[float]]:
    """Average True Range (Wilder's smoothing)."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period + 1:
        return result
    trs = []
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    result[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + trs[i - 1]) / period
        result[i] = atr
    return result


def calc_er(closes: list[float], period: int = 50) -> list[Optional[float]]:
    """
    Kaufman Efficiency Ratio.

    ER = |net change over period| / sum(|bar-to-bar changes| over period)
    Near 1.0 = strongly trending, near 0.0 = choppy/sideways.
    """
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period + 1:
        return result
    for i in range(period, n):
        net_change = abs(closes[i] - closes[i - period])
        sum_changes = sum(abs(closes[j] - closes[j - 1]) for j in range(i - period + 1, i + 1))
        result[i] = net_change / sum_changes if sum_changes > 0 else 0.0
    return result


def calc_volume_ma(volumes: list[float], period: int = 20) -> list[Optional[float]]:
    """Simple Moving Average of volume."""
    return calc_sma(volumes, period)
```

- [ ] **Step 4: Verify file parses without errors**

Run: `python3 -c "import strategies.volatility_harvester_strategy; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add strategies/volatility_harvester_strategy.py
git commit -m "feat(volatility-harvester): add parameters, data fetching, and indicators"
```

---

### Task 2: Implement the strategy engine

**Files:**
- Modify: `strategies/volatility_harvester_strategy.py`

The core `run_volatility_harvester()` function. Single pass through candles: check regime gate, check entries (ATR deviation + optional volume confirmation), check triple-layer exits.

- [ ] **Step 1: Add the `run_volatility_harvester()` function**

Add after the indicators section:

```python
# ==============================================================================
# STRATEGY ENGINE
# ==============================================================================

def run_volatility_harvester(
    candles: list[dict],
    atr_period: int = ATR_PERIOD,
    sma_period: int = SMA_PERIOD,
    deviation_mult: float = DEVIATION_MULT,
    stop_mult: float = STOP_MULT,
    max_hold_bars: int = MAX_HOLD_BARS,
    vol_ma_period: int = VOL_MA_PERIOD,
    vol_spike_mult: float = VOL_SPIKE_MULT,
    er_period: int = ER_PERIOD,
    er_threshold: float = ER_THRESHOLD,
    volume_filter: bool = VOLUME_FILTER,
    long_only: bool = LONG_ONLY,
) -> list[dict]:
    """
    Volatility Harvester — mean reversion in choppy markets.

    Buys panic dips and shorts sharp rips when ER indicates choppy regime.
    Exits via mean reversion, time limit, or stop loss (first to fire).

    Returns list of trade dicts.
    """
    if not candles:
        return []

    closes  = [c["close"]  for c in candles]
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    volumes = [float(c["volume"]) for c in candles]

    # --- Indicators ---
    sma    = calc_sma(closes, sma_period)
    atr    = calc_atr(highs, lows, closes, atr_period)
    er     = calc_er(closes, er_period)
    vol_ma = calc_volume_ma(volumes, vol_ma_period)

    # --- State ---
    trades: list[dict] = []
    position: dict | None = None
    regime_active_bars = 0

    for i in range(len(candles)):
        date  = candles[i]["date"]
        close = closes[i]

        # Track regime activity
        is_choppy = er[i] is not None and er[i] < er_threshold
        if is_choppy:
            regime_active_bars += 1

        # Skip bars where indicators aren't ready
        if sma[i] is None or atr[i] is None:
            continue

        # --- Check exits (before entries) ---
        if position is not None:
            exit_reason = None
            bars_held = i - position["entry_bar"]
            side = position["side"]

            # Exit 1: Mean reversion — price returned to SMA
            if side == "long" and close >= sma[i]:
                exit_reason = "mean_reversion"
            elif side == "short" and close <= sma[i]:
                exit_reason = "mean_reversion"

            # Exit 2: Time exit — held too long
            if exit_reason is None and bars_held >= max_hold_bars:
                exit_reason = "time_exit"

            # Exit 3: Stop loss — price moved against us by stop_mult * ATR
            if exit_reason is None:
                entry_atr = position["entry_atr"]
                if side == "long" and close <= position["entry_price"] - stop_mult * entry_atr:
                    exit_reason = "stop_loss"
                elif side == "short" and close >= position["entry_price"] + stop_mult * entry_atr:
                    exit_reason = "stop_loss"

            if exit_reason:
                ret_pct = ((close - position["entry_price"]) / position["entry_price"] * 100
                           if side == "long"
                           else (position["entry_price"] - close) / position["entry_price"] * 100)
                trades.append({
                    "entry_date":  position["entry_date"],
                    "entry_price": position["entry_price"],
                    "exit_date":   date,
                    "exit_price":  close,
                    "side":        side,
                    "exit_reason": exit_reason,
                    "bars_held":   bars_held,
                    "return_pct":  round(ret_pct, 3),
                })
                position = None

        # --- Check entries (only when flat and regime is choppy) ---
        if position is None and is_choppy:
            deviation = abs(close - sma[i])
            threshold = deviation_mult * atr[i]

            # Volume check (if enabled)
            vol_ok = True
            if volume_filter and vol_ma[i] is not None:
                vol_ok = volumes[i] >= vol_spike_mult * vol_ma[i]
            elif volume_filter and vol_ma[i] is None:
                vol_ok = False  # not enough data for volume MA yet

            if deviation >= threshold and vol_ok:
                # Determine direction
                if close < sma[i]:
                    # Price is below mean — panic dip — go long
                    position = {
                        "entry_date":  date,
                        "entry_price": close,
                        "entry_bar":   i,
                        "entry_atr":   atr[i],
                        "side":        "long",
                    }
                elif close > sma[i] and not long_only:
                    # Price is above mean — sharp rip — go short
                    position = {
                        "entry_date":  date,
                        "entry_price": close,
                        "entry_bar":   i,
                        "entry_atr":   atr[i],
                        "side":        "short",
                    }

    # Close any open position at end of data
    if position is not None:
        close = closes[-1]
        side = position["side"]
        bars_held = len(candles) - 1 - position["entry_bar"]
        ret_pct = ((close - position["entry_price"]) / position["entry_price"] * 100
                   if side == "long"
                   else (position["entry_price"] - close) / position["entry_price"] * 100)
        trades.append({
            "entry_date":  position["entry_date"],
            "entry_price": position["entry_price"],
            "exit_date":   candles[-1]["date"],
            "exit_price":  close,
            "side":        side,
            "exit_reason": "end_of_data",
            "bars_held":   bars_held,
            "return_pct":  round(ret_pct, 3),
        })

    # Attach regime info for metrics
    for t in trades:
        t["_regime_active_bars"] = regime_active_bars
        t["_total_bars"] = len(candles)

    return trades
```

- [ ] **Step 2: Verify file still parses**

Run: `python3 -c "import strategies.volatility_harvester_strategy; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add strategies/volatility_harvester_strategy.py
git commit -m "feat(volatility-harvester): implement strategy engine with regime gate and triple-layer exits"
```

---

### Task 3: Add cost application, metrics, and backtest pipeline

**Files:**
- Modify: `strategies/volatility_harvester_strategy.py`

Add `apply_costs()`, `calc_metrics()` (with exit breakdown + regime_active_pct), and `run_backtest()`.

- [ ] **Step 1: Add `apply_costs()` function**

Add after the strategy engine section:

```python
# ==============================================================================
# METRICS & REPORTING
# ==============================================================================

def apply_costs(trades: list[dict], commission_pct: float, slippage_pct: float) -> list[dict]:
    """Apply transaction costs to each trade."""
    total_cost = (commission_pct + slippage_pct) * 2  # entry + exit
    result = []
    for t in trades:
        side = t.get("side", "long")
        gross = ((t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100
                 if side == "long"
                 else (t["entry_price"] - t["exit_price"]) / t["entry_price"] * 100)
        net = round(gross - total_cost, 3)
        result.append({**t, "return_pct": net, "gross_return_pct": round(gross, 3), "cost_pct": round(-total_cost, 3)})
    return result
```

- [ ] **Step 2: Add `calc_metrics()` function**

```python
def calc_metrics(trades: list[dict], initial_capital: float, interval: str = "1h") -> dict:
    """Calculate backtest metrics including exit breakdown and regime activity."""
    if not trades:
        return {"total_trades": 0, "long_trades": 0, "short_trades": 0,
                "winning_trades": 0, "losing_trades": 0,
                "mean_reversion_exits": 0, "time_exits": 0,
                "stop_loss_exits": 0, "end_of_data_exits": 0,
                "regime_active_pct": 0,
                "win_rate_pct": 0, "total_return_pct": 0,
                "final_capital": initial_capital, "max_drawdown_pct": 0,
                "avg_gain_pct": 0, "avg_loss_pct": 0, "sharpe_ratio": 0,
                "profit_factor": 0, "expectancy_pct": 0}

    ann_map = {"5m": 252 * 78, "15m": 252 * 26, "30m": 252 * 13, "1h": 252 * 6, "1d": 252}
    ann = ann_map.get(interval, 252)

    winners = [t for t in trades if t["return_pct"] > 0]
    losers  = [t for t in trades if t["return_pct"] <= 0]

    capital = initial_capital
    peak_capital = capital
    max_dd  = 0.0
    returns = []
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        peak_capital = max(peak_capital, capital)
        max_dd = max(max_dd, (peak_capital - capital) / peak_capital * 100)

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

    # Regime activity (from metadata attached in engine)
    regime_active_bars = trades[0].get("_regime_active_bars", 0)
    total_bars = trades[0].get("_total_bars", 1)
    regime_pct = round(regime_active_bars / total_bars * 100, 1)

    return {
        "total_trades":          len(trades),
        "long_trades":           sum(1 for t in trades if t.get("side") == "long"),
        "short_trades":          sum(1 for t in trades if t.get("side") == "short"),
        "winning_trades":        len(winners),
        "losing_trades":         len(losers),
        "mean_reversion_exits":  sum(1 for t in trades if t.get("exit_reason") == "mean_reversion"),
        "time_exits":            sum(1 for t in trades if t.get("exit_reason") == "time_exit"),
        "stop_loss_exits":       sum(1 for t in trades if t.get("exit_reason") == "stop_loss"),
        "end_of_data_exits":     sum(1 for t in trades if t.get("exit_reason") == "end_of_data"),
        "regime_active_pct":     regime_pct,
        "win_rate_pct":          round(wr * 100, 1),
        "final_capital":         round(capital, 2),
        "total_return_pct":      round(total_ret, 2),
        "avg_gain_pct":          round(avg_gain, 2),
        "avg_loss_pct":          round(avg_loss, 2),
        "max_drawdown_pct":      round(-max_dd, 2),
        "profit_factor":         pf,
        "sharpe_ratio":          sharpe,
        "expectancy_pct":        round(wr * avg_gain + (1 - wr) * avg_loss, 2),
    }
```

- [ ] **Step 3: Add `run_backtest()` function**

```python
def run_backtest(
    symbol: str = "SPY",
    period: str = PERIOD,
    interval: str = INTERVAL,
    initial_capital: float = INITIAL_CAPITAL,
    commission_pct: float = COMMISSION_PCT,
    slippage_pct: float = SLIPPAGE_PCT,
    **strategy_params,
) -> dict:
    """Full backtest pipeline: fetch data -> run strategy -> compute metrics."""
    candles = fetch_ohlcv(symbol, period, interval)
    raw_trades = run_volatility_harvester(candles, **strategy_params)
    trades = apply_costs(raw_trades, commission_pct, slippage_pct)
    metrics = calc_metrics(trades, initial_capital, interval)

    bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)

    return {
        "symbol": symbol.upper(),
        "strategy": "volatility_harvester",
        "strategy_label": f"Volatility Harvester (Dev: {strategy_params.get('deviation_mult', DEVIATION_MULT)} ATR, "
                          f"Stop: {strategy_params.get('stop_mult', STOP_MULT)} ATR, "
                          f"ER < {strategy_params.get('er_threshold', ER_THRESHOLD)})",
        "parameters": {
            "atr_period": strategy_params.get("atr_period", ATR_PERIOD),
            "sma_period": strategy_params.get("sma_period", SMA_PERIOD),
            "deviation_mult": strategy_params.get("deviation_mult", DEVIATION_MULT),
            "stop_mult": strategy_params.get("stop_mult", STOP_MULT),
            "max_hold_bars": strategy_params.get("max_hold_bars", MAX_HOLD_BARS),
            "vol_ma_period": strategy_params.get("vol_ma_period", VOL_MA_PERIOD),
            "vol_spike_mult": strategy_params.get("vol_spike_mult", VOL_SPIKE_MULT),
            "er_period": strategy_params.get("er_period", ER_PERIOD),
            "er_threshold": strategy_params.get("er_threshold", ER_THRESHOLD),
            "volume_filter": strategy_params.get("volume_filter", VOLUME_FILTER),
            "long_only": strategy_params.get("long_only", LONG_ONLY),
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
```

- [ ] **Step 4: Verify file still parses**

Run: `python3 -c "import strategies.volatility_harvester_strategy; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add strategies/volatility_harvester_strategy.py
git commit -m "feat(volatility-harvester): add cost application, metrics, and backtest pipeline"
```

---

### Task 4: Add CLI entry point and console output

**Files:**
- Modify: `strategies/volatility_harvester_strategy.py`

Add the `main()` function with argparse (all 14 CLI flags from spec) and formatted console output matching project conventions.

- [ ] **Step 1: Add `main()` function**

Add at the bottom of the file:

```python
# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Volatility Harvester Strategy Backtester")
    parser.add_argument("--symbol", default="SPY", help="Yahoo Finance symbol (default: SPY)")
    parser.add_argument("--period", default=PERIOD, help="Data period (default: 2y)")
    parser.add_argument("--interval", default=INTERVAL, choices=["5m", "15m", "30m", "1h", "1d"],
                        help="Candle size (default: 1h)")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--commission", type=float, default=COMMISSION_PCT, help="Commission %% per trade")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% per trade")
    parser.add_argument("--atr-period", type=int, default=ATR_PERIOD, help="ATR period (default: 14)")
    parser.add_argument("--sma-period", type=int, default=SMA_PERIOD, help="SMA period for mean (default: 20)")
    parser.add_argument("--deviation-mult", type=float, default=DEVIATION_MULT,
                        help="ATR multiples from SMA to trigger entry (default: 2.0)")
    parser.add_argument("--stop-mult", type=float, default=STOP_MULT,
                        help="ATR multiples for stop loss (default: 3.0)")
    parser.add_argument("--max-hold-bars", type=int, default=MAX_HOLD_BARS,
                        help="Max bars to hold a position (default: 20)")
    parser.add_argument("--vol-ma-period", type=int, default=VOL_MA_PERIOD,
                        help="Volume MA period (default: 20)")
    parser.add_argument("--vol-spike-mult", type=float, default=VOL_SPIKE_MULT,
                        help="Volume spike multiplier (default: 1.5)")
    parser.add_argument("--er-period", type=int, default=ER_PERIOD, help="ER lookback (default: 50)")
    parser.add_argument("--er-threshold", type=float, default=ER_THRESHOLD,
                        help="ER threshold: below = choppy (default: 0.25)")
    parser.add_argument("--no-volume-filter", action="store_true",
                        help="Disable volume confirmation for entries")
    parser.add_argument("--long-only", action="store_true",
                        help="Disable short positions")
    args = parser.parse_args()

    vol_filter = not args.no_volume_filter
    vol_label = "ON" if vol_filter else "OFF"
    shorts_label = "OFF" if args.long_only else "ON"

    print(f"\n{'='*60}")
    print(f"  Volatility Harvester — {args.symbol}")
    print(f"  Entry: {args.deviation_mult} ATR  |  Stop: {args.stop_mult} ATR  |  Hold: {args.max_hold_bars} bars")
    print(f"  ER < {args.er_threshold}  |  Volume: {vol_label}  |  Shorts: {shorts_label}")
    print(f"  Interval: {args.interval}")
    print(f"{'='*60}\n")

    result = run_backtest(
        symbol=args.symbol, period=args.period, interval=args.interval,
        initial_capital=args.initial_capital,
        commission_pct=args.commission, slippage_pct=args.slippage,
        atr_period=args.atr_period, sma_period=args.sma_period,
        deviation_mult=args.deviation_mult, stop_mult=args.stop_mult,
        max_hold_bars=args.max_hold_bars,
        vol_ma_period=args.vol_ma_period, vol_spike_mult=args.vol_spike_mult,
        er_period=args.er_period, er_threshold=args.er_threshold,
        volume_filter=vol_filter, long_only=args.long_only,
    )

    m = result
    print(f"  Period:           {m['date_from']} -> {m['date_to']} ({m['candles_analyzed']} bars)")
    print(f"  Regime Active:    {m['regime_active_pct']}% of bars (ER < {args.er_threshold})")
    print(f"  Initial Capital:  ${m['initial_capital']:,.2f}")
    print(f"  Final Capital:    ${m['final_capital']:,.2f}")
    print(f"  Total Return:     {m['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:       {m['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:           {m['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:     {m['total_trades']} (L:{m['long_trades']} S:{m['short_trades']})")
    print(f"  Win Rate:         {m['win_rate_pct']}%")
    print(f"  Profit Factor:    {m['profit_factor']}")
    print(f"  Sharpe Ratio:     {m['sharpe_ratio']}")
    print(f"  Max Drawdown:     {m['max_drawdown_pct']}%")
    print(f"  Exits:            Reversion: {m['mean_reversion_exits']}  |  Time: {m['time_exits']}  |  Stop: {m['stop_loss_exits']}  |  EOD: {m['end_of_data_exits']}")

    print(f"\n  Trade Log:")
    for t in m["trade_log"]:
        side_label = "LONG " if t["side"] == "long" else "SHORT"
        print(f"    {side_label} {t['entry_date']} -> {t['exit_date']}  "
              f"${t['entry_price']:>10,.2f} -> ${t['exit_price']:>10,.2f}  "
              f"{t['return_pct']:+7.2f}%  [{t.get('exit_reason', 'n/a')}]")

    print(f"\n{'='*60}\n")

    fname = f"volatility_harvester_backtest_{args.symbol.replace('-','_')}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Full results saved to: {fname}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the full strategy on SPY**

Run: `python3 strategies/volatility_harvester_strategy.py --symbol SPY --period 2y`
Expected: Console output with header, metrics, trade log, and JSON file saved. Verify:
- Trades have both "long" and "short" sides (unless market is strongly bullish)
- Exit reasons include "mean_reversion", "time_exit", and/or "stop_loss"
- `regime_active_pct` is between 0-100%

- [ ] **Step 3: Test on BTC-USD (expected to be more active — choppy crypto)**

Run: `python3 strategies/volatility_harvester_strategy.py --symbol BTC-USD --period 2y`
Expected: More trades than SPY due to higher choppiness in crypto.

- [ ] **Step 4: Test long-only mode**

Run: `python3 strategies/volatility_harvester_strategy.py --symbol SPY --period 2y --long-only`
Expected: `S:0` in the output (no short trades).

- [ ] **Step 5: Test with volume filter disabled**

Run: `python3 strategies/volatility_harvester_strategy.py --symbol SPY --period 2y --no-volume-filter`
Expected: More trades than the default run (volume filter removes ~30-40% of signals).

- [ ] **Step 6: Commit**

```bash
git add strategies/volatility_harvester_strategy.py
git commit -m "feat(volatility-harvester): add CLI entry point with full console output"
```

---

### Task 5: Create comparison script and run full benchmark

**Files:**
- Create: `strategies/compare_volatility_harvester.py`

23-symbol comparison script following the exact pattern from `compare_straight_line.py`.

- [ ] **Step 1: Create the comparison script**

```python
"""Compare Volatility Harvester vs B&H across all tickers."""
import sys
sys.path.insert(0, ".")
from strategies.volatility_harvester_strategy import fetch_ohlcv, run_volatility_harvester, apply_costs, calc_metrics

SYMBOLS = [
    "SPY", "DIA", "QQQ",
    "BTC-USD", "GOOGL", "MSFT", "META", "PLTR", "SIL", "PAAS", "UUUU", "UEC",
    "VXX", "WDC", "STX", "BE", "MELI", "NVTS", "SMR", "KGC", "NVDA", "MU", "AAPL",
]
PERIOD = "2y"
INTERVAL = "1h"
COMMISSION = 0.1
SLIPPAGE = 0.05
CAPITAL = 10_000.0

print(f"\n{'='*115}")
print(f"  VOLATILITY HARVESTER vs BUY & HOLD — Dev: 2.0 ATR, Stop: 3.0 ATR, ER < 0.25, Vol: ON")
print(f"{'='*115}\n")

header = f"{'Symbol':<10} | {'VH Ret':>9} {'Trades':>7} {'WR':>6} {'PF':>6} {'DD':>8} {'Regime%':>8} | {'B&H':>9} | {'vs B&H':>8} | {'Exits (rev/time/stop/eod)'}"
print(header)
print("-" * 115)

totals_vh = []
totals_bnh = []
wins = 0

for sym in SYMBOLS:
    try:
        candles = fetch_ohlcv(sym, PERIOD, INTERVAL)
        bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
    except Exception as e:
        print(f"  {sym:<10} | SKIP: {e}")
        continue

    trades = run_volatility_harvester(candles)
    trades = apply_costs(trades, COMMISSION, SLIPPAGE)
    m = calc_metrics(trades, CAPITAL, INTERVAL)

    totals_vh.append(m["total_return_pct"])
    totals_bnh.append(bnh)
    vs = round(m["total_return_pct"] - bnh, 2)
    if m["total_return_pct"] >= bnh:
        wins += 1

    exits = f"{m['mean_reversion_exits']}/{m['time_exits']}/{m['stop_loss_exits']}/{m['end_of_data_exits']}"

    print(f"  {sym:<10} | {m['total_return_pct']:>+8.2f}% {m['total_trades']:>6}t {m['win_rate_pct']:>5.1f}% {m['profit_factor']:>5.2f} {m['max_drawdown_pct']:>7.2f}% {m['regime_active_pct']:>7.1f}% "
          f"| {bnh:>+8.2f}% | {vs:>+7.2f}% | {exits}")

print("-" * 115)
if totals_vh:
    avg_vh = sum(totals_vh) / len(totals_vh)
    avg_bnh = sum(totals_bnh) / len(totals_bnh)
    print(f"  {'AVERAGE':<10} | {avg_vh:>+8.2f}%{'':>50} | {avg_bnh:>+8.2f}% | {avg_vh - avg_bnh:>+7.2f}% |")
    print(f"  Beat B&H: {wins}/{len(totals_vh)} symbols")
print(f"{'='*115}\n")
```

- [ ] **Step 2: Run the comparison**

Run: `python3 strategies/compare_volatility_harvester.py`
Expected: Table output for all 23 symbols with returns, trade counts, win rates, exit breakdowns, and regime activity percentages. Note the results for the strategy_map.md and STRATEGIES.md updates.

- [ ] **Step 3: Commit**

```bash
git add strategies/compare_volatility_harvester.py
git commit -m "feat(volatility-harvester): add 23-symbol comparison script"
```

---

### Task 6: Update documentation

**Files:**
- Modify: `strategies/STRATEGIES.md` — add Volatility Harvester section
- Modify: `strategies/strategy_map.md` — update choppy/volatile scores
- Modify: `CLAUDE.md` — add Phase 1e, update strategy count to 11, update directory listing
- Modify: `README.md` — update strategy count to 11, add to fork additions and tools list

- [ ] **Step 1: Add Volatility Harvester section to `strategies/STRATEGIES.md`**

Add before the closing `---` at the end of the file:

```markdown
---

## Volatility Harvester Strategy

**Files:** `strategies/volatility_harvester_strategy.py` (Pine Script TBD)
**Type:** Mean reversion (choppy markets) | **Sides:** Long + Short (or long-only with `--long-only`) | **MCP key:** `volatility_harvester`

### How It Works

A counter-trend strategy designed specifically for choppy/volatile markets. Uses a Kaufman Efficiency Ratio gate to detect when the market is directionless, then buys panic dips and shorts sharp rips, betting on mean reversion.

**Regime Gate (Kaufman Efficiency Ratio):**
The ER measures how "efficient" price movement is. ER < 0.25 means lots of movement but no net direction (choppy) — the strategy only opens new positions in this regime. When ER >= 0.25 (trending), the strategy sits in cash.

**Entry (ATR Z-Score + Volume Confirmation):**
- Long: close is >= 2.0 ATR below SMA(20) AND volume >= 1.5x its MA (panic dip)
- Short: close is >= 2.0 ATR above SMA(20) AND volume >= 1.5x its MA (sharp rip)

**Exit (Triple Layer — first to fire wins):**
1. **Mean Reversion:** Price returns to SMA(20) — thesis complete
2. **Time Exit:** Position held for 20 bars — thesis expired
3. **Stop Loss:** Price moves 3 ATR against entry (ATR frozen at entry) — thesis wrong

### Default Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `atr_period` | 14 | ATR calculation period |
| `sma_period` | 20 | Mean for deviation + reversion target |
| `deviation_mult` | 2.0 | ATR multiples from SMA to trigger entry |
| `stop_mult` | 3.0 | ATR multiples for stop loss |
| `max_hold_bars` | 20 | Max bars to hold a position |
| `vol_ma_period` | 20 | Volume MA period |
| `vol_spike_mult` | 1.5 | Volume spike multiplier for confirmation |
| `er_period` | 50 | Efficiency Ratio lookback |
| `er_threshold` | 0.25 | Below = choppy (trade), above = trending (cash) |
| `volume_filter` | true | Require volume confirmation |
| `long_only` | false | Disable short positions |

### Usage

```bash
# Default (SPY, 2y, 1h, long+short)
python strategies/volatility_harvester_strategy.py

# Crypto (high choppiness expected)
python strategies/volatility_harvester_strategy.py --symbol BTC-USD --period 2y

# Long-only mode
python strategies/volatility_harvester_strategy.py --symbol QQQ --long-only

# Without volume filter (for thin-volume assets)
python strategies/volatility_harvester_strategy.py --symbol UUUU --no-volume-filter

# Wider entry threshold (fewer but higher-conviction trades)
python strategies/volatility_harvester_strategy.py --symbol VXX --deviation-mult 2.5
```
```

- [ ] **Step 2: Update `strategies/strategy_map.md`**

Update the Quick Reference scoring table — change Volatility Harvester's row (or add it if not present). The Choppy column should be 5, Bull Trend should be 1 (sits in cash), Sideways should be 3, Bear Trend should be 2, Transitions should be 3.

Also update the Choppy/volatile section in the flowchart to recommend Volatility Harvester as the primary option.

- [ ] **Step 3: Update `CLAUDE.md`**

Add Phase 1e section, update strategy count from 10 to 11, add files to directory listing, add row to strategy table, add run example.

- [ ] **Step 4: Update `README.md`**

Update "10 strategies" to "11 strategies" in the feature table, tools section, and strategy list. Add `volatility_harvester` to the strategy list with description.

- [ ] **Step 5: Commit all doc updates**

```bash
git add strategies/STRATEGIES.md strategies/strategy_map.md CLAUDE.md README.md
git commit -m "docs: add Volatility Harvester to all project documentation"
```
