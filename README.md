# AnyChords

An AI-powered web application that automatically generates playable, timeline-synced chord charts directly from YouTube videos.

## About

AnyChords bridges the gap between listening and playing. Simply paste a YouTube video link, and the local Python/FastAPI backend will extract the audio and use `librosa` to analyze the track. It automatically detects the tempo, estimates the key, and generates a precise, beat-level chord timeline. The React frontend presents a beautiful, continuous chord flow that highlights perfectly in sync with the video playback. 

## Key Features

- 🎸 **Automatic Chord Detection:** Local machine learning analysis converts YouTube audio into a playable chord chart.
- ⏱️ **Beat-Level Sync:** A continuous, flowing chord timeline that highlights the active chord exactly as the song plays.
- 🔁 **Pattern Recognition:** Automatically detects and extracts the core repeating chord progression (e.g. `Em ➔ C ➔ G ➔ D`).
- 🎹 **Transposition & Instruments:** Instantly transpose the entire chart up or down by semitones, and switch instrument contexts.
- ✏️ **Edit Mode:** Easily correct or fine-tune any chords in the auto-generated draft.

## Tech Stack

- **Frontend:** React, Vite, Vanilla CSS 
- **Backend:** Python, FastAPI, Librosa, NumPy, yt-dlp

## Roadmap

- **Instrument Enhancements**: Ukulele & Piano chord diagrams, plus an advanced Piano mode showing both left-hand chords and right-hand notes.
- **Practice Mode**: The ability to play/pause, slow down the playback, and loop sections. 
- **User Library**: Saving generated chord charts to the user's account and viewing recent history.
- **Brand & UI**: Ongoing UI cleaning, polishing the aesthetic, and building out the brand identity.
