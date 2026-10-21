"""Verify complete PL/EN input labels and the requested menu boundaries."""

import re
import unittest

from test_accessibility_connectivity_layout import language_phrases, menu_body, r1_translation, source


class InputRefinementsLabelTests(unittest.TestCase):
    def test_all_input_messages_have_complete_consistent_pl_en_catalogs(self):
        catalogs = {name: language_phrases(name) for name in ("english", "polski")}
        identifiers = set()
        for relative in ("apps/accessibility_touch.c", "apps/accessibility_typing.c",
                         "apps/accessibility_screen.c", "apps/accessibility_shortcut.c",
                         "apps/accessibility.c", "apps/recorder/keyboard.c",
                         "apps/hiby_power.c", "apps/hiby_connectivity.c"):
            identifiers.update(re.findall(r'\bLANG_\w+', source(relative)))
        for identifier in sorted(identifiers):
            if not identifier.startswith(("LANG_ACCESSIBILITY_", "LANG_TOUCH_GESTURE_", "LANG_TTS_", "LANG_KEYCLICK_")) and identifier != "LANG_HIBY_WIFI_INTERFACE_DOWN":
                continue
            with self.subTest(identifier=identifier):
                values = {}
                for name, catalog in catalogs.items():
                    self.assertTrue(identifier in catalog, name + ": " + identifier)
                    values[name] = {part: r1_translation(catalog[identifier], part)
                                    for part in ("source", "dest", "voice")}
                self.assertEqual(values["english"]["source"], values["polski"]["source"], identifier)

    def test_boolean_setting_names_do_not_contain_a_redundant_enable_command(self):
        for name in ("english", "polski"):
            catalog = language_phrases(name)
            for identifier in ("LANG_TTS_ENABLED", "LANG_ACCESSIBILITY_ENABLED",
                               "LANG_KEYCLICK_EMPTY_PITCH", "LANG_ACCESSIBILITY_LOCKED_BUTTONS"):
                for part in ("dest", "voice"):
                    value = r1_translation(catalog[identifier], part).casefold()
                    self.assertNotIn("enable ", value)
                    self.assertNotIn("włącz", value)

    def test_typing_settings_keep_all_modes_and_echo_controls_in_one_submenu(self):
        body = menu_body(source("apps/menus/settings_menu.c"), "accessibility_typing_item")
        self.assertEqual(re.findall(r'&(\w+)', body), ["accessibility_typing_mode_item",
                         "accessibility_typing_echo_item", "accessibility_typing_capitals_item",
                         "accessibility_typing_capital_pitch_item", "accessibility_typing_deletion_item"])

    def test_locked_screen_policy_names_the_allowed_action_in_both_languages(self):
        labels = {
            "english": "Allow physical buttons while the screen is locked",
            "polski": "Pozwalaj na używanie przycisków fizycznych przy zablokowanym ekranie",
        }
        for language, expected in labels.items():
            phrase = language_phrases(language)["LANG_ACCESSIBILITY_LOCKED_BUTTONS"]
            for part in ("dest", "voice"):
                with self.subTest(language=language, part=part):
                    self.assertEqual(r1_translation(phrase, part), expected)

    def test_wraparound_guides_match_actual_labels_and_existing_menu_route(self):
        for language, guide in (("english", "docs/ACCESSIBILITY-LISTS.md"),
                                ("polski", "docs/ACCESSIBILITY-LISTS-PL.md")):
            catalog = language_phrases(language)
            route = " → ".join(r1_translation(catalog[identifier], "dest") for identifier in
                               ("LANG_SETTINGS", "LANG_GENERAL_SETTINGS", "LANG_DISPLAY",
                                "LANG_SCROLL_MENU", "LANG_LIST_WRAPAROUND"))
            with self.subTest(language=language):
                self.assertIn(route, " ".join(source(guide).split()))
        for relative, menu, child in (("apps/menus/main_menu.c", "main_menu_", "settings_menu_item"),
                                      ("apps/menus/settings_menu.c", "settings_menu_item", "display_menu"),
                                      ("apps/menus/display_menu.c", "display_menu", "scroll_settings_menu"),
                                      ("apps/menus/display_menu.c", "scroll_settings_menu", "list_wraparound")):
            with self.subTest(menu=menu):
                self.assertIn("&" + child, menu_body(source(relative), menu))

    def test_scrolling_title_covers_text_and_list_controls_in_both_languages(self):
        body = menu_body(source("apps/menus/display_menu.c"), "scroll_settings_menu")
        for child in ("scroll_speed", "screen_scroll_step", "list_wraparound"):
            self.assertIn("&" + child, body)
        for language, expected in (("english", "Scrolling"), ("polski", "Przewijanie")):
            phrase = language_phrases(language)["LANG_SCROLL_MENU"]
            self.assertEqual(r1_translation(phrase, "source"), "Scrolling")
            for part in ("dest", "voice"):
                with self.subTest(language=language, part=part):
                    self.assertEqual(r1_translation(phrase, part), expected)

    def test_sensitivity_changes_both_gesture_and_typing_thresholds(self):
        self.assertIn("accessibility_touch_distance(", source("apps/accessibility.c"))
        self.assertIn("accessibility_touch_distance(TYPING_TAP_SLOP)", source("apps/accessibility_typing.c"))
        settings = source("apps/menus/display_menu.c")
        self.assertIn("accessibility_touch_sensitivity_menu", settings)


if __name__ == "__main__":
    unittest.main()
