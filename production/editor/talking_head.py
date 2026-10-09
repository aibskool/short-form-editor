#!/usr/bin/env python3
"""Render a Kallaway-style branded talking-head reel from one raw video.

python3 talking_head.py --source raw.mp4 --words words.json --output reel.mp4 --cta-keyword VAULT

This is the default path for a new raw talking-head. House-style presenter edits
stay on edit.py with a style object, not the "kallaway" preset.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from edit import build  # noqa: E402
from hyperframes_cli import run as run_hyperframes  # noqa: E402
from kallaway_audio import process_voice, tighten_video, write_bed, write_sfx_library  # noqa: E402
from kallaway_plan import plan_timeline  # noqa: E402
from kallaway_style import load_theme  # noqa: E402
from check_kallaway_style import check as check_style  # noqa: E402


def _read_words(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    if "words" in data:
        return data["words"]
    return [word for segment in data.get("segments", []) for word in segment.get("words", [])]


def _resolve_media(entry, base):
    if not isinstance(entry, dict) or not entry.get("media"):
        return
    media = Path(entry["media"]).expanduser()
    if not media.is_absolute():
        entry["media"] = str((base / media).resolve())


def _load_stage_plan(path):
    path = Path(path)
    data = json.loads(path.read_text())
    base = path.resolve().parent
    entries = data.get("stages") if isinstance(data, dict) else data
    if isinstance(entries, list):
        for entry in entries:
            _resolve_media(entry, base)
    if isinstance(data, dict):
        for beat in data.get("beats") or []:
            _resolve_media(beat, base)
            for overlay in beat.get("overlays") or []:
                _resolve_media(overlay, base)
    return data


def _try_transcribe(source, destination):
    try:
        import whisper
    except ImportError:
        raise SystemExit(
            "No --words file was provided and whisper is not installed. "
            "Pass --words words.json from intake, or install the intake extra and a Whisper model.")
    model = whisper.load_model("base.en")
    result = model.transcribe(str(source), word_timestamps=True)
    words = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            text = str(word.get("word", "")).strip()
            if text:
                words.append({"word": text, "start": float(word["start"]), "end": float(word["end"])})
    if not words:
        raise SystemExit(f"Whisper found no words in {source}")
    destination.write_text(json.dumps({"words": words}, indent=2) + "\n")
    return words


def render(source, output, words_path=None, project=None, keyword=None, title=None, theme_mode="dark",
           theme_path=None, stage_plan=None, music=None, emphasis=None, quality="draft", workers=1,
           skip_render=False, target_lufs=None, true_peak=None, codec_headroom_db=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    project = Path(project).resolve() if project else output.with_suffix("")
    project.mkdir(parents=True, exist_ok=True)
    theme, _colors, mode, _path = load_theme(theme_mode, theme_path)
    audio_cfg = theme["audio"]
    if words_path:
        raw_words = _read_words(words_path)
    else:
        raw_words = _try_transcribe(source, project / "whisper-words.json")
    tightened = tighten_video(
        source, raw_words, project / "tightened.mp4",
        gap=float(audio_cfg["pause_gap_seconds"]),
        handle=float(audio_cfg["join_handle_seconds"]),
        crossfade=float(audio_cfg.get("cut_crossfade_seconds", 0.008)))
    leveled = process_voice(
        tightened["output"], project / "voice.mp4",
        target_lufs=float(audio_cfg["voice_lufs"]), true_peak=float(audio_cfg["voice_true_peak"]),
        presence_hz=float(audio_cfg["presence_hz"]), presence_db=float(audio_cfg["presence_db"]))
    words = tightened["words"]
    # The processed file keeps the tightened picture. Word times are on that clock.
    if words[-1]["end"] > tightened["duration"] + 0.08:
        raise SystemExit("tightened word times run past the cut video; check the source timestamps")
    words_file = project / "words.json"
    words_file.write_text(json.dumps(words, indent=2) + "\n")
    if music is None:
        music = bool(audio_cfg.get("music_default", False))
    music_path = None
    music_note = None
    if music:
        try:
            bpm = None
            if isinstance(stage_plan, dict) and stage_plan.get("bed_bpm"):
                bpm = float(stage_plan["bed_bpm"])
            elif theme.get("audio", {}).get("bed_bpm"):
                bpm = float(theme["audio"]["bed_bpm"])
            music_path = write_bed(project / "music" / "bed.wav", max(8, words[-1]["end"] + 0.25), bpm=bpm)
            music_path = str(Path(music_path).resolve())
        except Exception as exc:  # degrade: a missing bed must not block the picture
            music = False
            music_note = f"Music bed was skipped: {exc}"
    write_sfx_library(project / "sfx")
    # Plan against the leveled file. Its duration matches the tightened cut.
    timeline = plan_timeline(
        words, source_path=str(Path(leveled["output"]).resolve()), words_path=str(words_file.resolve()),
        theme_mode=mode, title=title, keyword=keyword, stage_plan=stage_plan,
        music_path=music_path, music=music, emphasis=emphasis, theme_path=theme_path,
        seed_path=str(source))
    if music_note:
        timeline["audio_policy"]["user_opt_out"] = music_note
    timeline["source"]["segments"] = [{"start": 0, "end": round(float(words[-1]["end"]), 3)}]
    spec_path = project / "timeline.json"
    spec_path.write_text(json.dumps(timeline, indent=2) + "\n")
    pre = check_style(spec_path, words_file)
    if not pre["ok"]:
        raise SystemExit("style check failed before render:\n" + json.dumps(pre, indent=2))
    receipt = build(spec_path, project)
    post = check_style(project / "timeline.json", project / "mapped-words.json", project)
    report = {"precheck": pre, "build": receipt, "postcheck": post, "music_note": music_note,
              "tightened_seconds": tightened["duration"], "source_seconds": None,
              "stage_slots": timeline.get("stage_slots", [])}
    if not post["ok"]:
        (project / "style-check.json").write_text(json.dumps(report, indent=2) + "\n")
        raise SystemExit("style check failed after build:\n" + json.dumps(post, indent=2))
    if skip_render:
        (project / "style-check.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    rendered = project / "render-raw.mp4"
    run_hyperframes(["render", str(project), "--output", str(rendered), "--quality", quality,
                     "--workers", str(workers), "--no-best-effort", "--strict"])
    final = output
    if final.exists():
        raise SystemExit(f"refusing to overwrite {final}")
    # finalize_render treats any ffmpeg stderr as a failed decode. A library-path
    # warning on stderr would fail a good file, so the mix runs with a clean env.
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    finalize = [sys.executable, str(HERE.parent / "finalize_render.py"),
                "--input", str(rendered), "--output", str(final),
                "--receipt", str(project / "final-receipt.json")]
    if target_lufs is not None:
        finalize.extend(["--target-lufs", str(target_lufs)])
    if true_peak is not None:
        finalize.extend(["--true-peak", str(true_peak)])
    if codec_headroom_db is not None:
        finalize.extend(["--codec-headroom-db", str(codec_headroom_db)])
    subprocess.run(finalize, check=True, env=env)
    report["output"] = str(final)
    (project / "style-check.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--words", help="Word timings for the raw source. Whisper is used when this is omitted.")
    parser.add_argument("--project", help="Composition directory. Defaults to the output path without its suffix.")
    parser.add_argument("--cta-keyword", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--theme-mode", choices=["dark", "light"], default="dark")
    parser.add_argument("--theme", default=None, help="Override preset JSON. Colors and fonts live here.")
    parser.add_argument("--stage-plan", default=None,
                        help="JSON list of motifs, or a kallaway-stage-plan/v1 object. See stage-plan.schema.json.")
    parser.add_argument("--emphasis", default=None, help="JSON map of word to normal|marker|green|amber")
    parser.add_argument("--music", action="store_true",
                        help="Mix the CC0 lo-fi bed under the voice. Off unless this flag is set; Brandon adds music on the platform. music_drops in a stage plan apply only with the bed.")
    parser.add_argument("--no-music", action="store_true",
                        help="Leave the bed out. This is the default.")
    parser.add_argument("--quality", choices=["draft", "standard", "high"], default="draft")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--target-lufs", type=float, default=None)
    parser.add_argument("--true-peak", type=float, default=None)
    parser.add_argument("--codec-headroom-db", type=float, default=None,
                        help="Limiter headroom before AAC. Lower this when the deliverable true peak is -1 dBTP.")
    args = parser.parse_args()
    stage_plan = _load_stage_plan(args.stage_plan) if args.stage_plan else None
    emphasis = json.loads(args.emphasis) if args.emphasis else None
    music = None
    if args.music:
        music = True
    if args.no_music:
        music = False
    report = render(
        args.source, args.output, words_path=args.words, project=args.project, keyword=args.cta_keyword,
        title=args.title, theme_mode=args.theme_mode, theme_path=args.theme, stage_plan=stage_plan,
        music=music, emphasis=emphasis, quality=args.quality, workers=args.workers,
        skip_render=args.skip_render, target_lufs=args.target_lufs, true_peak=args.true_peak,
        codec_headroom_db=args.codec_headroom_db)
    print(json.dumps({"output": report.get("output"), "ok": report["postcheck"]["ok"],
                      "warnings": report["postcheck"]["warnings"], "music_note": report.get("music_note"),
                      "stage_slots": report.get("stage_slots")}, indent=2))


if __name__ == "__main__":
    main()
