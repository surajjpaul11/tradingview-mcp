const INDICATORS = [
  { key: 'fvg', label: 'FVG', title: 'Fair Value Gaps' },
  { key: 'volumeProfile', label: 'VP', title: 'Volume Profile (visible range)' },
];

function IndicatorToggles({ value, onToggle }) {
  return (
    <div className="indicator-toggles" role="group" aria-label="Indicators">
      {INDICATORS.map(({ key, label, title }) => (
        <button
          key={key}
          type="button"
          className="toggle"
          aria-pressed={value[key]}
          title={title}
          onClick={() => onToggle(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default IndicatorToggles;
