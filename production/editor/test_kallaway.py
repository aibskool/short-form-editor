import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from kallaway_audio import SFX_KINDS, keep_ranges, refine_word_bounds, sfx_variants, write_sfx_library
from kallaway_motifs import MOTIFS, motif_markup, resolve_annotations, screenshot_box, stage_events
from kallaway_plan import LIBRARY, caption_phrases, plan_timeline, plain_text, video_seed, _rotate
from kallaway_style import _caption_text, load_theme


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
        self.assertLess(refined[0]["end"], 0.48)
        self.assertGreater(refined[0]["end"], 0.40)

    def test_energy_trim_keeps_a_stop_closure_inside_the_word(self):
        rate = 16000
        t = np.arange(rate) / rate
        first = ((t >= 0.20) & (t < 0.46)).astype(np.float64) * 0.25 * np.sin(2 * np.pi * 180 * t)
        second = ((t >= 0.56) & (t < 0.90)).astype(np.float64) * 0.4 * np.sin(2 * np.pi * 180 * t)
        refined = refine_word_bounds(first + second, rate, [{"word": "reactivation", "start": 0.22, "end": 0.92}])
        self.assertLess(refined[0]["start"], 0.24)
        self.assertGreater(refined[0]["end"], 0.85)

    def test_split_card_is_tall_and_sfx_are_recorded_variants(self):
        theme, _, _, _ = load_theme("dark")
        layout = theme["layout"]
        height = layout["card_bottom"] - layout["card_top"]
        self.assertGreaterEqual(height, 0.38)
        self.assertLessEqual(height, 0.42)
        self.assertLess(layout["caption_split_y"], layout["card_top"])
        self.assertGreater(layout["caption_split_y"], layout["stage_top"] + layout["stage_height"])
        self.assertEqual(layout["wide_scale"], 1.0)
        self.assertAlmostEqual(layout["tight_scale"], 1.08)
        self.assertAlmostEqual(theme["audio"]["pause_gap_seconds"], 0.06)
        self.assertIn("paper", SFX_KINDS)
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
        self.assertTrue(all(phrase["word_range"][1] - phrase["word_range"][0] <= 2 for phrase in phrases))
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


if __name__ == "__main__":
    unittest.main()
