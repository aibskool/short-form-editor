#!/usr/bin/env python3
"""Brandon Meaux new-style preset.

Full-face talking head, hard punch-ins, short phrase captions, neon-green
emphasis, and a sparse pass over the pack SFX. The Kallaway split-screen
preset is a separate path and is not used here.

Brandon's own guidelines override the editing bible wherever they differ:
natural pauses stay, routine cuts are silent, captions are 3-6 word
phrases, and most moments have no sound. Captions still sit at y 1462,
on-screen figures match the spoken words, and green is #42FF40.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
PACK = HERE / "sfx" / "brandon_pack"
FPS = 30
W, H = 1080, 1920
GREEN = (0x42, 0xFF, 0x40, 255)
GREEN_HEX = "#42FF40"
CAPTION_BOTTOM = 1532 - 70  # locked lift, C-15
CAPTION_H = 65
PUNCH = 1.12  # 12% crop, inside the 8-15% punch-in
SR = 48000

APPROVED = {
    "demo", "claude", "listing", "skool", "ugc", "agent", "client",
    "newsletter", "realtor", "dropship", "notion", "website", "restaurant",
    "plan", "sites", "library", "retainer", "coloring", "local", "deals",
    "framework", "headshots", "paid", "zip", "etsy", "dub", "gta6", "astra",
    "guide",
}

# Bible start gains (section 11.2). Files are otherwise untouched.
# v2 levels sit on the v1 starts: Wrong Answer -8 dB, Pop 6 -6 dB,
# shutters and ticks +5 dB so they read on a phone speaker.
GAINS = {
    "pop": -4.5,
    "thump": -12.0,
    "negative": -9.8,
    "tick": 4.8,
    "shutter": 3.6,
    "landing": -8.3,
    "ding": -7.0,
    "impact": -5.0,
}
HERO_GLYPH_TOP = 1044  # green word top, inside y 1010-1080
SFX = {
    "pop": "27 Pops, Zaps & Switches/Pop 1.mp3",
    "thump": "27 Pops, Zaps & Switches/Pop 6.mp3",
    "negative": "00 Viral Reels Essentials/Wrong Answer.mp3",
    "tick": "24 UI Sounds/Ui Sound 12.mp3",
    "shutter": "34 Camera & Shutter/Camera 5.mp3",
    "landing": "35 Money & Cash/Cash Register Ka Ching.mp3",
    "ding": "28 Dings, Bells & Chimes/Ding Single 1.mp3",
    "impact": "00 Viral Reels Essentials/Dark Impact.mp3",
}
# Seconds into the file where the transient peaks, so the hit can sit on the frame.
PEAK_AT = {"pop": 0.036, "thump": 0.154, "tick": 0.001, "shutter": 0.128, "landing": 0.411, "impact": 0.251, "ding": 0.033, "negative": 0.259}
TRIM_AT = {"thump": 0.40, "impact": 0.55}


def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def ff(*args, **kw):
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args], check=True, **kw)


def qframe(t):
    return round(float(t) * FPS) / FPS


def norm_word(text):
    return text.lower().strip(".,!?;:\"'")


def caption_text(text):
    return text.strip().strip(".,!?;:\"").upper()


def load_words(path):
    data = json.loads(Path(path).read_text())
    words = data["words"] if isinstance(data, dict) else data
    return [{"word": w["word"], "start": float(w["start"]), "end": float(w["end"])} for w in words]


def find_word(words, text, occ=0):
    want = norm_word(text)
    seen = 0
    for i, w in enumerate(words):
        if norm_word(w["word"]) == want:
            if seen == occ:
                return i
            seen += 1
    raise KeyError(f"{text!r} occurrence {occ} not in transcript")


@dataclass
class Span:
    out: float
    src: float | None
    dur: float

    @property
    def out_end(self):
        return self.out + self.dur


def energy_runs(y, sr=SR):
    """Speech runs using the QA tool's rule: 10 ms hops, threshold p95-35 dB, holes under 30 ms closed."""
    hop = int(sr * 0.01)
    n = len(y) // hop
    rms = 20 * np.log10(np.sqrt((y[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    speech = rms > (np.percentile(rms, 95) - 35)
    runs = []
    s0 = None
    for i, on in enumerate(speech):
        if on and s0 is None:
            s0 = i
        if not on and s0 is not None:
            runs.append([s0, i])
            s0 = None
    if s0 is not None:
        runs.append([s0, n])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < 3:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    merged = [m for m in merged if m[1] - m[0] >= 4]
    return [(a / 100, b / 100) for a, b in merged], rms


def build_spans(words, audio, sr=SR):
    """Keep each spoken word, its consonant tail, and the natural pause.

    Connected thoughts keep their real gap. A pause longer than 0.60 s is
    dead air and comes back to about 0.32 s, or about 0.48 s after a
    sentence. The kept air is source room tone, never a silent sample,
    except for two frames after the last word.
    """
    _runs, rms = energy_runs(audio, sr)
    if len(rms) == 0:
        raise RuntimeError("no speech in the source")
    gate = float(np.percentile(rms, 95) - 35)
    keeps = []
    for i, w in enumerate(words):
        nxt = words[i + 1]["start"] if i + 1 < len(words) else w["end"] + 1.0
        prev_end = words[i - 1]["end"] + 0.05 if i else 0.0
        floor = max(prev_end, w["start"] - 0.12)
        t = w["start"]
        while t > floor + 0.01:
            hop = int((t - 0.01) * 100)
            if hop < 0 or hop >= len(rms) or rms[hop] < gate:
                break
            t -= 0.01
        a = max(0.0, t - 0.02)
        # A timestamp can start before the attack. Skip that dead air and
        # keep about 30 ms so the consonant is still there.
        onset = w["start"]
        limit = min(w["end"] - 0.04, w["start"] + 0.90)
        while onset < limit:
            hop = int(onset * 100)
            if 0 <= hop < len(rms) and rms[hop] >= gate:
                break
            onset += 0.01
        if onset > w["start"] + 0.06:
            a = max(0.0, onset - 0.03)
        b = w["end"] + 0.08
        cap = min(w["end"] + 0.18, nxt - 0.04)
        t = w["end"]
        while t < cap:
            hop = int(t * 100)
            if hop >= len(rms) or rms[hop] < gate:
                break
            t += 0.01
            b = t
        b = min(max(b, w["end"] + 0.04), max(cap, w["end"] + 0.04))
        # And a timestamp can run on after the syllable. Stop just after
        # the last loud hop when the next word is not already connected.
        if nxt - w["end"] > 0.18:
            last = None
            tt = a
            while tt <= min(w["end"] + 0.02, nxt):
                hop = int(tt * 100)
                if 0 <= hop < len(rms) and rms[hop] >= gate:
                    last = tt
                tt += 0.01
            if last is not None:
                b = min(b, last + 0.06)
        # A tight join stays one piece so the consonant and the breath are not cut.
        if nxt - w["end"] <= 0.12:
            b = max(b, min(nxt, w["end"] + 0.12))
        if keeps and a <= keeps[-1][1] + 0.08:
            keeps[-1][1] = max(keeps[-1][1], b)
        else:
            keeps.append([a, b])
    pieces = []
    for a, b in keeps:
        if b - a < 0.02:
            continue
        qa = round(a * FPS) / FPS
        qb = round(max(b, a + 1 / FPS) * FPS) / FPS
        if pieces and qa <= pieces[-1][1] + 1 / FPS:
            pieces[-1][1] = max(pieces[-1][1], qb)
        else:
            pieces.append([qa, qb])

    def _sentence(src_t):
        best = None
        for w in words:
            if w["end"] <= src_t + 0.04:
                best = w
        return bool(best and str(best["word"]).rstrip().endswith((".", "!", "?")))

    spans = []
    out = 0.0
    for i, (a, b) in enumerate(pieces):
        dur = max(1 / FPS, round((b - a) * FPS) / FPS)
        spans.append(Span(out, a, dur))
        out += dur
        if i + 1 >= len(pieces):
            break
        nxt = pieces[i + 1][0]
        gap = nxt - b
        if gap <= 1 / FPS:
            continue
        if gap <= 0.60:
            tone_end = nxt
        else:
            keep = 0.48 if _sentence(b) else 0.32
            tone_end = min(nxt, round((b + keep) * FPS) / FPS)
        tone_dur = round((tone_end - b) * FPS) / FPS
        if tone_dur < 1 / FPS:
            continue
        spans.append(Span(out, b, tone_dur))
        out += tone_dur
    # Hard out. Two silent frames, plus the 10 ms fade on the last speech piece.
    spans.append(Span(out, None, 2 / FPS))
    out += 2 / FPS
    total = round(out * FPS) / FPS
    spans[-1].dur += total - out

    def map_src(t):
        cursor = 0.0
        for s in spans:
            if s.src is None:
                cursor = s.out_end
                continue
            if s.src <= t <= s.src + s.dur + 0.03:
                return s.out + min(s.dur, max(0.0, t - s.src))
            if t < s.src:
                return s.out
            cursor = s.out_end
        return cursor

    for k, w in enumerate(words):
        w["idx"] = k
        w["out"] = map_src(w["start"])
        w["out_end"] = map_src(w["end"])
        if w["out_end"] < w["out"]:
            w["out_end"] = w["out"]
    return spans, out


def build_phrases(words):
    """Group every spoken word into a 3-6 word caption. Nothing is dropped."""
    chunks = []
    cur = []
    for i, w in enumerate(words):
        cur.append(w)
        punct = str(w["word"]).rstrip().endswith((".", "!", "?"))
        pause = False
        if i + 1 < len(words):
            pause = words[i + 1]["out"] - w["out_end"] >= 0.28
        if punct or pause or len(cur) >= 6:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    merged = []
    for ch in chunks:
        if merged and len(ch) < 3 and len(merged[-1]) + len(ch) <= 6:
            merged[-1].extend(ch)
        elif merged and len(merged[-1]) < 3 and len(merged[-1]) + len(ch) <= 6:
            merged[-1].extend(ch)
        else:
            merged.append(list(ch))
    # A 1- or 2-word chunk stuck between full lines borrows a word so every
    # caption stays in the 3-6 word range.
    guard = 0
    while any(len(ch) < 3 for ch in merged) and guard < 12:
        guard += 1
        for i, ch in enumerate(merged):
            if len(ch) >= 3:
                continue
            need = 3 - len(ch)
            left = i - 1 if i > 0 else None
            right = i + 1 if i + 1 < len(merged) else None
            if left is not None and len(merged[left]) - need >= 3:
                merged[i] = merged[left][-need:] + ch
                merged[left] = merged[left][:-need]
            elif right is not None and len(merged[right]) - need >= 3:
                merged[i] = ch + merged[right][:need]
                merged[right] = merged[right][need:]
            elif left is not None:
                blob = merged[left] + ch
                cut = min(max(len(blob) // 2, 3), len(blob) - 3) if len(blob) > 6 else len(blob)
                if len(blob) <= 6:
                    merged[left] = blob
                    del merged[i]
                else:
                    merged[left] = blob[:cut]
                    merged[i] = blob[cut:]
            elif right is not None:
                blob = ch + merged[right]
                cut = min(max(len(blob) // 2, 3), len(blob) - 3) if len(blob) > 6 else len(blob)
                if len(blob) <= 6:
                    merged[right] = blob
                    del merged[i]
                else:
                    merged[i] = blob[:cut]
                    merged[right] = blob[cut:]
            break
    phrases = []
    for ch in merged:
        text = " ".join(caption_text(w["word"]) for w in ch if caption_text(w["word"]))
        phrases.append({
            "words": ch,
            "t0": ch[0]["out"],
            "t1": ch[-1]["out_end"],
            "text": text,
        })
    return phrases


def _pick_cut(cands, jumps, target):
    """Prefer a pause boundary so the cut is visible even at the same scale."""
    near = [j for j in jumps if cands and min(cands) - 0.05 <= j <= max(cands) + 0.05]
    pool = near or cands
    return min(pool, key=lambda w: abs(w - target))


def _region_cuts(t0, t1, word_times, opening, jumps):
    cuts = [t0]
    if opening and t0 < 0.05:
        cands = [w for w in word_times if 1.55 <= w <= 2.70]
        if cands:
            cuts.append(_pick_cut(cands, jumps, 2.15))
    # Pause boundaries are visible at the same scale, so use them as cuts.
    for j in jumps:
        if cuts[-1] + 1.00 <= j <= t1 - 1.00:
            cuts.append(j)
    cuts = sorted(set(round(c, 3) for c in cuts))
    # Then break anything still longer than 3.2 s on a word.
    guard = 0
    while guard < 12:
        guard += 1
        nxt = None
        for a, b in zip(cuts, cuts[1:] + [t1]):
            if b - a > 2.20:
                target = a + 1.55
                cands = [w for w in word_times if a + 1.05 <= w <= min(a + 2.60, b - 0.90)]
                if not cands:
                    cands = [w for w in word_times if a + 0.80 <= w <= b - 0.70]
                if cands:
                    nxt = _pick_cut(cands, jumps, target)
                break
        if nxt is None or any(abs(nxt - c) < 0.2 for c in cuts):
            break
        cuts.append(nxt)
        cuts = sorted(cuts)
    if opening and t0 < 0.05:
        cuts = [c for c in cuts if c <= 0.05 or c >= 1.50]
    if not cuts or cuts[-1] != t1:
        if cuts and t1 - cuts[-1] < 0.85:
            cuts[-1] = t1
        else:
            cuts.append(t1)
    cuts = sorted(set(cuts))
    return list(zip(cuts, cuts[1:]))


@dataclass
class Shot:
    t0: float
    t1: float
    kind: str  # face, phone, bleed, mg
    scale: float = 1.0
    push: float = 0.0
    bw: bool = False
    flash: bool = False
    banner_off: bool = False
    plate: str = ""
    src_jump: bool = False

    @property
    def dur(self):
        return self.t1 - self.t0

    @property
    def label(self):
        if self.kind == "face":
            return "PUNCH" if self.scale >= 1.12 else "F"
        if self.kind == "mg":
            return "MG"
        return "SCR"


def _face_shots(t0, t1, word_times, jump_times, opening):
    shots = []
    for a, b in _region_cuts(t0, t1, word_times, opening and t0 < 0.05, jump_times):
        jump = any(abs(a - j) < 0.04 for j in jump_times)
        shots.append(Shot(a, b, "face", src_jump=jump))
    return shots


def _apply_scales(shots):
    """Toggle punch scale on continuous face cuts. Keep scale across a real jump."""
    scale = 1.0
    prev_face = False
    for s in shots:
        if s.kind != "face":
            prev_face = False
            scale = 1.0
            continue
        if prev_face and not s.src_jump:
            scale = PUNCH if scale < 1.06 else 1.0
        s.scale = scale
        s.push = 0.0
        prev_face = True

    def _pairs():
        out = []
        for i in range(1, len(shots)):
            a, b = shots[i - 1], shots[i]
            if a.kind == "face" and b.kind == "face":
                out.append(i)
        return out

    def _share():
        pairs = _pairs()
        if not pairs:
            return 0.0
        chg = 0
        for i in pairs:
            r = shots[i].scale / shots[i - 1].scale
            if r >= 1.08 or r <= 1 / 1.08:
                chg += 1
        return chg / len(pairs)

    # Jump cuts stay visible without a scale change. Use them to land near 50%.
    for i in _pairs():
        if _share() <= 0.62:
            break
        s = shots[i]
        if not (s.src_jump or s.flash or s.bw):
            continue
        prev = shots[i - 1]
        if abs(s.scale - prev.scale) >= 0.10:
            s.scale = prev.scale
            s.push = 0.0
    # A punch on every cut reads as constant reframing. Leave some cuts alone.
    for i in _pairs():
        if _share() <= 0.62:
            break
        if i % 2:
            continue
        s = shots[i]
        prev = shots[i - 1]
        if s.bw or prev.bw:
            continue
        if abs(s.scale - prev.scale) >= 0.10:
            s.scale = prev.scale
            s.push = 0.0
    for i in _pairs():
        if _share() >= 0.40:
            break
        s = shots[i]
        prev = shots[i - 1]
        if abs(s.scale - prev.scale) < 0.10:
            s.scale = PUNCH if prev.scale < 1.06 else 1.0
            s.push = 0.0
    return shots


def _mark_flashes(shots):
    """Pick the banner-off cut. No white flash."""
    for s in shots:
        s.flash = False
        s.banner_off = False
    starts = [s for s in shots if 4.55 <= s.t0 <= 8.30]
    if starts:
        min(starts, key=lambda s: abs(s.t0 - 4.8)).banner_off = True
    return shots


def _title_off_time(shots, fallback=6.0):
    marked = [s.t0 for s in shots if s.banner_off]
    if marked:
        return marked[0]
    cands = [s.t0 for s in shots if 4.55 <= s.t0 <= 8.30]
    return cands[0] if cands else fallback


def _clamp_inserts(raw, duration):
    """Place inserts on word times, keep a face gap, and end them before the CTA.

    Each insert stays at least 3.05 s so the shot p90 lands in range. Later
    inserts reserve that room instead of getting squeezed to a sliver.
    """
    placed = []
    limit = duration * 0.76
    gap = 0.90
    min_dur = 3.40
    n = len(raw)
    for i, spec in enumerate(raw):
        remaining = n - i - 1
        reserve = remaining * (min_dur + gap)
        latest_end = limit - reserve
        dur = min(spec["dur"], 4.3)
        t = spec["t"]
        if placed and t < placed[-1]["t1"] + gap:
            t = placed[-1]["t1"] + gap
        if t + dur > latest_end:
            dur = latest_end - t
        if dur < min_dur:
            t = latest_end - min_dur
            if placed and t < placed[-1]["t1"] + gap:
                t = placed[-1]["t1"] + gap
            dur = min(min_dur, latest_end - t)
        if dur < 2.8 or t >= limit:
            continue
        t = qframe(max(0.0, t))
        t1 = qframe(t + dur)
        placed.append({**spec, "t": t, "t1": t1, "dur": t1 - t})
    return placed


def _ensure_title_cut(shots, word_times):
    """The banner has to leave on a cut between 4.55 and 5.4 s."""
    if any(4.55 <= s.t0 <= 5.40 for s in shots):
        return shots
    for i, s in enumerate(shots):
        if s.kind != "face" or not (s.t0 < 4.75 < s.t1):
            continue
        cands = [w for w in word_times if max(s.t0 + 0.45, 4.55) <= w <= min(s.t1 - 0.45, 5.35)]
        cut = min(cands, key=lambda w: abs(w - 4.75)) if cands else 4.75
        if cut <= s.t0 + 0.4 or cut >= s.t1 - 0.4:
            cut = min(s.t1 - 0.5, max(s.t0 + 0.5, 4.75))
        left = Shot(s.t0, cut, "face", src_jump=s.src_jump)
        right = Shot(cut, s.t1, "face", src_jump=True)
        return shots[:i] + [left, right] + shots[i + 1:]
    return shots


def _ensure_three_long_shots(shots):
    """p90 needs three shots of at least 3.05 s. Merge one face pair if we are short."""
    def nlong(items):
        return sum(1 for s in items if s.dur >= 3.05)

    if nlong(shots) >= 3:
        return shots
    best = None
    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]
        if a.kind != "face" or b.kind != "face":
            continue
        if a.t0 < 1.2:
            continue  # leave the opening cut where it is
        if a.dur + b.dur < 3.05:
            continue
        if best is None or a.dur + b.dur < best[0]:
            best = (a.dur + b.dur, i)
    if best is None:
        return shots
    i = best[1]
    a, b = shots[i], shots[i + 1]
    merged = Shot(a.t0, b.t1, "face", src_jump=a.src_jump)
    return shots[:i] + [merged] + shots[i + 2:]


def _source_jumps(spans):
    """Output times where the picture leaves a hole in the source."""
    jumps = []
    prev = None
    for s in spans:
        if s.src is None:
            if s.out > 0.05:
                jumps.append(qframe(s.out))
            prev = None
            continue
        if prev is not None and s.src > prev + 0.12:
            jumps.append(qframe(s.out))
        prev = s.src + s.dur
    return jumps


def build_shots(words, spans, inserts, bw_word=None):
    duration = spans[-1].out_end
    word_times = sorted({qframe(w["out"]) for w in words if 0.4 < w["out"] < duration - 0.4})
    jump_times = _source_jumps(spans)
    timeline = []
    cursor = 0.0
    opening = True
    for ins in inserts:
        if ins["t"] > cursor + 0.8:
            timeline += _face_shots(cursor, ins["t"], word_times, jump_times, opening)
            opening = False
        timeline.append(Shot(ins["t"], ins["t1"], ins["kind"], plate=ins["plate"]))
        cursor = ins["t1"]
    if duration - cursor > 0.4:
        timeline += _face_shots(cursor, duration, word_times, jump_times, opening)
    timeline = _ensure_title_cut(timeline, word_times)
    timeline = _ensure_three_long_shots(timeline)
    _apply_scales(timeline)
    if bw_word is not None:
        t = words[bw_word]["out"]
        for s in timeline:
            if s.kind == "face" and s.t0 <= t < s.t1:
                s.bw = True
                s.scale = PUNCH
                s.push = 0.0
                break
    _mark_flashes(timeline)
    # Drop a zero-length tail and snap edges.
    clean = []
    for s in timeline:
        s.t0 = qframe(s.t0)
        s.t1 = qframe(s.t1)
        if s.t1 - s.t0 >= 1 / FPS:
            clean.append(s)
    if clean:
        clean[0].t0 = 0.0
        clean[-1].t1 = qframe(duration)
    return clean


@dataclass
class Cue:
    role: str
    t: float
    trigger: str
    gain: float | None = None
    path: str = ""

    def __post_init__(self):
        self.path = SFX[self.role]
        if self.gain is None:
            self.gain = GAINS[self.role]


def _emphasis_windows(specs, words, duration, cta_t):
    windows = []
    for spec in specs:
        w = words[find_word(words, spec["word"], spec.get("occ", 0))]
        start = w["out"]
        if spec.get("spoken"):
            start = words[find_word(words, spec["spoken"][0][0], spec["spoken"][0][1])]["out"]
        elif spec.get("count"):
            start = w["out"] - (len(spec["count"]) - 1) * (3 / FPS)
        hold = min(spec.get("hold", 0.95), 0.72)
        cap = duration if cta_t is None else cta_t - 0.36
        end = min(max(w["out"], start) + hold, cap, duration)
        start = max(0.0, start)
        if end - start < 0.30:
            continue
        windows.append({**spec, "t0": start, "t1": end, "land": w["out"], "word_idx": w["idx"]})
    windows.sort(key=lambda w: w["t0"])
    kept = []
    for win in windows:
        if kept and win["t0"] < kept[-1]["t1"] + 0.45:
            kept[-1]["t1"] = min(kept[-1]["t1"], win["t0"] - 0.45)
            if kept[-1]["t1"] - kept[-1]["t0"] < 0.30:
                kept.pop()
            if kept:
                win["t0"] = max(win["t0"], kept[-1]["t1"] + 0.45)
        if win["t1"] - win["t0"] >= 0.30:
            kept.append(win)
    return kept


def build_cues(words, shots, windows, negatives, cta_t, duration, keyword):
    cues = []
    for win in windows:
        cues.append(Cue("pop", qframe(max(0.0, win["t0"])), f"hero-{win['hero']}"))
        if win.get("count"):
            vals = win["count"]
            if win.get("spoken"):
                times = []
                for i, (text, occ) in enumerate(win["spoken"]):
                    times.append(words[find_word(words, text, occ)]["out"])
            else:
                land = win["land"]
                times = [land - (len(vals) - 1 - i) * (3 / FPS) for i in range(len(vals))]
            for i, (t, v) in enumerate(zip(times, vals)):
                if win["t0"] - 0.02 <= t <= win["t1"] + 0.02:
                    cues.append(Cue("tick", qframe(max(0.0, t)), f"tick-{v}"))
        if win.get("landing"):
            cues.append(Cue("landing", qframe(win["land"]), f"landing-{win['hero']}"))
    for s in shots:
        if s.kind != "face":
            cues.append(Cue("pop", s.t0, f"insert-{s.plate}"))
        if s.flash:
            cues.append(Cue("shutter", s.t0, "flash"))
    # Punch thumps on about half of face-to-face scale changes, never on a flash.
    punches = []
    for i, s in enumerate(shots):
        if s.kind != "face" or s.flash or i == 0:
            continue
        prev = shots[i - 1]
        if prev.kind == "face" and abs(s.scale - prev.scale) >= 0.10:
            punches.append(s.t0)
    # About half of the punch cuts, and never more than 80%.
    step = 2 if len(punches) >= 2 else 99
    for i, t in enumerate(punches):
        if i % step == 0:
            cues.append(Cue("thump", t, "punch"))
    landings = [c.t for c in cues if c.role == "landing"]
    kept_neg = []
    for spec in negatives:
        t = qframe(words[find_word(words, spec["word"], spec.get("occ", 0))]["out"])
        if any(abs(t - prev) < 3.0 for prev in kept_neg):
            continue
        if any(abs(t - land) < 0.40 for land in landings):
            continue
        kept_neg.append(t)
        cues.append(Cue("negative", t, f"negative-{spec['word']}"))
    if cta_t is not None:
        cues.append(Cue("pop", qframe(cta_t), f"cta-{keyword}"))
    # Dark impact under up to four hero pops, skipped when a thump is already there.
    impacts = 0
    thumps = {round(c.t, 3) for c in cues if c.role == "thump"}
    for c in list(cues):
        if impacts >= 4:
            break
        if c.role == "pop" and c.trigger.startswith("hero"):
            if any(abs(c.t - t) < 0.08 for t in thumps):
                continue
            cues.append(Cue("impact", c.t, c.trigger + "-impact"))
            impacts += 1
    cues.sort(key=lambda c: (c.t, c.role))
    return cues


def green_intervals(windows, cta_t, duration, title_off):
    spans = [(0.0, title_off)]  # banner green phrase
    for w in windows:
        spans.append((w["t0"], w["t1"]))
    if cta_t is not None:
        spans.append((cta_t, duration))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 0.30:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


# ---------------------------------------------------------------- plans
SCREEN = {
    "07web": Path("/tmp/reel07/project-v20/assets/media-004.png"),
    "07dark": Path("/tmp/reel07/project-v20/assets/media-003.mp4"),
    "09ui": Path("/tmp/reel09/project-v20/assets/media-003.mp4"),
    "09code": Path("/tmp/reel09/project-v20/assets/media-004.mp4"),
}


def reel_specs(reel):
    if reel == "07":
        return {
            "source": "/tmp/reel07/source.mp4",
            "words": "/tmp/reel07/words.json",
            "keyword": "plan",
            "title": ["Never Sell A Website", "For $2,000"],
            "title_green": "$2,000",
            "emphasis": [
                {"word": "mistake", "kicker": "most expensive", "hero": "MISTAKE", "hold": 0.95},
                {"word": "gone", "kicker": "they're", "hero": "GONE", "hold": 0.90},
                {"word": "7", "kicker": "client websites", "hero": "7", "hold": 0.95,
                 "count": [1, 2, 3, 4, 5, 6, 7]},
                {"word": "$2,000", "occ": 1, "kicker": "up front", "hero": "$2,000", "hold": 1.05,
                 "count": [0, 500, 1000, 1500, 2000]},
                {"word": "$400", "kicker": "a month", "hero": "$400", "hold": 1.05, "landing": True,
                 "count": [300, 400], "spoken": [("$300", 0), ("$400", 0)]},
                {"word": "leverage", "kicker": "That's", "hero": "LEVERAGE", "hold": 1.05},
            ],
            "negatives": [
                {"word": "mistake"},
                {"word": "gone"},
                {"word": "front", "occ": 1},
            ],
            "bw": "gone",
            "inserts": [
                {"word": "Option", "occ": 0, "dur": 4.00, "kind": "phone", "plate": "07web", "fit": "phone"},
                {"word": "watch", "dur": 3.50, "kind": "bleed", "plate": "07dark", "fit": "card"},
            ],
        }
    if reel == "09":
        return {
            "source": "/tmp/reel09/source-cfr.mp4",
            "words": "/tmp/reel09/words.json",
            "keyword": "sites",
            "title": ["Sell Functionality", "Not Just Pages"],
            "title_green": "Functionality",
            "emphasis": [
                {"word": "unlock", "kicker": "upgrade to", "hero": "UNLOCK", "hold": 0.95},
                {"word": "grand", "occ": 0, "kicker": "start charging", "hero": "$10K", "hold": 0.95,
                 "count": ["$2K", "$4K", "$6K", "$8K", "$10K"], "landing": True},
                {"word": "fifteen", "kicker": "builds", "hero": "$15K", "hold": 1.20,
                 "count": ["$500", "$10K", "$15K"], "spoken": [("five", 0), ("ten", 0), ("fifteen", 0)]},
                {"word": "functionality", "occ": 0, "kicker": "custom", "hero": "FUNCTIONALITY", "hold": 1.10},
                {"word": "portal", "kicker": "a client", "hero": "PORTAL", "hold": 1.05},
            ],
            "negatives": [
                {"word": "unlock"},
                {"word": "pages"},
            ],
            "bw": None,
            "inserts": [
                {"word": "Claude", "dur": 3.80, "kind": "phone", "plate": "09ui", "fit": "phone"},
                {"word": "booking", "dur": 3.60, "kind": "mg", "plate": "features"},
                {"word": "design", "dur": 3.50, "kind": "bleed", "plate": "09code", "fit": "crop"},
            ],
        }
    raise SystemExit(f"unknown reel {reel}")


def plan_reel(reel):
    spec = reel_specs(reel)
    if norm_word(spec["keyword"]) not in APPROVED:
        raise SystemExit(f"keyword {spec['keyword']} is not on the ManyChat list")
    words = load_words(spec["words"])
    spoken = {norm_word(w["word"]) for w in words}
    if norm_word(spec["keyword"]) not in spoken:
        raise SystemExit(f"keyword {spec['keyword']} is not spoken in the transcript")
    audio = load_mono(spec["source"])
    spans, duration = build_spans(words, audio)
    # About 80% of the way through, and long enough that the CTA green
    # outlasts the title banner on face frames.
    cta_t = qframe(min(duration * 0.78, duration - 4.6))
    # Three inserts, long enough for the shot p90, totalling about 33% of the reel.
    n_ins = len(spec["inserts"])
    budget = duration * (0.33 if n_ins >= 3 else 0.30)
    weights = (1.05, 1.15, 1.0)[:n_ins]
    durs = [budget * w / sum(weights) for w in weights]
    durs = [min(4.3, max(3.35, d)) for d in durs]
    # If the floor pushed the total past 40%, scale back down but keep one long shot.
    while sum(durs) > duration * 0.39:
        durs = [d - 0.05 for d in durs]
    for ins, dur in zip(spec["inserts"], durs):
        ins["dur"] = round(dur, 2)
    raw_inserts = []
    for ins in spec["inserts"]:
        w = words[find_word(words, ins["word"], ins.get("occ", 0))]
        raw_inserts.append({**ins, "t": qframe(w["out"])})
    raw_inserts.sort(key=lambda ins: ins["t"])
    inserts = _clamp_inserts(raw_inserts, duration)
    bw_idx = find_word(words, spec["bw"]) if spec.get("bw") else None
    shots = build_shots(words, spans, inserts, bw_idx)
    windows = _emphasis_windows(spec["emphasis"], words, duration, cta_t)
    cues = build_cues(words, shots, windows, spec["negatives"], cta_t, duration, spec["keyword"])
    title_off = _title_off_time(shots, 6.0)
    green = green_intervals(windows, cta_t, duration, title_off)
    plan = {
        "reel": reel,
        "spec": spec,
        "words": words,
        "spans": spans,
        "duration": duration,
        "shots": shots,
        "windows": windows,
        "cues": cues,
        "cta_t": cta_t,
        "title_off": title_off,
        "green": green,
        "inserts": inserts,
    }
    from brandon_v2 import apply_v2
    return apply_v2(plan)


def preview(plan):
    shots = plan["shots"]
    dur = plan["duration"]
    durs = np.array([s.dur for s in shots])
    face_shots = [s for s in shots if s.kind == "face"]
    face = sum(s.dur for s in face_shots)
    ratios = []
    for a, b in zip(shots, shots[1:]):
        if a.kind == "face" and b.kind == "face" and a.scale and b.scale:
            ratios.append(b.scale / a.scale)
    chg = [r for r in ratios if r >= 1.08 or r <= 1 / 1.08]
    push = sum(1 for s in face_shots if s.push >= 0.05)
    print(f"reel {plan['reel']}  {dur:.2f}s  {len(shots)} shots  first cut {shots[1].t0:.2f}s")
    print(f"  median {np.median(durs):.2f}  p90 {np.percentile(durs, 90):.2f}  max {durs.max():.2f}  face {face/dur:.0%}")
    print(f"  scale-change {len(chg)}/{len(ratios)}  push {push}/{len(face_shots)}")
    print("  shots:")
    for s in shots:
        flag = " FLASH" if s.flash else ""
        bw = " BW" if s.bw else ""
        push = f" push{s.push:.2f}" if s.push else ""
        print(f"    {s.t0:6.2f}-{s.t1:6.2f} {s.kind:5} x{s.scale:.2f}{push}{bw}{flag} {s.plate}")
    green = sum(b - a for a, b in plan["green"])
    cta = "none" if plan.get("cta_t") is None else f"{plan['cta_t']:.2f}"
    print(f"  title off {plan['title_off']:.2f}  cta {cta}  green {green/dur:.0%}  episodes {len(plan['green'])}")
    for a, b in plan["green"]:
        print(f"    green {a:.2f}-{b:.2f}")
    print(f"  cues {len(plan['cues'])}  (~{len(plan['cues'])/dur*60:.0f}/min before merge)")
    for c in plan["cues"]:
        print(f"    {c.t:6.2f} {c.role:9} {c.gain:+.1f} dB  {c.trigger}")


# ---------------------------------------------------------------- audio
def load_mono(path):
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-",
    ])
    return np.frombuffer(raw, np.float32).copy()


def voice_from_spans(source, spans):
    src = load_mono(source)
    out_n = int(round(spans[-1].out_end * SR))
    voice = np.zeros(out_n, np.float32)
    for i, s in enumerate(spans):
        if s.src is None:
            continue
        a = int(round(s.out * SR))
        n = int(round(s.dur * SR))
        b = int(round(s.src * SR))
        piece = src[b:b + n]
        if len(piece) < n:
            piece = np.pad(piece, (0, n - len(piece)))
        # 10 ms fade only where the source actually jumps, so a kept pause
        # does not dip and the fade never sits on the next word.
        nxt = spans[i + 1] if i + 1 < len(spans) else None
        jumps = nxt is None or nxt.src is None or s.src is None
        if not jumps and nxt is not None and nxt.src is not None:
            jumps = abs((s.src + s.dur) - nxt.src) > 0.03
        fade = int(0.010 * SR)
        if jumps and fade > 1 and a + n < out_n:
            piece = piece.copy()
            piece[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        voice[a:a + len(piece)] += piece[: max(0, out_n - a)]
    return voice


def measure_gaps(voice, sr=SR):
    """Same gap rules as measure_edit_v2 (10 ms hops, p95-35 dB, holes under 30 ms closed)."""
    hop = int(sr * 0.01)
    n = len(voice) // hop
    if n < 10:
        return {}
    rms = 20 * np.log10(np.sqrt((voice[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    speech = rms > (np.percentile(rms, 95) - 35)
    runs = []
    s0 = None
    for i, on in enumerate(speech):
        if on and s0 is None:
            s0 = i
        if not on and s0 is not None:
            runs.append([s0, i])
            s0 = None
    if s0 is not None:
        runs.append([s0, n])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < 3:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    merged = [m for m in merged if m[1] - m[0] >= 4]
    if len(merged) < 2:
        return {"n": 0}
    gaps = np.array([(merged[i + 1][0] - merged[i][1]) * 10 for i in range(len(merged) - 1)])
    g = gaps[gaps >= 50]
    return {
        "n": int(len(g)),
        "median": float(np.median(g)) if len(g) else None,
        "p90": float(np.percentile(g, 90)) if len(g) else None,
        "max": float(g.max()) if len(g) else None,
        "over150": float(np.mean(g > 150)) if len(g) else None,
        "lead": merged[0][0] / 100,
        "tail": n / 100 - merged[-1][1] / 100,
    }


def _decode_sfx(rel, trim=None):
    path = PACK / rel
    y = load_mono(path)
    if trim:
        y = y[: int(trim * SR)]
    fade = int(0.10 * SR) if trim else int(0.004 * SR)
    if len(y) > fade + 8:
        y = y.copy()
        y[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return y


def _nearby_peak(y, t, sr=SR, half=0.40):
    a = max(0, int((t - half) * sr))
    b = min(len(y), int((t + half) * sr))
    if b <= a:
        return 1e-4
    return max(float(np.max(np.abs(y[a:b]))), 1e-4)


def level_cues(voice, cues, words):
    """Put each transient 15 dB under the nearby voice, or 10 dB for an impact.

    The shared loudness gain comes later and moves voice and effects together.
    """
    for c in cues:
        vpeak = _nearby_peak(voice, c.t)
        nxt = next((w["out"] for w in words if w["out"] >= c.t + 0.08), None)
        peak = PEAK_AT.get(c.role, 0.0)
        # File length includes the pre-roll before the transient, and the
        # fade sits after the transient so it does not duck the hit.
        cap = None
        if nxt is not None:
            cap = max(peak + 0.14, peak + (nxt - c.t) - 0.03)
        base = TRIM_AT.get(c.role)
        trim = base
        if cap is not None:
            trim = cap if base is None else min(max(base, peak + 0.14), cap)
        if trim is not None and trim < peak + 0.14:
            trim = peak + 0.14
        c.trim = trim
        y = _decode_sfx(c.path, trim)
        fpeak = float(np.max(np.abs(y))) or 1e-6
        rel = 10.0 if c.role == "impact" else 15.0
        target = vpeak * 10 ** (-rel / 20.0)
        c.gain = float(20.0 * np.log10(max(target / fpeak, 1e-8)))
        c.rel_db = -rel
    return cues


def mix_sfx(cues, n_samples):
    bed = np.zeros(n_samples, np.float32)
    cache = {}
    placed = []
    for c in cues:
        trim = getattr(c, "trim", None)
        if trim is None:
            trim = TRIM_AT.get(c.role)
        key = (c.path, None if trim is None else round(float(trim), 4))
        if key not in cache:
            cache[key] = _decode_sfx(c.path, trim)
        y = cache[key]
        shift = PEAK_AT.get(c.role, 0.0)
        start = int(round((c.t - shift) * SR))
        gain = 10 ** (c.gain / 20)
        left = max(0, -start)
        a = start + left
        piece = y[left:] * gain
        b = min(n_samples, a + len(piece))
        if b > a:
            bed[a:b] += piece[: b - a]
        placed.append({
            "path": c.path, "start": round(c.t - shift, 4), "gain_db": round(c.gain, 2),
            "role": c.role, "trigger": c.trigger, "peak_on": round(c.t, 4),
            "hit_offset": round(shift, 4),
            "rel_db": getattr(c, "rel_db", None),
            "trim": None if trim is None else round(float(trim), 3),
        })
    return bed, placed


def sfx_events(bed, sr=SR):
    hop = int(sr * 0.01)
    n = len(bed) // hop
    rms = 20 * np.log10(np.sqrt((bed[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    ons = []
    prev = np.r_[np.full(5, -100.0), rms]
    for i in range(n):
        if rms[i] > -42 and rms[i] - prev[i:i + 5].min() >= 12 and (not ons or i / 100 - ons[-1] > 0.12):
            ons.append(i / 100)
    events = []
    for t in ons:
        if events and t - events[-1][-1] <= 0.2:
            events[-1].append(t)
        else:
            events.append([t])
    return [e[0] for e in events]


def _measure_pcm(y, sr=SR):
    """ebur128 on a float wav so a hot peak is not clipped before the reading."""
    import soundfile as sf
    path = "/tmp/brandon_loud.wav"
    sf.write(path, np.asarray(y, np.float32), sr)
    err = subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    tail = err[err.rfind("Summary:"):]
    import re
    I = float(re.search(r"I:\s+(-?[\d.]+)", tail).group(1))
    TP = float(re.search(r"Peak:\s+(-?[\d.]+)", tail).group(1))
    return I, TP


def _peak_db(y):
    return float(20 * np.log10(max(float(np.max(np.abs(y))), 1e-9)))


def fit_loudness(voice, bed):
    """One gain on the whole mix, aimed at -15 LUFS on the dual-mono file.

    A mono measurement reads about 3 LU quieter than the stereo delivery, so
    the mono target is -18. Only samples that would pass -2 dBFS are
    trimmed, which keeps a stray peak legal without turning the voice down.
    """
    mix = np.asarray(voice, np.float64) + np.asarray(bed, np.float64)
    I, _TP = _measure_pcm(mix)
    mix = mix * 10 ** ((-18.0 - I) / 20)
    ceil = 10 ** (-2.0 / 20)
    mix = np.clip(mix, -ceil, ceil)
    I3, _TP3 = _measure_pcm(mix)
    return mix.astype(np.float32), {
        "I_pcm": round(I3 + 3.0, 2),
        "TP_pcm": round(_peak_db(mix), 2),
    }


def _write_wav(path, y, sr=SR):
    y = np.clip(y, -1, 1)
    pcm = (y * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- pictures
def _text_image(text, font, fill):
    probe = Image.new("RGBA", (8, 8))
    box = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0] + 8, box[3] - box[1] + 8
    im = Image.new("RGBA", (max(w, 4), max(h, 4)), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - box[0], 4 - box[1]), text, font=font, fill=fill)
    return im


def _word_caption(text):
    im = _text_image(text, _font("BebasNeue-Regular.ttf", 120), (255, 255, 255, 255))
    arr = np.array(im)
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > 80)
    if len(ys) == 0:
        return Image.new("RGBA", (8, CAPTION_H), (0, 0, 0, 0))
    crop = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    scale = CAPTION_H / crop.size[1]
    crop = crop.resize((max(1, int(round(crop.size[0] * scale))), CAPTION_H), Image.Resampling.LANCZOS)
    hard = np.array(crop)
    mask = hard[:, :, 3] > 140
    hard[mask, :3] = 255
    hard[mask, 3] = 255
    hard[~mask] = (0, 0, 0, 0)
    glyph = Image.fromarray(hard, "RGBA")
    shadow = Image.new("RGBA", (glyph.size[0] + 16, glyph.size[1] + 16), (0, 0, 0, 0))
    sh = Image.new("RGBA", glyph.size, (0, 0, 0, 160))
    sh.putalpha(Image.fromarray((hard[:, :, 3] > 0).astype(np.uint8) * 150))
    shadow.paste(sh, (6, 8), sh)
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    canvas = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(glyph, (4, 2))
    return canvas


def make_caption(text):
    """One or two centered lines. The white glyph bottom is what the placer locks."""
    words = [w for w in str(text).split() if w]
    if not words:
        return Image.new("RGBA", (8, CAPTION_H), (0, 0, 0, 0))
    glyphs = [_word_caption(w) for w in words]
    gap = 16
    max_w = 980
    widths = [g.size[0] for g in glyphs]
    total = sum(widths) + gap * (len(glyphs) - 1)
    if total <= max_w or len(glyphs) == 1:
        groups = [glyphs]
    else:
        best_i, best = 1, None
        for i in range(1, len(glyphs)):
            left = sum(widths[:i]) + gap * max(0, i - 1)
            right = sum(widths[i:]) + gap * max(0, len(glyphs) - i - 1)
            score = abs(left - right)
            if best is None or score < best:
                best, best_i = score, i
        groups = [glyphs[:best_i], glyphs[best_i:]]
    line_gap = 8
    lines = []
    for group in groups:
        w = sum(g.size[0] for g in group) + gap * (len(group) - 1)
        h = max(g.size[1] for g in group)
        im = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
        x = 0
        for g in group:
            im.alpha_composite(g, (x, h - g.size[1]))
            x += g.size[0] + gap
        lines.append(im)
    width = max(im.size[0] for im in lines)
    height = sum(im.size[1] for im in lines) + line_gap * (len(lines) - 1)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    y = 0
    for im in lines:
        canvas.alpha_composite(im, ((width - im.size[0]) // 2, y))
        y += im.size[1] + line_gap
    return canvas


def _fit_hero(text, max_w=980, target_h=142):
    font = _font("Anton-Regular.ttf", 165)
    im = _text_image(text, font, GREEN)
    arr = np.array(im)
    ys, xs = np.where(arr[:, :, 3] > 80)
    if len(ys) == 0:
        return im
    crop = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    scale = target_h / crop.size[1]
    if crop.size[0] * scale > max_w:
        scale = max_w / crop.size[0]
    crop = crop.resize((max(1, int(crop.size[0] * scale)), max(1, int(crop.size[1] * scale))), Image.Resampling.LANCZOS)
    # Hard-ish green core so the hue survives H.264.
    a = np.array(crop)
    m = a[:, :, 3] > 120
    a[m, 0], a[m, 1], a[m, 2], a[m, 3] = 0x42, 0xFF, 0x40, 255
    return Image.fromarray(a, "RGBA")


def _glow(glyph):
    """Down-biased green glow around a hero word."""
    pad = 48
    g = Image.new("RGBA", (glyph.size[0] + pad * 2, glyph.size[1] + pad * 2), (0, 0, 0, 0))
    color = Image.new("RGBA", glyph.size, (*GREEN[:3], 255))
    color.putalpha(glyph.getchannel("A"))
    for dx, dy, blur, alpha in ((0, 8, 6, 180), (0, 16, 16, 110), (0, 28, 28, 70)):
        layer = Image.new("RGBA", g.size, (0, 0, 0, 0))
        faded = color.copy()
        faded.putalpha(faded.getchannel("A").point(lambda p, a=alpha: p * a // 255))
        layer.paste(faded, (pad + dx, pad + dy), faded)
        g.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))
    g.alpha_composite(glyph, (pad, pad))
    return g


def make_kicker(text):
    im = _text_image(text, _font("BebasNeue-Regular.ttf", 64), (255, 255, 255, 255))
    return im


def _money(value, win):
    if isinstance(value, str):
        return value
    if win["hero"].startswith("$"):
        return f"${value:,}"
    return str(value)


def _fit_cta(text):
    """Quoted keyword at 52% of the frame width (the 50-55% band)."""
    glyph = _fit_hero(text, max_w=int(W * 0.55), target_h=240)
    target = int(round(W * 0.52))
    if glyph.size[0] < 8:
        return _glow(glyph)
    scale = target / glyph.size[0]
    glyph = glyph.resize((target, max(1, int(round(glyph.size[1] * scale)))), Image.Resampling.LANCZOS)
    arr = np.array(glyph)
    mask = arr[:, :, 3] > 120
    arr[mask, 0], arr[mask, 1], arr[mask, 2], arr[mask, 3] = 0x42, 0xFF, 0x40, 255
    return _glow(Image.fromarray(arr, "RGBA"))


def _caption_safe(image):
    """Keep the caption band free of plate whites so the detector locks onto the word."""
    im = image.convert("RGB")
    ImageDraw.Draw(im).rectangle([0, 1220, W, H], fill=(0, 0, 0))
    return im


def phone_plate(image, bottom=None):
    shot = image.convert("RGB")
    plate = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(plate)
    if bottom is None:
        pw, ph = int(W * 0.82), int(H * 0.72)
        x, y = (W - pw) // 2, (H - ph) // 2 + 30
    else:
        # Whole screenshot, contained, with the handset ending at or above `bottom`.
        top = 168
        ph = bottom - top
        pw = int(ph * shot.size[0] / max(1, shot.size[1]))
        pw = min(pw, int(W * 0.88))
        ph = int(pw * shot.size[1] / max(1, shot.size[0]))
        if top + ph > bottom:
            ph = bottom - top
            pw = int(ph * shot.size[0] / max(1, shot.size[1]))
        x, y = (W - pw) // 2, top
    draw.rounded_rectangle([x, y, x + pw, y + ph], radius=46, outline=(255, 255, 255), width=8)
    inner = shot.resize((max(1, pw - 28), max(1, ph - 28)), Image.Resampling.LANCZOS)
    plate.paste(inner, (x + 14, y + 14))
    return _caption_safe(plate)


def bleed_plate(image):
    im = image.convert("RGB")
    sw, sh = im.size
    scale = max(W / sw, H / sh)
    im = im.resize((int(sw * scale) + 1, int(sh * scale) + 1), Image.Resampling.LANCZOS)
    left, top = (im.size[0] - W) // 2, (im.size[1] - H) // 2
    return _caption_safe(im.crop((left, top, left + W, top + H)))


def grab_frame(path, t):
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])
    # Width/height from the file.
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
        "-of", "csv=p=0", str(path),
    ], text=True).strip()
    width, height = map(int, probe.split(","))
    arr = np.frombuffer(raw, np.uint8).reshape(height, width, 3)
    return Image.fromarray(arr, "RGB")


def _stamp_example(image):
    """Mark a drawn or relabeled card so it is not read as a real result."""
    im = image.convert("RGBA")
    label = _text_image("EXAMPLE", _font("BebasNeue-Regular.ttf", 36), (255, 255, 255, 230))
    im.alpha_composite(label, (48, 108))
    return im.convert("RGB")


def mg_plate(name):
    im = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(im)
    if name == "count7":
        d.rounded_rectangle([180, 520, 900, 1180], radius=28, outline=(255, 255, 255), width=6)
        d.rectangle([180, 520, 900, 600], outline=(255, 255, 255), width=4)
        for i in range(7):
            cx = 280 + i * 80
            d.ellipse([cx - 22, 980, cx + 22, 1024], outline=(255, 255, 255), width=4)
    elif name == "sitedown":
        d.rounded_rectangle([160, 460, 920, 1180], radius=24, outline=(255, 255, 255), width=6)
        d.line([160, 660, 920, 660], fill=(255, 255, 255), width=4)
        d.line([300, 860, 780, 1180], fill=(255, 255, 255), width=8)
        d.line([780, 860, 300, 1180], fill=(255, 255, 255), width=8)
    elif name == "features":
        # Three labeled cards, all ending above the caption. Icons pop in the overlay.
        labels_y = (300, 540, 780)
        for y in labels_y:
            d.rounded_rectangle([180, y, 900, y + 200], radius=28, outline=(255, 255, 255), width=6)
        im = _stamp_example(im)
    else:
        d.rectangle([200, 560, 880, 1060], outline=(255, 255, 255), width=6)
    return _caption_safe(im)


def build_plates(plan, work):
    plates = {}
    for ins in plan["inserts"]:
        plate = ins["plate"]
        if plate in plates:
            continue
        if ins["kind"] == "mg":
            img = mg_plate(plate)
        else:
            src = SCREEN.get(plate)
            if plate == "09form":
                img = grab_frame(SCREEN["09code"], 7.0)
            elif src is None:
                img = Image.new("RGB", (W, H), (0, 0, 0))
            elif src.suffix.lower() == ".png":
                img = Image.open(src)
            else:
                img = grab_frame(src, 1.0 if plate != "09code" else 7.0)
            from brandon_v2 import prepare_plate
            img = prepare_plate(plate, img, ins.get("fit"), phone_plate, bleed_plate)
        path = work / f"plate_{plate}.png"
        img.save(path)
        plates[plate] = path
    return plates


# ---------------------------------------------------------------- video
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-an", "-video_track_timescale", "30000"]


def _frames(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path),
    ], text=True).strip()
    return int(out or 0)


def _ensure(path, n, work):
    got = _frames(path)
    if got == n:
        return path
    fixed = work / (path.stem + f"_{n}.mp4")
    if got > n:
        ff("-y", "-i", str(path), "-frames:v", str(n), *ENC, str(fixed))
    else:
        ff("-y", "-i", str(path), "-vf", f"tpad=stop_mode=clone:stop_duration={(n-got)/FPS}",
           "-frames:v", str(n), *ENC, str(fixed))
    return fixed


def _encode_source(source, src_t, n, scale, push, bw, dest):
    pre = max(0.0, src_t - 0.4)
    vf = [f"trim=start={src_t - pre:.4f}:duration={n / FPS + 0.05}", "setpts=PTS-STARTPTS",
          f"fps={FPS}", "scale=1080:1920:flags=bicubic"]
    if bw:
        vf.append("hue=s=0")
    if push:
        # Start at this shot's scale and creep. Cap the stack at 1.30x.
        vf.append(
            f"zoompan=z='min(1.30,{scale:.4f}+{push}*on/{FPS})':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={FPS}"
        )
    elif scale > 1.01:
        sw = int(round(1080 * scale / 2) * 2)
        sh = int(round(1920 * scale / 2) * 2)
        vf += [f"scale={sw}:{sh}:flags=bicubic", "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2"]
    vf.append(f"fps={FPS}")
    ff("-y", "-ss", f"{pre:.3f}", "-i", source, "-vf", ",".join(vf), "-frames:v", str(n), *ENC, str(dest))


def _encode_still(png, n, dest):
    # A still plate. zoompan inserts a false cut near the end, so this is a held frame.
    ff("-y", "-loop", "1", "-i", str(png), "-frames:v", str(n), *ENC, str(dest))


def _jump_times(spans, t0, t1):
    """Output times inside a shot where the picture jumps to a later source frame."""
    jumps = []
    prev_src_end = None
    for s in spans:
        if s.out_end <= t0 or s.out >= t1:
            if s.out >= t1:
                break
            continue
        if s.src is None:
            if t0 + 0.05 < s.out < t1 - 0.05:
                jumps.append(s.out)
            prev_src_end = None
            continue
        if prev_src_end is not None and s.src > prev_src_end + 0.12:
            if t0 + 0.05 < s.out < t1 - 0.05:
                jumps.append(s.out)
        prev_src_end = s.src + s.dur
    return jumps


def _spike_times(path, thresh=11.0, edge=4):
    """Frames inside a shot whose luma jump would read as a cut."""
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-vf", "scale=135:240",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, 240, 135).astype(np.float32)
    if len(frames) < 8:
        return []
    diff = np.mean(np.abs(np.diff(frames, axis=0)), axis=(1, 2))
    times = []
    for i, d in enumerate(diff, start=1):
        if d > thresh and edge < i < len(frames) - edge:
            times.append(i / FPS)
    return times


def _soften_jumps(path, dest, times, work, frames_n=6):
    """Blend a few frames across a pause splice so it does not read as an extra cut."""
    if not times:
        return path
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])
    frame_bytes = W * H * 3
    n = len(raw) // frame_bytes
    frames = [bytearray(raw[i * frame_bytes:(i + 1) * frame_bytes]) for i in range(n)]
    arrs = [np.frombuffer(f, dtype=np.uint8).reshape(H, W, 3) for f in frames]
    for t in times:
        i = int(round(t * FPS))
        a = max(1, i - frames_n // 2)
        b = min(n - 1, i + frames_n // 2)
        if b - a < 2:
            continue
        fa = arrs[a].astype(np.float32)
        fb = arrs[b].astype(np.float32)
        for k in range(a + 1, b):
            wgt = (k - a) / (b - a)
            arrs[k] = np.clip(fa * (1 - wgt) + fb * wgt, 0, 255).astype(np.uint8)
    out = work / (Path(dest).name + ".raw")
    with open(out, "wb") as f:
        for a_ in arrs:
            f.write(np.ascontiguousarray(a_).tobytes())
    ff("-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
       "-i", str(out), "-frames:v", str(n), *ENC, str(dest))
    out.unlink(missing_ok=True)
    return dest


def _hold(prev, n, dest, work):
    frame = work / "hold.png"
    ff("-y", "-sseof", "-0.04", "-i", str(prev), "-frames:v", "1", str(frame))
    ff("-y", "-loop", "1", "-i", str(frame), "-frames:v", str(n), *ENC, str(dest))


def _cover(spans, t0, t1):
    pieces = []
    for s in spans:
        a = max(t0, s.out)
        b = min(t1, s.out_end)
        if b - a < 0.5 / FPS:
            continue
        if s.src is None:
            pieces.append(("hold", b - a, None))
        else:
            pieces.append(("src", b - a, s.src + (a - s.out)))
    return pieces


def render_base(plan, work):
    source = plan["spec"]["source"]
    plates = build_plates(plan, work)
    parts = []
    prev = None
    for i, shot in enumerate(plan["shots"]):
        n = max(1, round(shot.dur * FPS))
        dest = work / f"shot_{i:02d}.mp4"
        if shot.kind == "face":
            bits = []
            for j, (kind, dur, src_t) in enumerate(_cover(plan["spans"], shot.t0, shot.t1)):
                bn = max(1, round(dur * FPS))
                bit = work / f"bit_{i:02d}_{j}.mp4"
                if kind == "src":
                    _encode_source(source, src_t, bn, shot.scale, shot.push, shot.bw, bit)
                    prev = bit
                else:
                    if prev is None:
                        _encode_source(source, 0.0, bn, shot.scale, 0, shot.bw, bit)
                    else:
                        _hold(prev, bn, bit, work)
                bits.append(_ensure(bit, bn, work))
            if len(bits) == 1:
                dest = bits[0]
            else:
                lst = work / f"shot_{i:02d}.txt"
                lst.write_text("".join(f"file '{p}'\n" for p in bits))
                ff("-y", "-f", "concat", "-safe", "0", "-i", str(lst), *ENC, str(dest))
            dest = _ensure(dest, n, work)
            # Hard cut at every take change. A nod inside the take is a 2-frame
            # hold, never a dissolve of two faces.
            jumps = [t - shot.t0 for t in _jump_times(plan["spans"], shot.t0, shot.t1)]
            # A nod is eased across a few frames of the same take. A take change
            # stays a hard cut: blending those frames is the ghosted double face.
            spikes = [t for t in _spike_times(dest, edge=1) if not any(abs(t - j) < 0.08 for j in jumps)]
            if spikes:
                eased = work / f"ease_{i:02d}.mp4"
                dest = _soften_jumps(dest, eased, spikes, work, frames_n=4)
                dest = _ensure(dest, n, work)
            prev = dest
        else:
            _encode_still(plates[shot.plate], n, dest)
            dest = _ensure(dest, n, work)
        parts.append(dest)
        print(f"  shot {i:02d} {shot.kind} {n} frames", flush=True)
    lst = work / "base.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    base = work / "base.mp4"
    ff("-y", "-f", "concat", "-safe", "0", "-i", str(lst), *ENC, str(base))
    from brandon_v2 import mask_pins
    faces = [(s.t0, s.t1) for s in plan["shots"] if s.kind == "face"]
    masked = work / "base_pin.mp4"
    return mask_pins(base, masked, faces, work)


def _motion_sprite(sprite, scale, fade):
    if scale < 0.999:
        sprite = sprite.resize(
            (max(1, int(round(sprite.size[0] * scale))), max(1, int(round(sprite.size[1] * scale)))),
            Image.Resampling.BILINEAR,
        )
    if fade < 0.999:
        arr = np.array(sprite)
        arr[:, :, 3] = np.clip(arr[:, :, 3].astype(np.float32) * fade, 0, 255).astype(np.uint8)
        sprite = Image.fromarray(arr, "RGBA")
    return sprite


def _paste(frame, sprite, cx, bottom=None, top=None):
    x = int(cx - sprite.size[0] / 2)
    y = int(bottom - sprite.size[1]) if bottom is not None else int(top)
    frame.alpha_composite(sprite, (x, y))


class Overlay:
    def __init__(self, plan):
        self.plan = plan
        self.captions = {}
        self.heroes = {}
        self.kickers = {}
        self.title = self._title()
        self.handle = _text_image("@bjmeaux", _font("BebasNeue-Regular.ttf", 36), (255, 255, 255, 230))

    def _title(self):
        spec = self.plan["spec"]
        font = _font("BebasNeue-Regular.ttf", 72)
        lines = []
        for line in spec["title"]:
            # Per-line rounded box. The green phrase is green text on the black box.
            words = line.split(" ")
            pieces = []
            for word in words:
                green_words = spec["title_green"].replace(",", "").split(" ")
                token = word.replace(",", "")
                is_green = (
                    word == spec["title_green"]
                    or token.strip("$") == spec["title_green"].strip("$").replace(",", "")
                    or token in green_words
                )
                fill = GREEN if is_green else (255, 255, 255, 255)
                pieces.append(_text_image(word + " ", font, fill))
            width = sum(p.size[0] for p in pieces) + 36
            height = max(p.size[1] for p in pieces) + 16
            box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ImageDraw.Draw(box).rounded_rectangle([0, 0, width - 1, height - 1], radius=12, fill=(0, 0, 0, 255))
            x = 18
            for p in pieces:
                box.alpha_composite(p, (x, (height - p.size[1]) // 2))
                x += p.size[0]
            lines.append(box)
        return lines

    def caption_for(self, t):
        phrases = self.plan.get("phrases") or []
        current = None
        for ph in phrases:
            if ph["t0"] - (1 / FPS) <= t:
                current = ph
            else:
                break
        if current is None or not current.get("text"):
            return None
        nxt = None
        for ph in phrases:
            if ph["t0"] > current["t0"] + 0.01:
                nxt = ph
                break
        if nxt and t >= nxt["t0"]:
            current = nxt
            nxt = None
            for ph in phrases:
                if ph["t0"] > current["t0"] + 0.01:
                    nxt = ph
                    break
        if nxt and (nxt["t0"] - current["t1"]) >= 0.40 and t > current["t1"] + 0.04:
            return None
        if nxt is None and t > current["t1"] + 0.20:
            return None
        text = current["text"]
        if text not in self.captions:
            self.captions[text] = make_caption(text)
        return self.captions[text]

    def _hero_motion(self, t, win):
        u = min(1.0, max(0.0, (t - win["t0"]) / 0.16))
        ease = 1 - (1 - u) ** 3
        scale = 0.92 + 0.08 * ease
        fade = 1.0
        if win["t1"] - t < 0.15:
            fade = max(0.0, (win["t1"] - t) / 0.15)
        return scale, fade

    def hero_at(self, t):
        # 07 and 09 have no comment card. A quoted keyword here was the CTA.
        for win in self.plan["windows"]:
            if win["t0"] <= t < win["t1"]:
                label = self._count_label(win, t) if win.get("count") else win["hero"]
                if label not in self.heroes:
                    self.heroes[label] = _glow(_fit_hero(label))
                kicker = win.get("kicker") or ""
                if kicker and kicker not in self.kickers:
                    self.kickers[kicker] = make_kicker(kicker)
                return (self.kickers.get(kicker), self.heroes[label])
        return None, None

    def _count_label(self, win, t):
        vals = win["count"]
        if win.get("spoken"):
            shown = _money(vals[0], win)
            for (text, occ), v in zip(win["spoken"], vals):
                wt = self.plan["words"][find_word(self.plan["words"], text, occ)]["out"]
                if t + 1e-4 >= wt:
                    shown = _money(v, win)
            return shown
        land = win["land"]
        step = 3 / FPS
        idx = 0
        for i in range(len(vals)):
            if t + 1e-4 >= land - (len(vals) - 1 - i) * step:
                idx = i
        return _money(vals[idx], win)

    def frame(self, index):
        t = index / FPS
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if t < self.plan["title_off"]:
            y = 268
            for line in self.title:
                fr.alpha_composite(line, ((W - line.size[0]) // 2, y))
                y += line.size[1] - 4
        _paste(fr, self.handle, W // 2, top=36)
        kicker, hero = self.hero_at(t)
        if hero is not None:
            win = next(w for w in self.plan["windows"] if w["t0"] <= t < w["t1"])
            scale, fade = self._hero_motion(t, win)
            sprite = _motion_sprite(hero, scale, fade)
            paste_y = int(round(HERO_GLYPH_TOP - 48 * scale))
            fr.alpha_composite(sprite, ((W - sprite.size[0]) // 2, paste_y))
            if kicker is not None and fade > 0.02:
                kick = kicker if fade > 0.999 else _motion_sprite(kicker, 1.0, fade)
                _paste(fr, kick, W // 2, bottom=HERO_GLYPH_TOP - 16)
        self._feature_cards(fr, t)
        cap = self.caption_for(t)
        if cap is not None:
            hard = np.array(cap)
            ys, xs = np.where((hard[:, :, 3] > 200) & (hard[:, :, :3].min(2) >= 230))
            if len(ys):
                gx0, gx1 = int(xs.min()), int(xs.max())
                cx = (gx0 + gx1) / 2
                glyph_bottom = int(ys.max())
                x = int(W / 2 - cx)
                y = int(CAPTION_BOTTOM - glyph_bottom)
                fr.alpha_composite(cap, (x, y))
        return fr

    def _feature_cards(self, fr, t):
        shot = next((s for s in self.plan["shots"] if s.t0 <= t < s.t1), None)
        if shot is None or shot.plate != "features":
            return
        pops = self.plan.get("feature_pops") or []
        font = _font("BebasNeue-Regular.ttf", 54)
        rows = (300, 540, 780)
        # One highlight at a time. Earlier steps stay dim. Later steps stay hidden
        # until their word, so a dense screen does not light up all at once.
        active = None
        for pop in pops:
            if shot.t0 - 0.02 <= pop["t"] <= shot.t1 + 0.02 and t + 1 / FPS >= pop["t"]:
                active = pop
        for row, pop in zip(rows, pops):
            if not (shot.t0 - 0.02 <= pop["t"] <= shot.t1 + 0.02 and t + 1 / FPS >= pop["t"]):
                continue
            on = pop is active
            fill = (255, 255, 255, 255) if on else (255, 255, 255, 110)
            label = _text_image(pop["label"], font, fill)
            fr.alpha_composite(label, (340, row + 70))
            if on:
                fr.alpha_composite(self._icon(pop["icon"]), (230, row + 50))

    def _icon(self, kind):
        if not hasattr(self, "_icons"):
            self._icons = {}
        if kind in self._icons:
            return self._icons[kind]
        im = Image.new("RGBA", (88, 88), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if kind == "book":
            d.rounded_rectangle([8, 14, 80, 74], radius=8, outline=(255, 255, 255, 255), width=4)
            d.line([44, 14, 44, 74], fill=(255, 255, 255, 255), width=3)
        elif kind == "calc":
            d.rounded_rectangle([10, 8, 78, 80], radius=8, outline=(255, 255, 255, 255), width=4)
            d.rectangle([20, 18, 68, 36], outline=(0x42, 0xFF, 0x40, 255), width=3)
        else:
            d.ellipse([28, 8, 60, 40], outline=(255, 255, 255, 255), width=4)
            d.arc([12, 44, 76, 88], 200, 340, fill=(255, 255, 255, 255), width=4)
        self._icons[kind] = im
        return im


def render_overlay(plan, work):
    n = round(plan["duration"] * FPS)
    dest = work / "overlay.mov"
    ov = Overlay(plan)
    proc = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "qtrle", str(dest),
    ], stdin=subprocess.PIPE)
    for i in range(n):
        proc.stdin.write(ov.frame(i).tobytes())
        if i % 150 == 0:
            print(f"  overlay {i}/{n}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("overlay encode failed")
    return dest


def mux(base, overlay, wav, dest):
    ff("-y", "-i", str(base), "-i", str(overlay), "-i", str(wav),
       "-filter_complex", "[0:v][1:v]overlay=format=auto:eof_action=pass,format=yuv420p,fps=30",
       "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
       "-b:v", "20M", "-maxrate", "24M", "-bufsize", "40M",
       "-c:a", "aac", "-b:a", "256k", "-ar", str(SR), "-ac", "2",
       "-movflags", "+faststart", "-shortest", str(dest))


def loudness_file(path):
    import re
    err = subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    tail = err[err.rfind("Summary:"):]
    return {
        "I": float(re.search(r"I:\s+(-?[\d.]+)", tail).group(1)),
        "LRA": float(re.search(r"LRA:\s+(-?[\d.]+)", tail).group(1)),
        "TP": float(re.search(r"Peak:\s+(-?[\d.]+)", tail).group(1)),
    }


SOUND_ID = {
    "pop": "POP_SOFT",
    "tick": "TAP_TICK",
    "negative": "WRONG_ANSWER",
    "impact": "IMPACT",
    "thump": "THUMP",
    "shutter": "SHUTTER",
    "landing": "LANDING",
    "ding": "DING",
}


def _purpose(role, trigger):
    if role == "impact":
        return "emphasize a major result"
    if role == "negative":
        return "set up a brief expectation that resolves immediately"
    if str(trigger).startswith("insert") or str(trigger).startswith("hero"):
        return "orient to a new element"
    if role == "cut":
        return "silent punch-in" if trigger == "punch" else "routine dialogue edit"
    if role == "caption":
        return "caption phrase"
    if role == "emphasis":
        return "emphasis arrives"
    if role == "dead-air":
        return "flag dead air"
    return "orient to a new element"


def long_pauses(voice, words, sr=SR):
    """Pauses the speech gate calls longer than 0.6 s, or 0.7 s after a reveal."""
    hop = int(sr * 0.01)
    n = len(voice) // hop
    if n < 10:
        return []
    rms = 20 * np.log10(np.sqrt((voice[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    speech = rms > (np.percentile(rms, 95) - 35)
    runs, s0 = [], None
    for i, on in enumerate(speech):
        if on and s0 is None:
            s0 = i
        if not on and s0 is not None:
            runs.append([s0, i])
            s0 = None
    if s0 is not None:
        runs.append([s0, n])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < 3:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    merged = [m for m in merged if m[1] - m[0] >= 4]
    flagged = []
    for i in range(len(merged) - 1):
        start = merged[i][1] / 100
        end = merged[i + 1][0] / 100
        ms = (end - start) * 1000
        reveal = False
        for w in words:
            if abs(w["out_end"] - start) <= 0.12 or abs(w["out"] - start) <= 0.12:
                reveal = str(w["word"]).rstrip().endswith((".", "!", "?"))
                break
        limit = 700 if reveal else 600
        if ms > limit:
            flagged.append({
                "time": round(start, 3),
                "ms": round(ms, 0),
                "after_reveal": reveal,
            })
    return flagged


def _drop_stacks(cues):
    """One sound at a time. A later routine pop loses if its file still overlaps."""
    ranked = sorted(cues, key=lambda c: (c.t, 0 if c.role == "impact" else 1 if c.role == "negative" else 2))
    kept = []
    for cue in ranked:
        peak = PEAK_AT.get(cue.role, 0.0)
        trim = float(getattr(cue, "trim", None) or 0.20)
        a = cue.t - peak
        b = a + trim
        if any(
            a < (other.t - PEAK_AT.get(other.role, 0.0)) + float(getattr(other, "trim", None) or 0.20) - 0.02
            and (other.t - PEAK_AT.get(other.role, 0.0)) < b - 0.02
            for other in kept
        ):
            continue
        kept.append(cue)
    kept.sort(key=lambda c: (c.t, c.role))
    return kept


def _span_bounds(spans, t):
    for s in spans:
        if s.out - 1e-4 <= t < s.out_end - 1e-4:
            if s.src is None:
                return None, None
            return round(s.src, 3), round(s.src + s.dur, 3)
    return None, None


def _phrase_text(plan, t):
    current = ""
    for ph in plan.get("phrases") or []:
        if ph["t0"] - 0.05 <= t:
            current = ph["text"]
        else:
            break
    return current


def _visual_state(plan, t):
    shot = next((s for s in plan["shots"] if s.t0 <= t < s.t1), plan["shots"][-1])
    bits = [shot.kind]
    if shot.plate:
        bits.append(shot.plate)
    if shot.kind == "face":
        bits.append(f"scale {shot.scale:.2f}")
        if shot.bw:
            bits.append("bw")
    hero = next((w["hero"] for w in plan["windows"] if w["t0"] <= t < w["t1"]), None)
    if hero:
        bits.append(f"hero {hero}")
    elif t < plan["title_off"]:
        bits.append("title")
    return " ".join(bits)


def write_cue_sheet(dest, plan, voice, bed, placed):
    """Event list with every visual and every sound, written before the picture.

    Each row has the twelve rubric fields. Listening is named as unavailable.
    """
    dest = Path(dest)
    by_trigger = {row["trigger"]: row for row in placed}
    events = []

    def _event(t, purpose, sound, row, notes, unresolved):
        src_in, src_out = _span_bounds(plan["spans"], t)
        hit = 0.0 if row is None else row.get("hit_offset") or 0.0
        sync = round(float(t), 3)
        measured = None
        if sound != "NONE" and voice is not None and bed is not None:
            vp = _nearby_peak(voice, t, half=0.35)
            bp = _nearby_peak(bed, t, half=0.05)
            if vp > 0 and bp > 0:
                measured = round(float(20 * np.log10(bp / vp)), 1)
        gain = None if row is None else row.get("gain_db")
        rel = measured if measured is not None else (None if row is None else row.get("rel_db"))
        if sound == "NONE":
            level = "none"
        elif gain is None:
            level = f"peak {rel} dB vs voice" if rel is not None else "unmeasured"
        else:
            level = f"gain {gain} dB, peak {rel} dB vs voice"
        events.append({
            "time": sync,
            "source_in": src_in,
            "source_out": src_out,
            "phrase": _phrase_text(plan, t),
            "visual": _visual_state(plan, t),
            "purpose": purpose,
            "sound": sound,
            "file": "" if row is None else row.get("path") or "",
            "hit_offset": round(float(hit), 4),
            "sync_time": sync,
            "trim_fade": notes,
            "level": level,
            "unresolved": unresolved,
        })

    listen_limit = "Listening was unavailable. The hit was placed from the file peak offset, not by ear."
    for cue in plan["cues"]:
        row = by_trigger.get(cue.trigger)
        notes = "unprocessed pack file"
        trim = getattr(cue, "trim", None)
        if trim:
            notes = f"trimmed to {float(trim):.2f}s with a 100 ms fade so the tail ends before the next phrase"
        elif cue.role == "pop":
            notes = "unprocessed pack file, 4 ms file-end fade"
        _event(
            cue.t,
            _purpose(cue.role, cue.trigger),
            SOUND_ID.get(cue.role, cue.role.upper()),
            row,
            notes,
            listen_limit,
        )

    def _silent(t, purpose, notes):
        if any(abs(t - c.t) < 0.08 for c in plan["cues"]):
            return
        if any(abs(t - e["time"]) < 0.05 and e["sound"] == "NONE" for e in events):
            return
        _event(t, purpose, "NONE", None, notes, "No sound by design.")

    for shot in plan["shots"]:
        if shot.t0 <= 0.02:
            continue
        prev = next((s for s in plan["shots"] if abs(s.t1 - shot.t0) < 0.02), None)
        punch = shot.kind == "face" and prev is not None and prev.kind == "face" and abs(shot.scale - prev.scale) > 0.01
        _silent(shot.t0, _purpose("cut", "punch" if punch else "cut"), "clean cut, no sound")
    for win in plan["windows"]:
        _silent(win["t0"], _purpose("emphasis", ""), "emphasis arrives with no sound")
    for ph in plan.get("phrases") or []:
        _silent(ph["t0"], _purpose("caption", ""), "caption update, no sound")
    pauses = long_pauses(voice, plan["words"]) if voice is not None else []
    for gap in pauses:
        kind = "after a reveal" if gap["after_reveal"] else "between thoughts"
        _event(
            gap["time"],
            _purpose("dead-air", ""),
            "NONE",
            None,
            "room tone kept; this hole is longer than the pause ceiling",
            f"Dead air {gap['ms']:.0f} ms {kind}. Ceiling is 0.7 s after a reveal and 0.6 s otherwise.",
        )
    events.sort(key=lambda e: (e["time"], e["sound"] == "NONE"))
    if pauses:
        pause_note = "Dead air over the ceiling is flagged on its own rows: " + ", ".join(
            f"{g['time']:.2f}s ({g['ms']:.0f} ms)" for g in pauses
        )
    else:
        pause_note = "No dead air over 0.6 s (0.7 s after a reveal) on the speech gate. Room tone stays in the shorter pauses."
    notes = [
        "No human listening check was possible.",
        "The mix is dual-mono, so a mono fold is the same program. Levels are a constant gain against nearby voice peaks. The voice was not raised to cover an effect, and nothing was ducked.",
        "Delivery target is -16 to -14 LUFS integrated and a true peak no higher than -1 dBTP.",
        pause_note,
        "One sound per event. No stacked files.",
    ]
    payload = {"reel": plan["reel"], "notes": notes, "events": events}
    dest.with_name(dest.stem + "-cues.json").write_text(json.dumps(payload, indent=1))
    lines = [
        f"# Cue sheet — reel {plan['reel']}",
        "",
        "No human listening check was possible.",
        "",
        "Written from the plan before the picture render. The mix is dual-mono. Each cue was leveled with a constant gain against the nearby voice.",
        "",
        pause_note,
        "",
        "| time | source in | source out | phrase | visual | purpose | sound | file | hit offset | sync time | trim/fade | level | unresolved |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for e in events:
        lines.append(
            "| {time} | {source_in} | {source_out} | {phrase} | {visual} | {purpose} | {sound} | {file} | {hit_offset} | {sync_time} | {trim_fade} | {level} | {unresolved} |".format(
                **{k: "" if v is None else str(v).replace("|", "/") for k, v in e.items()}
            )
        )
    lines += ["", "No human listening check was possible.", ""]
    dest.with_name(dest.stem + "-cues.md").write_text("\n".join(lines))
    return pauses


def _band_rms_db(path, af):
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "info", "-i", str(path), "-af", af, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    level = None
    for line in proc.stderr.splitlines():
        if "RMS level dB:" in line:
            try:
                level = float(line.split("RMS level dB:")[-1].strip())
            except ValueError:
                pass
    return level


def write_handoff(dest, loud, gaps):
    """G14 statement. Listening is unavailable. Say what was measured instead."""
    dest = Path(dest)
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(dest), "-ac", "2", "-ar", str(SR),
        "-f", "f32le", "-",
    ])
    stereo = np.frombuffer(raw, np.float32).reshape(-1, 2)
    # Ignore a one-sample tail from the decoder.
    n = min(len(stereo), int(stereo.shape[0]))
    diff = float(np.max(np.abs(stereo[:n, 0] - stereo[:n, 1]))) if n else 0.0
    identical = diff < 1e-5
    lf = _band_rms_db(dest, "highpass=f=20,lowpass=f=120,astats=metadata=1:reset=0")
    full = _band_rms_db(dest, "astats=metadata=1:reset=0")
    gap_max = None if not gaps else gaps.get("max")
    fx_median = None
    fx_path = dest.with_name(dest.stem + "-fx.wav")
    if fx_path.exists():
        import soundfile as sf
        bed, rate = sf.read(fx_path)
        if getattr(bed, "ndim", 1) > 1:
            bed = bed.mean(1)
        hop = max(1, int(rate * 0.01))
        n = len(bed) // hop
        if n:
            rms = 20 * np.log10(np.sqrt((bed[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
            fx_median = round(float(np.median(rms)), 1)
    if identical:
        channel = "L and R are sample-identical (dual-mono). A mono fold is the same program."
    else:
        channel = (
            f"The mix was written dual-mono. After AAC, L and R differ by at most {diff:.4f} "
            "(encoder). A mono fold is the same program within that tolerance."
        )
    bed_line = (
        f"- Non-voice stem median {fx_median} dBFS (10 ms hops). "
        "That floor is digital silence between hits, not a music bed. "
        f"Full-mix RMS is {full} dB and the 20–120 Hz band is {lf} dB; that band includes the voice."
    )
    lines = [
        f"# Listening and inspection statement — reel {dest.stem}",
        "",
        "No human listening check was possible.",
        "",
        "These three checks are on the rendered file.",
        "",
        "| check | status | what was measured instead |",
        "| --- | --- | --- |",
        "| headphones | unavailable | No headphone listening was possible. |",
        "| phone speaker | unavailable | No phone-speaker listening was possible. |",
        "| mono | unavailable | Listening in mono was not possible. The rendered file was measured instead. |",
        "",
        "## Measured on the rendered file",
        "",
        f"- Channels: {channel}",
        f"- Integrated loudness {loud.get('I')} LUFS, true peak {loud.get('TP')} dBTP, LRA {loud.get('LRA')} LU (ffmpeg ebur128 on the rendered file).",
        bed_line,
        f"- Speech-gate pauses: median {None if not gaps else gaps.get('median')} ms, max {gap_max} ms. Dead air over 0.6 s (0.7 s after a reveal) is flagged on the cue sheet.",
        "- Cue levels are a constant gain against the nearby voice peak. The voice was not raised to beat an effect. Nothing was ducked.",
        "",
        "No human listening check was possible.",
        "",
    ]
    path = dest.with_name(dest.stem + "-handoff.md")
    path.write_text("\n".join(lines))
    return path


def render(reel, dest, work=None):
    plan = plan_reel(reel)
    preview(plan)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    work = Path(work or f"/tmp/brandon-{reel}")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    print("voice", flush=True)
    voice = voice_from_spans(plan["spec"]["source"], plan["spans"])
    gaps = measure_gaps(voice)
    print("  gaps", gaps, flush=True)
    n = int(round(plan["duration"] * SR))
    if len(voice) < n:
        voice = np.pad(voice, (0, n - len(voice)))
    voice = voice[:n]
    from brandon_v2 import clean_voice, kill_dc
    voice = clean_voice(voice, plan["reel"])
    level_cues(voice, plan["cues"], plan["words"])
    plan["cues"] = _drop_stacks(plan["cues"])
    bed, placed = mix_sfx(plan["cues"], n)
    events = sfx_events(bed)
    per_min = len(events) / plan["duration"] * 60
    print(f"  sfx events {len(events)} ({per_min:.1f}/min)", flush=True)
    # Drop thumps first if the acoustic count is over the cap. Never drop a pop,
    # a Wrong Answer, a tick, or a shutter.
    if per_min > 39:
        thump_times = {round(c.t, 3) for c in plan["cues"] if c.role == "thump"}
        for kill in sorted(thump_times):
            plan["cues"] = [c for c in plan["cues"] if not (c.role == "thump" and abs(c.t - kill) < 0.02)]
            bed, placed = mix_sfx(plan["cues"], n)
            events = sfx_events(bed)
            per_min = len(events) / plan["duration"] * 60
            print(f"  dropped thump {kill:.2f} -> {len(events)} ({per_min:.1f}/min)", flush=True)
            if per_min <= 38:
                break
    if per_min > 40:
        # Impacts are optional. They usually merge with the pop, so this is a backstop.
        plan["cues"] = [c for c in plan["cues"] if c.role != "impact"]
        bed, placed = mix_sfx(plan["cues"], n)
        events = sfx_events(bed)
        per_min = len(events) / plan["duration"] * 60
        print(f"  dropped impacts -> {len(events)} ({per_min:.1f}/min)", flush=True)
    stems = dest.parent
    _write_wav(stems / f"{dest.stem}-vocals.wav", voice)
    _write_wav(stems / f"{dest.stem}-fx.wav", bed)
    # The event list exists before any picture frame is encoded.
    print("cue sheet", flush=True)
    write_cue_sheet(dest, plan, voice, bed, placed)
    print("base video", flush=True)
    base = render_base(plan, work)
    print("overlay", flush=True)
    overlay = render_overlay(plan, work)
    print("mix", flush=True)
    mix, info = fit_loudness(voice, bed)
    mix = kill_dc(mix)
    # The high-pass can put a sample back over the ceiling.
    ceil = 10 ** (-2.0 / 20)
    mix = np.clip(mix, -ceil, ceil).astype(np.float32)
    wav = work / "mix.wav"
    stereo = np.column_stack([mix, mix])
    # write stereo 16-bit
    pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(wav), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    print("mux", info, flush=True)
    mux(base, overlay, wav, dest)
    loud = loudness_file(dest)
    print("loudness", loud, flush=True)
    # If the encode drifted, apply one more constant gain via a second pass.
    if loud["I"] < -16.0 or loud["I"] > -14.0 or loud["TP"] > -1.0:
        shift = -15.0 - loud["I"]
        if loud["TP"] + shift > -1.5:
            shift = -1.5 - loud["TP"]
        tuned = work / "mix2.wav"
        adjusted = mix * 10 ** (shift / 20)
        stereo = np.column_stack([adjusted, adjusted])
        pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(tuned), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(SR)
            f.writeframes(pcm.tobytes())
        mux(base, overlay, tuned, dest)
        loud = loudness_file(dest)
        print("reloud", loud, "shift", round(shift, 2), flush=True)
    labels = [[s.label, round(s.t0, 3), round(s.t1, 3)] for s in plan["shots"]]
    label_path = dest.with_name(dest.stem + "-labels.json")
    label_path.write_text(json.dumps(labels))
    log_path = dest.with_name(dest.stem + "-sfx-log.json")
    log_path.write_text(json.dumps({
        "reel": plan["reel"], "keyword": plan["spec"]["keyword"],
        "cues": placed, "acoustic_events": [round(t, 3) for t in events],
        "events_per_min": round(per_min, 2),
    }, indent=1))
    import hashlib
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    receipt = {
        "style": "brandon-v2",
        "reel": plan["reel"],
        "file": str(dest),
        "sha256": digest,
        "duration": plan["duration"],
        "keyword": plan["spec"]["keyword"],
        "loudness": loud,
        "gaps": gaps,
        "title_off": plan["title_off"],
        "cta_t": plan["cta_t"],
        "caption_baseline": CAPTION_BOTTOM,
        "green": GREEN_HEX,
        "sfx_events_per_min": round(per_min, 2),
        "shots": [
            {"t0": round(s.t0, 3), "t1": round(s.t1, 3), "kind": s.kind, "label": s.label,
             "scale": s.scale, "push": s.push, "bw": s.bw, "flash": s.flash, "plate": s.plate}
            for s in plan["shots"]
        ],
    }
    dest.with_name(dest.stem + "-receipt.json").write_text(json.dumps(receipt, indent=1))
    from brandon_v2 import write_diff
    write_diff(dest, plan)
    write_handoff(dest, loud, gaps)
    print("wrote", dest, digest)
    return plan


def main():
    ap = argparse.ArgumentParser(description="Render a reel in the Brandon new style")
    ap.add_argument("--reel", required=True, choices=["07", "09"])
    ap.add_argument("--out")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--check-audio", action="store_true")
    args = ap.parse_args()
    if args.plan or args.check_audio:
        planned = plan_reel(args.reel)
        preview(planned)
        if args.check_audio:
            voice = voice_from_spans(planned["spec"]["source"], planned["spans"])
            print(json.dumps(measure_gaps(voice), indent=1))
        return 0
    if not args.out:
        ap.error("--out is required to render")
    render(args.reel, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
