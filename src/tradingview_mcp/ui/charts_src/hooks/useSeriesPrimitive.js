import { useEffect } from 'react';

// Attaches a new PrimitiveClass instance to the series while `enabled` is true.
export function useSeriesPrimitive(seriesRef, enabled, PrimitiveClass) {
  useEffect(() => {
    if (!enabled) return undefined;

    const series = seriesRef.current;
    const primitive = new PrimitiveClass();
    series.attachPrimitive(primitive);

    return () => {
      // The chart effect clears seriesRef when it removes the chart; the
      // primitive is gone with it, and detaching from a removed series throws.
      // Reading the latest ref value here is the point, not a stale-ref bug.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      if (seriesRef.current === series) series.detachPrimitive(primitive);
    };
  }, [seriesRef, enabled, PrimitiveClass]);
}
