import Icon from "./Icon";

function Segmented({ label, value, options, onChange, disabled }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
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

export default function Toolbar({
  instrument,
  onInstrument,
  detail,
  onDetail,
  transposition,
  onTranspose,
  shownKey,
  capo,
  onCapo,
  suggestedCapo,
  sensitivity,
  onSensitivity,
  recharting,
}) {
  return (
    <div className="toolbar" role="toolbar" aria-label="Chart settings">
      <div className="toolbar__group">
        <span className="toolbar__label">Instrument</span>
        <Segmented
          label="Instrument"
          value={instrument}
          onChange={onInstrument}
          options={[
            ["guitar", "Guitar"],
            ["ukulele", "Ukulele"],
            ["piano", "Piano"],
          ]}
        />
      </div>

      <div className="toolbar__group">
        <span className="toolbar__label">Chords</span>
        <Segmented
          label="Chord detail"
          value={detail}
          onChange={onDetail}
          options={[
            ["full", "Full", "Every chord as heard: 7ths, sus, slash chords… (S)"],
            ["simple", "Simple", "Plain triads for strumming along (S)"],
          ]}
        />
      </div>

      <div className="toolbar__group">
        <span className="toolbar__label">Key</span>
        <div className="stepper" role="group" aria-label="Transpose">
          <button
            type="button"
            onClick={() => onTranspose(transposition - 1)}
            aria-label="Transpose down a semitone"
            title="Down a semitone (−)"
          >
            <Icon name="minus" size={16} />
          </button>
          <button
            type="button"
            className="stepper__value"
            onClick={() => onTranspose(0)}
            disabled={transposition === 0}
            title={transposition === 0 ? "Original key" : "Back to the original key"}
          >
            {shownKey}
            {transposition !== 0 && <em>{transposition > 0 ? `+${transposition}` : transposition}</em>}
          </button>
          <button
            type="button"
            onClick={() => onTranspose(transposition + 1)}
            aria-label="Transpose up a semitone"
            title="Up a semitone (+)"
          >
            <Icon name="plus" size={16} />
          </button>
        </div>
      </div>

      {instrument === "guitar" && (
        <div className="toolbar__group">
          <span className="toolbar__label">Capo</span>
          <div className="capo">
            <select value={capo} onChange={(event) => onCapo(Number(event.target.value))} aria-label="Capo fret">
              {Array.from({ length: 8 }, (_, fret) => (
                <option key={fret} value={fret}>
                  {fret === 0 ? "None" : `Fret ${fret}`}
                </option>
              ))}
            </select>
            {suggestedCapo > 0 && capo !== suggestedCapo && (
              <button
                type="button"
                className="chip chip--accent"
                onClick={() => onCapo(suggestedCapo)}
                title="Lets you play easier open shapes"
              >
                <Icon name="sparkle" size={14} /> Try capo {suggestedCapo}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="toolbar__group">
        <span className="toolbar__label">Chord changes</span>
        <Segmented
          label="Chord changes"
          value={sensitivity}
          onChange={onSensitivity}
          disabled={recharting}
          options={[
            ["normal", "Steady", "Fewer, steadier changes. Best for most songs."],
            ["sensitive", recharting ? "Updating…" : "Quick", "Catches fast changes like Gm–Bb every two beats; may add a few extra."],
          ]}
        />
      </div>
    </div>
  );
}
