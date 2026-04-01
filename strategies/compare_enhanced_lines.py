"""Compare Enhanced Lines vs Straight Line vs B&H across symbols."""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from enhanced_lines_strategy import fetch_ohlcv, run_enhanced_lines, apply_costs, calc_metrics
from straight_line_strategy import run_straight_line, apply_costs as sl_apply_costs, calc_metrics as sl_calc_metrics

SYMBOLS = ["SPY", "QQQ", "BTC-USD", "AAPL", "NVDA", "GDX", "DIA"]
PERIOD = "2y"
INTERVAL = "1h"
COMMISSION = 0.1
SLIPPAGE = 0.05
CAPITAL = 10_000.0

print(f"\n{'='*120}")
print(f"  ENHANCED LINES vs STRAIGHT LINE vs BUY & HOLD — Period: {PERIOD}, Interval: {INTERVAL}")
print(f"{'='*120}\n")

header = (
    f"{'Symbol':<10} | {'Enh Ret':>9} {'Enh Trades':>11} | "
    f"{'SL Ret':>9} {'SL Trades':>10} | "
    f"{'B&H':>9} | {'Enh vs B&H':>11}"
)
print(header)
print("-" * 120)

totals_enh = []
totals_sl = []
totals_bnh = []
enh_wins = 0

for sym in SYMBOLS:
    try:
        candles = fetch_ohlcv(sym, PERIOD, INTERVAL)
        bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
    except Exception as e:
        print(f"  {sym:<10} | SKIP: {e}")
        continue

    # Enhanced Lines
    try:
        enh_trades = run_enhanced_lines(candles)
        enh_trades = apply_costs(enh_trades, COMMISSION, SLIPPAGE)
        enh_m = calc_metrics(enh_trades, CAPITAL, INTERVAL)
    except Exception as e:
        print(f"  {sym:<10} | Enhanced SKIP: {e}")
        continue

    # Straight Line
    try:
        sl_trades = run_straight_line(candles)
        sl_trades = sl_apply_costs(sl_trades, COMMISSION, SLIPPAGE)
        sl_m = sl_calc_metrics(sl_trades, CAPITAL, INTERVAL)
    except Exception as e:
        sl_m = {"total_return_pct": 0.0, "total_trades": 0}

    totals_enh.append(enh_m["total_return_pct"])
    totals_sl.append(sl_m["total_return_pct"])
    totals_bnh.append(bnh)

    vs_bnh = round(enh_m["total_return_pct"] - bnh, 2)
    if enh_m["total_return_pct"] >= bnh:
        enh_wins += 1

    print(
        f"  {sym:<10} | {enh_m['total_return_pct']:>+8.2f}% {enh_m['total_trades']:>10}t | "
        f"{sl_m['total_return_pct']:>+8.2f}% {sl_m['total_trades']:>9}t | "
        f"{bnh:>+8.2f}% | {vs_bnh:>+10.2f}%"
    )

print("-" * 120)
if totals_enh:
    avg_enh = sum(totals_enh) / len(totals_enh)
    avg_sl = sum(totals_sl) / len(totals_sl)
    avg_bnh = sum(totals_bnh) / len(totals_bnh)
    print(
        f"  {'AVERAGE':<10} | {avg_enh:>+8.2f}%{'':>23} | "
        f"{avg_sl:>+8.2f}%{'':>22} | "
        f"{avg_bnh:>+8.2f}% | {avg_enh - avg_bnh:>+10.2f}%"
    )
    print(f"  Enhanced Beat B&H: {enh_wins}/{len(totals_enh)} symbols")
print(f"{'='*120}\n")
