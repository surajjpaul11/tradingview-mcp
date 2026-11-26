import test from 'node:test';
import assert from 'node:assert/strict';
import { aggregateCandles, createLiveAggregator } from '../src/tradingview_mcp/ui/charts_src/candles.js';
import { findFairValueGaps, buildVolumeProfile } from '../src/tradingview_mcp/ui/charts_src/indicators.js';
import { parseHyperliquidCandle, parseYahooChart } from '../src/tradingview_mcp/ui/charts_src/feeds/parsers.js';
import { formatCrosshairTime } from '../src/tradingview_mcp/ui/charts_src/chartConfig.js';
import { buildSymbolGroups, filterSymbolGroups, findSymbol } from '../src/tradingview_mcp/ui/charts_src/symbols.js';
import { createDrawing, drawingSegments, drawingPoint } from '../src/tradingview_mcp/ui/charts_src/drawings.js';
import { DrawingPrimitive } from '../src/tradingview_mcp/ui/charts_src/primitives/DrawingPrimitive.js';
import { DEFAULT_STRATEGY } from '../src/tradingview_mcp/ui/charts_src/layouts.js';
import { strategyQuery } from '../src/tradingview_mcp/ui/charts_src/hooks/useStrategyData.js';

test('signal switches default off and reach strategy requests independently',()=>{
  const pane={strategy:structuredClone(DEFAULT_STRATEGY),resolution:'1d',range:'1Y'};
  const symbol={source:'yahoo',id:'AAPL'};
  let query=strategyQuery(symbol,pane);
  assert.equal(query.get('peak_reclaim_full_candle'),'false');
  pane.strategy.parameters.peak_reclaim_full_candle=true;
  query=strategyQuery(symbol,pane);
  assert.equal(query.get('peak_reclaim_full_candle'),'true');
  assert.equal(query.get('full_candle'),'false');
  assert.equal(query.get('compounding'),'true');
  assert.equal(query.get('initial_capital'),'10000');
  pane.strategy.parameters.compounding=false;
  pane.strategy.parameters.initial_capital=500;
  query=strategyQuery(symbol,pane);
  assert.equal(query.get('compounding'),'false');
  assert.equal(query.get('initial_capital'),'500');
  assert.equal(query.get('line_breakout_buy'),'false');
  assert.equal(query.get('entry_barrier_sell'),'false');
  pane.strategy.parameters.line_breakout_buy=true;
  query=strategyQuery(symbol,pane);
  assert.equal(query.get('line_breakout_buy'),'true');
  assert.equal(query.get('entry_barrier_sell'),'false');
  pane.strategy.parameters.reentry_mode='any';
  pane.strategy.parameters.reentry_price_breakout=true;
  query=strategyQuery(symbol,pane);
  assert.equal(query.get('reentry_mode'),'any');
  assert.equal(query.get('reentry_price_breakout'),'true');
  pane.backtestWindow={start_date:'2025-09-26',end_date:'2026-09-25'};
  query=strategyQuery(symbol,pane);
  assert.equal(query.get('start_date'),'2025-09-26');
  assert.equal(query.get('end_date'),'2026-09-25');
});

test('builds straight lines and parallel channel boundaries',()=>{
  const straight=createDrawing('trendline',[{time:1,price:10},{time:3,price:14}],'line-1');
  assert.equal(drawingSegments(straight).length,1);
  const channel=createDrawing('parallel_channel',[{time:1,price:10},{time:3,price:14},{time:2,price:16}],'channel-1');
  const segments=drawingSegments(channel);
  assert.equal(segments.length,3);
  assert.deepEqual(segments[1].points.map((point)=>point.price),[14,18]);
  assert.equal(segments[2].role,'midline');
});

test('drawing anchors follow logical positions when zoomed and in empty chart space',()=>{
  const candles=Array.from({length:100},(_,i)=>({time:60+i*60}));
  assert.deepEqual(drawingPoint(80.2,14,candles,60),{time:4860,price:14});
  assert.deepEqual(drawingPoint(104,14,candles,60),{time:6300,price:14});
  assert.deepEqual(drawingPoint(-2,14,candles,60),{time:-60,price:14});
  assert.equal(drawingPoint(null,14,candles,60),null);
  assert.equal(drawingPoint(2,null,candles,60),null);
  assert.equal(drawingPoint(2,14,[],60),null);
  assert.ok(createDrawing('trendline',[{time:60,price:10},{time:60,price:14}]));
  assert.equal(createDrawing('parallel_channel',[{time:60,price:10},{time:60,price:14},{time:120,price:15}]),null);
});

test('drawing primitive paints channel previews, anchors, and saved drawings without adding series',()=>{
  const primitive=new DrawingPrimitive(); const strokes=[];const anchors=[];let path=[];let updates=0;
  const scale={timeToCoordinate:(time)=>time>=60&&time<=180?time:null,logicalToCoordinate:(index)=>60+index*60,timeToIndex:()=>1};
  primitive.attached({chart:{timeScale:()=>scale},series:{priceToCoordinate:(price)=>200-price*10},requestUpdate:()=>updates++});
  const context={save(){},restore(){},setLineDash(){},beginPath(){path=[];},moveTo(x,y){path.push([x,y]);},lineTo(x,y){path.push([x,y]);},stroke(){if(path.length)strokes.push(path);},arc(x,y){anchors.push([x,y]);},fill(){}};
  const target={useMediaCoordinateSpace:(draw)=>draw({context})};
  const channel=createDrawing('parallel_channel',[{time:60,price:10},{time:180,price:14},{time:120,price:16}]);
  primitive.update({draft:channel,candles:[{time:60},{time:120},{time:180}]});primitive.draw(target);
  assert.equal(strokes.length,3);assert.equal(anchors.length,3);
  assert.deepEqual(strokes[1],[[60,60],[180,20]]);
  assert.deepEqual(primitive.coordinate({time:300,price:10}),{x:300,y:100});
  primitive.update({draft:null,drawings:[channel]});
  assert.equal(updates,2);assert.equal(primitive.draft,null);
  primitive.detached();assert.equal(primitive.chart,null);
});

test('merges and filters strategy dashboard symbols by data source',()=>{
  const groups=buildSymbolGroups(['AAPL','WULF','BTC-USD','WULF']);
  assert.equal(findSymbol('BTC',groups).source,'hyperliquid');
  assert.equal(findSymbol('BTC-USD',groups).source,'yahoo');
  assert.equal(groups.find((group)=>group.label.includes('Strategy Dashboard')).symbols.filter((symbol)=>symbol.id==='WULF').length,1);
  const filtered=filterSymbolGroups(groups,'wul');
  assert.deepEqual(filtered.flatMap((group)=>group.symbols.map((symbol)=>symbol.id)),['WULF']);
});

test('crosshair time includes the year',()=>{
  assert.match(formatCrosshairTime(Date.UTC(2026,6,31,16)/1000),/2026/);
  assert.match(formatCrosshairTime({year:2022,month:9,day:12}),/2022/);
});

test('normalizes Hyperliquid and Yahoo candles',()=>{
  assert.deepEqual(parseHyperliquidCandle({t:2000,o:'1',h:'3',l:'0.5',c:'2',v:'9'}),{time:2,open:1,high:3,low:.5,close:2,volume:9});
  const data=parseYahooChart({chart:{result:[{timestamp:[100],meta:{gmtoffset:0},indicators:{quote:[{open:[1],high:[2],low:[.5],close:[1.5],volume:[7]}]}}]}});
  assert.deepEqual(data,[{time:100,open:1,high:2,low:.5,close:1.5,volume:7}]);
});

test('aggregates history and rejects stale live buckets',()=>{
  const bars=[{time:0,open:1,high:2,low:1,close:2,volume:3},{time:60,open:2,high:4,low:1.5,close:3,volume:5}];
  assert.deepEqual(aggregateCandles(bars,120),[{time:0,open:1,high:4,low:1,close:3,volume:8}]);
  const update=createLiveAggregator(120); update(bars[1]);
  assert.equal(update({time:-60,open:0,high:1,low:0,close:1,volume:1}),null);
});

test('detects FVG and builds visible volume profile',()=>{
  const candles=[
    {time:1,open:1,high:2,low:1,close:2,volume:10},
    {time:2,open:2,high:3,low:2,close:3,volume:20},
    {time:3,open:4,high:5,low:4,close:5,volume:30},
  ];
  const gaps=findFairValueGaps(candles); assert.equal(gaps.length,1); assert.equal(gaps[0].type,'bullish');
  const profile=buildVolumeProfile(candles,4); assert.equal(profile.bins.length,4); assert.ok(profile.maxVolume>0);
});

class FakeWebSocket {
  static OPEN=1; static instances=[];
  constructor(){this.readyState=0;this.sent=[];FakeWebSocket.instances.push(this);queueMicrotask(()=>{this.readyState=1;this.onopen?.();});}
  send(value){this.sent.push(JSON.parse(value));}
  close(){this.closed=true;this.readyState=3;}
  emit(data){this.onmessage?.({data:JSON.stringify(data)});}
}

test('shares Hyperliquid socket and cleans subscriptions',async()=>{
  globalThis.WebSocket=FakeWebSocket;
  const { subscribeHyperliquidCandles }=await import(`../src/tradingview_mcp/ui/charts_src/feeds/hyperliquidSocket.js?test=${Date.now()}`);
  let first=0,second=0; const off1=subscribeHyperliquidCandles('BTC','1m',()=>first++); const off2=subscribeHyperliquidCandles('BTC','1m',()=>second++);
  await new Promise((resolve)=>setTimeout(resolve,0));
  assert.equal(FakeWebSocket.instances.length,1); const ws=FakeWebSocket.instances[0];
  assert.equal(ws.sent.filter((item)=>item.method==='subscribe').length,1);
  ws.emit({channel:'candle',data:{s:'BTC',i:'1m'}}); assert.equal(first,1);assert.equal(second,1);
  off1(); ws.emit({channel:'candle',data:{s:'BTC',i:'1m'}}); assert.equal(first,1);assert.equal(second,2);
  off2(); assert.ok(ws.sent.some((item)=>item.method==='unsubscribe'));
  await new Promise((resolve)=>setTimeout(resolve,1100)); assert.equal(ws.closed,true);
});


test('snapshot IDs apply only to their captured ticker, resolution, source and session',async()=>{
  const {snapshotApplies}=await import('../src/tradingview_mcp/ui/charts_src/feeds/history.js');
  const symbol={id:'AAPL',source:'yahoo'};
  const window={snapshot_id:'frozen',symbol:'AAPL',source:'yahoo',timeframe:'1d',trading_window:'regular market'};
  assert.equal(snapshotApplies(symbol,'1d','regular market',window),true);
  assert.equal(snapshotApplies(symbol,'1h','regular market',window),false);
  assert.equal(snapshotApplies(symbol,'1d','extended hours',window),false);
  assert.equal(snapshotApplies({id:'SPY',source:'yahoo'},'1d','regular market',window),false);
  assert.equal(snapshotApplies({...symbol,source:'hyperliquid'},'1d','24/7',window),false);
});


test('adaptive settings default off and are forwarded alongside fixed snapshot queries',async()=>{
  const {DEFAULT_STRATEGY}=await import('../src/tradingview_mcp/ui/charts_src/layouts.js');
  const {strategyQuery}=await import('../src/tradingview_mcp/ui/charts_src/hooks/useStrategyData.js');
  assert.equal(DEFAULT_STRATEGY.parameters.adaptive_tightening,false);
  const query=strategyQuery({id:'SPY',source:'yahoo'}, {resolution:'1d',range:'1Y',strategy:{name:'sloped_lines',parameters:{adaptive_tightening:true,adaptive_pivot_bars:1,adaptive_min_improvement_atr:.5}}});
  assert.equal(query.get('adaptive_tightening'),'true');
  assert.equal(query.get('adaptive_pivot_bars'),'1');
  assert.equal(query.get('adaptive_min_improvement_atr'),'0.5');
});
