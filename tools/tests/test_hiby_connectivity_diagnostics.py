from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'tools/diagnostics/hiby_r1_connectivity'
CENTRAL = Path('D:/work' if Path('D:/').is_dir() else 'C:/work') if sys.platform == 'win32' else Path('/mnt/d/work')
AREA = CENTRAL / 'Workspace/rockbox/r1-empty-radio-20261017/radio-diagnostics'
TESTS = AREA / 'tests'
FIXTURE_ARCHIVE = (CENTRAL / 'Snapshots/rockbox/connectivity-diagnostics-fixture-r34-alpha9-20261017' /
                   'rockbox-hibyr1-espeak-r34-alpha9-20261017-hardware-test.zip')
FIXTURE_SHA256 = '5ff3a5767695e7750ee74792ecd802da9c80399ca2d50478816967e36a1fcda3'
ALPHA8 = '7d82d50b88e0bfc3f0fe7bc6882843d047128d5504fc10bbdc72664119058390'
ALPHA9 = 'a536942c7cc6caa68c6dae24c2128e9d623562e2e26e7df10fdb51539684e122'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inventory(directory):
    return {path.relative_to(directory).as_posix(): digest(path)
            for path in directory.rglob('*') if path.is_file() and not path.is_symlink()}


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def linux_path(path):
    if sys.platform == 'win32':
        return '/mnt/' + path.drive[0].lower() + '/' + path.as_posix()[3:]
    return str(path)


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = TESTS / ('run-' + uuid.uuid4().hex)
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands = []
        cls.before = inventory(SOURCE)

    @classmethod
    def tearDownClass(cls):
        after = inventory(SOURCE)
        (cls.evidence / 'report.json').write_text(json.dumps(dict(
            created=datetime.now(timezone.utc).isoformat(), commands=cls.commands,
            inputs_before=cls.before, inputs_after=after, inputs_unchanged=after == cls.before,
            scope='Owned fake cards and sysfs/process fixtures only; no host radios, real card, profile or release writes',
            retained_copies='Script copies and synthetic data retained for reproducible regression evidence'), indent=2), encoding='utf-8')
        if after != cls.before:
            raise RuntimeError('Diagnostic sources changed during tests')

    def run_recorded(self, command, *, environment=None, input_text=None, timeout=30, expected=0):
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                env=environment, input=input_text, encoding='utf-8', errors='replace')
        self.commands.append(dict(test=self._testMethodName, command=command, exit_code=result.returncode,
                                  stdout=result.stdout, stderr=result.stderr))
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result


@unittest.skipUnless(sys.platform == 'win32' and shutil.which('powershell.exe'), 'Native Windows PowerShell 5.1 required')
class PowerShellDiagnosticsTests(EvidenceTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        archive_path = FIXTURE_ARCHIVE
        if not archive_path.is_file():
            raise RuntimeError('Required pinned alpha9 diagnostics fixture is missing: ' + str(archive_path))
        if digest(archive_path) != FIXTURE_SHA256:
            raise RuntimeError('Wrong pinned diagnostics fixture source')
        with zipfile.ZipFile(archive_path) as archive:
            cls.application = archive.read('.rockbox/rockbox.r1')
            cls.alsa = archive.read('.rockbox/libasound.so.2')

    def setUp(self):
        self.directory = self.evidence / self._testMethodName
        self.kit = self.directory / 'kit'
        self.card = self.directory / 'card'
        self.rockbox = self.card / '.rockbox'
        self.kit.mkdir(parents=True)
        self.rockbox.mkdir(parents=True)
        for name in ('Connectivity-diagnostics.ps1', 'launcher.sh'):
            shutil.copyfile(SOURCE / name, self.kit / name)
        (self.directory / 'fixture.txt').write_text('R1_CONNECTIVITY_ISOLATED_FIXTURE_V1', encoding='utf-8')
        (self.rockbox / 'rockbox.r1').write_bytes(self.application)
        (self.rockbox / 'libasound.so.2').write_bytes(self.alsa)
        (self.rockbox / 'rockbox-info.txt').write_text('Target: hibyr1\n', encoding='utf-8')
        for name in ('config.cfg', '.resume.cfg', 'rb_bl_mode.txt', 'rb_bt_on.txt', 'bookmarks.txt'):
            (self.rockbox / name).write_bytes(b'private-sentinel-no-copy-' + name.encode())
        self.environment = dict(os.environ, R1_CONNECTIVITY_TEST_FIXTURE=str(self.directory))

    def invoke(self, mode='Check', answer='', expected=0, commands=None, environment=None, card=None, language='en', menu=False):
        script = self.kit / 'Connectivity-diagnostics.ps1'
        if commands is None:
            invocation = ('& ' + quote(script) + ' -CardRoot ' + quote(card or self.card) +
                          ' -Language ' + quote(language))
            invocation += ' -Menu' if menu else ' -Mode ' + quote(mode)
            command = ['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                       '-Command', invocation]
        else:
            command = ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                       '. ' + quote(script) + ' -CardRoot ' + quote(card or self.card) + ' -Language en; '
                       'Initialize-Policy; $directory = Get-CardDirectory; ' + commands]
        command[-1] = '[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false); ' + command[-1]
        return self.run_recorded(command, environment=environment or self.environment, input_text=answer,
                                 expected=expected)

    def enable(self):
        return self.invoke('Enable', 'YES\n')

    def test_check_default_is_read_only_without_profile_collection(self):
        before = inventory(self.card)
        self.invoke()
        self.assertEqual(before, inventory(self.card))
        reports = list((self.kit / 'Reports').glob('*/report.json'))
        self.assertEqual(len(reports), 1)
        self.assertNotIn('private-sentinel', reports[0].read_text())

    def test_enable_restore_roundtrip_preserves_every_original_byte(self):
        before = inventory(self.card)
        self.enable()
        self.assertEqual((self.rockbox / 'rockbox.r1.connectivity-original').read_bytes(), self.application)
        self.assertEqual(digest(self.rockbox / 'rockbox.r1'), digest(SOURCE / 'launcher.sh'))
        (self.rockbox / 'r1-connectivity.log').write_text('passive log\n', encoding='utf-8')
        self.invoke('Collect')
        self.invoke('Restore', 'YES\n')
        self.assertEqual(before, inventory(self.card))
        self.assertEqual(len(list((self.kit / 'Reports').glob('*/launcher.sh'))), 1)
        self.assertEqual(len(list((self.kit / 'Reports').glob('*/r1-connectivity.log'))), 2)

    def test_enable_requires_exact_confirmation(self):
        before = inventory(self.card)
        self.invoke('Enable', 'yes\n', expected=1)
        self.assertEqual(before, inventory(self.card))

    def test_polish_confirmation_and_keyboard_menu(self):
        result = self.invoke(answer='\n', menu=True, language='pl')
        self.assertIn('1 Sprawdź (domyślnie); 2 Włącz; 3 Zbierz log; 4 Przywróć; 0 Wyjdź', result.stdout)
        self.assertIn('Numer i Enter; sam Enter = Sprawdź', result.stdout)
        result = self.invoke('Enable', 'tak\n', language='pl', expected=1)
        self.assertIn('Wpisz dokładnie TAK, aby zatwierdzić', result.stdout)
        self.assertEqual(result.stderr.strip(), 'Anulowano bez zmian')
        result = self.invoke('Enable', 'TAK\n', language='pl')
        self.assertIn('Oryginał przeniesiono na tej samej karcie.', result.stdout)
        self.assertIn('wyłącz go', result.stdout)
        result = self.invoke('Restore', 'TAK\n', language='pl')
        self.assertIn('Przywrócono oryginał.', result.stdout)

    def test_runtime_errors_follow_selected_language_without_bilingual_mixing(self):
        for language, expected_text, other_text in (
                ('pl', 'Nieznany wybór', 'Unknown selection'),
                ('en', 'Unknown selection', 'Nieznany wybór')):
            with self.subTest(language=language):
                result = self.invoke(answer='9\n', menu=True, language=language, expected=1)
                self.assertEqual(result.stderr.strip(), expected_text)
                self.assertNotIn(other_text, result.stderr)
                self.assertNotIn('\ufffd', result.stdout + result.stderr)
        (self.rockbox / 'r1-audio-launcher.log').write_bytes(b'owned prior diagnostic marker')
        for language, answer, expected_text, other_text in (
                ('pl', 'TAK\n', 'Wykryto diagnostykę audio.', 'Audio diagnostics detected.'),
                ('en', 'YES\n', 'Audio diagnostics detected.', 'Wykryto diagnostykę audio.')):
            with self.subTest(language=language):
                result = self.invoke('Enable', answer, language=language, expected=1)
                self.assertIn(expected_text, result.stderr)
                self.assertNotIn(other_text, result.stderr)

    def test_unicode_kit_and_card_relocation_keep_reports_adjacent(self):
        relocated_kit = self.directory / 'kit-Zażółć gęślą jaźń'
        relocated_card = self.directory / 'card-Łódź'
        self.kit.rename(relocated_kit)
        self.card.rename(relocated_card)
        self.kit = relocated_kit
        self.card = relocated_card
        self.rockbox = self.card / '.rockbox'
        self.environment.update(APPDATA=str(self.directory / 'forbidden-roaming'),
                                LOCALAPPDATA=str(self.directory / 'forbidden-local'))
        before = inventory(self.card)
        result = self.invoke(language='pl')
        self.assertIn(str(self.kit / 'Reports'), result.stdout)
        self.assertEqual(before, inventory(self.card))
        self.invoke('Enable', 'TAK\n', language='pl')
        (self.rockbox / 'r1-connectivity.log').write_text('owned passive Unicode relocation fixture\n', encoding='utf-8')
        self.invoke('Collect', language='pl')
        self.invoke('Restore', 'TAK\n', language='pl')
        self.assertEqual(before, inventory(self.card))
        reports = list((self.kit / 'Reports').glob('*/report.json'))
        self.assertEqual(len(reports), 3)
        for path in reports:
            report = json.loads(path.read_text(encoding='utf-8'))
            if 'card' in report:
                self.assertEqual(report['card'], str(self.rockbox))
        self.assertFalse((self.directory / 'forbidden-roaming').exists())
        self.assertFalse((self.directory / 'forbidden-local').exists())

    def test_unicode_missing_path_errors_are_localized(self):
        relocated_card = self.directory / 'card-Łódź'
        self.card.rename(relocated_card)
        self.card = relocated_card
        self.rockbox = self.card / '.rockbox'
        info = self.rockbox / 'rockbox-info.txt'
        info.rename(self.rockbox / 'saved-info.fixture')
        before = inventory(self.card)
        for language, expected_text in (('pl', 'Brak: '), ('en', 'Missing: ')):
            with self.subTest(language=language):
                result = self.invoke(language=language, expected=1)
                self.assertEqual(result.stderr.strip(), expected_text + str(info))
                self.assertNotIn('\ufffd', result.stderr)
        self.assertEqual(before, inventory(self.card))

    def test_platform_file_errors_use_selected_language(self):
        application = self.rockbox / 'rockbox.r1'
        application.rename(self.rockbox / 'saved-app.fixture')
        application.mkdir()
        before = inventory(self.card)
        for language, answer, expected_text, other_text in (
                ('pl', 'TAK\n', 'Brak uprawnień.', 'Access denied.'),
                ('en', 'YES\n', 'Access denied.', 'Brak uprawnień.')):
            with self.subTest(language=language):
                result = self.invoke('Enable', answer, language=language, expected=1)
                self.assertIn(expected_text, result.stderr)
                self.assertNotIn(other_text, result.stderr)
                self.assertNotIn('Exception calling', result.stderr)
        self.assertEqual(before, inventory(self.card))

    def test_polish_file_source_bom_prevents_ansi_mojibake(self):
        result = self.invoke(answer='0\n', menu=True, language='pl')
        expected_text = '1 Sprawdź (domyślnie); 2 Włącz'
        self.assertIn(expected_text, result.stdout)
        probe = self.run_recorded(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                                  '-Command', '[Text.Encoding]::Default.CodePage'])
        if probe.stdout.strip() != '65001':
            script = self.kit / 'Connectivity-diagnostics.ps1'
            script.write_bytes(script.read_bytes().removeprefix(b'\xef\xbb\xbf'))
            broken = self.invoke(answer='0\n', menu=True, language='pl', expected=1)
            self.assertNotIn(expected_text, broken.stdout)

    def test_repeat_enable_refuses(self):
        self.enable()
        before = inventory(self.card)
        self.invoke('Enable', 'YES\n', expected=1)
        self.assertEqual(before, inventory(self.card))

    def test_active_audio_original_trace_and_logs_refuse_enable_but_allow_check(self):
        for name in ('rockbox.r1.audio-original', 'r1-audio-trace.so', 'r1-audio-launcher.log', 'rockbox.r1.audio-new'):
            with self.subTest(name=name):
                path = self.rockbox / name
                path.write_bytes(b'old audio diagnostics')
                before = inventory(self.card)
                result = self.invoke('Enable', 'YES\n', expected=1)
                self.assertIn('matched alpha8 audio kit', result.stderr)
                self.invoke()
                self.assertEqual(before, inventory(self.card))
                path.unlink()

    def test_unknown_application_runtime_and_target_refuse(self):
        for name, bad, original in (
                ('rockbox.r1', b'unknown application', self.application),
                ('libasound.so.2', b'unknown runtime', self.alsa),
                ('rockbox-info.txt', b'Target: sansaclipzip\n', b'Target: hibyr1\n')):
            with self.subTest(name=name):
                path = self.rockbox / name
                path.write_bytes(bad)
                before = inventory(self.card)
                self.invoke('Enable', 'YES\n', expected=1)
                self.assertEqual(before, inventory(self.card))
                path.write_bytes(original)

    def test_existing_stage_state_original_or_log_never_overwritten(self):
        for name in ('.connectivity-stage', '.connectivity-state.json', 'rockbox.r1.connectivity-original', 'r1-connectivity.log'):
            with self.subTest(name=name):
                path = self.rockbox / name
                path.write_bytes(b'unknown existing file')
                before = inventory(self.card)
                self.invoke('Enable', 'YES\n', expected=1)
                self.assertEqual(before, inventory(self.card))
                path.unlink()

    def test_tampered_kit_refuses_before_card_writes(self):
        (self.kit / 'launcher.sh').write_bytes(b'tampered script')
        before = inventory(self.card)
        self.invoke('Enable', 'YES\n', expected=1)
        self.assertEqual(before, inventory(self.card))

    def test_changed_launcher_original_or_runtime_blocks_restore(self):
        self.enable()
        for name in ('rockbox.r1', 'rockbox.r1.connectivity-original', 'libasound.so.2', '.connectivity-state.json'):
            with self.subTest(name=name):
                path = self.rockbox / name
                original = path.read_bytes()
                path.write_bytes(b'unexpected changes')
                before = inventory(self.card)
                self.invoke('Restore', 'YES\n', expected=1)
                self.assertEqual(before, inventory(self.card))
                path.write_bytes(original)

    def test_new_runtime_file_blocks_restore(self):
        self.enable()
        (self.rockbox / 'extra.so').write_bytes(b'new runtime')
        before = inventory(self.card)
        self.invoke('Restore', 'YES\n', expected=1)
        self.assertEqual(before, inventory(self.card))

    def test_oversized_log_refuses_collection_and_restore(self):
        self.enable()
        (self.rockbox / 'r1-connectivity.log').write_bytes(bytes(65537))
        before = inventory(self.card)
        self.invoke('Collect', expected=1)
        self.invoke('Restore', 'YES\n', expected=1)
        self.assertEqual(before, inventory(self.card))

    def test_maximum_log_collected_exactly_without_card_mutation(self):
        self.enable()
        log = self.rockbox / 'r1-connectivity.log'
        log.write_bytes(b'R' * 65536)
        before = inventory(self.card)
        self.invoke('Collect')
        copied = list((self.kit / 'Reports').glob('*/r1-connectivity.log'))
        self.assertEqual([digest(path) for path in copied], [digest(log)])
        self.assertEqual(before, inventory(self.card))

    def test_enable_move_failures_roll_back(self):
        before = inventory(self.card)
        for failure in (1, 2):
            with self.subTest(failure=failure):
                self.invoke(commands=r'''
$script:MoveCount = 0
$originalMove = ${function:Move-CheckedItem}
function Move-CheckedItem($Source, $Destination, $Digest) {
    $script:MoveCount++
    if ($script:MoveCount -eq FAILURE) { throw 'injected move failure' }
    & $originalMove $Source $Destination $Digest
}
try { Enable-Card $directory; exit 3 } catch { exit 0 }
'''.replace('FAILURE', str(failure)))
                self.assertEqual(before, inventory(self.card))

    def test_restore_move_failures_roll_back_including_log_and_state(self):
        self.enable()
        (self.rockbox / 'r1-connectivity.log').write_bytes(b'passive fixture log')
        before = inventory(self.card)
        for failure in (1, 2, 3, 4):
            with self.subTest(failure=failure):
                self.invoke(commands=r'''
$script:MoveCount = 0
$originalMove = ${function:Move-CheckedItem}
function Move-CheckedItem($Source, $Destination, $Digest) {
    $script:MoveCount++
    if ($script:MoveCount -eq FAILURE) { throw 'injected restore failure' }
    & $originalMove $Source $Destination $Digest
}
try { Restore-Card $directory; exit 3 } catch { exit 0 }
'''.replace('FAILURE', str(failure)))
                self.assertEqual(before, inventory(self.card))

    def test_restore_post_move_failure_rolls_back_last_move(self):
        self.enable()
        before = inventory(self.card)
        self.invoke(commands=r'''
$script:MoveCount = 0
$originalMove = ${function:Move-CheckedItem}
function Move-CheckedItem($Source, $Destination, $Digest) {
    $script:MoveCount++
    & $originalMove $Source $Destination $Digest
    if ($script:MoveCount -eq 2) { throw 'injected post-move failure' }
}
try { Restore-Card $directory; exit 3 } catch { exit 0 }
''')
        self.assertEqual(before, inventory(self.card))

    def test_restore_recovers_interrupted_activation_both_sides_of_original_move(self):
        before = inventory(self.card)
        self.enable()
        (self.rockbox / 'rockbox.r1').rename(self.rockbox / '.connectivity-stage')
        self.invoke('Restore', 'YES\n')
        self.assertEqual(before, inventory(self.card))
        self.enable()
        (self.rockbox / 'rockbox.r1').rename(self.rockbox / '.connectivity-stage')
        (self.rockbox / 'rockbox.r1.connectivity-original').rename(self.rockbox / 'rockbox.r1')
        self.invoke('Restore', 'YES\n')
        self.assertEqual(before, inventory(self.card))

    def test_fixture_policy_rejects_parent_child_unc_and_unmarked_paths(self):
        for invalid in (self.card.parent, self.rockbox, str(self.card) + '\\..', '\\\\localhost\\invalid'):
            with self.subTest(invalid=str(invalid)):
                self.invoke(card=invalid, expected=1)
        (self.directory / 'fixture.txt').write_text('invalid fixture', encoding='utf-8')
        self.invoke(expected=1)

    def test_production_policy_rejects_fixture_directory_without_seam(self):
        environment = dict(self.environment)
        environment.pop('R1_CONNECTIVITY_TEST_FIXTURE')
        self.invoke(environment=environment, expected=1)

    def test_junction_card_and_reports_are_rejected(self):
        for name in ('cardlink', 'Reports'):
            with self.subTest(name=name):
                target = self.kit / name
                self.run_recorded(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                                   'New-Item -ItemType Junction -Path ' + quote(target) + ' -Target ' + quote(self.card) + ' | Out-Null'])
                if name == 'Reports':
                    before = inventory(self.card)
                    self.invoke(expected=1)
                    self.assertEqual(before, inventory(self.card))
                else:
                    self.invoke(commands='Assert-PlainPath ' + quote(target), expected=1)

    def test_rockbox_junction_rejected_before_reading_application(self):
        relocated = self.card / 'real-directory'
        self.rockbox.rename(relocated)
        self.run_recorded(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                           'New-Item -ItemType Junction -Path ' + quote(self.rockbox) + ' -Target ' + quote(relocated) + ' | Out-Null'])
        self.invoke(expected=1)


@unittest.skipUnless(shutil.which('wsl.exe') if sys.platform == 'win32' else shutil.which('sh'), 'POSIX shell required')
class LauncherDiagnosticsTests(EvidenceTests):
    def setUp(self):
        self.directory = self.evidence / self._testMethodName
        self.directory.mkdir()
        self.card = self.directory / 'card'
        self.card.mkdir()
        self.system = self.directory / 'system'
        self.system.mkdir()
        self.temporary = self.directory / 'tmp'
        self.temporary.mkdir()
        self.original = self.card / 'rockbox.r1.connectivity-original'
        self.original.write_text('#!/bin/sh\nprintf "original-app:%s:%s\\n" "$1" "$LD_LIBRARY_PATH"\nexit 23\n', encoding='utf-8', newline='\n')
        self.utility = self.directory / 'busybox-fake'
        shutil.copyfile(ROOT / 'tools/tests/fixtures/hiby_connectivity_diagnostic_utility.py', self.utility)
        self.launcher = self.directory / 'launcher.sh'

    def create(self, name, content):
        name = name.replace('mmc0:0001:1', 'mmc0_0001_1').replace('mmc0:0001:2', 'mmc0_0001_2')
        path = self.system / name.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')

    def invoke_launcher(self, expected=23, fail=None):
        text = (SOURCE / 'launcher.sh').read_text(encoding='utf-8')
        substitutions = {
            'directory=/data/mnt/sd_0/.rockbox': 'directory=' + quote(linux_path(self.card)),
            'systemroot=': 'systemroot=' + quote(linux_path(self.system)),
            'temporary=/tmp': 'temporary=' + quote(linux_path(self.temporary)),
            'utility=/bin/busybox': 'utility=' + quote(linux_path(self.utility)),
            'controller=/usr/bin/bluetoothctl': 'controller=' + quote(linux_path(self.directory / 'controller-fake')),
            ALPHA8: digest(self.original),
            'mmc0:0001:1': 'mmc0_0001_1',
            'mmc0:0001:2': 'mmc0_0001_2',
        }
        for original, replacement in substitutions.items():
            self.assertEqual(text.count(original), 1)
            text = text.replace(original, replacement)
        self.launcher.write_text(text, encoding='utf-8', newline='\n')
        prefix = ['wsl.exe', '--exec'] if sys.platform == 'win32' else []
        self.run_recorded(prefix + ['chmod', '700', linux_path(self.utility)])
        command = prefix + ['env', 'R1_FAKE_ROOT=' + linux_path(self.directory),
                            'R1_FAKE_FAIL=' + (fail or ''), 'sh', linux_path(self.launcher), 'fixture-argument']
        return self.run_recorded(command, expected=expected)

    def test_passive_snapshot_exact_sources_and_original_tmp_execution(self):
        for index, kind in ((4, 'bluetooth'), (7, 'wlan')):
            for field, value in (('type', kind), ('name', 'fixture-radio'), ('soft', '1'), ('hard', '0'), ('state', '0')):
                self.create('/sys/class/rfkill/rfkill' + str(index) + '/' + field, value + '\n')
        for function in ('mmc0:0001:1', 'mmc0:0001:2'):
            for field, value in (('vendor', '0x02d0'), ('device', '0x4345'), ('class', '0x00')):
                self.create('/sys/bus/sdio/devices/' + function + '/' + field, value + '\n')
        self.create('/sys/class/net/wlan0/flags', '0x1002\n')
        self.create('/proc/1/comm', 'bluetoothd\n')
        self.create('/proc/2/comm', 'private-secret-process\n')
        self.create('/proc/3/comm', 'hciattach\n')
        self.create('/run/r1_wireless_type', 'fixture-combo\n')
        self.create('/dev/rfkill', '')
        links = {}
        for function in ('mmc0_0001_1', 'mmc0_0001_2'):
            base = linux_path(self.system) + '/sys/bus/sdio/devices/' + function
            links[base + '/driver'] = '/sys/bus/sdio/drivers/bcmsdh_sdmmc'
            links[base + '/driver/module'] = '/sys/module/cywdhd'
        (self.directory / 'links.json').write_text(json.dumps(links), encoding='utf-8')
        before = inventory(self.system)
        result = self.invoke_launcher()
        self.assertIn('original-app:fixture-argument:', result.stdout)
        self.assertEqual(before, inventory(self.system))
        log = (self.card / 'r1-connectivity.log').read_text()
        for required in ('rfkill4/type: bluetooth', 'rfkill7/type: wlan', 'mmc0_0001_2/device: 0x4345',
                         'wlan0/flags: 0x1002', 'wlan1 absent', 'running service: bluetoothd', 'running service: hciattach'):
            self.assertIn(required, log)
        self.assertIn('driver: /sys/bus/sdio/drivers/bcmsdh_sdmmc', log)
        self.assertIn('driver/module: /sys/module/cywdhd', log)
        self.assertNotIn('private-secret', log)
        self.assertLessEqual(len(log.encode()), 65536)
        commands = [json.loads(line) for line in (self.directory / 'commands.jsonl').read_text().splitlines()]
        self.assertFalse(any(command[0] in ('timeout', 'bluetoothctl', 'ifconfig', 'rfkill') for command in commands))
        self.assertEqual(len(list(self.temporary.glob('r1-connectivity.*/program'))), 1)

    def test_existing_log_never_overwritten_or_appended(self):
        log = self.card / 'r1-connectivity.log'
        log.write_bytes(b'first snapshot preserved')
        self.invoke_launcher()
        self.assertEqual(log.read_bytes(), b'first snapshot preserved')

    def test_missing_all_radios_still_runs_original(self):
        self.invoke_launcher()
        log = (self.card / 'r1-connectivity.log').read_text()
        self.assertIn('unavailable', log)
        self.assertIn('wlan0 absent', log)
        self.assertIn('rfkill entries inspected (maximum 16): 0', log)

    def test_copy_failure_cleans_private_tmp_without_touching_original(self):
        before = inventory(self.card)
        self.invoke_launcher(expected=73, fail='cp')
        self.assertEqual(before, inventory(self.card))
        self.assertEqual(list(self.temporary.iterdir()), [])

    def test_chmod_failure_cleans_private_tmp_without_touching_original(self):
        before = inventory(self.card)
        self.invoke_launcher(expected=74, fail='chmod')
        self.assertEqual(before, inventory(self.card))
        self.assertEqual(list(self.temporary.iterdir()), [])

    def test_exec_failure_cleans_private_tmp(self):
        self.original.write_bytes(b'#!/nonexistent-connectivity-test-interpreter\n')
        self.invoke_launcher(expected=127)
        self.assertEqual(list(self.temporary.iterdir()), [])

    def test_long_values_are_bounded_and_process_limit_is_fixed(self):
        self.create('/sys/class/rfkill/rfkill0/type', 'wlan' * 10000)
        self.create('/proc/1/comm', 'private-process' * 10000)
        self.invoke_launcher()
        self.assertLess((self.card / 'r1-connectivity.log').stat().st_size, 8192)

    def test_unknown_original_rejected_before_snapshot_or_staging(self):
        text = (SOURCE / 'launcher.sh').read_text()
        text = text.replace('directory=/data/mnt/sd_0/.rockbox', 'directory=' + quote(linux_path(self.card)))
        text = text.replace('utility=/bin/busybox', 'utility=' + quote(linux_path(self.utility)))
        self.launcher.write_text(text, encoding='utf-8', newline='\n')
        prefix = ['wsl.exe', '--exec'] if sys.platform == 'win32' else []
        self.run_recorded(prefix + ['chmod', '700', linux_path(self.utility)])
        self.run_recorded(prefix + ['env', 'R1_FAKE_ROOT=' + linux_path(self.directory), 'sh', linux_path(self.launcher)], expected=70)
        self.assertFalse((self.card / 'r1-connectivity.log').exists())
        self.assertEqual(list(self.temporary.iterdir()), [])

    def test_optional_show_only_uses_trusted_fake_timeout_and_show(self):
        controller = self.directory / 'controller-fake'
        controller.write_text('#!/bin/sh\nexit 99\n', encoding='utf-8', newline='\n')
        prefix = ['wsl.exe', '--exec'] if sys.platform == 'win32' else []
        self.run_recorded(prefix + ['chmod', '700', linux_path(controller)])
        self.invoke_launcher()
        log = (self.card / 'r1-connectivity.log').read_text()
        self.assertIn('Controller fixture-controller Powered: no', log)
        commands = [json.loads(line) for line in (self.directory / 'commands.jsonl').read_text().splitlines()]
        self.assertIn(['timeout', '-s', 'KILL', '3', linux_path(controller), 'show'], commands)

    def test_dev_rfkill_metadata_fallback_when_stat_unavailable(self):
        self.create('/dev/rfkill', '')
        self.invoke_launcher(fail='stat')
        log = (self.card / 'r1-connectivity.log').read_text()
        self.assertIn('numeric ls stat fallback: crw------- 1 0 0 10, 242', log)


@unittest.skipUnless(shutil.which('wsl.exe') if sys.platform == 'win32' else shutil.which('sh'), 'POSIX runtime required')
class VendorUtilityTests(EvidenceTests):
    def test_actual_vendor_busybox_help_and_bounded_private_dd(self):
        self.directory = self.evidence / self._testMethodName
        self.directory.mkdir()
        workspace = CENTRAL / 'Workspace/rockbox'
        qemu = workspace / 'toolchains/hiby-r1-20261010/host/usr/bin/qemu-mipsel-static'
        vendor = workspace / 'r1-device-release-20261014/vendor-runtime'
        rootfs = workspace / 'r1-device-release-20261014/rootfs.squashfs'
        if not qemu.exists() or not rootfs.exists():
            self.skipTest('Controlled vendor runtime unavailable')
        prefix = ['wsl.exe', '--exec'] if sys.platform == 'win32' else []
        extraction = subprocess.run(prefix + ['unsquashfs', '-cat', linux_path(rootfs), 'bin/busybox'], capture_output=True, timeout=30)
        self.assertEqual(extraction.returncode, 0, extraction.stderr.decode(errors='replace'))
        self.assertEqual(len(extraction.stdout), 887820)
        utility = self.directory / 'busybox'
        utility.write_bytes(extraction.stdout)
        self.commands.append(dict(test=self._testMethodName, operation='Single rootfs member streamed without whole filesystem extraction',
                                  member='bin/busybox', size=len(extraction.stdout), sha256=digest(utility)))
        resolver = self.directory / 'libresolv.so.2'
        extraction = subprocess.run(prefix + ['unsquashfs', '-cat', linux_path(rootfs), 'lib/libresolv-2.22.so'], capture_output=True, timeout=30)
        self.assertEqual(extraction.returncode, 0)
        self.assertEqual(len(extraction.stdout), 87852)
        resolver.write_bytes(extraction.stdout)
        self.commands.append(dict(test=self._testMethodName, operation='Only missing BusyBox loader dependency streamed',
                                  member='lib/libresolv-2.22.so', size=len(extraction.stdout), sha256=digest(resolver)))
        runtime = prefix + [linux_path(qemu), '-L', linux_path(vendor), linux_path(vendor / 'lib/ld.so.1'),
                            '--inhibit-cache', '--library-path', linux_path(self.directory) + ':' + linux_path(vendor / 'lib'), linux_path(utility)]
        help_result = self.run_recorded(runtime + ['dd', '--help'])
        self.assertIn('count=', help_result.stderr)
        self.assertIn('bs=', help_result.stderr)
        self.run_recorded(runtime + ['mktemp', '--help'])
        for applet in ('sha256sum', 'cp', 'chmod', 'rm', 'rmdir', 'readlink', 'ls'):
            self.run_recorded(runtime + [applet, '--help'])
        stat_result = self.run_recorded(runtime + ['stat', '--help'], expected=127)
        self.assertIn('stat: applet not found', stat_result.stderr)
        timeout_result = self.run_recorded(runtime + ['timeout', '--help'], expected=127)
        self.assertIn('timeout: applet not found', timeout_result.stderr)
        source = self.directory / 'input.fixture'
        output = self.directory / 'output.fixture'
        source.write_bytes(bytes(range(256)) * 400)
        output.write_bytes(b'')
        self.run_recorded(runtime + ['dd', 'if=' + linux_path(source), 'of=' + linux_path(output), 'bs=65536', 'count=1', 'conv=notrunc'])
        self.assertEqual(output.read_bytes(), source.read_bytes()[:65536])
        result = subprocess.run(runtime + ['dd', 'if=' + linux_path(source), 'bs=256', 'count=1'], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, bytes(range(256)))
        self.commands.append(dict(test=self._testMethodName, operation='Actual vendor dd bounded attribute-sized read',
                                  exit_code=result.returncode, bytes=len(result.stdout)))
        self.run_recorded(runtime + ['sh', '-n', linux_path(SOURCE / 'launcher.sh')])


class SourceContractTests(unittest.TestCase):
    def test_powershell_unicode_source_has_utf8_bom(self):
        content = (SOURCE / 'Connectivity-diagnostics.ps1').read_bytes()
        self.assertTrue(content.startswith(b'\xef\xbb\xbf'), 'PowerShell 5.1 Unicode literals require a BOM')
        decoded = content.decode('utf-8-sig')
        for label in ('Sprawdź', 'domyślnie', 'Włącz', 'Przywróć', 'Wyjdź', 'dokładnie', 'zatwierdzić'):
            self.assertIn(label, decoded)

    def test_known_published_hashes_and_launcher_binding(self):
        script = (SOURCE / 'Connectivity-diagnostics.ps1').read_text(encoding='utf-8-sig')
        launcher = (SOURCE / 'launcher.sh').read_text()
        for checksum in (ALPHA8, ALPHA9):
            self.assertIn(checksum, script)
            self.assertIn(checksum, launcher)
        self.assertIn('for function in mmc0:0001:1 mmc0:0001:2', launcher)
        self.assertIn("$script:LauncherHash = '" + digest(SOURCE / 'launcher.sh') + "'", script)
        self.assertIn("$Mode = 'Check'", script)
        for forbidden in ('wifi_up', 'wifi_down', 'power on', 'power off', 'scan on', 'pair ', 'connect ', 'LD_PRELOAD='):
            self.assertNotIn(forbidden, launcher)

    def test_alpha9_archive_streaming_hash_and_member_hash(self):
        archive_path = FIXTURE_ARCHIVE
        self.assertTrue(archive_path.is_file(), 'Required pinned alpha9 diagnostics fixture is missing')
        self.assertEqual(digest(archive_path), FIXTURE_SHA256)
        with zipfile.ZipFile(archive_path) as archive:
            with archive.open('.rockbox/rockbox.r1') as application:
                self.assertEqual(hashlib.file_digest(application, 'sha256').hexdigest(), ALPHA9)


if __name__ == '__main__':
    unittest.main(verbosity=2)
