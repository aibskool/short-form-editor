"""Locate a callout in a screenshot and settle the pan on that box.

`target_text` is read with Tesseract. The box is stored as fractions of the
source image, and the pan ends with that box centered in the phone.
"""
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image


# Phone screen inside the default 1080x1920 stage (0.9 by 0.35, 8px pad).
DEFAULT_SCREEN = (956.0, 656.0)
_TOKEN = re.compile(r"[a-z0-9']+")
_OCR_CACHE = {}


def _tokens(text):
    return _TOKEN.findall(str(text).lower())


def _union(boxes):
    x0 = min(box["x"] for box in boxes)
    y0 = min(box["y"] for box in boxes)
    x1 = max(box["x"] + box["w"] for box in boxes)
    y1 = max(box["y"] + box["h"] for box in boxes)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def match_phrase(words, phrase):
    """Union of OCR words whose tokens equal `phrase`. Raises when it is missing or ambiguous."""
    needle = _tokens(phrase)
    if not needle:
        raise ValueError("target_text is empty")
    tokens = []
    for word in words:
        parts = _tokens(word.get("text", ""))
        for part in parts:
            tokens.append((part, word))
    hits = []
    last = len(tokens) - len(needle) + 1
    for index in range(max(0, last)):
        if [tokens[index + offset][0] for offset in range(len(needle))] != needle:
            continue
        used = []
        for offset in range(len(needle)):
            box = tokens[index + offset][1]
            if box not in used:
                used.append(box)
        hits.append(_union(used))
    if not hits:
        raise ValueError(f"target_text {phrase!r} was not found in the screenshot")
    unique = []
    for hit in hits:
        if not any(abs(hit["y"] - kept["y"]) < 0.01 and abs(hit["x"] - kept["x"]) < 0.01 for kept in unique):
            unique.append(hit)
    if len(unique) > 1:
        places = ", ".join(f"y={hit['y']:.2f}" for hit in unique)
        raise ValueError(f"target_text {phrase!r} matches more than once ({places}); use a longer phrase")
    return unique[0]


def _ocr_words(path):
    key = (str(path), Path(path).stat().st_mtime_ns, Path(path).stat().st_size)
    if key in _OCR_CACHE:
        return _OCR_CACHE[key]
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract is required to locate target_text on a screenshot")
    words = None
    error = None
    for psm in ("6", "3"):
        result = subprocess.run(
            ["tesseract", str(path), "stdout", "--psm", psm, "tsv"],
            text=True, capture_output=True, check=False)
        if result.returncode != 0:
            error = result.stderr[-500:]
            continue
        parsed = _parse_tsv(result.stdout, path)
        if parsed:
            words = parsed
            break
    if words is None:
        raise RuntimeError(f"tesseract could not read {path}: {error or 'no words'}")
    _OCR_CACHE[key] = words
    return words


def _parse_tsv(payload, path):
    with Image.open(path) as image:
        width, height = image.size
    words = []
    lines = payload.splitlines()
    if not lines:
        return words
    header = lines[0].split("\t")
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row.get("conf", "-1"))
            left, top = int(float(row["left"])), int(float(row["top"]))
            box_w, box_h = int(float(row["width"])), int(float(row["height"]))
        except (TypeError, ValueError):
            continue
        if confidence < 35 or box_w < 1 or box_h < 1:
            continue
        words.append({
            "text": text,
            "x": left / width, "y": top / height,
            "w": box_w / width, "h": box_h / height,
        })
    return words


def pad_box(box, image_size):
    """A little air so the stroke clears the glyphs."""
    width, height = image_size
    pad_x = max(6 / width, 0.012)
    pad_y = max(4 / height, box["h"] * 0.3)
    x0 = max(0.0, box["x"] - pad_x)
    y0 = max(0.0, box["y"] - pad_y)
    x1 = min(1.0, box["x"] + box["w"] + pad_x)
    y1 = min(1.0, box["y"] + box["h"] + pad_y)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _luma(pixel):
    red, green, blue = pixel[:3]
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def surface_box(path, text_box):
    """Grow a text box out to the card it sits on (heading, field, button).

    A row or column counts as outside once most of its pixels are far from the
    card color. Glyphs and a button on that card stay inside.
    """
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    pixels = image.load()
    x0 = max(0, min(width - 1, int(text_box["x"] * width)))
    y0 = max(0, min(height - 1, int(text_box["y"] * height)))
    x1 = max(x0 + 1, min(width, int((text_box["x"] + text_box["w"]) * width)))
    y1 = max(y0 + 1, min(height, int((text_box["y"] + text_box["h"]) * height)))
    samples = []
    for y in range(max(0, y0 - 14), y0):
        for x in range(x0, x1, 4):
            samples.append(_luma(pixels[x, y]))
    if not samples:
        samples.append(_luma(pixels[x0, y0]))
    card = sorted(samples)[len(samples) // 2]

    def far_fraction(samples_xy):
        if not samples_xy:
            return 1.0
        far = 0
        for x, y in samples_xy:
            if abs(_luma(pixels[x, y]) - card) > 80:
                far += 1
        return far / len(samples_xy)

    def row_outside(y):
        return far_fraction([(x, y) for x in range(0, width, 3)]) > 0.55

    top = y0
    while top > 0 and not row_outside(top - 1):
        top -= 1
    bottom = y1
    while bottom < height - 1 and not row_outside(bottom):
        bottom += 1

    def col_outside(x):
        return far_fraction([(x, y) for y in range(top, bottom, 3)]) > 0.55

    left = x0
    while left > 0 and not col_outside(left - 1):
        left -= 1
    right = x1
    while right < width - 1 and not col_outside(right):
        right += 1
    pad_x, pad_y = int(width * 0.006), int(height * 0.006)
    left, top = max(0, left - pad_x), max(0, top - pad_y)
    right, bottom = min(width, right + pad_x), min(height, bottom + pad_y)
    box = {"x": left / width, "y": top / height, "w": (right - left) / width, "h": (bottom - top) / height}
    # A region that swallows the page is not a card. Keep the words.
    if box["h"] > 0.55 or box["h"] < text_box["h"]:
        return pad_box(text_box, (width, height))
    return box


def locate_target(path, phrase, group="text"):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"screenshot for target_text {phrase!r} is missing: {path}")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError(f"target_text needs a still image, not {path.name}")
    words = _ocr_words(path)
    found = match_phrase(words, phrase)
    with Image.open(path) as image:
        image_size = image.size
    if group == "surface":
        box = surface_box(path, found)
    elif group in (None, "", "text"):
        box = pad_box(found, image_size)
    else:
        raise ValueError(f"unknown callout group {group!r}")
    return box


def frame_geometry(image_size, screen):
    """Pan height, as a percent of the phone, so image fractions match pan fractions.

    The screenshot is fit to the phone width. The phone then shows a vertical window.
    """
    image_w, image_h = image_size
    screen_w, screen_h = screen
    if image_w < 1 or image_h < 1 or screen_w < 1 or screen_h < 1:
        raise ValueError("screenshot and phone screen need a positive size")
    pan_h = screen_w * (image_h / image_w)
    if pan_h <= screen_h:
        return {"img_h": 100.0, "viewport_height": 1.0}
    return {"img_h": 100.0 * pan_h / screen_h, "viewport_height": screen_h / pan_h}


def settle_pan(box, viewport_height):
    """Scroll amount (0 top, 1 bottom) and the image fraction at the top of the phone.

    The target is centered, then shifted just enough to stay fully on screen.
    """
    viewport = min(1.0, max(0.05, float(viewport_height)))
    travel = max(0.0, 1.0 - viewport)
    center = float(box["y"]) + float(box["h"]) / 2
    top = center - viewport / 2
    if float(box["h"]) <= viewport:
        if float(box["y"]) < top:
            top = float(box["y"])
        if float(box["y"]) + float(box["h"]) > top + viewport:
            top = float(box["y"]) + float(box["h"]) - viewport
    top = min(max(top, 0.0), travel)
    scroll = (top / travel) if travel > 1e-6 else 0.0
    return round(scroll, 4), round(top, 4)


def box_in_viewport(block, frame, epsilon=0.015):
    """True when an image-space box lies fully inside the settled phone window."""
    if not isinstance(block, dict) or block.get("space") != "image":
        if not isinstance(block, dict) or "y" not in block:
            return True
        top, height = float(block.get("y", 0)), float(block.get("h", 0))
        left, width = float(block.get("x", 0)), float(block.get("w", 0))
    else:
        viewport = float((frame or {}).get("viewport_height") or 0)
        if viewport <= 0:
            return False
        origin = float(frame.get("viewport_top") or 0)
        top = (float(block["y"]) - origin) / viewport
        height = float(block["h"]) / viewport
        left, width = float(block["x"]), float(block["w"])
    return (top >= -epsilon and top + height <= 1 + epsilon
            and left >= -epsilon and left + width <= 1 + epsilon)


def place_targets(stage, screen=None):
    """Rewrite callout and highlight boxes from target_text, and aim the pan at them."""
    anchors = []
    for key in ("callout", "highlight"):
        block = stage.get(key)
        if not isinstance(block, dict) or not block.get("target_text"):
            continue
        if block.get("space") == "image" and stage.get("frame"):
            anchors.append(block)
            continue
        media = stage.get("media")
        box = locate_target(media, block["target_text"], block.get("group") or "text")
        block.update(box)
        block["space"] = "image"
        anchors.append(block)
    if not anchors:
        return None
    with Image.open(stage["media"]) as image:
        image_size = image.size
    frame = frame_geometry(image_size, screen or DEFAULT_SCREEN)
    anchor = _union(anchors)
    scroll_to, viewport_top = settle_pan(anchor, frame["viewport_height"])
    frame["viewport_top"] = viewport_top
    frame["scroll_to"] = scroll_to
    stage["frame"] = {key: round(float(value), 4) for key, value in frame.items()}
    scroll = stage.get("scroll") if isinstance(stage.get("scroll"), dict) else {}
    scroll = dict(scroll)
    scroll.setdefault("from", 0)
    scroll["to"] = scroll_to
    stage["scroll"] = scroll
    return stage["frame"]
