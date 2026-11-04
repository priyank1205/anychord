# Local analyser

Run `npm run dev:analyzer` in a second terminal while the Vite app is running.

The service accepts a YouTube URL from the local app, downloads audio into a temporary folder, produces an automatic chord draft, returns it to the browser, and removes the temporary folder before the request ends.

## Setup

```bash
python3 -m pip install -r server/requirements.txt
```

yt-dlp lives in `server/vendor/` (ignored by git) and ffmpeg must be on your `PATH`.

## What the analyser returns

```jsonc
{
  "key": "F minor",            // the key the song spends the most time in
  "opening_key": "F minor",
  "key_changes": [{ "time": 152.3, "key": "F# minor" }],
  "tempo": 132, "meter": "4/4",
  "confidence": 0.91,          // chance the chord you'd strum is right, 0-1, duration-weighted
  "progression": "Fm ➔ Db ➔ Ab ➔ Eb",
  "timing": [
    { "chord": "Fm7", "start": 1.97, "end": 3.79, "confidence": 0.98 },
    { "chord": "C7/E", "start": 3.79, "end": 5.61, "confidence": 0.55, "alternative": "C" }
  ]
}
```

Chord names come from this vocabulary (any root, optional `/bass`):

| Family | Types |
|---|---|
| Triads | `C` `Cm` `Cdim` `Caug` `Csus2` `Csus4` `C5` (power chord) |
| Sevenths | `C7` `Cmaj7` `Cm7` `Cm7b5` `Cdim7` `CmMaj7` `C7sus4` |
| Sixths and added notes | `C6` `Cm6` `Cadd9` `Cmadd9` |
| Extended | `C9` `Cmaj9` `Cm9` `C11` `Cm11` `C13` |
| Slash chords | `D/F#`, `C7/Bb` … (bass note when it isn't the root) |

Roots are spelled for the key (Bb in F major, A# in B major). Bass notes are spelled by interval (the 3rd of D is F#, even in a flat key). Same-note chords get their usual name: Am7, not C6/A. `N.C.` means no chord (silence, drum-only intros).

## How it works

`server/analysis.py` has the full pipeline and the reasoning for each stage. In short:

1. Separate harmonic and percussive sound. Beats come from the drums, and pitch comes from everything else.
2. Build a tuning-corrected log-frequency spectrum, so off-pitch recordings still work, and summarise it per beat.
3. Compute treble and bass chroma. The bass note settles Am vs C and Em vs G.
4. Decode the chords with a hidden Markov model over 24 major/minor chords plus "no chord". Chords change more readily on downbeats, and a soft key prior keeps borrowed chords (bVII, the major V in minor) cheap.
5. Find the key with a second model over 24 keys, using the chords, where the music comes to rest, cadences and the pitch profile. It can report a key change.
6. Name each chord in full with a second chord pass over 12 roots × 24 chord types, guided by the first. It removes overtones that would fake 7ths and 9ths, and smooths over a melody's passing notes. Richer chords have to keep earning their place, so a plain C stays C.

## Measuring accuracy

```bash
npm run benchmark                                  # 40 synthetic songs
python3 -m server.benchmark.run --seed 200 --modulate
python3 -m server.benchmark.run --seed 500 --extended   # rich chords
python3 -m server.benchmark.run --seed 700 --fast       # chords every 1-3 beats, pushed chords
python3 -m server.benchmark.run --dataset ~/my-annotated-songs
```

Synthetic songs (`server/benchmark/synth.py`) come with exact ground truth. They include detuning, drums, a loud melody with passing tones, inversions, sevenths, borrowed chords, distortion, reverb, 3/4 time and key changes. They are still cleaner than real mixes, so treat them as a regression signal and an upper bound.

Held-out synthetic results:

| Song set | Metric | Old analyser | New analyser |
|---|---|---|---|
| 60 songs | Chord accuracy (MIREX majmin, share of time correct) | 77.7% | **96.5%** |
| 60 songs | Key (MIREX weighted score) | 0.79 (42/60 exact) | **0.99 (59/60)** |
| 40 songs that change key | Chord accuracy | 50.4% | **96.6%** |
| 40 songs that change key | Key (MIREX weighted score) | 0.52 (18/40 exact) | **1.00 (40/40)** |
| All of the above | Meter (3/4 vs 4/4) | always "4/4" | **100%** |

Rich chords (`--extended`: jazz ii–V–Is, line clichés, sus/add9 pop, passing diminished chords, blues, power-chord rock, slash chords), held-out songs:

| Metric | Triads only | Full vocabulary |
|---|---|---|
| Exact chord (every note right) | 28% | **63%** |
| MIREX "sevenths" (maj/min/7/maj7/m7) | 49% | **83%** |
| Bass note (slash chords) | 75% | **87%** |
| Over-labelling on plain-triad songs (extras invented) | 0% | **3–4%** |

Fast harmonic rhythm (`--fast`: chords every 1–3 beats, line-end turnarounds like `C | Gm Bb Gm Bb | F`, chords pushed half a beat early), held-out songs:

| Metric | Before | Now |
|---|---|---|
| Chord changes found (F-measure, ±0.25 s) | 61% | **78%** |
| Root + major/minor | 79% | **87%** |
| Turnarounds reported as one blended chord (Gm + Bb → "Gm7") | 15 of 91 | **3 of 91** |

Three things did it. The chart is now decoded per half-beat, so pushed chords land where they're played. A bass note arriving on a new root makes that change cheaper. And evidence is no longer averaged across neighbouring beats, which had blended Gm | Bb into Gm7.

The known weak spot is a chord that lasts one beat and shares two notes with its neighbour, flipping back and forth (Gm–Bb–Gm–Bb). It now shows as the main chord (Gm) rather than a made-up Gm7, but the flips themselves are usually missed. Even with chord changes made free, the per-beat audio evidence for the in-between chord is too weak; the previous chord is still ringing. A model trained on real recordings is the likely fix.

Chords whose notes are mostly ambiguous are the weakest. G11 is close to F/G, Bm7b5 has the same notes as Dm6, and dim7/aug chords are symmetric, so the bass note has to decide. In those cases you'll often get a playable equivalent rather than the textbook name. The analyser leans towards *under*-labelling: it shows C where a song plays Cadd9 rather than invent extras.
**Real-world accuracy** is the number that matters, and it hasn't been measured for this code yet. Published template-plus-HMM systems of this kind score roughly 70–80% majmin on real pop datasets in MIREX, so expect something in that range on dense mixes. To measure it, put songs in a folder as `name.wav` plus `name.lab`, where each line of the `.lab` file is `start end chord` (e.g. `12.40 14.95 A:min7`). Add an optional `name.key` containing e.g. `A minor`, then run the `--dataset` command above.

## When a chart looks wrong: see what the analyser hears

```bash
npm run inspect -- "https://www.youtube.com/watch?v=..." --from 0:10 --to 0:30
```

This prints one line per half-beat: the chord the chart shows, the first pass's major/minor guesses with how sure it is, the loudest notes, and the bass note. For example, it shows whether the bass really moves from G to Bb (a Gm → Bb change) or stays on G (where "Bb" over G *is* Gm7). Works with audio files too (`npm run inspect -- song.mp3 --from 10 --to 30`).

## Tests

```bash
npm run test:analyzer
```
