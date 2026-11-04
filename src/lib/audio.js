import * as Tone from "tone";
import { Chord } from "@tonaljs/tonal";

// "Hear it" previews: a plucked strum for guitar and ukulele, a soft block
// chord for piano. Built lazily, because browsers only allow audio after a tap.
let synths = null;

async function setup() {
  if (synths) return synths;
  await Tone.start();
  const reverb = new Tone.Reverb({ decay: 2.2, preDelay: 0.04, wet: 0.25 }).toDestination();
  const pluck = (decay) =>
    new Tone.PolySynth(Tone.Synth, {
      oscillator: { type: "triangle" },
      envelope: { attack: 0.004, decay, sustain: 0.04, release: 0.9 },
    }).connect(reverb);
  const piano = new Tone.PolySynth(Tone.Synth, {
    oscillator: { type: "triangle8" },
    envelope: { attack: 0.02, decay: 1.4, sustain: 0.35, release: 1.6 },
  }).connect(reverb);
  synths = { guitar: pluck(1.1), ukulele: pluck(0.6), piano };
  return synths;
}

// Spread the notes upward from a starting octave, each above the last.
function voice(notes, octave) {
  let last = -Infinity;
  return notes.map((note) => {
    let midi = Tone.Frequency(`${note}${octave}`).toMidi();
    while (midi <= last) midi += 12;
    last = midi;
    return Tone.Frequency(midi, "midi").toNote();
  });
}

export async function playChordSound(chordName, instrument = "guitar") {
  if (!chordName || chordName === "N.C.") return;
  const { guitar, ukulele, piano } = await setup();
  const [symbol, bass] = chordName.split("/").map((part) => part.trim());
  const chord = Chord.get(symbol);
  const notes = chord.empty ? [] : chord.notes;
  if (!notes.length) return;
  const now = Tone.now();

  if (instrument === "piano") {
    const voiced = voice(notes, 4);
    if (bass) voiced.unshift(`${bass}2`);
    else voiced.unshift(`${notes[0]}3`);
    piano.triggerAttackRelease(voiced, "2n", now, 0.35);
    return;
  }

  const isUke = instrument === "ukulele";
  const synth = isUke ? ukulele : guitar;
  const voiced = isUke ? voice(notes, 4) : [`${bass || notes[0]}2`, ...voice([notes[0], ...notes.slice(1), notes[0]], 3)];
  voiced.forEach((note, index) => synth.triggerAttackRelease(note, isUke ? "4n" : "2n", now + index * (isUke ? 0.022 : 0.03), 0.5));
}
