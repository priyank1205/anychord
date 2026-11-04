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
5. Chord HMM over 24 major/minor triads + "no chord", decoded per half-beat
   (so chords pushed onto the "and" land in place) with bar-position-aware
   change probabilities and a soft, key-dependent prior (minor keys get their
   V major; borrowed chords like bVII stay cheap). Evidence is weighted by
   frame length, so finer frames don't make the chart twitchier.
6. Key found by a second HMM over the 24 keys, fed by the decoded chords
   (how long each chord lasts, first/last chord, V->I cadences) and the
   chroma profile. Changing key is expensive, so borrowed chords don't
   trigger it but a sustained modulation (last chorus up a step) does. Chords
   are then re-decoded under the key(s), and spelled for them (Bb, not A#).
7. Chord detail: a second chord HMM over 12 roots x 24 chord types (sevenths,
   sus, add9, 6ths, 9/11/13, dim, aug, power chords), guided by the first
   pass. Evidence comes from a gentler-compressed spectrum with each note's
   2nd/3rd harmonics removed (otherwise E's overtone B fakes Cmaj7). Richer
   chords must earn their place on every frame. (Averaging evidence over
   neighbouring beats was tried: it blended fast changes like Gm | Bb into
   one "Gm7".) Slash chords come from
   a contrast bass chroma, and same-note spellings are named the usual way
   (Am7, not C6/A).
8. Confidence = forward-backward probability that the chord you'd strum is
   right (C vs Am), not a constant; doubts like C vs Cmaj7 become the
   "alternative" instead.

Held-out synthetic results (python -m server.benchmark.run): chord majmin
96.5% (old analyser 77.7%), key score 0.99 (0.79); on rich-chord songs, exact
chord 63% and MIREX sevenths 83% (triads-only: 28% / 49%).
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from server.music import MAJOR, MINOR, QUALITY_INTERVALS, chord_label, format_key, key_signature_names

SR = 22050
HOP = 512
BINS_PER_SEMITONE = 3
FMIN_MIDI = 24  # C1
N_NOTES = 84  # C1..B7
NOTE_MIDI = np.arange(FMIN_MIDI, FMIN_MIDI + N_NOTES)

N_STATE = 24  # index of "no chord"; 0..23 are root*2 + (0 major | 1 minor)
N_STATES = 25


class AnalysisError(Exception):
    """Raised when the audio cannot produce a meaningful chart."""


@dataclass
class Params:
    # Emission model
    beta: float = 8.0  # sharpness of chord-template similarity
    bass_weight: float = 5.0  # log-bonus scale for the chord root in the bass
    inversion_bass_weight: float = 0.0  # bass on any chord tone (root most) supports the chord
    inversion_share: float = 0.6  # how much a 3rd/5th in the bass counts, vs the root
    bass_onset_bonus: float = 2.0  # cheaper chord change when the bass moves onto the new chord's root
    no_chord_threshold: float = 0.15  # template correlation below this favours N
    silence_level: float = 0.1  # harmonic level (vs the loud parts) below which N takes over
    compression: float = 1000.0  # log(1 + compression * spectrum) dynamic-range squash
    # Transition model (probability of a chord change entering a beat)
    change_downbeat: float = 0.40
    change_midbar: float = 0.35
    change_offbeat: float = 0.25
    change_unknown: float = 0.12
    change_between_beats: float = 0.08  # chords pushed onto the "and" (half a beat early)
    subdivisions: int = 2  # frames per beat: 2 lets a chord start on the "and"
    key_prior_strength: float = 1.0
    # Key model (evidence is in log-units per second of music)
    profile_weight: float = 4.0
    first_chord_bonus: float = 3.0
    last_chord_bonus: float = 6.0
    cadence_bonus: float = 1.5
    key_change_cost: float = 25.0
    # Chord detail pass (sevenths, sus, add9, 9/11/13, dim, aug, power, slash)
    detail_compression: float = 30.0  # gentler than `compression`: overtones must not pass as 7ths/9ths
    detail_register: tuple = (58.0, 14.0)  # (centre MIDI, width) of the notes that count as harmony
    overtone_decay: float = 0.4  # strength of the 2nd harmonic removed per note (0 = off); 3rd = decay^2
    presence_slope: float = 12.0  # sigmoid steepness of "is this note sounding?"
    presence_threshold: float = 0.3  # level relative to the loudest note where that flips
    presence_floor: float = 0.03  # no single note can be more certain than this, either way
    missing_weight: float = 1.0  # cost of a chord tone that isn't sounding
    extra_weight: float = 0.5  # cost of a sounding note outside the chord (melodies wander)
    third_weight: float = 1.5  # ... except a 3rd under a sus/power chord, whose point is having none
    detail_bass_weight: float = 3.0  # how strongly the bass note decides the root
    guide_weight: float = 1.0  # trust in the first pass's root and third
    guide_floor: float = 0.05  # caps how hard the first pass can veto a chord
    tier_penalty: tuple = (0.0, 0.5, 1.0, 1.5, 2.0)  # per-beat cost of each complexity tier
    entry_penalty: tuple = (0.0, 1.0, 2.0, 3.0, 4.0)  # one-off cost of starting such a chord
    same_root_change: float = 0.5  # share of chord changes that keep the root (C -> Cmaj7)
    first_pass_change: float = 0.9  # detail pass: chance of changing chord where the first pass did
    follow_bonus: float = 0.0  # ... and extra pull towards the first pass's new root there
    same_root_at_change: float = 0.1  # ... and of keeping the root there anyway
    slash_root_level: float = 0.6  # an inversion's root must be this quiet in the bass, relative to the bass note
    detail: bool = True  # False: major/minor triads only


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


@dataclass
class Features:
    boundaries: np.ndarray  # beat boundary times, length n + 1
    treble: np.ndarray  # (12, n) treble chroma, each column sums to 1 (or 0 if silent)
    bass: np.ndarray  # (12, n) bass chroma, each column sums to 1 (or 0)
    detail: np.ndarray  # (12, n) full-range chroma with gentler compression, max-normalised per beat
    detail_bass: np.ndarray  # (12, n) bass chroma with the same contrast, max-normalised per beat
    loudness: np.ndarray  # (n,) relative harmonic level in [0, 1]
    tempo: float
    subdivisions: int = 1  # frames per beat; frame i sits on beat i // subdivisions


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


def beat_spectrum(y: np.ndarray, sr: int = SR, subdivisions: int = 1) -> tuple[np.ndarray, np.ndarray, float]:
    """Audio -> (frame boundaries, per-frame semitone spectrum (N_NOTES, n), tempo).

    Frames are beats split into `subdivisions` equal parts, so a chord pushed
    onto the "and" of a beat gets its own frame instead of smearing a beat.
    """
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
    if subdivisions > 1:
        steps = np.diff(boundaries)[:, None] * (np.arange(subdivisions) / subdivisions)[None, :]
        boundaries = np.concatenate([(boundaries[:-1, None] + steps).reshape(-1), boundaries[-1:]])
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


# Only the 2nd and 3rd harmonics (octave, octave + fifth) are removed. The 5th
# harmonic of the bass note lands exactly on a real chord third (Eb2 -> G4);
# subtracting it erased real thirds and turned Eb into "Eb5" on real songs.
_OVERTONE_OFFSETS = [12, 19]


def suppress_overtones(beat_spectra: np.ndarray, decay: float) -> np.ndarray:
    """Remove each note's 2nd and 3rd harmonics, lowest note first.

    The 3rd harmonic of a chord's third is a major 7th above the root (E -> B
    in C major) and the 3rd harmonic of its fifth is the 9th (G -> D): left in,
    they turn plain triads into "Cmaj7" and "Cadd9".
    """
    if decay <= 0:
        return beat_spectra
    remaining = beat_spectra.copy()
    for note in range(N_NOTES):
        for order, offset in enumerate(_OVERTONE_OFFSETS, start=1):
            if note + offset < N_NOTES:
                remaining[note + offset] = np.maximum(remaining[note + offset] - decay**order * remaining[note], 0)
    return remaining


def detail_chroma(
    beat_spectra: np.ndarray,
    compression: float = Params.detail_compression,
    overtone_decay: float = Params.overtone_decay,
    register: tuple = Params.detail_register,
) -> tuple[np.ndarray, np.ndarray]:
    """Full-range and bass chroma for judging extra notes (7ths, 9ths ...) and
    the bass note, with enough contrast that overtones stay below real notes.

    Each column is scaled so its loudest pitch class is 1.
    """
    beat_spectra = suppress_overtones(beat_spectra, overtone_decay)
    salience = np.log1p(compression * beat_spectra / (beat_spectra.max() + 1e-12))
    result = []
    centre, width = register
    harmony_weights = np.exp(-0.5 * ((NOTE_MIDI - centre) / width) ** 2) * (NOTE_MIDI >= 28)
    for weights in (harmony_weights, _BASS_WEIGHTS):
        chroma = _fold(salience, weights)
        peaks = chroma.max(axis=0, keepdims=True)
        result.append(np.divide(chroma, peaks, out=np.zeros_like(chroma), where=peaks > 1e-12))
    return result[0], result[1]


def extract_features(y: np.ndarray, sr: int = SR, params: Params | None = None) -> Features:
    params = params or Params()
    boundaries, beat_spectra, tempo_bpm = beat_spectrum(y, sr, params.subdivisions)
    treble, bass, loudness = chroma_from_spectra(beat_spectra, params.compression)
    detail, detail_bass = detail_chroma(beat_spectra, params.detail_compression, params.overtone_decay, params.detail_register)
    return Features(
        boundaries=boundaries,
        treble=treble,
        bass=bass,
        detail=detail,
        detail_bass=detail_bass,
        loudness=loudness,
        tempo=tempo_bpm,
        subdivisions=params.subdivisions,
    )


def frame_weights(features: Features) -> np.ndarray:
    """Each frame's length in beats. Evidence is weighted by it so splitting
    beats into halves doesn't double how loudly the audio argues against the
    "chords change rarely" prior."""
    return np.clip(np.diff(features.boundaries) * features.tempo / 60.0, 0.2, 2.0)


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
    if params.inversion_bass_weight:
        # The bass on the chord's 3rd or 5th still supports it (Bb/F is a Bb
        # chord), just less than the root does. Without this, the F under a
        # Bb/F counted for nothing and Gm | Bb/F | Gm | Bb/F read as one Gm7.
        bass = features.detail_bass
        thirds = (roots + np.tile([4, 3], 12)) % 12
        fifths = (roots + 7) % 12
        fit = np.maximum(bass[roots], params.inversion_share * np.maximum(bass[thirds], bass[fifths]))
        support = np.log(fit + 0.1)
        logp[:24] += params.inversion_bass_weight * support
        logp[N_STATE] += params.inversion_bass_weight * np.median(support, axis=0)
    silent = np.clip(1.0 - features.loudness / params.silence_level, 0, 1)
    logp[N_STATE] = params.beta * params.no_chord_threshold + params.bass_weight * (1 / 12) + 20.0 * silent
    logp[:24] -= 20.0 * silent
    logp -= logp.max(axis=0, keepdims=True)
    return logp * frame_weights(features)[None, :]


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


N_CLASSES = 5  # frame classes, each with its own chance of a chord change


def _bar_positions(count: int, beats_per_bar: int | None, phase: int, subdivisions: int = 1) -> np.ndarray:
    """0 = downbeat, 1 = mid-bar (beat 3 of 4), 2 = other beat, 3 = beat of
    unknown meter, 4 = between beats (the "and")."""
    frame = np.arange(count)
    between = frame % subdivisions != 0
    if beats_per_bar is None:
        return np.where(between, 4, 3)
    position = (frame // subdivisions - phase) % beats_per_bar
    classes = np.full(count, 2)
    classes[position == 0] = 0
    if beats_per_bar == 4:
        classes[position == 2] = 1
    classes[between] = 4
    return classes


def _transition_set(prior: np.ndarray, params: Params) -> np.ndarray:
    return np.stack([_transition(change, prior, params.key_prior_strength) for change in _change_probabilities(params)])


def _change_probabilities(params: Params) -> tuple[float, ...]:
    """Chance of a chord change entering a frame, per frame class."""
    return (params.change_downbeat, params.change_midbar, params.change_offbeat, params.change_unknown, params.change_between_beats)


def viterbi(
    logp: np.ndarray,
    log_transitions: np.ndarray,
    classes: np.ndarray,
    log_initial: np.ndarray,
    entry_bonus: np.ndarray | None = None,
) -> np.ndarray:
    """Best state path. `entry_bonus` (states, n) is added to moving *into* a
    state at frame t (not to staying in it)."""
    states, count = logp.shape
    score = log_initial + logp[:, 0]
    back = np.zeros((states, count), dtype=np.int16)
    diagonal = np.arange(states)
    for t in range(1, count):
        candidates = score[:, None] + log_transitions[classes[t]]
        if entry_bonus is not None:
            candidates = candidates + entry_bonus[None, :, t]
            candidates[diagonal, diagonal] -= entry_bonus[:, t]
        back[:, t] = np.argmax(candidates, axis=0)
        score = candidates[back[:, t], np.arange(states)] + logp[:, t]
    path = np.zeros(count, dtype=int)
    path[-1] = int(np.argmax(score))
    for t in range(count - 1, 0, -1):
        path[t - 1] = back[path[t], t]
    return path


def posteriors(
    logp: np.ndarray,
    log_transitions: np.ndarray,
    classes: np.ndarray,
    log_initial: np.ndarray,
    entry_bonus: np.ndarray | None = None,
) -> np.ndarray:
    """Forward-backward state posteriors, (states, n)."""
    states, count = logp.shape
    alpha = np.zeros((states, count))
    beta = np.zeros((states, count))
    alpha[:, 0] = log_initial + logp[:, 0]
    eye = np.eye(states, dtype=bool)

    def step(t: int) -> np.ndarray:
        matrix = log_transitions[classes[t]]
        if entry_bonus is not None:
            matrix = matrix + np.where(eye, 0.0, entry_bonus[None, :, t])
        return matrix

    for t in range(1, count):
        alpha[:, t] = np.logaddexp.reduce(alpha[:, t - 1, None] + step(t), axis=0) + logp[:, t]
    for t in range(count - 2, -1, -1):
        beta[:, t] = np.logaddexp.reduce(step(t + 1) + (logp[:, t + 1] + beta[:, t + 1])[None, :], axis=1)
    gamma = alpha + beta
    gamma -= np.logaddexp.reduce(gamma, axis=0, keepdims=True)
    return np.exp(gamma)


# ---------------------------------------------------------------------------
# Meter, downbeat phase and key
# ---------------------------------------------------------------------------


def estimate_meter(path: np.ndarray, subdivisions: int = 1) -> tuple[int | None, int]:
    """Infer beats per bar (3 or 4) and downbeat phase from where chords change.

    A change pushed onto the "and" counts towards the beat it anticipates."""
    change_beats = [
        -(-t // subdivisions)
        for t in range(1, len(path))
        if path[t] != path[t - 1] and path[t] != N_STATE and path[t - 1] != N_STATE
    ]
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
# Chord detail: the full vocabulary, guided by the major/minor pass
# ---------------------------------------------------------------------------

DETAIL_QUALITIES = list(QUALITY_INTERVALS)
_Q = len(DETAIL_QUALITIES)
# How unusual each chord type is. Every tier up must be earned by evidence on
# every beat, which keeps a passing melody note from turning C into Cadd9.
# sus2 sits above power chords: a distorted guitar's C5 throws a strong D
# overtone (3rd harmonic of G) that would otherwise read as Csus2.
_TIER = {
    "": 0, "m": 0, "7": 1, "m7": 1, "maj7": 1, "5": 2, "sus4": 2, "sus2": 3, "6": 2, "m6": 2,
    "add9": 2, "madd9": 2, "dim": 2, "9": 3, "m9": 3, "maj9": 3, "m7b5": 3, "dim7": 3,
    "7sus4": 3, "mMaj7": 3, "aug": 3, "11": 4, "m11": 4, "13": 4,
}


def _detail_tables() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    membership = np.zeros((12 * _Q, 12))
    no_third = np.zeros((12 * _Q, 12))  # thirds that would contradict a sus/power chord
    image = np.zeros((12 * _Q, 2), dtype=int)  # first-pass states that support this chord
    tier = np.zeros(12 * _Q, dtype=int)
    for root in range(12):
        for index, quality in enumerate(DETAIL_QUALITIES):
            state = root * _Q + index
            intervals = set(QUALITY_INTERVALS[quality])
            membership[state, [(root + i) % 12 for i in intervals]] = 1
            if 4 in intervals and 3 not in intervals:
                image[state] = (root * 2, root * 2)
            elif 3 in intervals and 4 not in intervals:
                image[state] = (root * 2 + 1, root * 2 + 1)
            else:  # no third (sus, power, 11): either first-pass reading of the root will do
                image[state] = (root * 2, root * 2 + 1)
                no_third[state, [(root + 3) % 12, (root + 4) % 12]] = 1
            tier[state] = _TIER[quality]
    return membership, image, tier, no_third


_DETAIL_MEMBERS, _DETAIL_IMAGE, _DETAIL_TIER, _DETAIL_NO_THIRD = _detail_tables()


def detail_emissions(features: Features, path: np.ndarray, posterior: np.ndarray, params: Params) -> np.ndarray:
    """(12 * n_qualities, n beats) log-scores for every root/quality pair."""
    detail = features.detail
    presence = 1.0 / (1.0 + np.exp(-params.presence_slope * (detail - params.presence_threshold)))
    presence = np.clip(presence, params.presence_floor, 1 - params.presence_floor)
    notes = params.missing_weight * (_DETAIL_MEMBERS @ np.log(presence))
    outside = params.extra_weight * (1 - _DETAIL_MEMBERS) + (params.third_weight - params.extra_weight) * _DETAIL_NO_THIRD
    notes += outside @ np.log(1 - presence)

    # The bass should be the root, or failing that another chord tone (an inversion).
    roots = np.repeat(np.arange(12), _Q)
    inversion = np.max(_DETAIL_MEMBERS[:, :, None] * features.detail_bass[None, :, :], axis=1)
    bass_fit = np.maximum(features.detail_bass[roots], 0.6 * inversion)
    guide = np.maximum(posterior[_DETAIL_IMAGE[:, 0]], posterior[_DETAIL_IMAGE[:, 1]])

    return frame_weights(features)[None, :] * (
        notes
        + params.detail_bass_weight * np.log(bass_fit + 0.1)
        + params.guide_weight * np.log(guide + params.guide_floor)
        - np.asarray(params.tier_penalty)[_DETAIL_TIER][:, None]
    )


def _detail_transitions(params: Params) -> np.ndarray:
    states = 12 * _Q
    same_root = np.kron(np.eye(12), np.ones((_Q, _Q))).astype(bool)
    matrices = []
    for change in _change_probabilities(params):
        # A new root costs what it costs in the first pass (one of 11 roots,
        # major or minor); richer chord types then pay their entry penalty.
        other_root = change * (1 - params.same_root_change) / (11 * 2)
        matrix = np.where(same_root, change * params.same_root_change / (_Q - 1), other_root)
        np.fill_diagonal(matrix, 1 - change)
        log_matrix = np.log(matrix) - np.asarray(params.entry_penalty)[_DETAIL_TIER][None, :]
        np.fill_diagonal(log_matrix, np.log(1 - change))
        matrices.append(log_matrix)
    # Where the first pass changes chord, the detail pass follows it: its job is
    # to name chord types (7ths, sus ...), not to re-decide where chords change.
    # Without this it fused the first pass's Gm | Bb | Gm | Bb into one "Gm7".
    change = params.first_pass_change
    matrix = np.where(same_root, change * params.same_root_at_change / (_Q - 1), change * (1 - params.same_root_at_change) / 11 / _Q)
    np.fill_diagonal(matrix, 1 - change)
    log_matrix = np.log(matrix) - np.asarray(params.entry_penalty)[_DETAIL_TIER][None, :]
    np.fill_diagonal(log_matrix, np.log(1 - change))
    matrices.append(log_matrix)
    return np.stack(matrices)


def refine_chords(features: Features, path: np.ndarray, posterior: np.ndarray, beat_classes: np.ndarray, params: Params):
    """Second pass: label every voiced beat with a root/quality pair.

    Returns (detail state per beat, -1 where the first pass found no chord) and
    the detail emissions (for confidence).
    """
    emissions = detail_emissions(features, path, posterior, params)
    entry_bonus = params.bass_onset_bonus * np.repeat(bass_onsets(features), _Q, axis=0)
    transitions = _detail_transitions(params)
    classes = beat_classes.copy()
    classes[1:][path[1:] != path[:-1]] = N_CLASSES  # first-pass chord changes
    # Where the first pass moves to a new root, steer the detail pass onto it:
    # spreading the change over all 264 chords made "stay on Gm(7)" cheaper
    # than "move to Bb" even when the first pass had clearly heard the Bb.
    for t in range(1, len(path)):
        if N_STATE not in (path[t], path[t - 1]) and path[t] // 2 != path[t - 1] // 2:
            root = path[t] // 2
            entry_bonus[root * _Q : (root + 1) * _Q, t] += params.follow_bonus
    detail = np.full(len(path), -1)
    voiced = path != N_STATE
    start = 0
    while start < len(path):
        if not voiced[start]:
            start += 1
            continue
        end = start
        while end < len(path) and voiced[end]:
            end += 1
        run = slice(start, end)
        detail[run] = viterbi(emissions[:, run], transitions, classes[run], np.zeros(12 * _Q), entry_bonus[:, run])
        start = end
    return detail, emissions


_SIMPLE_QUALITY = {
    "7": "", "maj7": "", "6": "", "add9": "", "9": "", "maj9": "", "13": "", "m7": "m", "m6": "m", "madd9": "m",
    "m9": "m", "m11": "m", "mMaj7": "m", "m7b5": "dim", "dim7": "dim", "7sus4": "sus4", "11": "sus4",
}


_FAMILY = np.array([_SIMPLE_QUALITY.get(quality, quality) for quality in DETAIL_QUALITIES])


def _simplify(chord: str) -> str:
    """Bmaj7/D# -> B, F#m9 -> F#m: the triad a beginner would play."""
    body = chord.split("/")[0]
    root = body[:2] if body[1:2] in ("#", "b") else body[:1]
    suffix = body[len(root):]
    return root + _SIMPLE_QUALITY.get(suffix, suffix)


def _root_position(root: int, quality: str, bass: int) -> tuple[int, str, int]:
    """Prefer the spelling with the bass as root when one exists: C6/A -> Am7,
    Dm6/B -> Bm7b5, Csus2/G -> Gsus4."""
    if not bass:
        return root, quality, bass
    notes = {(root + interval) % 12 for interval in QUALITY_INTERVALS[quality]}
    new_root = (root + bass) % 12
    for candidate, intervals in QUALITY_INTERVALS.items():
        if {(new_root + interval) % 12 for interval in intervals} == notes:
            return new_root, candidate, 0
    return root, quality, bass


def _slash_bass(bass: np.ndarray, root: int, quality: str, params: Params) -> int:
    """Bass interval above the root for an inversion (C/E -> 4), or 0.

    `bass` is the max-normalised bass chroma over the chord's beats. A walking
    root-fifth bass keeps the root loud, so it stays in root position.
    """
    level = bass.mean(axis=1)
    if level.max() <= 0:
        return 0
    level = level / level.max()
    lowest = int(np.argmax(level))
    interval = (lowest - root) % 12
    if interval == 0 or interval not in QUALITY_INTERVALS[quality] or level[root] > params.slash_root_level:
        return 0
    return interval


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bass_onsets(features: Features) -> np.ndarray:
    """(12, n): how much each bass note rose into each frame."""
    bass = features.detail_bass
    return np.maximum(np.diff(bass, axis=1, prepend=bass[:, :1]), 0)


def _decode(logp, regions, beat_classes, params, entry_bonus=None):
    """Viterbi under a (possibly piecewise) key prior. Returns path and model."""
    count = logp.shape[1]
    transition_sets = [_transition_set(key_chord_prior(*key), params) for _, key in regions]
    transitions = np.concatenate(transition_sets)
    classes = beat_classes.copy()
    for index, (first_beat, _) in enumerate(regions):
        classes[first_beat:] = beat_classes[first_beat:] + N_CLASSES * index
    log_initial = np.log(key_chord_prior(*regions[0][1]))
    model = (transitions, classes, log_initial, entry_bonus)
    return viterbi(logp, *model), model


def analyze_audio(y: np.ndarray, sr: int = SR, params: Params | None = None) -> dict:
    params = params or Params()
    return analyze_features(extract_features(y, sr, params), params)


def analyze_features(features: Features, params: Params | None = None, trace: dict | None = None) -> dict:
    """Features -> chart. Pass a dict as `trace` to get the intermediate
    first-pass posteriors and paths back (used by server.inspect)."""
    params = params or Params()
    logp = emission_logprob(features, params)
    durations = np.diff(features.boundaries)
    count = logp.shape[1]

    # A bass note arriving on a chord's root makes changing to that chord
    # cheaper (the upper notes still have to agree): the cue that separates a
    # quick Gm | Bb from one long Gm when the two chords share two notes.
    onsets = bass_onsets(features)
    entry_bonus = np.zeros((N_STATES, count))
    entry_bonus[:24] = params.bass_onset_bonus * np.repeat(onsets, 2, axis=0)

    # Pass 1: key-agnostic, meter-agnostic decode.
    path, _ = _decode(logp, [(0, (None, None))], _bar_positions(count, None, 0, features.subdivisions), params, entry_bonus)
    beats_per_bar, phase = estimate_meter(path, features.subdivisions)
    beat_classes = _bar_positions(count, beats_per_bar, phase, features.subdivisions)

    # Pass 2: infer key region(s) from those chords, decode under them, and
    # repeat until the keys are stable (usually immediately).
    regions = key_regions(path, durations, features, params)
    tried: list = []
    while regions not in tried and len(tried) < 3:
        tried.append(regions)
        path, model = _decode(logp, regions, beat_classes, params, entry_bonus)
        regions = key_regions(path, durations, features, params)
    if regions != tried[-1]:
        path, model = _decode(logp, regions, beat_classes, params, entry_bonus)
    posterior = posteriors(logp, *model)

    if params.detail:
        detail, detail_scores = refine_chords(features, path, posterior, beat_classes, params)
    else:  # major/minor only: map first-pass states onto the detail grid
        detail = np.where(path == N_STATE, -1, (path // 2) * _Q + path % 2)
        detail_scores = None

    if trace is not None:
        trace.update(first_pass=path, posterior=posterior, detail=detail, regions=regions)

    region_of_beat = np.zeros(count, dtype=int)
    for index, (first_beat, _) in enumerate(regions):
        region_of_beat[first_beat:] = index

    def label(state: int, beat: int, bass: int = 0) -> str:
        if state < 0:
            return "N.C."
        root, index = divmod(int(state), _Q)
        return chord_label(root, DETAIL_QUALITIES[index], key_signature_names(*regions[region_of_beat[beat]][1]), bass)

    timing: list[dict] = []
    event_region: list[int] = []
    start = 0
    for t in range(1, count + 1):
        if t < count and detail[t] == detail[start] and region_of_beat[t] == region_of_beat[start]:
            continue
        state = int(detail[start])
        first_pass = posterior[:, start:t].mean(axis=1)
        event = {"start": round(float(features.boundaries[start]), 3), "end": round(float(features.boundaries[t]), 3)}
        if state < 0:
            event.update(chord="N.C.", confidence=round(float(first_pass[N_STATE]), 3))
        else:
            root, index = divmod(state, _Q)
            image = _DETAIL_IMAGE[state]
            root_confidence = float(max(first_pass[image[0]], first_pass[image[1]]))
            if detail_scores is not None:
                same_root = detail_scores[root * _Q : (root + 1) * _Q, start:t].mean(axis=1)
                quality_probs = np.exp(same_root - same_root.max())
                quality_probs /= quality_probs.sum()
            else:
                quality_probs = np.eye(_Q)[index]
            bass = _slash_bass(features.detail_bass[:, start:t], root, DETAIL_QUALITIES[index], params)
            named_root, named_quality, bass = _root_position(root, DETAIL_QUALITIES[index], bass)
            named = named_root * _Q + DETAIL_QUALITIES.index(named_quality)
            # Confidence = is the chord you'd strum right? C vs Cmaj7 doesn't
            # lower it (that doubt shows up as the alternative); C vs Am does.
            family = _FAMILY[index]
            family_probability = float(quality_probs[_FAMILY == family].sum())
            event.update(chord=label(named, start, bass), confidence=round(root_confidence * family_probability, 3))
            # Runner-up: another type on the same root (C vs Cmaj7) or another
            # first-pass chord (C vs Am), whichever is more likely.
            quality_probs[index] = 0
            other_quality = int(np.argmax(quality_probs))
            others = first_pass.copy()
            others[[image[0], image[1], N_STATE]] = 0
            other_chord = int(np.argmax(others))
            if quality_probs[other_quality] >= max(0.15, others[other_chord]):
                event["alternative"] = label(root * _Q + other_quality, start)
            elif others[other_chord] >= 0.15:
                event["alternative"] = label((other_chord // 2) * _Q + other_chord % 2, start)
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
        "progression": find_core_progression(main_chords, label(tonic * _Q + (mode == MINOR), tonic_beat))
        or find_core_progression([_simplify(chord) for chord in main_chords], label(tonic * _Q + (mode == MINOR), tonic_beat)),
    }


# "Quick changes": trust a moving bass more, including a bass on the chord's
# 3rd or 5th (Bb/F), make weak-beat changes cheaper, and keep the detail pass
# on the first pass's roots. Catches passages like Gm | Bb/F | Gm | Bb/F with
# a G held over the Bb (every two-beat rendition in the tests; the steady
# setting blends them into "Gm7"), at the price of a few extra changes on
# ordinary songs, hence opt-in.
SENSITIVE = {
    "inversion_bass_weight": 4.0,
    "inversion_share": 0.8,
    "bass_onset_bonus": 3.0,
    "change_offbeat": 0.35,
    # The detail pass then follows the first pass onto the new root; without
    # this, a G held over Bb/F re-merged Gm | Bb/F into "Gm7" (the real song).
    "first_pass_change": 0.95,
    "follow_bonus": 4.0,
}
SENSITIVITIES = ("normal", "sensitive")


def params_for(sensitivity: str = "normal") -> Params:
    if sensitivity not in SENSITIVITIES:
        raise ValueError(f"Unknown sensitivity {sensitivity!r}")
    return Params(**SENSITIVE) if sensitivity == "sensitive" else Params()


def analyze_file(path: str, sensitivity: str = "normal") -> dict:
    y, _ = librosa.load(path, sr=SR, mono=True)
    return analyze_audio(y, SR, params_for(sensitivity))


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
