export const DRAWING_TOOLS = {
  cursor: { label: 'Cursor', points: 0 },
  trendline: { label: 'Straight Line', points: 2 },
  parallel_channel: { label: 'Parallel Channel', points: 3 },
};

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
  if (points[0].time === points[1].time) return null;
  return { id, type, points: points.map(({ time, price }) => ({ time, price })) };
}
