#!/usr/bin/env python3
"""Track Brandon's face through a video (source take or finished render).

Writes normalized face boxes over time. The planner uses a source track to place
graphics beside the face and to follow it; the acceptance review runs it on the
encoded reel to measure how long Brandon is on screen at full size versus shrunk
into a band or gone.

    python3 production/editor/track_face.py reel.mp4 --out reel.face.json [--fps 5]

Output: {"video", "fps", "width", "height", "samples": [{"t", "face": [x, y, w, h] | null}]}
with the box in percent of the frame. Uses OpenCV's bundled Haar cascade, so it runs
offline; boxes are smoothed and short gaps are filled.
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - reported to the caller
    cv2 = None

SAMPLE_W, SAMPLE_H = 360, 640


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"]), float(data["format"]["duration"])


def frames(path, fps, start=0.0, end=None):
    """Grayscale frames at a fixed rate, letterboxed to a 9:16 sample canvas."""
    args = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(path)]
    if end is not None:
        args += ["-t", f"{max(.05, end - start):.3f}"]
    args += ["-vf", f"fps={fps},scale={SAMPLE_W}:{SAMPLE_H}:force_original_aspect_ratio=decrease,"
             f"pad={SAMPLE_W}:{SAMPLE_H}:(ow-iw)/2:(oh-ih)/2,format=gray", "-f", "rawvideo", "-"]
    size = SAMPLE_W * SAMPLE_H
    index = 0
    with subprocess.Popen(args, stdout=subprocess.PIPE) as proc:
        while True:
            chunk = proc.stdout.read(size)
            if len(chunk) < size:
                break
            yield start + index / fps, np.frombuffer(chunk, dtype=np.uint8).reshape(SAMPLE_H, SAMPLE_W)
            index += 1


def detector():
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is required: pip install opencv-python-headless")
    cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    if cascade.empty():
        raise RuntimeError("OpenCV Haar cascade not found")
    return cascade


def detect(cascade, gray):
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=6, minSize=(int(SAMPLE_H * .045),) * 2)
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return [100 * x / SAMPLE_W, 100 * y / SAMPLE_H, 100 * w / SAMPLE_W, 100 * h / SAMPLE_H]


def smooth(samples, gap=3):
    """Median-smooth boxes and bridge gaps of up to ``gap`` samples."""
    boxes = [s["face"] for s in samples]
    out = [list(b) if b else None for b in boxes]
    for i in range(len(boxes)):
        window = [b for b in boxes[max(0, i - 2):i + 3] if b]
        if boxes[i] and len(window) >= 3:
            out[i] = [float(np.median([b[k] for b in window])) for k in range(4)]
    i = 0
    while i < len(out):
        if out[i] is None:
            j = i
            while j < len(out) and out[j] is None:
                j += 1
            if 0 < i and j < len(out) and j - i <= gap:
                a, b = out[i - 1], out[j]
                for k in range(i, j):
                    f = (k - i + 1) / (j - i + 1)
                    out[k] = [a[m] + (b[m] - a[m]) * f for m in range(4)]
            i = j
        else:
            i += 1
    return [{"t": s["t"], "face": None if b is None else [round(v, 2) for v in b]} for s, b in zip(samples, out)]


def track(path, fps=5.0, start=0.0, end=None):
    width, height, duration = probe(path)
    cascade = detector()
    samples = [{"t": round(t, 3), "face": detect(cascade, gray)} for t, gray in frames(path, fps, start, end)]
    return {"video": str(path), "fps": fps, "width": width, "height": height, "duration": duration,
            "samples": smooth(samples)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float)
    a = ap.parse_args()
    result = track(a.video, a.fps, a.start, a.end)
    a.out.write_text(json.dumps(result, indent=1) + "\n")
    found = sum(1 for s in result["samples"] if s["face"])
    print(json.dumps({"out": str(a.out), "samples": len(result["samples"]), "with_face": found}))


if __name__ == "__main__":
    main()
