import argparse
import base64
import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import zipfile
from typing import NamedTuple


sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_materials import project_materials_root as _project_materials_root, confined_path, ensure_ignored_directories



ROOT = Path(__file__).resolve().parents[1]
ENGINE_REVISION = 'a14831fd3af6b3df77ef23b854cd05ee05b12851'
LEGACY_ENGINE_REVISION = '2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f'


class FirmwareTarget(NamedTuple):
    name: str
    slug: str
    label: str
    model_number: int
    target_id: int
    marker: bytes

    @property
    def document_prefix(self):
        return f'.rockbox/espeak-{self.slug}/'

    @property
    def manifest(self):
        return self.document_prefix + 'manifest.json'


CLIPPLUS = FirmwareTarget('sansaclipplus', 'clipplus', 'Clip+', 66, 66, b'cli+')
CLIPZIP = FirmwareTarget('sansaclipzip', 'clipzip', 'Clip Zip', 79, 68, b'clzp')
TARGETS = {target.name: target for target in (CLIPPLUS, CLIPZIP)}
TARGET_ID = 66
PLUGIN_ABI = 0xe006
PREFIX = 'arm-none-eabi-'
REQUIRED_SYMBOLS = ('rb_espeak_synth_tracked', 'rb_espeak_synth_character',
                    'espeak_Synth', 'tts_speak', 'reclist_speak', 'audio_set_pcm_output')
FIRMWARE = '.rockbox/rockbox.sansa'
MAX_FIRMWARE_PAYLOAD_BYTES = 1024 * 1024
MANIFEST = '.rockbox/espeak-clipplus/manifest.json'
DATA_PREFIX = '.rockbox/espeak-data/'
CATALOG_PREFIX = '.rockbox/langs/'
INTERNAL_DIRS = {'forme', 'workspace', 'installfiles', 'snapshots', 'trash',
                 '.git', '.svn', '.hg', '.ssh', '.cache', '__pycache__',
                 'toolchains', 'node_modules', '.venv', '.rockbox'}
ARTIFACT_SUFFIXES = {'.o', '.a', '.elf', '.exe', '.dll', '.so', '.pyc', '.pyo'}
PRIVATE_NAMES = {'.git-credentials', '.netrc', '_netrc', '.npmrc', '.pypirc',
                 'id_rsa', 'id_ed25519', 'credentials.json', 'agents.md'}
SOURCE_ARCHIVES = {'apps/plugins/puzzles/fonts.zip'}
SOURCE_BINARY_ASSETS = {'firmware/drivers/libertas/firmware/gspi8686_v9.bin',
                        'firmware/drivers/libertas/firmware/gspi8686_v9_helper.bin'}
STATE_NAMES = {'.resume.cfg', '.resume.cfg.new', 'config.cfg.new', 'nvram.bin',
               'playername.txt', 'simulator.log', '.tts-test-profile',
               'accessibility.cfg', 'accessibility-typing.cfg', 'accessibility-screen.cfg',
               'accessibility-shortcut.cfg', 'connectivity.cfg', 'accessibility.cfg.pending',
               'accessibility-typing-echo.cfg', 'accessibility-lock.cfg', 'touch-sensitivity.cfg', 'empty-feedback.cfg',
               'accessibility.cfg.new', 'accessibility.cfg.bak', 'tts-reader.cfg', 'bluetooth.cfg'}
DIAGNOSTIC_CARD_STATE_NAMES = {
    'rockbox.r1.connectivity-original', '.connectivity-state.json', '.connectivity-stage', 'r1-connectivity.log',
    'rockbox.r1.audio-original', 'rockbox.r1.audio-new', 'r1-audio-trace.so',
    'r1-audio-diagnostic.log', 'r1-audio-launcher.log',
}
DIAGNOSTIC_REPORT_ROOTS = {
    ('tools', 'diagnostics', 'hiby_r1_audio', 'reports'),
    ('tools', 'diagnostics', 'hiby_r1_connectivity', 'reports'),
}
IMAGE_SUFFIXES = {'.sansa', '.bin', '.mi4', '.ipod', '.iriver', '.sb', '.upd',
                  '.hex', '.rkw', '.fw', '.rom', '.elf', '.exe', '.dll', '.so',
                  '.apk', '.img'}
DEFAULT_CONFIG = (
    'lang: /.rockbox/langs/polski.lng\ntalk menu: on\ntalk dir: spell\n'
    'talk file: spell\ntalk dir clip: off\ntalk file clip: off\n'
    'tts enabled: on\ntts language: system\ntts variant: \ntts rate: 175\n'
    'tts rate scale: percent\ntts punctuation: none\n'
    'tts ducking: on\ntts ducking level: 25\n'
    'tts pitch: 50\ntts volume: 100\ntts range: 50\ntts wordgap: 0\n'
    'volume: -25\n'
).encode('utf-8')
REQUIRED_DATA = {'phondata', 'phonindex', 'phontab', 'intonations',
                 'pl_dict', 'en_dict', 'voices/pl', 'voices/en/en'}
DOCUMENTS = {
    'ESPEAK-PLUGINS-PL.md': 'docs/ESPEAK-PLUGINS-PL.md',
    'ESPEAK-PLUGINS.md': 'docs/ESPEAK-PLUGINS.md',
    'ESPEAK-BOOKMARKS-PL.md': 'docs/ESPEAK-BOOKMARKS-PL.md',
    'ESPEAK-BOOKMARKS.md': 'docs/ESPEAK-BOOKMARKS.md',
    'CZYTAJ.md': 'docs/ESPEAK-CLIPPLUS-PL.md',
    'README.md': 'docs/ESPEAK-CLIPPLUS.md',
    'Rockbox-COPYING.txt': 'docs/COPYING',
    'Rockbox-LICENSES.txt': 'docs/LICENSES',
    'Rockbox-CREDITS.txt': 'docs/CREDITS',
    'eSpeak-LICENSE.txt': 'lib/espeak/License.txt',
    'eSpeak-PROVENANCE.md': 'lib/espeak/README.md',
    'Sonic-LICENSE.txt': 'lib/espeak/sonic/LICENSE',
    'Sonic-PROVENANCE.md': 'lib/espeak/sonic/README.md',
}
RUNTIME_NOTICES = {
    'newlib-COPYRIGHT.txt': Path('/usr/share/doc/libnewlib-dev/copyright'),
    'newlib-Arm-BSD-3-Clause.txt': ROOT / 'docs/NEWLIB-ARM-NOTICES.txt',
    'GCC-ARM-PACKAGING-COPYRIGHT.txt': Path('/usr/share/doc/gcc-arm-none-eabi/copyright'),
    'GCC13-COPYRIGHT-and-RUNTIME-EXCEPTION.txt': Path('/usr/share/doc/gcc-13-base/copyright'),
    'LGPL-2.1.txt': Path('/usr/share/common-licenses/LGPL-2.1'),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def documents(target):
    return dict(DOCUMENTS, **{
        'CZYTAJ.md': f'docs/ESPEAK-{target.slug.upper()}-PL.md',
        'README.md': f'docs/ESPEAK-{target.slug.upper()}.md',
    })


def contained(path, root=None):
    root = ROOT if root is None else root
    roots = tuple(_project_materials_root(root, category)
                  for category in ('Workspace', 'Snapshots', 'installfiles'))
    resolved = confined_path(path, root, *roots,
                             error='Artifact path escapes project',
                             link_error='Artifact path is a symlink or junction')
    if resolved in roots:
        raise RuntimeError(f'Artifact path must not be a material root: {resolved}')
    return resolved


def safe_name(name):
    parts = name.split('/')
    if (not name or '\\' in name or ':' in name or
            any(part in {'', '.', '..'} or part.endswith((' ', '.')) for part in parts) or
            any(ord(character) < 32 for character in name)):
        raise RuntimeError(f'Unsafe archive path: {name!r}')
    return PurePosixPath(name)


def tree_files(directory):
    directory = confined_path(directory, directory, allow_root=True)
    files = {}
    for path in sorted(directory.rglob('*')):
        confined_path(path, directory)
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise RuntimeError(f'Non-regular artifact: {path}')
        if path.is_file():
            relative = path.relative_to(directory).as_posix()
            safe_name(relative)
            files[relative] = path
    return files


def hashes(files):
    return {name: sha256(path.read_bytes()) for name, path in sorted(files.items())}


def ensure_ignored(root, names):
    for name in names:
        directory = _project_materials_root(root, name)
        legacy = root / name
        if legacy.exists() and legacy != directory:
            ensure_ignored_directories(root, [name])
        ensure_ignored_directories(directory.parent, [directory.name])


def assert_unused(path):
    resolved = path.resolve()
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            links = [process / 'cwd', process / 'exe', *list((process / 'fd').iterdir())]
            for link in links:
                try:
                    target = link.resolve(strict=True)
                except (FileNotFoundError, ProcessLookupError):
                    continue
                if target == resolved or resolved in target.parents:
                    raise RuntimeError(f'Process {process.name} uses {path}')
        except (FileNotFoundError, ProcessLookupError):
            continue
    if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        return
    windows_path = subprocess.check_output(['wslpath', '-w', str(resolved)], text=True).strip()
    payload = base64.b64encode(windows_path.encode('utf-8')).decode('ascii')
    script = r'''
$ErrorActionPreference = 'Stop'
$target = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD'))
$target = [IO.Path]::GetFullPath($target).TrimEnd('\')
foreach ($process in Get-CimInstance Win32_Process) {
    if (($process.ExecutablePath -and ($process.ExecutablePath -eq $target -or
        $process.ExecutablePath.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase))) -or
        ($process.CommandLine -and $process.CommandLine.IndexOf($target, [StringComparison]::OrdinalIgnoreCase) -ge 0)) {
        throw "A Windows process uses $target"
    }
}
foreach ($file in Get-ChildItem -LiteralPath $target -File -Recurse -Force) {
    $handle = [IO.File]::Open($file.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    $handle.Dispose()
}
'''.replace('PAYLOAD', payload)
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], check=True)


def preserve(path, label, root=None):
    root = ROOT if root is None else root
    path = contained(path, root)
    if not path.exists():
        return None
    if not path.is_dir():
        raise RuntimeError(f'Expected an artifact directory: {path}')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', label):
        raise RuntimeError(f'Unsafe snapshot label: {label}')
    for category in ('Workspace', 'Snapshots', 'installfiles'):
        directory = _project_materials_root(root, category)
        if path.is_relative_to(directory):
            prefix = directory.name if category == 'installfiles' else category
            relative = Path(prefix) / path.relative_to(directory)
            break
    else:
        relative = path.relative_to(root.resolve())
    before = hashes(tree_files(path))
    assert_unused(path)
    ensure_ignored(root, ['snapshots'])
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    snapshot = contained(_project_materials_root(root, 'Snapshots') / f'{label}-{stamp}', root)
    destination = contained(snapshot / relative, root)
    if snapshot == path or path in snapshot.parents:
        raise RuntimeError(f'Snapshot must be outside the archived directory: {path}')
    snapshot.mkdir(parents=True, exist_ok=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f'Moving previous {label} (not copying): {path} -> {destination}', flush=True)
    shutil.move(str(path), str(destination))
    if hashes(tree_files(destination)) != before:
        raise RuntimeError(f'Snapshot integrity failure: {destination}')
    (snapshot / 'preservation.json').write_bytes(json_bytes({
        'original_path': relative.as_posix(), 'role': label, 'files': before}))
    return destination


def ensure_publication_filesystem(staging, destination):
    parent = next(path for path in destination.parents if path.exists())
    if staging.stat().st_dev != parent.stat().st_dev:
        raise RuntimeError('Cross-filesystem publication is not supported; the existing release was not replaced')


def source_allowed(name):
    relative = safe_name(name)
    parts = [part.lower() for part in relative.parts]
    if any(part in INTERNAL_DIRS for part in parts):
        return False
    if any(tuple(parts[:len(root)]) == root for root in DIAGNOSTIC_REPORT_ROOTS):
        return False
    if (len(parts) > 1 and parts[0].startswith(('build', 'sim'))) or parts[0] == 'output':
        return False
    if relative.suffix.lower() in ARTIFACT_SUFFIXES or parts[-1] in PRIVATE_NAMES:
        return False
    if relative.suffix.lower() in {'.zip', '.7z', '.tar', '.gz', '.xz', '.msi', '.apk'} and name not in SOURCE_ARCHIVES:
        return False
    if relative.suffix.lower() == '.bin' and name not in SOURCE_BINARY_ASSETS:
        return False
    if parts[-1] == '.env' or (parts[-1].startswith('.env.') and parts[-1] != '.env.example'):
        return False
    return True


def source_files(repository):
    repository = repository.resolve(strict=True)
    names = subprocess.check_output(['git', '-C', str(repository), 'ls-files',
                                     '-z', '--cached', '--others', '--exclude-standard'])
    files = {}
    parents = {}
    for encoded in sorted(set(names.split(b'\0')) - {b''}):
        name = os.fsdecode(encoded)
        if not source_allowed(name):
            continue
        path = repository / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.parent not in parents:
            parents[path.parent] = path.parent.resolve(strict=True)
        resolved = (parents[path.parent] / path.name).resolve(strict=True) if path.is_symlink() else parents[path.parent] / path.name
        if repository not in resolved.parents:
            raise RuntimeError(f'Source link escapes repository: {name}')
        if not source_allowed(resolved.relative_to(repository).as_posix()) or not resolved.is_file():
            raise RuntimeError(f'Unsafe source file: {name}')
        files[name] = path
    return files


def source_modes(repository):
    output = subprocess.check_output(['git', '-C', str(repository), 'ls-files', '--stage', '-z'])
    modes = {}
    for record in output.split(b'\0'):
        if record:
            metadata, name = record.split(b'\t', 1)
            modes[os.fsdecode(name)] = 0o755 if metadata.startswith(b'100755 ') else 0o644
    return modes


def runtime_files(source):
    directory = source / 'espeak-data'
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError(f'Missing exact supplied eSpeak data directory: {directory}')
    files = tree_files(directory)
    if not REQUIRED_DATA <= files.keys() or any(not files[name].stat().st_size for name in REQUIRED_DATA):
        raise RuntimeError('Missing required eSpeak runtime assets')
    return files


def validate_firmware(image, payload=None, target=CLIPPLUS):
    if len(image) <= 8 or image[4:8] != target.marker:
        raise RuntimeError(f'Not a Sansa {target.label} firmware header')
    payload_bytes = len(image) - 8
    if payload_bytes > MAX_FIRMWARE_PAYLOAD_BYTES:
        raise RuntimeError(f'{target.label} raw firmware payload is {payload_bytes} bytes, exceeding the conservative '
                           f'{MAX_FIRMWARE_PAYLOAD_BYTES}-byte (1 MiB) loader limit (8-byte header excluded)')
    checksum = struct.unpack_from('>I', image)[0]
    if checksum != (target.model_number + sum(image[8:])) & 0xffffffff:
        raise RuntimeError(f'Invalid {target.label} firmware checksum')
    if payload is not None and image[8:] != payload:
        raise RuntimeError('Firmware payload does not match rockbox.bin / ELF')
    if not any(image[8:]):
        raise RuntimeError('Empty firmware payload')
    return {'model': target.marker.decode('ascii'), 'model_number': target.model_number, 'checksum': checksum,
            'payload_bytes': payload_bytes, 'payload_sha256': sha256(image[8:])}


def validate_elf(image):
    if (len(image) < 52 or image[:7] != b'\x7fELF\x01\x01\x01' or
            struct.unpack_from('<HH', image, 16) != (2, 40)):
        raise RuntimeError('Expected a 32-bit little-endian ARM executable ELF')


def validate_symbols(symbols):
    names = {match.group(1) for match in re.finditer(r'^\s*[0-9a-fA-F]+\s+[Tt]\s+(\S+)\s*$', symbols, re.M)}
    if not set(REQUIRED_SYMBOLS) <= names:
        raise RuntimeError('ELF is missing defined integrated speech symbols')


def validate_module(name, image, target=CLIPPLUS):
    if len(image) < 28:
        raise RuntimeError(f'Truncated module: {name}')
    magic, target_id, version = struct.unpack_from('<IHH', image)
    suffix = PurePosixPath(name).suffix.lower()
    plugin = suffix in {'.rock', '.ovl'}
    expected_magic = {0x526f634b} if plugin else {0x52434f44, 0x52454e43}
    expected_version = PLUGIN_ABI if plugin else 50
    if suffix == '.ovl' and version == 1:
        if len(image) < 40 or struct.unpack_from('<H', image, 24)[0] != PLUGIN_ABI:
            raise RuntimeError(f'Wrong plugin ABI in image decoder: {name}')
        expected_version = 1
    if magic not in expected_magic or target_id != target.target_id or version != expected_version:
        raise RuntimeError(f'Wrong target or ABI in module: {name}')


def validate_catalog(name, image, target=CLIPPLUS):
    cookie = 0x9a if name.endswith('.vstrings') else 0x1a
    if len(image) < 10 or image[:3] != bytes([cookie, 6, target.target_id]):
        raise RuntimeError(f'Invalid {target.label} language catalog: {name}')
    count = int.from_bytes(image[4:6], 'big')
    offset = int.from_bytes(image[8:10], 'big')
    if not count or not 10 <= offset < len(image):
        raise RuntimeError(f'Invalid catalog offsets: {name}')
    identifiers = {}
    for entry in range(count):
        if offset + 2 >= len(image):
            raise RuntimeError(f'Truncated catalog: {name}, entry {entry}')
        identifier = image[offset:offset + 2]
        end = image.find(b'\0', offset + 2)
        content = image[offset + 2:end]
        if end < 0 or (identifier in identifiers and identifiers[identifier] != content):
            raise RuntimeError(f'Invalid catalog string: {name}')
        content.decode('utf-8')
        identifiers[identifier] = content
        offset = end + 1


def zip_entries(archive):
    entries = {}
    seen = set()
    for info in archive.infolist():
        name = info.filename.rstrip('/') if info.is_dir() else info.filename
        safe_name(name)
        if name.casefold() in seen:
            raise RuntimeError(f'Duplicate archive entry: {name}')
        seen.add(name.casefold())
        mode = stat.S_IFMT(info.external_attr >> 16)
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
            raise RuntimeError(f'Unsupported archive entry: {name}')
        if not info.is_dir():
            entries[name] = info
    return entries


def diagnostic_card_state(relative):
    parts = relative.parts
    if len(parts) < 2 or parts[0].lower() != '.rockbox':
        return False
    entry = parts[1].lower()
    return any(entry == name or entry.startswith(name + '.') for name in DIAGNOSTIC_CARD_STATE_NAMES)


def validate_package_entry(name, content, target=CLIPPLUS):
    relative = safe_name(name)
    if len(relative.parts) < 2 or relative.parts[0] != '.rockbox':
        raise RuntimeError(f'Unexpected package root: {name}')
    lower = relative.name.lower()
    if (diagnostic_card_state(relative) or lower in STATE_NAMES or lower.startswith(('accessibility.cfg.', 'accessibility-typing.cfg.', 'accessibility-screen.cfg.',
                                                'accessibility-shortcut.cfg.', 'connectivity.cfg.',
                                                'accessibility-typing-echo.cfg.', 'accessibility-lock.cfg.', 'touch-sensitivity.cfg.',
                                                'empty-feedback.cfg.', 'tts-reader.cfg.', 'bluetooth.cfg.')) or
            lower.endswith(('.bmark', '.bookmark')) or '.bmark.' in lower or
            '.bookmark.' in lower or
            lower.endswith(('.voice', '.talk', '.gc')) or
            'bootloader' in lower or (relative.suffix.lower() in IMAGE_SUFFIXES and name != FIRMWARE)):
        raise RuntimeError(f'Bootloader, other image or saved runtime state: {name}')
    if relative.suffix.lower() in {'.rock', '.ovl', '.codec'}:
        validate_module(name, content, target)
    if relative.suffix.lower() in {'.lng', '.vstrings'}:
        validate_catalog(name, content, target)


def verify_firmware_zip(path, expected_data=None, expected_catalogs=None, payload=None, target=CLIPPLUS):
    with zipfile.ZipFile(path) as archive:
        entries = zip_entries(archive)
        if target.manifest not in entries:
            raise RuntimeError('Missing firmware manifest')
        manifest = json.loads(archive.read(target.manifest))
        files = manifest['files']
        if set(entries) != set(files) | {target.manifest}:
            raise RuntimeError('Unmanifested or missing package files')
        for name, digest in files.items():
            content = archive.read(name)
            if sha256(content) != digest:
                raise RuntimeError(f'Package hash mismatch: {name}')
            validate_package_entry(name, content, target)
        if (manifest['target'] != target.name or manifest['plugin_abi'] != PLUGIN_ABI or
                manifest['engine_revision'] not in (ENGINE_REVISION, LEGACY_ENGINE_REVISION) or
                manifest['hardware_tested'] is not False):
            raise RuntimeError(f'Invalid experimental {target.label} manifest identity')
        required = {FIRMWARE, '.rockbox/config.cfg', '.rockbox/rockbox-info.txt'}
        required.update(target.document_prefix + name for name in (*documents(target), *RUNTIME_NOTICES))
        required.update(CATALOG_PREFIX + language + suffix
                        for language in ('english', 'polski') for suffix in ('.lng', '.vstrings'))
        required.update(DATA_PREFIX + name for name in REQUIRED_DATA)
        if not required <= entries.keys():
            raise RuntimeError(f'Missing runtime assets: {sorted(required - entries.keys())}')
        if archive.read('.rockbox/config.cfg') != DEFAULT_CONFIG:
            raise RuntimeError('Package does not use clean Polish defaults')
        if not any(name.endswith('.rock') for name in entries) or not any(name.endswith('.codec') for name in entries):
            raise RuntimeError('Missing rebuilt plugins or codecs')
        data = {name[len(DATA_PREFIX):]: files[name] for name in files if name.startswith(DATA_PREFIX)}
        catalogs = {name[len(CATALOG_PREFIX):]: files[name] for name in files if name.endswith('.vstrings')}
        if data != manifest['runtime_data'] or (expected_data is not None and data != expected_data):
            raise RuntimeError('eSpeak data differs from the exact supplied runtime')
        if catalogs != manifest['voice_catalogs'] or (expected_catalogs is not None and catalogs != expected_catalogs):
            raise RuntimeError('Missing or stale generated voice catalogs')
        firmware = validate_firmware(archive.read(FIRMWARE), payload, target)
        if firmware != manifest['firmware']:
            raise RuntimeError('Firmware metadata mismatch')
        validate_build_info(archive.read('.rockbox/rockbox-info.txt').decode('utf-8'), manifest['version'], target)
        return manifest


def write_firmware_zip(base_zip, output, additions, metadata, target=CLIPPLUS):
    excluded = []
    excluded_talk = []
    files = {}
    with zipfile.ZipFile(base_zip) as base, zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        entries = zip_entries(base)
        for name in sorted(entries):
            if name.lower().endswith('.voice'):
                excluded.append(name)
                continue
            if name.lower().endswith('.talk'):
                excluded_talk.append(name)
                continue
            if name == '.rockbox/config.cfg' or name == target.manifest or name.startswith(DATA_PREFIX):
                raise RuntimeError(f'Unexpected pre-existing runtime data in fresh make zip: {name}')
            if name in additions:
                if not name.endswith('.vstrings') or base.read(name) != additions[name]:
                    raise RuntimeError(f'Conflicting package addition: {name}')
                continue
            content = base.read(name)
            validate_package_entry(name, content, target)
            archive.writestr(name, content)
            files[name] = sha256(content)
        for name, content in sorted(additions.items()):
            validate_package_entry(name, content, target)
            archive.writestr(name, content)
            files[name] = sha256(content)
        manifest = dict(metadata, files=files, excluded_stock_voice_files=excluded,
                        excluded_stock_talk_files=excluded_talk)
        archive.writestr(target.manifest, json_bytes(manifest))
    return manifest


def write_source_archive(output, files, expected, modes, metadata):
    with tarfile.open(output, 'x:gz') as archive:
        for name, path in sorted(files.items()):
            safe_name(name)
            content = path.read_bytes()
            if sha256(content) != expected[name]:
                raise RuntimeError(f'Source changed after freeze: {name}')
            member = tarfile.TarInfo(name)
            member.mode = modes.get(name, 0o644)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        content = json_bytes(dict(metadata, files=expected))
        member = tarfile.TarInfo('source-manifest.json')
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))


def verify_source_archive(path, expected=None):
    with tarfile.open(path, 'r:gz') as archive:
        actual = {}
        manifest = None
        seen = set()
        for member in archive:
            relative = safe_name(member.name)
            if not member.isfile() or member.name.casefold() in seen:
                raise RuntimeError(f'Unsafe or duplicate source entry: {member.name}')
            seen.add(member.name.casefold())
            content = archive.extractfile(member).read()
            if member.name == 'source-manifest.json':
                manifest = json.loads(content)
            else:
                if (len(relative.parts) < 2 or relative.parts[0] not in {'rockbox', 'espeak-1.44.05-source'} or
                        not source_allowed('/'.join(relative.parts[1:]))):
                    raise RuntimeError(f'Non-source or private archive entry: {member.name}')
                actual[member.name] = sha256(content)
        if not manifest or actual != manifest['files'] or (expected is not None and actual != expected):
            raise RuntimeError('Source archive integrity failure')
        return manifest


def validate_build_info(text, version, target=CLIPPLUS):
    fields = dict(line.split(': ', 1) for line in text.splitlines() if ': ' in line)
    expected = {'Target': target.name, 'Target id': str(target.target_id),
                'CPU': 'arm', 'Binary': 'rockbox.sansa', 'Version': version}
    if any(fields.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f'rockbox-info.txt does not describe this native {target.label} build')


def run(command, build, name, environment):
    print('Running: ' + ' '.join(str(part) for part in command), flush=True)
    with (build / name).open('x', encoding='utf-8') as stream:
        subprocess.run(command, cwd=build, env=environment, stdout=stream,
                       stderr=subprocess.STDOUT, check=True)


def toolchain_versions():
    versions = {}
    for name in ('gcc', 'g++'):
        tool = PREFIX + name
        version = subprocess.check_output([tool, '-dumpfullversion'], text=True).strip()
        machine = subprocess.check_output([tool, '-dumpmachine'], text=True).strip()
        if version.split('.')[0] != '13' or machine != 'arm-none-eabi':
            raise RuntimeError(f'Expected ARM bare-metal GCC 13, got {tool} {machine} {version}')
        versions[tool] = subprocess.check_output([tool, '--version'], text=True).splitlines()[0]
    for name in ('nm', 'readelf', 'objcopy', 'ld'):
        versions[PREFIX + name] = subprocess.check_output([PREFIX + name, '--version'], text=True).splitlines()[0]
    return versions


def runtime_notices():
    for name, path in RUNTIME_NOTICES.items():
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError(f'Missing runtime license notice: {path}; see the native build guide')
    gcc_notice = RUNTIME_NOTICES['GCC13-COPYRIGHT-and-RUNTIME-EXCEPTION.txt'].read_text(encoding='utf-8')
    if 'GCC RUNTIME LIBRARY EXCEPTION' not in gcc_notice or 'Version 3.1' not in gcc_notice:
        raise RuntimeError('GCC packaging notice alone does not supply the runtime exception')
    return RUNTIME_NOTICES


def runtime_libraries():
    libraries = {}
    for name in ('libm.a', 'libgcc.a'):
        path = Path(subprocess.check_output([PREFIX + 'gcc', '-mcpu=arm926ej-s',
                                            '-print-file-name=' + name], text=True).strip())
        if not path.is_absolute() or not path.is_file():
            raise RuntimeError(f'Cannot identify the native runtime archive: {name}')
        libraries[name] = {'path': str(path.resolve()), 'sha256': sha256(path.read_bytes())}
    packages = subprocess.check_output(['dpkg-query', '-W',
        '-f=${binary:Package} ${Version} source=${source:Package} ${source:Version}\n',
        'gcc-arm-none-eabi', 'gcc-13-base', 'libnewlib-dev', 'libnewlib-arm-none-eabi'], text=True)
    return {'libraries': libraries, 'ubuntu_packages': packages.splitlines()}


def freeze_sources(source):
    projects = {'rockbox': ROOT, 'espeak-1.44.05-source': source}
    files = {}
    modes = {}
    for prefix, repository in projects.items():
        selected = source_files(repository)
        if prefix == 'espeak-1.44.05-source':
            selected.update({'espeak-data/' + name: path for name, path in runtime_files(source).items()})
        files.update({prefix + '/' + name: path for name, path in selected.items()})
        modes.update({prefix + '/' + name: mode for name, mode in source_modes(repository).items()})
    for name, path in runtime_notices().items():
        relative = 'rockbox/docs/native-runtime-licenses/' + name
        if relative in files:
            raise RuntimeError(f'Runtime notice would replace a project source: {relative}')
        files[relative] = path
    return files, hashes(files), modes


def validate_native_build(build, version, target=CLIPPLUS):
    validate_build_info((build / 'rockbox-info.txt').read_text(encoding='utf-8'), version, target)
    configuration = (build / 'autoconf.h').read_text(encoding='utf-8')
    if not re.search(r'^#define HAVE_ESPEAK\s+1\s*$', configuration, re.M):
        raise RuntimeError('Integrated eSpeak is not enabled in the native build')
    if re.search(r'^#define (SIMULATOR|BOOTLOADER|APPLICATION)\b', configuration, re.M):
        raise RuntimeError('Not a native normal firmware configuration')
    executable = build / 'rockbox.elf'
    validate_elf(executable.read_bytes())
    symbols = subprocess.check_output([PREFIX + 'nm', '--defined-only', str(executable)], text=True)
    validate_symbols(symbols)
    (build / 'symbols.txt').write_text(symbols, encoding='utf-8')
    attributes = subprocess.check_output([PREFIX + 'readelf', '-h', '-A', str(executable)], text=True)
    (build / 'elf-attributes.txt').write_text(attributes, encoding='utf-8')
    if not re.search(r'Tag_CPU_arch:\s+v5TEJ?\b', attributes):
        raise RuntimeError(f'ELF does not identify the {target.label} ARMv5TE architecture')
    proof = build / 'elf-payload-validation.bin'
    print(f'Creating retained ELF reconstruction for payload validation only: {proof}', flush=True)
    subprocess.run([PREFIX + 'objcopy', '-O', 'binary', str(executable), str(proof)], check=True)
    payload = (build / 'rockbox.bin').read_bytes()
    if proof.read_bytes() != payload:
        raise RuntimeError('rockbox.bin is not the binary payload of the validated ELF')
    firmware = validate_firmware((build / 'rockbox.sansa').read_bytes(), payload, target)
    return payload, {'elf_sha256': sha256(executable.read_bytes()), 'firmware': firmware,
                     'link_map_sha256': sha256((build / 'rockbox.map').read_bytes()),
                     'elf_architecture': 'ELF32 little-endian ARMv5TE/ARMv5TEJ',
                     'defined_speech_symbols': list(REQUIRED_SYMBOLS)}


def verify_release(firmware, source_archive=None, check_sums=True, target=CLIPPLUS):
    manifest = verify_firmware_zip(firmware, target=target)
    source_name = manifest['source_archive']['name']
    if safe_name(source_name).name != source_name:
        raise RuntimeError('Source archive name must not contain directories')
    source_archive = source_archive or firmware.parent / source_name
    if sha256(source_archive.read_bytes()) != manifest['source_archive']['sha256']:
        raise RuntimeError('Corresponding source archive hash mismatch')
    source_manifest = verify_source_archive(source_archive)
    if (source_manifest['version'] != manifest['version'] or
            source_manifest.get('target', CLIPPLUS.name) != target.name or
            sha256(json_bytes(source_manifest['files'])) != manifest['source_inventory_sha256']):
        raise RuntimeError('Source archive is for a different firmware build')
    if check_sums:
        sums = {}
        for line in (firmware.parent / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
            match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
            if not match or match.group(2) in sums or safe_name(match.group(2)).name != match.group(2):
                raise RuntimeError('Invalid release SHA256SUMS')
            sums[match.group(2)] = match.group(1)
        expected = {firmware.name: sha256(firmware.read_bytes()),
                    source_name: sha256(source_archive.read_bytes())}
        if sums != expected:
            raise RuntimeError('Release SHA256SUMS mismatch')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build experimental native Clip+/Clip Zip eSpeak firmware only after source freeze.')
    parser.add_argument('--target', choices=tuple(TARGETS), default=CLIPPLUS.name)
    parser.add_argument('--source-frozen', action='store_true', help='Confirm all agents have stopped editing the frozen sources')
    parser.add_argument('--version', help='Unique experimental release identifier')
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 2, 8))
    parser.add_argument('--espeak-source', type=Path, default=ROOT.parent / 'espeak-1.44.05-source')
    parser.add_argument('--verify', type=Path, help='Read-only verification of a final firmware ZIP and its source archive')
    parser.add_argument('--source-archive', type=Path, help='Corresponding source archive for --verify')
    arguments = parser.parse_args(argv)
    target = TARGETS[arguments.target]
    if arguments.verify:
        verify_release(arguments.verify, arguments.source_archive, target=target)
        print('Firmware/source archive integrity PASS; not a hardware test.')
        return
    if arguments.source_archive:
        parser.error('--source-archive requires --verify')
    if not arguments.source_frozen or not arguments.version:
        parser.error('Do not build before main confirms source freeze; then supply --source-frozen and --version')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', arguments.version) or arguments.jobs < 1:
        parser.error('Use a safe version identifier and a positive job count')
    if sys.platform != 'linux':
        parser.error('Run the build inside Linux/WSL with arm-none-eabi GCC 13, not Windows Python')
    ensure_ignored(ROOT, ['Workspace', 'installfiles', 'snapshots', 'Forme', 'trash'])
    source = arguments.espeak_source.resolve(strict=True)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != ENGINE_REVISION:
        raise RuntimeError(f'Expected supplied eSpeak revision {ENGINE_REVISION}; found {revision}')
    engine_data = runtime_files(source)
    data_hashes = hashes(engine_data)
    toolchain = toolchain_versions()
    runtime = runtime_libraries()
    print('WARNING: GCC 13 overrides Rockbox recommended GCC 9.5.0; hardware behavior is untested.', flush=True)
    files, frozen_hashes, modes = freeze_sources(source)
    build = contained(_project_materials_root(ROOT) / f'build-espeak-{target.slug}')
    release = contained(_project_materials_root(ROOT, 'installfiles') / target.slug)
    preserve(build, f'{target.slug}-native-build')
    build.mkdir(parents=True, exist_ok=False)
    (build / 'source-freeze.json').write_bytes(json_bytes({'version': arguments.version, 'files': frozen_hashes}))
    environment = dict(os.environ, VERSION=arguments.version,
                       OMP_NUM_THREADS=str(arguments.jobs))
    for name in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES'):
        environment.pop(name, None)
    configure = ['bash', str(ROOT / 'tools/configure'), '--target=' + target.name, '--type=n',
                 '--integrated-espeak', '--compiler-prefix=' + PREFIX, '--thumb']
    run(configure, build, 'configure.log', environment)
    run(['make', f'-j{arguments.jobs}', 'zip', f'VERSION={arguments.version}'],
        build, 'build-zip.log', environment)
    payload, validation = validate_native_build(build, arguments.version, target)
    if freeze_sources(source)[1] != frozen_hashes:
        raise RuntimeError('Sources changed during build; do not publish this build')
    catalogs = {path.name: path for path in sorted((build / 'apps/lang').glob('*.vstrings'))}
    if not {'english.vstrings', 'polski.vstrings'} <= catalogs.keys():
        raise RuntimeError('Missing generated Polish/English speech catalogs')
    additions = {DATA_PREFIX + name: path.read_bytes() for name, path in engine_data.items()}
    additions.update({CATALOG_PREFIX + name: path.read_bytes() for name, path in catalogs.items()})
    additions.update({target.document_prefix + name: (ROOT / relative).read_bytes()
                      for name, relative in documents(target).items()})
    additions.update({target.document_prefix + name: path.read_bytes()
                      for name, path in runtime_notices().items()})
    additions['.rockbox/config.cfg'] = DEFAULT_CONFIG
    staging = contained(build / 'release-staging')
    staging.mkdir(exist_ok=False)
    source_archive = staging / f'rockbox-{target.slug}-espeak-{arguments.version}-source.tar.gz'
    metadata = {
        'version': arguments.version, 'target': target.name, 'plugin_abi': PLUGIN_ABI,
        'engine_revision': revision, 'toolchain': toolchain, 'hardware_tested': False,
        'system_runtime': runtime, 'runtime_notice_hashes': hashes(runtime_notices()),
        'rockbox_revision': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'source_inventory_sha256': sha256(json_bytes(frozen_hashes)),
        'kind': f'Experimental native {target.label} firmware; not a bootloader or simulator',
        'warning': 'GCC 13 instead of recommended 9.5.0. Untested on hardware; not certified stable.',
        'configure_arguments': configure[2:], 'runtime_data': data_hashes,
        'voice_catalogs': hashes(catalogs), **validation,
    }
    print(f'Creating corresponding-source delivery copy: {source_archive}; retained beside firmware, not on device.', flush=True)
    write_source_archive(source_archive, files, frozen_hashes, modes, metadata)
    verify_source_archive(source_archive, frozen_hashes)
    metadata['source_archive'] = {'name': source_archive.name, 'sha256': sha256(source_archive.read_bytes())}
    firmware = staging / f'rockbox-{target.slug}-espeak-{arguments.version}.zip'
    print('Adding exact runtime copies of supplied eSpeak data and build catalogs to the firmware ZIP.', flush=True)
    write_firmware_zip(build / 'rockbox.zip', firmware, additions, metadata, target)
    verify_firmware_zip(firmware, data_hashes, hashes(catalogs), payload, target)
    verify_release(firmware, source_archive, check_sums=False, target=target)
    if freeze_sources(source)[1] != frozen_hashes:
        raise RuntimeError('Sources changed while packaging; release was not installed')
    if runtime_libraries() != runtime:
        raise RuntimeError('Native toolchain runtime changed during build; release was not installed')
    checksums = {path.name: sha256(path.read_bytes()) for path in (firmware, source_archive)}
    (staging / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in checksums.items()), encoding='utf-8')
    (build / 'validation.json').write_bytes(json_bytes(dict(metadata, archives=checksums,
        checks=['ARM ELF and speech symbols', f'ELF/bin/{target.label} image payload',
                'all plugin/overlay ABI and codec headers', 'ZIP/source hashes and exact assets'],
        limitations=['No player, playback, recording, battery, USB or screen-reader hardware test'])))
    ensure_publication_filesystem(staging, release)
    preserve(release, f'{target.slug}-native-release')
    assert_unused(staging)
    release.parent.mkdir(parents=True, exist_ok=True)
    if release.exists():
        raise RuntimeError('Release destination appeared during packaging; refusing to overwrite')
    staging.rename(release)
    verify_release(release / firmware.name, target=target)
    for name, digest in checksums.items():
        if sha256((release / name).read_bytes()) != digest:
            raise RuntimeError(f'Published archive changed: {name}')
    print(f'Native firmware and corresponding source: {release}\nNo bootloader installed. No hardware test performed.', flush=True)


if __name__ == '__main__':
    main()
