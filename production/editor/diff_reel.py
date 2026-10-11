"""Diff a new reel against the render it was built from.

Covers every inter-word gap, every caption position, and the first three
frames after every cut (source frame index, matte frame index, plate).
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from kallaway_matte import source_frame_at, split_plate_missing


def _load(path):
    return json.loads(Path(path).read_text())


def _words(path):
    data = _load(path)
    if isinstance(data, dict):
        data = data.get("words") or data.get("mapped") or []
    return list(data)


def word_gaps(words, minimum=0.04):
    rows = []
    for left, right in zip(words, words[1:]):
        gap = float(right["start"]) - float(left["end"])
        if gap < minimum:
            continue
        rows.append({
            "at": round(float(left["end"]), 3),
            "ms": int(round(gap * 1000)),
            "left": str(left.get("word") or ""),
            "right": str(right.get("word") or ""),
        })
    return rows


def _rms_db(path):
    wav = Path("/tmp") / (Path(path).stem + "-diff.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000", str(wav)],
        check=True)
    import soundfile as sf
    samples, rate = sf.read(wav)
    samples = np.asarray(samples, dtype=np.float64)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    hop = int(0.005 * rate)
    win = int(0.010 * rate)
    count = (len(samples) - win) // hop
    rms = np.array([
        math.sqrt(float(np.mean(samples[i * hop:i * hop + win] ** 2)))
        for i in range(count)
    ])
    level = 20.0 * np.log10(np.maximum(rms, 1e-9))
    times = np.arange(count) * hop / rate
    return times, level


def energy_gaps(path, threshold=-36.0, minimum=0.08):
    times, level = _rms_db(path)
    below = level < threshold
    rows = []
    index = 0
    count = len(level)
    while index < count:
        if not below[index]:
            index += 1
            continue
        end = index
        while end < count and below[end]:
            end += 1
        span = float(times[end - 1] - times[index]) + 0.005
        if span >= minimum:
            rows.append({
                "at": round(float(times[index]), 3),
                "ms": int(round(span * 1000)),
            })
        index = end
    return rows


def _pair(base, new, slack=0.45):
    used = set()
    pairs = []
    for item in base:
        match = None
        for index, other in enumerate(new):
            if index in used:
                continue
            if abs(other["at"] - item["at"]) <= slack:
                match = index
                break
        if match is None:
            pairs.append((item, None))
            continue
        used.add(match)
        pairs.append((item, new[match]))
    for index, other in enumerate(new):
        if index not in used:
            pairs.append((None, other))
    return pairs


def caption_rows(timeline):
    captions = timeline.get("captions") or {}
    rows = [{
        "shot": "(baseline)",
        "baseline_px": captions.get("full_baseline_px"),
        "caption_y": None,
    }]
    for shot in timeline.get("shots") or []:
        rows.append({
            "shot": shot.get("id"),
            "baseline_px": captions.get("full_baseline_px"),
            "caption_y": shot.get("caption_y"),
            "layout": shot.get("layout"),
            "start": shot.get("start"),
        })
    return rows


def _frame(video, moment, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{moment:.3f}", "-i", str(video),
         "-frames:v", "1", str(dest)],
        check=True)
    return np.asarray(Image.open(dest).convert("RGB"))


def cut_report(video, timeline, ranges, fps, directory, label):
    shots = list(timeline.get("shots") or [])
    rows = []
    for shot in shots[1:]:
        start = float(shot["start"])
        for offset in range(3):
            moment = start + offset / float(fps)
            frame_index = int(math.floor(moment * float(fps) + 1e-4))
            source_index = source_frame_at(ranges, fps, frame_index) if ranges else None
            image = _frame(video, moment, Path(directory) / f"{label}-{shot.get('id')}-{offset}.png")
            plate = None
            if shot.get("layout") == "split":
                plate = not split_plate_missing(image)
            rows.append({
                "shot": shot.get("id"),
                "offset": offset,
                "time": round(moment, 3),
                "video_frame": frame_index,
                "source_frame": source_index,
                "matte_frame": frame_index,
                "plate": plate,
                "mean": round(float(image.mean()), 2),
            })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-video", required=True)
    parser.add_argument("--new-video", required=True)
    parser.add_argument("--base-timeline", required=True)
    parser.add_argument("--new-timeline", required=True)
    parser.add_argument("--base-words", required=True)
    parser.add_argument("--new-words", required=True)
    parser.add_argument("--base-ranges", help="JSON list of [begin, end] video ranges")
    parser.add_argument("--new-ranges", help="JSON list of [begin, end] video ranges")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    base_tl, new_tl = _load(args.base_timeline), _load(args.new_timeline)
    base_words, new_words = _words(args.base_words), _words(args.new_words)
    base_ranges = _load(args.base_ranges) if args.base_ranges else None
    new_ranges = _load(args.new_ranges) if args.new_ranges else None

    lines = ["# Reel diff", ""]
    lines.append("## Inter-word gaps (mapped word end to next start, >= 40 ms)")
    for left, right in _pair(word_gaps(base_words), word_gaps(new_words), slack=0.6):
        if left and right:
            delta = right["ms"] - left["ms"]
            flag = "" if abs(delta) <= 15 else "  CHANGED"
            lines.append(
                f"{left['left']!r} -> {left['right']!r}: {left['ms']} ms at {left['at']} -> "
                f"{right['ms']} ms at {right['at']} ({delta:+d} ms){flag}")
        elif left:
            lines.append(f"ONLY BASE {left['left']!r} -> {left['right']!r}: {left['ms']} ms at {left['at']}")
        else:
            lines.append(f"ONLY NEW {right['left']!r} -> {right['right']!r}: {right['ms']} ms at {right['at']}")

    lines.append("")
    lines.append("## Energy gaps (10 ms RMS below -36 dBFS, >= 80 ms)")
    base_energy = energy_gaps(args.base_video)
    new_energy = energy_gaps(args.new_video)
    for left, right in _pair(base_energy, new_energy, slack=0.5):
        if left and right:
            delta = right["ms"] - left["ms"]
            flag = "" if abs(delta) <= 20 else "  CHANGED"
            lines.append(f"{left['at']} {left['ms']} ms -> {right['at']} {right['ms']} ms ({delta:+d} ms){flag}")
        elif left:
            lines.append(f"ONLY BASE {left['at']} {left['ms']} ms")
        else:
            lines.append(f"ONLY NEW {right['at']} {right['ms']} ms")

    lines.append("")
    lines.append("## Caption positions")
    base_caps = {row["shot"]: row for row in caption_rows(base_tl)}
    new_caps = {row["shot"]: row for row in caption_rows(new_tl)}
    for key in list(base_caps) + [key for key in new_caps if key not in base_caps]:
        left, right = base_caps.get(key), new_caps.get(key)
        if left and right:
            same = left.get("caption_y") == right.get("caption_y") and left.get("baseline_px") == right.get("baseline_px")
            flag = "" if same else "  CHANGED"
            lines.append(
                f"{key}: baseline {left.get('baseline_px')} -> {right.get('baseline_px')}, "
                f"caption_y {left.get('caption_y')} -> {right.get('caption_y')}{flag}")
        elif left:
            lines.append(f"ONLY BASE {key}: {left}")
        else:
            lines.append(f"ONLY NEW {key}: {right}")

    work = Path(args.out).with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    lines.append("")
    lines.append("## First 3 frames after each cut")
    lines.append("matte_frame is the person-mask index. It equals video_frame when the matte was packed in lockstep with the picture.")
    base_cuts = cut_report(args.base_video, base_tl, base_ranges, args.fps, work / "base", "base")
    new_cuts = cut_report(args.new_video, new_tl, new_ranges, args.fps, work / "new", "new")
    base_by = {(row["shot"], row["offset"]): row for row in base_cuts}
    for row in new_cuts:
        other = base_by.get((row["shot"], row["offset"]))
        plate = "n/a" if row["plate"] is None else ("present" if row["plate"] else "MISSING")
        base_plate = ""
        if other and other["plate"] is not None:
            base_plate = " base plate " + ("present" if other["plate"] else "MISSING")
        moved = ""
        if other and other["video_frame"] != row["video_frame"]:
            moved = f"  video frame {other['video_frame']} -> {row['video_frame']}"
        lines.append(
            f"{row['shot']} +{row['offset']} t={row['time']} video_frame={row['video_frame']} "
            f"source_frame={row['source_frame']} matte_frame={row['matte_frame']} plate={plate}"
            f"{base_plate}{moved}")

    text = "\n".join(lines) + "\n"
    Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    sys.exit(main())
