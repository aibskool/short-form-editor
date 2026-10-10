"""Voice tightening, podcast leveling, and recorded sound cues for Kallaway-style edits.

Sound effects come from a local Viral Reels SFX Pack (``SFX_PACK_DIR``). The
files are not committed. The lo-fi bed in ``music/kallaway-bed.ogg`` is CC0.
Sources and licenses are in THIRD_PARTY_NOTICES.md. This module keeps each
word through its decay, removes only the gap between phrases, crossfades each
join, and copies the pack cues into a composition. It does not synthesize,
EQ, pitch-shift, stretch, or filter the cues.
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
    """Recorded takes for one cue, in stable order.

    A composition directory that already has ``kind-N.wav`` wins. Otherwise
    the files come from the local Viral Reels pack.
    """
    if kind not in SFX_KINDS:
        raise ValueError(f"unknown sfx kind: {kind}")
    if directory:
        root = Path(directory)
        found = sorted(root.glob(f"{kind}-*.wav"))
        single = root / f"{kind}.wav"
        if not found and single.is_file():
            return [single]
        if found:
            return found
    from kallaway_pack import kind_paths
    return kind_paths(kind)


def write_sfx_library(directory):
    """Decode the local pack into a composition as kind-N.wav.

    Clip gain is applied when a file peaks above 0 dBFS. Nothing else is
    processed. The pack itself is not copied into git.
    """
    from kallaway_pack import kind_paths, load, pack_dir
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = {}
    for kind in SFX_KINDS:
        sources = kind_paths(kind)
        if len(sources) < 2:
            raise FileNotFoundError(
                f"kallaway sfx kind {kind} needs the Viral Reels pack at {pack_dir()} "
                "(set SFX_PACK_DIR). At least two files are required.")
        copied = []
        for index, source in enumerate(sources[:3], start=1):
            samples, _info = load(source)
            dest = directory / f"{kind}-{index}.wav"
            write_wav(dest, samples)
            copied.append(dest)
        shutil.copyfile(copied[0], directory / f"{kind}.wav")
        written[kind] = copied
    note = directory / "PACK.txt"
    note.write_text(
        "Decoded from a local Viral Reels SFX Pack for this composition only.\n"
        "The pack is not redistributed. See THIRD_PARTY_NOTICES.md.\n"
        f"SFX_PACK_DIR={pack_dir()}\n"
    )
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


# Keep the decay, including a quiet fricative the broadband meter would miss.
_HEAD_PAD = 0.030
_TAIL_PAD = 0.040
_TAIL_SEARCH = 0.350
_TAIL_MARGIN_DB = 3.0
_FRICATIVE_LOW = 3000.0
_FRICATIVE_HIGH = 10000.0


def _db(amplitude):
    return 20.0 * math.log10(max(float(amplitude), 1e-8))


def _biquad(samples, b0, b1, b2, a1, a2):
    from scipy.signal import lfilter
    return lfilter(
        [b0, b1, b2], [1.0, a1, a2], np.asarray(samples, dtype=np.float64))


def _rbj(samples, rate, freq, kind):
    """One RBJ biquad. ``kind`` is highpass or lowpass."""
    freq = min(float(freq), float(rate) * 0.45)
    omega = 2.0 * math.pi * freq / float(rate)
    cosine = math.cos(omega)
    alpha = math.sin(omega) / (2.0 * 0.707)
    if kind == "highpass":
        b0 = (1.0 + cosine) / 2.0
        b1 = -(1.0 + cosine)
        b2 = (1.0 + cosine) / 2.0
    else:
        b0 = (1.0 - cosine) / 2.0
        b1 = 1.0 - cosine
        b2 = (1.0 - cosine) / 2.0
    a0 = 1.0 + alpha
    return _biquad(samples, b0 / a0, b1 / a0, b2 / a0, (-2.0 * cosine) / a0, (1.0 - alpha) / a0)


def _fricative_band(samples, rate):
    """3–10 kHz energy. Broadband RMS treats a quiet "s" or "th" as silence."""
    band = _rbj(np.asarray(samples, dtype=np.float64), rate, _FRICATIVE_LOW, "highpass")
    return _rbj(band, rate, _FRICATIVE_HIGH, "lowpass")


def _decay_time(times, frames, thresh, whisper_end, limit):
    """Where the word settles at the floor, ignoring a single mouth-noise blip.

    A run of about 40 ms under the threshold ends the word. A one-frame spike
    after that does not pull the cut back into the noise.
    """
    mask = (times >= whisper_end) & (times <= limit)
    if not np.any(mask):
        return float(whisper_end)
    local_t = times[mask]
    local = frames[mask]
    if len(local_t) < 2:
        return float(local_t[-1])
    hop = float(local_t[1] - local_t[0]) if len(local_t) > 1 else 0.005
    quiet_need = max(2, int(round(0.04 / max(hop, 1e-3))))
    run = 0
    for index, level in enumerate(local):
        if float(level) <= thresh:
            run += 1
            if run >= quiet_need:
                return float(local_t[index - quiet_need + 1])
        else:
            run = 0
    hot = np.where(local > thresh)[0]
    if len(hot) == 0:
        return float(whisper_end)
    return float(local_t[hot[-1]])


def refine_word_bounds(samples, rate, words, pad_in=_HEAD_PAD, pad_out=_TAIL_PAD):
    """Keep each word through its decay, including a high-band fricative, then add 40 ms.

    The onset is the speech burst that overlaps the whisper span (a stop closure
    stays inside; a separated breath does not), pulled back 30 ms. The end is where
    BOTH broadband RMS and the 3–10 kHz band have fallen to their own noise floor
    + 3 dB, searched from the whisper end out to +350 ms, plus a 40 ms safety tail.
    ``fricative_tail`` is how long the high band stayed up past the whisper mark.
    """
    samples = np.asarray(samples, dtype=np.float64)
    ordered = sorted(words, key=lambda word: float(word["start"]))
    times, frames = _frame_rms(samples, rate, win_s=0.01, hop_s=0.005)
    _high_times, high_frames = _frame_rms(_fricative_band(samples, rate), rate, win_s=0.01, hop_s=0.005)
    if len(frames) == 0:
        return [dict(word) for word in ordered]
    floor = max(float(np.percentile(frames, 20)), 1e-5)
    thresh = floor * (10 ** (_TAIL_MARGIN_DB / 20.0))
    # The 20th percentile of the high band is often digital silence, which makes
    # every vowel look like a fricative. Use the high band during broadband quiet
    # instead, so the floor is the booth, not a zero sample.
    if len(high_frames) == len(frames):
        quiet = frames <= thresh
        if int(np.count_nonzero(quiet)) > 8:
            high_floor = float(np.percentile(high_frames[quiet], 90))
        else:
            high_floor = float(np.percentile(high_frames, 50))
    else:
        high_floor = float(np.percentile(high_frames, 50)) if len(high_frames) else 1e-5
    high_floor = max(high_floor, 1e-6)
    high_thresh = high_floor * (10 ** (_TAIL_MARGIN_DB / 20.0))
    duration = len(samples) / float(rate)
    refined = []
    for index, word in enumerate(ordered):
        start = float(word["start"])
        end = float(word["end"])
        next_start = float(ordered[index + 1]["start"]) if index + 1 < len(ordered) else duration
        chosen = dict(word)
        lo = max(0.0, start - 0.08)
        hi = min(max(next_start, end), max(end, start) + 0.02)
        mask = (times >= lo) & (times <= max(hi, lo + 0.02))
        local_t = times[mask]
        local = frames[mask]
        onset = start
        if len(local):
            # Floor + 3 dB, not a fraction of the vowel, so a quiet "s" or plosive still counts.
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
            belonging = []
            for run in runs:
                run_start = float(local_t[run[0]])
                run_end = float(local_t[min(run[1] - 1, len(local_t) - 1)])
                if min(run_end, end) - max(run_start, start) > 0.012:
                    belonging.append((run_start, run_end))
            if belonging:
                belonging.sort()
                clusters = [[belonging[0][0], belonging[0][1]]]
                for run_start, run_end in belonging[1:]:
                    if run_start - clusters[-1][1] <= _WORD_BRIDGE_SECONDS:
                        clusters[-1][1] = max(clusters[-1][1], run_end)
                    else:
                        clusters.append([run_start, run_end])

                def cluster_overlap(cluster):
                    return min(cluster[1], end) - max(cluster[0], start)

                onset = max(clusters, key=cluster_overlap)[0]
        # Overlapping tails stay in spoken order. The previous word's end may
        # run into this one; clamping the start to that end would reorder them.
        onset = max(0.0, onset - pad_in)
        if refined:
            onset = max(onset, float(refined[-1]["start"]) + 0.02)
        # A following word that starts while the fricative is still up does not
        # cut it. The ranges overlap and the pause cutter keeps them as one piece.
        limit = min(end + _TAIL_SEARCH, duration)
        broad_end = _decay_time(times, frames, thresh, end, max(end, limit))
        hiss_end = (
            _decay_time(_high_times, high_frames, high_thresh, end, max(end, limit))
            if len(high_frames) else broad_end)
        # A fricative that has already fallen stays inside the 350 ms window.
        # A vowel that is still up there is followed to the floor, at most +700 ms.
        if broad_end >= limit - 0.015:
            far = min(end + 0.700, duration)
            if next_start > end + 0.03:
                far = min(far, max(limit, next_start - 0.004))
            if far > limit + 0.01:
                broad_end = _decay_time(times, frames, thresh, end, far)
                if len(high_frames):
                    hiss_end = max(
                        hiss_end,
                        _decay_time(_high_times, high_frames, high_thresh, end, far))
        decay = max(broad_end, hiss_end)
        offset = min(duration, decay + pad_out)
        # The safety tail is silence after the word. A mouth noise inside those
        # 40 ms is the next event, so the tail stops at the rise.
        rise = thresh * (10 ** (6.0 / 20.0))
        hot = np.where((times > decay + 0.008) & (times <= offset) & (frames > rise))[0]
        if len(hot):
            offset = max(decay, min(offset, float(times[hot[0]]) - 0.004))
        if next_start > end + 0.03 and next_start - 0.004 >= decay:
            offset = min(offset, next_start - 0.004)
        if offset <= onset + 0.04:
            floor_start = float(refined[-1]["start"]) + 0.02 if refined else 0.0
            chosen["start"] = round(max(float(word["start"]), floor_start), 4)
            chosen["end"] = round(max(float(word["end"]), chosen["start"] + 0.041), 4)
            chosen["fricative_tail"] = round(max(0.0, hiss_end - end), 4)
            refined.append(chosen)
            continue
        chosen["start"] = round(onset, 4)
        chosen["end"] = round(offset, 4)
        chosen["fricative_tail"] = round(max(0.0, hiss_end - end), 4)
        refined.append(chosen)
    return refined


def _ending_consonant(word):
    import re
    token = re.sub(r"[^a-z]", "", str(word.get("word", word.get("text", ""))).lower())
    for suffix in ("th", "s", "t", "k", "d"):
        if token.endswith(suffix):
            return suffix
    return ""


def measure_joins(samples, rate, ranges, words):
    """Score each tightened join. The outgoing 20 ms must sit within 3 dB of the noise floor.

    Measured on the source tail that the cutter kept, before the crossfade mixes
    in the next word. ``fricative_tail`` is the high-band life past the whisper mark.
    """
    samples = np.asarray(samples, dtype=np.float64)
    times, frames = _frame_rms(samples, rate, win_s=0.01, hop_s=0.005)
    floor = max(float(np.percentile(frames, 20)) if len(frames) else 1e-5, 1e-6)
    floor_db = _db(floor)
    ordered = list(words)
    joins = []
    clock = 0.0
    for begin, end in ranges[:-1]:
        a = int(max(0, (float(end) - 0.020) * rate))
        b = int(min(len(samples), float(end) * rate))
        chunk = samples[a:b]
        rms = math.sqrt(float(np.dot(chunk, chunk)) / max(1, len(chunk))) if len(chunk) else 0.0
        over = _db(rms) - floor_db
        # A booth floor can sit under the breath. The cut fails when the tail is
        # still up with the vowel, not when a released consonant is merely above silence.
        peak_mask = (times >= float(end) - 0.45) & (times <= float(end) - 0.02)
        peak = float(frames[peak_mask].max()) if np.any(peak_mask) and len(frames) else rms
        released = (_db(peak) - _db(rms)) >= 18.0
        word = min(ordered, key=lambda item: abs(float(item["end"]) - float(end)))
        joins.append({
            "at": round(clock + (float(end) - float(begin)), 3),
            "source_end": round(float(end), 3),
            "word": str(word.get("word", word.get("text", ""))),
            "consonant": _ending_consonant(word),
            "fricative_tail": round(float(word.get("fricative_tail") or 0.0), 3),
            "tail_db": round(_db(rms), 2),
            "floor_db": round(floor_db, 2),
            "over_db": round(over, 2),
            "ok": over <= _TAIL_MARGIN_DB + 0.05 or released,
        })
        clock += float(end) - float(begin)
    return joins


def keep_ranges(words, source_duration, gap=0.02, handle=0.0):
    """Cut pauses longer than ``gap`` seconds down to about ``gap``.

    ``gap`` is the silence left between phrases (0 to 40 ms). The word bounds
    already include the decay and the safety tail, so this only deletes the
    air in the middle. ``handle`` is extra time outside those bounds.
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


def _load_mix_voice(path, rate=RATE):
    """Stereo voice for the SFX bake, averaged so a correlated pair does not sum past 0 dBFS.

    ``-ac 1`` adds the channels. The leveled file already peaks near -1 dBTP per
    channel, and that sum clips before a single effect is added.
    """
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(rate), "-f", "f32le", "-"])
    samples = np.frombuffer(raw, dtype="<f4").reshape(-1, 2).mean(axis=1)
    return np.ascontiguousarray(samples, dtype=np.float64)


def tighten_video(source, words, output, gap=0.02, handle=0.0, crossfade=0.012):
    """Write a tight 1x cut of the talking-head take and remap word times.

    Each word keeps its decay plus a safety tail. Pauses longer than ``gap``
    are cut down to about ``gap``, and each join gets an equal-power crossfade.
    Picture hard-cuts at the midpoint of that crossfade so the clocks match.
    """
    if not 0 <= crossfade <= 0.02:
        raise ValueError("cut crossfade must be between 0 and 20 ms")
    source, output = Path(source), Path(output)
    duration = _probe_duration(source)
    samples = _load_mono(source)
    refined = refine_word_bounds(samples, RATE, words)
    ranges = keep_ranges(refined, duration, gap=gap, handle=handle)
    # Picture hard-cuts on the word boundary. The crossfade lives in the silence
    # after the safety tail, so it does not eat the fricative.
    video = list(ranges)
    filters = []
    expected = 0.0
    last = len(ranges) - 1
    for index, (begin, end) in enumerate(ranges):
        vb, ve = video[index]
        filters.append(f"[0:v]trim=start={vb:.6f}:end={ve:.6f},setpts=PTS-STARTPTS[v{index}]")
        audio_end = end
        if crossfade and index < last:
            audio_end = min(ranges[index + 1][0], end + crossfade)
        length = audio_end - begin
        fades = ""
        if index == 0:
            fades += ",afade=t=in:d=0.004"
        if index == last:
            fades += f",afade=t=out:st={max(0, length - 0.004):.6f}:d=0.004"
        filters.append(
            f"[0:a]atrim=start={begin:.6f}:end={audio_end:.6f},asetpts=PTS-STARTPTS{fades}[a{index}]")
        expected += ve - vb
    if crossfade and len(ranges) > 1:
        # Quarter-sine curves are equal-power, so the join does not dip.
        filters.append(f"[a0][a1]acrossfade=d={crossfade:.4f}:c1=qsin:c2=qsin[ax1]")
        for index in range(2, len(ranges)):
            prev = f"ax{index - 1}"
            filters.append(f"[{prev}][a{index}]acrossfade=d={crossfade:.4f}:c1=qsin:c2=qsin[ax{index}]")
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
         "-g", "15", "-keyint_min", "15",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)],
        check=True)
    from edit import map_words
    segments = [{"start": begin, "end": end} for begin, end in video]
    mapped = map_words(refined, segments)
    joins = measure_joins(samples, RATE, ranges, refined)
    return {"output": str(output), "words": mapped, "ranges": video, "joins": joins,
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


# Momentary SFX loudness sits this far under the voice's short-term loudness.
# Playbook S5, no music: pops and ticks -10 to -16, whooshes -8 to -12,
# dings and the cash register -8 to -12, impacts -4 to -8.
UNDER_DB = {
    "pop": 13.0, "click": 13.0, "typing": 13.0, "ticking": 13.0,
    "marker": 18.0, "paper": 10.0, "error": 6.0,
    "whoosh": 10.0, "riser": 10.0, "ding": 10.0, "bass": 6.0,
}
_MOMENTARY_S = 0.400
_SHORTTERM_S = 3.0
# ITU-R BS.1770-4 pre-filter and RLB weighting, 48 kHz.
_K_PRE_B = (1.53512485958697, -2.69169618940638, 1.19839281085285)
_K_PRE_A = (-1.69065929318241, 0.73248077421585)
_K_RLB_B = (1.0, -2.0, 1.0)
_K_RLB_A = (-1.99004745483398, 0.99007225036621)


def _resample(samples, src_rate, dst_rate):
    samples = np.asarray(samples, dtype=np.float64)
    if int(src_rate) == int(dst_rate) or len(samples) == 0:
        return samples
    duration = len(samples) / float(src_rate)
    dest_n = max(1, int(round(duration * dst_rate)))
    source_x = np.linspace(0.0, duration, num=len(samples), endpoint=False)
    dest_x = np.linspace(0.0, duration, num=dest_n, endpoint=False)
    return np.interp(dest_x, source_x, samples)


def _lufs(mean_square):
    if mean_square <= 1e-20:
        return -120.0
    return -0.691 + 10.0 * math.log10(mean_square)


def _k_weight(samples, rate):
    weighted = _resample(samples, rate, RATE)
    weighted = _biquad(weighted, *_K_PRE_B, *_K_PRE_A)
    return _biquad(weighted, *_K_RLB_B, *_K_RLB_A)


def _momentary_lufs(weighted, start):
    """Ungated 400 ms K-weighted loudness. A short click is scored in the full window."""
    count = int(round(_MOMENTARY_S * RATE))
    origin = int(round(float(start) * RATE))
    chunk = np.zeros(count, dtype=np.float64)
    src_a = max(0, origin)
    src_b = min(len(weighted), origin + count)
    if src_b > src_a:
        dest = src_a - origin
        chunk[dest:dest + (src_b - src_a)] = weighted[src_a:src_b]
    return _lufs(float(np.dot(chunk, chunk)) / count)


def _loudest_momentary(weighted):
    """Loudest ungated 400 ms window. Returns LUFS and the window start in seconds."""
    count = int(round(_MOMENTARY_S * RATE))
    if len(weighted) == 0:
        return -120.0, 0.0
    if len(weighted) <= count:
        return _lufs(float(np.dot(weighted, weighted)) / max(1, len(weighted))), 0.0
    step = max(1, int(round(0.010 * RATE)))
    power = np.cumsum(weighted * weighted)
    best = -120.0
    best_at = 0
    last = len(weighted) - count
    for origin in range(0, last + 1, step):
        total = float(power[origin + count - 1] - (power[origin - 1] if origin else 0.0))
        val = _lufs(total / count)
        if val > best:
            best = val
            best_at = origin
    return best, best_at / float(RATE)


def _placed_window(weighted):
    """400 ms window that should land on the cue, and where it starts in the file.

    Boom 14 and Ka Ching 02 open on silence. Scoring that head as the level
    asks for tens of dB of gain, and the hit then arrives late. When the head
    is more than 8 dB quieter than the loudest window, skip to that window.
    """
    loud, body = _loudest_momentary(weighted)
    head = _momentary_lufs(weighted, 0.0)
    if body > 0.02 and loud > head + 8.0:
        return loud, body
    return head, 0.0


def _short_term_lufs(weighted, start):
    """Ungated 3 s K-weighted loudness around ``start``, using samples that exist."""
    origin = int(round((float(start) - _SHORTTERM_S / 2.0) * RATE))
    end = origin + int(round(_SHORTTERM_S * RATE))
    origin = max(0, origin)
    end = min(len(weighted), max(origin + 1, end))
    chunk = weighted[origin:end]
    if len(chunk) < int(0.05 * RATE):
        return -120.0
    return _lufs(float(np.dot(chunk, chunk)) / len(chunk))


def _load_wav(path):
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"{path} is not 16-bit PCM")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return _resample(samples, rate, RATE)


def _cue_for_mix(cue, library, variant_use):
    """Resolve one cue to a pack path. Muted cues are not played."""
    if cue.get("mute"):
        return None
    kind = str(cue.get("kind") or "")
    if kind not in SFX_KINDS:
        raise ValueError(f"unknown sfx kind: {kind}")
    chosen = cue.get("file")
    if not chosen:
        variants = sfx_variants(kind, library)
        if not variants:
            raise FileNotFoundError(f"no recordings for {kind}")
        slot = variant_use.get(kind, 0)
        variant_use[kind] = slot + 1
        chosen = variants[slot % len(variants)]
    prepared_cue = dict(cue)
    prepared_cue["file"] = str(chosen)
    prepared_cue["kind"] = kind
    return prepared_cue


def mix_cues(voice, rate, cues, library=None):
    """Place each cue so its momentary loudness sits under the voice at that moment.

    The offset is SFX momentary LUFS minus voice short-term LUFS, not a peak
    ratio. Pack files are not filtered. A file that peaks above 0 dBFS is
    turned down to 0 dBFS before that measurement. ``sound_at`` is the sample
    start; a reverse cue with ``align`` end finishes on ``sound_at``.

    A file that opens on silence is trimmed to its loud window so the hit
    lands on that time and the gain is not taken from the silence. Gain is
    clamped so a bad measurement cannot boost a cue by tens of dB.
    """
    from kallaway_pack import render
    voice = _resample(voice, rate, RATE)
    weighted_voice = _k_weight(voice, RATE)
    mixed = np.array(voice, dtype=np.float64, copy=True)
    variant_use = {}
    report = []
    for index, cue in enumerate(cues):
        prepared_cue = _cue_for_mix(cue, library, variant_use)
        if prepared_cue is None:
            continue
        prepared, placed, info = render(prepared_cue)
        if len(prepared) == 0:
            continue
        weighted_cue = _k_weight(prepared, RATE)
        if prepared_cue.get("align") == "end":
            cue_lufs, _body = _loudest_momentary(weighted_cue)
            body_at = 0.0
        else:
            cue_lufs, body_at = _placed_window(weighted_cue)
        if cue_lufs <= -70.0:
            continue
        voice_lufs = _short_term_lufs(weighted_voice, max(0.0, placed))
        under = prepared_cue.get("under_db")
        under = float(UNDER_DB.get(prepared_cue["kind"], 16.0) if under is None else under)
        target = voice_lufs - under
        gain_db = float(np.clip(target - cue_lufs, -40.0, 12.0))
        gain = 10 ** (gain_db / 20.0)
        offset = int(round(body_at * RATE))
        chunk = prepared[offset:]
        if offset > 0 and len(chunk):
            fade_n = min(len(chunk), int(round(0.005 * RATE)))
            chunk[:fade_n] *= np.linspace(0.0, 1.0, fade_n)
        start = int(round(placed * RATE))
        if start < 0:
            chunk = chunk[-start:]
            start = 0
        if 0 <= start < len(mixed) and len(chunk):
            stop = min(len(mixed), start + len(chunk))
            mixed[start:stop] += chunk[:stop - start] * gain
        report.append({
            "source_index": index,
            "kind": prepared_cue["kind"],
            "at": round(placed, 3),
            "cue_at": round(float(cue.get("at", placed)), 3),
            "body_at": round(body_at, 3),
            "under_db": under,
            "voice_lufs": round(voice_lufs, 2),
            "cue_lufs": round(cue_lufs, 2),
            "target_lufs": round(target, 2),
            "gain_db": round(gain_db, 2),
            "gain": round(gain, 5),
            "file": str(prepared_cue["file"]),
            "combo": cue.get("combo"),
            "label": cue.get("label"),
            "clip_gain_db": info.get("clip_gain_db", 0.0),
            "trim": prepared_cue.get("trim"),
            "trim_from": prepared_cue.get("trim_from"),
            "fade_out": prepared_cue.get("fade_out"),
            "fade_in": prepared_cue.get("fade_in"),
            "align": prepared_cue.get("align"),
            "loop": prepared_cue.get("loop"),
        })
    return mixed, report


def measure_sfx_stem(voice, rate, cues, library=None):
    """Mix the cues, subtract the voice-only render, and score every cue.

    A cue with no neighbor inside its 400 ms window must land within 2 dB of
    its target. A clustered cue must not come in quieter than that target, and
    its own 30 ms attack must land within 2 dB of the gained recording.
    """
    voice = _resample(voice, rate, RATE)
    mixed, report = mix_cues(voice, RATE, cues, library)
    isolated = mixed - voice
    weighted = _k_weight(isolated, RATE)
    from kallaway_pack import render
    rows = []
    for row in report:
        measured = _momentary_lufs(weighted, row["at"])
        error = measured - row["target_lufs"]
        window = [
            other for other in report
            if -0.08 <= float(other["at"]) - float(row["at"]) < (_MOMENTARY_S - 0.02)
        ]
        attack_n = int(round(0.030 * RATE))
        origin = int(round(float(row["at"]) * RATE))
        if origin < 0:
            attack = isolated[0:max(0, origin + attack_n)]
        else:
            attack = isolated[origin:origin + attack_n]
        attack_peak = float(np.max(np.abs(attack))) if len(attack) else 0.0
        prepared, _placed, _info = render(row)
        body = int(round(float(row.get("body_at") or 0.0) * RATE))
        cue_peak = float(np.max(np.abs(prepared[body:body + attack_n]))) if len(prepared) else 0.0
        cue_peak *= 10 ** (row["gain_db"] / 20.0)
        if cue_peak > 1e-8 and attack_peak > 0:
            attack_error = 20.0 * math.log10(attack_peak / cue_peak)
        else:
            attack_error = -120.0
        clustered = len(window) > 1
        if clustered:
            # Cues that share the 400 ms window add as power. The stem has to
            # match that sum, so a missing or quiet cue still fails.
            power = sum(10 ** (float(item["target_lufs"]) / 10.0) for item in window)
            expected = 10.0 * math.log10(max(power, 1e-20))
            judged = measured - expected
        else:
            expected = row["target_lufs"]
            judged = error
        scored = dict(row)
        scored["stem_lufs"] = round(measured, 2)
        scored["expected_lufs"] = round(expected, 2)
        scored["error_db"] = round(judged, 2)
        scored["attack_error_db"] = round(attack_error, 2)
        scored["clustered"] = clustered
        scored["ok"] = abs(judged) <= 2.0
        rows.append(scored)
    return rows


def mix_voice_sfx(source, output, cues, library=None):
    """Bake the leveled cues into the voice file. The picture is copied."""
    source, output = Path(source), Path(output)
    voice = _load_mix_voice(source, RATE)
    mixed, report = mix_cues(voice, RATE, cues, library)
    # A hot cue must not turn the voice down. Pull only the samples that cross
    # the ceiling, and only by reducing the effect under them. If the voice
    # itself is still over, a small whole-mix trim is the last resort.
    limit = 0.98
    peak = float(np.max(np.abs(mixed))) if len(mixed) else 0.0
    trim_db = 0.0
    if peak > limit and len(mixed) == len(voice):
        sfx = mixed - voice
        direction = np.sign(mixed)
        direction[direction == 0.0] = 1.0
        over = np.abs(mixed) > limit
        sfx = sfx.copy()
        sfx[over] = limit * direction[over] - voice[over]
        mixed = voice + sfx
        peak = float(np.max(np.abs(mixed))) if len(mixed) else 0.0
    if peak > limit:
        trim = limit / peak
        trim_db = 20.0 * math.log10(trim)
        mixed = mixed * trim
        peak = limit
    pcm = np.clip(mixed, -1.0, 1.0).astype(np.float32)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0",
         "-i", str(source), "-map", "1:v:0", "-map", "0:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", str(output)],
        input=pcm.tobytes(), check=True)
    return {"output": str(output), "peak": round(peak, 4), "trim_db": round(trim_db, 3), "cues": report}
