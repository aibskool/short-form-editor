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
from kallaway_audio import mix_voice_sfx, process_voice, tighten_video, write_bed, write_sfx_library  # noqa: E402
from kallaway_matte import attach_popout  # noqa: E402
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


def _scene_times(video):
    """Picture-cut times. A layout boundary near one of these is the same cut."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video),
         "-filter:v", "select='gt(scene,0.28)',showinfo", "-f", "null", "-"],
        capture_output=True, text=True)
    times = []
    for line in result.stderr.splitlines():
        if "pts_time:" not in line:
            continue
        token = line.split("pts_time:", 1)[1].split()[0]
        try:
            times.append(float(token))
        except ValueError:
            continue
    return times


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
        crossfade=float(audio_cfg.get("cut_crossfade_seconds", 0.008)),
        sentence_gap=float(audio_cfg.get("sentence_gap_seconds", audio_cfg["pause_gap_seconds"])))
    leveled = process_voice(
        tightened["output"], project / "voice.mp4",
        target_lufs=float(audio_cfg["voice_lufs"]), true_peak=float(audio_cfg["voice_true_peak"]),
        presence_hz=float(audio_cfg["presence_hz"]), presence_db=float(audio_cfg["presence_db"]),
        ratio=float(audio_cfg.get("compression_ratio", 2.2)))
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
    from kallaway_beats import snap_shot_edges
    timeline["shots"] = snap_shot_edges(timeline.get("shots") or [], _scene_times(leveled["output"]))
    if timeline.get("sfx"):
        baked = project / "voice-sfx.mp4"
        mixed = mix_voice_sfx(leveled["output"], baked, timeline["sfx"], project / "sfx")
        timeline["source"]["path"] = str(baked.resolve())
        timeline["sfx_baked"] = True
        timeline["sfx_mix"] = {"peak": mixed["peak"], "trim_db": mixed["trim_db"]}
        # The report lists only the cues that were played. Zip would write
        # those levels onto muted rows and drop the rest.
        for row in mixed["cues"]:
            cue = timeline["sfx"][row["source_index"]]
            cue.update({
                "under_db": row["under_db"],
                "gain_db": row["gain_db"],
                "gain": row["gain"],
                "target_lufs": row["target_lufs"],
                "voice_lufs": row["voice_lufs"],
                "file": row["file"],
                "body_at": row["body_at"],
            })
    timeline["source"]["segments"] = [{"start": 0, "end": round(float(words[-1]["end"]), 3)}]
    timeline["joins"] = tightened.get("joins") or []
    attach_popout(
        timeline, source, tightened.get("ranges") or [],
        timeline["source"]["path"], theme)
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
    # Playbook S9: -14 LUFS and a true peak at or below -1 dBTP. The headroom
    # keeps the AAC encode from poking back through that ceiling.
    if target_lufs is None:
        target_lufs = -14.0
    if true_peak is None:
        true_peak = -1.0
    if codec_headroom_db is None:
        codec_headroom_db = 0.8
    finalize.extend(["--target-lufs", str(target_lufs), "--true-peak", str(true_peak),
                     "--codec-headroom-db", str(codec_headroom_db)])
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
