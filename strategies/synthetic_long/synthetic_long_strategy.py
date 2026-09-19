"""
Synthetic Long Strategy
========================
Leveraged bullish strategy using options when VIX fear is elevated.

Two legs:
  1. BUY deep ITM LEAPS calls (delta ~0.85) — stock-like upside, less capital
  2. SELL far OTM puts (~25% below price, ~1yr out) — collect premium from high IV

Entry trigger: VIX >= 28 (fear elevated → fat premiums)
Exit: Calls closed when VIX normalizes + profit target hit, puts expire or bought back cheap

Uses Black-Scholes for options pricing (no historical options data available).
Approximation — real spreads, skew, and early exercise are not modeled.

Usage:
    python3 strategies/synthetic_long/synthetic_long_strategy.py --symbol SPY --period 5y
    python3 strategies/synthetic_long/synthetic_long_strategy.py --symbol QQQ --period 2y --vix-entry 25
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

# VIX thresholds
VIX_ENTRY      = 28    # Enter when VIX >= this (fear is high)
VIX_EXIT       = 20    # Close calls when VIX drops below this (calm)
VIX_EXTREME    = 35    # Double down — add second call position

# Call leg: deep ITM LEAPS
CALL_DELTA     = 0.85  # Target delta (deep ITM)
CALL_DTE       = 365   # Days to expiry — as far out as possible
CALL_ALLOC     = 0.40  # 40% of capital per call entry

# Put leg: far OTM, sell for premium
PUT_OTM_PCT    = 0.25  # Strike 25% below current price
PUT_DTE        = 365   # ~1 year out
PUT_ALLOC      = 0.30  # 30% of capital reserved as collateral per put

# Exit
CALL_PROFIT_TARGET = 0.50  # Close calls at +50% gain
CALL_STOP_LOSS     = 0.40  # Close calls at -40% loss
PUT_BUYBACK_PCT    = 0.10  # Buy back puts when they drop to 10% of premium collected
MAX_HOLD_DAYS      = 300   # Max hold for calls before rolling

RISK_FREE_RATE = 0.045  # ~4.5% (current T-bill rate approx)
COMMISSION     = 0.65   # Per contract
INITIAL_CAPITAL = 10_000.0
PERIOD   = "5y"
INTERVAL = "1d"


# ── Black-Scholes ───────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x / 2.0)
    return 0.5 * (1.0 + sign * y)


def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call option price. T in years."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def black_scholes_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put option price. T in years."""
    if T <= 0 or sigma <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def call_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call delta."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1)


def find_call_strike(S: float, target_delta: float, T: float, r: float, sigma: float) -> float:
    """Find strike that gives approximately the target delta for a call."""
    # Binary search for strike
    lo, hi = S * 0.3, S * 1.2
    for _ in range(60):
        mid = (lo + hi) / 2
        d = call_delta(S, mid, T, r, sigma)
        if d > target_delta:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


# ── Data Fetching ───────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "5y", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "synthetic-long/1.0"})
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


def calc_historical_vol(closes: list[float], period: int = 30) -> list[float | None]:
    """Annualized historical volatility (30-day rolling)."""
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        log_rets = [math.log(closes[j] / closes[j - 1]) for j in range(i - period + 1, i + 1)]
        std = (sum((r - sum(log_rets) / len(log_rets)) ** 2 for r in log_rets) / len(log_rets)) ** 0.5
        out[i] = std * math.sqrt(252)
    return out


# ── Strategy Engine ─────────────────────────────────────────────────

def run_synthetic_long(candles: list[dict], vix_candles: list[dict], params: dict | None = None) -> dict:
    p = params or {}
    vix_entry      = p.get("vix_entry", VIX_ENTRY)
    vix_exit       = p.get("vix_exit", VIX_EXIT)
    vix_extreme    = p.get("vix_extreme", VIX_EXTREME)
    call_delta_t   = p.get("call_delta", CALL_DELTA)
    call_dte       = p.get("call_dte", CALL_DTE)
    call_alloc     = p.get("call_alloc", CALL_ALLOC)
    put_otm_pct    = p.get("put_otm_pct", PUT_OTM_PCT)
    put_dte        = p.get("put_dte", PUT_DTE)
    put_alloc      = p.get("put_alloc", PUT_ALLOC)
    call_tp        = p.get("call_profit_target", CALL_PROFIT_TARGET)
    call_sl        = p.get("call_stop_loss", CALL_STOP_LOSS)
    put_buyback    = p.get("put_buyback_pct", PUT_BUYBACK_PCT)
    max_hold       = p.get("max_hold_days", MAX_HOLD_DAYS)
    r              = p.get("risk_free_rate", RISK_FREE_RATE)
    commission     = p.get("commission", COMMISSION)
    initial_cap    = p.get("initial_capital", INITIAL_CAPITAL)
    disable_exit   = p.get("disable_exit", False)

    n = len(candles)
    closes = [c["close"] for c in candles]
    hvol = calc_historical_vol(closes)

    # Build VIX lookup by date
    vix_by_date: dict[str, float] = {}
    for vc in vix_candles:
        vix_by_date[vc["date"]] = vc["close"]

    # State
    capital = initial_cap
    call_positions: list[dict] = []  # Active call legs
    put_positions: list[dict] = []   # Active put legs (short)
    trades: list[dict] = []
    signal_log: list[dict] = []

    warmup = 35  # Need 30+ bars for hvol

    for i in range(warmup, n):
        date = candles[i]["date"]
        close = closes[i]
        sigma = hvol[i] if hvol[i] is not None else 0.25
        vix = vix_by_date.get(date)

        if vix is None:
            continue

        # Use VIX/100 as implied vol proxy (VIX is annualized % vol)
        iv = vix / 100.0

        # ── Manage existing call positions ──────────────────────
        for cp in call_positions[:]:
            days_held = i - cp["entry_bar"]
            T_remaining = max((cp["dte"] - days_held) / 365.0, 0.001)
            current_call_price = black_scholes_call(close, cp["strike"], T_remaining, r, iv)
            pnl_pct = (current_call_price - cp["entry_premium"]) / cp["entry_premium"]

            exit_reason = ""
            if disable_exit:
                if i == n - 1:
                    exit_reason = "end_of_data"
            else:
                if pnl_pct >= call_tp:
                    exit_reason = "call_profit_target"
                elif pnl_pct <= -call_sl:
                    exit_reason = "call_stop_loss"
                elif vix < vix_exit and pnl_pct > 0:
                    exit_reason = "vix_normalized"
                elif days_held >= max_hold:
                    exit_reason = "max_hold"
                elif i == n - 1:
                    exit_reason = "end_of_data"

            if exit_reason:
                # Sell the call
                contracts = cp["contracts"]
                gross_pnl = (current_call_price - cp["entry_premium"]) * 100 * contracts
                net_pnl = gross_pnl - commission * contracts * 2  # Open + close
                capital += cp["cost"] + net_pnl

                trades.append({
                    "entry_date": cp["entry_date"], "exit_date": date,
                    "entry_price": round(cp["stock_price_at_entry"], 2),
                    "exit_price": round(close, 2),
                    "side": "long", "leg": "call",
                    "strike": round(cp["strike"], 2),
                    "entry_premium": round(cp["entry_premium"], 2),
                    "exit_premium": round(current_call_price, 2),
                    "contracts": contracts,
                    "return_pct": round(pnl_pct * 100, 2),
                    "pnl_usd": round(net_pnl, 2),
                    "exit_reason": exit_reason,
                    "entry_reason": "deep_itm_call",
                    "vix_at_entry": round(cp["vix_at_entry"], 1),
                    "vix_at_exit": round(vix, 1),
                    "days_held": days_held,
                    "strategy": "synthetic_long",
                })
                call_positions.remove(cp)

        # ── Manage existing put positions (short puts) ──────────
        for pp in put_positions[:]:
            days_held = i - pp["entry_bar"]
            T_remaining = max((pp["dte"] - days_held) / 365.0, 0.001)
            current_put_price = black_scholes_put(close, pp["strike"], T_remaining, r, iv)

            exit_reason = ""
            if disable_exit:
                if i == n - 1:
                    exit_reason = "end_of_data"
            else:
                # Buy back if put is now worth very little (profit realized)
                if current_put_price <= pp["entry_premium"] * put_buyback:
                    exit_reason = "put_decay_profit"
                # Put went ITM — stock dropped below strike
                elif close < pp["strike"]:
                    exit_reason = "put_assigned"
                elif days_held >= pp["dte"] - 5:
                    exit_reason = "put_expiry"
                elif i == n - 1:
                    exit_reason = "end_of_data"

            if exit_reason:
                contracts = pp["contracts"]
                # Short put: collected premium at entry, pay current price to buy back
                gross_pnl = (pp["entry_premium"] - current_put_price) * 100 * contracts
                if exit_reason == "put_assigned":
                    # Assigned: must buy shares at strike, current value is lower
                    assignment_loss = (pp["strike"] - close) * 100 * contracts
                    gross_pnl = pp["entry_premium"] * 100 * contracts - assignment_loss
                net_pnl = gross_pnl - commission * contracts * 2
                capital += pp["collateral"] + net_pnl

                trades.append({
                    "entry_date": pp["entry_date"], "exit_date": date,
                    "entry_price": round(pp["stock_price_at_entry"], 2),
                    "exit_price": round(close, 2),
                    "side": "short", "leg": "put",
                    "strike": round(pp["strike"], 2),
                    "entry_premium": round(pp["entry_premium"], 2),
                    "exit_premium": round(current_put_price, 2),
                    "contracts": contracts,
                    "return_pct": round(net_pnl / pp["collateral"] * 100, 2) if pp["collateral"] > 0 else 0,
                    "pnl_usd": round(net_pnl, 2),
                    "exit_reason": exit_reason,
                    "entry_reason": "otm_put_sell",
                    "vix_at_entry": round(pp["vix_at_entry"], 1),
                    "vix_at_exit": round(vix, 1),
                    "days_held": days_held,
                    "strategy": "synthetic_long",
                })
                put_positions.remove(pp)

        # ── Entry signals ───────────────────────────────────────
        if vix >= vix_entry:
            available = capital

            # Leg 1: Buy deep ITM calls
            if not call_positions and available > 500:
                call_budget = available * call_alloc
                T = call_dte / 365.0
                strike = find_call_strike(close, call_delta_t, T, r, iv)
                call_price = black_scholes_call(close, strike, T, r, iv)

                if call_price > 0:
                    contracts = max(1, int(call_budget / (call_price * 100)))
                    cost = call_price * 100 * contracts + commission * contracts
                    if cost <= available:
                        capital -= cost
                        call_positions.append({
                            "entry_bar": i, "entry_date": date,
                            "stock_price_at_entry": close,
                            "strike": strike, "dte": call_dte,
                            "entry_premium": call_price,
                            "contracts": contracts, "cost": cost,
                            "vix_at_entry": vix,
                        })
                        signal_log.append({"bar": i, "date": date, "signal": "buy_call",
                                           "vix": round(vix, 1), "strike": round(strike, 2),
                                           "premium": round(call_price, 2), "contracts": contracts})

            # Leg 2: Sell OTM puts
            if not put_positions and capital > 500:
                put_budget = capital * put_alloc
                T = put_dte / 365.0
                put_strike = round(close * (1 - put_otm_pct), 2)
                put_price = black_scholes_put(close, put_strike, T, r, iv)

                if put_price > 0.50:  # Only sell if premium is worthwhile
                    # Collateral needed: strike * 100 * contracts (cash-secured)
                    max_contracts = max(1, int(put_budget / (put_strike * 100)))
                    contracts = min(max_contracts, 2)  # Cap at 2 contracts
                    collateral = put_strike * 100 * contracts * 0.20  # 20% margin
                    premium_collected = put_price * 100 * contracts - commission * contracts

                    if collateral <= capital:
                        capital -= collateral
                        # Premium is received (added to capital later on exit)
                        put_positions.append({
                            "entry_bar": i, "entry_date": date,
                            "stock_price_at_entry": close,
                            "strike": put_strike, "dte": put_dte,
                            "entry_premium": put_price,
                            "contracts": contracts, "collateral": collateral,
                            "vix_at_entry": vix,
                        })
                        signal_log.append({"bar": i, "date": date, "signal": "sell_put",
                                           "vix": round(vix, 1), "strike": round(put_strike, 2),
                                           "premium": round(put_price, 2), "contracts": contracts})

            # VIX extreme: add second call if already holding
            if vix >= vix_extreme and len(call_positions) == 1 and capital > 500:
                call_budget = capital * 0.30
                T = call_dte / 365.0
                strike = find_call_strike(close, call_delta_t, T, r, iv)
                call_price = black_scholes_call(close, strike, T, r, iv)
                if call_price > 0:
                    contracts = max(1, int(call_budget / (call_price * 100)))
                    cost = call_price * 100 * contracts + commission * contracts
                    if cost <= capital:
                        capital -= cost
                        call_positions.append({
                            "entry_bar": i, "entry_date": date,
                            "stock_price_at_entry": close,
                            "strike": strike, "dte": call_dte,
                            "entry_premium": call_price,
                            "contracts": contracts, "cost": cost,
                            "vix_at_entry": vix,
                        })
                        signal_log.append({"bar": i, "date": date, "signal": "extreme_add_call",
                                           "vix": round(vix, 1), "strike": round(strike, 2),
                                           "premium": round(call_price, 2), "contracts": contracts})

    # ── Metrics ─────────────────────────────────────────────────────
    bh_ret = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100
    total_ret = (capital - initial_cap) / initial_cap * 100

    call_trades = [t for t in trades if t["leg"] == "call"]
    put_trades = [t for t in trades if t["leg"] == "put"]
    winning = [t for t in trades if t["pnl_usd"] > 0]
    losing = [t for t in trades if t["pnl_usd"] <= 0]
    win_rate = round(len(winning) / len(trades) * 100, 1) if trades else 0.0
    total_pnl = sum(t["pnl_usd"] for t in trades)

    avg_gain = round(statistics.mean([t["pnl_usd"] for t in winning]), 2) if winning else 0.0
    avg_loss = round(statistics.mean([t["pnl_usd"] for t in losing]), 2) if losing else 0.0
    gw = sum(t["pnl_usd"] for t in winning)
    gl = abs(sum(t["pnl_usd"] for t in losing))
    profit_factor = round(gw / gl, 2) if gl > 0 else float("inf")

    # Max drawdown on cumulative P&L
    equity = initial_cap
    peak_eq = initial_cap
    max_dd = 0.0
    for t in trades:
        equity += t["pnl_usd"]
        if equity > peak_eq:
            peak_eq = equity
        dd = (equity - peak_eq) / peak_eq * 100
        if dd < max_dd:
            max_dd = dd

    # Build VIX overlay
    vix_overlay = []
    for vc in vix_candles:
        if candles[0]["date"] <= vc["date"] <= candles[-1]["date"]:
            vix_overlay.append({"time": vc["date"], "value": round(vc["close"], 2)})

    result = {
        "symbol": p.get("symbol", ""),
        "strategy": "synthetic_long",
        "strategy_label": (
            f"Synthetic Long (VIX entry>={vix_entry}, call delta={call_delta_t}, "
            f"put OTM={put_otm_pct*100:.0f}%)"
        ),
        "period": p.get("period", PERIOD),
        "interval": p.get("interval", INTERVAL),
        "candles_analyzed": n,
        "date_from": candles[0]["date"],
        "date_to": candles[-1]["date"],
        "initial_capital": initial_cap,
        "final_capital": round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "buy_and_hold_return_pct": round(bh_ret, 2),
        "vs_buy_and_hold_pct": round(total_ret - bh_ret, 2),
        "total_trades": len(trades),
        "call_trades": len(call_trades),
        "put_trades": len(put_trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate_pct": win_rate,
        "avg_gain_usd": avg_gain,
        "avg_loss_usd": avg_loss,
        "total_pnl_usd": round(total_pnl, 2),
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(max_dd, 2),
        "trade_log": trades,
        "signal_log": signal_log,
        "overlays": [],
        "data_source": "Yahoo Finance + Black-Scholes estimates",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Synthetic Long Strategy — Options")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--period", default=PERIOD)
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--vix-entry", type=float, default=VIX_ENTRY)
    parser.add_argument("--vix-exit", type=float, default=VIX_EXIT)
    parser.add_argument("--vix-extreme", type=float, default=VIX_EXTREME)
    parser.add_argument("--call-delta", type=float, default=CALL_DELTA)
    parser.add_argument("--call-dte", type=int, default=CALL_DTE)
    parser.add_argument("--put-otm", type=float, default=PUT_OTM_PCT)
    parser.add_argument("--put-dte", type=int, default=PUT_DTE)
    parser.add_argument("--disable-exit", action="store_true", help="Hold all positions to end — no exits")
    parser.add_argument("--chart", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  Synthetic Long — {args.symbol}")
    print(f"  VIX entry>={args.vix_entry}  exit<{args.vix_exit}  extreme>={args.vix_extreme}")
    print(f"  Call: delta={args.call_delta} DTE={args.call_dte}d  "
          f"Put: OTM={args.put_otm*100:.0f}% DTE={args.put_dte}d")
    print(f"{'='*65}")

    candles = fetch_ohlcv(args.symbol, args.period, "1d")
    vix_candles = fetch_ohlcv("^VIX", args.period, "1d")
    print(f"\n  Fetched {len(candles)} candles ({candles[0]['date']} -> {candles[-1]['date']})")
    print(f"  VIX data: {len(vix_candles)} candles\n")

    params = {
        "symbol": args.symbol, "period": args.period, "interval": "1d",
        "initial_capital": args.initial_capital,
        "vix_entry": args.vix_entry, "vix_exit": args.vix_exit,
        "vix_extreme": args.vix_extreme,
        "call_delta": args.call_delta, "call_dte": args.call_dte,
        "put_otm_pct": args.put_otm, "put_dte": args.put_dte,
        "disable_exit": args.disable_exit,
    }
    result = run_synthetic_long(candles, vix_candles, params)

    print(f"  Period:          {result['date_from']} -> {result['date_to']}")
    print(f"  Total Return:    {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:      {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:          {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:    {result['total_trades']} (calls: {result['call_trades']}, puts: {result['put_trades']})")
    print(f"  Win Rate:        {result['win_rate_pct']}%")
    print(f"  Avg Gain:        ${result['avg_gain_usd']:+.2f}")
    print(f"  Avg Loss:        ${result['avg_loss_usd']:+.2f}")
    print(f"  Total P&L:       ${result['total_pnl_usd']:+.2f}")
    print(f"  Profit Factor:   {result['profit_factor']}")
    print(f"  Max Drawdown:    {result['max_drawdown_pct']}%")

    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        leg = "CALL" if t["leg"] == "call" else "PUT "
        side = "BUY " if t["side"] == "long" else "SELL"
        print(f"    {side} {leg} K=${t['strike']:>8.2f}  "
              f"{t['entry_date']} -> {t['exit_date']}  "
              f"VIX {t['vix_at_entry']:>4.0f}->{t['vix_at_exit']:>4.0f}  "
              f"${t['pnl_usd']:>+8.2f}  ({t['return_pct']:+.1f}%)  "
              f"[{t['exit_reason']}]  {t['days_held']}d")

    if result["signal_log"]:
        print(f"\n  Signal Log:")
        for s in result["signal_log"]:
            print(f"    {s['date']}  {s['signal']:20s}  VIX={s['vix']:>5.1f}  "
                  f"K=${s['strike']:>8.2f}  prem=${s['premium']:>6.2f}  x{s['contracts']}")

    print(f"\n{'='*65}\n")

    # Save results
    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    json_out = {k: v for k, v in result.items() if k != "overlays"}
    fname = script_dir / f"synthetic_long_backtest_{safe_sym}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html
        chart_path = script_dir / f"synthetic_long_chart_{safe_sym}_{args.period}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path,
                           vix_candles=vix_candles)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
