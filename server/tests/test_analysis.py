import numpy as np
import pytest

from server.analysis import SR, AnalysisError, Params, _root_position, _simplify, _slash_bass, analyze_audio, find_core_progression
from server.benchmark.metrics import majmin_scores
from server.benchmark.synth import make_song
from server.music import mirex_key_score, parse_chord, parse_key


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


def _rich_share(result):
    """Share of chord time labelled with more than a plain major/minor triad."""
    voiced = [event for event in result["timing"] if event["chord"] != "N.C."]
    total = sum(event["end"] - event["start"] for event in voiced)
    rich = sum(event["end"] - event["start"] for event in voiced if len(parse_chord(event["chord"])[1]) != 3)
    return rich / total


def test_seventh_chords_are_named():
    # D minor jazz: Dm9 Gm7 C7 Fmaj7 ... with slash chords.
    song = make_song(401, extended=True)
    result = analyze_audio(song.audio, song.sr)
    chords = {event["chord"] for event in result["timing"]}
    assert {"Gm7", "C7", "Fmaj7"} <= chords


def test_rich_chord_accuracy():
    sevenths = []
    for seed in (401, 404, 405, 406):
        song = make_song(seed, extended=True)
        result = analyze_audio(song.audio, song.sr)
        sevenths.append(majmin_scores(song.chords, _segments(result))["sevenths"])
    assert np.mean(sevenths) > 0.75


def _one_beat_turnarounds(song):
    """(start, end, chord A, chord B) for each A B A B run of one-beat chords."""
    beat = 60 / song.tempo
    chords = song.chords
    found = []
    for i in range(len(chords) - 3):
        run = chords[i : i + 4]
        if all(abs(end - start - beat) < 0.05 for start, end, _ in run) and run[0][2] == run[2][2] and run[1][2] == run[3][2]:
            found.append((run[0][0], run[3][1], run[0][2], run[1][2]))
    return found


def test_quick_changes_are_not_merged_into_one_rich_chord():
    """A quick Gm | Bb | Gm | Bb must not be reported as one long Gm7 (the
    two triads' notes together). Seen on a real song; regression guard."""
    for seed in (813, 821):  # both merged a turnaround into one rich chord before the fix
        song = make_song(seed, fast=True)
        turnarounds = _one_beat_turnarounds(song)
        assert turnarounds
        _assert_not_merged(song, analyze_audio(song.audio, song.sr), turnarounds)


def _assert_not_merged(song, result, turnarounds):
    for start, end, first, second in turnarounds:
        a, b = parse_chord(first), parse_chord(second)
        union = {(a[0] + i) % 12 for i in a[1]} | {(b[0] + i) % 12 for i in b[1]}
        for event in result["timing"]:
            if event["end"] > start + 0.1 and event["start"] < end - 0.1 and event["chord"] != "N.C.":
                root, intervals, _ = parse_chord(event["chord"])
                assert {(root + i) % 12 for i in intervals} != union, (event, first, second)


def test_fast_chord_changes_are_found():
    changes = []
    for seed in (700, 703, 707):
        song = make_song(seed, fast=True)
        result = analyze_audio(song.audio, song.sr)
        changes.append(majmin_scores(song.chords, _segments(result))["changes"])
    assert np.mean(changes) > 0.7


def test_plain_song_stays_plain(minor_song):
    """No inventing: a song of plain triads shouldn't sprout add9s and maj7s."""
    song, result = minor_song
    reference_rich = sum(e - s for s, e, label in song.chords if label != "N" and len(parse_chord(label)[1]) != 3)
    assert reference_rich == 0
    assert _rich_share(result) < 0.1


def test_triads_only_mode(minor_song):
    song, _ = minor_song
    result = analyze_audio(song.audio, song.sr, Params(detail=False))
    assert _rich_share(result) == 0


def test_same_notes_are_named_the_usual_way():
    assert _root_position(0, "6", 9) == (9, "m7", 0)  # C6/A -> Am7
    assert _root_position(2, "m6", 9) == (11, "m7b5", 0)  # Dm6/B -> Bm7b5
    assert _root_position(0, "sus2", 7) == (7, "sus4", 0)  # Csus2/G -> Gsus4
    assert _root_position(0, "", 4) == (0, "", 4)  # C/E stays C/E


def test_slash_bass_needs_a_held_bass_note():
    held_third = np.zeros((12, 4))
    held_third[4] = 1.0  # E held in the bass under C
    held_third[0] = 0.3
    assert _slash_bass(held_third, 0, "", Params()) == 4
    walking = np.zeros((12, 4))
    walking[0, [0, 2]] = 1.0  # root-fifth walking bass stays root position
    walking[7, [1, 3]] = 1.0
    assert _slash_bass(walking, 0, "", Params()) == 0


def test_simplify():
    assert _simplify("Bbmaj7/D") == "Bb"
    assert _simplify("F#m9") == "F#m"
    assert _simplify("Bm7b5") == "Bdim"
    assert _simplify("G7sus4") == "Gsus4"
    assert _simplify("E5") == "E5"


def test_chart_keeps_the_first_pass_chord_changes():
    """The detail pass names chord types; it must not undo where the first
    pass heard the root change (it used to fuse Gm | Bb into one Gm7)."""
    from server import analysis

    song = make_song(821, fast=True)
    features = analysis.extract_features(song.audio, song.sr)
    trace: dict = {}
    analysis.analyze_features(features, analysis.Params(), trace)
    path, detail = trace["first_pass"], trace["detail"]
    root_changes = [
        t for t in range(1, len(path))
        if analysis.N_STATE not in (path[t], path[t - 1]) and path[t] // 2 != path[t - 1] // 2
    ]
    kept = [t for t in root_changes if detail[t] >= 0 and detail[t] // analysis._Q == path[t] // 2]
    assert len(kept) >= 0.85 * len(root_changes)
