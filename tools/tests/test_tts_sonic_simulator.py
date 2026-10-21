"""Verify extended-rate speech through the native Windows mixer and reader."""

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

from test_tts_simulator import catalog_labels, find_window, send_key, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]


def main():
    if sys.platform != 'win32':
        raise RuntimeError('Run this regression on native Windows')
    build = (_project_materials_root(ROOT) / 'build-espeak-windows').resolve(strict=True)
    executable = (build / 'rockboxui.exe').resolve(strict=True)
    disk = (build / 'simdisk').resolve(strict=True)
    if executable.parent != build or disk.parent != build or not (disk / '.tts-test-profile').exists():
        raise RuntimeError('Refusing to use anything except the isolated development profile')
    native = windows_backend()
    native.ensure_unused(executable)
    labels = catalog_labels(build, 'polski')
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    results = _project_materials_root(ROOT) / 'sonic-simulator-tests' / timestamp
    results.mkdir(parents=True)
    report = {'passed': False, 'runs': [], 'executable_sha256':
              hashlib.sha256(executable.read_bytes()).hexdigest()}
    fixture = disk / '000 Sonic.txt'
    if fixture.exists():
        fixture.rename(results / 'previous-test-text.txt')
    fixture.write_text('Próba szybkiej syntezy. Żółw czyta słowa i przesuwa kursor. ' * 500,
                       encoding='utf-8')
    duration_fixture = disk / '001 Sonic duration.txt'
    if duration_fixture.exists():
        duration_fixture.rename(results / 'previous-duration-text.txt')
    duration_text = 'Szybkie czytanie ma skracać rzeczywisty czas odtwarzania całego tekstu. ' * 9
    duration_fixture.write_text(duration_text, encoding='utf-8')
    log = build / 'simulator.log'
    print(f'Native Sonic integration evidence: {results}', flush=True)
    try:
        for rate in (451, 1350):
            evidence = results / str(rate)
            evidence.mkdir()
            for name in ('config.cfg', 'config.cfg.new', '.resume.cfg', '.resume.cfg.new'):
                source = disk / '.rockbox' / name
                if source.exists():
                    source.rename(evidence / name)
            if log.exists():
                log.rename(evidence / 'previous-simulator.log')
            (disk / '.rockbox/config.cfg').write_text(
                'lang: /.rockbox/langs/polski.lng\ntalk menu: on\ntalk dir: spell\n'
                'talk file: spell\ntalk file clip: off\ntalk dir clip: off\n'
                'tts enabled: on\ntts language: system\ntts variant: \n'
                f'tts rate: {rate}\ntts volume: 100\ntts pitch: 50\ntts range: 50\n'
                'tts punctuation: none\ntts wordgap: 0\nvolume: -25\n', encoding='utf-8')
            capture = evidence / 'mixed.raw'
            environment = dict(os.environ, SDL_AUDIODRIVER='disk', SDL_VIDEODRIVER='windows',
                               SDL_DISKAUDIODELAY='12', SDL_DISKAUDIOFILE=str(capture))
            process = subprocess.Popen([str(executable), '--root', str(disk), '--audiodev', str(capture)],
                cwd=build, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
            window = None
            cursor = 0
            run = {'rate': rate, 'checks': []}
            report['runs'].append(run)
            try:
                window = find_window(process.pid, environment)
                native.set_hidden(process.pid, window, True)

                def text():
                    return log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''

                def recent():
                    nonlocal cursor
                    current = text()
                    result = current[cursor:]
                    cursor = len(current)
                    return result

                def expect(fragment, timeout=15):
                    collected = ''
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        collected += recent()
                        if fragment in collected:
                            return collected
                        if process.poll() is not None:
                            raise AssertionError(f'Simulator exited: {process.returncode}')
                        time.sleep(0.05)
                    raise AssertionError(f'Missing {fragment!r}: {collected[-1500:]}')

                def press(key):
                    recent()
                    send_key(process.pid, window, key, True, environment)
                    try:
                        time.sleep(0.12)
                    finally:
                        if process.poll() is None:
                            send_key(process.pid, window, key, False, environment)
                    time.sleep(0.4)

                def select(fragment):
                    for attempt in range(32):
                        phrases = re.findall(r'^TTS: (.*)$', recent(), re.MULTILINE)
                        if phrases and fragment in phrases[-1]:
                            beginning = capture.stat().st_size
                            press('space')
                            return beginning
                        press('Down')
                    raise AssertionError(f'Menu option missing: {fragment}')

                expect(f'rate={rate} ')
                run['checks'].append('extended configured rate reaches native synthesizer')
                press('Down')
                select(labels['LANG_DIR_BROWSER'])
                select('000 Sonic')
                expect('TTS utterance: Próba szybkiej syntezy.')
                time.sleep(1.0)
                positions = [int(value) for value in re.findall(r'TTS reader cursor: (\d+)', text())]
                if not positions or positions[-1] <= 0 or positions != sorted(positions):
                    raise AssertionError('Extended-rate playback cursor does not advance monotonically')
                press('space')
                expect('TTS reader state: paused')
                paused_text = text()
                utterances = paused_text.count('TTS utterance:')
                paused_positions = re.findall(r'TTS reader cursor: (\d+)', paused_text)
                pause_start = capture.stat().st_size
                time.sleep(1.2)
                pause_end = capture.stat().st_size
                if re.findall(r'TTS reader cursor: (\d+)', text()) != paused_positions:
                    raise AssertionError('Extended-rate cursor advanced during pause')
                press('space')
                expect('TTS reader state: reading')
                time.sleep(0.8)
                resumed = text()
                resumed_positions = re.findall(r'TTS reader cursor: (\d+)', resumed)
                if not resumed_positions or int(resumed_positions[-1]) <= int(paused_positions[-1]):
                    raise AssertionError('Extended-rate cursor did not resume')
                if resumed.count('TTS utterance:') != utterances:
                    raise AssertionError('Pause/resume re-synthesized the retained Sonic block')
                run['checks'].append('retimed cursor advances, freezes and resumes without re-synthesis')
                press('Right')
                navigation = expect('TTS reader state: paused')
                if 'TTS:' not in navigation:
                    expect('TTS:')
                press('space')
                expect('TTS reader state: reading')
                press('Escape')
                expect('TTS:')
                run['checks'].append('navigation interrupts Sonic and subsequent speech recovers')
                duration_start = select('001 Sonic duration')
                expect(f'TTS reader state: finished offset={len(duration_text.encode("utf-8"))}', timeout=45)
                duration_end = capture.stat().st_size
                run['reader_duration_bytes'] = duration_end - duration_start
                run['reader_duration_seconds'] = run['reader_duration_bytes'] / 176400
                run['checks'].append('fixed text reaches EOF after actual voice mixer playback')
                press('Escape')
                shutdown(process, window, environment)
                if process.returncode != 0:
                    raise AssertionError(f'Unexpected shutdown status: {process.returncode}')
                audio = array.array('h', capture.read_bytes())
                paused_audio = audio[pause_start // 2:pause_end // 2]
                if not paused_audio or any(paused_audio):
                    raise AssertionError('Actual high-rate mixer PCM is not silent during pause')
                nonzero = sum(sample != 0 for sample in audio)
                if nonzero < 1000 or 'TTS: synthesis failed' in text():
                    raise AssertionError('Extended-rate synthesis failed or produced no usable audio')
                run.update(pcm_samples=len(audio), nonzero_samples=nonzero,
                           pause_bytes=[pause_start, pause_end], paused_cursor=int(paused_positions[-1]),
                           resumed_cursor=int(resumed_positions[-1]))
                run['checks'].append('actual nonzero mixer output, silent pause and graceful shutdown')
            finally:
                if process.poll() is None:
                    if window is not None:
                        try:
                            shutdown(process, window, environment)
                        except (AssertionError, OSError, RuntimeError, subprocess.TimeoutExpired):
                            pass
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                native.ensure_unused(executable)
                if log.exists():
                    log.rename(evidence / 'simulator.log')
        duration_ratio = report['runs'][1]['reader_duration_bytes'] / report['runs'][0]['reader_duration_bytes']
        report['high_rate_duration_ratio'] = duration_ratio
        if duration_ratio >= 0.6:
            raise AssertionError(f'1350 WPM playback is not meaningfully faster than 451 WPM: {duration_ratio:.3f}')
        report['passed'] = True
    finally:
        native.ensure_unused(executable)
        if fixture.exists():
            fixture.rename(results / 'test-text.txt')
        if duration_fixture.exists():
            duration_fixture.rename(results / 'duration-text.txt')
        (results / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: native Sonic reader and mixer at 451 and 1350 WPM', flush=True)


if __name__ == '__main__':
    main()
