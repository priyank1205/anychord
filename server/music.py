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

NO_CHORD = "N"

# Every chord quality the analyser can name: pop suffix -> semitones above the
# root (mod 12). Order matters only for display ties.
QUALITY_INTERVALS: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "5": (0, 7),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "mMaj7": (0, 3, 7, 11),
    "7sus4": (0, 5, 7, 10),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "add9": (0, 2, 4, 7),
    "madd9": (0, 2, 3, 7),
    "9": (0, 2, 4, 7, 10),
    "maj9": (0, 2, 4, 7, 11),
    "m9": (0, 2, 3, 7, 10),
    "11": (0, 2, 5, 7, 10),  # as played: no 3rd (often written F/G for G11)
    "m11": (0, 2, 3, 5, 7, 10),
    "13": (0, 2, 4, 7, 9, 10),  # as played: no 11th
}

# Spellings people type, mapped onto the suffixes above.
_POP_ALIASES = {
    "maj": "", "M": "", "min": "m", "-": "m", "M7": "maj7", "Δ": "maj7", "Δ7": "maj7", "-7": "m7",
    "min7": "m7", "ø": "m7b5", "ø7": "m7b5", "min7b5": "m7b5", "°": "dim", "o": "dim", "°7": "dim7",
    "o7": "dim7", "+": "aug", "mmaj7": "mMaj7", "m(maj7)": "mMaj7", "minmaj7": "mMaj7", "mM7": "mMaj7",
    "add2": "add9", "sus": "sus4", "7sus": "7sus4", "maj6": "6", "min6": "m6", "min9": "m9",
    "min11": "m11", "madd2": "madd9", "m(add9)": "madd9", "(add9)": "add9", "9sus4": "11",
}

# Harte (2005) degree names -> semitones; shorthands -> degree lists.
_DEGREES = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "7": 11, "9": 14, "11": 17, "13": 21}
_HARTE_SHORTHAND = {
    "maj": "1,3,5", "min": "1,b3,5", "dim": "1,b3,b5", "aug": "1,3,#5", "maj7": "1,3,5,7",
    "min7": "1,b3,5,b7", "7": "1,3,5,b7", "dim7": "1,b3,b5,bb7", "hdim7": "1,b3,b5,b7",
    "minmaj7": "1,b3,5,7", "maj6": "1,3,5,6", "min6": "1,b3,5,6", "9": "1,3,5,b7,9",
    "maj9": "1,3,5,7,9", "min9": "1,b3,5,b7,9", "sus2": "1,2,5", "sus4": "1,4,5",
    "11": "1,3,5,b7,9,11", "min11": "1,b3,5,b7,9,11", "13": "1,3,5,b7,9,11,13",
    "maj13": "1,3,5,7,9,11,13", "min13": "1,b3,5,b7,9,11,13", "5": "1,5", "1": "1",
}


def _degree(text: str) -> int:
    text = text.strip()
    flats, sharps = text.count("b"), text.count("#")
    return (_DEGREES[text.lstrip("b#")] - flats + sharps) % 12


def parse_chord(label: str) -> tuple[int, frozenset[int], int] | str | None:
    """Parse a chord label into (root, pitch classes relative to root, bass interval).

    Returns "N" for no-chord and None for unparseable or "X" labels. Accepts
    Harte syntax ("A:min7/b3", "C:(1,5,b7,9,11)") and pop syntax ("Am7/G",
    "Bbmaj9", "F#m7b5", "E5", "N.C.").
    """
    text = label.strip()
    if text in {"N", "N.C.", "NC", "—", ""}:
        return NO_CHORD
    match = re.match(r"^([A-G][#b]?)(.*)$", text)
    if not match or text == "X":
        return None
    root = NOTE_INDEX[match.group(1)]
    rest = match.group(2).strip()
    body, _, bass_text = rest.partition("/")
    bass_text = bass_text.strip()

    if body.startswith(":"):
        quality = body.lstrip(":")
        shorthand, _, extra = quality.partition("(")
        if shorthand and shorthand not in _HARTE_SHORTHAND:
            return None
        degrees = _HARTE_SHORTHAND.get(shorthand, "1" if not extra else "").split(",") if shorthand or not extra else []
        intervals = {_degree(d) for d in degrees if d}
        for item in extra.rstrip(")").split(","):
            item = item.strip()
            if not item:
                continue
            if item.startswith("*"):
                intervals.discard(_degree(item[1:]))
            else:
                intervals.add(_degree(item))
        intervals.add(0)
        if bass_text:
            bass = _degree(bass_text) if bass_text[0] in "b#123456789" else (NOTE_INDEX[bass_text] - root) % 12
        else:
            bass = 0
        return root, frozenset(intervals), bass

    suffix = _POP_ALIASES.get(body, body)
    if suffix not in QUALITY_INTERVALS:
        return None
    bass = (NOTE_INDEX[bass_text] - root) % 12 if bass_text in NOTE_INDEX else 0
    if bass_text and bass_text not in NOTE_INDEX:
        return None
    return root, frozenset(QUALITY_INTERVALS[suffix]), bass


def reduce_majmin(label: str) -> tuple[int, str] | str | None:
    """Reduce a chord label to (root_pc, "maj"|"min"), "N" for no-chord, or None.

    A chord counts as major if it contains a major 3rd and perfect 5th (C7,
    Cmaj9, C6 ...) and minor likewise. Everything else (sus, dim, aug, power
    chords, "X") returns None and is excluded from majmin scoring, as in MIREX.
    """
    parsed = parse_chord(label)
    if parsed is None or parsed == NO_CHORD:
        return parsed
    root, intervals, _ = parsed
    if {4, 7} <= intervals and 3 not in intervals:
        return root, "maj"
    if {3, 7} <= intervals and 4 not in intervals:
        return root, "min"
    return None


_LETTERS = "CDEFGAB"
_LETTER_PC = [0, 2, 4, 5, 7, 9, 11]
# Letter steps from the root for each interval: a major 3rd above D is F#, not Gb.
_INTERVAL_STEPS = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 4, 9: 5, 10: 6, 11: 6}


def spell_above(root_name: str, interval: int) -> str | None:
    """Spell the note `interval` semitones above `root_name` by letter (D + 4 -> F#)."""
    letter = _LETTERS.index(root_name[0])
    target_letter = (letter + _INTERVAL_STEPS[interval]) % 7
    target_pc = (NOTE_INDEX[root_name] + interval) % 12
    offset = (target_pc - _LETTER_PC[target_letter] + 6) % 12 - 6
    accidental = {0: "", 1: "#", -1: "b"}.get(offset)
    return None if accidental is None else _LETTERS[target_letter] + accidental


def chord_label(root: int, quality: str, names: list[str], bass: int = 0) -> str:
    """Pop-style chord name ("Bbmaj7", "F#m7b5", "D/F#"); the root is spelled
    with `names`, the bass by its interval above the root."""
    name = names[root] + quality
    if bass:
        name += "/" + (spell_above(names[root], bass) or names[(root + bass) % 12])
    return name
