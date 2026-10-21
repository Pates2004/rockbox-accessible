import array
import datetime
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import wave

from test_tts_simulator import find_window, send_key, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]


def tone_amplitude(path, start, end):
    with path.open('rb') as stream:
        stream.seek(start - start % 4)
        samples = array.array('h', stream.read((end - start) // 4 * 4))
    amplitudes = []
    for offset in range(0, len(samples) - 8192, 8192):
        window = samples[offset:offset + 8192:2]
        real = sum(value * math.cos(2 * math.pi * 997 * index / 44100)
                   for index, value in enumerate(window))
        imaginary = sum(value * math.sin(2 * math.pi * 997 * index / 44100)
                        for index, value in enumerate(window))
        amplitudes.append(2 * math.hypot(real, imaginary) / len(window))
    if len(amplitudes) < 4:
        raise AssertionError('Too few audio frames for a playback-gain measurement')
    return statistics.median(amplitudes)


def main():
    if sys.platform != 'win32':
        raise RuntimeError('Run this regression on native Windows')
    build = _project_materials_root(ROOT) / 'build-espeak-windows'
    executable = build / 'rockboxui.exe'
    native = windows_backend()
    native.ensure_unused(executable)
    disk = build / 'simdisk'
    if not (disk / '.tts-test-profile').exists():
        raise RuntimeError('Refusing to use a non-test profile')
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    results = _project_materials_root(ROOT) / 'ducking-tests' / timestamp
    results.mkdir(parents=True)
    report = {'passed': False, 'runs': [], 'method':
              '997 Hz music, silent synthesized voice PCM, median spectral amplitude ratios'}
    (disk / '005 Ducking.txt').write_text('Pomiar przyciszania muzyki podczas syntezy mowy. ' * 200,
                                          encoding='utf-8')
    samples = array.array('h', (int(6000 * math.sin(2 * math.pi * 997 * frame / 44100))
                               for frame in range(44100)))
    with wave.open(str(disk / '006 Ducking.wav'), 'wb') as output:
        output.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
        for second in range(180):
            output.writeframesraw(samples.tobytes())
    try:
        for enabled, level in ((False, 25), (True, 25), (True, 50), (True, 0)):
            label = f'{"on" if enabled else "off"}-{level}'
            evidence = results / label
            evidence.mkdir()
            for relative in ('config.cfg', 'config.cfg.new', '.resume.cfg', '.resume.cfg.new'):
                source = disk / '.rockbox' / relative
                if source.exists():
                    source.rename(evidence / relative)
            log = build / 'simulator.log'
            if log.exists():
                log.rename(evidence / 'previous-simulator.log')
            (disk / '.rockbox/config.cfg').write_text(
                'lang: /.rockbox/langs/polski.lng\ntalk menu: on\ntalk dir: spell\n'
                'talk file: spell\ntalk file clip: off\ntalk dir clip: off\n'
                'tts enabled: on\ntts language: system\ntts rate: 175\ntts volume: 0\n'
                f'tts ducking: {"on" if enabled else "off"}\ntts ducking level: {level}\n'
                'volume: -25\n', encoding='utf-8')
            capture = evidence / 'mixed.raw'
            environment = dict(os.environ, SDL_AUDIODRIVER='disk', SDL_VIDEODRIVER='windows',
                               SDL_DISKAUDIODELAY='12', SDL_DISKAUDIOFILE=str(capture))
            process = subprocess.Popen([str(executable), '--root', str(disk), '--audiodev', str(capture)],
                cwd=build, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
            window = None
            cursor = 0
            try:
                window = find_window(process.pid, environment)
                native.set_hidden(process.pid, window, True)

                def recent():
                    nonlocal cursor
                    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
                    result = text[cursor:]
                    cursor = len(text)
                    return result

                def press(key):
                    recent()
                    send_key(process.pid, window, key, True, environment)
                    time.sleep(0.12)
                    send_key(process.pid, window, key, False, environment)
                    time.sleep(0.6)
                    if process.poll() is not None:
                        raise AssertionError(f'Simulator exited: {process.returncode}')

                def select(fragment):
                    for attempt in range(32):
                        phrases = re.findall(r'^TTS: (.*)$', recent(), re.MULTILINE)
                        if phrases and fragment in phrases[-1]:
                            press('space')
                            return
                        press('Down')
                    raise AssertionError(f'Menu entry unavailable: {fragment}')

                def measure():
                    start = capture.stat().st_size
                    time.sleep(1.2)
                    return start, capture.stat().st_size

                time.sleep(2)
                select('Pliki')
                select('006 Ducking')
                press('Insert')
                time.sleep(4)
                baseline_span = measure()
                select('Pliki')
                select('005 Ducking')
                deadline = time.monotonic() + 30
                while 'TTS: Pomiar przyciszania' not in log.read_text(encoding='utf-8', errors='replace'):
                    if time.monotonic() >= deadline or process.poll() is not None:
                        raise AssertionError('Text synthesis did not start during playback')
                    time.sleep(0.1)
                time.sleep(1.5)
                during_span = measure()
                press('space')
                time.sleep(1.5)
                paused_span = measure()
                press('space')
                time.sleep(1.5)
                resumed_span = measure()
                speech_log = log.read_text(encoding='utf-8', errors='replace')
                if 'TTS: Pomiar przyciszania' not in speech_log or 'TTS audio playback: 1' not in speech_log:
                    raise AssertionError('Measurement did not exercise synthesis during music playback')
                press('Escape')
                time.sleep(3)
                after_span = measure()
                shutdown(process, window, environment)
                baseline = tone_amplitude(capture, *baseline_span)
                during = tone_amplitude(capture, *during_span)
                paused = tone_amplitude(capture, *paused_span)
                resumed = tone_amplitude(capture, *resumed_span)
                after = tone_amplitude(capture, *after_span)
                if baseline < 20:
                    raise AssertionError(f'No stable music baseline: {baseline}')
                ratio = during / baseline
                recovery = after / baseline
                expected = level / 100 if enabled else 1.0
                run = {'enabled': enabled, 'level': level, 'baseline': baseline,
                       'during': during, 'paused': paused, 'resumed': resumed,
                       'after': after, 'ratio': ratio, 'recovery': recovery,
                       'pause_recovery': paused / baseline, 'resume_ratio': resumed / baseline}
                report['runs'].append(run)
                if abs(ratio - expected) > 0.035 or abs(recovery - 1) > 0.035:
                    raise AssertionError(f'Incorrect mixer attenuation/recovery: {run}')
                if abs(paused / baseline - 1) > 0.035 or abs(resumed / baseline - expected) > 0.035:
                    raise AssertionError(f'Incorrect pause/resume ducking: {run}')
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                if log.exists():
                    log.rename(evidence / 'simulator.log')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (results / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'Ducking evidence: {results}', flush=True)


if __name__ == '__main__':
    main()
