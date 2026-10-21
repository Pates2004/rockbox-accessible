"""Exercise real profile migration, menus and independently pending physical keys."""

import os
import ctypes
import hashlib
import json
import re
import subprocess
import unittest

import test_accessibility_settings as core


class AccessibilityContextProfilesTests(unittest.TestCase):
    setUpClass = classmethod(core.AccessibilitySettingsTests.setUpClass.__func__)
    tearDownClass = classmethod(core.AccessibilitySettingsTests.tearDownClass.__func__)
    setUp = core.AccessibilitySettingsTests.setUp
    constant = core.AccessibilitySettingsTests.constant
    parse = core.AccessibilitySettingsTests.parse
    script = core.AccessibilitySettingsTests.script

    def context(self, playback=False):
        return self.constant("CONTEXT_WPS" if playback else "CONTEXT_STD")

    def install(self, value):
        self.library.probe_disk(value, len(value))
        self.library.probe_reload()

    def click(self, raw, start=0, playback=False, locked=False):
        context = self.context(playback)
        pressed = self.library.probe_button(raw, start, context, locked)
        released = self.library.probe_button(raw | 0x2000000, start + 50, context, locked)
        return pressed, released

    def button_with_touch_idle(self, raw, milliseconds, playback=False):
        context = self.context(playback)
        self.library.accessibility_cancel_touch()
        result = self.library.probe_button(raw, milliseconds, context, False)
        self.library.probe_button(0, milliseconds + 10, context, False)
        self.library.probe_poll(milliseconds + 10, context)
        return result

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_touch_idle_preserves_double_and_triple_physical_presses_in_both_profiles(self):
        for enabled in (False, True):
            for playback in (False, True):
                for clicks in (2, 3):
                    with self.subTest(enabled=enabled, playback=playback, clicks=clicks):
                        self.setUp()
                        mappings = {(0, 1): self.constant("ACCESSIBILITY_ACTION_TIME"),
                                    (0, 2): self.constant("ACCESSIBILITY_ACTION_BATTERY")}
                        self.install(core.default_config(enabled=int(enabled), buttons=mappings,
                                                         playback_buttons=mappings))
                        for index in range(clicks):
                            self.button_with_touch_idle(1, index * 150, playback)
                            self.button_with_touch_idle(1 | 0x2000000, index * 150 + 50, playback)
                        self.library.probe_button(0, clicks * 150 + 400, self.context(playback), False)
                        self.assertEqual(self.library.probe_time_calls(), int(clicks == 2))
                        self.assertEqual(self.library.probe_battery_reads(), int(clicks == 3))

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_touch_idle_preserves_physical_hold_and_repeat(self):
        for playback in (False, True):
            with self.subTest(playback=playback):
                self.setUp()
                mappings = {(0, 3): self.constant("ACCESSIBILITY_ACTION_VOLUP")}
                self.install(core.default_config(enabled=1, hold=700, buttons=mappings,
                                                 playback_buttons=mappings))
                expected = self.constant("ACTION_WPS_VOLUP" if playback else "ACTION_LIST_VOLUP")
                self.button_with_touch_idle(1, 0, playback)
                self.assertEqual(self.button_with_touch_idle(1 | 0x4000000, 800, playback), expected)
                self.assertEqual(self.button_with_touch_idle(1 | 0x4000000, 1000, playback), expected)
                self.assertNotEqual(self.button_with_touch_idle(1 | 0x2000000, 1050, playback), expected)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_real_touch_contact_still_cancels_a_pending_physical_hold(self):
        self.install(core.default_config(enabled=1, hold=700,
                                         buttons={(0, 3): self.constant("ACCESSIBILITY_ACTION_VOLUP")}))
        unexpected = self.constant("ACTION_LIST_VOLUP")
        self.library.probe_button(1, 0, self.context(), False)
        self.library.probe_touch(self.constant("TOUCHEVENT_PRESS"), 20, 20, 100, self.context())
        self.assertNotEqual(self.library.probe_button(1 | 0x4000000, 800, self.context(), False), unexpected)
        self.assertNotEqual(self.library.probe_button(1 | 0x2000000, 850, self.context(), False), unexpected)

    def test_all_historical_versions_copy_maps_references_and_preserve_file_until_save(self):
        for version, maximum in core.VERSION_ACTION_LIMITS.items():
            if version >= 9:
                continue
            with self.subTest(version=version):
                self.setUp()
                mappings = {(button, slot): (button * 4 + slot) % (maximum + 2)
                            for button in range(5) for slot in range(4)}
                references = {}
                if version >= 3:
                    mappings[1, 0] = 12
                    references[1, 0] = 4
                    mappings[4, 3] = 12
                    references[4, 3] = 7
                value = core.default_config(version=version, enabled=0, clicks=1, hold=1200,
                    buttons=mappings, button_refs=references, paths={
                        0: "/.rockbox/rocks/apps/one.rock", 3: "/.rockbox/rocks/apps/two.rock"})
                self.install(value)
                self.assertEqual(self.library.probe_stat(2), 0)
                self.assertEqual(self.library.probe_disk_content(), value)
                for button in range(5):
                    for slot in range(4):
                        self.assertEqual(self.library.probe_playback_mapping(button, slot),
                                         self.library.probe_button_mapping(button, slot))
                        self.assertEqual(self.library.probe_playback_ref(button, slot),
                                         self.library.probe_ref(button, slot))
                self.assertEqual(self.library.probe_save(), 1)
                saved = self.library.probe_disk_content()
                self.assertTrue(saved.startswith(b"RBACCESSIBILITY:11\n"))
                self.assertEqual(self.parse(saved), 1)
                self.library.probe_reload()
                self.assertEqual(self.library.probe_disk_content(), saved)
                for button in range(5):
                    for slot in range(4):
                        self.assertEqual(self.library.probe_playback_mapping(button, slot),
                                         self.library.probe_button_mapping(button, slot))

    def test_v9_round_trip_keeps_independent_maps_and_launch_references(self):
        value = core.default_config(enabled=0, clicks=0, hold=1500, empty_pitch=0,
            empty_semitones=11, buttons={(1, 0): 12, (2, 3): 1},
            button_refs={(1, 0): 4}, playback_buttons={(1, 0): 12, (2, 3): 2},
            playback_refs={(1, 0): 7}, paths={0: "/.rockbox/rocks/apps/interface.rock",
                3: "/.rockbox/rocks/apps/playback.rock"})
        self.install(value)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_button_mapping(2, 3), 1)
        self.assertEqual(self.library.probe_playback_mapping(2, 3), 2)
        self.assertEqual(self.library.probe_ref(1, 0), 4)
        self.assertEqual(self.library.probe_playback_ref(1, 0), 7)
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_disk_content(), value)

    def test_bool_bindings_match_real_header_and_false_is_not_a_garbage_upper_register(self):
        header = self.source_bytes["apps/accessibility.h"].decode("utf-8")
        for name in re.findall(r'^bool\s+(accessibility_[a-z_]+)\s*\(', header, re.MULTILINE):
            self.assertIs(getattr(self.library, name).restype, ctypes.c_bool, name)
        self.library.probe_enable(False)
        self.assertIs(self.library.accessibility_enabled(), False)
        self.library.probe_enable(True)
        self.assertIs(self.library.accessibility_enabled(), True)

    def test_v9_rejects_truncation_duplicates_unordered_rows_and_wrong_references(self):
        value = core.default_config(playback_buttons={(4, 3): 12},
            playback_refs={(4, 3): 4}, paths={0: "/.rockbox/rocks/apps/playback.rock"})
        self.assertEqual(self.parse(value), 1)
        start = value.index(b"playback_button:")
        end = value.index(b"target:")
        for length in range(start, end + 1):
            with self.subTest(length=length):
                self.assertEqual(self.parse(value[:length]), 0)
        invalid = [value.replace(b"playback_button:1:0:", b"playback_button:0:0:"),
                   value.replace(b"playback_button:4:3:12:4", b"playback_button:4:3:23:4"),
                   value.replace(b"playback_button:4:3:12:4", b"playback_button:4:3:11:4"),
                   value.replace(b"playback_button:4:3:12:4", b"playback_button:4:3:12:13"),
                   value.replace(b"playback_button:4:3:12:4", b"playback_button:4:3:12:04"),
                   value.replace(b"target:0:/.rockbox/rocks/apps/playback.rock", b"target:0:"),
                   value[:end] + value[start:end] + value[end:], value + b"\n"]
        for malformed in invalid:
            self.assertEqual(self.parse(malformed), 0, malformed[-150:])

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_profile_menus_edit_reselect_and_reset_one_without_changing_the_other(self):
        for playback in (False, True):
            self.setUp()
            self.script([int(playback), 4, -1, -1], choice=11)
            self.assertEqual(self.library.accessibility_buttons_menu(), 0)
            self.assertEqual(self.library.probe_playback_mapping(1, 0), 11 if playback else 27)
            self.assertEqual(self.library.probe_button_mapping(1, 0), 27 if playback else 11)
            self.library.probe_reload()
            self.script([int(playback), 4, -1, -1], choice=11)
            writes = self.library.probe_stat(2)
            self.assertEqual(self.library.accessibility_buttons_menu(), 0)
            self.assertEqual(self.library.probe_option_initial_choice(), 11)
            self.assertEqual(self.library.probe_stat(2), writes)
            self.script([int(not playback), 8, -1, -1], choice=self.library.input_action_index(16))
            self.assertEqual(self.library.accessibility_buttons_menu(), 0)
            self.script([int(playback), 20, -1, -1])
            self.assertEqual(self.library.accessibility_buttons_menu(), 0)
            self.assertEqual(self.library.probe_playback_mapping(2, 0), 27 if playback else 16)
            self.assertEqual(self.library.probe_button_mapping(2, 0), 16 if playback else 27)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_only_actual_wps_selects_playback_not_menu_settings_or_keyboard(self):
        self.install(core.default_config(buttons={(1, 0): 11}, playback_buttons={(1, 0): 16}))
        for context in ("CONTEXT_STD", "CONTEXT_MAINMENU", "CONTEXT_SETTINGS", "CONTEXT_KEYBOARD"):
            self.library.accessibility_reset()
            reads = self.library.probe_battery_reads()
            self.library.probe_button(8, 0, self.constant(context), False)
            self.library.probe_button(8 | 0x2000000, 50, self.constant(context), False)
            self.assertEqual(self.library.probe_battery_reads(), reads + 1, context)
        before = self.library.probe_time_calls()
        for flag in (0, self.constant("CONTEXT_REMAPPED"), self.constant("CONTEXT_REMOTE")):
            self.library.accessibility_reset()
            context = self.context(True) | flag
            self.library.probe_button(8, 1000, context, False)
            self.library.probe_button(8 | 0x2000000, 1050, context, False)
        self.assertEqual(self.library.probe_time_calls(), before + 3)
        self.library.accessibility_reset()
        context = self.context(True) | self.constant("CONTEXT_CUSTOM")
        reads = self.library.probe_battery_reads()
        self.library.probe_button(8, 2000, context, False)
        self.library.probe_button(8 | 0x2000000, 2050, context, False)
        self.assertEqual(self.library.probe_battery_reads(), reads + 1)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_each_profile_single_double_triple_hold_and_none_keep_independent_semantics(self):
        for playback in (False, True):
            for slot in range(4):
                with self.subTest(playback=playback, slot=slot):
                    self.setUp()
                    self.install(core.default_config(buttons={(1, slot): 11},
                                                     playback_buttons={(1, slot): 16}))
                    if slot == 3:
                        self.library.probe_button(8, 0, self.context(playback), False)
                        self.library.probe_button(0, 700, self.context(playback), False)
                        self.library.probe_button(8 | 0x4000000, 800, self.context(playback), False)
                        self.library.probe_button(8 | 0x2000000, 850, self.context(playback), False)
                    else:
                        for click in range(slot + 1):
                            self.click(8, click * 100, playback)
                    self.library.probe_button(0, 1300, self.context(playback), False)
                    self.assertEqual(self.library.probe_time_calls(), int(playback))
                    self.assertEqual(self.library.probe_battery_reads(), int(not playback))
            for slot in (1, 2):
                self.setUp()
                self.install(core.default_config(buttons={(1, 0): 11, (1, slot): 0},
                    playback_buttons={(1, 0): 16, (1, slot): 0}))
                for click in range(slot + 1):
                    self.click(8, click * 100, playback)
                self.library.probe_button(0, 1300, self.context(playback), False)
                self.assertEqual(self.library.probe_time_calls(), 0)
                self.assertEqual(self.library.probe_battery_reads(), 0)
                self.assertEqual(self.library.probe_default_button_calls(), 0)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_native_other_button_does_not_discard_pending_custom_click(self):
        for playback in (False, True):
            self.setUp()
            self.install(core.default_config(buttons={(1, 0): 16, (1, 1): 11},
                                            playback_buttons={(1, 0): 16, (1, 1): 11}))
            self.click(8, 0, playback)
            self.assertEqual(self.click(16, 100, playback), (-1, -1))
            self.assertEqual(self.library.probe_time_calls(), 0)
            self.library.probe_button(0, 350, self.context(playback), False)
            self.assertEqual(self.library.probe_time_calls(), 1)
            self.assertEqual(self.library.probe_battery_reads(), 0)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_rapid_alternating_custom_buttons_retain_both_independent_multiclicks(self):
        for playback in (False, True):
            self.setUp()
            mappings = {(1, 0): 16, (1, 1): 11, (2, 0): 11, (2, 1): 16}
            self.install(core.default_config(buttons=mappings, playback_buttons=mappings))
            self.click(8, 0, playback)
            self.click(4, 80, playback)
            self.click(8, 160, playback)
            self.click(4, 240, playback)
            self.library.probe_button(0, 1000, self.context(playback), False)
            self.assertEqual(self.library.probe_battery_reads(), 1)
            self.assertEqual(self.library.probe_time_calls(), 1)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_hold_after_clicks_does_not_execute_an_earlier_action_during_regular_polls(self):
        for playback in (False, True):
            for clicks in (1, 2):
                with self.subTest(playback=playback, clicks=clicks):
                    self.setUp()
                    mappings = {(1, 0): 11, (1, 1): 11, (1, 2): 11, (1, 3): 16}
                    self.install(core.default_config(buttons=mappings, playback_buttons=mappings))
                    for index in range(clicks):
                        self.click(8, index * 100, playback)
                    pressed_at = clicks * 100
                    self.library.probe_button(8, pressed_at, self.context(playback), False)
                    for now in range(pressed_at + 50, pressed_at + 700, 50):
                        self.library.probe_button(0, now, self.context(playback), False)
                        self.assertEqual(self.library.probe_battery_reads(), 0, now)
                        self.assertEqual(self.library.probe_time_calls(), 0, now)
                    self.library.probe_button(0, pressed_at + 700, self.context(playback), False)
                    self.assertEqual(self.library.probe_time_calls(), 1)
                    self.library.probe_button(8 | 0x2000000, pressed_at + 750,
                                              self.context(playback), False)
                    self.library.probe_button(0, pressed_at + 1100, self.context(playback), False)
                    self.assertEqual(self.library.probe_battery_reads(), 0)
                    self.assertEqual(self.library.probe_time_calls(), 1)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_context_and_lock_changes_cancel_pending_and_consume_old_contact(self):
        for mapped in (False, True):
            for source, target in ((False, True), (True, False)):
                self.setUp()
                mappings = {(1, 0): 11} if mapped else {}
                self.install(core.default_config(buttons=mappings, playback_buttons=mappings))
                self.library.probe_button(8, 0, self.context(source), False)
                self.library.probe_button(0, 500, self.context(target), False)
                self.assertEqual(self.library.probe_button(8 | 0x4000000, 700,
                    self.context(target), False), self.constant("ACTION_UNKNOWN"))
                self.assertEqual(self.library.probe_button(8 | 0x2000000, 800,
                    self.context(target), False), self.constant("ACTION_UNKNOWN"))
                self.assertEqual(self.library.probe_battery_reads(), 0)
                self.click(8, 1000, target)
                self.assertEqual(self.library.probe_battery_reads(), int(mapped))
        self.setUp()
        self.install(core.default_config(buttons={(1, 0): 11, (1, 1): 16}))
        self.click(8)
        self.library.probe_button(0, 500, self.context(), True)
        self.assertEqual(self.library.probe_battery_reads(), 0)
        self.assertEqual(self.library.probe_time_calls(), 0)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_failed_atomic_profile_save_preserves_both_active_profiles_and_old_file(self):
        for fault in (4, 5, 6, 7, 8, 9, 10):
            self.setUp()
            value = core.default_config(buttons={(1, 0): 11}, playback_buttons={(1, 0): 16})
            self.install(value)
            self.library.probe_chunks(3, 3)
            self.library.probe_fault(fault)
            self.script([1, 4, -1, -1], choice=8)
            self.assertEqual(self.library.accessibility_buttons_menu(), 0)
            self.assertEqual(self.library.probe_button_mapping(1, 0), 11)
            self.assertEqual(self.library.probe_playback_mapping(1, 0), 16)
            self.assertEqual(self.library.probe_disk_content(), value)

    def test_touch_reset_preserves_both_profiles_and_paths_used_only_by_playback(self):
        value = core.default_config(replacements={1: 8}, hold=1600, clicks=2,
            buttons={(1, 0): 11}, playback_buttons={(1, 0): 12},
            playback_refs={(1, 0): 7}, paths={3: "/.rockbox/rocks/apps/playback.rock"})
        self.install(value)
        self.script([7, -1])
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        self.assertEqual(self.library.probe_mapping(1), 1)
        self.assertEqual(self.library.probe_button_mapping(1, 0), 11)
        self.assertEqual(self.library.probe_playback_mapping(1, 0), 12)
        self.assertEqual(self.library.probe_playback_ref(1, 0), 7)
        self.assertEqual(self.library.probe_path(3), b"/.rockbox/rocks/apps/playback.rock")
        self.assertEqual(self.library.probe_extra(5), 1600)
        self.assertEqual(self.library.accessibility_keyclick_sources(), 2)
        self.assertEqual(self.library.probe_save(), 1)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_reset_interface_retains_playback_only_launch_and_root_reset_clears_both(self):
        self.install(core.default_config(buttons={(1, 0): 11}, playback_buttons={(2, 0): 12},
            playback_refs={(2, 0): 4}, paths={0: "/.rockbox/rocks/apps/playback.rock"}))
        self.script([0, 20, -1, -1])
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_playback_mapping(2, 0), 12)
        self.assertEqual(self.library.probe_path(0), b"/.rockbox/rocks/apps/playback.rock")
        self.script([3, -1])
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_playback_mapping(2, 0), 27)
        self.assertEqual(self.library.probe_button_mapping(1, 0), 27)
        self.assertEqual(self.library.probe_path(0), b"")

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_full_plugin_pool_replacement_deduplication_and_resets_cover_both_profiles(self):
        paths = {index: f"/.rockbox/rocks/apps/shared{index}.rock" for index in range(4)}
        self.install(core.default_config(replacements={1: 12, 2: 12},
            gesture_refs={1: 4, 2: 5}, buttons={(1, 0): 12}, button_refs={(1, 0): 6},
            playback_buttons={(1, 0): 12}, playback_refs={(1, 0): 7}, paths=paths))
        replacement = b"/.rockbox/rocks/apps/replacement.rock"
        self.library.probe_launcher(1, replacement, 0)
        self.script([0, 4, -1, -1], choice=12)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_ref(1, 0), 6)
        self.assertEqual(self.library.probe_path(2), replacement)
        self.assertEqual(self.library.probe_playback_ref(1, 0), 7)
        self.assertEqual(self.library.probe_path(3), paths[3].encode())
        self.library.probe_launcher(1, replacement, 0)
        self.script([1, 4, -1, -1], choice=12)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_playback_ref(1, 0), 6)
        self.assertEqual(self.library.probe_path(3), b"")
        self.script([0, 20, -1, -1])
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_path(2), replacement)
        self.script([3, -1])
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_path(2), b"")
        for index in range(2):
            self.assertEqual(self.library.probe_path(index), paths[index].encode())
        self.library.probe_reload()
        self.assertEqual(self.library.probe_playback_mapping(1, 0), 27)
        self.assertEqual(self.library.probe_button_mapping(1, 0), 27)
        self.assertEqual(self.library.probe_ref(-1, 1), 4)
        self.assertEqual(self.library.probe_ref(-1, 2), 5)

    def test_touch_pitch_toggle_and_value_are_reachable_and_legacy_values_are_preserved(self):
        self.install(core.default_config(version=8, empty_pitch=0, empty_semitones=7))
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), 0)
        self.script([5, -1], choice=1)
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), 7)
        self.script([6, -1], choice=-9)
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), -9)
        self.library.probe_reload()
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), -9)

    def test_touch_rows_announce_mode_pitch_switch_and_pitch_value_in_display_order(self):
        self.install(core.default_config(empty_pitch=0, empty_semitones=7))
        expected = ((4, "LANG_ACCESSIBILITY_EMPTY_FEEDBACK", "LANG_ACCESSIBILITY_EMPTY_SOUND_ONLY"),
                    (5, "LANG_KEYCLICK_EMPTY_PITCH", "LANG_OFF"))
        for row, label, value in expected:
            before = self.library.probe_stat(6)
            self.library.probe_touch_row(row)
            self.assertEqual(self.library.probe_spoken(before), self.constant(label))
            self.assertEqual(self.library.probe_spoken(before + 1), self.constant(value))
        before = self.library.probe_stat(6)
        self.library.probe_touch_row(6)
        self.assertEqual(self.library.probe_spoken(before), self.constant("LANG_KEYCLICK_EMPTY_SEMITONES"))
        self.assertEqual(self.library.probe_extra(3), 7)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_profile_default_labels_and_shared_root_menu_are_spoken_in_their_actual_context(self):
        for playback in (False, True):
            before = self.library.probe_stat(6)
            self.library.probe_profile_row(1, 0, self.context(playback))
            spoken = [self.library.probe_spoken(index)
                      for index in range(before, self.library.probe_stat(6))]
            self.assertIn(self.constant("LANG_ACCESSIBILITY_DEFAULT_MUSIC" if playback else
                                        "LANG_ACCESSIBILITY_DEFAULT_IN_MENU"), spoken)
        labels = ("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", "LANG_ACCESSIBILITY_PLAYBACK_ACTIONS",
                  "LANG_ACCESSIBILITY_HOLD_TIME", "LANG_RESET", "LANG_ACCESSIBILITY_CONTROLS_GUIDE")
        for index, label in enumerate(labels):
            before = self.library.probe_stat(6)
            self.library.probe_button_root_speak(index)
            self.assertEqual(self.library.probe_spoken(before), self.constant(label))
        self.script([2, -1], choice=1300)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_extra(5), 1300)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_volume_mappings_use_actions_consumed_by_the_active_screen(self):
        for playback in (False, True):
            for button, raw, mapping, suffix in ((1, 8, 9, "VOLUP"), (2, 4, 10, "VOLDOWN"),
                                                 (3, 16, 0, "VOLUP"), (4, 32, 0, "VOLDOWN")):
                self.setUp()
                mappings = {(button, 0): mapping}
                self.install(core.default_config(buttons=mappings, playback_buttons=mappings))
                expected = self.constant(("ACTION_WPS_" if playback else "ACTION_LIST_") + suffix)
                self.assertEqual(self.click(raw, playback=playback)[1], expected)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "R1 physical profiles")
    def test_causal_mutant_reintroducing_cross_button_reset_loses_the_pending_action(self):
        source = (self.workspace / "manager.c").read_text(encoding="utf-8")
        original = "if (!physical_override(selected, context))\n            return false;"
        self.assertEqual(source.count(original), 1)
        mutated = source.replace(original, "if (!physical_override(selected, context))\n"
            "        { accessibility_cancel_buttons(); return false; }", 1)
        directory = self.workspace / "cross-button-reset-mutant"
        directory.mkdir()
        source_path = directory / "mutant.c"
        source_path.write_text(mutated, encoding="utf-8")
        metadata = json.loads((self.workspace / "provenance.json").read_text(encoding="utf-8"))
        output = directory / ("mutant.dll" if os.name == "nt" else "mutant.so")
        command = [str(source_path) if item == str(self.workspace / "manager.c") else
                   str(output) if item == str(self.workspace / "manager.so") else item
                   for item in metadata["command"]]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (directory / "compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        library = ctypes.CDLL(str(output))
        library.probe_disk.argtypes = [ctypes.c_char_p, ctypes.c_int]
        library.probe_button.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_int, ctypes.c_bool]
        library.input_reset()
        value = core.default_config(buttons={(1, 0): 16, (1, 1): 11})
        library.probe_disk(value, len(value))
        library.probe_reload()
        for raw, now in ((8, 0), (8 | 0x2000000, 50), (16, 100), (16 | 0x2000000, 150), (0, 350)):
            library.probe_button(raw, now, self.context(), False)
        observed = library.probe_time_calls()
        report = {"mutant_compile_exit": result.returncode, "observed_time_actions": observed,
                  "required_time_actions": 1, "killed": observed != 1,
                  "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                  "scope": "actual compiled manager with only the former destructive cross-button reset restored"}
        (directory / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.assertTrue(report["killed"])

    def test_keyclick_system_menu_has_no_empty_pitch_aliases_and_touch_contains_all_three(self):
        source = (core.ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
        section = source[source.index("/* Keyclick menu */"):source.index("#if CONFIG_CHARGING",
                         source.index("/* Keyclick menu */"))]
        for name in ("keyclick_empty_pitch", "keyclick_empty_semitones",
                     "accessibility_keyclick_empty_menu", "accessibility_keyclick_pitch_menu"):
            self.assertNotIn(name, section)
        manager = self.source_bytes["apps/accessibility.c"].decode("utf-8")
        labels = manager[manager.index("static const int menu_labels[]"):
                         manager.index("static const char *accessibility_get_name")]
        for label in ("LANG_ACCESSIBILITY_EMPTY_FEEDBACK", "LANG_KEYCLICK_EMPTY_PITCH",
                      "LANG_KEYCLICK_EMPTY_SEMITONES"):
            self.assertIn(label, labels)


if __name__ == "__main__":
    unittest.main(verbosity=2)
