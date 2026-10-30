"""Additional index-role acceptance inside the owned Windows package fixture."""
from pathlib import Path
import re
import time
import unittest


def require_index_role(text, connector, enabled):
    geometry = re.findall(r'A11Y list geometry:.*count=(\d+) selected=(\d+) group=(\d+)', text)
    if not geometry:
        raise AssertionError('Missing actual list geometry')
    count, selected, group = map(int, geometry[-1])
    if not count or group != 1 or selected >= count:
        raise AssertionError('Unexpected option-list geometry')
    position = f'{selected + 1} {connector} {count}'
    indices = re.findall(r'^TTS: (\d+ ' + re.escape(connector) + r' \d+)\s*$', text, re.M)
    if enabled:
        if position not in indices or not re.search(r'TTS utterance:[^\r\n]*' + re.escape(position), text):
            raise AssertionError('Missing synthesized categorical-list index: ' + position)
    elif indices:
        raise AssertionError('Numeric slider unexpectedly speaks a list index')
    return dict(position=selected + 1, total=count, enabled=enabled)


class IndexJourney:
    def __init__(self, inputs, executable, labels):
        self.inputs, self.labels = inputs, labels
        self.log = executable.parent / 'simulator.log'
        text = self.read()
        start = text.rfind('A11Y list geometry:')
        self.current = text[start:]
        self.steps = []

    def read(self):
        return self.log.read_text(encoding='utf-8', errors='replace')

    def step(self, key):
        start = len(self.read())
        self.inputs.press(key)
        deadline = time.monotonic() + 12
        previous, stable = None, time.monotonic()
        while time.monotonic() < deadline:
            text = self.read()[start:]
            if text != previous:
                previous, stable = text, time.monotonic()
            if 'TTS: ' in text and 'TTS utterance:' in text and time.monotonic() - stable >= 0.25:
                self.current = text
                self.steps.append(dict(key=key, text=text))
                return text
            self.inputs.alive()
            time.sleep(0.05)
        raise AssertionError('No settled synthesized row after ' + key)

    def enter(self, identifier, maximum=40):
        label = self.labels[identifier]
        for _ in range(maximum):
            spoken = re.findall(r'^TTS: (.*?)\r?$', self.current, re.M)
            if label in spoken:
                return self.step('Right')
            self.step('Down')
        raise AssertionError('Could not find menu row: ' + identifier + ' / ' + label)

    def run(self):
        for identifier in ('LANG_SETTINGS', 'LANG_GENERAL_SETTINGS', 'LANG_SYSTEM',
                           'LANG_ACCESSIBILITY_BUTTONS', 'LANG_ACCESSIBILITY_INTERFACE_ACTIONS'):
            self.enter(identifier)
        text = self.step('Right')  # First physical button's single-click action.
        checks = [require_index_role(text, self.labels['VOICE_OF'], True)]
        checks.append(require_index_role(self.step('Up'), self.labels['VOICE_OF'], True))
        for _ in range(4):
            self.step('Left')  # Cancel selector, profile, button menu, System.
        for identifier in ('LANG_VOICE', 'LANG_TALKBOX_SETTINGS', 'LANG_TTS', 'LANG_TTS_RATE'):
            text = self.enter(identifier)
        checks.append(require_index_role(text, self.labels['VOICE_OF'], False))
        self.step('Left')  # Restore the unchanged speech rate.
        return dict(passed=True, language=self.labels['VOICE_OF'], checks=checks, steps=self.steps)


def install_package_checks():
    """Install before the qualified private-desktop fixture patches Popen."""
    import test_tts_windows_package as package
    from test_tts_simulator import catalog_labels
    sessions = {}
    original_init = package.PackageInputProbe.__init__
    original_shutdown = package.shutdown
    build = Path('D:/work/Workspace/rockbox/build-espeak-windows-hibyr1')

    def initialize(self, process, executable, window, layout, report):
        original_init(self, process, executable, window, layout, report)
        sessions[process.pid] = (self, executable, report)

    def shutdown(process, window, environment, *args, **kwargs):
        inputs, executable, report = sessions.pop(process.pid)
        # One complete journey in each language; factory-default acceptance
        # retains the ordinary package test without repeating this journey.
        if report['label'] in ('normal-wasapi', 'unicode-path'):
            language = 'english' if report['label'] == 'normal-wasapi' else 'polski'
            report['index_role_acceptance'] = IndexJourney(inputs, executable, catalog_labels(build, language)).run()
        return original_shutdown(process, window, environment, *args, **kwargs)

    package.PackageInputProbe.__init__ = initialize
    package.shutdown = shutdown


class IndexAcceptanceTests(unittest.TestCase):
    def test_requires_actual_index_and_synthesized_utterance(self):
        geometry = 'A11Y list geometry: count=5 selected=3 group=1\n'
        text = geometry + 'TTS: Default\nTTS: 4 of 5\nTTS utterance: Default 4 of 5\n'
        self.assertEqual(require_index_role(text, 'of', True)['position'], 4)
        for invalid in (text.replace('4 of 5', '3 of 5'), text.replace('TTS utterance:', 'Queued:'), geometry):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                require_index_role(invalid, 'of', True)

    def test_numeric_slider_rejects_an_index(self):
        text = 'A11Y list geometry: count=1271 selected=95 group=1\nTTS: 175%\nTTS utterance: 175%\n'
        self.assertFalse(require_index_role(text, 'z', False)['enabled'])
        with self.assertRaises(AssertionError):
            require_index_role(text + 'TTS: 96 z 1271\n', 'z', False)


if __name__ == '__main__':
    unittest.main()
