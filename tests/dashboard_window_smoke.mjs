import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

// Exercise the real dashboard and chart library with deterministic market data.
const staticRoot = new URL('../src/tradingview_mcp/ui/static/', import.meta.url);
const candles = Array.from({ length: 100 }, (_, i) => ({
  time: 1735750800 + i * 86400, open: 200 + i, high: 203 + i,
  low: 199 + i, close: 202 + i, volume: 1000000 + i * 1000,
}));
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
const strategyRequests = [];
const savedWindow = { start_date: '2025-09-26', end_date: '2026-09-25', trading_window: 'regular market' };
const savedSignals = { line_breakout_buy: true, entry_barrier_sell: true };
page.setDefaultTimeout(10000);
page.on('pageerror', error => errors.push(error.message));
await page.route('**/*', async route => {
  const url = new URL(route.request().url());
  if (url.hostname !== 'dashboard.test') return route.abort();
  if (url.pathname.startsWith('/api/')) {
    strategyRequests.push({ path: url.pathname, query: url.searchParams });
    const payload = url.pathname === '/api/filters' ? { symbols: ['AAPL'], strategies: ['sloped_lines'] }
      : url.pathname === '/api/best-parameters' ? { found: true, data: { timeframe: '1d', period: '1y', backtest_window: savedWindow, parameters: { ...savedSignals }, performance: { total_pnl_pct: 47.61 } } }
      : url.pathname === '/api/candles' ? { candles }
      : url.pathname === '/api/trades' ? { trades: [] }
      : url.pathname === '/api/trendlines' ? { trendlines: [] }
      : url.pathname === '/api/market-status' ? { configured_default_window: 'regular market' }
      : {};
    return route.fulfill({ json: payload });
  }
  const filename = url.pathname === '/' ? 'index.html' : url.pathname.replace('/static/', '');
  const contentType = filename.endsWith('.css') ? 'text/css'
    : filename.endsWith('.js') ? 'application/javascript' : 'text/html';
  return route.fulfill({ body: await readFile(new URL(filename, staticRoot)), contentType });
});

const mode = expected => page.waitForFunction(value =>
  document.querySelector('#chart-window').dataset.displayMode === value, expected);
const settle = () => page.evaluate(() => new Promise(resolve =>
  requestAnimationFrame(() => requestAnimationFrame(resolve))));
const bounds = () => page.locator('#chart-window').boundingBox();

try {
  await page.goto('http://dashboard.test/');
  await page.waitForFunction(() => document.querySelector('#tv-chart').dataset.renderStatus === 'ready');
  const compounding = page.getByRole('checkbox', { name: 'Compounding', exact: true });
  const capital = page.getByLabel('Starting Capital ($)', { exact: true });
  assert.equal(await compounding.isChecked(), true);
  assert.equal(await capital.inputValue(), '10000');
  const breakout = page.getByRole('checkbox', { name: 'Line Breakout Buy', exact: true });
  const barrier = page.getByRole('checkbox', { name: 'Entry Barrier Sell', exact: true });
  assert.equal(await breakout.isChecked(), false);
  assert.equal(await barrier.isChecked(), false);
  for (const path of ['/api/trades', '/api/stats', '/api/trendlines']) {
    const request = strategyRequests.find(request => request.path === path);
    assert.equal(request.query.get('line_breakout_buy'), 'false');
    assert.equal(request.query.get('entry_barrier_sell'), 'false');
  }
  const peakFull = page.getByRole('checkbox', { name: 'Peak Reclaim Full Candle', exact: true });
  const generalFull = page.getByRole('checkbox', { name: 'Full Candle', exact: true });
  assert.equal(await peakFull.isChecked(), false);
  const peakResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === '/api/stats' && url.searchParams.get('peak_reclaim_full_candle') === 'true'
      && url.searchParams.get('full_candle') === 'false';
  });
  await peakFull.check();
  await peakResponse;
  assert.equal(await generalFull.isChecked(), false);
  await generalFull.check();
  assert.equal(await peakFull.isChecked(), true);
  await generalFull.uncheck();
  assert.equal(await peakFull.isChecked(), true);
  const fixedResponse = page.waitForResponse(response => response.url().includes('/api/stats?') && response.url().includes('compounding=false'));
  await compounding.uncheck();
  await fixedResponse;
  const capitalResponse = page.waitForResponse(response => response.url().includes('/api/stats?') && response.url().includes('initial_capital=500'));
  await capital.fill('500');
  await capital.press('Tab');
  await capitalResponse;
  const toggledResponse = page.waitForResponse(response => response.url().includes('/api/trendlines?')
    && response.url().includes('line_breakout_buy=true') && response.url().includes('entry_barrier_sell=true'));
  await page.locator('#best-params-badge').click();
  await toggledResponse;
  assert.equal(await peakFull.isChecked(), false);
  assert.equal(await compounding.isChecked(), true);
  assert.equal(await capital.inputValue(), '10000');
  assert.equal(await breakout.isChecked(), true);
  assert.equal(await barrier.isChecked(), true);
  for (const path of ['/api/trades', '/api/stats', '/api/trendlines']) {
    assert.ok(strategyRequests.some(request => request.path === path
      && request.query.get('line_breakout_buy') === 'true' && request.query.get('entry_barrier_sell') === 'true'));
  }
  assert.equal(await page.locator('#saved-window-controls').isVisible(), true);
  assert.match(await page.locator('#saved-window-label').innerText(), /2025-09-26.*2026-09-25/);
  for (const path of ['/api/candles', '/api/trades', '/api/stats', '/api/trendlines']) {
    assert.ok(strategyRequests.some(request => request.path === path
      && request.query.get('start_date') === savedWindow.start_date && request.query.get('end_date') === savedWindow.end_date));
  }
  const rollingResponse = page.waitForResponse(response => response.url().includes('/api/stats?') && !response.url().includes('start_date='));
  await page.getByRole('button', { name: 'Use rolling range', exact: true }).click();
  await rollingResponse;
  assert.equal(await page.locator('#saved-window-controls').isVisible(), false);
  savedSignals.line_breakout_buy = false;
  savedSignals.entry_barrier_sell = false;
  const disabledResponse = page.waitForResponse(response => response.url().includes('/api/trendlines?')
    && response.url().includes('line_breakout_buy=false') && response.url().includes('entry_barrier_sell=false'));
  await page.locator('#best-params-badge').click();
  await disabledResponse;
  assert.equal(await breakout.isChecked(), false);
  assert.equal(await barrier.isChecked(), false);
  await page.getByRole('button', { name: 'Use rolling range', exact: true }).click();
  await settle();
  await page.evaluate(() => {
    window.originalChart = chart;
    chart.timeScale().setVisibleLogicalRange({ from: 20, to: 60 });
  });
  await settle();
  const initialBounds = await bounds();
  const assertRestored = async () => {
    const restored = await bounds();
    // Playwright may scroll the page to reach the header; dimensions must restore.
    assert.equal(restored.width, initialBounds.width);
    assert.equal(restored.height, initialBounds.height);
    assert.equal(restored.x, initialBounds.x);
  };
  const initialRange = await page.evaluate(() => chart.timeScale().getVisibleLogicalRange());

  await page.getByRole('button', { name: 'Minimize chart', exact: true }).click();
  await mode('minimized');
  assert.equal(await page.locator('#chart-workspace').isVisible(), false);
  assert.ok((await bounds()).height < 60);
  await page.getByRole('button', { name: 'Restore chart size', exact: true }).click();
  await mode('normal');
  await settle();
  await assertRestored();

  await page.getByRole('button', { name: 'Fullscreen chart', exact: true }).click();
  await mode('fullscreen');
  await page.waitForFunction(() => document.fullscreenElement?.id === 'chart-window');
  await settle();
  const fullscreenBounds = await bounds();
  assert.equal(fullscreenBounds.x, 0);
  assert.equal(fullscreenBounds.y, 0);
  assert.equal(fullscreenBounds.width, 1440);
  assert.equal(fullscreenBounds.height, 1100);
  await page.getByRole('button', { name: 'Restore chart size', exact: true }).click();
  await mode('normal');
  await page.waitForFunction(() => !document.fullscreenElement);
  await settle();
  await assertRestored();

  await page.getByRole('button', { name: 'Fullscreen chart', exact: true }).click();
  await page.waitForFunction(() => document.fullscreenElement);
  await page.getByRole('button', { name: 'Minimize chart', exact: true }).click();
  await mode('minimized');
  await page.waitForFunction(() => !document.fullscreenElement);
  await page.getByRole('button', { name: 'Restore chart size', exact: true }).click();
  await mode('normal');

  // Native fullscreen exit (including browser Escape) restores dashboard state.
  await page.getByRole('button', { name: 'Fullscreen chart', exact: true }).click();
  await page.waitForFunction(() => document.fullscreenElement);
  await page.evaluate(() => document.exitFullscreen());
  await mode('normal');

  // Force rejection to verify embedded browsers still get viewport fullscreen.
  await page.evaluate(() => {
    document.querySelector('#chart-window').requestFullscreen = () => Promise.reject(new Error('Unavailable'));
  });
  await page.getByRole('button', { name: 'Fullscreen chart', exact: true }).click();
  await mode('fullscreen');
  await page.keyboard.press('Escape');
  await mode('normal');
  await page.getByRole('button', { name: 'Fullscreen chart', exact: true }).click();
  await mode('fullscreen');
  await page.getByRole('button', { name: 'Minimize chart', exact: true }).click();
  await mode('minimized');
  assert.equal(await page.evaluate(() => document.body.classList.contains('chart-fullscreen-active')), false);
  await page.getByRole('button', { name: 'Restore chart size', exact: true }).click();
  await mode('normal');
  await settle();
  assert.equal(await page.evaluate(() => chart === window.originalChart), true);
  const finalRange = await page.evaluate(() => chart.timeScale().getVisibleLogicalRange());
  assert.ok(Math.abs(initialRange.from - finalRange.from) < 0.01);
  assert.ok(Math.abs(initialRange.to - finalRange.to) < 0.01);

  // Indicators and controls remain usable in fullscreen at a smaller viewport.
  await page.locator('#tab-advanced').click();
  await page.setViewportSize({ width: 800, height: 700 });
  await page.getByRole('button', { name: 'Fullscreen chart', exact: true }).click();
  await mode('fullscreen');
  await settle();
  assert.equal(await page.locator('#volume-indicator-pane').isVisible(), true);
  assert.equal(await page.locator('#rsi-indicator-pane').isVisible(), true);
  const chartBounds = await page.locator('#tv-chart').boundingBox();
  assert.ok(chartBounds.width > 650 && chartBounds.height > 200);
  if (process.env.CHART_WINDOW_SCREENSHOT) await page.screenshot({ path: process.env.CHART_WINDOW_SCREENSHOT });
  await page.keyboard.press('Escape');
  await mode('normal');
  assert.deepEqual(errors, []);
  console.log('Dashboard chart window smoke checks passed.');
} finally {
  await browser.close();
}
