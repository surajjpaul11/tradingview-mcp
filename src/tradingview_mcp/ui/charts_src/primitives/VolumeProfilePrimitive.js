import { INDICATOR_STYLE } from '../chartConfig.js';
import { buildVolumeProfile } from '../indicators.js';
import { fromSeriesBar } from '../seriesBars.js';
import { getVisibleCandles } from './candleData.js';

const STYLE = INDICATOR_STYLE.volumeProfile;

// Series primitive drawing a visible-range volume profile as a horizontal
// histogram anchored to the right edge of the pane (next to the price axis).
// Recomputed on every draw so it follows scrolling and zooming.
export class VolumeProfilePrimitive {
  constructor() {
    this.chart = null;
    this.series = null;
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
    const visible = getVisibleCandles(this.chart, this.series.data()).map(fromSeriesBar);
    const profile = buildVolumeProfile(visible, STYLE.rows);
    if (!profile || profile.maxVolume === 0) return;

    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      const maxWidth = mediaSize.width * STYLE.maxWidthRatio;
      profile.bins.forEach((bin, index) => {
        this.drawBin(context, bin, index === profile.pocIndex, {
          paneWidth: mediaSize.width,
          width: (bin.volume / profile.maxVolume) * maxWidth,
        });
      });
    });
  }

  drawBin(context, bin, isPoc, { paneWidth, width }) {
    const top = this.series.priceToCoordinate(bin.high);
    const bottom = this.series.priceToCoordinate(bin.low);
    if (top === null || bottom === null || width <= 0) return;

    const height = Math.max(bottom - top - STYLE.rowGap, 1);
    context.fillStyle = isPoc ? STYLE.poc : STYLE.bar;
    context.fillRect(paneWidth - width, top, width, height);
  }
}
