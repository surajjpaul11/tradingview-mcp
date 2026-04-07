# Curved Channel Strategy — Improvement Log

Running log of strategy tweaks, backtests, and results. Each entry records the date, what changed, and the impact across test symbols.

## Test Symbols
- **SPY** (S&P 500 ETF, 2y daily) — large-cap benchmark
- **BTC-USD** (Bitcoin, 2y daily) — crypto/high-volatility
- **QQQ** (Nasdaq 100 ETF, 2y daily) — tech-heavy benchmark

---

## v0 — Baseline (2026-04-06)

**Description:** Initial implementation. Entry requires price in lower 40% of ascending channel + bullish bar. Shorts enabled at 25% size on channel break.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | +2.78% | +27.03% | -24.25% | 3 (2L/1S) | 33.3% | -3.34% | 3.18 |
| BTC-USD | -1.94% | +0.86% | -2.80% | 8 (1L/7S) | 12.5% | -7.58% | -1.40 |
| QQQ | +4.74% | +33.57% | -28.83% | 3 (2L/1S) | 66.7% | -0.09% | 15.15 |

**Issues:** Only 3-8 trades. 22 channel breaks missed while flat because entry too restrictive (lower 40% only).

---

## v1 — Widen entry to full channel (2026-04-06)

**Change:** Entry condition widened from lower 40% of channel to anywhere inside channel (between support and resistance). Still requires bullish bar (close > open).

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | +0.78% | +27.03% | -26.25% | 8 (6L/2S) | 62.5% | -6.42% | 0.62 |
| BTC-USD | +27.37% | +0.86% | +26.51% | 9 (2L/7S) | 22.2% | -5.39% | 4.78 |
| QQQ | +6.13% | +33.57% | -27.44% | 3 (2L/1S) | 66.7% | -0.09% | 17.37 |

**Delta from v0:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | -2.00% | +5 | More trades but new entries near top of channel led to larger drawdowns |
| BTC-USD | **+29.31%** | +1 | Caught the Oct 2024 BTC rally ($67K->$87K) that v0 missed entirely |
| QQQ | +1.39% | 0 | Earlier entry on Sep 13 vs Oct 3, captured more upside |

**Verdict:** Major improvement on BTC-USD (+29.31% delta). QQQ slightly better. SPY worse due to entries at unfavorable channel positions. Net positive change — keep.

---

## v2 — Breakout detection + channel reset + ATR trailing stop (2026-04-06)

**Change:** Rewrote strategy engine from pre-computed channels to inline bar-by-bar detection. Added breakout logic: when price breaks >2% beyond channel boundary, channel is invalidated, pivots cleared, and new channel must form from fresh pivots. Upside breakout closes long and re-enters at 150% size. Downside breakout sells long + opens 25% short. ATR trailing stop (2x ATR, 14-period) protects positions during channel-less wait period.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -4.26% | +27.03% | -31.29% | 15 (8L/7S) | 40.0% | -8.69% | -2.69 |
| BTC-USD | +44.23% | -1.38% | +45.61% | 15 (9L/6S) | 46.7% | -7.48% | 7.15 |
| QQQ | +0.19% | +33.57% | -33.38% | 12 (6L/6S) | 58.3% | -10.38% | 0.20 |

**Delta from v1:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | -5.04% | +7 | More trades from channel resets. ATR trailing stops cut some winners short, shorts whipsawed |
| BTC-USD | **+16.86%** | +6 | 3 upside breakouts captured at 150% size (+15.23%, +2.31%, +6.42% breakout entries). ATR trail locked in gains |
| QQQ | -5.94% | +9 | More frequent trading, but ETF steady trend doesn't produce clean breakouts |

**Exit breakdown:**
- SPY: 5 break, 3 expired, 3 flip, 0 breakout up, 0 breakout down, 3 ATR trail, 1 EOD
- BTC-USD: 1 break, 1 expired, 0 flip, 3 breakout up, 0 breakout down, 9 ATR trail, 1 EOD
- QQQ: 3 break, 4 expired, 2 flip, 0 breakout up, 0 breakout down, 3 ATR trail, 0 EOD

**Verdict:** Keep for BTC-USD (+16.86% delta, +44.23% total return, Sharpe 7.15 — excellent). Worse for SPY/QQQ which don't produce clean breakouts in steady uptrends. The breakout logic is best suited for volatile, momentum-driven assets. Next steps: consider adding a regime filter so breakout logic only activates when volatility is high enough.
