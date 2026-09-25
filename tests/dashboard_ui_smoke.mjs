import assert from 'node:assert/strict';
import net from 'node:net';
import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright-core';

const ROOT = new URL('..', import.meta.url).pathname.replace(/\/$/, '');
const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
].filter(Boolean);

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitForServer(url, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`Dashboard did not start within ${timeoutMs}ms: ${url}`);
}

async function startDashboard() {
  if (process.env.DASHBOARD_URL) {
    return { url: process.env.DASHBOARD_URL.replace(/\/$/, ''), process: null };
  }
  const port = await freePort();
  const python = existsSync(`${ROOT}/.venv/bin/python`) ? `${ROOT}/.venv/bin/python` : 'python3';
  const child = spawn(
    python,
    ['-m', 'uvicorn', 'tradingview_mcp.ui.server:app', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: ROOT,
      env: { ...process.env, PYTHONPATH: `${ROOT}/src` },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  let output = '';
  child.stdout.on('data', chunk => { output += chunk; });
  child.stderr.on('data', chunk => { output += chunk; });
  const url = `http://127.0.0.1:${port}`;
  try {
    await waitForServer(url);
  } catch (error) {
    child.kill('SIGTERM');
    throw new Error(`${error.message}\n${output}`);
  }
  return { url, process: child };
}

async function waitForChart(page, resolution, timeframe) {
  await page.waitForFunction(
    ({ resolution, timeframe }) => {
      const chart = document.querySelector('#tv-chart');
      const loading = document.querySelector('#loading');
      return chart?.dataset.renderStatus === 'ready'
        && chart.dataset.resolution === resolution
        && chart.dataset.timeframe === timeframe
        && Number(chart.dataset.candleCount) > 0
        && !loading?.classList.contains('active');
    },
    { resolution, timeframe },
    { timeout: 90_000 },
  );
}

async function waitForAnyChart(page) {
  await page.waitForFunction(
    () => {
      const chart = document.querySelector('#tv-chart');
      const loading = document.querySelector('#loading');
      return chart?.dataset.renderStatus === 'ready'
        && Number(chart.dataset.candleCount) > 0
        && !loading?.classList.contains('active');
    },
    null,
    { timeout: 90_000 },
  );
}

async function waitForStrategyChart(page, strategy) {
  await page.waitForFunction(
    strategy => {
      const chart = document.querySelector('#tv-chart');
      const loading = document.querySelector('#loading');
      return chart?.dataset.renderStatus === 'ready'
        && chart.dataset.strategy === strategy
        && Number(chart.dataset.candleCount) > 0
        && document.querySelectorAll('#tv-chart canvas').length > 0
        && !loading?.classList.contains('active');
    },
    strategy,
    { timeout: 90_000 },
  );
}

async function readChartState(page) {
  return page.evaluate(() => {
    const chart = document.querySelector('#tv-chart');
    const rect = chart?.getBoundingClientRect();
    const firstBuyIndex = Number(chart?.dataset.firstBuyIndex ?? -1);
    const visibleStartIndex = Number(chart?.dataset.visibleStartIndex ?? -1);
    const visibleEndIndex = Number(chart?.dataset.visibleEndIndex ?? -1);
    return {
      candleCount: Number(chart?.dataset.candleCount ?? 0),
      resolution: chart?.dataset.resolution,
      timeframe: chart?.dataset.timeframe,
      strategy: chart?.dataset.strategy,
      symbol: chart?.dataset.symbol,
      width: rect?.width ?? 0,
      height: rect?.height ?? 0,
      canvases: document.querySelectorAll('#tv-chart canvas').length,
      firstBuyIndex,
      visibleStartIndex,
      visibleEndIndex,
      advancedActive: document.querySelector('#tab-advanced')?.classList.contains('active') ?? false,
      volumeCanvases: document.querySelectorAll('#volume-chart canvas').length,
      rsiCanvases: document.querySelectorAll('#rsi-chart canvas').length,
      volumePoints: Number(document.querySelector('#volume-chart')?.dataset.pointCount ?? 0),
      rsiPoints: Number(document.querySelector('#rsi-chart')?.dataset.pointCount ?? 0),
      tradeCount: Number(chart?.dataset.tradeCount ?? 0),
      markerCount: Number(chart?.dataset.markerCount ?? 0),
      trendlinesReturned: Number(chart?.dataset.trendlinesReturned ?? 0),
      trendlinesDrawn: Number(chart?.dataset.trendlinesDrawn ?? 0),
    };
  });
}

function assertRenderedGraph(state, context) {
  assert.ok(state.candleCount > 0, `${context}: no candle data`);
  assert.ok(state.canvases > 0, `${context}: chart canvas missing`);
  assert.ok(state.width > 300 && state.height > 300, `${context}: chart has invalid dimensions`);
  assert.ok(state.visibleEndIndex >= state.visibleStartIndex, `${context}: viewport is invalid`);
  if (state.firstBuyIndex >= 0) {
    assert.ok(
      state.firstBuyIndex >= state.visibleStartIndex && state.firstBuyIndex <= state.visibleStartIndex + 3,
      `${context}: first buy is not at the left edge of the viewport`,
    );
  }
}

async function waitForSlopedChart(page, resolution, timeframe) {
  await page.waitForFunction(
    ({ resolution, timeframe }) => {
      const chart = document.querySelector('#tv-chart');
      const loading = document.querySelector('#loading');
      return chart?.dataset.renderStatus === 'ready'
        && chart.dataset.strategy === 'sloped_lines'
        && chart.dataset.resolution === resolution
        && chart.dataset.timeframe === timeframe
        && Number(chart.dataset.candleCount) > 0
        && !loading?.classList.contains('active');
    },
    { resolution, timeframe },
    { timeout: 90_000 },
  );
}

function assertSlopedOverlays(state, context) {
  assert.equal(state.strategy, 'sloped_lines', `${context}: wrong strategy`);
  assert.ok(state.trendlinesReturned > 0, `${context}: backend returned no sloped trendlines`);
  assert.ok(state.trendlinesDrawn > 0, `${context}: ${state.trendlinesReturned} trendlines returned but none drawn`);
  assert.ok(state.tradeCount > 0, `${context}: no sloped-lines trades to mark`);
  assert.ok(state.markerCount > 0, `${context}: ${state.tradeCount} trades but no chart markers`);
}

const dashboard = await startDashboard();
const executablePath = CHROME_CANDIDATES.find(existsSync);
assert.ok(executablePath, 'Chrome or Edge is required. Set CHROME_PATH to its executable.');

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));

try {
  await page.goto(`${dashboard.url}/?ui-smoke=${Date.now()}`, { waitUntil: 'domcontentloaded' });
  await waitForAnyChart(page);

  const axisLabels = await page.evaluate(() => ({
    fourAm: formatMarketAxisTick(Date.UTC(2026, 6, 21, 8) / 1000, 3),
    fiveAm: formatMarketAxisTick(Date.UTC(2026, 6, 21, 9) / 1000, 3),
    dateBoundary: formatMarketAxisTick(Date.UTC(2026, 6, 21, 8) / 1000, 2),
  }));
  assert.deepEqual(axisLabels, {
    fourAm: '4',
    fiveAm: '5',
    dateBoundary: 'Jul 21',
  });

  const slopedMarkerStyles = await page.evaluate(() => ({
    lineBuy: getSlopedEntryMarkerStyle('breakout', true),
    reclaimBuy: getSlopedEntryMarkerStyle('exit_peak_reclaim', true),
    lineSell: getSlopedExitMarkerStyle('support_break', true, false),
    protectionSell: getSlopedExitMarkerStyle('entry_barrier_break', true, false),
    endOfDataSell: getSlopedExitMarkerStyle('end_of_data', true, true),
    savedBadge: document.querySelector('#best-params-badge')?.textContent,
  }));
  assert.deepEqual(slopedMarkerStyles.lineBuy, {
    markerClass: 'sloped-line-signal', prefix: 'LINE BREAKOUT ', color: '#059669',
  });
  assert.deepEqual(slopedMarkerStyles.reclaimBuy, {
    markerClass: 'sloped-reentry', prefix: 'PEAK RECLAIM ', color: '#6EE7B7',
  });
  assert.deepEqual(slopedMarkerStyles.lineSell, {
    markerClass: 'sloped-line-signal', prefix: 'LINE SUPPORT BREAK ', color: '#DC2626',
  });
  assert.deepEqual(slopedMarkerStyles.protectionSell, {
    markerClass: 'sloped-protection', prefix: 'ENTRY BARRIER ', color: '#F59E0B',
  });
  assert.deepEqual(slopedMarkerStyles.endOfDataSell, {
    markerClass: 'sloped-end-of-data', prefix: 'END OF DATA ', color: '#94A3B8',
  });
  assert.match(slopedMarkerStyles.savedBadge || '', /Saved Best.*baseline/);

  const sessionControls = await page.evaluate(() => {
    const select = document.querySelector('#trading-window-select');
    const originalValue = select.value;
    const windows = {};
    for (const value of ['regular market', 'pre-market', 'after hours', 'extended hours', 'overnight']) {
      select.value = value;
      windows[value] = {
        active: getActiveTradingWindow(),
        preMarket: activeTradingWindowIncludes('pre-market'),
        regular: activeTradingWindowIncludes('regular market'),
        afterHours: activeTradingWindowIncludes('after hours'),
        overnight: activeTradingWindowIncludes('overnight'),
      };
    }
    select.value = originalValue;
    return {
      optionValues: Array.from(select.options, option => option.value),
      optionLabels: Array.from(select.options, option => option.textContent),
      legacyCheckboxes: document.querySelectorAll('#before-hours-checkbox, #after-hours-checkbox').length,
      windows,
    };
  });
  assert.deepEqual(sessionControls.optionValues, [
    'regular market', 'pre-market', 'after hours', 'extended hours', 'overnight',
  ]);
  assert.deepEqual(sessionControls.optionLabels, [
    'Regular market (9:30 AM–4:00 PM)',
    'Pre-market + regular (4:00 AM–4:00 PM)',
    'Regular + after hours (9:30 AM–8:00 PM)',
    'Extended session (4:00 AM–8:00 PM)',
    'All sessions / overnight (12:00 AM–11:59 PM)',
  ]);
  assert.equal(sessionControls.legacyCheckboxes, 0);
  assert.deepEqual(sessionControls.windows, {
    'regular market': { active: 'regular market', preMarket: false, regular: true, afterHours: false, overnight: false },
    'pre-market': { active: 'pre-market', preMarket: true, regular: true, afterHours: false, overnight: false },
    'after hours': { active: 'after hours', preMarket: false, regular: true, afterHours: true, overnight: false },
    'extended hours': { active: 'extended hours', preMarket: true, regular: true, afterHours: true, overnight: false },
    overnight: { active: 'overnight', preMarket: true, regular: true, afterHours: true, overnight: true },
  });
  const legacyWindows = await page.evaluate(() => ({
    neither: tradingWindowFromLegacySessionPreferences('false', 'false'),
    before: tradingWindowFromLegacySessionPreferences('true', 'false'),
    after: tradingWindowFromLegacySessionPreferences('false', 'true'),
    both: tradingWindowFromLegacySessionPreferences('true', 'true'),
  }));
  assert.deepEqual(legacyWindows, {
    neither: null,
    before: 'pre-market',
    after: 'after hours',
    both: 'extended hours',
  });

  const panes = ['regular', 'advanced'];
  const resolutions = ['1d', '4h', '12h'];
  const timeframes = ['3mo', '1y', '5y'];
  const results = [];

  for (const pane of panes) {
    await page.locator(`#tab-${pane}`).click();
    for (const resolution of resolutions) {
      await page.locator(`#btn-res-${resolution}`).click();
      for (const timeframe of timeframes) {
        await page.locator(`#btn-range-${timeframe}`).click();
        await waitForChart(page, resolution, timeframe);
        const state = await readChartState(page);
        const context = `${pane} ${resolution}/${timeframe}`;
        assert.equal(state.advancedActive, pane === 'advanced', `${context}: wrong pane active`);
        assertRenderedGraph(state, context);
        if (pane === 'advanced') {
          assert.ok(state.volumeCanvases > 0 && state.volumePoints > 0, `${context}: volume graph missing`);
          assert.ok(state.rsiCanvases > 0 && state.rsiPoints > 0, `${context}: RSI graph missing`);
        }
        results.push({ pane, resolution, timeframe, candles: state.candleCount });
      }
    }
  }

  await page.locator('#strategy-select').selectOption('sloped_lines');
  await waitForStrategyChart(page, 'sloped_lines');
  assertRenderedGraph(await readChartState(page), 'advanced sloped lines before strategy switch');

  await page.locator('#strategy-select').selectOption('bollinger');
  await waitForStrategyChart(page, 'bollinger');
  assertRenderedGraph(await readChartState(page), 'advanced Bollinger after strategy switch');

  await page.locator('#strategy-select').selectOption('sloped_lines');
  await waitForStrategyChart(page, 'sloped_lines');
  assertRenderedGraph(await readChartState(page), 'advanced sloped lines after strategy switch');

  // Five years of daily bars reliably contains sloped-line breakouts, so lines and markers must be drawn.
  await page.locator('#btn-res-1d').click();
  await page.locator('#btn-range-5y').click();
  await waitForSlopedChart(page, '1d', '5y');
  const slopedState = await readChartState(page);
  assertRenderedGraph(slopedState, 'sloped lines 1d/5y');
  assertSlopedOverlays(slopedState, 'sloped lines 1d/5y');
  results.push({
    strategy: 'sloped_lines',
    resolution: '1d',
    timeframe: '5y',
    candles: slopedState.candleCount,
    trades: slopedState.tradeCount,
    markers: slopedState.markerCount,
    trendlines: slopedState.trendlinesDrawn,
  });

  assert.deepEqual(pageErrors, [], `Browser errors: ${pageErrors.join('; ')}`);
  console.log(JSON.stringify({ passed: results.length, results }, null, 2));
} finally {
  await browser.close();
  if (dashboard.process) {
    dashboard.process.kill('SIGTERM');
    await new Promise(resolve => dashboard.process.once('exit', resolve));
  }
}
