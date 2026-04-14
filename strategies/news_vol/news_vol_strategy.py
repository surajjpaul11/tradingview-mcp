"""
News Volatility Capitalizer Strategy
======================================
Trades geopolitical volatility — specifically Middle East / Strait of Hormuz
escalations that cause simultaneous oil spikes and VIX jumps.

Signal detection:
  1. OIL SPIKE:  Crude (USO) rises >= 8% in 5 days
  2. VIX FEAR:   VIX >= 25
  3. GOLD SURGE: GLD rises >= 2% in 5 days (safe haven flow)
  When 2+ of these fire simultaneously → geopolitical event detected.

Portfolio allocation on trigger:
  - 30% Energy  (XLE — broad energy ETF)
  - 25% Defense (ITA — aerospace & defense ETF)
  - 20% Tankers (STNG — product tankers, benefits from Hormuz rerouting)
  - 15% Gold    (GLD — safe haven)
  - 10% Cash reserve

Exit conditions:
  - VIX normalizes below 18 AND oil retraces 50% of spike → event fading
  - Individual leg: +20% profit target or -12% stop loss
  - Max hold: 60 trading days (geopolitical premiums decay)

Also supports single-stock mode for individual tickers.

Usage:
    python3 strategies/news_vol/news_vol_strategy.py --period 5y --chart
    python3 strategies/news_vol/news_vol_strategy.py --period 2y --vix-trigger 22
    python3 strategies/news_vol/news_vol_strategy.py --symbol OXY --period 5y --single-stock
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

# Signal detection
OIL_SPIKE_PCT    = 0.08   # Oil up 8% in lookback window
OIL_LOOKBACK     = 5      # Days to measure oil spike
VIX_TRIGGER      = 25     # VIX >= this
GOLD_SPIKE_PCT   = 0.02   # Gold up 2% in lookback
GOLD_LOOKBACK    = 5
MIN_SIGNALS      = 2      # Need 2+ of 3 signals to confirm geopolitical event

# Portfolio legs
LEGS = {
    "energy":  {"symbol": "XLE",  "alloc": 0.30, "label": "Energy (XLE)"},
    "defense": {"symbol": "ITA",  "alloc": 0.25, "label": "Defense (ITA)"},
    "tankers": {"symbol": "STNG", "alloc": 0.20, "label": "Tankers (STNG)"},
    "gold":    {"symbol": "GLD",  "alloc": 0.15, "label": "Gold (GLD)"},
}

# Exit
PROFIT_TARGET  = 0.20   # +20% per leg
STOP_LOSS      = 0.12   # -12% per leg
MAX_HOLD_DAYS  = 60     # Max hold
VIX_EXIT       = 18     # VIX calm threshold
OIL_RETRACE    = 0.50   # Oil retraces 50% of spike → event fading

COMMISSION      = 0.001
SLIPPAGE        = 0.001
INITIAL_CAPITAL = 10_000.0
PERIOD   = "5y"
INTERVAL = "1d"


# ── Data Fetching ───────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "5y", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "news-vol/1.0"})
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


def build_price_lookup(candles: list[dict]) -> dict[str, float]:
    return {c["date"]: c["close"] for c in candles}


# ── Strategy Engine ─────────────────────────────────────────────────

def run_news_vol(candles_main: list[dict], oil_candles: list[dict],
                 vix_candles: list[dict], gold_candles: list[dict],
                 leg_candles: dict[str, list[dict]],
                 params: dict | None = None) -> dict:
    """
    candles_main: SPY (or primary symbol for B&H comparison)
    oil_candles:  USO
    vix_candles:  ^VIX
    gold_candles: GLD
    leg_candles:  {"energy": XLE candles, "defense": ITA candles, ...}
    """
    p = params or {}
    oil_spike_pct  = p.get("oil_spike_pct", OIL_SPIKE_PCT)
    oil_lookback   = p.get("oil_lookback", OIL_LOOKBACK)
    vix_trigger    = p.get("vix_trigger", VIX_TRIGGER)
    gold_spike_pct = p.get("gold_spike_pct", GOLD_SPIKE_PCT)
    gold_lookback  = p.get("gold_lookback", GOLD_LOOKBACK)
    min_signals    = p.get("min_signals", MIN_SIGNALS)
    profit_target  = p.get("profit_target", PROFIT_TARGET)
    stop_loss      = p.get("stop_loss", STOP_LOSS)
    max_hold       = p.get("max_hold_days", MAX_HOLD_DAYS)
    vix_exit       = p.get("vix_exit", VIX_EXIT)
    oil_retrace    = p.get("oil_retrace", OIL_RETRACE)
    commission     = p.get("commission", COMMISSION)
    slippage       = p.get("slippage", SLIPPAGE)
    initial_cap    = p.get("initial_capital", INITIAL_CAPITAL)
    single_stock   = p.get("single_stock", False)
    single_symbol  = p.get("symbol", "SPY")
    disable_exit   = p.get("disable_exit", False)
    cost_pct       = (commission + slippage) * 100

    n = len(candles_main)

    # Build price lookups
    oil_prices = build_price_lookup(oil_candles)
    vix_prices = build_price_lookup(vix_candles)
    gold_prices = build_price_lookup(gold_candles)

    # For each leg, build price lookup
    leg_prices: dict[str, dict[str, float]] = {}
    for leg_name, lc in leg_candles.items():
        leg_prices[leg_name] = build_price_lookup(lc)

    # If single stock mode, override legs
    if single_stock:
        active_legs = {"single": {"symbol": single_symbol, "alloc": 0.90, "label": single_symbol}}
        leg_prices["single"] = {c["date"]: c["close"] for c in candles_main}
    else:
        active_legs = dict(LEGS)

    # State
    capital = initial_cap
    positions: dict[str, dict] = {}  # leg_name -> position info
    trades: list[dict] = []
    signal_log: list[dict] = []
    cooldown = 0

    warmup = max(oil_lookback, gold_lookback) + 5

    for i in range(warmup, n):
        date = candles_main[i]["date"]
        close_main = candles_main[i]["close"]

        # Get indicator values
        vix = vix_prices.get(date)
        oil_now = oil_prices.get(date)
        gold_now = gold_prices.get(date)

        if vix is None or oil_now is None or gold_now is None:
            continue

        # Look back for oil and gold changes
        oil_past_date = candles_main[max(0, i - oil_lookback)]["date"]
        gold_past_date = candles_main[max(0, i - gold_lookback)]["date"]
        oil_past = oil_prices.get(oil_past_date, oil_now)
        gold_past = gold_prices.get(gold_past_date, gold_now)

        oil_change = (oil_now - oil_past) / oil_past if oil_past > 0 else 0
        gold_change = (gold_now - gold_past) / gold_past if gold_past > 0 else 0

        # ── Manage existing positions ───────────────────────────
        for leg_name in list(positions.keys()):
            pos = positions[leg_name]
            leg_price = leg_prices.get(leg_name, {}).get(date)
            if leg_price is None:
                continue

            days_held = i - pos["entry_bar"]
            pnl_pct = (leg_price - pos["entry_price"]) / pos["entry_price"]

            exit_reason = ""
            if disable_exit:
                if i == n - 1:
                    exit_reason = "end_of_data"
            else:
                if pnl_pct >= profit_target:
                    exit_reason = "profit_target"
                elif pnl_pct <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= max_hold:
                    exit_reason = "max_hold"
                # Event fading: VIX calm + oil retraced
                elif (vix < vix_exit and
                      oil_change < pos.get("oil_spike_at_entry", 0) * (1 - oil_retrace) and
                      days_held > 5):
                    exit_reason = "event_fading"
                elif i == n - 1:
                    exit_reason = "end_of_data"

            if exit_reason:
                gross_ret = pnl_pct * 100
                net_ret = gross_ret - cost_pct * 2
                pnl_usd = pos["capital_deployed"] * net_ret / 100

                capital += pos["capital_deployed"] + pnl_usd
                trades.append({
                    "entry_date": pos["entry_date"], "exit_date": date,
                    "entry_price": round(pos["entry_price"], 2),
                    "exit_price": round(leg_price, 2),
                    "side": "long", "leg": leg_name,
                    "signal": pos["signal"],
                    "entry_reason": pos["entry_reason"],
                    "return_pct": round(net_ret, 2),
                    "pnl_usd": round(pnl_usd, 2),
                    "exit_reason": exit_reason,
                    "vix_at_entry": round(pos["vix_at_entry"], 1),
                    "vix_at_exit": round(vix, 1),
                    "oil_change_at_entry": round(pos["oil_spike_at_entry"] * 100, 1),
                    "days_held": days_held,
                    "strategy": "news_vol",
                })
                del positions[leg_name]

        # ── Entry signals ───────────────────────────────────────
        if cooldown > 0:
            cooldown -= 1
            continue

        if positions:
            continue  # Already in trade

        # Count signals
        signals_fired = []
        if oil_change >= oil_spike_pct:
            signals_fired.append("oil_spike")
        if vix >= vix_trigger:
            signals_fired.append("vix_fear")
        if gold_change >= gold_spike_pct:
            signals_fired.append("gold_surge")

        if len(signals_fired) >= min_signals:
            signal_combo = "+".join(signals_fired)
            available = capital

            for leg_name, leg_info in active_legs.items():
                leg_price = leg_prices.get(leg_name, {}).get(date)
                if leg_price is None or leg_price <= 0:
                    continue

                alloc = leg_info["alloc"]
                deploy = available * alloc

                if deploy < 50:
                    continue

                capital -= deploy
                positions[leg_name] = {
                    "entry_bar": i, "entry_date": date,
                    "entry_price": leg_price,
                    "capital_deployed": deploy,
                    "signal": signal_combo,
                    "entry_reason": f"geopolitical_{leg_name}",
                    "vix_at_entry": vix,
                    "oil_spike_at_entry": oil_change,
                }

            if positions:
                signal_log.append({
                    "bar": i, "date": date,
                    "signals": signal_combo,
                    "vix": round(vix, 1),
                    "oil_5d": round(oil_change * 100, 1),
                    "gold_5d": round(gold_change * 100, 1),
                    "legs": list(positions.keys()),
                })
                cooldown = 10  # Don't re-enter for 10 bars

    # ── Metrics ─────────────────────────────────────────────────────
    bh_ret = (candles_main[-1]["close"] - candles_main[0]["close"]) / candles_main[0]["close"] * 100
    total_ret = (capital - initial_cap) / initial_cap * 100

    winning = [t for t in trades if t["pnl_usd"] > 0]
    losing = [t for t in trades if t["pnl_usd"] <= 0]
    win_rate = round(len(winning) / len(trades) * 100, 1) if trades else 0.0
    total_pnl = sum(t["pnl_usd"] for t in trades)
    avg_gain = round(statistics.mean([t["pnl_usd"] for t in winning]), 2) if winning else 0.0
    avg_loss = round(statistics.mean([t["pnl_usd"] for t in losing]), 2) if losing else 0.0
    gw = sum(t["pnl_usd"] for t in winning)
    gl = abs(sum(t["pnl_usd"] for t in losing))
    profit_factor = round(gw / gl, 2) if gl > 0 else float("inf")

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

    # Leg breakdown
    leg_summary = {}
    for leg_name in set(t["leg"] for t in trades):
        lt = [t for t in trades if t["leg"] == leg_name]
        leg_summary[leg_name] = {
            "trades": len(lt),
            "pnl": round(sum(t["pnl_usd"] for t in lt), 2),
            "avg_ret": round(statistics.mean([t["return_pct"] for t in lt]), 2) if lt else 0,
            "win_rate": round(len([t for t in lt if t["pnl_usd"] > 0]) / len(lt) * 100, 1) if lt else 0,
        }

    result = {
        "symbol": single_symbol if single_stock else "PORTFOLIO",
        "strategy": "news_vol",
        "strategy_label": (
            f"News Volatility Capitalizer (VIX>={vix_trigger}, oil spike>={oil_spike_pct*100:.0f}%, "
            f"min {min_signals} signals)"
        ),
        "period": p.get("period", PERIOD),
        "interval": INTERVAL,
        "candles_analyzed": n,
        "date_from": candles_main[0]["date"],
        "date_to": candles_main[-1]["date"],
        "initial_capital": initial_cap,
        "final_capital": round(capital, 2),
        "total_return_pct": round(total_ret, 2),
        "buy_and_hold_return_pct": round(bh_ret, 2),
        "vs_buy_and_hold_pct": round(total_ret - bh_ret, 2),
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate_pct": win_rate,
        "avg_gain_usd": avg_gain,
        "avg_loss_usd": avg_loss,
        "total_pnl_usd": round(total_pnl, 2),
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(max_dd, 2),
        "leg_summary": leg_summary,
        "signal_log": signal_log,
        "trade_log": trades,
        "overlays": [],
        "data_source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="News Volatility Capitalizer")
    parser.add_argument("--symbol", default="SPY", help="Primary symbol (for B&H comparison)")
    parser.add_argument("--period", default=PERIOD)
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--vix-trigger", type=float, default=VIX_TRIGGER)
    parser.add_argument("--oil-spike", type=float, default=OIL_SPIKE_PCT)
    parser.add_argument("--min-signals", type=int, default=MIN_SIGNALS, choices=[1, 2, 3])
    parser.add_argument("--single-stock", action="store_true",
                        help="Trade only --symbol instead of portfolio")
    parser.add_argument("--disable-exit", action="store_true",
                        help="Hold all positions to end — no exits")
    parser.add_argument("--chart", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  News Volatility Capitalizer")
    mode = f"Single: {args.symbol}" if args.single_stock else "Portfolio: XLE+ITA+STNG+GLD"
    print(f"  Mode: {mode}")
    print(f"  VIX>={args.vix_trigger}  Oil spike>={args.oil_spike*100:.0f}%  "
          f"Min signals: {args.min_signals}")
    if args.disable_exit:
        print(f"  EXIT DISABLED — holding all positions to end")
    print(f"{'='*65}")

    # Fetch all data
    print(f"\n  Fetching data...")
    candles_main = fetch_ohlcv(args.symbol, args.period, "1d")
    oil_candles = fetch_ohlcv("USO", args.period, "1d")
    vix_candles = fetch_ohlcv("^VIX", args.period, "1d")
    gold_candles = fetch_ohlcv("GLD", args.period, "1d")

    leg_candles = {}
    if not args.single_stock:
        for leg_name, leg_info in LEGS.items():
            leg_candles[leg_name] = fetch_ohlcv(leg_info["symbol"], args.period, "1d")
            print(f"    {leg_info['label']}: {len(leg_candles[leg_name])} candles")

    print(f"  Primary ({args.symbol}): {len(candles_main)} candles "
          f"({candles_main[0]['date']} -> {candles_main[-1]['date']})")
    print(f"  Oil (USO): {len(oil_candles)}  VIX: {len(vix_candles)}  Gold (GLD): {len(gold_candles)}\n")

    params = {
        "symbol": args.symbol, "period": args.period,
        "initial_capital": args.initial_capital,
        "vix_trigger": args.vix_trigger, "oil_spike_pct": args.oil_spike,
        "min_signals": args.min_signals,
        "single_stock": args.single_stock,
        "disable_exit": args.disable_exit,
    }
    result = run_news_vol(candles_main, oil_candles, vix_candles, gold_candles,
                          leg_candles, params)

    print(f"  Period:          {result['date_from']} -> {result['date_to']}")
    print(f"  Total Return:    {result['total_return_pct']:+.2f}%")
    print(f"  Buy & Hold:      {result['buy_and_hold_return_pct']:+.2f}%")
    print(f"  vs B&H:          {result['vs_buy_and_hold_pct']:+.2f}%")
    print(f"  Total Trades:    {result['total_trades']}")
    print(f"  Win Rate:        {result['win_rate_pct']}%")
    print(f"  Avg Gain:        ${result['avg_gain_usd']:+.2f}")
    print(f"  Avg Loss:        ${result['avg_loss_usd']:+.2f}")
    print(f"  Total P&L:       ${result['total_pnl_usd']:+.2f}")
    print(f"  Profit Factor:   {result['profit_factor']}")
    print(f"  Max Drawdown:    {result['max_drawdown_pct']}%")

    if result["leg_summary"]:
        print(f"\n  Leg Breakdown:")
        for leg, stats in sorted(result["leg_summary"].items(), key=lambda x: -x[1]["pnl"]):
            label = LEGS.get(leg, {}).get("label", leg)
            print(f"    {label:20s}  trades={stats['trades']}  "
                  f"P&L=${stats['pnl']:+.2f}  avg={stats['avg_ret']:+.1f}%  "
                  f"win={stats['win_rate']}%")

    if result["signal_log"]:
        print(f"\n  Geopolitical Events Detected:")
        for s in result["signal_log"]:
            print(f"    {s['date']}  {s['signals']:30s}  "
                  f"VIX={s['vix']:>5.1f}  oil_5d={s['oil_5d']:+.1f}%  "
                  f"gold_5d={s['gold_5d']:+.1f}%  -> {s['legs']}")

    print(f"\n  Trade Log:")
    for t in result["trade_log"]:
        leg_label = LEGS.get(t["leg"], {}).get("label", t["leg"])
        print(f"    {leg_label:20s}  {t['entry_date']} -> {t['exit_date']}  "
              f"VIX {t['vix_at_entry']:>4.0f}->{t['vix_at_exit']:>4.0f}  "
              f"${t['pnl_usd']:>+8.2f}  ({t['return_pct']:+.1f}%)  "
              f"[{t['exit_reason']}]  {t['days_held']}d")

    print(f"\n{'='*65}\n")

    # Save
    script_dir = Path(__file__).resolve().parent
    safe_sym = args.symbol.replace("-", "_")
    mode_tag = "single" if args.single_stock else "portfolio"
    json_out = {k: v for k, v in result.items() if k != "overlays"}
    fname = script_dir / f"news_vol_backtest_{safe_sym}_{mode_tag}_{args.period}.json"
    with open(fname, "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  Results saved to: {fname}\n")

    if args.chart:
        strategies_dir = script_dir.parent
        sys.path.insert(0, str(strategies_dir.parent))
        from strategies.visualize import generate_chart_html
        chart_path = script_dir / f"news_vol_chart_{safe_sym}_{mode_tag}_{args.period}.html"
        generate_chart_html(result=result, candles=candles_main, output_path=chart_path,
                           vix_candles=vix_candles)
        print(f"  Chart saved to: {chart_path}\n")


if __name__ == "__main__":
    main()
