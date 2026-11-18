import { fetchChartHistory } from './history.js';
const POLL_MS=30000;
export function subscribeYahoo(symbol,{resolution,range},{onHistory,onCandle,onError}){
  let active=true; const controller=new AbortController(); let latest=0; let revision=null;
  const load=async(initial=false)=>{
    try{
      let candles=await fetchChartHistory(symbol,resolution.id,initial?range.id:'1D',controller.signal,range.tradingWindow,range.backtestWindow);
      if(!active) return;
      if(!initial&&candles.dataStatus?.data_revision!==revision){
        candles=await fetchChartHistory(symbol,resolution.id,range.id,controller.signal,range.tradingWindow,range.backtestWindow);
        if(!active)return;
        initial=true;
      }
      revision=candles.dataStatus?.data_revision;
      if(initial){ onHistory(candles); latest=candles.at(-1)?.time ?? 0; }
      else candles.slice(-2).forEach((candle)=>{ if(candle.time>=latest){onCandle(candle); latest=candle.time;} });
    }catch(error){ if(active && error.name!=='AbortError') onError(error); }
  };
  load(true); const timer=range.backtestWindow?null:setInterval(()=>load(false),POLL_MS);
  return ()=>{active=false; clearInterval(timer); controller.abort();};
}
