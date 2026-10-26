import assert from 'node:assert/strict';
import net from 'node:net';
import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright-core';

const ROOT=new URL('..',import.meta.url).pathname.replace(/\/$/,'');
const chrome=['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'].find(existsSync);
const freePort=async()=>{
  for(let port=8001;port<=8004;port++){
    const available=await new Promise((resolve)=>{const server=net.createServer();server.once('error',()=>resolve(false));server.listen(port,'0.0.0.0',()=>server.close(()=>resolve(true)));});
    if(available)return port;
  }
  throw new Error('No free test port in 8001–8004');
};
async function start(){const port=await freePort();const python=process.env.PYTHON_BIN||(existsSync(`${ROOT}/.venv/bin/python`)?`${ROOT}/.venv/bin/python`:'python3');const child=spawn(python,['-m','uvicorn','tradingview_mcp.ui.server:app','--host','0.0.0.0','--port',String(port)],{cwd:ROOT,env:{...process.env,PYTHONPATH:`${ROOT}/src`},stdio:'ignore'});const url=`http://127.0.0.1:${port}`;for(let i=0;i<100;i++){try{if((await fetch(`${url}/charts`)).ok)return{url,child};}catch{}await new Promise((r)=>setTimeout(r,100));}throw new Error('charts server did not start');}
assert.ok(chrome,'Chrome or Edge is required');
const dashboard=await start();const browser=await chromium.launch({executablePath:chrome,headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on('pageerror',(error)=>errors.push(error.message));page.setDefaultTimeout(15000);
await page.addInitScript(()=>{
  class FakeWebSocket{
    static OPEN=1; constructor(){this.readyState=0;setTimeout(()=>{this.readyState=1;this.onopen?.();},0);}
    send(value){const message=JSON.parse(value);if(message.method==='subscribe'&&message.subscription.type==='candle'){setTimeout(()=>this.onmessage?.({data:JSON.stringify({channel:'candle',data:{s:message.subscription.coin,i:message.subscription.interval,t:240000,o:'13',h:'15',l:'12',c:'14',v:'40'}})}),40);}}
    close(){this.readyState=3;}
  }
  window.WebSocket=FakeWebSocket;
});
const candles=[
  {time:60,date:'1970-01-01 00:01',open:10,high:11,low:9,close:10.5,volume:10},
  {time:120,date:'1970-01-01 00:02',open:10.5,high:12,low:10,close:11.5,volume:20},
  {time:180,date:'1970-01-01 00:03',open:13,high:14,low:13,close:13.5,volume:30},
];
await page.route('**/api/chart/candles?**',(route)=>route.fulfill({json:{source:new URL(route.request().url()).searchParams.get('source'),candles,timeframe:'1m',period:'1d',data_status:{source:'sqlite',complete:true,stale:false,data_revision:'1:2',as_of:180}}}));
await page.route('**/api/filters',(route)=>route.fulfill({json:{symbols:['AAPL','SNDK','WULF'],strategies:['sloped_lines','enhanced_channel']}}));
await page.route('**/api/best-parameters?**',(route)=>route.fulfill({json:{found:true,data:{timeframe:'1d',period:'1y',backtest_window:{start_date:'2025-09-26',end_date:'2026-09-25',trading_window:'regular market'},snapshot_id:'test-snapshot',snapshot_origin:'reconstructed',parameters:{line_breakout_buy:true,entry_barrier_sell:true,pivot_lookback:5,anchor_source:'any_valid_candle',validation_boundary:'close',trendline_tolerance:.015},performance:{total_pnl_pct:47.61}}}}));
await page.route('**/api/stats?**',(route)=>route.fulfill({json:{total_pnl_pct:12.5,buy_and_hold_pct:8.1,win_rate_pct:55,total_trades:2}}));
await page.route('**/api/trades?**',(route)=>route.fulfill({json:{trades:[{created_at:'1970-01-01T00:01:00Z',closed_at:'1970-01-01T00:03:00Z',entry_price:10,exit_price:13,pnl_pct:30,entry_reason:'breakout',exit_reason:'support break'}]}}));
await page.route('**/api/trendlines?**',(route)=>route.fulfill({json:{trendlines:[{type:'resistance',status:'active',color:'#10b981',points:[{time:60,value:11},{time:180,value:14}]}]}}));
await page.route('**/api/channels?**',(route)=>route.fulfill({json:{overlays:[]}}));
try{
  await page.goto(`${dashboard.url}/charts`,{waitUntil:'networkidle'});
  await page.waitForFunction(()=>Number(document.querySelector('.lightweight-chart')?.dataset.candleCount)>=4);
  assert.equal(await page.locator('.chart-widget').count(),1);assert.ok(await page.locator('canvas').count()>0);
  await page.getByTitle('Fair Value Gaps').click();await page.getByTitle('Volume Profile (visible range)').click();
  assert.equal(await page.getByTitle('Fair Value Gaps').getAttribute('aria-pressed'),'true');
  const firstChartBody=page.locator('.chart-widget').first().locator('.chart-widget__body');
  await page.locator('.chart-widget').first().getByRole('button',{name:'Line'}).click();
  await page.waitForFunction(()=>document.querySelector('.chart-widget__body')?.dataset.drawingTool==='trendline');
  await firstChartBody.click({position:{x:180,y:260}});await page.waitForFunction(()=>document.querySelector('.drawing-toolbar button[aria-pressed="true"]')?.textContent.includes('1/2'));await page.waitForTimeout(550);await firstChartBody.click({position:{x:620,y:150}});
  await page.waitForFunction(()=>Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.drawingCount)===1);
  await page.locator('.chart-widget').first().getByRole('button',{name:'Channel'}).click();
  await page.waitForFunction(()=>document.querySelector('.chart-widget__body')?.dataset.drawingTool==='parallel_channel');
  await page.waitForTimeout(550);
  await firstChartBody.click({position:{x:220,y:300}});await page.waitForFunction(()=>document.querySelector('.drawing-toolbar button[aria-pressed="true"]')?.textContent.includes('1/3'));await page.waitForTimeout(550);
  await firstChartBody.click({position:{x:650,y:210}});await page.waitForFunction(()=>document.querySelector('.drawing-toolbar button[aria-pressed="true"]')?.textContent.includes('2/3'));await page.waitForTimeout(550);
  await firstChartBody.click({position:{x:400,y:120}});
  await page.waitForFunction(()=>Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.drawingCount)===2);
  await page.locator('.chart-widget').first().getByRole('button',{name:'Undo last drawing'}).click();
  await page.waitForFunction(()=>Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.drawingCount)===1);
  await page.locator('.pane-selector select').selectOption('2');await page.waitForFunction(()=>document.querySelectorAll('.chart-widget').length===2);
  const symbolSearch=page.locator('.chart-widget').nth(1).getByRole('combobox',{name:'Symbol'});
  await symbolSearch.fill('WULF');
  await page.locator('.chart-widget').nth(1).getByRole('option',{name:/WULF/}).click();
  assert.equal(await symbolSearch.inputValue(),'WULF');
  await page.locator('.chart-widget').first().getByRole('button',{name:'Strategy'}).click();
  await page.getByRole('checkbox',{name:'Show strategy'}).check();
  assert.equal(await page.getByRole('checkbox',{name:'Line Breakout Buy',exact:true}).isChecked(),false);
  assert.equal(await page.getByRole('checkbox',{name:'Entry Barrier Sell',exact:true}).isChecked(),false);
  const adaptive=page.getByRole('checkbox',{name:'Adaptive line tightening',exact:true});
  assert.equal(await adaptive.isChecked(),false);
  const adaptiveResponse=page.waitForResponse(response=>response.url().includes('/api/stats?')&&response.url().includes('adaptive_tightening=true')&&response.url().includes('adaptive_pivot_bars=1')&&response.url().includes('adaptive_min_improvement_atr=0.5'));
  await adaptive.check();
  await page.getByLabel('Adaptive confirmation',{exact:true}).selectOption('1');
  await page.getByLabel('Minimum tightening (ATR)',{exact:true}).selectOption('0.5');
  await adaptiveResponse;
  const peakFull=page.getByRole('checkbox',{name:'Peak Reclaim Full Candle',exact:true});
  const generalFull=page.getByRole('checkbox',{name:'Full candle',exact:true});
  assert.equal(await peakFull.isChecked(),false);
  await peakFull.check();
  assert.equal(await generalFull.isChecked(),false);
  await generalFull.check();
  assert.equal(await peakFull.isChecked(),true);
  await generalFull.uncheck();
  await page.getByRole('checkbox',{name:'Line Breakout Buy',exact:true}).check();
  await page.getByRole('checkbox',{name:'Entry Barrier Sell',exact:true}).check();
  await page.getByRole('checkbox',{name:'Staggered Lines'}).check();
  assert.equal(await page.getByRole('checkbox',{name:'Staggered Lines'}).isChecked(),true);
  assert.equal(await page.getByRole('checkbox',{name:'Active Line Labels'}).isChecked(),false);
  await page.getByRole('checkbox',{name:'Active Line Labels'}).check();
  assert.equal(await page.getByRole('checkbox',{name:'Active Line Labels'}).isChecked(),true);
  await page.waitForFunction(()=>document.querySelector('.chart-widget [role="group"][aria-label="Candle resolution"] [aria-pressed="true"]')?.textContent==='1h'&&document.querySelector('.chart-widget [role="group"][aria-label="Timeline"] [aria-pressed="true"]')?.textContent==='1M');
  await page.waitForFunction(()=>Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.markerCount)>=2&&Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.overlayCount)>=1);
  assert.match(await page.locator('.pane-stats').first().innerText(),/12.5%/);
  assert.equal(await adaptive.isChecked(),true);
  assert.equal(await page.getByRole('checkbox',{name:'Compounding',exact:true}).isChecked(),true);
  await page.getByRole('checkbox',{name:'Compounding',exact:true}).uncheck();
  await page.getByLabel('Starting Capital ($)',{exact:true}).fill('500');
  await page.getByRole('checkbox',{name:'Line Breakout Buy',exact:true}).uncheck();
  await page.getByRole('checkbox',{name:'Entry Barrier Sell',exact:true}).uncheck();
  await page.getByRole('button',{name:/Saved Best/}).click();await page.waitForFunction(()=>[...document.querySelectorAll('.drawer-message')].some((element)=>element.textContent.includes('47.61%')));
  assert.equal(await adaptive.isChecked(),false);
  assert.equal(await page.getByLabel('Adaptive confirmation',{exact:true}).inputValue(),'2');
  assert.equal(await page.getByLabel('Minimum tightening (ATR)',{exact:true}).inputValue(),'0.25');
  assert.equal(await page.getByRole('checkbox',{name:'Line Breakout Buy',exact:true}).isChecked(),true);
  assert.equal(await page.getByRole('checkbox',{name:'Entry Barrier Sell',exact:true}).isChecked(),true);
  assert.equal(await page.getByRole('checkbox',{name:'Compounding',exact:true}).isChecked(),true);
  assert.equal(await page.getByLabel('Starting Capital ($)',{exact:true}).inputValue(),'10000');
  assert.equal(await peakFull.isChecked(),false);
  assert.ok(await page.getByText('Saved window: 2025-09-26 → 2026-09-25').isVisible());
  await page.locator('.chart-widget').nth(1).locator('.chart-widget__body').click({position:{x:20,y:20}});
  assert.equal(await page.locator('.chart-widget').first().locator('.strategy-toggle').evaluate((element)=>element.classList.contains('enabled')),false);
  await page.reload({waitUntil:'networkidle'});await page.waitForFunction(()=>document.querySelectorAll('.chart-widget').length===2);
  await page.waitForFunction(()=>Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.drawingCount)===1);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,panes:2,liveCandles:4,strategyMarkers:2,overlays:1,drawings:1}));
}finally{await browser.close();dashboard.child.kill('SIGTERM');}
