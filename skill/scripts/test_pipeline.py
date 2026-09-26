"""Stage joins are checked without requiring story sources or corroboration."""
import json
import tempfile
import unittest
from pathlib import Path

import pipeline


class ResearchReadinessTests(unittest.TestCase):
    def test_story_title_is_ready_without_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            (run / "research").mkdir()
            (run / "research/story-bank.json").write_text(json.dumps({
                "stories": [{"id": "brandon-story", "title": "Brandon's stated purchase"}]
            }))
            report = pipeline.inspect(run)
            self.assertEqual(report["stages"]["research"]["status"], "ready")
            self.assertEqual(report["stages"]["research"]["blockers"], [])


if __name__ == "__main__":
    unittest.main()
