import { DRAWING_TOOLS } from '../drawings.js';

export default function DrawingToolbar({ tool, progress, drawingCount, onToolChange, onUndo, onClear }) {
  const required = DRAWING_TOOLS[tool]?.points || 0;
  const progressLabel = required && progress ? ` ${progress}/${required}` : '';
  return <div className="drawing-toolbar" role="toolbar" aria-label="Drawing tools">
    <button type="button" title="Draw a straight line with two clicks" aria-pressed={tool === 'trendline'} onClick={() => onToolChange(tool === 'trendline' ? 'cursor' : 'trendline')}>Line{tool === 'trendline' ? progressLabel : ''}</button>
    <button type="button" title="Draw a parallel channel with three clicks" aria-pressed={tool === 'parallel_channel'} onClick={() => onToolChange(tool === 'parallel_channel' ? 'cursor' : 'parallel_channel')}>Channel{tool === 'parallel_channel' ? progressLabel : ''}</button>
    <button type="button" title="Undo last drawing" aria-label="Undo last drawing" disabled={!drawingCount} onClick={onUndo}>↶</button>
    <button type="button" title="Clear drawings" disabled={!drawingCount} onClick={onClear}>Clear</button>
  </div>;
}
