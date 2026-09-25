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

const dashboard = await startDashboard();
const executablePath = CHROME_CANDIDATES.find(existsSync);
assert.ok(executablePath, 'Chrome or Edge is required. Set CHROME_PATH to its executable.');

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));

try {
  await page.goto(`${dashboard.url}/?ui-smoke=${Date.now()}`, { waitUntil: 'domcontentloaded' });
  await waitForChart(page, '1d', '1y');

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

  assert.deepEqual(pageErrors, [], `Browser errors: ${pageErrors.join('; ')}`);
  console.log(JSON.stringify({ passed: results.length, results }, null, 2));
} finally {
  await browser.close();
  if (dashboard.process) {
    dashboard.process.kill('SIGTERM');
    await new Promise(resolve => dashboard.process.once('exit', resolve));
  }
}
