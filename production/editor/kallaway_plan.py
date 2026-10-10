"""Turn a tightened word list into a Kallaway-style timeline using the brand preset.

When a stage plan is supplied, it chooses the graphic for each split shot.
Without one, motifs rotate through the library. The sequence is seeded by the
source video path, and the same motif is not used on two split shots in a row.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from kallaway_motifs import MOTIFS, stage_events, stage_windows
from kallaway_style import load_theme

NEGATIVE = {"no", "not", "never", "broken", "failed", "worse", "bad", "wrong", "stop"}
# Closing split is always the lead-magnet fan. Everything else rotates.
LIBRARY = (
    "thumbnail_grid", "line_chart", "bar_chart", "numbered_list", "counter",
    "highlight_box", "hand_circle", "typing_ui", "phone_frame", "broll_card",
    "mind_map", "logo_row", "quote_card", "offer_pair", "flow_line", "pill",
    "cursor_mock", "vacuum_merge", "state_swap",
)
AUTHOR_KEYS = {"motif", "spoken", "word_range", "why", "note", "covers", "schema"}


def plain_text(value):
    text = str(value).replace("\u2014", ", ").replace("\u2013", "-")
    text = re.sub(r"\s+", " ", text).strip()
    if "\u2014" in text or "\u2013" in text:
        raise ValueError("on-screen copy still contains an em dash or en dash")
    return text


def _token(word):
    return re.sub(r"[^a-z0-9']", "", str(word.get("word", word.get("text", ""))).lower())


def video_seed(source_path):
    """Stable integer seed from the video path. The same path keeps the same motif order."""
    digest = hashlib.sha256(str(source_path).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _snap(target, starts, low, high):
    window = [point for point in starts if low <= point <= high]
    pool = window or list(starts)
    if not pool:
        return target
    return min(pool, key=lambda point: (abs(point - target), point))


def caption_phrases(words, styles):
    """One lowercase word per chunk. Emphasis still lives on the word style."""
    del styles
    return [{"word_range": [index, index + 1]} for index in range(len(words))]


def _title_case(text):
    small = {"a", "an", "the", "to", "and", "or", "of", "on", "in", "for"}
    words = plain_text(text).split()
    titled = []
    for index, word in enumerate(words):
        lower = word.lower()
        titled.append(lower if index and lower in small else lower[:1].upper() + lower[1:])
    return " ".join(titled)


def _rotate(seed, index, previous):
    """Next library motif for this video, never the same as the previous split."""
    return _rotate_away(seed, index, {previous} if previous else set())


def _rotate_away(seed, index, blocked):
    span = len(LIBRARY)
    for step in range(span):
        motif = LIBRARY[(seed + index + step) % span]
        if motif not in blocked:
            return motif
    return LIBRARY[seed % span]


def _stage_for(motif, words, theme, keyword):
    spoken = [_token(word) for word in words if _token(word)]
    text = " ".join(spoken)
    content = theme["content"]
    if motif == "thumbnail_grid":
        labels = [_title_case(token) for token in spoken[:8]] or ["Hook", "Proof", "Offer", "Cut"]
        return {"motif": motif, "count": 8, "items": labels}
    if motif == "numbered_list":
        items = []
        chunk = []
        for token in spoken:
            chunk.append(token)
            if len(chunk) == 3:
                items.append(_title_case(" ".join(chunk)))
                chunk = []
            if len(items) == 4:
                break
        if chunk and len(items) < 4:
            items.append(_title_case(" ".join(chunk)))
        return {"motif": motif, "items": items or ["Open on the split", "Cut closer", "Show the proof", "Ask them to comment"]}
    if motif == "counter":
        number = 30
        for token in spoken:
            if token.isdigit():
                number = int(token)
                break
        return {"motif": motif, "value": number, "label": "ideas" if number == 30 else "count"}
    if motif == "bar_chart":
        return {"motif": motif, "count": 4, "negative": any(token in NEGATIVE or token == "works" for token in spoken)}
    if motif == "highlight_box":
        label = next((token for token in spoken if token in {"secret", "change", "proof"}), None)
        return {"motif": motif, "label": label or "the line that matters"}
    if motif == "hand_circle":
        return {"motif": motif, "label": "no longer" if "no" in spoken else (spoken[0] if spoken else "this")}
    if motif == "typing_ui":
        return {"motif": motif, "text": plain_text(" ".join(word.get("word", "") for word in words[:8])) or "Write the next step."}
    if motif == "doc_fan":
        return {"motif": motif, "count": 5, "pages": [
            ("VAULT", content["lead_magnet_title"]),
            ("30+", "AI business ideas"),
            ("A TO Z", "First client guide"),
            ("START", "A working system"),
            (keyword, "Comment the keyword"),
        ]}
    if motif == "mind_map":
        return {"motif": motif, "label": "Offer", "items": ["Hook", "Proof", "CTA"]}
    if motif == "logo_row":
        return {"motif": motif, "items": ["Plan", "Build", "Ship"]}
    if motif == "phone_frame":
        return {"motif": motif}
    if motif == "broll_card":
        return {"motif": motif}
    if motif == "line_chart":
        return {"motif": motif}
    if motif == "quote_card":
        return {"motif": motif, "text": "We already have one."}
    if motif == "offer_pair":
        return {"motif": motif, "items": ["Voice agent", "Site audit"]}
    if motif == "flow_line":
        return {"motif": motif, "items": ["New money", "You"]}
    if motif == "pill":
        return {"motif": motif, "label": keyword}
    return {"motif": motif}


def parse_stage_plan(stage_plan):
    """Return ('none'|'order'|'match', entries).

    A list, or an object whose stages omit locators, is applied in split-slot order.
    An object whose stages each name `spoken` or `word_range` is matched to those words.
    """
    if not stage_plan:
        return "none", []
    if isinstance(stage_plan, list):
        return "order", list(stage_plan)
    if isinstance(stage_plan, dict):
        stages = stage_plan.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValueError(
                "stage plan object needs a non-empty stages list; see production/editor/stage-plan.schema.json")
        located = []
        for item in stages:
            if not isinstance(item, dict):
                raise ValueError("stages in a stage-plan object must be objects with a motif")
            located.append(bool(item.get("spoken") or item.get("word_range")))
        if any(located) and not all(located):
            raise ValueError(
                "stage plan stages must all name a spoken phrase or word_range, "
                "or none of them so order follows the split slots")
        return ("match" if all(located) else "order"), list(stages)
    raise ValueError("stage plan must be a list of motifs or a kallaway-stage-plan/v1 object")


def _entry_motif(entry):
    if isinstance(entry, str):
        motif = entry
    elif isinstance(entry, dict):
        motif = entry.get("motif")
    else:
        raise ValueError("each stage plan entry must be a motif name or an object")
    if motif not in MOTIFS:
        names = ", ".join(MOTIFS)
        raise ValueError(f"unknown stage motif {motif!r}; choose one of: {names}")
    if motif == "doc_fan":
        raise ValueError("doc_fan is reserved for the closing lead-magnet shot")
    return motif


def _apply_entry(shot, entry, covered, theme, keyword):
    motif = _entry_motif(entry)
    stage = _stage_for(motif, covered, theme, keyword)
    if isinstance(entry, dict):
        stage.update({key: value for key, value in entry.items() if key not in AUTHOR_KEYS and value is not None})
    stage["motif"] = motif
    shot["stage"] = stage
    shot["stage_authored"] = True


def _slot_words(shot, ordered):
    return [word for word in ordered if shot["start"] - 0.02 <= float(word["start"]) < shot["end"]]


def _spoken(words):
    return " ".join(token for token in (_token(word) for word in words) if token)


def _match_entry(entry, slots, ordered, claimed):
    if entry.get("word_range") is not None:
        span = entry["word_range"]
        if (not isinstance(span, (list, tuple)) or len(span) != 2
                or not all(isinstance(part, int) and not isinstance(part, bool) for part in span)):
            raise ValueError("word_range must be [start, end) integer word indexes")
        start, end = span
        if not 0 <= start < end <= len(ordered):
            raise ValueError(f"word_range {list(span)} is outside the transcript")
        when = float(ordered[start]["start"])
        hits = [shot for shot in slots if shot["start"] - 0.02 <= when < shot["end"] and id(shot) not in claimed]
        if not hits:
            raise ValueError(
                f"word_range {list(span)} falls outside an open split slot; "
                "copy a range from stage_slots")
        return hits[0]
    needle = plain_text(entry.get("spoken", "")).lower()
    if not needle:
        raise ValueError("a matched stage needs spoken text or a word_range")
    hits = []
    for shot in slots:
        if id(shot) in claimed:
            continue
        if needle in _spoken(_slot_words(shot, ordered)):
            hits.append(shot)
    if not hits:
        raise ValueError(
            f"stage plan phrase {entry.get('spoken')!r} is not inside an open split shot; "
            "run kallaway_plan.py --slots and copy a phrase from stage_slots")
    return hits[0]


def _lands_on(motif, stage):
    """Short name of the picture a cue is allowed to hit."""
    stage = stage or {}
    motif = str(motif or "graphic")
    detail = ""
    for key in ("label", "text", "variant"):
        value = stage.get(key)
        if isinstance(value, str) and value.strip():
            detail = re.sub(r"\s+", " ", value).strip()[:60]
            break
    if not detail:
        items = stage.get("items")
        if isinstance(items, list) and items:
            detail = re.sub(r"\s+", " ", str(items[0])).strip()[:40]
    return f"{motif}: {detail}" if detail else motif


def word_gaps(words, minimum=0.02):
    """Pauses between aligned words. Silencedetect is not used.

    SFX and outdoor rumble sit above the silence threshold, so a detector on
    the mix hides the pause. The word clock is the only one that still shows it.
    """
    ordered = sorted(words or [], key=lambda word: float(word["start"]))
    gaps = []
    for prev, nxt in zip(ordered, ordered[1:]):
        start = float(prev["end"])
        end = float(nxt["start"])
        if end - start >= minimum:
            gaps.append((start, end, prev))
    return gaps


def gap_at(moment, gaps):
    """The word before ``moment`` when that moment sits strictly inside its pause."""
    moment = float(moment)
    for start, end, prev in gaps:
        if start < moment < end:
            return prev
    return None


def anchor_sfx(cues, words, fps=30):
    """Keep every audible hit on a picture, and off every aligned pause.

    A whoosh or riser leads its visual by 3–4 frames. That lead is the hit,
    so it is not pulled back onto the picture. Any other hit that only lands
    in a pause is muted.
    """
    gaps = word_gaps(words)
    lead = 4.0 / float(fps or 30)
    for cue in cues:
        if cue.get("mute"):
            continue
        if not str(cue.get("lands_on") or "").strip():
            cue["mute"] = True
            cue["mute_reason"] = "no visual"
            continue
        heard = float(cue.get("sound_at", cue.get("at", 0)))
        visual = float(cue.get("at", heard))
        kind = cue.get("kind")
        if kind in {"whoosh", "riser"} or cue.get("rotate") == "whoosh":
            if gap_at(visual, gaps) is None:
                cue["sound_at"] = round(max(0.0, visual - lead), 3)
                continue
        if gap_at(heard, gaps) is None:
            continue
        if gap_at(visual, gaps) is None and abs(visual - heard) <= 0.35:
            cue["sound_at"] = round(visual, 3)
            continue
        cue["mute"] = True
        cue["mute_reason"] = "gap"
    return cues


def sfx_placement_rows(cues):
    """Audible cues only: when they play, which pack file, and the picture they hit."""
    rows = []
    for cue in cues or []:
        if cue.get("mute"):
            continue
        pack = str(cue.get("file") or "")
        rows.append({
            "time": round(float(cue.get("sound_at", cue.get("at", 0))), 3),
            "file": Path(pack).name,
            "pack_file": pack,
            "lands_on": str(cue.get("lands_on") or ""),
            "label": str(cue.get("label") or ""),
        })
    rows.sort(key=lambda row: (row["time"], row["file"], row["label"]))
    return rows


def _cover_sfx(shots, words, styles, unders=None, fps=30, headers=None):
    """Graphic entrances get the mapped pack sound. Face cuts stay silent.

    Whooshes lead panel slides, chapter-header swaps, and big graphic
    transitions by 4 frames. ``at`` stays on the picture so the style check
    still sees the motif. The sample itself starts at ``sound_at``.
    A cue with no picture, and a cue whose sound falls in an aligned pause,
    is muted. The loop-close whoosh has no entrance to land on, so it stays muted.
    """
    from kallaway_audio import UNDER_DB
    from kallaway_pack import BOOM_14, COOL_WHOOSH, finish_sfx
    del styles
    unders = unders or {}
    fps = float(fps or 30)
    events = []
    for shot in shots:
        if shot.get("layout") != "split":
            continue
        for motif, start, end, stage in stage_windows(shot):
            for event in stage_events(motif, start, end, stage):
                event = dict(event)
                landing = _lands_on(motif, stage)
                event["lands_on"] = landing
                for extra in event.get("also") or []:
                    extra.setdefault("lands_on", landing)
                bed = event.get("bed")
                if isinstance(bed, dict):
                    bed.setdefault("lands_on", landing)
                events.append(event)
    if shots:
        opening = "opening title"
        first = shots[0]
        if first.get("layout") == "split" and first.get("stage"):
            opening = _lands_on(first["stage"].get("motif"), first["stage"])
        elif headers:
            text = str(headers[0].get("text") or "")
            if text:
                opening = f"chapter header: {text}"
        events.append({
            "at": 0.0, "kind": "bass", "file": BOOM_14, "combo": "2",
            "label": "Cold Slam", "under_db": float(unders.get("bass", UNDER_DB["bass"])),
            "fixed_file": True, "fixed_lead": True, "band": "low",
            "lands_on": opening,
        })
    previous = None
    for header in headers or []:
        text = str(header.get("text") or "")
        at = float(header.get("start") or 0.0)
        if previous and text and text != previous:
            covered = any(
                item.get("kind") in {"whoosh", "riser"} and abs(float(item.get("at", 0)) - at) < 0.2
                for item in events
            )
            if not covered:
                events.append({
                    "at": round(at, 3), "kind": "whoosh", "combo": "8",
                    "label": "Chapter header", "rotate": "whoosh", "band": "mid",
                    "lands_on": f"chapter header: {text}",
                })
        if text:
            previous = text
    if shots:
        duration = max(float(shot["end"]) for shot in shots)
        # The tail whoosh does not open a picture. It stays on the timeline
        # so the density pass can see it, and it does not play.
        events.append({
            "at": round(duration, 3), "kind": "whoosh", "file": COOL_WHOOSH, "combo": "47",
            "label": "Loop Close", "sound_at": round(max(0.0, duration - (1.0 / fps)), 3),
            "fixed_file": True, "fixed_lead": True, "band": "mid",
            "under_db": float(unders.get("whoosh", UNDER_DB["whoosh"])),
            "mute": True, "mute_reason": "no visual",
        })
    return anchor_sfx(finish_sfx(events, fps, unders, UNDER_DB), words)


def _append_cut(cuts, point, duration):
    point = round(float(point), 3)
    if 0.35 < point < duration - 0.2 and point > cuts[-1] + 0.45:
        cuts.append(point)


def plan_timeline(words, source_path, words_path, theme_mode="dark", title=None, keyword=None,
                  stage_plan=None, music_path=None, music=True, emphasis=None, theme_path=None,
                  width=1080, height=1920, fps=30, seed_path=None):
    if not words:
        raise ValueError("planning needs word timings")
    if set(LIBRARY) != set(MOTIFS) - {"doc_fan", "hero_board"}:
        raise ValueError("motif rotation is missing a library entry")
    theme, _colors, mode, path = load_theme(theme_mode, theme_path)
    ordered = sorted(words, key=lambda word: float(word["start"]))
    duration = round(float(ordered[-1]["end"]), 3)
    starts = [float(word["start"]) for word in ordered if 0.05 < float(word["start"]) < duration - 0.05]
    keyword = plain_text(keyword or theme["content"]["default_keyword"])
    styles = {str(key).lower(): value for key, value in (emphasis or {}).items()}
    styles.setdefault(keyword.lower(), "green")
    for token in NEGATIVE:
        styles.setdefault(token, "amber")
    if isinstance(stage_plan, dict) and stage_plan.get("beats"):
        from kallaway_beats import plan_authored
        return plan_authored(
            ordered, source_path, words_path, theme, mode, path, keyword, stage_plan,
            music_path=music_path, music=music, emphasis=styles,
            width=width, height=height, fps=fps)
    if any(_token(word) == "works" for word in ordered) and any(_token(word) in {"no", "not", "never"} for word in ordered):
        styles.setdefault("works", "amber")
    seed = video_seed(source_path if seed_path is None else seed_path)
    plan_mode, plan_entries = parse_stage_plan(stage_plan)

    def boundary(target, low, high, fallback):
        if not starts:
            return fallback
        return _snap(target, starts, low, high)

    if duration >= 8:
        first = boundary(1.05, 0.7, 1.7, 1.05)
        second = boundary(2.1, first + 0.55, 2.75, first + 0.9)
        full_at = boundary(3.0, max(2.3, second + 0.4), 3.9, max(second + 0.7, 3.0))
        cta_at = boundary(duration - 3.1, max(full_at + 1.4, duration - 4.8), duration - 1.6, duration - 3.0)
    elif duration >= 5:
        first = boundary(duration * 0.22, 0.45, duration * 0.34, duration * 0.22)
        second = None
        full_at = boundary(min(3.0, duration * 0.42), first + 0.45, duration * 0.58, duration * 0.42)
        cta_at = boundary(duration * 0.72, full_at + 0.7, duration - 0.9, duration * 0.72)
    else:
        first = second = None
        full_at = max(0.8, duration * 0.36)
        cta_at = max(full_at + 0.6, duration * 0.68)

    cuts = [0.0]
    if first:
        _append_cut(cuts, first, duration)
    if second:
        _append_cut(cuts, second, duration)
    if full_at <= cuts[-1] + 0.45:
        full_at = min(duration * 0.55, cuts[-1] + 0.8)
    _append_cut(cuts, full_at, duration)
    full_at = cuts[-1]
    cursor = full_at
    while cursor < cta_at - 1.5:
        nxt = boundary(cursor + 2.6, cursor + 1.55, min(cta_at - 0.45, cursor + 4.5), cursor + 2.6)
        if nxt <= cursor + 0.45 or nxt >= cta_at - 0.35:
            break
        cuts.append(round(nxt, 3))
        cursor = nxt
    if cta_at > cuts[-1] + 0.5 and cta_at < duration - 0.35:
        cuts.append(round(cta_at, 3))
    cuts.append(duration)
    # Drop a post-hook boundary that would leave a shot under 1.2s. The previous
    # shot simply holds until the next real cut, including the CTA.
    held = [cuts[0]]
    for point in cuts[1:-1]:
        if point - held[-1] < 1.2 and held[-1] >= full_at - 0.02:
            continue
        held.append(point)
    held.append(cuts[-1])
    cuts = held

    shots = []
    opened_full = False
    split_index = 0
    full_index = 0
    roles = []
    previous_motif = None
    for index in range(len(cuts) - 1):
        start, end = cuts[index], cuts[index + 1]
        is_last = index == len(cuts) - 2
        is_hook = not opened_full and not is_last and start < full_at - 0.02
        if is_last:
            layout, role = "split", "cta"
        elif is_hook:
            layout, role = "split", "hook"
        elif not opened_full:
            layout, role = "punch_in", "body"
            opened_full = True
        elif shots[-1]["layout"] == "split":
            layout, role = ("full" if full_index % 2 else "punch_in"), "body"
            full_index += 1
        else:
            layout, role = "split", "body"
        shot = {"id": f"shot-{index:02d}", "start": round(start, 3), "end": round(end, 3), "layout": layout}
        if layout == "split":
            covered = _slot_words(shot, ordered)
            if role == "cta":
                motif = "doc_fan"
            else:
                motif = _rotate(seed, split_index, previous_motif)
            shot["crop"] = "wide"
            shot["stage"] = _stage_for(motif, covered, theme, keyword)
            previous_motif = motif
            split_index += 1
        shots.append(shot)
        roles.append(role)

    body_slots = [shot for shot, role in zip(shots, roles) if shot["layout"] == "split" and role != "cta"]
    claimed = set()
    if plan_mode == "order":
        if len(plan_entries) > len(body_slots):
            raise ValueError(
                f"stage plan has {len(plan_entries)} stages and this cut has {len(body_slots)} split slots before the CTA")
        for shot, entry in zip(body_slots, plan_entries):
            _apply_entry(shot, entry, _slot_words(shot, ordered), theme, keyword)
            claimed.add(id(shot))
    elif plan_mode == "match":
        for entry in plan_entries:
            shot = _match_entry(entry, body_slots, ordered, claimed)
            _apply_entry(shot, entry, _slot_words(shot, ordered), theme, keyword)
            claimed.add(id(shot))

    # An authored motif can land on the same graphic as a neighbor the rotation
    # already chose. Nudge only the unauthored side so two splits never repeat.
    body = [(shot, role) for shot, role in zip(shots, roles) if shot["layout"] == "split"]
    for index, (shot, role) in enumerate(body):
        if role == "cta" or shot.get("stage_authored"):
            continue
        blocked = set()
        if index:
            blocked.add(body[index - 1][0]["stage"]["motif"])
        if index + 1 < len(body):
            blocked.add(body[index + 1][0]["stage"]["motif"])
        if shot["stage"]["motif"] not in blocked:
            continue
        replacement = _rotate_away(seed, index + 1, blocked)
        shot["stage"] = _stage_for(replacement, _slot_words(shot, ordered), theme, keyword)

    for shot in shots:
        shot.pop("stage_authored", None)

    title_text = plain_text(title or _title_case(" ".join(_token(word) for word in ordered[:3])))
    emphasis_words = [word for word in title_text.split() if styles.get(word.lower()) == "green"]
    if not emphasis_words and " " in title_text:
        emphasis_words = [title_text.split()[-1]]
    full_start = next(shot["start"] for shot in shots if shot["layout"] in {"full", "punch_in"})
    last = shots[-1]
    headers = [
        {"start": 0, "end": round(full_start, 3), "text": title_text,
         "emphasis": emphasis_words, "variant": "headline"},
        {"start": round(last["start"], 3), "end": round(last["end"], 3),
         "text": plain_text(theme["content"]["cta_template"].format(keyword=keyword)),
         "emphasis": [keyword], "variant": "headline",
         "sub": plain_text(theme["content"]["lead_magnet_title"])},
    ]
    under = float(theme["audio"]["music_under_db"])
    music_tracks = []
    if music and music_path:
        music_tracks.append({
            "path": music_path, "start": 0, "end": duration,
            "source_start": 0, "gain": round(10 ** (-under / 20), 5),
        })
    stage_slots = []
    for shot, role in zip(shots, roles):
        if shot["layout"] != "split":
            continue
        covered = _slot_words(shot, ordered)
        covered_ids = {id(word) for word in covered}
        indexes = [index for index, word in enumerate(ordered) if id(word) in covered_ids]
        stage_slots.append({
            "id": shot["id"],
            "role": role,
            "start": shot["start"],
            "end": shot["end"],
            "spoken": _spoken(covered),
            "word_range": [indexes[0], indexes[-1] + 1] if indexes else None,
            "motif": shot["stage"]["motif"],
            "authored": role != "cta" and id(shot) in claimed,
        })
    from kallaway_beats import apply_emphasis_punches
    shots = apply_emphasis_punches(
        shots, ordered, styles,
        float(theme["layout"].get("full_scale", 0.90)),
        float(theme["layout"].get("punch_step", 1.12)))
    sfx = _cover_sfx(shots, ordered, styles, theme.get("sfx_under_db") or {}, fps, headers)
    return {
        "style": "kallaway",
        "theme": theme["id"],
        "theme_mode": mode,
        "theme_path": str(path),
        "title": title_text,
        "cta": {"keyword": keyword, "lead_magnet": theme["content"]["lead_magnet_title"]},
        "output": {"width": width, "height": height, "fps": fps},
        "source": {"path": source_path, "object_position": theme["layout"]["object_position"],
                   "segments": [{"start": 0, "end": duration}]},
        "words_path": words_path,
        "motif_seed": seed,
        "audio_policy": {
            "profile": "kallaway",
            "music_required": bool(music and music_path),
            "music_under_db": under,
            "voice_lufs": theme["audio"]["voice_lufs"],
            "user_opt_out": None if music and music_path else "Music bed off for this reel.",
        },
        "music": music_tracks,
        "headers": headers,
        "shots": shots,
        "stage_slots": stage_slots,
        "captions": {
            "max_words": 1, "uppercase": False, "word_styles": styles,
            "phrases": caption_phrases(ordered, styles), "omit_terminal_punctuation": True,
        },
        "sfx": sfx,
        "sfx_log": sfx_placement_rows(sfx),
    }


def _read_words(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    if "words" in data:
        return data["words"]
    return [word for segment in data.get("segments", []) for word in segment.get("words", [])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--words", required=True, help="Word timings. Use the tightened words when you have them.")
    parser.add_argument("--source", required=True, help="Video path. Its string seeds the automatic motif rotation.")
    parser.add_argument("--stage-plan", help="JSON list or kallaway-stage-plan/v1 object.")
    parser.add_argument("--cta-keyword", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--theme-mode", choices=["dark", "light"], default="dark")
    parser.add_argument("--theme", default=None)
    parser.add_argument("--emphasis", default=None, help="JSON map of word to normal|marker|green|amber")
    parser.add_argument("--slots", action="store_true", help="Print split-shot slots instead of the full timeline.")
    parser.add_argument("--out", help="Write the timeline JSON here. Prints it when omitted.")
    args = parser.parse_args()
    stage_plan = json.loads(Path(args.stage_plan).read_text()) if args.stage_plan else None
    emphasis = json.loads(args.emphasis) if args.emphasis else None
    timeline = plan_timeline(
        _read_words(args.words), args.source, str(Path(args.words).resolve()),
        theme_mode=args.theme_mode, title=args.title, keyword=args.cta_keyword,
        stage_plan=stage_plan, music=False, emphasis=emphasis, theme_path=args.theme)
    payload = timeline["stage_slots"] if args.slots else timeline
    text = json.dumps(payload, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
