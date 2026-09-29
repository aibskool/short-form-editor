"""Word-cued motion graphic components for Brandon's stage style.

Each component returns HTML markup plus GSAP timeline lines. Components are
authored on a 1080-px grid, positioned in frame percentages, and every visible
change can be anchored to a spoken word through ``cues.CueResolver``.
"""
import html
import json
import math
import re

from icons import icon_svg, ICON_NAMES
import style

ROLES = {"popup", "popup_soft", "travel", "section", "reveal", "tap", "type", "count", "strike", "highlight"}
# Kinds that components used to request directly now map to roles in the house style.
ROLE_OF_KIND = {"pop": "popup", "tick": "highlight", "tap": "tap", "draw": "highlight", "deny": "strike",
                "typing": "type", "ticker": "count", "paper": "travel", "thud": "reveal", "stamp": "reveal",
                "whoosh_short": "travel", "whoosh": "section"}
LANDING_ROLES = {"popup", "popup_soft", "tap"}
LANDING_DELAY = .07

REGIONS = {
    # x, y, w (percent of frame). Heights are content-driven unless h is set.
    "top": (6, 6.5, 88),
    "headline": (6, 5.5, 88),
    "stage": (5, 17, 90),
    "center": (8, 30, 84),
    "upper": (7, 13, 86),
    "left": (4, 26, 45),
    "right": (51, 26, 45),
    "upper_left": (5, 11, 52),
    "upper_right": (43, 11, 52),
    "lower": (6, 56, 88),
    "seam": (30, 58, 40),
}

ENTERS = {"pop", "rise", "mask", "slide_left", "slide_right", "drop", "fade", "blur", "tilt", "none"}
EXITS = {"fade", "fall", "rise", "slide_left", "slide_right", "scale", "blur", "none", "cut"}


def esc(value):
    return html.escape(str(value), quote=True)


def js(value):
    return json.dumps(value, separators=(",", ":"))


def num(value, label, low=None, high=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number") from None
    if not math.isfinite(result) or (low is not None and result < low) or (high is not None and result > high):
        raise ValueError(f"{label} must be between {low} and {high}")
    return result


class Ctx:
    """Shared build context handed to every component."""

    def __init__(self, px, design, feel, resolver, width, height, fps, duration, media, house=None):
        self.px, self.design, self.feel, self.resolver = px, design, feel, resolver
        self.width, self.height, self.fps, self.duration = width, height, fps, duration
        self.media = media
        self.house = house or style.load()  # the timeline's merged house style
        self.sfx_events = []
        self.report = []

    def t(self, value, label, after=None, strict=False):
        return self.resolver.frame(self.resolver.resolve(value, label, after, strict))

    def sound(self, kind, at, gain=None, source="", duration=None):
        """Queue a sound by semantic role ("popup", "travel", "section", "reveal", "tap",
        "type", "count", "strike", "highlight") or by kind. Older component kinds map to
        roles, and the house style spec decides the actual sound (or silence) per role:
        pop-ups get the bubble family, travel and sections quiet whooshes, reveals a
        restrained impact."""
        if not kind:
            return
        role = kind if kind in ROLES else ROLE_OF_KIND.get(kind)
        if role:
            kind = style.sound_role(role, self.house)
            if not kind:
                return
            if role in LANDING_ROLES:
                at = float(at) + LANDING_DELAY  # a pop lands when the graphic reaches full size
        event = {"kind": kind, "at": round(float(at), 4), "gain": gain, "source": source}
        if role:
            event["role"] = role
        if duration is not None:
            event["duration"] = duration
        self.sfx_events.append(event)


def words_markup(text, accent=(), accent_class="accent-c", serif_accent=False):
    """Wrap words in mask spans; accent matches whole words (case-insensitive)."""
    accent_set = {a.casefold().strip(".,!?;:\"'") for a in accent}
    parts = []
    for token in str(text).split():
        key = token.casefold().strip(".,!?;:\"'")
        klass = accent_class if key in accent_set else ""
        if key in accent_set and serif_accent:
            klass += " serif"
        parts.append(f'<span class="w"><span class="wi {klass.strip()}">{esc(token)}</span></span>')
    return " ".join(parts)


class Component:
    """Base: placement, clip timing, scrim, enter/exit/float choreography."""

    kind = "base"
    default_region = "center"
    default_enter = "pop"
    default_exit = "fade"
    default_sfx = "popup"

    def __init__(self, spec, index, ctx):
        self.g, self.ctx, self.index = spec, ctx, index
        self.id = esc(spec.get("id") or f"g{index}-{self.kind}")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", self.id):
            raise ValueError(f"graphic {index} id {self.id!r} must start with a letter and use only letters, digits, - or _")
        self.start = ctx.t(spec.get("start"), f"graphic {self.id} start", strict=True)
        # An end cue names the next spoken occurrence after the graphic starts.
        self.end = ctx.t(spec.get("end"), f"graphic {self.id} end", self.start + 1e-3)
        if ctx.duration < self.end <= ctx.duration + 1 / ctx.fps + 1e-6:
            self.end = ctx.duration  # frame snapping may round a cue at the final frame just past the end
        if not 0 <= self.start < self.end <= ctx.duration + 1e-6:
            raise ValueError(f"graphic {self.id} must start before it ends inside the output timeline "
                             f"({self.start:.2f}-{self.end:.2f} of {ctx.duration:.2f}s)")
        region = spec.get("region", self.default_region)
        if region not in REGIONS:
            raise ValueError(f"graphic {self.id} region must be one of {', '.join(REGIONS)}")
        rx, ry, rw = REGIONS[region]
        self.x = num(spec.get("x", rx), f"{self.id} x", 0, 100)
        self.y = num(spec.get("y", ry), f"{self.id} y", 0, 100)
        self.w = num(spec.get("w", spec.get("width", rw)), f"{self.id} w", 1, 100)
        if self.x + self.w > 100.001:
            raise ValueError(f"graphic {self.id} exceeds the frame width (x + w > 100)")
        self.h = spec.get("h")
        if self.h is not None:
            self.h = num(self.h, f"{self.id} h", 1, 100)
            if self.y + self.h > 100.001:
                raise ValueError(f"graphic {self.id} exceeds the frame height (y + h > 100)")
        self.enter = spec.get("enter", self.default_enter)
        self.exit = spec.get("exit", self.default_exit)
        if self.enter not in ENTERS:
            raise ValueError(f"graphic {self.id} enter must be one of {', '.join(sorted(ENTERS))}")
        if self.exit not in EXITS:
            raise ValueError(f"graphic {self.id} exit must be one of {', '.join(sorted(EXITS))}")
        self.depth = spec.get("depth", "front")
        if self.depth not in {"front", "behind"}:
            raise ValueError(f"graphic {self.id} depth must be front or behind")
        self.anims = []
        self.body = f"{self.id}-body"

    # --- helpers -----------------------------------------------------------
    @property
    def px(self):
        return self.ctx.px

    @property
    def zoom(self):
        return num(self.g.get("scale", 1), f"{self.id} scale", .5, 2.5)

    @property
    def feel(self):
        return self.ctx.feel

    def cue(self, value, label, default=None, inside=True):
        if value is None:
            if default is None:
                raise ValueError(f"{self.id} {label} is required")
            return min(max(default, self.start), max(self.start, self.end - .1))
        seconds = self.ctx.t(value, f"{self.id} {label}", self.start)
        if inside and not self.start - 1e-6 <= seconds < self.end:
            raise ValueError(f"{self.id} {label} at {seconds:.2f}s falls outside its graphic "
                             f"({self.start:.2f}-{self.end:.2f}s)")
        return seconds

    def a(self, line):
        self.anims.append(line)

    def silent(self):
        """`"sfx": null` (or false) silences every sound this graphic makes."""
        return "sfx" in self.g and not self.g["sfx"]

    def sound(self, kind, at, gain=None, duration=None):
        if kind and not self.silent():
            self.ctx.sound(kind, at, gain, self.id, duration)

    def sfx(self, at, kind=None, gain=None):
        choice = self.g.get("sfx", self.default_sfx) if kind is None else kind
        self.sound(choice, at, gain)

    def hold(self):
        return self.end - self.start

    # --- framing -----------------------------------------------------------
    def wrap(self, inner, extra_class="", inner_style="", timed=True):
        """Outer box for a graphic. timed=False leaves the box out of HyperFrames' clip
        timing and shows it with GSAP instead; a <video> that carries its own data-start
        must not sit inside another timed element (lint: video_nested_in_timed_element)."""
        style = f"left:{self.x:.3f}%;top:{self.y:.3f}%;width:{self.w:.3f}%;"
        if self.h is not None:
            style += f"height:{self.h:.3f}%;"
        zoom = num(self.g.get("scale", 1), f"{self.id} scale", .5, 2.5)
        body_zoom = f"zoom:{zoom:.3f};" if abs(zoom - 1) > 1e-6 else ""
        scrim = self.g.get("scrim", False)
        scrim_markup = ""
        if scrim:
            klass = {"band": "mg-scrim band", "plate": "mg-scrim plate"}.get(scrim, "mg-scrim")
            scrim_markup = f'<div id="{self.id}-scrim" class="{klass}" data-layout-allow-overflow></div>'
            self.a(f'tl.fromTo("#{self.id}-scrim",{{opacity:0}},{{opacity:1,duration:{min(.35, self.hold() / 3):.3f},ease:"power1.out"}},{self.start:.4f});')
            self.a(f'tl.to("#{self.id}-scrim",{{opacity:0,duration:{min(.3, self.hold() / 3):.3f},ease:"power1.in"}},{max(self.start, self.end - .3):.4f});')
            self.a(f'tl.set("#{self.id}-scrim",{{opacity:0}},{self.end:.4f});')
        depth = " depth-behind" if self.depth == "behind" else ""
        if timed:
            timing = f'class="mg mg-{self.kind} clip{depth} {extra_class}" data-start="{self.start:.4f}" data-duration="{self.end - self.start:.4f}"'
        else:
            timing = f'class="mg mg-{self.kind}{depth} {extra_class}"'
            style += "visibility:hidden;opacity:0;"
            self.a(f'tl.set("#{self.id}",{{autoAlpha:1}},{self.start:.4f});')
            if self.end < self.ctx.duration - 1e-3:
                self.a(f'tl.set("#{self.id}",{{autoAlpha:0}},{self.end:.4f});')
        return (f'<div id="{self.id}" {timing} data-beat="{esc(self.g.get("beat", ""))}" style="{style}">'
                f'{scrim_markup}<div id="{self.id}-float" class="mg-float" style="position:relative;width:100%;height:100%">'
                f'<div id="{self.body}" class="mg-body" style="position:relative;width:100%;height:100%;{body_zoom}{inner_style}">{inner}</div></div></div>')

    def choreograph(self, enter_at=None, enter_target=None):
        """Standard entrance, idle float and exit for the whole body."""
        f = self.feel
        target = enter_target or f"#{self.body}"
        at = self.start if enter_at is None else enter_at
        dur = min(f["in"], max(.18, self.hold() * .4))
        k = self.px.n(1)
        enter = self.enter
        if enter == "pop":
            self.a(f'tl.fromTo("{target}",{{opacity:0,scale:.84,y:{24 * k:.1f}}},{{opacity:1,scale:1,y:0,duration:{dur:.3f},ease:"{f["pop"]}"}},{at:.4f});')
        elif enter == "rise":
            self.a(f'tl.fromTo("{target}",{{opacity:0,y:{46 * k:.1f},filter:"blur(8px)"}},{{opacity:1,y:0,filter:"blur(0px)",duration:{dur:.3f},ease:"{f["enter"]}"}},{at:.4f});')
        elif enter == "drop":
            self.a(f'tl.fromTo("{target}",{{opacity:0,y:{-60 * k:.1f},scale:.96}},{{opacity:1,y:0,scale:1,duration:{dur:.3f},ease:"{f["pop"]}"}},{at:.4f});')
        elif enter in {"slide_left", "slide_right"}:
            sign = 1 if enter == "slide_left" else -1  # slide_left enters from the right, moving left
            self.a(f'tl.fromTo("{target}",{{opacity:0,x:{sign * 140 * k:.1f},filter:"blur(10px)"}},{{opacity:1,x:0,filter:"blur(0px)",duration:{dur:.3f},ease:"{f["enter"]}"}},{at:.4f});')
        elif enter == "fade":
            self.a(f'tl.fromTo("{target}",{{opacity:0}},{{opacity:1,duration:{dur:.3f},ease:"power1.out"}},{at:.4f});')
        elif enter == "blur":
            self.a(f'tl.fromTo("{target}",{{opacity:0,scale:1.08,filter:"blur(18px)"}},{{opacity:1,scale:1,filter:"blur(0px)",duration:{dur:.3f},ease:"{f["enter"]}"}},{at:.4f});')
        elif enter == "tilt":
            self.a(f'tl.fromTo("{target}",{{opacity:0,rotationX:28,rotationY:-18,y:{80 * k:.1f},scale:.9,transformPerspective:{1400 * k:.0f}}},{{opacity:1,rotationX:0,rotationY:0,y:0,scale:1,duration:{max(dur, .55):.3f},ease:"{f["enter"]}"}},{at:.4f});')
        elif enter == "mask":
            self.a(f'tl.fromTo("{target}",{{clipPath:"inset(0% 100% 0% 0%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:{dur:.3f},ease:"{f["move"]}"}},{at:.4f});')
        if self.g.get("float", True) and self.hold() > 1.2:
            drift = 10 * k
            self.a(f'tl.fromTo("#{self.id}-float",{{y:0,scale:1}},{{y:{-drift:.1f},scale:1.018,duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.exit_anim(target)

    def exit_anim(self, target=None):
        target = target or f"#{self.body}"
        f = self.feel
        dur = min(f["out"], max(.12, self.hold() * .25))
        at = max(self.start + .05, self.end - dur)
        k = self.px.n(1)
        exit_kind = self.exit
        if exit_kind in {"none", "cut"}:
            return
        if self.end >= self.ctx.duration - 1.5 / self.ctx.fps:
            return  # held to the last frame (a closing CTA); never fade out on the final frames
        vars_ = {"fade": f'opacity:0',
                 "fall": f'opacity:0,y:{50 * k:.1f}',
                 "rise": f'opacity:0,y:{-50 * k:.1f}',
                 "slide_left": f'opacity:0,x:{-160 * k:.1f},filter:"blur(8px)"',
                 "slide_right": f'opacity:0,x:{160 * k:.1f},filter:"blur(8px)"',
                 "scale": 'opacity:0,scale:.82',
                 "blur": 'opacity:0,scale:1.06,filter:"blur(14px)"'}[exit_kind]
        self.a(f'tl.to("{target}",{{{vars_},duration:{dur:.3f},ease:"{f["exit"]}"}},{at:.4f});')
        # Hard kill at the clip boundary so non-linear seeks never show stale state.
        self.a(f'tl.set("{target}",{{opacity:0}},{self.end:.4f});')

    def render(self):
        raise NotImplementedError

    # Hero text repeats the spoken words in large type, so the short captions step aside
    # while it is up ("captions": "keep" or "hide" overrides the default per graphic).
    caption_default = "keep"

    def hides_captions(self):
        choice = self.g.get("captions", self.caption_default)
        if choice not in {"keep", "hide"}:
            raise ValueError(f"{self.id} captions must be keep or hide")
        return choice == "hide"

    showpiece_variants = ()

    def meta_box(self):
        """Frame-percent box the review uses for collisions (x, y, w, h or None)."""
        return [self.x, self.y, self.w, self.h]

    def showpiece(self):
        """True for art-directed moments the acceptance review counts (hook, reveal, payoff)."""
        return bool(self.g.get("showpiece")) or self.g.get("variant") in self.showpiece_variants


# ---------------------------------------------------------------------------
class Headline(Component):
    """Section headline: white display type with one contrasted accent phrase."""
    kind = "headline"
    default_region = "headline"
    default_enter = "mask"
    default_exit = "rise"
    default_sfx = "whoosh_short"

    def render(self):
        g = self.g
        lines = g.get("lines") or [g.get("text", "")]
        if not any(str(line).strip() for line in lines):
            raise ValueError(f"{self.id} needs text or lines")
        accent = str(g.get("accent", "")).strip()
        style = g.get("accent_style", "box")
        if style not in {"box", "serif", "underline", "color"}:
            raise ValueError(f"{self.id} accent_style must be box, serif, underline or color")
        size = num(g.get("size", 84), f"{self.id} size", 20, 220)
        align = g.get("align", "center")
        if align not in {"left", "center", "right"}:
            raise ValueError(f"{self.id} align must be left, center or right")
        accent_tokens = accent.split()
        full = " ".join(str(line) for line in lines)
        if accent and accent.casefold() not in full.casefold():
            raise ValueError(f"{self.id} accent {accent!r} must appear in the headline text")
        rows = []
        word_ids = []
        box_id = None
        for li, line in enumerate(lines):
            tokens = str(line).split()
            spans = []
            i = 0
            while i < len(tokens):
                window = tokens[i:i + len(accent_tokens)]
                is_accent = bool(accent_tokens) and [t.casefold().strip(".,!?:;") for t in window] == [t.casefold().strip(".,!?:;") for t in accent_tokens]
                if is_accent:
                    inner = []
                    for token in window:
                        wid = f"{self.id}-w{len(word_ids)}"
                        word_ids.append(wid)
                        klass = {"box": "hl-on-box", "serif": "serif accent-c", "underline": "", "color": "accent-c"}[style]
                        inner.append(f'<span class="w"><span id="{wid}" class="wi {klass}">{esc(token)}</span></span>')
                    box_id = f"{self.id}-accent"
                    if style == "box":
                        spans.append(f'<span class="hl-box"><i id="{box_id}" class="hl-box-bg"></i>{" ".join(inner)}</span>')
                    elif style == "underline":
                        spans.append(f'<span class="hl-ul">{" ".join(inner)}<svg id="{box_id}" class="hl-ul-svg" viewBox="0 0 100 12" preserveAspectRatio="none"><path vector-effect="non-scaling-stroke" d="M2 8 C 30 3, 62 11, 98 5"/></svg></span>')
                    else:
                        spans.append(" ".join(inner))
                    i += len(accent_tokens)
                else:
                    wid = f"{self.id}-w{len(word_ids)}"
                    word_ids.append(wid)
                    spans.append(f'<span class="w"><span id="{wid}" class="wi">{esc(tokens[i])}</span></span>')
                    i += 1
            rows.append(f'<div class="hl-line">{" ".join(spans)}</div>')
        if accent and box_id is None:
            raise ValueError(f"{self.id} accent {accent!r} must sit within one line; move the line break or shorten the accent")
        # Display leading is intentionally tight; the layout inspector should not flag it.
        inner = f'<div class="hl" data-layout-allow-overlap style="font-size:{self.px(size)};text-align:{align}">{"".join(rows)}</div>'
        markup = self.wrap(inner)
        f = self.feel
        at = self.start
        k = self.px.n(1)
        if self.enter == "mask":
            self.a(f'tl.fromTo({js(["#" + w for w in word_ids])},{{yPercent:112,rotation:4}},{{yPercent:0,rotation:0,duration:{max(.5, f["in"]):.3f},stagger:{f["stagger"]:.3f},ease:"{f["enter"]}"}},{at:.4f});')
        else:
            self.choreograph()
        if box_id and style == "box":
            self.a(f'tl.fromTo("#{box_id}",{{scaleX:0}},{{scaleX:1,duration:.42,ease:"{f["move"]}"}},{at + .16:.4f});')
        elif box_id and style == "underline":
            self.a(f'tl.fromTo("#{box_id}",{{clipPath:"inset(-150% 100% -150% -4%)"}},{{clipPath:"inset(-150% -4% -150% -4%)",duration:.5,ease:"power2.inOut"}},{at + .3:.4f});')
        elif box_id and style == "serif":
            self.a(f'tl.fromTo("#{self.id} .serif",{{filter:"blur(6px)",opacity:.2}},{{filter:"blur(0px)",opacity:1,duration:.5,ease:"power2.out"}},{at + .12:.4f});')
        if self.enter == "mask":
            if self.hold() > 1.2 and self.g.get("float", True):
                self.a(f'tl.fromTo("#{self.id}-float",{{scale:1}},{{scale:1.025,duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
            if self.exit == "rise":
                dur = min(.34, self.hold() * .25)
                self.a(f'tl.to({js(["#" + w for w in word_ids])},{{yPercent:-112,duration:{dur:.3f},stagger:{f["stagger"] * .5:.3f},ease:"{f["exit"]}"}},{max(at + .1, self.end - dur - .05):.4f});')
                self.a(f'tl.set("#{self.body}",{{opacity:0}},{self.end:.4f});')
                if box_id and style == "box":
                    self.a(f'tl.to("#{box_id}",{{scaleX:0,transformOrigin:"100% 50%",duration:{dur:.3f},ease:"{f["exit"]}"}},{max(at + .1, self.end - dur - .05):.4f});')
            else:
                self.exit_anim()
        self.sfx(at)
        return markup, self.anims


class Statement(Component):
    """Big kinetic words; optional reveal synced to the spoken words."""
    kind = "statement"
    default_region = "upper"
    default_enter = "rise"
    default_exit = "blur"
    default_sfx = None
    caption_default = "hide"

    def render(self):
        g = self.g
        text = str(g.get("text", "")).strip()
        if not text:
            raise ValueError(f"{self.id} needs text")
        size = num(g.get("size", 116), f"{self.id} size", 20, 260)
        align = g.get("align", "left")
        accent = g.get("accent_words", [])
        serif = g.get("accent_style", "color") == "serif"
        tokens = text.split()
        spans = []
        ids = []
        accent_set = {a.casefold().strip(".,!?;:\"'") for a in accent}
        accent_ids = []
        for i, token in enumerate(tokens):
            wid = f"{self.id}-w{i}"
            ids.append(wid)
            key = token.casefold().strip(".,!?;:\"'")
            klass = "accent-c" + (" serif" if serif else "") if key in accent_set else ""
            if key in accent_set:
                accent_ids.append(wid)
            spans.append(f'<span class="w"><span id="{wid}" class="wi {klass}">{esc(token)}</span></span>')
        inner = f'<div class="st" data-layout-allow-overlap style="font-size:{self.px(size)};text-align:{align}">{" ".join(spans)}</div>'
        markup = self.wrap(inner)
        f = self.feel
        k = self.px.n(1)
        times = self.word_times(tokens) if g.get("sync") == "spoken" else None
        reveal = g.get("reveal", "rise")
        if reveal not in {"rise", "pop", "fade"}:
            raise ValueError(f"{self.id} reveal must be rise, pop or fade")
        for i, wid in enumerate(ids):
            at = times[i] if times else self.start + i * f["stagger"] * 1.4
            if reveal == "rise":
                self.a(f'tl.fromTo("#{wid}",{{yPercent:105,opacity:0,filter:"blur(6px)"}},{{yPercent:0,opacity:1,filter:"blur(0px)",duration:.38,ease:"{f["enter"]}"}},{at:.4f});')
            elif reveal == "pop":
                self.a(f'tl.fromTo("#{wid}",{{scale:.4,opacity:0}},{{scale:1,opacity:1,duration:.34,ease:"{f["pop"]}"}},{at:.4f});')
            else:
                self.a(f'tl.fromTo("#{wid}",{{opacity:0}},{{opacity:1,duration:.25,ease:"power1.out"}},{at:.4f});')
        for wid in accent_ids:
            at = times[ids.index(wid)] if times else self.start + .2
            self.a(f'tl.fromTo("#{wid}",{{textShadow:"0 0 0px rgba(73,207,38,0)"}},{{textShadow:"0 0 {28 * k:.0f}px rgba(73,207,38,.55)",duration:.35,ease:"power2.out",immediateRender:false}},{at + .08:.4f});')
            if g.get("sfx", "pop"):
                self.sound(g.get("sfx", "pop"), at, None)
        if self.hold() > 1.2 and g.get("float", True):
            self.a(f'tl.fromTo("#{self.id}-float",{{scale:1}},{{scale:1.03,duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.exit_anim()
        return markup, self.anims

    def word_times(self, tokens):
        """Match the statement's tokens to the transcript from its start cue onward."""
        from cues import normalize
        words = self.ctx.resolver.words
        spoken = []
        for word in words:
            if word["end"] > self.start - .05:
                spoken.append(word)
        times, cursor = [], 0
        for token in tokens:
            wanted = normalize(token)
            found = None
            for j in range(cursor, min(len(spoken), cursor + 8)):
                if normalize(spoken[j]["word"]) == wanted:
                    found = j
                    break
            if found is None:
                # Unspoken tokens (symbols, numbers written differently) follow the previous word.
                times.append(times[-1] + .06 if times else self.start)
            else:
                times.append(max(self.start, self.ctx.resolver.frame(spoken[found]["start"])))
                cursor = found + 1
        return [min(t, self.end - .2) for t in times]


class Card(Component):
    kind = "card"
    default_region = "right"
    default_enter = "pop"

    def render(self):
        g = self.g
        variant = g.get("variant", "glass")
        if variant not in {"glass", "solid", "accent", "outline"}:
            raise ValueError(f"{self.id} variant must be glass, solid, accent or outline")
        icon = g.get("icon")
        parts = []
        if icon:
            if icon not in ICON_NAMES:
                raise ValueError(f"{self.id} icon {icon!r} is unknown")
            parts.append(f'<div id="{self.id}-icon" class="cd-icon">{icon_svg(icon)}</div>')
        if g.get("image"):
            parts.append(f'<div id="{self.id}-img" class="cd-img"><img src="{esc(self.ctx.media(g["image"]))}" style="object-position:{esc(g.get("image_position", "50% 50%"))}"></div>')
        text_parts = []
        if g.get("kicker"):
            text_parts.append(f'<div class="cd-kicker">{esc(g["kicker"])}</div>')
        if g.get("title"):
            text_parts.append(f'<div class="cd-title">{words_markup(g["title"], g.get("accent_words", []))}</div>')
        if g.get("value"):
            text_parts.append(f'<div id="{self.id}-value" class="cd-value">{esc(g["value"])}</div>')
        if g.get("body"):
            text_parts.append(f'<div class="cd-text">{esc(g["body"])}</div>')
        if not text_parts and not g.get("image"):
            raise ValueError(f"{self.id} card needs a title, value, body or image")
        parts.append(f'<div class="cd-copy">{"".join(text_parts)}</div>')
        layout = g.get("layout", "row" if icon and not g.get("image") else "column")
        inner = f'<div class="cd cd-{variant} cd-{layout} {"glass" if variant == "glass" else ""}">{"".join(parts)}</div>'
        markup = self.wrap(inner)
        self.choreograph()
        f = self.feel
        if icon:
            self.a(f'tl.fromTo("#{self.id}-icon",{{scale:0,rotation:-35}},{{scale:1,rotation:0,duration:.5,ease:"{f["spring"]}"}},{self.start + .12:.4f});')
        self.a(f'tl.fromTo("#{self.id} .cd-copy > *",{{opacity:0,y:{self.px.n(18):.1f}}},{{opacity:1,y:0,duration:.34,stagger:.06,ease:"{f["enter"]}"}},{self.start + .1:.4f});')
        for j, change in enumerate(g.get("changes", [])):
            at = self.cue(change.get("at"), f"change {j}")
            if "value" in change:
                # Swap text through a quick scale blink; textContent is set by a zero-length tween.
                self.a(f'tl.to("#{self.id}-value",{{scale:.6,opacity:0,duration:.1,ease:"power2.in"}},{at - .1:.4f});')
                self.a(f'tl.set("#{self.id}-value",{{textContent:{js(str(change["value"]))}}},{at:.4f});')
                self.a(f'tl.to("#{self.id}-value",{{scale:1,opacity:1,duration:.35,ease:"{f["pop"]}"}},{at:.4f});')
            state = change.get("state")
            if state == "win":
                self.a(f'tl.to("#{self.id} .cd",{{borderColor:"{self.ctx.design["accent"]}",boxShadow:"0 0 {self.px.n(70):.0f}px rgba(73,207,38,.38)",duration:.35,ease:"power2.out"}},{at:.4f});')
            elif state == "lose":
                self.a(f'tl.to("#{self.id} .cd",{{opacity:.35,filter:"grayscale(1)",duration:.35,ease:"power2.out"}},{at:.4f});')
            elif state is not None:
                raise ValueError(f"{self.id} change state must be win or lose")
            self.sound(change.get("sfx", "tick"), at, None)
        self.sfx(self.start)
        return markup, self.anims


def format_number(value, decimals, compact, prefix, suffix):
    if compact:
        for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs(value) >= size:
                return f"{prefix}{value / size:.{decimals}f}{unit}{suffix}"
    return f"{prefix}{value:,.{decimals}f}{suffix}"


class Stat(Component):
    kind = "stat"
    default_region = "upper"
    default_enter = "pop"

    def render(self):
        g = self.g
        value = num(g.get("value"), f"{self.id} value")
        start_value = num(g.get("from", 0), f"{self.id} from")
        decimals = int(g.get("decimals", 0))
        compact = bool(g.get("compact", False))
        prefix, suffix = str(g.get("prefix", "")), str(g.get("suffix", ""))
        size = num(g.get("size", 190), f"{self.id} size", 30, 420)
        count_at = self.cue(g.get("count_at"), "count_at", self.start + .12)
        count_duration = num(g.get("count_duration", 1.0), f"{self.id} count_duration", .1, 6)
        final = format_number(value, decimals, compact, prefix, suffix)
        align = g.get("align", "center")
        label = g.get("label", "")
        pill = g.get("pill")
        rows = []
        if pill:
            rows.append(f'<div id="{self.id}-pill" class="stt-pill">{esc(pill)}</div>')
        first = format_number(start_value, decimals, compact, prefix, suffix)
        rows.append(f'<div id="{self.id}-num" class="stt-num" style="font-size:{self.px(size)}">{esc(first)}</div>')
        if label:
            rows.append(f'<div id="{self.id}-label" class="stt-label">{words_markup(label, g.get("accent_words", []))}</div>')
        spark = g.get("sparkline")
        if spark:
            pts = [num(v, f"{self.id} sparkline") for v in spark]
            lo, hi = min(pts), max(pts)
            span = hi - lo or 1
            d = " ".join(f"{'M' if i == 0 else 'L'}{i * 100 / (len(pts) - 1):.2f} {28 - (p - lo) / span * 24:.2f}" for i, p in enumerate(pts))
            rows.append(f'<svg id="{self.id}-spark" class="stt-spark" viewBox="0 0 100 30" preserveAspectRatio="none"><path vector-effect="non-scaling-stroke" d="{d}"/></svg>')
        inner = f'<div class="stt" style="text-align:{align}">{"".join(rows)}</div>'
        markup = self.wrap(inner)
        self.choreograph()
        var = "v_" + self.id.replace("-", "_") + "_n"
        self.a(f'const {var}={{v:{start_value}}};tl.fromTo({var},{{v:{start_value}}},{{v:{value},duration:{count_duration:.3f},ease:"expo.out",onUpdate:()=>{{document.getElementById("{self.id}-num").textContent=__fmt({var}.v,{decimals},{str(compact).lower()},{js(prefix)},{js(suffix)});}}}},{count_at:.4f});')
        self.a(f'tl.fromTo("#{self.id}-num",{{textShadow:"0 0 0px rgba(73,207,38,0)"}},{{textShadow:"0 0 {self.px.n(46):.0f}px rgba(73,207,38,.45)",duration:.5,ease:"power2.out",immediateRender:false}},{count_at + count_duration * .6:.4f});')
        if spark:
            self.a(f'tl.fromTo("#{self.id}-spark",{{clipPath:"inset(-150% 100% -150% -4%)"}},{{clipPath:"inset(-150% -4% -150% -4%)",duration:{count_duration:.3f},ease:"power2.inOut"}},{count_at:.4f});')
        if pill:
            self.a(f'tl.fromTo("#{self.id}-pill",{{scale:0}},{{scale:1,duration:.45,ease:"{self.feel["spring"]}"}},{self.start + .15:.4f});')
        self.sfx(self.start)
        if g.get("tick_sfx", True):
            self.sound("ticker", count_at, None, duration=round(count_duration * .85, 3))
        return markup, self.anims


class Flow(Component):
    """Nodes joined by drawn connectors with travelling pulses; the core diagram."""
    kind = "flow"
    default_region = "stage"
    default_enter = "none"
    default_sfx = "popup"

    LAYOUTS = {"row", "column", "triangle", "hub", "custom", "zigzag"}

    def render(self):
        g = self.g
        nodes = g.get("nodes", [])
        if not 1 <= len(nodes) <= 9:
            raise ValueError(f"{self.id} needs one to nine nodes")
        ids = [str(n.get("id", i)) for i, n in enumerate(nodes)]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.id} node ids must be unique")
        layout = g.get("layout", "row")
        if layout not in self.LAYOUTS:
            raise ValueError(f"{self.id} layout must be one of {', '.join(sorted(self.LAYOUTS))}")
        height = self.h if self.h is not None else num(g.get("box_h", 34), f"{self.id} box_h", 5, 90)
        if self.h is None:
            self.h = height
        box_w_px = self.ctx.width * self.w / 100 / self.zoom
        box_h_px = self.ctx.height * height / 100 / self.zoom
        positions = self.positions(layout, len(nodes), nodes, box_w_px, box_h_px)
        node_size = num(g.get("node_size", 190), f"{self.id} node_size", 60, 400)
        ghost = g.get("slots", True)
        k = self.px.n(1)
        markup_nodes, svg_paths, anims_after = [], [], []
        f = self.feel
        node_at = {}
        for i, node in enumerate(nodes):
            nid = f"{self.id}-n{i}"
            at = self.cue(node.get("at"), f"node {ids[i]} at", self.start + .1 + i * .18)
            node_at[ids[i]] = at
            cx, cy = positions[i]
            icon = node.get("icon")
            image = node.get("image")
            accent = " fl-accent" if node.get("accent") else ""
            visual = ""
            if image:
                visual = f'<div class="fl-img fl-box"><img src="{esc(self.ctx.media(image))}"></div>'
            elif icon:
                if icon not in ICON_NAMES:
                    raise ValueError(f"{self.id} node {ids[i]} icon {icon!r} is unknown")
                visual = f'<div class="fl-icon fl-box">{icon_svg(icon)}</div>'
            label = f'<div class="fl-label">{esc(node.get("label", ""))}</div>' if node.get("label") else ""
            sub = f'<div class="fl-sub">{esc(node.get("sub", ""))}</div>' if node.get("sub") else ""
            style = node.get("style", "tile" if visual else "pill")
            if style not in {"tile", "pill", "card"}:
                raise ValueError(f"{self.id} node style must be tile, pill or card")
            size = num(node.get("size", node_size), f"{self.id} node size", 40, 500)
            slot = ""
            if ghost and at > self.start + .45:
                slot = f'<div id="{nid}-slot" class="fl-slot fl-slot-{style}"></div>'
                self.a(f'tl.fromTo("#{nid}-slot",{{opacity:0,scale:.8}},{{opacity:1,scale:1,duration:.4,ease:"{f["enter"]}"}},{self.start + .08 + i * .07:.4f});')
                self.a(f'tl.to("#{nid}-slot",{{opacity:0,scale:1.25,duration:.3,ease:"power2.out"}},{at:.4f});')
            markup_nodes.append(
                f'<div id="{nid}" class="fl-node fl-{style}{accent}" style="left:{cx:.1f}px;top:{cy:.1f}px;--ns:{size * k:.1f}px">{slot}'
                f'<div id="{nid}-in" class="fl-node-in{"" if visual else " fl-box"}">{visual}<div class="fl-text">{label}{sub}</div></div></div>')
            self.a(f'tl.fromTo("#{nid}-in",{{opacity:0,scale:.55,y:{20 * k:.1f}}},{{opacity:1,scale:1,y:0,duration:.5,ease:"{f["spring"]}"}},{at:.4f});')
            self.sound(node.get("sfx", g.get("sfx", "pop")), at, None)
            if node.get("dim_at") is not None:
                dim = self.cue(node["dim_at"], f"node {ids[i]} dim_at")
                self.a(f'tl.to("#{nid}-in",{{opacity:.28,filter:"grayscale(1)",duration:.3,ease:"power2.out"}},{dim:.4f});')
            if node.get("win_at") is not None:
                win = self.cue(node["win_at"], f"node {ids[i]} win_at")
                self.a(f'tl.to("#{nid} .fl-box",{{borderColor:"{self.ctx.design["accent"]}",color:"{self.ctx.design["accent"]}",boxShadow:"0 0 {48 * k:.0f}px rgba(73,207,38,.5)",duration:.3,ease:"power2.out"}},{win:.4f});')
                self.a(f'tl.fromTo("#{nid}-in",{{scale:1}},{{scale:1.12,duration:.18,yoyo:true,repeat:1,ease:"power2.out",immediateRender:false}},{win:.4f});')
                self.sound(node.get("win_sfx", "pop"), win, None)
        for j, link in enumerate(g.get("links", [])):
            a_id, b_id = str(link.get("from")), str(link.get("to"))
            if a_id not in ids or b_id not in ids:
                raise ValueError(f"{self.id} link {j} must join existing node ids")
            (x1, y1), (x2, y2) = positions[ids.index(a_id)], positions[ids.index(b_id)]
            # Trim the line so it meets node edges instead of centres.
            dx, dy = x2 - x1, y2 - y1
            dist = math.hypot(dx, dy) or 1
            trim = node_size * k * .62
            if dist <= 2 * trim + 4:
                trim = max(0, dist / 2 - 6)
            sx, sy = x1 + dx / dist * trim, y1 + dy / dist * trim
            ex, ey = x2 - dx / dist * trim, y2 - dy / dist * trim
            bend = float(link.get("bend", 0))
            mx, my = (sx + ex) / 2 - dy / dist * bend * dist, (sy + ey) / 2 + dx / dist * bend * dist
            d = f"M{sx:.1f} {sy:.1f} Q{mx:.1f} {my:.1f} {ex:.1f} {ey:.1f}"
            lid = f"{self.id}-l{j}"
            dashed = link.get("style", "dashed") == "dashed"
            at = self.cue(link.get("at"), f"link {j} at", max(node_at[a_id], node_at[b_id]) + .15)
            stroke = "var(--accent)" if link.get("accent", True) else "rgba(255,255,255,.55)"
            if ghost:
                svg_paths.append(f'<path d="{d}" class="fl-guide" style="stroke-width:{3 * k:.1f}px;stroke-dasharray:{2 * k:.1f} {12 * k:.1f}"/>')
            svg_paths.append(
                f'<mask id="{lid}-m" maskUnits="userSpaceOnUse"><path id="{lid}-mp" d="{d}" stroke="#fff" stroke-width="{12 * k:.1f}" fill="none" stroke-linecap="round"/></mask>'
                f'<path d="{d}" class="fl-link{" dashed" if dashed else ""}" stroke="{stroke}" style="stroke-width:{4 * k:.1f}px;{f"stroke-dasharray:{10 * k:.1f} {10 * k:.1f};" if dashed else ""}" mask="url(#{lid}-m)"/>'
                f'<circle id="{lid}-dot" r="{7 * k:.1f}" class="fl-dot" cx="0" cy="0" style="opacity:0"/>'
                f'<path id="{lid}-path" d="{d}" fill="none" stroke="none"/>')
            draw = num(link.get("draw", .55), f"{self.id} link draw", .1, 3)
            self.a(f'tl.fromTo("#{lid}-mp",{{drawSVG:"0%"}},{{drawSVG:"100%",duration:{draw:.3f},ease:"power2.inOut"}},{at:.4f});')
            if link.get("pulse", True):
                self.a(f'tl.set("#{lid}-dot",{{opacity:1}},{at + draw * .6:.4f});')
                self.a(f'tl.fromTo("#{lid}-dot",{{motionPath:{{path:"#{lid}-path",align:"#{lid}-path",alignOrigin:[.5,.5],start:0,end:0}}}},{{motionPath:{{path:"#{lid}-path",align:"#{lid}-path",alignOrigin:[.5,.5],start:0,end:1}},duration:{max(.5, draw * 1.4):.3f},ease:"power1.inOut",immediateRender:false}},{at + draw * .6:.4f});')
                self.a(f'tl.to("#{lid}-dot",{{opacity:0,duration:.15}},{at + draw * .6 + max(.5, draw * 1.4) - .12:.4f});')
            if link.get("label"):
                lx, ly = (sx + 2 * mx + ex) / 4, (sy + 2 * my + ey) / 4
                markup_nodes.append(f'<div id="{lid}-lab" class="fl-link-label" style="left:{lx:.1f}px;top:{ly:.1f}px">{esc(link["label"])}</div>')
                self.a(f'tl.fromTo("#{lid}-lab",{{opacity:0,scale:.6}},{{opacity:1,scale:1,duration:.4,ease:"{f["spring"]}"}},{at + draw * .5:.4f});')
            self.sound(link.get("sfx", "draw"), at, None)
        for j, focus in enumerate(g.get("focus", [])):
            node = str(focus.get("node"))
            if node not in ids:
                raise ValueError(f"{self.id} focus {j} names an unknown node")
            at = self.cue(focus.get("at"), f"focus {j}")
            cx, cy = positions[ids.index(node)]
            size = node_size * k * 1.55
            self.a(f'tl.to("#{self.id}-ring",{{x:{cx - size / 2:.1f},y:{cy - size / 2:.1f},width:{size:.1f},height:{size:.1f},opacity:1,duration:{.01 if j == 0 else .45},ease:"{f["move"]}"}},{at:.4f});')
            if j == 0:
                self.a(f'tl.fromTo("#{self.id}-ring",{{scale:1.6}},{{scale:1,duration:.45,ease:"{f["pop"]}"}},{at:.4f});')
            self.sound(focus.get("sfx", "tick"), at, None)
        ring = f'<div id="{self.id}-ring" class="fl-ring" style="opacity:0"></div>' if g.get("focus") else ""
        svg = f'<svg class="fl-svg" width="{box_w_px:.0f}" height="{box_h_px:.0f}" viewBox="0 0 {box_w_px:.0f} {box_h_px:.0f}">{"".join(svg_paths)}</svg>'
        inner = f'<div class="fl" style="width:100%;height:100%">{svg}{ring}{"".join(markup_nodes)}</div>'
        markup = self.wrap(inner)
        if self.enter != "none":
            self.choreograph()
        else:
            if self.g.get("float", True) and self.hold() > 1.2:
                self.a(f'tl.fromTo("#{self.id}-float",{{y:0}},{{y:{-8 * k:.1f},duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
            self.exit_anim()
        return markup, self.anims

    def positions(self, layout, count, nodes, w, h):
        pad_x, pad_y = w * .14, h * .2
        if layout == "custom":
            result = []
            for i, node in enumerate(nodes):
                if "x" not in node or "y" not in node:
                    raise ValueError(f"{self.id} custom layout nodes need x and y (percent of the flow box)")
                result.append((w * num(node["x"], "node x", 0, 100) / 100, h * num(node["y"], "node y", 0, 100) / 100))
            return result
        if layout == "row" or count == 1:
            if count == 1:
                return [(w / 2, h / 2)]
            return [(pad_x + (w - 2 * pad_x) * i / (count - 1), h / 2) for i in range(count)]
        if layout == "column":
            return [(w / 2, pad_y + (h - 2 * pad_y) * i / (count - 1)) for i in range(count)]
        if layout == "zigzag":
            return [(pad_x + (w - 2 * pad_x) * i / (count - 1), h * (.32 if i % 2 == 0 else .68)) for i in range(count)]
        if layout == "triangle":
            if count != 3:
                raise ValueError(f"{self.id} triangle layout needs exactly three nodes")
            return [(w / 2, h * .2), (w * .18, h * .8), (w * .82, h * .8)]
        # hub: first node centred, others on an ellipse around it
        cx, cy = w / 2, h / 2
        rx, ry = w * .36, h * .36
        result = [(cx, cy)]
        for i in range(count - 1):
            angle = -math.pi / 2 + 2 * math.pi * i / (count - 1)
            result.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle)))
        return result


class Orbit(Component):
    """Centre card with satellites popping onto a drawn ring that slowly turns."""
    kind = "orbit"
    default_region = "stage"
    default_enter = "none"
    default_sfx = "popup"

    def render(self):
        g = self.g
        items = g.get("items", [])
        if not 2 <= len(items) <= 10:
            raise ValueError(f"{self.id} orbit needs two to ten items")
        box_w = self.ctx.width * self.w / 100 / self.zoom
        size = min(box_w, self.ctx.height * num(g.get("box_h", 38), "orbit box_h", 10, 80) / 100 / self.zoom)
        if self.h is None:
            self.h = size * self.zoom / self.ctx.height * 100
        k = self.px.n(1)
        radius = size * .4
        cx, cy = box_w / 2, size / 2
        center = g.get("center", {})
        f = self.feel
        parts = []
        center_label = esc(center.get("label", ""))
        center_img = f'<img src="{esc(self.ctx.media(center["image"]))}">' if center.get("image") else ""
        parts.append(f'<div id="{self.id}-c" class="ob-center" style="left:{cx:.1f}px;top:{cy:.1f}px">{center_img}<span class="{"serif" if center.get("serif", True) else ""}">{center_label}</span></div>')
        circumference = 2 * math.pi * radius
        ring = (f'<svg class="ob-svg" width="{box_w:.0f}" height="{size:.0f}"><circle id="{self.id}-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" '
                f'style="stroke-width:{3 * k:.1f}px;stroke-dasharray:{8 * k:.1f} {9 * k:.1f}"/></svg>')
        start_angle = -90
        for i, item in enumerate(items):
            angle = math.radians(start_angle + 360 * i / len(items))
            x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
            at = self.cue(item.get("at"), f"item {i} at", self.start + .35 + i * .12)
            iid = f"{self.id}-i{i}"
            visual = f'<img src="{esc(self.ctx.media(item["image"]))}">' if item.get("image") else (
                f'<div class="ob-icon">{icon_svg(item["icon"])}</div>' if item.get("icon") else "")
            label = f'<span>{esc(item.get("label", ""))}</span>' if item.get("label") else ""
            parts.append(f'<div id="{iid}" class="ob-item{" ob-media" if item.get("image") else ""}" style="left:{x:.1f}px;top:{y:.1f}px"><div id="{iid}-in" class="ob-item-in">{visual}{label}</div></div>')
            self.a(f'tl.fromTo("#{iid}-in",{{opacity:0,scale:.4}},{{opacity:1,scale:1,duration:.5,ease:"{f["spring"]}"}},{at:.4f});')
            self.sound(item.get("sfx", "pop"), at, .1)
        inner = f'<div class="ob" style="width:100%;height:{size:.0f}px">{ring}{"".join(parts)}</div>'
        markup = self.wrap(inner)
        self.a(f'tl.fromTo("#{self.id}-c",{{opacity:0,scale:.5}},{{opacity:1,scale:1,duration:.55,ease:"{f["pop"]}"}},{self.start:.4f});')
        self.a(f'tl.fromTo("#{self.id}-ring",{{opacity:0,scale:.82,rotation:-90,transformOrigin:"50% 50%"}},{{opacity:1,scale:1,rotation:0,duration:.8,ease:"power2.inOut"}},{self.start + .1:.4f});')
        spin = num(g.get("spin", 14), f"{self.id} spin", 0, 180)
        if spin and self.hold() > 1:
            self.a(f'tl.to("#{self.id}-ring",{{rotation:{spin},duration:{self.hold():.3f},ease:"none"}},{self.start + .9:.4f});')
        self.sfx(self.start, "whoosh_short")
        if self.hold() > 1.2 and g.get("float", True):
            self.a(f'tl.fromTo("#{self.id}-float",{{scale:1}},{{scale:1.03,duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.exit_anim()
        return markup, self.anims


class Device(Component):
    """Phone/window/card frame that animates real screen proof: zoom, scroll, highlight, cursor."""
    kind = "device"
    default_region = "center"
    default_enter = "tilt"
    default_sfx = "whoosh_short"

    def render(self):
        g = self.g
        device = g.get("device", "phone")
        if device not in {"phone", "window", "card"}:
            raise ValueError(f"{self.id} device must be phone, window or card")
        media = g.get("media")
        if not media:
            raise ValueError(f"{self.id} needs media (a real screenshot or screen recording)")
        path = self.ctx.media(media)
        image = path.lower().rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "webp", "svg", "avif"}
        k = self.px.n(1)
        aspect = num(g.get("aspect", 9 / 19.5 if device == "phone" else 16 / 10), f"{self.id} aspect", .2, 4)
        width_px = self.ctx.width * self.w / 100 / self.zoom
        screen_h = width_px / aspect
        if self.h is None:
            self.h = (screen_h + (64 * k if device == "window" else 0)) * self.zoom / self.ctx.height * 100
        fit = g.get("fit", "cover")
        position = g.get("position", "50% 0%")
        if image:
            tag = f'<img id="{self.id}-media" src="{esc(path)}" style="object-fit:{esc(fit)};object-position:{esc(position)}">'
        else:
            source_start = num(g.get("media_start", 0), f"{self.id} media_start", 0)
            tag = (f'<video id="{self.id}-media" class="clip" src="{esc(path)}" data-start="{self.start:.4f}" data-duration="{self.end - self.start:.4f}" '
                   f'data-media-start="{source_start:.3f}" muted playsinline style="object-fit:{esc(fit)};object-position:{esc(position)}"></video>')
        chrome = ""
        if device == "window":
            title = esc(g.get("title", ""))
            chrome = f'<div class="dv-bar"><i></i><i></i><i></i><span>{title}</span></div>'
        overlays = []
        self._marks, self._taps = [], []
        for j, mark in enumerate(g.get("highlights", [])):
            rx, ry, rw, rh = (num(v, f"{self.id} highlight rect", 0, 100) for v in mark.get("rect", []))
            hid = f"{self.id}-h{j}"
            shape = mark.get("shape", "box")
            at = self.cue(mark.get("at"), f"highlight {j} at")
            until = self.cue(mark.get("end"), f"highlight {j} end", self.end - .05)
            self._marks.append((j, at, until, (rx, ry, rw, rh), mark.get("label")))
            overlays.append(f'<div id="{hid}" class="dv-hl dv-hl-{esc(shape)}" style="left:{rx}%;top:{ry}%;width:{rw}%;height:{rh}%;opacity:0"></div>')
            self.a(f'tl.fromTo("#{hid}",{{opacity:0,scale:1.25}},{{opacity:1,scale:1,duration:.32,ease:"{self.feel["pop"]}"}},{at:.4f});')
            leave = max(at + .36, until - .2)
            if leave + .15 < self.end:
                self.a(f'tl.to("#{hid}",{{opacity:0,duration:.15}},{leave:.4f});')
            if mark.get("label"):
                overlays.append(f'<div id="{hid}-lab" class="dv-hl-label" style="left:{rx}%;top:calc({ry + rh}% + {8 * k:.1f}px)">{esc(mark["label"])}</div>')
                self.a(f'tl.fromTo("#{hid}-lab",{{opacity:0,y:{10 * k:.1f}}},{{opacity:1,y:0,duration:.3,ease:"{self.feel["enter"]}"}},{at + .12:.4f});')
                leave = max(at + .46, until - .2)
                if leave + .15 < self.end:
                    self.a(f'tl.to("#{hid}-lab",{{opacity:0,duration:.15}},{leave:.4f});')
            self.sound(mark.get("sfx", "tick"), at, None)
        for j, tap in enumerate(g.get("taps", [])):
            tx, ty = num(tap.get("x"), "tap x", 0, 100), num(tap.get("y"), "tap y", 0, 100)
            at = self.cue(tap.get("at"), f"tap {j} at")
            self._taps.append((j, at, tx, ty))
            tid = f"{self.id}-t{j}"
            overlays.append(f'<div id="{tid}" class="dv-tap" style="left:{tx}%;top:{ty}%;opacity:0"></div>')
            self.a(f'tl.fromTo("#{tid}",{{opacity:.9,scale:.3}},{{opacity:0,scale:1.6,duration:.5,ease:"power2.out",immediateRender:false}},{at:.4f});')
            self.sound("tap", at, None)
        # The camera zooms past the screen edge on purpose; the screen clips it.
        media_layer = f'<div id="{self.id}-cam" class="dv-cam" data-layout-allow-overflow>{tag}{"".join(overlays)}</div>'
        radius = {"phone": 56, "window": 22, "card": 28}[device]
        screen = f'<div class="dv-screen" style="height:{screen_h:.1f}px;border-radius:{(radius - 10) * k if device == "phone" else 0:.1f}px">{media_layer}</div>'
        badge = ""
        if g.get("badge"):
            badge_at = self.cue(g.get("badge_at"), "badge_at", self.start + .5)
            badge = f'<div id="{self.id}-badge" class="dv-badge">{esc(g["badge"])}</div>'
            self.a(f'tl.fromTo("#{self.id}-badge",{{scale:0,rotation:-8}},{{scale:1,rotation:0,duration:.5,ease:"{self.feel["spring"]}"}},{badge_at:.4f});')
            self.sound("pop", badge_at, None)
        inner = f'<div class="dv dv-{device}" style="border-radius:{radius * k:.1f}px">{chrome}{screen}</div>{badge}'
        markup = self.wrap(inner, inner_style="perspective:1600px", timed=image)
        self.choreograph()
        moves = g.get("moves", [])
        state = {"scale": 1, "x": 0, "y": 0}
        camera_keys = [(float("-inf"), dict(state))]
        for j, move in enumerate(moves):
            at = self.cue(move.get("at"), f"move {j} at")
            dur = num(move.get("duration", .7), f"{self.id} move duration", .05, 8)
            target = {"scale": num(move.get("scale", state["scale"]), "move scale", .5, 6),
                      "xPercent": num(move.get("x", state["x"]), "move x", -90, 90),
                      "yPercent": num(move.get("y", state["y"]), "move y", -95, 95)}
            state = {"scale": target["scale"], "x": target["xPercent"], "y": target["yPercent"]}
            camera_keys.append((at, dict(state)))
            self.a(f'tl.to("#{self.id}-cam",{{scale:{target["scale"]},xPercent:{target["xPercent"]},yPercent:{target["yPercent"]},duration:{dur:.3f},ease:"{move.get("ease", "power3.inOut")}"}},{at:.4f});')
        self.check_framing(camera_keys, screen_h, width_px)
        scroll = g.get("scroll")
        if scroll:
            at = self.cue(scroll.get("start"), "scroll start", self.start + .4)
            until = self.cue(scroll.get("end"), "scroll end", self.end - .3)
            to = num(scroll.get("to", 60), f"{self.id} scroll to", 0, 100)
            x_pos = position.split()[0] if position.split() else "50%"
            self.a(f'tl.fromTo("#{self.id}-media",{{objectPosition:{js(position)}}},{{objectPosition:"{esc(x_pos)} {to}%",duration:{max(.2, until - at):.3f},ease:"power1.inOut",immediateRender:false}},{at:.4f});')
        if not moves and not scroll and image:
            # A still screenshot must never sit inert: slow directed push toward the focal area.
            self.a(f'tl.fromTo("#{self.id}-cam",{{scale:1}},{{scale:{num(g.get("push", 1.06), "push", 1, 1.4)},duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.sfx(self.start)
        return markup, self.anims

    def check_framing(self, keys, screen_h, width_px):
        """Report highlights, labels and taps that a camera move has pushed off the screen.

        The camera (transform-origin 50% 35%) maps a screen point p to
        50 + (p - 50) * scale + x horizontally and 35 + (p - 35) * scale + y vertically.
        Each mark is checked against the framing the camera is heading to when it shows.
        """
        k = self.px.n(1)

        def camera(t):
            return [state for at, state in keys if at <= t + 1e-6][-1]

        def view(px_, py_, s):
            return 50 + (px_ - 50) * s["scale"] + s["x"], 35 + (py_ - 35) * s["scale"] + s["y"]

        for j, at, until, (rx, ry, rw, rh), label in self._marks:
            for t in sorted({round(at + .32, 3), round(max(at + .32, until - .2), 3)}):
                s = camera(t)
                x0, y0 = view(rx, ry, s)
                x1, y1 = view(rx + rw, ry + rh, s)
                problems = []
                if x0 < -1 or y0 < -1 or x1 > 101 or y1 > 101:
                    problems.append(f"box spans x {x0:.0f} to {x1:.0f}%, y {y0:.0f} to {y1:.0f}%")
                if label:
                    label_w = (len(str(label)) * 32 * .47 + 36) * k / width_px * 100 * s["scale"]
                    label_h = (32 * 1.25 + 28) * k / screen_h * 100 * s["scale"]
                    if x0 < -1 or x0 + label_w > 101 or y1 + label_h > 101:
                        problems.append(f'label "{label}" reaches x {x0 + label_w:.0f}%, y {y1 + label_h:.0f}%')
                if problems:
                    self.ctx.report.append(f"{self.id}: highlight {j} leaves the screen at {t:.2f}s "
                                           f"({'; '.join(problems)}); move the camera or tighten the rect")
                    break
        for j, at, x, y in self._taps:
            vx, vy = view(x, y, camera(at))
            if not (2 <= vx <= 98 and 2 <= vy <= 98):
                self.ctx.report.append(f"{self.id}: tap {j} lands off the screen at {at:.2f}s (x {vx:.0f}%, y {vy:.0f}%)")


class Chart(Component):
    kind = "chart"
    default_region = "stage"
    default_enter = "pop"
    default_sfx = "whoosh_short"

    def render(self):
        g = self.g
        points = [num(v, f"{self.id} point") for v in g.get("points", [])]
        if len(points) < 2:
            raise ValueError(f"{self.id} chart needs at least two points")
        k = self.px.n(1)
        box_w = self.ctx.width * self.w / 100 / self.zoom
        box_h = self.ctx.height * (self.h if self.h is not None else num(g.get("box_h", 26), "chart box_h", 8, 80)) / 100 / self.zoom
        if self.h is None:
            self.h = box_h * self.zoom / self.ctx.height * 100
        plot_top, plot_bottom = box_h * .26, box_h * .9
        lo, hi = min(points + [g.get("min", min(points))]), max(points + [g.get("max", max(points))])
        span = (hi - lo) or 1
        pad = box_w * .06
        coords = [(pad + (box_w - 2 * pad) * i / (len(points) - 1), plot_bottom - (p - lo) / span * (plot_bottom - plot_top)) for i, p in enumerate(points)]
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in coords)
        area = d + f" L{coords[-1][0]:.1f} {plot_bottom:.1f} L{coords[0][0]:.1f} {plot_bottom:.1f} Z"
        draw_start = self.cue(g.get("draw_start"), "draw_start", self.start + .3)
        draw_end = self.cue(g.get("draw_end"), "draw_end", min(self.end - .2, draw_start + 1.4))
        if draw_end <= draw_start:
            raise ValueError(f"{self.id} draw_end must follow draw_start")
        color = "var(--negative)" if g.get("tone") == "negative" else "var(--accent)"
        gid = f"{self.id}-grad"
        title = f'<div class="ch-title">{words_markup(g["title"], g.get("accent_words", []))}</div>' if g.get("title") else ""
        pills = []
        for j, pill in enumerate(g.get("pills", [])):
            index = int(pill.get("index", len(points) - 1))
            if not 0 <= index < len(points):
                raise ValueError(f"{self.id} pill {j} index is outside the points")
            x, y = coords[index]
            default_at = draw_start + (draw_end - draw_start) * index / (len(points) - 1)
            at = self.cue(pill.get("at"), f"pill {j} at", default_at)
            pid = f"{self.id}-p{j}"
            # The positioning wrapper keeps its CSS translate; GSAP only animates the inner pill.
            edge = " ch-pill-first" if index == 0 else " ch-pill-last" if index == len(points) - 1 else ""
            pills.append(f'<div class="ch-pill-pos{edge}" style="left:{x:.1f}px;top:{y - 18 * k:.1f}px"><div id="{pid}" class="ch-pill">{esc(pill.get("text", ""))}</div></div>'
                         f'<div id="{pid}-dot" class="ch-dot" style="left:{x:.1f}px;top:{y:.1f}px"></div>')
            self.a(f'tl.fromTo("#{pid}",{{opacity:0,scale:.5,y:{14 * k:.1f}}},{{opacity:1,scale:1,y:0,duration:.42,ease:"{self.feel["spring"]}"}},{at:.4f});')
            self.a(f'tl.fromTo("#{pid}-dot",{{scale:0}},{{scale:1,duration:.3,ease:"{self.feel["pop"]}"}},{at - .05:.4f});')
            self.sound(pill.get("sfx", "pop"), at, .1)
        grid = "".join(f'<line x1="{pad:.1f}" x2="{box_w - pad:.1f}" y1="{plot_top + (plot_bottom - plot_top) * r:.1f}" y2="{plot_top + (plot_bottom - plot_top) * r:.1f}"/>' for r in (0, .5, 1))
        svg = (f'<svg class="ch-svg" width="{box_w:.0f}" height="{box_h:.0f}"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
               f'<stop offset="0" stop-color="{"#ff5d5d" if g.get("tone") == "negative" else self.ctx.design["accent"]}" stop-opacity=".38"/><stop offset="1" stop-color="#000" stop-opacity="0"/></linearGradient>'
               f'<clipPath id="{self.id}-clip"><rect id="{self.id}-reveal" x="0" y="0" width="0" height="{box_h:.0f}"/></clipPath></defs>'
               f'<g class="ch-grid">{grid}</g><path d="{area}" fill="url(#{gid})" clip-path="url(#{self.id}-clip)"/>'
               f'<path id="{self.id}-line" d="{d}" class="ch-line" style="stroke:{color};stroke-width:{6 * k:.1f}px"/></svg>')
        inner = f'<div class="ch glass" style="height:{box_h:.0f}px">{title}{svg}{"".join(pills)}</div>'
        markup = self.wrap(inner)
        self.choreograph()
        self.a(f'tl.fromTo("#{self.id}-line",{{drawSVG:"0%"}},{{drawSVG:"100%",duration:{draw_end - draw_start:.3f},ease:"power1.inOut"}},{draw_start:.4f});')
        self.a(f'tl.fromTo("#{self.id}-reveal",{{attr:{{width:0}}}},{{attr:{{width:{box_w:.0f}}},duration:{draw_end - draw_start:.3f},ease:"power1.inOut"}},{draw_start:.4f});')
        self.sound("draw", draw_start, None)
        self.sfx(self.start)
        return markup, self.anims


class Checklist(Component):
    kind = "checklist"
    default_region = "center"
    default_enter = "pop"

    def render(self):
        g = self.g
        items = g.get("items", [])
        if not 1 <= len(items) <= 6:
            raise ValueError(f"{self.id} checklist needs one to six items")
        k = self.px.n(1)
        f = self.feel
        rows = []
        title = f'<div class="ck-title">{words_markup(g["title"], g.get("accent_words", []))}</div>' if g.get("title") else ""
        numbered = g.get("numbered", True)
        for i, item in enumerate(items):
            rid = f"{self.id}-r{i}"
            at = self.cue(item.get("at"), f"item {i} at", self.start + .2 + i * .22)
            state = item.get("state", "done")
            if state not in {"done", "fail", "pending"}:
                raise ValueError(f"{self.id} item state must be done, fail or pending")
            done_at = self.cue(item.get("done_at"), f"item {i} done_at", at + .35) if state != "pending" else None
            mark = ('<svg viewBox="0 0 24 24"><path id="%s-mark" d="M5 12.5l4.5 4.5L19 7.5"/></svg>' % rid if state == "done" else
                    '<svg viewBox="0 0 24 24"><path id="%s-mark" d="M7 7l10 10M17 7L7 17"/></svg>' % rid)
            index = f'<span class="ck-num">{i + 1:02d}</span>' if numbered else ""
            rows.append(f'<div id="{rid}" class="ck-row ck-{state}" data-layout-allow-occlusion>{index}<span class="ck-box">{mark if state != "pending" else ""}</span>'
                        f'<span class="ck-text">{words_markup(item.get("text", ""), item.get("accent_words", []))}</span><b id="{rid}-strike" class="ck-strike"></b></div>')
            self.a(f'tl.fromTo("#{rid}",{{opacity:0,x:{-40 * k:.1f}}},{{opacity:1,x:0,duration:.4,ease:"{f["enter"]}"}},{at:.4f});')
            self.sound(item.get("sfx", "tick"), at, None)
            if done_at is not None:
                self.a(f'tl.fromTo("#{rid}-mark",{{drawSVG:"0%"}},{{drawSVG:"100%",duration:.3,ease:"power2.out"}},{done_at:.4f});')
                box_color = self.ctx.design["accent"] if state == "done" else self.ctx.design["negative"]
                self.a(f'tl.to("#{rid} .ck-box",{{backgroundColor:"{box_color}",borderColor:"{box_color}",duration:.2,ease:"power2.out"}},{done_at:.4f});')
                self.a(f'tl.fromTo("#{rid} .ck-box",{{scale:1}},{{scale:1.22,duration:.14,yoyo:true,repeat:1,ease:"power2.out",immediateRender:false}},{done_at:.4f});')
                if state == "fail":
                    self.a(f'tl.fromTo("#{rid}-strike",{{scaleX:0}},{{scaleX:1,duration:.3,ease:"power2.out"}},{done_at:.4f});')
                    self.a(f'tl.to("#{rid} .ck-text",{{opacity:.4,duration:.3}},{done_at:.4f});')
                self.sound("pop" if state == "done" else "deny", done_at, None)
        inner = f'<div class="ck glass">{title}{"".join(rows)}</div>'
        markup = self.wrap(inner)
        self.choreograph()
        self.sfx(self.start, "whoosh_short")
        return markup, self.anims


class Compare(Component):
    kind = "compare"
    default_region = "center"
    default_enter = "pop"

    def render(self):
        g = self.g
        f = self.feel
        k = self.px.n(1)
        sides = []
        for side in ("left", "right"):
            data = g.get(side)
            if not isinstance(data, dict):
                raise ValueError(f"{self.id} needs {side} object")
            tone = data.get("tone", "negative" if side == "left" else "positive")
            at = self.cue(data.get("at"), f"{side} at", self.start + (0 if side == "left" else .35))
            sid = f"{self.id}-{side}"
            items = "".join(f'<li>{esc(t)}</li>' for t in data.get("items", []))
            icon = icon_svg("x" if tone == "negative" else "check")
            sides.append(f'<div id="{sid}" class="cp-side cp-{tone}" data-layout-allow-occlusion><div class="cp-head"><span class="cp-ico">{icon}</span>{esc(data.get("title", ""))}</div><ul>{items}</ul><b id="{sid}-strike" class="cp-strike"></b></div>')
            self.a(f'tl.fromTo("#{sid}",{{opacity:0,y:{40 * k:.1f},scale:.94}},{{opacity:1,y:0,scale:1,duration:.45,ease:"{f["pop"]}"}},{at:.4f});')
            if data.get("items"):  # a side can be a title alone; never tween an empty selector
                self.a(f'tl.fromTo("#{sid} li",{{opacity:0,x:{-16 * k:.1f}}},{{opacity:1,x:0,duration:.3,stagger:.08,ease:"{f["enter"]}"}},{at + .15:.4f});')
            self.sound("pop", at, None)
        vs = f'<div id="{self.id}-vs" class="cp-vs">{esc(g.get("vs", "vs"))}</div>'
        inner = f'<div class="cp">{sides[0]}{vs}{sides[1]}</div>'
        markup = self.wrap(inner)
        self.a(f'tl.fromTo("#{self.id}-vs",{{scale:0,rotation:-20}},{{scale:1,rotation:0,duration:.45,ease:"{f["spring"]}"}},{self.start + .2:.4f});')
        if g.get("strike_at") is not None:
            at = self.cue(g["strike_at"], "strike_at")
            # Rotation lives in the tween: GSAP cannot recover it from a CSS scaleX(0) matrix.
            self.a(f'tl.fromTo("#{self.id}-left-strike",{{scaleX:0,rotation:-7}},{{scaleX:1,rotation:-7,duration:.32,ease:"power2.out"}},{at:.4f});')
            # Dim the losing side's words, not the red strike drawn over them.
            self.a(f'tl.to("#{self.id}-left .cp-head, #{self.id}-left ul",{{opacity:.38,filter:"grayscale(1)",duration:.35}},{at:.4f});')
            self.sound("deny", at, None)
        if g.get("win_at") is not None:
            at = self.cue(g["win_at"], "win_at")
            self.a(f'tl.fromTo("#{self.id}-right",{{scale:1}},{{scale:1.06,duration:.2,yoyo:true,repeat:1,ease:"power2.out",immediateRender:false}},{at:.4f});')
            self.a(f'tl.fromTo("#{self.id}-right",{{boxShadow:"0 {20 * k:.0f}px {50 * k:.0f}px rgba(0,0,0,.5)"}},{{boxShadow:"0 0 {60 * k:.0f}px rgba(73,207,38,.45)",duration:.4,immediateRender:false}},{at:.4f});')
            self.sound("pop", at, None)
        if self.hold() > 1.2 and g.get("float", True):
            self.a(f'tl.fromTo("#{self.id}-float",{{y:0}},{{y:{-8 * k:.1f},duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.exit_anim()
        return markup, self.anims


class Prompt(Component):
    """Prompt/script card that types exact text on a spoken span; optional send press."""
    kind = "prompt"
    default_region = "center"
    default_enter = "pop"
    default_sfx = "whoosh_short"

    def render(self):
        g = self.g
        text = str(g.get("text", ""))
        if not text.strip():
            raise ValueError(f"{self.id} needs the exact prompt text")
        f = self.feel
        k = self.px.n(1)
        type_start = self.cue(g.get("type_start"), "type_start", self.start + .35)
        type_end = self.cue(g.get("type_end"), "type_end", min(self.end - .3, type_start + max(.6, len(text) / 38)))
        if type_end <= type_start:
            raise ValueError(f"{self.id} type_end must follow type_start")
        label = esc(g.get("label", "Prompt"))
        style = g.get("style", "chat")
        if style not in {"chat", "script", "terminal"}:
            raise ValueError(f"{self.id} style must be chat, script or terminal")
        tid = f"{self.id}-text"
        send = ""
        if style == "chat":
            send = f'<div id="{self.id}-send" class="pr-send">{icon_svg("send")}</div>'
        header = (f'<div class="pr-head"><span class="pr-dot"></span>{label}</div>' if style != "script"
                  else f'<div class="pr-head pr-script serif">{label}</div>')
        inner = (f'<div class="pr pr-{style} glass">{header}<div class="pr-body"><span class="pr-ghost">{esc(text)}</span>'
                 f'<span class="pr-live"><span id="{tid}"></span><span id="{self.id}-caret" class="pr-caret"></span></span></div>{send}</div>')
        markup = self.wrap(inner)
        self.choreograph()
        var = "v_" + self.id.replace("-", "_") + "_c"
        self.a(f'const {var}={{n:0}};tl.fromTo({var},{{n:0}},{{n:{len(text)},duration:{type_end - type_start:.3f},ease:"none",onUpdate:()=>{{document.getElementById("{tid}").textContent={js(text)}.slice(0,Math.round({var}.n));}}}},{type_start:.4f});')
        blink = max(1, int((self.end - self.start - .35) / .25))  # blink through the hold, stop before the clip ends
        self.a(f'tl.fromTo("#{self.id}-caret",{{opacity:1}},{{opacity:0,duration:.25,repeat:{blink},yoyo:true,ease:"steps(1)"}},{self.start:.4f});')
        self.sound("typing", type_start, None, duration=round(type_end - type_start, 3))
        if style == "chat" and g.get("send_at") is not None:
            at = self.cue(g["send_at"], "send_at")
            self.a(f'tl.fromTo("#{self.id}-send",{{scale:1}},{{scale:.78,duration:.09,yoyo:true,repeat:1,ease:"power2.out"}},{at:.4f});')
            self.a(f'tl.to("#{self.id}-send",{{backgroundColor:"{self.ctx.design["accent"]}",color:"{self.ctx.design["accent_ink"]}",duration:.15}},{at:.4f});')
            self.sound("tap", at, None)
        self.sfx(self.start)
        return markup, self.anims


class Spotlight(Component):
    """Ring or box drawn around a frame region (face, hand, UI detail)."""
    kind = "spotlight"
    default_region = "center"
    default_enter = "none"
    default_sfx = "draw"

    def render(self):
        g = self.g
        shape = g.get("shape", "circle")
        if shape not in {"circle", "box"}:
            raise ValueError(f"{self.id} shape must be circle or box")
        k = self.px.n(1)
        w_px = self.ctx.width * self.w / 100 / self.zoom
        h_pct = self.h if self.h is not None else self.w * self.ctx.width / self.ctx.height
        self.h = h_pct
        h_px = self.ctx.height * h_pct / 100 / self.zoom
        stroke = 6 * k
        if shape == "circle":
            path = f'<ellipse id="{self.id}-s" cx="{w_px / 2:.1f}" cy="{h_px / 2:.1f}" rx="{w_px / 2 - stroke:.1f}" ry="{h_px / 2 - stroke:.1f}"/>'
        else:
            r = 18 * k
            path = f'<rect id="{self.id}-s" x="{stroke:.1f}" y="{stroke:.1f}" width="{w_px - 2 * stroke:.1f}" height="{h_px - 2 * stroke:.1f}" rx="{r:.1f}"/>'
        label = f'<div id="{self.id}-lab" class="sp-label">{esc(g["label"])}</div>' if g.get("label") else ""
        inner = f'<svg class="sp-svg" width="{w_px:.0f}" height="{h_px:.0f}" style="stroke-width:{stroke:.1f}px">{path}</svg>{label}'
        markup = self.wrap(inner)
        turn = ',rotation:-90,transformOrigin:"50% 50%"' if shape == "circle" else ""
        settle = ",rotation:0" if shape == "circle" else ""
        self.a(f'tl.fromTo("#{self.id}-s",{{drawSVG:"0%"{turn}}},{{drawSVG:"100%"{settle},duration:.5,ease:"power2.inOut"}},{self.start:.4f});')
        if label:
            self.a(f'tl.fromTo("#{self.id}-lab",{{opacity:0,y:{12 * k:.1f}}},{{opacity:1,y:0,duration:.35,ease:"{self.feel["enter"]}"}},{self.start + .3:.4f});')
        self.exit_anim()
        self.sfx(self.start)
        return markup, self.anims


class Badge(Component):
    kind = "badge"
    default_region = "seam"
    default_enter = "pop"

    def render(self):
        g = self.g
        text = str(g.get("text", "")).strip()
        if not text:
            raise ValueError(f"{self.id} needs text")
        variant = g.get("variant", "accent")
        if variant not in {"accent", "dark", "outline", "number"}:
            raise ValueError(f"{self.id} variant must be accent, dark, outline or number")
        icon = g.get("icon")
        ico = f'<span class="bd-ico">{icon_svg(icon)}</span>' if icon else ""
        size = num(g.get("size", 52), f"{self.id} size", 16, 200)
        inner = f'<div class="bd-wrap"><div class="bd bd-{variant}" style="font-size:{self.px(size)}">{ico}<span>{esc(text)}</span></div></div>'
        markup = self.wrap(inner)
        f = self.feel
        self.a(f'tl.fromTo("#{self.body}",{{scale:0,rotation:-10}},{{scale:1,rotation:0,duration:.55,ease:"{f["spring"]}"}},{self.start:.4f});')
        if self.hold() > 1.2 and g.get("float", True):
            self.a(f'tl.fromTo("#{self.id}-float",{{y:0}},{{y:{self.px.n(-6):.1f},duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.exit_anim()
        self.sfx(self.start)
        return markup, self.anims


class Equation(Component):
    """Niche hook: tiles joined by operators, resolving to a result (A + B = $X)."""
    kind = "equation"
    default_region = "top"
    default_enter = "none"
    default_sfx = "popup"

    def render(self):
        g = self.g
        terms = g.get("terms", [])
        if not 2 <= len(terms) <= 4:
            raise ValueError(f"{self.id} equation needs two to four terms")
        f = self.feel
        k = self.px.n(1)
        parts = []
        times = [self.cue(term.get("at"), f"term {i} at", self.start + i * .3) for i, term in enumerate(terms)]
        # With slots, the "? + ? = ?" skeleton is readable from the first frame and fills in on cue.
        # A term spoken right at the start needs no slot.
        slots_on = bool(g.get("slots", True))
        has_slot = [slots_on and at > self.start + .3 for at in times]
        early = any(has_slot)
        ops = g.get("ops") or ["+"] * (len(terms) - 1)
        if len(ops) != len(terms) - 1:
            raise ValueError(f"{self.id} needs {len(terms) - 1} ops for {len(terms)} terms")
        for i, (term, at) in enumerate(zip(terms, times)):
            tid = f"{self.id}-t{i}"
            if term.get("image"):
                visual = f'<img src="{esc(self.ctx.media(term["image"]))}">'
            elif term.get("icon"):
                visual = f'<span class="eq-ico">{icon_svg(term["icon"])}</span>'
            else:
                visual = ""
            label = f'<span class="eq-lab">{esc(term.get("label", ""))}</span>' if term.get("label") else ""
            slot = f'<div id="{tid}-slot" class="eq-slot" data-layout-allow-overlap data-layout-allow-occlusion>?</div>' if has_slot[i] else ""
            parts.append(f'<div class="eq-cell">{slot}<div id="{tid}" class="eq-tile">{visual}{label}</div></div>')
            if slot:
                self.a(f'tl.fromTo("#{tid}-slot",{{opacity:0,scale:.7}},{{opacity:1,scale:1,duration:.35,ease:"{f["enter"]}"}},{self.start + i * .08:.4f});')
                self.a(f'tl.to("#{tid}-slot",{{opacity:0,scale:1.3,duration:.25}},{at:.4f});')
            self.a(f'tl.fromTo("#{tid}",{{opacity:0,scale:.3,y:{30 * k:.1f},rotation:-12}},{{opacity:1,scale:1,y:0,rotation:0,duration:.5,ease:"{f["spring"]}"}},{at:.4f});')
            self.sound(term.get("sfx", "pop"), at, None)
            if i < len(terms) - 1:
                parts.append(f'<div id="{tid}-op" class="eq-op">{esc(ops[i])}</div>')
                op_at = self.start + .1 + i * .08 if early else min(at + .18, self.end - .3)
                self.a(f'tl.fromTo("#{tid}-op",{{opacity:0,scale:0}},{{opacity:1,scale:1,duration:.3,ease:"{f["pop"]}"}},{op_at:.4f});')
        result = g.get("result")
        res = ""
        if result:
            at = self.cue(result.get("at"), "result at", self.start + len(terms) * .3 + .2)
            size = num(result.get("size", 104), f"{self.id} result size", 30, 200)
            result_slot = slots_on and at > self.start + .6
            slot = f'<span id="{self.id}-rslot" class="eq-rslot" data-layout-allow-overlap>?</span>' if result_slot else ""
            res = (f'<div class="eq-res"><span id="{self.id}-eq" class="eq-op">=</span>'
                   f'<span class="eq-rwrap" data-layout-allow-occlusion><span id="{self.id}-res" class="eq-result" style="font-size:{self.px(size)}">'
                   f'{words_markup(result.get("text", ""), result.get("accent_words", []))}</span>{slot}</span></div>')
            eq_at = self.start + .1 + len(terms) * .08 if result_slot else at - .12
            self.a(f'tl.fromTo("#{self.id}-eq",{{opacity:0,scale:0}},{{opacity:1,scale:1,duration:.3,ease:"{f["pop"]}"}},{eq_at:.4f});')
            if result_slot:
                self.a(f'tl.fromTo("#{self.id}-rslot",{{opacity:0,scale:.7}},{{opacity:1,scale:1,duration:.35,ease:"{f["enter"]}"}},{eq_at + .05:.4f});')
                self.a(f'tl.to("#{self.id}-rslot",{{opacity:0,scale:1.15,duration:.2}},{at - .05:.4f});')
            self.a(f'tl.fromTo("#{self.id}-res .wi",{{yPercent:110}},{{yPercent:0,duration:.5,stagger:.05,ease:"{f["enter"]}"}},{at:.4f});')
            self.sound(result.get("sfx", "thud"), at, None)
        inner = f'<div class="eq"><div class="eq-row">{"".join(parts)}</div>{res}</div>'
        markup = self.wrap(inner)
        if self.hold() > 1.2 and g.get("float", True):
            self.a(f'tl.fromTo("#{self.id}-float",{{y:0}},{{y:{-8 * k:.1f},duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.exit_anim()
        return markup, self.anims


class CTA(Component):
    """Keyword call to action with several distinct treatments; the keyword must be spoken."""
    kind = "cta"
    default_region = "lower"
    default_enter = "none"
    default_sfx = "popup"
    STYLES = {"chip", "stamp", "type", "bubble", "underline", "fan"}

    def render(self):
        g = self.g
        keyword = str(g.get("keyword", "")).strip()
        if not keyword:
            raise ValueError(f"{self.id} needs the exact spoken keyword")
        if self.ctx.resolver.words and not self.ctx.resolver.occurrences(keyword):
            raise ValueError(f"{self.id} keyword {keyword!r} is never spoken; display the keyword Brandon says")
        style = g.get("style", "chip")
        if style not in self.STYLES:
            raise ValueError(f"{self.id} style must be one of {', '.join(sorted(self.STYLES))}")
        f = self.feel
        k = self.px.n(1)
        key_at = self.cue(g.get("keyword_at"), "keyword_at", self.start + .2)
        prefix = esc(g.get("prefix", "Comment"))
        suffix = g.get("suffix", "")
        kid = f"{self.id}-key"
        pages = ""
        if style == "fan":
            titles = g.get("pages", [])
            if not 1 <= len(titles) <= 5:
                raise ValueError(f"{self.id} fan style needs one to five real resource page titles or images")
            cards = []
            for i, page in enumerate(titles):
                rot = (i - (len(titles) - 1) / 2) * 9
                content = (f'<img src="{esc(self.ctx.media(page["image"]))}">' if isinstance(page, dict) and page.get("image")
                           else f'<div class="ct-page-t" data-layout-allow-overlap data-layout-allow-occlusion>{esc(page if isinstance(page, str) else page.get("title", ""))}</div><i></i><i></i><i></i><i class="short"></i>')
                cards.append(f'<div id="{self.id}-p{i}" class="ct-page" style="--rot:{rot:.1f}deg">{content}</div>')
                self.a(f'tl.fromTo("#{self.id}-p{i}",{{opacity:0,y:{120 * k:.1f},rotation:0,scale:.7}},{{opacity:1,y:0,rotation:{rot:.1f},scale:1,duration:.6,ease:"{f["pop"]}"}},{self.start + .1 + i * .08:.4f});')
            pages = f'<div class="ct-fan" data-layout-allow-overlap data-layout-allow-occlusion>{"".join(cards)}</div>'
            self.sound("paper", self.start + .1, None)
        key_markup = {
            "chip": f'<span id="{kid}" class="ct-key ct-chip">{esc(keyword)}</span>',
            "stamp": f'<span id="{kid}" class="ct-key ct-stamp">{esc(keyword)}</span>',
            "type": f'<span class="ct-key ct-type"><span id="{kid}"></span><span id="{kid}-caret" class="ct-caret"></span></span>',
            "bubble": f'<span id="{kid}" class="ct-key ct-bubble">{icon_svg("chat")}<span>{esc(keyword)}</span></span>',
            "underline": f'<span class="ct-key ct-ul"><span id="{kid}">{esc(keyword)}</span><svg id="{kid}-ul" viewBox="0 0 100 12" preserveAspectRatio="none"><path vector-effect="non-scaling-stroke" d="M2 8 C 30 3, 62 11, 98 5"/></svg></span>',
            "fan": f'<span id="{kid}" class="ct-key ct-chip">{esc(keyword)}</span>',
        }[style]
        sub = f'<div id="{self.id}-sub" class="ct-sub">{esc(suffix)}</div>' if suffix else ""
        inner = f'<div class="ct ct-style-{style}">{pages}<div class="ct-line"><span id="{self.id}-pre" class="ct-pre">{prefix}</span>{key_markup}</div>{sub}</div>'
        markup = self.wrap(inner)
        self.a(f'tl.fromTo("#{self.id}-pre",{{opacity:0,y:{24 * k:.1f}}},{{opacity:1,y:0,duration:.35,ease:"{f["enter"]}"}},{self.start:.4f});')
        if style == "chip" or style == "fan":
            self.a(f'tl.fromTo("#{kid}",{{scale:0,rotation:-6}},{{scale:1,rotation:0,duration:.55,ease:"{f["spring"]}"}},{key_at:.4f});')
        elif style == "stamp":
            self.a(f'tl.fromTo("#{kid}",{{scale:2.6,opacity:0,rotation:-14}},{{scale:1,opacity:1,rotation:-4,duration:.32,ease:"power4.in"}},{key_at - .2:.4f});')
            self.a(f'tl.fromTo("#{self.id}-float",{{x:0}},{{x:{6 * k:.1f},duration:.05,yoyo:true,repeat:3,ease:"none"}},{key_at + .12:.4f});')
        elif style == "type":
            var = "v_" + self.id.replace("-", "_") + "_k"
            self.a(f'const {var}={{n:0}};tl.fromTo({var},{{n:0}},{{n:{len(keyword)},duration:{max(.25, len(keyword) * .06):.3f},ease:"none",onUpdate:()=>{{document.getElementById("{kid}").textContent={js(keyword)}.slice(0,Math.round({var}.n));}}}},{key_at:.4f});')
            self.a(f'tl.fromTo("#{kid}-caret",{{opacity:1}},{{opacity:0,duration:.25,repeat:{max(1, int((self.hold() - .35) / .25))},yoyo:true,ease:"steps(1)"}},{self.start:.4f});')
        elif style == "bubble":
            self.a(f'tl.fromTo("#{kid}",{{scale:0,transformOrigin:"0% 100%"}},{{scale:1,duration:.5,ease:"{f["spring"]}"}},{key_at:.4f});')
        elif style == "underline":
            self.a(f'tl.fromTo("#{kid}",{{opacity:0,y:{30 * k:.1f}}},{{opacity:1,y:0,duration:.4,ease:"{f["enter"]}"}},{key_at:.4f});')
            self.a(f'tl.fromTo("#{kid}-ul",{{clipPath:"inset(-150% 100% -150% -4%)"}},{{clipPath:"inset(-150% -4% -150% -4%)",duration:.45,ease:"power2.inOut"}},{key_at + .2:.4f});')
        if suffix:
            self.a(f'tl.fromTo("#{self.id}-sub",{{opacity:0,y:{16 * k:.1f}}},{{opacity:1,y:0,duration:.35,ease:"{f["enter"]}"}},{key_at + .3:.4f});')
        # Renew the keyword once during a long hold instead of leaving it inert.
        if self.end - key_at > 2.2:
            pulse_target = f"#{kid}" if style not in {"type", "underline"} else f"#{self.id} .ct-key"
            self.a(f'tl.fromTo("{pulse_target}",{{scale:1}},{{scale:1.07,duration:.22,yoyo:true,repeat:1,ease:"power2.inOut",immediateRender:false}},{key_at + 1.6:.4f});')
        self.sound(g.get("sfx", "stamp" if style == "stamp" else "pop"), key_at, None)
        if self.hold() > 1.2 and g.get("float", True):
            self.a(f'tl.fromTo("#{self.id}-float",{{y:0}},{{y:{-6 * k:.1f},duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        self.exit_anim()
        return markup, self.anims


COMPONENTS = {cls.kind: cls for cls in (Headline, Statement, Card, Stat, Flow, Orbit, Device, Chart,
                                         Checklist, Compare, Prompt, Spotlight, Badge, Equation, CTA)}


def render_graphics(graphics, ctx):
    if not isinstance(graphics, list):
        raise ValueError("graphics must be a list")
    markup, anims, meta = [], [], []
    seen = set()
    for index, spec in enumerate(graphics):
        if not isinstance(spec, dict):
            raise ValueError(f"graphic {index} must be an object")
        kind = spec.get("type")
        if kind not in COMPONENTS:
            raise ValueError(f"graphic {index} type must be one of {', '.join(sorted(COMPONENTS))}")
        component = COMPONENTS[kind](spec, index, ctx)
        # Ids become CSS selectors and (with "-" as "_") script variable names.
        key = component.id.replace("-", "_")
        if key in seen:
            raise ValueError(f"duplicate graphic id {component.id} (ids must differ by more than - versus _)")
        seen.add(key)
        m, a = component.render()
        markup.append(m)
        anims.extend(a)
        meta.append({"id": component.id, "type": kind, "start": round(component.start, 3), "end": round(component.end, 3),
                     "beat": spec.get("beat", ""), "enter": component.enter, "exit": component.exit,
                     "box": [None if v is None else round(v, 2) for v in component.meta_box()],
                     "depth": component.depth, "scrim": bool(spec.get("scrim", False)),
                     "hides_captions": component.hides_captions(),
                     "variant": spec.get("variant"), "showpiece": component.showpiece(),
                     **({"size_px": component.fitted_px} if getattr(component, "fitted_px", None) else {})})
    return markup, anims, meta


# Presenter-first showreel primitives (hero type, callout tags, payoff reveal, particles).
# motion_kit registers them into COMPONENTS itself, so importing either module first works.
import motion_kit  # noqa: E402,F401
