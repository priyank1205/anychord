"""MIREX-style scoring for chord timelines and keys."""

from __future__ import annotations

import numpy as np

from server.music import NO_CHORD, parse_chord, reduce_majmin

FRAME = 0.01  # seconds; same sampling resolution mir_eval uses
_SEVENTHS = {frozenset(q) for q in ((0, 4, 7), (0, 3, 7), (0, 4, 7, 10), (0, 4, 7, 11), (0, 3, 7, 10))}
_TRIADS = {frozenset((0, 4, 7)), frozenset((0, 3, 7))}


def _sample(segments: list[tuple[float, float, str]], times: np.ndarray, reduce=reduce_majmin) -> list:
    labels: list = [NO_CHORD] * len(times)
    for start, end, label in segments:
        reduced = reduce(label)
        first, last = np.searchsorted(times, [start, end])
        for index in range(first, last):
            labels[index] = reduced
    return labels


def majmin_scores(reference: list[tuple[float, float, str]], estimate: list[tuple[float, float, str]]) -> dict:
    """Weighted chord-symbol recall at several levels of detail.

    majmin    root + major/minor (MIREX); sus, dim, aug, power refs excluded
    root      root only, over the same frames as majmin
    sevenths  root + exact notes, refs limited to maj/min/7/maj7/min7 (MIREX)
    exact     root + exact pitch-class set, every reference chord
    notes     same notes and same bass, whatever the name (Am7 == C6/A): what a player hears
    bass      lowest note (slash chords), every reference chord
    overlabel share of plain-triad reference time where the estimate adds notes
    underlabel share of 4+-note reference time where the estimate is a bare triad
    seg       1 - max(over-, under-segmentation)
    changes   F-measure of chord-change times (within 0.25 s): every change shown, none invented
    """
    end = max(segment[1] for segment in reference)
    times = np.arange(0.0, end, FRAME)
    ref = _sample(reference, times)
    est = _sample(estimate, times)
    scored = [i for i, label in enumerate(ref) if label is not None]
    nan = float("nan")
    if not scored:
        return {"changes": nan, "majmin": nan, "root": nan, "sevenths": nan, "exact": nan, "notes": nan, "bass": nan, "overlabel": nan, "underlabel": nan, "seg": nan}

    def root(label):
        return label[0] if isinstance(label, tuple) else label

    ref_full = _sample(reference, times, parse_chord)
    est_full = _sample(estimate, times, parse_chord)

    def same_notes(a, b):
        if a == NO_CHORD or b == NO_CHORD:
            return a == b
        return isinstance(a, tuple) and isinstance(b, tuple) and a[0] == b[0] and a[1] == b[1]

    def sounding(label):
        if not isinstance(label, tuple):
            return label
        root, intervals, bass_interval = label
        return frozenset((root + i) % 12 for i in intervals) | {(root + bass_interval) % 12}, (root + bass_interval) % 12

    def bass(label):
        return label if not isinstance(label, tuple) else (label[0] + label[2]) % 12

    exact_frames = [i for i, label in enumerate(ref_full) if label is not None]
    seventh_frames = [i for i in exact_frames if ref_full[i] == NO_CHORD or ref_full[i][1] in _SEVENTHS]
    triad_frames = [i for i in exact_frames if ref_full[i] != NO_CHORD and ref_full[i][1] in _TRIADS]
    rich_frames = [i for i in exact_frames if ref_full[i] != NO_CHORD and len(ref_full[i][1]) >= 4]

    def mean(values):
        return float(np.mean(values)) if values else nan

    return {
        "majmin": mean([ref[i] == est[i] for i in scored]),
        "root": mean([root(ref[i]) == root(est[i]) for i in scored]),
        "sevenths": mean([same_notes(ref_full[i], est_full[i]) for i in seventh_frames]),
        "exact": mean([same_notes(ref_full[i], est_full[i]) for i in exact_frames]),
        "notes": mean([sounding(ref_full[i]) == sounding(est_full[i]) for i in exact_frames]),
        "bass": mean([bass(ref_full[i]) == bass(est_full[i]) for i in exact_frames]),
        "overlabel": mean([isinstance(est_full[i], tuple) and len(est_full[i][1]) > 3 for i in triad_frames]),
        "underlabel": mean([isinstance(est_full[i], tuple) and len(est_full[i][1]) <= 3 for i in rich_frames]),
        "seg": segmentation_score(reference, estimate),
        "changes": change_f_measure(reference, estimate),
    }


def _change_times(segments: list[tuple[float, float, str]]) -> np.ndarray:
    times, previous = [], None
    for start, _, label in segments:
        parsed = parse_chord(label)
        if previous is not None and parsed != previous:
            times.append(start)
        previous = parsed
    return np.array(times)


def change_f_measure(reference, estimate, tolerance: float = 0.25) -> float:
    """Harmonic mean of change recall (each real change has an estimated one
    nearby) and precision (each estimated change has a real one nearby)."""
    ref, est = _change_times(reference), _change_times(estimate)
    if not len(ref) or not len(est):
        return float(len(ref) == len(est))
    recall = np.mean([np.min(np.abs(est - t)) <= tolerance for t in ref])
    precision = np.mean([np.min(np.abs(ref - t)) <= tolerance for t in est])
    return float(2 * recall * precision / (recall + precision)) if recall + precision else 0.0


def _directional_hamming(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Fraction of time in `a` segments not covered by their best-matching `b` segment."""
    total = sum(end - start for start, end in a)
    missed = 0.0
    for start, end in a:
        best = max((max(0.0, min(end, b_end) - max(start, b_start)) for b_start, b_end in b), default=0.0)
        missed += (end - start) - best
    return missed / total if total else 0.0


def _boundaries(segments: list[tuple[float, float, str]]) -> list[tuple[float, float]]:
    merged: list[list] = []
    for start, end, label in segments:
        if merged and merged[-1][2] == label and abs(merged[-1][1] - start) < 1e-6:
            merged[-1][1] = end
        else:
            merged.append([start, end, label])
    return [(start, end) for start, end, _ in merged]


def segmentation_score(reference, estimate) -> float:
    """1 - max(over-, under-segmentation). 1.0 means boundaries line up exactly."""
    ref, est = _boundaries(reference), _boundaries(estimate)
    over = _directional_hamming(ref, est)  # estimate splits reference segments
    under = _directional_hamming(est, ref)  # estimate merges reference segments
    return float(1.0 - max(over, under))
