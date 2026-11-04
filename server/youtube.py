"""Getting a song's audio from YouTube, politely and with clear errors.

- One yt-dlp run per song (audio + details together), using yt-dlp's own
  choice of YouTube clients. They change as YouTube changes, which is why
  yt-dlp is kept up to date by `npm start`.
- Songs are kept on disk, so analysing one again never goes back to YouTube.
- When YouTube asks for proof that we're not a bot, and the person has said
  which browser they use YouTube in, the download is retried with that
  browser's YouTube sign-in (cookies). It is only used when needed: yt-dlp's
  documentation warns that heavy use of an account can get it flagged.
- Failures come back as a short code plus a plain-English message, with
  yt-dlp's own words kept as technical details.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

import librosa

from server.analysis import SR

VENDOR_DIRECTORY = Path(__file__).parent / "vendor"
CACHE_DIRECTORY = Path(__file__).resolve().parent.parent / ".cache" / "audio"
CACHE_SONGS = 40  # about 4 MB each
DOWNLOAD_TIMEOUT = 360

# Browsers whose YouTube sign-in yt-dlp can read (`--cookies-from-browser`).
BROWSER_NAMES = {
    "chrome": "Chrome",
    "safari": "Safari",
    "firefox": "Firefox",
    "brave": "Brave",
    "edge": "Edge",
    "chromium": "Chromium",
    "opera": "Opera",
    "vivaldi": "Vivaldi",
}

# Failures a YouTube sign-in can fix. After one, the next downloads go straight
# to the sign-in for a while instead of asking anonymously and failing again.
SIGN_IN_FIXES = {"bot_check", "rate_limited", "age_restricted"}
BOT_CHECK_MEMORY = 60 * 60
_sign_in_needed_until = 0.0


class DownloadFailed(Exception):
    def __init__(self, code: str, message: str, details: str = "", status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status = status


@functools.cache
def downloader_info() -> dict:
    """yt-dlp and JavaScript runtime versions, for the health check and error details."""
    version = None
    try:
        match = re.search(r"__version__\s*=\s*'([^']+)'", (VENDOR_DIRECTORY / "yt_dlp" / "version.py").read_text())
        version = match.group(1) if match else None
    except OSError:
        pass
    node = None
    if shutil.which("node"):
        try:
            node = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5).stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"ytdlp_version": version, "js_runtime": f"node {node}" if node else None}


def ytdlp_arguments(url: str, template: str, browser: str | None = None) -> list[str]:
    arguments = [
        "--no-playlist",
        "--no-progress",
        "--match-filter", "!is_live",  # a live stream would never finish downloading
        "-f", "bestaudio/best",
        "-x", "--audio-format", "wav",
        "--write-info-json",  # the song's details, from the same request
        "-o", template,
    ]
    # yt-dlp needs a JavaScript runtime for most YouTube clients. It only looks
    # for deno by default; Node (22+) is already here because the website needs it.
    if shutil.which("node"):
        arguments += ["--js-runtimes", "node"]
    if browser:
        arguments += ["--cookies-from-browser", browser]
    return [*arguments, url]


def _run(command: list[str]) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(VENDOR_DIRECTORY), os.environ.get("PYTHONPATH")]))}
    try:
        return subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=DOWNLOAD_TIMEOUT, env=environment
        )
    except subprocess.TimeoutExpired as error:
        raise DownloadFailed("timeout", "The download took more than 6 minutes. Check your internet connection, or try a shorter video.", status=504) from error


def classify(output: str, browser: str | None = None) -> tuple[str, str, int]:
    """Turn yt-dlp's output into (code, plain-English message, HTTP status)."""
    text = output.lower()
    name = BROWSER_NAMES.get(browser or "", "your browser")

    def has(*needles: str) -> bool:
        return any(needle in text for needle in needles)

    # Problems reading the browser's sign-in come first: they are the real cause
    # of whatever YouTube said next.
    if browser == "safari" and has("operation not permitted", "could not find safari cookies database"):
        return (
            "cookies_permission",
            "macOS didn’t let AnyChords read Safari’s YouTube sign-in. Give your terminal app Full Disk Access "
            "(System Settings → Privacy & Security → Full Disk Access), restart AnyChords, then try again. Or pick another browser.",
            403,
        )
    if has("could not find") and has("cookies database"):
        return "cookies_missing", f"AnyChords couldn’t find {name} on this computer. Pick the browser you use for YouTube.", 422
    if browser and has("cannot decrypt", "find-generic-password failed", "exception running find-generic-password", "failed to decrypt cookie"):
        return (
            "cookies_locked",
            f"Your Mac didn’t share {name}’s YouTube sign-in. Try again, and when your Mac asks for your password, choose Always Allow.",
            403,
        )
    if has("not a bot"):
        if browser:
            return (
                "bot_check",
                f"YouTube still wants a sign-in. Check that you’re signed in to YouTube in {name}, then try again. "
                "Or pick another browser, or wait an hour.",
                429,
            )
        return (
            "bot_check",
            "YouTube wants proof that AnyChords isn’t a bot. This happens after many downloads from one computer. "
            "Let AnyChords use your browser’s YouTube sign-in, or wait an hour and try again.",
            429,
        )
    if has("confirm your age", "age-restricted", "age restricted", "inappropriate for some users"):
        return (
            "age_restricted",
            "This video is age-restricted, so YouTube needs a signed-in account to play it. Let AnyChords use your browser’s YouTube sign-in.",
            403,
        )
    if has("http error 429", "too many requests"):
        return (
            "rate_limited",
            "YouTube is limiting downloads from this computer. Wait a few minutes and try again, or let AnyChords use your browser’s YouTube sign-in.",
            429,
        )
    if has("private video"):
        return "private", "This video is private, so it can’t be downloaded.", 422
    if has("members-only", "members only", "join this channel"):
        return "members_only", "This video is only for the channel’s paying members.", 422
    if has("live event will begin", "premieres in", "premiere will begin", "does not pass filter (!is_live)"):
        return "live", "Live streams and premieres can’t be charted until they’ve finished. Try again once the video is fully uploaded.", 422
    if has("ffmpeg") and has("not found", "not installed"):
        return "not_installed", "ffmpeg is missing. In the terminal, run npm run setup, then npm start.", 500
    if has("requested format is not available", "no video formats found", "signature extraction failed", "nsig extraction failed",
           "challenge solving failed", "http error 403", "po token"):
        return (
            "outdated",
            "YouTube changed something and the downloader can’t keep up yet. Press Ctrl+C in the terminal and run npm start "
            "again (it updates the downloader), then try again.",
            502,
        )
    if has("video unavailable", "is not available", "has been removed", "no longer available", "copyright"):
        return "unavailable", "This video isn’t available. It may have been removed, made private, or blocked in your country.", 422
    if has(
        "unable to download webpage", "failed to resolve", "getaddrinfo", "nodename nor servname", "network is unreachable",
        "temporary failure in name resolution", "connection refused", "timed out", "unable to connect to proxy", "connection reset",
    ):
        return "network", "AnyChords couldn’t reach YouTube. Check your internet connection and try again.", 502
    return "download_failed", "The download didn’t work. The technical details say why.", 502


def _details(output: str) -> str:
    info = downloader_info()
    lines = [line.strip() for line in output.splitlines() if line.strip().startswith(("ERROR", "WARNING"))]
    versions = f"yt-dlp {info['ytdlp_version'] or 'unknown'} · JavaScript: {info['js_runtime'] or 'none found'}"
    return "\n".join([versions, *lines[-8:]]) if lines else versions + "\n" + output.strip()[-800:]


def download_audio(url: str, workdir: Path, browser: str | None = None) -> tuple[Path, dict]:
    """Download a video's audio as WAV into `workdir`; returns (path, details)."""
    if not (VENDOR_DIRECTORY / "yt_dlp").exists() or not shutil.which("ffmpeg"):
        raise DownloadFailed("not_installed", "The YouTube downloader or ffmpeg is missing. In the terminal, run npm run setup, then npm start.", status=500)
    template = str(workdir / "source.%(ext)s")
    result = _run([sys.executable, "-m", "yt_dlp", *ytdlp_arguments(url, template, browser)])
    output = f"{result.stdout}\n{result.stderr}"
    wav = workdir / "source.wav"
    if result.returncode != 0 or not wav.exists():
        if result.returncode == 0 and "does not pass filter" not in output:
            raise DownloadFailed("conversion_failed", "The video’s audio couldn’t be converted for analysis.", _details(output), 422)
        code, message, status = classify(output, browser)
        raise DownloadFailed(code, message, _details(output), status)
    try:
        info = json.loads((workdir / "source.info.json").read_text())
    except (OSError, ValueError):
        info = {}
    return wav, {key: info.get(key) for key in ("title", "uploader", "channel", "duration")}


# ---- Songs kept on disk ---------------------------------------------------------


def _cache_paths(key: str) -> tuple[Path, Path] | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", key or ""):
        return None  # only plain YouTube ids become file names
    return CACHE_DIRECTORY / f"{key}.flac", CACHE_DIRECTORY / f"{key}.json"


def _read_cached(key: str) -> tuple[np.ndarray, dict] | None:
    paths = _cache_paths(key)
    if not paths or not (paths[0].exists() and paths[1].exists()):
        return None
    try:
        y, rate = sf.read(paths[0], dtype="float32")
        details = json.loads(paths[1].read_text())
        os.utime(paths[0])  # recently used
    except (OSError, ValueError, RuntimeError):
        return None
    return (y, details) if rate == SR else None


def _write_cached(key: str, y: np.ndarray, details: dict) -> np.ndarray:
    """Store a song; returns the audio exactly as later runs will read it back."""
    paths = _cache_paths(key)
    if not paths:
        return y
    try:
        CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        sf.write(paths[0], y, SR, subtype="PCM_16")
        paths[1].write_text(json.dumps(details))
        stored, _ = sf.read(paths[0], dtype="float32")
    except (OSError, RuntimeError):
        return y  # the cache is a convenience; analyse anyway
    # Keep the most recently used songs; the one just stored always stays.
    others = sorted((path for path in CACHE_DIRECTORY.glob("*.flac") if path != paths[0]), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in others[CACHE_SONGS - 1 :]:
        old.unlink(missing_ok=True)
        old.with_suffix(".json").unlink(missing_ok=True)
    return stored


def _download_and_load(url: str, browser: str | None) -> tuple[np.ndarray, dict]:
    with tempfile.TemporaryDirectory(prefix="anychords-") as directory:
        wav, details = download_audio(url, Path(directory), browser)
        y, _ = librosa.load(str(wav), sr=SR, mono=True)
    return y, details


def fetch_audio(url: str, key: str, browser: str | None = None) -> tuple[np.ndarray, dict]:
    """A song's audio (mono, SR) and details: from disk if we have it, else YouTube."""
    global _sign_in_needed_until
    cached = _read_cached(key)
    if cached is not None:
        return cached
    use_sign_in = bool(browser) and time.monotonic() < _sign_in_needed_until
    try:
        y, details = _download_and_load(url, browser if use_sign_in else None)
    except DownloadFailed as error:
        if error.code in SIGN_IN_FIXES:
            _sign_in_needed_until = time.monotonic() + BOT_CHECK_MEMORY
        if error.code not in SIGN_IN_FIXES or not browser or use_sign_in:
            raise
        y, details = _download_and_load(url, browser)
    return _write_cached(key, y, details), details
