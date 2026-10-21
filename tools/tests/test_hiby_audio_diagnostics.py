from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'tools/diagnostics/hiby_r1_audio'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(sys.platform == 'win32' and shutil.which('powershell.exe'), 'Native Windows PowerShell is required')
class AudioDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = project_materials_root(ROOT) / 'hiby-audio-diagnostics-tests' / (
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.before = {path.name: digest(path) for path in SOURCE.iterdir() if path.is_file()}
        cls.commands = []

    @classmethod
    def tearDownClass(cls):
        after = {path.name: digest(path) for path in SOURCE.iterdir() if path.is_file()}
        (cls.evidence / 'report.json').write_text(json.dumps(dict(
            commands=cls.commands, inputs_before=cls.before, inputs_after=after,
            inputs_unchanged=cls.before == after, scope='Native PowerShell operations on owned fake card directories only'), indent=2), encoding='utf-8')
        if cls.before != after:
            raise RuntimeError('Diagnostic source changed during Windows tests')

    def setUp(self):
        self.directory = self.evidence / self._testMethodName
        self.kit = self.directory / 'kit'
        self.card = self.directory / 'card'
        self.rockbox = self.card / '.rockbox'
        self.kit.mkdir(parents=True)
        self.rockbox.mkdir(parents=True)
        shutil.copyfile(SOURCE / 'Audio-diagnostics.ps1', self.kit / 'Audio-diagnostics.ps1')
        (self.kit / 'r1-audio-trace.so').write_bytes(b'owned fixture library')
        (self.kit / 'launcher.sh').write_bytes(b'#!/bin/sh\nexit 99\n')
        (self.rockbox / 'rockbox.r1').write_bytes(b'owned native fixture application')
        (self.rockbox / 'libasound.so.2').write_bytes(b'owned native fixture ALSA')
        (self.rockbox / 'rockbox-info.txt').write_text('Target: hibyr1\n', encoding='utf-8')
        (self.rockbox / 'config.cfg').write_text('tts enabled: on\nvolume: -25\nwifi password: sensitive-sentinel-90713\n', encoding='utf-8')
        (self.rockbox / 'bookmarks.txt').write_bytes(b'preserve user bookmarks')
        self.manifest = dict(application_sha256=digest(self.rockbox / 'rockbox.r1'),
            alsa_sha256=digest(self.rockbox / 'libasound.so.2'), files={name: digest(self.kit / name)
                for name in ('Audio-diagnostics.ps1', 'r1-audio-trace.so', 'launcher.sh')})
        (self.kit / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def invoke(self, commands, expected=0):
        script = ". '{}'\n$kit = '{}'\n$card = '{}'\n$directory = Get-RockboxDirectory $card\n$manifest = Get-KitManifest $kit\n".format(
            str(self.kit / 'Audio-diagnostics.ps1').replace("'", "''"),
            str(self.kit).replace("'", "''"), str(self.card).replace("'", "''")) + commands
        command = ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script]
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.commands.append(dict(test=self._testMethodName, command=command,
            exit_code=result.returncode, stdout=result.stdout.decode(errors='replace'), stderr=result.stderr.decode(errors='replace')))
        self.assertEqual(result.returncode, expected, result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))

    def inventory(self):
        return {path.relative_to(self.card).as_posix(): digest(path) for path in self.card.rglob('*') if path.is_file()}

    def enable(self):
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest')

    def test_enable_moves_application_and_preserves_user_data(self):
        before = self.inventory()
        self.enable()
        after = self.inventory()
        self.assertEqual(after['.rockbox/rockbox.r1.audio-original'], before['.rockbox/rockbox.r1'])
        self.assertEqual(after['.rockbox/rockbox.r1'], self.manifest['files']['launcher.sh'])
        self.assertEqual(after['.rockbox/r1-audio-trace.so'], self.manifest['files']['r1-audio-trace.so'])
        for name, checksum in before.items():
            if name != '.rockbox/rockbox.r1':
                self.assertEqual(after[name], checksum)

    def test_repeat_enable_refuses_without_overwriting(self):
        self.enable()
        before = self.inventory()
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest', 1)
        self.assertEqual(before, self.inventory())

    def test_wrong_application_refuses_before_writes(self):
        (self.rockbox / 'rockbox.r1').write_bytes(b'different application')
        before = self.inventory()
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest', 1)
        self.assertEqual(before, self.inventory())

    def test_wrong_alsa_refuses_before_writes(self):
        (self.rockbox / 'libasound.so.2').write_bytes(b'different ALSA')
        before = self.inventory()
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest', 1)
        self.assertEqual(before, self.inventory())

    def test_existing_staging_file_is_preserved(self):
        (self.rockbox / 'rockbox.r1.audio-new').write_bytes(b'not installer data')
        before = self.inventory()
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest', 1)
        self.assertEqual(before, self.inventory())

    def test_existing_library_is_preserved(self):
        (self.rockbox / 'r1-audio-trace.so').write_bytes(b'not installer data')
        before = self.inventory()
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest', 1)
        self.assertEqual(before, self.inventory())

    def test_tampered_kit_refuses_before_writes(self):
        (self.kit / 'launcher.sh').write_bytes(b'tampered')
        before = self.inventory()
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest', 1)
        self.assertEqual(before, self.inventory())

    def test_other_player_is_rejected(self):
        (self.rockbox / 'rockbox-info.txt').write_text('Target: sansaclipzip\n', encoding='utf-8')
        before = self.inventory()
        self.invoke('Enable-AudioDiagnostics $directory $kit $manifest', 1)
        self.assertEqual(before, self.inventory())

    def test_check_is_read_only_and_filters_secrets(self):
        before = self.inventory()
        self.invoke('Save-CardReport $directory $kit $manifest $false | Out-Null')
        self.assertEqual(before, self.inventory())
        reports = list((self.kit / 'Reports').glob('*/report.json'))
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text(encoding='utf-8-sig')
        self.assertFalse('sensitive-sentinel-90713' in text, 'Sensitive configuration leaked')
        report = json.loads(text)
        self.assertTrue(report['application_matches'])
        self.assertEqual(report['settings']['config.cfg'], ['tts enabled: on', 'volume: -25'])
        self.assertLess(len(text), 4096)

    def test_collection_copies_logs_without_modifying_card(self):
        (self.rockbox / 'r1-audio-diagnostic.log').write_bytes(b'owned diagnostic log')
        before = self.inventory()
        self.invoke('Save-CardReport $directory $kit $manifest $true | Out-Null')
        self.assertEqual(before, self.inventory())
        logs = list((self.kit / 'Reports').glob('*/r1-audio-diagnostic.log'))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].read_bytes(), b'owned diagnostic log')

    def test_restore_moves_owned_diagnostics_and_preserves_settings(self):
        before = self.inventory()
        self.enable()
        (self.rockbox / 'r1-audio-diagnostic.log').write_bytes(b'owned diagnostic log')
        self.invoke('Restore-AudioDiagnostics $directory $kit $manifest | Out-Null')
        self.assertEqual(before, self.inventory())
        self.assertEqual(len(list((self.kit / 'Reports').glob('*/r1-audio-trace.so'))), 1)
        self.assertEqual(len(list((self.kit / 'Reports').glob('*/r1-audio-diagnostic.log'))), 1)

    def test_unknown_installed_launcher_cannot_be_restored_blindly(self):
        self.enable()
        (self.rockbox / 'rockbox.r1').write_bytes(b'unknown current program')
        before = self.inventory()
        self.invoke('Restore-AudioDiagnostics $directory $kit $manifest | Out-Null', 1)
        self.assertEqual(before, self.inventory())

    def test_failed_activation_restores_original_application(self):
        original = (self.rockbox / 'rockbox.r1').read_bytes()
        self.invoke(r'''
$script:MoveCount = 0
function Move-Item([string]$LiteralPath, [string]$Destination) {
    $script:MoveCount++
    if ($script:MoveCount -eq 2) { throw 'controlled move failure' }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination
}
try { Enable-AudioDiagnostics $directory $kit $manifest; exit 2 } catch { exit 0 }
''')
        self.assertEqual((self.rockbox / 'rockbox.r1').read_bytes(), original)
        self.assertFalse((self.rockbox / 'rockbox.r1.audio-original').exists())

    def test_failed_restore_keeps_existing_diagnostic_launcher(self):
        self.enable()
        before = self.inventory()
        self.invoke(r'''
$script:MoveCount = 0
function Move-Item([string]$LiteralPath, [string]$Destination) {
    $script:MoveCount++
    if ($script:MoveCount -eq 2) { throw 'controlled restore failure' }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination
}
try { Restore-AudioDiagnostics $directory $kit $manifest | Out-Null; exit 2 } catch { exit 0 }
''')
        self.assertEqual(before, self.inventory())


if __name__ == '__main__':
    unittest.main(verbosity=2)
