import { findRange } from '../timeframes.js';

export async function fetchChartHistory(symbol, resolutionId, rangeId, signal, tradingWindow = 'regular market', backtestWindow = null) {
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
  }
  const response = await fetch(`/api/chart/candles?${query}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${symbol.label}: HTTP ${response.status}`);
  }
  const data = await response.json();
  return (data.candles || []).sort((a, b) => a.time - b.time);
}
