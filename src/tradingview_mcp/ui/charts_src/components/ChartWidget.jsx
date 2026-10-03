import { useState } from 'react';
import IndicatorToggles from './IndicatorToggles.jsx';
import LightweightChart from './LightweightChart.jsx';
import SegmentedControl from './SegmentedControl.jsx';
import StatusBadge from './StatusBadge.jsx';
import SymbolSelector from './SymbolSelector.jsx';
import { findSymbol } from '../symbols.js';
import { rangeOptions,resolutionOptions,resolveResolution } from '../timeframes.js';
import { useStrategyData } from '../hooks/useStrategyData.js';

export default function ChartWidget({pane,active,onActivate,onPaneChange,onOpenStrategy}){
  const [status,setStatus]=useState({state:'loading'}); const symbol=findSymbol(pane.symbolId);
  const strategy=useStrategyData(symbol,pane);
  const symbolChange=(symbolId)=>onPaneChange((current)=>{const next=findSymbol(symbolId);return {symbolId,source:next.source,resolution:resolveResolution(next.source,current.resolution,current.range)};});
  const toggle=(key)=>onPaneChange((current)=>({indicators:{...current.indicators,[key]:!current.indicators[key]}}));
  return <section className={`chart-widget ${active?'active':''}`} onPointerDown={onActivate}>
    <header className="chart-widget__header">
      <SymbolSelector value={pane.symbolId} onChange={symbolChange}/>
      <SegmentedControl className="chart-widget__resolutions" label="Candle resolution" options={resolutionOptions(symbol.source,pane.range)} value={pane.resolution} onChange={(resolution)=>onPaneChange({resolution})}/>
      <IndicatorToggles value={pane.indicators} onToggle={toggle}/>
      <button type="button" className={`strategy-toggle ${pane.strategy.enabled?'enabled':''}`} onClick={(e)=>{e.stopPropagation();onOpenStrategy();}}>Strategy</button>
      <StatusBadge status={strategy.error?{state:'error',message:strategy.error}:status}/>
    </header>
    <div className="chart-widget__body"><LightweightChart symbol={symbol} pane={pane} strategyData={strategy} onStatusChange={setStatus}/></div>
    <footer className="chart-widget__footer">
      <SegmentedControl label="Timeline" options={rangeOptions(symbol.source,pane.resolution)} value={pane.range} onChange={(range)=>onPaneChange({range})}/>
      {pane.strategy.enabled&&strategy.stats&&<div className="pane-stats"><span>P&L <b className={(strategy.stats.total_pnl_pct??0)>=0?'positive':'negative'}>{strategy.stats.total_pnl_pct??0}%</b></span><span>B&H {strategy.stats.buy_and_hold_pct??0}%</span><span>Win {strategy.stats.win_rate_pct??0}%</span><span>{strategy.stats.total_trades??0} trades</span></div>}
      {pane.strategy.enabled&&!strategy.loading&&!strategy.error&&pane.strategy.name==='sloped_lines'&&strategy.trendlines.length===0&&<span className="strategy-empty">No Sloped Lines for these settings</span>}
    </footer>
  </section>;
}
