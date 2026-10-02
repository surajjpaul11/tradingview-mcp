import assert from 'node:assert/strict';
import net from 'node:net';
import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright-core';

const ROOT=new URL('..',import.meta.url).pathname.replace(/\/$/,'');
const chrome=['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'].find(existsSync);
const freePort=()=>new Promise((resolve,reject)=>{const server=net.createServer();server.once('error',reject);server.listen(0,'127.0.0.1',()=>{const {port}=server.address();server.close(()=>resolve(port));});});
async function start(){const port=await freePort();const python=existsSync(`${ROOT}/.venv/bin/python`)?`${ROOT}/.venv/bin/python`:'python3';const child=spawn(python,['-m','uvicorn','tradingview_mcp.ui.server:app','--host','127.0.0.1','--port',String(port)],{cwd:ROOT,env:{...process.env,PYTHONPATH:`${ROOT}/src`},stdio:'ignore'});const url=`http://127.0.0.1:${port}`;for(let i=0;i<100;i++){try{if((await fetch(`${url}/charts`)).ok)return{url,child};}catch{}await new Promise((r)=>setTimeout(r,100));}throw new Error('charts server did not start');}
assert.ok(chrome,'Chrome or Edge is required');
const dashboard=await start();const browser=await chromium.launch({executablePath:chrome,headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on('pageerror',(error)=>errors.push(error.message));
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
await page.route('**/api/chart/candles?**',(route)=>route.fulfill({json:{source:new URL(route.request().url()).searchParams.get('source'),candles,timeframe:'1m',period:'1d'}}));
await page.route('**/api/filters',(route)=>route.fulfill({json:{symbols:['AAPL'],strategies:['sloped_lines','enhanced_channel']}}));
await page.route('**/api/best-parameters?**',(route)=>route.fulfill({json:{found:true,data:{parameters:{pivot_lookback:5,anchor_source:'any_valid_candle',validation_boundary:'close',trendline_tolerance:.015},performance:{total_pnl_pct:47.61}}}}));
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
  await page.locator('.pane-selector select').selectOption('2');await page.waitForFunction(()=>document.querySelectorAll('.chart-widget').length===2);
  await page.locator('.chart-widget').nth(1).locator('select[aria-label="Symbol"]').selectOption('AAPL');
  await page.locator('.chart-widget').first().getByRole('button',{name:'Strategy'}).click();
  await page.getByRole('checkbox',{name:'Show strategy'}).check();
  await page.waitForFunction(()=>document.querySelector('.chart-widget [role="group"][aria-label="Candle resolution"] [aria-pressed="true"]')?.textContent==='1h'&&document.querySelector('.chart-widget [role="group"][aria-label="Timeline"] [aria-pressed="true"]')?.textContent==='1M');
  await page.waitForFunction(()=>Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.markerCount)>=2&&Number(document.querySelector('.chart-widget .lightweight-chart')?.dataset.overlayCount)>=1);
  assert.match(await page.locator('.pane-stats').first().innerText(),/12.5%/);
  await page.getByRole('button',{name:/Saved Best/}).click();await page.waitForFunction(()=>document.querySelector('.drawer-message')?.textContent.includes('47.61%'));
  await page.locator('.chart-widget').nth(1).locator('.chart-widget__body').click({position:{x:20,y:20}});
  assert.equal(await page.locator('.chart-widget').first().locator('.strategy-toggle').evaluate((element)=>element.classList.contains('enabled')),false);
  await page.reload({waitUntil:'networkidle'});await page.waitForFunction(()=>document.querySelectorAll('.chart-widget').length===2);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,panes:2,liveCandles:4,strategyMarkers:2,overlays:1}));
}finally{await browser.close();dashboard.child.kill('SIGTERM');}
