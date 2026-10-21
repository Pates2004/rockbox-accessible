import datetime
from pathlib import Path
import struct
import sys
import unittest
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_espeak_clipplus as package


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



TARGET = package.CLIPZIP


def firmware(target=TARGET, payload=b'Synthetic ARM packaging fixture, not executable'):
    return struct.pack('>I', target.model_number + sum(payload)) + target.marker + payload


def module(plugin=True, target=TARGET):
    return struct.pack('<IHH', 0x526f634b if plugin else 0x52434f44,
                       target.target_id, package.PLUGIN_ABI if plugin else 50) + bytes(24)


def catalog(voice=True, identifier=TARGET.target_id):
    return bytes([0x9a if voice else 0x1a, 6, identifier, 0]) + struct.pack('>HHH', 1, 6, 10) + b'\0\x01Test\0'


def build_info(target=TARGET):
    return (f'Target: {target.name}\nTarget id: {target.target_id}\nCPU: arm\n'
            'Binary: rockbox.sansa\nVersion: fixture\n').encode()


class ClipzipPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        cls.results = _project_materials_root(package.ROOT) / 'clipzip-package-tests' / timestamp
        cls.results.mkdir(parents=True)
        print(f'Synthetic Clip Zip package regression evidence: {cls.results}')

    def setUp(self):
        self.directory = self.results / self._testMethodName
        self.directory.mkdir()
        self.base = {package.FIRMWARE: firmware(),
                     '.rockbox/rocks/apps/test.rock': module(),
                     '.rockbox/codecs/test.codec': module(False),
                     '.rockbox/rockbox-info.txt': build_info()}
        self.additions = {package.DATA_PREFIX + name: b'data fixture'
                          for name in package.REQUIRED_DATA}
        for language in ('english', 'polski'):
            self.base[package.CATALOG_PREFIX + language + '.lng'] = catalog(False)
            self.additions[package.CATALOG_PREFIX + language + '.vstrings'] = catalog()
        self.additions.update({TARGET.document_prefix + name: b'notice fixture'
                              for name in (*package.documents(TARGET), *package.RUNTIME_NOTICES)})
        self.additions['.rockbox/config.cfg'] = package.DEFAULT_CONFIG
        self.metadata = {
            'version': 'fixture', 'target': TARGET.name, 'plugin_abi': package.PLUGIN_ABI,
            'engine_revision': package.ENGINE_REVISION, 'hardware_tested': False,
            'firmware': package.validate_firmware(firmware(), target=TARGET),
            'runtime_data': {name[len(package.DATA_PREFIX):]: package.sha256(content)
                             for name, content in self.additions.items() if name.startswith(package.DATA_PREFIX)},
            'voice_catalogs': {name[len(package.CATALOG_PREFIX):]: package.sha256(content)
                              for name, content in self.additions.items() if name.endswith('.vstrings')},
        }

    def create(self):
        base = self.directory / 'base-fixture.zip'
        output = self.directory / 'firmware-fixture.zip'
        with zipfile.ZipFile(base, 'x') as archive:
            for name, content in self.base.items():
                archive.writestr(name, content)
        package.write_firmware_zip(base, output, self.additions, self.metadata, TARGET)
        return output

    def test_full_clipzip_package_uses_distinct_manifest(self):
        output = self.create()
        manifest = package.verify_firmware_zip(output, target=TARGET)
        self.assertEqual(manifest['firmware']['model_number'], 79)
        self.assertEqual(manifest['firmware']['model'], 'clzp')
        with zipfile.ZipFile(output) as archive:
            self.assertIn(TARGET.manifest, archive.namelist())
            self.assertNotIn(package.MANIFEST, archive.namelist())
        with self.assertRaises(RuntimeError):
            package.verify_firmware_zip(output)

    def test_model_and_catalog_ids_follow_distinct_upstream_definitions(self):
        package.validate_catalog('polski.vstrings', catalog(), TARGET)
        package.validate_module('test.rock', module(), TARGET)
        package.validate_build_info(build_info().decode(), 'fixture', TARGET)
        for identifier in (66, 79):
            with self.subTest(identifier=identifier), self.assertRaises(RuntimeError):
                package.validate_catalog('polski.vstrings', catalog(identifier=identifier), TARGET)
        with self.assertRaises(RuntimeError):
            package.validate_module('test.rock', struct.pack('<IHH', 0x526f634b, 79, package.PLUGIN_ABI) + bytes(24), TARGET)

    def test_module_contract_is_anchored_to_upstream_headers(self):
        for relative, macro in (('apps/plugin.h', 'PLUGIN_MAGIC'),
                                ('lib/rbcodec/codecs/codecs.h', 'CODEC_MAGIC')):
            source = (package.ROOT / relative).read_text(encoding='utf-8')
            self.assertRegex(source, macro + r',\s*TARGET_ID,')
        configuration = (package.ROOT / 'tools/configure').read_text(encoding='utf-8')
        self.assertRegex(configuration, r'65\|sansaclipzip\)\s+target_id=68')
        self.assertEqual(TARGET.target_id, 68)
        self.assertEqual(TARGET.model_number, 79)

    def test_cross_target_firmware_and_module_rejected_both_directions(self):
        for destination, source in ((TARGET, package.CLIPPLUS), (package.CLIPPLUS, TARGET)):
            with self.subTest(destination=destination.name):
                with self.assertRaises(RuntimeError):
                    package.validate_firmware(firmware(source), target=destination)
                with self.assertRaises(RuntimeError):
                    package.validate_module('test.codec', module(False, source), destination)
                with self.assertRaises(RuntimeError):
                    package.validate_build_info(build_info(source).decode(), 'fixture', destination)

    def test_wrong_checksum_seed_rejected(self):
        image = firmware()
        wrong = struct.pack('>I', 68 + sum(image[8:])) + image[4:]
        with self.assertRaises(RuntimeError):
            package.validate_firmware(wrong, target=TARGET)

    def test_firmware_exactly_one_mib_payload_accepted_with_header(self):
        payload = b'\x01' * (1024 * 1024)
        image = firmware(payload=payload)
        self.assertEqual(len(image), len(payload) + 8)
        for expected_payload in (None, payload):
            with self.subTest(native_payload=expected_payload is not None):
                result = package.validate_firmware(image, expected_payload, TARGET)
                self.assertEqual(result['payload_bytes'], 1024 * 1024)

    def test_firmware_one_byte_over_one_mib_rejected_with_valid_checksum(self):
        payload = b'\x01' * (1024 * 1024 + 1)
        image = firmware(payload=payload)
        self.assertEqual(struct.unpack_from('>I', image)[0], (TARGET.model_number + sum(payload)) & 0xffffffff)
        for expected_payload in (None, payload):
            with self.subTest(native_payload=expected_payload is not None):
                with self.assertRaisesRegex(RuntimeError, r'Clip Zip.*1048577.*1048576.*1 MiB'):
                    package.validate_firmware(image, expected_payload, TARGET)

    def test_package_exactly_one_mib_payload_accepted(self):
        payload = b'\x01' * (1024 * 1024)
        image = firmware(payload=payload)
        self.base[package.FIRMWARE] = image
        self.metadata['firmware'] = package.validate_firmware(image, payload, TARGET)
        manifest = package.verify_firmware_zip(self.create(), payload=payload, target=TARGET)
        self.assertEqual(manifest['firmware']['payload_bytes'], len(payload))

    def test_package_one_byte_over_one_mib_rejected_with_valid_hashes(self):
        payload = b'\x01' * (1024 * 1024 + 1)
        image = firmware(payload=payload)
        self.base[package.FIRMWARE] = image
        self.metadata['firmware'].update(checksum=struct.unpack_from('>I', image)[0],
                                         payload_bytes=len(payload), payload_sha256=package.sha256(payload))
        output = self.create()
        for expected_payload in (None, payload):
            with self.subTest(native_payload=expected_payload is not None):
                with self.assertRaisesRegex(RuntimeError, r'Clip Zip.*1048577.*1048576.*1 MiB'):
                    package.verify_firmware_zip(output, payload=expected_payload, target=TARGET)

    def test_clipplus_module_cannot_enter_clipzip_package(self):
        self.base['.rockbox/rocks/apps/test.rock'] = module(target=package.CLIPPLUS)
        with self.assertRaises(RuntimeError):
            self.create()

    def test_clipplus_catalog_cannot_enter_clipzip_package(self):
        self.additions[package.CATALOG_PREFIX + 'polski.vstrings'] = catalog(identifier=66)
        with self.assertRaises(RuntimeError):
            self.create()

    def test_wrong_manifest_target_rejected(self):
        self.metadata['target'] = package.CLIPPLUS.name
        with self.assertRaises(RuntimeError):
            package.verify_firmware_zip(self.create(), target=TARGET)

    def test_profile_must_be_clean(self):
        self.additions['.rockbox/config.cfg'] += b'tts rate: 300\n'
        with self.assertRaises(RuntimeError):
            package.verify_firmware_zip(self.create(), target=TARGET)

    def test_missing_target_document_rejected(self):
        self.additions.pop(TARGET.document_prefix + 'CZYTAJ.md')
        with self.assertRaises(RuntimeError):
            package.verify_firmware_zip(self.create(), target=TARGET)

    def test_source_identity_is_checked_for_clipzip(self):
        source = self.directory / 'source-fixture.txt'
        source.write_text('Source fixture, not Rockbox', encoding='utf-8')
        files = {'rockbox/fixture.txt': source}
        inventory = package.hashes(files)
        archive = self.directory / 'source-fixture.tar.gz'
        package.write_source_archive(archive, files, inventory, {},
                                     {'version': 'fixture', 'target': package.CLIPPLUS.name})
        self.metadata['source_archive'] = {'name': archive.name, 'sha256': package.sha256(archive.read_bytes())}
        self.metadata['source_inventory_sha256'] = package.sha256(package.json_bytes(inventory))
        with self.assertRaisesRegex(RuntimeError, 'different firmware build'):
            package.verify_release(self.create(), check_sums=False, target=TARGET)


if __name__ == '__main__':
    unittest.main(verbosity=2)
