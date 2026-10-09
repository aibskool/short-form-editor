"""Graphic-stage motifs for the Kallaway split layout, drawn in the active brand theme."""
import html
import json


MOTIFS = (
    "thumbnail_grid", "phone_frame", "broll_card", "numbered_list", "line_chart",
    "bar_chart", "counter", "highlight_box", "hand_circle", "doc_fan", "typing_ui",
    "mind_map", "logo_row", "quote_card", "offer_pair", "flow_line", "pill",
)


def _esc(value):
    return html.escape(str(value), quote=True)


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


def image_height_percent(stage):
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
    """First moment a stroke may appear: after the entrance, after the pan, and on the word if the word is later."""
    settled = float(motion["entrance_end"])
    if motion.get("scroll_end") is not None:
        settled = max(settled, float(motion["scroll_end"]))
    moment = max(settled, float(cue))
    latest = max(settled, float(end) - 0.05)
    return round(min(moment, latest), 3)


def resolve_annotations(stage, start, end):
    """Write the draw time onto callout and highlight, and remember the pan window.

    `cue_at` keeps the spoken word. `at` becomes the moment the stroke starts.
    A second call leaves an already resolved stage alone.
    """
    if stage.get("motion"):
        return stage["motion"]
    motion = motion_window(stage, start, end)
    stage["motion"] = {
        "entrance_end": motion["entrance_end"],
        "scroll_start": motion["scroll_start"],
        "scroll_end": motion["scroll_end"],
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
    """Map a settled viewport box onto the tall screenshot, in percentages of that image."""
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
    return f'<div id="{ident}-chip" class="stage-chip {tone}">{_esc(chip.get("text", ""))}</div>'


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
        return events
    if motif == "numbered_list":
        items = stage.get("items") or ["One", "Two", "Three", "Four"]
        if stage.get("hold"):
            return [{"at": round(start, 3), "kind": "click"}]
        return [{"at": t, "kind": "click"} for t in _times(start, end, min(6, len(items)), 1.6)]
    if motif == "line_chart":
        nodes = _times(start + 0.16, end, 3, 0.9)
        return [{"at": round(start, 3), "kind": "whoosh"}] + [{"at": t, "kind": "ding"} for t in nodes]
    if motif == "bar_chart":
        if stage.get("reveal") == "slice":
            rise = min(0.55, max(0.28, (end - start) * 0.4))
            return [{"at": round(start, 3), "kind": "riser"},
                    {"at": _clamp(start + rise, start, end), "kind": "ding"}]
        count = int(stage.get("count") or len(stage.get("heights") or []) or 4)
        return [{"at": t, "kind": "pop"} for t in _times(start, end, max(1, count), 0.8)]
    if motif == "counter":
        ticks = _times(start, min(end, start + 0.9), 6, 0.8)
        events = [{"at": t, "kind": "ticking"} for t in ticks]
        events.append({"at": round(min(end - 0.08, start + 0.95), 3), "kind": "ding"})
        return events
    if motif == "highlight_box":
        # The line waits until the card slide has finished.
        draw = round(min(end - 0.05, start + ENTRANCE_SECONDS), 3)
        return [{"at": round(start, 3), "kind": "whoosh"}, {"at": draw, "kind": "pop"}]
    if motif == "hand_circle":
        return [{"at": round(start + 0.05, 3), "kind": "marker"}]
    if motif == "doc_fan":
        return [{"at": t, "kind": "paper"} for t in _times(start, end, int(stage.get("count", 5)), 1.15)]
    if motif == "typing_ui":
        return [{"at": t, "kind": "typing"} for t in _times(start, min(end, start + 1.15), 8, 1.05)]
    if motif == "mind_map":
        branches = _times(start + 0.12, end, 3, 0.9)
        return [{"at": round(start, 3), "kind": "pop"}] + [{"at": t, "kind": "ding"} for t in branches]
    if motif == "logo_row":
        return [{"at": t, "kind": "pop"} for t in _times(start, end, 3, 0.7)] + [
            {"at": round(min(end - 0.05, start + 0.2), 3), "kind": "whoosh"}]
    if motif == "quote_card":
        events = [{"at": round(start, 3), "kind": "pop"}]
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
    return []


def _pop(selector, at):
    return (f'tl.fromTo("{selector}",{{scale:0.8}},{{scale:1,duration:0.34,ease:"back.out(1.7)",'
            f'transformOrigin:"50% 50%",immediateRender:false}},{at});')


def _slide(selector, at):
    return (f'tl.fromTo("{selector}",{{y:78,opacity:0}},{{y:0,opacity:1,duration:0.4,ease:kallawaySlide,'
            f'immediateRender:false}},{at});')


def motif_markup(motif, stage, start, end, box, colors, ident, media_url=None, track_index=2):
    stage = stage or {}
    if motif in {"phone_frame", "broll_card"}:
        resolve_annotations(stage, start, end)
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
        scroll = stage.get("scroll") or {}
        desat = float(stage.get("desaturate") or 0)
        detailed = bool(scroll or desat or stage.get("callout") or stage.get("highlight"))
        motion = stage.get("motion") or resolve_annotations(stage, start, end)
        img_h = image_height_percent(stage)
        sat = max(0.0, min(1.0, 1.0 - desat))
        scroll_to = float(scroll.get("to", 0)) if scroll else 0
        if media_url:
            picture = (f'<img id="{ident}-img" src="{_esc(media_url)}" alt="" '
                       f'style="position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;'
                       f'filter:saturate({sat:.3f})">')
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
            _left, top, _width, _height = screenshot_box(
                {"x": 0, "y": highlight.get("y", 0.4), "w": 1, "h": 0.08}, img_h, scroll_to)
            extras += (f'<div id="{ident}-hl" class="hl-line phone-hl" style="top:{top:.2f}%">'
                       f'{_esc(highlight.get("label") or "")}</div>')
        thumb = "" if detailed else f'<div id="{ident}-thumb" class="thumb-dot"></div>'
        klass = "phone fill" if media_url and detailed else "phone"
        body = (f'<div id="{ident}-phone" class="{klass}"><div class="phone-screen">'
                f'<div id="{ident}-pan" class="phone-pan" style="height:{img_h:.0f}%">{picture}{extras}</div>'
                f'<div class="phone-bar"><div id="{ident}-prog"></div></div>{thumb}</div></div>')
        animations.append(_slide(f"#{ident}-phone", events[0]["at"]))
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
            animations.append(f'tl.set("#{ident}-ring",{{opacity:1}},{at:.3f});')
            animations.append(
                f'tl.fromTo("#{ident}-stroke",{{strokeDashoffset:{HAND_CIRCLE_LENGTH}}},'
                f'{{strokeDashoffset:0,duration:{draw:.2f},ease:"power1.inOut"}},{at:.3f});')
        if stage.get("highlight"):
            at = float(stage["highlight"]["at"])
            animations.append(
                f'tl.fromTo("#{ident}-hl",{{opacity:0,scale:0.92}},{{opacity:1,scale:1,duration:0.28,'
                f'ease:"back.out(1.7)",transformOrigin:"50% 50%",immediateRender:false}},{at:.3f});')

    elif motif == "broll_card":
        picture = (f'<img src="{_esc(media_url)}" alt="">' if media_url
                   else f'<div class="broll-fake"><span class="mono">B-ROLL</span></div>')
        body = (f'<div id="{ident}-card" class="broll-card">{picture}'
                f'<div class="broll-progress"><div id="{ident}-bar"></div></div></div>')
        animations.append(_slide(f"#{ident}-card", events[0]["at"]))
        animations.append(
            f'tl.fromTo("#{ident}-bar",{{scaleX:0}},{{scaleX:1,duration:{max(0.4, duration-0.35):.3f},ease:"none",transformOrigin:"0% 50%"}},{start+0.2});')

    elif motif == "numbered_list":
        items = list(stage.get("items") or ["Open on the split", "Cut closer", "Show the proof", "Ask for the comment"])[:6]
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
            animations.append(
                f'tl.fromTo("#{ident}-n{index}",{{scale:0.4,opacity:0}},{{scale:1,opacity:1,duration:0.28,'
                f'ease:"back.out(1.7)",transformOrigin:"50% 50%",immediateRender:false}},{events[index + 1]["at"]});')

    elif motif == "bar_chart":
        heights = list(stage.get("heights") or [42, 68, 38, 88])
        labels = list(stage.get("labels") or [])
        negative = bool(stage.get("negative"))
        sliced = stage.get("reveal") == "slice"
        count = min(len(heights), 5 if sliced else len(events))
        bars = []
        for index in range(count):
            color = warning if negative and index == 0 else (accent if index == count - 1 else border)
            caption = _esc(labels[index]) if index < len(labels) else f"{index+1:02d}"
            bars.append(
                f'<div class="bar-col"><div id="{ident}-b{index}" class="bar" '
                f'style="height:{heights[index]}%;background:{color}"></div>'
                f'<span class="mono">{caption}</span></div>')
            at = events[0]["at"] if sliced else events[index]["at"]
            animations.append(
                f'tl.fromTo("#{ident}-b{index}",{{scaleY:0}},{{scaleY:1,duration:0.42,ease:"back.out(1.4)",'
                f'transformOrigin:"50% 100%",immediateRender:false}},{at});')
        body = f'<div class="bars">{"".join(bars)}</div>'

    elif motif == "counter":
        target = int(stage.get("value", 30))
        label = stage.get("label") or ""
        prefix = json.dumps(str(stage.get("prefix") or ""))
        suffix = json.dumps(str(stage.get("suffix") or ""))
        variable = ident.replace("-", "_") + "n"
        label_html = f'<div class="mono count-label">{_esc(label)}</div>' if label else ""
        body = (f'<div class="counter"><div id="{ident}-num" class="count-num">{_esc(stage.get("prefix") or "")}0{_esc(stage.get("suffix") or "")}</div>'
                f'{label_html}</div>')
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
        animations.append(
            f'tl.fromTo("#{ident}-hl",{{opacity:0,scale:0.92}},{{opacity:1,scale:1,duration:0.28,'
            f'ease:"back.out(1.7)",transformOrigin:"50% 50%",immediateRender:false}},{events[1]["at"]});')

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
        pages = pages[:len(events)]
        fans = []
        spread = [-26, -13, 0, 13, 26]
        shifts = [-10, -5, 0, 5, 10]
        for index, page in enumerate(pages):
            kicker, title = page
            rot = spread[index] if index < len(spread) else 0
            shift = shifts[index] if index < len(shifts) else 0
            fans.append(
                f'<div class="page-rot" style="left:{16+shift}%;transform:rotate({rot}deg)">'
                f'<div id="{ident}-p{index}" class="page"><div class="page-rule"></div>'
                f'<div class="mono">{_esc(kicker)}</div><div class="page-title">{_esc(title)}</div></div></div>')
            animations.append(_pop(f"#{ident}-p{index}", events[index]["at"]))
        body = f'<div class="fan">{"".join(fans)}</div>'

    elif motif == "typing_ui":
        typed = stage.get("text") or "Turn the lesson into a client brief."
        body = (f'<div id="{ident}-win" class="window"><div class="chrome"><i></i><i></i><i></i>'
                f'<span class="mono">NOTES</span></div><div class="win-body">'
                f'<span id="{ident}-type"></span><span id="{ident}-caret" class="caret">|</span></div></div>')
        payload = json.dumps(typed)
        variable = ident.replace("-", "_") + "c"
        type_at = events[0]["at"]
        animations.append(_slide(f"#{ident}-win", start))
        animations.append(
            f'const {variable}={{n:0}};tl.to({variable},{{n:{len(typed)},duration:{min(1.15, max(0.4, duration-0.3)):.3f},'
            f'ease:"none",onUpdate:()=>{{const el=document.getElementById("{ident}-type");'
            f'if(el) el.textContent={payload}.slice(0,Math.floor({variable}.n));}}}},{type_at});')
        animations.append(
            f'tl.fromTo("#{ident}-caret",{{opacity:1}},{{opacity:0,duration:0.35,repeat:6,yoyo:true,ease:"none"}},{start});')

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
            cards.append(f'<div id="{ident}-o{index}" class="offer-card">{_esc(item)}</div>')
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
            f'tl.fromTo("#{ident}-dash",{{scaleX:0,opacity:0}},{{scaleX:1,opacity:1,duration:0.35,ease:"power2.out",'
            f'transformOrigin:"0% 50%",immediateRender:false}},{events[1]["at"]});')

    elif motif == "pill":
        label = stage.get("label") or stage.get("text") or "Comment"
        body = (f'<div class="pill-wrap"><div id="{ident}-pill" class="pill">{_esc(label)}</div></div>')
        animations.append(_pop(f"#{ident}-pill", events[0]["at"]))

    else:
        raise ValueError(f"unknown stage motif: {motif}")

    body += _stage_chip(ident, stage)

    # Colors that motifs reference through classes are set on the section via custom properties.
    section = (
        f'<section id="{ident}" class="stage clip" data-start="{start:.3f}" data-duration="{duration:.3f}" '
        f'data-track-index="{int(track_index)}" data-layout-allow-overflow '
        f'style="left:{box["left"]}px;top:{box["top"]}px;width:{box["width"]}px;height:{box["height"]}px;'
        f'--accent:{accent};--strong:{strong};--text:{text};--muted:{muted};--surface:{surface};'
        f'--border:{border};--contrast:{contrast};--warning:{warning};--on:{on_accent};--soft:{soft};">'
        f'{body}</section>')
    return section, animations, events
