import { ColorType } from 'lightweight-charts';

const MARKET_TIME_ZONE = 'America/New_York';

export function formatCrosshairTime(time) {
  const businessDay = time && typeof time === 'object';
  const date = businessDay
    ? new Date(Date.UTC(time.year, time.month - 1, time.day, 12))
    : new Date(Number(time) * 1000);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-US', {
    timeZone: MARKET_TIME_ZONE, month: 'short', day: 'numeric', year: 'numeric',
    ...(businessDay ? {} : { hour: 'numeric', minute: '2-digit', hour12: true, timeZoneName: 'short' }),
  }).format(date);
}

// Canvas colors can't read CSS variables, so these mirror the tokens in index.css.
const COLORS = {
  background: '#1e222d',
  text: '#787b86',
  grid: '#2a2e39',
  up: '#26a69a',
  down: '#ef5350',
};

export const CHART_OPTIONS = {
  autoSize: true,
  localization: { locale: 'en-US', timeFormatter: formatCrosshairTime },
  layout: {
    background: { type: ColorType.Solid, color: COLORS.background },
    textColor: COLORS.text,
    attributionLogo: false,
  },
  grid: {
    vertLines: { color: COLORS.grid },
    horzLines: { color: COLORS.grid },
  },
  rightPriceScale: { borderColor: COLORS.grid },
  timeScale: { borderColor: COLORS.grid, timeVisible: true },
};

export const INDICATOR_STYLE = {
  fvg: {
    bullish: { open: 'rgba(38, 166, 154, 0.22)', filled: 'rgba(38, 166, 154, 0.08)' },
    bearish: { open: 'rgba(239, 83, 80, 0.22)', filled: 'rgba(239, 83, 80, 0.08)' },
  },
  volumeProfile: {
    rows: 30,
    maxWidthRatio: 0.25,
    rowGap: 1,
    bar: 'rgba(41, 98, 255, 0.28)',
    poc: 'rgba(255, 183, 77, 0.55)',
  },
};

export const CANDLESTICK_OPTIONS = {
  upColor: COLORS.up,
  downColor: COLORS.down,
  borderVisible: false,
  wickUpColor: COLORS.up,
  wickDownColor: COLORS.down,
};
