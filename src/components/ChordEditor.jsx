import { useEffect, useRef, useState } from "react";
import ChordName from "./ChordName";
import Icon from "./Icon";
import { chordParts, formatTime, simplifyChord } from "../lib/music";

// Dialog for fixing one chord. Works in the key the chart is shown in.
export default function ChordEditor({ event, display, onSave, onClose }) {
  const shown = display(event.chord);
  const [value, setValue] = useState(shown);
  const inputRef = useRef(null);
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  // Runs once per opening: focus the field, keep Tab inside the dialog, close
  // on Escape, and hand focus back to the chord that opened it.
  useEffect(() => {
    const opener = document.activeElement;
    inputRef.current?.select();
    const onKey = (e) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key !== "Tab" || !dialogRef.current) return;
      const items = [...dialogRef.current.querySelectorAll("button, input")].filter((el) => !el.disabled);
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  const parts = chordParts(shown);
  const root = parts ? parts.letter + (parts.accidental === "♯" ? "#" : parts.accidental === "♭" ? "b" : "") : null;
  const suggestions = [
    event.alternative && display(event.alternative),
    simplifyChord(shown),
    ...(root ? ["", "m", "7", "maj7", "m7", "sus4", "add9"].map((quality) => root + quality) : []),
  ]
    .filter((chord, index, all) => chord && chord !== shown && all.indexOf(chord) === index)
    .slice(0, 7);

  const save = (chord) => {
    const trimmed = chord.trim();
    if (trimmed) onSave(trimmed);
  };

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="editor-title">
        <header className="dialog__header">
          <div>
            <h2 id="editor-title">Change chord</h2>
            <p>
              At {formatTime(event.start)} · now <ChordName chord={shown} className="inline-chord" />
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </header>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save(value);
          }}
        >
          <label className="field">
            <span>Chord</span>
            <input ref={inputRef} value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false} autoComplete="off" />
          </label>
          {suggestions.length > 0 && (
            <div className="dialog__suggestions" aria-label="Suggestions">
              {suggestions.map((chord) => (
                <button key={chord} type="button" className="chip" onClick={() => save(chord)}>
                  <ChordName chord={chord} />
                  {event.alternative && chord === display(event.alternative) && <em>analyser’s 2nd guess</em>}
                </button>
              ))}
            </div>
          )}
          <div className="dialog__actions">
            <button type="button" className="ghost-btn" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="primary-btn">
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
