import ChartWidget from './ChartWidget.jsx';
export default function LayoutController({paneCount,panes,activePane,symbolGroups,onActivate,onPaneChange,onOpenStrategy}){
  return <div className="layout-grid" data-panes={paneCount}>{panes.slice(0,paneCount).map((pane,index)=><ChartWidget key={index} pane={pane} active={activePane===index}
    symbolGroups={symbolGroups} onActivate={()=>onActivate(index)} onPaneChange={(patch)=>onPaneChange(index,patch)} onOpenStrategy={()=>onOpenStrategy(index)}/>)}</div>;
}
