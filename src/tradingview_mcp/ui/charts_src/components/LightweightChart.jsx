import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { CandlestickSeries, LineSeries, createChart, createSeriesMarkers } from 'lightweight-charts';
import { CANDLESTICK_OPTIONS, CHART_OPTIONS } from '../chartConfig.js';
import { createDrawing, DRAWING_TOOLS, drawingSegments } from '../drawings.js';
import { useCandleFeed } from '../hooks/useCandleFeed.js';
import { useSeriesPrimitive } from '../hooks/useSeriesPrimitive.js';
import { FairValueGapPrimitive } from '../primitives/FairValueGapPrimitive.js';
import { VolumeProfilePrimitive } from '../primitives/VolumeProfilePrimitive.js';

const unix=(value)=>{const time=Date.parse(value||'');return Number.isFinite(time)?Math.floor(time/1000):null;};
const nearest=(time,candles)=>candles.reduce((best,item)=>Math.abs(item.time-time)<Math.abs(best-time)?item.time:best,candles[0]?.time??time);
function markerData(trades,candles){
  const details=new Map(); const markers=[];
  trades.forEach((trade)=>{
    const entry=unix(trade.created_at); if(entry&&candles.length){const time=nearest(entry,candles);markers.push({time,position:'belowBar',color:'#22c55e',shape:'arrowUp',text:''});details.set(time,{kind:'BUY',price:trade.entry_price,reason:trade.entry_reason,quantity:trade.quantity,balance:trade.balance_before});}
    const exit=unix(trade.closed_at); if(exit&&candles.length){const time=nearest(exit,candles);markers.push({time,position:'aboveBar',color:'#ef4444',shape:'arrowDown',text:''});details.set(time,{kind:'SELL',price:trade.exit_price,reason:trade.exit_reason,pnl:trade.pnl_pct,quantity:trade.quantity,balance:trade.balance_after,pnlUsd:trade.pnl_usd});}
  });
  return {markers:markers.sort((a,b)=>a.time-b.time),details};
}
function linePoints(line,candles){
  if(Array.isArray(line.points)&&line.points.length>1)return line.points.map((point)=>{
    const parsed=Number(point.time)||unix(point.time)||unix(point.date);
    return {time:parsed&&candles.length?nearest(parsed,candles):parsed,value:Number(point.value??point.price)};
  }).filter((p)=>p.time&&Number.isFinite(p.value)).sort((a,b)=>a.time-b.time).filter((point,index,items)=>index===0||point.time!==items[index-1].time);
  const start=Number(line.start_time)||unix(line.start_date); const end=Number(line.end_time)||unix(line.end_date);
  return start&&end?[{time:nearest(start,candles),value:Number(line.start_price)},{time:nearest(end,candles),value:Number(line.end_price)}]:[];
}
export default function LightweightChart({symbol,pane,strategyData,drawingTool,onDrawingProgress,onDrawingComplete,onStatusChange}){
  const containerRef=useRef(null); const chartRef=useRef(null); const seriesRef=useRef(null); const markerRef=useRef(null); const overlayRef=useRef([]); const drawingSeriesRef=useRef([]);
  const drawingToolRef=useRef(drawingTool); const drawingStateRef=useRef({tool:drawingTool,points:[]}); const drawingCompleteRef=useRef(onDrawingComplete); const drawingProgressRef=useRef(onDrawingProgress);
  const candlesRef=useRef([]); const [candles,setCandles]=useState([]); const [selected,setSelected]=useState(null);
  useLayoutEffect(()=>{drawingToolRef.current=drawingTool;drawingCompleteRef.current=onDrawingComplete;drawingProgressRef.current=onDrawingProgress;if(drawingStateRef.current.tool!==drawingTool)drawingStateRef.current={tool:drawingTool,points:[]};},[drawingTool,onDrawingComplete,onDrawingProgress]);
  const onCandles=useCallback((value)=>{candlesRef.current=[...value];setCandles([...value]);},[]);
  useEffect(()=>{
    const chart=createChart(containerRef.current,CHART_OPTIONS); const series=chart.addSeries(CandlestickSeries,CANDLESTICK_OPTIONS);
    chartRef.current=chart;seriesRef.current=series;markerRef.current=createSeriesMarkers(series,[]);
    const click=(param)=>{
      if(!param.point)return;
      const tool=drawingToolRef.current;
      if(tool!=='cursor'){
        const price=series.coordinateToPrice(param.point.y);if(price===null)return;
        const loaded=candlesRef.current;const width=Math.max(chart.timeScale().width(),1);const fallbackIndex=Math.max(0,Math.min(loaded.length-1,Math.round((param.point.x/width)*(loaded.length-1))));
        const time=param.time??loaded[fallbackIndex]?.time;if(time===undefined)return;
        const state=drawingStateRef.current.tool===tool?drawingStateRef.current:{tool,points:[]};
        const points=[...state.points,{time,price:Number(price)}]; const required=DRAWING_TOOLS[tool]?.points||0;
        drawingStateRef.current={tool,points};drawingProgressRef.current?.(points.length);
        if(required&&points.length===required){
          const id=globalThis.crypto?.randomUUID?.()||`${tool}-${Date.now()}`;const drawing=createDrawing(tool,points,id);
          drawingStateRef.current={tool,points:[]};drawingProgressRef.current?.(0);if(drawing)drawingCompleteRef.current?.(drawing);
        }
        return;
      }
      if(!param.time)return;
      setSelected((current)=>current?.time===param.time?null:{time:param.time});
    }; chart.subscribeClick(click);
    return()=>{chart.unsubscribeClick(click);chart.remove();chartRef.current=null;seriesRef.current=null;markerRef.current=null;};
  },[]);
  useCandleFeed({chartRef,seriesRef},{symbol,resolutionId:pane.resolution,rangeId:pane.range,tradingWindow:pane.tradingWindow||'regular market',backtestWindow:pane.backtestWindow},onStatusChange,onCandles);
  useSeriesPrimitive(seriesRef,pane.indicators.fvg,FairValueGapPrimitive);
  useSeriesPrimitive(seriesRef,pane.indicators.volumeProfile,VolumeProfilePrimitive);
  const markerBundle=useMemo(()=>markerData(strategyData.trades||[],candles),[strategyData.trades,candles]);
  useEffect(()=>{markerRef.current?.setMarkers(markerBundle.markers);},[markerBundle.markers]);
  useEffect(()=>{
    const chart=chartRef.current;if(!chart)return;overlayRef.current.forEach((series)=>{try{chart.removeSeries(series);}catch{}});overlayRef.current=[];
    const overlays=[...(strategyData.trendlines||[]),...(strategyData.channels||[])];
    overlays.forEach((overlay)=>{
      const points=linePoints(overlay,candles); if(points.length<2)return;
      const showLabel=Boolean(pane.strategy.parameters.trendline_labels&&overlay.status==='active');
      const series=chart.addSeries(LineSeries,{color:overlay.color||(overlay.type==='support'?'#3b82f6':'#10b981'),lineWidth:2,lineStyle:overlay.status==='forming'?2:0,priceLineVisible:false,lastValueVisible:showLabel,title:showLabel?(overlay.label||overlay.type||''):''});
      series.setData(points);overlayRef.current.push(series);
    });
  },[strategyData.trendlines,strategyData.channels,candles,pane.strategy.parameters.trendline_labels]);
  useEffect(()=>{
    const chart=chartRef.current;if(!chart)return;drawingSeriesRef.current.forEach((series)=>{try{chart.removeSeries(series);}catch{}});drawingSeriesRef.current=[];
    (pane.drawings||[]).flatMap(drawingSegments).forEach((segment)=>{
      const color=segment.role==='line'?'#f59e0b':segment.role==='midline'?'rgba(34, 211, 238, 0.65)':'#22d3ee';
      const series=chart.addSeries(LineSeries,{color,lineWidth:2,lineStyle:segment.role==='midline'?2:0,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
      const data=segment.points.map((point)=>({time:point.time,value:point.price})).sort((a,b)=>a.time-b.time);
      series.setData(data);drawingSeriesRef.current.push(series);
    });
  },[pane.drawings]);
  const detail=selected?markerBundle.details.get(selected.time):null;
  return <><div ref={containerRef} className="lightweight-chart" data-source={symbol.source} data-symbol={symbol.id} data-candle-count={candles.length} data-marker-count={markerBundle.markers.length} data-overlay-count={(strategyData.trendlines?.length||0)+(strategyData.channels?.length||0)} data-drawing-count={pane.drawings?.length||0}/>{detail&&<button type="button" className="signal-detail" onClick={()=>setSelected(null)}><b>{detail.kind}</b> {detail.price?`$${Number(detail.price).toFixed(2)}`:''} {detail.reason||''} {detail.quantity!=null?`· ${Number(detail.quantity).toFixed(6)} shares`:''} {detail.balance!=null?`· balance $${Number(detail.balance).toFixed(2)}`:''} {detail.pnlUsd!=null?`· P&L $${Number(detail.pnlUsd).toFixed(2)}`:''} {detail.pnl!==undefined?`· ${Number(detail.pnl).toFixed(1)}%`:''}</button>}</>;
}
