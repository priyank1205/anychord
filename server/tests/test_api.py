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

    def fake_run(command, message, environment=None):
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

        bad = client.post("/api/analyze", json={"youtube_url": "https://example.com/video"})
        assert bad.status_code == 400
