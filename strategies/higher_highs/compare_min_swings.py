"""Compare min_swings=2 vs min_swings=3 across all tickers."""
import sys
sys.path.insert(0, ".")
from strategies.higher_highs_strategy import fetch_ohlcv, run_higher_highs, apply_costs, calc_metrics

SYMBOLS = [
    "BTC-USD", "GOOGL", "MSFT", "META", "PLTR", "SIL", "PAAS", "UUUU", "UEC",
    "VXX", "WDC", "STX", "BE", "MELI", "NVTS", "SMR", "KGC", "NVDA", "MU",
    "AAPL", "SPY", "DIA", "QQQ",
]
PERIOD = "2y"
INTERVAL = "1h"
COMMISSION = 0.1
SLIPPAGE = 0.05
CAPITAL = 10_000.0

print(f"\n{'='*110}")
print(f"  MIN_SWINGS COMPARISON: 2 vs 3 — Higher Highs (long-only, pivot=5, tol=3%, V3 exits)")
print(f"{'='*110}\n")

header = f"{'Symbol':<10} | {'min=2 Ret':>10} {'Trades':>7} {'WR':>6} {'PF':>6} | {'min=3 Ret':>10} {'Trades':>7} {'WR':>6} {'PF':>6} | {'B&H':>8} | {'Best':>6}"
print(header)
print("-" * 110)

totals = {2: [], 3: [], "bnh": []}

for sym in SYMBOLS:
    try:
        candles = fetch_ohlcv(sym, PERIOD, INTERVAL)
        bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
    except Exception as e:
        print(f"  {sym:<10} | SKIP: {e}")
        continue

    results = {}
    for ms in (2, 3):
        trades = run_higher_highs(
            candles, pivot_lookback=5, min_swings=ms, htf_multiplier=4,
            long_only=True, struct_tolerance=0.03, trail_enabled=False,
        )
        trades = apply_costs(trades, COMMISSION, SLIPPAGE)
        m = calc_metrics(trades, CAPITAL, INTERVAL)
        results[ms] = m

    for ms in (2, 3):
        totals[ms].append(results[ms]["total_return_pct"])
    totals["bnh"].append(bnh)

    best = "ms=2" if results[2]["total_return_pct"] >= results[3]["total_return_pct"] else "ms=3"

    print(f"  {sym:<10} | {results[2]['total_return_pct']:>+9.2f}% {results[2]['total_trades']:>6}t {results[2]['win_rate_pct']:>5.1f}% {results[2]['profit_factor']:>5.2f} "
          f"| {results[3]['total_return_pct']:>+9.2f}% {results[3]['total_trades']:>6}t {results[3]['win_rate_pct']:>5.1f}% {results[3]['profit_factor']:>5.2f} "
          f"| {bnh:>+7.2f}% | {best}")

print("-" * 110)
avg2 = sum(totals[2]) / len(totals[2])
avg3 = sum(totals[3]) / len(totals[3])
avgb = sum(totals["bnh"]) / len(totals["bnh"])
wins2 = sum(1 for a, b in zip(totals[2], totals[3]) if a >= b)
wins3 = len(totals[2]) - wins2
print(f"  {'AVERAGE':<10} | {avg2:>+9.2f}%{'':>27} | {avg3:>+9.2f}%{'':>27} | {avgb:>+7.2f}% |")
print(f"  min=2 wins: {wins2}/{len(totals[2])}  |  min=3 wins: {wins3}/{len(totals[3])}")
print(f"{'='*110}\n")
