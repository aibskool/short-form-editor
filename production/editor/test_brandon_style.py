"""Planner checks for the Brandon preset. The Kallaway path is not involved."""
import unittest
from pathlib import Path

from brandon_style import (
    APPROVED, CAPTION_BOTTOM, GREEN_HEX, Overlay, find_word, measure_gaps,
    norm_word, plan_reel, voice_from_spans,
)


class BrandonPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans = {reel: plan_reel(reel) for reel in ("07", "09")}

    def test_these_reels_end_without_a_cta_card(self):
        for plan in self.plans.values():
            self.assertIsNone(plan["cta_t"])
            self.assertFalse(any(str(c.trigger).startswith("cta-") for c in plan["cues"]))
            kicker, hero = Overlay(plan).hero_at(plan["duration"] - 0.15)
            self.assertIsNone(hero)
            self.assertIsNone(kicker)

    def test_keywords_are_spoken_and_approved(self):
        for plan in self.plans.values():
            word = norm_word(plan["spec"]["keyword"])
            self.assertIn(word, APPROVED)
            spoken = {norm_word(w["word"]) for w in plan["words"]}
            self.assertIn(word, spoken)

    def test_voice_gaps_match_the_bible(self):
        for plan in self.plans.values():
            voice = voice_from_spans(plan["spec"]["source"], plan["spans"])
            gaps = measure_gaps(voice)
            self.assertGreaterEqual(gaps["median"], 60)
            self.assertLessEqual(gaps["median"], 90)
            self.assertLessEqual(gaps["p90"], 150)
            self.assertLessEqual(gaps["max"], 250)
            self.assertLessEqual(gaps["over150"], 0.11)
            self.assertLessEqual(gaps["lead"], 0.10)
            self.assertGreaterEqual(gaps["tail"], 0.05)
            self.assertLessEqual(gaps["tail"], 0.15)

    def test_caption_baseline_is_lifted_70px(self):
        self.assertEqual(CAPTION_BOTTOM, 1462)
        self.assertEqual(GREEN_HEX, "#42FF40")
        import numpy as np
        plan = self.plans["07"]
        frame = np.array(Overlay(plan).frame(30))
        band = frame[1300:1760, 180:900]
        white = (band[:, :, 3] > 200) & (band[:, :, :3].min(2) >= 230)
        ys, xs = np.where(white)
        self.assertEqual(int(ys.max() + 1300), 1462)
        self.assertEqual(int(ys.max() - ys.min() + 1), 65)
        self.assertAlmostEqual((xs.min() + xs.max()) / 2 + 180, 540, delta=8)

    def test_sfx_spacing_rules(self):
        for plan in self.plans.values():
            negatives = [c.t for c in plan["cues"] if c.role == "negative"]
            landings = [c.t for c in plan["cues"] if c.role == "landing"]
            for i, t in enumerate(negatives):
                for other in negatives[i + 1:]:
                    self.assertGreaterEqual(abs(other - t), 3.0)
                for land in landings:
                    self.assertGreaterEqual(abs(land - t), 0.40)
            ticks = sorted(c.t for c in plan["cues"] if c.role == "tick")
            rolls, roll = [], []
            for t in ticks:
                if roll and t - roll[-1] > 0.45:
                    rolls.append(roll)
                    roll = []
                roll.append(t)
            if roll:
                rolls.append(roll)
            for times in rolls:
                self.assertLessEqual(len(times), 12)
                for a, b in zip(times, times[1:]):
                    self.assertGreaterEqual(b - a, 0.099)

    def test_plan_lands_inside_the_qa_ranges(self):
        import numpy as np
        for plan in self.plans.values():
            shots = plan["shots"]
            dur = plan["duration"]
            durs = np.array([s.dur for s in shots])
            self.assertGreaterEqual(shots[1].t0, 1.3)
            self.assertLessEqual(shots[1].t0, 3.0)
            self.assertGreaterEqual(float(np.median(durs)), 1.2)
            self.assertLessEqual(float(np.median(durs)), 2.1)
            self.assertGreaterEqual(float(np.percentile(durs, 90)), 3.0)
            self.assertLessEqual(float(np.percentile(durs, 90)), 4.5)
            face = sum(s.dur for s in shots if s.kind == "face") / dur
            self.assertGreaterEqual(face, 0.58)
            self.assertLessEqual(face, 0.74)
            self.assertLessEqual(max(s.dur for s in shots if s.kind == "face"), 7.0)
            self.assertGreaterEqual(plan["title_off"], 4.5)
            self.assertLessEqual(plan["title_off"], 8.5)
            self.assertGreaterEqual(len(plan["green"]), 4)
            ratios = []
            for a, b in zip(shots, shots[1:]):
                if a.kind == "face" and b.kind == "face":
                    ratios.append(b.scale / a.scale)
            changed = [r for r in ratios if r >= 1.08 or r <= 1 / 1.08]
            self.assertGreaterEqual(len(changed) / len(ratios), 0.30)
            self.assertLessEqual(len(changed) / len(ratios), 0.75)

    def test_numbers_match_the_spoken_words(self):
        words = self.plans["07"]["words"]
        self.assertEqual(words[find_word(words, "7")]["word"], "7")
        self.assertEqual(words[find_word(words, "$2,000")]["word"], "$2,000")
        self.assertEqual(words[find_word(words, "$400")]["word"], "$400")
        words = self.plans["09"]["words"]
        self.assertEqual(norm_word(words[find_word(words, "fifteen")]["word"]), "fifteen")
        self.assertEqual(norm_word(words[find_word(words, "sites")]["word"]), "sites")

    def test_kallaway_preset_is_untouched(self):
        text = Path(__file__).with_name("talking_head.py").read_text()
        self.assertIn("attach_popout", text)
        brandon = Path(__file__).with_name("brandon_style.py").read_text()
        self.assertNotIn("attach_popout", brandon)
        self.assertNotIn("import kallaway", brandon)


if __name__ == "__main__":
    unittest.main()
