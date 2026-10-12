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
    # The span builder already opens on the attack, so a second head cut
    # would clip the first word. 09 is speaking on the first sample.
    removals = []
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
    if plan["reel"] == "09":
        _glue_form(plan)
    _limit_stacks(plan["cues"])
    if plan["reel"] == "07":
        _pin_word_edges(plan)
    plan["title_off"] = B._title_off_time(plan["shots"], plan["title_off"])
    _retie_shutters(plan)
    plan["cues"].sort(key=lambda c: (c.t, c.role))
    if plan["shots"]:
        plan["shots"][0].t0 = 0.0
        plan["shots"][-1].t1 = B.qframe(plan["duration"])
        if plan["shots"][0].kind == "face":
            plan["shots"][0].push = 0.0
    _sync_feature_pops(plan)
    _drop_cta(plan)
    _sparse_cues(plan)
    apply_v3(plan)
    apply_v4(plan)
    _stamp_sentence_marks(plan)
    plan["phrases"] = B.build_phrases(plan["words"])
    _apply_caption_groups(plan)
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
    # The title's green word sits high. Hold the spoken heroes that are already
    # on the face until the collar-height green outnumbers the banner.
    # The last second stays clear.
    if plan["reel"] == "07":
        _restore_hero(plan, "LEVERAGE")
    else:
        _restore_hero(plan, "PORTAL")
    _balance_face_green(plan)
    plan["cta_t"] = None


def _extend_window(plan, hero, t1):
    t1 = B.qframe(t1)
    for win in plan["windows"]:
        if win["hero"] == hero and t1 > win["t1"]:
            win["t1"] = t1
            return


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


def _shot_at(plan, t):
    for shot in plan["shots"]:
        if shot.t0 <= t < shot.t1:
            return shot
    return plan["shots"][-1]


def _green_face_counts(plan):
    title = hero = 0
    t = 0.0
    while t < plan["duration"]:
        shot = _shot_at(plan, t)
        if shot.kind == "face":
            if t < plan["title_off"]:
                title += 1
            elif any(w["t0"] <= t < w["t1"] for w in plan["windows"]):
                hero += 1
        t += 0.1
    return title, hero


def _green_share(plan):
    spans = B.green_intervals(plan["windows"], None, plan["duration"], plan["title_off"])
    if plan["duration"] <= 0:
        return 0.0
    return sum(b - a for a, b in spans) / plan["duration"]


def _stretch_hero(plan, clear):
    best = None
    for win in plan["windows"]:
        if win["t1"] >= clear - 0.05 or win["t1"] < plan["title_off"]:
            continue
        limit = clear
        for other in plan["windows"]:
            if other is win:
                continue
            if other["t0"] >= win["t1"] - 0.01:
                limit = min(limit, other["t0"] - 0.45)
        for shot in plan["shots"]:
            if shot.kind != "face" and shot.t0 >= win["t1"] - 0.01:
                limit = min(limit, shot.t0)
        room = limit - win["t1"]
        if room < 0.20:
            continue
        if best is None or room > best[0]:
            best = (room, win, limit)
    if best is None:
        return False
    _room, win, limit = best
    win["t1"] = B.qframe(min(limit, win["t1"] + 0.50))
    return win["t1"] < limit or True


def _clip_insert_coverage(plan):
    """A hero can sit on a screen for about a second, not the whole insert."""
    for win in plan["windows"]:
        used = 0.0
        cut = None
        t = win["t0"]
        while t < win["t1"] - 1e-4:
            shot = _shot_at(plan, t)
            step = min(shot.t1, win["t1"]) - t
            if shot.kind != "face":
                if used + step > 1.15 and cut is None:
                    cut = t + max(0.0, 1.15 - used)
                used += step
            t += max(step, 1 / B.FPS)
        if cut is not None and cut > win["t0"] + 0.45:
            win["t1"] = B.qframe(cut)


def _shrink_longest(plan):
    win = max(plan["windows"], key=lambda w: w["t1"] - w["t0"], default=None)
    if win is None or win["t1"] - win["t0"] < 0.80:
        return False
    win["t1"] = B.qframe(win["t1"] - 0.30)
    return True


def _stretch_face_only(plan, clear):
    best = None
    for win in plan["windows"]:
        if win["t1"] >= clear - 0.05 or win["t1"] < plan["title_off"] - 0.05:
            continue
        shot = _shot_at(plan, min(win["t1"] - 0.02, plan["duration"] - 0.05))
        if shot.kind != "face":
            continue
        limit = min(shot.t1, clear)
        for other in plan["windows"]:
            if other is not win and other["t0"] >= win["t1"] - 0.01:
                limit = min(limit, other["t0"] - 0.45)
        room = limit - win["t1"]
        if room < 0.20:
            continue
        if best is None or room > best[0]:
            best = (room, win, limit)
    if best is None:
        return False
    _room, win, limit = best
    win["t1"] = B.qframe(min(limit, win["t1"] + 0.40))
    return True


def _plant_face_hero(plan, clear):
    """Hold the latest hero on a bare face stretch, without covering an insert."""
    if _green_share(plan) > 0.56:
        return False
    bare = []
    t = plan["title_off"]
    while t < clear - 0.4:
        shot = _shot_at(plan, t)
        seg_end = min(shot.t1, clear)
        if shot.kind == "face":
            cursor = max(t, shot.t0)
            while cursor < seg_end - 0.4:
                hit = [w for w in plan["windows"] if w["t0"] - 0.15 <= cursor < w["t1"]]
                if hit:
                    cursor = max(w["t1"] for w in hit)
                    continue
                end = seg_end
                for w in plan["windows"]:
                    if w["t0"] > cursor + 0.05:
                        end = min(end, w["t0"] - 0.45)
                if end - cursor >= 0.80:
                    bare.append((end - cursor, cursor, end))
                break
        t = max(seg_end, t + 0.1)
    if not bare:
        return False
    _dur, start, end = max(bare)
    prev = [w for w in plan["windows"] if w["t0"] < start]
    if not prev:
        return False
    src = max(prev, key=lambda w: w["t0"])
    room = min(end, start + 1.6) - start
    if _green_share(plan) + room / plan["duration"] > 0.57:
        room = (0.56 - _green_share(plan)) * plan["duration"]
    if room < 0.60:
        return False
    plan["windows"].append({
        "hero": src["hero"],
        "kicker": src.get("kicker") or "",
        "t0": B.qframe(start),
        "t1": B.qframe(start + room),
        "land": B.qframe(start),
        "word_idx": src.get("word_idx"),
    })
    plan["windows"].sort(key=lambda w: w["t0"])
    return True


def _balance_face_green(plan):
    """Hold face heroes long enough that the low green wins, and clear the last second."""
    clear = plan["duration"] - 1.0
    for win in plan["windows"]:
        if win["t1"] > clear:
            win["t1"] = B.qframe(max(win["t0"] + 0.30, clear))
    _clip_insert_coverage(plan)
    for _ in range(40):
        title, hero = _green_face_counts(plan)
        share = _green_share(plan)
        if hero >= title + 8 and share <= 0.58:
            break
        if share > 0.58:
            if not _shrink_longest(plan):
                break
            continue
        if hero < title + 8:
            if _stretch_face_only(plan, clear) or _plant_face_hero(plan, clear):
                continue
        break
    for win in plan["windows"]:
        if win["t1"] > clear:
            win["t1"] = B.qframe(max(win["t0"] + 0.30, clear))


def _sparse_cues(plan):
    """No sound is the default. A handful of cues, each with a job."""
    words = plan["words"]
    shots = plan["shots"]
    cues = []

    def word_out(text, occ=0):
        return words[B.find_word(words, text, occ)]["out"]

    def add_pop(hero=None, plate=None):
        if hero is not None:
            win = next((w for w in plan["windows"] if w["hero"] == hero), None)
            if win is None:
                return
            cues.append(B.Cue("pop", B.qframe(max(0.0, win["t0"])), f"hero-{hero}"))
            return
        shot = next((s for s in shots if s.plate == plate), None)
        if shot is None:
            return
        cues.append(B.Cue("pop", B.qframe(shot.t0), f"insert-{plate}"))

    if plan["reel"] == "07":
        cues.append(B.Cue("negative", B.qframe(word_out("mistake")), "negative-mistake"))
        for hero in ("7", "$2,000", "LEVERAGE"):
            add_pop(hero=hero)
        for plate in ("07web", "07dark"):
            add_pop(plate=plate)
        win = next((w for w in plan["windows"] if w["hero"] == "$400"), None)
        if win is not None:
            cues.append(B.Cue("impact", B.qframe(max(0.0, win["t0"])), "hero-$400-impact"))
    else:
        cues.append(B.Cue("negative", B.qframe(word_out("pages")), "negative-pages"))
        for hero in ("$10K", "FUNCTIONALITY"):
            add_pop(hero=hero)
        for plate in ("09ui", "features", "09code", "09form"):
            add_pop(plate=plate)
        win = next((w for w in plan["windows"] if w["hero"] == "$15K"), None)
        if win is not None:
            cues.append(B.Cue("impact", B.qframe(max(0.0, win["t0"])), "hero-$15K-impact"))
    impacts = [c.t for c in cues if c.role == "impact"]
    cues = [c for c in cues if c.role == "impact" or not any(abs(c.t - t) < 0.08 for t in impacts)]
    # At most two sounds on the same frame. Keep the impact, then the negative, then the earliest pop.
    cues.sort(key=lambda c: (c.t, 0 if c.role == "impact" else 1 if c.role == "negative" else 2))
    kept = []
    for cue in cues:
        near = [c for c in kept if abs(c.t - cue.t) <= 0.08]
        if len(near) >= 2:
            continue
        kept.append(cue)
    kept.sort(key=lambda c: (c.t, c.role))
    plan["cues"] = kept


def _stamp_sentence_marks(plan):
    """Put the transcript's periods and commas back on words Whisper left bare.

    A caption breaks on that punctuation. Without it, 09 draws
    'functionality Most designers' as one line.
    """
    marks = {
        "09": (
            ("unlock", 0, ","),
            ("grand", 0, "."),
            ("functionality", 0, "."),
            ("design", 0, "."),
            ("agree", 0, "."),
            ("work", 0, "."),
            ("flow", 0, ","),
            ("portal", 0, "."),
            ("pages", 0, ","),
            ("functionality", 1, "."),
            ("difference", 0, "."),
        ),
    }
    for word, occ, mark in marks.get(plan["reel"], ()):
        i = B.find_word(plan["words"], word, occ)
        token = str(plan["words"][i]["word"]).rstrip()
        if token.endswith((".", "!", "?", ",", ";", ":")):
            continue
        plan["words"][i]["word"] = token + mark


def apply_v3(plan):
    """The v2.1 grade. Only the items QA named. Everything else stays."""
    if plan["reel"] == "07":
        _v3_07(plan)
    else:
        _v3_09(plan)


def _word(plan, text, occ=0):
    return plan["words"][B.find_word(plan["words"], text, occ)]


def _try_word(plan, text, occ=0):
    try:
        return _word(plan, text, occ)
    except KeyError:
        return None


def _v3_07(plan):
    _extend_word(plan, "going", 0, 0.08, 43.4)
    _snap_named_cuts(plan)
    marker = _try_word(plan, "don't") or _try_word(plan, "own")
    if marker is not None:
        for win in plan["windows"]:
            if win.get("hero") == "$400" and win["t1"] > marker["out"] - 0.02:
                win["t1"] = B.qframe(max(win["t0"] + 0.40, marker["out"] - 0.08))
    plan["cues"] = [c for c in plan["cues"] if c.role != "negative" and c.trigger != "insert-07dark"]
    dollar = _try_word(plan, "$400")
    if dollar is not None:
        for cue in plan["cues"]:
            if cue.role == "impact":
                cue.t = B.qframe(dollar["out"])
    plan["cues"].sort(key=lambda c: (c.t, c.role))


def _snap_named_cuts(plan):
    """Move the three 07 picture cuts that land inside a word onto a word edge."""
    delta = 0.0
    if plan["spans"] and plan["spans"][0].src is not None:
        delta = float(plan["spans"][0].src) - 0.367
    targets = [17.667 - delta, 19.80 - delta, 27.667 - delta]
    for target in targets:
        best = None
        for i, shot in enumerate(plan["shots"]):
            if i == 0:
                continue
            dist = abs(shot.t0 - target)
            if best is None or dist < best[0]:
                best = (dist, i)
        if best is None or best[0] > 0.80:
            continue
        i = best[1]
        shot = plan["shots"][i]
        prev = plan["shots"][i - 1]
        inside = None
        for w in plan["words"]:
            if w["out"] + 0.03 < shot.t0 < w["out_end"] - 0.03:
                inside = w
                break
        if inside is None:
            continue
        edges = [B.qframe(inside["out"]), B.qframe(inside["out_end"])]
        edges.sort(key=lambda edge: abs(edge - shot.t0))
        for edge in edges:
            if edge - prev.t0 < 0.40 or shot.t1 - edge < 0.40:
                continue
            prev.t1 = edge
            shot.t0 = edge
            for ins in plan["inserts"]:
                if abs(ins.get("t1", -9) - target) <= best[0] + 0.15:
                    ins["t1"] = edge
                if abs(ins.get("t", -9) - target) <= best[0] + 0.15:
                    ins["t"] = edge
            break


def _v3_09(plan):
    _extend_word(plan, "difference", 0, 0.12, 36.13)
    for shot in plan["shots"]:
        if shot.plate == "09code":
            shot.kind = "face"
            shot.plate = ""
            shot.scale = 1.0
            shot.push = 0.0
    _place_form_and_features(plan)
    _close_long_pauses(plan, (0.45, 0.25, 0.35, 0.45))
    _place_09_cues(plan)
    _seal_shots(plan)


def _seal_shots(plan):
    shots = [s for s in plan["shots"] if s.t1 - s.t0 >= 1 / B.FPS]
    shots.sort(key=lambda s: (s.t0, s.t1))
    for i in range(len(shots) - 1):
        shots[i].t1 = shots[i + 1].t0
    if shots:
        shots[0].t0 = 0.0
        shots[-1].t1 = B.qframe(plan["duration"])
    plan["shots"] = shots


def _place_form_and_features(plan):
    portal = _try_word(plan, "portal")
    quote = _try_word(plan, "quote")
    booking = _try_word(plan, "booking")
    calc = _try_word(plan, "calculator") or quote
    if portal is None or calc is None:
        return
    form = next((s for s in plan["shots"] if s.plate == "09form"), None)
    feat = next((s for s in plan["shots"] if s.plate == "features"), None)
    if form is not None:
        form.t0 = B.qframe(calc["out"])
        client = None
        for w in plan["words"]:
            if B.norm_word(w["word"]) == "client" and 0 < portal["out"] - w["out"] < 1.2:
                client = w
        # End on a word boundary before the portal line, so the third box
        # can fill on its own shot instead of cutting through "client".
        end = B.qframe(client["out"] if client is not None else portal["out"] - 0.12)
        if end - form.t0 < 1.15:
            end = B.qframe(min(portal["out"] - 0.08, form.t0 + 1.40))
        form.t1 = end
        # The shot that used to follow the form starts where the form now ends.
        for shot in plan["shots"]:
            if shot is form:
                continue
            if shot.t0 >= form.t0 and shot.t0 < form.t1:
                shot.t0 = form.t1
    if feat is not None and booking is not None:
        feat.t0 = B.qframe(min(feat.t0, booking["out"]))
        if form is not None and feat.t0 < form.t0:
            feat.t1 = form.t0
    if form is not None:
        hold = B.qframe(portal["out_end"] + 0.35)
        for w in plan["words"]:
            if w["out"] >= portal["out_end"] - 0.02:
                hold = B.qframe(w["out"])
                break
        nxt = None
        for shot in plan["shots"]:
            if shot is form:
                continue
            if shot.t0 >= form.t1 - 0.05:
                nxt = shot
                break
        if nxt is not None and hold > form.t1 + 0.30:
            if nxt.t1 - hold >= 0.40:
                second = B.Shot(form.t1, hold, "mg", plate="features", scale=1.0)
                nxt.t0 = hold
                nxt.src_jump = True
                plan["shots"].append(second)
            else:
                nxt.kind = "mg"
                nxt.plate = "features"
                nxt.t0 = form.t1
                nxt.t1 = max(nxt.t1, hold)
    plan["shots"].sort(key=lambda s: (s.t0, s.t1))
    if booking is not None and quote is not None:
        plan["feature_pops"] = [
            {"t": B.qframe(booking["out"]), "label": "Booking flow", "icon": "book"},
            {"t": B.qframe(quote["out"]), "label": "Quote calculator", "icon": "calc"},
            {"t": B.qframe(portal["out"]), "label": "Client portal", "icon": "portal"},
        ]


def _close_long_pauses(plan, keeps):
    """Shorten the long holes QA named, and keep room tone in what remains."""
    voice = clean_voice(B.voice_from_spans(plan["spec"]["source"], plan["spans"]), plan["reel"])
    hop = int(B.SR * 0.01)
    n = len(voice) // hop
    if n < 10:
        return
    rms = 20 * np.log10(np.sqrt((voice[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
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
    merged = [m for m in merged if m[1] - m[0] >= 4]
    holes = []
    for i in range(len(merged) - 1):
        a = merged[i][1] / 100.0
        b = merged[i + 1][0] / 100.0
        if b - a > 0.58:
            holes.append((a, b))
    removals = []
    for (a, b), keep in zip(holes, keeps):
        cut_a = round(a + keep, 3)
        cut_b = round(b - 0.02, 3)
        if cut_b - cut_a >= 0.04:
            removals.append((cut_a, cut_b))
    if removals:
        _excise(plan, removals)


def _place_09_cues(plan):
    plan["cues"] = [c for c in plan["cues"] if c.trigger not in ("insert-09code", "insert-features")]
    dont = _try_word(plan, "don't")
    if dont is not None:
        i_word = None
        for w in plan["words"]:
            if B.norm_word(w["word"]) == "i" and 0 <= dont["out"] - w["out"] < 1.4:
                i_word = w
        if i_word is not None:
            prev_end = 0.0
            for w in plan["words"]:
                if w["out_end"] <= i_word["out"] - 0.02:
                    prev_end = max(prev_end, w["out_end"])
            if i_word["out"] - prev_end > 0.18:
                hit = i_word["out"] - 0.12
            else:
                hit = max(prev_end + 0.02, i_word["out"] - 0.06)
            for cue in plan["cues"]:
                if cue.role == "negative":
                    cue.t = B.qframe(max(0.2, hit))
                    cue.trigger = "negative-disagree"
    fifteen = _try_word(plan, "fifteen")
    if fifteen is not None:
        for cue in plan["cues"]:
            if cue.role == "impact":
                cue.t = B.qframe(fifteen["out"])
    form = next((s for s in plan["shots"] if s.plate == "09form"), None)
    for cue in plan["cues"]:
        if cue.trigger == "insert-09form":
            cue.extra_db = 4.0
            if form is not None:
                cue.t = B.qframe(form.t0)
    # Feature pop times follow the words after the pause excise.
    booking = _try_word(plan, "booking")
    quote = _try_word(plan, "quote")
    portal = _try_word(plan, "portal")
    if booking and quote and portal:
        plan["feature_pops"] = [
            {"t": B.qframe(booking["out"]), "label": "Booking flow", "icon": "book"},
            {"t": B.qframe(quote["out"]), "label": "Quote calculator", "icon": "calc"},
            {"t": B.qframe(portal["out"]), "label": "Client portal", "icon": "portal"},
        ]
    plan["cues"].sort(key=lambda c: (c.t, c.role))


def apply_v4(plan):
    """The v3 grade. Only the items QA named, on the v3 clock, then the open cut."""
    if plan["reel"] == "07":
        _v4_07(plan)
    else:
        _v4_09(plan)
    _excise_dissolves(plan)
    _seal_shots(plan)
    if plan["reel"] == "07":
        _lock_07_after_shift(plan)
    else:
        _lock_09_after_shift(plan)
        _end_portal_before_stop(plan)
        _rebuild_feature_pops(plan)
    plan["cues"].sort(key=lambda c: (c.t, c.role))


def _v4_07(plan):
    _set_cut(plan, 2.033, 2.08)
    _set_cut(plan, 17.133, 17.18)
    _set_cut(plan, 27.200, 27.30)
    for cue in plan["cues"]:
        if cue.trigger == "hero-7":
            cue.t = B.qframe(8.967)
            cue.extra_db = float(getattr(cue, "extra_db", 0.0) or 0.0) + 6.0
        elif cue.trigger == "hero-LEVERAGE":
            cue.extra_db = -5.0
    _close_word_gap(plan, "1", "about", 0.25)
    _close_word_gap(plan, "2", "a", 0.25, right_near=17.0)
    _extend_until(plan, "going", 41.80, 43.4)


def _v4_09(plan):
    _snap_word_edge(plan, 15.467, "think")
    _snap_word_edge(plan, 20.700, "makes")
    _snap_word_edge(plan, 23.533, "quote")
    _snap_word_edge(plan, 25.367, "a")
    _snap_word_edge(plan, 29.033, "sell")
    _snap_word_edge(plan, 30.767, "that's")
    for cue in plan["cues"]:
        if cue.role == "negative":
            cue.t = B.qframe(17.9)
            cue.extra_db = -4.0
        elif cue.trigger == "hero-$10K":
            cue.extra_db = -4.0
        elif cue.trigger == "hero-FUNCTIONALITY":
            cue.extra_db = -4.0
        elif cue.trigger == "insert-09ui":
            cue.extra_db = float(getattr(cue, "extra_db", 0.0) or 0.0) + 6.0
        elif cue.trigger == "insert-09form":
            cue.extra_db = 0.0
    _close_word_gap(plan, "calculator", "or", 0.25, voiced=True)
    _close_word_gap(plan, "portal", "stop", 0.50, voiced=True)


def _set_cut(plan, current, target):
    """Move the picture cut nearest `current` onto `target`. Both shots stay readable."""
    target = B.qframe(target)
    best = None
    for i, shot in enumerate(plan["shots"]):
        if i == 0:
            continue
        dist = abs(shot.t0 - current)
        if best is None or dist < best[0]:
            best = (dist, i)
    if best is None or best[0] > 0.45:
        return
    i = best[1]
    prev, shot = plan["shots"][i - 1], plan["shots"][i]
    if target - prev.t0 < 0.35 or shot.t1 - target < 0.35:
        return
    old = shot.t0
    prev.t1 = target
    shot.t0 = target
    for ins in plan["inserts"]:
        if abs(ins.get("t1", -9) - old) <= 0.06:
            ins["t1"] = target
        if abs(ins.get("t", -9) - old) <= 0.06:
            ins["t"] = target
    for cue in plan["cues"]:
        if abs(cue.t - old) <= 0.06 and str(cue.trigger).startswith("insert-"):
            cue.t = target


def _word_near(plan, text, t):
    best = None
    want = B.norm_word(text)
    for w in plan["words"]:
        if B.norm_word(w["word"]) != want:
            continue
        dist = min(abs(w["out"] - t), abs(w["out_end"] - t), abs((w["out"] + w["out_end"]) / 2 - t))
        if best is None or dist < best[0]:
            best = (dist, w)
    if best is None:
        raise KeyError(text)
    return best[1]


def _snap_word_edge(plan, current, text):
    w = _word_near(plan, text, current)
    edges = [B.qframe(w["out"]), B.qframe(w["out_end"])]
    edges.sort(key=lambda edge: abs(edge - current))
    _set_cut(plan, current, edges[0])


def _source_audio(plan):
    cache = getattr(_source_audio, "_cache", {})
    path = plan["spec"]["source"]
    if path not in cache:
        cache[path] = B.load_mono(path)
        _source_audio._cache = cache
    return cache[path]


def _voiced_out(plan, word, thresh=-22.0):
    """Output time of the first loud hop inside a word.

    Whisper's start can sit on a handling thump. The gap is measured from
    the previous word's end to this onset, not from the speech gate.
    """
    audio = _source_audio(plan)
    hop = int(0.01 * B.SR)
    t = float(word["start"])
    limit = float(word["end"]) - 0.02
    onset = t
    while t < limit:
        i = int(t * B.SR)
        seg = audio[i:i + hop]
        if len(seg) < hop // 2:
            break
        db = 20 * np.log10(float(np.sqrt(np.mean(seg ** 2))) + 1e-9)
        if db >= thresh:
            onset = t
            break
        t += 0.01
    return _map_src(plan["spans"], onset)


def _hop_db(audio, src_t):
    hop = int(0.01 * B.SR)
    i = int(src_t * B.SR)
    seg = audio[i:i + hop]
    if len(seg) < hop // 2:
        return -90.0
    return 20 * np.log10(float(np.sqrt(np.mean(seg ** 2))) + 1e-9)


def _drop_thumps(plan, start, end):
    """Cut handling hits inside a hole. They fooled the speech gate into keeping it."""
    if end - start < 0.12:
        return
    audio = _source_audio(plan)
    loud = []
    t = start
    while t < end - 0.06:
        src = B._source_at(plan["spans"], t)
        if src is not None and _hop_db(audio, src) >= -26.0:
            loud.append(t)
        t += 0.01
    if not loud:
        return
    ranges = []
    a = loud[0]
    prev = loud[0]
    for t in loud[1:]:
        if t - prev > 0.04:
            ranges.append((round(a - 0.02, 3), round(prev + 0.03, 3)))
            a = t
        prev = t
    ranges.append((round(max(start, a - 0.02), 3), round(min(end - 0.02, prev + 0.03), 3)))
    ranges = [(a, b) for a, b in ranges if b - a >= 0.04]
    if ranges:
        _excise(plan, ranges)


def _close_word_gap(plan, left, right, keep, right_near=None, voiced=False):
    if right_near is not None:
        lw = _word_near(plan, left, right_near)
        rw = _word_near(plan, right, right_near)
    elif left in {"1", "2"}:
        lw = _word_near(plan, left, 14.0 if left == "1" else 16.5)
        rw = _word_near(plan, right, lw["out_end"] + 0.8)
    else:
        lw = _word(plan, left)
        rw = _word(plan, right)
    start = float(lw["out_end"])
    end = _voiced_out(plan, rw) if voiced else float(rw["out"])
    if voiced and end > start:
        _drop_thumps(plan, start, end)
        start = float(lw["out_end"])
        end = _voiced_out(plan, rw)
    if end - start <= keep + 0.04:
        return
    cut_a = round(start + keep, 3)
    cut_b = round(end, 3)
    if cut_b - cut_a >= 0.04:
        _excise(plan, [(cut_a, cut_b)])


def _lock_07_after_shift(plan):
    """Put the three named cuts, and the pop on 7, back on the words after the open cut."""
    web = _word(plan, "website")
    _set_cut(plan, web["out"] + 0.04, web["out"] + 0.033)
    free = _word(plan, "free")
    _set_cut(plan, free["out"] + 0.05, free["out"] + 0.033)
    pay = _word(plan, "payment")
    _set_cut(plan, pay["out_end"] + 0.05, pay["out_end"] + 0.107)
    seven = _word(plan, "7")
    for cue in plan["cues"]:
        if cue.trigger == "hero-7":
            cue.t = B.qframe(seven["out"])


def _lock_09_after_shift(plan):
    """Snap the named cuts back onto the word edge once the gap closes have moved them."""
    for text, hint in (
        ("think", 15.0),
        ("makes", 20.0),
        ("quote", 23.0),
        ("a", 24.0),
        ("sell", 27.0),
        ("that's", 29.0),
    ):
        w = _word_near(plan, text, hint)
        edges = [B.qframe(w["out"]), B.qframe(w["out_end"])]
        # The cut that belongs to this word is the one already nearest it.
        current = min(edges, key=lambda edge: min(abs(s.t0 - edge) for s in plan["shots"][1:]))
        nearest_cut = min((s.t0 for s in plan["shots"][1:]), key=lambda t: abs(t - current))
        target = min(edges, key=lambda edge: abs(edge - nearest_cut))
        _set_cut(plan, nearest_cut, target)


def _extend_until(plan, text, src_end, src_len):
    w = _word(plan, text)
    for s in plan["spans"]:
        if s.src is None:
            continue
        if s.src - 0.03 <= w["end"] <= s.src + s.dur + 0.08:
            have = s.src + s.dur
            extra = min(max(0.0, src_len - have), max(0.0, src_end - have))
            if extra >= 0.02:
                _extend_word(plan, text, 0, extra, src_len)
            return


def _source_interval(plan, a, b):
    hits = []
    for s in plan["spans"]:
        if s.src is None:
            continue
        lo = max(a, s.src)
        hi = min(b, s.src + s.dur)
        if hi - lo >= 1 / B.FPS:
            hits.append((s.out + (lo - s.src), s.out + (hi - s.src)))
    if not hits:
        return None
    return hits[0][0], hits[-1][1]


def _excise_dissolves(plan):
    """Cut the baked dissolve windows. Holding those frames froze the open."""
    removals = []
    for a, b in B.OPEN_DISSOLVES.get(plan["reel"]) or []:
        hit = _source_interval(plan, a, b)
        if hit is None:
            continue
        lo, hi = hit
        if hi - lo >= 1 / B.FPS:
            removals.append((lo, hi))
    if removals:
        _excise(plan, removals)


def _end_portal_before_stop(plan):
    stop = _try_word(plan, "stop")
    if stop is None:
        return
    edge = B.qframe(max(0.0, stop["out"] - 0.04))
    for win in plan["windows"]:
        if win.get("hero") == "PORTAL" and win["t1"] > edge:
            win["t1"] = max(win["t0"] + 0.35, edge)


def _rebuild_feature_pops(plan):
    booking = _try_word(plan, "booking")
    quote = _try_word(plan, "quote")
    portal = _try_word(plan, "portal")
    if not (booking and quote and portal):
        return
    plan["feature_pops"] = [
        {"t": B.qframe(booking["out"]), "label": "Booking flow", "icon": "book"},
        {"t": B.qframe(quote["out"]), "label": "Quote calculator", "icon": "calc"},
        {"t": B.qframe(portal["out"]), "label": "Client portal", "icon": "portal"},
    ]


def _apply_caption_groups(plan):
    groups = _CAPTION_GROUPS.get(plan["reel"])
    if not groups:
        return
    words = plan["words"]
    i = 0
    phrases = []
    for norms, text in groups:
        chunk = words[i:i + len(norms)]
        got = [B.norm_word(w["word"]) for w in chunk]
        if got != list(norms):
            raise SystemExit(f"reel {plan['reel']} caption align at {i}: {got} != {list(norms)}")
        i += len(norms)
        phrases.append({
            "words": chunk,
            "t0": chunk[0]["out"],
            "t1": chunk[-1]["out_end"],
            "text": text,
            "spoken": " ".join(str(w["word"]).strip() for w in chunk),
        })
    if i != len(words):
        raise SystemExit(
            f"reel {plan['reel']} captions left {words[i]['word']!r} and {len(words) - i} more"
        )
    plan["phrases"] = phrases


_CAPTION_GROUPS = {
    "07": (
        (("charging", "$2,000", "up", "front", "for", "a", "website"),
         "CHARGING $2,000 UP FRONT\nFOR A WEBSITE"),
        (("is", "the", "most", "expensive", "mistake", "beginners", "make"),
         "IS THE MOST EXPENSIVE\nMISTAKE BEGINNERS MAKE"),
        (("they", "pay", "you", "once"), "THEY PAY YOU ONCE"),
        (("and", "then", "they're", "gone"), "AND THEN THEY'RE GONE"),
        (("i've", "built", "7", "client", "websites", "and"),
         "I'VE BUILT 7 CLIENT WEBSITES AND"),
        (("here's", "how", "i'd", "price", "the", "next", "one"),
         "HERE'S HOW I'D PRICE\nTHE NEXT ONE"),
        (("option", "1"), "OPTION 1"),
        (("about", "$2,000", "up", "front"), "ABOUT $2,000 UP FRONT"),
        (("option", "2"), "OPTION 2"),
        (("a", "free", "build", "plus", "$300", "to", "$400", "a", "month"),
         "A FREE BUILD PLUS\n$300 TO $400 A MONTH"),
        (("now", "watch", "what", "happens"), "NOW WATCH WHAT HAPPENS"),
        (("when", "they", "stop", "paying"), "WHEN THEY STOP PAYING"),
        (("they", "don't", "own", "it"), "THEY DON'T OWN IT"),
        (("so", "the", "site", "comes", "down"), "SO THE SITE COMES DOWN"),
        (("that's", "leverage"), "THAT'S LEVERAGE"),
        (("one", "payment", "ends", "it"), "ONE PAYMENT ENDS IT"),
        (("a", "monthly", "plan", "keeps", "it", "going"),
         "A MONTHLY PLAN\nKEEPS IT GOING"),
    ),
    "09": (
        (("if", "your", "website", "builder", "has", "ever"),
         "IF YOUR WEBSITE BUILDER HAS EVER"),
        (("told", "you", "upgrade", "to", "unlock"), "TOLD YOU UPGRADE TO UNLOCK"),
        (("this", "is", "how", "you"), "THIS IS HOW YOU"),
        (("start", "charging", "10", "grand"), "START CHARGING 10 GRAND"),
        (("i", "went", "from", "five", "hundred", "dollar", "sites"),
         "I WENT FROM\n$500 SITES"),
        (("to", "ten", "to", "fifteen", "thousand", "dollar", "builds"),
         "TO $10K TO $15K BUILDS"),
        (("using", "claude", "code", "for", "custom", "functionality"),
         "USING CLAUDE CODE FOR CUSTOM FUNCTIONALITY"),
        (("most", "designers", "think"), "MOST DESIGNERS THINK"),
        (("more", "money", "means", "better", "design"), "MORE MONEY MEANS BETTER DESIGN"),
        (("i", "don't", "agree"), "I DON'T AGREE"),
        (("owners", "pay", "for", "what"), "OWNERS PAY FOR WHAT"),
        (("makes", "their", "business", "work"), "MAKES THEIR BUSINESS WORK"),
        (("a", "booking", "flow"), "A BOOKING FLOW"),
        (("a", "quote", "calculator"), "A QUOTE CALCULATOR"),
        (("or", "a", "client", "portal"), "OR A CLIENT PORTAL"),
        (("stop", "selling", "pages"), "STOP SELLING PAGES"),
        (("sell", "functionality"), "SELL FUNCTIONALITY"),
        (("that's", "the", "ten", "grand", "difference"), "THAT'S THE TEN GRAND DIFFERENCE"),
    ),
}


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
    if plan.get("cta_t") is not None:
        plan["cta_t"] = _map_out(plan["cta_t"], removals)
    pops = []
    for pop in plan.get("feature_pops") or []:
        if any(a < pop["t"] < b for a, b in removals):
            pop["t"] = _map_out(pop["t"], removals)
        else:
            pop["t"] = _map_out(pop["t"], removals)
        pops.append(pop)
    if pops:
        plan["feature_pops"] = pops
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
    if plan.get("cta_t") is not None and plan["cta_t"] >= t:
        plan["cta_t"] = B.qframe(plan["cta_t"] + delta)
    for pop in plan.get("feature_pops") or []:
        if pop["t"] >= t - 1e-4:
            pop["t"] = B.qframe(pop["t"] + delta)
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


def _form_hold_end(plan, t):
    """About 2 s on the form, ending before the portal word when that is sooner."""
    t1 = B.qframe(min(plan["duration"] - 1.2, t + 2.00))
    try:
        portal = B.qframe(plan["words"][B.find_word(plan["words"], "portal")]["out"])
    except KeyError:
        portal = None
    if portal is not None and t + 0.40 < portal <= t1 + 0.05:
        t1 = B.qframe(min(t1, portal - 0.10))
    if t1 < t + 1.80:
        t1 = B.qframe(min(plan["duration"] - 1.2, t + 1.80))
    return t1


def _own_interval(shots, t, t1, plate):
    """The held screen owns [t, t1). Later shots start when it ends."""
    cleaned = []
    for s in shots:
        if s.plate == plate and abs(s.t0 - t) < 0.04:
            s.t0, s.t1 = t, t1
            cleaned.append(s)
            continue
        if s.t1 <= t + 1e-3:
            cleaned.append(s)
            continue
        if s.t0 >= t1 - 1e-3:
            cleaned.append(s)
            continue
        if s.t0 < t - 1e-3:
            s.t1 = t
            cleaned.append(s)
        if s.t1 > t1 + 1e-3:
            cleaned.append(B.Shot(
                t1, s.t1, s.kind, src_jump=True, scale=s.scale, push=0.0,
                bw=s.bw, plate=s.plate,
            ))
    cleaned.sort(key=lambda s: (s.t0, s.t1))
    return cleaned


def _insert_form(plan):
    w = plan["words"][B.find_word(plan["words"], "calculator")]
    t = B.qframe(w["out"])
    # Locate, then hold the form long enough to inspect. Stop just before
    # the portal hero so that word lands on the face.
    t1 = _form_hold_end(plan, t)
    shots = []
    placed = False
    for s in plan["shots"]:
        if placed or not (s.t0 <= t < s.t1):
            shots.append(s)
            continue
        if t - s.t0 >= 0.40:
            shots.append(B.Shot(s.t0, t, s.kind, scale=s.scale, push=0.0, bw=s.bw, plate=s.plate))
        else:
            t = s.t0
            t1 = _form_hold_end(plan, t)
        shots.append(B.Shot(t, t1, "bleed", plate="09form"))
        if s.t1 - t1 >= 0.40:
            shots.append(B.Shot(t1, s.t1, s.kind, src_jump=True, plate=s.plate, scale=s.scale))
        placed = True
    plan["shots"] = _own_interval(shots, t, t1, "09form")
    for ins in plan["inserts"]:
        if ins.get("plate") == "features" and ins.get("t", 0) < t < ins.get("t1", 0):
            ins["t1"] = t
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
    plan["title_off"] = B._title_off_time(shots, plan["title_off"])


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
                # A screen held for reading already covers this sliver. Do not
                # pull its out-point back.
                if prev.t1 <= nxt.t0 + 0.02:
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
    """Shutters went with the white flash. Routine cuts stay silent."""
    plan["cues"] = [c for c in plan["cues"] if c.role != "shutter"]
    for shot in plan["shots"]:
        shot.flash = False


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
    v2_receipts = {
        "07": Path("/opt/cursor/artifacts/2026-10-11_07_never-sell-a-website-for-2000_new_v2-receipt.json"),
        "09": Path("/opt/cursor/artifacts/2026-10-11_09_sell-functionality_new_v2-receipt.json"),
    }
    v2_path = v2_receipts.get(plan["reel"])
    if v2_path is not None and v2_path.exists():
        old = json.loads(v2_path.read_text())
        sfx_path = Path(str(v2_path).replace("-receipt.json", "-sfx-log.json"))
        old_cues = []
        if sfx_path.exists():
            logged = json.loads(sfx_path.read_text())
            old_cues = [
                {"t": c.get("peak_on", c.get("start")), "role": c.get("role"), "trigger": c.get("trigger")}
                for c in logged.get("cues") or []
            ]
        payload["against_new_v2"] = {
            "v2_file": old.get("file"),
            "v2_sha256": old.get("sha256"),
            "duration": {"new_v2": old.get("duration"), "new_v3": round(float(plan["duration"]), 3)},
            "loudness_new_v2": old.get("loudness"),
            "shots_new_v2": old.get("shots"),
            "shots_new_v3": [
                {"t0": round(s.t0, 3), "t1": round(s.t1, 3), "kind": s.kind, "plate": s.plate}
                for s in plan["shots"]
            ],
            "cues_new_v2": old_cues,
            "cues_new_v3": [
                {"t": round(c.t, 3), "role": c.role, "trigger": c.trigger}
                for c in plan["cues"]
            ],
        }
    v3_receipts = {
        "07": Path("/opt/cursor/artifacts/2026-10-11_07_never-sell-a-website-for-2000_new_v3-receipt.json"),
        "09": Path("/opt/cursor/artifacts/2026-10-11_09_sell-functionality_new_v3-receipt.json"),
    }
    v3_path = v3_receipts.get(plan["reel"])
    if v3_path is not None and v3_path.exists():
        old = json.loads(v3_path.read_text())
        sfx_path = Path(str(v3_path).replace("-receipt.json", "-sfx-log.json"))
        old_cues = []
        if sfx_path.exists():
            logged = json.loads(sfx_path.read_text())
            old_cues = [
                {"t": c.get("peak_on", c.get("start")), "role": c.get("role"), "trigger": c.get("trigger")}
                for c in logged.get("cues") or []
            ]
        payload["against_new_v3"] = {
            "v3_file": old.get("file"),
            "v3_sha256": old.get("sha256"),
            "duration": {"new_v3": old.get("duration"), "new_v4": round(float(plan["duration"]), 3)},
            "loudness_new_v3": old.get("loudness"),
            "shots_new_v3": old.get("shots"),
            "shots_new_v4": [
                {"t0": round(s.t0, 3), "t1": round(s.t1, 3), "kind": s.kind, "plate": s.plate}
                for s in plan["shots"]
            ],
            "cues_new_v3": old_cues,
            "cues_new_v4": [
                {"t": round(c.t, 3), "role": c.role, "trigger": c.trigger, "extra_db": getattr(c, "extra_db", 0.0)}
                for c in plan["cues"]
            ],
        }
    dest.with_name(dest.stem + "-diff.json").write_text(json.dumps(payload, indent=1))


def prepare_plate(plate, img, fit, phone_plate, bleed_plate):
    highlight = None
    if plate == "07web":
        img = _relabel_light(img)
        # The Option 2 block, wide enough to land near 80% of the frame.
        img = img.crop((50, 820, 1030, 1360))
        highlight = (20, 130, 730, 235)
    elif plate == "07dark":
        img = _relabel_dark(img)
        img = img.crop((540, 560, 1060, 1200))
        highlight = (10, 105, 500, 290)
    if plate in ("09code", "09form"):
        img = _crop_progress(img)
    elif plate == "09ui":
        img = _crop_margins(img, 0.07, 0.16, 0.03)
    if plate == "09ui":
        img = _place_wide(img, 0.75, top=200, limit=1380)
    elif plate in ("07web", "07dark"):
        img = _place_wide(img, 0.80, top=240, limit=1380, highlight=highlight)
    elif fit == "phone":
        img = phone_plate(img, bottom=CARD_BOTTOM)
    elif fit == "card":
        img = _fit_card(img, CARD_BOTTOM)
    else:
        img = bleed_plate(img)
    # Relabeled pricing cards are illustrative. Northpoint Roofing is a real
    # client, so those screen recordings stay unlabeled.
    if plate in ("07web", "07dark"):
        img = B._stamp_example(img)
    return img


def _place_wide(img, frac, top, limit, highlight=None):
    """Scale a cropped card to a fraction of the frame width, above the captions."""
    im = img.convert("RGB")
    target_w = int(B.W * frac)
    scale = target_w / max(1, im.size[0])
    target_h = max(1, int(round(im.size[1] * scale)))
    if top + target_h > limit:
        scale = (limit - top) / max(1, im.size[1])
        target_w = max(1, int(round(im.size[0] * scale)))
        target_h = max(1, int(round(im.size[1] * scale)))
    im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    plate = Image.new("RGB", (B.W, B.H), (0, 0, 0))
    x = (B.W - target_w) // 2
    plate.paste(im, (x, top))
    draw = ImageDraw.Draw(plate)
    draw.rounded_rectangle([x - 6, top - 6, x + target_w + 6, top + target_h + 6], radius=28, outline=(255, 255, 255), width=6)
    if highlight is not None:
        hx0, hy0, hx1, hy1 = highlight
        box = [
            x + int(round(hx0 * scale)),
            top + int(round(hy0 * scale)),
            x + int(round(hx1 * scale)),
            top + int(round(hy1 * scale)),
        ]
        draw.rounded_rectangle(box, radius=16, outline=(0x42, 0xFF, 0x40), width=8)
    return plate


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
    font = B._font("BebasNeue-Regular.ttf", 42)
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
    font = B._font("BebasNeue-Regular.ttf", 40)
    ink = (245, 245, 245)
    _cover_text(draw, [40, 590, 520, 665], bg, "Option 1: Up front", font, ink, (52, 612))
    _cover_text(draw, [550, 590, 1040, 660], bg, "Option 2: Monthly", font, ink, (562, 608))
    _cover_text(draw, [550, 665, 1040, 850], bg, "$300-$400/mo", font, ink, (562, 730))
    return im


def _crop_progress(img):
    """Drop the Step 2 of 4 header and the empty footer so the fields fill the card."""
    arr = np.array(img.convert("RGB"))
    h = arr.shape[0]
    if h < 500:
        return Image.fromarray(arr, "RGB")
    top = int(round(h * 0.115))
    bot = int(round(h * 0.60))
    return Image.fromarray(arr[top:bot], "RGB")


def _crop_margins(img, top, bottom, side):
    im = img.convert("RGB")
    w, h = im.size
    box = (
        int(w * side),
        int(h * top),
        int(w * (1 - side)),
        int(h * (1 - bottom)),
    )
    if box[2] - box[0] < 40 or box[3] - box[1] < 40:
        return im
    return im.crop(box)


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
    """Fill the lav pin with the surrounding shirt color. Feather is 6 px.

    The mask is re-fit on every face frame so it follows the pin.
    """
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
        small = cv2.resize(frame, (540, 960))
        _n, faces = net.detect(small)
        if faces is not None and len(faces):
            box = _pin_box(frame, faces[0])
            feather = _feather(box)
        if feather is None or box is None:
            return chunk
        _shirt_fill(frame, feather, box)
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
        return _pad_pin(int(mx) - 20, int(np.clip(my + 520, 0, B.H - 50)), 48, 56)
    _s, x, y, w, h = best
    core = gray[y:y + h, x:x + w] <= 24
    ys, xs = np.where(core)
    if len(ys) >= 20:
        x = x + int(xs.min())
        y = y + int(ys.min())
        w = int(xs.max() - xs.min() + 1)
        h = int(ys.max() - ys.min() + 1)
    return _pad_pin(x0 + int(x), y0 + int(y), max(8, int(w)), max(10, int(h)))


def _pad_pin(x, y, w, h):
    """Cover the clip, including the part that sits under the caption line."""
    pad_x, pad_top, pad_bot = 16, 12, 56
    x = int(max(0, x - pad_x))
    y = int(max(0, y - pad_top))
    w = int(min(B.W - x, max(w + pad_x * 2, 56)))
    h = int(min(B.H - y, max(h + pad_top + pad_bot, 100)))
    return (x, y, w, h)


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


def _shirt_fill(frame, feather, box):
    """Sample the shirt around the pin and fill the mask with that color."""
    x, y, w, h = box
    pad = 36
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(B.W, x + w + pad), min(B.H, y + h + pad)
    region = frame[y0:y1, x0:x1]
    if region.size == 0:
        return
    gray = region.astype(np.float32).mean(axis=2)
    inner = np.zeros(gray.shape, dtype=bool)
    ix0, iy0 = x - x0, y - y0
    inner[max(0, iy0):iy0 + h, max(0, ix0):ix0 + w] = True
    keep = (gray > 50) & (gray < 200) & ~inner
    sample = region[keep]
    if len(sample) < 40:
        sample = region[(gray > 35) & ~inner]
    if len(sample) < 10:
        color = np.array([128.0, 118.0, 112.0], np.float32)
    else:
        color = np.median(sample.astype(np.float32), axis=0)
    pix = frame.astype(np.float32)
    m = feather[:, :, None]
    pix[:] = pix * (1.0 - m) + color * m
    frame[:] = np.clip(pix, 0, 255).astype(np.uint8)
