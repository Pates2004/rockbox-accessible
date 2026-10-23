import argparse
import ctypes
from ctypes import wintypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import time

from test_tts_simulator import find_window, send_key, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root, confined_path
from build_espeak_clipplus import diagnostic_card_state



ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    'sansaclipplus': {'target_id': 66, 'label': 'Clip+', 'release': 'simwindows'},
    'sansaclipzip': {'target_id': 68, 'label': 'Clip Zip', 'release': 'simwindows-clipzip'},
    'hibyr1': {'target_id': 124, 'label': 'HiBy R1', 'release': 'simwindows-hibyr1'},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(directory):
    return {path.relative_to(directory).as_posix(): digest(path)
            for path in directory.rglob('*') if path.is_file()}


def validate_clean_profile(directory, manifest):
    files = inventory(directory)
    if set(files) != set(manifest['files']) | {'manifest.json'}:
        raise AssertionError('Package contains unmanifested files or is incomplete')
    disk = directory / 'simdisk'
    if {path.name for path in disk.iterdir()} != {'.rockbox'}:
        raise AssertionError('Package contains user files or a test disk marker')
    runtime_names = {'simulator.log', '.resume.cfg', '.resume.cfg.new', 'config.cfg.new',
                     'nvram.bin', 'playername.txt', '.tts-test-profile'}
    for path in directory.rglob('*'):
        name = path.name.lower()
        card_relative = path.relative_to(disk) if path.is_relative_to(disk) else None
        if ((card_relative is not None and diagnostic_card_state(card_relative)) or
                name in runtime_names or name in ('accessibility.cfg', 'accessibility-typing.cfg', 'accessibility-screen.cfg',
                                             'accessibility-shortcut.cfg', 'connectivity.cfg', 'accessibility-typing-echo.cfg',
                                             'accessibility-lock.cfg', 'touch-sensitivity.cfg', 'empty-feedback.cfg',
                                             'tts-reader.cfg', 'bluetooth.cfg') or
                name.startswith(('accessibility.cfg.', 'accessibility-typing.cfg.', 'accessibility-screen.cfg.',
                                 'accessibility-shortcut.cfg.', 'connectivity.cfg.', 'accessibility-typing-echo.cfg.',
                                 'accessibility-lock.cfg.', 'touch-sensitivity.cfg.', 'empty-feedback.cfg.',
                                 'tts-reader.cfg.', 'bluetooth.cfg.')) or path.suffix.lower() == '.gc' or
                name.endswith(('.bmark', '.bookmark')) or
                '.bmark.' in name or '.bookmark.' in name):
            raise AssertionError(f'Package contains saved runtime state: {path.name}')
    expected = {
        'lang': '/.rockbox/langs/polski.lng',
        'talk menu': 'on', 'talk dir': 'spell', 'talk file': 'spell',
        'talk dir clip': 'off', 'talk file clip': 'off',
        'tts enabled': 'on', 'tts language': 'system', 'tts variant': '',
        'tts rate': '175', 'tts rate scale': 'percent', 'tts punctuation': 'none',
        'tts ducking': 'on', 'tts ducking level': '25', 'tts pitch': '50',
        'tts volume': '100', 'tts range': '50', 'tts wordgap': '0', 'volume': '-25',
    }
    settings = {}
    for line in (disk / '.rockbox/config.cfg').read_text(encoding='utf-8').splitlines():
        key, separator, value = line.partition(':')
        key = key.strip()
        if not separator or key in settings:
            raise AssertionError('Invalid or duplicate setting in clean profile')
        settings[key] = value.strip()
    if settings != expected:
        raise AssertionError(f'Package does not contain clean default settings: {settings}')
    return settings


def module_header_offset(image):
    pe = struct.unpack_from('<I', image, 0x3c)[0]
    optional = pe + 24
    if struct.unpack_from('<H', image, optional)[0] != 0x20b:
        raise AssertionError('Expected a PE32+ module')
    section_count = struct.unpack_from('<H', image, pe + 6)[0]
    section_table = optional + struct.unpack_from('<H', image, pe + 20)[0]

    def file_offset(rva):
        for index in range(section_count):
            section = section_table + index * 40
            address, size, position = struct.unpack_from('<III', image, section + 12)
            if address <= rva < address + size:
                return position + rva - address
        raise AssertionError(f'Export RVA outside module sections: {rva}')

    exports = file_offset(struct.unpack_from('<I', image, optional + 112)[0])
    count, functions, names, ordinals = struct.unpack_from('<IIII', image, exports + 24)
    for index in range(count):
        name = file_offset(struct.unpack_from('<I', image, file_offset(names) + index * 4)[0])
        if image[name:image.index(b'\0', name)] != b'__header':
            continue
        ordinal = struct.unpack_from('<H', image, file_offset(ordinals) + index * 2)[0]
        header = file_offset(struct.unpack_from('<I', image, file_offset(functions) + ordinal * 4)[0])
        return header
    raise AssertionError('Rockbox module header export is missing')


def module_header(image):
    return struct.unpack_from('<IHH', image, module_header_offset(image))


def validate_manifest_target(manifest, target):
    if 'target' in manifest and manifest['target'] != target:
        raise AssertionError(f'Package target mismatch: expected {target}, found {manifest["target"]}')


def validate_module_identity(header, module, target):
    magic, target_id, version = header
    expected_api = {'.codec': 50, '.ovl': 1, '.rock': 0xe006}[module.suffix]
    expected_magic = (0x52434f44, 0x52454e43) if module.suffix == '.codec' else (0x526f634b,)
    if target_id != TARGETS[target]['target_id'] or version != expected_api or magic not in expected_magic:
        raise AssertionError(f'Wrong target or ABI in {module}: {target_id}, {version:#x}, {magic:#x}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', type=Path)
    parser.add_argument('--target', choices=tuple(TARGETS), default='sansaclipplus')
    arguments = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This test must run on native Windows, not WSL or Wine')
    target = TARGETS[arguments.target]
    release = confined_path(arguments.release or _project_materials_root(ROOT, 'installfiles') / target['release'],
                            _project_materials_root(ROOT, 'installfiles')).resolve(strict=True)
    if release.parent != _project_materials_root(ROOT, 'installfiles'):
        raise RuntimeError('Expected a package directly inside installfiles')
    native = windows_backend()
    native.ensure_unused(release / 'rockboxui.exe')
    relocated = release.with_name(f'Symulator próbny {target["label"]}')
    if relocated.exists():
        raise RuntimeError('Unicode relocation destination already exists')
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    results = confined_path(_project_materials_root(ROOT) / 'windows-package-tests' / timestamp,
                            _project_materials_root(ROOT))
    results.mkdir(parents=True)
    report = {'passed': False, 'platform': platform.platform(), 'target': arguments.target,
              'checks': [], 'runs': []}
    original = inventory(release)
    current = release
    print(f'Native package evidence: {results}', flush=True)

    def validate_manifest(directory):
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        validate_manifest_target(manifest, arguments.target)
        for relative, expected in manifest['files'].items():
            path = confined_path(directory / relative, directory)
            if directory not in path.parents or digest(path) != expected:
                raise AssertionError(f'Package integrity failure: {relative}')
        return manifest

    def smoke(directory, label, real_audio):
        executable = directory / 'rockboxui.exe'
        native.ensure_unused(executable)
        before = inventory(directory)
        environment = dict(os.environ, SDL_VIDEODRIVER='windows')
        environment.pop('SDL_AUDIODRIVER', None)
        environment.pop('SDL_DISKAUDIOFILE', None)
        if not real_audio:
            environment['SDL_AUDIODRIVER'] = 'disk'
            environment['SDL_DISKAUDIOFILE'] = str(results / f'{label}-audio.raw')
        run = {'label': label, 'directory': str(directory), 'real_audio': real_audio}
        report['runs'].append(run)
        command = [str(executable)]
        if not real_audio:
            command.extend(['--audiodev', environment['SDL_DISKAUDIOFILE']])
        process = subprocess.Popen(command, cwd=results, env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        log = directory / 'simulator.log'
        try:
            window = find_window(process.pid, environment)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
                if 'TTS parameters: language=pl variant= rate=175' in text:
                    break
                if process.poll() is not None:
                    raise AssertionError(f'Early package exit: {process.returncode}')
                time.sleep(0.1)
            else:
                raise AssertionError('No default Polish TTS startup in packaged executable')
            native.set_hidden(process.pid, window, True)
            time.sleep(1)
            for key in ('Down', 'Up'):
                send_key(process.pid, window, key, True, environment)
                time.sleep(0.15)
                send_key(process.pid, window, key, False, environment)
                time.sleep(0.8)
            shutdown(process, window, environment)
            text = log.read_text(encoding='utf-8', errors='replace')
            parameters = ('TTS parameters: language=pl variant= rate=175 pitch=50 '
                          'volume=100 range=50 wordgap=0 punctuation=0')
            if parameters not in text:
                raise AssertionError('Clean default parameters did not reach the synthesizer')
            drivers = re.findall(r'^\s*(\w+) \(active\)', text, re.MULTILINE)
            run['audio_drivers'] = drivers
            if real_audio and not any(driver in ('wasapi', 'directsound', 'winmm') for driver in drivers):
                raise AssertionError(f'No active native Windows output: {drivers}')
            if 'Unable to open audio' in text or 'TTS error' in text:
                raise AssertionError('Packaged simulator reports an audio/TTS error')
            if 'TTS: Biblioteka' not in text or len(re.findall(r'^TTS:', text, re.MULTILINE)) < 4:
                raise AssertionError('Missing actual package menu-navigation speech')
            run['exit_code'] = process.returncode
            run['passed'] = True
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            native.ensure_unused(executable)
            after = inventory(directory)
            modified = [path for path, expected in before.items() if after.get(path) != expected]
            run['modified_package_files'] = modified
            created = sorted(set(after) - set(before))
            run['created_runtime_files'] = created
            for relative in created:
                source = (directory / relative).resolve(strict=True)
                destination = (results / label / relative).resolve()
                if directory not in source.parents or results not in destination.parents or destination.exists():
                    raise RuntimeError('Unsafe runtime evidence move')
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.rename(destination)
                if digest(destination) != after[relative]:
                    raise AssertionError('Runtime evidence integrity failure')
            if modified:
                raise AssertionError(f'Smoke test modified installed package assets: {modified}')

    def locked_log_error(directory):
        executable = directory / 'rockboxui.exe'
        native.ensure_unused(executable)
        log = directory / 'simulator.log'
        if log.exists():
            raise RuntimeError('Refusing to lock a pre-existing user log')
        create_file = native.kernel32.CreateFileW
        create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create_file.restype = wintypes.HANDLE
        lock = create_file(str(log), 0xc0000000, 0, None, 1, 0x80, None)
        if lock == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        process = None
        try:
            process = subprocess.Popen([str(executable)], cwd=results,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            dialog = None
            for attempt in range(100):
                windows = []

                @native.window_callback
                def inspect_window(window, parameter):
                    if native.owns_window(process.pid, window):
                        class_name = ctypes.create_unicode_buffer(256)
                        native.user32.GetClassNameW(window, class_name, len(class_name))
                        if class_name.value == '#32770':
                            windows.append(window)
                    return True

                native.user32.EnumWindows(inspect_window, 0)
                if windows:
                    dialog = windows[0]
                    break
                if process.poll() is not None:
                    raise AssertionError('No native error dialog for locked local log')
                time.sleep(0.1)
            if not dialog:
                raise AssertionError('Timed out waiting for local-write failure dialog')
            get_text = native.user32.GetWindowTextW
            get_text.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            get_text.restype = ctypes.c_int
            enum_children = native.user32.EnumChildWindows
            enum_children.argtypes = [wintypes.HWND, native.window_callback, wintypes.LPARAM]
            enum_children.restype = wintypes.BOOL
            texts = []

            @native.window_callback
            def inspect_child(window, parameter):
                text = ctypes.create_unicode_buffer(4096)
                get_text(window, text, len(text))
                texts.append(text.value)
                return True

            enum_children(dialog, inspect_child, 0)
            text = '\n'.join(texts)
            if 'Nie mo' not in text or 'Cannot open simulator.log' not in text or 'No profile' not in text:
                raise AssertionError('Incomplete bilingual/no-fallback startup error')
            (results / 'locked-log-dialog.txt').write_text(text, encoding='utf-8')
            if not native.owns_window(process.pid, dialog):
                raise RuntimeError('Error dialog no longer belongs to the test')
            if not native.user32.PostMessageW(dialog, 0x0010, 0, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            process.wait(timeout=10)
            if process.returncode != 1:
                raise AssertionError(f'Unexpected startup failure status: {process.returncode}')
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            native.kernel32.CloseHandle(lock)
            native.ensure_unused(executable)
            destination = results / 'locked-log-fixture.log'
            if destination.exists() or log.resolve().parent != directory:
                raise RuntimeError('Unsafe log fixture move')
            expected = digest(log)
            log.rename(destination)
            if digest(destination) != expected:
                raise AssertionError('Log fixture integrity failure')

    try:
        manifest = validate_manifest(release)
        report['default_settings'] = validate_clean_profile(release, manifest)
        report['checks'].append('clean default profile without user files, resume state or test markers')
        if manifest.get('sonic_revision') != 'fbf75c3d6d846bad3bb3d456cbc5d07d9fd8c104':
            raise AssertionError('Missing exact Sonic source provenance')
        if digest(release / 'Sonic-LICENSE.txt') != digest(ROOT / 'lib/espeak/sonic/LICENSE'):
            raise AssertionError('Sonic license was not preserved')
        if digest(release / 'Sonic-PROVENANCE.md') != digest(ROOT / 'lib/espeak/sonic/README.md'):
            raise AssertionError('Sonic provenance was not preserved')
        report['checks'].append('exact bundled Sonic license and provenance')
        if manifest.get('plugin_abi') != 0xe006:
            raise AssertionError('Package metadata does not identify the integrated plugin ABI')
        report['manifest_files'] = len(manifest['files'])
        report['checks'].append('all initial package SHA-256 hashes match')
        image = (release / 'rockboxui.exe').read_bytes()
        offset = struct.unpack_from('<I', image, 0x3c)[0]
        if image[:2] != b'MZ' or image[offset:offset + 4] != b'PE\0\0':
            raise AssertionError('Not a Windows PE executable')
        if struct.unpack_from('<H', image, offset + 4)[0] != 0x8664:
            raise AssertionError('Not a native x64 executable')
        if struct.unpack_from('<H', image, offset + 24 + 68)[0] != 2:
            raise AssertionError('The executable unexpectedly uses the console subsystem')
        report['checks'].append('native x64 GUI executable, not a console or WSL launcher')
        modules = [path for path in release.rglob('*') if path.suffix in ('.codec', '.rock', '.ovl')]
        if not modules:
            raise AssertionError('No installed codecs/plugins')
        for module in modules:
            contents = module.read_bytes()
            header = struct.unpack_from('<I', contents, 0x3c)[0]
            if (contents[:2] != b'MZ' or contents[header:header + 4] != b'PE\0\0' or
                    struct.unpack_from('<H', contents, header + 4)[0] != 0x8664):
                raise AssertionError(f'Wrong module architecture: {module}')
            validate_module_identity(module_header(contents), module, arguments.target)
            if module.suffix == '.ovl':
                plugin_api = struct.unpack_from('<H', contents, module_header_offset(contents) + 40)[0]
                if plugin_api != 0xe006:
                    raise AssertionError(f'Wrong embedded plugin ABI in image decoder: {module}')
        report['native_modules'] = len(modules)
        report['checks'].append('all installed codecs and plugins are native x64 modules')
        report['checks'].append(f'all module exports have {target["label"]} target and matching codec/eSpeak plugin ABI')
        source = ROOT.parent / 'espeak-1.44.05-source/espeak-data'
        data = release / 'simdisk/.rockbox/espeak-data'
        if inventory(source) != inventory(data):
            raise AssertionError('eSpeak data differs from supplied checkout')
        report['checks'].append('all supplied engine data preserved exactly')
        smoke(release, 'normal-wasapi', True)
        report['checks'].append('native audio startup, keyboard speech and clean shutdown from foreign CWD')
        native.ensure_unused(release / 'rockboxui.exe')
        if inventory(release) != original:
            raise AssertionError('Unexpected files before package relocation')
        if relocated.parent.resolve() != release.parent or relocated.exists():
            raise RuntimeError('Unsafe package relocation')
        release.rename(relocated)
        current = relocated
        if inventory(current) != original:
            raise AssertionError('Package relocation changed file contents')
        smoke(current, 'unicode-path', False)
        report['checks'].append('program directory with Polish characters/spaces, without executable copies')
        native.ensure_unused(current / 'rockboxui.exe')
        if release.exists() or current.parent.resolve() != release.parent:
            raise RuntimeError('Unsafe package restoration')
        current.rename(release)
        current = release
        locked_log_error(release)
        report['checks'].append('locked local log produces bilingual native error and exits, without fallback')
        validate_manifest(release)
        validate_clean_profile(release, manifest)
        if inventory(release) != original:
            raise AssertionError('The clean release changed after both smoke tests')
        report['checks'].append('clean release restored; runtime evidence moved into Workspace with hashes')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if current == relocated and relocated.exists() and not release.exists():
            native.ensure_unused(relocated / 'rockboxui.exe')
            relocated.rename(release)
        (results / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
