"""Showreel-grade motion primitives for Brandon's presenter-first style.

Components (registered into components.COMPONENTS):

* ``hero``      large kinetic type over or beside Brandon, word-synced, with variants
                stack | slam | split | outline | card | depth, each with its own entrance
                and a deliberate exit. Hides the short captions while it is up.
* ``tag``       compact callout pills (one or a stacked list) that pop in on their words,
                optionally with a leader line to what they describe.
* ``reveal``    the closing payoff: the result rises in 2.5D on a card with depth,
                reflection, a light sweep, restrained particles and a word-synced title.
* ``particles`` restrained drifting glints for a showpiece moment.

Shot layout helper ``screen_markup`` builds the full-frame "screen detail" shot: a real
capture on a 2.5D plane over its own blurred backdrop, with keyframed focus crops that
land on spoken words and highlights that ride along with the plane.

Every size is authored on the 1080 grid; every time can be a word cue.
"""
import components as _components
from components import Component, esc, js, num
from cues import normalize


def word_times(component, tokens):
    """Spoken start time of each token, matched in order from the component's start."""
    words = component.ctx.resolver.words
    spoken = [w for w in words if w["end"] > component.start - .05]
    times, cursor = [], 0
    for token in tokens:
        wanted = normalize(token)
        found = None
        for j in range(cursor, min(len(spoken), cursor + 8)):
            if normalize(spoken[j]["word"]) == wanted:
                found = j
                break
        if found is None:
            times.append(times[-1] + .06 if times else component.start)
        else:
            times.append(max(component.start, component.ctx.resolver.frame(spoken[found]["start"])))
            cursor = found + 1
    return [min(t, component.end - .25) for t in times]


def fit_size(lines, size, box_px, low, scales=None, glyph=.6):
    """Shrink display type until every line fits the box. ``scales`` is each line's size
    relative to the base (a slam's last line is 1.28em); ``glyph`` is the average advance of
    an uppercase display glyph in em after the tight tracking."""
    scales = list(scales or []) + [1.0] * (len(lines) - len(scales or []))
    widest = max((len(str(line)) * sc for line, sc in zip(lines, scales)), default=1)
    while size > low and widest * size * glyph > box_px:
        size -= 4
    return max(size, low)


def hero_line_scales(variant, lines):
    return [1.0] * (len(lines) - 1) + [1.28] if variant == "slam" and lines else None


class Hero(Component):
    """Large kinetic type. Variants have their own entrances and exits:

    stack    words rise through masks on their spoken times; accent words glow green.
    slam     the key word crashes in from scale with blur and a shock ring; the rest settles.
    split    two lines drive in from opposite sides; an accent bar draws between them.
    outline  outlined words; the accent word fills green on its word.
    card     Instagram-native white card with a green marker under the accent (hook card).
    depth    stack placed behind Brandon (needs source.matte).
    """
    kind = "hero"
    default_region = "center"
    default_enter = "none"
    default_exit = "none"
    default_sfx = "popup"
    caption_default = "hide"
    showpiece_variants = ("slam", "split", "depth", "outline")
    VARIANTS = ("stack", "slam", "split", "outline", "card", "depth")
    ZONES = {"chest": 45.5, "top": 7.0, "center": 33.0, "low": 56.0}

    def __init__(self, spec, index, ctx):
        spec = dict(spec)
        zone = spec.get("zone", "chest")
        if zone not in self.ZONES:
            raise ValueError(f"hero zone must be one of {', '.join(self.ZONES)}")
        if "region" not in spec:
            spec.setdefault("y", self.ZONES[zone])
            spec.setdefault("x", 6)
            # Low type keeps clear of the platform's action buttons on the right.
            spec.setdefault("w", 80 if zone == "low" else 88)
        if spec.get("variant") == "depth":
            spec["depth"] = "behind"
        super().__init__(spec, index, ctx)

    def render(self):
        g = self.g
        variant = g.get("variant", "stack")
        if variant not in self.VARIANTS:
            raise ValueError(f"{self.id} variant must be one of {', '.join(self.VARIANTS)}")
        lines = [str(line) for line in (g.get("lines") or [g.get("text", "")])]
        if not any(line.strip() for line in lines):
            raise ValueError(f"{self.id} needs text or lines")
        if variant == "split" and len(lines) != 2:
            raise ValueError(f"{self.id} split needs exactly two lines")
        k = self.px.n(1)
        box_px = 1080 * self.w / 100
        accent = {a.casefold().strip(".,!?;:\"'") for a in g.get("accent_words", [])}
        default_size = 64 if variant == "card" else 136
        size = num(g.get("size", default_size), f"{self.id} size", 30, 260)
        if variant != "card":
            size = fit_size(lines, size, box_px, 84, hero_line_scales(variant, lines))
        self.fitted_px = size
        tokens, rows, ids, accent_ids = [], [], [], []
        for li, line in enumerate(lines):
            spans = []
            for token in line.split():
                wid = f"{self.id}-w{len(ids)}"
                key = token.casefold().strip(".,!?;:\"'")
                is_accent = key in accent
                ids.append(wid)
                tokens.append(token)
                if is_accent:
                    accent_ids.append(wid)
                if variant == "card":
                    klass = "hc-mark" if is_accent else ""
                    spans.append(f'<span id="{wid}" class="hc-w {klass}">{"<i></i>" if is_accent else ""}{esc(token)}</span>')
                elif variant == "outline":
                    fill = f'<span id="{wid}-fill" class="ho-fill" aria-hidden="true">{esc(token)}</span>' if is_accent else ""
                    spans.append(f'<span class="w"><span id="{wid}" class="wi ho-w">{esc(token)}{fill}</span></span>')
                else:
                    klass = "hero-accent" if is_accent else ""
                    # Slam and stack words cross each other while they land; that layering is intended.
                    spans.append(f'<span class="w"><span id="{wid}" class="wi {klass}" data-layout-allow-overlap>{esc(token)}</span></span>')
            rows.append(f'<div id="{self.id}-l{li}" class="hero-line">{" ".join(spans)}</div>')
        align = g.get("align", "center")
        if variant == "card":
            inner = (f'<div class="hero-cardwrap" style="text-align:{align}"><div id="{self.id}-card" class="hero-card" '
                     f'style="font-size:{self.px(size)}">{"".join(rows)}</div></div>')
        elif variant == "split":
            inner = (f'<div class="hero hero-split" data-layout-allow-overlap style="font-size:{self.px(size)};text-align:{align}">'
                     f'{rows[0]}<i id="{self.id}-bar" class="hero-bar" data-layout-ignore></i>{rows[1]}</div>')
        elif variant == "slam":
            inner = (f'<div class="hero hero-slam" data-layout-allow-overlap style="font-size:{self.px(size)};text-align:{align}">'
                     f'<i id="{self.id}-ring" class="hero-ring" data-layout-ignore></i>{"".join(rows)}</div>')
        else:
            klass = "hero-outline" if variant == "outline" else "hero-stack"
            inner = f'<div class="hero {klass}" data-layout-allow-overlap style="font-size:{self.px(size)};text-align:{align}">{"".join(rows)}</div>'
        markup = self.wrap(inner)
        times = word_times(self, tokens) if g.get("sync", "spoken") == "spoken" else [
            self.start + i * .07 for i in range(len(tokens))]
        getattr(self, f"_{'stack' if variant == 'depth' else variant}")(ids, accent_ids, times, k)
        # One pop when the graphic first lands; the key word of a slam can carry a restrained impact.
        first = self.start if variant == "card" or not times else times[0]
        if variant == "slam" and g.get("impact"):
            self.sound("reveal", self._key_time(ids, accent_ids, times))
        else:
            self.sfx(first)
        if g.get("float", True) and self.hold() > 1.4 and variant != "card":
            self.a(f'tl.fromTo("#{self.id}-float",{{y:0}},{{y:{-12 * k:.1f},duration:{self.hold():.3f},ease:"sine.inOut"}},{self.start:.4f});')
        return markup, self.anims

    # --- variants -------------------------------------------------------------
    def _kill(self, targets):
        if self.end < self.ctx.duration - 1.5 / self.ctx.fps:
            self.a(f'tl.set({js(targets)},{{opacity:0}},{self.end:.4f});')
            return True
        return False

    def _glow(self, wid, at, k, out=None):
        dur = .4 if out is None else max(.08, min(.4, out - at - .08))
        self.a(f'tl.fromTo("#{wid}",{{textShadow:"0 0 0px rgba(73,207,38,0)"}},{{textShadow:"0 0 {30 * k:.0f}px rgba(73,207,38,.65), 0 0 {70 * k:.0f}px rgba(73,207,38,.3)",'
               f'duration:{dur:.3f},ease:"power2.out",immediateRender:false}},{at + .06:.4f});')

    def _enter(self, at, out, wanted):
        """Entrance length that finishes before the exit begins."""
        return max(.1, min(wanted, out - at - .01))

    def _timing(self, times, exit_len, count=1, stagger=0.0):
        """Words land before the exit; the exit starts once the last word has landed and
        (with its stagger) finishes inside the graphic."""
        last = max(times) if times else self.start
        out = max(self.start + .3, self.end - exit_len - stagger * (count - 1))
        if last + .3 > out:
            out = min(max(out, last + .3), self.end - .14)
        room = self.end - out - .02
        stagger = min(stagger, max(0.0, (room - .1) / max(1, count - 1))) if count > 1 else 0.0
        exit_len = max(.08, min(exit_len, room - stagger * (count - 1)))
        return [min(t, out - .12) for t in times], out, exit_len, stagger

    def _stack(self, ids, accent_ids, times, k):
        times, out, ex, stg = self._timing(times, .3, len(ids), .025)
        for wid, at in zip(ids, times):
            self.a(f'tl.fromTo("#{wid}",{{yPercent:118,rotation:5,opacity:0,filter:"blur(6px)"}},'
                   f'{{yPercent:0,rotation:0,opacity:1,filter:"blur(0px)",duration:{self._enter(at, out, .52):.3f},ease:"expo.out"}},{at:.4f});')
            if wid in accent_ids:
                self.a(f'tl.fromTo("#{wid}",{{scale:1.22}},{{scale:1,duration:{self._enter(at, out, .5):.3f},ease:"back.out(2.2)",immediateRender:false}},{at:.4f});')
                self._glow(wid, at, k, out)
        if self._kill(["#" + w for w in ids]):
            self.a(f'tl.to({js(["#" + w for w in ids])},{{yPercent:-118,opacity:0,duration:{ex:.3f},stagger:{stg:.3f},ease:"power3.in"}},{out:.4f});')

    def _key_time(self, ids, accent_ids, times):
        key = accent_ids[0] if accent_ids else max(ids, key=len)
        return times[ids.index(key)]

    def _slam(self, ids, accent_ids, times, k):
        key = accent_ids[0] if accent_ids else ids[-1]
        times, out, ex, _ = self._timing(times, .28)
        key_at = times[ids.index(key)]
        for wid, at in zip(ids, times):
            if wid == key:
                self.a(f'tl.fromTo("#{wid}",{{scale:2.7,opacity:0,filter:"blur(22px)"}},'
                       f'{{scale:1,opacity:1,filter:"blur(0px)",duration:{self._enter(at, out, .46):.3f},ease:"back.out(1.35)"}},{at:.4f});')
                self._glow(wid, at, k, out)
            else:
                self.a(f'tl.fromTo("#{wid}",{{yPercent:60,opacity:0}},{{yPercent:0,opacity:1,duration:{self._enter(at, out, .34):.3f},ease:"expo.out"}},{at:.4f});')
        ring = max(.15, min(.7, out - (key_at + .05) - .02))  # the ring finishes before the exit
        self.a(f'tl.fromTo("#{self.id}-ring",{{scale:.2,opacity:.85}},{{scale:2.6,opacity:0,duration:{ring:.3f},ease:"power2.out"}},{key_at + .05:.4f});')
        self.a(f'tl.set("#{self.id}-ring",{{opacity:0}},{key_at + .05 + ring:.4f});')
        # A small frame kick sells the weight of the landing (restrained: 6 design px).
        if key_at + .26 < out:
            self.a(f'tl.fromTo("#{self.body}",{{x:0,y:0}},{{keyframes:[{{x:{-6 * k:.1f},y:{4 * k:.1f},duration:.05}},{{x:{5 * k:.1f},y:{-3 * k:.1f},duration:.05}},{{x:0,y:0,duration:.08}}]}},{key_at + .08:.4f});')
        if self._kill(["#" + w for w in ids] + [f"#{self.id}-ring"]):
            self.a(f'tl.to({js(["#" + w for w in ids])},{{scale:.86,opacity:0,filter:"blur(12px)",duration:{ex:.3f},ease:"power3.in"}},{out:.4f});')

    def _split(self, ids, accent_ids, times, k):
        first_line = [w for w in ids if w in self._line_ids(0)]
        times, out, ex, _ = self._timing(times, .3)
        t1 = times[0]
        t2 = times[len(first_line)] if len(times) > len(first_line) else min(t1 + .25, out - .15)
        self.a(f'tl.fromTo("#{self.id}-l0",{{x:{-190 * k:.1f},opacity:0,filter:"blur(12px)"}},{{x:0,opacity:1,filter:"blur(0px)",duration:{self._enter(t1, out, .55):.3f},ease:"expo.out"}},{t1:.4f});')
        self.a(f'tl.fromTo("#{self.id}-l1",{{x:{190 * k:.1f},opacity:0,filter:"blur(12px)"}},{{x:0,opacity:1,filter:"blur(0px)",duration:{self._enter(t2, out, .55):.3f},ease:"expo.out"}},{t2:.4f});')
        bar_at = min(t1 + .12, out - .12)
        self.a(f'tl.fromTo("#{self.id}-bar",{{scaleX:0}},{{scaleX:1,duration:{self._enter(bar_at, out, .5):.3f},ease:"expo.inOut"}},{bar_at:.4f});')
        for wid in accent_ids:
            at = times[ids.index(wid)]
            self.a(f'tl.fromTo("#{wid}",{{scale:1.18}},{{scale:1,duration:{self._enter(at, out, .45):.3f},ease:"back.out(2)",immediateRender:false}},{at:.4f});')
            self._glow(wid, at, k, out)
        if self._kill([f"#{self.id}-l0", f"#{self.id}-l1", f"#{self.id}-bar"]):
            self.a(f'tl.to("#{self.id}-l0",{{x:{-150 * k:.1f},opacity:0,duration:{ex:.3f},ease:"power3.in"}},{out:.4f});')
            self.a(f'tl.to("#{self.id}-l1",{{x:{150 * k:.1f},opacity:0,duration:{ex:.3f},ease:"power3.in"}},{out:.4f});')
            self.a(f'tl.to("#{self.id}-bar",{{scaleX:0,duration:{min(ex, .25):.3f},ease:"power3.in"}},{out:.4f});')

    def _line_ids(self, index):
        lines = [str(line) for line in (self.g.get("lines") or [self.g.get("text", "")])]
        count_before = sum(len(line.split()) for line in lines[:index])
        return {f"{self.id}-w{count_before + i}" for i in range(len(lines[index].split()))}

    def _outline(self, ids, accent_ids, times, k):
        times, out, ex, stg = self._timing(times, .26, len(ids), .02)
        for wid, at in zip(ids, times):
            self.a(f'tl.fromTo("#{wid}",{{yPercent:70,opacity:0}},{{yPercent:0,opacity:1,duration:{self._enter(at, out, .45):.3f},ease:"expo.out"}},{at:.4f});')
        for wid in accent_ids:
            at = min(times[ids.index(wid)] + .12, out - .12)
            self.a(f'tl.fromTo("#{wid}-fill",{{clipPath:"inset(0% 100% 0% 0%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:{self._enter(at, out, .42):.3f},ease:"power2.inOut"}},{at:.4f});')
        if self._kill(["#" + w for w in ids]):
            self.a(f'tl.to({js(["#" + w for w in ids])},{{yPercent:-60,opacity:0,duration:{ex:.3f},stagger:{stg:.3f},ease:"power3.in"}},{out:.4f});')

    def _card(self, ids, accent_ids, times, k):
        # A short card still lands fully before it leaves: entrance, marker and exit never overlap.
        out = max(self.start + .3, self.end - .24)
        land = self._enter(self.start, out, .48)
        self.a(f'tl.fromTo("#{self.id}-card",{{scale:.55,rotation:-5,opacity:0}},{{scale:1,rotation:0,opacity:1,duration:{land:.3f},ease:"back.out(1.9)"}},{self.start:.4f});')
        for wid in accent_ids:
            at = times[ids.index(wid)]
            if not self.start + .2 <= at <= min(self.end - .5, out - .12):
                at = min(self.start + .35, out - .12)  # unspoken accents mark right after the land
            self.a(f'tl.fromTo("#{wid} > i",{{scaleX:0}},{{scaleX:1,duration:{max(.08, min(.34, out - at - .02)):.3f},ease:"power2.out"}},{at:.4f});')
        if self._kill([f"#{self.id}-card"]):
            self.a(f'tl.to("#{self.id}-card",{{scale:.82,opacity:0,duration:{max(.08, min(.22, self.end - out - .01)):.3f},ease:"power3.in"}},{out:.4f});')


class Tag(Component):
    """Callout pills that land on their words; optional leader line to a point of interest.

    items: [{"text", "icon", "at"}] stack vertically (or one pill from text/icon/at).
    anchor: [x, y] frame percent the first pill points to with a drawn line and a pulse dot.
    """
    kind = "tag"
    default_region = "center"
    default_enter = "pop"
    default_exit = "fade"
    default_sfx = "popup"

    def __init__(self, spec, index, ctx):
        spec = dict(spec)
        self.pos = (num(spec.get("x", 8), "tag x", 0, 100), num(spec.get("y", 48), "tag y", 0, 100))
        spec.update({"x": 0, "y": 0, "w": 100, "h": 100})
        super().__init__(spec, index, ctx)

    def meta_box(self):
        items = self.g.get("items") or [{"text": self.g.get("text", "")}]
        size = float(self.g.get("size", 44))
        longest = max(len(str(it.get("text", ""))) for it in items)
        w = min(100.0, (longest * size * .55 + 150) / 10.8)
        h = len(items) * (size * 1.9 + 16) / 19.2
        x, y = self.pos
        return [x if self.g.get("align", "left") == "left" else x - w, y, w, h]

    def render(self):
        g = self.g
        from icons import icon_svg
        items = g.get("items") or [{"text": g.get("text", ""), "icon": g.get("icon"), "at": g.get("at")}]
        if not items or not all(str(it.get("text", "")).strip() for it in items):
            raise ValueError(f"{self.id} needs text or items with text")
        k = self.px.n(1)
        size = num(g.get("size", 44), f"{self.id} size", 30, 90)
        align = g.get("align", "left")
        x, y = self.pos
        rows = []
        for i, item in enumerate(items):
            icon = f'<span class="tg-ico">{icon_svg(item["icon"])}</span>' if item.get("icon") else ""
            tone = " tg-win" if item.get("tone") == "win" else ""
            rows.append(f'<div id="{self.id}-r{i}" class="tg-row{tone}">{icon}<span class="tg-txt">{esc(item["text"])}</span></div>')
        side = "right:auto;left" if align == "left" else "left:auto;right"
        place = f"{side}:{x if align == 'left' else 100 - x:.2f}%;top:{y:.2f}%"
        line = ""
        anchor = g.get("anchor")
        if anchor:
            ax, ay = num(anchor[0], "anchor x", 0, 100), num(anchor[1], "anchor y", 0, 100)
            sx = x + (1 if align == "left" else -1) * 2
            sy = y + 2.3
            w, h = self.ctx.width, self.ctx.height
            line = (f'<svg class="tg-lead" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
                    f'<path id="{self.id}-lead" d="M{sx * w / 100:.1f} {sy * h / 100:.1f} L{ax * w / 100:.1f} {ay * h / 100:.1f}"/>'
                    f'<circle id="{self.id}-dot" cx="{ax * w / 100:.1f}" cy="{ay * h / 100:.1f}" r="{9 * k:.1f}"/></svg>')
        inner = (f'<div class="tg" data-layout-allow-overflow>{line}<div class="tg-col tg-{align}" style="{place};font-size:{self.px(size)}">'
                 f'{"".join(rows)}</div></div>')
        markup = self.wrap(inner)
        for i, item in enumerate(items):
            at = self.cue(item.get("at"), f"item {i} at", self.start + i * .25)
            self.a(f'tl.fromTo("#{self.id}-r{i}",{{opacity:0,scale:.6,x:{(-30 if align == "left" else 30) * k:.1f}}},'
                   f'{{opacity:1,scale:1,x:0,duration:.42,ease:"back.out(1.9)"}},{at:.4f});')
            self.sound("popup", at)
            if i == 0 and anchor:
                self.a(f'tl.fromTo("#{self.id}-lead",{{drawSVG:"0%"}},{{drawSVG:"100%",duration:.4,ease:"power2.inOut"}},{at + .18:.4f});')
                self.a(f'tl.fromTo("#{self.id}-dot",{{scale:0,transformOrigin:"50% 50%"}},{{scale:1,duration:.3,ease:"back.out(3)"}},{at + .5:.4f});')
            if item.get("tone") == "win":
                win = self.cue(item.get("win_at", item.get("at")), f"item {i} win_at", at)
                self.a(f'tl.to("#{self.id}-r{i}",{{boxShadow:"0 0 {40 * k:.0f}px rgba(73,207,38,.55)",borderColor:"rgba(73,207,38,.8)",duration:.3}},{win + .1:.4f});')
        self.exit_anim(f"#{self.id} .tg")
        return markup, self.anims


class Reveal(Component):
    """Closing payoff: the result rises in 2.5D onto a lit card with a reflection and a
    word-synced title, a light sweep crosses it, and a few particles drift up. Built for
    a result the viewer should remember; the media is the real capture or an authored still."""
    kind = "reveal"
    default_region = "center"
    default_enter = "none"
    default_exit = "fade"
    default_sfx = "reveal"
    caption_default = "hide"
    showpiece_variants = ("tilt", "float", "phone")

    def __init__(self, spec, index, ctx):
        spec = dict(spec)
        spec.update({"x": 0, "y": 0, "w": 100, "h": 100})
        spec.setdefault("variant", "tilt")
        super().__init__(spec, index, ctx)

    def showpiece(self):
        return True

    def render(self):
        g = self.g
        media = g.get("media")
        if not media:
            raise ValueError(f"{self.id} needs media (the result to reveal)")
        path = self.ctx.media(media)
        image = path.lower().rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "webp", "svg", "avif"}
        k = self.px.n(1)
        W, H = self.ctx.width, self.ctx.height
        variant = g.get("variant", "tilt")
        if variant not in ("tilt", "float", "phone"):
            raise ValueError(f"{self.id} variant must be tilt, float or phone")
        aspect = num(g.get("aspect", .62 if variant == "phone" else .78), f"{self.id} aspect", .3, 2.5)
        card_w = num(g.get("card_w", 70 if variant == "phone" else 80), f"{self.id} card_w", 30, 96)
        # Keep the card to about half the frame height so the title and reflection both read.
        card_w = min(card_w, num(g.get("card_h_max", 52), f"{self.id} card_h_max", 20, 80) / 100 * H * aspect / W * 100)
        card_px_w = W * card_w / 100
        card_px_h = card_px_w / aspect
        top = num(g.get("card_y", 30), f"{self.id} card_y", 5, 70)
        position = g.get("position", "50% 0%")
        media_start = num(g.get("media_start", 0), f"{self.id} media_start", 0)

        def media_tag(extra_id, klass):
            if image:
                return f'<img id="{self.id}-{extra_id}" class="{klass}" src="{esc(path)}" style="object-position:{esc(position)}">'
            return (f'<video id="{self.id}-{extra_id}" class="clip {klass}" src="{esc(path)}" data-start="{self.start:.4f}" '
                    f'data-duration="{self.end - self.start:.4f}" data-media-start="{media_start:.3f}" muted playsinline '
                    f'style="object-position:{esc(position)}"></video>')

        backdrop = g.get("backdrop", "media_blur")
        back = ""
        still_at = media_start + num(g.get("still_at", 1.0), f"{self.id} still_at", 0)
        if backdrop == "media_blur":
            blurred = self.ctx.still(path, still_at, 26)
            back = f'<div id="{self.id}-back" class="rv-back"><img class="rv-back-media" src="{esc(blurred)}"><i class="rv-dim"></i></div>'
        elif backdrop == "dark":
            back = f'<div id="{self.id}-back" class="rv-back rv-dark"></div>'
        elif backdrop != "none":
            raise ValueError(f"{self.id} backdrop must be media_blur, dark or none")
        title = str(g.get("title", "")).strip()
        accent = {a.casefold().strip(".,!?;:\"'") for a in g.get("accent_words", [])}
        tokens = title.split()
        ids = [f"{self.id}-t{i}" for i in range(len(tokens))]
        title_html = ""
        if tokens:
            spans = [f'<span class="w"><span id="{wid}" class="wi {"hero-accent" if t.casefold().strip(".,!?;:") in accent else ""}">{esc(t)}</span></span>'
                     for wid, t in zip(ids, tokens)]
            tsize = fit_size([title], num(g.get("title_size", 104), f"{self.id} title_size", 40, 200), W * .88 * 1080 / W, 64)
            title_html = f'<div id="{self.id}-title" class="rv-title" style="font-size:{self.px(tsize)}">{" ".join(spans)}</div>'
        count = int(num(g.get("particles", 18), f"{self.id} particles", 0, 40))
        dots = []
        for i in range(count):
            # Deterministic, well-spread positions (golden-ratio sequence) around the card.
            u = (i * 0.61803398875) % 1
            v = (i * 0.41421356237 + .17) % 1
            size = (3 + (i * 7) % 5) * k
            dots.append(f'<i id="{self.id}-p{i}" class="rv-pt" style="left:{6 + u * 88:.2f}%;top:{top + 6 + v * 60:.2f}%;'
                        f'width:{size:.1f}px;height:{size:.1f}px"></i>')
        radius = (48 if variant == "phone" else 30) * k
        card = (f'<div class="rv-stage" style="top:{top:.2f}%;width:{card_px_w:.1f}px;height:{card_px_h:.1f}px;margin-left:{-card_px_w / 2:.1f}px">'
                f'<div id="{self.id}-card" class="rv-card" style="border-radius:{radius:.1f}px">{media_tag("media", "rv-media")}'
                f'<i id="{self.id}-sweep" class="rv-sweep" data-layout-ignore></i></div>'
                f'<div id="{self.id}-reflect" class="rv-reflect" style="border-radius:{radius:.1f}px">'
                f'<img class="rv-media" src="{esc(self.ctx.still(path, still_at))}" style="object-position:{esc(position)}"></div></div>')
        inner = (f'<div class="rv" data-layout-allow-overflow>{back}<i id="{self.id}-glow" class="rv-glow" data-layout-ignore style="top:{top + 12:.1f}%"></i>'
                 f'{title_html}{card}<div class="rv-pts" data-layout-ignore>{"".join(dots)}</div></div>')
        markup = self.wrap(inner, timed=image)
        s = self.start
        land = s + .75
        if back:
            self.a(f'tl.fromTo("#{self.id}-back",{{opacity:0,scale:1.12}},{{opacity:1,scale:1,duration:.6,ease:"power2.out"}},{s:.4f});')
        self.a(f'tl.fromTo("#{self.id}-glow",{{opacity:0,scale:.6}},{{opacity:1,scale:1,duration:1.1,ease:"power2.out"}},{s + .2:.4f});')
        tilt = 16 if variant == "tilt" else 6
        self.a(f'tl.fromTo("#{self.id}-card",{{yPercent:55,rotationX:48,rotationY:-8,scale:.78,opacity:0,transformPerspective:{1500 * k:.0f}}},'
               f'{{yPercent:0,rotationX:{tilt},rotationY:-4,scale:1,opacity:1,duration:.95,ease:"expo.out"}},{s + .05:.4f});')
        self.a(f'tl.fromTo("#{self.id}-reflect",{{opacity:0}},{{opacity:.26,duration:.8,ease:"power2.out"}},{s + .35:.4f});')
        # The card keeps settling in depth over the hold so the payoff never freezes.
        settle = s + 1.02  # after the rise completes, so the two tweens never fight
        if self.end - settle > .4:
            self.a(f'tl.to("#{self.id}-card",{{rotationX:{max(2, tilt - 10)},rotationY:3,duration:{self.end - settle:.3f},ease:"sine.inOut"}},{settle:.4f});')
        self.a(f'tl.fromTo("#{self.id}-sweep",{{xPercent:-160}},{{xPercent:160,duration:.9,ease:"power2.inOut"}},{land - .1:.4f});')
        if tokens:
            times = word_times(self, tokens) if g.get("sync", "spoken") == "spoken" else [s + .5 + i * .08 for i in range(len(tokens))]
            for wid, at in zip(ids, times):
                self.a(f'tl.fromTo("#{wid}",{{yPercent:118,opacity:0}},{{yPercent:0,opacity:1,duration:.5,ease:"expo.out"}},{at:.4f});')
            self.a(f'tl.fromTo("#{self.id}-title",{{y:0}},{{y:{-14 * k:.1f},duration:{max(.5, self.end - s):.3f},ease:"sine.inOut"}},{s:.4f});')
        for i in range(count):
            at = s + .5 + (i % 9) * .17
            rise = (70 + (i * 37) % 90) * k
            life = 1.6 + (i % 5) * .25
            self.a(f'tl.fromTo("#{self.id}-p{i}",{{y:0,opacity:0}},{{keyframes:[{{opacity:.85,y:{-rise * .35:.1f},duration:{life * .35:.2f}}},'
                   f'{{opacity:0,y:{-rise:.1f},duration:{life * .65:.2f}}}],ease:"none"}},{min(at, self.end - .4):.4f});')
        self.sound("reveal", land - .3)
        self.exit_anim(f"#{self.id} .rv")
        return markup, self.anims


class Particles(Component):
    """Restrained drifting glints over a region for a showpiece beat."""
    kind = "particles"
    default_region = "center"
    default_enter = "none"
    default_exit = "none"
    default_sfx = None

    def showpiece(self):
        return True

    def render(self):
        g = self.g
        k = self.px.n(1)
        count = int(num(g.get("count", 22), f"{self.id} count", 4, 60))
        color = g.get("color", "accent")
        tone = "var(--accent)" if color == "accent" else "#ffffff"
        dots = []
        for i in range(count):
            u = (i * 0.61803398875) % 1
            v = (i * 0.7548776662 + .1) % 1
            size = (3 + (i * 5) % 6) * k
            dots.append(f'<i id="{self.id}-p{i}" class="pt-dot" style="left:{u * 100:.2f}%;top:{v * 100:.2f}%;width:{size:.1f}px;height:{size:.1f}px;'
                        f'background:{tone};box-shadow:0 0 {10 * k:.0f}px {tone}"></i>')
        markup = self.wrap(f'<div class="pt" data-layout-ignore>{"".join(dots)}</div>')
        span = self.hold()
        for i in range(count):
            at = self.start + (i % 11) * min(.2, span / 14)
            life = min(span - (at - self.start), 1.4 + (i % 4) * .3)
            if life <= .2:
                continue
            self.a(f'tl.fromTo("#{self.id}-p{i}",{{y:0,opacity:0,scale:.6}},{{keyframes:[{{opacity:.9,scale:1,y:{-30 * k:.1f},duration:{life * .3:.2f}}},'
                   f'{{opacity:0,y:{-(90 + (i * 23) % 80) * k:.1f},duration:{life * .7:.2f}}}],ease:"none"}},{at:.4f});')
        return markup, self.anims


NEW_COMPONENTS = {cls.kind: cls for cls in (Hero, Tag, Reveal, Particles)}
_components.COMPONENTS.update(NEW_COMPONENTS)


def motion_css(px):
    return f"""
.hero{{font-family:var(--display);font-weight:900;letter-spacing:-.045em;line-height:.98;color:var(--text);
  text-shadow:0 {px(6)} {px(26)} rgba(0,0,0,.55)}}
.hero-line{{display:block}}
.hero-accent{{color:var(--accent)}}
.hero-slam .hero-line:last-child{{font-size:1.28em}}
.hero-ring{{position:absolute;left:50%;top:55%;width:{px(360)};height:{px(360)};margin:{px(-180)} 0 0 {px(-180)};border-radius:50%;
  border:{px(5)} solid var(--accent);box-shadow:0 0 {px(40)} rgba(73,207,38,.6),inset 0 0 {px(30)} rgba(73,207,38,.4);opacity:0;pointer-events:none}}
.hero-split .hero-line:first-child{{text-align:left}} .hero-split .hero-line:last-child{{text-align:right}}
.hero-bar{{display:block;height:{px(10)};margin:{px(14)} 12% {px(18)};border-radius:{px(6)};background:var(--accent);
  box-shadow:0 0 {px(26)} rgba(73,207,38,.6);transform-origin:50% 50%}}
.hero-outline .ho-w{{position:relative;color:rgba(255,255,255,.16);-webkit-text-stroke:{px(3.2)} #fff;text-shadow:0 {px(4)} {px(22)} rgba(0,0,0,.45)}}
.ho-fill{{position:absolute;left:0;top:0;color:var(--accent);-webkit-text-stroke:0;clip-path:inset(0% 100% 0% 0%);
  text-shadow:0 0 {px(30)} rgba(73,207,38,.55)}}
.hero-cardwrap{{width:100%}}
.hero-card{{display:inline-block;max-width:100%;background:var(--card-light);color:var(--card-light-ink);font-family:var(--display);
  font-weight:800;letter-spacing:-.02em;line-height:1.14;padding:.42em .62em .48em;border-radius:.42em;text-align:center;
  box-shadow:0 {px(18)} {px(50)} rgba(0,0,0,.45)}}
.hc-w{{position:relative;display:inline-block}}
.hc-mark{{z-index:0}} .hc-mark>i{{position:absolute;left:-.08em;right:-.08em;top:.12em;bottom:.02em;background:var(--accent);
  border-radius:.14em;z-index:-1;transform-origin:0 50%}}
.tg{{position:absolute;inset:0}}
.tg-col{{position:absolute;display:flex;flex-direction:column;gap:{px(16)}}} .tg-left{{align-items:flex-start}} .tg-right{{align-items:flex-end}}
.tg-row{{display:inline-flex;align-items:center;gap:{px(16)};padding:{px(16)} {px(30)} {px(16)} {px(18)};border-radius:999px;
  background:var(--panel-solid);border:{px(2)} solid var(--line);font-family:var(--display);font-weight:800;letter-spacing:-.02em;
  color:var(--text);box-shadow:0 {px(14)} {px(40)} rgba(0,0,0,.5);white-space:nowrap}}
.tg-ico{{width:1.35em;height:1.35em;border-radius:50%;display:grid;place-items:center;background:rgba(73,207,38,.16);color:var(--accent)}}
.tg-ico svg{{width:62%;height:62%}}
.tg-win{{border-color:rgba(73,207,38,.5)}}
.tg-lead{{position:absolute;inset:0;width:100%;height:100%;overflow:visible}}
.tg-lead path{{fill:none;stroke:rgba(255,255,255,.75);stroke-width:{px(3)};stroke-linecap:round}}
.tg-lead circle{{fill:var(--accent);filter:drop-shadow(0 0 {px(10)} rgba(73,207,38,.8))}}
.rv{{position:absolute;inset:0;overflow:hidden}}
.rv-back{{position:absolute;inset:-6%;}} .rv-back-media{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.rv-dim{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 45%,rgba(5,7,6,.55),rgba(5,7,6,.9) 75%)}}
.rv-dark{{background:var(--canvas)}}
.rv-glow{{position:absolute;left:50%;width:{px(900)};height:{px(900)};margin-left:{px(-450)};border-radius:50%;
  background:radial-gradient(closest-side,rgba(73,207,38,.28),rgba(73,207,38,0));pointer-events:none}}
.rv-title{{position:absolute;left:6%;right:6%;top:9%;text-align:center;font-family:var(--display);font-weight:900;letter-spacing:-.045em;
  line-height:.98;color:var(--text);text-shadow:0 {px(8)} {px(30)} rgba(0,0,0,.6)}}
.rv-stage{{position:absolute;left:50%;perspective:{px(1500)}}}
.rv-card{{position:absolute;inset:0;overflow:hidden;transform-style:preserve-3d;background:#111;
  box-shadow:0 {px(60)} {px(120)} rgba(0,0,0,.65),0 0 0 {px(2)} rgba(255,255,255,.14)}}
.rv-media{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.rv-sweep{{position:absolute;top:-20%;bottom:-20%;left:30%;width:40%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.28) 45%,rgba(255,255,255,.05) 60%,transparent);
  mix-blend-mode:screen;transform:skewX(-14deg)}}
.rv-reflect{{position:absolute;left:0;right:0;top:100%;height:100%;margin-top:{px(14)};overflow:hidden;transform:scaleY(-1);opacity:0;
  -webkit-mask-image:linear-gradient(0deg,rgba(0,0,0,.55),transparent 38%);mask-image:linear-gradient(0deg,rgba(0,0,0,.55),transparent 38%)}}
.rv-pts,.pt{{position:absolute;inset:0;pointer-events:none}}
.rv-pt,.pt-dot{{position:absolute;border-radius:50%;opacity:0}}
.rv-pt{{background:#e9ffe2;box-shadow:0 0 {px(12)} rgba(73,207,38,.9)}}
"""


# ---------------------------------------------------------------------------
# Full-frame screen detail shot (layout "screen")

def screen_markup(shot, i, start, end, ctx, path, is_image, width, height):
    """A real capture on a 2.5D plane over its own blurred backdrop. ``focus`` keyframes
    frame a region of the capture on a spoken word; ``highlights`` ride on the plane so
    they stay locked to the UI while the camera moves. Returns (markup, animations)."""
    k = width / 1080
    aspect = num(shot.get("aspect", 9 / 16), f"shot {i} aspect", .3, 3)  # capture width / height
    plane_w = width * num(shot.get("plane_w", 86), f"shot {i} plane_w", 40, 100) / 100
    plane_h = plane_w / aspect
    top = (height - plane_h) / 2
    media_start = num(shot.get("source_start", 0), f"shot {i} source_start", 0)
    position = shot.get("object_position", "50% 50%")
    timing = f'data-start="{start}" data-duration="{end - start}"'

    def media(klass, extra=""):
        if is_image:
            return f'<img class="{klass}" src="{esc(path)}" style="object-position:{esc(position)}{extra}">'
        return (f'<video id="scr-{i}-{klass}" class="clip {klass}" src="{esc(path)}" {timing} data-media-start="{media_start:.3f}" '
                f'data-track-index="2" muted playsinline style="object-position:{esc(position)}{extra}"></video>')

    marks = []
    anims = []
    for j, mark in enumerate(shot.get("highlights", [])):
        rx, ry, rw, rh = (num(v, f"shot {i} highlight rect", 0, 100) for v in mark["rect"])
        at = ctx.t(mark.get("at", start), f"shot {i} highlight {j} at", start)
        until = ctx.t(mark.get("end", end), f"shot {i} highlight {j} end", at) if mark.get("end") else end
        label = f'<span class="scr-lab">{esc(mark["label"])}</span>' if mark.get("label") else ""
        marks.append(f'<div id="scr-{i}-h{j}" class="scr-hl" style="left:{rx}%;top:{ry}%;width:{rw}%;height:{rh}%">{label}</div>')
        anims.append(f'tl.fromTo("#scr-{i}-h{j}",{{opacity:0,scale:1.15}},{{opacity:1,scale:1,duration:.34,ease:"back.out(1.8)"}},{at:.4f});')
        if until < end - .05:
            anims.append(f'tl.to("#scr-{i}-h{j}",{{opacity:0,duration:.2}},{max(at + .4, until - .2):.4f});')
        ctx.sound("popup_soft", at, None, f"shot-{i}-highlight")
    tilt = shot.get("tilt", [10, -8])
    backdrop = shot.get("backdrop", "blur")
    back = ""
    if backdrop == "blur":
        blurred = ctx.still(path, media_start + .5, 26)
        back = f'<div class="scr-back" data-layout-ignore><img class="scr-back-media" src="{esc(blurred)}"><i class="scr-dim"></i></div>'
    elif backdrop == "dark":
        back = '<div class="scr-back scr-dark"></div>'
    plane = (f'<div class="scr-stage" style="perspective:{1700 * k:.0f}px"><div id="scr-{i}-plane" class="scr-plane" '
             f'style="left:{(width - plane_w) / 2:.1f}px;top:{top:.1f}px;width:{plane_w:.1f}px;height:{plane_h:.1f}px">'
             f'{media("scr-media")}{"".join(marks)}<i id="scr-{i}-sweep" class="scr-sweep" data-layout-ignore></i></div></div>')
    markup = f'<div class="scr" style="width:{width}px;height:{height}px">{back}{plane}</div>'

    def framing(rect, anchor_y=.46):
        rx, ry, rw, rh = rect
        fill = num(shot.get("fill", .92), f"shot {i} fill", .4, 1.6)
        s = min(fill * width / (plane_w * rw / 100), .82 * height / (plane_h * rh / 100))
        s = max(.6, min(6.0, s))
        cx = (rx + rw / 2) / 100 * plane_w - plane_w / 2
        cy = (ry + rh / 2) / 100 * plane_h - plane_h / 2
        return s, -cx * s, (anchor_y - .5) * height - cy * s

    ease = shot.get("focus_ease", "expo.inOut")
    base_tilt = [num(tilt[0], "tilt x", -40, 40), num(tilt[1], "tilt y", -40, 40)]
    anims.append(f'tl.fromTo("#scr-{i}-plane",{{rotationX:{base_tilt[0] + 14},rotationY:{base_tilt[1] - 10},scale:.86,y:{80 * k:.1f},opacity:0}},'
                 f'{{rotationX:{base_tilt[0]},rotationY:{base_tilt[1]},scale:1,y:0,opacity:1,duration:.6,ease:"expo.out"}},{start:.4f});')
    free = start + .62  # focus moves begin once the plane has landed, and never overlap each other
    for j, key in enumerate(shot.get("focus", [])):
        at = max(free, ctx.t(key["at"], f"shot {i} focus {j} at", start))
        s, x, y = framing([num(v, f"shot {i} focus rect", 0, 100) for v in key["rect"]], num(key.get("anchor_y", .46), "anchor_y", .2, .8))
        kt = key.get("tilt", [base_tilt[0] * .3, base_tilt[1] * .3])
        dur = num(key.get("duration", .7), f"shot {i} focus duration", .05, 4)
        if at >= end - .1:
            continue
        dur = min(dur, max(.05, end - .05 - at))
        anims.append(f'tl.to("#scr-{i}-plane",{{scale:{s:.3f},x:{x:.1f},y:{y:.1f},rotationX:{num(kt[0], "tilt", -40, 40)},'
                     f'rotationY:{num(kt[1], "tilt", -40, 40)},duration:{dur:.3f},ease:"{key.get("ease", ease)}"}},{at:.4f});')
        free = at + dur + .01
        if key.get("sfx", True) and j == 0:
            ctx.sound("travel", at, None, f"shot-{i}-focus")
    if shot.get("sweep", True):
        anims.append(f'tl.fromTo("#scr-{i}-sweep",{{xPercent:-170}},{{xPercent:170,duration:.9,ease:"power2.inOut"}},{start + .35:.4f});')
    return markup, anims


def screen_css(px):
    return f"""
.scr{{position:absolute;left:0;top:0;overflow:hidden;background:var(--canvas)}}
.scr-back{{position:absolute;inset:-8%}} .scr-back-media{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.scr-dim{{position:absolute;inset:0;background:radial-gradient(ellipse at 50% 45%,rgba(5,7,6,.45),rgba(5,7,6,.88) 78%)}}
.scr-dark{{background:var(--canvas)}}
.scr-stage{{position:absolute;inset:0}}
.scr-plane{{position:absolute;overflow:hidden;border-radius:{px(34)};background:#0d0f0e;transform-origin:50% 50%;
  box-shadow:0 {px(50)} {px(110)} rgba(0,0,0,.7),0 0 0 {px(2)} rgba(255,255,255,.12)}}
.scr-media{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.scr-hl{{position:absolute;border:{px(4)} solid var(--accent);border-radius:{px(14)};box-shadow:0 0 0 {px(2000)} rgba(0,0,0,.38),0 0 {px(26)} rgba(73,207,38,.55);opacity:0}}
.scr-lab{{position:absolute;left:0;top:calc(100% + {px(10)});white-space:nowrap;background:var(--accent);color:var(--accent-ink);
  font:800 {px(34)} var(--display);padding:{px(8)} {px(16)};border-radius:{px(10)}}}
.scr-sweep{{position:absolute;top:-20%;bottom:-20%;left:30%;width:36%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.22) 45%,rgba(255,255,255,.04) 62%,transparent);
  mix-blend-mode:screen;transform:skewX(-14deg);pointer-events:none}}
"""
