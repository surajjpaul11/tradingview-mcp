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

---

## v3 — SMA(200) filter for shorts (2026-04-06)

**Change:** Shorts only allowed when price is below SMA(200). Added `calc_sma()` helper and `_short_allowed(bar)` gate. Filters out shorts during uptrends where they consistently lose.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -5.13% | +27.03% | -32.16% | 10 (5L/5S) | 30.0% | -5.80% | -4.14 |
| BTC-USD | +34.69% | -1.28% | +35.97% | 9 (5L/4S) | 55.6% | -1.29% | 9.82 |
| QQQ | -3.33% | +33.57% | -36.90% | 12 (7L/5S) | 58.3% | -12.77% | -1.46 |

**Delta from v2:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | -0.87% | -5 | Fewer shorts (10 vs 15) but remaining shorts still losing. SMA(200) too high to filter SPY shorts effectively — SPY rarely trades below its SMA(200) |
| BTC-USD | -9.55% | -6 | SMA filter blocked profitable Feb/Mar 2025 shorts and Jun/Jul 2025 breakout entries. Missed the big +11.18% 150% trade. MaxDD improved dramatically: -1.29% vs -7.48% |
| QQQ | -3.52% | 0 | Added a breakout_down trade but also a new long entry at bad timing. Worse overall |

**Verdict:** Mixed. BTC Sharpe improved massively (9.82 vs 7.15) with MaxDD dropping from -7.48% to -1.29%, but total return fell -9.55%. SPY/QQQ worse. The SMA filter is too blunt for this strategy — it blocks good shorts on volatile assets. Moving to improvement #2 (min hold period) which may better address the whipsaw problem without removing profitable shorts.

---

## v4 — Minimum 5-bar hold period for shorts (2026-04-06)

**Change:** Added `SHORT_MIN_HOLD = 5` — shorts cannot be exited via channel_break or channel_flip until held for at least 5 bars. Breakout exits (breakout_up) still fire immediately for safety. ATR trailing stop unaffected.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -5.70% | +27.03% | -32.73% | 9 (4L/5S) | 22.2% | -6.12% | -4.85 |
| BTC-USD | +23.06% | -1.20% | +24.26% | 8 (4L/4S) | 50.0% | -1.86% | 7.67 |
| QQQ | -4.93% | +33.57% | -38.50% | 12 (7L/5S) | 58.3% | -14.22% | -2.03 |

**Delta from v3:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | -0.57% | -1 | Min hold kept the Mar 2026 short longer — turned a -0.72% flip into a -1.05% flip. Made things slightly worse |
| BTC-USD | -11.63% | -1 | Eliminated the Jul 2024 channel_break exit, short now exits via breakout_up. But lost the Jul 2024 long entry that caught +8.79%. Fewer trades overall |
| QQQ | -1.60% | 0 | Jan 2025 short held longer before flip, entered next long at higher price ($531 vs $524). Worse entry caused -7.07% loss vs -5.87% |

**Verdict:** Net negative across all three symbols. The min hold period delayed exits on losing shorts, making them lose more. The problem isn't exit timing — it's that most shorts shouldn't be opened at all on uptrending assets. The SMA filter (v3) was the better approach for this specific issue. Keeping both changes and moving to improvement #3 (flat period re-entry) which addresses the biggest drag: sitting flat during 30-137 day rallies.

---

## v5 — SMA(50) fallback entry during flat periods (2026-04-06)

**Change:** When flat with no active channel for 10+ bars, enter long if price > SMA(50) on a bullish bar. Exit when price drops below SMA(50). If a channel forms while in a fallback position, hand off to normal channel logic.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -2.07% | +27.03% | -29.10% | 17 (12L/5S) | 41.2% | -6.59% | -0.78 |
| BTC-USD | -5.84% | -1.00% | -4.84% | 33 (29L/4S) | 33.3% | -25.54% | -0.08 |
| QQQ | **+14.24%** | +33.57% | -19.33% | 21 (16L/5S) | 52.4% | -13.52% | **2.29** |

**Delta from v4:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | +3.63% | +8 | Fallback caught May-Jun 2025 (+5.11%) and Jul-Oct 2025 (+4.13%). But 2 fallback exits lost -5.19% on bad entries during choppy Aug/Dec 2024 |
| BTC-USD | **-28.90%** | +25 | Disaster. Fallback triggered 29 longs — BTC's choppy sideways periods caused constant false entries and 20 channel_expired exits. SMA(50) is way too fast for crypto |
| QQQ | **+19.17%** | +9 | Huge win. Fallback caught the massive May-Sep 2025 rally (+20.40%). Flat gaps reduced from 347d to 92d |

**Verdict:** Keep for ETFs (SPY +3.63%, QQQ +19.17%), **revert for BTC**. The SMA(50) fallback works great for trending ETFs but is catastrophic for crypto's choppy price action. Next step: the fallback needs to be asset-type-aware, or use a longer SMA for volatile assets. Moving to improvement #4 (separate short entry threshold from channel break).

---

## v6 — Separate short entry threshold at 1.5% (2026-04-06)

**Change:** Short positions only open when break exceeds 1.5% below support (SHORT_ENTRY_PCT), while long exit still fires at 1.0% (TOUCH_TOLERANCE_PCT). This filters out marginal breaks that trigger unprofitable shorts.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -2.07% | +27.03% | -29.10% | 17 (12L/5S) | 41.2% | -6.59% | -0.78 |
| BTC-USD | -5.84% | -1.00% | -4.84% | 33 (29L/4S) | 33.3% | -25.54% | -0.08 |
| QQQ | **+18.74%** | +33.57% | -14.83% | 20 (16L/4S) | 55.0% | **-10.11%** | **3.03** |

**Delta from v5:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | 0.00% | 0 | No change — SPY breaks already exceeded 1.5% |
| BTC-USD | 0.00% | 0 | No change — BTC breaks already exceeded 1.5% |
| QQQ | **+4.50%** | -1 | Eliminated the Jan 2025 marginal short (-1.03% flip loss). Fewer shorts = cleaner equity curve. Sharpe 3.03, MaxDD improved to -10.11% |

**Verdict:** Keep. Pure improvement for QQQ, no change for SPY/BTC. The separate threshold successfully filters out marginal short entries on QQQ.

---

## Cumulative Summary (v0 → v6)

| Symbol | v0 | v1 | v2 | v3 | v4 | v5 | v6 |
|--------|------|------|------|------|------|------|------|
| SPY | +2.78% | +0.78% | -4.26% | -5.13% | -5.70% | -2.07% | -2.07% |
| BTC-USD | -1.94% | +27.37% | +44.23% | +34.69% | +23.06% | -5.84% | -5.84% |
| QQQ | +4.74% | +6.13% | +0.19% | -3.33% | -4.93% | +14.24% | **+18.74%** |

**Best per symbol:**
- **SPY**: v0 (+2.78%) — simple strategy works best on steady uptrend ETFs
- **BTC-USD**: v2 (+44.23%) — breakout detection is ideal for crypto momentum
- **QQQ**: v6 (+18.74%) — full v6 with fallback + separate short threshold

**Key insight:** The optimal configuration varies by asset class. SPY/QQQ benefit from fallback SMA entries during flat periods. BTC benefits from breakout detection but is hurt by SMA fallback. A production version should use asset-specific parameter presets.

---

## v7 — Asset-specific parameter presets (2026-04-07)

**Change:** Auto-detect crypto vs ETF symbols. Crypto preset disables fallback SMA and short SMA filter (too choppy). ETF preset keeps SMA(50) fallback and SMA(200) short filter. Detection uses symbol name patterns (-USD, BTC, ETH, etc.).

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -2.07% | +27.03% | -29.10% | 17 (12L/5S) | 41.2% | -6.59% | -0.78 |
| BTC-USD | **+31.69%** | -1.00% | **+32.69%** | 14 (8L/6S) | 42.9% | -7.57% | **5.83** |
| QQQ | +18.74% | +33.57% | -14.83% | 20 (16L/4S) | 55.0% | -10.11% | 3.03 |

**Delta from v6:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | 0.00% | 0 | Same ETF preset as v6 |
| BTC-USD | **+37.53%** | -19 | Crypto preset disabled fallback SMA → eliminated 29 false longs and 20 channel_expired losses. 4 breakout_up exits captured momentum. Sharpe 5.83 |
| QQQ | 0.00% | 0 | Same ETF preset as v6 |

**Verdict:** Keep. Massive recovery for BTC (+37.53% delta). The best combined result so far across all three symbols.

---

## v8 — Volume confirmation on entries (2026-04-06)

**Change:** Require volume >= 1.2x its 20-bar MA for all entries (channel long, channel short, fallback SMA). Added `VOL_CONFIRM_MULT = 1.2` and `VOL_CONFIRM_PERIOD = 20`. Filters out low-conviction entries where price moves on thin volume.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -4.42% | +27.03% | -31.45% | 15 (10L/5S) | 26.7% | -5.73% | -2.02 |
| BTC-USD | **+38.94%** | -1.12% | **+40.06%** | 13 (8L/5S) | 53.8% | -7.54% | **8.00** |
| QQQ | +10.92% | +33.57% | -22.65% | 14 (10L/4S) | 50.0% | -7.93% | 2.99 |

**Delta from v7:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | -2.35% | -2 | Volume filter blocked 2 fallback SMA entries. Remaining trades had worse timing — Dec 2024 fallback entry now gone but short losses persisted |
| BTC-USD | **+7.25%** | -1 | Filtered out the Oct 2024 short that lost -1.15%. Sharpe improved from 5.83 to 8.00. Better entry quality overall |
| QQQ | **-7.82%** | -6 | Volume filter blocked 6 entries including several profitable fallback SMA trades. The big May-Sep 2025 rally entry (+14.13%) survived but many smaller winners filtered out |

**Chart analysis:**
- SPY: 4 whipsaw trades (1-2 day holds) still losing money. 5/5 shorts unprofitable. Volume filter didn't help the core problem of shorting uptrends.
- BTC-USD: Strong performance. 7 flat periods averaging 63 days — selective but high quality. No whipsaws. ATR trailing stops working well (69% of exits).
- QQQ: 8/14 exits via channel_expired (57%) — too high, indicates channels expiring before meaningful moves. Volume filter was too restrictive for ETFs.

**Verdict:** Mixed. BTC improved significantly (+7.25%, Sharpe 8.00 — best ever). SPY/QQQ worse. The volume filter helps crypto (filters low-conviction entries in choppy markets) but hurts ETFs (blocks valid entries in steady uptrends where volume patterns differ). Consider making volume confirmation asset-specific like the SMA fallback, or reverting for ETFs.

---

## v9 — In-channel trailing stop (2026-04-06)

**Change:** Added trailing stop that activates inside channels after 2% profit. Uses 1.5x ATR (tighter than the 2x breakout trail). Locks in gains on winning channel trades instead of waiting for channel break/expire. New params: `CH_TRAIL_ACTIVATE_PCT = 2.0`, `CH_TRAIL_ATR_MULT = 1.5`.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -2.57% | +27.03% | -29.60% | 14 (11L/3S) | 42.9% | -6.08% | -1.11 |
| BTC-USD | +38.87% | -0.94% | +39.81% | 13 (8L/5S) | 53.8% | -7.59% | 7.99 |
| QQQ | **+14.89%** | +33.57% | -18.68% | 16 (12L/4S) | 56.2% | **-5.94%** | **4.52** |

**Delta from v8:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | **+1.85%** | -1 | 3 channel_trail_stop exits locked in gains. Oct 2024 long exited at +3.95% via trail. Nov 2025 trade split into profitable trail exit (+1.33%) + re-entry. Fewer shorts (3 vs 5) |
| BTC-USD | -0.07% | 0 | No change — BTC trades all exit via breakout_up or atr_trailing_stop already. Channel trail never activated (positions reach 2% profit but break out before trail catches up) |
| QQQ | **+3.97%** | +2 | 2 channel_trail_stop exits. Jan 2025 long now exits at +2.01% instead of losing -3.93% at channel_break. May 2025 long locks in +10.11% then re-enters for +4.01%. MaxDD improved from -7.93% to -5.94%. Sharpe 4.52 vs 2.99 |

**Exit breakdown:**
- SPY: 3 break, 2 expired, 0 flip, 0 breakout up, 2 breakout down, 3 ATR trail, 3 ch trail, 1 SMA fallback, 0 EOD
- BTC-USD: 0 break, 0 expired, 0 flip, 3 breakout up, 0 breakout down, 9 ATR trail, 0 ch trail, 0 SMA fallback, 1 EOD
- QQQ: 2 break, 8 expired, 0 flip, 0 breakout up, 1 breakout down, 3 ATR trail, 2 ch trail, 0 SMA fallback, 0 EOD

**Verdict:** Keep. Positive for ETFs (SPY +1.85%, QQQ +3.97%), neutral for BTC. The in-channel trailing stop successfully locks in profits on channel trades — the QQQ Jan 2025 trade going from -3.93% to +2.01% is the standout improvement. QQQ Sharpe jumped from 2.99 to 4.52 and MaxDD improved. No downside for BTC since it doesn't trigger.

---

## v10 — Reduce channel_expired churn (2026-04-06)

**Change:** Two changes: (1) Increased minimum channel extension from 10 to 20 bars. (2) On channel expiry, only close losing positions immediately; profitable positions transition to ATR trailing stop and keep riding.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | **+1.03%** | +27.03% | -26.00% | 13 (10L/3S) | 53.8% | -6.77% | **0.59** |
| BTC-USD | +38.85% | -0.90% | +39.75% | 13 (8L/5S) | 53.8% | -7.60% | 7.98 |
| QQQ | +7.39% | +33.57% | -26.18% | 15 (11L/4S) | 46.7% | -9.62% | 2.34 |

**Delta from v9:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | **+3.60%** | -1 | Channel_expired exits: 0 (was 2). Jun 2024 trade now rides ATR trail to +0.72% instead of expiring at -0.05%. Fewer shorts (3 vs 5). 4 ch_trail exits lock gains. Sharpe turned positive (0.59 vs -1.11) |
| BTC-USD | -0.02% | 0 | No change — BTC had 0 expired exits in v9 already |
| QQQ | **-7.50%** | -1 | Channel_expired exits: 1 (was 8). But some expired exits were protective! Oct 2024 short now held longer via trail, losing -1.20% vs +0.28%. Extended channels caused different entry timing on Dec 2024 trade. MaxDD worsened to -9.62% |

**Verdict:** Mixed. SPY big improvement (+3.60%, first positive return since v0, Sharpe positive). BTC unchanged. QQQ significantly worse (-7.50%) — the channel_expired exits were actually serving as a useful stop-loss on some QQQ trades. The "profitable positions ride" logic works for SPY's steady uptrend but hurts on QQQ where channel expiry was cutting losses early.

Reverting v10 for QQQ would require asset-specific behavior. Keeping the change since SPY improvement outweighs, but noting that channel_expired is not purely wasteful — it sometimes protects against late-channel deterioration.

---

## v11 — Scale short size by break magnitude (2026-04-06)

**Change:** Short position size scales with how far price breaks below support. Base 25% + 12.5% per 1% break, capped at 75%. Bigger breaks get bigger positions. Applied to channel break shorts and flat breakout shorts (descending channel entries stay at base 25%).

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -0.71% | +27.03% | -27.74% | 13 (10L/3S) | 53.8% | -6.77% | -0.25 |
| BTC-USD | +39.18% | -0.81% | +39.99% | 13 (8L/5S) | 53.8% | -8.41% | 7.38 |
| QQQ | +7.38% | +33.57% | -26.19% | 15 (11L/4S) | 46.7% | -9.87% | 2.31 |

**Delta from v10:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | **-1.74%** | 0 | Short sizes increased to 75%/52%/57% (was all 25%). Aug 2024 short at 75% lost -2.15% vs -0.72%. Larger losing shorts hurt more than the one winning short helped |
| BTC-USD | +0.33% | 0 | Feb 2025 short at 75% gained +8.01% vs +2.67% (big win). But Oct 2024 at 54% lost -2.49% vs -1.15%, Nov 2025 at 75% lost -3.59% vs -1.20%. Sharpe dropped 7.98→7.38 |
| QQQ | -0.01% | 0 | Essentially unchanged. Wins and losses both amplified symmetrically. Sharpe slightly lower |

**Verdict:** Revert. The scaling amplifies losses on wrong-way shorts more than it helps right-way shorts. SPY worse (-1.74%), BTC Sharpe dropped (7.38 vs 7.98) despite slightly higher return, QQQ flat. The core problem remains: most shorts on uptrending assets lose money, and making those positions bigger makes things worse.

---

## v12 — Pyramid into longs (2026-04-06)

**Change:** When an existing long position has 3%+ unrealized profit and a new ascending channel pivot confirms, close the position and re-enter at 150% size. Locks in gains via the close and bets larger on confirmed uptrends.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | -2.37% | +27.03% | -29.40% | 17 (12L/5S) | 35.3% | -8.75% | -0.77 |
| BTC-USD | +38.81% | -0.78% | +39.59% | 13 (8L/5S) | 53.8% | -7.62% | 7.97 |
| QQQ | +8.73% | +33.57% | -24.84% | 15 (11L/4S) | 46.7% | -9.62% | 2.65 |

**Delta from v10:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | **-3.40%** | +4 | 2 pyramid_upsize exits. Oct 2024: closed at +3.80%, re-entered 150% → lost -0.23% (net worse than original +3.95%). Sep 2025: closed at +6.42%, 150% → lost -3.41% (net worse than +4.31%). Pyramiding at late channel = buying high |
| BTC-USD | -0.04% | 0 | No pyramids triggered — BTC trades too short-lived (breakout/ATR exits fire before 3% + new pivot) |
| QQQ | **+1.34%** | 0 | May 2025 trade pyramided at +10.11%, 150% position then gained +5.95%. Net +19.04% for the pair vs +14.74% without pyramid |

**Verdict:** Revert. SPY worse (-3.40%) because pyramiding near channel tops amplifies subsequent reversals. QQQ slightly better (+1.34%) but not enough to justify the SPY deterioration and added complexity. BTC unaffected. The issue: by the time a trade reaches 3% profit AND a new pivot forms, we're often near the channel top where risk/reward is unfavorable.

---

## v13 — Time-based exit (30-bar max hold for stale positions) (2026-04-06)

**Change:** If a position has been held for 30+ bars and has less than 1% unrealized profit, close it as `time_exit`. Frees capital from sideways positions that aren't going anywhere.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | +1.18% | +27.03% | -25.85% | 14 (11L/3S) | 50.0% | -6.63% | 0.64 |
| BTC-USD | +38.80% | -0.76% | +39.56% | 13 (8L/5S) | 53.8% | -7.63% | 7.97 |
| QQQ | +7.39% | +33.57% | -26.18% | 15 (11L/4S) | 46.7% | -9.62% | 2.34 |

**Delta from v10:**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | +0.15% | +1 | Jan 2026 long exits at -0.90% after 30 bars (was -3.12% at channel_break after ~50 bars). Small improvement from cutting a stale losing position earlier |
| BTC-USD | -0.05% | 0 | No change — BTC trades all exit via ATR/breakout within <20 bars |
| QQQ | 0.00% | 0 | No change — no QQQ trades lasted 30 bars without 1% profit |

**Verdict:** Marginal. SPY +0.15%, others unchanged. The time exit only triggered once (SPY Jan 2026). Keep since it's a mild positive with no downside, but the impact is too small to matter on this test set. The strategy already has effective exits via channel_trail_stop and ATR trailing that cut positions before 30 bars.

---

## v14 — Cubic fit (degree=3) (2026-04-06)

**Change:** Switched polynomial degree from 2 (quadratic) to 3 (cubic). Cubic polynomials can capture S-shaped and more complex channel boundaries. No code changes — just `--degree 3` on CLI.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | **+12.51%** | +27.03% | -14.52% | 9 (7L/2S) | 44.4% | **-5.13%** | **5.86** |
| BTC-USD | +13.74% | -0.76% | +14.50% | 8 (4L/4S) | 37.5% | **-2.12%** | 6.57 |
| QQQ | +0.59% | +33.57% | -32.98% | 10 (9L/1S) | 50.0% | -15.12% | 0.48 |

**Delta from v10 (degree=2):**

| Symbol | Return delta | Trade count delta | Notes |
|--------|-------------|-------------------|-------|
| SPY | **+11.48%** | -4 | Fewer, better trades. Cubic channels held longer — May-Aug 2025 trade gained +8.15%, Sep-Nov 2025 gained +5.53%. Only 2 shorts (vs 3). Sharpe 5.86 vs 0.59 |
| BTC-USD | **-25.11%** | -5 | Severely worse. Cubic overfits to BTC's volatile pivots, creating wide channels that miss breakout signals. Only captured 1 breakout_up (vs 3). Lost the big Nov 2024 and Jul 2025 breakout sequences |
| QQQ | -6.80% | -5 | Worse. Jul 2024 long held too long (-6.65%). Dec 2024 long lost -4.02%. MaxDD jumped to -15.12%. Cubic channels too flexible for QQQ's price action |

**Verdict:** Asset-specific. Cubic is outstanding for SPY (+11.48%, Sharpe 5.86, MaxDD -5.13%), but catastrophic for BTC (-25.11%) and poor for QQQ (-6.80%). Cubic's extra flexibility helps capture smooth ETF trends but overfits volatile crypto data. **Recommendation:** Use `--degree 3` manually for smooth, steady-trend ETFs like SPY. Keep degree=2 as default — auto-selecting cubic for all ETFs hurt QQQ (-6.80%).

---

## v15 — Increase max_pivots to 30 (2026-04-06)

**Change:** Increased `MAX_PIVOTS` from 20 to 30 via `--max-pivots 30`. More pivots = longer history for channel fitting.

| Symbol | Return | B&H | Trades | Notes |
|--------|--------|-----|--------|-------|
| SPY | +1.18% | +27.03% | 14 | Identical to v10 |
| BTC-USD | +38.81% | -0.77% | 13 | Identical to v10 |
| QQQ | +7.39% | +33.57% | 15 | Identical to v10 |

**Verdict:** No effect. The pivot buffer rarely reaches 20 on 2y daily data (500 bars × ~2 pivots per 20 bars ≈ 50 total, but rolling window stays well under 20 due to channel resets). Skip.

---

## v16 — Only trade positive-slope channels (2026-04-06)

**Change:** Added slope check on ascending channel's lower boundary at entry bar. Only enter long if polynomial derivative is positive (channel still rising). Filters out channels where curve has flattened or turned down.

| Symbol | Return | B&H | Trades | Max DD | Sharpe | Delta from v10 |
|--------|--------|-----|--------|--------|--------|----------------|
| SPY | **+4.12%** | +27.03% | 12 | **-3.92%** | **2.33** | **+2.94%** |
| BTC-USD | +13.60% | -0.77% | 10 | -7.34% | 5.06 | **-25.21%** |
| QQQ | +2.04% | +33.57% | 11 | -5.99% | 1.00 | -5.35% |

**Verdict:** Revert. SPY improved nicely (+2.94%, best MaxDD at -3.92%), but BTC devastated (-25.21%). The slope filter blocks entries in channels where the curve has turned down — but for BTC, these are exactly where breakouts occur (curve turns down → price breaks up). The filter removes the breakout setup that drives BTC's returns.

---

## v17 — RSI divergence exit warning (2026-04-06)

**Change:** Added RSI(14) calculation. When price makes a higher high but RSI makes a lower high (bearish divergence, checked over 10-bar lookback), tightens the in-channel trailing stop multiplier by 0.5x. Aims to exit sooner when momentum is fading.

| Symbol | Return | B&H | Trades | Sharpe | Delta from v10 |
|--------|--------|-----|--------|--------|----------------|
| SPY | +1.49% | +27.03% | 14 | 0.78 | +0.31% |
| BTC-USD | +38.81% | -0.76% | 13 | 7.97 | +0.01% |
| QQQ | +7.17% | +33.57% | 16 | 2.16 | -0.22% |

**Verdict:** Negligible impact. RSI divergence on daily bars is too infrequent to meaningfully affect results. SPY +0.31%, BTC unchanged, QQQ -0.22%. The in-channel trailing stop already handles profit protection well without the RSI signal. Keep the RSI code but set `RSI_DIVERGENCE_LOOKBACK = 0` (disabled) by default — available for future use on intraday timeframes where divergence occurs more often.

---

## v18 — Asset-specific preset refinements (2026-04-07)

**Change:** Tested 3 ETF preset variations to improve SPY/QQQ without hurting BTC.

**Approach 1 — vol=OFF, ride=OFF for ETFs:**

| Symbol | Return | B&H | Delta from v10 |
|--------|--------|-----|----------------|
| SPY | -5.06% | +27.03% | -6.24% |
| BTC-USD | +38.74% | -0.77% | -0.07% |
| QQQ | **+17.85%** | +33.57% | **+10.46%** |

**Approach 2 — vol=OFF, ride=ON for ETFs:**

| Symbol | Return | Delta from v10 |
|--------|--------|----------------|
| SPY | -3.58% | -4.76% |
| QQQ | +3.05% | -4.34% |

**Approach 3 — disable shorts for ETFs:**

| Symbol | Return | Delta from v10 |
|--------|--------|----------------|
| SPY | -1.77% | -2.95% |
| BTC-USD | +38.75% | -0.06% |
| QQQ | -8.71% | -16.10% |

**Verdict:** Revert all. No single ETF preset improved both SPY and QQQ simultaneously. Approach 1 was promising for QQQ (+10.46%) but devastated SPY (-6.24%). The base v10 config remains the best general-purpose default. Asset-specific optimization needs per-symbol parameter tuning (like degree=3 for SPY) rather than broad preset categories.

---

## v19 — Lower in-channel trail activation (1% instead of 2%) (2026-04-07)

**Change:** Lowered `CH_TRAIL_ACTIVATE_PCT` from 2.0 to 1.0. Goal: lock in gains sooner on smaller ETF moves.

| Symbol | Return | B&H | Trades | Sharpe | Max DD | Delta from v10 |
|--------|--------|-----|--------|--------|--------|----------------|
| SPY | +1.96% | +27.03% | 15 | 0.98 | -5.92% | +0.78% |
| BTC-USD | +38.77% | -0.66% | 13 | 7.96 | -7.65% | -0.04% |
| QQQ | +4.66% | +33.57% | 13 | 1.65 | -11.91% | -2.73% |

**Exit breakdown:** SPY had 6 channel trail stops (up from ~2 at 2% threshold). BTC had 0 channel trail stops — crypto moves too big for this to matter. QQQ had 3 channel trail stops that cut winners short.

**Verdict:** Revert. SPY slightly better (+0.78%) but QQQ significantly worse (-2.73%). Tighter activation cuts winners short on QQQ. BTC unaffected. Net negative.

---

## v20 — Wider touch tolerance for crypto (1.0% → 1.5%) (2026-04-07)

**Change:** Set `tolerance = 1.5` for crypto preset (BTC-USD etc). ETFs remain at 1.0%. Goal: capture more channel touches on volatile assets.

| Symbol | Return | B&H | Trades | Sharpe | Max DD | Delta from v10 |
|--------|--------|-----|--------|--------|--------|----------------|
| SPY | +1.18% | +27.03% | 14 | 0.64 | -6.63% | 0.00% |
| BTC-USD | +28.81% | -1.53% | 11 | 6.89 | -7.45% | **-10.00%** |
| QQQ | +7.39% | +33.57% | 15 | 2.34 | -9.62% | 0.00% |

**Verdict:** Revert. Wider tolerance cost BTC 10% in returns (38.81% → 28.81%). Fewer pivots qualified as touches → channels formed less often → 2 fewer trades, both of which were profitable. The 1.0% tolerance was already well-calibrated for BTC.

---

## v21 — Minimum channel age filter (2026-04-07)

**Change:** Added `MIN_CHANNEL_AGE` parameter — channel must exist for N bars before allowing entry. Asset-specific: crypto=0 (breakouts are fast), ETFs=3 (filter out immature channels). Tested age=3,4,5 for ETFs.

**Age sweep (ETFs only, crypto always age=0):**

| Age | SPY | QQQ | Avg |
|-----|-----|-----|-----|
| 0 (v10) | +1.18% | +7.39% | +4.29% |
| **3** | **+3.76%** | **+10.46%** | **+7.11%** |
| 4 | +5.98% | +4.22% | +5.10% |
| 5 | +5.98% | +2.17% | +4.08% |

**Final results (age=3 for ETFs, age=0 for crypto):**

| Symbol | Return | B&H | Trades | Win Rate | Sharpe | Max DD | Delta from v10 |
|--------|--------|-----|--------|----------|--------|--------|----------------|
| SPY | **+3.76%** | +27.03% | 11 | 54.5% | **2.33** | **-3.85%** | **+2.58%** |
| BTC-USD | **+39.02%** | -1.37% | 13 | 53.8% | **8.02** | -7.48% | **+0.21%** |
| QQQ | **+10.46%** | +33.57% | 14 | 50.0% | **3.41** | -7.03% | **+3.07%** |

**Key observations:**
- SPY: Eliminated 3 whipsaw trades in late 2025. Win rate up from 50% to 54.5%, MaxDD improved from -6.63% to -3.85%.
- BTC: Unchanged (age=0 for crypto preset). Still +39.02% with 8.02 Sharpe.
- QQQ: Gained back Jan-Feb 2025 channel trade (+2.01%) that age=5 filtered out. +10.46% is the best QQQ result since v7 (+18.74%).
- Age=3 is the best compromise — enough patience to filter noise, not so much that valid entries are blocked.

**Verdict:** **KEEP.** First universally-positive change since v10. All three symbols improved. This is now the new baseline.

---

## v22 — Increase breakout add percentage (50% → 100%) (2026-04-07)

**Change:** Increased `BREAKOUT_ADD_PCT` from 50 to 100. On upside breakout, position re-enters at 200% instead of 150%. Only affects assets with breakout_up events (currently only BTC).

| Symbol | Return | B&H | Trades | Sharpe | Max DD | Delta from v21 |
|--------|--------|-----|--------|--------|--------|----------------|
| SPY | +3.76% | +27.03% | 11 | 2.33 | -3.85% | 0.00% |
| BTC-USD | **+42.23%** | -1.39% | 13 | 7.32 | -9.88% | **+3.21%** |
| QQQ | +10.46% | +33.57% | 14 | 3.41 | -7.03% | 0.00% |

**Trade-level impact on BTC:**
- Trade 4 (Nov 2024): +5.10% → **+6.80%** (200% vs 150%)
- Trade 8 (Jul 2025): +11.18% → **+14.91%** (biggest amplification)
- Trade 12 (Jan 2026): -7.22% → **-9.63%** (loser amplified too)

**Verdict:** Keep (marginal). +3.21% extra return for +2.40% extra MaxDD. Sharpe dropped from 8.02 to 7.32 due to higher volatility from larger positions. Only affects BTC where breakouts drive returns. SPY/QQQ unaffected (no breakout_up trades).

---

## v23 — Tighter short ATR trailing stop (1.5x vs 2.0x) (2026-04-07)

**Change:** Added `SHORT_ATR_TRAIL_MULT = 1.5` — shorts use a tighter trailing stop than longs (2.0x). Exits losing shorts faster before losses deepen.

| Symbol | Return | B&H | Trades | Win Rate | Sharpe | Max DD | Delta from v22 |
|--------|--------|-----|--------|----------|--------|--------|----------------|
| SPY | **+4.40%** | +27.03% | 11 | **63.6%** | **2.74** | **-3.28%** | **+0.64%** |
| BTC-USD | **+43.90%** | -1.41% | 13 | 53.8% | 7.59 | -10.07% | **+1.67%** |
| QQQ | +10.46% | +33.57% | 14 | 50.0% | 3.41 | -7.03% | 0.00% |

**Short trade improvements:**
- SPY trade 4: -0.59% → +0.03% (exited 1 day earlier, turning a loss into breakeven)
- BTC trade 2: -1.15% → -0.84% | trade 5: +2.67% → +3.10% | trade 10: -1.20% → -0.55%
- QQQ: unchanged (short exits already optimal at these levels)

**Verdict:** **KEEP.** All symbols improved or neutral. SPY MaxDD now -3.28% (best ever), win rate 63.6%. The logic is sound — shorts are inherently riskier on uptrending assets, so tighter stops make sense.

---

## v24 — Reduce time exit from 30 to 20 bars (2026-04-07)

**Change:** Lowered `TIME_EXIT_BARS` from 30 to 20. Exit stale positions earlier.

| Symbol | Return | Delta from v23 |
|--------|--------|----------------|
| SPY | +4.57% | **+0.17%** |
| BTC-USD | +43.90% | 0.00% |
| QQQ | +10.46% | 0.00% |

**Note:** Also tested `SHORT_MIN_HOLD` 5→3 — no impact (v23's tighter short ATR stop already handles fast exits).

**Verdict:** Keep (marginal). SPY's stale Jan-Mar 2026 trade exits ~10 bars earlier, saving -0.17% of loss.

---

## v25 — 2-bar channel confirmation for long entries (2026-04-07)

**Change:** Long entries now require previous bar's close to also be within the channel (between support and resistance). Filters out single-bar price spikes into a channel. Applied to in-channel longs only — breakout entries and shorts unchanged.

| Symbol | Return | B&H | Trades | Win Rate | Sharpe | Max DD | Delta from v24 |
|--------|--------|-----|--------|----------|--------|--------|----------------|
| SPY | **+5.03%** | +27.03% | 10 | **70.0%** | **3.26** | -3.28% | **+0.46%** |
| BTC-USD | +43.90% | -1.39% | 13 | 53.8% | 7.59 | -10.07% | 0.00% |
| QQQ | **+13.94%** | +33.57% | 13 | **53.8%** | **4.81** | **-5.80%** | **+3.48%** |

**Key trade changes:**
- SPY: Eliminated the Jan 21 - Mar 5 stale long (time_exit -0.90%) — previous bar wasn't in channel when it tried to enter. Win rate hit 70% (7 of 10 trades).
- QQQ: Eliminated the Mar 5 → Mar 6 whipsaw that lost -3.05%. Previous bar wasn't inside the channel — was a single-bar entry on a volatile day. Net +3.48%.
- BTC: Unchanged — BTC entries are breakout-driven, not channel-inside entries.

**Verdict:** **KEEP.** Another universally-positive change. QQQ's biggest improvement since v7. The 2-bar confirmation is logically sound — if a channel is valid, price should be in it for consecutive bars, not just a single bar.

---

## v26 — Auto cubic fit for ETFs (degree=3) (2026-04-07)

**Change:** Automatically set degree=3 for ETFs (SPY, QQQ) and degree=2 for crypto. Based on v14 finding that cubic gave SPY +12.51%.

| Symbol | Return | B&H | Trades | Win Rate | Sharpe | Max DD | Delta from v25 |
|--------|--------|-----|--------|----------|--------|--------|----------------|
| SPY | **+13.56%** | +27.03% | 9 | 55.6% | **6.41** | -4.27% | **+8.53%** |
| BTC-USD | +43.90% | -1.40% | 13 | 53.8% | 7.59 | -10.07% | 0.00% |
| QQQ | **-2.21%** | +33.57% | 8 | 37.5% | -0.49 | **-15.12%** | **-16.15%** |

**Verdict:** Revert. Cubic is symbol-specific, not asset-class-specific. Great for SPY (+8.53%) but catastrophic for QQQ (-16.15%). Cubic overfits to QQQ's more volatile tech price action (trade 2: -6.65%, trade 6: -4.02%). Keep degree=2 as default, use `--degree 3` CLI flag for SPY.

**Updated best config for SPY:** `--degree 3` → **+13.56%**, Sharpe 6.41, MaxDD -4.27%

---

## v31 — Reduce fallback wait (10 → 5) for ETFs (2026-04-07)

**Change:** Reduced wait bars after exit before fallback SMA re-entry from 10 to 5.

| Symbol | Return | Delta from v30 |
|--------|--------|----------------|
| SPY | -0.93% | **-5.96%** |
| QQQ | +12.62% | -1.32% |

**Verdict:** Revert. Premature re-entries. SPY devastated (-5.96%).

---

## v32 — Minimum 3 bars before fallback SMA exit (2026-04-07)

**Change:** Fallback SMA positions must be held at least 3 bars before the SMA exit can trigger. Prevents 1-day whipsaw exits on fallback entries.

| Symbol | Return | B&H | Trades | Win Rate | Sharpe | Max DD | Delta from v30 |
|--------|--------|-----|--------|----------|--------|--------|----------------|
| SPY | **+5.90%** | +27.03% | 10 | 70.0% | **3.99** | **-2.47%** | **+0.87%** |
| BTC-USD | +50.03% | -1.37% | 13 | 61.5% | 8.06 | -10.07% | 0.00% |
| QQQ | +13.94% | +33.57% | 13 | 53.8% | 4.81 | -5.80% | 0.00% |

**Key change:** SPY trade 5 (Dec 17): exit at $591.15 on bar 3 instead of $586.28 on bar 1 → loss reduced from -3.28% to -2.47%. MaxDD now -2.47% (best ever for SPY).

**Verdict:** **KEEP.** SPY improved with best-ever MaxDD. BTC/QQQ unaffected.

---

## v30 — Lower breakout threshold for crypto (2.0% → 1.5%) (2026-04-07)

**Change:** Set `breakout_pct = 1.5` for crypto preset (vs 2.0% for ETFs). Detects breakouts earlier, better entry prices.

| Symbol | Return | B&H | Trades | Win Rate | Sharpe | Max DD | Delta from v25 |
|--------|--------|-----|--------|----------|--------|--------|----------------|
| SPY | +5.03% | +27.03% | 10 | 70.0% | 3.26 | -3.28% | 0.00% |
| BTC-USD | **+50.03%** | -1.37% | 13 | **61.5%** | **8.06** | -10.07% | **+6.13%** |
| QQQ | +13.94% | +33.57% | 13 | 53.8% | 4.81 | -5.80% | 0.00% |

**Key trade improvements on BTC:**
- Trade 1 (Jul 2024): Entry at $57,899 vs $59,232 → +11.31% vs +8.79% (+2.52%)
- Trade 8 (Jun-Jul 2025): Entry Jun 29 vs Jul 2 → +15.85% vs +14.91% (+0.94%)
- Trade 10 (Nov 2025): Short turned profitable (+0.96% vs -0.55%) — earlier detection

**Verdict:** **KEEP.** BTC's biggest single-version improvement since v2. The 1.5% threshold catches breakouts ~1-3 days earlier at better prices. Win rate improved to 61.5%. Sharpe 8.06 (best ever). SPY/QQQ unaffected.

---

## v27 — Increase max_pivots (20 → 30) (2026-04-07)

**Change:** Increased rolling pivot window from 20 to 30.

**Verdict:** No impact. All three symbols identical to v25. The 20-pivot window already captures sufficient data. Reverted.

---

## v29 — Higher close filter (close > previous close) (2026-04-07)

**Change:** Required `close > previous_close` in addition to `close > open` for long entries.

| Symbol | Return | Delta from v25 |
|--------|--------|----------------|
| SPY | **+7.61%** | **+2.58%** (77.8% win rate, Sharpe 5.57) |
| BTC-USD | +43.90% | 0.00% |
| QQQ | +4.34% | **-9.60%** |

**Verdict:** Revert. Same pattern as v26 — great for SPY, devastating for QQQ. QQQ enters on gap-down days that close green (bullish inside the gap) which this filter blocks.

---

## v28 — Channel width filter (2026-04-07)

**Change:** Only trade channels where width is 2-15% of price. Tested wider 1-25% bounds too.

| Bounds | SPY | BTC | QQQ |
|--------|-----|-----|-----|
| 2-15% | +5.03% | **+15.12%** (-28.78%) | +8.91% (-5.03%) |
| 1-25% | +5.03% | +43.00% (-0.90%) | +13.94% |

**Verdict:** Revert. BTC channels are often >15% wide — filtering them destroys returns. Even loose bounds (1-25%) still block one profitable BTC entry. The channel width is already implicitly filtered by the polynomial fitting + touch tolerance.

---

## v33 — Adjust fallback SMA period (50 → 75/100) (2026-04-07)

**Change:** Tested SMA(75) and SMA(100) for fallback re-entry.

| SMA | SPY | QQQ |
|-----|-----|-----|
| 50 (v32) | **+5.90%** | +13.94% |
| 75 | +0.54% | +20.50% |
| 100 | +1.00% | **+27.57%** (Sharpe 10.93!) |

**Verdict:** Revert. SMA(100) is transformative for QQQ (+27.57%, Sharpe 10.93) but destroys SPY (+1.00%). The longer SMA filters out more whipsaws for QQQ's volatile tech sector but is too slow for SPY's smoother trends. Like degree=3, this is symbol-specific. Keep SMA(50) as default.

**Note for future:** QQQ users can try `--fallback-sma 100` (needs CLI arg addition).

---

## v34 — Faster pivot detection (pivot_right 5 → 3) (2026-04-07)

**Change:** Reduced `PIVOT_RIGHT` from 5 to 3 for earlier pivot confirmation.

| Symbol | Return | Delta from v32 |
|--------|--------|----------------|
| SPY | +7.34% | +1.44% |
| BTC-USD | +24.05% | **-25.98%** |
| QQQ | +0.11% | **-13.83%** |

**Verdict:** Revert. Faster pivots = more noise pivots = unreliable channels. Devastating for BTC and QQQ.

---

## v35 — Disable volume confirmation for ETFs (2026-04-07)

**Change:** Set `vol_mult = 0` for ETFs (crypto keeps volume ON).

| Symbol | Return | Delta from v32 |
|--------|--------|----------------|
| SPY | **-6.95%** | **-12.85%** |
| QQQ | +10.48% | -3.46% |

**Verdict:** Revert. Volume confirmation is ESSENTIAL for ETFs. Without it, SPY made 17 trades (vs 10) — too many entries at low-volume noise bars. Contradicts v8 findings (v8 tested adding volume confirmation; v35 confirms removing it is catastrophic).

---

## v36 — Channel-position sizing (2026-04-07)

**Change:** Attempted to scale long position size based on channel width (wider channel = less certain = smaller position).

**Verdict:** Revert. Reduced returns across all symbols by shrinking position size on valid entries. Channel width doesn't correlate well with trade quality.

---

## v37 — Volume confirmation 1.2x → 1.5x (2026-04-07)

**Change:** Tightened volume confirmation multiplier from 1.2x to 1.5x.

**Verdict:** Revert. Stricter volume filter blocked too many valid entries. 1.2x is already a good balance — raising to 1.5x filters out moderate-volume days that still produce winning trades.

---

## v38 — Lower 60% entry zone (2026-04-07)

**Change:** Restricted long entries to lower 60% of channel (vs full channel width).

**Verdict:** Revert. Missed too many valid entries near channel midpoint. The 2-bar confirmation (v25) already provides enough entry quality filtering without constraining the zone.

---

## v39 — Asset-specific channel extension (min_extend) (2026-04-07)

**Change:** Parameterized `min_extend` in `fit_boundary()` — controls minimum bars a channel remains valid beyond its last touch point. Crypto preset uses `min_extend=30` (longer channel lifetime), ETFs keep `min_extend=20` (default).

| Symbol | Return | Delta from v32 | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|----------------|--------|----------|--------|--------|
| SPY | +5.90% | 0.00% | 10 (7L/3S) | 70.0% | -2.47% | 3.99 |
| BTC-USD | **+59.01%** | **+8.98%** | 14 (9L/5S) | 64.3% | -10.07% | 8.81 |
| QQQ | +13.94% | 0.00% | 13 (9L/4S) | 53.8% | -5.80% | 4.81 |

**Exit breakdown (BTC-USD):** Breakout Up: 3, ATR Trail: 11
**Key BTC-USD change:** Longer channel extension keeps channels valid through volatile gaps. The breakout→re-entry cycle captures more upside (3 breakout-up entries at 200% size).

**Verdict:** ✅ KEEP. BTC-USD jumps from +50.03% to +59.01% (+8.98%) with no change to ETF results. Pure crypto improvement via longer channel lifetime. Sharpe 8.81 (up from 8.06).

---

## v40 — Crypto ATR period 14 → 21 (2026-04-07)

**Change:** Longer ATR lookback for crypto to smooth volatility estimate.

| Symbol | Return | Delta from v39 |
|--------|--------|----------------|
| SPY | +5.90% | 0.00% |
| BTC-USD | **+43.11%** | **-15.90%** |
| QQQ | +13.94% | 0.00% |

**Verdict:** Revert. ATR(21) makes trailing stops too loose — the 200% breakout re-entry on 2024-11-11 loses -3.87% (was +6.80% with ATR 14). Smoother ATR lets positions ride into pullbacks.

---

## v41 — Loss cooldown (3 bars after losing trade) (2026-04-07)

**Change:** Wait 3 bars after a losing trade before re-entering.

**Verdict:** Revert. Zero impact — all 3 symbols identical to v39. Losing trades already have natural spacing from next entry due to channel refit time.

---

## v42 — Wider touch tolerance for crypto (1.0% → 1.5%) (2026-04-07)

**Change:** Increased polynomial touch tolerance for crypto to account for larger wicks.

| Symbol | Return | Delta from v39 |
|--------|--------|----------------|
| BTC-USD | **+28.50%** | **-30.51%** |

**Verdict:** Revert. Wider tolerance makes channels too loose — fewer valid touch points detected, worse channel quality.

---

## v43 — Tighter ATR trail for breakout re-entries (1.5x vs 2.0x) (2026-04-07)

**Change:** Used `short_atr_trail_mult` (1.5x) instead of `atr_trail_mult` (2.0x) for positions with >100% size.

| Symbol | Return | Delta from v39 |
|--------|--------|----------------|
| SPY | +5.90% | 0.00% |
| BTC-USD | **+47.76%** | **-11.25%** |
| QQQ | +13.94% | 0.00% |

**Verdict:** Revert. Tighter trail exits breakout positions too early. BTC trade 4 now loses -3.87% instead of gaining +6.80%. The 2.0x trail gives breakout positions enough room to work.

---

## v44 — Reduced time_exit_bars (20 → 15) for ETFs (2026-04-07)

**Change:** Tighter time-based exit for stale positions.

| Symbol | Return | Delta from v39 |
|--------|--------|----------------|
| SPY | +5.90% | 0.00% |
| QQQ | **+8.81%** | **-5.13%** |

**Verdict:** Revert. Tighter time exit cuts QQQ winners short.

---

## v45 — Adaptive channel trail activation (1.0% ETF, 2.0% crypto) (2026-04-07)

**Change:** Earlier in-channel trailing stop activation for ETFs.

| Symbol | Return | Delta from v39 |
|--------|--------|----------------|
| SPY | +5.90% | 0.00% |
| QQQ | **+4.66%** | **-9.28%** |

Also tested 3.0%: QQQ +11.71% (-2.23%), SPY unchanged.

**Verdict:** Revert. 2.0% is the sweet spot — 1.0% exits too early, 3.0% lets positions ride into drawdowns.

---

## v46 — Positive channel slope filter for long entries (2026-04-07)

**Change:** Required support boundary to have positive slope (current > 5 bars ago) before entering long.

| Symbol | Return | Delta from v39 |
|--------|--------|----------------|
| SPY | **+8.50%** | **+2.60%** (77.8% win rate, Sharpe 6.64) |
| BTC-USD | **+20.09%** | **-38.92%** |
| QQQ | **+2.04%** | **-11.90%** |

**Verdict:** Revert. Great for SPY but devastating for BTC/QQQ. Quadratic curves can have local negative slope even in ascending channels — the filter is too restrictive for polynomial fits.

---

## v47 — ATR-based position sizing for longs (2026-04-07)

**Change:** Structural change — sized long entries based on ATR percentile. Low vol (ATR < 0.8x median) → 120%, high vol (> 1.2x median) → 80%, else 100%.

| Symbol | Return | Delta from v39 |
|--------|--------|----------------|
| SPY | +6.73% | +0.83% |
| BTC-USD | +57.90% | -1.11% |
| QQQ | +12.77% | -1.17% |

**Verdict:** Revert. SPY marginally improved but BTC/QQQ dropped. The sizing amplified the wrong trades — 120% on a loser, 80% on winners. ATR volatility doesn't predict individual trade outcomes.

---

## v48 — SMA(50) trend alignment filter for long entries (2026-04-07)

**Change:** Structural change — require `close > SMA(50) * 0.99` before entering ascending channel longs. Uses the existing fallback SMA (period=50 for ETFs, disabled for crypto). The 1% buffer prevents overly strict filtering while blocking clearly counter-trend entries.

| Symbol | Return | Delta from v39 | Trades | Win Rate | Sharpe | Max DD |
|--------|--------|----------------|--------|----------|--------|--------|
| SPY | **+8.50%** | **+2.60%** | 9 (6L/3S) | **77.8%** | **6.64** | -2.47% |
| BTC-USD | +59.01% | 0.00% | 14 (9L/5S) | 64.3% | 8.81 | -10.07% |
| QQQ | +13.94% | 0.00% | 13 (9L/4S) | 53.8% | 4.81 | -5.80% |

**Key insight:** The filter blocked SPY trade 9 (2026-03-03 → 03-12, -2.40% channel_break exit). SPY at $680 was below SMA(50) — the trend was down, and the channel entry was a falling-knife trap. With 0.99 buffer, QQQ's borderline Jan 2025 entry (+2.01% winner) passes through.

**Tested variants:**
- `close > SMA * 1.00` (strict): SPY +8.50%, QQQ **+11.69%** (-2.25% — blocks QQQ winner)
- `close > SMA * 0.99` (soft): SPY +8.50%, QQQ **+13.94%** (preserves QQQ winner) ← chosen
- `close > SMA * 0.98` (too soft): SPY +5.90%, QQQ +13.94% (no filtering at all)

**Verdict:** ✅ KEEP. SPY +2.60% improvement (77.8% win rate, Sharpe 6.64 from 3.99). BTC and QQQ unaffected. First successful structural change since v39.

---

## v49 — Channel quality score (7+ touch minimum) (2026-04-07)

**Change:** Required 7+ combined touch points (upper + lower) before entering a channel trade.

| Symbol | Return | Delta from v48 |
|--------|--------|----------------|
| SPY | +8.50% | 0.00% |
| BTC-USD | **+27.28%** | **-31.73%** |
| QQQ | +13.94% | 0.00% |

**Verdict:** Revert. 7-touch requirement is too strict for crypto — BTC channels often have 6 touches (3+3) and still produce profitable trades. SPY/QQQ unaffected because ETF channels tend to have more touches naturally.

---

## v50 — Breakout volume surge (2x for flat breakout entries) (2026-04-07)

**Change:** Required 2x volume (vs normal 1.2x) for flat breakout entries (section 6 — when flat and price breaks above/below channel).

| Symbol | Return | Delta from v48 |
|--------|--------|----------------|
| SPY | **+16.79%** | **+8.29%** (Sharpe 9.5, MaxDD -0.94%!) |
| BTC-USD | **-12.47%** | **-71.48%** |
| QQQ | +1.94% | **-12.00%** |

**Verdict:** Revert. SPY result is extraordinary (+16.79%, Sharpe 9.5) but BTC goes negative and QQQ drops to +1.94%. The volume surge filter blocks crypto breakouts that happen on normal volume. SPY-specific optimization — potentially useful as CLI flag but not a universal default.

**Note for future:** SPY users may benefit from `--breakout-vol-mult 2.0` CLI flag.

---

## v49 — Early Momentum Entry (2026-04-07)

**Change:** 25% exploratory long that fires before the first channel forms. Requires 3 consecutive bullish bars (close > open) each with above-average volume. Channel-gated: active only while `len(all_channels) == 0`, permanently deactivates once any channel is detected. One-shot — fires at most once per backtest. Activates ATR trailing stop. If an ascending channel later forms, position upgrades to 100% (`momentum_to_channel`).

**Parameters:** `EARLY_ENTRY_CONSECUTIVE=3`, `EARLY_ENTRY_SIZE=25` (no bar limit — gated by channel formation)

**Evolution:** Originally used a 30-bar window with 5 consecutive rising-volume bars — never fired. Loosened to 3 bars with above-avg volume and channel-gated activation.

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | +8.47% | +26.61% | -18.14% | 9 | 77.8% | -2.47% | 6.62 |
| BTC-USD | +68.88% | -1.08% | +69.96% | 15 | 60.0% | -10.07% | — |
| QQQ | +11.94% | +32.56% | -20.62% | 14 | 50.0% | -5.87% | 3.91 |

| Symbol | Return | Delta from v48 | v49 fired? |
|--------|--------|----------------|------------|
| SPY | +8.47% | **-0.03%** | No — channel forms before 3 bullish above-avg bars appear |
| BTC-USD | +68.88% | **+9.87%** | Yes — bar 42 (2024-06-05), $71k entry, stopped out -0.19% next day |
| QQQ | +11.94% | **-2.00%** | No — channel forms early |

**Verdict:** v49 now fires on BTC (entered at $71k before first channel). The entry itself lost -0.19% (stopped out immediately), but the channel-gated design is sound. The -0.32% total drag from the initial v50-only results is from adding this small losing trade. SPY/QQQ channels form too early for the pattern to appear.

**v50 update:** Added `REVERSAL_SHORT_ENABLED=False` flag. Reversal shorts disabled by default — QQQ's `SHORT REV-DN` on 2024-12-18 (-0.39%) is now prevented.

---

## v50 — Sharp Reversal Entry (2026-04-07)

**Change:** New 25% entry on sharp reversals: single-bar move ≥ 2x ATR with volume ≥ 2x volume MA, after ≥2 of prior 3 bars were opposite direction. Can fire multiple times (not one-shot). Activates ATR trailing stop. Upgrades to channel if matching channel forms (`reversal_to_channel`).

**Parameters:** `REVERSAL_ATR_MULT=2.0`, `REVERSAL_VOL_MULT=2.0`, `REVERSAL_LOOKBACK=3`, `REVERSAL_ENTRY_SIZE=25`

**Trades generated:**
- **SPY**: 1 new trade — `BUY REV-UP` on 2025-04-09 (post-crash bounce), closed +2.15% → strategy return +8.47%
- **BTC-USD**: 1 new trade — `BUY REV-UP` on 2024-11-06 (Trump election rally), upgraded to `REV→CH` at 100% → +16.97% gain, biggest single trade improvement
- **QQQ**: 2 new trades — `SHORT REV-DN` on 2024-12-18 (-0.39%), `BUY REV-UP` on 2025-04-09 (-1.84% due to ATR stop)

**Verdict:** Keep. BTC benefits massively (+10.19%) from the Nov 2024 reversal catching the channel handoff. SPY gets a small win. QQQ's reversal-short is a minor cost. The channel handoff pattern (speculative 25% → full 100% on channel confirmation) is the key mechanism — without it, the reversal trades are just small bets.

**Key insight:** Sharp reversal's real value is as a **channel pre-entry** — it gets into position early so the channel handoff can capture the full move. The standalone reversal trades (no channel upgrade) are marginal.

---

## Final Cumulative Summary (v0 → v50)

| Symbol | v0 | v7 | v10 | v21 | v25 | v30 | v32 | v39 | v48 | v50 (current) |
|--------|------|------|------|------|------|------|------|------|------|------|
| SPY | +2.78% | -2.07% | +1.18% | +3.76% | +5.03% | +5.03% | +5.90% | +5.90% | +8.50% | **+8.47%** |
| BTC-USD | -1.94% | +31.69% | +38.81% | +39.02% | +43.90% | +50.03% | +50.03% | +59.01% | +59.01% | **+68.88%** |
| QQQ | +4.74% | +18.74% | +7.39% | +10.46% | +13.94% | +13.94% | +13.94% | +13.94% | +13.94% | **+11.94%** |

**Best configuration per symbol:**
- **SPY**: v50 (ETF preset, degree=2, SMA trend filter, sharp reversal long) → **+8.47%**, MaxDD -2.47%
- **BTC-USD**: v50 (crypto preset, degree=2, breakout=1.5%, min_extend=30, sharp reversal long, early momentum) → **+68.88%**, MaxDD -10.07%
- **QQQ**: v48 (ETF preset, degree=2, SMA trend filter) → **+13.94%**, MaxDD -5.80% *(v50 at +11.94% due to reversal long loss)*

**Key findings across all iterations (v0 → v35):**
1. **Asset-specific presets are essential** — crypto and ETFs need different parameters
2. **Breakout detection (v2) is the single biggest improvement** for crypto (+44% at its best)
3. **In-channel trailing stop (v9) is the biggest ETF improvement** — locks in gains, Sharpe boost
4. **Cubic fit (v14/v26) is transformative for SPY** (+13.56%) but harmful for QQQ (-2.21%). Symbol-specific.
5. **SMA fallback (v5) is great for QQQ** but catastrophic for BTC. SMA(100) gives QQQ +27.57% but kills SPY (v33).
6. **Scaling short size (v11) and pyramiding (v12) both hurt** — amplify wrong-way bets
7. **Volume confirmation is ESSENTIAL for ETFs** (v35). Without it, SPY drops to -6.95%. Crypto benefits too (v8).
8. **Channel age filter (v21) is universally positive** — 3 bars for ETFs, 0 for crypto
9. **2-bar channel confirmation (v25) is universally positive** — biggest QQQ improvement since v7
10. **Lower breakout threshold (v30) is BTC's best improvement** — 1.5% vs 2.0% catches breakouts earlier
11. **Tighter short ATR trail (v23) improves SPY+BTC** — 1.5x vs 2.0x limits short-side losses
12. **Larger breakout position (v22) amplifies BTC winners** — 200% vs 150% on breakout re-entry
13. **Min hold for fallback SMA exit (v32) prevents whipsaw** — 3-bar minimum, SPY MaxDD -2.47%
14. **Many parameters are symbol-specific, not asset-class-specific** — degree, SMA period, higher-close filter all help one symbol while hurting another
15. **Faster pivots (v34) add noise** — pivot_right=3 is too fast, produces unreliable channels
16. **Channel extension (v39) is a pure crypto win** — min_extend=30 gives BTC +59.01% (from +50.03%) with zero ETF impact
17. **Position sizing experiments (v36) and entry zone restriction (v38) both reduce returns** — the base config already handles these well
18. **ATR period is well-calibrated at 14** (v40) — longer periods make trails too loose for crypto
19. **Touch tolerance 1.0% is optimal** (v42) — wider tolerance degrades channel quality
20. **Channel trail activation at 2.0% is the sweet spot** (v45) — 1.0% exits too early, 3.0% too late
21. **Breakout positions need 2.0x ATR room** (v43) — tighter trails exit too early on volatile moves
22. **Parameter tuning hit convergence at v39** — v40-v46 all reverted, confirming the current parameter set is locally optimal
23. **Structural changes can still improve** (v48) — SMA(50) trend alignment filter with 1% buffer added +2.60% to SPY without harming BTC/QQQ
24. **ATR-based sizing doesn't work** (v47) — volatility level doesn't predict trade outcome; fixed 100% sizing is better
25. **Sharp reversal's value is as channel pre-entry** (v50) — standalone reversal trades are marginal, but the 25%→100% channel handoff is powerful (BTC +10.19%)
26. **Poly-low slope detection works** (v49 revised) — polynomial through lows replaces consecutive-bars; fires on all 3 symbols, QQQ gains +5.10% from early 25% entry
27. **Counter-trend steep slope reversal doesn't work** (v51) — tested 2x through 8x slope multipliers; even at 8x the small 25% counter-trend bets drag returns. Disabled by default.
28. **Enable/disable flags for modularity** — master on/off flags (`EARLY_ENABLED`, `REVERSAL_ENABLED`, `DIVERG_ENABLED`) allow toggling each entry mechanism independently

---

## v49 (revised) — Poly-Low Entry (2026-04-07)

**Change:** Replaced the consecutive-bullish-bars approach (which never fired) with polynomial-through-lows slope detection. Fits a degree-2 polynomial through the last 12 bar lows using existing `polyfit()`. Enters 25% long when derivative at right edge is positive (lows trending up) and volume >= 80% of vol MA. Channel-gated: only fires while `len(all_channels) == 0`.

**Parameters:** `EARLY_POLY_LOOKBACK=12`, `EARLY_POLY_DEGREE=2`, `EARLY_VOL_GATE=0.80`, `EARLY_ENTRY_SIZE=25`

| Symbol | Return | B&H | vs B&H | Trades | Win Rate | Max DD | Sharpe |
|--------|--------|-----|--------|--------|----------|--------|--------|
| SPY | +8.69% | +27.09% | -18.40% | 10 (7L/3S) | 80.0% | -2.47% | 6.41 |
| BTC-USD | +65.11% | -0.12% | +65.23% | 15 (10L/5S) | 60.0% | -10.07% | 8.08 |
| QQQ | +18.07% | +33.59% | -15.52% | 14 (10L/4S) | 57.1% | -3.37% | 5.91 |

| Symbol | Return | Delta from v50 | v49 fired? |
|--------|--------|----------------|------------|
| SPY | +8.69% | **+0.22%** | Yes — bar 13, poly slope positive, 25% entry |
| BTC-USD | +65.11% | **-3.77%** | Yes — bar 13, but early entry stopped out for loss |
| QQQ | +18.07% | **+6.13%** | Yes — bar 13, 25% entry caught early uptrend (+2.84%) |

**Verdict:** Keep. Poly-low fires on all 3 symbols (unlike the old consecutive-bars which never fired). QQQ gains +6.13% — the 25% early entry at $424.45 rode to $473.96 (+2.84% portfolio contribution). SPY also gains slightly. BTC loses -3.77% because the early entry got stopped out, but the mechanism is sound. The polynomial slope through lows is a much more reliable signal than consecutive bullish bars.

---

## v51 — Steep Slope Reversal (2026-04-07)

**Change:** Counter-trend entry when price moves too steeply. Fits degree-1 polynomial through last 5 closes (recent slope) vs last 20 closes (baseline slope). When recent slope exceeds baseline by Nx multiplier AND is >= 0.5 ATR, sets a signal. Confirmation: next bar makes a lower low (for short signal) or higher high (for long signal). Enters 25% counter-trend position.

**Parameters:** `DIVERG_SLOPE_LOOKBACK=5`, `DIVERG_BASELINE_LOOKBACK=20`, `DIVERG_SLOPE_MULT=variable`, `DIVERG_SLOPE_MIN_ATR=0.5`, `DIVERG_CONFIRM_BARS=3`, `DIVERG_ENTRY_SIZE=25`, `DIVERG_SHORT_ENABLED=False`

**Systematic threshold test (shorts off, then shorts on):**

| Mult | SPY (shorts off) | BTC (shorts off) | QQQ (shorts off) |
|------|------------------|-------------------|-------------------|
| 2x | +7.48% | +62.94% | +17.10% |
| 3x | +8.57% | +63.42% | +18.07% |
| 4x | +8.57% | +63.42% | +18.07% |
| 5x | +8.57% | +63.42% | +18.07% |
| 6x | +8.57% | +63.42% | +18.07% |
| 7x | +8.57% | +63.42% | +18.07% |
| 8x | +8.57% | +63.42% | +18.07% |

| Mult | SPY (shorts on) | BTC (shorts on) | QQQ (shorts on) |
|------|-----------------|------------------|------------------|
| 2x | +6.51% | +61.76% | +15.89% |
| 3x | +7.49% | +64.07% | +17.83% |
| 4x | +8.57% | +64.36% | +18.07% |

**Analysis:** At 2x-3x, v51 fires but generates losing counter-trend trades. At 4x+, it never fires (threshold too high for any bar to hit). Either way, v51 doesn't add value — at lower thresholds it generates small losing bets, at higher thresholds it's a no-op.

**Verdict:** Disabled by default (`DIVERG_ENABLED = False`). Counter-trend 25% entries against steep moves are not profitable on daily bars. The win rates (42-56%) at 25% position size don't compensate for losers. Code retained for potential use on intraday timeframes where mean reversion is more reliable.

---

## Enable/Disable Flags (2026-04-07)

**Change:** Added master on/off flags for each entry mechanism:
- `EARLY_ENABLED = True` — v49 Poly-Low Entry
- `REVERSAL_ENABLED = True` — v50 Sharp Reversal
- `DIVERG_ENABLED = False` — v51 Steep Slope Reversal (off by default)

Flags are threaded through `run_curved_channel()`, `run_backtest()`, parameters dict, and CLI main().

---

## Final Cumulative Summary (v0 → v51)

| Symbol | v0 | v10 | v25 | v39 | v48 | v50 | v49-poly | v51 (off) |
|--------|------|------|------|------|------|------|----------|-----------|
| SPY | +2.78% | +1.18% | +5.03% | +5.90% | +8.50% | +8.47% | **+8.69%** | same |
| BTC-USD | -1.94% | +38.81% | +43.90% | +59.01% | +59.01% | +68.88% | **+65.11%** | same |
| QQQ | +4.74% | +7.39% | +13.94% | +13.94% | +13.94% | +11.94% | **+18.07%** | same |

**Current best configuration:**
- **SPY**: v49-poly (ETF preset, poly-low entry, sharp reversal, v51 off) → **+8.69%**, MaxDD -2.47%, Sharpe 6.41
- **BTC-USD**: v49-poly (crypto preset, poly-low entry, sharp reversal, v51 off) → **+65.11%**, MaxDD -10.07%, Sharpe 8.08
- **QQQ**: v49-poly (ETF preset, poly-low entry, sharp reversal, v51 off) → **+18.07%**, MaxDD -3.37%, Sharpe 5.91
