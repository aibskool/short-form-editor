"""Graphic-stage motifs for the Kallaway split layout, drawn in the active brand theme."""
import html
import json

from icons import icon_svg


MOTIFS = (
    "thumbnail_grid", "phone_frame", "broll_card", "numbered_list", "line_chart",
    "bar_chart", "counter", "highlight_box", "hand_circle", "doc_fan", "typing_ui",
    "mind_map", "logo_row", "quote_card", "offer_pair", "flow_line", "pill",
    "cursor_mock", "vacuum_merge", "state_swap",
)


def _esc(value):
    return html.escape(str(value), quote=True)


def _is_video_url(url):
    """Screen recordings play in the phone or card. Stills stay images."""
    if not url:
        return False
    path = str(url).lower().split("?", 1)[0]
    return path.endswith((".mp4", ".mov", ".webm", ".m4v"))


def _media_tag(ident, media_url, start, end, fit, sat, track_index, stage):
    style = (f"position:absolute;left:0;top:0;width:100%;height:100%;object-fit:{fit};"
             f"object-position:center;filter:saturate({sat:.3f})")
    if not _is_video_url(media_url):
        return f'<img id="{ident}-img" src="{_esc(media_url)}" alt="" style="{style}">'
    # The video carries its own clip timing. The stage section must not, or
    # HyperFrames rejects a video nested in a timed element.
    offset = float(stage.get("media_start") or 0)
    rate = float(stage.get("playback_rate") or 1)
    rate_attr = f' data-playback-rate="{rate:.3f}"' if abs(rate - 1.0) > 0.01 else ""
    return (
        f'<video id="{ident}-img" class="clip" src="{_esc(media_url)}" '
        f'data-start="{float(start):.3f}" data-duration="{max(0.04, float(end) - float(start)):.3f}" '
        f'data-media-start="{offset:.3f}"{rate_attr} data-track-index="{int(track_index)}" '
        f'muted playsinline style="{style}"></video>'
    )


def _rgba(hex_color, alpha):
    raw = hex_color.lstrip("#")
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def _times(start, end, count, window=1.25):
    count = max(1, int(count))
    span = min(window, max(0.24, (end - start) * 0.72))
    if count == 1:
        return [round(start, 3)]
    step = span / (count - 1)
    return [round(min(start + index * step, end - 0.05), 3) for index in range(count)]


def _clamp(moment, start, end):
    """Keep a cue inside the shot. Events must start at or after `start` and finish before `end`."""
    moment = float(moment)
    latest = max(start, end - 0.04)
    return round(min(max(moment, start), latest), 3)


# The phone/card slide is 0.4s. A marker stroke is a short hand-drawn sweep.
ENTRANCE_SECONDS = 0.4
DRAW_SECONDS = 0.36
MIN_SCROLL_SECONDS = 0.35
HAND_CIRCLE = "M48 7 C76 2, 99 22, 95 49 C98 76, 76 99, 49 96 C20 99, 1 74, 6 48 C2 20, 22 3, 48 7"
HAND_CIRCLE_LENGTH = 320


def _cue_time(block):
    if not isinstance(block, dict):
        return None
    if block.get("cue_at") is not None:
        return float(block["cue_at"])
    if block.get("at") is not None:
        return float(block["at"])
    return None


def hero_phone_box(stage_w, stage_h):
    """A centered handset at least 65% of the stage width, top bezel inside.

    A 9:19.5 phone at that width is taller than the stage. The frame then uses
    the full stage height so nothing is cropped at the top, and the recording
    is letterboxed inside the screen instead of being cut on the side.
    """
    stage_w, stage_h = float(stage_w), float(stage_h)
    chip_band = 58.0
    margin = 8.0
    usable_h = max(160.0, stage_h - chip_band - margin)
    max_w = max(120.0, stage_w - 2.0 * margin)
    phone_w = min(max_w, max(120.0, stage_w * 0.65))
    natural_h = phone_w * (19.5 / 9.0)
    phone_h = natural_h if natural_h <= usable_h else usable_h
    top = max(0.0, (stage_h - chip_band) - phone_h)
    pad = max(6, round(phone_w * 0.045))
    return {
        "screen": (float(phone_w - 2 * pad), float(phone_h - 2 * pad)),
        "width": round(phone_w),
        "height": round(phone_h),
        "left": round((stage_w - phone_w) / 2),
        "top": round(top),
        "pad": pad,
    }


def image_height_percent(stage):
    frame = stage.get("frame") or {}
    if frame.get("img_h"):
        return float(frame["img_h"])
    scroll = stage.get("scroll") or {}
    if not scroll:
        return 100.0
    if float(scroll.get("to", 0)) > 0.7:
        return 210.0
    return 168.0


def motion_window(stage, start, end):
    """Entrance end and scroll span for a phone or card.

    When a callout or highlight names a word, the pan starts with the shot and
    is shortened so it has settled by that word. A word that arrives before a
    minimum pan can finish leaves the draw waiting until the pan stops.
    """
    start, end = float(start), float(end)
    entrance_end = round(start + ENTRANCE_SECONDS, 3)
    scroll = stage.get("scroll") or {}
    img_h = image_height_percent(stage)
    if not scroll:
        return {"entrance_end": entrance_end, "scroll_start": None, "scroll_end": None, "img_h": img_h}
    cues = [moment for moment in (_cue_time(stage.get("callout")), _cue_time(stage.get("highlight"))) if moment is not None]
    cue = min(cues) if cues else None
    if cue is None:
        scroll_start = round(start + 0.12, 3)
        span = float(scroll["duration"]) if scroll.get("duration") is not None else max(0.45, end - start - 0.3)
    else:
        scroll_start = round(start, 3)
        natural = float(scroll["duration"]) if scroll.get("duration") is not None else max(0.45, min(1.15, (end - start) * 0.45))
        available = cue - scroll_start
        if available >= MIN_SCROLL_SECONDS:
            span = min(natural, available)
        else:
            span = MIN_SCROLL_SECONDS
    span = max(0.2, min(span, max(0.2, end - scroll_start - 0.05)))
    scroll_end = round(min(end - 0.02, scroll_start + span), 3)
    return {
        "entrance_end": entrance_end,
        "scroll_start": scroll_start,
        "scroll_end": scroll_end,
        "img_h": img_h,
    }


def draw_moment(cue, motion, end):
    """First moment a stroke may appear: after the entrance, the pan, the push, and on the word if the word is later."""
    settled = float(motion["entrance_end"])
    if motion.get("scroll_end") is not None:
        settled = max(settled, float(motion["scroll_end"]))
    if motion.get("push_end") is not None:
        settled = max(settled, float(motion["push_end"]))
    moment = max(settled, float(cue))
    latest = max(settled, float(end) - 0.05)
    return round(min(moment, latest), 3)


def resolve_annotations(stage, start, end, screen=None):
    """Write the draw time onto callout and highlight, and remember the pan window.

    `cue_at` keeps the spoken word. `at` becomes the moment the stroke starts.
    A `target_text` box is measured on the screenshot before the pan is aimed.
    A second call leaves an already resolved stage alone.
    """
    if stage.get("motion"):
        return stage["motion"]
    from kallaway_targets import place_targets
    place_targets(stage, screen)
    motion = motion_window(stage, start, end)
    if stage.get("motif") == "phone_frame":
        # The push starts once the slide has finished and ends before the circle.
        push_start = round(float(motion["entrance_end"]) + 0.02, 3)
        push_end = round(min(float(end) - 0.08, push_start + 0.38), 3)
        motion["push_start"] = push_start
        motion["push_end"] = push_end
    stage["motion"] = {
        "entrance_end": motion["entrance_end"],
        "scroll_start": motion["scroll_start"],
        "scroll_end": motion["scroll_end"],
        "push_start": motion.get("push_start"),
        "push_end": motion.get("push_end"),
    }
    for key in ("callout", "highlight"):
        block = stage.get(key)
        cue = _cue_time(block)
        if cue is None:
            continue
        if block.get("cue_at") is None:
            block["cue_at"] = round(cue, 3)
        block["at"] = draw_moment(block["cue_at"], motion, end)
        block["draw"] = DRAW_SECONDS
    return stage["motion"]


def screenshot_box(block, img_h, scroll_to):
    """Map a callout onto the screenshot, in percentages of that image.

    An image-space box (from target_text) is already in those percentages.
    A hand-authored box is a fraction of the settled phone window.
    """
    if block.get("space") == "image":
        return (float(block.get("x", 0)) * 100.0, float(block.get("y", 0)) * 100.0,
                float(block.get("w", 0.2)) * 100.0, float(block.get("h", 0.1)) * 100.0)
    extra = float(img_h) - 100.0
    to = float(scroll_to or 0)
    x = float(block.get("x", 0.3))
    y = float(block.get("y", 0.3))
    w = float(block.get("w", 0.28))
    h = float(block.get("h", 0.16))
    top = (y * 100.0 + to * extra) / float(img_h) * 100.0
    height = h * 100.0 / float(img_h) * 100.0
    return x * 100.0, top, w * 100.0, height


def _stage_chip(ident, stage):
    chip = stage.get("chip")
    if not chip:
        return ""
    if isinstance(chip, str):
        chip = {"text": chip}
    tone = chip.get("tone") if chip.get("tone") in {"green", "amber"} else "green"
    place = " bottom" if chip.get("place") == "bottom" else ""
    return f'<div id="{ident}-chip" class="stage-chip{place} {tone}">{_esc(chip.get("text", ""))}</div>'


def stage_windows(shot):
    """Motif windows on one shot: the split stage, then any timed overlay."""
    windows = []
    if shot.get("layout") == "split" and shot.get("stage"):
        stage = shot["stage"]
        windows.append((stage.get("motif"), float(shot["start"]), float(shot["end"]), stage))
    for overlay in shot.get("overlays") or []:
        windows.append((overlay.get("motif"), float(overlay["start"]), float(overlay["end"]), overlay))
    return windows


def stage_events(motif, start, end, stage=None):
    """SFX cues for one stage shot. Times match the entrance animations."""
    events = _stage_events(motif, start, end, stage)
    from kallaway_pack import decorate_events
    return decorate_events(motif, events, stage or {}, float(start), float(end))


def _stage_events(motif, start, end, stage=None):
    """SFX cues for one stage shot. Times match the entrance animations."""
    stage = stage or {}
    start, end = float(start), float(end)
    if motif not in MOTIFS:
        raise ValueError(f"unknown stage motif: {motif}")
    if motif == "thumbnail_grid":
        count = max(4, min(8, int(stage.get("count", 8))))
        return [{"at": t, "kind": "pop"} for t in _times(start, end, count, 1.35)]
    if motif in {"phone_frame", "broll_card"}:
        events = [{"at": round(start, 3), "kind": "whoosh"}]
        if stage.get("callout"):
            events.append({"at": float(stage["callout"].get("at", start + ENTRANCE_SECONDS)), "kind": "marker"})
        if stage.get("highlight"):
            events.append({"at": float(stage["highlight"].get("at", start + ENTRANCE_SECONDS)), "kind": "pop"})
        if stage.get("typing"):
            for moment in _times(start + 0.14, min(end, start + 1.15), 6, 0.9):
                events.append({"at": moment, "kind": "typing"})
        return events
    if motif == "numbered_list":
        items = stage.get("items") or ["One", "Two", "Three", "Four"]
        if stage.get("hold"):
            return [{"at": round(start, 3), "kind": "click"}]
        window = 4.5 if stage.get("variant") == "cards" else 1.6
        return [{"at": t, "kind": "click"} for t in _times(start, end, min(6, len(items)), window)]
    if motif == "line_chart":
        nodes = _times(start + 0.16, end, 3, 0.9)
        return [{"at": round(start, 3), "kind": "whoosh"}] + [{"at": t, "kind": "ding"} for t in nodes]
    if motif == "bar_chart":
        if stage.get("reveal") == "slice":
            rise = min(0.55, max(0.28, (end - start) * 0.4))
            return [{"at": round(start, 3), "kind": "riser"},
                    {"at": _clamp(start + rise, start, end), "kind": "ding"}]
        heights = list(stage.get("heights") or [])
        count = int(stage.get("count") or len(heights) or 4)
        last = float(heights[min(len(heights), count) - 1]) if heights else 100.0
        # Pack the pops when the last bar has to rise and then fall before the cut.
        window = 0.36 if last <= 12 else 0.8
        events = [{"at": t, "kind": "pop"} for t in _times(start, end, max(1, count), window)]
        if last <= 12 and events:
            events.append({"at": _clamp(float(events[-1]["at"]) + 0.26, start, end), "kind": "error"})
        return events
    if motif == "counter":
        ticks = _times(start, min(end, start + 0.9), 6, 0.8)
        events = [{"at": t, "kind": "ticking"} for t in ticks]
        events.append({"at": round(min(end - 0.08, start + 0.95), 3), "kind": "ding"})
        if stage.get("strike"):
            events.append({"at": _clamp(stage.get("strike_at", start + 0.45), start, end), "kind": "error"})
        return events
    if motif == "highlight_box":
        # The line waits until the card slide has finished.
        draw = round(min(end - 0.05, start + ENTRANCE_SECONDS), 3)
        return [{"at": round(start, 3), "kind": "whoosh"}, {"at": draw, "kind": "pop"}]
    if motif == "hand_circle":
        return [{"at": round(start, 3), "kind": "whoosh"},
                {"at": round(start + 0.05, 3), "kind": "marker"}]
    if motif == "doc_fan":
        count = int(stage.get("count", 5))
        if stage.get("strike"):
            events = [{"at": t, "kind": "paper"} for t in _times(start, min(end, start + 0.42), count, 0.4)]
            events.append({"at": _clamp(stage.get("strike_at", start + 0.5), start, end), "kind": "error"})
            return events
        return [{"at": t, "kind": "paper"} for t in _times(start, end, count, 1.15)]
    if motif == "typing_ui":
        return [{"at": t, "kind": "typing"} for t in _times(start, min(end, start + 1.15), 8, 1.05)]
    if motif == "mind_map":
        branches = _times(start + 0.12, end, 3, 0.9)
        return [{"at": round(start, 3), "kind": "pop"}] + [{"at": t, "kind": "ding"} for t in branches]
    if motif == "logo_row":
        return [{"at": t, "kind": "pop"} for t in _times(start, end, 3, 0.7)] + [
            {"at": round(min(end - 0.05, start + 0.2), 3), "kind": "whoosh"}]
    if motif == "quote_card":
        events = [{"at": round(start, 3), "kind": "whoosh"}, {"at": round(start, 3), "kind": "pop"}]
        if stage.get("variant") == "receipt":
            count = len(stage.get("items") or ["JAN", "FEB", "MAR", "APR", "MAY"])
            for moment in _times(start + 0.08, min(end, start + 0.62), max(1, count), 0.5):
                events.append({"at": moment, "kind": "ticking"})
        if stage.get("strike"):
            events.append({"at": _clamp(stage.get("strike_at", start + 0.35), start, end), "kind": "error"})
        return events
    if motif == "offer_pair":
        return [{"at": round(start, 3), "kind": "pop"},
                {"at": _clamp(start + 0.16, start, end), "kind": "pop"}]
    if motif == "flow_line":
        return [{"at": round(start, 3), "kind": "whoosh"},
                {"at": _clamp(start + 0.28, start, end), "kind": "ding"}]
    if motif == "pill":
        return [{"at": round(start, 3), "kind": "pop"}]
    if motif == "cursor_mock":
        return [{"at": round(start, 3), "kind": "whoosh"},
                {"at": _clamp(start + 0.42, start, end), "kind": "click"}]
    if motif == "vacuum_merge":
        items = stage.get("items") or ["One", "Two", "Three", "Four"]
        count = max(2, min(6, len(items)))
        events = [{"at": t, "kind": "pop"} for t in _times(start, end, count, 0.28)]
        events.append({"at": _clamp(start + 0.55, start, end), "kind": "whoosh"})
        events.append({"at": _clamp(start + 0.78, start, end), "kind": "ding"})
        return events
    if motif == "state_swap":
        return [{"at": round(start, 3), "kind": "whoosh"},
                {"at": round(start, 3), "kind": "pop"},
                {"at": _clamp(start + 0.42, start, end), "kind": "error"},
                {"at": _clamp(start + 0.62, start, end), "kind": "ding"}]
    return []


def _pop(selector, at):
    # Hidden until the cue, then one rise. immediateRender keeps the first frames at 0
    # so a card cannot flash full-size and collapse before it enters.
    return (f'tl.fromTo("{selector}",{{scale:0}},{{scale:1,duration:0.24,ease:"power2.out",'
            f'transformOrigin:"50% 50%",immediateRender:true}},{at});')


def _slide(selector, at):
    # Slide up from below the panel. The stage clips the offset, so the entrance
    # does not fade in.
    return (f'tl.fromTo("{selector}",{{y:72}},{{y:0,duration:0.24,ease:"back.out(1.4)",'
            f'immediateRender:true}},{at});')


def _snap_in(selector, at, fro, to, duration, ease="back.out(1.7)", origin="50% 50%"):
    """Pop or wipe. Opacity is already 1 on both keys, so a hidden element snaps on."""
    if isinstance(at, (int, float)):
        at = f"{float(at):.3f}"
    return (f'tl.fromTo("{selector}",{{{fro},opacity:1}},{{{to},opacity:1,duration:{float(duration):.2f},'
            f'ease:"{ease}",transformOrigin:"{origin}",immediateRender:false}},{at});')


def motif_markup(motif, stage, start, end, box, colors, ident, media_url=None, track_index=2):
    stage = stage or {}
    if motif in {"phone_frame", "broll_card"}:
        if motif == "phone_frame":
            # The visible screen, not the whole stage, so the pan centers on what we see.
            screen = hero_phone_box(box["width"], box["height"])["screen"]
        else:
            pad = 8 * (float(box["width"]) / 0.9) / 1080
            screen = (float(box["width"]) - 2 * pad, float(box["height"]) - 2 * pad)
        resolve_annotations(stage, start, end, screen)
    events = stage_events(motif, start, end, stage)
    animations = []
    duration = end - start
    text = colors["text"]
    muted = colors["muted"]
    accent = colors["accent"]
    strong = colors["accent_strong"]
    surface = colors["surface"]
    border = colors["border"]
    contrast = colors["contrast"]
    warning = colors["warning"]
    on_accent = colors["on_accent"]
    soft = _rgba(accent, 0.4)

    if motif == "thumbnail_grid":
        labels = list(stage.get("items") or ["Hook", "Proof", "Offer", "Cut", "List", "Chart", "Note", "CTA"])
        count = len(events)
        labels = (labels + ["Shot"] * count)[:count]
        cols = 4 if count >= 7 else 3
        cards = []
        for index, label in enumerate(labels):
            card = f"{ident}-t{index}"
            accent_edge = f"border-top:4px solid {accent};" if index == 0 else ""
            cards.append(
                f'<div id="{card}" class="thumb" style="background:linear-gradient(165deg,{surface},{contrast});'
                f'border:1px solid {border};{accent_edge}"><span class="mono">{index+1:02d}</span>'
                f'<b>{_esc(label)}</b><i>&#9654;</i></div>')
            animations.append(_pop(f"#{card}", events[index]["at"]))
        body = f'<div class="thumb-grid" style="grid-template-columns:repeat({cols},1fr)">{"".join(cards)}</div>'

    elif motif == "phone_frame":
        chip = stage.get("chip")
        if isinstance(chip, str):
            stage["chip"] = {"text": chip, "place": "bottom"}
        elif isinstance(chip, dict) and not chip.get("place"):
            chip["place"] = "bottom"
        scroll = stage.get("scroll") or {}
        desat = float(stage.get("desaturate") or 0)
        detailed = bool(scroll or desat or stage.get("callout") or stage.get("highlight"))
        motion = stage.get("motion") or resolve_annotations(stage, start, end)
        geo = hero_phone_box(box["width"], box["height"])
        img_h = image_height_percent(stage)
        sat = max(0.0, min(1.0, 1.0 - desat))
        scroll_to = float(scroll.get("to", 0)) if scroll else 0
        # A wide frame letterboxes the 9:16 recording so the price and the
        # modal stay whole. A tall frame covers, and only crops top and bottom.
        screen_w, screen_h = geo["screen"]
        fit = "contain" if screen_h <= 0 or (screen_w / screen_h) > 0.62 else "cover"
        if media_url:
            picture = _media_tag(ident, media_url, start, end, fit, sat, track_index, stage)
        else:
            picture = (f'<div class="phone-fake"><b style="color:{text}">Preview</b>'
                       f'<span class="mono" style="color:{muted}">9:16</span></div>')
        extras = ""
        if stage.get("callout"):
            callout = stage["callout"]
            left, top, width, height = screenshot_box(callout, img_h, scroll_to)
            extras += (
                f'<svg id="{ident}-ring" class="callout-draw" viewBox="0 0 100 100" preserveAspectRatio="none" '
                f'style="left:{left:.2f}%;top:{top:.2f}%;width:{width:.2f}%;height:{height:.2f}%">'
                f'<path id="{ident}-stroke" d="{HAND_CIRCLE}" stroke-dasharray="{HAND_CIRCLE_LENGTH}" '
                f'stroke-dashoffset="{HAND_CIRCLE_LENGTH}"/></svg>')
        if stage.get("highlight"):
            highlight = stage["highlight"]
            mapped = highlight if highlight.get("space") == "image" else {
                "x": 0, "y": highlight.get("y", 0.4), "w": 1, "h": 0.08}
            _left, top, _width, _height = screenshot_box(mapped, img_h, scroll_to)
            # An underline under the price, not a bar painted on top of the glyphs.
            # The underline marks the row. The label sat on the disclaimer text.
            extras += (f'<div id="{ident}-hl" class="hl-line phone-hl" style="top:{top + _height:.2f}%"></div>')
        thumb = "" if detailed else f'<div id="{ident}-thumb" class="thumb-dot"></div>'
        cursor = ""
        if stage.get("callout"):
            cursor = f'<div id="{ident}-cursor" class="cursor-ptr"></div>'
        # A filling bar reads as a stray underline. It is off unless the beat asks.
        bar = ""
        if stage.get("progress"):
            bar = f'<div class="phone-bar"><div id="{ident}-prog"></div></div>'
        phone_style = (
            f'position:absolute;left:{geo["left"]}px;top:{geo["top"]}px;width:{geo["width"]}px;'
            f'height:{geo["height"]}px;margin:0;padding:{geo["pad"]}px')
        body = (f'<div id="{ident}-phone" class="phone hero" style="{phone_style}">'
                f'<div class="phone-screen" style="height:{int(geo["screen"][1])}px">'
                f'<div id="{ident}-pan" class="phone-pan" style="height:{img_h:.2f}%">{picture}{extras}</div>'
                f'{bar}{thumb}{cursor}</div></div>')
        animations.append(_slide(f"#{ident}-phone", events[0]["at"]))
        origin = "50% 42%"
        callout = stage.get("callout") or {}
        frame = stage.get("frame") or {}
        if callout.get("y") is not None and frame.get("viewport_height"):
            view_top = float(frame.get("viewport_top") or 0)
            view_h = float(frame["viewport_height"])
            cy = (float(callout["y"]) + float(callout.get("h") or 0) / 2 - view_top) / view_h
            cx = float(callout.get("x") or 0.5) + float(callout.get("w") or 0) / 2
            ox = (geo["pad"] + min(1.0, max(0.0, cx)) * geo["screen"][0]) / geo["width"] * 100
            oy = (geo["pad"] + min(1.0, max(0.0, cy)) * geo["screen"][1]) / geo["height"] * 100
            origin = f"{ox:.1f}% {oy:.1f}%"
        push_at = float(motion.get("push_start") or (start + 0.42))
        push_end = float(motion.get("push_end") or (push_at + 0.38))
        # The handset already fits the panel. A push would crop the bezel again.
        animations.append(
            f'tl.set("#{ident}-phone",{{scale:1,transformOrigin:"{origin}"}},{push_at:.3f});')
        if stage.get("progress"):
            animations.append(
                f'tl.fromTo("#{ident}-prog",{{scaleX:0}},{{scaleX:1,duration:{max(0.4, duration-0.45):.3f},ease:"none",transformOrigin:"0% 50%"}},{start+0.2});')
        if not detailed:
            animations.append(
                f'tl.fromTo("#{ident}-thumb",{{y:40}},{{y:-120,duration:{max(0.4, duration-0.5):.3f},ease:"power1.inOut"}},{start+0.4});')
        if scroll:
            # The pan is the screenshot. yPercent moves the callout with the pixels.
            extra = img_h - 100
            fro = -float(scroll.get("from", 0)) * extra / img_h * 100
            to = -float(scroll.get("to", 0.45)) * extra / img_h * 100
            scroll_start = float(motion.get("scroll_start") or start)
            scroll_end = float(motion.get("scroll_end") or (scroll_start + 0.45))
            span = max(0.2, scroll_end - scroll_start)
            animations.append(
                f'tl.fromTo("#{ident}-pan",{{yPercent:{fro:.2f}}},{{yPercent:{to:.2f},duration:{span:.3f},'
                f'ease:"power1.inOut",immediateRender:false}},{scroll_start:.3f});')
        if stage.get("callout"):
            at = float(stage["callout"]["at"])
            draw = float(stage["callout"].get("draw") or DRAW_SECONDS)
            # A cursor and a pulse so the mock is not frozen until the oval draws.
            animations.append(
                f'tl.fromTo("#{ident}-cursor",{{x:140,y:90}},{{x:8,y:4,'
                f'duration:0.42,ease:"power2.out",immediateRender:true}},{start + 0.32:.3f});')
            animations.append(
                f'tl.to("#{ident}-phone",{{scale:1.04,duration:0.42,yoyo:true,repeat:3,'
                f'ease:"sine.inOut",transformOrigin:"{origin}"}},{start + 0.48:.3f});')
            animations.append(f'tl.set("#{ident}-ring",{{opacity:1}},{at:.3f});')
            animations.append(
                f'tl.fromTo("#{ident}-stroke",{{strokeDashoffset:{HAND_CIRCLE_LENGTH}}},'
                f'{{strokeDashoffset:0,duration:{draw:.2f},ease:"power1.inOut"}},{at:.3f});')
        if stage.get("highlight"):
            at = float(stage["highlight"]["at"])
            animations.append(_snap_in(
                f"#{ident}-hl", f"{at:.3f}", "scaleX:0", "scaleX:1", 0.28,
                ease="power2.out", origin="0% 50%"))

    elif motif == "broll_card":
        if media_url:
            picture = _media_tag(ident, media_url, start, end, "cover", 1.0, track_index, stage)
        else:
            picture = '<div class="broll-fake"><span class="mono">B-ROLL</span></div>'
        bar = ""
        if stage.get("progress"):
            bar = f'<div class="broll-progress"><div id="{ident}-bar"></div></div>'
        body = f'<div id="{ident}-card" class="broll-card">{picture}{bar}</div>'
        animations.append(_slide(f"#{ident}-card", events[0]["at"]))
        if stage.get("progress"):
            animations.append(
                f'tl.fromTo("#{ident}-bar",{{scaleX:0}},{{scaleX:1,duration:{max(0.4, duration-0.35):.3f},ease:"none",transformOrigin:"0% 50%"}},{start+0.2});')

    elif motif == "numbered_list":
        items = list(stage.get("items") or ["Open on the split", "Cut closer", "Show the proof", "Ask for the comment"])[:6]
        if stage.get("variant") == "cards":
            glyphs = ["calendar", "sheet", "lock", "doc", "globe", "bolt"]
            cards = []
            glow = f"0 24px 48px rgba(0,0,0,0.45), 0 0 36px {accent}aa"
            rest = "0 18px 36px rgba(0,0,0,0.35)"
            for index, item in enumerate(items[:3]):
                cards.append(
                    f'<div id="{ident}-row{index}" class="feat-card">'
                    f'<div class="feat-ico">{icon_svg(glyphs[index])}</div><b>{_esc(item)}</b></div>')
            body = f'<div class="feat-col">{"".join(cards)}</div>'
            for index, event in enumerate(events[:len(items[:3])]):
                animations.append(_pop(f"#{ident}-row{index}", event["at"]))
                animations.append(
                    f'tl.to("#{ident}-row{index}",{{boxShadow:"{glow}",borderColor:"{accent}",duration:0.2}},{event["at"]:.3f});')
                for earlier in range(index):
                    animations.append(
                        f'tl.to("#{ident}-row{earlier}",{{boxShadow:"{rest}",borderColor:"{border}",duration:0.2}},{event["at"]:.3f});')
        else:
            row_h = 100 / max(1, len(items))
            holding = bool(stage.get("hold"))
            active = max(0, min(len(items) - 1, int(stage.get("active", 0)))) if holding else 0
            rows = []
            for index, item in enumerate(items):
                blur = "filter:blur(4px);opacity:0.45;" if index > active else ""
                rows.append(
                    f'<div id="{ident}-row{index}" class="nrow" style="height:{row_h:.2f}%;{blur}">'
                    f'<span class="mono">{index+1:02d}</span><b>{_esc(item)}</b></div>')
            body = (f'<div class="nlist">{"".join(rows)}'
                    f'<div id="{ident}-box" class="nbox" style="height:{row_h - 2:.2f}%;top:{active * row_h:.2f}%"></div></div>')
            if holding:
                animations.append(f'tl.set("#{ident}-box",{{top:"{active * row_h:.2f}%"}},{events[0]["at"]});')
            else:
                for index, event in enumerate(events):
                    y = index * row_h
                    animations.append(f'tl.set("#{ident}-box",{{top:"{y:.2f}%"}},{event["at"]});')
                    for row in range(len(items)):
                        if row > index:
                            animations.append(f'tl.set("#{ident}-row{row}",{{filter:"blur(4px)",opacity:0.45}},{event["at"]});')
                        else:
                            animations.append(f'tl.set("#{ident}-row{row}",{{filter:"blur(0px)",opacity:1}},{event["at"]});')

    elif motif == "line_chart":
        body = (
            f'<svg class="chart" viewBox="0 0 1000 480" preserveAspectRatio="none">'
            f'<path id="{ident}-path" d="M40 90 C 180 100, 240 250, 340 320 S 560 430, 680 250 S 860 60, 960 84" '
            f'fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round" stroke-dasharray="1400"/>'
            f'<circle id="{ident}-n0" cx="340" cy="320" r="12" fill="{accent}" opacity="0"/>'
            f'<circle id="{ident}-n1" cx="680" cy="250" r="12" fill="{accent}" opacity="0"/>'
            f'<circle id="{ident}-n2" cx="960" cy="84" r="12" fill="{accent}" opacity="0"/>'
            f'</svg><div class="chart-label mono">reach</div>')
        animations.append(
            f'tl.fromTo("#{ident}-path",{{strokeDashoffset:1400}},{{strokeDashoffset:0,duration:0.95,ease:"power2.out"}},{start});')
        for index in range(3):
            animations.append(_snap_in(
                f"#{ident}-n{index}", events[index + 1]["at"], "scale:0", "scale:1", 0.28))

    elif motif == "bar_chart":
        heights = list(stage.get("heights") or [42, 68, 38, 88])
        labels = list(stage.get("labels") or [])
        negative = bool(stage.get("negative"))
        sliced = stage.get("reveal") == "slice"
        count = min(len(heights), 5 if sliced else len([event for event in events if event["kind"] == "pop"] or events))
        pop_events = [event for event in events if event["kind"] == "pop"] or events
        bars = []
        for index in range(count):
            short = float(heights[index]) <= 12
            color = warning if short or (negative and index == 0) else accent
            visual = 86 if short else heights[index]
            caption = _esc(labels[index]) if index < len(labels) else f"{index+1:02d}"
            marker = f'<div id="{ident}-x{index}" class="bar-x">X</div>' if short else ""
            bars.append(
                f'<div class="bar-col">{marker}<div id="{ident}-b{index}" class="bar" '
                f'style="height:{visual}%;background:{color}"></div>'
                f'<span class="mono">{caption}</span></div>')
            at = events[0]["at"] if sliced else pop_events[min(index, len(pop_events) - 1)]["at"]
            grow = 0.22 if short and not sliced else 0.36
            animations.append(
                f'tl.fromTo("#{ident}-b{index}",{{scaleY:0}},{{scaleY:1,duration:{grow:.2f},ease:"back.out(1.5)",'
                f'transformOrigin:"50% 100%",immediateRender:false}},{at});')
            if short and not sliced:
                # Start the fall after the rise, and finish it before the shot ends.
                drop_at = min(at + grow + 0.04, max(at + grow + 0.02, end - 0.32))
                animations.append(
                    f'tl.to("#{ident}-b{index}",{{scaleY:0.02,duration:0.26,ease:"power2.in"}},'
                    f'{drop_at:.3f});')
        drop = next((event for event in events if event["kind"] == "error"), None)
        if drop:
            animations.append(_snap_in(
                f"#{ident}-x{count - 1}", drop["at"], "scale:0", "scale:1", 0.2, ease="back.out(2)"))
        body = (
            f'<div class="chart-frame"><div class="y-axis"><span>100</span><span>50</span><span>0</span></div>'
            f'<div class="bars">{"".join(bars)}</div></div>')

    elif motif == "counter":
        target = int(stage.get("value", 30))
        label = stage.get("label") or ""
        prefix = json.dumps(str(stage.get("prefix") or ""))
        suffix = json.dumps(str(stage.get("suffix") or ""))
        variable = ident.replace("-", "_") + "n"
        label_html = f'<div class="mono count-label">{_esc(label)}</div>' if label else ""
        thumbs = []
        tick_events = [event for event in events if event["kind"] == "ticking"]
        ding_at = next((event["at"] for event in events if event["kind"] == "ding"), start)
        if stage.get("strike"):
            glyphs = ["calendar", "sheet", "lock", "doc", "globe", "bolt", "home", "star"]
            for index, item in enumerate(list(stage.get("items") or [])[:3]):
                at = tick_events[index]["at"] if index < len(tick_events) else ding_at
                thumbs.append(
                    f'<div id="{ident}-s{index}" class="range-card">'
                    f'<div class="range-ico">{icon_svg(glyphs[index])}</div><b>{_esc(item)}</b></div>')
                animations.append(_pop(f"#{ident}-s{index}", at))
            grid = f'<div class="range-row">{"".join(thumbs)}</div>' if thumbs else ""
            struck = ""
            if label:
                struck = (f'<div id="{ident}-old" class="range-old"><b>{_esc(label)}</b>'
                          f'<div id="{ident}-strike" class="quote-strike"></div></div>')
                at = next((event["at"] for event in events if event["kind"] == "error"), start + 0.45)
                animations.append(_pop(f"#{ident}-old", start))
                animations.append(
                    f'tl.fromTo("#{ident}-strike",{{scaleX:0}},{{scaleX:1,duration:0.16,ease:"power2.out",'
                    f'transformOrigin:"0% 50%",immediateRender:false}},{at:.3f});')
                animations.append(
                    f'tl.to("#{ident}-old",{{x:460,rotation:8,opacity:0,duration:0.26,ease:"power2.in"}},'
                    f'{min(end - 0.08, at + 0.28):.3f});')
            body = (f'<div class="counter range">{struck}'
                    f'<div id="{ident}-num" class="count-num">{_esc(stage.get("prefix") or "")}0{_esc(stage.get("suffix") or "")}</div>'
                    f'{grid}</div>')
        else:
            for index, item in enumerate(list(stage.get("items") or [])[:8]):
                at = tick_events[index]["at"] if index < len(tick_events) else ding_at
                thumbs.append(
                    f'<div id="{ident}-s{index}" class="site-thumb"><span class="mono">{index+1:02d}</span>'
                    f'<b>{_esc(item)}</b><i></i></div>')
                animations.append(_pop(f"#{ident}-s{index}", at))
            grid = f'<div class="site-grid">{"".join(thumbs)}</div>' if thumbs else ""
            dense = " dense" if thumbs else ""
            body = (f'<div class="counter{dense}"><div id="{ident}-num" class="count-num">{_esc(stage.get("prefix") or "")}0{_esc(stage.get("suffix") or "")}</div>'
                    f'{grid}{label_html}</div>')
        animations.append(
            f'const {variable}={{v:0}};'
            f'tl.to({variable},{{v:{target},duration:0.9,ease:"power2.out",'
            f'onUpdate:()=>{{const el=document.getElementById("{ident}-num");'
            f'if(el) el.textContent={prefix}+Math.round({variable}.v).toLocaleString("en-US")+{suffix};}}}},{start});')
        animations.append(_pop(f"#{ident}-num", start))

    elif motif == "highlight_box":
        line = stage.get("label") or "the line that matters"
        picture = f'<img src="{_esc(media_url)}" alt="">' if media_url else ""
        body = (f'<div id="{ident}-shot" class="shotcard">{picture}'
                f'<div class="fake-line" style="width:78%"></div>'
                f'<div class="fake-line" style="width:54%"></div>'
                f'<div id="{ident}-hl" class="hl-line">{_esc(line)}</div>'
                f'<div class="fake-line" style="width:66%"></div></div>')
        animations.append(_slide(f"#{ident}-shot", events[0]["at"]))
        animations.append(_snap_in(
            f"#{ident}-hl", events[1]["at"], "scaleX:0", "scaleX:1", 0.28,
            ease="power2.out", origin="0% 50%"))

    elif motif == "hand_circle":
        phrase = stage.get("label") or "this"
        body = (f'<div class="circle-wrap"><div class="circle-card">{_esc(phrase)}</div>'
                f'<svg class="circle-svg" viewBox="0 0 400 240">'
                f'<path id="{ident}-ring" d="M70 120 C 80 40, 300 30, 330 110 C 360 190, 120 220, 70 140" '
                f'fill="none" stroke="{strong}" stroke-width="7" stroke-linecap="round" stroke-dasharray="800"/></svg></div>')
        animations.append(
            f'tl.fromTo("#{ident}-ring",{{strokeDashoffset:800}},{{strokeDashoffset:0,duration:0.45,ease:"power2.out"}},{events[0]["at"]});')

    elif motif == "doc_fan":
        pages = stage.get("pages") or [
            ("VAULT", "AI Business Idea Vault"),
            ("30+", "AI business ideas"),
            ("A TO Z", "First client guide"),
            ("START", "A working system"),
            ("YOURS", "Comment the keyword"),
        ]
        paper = [event for event in events if event["kind"] == "paper"]
        pages = pages[:len(paper)]
        fans = []
        spread = [-26, -13, 0, 13, 26]
        shifts = [-10, -5, 0, 5, 10]
        for index, page in enumerate(pages):
            kicker, title = page
            rot = spread[index] if index < len(spread) else 0
            shift = shifts[index] if index < len(shifts) else 0
            left = (11 + shift) if stage.get("strike") else (16 + shift)
            fans.append(
                f'<div class="page-rot" style="left:{left}%;transform:rotate({rot}deg)">'
                f'<div id="{ident}-p{index}" class="page"><div class="page-rule"></div>'
                f'<div class="mono">{_esc(kicker)}</div><div class="page-title">{_esc(title)}</div>'
                f'<div id="{ident}-tint{index}" class="fan-tint"></div></div></div>')
            animations.append(_pop(f"#{ident}-p{index}", paper[index]["at"]))
        klass = "fan stack" if stage.get("strike") else "fan"
        body = f'<div id="{ident}-fan" class="{klass}">{"".join(fans)}</div>'
        if stage.get("strike"):
            at = next((event["at"] for event in events if event["kind"] == "error"), start + 0.5)
            for index in range(len(pages)):
                animations.append(
                    f'tl.to("#{ident}-tint{index}",{{opacity:0.78,duration:0.1,ease:"power1.out"}},{at:.3f});')
            animations.append(
                f'tl.to("#{ident}-fan",{{x:560,rotation:7,opacity:0,duration:0.26,ease:"power2.in"}},{at:.3f});')

    elif motif == "typing_ui":
        typed = stage.get("text") or "Turn the lesson into a client brief."
        title = stage.get("label") or "NOTES"
        result = stage.get("result") or ""
        window_class = "window terminal" if stage.get("label") else "window"
        result_html = (
            f'<div id="{ident}-result" class="term-result">{_esc(result)}</div>' if result else "")
        body = (f'<div id="{ident}-win" class="{window_class}"><div class="chrome"><i></i><i></i><i></i>'
                f'<span class="mono">{_esc(title)}</span></div><div class="win-body">'
                f'<span id="{ident}-type"></span><span id="{ident}-caret" class="caret">|</span>'
                f'{result_html}</div></div>')
        payload = json.dumps(typed)
        variable = ident.replace("-", "_") + "c"
        type_at = events[0]["at"]
        type_span = min(1.15, max(0.4, duration - 0.3))
        animations.append(_slide(f"#{ident}-win", start))
        animations.append(
            f'const {variable}={{n:0}};tl.to({variable},{{n:{len(typed)},duration:{type_span:.3f},'
            f'ease:"none",onUpdate:()=>{{const el=document.getElementById("{ident}-type");'
            f'if(el) el.textContent={payload}.slice(0,Math.floor({variable}.n));}}}},{type_at});')
        if result:
            animations.append(_pop(f"#{ident}-result", min(end - 0.4, type_at + type_span + 0.08)))
        animations.append(
            f'tl.to("#{ident}-caret",{{opacity:0,duration:0.12,ease:"none"}},{max(start, end - 0.12):.3f});')

    elif motif == "mind_map":
        center = stage.get("label") or "Offer"
        leaves = list(stage.get("items") or ["Hook", "Proof", "CTA"])[:3]
        body = (
            f'<svg class="mind" viewBox="0 0 1000 520">'
            f'<path id="{ident}-l0" d="M500 250 C 380 250, 280 120, 180 110" fill="none" stroke="{strong}" stroke-width="4" stroke-dasharray="400"/>'
            f'<path id="{ident}-l1" d="M500 250 C 620 250, 760 150, 840 120" fill="none" stroke="{strong}" stroke-width="4" stroke-dasharray="400"/>'
            f'<path id="{ident}-l2" d="M500 270 C 500 360, 500 400, 500 450" fill="none" stroke="{strong}" stroke-width="4" stroke-dasharray="400"/>'
            f'</svg>'
            f'<div id="{ident}-c" class="node center-node">{_esc(center)}</div>'
            f'<div id="{ident}-a" class="node leaf-a">{_esc(leaves[0])}</div>'
            f'<div id="{ident}-b" class="node leaf-b">{_esc(leaves[1] if len(leaves)>1 else "Proof")}</div>'
            f'<div id="{ident}-d" class="node leaf-c">{_esc(leaves[2] if len(leaves)>2 else "CTA")}</div>')
        animations.append(_pop(f"#{ident}-c", events[0]["at"]))
        for index, selector in enumerate(("a", "b", "d")):
            animations.append(
                f'tl.fromTo("#{ident}-l{index}",{{strokeDashoffset:400}},{{strokeDashoffset:0,duration:0.35,ease:"power2.out"}},{events[index+1]["at"]});')
            animations.append(_pop(f"#{ident}-{selector}", events[index + 1]["at"]))

    elif motif == "logo_row":
        labels = list(stage.get("items") or ["Plan", "Build", "Ship"])[:3]
        chips = []
        for index, label in enumerate(labels):
            chips.append(f'<div id="{ident}-c{index}" class="logo-chip">{_esc(label)}</div>')
            animations.append(_pop(f"#{ident}-c{index}", events[index]["at"]))
        body = (f'<div class="logo-row">{"".join(chips)}</div>'
                f'<svg class="logo-lines" viewBox="0 0 1000 200">'
                f'<path id="{ident}-d0" d="M250 100 H430" fill="none" stroke="{muted}" stroke-width="4" stroke-dasharray="10 12"/>'
                f'<path id="{ident}-d1" d="M570 100 H750" fill="none" stroke="{muted}" stroke-width="4" stroke-dasharray="10 12"/>'
                f'</svg>')
        animations.append(
            f'tl.fromTo("#{ident}-d0",{{strokeDashoffset:200}},{{strokeDashoffset:0,duration:0.4,ease:"power2.out"}},{events[-1]["at"]});')
        animations.append(
            f'tl.fromTo("#{ident}-d1",{{strokeDashoffset:200}},{{strokeDashoffset:0,duration:0.4,ease:"power2.out"}},{events[-1]["at"]});')

    elif motif == "quote_card":
        quote = stage.get("text") or stage.get("label") or "We already have one."
        variant = stage.get("variant") or ""
        if variant == "receipt":
            months = list(stage.get("items") or ["JAN", "FEB", "MAR", "APR", "MAY"])
            ticks = [event for event in events if event["kind"] == "ticking"]
            cells = []
            for index, month in enumerate(months):
                tone = "cal-on" if index == 0 else "cal-off"
                cells.append(f'<span id="{ident}-m{index}" class="{tone}">{_esc(month)}</span>')
                at = ticks[index]["at"] if index < len(ticks) else events[0]["at"]
                animations.append(_pop(f"#{ident}-m{index}", at))
            stamp = ""
            if stage.get("strike"):
                stamp = f'<div id="{ident}-stamp" class="paid-stamp">PAID</div>'
                at = next(event["at"] for event in events if event["kind"] == "error")
                animations.append(_snap_in(
                    f"#{ident}-stamp", at, "scale:1.45,rotation:-18", "scale:1,rotation:-12",
                    0.22, ease="back.out(2)"))
            body = (
                f'<div id="{ident}-quote" class="receipt"><div class="receipt-glow"></div>'
                f'<div class="mono receipt-kicker">INVOICE · WEBSITE BUILD</div>'
                f'<div class="receipt-amt">{_esc(quote)}</div>'
                f'<div class="receipt-line"><span>Paid once</span><span>Then nothing</span></div>'
                f'<div class="cal">{"".join(cells)}</div>{stamp}</div>')
            animations.append(_pop(f"#{ident}-quote", events[0]["at"]))
        elif variant == "browser":
            body = (
                f'<div id="{ident}-quote" class="browser"><div class="chrome"><i></i><i></i><i></i>'
                f'<span class="mono">client-site.com</span></div>'
                f'<div id="{ident}-live" class="browser-live"><b>Client site</b>'
                f'<span>Home</span><span>Work</span><span>Contact</span>'
                f'<div id="{ident}-rows" class="page-rows"><i></i><i></i><i></i></div></div>'
                f'<div id="{ident}-dead" class="browser-dead"><div id="{ident}-mark" class="offline-mark">!</div>'
                f'<div>{_esc(quote)}</div><div class="offline-sub">client-site.com</div></div></div>')
            animations.append(_slide(f"#{ident}-quote", events[0]["at"]))
            if stage.get("strike"):
                at = next(event["at"] for event in events if event["kind"] == "error")
                animations.append(
                    f'tl.fromTo("#{ident}-live",{{y:0,scale:1}},{{y:70,scale:0.82,duration:0.28,'
                    f'ease:"power2.in",transformOrigin:"50% 0%"}},{at - 0.12:.3f});')
                animations.append(f'tl.set("#{ident}-live",{{opacity:0}},{at:.3f});')
                animations.append(_snap_in(
                    f"#{ident}-dead", f"{at:.3f}", "y:36,scale:0.92", "y:0,scale:1", 0.2, ease="back.out(1.6)"))
                animations.append(
                    f'tl.fromTo("#{ident}-quote",{{x:0}},{{x:7,duration:0.04,yoyo:true,repeat:5,'
                    f'ease:"none"}},{at:.3f});')
                animations.append(
                    f'tl.fromTo("#{ident}-mark",{{scale:1}},{{scale:1.08,duration:0.45,yoyo:true,repeat:3,'
                    f'ease:"sine.inOut",transformOrigin:"50% 50%"}},{at + 0.28:.3f});')
        elif variant == "balance":
            body = (
                f'<div id="{ident}-quote" class="quote-card balance">'
                f'<div class="bal-row"><div class="bal-col"><b>Design spend</b>'
                f'<div id="{ident}-hi" class="bal-bar"></div></div>'
                f'<div id="{ident}-ne" class="bal-ne">≠</div>'
                f'<div class="bal-col"><b>Revenue</b><div id="{ident}-lo" class="bal-bar short"></div></div></div>'
                f'<div class="quote-text">{_esc(quote)}</div></div>')
            animations.append(_pop(f"#{ident}-quote", events[0]["at"]))
            animations.append(
                f'tl.fromTo("#{ident}-hi",{{scaleY:0}},{{scaleY:1,duration:0.4,ease:"power2.out",'
                f'transformOrigin:"50% 100%",immediateRender:true}},{events[0]["at"] + 0.08:.3f});')
            animations.append(
                f'tl.fromTo("#{ident}-lo",{{scaleY:0}},{{scaleY:1,duration:0.4,ease:"power2.out",'
                f'transformOrigin:"50% 100%",immediateRender:true}},{events[0]["at"] + 0.2:.3f});')
            animations.append(_pop(f"#{ident}-ne", events[0]["at"] + 0.34))
            animations.append(
                f'tl.fromTo("#{ident}-hi",{{scaleY:1}},{{scaleY:0.9,duration:0.4,yoyo:true,repeat:3,'
                f'ease:"sine.inOut",transformOrigin:"50% 100%"}},{events[0]["at"] + 0.7:.3f});')
        else:
            strike = ""
            if stage.get("strike"):
                strike = f'<div id="{ident}-strike" class="quote-strike"></div>'
                at = next(event["at"] for event in events if event["kind"] == "error")
                animations.append(
                    f'tl.fromTo("#{ident}-strike",{{scaleX:0}},{{scaleX:1,duration:0.22,ease:"power2.out",'
                    f'transformOrigin:"0% 50%",immediateRender:false}},{at});')
            body = (f'<div id="{ident}-quote" class="quote-card"><div class="quote-text">{_esc(quote)}{strike}</div></div>')
            animations.append(_pop(f"#{ident}-quote", events[0]["at"]))

    elif motif == "offer_pair":
        items = list(stage.get("items") or ["First offer", "Second offer"])[:2]
        while len(items) < 2:
            items.append("Offer")
        kicker = f'<div class="mono offer-kicker">{_esc(stage["kicker"])}</div>' if stage.get("kicker") else ""
        note = stage.get("disclaimer") or ""
        note_html = f'<div class="offer-note">{_esc(note)}</div>' if note else ""
        cards = []
        for index, item in enumerate(items):
            rich = "<br>".join(_esc(part.strip()) for part in str(item).split("|"))
            tone = " good" if index == 1 else ""
            cards.append(f'<div id="{ident}-o{index}" class="offer-card{tone}">{rich}</div>')
            animations.append(_pop(f"#{ident}-o{index}", events[index]["at"]))
        body = f'<div class="offer-col">{kicker}<div class="offer-row">{"".join(cards)}</div>{note_html}</div>'

    elif motif == "flow_line":
        items = list(stage.get("items") or ["From", "To"])[:2]
        while len(items) < 2:
            items.append("Next")
        body = (f'<div class="flow"><div id="{ident}-f0" class="flow-label">{_esc(items[0])}</div>'
                f'<div id="{ident}-dash" class="flow-dash"></div>'
                f'<div id="{ident}-f1" class="flow-label">{_esc(items[1])}</div></div>')
        animations.append(_pop(f"#{ident}-f0", events[0]["at"]))
        animations.append(_pop(f"#{ident}-f1", events[1]["at"]))
        animations.append(
            f'tl.fromTo("#{ident}-dash",{{scaleX:0}},{{scaleX:1,duration:0.35,ease:"power2.out",'
            f'transformOrigin:"0% 50%",immediateRender:true}},{events[1]["at"]});')

    elif motif == "pill":
        label = stage.get("label") or stage.get("text") or "Comment"
        body = (f'<div class="pill-wrap"><div id="{ident}-pill" class="pill">{_esc(label)}</div></div>')
        animations.append(_pop(f"#{ident}-pill", events[0]["at"]))

    elif motif == "cursor_mock":
        label = stage.get("label") or stage.get("text") or "Publish"
        body = (f'<div id="{ident}-ui" class="cursor-ui"><div id="{ident}-btn" class="cursor-btn">{_esc(label)}</div>'
                f'<div id="{ident}-cursor" class="cursor-ptr"></div></div>')
        animations.append(_slide(f"#{ident}-ui", events[0]["at"]))
        click_at = events[1]["at"]
        animations.append(
            f'tl.fromTo("#{ident}-cursor",{{x:86,y:48}},{{x:8,y:6,duration:0.32,'
            f'ease:"power2.out",immediateRender:true}},{events[0]["at"] + 0.08:.3f});')
        animations.append(
            f'tl.to("#{ident}-btn",{{scale:0.94,duration:0.08,yoyo:true,repeat:1,ease:"power1.inOut"}},{click_at:.3f});')

    elif motif == "vacuum_merge":
        items = list(stage.get("items") or ["Hook", "Proof", "Offer", "Close"])[:6]
        result = stage.get("label") or "One system"
        chips = []
        pop_events = [event for event in events if event["kind"] == "pop"]
        offsets = ((-90, -36), (90, -28), (-70, 42), (84, 40), (-16, -62), (24, 58))
        for index, item in enumerate(items):
            chips.append(f'<div id="{ident}-v{index}" class="vac-chip">{_esc(item)}</div>')
            at = pop_events[index]["at"] if index < len(pop_events) else start
            ox, oy = offsets[index % len(offsets)]
            animations.append(_pop(f"#{ident}-v{index}", at))
            animations.append(f'tl.set("#{ident}-v{index}",{{x:{ox},y:{oy}}},{at:.3f});')
            animations.append(
                f'tl.to("#{ident}-v{index}",{{x:0,y:0,opacity:0,duration:0.26,ease:"power2.in"}},'
                f'{_clamp(start + 0.48, start, end):.3f});')
        merge_at = next(event["at"] for event in events if event["kind"] == "ding")
        body = (f'<div class="vac">{"".join(chips)}'
                f'<div id="{ident}-result" class="vac-result">{_esc(result)}</div></div>')
        animations.append(_pop(f"#{ident}-result", merge_at))

    elif motif == "state_swap":
        items = list(stage.get("items") or ["Wrong", "Right"])[:2]
        while len(items) < 2:
            items.append("Right")
        swipe = next(event["at"] for event in events if event["kind"] == "error")
        good = next(event["at"] for event in events if event["kind"] == "ding")
        # Both cards are on screen together. The losing card tints and swipes
        # off. The winner then fills the middle so the panel is not half empty.
        label = stage.get("label") or ""
        label_html = f'<div class="mono rev-label">{_esc(label)}</div>' if label else ""
        body = (
            f'<div class="swap side"><div id="{ident}-bad" class="swap-card bad">'
            f'<div id="{ident}-tint" class="bad-tint"></div><b>{_esc(items[0])}</b></div>'
            f'<div id="{ident}-good" class="swap-card good"><b>{_esc(items[1])}</b>'
            f'<svg class="rev" viewBox="0 0 220 90"><path id="{ident}-line" '
            f'd="M8 78 L48 70 L82 58 L120 40 L160 22 L208 8" fill="none" stroke="{accent}" '
            f'stroke-width="6" stroke-linecap="round" stroke-dasharray="320"/>'
            f'<circle id="{ident}-dot" cx="208" cy="8" r="6" fill="{accent}" opacity="0"/></svg>'
            f'{label_html}</div></div>')
        animations.append(_pop(f"#{ident}-bad", events[0]["at"]))
        animations.append(_pop(f"#{ident}-good", events[0]["at"] + 0.1))
        animations.append(
            f'tl.to("#{ident}-tint",{{opacity:0.72,duration:0.12,ease:"power1.out"}},{swipe:.3f});')
        animations.append(
            f'tl.to("#{ident}-bad",{{x:280,opacity:0,rotation:8,duration:0.22,ease:"power2.in"}},{swipe:.3f});')
        animations.append(
            f'tl.to("#{ident}-good",{{flexBasis:"100%",maxWidth:"100%",duration:0.34,ease:"power2.out"}},{swipe + 0.16:.3f});')
        animations.append(
            f'tl.to("#{ident}-good",{{boxShadow:"0 24px 48px rgba(0,0,0,0.45), 0 0 42px {accent}aa",'
            f'duration:0.28}},{float(good):.3f});')
        animations.append(
            f'tl.fromTo("#{ident}-line",{{strokeDashoffset:320}},{{strokeDashoffset:0,duration:0.7,'
            f'ease:"power2.out"}},{float(good):.3f});')
        animations.append(_snap_in(
            f"#{ident}-dot", f"{float(good) + 0.55:.3f}", "scale:0", "scale:1", 0.2))

    else:
        raise ValueError(f"unknown stage motif: {motif}")

    body += _stage_chip(ident, stage)

    # A slow push so a held graphic never sits dead still.
    hold = max(0.6, float(end) - float(start) - 0.28)
    drift = 1.0 + min(0.08, max(0.05, hold * 0.012))
    animations.append(
        f'tl.fromTo("#{ident}",{{scale:1}},{{scale:{drift:.3f},duration:{hold:.3f},ease:"none",'
        f'transformOrigin:"50% 46%",immediateRender:false}},{float(start) + 0.22:.3f});')

    style = (f'left:{box["left"]}px;top:{box["top"]}px;width:{box["width"]}px;height:{box["height"]}px;'
             f'--accent:{accent};--strong:{strong};--text:{text};--muted:{muted};--surface:{surface};'
             f'--border:{border};--contrast:{contrast};--warning:{warning};--on:{on_accent};--soft:{soft};')
    # A playing screen recording times itself. Nesting that video in a timed section
    # fails HyperFrames' video_nested_in_timed_element lint, so the chrome shows with GSAP.
    if _is_video_url(media_url):
        # A hard cut. Opacity stays 1 so the panel cannot fade in over a couple of frames.
        if float(start) > 0.02:
            animations.append(f'tl.set("#{ident}",{{visibility:"hidden"}},{0});')
        animations.append(f'tl.set("#{ident}",{{visibility:"visible",opacity:1}},{float(start):.3f});')
        animations.append(f'tl.set("#{ident}",{{visibility:"hidden"}},{float(end):.3f});')
        section = (f'<section id="{ident}" class="stage" data-layout-allow-overflow '
                   f'style="visibility:hidden;opacity:1;{style}">{body}</section>')
    else:
        section = (
            f'<section id="{ident}" class="stage clip" data-start="{start:.3f}" data-duration="{duration:.3f}" '
            f'data-track-index="{int(track_index)}" data-layout-allow-overflow style="{style}">'
            f'{body}</section>')
    return section, animations, events
