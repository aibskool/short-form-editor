import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kallaway_audio import SFX_KINDS, keep_ranges, write_sfx_library
from kallaway_motifs import MOTIFS, stage_events
from kallaway_plan import LIBRARY, caption_phrases, plan_timeline, plain_text, video_seed, _rotate
from kallaway_style import load_theme


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
