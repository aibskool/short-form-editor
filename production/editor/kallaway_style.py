"""Build a HyperFrames composition in the Kallaway split / full / punch-in grammar.

Colors and fonts come from the theme preset. Existing presenter timelines never enter this module.
"""
import json
import os
from pathlib import Path
import shutil

from edit import escape, map_words, probe, read_words, resolve, validate_music
from kallaway_motifs import motif_markup

HERE = Path(__file__).resolve().parent
DEFAULT_THEME = HERE / "themes" / "ai-builder-school.json"


def load_theme(mode=None, theme_path=None):
    path = Path(theme_path) if theme_path else DEFAULT_THEME
    if not path.is_file():
        raise ValueError(f"theme preset not found: {path}")
    data = json.loads(path.read_text())
    selected = mode or data.get("default_mode", "dark")
    if selected not in data["modes"]:
        raise ValueError(f"theme has no mode {selected}")
    return data, data["modes"][selected], selected, path


def font_faces(theme, media):
    rules = []
    seen = set()
    for role, font in theme["fonts"].items():
        key = (font["family"], font["weight"], font["file"])
        if key in seen:
            continue
        seen.add(key)
        source = HERE / font["file"]
        if not source.is_file():
            raise ValueError(f"bundled font missing: {source}")
        url = media(str(source))
        rules.append(
            f"@font-face{{font-family:'{font['family']}';src:url('{url}') format('truetype');"
            f"font-weight:{int(font['weight'])};font-style:normal;font-display:block;}}")
    return "".join(rules)


def card_state(layout, crop, width, height, layout_spec, colors):
    if layout == "split":
        margin = layout_spec["card_margin_x"] * width
        top = layout_spec["card_top"] * height
        bottom = layout_spec["card_bottom"] * height
        scale = layout_spec["tight_scale"] if crop == "tight" else layout_spec["wide_scale"]
        return {
            "left": round(margin), "top": round(top),
            "width": round(width - 2 * margin), "height": round(bottom - top),
            "borderRadius": round(layout_spec["card_radius"] * width / 1080),
            "boxShadow": colors["card_shadow"], "scale": scale,
        }
    scale = layout_spec["punch_scale"] if layout == "punch_in" else 1
    return {"left": 0, "top": 0, "width": width, "height": height,
            "borderRadius": 0, "boxShadow": "none", "scale": scale}


def _caption_text(word, omit_punct=True, keep_case=()):
    """On-screen caption. `display` is the authored spelling. `keep_case` preserves PAID, AI, ADA."""
    if word.get("display"):
        return str(word["display"])
    text = str(word.get("word", word.get("text", ""))).strip()
    bare = text.strip(".,!?:;\"'").lower()
    kept = {item.lower(): item for item in keep_case}
    if bare in kept:
        return kept[bare]
    if omit_punct:
        text = text.strip(".,!?:;\"'")
    return text.lower()


def _word_style(word, styles):
    if word.get("style") in {"normal", "marker", "green", "amber"}:
        return word["style"]
    token = "".join(ch for ch in str(word.get("word", word.get("text", ""))).lower() if ch.isalnum() or ch == "'")
    return styles.get(token, "normal")


def build_kallaway(spec, spec_path, project):
    spec_path, project = Path(spec_path).resolve(), Path(project).resolve()
    project.mkdir(parents=True, exist_ok=True)
    assets = project / "assets"
    assets.mkdir(exist_ok=True)
    copied = {}

    def media(value):
        source = resolve(value, spec_path.parent)
        if not source.is_file() or not source.stat().st_size:
            raise ValueError(f"media missing or empty: {source}")
        if source not in copied:
            target = assets / f"media-{len(copied):03d}{source.suffix.lower()}"
            if target.exists() and not os.path.samefile(source, target):
                target.unlink()
            if not target.exists():
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copy2(source, target)
            copied[source] = target.relative_to(project).as_posix()
        return copied[source]

    theme, colors, mode, theme_path = load_theme(spec.get("theme_mode"), spec.get("theme_path"))
    if spec.get("theme") not in (None, theme["id"]):
        raise ValueError(f"theme id {spec.get('theme')} does not match {theme['id']}")
    layout_spec = theme["layout"]
    output = spec.get("output", {})
    width = int(output.get("width", 1080))
    height = int(output.get("height", 1920))
    fps = int(output.get("fps", 30))
    scale = width / 1080
    source_path = resolve(spec["source"]["path"], spec_path.parent)
    source_info = probe(source_path)
    source_duration = float(source_info["format"]["duration"])
    segments = spec["source"].get("segments") or [{"start": 0, "end": source_duration}]
    for segment in segments:
        if not 0 <= float(segment["start"]) < float(segment["end"]) <= source_duration + 0.05:
            raise ValueError("source segment lies outside the source video")
    duration = sum(float(segment["end"]) - float(segment["start"]) for segment in segments)
    position = spec["source"].get("object_position", layout_spec["object_position"])
    gsap = HERE / "node_modules/gsap/dist/gsap.min.js"
    if not gsap.is_file():
        raise ValueError("run npm ci in production/editor before building")
    shutil.copy2(gsap, assets / "gsap.min.js")

    parts, animations, audio = [], [], []
    source = media(str(source_path))
    has_audio = any(stream.get("codec_type") == "audio" for stream in source_info["streams"])
    cursor = 0.0
    for index, segment in enumerate(segments):
        length = float(segment["end"]) - float(segment["start"])
        timing = f'data-start="{cursor:.6f}" data-duration="{length:.6f}" data-media-start="{segment["start"]}"'
        parts.append(f'<video id="aroll-{index}" class="aroll clip" src="{source}" {timing} data-track-index="0" muted playsinline></video>')
        if has_audio:
            audio.append(f'<audio id="voice-{index}" src="{source}" {timing} data-track-index="10" data-volume="1"></audio>')
        cursor += length

    shots = spec.get("shots") or []
    if not shots:
        raise ValueError("kallaway timeline needs shots")
    first = card_state(shots[0].get("layout", "split"), shots[0].get("crop", "wide"),
                       width, height, layout_spec, colors)
    stage_box = {
        "left": round(layout_spec["stage_left"] * width),
        "top": round(layout_spec["stage_top"] * height),
        "width": round(layout_spec["stage_width"] * width),
        "height": round(layout_spec["stage_height"] * height),
    }
    for index, shot in enumerate(shots):
        start, end = float(shot["start"]), float(shot["end"])
        if not 0 <= start < end <= duration + 0.05:
            raise ValueError(f"shot {index} lies outside output timeline")
        layout = shot.get("layout", "split")
        if layout not in {"split", "full", "punch_in"}:
            raise ValueError(f"unknown kallaway layout: {layout}")
        for banned in ("transition", "crossfade", "fade", "whip"):
            if banned in shot:
                raise ValueError(f"shot {index} uses {banned}; kallaway layouts are hard cuts")
        state = card_state(layout, shot.get("crop", "wide"), width, height, layout_spec, colors)
        if shot.get("scale"):
            state["scale"] = float(shot["scale"])
        payload = {key: state[key] for key in ("left", "top", "width", "height", "borderRadius", "boxShadow")}
        animations.append(f'tl.set("#speaker-card",{json.dumps(payload)},{start});')
        animations.append(
            f'tl.set("#presenter-camera",{{scale:{state["scale"]},transformOrigin:"50% 30%"}},{start});')
        if shot.get("object_position"):
            animations.append(
                f'tl.set(".aroll",{{objectPosition:{json.dumps(shot["object_position"])}}},{start});')
        caption_y = layout_spec["caption_split_y"] if layout == "split" else layout_spec["caption_full_y"]
        animations.append(f'tl.set("#caption-anchor",{{top:"{shot.get("caption_y", caption_y * 100):.2f}%"}},{start});')
        if layout == "split" and shot.get("stage"):
            stage = dict(shot["stage"])
            media_url = media(stage["media"]) if stage.get("media") else None
            section, motion, _events = motif_markup(
                stage.get("motif", "thumbnail_grid"), stage, start, end, stage_box, colors, f"stage-{index}", media_url)
            parts.append(section)
            animations.extend(motion)
        for overlay_index, overlay in enumerate(shot.get("overlays") or []):
            overlay_media = media(overlay["media"]) if overlay.get("media") else None
            section, motion, _events = motif_markup(
                overlay.get("motif"), overlay, float(overlay["start"]), float(overlay["end"]),
                stage_box, colors, f"over-{index}-{overlay_index}", overlay_media, track_index=3)
            parts.append(section)
            animations.extend(motion)

    words = map_words(read_words(resolve(spec["words_path"], spec_path.parent)), segments) if spec.get("words_path") else []
    captions = spec.get("captions", {})
    styles = {str(key).lower(): value for key, value in captions.get("word_styles", {}).items()}
    keep_case = captions.get("keep_case") or []
    phrases = captions.get("phrases") or []
    if phrases:
        groups = []
        cursor_index = 0
        for phrase in phrases:
            begin, finish = phrase["word_range"]
            if begin != cursor_index or not begin < finish <= len(words):
                raise ValueError("caption phrases must cover words once, in order")
            groups.append(words[begin:finish])
            cursor_index = finish
        if cursor_index != len(words):
            raise ValueError("caption phrases do not cover the complete transcript")
    else:
        groups = [[word] for word in words]
    parts.append('<div id="caption-anchor">')
    for index, group in enumerate(groups):
        start = float(group[0]["start"])
        end = float(group[-1]["end"]) if index + 1 == len(groups) else float(groups[index + 1][0]["start"])
        end = min(duration, max(end, start + 0.08))
        spans = []
        for word in group:
            style = _word_style(word, styles)
            spans.append(
                f'<span class="cap {style}">{escape(_caption_text(word, captions.get("omit_terminal_punctuation", True), keep_case))}</span>')
        parts.append(
            f'<div id="cap-{index}" class="caption clip" data-start="{start:.4f}" data-duration="{max(0.04, end-start):.4f}" '
            f'data-track-index="5"><div id="capbox-{index}" class="caption-text">{" ".join(spans)}</div></div>')
        animations.append(
            f'tl.fromTo("#capbox-{index}",{{scale:0.9}},{{scale:1,duration:0.12,ease:"power2.out"}},{start:.4f});')
    parts.append("</div>")

    for index, header in enumerate(spec.get("headers") or []):
        start, end = float(header["start"]), float(header["end"])
        if end <= start:
            continue
        kind = header.get("variant", "headline")
        emphasis = {word.lower() for word in header.get("emphasis") or []}
        size_style = f' style="font-size:{float(header["size"]) * scale:.1f}px"' if header.get("size") else ""
        lines = header.get("lines") or []
        if lines:
            green = {int(line_no) for line_no in header.get("green_lines") or []}
            blocks = []
            for line_index, line in enumerate(lines):
                css_class = "header-line key" if line_index in green else "header-line"
                blocks.append(f'<div class="{css_class}">{escape(line)}</div>')
            inner = f'<div class="header-text"{size_style}>{"".join(blocks)}</div>'
        elif kind == "label":
            inner = f'<div class="header-label"{size_style}>{escape(header.get("text", ""))}</div>'
        else:
            pieces = []
            for token in str(header.get("text", "")).split(" "):
                bare = token.strip(".,!?:;\"'").lower()
                if bare in emphasis:
                    pieces.append(f'<span class="key">{escape(token)}</span>')
                else:
                    pieces.append(escape(token))
            sub = f'<div class="header-sub">{escape(header["sub"])}</div>' if header.get("sub") else ""
            inner = f'<div class="header-text">{" ".join(pieces)}</div>{sub}'
        parts.append(
            f'<div id="hdr-{index}" class="header clip" data-start="{start:.4f}" data-duration="{end-start:.4f}" '
            f'data-track-index="4">{inner}</div>')

    mono_family = theme["fonts"]["mono"]["family"]
    for index, notice in enumerate(spec.get("notices") or []):
        start, end = float(notice["start"]), float(notice["end"])
        parts.append(
            f'<div id="notice-{index}" class="notice clip" data-start="{start:.4f}" data-duration="{end-start:.4f}" '
            f'data-track-index="6" style="color:{colors["muted"]};background:{colors["surface"]};'
            f"font-family:'{mono_family}',monospace\">{escape(notice.get('text', ''))}</div>")
    for index, chip in enumerate(spec.get("chips") or []):
        start, end = float(chip["start"]), float(chip["end"])
        parts.append(
            f'<div id="chip-{index}" class="chip-corner clip" data-start="{start:.4f}" data-duration="{end-start:.4f}" '
            f'data-track-index="7" style="background:{colors["accent"]};color:{colors["on_accent"]};'
            f"font-family:'{mono_family}',monospace\">{escape(chip.get('text', ''))}</div>")

    from kallaway_audio import SFX_KINDS, write_sfx_library
    library = spec_path.parent / "sfx"
    if any(sound.get("kind") for sound in spec.get("sfx", [])) and not (library / "pop.wav").is_file():
        write_sfx_library(library)
    for index, sound in enumerate(spec.get("sfx", [])):
        if sound.get("kind"):
            if sound["kind"] not in SFX_KINDS:
                raise ValueError(f"unknown sfx kind: {sound['kind']}")
            path = media(str(library / f"{sound['kind']}.wav"))
            length = float(probe(project / path)["format"]["duration"])
        else:
            path = media(sound["path"])
            length = float(sound.get("duration", probe(project / path)["format"]["duration"]))
        gain = sound.get("gain", theme.get("sfx_gain", {}).get(sound.get("kind"), 0.35))
        audio.append(
            f'<audio id="sfx-{index}" src="{path}" data-start="{float(sound["at"]):.4f}" data-duration="{length:.4f}" '
            f'data-track-index="{20+index}" data-volume="{float(gain):.4f}"></audio>')

    for index, sound in enumerate(spec.get("music", [])):
        path, start, end, source_start, gain, envelope = validate_music(sound, spec_path, project, duration, index)
        relative = media(str(path))
        timing = (f'data-start="{start:.6f}" data-duration="{end-start:.6f}" data-media-start="{source_start:.6f}" '
                  f'data-track-index="{11+index}" data-volume="{gain:.6f}"')
        automation = ""
        if envelope is not None:
            payload = {"version": 1, "lanes": [{"target": "volume", "points": [{"t": float(point["t"]), "v": float(point["v"])} for point in envelope]}]}
            automation = f' data-automation="{escape(json.dumps(payload, separators=(",", ":")))}"'
        audio.append(f'<audio id="music-{index}" src="{relative}" {timing}{automation}></audio>')

    grid = colors["grid"]
    if colors.get("grid_style") == "lines":
        background = (f"background-color:{colors['background']};background-image:"
                      f"linear-gradient({grid} 1px,transparent 1px),linear-gradient(90deg,{grid} 1px,transparent 1px);"
                      f"background-size:{layout_spec['dot_spacing']*scale:.0f}px {layout_spec['dot_spacing']*scale:.0f}px;")
    else:
        spacing = layout_spec["dot_spacing"] * scale
        background = (f"background-color:{colors['background']};background-image:radial-gradient({grid} {1.25*scale:.2f}px,transparent {1.5*scale:.2f}px);"
                      f"background-size:{spacing:.0f}px {spacing:.0f}px;")
    display = theme["fonts"]["display"]["family"]
    caption = theme["fonts"]["caption"]["family"]
    mono = theme["fonts"]["mono"]["family"]
    caption_px = layout_spec["caption_font_px"] * scale
    title_px = layout_spec["title_font_px"] * scale
    mono_px = layout_spec["mono_font_px"] * scale
    css = f'''{font_faces(theme, media)}
    *{{box-sizing:border-box}} body{{margin:0;background:{colors['background']}}}
    #root{{position:relative;width:{width}px;height:{height}px;overflow:hidden;{background}}}
    #speaker-card{{position:absolute;left:{first['left']}px;top:{first['top']}px;width:{first['width']}px;height:{first['height']}px;overflow:hidden;z-index:4;border-radius:{first['borderRadius']}px;box-shadow:{first['boxShadow']};background:{colors['contrast']}}}
    #presenter-camera{{position:absolute;inset:0;transform-origin:50% 30%;width:100%;height:100%}}
    .aroll{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{position}}}
    .stage{{position:absolute;z-index:2;overflow:hidden}}
    #caption-anchor{{position:absolute;top:{layout_spec['caption_split_y']*100:.2f}%;left:0;width:100%;z-index:8;pointer-events:none}}
    .caption{{position:absolute;left:6%;width:88%;text-align:center}}
    .caption-text{{display:inline-block;font-family:'{caption}',sans-serif;font-weight:900;font-size:{caption_px:.1f}px;line-height:1.02;letter-spacing:-0.03em;color:{colors['text']};text-shadow:{colors['caption_shadow']}}}
    .cap.marker{{font-family:'{display}',cursive;font-weight:400;font-size:1.12em;letter-spacing:0}}
    .cap.green{{color:{colors['accent']}}}
    .cap.amber{{color:{colors['warning_text']}}}
    .header{{position:absolute;top:{layout_spec['title_top']*100:.2f}%;left:7%;width:86%;z-index:8;text-align:center}}
    .header-text{{font-family:'{display}',cursive;font-weight:400;font-size:{title_px:.1f}px;line-height:0.98;color:{colors['text']};text-shadow:{colors['caption_shadow']}}}
    .header-line{{display:block}}
    .header-text .key,.header-line.key{{color:{colors['accent']}}}
    .header-sub{{margin-top:8px;font-family:'{mono}',monospace;font-size:{mono_px:.1f}px;letter-spacing:0.08em;text-transform:uppercase;color:{colors['muted']}}}
    .header-label{{display:inline-block;background:{colors['accent']};color:{colors['on_accent']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{title_px*0.62:.1f}px;line-height:1;padding:0.22em 0.45em;border-radius:8px}}
    .mono{{font-family:'{mono}',monospace;letter-spacing:0.08em;text-transform:uppercase}}
    .thumb-grid{{display:grid;grid-template-rows:1fr 1fr;gap:{14*scale:.0f}px;height:100%}}
    .thumb{{position:relative;border-radius:{16*scale:.0f}px;overflow:hidden;transform:scale(0.8);display:flex;flex-direction:column;justify-content:flex-end;padding:{12*scale:.0f}px;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{22*scale:.0f}px}}
    .thumb .mono{{position:absolute;top:{10*scale:.0f}px;left:{10*scale:.0f}px;color:{colors['muted']};font-size:{mono_px*0.8:.1f}px}}
    .thumb i{{position:absolute;right:{12*scale:.0f}px;bottom:{12*scale:.0f}px;color:{colors['muted']};font-style:normal;font-size:{16*scale:.0f}px}}
    .phone{{width:{430*scale:.0f}px;height:92%;margin:0 auto;background:{colors['contrast']};border-radius:{36*scale:.0f}px;padding:{12*scale:.0f}px;box-shadow:{colors['card_shadow']}}}
    .phone-screen{{position:relative;height:100%;border-radius:{26*scale:.0f}px;overflow:hidden;background:{colors['surface']};border:1px solid {colors['border']}}}
    .phone-screen img,.broll-card img,.shotcard img{{width:100%;height:100%;object-fit:cover}}
    .phone-fake,.broll-fake{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;background:linear-gradient(160deg,{colors['surface']},{colors['contrast']});color:{colors['text']};font-family:'{caption}',sans-serif}}
    .phone-bar{{position:absolute;left:8%;right:8%;bottom:8%;height:{8*scale:.0f}px;border-radius:99px;background:{colors['border']};overflow:hidden}}
    .phone-bar div,.broll-progress div{{height:100%;width:100%;background:{colors['accent']};transform:scaleX(0);transform-origin:0 50%}}
    .thumb-dot{{position:absolute;left:50%;bottom:18%;width:{54*scale:.0f}px;height:{54*scale:.0f}px;margin-left:{-27*scale:.0f}px;border-radius:50%;background:{colors['text']};opacity:0.9}}
    .broll-card{{width:100%;height:78%;border-radius:{22*scale:.0f}px;overflow:hidden;background:{colors['surface']};border:1px solid {colors['border']};position:relative}}
    .broll-progress{{position:absolute;left:0;right:0;bottom:0;height:{10*scale:.0f}px;background:{colors['border']}}}
    .nlist{{position:relative;height:100%}}
    .nrow{{display:flex;align-items:center;gap:{16*scale:.0f}px;padding:0 8%;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{40*scale:.0f}px}}
    .nrow .mono{{color:{colors['muted']};font-size:{mono_px:.1f}px;width:{64*scale:.0f}px}}
    .nbox{{position:absolute;left:4%;right:4%;top:0;border:3px solid {colors['accent_strong']};border-radius:{16*scale:.0f}px;pointer-events:none}}
    .chart{{width:100%;height:86%}}
    .chart-label{{text-align:right;color:{colors['muted']};font-size:{mono_px:.1f}px}}
    .bars{{display:flex;align-items:flex-end;justify-content:space-between;height:100%;gap:{18*scale:.0f}px;padding:0 6% 8%}}
    .bar-col{{flex:1;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:8px}}
    .bar{{width:70%;border-radius:{10*scale:.0f}px {10*scale:.0f}px 0 0;transform:scaleY(0);transform-origin:50% 100%}}
    .bar-col .mono{{color:{colors['muted']};font-size:{mono_px*0.85:.1f}px}}
    .counter{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center}}
    .count-num{{font-family:'{caption}',sans-serif;font-weight:900;font-size:{210*scale:.0f}px;line-height:0.9;color:{colors['accent']};letter-spacing:-0.04em}}
    .count-label{{color:{colors['muted']};font-size:{mono_px:.1f}px;margin-top:12px}}
    .shotcard{{height:100%;border-radius:{20*scale:.0f}px;background:{colors['surface']};border:1px solid {colors['border']};padding:8% 8%;display:flex;flex-direction:column;justify-content:center;gap:{18*scale:.0f}px;position:relative;overflow:hidden}}
    .fake-line{{height:{22*scale:.0f}px;border-radius:8px;background:{colors['border']}}}
    .hl-line{{align-self:flex-start;background:{_rgba(colors['accent'], 0.4)};color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{32*scale:.0f}px;padding:0.2em 0.45em;border-radius:10px;border:2px solid {colors['accent_strong']}}}
    .circle-wrap{{position:relative;height:100%;display:flex;align-items:center;justify-content:center}}
    .circle-card{{font-family:'{display}',cursive;font-size:{72*scale:.0f}px;color:{colors['text']}}}
    .circle-svg{{position:absolute;inset:8% 10%;width:80%;height:84%}}
    .fan{{position:relative;height:100%}}
    .page-rot{{position:absolute;left:18%;top:6%;width:52%;height:78%;transform-origin:50% 90%}}
    .page{{height:100%;background:{colors['surface']};border:1px solid {colors['border']};border-radius:12px;box-shadow:{colors['card_shadow']};padding:8% 8%;color:{colors['text']}}}
    .page-rule{{height:6px;width:100%;background:{colors['accent_strong']};margin-bottom:12px}}
    .page .mono{{color:{colors['muted']};font-size:{mono_px*0.85:.1f}px}}
    .page-title{{font-family:'{display}',cursive;font-size:{36*scale:.0f}px;line-height:1.05;margin-top:10px}}
    .window{{height:86%;border-radius:{18*scale:.0f}px;overflow:hidden;border:1px solid {colors['border']};background:{colors['contrast']};box-shadow:{colors['card_shadow']}}}
    .chrome{{height:{54*scale:.0f}px;display:flex;align-items:center;gap:8px;padding:0 16px;background:{colors['surface']};color:{colors['muted']};font-size:{mono_px*0.8:.1f}px}}
    .chrome i{{width:{12*scale:.0f}px;height:{12*scale:.0f}px;border-radius:50%;background:{colors['border']}}}
    .chrome i:first-child{{background:{colors['accent']}}}
    .win-body{{padding:6% 6%;font-family:'{mono}',monospace;font-size:{28*scale:.0f}px;line-height:1.35;color:{colors['text']};letter-spacing:0;text-transform:none}}
    .caret{{color:{colors['accent']}}}
    .mind{{position:absolute;inset:0;width:100%;height:100%}}
    .node{{position:absolute;border:1px solid {colors['border']};background:{colors['surface']};color:{colors['text']};border-radius:14px;padding:10px 16px;font-family:'{caption}',sans-serif;font-weight:800;font-size:{26*scale:.0f}px}}
    .center-node{{left:40%;top:40%;border-color:{colors['accent_strong']}}}
    .leaf-a{{left:4%;top:8%}} .leaf-b{{right:4%;top:8%}} .leaf-c{{left:40%;bottom:4%}}
    .logo-row{{position:absolute;left:0;right:0;top:34%;display:flex;justify-content:space-between;padding:0 8%;z-index:2}}
    .logo-chip{{background:{colors['surface']};border:1px solid {colors['border']};color:{colors['text']};border-radius:16px;padding:18px 22px;font-family:'{caption}',sans-serif;font-weight:800;font-size:{32*scale:.0f}px}}
    .logo-lines{{position:absolute;left:0;right:0;top:28%;width:100%;height:40%}}
    .phone.fill{{width:100%;height:100%;margin:0;padding:{8*scale:.0f}px;border-radius:{28*scale:.0f}px}}
    .callout-ring{{position:absolute;border:{4*scale:.0f}px solid {colors['accent_strong']};border-radius:50%;box-sizing:border-box;pointer-events:none;z-index:3}}
    .phone-hl{{position:absolute;left:6%;right:6%;z-index:3}}
    .stage-chip{{position:absolute;top:{10*scale:.0f}px;right:{10*scale:.0f}px;z-index:4;padding:{6*scale:.0f}px {10*scale:.0f}px;border-radius:8px;font-family:'{mono}',monospace;font-size:{mono_px:.1f}px;letter-spacing:0.06em}}
    .stage-chip.green{{background:{colors['accent']};color:{colors['on_accent']}}}
    .stage-chip.amber{{background:{colors['warning']};color:{colors['contrast']}}}
    .quote-card{{height:100%;display:flex;align-items:center;justify-content:center;padding:6%}}
    .quote-text{{position:relative;font-family:'{display}',cursive;font-size:{64*scale:.0f}px;line-height:1.05;color:{colors['text']};text-align:center}}
    .quote-strike{{position:absolute;left:-4%;right:-4%;top:54%;height:{6*scale:.0f}px;background:{colors['warning']};transform:scaleX(0);transform-origin:0 50%}}
    .offer-col{{height:100%;display:flex;flex-direction:column;gap:{12*scale:.0f}px}}
    .offer-kicker{{color:{colors['muted']};font-size:{mono_px:.1f}px}}
    .offer-row{{flex:1;display:flex;gap:{12*scale:.0f}px}}
    .offer-card{{flex:1;display:flex;align-items:center;justify-content:center;text-align:center;padding:6%;background:{colors['surface']};border:1px solid {colors['border']};border-radius:16px;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{32*scale:.0f}px;line-height:1.05}}
    .offer-note{{text-align:center;color:{colors['muted']};font-family:'{mono}',monospace;font-size:{mono_px:.1f}px;letter-spacing:0.02em}}
    .flow{{height:100%;display:flex;align-items:center;justify-content:space-between;gap:{10*scale:.0f}px;padding:0 2%}}
    .flow-label{{flex:1;text-align:center;background:{colors['surface']};border:1px solid {colors['border']};border-radius:16px;padding:{16*scale:.0f}px;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{28*scale:.0f}px;line-height:1.05}}
    .flow-dash{{flex:0.55;height:0;border-top:{4*scale:.0f}px dashed {colors['accent']}}}
    .pill-wrap{{height:100%;display:flex;align-items:center;justify-content:center}}
    .pill{{background:{colors['accent']};color:{colors['on_accent']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{40*scale:.0f}px;line-height:1;padding:0.35em 0.7em;border-radius:999px}}
    .notice{{position:absolute;left:6%;top:11%;z-index:7;max-width:70%;font-size:{mono_px:.1f}px;letter-spacing:0.02em;padding:{6*scale:.0f}px {10*scale:.0f}px;border-radius:8px}}
    .chip-corner{{position:absolute;top:7.2%;right:4.5%;z-index:7;font-size:{mono_px:.1f}px;letter-spacing:0.04em;padding:{8*scale:.0f}px {12*scale:.0f}px;border-radius:10px}}
    .bar-col .mono{{max-width:100%;text-align:center;white-space:normal;line-height:1.1}}
    '''
    # _rgba is used above; import locally to keep the css f-string valid.
    speaker = f'<div id="speaker-card"><div id="presenter-camera" data-layout-allow-overflow>{"".join(part for part in parts if part.startswith("<video"))}</div></div>'
    rest = [part for part in parts if not part.startswith("<video")]
    slide = (
        "function kallawaySlide(t){var x1=0.25,y1=1,x2=0.5,y2=1,cx=3*x1,bx=3*(x2-x1)-cx,ax=1-cx-bx,cy=3*y1,by=3*(y2-y1)-cy,ay=1-cy-by;"
        "function sx(u){return ((ax*u+bx)*u+cx)*u;} function sy(u){return ((ay*u+by)*u+cy)*u;} var u=t;"
        "for(var i=0;i<5;i++){var dx=sx(u)-t,den=(3*ax*u+2*bx)*u+cx; if(Math.abs(den)<1e-5) break; u-=dx/den;}"
        "return sy(Math.max(0,Math.min(1,u)));}"
    )
    markup = (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(spec.get("title", "Talking head reel"))}</title>'
        f'<script src="assets/gsap.min.js"></script><style>{css}</style></head><body>'
        f'<div id="root" data-composition-id="main" data-width="{width}" data-height="{height}" data-duration="{duration}" data-fps="{fps}">'
        f'{speaker}{"".join(rest)}{"".join(audio)}</div><script>{slide}const tl=gsap.timeline({{paused:true}});'
        f'{"".join(animations)}window.__timelines=window.__timelines||{{}};window.__timelines.main=tl;</script></body></html>'
    )
    (project / "index.html").write_text(markup)
    (project / "timeline.json").write_text(json.dumps(spec, indent=2) + "\n")
    (project / "mapped-words.json").write_text(json.dumps(words, indent=2) + "\n")
    receipt = {
        "project": str(project), "style": "kallaway", "theme": theme["id"], "theme_mode": mode,
        "theme_path": str(theme_path), "duration": duration, "width": width, "height": height, "fps": fps,
        "words": len(words), "caption_groups": len(groups), "shots": len(shots),
        "original_audio_preserved": has_audio, "music_count": len(spec.get("music", [])),
        "sfx_count": len(spec.get("sfx", [])), "media_transfer": "local hardlink or copy; no upload", "rendered": False,
    }
    (project / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def _rgba(hex_color, alpha):
    raw = hex_color.lstrip("#")
    return f"rgba({int(raw[0:2], 16)},{int(raw[2:4], 16)},{int(raw[4:6], 16)},{alpha})"
