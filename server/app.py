"""Local-only YouTube audio to chord-chart service for AnyChords."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import librosa
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="AnyChords local analyzer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR_TEMPLATE = np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
MINOR_TEMPLATE = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
VENDOR_DIRECTORY = Path(__file__).parent / "vendor"


class AnalyzeRequest(BaseModel):
    youtube_url: str


def video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.hostname.removeprefix("www.").lower() if parsed.hostname else ""
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0] or None
    if host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
            return parts[1]
    return None


def run(command: list[str], message: str, environment: dict | None = None) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=360, check=True, env=environment)
        return result.stdout
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, "The audio download took too long. Try a shorter video.") from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip().splitlines()[-1] if error.stderr.strip() else "Unknown error"
        raise HTTPException(422, f"{message}: {details}") from error


def circular_correlation(chroma: np.ndarray, template: np.ndarray) -> tuple[int, float]:
    scores = [float(np.dot(chroma, np.roll(template, root))) for root in range(12)]
    index = int(np.argmax(scores))
    return index, scores[index]


def estimate_key(chroma: np.ndarray) -> str:
    global_chroma = chroma.mean(axis=1)
    if global_chroma.sum() > 0:
        global_chroma /= global_chroma.sum()
    
    maj_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    min_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    
    # Pearson correlation handles the mean subtraction
    best_key = "C major"
    best_corr = -2.0
    
    # Handle zero variance edge cases
    if np.std(global_chroma) == 0:
        return best_key

    for i in range(12):
        corr_maj = np.corrcoef(global_chroma, np.roll(maj_profile, i))[0, 1]
        if not np.isnan(corr_maj) and corr_maj > best_corr:
            best_corr = corr_maj
            best_key = f"{NOTE_NAMES[i]} major"
            
        corr_min = np.corrcoef(global_chroma, np.roll(min_profile, i))[0, 1]
        if not np.isnan(corr_min) and corr_min > best_corr:
            best_corr = corr_min
            best_key = f"{NOTE_NAMES[i]} minor"
            
    return best_key



def get_diatonic_mask(song_key: str) -> np.ndarray:
    root_name, scale_type = song_key.split(" ")
    root_idx = NOTE_NAMES.index(root_name)
    
    mask = np.full(24, -0.3)
    
    if scale_type == "major":
        diatonic = [
            (root_idx, 0),
            ((root_idx + 2) % 12, 1),
            ((root_idx + 4) % 12, 1),
            ((root_idx + 5) % 12, 0),
            ((root_idx + 7) % 12, 0),
            ((root_idx + 9) % 12, 1),
        ]
    else:
        diatonic = [
            (root_idx, 1),
            ((root_idx + 3) % 12, 0),
            ((root_idx + 5) % 12, 1),
            ((root_idx + 7) % 12, 1),
            ((root_idx + 8) % 12, 0),
            ((root_idx + 10) % 12, 0),
        ]
        
    for r, is_minor in diatonic:
        state = r * 2 + is_minor
        mask[state] = 0.0
        
    return mask

def smooth_labels_beat(emissions: np.ndarray, song_key: str) -> np.ndarray:
    state_count, window_count = emissions.shape
    scores = np.full((state_count, window_count), -np.inf)
    backpointers = np.zeros((state_count, window_count), dtype=int)
    
    diatonic_mask = get_diatonic_mask(song_key)
    scores[:, 0] = emissions[:, 0] + diatonic_mask
    
    transition_bonus = 0.1
    
    for column in range(1, window_count):
        for state in range(state_count):
            transitions = np.where(np.arange(state_count) == state, transition_bonus, 0.0)
            previous = scores[:, column - 1] + transitions
            backpointers[state, column] = int(np.argmax(previous))
            scores[state, column] = emissions[state, column] + diatonic_mask[state] + previous[backpointers[state, column]]
            
    labels = np.zeros(window_count, dtype=int)
    labels[-1] = int(np.argmax(scores[:, -1]))
    for column in range(window_count - 1, 0, -1):
        labels[column - 1] = backpointers[labels[column], column]
    return labels


def recognize_chords(wav_path: Path) -> tuple[list[dict], list[str], int, str, int, list[tuple[float, float]], str]:
    target_sr = 22050
    y, sr = librosa.load(str(wav_path), sr=target_sr)
    if len(y) == 0:
        raise HTTPException(422, "The selected video has no analysable audio.")

    hop_length = 512
    chroma = librosa.feature.chroma_cens(y=y, sr=sr, hop_length=hop_length)

    tempo_float, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    if len(beat_frames) == 0:
        raise HTTPException(status_code=400, detail="Could not detect beats in audio.")

    beats_per_bar = 8 if tempo_float[0] > 140 else 4
    tempo = int(np.clip(round(float(np.atleast_1d(tempo_float)[0])), 70, 160))
    if tempo_float[0] > 140:
        tempo = int(round(float(tempo_float[0]) / 2))

    song_key = estimate_key(chroma)

    beat_chromas = []
    for i in range(len(beat_frames) - 1):
        start = beat_frames[i]
        end = beat_frames[i+1]
        c = chroma[:, start:end].mean(axis=1)
        if c.sum() > 0: c /= c.sum()
        beat_chromas.append(c)

    if not beat_chromas:
        raise HTTPException(422, "No reliable chord information was found in this video.")

    templates = []
    for root in range(12):
        templates.extend([np.roll(MAJOR_TEMPLATE, root), np.roll(MINOR_TEMPLATE, root)])
    template_matrix = np.array(templates)

    emissions = template_matrix @ np.array(beat_chromas).T
    labels = smooth_labels_beat(emissions, song_key)

    detected: list[dict] = []
    current_chord = None
    
    for i, label in enumerate(labels):
        root = label // 2
        suffix = "" if label % 2 == 0 else "m"
        chord = f"{NOTE_NAMES[root]}{suffix}"
        
        start_frame = beat_frames[i]
        end_idx = min(i + 1, len(beat_frames) - 1)
        end_frame = beat_frames[end_idx]
        
        start_sec = float(librosa.frames_to_time(start_frame, sr=sr, hop_length=hop_length))
        end_sec = float(librosa.frames_to_time(end_frame, sr=sr, hop_length=hop_length))
        
        if chord != current_chord:
            if current_chord is not None:
                detected[-1]["end"] = start_sec
            detected.append({
                "chord": chord,
                "start": start_sec,
                "end": end_sec,
                "confidence": 0.8
            })
            current_chord = chord
        else:
            if detected:
                detected[-1]["end"] = end_sec

    song_key = estimate_key(chroma)
    overall = round(float(np.mean([item["confidence"] for item in detected])) * 100) if detected else 0

    # Determine tonic chord
    tonic_root_name = song_key.split(" ")[0]
    tonic_suffix = "m" if "minor" in song_key else ""
    tonic_chord = f"{tonic_root_name}{tonic_suffix}"
    
    sequential_chords = [d["chord"] for d in detected]
    core_progression = find_core_progression(sequential_chords, tonic_chord)

    return detected, overall, song_key, tempo, core_progression


def find_core_progression(sequential_chords: list[str], tonic_chord: str) -> str:
    if not sequential_chords:
        return ""
    
    # 1. Deduplicate consecutive identical chords
    deduped = []
    for chord in sequential_chords:
        if not deduped or deduped[-1] != chord:
            deduped.append(chord)
            
    # Try length 4, then length 3, then length 2
    pattern_len = 4
    if len(deduped) < pattern_len:
        pattern_len = len(deduped)
        if pattern_len < 2:
            return ""
            
    patterns = {}
    for i in range(len(deduped) - (pattern_len - 1)):
        pattern = tuple(deduped[i:i+pattern_len])
        if len(set(pattern)) == 1:
            continue
        patterns[pattern] = patterns.get(pattern, 0) + 1
        
    if not patterns:
        return ""
        
    max_count = max(patterns.values())
    if max_count <= 1 and pattern_len == 4:
        # Fallback to length 3
        pattern_len = 3
        patterns = {}
        for i in range(len(deduped) - (pattern_len - 1)):
            pattern = tuple(deduped[i:i+pattern_len])
            if len(set(pattern)) == 1:
                continue
            patterns[pattern] = patterns.get(pattern, 0) + 1
        if not patterns:
            return ""
        max_count = max(patterns.values())
        
    if max_count <= 1:
        return ""
        
    candidates = [pat for pat, count in patterns.items() if count == max_count]
    
    # Tie-breaker: find candidate starting with the tonic chord
    best_candidate = candidates[0]
    for pat in candidates:
        first_chord = pat[0].split(" ")[0] # Get first chord if it's a split bar
        if first_chord == tonic_chord:
            best_candidate = pat
            break
            
    return " ➔ ".join(best_candidate)





def ytdlp_environment() -> dict:
    existing_path = os.environ.get("PYTHONPATH", "")
    return {**os.environ, "PYTHONPATH": f"{VENDOR_DIRECTORY}{os.pathsep}{existing_path}"}


def ytdlp_command(*arguments: str) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", *arguments]


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    print(f"Analyzing URL: {request.youtube_url}")
    if not video_id(request.youtube_url):

        raise HTTPException(400, "Please provide a valid YouTube video URL.")
    if not (VENDOR_DIRECTORY / "yt_dlp").exists() or not shutil.which("ffmpeg"):
        raise HTTPException(500, "The project-local yt-dlp package and ffmpeg must be installed on this computer.")

    with tempfile.TemporaryDirectory(prefix="anychords-") as directory:
        workdir = Path(directory)
        environment = ytdlp_environment()
        metadata_raw = run(ytdlp_command("--no-playlist", "--skip-download", "--dump-single-json", "--extractor-args", "youtube:player_client=android", request.youtube_url), "Could not read video details", environment)
        metadata = json.loads(metadata_raw)
        output_template = str(workdir / "source.%(ext)s")
        run(ytdlp_command(
            "--no-playlist", "--no-progress", "-f", "bestaudio/best",
            "-x", "--audio-format", "wav", "--audio-quality", "5",
            "--extractor-args", "youtube:player_client=android",
            "-o", output_template, request.youtube_url,
        ), "Could not download audio", environment)
        wav_files = list(workdir.glob("*.wav"))
        if not wav_files:
            raise HTTPException(422, "The video audio could not be converted for analysis.")
        detected, confidence, key, tempo, core_progression = recognize_chords(wav_files[0])
        return {
            "title": metadata.get("title") or "YouTube video",
            "artist": metadata.get("uploader") or metadata.get("channel") or "YouTube",
            "key": key,
            "tempo": tempo,
            "meter": "4/4",
            "confidence": f"{confidence}% draft",
            "timing": detected,
            "progression": core_progression,
        }

