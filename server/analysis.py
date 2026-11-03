"""Audio -> key, meter, tempo and a beat-synchronous chord timeline.

Pipeline (each stage exists because it fixed a measurable failure; see
server/benchmark):

1. Harmonic/percussive separation. Drums smear chroma; the percussive part
   is still the best signal for beat tracking.
2. Tuning-corrected, 36-bin-per-octave CQT folded to a semitone spectrum, so
   recordings that are 30+ cents off concert pitch don't leak into the
   neighbouring pitch class.
3. Beat-synchronous median spectrum with strong log compression, so a quiet
   third (the note that decides major vs minor) still registers next to a
   loud root. (NNLS overtone removal and spectral whitening were tried and
   both scored worse on the benchmark.)
4. Separate treble and bass chroma. The bass note is the strongest single cue
   for the chord root (Am vs C, Em vs G).
5. Chord HMM over 24 major/minor triads + "no chord", decoded per beat with
   bar-position-aware change probabilities and a soft, key-dependent prior
   (minor keys get their V major; borrowed chords like bVII stay cheap).
6. Key found by a second HMM over the 24 keys, fed by the decoded chords
   (how long each chord lasts, first/last chord, V->I cadences) and the
   chroma profile. Changing key is expensive, so borrowed chords don't
   trigger it but a sustained modulation (last chorus up a step) does. Chords
   are then re-decoded under the key(s), and spelled for them (Bb, not A#).
7. Confidence comes from forward-backward posteriors, not a constant.

Measured on the synthetic benchmark (python -m server.benchmark.run), held-out
songs: chord majmin 96.5% (old analyser 77.7%), key score 0.99 (0.79).
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from server.music import MAJOR, MINOR, chord_name, format_key, key_signature_names

SR = 22050
HOP = 512
BINS_PER_SEMITONE = 3
FMIN_MIDI = 24  # C1
N_NOTES = 84  # C1..B7
NOTE_MIDI = np.arange(FMIN_MIDI, FMIN_MIDI + N_NOTES)

N_STATE = 24  # index of "no chord"; 0..23 are root*2 + (0 major | 1 minor)
N_STATES = 25
QUALITIES = ("maj", "min")


class AnalysisError(Exception):
    """Raised when the audio cannot produce a meaningful chart."""


@dataclass
class Params:
    # Emission model
    beta: float = 8.0  # sharpness of chord-template similarity
    bass_weight: float = 5.0  # log-bonus scale for the chord root in the bass
    no_chord_threshold: float = 0.15  # template correlation below this favours N
    silence_level: float = 0.1  # harmonic level (vs the loud parts) below which N takes over
    compression: float = 1000.0  # log(1 + compression * spectrum) dynamic-range squash
    # Transition model (probability of a chord change entering a beat)
    change_downbeat: float = 0.40
    change_midbar: float = 0.12
    change_offbeat: float = 0.03
    change_unknown: float = 0.12
    key_prior_strength: float = 1.0
    # Key model (evidence is in log-units per second of music)
    profile_weight: float = 4.0
    first_chord_bonus: float = 3.0
    last_chord_bonus: float = 6.0
    cadence_bonus: float = 1.5
    key_change_cost: float = 25.0


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


@dataclass
class Features:
    boundaries: np.ndarray  # beat boundary times, length n + 1
    treble: np.ndarray  # (12, n) treble chroma, each column sums to 1 (or 0 if silent)
    bass: np.ndarray  # (12, n) bass chroma, each column sums to 1 (or 0)
    loudness: np.ndarray  # (n,) relative harmonic level in [0, 1]
    tempo: float


_TREBLE_WEIGHTS = np.exp(-0.5 * ((NOTE_MIDI - 66) / 12.0) ** 2) * (NOTE_MIDI >= 48)
_BASS_WEIGHTS = np.exp(-0.5 * ((NOTE_MIDI - 40) / 6.0) ** 2) * (NOTE_MIDI <= 55)


def _fold(salience: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """(N_NOTES, n) note salience -> (12, n) chroma, columns normalised to sum 1."""
    weighted = salience * weights[:, None]
    chroma = np.zeros((12, salience.shape[1]))
    for index, midi in enumerate(NOTE_MIDI):
        chroma[midi % 12] += weighted[index]
    totals = chroma.sum(axis=0, keepdims=True)
    return np.divide(chroma, totals, out=np.zeros_like(chroma), where=totals > 1e-12)


def _beat_period(beat_times: np.ndarray) -> float:
    """Typical beat length. Beat times are quantised to 23 ms frames, so the
    plain median would snap 132 BPM to 129; averaging the near-median
    intervals recovers the in-between value while ignoring dropped beats."""
    intervals = np.diff(beat_times)
    median = float(np.median(intervals))
    typical = intervals[np.abs(intervals - median) < 0.15 * median]
    return float(typical.mean()) if typical.size else median


def _regular_beats(beat_times: np.ndarray, duration: float) -> np.ndarray:
    """Beat boundaries from 0 to `duration` with no holes.

    The tracker skips rubato intros, outros and quiet passages; those spans are
    filled with beats at the median period so their chords still get labelled.
    """
    period = _beat_period(beat_times) if len(beat_times) >= 2 else 0.5
    beat_times = [float(t) for t in beat_times if 0 <= t < duration] or [0.0]
    margin = 0.25 * period
    starts: list[float] = [0.0]

    def append(time: float) -> None:
        if time - starts[-1] < margin:
            return
        if time - starts[-1] > 1.6 * period:
            gap_start, steps = starts[-1], int(round((time - starts[-1]) / period))
            starts.extend(gap_start + step * (time - gap_start) / steps for step in range(1, steps))
        starts.append(time)

    first = beat_times[0]
    for lead in sorted(first - period * step for step in range(1, int(first / period) + 1)):
        append(lead)
    for time in beat_times:
        append(time)
    tail = starts[-1] + period
    while tail < duration - margin:
        append(tail)
        tail += period
    return np.array([*starts, duration])


def beat_spectrum(y: np.ndarray, sr: int = SR) -> tuple[np.ndarray, np.ndarray, float]:
    """Audio -> (beat boundaries, per-beat semitone spectrum (N_NOTES, n), tempo)."""
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    y = np.asarray(y, dtype=np.float32)
    duration = len(y) / SR
    if duration < 3.0 or not np.any(np.abs(y) > 1e-4):
        raise AnalysisError("The selected video has no analysable audio.")

    harmonic, percussive = librosa.effects.hpss(y)

    onset = librosa.onset.onset_strength(y=percussive, sr=SR, hop_length=HOP)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=SR, hop_length=HOP, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP)
    boundaries = _regular_beats(beat_times, duration)
    tempo_bpm = 60.0 / _beat_period(beat_times) if len(beat_times) >= 2 else float(np.atleast_1d(tempo)[0]) or 120.0

    # Tuning in semitones, applied as a fraction of a CQT bin.
    tuning = float(librosa.estimate_tuning(y=harmonic, sr=SR, bins_per_octave=12))
    cqt = np.abs(
        librosa.cqt(
            harmonic,
            sr=SR,
            hop_length=HOP,
            fmin=librosa.midi_to_hz(FMIN_MIDI),
            n_bins=N_NOTES * BINS_PER_SEMITONE,
            bins_per_octave=12 * BINS_PER_SEMITONE,
            tuning=tuning * BINS_PER_SEMITONE,
        )
    )
    # Semitone spectrum: centre bin of each triplet, widened to its neighbours
    # so vibrato and slight intonation drift aren't lost.
    padded = np.pad(cqt, ((1, 1), (0, 0)))
    centres = np.arange(N_NOTES) * BINS_PER_SEMITONE + 1
    semitone = np.maximum(padded[centres], 0.5 * (padded[centres - 1] + padded[centres + 1]))

    frames = librosa.time_to_frames(boundaries, sr=SR, hop_length=HOP)
    frames = np.clip(frames, 0, semitone.shape[1])
    segments = len(boundaries) - 1
    beat_spectra = np.zeros((N_NOTES, segments))
    last_frame = semitone.shape[1] - 1
    for index in range(segments):
        start = min(frames[index], last_frame)
        end = max(start + 1, min(frames[index + 1], last_frame + 1))
        beat_spectra[:, index] = np.median(semitone[:, start:end], axis=1)

    return boundaries, beat_spectra, tempo_bpm


def chroma_from_spectra(beat_spectra: np.ndarray, compression: float = Params.compression):
    """Beat spectra (N_NOTES, n) -> treble chroma, bass chroma, relative loudness."""
    salience = np.log1p(compression * beat_spectra / (beat_spectra.max() + 1e-12))
    level = beat_spectra.sum(axis=0)
    reference = np.percentile(level[level > 0], 90) if np.any(level > 0) else 1.0
    loudness = np.clip(level / (reference + 1e-12), 0, 1)
    return _fold(salience, _TREBLE_WEIGHTS), _fold(salience, _BASS_WEIGHTS), loudness


def extract_features(y: np.ndarray, sr: int = SR, params: Params | None = None) -> Features:
    params = params or Params()
    boundaries, beat_spectra, tempo_bpm = beat_spectrum(y, sr)
    treble, bass, loudness = chroma_from_spectra(beat_spectra, params.compression)
    return Features(
        boundaries=boundaries,
        treble=treble,
        bass=bass,
        loudness=loudness,
        tempo=tempo_bpm,
    )


# ---------------------------------------------------------------------------
# Emission model
# ---------------------------------------------------------------------------


def _chord_templates() -> np.ndarray:
    templates = np.zeros((24, 12))
    for root in range(12):
        for quality_index, third in enumerate((4, 3)):
            state = root * 2 + quality_index
            templates[state, [root, (root + third) % 12, (root + 7) % 12]] = 1.0
    centred = templates - templates.mean(axis=1, keepdims=True)
    return centred / np.linalg.norm(centred, axis=1, keepdims=True)


_TEMPLATES = _chord_templates()


def emission_logprob(features: Features, params: Params) -> np.ndarray:
    treble = features.treble - features.treble.mean(axis=0, keepdims=True)
    norms = np.linalg.norm(treble, axis=0, keepdims=True)
    treble = np.divide(treble, norms, out=np.zeros_like(treble), where=norms > 1e-12)
    correlation = _TEMPLATES @ treble  # (24, n), in [-1, 1]

    roots = np.repeat(np.arange(12), 2)
    bass_root = features.bass[roots]  # share of bass energy on each chord's root
    logp = np.zeros((N_STATES, correlation.shape[1]))
    logp[:24] = params.beta * correlation + params.bass_weight * bass_root
    silent = np.clip(1.0 - features.loudness / params.silence_level, 0, 1)
    logp[N_STATE] = params.beta * params.no_chord_threshold + params.bass_weight * (1 / 12) + 20.0 * silent
    logp[:24] -= 20.0 * silent
    logp -= logp.max(axis=0, keepdims=True)
    return logp


# ---------------------------------------------------------------------------
# Key-dependent chord prior and transition model
# ---------------------------------------------------------------------------

# (semitones above tonic, quality index) -> relative prior weight.
_MAJOR_KEY_CHORDS = {
    (0, 0): 1.0, (5, 0): 0.9, (7, 0): 0.9, (9, 1): 0.8, (2, 1): 0.6, (4, 1): 0.45,
    (10, 0): 0.35, (5, 1): 0.25, (2, 0): 0.25, (8, 0): 0.2, (4, 0): 0.2, (9, 0): 0.15,
    (3, 0): 0.15, (0, 1): 0.1, (7, 1): 0.1,
}
_MINOR_KEY_CHORDS = {
    (0, 1): 1.0, (8, 0): 0.85, (5, 1): 0.8, (10, 0): 0.8, (3, 0): 0.8, (7, 0): 0.7,
    (7, 1): 0.5, (5, 0): 0.25, (0, 0): 0.1, (1, 0): 0.1, (2, 1): 0.1,
}
_OTHER_CHORD = 0.05
_NO_CHORD_PRIOR = 0.05


def key_chord_prior(tonic: int | None, mode: str | None) -> np.ndarray:
    """Probability of each chord state given the key (uniform when key is None)."""
    if tonic is None:
        prior = np.full(N_STATES, 1.0)
        prior[N_STATE] = _NO_CHORD_PRIOR * 4
        return prior / prior.sum()
    table = _MAJOR_KEY_CHORDS if mode == MAJOR else _MINOR_KEY_CHORDS
    prior = np.full(N_STATES, _OTHER_CHORD)
    for (interval, quality), weight in table.items():
        prior[((tonic + interval) % 12) * 2 + quality] = weight
    prior[N_STATE] = _NO_CHORD_PRIOR
    return prior / prior.sum()


def _transition(change: float, prior: np.ndarray, strength: float) -> np.ndarray:
    target = prior**strength
    matrix = np.tile(target, (N_STATES, 1))
    np.fill_diagonal(matrix, 0.0)
    matrix /= matrix.sum(axis=1, keepdims=True)
    matrix *= change
    np.fill_diagonal(matrix, 1.0 - change)
    return np.log(matrix)


def _bar_positions(count: int, beats_per_bar: int | None, phase: int) -> np.ndarray:
    """0 = downbeat, 1 = mid-bar (beat 3 of 4), 2 = other beat, 3 = unknown meter."""
    if beats_per_bar is None:
        return np.full(count, 3)
    position = (np.arange(count) - phase) % beats_per_bar
    classes = np.full(count, 2)
    classes[position == 0] = 0
    if beats_per_bar == 4:
        classes[position == 2] = 1
    return classes


def _transition_set(prior: np.ndarray, params: Params) -> np.ndarray:
    changes = (params.change_downbeat, params.change_midbar, params.change_offbeat, params.change_unknown)
    return np.stack([_transition(change, prior, params.key_prior_strength) for change in changes])


def viterbi(logp: np.ndarray, log_transitions: np.ndarray, classes: np.ndarray, log_initial: np.ndarray) -> np.ndarray:
    states, count = logp.shape
    score = log_initial + logp[:, 0]
    back = np.zeros((states, count), dtype=np.int16)
    for t in range(1, count):
        candidates = score[:, None] + log_transitions[classes[t]]
        back[:, t] = np.argmax(candidates, axis=0)
        score = candidates[back[:, t], np.arange(states)] + logp[:, t]
    path = np.zeros(count, dtype=int)
    path[-1] = int(np.argmax(score))
    for t in range(count - 1, 0, -1):
        path[t - 1] = back[path[t], t]
    return path


def posteriors(logp: np.ndarray, log_transitions: np.ndarray, classes: np.ndarray, log_initial: np.ndarray) -> np.ndarray:
    """Forward-backward state posteriors, (states, n)."""
    states, count = logp.shape
    alpha = np.zeros((states, count))
    beta = np.zeros((states, count))
    alpha[:, 0] = log_initial + logp[:, 0]
    for t in range(1, count):
        alpha[:, t] = np.logaddexp.reduce(alpha[:, t - 1, None] + log_transitions[classes[t]], axis=0) + logp[:, t]
    for t in range(count - 2, -1, -1):
        beta[:, t] = np.logaddexp.reduce(log_transitions[classes[t + 1]] + (logp[:, t + 1] + beta[:, t + 1])[None, :], axis=1)
    gamma = alpha + beta
    gamma -= np.logaddexp.reduce(gamma, axis=0, keepdims=True)
    return np.exp(gamma)


# ---------------------------------------------------------------------------
# Meter, downbeat phase and key
# ---------------------------------------------------------------------------


def estimate_meter(path: np.ndarray) -> tuple[int | None, int]:
    """Infer beats per bar (3 or 4) and downbeat phase from where chords change."""
    change_beats = [t for t in range(1, len(path)) if path[t] != path[t - 1] and path[t] != N_STATE and path[t - 1] != N_STATE]
    if len(change_beats) < 6:
        return None, 0
    best: tuple[float, int, int] = (-1.0, 4, 0)
    for beats_per_bar in (4, 3):
        counts = np.bincount(np.array(change_beats) % beats_per_bar, minlength=beats_per_bar)
        phase = int(np.argmax(counts))
        concentration = counts[phase] / counts.sum()
        chance = 1.0 / beats_per_bar
        score = (concentration - chance) / (1 - chance)
        if beats_per_bar == 3:
            score -= 0.15  # 3/4 must clearly beat 4/4
        if score > best[0]:
            best = (score, beats_per_bar, phase)
    score, beats_per_bar, phase = best
    if score < 0.3:
        return None, phase
    return beats_per_bar, phase


# How much of a song's time each chord typically gets in a key (rounded from
# rock/pop corpus statistics). Unlike the decoding prior above, this is
# deliberately tonic-heavy: chord *sets* are ambiguous (E-D-A fits both
# E mixolydian and A major), so the key is decided by where the music rests.
_MAJOR_KEY_SHARE = {
    (0, 0): 0.30, (5, 0): 0.18, (7, 0): 0.16, (9, 1): 0.09, (2, 1): 0.05, (10, 0): 0.04,
    (4, 1): 0.03, (8, 0): 0.015, (2, 0): 0.015, (5, 1): 0.015, (4, 0): 0.01, (9, 0): 0.01,
    (3, 0): 0.01, (7, 1): 0.01, (0, 1): 0.005,
}
_MINOR_KEY_SHARE = {
    (0, 1): 0.30, (8, 0): 0.12, (10, 0): 0.12, (5, 1): 0.11, (3, 0): 0.10, (7, 0): 0.10,
    (7, 1): 0.05, (5, 0): 0.02, (0, 0): 0.01, (1, 0): 0.005, (2, 1): 0.005,
}
_KEY_SHARE_OTHER = 0.002

# Temperley (Kostka-Payne) pitch-class profiles, standardised.
_MAJOR_PROFILE = np.array([0.748, 0.060, 0.488, 0.082, 0.670, 0.460, 0.096, 0.715, 0.104, 0.366, 0.057, 0.400])
_MINOR_PROFILE = np.array([0.712, 0.084, 0.474, 0.618, 0.049, 0.460, 0.105, 0.747, 0.404, 0.067, 0.133, 0.330])

KEYS: list[tuple[int, str]] = [(tonic, mode) for mode in (MAJOR, MINOR) for tonic in range(12)]


def _key_tables() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    log_share = np.zeros((24, N_STATES))
    profiles = np.zeros((24, 12))
    tonic_state = np.zeros(24, dtype=int)
    dominant_state = np.zeros(24, dtype=int)
    for index, (tonic, mode) in enumerate(KEYS):
        table = _MAJOR_KEY_SHARE if mode == MAJOR else _MINOR_KEY_SHARE
        row = np.full(24, _KEY_SHARE_OTHER)
        for (interval, quality), share in table.items():
            row[((tonic + interval) % 12) * 2 + quality] = share
        log_share[index, :24] = np.log(row / row.sum())  # N carries no key evidence
        profile = np.roll(_MAJOR_PROFILE if mode == MAJOR else _MINOR_PROFILE, tonic)
        profile = profile - profile.mean()
        profiles[index] = profile / np.linalg.norm(profile)
        tonic_state[index] = tonic * 2 + (mode == MINOR)
        dominant_state[index] = ((tonic + 7) % 12) * 2  # V is major in both modes
    return log_share, profiles, tonic_state, dominant_state


_KEY_LOG_SHARE, _KEY_PROFILES, _KEY_TONIC, _KEY_DOMINANT = _key_tables()


def key_evidence(path: np.ndarray, durations: np.ndarray, features: Features, params: Params) -> np.ndarray:
    """(24 keys, n beats) evidence, in log-units per second of music."""
    evidence = _KEY_LOG_SHARE[:, path] * durations
    chroma = features.treble + 0.5 * features.bass
    evidence += params.profile_weight * (_KEY_PROFILES @ chroma) * (durations * features.loudness)
    voiced = np.flatnonzero(path != N_STATE)
    if voiced.size:
        first, last = voiced[0], voiced[-1]
        evidence[:, first] += params.first_chord_bonus * (_KEY_TONIC == path[first])
        evidence[:, last] += params.last_chord_bonus * (_KEY_TONIC == path[last])
        previous = path[voiced[:-1]]
        current = path[voiced[1:]]
        for beat, (a, b) in zip(voiced[1:], zip(previous, current)):
            if a != b:
                evidence[:, beat] += params.cadence_bonus * ((_KEY_DOMINANT == a) & (_KEY_TONIC == b))
    return evidence


def key_regions(path: np.ndarray, durations: np.ndarray, features: Features, params: Params) -> list[tuple[int, tuple[int, str]]]:
    """Viterbi over the 24 keys; changing key costs `key_change_cost`.

    Returns [(first_beat, (tonic, mode)), ...] — one entry unless the song
    really modulates (a sustained stretch that fits another key much better).
    """
    evidence = key_evidence(path, durations, features, params)
    score = evidence[:, 0].copy()
    back = np.zeros(evidence.shape, dtype=np.int8)
    for t in range(1, evidence.shape[1]):
        best = int(np.argmax(score))
        switch = score[best] - params.key_change_cost
        stay = score >= switch
        back[:, t] = np.where(stay, np.arange(24), best)
        score = np.where(stay, score, switch) + evidence[:, t]
    keys = np.zeros(evidence.shape[1], dtype=int)
    keys[-1] = int(np.argmax(score))
    for t in range(evidence.shape[1] - 1, 0, -1):
        keys[t - 1] = back[keys[t], t]
    regions = [(0, KEYS[keys[0]])]
    for t in range(1, len(keys)):
        if keys[t] != keys[t - 1]:
            regions.append((t, KEYS[keys[t]]))
    return regions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _decode(logp, regions, beat_classes, params):
    """Viterbi under a (possibly piecewise) key prior. Returns path and model."""
    count = logp.shape[1]
    transition_sets = [_transition_set(key_chord_prior(*key), params) for _, key in regions]
    transitions = np.concatenate(transition_sets)
    classes = beat_classes.copy()
    for index, (first_beat, _) in enumerate(regions):
        classes[first_beat:] = beat_classes[first_beat:] + 4 * index
    log_initial = np.log(key_chord_prior(*regions[0][1]))
    model = (transitions, classes, log_initial)
    return viterbi(logp, *model), model


def analyze_audio(y: np.ndarray, sr: int = SR, params: Params | None = None) -> dict:
    params = params or Params()
    return analyze_features(extract_features(y, sr, params), params)


def analyze_features(features: Features, params: Params | None = None) -> dict:
    params = params or Params()
    logp = emission_logprob(features, params)
    durations = np.diff(features.boundaries)
    count = logp.shape[1]

    # Pass 1: key-agnostic, meter-agnostic decode.
    path, _ = _decode(logp, [(0, (None, None))], _bar_positions(count, None, 0), params)
    beats_per_bar, phase = estimate_meter(path)
    beat_classes = _bar_positions(count, beats_per_bar, phase)

    # Pass 2: infer key region(s) from those chords, decode under them, and
    # repeat until the keys are stable (usually immediately).
    regions = key_regions(path, durations, features, params)
    tried: list = []
    while regions not in tried and len(tried) < 3:
        tried.append(regions)
        path, model = _decode(logp, regions, beat_classes, params)
        regions = key_regions(path, durations, features, params)
    if regions != tried[-1]:
        path, model = _decode(logp, regions, beat_classes, params)
    posterior = posteriors(logp, *model)

    region_of_beat = np.zeros(count, dtype=int)
    for index, (first_beat, _) in enumerate(regions):
        region_of_beat[first_beat:] = index

    def label(state: int, beat: int) -> str:
        if state == N_STATE:
            return "N.C."
        names = key_signature_names(*regions[region_of_beat[beat]][1])
        return chord_name(state // 2, QUALITIES[state % 2], names)

    timing: list[dict] = []
    event_region: list[int] = []
    start = 0
    for t in range(1, count + 1):
        if t < count and path[t] == path[start] and region_of_beat[t] == region_of_beat[start]:
            continue
        state = int(path[start])
        span = posterior[:, start:t].mean(axis=1)
        runner_up = int(np.argsort(span)[-2]) if span.argmax() == state else int(span.argmax())
        event = {
            "chord": label(state, start),
            "start": round(float(features.boundaries[start]), 3),
            "end": round(float(features.boundaries[t]), 3),
            "confidence": round(float(span[state]), 3),
        }
        if span[runner_up] >= 0.15:
            event["alternative"] = label(runner_up, start)
        timing.append(event)
        event_region.append(int(region_of_beat[start]))
        start = t

    voiced_index = [index for index, event in enumerate(timing) if event["chord"] != "N.C."]
    voiced = [timing[index] for index in voiced_index]
    if not voiced:
        raise AnalysisError("No reliable chord information was found in this video.")
    voiced_time = sum(event["end"] - event["start"] for event in voiced)
    confidence = sum(event["confidence"] * (event["end"] - event["start"]) for event in voiced) / voiced_time

    # The headline key is the one the song spends the most time in.
    region_bounds = [first for first, _ in regions] + [count]
    time_in_key: dict[tuple[int, str], float] = {}
    for index, (first, key) in enumerate(regions):
        span = features.boundaries[region_bounds[index + 1]] - features.boundaries[first]
        time_in_key[key] = time_in_key.get(key, 0.0) + float(span)
    tonic, mode = max(time_in_key, key=time_in_key.get)
    main_chords = [timing[index]["chord"] for index in voiced_index if regions[event_region[index]][1] == (tonic, mode)]
    tonic_beat = next(first for first, key in regions if key == (tonic, mode))

    tempo = features.tempo
    while tempo > 180:
        tempo /= 2
    while tempo < 60:
        tempo *= 2

    return {
        "key": format_key(tonic, mode),
        "opening_key": format_key(*regions[0][1]),
        "key_changes": [
            {"time": round(float(features.boundaries[first]), 3), "key": format_key(*key)} for first, key in regions[1:]
        ],
        "tempo": int(round(tempo)),
        "meter": f"{beats_per_bar or 4}/4",
        "confidence": round(confidence, 3),
        "timing": timing,
        "progression": find_core_progression(main_chords, label(tonic * 2 + (mode == MINOR), tonic_beat)),
    }


def analyze_file(path: str) -> dict:
    y, _ = librosa.load(path, sr=SR, mono=True)
    return analyze_audio(y, SR)


def find_core_progression(chords: list[str], tonic_chord: str) -> str:
    """Most repeated 4-chord (else 3-chord) cycle, rotated to start on the tonic when possible."""
    deduped = [chord for index, chord in enumerate(chords) if index == 0 or chords[index - 1] != chord]
    for length in (4, 3):
        if len(deduped) < length * 2:
            continue
        counts: dict[tuple, int] = {}
        for index in range(len(deduped) - length + 1):
            window = tuple(deduped[index : index + length])
            if len(set(window)) == 1:
                continue
            counts[window] = counts.get(window, 0) + 1
        if not counts or max(counts.values()) < 2:
            continue
        best_count = max(counts.values())
        candidates = [window for window, count in counts.items() if count == best_count]
        chosen = next((window for window in candidates if window[0] == tonic_chord), candidates[0])
        return " ➔ ".join(chosen)
    return ""
