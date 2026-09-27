"""
Compare Resistance Lines parameter variants vs Buy & Hold across a symbol basket.

Usage (from repo root):
  python strategies/resistance_lines/compare_resistance_lines.py              # 1d, 5y (defaults)
  python strategies/resistance_lines/compare_resistance_lines.py --interval 1h --period 2y
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resistance_lines_strategy import fetch_ohlcv, run_resistance_lines, apply_costs, calc_metrics  # noqa: E402

SYMBOLS = [
    "SPY", "DIA", "QQQ",
    "BTC-USD", "GOOGL", "MSFT", "META", "PLTR", "SIL", "PAAS", "UUUU", "UEC",
    "VXX", "WDC", "STX", "BE", "MELI", "NVTS", "SMR", "KGC", "NVDA", "MU", "AAPL",
]

VARIANTS = {
    "stop 0.5, zone 0.5":          {"stop_atr_mult": 0.5, "zone_atr_mult": 0.5},
    "stop 1.0, zone 0.5":          {"stop_atr_mult": 1.0, "zone_atr_mult": 0.5},
    "stop 1.5, zone 0.5":          {"stop_atr_mult": 1.5, "zone_atr_mult": 0.5},
    "stop 1.0, zone 0.5, touch 3": {"stop_atr_mult": 1.0, "zone_atr_mult": 0.5, "min_touches": 3},
    "stop 1.0, zone 0.5, RR 1.0":  {"stop_atr_mult": 1.0, "zone_atr_mult": 0.5, "min_rr": 1.0},
    "stop 1.0, zone 0.5, RR 2.0":  {"stop_atr_mult": 1.0, "zone_atr_mult": 0.5, "min_rr": 2.0},
    "stop 1.0, zone 0.75 (DEFAULT)": {"stop_atr_mult": 1.0, "zone_atr_mult": 0.75},
    "stop 1.0, zone 1.0":          {"stop_atr_mult": 1.0, "zone_atr_mult": 1.0},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--period", default="5y")
    ap.add_argument("--commission", type=float, default=0.1)
    ap.add_argument("--slippage", type=float, default=0.05)
    args = ap.parse_args()

    data, bnh = {}, {}
    for s in SYMBOLS:
        try:
            c = fetch_ohlcv(s, args.period, args.interval)
            data[s] = c
            bnh[s] = (c[-1]["close"] - c[0]["close"]) / c[0]["close"] * 100
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")

    print(f"\n{'='*112}")
    print(f"  RESISTANCE LINES variants — {args.interval}, {args.period}, {len(data)} symbols, "
          f"costs {2*(args.commission+args.slippage):.2f}% round trip")
    print(f"{'='*112}")
    print(f"  {'Variant':<30} {'AvgRet':>8} {'MedRet':>8} {'AvgB&H':>8} {'Beat':>6} {'Trades':>7} "
          f"{'WR':>6} {'AvgPF':>6} {'AvgDD':>8}")
    print("  " + "-" * 110)
    for name, params in VARIANTS.items():
        rets, pfs, dds, wrs, ntr, beat = [], [], [], [], 0, 0
        for s, c in data.items():
            t = apply_costs(run_resistance_lines(c, **params), args.commission, args.slippage)
            m = calc_metrics(t, 10_000.0, args.interval)
            rets.append(m["total_return_pct"])
            if m["total_trades"]:
                pfs.append(min(m["profit_factor"], 10))
                wrs.append(m["win_rate_pct"])
            dds.append(m["max_drawdown_pct"])
            ntr += m["total_trades"]
            beat += m["total_return_pct"] >= bnh[s]
        srt = sorted(rets)
        med = srt[len(srt) // 2]
        avg = lambda x: sum(x) / len(x) if x else 0  # noqa: E731
        print(f"  {name:<30} {avg(rets):>+7.2f}% {med:>+7.2f}% {avg(list(bnh.values())):>+7.2f}% "
              f"{beat:>3}/{len(data):<2} {ntr:>7} {avg(wrs):>5.1f}% {avg(pfs):>6.2f} {avg(dds):>7.2f}%")
    print(f"{'='*112}\n")

    # Per-symbol detail for the default variant
    print(f"  Per-symbol (DEFAULT variant):")
    for s, c in data.items():
        t = apply_costs(run_resistance_lines(c), args.commission, args.slippage)
        m = calc_metrics(t, 10_000.0, args.interval)
        print(f"    {s:<8} {m['total_return_pct']:>+8.2f}%  {m['total_trades']:>3}t  WR {m['win_rate_pct']:>5.1f}%  "
              f"PF {m['profit_factor']:>5}  DD {m['max_drawdown_pct']:>7.2f}%  | B&H {bnh[s]:>+8.2f}%")


if __name__ == "__main__":
    main()
