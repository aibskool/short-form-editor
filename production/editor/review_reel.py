#!/usr/bin/env python3
"""Acceptance review for a Brandon reel: house-style checks on a build, and on the
encoded render when one is given.

    python3 production/editor/review_reel.py --project build/ [--video reel.mp4] [--out review.json] [--strict]
    python3 production/editor/review_reel.py --measure reel.mp4 --out metrics.json

Every threshold comes from style_spec.json. Checks are grouped by the areas Brandon
named: word sync, mobile legibility, full-size presenter presence, visual progression,
transition variety, standout motion craft, sparse sound, forbidden patterns, plus the
hook, pacing and a regression comparison with the approved 20-second calibration
(reference/calibration-20s.json). Each check reports pass, warn or fail with the
measured value and the limit. A build with a fail is not ready to show; a warning needs
a look. With --video the review also tracks Brandon's face through the render to measure
how long he is on screen at full size, finds long dark card spans, silences and static
stretches, and measures loudness on full band and through a phone-speaker band.

Brandon's narration is the editorial input: nothing here checks whether a visual proves
a claim. The review cannot judge taste either; watch the render with sound at phone size.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import style  # noqa: E402

REFERENCE_PATH = HERE / "reference" / "calibration-20s.json"
PASS, WARN, FAIL = "pass", "warn", "fail"
GRID = 10  # timeline samples per second
AREAS = ("hook", "word_sync", "legibility", "presenter", "progression", "transitions", "motion_craft", "sound",
         "forbidden", "pacing", "regression")
AREA_TITLES = {"hook": "Hook", "word_sync": "Word sync", "legibility": "Mobile legibility",
               "presenter": "Full-size presenter", "progression": "Visual progression",
               "transitions": "Transition variety", "motion_craft": "Standout motion", "sound": "Sparse sound",
               "forbidden": "Forbidden patterns", "pacing": "Pacing", "regression": "Calibration regression"}
TEXT_TYPES = {"hero", "statement", "headline", "stat", "card", "tag", "equation", "compare", "checklist", "flow",
              "orbit", "chart", "badge", "cta", "prompt", "spotlight", "reveal"}
KEYED_TYPES = TEXT_TYPES | {"device"}
INFO_TYPES = {"tag", "card", "stat", "compare", "checklist", "flow", "orbit", "chart", "device", "prompt", "equation"}
BIG_TEXT = {"hero", "statement", "headline", "stat", "equation", "card", "reveal", "cta"}
SMALL_TYPES = {"badge", "spotlight", "particles"}
IMPACTS = {"impact_soft", "thud", "stamp", "impact", "riser"}
LAYOUT_STATE = {"presenter": "full", "stage": "stack", "split": "stack", "full_broll": "away", "screen": "away"}
SIZE_KEYS = {"size", "title_size", "label_size", "value_size", "font_size", "item_size", "sub_size", "text_size"}
SHOWPIECE_TRANSITIONS = {t.split(":", 1)[1] for t in style.load()["showpiece"]["types"] if t.startswith("transition:")}


def fitted_hero_px(spec):
    """The size a hero actually renders at: the authored size, shrunk to fit its lines."""
    from motion_kit import fit_size, hero_line_scales
    lines = [str(line) for line in (spec.get("lines") or [spec.get("text", "")])]
    width = spec.get("w", 80 if spec.get("zone") == "low" else 88)
    return fit_size(lines, float(spec.get("size", 136)), 1080 * float(width) / 100, 84,
                    hero_line_scales(spec.get("variant", "stack"), lines))


def merge_spans(spans):
    merged = []
    for a, z in sorted((float(a), float(z)) for a, z in spans if float(z) > float(a)):
        if merged and a <= merged[-1][1] + 1e-3:
            merged[-1][1] = max(merged[-1][1], z)
        else:
            merged.append([a, z])
    return [tuple(m) for m in merged]


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        if default is not None:
            return default
        raise FileNotFoundError(f"{path} not found; build the timeline first (edit.py build)")
    return json.loads(path.read_text())


def runs(flags, value, step=1 / GRID):
    """(start, end) spans in seconds where flags[i] == value."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [object()]):
        if f == value and start is None:
            start = i
        elif f != value and start is not None:
            out.append((start * step, i * step))
            start = None
    return out


def longest(spans):
    return max((b - a for a, b in spans), default=0.0)


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


# ---------------------------------------------------------------------------
class Build:
    """Everything the review needs from a build directory (new or older receipts)."""

    def __init__(self, project):
        p = Path(project)
        self.project = p
        self.resolved = read_json(p / "resolved-timeline.json")
        self.raw = read_json(p / "timeline.json", {})
        self.receipt = read_json(p / "build-receipt.json")
        self.words = read_json(p / "mapped-words.json", [])
        self.html = (p / "index.html").read_text() if (p / "index.html").is_file() else ""
        self.report = self.receipt.get("motion_report", {})
        self.duration = float(self.receipt["duration"])
        self.width = int(self.receipt.get("width", 1080))
        self.fps = int(self.receipt.get("fps", 30))
        self.style = style.load(self.resolved.get("style"))
        self.shots = [s for s in self.resolved.get("shots", []) if isinstance(s, dict)]
        self.transitions = [t for t in self.resolved.get("transitions", []) if isinstance(t, dict)]
        self.camera = [c for c in self.resolved.get("camera", []) if isinstance(c, dict)]
        self.captions = self._captions()
        self.graphics = self._graphics()
        self.sfx = self._sfx()
        self.resolver = None
        if self.words:
            from cues import CueResolver
            self.resolver = CueResolver(self.words, self.duration, self.fps)

    def t(self, value, fallback=None):
        """Seconds for a number or a word cue (screen focus keys are resolved at build time)."""
        if isinstance(value, (int, float)):
            return float(value)
        if self.resolver is None:
            return fallback
        try:
            return self.resolver.resolve(value, "review")
        except ValueError:
            return fallback

    def _captions(self):
        """Caption facts from the receipt; an older receipt's are read from the built page
        (the size, group count and longest group the viewer actually got)."""
        spec = self.resolved.get("spoken_captions", self.resolved.get("captions", {})) or {}
        house = style.caption_defaults(self.style)
        info = dict(self.report.get("captions") or {})
        html = self.html
        if "style" not in info:
            classes = re.findall(r'<div id="caption-\d+" class="caption clip ?([a-z]*)"', html)
            found = next((c for c in classes if c), None)
            info["style"] = self.receipt.get("caption_style") or found or spec.get("style", house["style"])
        if "font_px_1080" not in info:
            size = re.search(r"\.caption-text\{[^}]*?font-size:([\d.]+)px", html)
            if size:
                info["font_px_1080"] = round(float(size[1]) * 1080 / self.width, 1)
            else:
                size = spec.get("font_size")
                info["font_px_1080"] = float(size) * 1080 / self.width if size else float(house["font_px"])
        if "groups" not in info or "max_words" not in info:
            groups = re.findall(r'<div id="caption-(\d+)" class="caption', html)
            if groups:
                per_group = Counter(re.findall(r'id="caption-(\d+)-w\d+"', html))
                info.setdefault("groups", len(groups))
                info.setdefault("max_words", max(per_group.values(), default=0))
        info.setdefault("max_words", int(spec.get("max_words", house["max_words"])))
        info.setdefault("groups", int(self.receipt.get("caption_groups", 0)))
        anchor = re.search(r"#caption-anchor\{position:absolute;top:([\d.]+)%", html)
        info["y"] = float(anchor[1]) if anchor else float(spec.get("y", house["y"]))
        info["emphasis_words"] = spec.get("emphasis", [])
        return info

    def _graphics(self):
        specs = {}
        for item in self.resolved.get("graphics", []):
            if isinstance(item, dict) and item.get("id"):
                specs[item["id"]] = item
        raw_starts = {}
        for raw, res in zip(self.raw.get("graphics", []), self.resolved.get("graphics", [])):
            if isinstance(raw, dict) and isinstance(res, dict) and res.get("id"):
                raw_starts[res["id"]] = raw.get("start")
        meta = self.report.get("graphics_meta")
        out = []
        if meta:
            for m in meta:
                g = dict(m)
                g["spec"] = specs.get(m["id"], {})
                out.append(g)
        else:  # older receipt: rebuild what we can from the resolved timeline
            items = [item for item in self.resolved.get("graphics", []) if isinstance(item, dict)]
            # Legacy editorial graphics were built as kinetic statements named editorial-N.
            for i, item in enumerate(self.resolved.get("editorial_graphics", []) or []):
                if isinstance(item, dict) and "start" in item and "end" in item:
                    items.append({**item, "id": f"editorial-{i}", "type": "statement",
                                  "w": item.get("width", 88), "y": item.get("y", 12)})
            for item in items:
                kind = item.get("type")
                variant = item.get("variant")
                hides = item.get("captions", "hide" if kind in {"hero", "reveal"} else "keep") == "hide"
                out.append({"id": item.get("id"), "type": kind, "start": float(item["start"]), "end": float(item["end"]),
                            "box": [item.get("x"), item.get("y"), item.get("w", item.get("width")), item.get("h")],
                            "hides_captions": hides, "variant": variant, "enter": item.get("enter"), "spec": item})
        showpiece_types = set(self.style["showpiece"]["types"])
        for g in out:
            g["raw_start"] = raw_starts.get(g["id"])
            spec = g["spec"]
            # The house spec names the art-directed primitives; an author can flag one by hand.
            g["showpiece"] = bool(spec.get("showpiece")) or g["type"] in showpiece_types or (
                f'{g["type"]}:{g.get("variant") or ""}' in showpiece_types)
            g["covers"] = (g["type"] == "reveal" and spec.get("backdrop", "media_blur") != "none") or bool(spec.get("fullscreen"))
            if g["type"] == "hero" and g.get("variant") != "card" and not g.get("size_px"):
                g["size_px"] = fitted_hero_px(spec)
        return sorted(out, key=lambda g: g["start"])

    def _sfx(self):
        events = self.report.get("sfx_events")
        if events is not None:
            return [dict(e) for e in events]
        found = []
        pattern = re.compile(r'<audio id="sfx-\d+" src="([^"]+)" data-start="([\d.]+)"')
        for src, at in pattern.findall(self.html):
            name = Path(src).name
            m = re.match(r"sfx-([a-z_]+?)(?:-v(\d+)|-[\d_]+)?\.wav$", name)
            kind = m.group(1) if m else "file"
            found.append({"kind": kind, "at": float(at), "role": None, "source": "",
                          "variant": int(m.group(2)) if m and m.group(2) else None})
        return found

    # --- derived tracks ------------------------------------------------------
    def idx(self, seconds):
        return max(0, min(self.samples, int(round(float(seconds) * GRID))))

    @property
    def samples(self):
        return max(1, int(round(self.duration * GRID)))

    def presenter_track(self):
        """Per-sample presenter state from layouts and frame-covering graphics."""
        states = ["full"] * self.samples
        for shot in self.shots:
            state = LAYOUT_STATE.get(shot.get("layout", "presenter"), "full")
            for i in range(self.idx(shot["start"]), self.idx(shot["end"])):
                states[i] = state
        for g in self.graphics:
            if g["covers"]:
                for i in range(self.idx(g["start"]), self.idx(g["end"])):
                    states[i] = "away"
        return states

    def composition_track(self):
        """Per-sample composition key and class (what the viewer is looking at)."""
        n = self.samples
        shot_of = [-1] * n
        for k, shot in enumerate(self.shots):
            for i in range(self.idx(shot["start"]), self.idx(shot["end"])):
                shot_of[i] = k
        camera_epoch = [0] * n
        for move in sorted(self.camera, key=lambda c: float(c.get("at", 0))):
            for i in range(self.idx(move.get("at", 0)), n):
                camera_epoch[i] += 1
        focus_epoch = [0] * n
        for k, shot in enumerate(self.shots):
            if shot.get("layout") == "screen":
                for key in shot.get("focus", []):
                    at = self.t(key.get("at"))
                    if at is not None:
                        for i in range(self.idx(at), self.idx(shot["end"])):
                            focus_epoch[i] += 1
        over = [[] for _ in range(n)]
        cover = [None] * n
        for g in self.graphics:
            for i in range(self.idx(g["start"]), self.idx(g["end"])):
                if g["covers"]:
                    cover[i] = g["id"]
                elif g["type"] not in SMALL_TYPES:
                    over[i].append(g["id"])
        states = self.presenter_track()
        keys, classes = [], []
        for i in range(n):
            layout = self.shots[shot_of[i]].get("layout", "presenter") if shot_of[i] >= 0 else "presenter"
            if cover[i]:
                cls, key = "full_graphic", ("full_graphic", cover[i])
            elif states[i] == "stack":
                cls, key = "stack", ("stack",)
            elif layout == "screen":
                cls, key = "screen", ("screen", shot_of[i], focus_epoch[i])
            elif layout == "full_broll":
                cls, key = "screen", ("broll", shot_of[i])
            elif over[i]:
                cls, key = "presenter_graphic", ("presenter_graphic", tuple(sorted(over[i])), camera_epoch[i], shot_of[i])
            else:
                cls, key = "presenter", ("presenter", shot_of[i], camera_epoch[i])
            keys.append(key)
            classes.append(cls)
        return keys, classes

    def hard_cuts(self):
        """Shot boundaries that change layout or framing without a transition near them."""
        cuts = []
        near = [float(t["at"]) for t in self.transitions]
        for a, b in zip(self.shots, self.shots[1:]):
            at = float(b["start"])
            enter = b.get("enter")
            kind = enter.get("kind") if isinstance(enter, dict) else enter
            if kind not in (None, "cut"):
                continue
            same = (a.get("layout") == b.get("layout") and a.get("frame") == b.get("frame")
                    and a.get("zoom", 1) == b.get("zoom", 1) and a.get("media") == b.get("media"))
            if not same and not any(abs(at - t) < .25 for t in near):
                cuts.append(at)
        return cuts

    def transition_events(self):
        """(time, kind) for every visible transition: explicit, shot entrances, camera punches
        and quick camera pushes on a word (a slow opening drift is not a transition)."""
        events = [(float(t["at"]), t.get("kind", "?")) for t in self.transitions]
        for shot in self.shots:
            enter = shot.get("enter")
            kind = enter.get("kind") if isinstance(enter, dict) else enter
            if kind and kind not in {"cut", "fade", "none"}:
                events.append((float(shot["start"]), kind))
        for move in self.camera:
            if move.get("kind") == "punch":
                events.append((float(move["at"]), "punch"))
            elif move.get("kind") == "push" and float(move.get("at", 0)) > 0 and float(move.get("duration", 1.2)) <= .8:
                events.append((float(move["at"]), "push"))
        for at in self.hard_cuts():
            events.append((at, "cut"))
        return sorted(events)


# ---------------------------------------------------------------------------
class Review:
    def __init__(self, build=None):
        self.build = build
        self.checks = []
        self.metrics = {}

    def add(self, area, check, status, summary, value=None, limit=None, details=None):
        assert area in AREAS and status in (PASS, WARN, FAIL)
        item = {"area": area, "check": check, "status": status, "summary": summary}
        if value is not None:
            item["value"] = value
        if limit is not None:
            item["limit"] = limit
        if details:
            item["details"] = details
        self.checks.append(item)

    def result(self):
        counts = Counter(c["status"] for c in self.checks)
        return {"status": FAIL if counts[FAIL] else WARN if counts[WARN] else PASS,
                "counts": {PASS: counts[PASS], WARN: counts[WARN], FAIL: counts[FAIL]}}


def grade(value, good, bad, higher_is_better=True):
    if higher_is_better:
        return PASS if value >= good else WARN if value >= bad else FAIL
    return PASS if value <= good else WARN if value <= bad else FAIL


# --- timeline checks ----------------------------------------------------------
def check_hook(b, r):
    h = b.style["hook"]
    starts = [g["start"] for g in b.graphics]
    starts += [float(c.get("at", 0)) for c in b.camera]
    starts += [float(t["at"]) - float(t.get("duration", .3)) / 2 for t in b.transitions]
    starts += [float(s["start"]) for s in b.shots if s.get("layout", "presenter") != "presenter" or s.get("zoom_to")]
    first = min(starts, default=math.inf)
    r.metrics["first_motion_s"] = round(first, 2) if first < math.inf else None
    r.add("hook", "first_motion", grade(first, h["first_motion_by"], 1.0, False),
          f"first designed motion at {first:.2f}s" if first < math.inf else "no designed motion at all",
          round(first, 2) if first < math.inf else None, f"<= {h['first_motion_by']}s")
    text = [g for g in b.graphics if g["type"] in BIG_TEXT]
    first_text = text[0]["start"] if text else math.inf
    r.add("hook", "key_words_staged", grade(first_text, h["hero_words_by"], 2.5, False),
          f"large type first lands at {first_text:.2f}s" if text else "no large type in the reel",
          round(first_text, 2) if text else None, f"<= {h['hero_words_by']}s")
    visual = [g["start"] for g in b.graphics if g["showpiece"] or g["type"] in {"reveal", "stat", "device"}]
    visual += [float(s["start"]) for s in b.shots if s.get("layout") in {"screen", "full_broll"}]
    visual += [float(t["at"]) for t in b.transitions if t.get("kind") in SHOWPIECE_TRANSITIONS]
    payoff = min(visual, default=math.inf)
    r.add("hook", "payoff_in_3s", grade(payoff, h["payoff_by"], 5.0, False),
          f"first striking visual (showpiece, screen or result) at {payoff:.2f}s" if payoff < math.inf
          else "no showpiece, screen or result visual anywhere", round(payoff, 2) if payoff < math.inf else None,
          f"<= {h['payoff_by']}s")
    if b.graphics:
        g0 = b.graphics[0]
        hold = g0["end"] - g0["start"]
        if g0["start"] < 1.5 and g0["type"] in {"equation", "headline"}:
            status = FAIL if hold > 3.0 else WARN
            r.add("hook", "slow_open", status, f"opens on a {g0['type']} held {hold:.1f}s; open on the payoff or the "
                  "staged key words instead of a setup card", round(hold, 2), "no equation/title hook")
        else:
            r.add("hook", "slow_open", PASS, f"opens on {g0['type']}" + (f" ({g0['variant']})" if g0.get("variant") else ""))


def check_word_sync(b, r):
    tol = float(b.style["motion"]["word_sync_tolerance"]) + 1 / b.fps
    onsets = np.array(sorted(float(w["start"]) for w in b.words)) if b.words else np.array([])
    keyed = [g for g in b.graphics if g["type"] in KEYED_TYPES]
    off = []
    for g in keyed:
        if g["start"] <= 1.5 / b.fps:
            continue  # on screen from the first frame (a hook card), not an entrance on a word
        raw = g.get("raw_start")
        if isinstance(raw, str) and raw.strip().startswith("@"):
            continue
        if isinstance(raw, dict) and ("word" in raw or "word_index" in raw):
            continue
        d = float(np.min(np.abs(onsets - g["start"]))) if onsets.size else math.inf
        if d > tol:
            off.append(f'{g["id"]} at {g["start"]:.2f}s is {d:.2f}s from the nearest word')
    share = 1 - len(off) / len(keyed) if keyed else 1.0
    r.metrics["word_sync_share"] = round(share, 3)
    r.add("word_sync", "graphic_entrances", grade(share, .9, .75),
          f"{len(keyed) - len(off)} of {len(keyed)} word-bearing graphics enter on a spoken word", round(share, 3),
          ">= 0.9", off[:8])
    if b.words:
        words_ok = all(float(w["end"]) >= float(w["start"]) for w in b.words)
        r.add("word_sync", "caption_timing", PASS if words_ok else FAIL,
              "captions are built from the mapped word times" if words_ok else "mapped words have negative durations")
    else:
        r.add("word_sync", "caption_timing", FAIL, "no mapped words: captions and cues cannot follow the speech")


def check_captions(b, r):
    c, spec = b.captions, b.style["captions"]
    style_name = c.get("style")
    bad = style_name in spec.get("forbid_styles", [])
    r.add("legibility", "caption_style", FAIL if bad else PASS,
          f'captions use "{style_name}"' + (": every word changes color as it is spoken" if bad else ""),
          style_name, f"not {', '.join(spec.get('forbid_styles', []))}")
    groups = int(c.get("groups") or 0)
    if "emphasized" in c and groups:
        per = c["emphasized"] / groups
        times = c.get("emphasis_times", [])
        gaps = [b2 - a for a, b2 in zip(times, times[1:])]
        close = [g for g in gaps if g < spec["emphasis_min_gap"] - .05]
        status = PASS if per <= .5 and not close else WARN
        r.add("legibility", "selective_green", status,
              f'{c["emphasized"]} green words across {groups} caption groups'
              + (f"; {len(close)} closer than {spec['emphasis_min_gap']}s" if close else ""),
              round(per, 2), "<= 0.5 per group, spaced")
    px = float(c.get("font_px_1080", 0))
    r.add("legibility", "caption_size", grade(px, spec["min_px"], spec["floor_px"]), f"spoken captions {px:.0f}px on the 1080 grid",
          round(px, 1), f">= {spec['min_px']}px")
    words = int(c.get("max_words") or 0)
    r.add("legibility", "caption_length", PASS if words <= spec["max_words_allowed"] else WARN,
          f"caption groups up to {words} words", words, f"<= {spec['max_words_allowed']} words")


def text_size_issues(g, minimum):
    issues = []

    def walk(obj, path):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in SIZE_KEYS and isinstance(value, (int, float)) and value < minimum:
                    issues.append(f"{g['id']}.{path}{key} = {value}px")
                walk(value, f"{path}{key}.")
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                walk(value, f"{path}{i}.")
    walk(g["spec"], "")
    return issues


def graphic_box(g):
    """(x, y, w, h) in frame percent; estimates heights the components size to content."""
    x, y, w, h = (g.get("box") or [None] * 4) + [None] * (4 - len(g.get("box") or []))
    spec = g["spec"]
    if g["type"] == "hero" and h is None and y is not None:
        lines = spec.get("lines") or [spec.get("text", "")]
        size = float(spec.get("size", 64 if g.get("variant") == "card" else 136))
        h = len(lines) * size * (1.35 if g.get("variant") == "card" else 1.0) / 19.2
    return x, y, w, h


def check_layout_zones(b, r):
    zones = b.style["zones"]
    shift = float(b.captions.get("y", zones["caption"]["y"])) - float(zones["caption"]["y"])
    band = [zones["caption"]["band"][0] + shift, zones["caption"]["band"][1] + shift]  # where the captions really sit
    safe = zones["platform_safe"]
    hidden = merge_spans(b.captions.get("hidden_spans", []))
    collisions, unsafe = [], []
    for g in b.graphics:
        if g["type"] in SMALL_TYPES or g["covers"]:
            continue
        x, y, w, h = graphic_box(g)
        if y is None:
            continue
        bottom = y + (h or 0)
        if h is not None and y < band[1] and bottom > band[0] and not g.get("hides_captions"):
            shown = (g["end"] - g["start"]) - sum(overlap(g["start"], g["end"], a, z) for a, z in hidden)
            if shown > .2:
                collisions.append(f'{g["id"]} ({y:.0f}-{bottom:.0f}%) shares the caption band for {shown:.1f}s')
        if h is not None and bottom > safe["bottom"] + .5:
            unsafe.append(f'{g["id"]} reaches {bottom:.0f}% (platform text starts near {safe["bottom"]}%)')
        if y < safe["top"] - .5:
            unsafe.append(f'{g["id"]} starts at {y:.0f}% (top bar above {safe["top"]}%)')
        if x is not None and w is not None and x + w > 90.5 and h is not None and bottom > 62:
            unsafe.append(f'{g["id"]} reaches the right edge ({x + w:.0f}%) beside the action buttons')
    r.add("legibility", "caption_zone", PASS if not collisions else WARN,
          "hero text and captions keep separate zones" if not collisions else f"{len(collisions)} graphic(s) sit in the caption band",
          len(collisions), "0", collisions[:6])
    r.add("legibility", "platform_safe", PASS if not unsafe else WARN,
          "graphics stay clear of platform controls" if not unsafe else f"{len(unsafe)} graphic(s) near platform controls",
          len(unsafe), "0", unsafe[:6])
    small = [issue for g in b.graphics for issue in text_size_issues(g, b.style["type"]["min_readable_px"])]
    r.add("legibility", "text_size", PASS if not small else WARN,
          "authored text sizes stay readable at phone size" if not small else f"{len(small)} text size(s) below "
          f"{b.style['type']['min_readable_px']}px", len(small), f">= {b.style['type']['min_readable_px']}px", small[:6])
    heroes = [(g["id"], float(g.get("size_px") or fitted_hero_px(g["spec"]))) for g in b.graphics
              if g["type"] == "hero" and g.get("variant") != "card"]
    if heroes:
        low = b.style["type"]["hero_px"]["min"]
        sizes = [px for _, px in heroes]
        shrunk = [f"{gid} fits at {px:.0f}px" for gid, px in heroes if px < low]
        r.add("legibility", "hero_scale", PASS if not shrunk else WARN,
              f"hero type renders at {min(sizes):.0f}-{max(sizes):.0f}px" + ("; shorten the phrase or split it" if shrunk else ""),
              round(min(sizes)), f">= {low}px", shrunk[:6])


def check_presenter(b, r):
    lay = b.style["layout"]
    states = b.presenter_track()
    n = len(states)
    share = {s: states.count(s) / n for s in ("full", "stack", "away")}
    r.metrics["presenter_timeline"] = {k: round(v, 3) for k, v in share.items()}
    r.add("presenter", "full_size_share", grade(share["full"], lay["presenter_full_min"], lay["presenter_full_min"] - .15),
          f"Brandon full size for {share['full']:.0%} of the reel", round(share["full"], 3),
          f">= {lay['presenter_full_min']:.0%}")
    visible = share["full"] + share["stack"]
    r.add("presenter", "visible_share", grade(visible, lay["presenter_visible_min"], lay["presenter_visible_min"] - .15),
          f"on screen (any size) {visible:.0%}", round(visible, 3), f">= {lay['presenter_visible_min']:.0%}")
    stacks = runs(states, "stack")
    worst = longest(stacks)
    status = PASS
    if worst > lay["stack_max_seconds"] or share["stack"] > lay["stack_max_share"]:
        status = FAIL if worst > lay["stack_max_seconds"] * 1.5 or share["stack"] > lay["stack_max_share"] * 1.5 else WARN
    r.add("presenter", "stacked_band", status,
          f"shrunk into a band for {share['stack']:.0%} (longest {worst:.1f}s)" if stacks else "never shrunk into a band",
          round(worst, 2), f"<= {lay['stack_max_seconds']}s and <= {lay['stack_max_share']:.0%}",
          [f"{a:.1f}-{z:.1f}s" for a, z in stacks])
    away = runs(states, "away")
    showpiece_spans = [(g["start"], g["end"]) for g in b.graphics if g["showpiece"] and g["covers"]]
    long_away = []
    for a, z in away:
        limit = lay["showpiece_away_max_seconds"] if any(overlap(a, z, s, e) > (z - a) / 2 for s, e in showpiece_spans) \
            else lay["away_max_seconds"]
        if z - a > limit + 1e-6:
            long_away.append(f"{a:.1f}-{z:.1f}s ({z - a:.1f}s > {limit}s)")
    r.add("presenter", "away_runs", PASS if not long_away else WARN,
          f"longest time without Brandon {longest(away):.1f}s", round(longest(away), 2),
          f"<= {lay['away_max_seconds']}s ({lay['showpiece_away_max_seconds']}s for a showpiece)", long_away)
    r.add("presenter", "full_screen_share", grade(share["away"], lay["fullscreen_max_share"], lay["fullscreen_max_share"] + .15, False),
          f"full-screen screens/graphics {share['away']:.0%}", round(share["away"], 3), f"<= {lay['fullscreen_max_share']:.0%}")


def check_progression(b, r):
    lay = b.style["layout"]
    hold = b.style["motion"]["hold"]
    keys, classes = b.composition_track()
    worst, where = 0.0, None
    start = 0
    for i in range(1, len(keys) + 1):
        if i == len(keys) or keys[i] != keys[start]:
            length = (i - start) / GRID
            if length > worst:
                worst, where = length, (start / GRID, i / GRID, classes[start])
            start = i
    limit = lay["same_composition_max_seconds"]
    r.metrics["longest_same_composition_s"] = round(worst, 2)
    r.add("progression", "same_composition", grade(worst, limit, limit * 1.5, False),
          f"longest unchanged composition {worst:.1f}s" + (f" ({where[2].replace('_', ' ')}, {where[0]:.1f}-{where[1]:.1f}s)" if where else ""),
          round(worst, 2), f"<= {limit}s")
    used = {c: classes.count(c) / GRID for c in set(classes)}
    kinds = sorted(c for c, s in used.items() if s >= 1.0)
    need = 3 if b.duration >= 20 else 2 if b.duration >= 8 else 1
    r.metrics["composition_seconds"] = {k: round(v, 2) for k, v in sorted(used.items())}
    footage = any(s.get("layout") in {"screen", "full_broll", "stage", "split"} for s in b.shots) or any(
        g["type"] in {"reveal", "device"} for g in b.graphics)
    frames = sorted({s.get("frame", "center") for s in b.shots if s.get("layout", "presenter") == "presenter"
                     and float(s["end"]) - float(s["start"]) >= 1.0})
    if not footage and need == 3:
        # No captures in this story: the arc runs on framings (wide, close, a side with callouts) and type.
        ok = len(kinds) >= 2 and len(frames) >= 3
        r.add("progression", "composition_range", PASS if ok else WARN,
              f"compositions used: {', '.join(k.replace('_', ' ') for k in kinds)}; framings: {', '.join(frames)}",
              len(kinds), ">= 2 compositions and 3 framings (no footage)")
    else:
        r.add("progression", "composition_range", PASS if len(kinds) >= need else WARN,
              f"compositions used: {', '.join(k.replace('_', ' ') for k in kinds)}", len(kinds), f">= {need}")
    short = []
    eps = 1e-3  # frame-snapped times; a hold of exactly the minimum passes
    for g in b.graphics:
        length = g["end"] - g["start"]
        if g["type"] in INFO_TYPES and length < hold["info_min"] - eps:
            short.append((g, length, hold["info_min"], 1.2))
        elif g["type"] in {"hero", "statement", "headline"} and length < hold["hero_min"] - eps:
            short.append((g, length, hold["hero_min"], .6))
    for s in b.shots:
        if s.get("layout") == "screen" and float(s["end"]) - float(s["start"]) < hold["screen_min"] - eps:
            short.append(({"id": f"screen shot at {float(s['start']):.1f}s"}, float(s["end"]) - float(s["start"]), hold["screen_min"], .8))
    status = FAIL if any(length < floor for _, length, _, floor in short) else WARN if short else PASS
    r.add("progression", "reading_holds", status,
          "information holds long enough to read" if not short else f"{len(short)} item(s) leave before they can be read",
          len(short), f"info >= {hold['info_min']}s, hero >= {hold['hero_min']}s",
          [f'{g["id"]} holds {length:.2f}s (< {need_s}s)' for g, length, need_s, _ in short][:8])
    # Hero variants are different primitives (their own entrances, exits and layouts).
    types = Counter(f'{g["type"]}:{g.get("variant") or "stack"}' if g["type"] == "hero" else g["type"]
                    for g in b.graphics if g["type"] not in SMALL_TYPES)
    total = sum(types.values())
    if total >= 5:
        kind, count = types.most_common(1)[0]
        r.add("progression", "graphic_variety", PASS if count / total <= .4 else WARN,
              f"most used graphic: {kind} ({count} of {total})", round(count / total, 2), "<= 0.4")
    variants = [g.get("variant") or "stack" for g in b.graphics if g["type"] == "hero"]
    repeats = max((sum(1 for _ in grp) for _, grp in __import__("itertools").groupby(variants)), default=0)
    if len(variants) >= 3:
        r.add("progression", "hero_variety", PASS if repeats < 3 else WARN,
              f"hero variants: {', '.join(variants)}", repeats, "< 3 in a row")
    motifs = b.style["variety"].get("retired_motifs", {})
    used_icons = set()

    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "icon" and isinstance(value, str):
                    used_icons.add(value)
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)
    for g in b.graphics:
        walk(g["spec"])
    avoid = b.resolved.get("variation", {}).get("avoid", {})
    retired = (set(motifs.get("icons", [])) | set(avoid.get("icons", []))) & used_icons
    r.add("progression", "fresh_motifs", PASS if not retired else WARN,
          "no retired motifs" if not retired else f"reuses retired motif icons: {', '.join(sorted(retired))}",
          sorted(retired) or None, "none of " + ", ".join(sorted(motifs.get("icons", []))))
    if b.graphics and b.duration >= 20:
        closing = [g for g in b.graphics if g["end"] > b.duration * .65]
        lists = [g for g in closing if g["type"] in set(motifs.get("closing_types", []))]
        designed = any(g["showpiece"] for g in closing) or any(
            float(t["at"]) >= b.duration * .65 and t.get("kind") in SHOWPIECE_TRANSITIONS for t in b.transitions)
        problems = []
        if lists:
            problems.append(f"the ending recaps with a {lists[0]['type']} ({lists[0]['id']})")
        if not designed:
            problems.append("no showpiece in the closing third")
        r.add("progression", "designed_payoff", WARN if problems else PASS,
              "; ".join(problems) if problems else "the ending builds to a designed payoff")


def check_transitions(b, r):
    spec = b.style["transitions"]
    events = b.transition_events()
    kinds = [k for _, k in events]
    forbidden = [f"{k} at {t:.1f}s" for t, k in events if k in spec["forbidden"]]
    for flash in b.resolved.get("flashes", []):
        color = str(flash.get("color", "")).lower()
        if color in {"#49cf26", "green", b.style["color"]["accent"].lower()}:
            forbidden.append(f"green flash at {flash.get('at')}")
    r.add("transitions", "retired_transitions", FAIL if forbidden else PASS,
          "no green wipe or green flash" if not forbidden else "retired transitions present", len(forbidden), "0", forbidden)
    styled = [k for k in kinds if k != "cut"]
    r.metrics["transitions"] = dict(Counter(kinds))
    if b.duration >= 12 and not events:
        r.add("transitions", "section_changes", WARN, "no transitions or hard cuts between sections", 0, ">= 1")
    if len(styled) >= 3:
        kind, count = Counter(styled).most_common(1)[0]
        allowed = max(2, math.floor(spec["max_share"] * len(styled)))  # two of a kind is not a preset
        r.add("transitions", "no_single_preset", PASS if count <= allowed else WARN,
              f"most used transition: {kind} ({count} of {len(styled)})", round(count / len(styled), 2),
              f"<= {spec['max_share']} (or 2)")
    repeats = [f"{a[1]} at {a[0]:.1f}s and {b2[0]:.1f}s" for a, b2 in zip(events, events[1:])
               if a[1] == b2[1] and a[1] != "cut"]
    if spec.get("no_adjacent_repeat"):
        r.add("transitions", "adjacent_repeat", PASS if not repeats else WARN,
              "no transition repeats back to back" if not repeats else f"{len(repeats)} back-to-back repeat(s)",
              len(repeats), "0", repeats[:5])
    if b.duration >= 15:
        windows, thin = max(1, int(round(b.duration / 30))), []
        for w in range(windows):
            a, z = w * b.duration / windows, (w + 1) * b.duration / windows
            present = {k for t, k in events if a <= t < z}
            if len(present) < spec["min_kinds_per_30s"]:
                thin.append(f"{a:.0f}-{z:.0f}s: {', '.join(sorted(present)) or 'none'}")
        r.add("transitions", "mix", PASS if not thin else WARN,
              f"{len(set(kinds))} kinds: {', '.join(sorted(set(kinds)))}" if kinds else "no transitions",
              len(set(kinds)), f">= {spec['min_kinds_per_30s']} kinds per 30s", thin)


def showpieces(b):
    items = [(g["start"], f'{g["type"]}{":" + g["variant"] if g.get("variant") else ""} {g["id"]}') for g in b.graphics if g["showpiece"]]
    items += [(float(t["at"]), f'transition:{t["kind"]}') for t in b.transitions if t.get("kind") in SHOWPIECE_TRANSITIONS]
    items += [(float(s["start"]), "screen:2.5D") for s in b.shots if s.get("layout") == "screen"]
    return sorted(items)


def check_motion_craft(b, r):
    need = b.style["showpiece"]["min_count"] if b.duration >= 20 else 1
    items = showpieces(b)
    r.metrics["showpieces"] = [f"{t:.1f}s {label}" for t, label in items]
    r.add("motion_craft", "showpiece_count", PASS if len(items) >= need else WARN if items else FAIL,
          f"{len(items)} art-directed moment(s)", len(items), f">= {need}", r.metrics["showpieces"])
    hook = [t for t, _ in items if t <= b.style["hook"]["payoff_by"] + .5]
    r.add("motion_craft", "hook_showpiece", PASS if hook else WARN,
          "the hook has an art-directed moment" if hook else "no art-directed moment in the first 3 seconds")
    entrances = [g.get("enter") for g in b.graphics if g["type"] not in {"headline", "hero", "reveal", "particles"}]
    run = max((sum(1 for _ in grp) for _, grp in __import__("itertools").groupby(entrances)), default=0)
    if len(entrances) >= 4:
        r.add("motion_craft", "entrance_variety", PASS if run < 4 else WARN,
              f"{len(set(entrances))} entrance styles across {len(entrances)} graphics", run, "< 4 identical in a row")


def check_sound(b, r):
    s = b.style["sound"]
    music = b.resolved.get("music") or []
    r.add("sound", "no_music", FAIL if music else PASS, "no background music" if not music else f"{len(music)} music item(s)")
    kinds = [e["kind"] for e in b.sfx]
    r.metrics["sfx"] = dict(Counter(kinds))
    bad = sorted({k for k in kinds if k in s["forbidden_kinds"]})
    r.add("sound", "retired_sounds", FAIL if bad else PASS,
          "no beeps, ticks or old pops" if not bad else f"retired sounds used: {', '.join(bad)}", bad or None, "none")
    popups = [e for e in b.sfx if e.get("role") in {"popup", "popup_soft"}]
    wrong = sorted({e["kind"] for e in popups if e["kind"] not in {"bubble", "bubble_soft"}})
    bubbles = [e for e in b.sfx if e["kind"] in {"bubble", "bubble_soft"}]
    if popups or bubbles:
        r.add("sound", "popup_is_bubble", FAIL if wrong else PASS,
              "pop-ups land with the soft bubble family" if not wrong else f"pop-ups use {', '.join(wrong)}")
    if len(bubbles) >= 3:
        variants = {e.get("variant") for e in bubbles}
        r.add("sound", "bubble_variation", PASS if len(variants) >= 2 else WARN,
              f"{len(bubbles)} bubbles over {len(variants)} pitch/texture variants", len(variants), ">= 2")
    times = sorted(e["at"] for e in b.sfx)
    from sfx_kit import SUSTAINED
    transient = sorted(e["at"] for e in b.sfx if e["kind"] not in SUSTAINED)
    dense = max((sum(1 for u in transient if t <= u < t + 10) for t in transient), default=0)
    r.add("sound", "density", grade(dense, s["max_per_10s"], s["max_per_10s"] + 2, False),
          f"at most {dense} effects in any 10 seconds ({len(times)} total)", dense, f"<= {s['max_per_10s']} per 10s")
    impacts = sorted(e["at"] for e in b.sfx if e["kind"] in IMPACTS)
    close = [f"{a:.1f}s/{z:.1f}s" for a, z in zip(impacts, impacts[1:]) if z - a < s["impact_gap"]]
    r.add("sound", "impacts", PASS if len(impacts) <= s["max_impacts"] and not close else WARN,
          f"{len(impacts)} impact(s)" + (f", {len(close)} too close" if close else ""), len(impacts),
          f"<= {s['max_impacts']}, {s['impact_gap']}s apart", close)
    if b.words:
        per_word = len(times) / len(b.words)
        cap = float(s.get("max_per_word", .12))
        r.add("sound", "not_every_word", PASS if per_word <= cap + 1e-9 or len(times) <= 2 else WARN,
              f"{len(times)} effects for {len(b.words)} spoken words", round(per_word, 3), f"<= {cap} per word")
    cuts = b.hard_cuts()
    on_cuts = [c for c in cuts if any(abs(c - t) < .08 for t in times)]
    if len(cuts) >= 3:
        r.add("sound", "cuts_stay_dry", PASS if len(on_cuts) <= max(1, len(cuts) * .3) else WARN,
              f"{len(on_cuts)} of {len(cuts)} hard cuts carry a sound", len(on_cuts), "<= 30% of cuts")
    levels = b.report.get("sfx_levels", {})
    phone = {k: v for k, v in (levels.get("phone_band_offset_lu") or {}).items() if v is not None}
    loud = {k: v for k, v in phone.items() if v > s["phone_max_lu_over_voice"]}
    if phone:
        r.add("sound", "phone_speaker_mix", PASS if not loud else WARN,
              "effects sit under the voice on a phone speaker band" if not loud else
              "loud on a phone speaker: " + ", ".join(f"{k} {v:+.1f} LU" for k, v in loud.items()),
              round(max(phone.values()), 1), f"<= {s['phone_max_lu_over_voice']} LU vs voice")


def all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if key not in {"media", "path", "id", "beat", "at", "start", "end", "icon", "variant", "type", "font_path"}:
                yield from all_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from all_strings(value)


def check_forbidden(b, r):
    words = b.style["forbidden"]["disclaimer_words"]
    hits = []
    for source in (b.resolved.get("graphics", []), b.resolved.get("labels", []), b.resolved.get("editorial_graphics", [])):
        for text in all_strings(source):
            low = text.casefold()
            hits += [f'"{w}" in "{text[:60]}"' for w in words if w in low]
    r.add("forbidden", "disclaimers", FAIL if hits else PASS,
          "no disclaimers or caveats on screen" if not hits else f"{len(hits)} disclaimer phrase(s) on screen",
          len(hits), "0", hits[:6])
    bars = []

    def walk(obj, where):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"timer", "timer_bar", "progress", "progress_bar", "bars", "row_bars"} and value:
                    bars.append(f"{where}.{key}")
                walk(value, where)
        elif isinstance(obj, list):
            for value in obj:
                walk(value, where)
    for g in b.graphics:
        walk(g["spec"], g["id"])
    r.add("forbidden", "timer_bars", FAIL if bars else PASS,
          "no timer-bar pop-ups" if not bars else "timer/progress bars on pop-ups", len(bars), "0", bars)


def check_pacing(b, r):
    if not b.words:
        return
    words = sorted(b.words, key=lambda w: float(w["start"]))
    gaps = [(float(a["end"]), float(z["start"])) for a, z in zip(words, words[1:])]
    long_gaps = [(a, z) for a, z in gaps if z - a > .5]
    worst = max((z - a for a, z in gaps), default=0)
    r.metrics["longest_word_gap_s"] = round(worst, 2)
    r.add("pacing", "speech_gaps", grade(worst, .5, .8, False),
          f"longest pause between words {worst:.2f}s", round(worst, 2), "<= 0.5s",
          [f"{a:.2f}-{z:.2f}s ({z - a:.2f}s)" for a, z in long_gaps][:8])
    tail = b.duration - float(words[-1]["end"])
    r.add("pacing", "ending_tail", PASS if tail <= 1.2 else WARN, f"{tail:.2f}s after the last word", round(tail, 2), "<= 1.2s")


# --- render checks -------------------------------------------------------------
def gray_frames(video, fps, width=180, height=320, start=0.0, end=None):
    args = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video)]
    if end is not None:
        args += ["-t", f"{max(.05, end - start):.3f}"]
    args += ["-vf", f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
             f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    count = len(raw) // (width * height)
    return np.frombuffer(raw[:count * width * height], dtype=np.uint8).reshape(count, height, width)


def audio_metrics(video, spec):
    out = {}
    silence = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af",
                              "silencedetect=noise=-38dB:d=0.45", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", silence)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", silence)]
    out["silences"] = [[round(a, 2), round(z, 2)] for a, z in zip(starts, ends)]

    def loud(extra=""):
        text = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", f"{extra}ebur128=peak=true",
                               "-f", "null", "-"], capture_output=True, text=True).stderr
        integrated = re.findall(r"I:\s*(-?[\d.]+) LUFS", text)
        peak = re.findall(r"Peak:\s*(-?[\d.]+|-inf) dBFS", text)
        return (float(integrated[-1]) if integrated else None,
                float(peak[-1]) if peak and peak[-1] != "-inf" else None)
    out["integrated_lufs"], out["true_peak_dbfs"] = loud()
    lo, hi = spec["sound"]["phone_band_hz"]
    out["phone_band_lufs"], _ = loud(f"highpass=f={lo}:poles=2,highpass=f={lo}:poles=2,lowpass=f={hi}:poles=2,")
    return out


def decode_audio(path, rate, start=None, duration=None):
    args = ["ffmpeg", "-v", "error"]
    if start is not None:
        args += ["-ss", f"{float(start):.4f}"]
    args += ["-i", str(path)]
    if duration is not None:
        args += ["-t", f"{float(duration):.4f}"]
    args += ["-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def bandpass(signal, rate, lo, hi):
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / rate)
    spectrum[(freqs < lo) | (freqs > hi)] = 0
    return np.fft.irfft(spectrum, len(signal))


def k_weight(signal, rate):
    """ITU-R BS.1770 K-weighting (a +4 dB shelf above ~1.5 kHz and a 38 Hz high-pass), so a
    level reads in loudness units the way the builder sets it, not as raw energy: a low thump
    and a voice at the same RMS do not sound equally loud."""
    from scipy.signal import lfilter
    a_gain = 10 ** (4.0 / 40)
    w0 = 2 * math.pi * 1500 / rate
    alpha = math.sin(w0) / (2 * (1 / math.sqrt(2)))
    cos, root = math.cos(w0), 2 * math.sqrt(a_gain) * alpha
    b = [a_gain * ((a_gain + 1) + (a_gain - 1) * cos + root), -2 * a_gain * ((a_gain - 1) + (a_gain + 1) * cos),
         a_gain * ((a_gain + 1) + (a_gain - 1) * cos - root)]
    a = [(a_gain + 1) - (a_gain - 1) * cos + root, 2 * ((a_gain - 1) - (a_gain + 1) * cos),
         (a_gain + 1) - (a_gain - 1) * cos - root]
    shelved = lfilter(b, a, signal)
    w0 = 2 * math.pi * 38 / rate
    alpha, cos = math.sin(w0) / (2 * .5), math.cos(w0)
    b = [(1 + cos) / 2, -(1 + cos), (1 + cos) / 2]
    a = [1 + alpha, -2 * cos, 1 - alpha]
    return lfilter(b, a, shelved)


def sfx_spans(b):
    """(start, end) of every effect as placed in the composition."""
    spans = [(float(a), float(a) + float(d)) for a, d in
             re.findall(r'<audio id="sfx-\d+" src="[^"]+" data-start="([\d.]+)" data-duration="([\d.]+)"', b.html)]
    return spans or [(e["at"], e["at"] + .5) for e in b.sfx]


def mix_analysis(b, video, rate=32000, _fallback=True):
    """Separate the effects from the voice in a render and level each effect against
    speech, full band and through a phone-speaker band.

    The voice is rebuilt from the build's own source segments, aligned to the render and
    scaled by least squares; what remains is the effects bed plus codec noise. This needs
    the render before loudness finalizing (a dynamic normalizer rides the gain); given a
    finalized file, the raw render named in render-receipt.json is used instead."""
    from scipy.signal import correlate
    tags = re.findall(r'<audio id="voice-\d+" src="([^"]+)" data-start="([\d.]+)" data-duration="([\d.]+)" '
                      r'data-media-start="([\d.]+)"', b.html)
    if not tags or not b.sfx:
        return {"note": "no voice track or effects to separate", "events": []}
    try:
        mixed = decode_audio(video, rate)
    except subprocess.CalledProcessError:
        mixed = np.zeros(0)
    if mixed.size < rate or float(np.max(np.abs(mixed))) < 1e-5:
        return {"note": "the render has no audible audio stream to measure", "events": []}
    clips = []
    for src, start, dur, media_start in tags:
        try:
            seg = decode_audio(b.project / src, rate, media_start, dur)
        except subprocess.CalledProcessError:
            return {"note": f"could not read the voice source {src}; listen instead", "events": []}
        clips.append((int(round(float(start) * rate)), seg))

    def place(clips):
        track = np.zeros_like(mixed)
        for a, seg in clips:
            a = max(0, a)
            seg = seg[:max(0, len(track) - a)]
            track[a:a + len(seg)] = seg
        return track
    voice = place(clips)
    if float(np.max(np.abs(voice))) < 1e-5:
        return {"note": "the voice source is silent where the reel uses it; listen instead", "events": []}
    n = min(len(mixed), rate * 15)
    corr = correlate(mixed[:n], voice[:n], mode="full", method="fft")
    lags = np.arange(-n + 1, n)
    keep = np.abs(lags) <= int(.1 * rate)
    lag = int(lags[keep][np.argmax(corr[keep])])
    # The renderer rounds each clip's placement (to whole milliseconds), and a fraction of a
    # millisecond is enough to decorrelate speech, so refine every clip on its own.
    reach, refined = int(.003 * rate), []
    for a, seg in clips:
        a += lag
        length = min(len(seg), len(mixed) - a - reach, rate * 10)
        if a - reach >= 0 and length > rate // 4:
            window = mixed[a - reach:a + length + reach]
            fit = correlate(window, seg[:length], mode="valid", method="fft")  # one value per offset
            a += int(np.argmax(fit)) - reach
        refined.append((a, seg))
    voice = place(refined)
    quiet = np.ones(len(mixed), dtype=bool)
    for a, z in sfx_spans(b):
        quiet[int(max(0, a - .05) * rate):int((z + .15) * rate)] = False
    block = int(.5 * rate)
    count = len(mixed) // block
    blocks = [slice(i * block, (i + 1) * block) for i in range(count) if quiet[i * block:(i + 1) * block].all()]
    energy = np.array([np.dot(voice[s], voice[s]) for s in blocks])
    strong = [s for s, e in zip(blocks, energy) if e > np.percentile(energy, 40) and e > 1e-9] if blocks else []
    if len(strong) < 4:
        return {"note": "too little effect-free speech to level the effects against; listen instead", "events": []}
    gains = np.array([np.dot(mixed[s], voice[s]) / np.dot(voice[s], voice[s]) for s in strong])
    gain = float(np.median(gains))
    spread = float(np.std(gains) / max(abs(gain), 1e-9))
    if spread > .03 and _fallback:
        receipt = read_json(b.project / "render-receipt.json", {})
        raw = receipt.get("format", {}).get("filename")
        if raw and Path(raw).is_file() and Path(raw).resolve() != Path(video).resolve():
            result = mix_analysis(b, Path(raw), rate, _fallback=False)
            result["measured_on"] = str(raw)
            return result
    if spread > .03:
        return {"note": f"the voice gain rides by {spread:.0%} across this file (loudness finalizing); measure the raw "
                        "render to level the effects", "events": [], "gain_spread": round(spread, 3)}
    voice *= gain
    residual = mixed - voice
    lo, hi = b.style["sound"]["phone_band_hz"]
    phone_voice, phone_residual = bandpass(voice, rate, lo, hi), bandpass(residual, rate, lo, hi)
    k_voice, k_residual = k_weight(voice, rate), k_weight(residual, rate)

    def level(signal, spans):
        return float(np.sqrt(np.mean(np.concatenate([signal[s] for s in spans]) ** 2)))
    ref_full, ref_phone = level(k_voice, strong), level(phone_voice, strong)
    floor = 20 * math.log10(max(level(k_residual, strong), 1e-9) / ref_full)
    events = []
    for e in b.sfx:
        a = int(max(0, e["at"] - .02) * rate)
        z = min(len(mixed), a + int(.45 * rate))
        if z - a < rate // 20:
            continue
        full = float(np.sqrt(np.mean(k_residual[a:z] ** 2)))
        phone = float(np.sqrt(np.mean(phone_residual[a:z] ** 2)))
        events.append({"kind": e["kind"], "at": round(e["at"], 3),
                       "effect_lu": round(20 * math.log10(max(full, 1e-9) / ref_full), 1),
                       "phone_effect_db": round(20 * math.log10(max(phone, 1e-9) / ref_phone), 1)})
    return {"lag_ms": round(lag / rate * 1000, 1), "voice_gain": round(gain, 3), "gain_spread": round(spread, 4),
            "floor_db": round(floor, 1), "events": events}


def measure_render(video, spec, fps=5.0, build=None):
    """Render-only metrics: face track, dark spans, change cadence, silences, loudness,
    and (with a build) each effect's level against the voice."""
    import track_face
    lay = spec["layout"]
    face = track_face.track(video, fps)
    samples = face["samples"]
    states = []
    for s in samples:
        box = s["face"]
        if not box:
            states.append("away")
        else:
            x, y, w, h = box
            big = h / 100 >= lay["face_full_min"]
            high = y + h / 2 < 50
            states.append("full" if big and high else "stack")
    step = 1 / fps
    frames = gray_frames(video, fps)
    n = min(len(frames), len(states))
    dark = [(float(np.mean(frames[i] < spec["layout"]["black_luma"]))) for i in range(len(frames))]
    diff = [0.0] + [float(np.mean(np.abs(frames[i].astype(np.int16) - frames[i - 1].astype(np.int16))))
                    for i in range(1, len(frames))]
    head = gray_frames(video, 30, end=1.0)
    head_diff = [float(np.mean(np.abs(head[i].astype(np.int16) - head[i - 1].astype(np.int16)))) for i in range(1, len(head))]
    first_change = next((i / 30 for i, d in enumerate(head_diff, start=1) if d > 2.0), None)
    dark_flags = ["dark" if d > lay["black_area"] else "" for d in dark]
    static_flags = ["static" if d < 1.2 else "" for d in diff]
    metrics = {
        "video": str(video), "duration": face["duration"], "fps": fps,
        "presenter": {k: round(states[:n].count(k) / max(1, n), 3) for k in ("full", "stack", "away")},
        "presenter_runs": {k: [[round(a, 2), round(z, 2)] for a, z in runs(states, k, step)] for k in ("stack", "away")},
        "presenter_strip": "".join({"full": "F", "stack": "s", "away": "."}[st] for st in states),
        "dark_runs": [[round(a, 2), round(z, 2)] for a, z in runs(dark_flags, "dark", step)],
        "dark_share": round(sum(1 for d in dark_flags if d) / max(1, len(dark_flags)), 3),
        "static_runs": [[round(a, 2), round(z, 2)] for a, z in runs(static_flags, "static", step) if z - a >= 1.0],
        "mean_change": round(float(np.mean(diff[1:])) if len(diff) > 1 else 0.0, 2),
        "first_change_s": first_change,
    }
    metrics.update(audio_metrics(video, spec))
    if build is not None:
        metrics["mix"] = mix_analysis(build, video)
    return metrics


def check_render(b, r, m, spec=None):
    spec = b.style if b else (spec or style.load())
    lay = spec["layout"]
    r.metrics["render"] = m
    full = m["presenter"]["full"]
    r.add("presenter", "render_full_size", grade(full, lay["presenter_full_min"], lay["presenter_full_min"] - .15),
          f"face tracked at full size for {full:.0%} of the render", full, f">= {lay['presenter_full_min']:.0%}")
    stacks = [z - a for a, z in m["presenter_runs"]["stack"]]
    worst = max(stacks, default=0.0)
    r.add("presenter", "render_small_face", grade(worst, lay["stack_max_seconds"], lay["stack_max_seconds"] * 1.5, False),
          f"longest run with a small or lowered face {worst:.1f}s", round(worst, 2), f"<= {lay['stack_max_seconds']}s",
          [f"{a:.1f}-{z:.1f}s" for a, z in m["presenter_runs"]["stack"] if z - a > 1.0])
    showpiece_spans = [(g["start"], g["end"]) for g in b.graphics if g["showpiece"]] if b else []
    long_dark = []
    for a, z in m["dark_runs"]:
        limit = lay["showpiece_away_max_seconds"] if any(overlap(a, z, s, e) > (z - a) / 2 for s, e in showpiece_spans) \
            else lay["black_max_seconds"]
        if z - a > limit:
            long_dark.append(f"{a:.1f}-{z:.1f}s ({z - a:.1f}s)")
    worst_dark = max((z - a for a, z in m["dark_runs"]), default=0.0)
    r.add("progression", "dark_card_spans", PASS if not long_dark else WARN if len(long_dark) == 1 else FAIL,
          f"longest mostly-black frame span {worst_dark:.1f}s ({m['dark_share']:.0%} of frames mostly black)",
          round(worst_dark, 2), f"<= {lay['black_max_seconds']}s", long_dark)
    statics = [f"{a:.1f}-{z:.1f}s" for a, z in m["static_runs"] if z - a > 2.5]
    r.add("progression", "render_static", PASS if not statics else WARN,
          "the picture keeps moving" if not statics else f"{len(statics)} near-static stretch(es) over 2.5s", len(statics), "0", statics)
    first = m.get("first_change_s")
    r.add("hook", "render_first_motion", PASS if first is not None and first <= spec["hook"]["first_motion_by"] else WARN,
          f"the picture changes at {first:.2f}s" if first is not None else "no visible change in the first second",
          round(first, 2) if first is not None else None, f"<= {spec['hook']['first_motion_by']}s")
    words = sorted(b.words, key=lambda w: float(w["start"])) if b and b.words else []
    last_word = float(words[-1]["end"]) if words else m["duration"]
    gaps = [(a, z) for a, z in m["silences"] if a > .15 and z < last_word + .1 and z - a > .5]
    worst_gap = max((z - a for a, z in gaps), default=0.0)
    r.add("pacing", "render_silences", grade(worst_gap, .5, .8, False),
          f"longest silence inside the speech {worst_gap:.2f}s" if gaps else "no silence over 0.5s inside the speech",
          round(worst_gap, 2), "<= 0.5s", [f"{a:.2f}-{z:.2f}s" for a, z in gaps][:6])
    peak = m.get("true_peak_dbfs")
    if peak is not None:
        r.add("sound", "true_peak", PASS if peak <= -1.0 else WARN, f"true peak {peak:.1f} dBFS", peak, "<= -1.0 dBFS")
    mix = m.get("mix")
    if mix and mix.get("events"):
        limit = spec["sound"]["phone_max_lu_over_voice"]
        for band_name, key, label in (("full", "effect_lu", "headphones (full band, loudness-weighted)"),
                                      ("phone", "phone_effect_db", "phone speaker band")):
            values = [e[key] for e in mix["events"] if e.get(key) is not None]
            if not values:
                continue
            unit = "LU" if band_name == "full" else "dB"
            loud = [f'{e["kind"]} at {e["at"]:.2f}s {e[key]:+.1f} {unit}' for e in mix["events"]
                    if e.get(key) is not None and e[key] > limit]
            worst = max(values)
            r.add("sound", f"effects_under_voice_{band_name}", grade(worst, limit, limit + 4, False),
                  f"on {label} the loudest effect sits {worst:+.1f} {unit} against speech (median {float(np.median(values)):+.1f} {unit})",
                  round(worst, 1), f"<= {limit} {unit}", loud[:6])
        offsets = spec["sound"]["voice_offset_lu"]
        hot = [f'{e["kind"]} at {e["at"]:.2f}s {e["effect_lu"]:+.1f} LU (house {offsets[e["kind"]]} LU)'
               for e in mix["events"] if e["kind"] in offsets and e["effect_lu"] > offsets[e["kind"]] + 4]
        r.add("sound", "effects_at_house_level", PASS if not hot else WARN,
              "each effect sits near its house level under the voice" if not hot else
              f"{len(hot)} effect(s) more than 4 LU over their house level", len(hot), "0", hot[:6])
    elif mix and mix.get("note"):
        r.add("sound", "effects_under_voice_full", WARN, mix["note"])


# --- regression against the approved calibration --------------------------------
def regression(b, r, reference):
    ref = reference.get("metrics", {})
    if not ref:
        return
    first = r.metrics.get("first_motion_s")
    scene = min([float(t["at"]) for t in b.transitions] + [float(s["start"]) for s in b.shots
                 if s.get("layout", "presenter") != "presenter" and float(s["start"]) > 0] + [math.inf])
    target = ref.get("first_scene_change_s")
    if target is not None:
        value = min(scene, first if first is not None else math.inf)
        r.add("regression", "first_change", PASS if value <= target + .1 else WARN,
              f"first visual change {value:.2f}s (calibration {target}s)", round(value, 2) if value < math.inf else None,
              f"<= {target}s")
    styled = len(b.transitions) + sum(1 for shot in b.shots
                                      if (shot.get("enter", {}).get("kind") if isinstance(shot.get("enter"), dict)
                                          else shot.get("enter")) not in (None, "cut", "fade", "none"))
    per10 = styled / b.duration * 10 if b.duration else 0
    lo, hi = ref.get("transitions_per_10s_range", [None, None])
    if lo is not None:
        r.add("regression", "transition_rate", PASS if lo <= per10 <= hi else WARN,
              f"{per10:.1f} styled transitions per 10s (calibration {ref.get('transitions_per_10s')})",
              round(per10, 2), f"{lo}-{hi}")
    cap = b.captions.get("font_px_1080", 0)
    if ref.get("caption_px_1080"):
        r.add("regression", "caption_scale", PASS if cap >= ref["caption_px_1080"] else WARN,
              f"captions {cap:.0f}px vs calibration {ref['caption_px_1080']}px", round(cap), f">= {ref['caption_px_1080']}px")
    sizes = [float(g.get("size_px") or fitted_hero_px(g["spec"])) for g in b.graphics if g["type"] == "hero" and g.get("variant") != "card"]
    sizes += [float(g["spec"].get("title_size", 104)) for g in b.graphics if g["type"] == "reveal"]
    if ref.get("title_px_1080") and sizes:
        r.add("regression", "title_scale", PASS if max(sizes) >= ref["title_px_1080"] else WARN,
              f"largest designed type {max(sizes):.0f}px vs calibration {ref['title_px_1080']}px", round(max(sizes)),
              f">= {ref['title_px_1080']}px")
    graphics_rate = len([g for g in b.graphics if g["type"] not in SMALL_TYPES]) / b.duration * 10 if b.duration else 0
    lo, hi = ref.get("graphics_per_10s_range", [None, None])
    if lo is not None:
        r.add("regression", "graphic_density", PASS if lo <= graphics_rate <= hi else WARN,
              f"{graphics_rate:.1f} designed graphics per 10s", round(graphics_rate, 2), f"{lo}-{hi}")


# --- report ------------------------------------------------------------------------
def to_markdown(result):
    lines = [f"# Reel review: {result.get('title') or 'untitled'}", ""]
    counts = result["result"]["counts"]
    lines.append(f"**{result['result']['status'].upper()}** · {counts['fail']} fail · {counts['warn']} warn · "
                 f"{counts['pass']} pass · {result['duration']:.1f}s" + (f" · render `{Path(result['video']).name}`" if result.get("video") else ""))
    lines.append("")
    order = {FAIL: 0, WARN: 1, PASS: 2}
    fixes = [c for c in result["checks"] if c["status"] != PASS]
    if fixes:
        lines += ["## Fix first", ""]
        for c in sorted(fixes, key=lambda c: (order[c["status"]], AREAS.index(c["area"]))):
            lines.append(f"- **{c['status']}** {AREA_TITLES[c['area']]}: {c['summary']}"
                         + (f" (limit {c['limit']})" if c.get("limit") is not None else ""))
            for d in (c.get("details") or [])[:4]:
                lines.append(f"  - {d}")
        lines.append("")
    lines += ["## All checks", "", "| Area | Check | Result | Measured | Limit |", "| --- | --- | --- | --- | --- |"]
    for c in sorted(result["checks"], key=lambda c: AREAS.index(c["area"])):
        value = c.get("value")
        value = ", ".join(map(str, value)) if isinstance(value, list) else "" if value is None else value
        lines.append(f"| {AREA_TITLES[c['area']]} | {c['check']} | {c['status']} | {value} | {c.get('limit', '')} |")
    render = result["metrics"].get("render")
    if render:
        strip = render["presenter_strip"]
        per = max(1, int(round(render["fps"] / 2)))
        compact = "".join(strip[i] for i in range(0, len(strip), per))
        lines += ["", f"## Presenter strip (one mark per {per / render['fps']:.2g} s)", "",
                  "`F` full size · `s` small or lowered · `.` not on screen", "", f"`{compact}`"]
    lines.append("")
    return "\n".join(lines)


def review(project=None, video=None, reference_path=REFERENCE_PATH, face_fps=5.0):
    if not project and not video:
        raise ValueError("review needs a build directory, a rendered video, or both")
    b = Build(project) if project else None
    r = Review(b)
    if b:
        for check in (check_hook, check_word_sync, check_captions, check_layout_zones, check_presenter,
                      check_progression, check_transitions, check_motion_craft, check_sound, check_forbidden,
                      check_pacing):
            check(b, r)
        reference = read_json(reference_path, {}) if reference_path else {}
        if reference:
            regression(b, r, reference)
    if video:
        spec = b.style if b else style.load()
        check_render(b, r, measure_render(video, spec, face_fps, b), spec)
    out = {"title": b.resolved.get("title") if b else None, "project": str(project) if project else None,
           "video": str(video) if video else None, "duration": b.duration if b else r.metrics["render"]["duration"],
           "style_version": (b.style if b else style.load()).get("version"), "result": r.result(),
           "checks": r.checks, "metrics": r.metrics}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="build directory (edit.py build --project)")
    ap.add_argument("--video", help="encoded render to measure")
    ap.add_argument("--measure", help="measure a video only (no build), e.g. a reference export")
    ap.add_argument("--reference", default=str(REFERENCE_PATH), help="calibration metrics JSON ('' to skip)")
    ap.add_argument("--out", help="write the review JSON here (default: <project>/review.json)")
    ap.add_argument("--markdown", help="write a Markdown summary here (default: next to the JSON)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any check fails")
    a = ap.parse_args()
    if a.measure:
        metrics = measure_render(Path(a.measure), style.load())
        text = json.dumps(metrics, indent=1)
        if a.out:
            Path(a.out).write_text(text + "\n")
        print(text)
        return
    if not a.project:
        ap.error("--project is required (or --measure VIDEO)")
    result = review(a.project, a.video, a.reference or None)
    out = Path(a.out) if a.out else Path(a.project) / "review.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    md = Path(a.markdown) if a.markdown else out.with_suffix(".md")
    md.write_text(to_markdown(result))
    print(json.dumps({"review": str(out), "summary": str(md), **result["result"]}))
    if a.strict and result["result"]["status"] == FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
