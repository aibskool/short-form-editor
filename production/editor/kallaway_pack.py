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
POP_4 = "27 Pops, Zaps & Switches/Pop 4.mp3"
POP_1 = "27 Pops, Zaps & Switches/Pop 1.mp3"
POP_CYCLE = [POP_3, POP_5, POP_4]
FAST_WHIP = "03 Whooshes/Fast Whip.wav"
QUICK_SWING = "03 Whooshes/Quick Swing B.wav"
COOL_WHOOSH = "03 Whooshes/Cool Whoosh.wav"
SWIPE = "03 Whooshes/Movement Swipe Whoosh 2.mp3"
SIMPLE_WHOOSH = "03 Whooshes/Simple Whoosh 1.wav"
EPIC_03 = "04 Swishes & Swooshes/Epic Swishes 03.wav"
SWOOSH_FAST = "04 Swishes & Swooshes/Swoosh Fast 1.mp3"
SWISH_2 = "04 Swishes & Swooshes/Swish 2.mp3"
SWOOSH_17 = "04 Swishes & Swooshes/Swoosh 17.mp3"
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
BELL_5 = "28 Dings, Bells & Chimes/Bell 5.wav"
BELL_6 = "28 Dings, Bells & Chimes/Bell 6.wav"
BELL_7 = "28 Dings, Bells & Chimes/Bell 7.wav"
LIST_BELLS = [BELL_5, BELL_6, BELL_7]
CORRECT = "30 Notifications & Alerts/Alert Positive Correct.mp3"
BUZZER = "18 Fails & Buzzers/Buzzer 2.mp3"
BUZZER_ALT = "18 Fails & Buzzers/Buzzer 1.mp3"
UI_30 = "24 UI Sounds/Ui 30.wav"
KA_CHING = "35 Money & Cash/Cash Register Ka Ching.mp3"
KA_CHING_02 = "35 Money & Cash/Cash Register Ka Ching 02.mp3"
MONEY_FILES = [KA_CHING, KA_CHING_02]
TYPING_3 = "26 Typing & Keyboard/Typing 3.mp3"
TYPING_4 = "26 Typing & Keyboard/Typing 4.mp3"
CLICK_10 = "25 Mouse Clicks/Mouse Click 10.mp3"
CLICK_8 = "25 Mouse Clicks/Mouse Click 8.mp3"

# Editor kinds keep their animation meaning. These are the takes the HTML
# preview and the stem test rotate when a cue does not name a file.
KIND_FILES = {
    "pop": [POP_3, POP_5, POP_4],
    "whoosh": [FAST_WHIP, QUICK_SWING, SWIPE],
    "click": [BELL_6, CLICK_10, CLICK_8],
    "typing": [TYPING_3, TYPING_4],
    "ticking": [UI_30, BELL_6],
    "ding": [CORRECT, BELL_5],
    "bass": [BOOM_14, DEEP_HIT, IMPACT],
    "riser": [RISER_14, RISER_12],
    "error": [BUZZER, BUZZER_ALT],
    "marker": [SWISH_2, SWOOSH_FAST],
    "paper": [SWOOSH_FAST, SIMPLE_WHOOSH],
}

# Cool Whoosh stays on the optional loop close. Whoosh Fast Short is not in this pack.
WHOOSH_ROTATION = [FAST_WHIP, QUICK_SWING, SWIPE, SIMPLE_WHOOSH]
UI_ROTATION = [SWIPE, SWISH_2, SWOOSH_17]
CALLOUT_ROTATION = [SWISH_2, SWOOSH_FAST, SIMPLE_WHOOSH]

# Playbook S5, dB under the voice, with no music. Pops and ticks sit mid-range
# of -10 to -16. Dings and the cash register sit mid-range of -8 to -12.
# Marker draws use the quiet end because the pack has no squeak.
UNDER_FROM_SHEET = {
    "pop": 13.0, "click": 13.0, "typing": 13.0, "ticking": 13.0,
    "marker": 18.0, "paper": 10.0,
    "error": 6.0, "whoosh": 10.0, "riser": 10.0, "ding": 10.0, "bass": 6.0,
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
                    fade_in = 0.005
    else:
        start = int(round(float(cue.get("trim_from") or 0.0) * RATE))
        if start > 0:
            samples = samples[min(start, max(0, len(samples) - 1)):]
        if cue.get("trim"):
            count = max(1, int(round(float(cue["trim"]) * RATE)))
            if len(samples) > count:
                samples = samples[:count]
                if fade_out <= 0:
                    fade_out = 0.1
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
    if motif in {"phone_frame", "broll_card", "highlight_box", "line_chart", "flow_line"}:
        for event in events:
            if event["kind"] == "whoosh":
                event.setdefault("combo", "8")
                event.setdefault("label", "Panel slide")
                event.setdefault("rotate", "whoosh")
    if motif in {"cursor_mock", "logo_row"}:
        for event in events:
            if event["kind"] == "whoosh":
                event.setdefault("combo", "8")
                event.setdefault("label", "UI swipe")
                event.setdefault("rotate", "ui")
    if motif in {"phone_frame", "broll_card"}:
        for event in events:
            if event["kind"] == "whoosh":
                event["label"] = "Graphic entrance"
    if motif in {"phone_frame", "broll_card", "hand_circle"}:
        draw = 0.45 if motif == "hand_circle" else float((stage.get("callout") or {}).get("draw") or 0.36)
        for event in events:
            if event["kind"] != "marker":
                continue
            # The pack has no marker squeak. A quiet swish covers the draw.
            event.update({
                "file": SWISH_2, "combo": "callout", "label": "Callout swish",
                "fixed_file": True, "under_db": 18.0, "band": "mid",
                "trim": round(draw, 3), "fade_frames": 3,
            })
    if motif == "doc_fan":
        for index, event in enumerate(events):
            if event["kind"] == "error":
                event.update({
                    "file": BUZZER, "combo": "24", "label": "Graphic entrance",
                    "fixed_file": True, "under_db": 8.0, "trim_frames": 8,
                    "fade_frames": 3, "band": "noise",
                })
                continue
            event.update({
                "file": SWOOSH_FAST, "combo": "paper", "label": "Page swish",
                "fixed_file": True, "under_db": 10.0, "band": "mid",
            })
            event["also"] = [{
                "kind": "pop", "at": event["at"], "combo": "19",
                "label": "Graphic entrance" if index == 0 else "Page pop",
                "sound_at": event["at"], "band": "high",
            }]
            if index:
                event["mute"] = True
    if motif == "vacuum_merge":
        ding = next(event for event in events if event["kind"] == "ding")
        for event in events:
            if event["kind"] == "whoosh":
                event.update({
                    "file": REVERSE_14, "combo": "13", "label": "Reverse Lead-In",
                    "align": "end", "sound_at": ding["at"], "trim_frames": 21,
                    "fade_in": 0.005, "fixed_file": True, "fixed_lead": True, "band": "mid",
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
        if ticks:
            ticks[0]["mute"] = False
            ticks[0]["kind"] = "pop"
            ticks[0]["combo"] = "19"
            ticks[0]["label"] = "Graphic entrance"
        for event in events:
            if event["kind"] != "ding":
                continue
            event.update({
                "file": BELL_5, "combo": "25", "label": "Number Counter",
                "fixed_file": True, "under_db": 10.0, "trim_frames": 14, "fade_frames": 3,
                "band": "high",
                # The pop already lands on the counter. The bell sits a second later
                # with nothing new on screen.
                "mute": True, "mute_reason": "no visual",
            })
            event["bed"] = {
                "kind": "ticking", "at": ticks[0]["at"] if ticks else event["at"],
                "file": UI_30, "combo": "25", "label": "Number Counter bed",
                "under_db": 23.0, "loop": 0.9, "fixed_file": True, "band": "bed",
                "mute": True, "mute_reason": "no visual",
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
        seen_pop = False
        for event in events:
            if event["kind"] == "pop":
                if not seen_pop:
                    event["combo"] = "20"
                    event["label"] = "Chart entrance"
                    event["sound_at"] = round(float(event["at"]), 3)
                    seen_pop = True
                else:
                    event.setdefault("combo", "19")
                    event.setdefault("label", "Word Pop")
                    event["sound_at"] = _land(event["at"], end, 0.08)
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
                "file": KA_CHING, "combo": "42", "label": "Money Shot", "kind": "pop",
                "fixed_file": True, "under_db": 10.0, "sound_at": round(float(card["at"]), 3),
                "band": "high",
            })
        else:
            # The whoosh leads the card by 4 frames. It is not delayed onto the hold.
            card.update({
                "combo": "8", "label": "Graphic entrance", "band": "mid",
                "rotate": "whoosh", "kind": "whoosh",
                "sound_at": round(max(0.0, float(card["at"]) - 4.0 / 30.0), 3),
                "fixed_lead": True,
            })
        for extra in events[1:]:
            if extra.get("kind") == "pop" and abs(float(extra.get("at", 0)) - float(card["at"])) < 0.05:
                extra["mute"] = True
                extra["mute_reason"] = "stacked"
        tick_n = 0
        for event in events:
            if event["kind"] == "ticking":
                event.update({
                    "file": LIST_BELLS[tick_n % len(LIST_BELLS)], "combo": "22", "label": "List Tick",
                    "fixed_file": True, "trim_frames": 8, "fade_frames": 3,
                    "sound_at": event["at"], "band": "high",
                })
                tick_n += 1
            elif event["kind"] == "error":
                event.update({
                    "file": BUZZER, "combo": "24", "label": "Wrong Answer",
                    "fixed_file": True, "under_db": 6.0, "trim_frames": 8, "fade_frames": 3,
                    "band": "noise",
                })
    if motif == "numbered_list":
        if stage.get("variant") == "cards":
            for event in events:
                event.update({
                    "kind": "pop", "combo": "19", "label": "Graphic entrance",
                    "sound_at": round(float(event["at"]), 3), "band": "high",
                })
                event.pop("file", None)
                event.pop("fixed_file", None)
        else:
            for index, event in enumerate(events):
                event.update({
                    "file": LIST_BELLS[index % len(LIST_BELLS)], "combo": "22", "label": "List Tick",
                    "fixed_file": True, "trim_frames": 8, "fade_frames": 3, "band": "high",
                })
            if events:
                events[0]["label"] = "Graphic entrance"
                events[0]["combo"] = "19"
    if motif == "offer_pair":
        items = [str(item) for item in (stage.get("items") or [])]
        money_n = 0
        for index, event in enumerate(events):
            label = items[index] if index < len(items) else ""
            if "$" in label or "£" in label:
                event.update({
                    "file": MONEY_FILES[money_n % len(MONEY_FILES)], "combo": "42",
                    "label": "Money Shot", "fixed_file": True, "under_db": 10.0,
                    "sound_at": round(float(event["at"]), 3), "band": "high",
                })
                money_n += 1
            else:
                event.update({
                    "combo": "19", "label": "Word Pop", "band": "high",
                    "sound_at": round(float(event["at"]), 3),
                })
        # The hook boom already hits this pair. A second money hit, and a hit
        # delayed off the cards, is what pushed the reel over 20 per minute.
        if events and float(events[0].get("at", 0)) < 0.5:
            events[0]["mute"] = True
            events[0]["mute_reason"] = "stacked"
        if len(events) > 1:
            events[1]["mute"] = True
            events[1]["mute_reason"] = "stacked"
    if motif == "state_swap":
        for event in events:
            if event["kind"] == "whoosh":
                event["label"] = "Graphic entrance"
                event["combo"] = "8"
            elif event["kind"] == "pop":
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
                    "fixed_file": True, "under_db": 10.0, "band": "high",
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
                    "fixed_file": True, "band": "high",
                })
    if motif in {"thumbnail_grid", "mind_map", "logo_row", "pill"}:
        for event in events:
            if event["kind"] == "pop":
                event.setdefault("combo", "19")
                event.setdefault("label", "Word Pop")
                event.setdefault("sound_at", _land(event["at"], end, 0.26))
    defaults = {
        "pop": (None, "19", "Word Pop"),
        "whoosh": (None, "8", "Panel slide"),
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


def _bump(streak, file):
    if streak[0] == file:
        streak[1] += 1
    else:
        streak[0] = file
        streak[1] = 1


def _claim(cue, candidates, last, streak):
    """Rotate a family so the same file never plays twice in a row.

    A file may return later. Three identical plays in a row are skipped.
    """
    group = cue.get("rotate")
    family = "move" if group in {"whoosh", "ui", "callout"} else (group or "")
    if cue.get("fixed_file") and cue.get("file"):
        if family:
            last[family] = cue["file"]
        _bump(streak, cue["file"])
        return
    preferred = [cue["file"]] if cue.get("file") else []
    ordered = preferred + [item for item in candidates if item not in preferred]
    for rel in ordered:
        if family and rel == last.get(family):
            continue
        if streak[0] == rel and streak[1] >= 2:
            continue
        cue["file"] = rel
        if family:
            last[family] = rel
        _bump(streak, rel)
        return
    cue["mute"] = True


def _is_boom(cue):
    if cue.get("mute"):
        return False
    if cue.get("kind") == "bass":
        return True
    path = str(cue.get("file") or "").lower()
    return any(token in path for token in ("boom", "deep hit", "impact cinematic", "explosion", "sub drop"))


def _collapse_repeats(flat, window=0.45):
    """One sound per gesture. A stagger of the same combo inside ``window`` keeps the first."""
    last = {}
    order = sorted(
        (index for index, cue in enumerate(flat) if not cue.get("mute") and float(cue.get("under_db") or 0) < 20),
        key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])),
    )
    for index in order:
        cue = flat[index]
        key = str(cue.get("label") or cue.get("combo") or cue.get("kind"))
        moment = float(cue.get("sound_at", cue["at"]))
        if key in last and moment - last[key] < window:
            cue["mute"] = True
            continue
        last[key] = moment


def _density_rank(cue):
    combo = str(cue.get("combo") or "")
    if combo == "2":
        return 0
    if combo == "42":
        return 1
    if cue.get("label") in {"Chapter header", "Chart entrance", "Graphic entrance"}:
        return 2
    # The terminal's typing line is the sound for that card. It stays ahead of
    # a strike buzzer and a highlight pop when the reel is on the density line.
    if cue.get("label") == "Typewriter Line" or combo == "21":
        return 3
    if combo == "8" or cue.get("label") == "Number Counter":
        return 3
    if combo in {"23", "25", "36"}:
        return 4
    if combo == "24":
        return 5
    if combo == "22":
        return 6
    if combo in {"19", "20"}:
        return 7
    if combo == "47":
        return 9
    return 8


def _mute_whoosh_beside_card(flat):
    """A chapter whoosh within half a second of a card pop is the same entrance."""
    pops = [
        float(cue.get("at", 0))
        for cue in flat
        if not cue.get("mute") and cue.get("label") == "Graphic entrance" and cue.get("kind") == "pop"
    ]
    for cue in flat:
        if cue.get("mute") or cue.get("label") != "Chapter header":
            continue
        visual = float(cue.get("at", 0))
        if any(abs(visual - at) < 0.45 for at in pops):
            cue["mute"] = True
            cue["mute_reason"] = "stacked"


def _restore_isolated_entrances(flat, extra=5, gap=0.75, budget=None):
    """Put a sound back on an entrance the density cap silenced.

    Only a cue at least ``gap`` seconds from anything still playing is restored,
    and only a few of them, so stacked pops stay muted. Restores stop at the
    per-minute budget.
    """
    labels = {"Graphic entrance", "Chart entrance", "Chapter header"}
    audible = [
        index for index, cue in enumerate(flat)
        if not cue.get("mute") and float(cue.get("under_db") or 0) < 20
    ]
    muted = [
        index for index, cue in enumerate(flat)
        if cue.get("mute") and cue.get("label") in labels and float(cue.get("under_db") or 0) < 20
    ]
    restored = 0
    for index in sorted(muted, key=lambda item: float(flat[item].get("sound_at", flat[item]["at"]))):
        if restored >= extra or (budget is not None and len(audible) >= budget):
            break
        moment = float(flat[index].get("sound_at", flat[index]["at"]))
        if any(abs(float(flat[other].get("sound_at", flat[other]["at"])) - moment) < gap for other in audible):
            continue
        flat[index]["mute"] = False
        audible.append(index)
        restored += 1


def _mute_stacked_openings(flat):
    """One hit on the opening frame. A whoosh stacked on the boom does not play."""
    bass_at = [
        float(cue.get("sound_at", cue["at"]))
        for cue in flat
        if not cue.get("mute") and cue.get("kind") == "bass"
    ]
    for cue in flat:
        if cue.get("mute") or cue.get("kind") not in {"whoosh", "riser"}:
            continue
        moment = float(cue.get("sound_at", cue["at"]))
        if any(abs(moment - at) < 0.08 for at in bass_at):
            cue["mute"] = True
            cue["mute_reason"] = "stacked"


def _thin_close_whooshes(flat, budget, gap=2.5):
    """Drop a second whoosh that follows another by under ``gap`` when the reel is over budget."""
    def playing():
        return [
            index for index, cue in enumerate(flat)
            if not cue.get("mute") and float(cue.get("under_db") or 0) < 20
        ]

    guard = 0
    while len(playing()) > budget and guard < 6:
        guard += 1
        whooshes = sorted(
            (index for index in playing() if flat[index].get("kind") in {"whoosh", "riser"}),
            key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])),
        )
        dropped = False
        previous = None
        for index in whooshes:
            moment = float(flat[index].get("sound_at", flat[index]["at"]))
            if previous is not None and moment - previous < gap:
                flat[index]["mute"] = True
                flat[index]["mute_reason"] = "density"
                dropped = True
                break
            previous = moment
        if not dropped:
            break


def _limit_density(flat):
    """Stay at or under 20 SFX per minute. Beds under 20 dB do not spend the budget.

    The cap drops stacked pops, extra buzzers, and the optional loop close
    before it drops a money hit, a panel whoosh, or the hook boom.
    """
    _collapse_repeats(flat)
    _mute_stacked_openings(flat)
    _mute_whoosh_beside_card(flat)
    if not flat:
        return
    duration = max(float(cue["at"]) for cue in flat)
    budget = max(4, int(20.0 * duration / 60.0))
    _thin_close_whooshes(flat, budget)
    audible = [
        index for index, cue in enumerate(flat)
        if not cue.get("mute") and float(cue.get("under_db") or 0) < 20
    ]
    if len(audible) <= budget:
        return
    caps = {"2": 1, "42": 2, "8": 4, "chapter": 1, "graphic": 6, "23": 1, "25": 1, "24": 1, "22": 1, "19": 1, "20": 1, "47": 0, "callout": 0}
    ranked = sorted(audible, key=lambda index: (
        _density_rank(flat[index]),
        float(flat[index].get("sound_at", flat[index]["at"])),
    ))
    # Keep the buzzer that pairs with the check, not the earliest one.
    correct_at = next(
        (float(flat[index].get("sound_at", flat[index]["at"]))
         for index in audible if str(flat[index].get("combo")) == "23"),
        None,
    )
    if correct_at is not None:
        buzzers = [index for index in ranked if str(flat[index].get("combo")) == "24"]
        if buzzers:
            nearest = min(buzzers, key=lambda index: abs(float(flat[index].get("sound_at", flat[index]["at"])) - correct_at))
            rest = [index for index in ranked if index != nearest]
            # Keep this buzzer ahead of the other buzzers. It must not jump the boom or the money hits.
            slot = next(
                (i for i, index in enumerate(rest)
                 if _density_rank(flat[index]) > _density_rank(flat[nearest])),
                len(rest))
            rest.insert(slot, nearest)
            ranked = rest
    kept = []
    used = {}
    for index in ranked:
        if len(kept) >= budget:
            break
        cue = flat[index]
        if cue.get("label") == "Chapter header":
            slot = "chapter"
        elif cue.get("label") == "Graphic entrance":
            slot = "graphic"
        else:
            slot = str(cue.get("combo") or "")
        cap = caps.get(slot)
        if cap is not None and used.get(slot, 0) >= cap:
            continue
        kept.append(index)
        used[slot] = used.get(slot, 0) + 1
    keep_ids = set(kept)
    for index in audible:
        if index not in keep_ids:
            flat[index]["mute"] = True
    _restore_isolated_entrances(flat, budget=budget)
    beds = [
        index for index, cue in enumerate(flat)
        if not cue.get("mute") and float(cue.get("under_db") or 0) >= 20
    ]
    playing = [
        index for index, cue in enumerate(flat) if not cue.get("mute")
    ]
    if len(playing) > budget:
        for index in beds:
            if len(playing) <= budget:
                break
            flat[index]["mute"] = True
            playing.remove(index)
    _separate_whooshes(flat)
    _separate_fixed(flat, "42", MONEY_FILES)


def _separate_fixed(flat, combo, rotation):
    previous = None
    cursor = 0
    order = sorted(
        (index for index, cue in enumerate(flat)
         if not cue.get("mute") and str(cue.get("combo")) == combo),
        key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])),
    )
    for index in order:
        chosen = rotation[cursor % len(rotation)]
        if chosen == previous:
            cursor += 1
            chosen = rotation[cursor % len(rotation)]
        flat[index]["file"] = chosen
        previous = chosen
        cursor += 1


def _separate_whooshes(flat):
    """Heard whooshes alternate files even after the density pass drops one."""
    previous = None
    cursor = 0
    order = sorted(
        (index for index, cue in enumerate(flat)
         if not cue.get("mute") and cue.get("kind") == "whoosh" and str(cue.get("combo")) != "47"),
        key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])),
    )
    for index in order:
        chosen = WHOOSH_ROTATION[cursor % len(WHOOSH_ROTATION)]
        if chosen == previous:
            cursor += 1
            chosen = WHOOSH_ROTATION[cursor % len(WHOOSH_ROTATION)]
        flat[index]["file"] = chosen
        previous = chosen
        cursor += 1


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
            extra.setdefault("lands_on", item.get("lands_on"))
            flat.append(extra)
        if bed:
            bed = dict(bed)
            bed.setdefault("at", item["at"])
            bed.setdefault("lands_on", item.get("lands_on"))
            flat.append(bed)
    for cue in flat:
        resolve_frames(cue, fps)
        kind = cue.get("kind")
        if cue.get("under_db") is None:
            cue["under_db"] = float((unders or {}).get(kind, under_db.get(kind, 13.0)))
        cue["band"] = _band(cue)
        cue["priority"] = _priority(cue)
    lead = 4.0 / float(fps or 30)
    for cue in flat:
        if cue.get("mute") or cue.get("fixed_lead") or cue.get("align") == "end":
            continue
        if cue.get("kind") in {"whoosh", "riser"} or cue.get("rotate") == "whoosh":
            base = float(cue.get("sound_at", cue["at"]))
            cue["sound_at"] = round(max(0.0, base - lead), 3)
    last = {}
    streak = ["", 0]
    groups = {"whoosh": WHOOSH_ROTATION, "ui": UI_ROTATION, "callout": CALLOUT_ROTATION}
    timed = sorted(range(len(flat)), key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])))
    for index in timed:
        cue = flat[index]
        if cue.get("mute"):
            continue
        group = cue.get("rotate")
        if group in groups:
            _claim(cue, groups[group], last, streak)
        elif cue.get("file"):
            _bump(streak, cue["file"])
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
    booms = [index for index, cue in enumerate(flat) if _is_boom(cue)]
    if len(booms) > 3:
        ranked = sorted(booms, key=lambda index: (
            -int(flat[index].get("priority") or 0),
            float(flat[index].get("sound_at", flat[index]["at"])),
        ))
        for index in ranked[3:]:
            flat[index]["mute"] = True
    _limit_density(flat)
    pop_turn = 0
    heard = sorted(
        (index for index, cue in enumerate(flat)
         if not cue.get("mute") and cue.get("kind") == "pop"
         and str(cue.get("combo")) in {"19", "20", "callout"}),
        key=lambda index: float(flat[index].get("sound_at", flat[index]["at"])),
    )
    for index in heard:
        flat[index]["file"] = POP_CYCLE[pop_turn % len(POP_CYCLE)]
        pop_turn += 1
    for cue in flat:
        if cue.get("mute") or cue.get("file"):
            continue
        options = KIND_FILES.get(cue.get("kind")) or [POP_3]
        cue["file"] = options[0]
    cleaned = []
    for cue in flat:
        item = {key: value for key, value in cue.items() if key not in _DROP and value is not None}
        if item.get("mute") is False:
            item.pop("mute", None)
        cleaned.append(item)
    cleaned.sort(key=lambda item: (float(item["at"]), item.get("kind", "")))
    return cleaned
