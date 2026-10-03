import { SYMBOL_GROUPS } from '../symbols.js';

function SymbolSelector({ value, onChange }) {
  const handleChange = (event) => onChange(event.target.value);

  return (
    <select
      className="select select--compact"
      aria-label="Symbol"
      value={value}
      onChange={handleChange}
    >
      {SYMBOL_GROUPS.map((group) => (
        <optgroup key={group.label} label={group.label}>
          {group.symbols.map((symbol) => (
            <option key={symbol.id} value={symbol.id}>
              {symbol.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

export default SymbolSelector;
