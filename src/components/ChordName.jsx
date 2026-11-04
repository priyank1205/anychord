import { chordParts } from "../lib/music";

// Typesets a chord like a printed chart: big root, real ♯/♭, smaller quality,
// slash bass set apart. Falls back to plain text for anything unusual.
export default function ChordName({ chord, className = "" }) {
  if (!chord || chord === "N.C.") {
    return <span className={`chord-name chord-name--rest ${className}`}>N.C.</span>;
  }
  const parts = chordParts(chord);
  if (!parts) return <span className={`chord-name ${className}`}>{chord}</span>;
  return (
    <span className={`chord-name ${className}`} aria-label={chord}>
      <span className="chord-name__root" aria-hidden="true">
        {parts.letter}
        {parts.accidental && <span className="chord-name__accidental">{parts.accidental}</span>}
      </span>
      {parts.quality && (
        <span className="chord-name__quality" aria-hidden="true">
          {parts.quality}
        </span>
      )}
      {parts.bass && (
        <span className="chord-name__bass" aria-hidden="true">
          /{parts.bass.letter}
          {parts.bass.accidental}
        </span>
      )}
    </span>
  );
}
