"""Score the analyser on synthetic songs or on your own annotated recordings.

Synthetic benchmark (fast regression signal):
    python -m server.benchmark.run --songs 40
    python -m server.benchmark.run --songs 40 --seed 400 --extended   # rich chords
    python -m server.benchmark.run --songs 40 --seed 700 --fast       # quick changes

Real recordings (the number that matters): put `song.wav` next to a Harte
`.lab` file (`start end label` per line, e.g. `12.40 14.95 A:min7`) and an
optional `song.key` file containing e.g. `A minor`, then:
    python -m server.benchmark.run --dataset path/to/folder
"""

from __future__ import annotations

import argparse
import importlib
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from server.benchmark.metrics import majmin_scores
from server.music import mirex_key_score, parse_key


def load_analyzer(spec: str):
    module_name, function_name = spec.split(":")
    return getattr(importlib.import_module(module_name), function_name)


def _estimate_segments(result: dict) -> list[tuple[float, float, str]]:
    return [(event["start"], event["end"], event["chord"]) for event in result["timing"]]


def _score(name, reference, ref_key, result, elapsed, meta=""):
    scores = majmin_scores(reference, _estimate_segments(result))
    key_score = mirex_key_score(parse_key(result["key"]), ref_key) if ref_key else float("nan")
    return {"name": name, **scores, "key": key_score, "est_key": result["key"], "seconds": elapsed, "meta": meta}


def _synthetic_case(job):
    seed, analyzer_spec, modulate, extended, fast = job
    from server.benchmark.synth import PC_NAMES, make_song

    song = make_song(seed, modulate=modulate, extended=extended, fast=fast)
    analyzer = load_analyzer(analyzer_spec)
    started = time.perf_counter()
    result = analyzer(song.audio, song.sr)
    elapsed = time.perf_counter() - started
    ref_key = f"{PC_NAMES[song.key[0]]} {song.key[1]}"
    row = _score(f"synth-{seed:03d}", song.chords, song.key, result, elapsed, f"{song.description} | ref {ref_key}")
    row["tempo"] = float(abs(result["tempo"] - song.tempo) <= 0.04 * song.tempo)
    row["meter"] = float(result.get("meter") == f"{song.beats_per_bar}/4")
    return row


def _file_case(job):
    audio_path, analyzer_spec = job
    import librosa

    lab = audio_path.with_suffix(".lab")
    reference = []
    for line in lab.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            reference.append((float(parts[0]), float(parts[1]), parts[2]))
    key_file = audio_path.with_suffix(".key")
    ref_key = parse_key(key_file.read_text().strip()) if key_file.exists() else None
    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    analyzer = load_analyzer(analyzer_spec)
    started = time.perf_counter()
    result = analyzer(y, sr)
    return _score(audio_path.stem, reference, ref_key, result, time.perf_counter() - started)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--songs", type=int, default=40, help="number of synthetic songs")
    parser.add_argument("--seed", type=int, default=0, help="first synthetic seed")
    parser.add_argument("--dataset", type=Path, help="folder of .wav/.mp3 files with matching .lab (and optional .key)")
    parser.add_argument("--analyzer", default="server.analysis:analyze_audio", help="module:function(y, sr) -> result")
    parser.add_argument("--modulate", action="store_true", help="synthetic songs change key for the last third")
    parser.add_argument("--extended", action="store_true", help="synthetic songs use sevenths, sus, add9, 9/11/13, dim, aug, power and slash chords")
    parser.add_argument("--fast", action="store_true", help="synthetic songs change chord every 1-3 beats, with pushed chords")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--verbose", action="store_true", help="print every song")
    args = parser.parse_args()

    if args.dataset:
        audio = sorted(p for p in args.dataset.iterdir() if p.suffix in {".wav", ".mp3", ".flac", ".m4a"} and p.with_suffix(".lab").exists())
        jobs, worker = [(path, args.analyzer) for path in audio], _file_case
    else:
        jobs, worker = [(seed, args.analyzer, args.modulate, args.extended, args.fast) for seed in range(args.seed, args.seed + args.songs)], _synthetic_case

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(worker, jobs))

    for row in rows:
        if args.verbose or row["majmin"] < 0.7 or row["key"] < 1:
            print(f"{row['name']:>10}  majmin {row['majmin']:.3f}  exact {row['exact']:.3f}  seg {row['seg']:.3f}  "
                  f"key {row['key']:.1f} ({row['est_key']})  {row['seconds']:.1f}s  {row['meta']}")
    print()
    print(f"songs        {len(rows)}")
    for metric in ("majmin", "root", "sevenths", "exact", "bass", "overlabel", "underlabel", "seg", "changes", "key", "tempo", "meter"):
        values = np.array([row.get(metric, np.nan) for row in rows], dtype=float)
        print(f"{metric:<12} {np.nanmean(values):.3f}")
    print(f"exact keys   {sum(row['key'] == 1 for row in rows)}/{len(rows)}")
    print(f"sec/song     {np.mean([row['seconds'] for row in rows]):.2f}")


if __name__ == "__main__":
    main()
