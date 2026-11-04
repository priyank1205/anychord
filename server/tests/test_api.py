import json
from pathlib import Path

import soundfile as sf
from fastapi.testclient import TestClient

from server import app as server_app
from server.benchmark.synth import make_song


def test_analyze_endpoint_end_to_end(monkeypatch, tmp_path):
    """Exercise the HTTP contract with yt-dlp replaced by a synthetic song."""
    song = make_song(9)
    (tmp_path / "yt_dlp").mkdir()
    monkeypatch.setattr(server_app, "VENDOR_DIRECTORY", tmp_path)

    downloads = []

    def fake_run(command, message, environment=None):
        downloads.append(command)
        if "--dump-single-json" in command:
            return json.dumps({"title": "Test song", "uploader": "Tester"})
        template = command[command.index("-o") + 1]
        sf.write(str(Path(template.replace("%(ext)s", "wav"))), song.audio, song.sr)
        return ""

    monkeypatch.setattr(server_app, "run", fake_run)
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

        health = client.get("/api/health").json()
        assert health["status"] == "ok"
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
