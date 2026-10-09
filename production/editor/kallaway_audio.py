"""Voice tightening, podcast leveling, and recorded sound cues for Kallaway-style edits.

Sound effects live in ``sfx/kallaway`` and the lo-fi bed in ``music/kallaway-bed.ogg``.
Both are CC0 recordings. Sources and licenses are in THIRD_PARTY_NOTICES.md.
This module trims pauses to a short target gap, crossfades each join, and copies
the library into a composition. It does not synthesize the cues.
"""
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import numpy as np

RATE = 48000
HERE = Path(__file__).resolve().parent
SFX_LIBRARY = HERE / "sfx" / "kallaway"
BED_FILE = HERE / "music" / "kallaway-bed.ogg"
BED_NATIVE_BPM = 105.5
SFX_KINDS = (
    "pop", "whoosh", "click", "typing", "ticking", "ding", "bass", "riser", "error", "marker", "paper",
)


def _clamp(value):
    return max(-1.0, min(1.0, value))


def write_wav(path, samples, rate=RATE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        frames = bytearray()
        for sample in samples:
            frames += struct.pack("<h", int(_clamp(sample) * 32767))
        handle.writeframes(frames)
    return path


def sfx_variants(kind, directory=None):
    """Recorded takes for one cue, in stable order."""
    if kind not in SFX_KINDS:
        raise ValueError(f"unknown sfx kind: {kind}")
    root = Path(directory) if directory else SFX_LIBRARY
    found = sorted(root.glob(f"{kind}-*.wav"))
    single = root / f"{kind}.wav"
    if not found and single.is_file():
        return [single]
    return found


def write_sfx_library(directory):
    """Copy the committed CC0 library into a composition. Variants stay kind-N.wav."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not SFX_LIBRARY.is_dir():
        raise FileNotFoundError(f"kallaway sfx library missing: {SFX_LIBRARY}")
    written = {}
    for kind in SFX_KINDS:
        variants = sfx_variants(kind)
        if len(variants) < 2:
            raise FileNotFoundError(f"kallaway sfx kind {kind} needs at least two recorded variants")
        copied = []
        for source in variants:
            dest = directory / source.name
            shutil.copyfile(source, dest)
            copied.append(dest)
        shutil.copyfile(copied[0], directory / f"{kind}.wav")
        written[kind] = copied
    note = SFX_LIBRARY / "SOURCES.md"
    if note.is_file():
        shutil.copyfile(note, directory / "SOURCES.md")
    return written


def write_bed(path, duration, bpm=None):
    """Loop the committed CC0 lo-fi bed and level it near -14 LUFS.

    The recording is about 105 BPM with no vocals. ``bpm`` time-stretches it
    when a reel asks for another tempo. A later linear gain of 10^(-25/20)
    then sits about 25 dB under a -14 LUFS voice.
    """
    duration = max(4.0, float(duration))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not BED_FILE.is_file():
        raise FileNotFoundError(f"kallaway bed missing: {BED_FILE}")
    ratio = 1.0
    if bpm:
        ratio = max(0.88, min(1.12, float(bpm) / BED_NATIVE_BPM))
    tempo = f"atempo={ratio:.5f}," if abs(ratio - 1.0) > 0.008 else ""
    staged = path.with_suffix(".pre.wav")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-stream_loop", "-1", "-i", str(BED_FILE), "-t", f"{duration:.3f}",
         "-af", f"{tempo}aformat=channel_layouts=mono,aresample={RATE}",
         "-c:a", "pcm_s16le", str(staged)],
        check=True)
    measured = _loudnorm_measure(staged, -14, -2.0, "anull")
    effect = (f"loudnorm=I=-14:TP=-2:LRA=11:"
              f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
              f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
              f"offset={measured['target_offset']}:linear=true")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(staged),
         "-af", effect, "-c:a", "pcm_s16le", "-ar", str(RATE), str(path)],
        check=True)
    staged.unlink(missing_ok=True)
    path.with_name("BED-LICENSE.txt").write_text(
        "Lo-fi bed: Chill lofi inspired, loop edit, CC0 1.0.\n"
        "https://opengameart.org/content/chill-lofi-inspired-loop-edit\n"
        "Original by isaiah658. Loop edit by qubodup. No vocals. Native tempo about 105 BPM.\n"
        "See THIRD_PARTY_NOTICES.md.\n"
    )
    return path


def _frame_rms(samples, rate, win_s=0.01, hop_s=0.004):
    win = max(1, int(rate * win_s))
    hop = max(1, int(rate * hop_s))
    if len(samples) < win:
        return np.array([]), np.array([])
    count = 1 + (len(samples) - win) // hop
    frames = np.empty(count)
    for index in range(count):
        start = index * hop
        chunk = samples[start:start + win]
        frames[index] = math.sqrt(float(np.dot(chunk, chunk)) / win)
    times = (np.arange(count) * hop + win / 2) / rate
    return times, frames


# Stop closures inside a word are often 80–120 ms. Bridge those so the louder
# half of the word cannot discard the earlier half. A breath or the previous
# word's tail sits farther away and stays in its own cluster.
_WORD_BRIDGE_SECONDS = 0.14


def refine_word_bounds(samples, rate, words, pad_in=0.008, pad_out=0.012):
    """Snap each word to its speech energy so breaths and dead air fall outside.

    Hot frames that overlap the whisper span are clustered when the gap between
    them is at most 140 ms, which keeps a stop closure inside the word. A burst
    separated by a longer gap (a breath, or the previous word's tail) is left
    out. A short pad stays on the real onset and offset so plosives are not clipped.
    """
    samples = np.asarray(samples, dtype=np.float64)
    ordered = sorted(words, key=lambda word: float(word["start"]))
    times, frames = _frame_rms(samples, rate)
    if len(frames) == 0:
        return [dict(word) for word in ordered]
    floor = float(np.percentile(frames, 20))
    refined = []
    for index, word in enumerate(ordered):
        start = float(word["start"])
        end = float(word["end"])
        prev_end = float(refined[-1]["end"]) if refined else 0.0
        next_start = float(ordered[index + 1]["start"]) if index + 1 < len(ordered) else float(times[-1])
        lo = max(prev_end, start - 0.08)
        hi = min(next_start if next_start > start else end + 0.08, end + 0.10)
        mask = (times >= lo) & (times <= max(hi, lo + 0.02))
        local_t = times[mask]
        local = frames[mask]
        chosen = dict(word)
        if len(local) == 0:
            refined.append(chosen)
            continue
        peak = float(local.max())
        # Stay under the vowel so a quiet consonant still counts as speech.
        thresh = max(floor * 3.5, peak * 0.05, 1e-6)
        hot = local >= thresh
        runs = []
        cursor = 0
        while cursor < len(hot):
            if not hot[cursor]:
                cursor += 1
                continue
            stop = cursor
            while stop < len(hot) and hot[stop]:
                stop += 1
            runs.append((cursor, stop))
            cursor = stop
        if not runs:
            refined.append(chosen)
            continue

        belonging = []
        for run in runs:
            run_start = float(local_t[run[0]])
            run_end = float(local_t[run[1] - 1])
            if min(run_end, end) - max(run_start, start) > 0.012:
                belonging.append((run_start, run_end))
        if not belonging:
            refined.append(chosen)
            continue
        belonging.sort()
        clusters = [[belonging[0][0], belonging[0][1]]]
        for run_start, run_end in belonging[1:]:
            if run_start - clusters[-1][1] <= _WORD_BRIDGE_SECONDS:
                clusters[-1][1] = max(clusters[-1][1], run_end)
            else:
                clusters.append([run_start, run_end])

        def cluster_overlap(cluster):
            return min(cluster[1], end) - max(cluster[0], start)

        onset, offset = max(clusters, key=cluster_overlap)
        onset = max(prev_end, onset - pad_in)
        offset = min(float(times[-1]), offset + pad_out)
        if index + 1 < len(ordered):
            offset = min(offset, max(onset + 0.04, float(ordered[index + 1]["start"]) - 0.004))
        if offset - onset < 0.04:
            refined.append(chosen)
            continue
        chosen["start"] = round(onset, 4)
        chosen["end"] = round(offset, 4)
        refined.append(chosen)
    return refined


def keep_ranges(words, source_duration, gap=0.06, handle=0.004):
    """Cut pauses longer than ``gap`` seconds down to about ``gap``.

    ``gap`` is the silence that remains between phrases, not a threshold that
    keeps every shorter pause untouched only. Pauses already shorter than
    ``gap`` stay. ``handle`` is a few milliseconds kept outside each word.
    """
    if gap <= 0 or handle < 0:
        raise ValueError("pause gap and handle must be non-negative")
    ordered = sorted(words, key=lambda word: float(word["start"]))
    if not ordered:
        raise ValueError("no words to tighten")
    source_duration = float(source_duration)
    ranges = []
    start = max(0.0, float(ordered[0]["start"]) - min(handle, gap / 2))
    for prev, word in zip(ordered, ordered[1:]):
        pause = float(word["start"]) - float(prev["end"])
        if pause > gap:
            tail = min(gap * 0.45, max(0.0, pause - 0.004))
            head = min(gap - tail, max(0.0, pause - tail))
            ranges.append((start, min(source_duration, float(prev["end"]) + tail)))
            start = max(0.0, float(word["start"]) - head)
    ranges.append((start, min(source_duration, float(ordered[-1]["end"]) + min(handle, gap / 2))))
    merged = []
    for begin, end in ranges:
        if end - begin <= 0.01:
            continue
        if merged and begin <= merged[-1][1] + 1e-4:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((begin, end))
    if not merged:
        raise ValueError("tightening removed the entire take")
    return merged


def _probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def _probe_rate(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True)
    num, _, den = result.stdout.strip().partition("/")
    if den:
        return float(num) / float(den)
    return float(num or 30)


def _load_mono(path, rate=RATE):
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"])
    return np.frombuffer(raw, dtype=np.float32).copy()


def tighten_video(source, words, output, gap=0.06, handle=0.004, crossfade=0.008):
    """Write a tight 1x cut of the talking-head take and remap word times.

    Speech edges are snapped with an energy check, pauses longer than ``gap``
    are cut down to about ``gap``, and each join gets an audio crossfade.
    Picture hard-cuts at the midpoint of that crossfade so the clocks match.
    """
    if not 0 <= crossfade <= 0.02:
        raise ValueError("cut crossfade must be between 0 and 20 ms")
    source, output = Path(source), Path(output)
    duration = _probe_duration(source)
    samples = _load_mono(source)
    refined = refine_word_bounds(samples, RATE, words)
    ranges = keep_ranges(refined, duration, gap=gap, handle=handle)
    video = []
    for index, (begin, end) in enumerate(ranges):
        left, right = begin, end
        long_enough = (end - begin) > max(0.03, crossfade * 3)
        if crossfade and index > 0 and long_enough:
            left += crossfade / 2
        if crossfade and index < len(ranges) - 1 and long_enough:
            right -= crossfade / 2
        if right - left < 0.02:
            left, right = begin, end
        video.append((left, right))
    filters = []
    expected = 0.0
    last = len(ranges) - 1
    for index, (begin, end) in enumerate(ranges):
        vb, ve = video[index]
        filters.append(f"[0:v]trim=start={vb:.6f}:end={ve:.6f},setpts=PTS-STARTPTS[v{index}]")
        length = end - begin
        fades = ""
        if index == 0:
            fades += ",afade=t=in:d=0.004"
        if index == last:
            fades += f",afade=t=out:st={max(0, length - 0.004):.6f}:d=0.004"
        filters.append(
            f"[0:a]atrim=start={begin:.6f}:end={end:.6f},asetpts=PTS-STARTPTS{fades}[a{index}]")
        expected += ve - vb
    if crossfade and len(ranges) > 1:
        filters.append(f"[a0][a1]acrossfade=d={crossfade:.4f}:c1=tri:c2=tri[ax1]")
        for index in range(2, len(ranges)):
            prev = f"ax{index - 1}"
            filters.append(f"[{prev}][a{index}]acrossfade=d={crossfade:.4f}:c1=tri:c2=tri[ax{index}]")
        audio_label = f"[ax{last}]"
    else:
        audio_label = "[a0]"
    vlabels = "".join(f"[v{i}]" for i in range(len(ranges)))
    filters.append(f"{vlabels}concat=n={len(ranges)}:v=1:a=0[vout]")
    output.parent.mkdir(parents=True, exist_ok=True)
    graph = output.with_suffix(".tighten.txt")
    graph.write_text(";\n".join(filters))
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
         "-filter_complex_script", str(graph), "-map", "[vout]", "-map", audio_label,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)],
        check=True)
    from edit import map_words
    segments = [{"start": begin, "end": end} for begin, end in video]
    mapped = map_words(refined, segments)
    return {"output": str(output), "words": mapped, "ranges": video,
            "expected_duration": expected, "duration": _probe_duration(output),
            "fps": _probe_rate(output)}


def _loudnorm_measure(path, target, peak, chain):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
         f"{chain},loudnorm=I={target}:TP={peak}:LRA=7:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    import json
    import re
    blocks = re.findall(r'\{\s*"input_i".*?\}', result.stderr, re.S)
    if not blocks:
        raise RuntimeError("voice loudnorm returned no measurement")
    return json.loads(blocks[-1])


def process_voice(source, output, target_lufs=-14, true_peak=-1.5, presence_hz=4000, presence_db=4):
    """Compress about 4:1, add a presence lift, and level the voice to the target."""
    source, output = Path(source), Path(output)
    chain = (f"highpass=f=80,equalizer=f={presence_hz}:t=q:w=1.3:g={presence_db},"
             "acompressor=threshold=-18dB:ratio=4:attack=8:release=110:makeup=3")
    measured = _loudnorm_measure(source, target_lufs, true_peak, chain)
    effect = (f"{chain},loudnorm=I={target_lufs}:TP={true_peak}:LRA=7:"
              f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
              f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
              f"offset={measured['target_offset']}:linear=true")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
         "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", effect,
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(output)],
        check=True)
    return {"output": str(output), "measurement": measured, "target_lufs": target_lufs}
