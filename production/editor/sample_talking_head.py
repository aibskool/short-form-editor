#!/usr/bin/env python3
"""Build a short synthetic talking-head clip for the Kallaway pipeline smoke test.

The picture is an illustrated person, not a recording of anyone. Speech is espeak-ng.
Word timings match the file, including a few pauses longer than 0.1s so tightening has work to do.
"""
import argparse
import json
import math
import subprocess
import wave
from pathlib import Path

import numpy as np

SCRIPT = [
    "This", "one", "change", "makes", "a", "talking", "head", "feel", "edited.",
    "The", "old", "way", "no", "longer", "works.",
    "Start", "on", "the", "split", "and", "pop", "the", "grid.",
    "Then", "cut", "closer", "on", "the", "secret.",
    "Show", "a", "list,", "a", "chart,", "and", "the", "number.",
    "Comment", "VAULT", "to", "get", "the", "guide.",
]
# Pause after these source indexes so the raw take is not already gapless.
PAUSE_AFTER = {8, 14, 22, 29, 36}


def _trim(path):
    with wave.open(str(path), "rb") as handle:
        rate, count = handle.getframerate(), handle.getnframes()
        channels, width = handle.getnchannels(), handle.getsampwidth()
        raw = handle.readframes(count)
    if width != 2:
        raise RuntimeError("expected 16-bit espeak audio")
    samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, channels).mean(axis=1)
    loud = np.where(np.abs(samples) > 400)[0]
    if len(loud) == 0:
        return samples, rate
    start = max(0, int(loud[0]) - int(rate * 0.01))
    end = min(len(samples), int(loud[-1]) + int(rate * 0.02))
    return samples[start:end], rate


def synthesize(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    pieces, words, cursor = [], [], 0.0
    rate = None
    for index, token in enumerate(SCRIPT):
        wav = directory / f"word-{index:02d}.wav"
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", str(wav), token], check=True)
        samples, rate = _trim(wav)
        pieces.append(samples.astype(np.float32))
        words.append({"word": token.strip(",."), "start": round(cursor, 4),
                      "end": round(cursor + len(samples) / rate, 4)})
        cursor += len(samples) / rate
        if index in PAUSE_AFTER:
            gap = int(rate * 0.32)
            pieces.append(np.zeros(gap, dtype=np.float32))
            cursor += gap / rate
    audio = np.concatenate(pieces)
    peak = max(1.0, float(np.max(np.abs(audio))))
    pcm = (audio / peak * 28000).astype(np.int16)
    voice = directory / "voice.wav"
    with wave.open(str(voice), "wb") as handle:
        handle.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        handle.writeframes(pcm.tobytes())
    return voice, words, rate, pcm


def _ellipse(image, center, radii, color):
    cy, cx = center
    ry, rx = radii
    y0, y1 = max(0, cy - ry), min(image.shape[0], cy + ry)
    x0, x1 = max(0, cx - rx), min(image.shape[1], cx + rx)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1
    image[y0:y1, x0:x1][mask] = color


def render_video(voice, words, rate, pcm, output, fps=30):
    width, height = 1080, 1920
    frame_count = int(math.ceil(len(pcm) / rate * fps))
    base = np.zeros((height, width, 3), dtype=np.uint8)
    base[:] = (18, 20, 26)
    yy, xx = np.ogrid[:height, :width]
    warm = np.exp(-((xx - 260) ** 2) / (2 * 380 ** 2) - ((yy - 760) ** 2) / (2 * 620 ** 2))
    cyan = np.exp(-((xx - 900) ** 2) / (2 * 160 ** 2) - ((yy - 700) ** 2) / (2 * 480 ** 2))
    base = np.clip(base + warm[..., None] * np.array([70, 36, 12]) + cyan[..., None] * np.array([8, 36, 58]), 0, 255).astype(np.uint8)
    closed = base.copy()
    _ellipse(closed, (1180, 540), (760, 340), (22, 24, 30))
    _ellipse(closed, (980, 540), (180, 90), (196, 156, 126))
    _ellipse(closed, (640, 540), (230, 190), (214, 170, 142))
    _ellipse(closed, (500, 540), (150, 200), (32, 34, 38))
    _ellipse(closed, (600, 470), (16, 22), (40, 32, 28))
    _ellipse(closed, (600, 610), (16, 22), (40, 32, 28))
    opened = closed.copy()
    _ellipse(opened, (760, 540), (28, 46), (70, 36, 36))
    hop = rate // fps
    envelope = []
    for frame in range(frame_count):
        chunk = pcm[frame * hop:(frame + 1) * hop]
        envelope.append(float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))) if len(chunk) else 0.0)
    loud = max(envelope) or 1
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-i", str(voice), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    for level in envelope:
        mix = min(1.0, level / (loud * 0.45))
        frame = (closed.astype(np.float32) * (1 - mix) + opened.astype(np.float32) * mix).astype(np.uint8)
        process.stdin.write(frame.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed while muxing the sample talking head")
    return frame_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--words", required=True)
    args = parser.parse_args()
    output, words_path = Path(args.output), Path(args.words)
    voice, words, rate, pcm = synthesize(output.parent / "sample-speech")
    render_video(voice, words, rate, pcm, output)
    words_path.write_text(json.dumps(words, indent=2) + "\n")
    print(json.dumps({"output": str(output), "words": len(words), "seconds": words[-1]["end"]}))


if __name__ == "__main__":
    main()
