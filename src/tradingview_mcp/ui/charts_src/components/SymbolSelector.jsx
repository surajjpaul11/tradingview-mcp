import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { filterSymbolGroups, findSymbol } from '../symbols.js';

function SymbolSelector({ value, groups, onChange }) {
  const rootRef = useRef(null);
  const listboxId = useId();
  const current = findSymbol(value, groups);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(current.label);
  const [activeIndex, setActiveIndex] = useState(0);
  const filteredGroups = useMemo(() => filterSymbolGroups(groups, query), [groups, query]);
  const filteredSymbols = useMemo(() => filteredGroups.flatMap((group) => group.symbols), [filteredGroups]);

  useEffect(() => {
    const closeOnOutsideClick = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick);
  }, []);

  const choose = (symbol) => {
    onChange(symbol.id);
    setQuery(symbol.label);
    setOpen(false);
    setActiveIndex(0);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => Math.min(index + 1, Math.max(0, filteredSymbols.length - 1)));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => Math.max(0, index - 1));
    } else if (event.key === 'Enter' && open && filteredSymbols[activeIndex]) {
      event.preventDefault();
      choose(filteredSymbols[activeIndex]);
    } else if (event.key === 'Escape') {
      setQuery(current.label);
      setOpen(false);
    }
  };

  return (
    <div className="symbol-combobox" ref={rootRef}>
      <input
        className="symbol-combobox__input"
        role="combobox"
        aria-label="Symbol"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        value={open ? query : current.label}
        onFocus={() => { setQuery(''); setOpen(true); setActiveIndex(0); }}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); setActiveIndex(0); }}
        onKeyDown={handleKeyDown}
      />
      {open && (
        <div className="symbol-combobox__menu" id={listboxId} role="listbox">
          {filteredGroups.length ? filteredGroups.map((group) => (
            <div className="symbol-combobox__group" key={group.label}>
              <div className="symbol-combobox__group-label">{group.label}</div>
              {group.symbols.map((symbol) => {
                const index = filteredSymbols.indexOf(symbol);
                return <button type="button" role="option" aria-selected={symbol.id === value} className={index === activeIndex ? 'active' : ''}
                  key={`${symbol.source}:${symbol.id}`} onPointerDown={(event) => event.preventDefault()} onClick={() => choose(symbol)}>
                  <span>{symbol.label}</span><small>{symbol.source === 'hyperliquid' ? 'Hyperliquid' : 'Yahoo'}</small>
                </button>;
              })}
            </div>
          )) : <div className="symbol-combobox__empty">No matching ticker</div>}
        </div>
      )}
    </div>
  );
}

export default SymbolSelector;
