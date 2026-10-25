import { findRange } from '../timeframes.js';

const pendingHistory = new Map();
export const historyRequestKey=(symbol,resolutionId,rangeId,tradingWindow,backtestWindow)=>
  JSON.stringify([symbol.source,symbol.id,resolutionId,rangeId,tradingWindow,backtestWindow]);


async function loadChartHistory(symbol, resolutionId, rangeId, signal, tradingWindow = 'regular market', backtestWindow = null) {
  const range = findRange(rangeId);
  const query = new URLSearchParams({
    source: symbol.source,
    symbol: symbol.id,
    timeframe: resolutionId,
    period: range.period,
    trading_window: tradingWindow,
  });
  if (backtestWindow) {
    query.set('start_date', backtestWindow.start_date);
    query.set('end_date', backtestWindow.end_date);
    if (backtestWindow.snapshot_id) query.set('snapshot_id', backtestWindow.snapshot_id);
  }
  const response = await fetch(`/api/chart/candles?${query}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${symbol.label}: HTTP ${response.status}`);
  }
  const data = await response.json();
  const candles = (data.candles || []).sort((a, b) => a.time - b.time);
  candles.dataStatus = data.data_status;
  return candles;
}

export async function fetchChartHistory(symbol, resolutionId, rangeId, signal, tradingWindow = 'regular market', backtestWindow = null) {
  const key = historyRequestKey(symbol,resolutionId,rangeId,tradingWindow,backtestWindow);
  // Independent subscribers cannot cancel one another's shared backend request.
  let entry = pendingHistory.get(key);
  if (!entry || Date.now() - entry.at > 5000) {
    entry = {at: Date.now(), promise: loadChartHistory(symbol, resolutionId, rangeId, undefined, tradingWindow, backtestWindow)};
    pendingHistory.set(key, entry);
    entry.promise.catch(() => { if (pendingHistory.get(key) === entry) pendingHistory.delete(key); });
    if (pendingHistory.size > 100) pendingHistory.delete(pendingHistory.keys().next().value);
  }
  const result = await entry.promise;
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  return result;
}
