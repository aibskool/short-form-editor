"""Person matte for the Kallaway split-screen head pop-out.

The speaker card keeps the normal footage. Above the card's top edge, only the
person is drawn, so the head and hands sit on the graphics. The matte is built
once per source video and reused.

MediaPipe Selfie Segmentation runs on the CPU at a reduced size. A short
temporal median plus a one-pixel close kills flicker and pinholes. The stored
mask is a full-size gray video; the composition packs it into a VP9 alpha WebM
on the same frames as the picture.
"""
import hashlib
import os
import subprocess
from pathlib import Path

import numpy as np
from scipy import ndimage

MODEL = "mediapipe-selfie-0.10.14-general"
CACHE = Path.home() / ".cache" / "kallaway-mattes"
# Median head sits this far above the card, as a fraction of head height.
POP_FRACTION = 0.15
POP_FLOOR = 0.10
POP_CAP = 0.20
HOLE_AREA_FRACTION = 0.004
SEAM_PX = 2


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


def choose_anchor(head_tops, head_height):
    """Aim the median head at 15% above the card, and keep lower heads at least 10% out.

    A single crop cannot track a lean. The median is the look; the lower head
    only pulls the crop further when that still leaves the typical head under
    about 20% out.
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
    probe = min(height - 1, top + max(3, int(height * 0.025)))
    head_width = float(np.median(widths[top:probe + 1])) if probe > top else float(widths[top])
    head_width = max(head_width, 4.0)
    shoulder = None
    limit = min(height - 1, top + int(height * 0.38))
    for y in range(probe, limit + 1):
        if widths[y] > head_width * 1.45 and widths[y] > head_width + width * 0.05:
            shoulder = y
            break
    if shoulder is None:
        head_height = head_width * 1.3
    else:
        head_height = max(head_width * 0.8, shoulder - top)
    # A raised hand sits off the crown column but up in the head band.
    hand = None
    side = fg.copy()
    side[:, x0:x1] = False
    if side.any():
        side_top = int(np.where(side.any(axis=1))[0][0])
        if side_top < top + head_height * 0.75:
            hand = side_top
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
    tops, heights, hands = [], [], []
    for index, mask in enumerate(masks):
        found = _head_from_mask(mask)
        if not found:
            continue
        tops.append(found["top"] * scale_y)
        heights.append(found["height"] * scale_y)
        when = float(times[index]) if index < len(times) else index * step
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


def _segment_gray(source, output):
    facts = _video_facts(source)
    sample_w, sample_h = _analysis_size(facts["width"], facts["height"], 288)
    os.environ.setdefault("GLOG_minloglevel", "2")
    import mediapipe as mp
    segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0)
    decoder = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(source),
         "-vf", f"scale={sample_w}:{sample_h}:flags=bilinear",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_bytes = sample_w * sample_h * 3
    history = []
    previous = None
    raw_path = output.with_suffix(".raw")
    written = 0

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
        with raw_path.open("wb") as raw:
            while True:
                blob = _exact(frame_bytes)
                if len(blob) < frame_bytes:
                    break
                rgb = np.frombuffer(blob, dtype=np.uint8).reshape(sample_h, sample_w, 3)
                mask = np.asarray(segmenter.process(rgb).segmentation_mask, dtype=np.float32)
                history.append(mask)
                if len(history) > 3:
                    history.pop(0)
                median = np.median(np.stack(history, axis=0), axis=0)
                blended = median if previous is None else 0.7 * median + 0.3 * previous
                previous = blended
                closed = ndimage.binary_closing(blended >= 0.55, iterations=1)
                raw.write(np.where(closed, 255, 0).astype(np.uint8).tobytes())
                written += 1
                if written % 200 == 0:
                    print(f"segmented {written} frames", flush=True)
    finally:
        segmenter.close()
        if decoder.stdout:
            decoder.stdout.close()
        decoder.wait()
    if written < 2:
        raise RuntimeError(f"segmentation produced no frames for {source}")
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{sample_w}x{sample_h}",
        "-r", f"{facts['fps']:.6f}", "-i", str(raw_path),
        "-vf", f"scale={facts['width']}:{facts['height']}:flags=bilinear,gblur=sigma=0.8",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
        "-an", str(output),
    ])
    raw_path.unlink(missing_ok=True)
    return output


def ensure_source_matte(source, cache_dir=None):
    """Gray matte aligned to the raw source. Reused across renders."""
    source = Path(source)
    root = Path(cache_dir) if cache_dir else CACHE
    folder = root / source_digest(source)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "matte.mp4"
    if target.is_file() and target.stat().st_size > 0:
        return target
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
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
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


def _shot_scale(shot, layout):
    if shot.get("scale"):
        return float(shot["scale"])
    if shot.get("layout") == "punch_in":
        return float(layout.get("punch_scale", 1.27))
    if shot.get("layout") == "full":
        return float(layout.get("full_scale", 1.13))
    if shot.get("crop") == "tight":
        return float(layout.get("tight_scale", 1.08))
    return float(layout.get("wide_scale", 1))


def frame_popout(timeline, head, theme):
    """Point split shots so the crown clears the card, and lift captions off the head."""
    layout = theme["layout"]
    width = int(timeline.get("output", {}).get("width", 1080))
    height = int(timeline.get("output", {}).get("height", 1920))
    card_w = (1 - 2 * layout["card_margin_x"]) * width
    card_h = (layout["card_bottom"] - layout["card_top"]) * height
    card_top = layout["card_top"] * height
    video_w, video_h = head["width"], head["height"]
    groups = {}
    for shot in timeline.get("shots") or []:
        if shot.get("layout") != "split":
            continue
        scale = round(_shot_scale(shot, layout), 4)
        groups.setdefault(scale, []).append(shot)
    positions = {}
    for scale, shots in groups.items():
        pos_y = solve_position_y(
            head["head_top"], head["head_height"], head["pop_fraction"],
            video_w, video_h, card_w, card_h, scale=scale)
        positions[scale] = pos_y
        label = f"50% {pos_y * 100:.2f}%"
        for shot in shots:
            shot["object_position"] = label
    wide = positions.get(round(float(layout.get("wide_scale", 1)), 4), next(iter(positions.values()), 0.5))
    high_y = source_y_on_card(
        head["head_high"], video_w, video_h, card_w, card_h, wide, scale=1)
    font = layout["caption_font_px"] * (width / 1080)
    text_h = font * 1.02
    # The higher head (smaller source y) is the one captions have to clear.
    head_canvas = card_top + high_y
    # Sit the caption line above the higher head. It may overlap the lower
    # graphic panel; it must not sit on the crown. The title band stays clear.
    caption_top = head_canvas - 18 - text_h
    floor = (layout["stage_top"] + 0.12) * height
    caption_top = max(floor, caption_top)
    caption_pct = round(caption_top / height * 100, 2)
    for shot in timeline.get("shots") or []:
        if shot.get("layout") == "split":
            shot["caption_y"] = caption_pct
    low_y = source_y_on_card(
        head["head_low"], video_w, video_h, card_w, card_h, wide, scale=1)
    median_y = source_y_on_card(
        head["head_top"], video_w, video_h, card_w, card_h, wide, scale=1)
    head_px = head["head_height"] * cover_fit(video_w, video_h, card_w, card_h)
    timeline["source"]["popout"] = {
        "object_position": f"50% {wide * 100:.2f}%",
        "caption_y": caption_pct,
        "head_top": head["head_top"],
        "head_height": head["head_height"],
        "pop_fraction": head["pop_fraction"],
        "median_above_px": round(-median_y, 1),
        "low_above_px": round(-low_y, 1),
        "high_above_px": round(-high_y, 1),
        "head_px": round(head_px, 1),
        "samples": head["samples"],
        "hands": head.get("hands") or [],
    }
    return timeline


def attach_popout(timeline, raw_source, ranges, picture, theme):
    """Build the cached matte, cut it onto the tightened clock, and frame the card."""
    if not any(shot.get("layout") == "split" for shot in timeline.get("shots") or []):
        return timeline
    print("segmenting the speaker (cached after the first run)", flush=True)
    full = ensure_source_matte(raw_source)
    picture = Path(picture)
    mask = picture.with_name("person-mask.mp4")
    alpha = picture.with_name("person-pop.mov")
    cut_matte(full, ranges, mask)
    picture_facts = _video_facts(picture)
    mask_facts = _video_facts(mask)
    if abs(picture_facts["duration"] - mask_facts["duration"]) > 0.08:
        # The trim grid did not land on the same frames. Segment the picture itself.
        _segment_gray(picture, mask)
    if not alpha.is_file() or alpha.stat().st_mtime < mask.stat().st_mtime:
        print("packing the pop-out alpha", flush=True)
        alpha = pack_alpha(picture, mask, alpha)
    head = measure_head(mask)
    timeline["source"]["matte"] = str(alpha.resolve())
    timeline["source"]["matte_mask"] = str(mask.resolve())
    frame_popout(timeline, head, theme)
    popped = timeline["source"]["popout"]
    print(
        f"pop-out {popped['object_position']}  median {popped['median_above_px']}px above the card"
        f"  low {popped['low_above_px']}px  captions at {popped['caption_y']}%",
        flush=True)
    return timeline
