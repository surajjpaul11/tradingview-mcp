# Impact ranking and return tracking

The raw Yahoo candle snapshot was captured on 2026-09-21 from commit `8356ffe`, before code changes. The completed-bar baseline below excludes the still-open 2026-09-21 U.S. session and was reconstructed using the unmodified source at that commit. This report ranks the issues found in [PROJECT_STRATEGY_REVIEW.md](PROJECT_STRATEGY_REVIEW.md) by likely effect on capital, decisions, or reported performance. The impact ranking is an engineering judgment; it is not a measured strategy ranking.

| Rank | Issue and impact | Work in this pass | Remaining limitation |
|---:|---|---|---|
| **1** | **Order/signal safety.** A false signal or unprotected order can directly affect live capital. | Last-bar entries are exposed for nine in-process runners; end-of-data exits are filtered; Bitget spot short signals are blocked in live mode; protected Bitget spot orders now fail before the entry; Alpaca chooses OTO for one protective leg and bracket for two. | No durable signal/order idempotency, fill reconciliation, broker position sync, or complete exit-order workflow. Do not treat the live path as fully automated until these are built and paper tested. |
| **2** | **Return accounting and exposure.** The MCP engine treated every trade as an all-account position, distorting comparisons and rankings. | Shared return, trade log, and equity-curve calculations now use actual `shares` or `size_pct` where supplied. Short VWMA17 trades now carry `side=short`. | Risk and Sharpe calculations still use completed trades rather than a daily, marked portfolio. Open positions are not counted by every engine. A portfolio fill ledger is the next major task. |
| **3** | **Fill timing and gap prices.** Same-bar close fills and exact stop fills can produce returns unavailable in trading. | No cross-engine timing rewrite was attempted in this pass. | Define bar-close signal/next eligible fill semantics and model gaps, slippage, intrabar stop ordering, and partial fills consistently. Recalculate the baseline after that change. |
| **4** | **Future or shortened history in regime decisions.** An early decision could use a future volatility bucket or a mislabeled long channel. | Smart Hold now uses trailing historical ATR; Smart Hold RC fixes its bucket from history available before its first scored bar; Enhanced Channel uses full horizons and fixed Keltner lengths/warm-up. | Audit every standalone and Pine implementation for prefix invariance, especially current-bar channel/stop interaction and multi-timeframe aggregation. |
| **5** | **Invalid Donchian conditions.** The original channel included the tested bar, making its strict breakout/exit comparisons impossible on valid candles. | Compares current close to the previous completed channel. | Evaluate breakout execution at the next eligible fill and compare against an out-of-sample baseline. The corrected rule loses money on some tested symbols. |
| **6** | **Misleading walk-forward verdicts.** Inactive folds could be reported as robust, and losing folds could score favorably. | No-trade/negative-training folds are unscored; insufficient trades produce an explicit verdict; test evaluation retains preceding indicator history and excludes trades opened before the test slice. | This still is not training-only parameter optimization, and positions spanning a fold boundary are excluded. Use an untouched final holdout before interpreting robustness. |
| **7** | **Data consistency.** Independently fetched candles may differ by adjustment, session, and timestamp policy. | The before/after measurement uses identical, SHA-256 checked candle snapshots. MCP backtests and live signals now exclude an in-progress final candle, and the tracker does the same during a session. | Unify all providers and engines behind validated, versioned OHLCV snapshots with explicit adjustment and timezone policies. |
| **8** | **Standalone, MCP, and Pine divergence.** Strategy names can have different defaults, exits, and trade rules. | Documented in the project review and pinned reproducible MCP measurements. | Make one strategy registry and parity tests; then use the same engine/configuration from CLI, MCP, and UI. |
| **9** | **Installation/dashboard reproducibility.** Dynamic files, static assets, and stored reports depend on a source checkout. | No package layout rewrite was made. | Package resources, test an installed wheel outside the checkout, and store runs separately from executable source. |
| **10** | **Optimization and documentation drift.** Winner selection on the same symbols and stale descriptions can mislead research decisions. | Stored all 70 rows, including losses and inactive strategies, and avoided winner-only reporting. | Register hypotheses, use untouched evaluation sets, and generate docs from implemented defaults. |

## Frozen measurement

The measurement baseline is [returns_baseline_completed_2026-09-18.json](returns_baseline_completed_2026-09-18.json). It contains daily OHLCV and the pre-change return for each of 14 MCP strategies on **GOOGL, AAPL, MELI, SPY, and NVDA**: 499 completed bars per symbol, 2024-09-23 through 2026-09-18. Settings: $10,000 starting capital, 0.1% commission and 0.05% slippage per side. The raw [September 21 capture](returns_baseline_2026-09-21.json) was fetched before code changes; its in-progress final candle was removed, and the unmodified original worktree produced the completed-bar baseline. Each symbol's frozen candles have a SHA-256 hash. [Nasdaq's schedule](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule) gives the regular U.S. equity close as 4:00 p.m. ET; the snapshot was captured earlier that day.

The after measurement is [returns_comparison_completed_2026-09-18.json](returns_comparison_completed_2026-09-18.json). All 70 strategy/symbol rows are present. The [tracker](../scripts/strategy_return_tracker.py) checks the frozen data hashes and can regenerate the comparison without network access:

```bash
PYTHONPATH=src python3 scripts/strategy_return_tracker.py compare \
  --snapshot docs/returns_baseline_completed_2026-09-18.json \
  --output docs/returns_comparison_completed_2026-09-18.json
```

The figures below are **backtested total returns**, not actual realized profit. “Change” means after minus before in percentage points. A positive change after a bug fix means the corrected model reports more return on these historical candles; it does not prove an improved trading strategy. An unchanged return often means the fix affected live behavior, validation, or an untraded branch rather than these completed trades.

| Symbol | Buy and hold | Donchian before → after | VWMA17 before → after | Enhanced Lines before → after | Enhanced Channel before → after |
|---|---:|---:|---:|---:|---:|
| GOOGL | 115.97% | 0.00% → 60.21% | 28.37% → **−5.42%** | −62.13% → −15.09% | 6.21% → 17.25% |
| AAPL | 48.42% | 0.00% → 7.70% | 24.17% → **−0.24%** | 0.00% → 0.00% | 8.91% → 14.72% |
| MELI | −14.99% | 0.00% → **−45.65%** | −5.29% → −11.78% | 4.01% → 0.68% | −12.41% → −14.12% |
| SPY | 33.71% | 0.00% → 7.04% | −8.85% → −0.90% | −3.60% → −2.50% | −1.53% → 1.93% |
| NVDA | 91.18% | 0.00% → **−18.35%** | −32.75% → −25.30% | −0.99% → −0.33% | −19.17% → 2.27% |

The other ten registered strategies have unchanged measured returns on all five symbols. Full per-strategy values, trade counts, and before/after differences are in the JSON. The largest interpretation change is VWMA17: previously, MCP labeled shorts with `short=True`, while its cost/return calculation recognized only `side="short"`. The prior return therefore counted favorable short moves in the wrong direction. Enhanced Lines changed because the MCP previously compounded every partial trade over the whole $10,000 account. Donchian's old zero was a code defect, not a flat strategy result.

Smart Hold and Smart Hold RC are standalone strategies, outside the 14-strategy registry. Their pre-change runs were reconstructed from the exact Git commit recorded before edits and evaluated on the same frozen ticker candles. A VIX series was fetched once, trimmed to completed sessions, and saved with its hash in [smart_hold_comparison_completed_2026-09-18.json](smart_hold_comparison_completed_2026-09-18.json); it was supplied to both code versions. This is a reconstructed pre-change baseline, distinct from the MCP baseline captured before editing. The [comparison script](../scripts/compare_smart_hold.py) reruns offline using the saved VIX series.

| Symbol | Smart Hold before → after | Smart Hold RC before → after |
|---|---:|---:|
| GOOGL | **165.90% → 119.99%** | 97.12% → 102.28% |
| AAPL | 13.50% → 9.60% | 24.46% → 24.46% |
| MELI | −24.42% → −18.83% | 14.36% → 14.36% |
| SPY | 68.67% → 68.67% | 36.96% → 36.96% |
| NVDA | 98.02% → 98.02% | 57.62% → 57.62% |

The 45.91-point reduction for GOOGL Smart Hold is consistent with removing future volatility information from early decisions. It should be treated as a credibility correction, not a deterioration caused by the current market. Further validation should compare trailing-window choices on untouched dates and symbols.

## Decision from these measurements

The return changes are mixed. GOOGL and AAPL have several higher corrected returns, while MELI's Donchian and Enhanced Channel results are lower. These fixes improve the accuracy of the measurement and the safety of signal handling; they do **not** establish that overall trading performance improved. The next meaningful performance comparison should follow a consistent fill/portfolio model and use unseen dates and symbols.

Offline checks: nine new regression tests pass; the existing SQLite trade database test passes. All 70 after rows matched the MCP `compare_strategies` API on frozen candles. No broker orders were submitted. Live broker behavior was checked with test doubles only. Smart Hold and Smart Hold RC were compared separately; other standalone-only strategies and Pine parity were not rerun.
