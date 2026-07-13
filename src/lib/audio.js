import * as Tone from 'tone';
import { Chord } from '@tonaljs/tonal';

let pianoSynth = null;
let ukuleleSynth = null;
let isInitialized = false;

const initAudio = async () => {
  if (isInitialized) return;
  
  await Tone.start();

  // Piano synth: richer, more sustain, warmer
  pianoSynth = new Tone.PolySynth(Tone.Synth, {
    oscillator: {
      type: "triangle8"
    },
    envelope: {
      attack: 0.02,
      decay: 1.5,
      sustain: 0.5,
      release: 2,
    }
  }).toDestination();

  // Ukulele synth: plucky, fast attack, quick decay
  ukuleleSynth = new Tone.PolySynth(Tone.Synth, {
    oscillator: {
      type: "sine"
    },
    envelope: {
      attack: 0.005,
      decay: 0.5,
      sustain: 0.05,
      release: 0.8,
    }
  }).toDestination();

  // Add effects
  const chorus = new Tone.Chorus(4, 2.5, 0.5).start();
  const reverb = new Tone.Reverb({ decay: 2.5, preDelay: 0.1 });
  pianoSynth.chain(chorus, reverb, Tone.Destination);
  ukuleleSynth.chain(reverb, Tone.Destination);
  
  isInitialized = true;
};

export const playChordSound = async (chordName, instrument = 'Piano') => {
  if (!chordName || chordName === 'N.C.') return;

  if (!isInitialized) {
    await initAudio();
  }

  const baseChord = chordName.split('/')[0].trim();

  const chord = Chord.get(baseChord);
  if (!chord.empty && chord.notes.length > 0) {
    const isUke = instrument === 'Ukulele';
    const synthToUse = isUke ? ukuleleSynth : pianoSynth;

    const notesToPlay = chord.notes.map((note, index) => {
      let octave = 4;
      if (isUke) {
        // Ukulele voicing (close harmony, higher pitch)
        octave = 4 + Math.floor(index / 4); 
      } else {
        // Piano voicing
        octave = index === 0 ? 3 : 4;
      }
      return `${note}${octave}`;
    });

    if (!isUke && notesToPlay[0].endsWith('3')) {
       notesToPlay.push(`${chord.notes[0]}4`);
    }

    const duration = isUke ? "4n" : "2n";
    const velocity = isUke ? 0.6 : 0.4;
    
    if (isUke) {
      // Arpeggiate slightly to simulate a strum on the ukulele
      const now = Tone.now();
      notesToPlay.forEach((note, i) => {
        synthToUse.triggerAttackRelease(note, duration, now + i * 0.02, velocity);
      });
    } else {
      // Play block chord for piano
      synthToUse.triggerAttackRelease(notesToPlay, duration, Tone.now(), velocity);
    }
  }
};
