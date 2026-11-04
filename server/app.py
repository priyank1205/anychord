"""Local-only YouTube audio to chord-chart service for AnyChords."""

from __future__ import annotations

import subprocess
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from server import youtube
from server.analysis import SR, AnalysisError, Features, analyze_audio, analyze_features, extract_features, params_for

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
# No cross-origin access: the page reaches this server through the website
# server's /api proxy (vite.config.js), so other sites and other apps' pages on
# this computer can't call it from a browser.


class AnalyzeRequest(BaseModel):
    youtube_url: str
    sensitivity: Literal["normal", "sensitive"] = "normal"
    # The browser whose YouTube sign-in AnyChords may use when YouTube blocks
    # a download (see server/youtube.py). None: never use a sign-in.
    browser: Literal["chrome", "safari", "firefox", "brave", "edge", "chromium", "opera", "vivaldi"] | None = None


# Recently analysed videos: switching "Catch fast changes" on re-charts from these
# features in a second or two instead of downloading the audio again.
_FEATURE_CACHE: OrderedDict[str, tuple[Features, dict]] = OrderedDict()
_FEATURE_CACHE_SIZE = 4


def _features_for(url: str, browser: str | None = None) -> tuple[Features, dict]:
    key = video_id(url)
    if key in _FEATURE_CACHE:
        _FEATURE_CACHE.move_to_end(key)
        return _FEATURE_CACHE[key]
    y, metadata = youtube.fetch_audio(url, key, browser)
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


@app.get("/api/health")
def health():
    return {"status": "ok", **version_info(), **youtube.downloader_info()}


def _count_changes(result: dict) -> int:
    chords = [event["chord"] for event in result["timing"] if event["chord"] != "N.C."]
    return sum(1 for a, b in zip(chords, chords[1:]) if a != b)


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    print(f"Analyzing URL: {request.youtube_url}")
    if not video_id(request.youtube_url):
        raise HTTPException(400, "Please provide a valid YouTube video URL.")

    try:
        features, metadata = _features_for(request.youtube_url, request.browser)
        result = analyze_features(features, params_for(request.sensitivity))
        # How many more chord changes "Catch fast changes" would show for this song,
        # so the page can suggest it where it matters (decoding is ~1-2 s).
        hint = 0
        if request.sensitivity == "normal":
            hint = max(0, _count_changes(analyze_features(features, params_for("sensitive"))) - _count_changes(result))
    except youtube.DownloadFailed as error:
        detail = {"code": error.code, "message": error.message, "details": error.details, "browser": request.browser}
        raise HTTPException(error.status, detail) from error
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
