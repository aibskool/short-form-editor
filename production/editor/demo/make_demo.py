#!/usr/bin/env python3
"""Generate the motion-system demo inputs, and optionally build, check and render them.

The demo exercises every motion component without private footage. Its presenter is a
flat illustrated stand-in whose mouth follows a synthetic word map, with a speech-shaped
noise track at voice level so sound-effect levels are realistic. It is not a person, a
voice, or delivery material, and the two app screens in assets/ are drawn placeholders.

    python3 make_demo.py                 # writes work/<name>.mp4 and work/<name>.words.json
    python3 make_demo.py --render        # also builds, runs hyperframes check, renders drafts

Requires numpy and ffmpeg (both already needed by the editor).
"""
import argparse
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EDITOR = HERE.parent
W, H, FPS, RATE = 720, 1280, 30, 48000
TAIL = 0.5

SCRIPTS = {
    "stage-explainer": (
        "Most people chasing their first AI client are doing it backwards. They build the automation first, "
        "then go looking for someone to buy it. Flip it. Find one business with a painful manual task. "
        "Map the workflow: new lead, Claude agent, booked call. Then show them a thirty second demo. "
        "The demo does the selling for you. Comment AGENT and I'll send you the exact prompt."),
    "receipts-first": (
        "Claude plus one job equals every lead answered. Here's the prompt. Read every inbound lead, score it, "
        "and reply in under a minute. Right now you answer each one by hand. Say that's forty leads a week. "
        "The agent answers all forty, even while you sleep. The old way costs you evenings. "
        "The new way costs you one setup. Five tools, one workflow, and it runs every day without you. "
        "Comment FLOW and I'll send you the setup."),
}


def word_map(script):
    """Deterministic word timings: longer words take longer; punctuation adds pauses."""
    t, words = 0.25, []
    for token in script.split():
        core = re.sub(r"[^A-Za-z0-9']", "", token)
        length = 0.13 + 0.055 * len(core)
        words.append({"word": token, "start": round(t, 3), "end": round(t + length, 3)})
        t += length + 0.04
        if token.endswith((".", "?", "!")):
            t += 0.32
        elif token.endswith((",", ":")):
            t += 0.14
    return words


def speech_envelope(words, seconds, rate):
    """0-1 loudness contour: one soft hump per syllable-ish unit inside each word."""
    env = np.zeros(int(seconds * rate), dtype=np.float32)
    for word in words:
        a, b = int(word["start"] * rate), int(word["end"] * rate)
        n = max(1, b - a)
        syllables = max(1, round(len(re.sub(r"[^A-Za-z]", "", word["word"])) / 3))
        x = np.linspace(0, 1, n, endpoint=False)
        hump = np.sin(np.pi * x) ** 0.5
        pulses = 0.55 + 0.45 * np.abs(np.sin(np.pi * syllables * x))
        env[a:a + n] = np.maximum(env[a:a + n], (hump * pulses)[:len(env) - a])
    return env


def speech_track(words, seconds, seed):
    """Band-limited noise plus a low buzz, gated by the word envelope, around -20 dBFS RMS."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    env = speech_envelope(words, seconds, RATE)
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    shape = np.exp(-(np.log(np.maximum(freqs, 20) / 850) ** 2) / (2 * .75 ** 2))
    noise = np.fft.irfft(np.fft.rfft(rng.standard_normal(n)) * shape, n)
    t = np.arange(n) / RATE
    f0 = 118 + 14 * np.sin(2 * np.pi * .6 * t) + 6 * np.sin(2 * np.pi * 3.1 * t)
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    buzz = sum(np.sin(k * phase) / k for k in range(1, 14))
    buzz = np.fft.irfft(np.fft.rfft(buzz) * np.exp(-(np.log(np.maximum(freqs, 20) / 600) ** 2) / (2 * .9 ** 2)), n)
    signal = (.55 * noise / noise.std() + .6 * buzz / buzz.std()) * env
    speaking = env > .05
    signal *= 10 ** (-20 / 20) / max(1e-9, float(np.sqrt(np.mean(signal[speaking] ** 2))))
    return np.clip(signal, -.98, .98), env


def ellipse(xx, yy, cx, cy, rx, ry, soft=1.4):
    r = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    return np.clip((1 - r) * min(rx, ry) / soft, 0, 1)


def paint(rgb, alpha, mask, color):
    color = np.asarray(color, dtype=np.float32) / 255
    rgb[:] = rgb * (1 - mask[..., None]) + color * mask[..., None]
    alpha[:] = np.maximum(alpha, mask)


def background():
    s = W / 1080
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    frac = yy / H
    img = np.stack([34 - 18 * frac, 38 - 20 * frac, 40 - 20 * frac], -1) / 255
    rng = np.random.default_rng(3)
    for _ in range(14):
        x, y = rng.uniform(0, W), rng.uniform(80, 900) * s
        radius = rng.uniform(60, 130) * s
        color = np.array([rng.uniform(120, 255), rng.uniform(80, 170), rng.uniform(40, 90)]) / 255
        glow = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * radius ** 2))[..., None]
        img = img + glow * color * .22
    img[int(820 * s):int(842 * s)] = np.array([52, 44, 38]) / 255
    img[int(700 * s):int(820 * s), int(60 * s):int(180 * s)] = np.array([70, 74, 72]) / 255
    img[int(640 * s):int(820 * s), int(860 * s):int(960 * s)] = np.array([60, 56, 52]) / 255
    return np.clip(img, 0, 1).astype(np.float32)


def presenter_layer(pad):
    """The static figure (shirt, neck, head, cap) on a padded RGBA canvas."""
    s = W / 1080
    hh, ww = H + 2 * pad, W + 2 * pad
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    cx, cy = ww / 2, pad + 700 * s
    rgb = np.zeros((hh, ww, 3), dtype=np.float32)
    alpha = np.zeros((hh, ww), dtype=np.float32)
    paint(rgb, alpha, ellipse(xx, yy, cx, cy + 965 * s, 470 * s, 535 * s), (18, 20, 22))
    neck = ((abs(xx - cx) < (95 - 15 * np.clip((yy - cy - 150 * s) / (320 * s), 0, 1)) * s)
            & (yy > cy + 150 * s) & (yy < cy + 470 * s)).astype(np.float32)
    paint(rgb, alpha, neck, (160, 112, 86))
    paint(rgb, alpha, ellipse(xx, yy, cx, cy, 165 * s, 215 * s), (196, 142, 110))
    paint(rgb, alpha, ellipse(xx, yy, cx, cy + 72 * s, 150 * s, 143 * s), (186, 132, 102))
    cap = ellipse(xx, yy, cx, cy - 105 * s, 178 * s, 145 * s) * (yy < cy - 105 * s)
    paint(rgb, alpha, cap, (22, 24, 26))
    brim = ((xx > cx - 190 * s) & (xx < cx + 250 * s) & (yy > cy - 110 * s) & (yy < cy - 92 * s)).astype(np.float32)
    paint(rgb, alpha, brim, (22, 24, 26))
    return rgb, alpha, (cx - pad, cy - pad)


def face(frame, cx, cy, t, openness, blink):
    """Eyes, brows and a mouth whose opening follows the speech envelope."""
    s = W / 1080
    x0, y0 = int(cx - 120 * s), int(cy - 80 * s)
    x1, y1 = int(cx + 120 * s), int(cy + 150 * s)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    region = frame[y0:y1, x0:x1]
    alpha = np.zeros(region.shape[:2], dtype=np.float32)
    for ex in (-62, 62):
        ex = cx + ex * s
        if blink:
            mask = ((abs(xx - ex) < 20 * s) & (abs(yy - (cy - 10 * s)) < 3 * s)).astype(np.float32)
        else:
            mask = ellipse(xx, yy, ex, cy - 10 * s, 16 * s, 12 * s)
        paint(region, alpha, mask, (35, 28, 26))
        brow = ((abs(xx - ex) < 30 * s) & (abs(yy - (cy - 55 * s) + (xx - ex) * .1) < 4.5 * s)).astype(np.float32)
        paint(region, alpha, brow, (50, 36, 30))
    height = (6 + 30 * openness) * s
    paint(region, alpha, ellipse(xx, yy, cx, cy + 96 * s + height / 2, 44 * s, max(3 * s, height / 2 + 2 * s)), (92, 42, 40))


def make_clip(name, script, work):
    words = word_map(script)
    seconds = round(words[-1]["end"] + TAIL, 3)
    (work / f"{name}.words.json").write_text(json.dumps({"words": words}, indent=1) + "\n")
    audio, env = speech_track(words, seconds, seed=len(name))
    wav = work / f"{name}.speech.wav"
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((audio * 32767).astype("<i2").tobytes())
    bg = background()
    pad = 32
    rgb, alpha, (hx, hy) = presenter_layer(pad)
    target = work / f"{name}.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", str(target)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    per_frame = RATE // FPS
    for f in range(int(math.ceil(seconds * FPS))):
        t = f / FPS
        dx = int(round(10 * math.sin(t * .9)))
        dy = int(round(8 * math.sin(t * 2.1) + 4 * math.sin(t * 5.3)))
        layer = slice(pad - dy, pad - dy + H), slice(pad - dx, pad - dx + W)
        a = alpha[layer][..., None]
        frame = bg * (1 - a) + rgb[layer] * a
        openness = float(env[f * per_frame:(f + 1) * per_frame].mean()) if f * per_frame < len(env) else 0.0
        face(frame, hx + dx, hy + dy, t, openness, blink=(f % 110) < 4)
        process.stdin.write((np.clip(frame, 0, 1) * 255).astype(np.uint8).tobytes())
    process.stdin.close()
    if process.wait():
        raise SystemExit(f"ffmpeg failed while writing {target}")
    wav.unlink()
    return target, seconds


def run(args):
    print("$", " ".join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=sorted(SCRIPTS), help="generate one demo")
    parser.add_argument("--render", action="store_true", help="build, check and render draft MP4s into work/")
    parser.add_argument("--quality", default="draft", choices=["draft", "standard", "high"])
    parser.add_argument("--workers", default="2")
    args = parser.parse_args()
    work = HERE / "work"
    work.mkdir(exist_ok=True)
    for name, script in SCRIPTS.items():
        if args.only and name != args.only:
            continue
        clip, seconds = make_clip(name, script, work)
        print(json.dumps({"demo": name, "clip": str(clip), "seconds": seconds}))
        if args.render:
            project = work / name
            run([sys.executable, EDITOR / "edit.py", "build", "--spec", HERE / f"{name}.json", "--project", project])
            run([sys.executable, EDITOR / "hyperframes_cli.py", "check", project])
            run([sys.executable, EDITOR / "edit.py", "render", "--project", project, "--output",
                 work / f"{name}-render.mp4", "--quality", args.quality, "--workers", args.workers])


if __name__ == "__main__":
    main()
