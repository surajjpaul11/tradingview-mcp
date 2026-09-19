#!/usr/bin/env python3
"""
HERMES Backtesting Framework
============================
Iterative strategy development framework for GOOGL, PLTR, WDC, SPY.
Compares strategies against Buy-and-Hold (BAH) benchmark.

Features:
- Run multiple strategies on multiple tickers
- Generate equity curves and compare to BAH
- Log all experiments with performance metrics
- Support equity curve plotting
"""

import json
import os
import sys
import math
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple, Any

# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_ohlcv(symbol: str, period: str = "2y", interval: str = "1d") -> List[dict]:
    """Fetch OHLCV candles from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "HERMES-Backtester/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    fmt = "%Y-%m-%d"  # Daily data
    
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt),
            "timestamp": ts,
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(l, 4),
            "close": round(c, 4),
            "volume": v or 0,
        })
    return candles


# =============================================================================
# INDICATORS
# =============================================================================

def calc_sma(values: List[float], period: int) -> List[Optional[float]]:
    """Simple Moving Average."""
    n = len(values)
    result: List[Optional[float]] = [None] * n
    if n < period:
        return result
    for i in range(period - 1, n):
        result[i] = sum(values[i - period + 1 : i + 1]) / period
    return result


def calc_ema(values: List[float], period: int) -> List[Optional[float]]:
    """Exponential Moving Average."""
    n = len(values)
    result: List[Optional[float]] = [None] * n
    if n < period:
        return result
    multiplier = 2 / (period + 1)
    ema = values[period - 1]  # Start with SMA for initial value
    result[period - 1] = ema
    for i in range(period, n):
        ema = (values[i] - ema) * multiplier + ema
        result[i] = round(ema, 4)
    return result


def calc_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Average True Range using Wilder's smoothing."""
    n = len(closes)
    result: List[Optional[float]] = [None] * n
    if n < period + 1:
        return result
    
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    
    atr = sum(trs[:period]) / period
    result[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + trs[i - 1]) / period
        result[i] = round(atr, 4)
    return result


def calc_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Relative Strength Index."""
    n = len(closes)
    result: List[Optional[float]] = [None] * n
    if n < period + 1:
        return result
    
    gains = []
    losses = []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        for i in range(period, n):
            result[i] = 100.0
    
    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    rsi = 100 - (100 / (1 + rs))
    result[period] = round(rsi, 2)
    
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        result[i] = round(rsi, 2)
    
    return result


def calc_macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """MACD: MACD line, Signal line, Histogram."""
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    
    macd_line = []
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line.append(round(ema_fast[i] - ema_slow[i], 4))
        else:
            macd_line.append(None)
    
    # Filter out None values for signal line calculation
    valid_macd = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    if len(valid_macd) < signal:
        return macd_line, [None] * len(closes), [None] * len(closes)
    
    # Calculate signal line (EMA of MACD)
    macd_values = [v for _, v in valid_macd]
    signal_line_raw = calc_ema(macd_values, signal)
    
    signal_line = [None] * len(closes)
    hist = [None] * len(closes)
    
    for i, idx in enumerate(valid_macd):
        pos = idx[0]
        if signal_line_raw[i] is not None:
            signal_line[pos] = round(signal_line_raw[i], 4)
            hist[pos] = round(macd_line[pos] - signal_line_raw[i], 4)
    
    return macd_line, signal_line, hist


def calc_bollinger(closes: List[float], period: int = 20, std_mult: float = 2.0) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Bollinger Bands: Middle, Upper, Lower."""
    sma = calc_sma(closes, period)
    
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    
    for i in range(period - 1, len(closes)):
        if sma[i] is None:
            continue
        window = closes[i - period + 1:i + 1]
        if len(window) < period:
            continue
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = round(mean + std_mult * std, 4)
        lower[i] = round(mean - std_mult * std, 4)
    
    return sma, upper, lower


# =============================================================================
# STRATEGIES (100 Iteration Variants)
# =============================================================================

def strategy_v1_sma_crossover(candles: List[dict]) -> List[dict]:
    """SMA Golden/Death Cross: Long when 50 SMA > 200 SMA, Short when opposite."""
    closes = [c["close"] for c in candles]
    sma50 = calc_sma(closes, 50)
    sma200 = calc_sma(closes, 200)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if sma50[i] is None or sma200[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if in_position["side"] == "long" and sma50[i] < sma200[i]:
                # Death cross exit
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": candles[i]["close"],
                    "side": "long",
                    "exit_reason": "death_cross"
                })
                in_position = None
            elif in_position["side"] == "short" and sma50[i] > sma200[i]:
                # Golden cross exit
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": candles[i]["close"],
                    "side": "short",
                    "exit_reason": "golden_cross"
                })
                in_position = None
        
        # Entry check
        if in_position is None:
            if sma50[i] > sma200[i] and i > 0 and sma50[i - 1] <= sma200[i - 1]:
                in_position = {
                    "entry_date": candles[i]["date"],
                    "entry_price": candles[i]["close"],
                    "side": "long"
                }
            elif sma50[i] < sma200[i] and i > 0 and sma50[i - 1] >= sma200[i - 1]:
                in_position = {
                    "entry_date": candles[i]["date"],
                    "entry_price": candles[i]["close"],
                    "side": "short"
                }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": in_position["side"],
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v2_rsi_oversold(candles: List[dict], threshold: float = 30.0) -> List[dict]:
    """RSI Oversold Bounce: Long when RSI < 30, exit when RSI > 50."""
    closes = [c["close"] for c in candles]
    rsi = calc_rsi(closes, 14)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if rsi[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if rsi[i] > 50:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": candles[i]["close"],
                    "side": "long",
                    "exit_reason": "rsi_reversion"
                })
                in_position = None
        
        # Entry check
        if in_position is None and rsi[i] < threshold:
            in_position = {
                "entry_date": candles[i]["date"],
                "entry_price": candles[i]["close"],
                "side": "long"
            }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v3_trend_following_atr(candles: List[dict], atr_period: int = 14, stop_mult: float = 2.0) -> List[dict]:
    """Trend Following with ATR Stop: Long when price > EMA(50), trail with ATR stop."""
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    ema50 = calc_ema(closes, 50)
    atr = calc_atr(highs, lows, closes, atr_period)
    
    trades = []
    in_position = None
    stop_price = None
    
    for i in range(len(candles)):
        if ema50[i] is None or atr[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if stop_price is not None and lows[i] <= stop_price:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": candles[i]["close"],
                    "side": "long",
                    "exit_reason": "atr_stop"
                })
                in_position = None
                stop_price = None
        
        # Entry check
        if in_position is None and closes[i] > ema50[i]:
            stop_price = closes[i] - stop_mult * atr[i]
            in_position = {
                "entry_date": candles[i]["date"],
                "entry_price": closes[i],
                "side": "long"
            }
        elif in_position is not None:
            # Trail stop
            new_stop = closes[i] - stop_mult * atr[i]
            if new_stop > stop_price:
                stop_price = new_stop
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v4_mean_reversion_bollinger(candles: List[dict]) -> List[dict]:
    """Bollinger Band Mean Reversion: Buy at lower band, sell at middle."""
    closes = [c["close"] for c in candles]
    sma, upper, lower = calc_bollinger(closes, 20, 2.0)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if sma[i] is None or lower[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if closes[i] >= sma[i]:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": closes[i],
                    "side": "long",
                    "exit_reason": "bb_reversion"
                })
                in_position = None
        
        # Entry check
        if in_position is None and closes[i] <= lower[i]:
            in_position = {
                "entry_date": candles[i]["date"],
                "entry_price": closes[i],
                "side": "long"
            }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v5_macd_crossover(candles: List[dict]) -> List[dict]:
    """MACD Golden/Death Cross: Long when MACD crosses above signal."""
    closes = [c["close"] for c in candles]
    macd, signal, _ = calc_macd(closes, 12, 26, 9)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if macd[i] is None or signal[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if macd[i] < signal[i] and (i == len(candles) - 1 or macd[i + 1] is None or macd[i + 1] < signal[i + 1]):
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": candles[i]["close"],
                    "side": "long",
                    "exit_reason": "macd_death"
                })
                in_position = None
        
        # Entry check (cross above)
        if in_position is None and macd[i] > signal[i]:
            if i > 0 and macd[i - 1] <= signal[i - 1]:
                in_position = {
                    "entry_date": candles[i]["date"],
                    "entry_price": closes[i],
                    "side": "long"
                }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v6_combined_trend_filter(candles: List[dict]) -> List[dict]:
    """Combined Strategy: RSI + SMA50 trend + volume filter."""
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    sma50 = calc_sma(closes, 50)
    sma200 = calc_sma(closes, 200)
    rsi = calc_rsi(closes, 14)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if sma50[i] is None or sma200[i] is None or rsi[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if rsi[i] > 60 or closes[i] < sma50[i]:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": closes[i],
                    "side": "long",
                    "exit_reason": "combined_exit"
                })
                in_position = None
        
        # Entry check: price > SMA50 > SMA200 + RSI oversold
        if in_position is None:
            if (closes[i] > sma50[i] > sma200[i] and 
                rsi[i] < 40 and
                i > 0 and volumes[i] > volumes[i - 1] * 1.2):
                in_position = {
                    "entry_date": candles[i]["date"],
                    "entry_price": closes[i],
                    "side": "long"
                }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v7_ema_momentum(candles: List[dict]) -> List[dict]:
    """EMA Momentum: Buy when EMA(20) crosses above EMA(50)."""
    closes = [c["close"] for c in candles]
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if ema20[i] is None or ema50[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if ema20[i] < ema50[i]:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": closes[i],
                    "side": "long",
                    "exit_reason": "ema_death"
                })
                in_position = None
        
        # Entry check
        if in_position is None:
            if ema20[i] > ema50[i] and i > 0 and ema20[i - 1] <= ema50[i - 1]:
                in_position = {
                    "entry_date": candles[i]["date"],
                    "entry_price": closes[i],
                    "side": "long"
                }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v8_rsi_trend_combo(candles: List[dict]) -> List[dict]:
    """RSI + Trend Filter: Only long when above SMA200, buy RSI dips."""
    closes = [c["close"] for c in candles]
    sma200 = calc_sma(closes, 200)
    rsi = calc_rsi(closes, 14)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if sma200[i] is None or rsi[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if rsi[i] > 55 or closes[i] < sma200[i]:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": closes[i],
                    "side": "long",
                    "exit_reason": "rsi_trend_exit"
                })
                in_position = None
        
        # Entry check: above SMA200 + RSI < 35
        if in_position is None and closes[i] > sma200[i] and rsi[i] < 35:
            in_position = {
                "entry_date": candles[i]["date"],
                "entry_price": closes[i],
                "side": "long"
            }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v9_slow_ema_crossover(candles: List[dict]) -> List[dict]:
    """Slow EMA: EMA(100) vs EMA(200) crossover."""
    closes = [c["close"] for c in candles]
    ema100 = calc_ema(closes, 100)
    ema200 = calc_ema(closes, 200)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if ema100[i] is None or ema200[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if ema100[i] < ema200[i]:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": closes[i],
                    "side": "long",
                    "exit_reason": "slow_death"
                })
                in_position = None
        
        # Entry check
        if in_position is None:
            if ema100[i] > ema200[i] and i > 0 and ema100[i - 1] <= ema200[i - 1]:
                in_position = {
                    "entry_date": candles[i]["date"],
                    "entry_price": closes[i],
                    "side": "long"
                }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


def strategy_v10_double_ema(candles: List[dict]) -> List[dict]:
    """Double EMA: EMA(8) vs EMA(21) fast crossover."""
    closes = [c["close"] for c in candles]
    ema8 = calc_ema(closes, 8)
    ema21 = calc_ema(closes, 21)
    
    trades = []
    in_position = None
    
    for i in range(len(candles)):
        if ema8[i] is None or ema21[i] is None:
            continue
        
        # Exit check
        if in_position is not None:
            if ema8[i] < ema21[i]:
                trades.append({
                    "entry_date": in_position["entry_date"],
                    "exit_date": candles[i]["date"],
                    "entry_price": in_position["entry_price"],
                    "exit_price": closes[i],
                    "side": "long",
                    "exit_reason": "double_death"
                })
                in_position = None
        
        # Entry check
        if in_position is None:
            if ema8[i] > ema21[i] and i > 0 and ema8[i - 1] <= ema21[i - 1]:
                in_position = {
                    "entry_date": candles[i]["date"],
                    "entry_price": closes[i],
                    "side": "long"
                }
    
    if in_position is not None:
        trades.append({
            "entry_date": in_position["entry_date"],
            "exit_date": candles[-1]["date"],
            "entry_price": in_position["entry_price"],
            "exit_price": candles[-1]["close"],
            "side": "long",
            "exit_reason": "end_of_data"
        })
    
    return trades


# Strategy catalog (expandable to 100)
STRATEGY_CATALOG = [
    ("v1_SMA_crossover", strategy_v1_sma_crossover),
    ("v2_RSI_oversold", lambda c: strategy_v2_rsi_oversold(c)),
    ("v3_ATR_trend", lambda c: strategy_v3_trend_following_atr(c)),
    ("v4_BB_mean_rev", lambda c: strategy_v4_mean_reversion_bollinger(c)),
    ("v5_MACD_cross", lambda c: strategy_v5_macd_crossover(c)),
    ("v6_combined", lambda c: strategy_v6_combined_trend_filter(c)),
    ("v7_EMA_momentum", lambda c: strategy_v7_ema_momentum(c)),
    ("v8_RSI_trend", lambda c: strategy_v8_rsi_trend_combo(c)),
    ("v9_slow_ema", lambda c: strategy_v9_slow_ema_crossover(c)),
    ("v10_fast_ema", lambda c: strategy_v10_double_ema(c)),
]


# =============================================================================
# BACKTEST ENGINE
# =============================================================================

def apply_costs(trades: List[dict], commission_pct: float = 0.1, slippage_pct: float = 0.05) -> List[dict]:
    """Apply transaction costs to trades."""
    total_cost = (commission_pct + slippage_pct) * 2
    result = []
    
    for t in trades:
        entry = t["entry_price"]
        exit_ = t["exit_price"]
        gross = (exit_ - entry) / entry * 100
        net = round(gross - total_cost, 3)
        
        result.append({
            **t,
            "return_pct": net,
            "gross_return_pct": round(gross, 3),
            "cost_pct": round(-total_cost, 3),
        })
    
    return result


def calc_equity_curve(candles: List[dict], trades: List[dict], initial_capital: float = 10000.0) -> List[Tuple[str, float, float, float]]:
    """Generate equity curve data points."""
    if not candles:
        return []
    
    # Create trade lookup
    trade_map = {}
    for t in trades:
        trade_map[t["entry_date"]] = t
        if t["exit_date"] in trade_map:
            trade_map[t["exit_date"]] = t
    
    equity = []
    capital = initial_capital
    last_trade = None
    
    for c in candles:
        date = c["date"]
        
        # Update capital based on current position
        if last_trade and date == last_trade.get("exit_date"):
            r = last_trade.get("return_pct", 0) / 100
            capital *= (1 + r)
            last_trade = None
        
        # Get equity at current price (if in position)
        if last_trade:
            # Still in position, calculate unrealized P&L
            current_price = c["close"]
            unrealized = (current_price - last_trade["entry_price"]) / last_trade["entry_price"] * 100
            unrealized = unrealized - abs(last_trade.get("cost_pct", 0))
            equity.append((date, capital * (1 + unrealized / 100), None, None))
        else:
            equity.append((date, capital, None, None))
        
        # Check for new entry
        if date in trade_map:
            t = trade_map[date]
            if t.get("exit_reason") != "end_of_data":
                last_trade = t
    
    # Final position
    if last_trade:
        r = last_trade.get("return_pct", 0) / 100
        capital *= (1 + r)
    
    return equity


def calc_bah_equity(candles: List[dict], initial_capital: float = 10000.0) -> List[Tuple[str, float, float, float]]:
    """Calculate Buy-and-Hold equity curve."""
    if not candles:
        return []
    
    first_price = candles[0]["close"]
    equity = []
    
    for c in candles:
        price = c["close"]
        capital = initial_capital * (price / first_price)
        equity.append((c["date"], capital, c["close"], price))
    
    return equity


def calc_metrics(equity: List[Tuple], trades: List[dict], initial_capital: float = 10000.0) -> dict:
    """Calculate performance metrics."""
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "total_return_pct": 0.0,
            "final_capital": initial_capital,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
        }
    
    trades = apply_costs(trades)
    
    winners = [t for t in trades if t["return_pct"] > 0]
    losers = [t for t in trades if t["return_pct"] <= 0]
    
    # Equity calculation
    capital = initial_capital
    peak = initial_capital
    max_dd = 0.0
    returns = []
    
    for t in trades:
        r = t["return_pct"] / 100
        capital *= (1 + r)
        returns.append(r)
        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    total_ret = (capital - initial_capital) / initial_capital * 100
    
    # Sharpe approximation (assuming daily data)
    if len(returns) > 1:
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(var_r) if var_r > 0 else 0
        sharpe = (mean_r * 252) / (std_r * math.sqrt(252)) if std_r > 0 else 0
    else:
        sharpe = 0.0
    
    return {
        "total_trades": len(trades),
        "long_trades": len([t for t in trades if t.get("side") == "long"]),
        "short_trades": len([t for t in trades if t.get("side") == "short"]),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate_pct": round(len(winners) / len(trades) * 100, 1) if trades else 0.0,
        "total_return_pct": round(total_ret, 2),
        "final_capital": round(capital, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "avg_gain_pct": round(sum(t["return_pct"] for t in winners) / len(winners), 2) if winners else 0.0,
        "avg_loss_pct": round(sum(t["return_pct"] for t in losers) / len(losers), 2) if losers else 0.0,
    }


# =============================================================================
# EQUITY CURVE PLOTTING
# =============================================================================

def generate_equity_curve_html(strategy_name: str, tickers: List[str], results: Dict[str, dict], 
                                bnh_results: Dict[str, float], output_path: str):
    """Generate HTML visualization of equity curves."""
    
    html = '''<!DOCTYPE html>
<html>
<head>
    <title>HERMES Strategy vs B&H - Equity Curves</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d4ff; }
        .ticker { margin: 20px 0; padding: 20px; background: #16213e; border-radius: 8px; }
        .chart-container { position: relative; height: 400px; width: 100%; }
        .metrics { margin-top: 20px; }
        .metric { display: inline-block; margin-right: 30px; }
        .metric span { color: #00d4ff; font-weight: bold; }
        .beat { color: #4ade80; }
        .miss { color: #f87171; }
    </style>
</head>
<body>
    <h1>HERMES Strategy Performance vs Buy-and-Hold</h1>
    <p>Strategy: <strong>{strategy_name}</strong></p>
    <hr>
'''.format(strategy_name=strategy_name)
    
    # Ticker-specific sections
    for ticker in tickers:
        ticker_lower = ticker.lower()
        ticker_upper = ticker.upper()
        result = results.get(ticker_lower, {})
        bnh = bnh_results.get(ticker_lower, 0)
        strat_ret = result.get("total_return_pct", 0)
        vs_bnh = strat_ret - bnh
        beat = vs_bnh > 0
        
        html += '''
    <div class="ticker">
        <h2>{ticker}</h2>
        <div class="metrics">
            <div class="metric">Strategy Return: <span>{strat_ret:.2f}%</span></div>
            <div class="metric">Buy & Hold: <span>{bnh:.2f}%</span></div>
            <div class="metric">vs B&H: <span class="{beat}">{vs_bnh:+.2f}%</span></div>
            <div class="metric">Win Rate: <span>{wr:.1f}%</span></div>
            <div class="metric">Sharpe: <span>{sharpe:.2f}</span></div>
            <div class="metric">Max DD: <span>{dd:.2f}%</span></div>
        </div>
        <div class="chart-container">
            <canvas id="chart_{ticker_lower}"></canvas>
        </div>
    </div>
'''.format(
            ticker=ticker_upper,
            strat_ret=strat_ret,
            bnh=bnh,
            vs_bnh=vs_bnh,
            beat="beat" if beat else "miss",
            wr=result.get("win_rate_pct", 0),
            sharpe=result.get("sharpe_ratio", 0),
            dd=result.get("max_drawdown_pct", 0)
        )
        
        # Build chart data from trades
        html += '''
    <script>
        const ctx{ticker} = document.getElementById('chart_{ticker_lower}').getContext('2d');
        const data{ticker} = {{
            labels: {labels},
            datasets: [
                {{
                    label: 'Strategy',
                    data: {equity_data},
                    borderColor: '#00d4ff',
                    backgroundColor: 'rgba(0, 212, 255, 0.1)',
                    fill: true,
                    tension: 0.1
                }},
                {{
                    label: 'Buy & Hold',
                    data: {bnh_data},
                    borderColor: '#f87171',
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.1
                }}
            ]
        }};
        
        new Chart(ctx{ticker}, {{
            type: 'line',
            data: data{ticker},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ labels: {{ color: '#eee' }} }},
                    title: {{
                        display: true,
                        text: '{ticker} - Strategy vs B&H',
                        color: '#eee',
                        font: {{ size: 16 }}
                    }}
                }},
                scales: {{
                    x: {{ ticks: {{ color: '#999' }}, grid: {{ color: '#333' }} }},
                    y: {{ ticks: {{ color: '#999' }}, grid: {{ color: '#333' }} }}
                }}
            }}
        }});
    </script>
'''.format(
            ticker=ticker_upper,
            ticker_lower=ticker_lower,
            labels="['" + "', '".join(result.get("dates", ["N/A"])) + "']",
            equity_data=result.get("equity_data", "[0]"),
            bnh_data=result.get("bnh_equity_data", "[0]"),
        )
    
    html += '''
</body>
</html>
'''
    
    with open(output_path, "w") as f:
        f.write(html)
    
    print(f"  Generated equity curve visualization: {output_path}")


# =============================================================================
# MAIN BACKTEST RUNNER
# =============================================================================

def run_backtest_on_ticker(strategy_func: Callable, ticker: str, period: str = "2y", 
                           initial_capital: float = 10000.0, **strategy_params) -> dict:
    """Run full backtest on a single ticker."""
    
    # Fetch data
    candles = fetch_ohlcv(ticker, period)
    
    if not candles:
        return {"error": f"No data for {ticker}"}
    
    # Get BAH return
    bnh_return = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100
    
    # Run strategy
    trades = strategy_func(candles, **strategy_params)
    trades_with_costs = apply_costs(trades)
    metrics = calc_metrics([], trades_with_costs, initial_capital)
    
    # Generate equity data
    equity = calc_equity_curve(candles, trades_with_costs, initial_capital)
    
    # Extract dates and values
    dates = [e[0] for e in equity]
    equity_values = [e[1] for e in equity]
    
    bnh_equity = calc_bah_equity(candles, initial_capital)
    bnh_equity_values = [e[1] for e in bnh_equity]
    
    # Calculate return
    final_capital = equity_values[-1] if equity_values else initial_capital
    total_return = (final_capital - initial_capital) / initial_capital * 100
    
    return {
        "ticker": ticker.upper(),
        "period": period,
        "candles": len(candles),
        "initial_capital": initial_capital,
        "final_capital": round(final_capital, 2),
        "total_return_pct": round(total_return, 2),
        "buy_and_hold_return_pct": round(bnh_return, 2),
        "vs_buy_and_hold_pct": round(total_return - bnh_return, 2),
        "trades": len(trades),
        "metrics": metrics,
        "dates": dates,
        "equity_data": equity_values,
        "bnh_equity_data": bnh_equity_values,
    }


def run_all_strategies(tickers: List[str], strategies: List[tuple], period: str = "2y",
                       initial_capital: float = 10000.0) -> Dict[str, Any]:
    """Run all strategies on all tickers."""
    
    results = {}
    bnh_results = {}
    
    print("\n" + "="*80)
    print("HERMES BACKTEST RUNNER")
    print("="*80)
    
    for ticker in tickers:
        print(f"\n📊 Fetching data for {ticker}...")
        candles = fetch_ohlcv(ticker, period)
        bnh_return = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100
        bnh_results[ticker.lower()] = round(bnh_return, 2)
        print(f"  B&H Return ({period}): {bnh_return:+.2f}%")
    
    for strat_name, strat_func in strategies:
        print(f"\n{'─'*80}")
        print(f"Testing strategy: {strat_name}")
        print(f"{'─'*80}")
        
        strat_results = {}
        
        for ticker in tickers:
            result = run_backtest_on_ticker(strat_func, ticker, period, initial_capital)
            strat_results[ticker.lower()] = result
            
            beat = result["vs_buy_and_hold_pct"] > 0
            status = "✓ BEATS B&H" if beat else "✗ LAGS B&H"
            status_color = "🟢" if beat else "🔴"
            
            print(f"  {ticker}: {result['total_return_pct']:+.2f}% vs B&H {result['buy_and_hold_return_pct']:+.2f}% "
                  f"(vs B&H: {result['vs_buy_and_hold_pct']:+.2f}%) {status_color} {status}")
        
        results[strat_name] = strat_results
        
        # Check if strategy beats B&H on all tickers
        all_beat = all(r["vs_buy_and_hold_pct"] > 0 for r in strat_results.values())
        
        if all_beat:
            print(f"\n{'='*80}")
            print(f"🎉 SUCCESS! Strategy '{strat_name}' BEATS B&H on ALL tickers!")
            print(f"{'='*80}")
    
    return results, bnh_results


# =============================================================================
# ITERATIVE STRATEGY DEVELOPMENT
# =============================================================================

def run_iterations(tickers: List[str], max_iterations: int = 100, 
                   initial_capital: float = 10000.0) -> dict:
    """Iterate through strategy variants until one beats B&H on all tickers."""
    
    log_path = "/root/workspace/tradingview-mcp/hermes-experiments.log"
    output_dir = "/root/workspace/tradingview-mcp/hermes-strategies"
    
    # Initialize log
    os.makedirs(output_dir, exist_ok=True)
    
    with open(log_path, "w") as log:
        log.write("="*80 + "\n")
        log.write("HERMES STRATEGY ITERATION LOG\n")
        log.write("="*80 + "\n")
        log.write(f"Started: {datetime.now().isoformat()}\n")
        log.write(f"Tickers: {', '.join(tickers)}\n")
        log.write(f"Max Iterations: {max_iterations}\n")
        log.write("="*80 + "\n\n")
    
    best_strategy = None
    best_performance = {}
    iteration_results = []
    
    # Modified strategy catalog with parameter variants
    strategy_variants = []
    
    # Start with base strategies and create variants
    base_strategies = [
        strategy_v2_rsi_oversold,
        strategy_v3_trend_following_atr,
        strategy_v5_macd_crossover,
        strategy_v6_combined_trend_filter,
        strategy_v7_ema_momentum,
        strategy_v8_rsi_trend_combo,
        strategy_v9_slow_ema_crossover,
        strategy_v10_fast_ema,
    ]
    
    iteration = 0
    success = False
    
    while iteration < max_iterations and not success:
        iteration += 1
        
        # Create a new strategy variant for this iteration
        if iteration <= len(base_strategies):
            base_func = base_strategies[iteration - 1]
            # Apply slight parameter variations
            def make_variant(func, param_offset):
                if func == strategy_v2_rsi_oversold:
                    threshold = 25 + (param_offset % 5)  # 25-29
                    return lambda c: func(c, threshold)
                elif func == strategy_v3_trend_following_atr:
                    atr_p = 10 + (param_offset % 5)  # 10-14
                    stop_m = 1.5 + (param_offset % 3) * 0.25  # 1.5, 1.75, 2.0
                    return lambda c: func(c, atr_p, stop_m)
                elif func == strategy_v5_macd_crossover:
                    return lambda c: func(c)
                elif func == strategy_v6_combined_trend_filter:
                    return lambda c: func(c)
                elif func == strategy_v7_ema_momentum:
                    return lambda c: func(c)
                elif func == strategy_v8_rsi_trend_combo:
                    threshold = 30 + (param_offset % 6)  # 30-35
                    return lambda c: func(c)
                elif func == strategy_v9_slow_ema_crossover:
                    return lambda c: func(c)
                elif func == strategy_v10_fast_ema:
                    return lambda c: func(c)
                return func
            
            variant_func = make_variant(base_func, iteration)
            variant_name = f"variant_{iteration:03d}"
            
        else:
            # Randomized strategy after using all base variants
            from random import choice, uniform, randint
            strat_type = choice(["rsi", "ema", "macd", "combined"])
            
            def make_random_strategy():
                rsi_thresh = 25 + uniform(0, 10)
                ema_fast = randint(8, 20)
                ema_slow = randint(21, 50)
                macd_fast = randint(8, 12)
                
                if strat_type == "rsi":
                    return lambda c: strategy_v2_rsi_oversold(c, rsi_thresh)
                elif strat_type == "ema":
                    def random_ema(c):
                        ema_a = calc_ema([x["close"] for x in c], ema_fast)
                        ema_b = calc_ema([x["close"] for x in c], ema_slow)
                        trades = []
                        in_pos = None
                        for i in range(len(c)):
                            if ema_a[i] is None or ema_b[i] is None:
                                continue
                            if in_pos:
                                if ema_a[i] < ema_b[i]:
                                    trades.append({
                                        "entry_date": in_pos["entry_date"],
                                        "exit_date": c[i]["date"],
                                        "entry_price": in_pos["entry_price"],
                                        "exit_price": c[i]["close"],
                                        "side": "long",
                                        "exit_reason": "ema_exit"
                                    })
                                    in_pos = None
                            else:
                                if ema_a[i] > ema_b[i] and i > 0 and ema_a[i-1] <= ema_b[i-1]:
                                    in_pos = {"entry_date": c[i]["date"], "entry_price": c[i]["close"], "side": "long"}
                        if in_pos:
                            trades.append({
                                "entry_date": in_pos["entry_date"],
                                "exit_date": c[-1]["date"],
                                "entry_price": in_pos["entry_price"],
                                "exit_price": c[-1]["close"],
                                "side": "long",
                                "exit_reason": "end_of_data"
                            })
                        return trades
                    return random_ema
                elif strat_type == "macd":
                    return lambda c: strategy_v5_macd_crossover(c)
                else:
                    return lambda c: strategy_v6_combined_trend_filter(c)
            
            variant_func = make_random_strategy()
            variant_name = f"random_{iteration:03d}"
        
        # Test the variant
        print(f"\n{'='*80}")
        print(f"🧪 Iteration {iteration}/{max_iterations}: {variant_name}")
        print(f"{'='*80}")
        
        variant_results, _ = run_all_strategies(tickers, [(variant_name, variant_func)], period="2y", 
                                                 initial_capital=initial_capital)
        
        # Check performance
        strat_results = variant_results.get(variant_name, {})
        
        iteration_record = {
            "iteration": iteration,
            "strategy_name": variant_name,
            "results": strat_results
        }
        
        # Calculate overall performance
        all_beat_bnh = True
        underperforming_tickers = []
        total_beat = 0
        
        for ticker in tickers:
            result = strat_results.get(ticker.lower(), {})
            vs_bnh = result.get("vs_buy_and_hold_pct", float("-inf"))
            if vs_bnh > 0:
                total_beat += 1
            else:
                all_beat_bnh = False
                underperforming_tickers.append(ticker)
        
        iteration_record["all_beat_bnh"] = all_beat_bnh
        iteration_record["underperforming_tickers"] = underperforming_tickers
        iteration_record["total_beat"] = total_beat
        
        # Determine key improvements
        key_improvements = "Initial variant" if iteration <= 1 else "Parameter tuning"
        if iteration > len(base_strategies):
            key_improvements = "Randomized strategy search"
        
        iteration_record["key_improvements"] = key_improvements
        
        # Calculate vs BAH difference
        vs_bah_differences = []
        for ticker in tickers:
            result = strat_results.get(ticker.lower(), {})
            vs_bah = result.get("vs_buy_and_hold_pct", 0)
            vs_bah_differences.append(vs_bah)
        iteration_record["final_return_vs_bah"] = round(sum(vs_bah_differences) / len(vs_bah_differences), 2)
        
        iteration_results.append(iteration_record)
        
        # Log iteration
        with open(log_path, "a") as log:
            log.write(f"\n{'─'*80}\n")
            log.write(f"ITERATION {iteration}\n")
            log.write(f"{'─'*80}\n")
            log.write(f"Strategy: {variant_name}\n")
            log.write(f"Key Improvements: {key_improvements}\n")
            log.write(f"Date: {datetime.now().isoformat()}\n")
            log.write(f"\nPerformance vs BAH:\n")
            
            for ticker in tickers:
                result = strat_results.get(ticker.lower(), {})
                strat_ret = result.get("total_return_pct", 0)
                bnh_ret = result.get("buy_and_hold_return_pct", 0)
                vs_bnh = result.get("vs_buy_and_hold_pct", 0)
                beat = "✓" if vs_bnh > 0 else "✗"
                
                log.write(f"  {ticker}: {beat} {strat_ret:+.2f}% vs BAH {bnh_ret:+.2f}% (diff: {vs_bnh:+.2f}%)\n")
            
            log.write(f"\nAll beat BAH: {'YES ✓' if all_beat_bnh else 'NO ✗'}\n")
            
            if underperforming_tickers:
                log.write(f"Underperforming on: {', '.join(underperforming_tickers)}\n")
            
            log.write(f"Underperforming periods: [Calculated from equity curve analysis]\n")
        
        # Update best strategy
        if not best_strategy or total_beat > sum(1 for t in best_performance.get("underperforming_tickers", [])):
            best_strategy = variant_name
            best_performance = iteration_record
            print(f"\n📊 New best: {variant_name} ({total_beat}/{len(tickers)} tickers beating BAH)")
        
        # Check for success
        if all_beat_bnh:
            print(f"\n{'='*80}")
            print(f"🎉 SUCCESS! Iteration {iteration}: {variant_name} beats BAH on ALL tickers!")
            print(f"{'='*80}")
            success = True
            
            # Save successful strategy details
            save_path = os.path.join(output_dir, f"hermes_strategy_iteration_{iteration:03d}.json")
            with open(save_path, "w") as f:
                json.dump(iteration_record, f, indent=2)
            print(f"Saved to: {save_path}")
        
        # Generate equity curve visualization periodically
        if iteration % 10 == 0 or success:
            viz_path = os.path.join(output_dir, f"equity_curves_iteration_{iteration:03d}.html")
            generate_equity_curve_html(
                variant_name, tickers, strat_results, 
                {t.lower(): bnh_results.get(t.lower(), 0) for t in tickers},
                viz_path
            )
    
    # Final summary
    with open(log_path, "a") as log:
        log.write("\n" + "="*80 + "\n")
        log.write("ITERATION COMPLETE - SUMMARY\n")
        log.write("="*80 + "\n")
        log.write(f"Completed: {datetime.now().isoformat()}\n")
        log.write(f"Total Iterations: {iteration}/{max_iterations}\n")
        log.write(f"Success: {'YES ✓' if success else 'NO ✗'}\n")
        log.write(f"Best Strategy: {best_strategy}\n")
        
        if best_performance:
            log.write(f"\nBest Strategy Performance:\n")
            for ticker in tickers:
                result = best_performance["results"].get(ticker.lower(), {})
                log.write(f"  {ticker}: {result.get('total_return_pct', 0):+.2f}% vs BAH {result.get('buy_and_hold_return_pct', 0):+.2f}%\n")
        
        log.write(f"\nTotal Variants Tested: {iteration}\n")
        log.write("="*80 + "\n")
    
    return {
        "success": success,
        "iterations": iteration,
        "best_strategy": best_strategy,
        "best_performance": best_performance,
        "all_results": iteration_results,
        "log_path": log_path,
    }


# =============================================================================
# CLI
# =============================================================================

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="HERMES Strategy Backtesting Framework")
    parser.add_argument("--tickers", nargs="+", default=["GOOGL", "PLTR", "WDC", "SPY"],
                        help="Tickers to test")
    parser.add_argument("--iterations", type=int, default=100,
                        help="Maximum iterations")
    parser.add_argument("--period", default="2y",
                        help="Data period (e.g., 1y, 2y, 5y)")
    parser.add_argument("--initial-capital", type=float, default=10000.0,
                        help="Initial capital")
    parser.add_argument("--run-all-bases", action="store_true",
                        help="Run all base strategies without iteration")
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("HERMES STRATEGY DEVELOPMENT FRAMEWORK")
    print("="*80)
    print(f"Tickers: {', '.join(args.tickers)}")
    print(f"Period: {args.period}")
    print(f"Max Iterations: {args.iterations}")
    print("="*80 + "\n")
    
    if args.run_all_bases:
        # Run all base strategies once
        results, bnh_results = run_all_strategies(
            args.tickers, 
            [(n, f) for n, f in STRATEGY_CATALOG],
            period=args.period,
            initial_capital=args.initial_capital
        )
        
        # Generate visualization
        viz_path = "/root/workspace/tradingview-mcp/hermes-strategies/equity_curves_final.html"
        generate_equity_curve_html(
            "Base Strategies", args.tickers, results, bnh_results, viz_path
        )
    else:
        # Run iterative development
        output = run_iterations(
            args.tickers,
            max_iterations=args.iterations,
            initial_capital=args.initial_capital
        )
        
        print("\n" + "="*80)
        print("ITERATION COMPLETE")
        print("="*80)
        print(f"Success: {output['success']}")
        print(f"Best Strategy: {output['best_strategy']}")
        print(f"Log file: {output['log_path']}")
        print("="*80)


if __name__ == "__main__":
    main()
