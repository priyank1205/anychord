import guitarDb from "@tombatossals/chords-db/lib/guitar.json";
import ukuleleDb from "@tombatossals/chords-db/lib/ukulele.json";
import { chordParts, chordPitchClasses } from "../lib/music";

// chords-db spells some roots differently per instrument.
const ROOT_KEYS = {
  guitar: { "C#": "Csharp", Db: "Csharp", "D#": "Eb", "F#": "Fsharp", Gb: "Fsharp", "G#": "Ab", "A#": "Bb" },
  ukulele: { "C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb" },
};
const SUFFIXES = { "": "major", m: "minor", mMaj7: "mmaj7" };
const OPEN_STRINGS = { guitar: [4, 9, 2, 7, 11, 4], ukulele: [7, 0, 4, 9] };

function lookupShape(chord, instrument) {
  const parts = chordParts(chord);
  if (!parts) return null;
  const root = parts.letter + (parts.accidental === "♯" ? "#" : parts.accidental === "♭" ? "b" : "");
  const db = instrument === "guitar" ? guitarDb : ukuleleDb;
  const key = ROOT_KEYS[instrument][root] ?? root;
  if (parts.quality === "5" && instrument === "guitar") {
    // Power chord on the low E string (or A string if that sits lower on the neck).
    const pc = chordPitchClasses(chord).root;
    const onE = (pc - 4 + 12) % 12;
    const onA = (pc - 9 + 12) % 12;
    const frets = onE <= onA ? [onE, onE + 2, onE + 2, -1, -1, -1] : [-1, onA, onA + 2, onA + 2, -1, -1];
    const base = frets.includes(0) ? 1 : Math.min(...frets.filter((f) => f > 0));
    return { frets: frets.map((f) => (f > 0 ? f - base + 1 : f)), fingers: [], baseFret: base, barres: [] };
  }
  const shapes = db.chords[key]?.find((c) => c.suffix === (SUFFIXES[parts.quality] ?? parts.quality));
  return shapes?.positions?.[0] ?? null;
}

function FretDiagram({ chord, instrument, size }) {
  const shape = lookupShape(chord, instrument);
  const strings = instrument === "guitar" ? 6 : 4;
  const frets = 4;
  const width = 100;
  const height = 112;
  const left = 18;
  const top = 22;
  const gridWidth = width - left * 2;
  const gridHeight = 76;
  const stringGap = gridWidth / (strings - 1);
  const fretGap = gridHeight / frets;

  if (!shape) {
    return (
      <div className="diagram diagram--missing" style={{ width: size }}>
        <span>No {instrument} shape for this one yet</span>
      </div>
    );
  }
  const base = shape.baseFret || 1;
  const x = (string) => left + string * stringGap;
  const y = (fret) => top + (fret - 0.5) * fretGap;
  return (
    <svg className="diagram" viewBox={`0 0 ${width} ${height}`} width={size} role="img" aria-label={`${chord} on ${instrument}`}>
      <rect x={left} y={top} width={gridWidth} height={gridHeight} rx="2" className="diagram__board" />
      {Array.from({ length: frets + 1 }, (_, i) => (
        <line key={`f${i}`} x1={left} x2={left + gridWidth} y1={top + i * fretGap} y2={top + i * fretGap} className="diagram__fret" />
      ))}
      {Array.from({ length: strings }, (_, i) => (
        <line key={`s${i}`} x1={x(i)} x2={x(i)} y1={top} y2={top + gridHeight} className="diagram__string" />
      ))}
      {base === 1 ? (
        <rect x={left - 1} y={top - 3.5} width={gridWidth + 2} height="4" rx="1.5" className="diagram__nut" />
      ) : (
        <text x={left - 6} y={top + fretGap * 0.5 + 3.5} className="diagram__base" textAnchor="end">
          {base}
        </text>
      )}
      {(shape.barres ?? []).map((fret) => {
        const covered = shape.frets.map((f, i) => (f >= fret ? i : null)).filter((i) => i !== null);
        if (covered.length < 2) return null;
        return (
          <rect
            key={`b${fret}`}
            x={x(covered[0]) - 5.5}
            y={y(fret) - 5.5}
            width={x(covered[covered.length - 1]) - x(covered[0]) + 11}
            height="11"
            rx="5.5"
            className="diagram__dot"
          />
        );
      })}
      {shape.frets.map((fret, string) => {
        if (fret === -1) {
          return (
            <text key={`m${string}`} x={x(string)} y={top - 8} className="diagram__mark" textAnchor="middle">
              ×
            </text>
          );
        }
        if (fret === 0) {
          return <circle key={`o${string}`} cx={x(string)} cy={top - 11} r="3.4" className="diagram__open" />;
        }
        const finger = shape.fingers?.[string];
        return (
          <g key={`d${string}`}>
            <circle cx={x(string)} cy={y(fret)} r="5.6" className="diagram__dot" />
            {finger > 0 && (
              <text x={x(string)} y={y(fret) + 2.6} className="diagram__finger" textAnchor="middle">
                {finger}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

const WHITE = [0, 2, 4, 5, 7, 9, 11];
const BLACK = [1, 3, 6, 8, 10];
const BLACK_OFFSET = { 1: 1, 3: 2, 6: 4, 8: 5, 10: 6 };

function PianoDiagram({ chord, size }) {
  const pcs = chordPitchClasses(chord);
  if (!pcs) {
    return (
      <div className="diagram diagram--missing" style={{ width: size }}>
        <span>No piano voicing for this one yet</span>
      </div>
    );
  }
  // Voice the chord upwards from its root, starting in the lowest octave
  // shown; a slash bass sits below the root.
  const bass = pcs.bass !== pcs.root ? pcs.bass : null;
  const lit = new Set();
  let previous = pcs.notes[0] + (bass !== null && pcs.notes[0] <= bass ? 12 : 0);
  lit.add(previous);
  for (const pc of pcs.notes.slice(1)) {
    let note = pc;
    while (note <= previous) note += 12;
    lit.add(note);
    previous = note;
  }
  const octaves = Math.max(2, Math.ceil((previous + 1) / 12));
  const keyWidth = 13;
  const width = 7 * octaves * keyWidth;
  const height = 56;
  const isLit = (midi) => lit.has(midi);
  return (
    <svg className="diagram diagram--piano" viewBox={`0 0 ${width} ${height + 2}`} width={size} role="img" aria-label={`${chord} on piano`}>
      {Array.from({ length: octaves }, (_, octave) =>
        WHITE.map((pc, i) => {
          const midi = octave * 12 + pc;
          const cls =
            midi === bass
              ? "piano__key piano__key--white piano__key--bass"
              : isLit(midi)
                ? "piano__key piano__key--white piano__key--on"
                : "piano__key piano__key--white";
          return (
            <rect key={`w${midi}`} x={(octave * 7 + i) * keyWidth} y="1" width={keyWidth - 1.2} height={height} rx="2.4" className={cls} />
          );
        }),
      )}
      {Array.from({ length: octaves }, (_, octave) =>
        BLACK.map((pc) => {
          const midi = octave * 12 + pc;
          const cls =
            midi === bass
              ? "piano__key piano__key--black piano__key--bass"
              : isLit(midi)
                ? "piano__key piano__key--black piano__key--on"
                : "piano__key piano__key--black";
          return (
            <rect
              key={`b${midi}`}
              x={(octave * 7 + BLACK_OFFSET[pc]) * keyWidth - 4.4}
              y="1"
              width="8"
              height={height * 0.6}
              rx="1.8"
              className={cls}
            />
          );
        }),
      )}
    </svg>
  );
}

export default function ChordDiagram({ chord, instrument, size = 120 }) {
  if (!chord || chord === "N.C.") {
    return (
      <div className="diagram diagram--missing" style={{ width: size }}>
        <span>No chord</span>
      </div>
    );
  }
  return instrument === "piano" ? (
    <PianoDiagram chord={chord} size={size} />
  ) : (
    <FretDiagram chord={chord} instrument={instrument} size={size} />
  );
}
