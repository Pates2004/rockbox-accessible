import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('builder', ROOT / 'tools/build_espeak_simulator.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildGuardTests(unittest.TestCase):
    def check(self, running, target=r'D:\Rockbox\rockbox\installfiles\simwindows'):
        with patch.object(builder.subprocess, 'check_output', side_effect=[json.dumps(running), target]):
            builder.assert_windows_not_running(Path('/project/installfiles/simwindows'))

    def test_unrelated_simulator_is_not_stopped_or_blocking(self):
        self.check(r'D:\simwindows\rockboxui.exe')

    def test_exact_running_executable_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Close the native simulator'):
            self.check(r'D:\Rockbox\rockbox\Workspace\rockboxui.exe',
                       r'D:\Rockbox\rockbox\Workspace\rockboxui.exe')

    def test_case_insensitive_descendant_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Close the native simulator'):
            self.check([r'D:\simwindows\rockboxui.exe',
                        r'd:\ROCKBOX\rockbox\installfiles\SIMWINDOWS\rockboxui.exe'])

    def test_sibling_with_same_prefix_is_not_rejected(self):
        self.check(r'D:\Rockbox\rockbox\installfiles\simwindows-old\rockboxui.exe')

    def test_no_running_simulator(self):
        self.check([])

    def test_unknown_or_relative_path_fails_closed(self):
        for paths in ([None], [''], ['relative/rockboxui.exe'], 7):
            with self.subTest(paths=paths), self.assertRaises(RuntimeError):
                self.check(paths)
        with self.assertRaises(RuntimeError):
            self.check([], 'relative/simwindows')

    def test_process_inspection_failure_is_not_ignored(self):
        with patch.object(builder.subprocess, 'check_output', side_effect=subprocess.CalledProcessError(1, 'powershell')):
            with self.assertRaises(subprocess.CalledProcessError):
                builder.assert_windows_not_running(Path('/project/installfiles/simwindows'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
