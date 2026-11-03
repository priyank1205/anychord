import pytest

from server.music import format_key, key_signature_names, mirex_key_score, parse_key, reduce_majmin


@pytest.mark.parametrize(
    ("tonic", "mode", "expected"),
    [(10, "major", "Bb major"), (6, "minor", "F# minor"), (3, "minor", "Eb minor"), (8, "minor", "G# minor"), (1, "major", "Db major")],
)
def test_keys_use_conventional_spelling(tonic, mode, expected):
    assert format_key(tonic, mode) == expected


def test_chords_are_spelled_for_the_key():
    assert key_signature_names(5, "major")[10] == "Bb"  # F major: Bb, not A#
    assert key_signature_names(4, "major")[8] == "G#"  # E major: G#, not Ab
    assert key_signature_names(2, "minor")[10] == "Bb"  # D minor follows F major
    assert key_signature_names(0, "major")[10] == "Bb"  # borrowed bVII in C


@pytest.mark.parametrize(
    ("text", "expected"),
    [("A minor", (9, "minor")), ("Bb major", (10, "major")), ("F#m", (6, "minor")), ("C:maj", (0, "major")), ("Eb", (3, "major"))],
)
def test_parse_key(text, expected):
    assert parse_key(text) == expected


def test_mirex_key_score():
    assert mirex_key_score((0, "major"), (0, "major")) == 1.0
    assert mirex_key_score((7, "major"), (0, "major")) == 0.5  # fifth
    assert mirex_key_score((9, "minor"), (0, "major")) == 0.3  # relative
    assert mirex_key_score((0, "minor"), (0, "major")) == 0.2  # parallel
    assert mirex_key_score((1, "major"), (0, "major")) == 0.0


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("A:min7", (9, "min")), ("G:7/3", (7, "maj")), ("Bb:maj", (10, "maj")), ("N", "N"), ("C:sus4", None),
        ("Am7", (9, "min")), ("G/B", (7, "maj")), ("F#m", (6, "min")), ("N.C.", "N"), ("Bdim", None),
    ],
)
def test_reduce_majmin(label, expected):
    assert reduce_majmin(label) == expected
