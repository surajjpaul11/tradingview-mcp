// Pure indicator math. Candles are { time, open, high, low, close, volume }.

// ---------- Fair Value Gap ----------

function detectGap(first, third) {
  if (first.high < third.low) return { type: 'bullish', top: third.low, bottom: first.high };
  if (first.low > third.high) return { type: 'bearish', top: first.low, bottom: third.high };
  return null;
}

// A gap is filled once price trades back through its far edge.
function findFillIndex(candles, gap, fromIndex) {
  for (let index = fromIndex; index < candles.length; index += 1) {
    const candle = candles[index];
    const filled = gap.type === 'bullish' ? candle.low <= gap.bottom : candle.high >= gap.top;
    if (filled) return index;
  }
  return null;
}

// Returns gaps spanning C1..C3. endTime is the candle that filled the gap,
// or null while it is still open (drawn extending to the right edge).
export function findFairValueGaps(candles) {
  const gaps = [];
  for (let index = 2; index < candles.length; index += 1) {
    const gap = detectGap(candles[index - 2], candles[index]);
    if (!gap) continue;
    const fillIndex = findFillIndex(candles, gap, index + 1);
    gaps.push({
      ...gap,
      startTime: candles[index - 2].time,
      endTime: fillIndex === null ? null : candles[fillIndex].time,
    });
  }
  return gaps;
}

// ---------- Volume Profile ----------

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

// Spreads a candle's volume across the bins its high-low range covers,
// assuming volume traded evenly through the range.
function distributeVolume(candle, priceLow, binSize, volumes) {
  const lastBin = volumes.length - 1;
  const firstBin = clamp(Math.floor((candle.low - priceLow) / binSize), 0, lastBin);
  const endBin = clamp(Math.floor((candle.high - priceLow) / binSize), 0, lastBin);
  const range = candle.high - candle.low;

  if (range === 0 || firstBin === endBin) {
    volumes[firstBin] += candle.volume;
    return;
  }
  for (let bin = firstBin; bin <= endBin; bin += 1) {
    const binLow = priceLow + bin * binSize;
    const overlap = Math.min(candle.high, binLow + binSize) - Math.max(candle.low, binLow);
    volumes[bin] += (candle.volume * Math.max(overlap, 0)) / range;
  }
}

// Returns { bins: [{ low, high, volume }], maxVolume, pocIndex } or null when empty.
export function buildVolumeProfile(candles, binCount) {
  if (candles.length === 0 || binCount < 1) return null;

  const priceLow = Math.min(...candles.map((candle) => candle.low));
  const priceHigh = Math.max(...candles.map((candle) => candle.high));
  const binSize = (priceHigh - priceLow) / binCount || 1;
  const volumes = new Array(binCount).fill(0);

  candles.forEach((candle) => distributeVolume(candle, priceLow, binSize, volumes));

  const maxVolume = Math.max(...volumes);
  return {
    bins: volumes.map((volume, index) => ({
      low: priceLow + index * binSize,
      high: priceLow + (index + 1) * binSize,
      volume,
    })),
    maxVolume,
    pocIndex: volumes.indexOf(maxVolume),
  };
}
