import { useState } from 'react';
import { RANGES } from '../timeframes.js';
const STRATEGIES=['sloped_lines','enhanced_channel'];
const STRATEGY_PRESETS={
  sloped_lines:{resolution:'1h',range:'1M',parameters:{line_angle:0,pivot_lookback:5,anchor_source:'confirmed_pivots'}},
  enhanced_channel:{resolution:'1d',range:'1Y',parameters:{}},
};
const SLOPED_FIELDS=[
  ['pivot_lookback','Pivot','select',[2,3,4,5,6,7,8,10]],
  ['anchor_source','Anchors','select',['confirmed_pivots','any_valid_candle']],
  ['validation_boundary','Validation','select',['body','close','wick']],
  ['trendline_tolerance','Tolerance','select',[0,0.005,0.01,0.015,0.02]],
  ['confirm_candles','Confirm','select',[0,1,2,3]],
  ['line_angle','Angle','select',[0,2,3,4,5,6,7,8]],
  ['stop_loss_mode','Stop','select',['none','exit_peak_reclaim','barrier_trap_reentry','atr_stop_buffer']],
  ['min_anchor_bars','Anchor bars','select',[0,1,2,3,4,5]],
];
function label(value){return String(value).replaceAll('_',' ');}
export default function StrategyDrawer({pane,symbol,onChange,onClose}){
  const [message,setMessage]=useState('');
  const patchStrategy=(patch)=>onChange({strategy:{...pane.strategy,...patch}});
  const patchParam=(key,value)=>patchStrategy({parameters:{...pane.strategy.parameters,[key]:value}});
  const applyStrategy=(name,enabled=true)=>{
    const preset=STRATEGY_PRESETS[name]||{};
    onChange({
      backtestWindow:null,
      resolution:preset.resolution||pane.resolution,
      range:preset.range||pane.range,
      strategy:{...pane.strategy,name,enabled,parameters:{...pane.strategy.parameters,...preset.parameters}},
    });
    if(enabled)setMessage(`Applied ${label(name)} with ${preset.resolution} candles and a ${preset.range} timeline.`);
  };
  const loadBest=async()=>{
    setMessage('Loading…');
    const response=await fetch(`/api/best-parameters?strategy=${encodeURIComponent(pane.strategy.name)}&symbol=${encodeURIComponent(symbol.id)}`);
    const result=await response.json();
    if(!result.found){setMessage(`No saved best parameters for ${symbol.label} and ${pane.strategy.name}.`);return;}
    const window=result.data.backtest_window||null;
    onChange({
      resolution:result.data.timeframe||pane.resolution,
      range:RANGES.find((item)=>item.period===result.data.period)?.id||pane.range,
      tradingWindow:window?.trading_window||pane.tradingWindow,
      backtestWindow:window,
      strategy:{...pane.strategy,parameters:{...pane.strategy.parameters,peak_reclaim_full_candle:false,compounding:true,initial_capital:10000,...result.data.parameters}},
    });
    setMessage(`Loaded saved best${result.data.performance?.total_pnl_pct!==undefined?` (${result.data.performance.total_pnl_pct}%)`:''}.`);
  };
  return <aside className="strategy-drawer" aria-label="Strategy controls">
    <header><strong>Strategy · {symbol.label}</strong><button type="button" onClick={onClose} aria-label="Close strategy drawer">×</button></header>
    <div className="strategy-row">
      {symbol.source==='yahoo'&&<label className="session-field"><span>Market session</span><select value={pane.tradingWindow||'regular market'} onChange={(e)=>onChange({tradingWindow:e.target.value})}>
        <option value="regular market">Regular</option><option value="pre-market">Pre-market + regular</option><option value="after hours">Regular + after hours</option><option value="extended hours">Extended</option><option value="overnight">All sessions</option>
      </select></label>}
      <label><input type="checkbox" checked={pane.strategy.enabled} onChange={(e)=>e.target.checked?applyStrategy(pane.strategy.name):patchStrategy({enabled:false})}/> Show strategy</label>
      <select value={pane.strategy.name} onChange={(e)=>pane.strategy.enabled?applyStrategy(e.target.value):patchStrategy({name:e.target.value})}>
        {STRATEGIES.map((item)=><option key={item} value={item}>{label(item)}</option>)}
      </select>
      <button type="button" onClick={loadBest}>★ Saved Best</button>
    </div>
    {pane.strategy.name==='sloped_lines'&&<div className="strategy-fields">
      <label title="Reinvest available equity. Off: use the starting-capital budget, capped by available cash."><span>Compounding</span><input type="checkbox" checked={pane.strategy.parameters.compounding!==false} onChange={(e)=>patchParam('compounding',e.target.checked)}/></label>
      <label><span>Starting Capital ($)</span><input type="number" required min="0.01" step="0.01" value={pane.strategy.parameters.initial_capital??10000} onChange={(e)=>{if(e.target.checkValidity())patchParam('initial_capital',Number(e.target.value));}}/></label>
      {SLOPED_FIELDS.map(([key,title,,options])=><label key={key}><span>{title}</span><select value={pane.strategy.parameters[key]} onChange={(e)=>{
        const sample=options[0]; patchParam(key,typeof sample==='number'?Number(e.target.value):e.target.value);
      }}>{options.map((value)=><option key={value} value={value}>{key==='trendline_tolerance'?`${Number(value)*100}%`:label(value)}</option>)}</select></label>)}
      <label title="Enable buys when descending resistance breaks"><span>Line Breakout Buy</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.line_breakout_buy)} onChange={(e)=>patchParam('line_breakout_buy',e.target.checked)}/></label>
      <label title="Enable entry-low protection before support forms, including ATR Stop Buffer"><span>Entry Barrier Sell</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.entry_barrier_sell)} onChange={(e)=>patchParam('entry_barrier_sell',e.target.checked)}/></label>
      <label title="Use closing prices for line breaks, trap re-entry and entry protection; excludes Peak Reclaim"><span>Full candle</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.full_candle)} onChange={(e)=>patchParam('full_candle',e.target.checked)}/></label>
      <label title="Peak Reclaim only: require a close strictly above the sell peak and buy at that close"><span>Peak Reclaim Full Candle</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.peak_reclaim_full_candle)} onChange={(e)=>patchParam('peak_reclaim_full_candle',e.target.checked)}/></label>
      <label><span>Wick anchors</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.use_wick)} onChange={(e)=>patchParam('use_wick',e.target.checked)}/></label>
      <label><span>Gap Up</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.gap_up)} onChange={(e)=>patchParam('gap_up',e.target.checked)}/></label>
      <label><span>Gap Down</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.gap_down)} onChange={(e)=>patchParam('gap_down',e.target.checked)}/></label>
      <label title="Build tighter resistance from the latest touch and local maximum; build tighter support from later higher-low pivots"><span>Staggered Lines</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.staggered_lines)} onChange={(e)=>patchParam('staggered_lines',e.target.checked)}/></label>
      <label title="Show a price-axis label only for the currently active support or resistance"><span>Active Line Labels</span><input type="checkbox" checked={Boolean(pane.strategy.parameters.trendline_labels)} onChange={(e)=>patchParam('trendline_labels',e.target.checked)}/></label>
    </div>}
    {pane.strategy.name==='enhanced_channel'&&<div className="strategy-fields">
      <label><span>Channel width</span><input type="number" min="1" max="3" step="0.1" value={pane.strategy.parameters.channel_mult??1.7} onChange={(e)=>patchParam('channel_mult',Number(e.target.value))}/></label>
      <label><span>Lookback</span><input type="number" min="10" max="200" value={pane.strategy.parameters.lookback??50} onChange={(e)=>patchParam('lookback',Number(e.target.value))}/></label>
    </div>}
    {pane.backtestWindow&&<div className="drawer-message"><span>Saved window: {pane.backtestWindow.start_date} → {pane.backtestWindow.end_date}</span> <button type="button" onClick={()=>onChange({backtestWindow:null})}>Use rolling range</button></div>}
    {message&&<p className={message.startsWith('No ')?'drawer-message error':'drawer-message'}>{message}</p>}
  </aside>;
}
