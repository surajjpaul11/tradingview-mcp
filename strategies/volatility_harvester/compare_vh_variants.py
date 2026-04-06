"""Compare Volatility Harvester parameter variants."""
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

VARIANTS = [
    {"label": "V0: BASELINE (dev=2.0, stop=3.0, hold=20, L+S)",
     "deviation_mult": 2.0, "stop_mult": 3.0, "max_hold_bars": 20, "long_only": False},
    {"label": "V1: Best combo L+S (dev=3.0, stop=1.5, hold=10)",
     "deviation_mult": 3.0, "stop_mult": 1.5, "max_hold_bars": 10, "long_only": False},
    {"label": "V2: Long-only baseline (dev=2.0, stop=3.0, hold=20)",
     "deviation_mult": 2.0, "stop_mult": 3.0, "max_hold_bars": 20, "long_only": True},
    {"label": "V3: Long-only tight (dev=2.5, stop=1.5, hold=10)",
     "deviation_mult": 2.5, "stop_mult": 1.5, "max_hold_bars": 10, "long_only": True},
    {"label": "V4: Long-only wide (dev=3.0, stop=1.5, hold=10)",
     "deviation_mult": 3.0, "stop_mult": 1.5, "max_hold_bars": 10, "long_only": True},
    {"label": "V5: Long-only wider (dev=3.0, stop=2.0, hold=10)",
     "deviation_mult": 3.0, "stop_mult": 2.0, "max_hold_bars": 10, "long_only": True},
    {"label": "V6: Long-only widest (dev=3.0, stop=2.0, hold=15)",
     "deviation_mult": 3.0, "stop_mult": 2.0, "max_hold_bars": 15, "long_only": True},
    {"label": "V7: Long-only deep (dev=3.5, stop=2.0, hold=10)",
     "deviation_mult": 3.5, "stop_mult": 2.0, "max_hold_bars": 10, "long_only": True},
]

# Prefetch all data
print("Fetching data...", flush=True)
all_data = {}
for sym in SYMBOLS:
    try:
        candles = fetch_ohlcv(sym, PERIOD, INTERVAL)
        bnh = round((candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100, 2)
        all_data[sym] = (candles, bnh)
    except Exception as e:
        print(f"  SKIP {sym}: {e}")

print(f"\n{'='*120}")
print(f"  VOLATILITY HARVESTER — PARAMETER VARIANT COMPARISON ({len(all_data)} symbols, {PERIOD}, {INTERVAL})")
print(f"{'='*120}\n")

for v in VARIANTS:
    label = v["label"]
    params = {k: v[k] for k in ("deviation_mult", "stop_mult", "max_hold_bars", "long_only")}

    totals = []
    totals_bnh = []
    wins = 0
    total_trades = 0
    total_wr = []
    profitable = 0

    for sym, (candles, bnh) in all_data.items():
        trades = run_volatility_harvester(candles, **params)
        trades = apply_costs(trades, COMMISSION, SLIPPAGE)
        m = calc_metrics(trades, CAPITAL, INTERVAL)

        totals.append(m["total_return_pct"])
        totals_bnh.append(bnh)
        total_trades += m["total_trades"]
        if m["total_trades"] > 0:
            total_wr.append(m["win_rate_pct"])
        if m["total_return_pct"] >= bnh:
            wins += 1
        if m["total_return_pct"] > 0:
            profitable += 1

    avg_ret = sum(totals) / len(totals) if totals else 0
    avg_bnh = sum(totals_bnh) / len(totals_bnh) if totals_bnh else 0
    avg_wr = sum(total_wr) / len(total_wr) if total_wr else 0

    print(f"  {label}")
    print(f"    Avg Ret: {avg_ret:+.2f}%  |  vs B&H: {avg_ret - avg_bnh:+.2f}%  |  Beat B&H: {wins}/{len(totals)}  |  Profitable: {profitable}/{len(totals)}  |  WR: {avg_wr:.1f}%  |  Trades: {total_trades}")
    print()

print(f"{'='*120}\n")
