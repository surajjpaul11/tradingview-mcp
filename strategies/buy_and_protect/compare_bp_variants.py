"""Compare Buy and Protect parameter variants."""
import sys
sys.path.insert(0, ".")
from strategies.buy_and_protect_strategy import fetch_ohlcv, run_buy_and_protect, apply_costs, calc_metrics

SYMBOLS = ["SPY", "DIA", "QQQ", "BTC-USD", "GOOGL", "NVDA", "AAPL", "PLTR", "WDC", "KGC"]
PERIOD = "2y"
INTERVAL = "1d"
COMMISSION = 0.1
SLIPPAGE = 0.05
CAPITAL = 10_000.0

VARIANTS = {
    "SMA50 / 5% / 2.5x (default)":  dict(ma_period=50,  rapid_decline_pct=5.0,  atr_spike_mult=2.5),
    "SMA100 / 7% / 2.5x":           dict(ma_period=100, rapid_decline_pct=7.0,  atr_spike_mult=2.5),
    "SMA200 / 8% / 3.0x":           dict(ma_period=200, rapid_decline_pct=8.0,  atr_spike_mult=3.0),
    "SMA200 / 10% / 3.0x":          dict(ma_period=200, rapid_decline_pct=10.0, atr_spike_mult=3.0),
    "No MA exit / 7% decline only":  dict(ma_period=9999, rapid_decline_pct=7.0, atr_spike_mult=999.0),
    "No MA exit / 10% decline only": dict(ma_period=9999, rapid_decline_pct=10.0, atr_spike_mult=999.0),
}

# Fetch data once
data = {}
for sym in SYMBOLS:
    try:
        data[sym] = fetch_ohlcv(sym, PERIOD, INTERVAL)
        bnh = round((data[sym][-1]["close"] - data[sym][0]["close"]) / data[sym][0]["close"] * 100, 2)
        data[sym + "_bnh"] = bnh
    except Exception as e:
        print(f"  {sym}: SKIP ({e})")

print(f"\n{'='*130}")
print(f"  BUY AND PROTECT — PARAMETER VARIANT COMPARISON (2y, daily)")
print(f"{'='*130}\n")

for name, kwargs in VARIANTS.items():
    rets = []
    bnhs = []
    beats = 0
    details = []
    for sym in SYMBOLS:
        if sym not in data:
            continue
        trades = run_buy_and_protect(data[sym], **kwargs)
        trades = apply_costs(trades, COMMISSION, SLIPPAGE)
        m = calc_metrics(trades, CAPITAL, INTERVAL)
        bnh = data[sym + "_bnh"]
        rets.append(m["total_return_pct"])
        bnhs.append(bnh)
        if m["total_return_pct"] >= bnh:
            beats += 1
        details.append(f"{sym}:{m['total_return_pct']:+.0f}%({m['total_trades']}t)")

    avg_r = sum(rets) / len(rets)
    avg_b = sum(bnhs) / len(bnhs)
    print(f"  {name:<35} | Avg: {avg_r:>+7.1f}% | B&H: {avg_b:>+7.1f}% | vs: {avg_r-avg_b:>+7.1f}% | Beat: {beats}/{len(rets)}")
    print(f"    {', '.join(details)}")
    print()

print(f"{'='*130}\n")
