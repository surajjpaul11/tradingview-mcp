// Recomputes only when the series data changes (new bar or a live update to the last one).
export function memoizeByCandles(compute) {
  let lastKey = null;
  let lastResult = null;

  return (candles) => {
    const last = candles.at(-1);
    const key = last ? `${candles.length}:${last.time}:${last.high}:${last.low}:${last.close}` : '';
    if (key !== lastKey) {
      lastKey = key;
      lastResult = compute(candles);
    }
    return lastResult;
  };
}

// Logical indexes map 1:1 to data indexes for a single series without whitespace bars.
export function getVisibleCandles(chart, candles) {
  const range = chart.timeScale().getVisibleLogicalRange();
  if (!range) return [];
  const from = Math.max(0, Math.ceil(range.from));
  const to = Math.min(candles.length - 1, Math.floor(range.to));
  return candles.slice(from, to + 1);
}
