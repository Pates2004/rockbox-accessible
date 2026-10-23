import contextlib
import datetime
import io
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tarfile
import unittest
from unittest import mock

from materials_fixtures import materials_resolver
import zipfile
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_espeak_hiby as package


NOTICE = (b'GNU GENERAL PUBLIC LICENSE\nGNU LESSER GENERAL PUBLIC LICENSE\n'
          b'GCC RUNTIME LIBRARY EXCEPTION\nVersion 3.1\nSynthetic license metadata fixture.\n')


def elf_fixture(module=False, suffix='.rock', target=124, version=None, exported=True, versions=None,
                runtime=False, needed=None, definitions=None):
    address = 0x10000
    payload = b'Synthetic ELF metadata fixture; no executable instructions.\0'
    if module:
        version = version if version is not None else (50 if suffix == '.codec' else package.PLUGIN_ABI)
        payload = struct.pack('<IHHII', 0x52434f44 if suffix == '.codec' else 0x526f634b,
                              target, version, 0, 0) + bytes(24)
        if suffix == '.ovl' and version == 1:
            payload = payload[:24] + struct.pack('<H', package.PLUGIN_ABI) + payload[26:]
    names = ['__header'] if module else (['snd_pcm_open', 'snd_pcm_writei', 'snd_asoundlib_version', 'snd_mixer_open']
                                       if runtime else list(package.REQUIRED_SYMBOLS))
    needed = list(needed) if needed is not None else (sorted(package.ALSA_DEPENDENCIES) if runtime else
                                                    ([] if module else ['libc.so.6']))
    definitions = definitions if definitions is not None else (['libasound.so.2', 'ALSA_0.9'] if runtime else [])
    versions = versions if versions is not None else (() if module else ('GLIBC_2.16',))
    strings = b'\0libc.so.6\0' + b''.join(name.encode() + b'\0' for name in [*needed, *names, *versions, *definitions])
    sections = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    program_count = 1 if module or runtime else 2
    image = bytearray(52 + 32 * program_count)

    def section(kind, content, flags=0, link=0, entry_size=0):
        image.extend(bytes(-len(image) % 4))
        offset = len(image)
        image.extend(content)
        sections.append((0, kind, flags, address + offset if flags & 2 else 0,
                         offset, len(content), link, 0, 4, entry_size))
        return len(sections) - 1

    strings_index = section(3, strings, 2)
    data_index = section(1, payload, 3)
    data_offset = sections[data_index][4]
    symbols = bytearray(16)
    for name in names:
        symbols.extend(struct.pack('<IIIBBH', strings.index(name.encode() + b'\0'),
                                   address + data_offset, len(payload),
                                   (0x11 if exported else 0x01) if module else 0x12, 0, data_index))
    section(11, symbols, 2, strings_index, 16)
    section(0x7000002a, struct.pack('<HBBBBBBIIII', 0, 1 if runtime else 32, 0 if runtime else 2,
                                  1, 1, 0, 1, 0, 0, 0, 0), 2)
    dynamic = b''.join(struct.pack('<iI', 1, strings.index(name.encode() + b'\0')) for name in needed)
    if runtime:
        dynamic += struct.pack('<iI', 14, strings.index(b'libasound.so.2\0'))
    dynamic += struct.pack('<iI', 0, 0)
    section(6, dynamic, 2, strings_index, 8)
    if versions:
        version_data = struct.pack('<HHIII', 1, len(versions), 1, 16, 0)
        for index, name in enumerate(versions):
            version_data += struct.pack('<IHHII', 0, 0, index + 2, strings.index(name.encode() + b'\0'),
                                        16 if index + 1 < len(versions) else 0)
        version_index = section(0x6ffffffe, version_data, 2, strings_index)
        version_entry = list(sections[version_index])
        version_entry[7] = 1
        sections[version_index] = tuple(version_entry)
    if definitions:
        version_data = b''
        for index, name in enumerate(definitions):
            version_data += struct.pack('<HHHHIII', 1, 0, index + 1, 1, 0, 20,
                                        28 if index + 1 < len(definitions) else 0)
            version_data += struct.pack('<II', strings.index(name.encode() + b'\0'), 0)
        version_index = section(0x6ffffffd, version_data, 2, strings_index)
        version_entry = list(sections[version_index])
        version_entry[7] = len(definitions)
        sections[version_index] = tuple(version_entry)
    interpreter = len(image)
    if not (module or runtime):
        image.extend(b'/lib/ld.so.1\0')
    image.extend(bytes(-len(image) % 4))
    section_offset = len(image)
    for entry in sections:
        image.extend(struct.pack('<IIIIIIIIII', *entry))
    image[:16] = b'\x7fELF\x01\x01\x01' + bytes(9)
    struct.pack_into('<HHIIIIIHHHHHH', image, 16, 3 if module or runtime else 2, 8, 1,
                     0 if module or runtime else address + data_offset, 52, section_offset,
                     0x1007 if runtime else 0x70001000, 52, 32, program_count, 40, len(sections), 0)
    struct.pack_into('<IIIIIIII', image, 52, 1, 0, address, address, len(image), len(image), 7, 0x1000)
    if not (module or runtime):
        struct.pack_into('<IIIIIIII', image, 84, 3, interpreter, address + interpreter,
                         address + interpreter, 13, 13, 4, 1)
    return bytes(image)


def catalog(voice=True, identifier=124):
    return bytes([0x9a if voice else 0x1a, 6, identifier, 0]) + struct.pack('>HHH', 1, 6, 10) + b'\0\x01Test\0'


def build_info():
    return b'Target: hibyr1\nTarget id: 124\nCPU: hosted\nBinary: rockbox.r1\nVersion: fixture\n'


def evidence(needed=()):
    return {'needed': list(needed), 'version_requirements': ['GLIBC_2.16'] if needed else [],
            'readelf_sha256': 'a' * 64}


class HibyDefaultProfileTests(unittest.TestCase):
    def test_native_profile_seeds_minus_25_decibels_in_centibels(self):
        native_lines = package.DEFAULT_CONFIG.splitlines()
        shared_lines = package.shared.DEFAULT_CONFIG.splitlines()
        self.assertEqual([line for line in native_lines if line.startswith(b'volume:')],
                         [b'volume: -250'])
        self.assertEqual([line for line in native_lines if not line.startswith(b'volume:')],
                         [line for line in shared_lines if not line.startswith(b'volume:')])

    def test_shared_profile_keeps_original_volume(self):
        self.assertEqual([line for line in package.shared.DEFAULT_CONFIG.splitlines()
                          if line.startswith(b'volume:')], [b'volume: -25'])

    def test_fresh_profiles_do_not_override_the_core_interface_sound_default(self):
        for configuration in (package.DEFAULT_CONFIG, package.shared.DEFAULT_CONFIG):
            with self.subTest(configuration=configuration):
                self.assertFalse(any(line.startswith(b'keyclick:') for line in configuration.splitlines()))

    def test_native_profile_never_imports_existing_user_configuration(self):
        for configuration in (package.shared.DEFAULT_CONFIG, package.DEFAULT_CONFIG,
                              package.DEFAULT_CONFIG + b'tts rate: 200\n'):
            with self.subTest(configuration=configuration), io.BytesIO() as base, io.BytesIO() as output:
                with zipfile.ZipFile(base, 'w') as archive:
                    archive.writestr('.rockbox/config.cfg', configuration)
                base.seek(0)
                with self.assertRaisesRegex(RuntimeError, 'pre-existing profile'):
                    package.write_firmware_zip(base, output,
                                               {'.rockbox/config.cfg': package.DEFAULT_CONFIG}, {})
                self.assertEqual(output.getvalue(), b'')


class HibyPackageTests(unittest.TestCase):
    def test_radio_guides_are_required_for_new_packages_only(self):
        guides = {'RADIO-DYNAMIC.md', 'RADIO-DYNAMIC-PL.md'}
        for version in ('r34-alpha9-20261017', 'r34-alpha12-20261019'):
            with self.subTest(previous=version):
                manifest = {'version': version, 'files': {}}
                self.assertTrue(guides.isdisjoint(package.release_documents(manifest)))
                manifest['files'] = {package.TARGET.document_prefix + name: 'witness' for name in guides}
                self.assertTrue(guides.issubset(package.release_documents(manifest)))
        for version in ('r34-alpha13-20261020', 'future-release'):
            with self.subTest(current=version):
                self.assertTrue(guides.issubset(package.release_documents({'version': version, 'files': {}})))

    def test_current_talkbox_and_list_guides_are_all_required(self):
        guides = {'ESPEAK-ROCKBOX.md', 'ESPEAK-ROCKBOX-PL.md',
                  'ACCESSIBILITY-LISTS.md', 'ACCESSIBILITY-LISTS-PL.md'}
        for version in ('r34-alpha11-20261017', 'r34-alpha12-20261018', 'future-release'):
            with self.subTest(version=version):
                self.assertTrue(guides.issubset(package.release_documents({'version': version, 'files': {}})))

    def test_current_packages_reject_each_missing_radio_guide(self):
        original = self.directory
        for name in ('RADIO-DYNAMIC.md', 'RADIO-DYNAMIC-PL.md'):
            with self.subTest(name=name):
                self.directory = original / name
                self.directory.mkdir()
                key = package.TARGET.document_prefix + name
                content = self.additions.pop(key)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
                        package.verify_firmware_zip(self.create())
                finally:
                    self.additions[key] = content
        self.directory = original

    def test_previous_releases_do_not_require_new_menu_guides(self):
        guides = {'ESPEAK-ROCKBOX.md', 'ESPEAK-ROCKBOX-PL.md',
                  'ACCESSIBILITY-LISTS.md', 'ACCESSIBILITY-LISTS-PL.md'}
        for version in ('r34-alpha1-20261014', 'r34-alpha5-20261015', 'r34-alpha9-20261017', 'r34-alpha10-20261017'):
            with self.subTest(version=version):
                manifest = {'version': version, 'files': {}}
                self.assertTrue(guides.isdisjoint(package.release_documents(manifest)))
                manifest['files'] = {package.TARGET.document_prefix + name: 'witness' for name in guides}
                self.assertTrue(guides.issubset(package.release_documents(manifest)))

    def test_current_packages_reject_each_missing_talkbox_or_list_guide(self):
        original = self.directory
        for name in ('ESPEAK-ROCKBOX.md', 'ESPEAK-ROCKBOX-PL.md',
                     'ACCESSIBILITY-LISTS.md', 'ACCESSIBILITY-LISTS-PL.md'):
            with self.subTest(name=name):
                self.directory = original / name
                self.directory.mkdir()
                key = package.TARGET.document_prefix + name
                content = self.additions.pop(key)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
                        package.verify_firmware_zip(self.create())
                finally:
                    self.additions[key] = content
                    self.directory = original

    def test_current_abi_alpha10_fixture_verifies_without_the_new_guides(self):
        self.metadata['version'] = 'r34-alpha10-20261017'
        self.base['.rockbox/rockbox-info.txt'] = self.base['.rockbox/rockbox-info.txt'].replace(
            b'Version: fixture', b'Version: r34-alpha10-20261017')
        for name in ('ESPEAK-ROCKBOX.md', 'ESPEAK-ROCKBOX-PL.md',
                     'ACCESSIBILITY-LISTS.md', 'ACCESSIBILITY-LISTS-PL.md'):
            self.additions.pop(package.TARGET.document_prefix + name)
        output, source = self.source_pair()
        self.data_validation.side_effect = AssertionError('Legacy verification must not inspect checkout')
        self.assertEqual(package.verify_release(output, source)['version'], 'r34-alpha10-20261017')
        self.data_validation.assert_not_called()

    def test_connectivity_guides_required_in_new_release_without_rejecting_old_pairs(self):
        guides = {'ACCESSIBILITY-SHORTCUT.md', 'ACCESSIBILITY-SHORTCUT-PL.md',
                  'HIBY-R1-CONNECTIVITY.md', 'HIBY-R1-CONNECTIVITY-PL.md'}
        for version in ('r34-alpha1-20261014', 'r34-alpha2-20261015',
                        'r34-alpha3-20261015', 'r34-alpha4-20261015', 'r34-alpha5-20261015'):
            with self.subTest(version=version):
                manifest = {'version': version, 'files': {}}
                self.assertTrue(guides.isdisjoint(package.release_documents(manifest)))
                manifest['files'] = {package.TARGET.document_prefix + name: 'witness' for name in guides}
                self.assertTrue(guides.issubset(package.release_documents(manifest)))
        for version in ('r34-alpha6-20261016', 'future-release'):
            with self.subTest(version=version):
                self.assertTrue(guides.issubset(package.release_documents({'version': version, 'files': {}})))

    def test_screen_guides_required_in_new_release_without_rejecting_old_pairs(self):
        guides = {'ACCESSIBILITY-SCREEN.md', 'ACCESSIBILITY-SCREEN-PL.md'}
        for version in ('r34-alpha1-20261014', 'r34-alpha2-20261015',
                        'r34-alpha3-20261015', 'r34-alpha4-20261015'):
            with self.subTest(version=version):
                manifest = {'version': version, 'files': {}}
                self.assertTrue(guides.isdisjoint(package.release_documents(manifest)))
                manifest['files'] = {package.TARGET.document_prefix + name: 'witness' for name in guides}
                self.assertTrue(guides.issubset(package.release_documents(manifest)))
        for version in ('r34-alpha5-20261015', 'future-release'):
            with self.subTest(version=version):
                manifest = {'version': version, 'files': {}}
                self.assertTrue(guides.issubset(package.release_documents(manifest)))

    def test_private_bookmark_files_rejected(self):
        for name in ('book.txt.bmark', 'BOOK.TXT.BMARK', 'book.txt.bmark.tmp',
                     'book.txt.bmark.t01', 'book.txt.bmark.T0F',
                     'book.bookmark', 'book.BOOKMARK.pending'):
            with self.subTest(name=name), self.assertRaisesRegex(
                    RuntimeError, 'dirty runtime profile'):
                package.validate_package_entry('.rockbox/' + name, b'private history')

    def test_accessibility_profiles_rejected(self):
        for prefix in ('.rockbox/', '.rockbox/cache/'):
            for name in ('accessibility.cfg', 'ACCESSIBILITY.CFG',
                         'accessibility-typing-echo.cfg', 'ACCESSIBILITY-TYPING-ECHO.CFG', 'accessibility-typing-echo.cfg.tmp',
                         'accessibility-lock.cfg', 'ACCESSIBILITY-LOCK.CFG', 'accessibility-lock.cfg.future',
                         'touch-sensitivity.cfg', 'TOUCH-SENSITIVITY.CFG', 'touch-sensitivity.cfg.tmp',
                         'accessibility-screen.cfg', 'ACCESSIBILITY-SCREEN.CFG',
                         'tts-reader.cfg', 'TTS-READER.CFG', 'Tts-Reader.Cfg',
                         'tts-reader.cfg.tmp', 'TTS-READER.CFG.NEW', 'tts-reader.cfg.future', 'Tts-Reader.Cfg.BaK',
                         'bluetooth.cfg', 'BLUETOOTH.CFG', 'BlueTooth.Cfg',
                         'bluetooth.cfg.tmp', 'BLUETOOTH.CFG.NEW', 'bluetooth.cfg.future', 'BlueTooth.Cfg.BaK',
                         'empty-feedback.cfg', 'EMPTY-FEEDBACK.CFG', 'Empty-Feedback.Cfg',
                         'empty-feedback.cfg.tmp', 'EMPTY-FEEDBACK.CFG.NEW', 'empty-feedback.cfg.future',
                         'Empty-Feedback.Cfg.BaK',
                         'accessibility-shortcut.cfg', 'ACCESSIBILITY-SHORTCUT.CFG',
                         'accessibility-shortcut.cfg.tmp', 'connectivity.cfg',
                         'CONNECTIVITY.CFG', 'connectivity.cfg.tmp', 'connectivity.cfg.new',
                         'accessibility-screen.cfg.tmp', 'accessibility-screen.cfg.future',
                         'accessibility-typing.cfg', 'ACCESSIBILITY-TYPING.CFG',
                         'accessibility-typing.cfg.tmp', 'accessibility-typing.cfg.bak',
                         'accessibility.cfg.pending', 'Accessibility.cfg.BAK',
                         'accessibility.cfg.future'):
                with self.subTest(name=prefix + name), self.assertRaisesRegex(
                        RuntimeError, 'dirty runtime profile'):
                    package.validate_package_entry(prefix + name, b'private mapping')

    @classmethod
    def setUpClass(cls):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        cls.results = package.project_materials_root(package.ROOT) / 'r1-screen-state-20261015/espeak-builder-tests/hiby' / stamp
        cls.results.mkdir(parents=True)
        print(f'Retained synthetic ELF/package regression evidence (never executed): {cls.results}')

    def setUp(self):
        self.directory = self.results / self._testMethodName
        self.directory.mkdir()
        self.materials_root = materials_resolver(self.directory / 'source', self.directory / 'central')
        self.materials = self.materials_root(package.ROOT)
        self.release_root = self.materials_root(package.ROOT, 'installfiles')
        self.base = {package.FIRMWARE: elf_fixture(),
                     '.rockbox/database.ignore': b'',
                     '.rockbox/rockbox-info.txt': build_info(),
                     '.rockbox/rocks/apps/test.rock': elf_fixture(module=True),
                     '.rockbox/codecs/test.codec': elf_fixture(module=True, suffix='.codec'),
                     '.rockbox/rocks/viewers/test.ovl': elf_fixture(module=True, suffix='.ovl', version=1)}
        self.additions = {package.DATA_PREFIX + name: b'Synthetic supplied data fixture'
                          for name in package.shared.REQUIRED_DATA}
        for language in ('english', 'polski'):
            self.base[package.CATALOG_PREFIX + language + '.lng'] = catalog(False)
            self.additions[package.CATALOG_PREFIX + language + '.vstrings'] = catalog()
        self.additions.update({package.TARGET.document_prefix + name: b'Synthetic notice/document fixture'
                               for name in package.documents()})
        self.additions[package.NOTICE_PREFIX + 'NOTICE.txt'] = NOTICE
        self.additions['.rockbox/config.cfg'] = package.DEFAULT_CONFIG
        self.additions[package.AUTOSTART_FILE] = package.AUTOSTART_SEED
        modules = {name: package.validate_module(name, data) for name, data in self.base.items()
                   if Path(name).suffix in package.MODULE_SUFFIXES}
        self.metadata = {'target': 'hibyr1', 'plugin_abi': package.PLUGIN_ABI, 'version': 'fixture',
                         'engine_revision': package.ENGINE_REVISION, 'hardware_tested': False,
                         'channel': 'diagnostic', 'firmware_library_compatibility': 'untested',
                         'autostart': package.AUTOSTART,
                         'memory_configuration_mib': 16, 'core_arena_mib': 15,
                         'application': package.validate_elf(self.base[package.FIRMWARE]), 'modules': modules,
                         'runtime_data': {name[len(package.DATA_PREFIX):]: package.sha256(data)
                                          for name, data in self.additions.items() if name.startswith(package.DATA_PREFIX)},
                         'voice_catalogs': {name[len(package.CATALOG_PREFIX):]: package.sha256(data)
                                           for name, data in self.additions.items() if name.endswith('.vstrings')},
                         'runtime_notice_hashes': {'NOTICE.txt': package.sha256(NOTICE)},
                         'elf_evidence': {name: evidence() for name in modules}}
        self.metadata['elf_evidence'].update({'rockbox.elf': evidence(['libc.so.6']),
                                               package.FIRMWARE: evidence(['libc.so.6'])})
        self.dictionary_sources = {'pl_list': b'Synthetic Polish source list',
                                   'pl_rules': b'Synthetic Polish source rules'}
        entries = {**{'espeak-data/' + name: digest for name, digest in self.metadata['runtime_data'].items()},
                   **{'dictsource/' + name: package.sha256(content)
                      for name, content in self.dictionary_sources.items()}}
        self.data_manifest = ''.join(digest + '  ' + name + '\n' for name, digest in sorted(entries.items())).encode()
        self.data_sidecar = package.json_bytes({'engine_revision': package.ENGINE_REVISION,
                                                'purpose': 'Synthetic builder provenance fixture'})
        self.provenance = {'engine_revision': package.ENGINE_REVISION,
                           'runtime_data': self.metadata['runtime_data'],
                           'dictsource': {name: package.sha256(content)
                                          for name, content in self.dictionary_sources.items()},
                           'data_manifest_sha256': package.sha256(self.data_manifest),
                           'data_provenance_sha256': package.sha256(self.data_sidecar)}
        validation = mock.patch.object(package, 'validate_supplied_data', return_value=self.provenance)
        self.data_validation = validation.start()
        self.addCleanup(validation.stop)

    def create(self):
        base = self.directory / 'base-metadata-fixture.zip'
        output = self.directory / 'package-metadata-fixture.zip'
        with zipfile.ZipFile(base, 'x') as archive:
            for name, content in self.base.items():
                archive.writestr(name, content)
        package.write_firmware_zip(base, output, self.additions, self.metadata)
        return output

    def rewrite(self, original, changes):
        output = self.directory / 'changed-metadata-fixture.zip'
        with zipfile.ZipFile(original) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        for name, content in changes.items():
            if content is None:
                contents.pop(name)
            else:
                contents[name] = content
        with zipfile.ZipFile(output, 'x') as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
        return output

    def source_pair(self, extra_sources=None):
        files = {}
        provenance_sources = {}
        if self.metadata.get('espeak_data_provenance') is not None:
            provenance_sources = {
                'rockbox/lib/espeak/DATA.sha256': self.data_manifest,
                'rockbox/lib/espeak/DATA-PROVENANCE.json': self.data_sidecar,
                **{'espeak-1.44.05-source/dictsource/' + name: content
                   for name, content in self.dictionary_sources.items()},
            }
        for name, content in {'rockbox/apps/fixture.c': b'Synthetic corresponding source',
            **{'rockbox/' + relative: self.additions[package.TARGET.document_prefix + name]
               for name, relative in package.documents().items()
               if package.TARGET.document_prefix + name in self.additions},
            **{'espeak-1.44.05-source/espeak-data/' + name: self.additions[package.DATA_PREFIX + name]
               for name in self.metadata['runtime_data']},
            **{'rockbox/docs/native-runtime-licenses/hibyr1/' + name[len(package.NOTICE_PREFIX):]: content
               for name, content in self.additions.items() if name.startswith(package.NOTICE_PREFIX)},
            **provenance_sources, **(extra_sources or {})}.items():
            path = self.directory / 'source-inputs' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            files[name] = path
        frozen = package.hashes(files)
        source = self.directory / 'source-metadata-fixture.tar.gz'
        package.write_source_archive(source, files, frozen, {}, self.metadata)
        self.metadata['source_inventory_sha256'] = package.sha256(package.json_bytes(frozen))
        self.metadata['source_archive'] = {'name': source.name, 'sha256': package.sha256(source.read_bytes())}
        output = self.create()
        (self.directory / 'SHA256SUMS').write_text(''.join(f'{package.sha256(path.read_bytes())}  {path.name}\n'
            for path in (output, source)), encoding='utf-8')
        return output, source

    def test_complete_diagnostic_metadata_package_and_source_pair(self):
        output, source = self.source_pair()
        manifest = package.verify_release(output, source)
        self.assertEqual(manifest['channel'], 'diagnostic')
        self.assertFalse(manifest['hardware_tested'])
        self.assertEqual(manifest['core_arena_mib'], 15)
        self.assertEqual(manifest['files']['.rockbox/database.ignore'], package.sha256(b''))
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read('.rockbox/database.ignore'), b'')
        self.assertIn('HIBY-R1-CONTROLS.md', package.documents())
        self.assertEqual(package.documents()['CZYTAJ.md'], 'docs/ESPEAK-HIBYR1-PL.md')

    def test_new_data_provenance_binds_runtime_and_corresponding_sources_offline(self):
        self.metadata['espeak_data_provenance'] = self.provenance
        output, source = self.source_pair()
        self.data_validation.side_effect = AssertionError('Offline archive verification must not inspect checkout')
        manifest = package.verify_release(output, source)
        self.assertEqual(manifest['espeak_data_provenance'], self.provenance)
        self.data_validation.assert_not_called()

    def test_current_hardening_packages_require_each_appearance_and_power_guide(self):
        self.metadata['espeak_data_provenance'] = self.provenance
        original = self.directory
        for name in ('INTERFACE-APPEARANCE.md', 'INTERFACE-APPEARANCE-PL.md',
                     'HIBY-R1-POWER.md', 'HIBY-R1-POWER-PL.md'):
            with self.subTest(name=name):
                self.directory = original / name
                self.directory.mkdir()
                key = package.TARGET.document_prefix + name
                content = self.additions.pop(key)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
                        package.verify_firmware_zip(self.create())
                finally:
                    self.additions[key] = content
                    self.directory = original

    def test_alpha3_archives_remain_verifiable_without_later_hardening_guides(self):
        self.metadata['version'] = 'r34-alpha3-20261015'
        self.metadata['espeak_data_provenance'] = self.provenance
        self.base['.rockbox/rockbox-info.txt'] = self.base['.rockbox/rockbox-info.txt'].replace(
            b'Version: fixture', b'Version: r34-alpha3-20261015')
        for name in ('INTERFACE-APPEARANCE.md', 'INTERFACE-APPEARANCE-PL.md',
                     'HIBY-R1-POWER.md', 'HIBY-R1-POWER-PL.md'):
            self.additions.pop(package.TARGET.document_prefix + name)
        output, source = self.source_pair()
        self.data_validation.side_effect = AssertionError('Legacy archives must verify without checkout')
        self.assertEqual(package.verify_release(output, source)['version'], 'r34-alpha3-20261015')
        self.data_validation.assert_not_called()

    def test_legacy_verify_cli_needs_no_supplied_checkout(self):
        for name in ('ACCESSIBILITY-TYPING.md', 'ACCESSIBILITY-TYPING-PL.md',
                     'ACCESSIBILITY-CURTAIN.md', 'ACCESSIBILITY-CURTAIN-PL.md',
                     'HIBY-R1-NETWORK-EMULATION.md', 'HIBY-R1-NETWORK-EMULATION-PL.md'):
            self.additions.pop(package.TARGET.document_prefix + name)
        output, source = self.source_pair()
        self.data_validation.side_effect = AssertionError('Legacy verification must not inspect checkout')
        package.main(['--verify', str(output), '--source-archive', str(source),
                      '--espeak-source', str(self.directory / 'absent-checkout')])
        self.data_validation.assert_not_called()

    def test_new_provenance_packages_require_all_six_current_guides(self):
        self.metadata['espeak_data_provenance'] = self.provenance
        self.additions.pop(package.TARGET.document_prefix + 'ACCESSIBILITY-TYPING.md')
        with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
            package.verify_firmware_zip(self.create())

    def test_corresponding_dictionary_drift_rejected_with_recomputed_archive_hashes(self):
        self.metadata['espeak_data_provenance'] = self.provenance
        output, source = self.source_pair({
            'espeak-1.44.05-source/dictsource/pl_rules': b'Tampered synthetic source rules'})
        with self.assertRaisesRegex(ValueError, 'dictsource differs from provenance'):
            package.verify_release(output, source)

    def test_runtime_provenance_cannot_disagree_with_actual_package(self):
        self.metadata['espeak_data_provenance'] = dict(
            self.provenance, runtime_data=dict(self.provenance['runtime_data'], pl_dict='0' * 64))
        with self.assertRaisesRegex(ValueError, 'runtime differs from supplied-data provenance'):
            package.verify_firmware_zip(self.create())

    def test_provenance_hash_must_match_canonical_data_inventory(self):
        self.metadata['espeak_data_provenance'] = dict(self.provenance, data_manifest_sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'hashes differ from their provenance manifest'):
            package.verify_firmware_zip(self.create())

    def test_direct_packaging_data_drift_blocks_freeze_build_and_archives(self):
        self.data_validation.side_effect = ValueError('same-commit data drift')
        with mock.patch.object(package, 'freeze_sources') as freeze, \
                mock.patch.object(package, 'build_application') as build, \
                mock.patch.object(package, 'write_source_archive') as archive, \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(ValueError, 'same-commit data drift'):
                package.package_application(SimpleNamespace(), self.directory, {}, {}, self.directory / 'build')
        for action in (freeze, build, archive, preserve):
            action.assert_not_called()

    def test_same_commit_data_drift_blocks_main_before_preserve_freeze_or_build(self):
        source = self.directory / 'supplied'
        source.mkdir()
        self.data_validation.side_effect = ValueError('same-commit data drift')
        for mode in (['--build-only'], ['--stage-hardware-test', '--source-frozen',
                                      '--toolchain-notices', str(self.directory),
                                      '--alsa-source', str(self.directory / package.ALSA_SOURCE_NAME)]):
            with self.subTest(mode=mode), mock.patch.object(package.sys, 'platform', 'linux'), \
                    mock.patch.object(package.subprocess, 'check_output', return_value=package.ENGINE_REVISION), \
                    mock.patch.object(package, 'build_application') as build, \
                    mock.patch.object(package, 'package_application') as packaging, \
                    mock.patch.object(package, 'freeze_sources') as freeze, \
                    mock.patch.object(package.shared, 'preserve') as preserve, \
                    mock.patch.object(package, 'write_source_archive') as archive:
                with self.assertRaisesRegex(ValueError, 'same-commit data drift'):
                    package.main(['--version', 'fixture', '--espeak-source', str(source), *mode])
            for action in (build, packaging, freeze, preserve, archive):
                action.assert_not_called()

    def add_alsa(self):
        self.base[package.FIRMWARE] = elf_fixture(needed=['libc.so.6', 'libasound.so.2'])
        self.metadata['application'] = package.validate_elf(self.base[package.FIRMWARE])
        self.metadata['elf_evidence'][package.FIRMWARE] = evidence(['libasound.so.2', 'libc.so.6'])
        self.additions[package.ALSA_LIBRARY] = elf_fixture(runtime=True)
        self.metadata['bundled_runtime'] = {package.ALSA_LIBRARY: package.validate_alsa(self.additions[package.ALSA_LIBRARY])}
        self.metadata['system_runtime'] = {'libasound.so.2': {'path': 'synthetic-runtime-not-executed',
                                                           'sha256': package.sha256(self.additions[package.ALSA_LIBRARY])}}

    def test_required_alsa_is_not_merely_recorded_but_bundled(self):
        self.add_alsa()
        package.verify_firmware_zip(self.create())
        self.additions.pop(package.ALSA_LIBRARY)
        with self.assertRaisesRegex(RuntimeError, 'required bundled ALSA'):
            package.verify_firmware_zip(self.create_missing_alsa())

    def create_missing_alsa(self):
        output = self.directory / 'without-alsa.zip'
        base = self.directory / 'without-alsa-base.zip'
        with zipfile.ZipFile(base, 'x') as archive:
            for name, content in self.base.items():
                archive.writestr(name, content)
        package.write_firmware_zip(base, output, self.additions, self.metadata)
        return output

    def test_bundled_alsa_hash_is_bound_to_actual_linked_library(self):
        self.add_alsa()
        self.metadata['system_runtime']['libasound.so.2']['sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'actual linked toolchain runtime'):
            package.verify_firmware_zip(self.create())

    def test_compatible_mips1_alsa_does_not_relax_application_isa(self):
        runtime = elf_fixture(runtime=True)
        self.assertEqual(package.validate_alsa(runtime)['architecture'], 'MIPS1 little-endian O32 hard-float')
        with self.assertRaises(RuntimeError):
            package.validate_elf(runtime)
        for offset, content in ((4, bytes([2])), (5, bytes([2])), (18, struct.pack('<H', 62)),
                                (36, struct.pack('<I', 0x80001007))):
            invalid = bytearray(runtime)
            invalid[offset:offset + len(content)] = content
            with self.subTest(offset=offset), self.assertRaises(RuntimeError):
                package.validate_alsa(bytes(invalid))

    def test_alsa_rejects_missing_dependency_exports_versions_and_new_glibc(self):
        for image in (elf_fixture(runtime=True, needed=['libc.so.6']),
                      elf_fixture(runtime=True, definitions=['libasound.so.2']),
                      elf_fixture(runtime=True, versions=['GLIBC_2.23']),
                      elf_fixture(runtime=True).replace(b'snd_pcm_open', b'bad_pcm_open')):
            with self.subTest(digest=package.sha256(image)), self.assertRaises(RuntimeError):
                package.validate_alsa(image)

    def test_alsa_consumers_require_available_version_nodes(self):
        with self.assertRaisesRegex(RuntimeError, 'cannot satisfy'):
            package.validate_alsa_consumers(elf_fixture(runtime=True),
                                           {package.FIRMWARE: elf_fixture(versions=['ALSA_9.9'])})

    def test_alsa_sources_and_recipe_required_in_corresponding_source_delivery(self):
        self.add_alsa()
        output, source = self.source_pair()
        with self.assertRaisesRegex(RuntimeError, 'original ALSA corresponding source'):
            package.verify_release(output, source)

    def test_complete_alsa_source_archive_delivery_and_immutable_provenance(self):
        self.add_alsa()
        source = b'Synthetic ALSA source archive fixture, not an actual redistribution'
        recipe = b'Synthetic ALSA build recipe fixture'
        copying = b'Synthetic ALSA license fixture'
        recipe_name = 'official/tools/rockboxdev.sh'
        source_hash = package.sha256(source)
        recipe_hash = package.sha256(recipe)
        copying_hash = package.sha256(copying)
        self.metadata['alsa_sources'] = {package.ALSA_SOURCE_PREFIX + package.ALSA_SOURCE_NAME: source_hash,
                                         package.ALSA_SOURCE_PREFIX + recipe_name: recipe_hash}
        self.additions[package.NOTICE_PREFIX + 'alsa-lib-1.0.26/COPYING'] = copying
        self.metadata['runtime_notice_hashes']['alsa-lib-1.0.26/COPYING'] = copying_hash
        with mock.patch.object(package, 'ALSA_SOURCE_SHA256', source_hash), \
                mock.patch.object(package, 'ALSA_RECIPE_FILES', {recipe_name: recipe_hash}), \
                mock.patch.object(package, 'ALSA_COPYING_SHA256', copying_hash):
            output, archive = self.source_pair({package.ALSA_SOURCE_PREFIX + package.ALSA_SOURCE_NAME: source,
                                                package.ALSA_SOURCE_PREFIX + recipe_name: recipe})
            self.assertEqual(package.verify_release(output, archive)['alsa_sources'], self.metadata['alsa_sources'])
        with self.assertRaisesRegex(RuntimeError, 'original ALSA corresponding source'):
            package.verify_release(output, archive)

    def test_alsa_source_input_is_pinned_and_bound_to_toolchain_recipe(self):
        sdk = self.directory / 'sdk'
        source = sdk / 'downloads' / package.ALSA_SOURCE_NAME
        recipe = sdk / 'official/tools/rockboxdev.sh'
        source.parent.mkdir(parents=True)
        recipe.parent.mkdir(parents=True)
        source.write_bytes(b'Synthetic ALSA source input')
        recipe.write_bytes(b'Synthetic ALSA recipe input')
        copying = self.directory / 'COPYING'
        copying.write_bytes(b'Synthetic ALSA license input')
        source_hash, recipe_hash, copying_hash = [package.sha256(path.read_bytes()) for path in (source, recipe, copying)]
        provenance = self.directory / 'provenance.json'
        recipe_files = {'official/tools/rockboxdev.sh': recipe_hash}
        provenance.write_bytes(package.json_bytes({'recipe': {'files': recipe_files}, 'sources': {
            package.ALSA_SOURCE_NAME: {'archive_sha256': source_hash, 'source_provenance': {'sha256': source_hash},
                                       'original_files': {'alsa-lib-1.0.26/COPYING': copying_hash}}}}))
        notices = {'provenance.json': provenance, 'alsa-lib-1.0.26/COPYING': copying}
        with mock.patch.object(package, 'ALSA_SOURCE_SHA256', source_hash), \
                mock.patch.object(package, 'ALSA_RECIPE_FILES', recipe_files), \
                mock.patch.object(package, 'ALSA_COPYING_SHA256', copying_hash):
            files = package.alsa_source_files(source, notices)
            self.assertEqual(set(files), {package.ALSA_SOURCE_PREFIX + package.ALSA_SOURCE_NAME,
                                          package.ALSA_SOURCE_PREFIX + 'official/tools/rockboxdev.sh'})
            recipe.write_bytes(b'Changed recipe fixture')
            with self.assertRaisesRegex(RuntimeError, 'build recipe changed'):
                package.alsa_source_files(source, notices)
            source.write_bytes(b'Changed ALSA source fixture')
            with self.assertRaisesRegex(RuntimeError, 'original verified ALSA'):
                package.alsa_source_files(source, notices)

    def test_unrelated_system_libraries_cannot_be_smuggled_into_card_package(self):
        for name in ('.rockbox/libc.so.6', '.rockbox/ld.so.1', '.rockbox/libasound.so',
                     '.rockbox/lib/libasound.so.2', '.rockbox/libgcc_s.so.1'):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                package.validate_package_entry(name, elf_fixture(runtime=True))
        package.validate_package_entry('.rockbox/docs/audio.sources.txt', b'Ordinary non-library asset fixture')

    def test_factory_autostart_is_required_and_exact_not_a_user_profile(self):
        for content in (b'', b'0', b'0\n', bytes([2, 0, 0, 0]), bytes([0, 0, 0, 2]), bytes(8)):
            with self.subTest(content=content), self.assertRaisesRegex(RuntimeError, 'Autostart'):
                package.validate_package_entry(package.AUTOSTART_FILE, content)
        del self.additions[package.AUTOSTART_FILE]
        with self.assertRaisesRegex(RuntimeError, 'Missing runtime assets'):
            package.verify_firmware_zip(self.create())

    def test_hardware_test_identity_is_explicitly_unverified(self):
        self.metadata.update(channel='hardware-test', native_runtime_verified=False,
                             warning=package.HARDWARE_TEST_WARNING)
        manifest = package.verify_firmware_zip(self.create())
        self.assertEqual(manifest['channel'], 'hardware-test')
        self.assertFalse(manifest['native_runtime_verified'])
        self.assertFalse(manifest['hardware_tested'])
        with zipfile.ZipFile(self.directory / 'package-metadata-fixture.zip') as archive:
            self.assertEqual(archive.read(package.AUTOSTART_FILE), bytes(4))

    def test_hardware_test_cannot_claim_native_acceptance(self):
        self.metadata.update(channel='hardware-test', native_runtime_verified=True,
                             warning=package.HARDWARE_TEST_WARNING)
        with self.assertRaisesRegex(RuntimeError, 'unverified native execution'):
            package.verify_firmware_zip(self.create())

    def test_alsa_readelf_distinguishes_definitions_from_needed_versions(self):
        runtime = package.Elf32(elf_fixture(runtime=True), runtime=True)
        text = ('FP ABI: Hard float (double precision)\n' +
                ''.join(f'(NEEDED) Shared library: [{name}]\n' for name in runtime.needed) +
                'Version definition section\nCnt: 1 Name: libasound.so.2\nCnt: 1 Name: ALSA_0.9\n' +
                'Version needs section\nName: GLIBC_2.16\n')
        self.assertEqual(package.validate_readelf(text, runtime)['version_requirements'], ['GLIBC_2.16'])
        with self.assertRaisesRegex(RuntimeError, 'version definitions disagree'):
            package.validate_readelf(text.replace('Name: ALSA_0.9', 'Name: ALSA_9.9'), runtime)

    def test_elf_truncation_and_wrong_architectures(self):
        original = elf_fixture()
        variants = [original[:7], original[:51], b'ARM fixture', original[:-1]]
        for offset, value, format_string in ((4, 2, '<B'), (5, 2, '<B'), (18, 40, '<H'),
                (16, 1, '<H'), (36, 0x50001000, '<I'), (36, 0x70000000, '<I'),
                (36, 0x70001020, '<I'), (46, 0, '<H'), (44, 0, '<H')):
            changed = bytearray(original)
            struct.pack_into(format_string, changed, offset, value)
            variants.append(changed)
        for index, image in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(RuntimeError):
                package.validate_elf(image)

    def test_elf_rejects_soft_float_and_wrong_isa_attributes(self):
        for offset, value in ((7, 3), (3, 1), (2, 64), (0, 1), (5, 0)):
            image = bytearray(elf_fixture())
            section = next(item for item in package.Elf32(image).sections if item[1] == 0x7000002a)
            image[section[4] + offset] = value
            with self.subTest(offset=offset), self.assertRaises(RuntimeError):
                package.validate_elf(image)

    def test_application_loader_and_entry_are_checked(self):
        original = elf_fixture()
        changed = original.replace(b'/lib/ld.so.1\0', b'/lib/ld.so.2\0')
        with self.assertRaisesRegex(RuntimeError, 'interpreter'):
            package.validate_elf(changed)
        image = bytearray(original)
        struct.pack_into('<I', image, 24, 0xffff0000)
        with self.assertRaisesRegex(RuntimeError, 'entry point'):
            package.validate_elf(image)

    def test_hosted_headers_are_found_via_dynamic_symbols(self):
        for suffix, version in (('.rock', package.PLUGIN_ABI), ('.codec', 50), ('.ovl', 1), ('.ovl', package.PLUGIN_ABI)):
            with self.subTest(suffix=suffix, version=version):
                result = package.validate_module('fixture' + suffix, elf_fixture(True, suffix, version=version))
                self.assertEqual(result['target_id'], 124)
                self.assertEqual(result['api_version'], version)

    def test_module_rejects_foreign_model_stock_abi_and_raw_header(self):
        for suffix, target, version in (('.rock', 66, package.PLUGIN_ABI), ('.rock', 124, 266),
                ('.codec', 68, 50), ('.codec', 124, 49), ('.ovl', 124, 2)):
            with self.subTest(suffix=suffix, target=target, version=version), self.assertRaises(RuntimeError):
                package.validate_module('fixture' + suffix, elf_fixture(True, suffix, target, version))
        with self.assertRaises(RuntimeError):
            package.validate_module('raw.rock', struct.pack('<IHH', 0x526f634b, 124, package.PLUGIN_ABI) + bytes(32))

    def test_missing_hidden_and_non_object_headers_are_rejected(self):
        for field, value in (('name', 0), ('info', 0x12), ('other', 2), ('section', 0), ('size', 8)):
            image = bytearray(elf_fixture(True))
            symbols = next(item for item in package.Elf32(image, True).sections if item[1] == 11)
            offsets = {'name': (0, '<I'), 'size': (8, '<I'), 'info': (12, '<B'), 'other': (13, '<B'), 'section': (14, '<H')}
            offset, format_string = offsets[field]
            struct.pack_into(format_string, image, symbols[4] + 16 + offset, value)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                package.validate_module('fixture.rock', image)
        with self.assertRaises(RuntimeError):
            package.validate_module('fixture.rock', elf_fixture(True, exported=False))

    def test_image_decoder_embedded_abi_and_null_load_addresses(self):
        for offset, value in ((24, 266), (8, 1)):
            image = bytearray(elf_fixture(True, '.ovl', version=1))
            section = package.Elf32(image, True).sections[2]
            struct.pack_into('<H', image, section[4] + offset, value)
            with self.subTest(offset=offset), self.assertRaises(RuntimeError):
                package.validate_module('fixture.ovl', image)

    def test_unexpected_dependency_and_undefined_engine_rejected(self):
        image = elf_fixture().replace(b'libc.so.6\0', b'evil.so.1\0')
        with self.assertRaisesRegex(RuntimeError, 'dependencies'):
            package.validate_elf(image)
        image = bytearray(elf_fixture())
        symbols = next(item for item in package.Elf32(image).sections if item[1] == 11)
        struct.pack_into('<H', image, symbols[4] + 16 + 14, 0)
        with self.assertRaisesRegex(RuntimeError, 'undefined engine'):
            package.validate_elf(image)

    def test_readelf_dependency_versions_and_hardfloat_evidence(self):
        text = '(NEEDED) Shared library: [libc.so.6]\nFP ABI: Hard float (double precision)\nName: GLIBC_2.16\n'
        self.assertEqual(package.validate_readelf(text, package.Elf32(elf_fixture()))['version_requirements'], ['GLIBC_2.16'])
        for changed in (text.replace('libc.so.6', 'libstdc++.so.6'), text.replace('Hard float', 'Soft float'),
                text + 'Name: GLIBC_2.28\n', text + 'Name: GLIBCXX_3.4\n', text + 'Name: GCC_10.0\n'):
            with self.subTest(text=changed), self.assertRaises(RuntimeError):
                package.validate_readelf(changed, package.Elf32(elf_fixture()))

    def test_readelf_records_hosted_alsa_versions(self):
        text = '(NEEDED) Shared library: [libc.so.6]\nFP ABI: Hard float (double precision)\nName: ALSA_0.9\nName: ALSA_0.9.0rc4\n'
        self.assertEqual(package.validate_readelf(text, package.Elf32(elf_fixture(versions=('ALSA_0.9', 'ALSA_0.9.0rc4'))))['version_requirements'],
                         ['ALSA_0.9', 'ALSA_0.9.0rc4'])

    def test_dirty_runtime_profiles_and_vendor_images_rejected(self):
        for name in ('.rockbox/config.cfg.new', '.rockbox/.resume.cfg', '.rockbox/nvram.bin',
                '.rockbox/database_0.tcd', '.rockbox/database.idx', '.rockbox/database.unignore',
                '.rockbox/bookmarks/a.txt', '.rockbox/recent.bmark',
                '.rockbox/rocks/a.log', '.rockbox/bootloader.r1', '.rockbox/update.upt',
                '.rockbox/stock.bin', '.rockbox/a.voice', '.rockbox/a.talk', '.rockbox/rockbox.sansa'):
            for content in (b'', b'Synthetic dirty profile'):
                with self.subTest(name=name, content=content), self.assertRaises(RuntimeError):
                    package.validate_package_entry(name, content)

    def test_connectivity_and_audio_card_diagnostics_never_enter_clean_native_packages(self):
        names = ('rockbox.r1.connectivity-original', '.connectivity-state.json', '.connectivity-stage',
                 'r1-connectivity.log', 'rockbox.r1.audio-original', 'rockbox.r1.audio-new',
                 'r1-audio-trace.so', 'r1-audio-diagnostic.log', 'r1-audio-launcher.log')
        for name in names:
            for spelling in (name, name.upper(), name + '.tmp', name.upper() + '.BAK'):
                with self.subTest(name=spelling), self.assertRaisesRegex(RuntimeError, 'dirty runtime profile'):
                    package.validate_package_entry('.rockbox/' + spelling, b'synthetic diagnostic state')
        for name in ('.rockbox/.connectivity-stage/program', '.rockbox/.CONNECTIVITY-STAGE/launcher.sh'):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'dirty runtime profile'):
                package.validate_package_entry(name, b'synthetic staged diagnostic')

    def test_real_firmware_name_remains_allowed_but_substituted_shell_launcher_is_rejected(self):
        package.validate_package_entry('.rockbox/rockbox.r1', elf_fixture())
        for tool in ('hiby_r1_connectivity', 'hiby_r1_audio'):
            launcher = (package.ROOT / 'tools/diagnostics' / tool / 'launcher.sh').read_bytes()
            with self.subTest(tool=tool), self.assertRaises(RuntimeError):
                package.validate_package_entry('.rockbox/rockbox.r1', launcher)

    def test_database_ignore_exception_rejects_nonempty_or_nonroot_markers(self):
        for name, content in (('.rockbox/database.ignore', b'\0'),
                ('.rockbox/database.ignore', b'\n'),
                ('.rockbox/database.ignore', b'Synthetic user data'),
                ('.rockbox/Database.ignore', b''),
                ('.rockbox/database.IGNORE', b''),
                ('.rockbox/rocks/database.ignore', b''),
                ('.rockbox/database.ignore.old', b''),
                ('.rockbox/database.ignored', b''),
                ('.rockbox//database.ignore', b''),
                ('.rockbox/./database.ignore', b'')):
            with self.subTest(name=name, content=content), self.assertRaises(RuntimeError):
                package.validate_package_entry(name, content)

    def test_nonempty_database_ignore_rejected_from_fresh_make_zip(self):
        self.base['.rockbox/database.ignore'] = b'Synthetic user data'
        with self.assertRaisesRegex(RuntimeError, 'dirty runtime profile'):
            self.create()

    def test_nonempty_database_ignore_rejected_from_package(self):
        output = self.create()
        with zipfile.ZipFile(output) as archive:
            manifest = json.loads(archive.read(package.MANIFEST))
        content = b'Synthetic user data'
        manifest['files']['.rockbox/database.ignore'] = package.sha256(content)
        changed = self.rewrite(output, {'.rockbox/database.ignore': content,
                                       package.MANIFEST: package.json_bytes(manifest)})
        with self.assertRaisesRegex(RuntimeError, 'dirty runtime profile'):
            package.verify_firmware_zip(changed)

    def test_unsafe_archive_paths_duplicates_links_and_ancestor_files(self):
        cases = (['.rockbox/../outside'], ['/absolute'], ['C:/outside'],
                 ['.rockbox/CON.txt'], ['.rockbox/bad.'], ['.rockbox/a', '.rockbox/A'],
                 ['.rockbox/rocks', '.rockbox/rocks/a.rock'])
        for index, names in enumerate(cases):
            path = self.directory / f'bad-path-{index}.zip'
            with zipfile.ZipFile(path, 'x') as archive:
                for name in names:
                    archive.writestr(name, b'Synthetic path fixture')
            with self.subTest(names=names), zipfile.ZipFile(path) as archive, self.assertRaises(RuntimeError):
                package.zip_entries(archive)
        path = self.directory / 'symlink.zip'
        with zipfile.ZipFile(path, 'x') as archive:
            info = zipfile.ZipInfo('.rockbox/link')
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, '../../outside')
        with zipfile.ZipFile(path) as archive, self.assertRaises(RuntimeError):
            package.zip_entries(archive)
        path = self.directory / 'literal-backslash.zip'
        with zipfile.ZipFile(path, 'x') as archive:
            archive.writestr('.rockbox/bad', b'Synthetic path fixture')
        path.write_bytes(path.read_bytes().replace(b'.rockbox/bad', b'.rockbox\\bad'))
        with zipfile.ZipFile(path) as archive, self.assertRaises(RuntimeError):
            package.zip_entries(archive)

    def test_clean_polish_profile_enforced(self):
        self.additions['.rockbox/config.cfg'] += b'resume index: 42\n'
        with self.assertRaisesRegex(RuntimeError, 'clean Polish'):
            package.verify_firmware_zip(self.create())

    def test_dirty_base_profile_not_silently_replaced(self):
        self.base['.rockbox/config.cfg'] = b'User settings that must not be imported'
        with self.assertRaisesRegex(RuntimeError, 'pre-existing profile'):
            self.create()

    def test_catalog_target_and_catalog_pair_completeness(self):
        with self.assertRaises(RuntimeError):
            package.shared.validate_catalog('polski.vstrings', catalog(identifier=66), package.TARGET)
        self.base[package.CATALOG_PREFIX + 'deutsch.lng'] = catalog(False)
        with self.assertRaisesRegex(RuntimeError, 'complete pairs'):
            package.verify_firmware_zip(self.create())

    def test_all_supplied_data_hashes_must_match(self):
        output = self.create()
        expected = dict(self.metadata['runtime_data'], phondata='0' * 64)
        with self.assertRaisesRegex(RuntimeError, 'supplied runtime'):
            package.verify_firmware_zip(output, expected_data=expected)

    def test_missing_module_and_readelf_evidence_rejected(self):
        del self.metadata['elf_evidence']['.rockbox/codecs/test.codec']
        with self.assertRaisesRegex(RuntimeError, 'readelf evidence'):
            package.verify_firmware_zip(self.create())

    def test_package_hash_and_unlisted_entry_rejected(self):
        output = self.create()
        changed = self.rewrite(output, {package.DATA_PREFIX + 'phondata': b'Changed data'})
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            package.verify_firmware_zip(changed)

    def test_actual_hosted_notices_required_not_arm_newlib_substitute(self):
        notices = self.directory / 'notices'
        notices.mkdir()
        notice = notices / 'COPYING.txt'
        notice.write_bytes(b'ARM packaging-only notice')
        with self.assertRaisesRegex(RuntimeError, 'actual|Actual'):
            package.runtime_notices(notices)
        notice.write_bytes(NOTICE)
        self.assertEqual(set(package.runtime_notices(notices)), {'COPYING.txt'})

    def test_source_drift_additions_and_modes_block_publication(self):
        files = {'rockbox/apps/fixture.c': self.directory / 'fixture.c'}
        files['rockbox/apps/fixture.c'].write_bytes(b'Frozen source fixture')
        frozen = package.hashes(files)
        modes = {'rockbox/apps/fixture.c': 0o755}
        for changed, changed_modes in ((dict(frozen, extra='a' * 64), modes),
                (dict(frozen, **{'rockbox/apps/fixture.c': '0' * 64}), modes), (frozen, {})):
            with mock.patch.object(package, 'freeze_sources', return_value=(files, changed, changed_modes)):
                with self.assertRaisesRegex(RuntimeError, 'changed after freeze'):
                    package.assert_frozen(self.directory, {}, frozen, modes)

    def test_unchanged_gate_revalidates_same_commit_data(self):
        self.data_validation.side_effect = ValueError('same-commit data drift after freeze')
        with mock.patch.object(package, 'freeze_sources', return_value=({}, {}, {})), \
                mock.patch.object(package.subprocess, 'check_output', return_value=package.ENGINE_REVISION):
            with self.assertRaisesRegex(ValueError, 'data drift after freeze'):
                package.assert_frozen(self.directory, {}, {}, {})
        self.data_validation.assert_called_once_with(self.directory)

    def test_source_archive_detects_changes_between_freeze_and_write(self):
        source = self.directory / 'source.c'
        source.write_bytes(b'Frozen source fixture')
        files = {'rockbox/apps/fixture.c': source}
        frozen = package.hashes(files)
        source.write_bytes(b'Changed source fixture')
        with self.assertRaisesRegex(RuntimeError, 'Source changed'):
            package.write_source_archive(self.directory / 'source.tar.gz', files, frozen, {}, {})

    def test_source_archive_wrong_target_and_outer_checksum_rejected(self):
        output, source = self.source_pair()
        (self.directory / 'SHA256SUMS').write_text('0' * 64 + '  ' + output.name + '\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'SHA256SUMS'):
            package.verify_release(output, source)

    def test_source_archive_target_rejected_even_with_recomputed_hashes(self):
        output, source = self.source_pair()
        with tarfile.open(source, 'r:gz') as archive:
            contents = {member.name: archive.extractfile(member).read() for member in archive}
        manifest = json.loads(contents['source-manifest.json'])
        manifest['target'] = 'sansaclipplus'
        contents['source-manifest.json'] = package.json_bytes(manifest)
        altered = self.directory / 'wrong-target-source.tar.gz'
        with tarfile.open(altered, 'x:gz') as archive:
            for name, data in contents.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        with zipfile.ZipFile(output) as archive:
            metadata = json.loads(archive.read(package.MANIFEST))
        metadata['source_archive'] = {'name': altered.name, 'sha256': package.sha256(altered.read_bytes())}
        changed = self.rewrite(output, {package.MANIFEST: package.json_bytes(metadata)})
        with self.assertRaisesRegex(RuntimeError, 'Source inventory'):
            package.verify_release(changed, altered)

    def test_source_archive_rejects_traversing_private_and_unlisted_files(self):
        for index, name in enumerate(('rockbox/../outside.c', 'rockbox/.git/config', 'rockbox/apps/unlisted.c')):
            path = self.directory / f'unsafe-source-{index}.tar.gz'
            with tarfile.open(path, 'x:gz') as archive:
                for relative, data in ((name, b'Synthetic source fixture'), ('source-manifest.json', b'{"files":{}}')):
                    member = tarfile.TarInfo(relative)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                package.verify_source_archive(path)

    def test_freeze_includes_modified_and_untracked_sources_and_modes(self):
        repository = self.directory / 'repository'
        engine = self.directory / 'engine'
        for root in (repository, engine):
            root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
        source = repository / 'source.c'
        source.write_bytes(b'Initial source fixture')
        subprocess.run(['git', '-C', str(repository), 'add', 'source.c'], check=True)
        source.write_bytes(b'Modified source fixture')
        (repository / 'new.c').write_bytes(b'Untracked source fixture')
        (repository / 'AGENTS.md').write_bytes(b'Internal synthetic instructions')
        data = engine / 'espeak-data'
        data.mkdir()
        for name in package.shared.REQUIRED_DATA:
            path = data / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'Synthetic exact engine data fixture')
        notice = self.directory / 'NOTICE.txt'
        notice.write_bytes(NOTICE)
        with mock.patch.object(package, 'ROOT', repository):
            files, frozen, modes = package.freeze_sources(engine, {'NOTICE.txt': notice})
        self.assertEqual(files['rockbox/source.c'].read_bytes(), b'Modified source fixture')
        self.assertIn('rockbox/new.c', files)
        self.assertNotIn('rockbox/AGENTS.md', files)
        self.assertEqual(modes['rockbox/source.c'], 0o644)
        self.assertEqual(frozen['espeak-1.44.05-source/espeak-data/phondata'], package.sha256(b'Synthetic exact engine data fixture'))

    def test_unlisted_package_entry_rejected(self):
        changed = self.rewrite(self.create(), {'.rockbox/unlisted.txt': b'Synthetic extra file'})
        with self.assertRaisesRegex(RuntimeError, 'Unmanifested'):
            package.verify_firmware_zip(changed)

    def test_spdx_checksums_are_verified_against_real_package_inventory(self):
        output = self.create()
        name = package.TARGET.document_prefix + 'SPDX.json'
        with zipfile.ZipFile(output) as archive:
            manifest = json.loads(archive.read(package.MANIFEST))
            spdx = json.loads(archive.read(name))
        spdx['files'][0]['checksums'][0]['checksumValue'] = '0' * 64
        content = package.json_bytes(spdx)
        manifest['files'][name] = package.sha256(content)
        changed = self.rewrite(output, {name: content, package.MANIFEST: package.json_bytes(manifest)})
        with self.assertRaisesRegex(RuntimeError, 'SPDX'):
            package.verify_firmware_zip(changed)

    def test_elf_malformed_version_chain_and_newer_runtime_rejected(self):
        for versions in (('GLIBC_2.28',), ('GLIBCXX_3.4',), ('CXXABI_1.3',), ('GCC_10.0',)):
            with self.subTest(versions=versions), self.assertRaises(RuntimeError):
                package.validate_elf(elf_fixture(versions=versions))
        image = bytearray(elf_fixture())
        version_section = next(section for section in package.Elf32(image).sections if section[1] == 0x6ffffffe)
        struct.pack_into('<I', image, version_section[4] + 8, 0xffff0000)
        with self.assertRaisesRegex(RuntimeError, 'auxiliary'):
            package.validate_elf(image)

    def test_readelf_version_evidence_must_match_binary_version_table(self):
        text = '(NEEDED) Shared library: [libc.so.6]\nFP ABI: Hard float (double precision)\nName: GLIBC_2.0\n'
        with self.assertRaisesRegex(RuntimeError, 'version requirements disagree'):
            package.validate_readelf(text, package.Elf32(elf_fixture()))

    def test_runtime_evidence_requires_hashed_artifact_under_workspace(self):
        manifest = dict(self.metadata, source_inventory_sha256='b' * 64)
        workspace = self.materials
        workspace.mkdir(parents=True)
        log = workspace / 'native-synthesis-fixture.txt'
        log.write_bytes(b'Synthetic runtime gate fixture, not a native run report')
        report = {'target': 'hibyr1', 'version': 'fixture', 'scope': 'qemu-mipsel',
                  'application_sha256': manifest['application']['sha256'], 'source_inventory_sha256': 'b' * 64,
                  'checks': {'startup': True, 'synthesis': True, 'module_loading': True},
                  'artifacts': {log.name: package.sha256(log.read_bytes())}}
        path = self.directory / 'runtime-fixture.json'
        path.write_bytes(package.json_bytes(report))
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root):
            self.assertEqual(package.validate_runtime_evidence(path, manifest)['scope'], 'qemu-mipsel')
            log.write_bytes(b'Changed evidence fixture')
            with self.assertRaisesRegex(RuntimeError, 'artifact mismatch'):
                package.validate_runtime_evidence(path, manifest)
            report['artifacts'] = {'../outside': '0' * 64}
            path.write_bytes(package.json_bytes(report))
            with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                package.validate_runtime_evidence(path, manifest)

    def test_no_unresolved_toolchain_runtime_falls_back_to_host_libraries(self):
        with mock.patch.object(package.subprocess, 'check_output', side_effect=['', 'libgcc.a']):
            with self.assertRaisesRegex(RuntimeError, 'actual linked toolchain runtime'):
                package.runtime_libraries({}, [])

    def staged_fixture(self):
        self.metadata['espeak_data_provenance'] = self.provenance
        output, source = self.source_pair()
        with tarfile.open(source, 'r:gz') as archive:
            frozen = json.loads(archive.extractfile('source-manifest.json').read())['files']
        stage = self.materials / 'build-espeak-hibyr1/release-staging'
        stage.mkdir(parents=True)
        for path in (output, source, self.directory / 'SHA256SUMS'):
            path.rename(stage / path.name)
        manifest = package.verify_release(stage / output.name)
        manifest.update(toolchain={}, system_runtime={})
        arguments = SimpleNamespace(version='fixture', runtime_evidence=self.directory / 'runtime-fixture.json',
                                    alsa_source=None, publish_hardware_test=False)
        return stage, frozen, manifest, arguments

    def test_publish_gate_rejects_source_drift_before_preserving_release(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        changed = dict(frozen, **{'rockbox/apps/fixture.c': '0' * 64})
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest), \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_evidence': manifest['elf_evidence']}), \
                mock.patch.object(package, 'runtime_libraries', return_value={}), \
                mock.patch.object(package, 'freeze_sources', return_value=({}, changed, {})), \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(RuntimeError, 'Sources changed since'):
                package.publish_release(stage, arguments, self.directory, {}, {}, {})
        preserve.assert_not_called()
        self.assertTrue(stage.is_dir())

    def test_publish_data_drift_blocks_before_archive_inspection_or_preserve(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        self.data_validation.side_effect = ValueError('same-commit data drift at publication')
        with mock.patch.object(package, 'verify_release') as verify, \
                mock.patch.object(package, 'build_application') as build, \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(ValueError, 'data drift at publication'):
                package.publish_release(stage, arguments, self.directory, {}, {}, {})
        for action in (verify, build, preserve):
            action.assert_not_called()
        self.assertTrue(stage.is_dir())

    def test_publish_rechecks_data_after_freeze_before_preserve(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        self.data_validation.side_effect = [self.provenance, ValueError('late publication data drift')]
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest), \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_evidence': manifest['elf_evidence']}), \
                mock.patch.object(package, 'runtime_libraries', return_value={}), \
                mock.patch.object(package, 'freeze_sources', return_value=({}, frozen, {})), \
                mock.patch.object(package, 'validate_runtime_evidence', return_value={'scope': 'synthetic unit test'}), \
                mock.patch.object(package, 'assert_frozen') as unchanged, \
                mock.patch.object(package.shared, 'assert_unused'), \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(ValueError, 'late publication data drift'):
                package.publish_release(stage, arguments, self.directory, {}, {}, {})
        unchanged.assert_called_once()
        preserve.assert_not_called()
        self.assertEqual(self.data_validation.call_count, 2)
        self.assertTrue(stage.is_dir())

    def test_publish_gate_rejects_native_evidence_before_preserving_release(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest), \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_evidence': manifest['elf_evidence']}), \
                mock.patch.object(package, 'runtime_libraries', return_value={}), \
                mock.patch.object(package, 'freeze_sources', return_value=({}, frozen, {})), \
                mock.patch.object(package, 'validate_runtime_evidence', side_effect=RuntimeError('native runtime unverified')), \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(RuntimeError, 'native runtime unverified'):
                package.publish_release(stage, arguments, self.directory, {}, {}, {})
        preserve.assert_not_called()
        self.assertTrue(stage.is_dir())

    def test_publish_gate_rechecks_real_binary_evidence_before_preserving_release(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest), \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_sha256': 'changed'}), \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(RuntimeError, 'fresh ELF/readelf'):
                package.publish_release(stage, arguments, self.directory, {}, {}, {})
        preserve.assert_not_called()

    def test_publish_move_has_single_release_copy_and_integrity_check(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        before = package.hashes(package.shared.tree_files(stage))
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest), \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_evidence': manifest['elf_evidence']}), \
                mock.patch.object(package, 'runtime_libraries', return_value={}), \
                mock.patch.object(package, 'freeze_sources', return_value=({}, frozen, {})), \
                mock.patch.object(package, 'validate_runtime_evidence', return_value={'scope': 'synthetic unit test'}), \
                mock.patch.object(package, 'assert_frozen'), mock.patch.object(package.shared, 'assert_unused'), \
                mock.patch.object(package.shared, 'preserve'):
            package.publish_release(stage, arguments, self.directory, {}, {}, {})
        self.assertFalse(stage.exists())
        self.assertEqual(package.hashes(package.shared.tree_files(self.release_root / 'hibyr1')), before)
        self.assertEqual(self.data_validation.call_args_list,
                         [mock.call(self.directory), mock.call(self.directory)])

    def test_hardware_test_publication_preserves_all_non_runtime_gates(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        manifest.update(channel='hardware-test', native_runtime_verified=False, hardware_tested=False,
                        warning=package.HARDWARE_TEST_WARNING)
        arguments.publish_hardware_test = True
        arguments.runtime_evidence = None
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest) as integrity, \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_evidence': manifest['elf_evidence']}) as native, \
                mock.patch.object(package, 'runtime_libraries', return_value={}) as runtime, \
                mock.patch.object(package, 'bundled_runtime', return_value=({}, {})) as bundled, \
                mock.patch.object(package, 'freeze_sources', return_value=({}, frozen, {})) as freeze, \
                mock.patch.object(package, 'validate_runtime_evidence') as evidence_gate, \
                mock.patch.object(package, 'assert_frozen') as frozen_gate, \
                mock.patch.object(package.shared, 'assert_unused'), mock.patch.object(package.shared, 'preserve'):
            package.publish_release(stage, arguments, self.directory, {}, {}, {})
        self.assertEqual(integrity.call_count, 2)
        for gate in (native, runtime, bundled, freeze, frozen_gate):
            gate.assert_called_once()
        evidence_gate.assert_not_called()
        receipt = json.loads((stage.parent / 'publication.json').read_bytes())
        self.assertEqual(receipt['channel'], 'hardware-test')
        self.assertFalse(receipt['native_runtime_verified'])
        self.assertFalse(receipt['hardware_tested'])
        self.assertIsNone(receipt['runtime_evidence'])

    def test_hardware_test_flag_cannot_publish_diagnostic_staging(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        arguments.publish_hardware_test = True
        arguments.runtime_evidence = None
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest), \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_evidence': manifest['elf_evidence']}), \
                mock.patch.object(package, 'runtime_libraries', return_value={}), \
                mock.patch.object(package, 'bundled_runtime', return_value=({}, {})), \
                mock.patch.object(package, 'freeze_sources', return_value=({}, frozen, {})), \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(RuntimeError, 'explicitly labeled hardware-test'):
                package.publish_release(stage, arguments, self.directory, {}, {}, {})
        preserve.assert_not_called()
        self.assertTrue(stage.is_dir())

    def test_hardware_test_staged_runtime_drift_is_rejected_before_preservation(self):
        stage, frozen, manifest, arguments = self.staged_fixture()
        arguments.publish_hardware_test = True
        arguments.runtime_evidence = None
        with mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package, 'verify_release', return_value=manifest), \
                mock.patch.object(package, 'validate_native_build', return_value={'elf_evidence': manifest['elf_evidence']}), \
                mock.patch.object(package, 'runtime_libraries', return_value={}), \
                mock.patch.object(package, 'bundled_runtime', return_value=({}, {'changed': {}})), \
                mock.patch.object(package.shared, 'preserve') as preserve:
            with self.assertRaisesRegex(RuntimeError, 'freshly validated linked ALSA'):
                package.publish_release(stage, arguments, self.directory, {}, {}, {})
        preserve.assert_not_called()

    def test_corresponding_source_hash_rejected(self):
        output, source = self.source_pair()
        source.write_bytes(b'Changed source archive fixture')
        with self.assertRaisesRegex(RuntimeError, 'source archive hash'):
            package.verify_release(output, source)

    def test_configuration_requires_hosted_memory16(self):
        makefile = 'export MODELNAME=hibyr1\nexport APP_TYPE=hibyos\nexport MEMORYSIZE=16\nexport BINARY=rockbox.r1\n'
        (self.directory / 'Makefile').write_text(makefile, encoding='utf-8')
        (self.directory / 'autoconf.h').write_text('#define HAVE_ESPEAK 1\n#define APPLICATION 1\n', encoding='utf-8')
        package.validate_configuration(self.directory)
        for changed in (makefile.replace('16', '64'), makefile.replace('hibyos', 'sdl-sim'), makefile.replace('rockbox.r1', 'bootloader.r1')):
            (self.directory / 'Makefile').write_text(changed, encoding='utf-8')
            with self.assertRaises(RuntimeError):
                package.validate_configuration(self.directory)

    def test_build_info_wrong_binary_cpu_or_target_rejected(self):
        for old, new in (('hosted', 'arm'), ('124', '66'), ('rockbox.r1', 'rockbox.sansa'), ('fixture', 'other')):
            with self.subTest(old=old), self.assertRaises(RuntimeError):
                package.validate_build_info(build_info().decode().replace(old, new), 'fixture')

    def test_toolchain_rejects_wrong_version_or_triplet_before_build(self):
        for replies in (['13.2.0', package.PREFIX[:-1]], ['9.5.0', 'mipsel-linux-gnu']):
            with mock.patch.object(package.shutil, 'which', return_value='synthetic-tool-query'), \
                    mock.patch.object(package.subprocess, 'check_output', side_effect=replies):
                with self.assertRaisesRegex(RuntimeError, 'GCC 9.5.0'):
                    package.toolchain_versions({'PATH': 'fixture'})

    def test_missing_freeze_and_publish_evidence_never_start_build(self):
        cases = ([], ['--version', 'fixture'], ['--source-frozen', '--version', 'fixture', '--publish',
                 '--toolchain-notices', str(self.directory), '--alsa-source', str(self.directory)],
                 ['--build-only', '--version', 'fixture', '--publish'],
                 ['--publish-hardware-test', '--publish'], ['--publish-hardware-test', '--build-only'],
                 ['--publish-hardware-test', '--runtime-evidence', 'unused.json'],
                 ['--stage-hardware-test', '--publish-hardware-test'],
                 ['--verify', 'unused.zip', '--publish-hardware-test'])
        for argv in cases:
            with self.subTest(argv=argv), mock.patch.object(package, 'build_application') as build, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                package.main(argv)
            build.assert_not_called()

    def test_build_only_has_no_source_freeze_or_publication_requirement(self):
        source = self.directory / 'source'
        source.mkdir()
        build = self.materials / 'build-espeak-hibyr1'

        def compile_diagnostic(*arguments):
            build.mkdir(parents=True)

        with mock.patch.object(package.sys, 'platform', 'linux'), \
                mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                mock.patch.object(package.subprocess, 'check_output', return_value=package.ENGINE_REVISION), \
                mock.patch.object(package.shared, 'runtime_files'), mock.patch.object(package.shared, 'ensure_ignored'), \
                mock.patch.object(package, 'toolchain_versions', return_value={}), \
                mock.patch.object(package, 'validate_native_build', return_value={}), \
                mock.patch.object(package, 'build_application', side_effect=compile_diagnostic) as compile_call, \
                mock.patch.object(package, 'freeze_sources') as freeze, \
                mock.patch.object(package, 'package_application') as publish:
            package.main(['--build-only', '--version', 'fixture', '--espeak-source', str(source)])
        compile_call.assert_called_once()
        freeze.assert_not_called()
        publish.assert_not_called()
        report = json.loads((build / 'diagnostic-build.json').read_bytes())
        self.assertFalse(report['source_frozen'])
        self.assertFalse(report['publishable'])

    def test_hardware_test_cli_accepts_explicit_frozen_build_and_staged_modes(self):
        source = self.directory / 'source'
        source.mkdir()
        common = ['--version', 'fixture', '--source-frozen', '--espeak-source', str(source),
                  '--toolchain-notices', str(self.directory), '--alsa-source', str(self.directory / package.ALSA_SOURCE_NAME)]
        for mode in (['--publish-hardware-test'], ['--stage-hardware-test'],
                     ['--publish-hardware-test', '--staged', str(self.directory)]):
            with self.subTest(mode=mode), mock.patch.object(package.sys, 'platform', 'linux'), \
                    mock.patch.object(package, 'project_materials_root', side_effect=self.materials_root), \
                    mock.patch.object(package.subprocess, 'check_output', return_value=package.ENGINE_REVISION), \
                    mock.patch.object(package.shared, 'runtime_files'), mock.patch.object(package.shared, 'ensure_ignored'), \
                    mock.patch.object(package, 'toolchain_versions', return_value={}), \
                    mock.patch.object(package, 'build_application') as build, \
                    mock.patch.object(package, 'package_application') as packaging:
                package.main(common + mode)
            packaging.assert_called_once()
            build.assert_not_called()
            parsed = packaging.call_args.args[0]
            self.assertIsNone(parsed.runtime_evidence)
            self.assertFalse(parsed.publish)

    def test_runtime_gate_rejects_unbound_host_or_unsuccessful_reports(self):
        manifest = dict(self.metadata, source_inventory_sha256='b' * 64)
        path = self.directory / 'runtime-evidence.json'
        report = {'target': 'hibyr1', 'version': 'fixture', 'scope': 'host',
                  'application_sha256': manifest['application']['sha256'], 'source_inventory_sha256': 'b' * 64,
                  'checks': {'startup': True, 'synthesis': True, 'module_loading': True}, 'artifacts': {}}
        for changes in ({}, {'scope': 'qemu-mipsel', 'application_sha256': '0' * 64},
                {'scope': 'qemu-mipsel', 'checks': {'startup': True}}, {'scope': 'qemu-mipsel'}):
            path.write_bytes(package.json_bytes(dict(report, **changes)))
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                package.validate_runtime_evidence(path, manifest)

    def test_previous_build_snapshot_process_and_hash_guards_reused(self):
        root = self.directory / 'repository'
        root.mkdir()
        central = self.directory / 'central'
        resolver = materials_resolver(root, central)
        previous = resolver(root) / 'build-espeak-hibyr1'
        previous.mkdir(parents=True)
        (previous / 'previous.txt').write_bytes(b'Previous diagnostic build fixture')
        with mock.patch.object(package.shared, '_project_materials_root', side_effect=resolver), \
                mock.patch.object(package.shared, 'ensure_ignored'), \
                mock.patch.object(package.shared, 'assert_unused', side_effect=RuntimeError('active process')):
            with self.assertRaisesRegex(RuntimeError, 'active process'):
                package.shared.preserve(previous, 'hibyr1-build', root)
        self.assertTrue(previous.is_dir())
        with mock.patch.object(package.shared, '_project_materials_root', side_effect=resolver), \
                mock.patch.object(package.shared, 'ensure_ignored'), mock.patch.object(package.shared, 'assert_unused'):
            snapshot = package.shared.preserve(previous, 'hibyr1-build', root)
        self.assertFalse(previous.exists())
        self.assertEqual((snapshot / 'previous.txt').read_bytes(), b'Previous diagnostic build fixture')


if __name__ == '__main__':
    unittest.main(verbosity=2)
