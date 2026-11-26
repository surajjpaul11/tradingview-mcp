import { drawingSegments } from '../drawings.js';

// Draw directly on the candle pane so previews and annotations never change
// the price range or insert extra bars into the chart's shared time scale.
export class DrawingPrimitive {
  constructor() {
    this.drawings = [];
    this.draft = null;
    this.candles = [];
    this.interval = 60;
    this.paneView = {
      zOrder: () => 'top',
      renderer: () => ({ draw: (target) => this.draw(target) }),
    };
  }

  attached({ chart, series, requestUpdate }) {
    this.chart = chart;
    this.series = series;
    this.requestUpdate = requestUpdate;
  }

  detached() {
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
  }

  paneViews() { return [this.paneView]; }

  update({ drawings = this.drawings, draft = this.draft, candles = this.candles, interval = this.interval }) {
    Object.assign(this, { drawings, draft, candles, interval });
    this.requestUpdate?.();
  }

  coordinate(point) {
    const scale = this.chart.timeScale();
    let x = scale.timeToCoordinate(point.time);
    if (x === null && this.candles.length) {
      const first = this.candles[0].time;
      const last = this.candles.at(-1).time;
      const logical = point.time < first ? (point.time - first) / this.interval
        : point.time > last ? this.candles.length - 1 + (point.time - last) / this.interval
          : scale.timeToIndex(point.time, true);
      if (logical !== null) x = scale.logicalToCoordinate(logical);
    }
    const y = this.series.priceToCoordinate(point.price);
    return x === null || y === null ? null : { x, y };
  }

  draw(target) {
    if (!this.series) return;
    target.useMediaCoordinateSpace(({ context }) => {
      context.save();
      for (const drawing of [...this.drawings, ...(this.draft ? [this.draft] : [])]) {
        const draft = drawing === this.draft;
        for (const segment of drawingSegments(drawing)) {
          const [first, second] = segment.points.map((point) => this.coordinate(point));
          if (!first || !second) continue;
          context.strokeStyle = segment.role === 'line' ? '#f59e0b' : '#22d3ee';
          context.lineWidth = 2;
          context.setLineDash(draft || segment.role === 'midline' ? [6, 4] : []);
          context.beginPath();
          context.moveTo(first.x, first.y);
          context.lineTo(second.x, second.y);
          context.stroke();
        }
        context.setLineDash([]);
        for (const point of drawing.points) {
          const coordinate = this.coordinate(point);
          if (!coordinate) continue;
          context.beginPath();
          context.arc(coordinate.x, coordinate.y, 4, 0, Math.PI * 2);
          context.fillStyle = drawing.type === 'trendline' ? '#f59e0b' : '#22d3ee';
          context.fill();
          context.strokeStyle = '#fff';
          context.lineWidth = 1;
          context.stroke();
        }
      }
      context.restore();
    });
  }
}
