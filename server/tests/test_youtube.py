"""Downloading from YouTube: error messages, sign-in retries and the song cache."""

import json
import subprocess

import numpy as np
import pytest

from server import youtube
from server.analysis import SR

# Exactly what a user saw (note the curly apostrophe YouTube uses).
BOT_CHECK = (
    "ERROR: [youtube] OG5qs8a9slc: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the "
    "authentication. See  https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp  for how to manually pass "
    "cookies. Also see  https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies  for tips on effectively "
    "exporting YouTube cookies"
)


@pytest.mark.parametrize(
    "output, browser, code",
    [
        (BOT_CHECK, None, "bot_check"),
        (BOT_CHECK, "chrome", "bot_check"),
        ("WARNING: cannot decrypt v10 cookies: no key found\n" + BOT_CHECK, "chrome", "cookies_locked"),
        ("ERROR: could not find chrome cookies database in \"/Users/me/Library/Application Support/Google/Chrome\"", "chrome", "cookies_missing"),
        ("ERROR: [Errno 1] Operation not permitted: '/Users/me/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies'", "safari", "cookies_permission"),
        ("ERROR: could not find safari cookies database", "safari", "cookies_permission"),
        ("ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate for some users.", None, "age_restricted"),
        ("ERROR: [youtube] abc: HTTP Error 429: Too Many Requests", None, "rate_limited"),
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access to this video", None, "private"),
        ("ERROR: [youtube] abc: Join this channel to get access to members-only content like this video", None, "members_only"),
        ("ERROR: [youtube] abc: This live event will begin in 3 hours.", None, "live"),
        ("[download] Some stream does not pass filter (!is_live), skipping ..", None, "live"),
        ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader", None, "unavailable"),
        ("ERROR: [youtube] abc: Requested format is not available. Use --list-formats for a list of available formats", None, "outdated"),
        ("ERROR: unable to download video data: HTTP Error 403: Forbidden", None, "outdated"),
        (
            "ERROR: [youtube] abc: Unable to download webpage: ('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))",
            None,
            "network",
        ),
        ("ERROR: [youtube] abc: Unable to download webpage: <urlopen error [Errno 8] nodename nor servname provided>", None, "network"),
        ("ERROR: Postprocessing: ffprobe and ffmpeg not found. Please install or provide the path using --ffmpeg-location", None, "not_installed"),
        ("ERROR: something nobody has seen before (an unsigned value)", None, "download_failed"),
    ],
)
def test_errors_get_a_code_and_plain_message(output, browser, code):
    got, message, status = youtube.classify(output, browser)
    assert got == code
    assert message and "--" not in message, "messages must not tell people to type command-line flags"
    assert 400 <= status < 600


def test_messages_name_the_chosen_browser():
    assert "Chrome" in youtube.classify(BOT_CHECK, "chrome")[1]
    assert "Firefox" in youtube.classify("ERROR: could not find firefox cookies database in /x", "firefox")[1]


def test_download_uses_ytdlp_defaults_one_request_and_node(monkeypatch):
    monkeypatch.setattr(youtube.shutil, "which", lambda name: f"/usr/bin/{name}")
    arguments = youtube.ytdlp_arguments("https://youtu.be/x", "/tmp/source.%(ext)s")
    joined = " ".join(arguments)
    assert "player_client" not in joined, "let yt-dlp pick YouTube clients; the forced android one needs tokens we lack"
    assert "--write-info-json" in arguments, "details must come from the same request as the audio"
    assert arguments[arguments.index("--js-runtimes") + 1] == "node"
    assert "--cookies-from-browser" not in arguments
    signed_in = youtube.ytdlp_arguments("https://youtu.be/x", "/tmp/source.%(ext)s", "firefox")
    assert signed_in[signed_in.index("--cookies-from-browser") + 1] == "firefox"
    monkeypatch.setattr(youtube.shutil, "which", lambda name: None)
    assert "--js-runtimes" not in youtube.ytdlp_arguments("https://youtu.be/x", "/tmp/s.%(ext)s")


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    """Empty song cache, no remembered bot check, and a scripted downloader."""
    monkeypatch.setattr(youtube, "CACHE_DIRECTORY", tmp_path / "cache")
    monkeypatch.setattr(youtube, "_sign_in_needed_until", 0.0)
    script = {"fail_without_sign_in": None, "fail_always": None, "calls": []}

    def fake_download(url, browser):
        script["calls"].append(browser)
        if script["fail_always"]:
            raise youtube.DownloadFailed(script["fail_always"], "nope", status=422)
        if script["fail_without_sign_in"] and not browser:
            raise youtube.DownloadFailed(script["fail_without_sign_in"], "blocked", status=429)
        return np.sin(np.arange(SR) / 10).astype(np.float32) * 0.5, {"title": f"Song {url[-1]}"}

    monkeypatch.setattr(youtube, "_download_and_load", fake_download)
    return script


def test_songs_come_from_disk_the_second_time(fresh):
    y, details = youtube.fetch_audio("https://youtu.be/abcdefghijA", "abcdefghijA")
    again, details_again = youtube.fetch_audio("https://youtu.be/abcdefghijA", "abcdefghijA")
    assert fresh["calls"] == [None], "the second request must not touch YouTube"
    assert details_again == details == {"title": "Song A"}
    np.testing.assert_array_equal(y, again)  # first and later analyses see identical audio


def test_bot_check_without_a_browser_explains_and_remembers(fresh):
    fresh["fail_without_sign_in"] = "bot_check"
    with pytest.raises(youtube.DownloadFailed) as caught:
        youtube.fetch_audio("https://youtu.be/abcdefghijB", "abcdefghijB")
    assert caught.value.code == "bot_check"
    assert fresh["calls"] == [None]
    # The person then picks a browser: go straight to the sign-in, no second anonymous try.
    youtube.fetch_audio("https://youtu.be/abcdefghijB", "abcdefghijB", "chrome")
    assert fresh["calls"] == [None, "chrome"]


def test_sign_in_is_only_used_after_youtube_asks(fresh):
    youtube.fetch_audio("https://youtu.be/abcdefghijC", "abcdefghijC", "chrome")
    assert fresh["calls"] == [None], "with no block, download anonymously even if a browser was chosen"
    fresh["fail_without_sign_in"] = "bot_check"
    youtube.fetch_audio("https://youtu.be/abcdefghijD", "abcdefghijD", "chrome")
    assert fresh["calls"] == [None, None, "chrome"], "blocked: retry once with the sign-in"
    youtube.fetch_audio("https://youtu.be/abcdefghijE", "abcdefghijE", "chrome")
    assert fresh["calls"][-1] == "chrome" and len(fresh["calls"]) == 4, "for the next hour, use the sign-in straight away"


def test_other_failures_are_not_retried_with_a_sign_in(fresh):
    fresh["fail_always"] = "unavailable"
    with pytest.raises(youtube.DownloadFailed) as caught:
        youtube.fetch_audio("https://youtu.be/abcdefghijF", "abcdefghijF", "chrome")
    assert caught.value.code == "unavailable"
    assert fresh["calls"] == [None]


def test_cache_keeps_recent_songs_and_only_safe_names(fresh, monkeypatch):
    monkeypatch.setattr(youtube, "CACHE_SONGS", 2)
    for letter in "GHI":
        youtube.fetch_audio(f"https://youtu.be/abcdefghij{letter}", f"abcdefghij{letter}")
    kept = sorted(path.stem for path in youtube.CACHE_DIRECTORY.glob("*.flac"))
    assert len(kept) == 2 and "abcdefghijI" in kept
    assert sorted(path.stem for path in youtube.CACHE_DIRECTORY.glob("*.json")) == kept
    youtube.fetch_audio("https://youtu.be/../../evil", "../../evil")
    assert not list(youtube.CACHE_DIRECTORY.parent.glob("evil*")), "odd ids must never become file paths"


def _fake_run(stdout="", stderr="", returncode=0, write=True):
    def run(command):
        if write:
            template = command[command.index("-o") + 1]
            folder = template.rsplit("/", 1)[0]
            import soundfile as sf

            sf.write(f"{folder}/source.wav", np.zeros(SR, dtype=np.float32), SR)
            with open(f"{folder}/source.info.json", "w") as handle:
                json.dump({"title": "T", "uploader": "U", "channel": "C", "duration": 1, "formats": ["lots"]}, handle)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    return run


def test_download_audio_reads_details_from_the_same_run(monkeypatch, tmp_path):
    (tmp_path / "vendor" / "yt_dlp").mkdir(parents=True)
    monkeypatch.setattr(youtube, "VENDOR_DIRECTORY", tmp_path / "vendor")
    monkeypatch.setattr(youtube.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(youtube, "_run", _fake_run())
    wav, details = youtube.download_audio("https://youtu.be/x", tmp_path)
    assert wav.name == "source.wav"
    assert details == {"title": "T", "uploader": "U", "channel": "C", "duration": 1}

    monkeypatch.setattr(youtube, "_run", _fake_run(stderr=BOT_CHECK, returncode=1, write=False))
    with pytest.raises(youtube.DownloadFailed) as caught:
        youtube.download_audio("https://youtu.be/x", tmp_path / "empty")
    assert caught.value.code == "bot_check" and caught.value.status == 429
    assert "Sign in to confirm" in caught.value.details, "keep yt-dlp's words as technical details"

    live = _fake_run(stdout="[download] Live! does not pass filter (!is_live), skipping ..", write=False)
    monkeypatch.setattr(youtube, "_run", live)
    with pytest.raises(youtube.DownloadFailed) as caught:
        youtube.download_audio("https://youtu.be/x", tmp_path / "empty2")
    assert caught.value.code == "live"
