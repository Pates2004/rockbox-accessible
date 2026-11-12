"""Execute actual bounded RDS announcement state transitions, without a tuner."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest
import uuid

from test_tts_coverage import extract_block
from test_radio_dynamic import ROOT, catalog_label
from project_materials import project_materials_root


class RdsAutomaticTests(unittest.TestCase):
    def test_centre_key_and_common_dispatch(self):
        keymap = (ROOT / 'apps/keymaps/keymap-clip.c').read_text(encoding='utf-8')
        mapping = extract_block(keymap, 'static const struct button_mapping button_context_radio[]')
        self.assertRegex(mapping, r'ACTION_FM_RDS,\s*BUTTON_SELECT\|BUTTON_REL,\s*BUTTON_SELECT')
        self.assertRegex(mapping, r'ACTION_FM_MENU,\s*BUTTON_SELECT\|BUTTON_REPEAT,\s*BUTTON_SELECT')
        radio = (ROOT / 'apps/radio/radio.c').read_text(encoding='utf-8')
        start = radio.index('            case ACTION_FM_RDS:')
        stop = radio.index('            case ACTION_FM_PRESET:', start)
        dispatch = radio[start:stop]
        self.assertIn('if (talk_tts_enabled(&global_settings))', dispatch)
        self.assertIn('radio_speak_info();', dispatch)
        self.assertIn('/* fall through */', dispatch)
        loop = extract_block(radio, 'void radio_screen(')
        self.assertIn('button == ACTION_NONE && !done', loop)
        self.assertIn('search_dir != 0 || done', loop)

    def test_actual_catalogs_and_default(self):
        for language, expected in (("english", "Automatic RDS announcements"),
                                   ("polski", "Automatyczne odczytywanie RDS")):
            catalog = (ROOT / "apps/lang" / (language + ".lang")).read_text(encoding="utf-8")
            for section in ("dest", "voice"):
                self.assertEqual(catalog_label(catalog, "LANG_FM_RDS_TALK", section), expected)
        settings = (ROOT / 'apps/settings_list.c').read_text(encoding='utf-8')
        self.assertIn('fm_rds_talk, LANG_FM_RDS_TALK, 0,', settings)
        self.assertIn('"rds announcements", "off,station,text,both"', settings)

    def test_actual_state_transitions(self):
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        if not shutil.which(compiler[0]):
            self.skipTest('Host C compiler required')
        area = project_materials_root(ROOT) / 'rds-automatic-tests' / uuid.uuid4().hex
        area.mkdir(parents=True)
        paths = ['apps/radio/radio.c', 'apps/settings.h',
                 'tools/tests/fixtures/rds_automatic_fixture.c', 'tools/tests/test_rds_automatic.py']
        inputs = {name: (ROOT / name).read_bytes() for name in paths}
        radio = inputs[paths[0]].decode('utf-8')
        settings = inputs[paths[1]].decode('utf-8')
        policy = '\n'.join(extract_block(settings, 'static inline bool ' + name + '(')
                           for name in ('talk_tts_enabled', 'talk_menus_enabled', 'talk_dynamic_enabled'))
        production = extract_block(radio, 'struct radio_rds_info\n') + ';\n'
        production += extract_block(radio, 'struct radio_rds_speech\n') + ';\n'
        production += '\n'.join(extract_block(radio, signature) for signature in
                                ('static void radio_read_info(', 'static int radio_info_speak(',
                                 'static void radio_speak_info(', 'static bool radio_rds_waiting(',
                                 'static void radio_rds_speech_update('))
        template = inputs[paths[2]].decode('utf-8')
        source = area / 'rds.c'
        source.write_text(template.replace('ACTUAL_POLICY', policy).replace('ACTUAL_RDS', production),
                          encoding='utf-8')
        results = []
        scenarios = ('manual', 'manual-empty', 'normal', 'wrap', 'throttle', 'busy', 'unstable', 'blank', 'input', 'retune',
                     'modes', 'long', 'paused', 'off', 'disabled', 'invalid', 'dynamic', 'synthesis',
                     'unavailable', 'missing', 'recording', 'searching')
        try:
            for mode, flags in (('ordinary', []), ('ubsan', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])):
                binary = area / (mode + ('.exe' if os.name == 'nt' else '.bin'))
                command = compiler + ['-DHAVE_ESPEAK', '-std=c99', '-O1', '-Wall', '-Wextra', '-Werror',
                                      *flags, str(source), '-o', str(binary)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                results.append(dict(argv=command, exit=result.returncode, stderr=result.stderr))
                self.assertEqual(result.returncode, 0, result.stderr)
                for scenario in scenarios:
                    with self.subTest(mode=mode, scenario=scenario):
                        result = subprocess.run([str(binary), scenario], capture_output=True, text=True, timeout=5)
                        results.append(dict(mode=mode, scenario=scenario, exit=result.returncode,
                                            stdout=result.stdout, stderr=result.stderr))
                        self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            (area / 'report.json').write_text(json.dumps(dict(
                scope='Actual production state machine; mocked tuner and speech; no physical RF/audio acceptance',
                inputs={k: hashlib.sha256(v).hexdigest() for k, v in inputs.items()}, results=results,
                passed=bool(results) and all(row['exit'] == 0 for row in results)), indent=2), encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
