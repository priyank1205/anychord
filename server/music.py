"""Music-theory helpers shared by the analyser, the benchmark, and the tests.

Everything here is pure Python: pitch-class spelling, chord-label parsing, and
key scoring. Pitch classes are integers 0-11 with C = 0.
"""

from __future__ import annotations

import re

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
# C major / A minor have no accidentals; borrowed chords there are
# conventionally flat (Bb, Eb, Ab) except F# (V/V of G).
NEUTRAL_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

NOTE_INDEX = {
    "C": 0, "B#": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "Fb": 4,
    "E#": 5, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
    "A#": 10, "Bb": 10, "B": 11, "Cb": 11,
}

# Major-key tonics spelled with flats in their key signature (relative minors
# follow their relative major).
_FLAT_MAJOR_TONICS = {5, 10, 3, 8, 1}  # F, Bb, Eb, Ab, Db
_SHARP_MAJOR_TONICS = {7, 2, 9, 4, 11, 6}  # G, D, A, E, B, F#

MAJOR, MINOR = "major", "minor"


def key_signature_names(tonic: int, mode: str) -> list[str]:
    """Return the 12 note names to use for chords in the given key."""
    major_tonic = tonic if mode == MAJOR else (tonic + 3) % 12
    if major_tonic in _FLAT_MAJOR_TONICS:
        return FLAT_NAMES
    if major_tonic in _SHARP_MAJOR_TONICS:
        return SHARP_NAMES
    return NEUTRAL_NAMES


def key_tonic_name(tonic: int, mode: str) -> str:
    """Conventional tonic spelling: Bb major (not A#), F# minor (not Gb), Eb minor."""
    if mode == MAJOR:
        return ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"][tonic]
    return ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"][tonic]


def format_key(tonic: int, mode: str) -> str:
    return f"{key_tonic_name(tonic, mode)} {mode}"


def parse_key(text: str) -> tuple[int, str]:
    """Parse "A minor", "Bb major", "F#m", "C:maj", "a:min"."""
    cleaned = text.strip()
    match = re.match(r"^([A-Ga-g])([#b]?)\s*[: ]?\s*(.*)$", cleaned)
    if not match:
        raise ValueError(f"Unrecognised key: {text!r}")
    root = match.group(1).upper() + match.group(2)
    rest = match.group(3).strip().lower()
    mode = MINOR if rest in {"m", "min", "minor", "aeolian"} else MAJOR
    if rest not in {"", "maj", "major", "ionian", "m", "min", "minor", "aeolian"}:
        raise ValueError(f"Unrecognised key mode: {text!r}")
    return NOTE_INDEX[root], mode


def mirex_key_score(estimated: tuple[int, str], reference: tuple[int, str]) -> float:
    """MIREX weighted key score: exact 1, fifth 0.5, relative 0.3, parallel 0.2."""
    (est_tonic, est_mode), (ref_tonic, ref_mode) = estimated, reference
    if estimated == reference:
        return 1.0
    if est_mode == ref_mode and (est_tonic - ref_tonic) % 12 in (5, 7):
        return 0.5
    if est_mode != ref_mode:
        if ref_mode == MAJOR and est_tonic == (ref_tonic + 9) % 12:
            return 0.3
        if ref_mode == MINOR and est_tonic == (ref_tonic + 3) % 12:
            return 0.3
        if est_tonic == ref_tonic:
            return 0.2
    return 0.0


# ---------------------------------------------------------------------------
# Chord labels
# ---------------------------------------------------------------------------

# Qualities that reduce to a major or minor triad under MIREX "majmin" rules.
_HARTE_MAJ = {"maj", "maj7", "7", "maj6", "6", "9", "maj9", "11", "13", "maj13", "add9"}
_HARTE_MIN = {"min", "min7", "minmaj7", "min6", "min9", "min11", "min13", "madd9"}
_POP_MAJ = {"", "maj", "M", "maj7", "M7", "7", "6", "9", "maj9", "add9", "11", "13"}
_POP_MIN = {"m", "min", "-", "m7", "min7", "-7", "m6", "m9", "mmaj7", "m(maj7)", "madd9", "m11"}

NO_CHORD = "N"


def reduce_majmin(label: str) -> tuple[int, str] | str | None:
    """Reduce a chord label to (root_pc, "maj"|"min"), "N" for no-chord, or None.

    None means the chord is outside the major/minor vocabulary (sus, dim, aug,
    power chords, "X") and is excluded from majmin scoring, as in MIREX.
    Accepts Harte syntax ("A:min7/b3") and pop syntax ("Am7", "G/B", "N.C.").
    """
    text = label.strip()
    if text in {"N", "N.C.", "NC", "—", ""}:
        return NO_CHORD
    if text == "X":
        return None
    match = re.match(r"^([A-G][#b]?)(.*)$", text)
    if not match:
        return None
    root = NOTE_INDEX[match.group(1)]
    rest = match.group(2).split("/")[0].strip()
    if rest.startswith(":"):
        quality = rest[1:].split("(")[0]
        if quality in _HARTE_MAJ:
            return root, "maj"
        if quality in _HARTE_MIN:
            return root, "min"
        return None
    if rest in _POP_MAJ:
        return root, "maj"
    if rest in _POP_MIN:
        return root, "min"
    return None


def chord_name(root: int, quality: str, names: list[str]) -> str:
    """Pop-style chord name ("Bb", "F#m") for an analyser state."""
    return names[root] + ("m" if quality == "min" else "")
