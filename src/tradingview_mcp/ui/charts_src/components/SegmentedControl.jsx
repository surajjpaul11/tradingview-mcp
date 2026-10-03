// A row of mutually exclusive buttons. Unavailable options use aria-disabled
// rather than `disabled` so their tooltip (the reason) still shows on hover.
function SegmentedControl({ label, options, value, onChange, className = '' }) {
  return (
    <div className={`segmented ${className}`} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          className="segmented__button"
          aria-pressed={option.id === value}
          aria-disabled={option.disabled}
          title={option.title || undefined}
          onClick={() => !option.disabled && onChange(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export default SegmentedControl;
