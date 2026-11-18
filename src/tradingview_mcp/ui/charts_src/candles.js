// Pure helpers for building coarser candles (e.g. 4h from 1h) when a source
// doesn't offer a resolution natively. Candles are { time, open, high, low, close, volume }.

export const bucketStart = (time, bucketSeconds) =>
  Math.floor(time / bucketSeconds) * bucketSeconds;

function mergeBars(time, bars) {
  const sorted = [...bars].sort((a, b) => a.time - b.time);
  return {
    time,
    open: sorted[0].open,
    high: Math.max(...sorted.map((bar) => bar.high)),
    low: Math.min(...sorted.map((bar) => bar.low)),
    close: sorted.at(-1).close,
    volume: sorted.reduce((total, bar) => total + bar.volume, 0),
  };
}

// Groups time-ordered candles into buckets of bucketSeconds.
export function aggregateCandles(candles, bucketSeconds) {
  const buckets = new Map();
  candles.forEach((candle) => {
    const time = bucketStart(candle.time, bucketSeconds);
    if (!buckets.has(time)) buckets.set(time, []);
    buckets.get(time).push(candle);
  });
  return [...buckets].map(([time, bars]) => mergeBars(time, bars));
}

// Folds a stream of live base candles into the current coarse bucket.
// Returns the updated coarse candle, or null for a candle older than the bucket.
export function createLiveAggregator(bucketSeconds) {
  let bucketTime = null;
  const bars = new Map();

  return (candle) => {
    const time = bucketStart(candle.time, bucketSeconds);
    if (bucketTime !== null && time < bucketTime) return null;
    if (time !== bucketTime) {
      bucketTime = time;
      bars.clear();
    }
    bars.set(candle.time, candle);
    return mergeBars(time, bars.values());
  };
}
