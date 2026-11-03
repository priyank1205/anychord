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

CHORD_INTERVALS = {
    "maj": [0, 4, 7],
    "min": [0, 3, 7],
    "7": [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "sus4": [0, 5, 7],
}
HARTE_QUALITY = {"maj": "maj", "min": "min", "7": "7", "maj7": "maj7", "min7": "min7", "sus4": "sus4"}
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


def make_song(seed: int, duration_bars: int | None = None, modulate: bool = False) -> Song:
    """Build one synthetic song. Same seed, same song.

    With modulate=True the last third moves up 1-2 semitones (the classic pop
    "truck driver's gear change"); the reference key stays the opening key.
    """
    rng = np.random.default_rng(seed)
    mode = "major" if rng.random() < 0.6 else "minor"
    tonic = int(rng.integers(0, 12))
    tempo = float(rng.uniform(72, 150))
    beats_per_bar = 3 if rng.random() < 0.15 else 4
    detune = float(rng.uniform(-35, 35))
    beat = 60.0 / tempo
    bank = MAJOR_PROGRESSIONS if mode == "major" else MINOR_PROGRESSIONS
    verse, chorus = (bank[i] for i in rng.choice(len(bank), size=2, replace=False))

    # Chord plan in beats: mostly one chord per bar, sometimes split bars or held bars.
    plan: list[tuple[int, str, int]] = []
    sections = [verse, verse, chorus, chorus, verse, chorus]
    total_bars = duration_bars or int(rng.integers(20, 30))
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
    plan.append((tonic, "min" if mode == "minor" else "maj", 2 * beats_per_bar))  # final tonic
    tonics = [tonic] * len(plan)
    if modulate:
        shift = int(rng.choice([1, 2]))
        for index in range(int(len(plan) * 0.65), len(plan)):
            root, quality, length = plan[index]
            plan[index] = ((root + shift) % 12, quality, length)
            tonics[index] = (tonic + shift) % 12

    lead_in = float(rng.uniform(0.2, 1.5))
    drum_intro_bars = int(rng.integers(0, 2))
    intro_beats = drum_intro_bars * beats_per_bar
    total_beats = intro_beats + sum(length for *_, length in plan)
    beat_times = lead_in + np.arange(total_beats + 1) * beat
    length_sec = beat_times[-1] + 1.5
    music = np.zeros(int(length_sec * SR))
    drums = np.zeros_like(music)

    harmony_style = rng.choice(["strum", "arp", "pad", "piano"], size=int(rng.integers(1, 3)), replace=False)
    distortion = rng.random() < 0.25
    scale = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    melody_note = 72 + ((tonic - 72) % 12)
    chords: list[tuple[float, float, str]] = []
    if lead_in + intro_beats * beat > 0:
        chords.append((0.0, float(beat_times[intro_beats]), "N"))

    cursor = intro_beats
    plan_index = 0
    for root, quality, length in plan:
        start, end = float(beat_times[cursor]), float(beat_times[cursor + length])
        pcs = [(root + interval) % 12 for interval in CHORD_INTERVALS[quality]]
        inversion = rng.random() < 0.1 and quality in ("maj", "min")
        bass_pc = pcs[1] if inversion else root
        label = f"{PC_NAMES[root]}:{HARTE_QUALITY[quality]}" + ("/3" if inversion and quality == "maj" else "/b3" if inversion else "")
        chords.append((start, end, label))
        voicing = _voicing(pcs, rng)

        for style in harmony_style:
            if style == "pad":
                for note in voicing:
                    tone = _tone(_midi_hz(note, detune), end - start + 0.05, rng, _partials(rng, 8, 1.0), 0, attack=0.08, sustain=True)
                    _add(music, start, tone, 0.12)
                continue
            for step in range(length * 2):
                time = start + step * beat / 2
                on_beat = step % 2 == 0
                if style == "strum" and (on_beat or rng.random() < 0.4):
                    for string, note in enumerate(voicing if rng.random() < 0.5 else voicing[::-1]):
                        tone = _tone(_midi_hz(note, detune), 1.2, rng, _partials(rng, 12, 1.2), 3.5, inharmonicity=1e-4)
                        _add(music, time + string * rng.uniform(0.006, 0.014), tone, 0.16 if on_beat else 0.09)
                elif style == "arp":
                    note = voicing[step % len(voicing)] + (12 if step % 4 == 3 else 0)
                    tone = _tone(_midi_hz(note, detune), 0.8, rng, _partials(rng, 10, 1.4), 4.5, inharmonicity=1e-4)
                    _add(music, time, tone, 0.22)
                elif style == "piano" and step % beats_per_bar == 0:
                    for note in voicing:
                        tone = _tone(_midi_hz(note, detune), 1.8, rng, _partials(rng, 14, 1.6), 1.8, inharmonicity=3e-4)
                        _add(music, time, tone, 0.15)

        # Bass: root (or inversion) on the downbeat, fifth or root mid-bar,
        # and a scale-step approach note into the next chord now and then.
        bass_base = 36 + ((bass_pc - 36) % 12)
        for offset in range(length):
            time = start + offset * beat
            if offset % beats_per_bar == 0:
                note = bass_base
            elif offset % beats_per_bar == 2 and beats_per_bar == 4:
                note = bass_base + 7 if rng.random() < 0.5 else bass_base
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
            time = start + offset * beat
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

    if distortion:
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
        f"{'+'.join(harmony_style)}{', distorted' if distortion else ''}{', modulates' if modulate else ''}"
    )
    return Song(mix.astype(np.float32), SR, (tonic, mode), tempo, beats_per_bar, detune, chords, description)
