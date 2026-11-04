import json
import subprocess
from collections import OrderedDict
from pathlib import Path

import soundfile as sf
from fastapi.testclient import TestClient

from server import app as server_app
from server import youtube
from server.benchmark.synth import make_song


def _fake_youtube(monkeypatch, tmp_path, song, block_anonymous=False):
    """Replace the yt-dlp process with one that 'downloads' a synthetic song."""
    (tmp_path / "vendor" / "yt_dlp").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(youtube, "VENDOR_DIRECTORY", tmp_path / "vendor")
    monkeypatch.setattr(youtube, "CACHE_DIRECTORY", tmp_path / "cache")
    monkeypatch.setattr(youtube, "_sign_in_needed_until", 0.0)
    monkeypatch.setattr(youtube.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(server_app, "_FEATURE_CACHE", OrderedDict())
    downloads = []

    def fake_run(command):
        downloads.append(command)
        if block_anonymous and "--cookies-from-browser" not in command:
            return subprocess.CompletedProcess(command, 1, "", "ERROR: [youtube] x: Sign in to confirm you’re not a bot. Use --cookies-from-browser")
        folder = Path(command[command.index("-o") + 1]).parent
        sf.write(str(folder / "source.wav"), song.audio, song.sr)
        (folder / "source.info.json").write_text(json.dumps({"title": "Test song", "uploader": "Tester"}))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(youtube, "_run", fake_run)
    return downloads


def test_analyze_endpoint_end_to_end(monkeypatch, tmp_path):
    """Exercise the HTTP contract with yt-dlp replaced by a synthetic song."""
    song = make_song(9)
    downloads = _fake_youtube(monkeypatch, tmp_path, song)
    with TestClient(server_app.app) as client:
        response = client.post("/api/analyze", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["title"] == "Test song"
        assert body["key"] == "B minor"
        assert {"tempo", "meter", "confidence", "timing", "progression", "key_changes", "opening_key"} <= body.keys()
        assert body["sensitivity"] == "normal"
        assert isinstance(body["quick_changes_hint"], int) and body["quick_changes_hint"] >= 0
        assert body["restart_required"] is False  # same code on disk as the running server
        assert len(downloads) == 1, "one yt-dlp run per song: audio and details together"

        cached = sorted(path.name for path in (tmp_path / "cache").iterdir())
        assert cached == ["dQw4w9WgXcQ.flac", "dQw4w9WgXcQ.json"]
        server_app._FEATURE_CACHE.clear()  # as after restarting AnyChords
        again_after_restart = client.post("/api/analyze", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"})
        assert again_after_restart.status_code == 200
        assert len(downloads) == 1, "a song analysed before comes from disk, not YouTube"
        assert again_after_restart.json()["timing"] == body["timing"]

        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert "ytdlp_version" in health and "js_runtime" in health
        assert health["analyzer_version"] == body["analyzer_version"]

        calls = len(downloads)
        again = client.post("/api/analyze", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ", "sensitivity": "sensitive"})
        assert again.status_code == 200, again.text
        assert again.json()["sensitivity"] == "sensitive"
        assert len(downloads) == calls, "switching sensitivity must reuse the analysed audio"

        bad = client.post("/api/analyze", json={"youtube_url": "https://example.com/video"})
        assert bad.status_code == 400
        wrong = client.post("/api/analyze", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ", "sensitivity": "max"})
        assert wrong.status_code == 422


def test_stale_analyser_says_it_needs_a_restart(monkeypatch):
    """After `git pull` with the old server still running, answers must say so."""
    monkeypatch.setattr(server_app, "RUNNING_VERSION", "0000000")
    with TestClient(server_app.app) as client:
        assert client.get("/api/health").json()["restart_required"] is True


def test_youtube_bot_check_comes_back_as_a_fixable_error(monkeypatch, tmp_path):
    """A blocked download explains itself; naming a browser fixes it."""
    downloads = _fake_youtube(monkeypatch, tmp_path, make_song(9), block_anonymous=True)
    with TestClient(server_app.app) as client:
        blocked = client.post("/api/analyze", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"})
        assert blocked.status_code == 429
        detail = blocked.json()["detail"]
        assert detail["code"] == "bot_check"
        assert "sign-in" in detail["message"] and "--" not in detail["message"]
        assert "Sign in to confirm" in detail["details"]

        fixed = client.post("/api/analyze", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ", "browser": "chrome"})
        assert fixed.status_code == 200, fixed.text
        used = downloads[-1]
        assert used[used.index("--cookies-from-browser") + 1] == "chrome"
        assert len(downloads) == 2, "after a block, go straight to the sign-in instead of asking anonymously again"

        unknown = client.post("/api/analyze", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ", "browser": "netscape"})
        assert unknown.status_code == 422
