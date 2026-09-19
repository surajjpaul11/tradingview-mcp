#!/usr/bin/env python3
"""
Active Trader — Runs strategy signals against Alpaca paper positions.

For each symbol+strategy pair:
  1. Fetch recent OHLCV data
  2. Run the strategy to determine current signal (hold vs exit)
  3. Compare to Alpaca positions
  4. Execute trades if signal and position disagree

Strategies check the LAST bar's state:
  - If strategy ends "in position" → we should hold
  - If strategy ends "out of position" → we should sell
  - If strategy says "enter" but we don't hold → we should buy

Usage:
    python3 scripts/active_trader.py              # Check signals + trade
    python3 scripts/active_trader.py --dry-run     # Check signals only, no trades
    python3 scripts/active_trader.py --status       # Just show current state
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Add project paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ── Configuration ───────────────────────────────────────────────────

# Symbol → Strategy mapping (from strategy-performers.md best combos)
PORTFOLIO = {
    # Active positions
    "WDC":   {"strategy": "smart_hold",        "capital": 100},
    "GOOGL": {"strategy": "smart_hold",         "capital": 100},
    "AMD":   {"strategy": "hyperbolic_runner",  "capital": 100},
    "SPY":   {"strategy": "smart_hold",         "capital": 100},
    "AMZN":  {"strategy": "smart_hold",         "capital": 100},
    "SNDK":  {"strategy": "hyperbolic_runner",  "capital": 200},
    "BE":    {"strategy": "hyperbolic_runner",  "capital": 125},
    "SMR":   {"strategy": "adaptive_smart_hold", "capital": 78},
    # Pending sell (PDT blocked today)
    "SMCI":  {"strategy": "curved_channel",     "capital": 100},
    # Dropped (sold)
    # "PLTR": sold — negative strategy return
    # "TSLA": sold — ma_breakdown exit
    # "MSFT": sold — vix_accelerated_exit
}

DATA_PERIOD = "6mo"  # Enough history for indicators to warm up

# RSI Cash Allocation Overlay
RSI_PERIOD       = 14
RSI_OVERBOUGHT   = 70   # Trim to raise cash
RSI_OVERSOLD     = 30   # Deploy cash
CASH_TARGET_PCT  = 0.20  # Target 20% cash when overbought
# When overbought: trim positions to ensure cash >= 20% of equity
# When oversold: deploy cash into oversold stocks, can go to 0% cash
# This overlay only trims/adds — never fully exits (main strategy controls that)


# ── Data Fetching ───────────────────────────────────────────────────

def fetch_ohlcv(symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": "active-trader/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    q = result["indicators"]["quote"][0]
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        candles.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": round(o, 4), "high": round(h, 4),
            "low": round(l, 4), "close": round(c, 4), "volume": v or 0,
        })
    return candles


# ── Strategy Signal Runners ────────────────────────────────────────
# Each returns: {"signal": "hold"|"exit"|"enter", "reason": "...", "details": {...}}

def check_smart_hold_signal(symbol: str) -> dict:
    """Run Smart Hold and check if we should be in position."""
    try:
        from strategies.smart_hold.smart_hold_strategy import run_smart_hold
        candles = fetch_ohlcv(symbol, DATA_PERIOD)
        vix_candles = fetch_ohlcv("^VIX", DATA_PERIOD)
        result = run_smart_hold(candles, vix_candles, {"symbol": symbol})
        trades = result.get("trade_log", [])

        if not trades:
            return {"signal": "hold", "reason": "no_trades_initial_hold",
                    "details": {"strategy_return": result.get("total_return_pct", 0)}}

        last_trade = trades[-1]
        last_date = candles[-1]["date"]

        # If the last trade has no exit (still open) or exit is the last bar
        if last_trade.get("exit_date") == last_date and last_trade.get("exit_reason") == "end_of_data":
            # Strategy was in position at end → hold
            return {"signal": "hold", "reason": "in_position_at_end",
                    "details": {"entry": last_trade.get("entry_date"),
                                "return": last_trade.get("return_pct", 0)}}
        elif last_trade.get("exit_date") == last_date:
            # Strategy exited on the last bar for a real reason → exit
            return {"signal": "exit", "reason": last_trade.get("exit_reason", "unknown"),
                    "details": {"exit_date": last_trade["exit_date"],
                                "return": last_trade.get("return_pct", 0)}}
        else:
            # Last trade exited before the last bar — check if re-entry happened
            # If there are more recent entry signals after the last exit, hold
            last_exit_date = last_trade.get("exit_date", "")
            # Check if any trade entry is after the last exit
            reentries = [t for t in trades if t.get("entry_date", "") > last_exit_date]
            if reentries:
                return {"signal": "hold", "reason": "re_entered_after_exit",
                        "details": {"reentry_date": reentries[-1]["entry_date"]}}
            else:
                return {"signal": "exit", "reason": f"exited_{last_trade.get('exit_reason', 'unknown')}",
                        "details": {"exit_date": last_exit_date,
                                    "bars_since_exit": "recent"}}
    except Exception as e:
        return {"signal": "hold", "reason": f"error: {e}", "details": {}}


def check_hyperbolic_runner_signal(symbol: str) -> dict:
    """Run Hyperbolic Runner and check signal."""
    try:
        from strategies.hyperbolic_runner.hyperbolic_runner_strategy import run_hyperbolic_runner
        candles = fetch_ohlcv(symbol, DATA_PERIOD)
        result = run_hyperbolic_runner(candles, {"symbol": symbol})
        trades = result.get("trade_log", [])

        if not trades:
            return {"signal": "enter", "reason": "no_trades_waiting",
                    "details": {"strategy_return": result.get("total_return_pct", 0)}}

        last_trade = trades[-1]
        last_date = candles[-1]["date"]

        if last_trade.get("exit_date") == last_date and last_trade.get("exit_reason") == "end_of_data":
            return {"signal": "hold", "reason": "in_position_at_end",
                    "details": {"return": last_trade.get("return_pct", 0)}}
        elif last_trade.get("exit_date") == last_date:
            return {"signal": "exit", "reason": last_trade.get("exit_reason", "unknown"),
                    "details": {"return": last_trade.get("return_pct", 0)}}
        else:
            return {"signal": "exit", "reason": f"exited_{last_trade.get('exit_reason', '')}",
                    "details": {"exit_date": last_trade.get("exit_date")}}
    except Exception as e:
        return {"signal": "hold", "reason": f"error: {e}", "details": {}}


def check_curved_channel_signal(symbol: str) -> dict:
    """Run Curved Channel and check signal."""
    try:
        from strategies.curves.curved_channel_strategy import run_curved_channel
        candles = fetch_ohlcv(symbol, DATA_PERIOD)
        result = run_curved_channel(candles, {"symbol": symbol})
        trades = result.get("trade_log", [])

        if not trades:
            return {"signal": "enter", "reason": "no_trades_waiting",
                    "details": {}}

        last_trade = trades[-1]
        last_date = candles[-1]["date"]

        if last_trade.get("exit_date") == last_date and last_trade.get("exit_reason") == "end_of_data":
            return {"signal": "hold", "reason": "in_position_at_end",
                    "details": {"return": last_trade.get("return_pct", 0)}}
        elif last_trade.get("exit_date") == last_date:
            return {"signal": "exit", "reason": last_trade.get("exit_reason", "unknown"),
                    "details": {"return": last_trade.get("return_pct", 0)}}
        else:
            return {"signal": "exit", "reason": f"exited_{last_trade.get('exit_reason', '')}",
                    "details": {"exit_date": last_trade.get("exit_date")}}
    except Exception as e:
        return {"signal": "hold", "reason": f"error: {e}", "details": {}}


def check_adaptive_smart_hold_signal(symbol: str) -> dict:
    """Run Adaptive Smart Hold (RC re-entry for high-vol, standard for low-vol)."""
    try:
        from strategies.smart_hold_rc.run_adaptive import calc_median_atr_pct
        candles = fetch_ohlcv(symbol, DATA_PERIOD)
        vix_candles = fetch_ohlcv("^VIX", DATA_PERIOD)
        median_atr = calc_median_atr_pct(candles)

        if median_atr > 10.0:
            # High vol → use RC re-entry
            from strategies.smart_hold_rc.smart_hold_rc_strategy import run_smart_hold_rc
            result = run_smart_hold_rc(candles, vix_candles, {
                "symbol": symbol, "force_rc": True,
            })
        else:
            # Low vol → standard Smart Hold
            from strategies.smart_hold.smart_hold_strategy import run_smart_hold
            result = run_smart_hold(candles, vix_candles, {"symbol": symbol})

        trades = result.get("trade_log", [])
        if not trades:
            return {"signal": "hold", "reason": "no_trades_initial_hold",
                    "details": {"mode": "rc" if median_atr > 10 else "standard",
                                "atr_pct": round(median_atr, 1)}}

        last_trade = trades[-1]
        last_date = candles[-1]["date"]

        if last_trade.get("exit_date") == last_date and last_trade.get("exit_reason") == "end_of_data":
            return {"signal": "hold", "reason": "in_position_at_end",
                    "details": {"mode": "rc" if median_atr > 10 else "standard",
                                "return": last_trade.get("return_pct", 0)}}
        elif last_trade.get("exit_date") == last_date:
            return {"signal": "exit", "reason": last_trade.get("exit_reason", "unknown"),
                    "details": {"return": last_trade.get("return_pct", 0)}}
        else:
            last_exit_date = last_trade.get("exit_date", "")
            reentries = [t for t in trades if t.get("entry_date", "") > last_exit_date]
            if reentries:
                return {"signal": "hold", "reason": "re_entered_after_exit",
                        "details": {"reentry_date": reentries[-1]["entry_date"]}}
            else:
                return {"signal": "exit", "reason": f"exited_{last_trade.get('exit_reason', '')}",
                        "details": {"exit_date": last_exit_date}}
    except Exception as e:
        return {"signal": "hold", "reason": f"error: {e}", "details": {}}


STRATEGY_CHECKERS = {
    "smart_hold": check_smart_hold_signal,
    "hyperbolic_runner": check_hyperbolic_runner_signal,
    "curved_channel": check_curved_channel_signal,
    "adaptive_smart_hold": check_adaptive_smart_hold_signal,
}


def calc_rsi(closes: list[float], period: int = 14) -> float | None:
    """Calculate current RSI from a list of closing prices."""
    if len(closes) < period + 1:
        return None
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, period + 1)]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, period + 1)]
    ag, al = sum(gains) / period, sum(losses) / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def get_rsi_for_symbol(symbol: str) -> float | None:
    """Fetch recent data and compute current RSI(14)."""
    try:
        candles = fetch_ohlcv(symbol, "3mo")
        closes = [c["close"] for c in candles]
        return calc_rsi(closes, RSI_PERIOD)
    except Exception:
        return None


# ── Alpaca Connection ───────────────────────────────────────────────

def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()


def get_alpaca_api():
    import alpaca_trade_api as tradeapi
    return tradeapi.REST(
        os.environ["ALPACA_API_KEY"],
        os.environ["ALPACA_API_SECRET"],
        "https://paper-api.alpaca.markets",
        api_version="v2",
    )


# ── Main ────────────────────────────────────────────────────────────

def run(dry_run: bool = False, status_only: bool = False):
    load_env()
    import alpaca_trade_api as tradeapi
    api = get_alpaca_api()

    clock = api.get_clock()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not clock.is_open:
        print(f"[{now}] Market closed. Next open: {clock.next_open}")
        return

    account = api.get_account()
    equity = float(account.equity)
    cash = float(account.cash)

    # Get current positions
    positions = {p.symbol: p for p in api.list_positions()}

    print(f"[{now}] === ACTIVE TRADER {'(DRY RUN)' if dry_run else '(LIVE PAPER)'} ===")
    print(f"Equity: ${equity:,.2f}  Cash: ${cash:,.2f}")
    print()

    if status_only:
        # Just show positions
        for sym, p in positions.items():
            strat = PORTFOLIO.get(sym, {}).get("strategy", "unknown")
            pnl_pct = float(p.unrealized_plpc) * 100
            print(f"  {sym:8s}  {strat:22s}  {pnl_pct:+.2f}%  ${float(p.unrealized_pl):+.2f}")
        return

    # Check each symbol's strategy signal
    print(f"{'Symbol':8s}  {'Strategy':22s}  {'Position':10s}  {'Signal':8s}  {'Reason':30s}  {'Action':15s}")
    print("-" * 100)

    actions_taken = []

    for symbol, config in PORTFOLIO.items():
        strategy = config["strategy"]
        checker = STRATEGY_CHECKERS.get(strategy)
        has_position = symbol in positions

        if checker is None:
            print(f"{symbol:8s}  {strategy:22s}  {'HELD' if has_position else 'NONE':10s}  "
                  f"{'???':8s}  {'no checker implemented':30s}  {'skip':15s}")
            continue

        # Run strategy signal check
        try:
            result = checker(symbol)
        except Exception as e:
            print(f"{symbol:8s}  {strategy:22s}  {'HELD' if has_position else 'NONE':10s}  "
                  f"{'ERROR':8s}  {str(e)[:30]:30s}  {'skip':15s}")
            continue

        signal = result["signal"]
        reason = result["reason"]

        # Determine action
        action = "none"
        if signal == "exit" and has_position:
            action = "SELL"
        elif signal == "enter" and not has_position:
            action = "BUY"
        elif signal == "hold" and has_position:
            action = "hold"
        elif signal == "hold" and not has_position:
            action = "wait"
        elif signal == "exit" and not has_position:
            action = "already_out"
        elif signal == "enter" and has_position:
            action = "already_in"

        pos_str = "HELD" if has_position else "NONE"
        if has_position:
            pnl = float(positions[symbol].unrealized_plpc) * 100
            pos_str = f"HELD {pnl:+.1f}%"

        action_display = action
        if action == "SELL":
            action_display = ">>> SELL <<<"
        elif action == "BUY":
            action_display = ">>> BUY <<<"

        print(f"{symbol:8s}  {strategy:22s}  {pos_str:10s}  {signal:8s}  {reason[:30]:30s}  {action_display:15s}")

        # Execute trades
        if action == "SELL" and not dry_run:
            try:
                qty = positions[symbol].qty
                order = api.submit_order(symbol=symbol, qty=qty, side="sell",
                                         type="market", time_in_force="day")
                actions_taken.append(f"SOLD {qty} {symbol} (order {order.id[:8]})")
                print(f"  >> EXECUTED: Sold {qty} {symbol}")
            except Exception as e:
                print(f"  >> SELL FAILED: {e}")

        elif action == "BUY" and not dry_run:
            try:
                # Use available cash, allocate ~$100 per position
                buy_amount = min(100.0, cash * 0.9)
                if buy_amount > 10:
                    # Get current price
                    candles = fetch_ohlcv(symbol, "5d")
                    price = candles[-1]["close"]
                    qty = round(buy_amount / price, 2)
                    order = api.submit_order(symbol=symbol, qty=str(qty), side="buy",
                                             type="market", time_in_force="day")
                    actions_taken.append(f"BOUGHT {qty} {symbol} @ ~${price:.2f} (order {order.id[:8]})")
                    print(f"  >> EXECUTED: Bought {qty} {symbol}")
                    cash -= buy_amount
            except Exception as e:
                print(f"  >> BUY FAILED: {e}")

    # ── RSI Cash Allocation Overlay ────────────────────────────────
    # Runs AFTER main strategy signals — trims overbought, adds oversold
    # Refresh positions and cash after any strategy trades
    positions = {p.symbol: p for p in api.list_positions()}
    account = api.get_account()
    equity = float(account.equity)
    cash = float(account.cash)
    cash_pct = cash / equity if equity > 0 else 0

    print()
    print(f"{'─'*50}")
    print(f"RSI CASH ALLOCATION OVERLAY")
    print(f"Cash: ${cash:,.2f} ({cash_pct*100:.1f}% of equity)  Target when OB: {CASH_TARGET_PCT*100:.0f}%")
    print(f"{'Symbol':8s}  {'RSI':>6s}  {'Status':12s}  {'Action':20s}")
    print(f"{'─'*50}")

    # Compute RSI for all held positions
    rsi_data: dict[str, float] = {}
    overbought_syms = []
    oversold_syms = []

    for symbol in list(positions.keys()):
        rsi = get_rsi_for_symbol(symbol)
        if rsi is None:
            print(f"{symbol:8s}  {'N/A':>6s}  {'unknown':12s}  {'skip':20s}")
            continue

        rsi_data[symbol] = rsi
        if rsi >= RSI_OVERBOUGHT:
            status = "OVERBOUGHT"
            overbought_syms.append(symbol)
        elif rsi <= RSI_OVERSOLD:
            status = "OVERSOLD"
            oversold_syms.append(symbol)
        else:
            status = "neutral"

        print(f"{symbol:8s}  {rsi:>6.1f}  {status:12s}")

    # Phase 1: OVERBOUGHT — trim to raise cash to 20%
    if overbought_syms and cash_pct < CASH_TARGET_PCT:
        cash_needed = equity * CASH_TARGET_PCT - cash
        if cash_needed > 5:
            print(f"\n  OB detected — need ${cash_needed:.2f} more cash to reach {CASH_TARGET_PCT*100:.0f}%")
            # Trim overbought positions proportionally
            trim_per_stock = cash_needed / len(overbought_syms)
            for symbol in overbought_syms:
                pos = positions.get(symbol)
                if pos is None:
                    continue
                pos_value = float(pos.market_value)
                price = float(pos.current_price)
                # Don't trim more than 50% of any single position
                max_trim = pos_value * 0.50
                trim_amount = min(trim_per_stock, max_trim)
                trim_qty = round(trim_amount / price, 2)

                if trim_qty > 0.01 and not dry_run:
                    try:
                        order = api.submit_order(symbol=symbol, qty=str(trim_qty), side="sell",
                                                 type="market", time_in_force="day")
                        actions_taken.append(
                            f"RSI-TRIM {trim_qty} {symbol} (RSI={rsi_data[symbol]:.0f}, "
                            f"raising ${trim_amount:.0f} cash)")
                        print(f"  >> RSI TRIM: Sold {trim_qty} {symbol} "
                              f"(RSI={rsi_data[symbol]:.0f}) to raise ${trim_amount:.2f}")
                    except Exception as e:
                        print(f"  >> RSI TRIM FAILED {symbol}: {e}")
                elif trim_qty > 0.01:
                    print(f"  >> DRY RUN: Would trim {trim_qty} {symbol} (RSI={rsi_data[symbol]:.0f})")

    # Phase 2: OVERSOLD — deploy cash into oversold stocks
    elif oversold_syms and cash > 50:
        deploy_total = cash - 10  # Keep $10 minimum
        deploy_per = deploy_total / len(oversold_syms)
        print(f"\n  OS detected — deploying ${deploy_total:.2f} into {len(oversold_syms)} oversold stocks")

        for symbol in oversold_syms:
            if deploy_per < 10:
                continue
            try:
                candles = fetch_ohlcv(symbol, "5d")
                price = candles[-1]["close"]
                qty = round(deploy_per / price, 2)
                if qty > 0.01 and not dry_run:
                    # Check if we already hold it (add to position) or new buy
                    order = api.submit_order(symbol=symbol, qty=str(qty), side="buy",
                                             type="market", time_in_force="day")
                    actions_taken.append(
                        f"RSI-DEPLOY {qty} {symbol} (RSI={rsi_data[symbol]:.0f}, "
                        f"deploying ${deploy_per:.0f})")
                    print(f"  >> RSI DEPLOY: Bought {qty} {symbol} "
                          f"(RSI={rsi_data[symbol]:.0f}) ${deploy_per:.2f}")
                elif qty > 0.01:
                    print(f"  >> DRY RUN: Would buy {qty} {symbol} (RSI={rsi_data[symbol]:.0f})")
            except Exception as e:
                print(f"  >> RSI DEPLOY FAILED {symbol}: {e}")
    else:
        if not overbought_syms and not oversold_syms:
            print(f"\n  All RSIs neutral — no cash reallocation needed")
        elif overbought_syms and cash_pct >= CASH_TARGET_PCT:
            print(f"\n  OB stocks detected but cash already >= {CASH_TARGET_PCT*100:.0f}% — no trim needed")

    # Phase 3: EXCESS CASH — deploy when cash > 25% and no overbought stocks
    # Re-check cash after any Phase 1/2 actions
    account = api.get_account()
    cash = float(account.cash)
    equity = float(account.equity)
    cash_pct = cash / equity if equity > 0 else 0
    EXCESS_CASH_THRESHOLD = 0.25  # Deploy when cash > 25%
    CASH_FLOOR_PCT = 0.10         # Always keep at least 10% cash

    if cash_pct > EXCESS_CASH_THRESHOLD and not overbought_syms:
        cash_floor = equity * CASH_FLOOR_PCT
        deploy_total = cash - cash_floor
        if deploy_total > 20:
            print(f"\n  EXCESS CASH: ${cash:.2f} ({cash_pct*100:.1f}%) > 25% threshold")
            print(f"  Deploying ${deploy_total:.2f} (keeping ${cash_floor:.2f} floor)")

            # Rank held positions by RSI ascending (lowest RSI = best entry)
            held_with_rsi = [(sym, rsi_data[sym]) for sym in positions if sym in rsi_data]
            held_with_rsi.sort(key=lambda x: x[1])  # Lowest RSI first

            if held_with_rsi:
                # Weight allocation: lowest RSI gets more
                # Simple approach: split proportionally, with lowest RSI getting 2x weight
                total_weight = 0
                weights = []
                for sym, rsi in held_with_rsi:
                    # Weight inversely proportional to RSI (lower RSI = higher weight)
                    w = max(1, (100 - rsi) / 50)  # RSI 30 → w=1.4, RSI 50 → w=1.0, RSI 70 → w=0.6
                    weights.append((sym, rsi, w))
                    total_weight += w

                for sym, rsi, w in weights:
                    alloc = deploy_total * (w / total_weight)
                    if alloc < 10:
                        continue
                    try:
                        price = float(positions[sym].current_price)
                        qty = round(alloc / price, 2)
                        if qty > 0.01 and not dry_run:
                            order = api.submit_order(symbol=sym, qty=str(qty), side="buy",
                                                     type="market", time_in_force="day")
                            actions_taken.append(
                                f"EXCESS-DEPLOY {qty} {sym} (RSI={rsi:.0f}, ${alloc:.0f})")
                            print(f"  >> EXCESS DEPLOY: Bought {qty} {sym} "
                                  f"(RSI={rsi:.0f}, weight={w:.1f}) ${alloc:.2f}")
                        elif qty > 0.01:
                            print(f"  >> DRY RUN: Would buy {qty} {sym} "
                                  f"(RSI={rsi:.0f}, weight={w:.1f}) ${alloc:.2f}")
                    except Exception as e:
                        print(f"  >> EXCESS DEPLOY FAILED {sym}: {e}")
            else:
                print(f"  No positions with RSI data to deploy into")
    elif cash_pct > EXCESS_CASH_THRESHOLD and overbought_syms:
        print(f"\n  Excess cash ({cash_pct*100:.1f}%) but OB stocks present — holding cash")

    print()
    if actions_taken:
        print(f"Actions taken: {len(actions_taken)}")
        for a in actions_taken:
            print(f"  {a}")
    else:
        print("No actions needed — all positions aligned with strategy signals.")

    # Log to file
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "active_trader.log", "a") as f:
        f.write(f"[{now}] equity=${equity:.2f} actions={len(actions_taken)} "
                f"{'DRY_RUN' if dry_run else 'LIVE'}\n")
        for a in actions_taken:
            f.write(f"  {a}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Active Trader")
    parser.add_argument("--dry-run", action="store_true", help="Check signals without trading")
    parser.add_argument("--status", action="store_true", help="Show positions only")
    args = parser.parse_args()
    run(dry_run=args.dry_run, status_only=args.status)
