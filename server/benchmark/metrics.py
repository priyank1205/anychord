"""MIREX-style scoring for chord timelines and keys."""

from __future__ import annotations

import numpy as np

from server.music import NO_CHORD, reduce_majmin

FRAME = 0.01  # seconds; same sampling resolution mir_eval uses


def _sample(segments: list[tuple[float, float, str]], times: np.ndarray) -> list:
    labels: list = [NO_CHORD] * len(times)
    for start, end, label in segments:
        reduced = reduce_majmin(label)
        first, last = np.searchsorted(times, [start, end])
        for index in range(first, last):
            labels[index] = reduced
    return labels


def majmin_scores(reference: list[tuple[float, float, str]], estimate: list[tuple[float, float, str]]) -> dict:
    """Weighted chord-symbol recall (majmin and root) plus segmentation quality.

    Reference frames whose chord is outside maj/min/N (sus, dim, ...) are
    excluded, exactly as the MIREX majmin metric does.
    """
    end = max(segment[1] for segment in reference)
    times = np.arange(0.0, end, FRAME)
    ref = _sample(reference, times)
    est = _sample(estimate, times)
    scored = [i for i, label in enumerate(ref) if label is not None]
    if not scored:
        return {"majmin": float("nan"), "root": float("nan"), "seg": float("nan")}
    majmin = np.mean([ref[i] == est[i] for i in scored])

    def root(label):
        return label[0] if isinstance(label, tuple) else label

    root_score = np.mean([root(ref[i]) == root(est[i]) for i in scored])
    return {"majmin": float(majmin), "root": float(root_score), "seg": segmentation_score(reference, estimate)}


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
