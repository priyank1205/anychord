# AnyChords

An AI-powered web application that automatically generates playable, timeline-synced chord charts directly from YouTube videos.

## About

AnyChords bridges the gap between listening and playing. Simply paste a YouTube video link, and the local Python/FastAPI backend will extract the audio and use `librosa` to analyze the track. It automatically detects the tempo and meter, finds the key (including mid-song key changes), and generates a precise, beat-level chord timeline. The React frontend lays the chords out as a lead sheet (bars and beats) that lights up in sync with the video.

## Key Features

- 🎸 **Automatic Chord Detection:** A tuned chroma + hidden-Markov-model pipeline converts YouTube audio into a playable chord chart. It is measured against a ground-truth benchmark (see [`server/README.md`](server/README.md)).
- 🎷 **Every Chord Type the Song Uses:** major, minor, 7ths (maj7, m7, dominant 7, m7b5, dim7, mMaj7), sus2/sus4/7sus4, add9, 6ths, 9/11/13, dim, aug, power chords and slash chords (D/F#). Toggle **Full** / **Simple** to show every chord or just the triad to strum, and **Steady** / **Catch fast changes** when a song flips chords faster than the chart shows. **Chords in this song** lists every chord with its shape, and a **Reset** button (or `0`) takes a transposed chart back to the original key.
- 🎼 **Key Detection:** The key comes from where the music rests (tonic, cadences, final chord), not just which notes appear. Key changes are reported, and chords are spelled for their key (Bb, not A#).
- 🎯 **Honest Confidence:** Every chord carries a confidence score. Shaky calls are underlined in the chart, and edit mode offers the analyser's second guess as a one-click fix.
- ⏱️ **A Chart That Follows the Music:** Chords sit in real bars, sized by how many beats they last, so a two-beat Gm–Bb flip looks different from a whole bar of Gm. The playing chord, beat and bar light up as the video plays; tap any chord to jump there.
- 🎧 **Practice Tools:** Now / Next with finger shapes and a beat countdown to the next change, 0.5× and 0.75× speed, loop a line, and a capo suggestion for easier open shapes. Diagrams for guitar, ukulele and piano.
- ⌨️ **Keyboard Shortcuts:** `Space` play/pause, `←` `→` previous/next chord, `L` loop, `S` simple chords, `E` edit, `−` `+` transpose, `0` original key.
- 🔁 **Pattern Recognition:** Automatically detects and extracts the core repeating chord progression (e.g. `Em ➔ C ➔ G ➔ D`).
- 🎹 **Transposition & Capo:** Transpose the whole chart by semitones, or set a capo and see the shapes to play.
- ✏️ **Edit Mode:** Fix any chord by hand, with the analyser's second guess one tap away. Copy the chart as text, bar by bar.
- 🌗 **Light and Dark:** Follows your system setting. Works on phones, with a mini player that stays on screen while you scroll the chart.

## Run It Locally (macOS or Linux)

You need [Node.js](https://nodejs.org) and Python 3.10+. On a Mac, [Homebrew](https://brew.sh) lets the setup install ffmpeg for you.

```bash
npm run setup   # once: installs everything (about a minute)
npm start       # every time: starts the analyser and the website, opens your browser
```

Paste a YouTube link and click **Get chords**. Press `Ctrl+C` in the terminal to stop.

After a `git pull`, restart with `npm start`. It stops any analyser still running from before, and the line under the chart shows which analyser version made it. If the code on disk is newer than the running analyser, the page tells you to restart.

## Tech Stack

- **Frontend:** React, Vite, Vanilla CSS 
- **Backend:** Python, FastAPI, Librosa, NumPy, yt-dlp

## Roadmap

- **Piano Mode**: Left-hand bass and right-hand voicings, beyond the single chord diagram.
- **User Library**: Saving generated chord charts and viewing recent history.
