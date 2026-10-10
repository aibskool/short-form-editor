import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from kallaway_audio import (
    SFX_KINDS, UNDER_DB, _k_weight, _load_mix_voice, _momentary_lufs, keep_ranges,
    measure_sfx_stem, mix_cues, refine_word_bounds, sfx_variants, write_sfx_library,
)
from kallaway_motifs import MOTIFS, motif_markup, resolve_annotations, screenshot_box, stage_events
from kallaway_plan import LIBRARY, caption_phrases, plan_timeline, plain_text, video_seed, _rotate
from kallaway_style import _caption_text, card_state, load_theme


def words_for(duration=16, step=0.34):
    tokens = ("This one change makes a talking head feel edited The old way no longer works "
              "Start on the split and pop the grid Then cut closer on the secret "
              "Show a list a chart and the number Comment VAULT to get the guide").split()
    words = []
    cursor = 0.05
    for token in tokens:
        end = min(duration - 0.05, cursor + 0.22)
        if end <= cursor:
            break
        words.append({"word": token, "start": round(cursor, 3), "end": round(end, 3)})
        cursor += step
        if cursor >= duration:
            break
    words[-1]["end"] = duration
    return words


class KallawayTests(unittest.TestCase):
    def test_theme_is_the_only_palette_source(self):
        theme, dark, mode, _path = load_theme("dark")
        self.assertEqual(mode, "dark")
        self.assertEqual(dark["background"], "#1A1A1A")
        self.assertEqual(dark["accent"], "#54C947")
        self.assertEqual(theme["fonts"]["display"]["family"], "Permanent Marker")
        self.assertEqual(theme["fonts"]["caption"]["family"], "Inter")
        self.assertEqual(theme["fonts"]["mono"]["family"], "IBM Plex Mono")
        self.assertAlmostEqual(theme["layout"]["tight_scale"], 1.08)
        _theme, light, light_mode, _path = load_theme("light")
        self.assertEqual(light_mode, "light")
        self.assertEqual(light["background"], "#FBF8F1")
        self.assertEqual(light["text"], "#211C18")
        self.assertNotIn("\u2014", theme["content"]["lead_magnet_detail"])

    def test_plain_text_strips_em_dash(self):
        self.assertEqual(plain_text("one \u2014 two"), "one , two")

    def test_pause_removal_keeps_short_gaps_and_drops_long_ones(self):
        words = [
            {"word": "keep", "start": 0.2, "end": 0.4},
            {"word": "close", "start": 0.45, "end": 0.7},
            {"word": "later", "start": 1.2, "end": 1.4},
        ]
        ranges = keep_ranges(words, 2.0, gap=0.1, handle=0.02)
        self.assertEqual(len(ranges), 2)
        self.assertLess(ranges[0][1] - ranges[0][0], 0.7)
        self.assertGreater(ranges[1][0], 1.0)
        tight = keep_ranges([
            {"word": "a", "start": 0.0, "end": 0.2},
            {"word": "b", "start": 0.25, "end": 0.4},
        ], 1.0, gap=0.1, handle=0.02)
        self.assertEqual(len(tight), 1)
        cut = keep_ranges([
            {"word": "one", "start": 0.0, "end": 0.3},
            {"word": "two", "start": 0.9, "end": 1.1},
        ], 2.0, gap=0.06, handle=0.0)
        self.assertEqual(len(cut), 2)
        kept = (cut[0][1] - 0.3) + (0.9 - cut[1][0])
        self.assertAlmostEqual(kept, 0.06, places=2)

    def test_energy_trim_drops_a_separated_breath(self):
        rate = 16000
        t = np.arange(rate) / rate
        tone = ((t >= 0.28) & (t < 0.42)).astype(np.float64) * 0.4 * np.sin(2 * np.pi * 220 * t)
        breath = ((t >= 0.05) & (t < 0.12)).astype(np.float64) * 0.05 * np.random.default_rng(1).standard_normal(rate)
        refined = refine_word_bounds(tone + breath, rate, [{"word": "hey", "start": 0.05, "end": 0.50}])
        self.assertGreater(refined[0]["start"], 0.2)
        self.assertLess(refined[0]["start"], 0.30)
        # The whisper mark already sits past the tone, so the safety tail stays on it.
        self.assertGreater(refined[0]["end"], 0.50)
        self.assertLess(refined[0]["end"], 0.56)

    def test_energy_trim_keeps_a_stop_closure_inside_the_word(self):
        rate = 16000
        t = np.arange(rate) / rate
        first = ((t >= 0.20) & (t < 0.46)).astype(np.float64) * 0.25 * np.sin(2 * np.pi * 180 * t)
        second = ((t >= 0.56) & (t < 0.90)).astype(np.float64) * 0.4 * np.sin(2 * np.pi * 180 * t)
        refined = refine_word_bounds(first + second, rate, [{"word": "reactivation", "start": 0.22, "end": 0.92}])
        self.assertLess(refined[0]["start"], 0.24)
        self.assertGreater(refined[0]["end"], 0.85)

    def test_word_end_follows_energy_past_an_early_whisper_mark(self):
        rate = 16000
        t = np.arange(rate) / rate
        tone = ((t >= 0.20) & (t < 0.62)).astype(np.float64) * 0.35 * np.sin(2 * np.pi * 180 * t)
        refined = refine_word_bounds(tone, rate, [{"word": "most", "start": 0.22, "end": 0.40}])
        self.assertLess(refined[0]["start"], 0.22)
        self.assertGreater(refined[0]["end"], 0.62)
        self.assertLess(refined[0]["end"], 0.68)

    def test_word_end_follows_a_vowel_that_is_still_up_at_350ms(self):
        rate = 16000
        t = np.arange(int(rate * 1.4)) / rate
        tone = ((t >= 0.20) & (t < 0.95)).astype(np.float64) * 0.35 * np.sin(2 * np.pi * 180 * t)
        refined = refine_word_bounds(tone, rate, [{"word": "leverage", "start": 0.22, "end": 0.40}])
        self.assertGreater(refined[0]["end"], 0.95)
        self.assertLess(refined[0]["end"], 1.05)

    def test_fricative_tail_keeps_a_quiet_hiss(self):
        rate = 16000
        t = np.arange(rate) / rate
        vowel = ((t >= 0.20) & (t < 0.45)).astype(np.float64) * 0.4 * np.sin(2 * np.pi * 180 * t)
        hiss = ((t >= 0.45) & (t < 0.68)).astype(np.float64) * 0.02 * np.sin(2 * np.pi * 6000 * t)
        refined = refine_word_bounds(vowel + hiss, rate, [{"word": "once", "start": 0.22, "end": 0.45}])
        self.assertGreater(refined[0]["fricative_tail"], 0.15)
        self.assertGreater(refined[0]["end"], 0.68)

    def test_split_card_is_tall_and_sfx_are_recorded_variants(self):
        theme, colors, _, _ = load_theme("dark")
        layout = theme["layout"]
        height = layout["card_bottom"] - layout["card_top"]
        self.assertAlmostEqual(layout["card_top"] * 1920, 1408, delta=2)
        self.assertAlmostEqual(layout["card_bottom"], 1.0)
        self.assertGreaterEqual(height, 0.25)
        self.assertLessEqual(height, 0.29)
        self.assertAlmostEqual(layout["card_margin_x"] * 1080, 71, delta=1)
        self.assertLess(layout["caption_split_y"], layout["card_top"])
        self.assertGreater(layout["caption_split_y"], layout["stage_top"] + layout["stage_height"])
        stage_bottom = (layout["stage_top"] + layout["stage_height"]) * 1920
        self.assertAlmostEqual(stage_bottom, 1230, delta=2)
        self.assertAlmostEqual(layout["caption_baseline_px"], 1305, delta=2)
        card = card_state("split", "wide", 1080, 1920, layout, colors)
        self.assertEqual(card["top"], 1408)
        self.assertEqual(card["height"], 512)
        self.assertGreaterEqual(card["left"], 60)
        self.assertLessEqual(card["left"], 85)
        self.assertEqual(card["borderRadius"], "31px 31px 0 0")
        self.assertEqual(card_state("full", "wide", 1080, 1920, layout, colors)["borderRadius"], 0)
        self.assertEqual(card_state("punch_in", "wide", 1080, 1920, layout, colors)["borderRadius"], 0)
        words = words_for()
        timeline = plan_timeline(words, "/reels/silent.mp4", "words.json", music=False, keyword="VAULT")
        splits = [shot for shot in timeline["shots"] if shot["layout"] == "split"]
        self.assertTrue(splits)
        self.assertTrue(all(shot.get("crop") == "wide" for shot in splits))
        self.assertEqual(layout["wide_scale"], 1.0)
        self.assertAlmostEqual(layout["tight_scale"], 1.08)
        self.assertAlmostEqual(theme["audio"]["pause_gap_seconds"], 0.02)
        self.assertAlmostEqual(theme["audio"]["cut_crossfade_seconds"], 0.012)
        self.assertAlmostEqual(theme["layout"]["full_scale"], 1.13)
        self.assertIn("paper", SFX_KINDS)
        from kallaway_pack import pack_ready
        if pack_ready():
            self.assertGreaterEqual(len(sfx_variants("whoosh")), 2)
        self.assertTrue(all(event["kind"] == "paper" for event in stage_events("doc_fan", 1.0, 2.4, {"count": 3})))
        self.assertFalse(theme["audio"]["music_default"])

    def test_music_stays_off_and_drops_do_not_add_hits(self):
        from check_kallaway_style import check
        words = words_for()
        plan = {
            "schema": "kallaway-stage-plan/v1",
            "music_drops": [{"spoken": "old way", "until": "Start on", "hit": True}],
            "beats": [
                {"spoken": "This one", "layout": "split", "motif": "pill", "label": "Comment VAULT",
                 "header": {"text": "Comment VAULT", "emphasis": ["VAULT"]}},
                {"spoken": "old way", "layout": "full"},
                {"spoken": "Start on", "layout": "split", "motif": "counter", "value": 3},
                {"spoken": "Comment VAULT", "layout": "split", "motif": "doc_fan"},
            ],
        }
        timeline = plan_timeline(words, "/reels/silent.mp4", "words.json", music=False,
                                 music_path="/tmp/bed.wav", stage_plan=plan, keyword="VAULT")
        self.assertEqual(timeline["music"], [])
        self.assertFalse(any(item["kind"] == "bass" and item["at"] > 0.05 for item in timeline["sfx"]))
        timeline["audio_policy"]["user_opt_out"] = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "timeline.json"
            words_path = root / "words.json"
            timeline["words_path"] = "words.json"
            spec.write_text(json.dumps(timeline))
            words_path.write_text(json.dumps(words))
            report = check(spec, words_path)
            self.assertTrue(report["ok"], report)
            self.assertFalse(any("music" in error for error in report["errors"]))
            self.assertFalse(any("music" in warning for warning in report["warnings"]))

    def test_callout_draws_after_the_pan_and_rides_the_screenshot(self):
        from check_kallaway_style import check
        stage = {
            "motif": "phone_frame",
            "scroll": {"from": 0, "to": 0.42, "duration": 1.2},
            "callout": {"at": 0.9, "x": 0.8, "y": 0.3, "w": 0.16, "h": 0.48},
        }
        resolve_annotations(stage, 0.0, 3.0)
        self.assertLessEqual(stage["motion"]["scroll_end"], 0.9)
        self.assertGreaterEqual(stage["callout"]["at"], stage["motion"]["entrance_end"])
        self.assertGreaterEqual(stage["callout"]["at"], stage["motion"]["scroll_end"])
        self.assertGreaterEqual(stage["callout"]["at"], 0.9)
        marker = next(event for event in stage_events("phone_frame", 0.0, 3.0, stage) if event["kind"] == "marker")
        self.assertEqual(marker["at"], stage["callout"]["at"])
        left, top, width, height = screenshot_box(stage["callout"], 168, 0.42)
        self.assertAlmostEqual(top, 34.86, places=1)
        early = {
            "scroll": {"from": 0.35, "to": 1, "duration": 1.15},
            "callout": {"at": 1.1, "x": 0.1, "y": 0.81, "w": 0.8, "h": 0.15},
        }
        resolve_annotations(early, 1.0, 4.0)
        self.assertGreater(early["callout"]["at"], early["callout"]["cue_at"])
        self.assertGreaterEqual(early["callout"]["at"], early["motion"]["scroll_end"])
        colors = {"text": "#fff", "muted": "#aaa", "accent": "#54C947", "accent_strong": "#43AD38",
                  "surface": "#242424", "border": "#333", "contrast": "#111", "warning": "#ECC94B", "on_accent": "#111"}
        section, animations, _events = motif_markup(
            "phone_frame", stage, 0.0, 3.0, {"left": 0, "top": 0, "width": 400, "height": 700}, colors, "stage-0", "shot.png")
        pan = section.index('id="stage-0-pan"')
        ring = section.index('id="stage-0-ring"')
        self.assertLess(pan, ring)
        self.assertIn(f'tl.set("#stage-0-ring",{{opacity:1}},{stage["callout"]["at"]:.3f});', animations)
        bad = {
            "style": "kallaway", "theme": "ai-builder-school", "theme_mode": "dark",
            "output": {"width": 1080, "height": 1920, "fps": 30},
            "audio_policy": {"music_required": False}, "music": [],
            "headers": [{"start": 0, "end": 2, "text": "Comment VAULT"}],
            "cta": {"keyword": "VAULT"},
            "shots": [{
                "id": "shot-00", "start": 0, "end": 2.2, "layout": "split",
                "stage": {"motif": "phone_frame", "scroll": {"from": 0, "to": 0.4},
                          "motion": {"entrance_end": 0.4, "scroll_start": 0, "scroll_end": 1.1},
                          "callout": {"at": 0.2, "x": 0.5, "y": 0.4, "w": 0.2, "h": 0.2}},
            }, {
                "id": "shot-01", "start": 2.2, "end": 3.2, "layout": "full",
            }],
            "sfx": [{"kind": "whoosh", "at": 0}, {"kind": "marker", "at": 0.2}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "timeline.json"
            spec.write_text(json.dumps(bad))
            report = check(spec, None)
            self.assertFalse(report["ok"])
            self.assertTrue(any("still scrolling" in error or "frame entrance" in error for error in report["errors"]))

    def test_every_motif_emits_in_range_events(self):
        for motif in MOTIFS:
            events = stage_events(motif, 1.0, 3.2, {"count": 8, "items": ["A", "B", "C", "D"]})
            self.assertTrue(events, motif)
            for event in events:
                self.assertGreaterEqual(event["at"], 1.0)
                self.assertLess(event["at"], 3.2)
                self.assertIn(event["kind"], SFX_KINDS)

    def test_plan_follows_structure_rules(self):
        words = words_for()
        timeline = plan_timeline(words, "voice.mp4", "words.json", title="This one change",
                                 keyword="VAULT", emphasis={"secret": "marker", "change": "green"})
        shots = timeline["shots"]
        self.assertEqual(shots[0]["layout"], "split")
        self.assertEqual(shots[0]["start"], 0)
        self.assertAlmostEqual(shots[-1]["end"], words[-1]["end"])
        self.assertEqual(shots[-1]["stage"]["motif"], "doc_fan")
        fulls = [shot for shot in shots if shot["layout"] in {"full", "punch_in"}]
        self.assertTrue(any(2.2 <= shot["start"] <= 4.0 for shot in fulls))
        for left, right in zip(shots, shots[1:]):
            self.assertAlmostEqual(left["end"], right["start"])
            self.assertLessEqual(right["end"] - right["start"], 5.5)
        phrases = caption_phrases(words, timeline["captions"]["word_styles"])
        covered = [index for phrase in phrases for index in range(*phrase["word_range"])]
        self.assertEqual(covered, list(range(len(words))))
        self.assertTrue(all(phrase["word_range"][1] - phrase["word_range"][0] == 1 for phrase in phrases))
        self.assertEqual(timeline["captions"]["max_words"], 1)
        self.assertEqual(_caption_text({"word": "I"}), "I")
        self.assertEqual(_caption_text({"word": "Never,"}), "never")
        self.assertFalse(any(item.get("combo") == "15" for item in timeline["sfx"]))
        self.assertFalse(any(item.get("label") == "Standard Cut" for item in timeline["sfx"]))
        for shot in timeline["shots"]:
            if shot["layout"] not in {"full", "punch_in"}:
                continue
            leaked = [
                item for item in timeline["sfx"]
                if not item.get("mute") and item.get("combo") in {"8", "15"}
                and abs(float(item["at"]) - float(shot["start"])) < 0.08
            ]
            self.assertFalse(leaked, leaked)
        audible = [item for item in timeline["sfx"] if not item.get("mute")]
        per_minute = len(audible) / (timeline["shots"][-1]["end"] / 60.0)
        self.assertGreaterEqual(per_minute, 8.0, audible)
        self.assertLessEqual(per_minute, 20.0, audible)
        heard_whoosh = [
            (item.get("file") or "").split("/")[-1]
            for item in sorted(audible, key=lambda item: float(item.get("sound_at", item["at"])))
            if item.get("kind") == "whoosh"
        ]
        self.assertTrue(all(left != right for left, right in zip(heard_whoosh, heard_whoosh[1:])))
        self.assertIn("comment", timeline["headers"][-1]["text"].lower())
        self.assertTrue(timeline["sfx"])
        self.assertNotIn("\u2014", json.dumps(timeline))

    def test_style_checker_rejects_a_crossfade_and_a_long_caption(self):
        from check_kallaway_style import check
        words = words_for(8, 0.4)
        timeline = plan_timeline(words, "voice.mp4", "words.json", music=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "timeline.json"
            words_path = root / "words.json"
            words_path.write_text(json.dumps(words))
            timeline["words_path"] = "words.json"
            spec.write_text(json.dumps(timeline))
            # The checker measures SFX against stage events. A planned timeline should pass
            # the structural gates even before HTML exists.
            report = check(spec, words_path)
            self.assertTrue(report["ok"], report)
            timeline["shots"][1]["transition"] = "crossfade"
            timeline["captions"]["phrases"][0]["word_range"] = [0, 6]
            spec.write_text(json.dumps(timeline))
            failed = check(spec, words_path)
            self.assertFalse(failed["ok"])
            self.assertTrue(any("crossfade" in error for error in failed["errors"]))

    def test_build_uses_brand_fonts_and_colors(self):
        from edit import build
        words = words_for(6, 0.45)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "talk.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=0x224466:s=320x568:d=6:r=30",
                "-f", "lavfi", "-i", "sine=frequency=220:duration=6",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
                check=True)
            timeline = plan_timeline(words, str(source), "words.json", music=False, keyword="VAULT",
                                     title="This one change", emphasis={"change": "green"})
            # Keep the synthetic clip's full duration so the builder does not reject the segment.
            timeline["source"]["segments"] = [{"start": 0, "end": words[-1]["end"]}]
            (root / "words.json").write_text(json.dumps(words))
            spec = root / "timeline.json"
            spec.write_text(json.dumps(timeline))
            from kallaway_pack import pack_ready
            if not pack_ready():
                self.skipTest("SFX_PACK_DIR has no Viral Reels pack")
            write_sfx_library(root / "sfx")
            project = root / "composition"
            receipt = build(spec, project)
            html = (project / "index.html").read_text()
            self.assertEqual(receipt["style"], "kallaway")
            for token in ("Permanent Marker", "IBM Plex Mono", "Inter", "#1A1A1A", "#54C947", "#F2F2F0"):
                self.assertIn(token, html)
            self.assertNotIn("#E60000", html)
            self.assertNotIn("#FF2A2A", html)
            shutil.rmtree(project)

    def test_fallback_rotates_by_video_without_back_to_back_repeats(self):
        words = words_for()
        sequences = []
        for name in ("one.mp4", "two.mp4", "three.mp4", "four.mp4", "five.mp4", "six.mp4"):
            timeline = plan_timeline(words, f"/reels/{name}", "words.json", music=False)
            motifs = [slot["motif"] for slot in timeline["stage_slots"]]
            self.assertEqual(motifs[-1], "doc_fan")
            body = motifs[:-1]
            self.assertGreaterEqual(len(body), 2)
            self.assertTrue(all(left != right for left, right in zip(body, body[1:])), body)
            self.assertEqual(len(body), len(set(body)), body)
            self.assertTrue(all(slot["authored"] is False for slot in timeline["stage_slots"] if slot["role"] != "cta"))
            sequences.append(tuple(body))
        self.assertGreater(len(set(sequences)), 1)
        again = plan_timeline(words, "/reels/one.mp4", "words.json", music=False)
        self.assertEqual(sequences[0], tuple(slot["motif"] for slot in again["stage_slots"][:-1]))
        seed = video_seed("/reels/one.mp4")
        previous = None
        walked = []
        for index in range(len(LIBRARY)):
            motif = _rotate(seed, index, previous)
            self.assertNotEqual(motif, previous)
            walked.append(motif)
            previous = motif
        self.assertEqual(set(walked), set(LIBRARY))

    def test_stage_plan_can_target_a_spoken_slot(self):
        words = words_for()
        base = plan_timeline(words, "/reels/alpha.mp4", "words.json", music=False)
        slots = [slot for slot in base["stage_slots"] if slot["role"] != "cta" and slot["spoken"]]
        target = slots[0]
        other = slots[1]
        plan = {"schema": "kallaway-stage-plan/v1", "stages": [
            {"spoken": target["spoken"], "motif": "mind_map", "label": "Offer", "why": "author note"},
            {"word_range": other["word_range"], "motif": "phone_frame"},
        ]}
        authored = plan_timeline(words, "/reels/alpha.mp4", "words.json", music=False, stage_plan=plan)
        by_spoken = {slot["spoken"]: slot for slot in authored["stage_slots"]}
        self.assertEqual(by_spoken[target["spoken"]]["motif"], "mind_map")
        self.assertTrue(by_spoken[target["spoken"]]["authored"])
        self.assertEqual(by_spoken[other["spoken"]]["motif"], "phone_frame")
        self.assertNotIn("author note", json.dumps(authored["shots"]))
        body = [slot["motif"] for slot in authored["stage_slots"][:-1]]
        self.assertTrue(all(left != right for left, right in zip(body, body[1:])), body)
        ordered = plan_timeline(words, "/reels/alpha.mp4", "words.json", music=False,
                                stage_plan=["typing_ui", {"motif": "counter", "value": 12, "label": "count"}])
        self.assertEqual(ordered["stage_slots"][0]["motif"], "typing_ui")
        self.assertEqual(ordered["stage_slots"][1]["motif"], "counter")
        counter = next(shot["stage"] for shot in ordered["shots"] if shot["id"] == ordered["stage_slots"][1]["id"])
        self.assertEqual(counter["value"], 12)
        self.assertEqual(counter["label"], "count")
        with self.assertRaises(ValueError):
            plan_timeline(words, "/reels/alpha.mp4", "words.json", music=False, stage_plan=["not_a_motif"])
        with self.assertRaises(ValueError):
            plan_timeline(words, "/reels/alpha.mp4", "words.json", music=False, stage_plan=["doc_fan"])
        example = json.loads((Path(__file__).resolve().parent / "examples" / "vault-stage-plan.json").read_text())
        self.assertEqual(example["schema"], "kallaway-stage-plan/v1")
        self.assertTrue(all(stage["motif"] in LIBRARY for stage in example["stages"]))

    def test_authored_beats_keep_a_midroll_cta_and_drop_the_bed(self):
        from check_kallaway_style import check
        tokens = ("Almost every local business has a list like this "
                  "Here is how you get paid to wake it up "
                  "That is not a no A good site means real customers "
                  "comment PAID and I will send the guide").split()
        words = []
        cursor = 0.12
        for token in tokens:
            words.append({"word": token, "start": round(cursor, 3), "end": round(cursor + 0.28, 3)})
            cursor += 0.42
        words[-1]["end"] = round(cursor, 3)
        plan = {
            "schema": "kallaway-stage-plan/v1",
            "bed_bpm": 104,
            "punch_scale": 1.2,
            "captions": {"keep_case": ["PAID"]},
            "emphasis": {"no": "green", "not": "green"},
            "music_drops": [{"spoken": "not a no", "until": "good site", "hit": True}],
            "chips": [{"after": "comment PAID", "text": "Comment PAID", "place": "stage-corner"}],
            "beats": [
                {"spoken": "Almost every", "layout": "split", "motif": "phone_frame",
                 "header": {"lines": ["We already have a website?", "Pitch this instead"],
                            "green_lines": [1], "size": 64},
                 "callout": {"spoken": "list like this", "x": 0.6, "y": 0.3, "w": 0.2, "h": 0.16},
                 "overlays": [{"spoken": "paid", "motif": "counter", "value": 5, "suffix": "%"}]},
                {"spoken": "wake it up", "layout": "punch_in"},
                {"spoken": "not a no", "layout": "full"},
                {"spoken": "good site", "layout": "split", "motif": "quote_card", "text": "We already have one.",
                 "strike": {"spoken": "real customers"}},
                {"spoken": "comment PAID", "layout": "split", "motif": "pill", "label": "Comment PAID",
                 "header": {"text": "Comment PAID", "emphasis": ["PAID"], "sub": "AI Business Idea Vault"},
                 "disclaimer": "(not legal advice)"},
            ],
        }
        timeline = plan_timeline(words, "/reels/authored.mp4", "words.json", music_path="/tmp/bed.wav",
                                 keyword="PAID", stage_plan=plan)
        self.assertEqual(timeline["structure"], "authored")
        self.assertNotEqual(timeline["shots"][-1]["stage"]["motif"], "doc_fan")
        self.assertEqual(timeline["shots"][-1]["stage"]["motif"], "pill")
        motifs = [shot["stage"]["motif"] for shot in timeline["shots"] if shot["layout"] == "split"]
        self.assertTrue(all(left != right for left, right in zip(motifs, motifs[1:])), motifs)
        self.assertLessEqual(min(shot["start"] for shot in timeline["shots"] if shot["layout"] in {"full", "punch_in"}), 8)
        self.assertEqual(timeline["music"][0]["envelope"][-1]["v"], 1)
        self.assertGreater(timeline["chips"][0]["start"], 1)
        self.assertTrue(any("not legal advice" in notice["text"] for notice in timeline["notices"]))
        self.assertEqual(timeline["captions"]["word_styles"]["no"], "green")
        held = stage_events("numbered_list", 1.0, 2.4, {"hold": True, "active": 2, "items": ["A", "B", "C"]})
        self.assertEqual(len(held), 1)
        self.assertEqual(_caption_text({"word": "paid"}, keep_case=["PAID"]), "PAID")
        self.assertEqual(_caption_text({"word": "five", "display": "5%"}), "5%")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "timeline.json"
            words_path = root / "words.json"
            timeline["words_path"] = "words.json"
            spec.write_text(json.dumps(timeline))
            words_path.write_text(json.dumps(words))
            report = check(spec, words_path)
            self.assertTrue(report["ok"], report)

    def test_house_timeline_still_rejects_music(self):
        from edit import build
        words = [{"word": "hello", "start": 0.1, "end": 0.4}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "talk.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=0x224466:s=320x568:d=1:r=30",
                "-f", "lavfi", "-i", "sine=frequency=220:duration=1",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
                check=True)
            (root / "words.json").write_text(json.dumps(words))
            spec = root / "timeline.json"
            spec.write_text(json.dumps({
                "style": {"zones": {"caption": {"y": 70}}},
                "audio_policy": {"music_required": True},
                "source": {"path": str(source)},
                "words_path": "words.json",
                "shots": [{"start": 0, "end": 0.5, "layout": "presenter"}],
            }))
            with self.assertRaises(ValueError) as caught:
                build(spec, root / "out")
            self.assertIn("background music", str(caught.exception))


    def test_sfx_levels_follow_voice_loudness(self):
        unders = load_theme()[0]["sfx_under_db"]
        self.assertEqual(set(unders), set(UNDER_DB))
        for kind, under in UNDER_DB.items():
            self.assertAlmostEqual(float(unders[kind]), under, places=1)

    def test_sfx_stem_hits_every_cue_level(self):
        # Pack files are several seconds long. Space the cues past each file so a
        # tail is not scored inside the next 400 ms window.
        rate = 48000
        t = np.arange(int(rate * 12.0)) / rate
        voice = 0.2 * np.sin(2 * np.pi * 180 * t)
        cues = [
            {"kind": "bass", "at": 0.20, "under_db": 6},
            {"kind": "pop", "at": 5.20, "under_db": 16},
            {"kind": "whoosh", "at": 6.40, "under_db": 10},
            {"kind": "ding", "at": 8.60, "under_db": 12},
            {"kind": "marker", "at": 10.20, "under_db": 14},
        ]
        rows = measure_sfx_stem(voice, rate, cues)
        self.assertEqual(len(rows), len(cues))
        for row in rows:
            self.assertFalse(row["clustered"], row)
            self.assertTrue(row["ok"], row)
            self.assertLessEqual(abs(row["error_db"]), 2.0, row)
            self.assertLessEqual(row["gain_db"], 12.0, row)

    def test_leading_silence_does_not_crush_the_voice(self):
        from kallaway_pack import pack_ready
        if not pack_ready():
            return
        rate = 48000
        t = np.arange(int(rate * 3.0)) / rate
        voice = 0.2 * np.sin(2 * np.pi * 180 * t)
        cues = [
            {"kind": "bass", "at": 0.20, "file": "07 Booms/Boom 14.mp3", "under_db": 6},
            {"kind": "pop", "at": 1.60, "file": "35 Money & Cash/Cash Register Ka Ching 02.mp3", "under_db": 10},
        ]
        mixed, report = mix_cues(voice, rate, cues)
        self.assertEqual(len(report), 2)
        isolated = _k_weight(mixed - voice, rate)
        for row in report:
            self.assertGreater(row["cue_lufs"], -40.0, row)
            self.assertLess(row["gain_db"], 6.0, row)
            heard = _momentary_lufs(isolated, row["at"])
            self.assertGreater(heard, -50.0, row)
            self.assertLess(abs(heard - row["target_lufs"]), 3.0, row)
        voice_rms = float(np.sqrt(np.mean(voice * voice)))
        mix_rms = float(np.sqrt(np.mean(mixed * mixed)))
        self.assertLess(abs(20.0 * np.log10(mix_rms / voice_rms)), 6.0)
        self.assertLess(float(np.max(np.abs(mixed))), 2.0)

    def test_stereo_voice_is_averaged_before_the_sfx_bake(self):
        rate = 48000
        tone = (0.8 * np.sin(2 * np.pi * 220 * np.arange(rate // 2) / rate)).astype(np.float32)
        stereo = np.column_stack([tone, tone])
        pcm = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(rate)
                handle.writeframes(pcm)
            voice = _load_mix_voice(path, rate)
        self.assertLess(float(np.max(np.abs(voice))), 0.85)
        self.assertGreater(float(np.max(np.abs(voice))), 0.7)

    def test_progress_bar_is_off_unless_the_beat_asks(self):
        colors = {"text": "#fff", "muted": "#aaa", "accent": "#54C947", "accent_strong": "#43AD38",
                  "surface": "#242424", "border": "#333", "contrast": "#111", "warning": "#ECC94B", "on_accent": "#111"}
        box = {"left": 0, "top": 0, "width": 400, "height": 700}
        phone, anim, _events = motif_markup(
            "phone_frame", {"motif": "phone_frame"}, 0.0, 2.0, box, colors, "stage-0", "shot.png")
        self.assertNotIn("phone-bar", phone)
        self.assertNotIn("-prog", anim)
        opted, _anim, _events = motif_markup(
            "phone_frame", {"motif": "phone_frame", "progress": True}, 0.0, 2.0, box, colors, "stage-1", "shot.png")
        self.assertIn("phone-bar", opted)
        card, anim, _events = motif_markup(
            "broll_card", {"motif": "broll_card"}, 0.0, 2.0, box, colors, "stage-2", "clip.mp4")
        self.assertNotIn("broll-progress", card)
        self.assertNotIn("-bar", anim)

    def test_target_text_centers_the_card_inside_the_phone(self):
        from PIL import Image, ImageDraw, ImageFont
        from kallaway_targets import locate_target, match_phrase, settle_pan, surface_box
        from check_kallaway_style import check
        font_path = Path(__file__).resolve().parent / "fonts" / "Inter-Black.ttf"
        font = ImageFont.truetype(str(font_path), 52)
        with tempfile.TemporaryDirectory() as tmp:
            image = Image.new("RGB", (800, 1400), (42, 47, 54))
            draw = ImageDraw.Draw(image)
            draw.rectangle((50, 480, 750, 860), fill=(255, 248, 241))
            draw.text((90, 560), "Join our email list", fill=(20, 20, 20), font=font)
            path = Path(tmp) / "page.png"
            image.save(path)
            tight = locate_target(path, "Join our email list", "text")
            card = surface_box(path, {"x": 0.15, "y": 0.42, "w": 0.4, "h": 0.04})
            self.assertLess(card["y"], tight["y"])
            self.assertGreater(card["y"] + card["h"], tight["y"] + tight["h"])
            self.assertLess(card["h"], 0.45)
            stage = {
                "motif": "phone_frame",
                "media": str(path),
                "scroll": {"from": 0},
                "callout": {"at": 1.2, "target_text": "Join our email list", "group": "surface"},
            }
            resolve_annotations(stage, 0.0, 3.0, (400, 280))
            callout = stage["callout"]
            self.assertEqual(callout["space"], "image")
            self.assertGreaterEqual(callout["at"], stage["motion"]["scroll_end"])
            frame = stage["frame"]
            view_top = frame["viewport_top"]
            view_h = frame["viewport_height"]
            center = (callout["y"] + callout["h"] / 2 - view_top) / view_h
            self.assertAlmostEqual(center, 0.5, delta=0.08)
            self.assertGreaterEqual(callout["y"], view_top - 0.01)
            self.assertLessEqual(callout["y"] + callout["h"], view_top + view_h + 0.01)
            scroll, _top = settle_pan(callout, view_h)
            self.assertAlmostEqual(scroll, stage["scroll"]["to"], places=3)
            with self.assertRaises(ValueError):
                match_phrase(
                    [{"text": "Join", "x": 0.1, "y": 0.2, "w": 0.1, "h": 0.02},
                     {"text": "list", "x": 0.2, "y": 0.2, "w": 0.1, "h": 0.02},
                     {"text": "Join", "x": 0.1, "y": 0.6, "w": 0.1, "h": 0.02},
                     {"text": "list", "x": 0.2, "y": 0.6, "w": 0.1, "h": 0.02}],
                    "Join list")
            outside = {
                "style": "kallaway", "theme": "ai-builder-school", "theme_mode": "dark",
                "output": {"width": 1080, "height": 1920, "fps": 30},
                "audio_policy": {"music_required": False}, "music": [],
                "headers": [{"start": 0, "end": 2, "text": "Comment VAULT"}],
                "cta": {"keyword": "VAULT"},
                "shots": [{
                    "id": "shot-00", "start": 0, "end": 2.2, "layout": "split",
                    "stage": {
                        "motif": "phone_frame",
                        "scroll": {"from": 0, "to": 0},
                        "motion": {"entrance_end": 0.4, "scroll_start": 0, "scroll_end": 0.4},
                        "frame": {"img_h": 200, "viewport_height": 0.5, "viewport_top": 0.0, "scroll_to": 0},
                        "callout": {"at": 1.0, "space": "image", "x": 0.1, "y": 0.8, "w": 0.4, "h": 0.1},
                    },
                }, {
                    "id": "shot-01", "start": 2.2, "end": 3.2, "layout": "full",
                }],
                "sfx": [{"kind": "whoosh", "at": 0}, {"kind": "marker", "at": 1.0}],
            }
            spec = Path(tmp) / "timeline.json"
            spec.write_text(json.dumps(outside))
            report = check(spec, None)
            self.assertFalse(report["ok"])
            self.assertTrue(any("outside the phone" in error for error in report["errors"]))

    def test_screen_recording_is_its_own_timed_video(self):
        colors = {"text": "#fff", "muted": "#aaa", "accent": "#54C947", "accent_strong": "#43AD38",
                  "surface": "#242424", "border": "#333", "contrast": "#111", "warning": "#ECC94B", "on_accent": "#111"}
        box = {"left": 0, "top": 0, "width": 400, "height": 700}
        stage = {"motif": "phone_frame", "media_start": 1.25, "playback_rate": 1.4,
                 "chip": {"text": "Source: the article", "place": "bottom", "tone": "green"}}
        section, animations, _events = motif_markup(
            "phone_frame", stage, 1.2, 3.0, box, colors, "stage-9", "clip.mp4")
        self.assertIn("<video", section)
        self.assertIn('data-media-start="1.250"', section)
        self.assertIn('data-playback-rate="1.400"', section)
        self.assertNotIn('class="stage clip"', section)
        self.assertIn("stage-chip bottom", section)
        script = "".join(animations)
        self.assertIn('tl.set("#stage-9",{autoAlpha:1},1.200);', script)
        self.assertIn('tl.set("#stage-9",{autoAlpha:0},3.000);', script)

    def test_phone_screen_fills_the_panel_and_pushes_before_the_circle(self):
        from kallaway_motifs import hero_phone_box
        colors = {"text": "#fff", "muted": "#aaa", "accent": "#54C947", "accent_strong": "#43AD38",
                  "surface": "#242424", "border": "#333", "contrast": "#111", "warning": "#ECC94B",
                  "on_accent": "#111", "negative": "#E0533D"}
        box = {"left": 54, "top": 298, "width": 972, "height": 672}
        stage = {
            "motif": "phone_frame",
            "uncropped": True,
            "callout": {"at": 1.5, "x": 0.5, "y": 0.35, "w": 0.13, "h": 0.04},
        }
        section, animations, _events = motif_markup(
            "phone_frame", stage, 0.0, 3.0, box, colors, "stage-4", "clip.mp4")
        geo = hero_phone_box(box["width"], box["height"])
        screen_w = geo["screen"][0]
        self.assertGreaterEqual(screen_w / box["width"], 0.80)
        self.assertLessEqual(screen_w / box["width"], 0.90)
        self.assertGreater(geo["height"], box["height"])
        self.assertLess(geo["top"], 0)
        self.assertIn(f'width:{geo["width"]}px', section)
        self.assertIn("object-fit:cover", section)
        self.assertNotIn("object-fit:contain", section)
        self.assertGreaterEqual(stage["callout"]["at"], stage["motion"]["push_end"])
        script = "".join(animations)
        self.assertIn("scale:1.06", script)
        self.assertLess(stage["motion"]["push_end"], stage["callout"]["at"] + 0.001)

    def test_state_swap_exit_is_hard_killed_on_a_clip_boundary(self):
        from edit import boundary_hard_kills
        colors = {"text": "#fff", "muted": "#aaa", "accent": "#54C947", "accent_strong": "#43AD38",
                  "surface": "#242424", "border": "#333", "contrast": "#111", "warning": "#ECC94B", "on_accent": "#111"}
        box = {"left": 0, "top": 0, "width": 400, "height": 700}
        stage = {"motif": "state_swap", "items": ["One payment ends", "Monthly plan stays"]}
        section, animations, events = motif_markup(
            "state_swap", stage, 2.0, 5.0, box, colors, "stage-13")
        swipe = next(event["at"] for event in events if event["kind"] == "error")
        boundary = round(swipe + 0.22, 3)
        markup = section + f'<div class="caption clip" data-start="{boundary:.3f}" data-duration="0.40"></div>'
        kills = boundary_hard_kills("".join(animations), markup)
        self.assertTrue(any("#stage-13-bad" in kill and "opacity:0" in kill for kill in kills), kills)
        script = "".join(animations)
        self.assertIn('id="stage-13-good"', section)
        self.assertNotIn('tl.set("#stage-13-good",{scale:0,opacity:0},2.000);', script)
        self.assertIn('id="stage-13-line"', section)
        self.assertIn("swap side", section)

    def test_reach_reel_can_omit_the_comment_ask(self):
        from check_kallaway_style import check
        tokens = "Charging two thousand is a most expensive mistake and then you stop paying".split()
        words = []
        cursor = 0.08
        for token in tokens:
            words.append({"word": token, "start": round(cursor, 3), "end": round(cursor + 0.24, 3)})
            cursor += 0.46
        plan = {
            "schema": "kallaway-stage-plan/v1",
            "omit_cta": True,
            "emphasis": {"thousand": "green", "mistake": "marker", "paying": "amber"},
            "beats": [
                {"spoken": "Charging", "layout": "split", "motif": "offer_pair",
                 "items": ["$2,000 UPFRONT", "FREE BUILD"],
                 "header": {"lines": ["Never sell a website for", "$2,000"], "green_lines": [1]}},
                {"spoken": "is a most", "layout": "full"},
                {"spoken": "stop paying", "layout": "split", "motif": "state_swap",
                 "items": ["One payment ends", "Monthly plan stays"]},
            ],
        }
        timeline = plan_timeline(words, "/reels/reach.mp4", "words.json", music=False, stage_plan=plan)
        self.assertFalse(timeline["cta"]["required"])
        self.assertEqual(timeline["cta"]["keyword"], "")
        punches = [shot for shot in timeline["shots"] if shot["layout"] == "punch_in"]
        self.assertTrue(punches)
        self.assertGreater(punches[0]["scale"], timeline["shots"][0].get("scale", 1))
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "timeline.json"
            spec.write_text(json.dumps(timeline))
            report = check(spec, None)
            self.assertTrue(report["ok"], report)

    def test_join_tail_stays_near_the_noise_floor(self):
        from kallaway_audio import measure_joins
        rate = 16000
        t = np.arange(int(rate * 1.4)) / rate
        tone = (((t >= 0.10) & (t < 0.40)) | ((t >= 0.90) & (t < 1.20))).astype(np.float64)
        samples = tone * 0.3 * np.sin(2 * np.pi * 200 * t)
        words = [
            {"word": "costs", "start": 0.12, "end": 0.38},
            {"word": "stop", "start": 0.92, "end": 1.18},
        ]
        refined = refine_word_bounds(samples, rate, words)
        ranges = keep_ranges(refined, 1.4, gap=0.02, handle=0)
        self.assertGreater(refined[0]["end"], 0.40)
        joins = measure_joins(samples, rate, ranges, refined)
        self.assertTrue(joins)
        self.assertTrue(all(item["ok"] for item in joins), joins)
        self.assertEqual(joins[0]["consonant"], "s")

    def test_pop_crop_clears_crown_and_raised_hand_without_covering_the_hero(self):
        from kallaway_matte import cover_fit, frame_popout, parse_position, pop_limits, source_y_on_card
        theme, _, _, _ = load_theme("dark")
        layout = theme["layout"]
        card_w = (1 - 2 * layout["card_margin_x"]) * 1080
        card_h = (layout["card_bottom"] - layout["card_top"]) * 1920
        limits = pop_limits(layout, 1920)
        base = {
            "width": 1080, "height": 1920,
            "head_top": 331.0, "head_height": 420.0,
            "head_low": 400.0, "head_high": 280.0,
            "pop_fraction": 0.32, "samples": 4, "hands": [],
        }

        def place(head):
            timeline = {
                "output": {"width": 1080, "height": 1920},
                "source": {"object_position": "50% 50%"},
                "shots": [
                    {"layout": "split", "crop": "wide"},
                    {"layout": "full"},
                    {"layout": "punch_in"},
                ],
            }
            frame_popout(timeline, head, theme)
            _x, pos_y = parse_position(timeline["shots"][0]["object_position"])
            crown = source_y_on_card(head["head_top"], 1080, 1920, card_w, card_h, pos_y)
            self.assertNotIn("object_position", timeline["shots"][1])
            self.assertNotIn("object_position", timeline["shots"][2])
            self.assertNotIn("caption_y", timeline["shots"][0])
            self.assertEqual(timeline["source"]["object_position"], timeline["shots"][0]["object_position"])
            return crown, pos_y, timeline

        crown, pos0, _timeline = place(base)
        self.assertLess(crown, -40)
        self.assertGreaterEqual(limits["card_top"] + crown, limits["baseline"] - 2)
        self.assertGreaterEqual(limits["card_top"] + crown, limits["stage_bottom"] - 1)

        raised = dict(base, hands=[{"at": 1.0, "top": 160.0}])
        crown, pos_y, timeline = place(raised)
        hand = source_y_on_card(160.0, 1080, 1920, card_w, card_h, pos_y)
        self.assertLess(hand, -8)
        self.assertGreaterEqual(limits["card_top"] + hand, limits["stage_bottom"] - 1)
        self.assertGreaterEqual(limits["card_top"] + crown, limits["stage_bottom"] - 1)
        self.assertLess(crown, 0)
        self.assertLessEqual(timeline["source"]["popout"]["hand_above_px"], limits["hero_clear"] + 1)

        # A hand that the crown crop leaves just inside the card breaks out.
        fit = cover_fit(1080, 1920, card_w, card_h)
        offset = pos0 * (card_h - 1920 * fit)
        edge_top = (20 - offset) / fit
        edge = dict(base, hands=[{"at": 1.2, "top": edge_top}])
        crown, pos_y, _timeline = place(edge)
        hand = source_y_on_card(edge_top, 1080, 1920, card_w, card_h, pos_y)
        self.assertLessEqual(hand, -12)
        self.assertGreaterEqual(limits["card_top"] + crown, limits["stage_bottom"] - 1)
        self.assertGreaterEqual(limits["card_top"] + hand, limits["stage_bottom"] - 1)

    def test_pop_crop_puts_the_crown_above_the_card(self):
        from kallaway_matte import cover_fit, solve_position_y, source_y_on_card
        theme, _, _, _ = load_theme("dark")
        layout = theme["layout"]
        card_w = (1 - 2 * layout["card_margin_x"]) * 1080
        card_h = (layout["card_bottom"] - layout["card_top"]) * 1920
        head_top, head_height = 420.0, 280.0
        pos_y = solve_position_y(head_top, head_height, 0.15, 1080, 1920, card_w, card_h, scale=1)
        local = source_y_on_card(head_top, 1080, 1920, card_w, card_h, pos_y, scale=1)
        expected = -0.15 * head_height * cover_fit(1080, 1920, card_w, card_h)
        self.assertAlmostEqual(local, expected, delta=1.5)
        self.assertLess(local, -0.10 * head_height * cover_fit(1080, 1920, card_w, card_h))
        self.assertGreater(local, -0.20 * head_height * cover_fit(1080, 1920, card_w, card_h))

    def test_matte_hole_check_rejects_an_enclosed_gap(self):
        from kallaway_matte import large_holes
        solid = np.zeros((120, 80), dtype=np.uint8)
        solid[10:110, 15:65] = 255
        self.assertEqual(large_holes(solid), [])
        punched = solid.copy()
        punched[40:70, 30:55] = 0
        holes = large_holes(punched, fraction=0.002)
        self.assertTrue(holes)
        self.assertGreater(holes[0]["area"], holes[0]["limit"])

    def test_popout_layer_sits_above_the_card_and_full_screen_hides_it(self):
        from edit import build
        from check_kallaway_style import check
        words = words_for(6, 0.45)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "talk.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=0x224466:s=320x568:d=6:r=30",
                "-f", "lavfi", "-i", "sine=frequency=220:duration=6",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
                check=True)
            mask = root / "mask.mp4"
            frame = np.full((90, 64), 40, dtype=np.uint8)
            yy, xx = np.ogrid[:90, :64]
            frame[((yy - 40) / 28) ** 2 + ((xx - 32) / 16) ** 2 <= 1] = 220
            raw = root / "mask.raw"
            raw.write_bytes(frame.tobytes() * 12)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "gray", "-s", "64x90", "-r", "30", "-i", str(raw),
                "-frames:v", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mask)],
                check=True)
            timeline = plan_timeline(words, str(source), "words.json", music=False, keyword="VAULT",
                                     title="This one change")
            timeline["source"]["segments"] = [{"start": 0, "end": words[-1]["end"]}]
            timeline["source"]["matte"] = str(mask)
            timeline["source"]["matte_mask"] = str(mask)
            (root / "words.json").write_text(json.dumps(words))
            spec = root / "timeline.json"
            spec.write_text(json.dumps(timeline))
            from kallaway_pack import pack_ready
            if not pack_ready():
                self.skipTest("SFX_PACK_DIR has no Viral Reels pack")
            write_sfx_library(root / "sfx")
            project = root / "composition"
            build(spec, project)
            html = (project / "index.html").read_text()
            self.assertIn('id="speaker-pop"', html)
            self.assertIn("31px 31px 0 0", html)
            self.assertNotIn("0 0px", html)
            self.assertIn('id="pop-camera"', html)
            self.assertIn("z-index:6", html)
            self.assertIn('"autoAlpha": 0', html)
            self.assertNotIn('"visibility": "hidden"', html)
            self.assertIn("z-index:2", html)
            self.assertIn("z-index:8", html)
            pop_sets = re.findall(r'tl\.set\("#speaker-pop",(\{.*?\}),([0-9.]+)\);', html)
            card_sets = re.findall(r'tl\.set\("#speaker-card",(\{.*?\}),([0-9.]+)\);', html)
            self.assertTrue(pop_sets and card_sets)
            card_at = {}
            for payload, at in card_sets:
                card_at.setdefault(at, []).append(json.loads(payload))
            for payload, at in pop_sets:
                state = json.loads(payload)
                self.assertIn(at, card_at)
                card = card_at[at][-1]
                full_canvas = card["left"] == 0 and card["top"] == 0 and card["borderRadius"] == 0
                if full_canvas:
                    self.assertEqual(state.get("autoAlpha"), 0)
                    self.assertIn("inset(100%", state.get("clipPath", ""))
                else:
                    self.assertEqual(state.get("autoAlpha"), 1)
                    self.assertNotIn("inset(100%", state.get("clipPath", ""))
            report = check(project / "timeline.json", project / "mapped-words.json", project)
            self.assertTrue(report["ok"], report)
            broken = frame.copy()
            broken[35:55, 24:40] = 0
            raw.write_bytes(broken.tobytes() * 12)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "gray", "-s", "64x90", "-r", "30", "-i", str(raw),
                "-frames:v", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mask)],
                check=True)
            failed = check(project / "timeline.json", project / "mapped-words.json", project)
            self.assertTrue(any(error.startswith("matte:") for error in failed["errors"]), failed)

    def test_guided_feather_smooths_a_blocky_crown_and_casts_a_shadow(self):
        from kallaway_matte import refine_frame
        height = width = 180
        yy, xx = np.ogrid[:height, :width]
        center, radius = 90, 58
        disk = (yy - center) ** 2 + (xx - center) ** 2 <= radius ** 2
        rgb = np.zeros((height, width, 3), np.uint8)
        rgb[:] = (18, 18, 20)
        rgb[disk] = (232, 186, 170)
        block = 6
        small = disk[::block, ::block]
        coarse = np.repeat(np.repeat(small, block, axis=0), block, axis=1)[:height, :width].astype(np.float32)
        person, _straight, out_a, _field = refine_frame(rgb, coarse)

        def steps(alpha, level):
            tops = []
            for column in range(40, 140):
                hit = np.where(alpha[:, column] > level)[0]
                if hit.size:
                    tops.append(hit[0])
            return np.abs(np.diff(np.asarray(tops, dtype=np.float64)))

        coarse_steps = steps(coarse, 0.5)
        smooth_steps = steps(person, 0.5)
        self.assertGreater(coarse_steps.max(), 2)
        self.assertLessEqual(smooth_steps.max(), 2)
        self.assertGreater(person[center, center], 0.98)
        # The 0.2 to 0.8 band is a few pixels, not a hard stair and not a wide halo.
        widths = []
        for column in range(50, 130, 3):
            column_alpha = person[:, column]
            high = np.where(column_alpha > 0.8)[0]
            low = np.where(column_alpha < 0.2)[0]
            if high.size and low.size:
                below = low[low < high[0]]
                if below.size:
                    widths.append(high[0] - below[-1])
        self.assertTrue(widths)
        self.assertGreaterEqual(np.median(widths), 2)
        self.assertLessEqual(np.median(widths), 5)
        below = out_a[center + radius + 3:center + radius + 16, center - 8:center + 8].mean()
        above = out_a[center - radius - 16:center - radius - 3, center - 8:center + 8].mean()
        self.assertGreater(below, above + 0.04)
        self.assertLess(below, 0.75)


    def test_pack_cues_follow_the_combo_guide(self):
        from kallaway_pack import BACKWARDS, load, pack_ready, render, resolve
        ticks = stage_events("counter", 1.0, 2.4, {"value": 7, "items": ["A", "B"]})
        self.assertTrue(all(event.get("mute") for event in ticks if event["kind"] == "ticking"))
        ding = next(event for event in ticks if event["kind"] == "ding")
        self.assertEqual(ding["combo"], "25")
        self.assertIn("Bell 5", ding["file"])
        self.assertIn("Ui 30", ding["bed"]["file"])
        self.assertTrue(all(event["kind"] == "paper" for event in stage_events("doc_fan", 1.0, 2.4, {"count": 3})))
        pages = stage_events("doc_fan", 1.0, 2.4, {"count": 3})
        self.assertIn("Swoosh Fast", pages[0].get("file", ""))
        self.assertTrue(all(event.get("mute") for event in pages[1:]))
        self.assertTrue(all(
            any(extra.get("kind") == "pop" for extra in (event.get("also") or []))
            for event in pages))
        money = stage_events("quote_card", 1.0, 2.4, {"variant": "receipt", "text": "$2,000", "items": ["JAN"]})
        self.assertEqual(money[0]["combo"], "42")
        self.assertIn("Ka Ching", money[0]["file"])
        merge = stage_events("vacuum_merge", 1.0, 2.4, {"items": ["A", "B"]})
        suck = next(event for event in merge if event["kind"] == "whoosh")
        self.assertEqual(suck["align"], "end")
        self.assertIn("Cinematic Reverse", suck["file"])
        self.assertEqual(suck["sound_at"], next(event["at"] for event in merge if event["kind"] == "ding"))
        marker = next(event for event in stage_events("phone_frame", 0.0, 3.0, {
            "callout": {"at": 1.2, "x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2},
        }) if event["kind"] == "marker")
        self.assertEqual(marker["at"], 1.2)
        self.assertEqual(marker["combo"], "callout")
        if not pack_ready():
            return
        samples, info = load(resolve(BACKWARDS))
        self.assertLessEqual(float(np.max(np.abs(samples))), 1.0)
        self.assertLess(info["clip_gain_db"], -10.0)
        whoosh, _placed, whoosh_info = render({"file": "03 Whooshes/Fast Whip.wav", "at": 0, "kind": "whoosh"})
        raw, _raw_info = load(resolve("03 Whooshes/Fast Whip.wav"))
        self.assertEqual(whoosh_info["clip_gain_db"], 0.0)
        self.assertLess(float(np.max(np.abs(whoosh - raw))), 1e-4)


if __name__ == "__main__":
    unittest.main()
