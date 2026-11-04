// A short made-up progression for the landing-page preview (94 BPM, 4/4).
const TEMPO = 94;
const PLAN = [
  ["F", 4],
  ["C/G", 4],
  ["Gm", 2],
  ["Bb/F", 2],
  ["Gm", 2],
  ["Bb/F", 2],
  ["F", 4],
  ["C/G", 4],
  ["Dm7", 2],
  ["Bbmaj7", 2],
  ["Gm7", 2],
  ["C7", 2],
];

const beat = 60 / TEMPO;
let cursor = 0;
const timing = PLAN.map(([chord, beats], index) => {
  const event = { chord, start: cursor, end: cursor + beats * beat, confidence: index === 9 ? 0.5 : 0.95 };
  cursor += beats * beat;
  return event;
});

export const DEMO = {
  tempo: TEMPO,
  key: "F major",
  beats: Array.from({ length: Math.round(cursor / beat) }, (_, i) => i * beat),
  beats_per_bar: 4,
  first_downbeat: 0,
  timing,
};
