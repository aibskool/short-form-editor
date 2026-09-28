#!/usr/bin/env python3
"""Transcribe local takes with word timestamps using NVIDIA Parakeet TDT through sherpa-onnx.

Runs fully offline once the model is downloaded, which suits machines where the
Whisper weights cannot be fetched. Output matches what intake.py --transcript,
prepare_take.py and edit.py read: {"words": [{"word", "start", "end"}], ...}.

    pip install sherpa-onnx
    curl -L -o parakeet.tar.bz2 https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2
    tar xjf parakeet.tar.bz2
    python3 transcribe_parakeet.py --model-dir sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8 --out words/ A01.mov A02.mov

Word ends come from the next token's start (or the model's token durations when
available), trimmed to where the audio actually falls quiet. Check names and
numbers against the recording before rendering.
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

RATE = 16000


def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(RATE),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def recognizer(model_dir, threads):
    import sherpa_onnx
    model_dir = Path(model_dir)
    pick = lambda stem: str(next(p for p in (model_dir / f"{stem}.int8.onnx", model_dir / f"{stem}.onnx") if p.is_file()))
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=pick("encoder"), decoder=pick("decoder"), joiner=pick("joiner"),
        tokens=str(model_dir / "tokens.txt"), num_threads=threads, model_type="nemo_transducer")


def speech_end(audio, start, limit, floor):
    """Last moment before `limit` where the 10 ms envelope is still above the noise floor."""
    a, b = int(start * RATE), int(limit * RATE)
    if b - a < 160:
        return limit
    frames = audio[a:b][: (b - a) // 160 * 160].reshape(-1, 160)
    loud = np.sqrt((frames ** 2).mean(axis=1)) > floor
    if not loud.any():
        return min(limit, start + .12)
    return start + (np.nonzero(loud)[0][-1] + 1) * .01


def words_from_result(result, audio, duration):
    tokens, starts = list(result.tokens), list(result.timestamps)
    durations = list(getattr(result, "durations", []) or [])
    rms = np.sqrt(np.convolve(audio ** 2, np.ones(480) / 480, mode="same")) if len(audio) else np.zeros(1)
    floor = max(1e-4, float(np.percentile(rms, 20)) * 2.5)
    words = []
    for i, (token, start) in enumerate(zip(tokens, starts)):
        text = token.replace("▁", " ")
        if text.startswith(" ") or not words:
            words.append({"word": text.strip(), "start": float(start), "tokens": [i]})
        else:
            words[-1]["word"] += text
            words[-1]["tokens"].append(i)
    for w in words:
        last = w.pop("tokens")[-1]
        nxt = float(starts[last + 1]) if last + 1 < len(starts) else duration
        if durations and last < len(durations) and durations[last] > 0:
            limit = min(nxt, float(starts[last]) + float(durations[last]) + .08)
        else:
            limit = min(nxt, float(starts[last]) + .6)
        w["end"] = round(max(w["start"] + .05, speech_end(audio, w["start"], limit, floor)), 3)
        w["start"] = round(w["start"], 3)
    return [w for w in words if w["word"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="folder for <source>.words.json")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    asr = recognizer(args.model_dir, args.threads)
    for source in args.sources:
        audio = load_audio(source)
        stream = asr.create_stream()
        stream.accept_waveform(RATE, audio)
        asr.decode_stream(stream)
        duration = len(audio) / RATE
        words = words_from_result(stream.result, audio, duration)
        record = {"source": source.name, "engine": "parakeet-tdt-0.6b-v2 (sherpa-onnx)", "duration": round(duration, 3),
                  "text": stream.result.text.strip(), "words": words}
        target = args.out / f"{source.stem}.words.json"
        target.write_text(json.dumps(record, indent=1) + "\n")
        print(f"{source.name} ({duration:.2f}s): {record['text']}")


if __name__ == "__main__":
    main()
