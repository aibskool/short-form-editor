import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('migrate', Path(__file__).with_name('migrate_brandon_config.py'))
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in migrate.REQUIRED:
            p=self.root/'checkout'/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('fixture')

    def test_project_config_is_dry_run_then_idempotent_and_old_file_stays(self):
        old=self.root/'old/project.json';new=self.root/'new/project.json'
        old.parent.mkdir()
        old.write_text(json.dumps({'project_root':str(self.root/'checkout')}))
        self.assertEqual(migrate.migrate_config(old,new,True)['status'],'would_create')
        self.assertFalse(new.exists())
        self.assertEqual(migrate.migrate_config(old,new)['status'],'created')
        self.assertEqual(migrate.migrate_config(old,new)['status'],'already_migrated')
        self.assertTrue(old.exists())
        new.write_text(json.dumps({'project_root':'/different'}))
        with self.assertRaisesRegex(ValueError,'conflicting'):
            migrate.migrate_config(old,new)

    def test_timeline_preserves_semantics_and_never_infers_editorial_graphics(self):
        old=self.root/'old.json';new=self.root/'new.json'
        data={'captions':{'phrases':[{'word_range':[0,2]}]},'labels':[{'text':'SOURCE'}],
              'output':{'split_fraction':.45},'audio_policy':{'music_required':True},
              'shots':[{'layout':'split','graphic':{'title':'Historical example'}}]}
        old.write_text(json.dumps(data))
        receipt=migrate.migrate_timeline(old,new)
        self.assertTrue(receipt['legacy_captions_converted'])
        self.assertFalse(receipt['editorial_graphics_inferred'])
        output=json.loads(new.read_text())
        self.assertEqual(output['spoken_captions'],data['captions'])
        self.assertNotIn('captions',output)
        self.assertNotIn('editorial_graphics',output)
        for key in ('labels','output','audio_policy','shots'):
            self.assertEqual(output[key],data[key])
        self.assertEqual(migrate.migrate_timeline(old,new)['status'],'already_migrated')
        with self.assertRaisesRegex(ValueError,'existing target differs'):
            new.write_text('{}');migrate.migrate_timeline(old,new)


if __name__=='__main__':
    unittest.main()
