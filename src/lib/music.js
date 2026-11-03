// Key-aware spelling and transposition. Mirrors server/music.py so a chart
// transposed in the browser is spelled the way the analyser would spell it
// (Bb in F major, A# in B major).

export const NOTE_INDEX = {
  C: 0, "B#": 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, Fb: 4, "E#": 5, F: 5,
  "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11, Cb: 11,
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

// Transpose a chord symbol and spell it for `keyText` (the key it ends up in).
// Untransposed chords are returned untouched so manual edits stay as typed.
export function transposeChord(chord, semitones, keyText) {
  if (!semitones || !chord || chord === "N.C.") return chord;
  const names = keySignatureNames(parseKey(keyText));
  return chord.replace(/(^|\/)([A-G](?:#|b)?)/g, (match, prefix, root) => {
    const index = NOTE_INDEX[root];
    return index === undefined ? match : `${prefix}${names[mod12(index + semitones)]}`;
  });
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
