import { DEFAULT_PANE_SYMBOLS, findSymbol } from './symbols.js';

export const PANE_OPTIONS = [1, 2, 4, 6, 8];
export const DEFAULT_PANE_COUNT = 1;
export const DEFAULT_STRATEGY = {
  enabled: false,
  name: 'sloped_lines',
  parameters: {
    adaptive_tightening: false, adaptive_pivot_bars: 2, adaptive_min_improvement_atr: .25,
    peak_reclaim_full_candle: false, compounding: true, initial_capital: 10000, line_breakout_buy: false, entry_barrier_sell: false, full_candle: false, use_wick: false, gap_up: false, gap_down: false, staggered_lines: false, trendline_labels: false, confirm_candles: 0, pivot_lookback: 5,
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
  drawings: [],
  strategy: structuredClone(DEFAULT_STRATEGY),
}));
