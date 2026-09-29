"""Original synthesized UI sound effects (no third-party samples, no tonal beeps).

Every sound is generated deterministically from seeded noise and short pitch-
dropping bodies, then peak-normalized. Levels in DEFAULT_GAIN sit well under
speech; judge the final mix by listening at phone volume.
"""
import math
import re
import wave
from pathlib import Path

import numpy as np
from scipy import signal

RATE = 48000

import style

DEFAULT_GAIN = {
    "whoosh": .20, "whoosh_short": .18, "swipe": .13, "pop": .20, "tick": .16, "tap": .17,
    "typing": .12, "thud": .24, "riser": .13, "draw": .10, "paper": .15, "deny": .18,
    "stamp": .24, "shimmer": .07, "ticker": .12, "bubble": .16, "bubble_soft": .12, "impact_soft": .2,
}
IMPACTS = {"thud", "stamp", "riser", "impact_soft"}
BUBBLES = {"bubble", "bubble_soft"}
# Level of each sound's loudest 400 ms relative to the voice's integrated loudness (LU),
# from the house style spec; kinds the spec does not list keep these fallbacks.
VOICE_OFFSET = {
    "whoosh": -10, "whoosh_short": -11, "swipe": -13, "pop": -12, "tap": -14, "tick": -15, "typing": -16,
    "ticker": -16, "draw": -15, "paper": -13, "deny": -12, "stamp": -9, "thud": -9, "riser": -12, "shimmer": -18,
    "bubble": -15, "bubble_soft": -18, "impact_soft": -12,
}
VOICE_OFFSET.update(style.load()["sound"]["voice_offset_lu"])
# Older timelines named sounds that are now retired; "pop" becomes the bubble family.
LEGACY = {"soft_pop": "bubble", "soft_click": "tick", "soft_whoosh": "whoosh_short", "soft_error": "deny", "pop": "bubble"}
KINDS = frozenset(DEFAULT_GAIN)
VARIANTS = int(style.load()["sound"].get("bubble_variants", 6))
HOOK_WINDOW = float(style.load()["hook"]["payoff_by"])


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def _env(n, attack, release, curve=2.0):
    t = np.linspace(0, 1, n, endpoint=False)
    a = max(attack, 1e-4)
    rise = np.clip(t / a, 0, 1) ** 1.5
    fall = np.clip((1 - t) / max(release, 1e-4), 0, 1) ** curve
    return np.minimum(rise, fall)


def _band_sweep(noise, centers, width_octaves):
    """Shape noise with a moving Gaussian band (centers: Hz per STFT frame)."""
    f, t, z = signal.stft(noise, RATE, nperseg=1024, noverlap=768)
    frames = z.shape[1]
    c = np.interp(np.linspace(0, 1, frames), np.linspace(0, 1, len(centers)), centers)
    logf = np.log2(np.maximum(f, 20))[:, None]
    mask = np.exp(-0.5 * ((logf - np.log2(c)[None, :]) / width_octaves) ** 2)
    _, out = signal.istft(z * mask, RATE, nperseg=1024, noverlap=768)
    return out[:len(noise)]


def _body(n, f0, f1, decay):
    t = np.arange(n) / RATE
    freq = f1 + (f0 - f1) * np.exp(-t / max(decay * .45, 1e-4))
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    return np.sin(phase) * np.exp(-t / decay)


def _lp(x, cutoff, order=2):
    sos = signal.butter(order, cutoff, "lowpass", fs=RATE, output="sos")
    return signal.sosfilt(sos, x)


def _bp(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, hi], "bandpass", fs=RATE, output="sos")
    return signal.sosfilt(sos, x)


def _click(n, seed, lo=2500, hi=7000, decay=.006):
    t = np.arange(n) / RATE
    burst = _bp(_noise(n, seed), lo, hi) * np.exp(-t / decay)
    return burst


def _bubble(seed, variant, soft=False):
    """Soft, rounded bubble pop: a short sine whose pitch rises as the bubble closes,
    a smooth attack and a quick decay, low-passed for roundness. Each variant shifts
    pitch, glide, decay and texture slightly so repeated pop-ups never sound identical."""
    rng = np.random.default_rng(1000 + seed * 31 + variant * 7)
    base = (330 if soft else 470) * (0.88 + 0.24 * rng.random())
    rise = (0.30 if soft else 0.42) + 0.30 * rng.random()
    decay = (0.034 if soft else 0.026) + 0.014 * rng.random()
    n = int(RATE * (0.16 if soft else 0.13))
    t = np.arange(n) / RATE
    freq = base * (1 + rise * (1 - np.exp(-t / 0.016)))
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    attack = 0.5 - 0.5 * np.cos(np.pi * np.clip(t / 0.004, 0, 1))
    env = attack * np.exp(-t / decay)
    tone = np.sin(phase) + (0.06 + 0.1 * rng.random()) * np.sin(2.3 * phase + 0.7)
    wet = _lp(_noise(n, seed + 90 + variant), 3200) * np.exp(-t / 0.004) * (0.04 if soft else 0.07) * (0.6 + 0.8 * rng.random())
    x = tone * env + wet
    x = _lp(x, 2600 if soft else 3400, order=2)
    sos = signal.butter(2, 140, "highpass", fs=RATE, output="sos")
    return signal.sosfilt(sos, x)


def synth(kind, duration=None, seed=7, variant=0):
    kind = LEGACY.get(kind, kind)
    if kind in BUBBLES:
        x = _bubble(seed, variant, soft=kind == "bubble_soft")
    elif kind == "impact_soft":
        # Restrained reveal impact: a low rounded body and a short air tail, no crack.
        n = int(RATE * .46)
        t = np.arange(n) / RATE
        body = _body(n, 82, 44, .15) * (0.5 - 0.5 * np.cos(np.pi * np.clip(t / .006, 0, 1)))
        air = _lp(_noise(n, seed + 95), 1100) * np.exp(-t / .045) * .28
        x = _lp(body + air, 1800)
    elif kind == "whoosh":
        n = int(RATE * .56)
        x = _band_sweep(_noise(n, seed), [380, 900, 2300, 1500, 700], .9) * _env(n, .58, .42, 2.4)
    elif kind == "whoosh_short":
        n = int(RATE * .32)
        x = _band_sweep(_noise(n, seed + 1), [600, 1600, 3200, 1800], .8) * _env(n, .5, .5, 2.2)
    elif kind == "swipe":
        n = int(RATE * .2)
        x = _band_sweep(_noise(n, seed + 2), [1800, 4200, 6500], .6) * _env(n, .35, .65, 2.6)
    elif kind == "pop":
        n = int(RATE * .11)
        t = np.arange(n) / RATE
        air = _lp(_noise(n, seed + 3), 2600) * np.exp(-t / .018) * np.clip(t / .003, 0, 1)
        x = air + .32 * _body(n, 300, 140, .026)  # air-led pop; the body stays a thump, not a tone
    elif kind == "tick":
        n = int(RATE * .035)
        x = _click(n, seed + 4, 2800, 7500, .005)
    elif kind == "tap":
        n = int(RATE * .08)
        x = np.zeros(n)
        first = _click(int(RATE * .03), seed + 5, 1400, 4200, .006)
        second = .55 * _click(int(RATE * .03), seed + 6, 1600, 5000, .005)
        x[:len(first)] += first
        offset = int(RATE * .042)
        x[offset:offset + len(second)] += second[:n - offset]
    elif kind == "typing":
        length = max(.2, float(duration or .8))
        n = int(RATE * length)
        x = np.zeros(n)
        rng = np.random.default_rng(seed + 7)
        cursor = int(RATE * .01)
        while cursor < n - int(RATE * .03):
            key = _click(int(RATE * .028), int(rng.integers(1, 1 << 30)), 1200 + rng.random() * 900, 4200 + rng.random() * 2500, .004 + rng.random() * .003)
            key *= .55 + rng.random() * .45
            end = min(n, cursor + len(key))
            x[cursor:end] += key[:end - cursor]
            cursor += int(RATE * (.055 + rng.random() * .075))
        x *= _env(n, .04, .08, 1.0)
    elif kind == "ticker":
        # Decelerating ticks for a count-up; spacing widens like an expo.out counter.
        length = max(.25, float(duration or 1.0))
        n = int(RATE * length)
        x = np.zeros(n)
        count = max(4, min(16, int(length * 11)))
        for i in range(count):
            frac = 1 - (1 - i / count) ** 2.4
            start = int(frac * (n - int(RATE * .03)))
            tick = _click(int(RATE * .03), seed + 40 + i, 2600, 7600, .0045) * (1 - .45 * i / count)
            x[start:start + len(tick)] += tick[:n - start]
    elif kind == "thud":
        n = int(RATE * .5)
        t = np.arange(n) / RATE
        x = _body(n, 96, 44, .16) + .35 * _lp(_noise(n, seed + 8), 900) * np.exp(-t / .012)
    elif kind == "riser":
        n = int(RATE * .9)
        x = _band_sweep(_noise(n, seed + 9), [300, 700, 1600, 3600, 5200], .7) * _env(n, .92, .08, 1.2)
    elif kind == "draw":
        n = int(RATE * .36)
        t = np.arange(n) / RATE
        grain = 1 + .6 * np.sin(2 * np.pi * 27 * t + 3 * np.sin(2 * np.pi * 3.1 * t))
        x = _bp(_noise(n, seed + 10), 1800, 5200) * grain * _env(n, .25, .5, 1.6)
    elif kind == "paper":
        n = int(RATE * .42)
        x = np.zeros(n)
        rng = np.random.default_rng(seed + 11)
        for i in range(4):
            start = int(RATE * (.02 + i * .085 + rng.random() * .02))
            size = int(RATE * .07)
            burst = _lp(_bp(_noise(size, seed + 20 + i), 700, 6000), 5000) * _env(size, .2, .8, 2.5) * (.9 - i * .15)
            end = min(n, start + size)
            x[start:end] += burst[:end - start]
    elif kind == "deny":
        n = int(RATE * .24)
        x = np.zeros(n)
        for i, (f0, f1) in enumerate(((150, 92), (135, 80))):
            size = int(RATE * .11)
            knock = _body(size, f0, f1, .035) + .25 * _click(size, seed + 30 + i, 600, 2200, .004)
            start = int(RATE * .1 * i)
            x[start:start + size] += knock[:n - start] * (1 if i == 0 else .8)
    elif kind == "stamp":
        n = int(RATE * .34)
        t = np.arange(n) / RATE
        x = .8 * _body(n, 130, 58, .07) + .6 * _lp(_noise(n, seed + 12), 1600) * np.exp(-t / .02)
    elif kind == "shimmer":
        n = int(RATE * .6)
        t = np.arange(n) / RATE
        x = _bp(_noise(n, seed + 13), 5500, 11000) * (0.55 + .45 * np.sin(2 * np.pi * 17 * t)) * _env(n, .3, .7, 1.8)
    else:
        raise ValueError(f"unknown SFX kind {kind!r}; choose from {', '.join(sorted(KINDS))}")
    peak = float(np.max(np.abs(x))) or 1.0
    return x / peak * 10 ** (-1 / 20)  # -1 dBFS peak


def write(kind, path, duration=None, variant=0):
    data = synth(kind, duration, variant=variant)
    pcm = np.clip(data * 32767, -32768, 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        out.writeframes(pcm)
    return len(data) / RATE


TRANSIENTS = {"pop", "tick", "tap", "draw", "deny", "stamp", "thud", "bubble", "bubble_soft", "impact_soft"}
SUSTAINED = {"typing", "ticker", "riser", "shimmer", "paper"}


def priority(event, hook_window=HOOK_WINDOW):
    """Lower wins: explicit > transitions/layout moves > anything in the hook window >
    reveals and sustained sounds > entrances."""
    if event.get("explicit"):
        return 0
    source = str(event.get("source", ""))
    kind = LEGACY.get(event["kind"], event["kind"])
    if re.fullmatch(r"(transition|shot|camera)-\d+", source):
        return 1  # section moves (a highlight inside a shot is an entrance, not a move)
    if float(event["at"]) < hook_window:
        return 1.5  # the hook's own pop-ups keep their sound ahead of later ones
    if kind in SUSTAINED or kind in {"stamp", "thud", "deny", "impact_soft"} or event.get("role") == "reveal":
        return 2
    return 3


def speech_rate(words, at, window=.6):
    """Words per second around a moment; dense speech has no room for a pop."""
    if not words:
        return 0.0
    count = sum(1 for w in words if at - window <= float(w["start"]) <= at + window)
    return count / (2 * window)


def plan(events, duration, policy=None, words=None, house=None):
    """Keep sound effects sparse: bubble pops only where a pop-up lands and speech leaves room,
    one pop per cluster of arrivals, quiet whooshes spaced out, an impact budget, a cap per
    ten seconds and per spoken word. Sustained sounds may layer under a transient.
    ``house`` is the (timeline-merged) style spec. Returns (kept, dropped)."""
    spec = house or style.load()
    sound = spec["sound"]
    policy = dict({"min_gap": .12, "max_impacts": sound["max_impacts"], "impact_gap": sound["impact_gap"],
                   "whoosh_gap": 1.0, "same_kind_gap": .3, "popup_min_gap": sound["popup_min_gap"],
                   "dense_speech_wps": sound["dense_speech_wps"], "max_per_10s": sound["max_per_10s"],
                   "max_per_word": sound.get("max_per_word")},
                  **(policy or {}))
    retired = set(sound.get("forbidden_kinds", [])) - set(LEGACY)
    hook_window = float(spec["hook"]["payoff_by"])
    ordered = sorted(events, key=lambda e: (priority(e, hook_window), float(e["at"])))
    kept, dropped = [], []
    impacts = []
    # Never more than one effect per so many spoken words, whatever the density windows allow.
    budget = max(2, int(len(words) * float(policy["max_per_word"]))) if words and policy.get("max_per_word") else None
    for event in ordered:
        kind = LEGACY.get(event["kind"], event["kind"])
        at = float(event["at"])
        reason = None
        if kind in retired and not event.get("explicit"):
            dropped.append({**event, "kind": kind, "reason": f"{kind} is retired from the house sound policy"})
            continue
        if kind not in KINDS:
            raise ValueError(f"unknown SFX kind {event['kind']!r}")
        if not 0 <= at < duration:
            reason = "outside timeline"
        elif kind in IMPACTS and not event.get("explicit"):
            if len(impacts) >= policy["max_impacts"]:
                reason = "impact budget reached"
            elif any(abs(at - other) < policy["impact_gap"] for other in impacts):
                reason = "impact too close to another impact"
        if reason is None and not event.get("explicit"):
            if kind in BUBBLES and event.get("role") != "reveal" and speech_rate(words, at) > policy["dense_speech_wps"]:
                reason = f"dense speech ({speech_rate(words, at):.1f} words/s) leaves no room for a pop"
            for other in kept:
                if reason:
                    break
                gap = abs(at - other["at"])
                other_kind = other["kind"]
                if kind in BUBBLES and other_kind in BUBBLES and gap < policy["popup_min_gap"]:
                    reason = f"pop-ups arrive in a cluster ({gap:.2f}s apart); one pop covers them"
                elif kind == other_kind and gap < policy["same_kind_gap"]:
                    reason = f"same sound {gap:.2f}s after another {kind}"
                elif kind in TRANSIENTS and other_kind in TRANSIENTS and gap < policy["min_gap"]:
                    reason = f"within {policy['min_gap']}s of {other_kind}"
                elif kind.startswith("whoosh") and other_kind.startswith("whoosh") and gap < policy["whoosh_gap"]:
                    reason = "whooshes too dense"
            if reason is None and budget is not None and len(kept) >= budget:
                reason = f"effects budget reached ({budget} for {len(words)} spoken words)"
            if reason is None and kind not in SUSTAINED:
                # Every ten-second window that would hold this sound stays under the cap.
                near = [o["at"] for o in kept if o["kind"] not in SUSTAINED and abs(o["at"] - at) < 10] + [at]
                for lo in [t for t in near if at - 10 < t <= at]:
                    if sum(1 for t in near if lo <= t < lo + 10) > policy["max_per_10s"]:
                        reason = f"more than {policy['max_per_10s']} effects in ten seconds"
                        break
        if reason:
            dropped.append({**event, "kind": kind, "reason": reason})
            continue
        if kind in IMPACTS:
            impacts.append(at)
        kept.append({**event, "kind": kind})
    kept.sort(key=lambda e: e["at"])
    return kept, dropped


def variant_for(event, variants=None):
    """Stable bubble variant per event so repeats differ but rebuilds stay identical."""
    return int(round(float(event["at"]) * 1000)) * 7919 % int(variants or VARIANTS)


def momentary_max(path, gain=1.0):
    """Loudest 400 ms window (LUFS) of a sound at a gain, padded so short hits register."""
    import re
    import subprocess
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                             f"volume={gain},apad=pad_dur=0.6,ebur128", "-f", "null", "-"],
                            capture_output=True, text=True)
    values = [float(v) for v in re.findall(r"M:\s*(-?\d+\.\d)", result.stderr)]
    return max(values) if values else None


def phone_offset(sound_path, gain, voice_phone_lufs, band=None):
    """Loudest 400 ms of a sound at its gain, through the phone-speaker band, relative to the
    voice measured through the same band (LU). Small speakers drop the low end, so a pop that
    sits well under the voice on headphones can poke out on a phone."""
    import re
    import subprocess
    if voice_phone_lufs is None:
        return None
    lo, hi = band or style.load()["sound"]["phone_band_hz"]
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(sound_path), "-af",
                             f"volume={gain},highpass=f={lo}:poles=2,highpass=f={lo}:poles=2,lowpass=f={hi}:poles=2,"
                             "apad=pad_dur=0.6,ebur128", "-f", "null", "-"], capture_output=True, text=True)
    values = [float(v) for v in re.findall(r"M:\s*(-?\d+\.\d)", result.stderr)]
    if not values or max(values) < -70:
        return None
    return round(max(values) - voice_phone_lufs, 1)


def matched_gain(kind, sound_path, voice_lufs, offsets=None):
    """Gain that places this sound's loudest 400 ms its voice offset (LU) under the recorded
    voice; ``offsets`` are the timeline's merged house-style offsets."""
    if voice_lufs is None:
        return DEFAULT_GAIN[kind]
    level = momentary_max(sound_path)
    if level is None or level < -70:
        return DEFAULT_GAIN[kind]
    target = voice_lufs + (offsets or {}).get(kind, VOICE_OFFSET[kind])
    return round(max(.01, min(1.0, 10 ** ((target - level) / 20))), 4)
