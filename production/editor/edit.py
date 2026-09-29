#!/usr/bin/env python3
"""Build and render local Brandon A-roll edits; no HeyGen cloud-render API jobs.

python3 edit.py build --spec timeline.json --project /path/to/composition
python3 edit.py render --project /path/to/composition --output /path/to/pilot.mp4

The builder writes one HyperFrames composition (HTML + GSAP timeline). Layers,
bottom to top: stage backdrop, presenter (with optional depth matte), shots,
stage band frame, spoken captions, motion graphics, transitions.
"""
import argparse
import copy
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from motion_scenes import scene_markup, CSS as MOTION_CSS
from editorial_scenes import artifact_markup, CSS as ARTIFACT_CSS
from kinetic_scenes import kinetic_markup, CSS as KINETIC_CSS
from hyperframes_cli import run as run_hyperframes
from cues import CueResolver, CueError, emphasis_key
from design import design_tokens, install_fonts, Scale, base_css, FEELS
from components import Ctx, render_graphics
from component_css import component_css
from motion_kit import motion_css, screen_css, screen_markup
import sfx_kit
import style

HERE = Path(__file__).resolve().parent
STYLE = style.load()
GSAP_PLUGINS = ("DrawSVGPlugin", "MotionPathPlugin", "CustomEase", "CustomWiggle")
TRANSITIONS = {"blur_flash", "light_leak", "flash", "whip", "zoom_blur", "push_in", "match_move", "shape_wipe", "punch"}
SHOT_MOTIONS = {"cut", "fade", "slide_up", "slide_down", "slide_left", "slide_right", "iris", "zoom", "expand", "morph"}
# Later fromTo tweens on an element+property must not pre-apply their start state at
# build time (that would override the earlier entrance while the playhead is before it).
FROMTO_GUARD = ('(function(){const seen=new WeakMap();const orig=tl.fromTo.bind(tl);'
                'tl.fromTo=function(t,f,v,p){const els=gsap.utils.toArray(t).filter(e=>e&&typeof e==="object");'
                'const props=Object.keys(f||{});let again=false;'
                'for(const el of els){const s=seen.get(el);if(s&&props.some(k=>s.has(k)))again=true;}'
                'for(const el of els){let s=seen.get(el);if(!s){s=new Set();seen.set(el,s);}props.forEach(k=>s.add(k));}'
                'if(again&&v&&v.immediateRender===undefined){v=Object.assign({},v,{immediateRender:false});}'
                'return orig(t,f,v,p);};})();')
# Presenter framings (scale, xPercent, yPercent) that keep Brandon full size. The camera
# pivots at 50% 38%, so each stays inside the source frame (no exposed edges).
PRESENTER_FRAMES = {"center": (1.0, 0, 0), "tight": (1.14, 0, 3), "close": (1.26, 0, 6),
                    "space_left": (1.14, 6.5, 1.5), "space_right": (1.14, -6.5, 1.5)}
STAGE_DEFAULTS = {"band_top": 63.5, "inset": 2.2, "bottom": 2.0, "radius": 36, "edge": "card",
                  "presenter_scale": .9, "presenter_x": 0, "presenter_y": 42, "caption_y": None}
COMPLEX_GRAPHICS = {"flow", "orbit", "device", "chart", "checklist", "compare", "prompt", "stat", "card"}


def probe(path):
    command = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    return json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)


def escape(value):
    return html.escape(str(value), quote=True)


def resolve(value, base):
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def finite_number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be finite")
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def validate_music(sound, spec_path, project, duration, index):
    path = resolve(sound.get("path"), spec_path.parent)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"music {index} missing or empty: {path}")
    start = finite_number(sound.get("start", 0), f"music {index} start")
    end = finite_number(sound.get("end", duration), f"music {index} end")
    source_start = finite_number(sound.get("source_start", 0), f"music {index} source_start")
    gain = finite_number(sound.get("gain", 1), f"music {index} gain")
    if start < 0 or end <= start or end > duration + 0.0001:
        raise ValueError(f"music {index} timeline bounds are invalid")
    if source_start < 0 or gain < 0 or gain > 1:
        raise ValueError(f"music {index} source_start/gain are invalid")
    return path, start, end, source_start, gain, sound.get("envelope")


def read_words(path):
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    if "words" in data:
        return data["words"]
    return [word for segment in data.get("segments", []) for word in segment.get("words", [])]


def map_words(words, segments):
    result, cursor = [], 0.0
    if any(float(w["start"]) < 0 or float(w["end"]) <= float(w["start"]) for w in words):
        raise ValueError("word timings must have nonnegative starts and end after start")
    words = sorted(words, key=lambda w: float(w["start"]))
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        for word in words:
            a, b = float(word["start"]), float(word["end"])
            if start <= (a + b) / 2 < end:
                text = str(word.get("word", word.get("text", ""))).strip()
                if text:
                    result.append({**word, "word": text, "start": cursor + max(a, start) - start,
                                   "end": cursor + min(b, end) - start})
        cursor += end - start
    return result


def validate_scene_cues(shots, words, fps):
    """Reject a declared word cue that misses the nearest encoded frame."""
    for shot_index, shot in enumerate(shots):
        scene = shot.get('scene', {})
        if scene.get('kind') not in {'kinetic_ranking', 'kinetic_stat', 'kinetic_comparison'}:
            continue
        for item_index, item in enumerate(scene.get('items', [])):
            for field, index_field, offset_field in (('at','anchor_word_index','cue_offset'),('fade_at','fade_anchor_word_index','fade_cue_offset')):
                if index_field in item:
                    index = int(item[index_field])
                    if not 0 <= index < len(words) or field not in item:
                        raise ValueError(f'shot {shot_index} item {item_index} has invalid {index_field}')
                    expected = words[index]['start'] + float(item.get(offset_field, 0))
                    if abs(float(item[field])-expected) > 1/fps + .001:
                        raise ValueError(f'shot {shot_index} item {item_index} {field} misses spoken cue by more than one frame')


def caption_groups(words, max_words=4, max_chars=27):
    groups, current = [], []
    for word in words:
        gap = current and word["start"] - current[-1]["end"] > 0.35
        too_long = len(" ".join(w["word"] for w in current + [word])) > max_chars
        if current and (len(current) >= max_words or too_long or gap):
            groups.append(current)
            current = []
        current.append(word)
        if word["word"].endswith((".", "?", "!", ":", ";")):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def choose_emphasis(groups, emphasis, captions, defaults):
    """Pick which caption words turn green: listed (or planner-stressed) words, at most
    emphasis_max_per_group per group and never closer than emphasis_min_gap seconds."""
    per_group = int(captions.get("emphasis_max_per_group", defaults["emphasis_max_per_group"]))
    min_gap = float(captions.get("emphasis_min_gap", defaults["emphasis_min_gap"]))
    chosen, last = set(), -1e9
    for i, group in enumerate(groups):
        picked = 0
        for k, word in enumerate(group):
            key = emphasis_key(word["word"])
            if picked >= per_group or not (word.get("emphasis") or (key and key in emphasis)):
                continue
            if float(word["start"]) - last < min_gap:
                continue
            chosen.add((i, k))
            picked += 1
            last = float(word["start"])
    return chosen


def caption_visibility(spans, duration):
    """GSAP sets that hide the caption anchor during the merged spans and show it otherwise."""
    merged = []
    for a, b in sorted((max(0.0, float(a)), min(duration, float(b))) for a, b in spans if float(b) > float(a)):
        if merged and a <= merged[-1][1] + 1e-3:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    lines = ['tl.set("#caption-anchor",{autoAlpha:1},0);']
    for a, b in merged:
        lines.append(f'tl.set("#caption-anchor",{{autoAlpha:0}},{a:.4f});')
        if b < duration - 1e-3:
            lines.append(f'tl.set("#caption-anchor",{{autoAlpha:1}},{b:.4f});')
    return lines


def phrase_groups(words, phrases):
    """Optional reviewed semantic captions, with complete ordered word coverage."""
    groups, cursor = [], 0
    for phrase in phrases:
        start, end = phrase["word_range"]
        if start != cursor or not start < end <= len(words):
            raise ValueError("caption phrases must cover words once, in order")
        breaks = phrase.get("line_breaks", [])
        if breaks != sorted(set(breaks)) or any(not 0 < b < end-start for b in breaks):
            raise ValueError("caption line break is outside its phrase")
        groups.append(words[start:end])
        cursor = end
    if cursor != len(words):
        raise ValueError("caption phrases do not cover the complete transcript")
    return groups


def validate_editorial_graphics(graphics, duration):
    """Check independent, claim-linked graphic timing and normalized placement."""
    if not isinstance(graphics, list):
        raise ValueError("editorial_graphics must be a list")
    for index, item in enumerate(graphics):
        if not isinstance(item, dict) or not str(item.get("claim_id", "")).strip():
            raise ValueError(f"editorial graphic {index} needs a claim_id")
        if not str(item.get("text", "")).strip():
            raise ValueError(f"editorial graphic {index} needs text")
        start = finite_number(item.get("start"), f"editorial graphic {index} start")
        end = finite_number(item.get("end"), f"editorial graphic {index} end")
        if not 0 <= start < end <= duration + 0.0001:
            raise ValueError(f"editorial graphic {index} lies outside output timeline")
        x = finite_number(item.get("x", 6), f"editorial graphic {index} x")
        y = finite_number(item.get("y", 12), f"editorial graphic {index} y")
        width = finite_number(item.get("width", 88), f"editorial graphic {index} width")
        if not 0 <= x <= 100 or not 0 <= y <= 100 or width <= 0 or x + width > 100:
            raise ValueError(f"editorial graphic {index} exceeds canvas")
        if item.get("animation", "rise") not in {"rise", "pop", "fade"}:
            raise ValueError(f"editorial graphic {index} has unknown animation")
        if item.get("align", "left") not in {"left", "center", "right"}:
            raise ValueError(f"editorial graphic {index} has unknown alignment")
        if item.get("font_size") is not None and finite_number(item["font_size"], "font_size") <= 0:
            raise ValueError(f"editorial graphic {index} font_size must be positive")
    return graphics


def editorial_words(item):
    """Escape user text and emphasize only literal words present in that text."""
    accent = {str(w).casefold().strip('.,!?;:') for w in item.get("accent_words", [])}
    words = []
    for token in str(item["text"]).split():
        klass = "editorial-accent" if token.casefold().strip('.,!?;:') in accent else "editorial-white"
        words.append(f'<span class="{klass}">{escape(token)}</span>')
    return " ".join(words)


def resolve_legacy_times(spec, resolver):
    """Copy the spec with word cues in shared timing fields replaced by seconds."""
    spec = copy.deepcopy(spec)

    def fix(item, key, label, after=None):
        if key in item and item[key] is not None and not isinstance(item[key], (int, float)):
            # Starts must be unambiguous; ends take the next occurrence after their start.
            item[key] = resolver.frame(resolver.resolve(item[key], label, after, strict=after is None))

    for i, shot in enumerate(spec.get("shots", [])):
        fix(shot, "start", f"shot {i} start")
        fix(shot, "end", f"shot {i} end", float(shot["start"]) + 1e-3 if isinstance(shot.get("start"), (int, float)) else None)
        for j, item in enumerate(shot.get("scene", {}).get("items", []) if isinstance(shot.get("scene"), dict) else []):
            fix(item, "at", f"shot {i} item {j} at")
            fix(item, "fade_at", f"shot {i} item {j} fade_at")
        for j, cue in enumerate(shot.get("scene", {}).get("motion_cues", []) if isinstance(shot.get("scene"), dict) else []):
            fix(cue, "at", f"shot {i} motion cue {j}")
    for collection, keys in (("editorial_graphics", ("start", "end")), ("labels", ("start", "end")),
                             ("zooms", ("at",)), ("flashes", ("at",)), ("transitions", ("at",)),
                             ("sfx", ("at",)), ("camera", ("at",))):
        for i, item in enumerate(spec.get(collection, [])):
            if isinstance(item, dict):
                for key in keys:
                    after = float(item["start"]) + 1e-3 if key == "end" and isinstance(item.get("start"), (int, float)) else None
                    fix(item, key, f"{collection} {i} {key}", after)
    return spec


def make_accent(path, kind):
    """Legacy entry point: synthesize a named accent with the non-tonal SFX kit."""
    return sfx_kit.write(kind, path)


def shot_motion(value, label):
    if value is None:
        return {"kind": "cut", "duration": 0.0}
    motion = {"kind": value} if isinstance(value, str) else dict(value)
    if motion.get("kind") not in SHOT_MOTIONS:
        raise ValueError(f"{label} kind must be one of {', '.join(sorted(SHOT_MOTIONS))}")
    motion["duration"] = finite_number(motion.get("duration", .42), f"{label} duration")
    if not .05 <= motion["duration"] <= 1.5:
        raise ValueError(f"{label} duration must be between 0.05 and 1.5 seconds")
    return motion


def stage_settings(spec, shot, index):
    settings = dict(STAGE_DEFAULTS)
    settings.update(spec.get("stage", {}))
    settings.update(shot.get("stage", {}))
    unknown = set(settings) - set(STAGE_DEFAULTS)
    if unknown:
        raise ValueError(f"shot {index} stage has unknown keys: {', '.join(sorted(unknown))}")
    for key in ("band_top", "inset", "bottom", "radius", "presenter_scale", "presenter_x", "presenter_y"):
        settings[key] = finite_number(settings[key], f"shot {index} stage.{key}")
    if not 35 <= settings["band_top"] <= 85:
        raise ValueError(f"shot {index} stage.band_top must keep a readable presenter band (35-85%)")
    if not 0.4 <= settings["presenter_scale"] <= 1.6:
        raise ValueError(f"shot {index} stage.presenter_scale must be between 0.4 and 1.6")
    if settings["edge"] not in {"card", "fade"}:
        raise ValueError(f"shot {index} stage.edge must be card or fade")
    return settings


def build(spec_path, project):
    spec_path, project = Path(spec_path).resolve(), Path(project).resolve()
    raw_spec = json.loads(spec_path.read_text())
    project.mkdir(parents=True, exist_ok=True)
    assets = project / "assets"
    assets.mkdir(exist_ok=True)
    copied = {}

    def media(value):
        source = resolve(value, spec_path.parent)
        if not source.is_file() or not source.stat().st_size:
            raise ValueError(f"media missing or empty: {source}")
        if source not in copied:
            target = assets / f"media-{len(copied):03}{source.suffix.lower()}"
            if target.exists() and not os.path.samefile(source, target):
                target.unlink()
            if not target.exists():
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copy2(source, target)
            copied[source] = target.relative_to(project).as_posix()
        return copied[source]

    source_path = resolve(raw_spec["source"]["path"], spec_path.parent)
    source_info = probe(source_path)
    source_duration = float(source_info["format"]["duration"])
    segments = raw_spec["source"].get("segments") or [{"start": 0, "end": source_duration}]
    # HyperFrames places each audio clip on a whole millisecond; cutting on that grid keeps
    # every voice clip exactly where the picture and the review expect it.
    segments = [{**s, "start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3)} for s in segments]
    for segment in segments:
        if not 0 <= float(segment["start"]) < float(segment["end"]) <= source_duration + 0.05:
            raise ValueError("source segment lies outside the source video")
    duration = sum(float(s["end"]) - float(s["start"]) for s in segments)
    output = raw_spec.get("output", {})
    width, height, fps = int(output.get("width", 1080)), int(output.get("height", 1920)), int(output.get("fps", 30))
    words = map_words(read_words(resolve(raw_spec["words_path"], spec_path.parent)), segments) if raw_spec.get("words_path") else []
    resolver = CueResolver(words, duration, fps)
    try:
        spec = resolve_legacy_times(raw_spec, resolver)
    except CueError as error:
        raise ValueError(str(error)) from None
    validate_scene_cues(spec.get('shots', []), words, fps)
    music = spec.get("music", [])
    music_required = bool(spec.get("audio_policy", {}).get("music_required", False))
    if music_required or music:
        raise ValueError("Brandon short-form exports must not contain background music; add music on the platform")
    policy = spec.get("audio_policy", {})
    if policy.get("music_required") is not False:
        raise ValueError("audio_policy.music_required must be false for Brandon short-form exports")
    design = design_tokens(spec, style.load(spec.get("style")))
    feel = FEELS[design["feel"]]
    px = Scale(width, height)
    split_fraction = float(output.get("split_fraction", 0.5))
    if not 0.25 <= split_fraction <= 0.75:
        raise ValueError("split_fraction must leave room for both visual and presenter")
    split_height = round(height * split_fraction)
    if "spoken_captions" in spec and "captions" in spec:
        raise ValueError("choose spoken_captions or legacy captions, not both")
    captions = spec.get("spoken_captions", spec.get("captions", {}))
    if not isinstance(captions, dict):
        raise ValueError("spoken_captions must be an object")
    legacy_graphics = validate_editorial_graphics(spec.get("editorial_graphics", []), duration)
    house = style.load(spec.get("style"))
    cap_defaults = style.caption_defaults(house)
    font_size = float(captions.get("font_size", cap_defaults["font_px"] * width / 1080))
    caption_y = finite_number(captions.get('y', cap_defaults["y"]), 'spoken_captions.y')
    if not 60 <= caption_y <= 90:
        raise ValueError('spoken_captions.y must stay in the lower part of the frame (60-90)')
    caption_style = captions.get("style", cap_defaults["style"])
    if caption_style not in {"pop", "phrase", "reveal", "karaoke"}:
        raise ValueError("spoken_captions.style must be pop, phrase, reveal or karaoke")
    if caption_style in cap_defaults.get("forbid_styles", []):
        warnings_early = [f"spoken_captions.style {caption_style!r} changes color on every word; the house style uses 'pop'"]
    else:
        warnings_early = []
    accent = captions.get("accent", cap_defaults["emphasis_color"])
    position = spec["source"].get("object_position", "50% 40%")
    font_name = captions.get("font_family", design["caption_font"])
    font_css = install_fonts(assets)
    if captions.get("font_path"):
        font_name = "BrandonCaption"
        font_css += f"@font-face{{font-family:'BrandonCaption';src:url('{media(captions['font_path'])}');font-weight:900;}}"
    gsap = HERE / "node_modules/gsap/dist/gsap.min.js"
    if not gsap.is_file():
        raise ValueError("run npm ci in production/editor before building")
    shutil.copy2(gsap, assets / "gsap.min.js")
    for plugin in GSAP_PLUGINS:
        shutil.copy2(HERE / f"node_modules/gsap/dist/{plugin}.min.js", assets / f"{plugin}.min.js")

    parts, animations, audio, cursor = [], [], [], 0.0
    warnings = list(warnings_early)
    source = media(str(source_path))
    has_audio = any(stream.get("codec_type") == "audio" for stream in source_info["streams"])
    aroll, matte_parts = [], []
    for i, segment in enumerate(segments):
        length = float(segment["end"]) - float(segment["start"])
        timing = f'data-start="{cursor:.6f}" data-duration="{length:.6f}" data-media-start="{segment["start"]}"'
        aroll.append(f'<video id="aroll-{i}" class="aroll clip" src="{source}" {timing} data-track-index="0" muted playsinline></video>')
        if has_audio:
            audio.append(f'<audio id="voice-{i}" src="{source}" {timing} data-track-index="10" data-volume="1"></audio>')
        cursor += length

    # Optional presenter matte: a transparent video of Brandon on the source clock lets
    # graphics with depth:"behind" sit between the room and his silhouette.
    matte = spec["source"].get("matte")
    if matte:
        matte_path = resolve(matte["path"], spec_path.parent)
        matte_offset = finite_number(matte.get("source_start", 0), "source.matte.source_start")
        matte_length = float(probe(matte_path)["format"]["duration"])
        matte_src = media(str(matte_path))
        cursor = 0.0
        for i, segment in enumerate(segments):
            a, b = float(segment["start"]), float(segment["end"])
            lo, hi = max(a, matte_offset), min(b, matte_offset + matte_length)
            if hi - lo > 1 / fps:
                out_start = cursor + lo - a
                matte_parts.append(f'<video id="matte-{i}" class="aroll matte clip" src="{matte_src}" data-start="{out_start:.6f}" '
                                   f'data-duration="{hi - lo:.6f}" data-media-start="{lo - matte_offset:.6f}" muted playsinline></video>')
            cursor += b - a

    ctx = Ctx(px, design, feel, resolver, width, height, fps, duration, media, house=house)

    def still(asset_rel, at=0.0, blur=0):
        """A frame of an asset as a (pre-blurred, darkened) JPEG: cheap backdrops and
        reflections instead of decoding the same video two or three times."""
        source_file = project / asset_rel
        is_img = source_file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".avif"}
        at = max(0.0, float(at))
        if not is_img:
            # Grabbing past the end of a clip yields no frame: clamp to its last tenth of a second.
            try:
                at = min(at, max(0.0, float(probe(source_file)["format"]["duration"]) - .1))
            except (KeyError, ValueError, subprocess.CalledProcessError):
                pass
        target = assets / f"still-{Path(asset_rel).stem}-{int(round(at * 1000))}-{int(blur)}.jpg"
        if not target.exists():
            chain = "scale=540:-2" + (f",gblur=sigma={blur},eq=brightness=-0.10:saturation=1.15" if blur else "")
            for grab in ([at, 0.0] if at > 0 and not is_img else [at]):
                args = ["ffmpeg", "-v", "error", "-y"] + ([] if is_img else ["-ss", f"{grab:.3f}"])
                subprocess.run(args + ["-i", str(source_file), "-frames:v", "1", "-vf", chain, "-q:v", "3", str(target)], check=True)
                if target.exists() and target.stat().st_size > 0:
                    break
            else:
                raise ValueError(f"could not grab a frame of {asset_rel} at {at:.2f}s for a backdrop or reflection")
        return target.relative_to(project).as_posix()
    ctx.still = still

    # Legacy editorial graphics render through the kinetic statement component.
    upgraded = []
    for i, item in enumerate(legacy_graphics):
        upgraded.append({"id": f"editorial-{i}", "type": "statement", "start": float(item["start"]), "end": float(item["end"]),
                         "beat": item["claim_id"], "text": item["text"], "accent_words": item.get("accent_words", []),
                         "x": item.get("x", 6), "y": item.get("y", 12), "w": item.get("width", 88),
                         "size": float(item.get("font_size", width * .105)) * 1080 / width, "align": item.get("align", "left"),
                         "reveal": item.get("animation", "rise"), "exit": "fade", "sfx": None,
                         "sync": item.get("sync"), "scrim": item.get("scrim", False)})
    try:
        graphic_markup, graphic_anims, graphic_meta = render_graphics(upgraded + spec.get("graphics", []), ctx)
    except CueError as error:
        raise ValueError(str(error)) from None
    warnings.extend(ctx.report)
    behind = [m for m, meta in zip(graphic_markup, graphic_meta) if meta["depth"] == "behind"]
    front = [m for m, meta in zip(graphic_markup, graphic_meta) if meta["depth"] != "behind"]
    if behind and not matte_parts:
        raise ValueError('graphics with depth:"behind" need source.matte (a transparent presenter video)')
    parts.append('<div id="presenter"><div id="presenter-camera" data-layout-allow-overflow>' + "".join(aroll)
                 + (f'<div id="depth-layer">{"".join(behind)}</div>' if behind else "") + "".join(matte_parts) + '</div></div>')

    shots = spec.get("shots", [])
    caption_hidden_shots = []
    backdrops = []
    layout_spans = []
    stage_caption_positions = []
    morph_spans = []
    previous_layout = None
    for i, shot in enumerate(shots):
        start, end = float(shot["start"]), float(shot["end"])
        if not 0 <= start < end <= duration + 0.05:
            raise ValueError(f"shot {i} lies outside output timeline")
        layout = shot.get("layout", "presenter")
        if layout not in {"split", "full_broll", "presenter", "stage", "screen"}:
            raise ValueError(f"unknown shot layout: {layout}")
        layout_spans.append((start, min(end, duration), layout))
        split = layout == "split"
        enter = shot_motion(shot.get("enter"), f"shot {i} enter")
        exit_motion = shot_motion(shot.get("exit"), f"shot {i} exit")
        morph = enter["kind"] == "morph"
        if morph and layout not in {"presenter", "stage"}:
            raise ValueError(f"shot {i} enter morph only moves the presenter between presenter and stage layouts")
        if layout in {"presenter", "stage"}:
            ignored = [f"{phase} {m['kind']}" for phase, m in (("enter", enter), ("exit", exit_motion))
                       if m["kind"] not in {"cut", "morph"}]
            if exit_motion["kind"] == "morph":
                ignored.append("exit morph")
            if ignored:
                warnings.append(f"shot {i}: {', '.join(ignored)} ignored; {layout} shots change by cut or by an enter morph "
                                "(use a transition for anything else)")
        animations.append(f'tl.set("#presenter",{{top:{split_height if split else 0},height:{height-split_height if split else height}}},{start});')
        if not shot.get("spoken_caption_visible", True):
            caption_hidden_shots.append((start, end))
        if shot.get("caption_y") is not None:
            # Captions keep one lower-third anchor across presenter and B-roll shots;
            # only stage shots move it (to the seam above the presenter band).
            warnings.append(f"shot {i}: caption_y is ignored; captions keep the spoken_captions.y anchor. Over busy "
                            "footage set caption_background on the shot; in stage shots use stage.caption_y")
        backing = shot.get("caption_background") or captions.get("background", "rgba(0,0,0,0)")
        if not shot.get("caption_background") and layout in {"full_broll", "split", "screen"} and shot.get("media") and captions.get("auto_backing", True):
            # A screen plane is dense UI moving under the captions: it always gets the backing.
            if layout == "screen" or bright_caption_band(resolve(shot["media"], spec_path.parent), shot, caption_y, split,
                                                         split_fraction):
                backing = "rgba(8,11,9,.86)"
                if layout != "screen":
                    warnings.append(f"shot {i}: bright media under the captions; dark caption backing applied")
        animations.append(f'tl.set(".caption-text",{{backgroundColor:"{backing}"}},{start});')
        if layout == "stage":
            st = stage_settings(spec, shot, i)
            clip = f'inset({st["band_top"]:.3f}% {st["inset"]:.3f}% {st["bottom"]:.3f}% {st["inset"]:.3f}% round {px.n(st["radius"]):.1f}px)'
            camera = {"scale": st["presenter_scale"], "xPercent": st["presenter_x"], "yPercent": st["presenter_y"]}
            stage_caption = st["caption_y"] if st["caption_y"] is not None else max(8, st["band_top"] - 6.2)
            stage_caption_positions.append((start, end, stage_caption))
            mask = ("linear-gradient(180deg,rgba(0,0,0,0) 0%,rgba(0,0,0,0) " + f"{st['band_top'] - 6:.2f}%,#000 {st['band_top'] + 4:.2f}%,#000 100%)")
            if morph:
                d = enter["duration"]
                morph_spans.append((start, start + d))
                if st["edge"] == "card":
                    animations.append(f'tl.to("#presenter",{{clipPath:"{clip}",duration:{d:.3f},ease:"{feel["move"]}"}},{start:.4f});')
                else:
                    animations.append(f'tl.set("#presenter",{{webkitMaskImage:"{mask}",maskImage:"{mask}"}},{start:.4f});')
                animations.append(f'tl.to("#presenter-camera",{{scale:{camera["scale"]},xPercent:{camera["xPercent"]},yPercent:{camera["yPercent"]},duration:{d:.3f},ease:"{feel["move"]}"}},{start:.4f});')
                animations.append(f'tl.to("#caption-anchor",{{y:{(stage_caption - caption_y) * height / 100:.1f},duration:{d:.3f},ease:"{feel["move"]}"}},{start:.4f});')
            else:
                if st["edge"] == "card":
                    animations.append(f'tl.set("#presenter",{{clipPath:"{clip}"}},{start:.4f});')
                else:
                    animations.append(f'tl.set("#presenter",{{clipPath:"inset(0% 0% 0% 0% round 0px)",webkitMaskImage:"{mask}",maskImage:"{mask}"}},{start:.4f});')
                animations.append(f'tl.set("#presenter-camera",{{scale:{camera["scale"]},xPercent:{camera["xPercent"]},yPercent:{camera["yPercent"]}}},{start:.4f});')
                animations.append(f'tl.set("#caption-anchor",{{y:{(stage_caption - caption_y) * height / 100:.1f}}},{start:.4f});')
            following = shots[i + 1] if i + 1 < len(shots) else None
            tail = 0.0
            if following is not None and following.get("layout", "presenter") != "stage":
                follow_motion = shot_motion(following.get("enter"), f"shot {i + 1} enter")
                if follow_motion["kind"] == "morph":
                    tail = follow_motion["duration"]
                elif following.get("layout") == "full_broll" and follow_motion["kind"] != "cut":
                    # Full-frame footage grows over the stage (expand, iris, slide): keep the stage
                    # backdrop and band behind it until it covers the frame, instead of flashing the
                    # full presenter. (The band's frame sits above b-roll, so it still ends at the cut.)
                    tail = min(follow_motion["duration"], (float(following["end"]) - float(following["start"])) * .45)
            backdrop = shot.get("backdrop", design["stage_backdrop"])
            if backdrop not in {"dots", "grid", "radial", "plain"}:
                raise ValueError(f"shot {i} backdrop must be dots, grid, radial or plain")
            bg_end = min(duration, end + tail)
            backdrops.append(f'<div id="stage-bg-{i}" class="clip stage-bg stage-{backdrop}" data-start="{start:.4f}" data-duration="{bg_end - start:.4f}"><div id="stage-bg-{i}-tex" class="stage-tex" data-layout-allow-overflow></div><div class="stage-vignette"></div></div>')
            animations.append(f'tl.fromTo("#stage-bg-{i}-tex",{{y:0}},{{y:{px.n(-60):.1f},duration:{bg_end - start:.3f},ease:"none"}},{start:.4f});')
            if st["edge"] == "card":
                top_px, left_px = height * st["band_top"] / 100, width * st["inset"] / 100
                band_w, band_h = width - 2 * left_px, height * (100 - st["band_top"] - st["bottom"]) / 100
                parts.append(f'<div id="stage-frame-{i}" class="clip stage-frame" data-start="{start:.4f}" data-duration="{end - start:.4f}" '
                             f'style="left:{left_px:.1f}px;top:{top_px:.1f}px;width:{band_w:.1f}px;height:{band_h:.1f}px;border-radius:{px.n(st["radius"]):.1f}px"></div>')
                if morph:
                    animations.append(f'tl.fromTo("#stage-frame-{i}",{{opacity:0}},{{opacity:1,duration:.2}},{start + enter["duration"] * .8:.4f});')
            if morph:
                animations.append(f'tl.fromTo("#stage-bg-{i}",{{opacity:0}},{{opacity:1,duration:{enter["duration"] * .7:.3f},ease:"power1.out"}},{start:.4f});')
                ctx.sound(shot.get("enter_sfx", "whoosh_short"), start, None, f"shot-{i}")
            previous_layout = layout
            continue
        # Any non-stage shot restores the full-frame presenter.
        restore_clip = "inset(0% 0% 0% 0% round 0px)"
        cam = {"scale": shot.get("zoom", 1), "xPercent": shot.get("x_percent", 0), "yPercent": shot.get("y_percent", 0)}
        if shot.get("frame"):
            # Presenter-first framings: stay full size, reframe to open negative space for a graphic.
            frame = shot["frame"]
            if frame not in PRESENTER_FRAMES:
                raise ValueError(f"shot {i} frame must be one of {', '.join(PRESENTER_FRAMES)}")
            cam = dict(zip(("scale", "xPercent", "yPercent"), PRESENTER_FRAMES[frame]))
        if morph and previous_layout != "stage":
            warnings.append(f"shot {i}: enter morph needs a stage shot right before it; this shot cuts in")
        if morph and previous_layout == "stage":
            d = enter["duration"]
            morph_spans.append((start, start + d))
            animations.append(f'tl.to("#presenter",{{clipPath:"{restore_clip}",duration:{d:.3f},ease:"{feel["move"]}"}},{start:.4f});')
            animations.append(f'tl.set("#presenter",{{webkitMaskImage:"none",maskImage:"none"}},{start + d:.4f});')
            animations.append(f'tl.to("#presenter-camera",{{scale:{cam["scale"]},xPercent:{cam["xPercent"]},yPercent:{cam["yPercent"]},duration:{d:.3f},ease:"{feel["move"]}"}},{start:.4f});')
            animations.append(f'tl.to("#caption-anchor",{{y:0,duration:{d:.3f},ease:"{feel["move"]}"}},{start:.4f});')
            ctx.sound(shot.get("enter_sfx", "whoosh_short"), start, None, f"shot-{i}")
        else:
            restore_at = start
            if previous_layout == "stage" and layout == "full_broll" and enter["kind"] != "cut":
                restore_at = start + min(enter["duration"], (end - start) * .45)  # once the footage covers the frame
            animations.append(f'tl.set("#presenter",{{clipPath:"{restore_clip}",webkitMaskImage:"none",maskImage:"none"}},{restore_at:.4f});')
            if shot.get("frame_move") == "glide" and previous_layout == "presenter":
                glide = min(.7, (end - start) * .4)
                animations.append(f'tl.to("#presenter-camera",{{scale:{cam["scale"]},xPercent:{cam["xPercent"]},yPercent:{cam["yPercent"]},duration:{glide:.3f},ease:"{feel["move"]}"}},{restore_at:.4f});')
            else:
                animations.append(f'tl.set("#presenter-camera",{{scale:{cam["scale"]},xPercent:{cam["xPercent"]},yPercent:{cam["yPercent"]}}},{restore_at:.4f});')
            animations.append(f'tl.set("#caption-anchor",{{y:0}},{start});')
        if shot.get('zoom_to') is not None:
            zoom_to = finite_number(shot['zoom_to'], f'shot {i} zoom_to')
            if not 1 <= zoom_to <= 1.2:
                raise ValueError('zoom_to must be between 1 and 1.2')
            animations.append(f'tl.to("#presenter-camera",{{scale:{zoom_to},duration:{min(end-start,.85)},ease:"power2.out"}},{start});')
        previous_layout = layout
        if layout == "presenter":
            continue
        rect = f'width:{width}px;height:{split_height if split else height}px;'
        timing = f'data-start="{start}" data-duration="{end-start}" data-track-index="2"'
        inner = []
        if layout == "screen":
            if not shot.get("media"):
                raise ValueError(f"shot {i} screen layout needs media (a capture)")
            path = media(shot["media"])
            is_image = Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".avif"}
            try:
                screen, motion = screen_markup(shot, i, start, end, ctx, path, is_image, width, height)
            except CueError as error:
                raise ValueError(str(error)) from None
            # A timed canvas fill sits first so nothing of the presenter shows around the plane.
            fill = (f'<div id="screen-fill-{i}" class="clip" data-start="{start}" data-duration="{end-start}" data-track-index="1" '
                    f'style="position:absolute;left:0;top:0;{rect}background:{escape(design["canvas"])};"></div>')
            parts.append(f'<div id="shot-{i}" class="clip shot-wrap" data-start="{start}" data-duration="{end-start}" style="position:absolute;left:0;top:0;{rect}z-index:2;">{fill}{screen}</div>')
            animations.extend(motion)
            animations.extend(shot_transition(f"#shot-{i}", enter, start, end, "enter", feel, px, width, height))
            animations.extend(shot_transition(f"#shot-{i}", exit_motion, start, end, "exit", feel, px, width, height))
            continue
        if shot.get("media"):
            path = media(shot["media"])
            image = Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".avif"}
            if image and not shot.get('media_motion') and abs(float(shot.get('media_zoom', 1))-1) < .0001:
                raise ValueError(f"shot {i} still image needs directed media_motion or media_zoom")
            tag = "img" if image else "video"
            extra = '' if image else f' muted playsinline data-media-start="{shot.get("source_start",0)}"'
            media_style = f'{rect}object-fit:{escape(shot.get("fit","contain"))};object-position:{escape(shot.get("object_position","50% 50%"))};background:{escape(shot.get("background","#111"))};'
            if shot.get("media_crop"):
                x, y, cw, ch = map(float, shot["media_crop"])
                info = next(s for s in probe(project/path)["streams"] if s.get("codec_type") == "video")
                iw, ih = info["width"], info["height"]
                if min(x,y)<0 or min(cw,ch)<=0 or x+cw>iw or y+ch>ih:
                    raise ValueError(f"shot {i} crop is outside source pixels")
                scale = min(width/cw, (split_height if split else height)/ch)
                left = (width-cw*scale)/2-x*scale
                top = ((split_height if split else height)-ch*scale)/2-y*scale
                media_style = f'width:{iw*scale}px;height:{ih*scale}px;left:{left}px;top:{top}px;max-width:none;clip-path:inset({y*scale}px {(iw-x-cw)*scale}px {(ih-y-ch)*scale}px {x*scale}px);'
            # Native video composition may not paint the element's CSS background
            # behind contain-fit media. A timed canvas-sized fill keeps portrait
            # phone inserts from exposing strips of the presenter at their sides.
            inner.append(f'<div id="broll-fill-{i}" class="clip" data-start="{start}" data-duration="{end-start}" data-track-index="1" style="position:absolute;left:0;top:0;z-index:2;{rect}background:{escape(shot.get("background","#111"))};"></div>')
            inner.append(f'<div class="broll-viewport" style="{rect}"><div id="broll-camera-{i}" class="broll-camera" data-layout-allow-overflow><{tag} id="broll-{i}" class="broll clip" src="{path}" {timing}{extra} style="{media_style}"></{tag}></div></div>')
            if shot.get("media_zoom") and not shot.get("media_motion"):
                animations.append(f'tl.fromTo("#broll-camera-{i}",{{scale:1}},{{scale:{float(shot["media_zoom"])},duration:{end-start},ease:"none"}},{start});')
            motion = shot.get("media_motion")
            if motion is not None:
                if not isinstance(motion, dict) or not isinstance(motion.get("from"), dict) or not isinstance(motion.get("to"), dict):
                    raise ValueError(f"shot {i} media_motion needs from/to objects")
                def motion_values(state, label):
                    return {"scale": finite_number(state.get("scale", 1), f"shot {i} media_motion {label}.scale"),
                            "xPercent": finite_number(state.get("x_percent", 0), f"shot {i} media_motion {label}.x_percent"),
                            "yPercent": finite_number(state.get("y_percent", 0), f"shot {i} media_motion {label}.y_percent")}
                motion_from = motion_values(motion["from"], "from")
                motion_to = motion_values(motion["to"], "to")
                animations.append(f'tl.fromTo("#broll-camera-{i}",{json.dumps(motion_from,separators=(",",":"))},{json.dumps({**motion_to,"duration":end-start,"ease":"none"},separators=(",",":"))},{start});')
        elif shot.get("scene"):
            kind = shot["scene"].get("kind")
            maker = (artifact_markup if kind == "artifact_preview" else
                     kinetic_markup if kind in {"kinetic_ranking", "kinetic_stat", "kinetic_comparison"} else scene_markup)
            scene, motion = maker(shot["scene"], f'motion-{i}', start, end, width, split_height if split else height)
            inner.append(scene)
            animations.extend(motion)
        elif shot.get("graphic"):
            graphic = shot["graphic"]
            cards = ''.join(f'<div class="role" id="role-{i}-{j}"><strong>{escape(c.get("label",""))}</strong><span>{escape(c.get("text",""))}</span></div>' for j,c in enumerate(graphic.get("cards",[])))
            inner.append(f'<section id="graphic-{i}" class="graphic clip" {timing} style="{rect}"><div class="graphic-inner"><p class="eyebrow">{escape(graphic.get("eyebrow",""))}</p><h1>{escape(graphic.get("title",""))}</h1><div class="roles">{cards}</div><p class="footer">{escape(graphic.get("footer",""))}</p></div></section>')
            animations.append(f'tl.fromTo("#graphic-{i} .role",{{y:18,opacity:0}},{{y:0,opacity:1,duration:0.22,stagger:0.08,ease:"power2.out"}},{start});')
            animations.append(f'tl.fromTo("#graphic-{i} h1, #graphic-{i} .eyebrow, #graphic-{i} .footer",{{y:16,opacity:0}},{{y:0,opacity:1,duration:0.22,stagger:0.10,ease:"power2.out"}},{start});')
        else:
            raise ValueError(f"shot {i} needs media or graphic for {layout}")
        parts.append(f'<div id="shot-{i}" class="clip shot-wrap" data-start="{start}" data-duration="{end-start}" style="position:absolute;left:0;top:0;{rect}z-index:2;">{"".join(inner)}</div>')
        animations.extend(shot_transition(f"#shot-{i}", enter, start, end, "enter", feel, px, width, height))
        animations.extend(shot_transition(f"#shot-{i}", exit_motion, start, end, "exit", feel, px, width, height))
        if enter["kind"] not in {"cut", "fade"} and shot.get("enter_sfx", "whoosh_short"):
            ctx.sound(shot.get("enter_sfx", "whoosh_short"), start, None, f"shot-{i}")

    for zoom in spec.get("zooms", []):
        animations.append(f'tl.to("#presenter-camera",{{scale:{float(zoom["scale"])},duration:{float(zoom.get("duration",0.16))},ease:"power2.out"}},{float(zoom["at"])});')
    for j, move in enumerate(spec.get("camera", [])):
        animations.extend(camera_move(move, j, duration, feel, px, ctx))
        if move.get("kind", "push") in {"push", "punch"}:
            for a, b in morph_spans:
                if a - 1e-3 < float(move["at"]) < b - 1e-3:
                    warnings.append(f'camera {j} {move.get("kind", "push")} at {float(move["at"]):.2f}s starts during the presenter morph '
                                    f'({a:.2f}-{b:.2f}s); start it after the morph so the two moves do not fight')

    phrases = captions.get("phrases", [])
    groups = phrase_groups(words, phrases) if phrases else caption_groups(
        words, int(captions.get("max_words", cap_defaults["max_words"])), int(captions.get("max_chars", cap_defaults["max_chars"])))
    emphasis = {emphasis_key(w) for w in captions.get("emphasis", [])} - {""}
    emphasized_ids = choose_emphasis(groups, emphasis, captions, cap_defaults)
    uppercase = captions.get("uppercase", cap_defaults["uppercase"])
    omit_punct = captions.get("omit_terminal_punctuation", cap_defaults["omit_terminal_punctuation"])
    hold = float(captions.get("hold", cap_defaults["hold"]))
    parts.append('<div id="caption-anchor">')
    for i, group in enumerate(groups):
        start = group[0]["start"]
        next_start = groups[i+1][0]["start"] if i+1<len(groups) else duration
        end = min(next_start, group[-1]["end"] + hold)
        phrase = phrases[i] if phrases else {}
        breaks = [0, *phrase.get("line_breaks", []), len(group)]
        lines = []
        for j, (a, b) in enumerate(zip(breaks, breaks[1:])):
            connector = j == 0 and phrase.get("lead_in", False)
            spans = []
            for k, word in enumerate(group[a:b], start=a):
                text = word["word"].strip(".,!?:;") if omit_punct else word["word"]
                emphasized = (i, k) in emphasized_ids
                text = text.upper() if uppercase and not connector else text
                wid = f"caption-{i}-w{k}"
                spans.append(f'<span id="{wid}" class="{"emphasis" if emphasized else "word"}">{escape(text)}</span>')
                spoken = max(start, resolver.frame(word["start"]))
                if caption_style == "karaoke":
                    color = accent if emphasized else "#ffffff"
                    animations.append(f'tl.to("#{wid}",{{color:"{color}",duration:.06,ease:"none"}},{spoken:.4f});')
                elif caption_style == "reveal":
                    animations.append(f'tl.fromTo("#{wid}",{{opacity:0,y:{px.n(10):.1f}}},{{opacity:1,y:0,duration:.1,ease:"power2.out"}},{spoken:.4f});')
                elif caption_style == "pop" and k > 0:
                    # Later words keep their space (no re-centering jump) and pop in when spoken;
                    # an emphasized word pops a little bigger in the same tween.
                    grow = 1.3 if emphasized else .82
                    animations.append(f'tl.fromTo("#{wid}",{{opacity:0,scale:{grow},y:{px.n(6):.1f}}},{{opacity:1,scale:1,y:0,duration:{.3 if emphasized else .12},ease:"back.out(2)"}},{spoken:.4f});')
                if emphasized and not (caption_style == "pop" and k > 0):
                    animations.append(f'tl.fromTo("#{wid}",{{scale:{1.14 if caption_style == "pop" else 1.22}}},{{scale:1,duration:.3,ease:"{feel["pop"]}",immediateRender:false}},{spoken:.4f});')
            line_id = f'caption-{i}-line-{j}'
            lines.append(f'<span id="{line_id}" class="caption-line {"connector" if connector else ""}">{" ".join(spans)}</span>')
            if j and phrase.get("progressive", True):
                animations.append(f'tl.fromTo("#{line_id}",{{opacity:0,y:6}},{{opacity:1,y:0,duration:0.07,ease:"power2.out"}},{group[a]["start"]});')
        klass = {"karaoke": " karaoke", "pop": " pop"}.get(caption_style, "")
        parts.append(f'<div id="caption-{i}" class="caption clip{klass}" data-start="{start}" data-duration="{max(.01,end-start)}" data-track-index="5"><div class="caption-text">{"".join(lines)}</div></div>')
        if caption_style == "pop":
            animations.append(f'tl.fromTo("#caption-{i} .caption-text",{{scale:.86,y:{px.n(12):.1f},opacity:0}},{{scale:1,y:0,opacity:1,duration:0.16,ease:"back.out(1.8)"}},{start});')
        else:
            animations.append(f'tl.fromTo("#caption-{i} .caption-text",{{scale:0.94,y:{px.n(8):.1f}}},{{scale:1,y:0,duration:0.12,ease:"power2.out"}},{start});')
    # Captions step aside while hero text says the same words, and wherever a shot hides them.
    hide_spans = [(a, b) for a, b in caption_hidden_shots]
    if captions.get("hide_under_hero", cap_defaults["hide_under_hero"]):
        for meta in graphic_meta:
            if meta.get("hides_captions"):
                hide_spans.append((meta["start"], meta["end"]))
    animations.extend(caption_visibility(hide_spans, duration))
    parts.append('</div>')
    parts.extend(front)
    animations.extend(graphic_anims)

    for i, flash in enumerate(spec.get("flashes", [])):
        at, length = float(flash["at"]), float(flash.get("duration", .16))
        peak = min(.22, max(0, float(flash.get("opacity", .14))))
        color = str(flash.get("color", "#fff4e6"))
        if color.lower() in {design["accent"].lower(), "#49cf26", "green"}:
            raise ValueError("green flashes were retired after Brandon's review; use a neutral flash or a full-frame transition")
        parts.append(f'<div id="light-leak-clip-{i}" class="clip" data-start="{at}" data-duration="{length}" data-track-index="7" style="position:absolute;inset:0;z-index:7;pointer-events:none;"><div id="light-leak-{i}" style="position:absolute;inset:0;opacity:0;background:radial-gradient(ellipse at 50% 45%,{escape(color)},transparent 80%);"></div></div>')
        animations.append(f'tl.fromTo("#light-leak-{i}",{{opacity:0}},{{opacity:{peak},duration:{length*.3}}},{at});tl.to("#light-leak-{i}",{{opacity:0,duration:{length*.7}}},{at+length*.3});tl.set("#light-leak-{i}",{{opacity:0}},{at+length});')
    transition_log = []
    for i, transition in enumerate(spec.get("transitions", [])):
        markup, motion, log = frame_transition(transition, i, duration, px, ctx)
        parts.extend(markup)
        animations.extend(motion)
        transition_log.append(log)
    for i, label in enumerate(spec.get("labels", [])):
        parts.append(f'<div id="label-{i}" class="editor-label clip" data-start="{label["start"]}" data-duration="{label["end"]-label["start"]}" data-track-index="6" style="top:{float(label.get("y",4))}%;left:{float(label.get("x",5))}%;">{escape(label["text"])}</div>')
        animations.append(f'tl.fromTo("#label-{i}",{{opacity:0,y:12}},{{opacity:1,y:0,duration:.22,ease:"power2.out"}},{float(label["start"])});')

    sfx_events = []
    for sound in spec.get("sfx", []):
        event = {"kind": sound.get("kind"), "at": float(sound["at"]), "gain": sound.get("gain"), "source": "timeline", "explicit": True}
        if sound.get("path"):
            event.update({"kind": "file", "path": sound["path"], "duration": sound.get("duration")})
        elif sound.get("duration") is not None:
            event["duration"] = sound["duration"]
        sfx_events.append(event)
    if spec.get("sfx_auto", True):
        sfx_events.extend(ctx.sfx_events)
    file_events = [e for e in sfx_events if e["kind"] == "file"]
    synth_events = [e for e in sfx_events if e["kind"] != "file"]
    kept, dropped = sfx_kit.plan(synth_events, duration, spec.get("sfx_policy"), words=words, house=house)
    band = house["sound"]["phone_band_hz"]
    voice_lufs = voice_loudness(source_path, segments) if has_audio and kept else None
    voice_phone = voice_loudness(source_path, segments, phone=True, band=band) if has_audio and kept else None
    matched, phone_check = {}, {}
    kept = sorted(kept + file_events, key=lambda e: e["at"])
    sound_tracks = {}
    variants = int(house["sound"].get("bubble_variants") or sfx_kit.VARIANTS)
    last_variant = None
    for i, event in enumerate(kept):
        if event["kind"] == "file":
            path = media(event["path"])
            length = float(event.get("duration") or probe(project/path)["format"]["duration"])
            gain = event.get("gain") if event.get("gain") is not None else .15
        else:
            kind = event["kind"]
            variable = kind in {"typing", "ticker"}
            length_hint = round(float(event.get("duration") or 1.0), 2) if variable else None
            variant = 0
            if kind in sfx_kit.BUBBLES:
                # Stable per moment, and never the same pitch/texture twice in a row.
                variant = sfx_kit.variant_for(event, variants)
                if variant == last_variant and variants > 1:
                    variant = (variant + 1) % variants
                last_variant = event["variant"] = variant
            suffix = ('-' + str(length_hint).replace('.', '_')) if variable else (f"-v{variant}" if kind in sfx_kit.BUBBLES else "")
            target = assets / f"sfx-{kind}{suffix}.wav"
            if not target.exists():
                sfx_kit.write(kind, target, length_hint, variant=variant)
            path = target.relative_to(project).as_posix()
            length = float(probe(target)["format"]["duration"])
            # Each file (bubble variants differ in pitch and texture) is leveled on its own.
            level_key = target.name
            if level_key not in matched:
                matched[level_key] = sfx_kit.matched_gain(kind, target, voice_lufs, house["sound"]["voice_offset_lu"])
                phone_check[level_key] = sfx_kit.phone_offset(target, matched[level_key], voice_phone, band)
            gain = event.get("gain") if event.get("gain") is not None else matched[level_key]
        if not 0 <= float(gain) <= 1:
            raise ValueError(f"SFX gain must be between 0 and 1 (event at {event['at']})")
        length = min(length, max(.02, duration - event["at"]))
        track = sound_tracks.setdefault(path, 12 + len(sound_tracks))
        audio.append(f'<audio id="sfx-{i}" src="{path}" data-start="{event["at"]:.4f}" data-duration="{length:.4f}" data-track-index="{track}" data-volume="{float(gain):.3f}"></audio>')

    css = f'''{font_css}{base_css(design, px)}{MOTION_CSS}{ARTIFACT_CSS}{KINETIC_CSS}{component_css(px)}{motion_css(px)}{screen_css(px)}
    *{{box-sizing:border-box}} body{{margin:0;background:#111}} #root{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:{escape(design["canvas"])}}}
    #presenter{{position:absolute;inset:0;width:{width}px;height:{height}px;overflow:hidden;z-index:1}} #presenter-camera{{position:relative;width:100%;height:100%;transform-origin:50% 38%}}
    #depth-layer{{position:absolute;inset:0;z-index:1}} .matte{{z-index:2}}
    .aroll{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{position}}} .broll,.graphic{{position:absolute;left:0;top:0;z-index:2}}
    .broll-viewport{{position:absolute;left:0;top:0;z-index:2;overflow:hidden}} .broll-camera{{position:relative;width:100%;height:100%;transform-origin:center}}
    #backdrop{{position:absolute;inset:0;z-index:0}} #frame{{z-index:1}}
    .stage-bg{{position:absolute;inset:0;z-index:0;background:var(--canvas);overflow:hidden}}
    .stage-tex{{position:absolute;inset:-10%;}}
    .stage-dots .stage-tex{{background-image:radial-gradient(rgba(255,255,255,.085) {px(1.6)},transparent {px(2.2)});background-size:{px(34)} {px(34)}}}
    .stage-grid .stage-tex{{background-image:linear-gradient(rgba(255,255,255,.05) {px(1.5)},transparent {px(1.5)}),linear-gradient(90deg,rgba(255,255,255,.05) {px(1.5)},transparent {px(1.5)});background-size:{px(72)} {px(72)}}}
    .stage-radial .stage-tex{{background:radial-gradient(ellipse at 50% 34%,rgba(73,207,38,.16),transparent 60%)}}
    .stage-vignette{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 32%,rgba(73,207,38,.07),transparent 55%),radial-gradient(ellipse at 50% 50%,transparent 45%,rgba(0,0,0,.6) 100%)}}
    .stage-frame{{position:absolute;z-index:3;pointer-events:none;border:{px(2)} solid rgba(255,255,255,.13);box-shadow:inset 0 {px(2)} 0 rgba(255,255,255,.08),0 {px(-10)} {px(40)} rgba(0,0,0,.55)}}
    #caption-anchor{{position:absolute;top:{caption_y}%;left:0;width:100%;z-index:8}} .caption{{position:absolute;left:5%;width:90%;text-align:center}}
    .caption-text{{display:inline-block;max-width:100%;border-radius:.16em;padding:.07em .12em;font-family:"{font_name}","Archivo Black","Arial Black",Arial,sans-serif;font-weight:900;font-size:{font_size}px;line-height:1.06;letter-spacing:-0.02em;color:white;-webkit-text-stroke:{width*.0035}px #222;paint-order:stroke fill;text-shadow:0 {width*.003}px {width*.004}px #111;}}
    .caption-line{{display:block}} .caption-line.connector{{font-family:Arial,sans-serif;font-size:.72em;font-weight:500;line-height:1.18;letter-spacing:0;-webkit-text-stroke:{width*.0017}px #222;}}
    .caption .word,.caption .emphasis{{display:inline-block}}
    .emphasis{{color:{accent}}} .pop .emphasis{{text-shadow:0 0 {width*.02:.1f}px rgba(73,207,38,.5),0 {width*.003}px {width*.004}px #111}} .karaoke .word,.karaoke .emphasis{{color:{escape(captions.get("upcoming_color", "#a3aba6"))}}} .graphic{{background:#efede8;color:#171719;font-family:Arial,sans-serif}}
    .editorial-graphic{{position:absolute;z-index:9;max-height:75%;overflow:hidden;color:white;font-family:Arial,sans-serif;font-weight:900;line-height:1.02;letter-spacing:-.035em;text-shadow:0 2px 10px #000b;pointer-events:none;}}
    .editorial-white{{color:#fff}} .editorial-accent{{color:{design["accent"]};text-shadow:0 0 18px #49cf2666,0 2px 10px #000b}}
    .editor-label{{position:absolute;z-index:8;font:700 30px Arial,sans-serif;letter-spacing:.08em;color:#fff;background:#1d1c20;padding:12px 18px;border-radius:6px;}}
    .graphic-inner{{position:absolute;inset:9% 8%;display:flex;flex-direction:column;justify-content:center;gap:{width*.02}px}} .eyebrow{{font-size:{width*.017}px;letter-spacing:.13em;font-weight:800;color:#706476;margin:0}}
    h1{{font-size:{width*.065}px;line-height:1.04;margin:0;letter-spacing:-.055em;font-weight:900}} .roles{{display:grid;grid-template-columns:1fr 1fr;gap:{width*.025}px}}
    .role{{background:#fff;border:2px solid #d4d0d9;border-radius:{width*.023}px;padding:{width*.022}px;display:flex;flex-direction:column;gap:{width*.012}px}} .role strong{{font-size:{width*.032}px;letter-spacing:-.03em}} .role span{{font-size:{width*.022}px;line-height:1.24;color:#57525e}} .footer{{font-size:{width*.022}px;color:#514757;margin:0;line-height:1.3}}
    .fx-layer{{position:absolute;inset:0;z-index:12;pointer-events:none}}
    '''
    filters = ('<svg width="0" height="0" style="position:absolute"><filter id="whip-blur" x="-20%" y="-20%" width="140%" height="140%">'
               '<feGaussianBlur id="whip-blur-g" stdDeviation="0 0"/></filter></svg>')
    scripts = "".join(f'<script src="assets/{name}.min.js"></script>' for name in ("gsap",) + GSAP_PLUGINS)
    helpers = ('function __fmt(v,d,c,p,s){let u="";const a=Math.abs(v);if(c){if(a>=1e9){v/=1e9;u="B"}else if(a>=1e6){v/=1e6;u="M"}else if(a>=1e3){v/=1e3;u="K"}}'
               'return p+Number(v).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d})+u+s;}'
               f'gsap.registerPlugin({",".join(GSAP_PLUGINS)});CustomWiggle.create("shake",{{wiggles:7,type:"easeOut"}});')
    stage = f'{filters}<div id="backdrop">{"".join(backdrops)}</div><div id="frame">{"".join(parts)}</div>{"".join(audio)}'
    animations.extend(boundary_hard_kills("".join(animations), stage))
    markup = (f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(spec.get("title","Brandon reel edit"))}</title>{scripts}<style>{css}</style></head>'
              f'<body><div id="root" data-composition-id="main" data-width="{width}" data-height="{height}" data-duration="{duration}" data-fps="{fps}">'
              f'{stage}</div>'
              f'<script>{helpers}const tl=gsap.timeline({{paused:true}});{FROMTO_GUARD}{"".join(animations)}window.__timelines=window.__timelines||{{}};window.__timelines.main=tl;</script></body></html>')
    (project/"index.html").write_text(markup)
    (project/"timeline.json").write_text(json.dumps(raw_spec,indent=2)+"\n")
    (project/"mapped-words.json").write_text(json.dumps(words,indent=2)+"\n")
    # The same timeline with outer word cues replaced by seconds, for tools that need numbers.
    resolved = copy.deepcopy(spec)
    for item, meta in zip(resolved.get("graphics", []), graphic_meta[len(upgraded):]):
        item.update({"id": meta["id"], "start": meta["start"], "end": meta["end"]})
    (project/"resolved-timeline.json").write_text(json.dumps(resolved,indent=2)+"\n")
    report = motion_report(layout_spans, duration, graphic_meta, kept, dropped, transition_log, resolver, caption_y,
                           stage_caption_positions, warnings)
    ctas = [g.get("style", "chip") for g in spec.get("graphics", []) if g.get("type") == "cta"]
    first = min(graphic_meta, key=lambda g: g["start"])["type"] if graphic_meta else None
    report["signature"] = {"hook": first, "cta_styles": ctas, "stage_sections": sum(1 for *_, l in layout_spans if l == "stage"),
                           "transitions": [t["kind"] for t in transition_log],
                           "sequence": [g["type"] for g in sorted(graphic_meta, key=lambda g: g["start"])]}
    report["cta_styles"] = ctas
    report["timeline"] = [{k: g[k] for k in ("id", "type", "start", "end", "beat")} for g in sorted(graphic_meta, key=lambda g: g["start"])]
    # Full per-graphic facts and the caption/sound plan, for review_reel.py.
    report["graphics_meta"] = sorted(graphic_meta, key=lambda g: g["start"])
    report["captions"] = {"style": caption_style, "font_px_1080": round(font_size * 1080 / width, 1), "groups": len(groups),
                          "max_words": max((len(g) for g in groups), default=0), "emphasized": len(emphasized_ids),
                          "emphasis_times": sorted(round(groups[i][k]["start"], 3) for i, k in emphasized_ids),
                          "hidden_spans": [[round(a, 3), round(b, 3)] for a, b in hide_spans]}
    report["sfx_events"] = [{"kind": e["kind"], "at": round(float(e["at"]), 3), "role": e.get("role"), "source": e.get("source", ""),
                             "variant": e.get("variant") if e["kind"] in sfx_kit.BUBBLES else None} for e in kept]
    avoid = spec.get("variation", {}).get("avoid", {})
    if first and first in avoid.get("hooks", []):
        report["warnings"].append(f"hook treatment {first!r} repeats a recent reel (variation.avoid.hooks)")
    for cta_style in ctas:
        if cta_style in avoid.get("cta_styles", []):
            report["warnings"].append(f"CTA style {cta_style!r} repeats a recent reel (variation.avoid.cta_styles)")
    limit = house["sound"]["phone_max_lu_over_voice"]
    loud_on_phone = {k: v for k, v in phone_check.items() if v is not None and v > limit}
    for kind, offset in loud_on_phone.items():
        report["warnings"].append(f"{kind} peaks {offset:+.1f} LU against the voice on a phone speaker band "
                                  f"(limit {limit} LU); lower it or move it off the words")
    report["sfx_levels"] = {"voice_integrated_lufs": voice_lufs, "voice_phone_band_lufs": voice_phone, "gains": matched,
                            "phone_band_offset_lu": phone_check,
                            "basis": "each sound's loudest 400 ms sits the house voice offset under the voice (full band); "
                                     "phone_band_offset_lu repeats the check through a 300 Hz-8 kHz phone-speaker band. Confirm by listening."}
    receipt = {"project":str(project),"duration":duration,"width":width,"height":height,"fps":fps,"words":len(words),
               "caption_groups":len(groups),"caption_style":caption_style,"editorial_graphics":len(legacy_graphics),
               "graphics":len(graphic_meta),"shots":len(shots),"original_audio_preserved":has_audio,
               "music_count":len(music),"music_required":music_required,"design":{k: design[k] for k in ("accent", "feel", "display_font", "caption_font")},
               "media_transfer":"local hardlink or copy; no upload","rendered":False,"motion_report":report}
    (project/"build-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    return receipt


def voice_loudness(path, segments, phone=False, band=None):
    """Integrated loudness (LUFS) of the kept speech; SFX levels are set relative to it.
    phone=True measures through a phone-speaker band (``band`` Hz, default the house style's)."""
    filters = "".join(f"[0:a]atrim={float(s['start'])}:{float(s['end'])},asetpts=PTS-STARTPTS[a{i}];" for i, s in enumerate(segments))
    joined = "".join(f"[a{i}]" for i in range(len(segments)))
    shaping = ""
    if phone:
        lo, hi = band or STYLE["sound"]["phone_band_hz"]
        shaping = f"highpass=f={lo}:poles=2,highpass=f={lo}:poles=2,lowpass=f={hi}:poles=2,"
    graph = f"{filters}{joined}concat=n={len(segments)}:v=0:a=1,{shaping}ebur128[out]"
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-filter_complex", graph,
                             "-map", "[out]", "-f", "null", "-"], capture_output=True, text=True)
    found = re.findall(r"I:\s*(-?\d+\.\d) LUFS", result.stderr)
    if not found:
        return None
    value = float(found[-1])
    return value if value > -60 else None


def bright_caption_band(path, shot, caption_y, split, split_fraction, whole=False):
    """Sample the media where captions sit; light UI needs a caption backing. A 2.5D screen
    plane moves under the captions, so whole=True judges the capture's overall brightness."""
    try:
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".avif"}:
            args = ["ffmpeg", "-v", "error", "-i", str(path)]
        else:
            at = float(shot.get("source_start", 0)) + max(0.0, (float(shot["end"]) - float(shot["start"])) / 2)
            args = ["ffmpeg", "-v", "error", "-ss", f"{at:.3f}", "-i", str(path)]
        raw = subprocess.run(args + ["-frames:v", "1", "-vf", "scale=90:160,format=gray", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError, ValueError):
        return False
    if len(raw) < 90 * 160:
        return False
    if whole:
        return sum(raw) / len(raw) > 140
    if split:
        seam = split_fraction * 100
        if caption_y - 3 >= seam:
            return False  # the captions sit over the presenter, not the media
        caption_y = caption_y / split_fraction
    top = int(160 * (caption_y - 3) / 100)
    band = raw[top * 90:min(160, top + 16) * 90]
    return bool(band) and sum(band) / len(band) > 150


def shot_transition(target, motion, start, end, phase, feel, px, width, height):
    """Enter/exit choreography for a whole shot container (b-roll, scene or card)."""
    kind = motion["kind"]
    if kind in {"cut", "morph"}:
        return []
    d = min(motion["duration"], (end - start) * .45)
    at = start if phase == "enter" else max(start, end - d)
    ease = feel["enter"] if phase == "enter" else feel["exit"]
    ox, oy = motion.get("origin", [50, 50])
    states = {
        "fade": ({"opacity": 0}, {"opacity": 1}),
        "slide_up": ({"yPercent": 100}, {"yPercent": 0}),
        "slide_down": ({"yPercent": -100}, {"yPercent": 0}),
        "slide_left": ({"xPercent": 100}, {"xPercent": 0}),
        "slide_right": ({"xPercent": -100}, {"xPercent": 0}),
        "iris": ({"clipPath": f"circle(0% at {ox}% {oy}%)"}, {"clipPath": f"circle(150% at {ox}% {oy}%)"}),
        "zoom": ({"scale": 1.18, "opacity": 0, "filter": "blur(14px)"}, {"scale": 1, "opacity": 1, "filter": "blur(0px)"}),
        "expand": ({"clipPath": f"inset(30% 18% 30% 18% round {px.n(48):.0f}px)"}, {"clipPath": "inset(0% 0% 0% 0% round 0px)"}),
    }
    hidden, shown = states[kind]
    if phase == "enter":
        return [f'tl.fromTo("{target}",{json.dumps(hidden)},{json.dumps({**shown, "duration": round(d, 3), "ease": ease})},{at:.4f});']
    exit_state = dict(hidden)
    if kind == "slide_up":
        exit_state = {"yPercent": -100}
    elif kind == "slide_left":
        exit_state = {"xPercent": -100}
    elif kind == "slide_right":
        exit_state = {"xPercent": 100}
    elif kind == "slide_down":
        exit_state = {"yPercent": 100}
    return [f'tl.to("{target}",{json.dumps({**exit_state, "duration": round(d, 3), "ease": ease})},{at:.4f});']


def camera_move(move, index, duration, feel, px, ctx):
    kind = move.get("kind", "push")
    at = finite_number(move.get("at"), f"camera {index} at")
    if not 0 <= at < duration:
        raise ValueError(f"camera {index} lies outside the timeline")
    scale = finite_number(move.get("scale", 1), f"camera {index} scale")
    x, y = finite_number(move.get("x", 0), "camera x"), finite_number(move.get("y", 0), "camera y")
    if kind == "punch":
        if not .8 <= scale <= 1.6:
            raise ValueError(f"camera {index} punch scale must be between 0.8 and 1.6")
        return [f'tl.set("#presenter-camera",{{scale:{scale},xPercent:{x},yPercent:{y}}},{at:.4f});']
    if kind == "push":
        d = finite_number(move.get("duration", 1.2), f"camera {index} duration")
        if not .8 <= scale <= 1.6:
            raise ValueError(f"camera {index} push scale must be between 0.8 and 1.6")
        return [f'tl.to("#presenter-camera",{{scale:{scale},xPercent:{x},yPercent:{y},duration:{d:.3f},ease:"{move.get("ease", "sine.inOut")}"}},{at:.4f});']
    if kind == "shake":
        amp = finite_number(move.get("amount", 7), f"camera {index} amount")
        if not 0 < amp <= 20:
            raise ValueError(f"camera {index} shake amount must be between 0 and 20 (design px)")
        d = finite_number(move.get("duration", .32), f"camera {index} duration")
        if move.get("sfx"):
            ctx.sound(move["sfx"], at, None, f"camera-{index}")
        return [f'tl.fromTo("#frame",{{x:0}},{{x:{px.n(amp):.1f},duration:{d:.3f},ease:"shake",immediateRender:false}},{at:.4f});',
                f'tl.set("#frame",{{x:0}},{at + d:.4f});']
    raise ValueError(f"camera {index} kind must be punch, push or shake")


def frame_transition(transition, i, duration, px, ctx):
    at = finite_number(transition.get("at"), f"transition {i} at")
    length = finite_number(transition.get("duration", .24), f"transition {i} duration")
    kind = transition.get("kind")
    if kind == "green_wipe":
        raise ValueError("transition kind green_wipe was retired after Brandon's review (it read as a green half-frame flash); "
                         "use whip, zoom_blur, flash, blur_flash or light_leak, or a shot enter such as iris/expand/slide_up")
    if kind not in TRANSITIONS or not 0 <= at < duration or not 0 < length <= .8 or at + length > duration:
        raise ValueError(f"transition {i} has invalid kind or bounds")
    markup, motion = [], []
    half = length / 2
    if kind in {"blur_flash", "light_leak", "flash"}:
        background = {"blur_flash": "linear-gradient(90deg,transparent,#f6fff3 45%,#f6fff3 55%,transparent)",
                      "light_leak": "linear-gradient(115deg,transparent 20%,rgba(255,176,90,.9) 42%,rgba(255,230,190,.95) 50%,rgba(255,176,90,.9) 58%,transparent 80%)",
                      "flash": "#fffaf2"}[kind]
        markup.append(f'<div id="transition-{i}" class="clip fx-layer" data-start="{at}" data-duration="{length}" data-track-index="8" style="opacity:0;background:{background};"></div>')
        if kind == "light_leak":
            # Crosses the entire frame instead of blooming in one corner.
            peak = min(.5, float(transition.get("opacity", .36)))
            motion.append(f'tl.fromTo("#transition-{i}",{{opacity:0,xPercent:-60}},{{opacity:{peak},xPercent:0,duration:{half:.3f},ease:"power1.in"}},{at});tl.to("#transition-{i}",{{opacity:0,xPercent:60,duration:{half:.3f},ease:"power1.out"}},{at + half});')
        else:
            peak = .45 if kind == "blur_flash" else float(transition.get("opacity", .32))
            motion.append(f'tl.fromTo("#transition-{i}",{{opacity:0}},{{opacity:{peak},duration:{length*.35}}},{at});tl.to("#transition-{i}",{{opacity:0,duration:{length*.65}}},{at+length*.35});')
        # A hard kill where the fade ends, so seeking past it never leaves the layer lit.
        motion.append(f'tl.set("#transition-{i}",{{opacity:0}},{at + length:.4f});')
        if transition.get("sfx"):
            ctx.sound(transition["sfx"], at, None, f"transition-{i}")
    elif kind == "whip":
        direction = transition.get("direction", "left")
        if direction not in {"left", "right", "up", "down"}:
            raise ValueError(f"transition {i} direction must be left, right, up or down")
        axis = "x" if direction in {"left", "right"} else "y"
        sign = -1 if direction in {"left", "up"} else 1
        travel = px.n(140) * sign
        blur = "60 0" if axis == "x" else "0 60"
        motion.append(f'tl.set("#frame",{{filter:"url(#whip-blur)"}},{at - half:.4f});')
        motion.append(f'tl.fromTo("#whip-blur-g",{{attr:{{stdDeviation:"0 0"}}}},{{attr:{{stdDeviation:"{blur}"}},duration:{half - .004:.3f},ease:"power2.in",immediateRender:false}},{at - half:.4f});')
        motion.append(f'tl.fromTo("#frame",{{{axis}:0}},{{{axis}:{travel:.1f},duration:{half - .004:.3f},ease:"power2.in",immediateRender:false}},{at - half:.4f});')
        motion.append(f'tl.set("#frame",{{{axis}:{-travel:.1f}}},{at:.4f});')
        motion.append(f'tl.to("#frame",{{{axis}:0,duration:{half:.3f},ease:"power3.out"}},{at:.4f});')
        motion.append(f'tl.to("#whip-blur-g",{{attr:{{stdDeviation:"0 0"}},duration:{half:.3f},ease:"power3.out"}},{at:.4f});')
        motion.append(f'tl.set("#frame",{{filter:"none"}},{at + half:.4f});')
        ctx.sound(transition.get("sfx", "whoosh"), max(0, at - half), None, f"transition-{i}")
    elif kind == "zoom_blur":
        motion.append(f'tl.fromTo("#frame",{{scale:1,filter:"blur(0px)"}},{{scale:1.14,filter:"blur({px.n(14):.1f}px)",duration:{half - .004:.3f},ease:"power2.in",immediateRender:false}},{at - half:.4f});')
        motion.append(f'tl.set("#frame",{{scale:.9}},{at:.4f});')
        motion.append(f'tl.to("#frame",{{scale:1,filter:"blur(0px)",duration:{half:.3f},ease:"power3.out"}},{at:.4f});')
        motion.append(f'tl.set("#frame",{{filter:"none"}},{at + half:.4f});')
        ctx.sound(transition.get("sfx", "whoosh_short"), max(0, at - half), None, f"transition-{i}")
    elif kind == "push_in":
        # A tracked push into what the viewer should look at next (a card, a screen, a tag);
        # the incoming shot continues the same forward motion.
        tx, ty = (finite_number(v, f"transition {i} target") for v in transition.get("target", [50, 45]))
        depth = finite_number(transition.get("depth", 2.4), f"transition {i} depth")
        motion.append(f'tl.set("#frame",{{transformOrigin:"{tx:.1f}% {ty:.1f}%"}},{at - half:.4f});')
        motion.append(f'tl.fromTo("#frame",{{scale:1,filter:"blur(0px)"}},{{scale:{depth:.2f},filter:"blur({px.n(10):.1f}px)",duration:{half - .004:.3f},ease:"power3.in",immediateRender:false}},{at - half:.4f});')
        motion.append(f'tl.set("#frame",{{transformOrigin:"50% 45%",scale:.74,filter:"blur({px.n(8):.1f}px)"}},{at:.4f});')
        motion.append(f'tl.to("#frame",{{scale:1,filter:"blur(0px)",duration:{half:.3f},ease:"power3.out"}},{at:.4f});')
        motion.append(f'tl.set("#frame",{{filter:"none"}},{at + half:.4f});')
        ctx.sound(transition.get("sfx", "travel"), max(0, at - half), None, f"transition-{i}")
    elif kind == "match_move":
        # Carry one motion vector across the cut: the outgoing shot leaves in the direction of
        # travel and the incoming one arrives from the opposite side still moving that way.
        direction = transition.get("direction", "left")
        if direction not in {"left", "right", "up", "down"}:
            raise ValueError(f"transition {i} direction must be left, right, up or down")
        prop = "xPercent" if direction in {"left", "right"} else "yPercent"
        sign = -1 if direction in {"left", "up"} else 1
        blur = "34 0" if prop == "xPercent" else "0 34"
        motion.append(f'tl.set("#frame",{{filter:"url(#whip-blur)"}},{at - half:.4f});')
        motion.append(f'tl.fromTo("#whip-blur-g",{{attr:{{stdDeviation:"0 0"}}}},{{attr:{{stdDeviation:"{blur}"}},duration:{half - .004:.3f},ease:"power2.in",immediateRender:false}},{at - half:.4f});')
        motion.append(f'tl.fromTo("#frame",{{{prop}:0}},{{{prop}:{sign * 58},duration:{half - .004:.3f},ease:"power3.in",immediateRender:false}},{at - half:.4f});')
        motion.append(f'tl.set("#frame",{{{prop}:{-sign * 58}}},{at:.4f});')
        motion.append(f'tl.to("#frame",{{{prop}:0,duration:{half:.3f},ease:"power3.out"}},{at:.4f});')
        motion.append(f'tl.to("#whip-blur-g",{{attr:{{stdDeviation:"0 0"}},duration:{half:.3f},ease:"power3.out"}},{at:.4f});')
        motion.append(f'tl.set("#frame",{{filter:"none"}},{at + half:.4f});')
        ctx.sound(transition.get("sfx", "travel"), max(0, at - half), None, f"transition-{i}")
    elif kind == "shape_wipe":
        # A shape grows from where the eye already is (a graphic, a button) and clears to the
        # next shot; its color can carry over from the outgoing shot.
        ox, oy = (finite_number(v, f"transition {i} origin") for v in transition.get("origin", [50, 50]))
        color = str(transition.get("color", "#0b0e0c"))
        if color.lower() in {"#49cf26", "green", "accent"}:
            raise ValueError("shape_wipe cannot be accent green (it reads as the retired green flash); carry a color from the shot or use the dark canvas")
        ex, ey = 100 - ox, 100 - oy
        markup.append(f'<div id="transition-{i}" class="clip fx-layer" data-start="{at - half:.4f}" data-duration="{length:.4f}" data-track-index="8" '
                      f'style="background:{escape(color)};clip-path:circle(0% at {ox:.1f}% {oy:.1f}%)"></div>')
        motion.append(f'tl.fromTo("#transition-{i}",{{clipPath:"circle(0% at {ox:.1f}% {oy:.1f}%)"}},{{clipPath:"circle(150% at {ox:.1f}% {oy:.1f}%)",duration:{half:.3f},ease:"power3.in"}},{at - half:.4f});')
        motion.append(f'tl.set("#transition-{i}",{{clipPath:"circle(150% at {ex:.1f}% {ey:.1f}%)"}},{at:.4f});')
        motion.append(f'tl.to("#transition-{i}",{{clipPath:"circle(0% at {ex:.1f}% {ey:.1f}%)",duration:{half:.3f},ease:"power3.out"}},{at:.4f});')
        ctx.sound(transition.get("sfx", "travel"), max(0, at - half), None, f"transition-{i}")
    elif kind == "punch":
        # An energetic hard cut: the incoming shot lands slightly pushed in and settles.
        motion.append(f'tl.fromTo("#frame",{{scale:{finite_number(transition.get("scale", 1.1), f"transition {i} scale"):.3f}}},'
                      f'{{scale:1,duration:{max(.12, length):.3f},ease:"power3.out",immediateRender:false}},{at:.4f});')
        if transition.get("sfx"):
            ctx.sound(transition["sfx"], at, None, f"transition-{i}")
    if kind in {"whip", "zoom_blur", "push_in", "match_move", "shape_wipe"} and at - half < 0:
        raise ValueError(f"transition {i} needs {half:.2f}s before its cut")
    return markup, motion, {"kind": kind, "at": round(at, 3), "duration": length}


BOUNDARY_EPSILON = .05  # HyperFrames' scene-boundary tolerance


def _call_args(script, open_paren):
    """Top-level arguments of the call whose "(" sits at open_paren, and the index after ")"."""
    args, depth, quote, start, k = [], 1, None, open_paren + 1, open_paren + 1
    while k < len(script):
        c = script[k]
        if quote:
            if c == "\\":
                k += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append(script[start:k].strip())
                return args, k + 1
        elif c == "," and depth == 1:
            args.append(script[start:k].strip())
            start = k + 1
        k += 1
    return None, len(script)


def _literal_targets(text):
    """Number of elements a GSAP target literal names ("#a" or ["#a","#b"]), or None if not a literal."""
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if isinstance(value, str):
        return 1
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return len(value)
    return None


def _object_number(obj, key):
    found = re.search(rf'(?:^|[{{,])\s*{key}\s*:\s*(-?[\d.]+)\s*(?=[,}}])', obj)
    return float(found.group(1)) if found else None


def boundary_hard_kills(script, markup):
    """tl.set hard kills for exits that finish on another clip's start.

    HyperFrames rejects a fade to opacity 0 that ends within 50 ms of a clip start
    unless a tl.set with the same target hides it there, because a seek that lands
    after the fade would otherwise keep stale state. Caption clips start on almost
    every word, so any exit can land on one; this adds the kill wherever it is missing.
    """
    boundaries = sorted({float(v) for v in re.findall(r'data-start="(-?[\d.]+)"', markup)})
    exits, kills = [], []
    for match in re.finditer(r'tl\.(to|fromTo|set)\(', script):
        args, _ = _call_args(script, match.end() - 1)
        if not args:
            continue
        method = match.group(1)
        wanted = {"to": 3, "fromTo": 4, "set": 3}[method]
        if len(args) != wanted or _literal_targets(args[0]) is None:
            continue
        try:
            position = float(args[-1])
        except ValueError:
            continue
        values = args[-2]
        hidden = next((key for key in ("opacity", "autoAlpha") if _object_number(values, key) == 0), None)
        if not hidden:
            continue
        target = json.dumps(json.loads(args[0]), separators=(",", ":"))
        if method == "set":
            kills.append((target, position))
            continue
        if re.search(r'\b(keyframes|repeat|yoyo)\s*:', values):
            continue
        duration = _object_number(values, "duration")
        stagger = _object_number(values, "stagger") or 0.0
        end = position + (.5 if duration is None else duration) + stagger * (_literal_targets(args[0]) - 1)
        exits.append((target, end, hidden))
    added = []
    for target, end, hidden in exits:
        near = [b for b in boundaries if abs(end - b) <= BOUNDARY_EPSILON]
        if not near:
            continue
        if any(t == target and any(abs(p - b) <= BOUNDARY_EPSILON for b in near) for t, p in kills):
            continue
        kills.append((target, end))
        added.append(f'tl.set({target},{{{hidden}:0}},{end:.4f});')
    return added


def motion_report(layout_spans, duration, graphics, kept, dropped, transitions, resolver, caption_y, stage_captions, warnings):
    """Mechanical balance checks; the encoded render still needs human review."""
    seconds = {"presenter": 0.0, "stage": 0.0, "split": 0.0, "full_broll": 0.0, "screen": 0.0}
    covered = 0.0
    for start, end, layout in layout_spans:
        seconds[layout] += max(0, end - start)
        covered += max(0, end - start)
    seconds["presenter"] += max(0, duration - covered)  # unlisted time shows the full presenter
    visible = seconds["presenter"] + seconds["stage"] + seconds["split"]
    report = {"layout_seconds": {k: round(v, 2) for k, v in seconds.items()},
              "presenter_visible_ratio": round(visible / duration, 3) if duration else 0,
              "presenter_full_frame_ratio": round(seconds["presenter"] / duration, 3) if duration else 0,
              "graphics_by_type": {}, "cta_styles": [], "sfx_kept": len(kept),
              "sfx_dropped": [{"kind": e["kind"], "at": e["at"], "reason": e["reason"]} for e in dropped],
              "transitions": transitions, "word_cues_resolved": len(resolver.used), "warnings": list(warnings)}
    ordered = sorted(graphics, key=lambda g: g["start"])
    for g in ordered:
        report["graphics_by_type"][g["type"]] = report["graphics_by_type"].get(g["type"], 0) + 1
        hold = g["end"] - g["start"]
        if g["type"] in COMPLEX_GRAPHICS and hold < 2.0:
            report["warnings"].append(f'{g["id"]}: {g["type"]} holds {hold:.2f}s; complex panels generally need 2-3s to read')
        x, y, w, h = g["box"]
        if (h is not None and y < caption_y + 7 and y + h > caption_y - 1 and g["type"] not in {"badge", "spotlight"}
                and not g.get("hides_captions")):
            report["warnings"].append(f'{g["id"]}: box {y:.0f}-{y + h:.0f}% may collide with spoken captions at {caption_y}%')
        for a, b, seam in stage_captions:
            if (h is not None and g["start"] < b and g["end"] > a and y < seam + 5 and y + h > seam + .5
                    and g["type"] not in {"badge", "spotlight"}):
                report["warnings"].append(f'{g["id"]}: box {y:.0f}-{y + h:.0f}% covers the stage caption at {seam:.1f}% '
                                          f'({max(a, g["start"]):.1f}-{min(b, g["end"]):.1f}s); shrink it or move it up')
                break
    for start, end, layout in layout_spans:
        if layout != "stage":
            continue
        covering = sorted((max(start, g["start"]), min(end, g["end"])) for g in graphics
                          if g["type"] not in {"headline", "badge"} and g["end"] > start and g["start"] < end)
        cursor, longest = start, 0.0
        for a, b in covering:
            longest = max(longest, a - cursor)
            cursor = max(cursor, b)
        longest = max(longest, end - cursor)
        if longest > 1.0:
            report["warnings"].append(f"stage at {start:.1f}-{end:.1f}s shows an empty stage for {longest:.1f}s; "
                                      "bring the diagram in earlier (slots) or cut to the presenter")
    run_type, run_length = None, 0
    for g in ordered:
        if g["type"] == run_type:
            run_length += 1
            if run_length == 3:
                report["warnings"].append(f'three {run_type} graphics in a row near {g["start"]:.1f}s; vary the treatment')
        else:
            run_type, run_length = g["type"], 1
    enters = [g["enter"] for g in ordered if g["type"] not in {"headline", "hero", "reveal", "particles", "cta"}]
    for i in range(len(enters) - 3):
        if len(set(enters[i:i + 4])) == 1:
            report["warnings"].append(f'four consecutive graphics share the "{enters[i]}" entrance; vary entrances')
            break
    if duration > 12 and report["presenter_visible_ratio"] < .7:
        report["warnings"].append(f'Brandon is visible for {report["presenter_visible_ratio"]:.0%} of the reel; he asked to stay visible behind most graphics')
    if duration > 12 and seconds["full_broll"] / duration > .3:
        report["warnings"].append("full-screen sections exceed 30% of the reel; reserve them for moments that need the whole frame")
    if duration > 15 and report["presenter_full_frame_ratio"] > .92 and len(graphics) < 3:
        report["warnings"].append("mostly uninterrupted talking head with few graphics; add emphasis for key spoken claims")
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command",choices=["build","render"])
    ap.add_argument("--spec")
    ap.add_argument("--project",required=True)
    ap.add_argument("--output")
    ap.add_argument("--quality",choices=["draft","standard","high"],default="standard")
    ap.add_argument("--workers",type=int,default=1)
    args=ap.parse_args()
    if args.command=="build":
        if not args.spec: ap.error("build requires --spec")
        print(json.dumps(build(args.spec,args.project),indent=2))
    else:
        if not args.output: ap.error("render requires --output")
        target=Path(args.output).resolve()
        if target.exists() and any(os.path.samefile(target, asset) for asset in (Path(args.project)/"assets").glob("*")):
            ap.error(f"{target} is a source file of this composition (assets are hardlinked); choose a new output path")
        command=["render",str(Path(args.project).resolve()),"--output",str(Path(args.output).resolve()),"--quality",args.quality,"--workers",str(args.workers),"--no-best-effort","--strict"]
        run_hyperframes(command)
        result=probe(Path(args.output))
        (Path(args.project)/"render-receipt.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps({"output":str(Path(args.output).resolve()),"duration":result["format"]["duration"],"bytes":Path(args.output).stat().st_size}))


if __name__=="__main__":
    main()
