import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from compare_style import create


class ComparisonTests(unittest.TestCase):
    def test_20_second_three_reference_review_remains_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / 'synthetic.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                            '-i', 'color=c=green:s=160x284:r=5:d=20', '-c:v', 'mpeg4',
                            str(candidate)], check=True)
            references = [(name, candidate, 2, 4, job) for name, job in
                          [('Astra', 'screen proof'), ('Photographer', 'opening'), ('GovDeals', 'CTA')]]
            with self.assertRaisesRegex(ValueError, 'three distinctly named'):
                create(candidate, references[:2], root / 'incomplete', fps=2)
            result = create(candidate, references, root / 'review', fps=2)
            self.assertEqual(result['status'], 'pending_human_review')
            self.assertEqual(len(result['frame_mapping']), 40)
            self.assertEqual(result['candidate_sha256'], hashlib.sha256(candidate.read_bytes()).hexdigest())
            self.assertEqual(len(result['clips']), 4)
            self.assertTrue((root / 'review/index.html').is_file())

    def test_shortened_calibration_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);candidate=root/'short.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi',
                            '-i','color=c=green:s=160x284:r=5:d=17','-c:v','mpeg4',str(candidate)],check=True)
            references=[(name,candidate,0,10,'visual job') for name in ('Astra','Photographer','GovDeals')]
            with self.assertRaisesRegex(ValueError,'must be 20 seconds'):
                create(candidate,references,root/'strict',fps=2)
            result=create(candidate,references,root/'tight',fps=2,allow_tightened=True)
            self.assertTrue(result['tightened_from_20s'])
            self.assertEqual(result['status'],'pending_human_review')


if __name__ == '__main__':
    unittest.main()
