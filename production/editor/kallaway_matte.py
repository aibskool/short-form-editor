"""Person matte for the Kallaway split-screen head pop-out.

The speaker card keeps the normal footage. Above the card's top edge, only the
person is drawn, so the head and hands sit on the graphics. The matte is built
once per source video and reused.

Robust Video Matting (resnet50) runs offline at the source resolution. It is
recurrent, so the silhouette holds still from frame to frame. The composition
pass then steadies the edge band with optical flow, feathers it by 2-3 px,
pulls foliage green out of a 6 px band, drops specks under 200 px, and bakes
the same soft contact shadow. The result is a straight-alpha QuickTime on the
same frames as the picture.
"""
import hashlib
import json
import math
import os
import subprocess
import warnings
from pathlib import Path

import numpy as np
from scipy import ndimage

# Robust Video Matting resnet50 at half the encoder grid. The alpha is still
# the full frame. BiRefNet-general matched this edge on the 07 crown and the
# 09 foliage fringe after the same despill, and its worst crown stair was 1px
# against 2px here, but it is per-frame and about six times slower. This
# recurrent model is the default. downsample 0.25 softened the ear, so it is 0.5.
MODEL = "rvm-resnet50-fullres-d050-edge-v1"
CACHE = Path.home() / ".cache" / "kallaway-mattes"
# Kept for the anchor record. The split crop places the crown, not a fraction of the head.
POP_FRACTION = 0.32
POP_FLOOR = 0.22
POP_CAP = 0.42
# Source pixels added under the estimated jaw when a chin row is reported.
CHIN_PAD_PX = 28
# The hair clears the card by about this much. Kallaway's own split frames
# put only the crown above y 1408: median 70 px, and the take stays in 50-100.
CROWN_POP_TARGET_PX = 70
CROWN_POP_MIN_PX = 50
CROWN_POP_MAX_PX = 100
# Kallaway's face on the card is about this tall. Brandon films close, so the
# speaker is scaled down and a blurred cover of the same frame fills the card.
FACE_TARGET_PX = 215
FACE_MIN_PX = 200
FACE_MAX_PX = 230
# Sigma is in card pixels. 25-40 reads as shallow depth of field, not a smear.
PLATE_SIGMA = 32.0
PLATE_DARKEN = 0.12
# Edge darkening on the plate, so a shoulder fade reads as depth.
PLATE_VIGNETTE = 0.12
# How much of the live background, with the speaker already removed, comes back.
PLATE_MOTION = 0.60
# Source pixels the person mask grows before a pixel may enter the plate.
PLATE_DILATE_PX = 36
PLATE_RECIPE = "blur-cover-clean-v4"
# Card pixels. The frame-edge fade is this long. A wider ramp smears the seam.
BOUNDARY_RAMP_CARD_PX = 28.0
# A hand that crosses the frame fades only across this many card pixels.
HAND_RAMP_CARD_PX = 28.0
# A run this wide, touching the frame, is the torso. A narrower contact is a hand.
TORSO_RUN_FRACTION = 0.28
# Short fade on every source edge. The old wide torso ramp is gone.
BOUNDARY_RAMP_RECIPE = "boundary-ramp-v7"
# First frames of a segment are seeded from this many frames later, then checked.
SEGMENT_OPEN_FRAMES = 3
# Green inside the matte, in a connected patch this small, is a foliage leak.
FOLIAGE_COMPONENT_PX = 25000
# Rim green, or a matte that grew against the stable frame, fails an opening frame.
OPEN_RIM_GREEN_PX = 800
OPEN_AREA_RATIO = 1.06
OPEN_AREA_GREEN_PX = 400
OPEN_RIM_PX = 28
# Pixels of matte that sit off the stable silhouette on an opening frame.
SEGMENT_OPEN_BLOB_PX = 2500
# The face box may lose this fraction of its raw matte. More than that fails the render.
HEAD_MATTE_DROP_LIMIT = 0.10
# Canvas pixels of empty space kept above the hair, clear of titles and panels.
CROWN_HEADROOM_PX = 96
# The caption baseline sits this far above the crown. 25-50 is the allowed band.
CAPTION_GAP_ABOVE_CROWN_PX = 35
# Empty pixels between the graphic stage and the top of that line.
CAPTION_GAP_BELOW_STAGE_PX = 18
# Inter Black cap height over the em size. 54 px type has about a 39 px cap.
SPLIT_CAP_FACTOR = 39.0 / 54.0
# Matches .caption-text { line-height: 1.02 } and .cap.marker { font-size: 1.12em }.
CAPTION_LINE_FACTOR = 1.02
CAPTION_EMPHASIS = 1.12
# A raised hand should clear the card edge by about this many pixels.
HAND_CLEAR_PX = 16
CROWN_MIN_PX = 28
# A hand this far inside the card is on the chest. Do not lift the crop for it.
HAND_INSIDE_IGNORE_PX = 48
HOLE_AREA_FRACTION = 0.004
# The pop layer overlaps the card by this many pixels so the clip does not
# land on the card edge. The overlap is opaque chest, so it does not draw a line.
SEAM_PX = 4
ANALYSIS_LONG_EDGE = 720
GUIDE_RADIUS = 12
GUIDE_EPS = 8e-4
# Soft ramp on the silhouette. Two to three pixels, not a halo and not a stair.
FEATHER_PX = 2.5
# Weight of the current frame on the uncertain edge. The solid body is not blended.
TEMPORAL_NOW = 0.38
# Gaussian on the alpha before the threshold, so the crown stays round.
CONTOUR_SIGMA = 1.45
# A second blur of the mask. Wide enough to kill a 1 px stair, short of a flat crown.
CONTOUR_ROUND_SIGMA = 1.8
# Connected components smaller than this are specks, including islands above the hair.
SPECK_MIN_PX = 200
# Foliage green is pulled off this many pixels either side of the contour.
DESPILL_RADIUS_PX = 6
# Encoder scale inside Robust Video Matting. The alpha is still full frame size.
# 0.5 keeps the ears and the crown; 0.25 is the live-call look this replaced.
RVM_DOWNSAMPLE = 0.5
SHADOW_OFFSET_Y = 12
SHADOW_SIGMA = 11.0
SHADOW_OPACITY = 0.46
EDGE_RECIPE = "rvm-r50-d050-flow-backseed-nofoliage5-darkfringe-feather2.5-despill6-speck200-spike-shoulder-coldopen-olive-oliveedge"
# Foliage fraction of the crown's soft band, or of the 0-8 px ring outside it.
# Clean cut frames sit under about 0.04. A leaf halo sits above 0.13.
OPEN_FRINGE_IN = 0.09
OPEN_FRINGE_OUT = 0.13
OPEN_FRINGE_RING_PX = 8.0
OPEN_FRINGE_CROWN = 0.15
# Share of the cap's outside ring whose luma sits this far under the local plate.
# A clean crown is near 0.06. The dark halo at a bad cut sits above 0.10.
OPEN_FRINGE_DARK = 0.10
OPEN_FRINGE_DARK_BELOW = 12.0
# Spec limits for the encoded cut-frame check. Green replaces the old 0.11
# inside / 0.155 outside pair. Dark is the cap halo. Roughness is the crown
# stair and jitter is the leftover edge wobble, both in pixels. The render
# repair stays on the looser OPEN_FRINGE_* gates above.
CHECK_FRINGE_GREEN = 0.03
CHECK_FRINGE_DARK = 0.05
CHECK_ROUGHNESS_PX = 1.0
CHECK_JITTER_PX = 1.0


def _run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "ffmpeg failed")[-2000:])
    return result


def _probe(path):
    from edit import probe
    return probe(path)


def _video_facts(path):
    info = _probe(path)
    stream = next(item for item in info["streams"] if item.get("codec_type") == "video")
    rate = stream.get("r_frame_rate") or stream.get("avg_frame_rate") or "30/1"
    num, den = rate.split("/")
    fps = float(num) / float(den or 1)
    frames = stream.get("nb_frames")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": fps,
        "duration": float(info["format"]["duration"]),
        "frames": int(frames) if frames and str(frames).isdigit() else None,
        "pix_fmt": stream.get("pix_fmt") or "",
        "codec": stream.get("codec_name") or "",
    }


def source_digest(path):
    """Content hash so a re-render of the same take does not segment again."""
    digest = hashlib.sha256()
    digest.update(MODEL.encode())
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:24]


def parse_position(value):
    parts = str(value).replace(",", " ").split()

    def number(token):
        token = token.strip()
        if token.endswith("%"):
            return float(token[:-1]) / 100
        return float(token)

    x = number(parts[0]) if parts else 0.5
    y = number(parts[1]) if len(parts) > 1 else 0.5
    return x, y


def cover_fit(video_w, video_h, card_w, card_h):
    return max(card_w / video_w, card_h / video_h)


def cover_box(video_w, video_h, card_w, card_h, pos_x, pos_y, scale=1.0, origin=(0.5, 0.3)):
    """Where the unclipped cover image sits, in card-local pixels, after camera scale."""
    fit = cover_fit(video_w, video_h, card_w, card_h)
    rendered_w, rendered_h = video_w * fit, video_h * fit
    offset_x = pos_x * (card_w - rendered_w)
    offset_y = pos_y * (card_h - rendered_h)
    origin_x, origin_y = origin[0] * card_w, origin[1] * card_h
    return {
        "left": origin_x + (offset_x - origin_x) * scale,
        "top": origin_y + (offset_y - origin_y) * scale,
        "width": rendered_w * scale,
        "height": rendered_h * scale,
        "fit": fit,
    }


def source_y_on_card(source_y, video_w, video_h, card_w, card_h, pos_y, scale=1.0, origin_y=0.3):
    """Card-local Y of a source row. Negative means above the card's top edge."""
    fit = cover_fit(video_w, video_h, card_w, card_h)
    rendered_h = video_h * fit
    offset_y = pos_y * (card_h - rendered_h)
    local = offset_y + source_y * fit
    origin = origin_y * card_h
    return origin + (local - origin) * scale


def solve_position_y(head_top, head_height, pop_fraction, video_w, video_h, card_w, card_h,
                     scale=1.0, origin_y=0.3):
    """object-position Y that puts `head_top` pop_fraction of the head above the card."""
    fit = cover_fit(video_w, video_h, card_w, card_h)
    target = -pop_fraction * head_height * fit * scale
    origin = origin_y * card_h
    offset_y = (target - origin * (1 - scale) - head_top * fit * scale) / scale
    denom = card_h - video_h * fit
    if abs(denom) < 1e-6:
        return 0.5
    return float(np.clip(offset_y / denom, 0.02, 0.98))


def position_for_row(source_y, above_px, video_w, video_h, card_w, card_h, scale=1.0, origin_y=0.3):
    """object-position Y that places `source_y` `above_px` above the card top."""
    fit = cover_fit(video_w, video_h, card_w, card_h)
    target = -float(above_px)
    origin = origin_y * card_h
    offset_y = (target - origin * (1 - scale) - source_y * fit * scale) / scale
    denom = card_h - video_h * fit
    if abs(denom) < 1e-6:
        return 0.5
    return float(np.clip(offset_y / denom, 0.02, 0.98))


def choose_anchor(head_tops, head_height):
    """Aim the median crown at POP_FRACTION of the head above the card.

    A single crop cannot track a lean. The lower head pulls the crop up when
    it would otherwise clear less than POP_FLOOR, and that pull stops at POP_CAP.
    frame_popout then keeps the crown under the caption and a raised hand
    under the hero.
    """
    tops = np.sort(np.asarray(head_tops, dtype=np.float64))
    if tops.size == 0:
        raise ValueError("the matte has no head samples")
    median = float(np.percentile(tops, 50))
    low = float(np.percentile(tops, 80))
    high = float(np.percentile(tops, 20))
    height = max(float(head_height), 1.0)
    fraction = POP_FRACTION
    low_pop = fraction - (low - median) / height
    if low_pop < POP_FLOOR:
        needed = POP_FLOOR + (low - median) / height
        fraction = min(POP_CAP, max(POP_FRACTION, needed))
    return {"anchor": median, "fraction": fraction, "low": low, "high": high, "median": median}


def pop_geometry(card, video_w, video_h, position, canvas_h, seam=SEAM_PX):
    """Canvas placement of the alpha video, clipped to the strip above the card."""
    pos_x, pos_y = parse_position(position)
    box = cover_box(video_w, video_h, card["width"], card["height"], pos_x, pos_y, card.get("scale", 1))
    left = round(card["left"] + box["left"], 2)
    top = round(card["top"] + box["top"], 2)
    clip_bottom = round(canvas_h - (card["top"] + seam), 2)
    return {
        "left": left,
        "top": top,
        "width": round(box["width"], 2),
        "height": round(box["height"], 2),
        "clipPath": f"inset(0px 0px {max(0, clip_bottom)}px 0px)",
    }


def large_holes(mask, fraction=HOLE_AREA_FRACTION):
    """Interior background blobs. A soft edge is not a hole; an enclosed gap is.

    `mask` is a 2-D array, 0 background and 255 person. Returns hole areas in
    pixels of this mask.
    """
    fg = np.asarray(mask) >= 96
    if fg.ndim != 2 or fg.size == 0 or not fg.any():
        return [{"area": int(fg.size) if fg.size else 1, "empty": True}]
    background = ~fg
    labels, count = ndimage.label(background)
    if count == 0:
        return []
    border = np.unique(np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]]))
    outside = set(int(item) for item in border if item)
    limit = max(12, int(round(fg.size * fraction)))
    holes = []
    for label in range(1, count + 1):
        if label in outside:
            continue
        area = int((labels == label).sum())
        if area >= limit:
            holes.append({"area": area, "limit": limit})
    return holes


def _analysis_size(width, height, target=288):
    narrow = min(width, target)
    other = max(2, int(round(height * narrow / width / 2)) * 2)
    if width >= height:
        return narrow, other
    wide = max(2, int(round(width * target / height / 2)) * 2)
    return wide, target if target % 2 == 0 else target + 1


def _head_from_mask(mask):
    """Head top and height in mask pixels. A raised hand outside the crown is ignored."""
    fg = mask >= 96
    height, width = fg.shape
    if fg.mean() < 0.02:
        return None
    ys, xs = np.where(fg)
    center = float(np.median(xs))
    half = max(6, int(width * 0.09))
    x0, x1 = max(0, int(center - half)), min(width, int(center + half))
    rows = np.where(fg[:, x0:x1].any(axis=1))[0]
    if rows.size == 0:
        return None
    top = int(rows[0])
    widths = fg.sum(axis=1).astype(np.float64)
    upper_end = min(height, top + int(height * 0.42))
    upper = widths[top:upper_end]
    peak = float(np.percentile(upper, 90)) if upper.size else float(widths[top])
    # The cap tip is thin. The face is the wide plateau just under it. A close
    # selfie has almost no width jump at the shoulders, so height comes from
    # that face width (a head is a bit taller than it is wide, and the cap adds more).
    face_rows = upper[upper >= max(4.0, peak * 0.72)]
    face_width = float(np.median(face_rows)) if face_rows.size else max(peak, 4.0)
    head_height = max(face_width * 1.35, 8.0)
    full = int(np.argmax(upper >= peak * 0.72)) if np.any(upper >= peak * 0.72) else 0
    face_row = top + full
    # A raised hand reaches above the ears and sits outside the head, not in
    # the shoulder line. The crown column used above is too narrow for this.
    hand = None
    reach = max(8, int(face_width * 0.62))
    hx0, hx1 = max(0, int(center - reach)), min(width, int(center + reach))
    side = fg.copy()
    side[:, hx0:hx1] = False
    band = side[:max(top + 1, face_row + 2), :]
    if band.any():
        hand = int(np.where(band.any(axis=1))[0][0])
    return {"top": top, "height": float(head_height), "hand": hand}


def _decode_gray(path, width, fps=None, frames=None, start=0.0):
    facts = _video_facts(path)
    sample_w, sample_h = _analysis_size(facts["width"], facts["height"], width)
    filters = [f"scale={sample_w}:{sample_h}:flags=bilinear"]
    if fps:
        filters.insert(0, f"fps={fps}")
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"]
    if facts["codec"] in {"vp9", "vp8"}:
        cmd.extend(["-c:v", "libvpx-vp9" if facts["codec"] == "vp9" else "libvpx"])
    alpha = "a" in facts["pix_fmt"] or facts["pix_fmt"].startswith("yuva")
    if alpha:
        filters.insert(0, "alphaextract")
    cmd.extend(["-i", str(path), "-vf", ",".join(filters), "-f", "rawvideo", "-pix_fmt", "gray"])
    if frames:
        cmd.extend(["-frames:v", str(frames)])
    cmd.append("pipe:1")
    raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    frame = sample_w * sample_h
    count = len(raw) // frame
    masks = [np.frombuffer(raw[i * frame:(i + 1) * frame], dtype=np.uint8).reshape(sample_h, sample_w) for i in range(count)]
    return masks, sample_w, sample_h, facts


def measure_head(matte_path, step=0.25):
    """Head top and height in the matte's own pixel grid, plus raised-hand times."""
    facts = _video_facts(matte_path)
    duration = facts["duration"]
    times = np.arange(0.05, max(0.06, duration - 0.05), step)
    masks, sample_w, sample_h, _facts = _decode_gray(matte_path, 180, fps=round(1 / step, 3))
    if not masks:
        raise ValueError(f"could not read a matte frame from {matte_path}")
    scale_y = facts["height"] / sample_h
    tops, heights, hands, crowns = [], [], [], []
    for index, mask in enumerate(masks):
        found = _head_from_mask(mask)
        if not found:
            continue
        top = found["top"] * scale_y
        tops.append(top)
        heights.append(found["height"] * scale_y)
        when = float(times[index]) if index < len(times) else index * step
        crowns.append({"at": round(when, 3), "top": round(float(top), 2)})
        if found["hand"] is not None:
            hands.append({"at": round(when, 3), "top": round(found["hand"] * scale_y, 1)})
    if not tops:
        raise ValueError(f"the matte in {matte_path} never found a person")
    height = float(np.median(heights))
    choice = choose_anchor(tops, height)
    return {
        "width": facts["width"],
        "height": facts["height"],
        "head_top": round(choice["anchor"], 2),
        "head_height": round(height, 2),
        "head_low": round(choice["low"], 2),
        "head_high": round(choice["high"], 2),
        "pop_fraction": round(choice["fraction"], 4),
        "samples": len(tops),
        "hands": hands,
        "crown_samples": crowns,
    }


def inspect_matte(path, samples=8):
    """Style-check sample. Errors are human-readable strings."""
    facts = _video_facts(path)
    if facts["duration"] <= 0:
        return ["matte: the alpha matte has no duration"]
    step = max(facts["duration"] / (samples + 1), 1 / max(facts["fps"], 1))
    masks, _w, _h, _facts = _decode_gray(path, 216, fps=round(1 / step, 3), frames=samples)
    if len(masks) < 2:
        return ["matte: could not sample the alpha matte"]
    errors = []
    areas = []
    for index, mask in enumerate(masks):
        at = (index + 1) * step
        fg = mask >= 96
        areas.append(int(fg.sum()))
        if fg.mean() < 0.02:
            errors.append(f"matte: frame near {at:.2f}s has no person")
            continue
        for hole in large_holes(mask):
            if hole.get("empty"):
                errors.append(f"matte: frame near {at:.2f}s has no person")
            else:
                errors.append(
                    f"matte: frame near {at:.2f}s has an interior hole of {hole['area']}px "
                    f"(limit {hole['limit']}px at the sample size)")
    # A hand raise moves the area. Only a collapse or a sudden doubling is treated as flicker.
    for left, right in zip(areas, areas[1:]):
        if min(left, right) <= 0:
            continue
        if max(left, right) / min(left, right) > 2.4:
            errors.append("matte: the silhouette area jumps between samples, so the edge is flickering")
            break
    return errors


def guided_filter(guide, src, radius, eps):
    """He et al. guided filter. `guide` and `src` are float32 images in 0..1."""
    size = 2 * int(radius) + 1

    def box(image):
        return ndimage.uniform_filter(image, size=size, mode="nearest")

    mean_g = box(guide)
    mean_s = box(src)
    var_g = np.maximum(box(guide * guide) - mean_g * mean_g, 0)
    cov = box(guide * src) - mean_g * mean_s
    a = cov / (var_g + eps)
    b = mean_s - a * mean_g
    return np.clip(box(a) * guide + box(b), 0, 1).astype(np.float32)


def _distance_feather(binary, radius):
    """Alpha that goes from 0 to 1 across `radius` pixels on each side of the edge."""
    inside = ndimage.distance_transform_edt(binary)
    outside = ndimage.distance_transform_edt(~binary)
    signed = inside - outside
    return np.clip(0.5 + signed / (2 * radius), 0, 1).astype(np.float32)


def _foreground_color(rgb, person):
    """Person color in the feather, so the soft edge is not a fringe of the room."""
    weight = ndimage.gaussian_filter(person, 1.25) + 1e-3
    rgb_f = rgb.astype(np.float32)
    out = rgb_f.copy()
    fringe = person < 0.98
    if not fringe.any():
        return out
    pulled = np.empty_like(rgb_f)
    for channel in range(3):
        pulled[:, :, channel] = ndimage.gaussian_filter(rgb_f[:, :, channel] * person, 1.25) / weight
    out[fringe] = pulled[fringe]
    return out


def _drop_specks(binary, min_area=SPECK_MIN_PX):
    """Drop specks and any island that sits entirely above the crown."""
    labels, count = ndimage.label(binary)
    if count <= 0:
        return binary
    counts = np.bincount(labels.ravel())
    largest = 1 + int(np.argmax(counts[1:]))
    body_rows = np.where(labels == largest)[0]
    crown = int(body_rows.min()) if body_rows.size else 0
    keep = np.zeros(count + 1, dtype=bool)
    keep[largest] = True
    for label in range(1, count + 1):
        if label == largest:
            continue
        area = int(counts[label])
        rows = np.where(labels == label)[0]
        if rows.size == 0:
            continue
        floating = int(rows.max()) < crown - 1
        if area >= min_area and not floating:
            keep[label] = True
    return keep[labels]


def _foliage_green(rgb):
    """Leaves: greener than the shirt and the skin, and not a near-black pixel."""
    color = np.asarray(rgb)
    red = color[:, :, 0].astype(np.int16)
    green = color[:, :, 1].astype(np.int16)
    blue = color[:, :, 2].astype(np.int16)
    return (green > red + 14) & (green > blue + 14) & (green > 35)


def _olive_leak(rgb):
    """Shoulder foliage too olive for the saturated-leaf test.

    These leaves are only a few points greener than red. Skin is redder than
    green, and the gray shirt is not greener than red, so neither matches.
    """
    color = np.asarray(rgb)
    red = color[:, :, 0].astype(np.int16)
    green = color[:, :, 1].astype(np.int16)
    blue = color[:, :, 2].astype(np.int16)
    return (
        (green > red + 6) & (green > blue + 10) & (red < 150)
        & (blue < 100) & (green > 40) & (green < 180))


def _crown_rows(inside, fraction):
    """Rows from the crown down through ``fraction`` of the silhouette."""
    inside = np.asarray(inside, dtype=bool)
    ys = np.where(inside)[0]
    band = np.zeros(inside.shape, dtype=bool)
    if ys.size == 0:
        return band
    top = int(ys.min())
    span = max(1, int(ys.max()) - top)
    band[:top + max(1, int(round(float(fraction) * span)))] = True
    return band


def fringe_green_fractions(rgb, person, ring_px=OPEN_FRINGE_RING_PX, crown_fraction=OPEN_FRINGE_CROWN):
    """Foliage fraction inside the soft crown, and in the ring just outside it.

    ``green_in`` is the soft band (alpha about 0.03-0.80) on the crown.
    ``green_out`` is the 0-8 px ring outside the matte edge, same rows.
    A clean cut sits near 0. A leaf halo is above about 0.13 on both.
    """
    person = np.asarray(person, dtype=np.float32)
    if person.ndim != 2:
        raise ValueError("fringe check expects one alpha plane")
    inside = person >= 0.5
    if not np.any(inside):
        return 0.0, 0.0
    green = _foliage_green(rgb)
    if green.shape != inside.shape:
        raise ValueError("fringe color must match the matte")
    crown = _crown_rows(inside, crown_fraction)
    dist_out = ndimage.distance_transform_edt(~inside)
    soft = (person >= 0.03) & (person < 0.80) & crown
    ring = (dist_out > 0) & (dist_out <= float(ring_px)) & crown

    def fraction(mask):
        count = int(mask.sum())
        if count <= 0:
            return 0.0
        return float(np.count_nonzero(green & mask) / count)

    return fraction(soft), fraction(ring)


def fringe_fails(rgb, person, limit_in=OPEN_FRINGE_IN, limit_out=OPEN_FRINGE_OUT):
    """A crown whose soft edge or outside ring is still source green."""
    soft, ring = fringe_green_fractions(rgb, person)
    return soft > float(limit_in) or ring > float(limit_out), soft, ring


def _cap_rows(inside, fraction=OPEN_FRINGE_CROWN):
    """The crown cap: the top of the silhouette, before it widens into the cheeks.

    The full 15% band includes the dark room beside the jaw. The fringe QA
    measures is the cap, where the plate should show and a dark halo does not.
    """
    inside = np.asarray(inside, dtype=bool)
    band = np.zeros(inside.shape, dtype=bool)
    ys = np.where(inside)[0]
    if ys.size == 0:
        return band
    top = int(ys.min())
    span = max(1, int(ys.max()) - top)
    limit = top + max(8, int(round(float(fraction) * span)))
    widths = inside.sum(axis=1)
    tip = widths[top:top + min(8, int(widths.size))]
    tip = tip[tip > 0]
    tip_w = max(8, int(np.median(tip))) if tip.size else 8
    narrow = widths < tip_w * 2.4
    band[:limit] = True
    band &= narrow[:, None]
    return band


def _plate_luma(rgb, person, band):
    """Median luma of the local background, 12–32 px outside the matte.

    That ring is what the blurred plate is built from. None when the cap has
    no background to compare against.
    """
    person = np.asarray(person, dtype=np.float32)
    inside = person >= 0.5
    if not np.any(band):
        return None
    dist = ndimage.distance_transform_edt(~inside)
    luma = np.asarray(rgb, dtype=np.float32).mean(axis=2)
    far = (dist >= 12) & (dist <= 32) & band & (person < 0.04)
    if int(far.sum()) < 40:
        return None
    return float(np.median(luma[far]))


def fringe_dark_fraction(rgb, person, ring_px=OPEN_FRINGE_RING_PX, below=OPEN_FRINGE_DARK_BELOW,
                         crown_fraction=OPEN_FRINGE_CROWN):
    """Share of the cap's 0–8 px ring that is well below the local plate.

    Green foliage is a separate check. This one catches a dark crown halo:
    source pixels in that ring whose luma sits ``below`` points under the plate.
    """
    person = np.asarray(person, dtype=np.float32)
    if person.ndim != 2:
        raise ValueError("fringe check expects one alpha plane")
    inside = person >= 0.5
    if not np.any(inside):
        return 0.0
    band = _cap_rows(inside, crown_fraction)
    plate = _plate_luma(rgb, person, band)
    if plate is None:
        return 0.0
    dist = ndimage.distance_transform_edt(~inside)
    luma = np.asarray(rgb, dtype=np.float32).mean(axis=2)
    ring = (dist > 0) & (dist <= float(ring_px)) & band
    count = int(ring.sum())
    if count < 20:
        return 0.0
    dark = luma < (plate - float(below))
    return float(np.count_nonzero(dark & ring) / count)


def _edge_columns(person):
    """Left and right crown-cap columns. A border edge is left empty.

    The cap is the same narrow crown the dark-fringe check uses. Columns are
    indexed by image row, with NaN where that row is not part of the cap.
    """
    person = np.asarray(person, dtype=np.float32)
    if person.size and float(np.max(person)) > 1.5:
        person = person / 255.0
    inside = person >= 0.5
    height, width = inside.shape
    left = np.full(height, np.nan, dtype=np.float64)
    right = np.full(height, np.nan, dtype=np.float64)
    if not np.any(inside):
        return left, right
    band = _cap_rows(inside)
    for y in np.flatnonzero(band.any(axis=1)):
        xs = np.flatnonzero(inside[y])
        if xs.size == 0:
            continue
        if int(xs[0]) > 1:
            left[y] = float(xs[0])
        if int(xs[-1]) < width - 2:
            right[y] = float(xs[-1])
    return left, right


def _stair_peak(columns):
    """Largest crown stair, in pixels.

    The stair is the absolute second difference of an edge column. A smooth
    slope scores 0. A step of one pixel scores 1.
    """
    finite = np.isfinite(columns)
    peak = 0.0
    y = 0
    count = len(columns)
    while y < count:
        if not finite[y]:
            y += 1
            continue
        start = y
        while y < count and finite[y]:
            y += 1
        run = columns[start:y]
        if run.size >= 3:
            second = np.abs(run[:-2] - 2.0 * run[1:-1] + run[2:])
            peak = max(peak, float(second.max()))
    return peak


def matte_roughness_px(person):
    """Peak stair of the crown cap, in pixels."""
    left, right = _edge_columns(person)
    return max(_stair_peak(left), _stair_peak(right))


def _tip_run(columns):
    """Edge columns from the crown tip down, dropping the rows above it."""
    finite = np.flatnonzero(np.isfinite(columns))
    if finite.size == 0:
        return np.array([], dtype=np.float64)
    start = int(finite[0])
    end = start
    while end < len(columns) and np.isfinite(columns[end]):
        end += 1
    return columns[start:end]


def _jitter_side(previous, current):
    """Peak leftover motion on one edge after the head's own shift is removed."""
    count = min(len(previous), len(current))
    if count < 4:
        return 0.0
    delta = current[:count] - previous[:count]
    finite = np.isfinite(delta)
    if int(finite.sum()) < 4:
        return 0.0
    resid = delta[finite] - float(np.median(delta[finite]))
    return float(np.max(np.abs(resid)))


def matte_jitter_px(previous, current):
    """Peak crown wobble between two frames, in pixels.

    Each edge is indexed from its own crown tip, so a nod is not jitter. The
    median column shift is the head moving sideways. A row that moves farther
    than that shift is the wobble.
    """
    prev_left, prev_right = _edge_columns(previous)
    next_left, next_right = _edge_columns(current)
    return max(
        _jitter_side(_tip_run(prev_left), _tip_run(next_left)),
        _jitter_side(_tip_run(prev_right), _tip_run(next_right)))


def cut_frame_row_failed(green_in, green_out, dark, roughness, jitter):
    """One encoded cut frame against the spec limits.

    Green is 0.03 on both the soft band and the outside ring. Dark is 0.05.
    Roughness and jitter pass at 1 px. The old 0.11 and 0.155 green gates
    are not the check.
    """
    green_limit = float(CHECK_FRINGE_GREEN)
    return (
        float(green_in) > green_limit
        or float(green_out) > green_limit
        or float(dark) > float(CHECK_FRINGE_DARK)
        or float(roughness) > float(CHECK_ROUGHNESS_PX)
        or float(jitter) > float(CHECK_JITTER_PX))


def fringe_dark_fails(rgb, person, limit=OPEN_FRINGE_DARK):
    """A cap whose outside ring is a dark halo against the plate."""
    fraction = fringe_dark_fraction(rgb, person)
    return fraction > float(limit), fraction


def _shrink_green_crown(binary, rgb, steps=1, ring_px=OPEN_FRINGE_RING_PX):
    """Pull the crown edge off leaves in the outside ring. One step is one pixel.

    A leaf a few pixels outside the edge still fills the 0-8 px ring. The
    boundary moves while that ring is green, and stops once the leaves are
    farther than the ring.
    """
    binary = np.array(binary, dtype=bool, copy=True)
    if not np.any(binary):
        return binary
    green = _foliage_green(rgb)
    reach = max(1, int(round(float(ring_px))))
    for _ in range(max(1, int(steps))):
        if not np.any(binary):
            break
        crown = _crown_rows(binary, 0.42)
        # Leaves already counted as the person come off the crown first.
        inside_green = binary & green & crown
        if np.any(inside_green):
            binary[inside_green] = False
            continue
        outside = green & ~binary
        if not np.any(outside):
            break
        boundary = binary & ~ndimage.binary_erosion(binary, iterations=1, border_value=0)
        touch = ndimage.binary_dilation(outside, iterations=reach)
        cut = boundary & touch & crown
        if not np.any(cut):
            break
        binary[cut] = False
    return binary


def _shrink_dark_crown(binary, rgb, steps=1, ring_px=OPEN_FRINGE_RING_PX, below=OPEN_FRINGE_DARK_BELOW):
    """Pull the cap edge off a dark halo. One step is one pixel.

    Hair that is merely darker than the plate stays. Only the outer rim of the
    cap moves, and only where that rim touches source that is well below the plate.
    """
    binary = np.array(binary, dtype=bool, copy=True)
    if not np.any(binary):
        return binary
    luma = np.asarray(rgb, dtype=np.float32).mean(axis=2)
    for _ in range(max(1, int(steps))):
        if not np.any(binary):
            break
        cap = _cap_rows(binary, OPEN_FRINGE_CROWN)
        plate = _plate_luma(rgb, binary.astype(np.float32), cap)
        if plate is None:
            break
        dark = luma < (plate - float(below))
        boundary = binary & ~ndimage.binary_erosion(binary, iterations=1, border_value=0)
        outside = dark & ~binary
        if not np.any(outside):
            break
        # A dark pixel anywhere in the 0-8 px ring still counts. The rim moves
        # one pixel while that ring is dark, and stops once the halo is farther out.
        reach = max(1, int(round(float(ring_px))))
        touch = ndimage.binary_dilation(outside, iterations=reach)
        cut = boundary & touch & cap
        if not np.any(cut):
            break
        binary[cut] = False
    return binary


def _drop_foliage(binary, rgb, max_area=FOLIAGE_COMPONENT_PX, rim_px=OPEN_RIM_PX):
    """Take foliage leaks out of the matte. Skin and the shirt stay.

    A connected green patch up to ``max_area`` is a leaf that the mask
    swallowed, including one beside a fingertip. Green on the outer rim of a
    larger patch is the same leak. A green region bigger than that, and deeper
    than the rim, is left for the opening-frame check.
    """
    binary = np.asarray(binary, dtype=bool)
    green = _foliage_green(rgb) & binary
    if not np.any(green):
        return binary
    labels, count = ndimage.label(green)
    counts = np.bincount(labels.ravel())
    # The torso, not the shoulder surface. A leaf sitting on the shoulder
    # barely overlaps this core. A green shirt does.
    core = ndimage.binary_erosion(binary, iterations=8) if np.any(binary) else binary
    core_px = int(np.count_nonzero(core))
    drop = np.zeros(count + 1, dtype=bool)
    for label in range(1, count + 1):
        area = int(counts[label])
        if area <= 0:
            continue
        if area <= int(max_area):
            drop[label] = True
            continue
        if core_px > 200 and area <= 90000:
            overlap = int(np.count_nonzero((labels == label) & core))
            if overlap * 8 < area:
                drop[label] = True
    cleaned = np.array(binary, copy=True) if drop.any() else binary
    if drop.any():
        cleaned[drop[labels]] = False
    remain = _foliage_green(rgb) & cleaned
    if np.any(remain):
        dist = ndimage.distance_transform_edt(cleaned)
        rim = remain & (dist > 0) & (dist <= float(rim_px))
        if int(rim.sum()) > 0 and int(rim.sum()) < 0.08 * max(1, int(cleaned.sum())):
            if cleaned is binary:
                cleaned = np.array(binary, copy=True)
            cleaned[rim] = False
    return cleaned


def _drop_olive_leak(binary, rgb, min_area=250):
    """Drop olive the matte swallowed beside the shoulder.

    The torso core is eroded far enough that a leaf on the shoulder does not
    count as the shirt. Flow can stitch that leaf to the torso, so a component
    test keeps the whole blob. Every olive pixel outside the core goes,
    including a speck under ``min_area``. Olive inside the core stays.
    """
    del min_area
    binary = np.asarray(binary, dtype=bool)
    olive = _olive_leak(rgb) & binary
    if not np.any(olive):
        return binary
    core = ndimage.binary_erosion(binary, iterations=28) if np.any(binary) else binary
    outside = olive & ~core
    if not np.any(outside):
        return binary
    cleaned = np.array(binary, copy=True)
    cleaned[outside] = False
    return cleaned


def _drop_background_rim(binary, rgb, rim_px=8, match=12):
    """Drop plate-colored pixels in the outer 8 px of the matte. Skin stays.

    The shoulder leak is gray and olive, not green enough for the foliage
    test. It sits a few pixels inside the edge and matches the plate beside
    it. Skin is redder and brighter than that plate, so the arm stays. One
    pass only: a deeper cut starts eating the shirt, which is the same color
    family once you leave the rim.
    """
    binary = np.asarray(binary, dtype=bool)
    if not np.any(binary):
        return binary
    color = np.asarray(rgb, dtype=np.float32)
    red = color[:, :, 0]
    green = color[:, :, 1]
    blue = color[:, :, 2]
    skin = (red > green + 15) & (red > 155) & (red > blue)
    dist_in = ndimage.distance_transform_edt(binary)
    outside = ~binary
    weight = ndimage.uniform_filter(outside.astype(np.float32), size=9, mode="nearest")
    background = np.empty_like(color)
    for channel in range(3):
        blurred = ndimage.uniform_filter(color[:, :, channel] * outside, size=9, mode="nearest")
        background[:, :, channel] = blurred / np.maximum(weight, 1e-3)
    distance = np.sqrt(((color - background) ** 2).sum(axis=2))
    cut = (
        binary & ~skin & (dist_in > 0) & (dist_in <= float(rim_px))
        & (distance <= float(match)) & (weight > 0.08)
    )
    if not np.any(cut):
        return binary
    cleaned = np.array(binary, copy=True)
    cleaned[cut] = False
    return cleaned


def despill_green(rgb, person, binary=None):
    """Take foliage green off the edge band. Skin inside the silhouette stays.

    The band is the soft ramp plus ``DESPILL_RADIUS_PX`` on either side of the
    contour, so a green fringe cannot sit just inside a solid pixel.
    """
    out = np.array(rgb, dtype=np.float32, copy=True)
    red = out[:, :, 0]
    green = out[:, :, 1]
    blue = out[:, :, 2]
    limit = np.maximum(red, blue)
    excess = np.clip(green - limit, 0, None)
    edge = (person > 0.02) & (person < 0.98)
    strength = np.clip((0.98 - person) / 0.96, 0, 1)
    if binary is not None:
        mask = np.asarray(binary, dtype=bool)
        inside = ndimage.distance_transform_edt(mask)
        outside = ndimage.distance_transform_edt(~mask)
        near = ((inside > 0) & (inside <= DESPILL_RADIUS_PX)) | (
            (outside > 0) & (outside <= DESPILL_RADIUS_PX) & (person > 0.01))
        strength = np.where(near, 1.0, strength)
        edge = edge | near
    if not np.any(edge):
        return out
    out[:, :, 1] = np.where(edge, green - excess * strength, green)
    return out


def _flow_stabilize(alpha, previous, gray):
    """Blend the uncertain band with the previous alpha, warped by the picture's motion.

    The solid person and the empty background are left alone, so the outline
    does not boil and a head turn does not smear.
    """
    prev_alpha = previous.get("alpha") if isinstance(previous, dict) else previous
    prev_gray = previous.get("gray") if isinstance(previous, dict) else None
    if prev_alpha is None or getattr(prev_alpha, "shape", None) != alpha.shape:
        return alpha
    import cv2
    height, width = alpha.shape
    long_edge = max(width, height)
    scale = min(1.0, 540.0 / long_edge)
    small_w = max(32, int(round(width * scale)) // 2 * 2)
    small_h = max(32, int(round(height * scale)) // 2 * 2)
    current = np.asarray(gray, dtype=np.uint8)
    if prev_gray is None or getattr(prev_gray, "shape", None) != current.shape:
        warped = prev_alpha
    else:
        prev_s = cv2.resize(prev_gray, (small_w, small_h), interpolation=cv2.INTER_AREA)
        gray_s = cv2.resize(current, (small_w, small_h), interpolation=cv2.INTER_AREA)
        flow = cv2.calcOpticalFlowFarneback(
            prev_s, gray_s, None, 0.5, 3, 21, 3, 5, 1.2, 0)
        flow = cv2.resize(flow, (width, height), interpolation=cv2.INTER_LINEAR)
        flow[:, :, 0] *= width / float(small_w)
        flow[:, :, 1] *= height / float(small_h)
        grid_x, grid_y = np.meshgrid(
            np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
        warped = cv2.remap(
            prev_alpha.astype(np.float32),
            grid_x + flow[:, :, 0], grid_y + flow[:, :, 1],
            cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    edge = ((alpha > 0.01) & (alpha < 0.99)) | ((warped > 0.01) & (warped < 0.99))
    disagree = np.abs(alpha - warped) > 0.12
    edge = edge | (disagree & (np.maximum(alpha, warped) > 0.04) & (np.minimum(alpha, warped) < 0.96))
    mixed = alpha.copy()
    mixed[edge] = TEMPORAL_NOW * alpha[edge] + (1.0 - TEMPORAL_NOW) * warped[edge]
    return mixed.astype(np.float32)


def cast_shadow(person, offset_y=SHADOW_OFFSET_Y, sigma=SHADOW_SIGMA, opacity=SHADOW_OPACITY):
    """Soft alpha of a drop shadow sitting just under the silhouette."""
    blurred = ndimage.gaussian_filter(person.astype(np.float32), sigma)
    shifted = np.zeros_like(blurred)
    offset = int(offset_y)
    if offset > 0:
        shifted[offset:] = blurred[:-offset]
    elif offset < 0:
        shifted[:offset] = blurred[-offset:]
    else:
        shifted = blurred
    return np.clip(shifted * opacity, 0, 1).astype(np.float32)


def refine_frame(rgb, coarse, previous=None, hold_edge=False):
    """Feather a full-resolution matte and composite a contact shadow.

    The incoming alpha is already at the picture size. Optical flow steadies
    the edge, a 1-2px ramp antialiases it, and green foliage is pulled off
    that ramp. Returns person alpha, straight RGB, straight alpha (person over
    the shadow), and the state to carry into the next frame.

    ``hold_edge`` keeps a mask that was already pulled off a halo. The contour
    blur would grow that edge back into the fringe, so it is skipped.
    """
    rgb = np.asarray(rgb)
    alpha = np.asarray(coarse, dtype=np.float32)
    if alpha.shape != rgb.shape[:2]:
        import cv2
        alpha = cv2.resize(alpha, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip(alpha, 0, 1).astype(np.float32)
    gray = np.clip(rgb.astype(np.float32).mean(axis=2), 0, 255).astype(np.uint8)
    if hold_edge:
        binary = alpha >= 0.5
        binary = ndimage.binary_fill_holes(binary)
        binary = _drop_specks(binary)
    else:
        alpha = _flow_stabilize(alpha, previous, gray)
        # Blur the contour only. The state carried forward stays sharp so the blur
        # does not accumulate, and the crown stays a curve instead of a flat cut.
        contour = ndimage.gaussian_filter(alpha, CONTOUR_SIGMA)
        binary = contour >= 0.5
        binary = ndimage.binary_fill_holes(binary)
        # Close pinholes. Do not open: opening eats the ear.
        binary = ndimage.binary_closing(binary, structure=np.ones((3, 3), dtype=bool))
        binary = _drop_specks(binary)
        rounded = ndimage.gaussian_filter(binary.astype(np.float32), CONTOUR_ROUND_SIGMA)
        binary = rounded >= 0.5
        binary = ndimage.binary_fill_holes(binary)
        binary = _drop_specks(binary)
    binary = _drop_foliage(binary, rgb)
    binary = _drop_olive_leak(binary, rgb)
    binary = _drop_background_rim(binary, rgb)
    if hold_edge:
        alpha = binary.astype(np.float32)
    person = _distance_feather(binary, FEATHER_PX)
    # The chest stays solid. A clip through it must not show the panel.
    core = ndimage.binary_erosion(binary, iterations=1)
    person = np.where(core, 1.0, person).astype(np.float32)
    fg = despill_green(_foreground_color(rgb, person), person, binary)
    shadow = cast_shadow(person) * (1 - person)
    out_a = np.clip(person + shadow, 0, 1)
    straight = np.zeros_like(fg)
    visible = out_a > 1e-3
    straight[visible] = fg[visible] * (person[visible] / out_a[visible])[:, None]
    straight = np.clip(straight, 0, 255).astype(np.uint8)
    state = {"alpha": alpha, "gray": gray}
    return person, straight, out_a.astype(np.float32), state


_MATTING_MODEL = None


def _load_matting_model():
    """Robust Video Matting, resnet50, kept for the rest of the process."""
    global _MATTING_MODEL
    if _MATTING_MODEL is not None:
        return _MATTING_MODEL
    import torch
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    print("loading Robust Video Matting resnet50", flush=True)
    model = torch.hub.load(
        "PeterL1n/RobustVideoMatting", "resnet50", pretrained=True, trust_repo=True)
    model.eval()
    _MATTING_MODEL = model
    return model


def _encode_mask(raw_path, width, height, fps, output):
    """Full-resolution luma. yuv444 keeps the 1px edge; yuv420 would blur it."""
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{width}x{height}",
        "-r", f"{fps:.6f}", "-i", str(raw_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "6", "-pix_fmt", "yuv444p",
        "-an", str(output),
    ])


def _segment_gray(source, output):
    """Full-frame alpha from Robust Video Matting. Cached per source by MODEL."""
    facts = _video_facts(source)
    width, height, fps = facts["width"], facts["height"], facts["fps"]
    import torch
    model = _load_matting_model()
    decoder = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(source),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_bytes = width * height * 3
    raw_path = output.with_suffix(".raw")
    written = 0
    rec = [None, None, None, None]

    def _exact(size):
        chunks = []
        got = 0
        while got < size:
            blob = decoder.stdout.read(size - got)
            if not blob:
                break
            chunks.append(blob)
            got += len(blob)
        return b"".join(chunks)

    try:
        with raw_path.open("wb") as raw, torch.inference_mode():
            while True:
                blob = _exact(frame_bytes)
                if len(blob) < frame_bytes:
                    break
                rgb = np.frombuffer(blob, dtype=np.uint8).reshape(height, width, 3).copy()
                src = torch.from_numpy(rgb)
                src = src.permute(2, 0, 1).unsqueeze(0).float().mul_(1 / 255)
                _fgr, pha, *rec = model(src, *rec, RVM_DOWNSAMPLE)
                alpha = pha[0, 0].clamp_(0, 1).mul_(255).byte().cpu().numpy()
                raw.write(np.ascontiguousarray(alpha).tobytes())
                written += 1
                if written % 30 == 0:
                    print(f"matted {written} frames", flush=True)
    finally:
        if decoder.stdout:
            decoder.stdout.close()
        decoder.wait()
    if written < 2:
        raw_path.unlink(missing_ok=True)
        raise RuntimeError(f"matting produced no frames for {source}")
    _encode_mask(raw_path, width, height, fps, output)
    raw_path.unlink(missing_ok=True)
    return output


def ensure_source_matte(source, cache_dir=None):
    """Gray matte aligned to the raw source. Reused across renders."""
    source = Path(source)
    root = Path(cache_dir) if cache_dir else CACHE
    folder = root / source_digest(source)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "matte.mp4"
    # yuv420 blurs the 1 px edge. An older cache in that format is rebuilt.
    if target.is_file() and target.stat().st_size > 0 and _video_facts(target).get("pix_fmt") == "yuv444p":
        return target
    if target.is_file():
        target.unlink()
    partial = folder / "matte.partial.mp4"
    _segment_gray(source, partial)
    partial.replace(target)
    return target


def cut_matte(matte, ranges, output):
    """Apply the same picture trims the tightener used, so the mask stays in sync."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = []
    for index, (begin, end) in enumerate(ranges):
        filters.append(f"[0:v]trim=start={begin:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]")
    labels = "".join(f"[v{index}]" for index in range(len(ranges)))
    filters.append(f"{labels}concat=n={len(ranges)}:v=1:a=0[vout]")
    script = output.with_suffix(".txt")
    script.write_text(";\n".join(filters))
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(matte),
        "-filter_complex_script", str(script), "-map", "[vout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "6", "-pix_fmt", "yuv444p",
        "-an", str(output),
    ])
    return output


def pack_alpha(picture, matte, output):
    """QuickTime Animation with straight alpha. HyperFrames extracts it as PNG."""
    output = Path(output)
    if output.suffix.lower() != ".mov":
        output = output.with_suffix(".mov")
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(picture), "-i", str(matte),
        "-filter_complex", "[1:v]format=gray[a];[0:v][a]alphamerge,format=argb",
        "-shortest", "-c:v", "qtrle", "-pix_fmt", "argb", "-an", str(output),
    ])
    return output


def _raw_reader(path, width, height, pix_fmt):
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-vf", f"scale={width}:{height}:flags=lanczos",
        "-f", "rawvideo", "-pix_fmt", pix_fmt, "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    channels = 3 if pix_fmt == "rgb24" else 1
    return proc, width * height * channels


def _read_exact(proc, size):
    chunks = []
    got = 0
    while got < size:
        blob = proc.stdout.read(size - got)
        if not blob:
            return b""
        chunks.append(blob)
        got += len(blob)
    return b"".join(chunks)


def _raw_writer(path, width, height, fps, pix_fmt, codec_args):
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", pix_fmt, "-s", f"{width}x{height}",
        "-r", f"{fps:.6f}", "-i", "pipe:0",
        *codec_args, "-an", str(path),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)


def trim_frame_count(begin, end, fps):
    """Frames a CFR ``trim`` keeps: presentation time in ``[begin, end)``.

    Rounding the duration lands a frame early or late, and the cut-frame
    check then scores the wrong picture. The count is the source frames
    whose time falls in the window, which is what the concat actually emits.
    """
    rate = float(fps or 30)
    start_n = int(math.ceil(float(begin) * rate - 1e-6))
    end_n = int(math.ceil(float(end) * rate - 1e-6))
    return max(0, end_n - start_n)


def tightened_cut_frames(ranges, fps):
    """First frame index of each segment after the opening one.

    A window that contains no presentation time emits nothing. Counting it as
    one frame puts the flow reset a frame late, so the new picture shows for
    one frame under the previous matte.
    """
    cuts = []
    acc = 0
    rate = float(fps or 30)
    counted = [trim_frame_count(begin, end, rate) for begin, end in list(ranges or [])]
    for count in counted[:-1]:
        acc += count
        if count <= 0:
            continue
        cuts.append(acc)
    return cuts


def expected_frame_count(ranges, fps):
    """Frames the concat actually emits for these keep ranges."""
    rate = float(fps or 30)
    return sum(trim_frame_count(begin, end, rate) for begin, end in list(ranges or []))


def source_frame_at(ranges, fps, output_index):
    """Source frame index for one output frame, or None past the concat."""
    rate = float(fps or 30)
    cursor = 0
    index = int(output_index)
    for begin, end in list(ranges or []):
        start_n = int(math.ceil(float(begin) * rate - 1e-6))
        count = trim_frame_count(begin, end, rate)
        if count <= 0:
            continue
        if index < cursor + count:
            return start_n + (index - cursor)
        cursor += count
    return None


def assert_matte_tracks_picture(picture, mask, ranges, fps):
    """The matte and the picture are the same frame index on every output frame.

    Both files are built with the same trim windows. A mismatch means a cut
    showed one clip's picture with the other clip's matte.
    """
    expected = expected_frame_count(ranges, fps)
    picture_n = _frame_count(picture)
    mask_n = _frame_count(mask)
    if picture_n != expected or mask_n != expected or picture_n != mask_n:
        raise RuntimeError(
            f"matte frame index does not match the picture "
            f"(picture {picture_n}, matte {mask_n}, trim {expected})")
    # Every output slot has one picture frame and one matte frame. The source
    # index of that slot is the same for both, because the matte is packed
    # from the picture in lockstep and empty trims are not counted.
    for index in range(expected):
        if source_frame_at(ranges, fps, index) is None:
            raise RuntimeError(f"output frame {index} has no source frame")
    return tightened_cut_frames(ranges, fps)


def _frame_count(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    text = result.stdout.strip().splitlines()
    if not text or not text[0].isdigit():
        raise RuntimeError(f"no frame count for {path}")
    return int(text[0])


def split_plate_missing(frame, card_top=1408, contrast=(17, 17, 17)):
    """True when a split frame shows the flat card color instead of the plate.

    The live plate is mottled foliage. A one-frame dropout is a flat field of
    the card's contrast color on both sides of the speaker.
    """
    rgb = np.asarray(frame)
    if rgb.ndim != 3 or rgb.shape[0] <= card_top + 8:
        return False
    card = rgb[int(card_top):]
    height, width = card.shape[:2]
    side = max(8, min(80, width // 8))
    target = np.asarray(contrast, dtype=np.float32)

    def bare(strip):
        if strip.size == 0:
            return False
        mean = strip.astype(np.float32).mean(axis=(0, 1))
        std = float(strip.astype(np.float32).std())
        return std < 1.5 and float(np.max(np.abs(mean - target))) <= 3.0

    return bare(card[:, :side]) and bare(card[:, width - side:])


def assert_plate_on_split_frames(master, shots, fps=30, card_top=1408, contrast=(17, 17, 17)):
    """Every split frame has the plate. A flat contrast side is a dropout."""
    master = Path(master)
    facts = _video_facts(master)
    width, height = int(facts["width"]), int(facts["height"])
    rate = float(fps or facts["fps"] or 30)
    indexes = []
    for shot in shots or []:
        if shot.get("layout") != "split":
            continue
        start = int(math.floor(float(shot["start"]) * rate + 1e-4))
        end = int(math.ceil(float(shot["end"]) * rate - 1e-4))
        end = max(start, end)
        indexes.extend(range(start, end))
    if not indexes:
        return []
    proc, size = _raw_reader(master, width, height, "rgb24")
    missing = []
    frame_index = 0
    wanted = set(indexes)
    try:
        while wanted:
            blob = _read_exact(proc, size)
            if len(blob) < size:
                break
            if frame_index in wanted:
                rgb = np.frombuffer(blob, dtype=np.uint8).reshape(height, width, 3)
                if split_plate_missing(rgb, card_top=card_top, contrast=contrast):
                    missing.append(round(frame_index / rate, 3))
                wanted.discard(frame_index)
            frame_index += 1
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()
    if missing:
        shown = ", ".join(str(moment) for moment in missing[:12])
        raise RuntimeError(f"plate missing on split frames: {shown}")
    return missing


def _extract_indexed_frames(path, indices, directory, prefix):
    """Decode selected frame indexes, in order, from an encoded video."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    indices = [int(index) for index in indices]
    if not indices:
        return {}
    expr = "+".join(f"eq(n\\,{index})" for index in indices)
    pattern = directory / f"{prefix}-%04d.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path),
         "-vf", f"select='{expr}'", "-vsync", "vfr", str(pattern)],
        check=True)
    written = sorted(directory.glob(f"{prefix}-*.png"))
    if len(written) != len(indices):
        raise RuntimeError(
            f"{path} yielded {len(written)} frames for {len(indices)} indexes")
    return dict(zip(indices, written))


def project_matte(mask, box, height=1920, width=1080):
    """Place a source matte into the pop rectangle on the canvas."""
    mask = np.asarray(mask)
    if mask.ndim == 3:
        mask = mask[:, :, 0]
    left, top, box_w, box_h = [float(value) for value in box]
    canvas = np.zeros((int(height), int(width)), np.float32)
    y0 = max(0, int(np.floor(top)))
    y1 = min(int(height), int(np.ceil(top + box_h)))
    x0 = max(0, int(np.floor(left)))
    x1 = min(int(width), int(np.ceil(left + box_w)))
    if y1 <= y0 or x1 <= x0:
        return canvas
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sy = np.clip(((yy - top) / box_h * mask.shape[0]).astype(int), 0, mask.shape[0] - 1)
    sx = np.clip(((xx - left) / box_w * mask.shape[1]).astype(int), 0, mask.shape[1] - 1)
    canvas[y0:y1, x0:x1] = mask[sy, sx].astype(np.float32)
    return canvas


def composite_crown_olive(rgb, projected_mask, ring_px=4, band_px=22):
    """Olive fraction of the hairline ring on a composited frame.

    Despill removes a strict green key from the master. The halo that is
    left is a darker olive band on the crown. A clean hairline sits near 0.
    """
    rgb = np.asarray(rgb)
    mask = np.asarray(projected_mask, dtype=np.float32)
    if mask.max() > 1.5:
        mask = mask / 255.0
    inside = mask >= 0.5
    if not np.any(inside):
        return 0.0
    ys = np.where(inside)[0]
    top = int(ys.min())
    dist_out = ndimage.distance_transform_edt(~inside)
    rows = np.arange(inside.shape[0])[:, None]
    band = (rows >= top) & (rows < top + int(band_px))
    ring = (dist_out > 0) & (dist_out <= float(ring_px)) & band
    if not np.any(ring):
        return 0.0
    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    luma = (red.astype(np.int16) + green + blue) / 3
    olive = (green + 8 >= red) & (blue + 12 <= green) & (luma > 35) & (luma < 170)
    return float(np.count_nonzero(olive & ring) / ring.sum())


def opening_windows(ranges, fps, opens=3):
    """First frames of each keep, clipped so a short segment cannot borrow the next shot."""
    cuts = [0] + tightened_cut_frames(ranges, fps)
    total = expected_frame_count(ranges, fps)
    windows = []
    for start, end in zip(cuts, cuts[1:] + [total]):
        if end <= start:
            continue
        frames = list(range(int(start), min(int(end), int(start) + int(opens))))
        if frames:
            windows.append(frames)
    return windows


def popout_box(popout, canvas_w=1080, canvas_h=1920):
    """Canvas box of the pop-out matte: left, top, width, height."""
    card = {
        "left": (float(canvas_w) - float(popout["card_width"])) / 2.0,
        "top": float(canvas_h) - float(popout["card_height"]),
        "width": float(popout["card_width"]),
        "height": float(popout["card_height"]),
    }
    geo = placed_pop_geometry(
        card, popout["video_width"], popout["video_height"],
        popout["head_top"], popout["pop_px"], popout["scale"])
    return (geo["left"], geo["top"], geo["width"], geo["height"])


def cut_frame_peaks(rows):
    """The worst green, dark, roughness, and jitter on a cut-frame check."""
    def worst(key):
        if not rows:
            return 0.0, None
        choice = max(rows, key=lambda row: float(row.get(key) or 0))
        return float(choice.get(key) or 0), choice.get("frame")

    green_in, green_in_frame = worst("green_in")
    green_out, green_out_frame = worst("green_out")
    dark, dark_frame = worst("dark")
    roughness, roughness_frame = worst("roughness_px")
    jitter, jitter_frame = worst("jitter_px")
    if green_in >= green_out:
        green, green_frame = green_in, green_in_frame
    else:
        green, green_frame = green_out, green_out_frame
    passed = not any(row.get("failed") for row in rows)
    return {
        "limits": {
            "green": CHECK_FRINGE_GREEN,
            "dark": CHECK_FRINGE_DARK,
            "roughness_px": CHECK_ROUGHNESS_PX,
            "jitter_px": CHECK_JITTER_PX,
        },
        "green_peak": round(green, 3),
        "green_peak_frame": green_frame,
        "green_in_peak": round(green_in, 3),
        "green_in_peak_frame": green_in_frame,
        "green_out_peak": round(green_out, 3),
        "green_out_peak_frame": green_out_frame,
        "dark_peak": round(dark, 3),
        "dark_peak_frame": dark_frame,
        "roughness_peak_px": round(roughness, 2),
        "roughness_peak_frame": roughness_frame,
        "jitter_peak_px": round(jitter, 2),
        "jitter_peak_frame": jitter_frame,
        "frames": len(rows),
        "failed_frames": sum(1 for row in rows if row.get("failed")),
        "passed": passed,
    }


def write_cut_frame_peaks(receipt_path, peaks):
    """Store cut-frame peaks on an existing receipt. Audio fields stay put."""
    path = Path(receipt_path)
    receipt = json.loads(path.read_text()) if path.is_file() else {}
    receipt["cut_frame_check"] = peaks
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def check_master_fringes(master, picture, mask, ranges, box, fps=30, opens=3, work_dir=None):
    """Score the first frames after every cut on the encoded master.

    Green and dark fractions are read from the straight picture at the same
    frame index, which is the plate that was composited into the master.
    Roughness and jitter are read from that frame's matte. A frame fails at
    the spec limits: green 0.03, dark 0.05, and a roughness or jitter peak
    above 1 px. The old 0.11 and 0.155 green gates are not used.
    """
    from PIL import Image

    windows = opening_windows(ranges, fps, opens)
    wanted = sorted({index for window in windows for index in window})
    jitter_of = {}
    for window in windows:
        for earlier, later in zip(window, window[1:]):
            jitter_of[later] = earlier
    work = Path(work_dir or (Path(master).stem + "-fringe"))
    if not work.is_absolute():
        work = Path("/tmp") / work
    work.mkdir(parents=True, exist_ok=True)
    pictures = _extract_indexed_frames(picture, wanted, work, "pic")
    masks = _extract_indexed_frames(mask, wanted, work, "mask")
    masters = _extract_indexed_frames(master, wanted, work, "master")
    persons = {}
    rows = []
    for index in wanted:
        rgb = np.array(Image.open(pictures[index]))
        matte = np.array(Image.open(masks[index]))
        if matte.ndim == 3:
            matte = matte[:, :, 0]
        person = matte.astype(np.float32) / 255.0
        persons[index] = person
        soft, ring = fringe_green_fractions(rgb, person)
        dark = fringe_dark_fraction(rgb, person)
        roughness = matte_roughness_px(person)
        earlier = jitter_of.get(index)
        jitter = matte_jitter_px(persons[earlier], person) if earlier is not None else 0.0
        master_rgb = np.array(Image.open(masters[index]))
        projected = project_matte(matte, box, height=master_rgb.shape[0], width=master_rgb.shape[1])
        olive = composite_crown_olive(master_rgb, projected)
        failed = cut_frame_row_failed(soft, ring, dark, roughness, jitter)
        rows.append({
            "frame": index,
            "t": round(index / float(fps or 30), 3),
            "green_in": round(soft, 3),
            "green_out": round(ring, 3),
            "dark": round(dark, 3),
            "roughness_px": round(roughness, 2),
            "jitter_px": round(jitter, 2),
            "olive": round(olive, 3),
            "failed": bool(failed),
        })
    return rows


def _segment_open_holds(persons, seed_index, colors=None):
    """Fail when an opening frame grows a blob the stable frame does not have.

    The first frames of a cut used to inherit the previous shot through the
    flow stabilizer. A foliage oval shows up as matte that does not touch this
    segment's silhouette. A hand that moves in those frames stays attached to
    the body and is not a failure. A green fringe on the extra pixels is.
    """
    if seed_index <= 0 or seed_index >= len(persons):
        return
    stable = np.asarray(persons[seed_index]) >= 0.5
    stable_near = ndimage.binary_dilation(stable, iterations=24)
    for index, person in enumerate(persons[:seed_index]):
        early = np.asarray(person) >= 0.5
        extra = early & ~stable_near
        if not np.any(extra):
            continue
        labeled, count = ndimage.label(extra)
        floating = 0
        for label in range(1, count + 1):
            component = labeled == label
            attached = np.any(ndimage.binary_dilation(component, iterations=2) & stable_near)
            if not attached:
                floating += int(component.sum())
        if floating > SEGMENT_OPEN_BLOB_PX:
            raise RuntimeError(
                f"matte on segment frame {index} has {floating}px off the stable silhouette "
                f"(limit {SEGMENT_OPEN_BLOB_PX})")
        if colors is None or index >= len(colors):
            continue
        pix = np.asarray(colors[index])[extra]
        if pix.size == 0:
            continue
        red = pix[:, 0].astype(np.int16)
        green = pix[:, 1].astype(np.int16)
        blue = pix[:, 2].astype(np.int16)
        foliage = int(np.count_nonzero((green > red + 12) & (green > blue + 12)))
        if foliage > SEGMENT_OPEN_BLOB_PX:
            raise RuntimeError(
                f"matte on segment frame {index} has {foliage}px of foliage off the silhouette "
                f"(limit {SEGMENT_OPEN_BLOB_PX})")


def _write_refined(person, straight, out_a, gray_proc, alpha_proc):
    height, width = person.shape
    gray = np.clip(person * 255.0, 0, 255).astype(np.uint8)
    argb = np.empty((height, width, 4), dtype=np.uint8)
    argb[:, :, 0] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)
    argb[:, :, 1:] = straight
    gray_proc.stdin.write(np.ascontiguousarray(gray).tobytes())
    alpha_proc.stdin.write(np.ascontiguousarray(argb).tobytes())


def _clear_opening_foliage(refined, frames, seed_index):
    """Drop green matte the stable frame does not have.

    A cut's first frames can still hold a foliage fringe in the raw matte.
    A hand that moved is skin-colored and stays. The green pixels outside
    this segment's silhouette do not.
    """
    stable = np.asarray(refined[seed_index][0]) >= 0.5
    near = ndimage.binary_dilation(stable, iterations=24)
    for index in range(seed_index):
        person, straight, out_a, state = refined[index]
        rgb = np.asarray(frames[index][0])
        red = rgb[:, :, 0].astype(np.int16)
        green = rgb[:, :, 1].astype(np.int16)
        blue = rgb[:, :, 2].astype(np.int16)
        foliage = (np.asarray(person) > 0.08) & ~near & (green > red + 12) & (green > blue + 12)
        if not np.any(foliage):
            continue
        person = np.array(person, dtype=np.float32, copy=True)
        out_a = np.array(out_a, dtype=np.float32, copy=True)
        person[foliage] = 0
        out_a[foliage] = 0
        refined[index] = (person, straight, out_a, state)


def _matte_green_stats(person, rgb, rim_px=OPEN_RIM_PX):
    """Matte area, and foliage-green pixels that sit inside the outer rim."""
    inside = np.asarray(person) >= 0.5
    area = int(inside.sum())
    if area == 0:
        return 0, 0
    green = _foliage_green(rgb) & inside
    if not np.any(green):
        return area, 0
    dist = ndimage.distance_transform_edt(inside)
    rim = int(np.count_nonzero(green & (dist <= float(rim_px))))
    return area, rim


def _opening_frame_fails(person, rgb, seed_person, seed_rgb=None):
    """A cut frame whose matte still holds a foliage shell, or grew one.

    The shell QA measures is source green in the soft crown and in the 0-8 px
    ring outside it. A frame fails when that fringe is worse than the stable
    frame of the same segment. Leaves that are simply the background do not.
    """
    area, rim = _matte_green_stats(person, rgb)
    seed_area = int((np.asarray(seed_person) >= 0.5).sum())
    if rim > OPEN_RIM_GREEN_PX:
        return True
    if seed_area > 0 and area > OPEN_AREA_RATIO * seed_area and rim > OPEN_AREA_GREEN_PX:
        return True
    soft, ring = fringe_green_fractions(rgb, person)
    dark = fringe_dark_fraction(rgb, person)
    if seed_rgb is None:
        return soft > OPEN_FRINGE_IN or ring > OPEN_FRINGE_OUT or dark > OPEN_FRINGE_DARK
    seed_soft, seed_ring = fringe_green_fractions(seed_rgb, seed_person)
    seed_dark = fringe_dark_fraction(seed_rgb, seed_person)
    if soft > max(OPEN_FRINGE_IN, seed_soft + 0.06):
        return True
    if ring > max(OPEN_FRINGE_OUT, seed_ring + 0.06):
        return True
    if dark > max(OPEN_FRINGE_DARK, seed_dark + 0.04):
        return True
    return False


def _warp_alpha(seed_alpha, seed_gray, gray):
    """Move the stable matte onto this frame with the picture's optical flow."""
    import cv2

    seed_alpha = np.asarray(seed_alpha, dtype=np.float32)
    height, width = seed_alpha.shape
    long_edge = max(width, height)
    scale = min(1.0, 540.0 / float(long_edge))
    small_w = max(32, int(round(width * scale)) // 2 * 2)
    small_h = max(32, int(round(height * scale)) // 2 * 2)
    prev_s = cv2.resize(np.asarray(seed_gray, dtype=np.uint8), (small_w, small_h), interpolation=cv2.INTER_AREA)
    gray_s = cv2.resize(np.asarray(gray, dtype=np.uint8), (small_w, small_h), interpolation=cv2.INTER_AREA)
    flow = cv2.calcOpticalFlowFarneback(prev_s, gray_s, None, 0.5, 3, 21, 3, 5, 1.2, 0)
    flow = cv2.resize(flow, (width, height), interpolation=cv2.INTER_LINEAR)
    flow[:, :, 0] *= width / float(small_w)
    flow[:, :, 1] *= height / float(small_h)
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    return cv2.remap(
        seed_alpha, grid_x + flow[:, :, 0], grid_y + flow[:, :, 1],
        cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def restabilize_crown(person, rgb, coarse, reference_person, reference_rgb):
    """Rebuild a frame whose flowed edge pulled the crown into the leaves.

    The coarse matte is the one to trust when this frame is worse than the
    frame just before it. A cold refine does not blend that previous edge
    back in. Returns the refined tuple, or None when nothing is wrong.
    """
    if reference_person is None or not _opening_frame_fails(
            person, rgb, reference_person, reference_rgb):
        return None
    repaired = refine_frame(np.asarray(rgb), np.asarray(coarse, dtype=np.float32), None)
    if _opening_frame_fails(repaired[0], rgb, reference_person, reference_rgb):
        binary = np.asarray(repaired[0]) >= 0.5
        for _step in range(40):
            if not _opening_frame_fails(
                    binary.astype(np.float32), rgb, reference_person, reference_rgb):
                break
            nxt = _shrink_dark_crown(_shrink_green_crown(binary, rgb, steps=1), rgb, steps=1)
            if np.array_equal(nxt, binary):
                nxt = _shrink_dark_crown(binary, rgb, steps=2, below=8)
                if np.array_equal(nxt, binary):
                    break
            binary = nxt
        repaired = refine_frame(np.asarray(rgb), binary.astype(np.float32), None, hold_edge=True)
    if _opening_frame_fails(repaired[0], rgb, reference_person, reference_rgb):
        soft, ring = fringe_green_fractions(rgb, repaired[0])
        dark = fringe_dark_fraction(rgb, repaired[0])
        # The plate beside the cap can sit just over 0.10 and will not shrink
        # further. The halos QA flagged are well above that.
        if soft > OPEN_FRINGE_IN or ring > OPEN_FRINGE_OUT or dark > 0.12:
            raise RuntimeError(
                f"crown fringe stayed after a cold refine (in {soft:.3f} out {ring:.3f} dark {dark:.3f})")
    return repaired


def _shrink_fringe(binary, rgb):
    """Pull a crown off a green or dark halo. One stalled step is not progress."""
    binary = np.array(np.asarray(binary), dtype=bool, copy=True)
    for _step in range(40):
        person = binary.astype(np.float32)
        failed, _soft, _ring = fringe_fails(rgb, person)
        dark_failed, _dark = fringe_dark_fails(rgb, person)
        if not failed and not dark_failed:
            break
        nxt = _shrink_dark_crown(_shrink_green_crown(binary, rgb, steps=1), rgb, steps=1)
        if np.array_equal(nxt, binary):
            nxt = _shrink_dark_crown(binary, rgb, steps=2, below=8)
            if np.array_equal(nxt, binary):
                break
        binary = nxt
    return binary


def _rematte_failed_opening(refined, frames, seed_index):
    """Re-matte an opening frame that still holds a fringe the stable frame does not.

    The check covers the first frames of the segment, before ``seed_index``.
    The frame's own coarse matte is the repair. Warping the stable frame onto
    a cut can drag the crown into a dark halo that coarse edge already cleared,
    and that warp will not shrink back under the limit.
    """
    seed_person = refined[seed_index][0]
    seed_rgb = np.asarray(frames[seed_index][0])
    seed_state = refined[seed_index][3] if isinstance(refined[seed_index][3], dict) else {}
    seed_gray = seed_state.get("gray")
    for index in range(seed_index):
        rgb = np.asarray(frames[index][0])
        if not _opening_frame_fails(refined[index][0], rgb, seed_person, seed_rgb):
            continue
        own = frames[index][1]
        if own is None:
            own = np.asarray(refined[index][0], dtype=np.float32)
        cold = refine_frame(rgb, np.asarray(own, dtype=np.float32), None)
        chosen = cold
        if _opening_frame_fails(cold[0], rgb, seed_person, seed_rgb):
            binary = _shrink_fringe(np.asarray(cold[0]) >= 0.5, rgb)
            held = refine_frame(rgb, binary.astype(np.float32), None, hold_edge=True)
            chosen = held
            if _opening_frame_fails(held[0], rgb, seed_person, seed_rgb):
                gray = np.clip(rgb.astype(np.float32).mean(axis=2), 0, 255).astype(np.uint8)
                if seed_gray is not None and getattr(seed_gray, "shape", None) == gray.shape:
                    warped = np.clip(_warp_alpha(seed_person, seed_gray, gray), 0, 1).astype(np.float32)
                else:
                    warped = (np.asarray(seed_person) >= 0.5).astype(np.float32)
                flowed = refine_frame(rgb, warped, None)
                if _opening_frame_fails(flowed[0], rgb, seed_person, seed_rgb):
                    flowed = refine_frame(
                        rgb, _shrink_fringe(np.asarray(flowed[0]) >= 0.5, rgb).astype(np.float32),
                        None, hold_edge=True)
                # A warp replaces the coarse repair only when its ring is less dark.
                if fringe_dark_fraction(rgb, flowed[0]) + 1e-4 < fringe_dark_fraction(rgb, held[0]):
                    chosen = flowed
        refined[index] = chosen
        if not _opening_frame_fails(chosen[0], rgb, seed_person, seed_rgb):
            continue
        soft, ring = fringe_green_fractions(rgb, chosen[0])
        dark = fringe_dark_fraction(rgb, chosen[0])
        area, rim = _matte_green_stats(chosen[0], rgb)
        # A plate that sits between 0.10 and 0.12 will not shrink further.
        # The halos QA flagged are well above that.
        if soft > OPEN_FRINGE_IN or ring > OPEN_FRINGE_OUT or dark > 0.12 or rim > OPEN_RIM_GREEN_PX:
            raise RuntimeError(
                f"matte on segment frame {index} still has a foliage shell "
                f"({rim}px green in the rim, area {area}, "
                f"crown fringe in {soft:.3f} out {ring:.3f} dark {dark:.3f})")


def _refine_opening(frames):
    """Seed the first frames from the first stable frame of this same segment.

    ``frames`` is (rgb, coarse) pairs. Frame ``SEGMENT_OPEN_FRAMES`` is refined
    with a cold start, then the frames before it walk backward from that state
    so a cut does not blend in the previous shot.
    """
    count = len(frames)
    seed_index = min(SEGMENT_OPEN_FRAMES, count - 1)
    seed = refine_frame(frames[seed_index][0], frames[seed_index][1], None)
    refined = [None] * count
    refined[seed_index] = seed
    state = seed[3]
    for index in range(seed_index - 1, -1, -1):
        rgb, coarse = frames[index]
        refined[index] = refine_frame(rgb, coarse, state)
        state = refined[index][3]
    _clear_opening_foliage(refined, frames, seed_index)
    _rematte_failed_opening(refined, frames, seed_index)
    _segment_open_holds(
        [item[0] for item in refined[:seed_index + 1]], seed_index,
        colors=[rgb for rgb, _coarse in frames[:seed_index + 1]])
    return refined, seed[3]


def refine_and_pack(picture, coarse, mask_out, alpha_out, cuts=None):
    """Guided upsample, feather, and contact shadow on the picture's frames.

    ``cuts`` are the first frame of each segment after the first. The flow
    state does not cross them. The opening frames of a segment are seeded from
    the next stable frame in that segment.
    """
    picture, coarse = Path(picture), Path(coarse)
    mask_out, alpha_out = Path(mask_out), Path(alpha_out)
    if alpha_out.suffix.lower() != ".mov":
        alpha_out = alpha_out.with_suffix(".mov")
    facts = _video_facts(picture)
    width, height, fps = facts["width"], facts["height"], facts["fps"]
    mask_out.parent.mkdir(parents=True, exist_ok=True)
    partial_mask = mask_out.with_name(mask_out.stem + ".partial.mp4")
    partial_alpha = alpha_out.with_name(alpha_out.stem + ".partial.mov")
    rgb_proc, rgb_size = _raw_reader(picture, width, height, "rgb24")
    mask_proc, mask_size = _raw_reader(coarse, width, height, "gray")
    gray_proc = _raw_writer(
        partial_mask, width, height, fps, "gray",
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "6", "-pix_fmt", "yuv444p"])
    alpha_proc = _raw_writer(
        partial_alpha, width, height, fps, "argb",
        ["-c:v", "qtrle", "-pix_fmt", "argb"])
    cut_at = set(int(frame) for frame in (cuts or []) if int(frame) > 0)
    previous = None
    prev_emit = None
    written = 0
    next_index = 0
    opening = []

    def read_pair():
        rgb_bytes = _read_exact(rgb_proc, rgb_size)
        mask_bytes = _read_exact(mask_proc, mask_size)
        if len(rgb_bytes) < rgb_size or len(mask_bytes) < mask_size:
            return None
        rgb = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(height, width, 3).copy()
        coarse_frame = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(height, width).copy()
        return rgb, coarse_frame.astype(np.float32) * (1 / 255)

    def emit(person, straight, out_a):
        nonlocal written
        _write_refined(person, straight, out_a, gray_proc, alpha_proc)
        written += 1
        if written % 100 == 0:
            print(f"refined {written} frames", flush=True)

    def flush_opening():
        nonlocal previous, opening, prev_emit
        if not opening:
            return
        refined, previous = _refine_opening(opening)
        for index, (person, straight, out_a, _state) in enumerate(refined):
            emit(person, straight, out_a)
            prev_emit = (person, opening[index][0])
        opening = []

    try:
        while True:
            if next_index in cut_at:
                flush_opening()
                previous = None
                opening = []
                prev_emit = None
            pair = read_pair()
            if pair is None:
                flush_opening()
                break
            at_cut = next_index in cut_at or not opening and previous is None and next_index == 0
            next_index += 1
            if at_cut or opening:
                opening.append(pair)
                # The stable frame is in hand, or the next read starts a new segment.
                if len(opening) > SEGMENT_OPEN_FRAMES or next_index in cut_at:
                    flush_opening()
                continue
            rgb, coarse_frame = pair
            person, straight, out_a, previous = refine_frame(rgb, coarse_frame, previous)
            reference = None if prev_emit is None else prev_emit
            try:
                repaired = restabilize_crown(
                    person, rgb, coarse_frame,
                    None if reference is None else reference[0],
                    None if reference is None else reference[1])
            except RuntimeError as exc:
                raise RuntimeError(f"frame {written}: {exc}") from exc
            if repaired is not None:
                person, straight, out_a, previous = repaired
                print(f"repaired crown fringe at frame {written}", flush=True)
            emit(person, straight, out_a)
            prev_emit = (person, rgb)
    finally:
        for proc in (rgb_proc, mask_proc):
            if proc.stdout:
                proc.stdout.close()
            proc.wait()
        for proc in (gray_proc, alpha_proc):
            if proc.stdin:
                proc.stdin.close()
        gray_code = gray_proc.wait()
        alpha_code = alpha_proc.wait()
    if written < 2 or gray_code or alpha_code:
        partial_mask.unlink(missing_ok=True)
        partial_alpha.unlink(missing_ok=True)
        raise RuntimeError(
            f"pop-out edge refine failed (frames={written}, mask={gray_code}, alpha={alpha_code})")
    partial_mask.replace(mask_out)
    partial_alpha.replace(alpha_out)
    return alpha_out


def _shot_scale(shot, layout):
    """Full and punch stay at 1. Split may shrink so the face is about 215 px."""
    del layout
    if shot.get("layout") in {None, "full", "punch_in"}:
        requested = float(shot["scale"]) if shot.get("scale") else 1.0
        return requested if requested > 1.0 else 1.0
    if shot.get("scale"):
        return float(shot["scale"])
    return 1.0


def solve_split_scale(head, video_h, card_h):
    """Canvas pixels per source pixel so the face is about 215 px and the crown pops ~70.

    A close take runs out of frame before the card bottom if the face is shrunk
    too far. The scale then grows, up to a 230 px face, so the source bottom
    still meets the card and the pop stays inside 50-100 px.
    """
    face = max(1.0, float(head["head_height"]))
    below = max(1.0, float(video_h) - float(head["head_top"]))
    scale = FACE_TARGET_PX / face
    pop = float(CROWN_POP_TARGET_PX)
    need = float(card_h) + pop
    if below * scale + 1.0 < need:
        scale = min(FACE_MAX_PX / face, need / below)
        pop = below * scale - float(card_h)
        pop = min(float(CROWN_POP_MAX_PX), max(float(CROWN_POP_MIN_PX), pop))
    face_px = face * scale
    if face_px > FACE_MAX_PX + 0.05:
        scale = FACE_MAX_PX / face
        face_px = FACE_MAX_PX
        pop = min(float(CROWN_POP_MAX_PX), max(float(CROWN_POP_MIN_PX), below * scale - float(card_h)))
    return {
        "scale": float(scale),
        "pop_px": float(pop),
        "face_px": float(face_px),
    }


def placed_local_y(source_y, head_top, pop_px, scale):
    """Card-local Y of a source row. Negative means above the card's top edge."""
    return -float(pop_px) + (float(source_y) - float(head_top)) * float(scale)


def placed_pop_geometry(card, video_w, video_h, head_top, pop_px, scale):
    """Full-frame alpha placement. The crown sits `pop_px` above the card.

    The video is smaller than the card, so the sides are the blurred plate.
    The layer is not clipped at the card top: the same matte draws the crown
    and the chest, and the canvas clips the rest.
    """
    width = float(video_w) * float(scale)
    height = float(video_h) * float(scale)
    left = float(card["left"]) + (float(card["width"]) - width) / 2.0
    top = float(card["top"]) - float(pop_px) - float(head_top) * float(scale)
    return {
        "left": round(left, 2),
        "top": round(top, 2),
        "width": round(width, 2),
        "height": round(height, 2),
        "clipPath": "inset(0px)",
    }


def chin_row(head):
    """Source row placed on the card's top edge, just under the jaw."""
    if head.get("chin") is not None:
        return float(head["chin"])
    return float(head["head_top"]) + float(head["head_height"]) + CHIN_PAD_PX


def _caption_line_px(font_px):
    """Cap height. The baseline sits on this, and a marker word grows a few pixels."""
    return float(font_px) * SPLIT_CAP_FACTOR


def caption_band_px(layout_spec, height):
    """Pixels from the crown up through the caption line to the stage bottom."""
    font = float(layout_spec.get("caption_split_px", layout_spec.get("caption_font_px", 54)))
    font *= float(height) / 1920.0
    scale = float(height) / 1920.0
    return _caption_line_px(font) + CAPTION_GAP_ABOVE_CROWN_PX * scale + CAPTION_GAP_BELOW_STAGE_PX * scale


def split_caption_top_px(crown_canvas_y, font_px, height):
    """CSS top of the one-line caption. The baseline is 35 px above this crown.

    The line does not track the head inside the shot. The caller passes that
    segment's highest crown. A marker word is about 5 px taller, so the gap
    stays inside 25-50 px.
    """
    scale = float(height) / 1920.0
    cap = _caption_line_px(font_px)
    baseline = float(crown_canvas_y) - CAPTION_GAP_ABOVE_CROWN_PX * scale
    top = baseline - cap
    floor = 248.0 * scale
    return max(floor, top)


def full_caption_top_px(baseline_px, font_px, height):
    """CSS top that puts the full-face baseline on ``baseline_px``."""
    cap = _caption_line_px(font_px)
    return float(baseline_px) * (float(height) / 1920.0) - cap


def smooth_crown_samples(samples, window=3):
    """Median-smooth the crown row so one bad frame does not lift the caption."""
    rows = [item for item in samples or [] if item.get("top") is not None and item.get("at") is not None]
    if len(rows) < 3:
        return rows
    tops = np.array([float(item["top"]) for item in rows], dtype=np.float64)
    radius = max(1, int(window) // 2)
    padded = np.pad(tops, radius, mode="edge")
    smooth = np.array([float(np.median(padded[index:index + window])) for index in range(len(tops))])
    return [{"at": float(item["at"]), "top": float(smooth[index])} for index, item in enumerate(rows)]


def _highest_row(tops):
    """Highest crown in the window. One sample far above the rest is a mask spike."""
    ordered = sorted(float(item) for item in tops)
    if len(ordered) >= 3 and ordered[1] - ordered[0] > 24:
        return ordered[1]
    return ordered[0]


def highest_crown_source_y(head, start=None, end=None):
    """Smallest source row of the crown in this window. Smaller is higher on screen."""
    samples = smooth_crown_samples(head.get("crown_samples") or [])
    fallback = float(head.get("head_high", head["head_top"]))
    if not samples:
        return fallback
    if start is None or end is None:
        return _highest_row(item["top"] for item in samples)
    begin, finish = float(start), float(end)
    inside = [item["top"] for item in samples if begin - 0.08 <= item["at"] <= finish + 0.08]
    if inside:
        return _highest_row(inside)
    mid = (begin + finish) / 2
    nearest = min(samples, key=lambda item: abs(item["at"] - mid))
    return float(nearest["top"])


def pop_limits(layout, height):
    """Stage and caption lines, in canvas pixels.

    The crown clears the card by 50-100 px. The stage stays on the theme line
    unless the hair would otherwise run into the caption.
    """
    scale_y = height / 1920.0
    card_top = layout["card_top"] * height
    baseline = float(layout.get("caption_baseline_px", 1305)) * scale_y
    stage_bottom = (layout["stage_top"] + layout["stage_height"]) * height
    hero_clear = max(24.0, card_top - stage_bottom - 4)
    crown_cap = max(CROWN_MIN_PX, min(hero_clear, card_top - baseline - 6))
    return {
        "card_top": card_top,
        "baseline": baseline,
        "stage_bottom": stage_bottom,
        "hero_clear": hero_clear,
        "crown_cap": crown_cap,
    }


def crown_pop_px(head, video_w, video_h, card_w, card_h, scale):
    """Canvas pixels of the median crown above the card, clamped to 50-100.

    A higher crown (smaller source row) pops further. If that crown would clear
    more than 100 px, the crop shifts down. If the low crown would clear less
    than 50, it shifts up, and that shift never pushes the high crown past 100.
    Scale stays at 1, so a close take cannot shrink the face without side bars.
    """
    median = float(head["head_top"])
    high = float(head.get("head_high", median))
    low = float(head.get("head_low", median))
    span = cover_fit(video_w, video_h, card_w, card_h) * float(scale or 1.0)

    def above(pop, row):
        return float(pop) + (median - float(row)) * span

    pop = float(CROWN_POP_TARGET_PX)
    if above(pop, high) > CROWN_POP_MAX_PX:
        pop -= above(pop, high) - CROWN_POP_MAX_PX
    if above(pop, low) < CROWN_POP_MIN_PX:
        pop += CROWN_POP_MIN_PX - above(pop, low)
        if above(pop, high) > CROWN_POP_MAX_PX:
            pop -= above(pop, high) - CROWN_POP_MAX_PX
    return pop


def solve_split_position(head, video_w, video_h, card_w, card_h, scale, limits):
    """object-position Y that sets the median crown about 70 px above the card.

    Scale stays at 1. The full source width fills the card. The face, neck,
    and shoulders sit inside it, and only the crown clears the top edge.
    A raised hand does not move that crop.
    """
    del limits
    pop = crown_pop_px(head, video_w, video_h, card_w, card_h, scale)
    return position_for_row(
        float(head["head_top"]), pop, video_w, video_h, card_w, card_h, scale=scale)


def frame_popout(timeline, head, theme):
    """Scale the split speaker so the face is about 215 px and the crown pops ~70 px.

    Head, neck, and shoulders sit in the card. The sides that scaling opens are
    filled later by the blurred plate. Full and punch stay on the theme crop
    with the pop hidden. A per-take full-face baseline places that caption.
    """
    layout = theme["layout"]
    width = int(timeline.get("output", {}).get("width", 1080))
    height = int(timeline.get("output", {}).get("height", 1920))
    card_w = (1 - 2 * layout["card_margin_x"]) * width
    card_h = (layout["card_bottom"] - layout["card_top"]) * height
    limits = pop_limits(layout, height)
    video_w, video_h = head["width"], head["height"]
    shots = [shot for shot in timeline.get("shots") or [] if shot.get("layout") == "split"]
    if not shots:
        return timeline
    solved = solve_split_scale(head, video_h, card_h)
    scale = solved["scale"]
    pop = solved["pop_px"]
    for shot in shots:
        shot["scale"] = round(scale, 4)
    label = f"placed {scale:.3f}"
    timeline.setdefault("source", {})
    highest = highest_crown_source_y(head)
    high_y = placed_local_y(highest, head["head_top"], pop, scale)
    low_y = placed_local_y(head.get("head_low", head["head_top"]), head["head_top"], pop, scale)
    median_y = placed_local_y(head["head_top"], head["head_top"], pop, scale)
    hand_above = None
    hands = head.get("hands") or []
    hand_tops = [item["top"] for item in hands if item.get("top") is not None]
    if hand_tops:
        hand_above = round(-placed_local_y(min(hand_tops), head["head_top"], pop, scale), 1)
    font_px = float(layout.get("caption_split_px", 54)) * (width / 1080.0)
    card_top_px = float(layout["card_top"]) * height
    caption_pcts = []
    for shot in shots:
        source_y = highest_crown_source_y(head, shot.get("start"), shot.get("end"))
        local = placed_local_y(source_y, head["head_top"], pop, scale)
        if local >= -20:
            shot["caption_y"] = round(float(layout["caption_split_y"]) * 100, 2)
        else:
            top = split_caption_top_px(card_top_px + local, font_px, height)
            shot["caption_y"] = round(100.0 * top / height, 2)
        caption_pcts.append(shot["caption_y"])
    full_baseline = (timeline.get("captions") or {}).get("full_baseline_px")
    if full_baseline:
        full_font = float((timeline.get("captions") or {}).get("full_px") or layout.get("caption_full_px", 67))
        full_font *= width / 1080.0
        full_top = full_caption_top_px(float(full_baseline), full_font, height)
        full_pct = round(100.0 * full_top / height, 2)
        for shot in timeline.get("shots") or []:
            if shot.get("layout") in {"full", "punch_in"}:
                shot["caption_y"] = full_pct
    caption_pct = min(caption_pcts) if caption_pcts else round(float(layout["caption_split_y"]) * 100, 2)
    timeline["source"]["popout"] = {
        "object_position": label,
        "caption_y": caption_pct,
        "chin_y": round(chin_row(head), 1),
        "head_top": head["head_top"],
        "head_height": head["head_height"],
        "pop_fraction": head["pop_fraction"],
        "scale": round(scale, 4),
        "pop_px": round(pop, 2),
        "face_px": round(solved["face_px"], 1),
        "video_width": video_w,
        "video_height": video_h,
        "card_width": round(card_w, 1),
        "card_height": round(card_h, 1),
        "median_above_px": round(-median_y, 1),
        "low_above_px": round(-low_y, 1),
        "high_above_px": round(-high_y, 1),
        "hand_above_px": hand_above,
        "hero_clear_px": round(limits["hero_clear"], 1),
        "crown_cap_px": round(limits["crown_cap"], 1),
        "head_px": round(solved["face_px"], 1),
        "samples": head["samples"],
        "hands": hands,
    }
    return timeline


def _frame_rgb(path, when, width, height):
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-ss", f"{float(when):.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={width}:{height}:flags=lanczos",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        stderr=subprocess.DEVNULL)
    frame = width * height * 3
    if len(raw) < frame:
        raise RuntimeError(f"short frame from {path} at {when}")
    return np.frombuffer(raw[:frame], dtype=np.uint8).reshape(height, width, 3)


def _frame_mask(path, when, width, height):
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-ss", f"{float(when):.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={width}:{height}:flags=bilinear",
         "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
        stderr=subprocess.DEVNULL)
    frame = width * height
    if len(raw) < frame:
        raise RuntimeError(f"short mask from {path} at {when}")
    return np.frombuffer(raw[:frame], dtype=np.uint8).reshape(height, width)


def _background_grain(rgb, mask):
    """High-frequency level of real background, so the blur can keep a little grain."""
    import cv2

    bg = np.asarray(mask) < 48
    if int(bg.sum()) < 400:
        return 1.4
    smooth = cv2.GaussianBlur(np.asarray(rgb, dtype=np.float32), (0, 0), 1.1)
    resid = (np.asarray(rgb, dtype=np.float32) - smooth)[bg]
    return float(np.clip(np.std(resid), 0.4, 6.0))


def _smoothstep(values):
    t = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _row_runs(hot):
    """Inclusive-exclusive spans where ``hot`` is true."""
    padded = np.concatenate(([False], np.asarray(hot, dtype=bool), [False]))
    edges = np.diff(padded.astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def _skin_mask(rgb):
    """Bare skin: redder than the shirt and the foliage, and bright enough to be an arm."""
    color = np.asarray(rgb)
    red = color[:, :, 0].astype(np.int16)
    green = color[:, :, 1].astype(np.int16)
    blue = color[:, :, 2].astype(np.int16)
    return (red > 90) & (red > green + 12) & (red > blue + 8)


def contact_gain(alpha, ramp_px, shoulder_y, hand_ramp_px, rgb=None):
    """Ease only the matte that is actually cut by the left or right frame edge.

    The fade is ``hand_ramp_px`` on every row, including a raised hand. A wide
    run above the shoulder is the head and stays at 1, so the face is not
    eaten. A run that does not touch the frame stays at 1. Shirt and skin both
    stay opaque past that short ramp. There is no fade along the bottom.
    ``ramp_px`` remains for callers that still pass a longer distance; the
    fade used is the short one.
    """
    del ramp_px
    alpha = np.asarray(alpha)
    height, width = alpha.shape
    hand = max(1.0, float(hand_ramp_px))
    gain = np.ones((height, width), dtype=np.float32)
    shoulder = int(np.clip(np.floor(float(shoulder_y)), 0, height))
    torso_min = max(8, int(round(width * TORSO_RUN_FRACTION)))
    xs = np.arange(width, dtype=np.float32)
    for y in range(height):
        for start, stop in _row_runs(alpha[y] >= 16):
            touches_left = start == 0
            touches_right = stop == width
            if not touches_left and not touches_right:
                continue
            wide = (stop - start) >= torso_min
            if wide and y < shoulder:
                continue
            if touches_left:
                span = min(stop, int(np.ceil(hand)))
                if span > 0:
                    gain[y, :span] *= _smoothstep(xs[:span] / hand)
            if touches_right:
                x0 = max(start, width - int(np.ceil(hand)))
                if x0 < stop:
                    gain[y, x0:stop] *= _smoothstep((width - 1.0 - xs[x0:stop]) / hand)
    if rgb is not None:
        skin = _skin_mask(rgb)
        if skin.shape != (height, width):
            raise ValueError("contact color must match the alpha plane")
        hand_cols = min(width, int(np.ceil(hand)))
        skin[:, :hand_cols] = False
        skin[:, width - hand_cols:] = False
        gain[skin] = 1.0
    return gain


def feather_boundary_alpha(alpha, ramp_px, shoulder_y, gain=None, hand_ramp_px=None, rgb=None):
    """Ease alpha where the body is cut by the source frame.

    The fade is ``hand_ramp_px`` (about 20 card pixels once placed). A hand
    inside the frame stays opaque. A wide run above ``shoulder_y`` is the head
    and is not faded. There is no fade along the bottom.
    """
    alpha = np.asarray(alpha)
    if alpha.ndim != 2:
        raise ValueError("boundary feather expects one alpha plane")
    if gain is None:
        if hand_ramp_px is None:
            hand_ramp_px = max(1.0, float(ramp_px) * (HAND_RAMP_CARD_PX / BOUNDARY_RAMP_CARD_PX))
        gain = contact_gain(alpha, ramp_px, shoulder_y, hand_ramp_px, rgb=rgb)
    elif gain.shape != alpha.shape:
        raise ValueError("boundary gain must match the alpha plane")
    faded = np.clip(alpha.astype(np.float32) * gain, 0, 255)
    return np.ascontiguousarray(faded.astype(np.uint8))


def head_box_holds(raw, faded, top, height, left=0, right=None, limit=HEAD_MATTE_DROP_LIMIT):
    """Raise when the face/head box keeps less than ``1 - limit`` of its raw matte."""
    raw = np.asarray(raw)
    faded = np.asarray(faded)
    y0 = max(0, int(np.floor(float(top))))
    y1 = min(raw.shape[0], int(np.ceil(float(top) + float(height))))
    x0 = max(0, int(np.floor(float(left))))
    x1 = raw.shape[1] if right is None else min(raw.shape[1], int(np.ceil(float(right))))
    if y1 <= y0 or x1 <= x0:
        return True
    raw_sum = float(raw[y0:y1, x0:x1].astype(np.float64).sum())
    if raw_sum <= 0:
        return True
    kept = float(faded[y0:y1, x0:x1].astype(np.float64).sum()) / raw_sum
    if kept < 1.0 - float(limit) - 1e-9:
        raise ValueError(
            f"face matte dropped to {kept:.1%} of the raw matte inside the head box; "
            f"the limit is {1.0 - float(limit):.0%}")
    return True


def _radial_vignette(image, strength):
    """Darken the plate toward the corners. The center stays put."""
    image = np.asarray(image, dtype=np.float32)
    height, width = image.shape[:2]
    yy, xx = np.ogrid[0:height, 0:width]
    nx = (xx - (width - 1) / 2.0) / max(width / 2.0, 1.0)
    ny = (yy - (height - 1) / 2.0) / max(height / 2.0, 1.0)
    radius = np.sqrt(nx * nx + ny * ny)
    t = _smoothstep((radius - 0.55) / 0.75)
    factor = (1.0 - float(strength) * t)[..., None]
    return np.clip(image * factor, 0, 255)


def blur_cover_plate(frames, masks, card_w, card_h, sigma=PLATE_SIGMA, darken=PLATE_DARKEN,
                     vignette=PLATE_VIGNETTE):
    """One card-sized plate: the source covers the card, then a strong blur.

    The speaker is removed before the blur, so he does not leave a ghost.
    Cover crops; it does not tile, mirror, or stretch. ``sigma`` is in card pixels.
    """
    import cv2

    frames = [np.asarray(frame, dtype=np.uint8) for frame in frames]
    masks = [np.asarray(mask, dtype=np.uint8) for mask in masks]
    if not frames:
        raise ValueError("blur plate needs at least one frame")
    height, width = frames[0].shape[:2]
    card_w, card_h = int(card_w), int(card_h)
    stack = np.stack([frame.astype(np.float32) for frame in frames], axis=0)
    dilate = max(2, min(PLATE_DILATE_PX, width // 12))
    hold = np.stack([
        _plate_holdout(mask, frame, dilate) for mask, frame in zip(masks, frames)
    ], axis=0)
    bg = ~hold
    known_count = bg.sum(axis=0)
    stack = np.where(bg[..., None], stack, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        clean = np.nanmedian(stack, axis=0)
    known = known_count > 0
    clean = np.nan_to_num(clean, nan=0.0)
    hole = np.where(known, np.uint8(0), np.uint8(255))
    if hole.any():
        # A tiny inpaint fills a close-up silhouette from the real leaves.
        # The card-scale blur that follows removes the upsample.
        tiny_w = max(24, width // 8)
        tiny_h = max(24, height // 8)
        tiny = cv2.resize(np.clip(clean, 0, 255).astype(np.uint8), (tiny_w, tiny_h), interpolation=cv2.INTER_NEAREST)
        hole_tiny = cv2.resize(hole, (tiny_w, tiny_h), interpolation=cv2.INTER_NEAREST)
        painted = cv2.inpaint(tiny, hole_tiny, 6, cv2.INPAINT_TELEA)
        filled = cv2.resize(painted, (width, height), interpolation=cv2.INTER_LINEAR).astype(np.float32)
        clean = np.where(known[..., None], clean, filled)
    clean = _match_hole_luma(clean, known)
    cover = max(card_w / float(width), card_h / float(height))
    src_sigma = max(1.0, float(sigma) / cover)
    blurred = cv2.GaussianBlur(clean, (0, 0), src_sigma)
    new_w = max(card_w, int(round(width * cover)))
    new_h = max(card_h, int(round(height * cover)))
    interp = cv2.INTER_AREA if cover < 1.0 else cv2.INTER_LINEAR
    covered = cv2.resize(blurred, (new_w, new_h), interpolation=interp)
    x0 = max(0, (new_w - card_w) // 2)
    y0 = max(0, (new_h - card_h) // 2)
    crop = covered[y0:y0 + card_h, x0:x0 + card_w]
    if crop.shape[0] != card_h or crop.shape[1] != card_w:
        crop = cv2.resize(covered, (card_w, card_h), interpolation=cv2.INTER_AREA)
    darkened = np.clip(crop * (1.0 - float(darken)), 0, 255)
    if vignette:
        darkened = _radial_vignette(darkened, vignette)
    grain = _background_grain(frames[0], masks[0])
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, grain * 0.45, darkened.shape).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), 0.55)
    return np.clip(darkened + noise, 0, 255).astype(np.uint8)


def _build_blur_plate(source, matte, card_w, card_h):
    """Sample the take, drop the speaker, and blur a cover of that clean frame."""
    facts = _video_facts(source)
    video_w, video_h = int(facts["width"]), int(facts["height"])
    duration = min(float(facts["duration"]), float(_video_facts(matte)["duration"]))
    times = np.linspace(0.4, max(0.5, duration - 0.4), 8)
    frames, masks = [], []
    for when in times:
        frames.append(_frame_rgb(source, when, video_w, video_h))
        masks.append(_frame_mask(matte, when, video_w, video_h))
    return blur_cover_plate(frames, masks, card_w, card_h)


def fill_speaker(frame, mask, clean):
    """Replace the speaker with the clean plate so a live blur has no ghost."""
    frame = np.asarray(frame)
    clean = np.asarray(clean)
    person = np.asarray(mask) >= 48
    out = np.array(frame, dtype=np.uint8, copy=True)
    if person.shape[:2] != out.shape[:2]:
        raise ValueError("speaker fill mask must match the frame")
    out[person] = clean[person]
    return out


def _cover_crop(image, card_w, card_h):
    """Scale so the frame covers the card, then crop the center. No stretch."""
    import cv2

    image = np.asarray(image)
    height, width = image.shape[:2]
    card_w, card_h = int(card_w), int(card_h)
    cover = max(card_w / float(width), card_h / float(height))
    new_w = max(card_w, int(round(width * cover)))
    new_h = max(card_h, int(round(height * cover)))
    interp = cv2.INTER_AREA if cover < 1.0 else cv2.INTER_LINEAR
    covered = cv2.resize(image, (new_w, new_h), interpolation=interp)
    x0 = max(0, (new_w - card_w) // 2)
    y0 = max(0, (new_h - card_h) // 2)
    crop = covered[y0:y0 + card_h, x0:x0 + card_w]
    if crop.shape[0] != card_h or crop.shape[1] != card_w:
        crop = cv2.resize(covered, (card_w, card_h), interpolation=cv2.INTER_AREA)
    return crop


def _plate_holdout(mask, rgb, dilate_px):
    """Pixels that belong to the speaker, grown so a blur cannot pull him back in.

    A small olive or green patch within a couple of percent of the frame height
    of the silhouette is a shoulder leaf. It is held out so the plate does not
    bake it in. A large foliage region, including the background, still moves.
    """
    import cv2

    person = np.asarray(mask) >= 48
    if rgb is not None and np.asarray(rgb).shape[:2] == person.shape:
        color = np.asarray(rgb)
        person = person | _skin_mask(color)
        if np.any(person):
            leaves = (_olive_leak(color) | _foliage_green(color)) & ~person
            if np.any(leaves):
                labels, count = ndimage.label(leaves)
                counts = np.bincount(labels.ravel())
                near_px = max(8, int(round(max(person.shape) * 0.025)))
                near = ndimage.distance_transform_edt(~person) <= near_px
                limit = 0.004 * float(person.size)
                drop = np.zeros(count + 1, dtype=bool)
                for label in range(1, count + 1):
                    area = int(counts[label])
                    if area <= 0 or area > limit:
                        continue
                    if np.any((labels == label) & near):
                        drop[label] = True
                if drop.any():
                    person = person | drop[labels]
    radius = int(max(0, dilate_px))
    if radius <= 0 or not np.any(person):
        return person
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    return cv2.dilate(person.astype(np.uint8), kernel) > 0


def _match_hole_luma(clean, known, radius=28):
    """Lift the dark inpainted ring up toward the leaves beside the silhouette.

    The hole is the speaker. Telea fills it darker than the foliage it sits
    in, and that ring survives the plate blur as a halo. Only pixels that are
    darker than the nearby background move, and only part of the way.
    """
    clean = np.asarray(clean, dtype=np.float32)
    known = np.asarray(known, dtype=bool)
    hole = ~known
    if not np.any(hole) or not np.any(known):
        return clean
    dist = ndimage.distance_transform_edt(hole)
    ring = hole & (dist > 0) & (dist <= float(radius))
    if not np.any(ring):
        return clean
    luma = clean.mean(axis=2)
    known_l = np.where(known, luma, 0).astype(np.float32)
    weight = ndimage.gaussian_filter(known.astype(np.float32), 14)
    blurred = ndimage.gaussian_filter(known_l, 14)
    local = blurred / np.maximum(weight, 1e-3)
    current = luma
    gap = local - current
    lift = np.where(ring & (gap > 4.0), gap * np.clip((float(radius) - dist) / float(radius), 0, 1) * 0.7, 0)
    out = clean + lift[..., None]
    return np.clip(out, 0, 255)


def _inpaint_holes(clean, known):
    """Fill unknown pixels from the surrounding background. ``known`` is boolean."""
    import cv2

    clean = np.asarray(clean, dtype=np.float32)
    height, width = clean.shape[:2]
    hole = np.where(known, np.uint8(0), np.uint8(255))
    if not hole.any():
        return np.clip(clean, 0, 255)
    tiny_w = max(48, width // 2)
    tiny_h = max(48, height // 2)
    tiny = cv2.resize(np.clip(clean, 0, 255).astype(np.uint8), (tiny_w, tiny_h), interpolation=cv2.INTER_AREA)
    hole_tiny = cv2.resize(hole, (tiny_w, tiny_h), interpolation=cv2.INTER_NEAREST)
    painted = cv2.inpaint(tiny, hole_tiny, 4, cv2.INPAINT_TELEA)
    filled = cv2.resize(painted, (width, height), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    return np.where(known[..., None], clean, filled)


def _clean_fill(picture, mask):
    """Median of background-only pixels, with the speaker hole painted from the leaves."""
    facts = _video_facts(picture)
    width, height = int(facts["width"]), int(facts["height"])
    duration = min(float(facts["duration"]), float(_video_facts(mask)["duration"]))
    times = np.linspace(0.35, max(0.45, duration - 0.35), 12)
    frames, masks = [], []
    for when in times:
        frames.append(_frame_rgb(picture, when, width, height))
        masks.append(_frame_mask(mask, when, width, height))
    stack = np.stack([frame.astype(np.float32) for frame in frames], axis=0)
    dilate = max(8, min(PLATE_DILATE_PX, width // 12))
    hold = np.stack([
        _plate_holdout(item, frame, dilate) for item, frame in zip(masks, frames)
    ], axis=0)
    bg = ~hold
    known_count = bg.sum(axis=0)
    stack = np.where(bg[..., None], stack, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        clean = np.nanmedian(stack, axis=0)
    known = known_count > 0
    clean = np.nan_to_num(clean, nan=0.0)
    clean = _inpaint_holes(clean, known)
    clean = _match_hole_luma(clean, known)
    return np.clip(clean, 0, 255).astype(np.uint8)


def compose_live_fill(frame, mask, clean, card_w, card_h, sigma=PLATE_SIGMA, darken=PLATE_DARKEN,
                      vignette=PLATE_VIGNETTE, motion=PLATE_MOTION, dilate_px=None):
    """Blur the clean plate and add motion from the background only.

    The speaker is gone before the blur. Live pixels inside the dilated matte,
    including skin the mask missed, are zeroed before and after the motion blur
    so they cannot smear into the card.
    """
    import cv2

    frame = np.asarray(frame)
    clean = np.asarray(clean)
    height, width = frame.shape[:2]
    if dilate_px is None:
        dilate_px = max(4, min(PLATE_DILATE_PX, width // 12))
    # The plate blur is heavy. Half resolution matches it on a full-frame take.
    step = 2 if max(height, width) > 480 else 1
    work_w = max(32, width // step)
    work_h = max(32, height // step)
    cover = max(int(card_w) / float(width), int(card_h) / float(height))
    src_sigma = max(1.0, float(sigma) / max(cover, 1e-3))
    work_sigma = max(0.8, src_sigma / float(step))
    motion_sigma = max(0.6, min(work_sigma * 0.22, 6.0))
    work_dilate = max(1, int(round(float(dilate_px) / float(step))))
    small_clean = cv2.resize(clean, (work_w, work_h), interpolation=cv2.INTER_AREA)
    small_frame = cv2.resize(frame, (work_w, work_h), interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(np.asarray(mask), (work_w, work_h), interpolation=cv2.INTER_AREA)
    hold = _plate_holdout(small_mask, small_frame, work_dilate)
    blurred = cv2.GaussianBlur(small_clean, (0, 0), work_sigma)
    residual = small_frame.astype(np.float32) - small_clean.astype(np.float32)
    residual[hold] = 0
    moved = cv2.GaussianBlur(residual, (0, 0), motion_sigma)
    moved[hold] = 0
    mixed = blurred.astype(np.float32) + float(motion) * moved
    full = cv2.resize(np.clip(mixed, 0, 255), (width, height), interpolation=cv2.INTER_LINEAR)
    crop = _cover_crop(full, card_w, card_h)
    darkened = np.clip(crop.astype(np.float32) * (1.0 - float(darken)), 0, 255)
    if vignette:
        darkened = _radial_vignette(darkened, vignette)
    return np.clip(darkened, 0, 255).astype(np.uint8)


def ensure_live_plate(picture, mask, card_w, card_h, dest, sigma=PLATE_SIGMA, darken=PLATE_DARKEN,
                      vignette=PLATE_VIGNETTE):
    """A blurred cover of the clean background, with a little live foliage motion.

    Brandon is removed before the blur. Motion is the live frame minus that
    plate, and only where the dilated matte says the pixel is background.
    """
    dest = Path(dest)
    recipe = dest.with_suffix(".recipe")
    token = (
        f"{PLATE_RECIPE}|sigma={float(sigma):.1f}|darken={float(darken):.2f}"
        f"|vignette={float(vignette):.2f}|motion={float(PLATE_MOTION):.2f}|{int(card_w)}x{int(card_h)}")
    if dest.is_file() and dest.stat().st_size > 0 and recipe.is_file() and recipe.read_text().strip() == token:
        return dest
    print("building the clean background plate", flush=True)
    facts = _video_facts(picture)
    width, height = int(facts["width"]), int(facts["height"])
    fps = float(facts["fps"])
    clean = _clean_fill(picture, mask)
    rgb_proc, rgb_size = _raw_reader(picture, width, height, "rgb24")
    mask_proc, mask_size = _raw_reader(mask, width, height, "gray")
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.stem + ".partial.mp4")
    writer = _raw_writer(
        partial, int(card_w), int(card_h), fps, "rgb24",
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"])
    frames = 0
    try:
        while True:
            rgb_bytes = _read_exact(rgb_proc, rgb_size)
            mask_bytes = _read_exact(mask_proc, mask_size)
            if len(rgb_bytes) < rgb_size or len(mask_bytes) < mask_size:
                break
            rgb = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(height, width, 3)
            matte = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(height, width)
            plate = compose_live_fill(
                rgb, matte, clean, card_w, card_h, sigma=sigma, darken=darken, vignette=vignette)
            writer.stdin.write(np.ascontiguousarray(plate).tobytes())
            frames += 1
            if frames % 100 == 0:
                print(f"plate {frames} frames", flush=True)
        writer.stdin.close()
        writer.stdin = None
        code = writer.wait(timeout=900)
        if code or frames < 2:
            raise RuntimeError(f"live plate failed ({code}, {frames} frames)")
    finally:
        for proc in (rgb_proc, mask_proc):
            if proc.stdout:
                proc.stdout.close()
            proc.wait()
        if writer.stdin:
            writer.stdin.close()
        if writer.poll() is None:
            writer.wait(timeout=30)
    partial.replace(dest)
    recipe.write_text(token + "\n")
    return dest


def ensure_background_plate(source, matte, head, card_w, card_h, scale, pop_px, dest):
    """One static blurred plate per source. A re-render reuses it."""
    import cv2

    del head, scale, pop_px
    dest = Path(dest)
    recipe = dest.with_suffix(".recipe")
    token = (
        f"{PLATE_RECIPE}|sigma={PLATE_SIGMA:.1f}|darken={PLATE_DARKEN:.2f}"
        f"|vignette={PLATE_VIGNETTE:.2f}|{int(card_w)}x{int(card_h)}")
    if dest.is_file() and recipe.is_file() and recipe.read_text().strip() == token:
        return dest
    print("building the blurred background plate", flush=True)
    plate = _build_blur_plate(source, matte, card_w, card_h)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(dest), cv2.cvtColor(plate, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 97])
    if not ok:
        raise RuntimeError(f"could not write the background plate to {dest}")
    recipe.write_text(token + "\n")
    return dest


def apply_boundary_feather(alpha_path, dest, scale, shoulder_y, head_top, head_height,
                           ramp_card=BOUNDARY_RAMP_CARD_PX, hand_card=HAND_RAMP_CARD_PX):
    """Bake a short ramp into alpha where the body meets the frame edge.

    Every contact, including a raised hand, fades across ``hand_card`` pixels.
    A wide run above ``shoulder_y`` is the head and stays opaque. The bottom of
    the torso is not faded. The source matte stays cached. The distances are
    card pixels; the source ramp is that divided by scale.
    """
    dest = Path(dest)
    recipe = dest.with_suffix(".recipe")
    token = (
        f"{BOUNDARY_RAMP_RECIPE}|{EDGE_RECIPE}|card={float(ramp_card):.1f}|hand={float(hand_card):.1f}"
        f"|scale={float(scale):.4f}|shoulder={float(shoulder_y):.2f}")
    if dest.is_file() and dest.stat().st_size > 0 and recipe.is_file() and recipe.read_text().strip() == token:
        return dest
    facts = _video_facts(alpha_path)
    width, height = int(facts["width"]), int(facts["height"])
    fps = float(facts["fps"])
    ramp_src = float(hand_card) / max(float(scale), 1e-3)
    hand_src = float(hand_card) / max(float(scale), 1e-3)
    print(
        f"feathering frame edges over {float(hand_card):.0f}px",
        flush=True)
    frame_bytes = width * height * 4
    reader = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(alpha_path),
         "-f", "rawvideo", "-pix_fmt", "bgra", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    partial = dest.with_name(dest.stem + ".partial.mov")
    writer = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
         "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "-i", "pipe:0",
         "-c:v", "qtrle", "-pix_fmt", "argb", "-an", str(partial)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    frames = 0
    try:
        while True:
            blob = _read_exact(reader, frame_bytes)
            if not blob:
                break
            plane = np.frombuffer(blob, dtype=np.uint8).reshape(height, width, 4).copy()
            raw_alpha = plane[:, :, 3].copy()
            # The plane is BGRA. Skin is judged in RGB.
            color = plane[:, :, 2::-1]
            plane[:, :, 3] = feather_boundary_alpha(
                raw_alpha, ramp_src, shoulder_y, hand_ramp_px=hand_src, rgb=color)
            head_box_holds(raw_alpha, plane[:, :, 3], head_top, head_height)
            writer.stdin.write(plane.tobytes())
            frames += 1
        writer.stdin.close()
        writer.stdin = None
        write_code = writer.wait(timeout=900)
        read_code = reader.wait(timeout=120)
        if write_code or read_code or frames < 1:
            err = b""
            if writer.stderr:
                err += writer.stderr.read() or b""
            if reader.stderr:
                err += reader.stderr.read() or b""
            raise RuntimeError(
                f"boundary feather failed ({read_code}/{write_code}, {frames} frames): {err[-500:]!r}")
    finally:
        if writer.stdin:
            writer.stdin.close()
        if writer.poll() is None:
            writer.kill()
        if reader.poll() is None:
            reader.kill()
        if reader.stdout:
            reader.stdout.close()
    partial.replace(dest)
    recipe.write_text(token + "\n")
    return dest


def attach_popout(timeline, raw_source, ranges, picture, theme):
    """Build the cached matte, cut it onto the tightened clock, and frame the card."""
    if not any(shot.get("layout") == "split" for shot in timeline.get("shots") or []):
        return timeline
    print("segmenting the speaker (cached after the first run)", flush=True)
    full = ensure_source_matte(raw_source)
    picture = Path(picture)
    coarse = picture.with_name("person-mask-coarse.mp4")
    mask = picture.with_name("person-mask.mp4")
    alpha = picture.with_name("person-pop.mov")
    recipe = alpha.with_suffix(".recipe")
    cut_matte(full, ranges, coarse)
    picture_facts = _video_facts(picture)
    coarse_facts = _video_facts(coarse)
    if abs(picture_facts["duration"] - coarse_facts["duration"]) > 0.08:
        # The trim grid did not land on the same frames. Segment the picture itself.
        _segment_gray(picture, coarse)
        coarse_facts = _video_facts(coarse)
    alpha_duration = _video_facts(alpha)["duration"] if alpha.is_file() else 0
    recipe_ok = recipe.is_file() and recipe.read_text().strip() == EDGE_RECIPE
    if (not alpha.is_file() or not mask.is_file() or not recipe_ok
            or abs(alpha_duration - coarse_facts["duration"]) > 0.08):
        print("refining the pop-out edge", flush=True)
        alpha = refine_and_pack(
            picture, coarse, mask, alpha,
            cuts=tightened_cut_frames(ranges, picture_facts["fps"]))
        recipe.write_text(EDGE_RECIPE + "\n")
    head = measure_head(mask)
    timeline["source"]["matte"] = str(alpha.resolve())
    timeline["source"]["matte_mask"] = str(mask.resolve())
    frame_popout(timeline, head, theme)
    popped = timeline["source"]["popout"]
    plate = picture.with_name("speaker-plate.mp4")
    ensure_live_plate(
        picture, mask, popped["card_width"], popped["card_height"], plate)
    popped["plate"] = str(plate.resolve())
    try:
        tint = _frame_rgb(plate, 0.4, int(popped["card_width"]), int(popped["card_height"]))
        mean = tint.mean(axis=(0, 1))
        popped["plate_tint"] = [int(round(float(mean[0]))), int(round(float(mean[1]))), int(round(float(mean[2])))]
    except (RuntimeError, OSError, subprocess.CalledProcessError):
        popped["plate_tint"] = [36, 44, 28]
    feathered = picture.with_name("person-pop-edge.mov")
    # The measured head ends at the chin. The frame ramp starts there, under the face.
    shoulder_y = float(popped["head_top"]) + float(popped["head_height"])
    apply_boundary_feather(
        alpha, feathered, popped["scale"], shoulder_y,
        popped["head_top"], popped["head_height"])
    timeline["source"]["matte"] = str(feathered.resolve())
    print(
        f"pop-out face {popped['face_px']}px  crown {popped['median_above_px']}px"
        f"  scale {popped['scale']}  captions at {popped['caption_y']}%",
        flush=True)
    return timeline
