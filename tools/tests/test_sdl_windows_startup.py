import array
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from test_tts_simulator import find_window, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]


def prepare_profile(source, disk):
    if not (source / '.tts-test-profile').is_file():
        raise RuntimeError('Refusing to use a non-test profile')
    profile = disk / '.rockbox'
    profile.mkdir(parents=True)
    shutil.copytree(source / '.rockbox/espeak-data', profile / 'espeak-data')
    (profile / 'langs').mkdir()
    for name in ('polski.lng', 'polski.vstrings'):
        shutil.copy2(source / '.rockbox/langs' / name, profile / 'langs' / name)
    (disk / '.tts-test-profile').write_text(
        'Synthetic startup test profile. Not user data.\n', encoding='utf-8')
    (profile / 'config.cfg').write_text(
        'lang: /.rockbox/langs/polski.lng\ntalk menu: on\ntalk dir: spell\n'
        'talk file: spell\ntalk file clip: off\ntalk dir clip: off\n'
        'tts enabled: on\ntts language: system\ntts variant: \n'
        'tts rate: 175\ntts pitch: 50\ntts volume: 100\ntts range: 50\n'
        'tts wordgap: 0\ntts punctuation: none\ntts ducking: off\n'
        'volume: -25\n', encoding='utf-8')


def main():
    if sys.platform != 'win32':
        raise RuntimeError('Run on native Windows')
    build = _project_materials_root(ROOT) / 'build-espeak-windows'
    executable = build / 'rockboxui.exe'
    native = windows_backend()
    native.ensure_unused(executable)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    results = _project_materials_root(ROOT) / 'sdl-startup-windows' / timestamp
    results.mkdir(parents=True)
    disk = results / 'simdisk'
    log = build / 'simulator.log'
    if log.exists():
        log.rename(results / 'previous-simulator.log')
    report = {'passed': False, 'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
              'test_profile': str(disk), 'runs': []}
    try:
        prepare_profile(build / 'simdisk', disk)
        for iteration in range(3):
            for hidden in (False, True):
                label = f'{iteration + 1}-{"hidden" if hidden else "normal"}'
                capture = results / f'{label}.raw'
                environment = dict(os.environ, SDL_VIDEODRIVER='windows', SDL_AUDIODRIVER='disk',
                                   SDL_DISKAUDIOFILE=str(capture), SDL_DISKAUDIODELAY='12')
                startup = subprocess.STARTUPINFO()
                if hidden:
                    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startup.wShowWindow = 0
                process = subprocess.Popen([str(executable), '--root', str(disk), '--audiodev', str(capture)],
                                           cwd=results, env=environment, startupinfo=startup,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                run = {'label': label, 'passed': False}
                report['runs'].append(run)
                try:
                    window = find_window(process.pid, environment)
                    deadline = time.monotonic() + 20
                    while True:
                        if process.poll() is not None:
                            raise AssertionError(f'Startup exited with {process.returncode}')
                        text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
                        if ('TTS utterance:' in text and 'TTS parameters:' in text and
                                capture.exists() and capture.stat().st_size >= 65536):
                            break
                        if time.monotonic() >= deadline:
                            raise AssertionError('No startup synthesis/output')
                        time.sleep(0.1)
                    run['tts_parameters'] = next(
                        line for line in text.splitlines() if line.startswith('TTS parameters:'))
                    if 'volume=100' not in run['tts_parameters'].split():
                        raise AssertionError(f"Unexpected startup voice settings: {run['tts_parameters']}")
                    native.set_hidden(process.pid, window, True)
                    time.sleep(1.5)
                    run['startup_bytes'] = capture.stat().st_size
                    shutdown(process, window, environment)
                    if process.returncode != 0:
                        raise AssertionError(f'Shutdown exited with {process.returncode}')
                    samples = array.array('h', capture.read_bytes()[:run['startup_bytes']])
                    run['nonzero_samples'] = sum(sample != 0 for sample in samples)
                    if not run['nonzero_samples']:
                        raise AssertionError('Startup output contains only silence')
                    run['passed'] = True
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                    run['exit_code'] = process.returncode
                    if log.exists():
                        log.rename(results / f'{label}.log')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (results / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'Native startup evidence: {results}', flush=True)


if __name__ == '__main__':
    main()
