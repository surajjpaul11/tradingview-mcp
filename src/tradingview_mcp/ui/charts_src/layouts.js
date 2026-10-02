import { DEFAULT_PANE_SYMBOLS, findSymbol } from './symbols.js';

export const PANE_OPTIONS = [1, 2, 4, 6, 8];
export const DEFAULT_PANE_COUNT = 1;
export const DEFAULT_STRATEGY = {
  enabled: false,
  name: 'sloped_lines',
  parameters: {
    full_candle: false, use_wick: false, confirm_candles: 0, pivot_lookback: 5,
    anchor_source: 'confirmed_pivots', validation_boundary: 'body', trendline_tolerance: 0,
    inverse_color_trigger: false, line_angle: 3, stop_loss_mode: 'exit_peak_reclaim', min_anchor_bars: 2,
  },
};
export const DEFAULT_PANES = DEFAULT_PANE_SYMBOLS.map((symbolId) => ({
  symbolId,
  source: findSymbol(symbolId).source,
  resolution: '1m',
  range: '1D',
  tradingWindow: 'regular market',
  indicators: { fvg: false, volumeProfile: false },
  strategy: structuredClone(DEFAULT_STRATEGY),
}));
