"""Check screen notice translations, existing timer links and conditional menus."""

import itertools
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
LABELS = (
    ("LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT",
     "Automatic screen lock after inactivity", "Automatyczna blokada ekranu po bezczynności"),
    ("LANG_ACCESSIBILITY_AUTOLOCK_LEGACY",
     "Use advanced keylock settings", "Zgodnie z zaawansowaną blokadą klawiszy"),
    ("LANG_ACCESSIBILITY_ACTION_TIME",
     "Announce current time", "Podaj aktualny czas"),
    ("LANG_ACCESSIBILITY_SCREEN_STATE",
     "Screen state announcements", "Zgłaszanie stanu ekranu"),
    ("LANG_ACCESSIBILITY_SCREEN_UNLOCK_NOTICE",
     "On screen unlock", "Komunikat przy odblokowaniu ekranu"),
    ("LANG_ACCESSIBILITY_SCREEN_LOCK_NOTICE",
     "On screen lock", "Komunikat przy blokowaniu ekranu"),
    ("LANG_ACCESSIBILITY_SCREEN_UNLOCKED",
     "Screen unlocked", "Ekran odblokowany"),
    ("LANG_ACCESSIBILITY_SCREEN_LOCKED",
     "Screen locked", "Ekran zablokowany"),
    ("LANG_ACCESSIBILITY_SCREEN_SAY_UNLOCKED",
     "Say screen unlocked", "Powiedz ekran odblokowany"),
    ("LANG_ACCESSIBILITY_SCREEN_SAY_LOCKED",
     "Say screen locked", "Powiedz ekran zablokowany"),
    ("LANG_ACCESSIBILITY_NOTICE_TIME_BATTERY",
     "Announce time and battery level", "Podaj czas i stan baterii"),
    ("LANG_ACCESSIBILITY_NOTICE_ALL",
     "Announce screen state, time and battery level", "Podaj stan ekranu, czas i stan baterii"),
    ("LANG_ACCESSIBILITY_NOTICE_SILENT",
     "Say nothing", "Nic nie mów"),
)
POLICY_FIELDS = r"\b(?:accessibility_screen\w*|screen_(?:unlock|lock)_notice|unlock_notice|lock_notice)\b"


def read_source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def language_phrases(language):
    identifiers = []
    phrases = {}
    for block in re.findall(r"<phrase>(.*?)</phrase>",
                            read_source(f"apps/lang/{language}.lang"), re.S):
        identifier = re.search(r"\bid:\s*(\w+)", block)
        if not identifier:
            continue
        identifiers.append(identifier[1])
        sections = {}
        for section in ("source", "dest", "voice"):
            contents = re.findall(rf"<{section}>(.*?)</{section}>", block, re.S)
            if len(contents) == 1:
                values = re.findall(r'^\s*\*:\s*"([^"]*)"\s*$', contents[0], re.M)
                if len(values) == 1:
                    sections[section] = values[0]
        phrases[identifier[1]] = sections
    return identifiers, phrases


def menu_block(source, name):
    match = re.search(r"\bMAKE_MENU\(\s*" + re.escape(name) + r"\s*,.*?\);",
                      source, re.S)
    return match[0] if match else ""


class ScreenLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.languages = {
            language: language_phrases(language) for language in ("english", "polski")
        }

    def test_exact_english_source_display_and_voice_labels(self):
        phrases = self.languages["english"][1]
        for identifier, english, polish in LABELS:
            with self.subTest(identifier=identifier):
                self.assertEqual(phrases[identifier],
                                 dict(source=english, dest=english, voice=english))

    def test_exact_polish_display_and_voice_with_english_source(self):
        phrases = self.languages["polski"][1]
        for identifier, english, polish in LABELS:
            with self.subTest(identifier=identifier):
                self.assertEqual(phrases[identifier],
                                 dict(source=english, dest=polish, voice=polish))

    def test_new_ids_are_appended_once_in_matching_order(self):
        expected = [identifier for identifier, english, polish in LABELS[2:]]
        for language, (identifiers, phrases) in self.languages.items():
            with self.subTest(language=language):
                previous_end = identifiers.index("LANG_HIBY_WIFI_SIMULATOR")
                self.assertEqual(identifiers[previous_end + 1:
                                             previous_end + 1 + len(expected)],
                                 expected)
                for identifier in expected:
                    self.assertEqual(identifiers.count(identifier), 1)
                timeout_ids = [identifier for identifier, english, polish in LABELS[:2]]
                self.assertEqual([identifier for identifier in identifiers if identifier in timeout_ids], timeout_ids)
                self.assertGreater(identifiers.index(timeout_ids[0]), identifiers.index(expected[-1]))

    def test_battery_choice_reuses_the_existing_action_label(self):
        for language, (identifiers, phrases) in self.languages.items():
            with self.subTest(language=language):
                self.assertEqual(identifiers.count("LANG_ACCESSIBILITY_BATTERY"), 1)
                self.assertNotIn("LANG_ACCESSIBILITY_ACTION_BATTERY", identifiers)
                expected = ("Speak battery status" if language == "english"
                            else "Wypowiedz stan baterii")
                self.assertEqual(phrases["LANG_ACCESSIBILITY_BATTERY"],
                                 dict(source="Speak battery status",
                                      dest=expected, voice=expected))

    def test_screen_module_references_have_complete_paired_labels(self):
        runtime = read_source("apps/accessibility_screen.c")
        identifiers = set(re.findall(r"\bLANG_ACCESSIBILITY_\w+\b", runtime))
        self.assertTrue(identifiers)
        for identifier in sorted(identifiers):
            for language, (ordered_ids, phrases) in self.languages.items():
                with self.subTest(identifier=identifier, language=language):
                    self.assertTrue(identifier in phrases,
                                    f"{language}: missing screen notice label {identifier}")
                    self.assertEqual(set(phrases[identifier]), {"source", "dest", "voice"})
                    self.assertEqual(phrases[identifier]["dest"],
                                     phrases[identifier]["voice"])
                    self.assertEqual(phrases[identifier]["source"],
                                     self.languages["english"][1][identifier]["source"])


class ScreenMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read_source("apps/menus/settings_menu.c")

    def test_shared_api_header_has_the_softlock_policy_guard(self):
        self.assertRegex(
            self.source,
            r'#if defined\(HAVE_ESPEAK\) && !defined\(HAS_BUTTON_HOLD\)\s*'
            r'#include "accessibility_screen.h"\s*#endif',
        )

    def test_private_policy_editors_use_provided_callbacks_and_usb_returns(self):
        for state in ("unlock", "lock"):
            with self.subTest(state=state):
                self.assertRegex(
                    self.source,
                    rf"MENUITEM_FUNCTION\(accessibility_screen_{state}_item,\s*"
                    rf"MENU_FUNC_CHECK_RETVAL,\s*"
                    rf"ID2P\(LANG_ACCESSIBILITY_SCREEN_{state.upper()}_NOTICE\),\s*"
                    rf"accessibility_screen_{state}_menu,\s*NULL,\s*Icon_Voice\);",
                )

    def test_backlight_settings_keep_their_original_display_owner(self):
        display = read_source("apps/menus/display_menu.c")
        for suffix in ("", "_plugged"):
            with self.subTest(suffix=suffix):
                field = "backlight_timeout" + suffix
                self.assertNotIn("accessibility_screen_backlight" + suffix + "_item", self.source)
                self.assertRegex(
                    display,
                    rf"MENUITEM_SETTING\({field},\s*&global_settings\.{field},\s*NULL\);",
                )

    def test_announcements_menu_contains_only_announcements(self):
        screen = menu_block(self.source, "accessibility_screen_menu")
        self.assertTrue(screen)
        self.assertIn("ID2P(LANG_ACCESSIBILITY_SCREEN_STATE)", screen)
        self.assertEqual(
            re.findall(r"&(\w+)", screen),
            ["accessibility_screen_unlock_item", "accessibility_screen_lock_item"],
        )
        start = self.source.index("MENUITEM_FUNCTION(accessibility_screen_unlock_item,")
        end = self.source.index("MAKE_MENU(voice_settings_menu,", start)
        self.assertEqual(
            re.findall(r"global_settings\.(\w+)", self.source[start:end]),
            [],
        )
        self.assertIn("&sel_softlock", menu_block(self.source, "system_menu"))

    def test_timeout_control_is_with_the_existing_touch_lock_options(self):
        display = read_source("apps/menus/display_menu.c")
        touch = menu_block(display, "touchscreen_menu")
        entries = re.findall(r"&(\w+)", touch)
        self.assertEqual(entries[-4:], ["touchscreen_unlock_any_button_item",
                                      "touchscreen_locked_buttons_item", "touchscreen_autolock_item",
                                      "touchscreen_wake_item"])
        self.assertRegex(display, r"MENUITEM_FUNCTION\(touchscreen_autolock_item,\s*"
                         r"MENU_FUNC_CHECK_RETVAL,\s*ID2P\(LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT\),\s*"
                         r"accessibility_screen_autolock_menu,\s*NULL,\s*Icon_NOICON\);")

    def test_policy_has_no_global_settings_fields_or_plugin_abi_change(self):
        settings = read_source("apps/settings.h")
        structure = settings[settings.index("struct user_settings\n{"):]
        structure = structure[:structure.index("\n};")]
        self.assertNotRegex(structure, POLICY_FIELDS)
        settings_list = read_source("apps/settings_list.c")
        self.assertNotRegex(settings_list, POLICY_FIELDS)
        self.assertNotIn("LANG_ACCESSIBILITY_SCREEN_", settings_list)
        self.assertRegex(read_source("apps/plugin.h"),
                         r"#define\s+PLUGIN_API_VERSION\s+0xe006\b")

    def test_both_guides_cover_indices_shared_timer_and_migration(self):
        for path in ("docs/ACCESSIBILITY-SCREEN.md", "docs/ACCESSIBILITY-SCREEN-PL.md"):
            with self.subTest(path=path):
                guide = read_source(path)
                self.assertEqual(re.findall(r"^\| ([0-5]) \|", guide, re.M),
                                 ["0", "1", "2", "3", "4", "5", "0", "1"])
                for requirement in (
                    "SEL_ACTION_AUTOLOCK", "SEL_ACTION_ALWAYSAUTOLOCK", "ALLOW_SOFTLOCK",
                    "global_settings.backlight_timeout",
                    "global_settings.backlight_timeout_plugged", "HAS_BUTTON_HOLD",
                    "/.rockbox/accessibility-screen.cfg", "RBACCESSIBILITY-SCREEN:1",
                    "accessibility.cfg", "RBACCESSIBILITY:5", "NVDA/UI Automation",
                ):
                    self.assertIn(requirement, guide)


class ScreenMenuPreprocessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            raise unittest.SkipTest("Menu guard matrix requires an existing C preprocessor")
        source = re.sub(r'^\s*#include[^\n]*$', '',
                        read_source("apps/menus/settings_menu.c"), flags=re.M)
        cls.variants = []
        features = ("HAVE_ESPEAK", "HAS_BUTTON_HOLD", "HAVE_TOUCHSCREEN",
                    "HAVE_BACKLIGHT", "CONFIG_CHARGING")
        for values in itertools.product((False, True), repeat=len(features)):
            enabled = dict(zip(features, values))
            definitions = ["-DHIBY_R1=1", "-DHAVE_SCREEN_CURTAIN=1"]
            definitions.extend(f"-D{feature}=1" for feature in features if enabled[feature])
            result = subprocess.run(
                [compiler, "-E", "-P", "-x", "c", *definitions, "-"],
                input=source, text=True, capture_output=True, timeout=20,
            )
            if result.returncode:
                raise AssertionError(f"Preprocessing {enabled}: {result.stderr}")
            cls.variants.append((enabled, result.stdout))

    def test_policy_menu_is_present_only_with_espeak_and_software_lock(self):
        for enabled, source in self.variants:
            with self.subTest(features=enabled):
                expected = enabled["HAVE_ESPEAK"] and not enabled["HAS_BUTTON_HOLD"]
                screen = menu_block(source, "accessibility_screen_menu")
                self.assertEqual(bool(screen), expected)
                voice = menu_block(source, "voice_settings_menu")
                self.assertNotIn("&accessibility_screen_menu", voice)
                display = menu_block(source, "accessibility_display_menu")
                self.assertEqual("&accessibility_screen_menu" in display, expected)
                for state in ("unlock", "lock"):
                    declaration = f"MENUITEM_FUNCTION(accessibility_screen_{state}_item,"
                    self.assertEqual(declaration in source, expected)
                if expected:
                    self.assertTrue(menu_block(source, "sel_softlock"))
                    self.assertNotIn("&sel_softlock", screen)
                    self.assertIn("&sel_softlock", menu_block(source, "system_menu"))

    def test_backlight_and_charging_links_follow_target_capabilities(self):
        for enabled, source in self.variants:
            for suffix in ("", "_plugged"):
                with self.subTest(features=enabled, suffix=suffix):
                    name = "accessibility_screen_backlight" + suffix + "_item"
                    self.assertNotIn(f"MENUITEM_SETTING({name},", source)
                    screen = menu_block(source, "accessibility_screen_menu")
                    self.assertNotIn("&" + name, screen)

    def test_talkbox_first_and_nested_rows_retain_their_order(self):
        for enabled, source in self.variants:
            with self.subTest(features=enabled):
                expected = []
                if enabled["HAVE_ESPEAK"]:
                    expected.append("talkbox_settings_menu")
                    expected.append("accessibility_shortcut_menu")
                nested = []
                if enabled["HAVE_ESPEAK"]:
                    nested.extend(("tts_settings_menu", "tts_enabled_item", "tts_ducking_item",
                                   "tts_ducking_level_item", "tts_reader_settings_menu"))
                if enabled["HAVE_ESPEAK"] and enabled["HAVE_TOUCHSCREEN"]:
                    nested.append("accessibility_touch_item")
                if enabled["HAVE_ESPEAK"] and (not enabled["HAS_BUTTON_HOLD"] or enabled["HAVE_TOUCHSCREEN"]):
                    nested.append("accessibility_display_menu")
                if enabled["HAVE_ESPEAK"] and enabled["HAVE_TOUCHSCREEN"]:
                    nested.append("accessibility_typing_item")
                if enabled["HAVE_ESPEAK"]:
                    nested.extend(("list_boundary_feedback_item", "tts_announce_position_item",
                                   "tts_announce_dynamic_item"))
                expected.extend(("talk_menu_item", "talk_dir_item", "talk_dir_clip_item",
                                 "talk_file_item", "talk_file_clip_item", "talk_filetype_item",
                                 "talk_battery_level_item", "talk_mixer_amp_item"))
                self.assertEqual(re.findall(r"&(\w+)",
                                            menu_block(source, "voice_settings_menu")),
                                 expected)
                self.assertEqual(re.findall(r"&(\w+)", menu_block(source, "talkbox_settings_menu")), nested)
                system = menu_block(source, "system_menu")
                touch_settings = enabled["HAVE_ESPEAK"] and enabled["HAVE_TOUCHSCREEN"]
                self.assertEqual("&touchscreen_menu" in system, touch_settings)
                self.assertEqual("&accessibility_buttons_item" in system, touch_settings)
                self.assertEqual(source.count("&accessibility_shortcut_menu"), int(enabled["HAVE_ESPEAK"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
