// lightweight-charts drops unknown bar fields; only `customValues` survives
// into series.data(), so volume rides there between the feed and the primitives.

export const toSeriesBar = ({ volume, ...bar }) => ({ ...bar, customValues: { volume } });

export const fromSeriesBar = ({ customValues, ...bar }) => ({
  ...bar,
  volume: customValues?.volume ?? 0,
});
