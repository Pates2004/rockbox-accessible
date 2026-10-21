"""Check menu integration, complete service labels and clean-package policy."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def menu_body(text, name):
    match = re.search(r"\bMAKE_MENU\(" + re.escape(name) + r",.*?\);", text, re.S)
    if not match:
        raise AssertionError("Missing menu: " + name)
    return match.group(0)


def language_phrases(name):
    text = source("apps/lang/" + name + ".lang")
    return {
        match.group(1): match.group(0)
        for match in re.finditer(r"<phrase>\s+id:\s+(\w+)\s+.*?</phrase>", text, re.S)
    }


def r1_translation(phrase, section):
    block = re.search(r"<" + section + r">(.*?)</" + section + r">", phrase, re.S)
    if not block:
        raise AssertionError("Missing language section: " + section)
    values = dict(re.findall(r"^\s*([^:\n]+):\s*(\"[^\"\n]*\"|none)\s*$",
                             block.group(1), re.M))
    value = values.get("hibyr1", values.get("*"))
    if not value or value == "none":
        raise AssertionError("Missing R1 translation: " + section)
    return value[1:-1]


class AccessibilityConnectivityLayoutTests(unittest.TestCase):
    def test_target_specific_language_overrides_none_fallback(self):
        self.assertEqual(r1_translation('<voice>\n *: none\n hibyr1: "R1"\n</voice>',
                                        "voice"), "R1")
        with self.assertRaisesRegex(AssertionError, "Missing R1 translation"):
            r1_translation('<voice>\n *: none\n sansaclipzip: "Zip"\n</voice>', "voice")

    def test_connectivity_is_a_settings_child_not_a_general_or_system_child(self):
        main = source("apps/menus/main_menu.c")
        settings = source("apps/menus/settings_menu.c")
        self.assertIn("&connectivity_item,", menu_body(main, "main_menu_"))
        self.assertRegex(main, r"MENUITEM_FUNCTION\(connectivity_item,\s*MENU_FUNC_CHECK_RETVAL,"
                              r"\s*ID2P\(LANG_CONNECTIVITY\), hiby_connectivity_menu")
        self.assertNotIn("hiby_bluetooth_item", settings)
        self.assertNotIn("hiby_wifi_status", settings)
        self.assertNotIn("connectivity_item", menu_body(settings, "settings_menu_item"))
        self.assertNotIn("connectivity_item", menu_body(settings, "system_menu"))

    def test_existing_settings_sibling_order_is_preserved(self):
        body = menu_body(source("apps/menus/main_menu.c"), "main_menu_")
        siblings = ("sound_settings", "playback_settings", "settings_menu_item",
                    "theme_menu", "connectivity_item", "recording_settings",
                    "timedate_item", "main_menu_config_item", "manage_settings")
        offsets = [body.index("&" + sibling) for sibling in siblings]
        self.assertEqual(offsets, sorted(offsets))

    def test_talkbox_is_first_and_keeps_screen_reader_controls_separate(self):
        text = source("apps/menus/settings_menu.c")
        body = menu_body(text, "voice_settings_menu")
        siblings = ("talkbox_settings_menu", "accessibility_shortcut_menu",
                    "talk_menu_item", "talk_dir_item",
                    "talk_dir_clip_item", "talk_file_item", "talk_file_clip_item",
                    "talk_filetype_item", "talk_battery_level_item", "talk_mixer_amp_item")
        offsets = [body.index("&" + sibling + ",") for sibling in siblings[:-1]]
        offsets.append(body.index("&" + siblings[-1] + ")"))
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(re.findall(r"&(\w+)", body), list(siblings))
        self.assertEqual(re.findall(r"&(\w+)", menu_body(text, "talkbox_settings_menu")), [
            "tts_settings_menu", "tts_enabled_item", "tts_ducking_item", "tts_ducking_level_item",
            "tts_reader_settings_menu", "accessibility_touch_item", "accessibility_display_menu",
            "accessibility_typing_item", "list_boundary_feedback_item", "tts_announce_position_item",
            "tts_announce_dynamic_item"])
        self.assertEqual(re.findall(r"&(\w+)", menu_body(text, "tts_settings_menu")), [
            "tts_language_item", "tts_variant_item", "tts_rate_item", "tts_rate_scale_item",
            "tts_pitch_item", "tts_volume_item", "tts_range_item", "tts_wordgap_item", "tts_punctuation_item"])

    def test_grouped_shortcut_has_one_menu_and_keeps_individual_service_actions(self):
        text = source("apps/menus/settings_menu.c")
        self.assertEqual(text.count("MAKE_MENU(accessibility_shortcut_menu,"), 1)
        self.assertEqual(menu_body(text, "voice_settings_menu").count("&accessibility_shortcut_menu,"), 1)
        self.assertIn("&accessibility_shortcut_services_menu", menu_body(text, "accessibility_shortcut_menu"))
        controls = source("apps/accessibility.c")
        self.assertIn("accessibility_services_activate();", controls)
        self.assertIn("accessibility_shortcut_toggle_espeak();", controls)
        self.assertIn("accessibility_shortcut_toggle_voice_files();", controls)

    def test_physical_and_general_touch_settings_are_system_children(self):
        text = source("apps/menus/settings_menu.c")
        system = menu_body(text, "system_menu")
        self.assertEqual(system.count("&accessibility_buttons_item"), 1)
        self.assertEqual(system.count("&touchscreen_menu"), 1)
        self.assertLess(system.index("&touchscreen_menu"), system.index("&accessibility_buttons_item"))
        self.assertLess(system.index("&accessibility_buttons_item"), system.index("&keyclick_menu"))
        accessibility = menu_body(text, "voice_settings_menu")
        self.assertNotIn("accessibility_buttons_item", accessibility)
        display = source("apps/menus/display_menu.c")
        self.assertIn("#if defined(HAVE_TOUCHSCREEN) && !defined(HAVE_ESPEAK)", display)
        touch = menu_body(display, "touchscreen_menu")
        for item in ("touchscreen_sensitivity_item", "touchscreen_unlock_any_button_item", "touchscreen_locked_buttons_item"):
            self.assertEqual(touch.count("&" + item), 1)

    def test_old_startup_diagnostic_is_retained_only_in_debug_menu(self):
        debug = source("apps/debug_menu.c")
        self.assertIn("{ ID2P(LANG_HIBY_WIFI_STARTUP), hiby_wifi_startup_debug }", debug)
        self.assertIn("return hiby_power_status_menu() != 0;", debug)
        self.assertNotIn("LANG_HIBY_WIFI_STARTUP", source("apps/menus/settings_menu.c"))

    def test_startup_policy_follows_audio_and_shutdown_precedes_audio_teardown(self):
        main = source("apps/main.c")
        policy = main.index("hiby_connectivity_apply_startup_policy();")
        audio = main.rfind("audio_init();", 0, policy)
        self.assertGreaterEqual(audio, 0)
        self.assertNotIn("}", main[audio:policy])
        self.assertIn("#if defined(HIBY_R1) && defined(HAVE_ESPEAK)", main[audio:policy])
        misc = source("apps/misc.c")
        controller = misc.index("hiby_connectivity_shutdown();")
        bluetooth = misc.index("hiby_bluetooth_shutdown();")
        pcm = misc.index("hiby_pcm_shutdown();")
        self.assertLess(controller, bluetooth)
        self.assertLess(bluetooth, pcm)

    def test_all_new_core_labels_have_matching_pl_en_source_and_spoken_destinations(self):
        english = language_phrases("english")
        polish = language_phrases("polski")
        required = set()
        for relative in ("apps/accessibility_shortcut.c", "apps/hiby_connectivity.c",
                         "apps/hiby_bluetooth.c", "apps/accessibility.c"):
            required.update(re.findall(r"\bLANG_\w+", source(relative)))
        required.update(("LANG_CONNECTIVITY", "LANG_ACCESSIBILITY_SHORTCUT_ACTIVATE"))
        for identifier in sorted(required):
            with self.subTest(identifier=identifier):
                self.assertTrue(identifier in english, "Missing English phrase: " + identifier)
                self.assertTrue(identifier in polish, "Missing Polish phrase: " + identifier)
                sections = []
                for language in (english, polish):
                    phrase = language[identifier]
                    values = {}
                    for section in ("source", "dest", "voice"):
                        values[section] = r1_translation(phrase, section)
                        self.assertTrue(values[section], identifier + ": " + section)
                    sections.append(values)
                self.assertEqual(sections[0]["source"], sections[1]["source"])

    def test_rockbox_info_brand_is_correct_visually_and_when_spoken(self):
        phrase = language_phrases("polski")["LANG_ROCKBOX_INFO"]
        for section in ("dest", "voice"):
            self.assertRegex(phrase, r"<" + section + r">\s*\*:\s*\"Informacje Rockboxa\"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
