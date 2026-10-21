"""Check the complete Polish/English accessibility vocabulary and stored values."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


def phrases(language):
    result = {}
    for block in re.findall(r"<phrase>(.*?)</phrase>",
                            (ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8"), re.S):
        identifier = re.search(r"\bid:\s*(\w+)", block)
        if not identifier:
            continue
        sections = {}
        for section in ("source", "dest", "voice"):
            contents = re.search(rf"<{section}>(.*?)</{section}>", block, re.S)
            if contents:
                value = re.search(r'\*:\s*"([^"]*)"', contents[1])
                if value:
                    sections[section] = value[1]
        result[identifier[1]] = sections
    return result


class AccessibilityLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.english = phrases("english")
        cls.polish = phrases("polski")

    def assert_label(self, identifier, english, polish):
        self.assertEqual(self.english[identifier], dict(source=english, dest=english, voice=english))
        self.assertEqual(self.polish[identifier], dict(source=english, dest=polish, voice=polish))

    def test_system_language_is_a_label_not_a_new_serialized_value(self):
        self.assert_label("LANG_TTS_SYSTEM", "Follow system language", "Zgodny z systemem")
        settings = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
        self.assertRegex(settings, r'tts_language[^\n]*"system"')
        runtime = (ROOT / "apps/tts.c").read_text(encoding="utf-8")
        self.assertIn('"system"', runtime)
        self.assertIn("LANG_TTS_SYSTEM", runtime)

    def test_accessibility_menu_names(self):
        self.assert_label("LANG_VOICE", "Accessibility", "Dostępność")
        self.assert_label("LANG_TALKBOX_SETTINGS", "Talkbox settings", "Ustawienia Talkbox")
        self.assert_label("LANG_TTS", "eSpeak settings", "Ustawienia eSpeak")
        self.assert_label("LANG_ACCESSIBILITY", "Touch exploration settings", "Ustawienia przeglądania dotykowego")
        self.assert_label("LANG_ACCESSIBILITY_BUTTONS", "Physical button settings", "Ustawienia przycisków fizycznych")
        self.assert_label("LANG_ACCESSIBILITY_ENABLED", "Explore by touch", "Przeglądanie dotykowe")
        self.assert_label("LANG_ACCESSIBILITY_DISPLAY_SETTINGS", "Screen settings", "Ustawienia ekranu")

    def test_touch_wake_and_radio_states_have_complete_matching_vocabulary(self):
        for identifier, english, polish in (
            ("LANG_TOUCH_WAKE_SETTINGS", "Wake and unlock screen", "Wybudzanie i odblokowywanie ekranu"),
            ("LANG_TOUCH_WAKE_SINGLE", "One tap", "Jedno stuknięcie"),
            ("LANG_TOUCH_WAKE_DOUBLE", "Two taps", "Dwukrotne stuknięcie"),
            ("LANG_TOUCH_WAKE_TRIPLE", "Three taps", "Trzykrotne stuknięcie"),
            ("LANG_TOUCH_WAKE_LIGHT", "Only turn on backlight", "Tylko włącz podświetlenie"),
            ("LANG_TOUCH_WAKE_UNLOCK", "Wake and unlock screen", "Wybudź i odblokuj ekran"),
            ("LANG_HIBY_CONNECTIVITY_ADMIN_OFF", "Disabled in software", "Wyłączone programowo"),
            ("LANG_HIBY_CONNECTIVITY_ADMIN_ON", "Enabled in software", "Włączone programowo"),
        ):
            with self.subTest(identifier=identifier):
                self.assert_label(identifier, english, polish)

    def test_physical_button_contexts_have_distinct_complete_labels(self):
        from test_accessibility_connectivity_layout import language_phrases
        self.assert_label("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", "Interface actions", "Akcje w interfejsie")
        self.assert_label("LANG_ACCESSIBILITY_PLAYBACK_ACTIONS", "Playback screen actions", "Akcje na ekranie odtwarzania")
        for language, catalog in (("english", self.english), ("polski", self.polish)):
            system_phrase = language_phrases(language)["LANG_TOUCHSCREEN_SETTINGS"]
            system_name = re.search(r'<dest>.*?\btouchscreen:\s*"([^"\n]+)"', system_phrase, re.S)
            self.assertIsNotNone(system_name)
            self.assertNotEqual(catalog["LANG_ACCESSIBILITY"]["dest"], system_name[1])

    def test_all_swipes_have_explicit_complete_labels(self):
        directions = {"LEFT": ("left", "lewo"), "RIGHT": ("right", "prawo"),
                      "UP": ("up", "górę"), "DOWN": ("down", "dół")}
        for first, (english, polish) in directions.items():
            self.assert_label("LANG_ACCESSIBILITY_SWIPE_" + first,
                              "Swipe " + english, "Przesunięcie w " + polish)
            for second, (next_english, next_polish) in directions.items():
                if first != second:
                    self.assert_label(f"LANG_ACCESSIBILITY_SWIPE_{first}_{second}",
                                      f"Swipe {english}, then {next_english}",
                                      f"Przesunięcie w {polish}, a potem w {next_polish}")

    def test_input_sound_sources(self):
        for suffix, english, polish in (
            ("SOURCES", "Interface sounds for", "Dźwięki interfejsu dla"),
            ("NONE", "None", "Brak"),
            ("BOTH", "Physical buttons and gestures", "Przyciski fizyczne i gesty"),
            ("PHYSICAL", "Physical buttons only", "Tylko przyciski fizyczne"),
            ("GESTURES", "Gestures only", "Tylko gesty"),
            ("EXPLORATION", "Screen exploration only", "Tylko eksploracja ekranu"),
            ("PHYSICAL_EXPLORATION", "Buttons and exploration", "Przyciski i eksploracja"),
            ("GESTURES_EXPLORATION", "Gestures and exploration", "Gesty i eksploracja"),
            ("ALL", "All inputs", "Wszystkie"),
        ):
            self.assert_label("LANG_KEYCLICK_" + suffix, english, polish)

    def test_assignment_directions_are_explicit_arrow_actions(self):
        for suffix, english, polish in (
            ("UP", "Up arrow", "Strzałka w górę"),
            ("DOWN", "Down arrow", "Strzałka w dół"),
            ("LEFT", "Left arrow", "Strzałka w lewo"),
            ("RIGHT", "Right arrow", "Strzałka w prawo"),
        ):
            self.assert_label("LANG_ACCESSIBILITY_" + suffix, english, polish)
        source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        actions = source[source.index("static const int action_labels["):]
        actions = actions[:actions.index("};")]
        self.assertNotRegex(actions, r'\bLANG_(LEFT|RIGHT)\b')

    def test_espeak_is_first_and_touch_buttons_are_separate(self):
        source = (ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
        menu = source[source.index("MAKE_MENU(voice_settings_menu,"):]
        menu = menu[:menu.index(");")]
        self.assertLess(menu.index("&talkbox_settings_menu"), menu.index("&accessibility_shortcut_menu"))
        self.assertNotIn("&tts_settings_menu", menu)
        self.assertNotIn("&accessibility_touch_item", menu)
        self.assertNotIn("&accessibility_buttons_item", menu)
        talkbox = source[source.index("MAKE_MENU(talkbox_settings_menu,"):]
        talkbox = talkbox[:talkbox.index(");")]
        self.assertRegex(talkbox, r'ID2P\(LANG_TALKBOX_SETTINGS\),\s*0, Icon_Voice,\s*&tts_settings_menu,')
        self.assertLess(talkbox.index("&tts_settings_menu"), talkbox.index("&accessibility_touch_item"))
        self.assertNotIn("&accessibility_shortcut_menu", talkbox)
        self.assertNotIn("&talk_menu_item", talkbox)
        engine = source[source.index("MAKE_MENU(tts_settings_menu,"):]
        engine = engine[:engine.index(");")]
        self.assertRegex(engine, r'ID2P\(LANG_TTS\),\s*0, Icon_Voice,')
        system = source[source.index("MAKE_MENU(system_menu,"):]
        system = system[:system.index(");")]
        self.assertLess(system.index("&touchscreen_menu"), system.index("&accessibility_buttons_item"))
        self.assertLess(system.index("&accessibility_buttons_item"), system.index("&keyclick_menu"))
        self.assertIn("accessibility_keyclick_menu", source)

    def test_all_input_action_labels_have_paired_spoken_translations(self):
        source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        identifiers = set(re.findall(r'\bLANG_(?:ACCESSIBILITY|KEYCLICK)_[A-Z_]+\b', source))
        self.assertTrue(identifiers)
        for identifier in identifiers:
            with self.subTest(identifier=identifier):
                self.assertTrue(identifier in self.english, identifier + " missing from English")
                self.assertTrue(identifier in self.polish, identifier + " missing from Polish")
                english, polish = self.english[identifier], self.polish[identifier]
                self.assertEqual(english["source"], english["dest"])
                self.assertEqual(english["dest"], english["voice"])
                self.assertEqual(english["source"], polish["source"])
                self.assertEqual(polish["dest"], polish["voice"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
