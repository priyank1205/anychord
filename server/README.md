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
  "confidence": 0.91,          // duration-weighted posterior probability, 0-1
  "progression": "Fm ➔ Db ➔ Ab ➔ Eb",
  "timing": [
    { "chord": "Fm", "start": 1.97, "end": 3.79, "confidence": 0.98 },
    { "chord": "C", "start": 3.79, "end": 5.61, "confidence": 0.55, "alternative": "Cm" }
  ]
}
```

Chords are spelled for their key (Bb in F major, A# in B major). `N.C.` means no chord (silence, drum-only intros).

## How it works

`server/analysis.py` has the full pipeline and the reasoning for each stage. In short:

1. Separate harmonic and percussive sound. Beats come from the drums, and pitch comes from everything else.
2. Build a tuning-corrected log-frequency spectrum, so off-pitch recordings still work, and summarise it per beat.
3. Compute treble and bass chroma. The bass note settles Am vs C and Em vs G.
4. Decode the chords with a hidden Markov model over 24 major/minor chords plus "no chord". Chords change more readily on downbeats, and a soft key prior keeps borrowed chords (bVII, the major V in minor) cheap.
5. Find the key with a second model over 24 keys, using the chords, where the music comes to rest, cadences and the pitch profile. It can report a key change.

## Measuring accuracy

```bash
npm run benchmark                                  # 40 synthetic songs
python3 -m server.benchmark.run --seed 200 --modulate
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

**Real-world accuracy** is the number that matters, and it hasn't been measured for this code yet. Published template-plus-HMM systems of this kind score roughly 70–80% majmin on real pop datasets in MIREX, so expect something in that range on dense mixes. To measure it, put songs in a folder as `name.wav` plus `name.lab`, where each line of the `.lab` file is `start end chord` (e.g. `12.40 14.95 A:min7`). Add an optional `name.key` containing e.g. `A minor`, then run the `--dataset` command above.

## Tests

```bash
npm run test:analyzer
```
