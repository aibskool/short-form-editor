"""Opt-in native render regression for the stage layout and motion graphics.

Run from the repository root:
    RUN_HYPERFRAMES_INTEGRATION=1 python3 production/editor/test_stage_render.py -v

Checks decoded pixels from a real HyperFrames render: the presenter is clipped into
the lower band during a stage shot, the stage canvas shows above it, an accent
badge paints on its word cue, and the presenter returns full-frame afterwards.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H = 180, 320


def rgb_at(video, seconds, x, y):
    data = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(seconds), "-i", str(video),
                           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                          capture_output=True, check=True).stdout
    values = [data[((py * W + px) * 3):((py * W + px) * 3 + 3)] for py in range(y - 1, y + 2) for px in range(x - 1, x + 2)]
    return tuple(round(sum(v[c] for v in values) / len(values)) for c in range(3))


@unittest.skipUnless(os.environ.get("RUN_HYPERFRAMES_INTEGRATION") == "1",
                     "Set RUN_HYPERFRAMES_INTEGRATION=1 to render the stage fixture")
class StageRenderTests(unittest.TestCase):
    def test_stage_band_backdrop_badge_and_return(self):
        for tool in ("ffmpeg", "ffprobe"):
            self.assertIsNotNone(shutil.which(tool))
        with tempfile.TemporaryDirectory(prefix="reel-stage-") as folder:
            root = Path(folder)
            source = root / "red.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"color=c=red:size={W}x{H}:rate=30", "-t", "3", "-an", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", str(source)], check=True)
            words = [{"word": w, "start": .1 + i * .3, "end": .35 + i * .3} for i, w in enumerate("one two three four five six seven eight".split())]
            (root / "words.json").write_text(json.dumps(words))
            spec = {"source": {"path": str(source), "segments": [{"start": 0, "end": 3}]}, "words_path": "words.json",
                    "output": {"width": W, "height": H, "fps": 30}, "audio_policy": {"music_required": False},
                    "spoken_captions": {"style": "pop"},
                    "shots": [{"start": 0, "end": 1, "layout": "stage", "backdrop": "plain"},
                              {"start": 1, "end": 3, "layout": "presenter"}],
                    "graphics": [{"type": "badge", "start": "@three", "end": .95, "text": "#1", "x": 5, "y": 8, "w": 40,
                                  "variant": "accent", "size": 90, "float": False, "sfx": None}]}
            (root / "timeline.json").write_text(json.dumps(spec))
            project, output = root / "comp", root / "out.mp4"
            subprocess.run([sys.executable, str(HERE / "edit.py"), "build", "--spec", str(root / "timeline.json"),
                            "--project", str(project)], check=True, capture_output=True)
            subprocess.run([sys.executable, str(HERE / "edit.py"), "render", "--project", str(project), "--output",
                            str(output), "--quality", "standard", "--workers", "1"], check=True, capture_output=True)
            band = rgb_at(output, .85, W // 2, int(H * .9))
            canvas = rgb_at(output, .85, W // 2, int(H * .45))
            after = rgb_at(output, 2.5, W // 2, int(H * .45))
            observed = {"band": band, "canvas": canvas, "after": after}
            self.assertTrue(band[0] > 200 and band[1] < 60, f"presenter must fill the stage band: {observed}")
            self.assertTrue(max(canvas) < 40, f"stage canvas must show above the band: {observed}")
            self.assertTrue(after[0] > 200 and after[1] < 60, f"presenter must return full-frame: {observed}")
            # Sample the pill fill beside the "#1" glyphs (the text itself is dark ink).
            badge = rgb_at(output, .85, int(W * .175), int(H * .12))
            self.assertTrue(badge[1] > 150 and badge[0] < 140, f"accent badge must paint on cue: {badge}")
            before_cue = rgb_at(output, .3, int(W * .175), int(H * .12))
            self.assertTrue(before_cue[1] < 100, f"badge must not show before its word: {before_cue}")
            print(json.dumps({**observed, "badge": badge, "before_cue": before_cue}))


if __name__ == "__main__":
    unittest.main()
