"""Graphic-stage motifs for the Kallaway split layout, drawn in the active brand theme."""
import html
import json


MOTIFS = (
    "thumbnail_grid", "phone_frame", "broll_card", "numbered_list", "line_chart",
    "bar_chart", "counter", "highlight_box", "hand_circle", "doc_fan", "typing_ui",
    "mind_map", "logo_row",
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
        return [{"at": round(start, 3), "kind": "whoosh"}]
    if motif == "numbered_list":
        items = stage.get("items") or ["One", "Two", "Three", "Four"]
        return [{"at": t, "kind": "click"} for t in _times(start, end, min(6, len(items)), 1.6)]
    if motif == "line_chart":
        nodes = _times(start + 0.16, end, 3, 0.9)
        return [{"at": round(start, 3), "kind": "whoosh"}] + [{"at": t, "kind": "ding"} for t in nodes]
    if motif == "bar_chart":
        return [{"at": t, "kind": "pop"} for t in _times(start, end, int(stage.get("count", 4)), 0.8)]
    if motif == "counter":
        ticks = _times(start, min(end, start + 0.9), 6, 0.8)
        events = [{"at": t, "kind": "ticking"} for t in ticks]
        events.append({"at": round(min(end - 0.08, start + 0.95), 3), "kind": "ding"})
        return events
    if motif == "highlight_box":
        return [{"at": round(start, 3), "kind": "whoosh"},
                {"at": round(min(end - 0.05, start + 0.28), 3), "kind": "pop"}]
    if motif == "hand_circle":
        return [{"at": round(start + 0.05, 3), "kind": "marker"}]
    if motif == "doc_fan":
        return [{"at": t, "kind": "pop"} for t in _times(start, end, int(stage.get("count", 5)), 1.15)]
    if motif == "typing_ui":
        return [{"at": t, "kind": "typing"} for t in _times(start, min(end, start + 1.15), 8, 1.05)]
    if motif == "mind_map":
        branches = _times(start + 0.12, end, 3, 0.9)
        return [{"at": round(start, 3), "kind": "pop"}] + [{"at": t, "kind": "ding"} for t in branches]
    if motif == "logo_row":
        return [{"at": t, "kind": "pop"} for t in _times(start, end, 3, 0.7)] + [
            {"at": round(min(end - 0.05, start + 0.2), 3), "kind": "whoosh"}]
    return []


def _pop(selector, at):
    return (f'tl.fromTo("{selector}",{{scale:0.8}},{{scale:1,duration:0.34,ease:"back.out(1.7)",'
            f'transformOrigin:"50% 50%",immediateRender:false}},{at});')


def _slide(selector, at):
    return (f'tl.fromTo("{selector}",{{y:78,opacity:0}},{{y:0,opacity:1,duration:0.4,ease:kallawaySlide,'
            f'immediateRender:false}},{at});')


def motif_markup(motif, stage, start, end, box, colors, ident, media_url=None):
    stage = stage or {}
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
        screen = (f'<img src="{_esc(media_url)}" alt="">' if media_url
                  else f'<div class="phone-fake"><b style="color:{text}">Preview</b><span class="mono" style="color:{muted}">9:16</span></div>')
        body = (f'<div id="{ident}-phone" class="phone"><div class="phone-screen">{screen}'
                f'<div class="phone-bar"><div id="{ident}-prog"></div></div>'
                f'<div id="{ident}-thumb" class="thumb-dot"></div></div></div>')
        animations.append(_slide(f"#{ident}-phone", events[0]["at"]))
        animations.append(
            f'tl.fromTo("#{ident}-prog",{{scaleX:0}},{{scaleX:1,duration:{max(0.4, duration-0.45):.3f},ease:"none",transformOrigin:"0% 50%"}},{start+0.35});')
        animations.append(
            f'tl.fromTo("#{ident}-thumb",{{y:40}},{{y:-120,duration:{max(0.4, duration-0.5):.3f},ease:"power1.inOut"}},{start+0.4});')

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
        rows = []
        for index, item in enumerate(items):
            blur = "filter:blur(4px);opacity:0.45;" if index else ""
            rows.append(
                f'<div id="{ident}-row{index}" class="nrow" style="height:{row_h:.2f}%;{blur}">'
                f'<span class="mono">{index+1:02d}</span><b>{_esc(item)}</b></div>')
        body = (f'<div class="nlist">{"".join(rows)}'
                f'<div id="{ident}-box" class="nbox" style="height:{row_h - 2:.2f}%"></div></div>')
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
        heights = stage.get("heights") or [42, 68, 38, 88]
        negative = bool(stage.get("negative"))
        bars = []
        count = min(len(heights), len(events), 5)
        for index in range(count):
            color = warning if negative and index == 0 else (accent if index == count - 1 else border)
            bars.append(
                f'<div class="bar-col"><div id="{ident}-b{index}" class="bar" '
                f'style="height:{heights[index]}%;background:{color}"></div>'
                f'<span class="mono">{index+1:02d}</span></div>')
            animations.append(
                f'tl.fromTo("#{ident}-b{index}",{{scaleY:0}},{{scaleY:1,duration:0.36,ease:"back.out(1.4)",'
                f'transformOrigin:"50% 100%",immediateRender:false}},{events[index]["at"]});')
        body = f'<div class="bars">{"".join(bars)}</div>'

    elif motif == "counter":
        target = int(stage.get("value", 30))
        label = stage.get("label") or "ideas"
        body = (f'<div class="counter"><div id="{ident}-num" class="count-num">0</div>'
                f'<div class="mono count-label">{_esc(label)}</div></div>')
        animations.append(
            f'const {ident.replace("-", "_")}n={{v:0}};'
            f'tl.to({ident.replace("-", "_")}n,{{v:{target},duration:0.9,ease:"power2.out",'
            f'onUpdate:()=>{{const el=document.getElementById("{ident}-num");'
            f'if(el) el.textContent=Math.round({ident.replace("-", "_")}n.v).toLocaleString("en-US");}}}},{start});')
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
        animations.append(_pop(f"#{ident}-hl", events[1]["at"]))

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
    else:
        raise ValueError(f"unknown stage motif: {motif}")

    # Colors that motifs reference through classes are set on the section via custom properties.
    section = (
        f'<section id="{ident}" class="stage clip" data-start="{start:.3f}" data-duration="{duration:.3f}" '
        f'data-track-index="2" data-layout-allow-overflow '
        f'style="left:{box["left"]}px;top:{box["top"]}px;width:{box["width"]}px;height:{box["height"]}px;'
        f'--accent:{accent};--strong:{strong};--text:{text};--muted:{muted};--surface:{surface};'
        f'--border:{border};--contrast:{contrast};--warning:{warning};--on:{on_accent};--soft:{soft};">'
        f'{body}</section>')
    return section, animations, events
