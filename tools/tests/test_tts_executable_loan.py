from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from materials_fixtures import materials_resolver

import test_tts_recorder_gui as recorder


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


EVIDENCE = project_materials_root(recorder.ROOT) / 'executable-loan-tests'


class ExecutableLoanTests(unittest.TestCase):
    def setUp(self):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        self.area = EVIDENCE / (self._testMethodName + '-' + stamp)
        self.materials_root = materials_resolver(self.area / 'source', self.area / 'central')
        self.workspace = self.materials_root(recorder.ROOT)
        self.build = self.workspace / 'build'
        self.build.mkdir(parents=True)
        self.executable = self.build / 'rockboxui.exe'
        self.executable.write_bytes(b'Synthetic loan fixture, not an executable.\n')
        self.payload = self.executable.read_bytes()
        self.backend = SimpleNamespace(ensure_unused=mock.Mock())
        self.patches = [mock.patch.object(recorder, '_project_materials_root', side_effect=self.materials_root),
                        mock.patch.object(recorder, 'windows_backend', return_value=self.backend)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def loan(self, relative='phase/GUI/run'):
        results = self.workspace / relative
        results.mkdir(parents=True)
        runtime = results / 'fixture'
        runtime.mkdir()
        return recorder.ExecutableLoan(self.build, results, {}), runtime

    def test_nested_results_restore_original_identity_without_copying(self):
        original = self.executable.stat()
        loan, runtime = self.loan()
        loan.move_to(runtime)
        self.assertFalse(self.executable.exists())
        loan.restore(None)
        restored = self.executable.stat()
        self.assertEqual((restored.st_dev, restored.st_ino), (original.st_dev, original.st_ino))
        self.assertEqual(self.executable.read_bytes(), self.payload)
        self.assertFalse((runtime / 'rockboxui.exe').exists())
        self.assertTrue(loan.record['restored'])

    def test_flat_results_remain_compatible(self):
        loan, runtime = self.loan('suite/run')
        loan.move_to(runtime)
        loan.restore(None)
        self.assertEqual(self.executable.read_bytes(), self.payload)
        self.assertTrue(loan.record['restored'])

    def test_restore_refuses_a_live_owned_process(self):
        loan, runtime = self.loan()
        loan.move_to(runtime)
        with self.assertRaisesRegex(RuntimeError, 'process exits'):
            loan.restore(SimpleNamespace(poll=lambda: None))
        self.assertFalse(self.executable.exists())
        self.assertEqual((runtime / 'rockboxui.exe').read_bytes(), self.payload)
        loan.restore(None)

    def test_restore_never_overwrites_an_occupied_destination(self):
        loan, runtime = self.loan()
        loan.move_to(runtime)
        self.executable.write_bytes(b'New file at occupied path')
        with self.assertRaisesRegex(RuntimeError, 'occupied'):
            loan.restore(None)
        self.assertEqual(self.executable.read_bytes(), b'New file at occupied path')
        self.assertEqual((runtime / 'rockboxui.exe').read_bytes(), self.payload)

    def test_changed_borrowed_content_is_not_restored(self):
        loan, runtime = self.loan()
        loan.move_to(runtime)
        (runtime / 'rockboxui.exe').write_bytes(b'Modified borrowed file')
        with self.assertRaisesRegex(RuntimeError, 'hash changed'):
            loan.restore(None)
        self.assertFalse(self.executable.exists())

    def test_both_build_and_results_must_stay_in_workspace(self):
        outside = self.area / 'outside'
        outside.mkdir()
        results = self.workspace / 'phase/run'
        results.mkdir(parents=True)
        for build, evidence in ((outside, results), (self.build, outside)):
            with self.subTest(build=build, evidence=evidence), self.assertRaises(RuntimeError):
                recorder.ExecutableLoan(build, evidence, {})

    def test_snapshot_and_release_categories_cannot_be_used_for_loans(self):
        results = self.workspace / 'phase/run'
        results.mkdir(parents=True)
        for category in ('Snapshots', 'installfiles'):
            outside = self.materials_root(recorder.ROOT, category) / 'build'
            outside.mkdir(parents=True)
            for build, evidence in ((outside, results), (self.build, outside)):
                with self.subTest(category=category, build=build, evidence=evidence), self.assertRaises(RuntimeError):
                    recorder.ExecutableLoan(build, evidence, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
