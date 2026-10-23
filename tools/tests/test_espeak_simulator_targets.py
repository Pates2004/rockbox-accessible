import contextlib
import datetime
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

from materials_fixtures import materials_resolver

import test_tts_windows_package as validator


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('simulator_builder', ROOT / 'tools/build_espeak_simulator.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
EXPECTED_VERSIONS = {
    'sansaclipplus': {
        'windows': '0ed3734e5e-espeak-r29-win-alpha7-20261011',
        'linux': '0ed3734e5e-espeak-r29-alpha7-20261011',
    },
    'sansaclipzip': {
        'windows': '0ed3734e5e-espeak-r29-clipzip-win-alpha8-20261011',
        'linux': '0ed3734e5e-espeak-r29-clipzip-alpha8-20261011',
    },
    'hibyr1': {
        'windows': '0ed3734e5e-espeak-r34-hibyr1-win-alpha18-20261023',
        'linux': '0ed3734e5e-espeak-r34-hibyr1-alpha15-20261023',
    },
}


class SimulatorTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        cls.results = _project_materials_root(ROOT) / 'r1-screen-state-20261015/espeak-builder-tests/simulator' / timestamp
        cls.results.mkdir(parents=True)
        print(f'Synthetic packaging fixtures (not executable builds): {cls.results}', flush=True)

    def setUp(self):
        self.area = self.results / self._testMethodName
        self.root = self.area / 'source'
        self.root.mkdir(parents=True)
        self.materials_root = materials_resolver(self.root, self.area / 'materials')
        self.materials = self.materials_root(self.root)
        self.snapshots = self.materials_root(self.root, 'Snapshots')
        self.release_root = self.materials_root(self.root, 'installfiles')
        self.materials.mkdir(parents=True)
        self.source = self.root / 'engine'
        self.sdk = self.root / 'sdk/x86_64-w64-mingw32'
        for name in ('phondata', 'pl_dict'):
            self.write(self.source / 'espeak-data' / name, f'Synthetic data: {name}')
        for name in ('bin/sdl2-config', 'lib/libSDL2.a'):
            self.write(self.sdk / name, 'Synthetic SDK fixture')
        self.write(self.sdk.parent / 'LICENSE.txt', 'Synthetic SDL license')
        for name in ('ESPEAK-WINDOWS-PL.md', 'ESPEAK-WINDOWS.md', 'ESPEAK.md', 'ESPEAK-PL.md',
                     'ESPEAK-TARGETS.md', 'ESPEAK-TARGETS-PL.md', 'ESPEAK-CLIPPLUS.md', 'ESPEAK-CLIPPLUS-PL.md',
                     'ESPEAK-CLIPZIP.md', 'ESPEAK-CLIPZIP-PL.md',
                     'ESPEAK-HIBYR1.md', 'ESPEAK-HIBYR1-PL.md',
                     'HIBY-R1-CONTROLS.md', 'HIBY-R1-CONTROLS-PL.md',
                     'HIBY-R1-INSTALL.md', 'HIBY-R1-INSTALL-PL.md',
                     'ACCESSIBILITY-TOUCH.md', 'ACCESSIBILITY-TOUCH-PL.md',
                     'ACCESSIBILITY-BUTTONS.md', 'ACCESSIBILITY-BUTTONS-PL.md',
                     'ACCESSIBILITY-TYPING.md', 'ACCESSIBILITY-TYPING-PL.md',
                     'ESPEAK-ROCKBOX.md', 'ESPEAK-ROCKBOX-PL.md',
                     'ACCESSIBILITY-LISTS.md', 'ACCESSIBILITY-LISTS-PL.md',
                     'ACCESSIBILITY-SCREEN.md', 'ACCESSIBILITY-SCREEN-PL.md',
                     'ACCESSIBILITY-SHORTCUT.md', 'ACCESSIBILITY-SHORTCUT-PL.md',
                     'HIBY-R1-CONNECTIVITY.md', 'HIBY-R1-CONNECTIVITY-PL.md',
                     'ACCESSIBILITY-CURTAIN.md', 'ACCESSIBILITY-CURTAIN-PL.md',
                     'INTERFACE-APPEARANCE.md', 'INTERFACE-APPEARANCE-PL.md',
                     'HIBY-R1-POWER.md', 'HIBY-R1-POWER-PL.md',
                     'RADIO-DYNAMIC.md', 'RADIO-DYNAMIC-PL.md',
                     'HIBY-R1-NETWORK-EMULATION.md', 'HIBY-R1-NETWORK-EMULATION-PL.md',
                     'ESPEAK-BLUETOOTH.md', 'ESPEAK-BLUETOOTH-PL.md',
                     'ESPEAK-HIBY-USB.md', 'ESPEAK-HIBY-USB-PL.md',
                     'ESPEAK-BOOKMARKS.md', 'ESPEAK-BOOKMARKS-PL.md',
                     'ESPEAK-PLUGINS.md', 'ESPEAK-PLUGINS-PL.md'):
            self.write(self.root / 'docs' / name, f'Synthetic documentation: {name}')
        for name in ('License.txt', 'sonic/LICENSE', 'sonic/README.md'):
            self.write(self.root / 'lib/espeak' / name, f'Synthetic notice: {name}')
        for name in ('run-espeak-simulator.sh', 'run-espeak-simulator.cmd'):
            self.write(self.root / 'tools' / name, f'Synthetic launcher: {name}')
        self.patch(builder, 'ROOT', self.root)
        self.patch(builder, '_project_materials_root', self.materials_root)
        self.patch(validator, '_project_materials_root', self.materials_root)
        self.output = self.patch(builder.subprocess, 'check_output', side_effect=self.command_output)
        self.run = self.patch(builder, 'run', side_effect=self.install_fixture)
        self.preserve = self.patch(builder, 'preserve')
        self.not_running = self.patch(builder, 'assert_not_running')
        runtime_data = {name: builder.digest(self.source / 'espeak-data' / name)
                        for name in ('phondata', 'pl_dict')}
        manifest = ''.join(digest + '  espeak-data/' + name + '\n'
                           for name, digest in sorted(runtime_data.items()))
        self.provenance = {'engine_revision': builder.ENGINE_REVISION, 'runtime_data': runtime_data,
                           'dictsource': {}, 'data_manifest_sha256': builder.hashlib.sha256(manifest.encode()).hexdigest(),
                           'data_provenance_sha256': 'b' * 64}
        self.data_validation = self.patch(builder, 'validate_supplied_data', return_value=self.provenance)

    def patch(self, owner, attribute, *arguments, **keywords):
        patcher = mock.patch.object(owner, attribute, *arguments, **keywords)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def command_output(self, command, **keywords):
        if command == ['git', '-C', str(self.source), 'rev-parse', 'HEAD']:
            return builder.ENGINE_REVISION + '\n'
        if command == ['git', '-C', str(self.root), 'rev-parse', 'HEAD']:
            return 'synthetic-rockbox-revision\n'
        if command == [str(self.sdk / 'bin/sdl2-config'), '--version']:
            return '2.32.10\n'
        if command[0] in ('nm', 'x86_64-w64-mingw32-nm'):
            Path(command[1]).read_bytes()
            return '0000 T rb_espeak_synth\n0001 T tts_speak\n'
        if command[0] == 'x86_64-w64-mingw32-objdump':
            return 'DLL Name: KERNEL32.dll\nDLL Name: USER32.dll\n'
        raise AssertionError(f'Unexpected external command: {command}')

    def install_fixture(self, command, directory, log, environment):
        if command[:2] == ['make', 'fullinstall']:
            disk = Path(command[2].removeprefix('RBPREFIX='))
            (disk / '.rockbox/langs').mkdir(parents=True)
            self.write(disk / '.rockbox/rockbox-info.txt', (directory / 'rockbox-info.txt').read_text())

    def invoke(self, *arguments):
        command = ['build_espeak_simulator.py', '--jobs', '2', '--sdl-sdk', str(self.sdk),
                   '--espeak-source', str(self.source), *arguments]
        with mock.patch.object(sys, 'argv', command), contextlib.redirect_stdout(io.StringIO()):
            builder.main()

    def prepare_build(self, name, target='sansaclipplus', windows=True):
        build = self.materials / name
        self.write(build / ('rockboxui.exe' if windows else 'rockboxui'), 'Synthetic non-executable simulator')
        self.write(build / 'UI256.bmp', 'Synthetic target bitmap')
        self.write(build / 'Makefile', f'export MODELNAME={target}\n')
        self.write(build / 'rockbox-info.txt', f'Target: {target}\n')
        for language in ('english', 'polski'):
            self.write(build / 'apps/lang' / f'{language}.vstrings', f'Synthetic {language} voice strings')
        self.write(build / 'simdisk/.rockbox/config.cfg', 'tts rate: 450\n')
        self.write(build / 'simdisk/.rockbox/.resume.cfg', 'resume index: 7\n')
        self.write(build / 'simdisk/book.txt', 'Synthetic user data; must not be packaged')
        return build

    def protect_clipplus(self):
        build = self.prepare_build('build-espeak-windows')
        release = self.release_root / 'simwindows'
        self.write(release / 'rockboxui.exe', 'Synthetic existing Clip+ release')
        self.write(release / 'simdisk/.rockbox/config.cfg', 'tts rate: 450\n')
        self.write(release / 'simdisk/.rockbox/.resume.cfg', 'resume index: 12\n')
        self.write(release / 'simdisk/book.txt', 'Synthetic private book')
        return {directory: validator.inventory(directory) for directory in (build, release)}

    def assert_protected(self, protected):
        for directory, files in protected.items():
            self.assertEqual(validator.inventory(directory), files)
        self.assertFalse((self.snapshots).exists())

    def assert_build(self, target, name, label, windows=True):
        build = self.materials / name
        configuration = ['bash', str(self.root / 'tools/configure'), f'--target={target}',
                         '--type=as6' if windows else '--type=s', '--integrated-espeak']
        if not windows:
            configuration.append('--sdl-threads')
        calls = self.run.call_args_list
        self.assertEqual(calls[0].args[:3], (configuration, build, build / 'configure.log'))
        self.assertEqual(calls[1].args[:3], (['make', '-j2'], build, build / 'build.log'))
        environment = calls[0].args[3]
        self.assertEqual(environment['OMP_NUM_THREADS'], '2')
        self.assertEqual(environment['VERSION'], EXPECTED_VERSIONS[target]['windows' if windows else 'linux'])
        self.assertEqual(calls[1].args[3]['VERSION'], environment['VERSION'])
        if windows:
            self.assertEqual(environment['CXX'], 'x86_64-w64-mingw32-g++')
        self.preserve.assert_called_once_with(build, label)

    def assert_package(self, build, release_name, target, kind, windows=True):
        release = self.release_root / release_name
        manifest = json.loads((release / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['target'], target)
        self.assertEqual(manifest['kind'], kind)
        self.assertEqual(manifest['version'], EXPECTED_VERSIONS[target]['windows' if windows else 'linux'])
        self.assertEqual(manifest['engine_revision'], builder.ENGINE_REVISION)
        if target == 'hibyr1':
            self.assertEqual(manifest['espeak_data_provenance'], self.provenance)
            self.assertGreaterEqual(self.data_validation.call_count, 3)
        else:
            self.assertNotIn('espeak_data_provenance', manifest)
            self.data_validation.assert_not_called()
        self.assertEqual(manifest['plugin_abi'], 0xe006)
        self.assertEqual(manifest['windows_system_imports'], ['KERNEL32.dll', 'USER32.dll'] if windows else [])
        self.assertEqual(validator.validate_clean_profile(release, manifest)['tts rate'], '175')
        expected = {name: digest for name, digest in validator.inventory(release).items() if name != 'manifest.json'}
        self.assertEqual(manifest['files'], expected)
        executable = 'rockboxui.exe' if windows else 'rockboxui'
        self.assertEqual((release / executable).read_bytes(), b'Synthetic non-executable simulator')
        self.assertFalse((build / executable).exists())
        self.assertEqual((release / 'UI256.bmp').read_bytes(), (build / 'UI256.bmp').read_bytes())
        for language in ('english', 'polski'):
            self.assertEqual((release / 'simdisk/.rockbox/langs' / f'{language}.vstrings').read_bytes(),
                             (build / 'apps/lang' / f'{language}.vstrings').read_bytes())
        for name in ('phondata', 'pl_dict'):
            self.assertEqual((release / 'simdisk/.rockbox/espeak-data' / name).read_bytes(),
                             (self.source / 'espeak-data' / name).read_bytes())
        for source, destination in (('run-espeak-simulator.cmd', 'Uruchom.cmd'),
                                    ('run-espeak-simulator.sh', 'launch.sh')):
            self.assertEqual((release / destination).exists(), not windows)
            if not windows:
                self.assertEqual((release / destination).read_bytes(), (self.root / 'tools' / source).read_bytes())
        self.not_running.assert_called_once_with(build / executable)
        self.assertEqual(self.run.call_args_list[-1].args[:3],
                         (['make', 'fullinstall', f'RBPREFIX={release / "simdisk"}'], build, build / 'install.log'))
        self.assertEqual(self.run.call_args_list[-1].args[3]['VERSION'], manifest['version'])
        self.assertEqual((release / 'CZYTAJ.md').read_bytes(),
                         (self.root / 'docs' / ('ESPEAK-HIBYR1-PL.md' if target == 'hibyr1' else
                          'ESPEAK-WINDOWS-PL.md' if windows else 'ESPEAK-PL.md')).read_bytes())
        if windows:
            self.assertEqual((release / 'README.md').read_bytes(),
                             (self.root / 'docs' / ('ESPEAK-HIBYR1.md' if target == 'hibyr1' else
                              'ESPEAK-WINDOWS.md')).read_bytes())
            for name in ('INTERFACE-APPEARANCE.md', 'INTERFACE-APPEARANCE-PL.md',
                         'ACCESSIBILITY-SCREEN.md', 'ACCESSIBILITY-SCREEN-PL.md',
                         'HIBY-R1-POWER.md', 'HIBY-R1-POWER-PL.md',
                         'RADIO-DYNAMIC.md', 'RADIO-DYNAMIC-PL.md'):
                if target == 'hibyr1':
                    self.assertEqual((release / name).read_bytes(), (self.root / 'docs' / name).read_bytes())
                    self.assertEqual(manifest['files'][name], builder.digest(self.root / 'docs' / name))
                else:
                    self.assertFalse((release / name).exists())
            for name in ('ESPEAK-PLUGINS.md', 'ESPEAK-PLUGINS-PL.md'):
                self.assertEqual((release / name).read_bytes(),
                                 (self.root / 'docs' / name).read_bytes())
            for name in ('ESPEAK-ROCKBOX.md', 'ESPEAK-ROCKBOX-PL.md',
                         'ACCESSIBILITY-LISTS.md', 'ACCESSIBILITY-LISTS-PL.md'):
                if target == 'hibyr1':
                    self.assertTrue((release / name).is_file(), 'Missing new R1 guide: ' + name)
                    self.assertEqual((release / name).read_bytes(), (self.root / 'docs' / name).read_bytes())
                else:
                    self.assertFalse((release / name).exists())
            native_guides = {'sansaclipplus': {'ESPEAK-CLIPPLUS.md', 'ESPEAK-CLIPPLUS-PL.md'},
                             'sansaclipzip': {'ESPEAK-CLIPZIP.md', 'ESPEAK-CLIPZIP-PL.md'},
                             'hibyr1': {'ESPEAK-HIBYR1.md', 'ESPEAK-HIBYR1-PL.md'}}[target]
            self.assertEqual({path.name for path in release.glob('ESPEAK-CLIP*.md')},
                             native_guides if target != 'hibyr1' else set())
            for name in native_guides | {'ESPEAK.md', 'ESPEAK-PL.md', 'ESPEAK-TARGETS.md', 'ESPEAK-TARGETS-PL.md'}:
                self.assertEqual((release / name).read_bytes(), (self.root / 'docs' / name).read_bytes())

    def test_default_windows_build_keeps_clipplus_paths(self):
        self.invoke('--build-only')
        self.assert_build('sansaclipplus', 'build-espeak-windows', 'clipplus-windows-development')
        self.assertEqual(self.run.call_count, 2)
        self.assertFalse((self.release_root).exists())

    def test_explicit_clipplus_matches_default(self):
        self.invoke('--target', 'sansaclipplus', '--build-only')
        self.assert_build('sansaclipplus', 'build-espeak-windows', 'clipplus-windows-development')

    def test_clipzip_windows_build_never_touches_clipplus(self):
        protected = self.protect_clipplus()
        self.invoke('--target', 'sansaclipzip', '--build-only')
        self.assert_build('sansaclipzip', 'build-espeak-windows-clipzip', 'clipzip-windows-development')
        self.assert_protected(protected)

    def test_hiby_r1_windows_build_keeps_sansa_release_untouched(self):
        protected = self.protect_clipplus()
        with mock.patch.dict(builder.os.environ, VERSION='0ed3734e5e-espeak-r34-hibyr1-win-alpha15-20261019'):
            self.invoke('--target', 'hibyr1', '--build-only')
        self.assert_build('hibyr1', 'build-espeak-windows-hibyr1', 'hibyr1-windows-development')
        self.assert_protected(protected)

    def test_hiby_r1_windows_package_is_clean_and_target_specific(self):
        protected = self.protect_clipplus()
        build = self.prepare_build('build-espeak-windows-hibyr1', 'hibyr1')
        self.invoke('--target', 'hibyr1', '--package-only')
        self.assert_package(build, 'simwindows-hibyr1', 'hibyr1',
                            'Native Windows x64 HiBy R1 simulator; not device firmware')
        for name in ('HIBY-R1-CONTROLS.md', 'HIBY-R1-CONTROLS-PL.md',
                     'HIBY-R1-INSTALL.md', 'HIBY-R1-INSTALL-PL.md'):
            self.assertEqual((self.release_root / 'simwindows-hibyr1' / name).read_bytes(),
                             (self.root / 'docs' / name).read_bytes())
        self.assert_protected(protected)

    def assert_missing_radio_guide_blocks_publication(self, name):
        build = self.prepare_build('build-espeak-windows-hibyr1', 'hibyr1')
        (self.root / 'docs' / name).rename(self.area / name)
        with self.assertRaises(FileNotFoundError):
            self.invoke('--target', 'hibyr1', '--package-only')
        self.assertTrue((build / 'rockboxui.exe').is_file())
        self.assertFalse((self.release_root / 'simwindows-hibyr1/rockboxui.exe').exists())
        self.assertFalse((self.release_root / 'simwindows-hibyr1/manifest.json').exists())

    def test_missing_english_radio_guide_blocks_publication_before_executable_move(self):
        self.assert_missing_radio_guide_blocks_publication('RADIO-DYNAMIC.md')

    def test_missing_polish_radio_guide_blocks_publication_before_executable_move(self):
        self.assert_missing_radio_guide_blocks_publication('RADIO-DYNAMIC-PL.md')

    def test_r1_same_commit_data_drift_blocks_before_preserve_or_build(self):
        self.data_validation.side_effect = ValueError('same-commit data drift')
        with self.assertRaisesRegex(ValueError, 'same-commit data drift'):
            self.invoke('--target', 'hibyr1', '--build-only')
        self.run.assert_not_called()
        self.preserve.assert_not_called()
        self.assertFalse((self.materials / 'build-espeak-windows-hibyr1').exists())

    def test_r1_same_commit_data_drift_blocks_package_before_any_installation(self):
        build = self.prepare_build('build-espeak-windows-hibyr1', 'hibyr1')
        protected = {build: validator.inventory(build)}
        self.data_validation.side_effect = ValueError('same-commit data drift')
        with self.assertRaisesRegex(ValueError, 'same-commit data drift'):
            self.invoke('--target', 'hibyr1', '--package-only')
        self.run.assert_not_called()
        self.preserve.assert_not_called()
        self.assert_protected(protected)
        self.assertFalse(self.release_root.exists())

    def test_r1_rechecks_data_after_compilation_before_packaging(self):
        self.prepare_build('build-espeak-windows-hibyr1', 'hibyr1')
        self.data_validation.side_effect = [self.provenance, ValueError('data drift after compilation')]
        with self.assertRaisesRegex(ValueError, 'data drift after compilation'):
            self.invoke('--target', 'hibyr1')
        self.assertEqual(self.run.call_count, 2)
        self.assertFalse(self.release_root.exists())

    def test_r1_rechecks_data_before_moving_executable_to_release(self):
        build = self.prepare_build('build-espeak-windows-hibyr1', 'hibyr1')
        self.data_validation.side_effect = [self.provenance, self.provenance,
                                            ValueError('data drift at publication')]
        with self.assertRaisesRegex(ValueError, 'data drift at publication'):
            self.invoke('--target', 'hibyr1', '--package-only')
        self.assertEqual(self.data_validation.call_count, 3)
        self.assertTrue((build / 'rockboxui.exe').is_file())
        self.assertFalse((self.release_root / 'simwindows-hibyr1/rockboxui.exe').exists())
        self.assertFalse((self.release_root / 'simwindows-hibyr1/manifest.json').exists())

    def test_r1_packaged_data_is_bound_to_provenance_before_executable_move(self):
        build = self.prepare_build('build-espeak-windows-hibyr1', 'hibyr1')
        original_copy = builder.shutil.copytree

        def altered_copy(source, destination):
            result = original_copy(source, destination)
            (destination / 'pl_dict').write_bytes(b'Corrupt synthetic destination data')
            return result

        with mock.patch.object(builder.shutil, 'copytree', side_effect=altered_copy):
            with self.assertRaisesRegex(ValueError, 'runtime differs from supplied-data provenance'):
                self.invoke('--target', 'hibyr1', '--package-only')
        self.assertTrue((build / 'rockboxui.exe').exists())
        self.assertFalse((self.release_root / 'simwindows-hibyr1/manifest.json').exists())

    def test_sansa_builds_do_not_require_current_r1_data(self):
        self.data_validation.side_effect = AssertionError('R1 data validation must not gate Sansa')
        self.invoke('--target', 'sansaclipzip', '--build-only')
        self.data_validation.assert_not_called()
        self.assert_build('sansaclipzip', 'build-espeak-windows-clipzip', 'clipzip-windows-development')

    def test_hiby_r1_cannot_package_a_sansa_build(self):
        self.prepare_build('build-espeak-windows-hibyr1', 'sansaclipzip')
        with self.assertRaisesRegex(RuntimeError, 'build target mismatch'):
            self.invoke('--target', 'hibyr1', '--package-only')
        self.run.assert_not_called()
        self.assertFalse((self.release_root / 'simwindows-hibyr1').exists())

    def test_default_linux_build_keeps_legacy_paths(self):
        self.invoke('--platform', 'linux', '--build-only')
        self.assert_build('sansaclipplus', 'build-espeak', 'clipplus-development', windows=False)

    def test_clipzip_linux_build_is_separate(self):
        self.invoke('--platform', 'linux', '--target', 'sansaclipzip', '--build-only')
        self.assert_build('sansaclipzip', 'build-espeak-simulator-clipzip', 'clipzip-development', windows=False)

    def test_unknown_target_fails_before_side_effects(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            self.invoke('--target', 'unknown')
        self.assertEqual(raised.exception.code, 2)
        self.output.assert_not_called()
        self.run.assert_not_called()
        self.preserve.assert_not_called()

    def test_existing_clipplus_release_is_rejected_without_changes(self):
        protected = self.protect_clipplus()
        with self.assertRaisesRegex(RuntimeError, 'installed simulator already exists'):
            self.invoke('--package-only')
        self.assert_protected(protected)
        self.run.assert_not_called()
        self.preserve.assert_not_called()

    def test_existing_clipzip_release_is_rejected_without_changes(self):
        protected = self.protect_clipplus()
        release = self.release_root / 'simwindows-clipzip'
        self.write(release / 'simdisk/.rockbox/config.cfg', 'tts rate: 900\n')
        protected[release] = validator.inventory(release)
        with self.assertRaisesRegex(RuntimeError, 'installed simulator already exists'):
            self.invoke('--target', 'sansaclipzip', '--package-only')
        self.assert_protected(protected)
        self.run.assert_not_called()
        self.preserve.assert_not_called()

    def test_build_only_leaves_existing_clipzip_release_untouched(self):
        release = self.release_root / 'simwindows-clipzip'
        self.write(release / 'simdisk/.rockbox/config.cfg', 'tts rate: 900\n')
        protected = {release: validator.inventory(release)}
        self.invoke('--target', 'sansaclipzip', '--build-only')
        self.assert_build('sansaclipzip', 'build-espeak-windows-clipzip', 'clipzip-windows-development')
        self.assert_protected(protected)

    def test_default_windows_package_has_clean_clipplus_profile(self):
        build = self.prepare_build('build-espeak-windows')
        self.invoke('--package-only')
        self.assert_package(build, 'simwindows', 'sansaclipplus',
                            'Native Windows x64 Clip+ simulator; not device firmware')
        self.preserve.assert_not_called()
        self.assertEqual(self.run.call_count, 1)

    def test_clipzip_windows_package_is_clean_and_preserves_clipplus(self):
        protected = self.protect_clipplus()
        build = self.prepare_build('build-espeak-windows-clipzip', 'sansaclipzip')
        self.invoke('--target', 'sansaclipzip', '--package-only')
        self.assert_package(build, 'simwindows-clipzip', 'sansaclipzip',
                            'Native Windows x64 Clip Zip simulator; not device firmware')
        self.assert_protected(protected)
        self.preserve.assert_not_called()
        self.assertEqual(self.run.call_count, 1)

    def test_clipzip_combined_build_and_package_uses_only_selected_paths(self):
        protected = self.protect_clipplus()
        build = self.prepare_build('build-espeak-windows-clipzip', 'sansaclipzip')
        self.invoke('--target', 'sansaclipzip')
        self.assert_build('sansaclipzip', 'build-espeak-windows-clipzip', 'clipzip-windows-development')
        self.assert_package(build, 'simwindows-clipzip', 'sansaclipzip',
                            'Native Windows x64 Clip Zip simulator; not device firmware')
        self.assert_protected(protected)
        self.assertEqual(self.run.call_count, 3)

    def test_linux_package_keeps_legacy_launchers_and_clean_profile(self):
        build = self.prepare_build('build-espeak', windows=False)
        self.invoke('--platform', 'linux', '--package-only')
        self.assert_package(build, 'clipplus-espeak-simulator', 'sansaclipplus',
                            'Linux/WSL Clip+ simulator; not device firmware', windows=False)

    def test_clipzip_linux_package_uses_distinct_version_and_clean_profile(self):
        build = self.prepare_build('build-espeak-simulator-clipzip', 'sansaclipzip', windows=False)
        self.invoke('--platform', 'linux', '--target', 'sansaclipzip', '--package-only')
        self.assert_package(build, 'clipzip-espeak-simulator', 'sansaclipzip',
                            'Linux/WSL Clip Zip simulator; not device firmware', windows=False)

    def test_package_only_rejects_wrong_target_before_installation(self):
        protected = self.protect_clipplus()
        build = self.prepare_build('build-espeak-windows-clipzip')
        protected[build] = validator.inventory(build)
        with self.assertRaisesRegex(RuntimeError, 'build target mismatch'):
            self.invoke('--target', 'sansaclipzip', '--package-only')
        self.assert_protected(protected)
        self.assertFalse((self.release_root / 'simwindows-clipzip').exists())
        self.run.assert_not_called()
        self.preserve.assert_not_called()
        self.not_running.assert_not_called()

    def test_build_identity_requires_matching_makefile_and_info(self):
        for filename, content in (('Makefile', 'export MODELNAME=sansaclipplus\n'),
                                  ('rockbox-info.txt', 'Target: sansaclipplus\n')):
            with self.subTest(filename=filename):
                build = self.prepare_build(filename + '-fixture', 'sansaclipzip')
                self.write(build / filename, content)
                with self.assertRaisesRegex(RuntimeError, 'build target mismatch'):
                    builder.validate_build_target(build, 'sansaclipzip')

    def test_missing_clipzip_build_cannot_fall_back_to_clipplus(self):
        protected = self.protect_clipplus()
        with self.assertRaisesRegex(RuntimeError, 'Cannot verify simulator build target'):
            self.invoke('--target', 'sansaclipzip', '--package-only')
        self.assert_protected(protected)
        self.run.assert_not_called()
        self.preserve.assert_not_called()

    def test_package_only_rejects_clipzip_build_in_legacy_clipplus_path(self):
        build = self.prepare_build('build-espeak-windows', 'sansaclipzip')
        protected = {build: validator.inventory(build)}
        with self.assertRaisesRegex(RuntimeError, 'build target mismatch'):
            self.invoke('--package-only')
        self.assert_protected(protected)
        self.assertFalse((self.release_root).exists())
        self.run.assert_not_called()
        self.preserve.assert_not_called()

    def test_build_identity_rejects_empty_or_duplicate_target_fields(self):
        for name, content in (('Makefile', ''), ('rockbox-info.txt', ''),
                              ('Makefile', 'export MODELNAME=sansaclipzip\nexport MODELNAME=sansaclipplus\n'),
                              ('rockbox-info.txt', 'Target: sansaclipzip\nTarget: sansaclipplus\n')):
            with self.subTest(name=name, content=content):
                build = self.prepare_build('identity-fixture', 'sansaclipzip')
                self.write(build / name, content)
                with self.assertRaisesRegex(RuntimeError, 'build target mismatch'):
                    builder.validate_build_target(build, 'sansaclipzip')

    def test_validator_cli_selects_default_explicit_and_custom_release_paths(self):
        for arguments, release_name, label in (
                ([], 'simwindows', 'Clip+'),
                (['--target', 'sansaclipzip'], 'simwindows-clipzip', 'Clip Zip'),
                (['--target', 'sansaclipzip', '--release', str(self.release_root / 'custom')],
                 'custom', 'Clip Zip')):
            with self.subTest(arguments=arguments):
                release = self.release_root / release_name
                release.mkdir(parents=True, exist_ok=True)
                (release.parent / f'Symulator pr\u00f3bny {label}').mkdir(exist_ok=True)
                native = mock.Mock()
                with mock.patch.object(validator, 'ROOT', self.root), \
                        mock.patch.object(validator, 'windows_backend', return_value=native), \
                        mock.patch.object(sys, 'platform', 'win32'), \
                        mock.patch.object(sys, 'argv', ['validator', *arguments]), \
                        self.assertRaisesRegex(RuntimeError, 'Unicode relocation destination already exists'):
                    validator.main()
                native.ensure_unused.assert_called_once_with(release / 'rockboxui.exe')

    def test_validator_rejects_manifest_mismatch_before_any_process_launch(self):
        release = self.release_root / 'simwindows-clipzip'
        self.write(release / 'manifest.json', json.dumps({'target': 'sansaclipplus', 'files': {}}))
        protected = {release: validator.inventory(release)}
        with mock.patch.object(validator, 'ROOT', self.root), \
                mock.patch.object(validator, 'windows_backend'), \
                mock.patch.object(validator.subprocess, 'Popen') as launch, \
                mock.patch.object(sys, 'platform', 'win32'), \
                mock.patch.object(sys, 'argv', ['validator', '--target', 'sansaclipzip']), \
                contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(AssertionError, 'Package target mismatch'):
            validator.main()
        launch.assert_not_called()
        self.assert_protected(protected)
        report_path, = (self.materials / 'windows-package-tests').glob('*/report.json')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        self.assertFalse(report['passed'])
        self.assertEqual(report['target'], 'sansaclipzip')

    def test_running_clipzip_blocks_packaging_without_changing_either_target(self):
        protected = self.protect_clipplus()
        build = self.prepare_build('build-espeak-windows-clipzip', 'sansaclipzip')
        protected[build] = validator.inventory(build)
        self.not_running.side_effect = RuntimeError('Close the native simulator')
        with self.assertRaisesRegex(RuntimeError, 'Close the native simulator'):
            self.invoke('--target', 'sansaclipzip', '--package-only')
        self.assert_protected(protected)
        self.run.assert_not_called()
        self.preserve.assert_not_called()


class WindowsValidatorTargetTests(unittest.TestCase):
    def test_matching_manifest_targets_and_legacy_missing_target(self):
        for target in ('sansaclipplus', 'sansaclipzip'):
            with self.subTest(target=target):
                validator.validate_manifest_target({'target': target}, target)
                validator.validate_manifest_target({}, target)

    def test_manifest_target_mismatch_is_rejected(self):
        for expected, actual in (('sansaclipplus', 'sansaclipzip'), ('sansaclipzip', 'sansaclipplus'),
                                 ('sansaclipzip', None), ('sansaclipzip', 'unknown')):
            with self.subTest(expected=expected, actual=actual), self.assertRaisesRegex(AssertionError, 'target mismatch'):
                validator.validate_manifest_target({'target': actual}, expected)

    def test_target_ids_and_module_abis_for_both_targets(self):
        for target, model in (('sansaclipplus', 66), ('sansaclipzip', 68)):
            for suffix, magic, abi in (('.rock', 0x526f634b, 0xe006), ('.ovl', 0x526f634b, 1),
                                       ('.codec', 0x52434f44, 50), ('.codec', 0x52454e43, 50)):
                with self.subTest(target=target, suffix=suffix, magic=magic):
                    module = Path('fixture' + suffix)
                    validator.validate_module_identity((magic, model, abi), module, target)
                    for header in ((magic, 68 if model == 66 else 66, abi), (magic, model, abi + 1),
                                   (0, model, abi)):
                        with self.assertRaisesRegex(AssertionError, 'Wrong target or ABI'):
                            validator.validate_module_identity(header, module, target)

    def test_firmware_model_number_is_not_clipzip_module_target_id(self):
        with self.assertRaisesRegex(AssertionError, 'Wrong target or ABI'):
            validator.validate_module_identity((0x526f634b, 79, 0xe006), Path('fixture.rock'), 'sansaclipzip')

    def test_previous_plugin_apis_are_rejected_for_every_target(self):
        for target, configuration in validator.TARGETS.items():
            for abi in (285, 0xe003, 0xe004, 0xe005):
                with self.subTest(target=target, abi=abi), self.assertRaisesRegex(AssertionError, 'Wrong target or ABI'):
                    validator.validate_module_identity((0x526f634b, configuration['target_id'], abi),
                                                       Path('fixture.rock'), target)


if __name__ == '__main__':
    unittest.main(verbosity=2)
