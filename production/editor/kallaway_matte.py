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
PLATE_RECIPE = "blur-cover-v1"
# Card pixels. Divided by the placed scale when the ramp is baked into the source matte.
BOUNDARY_RAMP_CARD_PX = 64.0
BOUNDARY_RAMP_RECIPE = "boundary-ramp-v1"
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
EDGE_RECIPE = "rvm-r50-d050-flow-smooth-feather2.5-despill6-speck200"


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


def refine_frame(rgb, coarse, previous=None):
    """Feather a full-resolution matte and composite a contact shadow.

    The incoming alpha is already at the picture size. Optical flow steadies
    the edge, a 1-2px ramp antialiases it, and green foliage is pulled off
    that ramp. Returns person alpha, straight RGB, straight alpha (person over
    the shadow), and the state to carry into the next frame.
    """
    rgb = np.asarray(rgb)
    alpha = np.asarray(coarse, dtype=np.float32)
    if alpha.shape != rgb.shape[:2]:
        import cv2
        alpha = cv2.resize(alpha, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip(alpha, 0, 1).astype(np.float32)
    gray = np.clip(rgb.astype(np.float32).mean(axis=2), 0, 255).astype(np.uint8)
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


def refine_and_pack(picture, coarse, mask_out, alpha_out):
    """Guided upsample, feather, and contact shadow on the picture's frames."""
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
    previous = None
    written = 0
    try:
        while True:
            rgb_bytes = _read_exact(rgb_proc, rgb_size)
            mask_bytes = _read_exact(mask_proc, mask_size)
            if len(rgb_bytes) < rgb_size or len(mask_bytes) < mask_size:
                break
            rgb = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(height, width, 3)
            coarse_frame = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(height, width)
            person, straight, out_a, previous = refine_frame(
                rgb, coarse_frame.astype(np.float32) * (1 / 255), previous)
            gray = np.clip(person * 255.0, 0, 255).astype(np.uint8)
            argb = np.empty((height, width, 4), dtype=np.uint8)
            argb[:, :, 0] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)
            argb[:, :, 1:] = straight
            gray_proc.stdin.write(np.ascontiguousarray(gray).tobytes())
            alpha_proc.stdin.write(np.ascontiguousarray(argb).tobytes())
            written += 1
            if written % 100 == 0:
                print(f"refined {written} frames", flush=True)
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
        full_font = float(layout.get("caption_full_px", 67)) * (width / 1080.0)
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


def feather_boundary_alpha(alpha, ramp_px, touch_px=3):
    """Ease alpha to 0 where the matte is cut by the source frame.

    A row fades only when opaque pixels meet the left or right edge, and a
    column fades only when they meet the bottom. The crown and any organic
    edge inside the frame keep the matte's own feather. ``ramp_px`` is in
    the same pixels as ``alpha``.
    """
    alpha = np.asarray(alpha)
    if alpha.ndim != 2:
        raise ValueError("boundary feather expects one alpha plane")
    height, width = alpha.shape
    ramp = max(1.0, float(ramp_px))
    edge = max(1, int(touch_px))
    opaque = alpha > 16
    touch_left = opaque[:, :edge].any(axis=1)
    touch_right = opaque[:, -edge:].any(axis=1)
    touch_bottom = opaque[-edge:, :].any(axis=0)
    if not (touch_left.any() or touch_right.any() or touch_bottom.any()):
        return np.ascontiguousarray(alpha)
    gain = np.ones((height, width), dtype=np.float32)
    xs = np.arange(width, dtype=np.float32)
    ys = np.arange(height, dtype=np.float32)
    if touch_left.any():
        gain[touch_left] *= _smoothstep(xs / ramp)
    if touch_right.any():
        gain[touch_right] *= _smoothstep((width - 1 - xs) / ramp)
    if touch_bottom.any():
        gain[:, touch_bottom] *= _smoothstep((height - 1 - ys) / ramp)[:, None]
    faded = np.clip(alpha.astype(np.float32) * gain, 0, 255)
    return np.ascontiguousarray(faded.astype(np.uint8))


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
    bg = np.stack([mask < 48 for mask in masks], axis=0)
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


def apply_boundary_feather(alpha_path, dest, scale, ramp_card=BOUNDARY_RAMP_CARD_PX):
    """Bake an eased ramp into alpha that meets the left, right, or bottom edge.

    The source matte stays cached. This file is the one the card composites,
    so a change of ramp does not re-run Robust Video Matting. ``ramp_card``
    is pixels on the placed card; the source ramp is that divided by scale.
    """
    dest = Path(dest)
    recipe = dest.with_suffix(".recipe")
    token = f"{BOUNDARY_RAMP_RECIPE}|card={float(ramp_card):.1f}|scale={float(scale):.4f}"
    if dest.is_file() and dest.stat().st_size > 0 and recipe.is_file() and recipe.read_text().strip() == token:
        return dest
    facts = _video_facts(alpha_path)
    width, height = int(facts["width"]), int(facts["height"])
    fps = float(facts["fps"])
    ramp_src = float(ramp_card) / max(float(scale), 1e-3)
    print(f"feathering frame-cut edges over {float(ramp_card):.0f}px at card scale", flush=True)
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
            plane[:, :, 3] = feather_boundary_alpha(plane[:, :, 3], ramp_src)
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
        alpha = refine_and_pack(picture, coarse, mask, alpha)
        recipe.write_text(EDGE_RECIPE + "\n")
    head = measure_head(mask)
    timeline["source"]["matte"] = str(alpha.resolve())
    timeline["source"]["matte_mask"] = str(mask.resolve())
    frame_popout(timeline, head, theme)
    popped = timeline["source"]["popout"]
    plate = picture.with_name("speaker-plate.jpg")
    ensure_background_plate(
        raw_source, full, head,
        popped["card_width"], popped["card_height"],
        popped["scale"], popped["pop_px"], plate)
    popped["plate"] = str(plate.resolve())
    import cv2
    bgr = cv2.imread(str(plate), cv2.IMREAD_COLOR)
    if bgr is not None:
        mean = bgr.mean(axis=(0, 1))
        popped["plate_tint"] = [int(round(float(mean[2]))), int(round(float(mean[1]))), int(round(float(mean[0])))]
    feathered = picture.with_name("person-pop-edge.mov")
    apply_boundary_feather(alpha, feathered, popped["scale"])
    timeline["source"]["matte"] = str(feathered.resolve())
    print(
        f"pop-out face {popped['face_px']}px  crown {popped['median_above_px']}px"
        f"  scale {popped['scale']}  captions at {popped['caption_y']}%",
        flush=True)
    return timeline
