import datetime
import json
from pathlib import Path
import unittest

from test_tts_windows_package import inventory, validate_clean_profile


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    'lang: /.rockbox/langs/polski.lng\ntalk menu: on\ntalk dir: spell\n'
    'talk file: spell\ntalk dir clip: off\ntalk file clip: off\n'
    'tts enabled: on\ntts language: system\ntts variant: \ntts rate: 175\n'
    'tts rate scale: percent\ntts punctuation: none\n'
    'tts ducking: on\ntts ducking level: 25\ntts pitch: 50\n'
    'tts volume: 100\ntts range: 50\ntts wordgap: 0\nvolume: -25\n'
)


class CleanPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        cls.results = _project_materials_root(ROOT) / 'clean-package-tests' / timestamp
        cls.results.mkdir(parents=True)
        print(f'Clean package regression fixtures: {cls.results}', flush=True)

    def setUp(self):
        self.release = self.results / self._testMethodName
        self.configuration = self.release / 'simdisk/.rockbox/config.cfg'
        self.configuration.parent.mkdir(parents=True)
        self.configuration.write_text(DEFAULT_CONFIG, encoding='utf-8')

    def manifest(self):
        files = inventory(self.release)
        files.pop('manifest.json', None)
        manifest = {'files': files}
        (self.release / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return manifest

    def test_accessibility_profiles_rejected_even_if_manifested(self):
        names = ('accessibility.cfg', 'ACCESSIBILITY.CFG',
                 'accessibility-typing-echo.cfg', 'ACCESSIBILITY-TYPING-ECHO.CFG', 'accessibility-typing-echo.cfg.tmp',
                 'accessibility-lock.cfg', 'ACCESSIBILITY-LOCK.CFG', 'accessibility-lock.cfg.future',
                 'touch-sensitivity.cfg', 'TOUCH-SENSITIVITY.CFG', 'touch-sensitivity.cfg.tmp',
                 'accessibility-screen.cfg', 'ACCESSIBILITY-SCREEN.CFG',
                 'tts-reader.cfg', 'TTS-READER.CFG', 'Tts-Reader.Cfg',
                         'tts-reader.cfg.tmp', 'TTS-READER.CFG.NEW', 'tts-reader.cfg.future', 'Tts-Reader.Cfg.BaK',
                         'bluetooth.cfg', 'BLUETOOTH.CFG', 'BlueTooth.Cfg',
                         'bluetooth.cfg.tmp', 'BLUETOOTH.CFG.NEW', 'bluetooth.cfg.future', 'BlueTooth.Cfg.BaK',
                         'empty-feedback.cfg', 'EMPTY-FEEDBACK.CFG', 'Empty-Feedback.Cfg',
                 'empty-feedback.cfg.tmp', 'EMPTY-FEEDBACK.CFG.NEW', 'empty-feedback.cfg.future',
                 'Empty-Feedback.Cfg.BaK',
                 'accessibility-screen.cfg.tmp', 'accessibility-screen.cfg.future',
                 'accessibility-shortcut.cfg', 'ACCESSIBILITY-SHORTCUT.CFG',
                 'accessibility-shortcut.cfg.tmp', 'accessibility-shortcut.cfg.future',
                 'connectivity.cfg', 'CONNECTIVITY.CFG', 'connectivity.cfg.tmp', 'connectivity.cfg.future',
                 'accessibility.cfg.pending', 'Accessibility.cfg.BAK',
                 'accessibility.cfg.future')
        for index, name in enumerate(names):
            with self.subTest(name=name):
                self.release = self.results / f'accessibility-profile-{index}'
                self.configuration = self.release / 'simdisk/.rockbox/config.cfg'
                self.configuration.parent.mkdir(parents=True)
                self.configuration.write_text(DEFAULT_CONFIG, encoding='utf-8')
                (self.configuration.parent / name).write_text('private mapping', encoding='utf-8')
                with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
                    validate_clean_profile(self.release, self.manifest())

    def test_clean_defaults(self):
        settings = validate_clean_profile(self.release, self.manifest())
        self.assertEqual(settings['tts rate'], '175')
        self.assertEqual(settings['tts language'], 'system')
        self.assertNotIn('keyclick', settings)

    def test_card_diagnostic_state_and_stage_contents_rejected_even_when_manifested(self):
        names = ('rockbox.r1.connectivity-original', '.connectivity-state.json', '.connectivity-stage',
                 '.connectivity-stage/program', 'r1-connectivity.log', 'rockbox.r1.audio-original',
                 'rockbox.r1.audio-new', 'r1-audio-trace.so', 'r1-audio-diagnostic.log', 'r1-audio-launcher.log')
        for index, name in enumerate(names):
            for variant, spelling in enumerate((name, name.upper(), name + '.tmp')):
                with self.subTest(name=spelling):
                    release = self.results / f'diagnostic-state-{index}-{variant}'
                    config = release / 'simdisk/.rockbox/config.cfg'
                    config.parent.mkdir(parents=True)
                    config.write_text(DEFAULT_CONFIG, encoding='utf-8')
                    state = config.parent / spelling
                    state.parent.mkdir(parents=True, exist_ok=True)
                    state.write_text('Synthetic diagnostic runtime state', encoding='utf-8')
                    self.release = release
                    with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
                        validate_clean_profile(release, self.manifest())

    def test_explicit_keyclick_off_cannot_override_fresh_core_default(self):
        self.configuration.write_text(DEFAULT_CONFIG + 'keyclick: off\n', encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'clean default settings'):
            validate_clean_profile(self.release, self.manifest())

    def test_bookmark_aliases_and_alternate_temps_rejected_even_if_manifested(self):
        names = ('recent.bookmark', 'RECENT.BOOKMARK', 'book.txt.bookmark.tmp',
                 'book.txt.BOOKMARK.T01', 'book.txt.bmark.t01',
                 'book.txt.BMARK.T0F')
        for index, name in enumerate(names):
            with self.subTest(name=name):
                self.release = self.results / f'bookmark-alias-{index}'
                self.configuration = self.release / 'simdisk/.rockbox/config.cfg'
                self.configuration.parent.mkdir(parents=True)
                self.configuration.write_text(DEFAULT_CONFIG, encoding='utf-8')
                (self.configuration.parent / name).write_text('private bookmark', encoding='utf-8')
                with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
                    validate_clean_profile(self.release, self.manifest())

    def test_previous_speed_is_rejected_even_if_manifested(self):
        self.configuration.write_text(DEFAULT_CONFIG.replace('tts rate: 175', 'tts rate: 450'), encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'clean default settings'):
            validate_clean_profile(self.release, self.manifest())

    def test_resume_state_is_rejected_even_if_manifested(self):
        (self.configuration.parent / '.resume.cfg').write_text('resume index: 7\n', encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
            validate_clean_profile(self.release, self.manifest())

    def test_user_files_are_rejected_even_if_manifested(self):
        (self.release / 'simdisk/book.txt').write_text('Private test text', encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'user files'):
            validate_clean_profile(self.release, self.manifest())

    def test_pending_resume_state_is_rejected_even_if_manifested(self):
        (self.configuration.parent / '.resume.cfg.new').write_text('resume index: 7\n', encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
            validate_clean_profile(self.release, self.manifest())

    def test_player_name_is_rejected_even_if_manifested(self):
        (self.configuration.parent / 'playername.txt').write_text('Test player\n', encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
            validate_clean_profile(self.release, self.manifest())

    def test_generated_font_cache_is_rejected_even_if_manifested(self):
        (self.configuration.parent / '08-Rockfont.gc').touch()
        with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
            validate_clean_profile(self.release, self.manifest())

    def test_bookmark_history_is_rejected_even_if_manifested(self):
        for name in ('most-recent.bmark', 'book.txt.bmark', 'RECENT.BMARK'):
            with self.subTest(name=name):
                path = self.configuration.parent / name
                path.write_text('Private bookmark position\n', encoding='utf-8')
                with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
                    validate_clean_profile(self.release, self.manifest())
                path.unlink()

    def test_pending_bookmark_history_is_rejected_even_if_manifested(self):
        for name in ('most-recent.bmark.tmp', 'book.txt.bmark.new', 'RECENT.BMARK.BAK'):
            with self.subTest(name=name):
                path = self.configuration.parent / name
                path.write_text('Private pending bookmark position\n', encoding='utf-8')
                with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
                    validate_clean_profile(self.release, self.manifest())
                path.unlink()

    def test_synthetic_disk_is_rejected(self):
        (self.release / 'simdisk/.tts-test-profile').touch()
        with self.assertRaisesRegex(AssertionError, 'test disk marker'):
            validate_clean_profile(self.release, self.manifest())

    def test_unmanifested_file_is_rejected(self):
        manifest = self.manifest()
        (self.release / 'unexpected.txt').touch()
        with self.assertRaisesRegex(AssertionError, 'unmanifested'):
            validate_clean_profile(self.release, manifest)

    def test_duplicate_setting_is_rejected(self):
        self.configuration.write_text(DEFAULT_CONFIG + 'tts rate: 175\n', encoding='utf-8')
        with self.assertRaisesRegex(AssertionError, 'duplicate setting'):
            validate_clean_profile(self.release, self.manifest())

    def test_saved_log_is_rejected_even_if_manifested(self):
        (self.release / 'simulator.log').touch()
        with self.assertRaisesRegex(AssertionError, 'saved runtime state'):
            validate_clean_profile(self.release, self.manifest())


if __name__ == '__main__':
    unittest.main(verbosity=2)
