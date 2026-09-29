"""House style, planner and acceptance review tests.

python3 production/editor/test_house_style.py -v

Covers the single style spec, the bubble-pop sound family and sparse SFX policy, the
presenter-first primitives (hero variants, callouts, screen detail, payoff reveal), the
beat planner on two differently structured stories, the acceptance review, and the
removal of proof gates from the editorial rules.
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import style
import sfx_kit
from cues import CueResolver
from components import Ctx, render_graphics
from design import Scale, FEELS, DEFAULT_DESIGN

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

STORY_DEMO = ("I built a two thousand dollar app in one afternoon. I gave Claude one prompt and it wrote the code. "
              "But the crazy part is what happened next. It found ten real customers, wrote each one a personal email, "
              "and hit the send button. And now the app is live on its own domain with paying users. "
              "Comment the word LAUNCH and I will send you the prompt.")
STORY_CLAIM = ("Most people use AI like a search engine. That is the mistake. Here's the thing nobody tells you. "
               "The best prompts give the model a job, a goal and a finish line. Instead of asking questions you hand "
               "it the whole task. Try it on your next project today. Comment the word JOB and I will send you my template.")


def timed_words(text, rate=.31, pause=.28):
    words, t = [], .15
    for token in text.split():
        length = rate + .012 * len(token)
        words.append({"word": token, "start": round(t, 3), "end": round(t + length - .04, 3)})
        t += length + (pause if token.endswith((".", "?", "!")) else .06 if token.endswith(",") else 0)
    return words, t + .3


def still(path, text, dark=False):
    im = Image.new("RGB", (540, 960), (18, 20, 19) if dark else (244, 241, 234))
    d = ImageDraw.Draw(im)
    for i, line in enumerate(text):
        d.rectangle((40, 120 + i * 150, 500, 200 + i * 150), fill=(60, 64, 62) if dark else (210, 205, 196))
        d.text((60, 145 + i * 150), line, fill=(255, 255, 255) if dark else (20, 20, 20))
    im.save(path)


def source_video(path, seconds):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x39424a:size=180x320:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=170:sample_rate=48000", "-t", f"{seconds:.2f}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)


class StyleSpecTests(unittest.TestCase):
    def test_one_spec_feeds_the_pipeline(self):
        spec = style.load()
        for section in style.SECTIONS:
            self.assertIn(section, spec)
        self.assertEqual(spec["color"]["accent"], "#49cf26")
        self.assertEqual(style.caption_defaults()["style"], "pop")
        self.assertIn("karaoke", spec["captions"]["forbid_styles"])
        self.assertFalse(spec["sound"]["music"])
        self.assertEqual(DEFAULT_DESIGN["accent"], spec["color"]["accent"])  # design tokens come from the spec

    def test_overrides_merge_and_unknown_keys_fail(self):
        merged = style.load({"zones": {"caption": {"y": 70}}})
        self.assertEqual(merged["zones"]["caption"]["y"], 70)
        self.assertEqual(style.caption_defaults(merged)["y"], 70)
        self.assertEqual(style.load()["zones"]["caption"]["y"], 71.5)  # the base spec is untouched
        with self.assertRaisesRegex(ValueError, "unknown style key"):
            style.load({"captions": {"colour": "red"}})

    def test_sound_roles_use_the_bubble_family_and_retire_the_old_pop(self):
        self.assertEqual(style.sound_role("popup"), "bubble")
        self.assertEqual(style.sound_role("popup_soft"), "bubble_soft")
        self.assertEqual(style.sound_role("travel"), "whoosh_short")
        self.assertEqual(style.sound_role("reveal"), "impact_soft")
        self.assertIsNone(style.sound_role("type"))
        roles = style.load()["sound"]["roles"].values()
        self.assertNotIn("pop", roles)
        self.assertIn("pop", style.load()["sound"]["forbidden_kinds"])


class BubbleSoundTests(unittest.TestCase):
    def test_bubble_variants_differ_and_stay_soft(self):
        a = sfx_kit.synth("bubble", .3, variant=0)
        b = sfx_kit.synth("bubble", .3, variant=3)
        self.assertNotEqual(list(a[:400]), list(b[:400]))
        for data in (a, b):
            peak = max(abs(float(v)) for v in data)
            self.assertLess(peak, 1.0)
        self.assertEqual(sfx_kit.LEGACY.get("pop"), "bubble")

    def test_component_popups_land_as_bubbles_after_the_graphic_lands(self):
        words = [{"word": w, "start": .3 + i * .5, "end": .6 + i * .5} for i, w in enumerate("one clear result".split())]
        c = Ctx(Scale(720, 1280), dict(DEFAULT_DESIGN), FEELS["snap"], CueResolver(words, 4, 30), 720, 1280, 30, 4,
                media=lambda value: f"assets/{value}")
        render_graphics([{"type": "tag", "start": "@clear", "end": 3.5, "items": [{"text": "Clear", "at": "@clear"}]}], c)
        popup = [e for e in c.sfx_events if e.get("role") == "popup"]
        self.assertEqual(popup[0]["kind"], "bubble")
        self.assertAlmostEqual(popup[0]["at"], round(words[1]["start"] * 30) / 30 + .07, places=2)

    def test_plan_skips_pops_in_dense_speech_and_clusters(self):
        dense = [{"word": "w", "start": 1 + i * .15, "end": 1.1 + i * .15} for i in range(10)]
        kept, dropped = sfx_kit.plan([{"kind": "bubble", "at": 1.5, "source": "g", "role": "popup"}], 10, words=dense)
        self.assertEqual(kept, [])
        self.assertIn("dense speech", dropped[0]["reason"])
        events = [{"kind": "bubble", "at": 4.0 + i * .2, "source": f"g{i}", "role": "popup"} for i in range(3)]
        kept, dropped = sfx_kit.plan(events, 10)
        self.assertEqual(len(kept), 1)
        self.assertTrue(all("cluster" in d["reason"] for d in dropped))

    def test_every_ten_second_window_respects_the_cap(self):
        events = [{"kind": "bubble", "at": t, "source": f"g{n}", "role": "popup"} for n, t in enumerate((4, 5, 6, 7, 11, 12.5))]
        kept, _ = sfx_kit.plan(events, 20)
        times = [e["at"] for e in kept]
        cap = style.load()["sound"]["max_per_10s"]
        self.assertTrue(all(sum(1 for u in times if t <= u < t + 10) <= cap for t in times), times)


class PrimitiveTests(unittest.TestCase):
    def ctx(self, words, duration):
        return Ctx(Scale(720, 1280), dict(DEFAULT_DESIGN), FEELS["snap"], CueResolver(words, duration, 30), 720, 1280, 30,
                   duration, media=lambda value: f"assets/{value}")

    def test_hero_variants_render_and_words_land_before_the_exit(self):
        words = [{"word": w, "start": .2 + i * .22, "end": .4 + i * .22} for i, w in enumerate("to top it all off".split())]
        for variant in ("stack", "slam", "split", "outline", "card"):
            c = self.ctx(words, 3)
            spec = {"id": f"h-{variant}", "type": "hero", "variant": variant, "start": .15, "end": 1.2,
                    "accent_words": ["OFF"]}
            spec.update({"lines": ["TO TOP IT", "ALL OFF"]} if variant == "split" else {"text": "TO TOP IT ALL OFF"})
            markup, anims, meta = render_graphics([spec], c)
            self.assertTrue(meta[0]["hides_captions"])
            starts = [float(m) for m in re.findall(r'tl\.fromTo\("#h-\w+-w\d",\{(?:yPercent|scale)[^;]*?\},([\d.]+)\);', "".join(anims))]
            exits = [float(m) for m in re.findall(r'tl\.to\([^;]*opacity:0[^;]*,([\d.]+)\);', "".join(anims))]
            if starts and exits:
                self.assertLess(max(starts), min(exits), variant)
        with self.assertRaisesRegex(ValueError, "split needs exactly two lines"):
            render_graphics([{"type": "hero", "variant": "split", "text": "ONE LINE", "start": 0, "end": 1}], self.ctx(words, 3))

    def test_showpieces_are_marked_for_the_review(self):
        words = [{"word": w, "start": .2 + i * .3, "end": .45 + i * .3} for i, w in enumerate("live on the internet".split())]
        c = self.ctx(words, 5)
        c.still = lambda asset, at=0, blur=0: f"assets/still-{blur}.jpg"
        _, _, meta = render_graphics([
            {"id": "pay", "type": "reveal", "media": "site.png", "title": "LIVE ON THE INTERNET", "start": .1, "end": 4},
            {"id": "slam", "type": "hero", "variant": "slam", "text": "LIVE", "start": .2, "end": 1.2},
            {"id": "stack", "type": "hero", "variant": "stack", "text": "ON THE INTERNET", "start": 1.3, "end": 2.4}], c)
        self.assertEqual([m["showpiece"] for m in meta], [True, True, False])


class PlannerTests(unittest.TestCase):
    """The planner reads the story before choosing graphics, and two stories get two edits."""

    def plan(self, root, text, name, assets=None, avoid=None):
        from plan_reel import plan_reel
        words, seconds = timed_words(text)
        source_video(root / f"{name}.mp4", seconds)
        (root / f"{name}.words.json").write_text(json.dumps({"words": words}))
        draft = {"title": name, "source": {"path": f"{name}.mp4"}, "words_path": f"{name}.words.json",
                 "output": {"width": 360, "height": 640, "fps": 30},
                 "variation": {"avoid": avoid or {"cta_styles": ["bubble"]}}}
        (root / f"{name}.draft.json").write_text(json.dumps(draft))
        timeline, plan = plan_reel(root / f"{name}.draft.json", assets, seed=11)
        path = root / f"{name}.timeline.json"
        path.write_text(json.dumps(timeline))
        return timeline, plan, path

    def assets(self, root):
        still(root / "code.png", ["def build_app():", "prompt -> code"], dark=True)
        still(root / "mail.png", ["To: customer", "A personal email", "[ Send ]"])
        still(root / "site.png", ["LAUNCH", "Live app", "Paying users"])
        inventory = {"assets": [
            {"id": "code", "path": "code.png", "quality": "sharp", "aspect": .5625,
             "tags": ["prompt", "code", "wrote", "claude"],
             "moments": [{"label": "the prompt", "rect": [5, 10, 90, 12], "tags": ["prompt", "gave"]},
                         {"label": "the code", "rect": [5, 26, 90, 12], "tags": ["code", "wrote"]}]},
            {"id": "mail", "path": "mail.png", "quality": "soft", "aspect": .5625,
             "tags": ["email", "customers", "send", "button", "personal"],
             "moments": [{"label": "personal email", "rect": [5, 26, 90, 12], "tags": ["email", "personal", "wrote"]},
                         {"label": "send", "rect": [5, 42, 90, 12], "tags": ["send", "button", "hit"]}]},
            {"id": "site", "path": "site.png", "quality": "sharp", "aspect": .5625, "result": True,
             "tags": ["app", "live", "domain", "users", "paying"],
             "moments": [{"label": "live", "rect": [5, 10, 90, 30], "tags": ["live", "app", "domain", "users"]}]}]}
        (root / "assets.json").write_text(json.dumps(inventory))
        return root / "assets.json"

    def test_story_beats_are_found_before_graphics(self):
        from plan_reel import plan_reel  # noqa: F401
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            timeline, plan, _ = self.plan(root, STORY_DEMO, "demo", self.assets(root))
            roles = [b["role"] for b in plan["beats"]]
            self.assertEqual(roles[0], "hook")
            self.assertEqual(roles[-1], "cta")
            self.assertIn("turn", roles)
            self.assertIn("demo", roles)
            self.assertIn("payoff", roles)
            hook_stress = [s["word"].lower() for s in plan["beats"][0]["stressed"]]
            self.assertTrue({"thousand", "two", "one"} & set(hook_stress), hook_stress)
            self.assertIn("thousand", [e.lower() for e in timeline["spoken_captions"]["emphasis"]])

    def test_two_stories_build_presenter_first_and_look_different(self):
        from edit import build
        import review_reel
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demo, _, demo_path = self.plan(root, STORY_DEMO, "demo", self.assets(root))
            claim, _, claim_path = self.plan(root, STORY_CLAIM, "claim", None, {"cta_styles": ["bubble", "chip"]})
            signatures = []
            for name, timeline, path in (("demo", demo, demo_path), ("claim", claim, claim_path)):
                self.assertFalse(any(s.get("layout") in {"stage", "split"} for s in timeline["shots"]), name)
                kinds = [t["kind"] for t in timeline["transitions"]]
                self.assertTrue(all(a != b for a, b in zip(kinds, kinds[1:])), kinds)
                receipt = build(str(path), str(root / f"{name}-build"))
                report = receipt["motion_report"]
                self.assertEqual(report["captions"]["style"], "pop")
                self.assertTrue(all(e["kind"] not in {"pop", "tick", "beep"} for e in report["sfx_events"]))
                result = review_reel.review(root / f"{name}-build")
                failed = [c for c in result["checks"] if c["status"] == "fail"]
                self.assertEqual(failed, [], name)
                first_text = min(g["start"] for g in report["graphics_meta"] if g["type"] in {"hero", "stat", "reveal"})
                self.assertLessEqual(first_text, 1.3, name)
                signatures.append((tuple(g["type"] + ":" + str(g.get("variant")) for g in report["graphics_meta"]),
                                   tuple(s.get("layout") for s in timeline["shots"])))
            self.assertNotEqual(signatures[0], signatures[1])
            self.assertTrue(any(s.get("layout") == "screen" for s in demo["shots"]))
            self.assertFalse(any(s.get("layout") == "screen" for s in claim["shots"]))
            self.assertTrue(any(g["type"] == "reveal" for g in demo["graphics"]))
            cta = [g for g in claim["graphics"] if g["type"] == "cta"]
            self.assertTrue(cta and cta[0]["style"] not in {"bubble", "chip"})


class ReviewTests(unittest.TestCase):
    def test_review_fails_the_retired_patterns(self):
        from edit import build
        import review_reel
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            words, seconds = timed_words(STORY_CLAIM)
            source_video(root / "src.mp4", seconds)
            (root / "words.json").write_text(json.dumps({"words": words}))
            spec = {"source": {"path": "src.mp4"}, "words_path": "words.json",
                    "output": {"width": 360, "height": 640, "fps": 30}, "audio_policy": {"music_required": False},
                    "spoken_captions": {"style": "karaoke"},
                    "shots": [{"start": 0, "end": 1.0, "layout": "presenter"},
                              {"start": 1.0, "end": 9.0, "layout": "stage"},
                              {"start": 9.0, "end": round(seconds - .1, 2), "layout": "presenter"}],
                    "graphics": [{"type": "statement", "start": "@mistake", "end": "@nobody", "text": "Results may vary",
                                  "y": 12},
                                 {"type": "equation", "start": 0.05, "end": 4.5, "y": 20,
                                  "terms": [{"label": "AI", "icon": "bot"}, {"label": "Search", "icon": "search"}],
                                  "result": {"text": "Mistake"}}]}
            (root / "timeline.json").write_text(json.dumps(spec))
            build(str(root / "timeline.json"), str(root / "comp"))
            result = review_reel.review(root / "comp")
            status = {(c["area"], c["check"]): c["status"] for c in result["checks"]}
            self.assertEqual(status[("legibility", "caption_style")], "fail")
            self.assertEqual(status[("presenter", "stacked_band")], "fail")
            self.assertEqual(status[("forbidden", "disclaimers")], "fail")
            self.assertEqual(status[("hook", "slow_open")], "fail")
            self.assertEqual(result["result"]["status"], "fail")
            markdown = review_reel.to_markdown(result)
            self.assertIn("## Fix first", markdown)

    def test_effect_levels_survive_sub_millisecond_clip_placement(self):
        # HyperFrames places each voice clip on a whole millisecond. A reel cut at 39.5867 s
        # came back 0.3 ms late, which decorrelated the rebuilt voice and hid every effect level.
        import numpy as np
        import wave
        import review_reel
        rate = 48000

        def write(path, samples):
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        rng = np.random.default_rng(7)
        t = np.arange(int(8.5 * rate)) / rate
        noise = np.fft.rfft(rng.normal(0, .12, t.size))
        noise[np.fft.rfftfreq(t.size, 1 / rate) > 4000] = 0      # speech-band, like a voice
        speech = np.fft.irfft(noise, t.size) * 3 * (.55 + .45 * np.sin(2 * np.pi * 4 * t) ** 2)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / "voice.wav", speech)
            late = 4 * rate + int(.0003 * rate)          # the second clip lands 0.3 ms late
            mix = np.zeros(8 * rate)
            mix[:4 * rate] = speech[:4 * rate]
            mix[late:] = speech[int(4.2 * rate):int(4.2 * rate) + 8 * rate - late]
            bubble = .25 * np.sin(2 * np.pi * 900 * np.arange(int(.12 * rate)) / rate) * np.hanning(int(.12 * rate))
            mix[2 * rate:2 * rate + bubble.size] += bubble
            write(root / "render.wav", mix)

            class Built:
                project = root
                style = style.load()
                sfx = [{"kind": "bubble", "at": 2.0}]
                html = ('<audio id="voice-0" src="voice.wav" data-start="0.000000" data-duration="4.000000" data-media-start="0.0">'
                        '<audio id="voice-1" src="voice.wav" data-start="4.000000" data-duration="4.000000" data-media-start="4.2">'
                        '<audio id="sfx-0" src="bubble.wav" data-start="2.0" data-duration="0.12">')
            result = review_reel.mix_analysis(Built(), root / "render.wav")
            self.assertLess(result["gain_spread"], .03, result)
            self.assertEqual([e["kind"] for e in result["events"]], ["bubble"])
            self.assertLess(result["events"][0]["effect_lu"], -3)

    def test_render_measure_tracks_presence_and_silence(self):
        import review_reel
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "clip.mp4"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:size=180x320:rate=30",
                            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                            "yuv420p", "-c:a", "aac", "-shortest", str(video)], check=True)
            metrics = review_reel.measure_render(video, style.load(), fps=5)
            self.assertEqual(metrics["presenter"]["full"], 0.0)  # no face anywhere
            self.assertGreater(metrics["dark_share"], .9)
            self.assertTrue(metrics["dark_runs"])


class HardeningTests(unittest.TestCase):
    """Defects an independent review found in the first version of the planner and review."""

    def plan(self, root, text, name, assets=None, seed=5, segments=None):
        from plan_reel import plan_reel
        words, seconds = timed_words(text)
        source_video(root / f"{name}.mp4", seconds)
        (root / f"{name}.words.json").write_text(json.dumps({"words": words}))
        draft = {"title": name, "source": {"path": f"{name}.mp4", **({"segments": segments(words)} if segments else {})},
                 "words_path": f"{name}.words.json", "output": {"width": 360, "height": 640, "fps": 30}}
        (root / f"{name}.draft.json").write_text(json.dumps(draft))
        return plan_reel(root / f"{name}.draft.json", assets, seed=seed), words

    def test_light_layers_are_hard_killed_where_their_fade_ends(self):
        # HyperFrames lint (gsap_exit_missing_hard_kill) failed a real reel when a light leak's
        # fade ended on another clip's start with no tl.set after it.
        import edit

        class Quiet:
            def sound(self, *args, **kwargs):
                pass

        for kind in ("flash", "blur_flash", "light_leak"):
            _, motion, _ = edit.frame_transition({"kind": kind, "at": 24.3667, "duration": .4}, 3, 60, Scale(720, 1280), Quiet())
            self.assertIn('tl.set("#transition-3",{opacity:0},24.7667);', "".join(motion), kind)

    def test_source_cuts_land_on_whole_milliseconds(self):
        # The renderer places audio clips on a millisecond grid; a cut at 39.5867 s put the
        # voice 0.3 ms away from where the picture and the review expected it.
        from edit import build
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_video(root / "src.mp4", 4)
            spec = {"source": {"path": "src.mp4", "segments": [{"start": 0, "end": 1.23456}, {"start": 1.5333, "end": 3.0}]},
                    "output": {"width": 360, "height": 640, "fps": 30}, "audio_policy": {"music_required": False},
                    "shots": [{"start": 0, "end": 2.70, "layout": "presenter"}]}
            (root / "timeline.json").write_text(json.dumps(spec))
            build(str(root / "timeline.json"), str(root / "comp"))
            html = (root / "comp/index.html").read_text()
            self.assertIn('id="voice-1" src="assets/media-000.mp4" data-start="1.235000" data-duration="1.467000" '
                          'data-media-start="1.533"', html)

    def test_any_exit_ending_on_a_clip_start_gets_a_matching_hard_kill(self):
        # The same lint failed a split hero whose line exits ended on an A-roll clip start;
        # the builder now adds the kill for any exit that lands within 50 ms of a clip start.
        import edit
        script = ('tl.to("#hero-l0",{x:-150,opacity:0,duration:.3,ease:"power3.in"},51.22);'
                  'tl.to(["#w0","#w1"],{yPercent:-60,opacity:0,duration:.2,stagger:.05},2.0);tl.set(["#w0","#w1"],{opacity:0},2.26);'
                  'tl.fromTo("#far",{opacity:1},{opacity:0,duration:.4,filter:"blur(8px)"},3.0);'
                  'tl.to("#half",{opacity:.5,duration:.4},3.5);')
        markup = '<video class="clip" data-start="51.5201"></video><div data-start="2.25"></div><div data-start="3.9"></div>'
        self.assertEqual(edit.boundary_hard_kills(script, markup), ['tl.set("#hero-l0",{opacity:0},51.5200);'])

    def test_a_spoken_w_number_is_a_word_not_an_index(self):
        words = [{"word": w, "start": i * .4, "end": i * .4 + .3} for i, w in enumerate("send the W2 form today".split())]
        resolver = CueResolver(words, 3, 30)
        self.assertAlmostEqual(resolver.resolve("@w2"), .8)       # the spoken "W2"
        self.assertAlmostEqual(resolver.resolve("@w3"), 1.2)      # no spoken "w3": word index 3

    def test_caption_emphasis_uses_one_key_in_planner_and_builder(self):
        from cues import emphasis_key
        self.assertEqual(emphasis_key("$5,000."), emphasis_key("$5000"))
        self.assertEqual(emphasis_key("\u201cWebsite\u201d"), "website")

    def test_spoken_money_keeps_his_number(self):
        from plan_reel import display_words
        self.assertEqual(display_words("I built a two thousand dollar app".split()), ["I", "built", "a", "$2,000", "app"])
        self.assertEqual(display_words("a thousand dollar site".split()), ["$1,000", "site"])
        self.assertEqual(display_words("one point five million users".split()), ["1.5M", "users"])

    def test_spoken_amounts_stay_whole_on_screen(self):
        from plan_reel import display_words, phrase_around, clauses
        self.assertEqual(display_words("thirteen thousand dollars".split()), ["$13,000"])
        self.assertEqual(display_words("a hundred and fifty dollars".split()), ["$150"])
        self.assertEqual(display_words("5 thousand dollars".split()), ["$5,000"])
        for kept in ("half a million dollars", "a few thousand dollars", "one two three", "twenty twenty four"):
            self.assertEqual(display_words(kept.split()), kept.split(), kept)
        words = [{"word": w, "start": i * .3, "end": i * .3 + .25}
                 for i, w in enumerate("I paid a hundred and fifty dollars for the tools.".split())]
        beat = {"idx": list(range(len(words))), "clauses": clauses(words, list(range(len(words))))}
        for target in (3, 5):  # "hundred" or "fifty": the phrase takes the whole amount
            self.assertIn("$150", phrase_around(words, beat, target)[1])

    def test_a_breath_or_a_lead_in_does_not_become_the_hook(self):
        from plan_reel import split_beats
        text = "Okay. What if you could build an app in ten minutes? I did it twice."
        words, _ = timed_words(text)
        words[4]["start"] += 1.0  # a one-second breath after "What if you"
        for w in words[4:]:
            w["pause_before"] = 0.0
        words[4]["pause_before"] = 1.0
        beats = [" ".join(words[i]["word"] for i in b) for b in split_beats(words)]
        self.assertEqual(beats[0], "Okay. What if you could build an app in ten minutes?")

    def test_timeline_style_overrides_reach_design_and_voice_band(self):
        from design import design_tokens
        from edit import voice_loudness
        self.assertEqual(design_tokens({}, style.load({"color": {"accent": "#ff6a00"}}))["accent"], "#ff6a00")
        with tempfile.TemporaryDirectory() as folder:
            clip = Path(folder) / "tone.mp4"
            source_video(clip, 2.0)  # a 170 Hz tone
            low = voice_loudness(clip, [{"start": 0, "end": 2}], phone=True, band=[60, 250])
            high = voice_loudness(clip, [{"start": 0, "end": 2}], phone=True, band=[1000, 4000])
            self.assertTrue(low is not None and (high is None or low > high + 10), (low, high))

    def test_style_overrides_are_type_checked(self):
        with self.assertRaisesRegex(ValueError, "must be an object"):
            style.load({"zones": 5})
        with self.assertRaisesRegex(ValueError, "must be a number"):
            style.load({"layout": {"fullscreen_max_share": "most"}})
        self.assertEqual(style.load({"sound": {"roles": {"type": "bubble_soft"}}})["sound"]["roles"]["type"], "bubble_soft")

    def test_a_cta_over_two_sentences_gives_one_keyword_graphic(self):
        with tempfile.TemporaryDirectory() as folder:
            (timeline, _), _ = self.plan(Path(folder), STORY_CLAIM.rsplit(" Comment", 1)[0]
                                         + " Comment LAUNCH below. And I'll send you the exact prompt.", "cta2")
            ids = [g["id"] for g in timeline["graphics"]]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(sum(1 for g in timeline["graphics"] if g["type"] == "cta"), 1)

    def test_graphics_stay_inside_a_reel_trimmed_at_the_last_word(self):
        from edit import build
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (timeline, plan), _ = self.plan(root, STORY_DEMO, "tight",
                                            segments=lambda words: [{"start": 0, "end": words[-1]["end"] + .02}])
            (root / "tight.timeline.json").write_text(json.dumps(timeline))
            receipt = build(str(root / "tight.timeline.json"), str(root / "tight-build"))
            for g in receipt["motion_report"]["graphics_meta"]:
                self.assertLessEqual(g["end"], receipt["duration"] + 1e-6, g["id"])
                if g["type"] == "hero":
                    self.assertGreaterEqual(g["end"] - g["start"], .9 - 1e-3, g["id"])

    def test_every_hook_gets_an_art_directed_moment_in_three_seconds(self):
        import review_reel
        from edit import build
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            text = ("What if your website could sell while you sleep? I checked every single email before it went out. "
                    "The whole thing runs on autopilot. Three clients signed in the first week. "
                    "Follow me for more builds like this one.")
            for seed in (3, 8, 21):
                (timeline, _), _ = self.plan(root, text, f"q{seed}", seed=seed)
                (root / f"q{seed}.timeline.json").write_text(json.dumps(timeline))
                build(str(root / f"q{seed}.timeline.json"), str(root / f"q{seed}-build"))
                result = review_reel.review(root / f"q{seed}-build")
                status = {c["check"]: c["status"] for c in result["checks"]}
                self.assertEqual(status["payoff_in_3s"], "pass", seed)
                self.assertEqual(status["first_motion"], "pass", seed)
                self.assertEqual([c for c in result["checks"] if c["status"] == "fail"], [], seed)

    def test_planned_paths_follow_the_timeline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            words, seconds = timed_words(STORY_CLAIM)
            source_video(root / "clip.mp4", seconds)
            (root / "words.json").write_text(json.dumps({"words": words}))
            (root / "draft.json").write_text(json.dumps({"title": "paths", "source": {"path": "clip.mp4"},
                                                         "words_path": "words.json"}))
            out = root / "elsewhere" / "planned.json"
            out.parent.mkdir()
            subprocess.run(["python3", str(HERE / "plan_reel.py"), "--draft", str(root / "draft.json"), "--out", str(out)],
                           check=True, capture_output=True)
            timeline = json.loads(out.read_text())
            self.assertTrue((out.parent / timeline["source"]["path"]).resolve().is_file())
            self.assertTrue((out.parent / timeline["words_path"]).resolve().is_file())

    def test_review_needs_a_build_or_a_video(self):
        import review_reel
        with self.assertRaises(ValueError):
            review_reel.review()

    def test_sound_budget_follows_the_spoken_words(self):
        words = [{"word": "w", "start": i * .8, "end": i * .8 + .3} for i in range(30)]
        events = [{"kind": "bubble", "at": 1 + i * 3.0, "source": f"g{i}", "role": "popup"} for i in range(8)]
        kept, dropped = sfx_kit.plan(events, 25, words=words)
        self.assertLessEqual(len(kept), max(2, int(30 * style.load()["sound"]["max_per_word"])))
        self.assertTrue(any("budget" in d["reason"] for d in dropped))
        self.assertEqual(sfx_kit.priority({"kind": "bubble", "at": 9, "source": "shot-3-highlight-0"}), 3)
        self.assertEqual(sfx_kit.priority({"kind": "whoosh", "at": 9, "source": "shot-3"}), 1)

    def test_components_register_in_either_import_order(self):
        for order in ("import motion_kit, components", "import components, motion_kit"):
            subprocess.run(["python3", "-c", f"{order}; assert {{'hero', 'tag', 'reveal', 'particles'}} <= set(components.COMPONENTS)"],
                           cwd=HERE, check=True, capture_output=True)

    def test_a_short_card_lands_before_it_leaves(self):
        words = [{"word": w, "start": .2 + i * .15, "end": .3 + i * .15} for i, w in enumerate("big news today".split())]
        c = Ctx(Scale(720, 1280), dict(DEFAULT_DESIGN), FEELS["snap"], CueResolver(words, 3, 30), 720, 1280, 30, 3,
                media=lambda value: f"assets/{value}")
        _, anims, _ = render_graphics([{"id": "c", "type": "hero", "variant": "card", "text": "Big news today",
                                        "accent_words": ["news"], "start": .2, "end": .7}], c)
        js = "".join(anims)
        enter = re.search(r'tl\.fromTo\("#c-card",\{[^}]*\},\{[^}]*duration:([\d.]+)[^}]*\},([\d.]+)\)', js)
        leave = re.search(r'tl\.to\("#c-card",\{[^}]*\},([\d.]+)\)', js)
        self.assertLessEqual(float(enter[2]) + float(enter[1]), float(leave[1]) + 1e-6)

    def test_planned_hero_type_fits_at_the_house_size(self):
        from motion_kit import fit_size, hero_line_scales
        with tempfile.TemporaryDirectory() as folder:
            (timeline, _), _ = self.plan(Path(folder), STORY_DEMO, "fit")
            floor = style.load()["type"]["hero_px"]["min"]
            for g in timeline["graphics"]:
                if g["type"] == "hero" and g["variant"] != "card":
                    size = fit_size(g["lines"], 136, 1080 * .8, 84, hero_line_scales(g["variant"], g["lines"]))
                    self.assertGreaterEqual(size, floor, g)


class ProofGateRemovalTests(unittest.TestCase):
    """Brandon's narration is authoritative: no rule may require visible proof before a claim is used."""

    def test_review_failure_codes_do_not_gate_on_evidence(self):
        schema = json.loads((ROOT / "production/editorial-map.schema.json").read_text())
        codes = schema["$defs"]["failureCode"]["enum"]
        for code in ("contradictory_evidence", "false_product_proof", "unsupported_visual_claim"):
            self.assertNotIn(code, codes)

    def test_instructions_do_not_ask_for_proof(self):
        gates = [r"narrow (the )?claim", r"evidence gap", r"stronger proof", r"cannot promote a draft",
                 r"only if one was observed", r"phrase the claim as documented", r"does not prove a new tool", r"does not prove four",
                 r"interaction proof", r"proof opportunit", r"not proof of app"]
        for folder in ("skill/references", "plugins/brandon-reel-engine/references", "plugins/brandon-reel-engine/skills"):
            for path in (ROOT / folder).rglob("*.md"):
                text = path.read_text()
                for pattern in gates:
                    self.assertIsNone(re.search(pattern, text, re.I), f"{path.relative_to(ROOT)}: {pattern}")


if __name__ == "__main__":
    unittest.main()
