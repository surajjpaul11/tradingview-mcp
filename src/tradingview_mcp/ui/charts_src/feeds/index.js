import { subscribeHyperliquid } from './hyperliquid.js';
import { subscribeYahoo } from './yahoo.js';
const FEEDS={hyperliquid:subscribeHyperliquid,yahoo:subscribeYahoo};
export function subscribeCandles(symbol,timeframe,handlers){
  const feed=FEEDS[symbol.source];
  if(!feed) throw new Error(`Unsupported source: ${symbol.source}`);
  return feed(symbol,timeframe,handlers);
}
