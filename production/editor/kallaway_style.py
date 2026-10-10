"""Build a HyperFrames composition in the Kallaway split / full / punch-in grammar.

Colors and fonts come from the theme preset. Existing presenter timelines never enter this module.
"""
import json
import os
from pathlib import Path
import shutil

from edit import boundary_hard_kills, escape, map_words, probe, read_words, resolve, validate_music
from kallaway_matte import caption_band_px, placed_pop_geometry, pop_geometry
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


def radius_css(value):
    """CSS border-radius. A number is one radius; a string is used as written."""
    if isinstance(value, str):
        return value
    number = float(value)
    if number == int(number):
        return f"{int(number)}px"
    return f"{number}px"


def full_caption_top(beard_bottom, pin_top, font_px, below_beard=25.0, above_pin=30.0, line=1.02):
    """Canvas y of a full-face caption between the beard and the lapel pin.

    Letter tops stay `below_beard` px under the beard. Descenders stay
    `above_pin` px above the pin. The line moves up when the gap is tight.
    """
    box = float(font_px) * line
    top = float(beard_bottom) + float(below_beard)
    if float(pin_top) - (top + box) < float(above_pin):
        top = float(pin_top) - float(above_pin) - box
    return top


def assign_full_captions(shots, chins, layout, height=1920):
    """Place each full-face caption from that shot's chin, between beard and pin."""
    font = float(layout.get("caption_full_px", 67))
    beard_pad = float(layout.get("full_beard_below_chin_px", 48))
    pin_pad = float(layout.get("full_pin_below_chin_px", 200))
    below = float(layout.get("caption_beard_gap_px", 25))
    above = float(layout.get("caption_pin_gap_px", 30))
    for shot in shots or []:
        if shot.get("layout") not in {"full", "punch_in"}:
            continue
        chin = chins.get(shot.get("id"))
        if chin is None:
            continue
        top = full_caption_top(float(chin) + beard_pad, float(chin) + pin_pad, font, below, above)
        shot["caption_y"] = round(top / float(height) * 100, 3)
    return shots


def graphic_stage_bottom(layout_spec, height, popout=None):
    """Canvas y where panel graphics stop, above the caption and the popped hair.

    The theme bottom already clears a normal head. A taller measured crown,
    or a hand above that crown, pulls the bottom up so the caption band
    between the panels and the hair stays empty.
    """
    stage_top = float(layout_spec["stage_top"]) * height
    theme_bottom = stage_top + float(layout_spec["stage_height"]) * height
    rise = 0.0
    for key in ("high_above_px", "hand_above_px", "median_above_px"):
        if popout and popout.get(key):
            rise = max(rise, float(popout[key]))
    if rise <= 0:
        return theme_bottom
    card_top = float(layout_spec["card_top"]) * height
    cleared = card_top - rise - caption_band_px(layout_spec, height)
    floor = stage_top + 160
    return max(floor, min(theme_bottom, cleared))


def card_state(layout, crop, width, height, layout_spec, colors):
    """Scale 1 fills the card or the frame. A scale under 1 letterboxes the face."""
    del crop
    scale = 1.0
    if layout == "split":
        margin = layout_spec["card_margin_x"] * width
        top = layout_spec["card_top"] * height
        bottom = layout_spec["card_bottom"] * height
        radius = round(layout_spec["card_radius"] * width / 1080)
        # Flush bottom. Only the top corners are rounded. Full and punch stay square.
        return {
            "left": round(margin), "top": round(top),
            "width": round(width - 2 * margin), "height": round(bottom - top),
            "borderRadius": f"{radius}px {radius}px 0 0",
            "boxShadow": colors["card_shadow"], "scale": scale,
        }
    return {"left": 0, "top": 0, "width": width, "height": height,
            "borderRadius": 0, "boxShadow": "none", "scale": scale}


def _caption_text(word, omit_punct=True, keep_case=()):
    """On-screen caption. Prices keep their spelling. Everything else is lowercase."""
    text = str(word.get("display") or word.get("word") or word.get("text") or "").strip()
    bare = text.strip(".,!?:;\"'")
    kept = {item.lower(): item for item in keep_case}
    if bare.lower() in kept:
        return kept[bare.lower()]
    if bare.lower() == "i":
        return "I"
    if any(ch.isdigit() for ch in bare) or bare.startswith("$"):
        shown = bare if omit_punct else text
        return shown
    if omit_punct:
        text = bare
    return text.lower()


def _word_style(word, styles):
    """The planned map wins. A color baked onto the word is only the fallback.

    Source transcripts often arrive with an old green on a price. The beat cap
    and the stage plan have already decided, and that decision is ``styles``.
    """
    token = "".join(ch for ch in str(word.get("word", word.get("text", ""))).lower() if ch.isalnum() or ch == "'")
    if token in styles:
        return styles[token]
    if word.get("style") in {"normal", "marker", "green", "amber"}:
        return word["style"]
    return "normal"


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
    position = layout_spec.get("full_object_position") or spec["source"].get(
        "object_position", layout_spec["object_position"])
    popout = spec.get("source", {}).get("popout") or {}
    placed = bool(popout.get("face_px") and popout.get("plate"))
    plate_src = media(popout["plate"]) if placed else None
    gsap = HERE / "node_modules/gsap/dist/gsap.min.js"
    if not gsap.is_file():
        raise ValueError("run npm ci in production/editor before building")
    shutil.copy2(gsap, assets / "gsap.min.js")

    parts, animations, audio, pop_parts = [], [], [], []
    source = media(str(source_path))
    video_stream = next(item for item in source_info["streams"] if item.get("codec_type") == "video")
    video_w, video_h = int(video_stream["width"]), int(video_stream["height"])
    matte_src = media(spec["source"]["matte"]) if spec["source"].get("matte") else None
    has_audio = any(stream.get("codec_type") == "audio" for stream in source_info["streams"])
    cursor = 0.0
    for index, segment in enumerate(segments):
        length = float(segment["end"]) - float(segment["start"])
        timing = f'data-start="{cursor:.6f}" data-duration="{length:.6f}" data-media-start="{segment["start"]}"'
        parts.append(f'<video id="aroll-{index}" class="aroll clip" src="{source}" {timing} data-track-index="0" muted playsinline></video>')
        if matte_src:
            pop_parts.append(
                f'<video id="pop-{index}" class="pop-aroll clip" src="{matte_src}" {timing} '
                f'data-track-index="1" muted playsinline></video>')
        if has_audio:
            audio.append(f'<audio id="voice-{index}" src="{source}" {timing} data-track-index="10" data-volume="1"></audio>')
        cursor += length

    shots = spec.get("shots") or []
    if not shots:
        raise ValueError("kallaway timeline needs shots")
    first = card_state(shots[0].get("layout", "split"), shots[0].get("crop", "wide"),
                       width, height, layout_spec, colors)
    stage_top_px = round(layout_spec["stage_top"] * height)
    stage_bottom_px = graphic_stage_bottom(layout_spec, height, spec.get("source", {}).get("popout"))
    stage_box = {
        "left": round(layout_spec["stage_left"] * width),
        "top": stage_top_px,
        "width": round(layout_spec["stage_width"] * width),
        "height": max(160, round(stage_bottom_px - stage_top_px)),
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
        # A punch may crop tighter. Split scale is the placed face size, not a
        # CSS shrink of the cover crop, so the camera transform stays at 1.
        camera_scale = 1.0
        if layout != "split" and shot.get("scale") and float(shot["scale"]) > 1.0:
            camera_scale = float(shot["scale"])
            state["scale"] = camera_scale
        payload = {key: state[key] for key in ("left", "top", "width", "height", "borderRadius", "boxShadow")}
        animations.append(f'tl.set("#speaker-card",{json.dumps(payload)},{start});')
        animations.append(
            f'tl.set("#presenter-camera",{{scale:{camera_scale},transformOrigin:"50% 30%"}},{start});')
        if layout == "split" and placed:
            animations.append(f'tl.set(".aroll",{{autoAlpha:0}},{start});')
            animations.append(f'tl.set("#speaker-plate",{{autoAlpha:1}},{start});')
        else:
            animations.append(f'tl.set(".aroll",{{autoAlpha:1}},{start});')
            if plate_src:
                animations.append(f'tl.set("#speaker-plate",{{autoAlpha:0}},{start});')
            if shot.get("object_position"):
                animations.append(
                    f'tl.set(".aroll",{{objectPosition:{json.dumps(shot["object_position"])}}},{start});')
        if matte_src:
            # Same timestamp as #speaker-card. HyperFrames sets each [data-start] video
            # to visibility:visible, and a visible child paints through a hidden parent,
            # so visibility alone leaves the popped crown on full and punch frames.
            # autoAlpha 0 flattens the subtree (opacity) and the closed clip is the
            # second lock. Full and punch stay off; split matches the card on this frame.
            if layout == "split":
                if placed:
                    geo = placed_pop_geometry(
                        state, video_w, video_h,
                        popout["head_top"], popout["pop_px"], popout["scale"])
                else:
                    geo = pop_geometry(
                        state, video_w, video_h,
                        shot.get("object_position") or position, height)
                animations.append(
                    f'tl.set("#pop-camera",{json.dumps({key: geo[key] for key in ("left", "top", "width", "height")})},{start});')
                animations.append(
                    f'tl.set("#speaker-pop",{json.dumps({"autoAlpha": 1, "clipPath": geo["clipPath"]})},{start});')
            else:
                animations.append(
                    f'tl.set("#speaker-pop",{json.dumps({"autoAlpha": 0, "clipPath": "inset(100% 0px 0px 0px)"})},{start});')
        caption_y = layout_spec["caption_split_y"] if layout == "split" else layout_spec["caption_full_y"]
        split_px = float(layout_spec.get("caption_split_px", layout_spec["caption_font_px"]))
        full_px = float(layout_spec.get("caption_full_px", split_px))
        caption_px_shot = (split_px if layout == "split" else full_px) * scale
        animations.append(
            f'tl.set("#caption-anchor",{{top:"{shot.get("caption_y", caption_y * 100):.2f}%",'
            f'fontSize:"{caption_px_shot:.1f}px"}},{start});')
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

    reveal = spec.get("speaker_reveal")
    if reveal:
        # Opening words play under a full-frame graphic until his hand is off
        # his face. The picture keeps rolling; the card and the pop-out cut in live.
        reveal = float(reveal)
        animations.append('tl.set("#speaker-card",{autoAlpha:0},0);')
        animations.append(
            'tl.set("#speaker-pop",{autoAlpha:0,clipPath:"inset(100% 0px 0px 0px)"},0);')
        animations.append(
            f'tl.set("#stage-0",{{left:0,top:0,width:{width},height:{height}}},0);')
        shown = card_state("split", shots[0].get("crop", "wide"), width, height, layout_spec, colors)
        animations.append(
            'tl.set("#speaker-card",{autoAlpha:1,'
            f'left:{shown["left"]},top:{shown["top"]},width:{shown["width"]},height:{shown["height"]},'
            f'borderRadius:{json.dumps(shown["borderRadius"])},boxShadow:{json.dumps(shown["boxShadow"])}}},'
            f'{reveal:.3f});')
        if matte_src and shots[0].get("layout", "split") == "split":
            if placed:
                geo = placed_pop_geometry(
                    shown, video_w, video_h,
                    popout["head_top"], popout["pop_px"], popout["scale"])
            else:
                geo = pop_geometry(
                    shown, video_w, video_h,
                    shots[0].get("object_position") or position, height)
            animations.append(
                f'tl.set("#pop-camera",{json.dumps({key: geo[key] for key in ("left", "top", "width", "height")})},{reveal:.3f});')
            animations.append(
                f'tl.set("#speaker-pop",{json.dumps({"autoAlpha": 1, "clipPath": geo["clipPath"]})},{reveal:.3f});')
        animations.append(
            f'tl.set("#stage-0",{{left:{stage_box["left"]},top:{stage_box["top"]},'
            f'width:{stage_box["width"]},height:{stage_box["height"]}}},{reveal:.3f});')

    words = map_words(read_words(resolve(spec["words_path"], spec_path.parent)), segments) if spec.get("words_path") else []
    captions = spec.get("captions", {})
    styles = {str(key).lower(): value for key, value in captions.get("word_styles", {}).items()}
    style_at = list(captions.get("style_at") or [])
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
    word_index = 0
    for index, group in enumerate(groups):
        start = float(group[0]["start"])
        end = float(group[-1]["end"]) if index + 1 == len(groups) else float(groups[index + 1][0]["start"])
        end = min(duration, max(end, start + 0.08))
        spans = []
        for word in group:
            if word_index < len(style_at):
                style = style_at[word_index]
            else:
                style = _word_style(word, styles)
            word_index += 1
            spans.append(
                f'<span class="cap {style}">{escape(_caption_text(word, captions.get("omit_terminal_punctuation", True), keep_case))}</span>')
        parts.append(
            f'<div id="cap-{index}" class="caption clip" data-start="{start:.4f}" data-duration="{max(0.04, end-start):.4f}" '
            f'data-track-index="5"><div id="capbox-{index}" class="caption-text">{" ".join(spans)}</div></div>')
        animations.append(
            f'tl.fromTo("#capbox-{index}",{{scale:0.9}},{{scale:1,duration:{3.0 / float(fps):.3f},ease:"power2.out"}},{start:.4f});')
    parts.append("</div>")

    for index, header in enumerate(spec.get("headers") or []):
        start, end = float(header["start"]), float(header["end"])
        if end <= start:
            continue
        kind = header.get("variant", "headline")
        payoff = str(header.get("payoff") or "").strip(".,!?:;\"'")
        if not payoff and header.get("emphasis"):
            payoff = str(header["emphasis"][-1]).strip(".,!?:;\"'")
        payoff_style = header.get("payoff_style") or "marker"
        size_style = f' style="font-size:{float(header["size"]) * scale:.1f}px"' if header.get("size") else ""
        lines = header.get("lines") or []

        def _payoff_html(token):
            bare = token.strip(".,!?:;\"'")
            if payoff and bare.lower() == payoff.lower():
                if payoff_style == "amber":
                    css = "payoff box amber"
                elif payoff_style == "box":
                    css = "payoff box"
                else:
                    css = "payoff"
                return f'<span class="{css}">{escape(token)}</span>'
            return escape(token)

        if lines:
            blocks = []
            for line in lines:
                words_html = " ".join(_payoff_html(token) for token in str(line).split(" "))
                blocks.append(f'<div class="header-line">{words_html}</div>')
            inner = f'<div class="header-text"{size_style}>{"".join(blocks)}</div>'
        elif kind == "label":
            inner = f'<div class="header-label"{size_style}>{escape(header.get("text", ""))}</div>'
        else:
            pieces = [_payoff_html(token) for token in str(header.get("text", "")).split(" ") if token]
            sub = f'<div class="header-sub">{escape(header["sub"])}</div>' if header.get("sub") else ""
            inner = f'<div class="header-text"{size_style}>{" ".join(pieces)}</div>{sub}'
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

    from kallaway_audio import SFX_KINDS, sfx_variants, write_sfx_library
    library = spec_path.parent / "sfx"
    # Cues baked into the voice file must not be mixed a second time here.
    if spec.get("sfx") and not spec.get("sfx_baked"):
        if any(sound.get("kind") for sound in spec.get("sfx", [])) and not sfx_variants("pop", library):
            write_sfx_library(library)
        variant_use = {}
        for index, sound in enumerate(spec.get("sfx", [])):
            if sound.get("mute"):
                continue
            if sound.get("kind"):
                if sound["kind"] not in SFX_KINDS:
                    raise ValueError(f"unknown sfx kind: {sound['kind']}")
            if sound.get("file"):
                from kallaway_audio import write_wav
                from kallaway_pack import render
                samples, cue_at, _info = render(sound)
                if cue_at < 0:
                    drop = int(round(-cue_at * 48000))
                    samples = samples[drop:]
                    cue_at = 0.0
                dest = library / f"cue-{index}.wav"
                write_wav(dest, samples)
                path = media(str(dest))
                length = max(0.04, len(samples) / 48000.0)
                start_at = cue_at
            elif sound.get("kind"):
                variants = sfx_variants(sound["kind"], library)
                if not variants:
                    raise ValueError(f"sfx library has no files for {sound['kind']}")
                slot = variant_use.get(sound["kind"], 0)
                variant_use[sound["kind"]] = slot + 1
                chosen = variants[slot % len(variants)]
                path = media(str(chosen))
                length = float(probe(project / path)["format"]["duration"])
                start_at = float(sound.get("sound_at", sound["at"]))
            else:
                path = media(sound["path"])
                length = float(sound.get("duration", probe(project / path)["format"]["duration"]))
                start_at = float(sound.get("sound_at", sound["at"]))
            if sound.get("under_db") is not None:
                gain = 10 ** (-float(sound["under_db"]) / 20.0)
            else:
                gain = sound.get("gain", theme.get("sfx_gain", {}).get(sound.get("kind"), 0.35))
            audio.append(
                f'<audio id="sfx-{index}" src="{path}" data-start="{float(start_at):.4f}" data-duration="{length:.4f}" '
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
    card_radius_css = radius_css(first["borderRadius"])
    split_open = placed and shots and shots[0].get("layout") == "split"
    aroll_open = "opacity:0;visibility:hidden;" if split_open else ""
    plate_open = "" if split_open else "opacity:0;visibility:hidden;"
    css = f'''{font_faces(theme, media)}
    *{{box-sizing:border-box}} body{{margin:0;background:{colors['background']}}}
    #root{{position:relative;width:{width}px;height:{height}px;overflow:hidden;{background}}}
    #speaker-card{{position:absolute;left:{first['left']}px;top:{first['top']}px;width:{first['width']}px;height:{first['height']}px;overflow:hidden;z-index:4;border-radius:{card_radius_css};box-shadow:{first['boxShadow']};background:{colors['contrast']}}}
    #speaker-plate{{position:absolute;inset:0;width:100%;height:100%;object-fit:fill;z-index:0;{plate_open}}}
    #presenter-camera{{position:absolute;inset:0;transform-origin:50% 30%;width:100%;height:100%;z-index:1}}
    .aroll{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{position};{aroll_open}}}
    #speaker-pop{{position:absolute;left:0;top:0;width:{width}px;height:{height}px;z-index:6;overflow:hidden;pointer-events:none;visibility:hidden;opacity:0}}
    #pop-camera{{position:absolute}}
    #pop-camera.placed-edge{{mask-image:linear-gradient(to right,transparent 0,#000 18px,#000 calc(100% - 18px),transparent 100%);-webkit-mask-image:linear-gradient(to right,transparent 0,#000 18px,#000 calc(100% - 18px),transparent 100%)}}
    .pop-aroll{{position:absolute;inset:0;width:100%;height:100%;object-fit:fill}}
    .stage{{position:absolute;z-index:2;overflow:hidden}}
    #caption-anchor{{position:absolute;top:{layout_spec['caption_split_y']*100:.2f}%;left:0;width:100%;z-index:8;pointer-events:none;font-size:{caption_px:.1f}px}}
    .caption{{position:absolute;left:6%;width:88%;text-align:center}}
    .caption-text{{display:inline-block;white-space:nowrap;font-family:'{caption}',sans-serif;font-weight:900;font-size:1em;line-height:1.02;letter-spacing:-0.04em;color:{colors['text']};text-shadow:{colors['caption_shadow']}}}
    .cap.marker{{font-family:'{display}',cursive;font-weight:400;font-size:1.12em;letter-spacing:0}}
    .cap.green{{color:{colors['accent']}}}
    .cap.amber{{color:{colors['warning_text']}}}
    .header{{position:absolute;top:{layout_spec['title_top']*100:.2f}%;left:7%;width:86%;z-index:8;text-align:center}}
    .header-text{{font-family:'{caption}',sans-serif;font-weight:800;font-size:{title_px:.1f}px;line-height:1.05;color:{colors['text']};text-shadow:{colors['caption_shadow']}}}
    .header-line{{display:block}}
    .header-text .payoff{{font-family:'{display}',cursive;font-weight:400;font-size:1.05em}}
    .header-text .payoff.box{{font-family:'{caption}',sans-serif;font-weight:800;background:{colors['accent']};color:{colors['on_accent']};padding:0.02em 0.16em;border-radius:8px}}
    .header-text .payoff.box.amber{{background:{colors['warning']};color:{colors['contrast']}}}
    .header-text .key,.header-line.key{{color:{colors['accent']}}}
    .header-sub{{margin-top:8px;font-family:'{mono}',monospace;font-size:{mono_px:.1f}px;letter-spacing:0.08em;text-transform:uppercase;color:{colors['muted']}}}
    .header-label{{display:inline-block;background:{colors['accent']};color:{colors['on_accent']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{title_px*0.62:.1f}px;line-height:1;padding:0.22em 0.45em;border-radius:8px}}
    .mono{{font-family:'{mono}',monospace;letter-spacing:0.08em;text-transform:uppercase}}
    .thumb-grid{{display:grid;grid-template-rows:1fr 1fr;gap:{14*scale:.0f}px;height:100%}}
    .thumb{{position:relative;border-radius:{16*scale:.0f}px;overflow:hidden;transform:scale(0.8);display:flex;flex-direction:column;justify-content:flex-end;padding:{12*scale:.0f}px;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{22*scale:.0f}px}}
    .thumb .mono{{position:absolute;top:{10*scale:.0f}px;left:{10*scale:.0f}px;color:{colors['muted']};font-size:{mono_px*0.8:.1f}px}}
    .thumb i{{position:absolute;right:{12*scale:.0f}px;bottom:{12*scale:.0f}px;color:{colors['muted']};font-style:normal;font-size:{16*scale:.0f}px}}
    .phone{{width:{430*scale:.0f}px;height:92%;margin:0 auto;background:{colors['contrast']};border-radius:{36*scale:.0f}px;padding:{12*scale:.0f}px;box-shadow:{colors['card_shadow']},0 0 48px {colors['accent']}55}}
    .phone-screen{{position:relative;height:100%;border-radius:{26*scale:.0f}px;overflow:hidden;background:{colors['surface']};border:1px solid {colors['border']}}}
    .phone-screen img,.broll-card img,.shotcard img,.phone-screen video,.broll-card video,.shotcard video{{width:100%;height:100%;object-fit:cover}}
    .ig-handle{{position:absolute;left:0;right:0;bottom:2.2%;z-index:9;text-align:center;font-family:'{mono}',monospace;font-size:{mono_px:.1f}px;letter-spacing:0.06em;color:{colors['text']};text-shadow:{colors['caption_shadow']};pointer-events:none}}
    .phone-fake,.broll-fake{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;background:linear-gradient(160deg,{colors['surface']},{colors['contrast']});color:{colors['text']};font-family:'{caption}',sans-serif}}
    .phone-bar{{position:absolute;left:8%;right:8%;bottom:8%;height:{8*scale:.0f}px;border-radius:99px;background:{colors['border']};overflow:hidden}}
    .phone-bar div,.broll-progress div{{height:100%;width:100%;background:{colors['accent']};transform:scaleX(0);transform-origin:0 50%}}
    .thumb-dot{{position:absolute;left:50%;bottom:18%;width:{54*scale:.0f}px;height:{54*scale:.0f}px;margin-left:{-27*scale:.0f}px;border-radius:50%;background:{colors['text']};opacity:0.9}}
    .broll-card,.quote-card,.offer-card,.shotcard,.cursor-ui,.swap-card,.vac-result{{box-shadow:{colors['card_shadow']}}}
    .broll-card{{width:100%;height:78%;border-radius:{22*scale:.0f}px;overflow:hidden;background:{colors['surface']};border:1px solid {colors['border']};position:relative}}
    .broll-progress{{position:absolute;left:0;right:0;bottom:0;height:{10*scale:.0f}px;background:{colors['border']}}}
    .nlist{{position:relative;height:100%}}
    .nrow{{display:flex;align-items:center;gap:{16*scale:.0f}px;padding:0 8%;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{40*scale:.0f}px}}
    .nrow .mono{{color:{colors['muted']};font-size:{mono_px:.1f}px;width:{64*scale:.0f}px}}
    .nbox{{position:absolute;left:4%;right:4%;top:0;border:3px solid {colors['accent_strong']};border-radius:{16*scale:.0f}px;pointer-events:none}}
    .chart{{width:100%;height:86%}}
    .chart-label{{text-align:right;color:{colors['muted']};font-size:{mono_px:.1f}px}}
    .chart-frame{{display:flex;height:100%;gap:{8*scale:.0f}px;padding:2% 2% 0}}
    .y-axis{{display:flex;flex-direction:column;justify-content:space-between;height:86%;color:{colors['muted']};font-family:'{mono}',monospace;font-size:{mono_px*0.7:.1f}px;letter-spacing:0}}
    .bars{{display:flex;align-items:flex-end;justify-content:space-between;height:100%;gap:{14*scale:.0f}px;padding:0 2% 4%;flex:1;border-left:2px solid {colors['border']};border-bottom:2px solid {colors['border']}}}
    .bar-col{{position:relative;flex:1;height:86%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px}}
    .bar{{width:78%;border-radius:{10*scale:.0f}px {10*scale:.0f}px 0 0;transform:scaleY(0);transform-origin:50% 100%;box-shadow:0 12px 24px rgba(0,0,0,0.35)}}
    .bar-x{{position:absolute;top:8%;left:0;right:0;text-align:center;font-family:'{display}',cursive;font-size:{42*scale:.0f}px;color:{colors['warning']};opacity:0;text-shadow:0 8px 18px rgba(0,0,0,0.45)}}
    .bar-col .mono{{color:{colors['muted']};font-size:{mono_px*0.85:.1f}px}}
    .counter{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center}}
    .counter.dense{{justify-content:space-between;padding:1% 0 0}}
    .count-num{{font-family:'{caption}',sans-serif;font-weight:900;font-size:{210*scale:.0f}px;line-height:0.9;color:{colors['accent']};letter-spacing:-0.04em;text-shadow:0 0 36px {colors['accent']}88}}
    .counter.dense .count-num{{font-size:{148*scale:.0f}px}}
    .count-label{{color:{colors['muted']};font-size:{mono_px:.1f}px;margin-top:8px}}
    .counter.range{{position:relative;justify-content:flex-start;gap:{10*scale:.0f}px;padding-top:1%}}
    .counter.range .count-num{{font-size:{168*scale:.0f}px;margin-top:2%}}
    .range-old{{position:relative;z-index:5;text-align:center;font-family:'{display}',cursive;font-size:{72*scale:.0f}px;line-height:0.9;color:{colors['warning_text']};margin-bottom:4%}}
    .range-old .quote-strike{{top:54%}}
    .range-row{{display:flex;gap:{12*scale:.0f}px;width:100%;flex:1;min-height:0}}
    .range-card{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:{8*scale:.0f}px;padding:4% 3%;border-radius:18px;background:linear-gradient(180deg,{colors['surface']},{colors['contrast']});border:1px solid rgba(255,255,255,0.14);box-shadow:0 24px 48px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.12);color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{32*scale:.0f}px;line-height:1.05;text-align:center}}
    .range-ico{{width:{64*scale:.0f}px;height:{64*scale:.0f}px;color:{colors['accent']}}}
    .range-ico svg{{width:100%;height:100%}}
    .feat-col{{height:100%;display:flex;flex-direction:column;gap:{12*scale:.0f}px}}
    .feat-card{{flex:1;display:flex;align-items:center;gap:{18*scale:.0f}px;padding:0 6%;border-radius:18px;background:linear-gradient(180deg,{colors['surface']},{colors['contrast']});border:2px solid {colors['border']};box-shadow:0 18px 36px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.12);color:{colors['text']};font-family:'{display}',cursive;font-size:{52*scale:.0f}px;line-height:0.95}}
    .feat-ico{{width:{72*scale:.0f}px;height:{72*scale:.0f}px;flex:0 0 {72*scale:.0f}px;color:{colors['accent']}}}
    .feat-ico svg{{width:100%;height:100%}}
    .site-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:{8*scale:.0f}px;width:100%;flex:1}}
    .site-thumb{{position:relative;border-radius:{12*scale:.0f}px;background:linear-gradient(160deg,{colors['surface']},{colors['contrast']});border:1px solid {colors['border']};box-shadow:0 16px 32px rgba(0,0,0,0.4);min-height:{72*scale:.0f}px;padding:{8*scale:.0f}px;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{16*scale:.0f}px}}
    .site-thumb .mono{{display:block;color:{colors['muted']};font-size:{mono_px*0.65:.1f}px;margin-bottom:4px}}
    .site-thumb i{{position:absolute;left:8%;right:8%;bottom:18%;height:8px;border-radius:4px;background:{colors['accent']};opacity:0.85}}
    .shotcard{{height:100%;border-radius:{20*scale:.0f}px;background:{colors['surface']};border:1px solid {colors['border']};padding:8% 8%;display:flex;flex-direction:column;justify-content:center;gap:{18*scale:.0f}px;position:relative;overflow:hidden}}
    .fake-line{{height:{22*scale:.0f}px;border-radius:8px;background:{colors['border']}}}
    .hl-line{{align-self:flex-start;background:{_rgba(colors['accent'], 0.4)};color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{32*scale:.0f}px;padding:0.2em 0.45em;border-radius:10px;border:2px solid {colors['accent_strong']};opacity:0}}
    .circle-wrap{{position:relative;height:100%;display:flex;align-items:center;justify-content:center}}
    .circle-card{{font-family:'{display}',cursive;font-size:{72*scale:.0f}px;color:{colors['text']}}}
    .circle-svg{{position:absolute;inset:8% 10%;width:80%;height:84%}}
    .fan{{position:relative;height:100%}}
    .page-rot{{position:absolute;left:18%;top:6%;width:52%;height:78%;transform-origin:50% 90%}}
    .page{{height:100%;background:{colors['surface']};border:1px solid {colors['border']};border-radius:12px;box-shadow:{colors['card_shadow']};padding:8% 8%;color:{colors['text']}}}
    .page-rule{{height:6px;width:100%;background:{colors['accent_strong']};margin-bottom:12px}}
    .page .mono{{color:{colors['muted']};font-size:{mono_px*0.85:.1f}px}}
    .page-title{{font-family:'{display}',cursive;font-size:{36*scale:.0f}px;line-height:1.05;margin-top:10px}}
    .fan.stack .page-rot{{width:74%;height:90%;top:4%}}
    .fan.stack .page-title{{font-size:{56*scale:.0f}px}}
    .fan-tint{{position:absolute;inset:0;background:{colors['warning']};opacity:0;pointer-events:none;border-radius:12px}}
    .window{{height:86%;border-radius:{18*scale:.0f}px;overflow:hidden;border:1px solid {colors['border']};background:{colors['contrast']};box-shadow:{colors['card_shadow']}}}
    .window.terminal{{height:100%;box-shadow:0 28px 64px rgba(0,0,0,0.5), 0 0 42px {colors['accent']}55, inset 0 1px 0 rgba(255,255,255,0.12)}}
    .window.terminal .win-body{{font-size:{36*scale:.0f}px;line-height:1.28}}
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
    .phone.hero{{position:absolute;margin:0;box-shadow:0 28px 64px rgba(0,0,0,0.55),0 0 48px {colors['accent']}44}}
    .phone.hero .phone-screen img,.phone.hero .phone-screen video{{object-fit:cover;background:{colors['contrast']}}}
    .phone-pan{{position:absolute;left:0;top:0;width:100%}}
    .callout-draw{{position:absolute;overflow:visible;pointer-events:none;z-index:4;opacity:0}}
    .callout-draw path{{fill:none;stroke:{colors['accent_strong']};stroke-width:7;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}}
    .phone-hl{{position:absolute;left:8%;right:8%;z-index:3;height:0;padding:0;background:transparent;border:none;border-bottom:4px solid {colors['accent']};overflow:visible}}
    .quote-card.balance{{flex-direction:column;align-items:stretch;justify-content:flex-end;height:100%;padding:4% 6% 8%}}
    .bal-row{{display:flex;align-items:flex-end;justify-content:center;gap:6%;height:78%;width:100%}}
    .bal-col{{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:12px;width:34%;font-family:'{caption}',sans-serif;font-size:{36*scale:.0f}px;color:{colors['text']}}}
    .bal-bar{{width:100%;height:88%;background:{colors['accent']};border-radius:16px 16px 6px 6px;transform:scaleY(0);transform-origin:50% 100%}}
    .bal-bar.short{{height:32%;background:{colors['warning']}}}
    .bal-ne{{font-family:'{display}',cursive;font-size:{72*scale:.0f}px;color:{colors['text']};align-self:center}}
    .stage-chip{{position:absolute;top:{10*scale:.0f}px;right:{10*scale:.0f}px;z-index:4;padding:{6*scale:.0f}px {10*scale:.0f}px;border-radius:8px;font-family:'{mono}',monospace;font-size:{mono_px:.1f}px;letter-spacing:0.06em}}
    .stage-chip.bottom{{top:auto;bottom:{10*scale:.0f}px;left:{10*scale:.0f}px;right:{10*scale:.0f}px;text-align:center;white-space:normal;line-height:1.2;font-size:{mono_px*0.72:.1f}px;letter-spacing:0.03em}}
    .cursor-ui{{position:relative;height:100%;display:flex;align-items:center;justify-content:center}}
    .cursor-btn{{padding:{18*scale:.0f}px {36*scale:.0f}px;border-radius:14px;background:{colors['accent']};color:{colors['on_accent']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{36*scale:.0f}px}}
    .cursor-ptr{{position:absolute;left:58%;top:58%;width:0;height:0;border-left:{18*scale:.0f}px solid {colors['text']};border-top:{8*scale:.0f}px solid transparent;border-bottom:{8*scale:.0f}px solid transparent;filter:drop-shadow(0 8px 12px rgba(0,0,0,0.35))}}
    .vac{{position:relative;height:100%;display:flex;align-items:center;justify-content:center}}
    .vac-chip{{position:absolute;padding:{10*scale:.0f}px {16*scale:.0f}px;border-radius:999px;background:{colors['surface']};color:{colors['text']};border:1px solid {colors['border']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{26*scale:.0f}px}}
    .vac-result{{position:relative;padding:{16*scale:.0f}px {22*scale:.0f}px;border-radius:16px;background:{colors['accent']};color:{colors['on_accent']};font-family:'{display}',cursive;font-size:{40*scale:.0f}px;box-shadow:{colors['card_shadow']},0 0 36px {colors['accent']}66}}
    .swap{{position:relative;height:100%;display:flex;align-items:center;justify-content:center}}
    .swap.side{{align-items:stretch;gap:{14*scale:.0f}px}}
    .swap-card{{position:absolute;width:78%;padding:8% 6%;border-radius:18px;text-align:center;font-family:'{display}',cursive;font-size:{42*scale:.0f}px;color:{colors['text']}}}
    .swap.side .swap-card{{position:relative;width:auto;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:8% 6%;font-size:{64*scale:.0f}px;line-height:0.95;overflow:hidden;min-height:88%}}
    .swap-card.bad{{background:{colors['surface']};border:2px solid {colors['warning']};box-shadow:{colors['card_shadow']},0 0 36px {colors['warning']}55}}
    .swap-card.good{{background:{colors['surface']};border:2px solid {colors['accent']};box-shadow:{colors['card_shadow']},0 0 36px {colors['accent']}66}}
    .bad-tint{{position:absolute;inset:0;background:{colors['warning']};opacity:0;pointer-events:none}}
    .rev{{width:100%;height:{220*scale:.0f}px;margin-top:{18*scale:.0f}px}}
    .rev-label{{margin-top:10px;color:{colors['accent']};font-size:{mono_px:.1f}px;letter-spacing:0.08em}}
    .stage-chip.green{{background:{colors['accent']};color:{colors['on_accent']}}}
    .stage-chip.amber{{background:{colors['warning']};color:{colors['contrast']}}}
    .quote-card{{height:100%;display:flex;align-items:center;justify-content:center;padding:6%}}
    .quote-text{{position:relative;font-family:'{display}',cursive;font-size:{96*scale:.0f}px;line-height:1.0;color:{colors['text']};text-align:center}}
    .receipt{{position:relative;height:100%;display:flex;flex-direction:column;justify-content:center;gap:{8*scale:.0f}px;padding:5% 6%;border-radius:{22*scale:.0f}px;background:linear-gradient(180deg,{colors['surface']},{colors['contrast']});border:1px solid rgba(255,255,255,0.14);box-shadow:0 28px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.16)}}
    .receipt-glow{{position:absolute;left:18%;right:18%;top:16%;height:42%;background:radial-gradient(circle,{colors['accent']}55,transparent 70%);filter:blur(8px);pointer-events:none}}
    .receipt-kicker{{position:relative;color:{colors['muted']};font-size:{mono_px*0.8:.1f}px}}
    .receipt-amt{{position:relative;font-family:'{display}',cursive;font-size:{112*scale:.0f}px;line-height:0.9;color:{colors['text']};text-shadow:0 0 28px {colors['accent']}77}}
    .receipt-line{{position:relative;display:flex;justify-content:space-between;color:{colors['muted']};font-family:'{mono}',monospace;font-size:{mono_px*0.75:.1f}px}}
    .cal{{position:relative;display:flex;gap:{6*scale:.0f}px}}
    .cal span{{flex:1;text-align:center;padding:{8*scale:.0f}px 0;border-radius:8px;font-family:'{mono}',monospace;font-size:{mono_px*0.7:.1f}px}}
    .cal-on{{background:{colors['accent']};color:{colors['on_accent']}}}
    .cal-off{{background:{colors['contrast']};color:{colors['muted']};border:1px solid {colors['border']}}}
    .paid-stamp{{position:absolute;right:8%;top:18%;padding:{6*scale:.0f}px {14*scale:.0f}px;border:4px solid {colors['accent']};color:{colors['accent']};font-family:'{display}',cursive;font-size:{54*scale:.0f}px;letter-spacing:0.04em;border-radius:8px;opacity:0;box-shadow:0 12px 28px rgba(0,0,0,0.35)}}
    .browser{{position:relative;height:100%;display:flex;flex-direction:column;border-radius:{20*scale:.0f}px;overflow:hidden;background:{colors['contrast']};border:1px solid rgba(255,255,255,0.14);box-shadow:0 28px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.12)}}
    .browser .chrome{{flex:0 0 auto}}
    .browser-live{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:{10*scale:.0f}px;padding:8%;color:{colors['text']};font-family:'{caption}',sans-serif;font-weight:800;font-size:{28*scale:.0f}px}}
    .browser-live b{{font-family:'{display}',cursive;font-weight:400;font-size:{64*scale:.0f}px}}
    .browser-live span{{display:inline-block;margin-right:{10*scale:.0f}px;padding:0.2em 0.5em;border-radius:999px;background:{colors['surface']};border:1px solid {colors['border']};font-size:{18*scale:.0f}px}}
    .browser-dead{{position:absolute;left:0;right:0;top:{54*scale:.0f}px;bottom:0;padding:8% 6%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:{12*scale:.0f}px;font-family:'{display}',cursive;font-size:{48*scale:.0f}px;line-height:0.95;color:{colors['text']};text-align:center;opacity:0}}
    .page-rows{{display:flex;flex-direction:column;gap:{8*scale:.0f}px;margin-top:{12*scale:.0f}px}}
    .page-rows i{{display:block;height:{14*scale:.0f}px;border-radius:7px;background:{colors['surface']};border:1px solid {colors['border']}}}
    .page-rows i:nth-child(2){{width:72%}} .page-rows i:nth-child(3){{width:48%}}
    .offline-mark{{width:{92*scale:.0f}px;height:{92*scale:.0f}px;border-radius:50%;border:{6*scale:.0f}px solid {colors['warning']};color:{colors['warning']};display:flex;align-items:center;justify-content:center;font-family:'{display}',cursive;font-size:{64*scale:.0f}px;line-height:1}}
    .offline-sub{{font-family:'{mono}',monospace;font-size:{mono_px:.1f}px;color:{colors['muted']}}}
    .term-result{{display:inline-block;margin-top:{18*scale:.0f}px;padding:{10*scale:.0f}px {16*scale:.0f}px;border-radius:12px;background:{colors['accent']};color:{colors['on_accent']};font-family:'{display}',cursive;font-size:{36*scale:.0f}px;transform:scale(0)}}
    .quote-strike{{position:absolute;left:-4%;right:-4%;top:46%;height:{14*scale:.0f}px;background:{colors['warning']};z-index:3;transform:scaleX(0);transform-origin:0 50%;box-shadow:0 0 0 1px {colors['warning']}}}
    .offer-col{{height:100%;display:flex;flex-direction:column;gap:{12*scale:.0f}px}}
    .offer-kicker{{color:{colors['muted']};font-size:{mono_px:.1f}px}}
    .offer-row{{flex:1;display:flex;gap:{12*scale:.0f}px}}
    .offer-card{{flex:1;display:flex;align-items:center;justify-content:center;text-align:center;padding:6% 4%;background:linear-gradient(180deg,{colors['surface']},{colors['contrast']});border:1px solid rgba(255,255,255,0.14);border-radius:18px;color:{colors['text']};font-family:'{display}',cursive;font-size:{52*scale:.0f}px;line-height:0.95;box-shadow:0 24px 48px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.12);transform:scale(0)}}
    .offer-card.good{{border-color:{colors['accent']};box-shadow:0 24px 48px rgba(0,0,0,0.45),0 0 36px {colors['accent']}66}}
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
    cover = "visibility:hidden;opacity:0;" if spec.get("speaker_reveal") else ""
    plate_html = f'<img id="speaker-plate" src="{plate_src}" alt="">' if plate_src else ""
    speaker = (
        f'<div id="speaker-card" style="{cover}">{plate_html}'
        f'<div id="presenter-camera" data-layout-allow-overflow>'
        f'{"".join(part for part in parts if part.startswith("<video"))}</div></div>')
    if pop_parts:
        opening = shots[0]
        if opening.get("layout") == "split" and not spec.get("speaker_reveal"):
            if placed:
                geo = placed_pop_geometry(
                    first, video_w, video_h,
                    popout["head_top"], popout["pop_px"], popout["scale"])
            else:
                geo = pop_geometry(
                    first, video_w, video_h, opening.get("object_position") or position, height)
            pop_style = f'style="opacity:1;visibility:visible;clip-path:{geo["clipPath"]}"'
            cam_style = (
                f'style="left:{geo["left"]}px;top:{geo["top"]}px;width:{geo["width"]}px;height:{geo["height"]}px"')
        else:
            pop_style = 'style="opacity:0;visibility:hidden;clip-path:inset(100% 0px 0px 0px)"'
            cam_style = ""
        edge = ' class="placed-edge"' if placed else ""
        speaker += (
            f'<div id="speaker-pop" data-layout-allow-overflow {pop_style}>'
            f'<div id="pop-camera"{edge} {cam_style}>{"".join(pop_parts)}</div></div>')
    rest = [part for part in parts if not part.startswith("<video")]
    slide = (
        "function kallawaySlide(t){var x1=0.25,y1=1,x2=0.5,y2=1,cx=3*x1,bx=3*(x2-x1)-cx,ax=1-cx-bx,cy=3*y1,by=3*(y2-y1)-cy,ay=1-cy-by;"
        "function sx(u){return ((ax*u+bx)*u+cx)*u;} function sy(u){return ((ay*u+by)*u+cy)*u;} var u=t;"
        "for(var i=0;i<5;i++){var dx=sx(u)-t,den=(3*ax*u+2*bx)*u+cx; if(Math.abs(den)<1e-5) break; u-=dx/den;}"
        "return sy(Math.max(0,Math.min(1,u)));}"
    )
    body = f'{speaker}{"".join(rest)}{"".join(audio)}<div class="ig-handle">@bjmeaux</div>'
    # Caption clips start on almost every word. An exit that lands on one needs a hard kill.
    animations.extend(boundary_hard_kills("".join(animations), body))
    markup = (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(spec.get("title", "Talking head reel"))}</title>'
        f'<script src="assets/gsap.min.js"></script><style>{css}</style></head><body>'
        f'<div id="root" data-composition-id="main" data-width="{width}" data-height="{height}" data-duration="{duration}" data-fps="{fps}">'
        f'{body}</div><script>{slide}const tl=gsap.timeline({{paused:true}});'
        f'{"".join(animations)}window.__timelines=window.__timelines||{{}};window.__timelines.main=tl;</script></body></html>'
    )
    (project / "index.html").write_text(markup)
    (project / "timeline.json").write_text(json.dumps(spec, indent=2) + "\n")
    (project / "mapped-words.json").write_text(json.dumps(words, indent=2) + "\n")
    receipt = {
        "project": str(project), "style": "kallaway", "theme": theme["id"], "theme_mode": mode,
        "theme_path": str(theme_path), "duration": duration, "width": width, "height": height, "fps": fps,
        "words": len(words), "caption_groups": len(groups), "shots": len(shots),
        "original_audio_preserved": has_audio, "popout": bool(pop_parts),
        "music_count": len(spec.get("music", [])),
        "sfx_count": len(spec.get("sfx", [])), "media_transfer": "local hardlink or copy; no upload", "rendered": False,
    }
    (project / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def _rgba(hex_color, alpha):
    raw = hex_color.lstrip("#")
    return f"rgba({int(raw[0:2], 16)},{int(raw[2:4], 16)},{int(raw[4:6], 16)},{alpha})"
