import { useEffect, useMemo, useState } from 'react';
import { findRange } from '../timeframes.js';

const EMPTY={stats:null,trades:[],trendlines:[],channels:[],loading:false,error:'',query:''};
const PARAM_KEYS={
  full_candle:'full_candle',use_wick:'use_wick',confirm_candles:'confirm_candles',pivot_lookback:'pivot_lookback',
  anchor_source:'anchor_source',validation_boundary:'validation_boundary',trendline_tolerance:'trendline_tolerance',
  inverse_color_trigger:'inverse_color_trigger',line_angle:'line_angle',stop_loss_mode:'stop_loss_mode',min_anchor_bars:'min_anchor_bars',
  channel_mult:'channel_mult',lookback:'lookback',
};
export function strategyQuery(symbol,pane){
  const query=new URLSearchParams({
    source:symbol.source,symbol:symbol.id,strategy:pane.strategy.name,timeframe:pane.resolution,
    period:findRange(pane.range).period,trading_window:pane.tradingWindow||'regular market',
  });
  Object.entries(pane.strategy.parameters||{}).forEach(([key,value])=>{
    if(PARAM_KEYS[key] && value!==undefined && value!==null) query.set(PARAM_KEYS[key],String(value));
  });
  return query;
}
export function useStrategyData(symbol,pane){
  const [state,setState]=useState(EMPTY);
  const query=useMemo(()=>strategyQuery(symbol,pane).toString(),[symbol,pane]);
  useEffect(()=>{
    if(!pane.strategy.enabled)return undefined;
    const controller=new AbortController();
    const fetchJson=async(path)=>{
      const response=await fetch(`${path}?${query}`,{signal:controller.signal});
      if(!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
      return response.json();
    };
    const overlayPath=pane.strategy.name==='enhanced_channel'?'/api/channels':'/api/trendlines';
    Promise.all([fetchJson('/api/stats'),fetchJson('/api/trades'),fetchJson(overlayPath)])
      .then(([stats,trades,overlay])=>setState({stats,trades:trades.trades||[],trendlines:overlay.trendlines||[],channels:overlay.overlays||[],loading:false,error:'',query}))
      .catch((error)=>{if(error.name!=='AbortError')setState({...EMPTY,error:error.message,query});});
    return ()=>controller.abort();
  },[pane.strategy.enabled,pane.strategy.name,query]);
  return pane.strategy.enabled ? (state.query===query?state:{...EMPTY,loading:true}) : EMPTY;
}
