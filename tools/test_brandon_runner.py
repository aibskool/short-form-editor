import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('brandon_runner',HERE/'plugins/brandon-reel-engine/scripts/reel.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ProjectResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in runner.REQUIRED:
            f=self.root/'checkout'/name
            f.parent.mkdir(parents=True,exist_ok=True)
            f.write_text('fixture')
        self.new=self.root/'new.json';self.old=self.root/'old.json'

    def test_new_saved_config_precedes_legacy_environment(self):
        self.new.write_text(json.dumps({'project_root':str(self.root/'checkout')}))
        with patch.object(runner,'CONFIG',self.new),patch.object(runner,'LEGACY_CONFIG',self.old),patch.dict(os.environ,{'SAMIN_REEL_PROJECT':'/wrong'},clear=True):
            project,basis=runner.resolve_project()
        self.assertEqual(project,self.root/'checkout')
        self.assertEqual(basis,'local_configuration')

    def test_conflicting_environment_and_config_are_reported(self):
        self.new.write_text(json.dumps({'project_root':str(self.root/'checkout')}))
        self.old.write_text(json.dumps({'project_root':'/wrong'}))
        with patch.object(runner,'CONFIG',self.new),patch.object(runner,'LEGACY_CONFIG',self.old),patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'disagree'):
                runner.resolve_project()
        with patch.dict(os.environ,{'BRANDON_REEL_PROJECT':str(self.root/'checkout'),
                                     'SAMIN_REEL_PROJECT':'/wrong'},clear=True):
            with self.assertRaisesRegex(ValueError,'different checkouts'):
                runner.resolve_project()


if __name__=='__main__': unittest.main()
