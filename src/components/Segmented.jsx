// A row of mutually exclusive options (radio group styled as a pill switch).
export default function Segmented({ label, value, options, onChange, disabled, size }) {
  return (
    <div className={`segmented ${size === "small" ? "segmented--small" : ""}`} role="radiogroup" aria-label={label}>
      {options.map(([optionValue, optionLabel, hint]) => (
        <button
          key={optionValue}
          type="button"
          role="radio"
          aria-checked={value === optionValue}
          className={value === optionValue ? "is-on" : ""}
          onClick={() => onChange(optionValue)}
          disabled={disabled}
          title={hint}
        >
          {optionLabel}
        </button>
      ))}
    </div>
  );
}
