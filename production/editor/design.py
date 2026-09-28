"""Design tokens, bundled fonts and shared CSS for Brandon's stage motion system.

Every size is authored on a 1080-px-wide design grid and scaled to the output
width, so a 720x1280 proxy and a 1080x1920 final share the same layout.
"""
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent

DEFAULT_DESIGN = {
    "accent": "#49cf26",        # Brandon's requested accent (not sampled from a reference)
    "accent_ink": "#06140a",    # text placed on an accent box
    "text": "#ffffff",
    "text_2": "#d3dad5",
    "muted": "#8b958f",
    "negative": "#ff5d5d",       # restrained red for strikes and failed states only
    "warm": "#ffc53d",          # optional second highlight; needs a deliberate reason
    "canvas": "#050706",
    "panel": "rgba(15,19,17,0.90)",
    "panel_solid": "#0f1311",
    "line": "rgba(255,255,255,0.11)",
    "display_font": "Inter Tight",
    "serif_font": "Instrument Serif",
    "caption_font": "Archivo Black",
    "mono_font": "JetBrains Mono",
    "feel": "snap",
    "stage_backdrop": "dots",
}

# Timing personalities. Components read these instead of hard-coding eases so a
# reel can change feel without re-authoring every graphic.
FEELS = {
    "snap": {"pop": "back.out(1.7)", "enter": "expo.out", "exit": "power3.in", "move": "expo.inOut",
             "in": .46, "out": .26, "stagger": .055, "spring": "back.out(2.4)"},
    "glide": {"pop": "power3.out", "enter": "power3.out", "exit": "power2.in", "move": "power3.inOut",
              "in": .62, "out": .34, "stagger": .08, "spring": "back.out(1.3)"},
    "editorial": {"pop": "expo.out", "enter": "expo.out", "exit": "power3.in", "move": "expo.inOut",
                  "in": .72, "out": .38, "stagger": .045, "spring": "back.out(1.5)"},
}

FONT_FILES = {
    # family: [(package, file, weight, style)]
    "Inter Tight": [("inter-tight", f"inter-tight-latin-{w}-normal.woff2", w, "normal") for w in (500, 600, 700, 800, 900)]
                   + [("inter-tight", "inter-tight-latin-800-italic.woff2", 800, "italic")],
    "Instrument Serif": [("instrument-serif", "instrument-serif-latin-400-normal.woff2", 400, "normal"),
                         ("instrument-serif", "instrument-serif-latin-400-italic.woff2", 400, "italic")],
    "Archivo Black": [("archivo-black", "archivo-black-latin-400-normal.woff2", 400, "normal")],
    "JetBrains Mono": [("jetbrains-mono", f"jetbrains-mono-latin-{w}-normal.woff2", w, "normal") for w in (500, 700)],
}


def design_tokens(spec):
    design = dict(DEFAULT_DESIGN)
    supplied = spec.get("design", {})
    if not isinstance(supplied, dict):
        raise ValueError("design must be an object")
    unknown = set(supplied) - set(DEFAULT_DESIGN)
    if unknown:
        raise ValueError(f"unknown design keys: {', '.join(sorted(unknown))}")
    design.update(supplied)
    if design["feel"] not in FEELS:
        raise ValueError(f"design.feel must be one of {', '.join(FEELS)}")
    if design["stage_backdrop"] not in {"dots", "grid", "radial", "plain"}:
        raise ValueError("design.stage_backdrop must be dots, grid, radial or plain")
    return design


def install_fonts(assets):
    """Copy bundled OFL fonts into the composition so every machine renders the same type."""
    fonts = assets / "fonts"
    fonts.mkdir(exist_ok=True)
    faces, missing = [], []
    for family, files in FONT_FILES.items():
        for package, name, weight, style in files:
            source = HERE / "node_modules/@fontsource" / package / "files" / name
            if not source.is_file():
                missing.append(f"@fontsource/{package}/{name}")
                continue
            target = fonts / name
            if not target.exists():
                shutil.copy2(source, target)
            faces.append(f"@font-face{{font-family:'{family}';src:url('assets/fonts/{name}') format('woff2');"
                         f"font-weight:{weight};font-style:{style};font-display:block;}}")
        # The OFL travels with the font files it covers.
        license_file = HERE / "node_modules/@fontsource" / files[0][0] / "LICENSE"
        if license_file.is_file():
            shutil.copy2(license_file, fonts / f"{files[0][0]}-OFL.txt")
    if missing:
        raise ValueError("bundled fonts missing; run npm ci in production/editor: " + ", ".join(missing[:3]))
    return "".join(faces)


class Scale:
    """px(48) -> '32.00px' at 720 wide; all authored values use the 1080 grid."""

    def __init__(self, width, height):
        self.width, self.height = width, height
        self.k = width / 1080

    def __call__(self, value):
        return f"{float(value) * self.k:.2f}px"

    def n(self, value):
        return float(value) * self.k


def base_css(design, scale):
    px = scale
    d = design
    return f"""
:root{{--accent:{d['accent']};--accent-ink:{d['accent_ink']};--text:{d['text']};--text2:{d['text_2']};--muted:{d['muted']};
--negative:{d['negative']};--warm:{d['warm']};--canvas:{d['canvas']};--panel:{d['panel']};--panel-solid:{d['panel_solid']};--line:{d['line']};
--display:'{d['display_font']}','Inter Tight',Arial,sans-serif;--serif:'{d['serif_font']}',Georgia,serif;--mono:'{d['mono_font']}',Menlo,monospace;}}
#frame{{position:absolute;inset:0;overflow:hidden;transform-origin:50% 45%}}
.mg{{position:absolute;z-index:9;pointer-events:none;font-family:var(--display);color:var(--text);box-sizing:border-box}}
.mg *{{box-sizing:border-box}}
.mg.depth-behind{{z-index:3}}
.mg-scrim{{position:absolute;inset:-18% -14%;border-radius:50%;background:radial-gradient(closest-side,rgba(0,0,0,.62),rgba(0,0,0,.34) 55%,rgba(0,0,0,0) 100%);z-index:-1;opacity:0}}
.mg-scrim.band{{inset:-30% -40%;border-radius:0;background:linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,.58) 35%,rgba(0,0,0,.58) 65%,rgba(0,0,0,0))}}
.w{{display:inline-block;overflow:hidden;vertical-align:bottom;padding:0 .02em .06em;margin-bottom:-.06em}}
.wi{{display:inline-block;will-change:transform}}
.accent-c{{color:var(--accent)}}
.serif{{font-family:var(--serif);font-style:italic;font-weight:400;letter-spacing:-.01em}}
.ico{{display:inline-block;width:1em;height:1em;vertical-align:-.12em}}
.ico svg{{width:100%;height:100%;display:block}}
.glass{{background:var(--panel);border:{px(1.5)} solid var(--line);box-shadow:0 {px(22)} {px(60)} rgba(0,0,0,.55),inset 0 {px(1.5)} 0 rgba(255,255,255,.06);backdrop-filter:blur({px(16)}) saturate(1.2);-webkit-backdrop-filter:blur({px(16)}) saturate(1.2)}}
"""
