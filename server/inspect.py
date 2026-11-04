"""Show what the analyser hears, half-beat by half-beat, for a stretch of a song.

    npm run inspect -- "https://www.youtube.com/watch?v=..." --from 0:10 --to 0:30
    npm run inspect -- song.mp3 --from 10 --to 30

Each line is one frame (| = on the beat, . = between beats):

    0:12.43 |  Gm7      first pass  Gm 82%  Bb 15%     notes  G 1.00 D .85 Bb .70 F .55   bass  G 1.00 Bb .40

- chart: the chord the chart shows there
- first pass: the analyser's major/minor reading and how sure it is
- notes: the loudest pitch classes, relative to the loudest (1.00)
- bass: the loudest bass notes, same scale

Nothing is saved; paste the output wherever you need it.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np

from server.analysis import N_STATE, SR, analyze_features, extract_features, params_for
from server.music import key_signature_names


def parse_time(text: str) -> float:
    """"1:23.5" or "83.5" -> seconds."""
    seconds = 0.0
    for part in text.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


def load(source: str) -> tuple[np.ndarray, str]:
    if Path(source).exists():
        y, _ = librosa.load(source, sr=SR, mono=True)
        return y, Path(source).name
    from server.app import download_audio  # needs yt-dlp in server/vendor and ffmpeg

    with tempfile.TemporaryDirectory(prefix="anychords-inspect-") as directory:
        wav, metadata = download_audio(source, Path(directory))
        y, _ = librosa.load(str(wav), sr=SR, mono=True)
    return y, metadata.get("title") or source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="YouTube link or audio file")
    parser.add_argument("--from", dest="start", default="0", help="start time, e.g. 0:10 (default 0)")
    parser.add_argument("--to", dest="end", default=None, help="end time, e.g. 0:30 (default: start + 30 s)")
    parser.add_argument("--sensitive", action="store_true", help='use the "more quick changes" setting')
    args = parser.parse_args()
    start = parse_time(args.start)
    end = parse_time(args.end) if args.end else start + 30

    print("Loading audio…", file=sys.stderr)
    y, title = load(args.source)
    params = params_for("sensitive" if args.sensitive else "normal")
    features = extract_features(y, SR, params)
    trace: dict = {}
    result = analyze_features(features, params, trace)

    names = key_signature_names(*trace["regions"][0][1])
    first_pass_name = ["N.C." if s == N_STATE else names[s // 2] + ("m" if s % 2 else "") for s in range(N_STATE + 1)]
    note_names = names

    def chart_at(time: float) -> str:
        return next((e["chord"] for e in result["timing"] if e["start"] <= time < e["end"]), "")

    print(f"{title} | key {result['key']} | {result['tempo']} BPM | {result['meter']} | frames of half a beat")
    print(f"chart {clock(start)}-{clock(end)}: " + " ".join(
        e["chord"] for e in result["timing"] if e["end"] > start and e["start"] < end
    ))
    print()
    posterior = trace["posterior"]
    for index in range(len(features.boundaries) - 1):
        t0, t1 = features.boundaries[index], features.boundaries[index + 1]
        if t1 <= start or t0 >= end:
            continue
        marker = "|" if index % features.subdivisions == 0 else "."
        top = np.argsort(-posterior[:, index])[:2]
        guesses = "  ".join(f"{first_pass_name[s]:<4}{posterior[s, index] * 100:3.0f}%" for s in top)
        notes = features.detail[:, index]
        bass = features.detail_bass[:, index]
        loud = "  ".join(f"{note_names[k]:<2}{notes[k]:.2f}" for k in np.argsort(-notes)[:5])
        low = "  ".join(f"{note_names[k]:<2}{bass[k]:.2f}" for k in np.argsort(-bass)[:2])
        print(f"{clock(t0)} {marker} {chart_at((t0 + t1) / 2):<7}  first pass {guesses:<20}  notes {loud}   bass {low}")


if __name__ == "__main__":
    main()
