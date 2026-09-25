# Bugs to Fix

Running log of bugs noticed while working on this project: what happens, how to reproduce it,
what causes it, and how it was fixed. Keep entries once fixed so they can be referred back to.

For the earlier read-only code review, see `potential issues found by Claude.md`.

**Status values:** `OPEN` (not fixed) · `WORKAROUND` (test or user-side workaround, root cause still there) · `FIXED`.

## Entry template

```
## BUG-NNN: Short title — STATUS
- **Found:** YYYY-MM-DD, branch, how it was noticed
- **Where:** file(s) and function(s)
- **Symptom:** what the user or test sees
- **Reproduce:** numbered steps
- **Cause:** confirmed root cause (or "unknown" + best guess, clearly labeled)
- **Fix / what needs to be done:** planned fix, or what was done once fixed
- **Fixed in:** commit hash + date (when fixed)
```

---

## BUG-001: Chart throws "Value is null" when reloading after a strategy switch — FIXED

- **Found:** 2026-09-25, branch `claude`. The strengthened dashboard browser test
  (`tests/dashboard_ui_smoke.mjs`) failed with `Browser errors: Value is null`.
- **Where:** `src/tradingview_mcp/ui/static/app.js` → `updateDashboard()`. The error was thrown
  inside Lightweight Charts v4.1.3 (`static/lightweight-charts.standalone.production.js`).
- **Symptom:** The browser console logged `Uncaught Error: Value is null`, one to three times.
  The chart still ended up drawn correctly, so users couldn't see it. It failed the browser
  test, which treats any browser error as a failure.
- **Reproduce (before the fix):**
  1. Start the dashboard: `./start.command` (or `uv run python src/tradingview_mcp/ui/server.py`).
  2. Open it in Chrome with DevTools → Console open.
  3. Click the **Advanced** tab. Pick resolution **12H** and range **5Y**.
  4. Change the strategy dropdown to **Bollinger**, then back to **Sloped Lines**.
     (Sloped Lines loads its saved best parameters, which resets the chart to 1D / 1Y.)
  5. Trigger any reload of the chart: click range **5Y**, or the **Regular** tab.
  6. `Value is null` appears in the console shortly after the reload.

  Automated: `npm run test:ui`. The test's final step (click 5Y right after switching back to
  Sloped Lines) is exactly this sequence, so it now guards against the bug coming back.
  Waiting before the click did **not** avoid the bug; it isn't a click-timing issue.
- **Cause (confirmed):** The main chart shares one time scale across the candles and every
  overlay line. `updateDashboard()` loaded the new candles first and removed the previous
  trendline/channel overlay series only later, after the new trendlines were fetched. Removing
  series after the swap shifted the shared time-scale positions under the new candles, so the
  library looked up bars at positions that no longer existed. Two stack traces, same cause
  (captured with the non-minified `lightweight-charts@4.1.3` development build):
  ```
  Error: Value is null
    at ensureNotNull
    at TimeScale._internal_timeRangeForLogicalRange
    at TimeScaleApi.getVisibleRange
    at TimeScaleApi._private__onVisibleBarsChanged      <- visible-time-range event
    ...
  Error: Value is null
    at ensureNotNull
    at SeriesBarColorer.Candlestick                     <- drawing a candle
    at SeriesCandlesticksPaneView._internal__createRawItem
    ...
  ```
  Dead end, recorded so it isn't retried: switching the listener from
  `subscribeVisibleTimeRangeChange` to `subscribeVisibleLogicalRangeChange` removed the first
  trace but not the second. It wasn't needed once the real cause was fixed, so it was reverted.
- **Fix:** In `updateDashboard()`, remove the old trendline and channel overlay series *before*
  `candlestickSeries.setData(...)`. New overlays are added after the new candles, as before.
  Side effect: during a reload the old lines vanish right away instead of staying until the new
  ones arrive.
- **Verified:** `npm run test:ui` passed 3/3 runs; 38/38 Python tests pass. On the Advanced tab,
  dragging and zooming the main chart still keeps the volume and RSI panels aligned (checked with
  a Playwright script, no browser errors).
- **Fixed in:** see `git log -- BUGS_TO_FIX.md` (commit "Fix chart error when overlays change,
  test sloped-line drawing"), 2026-09-25.
