#!/usr/bin/env python3
"""Assemble a talking-head master from several takes, with a word map on the master clock.

Brandon films one line per clip (A01, A02, ...). This cuts each take to its kept
ranges on the frame grid, joins them in order with short audio fades at every cut,
conforms frame rate and size, and remaps each take's word timings so edit.py can
use one source and one words file.

    python3 production/assemble_takes.py --edl edl.json --output master.mp4 --words-output master.words.json

edl.json (paths relative to it):
    {"output": {"width": 1440, "height": 2560, "fps": 30, "crf": 16, "level_lufs": -23},
     "takes": [{"source": "A01.mov", "words": "words/A01.words.json", "keep": [[0.13, 4.42], [4.70, 6.62]]},
               {"source": "A02.mov", "words": "words/A02.words.json", "keep": [[0.0, 5.36]]}]}

"level_lufs" evens the voice across takes filmed at different distances or energy:
each take's kept speech is measured and gained to that integrated loudness (at most
8 dB either way; the receipt lists every gain). A take may set its own "gain_db".

Words keep their spoken text; a word belongs to the kept range where it starts
(or that holds most of it) and is clamped to that range. For the tightest cue
timing, re-transcribe the finished master as well. The --map-output receipt
records where every master second came from. Listen to every join before rendering.
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

FADE = 0.008
MAX_LEVEL_DB = 8.0


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def read_words(path):
    data = json.loads(Path(path).read_text())
    words = data if isinstance(data, list) else data.get("words") or [
        w for s in data.get("segments", []) for w in s.get("words", [])]
    return [{"word": str(w.get("word", w.get("text", ""))).strip(), "start": float(w["start"]), "end": float(w["end"])}
            for w in words if str(w.get("word", w.get("text", ""))).strip()]


def take_loudness(source, ranges):
    """Integrated loudness (LUFS) of a take's kept ranges, or None when too quiet to measure."""
    parts = "".join(f"[0:a]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS[p{i}];" for i, (a, b) in enumerate(ranges))
    joined = "".join(f"[p{i}]" for i in range(len(ranges)))
    graph = f"{parts}{joined}concat=n={len(ranges)}:v=0:a=1,ebur128[out]"
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-filter_complex", graph,
                             "-map", "[out]", "-f", "null", "-"], capture_output=True, text=True)
    found = re.findall(r"I:\s*(-?\d+\.\d) LUFS", result.stderr)
    value = float(found[-1]) if found else None
    return value if value is not None and value > -60 else None


def take_gains(edl, pieces):
    """dB gain per take: its own "gain_db", else toward output.level_lufs when set."""
    target = edl.get("output", {}).get("level_lufs")
    gains = {}
    for t, take in enumerate(edl["takes"]):
        if take.get("gain_db") is not None:
            gains[t] = {"gain_db": float(take["gain_db"]), "measured_lufs": None}
            continue
        if target is None:
            continue
        spans = [p for p in pieces if p["take"] == t]
        measured = take_loudness(spans[0]["source"], [(p["source_start"], p["source_end"]) for p in spans]) if spans else None
        gain = 0.0 if measured is None else max(-MAX_LEVEL_DB, min(MAX_LEVEL_DB, float(target) - measured))
        gains[t] = {"gain_db": round(gain, 2), "measured_lufs": measured}
    return gains


def plan(edl, base):
    fps = int(edl.get("output", {}).get("fps", 30))
    pieces, cursor = [], 0.0
    for t, take in enumerate(edl["takes"]):
        source = (base / take["source"]).resolve()
        if not source.is_file():
            raise ValueError(f"take {t}: missing source {source}")
        length = probe_duration(source)
        keep = take.get("keep") or [[0, length]]
        last_end = -1.0
        for k, (start, end) in enumerate(keep):
            start, end = float(start), float(end)
            if not 0 <= start < end <= length + 1e-3 or start < last_end:
                raise ValueError(f"take {t} keep {k} must be ordered, non-overlapping and inside the {length:.3f}s source")
            last_end = end
            frames = max(1, round((end - start) * fps))  # whole frames so picture and sound stay the same length
            seconds = frames / fps
            pieces.append({"take": t, "source": str(source), "source_start": round(start, 4),
                           "source_end": round(start + seconds, 4), "frames": frames,
                           "master_start": round(cursor, 4), "master_end": round(cursor + seconds, 4)})
            cursor += seconds
    return pieces, cursor


SLACK = 0.08  # one ASR frame: token timestamps land up to this late or early


def remap_words(edl, base, pieces):
    """Move each take's words onto the master clock; return (words, dropped).

    ASR word ends run long, so a word stays with the kept range where it starts
    (give or take one ASR frame), or with the range holding most of it. Words in
    cut time are dropped and listed, because a late timestamp at the end of a take
    can drop a word that was kept. Re-transcribing the master avoids that.
    """
    words, dropped = [], []
    for t, take in enumerate(edl["takes"]):
        if not take.get("words"):
            continue
        spans = [p for p in pieces if p["take"] == t]
        for w in read_words(base / take["words"]):
            length = max(w["end"] - w["start"], 1e-3)
            best, best_overlap = None, 0.0
            for p in spans:
                if p["source_start"] - SLACK <= w["start"] < p["source_end"] - .02:
                    best, best_overlap = p, length
                    break
                overlap = min(w["end"], p["source_end"]) - max(w["start"], p["source_start"])
                if overlap > best_overlap:
                    best, best_overlap = p, overlap
            if best is None or best_overlap < .5 * length:
                dropped.append({"take": Path(take["source"]).stem, "word": w["word"], "start": w["start"]})
                continue
            offset = best["master_start"] - best["source_start"]
            start = max(w["start"], best["source_start"]) + offset
            end = min(w["end"], best["source_end"]) + offset
            words.append({"word": w["word"], "start": round(start, 3), "end": round(max(end, start + .04), 3),
                          "take": Path(take["source"]).stem})
    return words, dropped


def assemble(edl_path, output, words_output, map_output=None):
    edl_path = Path(edl_path).resolve()
    edl = json.loads(edl_path.read_text())
    base = edl_path.parent
    out = edl.get("output", {})
    width, height, fps = int(out.get("width", 1080)), int(out.get("height", 1920)), int(out.get("fps", 30))
    crf = int(out.get("crf", 16))
    pieces, total = plan(edl, base)
    gains = take_gains(edl, pieces)
    args, filters = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"], []
    for i, p in enumerate(pieces):
        seconds = p["frames"] / fps
        gain = gains.get(p["take"], {}).get("gain_db", 0.0)
        level = f"volume={gain:.2f}dB," if gain else ""
        args += ["-ss", f"{p['source_start']:.4f}", "-t", f"{seconds + 0.2:.4f}", "-i", p["source"]]
        filters.append(f"[{i}:v]fps={fps},trim=end_frame={p['frames']},setpts=PTS-STARTPTS,"
                       f"scale={width}:{height}:flags=lanczos:force_original_aspect_ratio=increase,"
                       f"crop={width}:{height},setsar=1,format=yuv420p[v{i}]")
        filters.append(f"[{i}:a]atrim=end={seconds:.5f},asetpts=PTS-STARTPTS,aresample=48000,{level}"
                       f"aformat=sample_fmts=fltp:channel_layouts=stereo,afade=t=in:d={FADE},"
                       f"afade=t=out:st={max(0, seconds - FADE):.5f}:d={FADE}[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(pieces)))
    filters.append(f"{joined}concat=n={len(pieces)}:v=1:a=1[v][a]")
    args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-r", str(fps),
             "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
             "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", str(Path(output).resolve())]
    subprocess.run(args, check=True)
    words, dropped = remap_words(edl, base, pieces)
    Path(words_output).write_text(json.dumps({"words": words}, indent=1) + "\n")
    receipt = {"edl": str(edl_path), "output": str(Path(output).resolve()), "duration": round(total, 4),
               "fps": fps, "size": [width, height], "pieces": pieces, "words": len(words), "dropped_words": dropped,
               "levels": {Path(edl["takes"][t]["source"]).stem: g for t, g in sorted(gains.items())},
               "note": "cuts are frame-aligned with 8 ms audio fades; listen to every join"}
    if map_output:
        Path(map_output).write_text(json.dumps(receipt, indent=1) + "\n")
    measured = probe_duration(output)
    if abs(measured - total) > 1.5 / fps:
        raise RuntimeError(f"assembled duration {measured:.3f}s differs from the plan {total:.3f}s")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--edl", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--words-output", required=True)
    parser.add_argument("--map-output")
    args = parser.parse_args()
    receipt = assemble(args.edl, args.output, args.words_output, args.map_output)
    print(json.dumps({k: receipt[k] for k in ("output", "duration", "words")}, indent=1))
    if receipt["dropped_words"]:
        listed = ", ".join(f'{d["take"]}:{d["word"]}@{d["start"]:.2f}' for d in receipt["dropped_words"])
        print(f"dropped as cut (check the ones you kept, or re-transcribe the master): {listed}")


if __name__ == "__main__":
    main()
