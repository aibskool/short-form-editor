"""Unit tests for the stage motion system: word cues, components, layouts, sound.

python3 production/editor/test_motion_system.py -v
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from cues import CueResolver, CueError
from components import Ctx, render_graphics
from design import Scale, FEELS, DEFAULT_DESIGN
import sfx_kit

WORDS = [{"word": w, "start": round(.2 + i * .4, 3), "end": round(.5 + i * .4, 3)}
         for i, w in enumerate("Then map the workflow then show the demo, the demo sells".split())]


def ctx(duration=6.0):
    resolver = CueResolver(WORDS, duration, 30)
    return Ctx(Scale(720, 1280), dict(DEFAULT_DESIGN), FEELS["snap"], resolver, 720, 1280, 30, duration,
               media=lambda value: f"assets/{value}")


class CueTests(unittest.TestCase):
    def setUp(self):
        self.cues = CueResolver(WORDS, 6.0, 30)

    def test_phrases_occurrences_edges_and_offsets(self):
        self.assertAlmostEqual(self.cues.resolve("@map"), .6)
        self.assertAlmostEqual(self.cues.resolve("@the demo#2"), WORDS[8]["start"])
        self.assertAlmostEqual(self.cues.resolve("@workflow:end"), WORDS[3]["end"])
        self.assertAlmostEqual(self.cues.resolve("@map+0.1"), .7)
        self.assertAlmostEqual(self.cues.resolve("@w5"), WORDS[5]["start"])
        self.assertAlmostEqual(self.cues.resolve({"word": "demo", "n": 2, "edge": "end", "offset": -.05}), WORDS[9]["end"] - .05)
        self.assertAlmostEqual(self.cues.resolve(2.5), 2.5)

    def test_after_picks_the_next_spoken_occurrence(self):
        self.assertAlmostEqual(self.cues.resolve("@then", after=1.0), WORDS[4]["start"])
        self.assertAlmostEqual(self.cues.resolve("@then#1", after=1.0), WORDS[0]["start"])

    def test_strict_start_cues_reject_repeated_words_with_times(self):
        with self.assertRaisesRegex(CueError, r"ambiguous.*#1 at 0\.20s.*#2 at 1\.80s"):
            self.cues.resolve("@then", strict=True)
        self.assertAlmostEqual(self.cues.resolve("@then#2", strict=True), WORDS[4]["start"])
        self.assertAlmostEqual(self.cues.resolve("@map the", strict=True), .6)

    def test_hyphenated_numbers_are_words_not_offsets(self):
        words = [{"word": w, "start": i * 1.0, "end": i * 1.0 + .5} for i, w in enumerate("try GPT now then GPT-5 and 24-7".split())]
        cues = CueResolver(words, 9, 30)
        self.assertAlmostEqual(cues.resolve("@GPT-5"), 4.0)
        self.assertAlmostEqual(cues.resolve("@24-7"), 6.0)
        self.assertAlmostEqual(cues.resolve("@now-0.5"), 1.5)

    def test_unknown_words_fail_with_context(self):
        with self.assertRaisesRegex(CueError, "not in the mapped transcript"):
            self.cues.resolve("@casino")
        with self.assertRaises(CueError):
            self.cues.resolve("casino")


class ComponentTests(unittest.TestCase):
    def render(self, graphics, duration=6.0):
        return render_graphics(graphics, ctx(duration))

    def test_headline_accent_must_be_in_text_and_renders_box(self):
        markup, anims, meta = self.render([{"type": "headline", "start": "@map", "end": 3, "text": "Map The Workflow",
                                            "accent": "Workflow", "accent_style": "box"}])
        self.assertIn("hl-box-bg", markup[0])
        self.assertTrue(any("scaleX:0" in a for a in anims))
        self.assertEqual(meta[0]["type"], "headline")
        with self.assertRaisesRegex(ValueError, "accent"):
            self.render([{"type": "headline", "start": .1, "end": 2, "text": "Map it", "accent": "Casino"}])

    def test_review_regressions_ids_accents_ops_wipes_and_silence(self):
        with self.assertRaisesRegex(ValueError, "start with a letter"):
            self.render([{"id": "1-hook", "type": "badge", "start": .1, "end": 2, "text": "1"}])
        with self.assertRaisesRegex(ValueError, "duplicate graphic id"):
            self.render([{"id": "a-b", "type": "badge", "start": .1, "end": 2, "text": "1"},
                         {"id": "a_b", "type": "badge", "start": .1, "end": 2, "text": "2"}])
        with self.assertRaisesRegex(ValueError, "within one line"):
            self.render([{"type": "headline", "start": .1, "end": 2, "lines": ["Map the", "workflow then"],
                          "accent": "the workflow"}])
        with self.assertRaisesRegex(ValueError, "ops"):
            self.render([{"type": "equation", "start": .1, "end": 4, "ops": ["+"],
                          "terms": [{"label": "A"}, {"label": "B"}, {"label": "C"}]}])
        _, anims, _ = self.render([{"id": "u", "type": "headline", "start": .1, "end": 3, "text": "Map The Workflow",
                                    "accent": "Workflow", "accent_style": "underline"}])
        wipe = [a for a in anims if '"#u-accent"' in a]
        self.assertTrue(wipe and "clipPath" in wipe[0] and "drawSVG" not in wipe[0], wipe)
        c = ctx()
        render_graphics([{"type": "orbit", "start": .2, "end": 4, "sfx": None, "center": {"label": "Hub"},
                          "items": [{"label": "A", "icon": "inbox"}, {"label": "B", "icon": "bot"}]},
                         {"type": "device", "start": .2, "end": 4, "media": "ui.png", "sfx": None,
                          "taps": [{"x": 50, "y": 50, "at": 2.0}]}], c)
        self.assertEqual(c.sfx_events, [])
        _, anims, _ = self.render([{"id": "d", "type": "device", "start": .2, "end": 4, "media": "ui.png",
                                    "taps": [{"x": 50, "y": 50, "at": 2.0}]}])
        self.assertTrue(any('"#d-t0"' in a and "immediateRender:false" in a for a in anims))

    def test_bounds_types_ids_and_internal_cues_are_validated(self):
        with self.assertRaisesRegex(ValueError, "frame width"):
            self.render([{"type": "badge", "start": .1, "end": 2, "text": "#1", "x": 90, "w": 20}])
        with self.assertRaisesRegex(ValueError, "type must be one of"):
            self.render([{"type": "sparkles", "start": .1, "end": 2}])
        with self.assertRaisesRegex(ValueError, "duplicate graphic id"):
            self.render([{"id": "a", "type": "badge", "start": .1, "end": 2, "text": "1"},
                         {"id": "a", "type": "badge", "start": .1, "end": 2, "text": "2"}])
        with self.assertRaisesRegex(ValueError, "outside its graphic"):
            self.render([{"type": "flow", "start": 1.0, "end": 2.0, "nodes": [{"id": "a", "label": "A", "at": "@sells"}]}])
        with self.assertRaisesRegex(ValueError, "existing node ids"):
            self.render([{"type": "flow", "start": .1, "end": 3, "nodes": [{"id": "a", "label": "A"}],
                          "links": [{"from": "a", "to": "zzz"}]}])

    def test_flow_draws_links_on_cue_with_slots_and_pulses(self):
        markup, anims, _ = self.render([{"type": "flow", "start": .2, "end": 5.5, "layout": "row",
            "nodes": [{"id": "lead", "label": "Lead", "icon": "inbox", "at": "@map"},
                      {"id": "agent", "label": "Agent", "icon": "bot", "at": "@workflow", "win_at": "@show"}],
            "links": [{"from": "lead", "to": "agent", "at": "@workflow:end"}],
            "focus": [{"at": "@map", "node": "lead"}]}])
        self.assertIn("fl-slot", markup[0])
        self.assertTrue(any("drawSVG" in a and f"{WORDS[3]['end']:.4f}"[:4] in a for a in anims))
        self.assertTrue(any("motionPath" in a for a in anims))

    def test_stat_counts_on_spoken_number_and_starts_at_from_value(self):
        markup, anims, _ = self.render([{"type": "stat", "start": .2, "end": 5, "value": 41, "from": 12, "suffix": "%",
                                         "count_at": "@demo"}])
        self.assertIn(">12%<", markup[0])
        self.assertTrue(any("__fmt" in a and "v:41" in a for a in anims))

    def test_cta_styles_do_not_leak_onto_their_container(self):
        markup, _, _ = self.render([{"type": "cta", "style": "stamp", "start": .2, "end": 5, "keyword": "DEMO",
                                     "keyword_at": "@demo#1"}])
        self.assertIn("ct-style-stamp", markup[0])
        self.assertNotIn('class="ct ct-stamp"', markup[0])

    def test_graphic_held_to_the_last_frame_does_not_exit(self):
        _, anims, meta = self.render([{"type": "cta", "id": "close", "start": 3.5, "end": 6.02, "keyword": "demo",
                                       "keyword_at": "@demo#2"}])
        self.assertEqual(meta[0]["end"], 6.0)
        self.assertFalse(any('tl.set("#close' in a and "opacity:0}" in a for a in anims), anims)

    def test_cta_keyword_must_be_spoken(self):
        with self.assertRaisesRegex(ValueError, "never spoken"):
            self.render([{"type": "cta", "start": .2, "end": 5, "keyword": "FLOW", "keyword_at": 1.0}])

    def test_prompt_reserves_final_size_and_types_exact_text(self):
        markup, anims, _ = self.render([{"type": "prompt", "start": .2, "end": 5, "text": "Score every lead",
                                         "type_start": "@map", "type_end": "@workflow:end"}])
        self.assertIn('pr-ghost">Score every lead<', markup[0])
        self.assertTrue(any('"Score every lead".slice' in a for a in anims))
        blink = next(a for a in anims if "-caret" in a and "repeat:" in a)
        repeats = int(blink.split("repeat:")[1].split(",")[0])
        self.assertLess(.2 + .25 * (repeats + 1), 5)  # the blink stops before the clip ends (lint hard-kill rule)
        self.assertGreater(.25 * (repeats + 1), 4)

    def test_exits_hard_kill_at_clip_end(self):
        _, anims, _ = self.render([{"type": "card", "start": .2, "end": 3.0, "title": "One task", "icon": "briefcase"}])
        self.assertTrue(any('tl.set("#g0-card-body",{opacity:0},3.0000)' in a for a in anims))

    def test_sound_events_follow_visual_cues(self):
        c = ctx()
        render_graphics([{"type": "badge", "start": "@show", "end": 4, "text": "#1", "sfx": "pop"}], c)
        self.assertEqual(c.sfx_events[0]["kind"], "pop")
        self.assertAlmostEqual(c.sfx_events[0]["at"], WORDS[5]["start"], places=1)


class SoundTests(unittest.TestCase):
    def test_every_sound_is_finite_normalized_and_not_a_beep(self):
        for kind in sorted(sfx_kit.KINDS):
            data = sfx_kit.synth(kind, .8)
            self.assertTrue(len(data) > 100, kind)
            peak = max(abs(float(v)) for v in data)
            self.assertAlmostEqual(peak, 10 ** (-1 / 20), places=3)
        for legacy, current in sfx_kit.LEGACY.items():
            self.assertIn(current, sfx_kit.KINDS, legacy)

    def test_plan_keeps_restraint(self):
        events = [{"kind": "thud", "at": t, "source": "g"} for t in (1, 2, 6, 11, 16)]
        kept, dropped = sfx_kit.plan(events, 20)
        self.assertEqual([e["at"] for e in kept], [1, 6, 11])
        events = [{"kind": "whoosh", "at": 1.0, "source": "g"}, {"kind": "whoosh_short", "at": 1.5, "source": "g"},
                  {"kind": "typing", "at": 1.02, "source": "g", "duration": 1},
                  {"kind": "pop", "at": 3.0, "source": "g"}, {"kind": "tick", "at": 3.05, "source": "g"},
                  {"kind": "whoosh_short", "at": 1.45, "source": "transition-0"}]
        kept, dropped = sfx_kit.plan(events, 20)
        kinds = sorted((e["kind"], e["at"]) for e in kept)
        self.assertIn(("whoosh_short", 1.45), kinds)   # transition whoosh outranks the entrance whoosh
        self.assertIn(("typing", 1.02), kinds)          # sustained sounds layer under transients
        self.assertNotIn(("tick", 3.05), kinds)
        explicit = sfx_kit.plan([{"kind": "thud", "at": t, "explicit": True} for t in (1, 1.5, 2, 2.5)], 5)[0]
        self.assertEqual(len(explicit), 4)


class BuildTests(unittest.TestCase):
    def fixture(self, root, extra):
        source = root / "source.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x223344:size=180x320:rate=30",
                        "-f", "lavfi", "-i", "sine=frequency=180:sample_rate=48000", "-t", "6",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)], check=True)
        (root / "words.json").write_text(json.dumps({"words": WORDS}))
        spec = {"source": {"path": "source.mp4", "segments": [{"start": 0, "end": 6}]}, "words_path": "words.json",
                "output": {"width": 360, "height": 640, "fps": 30}, "audio_policy": {"music_required": False},
                "spoken_captions": {"style": "karaoke", "emphasis": ["demo"]}}
        spec.update(extra)
        path = root / "timeline.json"
        path.write_text(json.dumps(spec))
        return path

    def test_stage_layout_graphics_and_retired_effects(self):
        from edit import build
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spec = self.fixture(root, {
                "shots": [{"start": 0, "end": "@map", "layout": "presenter"},
                          {"start": "@map", "end": "@show", "layout": "stage", "enter": "morph"},
                          {"start": "@show", "end": 6, "layout": "presenter", "enter": "morph"}],
                "graphics": [{"type": "headline", "start": "@map", "end": "@show-0.1", "text": "Map The Workflow", "accent": "Workflow"},
                             {"type": "cta", "start": "@show", "end": 5.9, "keyword": "DEMO", "keyword_at": "@demo#2", "style": "chip"}],
                "transitions": [{"kind": "whip", "at": "@show", "duration": .3}],
                "camera": [{"kind": "push", "at": .2, "scale": 1.05, "duration": 1}]})
            receipt = build(str(spec), str(root / "comp"))
            html = (root / "comp/index.html").read_text()
            self.assertIn('<div id="backdrop"><div id="stage-bg-1"', html)
            self.assertIn("seen=new WeakMap()", html)
            self.assertIn("@font-face{font-family:'Inter Tight'", html)
            self.assertIn('class="caption clip karaoke"', html)
            self.assertEqual(receipt["graphics"], 2)
            report = receipt["motion_report"]
            self.assertGreater(report["layout_seconds"]["stage"], 1)
            self.assertEqual(report["presenter_visible_ratio"], 1.0)
            self.assertGreater(report["sfx_kept"], 0)
            self.assertIsNotNone(report["sfx_levels"]["voice_integrated_lufs"])
            self.assertTrue((root / "comp/assets/fonts/archivo-black-latin-400-normal.woff2").is_file())
            self.assertIn(".caption .word,.caption .emphasis{display:inline-block}", html)
            self.assertNotIn(".caption span{display:inline-block}", html)
            resolved = json.loads((root / "comp/resolved-timeline.json").read_text())
            self.assertAlmostEqual(resolved["shots"][1]["start"], round(WORDS[1]["start"] * 30) / 30, places=3)
            self.assertEqual([g["type"] for g in report["timeline"]], ["headline", "cta"])
            overlap = self.fixture(root, {"shots": [{"start": 0, "end": "@map", "layout": "stage"},
                                                    {"start": "@map", "end": 6, "layout": "presenter", "enter": "morph"}],
                                          "camera": [{"kind": "push", "at": "@map+0.1", "scale": 1.05}]})
            warned = build(str(overlap), str(root / "overlap"))["motion_report"]["warnings"]
            self.assertTrue(any("during the presenter morph" in w for w in warned), warned)
            for bad, message in (({"transitions": [{"kind": "green_wipe", "at": 1, "duration": .3}]}, "retired"),
                                 ({"flashes": [{"at": 1, "color": "#49cf26"}]}, "green flashes"),
                                 ({"graphics": [{"type": "badge", "start": "@then", "end": 3, "text": "1"}]}, "ambiguous")):
                with self.assertRaisesRegex(ValueError, message):
                    build(str(self.fixture(root, bad)), str(root / "bad"))

    def test_bright_media_backing_respects_split_layout(self):
        from edit import bright_caption_band
        with tempfile.TemporaryDirectory() as folder:
            white = Path(folder) / "white.png"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=white:size=90x160",
                            "-frames:v", "1", str(white)], check=True)
            self.assertTrue(bright_caption_band(white, {"start": 0, "end": 1}, 83, False, .5))
            self.assertFalse(bright_caption_band(white, {"start": 0, "end": 1}, 83, True, .5))
            self.assertTrue(bright_caption_band(white, {"start": 0, "end": 1}, 40, True, .5))

    def test_legacy_editorial_graphics_render_as_kinetic_statements(self):
        from edit import build
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spec = self.fixture(root, {"editorial_graphics": [{"claim_id": "hook", "text": "Verified idea", "start": 0,
                                                                "end": 2, "accent_words": ["Verified"], "animation": "pop"}]})
            build(str(spec), str(root / "comp"))
            html = (root / "comp/index.html").read_text()
            self.assertIn('id="editorial-0"', html)
            self.assertIn('data-beat="hook"', html)


if __name__ == "__main__":
    unittest.main()
