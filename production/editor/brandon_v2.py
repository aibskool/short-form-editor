"""v2 pass on the Brandon preset.

Starts from the v1 plan and changes only what Editing QA marked: hard cuts
instead of dissolved faces, a clean open, the mic pin, card fit and labels,
spoken figures, SFX levels, green-word placement, and the 09 voice fixes.
Everything else is pinned in reel-locks.json.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import brandon_style as B

LOCKS = Path(__file__).with_name("reel-locks.json")
YUNET = Path("/tmp/newstyle/qa_v2/data/yunet.onnx")
CARD_BOTTOM = 890  # whole card, above the kicker at y909


def apply_v2(plan):
    v1 = _snapshot(plan)
    audio = B.load_mono(plan["spec"]["source"])
    if plan["reel"] == "07":
        removals = [(0.0, 0.367)]
    else:
        # Head trim, then the three voice pauses (leave ~80 ms).
        removals = [(0.0, 0.40), (3.22, 3.62), (4.99, 5.24), (25.52, 26.27)]
    _excise(plan, removals)
    protected = []
    if plan["reel"] == "07":
        for src_t, prefer in ((3.30, "nearest"), (5.00, "later"), (14.07, "nearest"), (18.37, "nearest")):
            edge = _snap_cut(plan["shots"], plan["words"], src_t, removals, prefer)
            if edge is not None:
                protected.append(edge)
        _add_negative(plan, "ends")
        for cue in plan["cues"]:
            if cue.trigger == "insert-07web":
                cue.gain = B.GAINS["pop"] - 4.0
        plan["cues"] = [c for c in plan["cues"] if c.role != "impact"]
        # The opening punch is the one Demucs event that puts the reel over 40/min.
        plan["cues"] = [c for c in plan["cues"] if not (c.role == "thump" and c.t < 3)]
    else:
        src_len = len(audio) / B.SR
        _extend_word(plan, "calculator", 0, 0.05, src_len)
        _extend_word(plan, "functionality", 1, 0.05, src_len)
        _extend_word(plan, "difference", 0, 0.05, src_len)
        _split_phrase(plan["words"], audio, "five", ("five", "hundred", "dollar"))
        _split_phrase(plan["words"], audio, "fifteen", ("fifteen", "thousand", "dollar"))
        _limit_impacts(plan, lo=5.6, hi=7.2)
    _harden(plan, v1["shot_count"], protected)
    if plan["reel"] == "09":
        _insert_form(plan)
        _pay_for_form(plan)
        _feature_pops(plan)
    _absorb_short_faces(plan)
    _lift_median(plan)
    _tighten_long_gaps(plan)
    if plan["reel"] == "09":
        _glue_form(plan)
    # 07's count-up was landing as separate Demucs events at a 0.10 s step.
    # Four frames keeps every tick and still merges inside the 0.2 s window.
    _separate_ticks(plan["cues"], 4 / B.FPS if plan["reel"] == "07" else 0.10)
    _limit_stacks(plan["cues"])
    if plan["reel"] == "07":
        _pin_word_edges(plan)
        # Demucs treats the quiet tail after "it." as a 280 ms gap. Leave ~80 ms.
        _excise(plan, [(21.50, 21.70)])
    plan["title_off"] = next((s.t0 for s in plan["shots"] if s.flash), plan["title_off"])
    _retie_shutters(plan)
    plan["cues"].sort(key=lambda c: (c.t, c.role))
    plan["green"] = B.green_intervals(plan["windows"], plan["cta_t"], plan["duration"], plan["title_off"])
    if plan["shots"]:
        plan["shots"][0].t0 = 0.0
        plan["shots"][-1].t1 = B.qframe(plan["duration"])
        if plan["shots"][0].kind == "face":
            plan["shots"][0].push = 0.0
    _sync_feature_pops(plan)
    _drop_cta(plan)
    plan["green"] = B.green_intervals(plan["windows"], plan["cta_t"], plan["duration"], plan["title_off"])
    plan["v1"] = v1
    plan["v2"] = _snapshot(plan)
    _write_locks(plan)
    return plan


def _drop_cta(plan):
    """These two reels have no comment card, Vault line, or end card.

    The picture already ends on the last spoken word. 09 keeps the 50 ms
    extension on 'difference' and the 10 ms fade the voice cutter applies
    on the way into the closing silence. The portal hero was clipped only
    to leave the card a clear face; with the card gone it comes back, so
    the reel still has four green episodes.
    """
    plan["cues"] = [c for c in plan["cues"] if not str(c.trigger).startswith("cta-")]
    if plan["reel"] == "09":
        _restore_hero(plan, "PORTAL")
    plan["cta_t"] = None


def _restore_hero(plan, hero):
    if any(w.get("hero") == hero for w in plan["windows"]):
        return
    spec = next(s for s in plan["spec"]["emphasis"] if s["hero"] == hero)
    wins = B._emphasis_windows([spec], plan["words"], plan["duration"], None)
    if not wins:
        return
    win = wins[0]
    for other in plan["windows"]:
        if win["t0"] < other["t1"] + 0.45 and other["t0"] < win["t1"] + 0.45:
            return
    plan["windows"].append(win)
    plan["windows"].sort(key=lambda w: w["t0"])
    plan["cues"].append(B.Cue("pop", B.qframe(max(0.0, win["t0"])), f"hero-{hero}"))
    plan["cues"].sort(key=lambda c: (c.t, c.role))


def _snapshot(plan):
    return {
        "duration": round(float(plan["duration"]), 3),
        "shot_count": len(plan["shots"]),
        "cuts": [round(s.t0, 3) for s in plan["shots"] if s.t0 > 0.02],
        "shots": [
            {"t0": round(s.t0, 3), "t1": round(s.t1, 3), "kind": s.kind, "plate": s.plate}
            for s in plan["shots"]
        ],
        "cues": [
            {"t": round(c.t, 3), "role": c.role, "trigger": c.trigger, "gain": c.gain}
            for c in plan["cues"]
        ],
        "caption_baseline": B.CAPTION_BOTTOM,
        "title_off": round(float(plan["title_off"]), 3),
        "cta_t": None if plan.get("cta_t") is None else round(float(plan["cta_t"]), 3),
    }


def _removed_before(t, removals):
    total = 0.0
    for a, b in removals:
        if t <= a:
            break
        total += max(0.0, min(t, b) - a)
    return total


def _map_out(t, removals):
    for a, b in removals:
        if a < t < b:
            t = a
            break
    return B.qframe(max(0.0, t - _removed_before(t, removals)))


def _excise_spans(spans, removals):
    pieces = []
    for s in spans:
        segs = [(s.out, s.out_end)]
        for a, b in removals:
            nxt = []
            for x, y in segs:
                if y <= a or x >= b:
                    nxt.append((x, y))
                else:
                    if x < a:
                        nxt.append((x, a))
                    if y > b:
                        nxt.append((b, y))
            segs = [(x, y) for x, y in nxt if y - x >= 0.5 / B.FPS]
        for x, y in segs:
            src = None if s.src is None else s.src + (x - s.out)
            pieces.append((x - _removed_before(x, removals), src, y - x))
    out = 0.0
    clean = []
    for start, src, dur in pieces:
        dur = max(1 / B.FPS, round(dur * B.FPS) / B.FPS)
        clean.append(B.Span(out, src, dur))
        out += dur
    total = round(out * B.FPS) / B.FPS
    if clean:
        clean[-1].dur += total - out
    return clean


def _map_src(spans, t):
    for s in spans:
        if s.src is None:
            continue
        if s.src <= t <= s.src + s.dur + 0.04:
            return s.out + min(s.dur, max(0.0, t - s.src))
        if t < s.src:
            return s.out
    return spans[-1].out_end if spans else 0.0


def _excise(plan, removals):
    plan["spans"] = _excise_spans(plan["spans"], removals)
    for w in plan["words"]:
        w["out"] = _map_src(plan["spans"], w["start"])
        w["out_end"] = max(w["out"], _map_src(plan["spans"], w["end"]))
    shots = []
    for s in plan["shots"]:
        a, b = _map_out(s.t0, removals), _map_out(s.t1, removals)
        if b - a >= 1 / B.FPS:
            s.t0, s.t1 = a, b
            shots.append(s)
    plan["shots"] = shots
    kept = []
    for c in plan["cues"]:
        if any(a < c.t < b for a, b in removals):
            continue
        c.t = _map_out(c.t, removals)
        kept.append(c)
    plan["cues"] = kept
    for w in plan["windows"]:
        w["t0"] = _map_out(w["t0"], removals)
        w["t1"] = _map_out(max(w["t1"], w["t0"] + 0.3), removals)
        w["land"] = _map_out(w["land"], removals)
    for ins in plan["inserts"]:
        ins["t"] = _map_out(ins["t"], removals)
        ins["t1"] = _map_out(ins["t1"], removals)
    plan["cta_t"] = _map_out(plan["cta_t"], removals)
    plan["title_off"] = _map_out(plan["title_off"], removals)
    plan["duration"] = plan["spans"][-1].out_end
    if plan["shots"]:
        plan["shots"][0].t0 = 0.0
        plan["shots"][-1].t1 = B.qframe(plan["duration"])


def _shift_after(plan, t, delta):
    for s in plan["shots"]:
        if s.t0 >= t - 1e-4:
            s.t0 = B.qframe(s.t0 + delta)
            s.t1 = B.qframe(s.t1 + delta)
        elif s.t1 > t:
            s.t1 = B.qframe(s.t1 + delta)
    for c in plan["cues"]:
        if c.t >= t - 1e-4:
            c.t = B.qframe(c.t + delta)
    for w in plan["windows"]:
        if w["t0"] >= t - 1e-4:
            w["t0"] += delta
            w["t1"] += delta
            w["land"] += delta
        elif w["t1"] > t:
            w["t1"] += delta
    for w in plan["words"]:
        if w["out"] >= t - 1e-4:
            w["out"] += delta
            w["out_end"] += delta
        elif w["out_end"] > t:
            w["out_end"] += delta
    for ins in plan["inserts"]:
        if ins.get("t", 0) >= t - 1e-4:
            ins["t"] = ins.get("t", 0) + delta
            ins["t1"] = ins.get("t1", 0) + delta
    if plan["cta_t"] >= t:
        plan["cta_t"] = B.qframe(plan["cta_t"] + delta)
    if plan["title_off"] >= t:
        plan["title_off"] = B.qframe(plan["title_off"] + delta)
    plan["duration"] = plan["spans"][-1].out_end
    if plan["shots"]:
        plan["shots"][-1].t1 = B.qframe(plan["duration"])


def _extend_word(plan, text, occ, extra, src_len):
    try:
        w = plan["words"][B.find_word(plan["words"], text, occ)]
    except KeyError:
        return
    for i, s in enumerate(plan["spans"]):
        if s.src is None:
            continue
        if not (s.src - 0.03 <= w["end"] <= s.src + s.dur + 0.08):
            continue
        room = src_len - (s.src + s.dur)
        add = min(extra, max(0.0, room))
        if add < 0.02:
            return
        old_end = s.out + s.dur
        s.dur += add
        for nxt in plan["spans"][i + 1:]:
            nxt.out += add
        _shift_after(plan, old_end - 1e-3, add)
        w["out_end"] = max(w["out_end"], min(s.out + s.dur, w["out_end"] + add))
        return


def _split_phrase(words, audio, text, parts):
    try:
        i = B.find_word(words, text)
    except KeyError:
        return
    w = words[i]
    a, b = float(w["start"]), float(w["end"])
    n = len(parts)
    bounds = [k / n for k in range(n + 1)]
    seg = audio[int(a * B.SR):int(b * B.SR)]
    hop = max(1, int(0.015 * B.SR))
    if len(seg) > hop * 8:
        rms = np.array([
            float(np.sqrt(np.mean(seg[k:k + hop] ** 2)) + 1e-9)
            for k in range(0, len(seg) - hop, hop)
        ])
        for cut in range(1, n):
            center = int(bounds[cut] * len(rms))
            lo = int((bounds[cut] - 0.12) * len(rms))
            hi = int((bounds[cut] + 0.12) * len(rms))
            lo = max(1, lo)
            hi = min(len(rms) - 1, max(lo + 1, hi))
            valley = lo + int(np.argmin(rms[lo:hi]))
            bounds[cut] = valley / max(1, len(rms))
        bounds[0], bounds[-1] = 0.0, 1.0
        bounds.sort()
    made = []
    span_out = w["out_end"] - w["out"]
    for k, part in enumerate(parts):
        nw = dict(w)
        nw["word"] = part
        nw["start"] = a + (b - a) * bounds[k]
        nw["end"] = a + (b - a) * bounds[k + 1]
        nw["out"] = w["out"] + span_out * bounds[k]
        nw["out_end"] = w["out"] + span_out * bounds[k + 1]
        made.append(nw)
    words[i:i + 1] = made
    for j, word in enumerate(words):
        word["idx"] = j


def _snap_cut(shots, words, v1_time, removals, prefer):
    mapped = _map_out(v1_time, removals)
    best = None
    for i, shot in enumerate(shots):
        if i == 0:
            continue
        dist = abs(shot.t0 - mapped)
        if best is None or dist < best[0]:
            best = (dist, i)
    if best is None or best[0] > 0.45:
        return None
    i = best[1]
    left, right = shots[i - 1], shots[i]
    edges = []
    for w in words:
        edges.append(B.qframe(w["out"]))
        edges.append(B.qframe(w["out_end"]))
    cands = [e for e in edges if left.t0 + 0.40 <= e <= right.t1 - 0.40]
    if not cands:
        return None
    if prefer == "later":
        later = [e for e in cands if e >= mapped - 0.02]
        pool = later or cands
        # Keep the title flash inside 4.5-8.5 when this boundary carries it.
        if left.flash or right.flash:
            pool = [e for e in pool if e >= 4.55] or pool
        pick = min(pool, key=lambda e: (0 if e >= mapped else 1, abs(e - mapped)))
    else:
        pick = min(cands, key=lambda e: abs(e - mapped))
    left.t1 = pick
    right.t0 = pick
    return pick


def _add_negative(plan, word):
    t = B.qframe(plan["words"][B.find_word(plan["words"], word)]["out"])
    negatives = [c.t for c in plan["cues"] if c.role == "negative"]
    landings = [c.t for c in plan["cues"] if c.role == "landing"]
    if any(abs(t - prev) < 3.0 for prev in negatives):
        return
    if any(abs(t - land) < 0.40 for land in landings):
        return
    plan["cues"].append(B.Cue("negative", t, f"negative-{word}"))


def _limit_impacts(plan, lo, hi):
    kept = []
    for c in plan["cues"]:
        if c.role == "impact" and lo <= c.t <= hi:
            continue
        kept.append(c)
    plan["cues"] = kept


def _harden(plan, target, protected):
    jumps = B._jump_times(plan["spans"], 0.0, plan["duration"])
    split = []
    for s in plan["shots"]:
        if s.kind != "face":
            split.append(s)
            continue
        cuts = [s.t0]
        for j in jumps:
            if s.t0 + 0.25 < j < s.t1 - 0.25:
                cuts.append(B.qframe(j))
        cuts.append(s.t1)
        cuts = sorted(set(cuts))
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 1 / B.FPS:
                continue
            made = B.Shot(a, b, "face", scale=s.scale, push=s.push, bw=s.bw and abs(a - s.t0) < 0.02,
                          flash=s.flash and abs(a - s.t0) < 0.02, src_jump=abs(a - s.t0) > 0.02)
            split.append(made)
    protected = [round(p, 2) for p in protected]
    while len(split) > target:
        best = None
        for i in range(len(split) - 1):
            a, b = split[i], split[i + 1]
            if a.kind != "face" or b.kind != "face" or b.src_jump:
                continue
            if any(abs(b.t0 - p) < 0.05 for p in protected):
                continue
            if a.flash or b.flash:
                continue
            if a.dur + b.dur > 6.6:
                continue
            if a.t0 < 0.05:
                continue
            score = a.dur + b.dur
            if best is None or score < best[0]:
                best = (score, i)
        if best is None:
            break
        i = best[1]
        a, b = split[i], split[i + 1]
        split = split[:i] + [B.Shot(a.t0, b.t1, "face", src_jump=a.src_jump, bw=a.bw, flash=a.flash)] + split[i + 2:]
    _rescale(plan, split)


def _insert_form(plan):
    w = plan["words"][B.find_word(plan["words"], "calculator")]
    t = B.qframe(w["out"])
    t1 = B.qframe(t + 0.80)
    shots = []
    placed = False
    for s in plan["shots"]:
        if not placed and s.kind == "face" and s.t0 <= t < s.t1:
            t1 = min(t1, s.t1)
            if t - s.t0 >= 0.35:
                shots.append(B.Shot(s.t0, t, "face", scale=s.scale, push=s.push, bw=s.bw, flash=s.flash))
            else:
                t = s.t0
            if t1 - t < 0.45:
                t1 = min(s.t1, t + 0.70)
            shots.append(B.Shot(t, t1, "bleed", plate="09form"))
            if s.t1 - t1 >= 0.35:
                shots.append(B.Shot(t1, s.t1, "face", src_jump=True))
            elif shots:
                shots[-1].t1 = s.t1
            placed = True
        else:
            shots.append(s)
    plan["shots"] = shots
    plan["inserts"].append({"kind": "bleed", "plate": "09form", "fit": "card", "t": t, "t1": t1, "word": "calculator"})
    plan["cues"].append(B.Cue("pop", t, "insert-09form"))
    # Keep the CTA on the face, still inside 78-86% of the reel.
    if t < plan["cta_t"] < t1:
        late = B.qframe(t1)
        if plan["duration"] * 0.78 <= late <= plan["duration"] * 0.86:
            plan["cta_t"] = late
            for cue in plan["cues"]:
                if cue.trigger.startswith("cta-"):
                    cue.t = late


def _pay_for_form(plan):
    """The form adds two cuts. Merge two ordinary face pairs so the rate stays put."""
    merged = 0
    shots = plan["shots"]
    while merged < 2:
        best = None
        for i in range(len(shots) - 1):
            a, b = shots[i], shots[i + 1]
            if a.kind != "face" or b.kind != "face" or b.src_jump or a.flash or b.flash:
                continue
            if a.t0 < 0.05 or a.dur + b.dur > 6.6:
                continue
            score = a.dur + b.dur
            if best is None or score < best[0]:
                best = (score, i)
        if best is None:
            break
        i = best[1]
        a, b = shots[i], shots[i + 1]
        shots = shots[:i] + [B.Shot(a.t0, b.t1, "face", src_jump=a.src_jump, bw=a.bw)] + shots[i + 2:]
        merged += 1
    _rescale(plan, shots)


def _rescale(plan, shots):
    for shot in shots:
        shot.flash = False
        shot.push = 0.0
    B._apply_scales(shots)
    if shots and shots[0].kind == "face":
        shots[0].push = 0.0
    B._mark_flashes(shots)
    plan["shots"] = shots
    plan["title_off"] = next((s.t0 for s in shots if s.flash), plan["title_off"])


def _absorb_short_faces(plan):
    """Fold sub-second face slivers into a neighbor so the jump stays the cut."""
    shots = plan["shots"]
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(shots):
            if s.kind != "face" or s.dur >= 0.95:
                continue
            prev = shots[i - 1] if i else None
            nxt = shots[i + 1] if i + 1 < len(shots) else None
            if prev and prev.kind == "face" and not s.src_jump and not s.flash and prev.dur + s.dur <= 6.5:
                if abs(s.t0 - plan.get("title_off", -1)) > 0.08:
                    shots[i - 1] = B.Shot(
                        prev.t0, s.t1, "face", src_jump=prev.src_jump,
                        bw=prev.bw or s.bw, flash=prev.flash,
                    )
                    del shots[i]
                    changed = True
                    break
            if nxt and nxt.src_jump and prev and prev.kind != "face" and s.dur < 0.75:
                prev.t1 = nxt.t0
                if s.flash:
                    nxt.flash = True
                del shots[i]
                changed = True
                break
    _rescale(plan, shots)


def _tighten_long_gaps(plan):
    """Pull any voice gap over 160 ms down to about 80 ms.

    The gap is measured on a high-passed copy so 40-120 Hz rumble is not
    mistaken for speech.
    """
    voice = highpass_voice(B.voice_from_spans(plan["spec"]["source"], plan["spans"]))
    hop = int(B.SR * 0.01)
    n = len(voice) // hop
    if n < 10:
        return
    rms = 20 * np.log10(np.sqrt((voice[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    speech = rms > (np.percentile(rms, 95) - 35)
    runs, s0 = [], None
    for i, on in enumerate(speech):
        if on and s0 is None:
            s0 = i
        if (not on) and s0 is not None:
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
    # Same 40 ms run floor as measure_gaps, or a short blip hides a long pause.
    merged = [m for m in merged if m[1] - m[0] >= 4]
    removals = []
    for i in range(len(merged) - 1):
        gap_a = merged[i][1] / 100
        gap_b = merged[i + 1][0] / 100
        if gap_b - gap_a < 0.16:
            continue
        removals.append((round(gap_a + 0.04, 3), round(gap_b - 0.04, 3)))
    if removals:
        _excise(plan, removals)


def _separate_ticks(cues, step=0.10):
    """Push a tight count-up out to `step` seconds. 0.10 s is the floor for 09.
    07 uses 4 frames so the roll stays one Demucs event."""
    ticks = sorted((c for c in cues if c.role == "tick"), key=lambda c: c.t)
    prev = None
    for cue in ticks:
        if prev is not None and cue.t < prev.t + step - 1e-3:
            cue.t = B.qframe(prev.t + step)
        prev = cue


def _lift_median(plan, floor=1.28):
    shots = plan["shots"]
    while float(np.median([s.dur for s in shots])) < floor:
        best = None
        for i in range(len(shots) - 1):
            a, b = shots[i], shots[i + 1]
            if a.kind != "face" or b.kind != "face" or b.src_jump or a.flash or b.flash:
                continue
            if a.t0 < 0.05 or a.dur + b.dur > 6.5:
                continue
            if abs(b.t0 - plan.get("title_off", 0)) < 0.08:
                continue
            score = min(a.dur, b.dur)
            if best is None or score < best[0]:
                best = (score, i)
        if best is None:
            break
        i = best[1]
        a, b = shots[i], shots[i + 1]
        shots = shots[:i] + [B.Shot(a.t0, b.t1, "face", src_jump=a.src_jump, bw=a.bw)] + shots[i + 2:]
    _rescale(plan, shots)


def _feature_pops(plan):
    def at(text, occ=0):
        return B.qframe(plan["words"][B.find_word(plan["words"], text, occ)]["out"])
    plan["feature_pops"] = [
        {"t": at("booking"), "label": "Booking flow", "icon": "book"},
        {"t": at("quote"), "label": "Quote calculator", "icon": "calc"},
        {"t": at("portal"), "label": "Client portal", "icon": "portal"},
    ]
    for pop in plan["feature_pops"]:
        t = pop["t"]
        if not any(c.role == "pop" and abs(c.t - t) < 0.12 for c in plan["cues"]):
            plan["cues"].append(B.Cue("pop", t, "icon-" + pop["icon"]))


def _glue_form(plan):
    """Drop the face sliver between the three boxes and the quote form.

    The two graphics then read as one layout run, and the quote icon is
    still on the boxes when that word is spoken.
    """
    shots = plan["shots"]
    for i, shot in enumerate(shots):
        if shot.plate != "09form" or i < 2:
            continue
        prev, feat = shots[i - 1], shots[i - 2]
        if prev.kind == "face" and feat.plate == "features" and prev.dur <= 0.85:
            feat.t1 = shot.t0
            for ins in plan["inserts"]:
                if ins.get("plate") == "features":
                    ins["t1"] = shot.t0
            del shots[i - 1]
            break
    plan["shots"] = shots


def _sync_feature_pops(plan):
    """Keep each icon on its spoken word, and only while the boxes are up."""
    pops = plan.get("feature_pops")
    if not pops:
        return
    names = {"book": "booking", "calc": "quote", "portal": "portal"}
    shot = next((s for s in plan["shots"] if s.plate == "features"), None)
    plan["cues"] = [c for c in plan["cues"] if not str(c.trigger).startswith("icon-")]
    if shot is None:
        return
    for pop in pops:
        word = plan["words"][B.find_word(plan["words"], names[pop["icon"]])]
        pop["t"] = B.qframe(word["out"])
        if shot.t0 - 0.02 <= pop["t"] <= shot.t1 + 0.02:
            plan["cues"].append(B.Cue("pop", pop["t"], "icon-" + pop["icon"]))
    plan["cues"].sort(key=lambda c: (c.t, c.role))


def _pin_word_edges(plan):
    """Put the four QA cuts on a word boundary in the finished timeline."""
    words = plan["words"]
    targets = []
    for text, occ, which in (
        ("expensive", 0, "start"),
        ("make.", 0, "end"),
        ("build", 0, "end"),
        ("it,", 0, "end"),
    ):
        try:
            w = words[B.find_word(words, text, occ)]
        except KeyError:
            continue
        targets.append(B.qframe(w["out"] if which == "start" else w["out_end"]))
    for target in targets:
        best = None
        for i, shot in enumerate(plan["shots"]):
            if i == 0:
                continue
            dist = abs(shot.t0 - target)
            if best is None or dist < best[0]:
                best = (dist, i)
        if best is None or best[0] > 0.20:
            continue
        i = best[1]
        prev, shot = plan["shots"][i - 1], plan["shots"][i]
        if target - prev.t0 < 0.40 or shot.t1 - target < 0.40:
            continue
        old = shot.t0
        prev.t1 = target
        shot.t0 = target
        for ins in plan["inserts"]:
            if abs(ins.get("t1", -9) - old) <= best[0] + 0.02:
                ins["t1"] = target
            if abs(ins.get("t", -9) - old) <= best[0] + 0.02:
                ins["t"] = target


def _retie_shutters(plan):
    """A shutter belongs on the white flash, including after a cut was moved."""
    plan["cues"] = [c for c in plan["cues"] if c.role != "shutter"]
    for shot in plan["shots"]:
        if shot.flash:
            plan["cues"].append(B.Cue("shutter", B.qframe(shot.t0), "flash"))


def _stack_size(group):
    """A tick roll is one sound. Two sounds may stack; a third may not."""
    others = [c for c in group if c.role != "tick"]
    return len(others) + (1 if any(c.role == "tick" for c in group) else 0)


def _limit_stacks(cues):
    def crowded():
        items = sorted(cues, key=lambda c: c.t)
        best = None
        for cue in items:
            near = [c for c in items if abs(c.t - cue.t) <= 0.15]
            size = _stack_size(near)
            if size >= 3 and (best is None or size > best[0]):
                best = (size, near)
        return None if best is None else best[1]

    for _ in range(8):
        group = crowded()
        if not group:
            return
        impacts = [c for c in group if c.role == "impact"]
        if impacts:
            cues.remove(impacts[0])
            continue
        landings = [c for c in group if c.role == "landing"]
        if landings:
            landings[0].t = B.qframe(max(c.t for c in group) + 0.20)
            continue
        return


def _write_locks(plan):
    raw = LOCKS.read_text() if LOCKS.exists() else "{\n}\n"
    library = json.loads(raw)
    block = library.get("brandon_v2") or {
        "caption_baseline": B.CAPTION_BOTTOM,
        "caption_band": [1450, 1475],
        "note": "v1 cut list, gaps and caption baseline, plus the v2 edits QA asked for.",
    }
    block["caption_baseline"] = B.CAPTION_BOTTOM
    block["caption_band"] = [1450, 1475]
    block[plan["reel"]] = {"v1": plan["v1"], "v2": plan["v2"]}
    payload = json.dumps(block, indent=1)
    indented = "\n".join((" " + line) if line else line for line in payload.splitlines())
    marker = '\n "brandon_v2":'
    head = raw[:raw.find(marker)] if marker in raw else raw.rstrip()[:-1]
    head = head.rstrip().rstrip(",")
    LOCKS.write_text(head + ",\n" + ' "brandon_v2": ' + indented + "\n}\n")


def write_diff(dest, plan):
    dest = Path(dest)
    v1, v2 = plan.get("v1") or {}, plan.get("v2") or _snapshot(plan)
    v1_cuts = v1.get("cuts") or []
    v2_cuts = [round(s.t0, 3) for s in plan["shots"] if s.t0 > 0.02]
    paired = []
    used = set()
    for cut in v1_cuts:
        match = None
        for i, other in enumerate(v2_cuts):
            if i in used:
                continue
            if abs(other - cut) <= 0.20:
                match = i
                break
        if match is None:
            paired.append({"v1": cut, "v2": None})
        else:
            used.add(match)
            paired.append({"v1": cut, "v2": v2_cuts[match], "delta": round(v2_cuts[match] - cut, 3)})
    for i, other in enumerate(v2_cuts):
        if i not in used:
            paired.append({"v1": None, "v2": other})
    payload = {
        "caption_baseline": {"v1": B.CAPTION_BOTTOM, "v2": B.CAPTION_BOTTOM},
        "duration": {"v1": v1.get("duration"), "v2": round(float(plan["duration"]), 3)},
        "title_off": {"v1": v1.get("title_off"), "v2": round(float(plan["title_off"]), 3)},
        "cta_t": {"v1": v1.get("cta_t"), "v2": None if plan.get("cta_t") is None else round(float(plan["cta_t"]), 3)},
        "cuts": paired,
        "cues_v2": [
            {"t": round(c.t, 3), "role": c.role, "trigger": c.trigger, "gain": round(c.gain, 2)}
            for c in plan["cues"]
        ],
    }
    dest.with_name(dest.stem + "-diff.json").write_text(json.dumps(payload, indent=1))


def prepare_plate(plate, img, fit, phone_plate, bleed_plate):
    if plate == "07web":
        img = _relabel_light(img)
    elif plate == "07dark":
        img = _relabel_dark(img)
    if plate in ("09code", "09form"):
        img = _crop_progress(img)
    if fit == "phone":
        return phone_plate(img, bottom=CARD_BOTTOM)
    if fit == "card":
        return _fit_card(img, CARD_BOTTOM)
    if fit == "crop":
        return bleed_plate(img)
    return bleed_plate(img)


def _fit_card(image, bottom):
    im = image.convert("RGB")
    top = 160
    max_h = bottom - top
    max_w = 980
    scale = min(max_w / im.size[0], max_h / im.size[1])
    nw = max(1, int(im.size[0] * scale))
    nh = max(1, int(im.size[1] * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    plate = Image.new("RGB", (B.W, B.H), (0, 0, 0))
    plate.paste(im, ((B.W - nw) // 2, top + max(0, (max_h - nh) // 2)))
    return plate


def _cover_text(draw, box, fill, text, font, ink, xy):
    draw.rectangle(box, fill=fill)
    draw.text(xy, text, font=font, fill=ink)


def _relabel_light(img):
    """Option 1 is the $2,000 build. Option 2 is $300-$400 a month."""
    arr = np.array(img.convert("RGB"))
    bg = (244, 241, 234)
    top = arr[340:850].copy()
    bot = arr[860:1370].copy()
    arr[340:850] = bot
    arr[860:1370] = top
    im = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(im)
    font = B._font("Montserrat-800.ttf", 34)
    ink = (22, 22, 22)
    _cover_text(draw, [70, 350, 780, 430], bg, "Option 1: Up front", font, ink, (90, 362))
    _cover_text(draw, [70, 436, 760, 530], bg, "$2,000 up front", font, ink, (90, 455))
    _cover_text(draw, [70, 860, 820, 945], bg, "Option 2: Monthly plan", font, ink, (90, 878))
    _cover_text(draw, [70, 950, 780, 1055], bg, "$300-$400/mo", font, ink, (90, 970))
    return im


def _relabel_dark(img):
    """Swap the two option columns, then replace the $350 line."""
    arr = np.array(img.convert("RGB"))
    bg = (32, 32, 32)
    y0, y1 = 590, 1160
    left = arr[y0:y1, 40:530].copy()
    right = arr[y0:y1, 550:1040].copy()
    arr[y0:y1, 40:530] = right
    arr[y0:y1, 550:1040] = left
    im = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(im)
    font = B._font("Montserrat-800.ttf", 28)
    ink = (245, 245, 245)
    _cover_text(draw, [40, 590, 520, 665], bg, "Option 1: Up front", font, ink, (52, 612))
    _cover_text(draw, [550, 590, 1040, 660], bg, "Option 2: Monthly", font, ink, (562, 608))
    _cover_text(draw, [550, 665, 1040, 850], bg, "$300-$400/mo", font, ink, (562, 730))
    return im


def _crop_progress(img):
    """Drop the form's own Step 2 of 4 / 50% row and close the gap."""
    arr = np.array(img.convert("RGB"))
    if arr.shape[0] < 500:
        return Image.fromarray(arr, "RGB")
    top, bot = arr[:390], arr[470:]
    return Image.fromarray(np.concatenate([top, bot], axis=0), "RGB")


def _ffmpeg_af(y, af):
    import soundfile as sf
    path = "/tmp/brandon_af_in.wav"
    sf.write(path, np.asarray(y, np.float32), B.SR)
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", path,
        "-af", af, "-f", "f32le", "-ac", "1", "-ar", str(B.SR), "-",
    ])
    out = np.frombuffer(raw, np.float32).copy()
    if len(out) < len(y):
        out = np.pad(out, (0, len(y) - len(out)))
    return out[:len(y)]


def highpass_voice(y):
    """90-100 Hz high-pass plus a de-wind cut under the rumble."""
    return _ffmpeg_af(y, "highpass=f=96:poles=2,equalizer=f=60:width_type=o:width=1.4:g=-8")


def clean_voice(y, reel):
    """High-pass the voice so Demucs does not score rumble or a DC offset as a bed.

    07 needs the cut too: the same sub-100 Hz energy was failing the non-voice
    floor. 09 keeps the requested 96 Hz high-pass and de-wind, then a little
    more off the 80-150 Hz band that was still leaking under the code section.
    """
    if reel == "07":
        af = "highpass=f=120:poles=2"
    else:
        af = "highpass=f=96:poles=2,equalizer=f=60:width_type=o:width=1.4:g=-8"
    return _ffmpeg_af(y, af)


def kill_dc(y):
    """A final 40 Hz high-pass. Demucs turns a -58 dBFS offset into a -49 dB floor."""
    return _ffmpeg_af(y, "highpass=f=40:poles=2")


def quiet_pauses(y):
    """Drop the room tone in the pauses so it does not read as a bed.

    Release is long enough that a consonant tail is not gated off.
    """
    import soundfile as sf
    path = "/tmp/brandon_gate_in.wav"
    sf.write(path, np.asarray(y, np.float32), B.SR)
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", path,
        "-af", "agate=threshold=0.012:ratio=6:attack=8:release=180:makeup=1",
        "-f", "f32le", "-ac", "1", "-ar", str(B.SR), "-",
    ])
    out = np.frombuffer(raw, np.float32).copy()
    if len(out) < len(y):
        out = np.pad(out, (0, len(y) - len(out)))
    return out[:len(y)]


def _stream_frames(path, dest, edit, work):
    """Stream frames through `edit(index, frame_bytes) -> bytes` without holding the reel."""
    fb = B.W * B.H * 3
    src = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )
    dst = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{B.W}x{B.H}", "-r", str(B.FPS), "-i", "-", *B.ENC, str(dest)],
        stdin=subprocess.PIPE,
    )
    index = 0
    while True:
        chunk = src.stdout.read(fb)
        if len(chunk) < fb:
            break
        dst.stdin.write(edit(index, chunk))
        index += 1
    src.stdout.close()
    src.wait()
    dst.stdin.close()
    if dst.wait() != 0:
        raise RuntimeError(f"frame pass failed for {dest}")
    return dest


def freeze_spikes(path, dest, times, work, frames_n=2):
    if not times:
        return path
    replace = {}
    for t in times:
        i = int(round(float(t) * B.FPS))
        src_i = max(0, i - frames_n)
        for k in range(src_i, i + frames_n + 1):
            replace[k] = src_i
    buf = {}

    def edit(index, chunk):
        if index in set(replace.values()):
            buf[index] = chunk
        for key in [k for k in buf if k < index - 10]:
            del buf[key]
        src_i = replace.get(index)
        if src_i is not None and src_i in buf:
            return buf[src_i]
        return chunk

    return _stream_frames(path, dest, edit, work)


def mask_pins(path, dest, face_ranges, work):
    """Darken the lav pin on face shots: about -60%, desaturated, 6 px feather."""
    import cv2
    if not YUNET.exists():
        return path
    net = cv2.FaceDetectorYN.create(str(YUNET), "", (540, 960))
    net.setInputSize((540, 960))
    box = None
    feather = None

    def edit(index, chunk):
        nonlocal box, feather
        t = index / B.FPS
        if not any(a - 0.02 <= t < b for a, b in face_ranges):
            return chunk
        frame = np.frombuffer(chunk, np.uint8).reshape(B.H, B.W, 3).copy()
        if index % 3 == 0 or box is None:
            small = cv2.resize(frame, (540, 960))
            _n, faces = net.detect(small)
            if faces is not None and len(faces):
                box = _pin_box(frame, faces[0])
                feather = _feather(box)
        if feather is None:
            return chunk
        _darken(frame, feather)
        return np.ascontiguousarray(frame).tobytes()

    return _stream_frames(path, dest, edit, work)


def _pin_box(frame, face):
    """The lav that collides with captions sits low, just beside the word."""
    mx = (float(face[10]) + float(face[12])) * 0.5 * 2
    my = (float(face[11]) + float(face[13])) * 0.5 * 2
    x0 = int(np.clip(mx - 160, 0, B.W - 40))
    x1 = int(np.clip(mx + 180, x0 + 40, B.W))
    y0 = int(np.clip(my + 280, 0, B.H - 80))
    y1 = int(np.clip(my + 680, y0 + 40, B.H - 8))
    gray = frame[y0:y1, x0:x1].mean(axis=2)
    if gray.size == 0:
        return (int(mx) - 18, int(np.clip(my + 500, 0, B.H - 50)), 40, 48)
    mask = (gray <= 42).astype(np.uint8)
    n, _labels, stats, cents = cv2_components(mask)
    best = None
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (80 <= area <= 2200 and 12 <= w <= 90 and 14 <= h <= 110):
            continue
        cx, cy = cents[i]
        if abs((x0 + cx) - mx) > 150:
            continue
        # Lowest blob on the placket, not a small shadow higher up.
        score = cy
        if best is None or score > best[0]:
            best = (score, x, y, w, h)
    if best is None:
        return (int(mx) - 20, int(np.clip(my + 520, 0, B.H - 50)), 40, 50)
    _s, x, y, w, h = best
    core = gray[y:y + h, x:x + w] <= 24
    ys, xs = np.where(core)
    if len(ys) >= 20:
        x = x + int(xs.min())
        y = y + int(ys.min())
        w = int(xs.max() - xs.min() + 1)
        h = int(ys.max() - ys.min() + 1)
    return (x0 + int(x), y0 + int(y), max(8, int(w)), max(10, int(h)))


def cv2_components(mask):
    import cv2
    return cv2.connectedComponentsWithStats(mask)


def _feather(box):
    import cv2
    x, y, w, h = box
    mask = np.zeros((B.H, B.W), np.float32)
    cv2.ellipse(
        mask,
        (int(x + w / 2), int(y + h / 2)),
        (max(8, int(w * 0.7)), max(10, int(h * 0.75))),
        0, 0, 360, 1.0, -1,
    )
    return cv2.GaussianBlur(mask, (0, 0), 6)


def _darken(frame, feather):
    pix = frame.astype(np.float32)
    gray = pix.mean(axis=2, keepdims=True)
    m = feather[:, :, None]
    darkened = gray * 0.40
    pix[:] = pix * (1 - m) + darkened * m
    frame[:] = np.clip(pix, 0, 255).astype(np.uint8)
