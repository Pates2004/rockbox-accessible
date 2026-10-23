import ast
import contextlib
import datetime
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
import tarfile
import unittest
from unittest import mock
from types import SimpleNamespace

from materials_fixtures import materials_resolver
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_espeak_clipplus as package


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



def firmware(payload=b'ARM test fixture, not executable firmware'):
    return struct.pack('>I', (66 + sum(payload)) & 0xffffffff) + b'cli+' + payload


def catalog(voice=True):
    return bytes([0x9a if voice else 0x1a, 6, 66, 0]) + struct.pack('>HHH', 1, 6, 10) + b'\0\x01Test\0'


def module(plugin=True, target=66, abi=None):
    return struct.pack('<IHH', 0x526f634b if plugin else 0x52434f44,
                       target, abi if abi is not None else (0xe006 if plugin else 50)) + bytes(24)


class ClipplusPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        cls.results = _project_materials_root(package.ROOT) / 'clipplus-package-tests' / timestamp
        cls.results.mkdir(parents=True)
        print(f'Synthetic packaging regression fixtures (not firmware): {cls.results}')

    def setUp(self):
        self.directory = self.results / self._testMethodName
        self.directory.mkdir()
        self.materials_root = materials_resolver(self.directory / 'source', self.directory / 'central')
        self.materials = self.materials_root(package.ROOT)
        self.release_root = self.materials_root(package.ROOT, 'installfiles')
        patcher = mock.patch.object(package, '_project_materials_root', side_effect=self.materials_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.base_files = {
            package.FIRMWARE: firmware(),
            '.rockbox/rocks/apps/test.rock': module(),
            '.rockbox/rocks/apps/test.ovl': module(),
            '.rockbox/codecs/test.codec': module(False),
            '.rockbox/rockbox-info.txt': (
                b'Target: sansaclipplus\nTarget id: 66\nCPU: arm\nBinary: rockbox.sansa\nVersion: fixture\n'),
        }
        for language in ('english', 'polski'):
            self.base_files[package.CATALOG_PREFIX + language + '.lng'] = catalog(False)
        self.additions = {package.DATA_PREFIX + name: b'data fixture: ' + name.encode()
                          for name in package.REQUIRED_DATA}
        for language in ('english', 'polski'):
            self.additions[package.CATALOG_PREFIX + language + '.vstrings'] = catalog()
        self.additions['.rockbox/config.cfg'] = package.DEFAULT_CONFIG
        self.additions.update({'.rockbox/espeak-clipplus/' + name: b'fixture documentation'
                               for name in (*package.DOCUMENTS, *package.RUNTIME_NOTICES)})
        self.metadata = {
            'version': 'fixture', 'target': 'sansaclipplus', 'plugin_abi': package.PLUGIN_ABI,
            'engine_revision': package.ENGINE_REVISION, 'hardware_tested': False,
            'firmware': package.validate_firmware(firmware()),
            'runtime_data': {name[len(package.DATA_PREFIX):]: package.sha256(content)
                             for name, content in self.additions.items() if name.startswith(package.DATA_PREFIX)},
            'voice_catalogs': {name[len(package.CATALOG_PREFIX):]: package.sha256(content)
                              for name, content in self.additions.items() if name.endswith('.vstrings')},
        }

    def create(self):
        base = self.directory / 'make-zip-fixture.zip'
        output = self.directory / 'firmware-fixture.zip'
        with zipfile.ZipFile(base, 'x') as archive:
            for name, content in self.base_files.items():
                archive.writestr(name, content)
        package.write_firmware_zip(base, output, self.additions, self.metadata)
        return output

    def rewrite(self, original, changed, remanifest=False):
        output = self.directory / 'mutated-fixture.zip'
        with zipfile.ZipFile(original) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        for name, content in changed.items():
            if content is None:
                files.pop(name, None)
            else:
                files[name] = content
        if remanifest:
            manifest = json.loads(files[package.MANIFEST])
            manifest['files'] = {name: package.sha256(content) for name, content in files.items()
                                 if name != package.MANIFEST}
            files[package.MANIFEST] = package.json_bytes(manifest)
        with zipfile.ZipFile(output, 'x') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return output

    def test_accessibility_profiles_rejected(self):
        for prefix in ('.rockbox/', '.rockbox/cache/'):
            for name in ('accessibility.cfg', 'ACCESSIBILITY.CFG',
                         'accessibility-screen.cfg', 'ACCESSIBILITY-SCREEN.CFG',
                         'tts-reader.cfg', 'TTS-READER.CFG', 'Tts-Reader.Cfg',
                         'tts-reader.cfg.tmp', 'TTS-READER.CFG.NEW', 'tts-reader.cfg.future', 'Tts-Reader.Cfg.BaK',
                         'bluetooth.cfg', 'BLUETOOTH.CFG', 'BlueTooth.Cfg',
                         'bluetooth.cfg.tmp', 'BLUETOOTH.CFG.NEW', 'bluetooth.cfg.future', 'BlueTooth.Cfg.BaK',
                         'empty-feedback.cfg', 'EMPTY-FEEDBACK.CFG', 'Empty-Feedback.Cfg',
                         'empty-feedback.cfg.tmp', 'EMPTY-FEEDBACK.CFG.NEW', 'empty-feedback.cfg.future',
                         'Empty-Feedback.Cfg.BaK',
                         'accessibility-screen.cfg.tmp', 'accessibility-screen.cfg.future',
                         'accessibility-typing.cfg', 'ACCESSIBILITY-TYPING.CFG',
                         'accessibility-typing.cfg.tmp', 'accessibility-typing.cfg.bak',
                         'accessibility.cfg.pending', 'Accessibility.cfg.BAK',
                         'accessibility.cfg.future'):
                with self.subTest(name=prefix + name), self.assertRaisesRegex(
                        RuntimeError, 'saved runtime state'):
                    package.validate_package_entry(prefix + name, b'private mapping')

    def test_private_bookmark_files_rejected(self):
        for name in ('book.txt.bmark', 'BOOK.TXT.BMARK', 'book.txt.bmark.tmp',
                     'book.txt.bmark.t01', 'book.txt.bmark.T0F',
                     'book.bookmark', 'book.BOOKMARK.pending'):
            with self.subTest(name=name), self.assertRaisesRegex(
                    RuntimeError, 'saved runtime state'):
                package.validate_package_entry('.rockbox/' + name, b'private history')

    def test_valid_package_and_exact_runtime(self):
        output = self.create()
        manifest = package.verify_firmware_zip(output, self.metadata['runtime_data'], self.metadata['voice_catalogs'])
        self.assertFalse(manifest['hardware_tested'])
        self.assertEqual(manifest['firmware']['model'], 'cli+')
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), set(manifest['files']) | {package.MANIFEST})

    def test_firmware_header_checksum_and_payload(self):
        image = firmware()
        self.assertEqual(package.validate_firmware(image, image[8:])['model_number'], 66)
        for invalid in (b'', image[:8], image[:4] + b'clzp' + image[8:], bytes(4) + image[4:], firmware(bytes(10))):
            with self.subTest(image=invalid), self.assertRaises(RuntimeError):
                package.validate_firmware(invalid)
        with self.assertRaisesRegex(RuntimeError, 'payload'):
            package.validate_firmware(image, b'different payload')

    def test_firmware_exactly_one_mib_payload_accepted_with_header(self):
        payload = b'\x01' * (1024 * 1024)
        image = firmware(payload)
        self.assertEqual(len(image), len(payload) + 8)
        for expected_payload in (None, payload):
            with self.subTest(native_payload=expected_payload is not None):
                result = package.validate_firmware(image, expected_payload)
                self.assertEqual(result['payload_bytes'], 1024 * 1024)

    def test_firmware_one_byte_over_one_mib_rejected_with_valid_checksum(self):
        payload = b'\x01' * (1024 * 1024 + 1)
        image = firmware(payload)
        self.assertEqual(struct.unpack_from('>I', image)[0], (66 + sum(payload)) & 0xffffffff)
        for expected_payload in (None, payload):
            with self.subTest(native_payload=expected_payload is not None):
                with self.assertRaisesRegex(RuntimeError, r'Clip\+.*1048577.*1048576.*1 MiB'):
                    package.validate_firmware(image, expected_payload)

    def test_package_exactly_one_mib_payload_accepted(self):
        payload = b'\x01' * (1024 * 1024)
        image = firmware(payload)
        self.base_files[package.FIRMWARE] = image
        self.metadata['firmware'] = package.validate_firmware(image, payload)
        manifest = package.verify_firmware_zip(self.create(), payload=payload)
        self.assertEqual(manifest['firmware']['payload_bytes'], len(payload))

    def test_package_one_byte_over_one_mib_rejected_with_valid_hashes(self):
        payload = b'\x01' * (1024 * 1024 + 1)
        image = firmware(payload)
        self.base_files[package.FIRMWARE] = image
        self.metadata['firmware'].update(checksum=struct.unpack_from('>I', image)[0],
                                         payload_bytes=len(payload), payload_sha256=package.sha256(payload))
        output = self.create()
        for expected_payload in (None, payload):
            with self.subTest(native_payload=expected_payload is not None):
                with self.assertRaisesRegex(RuntimeError, r'Clip\+.*1048577.*1048576.*1 MiB'):
                    package.verify_firmware_zip(output, payload=expected_payload)

    def test_same_filesystem_publication_requires_no_destination_mutation(self):
        staging = self.directory / 'publication-staging'
        staging.mkdir()
        destination = self.directory / 'missing-release/result'
        package.ensure_publication_filesystem(staging, destination)
        self.assertFalse(destination.parent.exists())
        self.assertTrue(staging.is_dir())

    def test_cross_filesystem_publication_is_rejected_before_existing_release_is_archived(self):
        staging = self.directory / 'publication-staging'
        staging.mkdir()
        destination = self.directory / 'release/result'
        destination.mkdir(parents=True)
        marker = destination / 'user-data.txt'
        marker.write_bytes(b'preserved synthetic user data')
        original = Path.stat

        def different_filesystem(path, *arguments, **keywords):
            value = original(path, *arguments, **keywords)
            return SimpleNamespace(st_dev=value.st_dev + 1) if path == staging else value

        with mock.patch.object(Path, 'stat', autospec=True, side_effect=different_filesystem):
            with self.assertRaisesRegex(RuntimeError, 'existing release was not replaced'):
                package.ensure_publication_filesystem(staging, destination)
        self.assertEqual(marker.read_bytes(), b'preserved synthetic user data')
        self.assertTrue(staging.is_dir())
        main = next(node for node in ast.parse(Path(package.__file__).read_text(encoding='utf-8')).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'main')
        checks = [node.lineno for node in ast.walk(main) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name) and node.func.id == 'ensure_publication_filesystem']
        preservation = [node.lineno for node in ast.walk(main) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name) and node.func.id == 'preserve'
                        and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == 'release']
        self.assertEqual(len(checks), 1)
        self.assertEqual(len(preservation), 1)
        self.assertLess(checks[0], preservation[0])

    def test_elf_architecture_and_defined_symbols(self):
        image = bytearray(52)
        image[:7] = b'\x7fELF\x01\x01\x01'
        struct.pack_into('<HH', image, 16, 2, 40)
        package.validate_elf(image)
        for offset, value in ((4, 2), (5, 2), (16, 1), (18, 62)):
            invalid = bytearray(image)
            invalid[offset] = value
            with self.subTest(offset=offset), self.assertRaises(RuntimeError):
                package.validate_elf(invalid)
        symbols = ''.join(f'00001000 T {name}\n' for name in package.REQUIRED_SYMBOLS)
        package.validate_symbols(symbols)
        self.assertTrue({'reclist_speak', 'audio_set_pcm_output'} <= set(package.REQUIRED_SYMBOLS))
        self.assertNotIn('rb_espeak_synth', package.REQUIRED_SYMBOLS)
        package.validate_symbols(symbols + '00001200 T rb_espeak_synth\n')
        for name in package.REQUIRED_SYMBOLS:
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                package.validate_symbols(symbols.replace(f'00001000 T {name}\n', f'         U {name}\n'))

    def test_unused_synth_wrapper_does_not_substitute_used_entrypoints(self):
        with self.assertRaisesRegex(RuntimeError, 'missing defined'):
            package.validate_symbols('00001000 T rb_espeak_synth\n00001200 T tts_speak\n')

    def test_old_plugin_abi_other_target_and_codec_abi_rejected(self):
        for name, content in (('test.rock', module(abi=285)), ('test.rock', module(abi=0xe003)),
                              ('test.rock', module(abi=0xe004)), ('test.rock', module(abi=0xe005)),
                              ('test.ovl', module(target=80)),
                              ('test.codec', module(False, abi=49)), ('test.rock', b'MZ')):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                package.validate_module(name, content)

    def test_image_decoder_own_api_and_embedded_plugin_abi(self):
        decoder = struct.pack('<IHH', 0x526f634b, 66, 1) + bytes(16) + struct.pack('<H', 0xe006) + bytes(14)
        package.validate_module('bmp.ovl', decoder)
        for invalid in (decoder[:28], decoder[:24] + struct.pack('<H', 285) + decoder[26:],
                        decoder[:24] + struct.pack('<H', 0xe003) + decoder[26:],
                        decoder[:24] + struct.pack('<H', 0xe004) + decoder[26:],
                        decoder[:24] + struct.pack('<H', 0xe005) + decoder[26:],
                        decoder[:4] + struct.pack('<H', 80) + decoder[6:],
                        decoder[:6] + struct.pack('<H', 2) + decoder[8:]):
            with self.subTest(image=invalid), self.assertRaises(RuntimeError):
                package.validate_module('bmp.ovl', invalid)

    def test_catalog_wrong_target_truncation_and_conflicting_duplicates_rejected(self):
        package.validate_catalog('polski.vstrings', catalog())
        invalids = [catalog()[:2] + b'\x50' + catalog()[3:], catalog()[:-1],
                    catalog()[:4] + struct.pack('>HHH', 2, 6, 10) + catalog()[10:] + b'\0\x01Conflict\0']
        for invalid in invalids:
            with self.subTest(image=invalid), self.assertRaises(RuntimeError):
                package.validate_catalog('polski.vstrings', invalid)

    def test_identical_upstream_catalog_duplicates_are_compatible_with_loader(self):
        duplicate = catalog()[:4] + struct.pack('>HHH', 2, 6, 10) + catalog()[10:] * 2
        package.validate_catalog('chinese-trad.vstrings', duplicate)

    def test_stock_voice_files_are_omitted(self):
        self.base_files['.rockbox/langs/polski.voice'] = b'obsolete voice'
        manifest = package.verify_firmware_zip(self.create())
        self.assertEqual(manifest['excluded_stock_voice_files'], ['.rockbox/langs/polski.voice'])

    def test_stock_invalid_voice_talk_from_make_zip_is_omitted(self):
        name = '.rockbox/langs/InvalidVoice_english.talk'
        self.base_files[name] = b'Stock invalid-voice announcement fixture'
        output = self.create()
        manifest = package.verify_firmware_zip(output)
        self.assertEqual(manifest['excluded_stock_talk_files'], [name])
        self.assertNotIn(name, manifest['files'])
        with zipfile.ZipFile(output) as archive:
            self.assertNotIn(name, archive.namelist())

    def test_arbitrary_final_talk_file_rejected_even_when_manifested(self):
        output = self.rewrite(self.create(), {'.rockbox/clips/custom.talk': b'Private clip fixture'}, True)
        with self.assertRaisesRegex(RuntimeError, 'saved runtime state'):
            package.verify_firmware_zip(output)

    def test_hash_corruption_is_detected(self):
        output = self.rewrite(self.create(), {package.DATA_PREFIX + 'phondata': b'corrupt'})
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            package.verify_firmware_zip(output)

    def test_unmanifested_file_is_detected(self):
        output = self.rewrite(self.create(), {'.rockbox/extra.txt': b'extra'})
        with self.assertRaisesRegex(RuntimeError, 'Unmanifested'):
            package.verify_firmware_zip(output)

    def test_missing_required_asset_even_when_remanifested(self):
        output = self.rewrite(self.create(), {package.DATA_PREFIX + 'phondata': None}, True)
        with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
            package.verify_firmware_zip(output)

    def test_missing_generated_extra_catalog(self):
        expected = dict(self.metadata['voice_catalogs'], french='missing-hash')
        with self.assertRaisesRegex(RuntimeError, 'voice catalogs'):
            package.verify_firmware_zip(self.create(), expected_catalogs=expected)

    def test_clean_config_cannot_be_replaced_even_when_remanifested(self):
        output = self.rewrite(self.create(), {'.rockbox/config.cfg': b'tts rate: 450\n'}, True)
        with self.assertRaisesRegex(RuntimeError, 'clean Polish defaults'):
            package.verify_firmware_zip(output)

    def test_preexisting_user_config_in_base_is_rejected(self):
        self.base_files['.rockbox/config.cfg'] = b'user settings'
        with self.assertRaisesRegex(RuntimeError, 'pre-existing'):
            self.create()

    def test_bootloader_other_player_state_and_root_rejected(self):
        for name in ('.rockbox/bootloader-clipplus.sansa', '.rockbox/rockbox.ipod',
                     '.rockbox/clppa.bin', '.rockbox/.resume.cfg', '.rockbox/langs/english.voice',
                     'book.txt', 'simdisk/.rockbox/rockbox.sansa'):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                package.validate_package_entry(name, b'not allowed')

    def test_duplicate_casefold_and_symlink_zip_entries_rejected(self):
        cases = [('case', ['.rockbox/config.cfg', '.rockbox/CONFIG.CFG']),
                 ('traversal', ['.rockbox/../outside'])]
        for label, names in cases:
            path = self.directory / (label + '.zip')
            with zipfile.ZipFile(path, 'x') as archive:
                for name in names:
                    archive.writestr(name, b'fixture')
            with zipfile.ZipFile(path) as archive, self.assertRaises(RuntimeError):
                package.zip_entries(archive)
        path = self.directory / 'symlink.zip'
        with zipfile.ZipFile(path, 'x') as archive:
            info = zipfile.ZipInfo('.rockbox/link')
            info.external_attr = 0o120777 << 16
            archive.writestr(info, '../../outside')
        with zipfile.ZipFile(path) as archive, self.assertRaises(RuntimeError):
            package.zip_entries(archive)

    def test_clean_defaults_match_existing_simulator_without_modifying_it(self):
        source = (package.ROOT / 'tools/build_espeak_simulator.py').read_text(encoding='utf-8')
        candidates = [node.args[0].value for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr == 'write_text' and node.args
                      and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                      and node.args[0].value.startswith('lang: /.rockbox/langs/polski.lng')]
        self.assertEqual(candidates, [package.DEFAULT_CONFIG.decode('utf-8')])
        self.assertFalse(any(line.startswith(b'keyclick:') for line in package.DEFAULT_CONFIG.splitlines()))

    def test_source_inventory_includes_untracked_native_and_excludes_internal_credentials(self):
        repository = self.directory / 'repository'
        repository.mkdir()
        subprocess.run(['git', 'init', '-q', str(repository)], check=True)
        content = {
            'apps/tracked.c': b'old source', 'lib/espeak/native/new.c': b'new native source',
            '.gitignore': b'/ignored/\n', 'ignored/result.c': b'ignored',
            'Forme/audit.md': b'internal', 'Workspace/toolchain/compiler': b'toolchain',
            'installfiles/release.zip': b'release', 'snapshots/old.c': b'old',
            'trash/stale.c': b'waste', '.git-credentials': b'fixture, not a credential',
            'AGENTS.md': b'Internal assistant instructions', 'old-release.zip': b'old release',
        }
        for name, value in content.items():
            path = repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        subprocess.run(['git', '-C', str(repository), 'add', 'apps/tracked.c', '.gitignore', 'Forme/audit.md'], check=True)
        (repository / 'apps/tracked.c').write_bytes(b'actual modified source')
        files = package.source_files(repository)
        self.assertEqual(set(files), {'apps/tracked.c', '.gitignore', 'lib/espeak/native/new.c'})
        self.assertEqual(files['apps/tracked.c'].read_bytes(), b'actual modified source')

    def test_source_archive_checks_every_entry_and_freeze_drift(self):
        source = self.directory / 'native.c'
        source.write_bytes(b'native source fixture')
        files = {'rockbox/lib/espeak/native/fixture.c': source}
        expected = package.hashes(files)
        archive = self.directory / 'source-fixture.tar.gz'
        package.write_source_archive(archive, files, expected, {}, {'version': 'fixture'})
        self.assertEqual(package.verify_source_archive(archive, expected)['files'], expected)
        source.write_bytes(b'changed after freeze')
        with self.assertRaisesRegex(RuntimeError, 'Source changed'):
            package.write_source_archive(self.directory / 'drift.tar.gz', files, expected, {}, {})

    def test_diagnostic_reports_exclusion_is_scoped_without_losing_tools_or_other_reports(self):
        repository = self.directory / 'diagnostic-source-fixture'
        repository.mkdir()
        subprocess.run(['git', 'init', '-q', str(repository)], check=True)
        kept = {
            'tools/diagnostics/hiby_r1_connectivity/Connectivity-diagnostics.ps1',
            'tools/diagnostics/hiby_r1_connectivity/launcher.sh',
            'tools/diagnostics/hiby_r1_audio/Audio-diagnostics.ps1',
            'tools/diagnostics/hiby_r1_audio/r1_audio_trace.c',
            'tools/tests/test_hiby_connectivity_diagnostics.py',
            'tools/tests/fixtures/hiby_connectivity_diagnostic_utility.py',
            'Reports/project-notes.txt', 'docs/Reports/README.txt',
            'tools/diagnostics/another_tool/Reports/result.txt',
            'tools/diagnostics/hiby_r1_connectivity/docs/Reports/README.txt',
        }
        omitted = {
            'tools/diagnostics/hiby_r1_connectivity/Reports/card.json',
            'tools/diagnostics/hiby_r1_connectivity/Reports/nested/radio.txt',
            'tools/diagnostics/hiby_r1_audio/Reports/audio.json',
            'tools/diagnostics/hiby_r1_audio/reports/nested/capture.txt',
        }
        for name in sorted(kept | omitted):
            path = repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Synthetic source/report fixture: ' + name, encoding='utf-8')
        subprocess.run(['git', '-C', str(repository), 'add', '.'], check=True)
        files = package.source_files(repository)
        self.assertEqual(set(files), kept)
        archive_files = {'rockbox/' + name: path for name, path in files.items()}
        expected = package.hashes(archive_files)
        archive = self.directory / 'scoped-diagnostic-sources.tar.gz'
        package.write_source_archive(archive, archive_files, expected, {}, {'version': 'diagnostic-source-fixture'})
        self.assertEqual(package.verify_source_archive(archive, expected)['files'], expected)
        self.assertTrue(package.source_allowed('tools/diagnostics/hiby_r1_connectivity/report_helpers.py'))
        self.assertTrue(package.source_allowed('apps/Reports/menu.c'))

    def test_card_diagnostic_state_is_rejected_without_banning_tool_sources(self):
        for name in sorted(package.DIAGNOSTIC_CARD_STATE_NAMES):
            for spelling in (name, name.upper(), name + '.pending'):
                with self.subTest(name=spelling), self.assertRaisesRegex(RuntimeError, 'saved runtime state'):
                    package.validate_package_entry('.rockbox/' + spelling, b'diagnostic fixture')
        self.assertFalse(package.diagnostic_card_state(PurePosixPath('.rockbox/rockbox.r1')))
        self.assertFalse(package.diagnostic_card_state(PurePosixPath('.rockbox/docs/.connectivity-state.json')))

    def test_source_archive_rejects_unlisted_files_and_credentials(self):
        for number, name in enumerate(('rockbox/apps/new.c', 'rockbox/.git/config')):
            path = self.directory / f'invalid-source-{number}.tar.gz'
            with tarfile.open(path, 'x:gz') as archive:
                for relative, data in ((name, b'fixture'), ('source-manifest.json', b'{"files":{}}')):
                    member = tarfile.TarInfo(relative)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                package.verify_source_archive(path)

    def test_containment_and_in_use_previous_release(self):
        with self.assertRaisesRegex(RuntimeError, 'escapes'):
            package.contained(self.directory.parent, self.directory)
        release = self.release_root / 'clipplus'
        release.mkdir(parents=True)
        original = release / 'previous.zip'
        original.write_bytes(b'previous release fixture')
        with mock.patch.object(package, 'assert_unused', side_effect=RuntimeError('in use')):
            with self.assertRaisesRegex(RuntimeError, 'in use'):
                package.preserve(release, 'release', self.directory)
        self.assertTrue(original.is_file())

    def test_previous_release_moves_with_structure_and_hashes(self):
        release = self.release_root / 'clipplus'
        release.mkdir(parents=True)
        original = release / 'previous.zip'
        original.write_bytes(b'previous release fixture')
        with mock.patch.object(package, 'assert_unused'), mock.patch.object(package, 'ensure_ignored'):
            destination = package.preserve(release, 'release', self.directory)
        self.assertFalse(release.exists())
        self.assertEqual((destination / original.name).read_bytes(), b'previous release fixture')
        self.assertEqual(destination.relative_to(self.materials_root(package.ROOT, 'Snapshots')).parts[-2:], ('installfiles', 'clipplus'))

    def test_missing_source_freeze_never_starts_a_build(self):
        with mock.patch.object(package.subprocess, 'run') as run:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                package.main([])
        self.assertEqual(error.exception.code, 2)
        run.assert_not_called()

    def test_toolchain_rejects_wrong_major_and_target(self):
        for replies in (['12.3.0', 'arm-none-eabi'], ['13.3.0', 'x86_64-linux-gnu']):
            with mock.patch.object(package.subprocess, 'check_output', side_effect=replies):
                with self.assertRaisesRegex(RuntimeError, 'GCC 13'):
                    package.toolchain_versions()

    def test_source_pairing_and_outer_manifest_checksum(self):
        source = self.directory / 'source.c'
        source.write_bytes(b'Corresponding source fixture, not player code')
        files = {'rockbox/apps/fixture.c': source}
        source_hashes = package.hashes(files)
        archive = self.directory / 'source-fixture.tar.gz'
        package.write_source_archive(archive, files, source_hashes, {}, {'version': 'fixture'})
        self.metadata['source_archive'] = {'name': archive.name, 'sha256': package.sha256(archive.read_bytes())}
        self.metadata['source_inventory_sha256'] = package.sha256(package.json_bytes(source_hashes))
        output = self.create()
        sums = self.directory / 'SHA256SUMS'
        sums.write_text(''.join(f'{package.sha256(path.read_bytes())}  {path.name}\n'
                                for path in (output, archive)), encoding='utf-8')
        self.assertEqual(package.verify_release(output)['version'], 'fixture')
        sums.write_text('0' * 64 + '  ' + output.name + '\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'SHA256SUMS mismatch'):
            package.verify_release(output)

    def test_missing_notice_and_packaging_only_gcc_notice_are_rejected(self):
        missing = self.directory / 'missing-copyright'
        with mock.patch.object(package, 'RUNTIME_NOTICES', {'newlib-COPYRIGHT.txt': missing}):
            with self.assertRaisesRegex(RuntimeError, 'Missing runtime license'):
                package.runtime_notices()
        notice = self.directory / 'gcc-copyright'
        notice.write_text('This covers only compiler packaging', encoding='utf-8')
        with mock.patch.object(package, 'RUNTIME_NOTICES', {'GCC13-COPYRIGHT-and-RUNTIME-EXCEPTION.txt': notice}):
            with self.assertRaisesRegex(RuntimeError, 'runtime exception'):
                package.runtime_notices()

    def test_missing_bundled_runtime_notice_rejected(self):
        output = self.rewrite(self.create(), {'.rockbox/espeak-clipplus/newlib-COPYRIGHT.txt': None}, True)
        with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
            package.verify_firmware_zip(output)

    def test_arm_math_notices_match_verified_complete_upstream_blocks(self):
        path = package.RUNTIME_NOTICES['newlib-Arm-BSD-3-Clause.txt']
        self.assertEqual(path, package.ROOT / 'docs/NEWLIB-ARM-NOTICES.txt')
        text = path.read_text(encoding='utf-8')
        blocks = re.findall(r'/\*.*?\*/', text, re.S)
        self.assertEqual([package.sha256(block.encode('utf-8')) for block in blocks], [
            '53238646bad776698b01918350143a089b400ac46bc5d3fc75dbb29f887dc6b8',
            '955d9a5be20c8ac6f32b66b6a1c7e0e3bca8d725338f5011e131153d62e074a0'])
        self.assertIn('Copyright (c) 2018 Arm Ltd.  All rights reserved.', blocks[0])
        self.assertIn('Copyright (c) 2017-2018 Arm Ltd.  All rights reserved.', blocks[1])

    def test_missing_bundled_arm_math_notice_rejected(self):
        name = '.rockbox/espeak-clipplus/newlib-Arm-BSD-3-Clause.txt'
        output = self.rewrite(self.create(), {name: None}, True)
        with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
            package.verify_firmware_zip(output)

    def test_arm_notice_reaches_binary_and_source_without_generated_path_collision(self):
        name = 'newlib-Arm-BSD-3-Clause.txt'
        path = package.RUNTIME_NOTICES[name]
        original = 'rockbox/docs/NEWLIB-ARM-NOTICES.txt'
        generated = 'rockbox/docs/native-runtime-licenses/' + name
        with mock.patch.object(package, 'source_files', side_effect=[{'docs/NEWLIB-ARM-NOTICES.txt': path}, {}]), \
                mock.patch.object(package, 'source_modes', return_value={}), \
                mock.patch.object(package, 'runtime_files', return_value={}), \
                mock.patch.object(package, 'runtime_notices', return_value={name: path}):
            files, expected, modes = package.freeze_sources(self.directory)
        self.assertEqual(set(files), {original, generated})
        source_archive = self.directory / 'arm-notice-source-fixture.tar.gz'
        package.write_source_archive(source_archive, files, expected, modes, {'version': 'fixture'})
        source_manifest = package.verify_source_archive(source_archive, expected)
        self.assertEqual(source_manifest['files'][generated], package.sha256(path.read_bytes()))
        binary_path = '.rockbox/espeak-clipplus/' + name
        self.additions[binary_path] = path.read_bytes()
        binary = self.create()
        package.verify_firmware_zip(binary)
        with zipfile.ZipFile(binary) as archive:
            self.assertEqual(archive.read(binary_path), path.read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
