import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root, confined_path



ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def processes_using(executable):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / 'exe').resolve(strict=True) == executable:
                found.append(int(entry.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return found


def completed_calls(trace):
    pending = {}
    for line in trace.splitlines():
        parsed = re.match(r'(\d+)\s+(.*)', line)
        if not parsed:
            continue
        identifier, call = parsed.groups()
        if call.endswith('<unfinished ...>'):
            pending[identifier] = call.removesuffix('<unfinished ...>')
        elif call.startswith('<... '):
            resumed = re.match(r'<\.\.\. \w+ resumed>(.*)', call)
            if resumed and identifier in pending:
                yield pending.pop(identifier) + resumed.group(1)
        else:
            yield call


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', type=Path,
                        default=_project_materials_root(ROOT, 'installfiles') / 'clipplus-espeak-simulator')
    arguments = parser.parse_args()
    release = confined_path(arguments.release, _project_materials_root(ROOT, 'installfiles'))
    if _project_materials_root(ROOT, 'installfiles') not in release.parents:
        raise RuntimeError('Package validation requires a release inside installfiles')
    executable = release / 'rockboxui'
    if processes_using(executable):
        raise RuntimeError('The packaged simulator is already running')
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    results = _project_materials_root(ROOT) / 'package-validation' / timestamp
    results.mkdir(parents=True)
    report = {'release': str(release), 'passed': False, 'checks': []}
    print(f'Package validation evidence: {results}', flush=True)
    process = None
    original = {str(path.relative_to(release)): digest(path)
                for path in release.rglob('*') if path.is_file()}
    try:
        manifest = json.loads((release / 'manifest.json').read_text())
        for relative, expected in manifest['files'].items():
            path = (release / relative).resolve()
            if release not in path.parents or digest(path) != expected:
                raise AssertionError(f'Package integrity failure: {relative}')
        report['manifest_files'] = len(manifest['files'])
        report['checks'].append('all initial manifest SHA-256 hashes match')
        source = ROOT.parent / 'espeak-1.44.05-source/espeak-data'
        expected = {str(path.relative_to(source)): digest(path)
                    for path in source.rglob('*') if path.is_file()}
        destination = release / 'simdisk/.rockbox/espeak-data'
        actual = {str(path.relative_to(destination)): digest(path)
                  for path in destination.rglob('*') if path.is_file()}
        if expected != actual:
            raise AssertionError('Packaged eSpeak data differs from supplied source')
        report['engine_data_files'] = len(actual)
        report['polish_dictionary_sha256'] = actual['pl_dict']
        report['checks'].append('complete engine data exactly matches supplied checkout')
        libraries = subprocess.check_output(['ldd', str(executable)], text=True)
        (results / 'linked-libraries.txt').write_text(libraries)
        if 'libespeak' in libraries or 'not found' in libraries:
            raise AssertionError('Unexpected engine library or unresolved dynamic dependency')
        symbols = subprocess.check_output(['nm', str(executable)], text=True)
        if ' rb_espeak_synth\n' not in symbols or ' tts_speak\n' not in symbols:
            raise AssertionError('Integrated TTS symbols missing')
        report['checks'].append('built-in TTS and resolved host libraries without libespeak')
        environment = dict(os.environ, SDL_VIDEODRIVER='x11', SDL_AUDIODRIVER='pulseaudio')
        trace = results / 'syscalls.log'
        with (results / 'launcher.log').open('w') as output:
            process = subprocess.Popen(['strace', '-f', '-yy', '-s', '512', '-o', str(trace),
                '-e', 'trace=%file,write,writev,connect', 'bash', str(release / 'launch.sh')],
                cwd=results, env=environment, stdout=output, stderr=subprocess.STDOUT)
            window = None
            for attempt in range(200):
                if process.poll() is not None:
                    raise RuntimeError(f'Packaged simulator exited early: {process.returncode}')
                for identifier in processes_using(executable):
                    result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(identifier)],
                        capture_output=True, text=True, env=environment)
                    if result.returncode == 0:
                        window = result.stdout.splitlines()[0]
                        break
                if window:
                    break
                time.sleep(0.1)
            if not window:
                raise AssertionError('No packaged simulator window')
            log = release / 'simulator.log'
            for attempt in range(150):
                text = log.read_text(encoding='utf-8', errors='replace')
                if 'TTS parameters: language=pl variant= rate=175' in text:
                    break
                if process.poll() is not None:
                    raise RuntimeError('Packaged simulator exited before startup speech')
                time.sleep(0.1)
            else:
                raise AssertionError('Clean Polish TTS profile was not used')
            time.sleep(3)
            subprocess.run(['xdotool', 'keydown', '--window', window, 'Escape'],
                           check=True, env=environment)
            time.sleep(3)
            subprocess.run(['xdotool', 'keyup', 'Escape'], check=True, env=environment)
            process.wait(timeout=20)
            if process.returncode != 0:
                raise AssertionError(f'Packaged simulator shutdown status: {process.returncode}')
        text = log.read_text(encoding='utf-8', errors='replace')
        if re.search(r'TTS (?:error|failed)|Unable to open audio|SDL.*error', text, re.IGNORECASE):
            raise AssertionError('Runtime error in packaged simulator log')
        trace_text = trace.read_text(encoding='utf-8', errors='replace')
        if not any('connect(' in line and '/mnt/wslg/PulseServer' in line and '= 0' in line
                   for line in trace_text.splitlines()):
            raise AssertionError('No successful connection to WSLg PulseAudio')
        report['checks'].append('launcher works from unrelated directory with clean Polish defaults')
        report['checks'].append('WSLg PulseAudio connection and graceful keyboard shutdown')
        writable = set()
        for line in completed_calls(trace_text):
            if 'open' in line and ('O_WRONLY' in line or 'O_RDWR' in line):
                match = re.search(r'= \d+<([^>]+)>', line)
                if match:
                    writable.add(match.group(1).split('<', 1)[0])
        report['successful_writable_opens'] = sorted(writable)
        unexpected = [path for path in writable if not (
            Path(path).is_relative_to(release) or Path(path).is_relative_to(results) or
            path in ('/dev/null', '/dev/tty') or path.startswith('/memfd:') or
            path.startswith('/dev/shm/pulse-shm-'))]
        if unexpected:
            raise AssertionError(f'Writable paths need review: {unexpected}')
        report['checks'].append('observed application writable files stay alongside program')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if process is not None and process.poll() is None:
            for identifier in processes_using(executable):
                os.kill(identifier, 15)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        after = {str(path.relative_to(release)): digest(path)
                 for path in release.rglob('*') if path.is_file()}
        report['runtime_created_files'] = sorted(set(after) - set(original))
        report['runtime_modified_files'] = sorted(path for path in original if original[path] != after.get(path))
        (results / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
