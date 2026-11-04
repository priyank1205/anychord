"""Local-only YouTube audio to chord-chart service for AnyChords."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import librosa

from server.analysis import SR, AnalysisError, Features, analyze_audio, analyze_features, extract_features, params_for

VENDOR_DIRECTORY = Path(__file__).parent / "vendor"
REPOSITORY = Path(__file__).resolve().parent.parent


def _code_version() -> str | None:
    """Short git commit of the code on disk (None outside a git checkout)."""
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPOSITORY, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


# The code this process is running. If `git pull` brings newer code while it
# runs, answers say so: a stale analyser silently giving old results is worse
# than a nag to restart.
RUNNING_VERSION = _code_version()


def version_info() -> dict:
    on_disk = _code_version()
    return {
        "analyzer_version": RUNNING_VERSION,
        "restart_required": bool(RUNNING_VERSION and on_disk and on_disk != RUNNING_VERSION),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    # librosa JIT-compiles its beat tracker on first use (~5 s). Pay that at
    # startup instead of on the user's first request.
    t = np.arange(6 * SR) / SR
    warmup = sum(np.sin(2 * np.pi * f * t) for f in (261.63, 329.63, 392.0)) * (1 + np.sin(2 * np.pi * 2 * t)) / 6
    try:
        analyze_audio(warmup.astype(np.float32), SR)
    except AnalysisError:
        pass
    yield


app = FastAPI(title="AnyChords local analyzer", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    youtube_url: str
    sensitivity: Literal["normal", "sensitive"] = "normal"


# Recently analysed videos: switching "Catch fast changes" on re-charts from these
# features in a second or two instead of downloading the audio again.
_FEATURE_CACHE: OrderedDict[str, tuple[Features, dict]] = OrderedDict()
_FEATURE_CACHE_SIZE = 4


def _features_for(url: str) -> tuple[Features, dict]:
    key = video_id(url)
    if key in _FEATURE_CACHE:
        _FEATURE_CACHE.move_to_end(key)
        return _FEATURE_CACHE[key]
    with tempfile.TemporaryDirectory(prefix="anychords-") as directory:
        wav_path, metadata = download_audio(url, Path(directory))
        y, _ = librosa.load(str(wav_path), sr=SR, mono=True)
    entry = (extract_features(y, SR), metadata)
    _FEATURE_CACHE[key] = entry
    while len(_FEATURE_CACHE) > _FEATURE_CACHE_SIZE:
        _FEATURE_CACHE.popitem(last=False)
    return entry


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


def ytdlp_environment() -> dict:
    existing_path = os.environ.get("PYTHONPATH", "")
    return {**os.environ, "PYTHONPATH": f"{VENDOR_DIRECTORY}{os.pathsep}{existing_path}"}


def ytdlp_command(*arguments: str) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", *arguments]


def download_audio(url: str, workdir: Path) -> tuple[Path, dict]:
    """Download a YouTube video's audio as WAV into `workdir`; returns (path, metadata)."""
    if not (VENDOR_DIRECTORY / "yt_dlp").exists() or not shutil.which("ffmpeg"):
        raise HTTPException(500, "The project-local yt-dlp package and ffmpeg must be installed on this computer.")
    environment = ytdlp_environment()
    metadata_raw = run(ytdlp_command("--no-playlist", "--skip-download", "--dump-single-json", "--extractor-args", "youtube:player_client=android", url), "Could not read video details", environment)
    metadata = json.loads(metadata_raw)
    output_template = str(workdir / "source.%(ext)s")
    run(ytdlp_command(
        "--no-playlist", "--no-progress", "-f", "bestaudio/best",
        "-x", "--audio-format", "wav", "--audio-quality", "5",
        "--extractor-args", "youtube:player_client=android",
        "-o", output_template, url,
    ), "Could not download audio", environment)
    wav_files = list(workdir.glob("*.wav"))
    if not wav_files:
        raise HTTPException(422, "The video audio could not be converted for analysis.")
    return wav_files[0], metadata


@app.get("/api/health")
def health():
    return {"status": "ok", **version_info()}


def _count_changes(result: dict) -> int:
    chords = [event["chord"] for event in result["timing"] if event["chord"] != "N.C."]
    return sum(1 for a, b in zip(chords, chords[1:]) if a != b)


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    print(f"Analyzing URL: {request.youtube_url}")
    if not video_id(request.youtube_url):
        raise HTTPException(400, "Please provide a valid YouTube video URL.")

    try:
        features, metadata = _features_for(request.youtube_url)
        result = analyze_features(features, params_for(request.sensitivity))
        # How many more chord changes "Catch fast changes" would show for this song,
        # so the page can suggest it where it matters (decoding is ~1-2 s).
        hint = 0
        if request.sensitivity == "normal":
            hint = max(0, _count_changes(analyze_features(features, params_for("sensitive"))) - _count_changes(result))
    except AnalysisError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "title": metadata.get("title") or "YouTube video",
        "artist": metadata.get("uploader") or metadata.get("channel") or "YouTube",
        "sensitivity": request.sensitivity,
        "quick_changes_hint": hint,
        **version_info(),
        **result,
    }
