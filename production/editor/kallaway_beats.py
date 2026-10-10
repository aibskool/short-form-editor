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
    "variant", "uncropped",
)

# Full-screen is zoomed out so the face is about a third of the frame. A punch is +10%.
FULL_SCALE = 0.90
PUNCH_STEP = 1.10
CONTRAST_WORDS = {"but", "so", "now", "most", "never", "stop", "you"}


def _emphasis_rank(word, styles):
    """Lower is the word the punch should land on. None means leave the shot alone."""
    token = _token(word)
    if not token:
        return None
    style = styles.get(token)
    if style == "marker":
        return 0
    if style in {"green", "amber"}:
        return 1
    if any(char.isdigit() for char in token):
        return 2
    if token in CONTRAST_WORDS and style != "normal":
        return 3
    return None


def apply_emphasis_punches(shots, words, styles, full_scale=FULL_SCALE, step=PUNCH_STEP):
    """One silent punch on the key word of a full-screen stretch, held through that stretch.

    The full-screen scale is the thought-start frame. The punch does not jump
    back out inside the phrase, and neither piece is shorter than 0.8 s. An
    authored punch-in is kept as one shot.
    """
    built = []
    for shot in shots:
        start, end = float(shot["start"]), float(shot["end"])
        if shot.get("layout") == "punch_in":
            shot = dict(shot)
            if "scale" not in shot:
                shot["scale"] = round(float(full_scale) * float(step), 3)
            built.append(shot)
            continue
        if shot.get("layout") != "full":
            built.append(shot)
            continue
        best = None
        if end - start >= 1.25:
            for word in words:
                at = float(word["start"])
                # The punch itself is held at least 0.8 s. The opening frame can be shorter.
                if not (start + 0.45 <= at <= end - 0.8):
                    continue
                rank = _emphasis_rank(word, styles)
                if rank is None:
                    continue
                if best is None or rank < best[0] or (rank == best[0] and at < best[1]):
                    best = (rank, at)
        piece = {key: value for key, value in shot.items() if key != "stage"}
        piece["scale"] = round(float(full_scale), 3)
        if best is None:
            piece["start"] = round(start, 3)
            piece["end"] = round(end, 3)
            piece["layout"] = "full"
            built.append(piece)
            continue
        at = best[1]
        opening = dict(piece)
        opening["start"] = round(start, 3)
        opening["end"] = round(at, 3)
        opening["layout"] = "full"
        built.append(opening)
        punch = dict(piece)
        punch["start"] = round(at, 3)
        punch["end"] = round(end, 3)
        punch["layout"] = "punch_in"
        punch["scale"] = round(float(full_scale) * float(step), 3)
        built.append(punch)
    for index, shot in enumerate(built):
        shot["id"] = f"shot-{index:02d}"
    return built


def _phone_screen(theme, width, height):
    from kallaway_motifs import hero_phone_box
    layout = theme["layout"]
    box = hero_phone_box(layout["stage_width"] * width, layout["stage_height"] * height)
    return box["screen"]


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


_SMALL_WORDS = {"a", "an", "the", "for", "to", "of", "and", "or", "in", "on", "at", "by", "vs"}


def _title_word(token, first):
    bare = token.strip(".,!?:;\"'")
    if not bare:
        return token
    if any(ch.isdigit() for ch in bare) or bare.startswith("$"):
        return token
    if not first and bare.lower() in _SMALL_WORDS:
        return bare.lower() + token[len(bare):]
    return bare[:1].upper() + bare[1:].lower() + token[len(bare):]


def _title_case(text):
    words = str(text).split()
    return " ".join(_title_word(word, index == 0) for index, word in enumerate(words))


def _fit_header(header, width, height, layout):
    """Title Case Inter, one payoff word, kept inside y 100–240."""
    lines = [_title_case(line) for line in (header.get("lines") or [])]
    text = _title_case(header.get("text") or " ".join(lines))
    if not lines:
        lines = [text] if text else []
    green = {int(index) for index in header.get("green_lines") or []}
    emphasis = [_title_case(word) if not any(ch.isdigit() for ch in word) else word
                for word in header.get("emphasis") or []]
    payoff = ""
    payoff_style = "marker"
    if emphasis:
        payoff = emphasis[-1].strip(".,!?:;\"'")
    elif green and lines:
        source = lines[min(max(green), len(lines) - 1)]
        payoff = source.split()[-1].strip(".,!?:;\"'") if source.split() else ""
    if payoff and (payoff[:1] == "$" or any(ch.isdigit() for ch in payoff)):
        payoff_style = "box"
    title_top = float(layout.get("title_top", 0.0520833333)) * height
    max_bottom = min(240.0, float(layout["stage_top"]) * height - 8)
    room = max(48.0, max_bottom - title_top)
    line_count = max(1, len(lines))
    size = min(72.0, room / (line_count * 1.05))
    # Shrink until the longest line fits the title width.
    usable = width * 0.86
    longest = max((len(line) for line in lines), default=1)
    while size > 36 and longest * size * 0.52 > usable:
        size -= 2
    bottom = round(title_top + line_count * size * 1.05, 1)
    entry = {
        "text": text,
        "emphasis": [payoff] if payoff else [],
        "payoff": payoff,
        "payoff_style": payoff_style,
        "variant": header.get("variant") or "headline",
        "size": round(size, 1),
        "bottom": bottom,
    }
    if lines:
        entry["lines"] = lines
    if header.get("sub"):
        entry["sub"] = _clean(header["sub"])
    return entry


def _cap_emphasis(words, styles, spans):
    """At most one marker or green word in each beat. Amber prices stay."""
    rank = {"marker": 0, "green": 1}
    winners = set()
    losers = set()
    for begin, end in spans:
        best = None
        seen = []
        for index in range(begin, end):
            token = _token(words[index])
            style = styles.get(token)
            if style not in rank:
                continue
            seen.append(token)
            if best is None or rank[style] < best[0] or (rank[style] == best[0] and index >= best[2]):
                best = (rank[style], token, index)
        if best:
            winners.add(best[1])
            for token in seen:
                if token != best[1]:
                    losers.add(token)
    for token in losers - winners:
        styles[token] = "normal"
    return styles


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
    # A phone chip with no place used to sit on the mock header. The bottom
    # edge is the only place that clears the screen and the title.
    if motif == "phone_frame":
        chip = stage.get("chip")
        if isinstance(chip, str):
            stage["chip"] = {"text": chip, "place": "bottom"}
        elif isinstance(chip, dict) and not chip.get("place"):
            chip["place"] = "bottom"
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
            if layout == "split":
                position = beat.get("object_position") or stage_plan.get("object_position")
            else:
                position = beat.get("object_position") or stage_plan.get("full_object_position") or theme["layout"].get("full_object_position")
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
                crop = beat.get("crop") or "wide"
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
            shots.append(shot)
        # A callout that belongs to a later word stays on the split piece above.
        del split_pieces

    for left, right in zip(shots, shots[1:]):
        if left.get("layout") == "split" and right.get("layout") == "split":
            same = (
                left["stage"].get("motif") == right["stage"].get("motif")
                and (left["stage"].get("variant") or "") == (right["stage"].get("variant") or "")
                and (left["stage"].get("media") or "") == (right["stage"].get("media") or "")
                and (left["stage"].get("text") or "") == (right["stage"].get("text") or "")
            )
            if same:
                raise ValueError(
                    f"motif {left['stage']['motif']} repeats on {left['id']} and {right['id']}; "
                    "put a full-screen cut or a different motif between them")
        if right["end"] - right["start"] > 5.5:
            raise ValueError(f"{right['id']} is longer than 5.5s")

    spans = []
    for index, (item, nxt) in enumerate(zip(resolved, resolved[1:] + [None])):
        begin = 0 if index == 0 else item["index"]
        stop = nxt["index"] if nxt else len(ordered)
        spans.append((begin, stop))
    _cap_emphasis(ordered, styles, spans)
    full_scale = float(stage_plan.get("full_scale") or theme["layout"].get("full_scale") or FULL_SCALE)
    step = float(stage_plan.get("punch_step") or PUNCH_STEP)
    shots = apply_emphasis_punches(shots, ordered, styles, full_scale, step)

    headers = []
    notices = []
    for item in resolved:
        beat = item["beat"]
        header = beat.get("header")
        if header:
            entry = _fit_header(header, width, height, theme["layout"])
            entry["start"] = item["start"]
            entry["end"] = item["end"]
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

    from kallaway_audio import UNDER_DB
    unders = theme.get("sfx_under_db") or {}
    sfx = _cover_sfx(shots, ordered, styles, unders, fps, headers)
    present = {(item["kind"], item["at"]) for item in sfx}
    for moment in bass_at:
        key = ("bass", round(moment, 3))
        if key not in present:
            sfx.append({
                "kind": "bass", "at": key[1],
                "under_db": float(unders.get("bass", UNDER_DB["bass"])),
            })
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
            "max_words": 1, "uppercase": False, "word_styles": styles,
            "keep_case": [_clean(token) for token in keep_case],
            "phrases": caption_phrases(ordered, styles), "omit_terminal_punctuation": True,
        },
        "sfx": sfx,
        "speaker_reveal": float(stage_plan["speaker_reveal"]) if stage_plan.get("speaker_reveal") else None,
    }
