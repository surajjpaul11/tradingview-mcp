"""Compare Buy and Protect vs B&H across all tickers."""
import sys
sys.path.insert(0, ".")
from strategies.buy_and_protect_strategy import fetch_ohlcv, run_buy_and_protect, apply_costs, calc_metrics

SYMBOLS = [
    "SPY", "DIA", "QQQ",
    "BTC-USD", "GOOGL", "MSFT", "META", "PLTR", "SIL", "PAAS", "UUUU", "UEC",
    "VXX", "WDC", "STX", "BE", "MELI", "NVTS", "SMR", "KGC", "NVDA", "MU", "AAPL",
]
PERIOD = "2y"
INTERVAL = "1d"
COMMISSION = 0.1
SLIPPAGE = 0.05
CAPITAL = 10_000.0

print(f"\n{'='*115}")
print(f"  BUY AND PROTECT vs BUY & HOLD — SMA(200), 8% decline, 3.0x ATR spike, 2+ signal confluence")
print(f"{'='*115}\n")

header = f"{'Symbol':<10} | {'B&P Ret':>9} {'Trades':>7} {'WR':>6} {'PF':>6} {'DD':>8} | {'B&H':>9} | {'vs B&H':>8} | {'Exits (dec/ma/vol/eod)'}"
print(header)
print("-" * 115)

totals_bp = []
totals_bnh = []
wins = 0

for sym in SYMBOLS:
    try:
        candles = fetch_ohlcv(sym, PERIOD, INTERVAL)
        bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
    except Exception as e:
        print(f"  {sym:<10} | SKIP: {e}")
        continue

    trades = run_buy_and_protect(candles)
    trades = apply_costs(trades, COMMISSION, SLIPPAGE)
    m = calc_metrics(trades, CAPITAL, INTERVAL)

    totals_bp.append(m["total_return_pct"])
    totals_bnh.append(bnh)
    vs = round(m["total_return_pct"] - bnh, 2)
    if m["total_return_pct"] >= bnh:
        wins += 1

    exits = f"{m['rapid_decline_exits']}/{m['ma_breakdown_exits']}/{m['volatility_spike_exits']}/{m['end_of_data_exits']}"

    print(f"  {sym:<10} | {m['total_return_pct']:>+8.2f}% {m['total_trades']:>6}t {m['win_rate_pct']:>5.1f}% {m['profit_factor']:>5.2f} {m['max_drawdown_pct']:>7.2f}% "
          f"| {bnh:>+8.2f}% | {vs:>+7.2f}% | {exits}")

print("-" * 115)
avg_bp = sum(totals_bp) / len(totals_bp)
avg_bnh = sum(totals_bnh) / len(totals_bnh)
print(f"  {'AVERAGE':<10} | {avg_bp:>+8.2f}%{'':>40} | {avg_bnh:>+8.2f}% | {avg_bp - avg_bnh:>+7.2f}% |")
print(f"  Beat B&H: {wins}/{len(totals_bp)} symbols")
print(f"{'='*115}\n")
