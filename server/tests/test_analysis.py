import numpy as np
import pytest

from server.analysis import SR, AnalysisError, analyze_audio, find_core_progression
from server.benchmark.metrics import majmin_scores
from server.benchmark.synth import make_song
from server.music import mirex_key_score, parse_key


def _segments(result):
    return [(event["start"], event["end"], event["chord"]) for event in result["timing"]]


@pytest.fixture(scope="module")
def minor_song():
    # F minor with a major V (C, C7): the chord a diatonic-only model throws away.
    song = make_song(328)
    return song, analyze_audio(song.audio, song.sr)


def test_minor_key_with_major_dominant(minor_song):
    song, result = minor_song
    assert song.key == (5, "minor")
    assert result["key"] == "F minor"
    assert "C" in {event["chord"] for event in result["timing"]}
    assert majmin_scores(song.chords, _segments(result))["majmin"] > 0.9


def test_result_shape(minor_song):
    song, result = minor_song
    timing = result["timing"]
    assert timing[0]["start"] == 0.0
    assert timing[-1]["end"] == pytest.approx(len(song.audio) / song.sr, abs=0.01)
    assert all(a["end"] == b["start"] for a, b in zip(timing, timing[1:])), "timeline must be gap-free"
    assert all(a["chord"] != b["chord"] for a, b in zip(timing, timing[1:])), "neighbouring events must differ"
    assert all(0.0 <= event["confidence"] <= 1.0 for event in timing)
    assert 0.0 < result["confidence"] <= 1.0
    assert result["meter"] == "4/4"
    assert abs(result["tempo"] - song.tempo) < 3
    assert result["key_changes"] == []
    assert "#" not in "".join(event["chord"] for event in timing)  # F minor is spelled with flats (Db, not C#)


def test_three_four_song():
    song = make_song(0)  # F# minor, 3/4
    result = analyze_audio(song.audio, song.sr)
    assert result["meter"] == "3/4"
    assert result["key"] == "F# minor"


def test_key_change_is_reported():
    song = make_song(204, modulate=True)
    result = analyze_audio(song.audio, song.sr)
    assert parse_key(result["key"]) == song.key
    assert result["opening_key"] == result["key"]
    assert len(result["key_changes"]) == 1
    assert result["key_changes"][0]["key"] != result["key"]
    assert majmin_scores(song.chords, _segments(result))["majmin"] > 0.9


def test_silence_is_rejected():
    with pytest.raises(AnalysisError):
        analyze_audio(np.zeros(10 * SR, dtype=np.float32), SR)


def test_benchmark_regression():
    """Guard rail for future tuning: a handful of held-out synthetic songs."""
    chord_scores, key_scores = [], []
    for seed in (101, 113, 126, 138, 150):
        song = make_song(seed)
        result = analyze_audio(song.audio, song.sr)
        chord_scores.append(majmin_scores(song.chords, _segments(result))["majmin"])
        key_scores.append(mirex_key_score(parse_key(result["key"]), song.key))
    assert np.mean(chord_scores) > 0.92
    assert np.mean(key_scores) >= 0.9


def test_core_progression_prefers_tonic_rotation():
    chords = ["Am", "F", "C", "G"] * 3 + ["C", "G", "Am", "F"]
    assert find_core_progression(chords, "C") in {"C ➔ G ➔ Am ➔ F", "Am ➔ F ➔ C ➔ G"}
    assert find_core_progression(["C", "C", "G"], "C") == ""
