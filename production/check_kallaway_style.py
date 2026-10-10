#!/usr/bin/env python3
"""Check a Kallaway-style timeline for hard cuts, caption length, shot bounds, SFX, ending, and brand tokens.

This does not judge whether the reel is good. It checks the style contract.
"""
import argparse
import json
import re
import sys
from pathlib import Path

EDITOR = Path(__file__).resolve().parent / "editor"
sys.path.insert(0, str(EDITOR))
from kallaway_matte import inspect_matte  # noqa: E402
from kallaway_motifs import ENTRANCE_SECONDS, motion_window, stage_events, stage_windows  # noqa: E402
from kallaway_targets import box_in_viewport  # noqa: E402
from kallaway_style import DEFAULT_THEME, load_theme  # noqa: E402

FORBIDDEN = {"#e60000", "#ff2a2a", "#ff0000", "#d33633", "#00e676", "#0e0e0e"}


def _walk_strings(value, found):
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _walk_strings(item, found)
    elif isinstance(value, list):
        for item in value:
            _walk_strings(item, found)


def _boxes_hit(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _colors_in(html):
    return {f"#{match.group(1).lower()}" for match in re.finditer(r"#([0-9A-Fa-f]{6})(?![0-9A-Fa-fA-Z_])", html)}


def scene_cuts(video, threshold=0.30):
    """Hard-cut times in a rendered file. Ordinary caption motion stays under this."""
    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video),
         "-filter:v", f"select='gt(scene,{float(threshold):.3f})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True)
    times = []
    for line in result.stderr.splitlines():
        if "pts_time:" not in line:
            continue
        token = line.split("pts_time:", 1)[1].split()[0]
        try:
            times.append(float(token))
        except ValueError:
            continue
    return times


def short_spans(cuts, duration, minimum=0.5, fps=30):
    """Spans between output scene cuts that are under ``minimum`` seconds."""
    tolerance = 0.5 / float(fps or 30)
    edges = [0.0]
    for moment in sorted(float(item) for item in cuts or []):
        if moment <= edges[-1] + tolerance or moment >= float(duration) - tolerance:
            continue
        edges.append(moment)
    edges.append(float(duration))
    found = []
    for begin, end in zip(edges, edges[1:]):
        if end - begin < float(minimum) - tolerance:
            found.append({"start": round(begin, 3), "end": round(end, 3), "seconds": round(end - begin, 3)})
    return found


def _probe_duration(video):
    import subprocess
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True)
    return float(probe.stdout.strip() or 0)


def insert_spans_from_diffs(diffs, fps=30, prev_min=20.0, next_min=25.0, hold_max=10.0):
    """Spans where a cut in and a cut out land within two frames, then the picture holds.

    ``diffs[i]`` is the mean absolute difference between frame i and frame i+1.
    A head turn differs from both neighbors and keeps moving. A stray take is a
    second cut one or two frames later, and the frame after that cut holds.
    """
    step = 1.0 / float(fps)
    spans = []
    count = len(diffs) + 1
    index = 1
    while index < count - 2:
        entered = diffs[index - 1] >= prev_min
        left = diffs[index] >= next_min and diffs[index + 1] < hold_max
        if entered and left:
            spans.append((round(index * step, 4), round((index + 1) * step, 4)))
            index += 2
            continue
        two = (
            index < count - 3
            and entered
            and diffs[index] < hold_max
            and diffs[index + 1] >= next_min
            and diffs[index + 2] < hold_max
        )
        if two:
            spans.append((round(index * step, 4), round((index + 2) * step, 4)))
            index += 3
            continue
        index += 1
    return spans


def find_insert_spans(video, prev_min=20.0, next_min=25.0, hold_max=10.0, fps=30):
    """One- and two-frame takes measured on decoded output frames."""
    import subprocess
    import numpy as np
    duration = _probe_duration(video)
    if duration <= 0:
        return []
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", "fps=30,scale=180:320", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        stderr=subprocess.DEVNULL)
    frame = 180 * 320
    count = len(raw) // frame
    if count < 4:
        return []
    frames = [np.frombuffer(raw[i * frame:(i + 1) * frame], dtype=np.uint8) for i in range(count)]
    diffs = [
        float(np.mean(np.abs(frames[index + 1].astype(np.float32) - frames[index].astype(np.float32))))
        for index in range(count - 1)
    ]
    return insert_spans_from_diffs(diffs, fps=fps, prev_min=prev_min, next_min=next_min, hold_max=hold_max)


def shift_moment(moment, spans):
    """Move a timestamp left by the spans cut out of the picture before it."""
    moment = float(moment)
    lost = 0.0
    for start, end in spans:
        if end <= moment:
            lost += end - start
        elif start < moment:
            return round(start - lost, 4)
        else:
            break
    return round(moment - lost, 4)


def punch_tight_spans(ranges, spans):
    """Drop tightened-clock spans from the source ranges that were concatenated to build them."""
    spans = sorted((float(start), float(end)) for start, end in spans)
    out = []
    cursor = 0.0
    index = 0
    for begin, end in ranges:
        begin, end = float(begin), float(end)
        length = end - begin
        local = []
        while index < len(spans) and spans[index][0] < cursor + length - 1e-4:
            start, stop = spans[index]
            if stop <= cursor + 1e-4:
                index += 1
                continue
            local_start = max(0.0, start - cursor)
            local_end = min(length, stop - cursor)
            if local_end > local_start + 1e-4:
                local.append((local_start, local_end))
            if stop <= cursor + length + 1e-4:
                index += 1
            else:
                break
        pos = 0.0
        for local_start, local_end in local:
            if local_start > pos + 0.005:
                out.append((round(begin + pos, 4), round(begin + local_start, 4)))
            pos = local_end
        if length > pos + 0.005:
            out.append((round(begin + pos, 4), round(end, 4)))
        cursor += length
    return out


def output_short_shots(video, minimum=0.5, threshold=0.30):
    """Fail a rendered shot under 0.5 s. This reads the output frames, not the plan."""
    duration = _probe_duration(video)
    classic = short_spans(scene_cuts(video, threshold), duration, minimum=minimum)
    inserts = [
        {"start": start, "end": end, "seconds": round(end - start, 3), "kind": "insert"}
        for start, end in find_insert_spans(video)
        if end - start < float(minimum)
    ]
    return classic + inserts


def check(timeline_path, words_path=None, project=None):
    errors, warnings = [], []
    path = Path(timeline_path)
    data = json.loads(path.read_text())
    if data.get("style") != "kallaway":
        errors.append("style: timeline is not a kallaway edit")
        return {"ok": False, "errors": errors, "warnings": warnings}
    theme_path = data.get("theme_path") or DEFAULT_THEME
    if data.get("theme") == "ai-builder-school" and not Path(theme_path).is_file():
        theme_path = DEFAULT_THEME
    theme, colors, mode, _resolved = load_theme(data.get("theme_mode"), theme_path)
    if data.get("theme") not in (None, theme["id"]):
        errors.append(f"theme: {data.get('theme')} does not match preset {theme['id']}")
    strings = []
    _walk_strings(data, strings)
    for text in strings:
        if "\u2014" in text or "\u2013" in text:
            errors.append(f"voice: on-screen text contains an em dash or en dash: {text[:80]}")
            break

    shots = data.get("shots") or []
    if not shots:
        errors.append("shots: timeline has no shots")
    fps = float(data.get("output", {}).get("fps", 30))
    tolerance = 0.5 / fps + 1e-3
    duration = shots[-1]["end"] if shots else 0
    if shots and abs(float(shots[0]["start"])) > tolerance:
        errors.append("shots: first shot must start at 0")
    if shots and shots[0].get("layout") != "split":
        errors.append("hook: first shot must be the split layout")
    for index, shot in enumerate(shots):
        for banned in ("transition", "crossfade", "fade", "whip", "slide"):
            if banned in shot:
                errors.append(f"shots:{shot.get('id', index)}: {banned}={shot.get(banned)} is not a hard cut")
        layout = shot.get("layout")
        if layout not in {"split", "full", "punch_in"}:
            errors.append(f"shots:{shot.get('id', index)}: layout {layout} is outside the three camera states")
        length = float(shot["end"]) - float(shot["start"])
        if length > 5.5 + tolerance:
            errors.append(f"shots:{shot.get('id', index)}: {length:.2f}s is longer than 5.5s")
        elif length < 0.5 - tolerance:
            errors.append(f"shots:{shot.get('id', index)}: {length:.2f}s is shorter than 0.5s")
        elif float(shot["start"]) >= 3.2 and index != len(shots) - 1 and not 1.15 <= length <= 5.05:
            warnings.append(f"shots:{shot.get('id', index)}: body shot is {length:.2f}s; expected about 2-5s")
        if index and abs(float(shot["start"]) - float(shots[index - 1]["end"])) > tolerance:
            errors.append(f"shots:{shot.get('id', index)}: gap or overlap at the layout cut")
        if layout == "split" and not shot.get("stage"):
            errors.append(f"shots:{shot.get('id', index)}: split shot has no graphic stage")
    if duration >= 6 and data.get("structure") == "authored":
        fulls = [shot for shot in shots if shot.get("layout") in {"full", "punch_in"}]
        if not fulls or min(float(shot["start"]) for shot in fulls) > 8.0:
            errors.append("hook: authored reel has no full-screen or punch-in by 8.0s")
        changed = False
        for shot in shots:
            if float(shot["start"]) <= 0.05 or float(shot["start"]) > 4.0:
                continue
            if shot.get("layout") != shots[0].get("layout"):
                changed = True
            elif shot.get("stage") and shots[0].get("stage") and shot["stage"].get("motif") != shots[0]["stage"].get("motif"):
                changed = True
        if not changed:
            errors.append("hook: authored reel does not change layout or motif by 4.0s")
    elif duration >= 6:
        fulls = [shot for shot in shots if shot.get("layout") in {"full", "punch_in"}]
        if not fulls or not any(2.2 <= float(shot["start"]) <= 4.0 for shot in fulls):
            errors.append("hook: no hard cut to full-screen or punch-in between 2.2s and 4.0s")
    elif not any(shot.get("layout") in {"full", "punch_in"} for shot in shots):
        errors.append("hook: reel never cuts to a full-screen camera state")

    captions = data.get("captions", {})
    phrases = captions.get("phrases") or []
    if phrases:
        for phrase in phrases:
            count = phrase["word_range"][1] - phrase["word_range"][0]
            if count > 3:
                errors.append(f"captions: a group has {count} words")
    elif int(captions.get("max_words", 1)) > 3:
        warnings.append("captions: max_words is above 3 and no explicit phrases were checked")
    if captions.get("uppercase") is True:
        errors.append("captions: Kallaway captions stay lowercase")

    words = None
    word_file = Path(words_path) if words_path else None
    if word_file is None and data.get("words_path"):
        candidate = Path(data["words_path"])
        word_file = candidate if candidate.is_file() else path.parent / candidate
    if word_file and Path(word_file).is_file():
        payload = json.loads(Path(word_file).read_text())
        words = payload if isinstance(payload, list) else payload.get("words")
    if words:
        end = float(words[-1]["end"])
        if abs(end - float(shots[-1]["end"])) > 0.12:
            errors.append(f"ending: timeline ends at {shots[-1]['end']} but the last word ends at {end}")
        if float(shots[-1]["end"]) > end + 0.12:
            errors.append("ending: timeline continues after the final syllable")
    else:
        warnings.append("ending: no word file supplied, so the final-syllable cut was not measured")

    music = data.get("music") or []
    # Brandon adds the bed himself. A missing track is the default, not an error or a warning.
    for track in music:
        envelope = track.get("envelope") or []
        if len(envelope) >= 2 and float(envelope[-1].get("v", 1)) == 0:
            span = float(envelope[-1]["t"]) - float(envelope[-2]["t"])
            if span > 0.2:
                errors.append("ending: music fades out instead of cutting on the last word")

    for shot in shots:
        for motif, start, end, stage in stage_windows(shot):
            if motif == "highlight_box":
                pops = [event for event in stage_events(motif, start, end, stage) if event["kind"] == "pop"]
                if pops and float(pops[0]["at"]) + 0.001 < start + ENTRANCE_SECONDS:
                    errors.append(
                        f"callout: highlight on {shot.get('id', motif)} starts at {pops[0]['at']} "
                        f"during the card entrance that ends at {round(start + ENTRANCE_SECONDS, 3)}")
            if motif not in {"phone_frame", "broll_card"}:
                continue
            stored = stage.get("motion") or {}
            if stored:
                entrance_end = float(stored.get("entrance_end", start + ENTRANCE_SECONDS))
                scroll_end = stored.get("scroll_end")
            else:
                window = motion_window(stage, start, end)
                entrance_end = window["entrance_end"]
                scroll_end = window["scroll_end"]
            for key in ("callout", "highlight"):
                block = stage.get(key)
                if not isinstance(block, dict) or block.get("at") is None:
                    continue
                visible = float(block["at"])
                if visible + 0.001 < entrance_end:
                    errors.append(
                        f"callout: {key} on {shot.get('id', motif)} starts at {visible} "
                        f"during the frame entrance that ends at {entrance_end}")
                if scroll_end is not None and visible + 0.001 < float(scroll_end):
                    errors.append(
                        f"callout: {key} on {shot.get('id', motif)} starts at {visible} "
                        f"while the screenshot is still scrolling until {scroll_end}")
                if not box_in_viewport(block, stage.get("frame")):
                    errors.append(
                        f"callout: {key} on {shot.get('id', motif)} is outside the phone "
                        "after the pan settles")

    sfx = data.get("sfx") or []
    for shot in shots:
        for motif, start, end, stage in stage_windows(shot):
            for event in stage_events(motif, start, end, stage):
                if not any(abs(float(item.get("at", -99)) - float(event["at"])) <= 0.12 for item in sfx):
                    errors.append(f"sfx: no sound within 0.12s of {motif} at {event['at']}")
                    break
    if shots and not sfx:
        errors.append("sfx: no sound effects were scheduled")
    from kallaway_plan import gap_at, word_gaps
    gaps = word_gaps(words or [])
    played = [cue for cue in sfx if not cue.get("mute")]
    logged = data.get("sfx_log")
    if played and not isinstance(logged, list):
        errors.append("sfx: placement log is missing; gate G9 needs time, pack file, and what it lands on")
    for cue in played:
        label = cue.get("label") or cue.get("kind") or "sfx"
        landing = str(cue.get("lands_on") or "").strip()
        heard = float(cue.get("sound_at", cue.get("at", 0)))
        if not landing:
            errors.append(f"sfx: {label} at {heard:.3f}s has no visual to land on")
        covered = gap_at(heard, gaps) if words else None
        visual = float(cue.get("at", heard))
        lead = visual - heard
        whoosh_lead = (
            cue.get("kind") in {"whoosh", "riser"}
            and 0.05 <= lead <= 0.16
            and (gap_at(visual, gaps) is None if words else True)
        )
        if covered is not None and not whoosh_lead:
            errors.append(
                f"sfx: {label} at {heard:.3f}s covers the pause after {covered.get('word')}; "
                "pauses come from word alignment and stay clear of SFX")
        if isinstance(logged, list):
            hit = any(
                abs(float(row.get("time", -99)) - heard) <= 0.001
                and str(row.get("lands_on") or "") == landing
                and str(row.get("file") or "")
                for row in logged
            )
            if landing and not hit:
                errors.append(
                    f"sfx: placement log has no row for {label} at {heard:.3f}s on {landing}")
    tighten_ranges = data.get("source_ranges") or []
    source_words = data.get("source_words") or []
    if tighten_ranges and source_words:
        from kallaway_audio import interior_cuts
        for hit in interior_cuts(tighten_ranges, source_words):
            errors.append(
                f"cut: keep range {hit['edge']} at {hit['at']}s falls inside \"{hit['word']}\"")
    for join in data.get("joins") or []:
        if join.get("ok") is False:
            errors.append(
                f"join: outgoing tail at {join.get('at')}s ({join.get('word')}) is "
                f"{join.get('over_db')} dB above the noise floor; the cut clips the word")

    cta = data.get("cta") or {}
    headers = data.get("headers") or []
    if not headers:
        errors.append("headers: no title header")
    elif float(headers[0].get("start", 1)) > 0.05:
        errors.append("hook: title header does not start on frame 1")
    frame_h = float(data.get("output", {}).get("height", 1920))
    frame_w = float(data.get("output", {}).get("width", 1080))
    title_top = float(theme["layout"]["title_top"]) * frame_h
    stage_top = float(theme["layout"]["stage_top"]) * frame_h
    stage_left = float(theme["layout"]["stage_left"]) * frame_w
    stage_right = stage_left + float(theme["layout"]["stage_width"]) * frame_w
    for index, header in enumerate(headers):
        lines = header.get("lines") or ([header.get("text")] if header.get("text") else [])
        size = float(header.get("size") or theme["layout"].get("title_font_px") or 64)
        bottom = float(header.get("bottom") or (title_top + max(1, len(lines)) * size * 1.05))
        if bottom > 240.5:
            errors.append(f"title: header {index} ends at y {bottom:.0f}, below the y 240 limit")
        if bottom > stage_top - 4:
            errors.append(f"title: header {index} overlaps the stage (title bottom {bottom:.0f}, stage top {stage_top:.0f})")
    for shot in shots:
        if shot.get("layout") != "split":
            continue
        stage = shot.get("stage") or {}
        chip = stage.get("chip")
        if isinstance(chip, dict) and chip.get("text") and stage.get("motif") == "phone_frame":
            if chip.get("place") != "bottom":
                errors.append(f"collision: phone chip on {shot.get('id')} covers the top of the mock")
        callout = stage.get("callout") if isinstance(stage.get("callout"), dict) else None
        highlight = stage.get("highlight") if isinstance(stage.get("highlight"), dict) else None
        if callout and highlight:
            ax, ay, aw, ah = (float(callout.get(key, 0)) for key in ("x", "y", "w", "h"))
            bx, by, bw, bh = (float(highlight.get(key, 0)) for key in ("x", "y", "w", "h"))
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                errors.append(f"collision: callout and highlight overlap on {shot.get('id')}")
    del stage_right
    layout = theme["layout"]
    for key in ("wide_scale", "tight_scale", "full_scale", "punch_scale"):
        if float(layout.get(key, 1)) < 0.999:
            errors.append(f"fill: {key} is {layout.get(key)}; the face must fill the card or the frame")
    popout = (data.get("source") or {}).get("popout") or {}
    placed = bool(popout.get("face_px"))
    for shot in shots:
        scale = shot.get("scale")
        if scale is None or float(scale) >= 0.999:
            continue
        if shot.get("layout") == "split" and placed:
            continue
        errors.append(
            f"fill: {shot.get('id')} scale {scale} letterboxes the face; "
            "full bleed stays at scale 1, and a split shrink needs the blurred plate")
    if placed:
        face_px = float(popout["face_px"])
        pop_px = float(popout.get("pop_px") or popout.get("median_above_px") or 0)
        if face_px > 230.5:
            errors.append(f"face: split face is {face_px:.0f}px; the target is 200-230")
        if pop_px < 49 or pop_px > 101:
            errors.append(f"face: crown pop is {pop_px:.0f}px; the band is 50-100")
    from kallaway_motifs import hero_phone_box
    stage_w = float(layout["stage_width"]) * frame_w
    stage_h = float(layout["stage_height"]) * frame_h
    phone = hero_phone_box(stage_w, stage_h)
    if phone["top"] < 0 or phone["top"] + phone["height"] > stage_h - 40:
        errors.append(
            f"phone: the handset is cropped (top {phone['top']}, height {phone['height']}, stage {stage_h:.0f})")
    if phone["width"] > stage_w + 1:
        errors.append(f"phone: the handset is wider than the stage ({phone['width']} > {stage_w:.0f})")
    if phone["width"] < stage_w * 0.65 - 1:
        errors.append(
            f"phone: the handset is {phone['width']}px, under 65% of the {stage_w:.0f}px stage")
    if abs((phone["left"] + phone["width"] / 2.0) - stage_w / 2.0) > 2:
        errors.append(f"phone: the handset is off center (left {phone['left']})")
    style_at = (data.get("captions") or {}).get("style_at") or []
    if words and style_at and len(style_at) == len(words):
        from kallaway_beats import _sentence_spans
        for begin, end in _sentence_spans(words):
            colored = [
                index for index in range(begin, end)
                if style_at[index] in {"marker", "green", "amber"}
            ]
            if len(colored) > 1:
                errors.append(
                    f"emphasis: sentence at {words[begin].get('start')}s has {len(colored)} colored words")
    if words and len(words) > 4:
        gaps = []
        mids = []
        for prev, word in zip(words, words[1:]):
            gap = float(word["start"]) - float(prev["end"])
            gaps.append(gap)
            text = str(prev.get("word") or prev.get("text") or "").rstrip()
            if not text.endswith((".", "!", "?")):
                mids.append((gap, prev))
        tight = sum(gap <= 0.05 for gap in gaps) / len(gaps) > 0.6
        if tight:
            for gap, prev in mids:
                if gap > 0.045:
                    errors.append(
                        f"gap: mid-phrase pause after {prev.get('word')} is {gap * 1000:.0f} ms; "
                        "the cap is 40 ms")
    keyword = str(cta.get("keyword") or "")
    closing = " ".join(str(header.get("text", "")) for header in headers).lower()
    # A reach reel sets cta.required false and ends on the last word with no comment ask.
    if cta.get("required", not cta.get("omit", False)):
        if "comment" not in closing:
            errors.append("cta: no Comment header on the ending")
        if keyword and keyword.lower() not in closing:
            errors.append(f"cta: header does not show the keyword {keyword}")

    html_path = None
    if project:
        candidate = Path(project) / "index.html"
        if candidate.is_file():
            html_path = candidate
    if html_path:
        html = html_path.read_text()
        allowed = set()
        for mode_colors in theme["modes"].values():
            for value in mode_colors.values():
                if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                    allowed.add(value.lower())
        used = _colors_in(html)
        stray = sorted(color for color in used if color not in allowed)
        if stray:
            errors.append(f"brand: colors outside the preset: {', '.join(stray[:12])}")
        banned = sorted(color for color in used if color in FORBIDDEN)
        if banned:
            errors.append(f"brand: Kallaway palette colors are still in the render: {', '.join(banned)}")
        for token, label in ((colors["background"], "background"), (colors["accent"], "accent"), (colors["text"], "text")):
            if token.lower() not in used:
                errors.append(f"brand: {label} {token} is not used in the composition")
        for family in ("Permanent Marker", "Inter", "IBM Plex Mono"):
            if family not in html:
                errors.append(f"brand: font {family} is not used in the composition")
        if re.search(r"fromTo\([^;]*\{[^}]*opacity:0[,}]", html):
            errors.append("entrance: a graphic fades in; use a pop or a slide")
    else:
        warnings.append("brand: no built index.html was scanned for palette and fonts")

    source = data.get("source") or {}
    matte_raw = source.get("matte_mask") or source.get("matte")
    if matte_raw:
        matte_path = Path(matte_raw)
        if not matte_path.is_absolute():
            matte_path = path.parent / matte_path
        if not matte_path.is_file():
            errors.append(f"matte: person matte is missing ({matte_path.name})")
        else:
            try:
                errors.extend(inspect_matte(matte_path))
            except Exception as exc:
                errors.append(f"matte: could not read the person matte ({exc})")
        if html_path and "speaker-pop" not in html_path.read_text():
            errors.append("popout: the split composite is missing the head pop-out layer")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "theme": theme["id"], "theme_mode": mode}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--words", type=Path)
    parser.add_argument("--project", type=Path, help="Composition directory with index.html")
    args = parser.parse_args()
    report = check(args.timeline, args.words, args.project)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
