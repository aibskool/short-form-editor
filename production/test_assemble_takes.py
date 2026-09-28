"""Tests for assemble_takes.py: frame-aligned joins and words on the master clock.

python3 production/test_assemble_takes.py -v
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import assemble_takes


def clip(path, seconds, color):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:size=90x160:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000", "-t", str(seconds),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)


class AssembleTakesTests(unittest.TestCase):
    def test_joins_kept_ranges_and_moves_words_onto_the_master_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip(root / "A01.mov", 3, "red")
            clip(root / "A02.mov", 2, "blue")
            (root / "words").mkdir()
            (root / "words/A01.words.json").write_text(json.dumps({"words": [
                {"word": "cut", "start": 0.05, "end": 0.3},           # before the kept range: dropped
                {"word": "one", "start": 0.5, "end": 0.9},
                {"word": "long", "start": 1.7, "end": 2.4},           # starts inside, ASR end runs past the cut
                {"word": "late", "start": 2.62, "end": 2.9}]}))       # starts in cut time: dropped and listed
            (root / "words/A02.words.json").write_text(json.dumps({"words": [
                {"word": "two", "start": 0.36, "end": 0.7}]}))        # one ASR frame early: kept
            edl = {"output": {"width": 90, "height": 160, "fps": 30, "crf": 30},
                   "takes": [{"source": "A01.mov", "words": "words/A01.words.json", "keep": [[0.4, 1.0], [1.5, 2.0]]},
                             {"source": "A02.mov", "words": "words/A02.words.json", "keep": [[0.4, 1.2]]}]}
            (root / "edl.json").write_text(json.dumps(edl))
            receipt = assemble_takes.assemble(root / "edl.json", root / "master.mp4", root / "master.words.json",
                                              root / "master.map.json")
            self.assertAlmostEqual(receipt["duration"], 1.9, places=3)
            self.assertEqual([p["master_start"] for p in receipt["pieces"]], [0.0, 0.6, 1.1])
            words = {w["word"]: w for w in json.loads((root / "master.words.json").read_text())["words"]}
            self.assertEqual(sorted(words), ["long", "one", "two"])
            self.assertAlmostEqual(words["one"]["start"], 0.1, places=3)
            self.assertAlmostEqual(words["long"]["start"], 0.8, places=3)
            self.assertAlmostEqual(words["long"]["end"], 1.1, places=3)   # clamped to the cut
            self.assertAlmostEqual(words["two"]["start"], 1.1, places=3)
            self.assertEqual([d["word"] for d in receipt["dropped_words"]], ["cut", "late"])
            self.assertTrue((root / "master.map.json").is_file())
            with self.assertRaisesRegex(ValueError, "ordered"):
                edl["takes"][0]["keep"] = [[1.5, 2.0], [0.4, 1.0]]
                assemble_takes.plan(edl, root)


if __name__ == "__main__":
    unittest.main()
