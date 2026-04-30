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
print(f"  VOLATILITY HARVESTER vs BUY & HOLD — Dev: 3.0 ATR, Stop: 2.0 ATR, Hold: 15, ER < 0.25, Vol: ON")
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
