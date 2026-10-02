import { fetchChartHistory } from './history.js';
const POLL_MS=30000;
export function subscribeYahoo(symbol,{resolution,range},{onHistory,onCandle,onError}){
  let active=true; const controller=new AbortController(); let latest=0;
  const load=async(initial=false)=>{
    try{
      const candles=await fetchChartHistory(symbol,resolution.id,initial?range.id:'1D',controller.signal,range.tradingWindow);
      if(!active) return;
      if(initial){ onHistory(candles); latest=candles.at(-1)?.time ?? 0; }
      else candles.slice(-2).forEach((candle)=>{ if(candle.time>=latest){onCandle(candle); latest=candle.time;} });
    }catch(error){ if(active && error.name!=='AbortError') onError(error); }
  };
  load(true); const timer=setInterval(()=>load(false),POLL_MS);
  return ()=>{active=false; clearInterval(timer); controller.abort();};
}
