# Adaptive line comparison

Generated: 2026-10-25T23:29:25.353315-04:00

Fixed settings and candles; returns are after the existing commission/slippage model. Adaptive stays off by default. Saved Best records are unchanged.

| Ticker / window | Baseline return | Adaptive return | Difference | Daily-close drawdown: before → after | Trades: before → after |
|---|---:|---:|---:|---:|---:|
| AAPL / saved | 49.01% | 49.01% | +0.00 pp | 7.34% → 7.34% | 38 → 38 |
| AAPL / archive_2y | 96.10% | 96.10% | +0.00 pp | 20.39% → 20.39% | 69 → 69 |
| AAPL / earlier_period | 32.61% | 32.61% | +0.00 pp | 20.39% → 20.39% | 33 → 33 |
| SPY / saved | 17.06% | 17.23% | +0.17 pp | 4.53% → 4.53% | 11 → 17 |
| SPY / archive_2y | 31.37% | 34.30% | +2.93 pp | 7.94% → 7.94% | 33 → 40 |
| SPY / earlier_period | 8.55% | 8.55% | +0.00 pp | 7.94% → 7.94% | 20 → 20 |

## Saved-window sensitivity

| Ticker | Baseline | Legacy staggered | Adaptive 2-bar / 0.25 ATR | Adaptive 1-bar / 0.25 ATR | Adaptive 2-bar / 0.5 ATR | Adaptive + staggered |
|---|---:|---:|---:|---:|---:|---:|
| AAPL | 49.01% | 49.01% | 49.01% | 49.01% | 49.01% | 49.01% |
| SPY | 17.06% | 8.47% | 17.23% | 8.95% | 16.04% | 10.46% |

## SPY screenshot case

Adaptive support tightens on May 21 using the April 29 / May 19 anchors, rising $1.6154 per candle instead of the original $0.12435. The April 27 position exits June 5 rather than September 22.

From that April 27 entry onward, normalized net return is **8.69% baseline vs 7.75% adaptive**, with 1 vs 7 trades. Closer tracking did not improve this particular part of the window; the small full-window improvement comes from earlier trades.

AAPL has no qualifying adaptive replacements with the tested presets. The existing minimum anchor move, boundary validation and confirmation rules remain enforced.

## Limits

- The saved and two-year windows overlap; they are not independent samples.
- Earlier periods precede each saved window but use the existing Saved Best parameters; not a prospective out-of-sample validation.
- Drawdown is measured at daily closes; intraday drawdown may be greater.
- Returns include 0.1% commission and 0.05% slippage per side unless a preset specifies otherwise.
- Reentries within 3 bars are a turnover diagnostic, not proof of a false signal.
