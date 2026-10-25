import { fetchChartHistory } from './history.js';
import { createLiveAggregator } from '../candles.js';
import { parseHyperliquidCandle } from './parsers.js';
import { subscribeHyperliquidCandles } from './hyperliquidSocket.js';

export function subscribeHyperliquid(symbol,{resolution,range},{onHistory,onCandle,onError}){
  let active=true; const controller=new AbortController(); let historyReady=false; const pending=[];
  const interval=resolution.id==='5d'?'1d':resolution.id;
  const aggregate=resolution.id==='5d'?createLiveAggregator(resolution.seconds):(candle)=>candle;
  fetchChartHistory(symbol,resolution.id,range.id,controller.signal,range.tradingWindow,range.backtestWindow).then((candles)=>{
    if(!active) return; onHistory(candles); historyReady=true;
    pending.sort((a,b)=>a.time-b.time).forEach(onCandle); pending.length=0;
  }).catch((error)=>{ if(active && error.name!=='AbortError') onError(error); });
  const unsubscribe=range.backtestWindow?()=>{}:subscribeHyperliquidCandles(symbol.id,interval,(raw)=>{
    if(!active) return; const candle=aggregate(parseHyperliquidCandle(raw));
    if(!candle)return;
    if(historyReady) onCandle(candle); else pending.push(candle);
  });
  return ()=>{active=false; controller.abort(); unsubscribe();};
}
