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

    def test_pauses_keep_room_tone(self):
        for plan in self.plans.values():
            voice = voice_from_spans(plan["spec"]["source"], plan["spans"])
            gaps = measure_gaps(voice)
            self.assertLessEqual(gaps["lead"], 0.12)
            self.assertGreaterEqual(gaps["tail"], 0.04)
            self.assertLessEqual(gaps["tail"], 0.15)
            if gaps.get("max") is not None:
                self.assertLessEqual(gaps["max"], 700)
                self.assertGreaterEqual(gaps["p90"], 180)
            silent = [s for s in plan["spans"] if s.src is None]
            self.assertTrue(silent)
            self.assertTrue(all(s.out > plan["duration"] - 0.12 for s in silent))

    def test_captions_are_short_phrases(self):
        self.assertEqual(CAPTION_BOTTOM, 1462)
        self.assertEqual(GREEN_HEX, "#42FF40")
        import numpy as np
        for plan in self.plans.values():
            phrases = plan["phrases"]
            idxs = [w["idx"] for ph in phrases for w in ph["words"]]
            self.assertEqual(idxs, list(range(len(plan["words"]))))
            for ph in phrases:
                self.assertGreaterEqual(len(ph["words"]), 1)
                self.assertLessEqual(len(ph["words"]), 6)
                self.assertTrue(ph["text"])
        plan = self.plans["07"]
        frame = np.array(Overlay(plan).frame(30))
        band = frame[1200:1760, 80:1000]
        white = (band[:, :, 3] > 200) & (band[:, :, :3].min(2) >= 230)
        ys, xs = np.where(white)
        self.assertEqual(int(ys.max() + 1200), 1462)
        height = int(ys.max() - ys.min() + 1)
        self.assertGreaterEqual(height, 60)
        self.assertLessEqual(height, 180)
        self.assertAlmostEqual((xs.min() + xs.max()) / 2 + 80, 540, delta=24)

    def test_cues_are_sparse(self):
        for plan in self.plans.values():
            cues = plan["cues"]
            per = len(cues) / plan["duration"] * 60
            self.assertLess(per, 20)
            self.assertGreaterEqual(len(cues), 4)
            self.assertFalse(any(c.role in ("tick", "thump", "shutter", "landing", "ding") for c in cues))
            self.assertLessEqual(sum(c.role == "negative" for c in cues), 1)
            self.assertLessEqual(sum(c.role == "impact" for c in cues), 1)
            self.assertFalse(any(str(c.trigger).startswith("icon-") or str(c.trigger).startswith("cta-") for c in cues))
            self.assertFalse(any(s.flash for s in plan["shots"]))
            self.assertTrue(all(s.push == 0 for s in plan["shots"]))
            scales = {round(s.scale, 2) for s in plan["shots"] if s.kind == "face"}
            self.assertTrue(scales <= {1.0, 1.12})

    def test_plan_lands_inside_the_qa_ranges(self):
        import numpy as np
        for plan in self.plans.values():
            shots = plan["shots"]
            dur = plan["duration"]
            durs = np.array([s.dur for s in shots])
            self.assertGreaterEqual(shots[1].t0, 1.0)
            self.assertLessEqual(shots[1].t0, 3.2)
            self.assertGreaterEqual(float(np.median(durs)), 1.0)
            self.assertLessEqual(float(np.median(durs)), 3.4)
            self.assertGreaterEqual(float(np.percentile(durs, 90)), 2.4)
            self.assertLessEqual(float(np.percentile(durs, 90)), 6.5)
            face = sum(s.dur for s in shots if s.kind == "face") / dur
            self.assertGreaterEqual(face, 0.50)
            self.assertLessEqual(face, 0.80)
            self.assertLessEqual(max(s.dur for s in shots if s.kind == "face"), 8.0)
            self.assertGreaterEqual(plan["title_off"], 4.5)
            self.assertLessEqual(plan["title_off"], 8.5)
            self.assertGreaterEqual(len(plan["green"]), 4)
            ratios = []
            for a, b in zip(shots, shots[1:]):
                if a.kind == "face" and b.kind == "face":
                    ratios.append(b.scale / a.scale)
            changed = [r for r in ratios if r >= 1.08 or r <= 1 / 1.08]
            self.assertGreaterEqual(len(changed) / len(ratios), 0.30)
            self.assertLessEqual(len(changed) / len(ratios), 0.90)

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
