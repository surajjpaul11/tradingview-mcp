import { PANE_OPTIONS } from '../layouts.js';

function PaneSelector({ value, onChange }) {
  const handleChange = (event) => onChange(Number(event.target.value));

  return (
    <label className="pane-selector">
      <span className="pane-selector__label">Layout</span>
      <select
        className="select"
        value={value}
        onChange={handleChange}
      >
        {PANE_OPTIONS.map((count) => (
          <option key={count} value={count}>
            {count} {count === 1 ? 'pane' : 'panes'}
          </option>
        ))}
      </select>
    </label>
  );
}

export default PaneSelector;
