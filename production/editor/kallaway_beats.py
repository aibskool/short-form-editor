"""Authored beat timelines for a Kallaway edit.

A stage plan with `beats` replaces the automatic split rotation. Each beat names
the words it starts on, a camera layout, and an optional motif. The planner cuts
on those words, splits a beat that would run past 5.4 seconds, and turns the
overflow into a full-screen or punch-in so the same motif is not used twice in
a row. The closing shot is whatever the last beat says. It is not forced to the
lead-magnet fan, so a Comment header can sit mid-reel.
"""
import re

from kallaway_motifs import resolve_annotations
from kallaway_plan import (
    NEGATIVE, _cover_sfx, _slot_words, _spoken, _token, caption_phrases, plain_text,
)


MAX_SHOT = 5.4
MIN_SHOT = 0.5
STAGE_KEYS = (
    "media", "items", "count", "value", "label", "text", "heights", "negative",
    "pages", "hold", "active", "prefix", "suffix", "scroll", "desaturate",
    "chip", "reveal", "labels", "kicker", "disclaimer", "progress",
    "media_start", "playback_rate", "target_still", "target_time", "poster_time", "typing",
)

# Full-screen sits 13% tighter than a wide split. Each punch stacks another 12%.
FULL_SCALE = 1.13
PUNCH_STEP = 1.12
CONTRAST_WORDS = {"but", "so", "now", "most", "never", "stop", "you"}


def _is_emphasis(word, styles):
    token = _token(word)
    if not token:
        return False
    style = styles.get(token)
    if style not in (None, "", "normal"):
        return True
    if any(char.isdigit() for char in token):
        return True
    return token in CONTRAST_WORDS and style != "normal"


def apply_emphasis_punches(shots, words, styles, full_scale=FULL_SCALE, step=PUNCH_STEP):
    """Hard punch-ins on emphasis words inside a full-screen stretch. Silent cuts.

    The first piece stays full-screen at ``full_scale``. Later pieces jump 12%
    tighter, up to three steps, then punch back out to the full-screen scale.
    """
    built = []
    for shot in shots:
        start, end = float(shot["start"]), float(shot["end"])
        if shot.get("layout") == "punch_in" and "scale" not in shot:
            shot = dict(shot)
            shot["scale"] = round(float(full_scale) * float(step), 3)
            built.append(shot)
            continue
        if shot.get("layout") != "full":
            built.append(shot)
            continue
        cuts = [start]
        if end - start >= 1.55:
            picked = []
            for word in words:
                at = float(word["start"])
                if start + 0.55 <= at <= end - 0.55 and _is_emphasis(word, styles):
                    if not picked or at - picked[-1] >= 1.5:
                        picked.append(at)
            for at in picked:
                if at - cuts[-1] >= 0.5 and end - at >= 0.5:
                    cuts.append(at)
        cuts.append(end)
        level = 0
        for index, (left, right) in enumerate(zip(cuts, cuts[1:])):
            piece = {key: value for key, value in shot.items() if key != "stage"}
            piece["start"] = round(left, 3)
            piece["end"] = round(right, 3)
            if index == 0 or level >= 3:
                piece["layout"] = "full"
                piece["scale"] = round(float(full_scale), 3)
                level = 0
            else:
                level += 1
                piece["layout"] = "punch_in"
                piece["scale"] = round(float(full_scale) * (float(step) ** level), 3)
            built.append(piece)
    for index, shot in enumerate(built):
        shot["id"] = f"shot-{index:02d}"
    return built


def _phone_screen(theme, width, height):
    layout = theme["layout"]
    pad = 8 * (width / 1080)
    return (layout["stage_width"] * width - 2 * pad, layout["stage_height"] * height - 2 * pad)


def _tokens(text):
    return re.findall(r"[a-z0-9']+", str(text).lower())


def locate(words, phrase, start_index=0):
    """Index of `phrase` in `words`, searching forward from `start_index`."""
    needle = _tokens(phrase)
    if not needle:
        raise ValueError("a beat phrase is empty")
    hay = [_token(word) for word in words]
    last = len(hay) - len(needle) + 1
    for index in range(max(0, start_index), last):
        if hay[index:index + len(needle)] == needle:
            return index
    raise ValueError(f"phrase not in the transcript from word {start_index}: {phrase!r}")


def _moment(words, spec, default, start_index):
    if isinstance(spec, dict) and spec.get("spoken"):
        return float(words[locate(words, spec["spoken"], start_index)]["start"])
    if isinstance(spec, dict) and spec.get("at") is not None:
        return float(spec["at"])
    return float(default)


def _cut_points(start, end, words):
    points = [round(float(start), 3)]
    cursor = float(start)
    end = float(end)
    while end - cursor > MAX_SHOT:
        low = cursor + 1.25
        high = min(cursor + 4.9, end - MIN_SHOT)
        target = min(cursor + 3.3, high)
        candidates = [float(word["start"]) for word in words if low <= float(word["start"]) <= high]
        if not candidates:
            break
        nxt = min(candidates, key=lambda point: (abs(point - target), point))
        if nxt <= cursor + 0.45:
            break
        points.append(round(nxt, 3))
        cursor = nxt
    points.append(round(end, 3))
    if len(points) >= 3 and points[-1] - points[-2] < MIN_SHOT:
        points.pop(-2)
    return points


def _clean(value):
    if isinstance(value, str):
        return plain_text(value)
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    return value


def _stage_from(beat, motif):
    stage = {"motif": motif}
    for key in STAGE_KEYS:
        if beat.get(key) is not None:
            stage[key] = _clean(beat[key])
    return stage


def _timed_block(block, words, start_index, piece_start, piece_end, keep):
    if not block:
        return None
    at = _moment(words, block, piece_start + 0.3, start_index)
    if piece_start - 0.02 <= at < piece_end - 0.05:
        fitted = _clean(dict(block))
        fitted["at"] = round(at, 3)
        fitted.pop("spoken", None)
        return fitted
    if keep:
        fitted = _clean(dict(block))
        fitted["at"] = round(max(piece_start, piece_end - 0.2), 3)
        fitted.pop("spoken", None)
        return fitted
    return None


def _overlay(spec, words, start_index, piece_start, piece_end, keep):
    at = _moment(words, spec, piece_start, start_index)
    if not (piece_start - 0.02 <= at < piece_end) and not keep:
        return None
    start = at if piece_start - 0.02 <= at < piece_end else piece_start
    start = max(piece_start, min(start, piece_end - 0.4))
    payload = _stage_from(spec, spec.get("motif"))
    if not payload.get("motif"):
        raise ValueError("an overlay needs a motif")
    payload["start"] = round(start, 3)
    payload["end"] = round(piece_end, 3)
    return payload


def plan_authored(words, source_path, words_path, theme, mode, theme_path, keyword, stage_plan,
                  music_path=None, music=True, emphasis=None, width=1080, height=1920, fps=30):
    if not words:
        raise ValueError("planning needs word timings")
    beats = stage_plan.get("beats") or []
    if not beats:
        raise ValueError("an authored stage plan needs a non-empty beats list")
    ordered = list(words)
    duration = round(float(ordered[-1]["end"]), 3)
    omit_cta = bool(stage_plan.get("omit_cta"))
    passed_keyword = str(keyword or "")
    if omit_cta:
        keyword = ""
    styles = {str(key).lower(): value for key, value in (emphasis or {}).items()}
    if keyword:
        styles.setdefault(keyword.lower(), "green")
    if omit_cta and passed_keyword.lower() not in {str(key).lower() for key in (stage_plan.get("emphasis") or {})}:
        styles.pop(passed_keyword.lower(), None)
    for token in NEGATIVE:
        styles.setdefault(token, "amber")
    # A plan color is intentional. It wins over the automatic amber list.
    for key, value in (stage_plan.get("emphasis") or {}).items():
        styles[str(key).lower()] = value

    resolved = []
    cursor = 0
    for beat in beats:
        if not isinstance(beat, dict) or not beat.get("spoken"):
            raise ValueError("each beat needs a spoken phrase copied from the transcript")
        index = locate(ordered, beat["spoken"], cursor)
        start = 0.0 if not resolved else float(ordered[index]["start"])
        resolved.append({"beat": beat, "index": index, "start": round(start, 3)})
        cursor = index + max(1, len(_tokens(beat["spoken"])))
    for position, item in enumerate(resolved):
        end = resolved[position + 1]["start"] if position + 1 < len(resolved) else duration
        if end <= item["start"] + 0.05:
            raise ValueError(f"beat {item['beat']['spoken']!r} does not advance the timeline")
        item["end"] = round(end, 3)

    shots = []
    split_index = 0
    screen = _phone_screen(theme, width, height)
    for item in resolved:
        beat = item["beat"]
        points = _cut_points(item["start"], item["end"], ordered)
        split_pieces = []
        for piece_index, (start, end) in enumerate(zip(points, points[1:])):
            if end - start < 0.4:
                raise ValueError(f"beat {beat['spoken']!r} produced a shot shorter than 0.4s")
            layout = beat.get("layout", "split") if piece_index == 0 else ("punch_in" if piece_index % 2 else "full")
            if layout not in {"split", "full", "punch_in"}:
                raise ValueError(f"unknown layout on beat {beat['spoken']!r}")
            shot = {
                "id": f"shot-{len(shots):02d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "layout": layout,
            }
            position = beat.get("object_position") or stage_plan.get("object_position")
            if position:
                shot["object_position"] = position
            if layout == "punch_in":
                scale = beat.get("scale", stage_plan.get("punch_scale"))
                if scale:
                    shot["scale"] = float(scale)
            if layout == "split":
                motif = beat.get("motif")
                if not motif:
                    raise ValueError(f"split beat {beat['spoken']!r} needs a motif")
                crop = beat.get("crop") or ("tight" if split_index % 2 else "wide")
                shot["crop"] = crop
                only_split = piece_index == 0
                stage = _stage_from(beat, motif)
                callout = _timed_block(beat.get("callout"), ordered, item["index"], start, end, only_split)
                highlight = _timed_block(beat.get("highlight"), ordered, item["index"], start, end, only_split)
                if callout:
                    stage["callout"] = callout
                if highlight:
                    stage["highlight"] = highlight
                if beat.get("strike"):
                    stage["strike"] = True
                    spoken = beat["strike"].get("spoken") if isinstance(beat["strike"], dict) else None
                    if spoken:
                        at = float(ordered[locate(ordered, spoken, item["index"])]["start"])
                        if start - 0.02 <= at < end:
                            stage["strike_at"] = round(at, 3)
                        elif only_split:
                            stage["strike_at"] = round(min(end - 0.12, start + 0.35), 3)
                    else:
                        stage["strike_at"] = round(min(end - 0.12, start + 0.35), 3)
                shot["stage"] = stage
                if motif in {"phone_frame", "broll_card"}:
                    resolve_annotations(stage, start, end, screen)
                overlays = []
                for spec in beat.get("overlays") or []:
                    overlay = _overlay(spec, ordered, item["index"], start, end, only_split and piece_index == 0)
                    if overlay:
                        if overlay["motif"] == motif:
                            raise ValueError(f"overlay {motif} repeats the shot motif on {beat['spoken']!r}")
                        overlays.append(overlay)
                if overlays:
                    for overlay in overlays:
                        if overlay.get("motif") in {"phone_frame", "broll_card"}:
                            resolve_annotations(overlay, overlay["start"], overlay["end"], screen)
                    shot["overlays"] = overlays
                split_pieces.append(shot)
                split_index += 1
            shots.append(shot)
        # A callout that belongs to a later word stays on the split piece above.
        del split_pieces

    for left, right in zip(shots, shots[1:]):
        if left.get("layout") == "split" and right.get("layout") == "split":
            if left["stage"]["motif"] == right["stage"]["motif"]:
                raise ValueError(
                    f"motif {left['stage']['motif']} repeats on {left['id']} and {right['id']}; "
                    "put a full-screen cut or a different motif between them")
        if right["end"] - right["start"] > 5.5:
            raise ValueError(f"{right['id']} is longer than 5.5s")

    full_scale = float(stage_plan.get("full_scale") or theme["layout"].get("full_scale") or FULL_SCALE)
    step = float(stage_plan.get("punch_step") or PUNCH_STEP)
    shots = apply_emphasis_punches(shots, ordered, styles, full_scale, step)

    headers = []
    notices = []
    for item in resolved:
        beat = item["beat"]
        header = beat.get("header")
        if header:
            lines = [_clean(line) for line in header.get("lines") or []]
            text = _clean(header.get("text") or " ".join(lines))
            entry = {
                "start": item["start"],
                "end": item["end"],
                "text": text,
                "emphasis": [_clean(word) for word in header.get("emphasis") or []],
                "variant": header.get("variant") or "headline",
            }
            if lines:
                entry["lines"] = lines
                entry["green_lines"] = [int(index) for index in header.get("green_lines") or []]
            if header.get("sub"):
                entry["sub"] = _clean(header["sub"])
            if header.get("size"):
                entry["size"] = float(header["size"])
            headers.append(entry)
        if beat.get("disclaimer"):
            notices.append({
                "start": item["start"], "end": item["end"], "text": _clean(beat["disclaimer"]),
            })

    chips = []
    for chip in stage_plan.get("chips") or []:
        if chip.get("from"):
            start = float(ordered[locate(ordered, chip["from"], 0)]["start"])
        elif chip.get("after"):
            needle = _tokens(chip["after"])
            owners = [item for item in resolved if _tokens(item["beat"]["spoken"])[:len(needle)] == needle]
            if not owners:
                raise ValueError(f"chip after {chip['after']!r} does not match a beat")
            start = owners[0]["end"]
        else:
            raise ValueError("a chip needs from (a spoken phrase) or after (a beat phrase)")
        chips.append({
            "start": round(start, 3),
            "end": duration,
            "text": _clean(chip.get("text") or ""),
            "place": chip.get("place") or "stage-corner",
        })

    envelope = []
    bass_at = []
    # Drops and their return hits only exist while a bed is actually mixed.
    if music and music_path:
        bass_at.append(0.0)
        for drop in stage_plan.get("music_drops") or []:
            out_index = locate(ordered, drop["spoken"], 0)
            back_index = locate(ordered, drop["until"], out_index + len(_tokens(drop["spoken"])))
            out_at = float(ordered[out_index]["start"])
            back_at = float(ordered[back_index]["start"])
            if back_at <= out_at + 0.12:
                raise ValueError(f"music drop {drop['spoken']!r} returns before it leaves")
            for moment, level in ((out_at - 0.02, 1), (out_at, 0), (back_at - 0.03, 0), (back_at, 1)):
                moment = round(max(0.0, moment), 3)
                if envelope and moment <= envelope[-1]["t"]:
                    moment = round(envelope[-1]["t"] + 0.03, 3)
                envelope.append({"t": moment, "v": level})
            if drop.get("hit", True):
                bass_at.append(round(back_at, 3))
        if envelope and envelope[-1]["v"] == 0:
            envelope.append({"t": duration, "v": 1})

    under = float(theme["audio"]["music_under_db"])
    music_tracks = []
    if music and music_path:
        track = {
            "path": music_path, "start": 0, "end": duration,
            "source_start": 0, "gain": round(10 ** (-under / 20), 5),
        }
        if envelope:
            if envelope[0]["t"] > 0:
                envelope.insert(0, {"t": 0, "v": 1})
            track["envelope"] = envelope
        music_tracks.append(track)

    gains = theme.get("sfx_gain", {})
    sfx = _cover_sfx(shots, ordered, styles, gains)
    present = {(item["kind"], item["at"]) for item in sfx}
    for moment in bass_at:
        key = ("bass", round(moment, 3))
        if key not in present:
            sfx.append({"kind": "bass", "at": key[1], "gain": gains.get("bass", 0.35)})
    sfx.sort(key=lambda item: (item["at"], item["kind"]))

    title = headers[0]["text"] if headers else plain_text(keyword)
    keep_case = list((stage_plan.get("captions") or {}).get("keep_case") or [])
    position = stage_plan.get("object_position") or theme["layout"]["object_position"]
    stage_slots = []
    for shot in shots:
        if shot["layout"] != "split":
            continue
        covered = _slot_words(shot, ordered)
        covered_ids = {id(word) for word in covered}
        indexes = [index for index, word in enumerate(ordered) if id(word) in covered_ids]
        stage_slots.append({
            "id": shot["id"],
            "role": "authored",
            "start": shot["start"],
            "end": shot["end"],
            "spoken": _spoken(covered),
            "word_range": [indexes[0], indexes[-1] + 1] if indexes else None,
            "motif": shot["stage"]["motif"],
            "authored": True,
        })
    return {
        "style": "kallaway",
        "structure": "authored",
        "theme": theme["id"],
        "theme_mode": mode,
        "theme_path": str(theme_path),
        "title": title,
        "cta": {"keyword": keyword, "lead_magnet": theme["content"]["lead_magnet_title"],
                "omit": omit_cta, "required": not omit_cta},
        "output": {"width": width, "height": height, "fps": fps},
        "source": {"path": source_path, "object_position": position,
                   "segments": [{"start": 0, "end": duration}]},
        "words_path": words_path,
        "audio_policy": {
            "profile": "kallaway",
            "music_required": bool(music and music_path),
            "music_under_db": under,
            "voice_lufs": theme["audio"]["voice_lufs"],
            "user_opt_out": None if music and music_path else "Music bed off for this reel.",
        },
        "music": music_tracks,
        "headers": headers,
        "chips": chips,
        "notices": notices,
        "shots": shots,
        "stage_slots": stage_slots,
        "captions": {
            "max_words": 2, "uppercase": False, "word_styles": styles,
            "keep_case": [_clean(token) for token in keep_case],
            "phrases": caption_phrases(ordered, styles), "omit_terminal_punctuation": True,
        },
        "sfx": sfx,
    }
