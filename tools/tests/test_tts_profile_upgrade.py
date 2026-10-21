import argparse
import array
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from test_tts_simulator import find_window, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-language', default='pl')
    arguments = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('Run the upgraded-profile smoke test on native Windows')
    release = _project_materials_root(ROOT, 'installfiles') / 'simwindows'
    executable = release / 'rockboxui.exe'
    native = windows_backend()
    native.ensure_unused(executable)
    config = release / 'simdisk/.rockbox/config.cfg'
    original = config.read_bytes()
    parsed = dict(re.findall(r'^([^#\n:]+):[ \t]*(.*)$', original.decode('utf-8'), re.MULTILINE))
    expected_rate = int(parsed.get('tts rate', 175))
    expected_variant = parsed.get('tts variant', '').strip()
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    evidence = _project_materials_root(ROOT) / 'profile-upgrade-tests' / timestamp
    evidence.mkdir(parents=True)
    capture = evidence / 'startup.raw'
    log = release / 'simulator.log'
    if log.exists():
        raise RuntimeError('Refusing to overwrite an existing user log')
    report = {'passed': False, 'expected_rate': expected_rate,
              'expected_language': arguments.expected_language,
              'expected_variant': expected_variant,
              'profile_sha256': hashlib.sha256(original).hexdigest(),
              'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}
    environment = dict(os.environ, SDL_VIDEODRIVER='windows', SDL_AUDIODRIVER='disk',
                       SDL_DISKAUDIODELAY='12', SDL_DISKAUDIOFILE=str(capture))
    process = subprocess.Popen([str(executable), '--audiodev', str(capture)], cwd=evidence,
                               env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    window = None
    try:
        window = find_window(process.pid, environment)
        native.set_hidden(process.pid, window, True)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
            expected = (rf'^TTS parameters: language={re.escape(arguments.expected_language)} '
                        rf'variant={re.escape(expected_variant)} rate={expected_rate}\b')
            if re.search(expected, text, re.MULTILINE):
                break
            if process.poll() is not None:
                raise AssertionError(f'Upgraded simulator exited: {process.returncode}')
            time.sleep(0.1)
        else:
            raise AssertionError('Restored settings did not reach actual synthesis')
        time.sleep(1)
        shutdown(process, window, environment)
        pending = config.with_name('config.cfg.new')
        persisted = (pending if pending.exists() else config).read_text(encoding='utf-8')
        saved = re.search(r'^tts rate:\s*(\d+)', persisted, re.MULTILINE)
        saved_rate = int(saved.group(1)) if saved else 175
        if saved_rate != expected_rate:
            raise AssertionError('Graceful shutdown lost the restored speech rate')
        if config.read_bytes() != original:
            raise AssertionError('The startup smoke test rewrote the restored base profile')
        samples = array.array('h', capture.read_bytes())
        report['nonzero_samples'] = sum(sample != 0 for sample in samples)
        if report['nonzero_samples'] < 100:
            raise AssertionError('No synthesized audio from the upgraded profile')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if log.exists():
            log.rename(evidence / 'simulator.log')
        (evidence / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'Upgraded-profile evidence: {evidence}', flush=True)


if __name__ == '__main__':
    main()
