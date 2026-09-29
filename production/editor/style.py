"""Brandon's house style: one spec (style_spec.json) read by every stage of the editor.

The builder (edit.py), design tokens (design.py), components, the sound kit, the
beat planner (plan_reel.py) and the acceptance review (review_reel.py) all read
their defaults from here, so changing the spec changes every future edit.

A timeline may override a few values under a top-level "style" object, e.g.
{"style": {"zones": {"caption": {"y": 70}}}}; unknown keys are rejected.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC_PATH = HERE / "style_spec.json"
SECTIONS = ("color", "type", "zones", "captions", "motion", "layout", "hook", "showpiece", "transitions",
            "sound", "forbidden", "variety")


@lru_cache(maxsize=1)
def _base():
    data = json.loads(SPEC_PATH.read_text())
    missing = [s for s in SECTIONS if s not in data]
    if missing:
        raise ValueError(f"style_spec.json is missing sections: {', '.join(missing)}")
    return data


def _kind(value):
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    return None


def _merge(base, extra, path=""):
    for key, value in extra.items():
        name = path + key
        if key not in base:
            raise ValueError(f"unknown style key {name!r}")
        current = base[key]
        if isinstance(current, dict):
            if not isinstance(value, dict):
                raise ValueError(f"style key {name!r} must be an object of overrides, not {value!r}")
            _merge(current, value, name + ".")
            continue
        # A value replaces one of the same kind; null only where the spec itself uses null
        # (a silent sound role), and a silent role may be given a sound name.
        wanted, given = _kind(current), _kind(value)
        if current is None:
            if value is not None and not isinstance(value, str):
                raise ValueError(f"style key {name!r} must be text or null, not {value!r}")
        elif value is None or wanted != given:
            raise ValueError(f"style key {name!r} must be {wanted}, not {value!r}")
        base[key] = value
    return base


def load(overrides=None):
    """The house style, optionally with a timeline's "style" overrides merged in."""
    spec = copy.deepcopy(_base())
    if overrides:
        if not isinstance(overrides, dict):
            raise ValueError("style overrides must be an object")
        _merge(spec, overrides)
    return spec


def design_defaults(spec=None):
    """Keys used by design.py (colors, fonts, feel)."""
    s = spec or _base()
    c, t = s["color"], s["type"]
    return {
        "accent": c["accent"], "accent_ink": c["accent_ink"], "text": c["text"], "text_2": c["text_2"],
        "muted": c["muted"], "negative": c["negative"], "warm": c["warm"], "canvas": c["canvas"],
        "panel": c["panel"], "panel_solid": c["panel_solid"], "line": c["line"],
        "card_light": c["card_light"], "card_light_ink": c["card_light_ink"],
        "display_font": t["display_font"], "serif_font": t["serif_font"], "caption_font": t["caption_font"],
        "mono_font": t["mono_font"], "feel": s["motion"]["feel"], "stage_backdrop": "dots",
    }


def caption_defaults(spec=None):
    s = spec or _base()
    c = dict(s["captions"])
    c["y"] = s["zones"]["caption"]["y"]
    c["font_px"] = s["type"]["caption_px"]
    return c


def sound_role(role, spec=None):
    """Sound kind mapped to a semantic role (popup, travel, section, reveal...); None means silent."""
    roles = (spec or _base())["sound"]["roles"]
    if role not in roles:
        raise ValueError(f"unknown sound role {role!r}; choose from {', '.join(sorted(roles))}")
    return roles[role]


def voice_offset(kind, spec=None):
    return (spec or _base())["sound"]["voice_offset_lu"].get(kind)


def zone(name, spec=None):
    return (spec or _base())["zones"][name]
