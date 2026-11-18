import { INDICATOR_STYLE } from '../chartConfig.js';
import { findFairValueGaps } from '../indicators.js';
import { memoizeByCandles } from './candleData.js';

const COLORS = INDICATOR_STYLE.fvg;

// Series primitive drawing FVG boxes behind the candles. Open gaps extend
// to the right edge; filled gaps stop at the filling candle and fade.
export class FairValueGapPrimitive {
  constructor() {
    this.chart = null;
    this.series = null;
    this.gapsFor = memoizeByCandles(findFairValueGaps);
    this.paneView = {
      zOrder: () => 'bottom',
      renderer: () => ({ draw: (target) => this.draw(target) }),
    };
  }

  attached({ chart, series }) {
    this.chart = chart;
    this.series = series;
  }

  detached() {
    this.chart = null;
    this.series = null;
  }

  paneViews() {
    return [this.paneView];
  }

  draw(target) {
    if (!this.series) return;
    const gaps = this.gapsFor(this.series.data());
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      gaps.forEach((gap) => this.drawGap(context, gap, mediaSize.width));
    });
  }

  drawGap(context, gap, paneWidth) {
    const timeScale = this.chart.timeScale();
    const left = timeScale.timeToCoordinate(gap.startTime);
    const right = gap.endTime === null ? paneWidth : timeScale.timeToCoordinate(gap.endTime);
    const top = this.series.priceToCoordinate(gap.top);
    const bottom = this.series.priceToCoordinate(gap.bottom);

    if ([left, right, top, bottom].includes(null)) return;
    if (right < 0 || left > paneWidth) return;

    context.fillStyle = COLORS[gap.type][gap.endTime === null ? 'open' : 'filled'];
    context.fillRect(left, top, right - left, bottom - top);
  }
}
