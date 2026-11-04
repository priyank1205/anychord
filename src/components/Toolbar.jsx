import Icon from "./Icon";
import Segmented from "./Segmented";

export default function Toolbar({
  instrument,
  detail,
  onDetail,
  transposition,
  onTranspose,
  shownKey,
  originalKey,
  capo,
  onCapo,
  suggestedCapo,
  sensitivity,
  onSensitivity,
  recharting,
}) {
  return (
    <div className="toolbar" role="toolbar" aria-label="Chart settings">
      <div className="toolbar__group toolbar__group--detail">
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

      <div className="toolbar__group toolbar__group--key">
        <span className="toolbar__label">Key</span>
        <div className="key-control">
          <div className="stepper" role="group" aria-label="Transpose">
            <button
              type="button"
              onClick={() => onTranspose(transposition - 1)}
              aria-label="Transpose down a semitone"
              title="Down a semitone (−)"
            >
              <Icon name="minus" size={16} />
            </button>
            <span className="stepper__value" aria-live="polite">
              {shownKey}
              {transposition !== 0 && <em>{transposition > 0 ? `+${transposition}` : transposition}</em>}
            </span>
            <button
              type="button"
              onClick={() => onTranspose(transposition + 1)}
              aria-label="Transpose up a semitone"
              title="Up a semitone (+)"
            >
              <Icon name="plus" size={16} />
            </button>
          </div>
          {transposition !== 0 && (
            <button
              type="button"
              className="ghost-btn key-control__reset"
              onClick={() => onTranspose(0)}
              aria-label={`Reset to the original key, ${originalKey}`}
              title={`Back to ${originalKey} (0)`}
            >
              <Icon name="reset" size={15} />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {instrument === "guitar" && (
        <div className="toolbar__group toolbar__group--capo">
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

      <div className="toolbar__group toolbar__group--changes">
        <span className="toolbar__label">Chord changes</span>
        <Segmented
          label="Chord changes"
          value={sensitivity}
          onChange={onSensitivity}
          disabled={recharting}
          options={[
            ["normal", "Steady", "Fewer, steadier changes. Best for most songs."],
            [
              "sensitive",
              recharting ? "Updating…" : "Catch fast changes",
              "Also finds chords that last only a beat or two, like Gm–B♭ flips. May add a few extras.",
            ],
          ]}
        />
      </div>
    </div>
  );
}
