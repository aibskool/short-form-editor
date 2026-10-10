"""Viral Reels SFX Pack placement. The audio files are not in git.

The pack is royalty-free in a video and may not be redistributed as a library.
Point SFX_PACK_DIR at a local copy (default: production/editor/sfx/viral-pack).
Files are used as supplied. The only edits are a timeline trim, a short fade
where a long file is cut, and clip gain on anything that peaks above 0 dBFS.
No EQ, pitch shift, time-stretch, or filtering.
"""
import math
import os
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RATE = 48000

POP_3 = "27 Pops, Zaps & Switches/Pop 3.mp3"
POP_5 = "27 Pops, Zaps & Switches/Pop 5.mp3"
POP_1 = "27 Pops, Zaps & Switches/Pop 1.mp3"
FAST_WHIP = "03 Whooshes/Fast Whip.wav"
QUICK_SWING = "03 Whooshes/Quick Swing B.wav"
COOL_WHOOSH = "03 Whooshes/Cool Whoosh.wav"
EPIC_03 = "04 Swishes & Swooshes/Epic Swishes 03.wav"
EPIC_05 = "04 Swishes & Swooshes/Epic Swishes 05.wav"
EPIC_08 = "04 Swishes & Swooshes/Epic Swishes 08.wav"
SIMPLE_WHOOSH = "03 Whooshes/Simple Whoosh 1.wav"
SWOOSH_FAST = "04 Swishes & Swooshes/Swoosh Fast 1.mp3"
DEEP_WHOOSH = "05 Deep & Power Whooshes/Deep Whoosh 2.wav"
BACKWARDS = "04 Swishes & Swooshes/Backwards Swoosh.wav"
DEEP_HIT = "06 Hits & Punches/Deep Hit.wav"
IMPACT = "00 Viral Reels Essentials/Impact Cinematic Boom.mp3"
HIT_DULL = "06 Hits & Punches/Hit Dull.mp3"
BOOM_14 = "07 Booms/Boom 14.mp3"
REVERSE_14 = "02 Reverse FX/Cinematic Reverse 14.wav"
REVERSE_2 = "02 Reverse FX/Cinematic Reverse 2.wav"
RISER_14 = "11 Risers/Riser 14.wav"
RISER_12 = "11 Risers/Riser 12.wav"
EXPLOSION = "09 Explosions & Crashes/Explosion 3.mp3"
BELL_6 = "28 Dings, Bells & Chimes/Bell 6.wav"
BELL_5 = "28 Dings, Bells & Chimes/Bell 5.wav"
CORRECT = "30 Notifications & Alerts/Alert Positive Correct.mp3"
BUZZER = "18 Fails & Buzzers/Buzzer 2.mp3"
BUZZER_ALT = "18 Fails & Buzzers/Buzzer 1.mp3"
UI_30 = "24 UI Sounds/Ui 30.wav"
KA_CHING = "35 Money & Cash/Cash Register Ka Ching.mp3"
TYPING_3 = "26 Typing & Keyboard/Typing 3.mp3"
TYPING_4 = "26 Typing & Keyboard/Typing 4.mp3"
CLICK_10 = "25 Mouse Clicks/Mouse Click 10.mp3"
CLICK_8 = "25 Mouse Clicks/Mouse Click 8.mp3"

# Editor kinds keep their animation meaning. These are the takes the HTML
# preview and the stem test rotate when a cue does not name a file.
KIND_FILES = {
    "pop": [POP_3, POP_5, POP_1],
    "whoosh": [FAST_WHIP, QUICK_SWING, EPIC_03],
    "click": [BELL_6, CLICK_10, CLICK_8],
    "typing": [TYPING_3, TYPING_4],
    "ticking": [UI_30, BELL_6],
    "ding": [CORRECT, BELL_5],
    "bass": [BOOM_14, DEEP_HIT, IMPACT],
    "riser": [RISER_14, RISER_12],
    "error": [BUZZER, BUZZER_ALT],
    "marker": [SWOOSH_FAST, SIMPLE_WHOOSH],
    "paper": [SWOOSH_FAST, SIMPLE_WHOOSH],
}

# Cool Whoosh is reserved for the loop close (combo 47), so a cut cannot be the third play.
WHOOSH_ROTATION = [
    FAST_WHIP, QUICK_SWING, EPIC_03, EPIC_05, EPIC_08,
    SIMPLE_WHOOSH, SWOOSH_FAST, DEEP_WHOOSH,
]
CALLOUT_ROTATION = [SWOOSH_FAST, SIMPLE_WHOOSH, EPIC_03]
PUNCH_SWOOSH = [BACKWARDS, REVERSE_2]
PUNCH_HIT = [DEEP_HIT, IMPACT]

# Midpoints of the mix cheat sheet, dB under the voice. No music in the reel.
UNDER_FROM_SHEET = {
    "pop": 16.0, "click": 16.0, "typing": 16.0, "ticking": 16.0,
    "marker": 14.0, "paper": 14.0,
    "error": 6.0, "whoosh": 10.0, "riser": 10.0, "ding": 12.0, "bass": 6.0,
}

_CACHE = {}
_DURATION = {}
_DROP = ("also", "bed", "fixed_file", "fixed_lead", "rotate", "trim_frames",
         "fade_frames", "fade_in_frames", "delay_frames", "delay_from", "priority")


def pack_dir():
    raw = os.environ.get("SFX_PACK_DIR")
    if raw:
        return Path(raw)
    return HERE / "sfx" / "viral-pack"


def pack_ready():
    return (pack_dir() / FAST_WHIP).is_file()


def resolve(file):
    path = Path(file)
    if path.is_file():
        return path
    return pack_dir() / str(file)


def kind_paths(kind):
    found = []
    for rel in KIND_FILES.get(kind, []):
        path = resolve(rel)
        if path.is_file():
            found.append(path)
    return found


def _decode(path):
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", str(RATE), "-f", "f32le", "pipe:1"],
        check=True, capture_output=True).stdout
    if len(raw) < 4:
        raise RuntimeError(f"could not decode {path}")
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def load(path):
    """Decode once. Clip-gain only when the file peaks above 0 dBFS.

    Quiet files are not turned up. Backwards Swoosh is the loud one (about
    +12 dBFS in this copy; the pack note says +13.4).
    """
    path = str(path)
    if path not in _CACHE:
        samples = _decode(path)
        peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
        clip_db = 0.0
        if peak > 1.0:
            samples = samples * (1.0 / peak)
            clip_db = -20.0 * math.log10(peak)
            peak = 1.0
        _CACHE[path] = (samples, {"clip_gain_db": round(clip_db, 2), "peak_db": round(20.0 * math.log10(max(peak, 1e-8)), 2)})
    samples, info = _CACHE[path]
    return samples.copy(), dict(info)


def file_duration(file):
    key = str(file)
    if key not in _DURATION:
        path = resolve(file)
        if not path.is_file():
            _DURATION[key] = 0.4
        else:
            samples, _info = load(path)
            _DURATION[key] = len(samples) / float(RATE)
    return _DURATION[key]


def _fade(samples, fade_in, fade_out):
    if len(samples) == 0:
        return samples
    if fade_in and fade_in > 0:
        count = min(len(samples), max(1, int(round(fade_in * RATE))))
        samples[:count] *= np.linspace(0.0, 1.0, count)
    if fade_out and fade_out > 0:
        count = min(len(samples), max(1, int(round(fade_out * RATE))))
        samples[-count:] *= np.linspace(1.0, 0.0, count)
    return samples


def render(cue):
    """Trim, fade, and loop. Returns samples, the mix start, and clip-gain info."""
    samples, info = load(resolve(cue["file"]))
    fade_in = float(cue.get("fade_in") or 0.0)
    fade_out = float(cue.get("fade_out") or 0.0)
    if cue.get("align") == "end":
        keep = cue.get("trim")
        if keep:
            count = max(1, int(round(float(keep) * RATE)))
            if len(samples) > count:
                samples = samples[-count:]
                if fade_in <= 0:
                    fade_in = 0.04
    else:
        start = int(round(float(cue.get("trim_from") or 0.0) * RATE))
        if start > 0:
            samples = samples[min(start, max(0, len(samples) - 1)):]
        if cue.get("trim"):
            count = max(1, int(round(float(cue["trim"]) * RATE)))
            if len(samples) > count:
                samples = samples[:count]
                if fade_out <= 0:
                    fade_out = 0.04
    if cue.get("loop"):
        need = max(1, int(round(float(cue["loop"]) * RATE)))
        if len(samples) == 0:
            samples = np.zeros(need)
        elif len(samples) < need:
            reps = int(math.ceil(need / len(samples)))
            samples = np.tile(samples, reps)[:need]
        else:
            samples = samples[:need]
            if fade_out <= 0:
                fade_out = 0.06
    samples = _fade(samples, fade_in, fade_out)
    if cue.get("align") == "end":
        end = float(cue.get("sound_at", cue["at"]))
        placed = end - (len(samples) / float(RATE))
    elif cue.get("sound_at") is not None:
        placed = float(cue["sound_at"])
    else:
        placed = float(cue["at"])
    return samples, placed, info


def _land(at, end, delay):
    return round(min(float(at) + delay, float(end) - 0.04), 3)


def _money(stage):
    if stage.get("variant") == "receipt":
        return True
    blob = " ".join(str(stage.get(key) or "") for key in ("text", "label"))
    return "$" in blob or "£" in blob


def decorate_events(motif, events, stage, start, end):
    """Attach pack files without moving the animation time or the kind.

    ``at`` stays on the visual so the style check and the GSAP cues agree.
    ``sound_at`` is when the sample actually starts.
    """
    events = [dict(event) for event in events]
    stage = stage or {}
    if motif in {"phone_frame", "broll_card", "highlight_box", "line_chart", "flow_line", "cursor_mock", "logo_row"}:
        for event in events:
            if event["kind"] == "whoosh":
                event.setdefault("combo", "8")
                event.setdefault("label", "Standard Cut")
                event.setdefault("rotate", "whoosh")
    if motif in {"phone_frame", "broll_card", "hand_circle"}:
        draw = 0.45 if motif == "hand_circle" else float((stage.get("callout") or {}).get("draw") or 0.36)
        for event in events:
            if event["kind"] != "marker":
                continue
            event.update({
                "combo": "callout", "label": "Callout swish", "rotate": "callout",
                "under_db": 14.0, "band": "mid",
            })
            event["also"] = [{
                "kind": "pop", "at": event["at"], "sound_at": _land(event["at"], end, draw),
                "combo": "callout", "label": "Callout pop",
                "under_db": 16.0, "band": "high",
            }]
    if motif == "doc_fan":
        for index, event in enumerate(events):
            event.update({
                "file": SWOOSH_FAST, "combo": "paper", "label": "Page swish",
                "rotate": "callout", "under_db": 14.0, "band": "mid",
            })
            if index:
                event["mute"] = True
    if motif == "vacuum_merge":
        ding = next(event for event in events if event["kind"] == "ding")
        for event in events:
            if event["kind"] == "whoosh":
                event.update({
                    "file": REVERSE_14, "combo": "13", "label": "Reverse Lead-In",
                    "align": "end", "sound_at": ding["at"], "trim_frames": 21,
                    "fade_in_frames": 3, "fixed_file": True, "fixed_lead": True, "band": "mid",
                })
            elif event["kind"] == "ding":
                event.update({
                    "file": DEEP_HIT, "combo": "13", "label": "Reverse hit",
                    "fixed_file": True, "under_db": 6.0, "trim_frames": 12,
                    "fade_frames": 3, "band": "low",
                })
            elif event["kind"] == "pop":
                event.setdefault("combo", "19")
                event.setdefault("label", "Word Pop")
    if motif == "counter":
        ticks = [event for event in events if event["kind"] == "ticking"]
        for event in ticks:
            event["mute"] = True
            event["combo"] = "25"
            event["label"] = "Counter tick"
        for event in events:
            if event["kind"] != "ding":
                continue
            event.update({
                "file": BELL_5, "combo": "25", "label": "Number Counter",
                "fixed_file": True, "under_db": 12.0, "trim_frames": 14, "fade_frames": 3,
                "band": "high",
            })
            event["bed"] = {
                "kind": "ticking", "at": ticks[0]["at"] if ticks else event["at"],
                "file": UI_30, "combo": "25", "label": "Number Counter bed",
                "under_db": 23.0, "loop": 0.9, "fixed_file": True, "band": "bed",
            }
    if motif == "bar_chart" and stage.get("reveal") == "slice":
        riser = next(event for event in events if event["kind"] == "riser")
        riser.update({
            "file": RISER_14, "combo": "36", "label": "Full Reveal",
            "trim_frames": 24, "fade_frames": 2, "fixed_file": True, "fixed_lead": True,
            "band": "mid",
        })
        ding = next(event for event in events if event["kind"] == "ding")
        ding.update({
            "file": EXPLOSION, "combo": "36", "label": "Full Reveal hit",
            "delay_frames": 28, "delay_from": riser["at"], "fixed_file": True,
            "fixed_lead": True, "under_db": 6.0, "trim_frames": 18, "fade_frames": 3,
            "band": "low",
        })
    elif motif == "bar_chart":
        for event in events:
            if event["kind"] == "pop":
                event.setdefault("combo", "19")
                event.setdefault("label", "Word Pop")
                event["sound_at"] = _land(event["at"], end, 0.22)
            elif event["kind"] == "error":
                event.update({
                    "file": BUZZER, "combo": "24", "label": "Wrong Answer",
                    "fixed_file": True, "under_db": 6.0, "trim_frames": 8, "fade_frames": 3,
                    "band": "noise",
                })
    if motif == "quote_card":
        card = events[0]
        if _money(stage):
            card.update({
                "file": KA_CHING, "combo": "42", "label": "Money Shot",
                "fixed_file": True, "under_db": 6.0, "sound_at": _land(card["at"], end, 0.26),
                "band": "high",
            })
        else:
            card.update({
                "file": POP_1, "combo": "20", "label": "Caption Slam",
                "fixed_file": True, "under_db": 16.0, "sound_at": _land(card["at"], end, 0.24),
                "band": "high",
            })
            # Hit Dull at 40% is about 8 dB under a full impact (impact sits at -6).
            card["also"] = [{
                "kind": "pop", "at": card["at"], "sound_at": card["sound_at"],
                "file": HIT_DULL, "combo": "20", "label": "Caption Slam hit",
                "fixed_file": True, "under_db": 14.0, "band": "low",
            }]
        for event in events:
            if event["kind"] == "ticking":
                event.update({
                    "file": BELL_6, "combo": "22", "label": "List Tick",
                    "fixed_file": True, "under_db": 16.0, "trim_frames": 3, "fade_frames": 2,
                    "sound_at": event["at"], "band": "high",
                })
            elif event["kind"] == "error":
                event.update({
                    "file": BUZZER, "combo": "24", "label": "Wrong Answer",
                    "fixed_file": True, "under_db": 6.0, "trim_frames": 8, "fade_frames": 3,
                    "band": "noise",
                })
    if motif == "numbered_list":
        for event in events:
            event.update({
                "file": BELL_6, "combo": "22", "label": "List Tick",
                "fixed_file": True, "under_db": 16.0, "trim_frames": 8, "fade_frames": 3,
                "band": "high",
            })
    if motif == "offer_pair":
        for event in events:
            event.update({
                "combo": "19", "label": "Word Pop", "band": "high",
                "sound_at": _land(event["at"], end, 0.26),
            })
    if motif == "state_swap":
        for event in events:
            if event["kind"] == "pop":
                event.update({"combo": "19", "label": "Word Pop", "sound_at": _land(event["at"], end, 0.26)})
            elif event["kind"] == "error":
                event.update({
                    "file": BUZZER, "combo": "24", "label": "Wrong Answer",
                    "fixed_file": True, "under_db": 6.0, "trim_frames": 8, "fade_frames": 3,
                    "band": "noise",
                })
            elif event["kind"] == "ding":
                event.update({
                    "file": CORRECT, "combo": "23", "label": "Checkmark",
                    "fixed_file": True, "under_db": 12.0, "band": "high",
                })
    if motif == "typing_ui" or any(event["kind"] == "typing" for event in events):
        typing = [event for event in events if event["kind"] == "typing"]
        if typing:
            span = max(0.2, typing[-1]["at"] - typing[0]["at"] + 0.12)
            typing[0].update({
                "file": TYPING_3, "combo": "21", "label": "Typewriter Line",
                "fixed_file": True, "trim": round(span, 3), "fade_frames": 3, "band": "mid",
            })
            for extra in typing[1:]:
                extra["mute"] = True
                extra["combo"] = "21"
    if motif == "cursor_mock":
        for event in events:
            if event["kind"] == "click":
                event.update({
                    "file": CLICK_10, "combo": "click", "label": "Mouse click",
                    "fixed_file": True, "under_db": 16.0, "band": "high",
                })
    if motif in {"thumbnail_grid", "mind_map", "logo_row", "pill"}:
        for event in events:
            if event["kind"] == "pop":
                event.setdefault("combo", "19")
                event.setdefault("label", "Word Pop")
                event.setdefault("sound_at", _land(event["at"], end, 0.26))
    defaults = {
        "pop": (None, "19", "Word Pop"),
        "whoosh": (None, "8", "Standard Cut"),
        "click": (BELL_6, "22", "List Tick"),
        "typing": (TYPING_3, "21", "Typewriter Line"),
        "ticking": (None, "25", "Counter tick"),
        "ding": (BELL_5, "bell", "Bell"),
        "bass": (None, "2", "Cold Slam"),
        "riser": (RISER_12, "1", "Hard Open"),
        "error": (BUZZER, "24", "Wrong Answer"),
        "marker": (None, "callout", "Callout swish"),
        "paper": (None, "paper", "Page swish"),
    }
    for event in events:
        file, combo, label = defaults.get(event["kind"], (None, "", event["kind"]))
        event.setdefault("combo", combo)
        event.setdefault("label", label)
        if file and not event.get("file"):
            event["file"] = file
        if event["kind"] in {"whoosh", "riser"} and not event.get("rotate") and not event.get("fixed_file"):
            event["rotate"] = "whoosh"
        event.setdefault("band", _band(event))
    return events


def _band(cue):
    if cue.get("band"):
        return cue["band"]
    if float(cue.get("under_db") or 0) >= 20:
        return "bed"
    kind = cue.get("kind")
    path = str(cue.get("file") or "").lower()
    if kind == "bass" or any(token in path for token in ("boom", "deep hit", "sub drop", "impact")):
        return "low"
    if kind in {"whoosh", "riser", "marker", "paper", "typing"} or "whoosh" in path or "swoosh" in path or "reverse" in path:
        return "mid"
    if kind == "error":
        return "noise"
    return "high"


def _priority(cue):
    combo = str(cue.get("combo") or "")
    if combo in {"2", "8", "13", "15", "20", "23", "24", "36", "42", "47"}:
        return 3
    if cue.get("kind") in {"whoosh", "riser", "bass", "error", "ding"}:
        return 3
    if combo in {"19", "22", "callout", "paper"}:
        return 2
    return 1


def resolve_frames(cue, fps):
    fps = float(fps or 30)
    if cue.get("trim_frames") is not None:
        cue["trim"] = round(float(cue["trim_frames"]) / fps, 3)
    if cue.get("fade_frames") is not None:
        cue["fade_out"] = round(float(cue["fade_frames"]) / fps, 3)
    if cue.get("fade_in_frames") is not None:
        cue["fade_in"] = round(float(cue["fade_in_frames"]) / fps, 3)
    if cue.get("delay_frames") is not None:
        anchor = float(cue.get("delay_from", cue["at"]))
        cue["sound_at"] = round(anchor + float(cue["delay_frames"]) / fps, 3)
        cue["fixed_lead"] = True
    return cue


def _occupy(cue):
    if cue.get("trim"):
        return float(cue["trim"])
    if cue.get("loop"):
        return float(cue["loop"])
    kind = cue.get("kind")
    if kind in {"bass", "error"}:
        return 0.45
    if kind in {"pop", "click", "ding", "marker"}:
        return 0.2
    return 0.5


def _claim(cue, candidates, uses, last):
    group = cue.get("rotate")
    if cue.get("fixed_file") and cue.get("file"):
        uses[cue["file"]] = uses.get(cue["file"], 0) + 1
        if group:
            last[group] = cue["file"]
        return
    preferred = []
    if cue.get("file"):
        preferred.append(cue["file"])
    ordered = preferred + [item for item in candidates if item not in preferred]
    for rel in ordered:
        if uses.get(rel, 0) >= 2:
            continue
        if group and rel == last.get(group):
            continue
        cue["file"] = rel
        uses[rel] = uses.get(rel, 0) + 1
        last[group or ""] = rel
        return
    cue["mute"] = True


def finish_sfx(cues, fps, unders, under_db):
    """Expand companions, rotate whooshes, and keep at most three layers."""
    flat = []
    for cue in cues:
        companions = list(cue.get("also") or [])
        bed = cue.get("bed")
        item = {key: value for key, value in cue.items() if key not in {"also", "bed"}}
        flat.append(item)
        for extra in companions:
            extra = dict(extra)
            extra.setdefault("at", item["at"])
            flat.append(extra)
        if bed:
            bed = dict(bed)
            bed.setdefault("at", item["at"])
            flat.append(bed)
    for cue in flat:
        resolve_frames(cue, fps)
        kind = cue.get("kind")
        if cue.get("under_db") is None:
            cue["under_db"] = float((unders or {}).get(kind, under_db.get(kind, 16.0)))
        cue["band"] = _band(cue)
        cue["priority"] = _priority(cue)
    lead = 4.0 / float(fps or 30)
    for cue in flat:
        if cue.get("mute") or cue.get("fixed_lead") or cue.get("align") == "end":
            continue
        if cue.get("kind") in {"whoosh", "riser"} or cue.get("rotate") == "whoosh":
            base = float(cue.get("sound_at", cue["at"]))
            cue["sound_at"] = round(max(0.0, base - lead), 3)
    uses = {}
    last = {}
    groups = {"whoosh": WHOOSH_ROTATION, "callout": CALLOUT_ROTATION, "punch": PUNCH_SWOOSH, "hit": PUNCH_HIT}
    timed = sorted(range(len(flat)), key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])))
    for index in timed:
        cue = flat[index]
        if cue.get("mute"):
            continue
        group = cue.get("rotate")
        if group in groups:
            _claim(cue, groups[group], uses, last)
        elif cue.get("file"):
            uses[cue["file"]] = uses.get(cue["file"], 0) + 1
    active = []
    order = sorted(range(len(flat)), key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])))
    for index in order:
        cue = flat[index]
        if cue.get("mute"):
            continue
        if cue.get("band") == "bed" or float(cue.get("under_db") or 0) >= 20:
            continue
        start = float(cue.get("sound_at", cue["at"]))
        if cue.get("align") == "end":
            start = start - _occupy(cue)
        active = [item for item in active if item[0] > start + 0.02]
        band = cue["band"]
        same = [item for item in active if item[1] == band]
        high_cap = 2 if band == "high" else 1
        total_cap = len(active) >= 3
        band_cap = len(same) >= high_cap
        if band_cap or total_cap:
            if cue["priority"] >= 3:
                decorative = [item for item in active if item[2] < 3 and (item[1] == band or total_cap)]
                if decorative and (band_cap or total_cap):
                    drop = min(decorative, key=lambda item: item[2])
                    flat[drop[3]]["mute"] = True
                    active = [item for item in active if item[3] != drop[3]]
                elif band_cap:
                    cue["mute"] = True
                    continue
            else:
                cue["mute"] = True
                continue
        active.append((start + _occupy(cue), band, cue["priority"], index))
    pop_turn = 0
    heard = sorted(
        (index for index, cue in enumerate(flat)
         if not cue.get("mute") and cue.get("kind") == "pop" and str(cue.get("combo")) in {"19", "callout"}),
        key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])),
    )
    for index in heard:
        flat[index]["file"] = POP_3 if pop_turn % 2 == 0 else POP_5
        pop_turn += 1
    cleaned = []
    for cue in flat:
        item = {key: value for key, value in cue.items() if key not in _DROP and value is not None}
        if item.get("mute") is False:
            item.pop("mute", None)
        cleaned.append(item)
    cleaned.sort(key=lambda item: (float(item["at"]), item.get("kind", "")))
    return cleaned
