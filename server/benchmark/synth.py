"""Synthetic songs with exact ground truth, for regression-testing the analyser.

These are deliberately unfriendly: global detuning, drums, a loud melody full
of passing tones, walking/approach bass notes, inversions, sevenths, borrowed
chords, V-major in minor keys, distortion, reverb and 3/4 songs. They are still
cleaner than a real mix, so treat the scores as an upper bound and a
regression signal, not as real-world accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import fftconvolve, lfilter

SR = 22050

# (semitones above tonic, quality). Qualities: maj, min, 7, maj7, min7, sus4.
MAJOR_PROGRESSIONS = [
    [(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")],  # I V vi IV
    [(9, "min"), (5, "maj"), (0, "maj"), (7, "maj")],  # vi IV I V
    [(0, "maj"), (5, "maj"), (7, "maj"), (5, "maj")],  # I IV V IV
    [(0, "maj"), (9, "min"), (5, "maj"), (7, "maj")],  # I vi IV V
    [(0, "maj"), (10, "maj"), (5, "maj"), (0, "maj")],  # I bVII IV I
    [(2, "min7"), (7, "7"), (0, "maj7"), (0, "maj7")],  # ii7 V7 Imaj7
    [(0, "maj"), (4, "min"), (5, "maj"), (5, "min")],  # I iii IV iv
    [(0, "maj"), (2, "maj"), (5, "maj"), (0, "maj")],  # I II IV I
    [(0, "maj"), (8, "maj"), (10, "maj"), (0, "maj")],  # I bVI bVII I
    [(5, "maj"), (7, "maj"), (4, "min"), (9, "min")],  # IV V iii vi
    [(0, "maj"), (7, "maj"), (5, "sus4"), (5, "maj")],  # I V IVsus4 IV
]
MINOR_PROGRESSIONS = [
    [(0, "min"), (8, "maj"), (3, "maj"), (10, "maj")],  # i VI III VII
    [(0, "min"), (5, "min"), (7, "maj"), (0, "min")],  # i iv V i
    [(0, "min"), (10, "maj"), (8, "maj"), (7, "maj")],  # i VII VI V
    [(0, "min"), (5, "min"), (10, "maj"), (3, "maj")],  # i iv VII III
    [(0, "min"), (8, "maj"), (5, "min"), (7, "7")],  # i VI iv V7
    [(0, "min7"), (7, "min"), (5, "min7"), (0, "min")],  # i v iv i
    [(0, "min"), (3, "maj"), (10, "maj"), (5, "min")],  # i III VII iv
]

# Extended-vocabulary songs (extended=True): jazz ii-V-Is, line clichés,
# sus/add9 pop, passing diminished chords, blues dominants, and power-chord
# rock. Quality names follow server.music.QUALITY_INTERVALS.
EXTENDED_MAJOR = [
    [(2, "min7"), (7, "7"), (0, "maj7"), (0, "maj7")],  # ii7 V7 Imaj7
    [(2, "m9"), (7, "13"), (0, "maj9"), (0, "6")],  # ii9 V13 Imaj9 I6
    [(0, "add9"), (7, "sus4"), (7, "maj"), (9, "min7")],  # Iadd9 Vsus4 V vi7
    [(0, "maj"), (0, "maj7"), (0, "7"), (5, "maj")],  # line cliché
    [(0, "maj"), (1, "dim7"), (2, "min7"), (7, "7")],  # I #I°7 ii7 V7
    [(0, "maj"), (0, "aug"), (0, "6"), (0, "7")],  # I I+ I6 I7
    [(5, "maj7"), (4, "min7"), (2, "min7"), (0, "maj7")],  # IVmaj7 iii7 ii7 Imaj7
    [(0, "sus2"), (0, "maj"), (5, "sus2"), (5, "maj")],  # sus2 resolutions
    [(7, "7sus4"), (7, "7"), (0, "maj"), (0, "add9")],
    [(5, "maj"), (7, "11"), (0, "maj"), (9, "min")],  # IV V11 I vi
    [(0, "7"), (5, "7"), (0, "7"), (7, "9")],  # blues
]
EXTENDED_MINOR = [
    [(2, "m7b5"), (7, "7"), (0, "min7"), (0, "m9")],  # iiø7 V7 i7
    [(0, "min"), (0, "mMaj7"), (0, "min7"), (0, "m6")],  # minor line cliché
    [(0, "m9"), (5, "min7"), (10, "7"), (3, "maj7")],
    [(0, "m11"), (5, "7"), (0, "m11"), (5, "7")],  # dorian vamp
    [(0, "min"), (10, "maj"), (8, "maj7"), (7, "7")],
    [(0, "min7"), (11, "dim7"), (0, "min"), (7, "7sus4")],  # i7 vii°7 i Vsus
    [(0, "madd9"), (8, "maj"), (3, "maj"), (2, "dim")],
]
POWER_PROGRESSIONS = [
    [(0, "5"), (3, "5"), (5, "5"), (0, "5")],
    [(0, "5"), (10, "5"), (5, "5"), (7, "5")],
    [(0, "5"), (8, "5"), (10, "5"), (0, "5")],
]

# Fast harmonic rhythm (fast=True): (degree, quality, beats). Line-end
# turnarounds that flip between chords every beat, half-bar changes and
# walking chords; in 4/4, each pattern fills whole bars.
FAST_MAJOR = [
    [(7, "maj", 4), (2, "min", 1), (5, "maj", 1), (2, "min", 1), (5, "maj", 1), (0, "maj", 8)],  # V | ii IV ii IV | I
    [(0, "maj", 2), (5, "maj", 2), (7, "maj", 2), (5, "maj", 2)],  # I IV V IV, two beats each
    [(9, "min", 3), (7, "maj", 1), (5, "maj", 4)],  # vi (3) V (1) | IV
    [(0, "maj", 1), (2, "min", 1), (4, "min", 1), (5, "maj", 1), (7, "maj", 4)],  # walking I ii iii IV | V
    [(5, "maj", 2), (7, "maj", 2), (0, "maj", 2), (9, "min", 2)],
    [(0, "maj", 4), (4, "min", 1), (7, "maj", 1), (4, "min", 1), (7, "maj", 1)],  # I | iii V iii V
]
FAST_MINOR = [
    [(0, "min", 2), (10, "maj", 2), (8, "maj", 2), (7, "maj", 2)],  # i VII VI V, two beats each
    [(0, "min", 4), (5, "min", 1), (7, "maj", 1), (0, "min", 2)],  # i | iv V i
    [(8, "maj", 1), (10, "maj", 1), (0, "min", 2), (8, "maj", 1), (10, "maj", 1), (0, "min", 2)],
    [(3, "maj", 4), (5, "min", 1), (8, "maj", 1), (5, "min", 1), (8, "maj", 1)],  # III | iv VI iv VI
    [(0, "min", 3), (10, "maj", 1), (8, "maj", 4)],
]

CHORD_INTERVALS = {
    "maj": [0, 4, 7],
    "min": [0, 3, 7],
    "7": [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "sus4": [0, 5, 7],
    "sus2": [0, 2, 7],
    "5": [0, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "m7b5": [0, 3, 6, 10],
    "dim7": [0, 3, 6, 9],
    "mMaj7": [0, 3, 7, 11],
    "7sus4": [0, 5, 7, 10],
    "6": [0, 4, 7, 9],
    "m6": [0, 3, 7, 9],
    "add9": [0, 4, 7, 14],
    "madd9": [0, 3, 7, 14],
    "9": [0, 4, 7, 10, 14],
    "maj9": [0, 4, 7, 11, 14],
    "m9": [0, 3, 7, 10, 14],
    "11": [0, 7, 10, 14, 17],
    "m11": [0, 3, 7, 10, 14, 17],
    "13": [0, 4, 7, 10, 14, 21],
}
HARTE_QUALITY = {
    "maj": "maj", "min": "min", "7": "7", "maj7": "maj7", "min7": "min7", "sus4": "sus4", "sus2": "sus2",
    "5": "5", "dim": "dim", "aug": "aug", "m7b5": "hdim7", "dim7": "dim7", "mMaj7": "minmaj7",
    "7sus4": "sus4(b7)", "6": "maj6", "m6": "min6", "add9": "maj(9)", "madd9": "min(9)", "9": "9",
    "maj9": "maj9", "m9": "min9", "11": "(1,5,b7,9,11)", "m11": "min11", "13": "7(9,13)",
}
_BASS_DEGREE = {3: "b3", 4: "3", 6: "b5", 7: "5", 8: "#5", 9: "6", 10: "b7", 11: "7"}
PC_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]


@dataclass
class Song:
    audio: np.ndarray
    sr: int
    key: tuple[int, str]
    tempo: float
    beats_per_bar: int
    detune_cents: float
    # (start_sec, end_sec, harte_label)
    chords: list[tuple[float, float, str]] = field(default_factory=list)
    description: str = ""


def _midi_hz(midi: float, detune_cents: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69 + detune_cents / 100.0) / 12.0)


def _tone(
    freq: float,
    duration: float,
    rng: np.random.Generator,
    partials: np.ndarray,
    decay: float,
    attack: float = 0.005,
    inharmonicity: float = 0.0,
    vibrato_cents: float = 0.0,
    sustain: bool = False,
) -> np.ndarray:
    count = max(1, int(duration * SR))
    t = np.arange(count) / SR
    if vibrato_cents:
        rate = rng.uniform(4.5, 6.5)
        ramp = np.clip(t / 0.25, 0, 1)
        deviation = 2 ** (vibrato_cents * ramp * np.sin(2 * np.pi * rate * t) / 1200.0)
        phase_base = 2 * np.pi * np.cumsum(freq * deviation) / SR
    else:
        phase_base = 2 * np.pi * freq * t
    signal = np.zeros(count)
    for index, amplitude in enumerate(partials, start=1):
        stretch = np.sqrt(1 + inharmonicity * index * index)
        if freq * index * stretch >= SR / 2 - 500:
            break
        envelope = 1.0 if sustain else np.exp(-t * decay * (1 + 0.25 * (index - 1)))
        signal += amplitude * envelope * np.sin(index * stretch * phase_base + rng.uniform(0, 2 * np.pi))
    attack_count = max(1, int(attack * SR))
    signal[:attack_count] *= np.linspace(0, 1, attack_count)
    release_count = min(count, int(0.03 * SR))
    signal[-release_count:] *= np.linspace(1, 0, release_count)
    return signal


def _add(buffer: np.ndarray, start: float, signal: np.ndarray, gain: float) -> None:
    index = int(start * SR)
    if index >= len(buffer):
        return
    end = min(len(buffer), index + len(signal))
    buffer[index:end] += gain * signal[: end - index]


def _partials(rng: np.random.Generator, count: int, rolloff: float) -> np.ndarray:
    base = 1.0 / np.arange(1, count + 1) ** rolloff
    return base * rng.uniform(0.6, 1.4, size=count)


def _voicing(pitch_classes: list[int], rng: np.random.Generator) -> list[int]:
    low = int(rng.integers(50, 58))
    notes = sorted(low + ((pc - low) % 12) for pc in pitch_classes)
    if rng.random() < 0.6:
        notes.append(notes[0] + 12)
    return notes


def _drums(buffer: np.ndarray, beat_times: np.ndarray, beats_per_bar: int, level: float, rng: np.random.Generator) -> None:
    kick_t = np.arange(int(0.3 * SR)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-kick_t / 0.03)) / SR) * np.exp(-kick_t / 0.12)
    snare_t = np.arange(int(0.2 * SR)) / SR
    snare = (rng.normal(size=len(snare_t)) * 0.7 + np.sin(2 * np.pi * 185 * snare_t)) * np.exp(-snare_t / 0.06)
    hat_t = np.arange(int(0.06 * SR)) / SR
    hat = lfilter([1, -1], [1], rng.normal(size=len(hat_t))) * np.exp(-hat_t / 0.015) * 0.4
    period = float(np.median(np.diff(beat_times))) if len(beat_times) > 1 else 0.5
    for index, time in enumerate(beat_times):
        position = index % beats_per_bar
        if position == 0 or (beats_per_bar == 4 and position == 2):
            _add(buffer, time, kick, level)
        if (beats_per_bar == 4 and position in (1, 3)) or (beats_per_bar == 3 and position in (1, 2)):
            _add(buffer, time, snare, level * 0.6)
        _add(buffer, time, hat, level * 0.5)
        _add(buffer, time + period / 2, hat, level * 0.35)


def make_song(seed: int, duration_bars: int | None = None, modulate: bool = False, extended: bool = False, fast: bool = False) -> Song:
    """Build one synthetic song. Same seed, same song.

    With modulate=True the last third moves up 1-2 semitones (the classic pop
    "truck driver's gear change"); the reference key stays the opening key.
    With extended=True the harmony uses sevenths, sus, add9, 6ths, 9/11/13,
    diminished/augmented, power chords and slash chords.
    With fast=True chords change every 1-3 beats (4/4), including line-end
    turnarounds like "C | Gm Bb Gm Bb | F" and chords pushed half a beat early.
    """
    rng = np.random.default_rng(seed)
    mode = "major" if rng.random() < 0.6 else "minor"
    tonic = int(rng.integers(0, 12))
    tempo = float(rng.uniform(72, 150))
    beats_per_bar = 3 if rng.random() < 0.15 else 4
    detune = float(rng.uniform(-35, 35))
    beat = 60.0 / tempo
    bank = MAJOR_PROGRESSIONS if mode == "major" else MINOR_PROGRESSIONS
    power = False
    if extended:
        power = rng.random() < 0.2
        bank = POWER_PROGRESSIONS if power else EXTENDED_MAJOR if mode == "major" else EXTENDED_MINOR
        if power:
            mode = "minor"
    if fast:
        beats_per_bar = 4
        bank = FAST_MAJOR if mode == "major" else FAST_MINOR
    verse, chorus = (bank[i] for i in rng.choice(len(bank), size=2, replace=False))

    # Chord plan in beats: mostly one chord per bar, sometimes split bars or held bars.
    plan: list[tuple[int, str, int]] = []
    sections = [verse, verse, chorus, chorus, verse, chorus]
    total_bars = duration_bars or int(rng.integers(20, 30))
    section = 0
    while fast and sum(length for *_, length in plan) < total_bars * beats_per_bar:
        plan.extend(((tonic + degree) % 12, quality, length) for degree, quality, length in sections[section % len(sections)])
        section += 1
    while sum(length for *_, length in plan) < total_bars * beats_per_bar:
        for degree, quality in sections[len(plan) // 4 % len(sections)]:
            style = rng.random()
            if style < 0.12 and beats_per_bar == 4:
                length = 2
            elif style < 0.25:
                length = 2 * beats_per_bar
            else:
                length = beats_per_bar
            plan.append(((tonic + degree) % 12, quality, length))
    plan.append((tonic, "5" if power else "min" if mode == "minor" else "maj", 2 * beats_per_bar))  # final tonic
    tonics = [tonic] * len(plan)
    if modulate:
        shift = int(rng.choice([1, 2]))
        for index in range(int(len(plan) * 0.65), len(plan)):
            root, quality, length = plan[index]
            plan[index] = ((root + shift) % 12, quality, length)
            tonics[index] = (tonic + shift) % 12
    # Pushed chords: arrive half a beat early, as in most pop playing (after a
    # chord of 2+ beats; pushing after a one-beat chord would leave half a beat).
    pushed = [False] + [bool(rng.random() < 0.15) and plan[i - 1][2] >= 2 for i in range(1, len(plan))] if fast else [False] * len(plan)

    lead_in = float(rng.uniform(0.2, 1.5))
    drum_intro_bars = int(rng.integers(0, 2))
    intro_beats = drum_intro_bars * beats_per_bar
    total_beats = intro_beats + sum(length for *_, length in plan)
    beat_times = lead_in + np.arange(total_beats + 1) * beat
    length_sec = beat_times[-1] + 1.5
    music = np.zeros(int(length_sec * SR))
    drums = np.zeros_like(music)
    # Extended songs distort only the guitar/keys, as real mixes do; the
    # original benchmark distorts the whole bus (kept for comparability).
    harmony = np.zeros_like(music) if extended else music

    harmony_style = rng.choice(["strum", "arp", "pad", "piano"], size=int(rng.integers(1, 3)), replace=False)
    distortion = rng.random() < 0.25
    if power:
        harmony_style, distortion = np.array(["strum"]), True
    scale = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    melody_note = 72 + ((tonic - 72) % 12)
    chords: list[tuple[float, float, str]] = []
    if lead_in + intro_beats * beat > 0:
        chords.append((0.0, float(beat_times[intro_beats]), "N"))

    cursor = intro_beats
    plan_index = 0
    for root, quality, length in plan:
        grid_start = float(beat_times[cursor])
        start = grid_start - (beat / 2 if pushed[plan_index] else 0.0)
        end = float(beat_times[cursor + length]) - (beat / 2 if plan_index + 1 < len(plan) and pushed[plan_index + 1] else 0.0)
        intervals = CHORD_INTERVALS[quality]
        pcs = [(root + interval) % 12 for interval in intervals]
        if extended:
            bass_options = [i for i in intervals if i in _BASS_DEGREE]
            bass_interval = int(rng.choice(bass_options)) if bass_options and quality != "5" and rng.random() < 0.15 else 0
            bass_pc = (root + bass_interval) % 12
            label = f"{PC_NAMES[root]}:{HARTE_QUALITY[quality]}" + (f"/{_BASS_DEGREE[bass_interval]}" if bass_interval else "")
            voiced = [pc for pc, i in zip(pcs, intervals) if not (len(intervals) >= 5 and i == 7 and rng.random() < 0.5)]
            voicing = _voicing(voiced, rng)
            if quality == "5":
                voicing = sorted({voicing[0], voicing[0] + 7, voicing[0] + 12})
        else:
            inversion = rng.random() < 0.1 and quality in ("maj", "min")
            bass_pc = pcs[1] if inversion else root
            label = f"{PC_NAMES[root]}:{HARTE_QUALITY[quality]}" + ("/3" if inversion and quality == "maj" else "/b3" if inversion else "")
            voicing = _voicing(pcs, rng)
        chords.append((start, end, label))

        for style in harmony_style:
            if style == "pad":
                for note in voicing:
                    tone = _tone(_midi_hz(note, detune), end - start + 0.05, rng, _partials(rng, 8, 1.0), 0, attack=0.08, sustain=True)
                    _add(harmony, start, tone, 0.12)
                continue
            for step in range(int(round((end - start) / (beat / 2)))):
                time = start + step * beat / 2
                on_beat = (step + pushed[plan_index]) % 2 == 0
                if style == "strum" and (on_beat or rng.random() < 0.4):
                    for string, note in enumerate(voicing if rng.random() < 0.5 else voicing[::-1]):
                        tone = _tone(_midi_hz(note, detune), 1.2, rng, _partials(rng, 12, 1.2), 3.5, inharmonicity=1e-4)
                        _add(harmony, time + string * rng.uniform(0.006, 0.014), tone, 0.16 if on_beat else 0.09)
                elif style == "arp":
                    note = voicing[step % len(voicing)] + (12 if step % 4 == 3 else 0)
                    tone = _tone(_midi_hz(note, detune), 0.8, rng, _partials(rng, 10, 1.4), 4.5, inharmonicity=1e-4)
                    _add(harmony, time, tone, 0.22)
                elif style == "piano" and step % beats_per_bar == 0:
                    for note in voicing:
                        tone = _tone(_midi_hz(note, detune), 1.8, rng, _partials(rng, 14, 1.6), 1.8, inharmonicity=3e-4)
                        _add(harmony, time, tone, 0.15)

        # Bass: root (or inversion) on the downbeat, fifth or root mid-bar,
        # and a scale-step approach note into the next chord now and then.
        bass_base = 36 + ((bass_pc - 36) % 12)
        for offset in range(length):
            time = start + offset * beat if offset == 0 else grid_start + offset * beat
            if offset % beats_per_bar == 0:
                note = bass_base
            elif offset % beats_per_bar == 2 and beats_per_bar == 4:
                # The chord's own fifth (the original benchmark added a fifth
                # above an inverted bass: B under C/E, a note not in the chord).
                fifth = next((i for i in intervals if i in (6, 7, 8)), 0)
                note = 36 + ((root + fifth - 36) % 12) if rng.random() < 0.5 else bass_base
            elif offset == length - 1 and rng.random() < 0.3 and plan_index + 1 < len(plan):
                next_root = plan[plan_index + 1][0]
                note = 36 + ((next_root - 36) % 12) + (1 if rng.random() < 0.5 else -2)
            else:
                continue
            tone = _tone(_midi_hz(note, detune), beat * 1.9, rng, _partials(rng, 8, 1.8), 2.0)
            _add(music, time, tone, 0.5)

        # Melody: chord tones on strong beats, scale passing tones in between.
        for offset in range(length):
            if rng.random() < 0.2:
                continue
            time = grid_start + offset * beat
            if offset % 2 == 0:
                candidates = [melody_note + d for d in range(-5, 6) if (melody_note + d) % 12 in pcs]
            else:
                candidates = [melody_note + d for d in (-2, -1, 1, 2) if (melody_note + d - tonics[plan_index]) % 12 in scale]
            if candidates:
                melody_note = int(np.clip(rng.choice(candidates), 64, 84))
            vocal = _tone(_midi_hz(melody_note, detune), beat * 0.95, rng, _partials(rng, 6, 0.9), 0, attack=0.03, vibrato_cents=float(rng.uniform(15, 35)), sustain=True)
            _add(music, time, vocal, float(rng.uniform(0.18, 0.3)))

        cursor += length
        plan_index += 1

    if extended:
        music = music + (np.tanh(3.0 * harmony) / 3.0 if distortion else harmony)
    elif distortion:
        music = np.tanh(3.0 * music) / 3.0
    _drums(drums, beat_times[:-1], beats_per_bar, float(rng.uniform(0.25, 0.6)), rng)
    mix = music + drums
    ir_t = np.arange(int(1.2 * SR)) / SR
    impulse = rng.normal(size=len(ir_t)) * np.exp(-ir_t / rng.uniform(0.2, 0.45))
    impulse /= np.sqrt(np.sum(impulse**2))
    wet = fftconvolve(mix, impulse)[: len(mix)]
    mix = mix + float(rng.uniform(0.1, 0.35)) * wet + rng.normal(scale=1e-3, size=len(mix))
    mix /= np.max(np.abs(mix)) + 1e-9
    chords.append((float(beat_times[-1]), float(length_sec), "N"))

    description = (
        f"{PC_NAMES[tonic]} {mode}, {tempo:.0f} BPM, {beats_per_bar}/4, detune {detune:+.0f}c, "
        f"{'+'.join(harmony_style)}{', distorted' if distortion else ''}{', modulates' if modulate else ''}{', power chords' if power else ', extended' if extended else ''}{', fast changes' if fast else ''}"
    )
    return Song(mix.astype(np.float32), SR, (tonic, mode), tempo, beats_per_bar, detune, chords, description)


def render_progression(
    chords: list[tuple[str, float]],
    tempo: float,
    bass: list[tuple[str, float]],
    held: list[tuple[str | None, float]] | None = None,
    seed: int = 0,
    held_gain: float = 0.2,
) -> Song:
    """Render an explicit progression, for regression tests built from real songs.

    chords: (Harte label, beats), e.g. ("Bb:maj/5", 2). bass: (note, beats),
    a bass line played under them. held: (note or None, beats), a sustained
    voice on top (a sung or held note that rings across chord changes).
    """
    from server.music import NOTE_INDEX, parse_chord

    rng = np.random.default_rng(seed)
    beat = 60.0 / tempo
    lead_in = 0.5
    total = sum(beats for _, beats in chords)
    length = lead_in + total * beat + 1.5
    music = np.zeros(int(length * SR))
    labels: list[tuple[float, float, str]] = [(0.0, lead_in, "N")]
    time = lead_in
    for label, beats in chords:
        root, intervals, _ = parse_chord(label)
        voicing = _voicing(sorted((root + i) % 12 for i in intervals), rng)
        for step in range(int(beats * 2)):
            on_beat = step % 2 == 0
            if on_beat or rng.random() < 0.4:
                for string, note in enumerate(voicing):
                    tone = _tone(_midi_hz(note, 0), 1.2, rng, _partials(rng, 12, 1.2), 3.5, inharmonicity=1e-4)
                    _add(music, time + step * beat / 2 + string * 0.01, tone, 0.16 if on_beat else 0.09)
        labels.append((time, time + beats * beat, label))
        time += beats * beat
    time = lead_in
    for note, beats in bass:
        midi = 36 + ((NOTE_INDEX[note] - 36) % 12)
        _add(music, time, _tone(_midi_hz(midi, 0), beats * beat * 0.95, rng, _partials(rng, 8, 1.8), 2.0), 0.5)
        time += beats * beat
    time = lead_in
    for note, beats in held or []:
        if note:
            midi = 67 + ((NOTE_INDEX[note] - 67) % 12)
            voice = _tone(_midi_hz(midi, 0), beats * beat, rng, _partials(rng, 6, 0.9), 0, attack=0.05, vibrato_cents=20, sustain=True)
            _add(music, time, voice, held_gain)
        time += beats * beat
    drums = np.zeros_like(music)
    _drums(drums, lead_in + np.arange(int(total)) * beat, 4, 0.3, rng)
    mix = music + drums
    mix /= np.max(np.abs(mix)) + 1e-9
    labels.append((lead_in + total * beat, length, "N"))
    return Song(mix.astype(np.float32), SR, (0, "major"), tempo, 4, 0.0, labels, "explicit progression")
