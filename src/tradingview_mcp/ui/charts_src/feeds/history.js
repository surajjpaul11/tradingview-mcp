import { findRange } from '../timeframes.js';

export async function fetchChartHistory(symbol, resolutionId, rangeId, signal, tradingWindow = 'regular market') {
  const range = findRange(rangeId);
  const query = new URLSearchParams({
    source: symbol.source,
    symbol: symbol.id,
    timeframe: resolutionId,
    period: range.period,
    trading_window: tradingWindow,
  });
  const response = await fetch(`/api/chart/candles?${query}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${symbol.label}: HTTP ${response.status}`);
  }
  const data = await response.json();
  return (data.candles || []).sort((a, b) => a.time - b.time);
}
