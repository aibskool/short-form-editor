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
from kallaway_motifs import stage_events  # noqa: E402
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


def _colors_in(html):
    return {f"#{match.group(1).lower()}" for match in re.finditer(r"#([0-9A-Fa-f]{6})(?![0-9A-Fa-fA-Z_])", html)}


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
        elif length < 0.4:
            errors.append(f"shots:{shot.get('id', index)}: {length:.2f}s is shorter than 0.4s")
        elif float(shot["start"]) >= 3.2 and index != len(shots) - 1 and not 1.15 <= length <= 5.05:
            warnings.append(f"shots:{shot.get('id', index)}: body shot is {length:.2f}s; expected about 2-5s")
        if index and abs(float(shot["start"]) - float(shots[index - 1]["end"])) > tolerance:
            errors.append(f"shots:{shot.get('id', index)}: gap or overlap at the layout cut")
        if layout == "split" and not shot.get("stage"):
            errors.append(f"shots:{shot.get('id', index)}: split shot has no graphic stage")
    if duration >= 6:
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
            if count > 4:
                errors.append(f"captions: a group has {count} words")
            elif count > 2:
                warnings.append(f"captions: a group has {count} words; the style is 1-2")
    elif int(captions.get("max_words", 2)) > 2:
        warnings.append("captions: max_words is above 2 and no explicit phrases were checked")
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
    policy = data.get("audio_policy") or {}
    if not music and not policy.get("user_opt_out"):
        errors.append("audio: music bed is missing and there is no opt-out")
    for track in music:
        envelope = track.get("envelope") or []
        if len(envelope) >= 2 and float(envelope[-1].get("v", 1)) == 0:
            span = float(envelope[-1]["t"]) - float(envelope[-2]["t"])
            if span > 0.2:
                errors.append("ending: music fades out instead of cutting on the last word")

    sfx = data.get("sfx") or []
    for shot in shots:
        if shot.get("layout") != "split" or not shot.get("stage"):
            continue
        for event in stage_events(shot["stage"].get("motif"), shot["start"], shot["end"], shot["stage"]):
            if not any(abs(float(item.get("at", -99)) - float(event["at"])) <= 0.12 for item in sfx):
                errors.append(f"sfx: no sound within 0.12s of {shot['stage'].get('motif')} at {event['at']}")
                break
    if shots and not sfx:
        errors.append("sfx: no sound effects were scheduled")

    cta = data.get("cta") or {}
    headers = data.get("headers") or []
    if not headers:
        errors.append("headers: no title header")
    elif float(headers[0].get("start", 1)) > 0.05:
        errors.append("hook: title header does not start on frame 1")
    keyword = str(cta.get("keyword") or "")
    closing = " ".join(str(header.get("text", "")) for header in headers).lower()
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
    else:
        warnings.append("brand: no built index.html was scanned for palette and fonts")

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
