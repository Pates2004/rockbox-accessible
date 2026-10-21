import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import test_polish_translation as catalog_support
import test_tts_plugin_translation as plugin_support


ROOT = Path(__file__).resolve().parents[2]
LABELS = {
    "LANG_TALKBOX_SETTINGS": ("*", "Ustawienia Talkbox"),
    "LANG_TTS": ("*", "Ustawienia eSpeak"),
    "LANG_VOICE_MENU": (
        "*", "Używaj plików głosowych do czytania interfejsu",
    ),
    "LANG_VOICE_DIR": ("*", "Czytanie nazw katalogów"),
    "LANG_VOICE_FILE": ("*", "Czytanie nazw plików"),
    "LANG_TALK_MIXER_LEVEL": ("*", "Głośność plików głosowych"),
    "LANG_REPLAYGAIN": ("*", "ReplayGain"),
    "LANG_REPLAYGAIN_MODE": ("*", "Tryb ReplayGain"),
    "LANG_CROSSFEED": ("*", "Crossfeed"),
    "LANG_BRIGHTNESS": ("backlight_brightness", "Jasność podświetlenia"),
    "LANG_FLIP_DISPLAY": ("*", "Odwróć ekran"),
}
DISPLAY_MARKERS = {"LANG_REPLAYGAIN": "~", "LANG_CROSSFEED": "~"}
INTEGRATED_TRANSLATIONS = {
    **catalog_support.TTS_TRANSLATIONS, **plugin_support.TRANSLATIONS,
}
TARGETS = (
    ("sansaclipplus", 66, "rtc:recording:radio:charging"),
    ("sansaclipzip", 68, "rtc:recording:radio:charging:backlight_brightness"),
    ("hibyr1", 124, "charging:backlight_brightness"),
)


def setting_arguments(name):
    settings = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
    match = re.search(
        r"\b(?:TABLE_SETTING_LIST|INT_SETTING|OFFON_SETTING|CHOICE_SETTING)"
        rf"\(\s*[^,]+,\s*{re.escape(name)}\s*,", settings,
    )
    if match is None:
        raise AssertionError(f"Missing setting declaration: {name}")
    arguments = settings[match.end():]
    depth = 1
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|[()]', arguments):
        if token.group() == "(":
            depth += 1
        elif token.group() == ")":
            depth -= 1
            if depth == 0:
                return arguments[:token.start()]
    raise AssertionError(f"Unclosed setting declaration: {name}")


class PolishSpeechLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polish = catalog_support.parse_language(
            (ROOT / "apps/lang/polski.lang").read_text(encoding="utf-8")
        )
        cls.english = catalog_support.parse_language(
            (ROOT / "apps/lang/english.lang").read_text(encoding="utf-8")
        )

    def test_exact_display_and_voice_labels(self):
        for identifier, (selector, label) in LABELS.items():
            for section in ("dest", "voice"):
                marker = DISPLAY_MARKERS.get(identifier, "") if section == "dest" else ""
                expected = {selector: f'"{marker}{label}"'}
                if selector != "*":
                    expected = {"*": "none", **expected}
                with self.subTest(identifier=identifier, section=section):
                    self.assertEqual(expected, self.polish[identifier][section])
                    self.assertEqual(label.strip(), label)

    def test_audio_feature_names_are_canonical_in_all_translated_fields(self):
        canonical = {"replaygain": "ReplayGain", "crossfeed": "Crossfeed"}
        for identifier, phrase in self.polish.items():
            for section in ("dest", "voice"):
                for selector, text in phrase[section].items():
                    with self.subTest(id=identifier, section=section, selector=selector):
                        self.assertNotRegex(text, r"(?i)riplejgejn|krosfi[dt]")
                        for token in re.findall(r"(?i)\b(?:replaygain|crossfeed)\b", text):
                            self.assertEqual(canonical[token.lower()], token)

    def test_timer_and_other_brightness_labels_are_preserved(self):
        for section in ("dest", "voice"):
            with self.subTest(section=section):
                self.assertEqual(
                    {"*": '"Podświetlenie"'}, self.polish["LANG_BACKLIGHT"][section],
                )
                charging = (
                    "Podświetlenie (w trakcie ładowania)" if section == "dest"
                    else "Podświetlenie w trakcie ładowania"
                )
                self.assertEqual(
                    {"*": "none", "charging": f'"{charging}"'},
                    self.polish["LANG_BACKLIGHT_ON_WHEN_CHARGING"][section],
                )
                self.assertEqual(
                    {"*": '"Jasność podświetlenia"', "lowmem": "none"},
                    self.polish["LANG_BACKLIGHT_BRIGHTNESS"][section],
                )
                self.assertEqual(
                    {"*": "none", "buttonlight_brightness":
                     '"Jasność podświetlenia przycisków"'},
                    self.polish["LANG_BUTTONLIGHT_BRIGHTNESS"][section],
                )

    def test_real_setting_bindings_distinguish_duration_from_brightness(self):
        for setting, identifier, callback in (
            ("backlight_timeout", "LANG_BACKLIGHT", "backlight_set_timeout"),
            ("backlight_timeout_plugged", "LANG_BACKLIGHT_ON_WHEN_CHARGING",
             "backlight_set_timeout_plugged"),
            ("remote_backlight_timeout", "LANG_BACKLIGHT", "remote_backlight_set_timeout"),
            ("remote_backlight_timeout_plugged", "LANG_BACKLIGHT_ON_WHEN_CHARGING",
             "remote_backlight_set_timeout_plugged"),
        ):
            with self.subTest(setting=setting):
                arguments = setting_arguments(setting)
                self.assertRegex(arguments, rf"^\s*{identifier}\s*,")
                self.assertRegex(arguments, r"\bUNIT_SEC\b")
                self.assertRegex(arguments, rf"\b{callback}\b")
                self.assertNotIn("LANG_BRIGHTNESS", arguments)
        brightness = setting_arguments("brightness")
        self.assertRegex(brightness, r"^\s*LANG_BRIGHTNESS\s*,")
        self.assertRegex(brightness, r"\bUNIT_INT\b")
        self.assertIn("backlight_set_brightness", brightness)
        self.assertNotIn("UNIT_SEC", brightness)

    def test_name_modes_remain_separate_from_voice_file_switches_and_volume(self):
        for setting, identifier in (
            ("talk_dir", "LANG_VOICE_DIR"), ("talk_file", "LANG_VOICE_FILE"),
        ):
            with self.subTest(setting=setting):
                arguments = setting_arguments(setting)
                self.assertRegex(arguments, rf"^\s*{identifier}\s*,")
                for choice in ("off_number_spell", "LANG_OFF", "LANG_VOICE_NUMBER",
                               "LANG_VOICE_SPELL"):
                    self.assertIn(choice, arguments)
        for setting, identifier in (
            ("talk_menu", "LANG_VOICE_MENU"),
            ("talk_dir_clip", "LANG_VOICE_DIR_TALK"),
            ("talk_file_clip", "LANG_VOICE_FILE_TALK"),
            ("talk_mixer_amp", "LANG_TALK_MIXER_LEVEL"),
        ):
            with self.subTest(setting=setting):
                self.assertRegex(setting_arguments(setting), rf"^\s*{identifier}\s*,")
        self.assertIn("voice_set_mixer_level", setting_arguments("talk_mixer_amp"))
        self.assertRegex(setting_arguments("tts_volume"), r"^\s*LANG_TTS_VOLUME\s*,")
        self.assertNotIn("voice_set_mixer_level", setting_arguments("tts_volume"))

    def test_flip_label_is_bound_to_display_rotation(self):
        for setting in ("flip_display", "remote_flip_display"):
            with self.subTest(setting=setting):
                self.assertRegex(setting_arguments(setting), r"^\s*LANG_FLIP_DISPLAY\s*,")
        display = (ROOT / "apps/menus/display_menu.c").read_text(encoding="utf-8")
        for callback in ("button_set_flip", "lcd_set_flip"):
            self.assertRegex(display, rf"{callback}\(global_settings\.flip_display\)")
        self.assertIn("lcd_remote_set_flip(global_settings.remote_flip_display)", display)

    def test_source_selectors_placeholders_and_nontext_markers_are_preserved(self):
        self.assertEqual(self.english.keys(), self.polish.keys())
        for identifier, phrase in self.polish.items():
            reference = self.english[identifier]
            with self.subTest(identifier=identifier):
                self.assertEqual(reference["user"], phrase["user"])
                self.assertEqual(reference["source"], phrase["source"])
            for section in catalog_support.SECTIONS:
                self.assertEqual(reference[section].keys(), phrase[section].keys())
                for selector, value in phrase[section].items():
                    original = reference[section][selector]
                    with self.subTest(id=identifier, section=section, selector=selector):
                        self.assertEqual(
                            catalog_support.PLACEHOLDER.findall(original),
                            catalog_support.PLACEHOLDER.findall(value),
                        )
                        if not original.startswith('"') or not value.startswith('"'):
                            self.assertEqual(original, value)

    def test_all_102_integrated_speech_phrases_are_preserved(self):
        self.assertEqual(47, len(catalog_support.TTS_TRANSLATIONS))
        self.assertEqual(55, len(plugin_support.TRANSLATIONS))
        self.assertEqual(102, len(INTEGRATED_TRANSLATIONS))
        for identifier, (source, translation) in INTEGRATED_TRANSLATIONS.items():
            voice = catalog_support.TTS_VOICE_OVERRIDES.get(
                identifier, (source, translation),
            )[1]
            with self.subTest(identifier=identifier):
                self.assertEqual({"*": f'"{source}"'}, self.polish[identifier]["source"])
                self.assertEqual({"*": f'"{translation}"'}, self.polish[identifier]["dest"])
                self.assertEqual({"*": f'"{voice}"'}, self.polish[identifier]["voice"])


@unittest.skipUnless(shutil.which("perl"), "Perl is required for actual genlang catalogs")
class PolishSpeechCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workspace = catalog_support.project_materials_root(ROOT)
        workspace.mkdir(parents=True, exist_ok=True)
        cls.output = Path(tempfile.mkdtemp(prefix="polish-speech-labels-", dir=workspace))
        cls.catalogs = {}
        cls.identifiers = {}
        cls.features = {}
        for model, model_number, enabled_features in TARGETS:
            for features in (enabled_features, ""):
                case = model + ("-enabled" if features else "-disabled")
                cls.features[case] = features.split(":") if features else []
                target = model + (":" + features if features else "")
                output = cls.output / case
                output.mkdir()
                for language in ("english", "polski"):
                    prefix = output / language
                    command = [
                        "perl", "-s", (ROOT / "tools/genlang").as_posix(),
                        f"-e={(ROOT / 'apps/lang/english.lang').as_posix()}", f"-t={target}",
                        f"-i={model_number}", f"-b={prefix.as_posix()}.lng",
                        f"-c={prefix.as_posix()}.vstrings",
                        (ROOT / f"apps/lang/{language}.lang").as_posix(),
                    ]
                    completed = subprocess.run(
                        command, capture_output=True, text=True, encoding="utf-8",
                        cwd=ROOT, timeout=60,
                    )
                    (output / f"{language}.json").write_text(json.dumps({
                        "command": command, "returncode": completed.returncode,
                        "stdout": completed.stdout, "stderr": completed.stderr,
                    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    if completed.returncode or completed.stderr:
                        raise AssertionError(
                            f"genlang failed for {case}/{language}: {completed.stderr}"
                        )
                    for extension in ("lng", "vstrings"):
                        cls.catalogs[case, language, extension] = (
                            catalog_support.GenlangCatalogTests.read_catalog(
                                Path(f"{prefix}.{extension}"),
                            )
                        )
                cls.identifiers[case] = (
                    catalog_support.GenlangCatalogTests.read_identifiers(output / "english.list")
                )
        (cls.output / "inventory.json").write_text(json.dumps({
            path.relative_to(cls.output).as_posix(): {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(cls.output.rglob("*")) if path.is_file()
        }, indent=2) + "\n", encoding="utf-8")

    def test_real_catalog_headers_ids_sizes_and_placeholders(self):
        model_numbers = {model: number for model, number, features in TARGETS}
        for (case, language, extension), catalog in self.catalogs.items():
            with self.subTest(case=case, language=language, extension=extension):
                model = case.rsplit("-", 1)[0]
                cookie = 0x1A if extension == "lng" else 0x9A
                self.assertEqual(bytes((cookie, 6, model_numbers[model], 0)), catalog["header"])
                self.assertEqual(catalog["declared_size"], catalog["payload_size"])
                reference = self.catalogs[case, "english", extension]["values"]
                self.assertEqual(reference.keys(), catalog["values"].keys())
                expected_ids = {
                    number for number in self.identifiers[case].values()
                    if extension == "vstrings" or number < 0x8000
                }
                self.assertEqual(expected_ids, set(catalog["values"]))
                for identifier, value in catalog["values"].items():
                    self.assertEqual(
                        catalog_support.PLACEHOLDER.findall(reference[identifier]),
                        catalog_support.PLACEHOLDER.findall(value),
                    )

    def test_exact_labels_reach_real_display_and_voice_catalogs(self):
        for case, identifiers in self.identifiers.items():
            for identifier, (selector, expected) in LABELS.items():
                if selector != "*" and selector not in self.features[case]:
                    self.assertNotIn(identifier, identifiers)
                    continue
                for extension in ("lng", "vstrings"):
                    with self.subTest(case=case, identifier=identifier, extension=extension):
                        values = self.catalogs[case, "polski", extension]["values"]
                        self.assertEqual(expected, values[identifiers[identifier]])

    def test_duration_labels_survive_with_and_without_charging(self):
        for case, identifiers in self.identifiers.items():
            for extension in ("lng", "vstrings"):
                values = self.catalogs[case, "polski", extension]["values"]
                with self.subTest(case=case, extension=extension):
                    self.assertEqual("Podświetlenie", values[identifiers["LANG_BACKLIGHT"]])
                    identifier = "LANG_BACKLIGHT_ON_WHEN_CHARGING"
                    if "charging" in self.features[case]:
                        expected = (
                            "Podświetlenie (w trakcie ładowania)" if extension == "lng"
                            else "Podświetlenie w trakcie ładowania"
                        )
                        self.assertEqual(expected, values[identifiers[identifier]])
                    else:
                        self.assertNotIn(identifier, identifiers)

    def test_all_101_speech_additions_survive_real_catalog_generation(self):
        for case, identifiers in self.identifiers.items():
            for identifier, (source, translated) in INTEGRATED_TRANSLATIONS.items():
                voice = catalog_support.TTS_VOICE_OVERRIDES.get(
                    identifier, (source, translated),
                )[1]
                for extension, expected in (("lng", translated), ("vstrings", voice)):
                    with self.subTest(case=case, identifier=identifier, extension=extension):
                        values = self.catalogs[case, "polski", extension]["values"]
                        self.assertEqual(expected, values[identifiers[identifier]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
