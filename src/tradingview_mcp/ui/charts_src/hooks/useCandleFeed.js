import { useEffect } from 'react';
import { subscribeCandles } from '../feeds/index.js';
import { toSeriesBar } from '../seriesBars.js';
import { DAY, findRange, findResolution } from '../timeframes.js';

export function useCandleFeed({chartRef,seriesRef},{symbol,resolutionId,rangeId,tradingWindow,backtestWindow},onStatusChange,onCandlesChange){
  useEffect(()=>{
    const chart=chartRef.current; const series=seriesRef.current;
    const resolution=findResolution(resolutionId); const range=findRange(rangeId);
    let candles=[]; let lastTime=null;
    series.setData([]); chart.applyOptions({timeScale:{timeVisible:resolution.seconds<DAY}}); onStatusChange({state:'loading'});
    const publish=()=>onCandlesChange?.(candles);
    const onHistory=(history)=>{
      const byTime=new Map(history.map((candle)=>[candle.time,candle])); candles=[...byTime.values()].sort((a,b)=>a.time-b.time);
      series.setData(candles.map(toSeriesBar)); chart.timeScale().fitContent(); lastTime=candles.at(-1)?.time??0; publish(); onStatusChange({state:'live'});
    };
    const onCandle=(candle)=>{
      if(lastTime===null||candle.time<lastTime)return;
      series.update(toSeriesBar(candle));
      if(candle.time===lastTime)candles[candles.length-1]=candle;else candles.push(candle);
      lastTime=candle.time; publish();
    };
    const onError=(error)=>{console.error(error);onStatusChange({state:'error',message:error.message});};
    return subscribeCandles(symbol,{resolution,range:{...range,tradingWindow,backtestWindow}},{onHistory,onCandle,onError});
  },[chartRef,seriesRef,symbol,resolutionId,rangeId,tradingWindow,backtestWindow,onStatusChange,onCandlesChange]);
}
