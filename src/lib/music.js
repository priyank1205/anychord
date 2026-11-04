// Key-aware spelling and transposition. Mirrors server/music.py so a chart
// transposed in the browser is spelled the way the analyser would spell it
// (Bb in F major, A# in B major).

export const NOTE_INDEX = {
  C: 0,
  "B#": 0,
  "C#": 1,
  Db: 1,
  D: 2,
  "D#": 3,
  Eb: 3,
  E: 4,
  Fb: 4,
  "E#": 5,
  F: 5,
  "F#": 6,
  Gb: 6,
  G: 7,
  "G#": 8,
  Ab: 8,
  A: 9,
  "A#": 10,
  Bb: 10,
  B: 11,
  Cb: 11,
};

const SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
const NEUTRAL_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const MAJOR_TONIC_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const MINOR_TONIC_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"];
const FLAT_MAJOR_TONICS = new Set([5, 10, 3, 8, 1]);
const SHARP_MAJOR_TONICS = new Set([7, 2, 9, 4, 11, 6]);

export function parseKey(text) {
  const match = /^([A-G][#b]?)\s+(major|minor)$/.exec((text ?? "").trim());
  if (!match || NOTE_INDEX[match[1]] === undefined) return null;
  return { tonic: NOTE_INDEX[match[1]], mode: match[2] };
}

export function formatKey({ tonic, mode }) {
  const names = mode === "major" ? MAJOR_TONIC_NAMES : MINOR_TONIC_NAMES;
  return `${names[tonic]} ${mode}`;
}

function keySignatureNames(key) {
  if (!key) return SHARP_NAMES;
  const majorTonic = key.mode === "major" ? key.tonic : (key.tonic + 3) % 12;
  if (FLAT_MAJOR_TONICS.has(majorTonic)) return FLAT_NAMES;
  if (SHARP_MAJOR_TONICS.has(majorTonic)) return SHARP_NAMES;
  return NEUTRAL_NAMES;
}

const mod12 = (value) => ((value % 12) + 12) % 12;

export function transposeKey(text, semitones) {
  const key = parseKey(text);
  if (!key || !semitones) return text;
  return formatKey({ tonic: mod12(key.tonic + semitones), mode: key.mode });
}

const LETTERS = "CDEFGAB";
const LETTER_PC = [0, 2, 4, 5, 7, 9, 11];
const INTERVAL_STEPS = { 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 4, 9: 5, 10: 6, 11: 6 };
const CHORD_PATTERN = /^([A-G][#b]?)([^/]*)(?:\/([A-G][#b]?))?$/;

// The note `interval` semitones above `rootName`, spelled by letter: the
// major third above D is F#, never Gb, whatever the key signature says.
function spellAbove(rootName, interval) {
  const letter = (LETTERS.indexOf(rootName[0]) + INTERVAL_STEPS[interval]) % 7;
  const offset = mod12(NOTE_INDEX[rootName] + interval - LETTER_PC[letter] + 6) - 6;
  const accidental = { 0: "", 1: "#", [-1]: "b" }[offset];
  return accidental === undefined ? null : LETTERS[letter] + accidental;
}

// Transpose a chord symbol and spell it for `keyText` (the key it ends up in).
// Untransposed chords are returned untouched so manual edits stay as typed.
export function transposeChord(chord, semitones, keyText) {
  if (!semitones || !chord || chord === "N.C.") return chord;
  const match = CHORD_PATTERN.exec(chord.trim());
  if (!match || NOTE_INDEX[match[1]] === undefined) return chord;
  const [, root, suffix, bass] = match;
  const names = keySignatureNames(parseKey(keyText));
  const newRoot = names[mod12(NOTE_INDEX[root] + semitones)];
  if (!bass || NOTE_INDEX[bass] === undefined) return newRoot + suffix;
  const interval = mod12(NOTE_INDEX[bass] - NOTE_INDEX[root]);
  const newBass = (interval && spellAbove(newRoot, interval)) || names[mod12(NOTE_INDEX[bass] + semitones)];
  return `${newRoot}${suffix}/${newBass}`;
}

// The triad a beginner would strum: Bbmaj7/D -> Bb, F#m9 -> F#m, Bm7b5 -> Bdim.
const SIMPLE_SUFFIX = {
  7: "",
  maj7: "",
  6: "",
  add9: "",
  9: "",
  maj9: "",
  13: "",
  m7: "m",
  m6: "m",
  madd9: "m",
  m9: "m",
  m11: "m",
  mMaj7: "m",
  m7b5: "dim",
  dim7: "dim",
  "7sus4": "sus4",
  11: "sus4",
};

export function simplifyChord(chord) {
  const match = CHORD_PATTERN.exec((chord ?? "").trim());
  if (!match) return chord;
  const [, root, suffix] = match;
  return root + (SIMPLE_SUFFIX[suffix] ?? suffix);
}

// Which key is in force at `time`, given the analyser's headline key plus any
// key changes. Before the first change we use the opening key, which is the
// headline key unless the song starts in a different one.
export function keyAt(time, arrangement) {
  const changes = arrangement.key_changes ?? [];
  let current = arrangement.opening_key ?? arrangement.key;
  for (const change of changes) {
    if (time >= change.time) current = change.key;
  }
  return current;
}

export function formatTime(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// Split a chord symbol for typesetting: "Bbmaj7/F" -> B, ♭, maj7, F.
export function chordParts(chord) {
  const match = CHORD_PATTERN.exec((chord ?? "").trim());
  if (!match) return null;
  const [, root, suffix, bass] = match;
  const glyph = (name) => ({ letter: name[0], accidental: name[1] === "#" ? "♯" : name[1] === "b" ? "♭" : "" });
  return { ...glyph(root), quality: suffix, bass: bass ? glyph(bass) : null };
}

// Pitch classes sounding in a chord, root first (for the piano diagram).
const QUALITY_INTERVALS = {
  "": [0, 4, 7],
  m: [0, 3, 7],
  5: [0, 7],
  sus2: [0, 2, 7],
  sus4: [0, 5, 7],
  dim: [0, 3, 6],
  aug: [0, 4, 8],
  7: [0, 4, 7, 10],
  maj7: [0, 4, 7, 11],
  m7: [0, 3, 7, 10],
  m7b5: [0, 3, 6, 10],
  dim7: [0, 3, 6, 9],
  mMaj7: [0, 3, 7, 11],
  "7sus4": [0, 5, 7, 10],
  6: [0, 4, 7, 9],
  m6: [0, 3, 7, 9],
  add9: [0, 2, 4, 7],
  madd9: [0, 2, 3, 7],
  9: [0, 2, 4, 7, 10],
  maj9: [0, 2, 4, 7, 11],
  m9: [0, 2, 3, 7, 10],
  11: [0, 2, 5, 7, 10],
  m11: [0, 2, 3, 5, 7, 10],
  13: [0, 2, 4, 7, 9, 10],
};

export function chordPitchClasses(chord) {
  const match = CHORD_PATTERN.exec((chord ?? "").trim());
  if (!match || NOTE_INDEX[match[1]] === undefined) return null;
  const [, root, suffix, bass] = match;
  const intervals = QUALITY_INTERVALS[suffix];
  if (!intervals) return null;
  const rootPc = NOTE_INDEX[root];
  return {
    root: rootPc,
    bass: bass && NOTE_INDEX[bass] !== undefined ? NOTE_INDEX[bass] : rootPc,
    notes: intervals.map((interval) => mod12(rootPc + interval)),
  };
}

// Guitar capo: the fret that turns the most chord time into open shapes
// (C, D, E, G, A, Am, Dm, Em). Only suggested when it clearly helps.
const OPEN_SHAPES = new Set(["C", "D", "E", "G", "A", "Am", "Dm", "Em"]);

export function suggestCapo(events, keyText) {
  const time = (capo) =>
    events.reduce((sum, event) => {
      if (event.chord === "N.C.") return sum;
      const shape = simplifyChord(transposeChord(event.chord, -capo, transposeKey(keyText, -capo)));
      return sum + (OPEN_SHAPES.has(shape) ? event.end - event.start : 0);
    }, 0);
  const total = events.reduce((sum, event) => sum + (event.chord === "N.C." ? 0 : event.end - event.start), 0) || 1;
  const scores = Array.from({ length: 8 }, (_, capo) => time(capo) / total);
  let best = 0;
  for (let capo = 1; capo < 8; capo++) if (scores[capo] > scores[best] + 0.15) best = capo;
  return { capo: best, share: scores[best], openShare: scores[0] };
}
