"""Brandon short-form no-background-music validation.

Run unit-only validation with:
    python3 production/editor/test_music.py -v

Run the one-second HyperFrames integration render with:
    RUN_HYPERFRAMES_INTEGRATION=1 python3 production/editor/test_music.py -v
"""
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def command(args, cwd=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f"command failed: {args}\n{result.stderr[-3000:]}")
    return result.stdout


def decoded_rms(video, start, duration):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start),
         "-t", str(duration), "-i", str(video), "-vn", "-ac", "1",
         "-ar", "48000", "-f", "f32le", "pipe:1"],
        capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors="replace")[-3000:])
    samples = struct.unpack("<" + "f" * (len(result.stdout) // 4), result.stdout)
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


class MusicValidationTests(unittest.TestCase):
    def write_fixture(self, root, music=None, policy=None):
        source = root / "source.mp4"
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "color=c=black:size=160x280:rate=10",
                 "-t", "1", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)])
        spec = {
            "title": "music fixture",
            "source": {"path": str(source), "segments": [{"start": 0, "end": 1}]},
            "output": {"width": 160, "height": 280, "fps": 10},
            "shots": [{"start": 0, "end": 1, "layout": "presenter"}],
        }
        if music is not None:
            spec["music"] = music
        if policy is not None:
            spec["audio_policy"] = policy
        path = root / "timeline.json"
        path.write_text(json.dumps(spec))
        return path

    def tone(self, root):
        path = root / "tone.wav"
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                 "-t", "1", str(path)])
        return path

    def test_short_form_rejects_music_and_accepts_voice_only_policy(self):
        from edit import build
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            missing = self.write_fixture(root, policy={"music_required": True})
            with self.assertRaisesRegex(ValueError, "must not contain background music"):
                build(str(missing), str(root / "required-composition"))
            absent = self.write_fixture(root)
            with self.assertRaisesRegex(ValueError, "must be false"):
                build(str(absent), str(root / "unspecified-composition"))
            silent = self.write_fixture(root, policy={"music_required": False})
            receipt = build(str(silent), str(root / "voice-only"))
            self.assertEqual(receipt["music_count"], 0)
            self.assertNotIn('id="music-', (root / "voice-only/index.html").read_text())
            tone = self.tone(root)
            invalid = self.write_fixture(root, music=[{"path": str(tone), "start": 0, "end": 1}],
                                         policy={"music_required": False})
            with self.assertRaisesRegex(ValueError, "must not contain background music"):
                build(str(invalid), str(root / "music-composition"))


if __name__ == "__main__":
    unittest.main()
