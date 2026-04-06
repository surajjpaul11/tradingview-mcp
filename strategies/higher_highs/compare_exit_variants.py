"""Compare exit mechanism variants for the Higher Highs strategy."""
import sys
sys.path.insert(0, ".")
from strategies.higher_highs_strategy import fetch_ohlcv, run_higher_highs, apply_costs, calc_metrics

SYMBOLS = ["SPY", "DIA", "QQQ"]
PERIOD = "2y"
INTERVAL = "1h"
COMMISSION = 0.1
SLIPPAGE = 0.05
CAPITAL = 10_000.0

VARIANTS = {
    "Baseline (5x ATR trail)": dict(trail_atr_mult=5.0),
    "V2: Trail after 2% profit": dict(trail_atr_mult=5.0, min_profit_to_trail=2.0),
    "V3: No trailing (struct+exhaust)": dict(trail_enabled=False),
    "V2+V3: No trail, activate at 2%": dict(trail_atr_mult=5.0, min_profit_to_trail=2.0, trail_enabled=True),
    "V2+V3a: No trail, activate at 3%": dict(trail_atr_mult=5.0, min_profit_to_trail=3.0, trail_enabled=True),
    "V2+V3b: No trail, activate at 5%": dict(trail_atr_mult=5.0, min_profit_to_trail=5.0, trail_enabled=True),
    "V2+V3c: 8x trail, activate at 3%": dict(trail_atr_mult=8.0, min_profit_to_trail=3.0, trail_enabled=True),
}

print(f"\n{'='*100}")
print(f"  EXIT MECHANISM COMPARISON — Higher Highs Strategy (long-only, pivot=5, tolerance=3%)")
print(f"{'='*100}\n")

# Fetch data once per symbol
data = {}
for sym in SYMBOLS:
    print(f"  Fetching {sym}...", end=" ", flush=True)
    data[sym] = fetch_ohlcv(sym, PERIOD, INTERVAL)
    bnh = round((data[sym][-1]["close"] - data[sym][0]["close"]) / data[sym][0]["close"] * 100, 2)
    data[sym + "_bnh"] = bnh
    print(f"{len(data[sym])} bars, B&H: {bnh:+.2f}%")

print(f"\n{'-'*100}")
print(f"{'Variant':<38} | {'SPY':>12} | {'DIA':>12} | {'QQQ':>12} | {'Avg':>8}")
print(f"{'':<38} | {'Ret / Trades':>12} | {'Ret / Trades':>12} | {'Ret / Trades':>12} |")
print(f"{'-'*100}")

for name, kwargs in VARIANTS.items():
    row_ret = []
    row_detail = []
    for sym in SYMBOLS:
        trades = run_higher_highs(
            data[sym], pivot_lookback=5, min_swings=3, htf_multiplier=4,
            long_only=True, struct_tolerance=0.03, **kwargs
        )
        trades = apply_costs(trades, COMMISSION, SLIPPAGE)
        m = calc_metrics(trades, CAPITAL, INTERVAL)
        ret = m["total_return_pct"]
        row_ret.append(ret)
        wr = m["win_rate_pct"]
        n = m["total_trades"]
        row_detail.append(f"{ret:+7.2f}% ({n:2d}t)")

    avg = sum(row_ret) / len(row_ret)
    print(f"  {name:<36} | {row_detail[0]:>12} | {row_detail[1]:>12} | {row_detail[2]:>12} | {avg:+7.2f}%")

print(f"{'-'*100}")
print(f"  {'Buy & Hold':<36}", end=" |")
for sym in SYMBOLS:
    bnh = data[sym + "_bnh"]
    print(f" {bnh:+7.2f}%      ", end=" |")
print()
print(f"{'='*100}\n")

# Detailed breakdown per variant
for name, kwargs in VARIANTS.items():
    print(f"\n--- {name} ---")
    for sym in SYMBOLS:
        trades = run_higher_highs(
            data[sym], pivot_lookback=5, min_swings=3, htf_multiplier=4,
            long_only=True, struct_tolerance=0.03, **kwargs
        )
        trades = apply_costs(trades, COMMISSION, SLIPPAGE)
        m = calc_metrics(trades, CAPITAL, INTERVAL)
        print(f"  {sym}: Return {m['total_return_pct']:+.2f}%  |  WR {m['win_rate_pct']}%  |  "
              f"Trades {m['total_trades']} (W:{m['winning_trades']} L:{m['losing_trades']})  |  "
              f"PF {m['profit_factor']}  |  DD {m['max_drawdown_pct']}%  |  "
              f"Exits: exhaust={m['exhaustion_exits']} trail={m['trailing_exits']} struct={m['structure_exits']} eod={m['end_of_data_exits']}")
