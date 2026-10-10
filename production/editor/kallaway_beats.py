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
    NEGATIVE, _cover_sfx, _lands_on, _slot_words, _spoken, _token, anchor_sfx,
    caption_phrases, plain_text, sfx_placement_rows,
)


MAX_SHOT = 5.4
MIN_SHOT = 0.5
STAGE_KEYS = (
    "media", "items", "count", "value", "label", "text", "heights", "negative",
    "pages", "hold", "active", "prefix", "suffix", "scroll", "desaturate",
    "chip", "reveal", "labels", "kicker", "disclaimer", "progress",
    "media_start", "playback_rate", "target_still", "target_time", "poster_time", "typing",
    "variant", "uncropped", "scan", "notes", "from", "sweep", "motion", "lock_at", "negative",
)

# Full-screen and punch share scale 1 so the face is full bleed with no mid-shot jump.
FULL_SCALE = 1.0
PUNCH_STEP = 1.0
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
        punch_scale = round(float(full_scale) * float(step), 3)
        if best is None or abs(punch_scale - float(full_scale)) < 0.001:
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
        punch["scale"] = punch_scale
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
    # AI, ADA, and WCAG stay initials. WEBSITE stays capped when the line wrote it that way.
    if bare.upper() in {"AI", "ADA", "WCAG"} or (bare.upper() == "WEBSITE" and bare.isupper()):
        return bare.upper() + token[len(bare):]
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
        # A price in the title is the bad offer. Amber, not a green payoff box.
        payoff_style = "amber"
    if header.get("payoff_tone") == "amber":
        payoff_style = "amber"
    if header.get("payoff_style") in {"box", "marker", "amber"}:
        payoff_style = header["payoff_style"]
    title_top = float(layout.get("title_top", 0.0520833333)) * height
    # 40–60 px between the title and the stage. The final card sits on that line.
    max_bottom = min(240.0, float(layout["stage_top"]) * height - 50.0)
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


def output_join_times(ranges):
    """Picture-cut times on the tightened clock. The concat hard-cuts at each range end."""
    clock = 0.0
    times = []
    ordered = list(ranges or [])
    for begin, end in ordered[:-1]:
        clock += float(end) - float(begin)
        times.append(round(clock, 3))
    return times


def snap_shot_edges(shots, scene_times, window=0.12, minimum=0.5, joins=None):
    """Move a layout cut onto a nearby picture cut so a 1–3 frame orphan cannot sit between them.

    A tighten join within two frames wins, so the layout and the take change on
    the same frame. Otherwise the picture change is the earliest scene inside
    the window. A one-frame pull is kept even when a neighbor is already short:
    reverting it is what leaves the stray frame of the previous take.
    """
    if len(shots) < 2 or (not scene_times and not joins):
        return shots
    original = [float(shot["start"]) for shot in shots] + [float(shots[-1]["end"])]
    edges = list(original)
    scenes = sorted(float(moment) for moment in (scene_times or []))
    join_times = sorted(float(moment) for moment in (joins or []))
    locked = set()
    for index in range(1, len(edges) - 1):
        if not join_times:
            break
        nearest = min(join_times, key=lambda moment: abs(moment - edges[index]))
        if abs(nearest - edges[index]) <= 2.5 / 30.0:
            edges[index] = nearest
            locked.add(index)
    for index in range(1, len(edges) - 1):
        if index in locked or not scenes:
            continue
        near = [moment for moment in scenes if abs(moment - edges[index]) <= window]
        if not near:
            continue
        before = [moment for moment in near if moment <= edges[index] + (1.0 / 30.0)]
        edges[index] = min(before) if before else min(near, key=lambda moment: abs(moment - edges[index]))
    for index in range(1, len(edges) - 1):
        if index in locked:
            continue
        moved = abs(edges[index] - original[index])
        short = edges[index] - edges[index - 1] < minimum or edges[index + 1] - edges[index] < minimum
        if short and moved > 0.15:
            edges[index] = original[index]
    for shot, start, end in zip(shots, edges, edges[1:]):
        shot["start"] = round(start, 3)
        shot["end"] = round(end, 3)
    return shots


def close_short_picture_gaps(shots, joins, minimum=0.5):
    """Move a layout edge onto a picture join that would leave a flash under 0.5 s.

    The plan can call a shot 2 s long while the picture changes 0.4 s after the
    layout cut. On the output frames that 0.4 s is its own shot. Pull the edge
    onto the join when both neighbors still hold `minimum`.
    """
    if len(shots) < 2 or not joins:
        return shots
    edges = [float(shots[0]["start"])] + [float(shot["end"]) for shot in shots]
    for join in sorted(float(moment) for moment in joins):
        nearest = min(range(1, len(edges) - 1), key=lambda index: abs(edges[index] - join))
        if abs(edges[nearest] - join) < 1.0 / 30.0 or abs(edges[nearest] - join) >= minimum:
            continue
        if join - edges[nearest - 1] + 1e-3 < minimum or edges[nearest + 1] - join + 1e-3 < minimum:
            continue
        edges[nearest] = join
    for shot, start, end in zip(shots, edges, edges[1:]):
        shot["start"] = round(start, 3)
        shot["end"] = round(end, 3)
    return shots


def short_picture_runs(path, minimum=0.5, change=28.0, edge=32):
    """Shots under `minimum` seconds, measured from output-frame changes.

    A hard cut moves the whole downscaled frame. A caption or a small graphic
    does not clear `change`, so those are not extra shots.
    """
    import subprocess
    import numpy as np
    probe = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(path)],
        text=True).strip()
    num, den = (probe.split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    if fps <= 0:
        fps = 30.0
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"scale={edge}:{edge}:flags=area",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stderr=subprocess.DEVNULL)
    frame = edge * edge * 3
    count = len(raw) // frame
    if count < 2:
        return []
    frames = np.frombuffer(raw[:count * frame], dtype=np.uint8).reshape(count, edge, edge, 3).astype(np.int16)
    diffs = np.abs(frames[1:].astype(np.int16) - frames[:-1]).mean(axis=(1, 2, 3))
    cuts = [0]
    for index, diff in enumerate(diffs, start=1):
        if float(diff) >= change:
            cuts.append(index)
    cuts.append(count)
    short = []
    for begin, end in zip(cuts, cuts[1:]):
        seconds = (end - begin) / fps
        if seconds + 1e-6 < minimum:
            short.append({
                "start": round(begin / fps, 3),
                "end": round(end / fps, 3),
                "seconds": round(seconds, 3),
            })
    return short


def punch_short_jumps(shots, joins, scale=1.12, short=1.5):
    """A picture join inside a full-face shot that leaves a piece under 1.5 s becomes a punch.

    The jump stays in the take. The short side scales up, at most 15 percent,
    so the cut is a punch instead of a naked jump.
    """
    join_times = [float(moment) for moment in (joins or [])]
    if len(shots) < 1 or not join_times or scale <= 1.0 or scale > 1.15:
        return shots
    built = []
    for shot in shots:
        start, end = float(shot["start"]), float(shot["end"])
        if shot.get("layout") != "full":
            built.append(shot)
            continue
        inside = [moment for moment in join_times if start + 0.2 < moment < end - 0.2]
        if not inside:
            built.append(shot)
            continue
        cut = min(inside, key=lambda moment: min(moment - start, end - moment))
        left, right = cut - start, end - cut
        if min(left, right) >= short or min(left, right) < 0.5:
            built.append(shot)
            continue
        opening = dict(shot)
        opening["end"] = round(cut, 3)
        closing = dict(shot)
        closing["start"] = round(cut, 3)
        if left <= right:
            opening["layout"] = "punch_in"
            opening["scale"] = round(float(scale), 3)
            closing["layout"] = "full"
            closing["scale"] = 1.0
        else:
            closing["layout"] = "punch_in"
            closing["scale"] = round(float(scale), 3)
            opening["layout"] = "full"
            opening["scale"] = 1.0
        built.extend((opening, closing))
    for index, shot in enumerate(built):
        shot["id"] = f"shot-{index:02d}"
    return built


def lengthen_closing_face(shots, headers=None, minimum=1.52):
    """The last full-face or punch has to hold at least a second and a half."""
    if len(shots) < 2:
        return shots
    last = shots[-1]
    if last.get("layout") not in {"full", "punch_in"}:
        return shots
    span = float(last["end"]) - float(last["start"])
    if span + 1e-3 >= minimum:
        return shots
    prev = shots[-2]
    room = float(prev["end"]) - float(prev["start"]) - 1.2
    shift = min(max(0.0, room), minimum - span)
    if shift < 0.03:
        return shots
    boundary = round(float(last["start"]) - shift, 3)
    prev["end"] = boundary
    last["start"] = boundary
    for header in headers or []:
        if float(header.get("start", 0)) < boundary < float(header.get("end", 0)):
            header["end"] = boundary
    return shots


def _sentence_spans(words):
    """Sentence slices. A period, a long pause, or a capital start opens the next one."""
    if not words:
        return []
    continuations = {"and", "but", "that", "so", "when", "or", "because"}
    spans = []
    begin = 0
    for index, word in enumerate(words[:-1]):
        text = str(word.get("word") or word.get("text") or "").rstrip()
        nxt = str(words[index + 1].get("word") or words[index + 1].get("text") or "").strip()
        gap = float(words[index + 1]["start"]) - float(word["end"])
        token = _token(word)
        nxt_token = _token(words[index + 1])
        end_punct = text.endswith((".", "!", "?"))
        capital = bool(nxt[:1].isupper()) and nxt_token not in {"i", "ive", "id", "im"}
        fresh_i = nxt_token in {"i", "ive", "id", "im"} and token not in continuations
        if end_punct or gap > 0.35 or capital or fresh_i:
            spans.append((begin, index + 1))
            begin = index + 1
    spans.append((begin, len(words)))
    return spans


def _cap_emphasis(words, styles, spans):
    """One colored word per sentence. Amber counts. A price beats another amber."""
    rank = {"marker": 0, "amber": 1, "green": 2}
    chosen = {}
    groups = _sentence_spans(words) or list(spans)
    for begin, end in groups:
        best = None
        seen = []
        for index in range(begin, end):
            token = _token(words[index])
            style = styles.get(token)
            if style not in rank:
                continue
            score = rank[style]
            if any(ch.isdigit() for ch in token) and style == "amber":
                score = -1
            seen.append(index)
            if best is None or score < best[0] or (score == best[0] and index >= best[2]):
                best = (score, token, index)
        if best:
            chosen[best[2]] = styles.get(best[1], "normal")
    style_at = []
    for index, word in enumerate(words):
        token = _token(word)
        style = styles.get(token, "normal")
        if style in rank:
            style = chosen.get(index, "normal")
        style_at.append(style if style in {"normal", "marker", "green", "amber"} else "normal")
    kept = {}
    for index, style in enumerate(style_at):
        if style in rank:
            kept[_token(words[index])] = style
    for token in list(styles):
        if styles.get(token) in rank and token not in kept:
            styles[token] = "normal"
    for token, style in kept.items():
        styles[token] = style
    return style_at


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
                if beat.get("lock_spoken"):
                    at = float(ordered[locate(ordered, beat["lock_spoken"], item["index"])]["start"])
                    if start - 0.02 <= at < end:
                        stage["lock_at"] = round(at, 3)
                if motif == "phone_frame" and shots and shots[-1].get("layout") in {"full", "punch_in"}:
                    # The handset enters after the face cut. The whoosh rides that entrance.
                    stage["enter_after"] = 0.20
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
    # Colors baked onto the transcript join the cap. A plan entry already in
    # ``styles`` keeps its color, so an amber price is not put back to green.
    for word in ordered:
        baked = word.get("style")
        token = _token(word)
        if baked in {"marker", "green", "amber"} and token not in styles:
            styles[token] = baked
    style_at = _cap_emphasis(ordered, styles, spans)
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
            # The same title across beats is one hold, not a new card that pops in again.
            if headers and headers[-1].get("text") == entry.get("text") and abs(headers[-1]["end"] - entry["start"]) < 0.08:
                headers[-1]["end"] = entry["end"]
            else:
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

    lengthen_closing_face(shots, headers, minimum=1.52)
    from kallaway_audio import UNDER_DB
    unders = theme.get("sfx_under_db") or {}
    sfx = _cover_sfx(shots, ordered, styles, unders, fps, headers)
    present = {(item["kind"], item["at"]) for item in sfx}
    for moment in bass_at:
        key = ("bass", round(moment, 3))
        if key not in present:
            landing = ""
            for shot in shots:
                if shot.get("layout") != "split" or not shot.get("stage"):
                    continue
                if float(shot["start"]) - 0.05 <= key[1] <= float(shot["end"]) + 0.02:
                    landing = _lands_on(shot["stage"].get("motif"), shot["stage"])
                    break
            from kallaway_pack import BOOM_14
            cue = {
                "kind": "bass", "at": key[1], "file": BOOM_14, "combo": "2",
                "under_db": float(unders.get("bass", UNDER_DB["bass"])),
                "lands_on": landing, "label": "Music return",
                "fixed_file": True, "fixed_lead": True,
            }
            if not landing:
                cue["mute"] = True
                cue["mute_reason"] = "no visual"
            sfx.append(cue)
    sfx = anchor_sfx(sfx, ordered)
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
            "style_at": style_at,
            "keep_case": [_clean(token) for token in keep_case],
            "phrases": caption_phrases(ordered, styles), "omit_terminal_punctuation": True,
        },
        "sfx": sfx,
        "sfx_log": sfx_placement_rows(sfx),
        "speaker_reveal": float(stage_plan["speaker_reveal"]) if stage_plan.get("speaker_reveal") else None,
    }
