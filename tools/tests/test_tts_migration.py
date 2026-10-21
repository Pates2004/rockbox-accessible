import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from materials_fixtures import materials_resolver


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('migration', ROOT / 'tools/migrate_espeak_simulator.py')
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        workspace = _project_materials_root(ROOT) / 'migration-tests'
        workspace.mkdir(parents=True, exist_ok=True)
        self.fixture = tempfile.TemporaryDirectory(dir=workspace)
        fixture = Path(self.fixture.name).resolve()
        self.root = fixture / 'source'
        self.root.mkdir()
        self.materials_root = materials_resolver(self.root, fixture / 'materials')
        self.materials = self.materials_root(self.root)
        for owner, attribute, value in ((migration, 'ROOT', self.root),
                                        (migration, '_project_materials_root', self.materials_root)):
            patcher = mock.patch.object(owner, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.previous = self.materials_root(self.root, 'Snapshots') / 'previous'
        self.release = self.materials_root(self.root, 'installfiles') / 'simwindows'
        for package in (self.previous, self.release):
            disk = package / 'simdisk/.rockbox'
            disk.mkdir(parents=True)
            (disk / 'config.cfg').write_text('tts language: system\ntts rate: 175\n')
            (disk / 'polski.lng').write_text('catalog')
            manifest = {path.relative_to(package).as_posix(): migration.digest(path)
                        for path in package.rglob('*') if path.is_file()}
            (package / 'manifest.json').write_text(json.dumps({'files': manifest}))

    def tearDown(self):
        self.fixture.cleanup()

    def test_pristine_assets_are_not_duplicated(self):
        self.assertEqual(migration.migration_plan(self.previous, self.release), [])

    def test_pending_sparse_config_is_authoritative(self):
        pending = self.previous / 'simdisk/.rockbox/config.cfg.new'
        pending.write_text('tts rate: 450\nvolume: 0\n')
        plan = migration.migration_plan(self.previous, self.release)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][0], pending)
        self.assertEqual(plan[0][1], self.release / 'simdisk/.rockbox/config.cfg')

    def test_pending_resume_replaces_only_old_resume(self):
        (self.previous / 'simdisk/.rockbox/.resume.cfg').write_text('volume: -25\n')
        (self.previous / 'simdisk/.rockbox/.resume.cfg.new').write_text('volume: -1\n')
        plan = migration.migration_plan(self.previous, self.release)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][1].name, '.resume.cfg')

    def test_user_files_survive_with_exact_bytes(self):
        document = self.previous / 'simdisk/reading.txt'
        document.write_bytes(b'User text\n')
        migration.migrate(self.previous, self.release)
        self.assertEqual((self.release / 'simdisk/reading.txt').read_bytes(), document.read_bytes())
        self.assertTrue(document.exists())

    def test_changed_runtime_asset_is_not_silently_overwritten(self):
        (self.previous / 'simdisk/.rockbox/polski.lng').write_text('custom catalog')
        with self.assertRaisesRegex(RuntimeError, 'conflicts'):
            migration.migration_plan(self.previous, self.release)

    def test_new_user_profile_is_not_replaced(self):
        (self.previous / 'simdisk/.rockbox/config.cfg.new').write_text('tts rate: 450\n')
        (self.release / 'simdisk/.rockbox/config.cfg').write_text('tts rate: 200\n')
        with self.assertRaisesRegex(RuntimeError, 'already modified'):
            migration.migration_plan(self.previous, self.release)

    def test_non_snapshot_source_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Unsafe user-data migration path'):
            migration.migration_plan(self.release, self.release)


if __name__ == '__main__':
    unittest.main()
