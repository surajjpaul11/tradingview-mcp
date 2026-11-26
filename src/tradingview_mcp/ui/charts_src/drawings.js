export const DRAWING_TOOLS = {
  cursor: { label: 'Cursor', points: 0 },
  trendline: { label: 'Straight Line', points: 2 },
  parallel_channel: { label: 'Parallel Channel', points: 3 },
};

export function drawingHint(tool, progress) {
  if (tool === 'trendline') return progress ? 'Click the end point of your line.' : 'Click the start point of your line.';
  if (tool === 'parallel_channel') return ['Click the first point of the channel baseline.', 'Click the second point of the channel baseline.', 'Click to set the channel width.'][progress];
  return '';
}

// Use the visible logical scale, including the empty space beyond the last bar.
// Mapping x as a fraction of all history places anchors incorrectly after zooming.
export function drawingPoint(logical, price, candles, interval) {
  if (!Number.isFinite(logical) || !Number.isFinite(price) || !candles.length) return null;
  const index = Math.round(logical);
  const last = candles.length - 1;
  const time = candles[index]?.time ?? (index < 0
    ? candles[0].time + index * interval
    : candles[last].time + (index - last) * interval);
  return { time, price };
}

const line = (first, second, role) => ({ role, points: [first, second] });

export function drawingSegments(drawing) {
  const points = drawing?.points || [];
  if (drawing?.type === 'trendline' && points.length === 2) {
    return [line(points[0], points[1], 'line')];
  }
  if (drawing?.type !== 'parallel_channel' || points.length !== 3) return [];
  const [first, second, offsetAnchor] = points;
  const timeDelta = second.time - first.time;
  if (!timeDelta) return [];
  const slope = (second.price - first.price) / timeDelta;
  const baselineAtOffset = first.price + slope * (offsetAnchor.time - first.time);
  const offset = offsetAnchor.price - baselineAtOffset;
  return [
    line(first, second, 'boundary'),
    line({ ...first, price: first.price + offset }, { ...second, price: second.price + offset }, 'boundary'),
    line({ ...first, price: first.price + offset / 2 }, { ...second, price: second.price + offset / 2 }, 'midline'),
  ];
}

export function createDrawing(type, points, id = `${type}-${Date.now()}`) {
  const required = DRAWING_TOOLS[type]?.points ?? 0;
  if (!required || points.length !== required) return null;
  if (points.some(({ time, price }) => !Number.isFinite(time) || !Number.isFinite(price))) return null;
  if (points[0].time === points[1].time && (type === 'parallel_channel' || points[0].price === points[1].price)) return null;
  return { id, type, points: points.map(({ time, price }) => ({ time, price })) };
}
