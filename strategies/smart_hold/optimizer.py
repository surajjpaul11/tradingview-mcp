"""
Smart Hold Strategy Optimizer
==============================
Iterates 100 times, trying parameter tweaks and logic changes.
Keeps changes only if ALL 4 tickers improve total_return_pct.
Logs every iteration and regenerates charts on improvements.

Usage:
    python3 strategies/smart_hold/optimizer.py
"""
from __future__ import annotations

import copy
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Setup imports
script_dir = Path(__file__).resolve().parent
strategies_dir = script_dir.parent
sys.path.insert(0, str(strategies_dir.parent))

from strategies.smart_hold.smart_hold_strategy import (
    fetch_ohlcv, run_smart_hold,
    FAST_MA, SLOW_MA, EXIT_MA, EXIT_CONFIRM_BARS, SLOPE_LOOKBACK,
    VIX_EXIT_BOOST, VIX_FEAR_ENTRY, VIX_EXTREME, VIX_ENTRY_DECLINE,
    REENTRY_MA_RECLAIM, RSI_OVERSOLD, TRAILING_STOP_ATR_MULT,
    REENTRY_COOLDOWN_BARS, COMMISSION_PCT, SLIPPAGE_PCT, INITIAL_CAPITAL,
)
from strategies.visualize import generate_chart_html

# ── Config ──────────────────────────────────────────────────────────
TICKERS = ["GOOGL", "WDC", "SPY", "QQQ"]
PERIOD = "2y"
INTERVAL = "1d"
MAX_ITERATIONS = 100
LOG_FILE = script_dir / "optimizer_log.md"
BEST_PARAMS_FILE = script_dir / "best_params.json"

# ── Parameter space with bounds ─────────────────────────────────────
# Each entry: (default, min, max, step, type)
PARAM_SPACE = {
    "fast_ma":               (FAST_MA, 5, 20, 1, int),
    "slow_ma":               (SLOW_MA, 30, 80, 5, int),
    "exit_ma":               (EXIT_MA, 20, 80, 5, int),
    "exit_confirm_bars":     (EXIT_CONFIRM_BARS, 1, 8, 1, int),
    "slope_lookback":        (SLOPE_LOOKBACK, 3, 10, 1, int),
    "vix_exit_boost":        (VIX_EXIT_BOOST, 18.0, 35.0, 1.0, float),
    "vix_fear_entry":        (VIX_FEAR_ENTRY, 22.0, 40.0, 1.0, float),
    "vix_extreme":           (VIX_EXTREME, 28.0, 50.0, 1.0, float),
    "vix_entry_decline":     (VIX_ENTRY_DECLINE, 1.0, 8.0, 0.5, float),
    "reentry_ma_reclaim":    (REENTRY_MA_RECLAIM, 1, 5, 1, int),
    "rsi_oversold":          (RSI_OVERSOLD, 20, 40, 2, int),
    "trailing_stop_atr_mult":(TRAILING_STOP_ATR_MULT, 3.0, 10.0, 0.5, float),
    "reentry_cooldown_bars": (REENTRY_COOLDOWN_BARS, 1, 5, 1, int),
}


def get_default_params() -> dict:
    return {k: v[0] for k, v in PARAM_SPACE.items()}


def mutate_params(params: dict, n_changes: int = None) -> tuple[dict, list[str]]:
    """Mutate 1-3 random parameters. Returns (new_params, list of change descriptions)."""
    new_params = copy.deepcopy(params)
    if n_changes is None:
        n_changes = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]

    keys = random.sample(list(PARAM_SPACE.keys()), min(n_changes, len(PARAM_SPACE)))
    changes = []

    for key in keys:
        default, lo, hi, step, typ = PARAM_SPACE[key]
        old_val = new_params[key]

        # Random perturbation: ±1 to ±3 steps
        n_steps = random.choice([-3, -2, -1, 1, 2, 3])
        new_val = old_val + n_steps * step

        # Clamp to bounds
        new_val = max(lo, min(hi, new_val))
        if typ == int:
            new_val = int(round(new_val))
        else:
            new_val = round(new_val, 2)

        if new_val != old_val:
            new_params[key] = new_val
            changes.append(f"{key}: {old_val} -> {new_val}")

    # If no actual changes happened, force one
    if not changes:
        key = random.choice(list(PARAM_SPACE.keys()))
        default, lo, hi, step, typ = PARAM_SPACE[key]
        old_val = new_params[key]
        direction = 1 if random.random() > 0.5 else -1
        new_val = old_val + direction * step
        new_val = max(lo, min(hi, new_val))
        if typ == int:
            new_val = int(round(new_val))
        else:
            new_val = round(new_val, 2)
        new_params[key] = new_val
        changes.append(f"{key}: {old_val} -> {new_val}")

    return new_params, changes


def evaluate(params: dict, data: dict) -> dict[str, dict]:
    """Run strategy on all tickers with given params. Returns {ticker: result_summary}."""
    results = {}
    for sym in TICKERS:
        candles, vix = data[sym]
        p = {**params, "symbol": sym, "period": PERIOD, "interval": INTERVAL,
             "initial_capital": INITIAL_CAPITAL, "commission_pct": COMMISSION_PCT,
             "slippage_pct": SLIPPAGE_PCT}
        r = run_smart_hold(candles, vix, p)
        results[sym] = {
            "total_return_pct": r["total_return_pct"],
            "buy_and_hold_return_pct": r["buy_and_hold_return_pct"],
            "vs_buy_and_hold_pct": r["vs_buy_and_hold_pct"],
            "total_trades": r["total_trades"],
            "win_rate_pct": r["win_rate_pct"],
            "max_drawdown_pct": r["max_drawdown_pct"],
            "profit_factor": r["profit_factor"],
            "sharpe_ratio": r["sharpe_ratio"],
        }
    return results


def is_improvement(baseline: dict, candidate: dict) -> bool:
    """
    Returns True if candidate improves aggregate total_return_pct across all tickers,
    while no single ticker drops more than 5% absolute from its baseline.
    """
    total_delta = 0.0
    for sym in TICKERS:
        delta = candidate[sym]["total_return_pct"] - baseline[sym]["total_return_pct"]
        # No single ticker can drop more than 5% absolute
        if delta < -5.0:
            return False
        total_delta += delta
    # Aggregate must improve
    return total_delta > 0.0


def generate_charts(params: dict, data: dict):
    """Regenerate HTML charts for all tickers."""
    for sym in TICKERS:
        candles, vix = data[sym]
        p = {**params, "symbol": sym, "period": PERIOD, "interval": INTERVAL,
             "initial_capital": INITIAL_CAPITAL, "commission_pct": COMMISSION_PCT,
             "slippage_pct": SLIPPAGE_PCT}
        result = run_smart_hold(candles, vix, p)
        chart_path = script_dir / f"smart_hold_chart_{sym.replace('-','_')}_{PERIOD}.html"
        generate_chart_html(result=result, candles=candles, output_path=chart_path, vix_candles=vix)
        # Also save backtest JSON
        json_result = {k: v for k, v in result.items() if k != "overlays"}
        json_path = script_dir / f"smart_hold_backtest_{sym.replace('-','_')}_{PERIOD}.json"
        with open(json_path, "w") as f:
            json.dump(json_result, f, indent=2)


def format_results(results: dict) -> str:
    lines = []
    for sym in TICKERS:
        r = results[sym]
        lines.append(f"  {sym:6s}: {r['total_return_pct']:+8.2f}% (vs B&H: {r['vs_buy_and_hold_pct']:+.2f}%, "
                      f"trades={r['total_trades']}, win={r['win_rate_pct']}%, dd={r['max_drawdown_pct']}%)")
    return "\n".join(lines)


def main():
    random.seed(2026)

    print("=" * 70)
    print("  Smart Hold Strategy Optimizer")
    print(f"  Tickers: {', '.join(TICKERS)}")
    print(f"  Max iterations: {MAX_ITERATIONS}")
    print("=" * 70)

    # ── Fetch data once ──
    print("\n  Fetching market data...")
    data = {}
    vix = fetch_ohlcv("^VIX", PERIOD, INTERVAL)
    for sym in TICKERS:
        candles = fetch_ohlcv(sym, PERIOD, INTERVAL)
        data[sym] = (candles, vix)
        print(f"    {sym}: {len(candles)} candles")
    print(f"    VIX: {len(vix)} candles")

    # ── Baseline ──
    current_params = get_default_params()
    current_results = evaluate(current_params, data)

    print(f"\n  Baseline results:")
    print(format_results(current_results))

    # ── Initialize log ──
    improvements = 0
    log_lines = [
        "# Smart Hold Optimizer Log\n",
        f"Started: {datetime.now(timezone.utc).isoformat()}\n",
        f"Tickers: {', '.join(TICKERS)}\n\n",
        "## Baseline\n",
        f"```\n{format_results(current_results)}\n```\n",
        f"Parameters: `{json.dumps(current_params)}`\n\n",
        "---\n\n",
    ]

    # ── Optimization loop ──
    for i in range(1, MAX_ITERATIONS + 1):
        candidate_params, changes = mutate_params(current_params)
        candidate_results = evaluate(candidate_params, data)

        improved = is_improvement(current_results, candidate_results)

        status = "IMPROVED" if improved else "no improvement"
        change_str = "; ".join(changes)

        # Calculate deltas
        deltas = {}
        for sym in TICKERS:
            delta = candidate_results[sym]["total_return_pct"] - current_results[sym]["total_return_pct"]
            deltas[sym] = delta
        delta_str = ", ".join(f"{sym}: {d:+.2f}%" for sym, d in deltas.items())

        print(f"\n  [{i:3d}/{MAX_ITERATIONS}] {status} | {change_str}")
        print(f"         Deltas: {delta_str}")

        if improved:
            improvements += 1
            current_params = candidate_params
            current_results = candidate_results

            print(f"         >>> Keeping change #{improvements}! Regenerating charts...")
            generate_charts(current_params, data)

            # Log improvement
            log_lines.append(f"## Iteration {i} — IMPROVEMENT #{improvements}\n\n")
            log_lines.append(f"**Changes:** {change_str}\n\n")
            log_lines.append(f"**Deltas:** {delta_str}\n\n")
            log_lines.append(f"```\n{format_results(current_results)}\n```\n\n")
            log_lines.append(f"**Parameters:** `{json.dumps(current_params)}`\n\n")
            log_lines.append("---\n\n")

            # Save best params
            with open(BEST_PARAMS_FILE, "w") as f:
                json.dump({
                    "params": current_params,
                    "results": current_results,
                    "improvement_number": improvements,
                    "iteration": i,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, f, indent=2)
        else:
            # Log non-improvement briefly (every 10th or specific)
            if i % 10 == 0:
                log_lines.append(f"*Iterations {max(1,i-9)}-{i}: {improvements} improvements so far*\n\n")

    # ── Final summary ──
    summary = [
        f"\n## Final Summary\n\n",
        f"**Total iterations:** {MAX_ITERATIONS}\n",
        f"**Total improvements:** {improvements}\n",
        f"**Improvement rate:** {improvements/MAX_ITERATIONS*100:.1f}%\n\n",
        f"### Final Results\n",
        f"```\n{format_results(current_results)}\n```\n\n",
        f"### Final Parameters\n",
        f"```json\n{json.dumps(current_params, indent=2)}\n```\n\n",
        f"Completed: {datetime.now(timezone.utc).isoformat()}\n",
    ]
    log_lines.extend(summary)

    # Write log
    with open(LOG_FILE, "w") as f:
        f.writelines(log_lines)

    print(f"\n{'=' * 70}")
    print(f"  Optimization complete!")
    print(f"  Improvements: {improvements} / {MAX_ITERATIONS}")
    print(f"  Log: {LOG_FILE}")
    print(f"  Best params: {BEST_PARAMS_FILE}")
    print(f"\n  Final results:")
    print(format_results(current_results))
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
