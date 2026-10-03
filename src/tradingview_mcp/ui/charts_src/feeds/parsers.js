// Pure converters from raw feed payloads into lightweight-charts candles:
// { time (UTC seconds), open, high, low, close, volume }

export function parseHyperliquidCandle(raw) {
  return {
    time: Math.floor(raw.t / 1000),
    open: Number(raw.o),
    high: Number(raw.h),
    low: Number(raw.l),
    close: Number(raw.c),
    volume: Number(raw.v),
  };
}

const isCompleteBar = (bar) =>
  [bar.open, bar.high, bar.low, bar.close].every((value) => value != null);

// Shifts timestamps by the exchange's GMT offset so the time axis
// shows exchange-local times (e.g. 09:15 IST for NSE open).
export function parseYahooChart(payload) {
  const result = payload?.chart?.result?.[0];
  if (!result) {
    throw new Error(payload?.chart?.error?.description ?? 'No chart data');
  }

  const { timestamp = [], indicators, meta } = result;
  const quote = indicators?.quote?.[0] ?? {};
  const offset = meta?.gmtoffset ?? 0;

  return timestamp
    .map((time, index) => ({
      time: time + offset,
      open: quote.open?.[index],
      high: quote.high?.[index],
      low: quote.low?.[index],
      close: quote.close?.[index],
      volume: quote.volume?.[index] ?? 0,
    }))
    .filter(isCompleteBar);
}
