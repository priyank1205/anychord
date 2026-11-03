"""Local-only YouTube audio to chord-chart service for AnyChords."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.analysis import SR, AnalysisError, analyze_audio, analyze_file

VENDOR_DIRECTORY = Path(__file__).parent / "vendor"


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
    allow_methods=["POST"],
    allow_headers=["*"],
)


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
        try:
            result = analyze_file(str(wav_files[0]))
        except AnalysisError as error:
            raise HTTPException(422, str(error)) from error
        return {
            "title": metadata.get("title") or "YouTube video",
            "artist": metadata.get("uploader") or metadata.get("channel") or "YouTube",
            **result,
        }

