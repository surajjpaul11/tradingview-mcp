"""
Comparison Script: Liquidity & Capitulation Strategy vs Buy & Hold
Across Major Equity Indices, Mega-Caps, and Crypto.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from strategies.liquidity_exhaustion.liquidity_exhaustion_strategy import run_backtest

SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "BTC-USD"]


def main():
    parser = argparse.ArgumentParser(description="Compare Liquidity Strategy vs Buy & Hold")
    parser.add_argument("--period", default="5y", help="Lookback period (default: 5y)")
    parser.add_argument("--enable-short", action="store_true", help="Enable short trades")
    args = parser.parse_args()

    print(f"\nEvaluating Liquidity & Capitulation Strategy vs B&H ({args.period})...\n")
    print(f"{'Symbol':<9} | {'Trades':<6} | {'Win%':<6} | {'Strategy Ret':<13} | {'Max DD':<9} | {'B&H Ret':<11} | {'Alpha vs B&H':<12}")
    print("-" * 80)

    for sym in SYMBOLS:
        try:
            res = run_backtest(symbol=sym, period=args.period, enable_short=args.enable_short)
            print(
                f"{res['symbol']:<9} | "
                f"{res['total_trades']:<6} | "
                f"{res['win_rate_pct']:<5.1f}% | "
                f"{res['total_return_pct']:>+11.2f}% | "
                f"{res['max_drawdown_pct']:>7.2f}% | "
                f"{res['buy_and_hold_return_pct']:>+9.2f}% | "
                f"{res['vs_buy_and_hold_pct']:>+11.2f}%"
            )
        except Exception as e:
            print(f"{sym:<9} | ERROR: {e}")

    print("-" * 80)


if __name__ == "__main__":
    main()
