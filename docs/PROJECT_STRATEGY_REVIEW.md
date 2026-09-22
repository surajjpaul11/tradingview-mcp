# Project and strategy review

Reviewed 2026-09-21 at commit `8356ffe`. Worktree: `/Users/spaul11/Projects/codex`; branch: `codex/codex`.

## Assessment

This is a useful trading research workbench with broad strategy coverage, inspectable Python implementations, Pine visualizations, MCP tools, a dashboard, and broker adapters. Its main weakness is that research, accounting, signal detection, and execution do not yet share one consistent model. Fixing that foundation is more valuable than adding indicators or further optimizing reported returns.

The review found 23 named implemented strategy families: 14 exposed through the MCP registry and nine additional standalone families. There are also an EMA parameter sweep, ten Hermes variants, three iterative backtester variants, and a regime-selection research folder. “Implemented” does not mean deployed: this review did not inspect broker accounts or establish which strategies currently hold positions.

Scope: static implementation review plus deterministic offline reproductions. Existing performance reports were not independently rerun against market history. Recommendations below are engineering and research priorities, not evidence that a strategy will outperform. No orders were submitted and no strategy code was changed.

## How the project fits together

- **Interfaces:** `src/tradingview_mcp/server.py` exposes MCP research and trading tools; `src/tradingview_mcp/ui/server.py` serves the FastAPI dashboard.
- **Data:** TradingView screening/technical analysis, Yahoo OHLCV, RSS news, and Reddit sentiment. Standalone strategies duplicate fetching and indicator code.
- **Research:** `backtest_service.py` supplies the 14-strategy registry, comparisons, trade logs, metrics, and temporal splits. More advanced strategies live outside the installable `src` package.
- **Trading:** `signal_service.py` infers signals by comparing backtest trade lists; `execution_service.py` routes orders to Bitget spot or Alpaca; SQLite records trades and exits.
- **Artifacts:** Strategy folders contain Python, selected Pine implementations, JSON results, HTML charts, and optimization notes. Some dashboard choices come from historical database records rather than the executable registry.

Useful foundations to retain: mostly understandable Python logic, broker adapter boundaries, dry-run defaults, SQLite WAL/foreign keys, explicit pivot confirmation timestamps in several engines, and modular signal registries in Smart Hold and Hyperbolic Runner.

## Findings to address first

### 1. P1 — Live signals do not reliably represent entries or exits

Evidence: [signal_service.py](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/signal_service.py:80), [RSI runner](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/backtest_service.py:103), [Buy and Protect finalization](/Users/spaul11/Projects/codex/strategies/buy_and_protect/buy_and_protect_strategy.py:290).

The signal service compares completed-trade lists. RSI and several other engines return no record for an open position, so a last-bar entry disappears. Conversely, engines that force-close at the end of any input history create artificial latest-bar exits. Both cases were reproduced offline: a final RSI value of 0 produced `none`; a steadily rising Buy and Protect series produced `exit` solely because the input ended.

**Improve:** return explicit signal events and position state. Make research liquidation an optional reporting operation, never a trading signal. Process only finalized bars, persist the last processed bar, and add one-event-per-bar idempotency. Test entry, hold, exit, reversal, partial exit, and restart behavior on the actual engines.

### 2. P1 — Shared accounting ignores fractional sizing and open risk

Evidence: [trade log](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/backtest_service.py:619), [metrics](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/backtest_service.py:669), [Enhanced Lines accounting](/Users/spaul11/Projects/codex/strategies/enhanced_lines/enhanced_lines_strategy.py:814).

The MCP engine compounds every trade return over the entire account, ignoring `shares` and overlapping/partial lots. A one-share purchase at $100 sold at $110 with $10,000 initial capital becomes $11,000 through MCP, versus $10,010 through the standalone shares-aware calculator. This directly undermines comparisons involving Enhanced Lines.

Drawdown is measured at exits, so an intra-trade crash followed by recovery can disappear. Sharpe annualizes irregular trade returns as though each were a bar return. Calmar uses total return rather than annualized return. Several engines omit positions still open at the end; others force-liquidate them, creating inconsistent comparisons. Trade-log formatting also drops side, size, and reasons.

**Improve:** one cash/position/fill ledger, portfolio valuation every bar, explicit costs and exposures, retained open positions, and consistent end-of-test liquidation policy. Derive periodic returns, CAGR, drawdown, and Sharpe from the same equity series with the correct asset calendar. Rebuild rankings only afterward.

### 3. P1 — Donchian cannot enter on valid OHLC data

Evidence: [entry and exit conditions](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/backtest_service.py:249), [channel calculation](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/indicators_calc.py:251).

The upper channel includes the bar whose high is tested. That high cannot be strictly greater than its own window maximum. The exit similarly compares close below a window minimum that includes the current low, impossible for valid candles. A rising 300-bar series returned zero trades, consistent with the mathematical defect.

**Improve:** compare against the preceding completed channel, specify high-break versus close-break entry semantics, and execute on the next eligible price. Test breakout, reversal, and equality cases.

### 4. P1 — Walk-forward verdicts give false confidence

Evidence: [walk_forward_backtest](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/backtest_service.py:879).

Zero train return and zero test return score 1.0, so the broken Donchian runner received `ROBUST` with zero out-of-sample trades. When both returns are negative, larger test losses can increase the score. Test windows start without prior indicator history; defaults needing 100–200 bars can remain inactive. There is no train-only parameter fitting or selection step, so this is a segmented fixed-strategy test rather than a full optimization-and-validation workflow.

**Improve:** use “insufficient evidence” for inactive folds, carry historical warm-up into the test without scoring it, normalize time horizons, and use training-only selection followed by untouched evaluation. Record all attempted variants and require sufficient observations; do not infer robustness from a raw return ratio.

### 5. P1 — Execution lacks a complete order lifecycle

Evidence: [Bitget protective orders](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/execution_service.py:116), [execution and logging](/Users/spaul11/Projects/codex/src/tradingview_mcp/core/services/execution_service.py:369), [signal-to-order path](/Users/spaul11/Projects/codex/src/tradingview_mcp/server.py:3198).

Bitget submits the market order first, then independent stop/limit orders. Protective-order exceptions are returned inside an otherwise successful result; no sibling cancellation or fill reconciliation is implemented. Order logging uses requested quantity and quoted price instead of confirmed fills. There is no stable client-order idempotency key. The combined signal-to-order tool ignores `exit` signals and maps `short` to a sell even though Bitget is configured for spot, where selling inventory is not opening a short.

**Improve:** separate order intent, acceptance, partial fill, fill, rejection, and cancellation. Reconcile broker positions; support close/reduce instructions explicitly; validate instrument precision, buying power, and protective prices. Add account exposure limits and an emergency stop. Keep research/paper/live records and capabilities distinct. For Alpaca, select bracket versus one-trigger orders according to which protective legs are supplied; official bracket requirements are documented in [Alpaca order documentation](https://docs.alpaca.markets/us/docs/orders-at-alpaca).

### 6. P1 — Some strategy decisions depend on future sample length/data

Evidence: [Smart Hold volatility bucket](/Users/spaul11/Projects/codex/strategies/smart_hold/smart_hold_strategy.py:238), [Smart Hold RC bucket](/Users/spaul11/Projects/codex/strategies/smart_hold_rc/smart_hold_rc_strategy.py:188), [Enhanced Channel warm-up](/Users/spaul11/Projects/codex/strategies/enhanced_channel/enhanced_channel_strategy.py:347), [Keltner periods](/Users/spaul11/Projects/codex/strategies/enhanced_channel/enhanced_channel_strategy.py:231).

Smart Hold variants calculate their volatility classification from the first 100 bars, then apply it while trading earlier bars. Enhanced Channel varies initial warm-up with total input length, and its optional Keltner periods also depend on total length. Extending history can therefore change earlier behavior.

**Improve:** estimate from pre-test history or a trailing window, freeze parameters before scoring, and make warm-up independent of the future input length. Add prefix-invariance tests: extending a dataset must not change prior eligible signals or fills, excluding intentional final liquidation records.

### 7. P2 — Execution timing differs across engines and Pine

Many Python runners use the completed bar’s close both to compute a signal and as its fill. VWMA17 fills stops exactly at the threshold even through a gap. Scalping checks stops against close alone. Enhanced Channel can update a stop using the current completed channel and test it against that same bar’s earlier low/high in intrabar-stop modes.

**Improve:** specify signal time, earliest fill time, gap fills, and stop/target ordering. Use prior-bar stop levels for intrabar testing, or evaluate with finer data. A same-close fill requires an explicit supported execution assumption. TradingView’s default emulator fills a new order on the next available tick; see [TradingView strategy documentation](https://www.tradingview.com/pine-script-docs/concepts/strategies/). Match Pine settings and export comparable event traces before claiming parity.

## Review of each named strategy

Weaknesses marked “research risk” are hypotheses to evaluate, not demonstrated trading losses. Shared accounting/timing findings above apply in addition to these strategy-specific notes. MCP means present in `_STRATEGY_MAP`; standalone means outside that registry.

| Strategy / implementation | What it does | Weakness and improvement scope |
|---|---|---|
| **RSI — MCP**, `backtest_service.py:103` | Buys RSI below 40; exits above 60. | Open entries disappear from live detection. No independent loss/time exit. Research risk: oversold can persist during a decline. Fix state handling; compare a trend gate and time/risk limit against the unfiltered baseline. |
| **Bollinger — MCP**, `backtest_service.py:119` | Buys below lower band; exits above middle band. | Same open-state issue; no separate downside control. Research risk: fading a persistent trend. Test band-width/regime filters and holding limits; measure missed upside as well as reduced losses. |
| **MACD — MCP**, `backtest_service.py:135` | Long-only MACD crossover. | Lag and repeated crosses are research risks; no open mark-to-market. Standardize fills, then test a small deadband or trend filter with turnover and missed-entry reporting. |
| **EMA Cross — MCP**, `backtest_service.py:212` | Long-only EMA20/50 crossover. | Documentation implies short behavior in places, but this runner exits to cash. Few long trades can make estimates unstable. Clarify sides; test a small, predeclared parameter neighborhood with exposure-matched benchmarks. |
| **Supertrend — MCP**, `backtest_service.py:230` | Long-only ATR trend flips. | Same documentation/state mismatch. Research risk: churn in ranges. Verify indicator parity on known candles and test multiplier sensitivity, gap behavior, and regime-conditioned turnover. |
| **Donchian — MCP**, `backtest_service.py:249` | Intended channel breakout. | Confirmed impossible entry/exit conditions. Repair indexing before any optimization or ranking. Then evaluate separate entry/exit windows and volatility sizing. |
| **VWMA17 — MCP + standalone**, `strategies/vwma17/` | Volume-weighted crossover; ER switches SMA filter; ATR stop/target. | Exact-threshold gap fills, discarded open positions, and duplicated Python implementations. Hard ER switching may churn; fixed target may truncate trends. Unify implementation, make fills gap-aware, and compare hysteresis/trailing exits via isolated experiments. |
| **Higher Highs — MCP + standalone**, `strategies/higher_highs/` | Confirmed higher/lower swings and multi-timeframe pullbacks. | MCP defaults to two swings, multiplier eight, and single-structure-break exits; standalone adds tolerance, exhaustion, optional trailing, and different defaults. Bar-count aggregation is not session-aware. Use one configuration and timestamp-aware completed HTF bars; ablate exhaustion components. |
| **Buy and Protect — MCP + standalone**, `strategies/buy_and_protect/` | Starts long; exits when at least two danger conditions agree. | Artificial final exits become live signals. SMA200 protection is unavailable early without prehistory; two-of-three gating can delay gradual-decline exits. Warm up before scored entry; test crash speed and re-entry delay separately. Correct stale header claiming any one danger signal exits. |
| **Straight Line — MCP + standalone**, `strategies/straight_line/` | Trades confirmed trendline breaks. | Pivot/touch confirmation delays entries; fixed percentage tolerance changes meaning across volatility. No independent disaster-stop layer. Test ATR-scaled tolerance, line age, and a separate risk limit while preserving confirmed-pivot timing. |
| **Enhanced Lines — MCP + standalone/Pine**, `strategies/enhanced_lines/` | Channel bounces with volume sizing and FIFO partial exits. | Confirmed MCP sizing/accounting incompatibility. Refitted boundaries and volume-driven sizing add research degrees of freedom. First unify lot accounting; then test frozen-versus-refitted lines and cap position risk independently of volume. |
| **EMA21 — MCP + Pine**, `backtest_service.py:152` | Price/EMA21 cross, long and short; optional ATR exits. | Open positions omitted; same-close reversal fills; optional stops lack gap-aware execution. Long/short reversal may be incompatible with a selected broker. Add a side/capability configuration and parity tests before evaluating slope/deadband filters. |
| **Enhanced Channel — MCP + standalone/Pine**, `strategies/enhanced_channel/` | Rolling regression/Donchian/Keltner channels, bounce/reclaim/inflection entries, ratcheted stops. | Short history silently substitutes for long macro windows, so nominal horizons overlap early. Sample-length-dependent warm-up/Keltner periods and same-bar stop timing need correction. Require explicit horizon readiness, fixed warm-up, causal stops, and ablations of each entry mode. |
| **Curved Channel — standalone**, `strategies/curves/` | Polynomial pivot channels plus fallback, breakout, re-entry, and sizing modes. | Large parameter surface and polynomial extrapolation make stability hard to establish. Chart curves alone do not prove when the boundary became available. Preserve causal boundary snapshots, normalize fitting coordinates, cap extrapolation, and compare linear versus quadratic/cubic out of sample. Remove modes that add no stable incremental value. |
| **Smart Hold — standalone**, `strategies/smart_hold/` | Mostly invested; modular MA/ATR exits and VIX/price re-entry signals. | First-100-bar volatility lookahead; first-match signal priority obscures attribution. Current-ATR trailing distance can widen when volatility rises. Use historical-only volatility, ratcheted stops, and per-signal ablations; measure upside capture, drawdown, time out, and re-entry lag. |
| **Smart Hold RC — standalone**, `strategies/smart_hold_rc/` | Smart Hold-style exits; selects structural versus standard re-entry by volatility. | Same early lookahead; 2.5% bucket is explicitly chosen from particular stocks’ results. Hard switching can overfit the sample. Compare each fixed mode and a trailing, hysteretic selector on unseen symbols/time periods. |
| **Hyperbolic Runner — standalone**, `strategies/hyperbolic_runner/` | Detects explosive moves, holds with wide ATR exits, adds pyramid exposure. | Research selection focuses on known historical winners. Default 20×ATR protection and up to 1.5× sizing require meaningful exposure/margin modeling. Include failed runners and delisted assets; use point-in-time selection, financing costs, gap stress, and position-level loss limits. |
| **Reversal Channel — standalone**, `strategies/reversal_channel/` | Downtrend → higher high → higher low state machine. | Defaults differ from narrative (one minimum swing and 5×ATR versus stated two and 8×). Structural delay is a research tradeoff. Keep pivot availability explicit, reconcile docs, and test staleness, tolerance, and failed-reversal exits independently. |
| **RSI Volume Watch — standalone**, `strategies/rsi_volume_watch/` | RSI50 crossings with volume confirmation, trailing/time exits. | Volume is not directional proof. Close-based trailing execution misses intrabar excursions. Test session-adjusted volume for intraday use, causal ratcheted stops, and the incremental value of the volume gate over RSI alone. |
| **Scalping — standalone**, `strategies/scalping/` | Configurable EMA, RSI/Bollinger, MACD, stochastic confluence. | Close-only stop/target evaluation is especially material at short horizons. Constant costs and correlated votes can overstate usefulness. Replay finer bars with spread/latency/slippage scenarios and time-of-day costs; ablate each signal rather than counting correlated indicators as independent confirmation. |
| **Synthetic Long — standalone**, `strategies/synthetic_long/` | Modeled deep-ITM calls plus far-OTM short puts during VIX fear. | A leveraged bullish options combination, not equal-strike synthetic stock. Uses model prices instead of historical chains. DTE decays by bar count despite calendar-year pricing; “cash-secured” comment conflicts with 20% collateral. Fix calendar expiry and margin/assignment/cash accounting; require actual chain quotes for performance claims. |
| **News Vol — standalone**, `strategies/news_vol/` | Oil/VIX/gold price triggers allocate to energy, defense, tankers, gold. | It infers a geopolitical event from prices; it does not ingest or identify news events. Fixed narrative-specific holdings and thresholds risk selection bias. Missing indicator data skips management for that date. Separate exposure management from signal availability; use timestamp-aligned data and test false triggers, missed events, and portfolio correlation. |

## Experiments and strategy-selection research

These are additional research variants rather than separate production integrations.

| Experiment | Weakness / improvement |
|---|---|
| EMA sweep (`strategies/ema_sweep/ema_sweep_test.py`) | Selects top EMA lengths on SPY/QQQ over the same two-year history. Reserve an untouched evaluation period; report the whole parameter surface, not only winners. |
| Hermes v1 SMA50/200 | Long/short regime baseline; slow confirmation and short financing need modeling. Compare against the equivalent registry baseline. |
| Hermes v2 RSI oversold | Same falling-market exposure hypothesis as RSI; select threshold only in training. |
| Hermes v3 ATR trend | Audit stop chronology and gaps; evaluate ATR distance stability rather than best return. |
| Hermes v4 Bollinger mean reversion | Duplicates a baseline family; consolidate into a common parameterized engine and test regime sensitivity. |
| Hermes v5 MACD | Duplicate crossover engine; parity-check then remove duplicated accounting. |
| Hermes v6 RSI + SMA + volume | Additional filters create selection flexibility; measure each filter’s independent contribution and retained trade count. |
| Hermes v7 EMA20/50 | Entry uses level alignment, despite a crossover description. Decide level versus cross semantics and use a shared implementation. |
| Hermes v8 RSI + SMA200 | Trend gate may avoid declines but delay reversals; evaluate the gate with matched exposure and no retuning on test. |
| Hermes v9 slow EMA | Longer lag and fewer observations; test trend-duration sensitivity and confidence intervals. |
| Hermes v10 EMA8/21 | Faster turnover requires stronger cost tests. The iteration catalog references undefined `strategy_v10_fast_ema`; the defined function is `strategy_v10_double_ema`. Fix the catalog before running it. |
| Iterative v1 SMA50/200 | `run_strategy_1` can replace the equity array with a scalar on exit, then index it. Initial equity/state handling is inconsistent. Replace with the shared ledger. |
| Iterative v2 RSI | Warm-up equity remains zero and holding valuation repeatedly uses a fixed base times a one-bar ratio. Correct the equity path before evaluating signals. |
| Iterative v3 12-month momentum | Same zero warm-up and valuation problems; long lookback reduces scored observations. Use shared accounting and explicit historical warm-up. |
| Regime master folder | A proposal and reference-indicator collection, not an integrated switcher. Map each regime to a baseline, add transition hysteresis and a flat/uncertain state, and test whether switching improves a fixed blend after costs. Audit third-party licenses before redistribution. |

Hermes’ “iterate until beating buy-and-hold on all tickers” objective repeatedly selects on the evaluation set. Replace that stopping rule with a fixed experiment budget, registered hypotheses, reproducible seeds, training-only selection, and a final holdout. Both experiment scripts also use hard-coded `/root/workspace/...` paths, limiting portability.

## Project-wide improvement scope

1. **Canonical strategy API and registry.** Define metadata, defaults, supported assets/sides/timeframes, warm-up, parameter schema, state, and events once. Import the same engine from CLI/MCP/UI. Convert Pine to a tested mirror where supported. Generate documentation and UI controls from the registry.
2. **Installable package and deployment checks.** Dynamic runners walk from installed service files to an external `strategies` tree, while setuptools discovers only `src` packages. The UI expects static assets not declared in package-data. Add wheel-content checks and an installed-wheel smoke test outside the checkout; package strategy code and UI resources explicitly. Container source copies do not automatically repair installed-module-relative paths. The Compose file also lacks a persistent database volume.
3. **Canonical data snapshots.** Cache immutable OHLCV with provider/version, adjustment policy, timezone, session, interval, and checksum. Current raw Yahoo fetching and dashboard `yfinance` history do not explicitly align their adjustment policies. Validate duplicates, gaps, finite/positive prices, missing volume, and finalized candles. Replace bare bar-count HTF grouping with session-aware aggregation.
4. **Portfolio and journal correctness.** Preserve side, actual size, costs, execution ids, and strategy configuration throughout. Dashboard `_save_backtest_trades` fabricates $1,000 sizing, one-day holding periods, and $3 fees; its price-based P&L can disagree with net returns. Store run ids and actual facts, not reconstructed approximations. Separate backtest/paper/live queries and reconcile fills before recognizing positions.
5. **Validation and CI.** The reviewed `.github` directory contains templates/funding but no workflow. Existing signal/execution scripts rely on live data and often print failures or return `False`, which is not an assertion failure under pytest. Introduce offline fixtures and assertions for accounting, causality, signal state, package installation, and mocked broker lifecycle. Preserve a small opt-in integration suite separately.
6. **Operational reliability.** Synchronous fetching/backtests run inside async dashboard routes. Move expensive work to bounded workers, cache results, add timeouts and per-strategy failure isolation, and use structured errors. One strategy failure should not abort all comparisons. Validate authentication/access controls for HTTP exposure before enabling broker capabilities there.
7. **Reproducible research records.** Store commit, data snapshot, parameter hash, period, warm-up, costs, benchmark, and selection history with every result. Keep generated reports outside source or indexed by immutable run id. Existing “best performers” and ticker maps are historical selections, not forward-valid assignments.
8. **News/sentiment quality.** Treat source freshness, availability, duplicate stories, and ticker relevance explicitly; missing coverage should not silently mean neutral. Record why a combined signal fired and evaluate incremental value beyond price signals.
9. **Documentation cleanup.** README strategy count and paths lag implementation; some descriptions disagree with defaults. `package.json` advertises `dist/index.js` while its build command builds Python. Clarify supported distribution, transport, ports, setup, and actual live execution capabilities.

## Suggested implementation sequence

| Stage | Deliverable | Acceptance condition |
|---|---|---|
| **1 — Establish trustworthy behavior** | Explicit events/state, fix Donchian, remove false robustness verdicts, shared lot ledger. | Offline fixtures reproduce correct entries/exits; fractional/short/partial accounting reconciles; no-trade folds cannot pass. |
| **2 — Make tests causal and comparable** | Immutable data, fixed warm-up, next-eligible fills, per-bar portfolio equity, common benchmarks. | Prefix-invariance passes; costs/gaps/terminal positions are consistent; CLI and MCP agree. |
| **3 — Validate execution in paper mode** | Broker state machine, idempotency, fill reconciliation, exits, capability checks and risk limits. | Restart/retry cannot duplicate an order; rejected protection is actionable; cash/positions match broker fixtures. |
| **4 — Evaluate incremental strategy value** | Train-only selection, untouched evaluation, ablations, unseen symbols and market regimes. | Every retained feature improves a predeclared metric with acceptable costs/risk and adequate evidence. |
| **5 — Simplify and package** | Unified registry/UI/docs, installable resources, CI and durable run storage. | Clean installed-wheel and container smoke tests work outside the source tree. |

For a first research baseline, use a small set spanning distinct hypotheses: EMA Cross (trend), Bollinger (mean reversion), Buy and Protect (exposure management), and Enhanced Channel (channel behavior). This is a simplification proposal, not a performance ranking. Keep the remaining variants available for controlled comparisons; defer options and scalping performance claims until their execution/data models are adequate.

## Verification performed

- Parsed all **83 Python files under `src` and `strategies`** successfully. This is syntax validation, not functional correctness.
- Called all **14 registered strategy runners** on 300 synthetic rising candles; no exceptions. Most appropriately returned no completed trades, so this is only an import/interface smoke check.
- Reproduced impossible Donchian behavior, missed last-bar RSI entry, false Buy and Protect exit, the one-share accounting discrepancy, and zero-trade `ROBUST` classification.
- Read standalone implementations, signal modules, services, packaging/deployment files, experiment scripts, and tests. No full historical performance sweep, Pine compilation, installed-wheel build, or broker integration test was run.

The immediate recommendation is to repair signal and accounting correctness, then rerun research. Current strategy rankings cannot reliably answer which strategy is strongest.
