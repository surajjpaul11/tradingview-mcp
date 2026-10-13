import { useEffect, useState } from 'react';
import LayoutController from './components/LayoutController.jsx';
import PaneSelector from './components/PaneSelector.jsx';
import StrategyDrawer from './components/StrategyDrawer.jsx';
import { DEFAULT_PANE_COUNT, DEFAULT_PANES } from './layouts.js';
import { buildSymbolGroups, findSymbol, SYMBOL_GROUPS } from './symbols.js';
import './App.css';

const STORAGE_KEY='hyperliquid-charts-workspace-v1';
function loadWorkspace(){
  try{const value=JSON.parse(localStorage.getItem(STORAGE_KEY));if(value?.panes?.length===8)return {...value,panes:value.panes.map((pane)=>({...pane,tradingWindow:pane.tradingWindow||'regular market'}))};}catch{}
  return {paneCount:DEFAULT_PANE_COUNT,panes:DEFAULT_PANES};
}
function App(){
  const [workspace,setWorkspace]=useState(loadWorkspace);
  const [symbolGroups,setSymbolGroups]=useState(SYMBOL_GROUPS);
  const [activePane,setActivePane]=useState(0);
  const [drawerOpen,setDrawerOpen]=useState(false);
  useEffect(()=>localStorage.setItem(STORAGE_KEY,JSON.stringify(workspace)),[workspace]);
  useEffect(()=>{
    const controller=new AbortController();
    fetch('/api/filters',{signal:controller.signal})
      .then((response)=>response.ok?response.json():Promise.reject(new Error(`Symbols: HTTP ${response.status}`)))
      .then((data)=>setSymbolGroups(buildSymbolGroups(data.symbols)))
      .catch((error)=>{if(error.name!=='AbortError')console.error(error);});
    return ()=>controller.abort();
  },[]);
  const setPaneCount=(paneCount)=>setWorkspace((current)=>({...current,paneCount}));
  const changePane=(index,patch)=>setWorkspace((current)=>{
    const target=current.panes[index]; const changes=typeof patch==='function'?patch(target):patch;
    const updated={...target,...changes}; const activating=Boolean(changes.strategy?.enabled);
    return {...current,panes:current.panes.map((pane,i)=>{
      if(i===index)return updated;
      return activating?{...pane,strategy:{...pane.strategy,enabled:false}}:pane;
    })};
  });
  const activatePane=(index)=>{
    setActivePane(index);
    setWorkspace((current)=>({...current,panes:current.panes.map((pane,i)=>i===index?pane:{...pane,strategy:{...pane.strategy,enabled:false}})}));
  };
  const pane=workspace.panes[activePane]; const symbol=findSymbol(pane.symbolId,symbolGroups);
  return <div className="app">
    <header className="app__toolbar">
      <a className="app__title" href="/charts">Hyperliquid Charts</a>
      <div className="toolbar-actions"><a href="/">Strategy Dashboard</a><PaneSelector value={workspace.paneCount} onChange={setPaneCount}/></div>
    </header>
    <main className={`app__workspace ${drawerOpen?'drawer-open':''}`}>
      <LayoutController paneCount={workspace.paneCount} panes={workspace.panes} activePane={activePane}
        symbolGroups={symbolGroups} onActivate={activatePane} onPaneChange={changePane} onOpenStrategy={(index)=>{activatePane(index);setDrawerOpen(true);}}/>
      {drawerOpen&&<StrategyDrawer pane={pane} symbol={symbol} onChange={(patch)=>changePane(activePane,patch)} onClose={()=>setDrawerOpen(false)}/>} 
    </main>
  </div>;
}
export default App;
