import argparse
import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_espeak_clipplus as shared
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib/espeak'))
from data_provenance import validate_packaged_data, validate_supplied_data

TARGET = shared.FirmwareTarget('hibyr1', 'hibyr1', 'HiBy R1', 124, 124, b'')
PREFIX = 'mipsel-rockbox-linux-gnu-'
ENGINE_REVISION = shared.ENGINE_REVISION
PLUGIN_ABI = shared.PLUGIN_ABI
FIRMWARE = '.rockbox/rockbox.r1'
MANIFEST = TARGET.manifest
DATA_PREFIX = shared.DATA_PREFIX
CATALOG_PREFIX = shared.CATALOG_PREFIX
DEFAULT_CONFIG = shared.DEFAULT_CONFIG.replace(b'\nvolume: -25\n', b'\nvolume: -250\n')
REQUIRED_SYMBOLS = ('rb_espeak_synth_tracked', 'rb_espeak_synth_character',
                    'espeak_Synth', 'tts_speak')
LIBRARIES = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2',
             'librt.so.1', 'libasound.so.2', 'libgcc_s.so.1', 'ld.so.1'}
MODULE_SUFFIXES = {'.rock', '.codec', '.ovl'}
NOTICE_PREFIX = TARGET.document_prefix + 'toolchain-licenses/'
ALSA_LIBRARY = '.rockbox/libasound.so.2'
ALSA_SOURCE_PREFIX = 'rockbox/docs/native-runtime-sources/hibyr1/'
ALSA_SOURCE_NAME = 'alsa-lib-1.0.26.tar.bz2'
ALSA_SOURCE_SHA256 = '8c9f8161603cc3db640619650401292c3e110da63429ab6938aac763319f6e7d'
ALSA_COPYING_SHA256 = 'a190dc9c8043755d90f8b0a75fa66b9e42d4af4c980bf5ddc633f0124db3cee7'
ALSA_RECIPE_SHA256 = '5a20d7c7b2100d2b63c5ac6306659a0d9e883fb8b2e48822e002d4af8bc9e323'
ALSA_RECIPE_FILES = {
    'official/tools/rockboxdev.sh': ALSA_RECIPE_SHA256,
    'official/tools/toolchain-patches/binutils-c23.patch': '25ca694d8612ccdb731d0fb4964f77f7ef1c3e4fd9e10fcc468a0feeeb556abd',
    'official/tools/toolchain-patches/glibc-227-make44.patch': '81eed79adf06f03ac519cdc1eb324685b8665604309b5fbffb24084a1a52acd1',
    'official/tools/toolchain-patches/glibc-227-texinfo.patch': 'ee4c0c622e289f248f10740079cd365b9aeb4055c68079e37fd213beb2edaaa4',
    'official/tools/toolchain-patches/linux-c23.patch': '822e45c89ef5a2228f2dc9dee5ab4ebcc8b5a6c493b534e85e9f808acda46100',
}
ALSA_DEPENDENCIES = {'libc.so.6', 'libm.so.6', 'libdl.so.2', 'libpthread.so.0', 'librt.so.1'}
AUTOSTART_FILE = '.rockbox/rb_bl_mode.txt'
AUTOSTART_SEED = bytes(4)
AUTOSTART = {'path': AUTOSTART_FILE, 'sha256': shared.sha256(AUTOSTART_SEED),
             'mode': 'Rockbox', 'value': 0, 'encoding': 'uint32-le',
             'loader': 'bahusoid/x1600_hiby_v2/HiBy-R1-1.8b2', 'factory_seed': True}
HARDWARE_TEST_WARNING = ('First-device-test package: native startup, synthesis and module loading have NOT been verified; '
                         'physical R1 execution and firmware/library compatibility are untested. '
                         'Pinned HiBy R1 1.8b2 already includes ALSA; bundled SDK ALSA 1.0.26 is a controlled runtime, '
                         'not a fix for missing ALSA in that firmware. Vendor Bluetooth/plugin compatibility is unverified.')
sha256 = shared.sha256
json_bytes = shared.json_bytes
hashes = shared.hashes
write_source_archive = shared.write_source_archive
verify_source_archive = shared.verify_source_archive


def safe_name(name):
    relative = shared.safe_name(name)
    reserved = {'con', 'prn', 'aux', 'nul', *(f'com{number}' for number in range(1, 10)),
                *(f'lpt{number}' for number in range(1, 10))}
    if any(part.split('.')[0].casefold() in reserved for part in relative.parts):
        raise RuntimeError(f'Unsafe Windows archive path: {name!r}')
    return relative


def zip_entries(archive):
    for info in archive.infolist():
        original = info.orig_filename
        safe_name(original.rstrip('/') if info.is_dir() else original)
    entries = shared.zip_entries(archive)
    names = {name.casefold() for name in entries}
    for info in archive.infolist():
        relative = safe_name(info.filename.rstrip('/') if info.is_dir() else info.filename)
        if any(parent.as_posix().casefold() in names for parent in relative.parents if parent != PurePosixPath('.')):
            raise RuntimeError(f'Archive file/directory path conflict: {info.filename}')
    return entries


class Elf32:
    def __init__(self, image, module=False, runtime=False):
        self.image = image
        if len(image) < 52 or image[:7] != b'\x7fELF\x01\x01\x01':
            raise RuntimeError('Expected an ELF32 little-endian MIPS image')
        (self.kind, machine, version, self.entry, program_offset, section_offset,
         flags, header_size, program_size, program_count, section_size,
         section_count, section_names) = struct.unpack_from('<HHIIIIIHHHHHH', image, 16)
        if (machine != 8 or version != 1 or header_size != 52 or
                self.kind not in ((3,) if module or runtime else (2, 3)) or
                (not (module or runtime) and not self.entry) or
                flags & 0xf0000000 not in ((0, 0x70000000) if runtime else (0x70000000,)) or
                flags & 0xf000 != 0x1000 or flags & 0x20 or flags & 0x06000000):
            raise RuntimeError('Expected MIPS32r2 O32 ELF with the correct application/module type')
        if not section_count or section_size != 40 or section_names >= section_count:
            raise RuntimeError('Invalid ELF section table')
        self.slice(section_offset, section_size * section_count)
        self.sections = [struct.unpack_from('<IIIIIIIIII', image, section_offset + index * 40)
                         for index in range(section_count)]
        for section in self.sections:
            if section[1] != 8:
                self.slice(section[4], section[5])
        if not program_count or program_size != 32:
            raise RuntimeError('Invalid ELF program table')
        self.slice(program_offset, program_size * program_count)
        self.programs = [struct.unpack_from('<IIIIIIII', image, program_offset + index * 32)
                         for index in range(program_count)]
        for program in self.programs:
            self.slice(program[1], program[4])
            if program[4] > program[5]:
                raise RuntimeError('Invalid ELF segment size')
        if not any(program[0] == 1 for program in self.programs):
            raise RuntimeError('ELF contains no loadable segment')
        if not (module or runtime) and not any(program[0] == 1 and program[6] & 1 and
                program[2] <= self.entry < program[2] + program[4] for program in self.programs):
            raise RuntimeError('ELF entry point is outside executable file data')
        interpreters = [self.slice(program[1], program[4]) for program in self.programs if program[0] == 3]
        if module or runtime:
            if interpreters:
                raise RuntimeError('Module contains a program interpreter')
            self.interpreter = None
        else:
            if interpreters != [b'/lib/ld.so.1\0']:
                raise RuntimeError('Unexpected hosted MIPS program interpreter')
            self.interpreter = '/lib/ld.so.1'
        abi_sections = [section for section in self.sections if section[1] == 0x7000002a]
        if len(abi_sections) != 1 or abi_sections[0][5] != 24:
            raise RuntimeError('Missing or malformed MIPS ABI flags')
        abi = struct.unpack('<HBBBBBBIIII', self.slice(abi_sections[0][4], 24))
        expected_isa = (1, 0) if runtime and flags & 0xf0000000 == 0 else (32, 2)
        if (abi[:4] != (0, *expected_isa, 1) or abi[4] not in (1, 2) or
                abi[6] not in (1, 5, 6, 7) or any(abi[index] for index in (5, 7, 8))):
            raise RuntimeError('Expected MIPS32r2 O32 hard-float ABI flags')
        self.isa = 'MIPS1' if expected_isa == (1, 0) else 'MIPS32r2'
        self.symbols = []
        for section in self.sections:
            if section[1] not in (2, 11):
                continue
            if section[9] != 16 or section[5] % 16:
                raise RuntimeError('Malformed ELF symbol table')
            strings = self.strings(section[6])
            for offset in range(section[4], section[4] + section[5], 16):
                name, value, size, info, other, index = struct.unpack_from('<IIIBBH', image, offset)
                self.symbols.append({'name': self.string(strings, name), 'value': value, 'size': size,
                                     'info': info, 'other': other, 'section': index,
                                     'dynamic': section[1] == 11})
        self.needed = []
        self.sonames = []
        for section in self.sections:
            if section[1] != 6:
                continue
            if section[9] != 8 or section[5] % 8:
                raise RuntimeError('Malformed ELF dynamic table')
            strings = self.strings(section[6])
            for offset in range(section[4], section[4] + section[5], 8):
                tag, value = struct.unpack_from('<iI', image, offset)
                if tag in (15, 29):
                    raise RuntimeError('Unexpected ELF RPATH/RUNPATH')
                if tag == 1:
                    self.needed.append(self.string(strings, value))
                elif tag == 14:
                    self.sonames.append(self.string(strings, value))
        if len(set(self.needed)) != len(self.needed) or not set(self.needed) <= LIBRARIES:
            raise RuntimeError(f'Unexpected ELF dependencies: {self.needed}')
        if not module and 'libc.so.6' not in self.needed:
            raise RuntimeError('Hosted application does not declare its libc dependency')
        self.version_requirements = []
        for section in self.sections:
            if section[1] != 0x6ffffffe:
                continue
            strings = self.strings(section[6])
            data = self.slice(section[4], section[5])
            offset = 0
            seen = set()
            for index in range(section[7]):
                if offset in seen or offset + 16 > len(data):
                    raise RuntimeError('Malformed ELF version requirements')
                seen.add(offset)
                version, count, filename, auxiliary, following = struct.unpack_from('<HHIII', data, offset)
                if version != 1 or not count or self.string(strings, filename) not in self.needed:
                    raise RuntimeError('Invalid version requirement library')
                auxiliary_offset = offset + auxiliary
                auxiliary_seen = set()
                for auxiliary_index in range(count):
                    if auxiliary_offset in auxiliary_seen or auxiliary_offset + 16 > len(data):
                        raise RuntimeError('Malformed ELF version requirement auxiliary table')
                    auxiliary_seen.add(auxiliary_offset)
                    _, _, _, name, next_auxiliary = struct.unpack_from('<IHHII', data, auxiliary_offset)
                    self.version_requirements.append(self.string(strings, name))
                    if bool(next_auxiliary) != (auxiliary_index + 1 < count):
                        raise RuntimeError('Invalid ELF version requirement chain')
                    auxiliary_offset += next_auxiliary
                if bool(following) != (index + 1 < section[7]):
                    raise RuntimeError('Invalid ELF version library chain')
                offset += following
        self.version_requirements = sorted(set(self.version_requirements))
        validate_versions(self.version_requirements)
        self.version_definitions = []
        for section in self.sections:
            if section[1] != 0x6ffffffd:
                continue
            strings = self.strings(section[6])
            data = self.slice(section[4], section[5])
            offset = 0
            seen = set()
            for index in range(section[7]):
                if offset in seen or offset + 20 > len(data):
                    raise RuntimeError('Malformed ELF version definitions')
                seen.add(offset)
                version, _, _, count, _, auxiliary, following = struct.unpack_from('<HHHHIII', data, offset)
                if version != 1 or not count:
                    raise RuntimeError('Invalid ELF version definition')
                auxiliary_offset = offset + auxiliary
                auxiliary_seen = set()
                for auxiliary_index in range(count):
                    if auxiliary_offset in auxiliary_seen or auxiliary_offset + 8 > len(data):
                        raise RuntimeError('Malformed ELF version definition auxiliary table')
                    auxiliary_seen.add(auxiliary_offset)
                    name, next_auxiliary = struct.unpack_from('<II', data, auxiliary_offset)
                    value = self.string(strings, name)
                    if auxiliary_index == 0:
                        self.version_definitions.append(value)
                    if bool(next_auxiliary) != (auxiliary_index + 1 < count):
                        raise RuntimeError('Invalid ELF version definition auxiliary chain')
                    auxiliary_offset += next_auxiliary
                if bool(following) != (index + 1 < section[7]):
                    raise RuntimeError('Invalid ELF version definition chain')
                offset += following
        if len(set(self.version_definitions)) != len(self.version_definitions):
            raise RuntimeError('Duplicate ELF version definitions')
        self.version_definitions.sort()
        undefined = {symbol['name'].split('@')[0] for symbol in self.symbols if not symbol['section']}
        forbidden = [name for name in undefined if name.startswith(('rb_espeak_', 'espeak_', 'tts_', '_Zn', '_Zd'))
                     or name in {'__gxx_personality_v0', '__cxa_throw', '__cxa_guard_acquire',
                                 *(() if runtime else ('setlocale', 'newlocale', 'uselocale', 'nl_langinfo',
                                                       'mbrtowc', 'mbstowcs', 'wcrtomb', 'wcstombs'))}]
        if forbidden:
            raise RuntimeError(f'Unexpected undefined engine/C++/locale symbols: {sorted(forbidden)}')

    def slice(self, offset, size):
        if offset < 0 or size < 0 or offset > len(self.image) or size > len(self.image) - offset:
            raise RuntimeError('Truncated ELF structure')
        return self.image[offset:offset + size]

    def strings(self, index):
        if index >= len(self.sections) or self.sections[index][1] != 3:
            raise RuntimeError('Invalid ELF string table')
        section = self.sections[index]
        return self.slice(section[4], section[5])

    @staticmethod
    def string(strings, offset):
        end = strings.find(b'\0', offset)
        if offset >= len(strings) or end < 0:
            raise RuntimeError('Invalid ELF string offset')
        try:
            return strings[offset:end].decode('ascii')
        except UnicodeDecodeError as error:
            raise RuntimeError('Non-ASCII ELF symbol or library') from error

    def exported_header(self):
        symbols = [symbol for symbol in self.symbols if symbol['name'] == '__header' and symbol['dynamic']]
        if len(symbols) != 1:
            raise RuntimeError('Missing or duplicate exported ELF __header')
        symbol = symbols[0]
        if (symbol['info'] != 0x11 or symbol['other'] & 3 or
                not 0 < symbol['section'] < len(self.sections)):
            raise RuntimeError('Invalid exported ELF __header symbol')
        section = self.sections[symbol['section']]
        delta = symbol['value'] - section[3]
        if section[1] == 8 or not section[2] & 2 or delta < 0 or delta + symbol['size'] > section[5]:
            raise RuntimeError('ELF __header does not reference allocated file data')
        if not any(program[0] == 1 and program[2] <= symbol['value'] and
                symbol['value'] + symbol['size'] <= program[2] + program[4] and
                program[1] + symbol['value'] - program[2] == section[4] + delta for program in self.programs):
            raise RuntimeError('ELF __header is outside loadable file data')
        return self.slice(section[4] + delta, symbol['size'])


def validate_elf(image):
    elf = Elf32(image)
    return {'sha256': sha256(image), 'bytes': len(image), 'architecture': 'MIPS32r2 little-endian O32 hard-float',
            'interpreter': elf.interpreter, 'needed': sorted(elf.needed),
            'version_requirements': elf.version_requirements}


def validate_alsa(image):
    elf = Elf32(image, runtime=True)
    exports = {symbol['name'] for symbol in elf.symbols if symbol['dynamic'] and symbol['section'] and
               symbol['info'] >> 4 in (1, 2) and not symbol['other'] & 3}
    if (elf.entry or elf.sonames != ['libasound.so.2'] or set(elf.needed) != ALSA_DEPENDENCIES or
            not {'snd_pcm_open', 'snd_pcm_writei', 'snd_asoundlib_version', 'snd_mixer_open'} <= exports or
            'ALSA_0.9' not in elf.version_definitions or 'libasound.so.2' not in elf.version_definitions):
        raise RuntimeError('Invalid bundled ALSA runtime identity/dependencies/exports')
    validate_versions(name for name in elf.version_definitions if name != 'libasound.so.2')
    if any(version.startswith('GLIBC_') and tuple(map(int, version[6:].split('.'))) > (2, 22)
           for version in elf.version_requirements):
        raise RuntimeError('Bundled ALSA requires a newer glibc than pinned R1 firmware 1.8b2')
    return {'sha256': sha256(image), 'bytes': len(image), 'architecture': elf.isa + ' little-endian O32 hard-float',
            'soname': 'libasound.so.2', 'needed': sorted(elf.needed),
            'version_requirements': elf.version_requirements, 'version_definitions': elf.version_definitions}


def validate_alsa_consumers(image, consumers):
    elf = Elf32(image, runtime=True)
    exports = {symbol['name'] for symbol in elf.symbols if symbol['dynamic'] and symbol['section'] and
               symbol['info'] >> 4 in (1, 2) and not symbol['other'] & 3}
    for name, content in consumers.items():
        consumer = Elf32(content, module=name != FIRMWARE)
        imports = {symbol['name'] for symbol in consumer.symbols if symbol['dynamic'] and not symbol['section'] and
                   symbol['name'].startswith('snd_')}
        versions = {version for version in consumer.version_requirements if version.startswith('ALSA_')}
        if not imports <= exports or not versions <= set(elf.version_definitions):
            raise RuntimeError(f'Bundled ALSA cannot satisfy application/module symbols or versions: {name}')


def validate_module(name, image):
    suffix = PurePosixPath(name).suffix.lower()
    elf = Elf32(image, module=True)
    header = elf.exported_header()
    minimum = 32 if suffix == '.codec' else 28
    if len(header) < minimum:
        raise RuntimeError(f'Truncated module __header: {name}')
    magic, target, version, load, end = struct.unpack_from('<IHHII', header)
    expected_magic = {0x52434f44, 0x52454e43} if suffix == '.codec' else {0x526f634b}
    expected_version = 50 if suffix == '.codec' else PLUGIN_ABI
    if suffix == '.ovl' and version == 1:
        if len(header) < 40 or struct.unpack_from('<H', header, 24)[0] != PLUGIN_ABI:
            raise RuntimeError(f'Wrong image decoder embedded plugin ABI: {name}')
        expected_version = 1
    if magic not in expected_magic or target != 124 or version != expected_version or load or end:
        raise RuntimeError(f'Wrong hosted module model/header/ABI: {name}')
    return {'sha256': sha256(image), 'target_id': target, 'api_version': version,
            'needed': sorted(elf.needed), 'version_requirements': elf.version_requirements}


def toolchain_environment(directory=None):
    environment = dict(os.environ)
    if directory is not None:
        directory = directory.resolve(strict=True)
        if not directory.is_dir():
            raise RuntimeError('--toolchain-bin must be a directory')
        environment['PATH'] = str(directory) + os.pathsep + environment.get('PATH', '')
    for name in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES'):
        environment.pop(name, None)
    return environment


def toolchain_versions(environment):
    result = {}
    for name in ('gcc', 'g++', 'readelf', 'nm', 'objcopy', 'ld'):
        executable = shutil.which(PREFIX + name, path=environment.get('PATH'))
        if not executable:
            raise RuntimeError(f'Missing exact hosted toolchain: {PREFIX + name}; use --toolchain-bin or PATH')
        command = [executable]
        if name in ('gcc', 'g++'):
            version = subprocess.check_output(command + ['-dumpfullversion'], env=environment, text=True).strip()
            machine = subprocess.check_output(command + ['-dumpmachine'], env=environment, text=True).strip()
            if version != '9.5.0' or machine != PREFIX[:-1]:
                raise RuntimeError(f'Expected hosted {PREFIX[:-1]} GCC 9.5.0, found {machine} {version}')
        result[name] = {'path': executable, 'sha256': sha256(Path(executable).read_bytes()),
                        'version': subprocess.check_output(command + ['--version'], env=environment, text=True).splitlines()[0]}
    return result


def validate_configuration(build):
    makefile = (build / 'Makefile').read_text(encoding='utf-8')
    for key, value in {'MODELNAME': 'hibyr1', 'APP_TYPE': 'hibyos', 'MEMORYSIZE': '16', 'BINARY': 'rockbox.r1'}.items():
        if re.findall(r'^export ' + key + r'\s*=\s*(\S+)\s*$', makefile, re.M) != [value]:
            raise RuntimeError(f'Wrong R1 configuration: {key}')
    configuration = (build / 'autoconf.h').read_text(encoding='utf-8')
    if not re.search(r'^#define HAVE_ESPEAK\s+1\s*$', configuration, re.M):
        raise RuntimeError('Integrated eSpeak is disabled')
    if re.search(r'^#define (SIMULATOR|BOOTLOADER)\b', configuration, re.M):
        raise RuntimeError('Expected a normal hosted application configuration')


def build_application(build, version, jobs, environment):
    shared.preserve(build, 'hibyr1-native-build')
    build.mkdir(parents=True, exist_ok=False)
    configure = ['bash', str(ROOT / 'tools/configure'), '--target=hibyr1', '--type=N',
                 '--integrated-espeak', '--compiler-prefix=' + PREFIX]
    shared.run(configure, build, 'configure.log', environment)
    validate_configuration(build)
    shared.run(['make', f'-j{jobs}', 'zip', f'VERSION={version}'], build, 'build-zip.log', environment)
    return configure


def validate_build_info(text, version):
    fields = {}
    for line in text.splitlines():
        if ': ' in line:
            key, value = line.split(': ', 1)
            if key in fields:
                raise RuntimeError('Duplicate build information field')
            fields[key] = value
    expected = {'Target': 'hibyr1', 'Target id': '124', 'CPU': 'hosted',
                'Binary': 'rockbox.r1', 'Version': version}
    if any(fields.get(key) != value for key, value in expected.items()):
        raise RuntimeError('rockbox-info.txt is not this hosted R1 build')


def validate_versions(versions):
    for version in versions:
        if re.fullmatch(r'ALSA_[0-9]+(?:\.[0-9]+)+(?:rc[0-9]+)?', version):
            continue
        match = re.fullmatch(r'(GLIBC|GCC)_([0-9]+(?:\.[0-9]+)+)', version)
        if not match:
            raise RuntimeError(f'Unexpected ELF symbol version requirement: {version}')
        components = tuple(int(part) for part in match[2].split('.'))
        limit = (2, 27) if match[1] == 'GLIBC' else (9, 5, 0)
        if components > limit:
            raise RuntimeError(f'ELF requires a newer runtime than the hosted toolchain: {version}')


def validate_readelf(text, elf):
    needed = re.findall(r'\(NEEDED\).*?Shared library: \[([^\]]+)\]', text)
    if sorted(needed) != sorted(elf.needed):
        raise RuntimeError('readelf dependencies disagree with ELF dynamic table')
    if not re.search(r'FP ABI:\s*Hard float', text):
        raise RuntimeError('readelf did not confirm the hard-float ABI')
    needs_text = text.split('Version needs section', 1)[-1] if elf.version_definitions else text
    versions = sorted(set(re.findall(r'\bName:\s+(\S+)', needs_text)))
    validate_versions(versions)
    if versions != elf.version_requirements:
        raise RuntimeError('readelf version requirements disagree with ELF version table')
    if elf.version_definitions:
        definitions = sorted(set(re.findall(r'Cnt:\s*\d+\s+Name:\s+(\S+)', text)))
        if definitions != elf.version_definitions:
            raise RuntimeError('readelf version definitions disagree with ELF version table')
    return {'needed': sorted(needed), 'version_requirements': versions,
            'readelf_sha256': sha256(text.encode('utf-8'))}


def inspect_elf(path, environment, report_path, module=False, runtime=False):
    elf = Elf32(path.read_bytes(), module=module, runtime=runtime)
    text = subprocess.check_output([PREFIX + 'readelf', '-W', '-h', '-A', '-l', '-d', '-V', '-s', str(path)],
                                   env=environment, text=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding='utf-8')
    return validate_readelf(text, elf)


def allocated_sections(elf):
    return sorted((section[1], section[2], section[3], section[5],
                   None if section[1] == 8 else sha256(elf.slice(section[4], section[5])))
                  for section in elf.sections if section[2] & 2)


def validate_native_build(build, version, environment):
    validate_configuration(build)
    validate_build_info((build / 'rockbox-info.txt').read_text(encoding='utf-8'), version)
    executable = build / 'rockbox.elf'
    application = build / 'rockbox.r1'
    core = Elf32(executable.read_bytes())
    packaged = Elf32(application.read_bytes())
    defined = {symbol['name'] for symbol in core.symbols if symbol['section'] and symbol['info'] & 15 == 2}
    if not set(REQUIRED_SYMBOLS) <= defined:
        raise RuntimeError('Native ELF is missing defined integrated speech functions')
    arenas = [symbol['size'] for symbol in core.symbols if symbol['name'] == 'audiobuffer' and symbol['section']]
    if arenas != [15 * 1024 * 1024]:
        raise RuntimeError('Native core audiobuffer is not the configured 15 MiB arena')
    if allocated_sections(core) != allocated_sections(packaged) or core.entry != packaged.entry:
        raise RuntimeError('rockbox.r1 does not match allocated sections of the linked rockbox.elf')
    evidence = {'rockbox.elf': inspect_elf(executable, environment, build / 'elf-verification/core.txt'),
                FIRMWARE: inspect_elf(application, environment, build / 'elf-verification/application.txt')}
    modules = {}
    with zipfile.ZipFile(build / 'rockbox.zip') as archive:
        entries = zip_entries(archive)
        if FIRMWARE not in entries or archive.read(FIRMWARE) != application.read_bytes():
            raise RuntimeError('Fresh make zip contains a different application')
        candidates = {}
        for path in sorted(build.rglob('*')):
            if path.is_file() and path.suffix in MODULE_SUFFIXES:
                confined_path(path, build)
                candidates.setdefault(path.name, []).append(path)
        for name in sorted(entries):
            if PurePosixPath(name).suffix not in MODULE_SUFFIXES:
                continue
            content = archive.read(name)
            modules[name] = validate_module(name, content)
            matches = [path for path in candidates.get(PurePosixPath(name).name, []) if path.read_bytes() == content]
            if not matches:
                raise RuntimeError(f'Packaged module does not match a fresh build output: {name}')
            evidence[name] = inspect_elf(matches[0], environment,
                                        build / 'elf-verification' / (name + '.txt'), module=True)
    if not any(name.endswith('.rock') for name in modules) or not any(name.endswith('.codec') for name in modules):
        raise RuntimeError('Missing freshly rebuilt plugins/codecs')
    return {'application': validate_elf(application.read_bytes()), 'modules': modules,
            'elf_sha256': sha256(executable.read_bytes()),
            'link_map_sha256': sha256((build / 'rockbox.map').read_bytes()),
            'defined_speech_symbols': list(REQUIRED_SYMBOLS), 'elf_evidence': evidence,
            'memory_configuration_mib': 16, 'core_arena_mib': 15,
            'firmware_library_compatibility': 'untested', 'hardware_tested': False}


def documents():
    return dict(shared.documents(TARGET), **{
        'HIBY-R1-INSTALL.md': 'docs/HIBY-R1-INSTALL.md',
        'HIBY-R1-INSTALL-PL.md': 'docs/HIBY-R1-INSTALL-PL.md',
        'HIBY-R1-CONTROLS.md': 'docs/HIBY-R1-CONTROLS.md',
        'HIBY-R1-CONTROLS-PL.md': 'docs/HIBY-R1-CONTROLS-PL.md',
        'ACCESSIBILITY-TOUCH.md': 'docs/ACCESSIBILITY-TOUCH.md',
        'ACCESSIBILITY-TOUCH-PL.md': 'docs/ACCESSIBILITY-TOUCH-PL.md',
        'ACCESSIBILITY-TYPING.md': 'docs/ACCESSIBILITY-TYPING.md',
        'ACCESSIBILITY-TYPING-PL.md': 'docs/ACCESSIBILITY-TYPING-PL.md',
        'ESPEAK-ROCKBOX.md': 'docs/ESPEAK-ROCKBOX.md',
        'ESPEAK-ROCKBOX-PL.md': 'docs/ESPEAK-ROCKBOX-PL.md',
        'ACCESSIBILITY-LISTS.md': 'docs/ACCESSIBILITY-LISTS.md',
        'ACCESSIBILITY-LISTS-PL.md': 'docs/ACCESSIBILITY-LISTS-PL.md',
        'RADIO-DYNAMIC.md': 'docs/RADIO-DYNAMIC.md',
        'RADIO-DYNAMIC-PL.md': 'docs/RADIO-DYNAMIC-PL.md',
        'ACCESSIBILITY-SCREEN.md': 'docs/ACCESSIBILITY-SCREEN.md',
        'ACCESSIBILITY-SCREEN-PL.md': 'docs/ACCESSIBILITY-SCREEN-PL.md',
        'ACCESSIBILITY-SHORTCUT.md': 'docs/ACCESSIBILITY-SHORTCUT.md',
        'ACCESSIBILITY-SHORTCUT-PL.md': 'docs/ACCESSIBILITY-SHORTCUT-PL.md',
        'HIBY-R1-CONNECTIVITY.md': 'docs/HIBY-R1-CONNECTIVITY.md',
        'HIBY-R1-CONNECTIVITY-PL.md': 'docs/HIBY-R1-CONNECTIVITY-PL.md',
        'ACCESSIBILITY-CURTAIN.md': 'docs/ACCESSIBILITY-CURTAIN.md',
        'ACCESSIBILITY-CURTAIN-PL.md': 'docs/ACCESSIBILITY-CURTAIN-PL.md',
        'INTERFACE-APPEARANCE.md': 'docs/INTERFACE-APPEARANCE.md',
        'INTERFACE-APPEARANCE-PL.md': 'docs/INTERFACE-APPEARANCE-PL.md',
        'HIBY-R1-POWER.md': 'docs/HIBY-R1-POWER.md',
        'HIBY-R1-POWER-PL.md': 'docs/HIBY-R1-POWER-PL.md',
        'HIBY-R1-NETWORK-EMULATION.md': 'docs/HIBY-R1-NETWORK-EMULATION.md',
        'HIBY-R1-NETWORK-EMULATION-PL.md': 'docs/HIBY-R1-NETWORK-EMULATION-PL.md',
        'ESPEAK-BLUETOOTH.md': 'docs/ESPEAK-BLUETOOTH.md',
        'ESPEAK-BLUETOOTH-PL.md': 'docs/ESPEAK-BLUETOOTH-PL.md',
        'ESPEAK-HIBY-USB.md': 'docs/ESPEAK-HIBY-USB.md',
        'ESPEAK-HIBY-USB-PL.md': 'docs/ESPEAK-HIBY-USB-PL.md',
    })


def release_documents(manifest):
    added = {'ACCESSIBILITY-TYPING.md', 'ACCESSIBILITY-TYPING-PL.md',
             'ACCESSIBILITY-CURTAIN.md', 'ACCESSIBILITY-CURTAIN-PL.md',
             'HIBY-R1-NETWORK-EMULATION.md', 'HIBY-R1-NETWORK-EMULATION-PL.md'}
    hardening = {'INTERFACE-APPEARANCE.md', 'INTERFACE-APPEARANCE-PL.md',
                 'HIBY-R1-POWER.md', 'HIBY-R1-POWER-PL.md'}
    legacy = manifest.get('version') in {'r34-alpha1-20261014', 'r34-alpha2-20261015',
                                       'r34-alpha3-20261015'}
    screen_documents = {'ACCESSIBILITY-SCREEN.md', 'ACCESSIBILITY-SCREEN-PL.md'}
    screen_legacy = legacy or manifest.get('version') == 'r34-alpha4-20261015'
    connectivity_documents = {'ACCESSIBILITY-SHORTCUT.md', 'ACCESSIBILITY-SHORTCUT-PL.md',
                              'HIBY-R1-CONNECTIVITY.md', 'HIBY-R1-CONNECTIVITY-PL.md'}
    connectivity_legacy = screen_legacy or manifest.get('version') == 'r34-alpha5-20261015'
    talkbox_documents = {'ESPEAK-ROCKBOX.md', 'ESPEAK-ROCKBOX-PL.md',
                         'ACCESSIBILITY-LISTS.md', 'ACCESSIBILITY-LISTS-PL.md'}
    radio_documents = {'RADIO-DYNAMIC.md', 'RADIO-DYNAMIC-PL.md'}
    alpha_version = re.fullmatch(r'r34-alpha([1-9][0-9]*)-[0-9]{8}', manifest.get('version', ''))
    talkbox_legacy = alpha_version is not None and int(alpha_version[1]) < 11
    radio_legacy = alpha_version is not None and int(alpha_version[1]) < 13
    return {name: relative for name, relative in documents().items()
            if (manifest.get('espeak_data_provenance') is not None or name not in added
                or TARGET.document_prefix + name in manifest['files'])
            and (name not in hardening or not legacy or TARGET.document_prefix + name in manifest['files'])
            and (name not in screen_documents or not screen_legacy or TARGET.document_prefix + name in manifest['files'])
            and (name not in connectivity_documents or not connectivity_legacy or TARGET.document_prefix + name in manifest['files'])
            and (name not in talkbox_documents or not talkbox_legacy or TARGET.document_prefix + name in manifest['files'])
            and (name not in radio_documents or not radio_legacy or TARGET.document_prefix + name in manifest['files'])}


def runtime_notices(directory):
    files = shared.tree_files(directory)
    if not files or any(not path.stat().st_size for path in files.values()):
        raise RuntimeError('Missing actual toolchain license/provenance notices')
    text = '\n'.join(path.read_text(encoding='utf-8') for path in files.values())
    if ('GCC RUNTIME LIBRARY EXCEPTION' not in text or 'Version 3.1' not in text or
            'GNU LESSER GENERAL PUBLIC LICENSE' not in text or
            'GNU GENERAL PUBLIC LICENSE' not in text):
        raise RuntimeError('Actual hosted toolchain notices must include GPL, LGPL and GCC Runtime Library Exception 3.1')
    return files


def runtime_libraries(environment, needed):
    libraries = {}
    needed = set(needed)
    if 'libasound.so.2' in needed:
        needed.update(ALSA_DEPENDENCIES)
    sysroot_text = subprocess.check_output([PREFIX + 'gcc', '-print-sysroot'], env=environment, text=True).strip()
    sysroot = Path(sysroot_text) if sysroot_text else None
    for name in sorted(set(needed) | {'libgcc.a'}):
        resolved = subprocess.check_output([PREFIX + 'gcc', '-print-file-name=' + name], env=environment, text=True).strip()
        path = Path(resolved)
        if not path.is_absolute() or not path.is_file():
            matches = [sysroot / relative / name for relative in ('lib', 'usr/lib', 'lib32', 'usr/lib32')] if sysroot else []
            matches = [candidate for candidate in matches if candidate.is_file()]
            if not matches:
                raise RuntimeError(f'Cannot identify actual linked toolchain runtime: {name}')
            path = matches[0]
        path = path.resolve(strict=True)
        libraries[name] = {'path': str(path), 'sha256': sha256(path.read_bytes())}
    return libraries


def alsa_source_files(archive, notices):
    archive = archive.resolve(strict=True)
    if archive.name != ALSA_SOURCE_NAME or sha256(archive.read_bytes()) != ALSA_SOURCE_SHA256:
        raise RuntimeError('Expected the original verified ALSA 1.0.26 source archive')
    provenance = json.loads(notices['provenance.json'].read_bytes())
    source = provenance['sources'][ALSA_SOURCE_NAME]
    copying = 'alsa-lib-1.0.26/COPYING'
    if (source['archive_sha256'] != ALSA_SOURCE_SHA256 or
            source['source_provenance']['sha256'] != ALSA_SOURCE_SHA256 or
            source['original_files'].get(copying) != ALSA_COPYING_SHA256 or
            sha256(notices[copying].read_bytes()) != ALSA_COPYING_SHA256):
        raise RuntimeError('ALSA source archive/notices disagree with toolchain provenance')
    toolchain_root = archive.parent.parent
    recipes = provenance['recipe']['files']
    if recipes != ALSA_RECIPE_FILES:
        raise RuntimeError('Unknown ALSA toolchain build recipe')
    files = {ALSA_SOURCE_PREFIX + ALSA_SOURCE_NAME: archive}
    for name, digest in recipes.items():
        relative = safe_name(name)
        if not name.startswith('official/tools/'):
            raise RuntimeError('Unexpected toolchain recipe source path')
        path = confined_path(toolchain_root / relative, toolchain_root).resolve(strict=True)
        if not path.is_file() or sha256(path.read_bytes()) != digest:
            raise RuntimeError(f'Toolchain build recipe changed: {name}')
        files[ALSA_SOURCE_PREFIX + relative.as_posix()] = path
    return files


def bundled_runtime(environment, validation, build, runtime):
    needed = {name for item in validation['elf_evidence'].values() for name in item['needed']}
    if 'libasound.so.2' not in needed:
        return {}, {}
    library = Path(runtime['libasound.so.2']['path'])
    content = library.read_bytes()
    metadata = validate_alsa(content)
    if metadata['sha256'] != runtime['libasound.so.2']['sha256']:
        raise RuntimeError('Actual linked ALSA library changed')
    inspect_elf(library, environment, build / 'elf-verification/libasound.so.2.txt', runtime=True)
    with zipfile.ZipFile(build / 'rockbox.zip') as archive:
        consumers = {name: archive.read(name) for name in [FIRMWARE, *validation['modules']]}
    validate_alsa_consumers(content, consumers)
    return {ALSA_LIBRARY: content}, {ALSA_LIBRARY: metadata}


def freeze_sources(source, notices, alsa_sources=None):
    files = {}
    modes = {}
    for prefix, repository in (('rockbox', ROOT), ('espeak-1.44.05-source', source)):
        selected = shared.source_files(repository)
        selected = {name: path for name, path in selected.items() if name not in shared.SOURCE_BINARY_ASSETS
                    and PurePosixPath(name).suffix.lower() not in shared.IMAGE_SUFFIXES | {'.r1', '.upt'}}
        if prefix == 'espeak-1.44.05-source':
            selected.update({'espeak-data/' + name: path for name, path in shared.runtime_files(source).items()})
        files.update({prefix + '/' + name: path for name, path in selected.items()})
        modes.update({prefix + '/' + name: mode for name, mode in shared.source_modes(repository).items()})
    for name, path in notices.items():
        relative = 'rockbox/docs/native-runtime-licenses/hibyr1/' + name
        if relative in files:
            raise RuntimeError(f'Toolchain notice would overwrite a source: {relative}')
        files[relative] = path
    for name, path in (alsa_sources or {}).items():
        if name in files:
            raise RuntimeError(f'ALSA source would overwrite a source: {name}')
        files[name] = path
    return files, hashes(files), modes


def assert_frozen(source, notices, expected, modes, alsa_sources=None):
    current = freeze_sources(source, notices, alsa_sources)
    if current[1] != expected or current[2] != modes:
        raise RuntimeError('Sources/notices/modes changed after freeze; this build must not be published')
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != ENGINE_REVISION:
        raise RuntimeError('Supplied eSpeak source revision changed after freeze')
    validate_supplied_data(source)


def validate_package_entry(name, content):
    relative = safe_name(name)
    if len(relative.parts) < 2 or relative.parts[0] != '.rockbox':
        raise RuntimeError(f'Unexpected package root: {name}')
    if name == '.rockbox/database.ignore' and content == b'':
        return
    lower = relative.name.lower()
    if (shared.diagnostic_card_state(relative) or lower in shared.STATE_NAMES or lower.startswith(('accessibility.cfg.', 'accessibility-typing.cfg.', 'accessibility-screen.cfg.',
                                                       'accessibility-shortcut.cfg.', 'connectivity.cfg.',
                                                       'accessibility-typing-echo.cfg.', 'accessibility-lock.cfg.', 'touch-sensitivity.cfg.',
                                                       'empty-feedback.cfg.')) or
            '.bmark.' in lower or '.bookmark.' in lower or
            lower.endswith(('.voice', '.talk', '.gc', '.upt')) or
            any(part.lower() in {'database', 'playlists', 'recordings', 'bookmarks'} for part in relative.parts) or
            lower.startswith(('database_', 'database.', 'resume.')) or
            lower.endswith(('.bmark', '.bookmark', '.m3u', '.m3u8', '.log')) or
            'bootloader' in lower or 'vendor' in lower or
            (relative.suffix.lower() in shared.IMAGE_SUFFIXES | {'.r1'} and name != FIRMWARE)):
        raise RuntimeError(f'Bootloader/vendor image or dirty runtime profile: {name}')
    if name == FIRMWARE:
        validate_elf(content)
    elif name == ALSA_LIBRARY:
        validate_alsa(content)
    elif re.search(r'\.so(?:\..*)?$', relative.name, re.I):
        raise RuntimeError(f'Unexpected bundled runtime library: {name}')
    elif name == AUTOSTART_FILE:
        if content != AUTOSTART_SEED:
            raise RuntimeError('Autostart must be the clean pinned-loader Rockbox seed')
    elif relative.suffix.lower() in MODULE_SUFFIXES:
        validate_module(name, content)
    elif relative.suffix.lower() in {'.lng', '.vstrings'}:
        shared.validate_catalog(name, content, TARGET)


def verify_firmware_zip(path, expected_data=None, expected_catalogs=None):
    with zipfile.ZipFile(path) as archive:
        entries = zip_entries(archive)
        if MANIFEST not in entries:
            raise RuntimeError('Missing R1 application manifest')
        manifest = json.loads(archive.read(MANIFEST))
        if (manifest.get('target') != 'hibyr1' or manifest.get('plugin_abi') != PLUGIN_ABI or
                manifest.get('engine_revision') not in (ENGINE_REVISION, shared.LEGACY_ENGINE_REVISION) or
                manifest.get('hardware_tested') is not False or
                manifest.get('channel') not in {'diagnostic', 'experimental', 'hardware-test'} or
                manifest.get('firmware_library_compatibility') != 'untested' or
                manifest.get('memory_configuration_mib') != 16 or manifest.get('core_arena_mib') != 15):
            raise RuntimeError('Invalid experimental hosted R1 identity')
        if (manifest.get('channel') == 'hardware-test' and
                (manifest.get('native_runtime_verified') is not False or
                 manifest.get('warning') != HARDWARE_TEST_WARNING)):
            raise RuntimeError('Hardware-test packages must explicitly disclose unverified native execution')
        if manifest.get('autostart') != AUTOSTART:
            raise RuntimeError('Missing pinned-loader factory autostart metadata')
        files = manifest['files']
        if set(entries) != set(files) | {MANIFEST}:
            raise RuntimeError('Unmanifested or missing package files')
        for name, digest in files.items():
            content = archive.read(name)
            if sha256(content) != digest:
                raise RuntimeError(f'Package hash mismatch: {name}')
            validate_package_entry(name, content)
        required = {FIRMWARE, '.rockbox/config.cfg', '.rockbox/rockbox-info.txt', AUTOSTART_FILE,
                    TARGET.document_prefix + 'SPDX.json'}
        required.update(TARGET.document_prefix + name for name in release_documents(manifest))
        required.update(CATALOG_PREFIX + language + suffix for language in ('english', 'polski')
                        for suffix in ('.lng', '.vstrings'))
        required.update(DATA_PREFIX + name for name in shared.REQUIRED_DATA)
        if not required <= entries.keys():
            raise RuntimeError(f'Missing runtime assets: {sorted(required - entries.keys())}')
        if archive.read('.rockbox/config.cfg') != DEFAULT_CONFIG:
            raise RuntimeError('Package does not use the clean Polish default profile')
        validate_build_info(archive.read('.rockbox/rockbox-info.txt').decode('utf-8'), manifest['version'])
        if validate_elf(archive.read(FIRMWARE)) != manifest['application']:
            raise RuntimeError('Application ELF metadata mismatch')
        modules = {name: validate_module(name, archive.read(name)) for name in files
                   if PurePosixPath(name).suffix.lower() in MODULE_SUFFIXES}
        if modules != manifest['modules'] or not any(name.endswith('.rock') for name in modules) or not any(
                name.endswith('.codec') for name in modules):
            raise RuntimeError('Missing or inconsistent rebuilt module inventory')
        needed = set(manifest['application']['needed']) | {library for item in modules.values() for library in item['needed']}
        bundled = {ALSA_LIBRARY: validate_alsa(archive.read(ALSA_LIBRARY))} if ALSA_LIBRARY in files else {}
        expected_bundled = {ALSA_LIBRARY} if 'libasound.so.2' in needed else set()
        if set(bundled) != expected_bundled or bundled != manifest.get('bundled_runtime', {}):
            raise RuntimeError('Missing or inconsistent required bundled ALSA runtime')
        if bundled:
            if manifest.get('system_runtime', {}).get('libasound.so.2', {}).get('sha256') != bundled[ALSA_LIBRARY]['sha256']:
                raise RuntimeError('Bundled ALSA differs from actual linked toolchain runtime')
            validate_alsa_consumers(archive.read(ALSA_LIBRARY),
                                    {name: archive.read(name) for name in [FIRMWARE, *modules]})
        data = {name[len(DATA_PREFIX):]: digest for name, digest in files.items() if name.startswith(DATA_PREFIX)}
        catalogs = {name[len(CATALOG_PREFIX):]: digest for name, digest in files.items()
                    if name.startswith(CATALOG_PREFIX) and name.endswith('.vstrings')}
        if data != manifest['runtime_data'] or expected_data is not None and data != expected_data:
            raise RuntimeError('eSpeak data differs from the supplied runtime')
        if manifest.get('espeak_data_provenance') is not None:
            validate_packaged_data(manifest['espeak_data_provenance'], data)
        if catalogs != manifest['voice_catalogs'] or expected_catalogs is not None and catalogs != expected_catalogs:
            raise RuntimeError('Missing or stale generated voice catalogs')
        if {name[:-9] for name in catalogs} != {PurePosixPath(name).stem for name in files
                if name.startswith(CATALOG_PREFIX) and name.endswith('.lng')}:
            raise RuntimeError('Language and voice catalogs do not form complete pairs')
        notices = {name[len(NOTICE_PREFIX):]: digest for name, digest in files.items() if name.startswith(NOTICE_PREFIX)}
        if not notices or notices != manifest['runtime_notice_hashes']:
            raise RuntimeError('Missing actual toolchain notices')
        notice_text = '\n'.join(archive.read(NOTICE_PREFIX + name).decode('utf-8') for name in notices)
        if ('GCC RUNTIME LIBRARY EXCEPTION' not in notice_text or 'Version 3.1' not in notice_text or
                'GNU LESSER GENERAL PUBLIC LICENSE' not in notice_text or 'GNU GENERAL PUBLIC LICENSE' not in notice_text):
            raise RuntimeError('Incomplete hosted toolchain licensing notices')
        spdx = json.loads(archive.read(TARGET.document_prefix + 'SPDX.json'))
        spdx_hashes = {}
        for item in spdx.get('files', []):
            name = item['fileName']
            if name in spdx_hashes or item.get('licenseConcluded') != 'NOASSERTION':
                raise RuntimeError('Invalid SPDX file inventory')
            checksums = item['checksums']
            if len(checksums) != 1 or checksums[0]['algorithm'] != 'SHA256':
                raise RuntimeError('Invalid SPDX checksums')
            spdx_hashes[name] = checksums[0]['checksumValue']
        if spdx.get('spdxVersion') != 'SPDX-2.3' or spdx_hashes != {
                name: digest for name, digest in files.items() if name != TARGET.document_prefix + 'SPDX.json'}:
            raise RuntimeError('SPDX does not match packaged files')
        evidence = manifest['elf_evidence']
        if set(evidence) != set(modules) | {'rockbox.elf', FIRMWARE}:
            raise RuntimeError('Missing per-module readelf evidence')
        for name in set(modules) | {FIRMWARE}:
            expected = modules[name] if name in modules else manifest['application']
            if (evidence[name]['needed'] != expected['needed'] or
                    evidence[name]['version_requirements'] != expected['version_requirements']):
                raise RuntimeError('readelf dependency/version evidence mismatch')
        return manifest


def write_firmware_zip(base_zip, output, additions, metadata):
    files = {}
    with zipfile.ZipFile(base_zip) as base:
        entries = zip_entries(base)
        contents = {}
        for name in sorted(entries):
            if name.lower().endswith(('.voice', '.talk')):
                continue
            if name == '.rockbox/config.cfg' or name == MANIFEST or name.startswith(DATA_PREFIX):
                raise RuntimeError(f'Unexpected pre-existing profile/data in fresh make zip: {name}')
            content = base.read(name)
            if name in additions:
                if not name.endswith('.vstrings') or content != additions[name]:
                    raise RuntimeError(f'Conflicting package addition: {name}')
                continue
            contents[name] = content
        contents.update(additions)
        for name, content in contents.items():
            validate_package_entry(name, content)
            files[name] = sha256(content)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        spdx = {'spdxVersion': 'SPDX-2.3', 'dataLicense': 'CC0-1.0', 'SPDXID': 'SPDXRef-DOCUMENT',
                'name': 'Experimental HiBy R1 ' + metadata['version'],
                'documentNamespace': 'https://spdx.org/spdxdocs/rockbox-hibyr1-' + sha256(json_bytes(files)),
                'creationInfo': {'created': timestamp, 'creators': ['Tool: build_espeak_hiby.py']},
                'files': [{'SPDXID': f'SPDXRef-File-{index}', 'fileName': name,
                           'checksums': [{'algorithm': 'SHA256', 'checksumValue': digest}],
                           'licenseConcluded': 'NOASSERTION', 'licenseInfoInFile': ['NOASSERTION'],
                           'copyrightText': 'NOASSERTION'} for index, (name, digest) in enumerate(sorted(files.items()))]}
        contents[TARGET.document_prefix + 'SPDX.json'] = json_bytes(spdx)
        files[TARGET.document_prefix + 'SPDX.json'] = sha256(json_bytes(spdx))
        manifest = dict(metadata, files=files)
        with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(contents.items()):
                archive.writestr(name, content)
            archive.writestr(MANIFEST, json_bytes(manifest))
    return manifest


def verify_release(firmware, source_archive=None):
    manifest = verify_firmware_zip(firmware)
    source_name = manifest['source_archive']['name']
    if safe_name(source_name).name != source_name:
        raise RuntimeError('Unsafe corresponding-source archive filename')
    source_archive = source_archive or firmware.parent / source_name
    if sha256(source_archive.read_bytes()) != manifest['source_archive']['sha256']:
        raise RuntimeError('Corresponding source archive hash mismatch')
    source_manifest = verify_source_archive(source_archive)
    if (source_manifest.get('target') != 'hibyr1' or source_manifest.get('version') != manifest['version'] or
            source_manifest.get('engine_revision') != manifest['engine_revision'] or
            sha256(json_bytes(source_manifest['files'])) != manifest['source_inventory_sha256']):
        raise RuntimeError('Source inventory does not match this application build')
    provenance = manifest.get('espeak_data_provenance')
    if source_manifest.get('espeak_data_provenance') != provenance:
        raise RuntimeError('Application/source eSpeak data provenance mismatch')
    if provenance is not None:
        if provenance.get('engine_revision') != manifest['engine_revision']:
            raise RuntimeError('Application/eSpeak data provenance revision mismatch')
        validate_packaged_data(provenance, manifest['runtime_data'], source_manifest['files'])
    for name, digest in manifest['runtime_data'].items():
        if source_manifest['files'].get('espeak-1.44.05-source/espeak-data/' + name) != digest:
            raise RuntimeError('Source archive runtime data mismatch')
    for name, digest in manifest['runtime_notice_hashes'].items():
        if source_manifest['files'].get('rockbox/docs/native-runtime-licenses/hibyr1/' + name) != digest:
            raise RuntimeError('Source archive toolchain notice mismatch')
    for name, relative in release_documents(manifest).items():
        if source_manifest['files'].get('rockbox/' + relative) != manifest['files'][TARGET.document_prefix + name]:
            raise RuntimeError('Source archive packaged documentation/license mismatch')
    alsa_sources = {name: digest for name, digest in source_manifest['files'].items() if name.startswith(ALSA_SOURCE_PREFIX)}
    if alsa_sources != manifest.get('alsa_sources', {}) or source_manifest.get('alsa_sources', {}) != alsa_sources:
        raise RuntimeError('ALSA corresponding-source inventory mismatch')
    if manifest.get('bundled_runtime'):
        expected_alsa_sources = {ALSA_SOURCE_PREFIX + ALSA_SOURCE_NAME: ALSA_SOURCE_SHA256,
                                 **{ALSA_SOURCE_PREFIX + name: digest for name, digest in ALSA_RECIPE_FILES.items()}}
        if (alsa_sources != expected_alsa_sources or
                manifest['runtime_notice_hashes'].get('alsa-lib-1.0.26/COPYING') != ALSA_COPYING_SHA256):
            raise RuntimeError('Missing original ALSA corresponding source, build recipe or license')
    sums = {}
    for line in (firmware.parent / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match or match[2] in sums or safe_name(match[2]).name != match[2]:
            raise RuntimeError('Invalid release SHA256SUMS')
        sums[match[2]] = match[1]
    if sums != {firmware.name: sha256(firmware.read_bytes()), source_name: sha256(source_archive.read_bytes())}:
        raise RuntimeError('Release SHA256SUMS mismatch')
    return manifest


def validate_runtime_evidence(path, manifest):
    evidence = json.loads(path.read_bytes())
    if (evidence.get('target') != 'hibyr1' or evidence.get('version') != manifest['version'] or
            evidence.get('application_sha256') != manifest['application']['sha256'] or
            evidence.get('source_inventory_sha256') != manifest['source_inventory_sha256'] or
            evidence.get('scope') not in {'qemu-mipsel', 'device'} or
            any(evidence.get('checks', {}).get(check) is not True for check in ('startup', 'synthesis', 'module_loading'))):
        raise RuntimeError('Missing successful build-bound native runtime evidence')
    artifacts = evidence.get('artifacts')
    if not isinstance(artifacts, dict) or not artifacts:
        raise RuntimeError('Runtime evidence must reference hashed diagnostic artifacts')
    workspace = project_materials_root(ROOT)
    for name, digest in artifacts.items():
        safe_name(name)
        artifact = confined_path(workspace / name, workspace)
        if not artifact.is_file() or sha256(artifact.read_bytes()) != digest:
            raise RuntimeError(f'Native runtime evidence artifact mismatch: {name}')
    return evidence


def publish_release(staging, arguments, source, notices, toolchain, environment):
    provenance = validate_supplied_data(source)
    if arguments.publish_hardware_test and arguments.runtime_evidence:
        raise RuntimeError('Hardware-test publication cannot claim native runtime evidence')
    build = project_materials_root(ROOT) / 'build-espeak-hibyr1'
    staging = confined_path(staging, build)
    if staging != build / 'release-staging':
        raise RuntimeError('Publication requires the dedicated R1 release-staging directory')
    archives = list(staging.glob('*.zip'))
    if len(archives) != 1:
        raise RuntimeError('Expected exactly one staged R1 application package')
    manifest = verify_release(archives[0])
    if manifest.get('espeak_data_provenance') != provenance:
        raise RuntimeError('Staged package differs from current supplied eSpeak data provenance')
    if manifest['version'] != arguments.version or manifest['toolchain'] != toolchain:
        raise RuntimeError('Staged package version/toolchain changed')
    validation = validate_native_build(build, arguments.version, environment)
    if any(manifest.get(key) != value for key, value in validation.items()):
        raise RuntimeError('Staged package differs from fresh ELF/readelf/module validation')
    needed = {library for item in validation['elf_evidence'].values() for library in item['needed']}
    runtime = runtime_libraries(environment, needed)
    if runtime != manifest['system_runtime']:
        raise RuntimeError('Staged toolchain runtime changed')
    _, bundled = bundled_runtime(environment, validation, build, runtime)
    if bundled != manifest.get('bundled_runtime', {}):
        raise RuntimeError('Staged bundled runtime differs from freshly validated linked ALSA')
    alsa_sources = alsa_source_files(arguments.alsa_source, notices) if arguments.alsa_source else {}
    frozen = freeze_sources(source, notices, alsa_sources)
    if sha256(json_bytes(frozen[1])) != manifest['source_inventory_sha256']:
        raise RuntimeError('Sources changed since the staged package freeze')
    hardware_test = arguments.publish_hardware_test
    if hardware_test:
        if (manifest['channel'] != 'hardware-test' or manifest.get('native_runtime_verified') is not False or
                manifest.get('hardware_tested') is not False or manifest.get('warning') != HARDWARE_TEST_WARNING):
            raise RuntimeError('Hardware-test publication requires an explicitly labeled hardware-test staging package')
        evidence = None
        print('WARNING: ' + HARDWARE_TEST_WARNING, flush=True)
    else:
        evidence = validate_runtime_evidence(arguments.runtime_evidence, manifest)
    before = hashes(shared.tree_files(staging))
    shared.assert_unused(staging)
    assert_frozen(source, notices, frozen[1], frozen[2], alsa_sources)
    if validate_supplied_data(source) != provenance:
        raise RuntimeError('Supplied eSpeak data changed before publication')
    installfiles = project_materials_root(ROOT, 'installfiles')
    release = confined_path(installfiles / 'hibyr1', installfiles)
    shared.ensure_publication_filesystem(staging, release)
    shared.preserve(release, 'hibyr1-native-release')
    release.parent.mkdir(parents=True, exist_ok=True)
    if hashes(shared.tree_files(staging)) != before:
        raise RuntimeError('Staging changed before publication')
    print(f'Moving verified experimental R1 package (not copying): {staging} -> {release}', flush=True)
    shutil.move(str(staging), str(release))
    if hashes(shared.tree_files(release)) != before:
        raise RuntimeError('Published R1 package integrity failure')
    verify_release(release / archives[0].name)
    (build / 'publication.json').write_bytes(json_bytes({'release': str(release), 'files': before,
        'channel': manifest['channel'], 'native_runtime_verified': evidence is not None, 'hardware_tested': False,
        'warning': manifest.get('warning'), 'runtime_evidence': evidence, 'firmware_library_compatibility': 'untested'}))


def package_application(arguments, source, environment, toolchain, build):
    provenance = validate_supplied_data(source)
    notices = runtime_notices(arguments.toolchain_notices)
    alsa_sources = alsa_source_files(arguments.alsa_source, notices)
    if arguments.staged:
        publish_release(arguments.staged, arguments, source, notices, toolchain, environment)
        return
    files, frozen, modes = freeze_sources(source, notices, alsa_sources)
    data = shared.runtime_files(source)
    data_hashes = hashes(data)
    validate_packaged_data(provenance, data_hashes, frozen)
    configure = build_application(build, arguments.version, arguments.jobs, environment)
    (build / 'source-freeze.json').write_bytes(json_bytes({'files': frozen, 'modes': modes}))
    validation = validate_native_build(build, arguments.version, environment)
    needed = {library for evidence in validation['elf_evidence'].values() for library in evidence['needed']}
    runtime = runtime_libraries(environment, needed)
    runtime_additions, bundled = bundled_runtime(environment, validation, build, runtime)
    assert_frozen(source, notices, frozen, modes, alsa_sources)
    catalogs = {path.name: path for path in sorted((build / 'apps/lang').glob('*.vstrings'))}
    if not {'english.vstrings', 'polski.vstrings'} <= catalogs.keys():
        raise RuntimeError('Missing generated Polish/English voice catalogs')
    additions = {DATA_PREFIX + name: path.read_bytes() for name, path in data.items()}
    additions.update({CATALOG_PREFIX + name: path.read_bytes() for name, path in catalogs.items()})
    additions.update({TARGET.document_prefix + name: (ROOT / relative).read_bytes() for name, relative in documents().items()})
    additions.update({NOTICE_PREFIX + name: path.read_bytes() for name, path in notices.items()})
    additions.update(runtime_additions)
    additions[AUTOSTART_FILE] = AUTOSTART_SEED
    additions['.rockbox/config.cfg'] = DEFAULT_CONFIG
    staging = build / 'release-staging'
    staging.mkdir(exist_ok=False)
    source_archive = staging / f'rockbox-hibyr1-espeak-{arguments.version}-source.tar.gz'
    hardware_test = arguments.publish_hardware_test or arguments.stage_hardware_test
    metadata = {'version': arguments.version, 'target': 'hibyr1', 'engine_revision': ENGINE_REVISION,
                'plugin_abi': PLUGIN_ABI, 'channel': 'hardware-test' if hardware_test else
                    ('experimental' if arguments.publish else 'diagnostic'),
                'kind': 'Experimental hosted Linux HiBy R1 application',
                'warning': HARDWARE_TEST_WARNING if hardware_test else
                    'Target firmware/library compatibility and physical R1 execution are untested.',
                'native_runtime_verified': False, 'bundled_runtime': bundled,
                'alsa_sources': hashes(alsa_sources), 'autostart': AUTOSTART,
                'toolchain': toolchain, 'system_runtime': runtime, 'runtime_notice_hashes': hashes(notices),
                'rockbox_revision': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                'source_inventory_sha256': sha256(json_bytes(frozen)), 'configure_arguments': configure[2:],
                'runtime_data': data_hashes, 'espeak_data_provenance': provenance,
                'voice_catalogs': hashes(catalogs), **validation}
    print(f'Creating retained corresponding-source delivery: {source_archive}', flush=True)
    print('Copying exact supplied runtime data/notices into the device ZIP and source delivery for their distinct roles.', flush=True)
    write_source_archive(source_archive, files, frozen, modes, metadata)
    verify_source_archive(source_archive, frozen)
    metadata['source_archive'] = {'name': source_archive.name, 'sha256': sha256(source_archive.read_bytes())}
    output = staging / f'rockbox-hibyr1-espeak-{arguments.version}-{metadata["channel"]}.zip'
    write_firmware_zip(build / 'rockbox.zip', output, additions, metadata)
    (staging / 'SHA256SUMS').write_text(''.join(f'{sha256(path.read_bytes())}  {path.name}\n'
        for path in (output, source_archive)), encoding='utf-8')
    verify_firmware_zip(output, data_hashes, hashes(catalogs))
    verify_release(output)
    assert_frozen(source, notices, frozen, modes, alsa_sources)
    if toolchain_versions(environment) != toolchain:
        raise RuntimeError('Toolchain changed during compilation; do not publish')
    if runtime_libraries(environment, needed) != runtime:
        raise RuntimeError('Actual linked toolchain runtime changed; do not publish')
    if bundled_runtime(environment, validation, build, runtime)[1] != bundled:
        raise RuntimeError('Bundled ALSA changed during packaging; do not publish')
    (build / 'package-verification.json').write_bytes(json_bytes({'package': str(output),
        'sha256': sha256(output.read_bytes()), 'source_inventory_sha256': metadata['source_inventory_sha256'],
        'checks': ['ELF ABI/readelf/dependencies/versions', 'all module headers', 'clean Polish profile',
                   'exact runtime data and catalog pairs', 'ZIP/source/SPDX/SHA256SUMS integrity'],
        'native_runtime_verified': False, 'hardware_tested': False}))
    if arguments.publish or arguments.publish_hardware_test:
        publish_release(staging, arguments, source, notices, toolchain, environment)
    else:
        print(f'Verified diagnostic R1 package staged: {output}; nothing published.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build and verify experimental hosted HiBy R1 eSpeak packages.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--build-only', action='store_true', help='Compile diagnostic outputs in Workspace without source freeze, packaging or publication')
    parser.add_argument('--source-frozen', action='store_true', help='Main confirms that all workers have stopped editing sources')
    parser.add_argument('--version', help='Unique experimental identifier, e.g. r29-alpha1-20261010')
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 2, 8))
    parser.add_argument('--toolchain-bin', type=Path, help='Exact hosted GCC 9.5.0 bin directory; otherwise use PATH')
    parser.add_argument('--espeak-source', type=Path, default=ROOT.parent / 'espeak-1.44.05-source')
    parser.add_argument('--toolchain-notices', type=Path, help='Actual toolchain license/provenance files for the source and application packages')
    parser.add_argument('--alsa-source', type=Path, help='Original verified ALSA 1.0.26 archive in the toolchain downloads directory, required for packaging/publication')
    mode.add_argument('--publish', action='store_true', help='Explicitly publish a verified staged package after runtime evidence checks')
    mode.add_argument('--publish-hardware-test', action='store_true', help='Explicitly publish a first-device-test package WITHOUT claiming native runtime or hardware acceptance')
    mode.add_argument('--stage-hardware-test', action='store_true', help='Build and validate hardware-test staging only; publish later with --staged and --publish-hardware-test')
    parser.add_argument('--staged', type=Path, help='Publish existing release-staging instead of rebuilding; requires an explicit publication mode and --source-frozen')
    parser.add_argument('--runtime-evidence', type=Path, help='Build-bound native startup/synthesis/module-loading evidence JSON')
    parser.add_argument('--verify', type=Path, help='Read-only integrity verification of an application ZIP and corresponding source')
    parser.add_argument('--source-archive', type=Path)
    arguments = parser.parse_args(argv)
    if arguments.verify:
        if arguments.build_only or arguments.publish or arguments.publish_hardware_test or arguments.stage_hardware_test or arguments.staged or arguments.runtime_evidence:
            parser.error('--verify cannot build or publish')
        verify_release(arguments.verify, arguments.source_archive)
        print('R1 package/source integrity PASS; target firmware/library compatibility remains untested.')
        return
    if arguments.source_archive:
        parser.error('--source-archive requires --verify')
    if arguments.staged and not (arguments.publish or arguments.publish_hardware_test):
        parser.error('--staged requires --publish or --publish-hardware-test')
    if arguments.runtime_evidence and not arguments.publish:
        parser.error('--runtime-evidence is reserved for verified --publish; hardware-test publication cannot claim it')
    if (not arguments.version or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', arguments.version)
            or arguments.jobs < 1):
        parser.error('Supply a safe --version identifier and a positive --jobs count')
    if not arguments.build_only and (not arguments.source_frozen or not arguments.toolchain_notices or not arguments.alsa_source):
        parser.error('Packaging requires main source freeze (--source-frozen), --toolchain-notices and --alsa-source')
    if arguments.publish and not arguments.runtime_evidence:
        parser.error('--publish requires build-bound --runtime-evidence')
    if sys.platform != 'linux':
        parser.error('Build inside Linux/WSL with the exact hosted MIPS GCC 9.5.0 toolchain')
    source = arguments.espeak_source.resolve(strict=True)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != ENGINE_REVISION:
        raise RuntimeError(f'Expected supplied eSpeak source commit {ENGINE_REVISION}, found {revision}')
    provenance = validate_supplied_data(source)
    shared.runtime_files(source)
    environment = toolchain_environment(arguments.toolchain_bin)
    environment.update(VERSION=arguments.version, OMP_NUM_THREADS=str(arguments.jobs), LC_ALL='C')
    toolchain = toolchain_versions(environment)
    shared.ensure_ignored(ROOT, ['Workspace', 'snapshots', 'installfiles'])
    workspace = project_materials_root(ROOT)
    build = confined_path(workspace / 'build-espeak-hibyr1', workspace)
    if arguments.build_only:
        build_application(build, arguments.version, arguments.jobs, environment)
        report = validate_native_build(build, arguments.version, environment)
        if validate_supplied_data(source) != provenance:
            raise RuntimeError('Supplied eSpeak data changed during diagnostic compilation')
        (build / 'diagnostic-build.json').write_bytes(json_bytes(dict(report, toolchain=toolchain,
            espeak_data_provenance=provenance,
            version=arguments.version, source_frozen=False, publishable=False,
            warning='Diagnostic compilation only; no corresponding-source package or native runtime acceptance.')))
        print(f'Diagnostic R1 build validated: {build}; nothing published.')
        return
    package_application(arguments, source, environment, toolchain, build)


if __name__ == '__main__':
    main()
