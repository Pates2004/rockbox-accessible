"""Exercise independently persisted gesture profiles through the real manager."""

import unittest

import test_accessibility_settings as core


class AccessibilityGestureProfilesTests(unittest.TestCase):
    setUpClass = classmethod(core.AccessibilitySettingsTests.setUpClass.__func__)
    tearDownClass = classmethod(core.AccessibilitySettingsTests.tearDownClass.__func__)
    setUp = core.AccessibilitySettingsTests.setUp
    constant = core.AccessibilitySettingsTests.constant
    parse = core.AccessibilitySettingsTests.parse
    script = core.AccessibilitySettingsTests.script
    touch = core.AccessibilitySettingsTests.touch
    poll = core.AccessibilitySettingsTests.poll
    process_pending = core.AccessibilitySettingsTests.process_pending

    def install(self, data):
        self.library.probe_disk(data, len(data))
        self.library.probe_reload()

    def stroke(self, context, start=0):
        self.touch("TOUCHEVENT_PRESS", 100, 100, start, context)
        self.touch("TOUCHEVENT_CONTACT", 60, 100, start + 30, context)
        return self.touch("TOUCHEVENT_RELEASE", 60, 100, start + 100, context)

    def test_defaults_have_equal_independent_profiles(self):
        for slot in range(1, 21):
            self.assertEqual(self.library.probe_mapping(slot), self.library.probe_playback_gesture(slot))
        self.library.probe_assign(1, 11)
        self.assertEqual(self.library.probe_playback_gesture(1), 1)

    def test_every_legacy_version_copies_gestures_and_launch_refs_without_writing(self):
        for version, maximum in core.VERSION_ACTION_LIMITS.items():
            if version >= 10:
                continue
            with self.subTest(version=version):
                self.setUp()
                data = core.default_config(version=version,
                    replacements={1: min(maximum, 12), 17: 0},
                    gesture_refs={1: 4} if version >= 3 else {},
                    paths={0: "/.rockbox/rocks/apps/legacy.rock"})
                self.install(data)
                self.assertEqual(self.library.probe_disk_content(), data)
                self.assertEqual(self.library.probe_stat(2), 0)
                for slot in range(1, 21):
                    self.assertEqual(self.library.probe_mapping(slot), self.library.probe_playback_gesture(slot))
                    self.assertEqual(self.library.probe_ref(-1, slot), self.library.probe_playback_gesture_ref(slot))
                self.assertEqual(self.library.probe_save(), 1)
                self.assertTrue(self.library.probe_disk_content().startswith(b"RBACCESSIBILITY:11\n"))
                self.assertEqual(self.parse(self.library.probe_disk_content()), 1)

    def test_current_round_trip_preserves_different_actions_and_shared_launch_pool(self):
        data = core.default_config(replacements={1: 12, 19: 11},
            gesture_refs={1: 4}, playback_gestures={1: 12, 19: 16},
            playback_gesture_refs={1: 7}, paths={0: "/.rockbox/rocks/apps/menu.rock",
                3: "/.rockbox/rocks/apps/music.rock"},
            buttons={(1, 0): 11}, playback_buttons={(1, 0): 16})
        self.assertEqual(len(data.splitlines()), 92)
        self.install(data)
        self.assertEqual(self.library.probe_mapping(19), 11)
        self.assertEqual(self.library.probe_playback_gesture(19), 16)
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_disk_content(), data)

    def test_current_parser_rejects_malformed_playback_gesture_block(self):
        data = core.default_config(playback_gestures={1: 12},
            playback_gesture_refs={1: 4}, paths={0: "/.rockbox/rocks/apps/music.rock"})
        self.assertEqual(self.parse(data), 1)
        invalid = [data.replace(b"playback_gesture:1:12:4", row) for row in (
            b"playback_gesture:0:12:4", b"playback_gesture:2:12:4",
            b"playback_gesture:1:22:4", b"playback_gesture:1:11:4",
            b"playback_gesture:1:12:13", b"playback_gesture:1:12:04")]
        start, end = data.index(b"playback_gesture:"), data.index(b"button:")
        invalid.extend((data[:start] + data[end:], data[:end] + data[start:end] + data[end:]))
        for malformed in invalid:
            self.assertEqual(self.parse(malformed), 0)

    def test_strokes_use_active_screen_profile_and_native_semantics(self):
        self.install(core.default_config(replacements={1: 2}, playback_gestures={1: 1}))
        self.assertEqual(self.stroke("CONTEXT_STD"), self.constant("ACTION_STD_NEXT"))
        self.assertEqual(self.stroke("CONTEXT_WPS", 500), self.constant("ACTION_WPS_VOLUP"))
        self.assertEqual(self.stroke("CONTEXT_STD", 1000), self.constant("ACTION_STD_NEXT"))

    def test_custom_and_plugin_contexts_do_not_masquerade_as_playback(self):
        self.install(core.default_config(replacements={1: 11}, playback_gestures={1: 16}))
        playback = self.constant("CONTEXT_WPS")
        self.assertEqual(self.library.probe_context_gesture(playback, 1), 16)
        for flag in ("CONTEXT_CUSTOM", "CONTEXT_CUSTOM2", "CONTEXT_PLUGIN"):
            self.assertEqual(self.library.probe_context_gesture(playback | self.constant(flag), 1), 11)
        for flag in ("CONTEXT_REMOTE", "CONTEXT_LOCKED", "CONTEXT_REMAPPED"):
            self.assertEqual(self.library.probe_context_gesture(playback | self.constant(flag), 1), 16)

    def test_context_change_cancels_pending_taps_instead_of_using_new_profile(self):
        self.install(core.default_config(replacements={17: 11}, playback_gestures={17: 16}))
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0, "CONTEXT_WPS")
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 40, "CONTEXT_WPS")
        self.touch("TOUCHEVENT_PRESS", 40, 50, 80, "CONTEXT_WPS")
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 120, "CONTEXT_WPS")
        self.assertEqual(self.poll(500, "CONTEXT_STD"), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_time_calls(), 0)
        self.assertEqual(self.library.probe_stat(5), 0)

    def test_hold_recognizer_configuration_follows_each_profile(self):
        self.install(core.default_config(replacements={18: 0}, playback_gestures={18: 16}))
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0, "CONTEXT_WPS")
        self.poll(1000, "CONTEXT_WPS")
        self.assertEqual(self.library.probe_time_calls(), 1)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 1100, "CONTEXT_WPS")
        self.touch("TOUCHEVENT_PRESS", 40, 50, 1500, "CONTEXT_STD")
        self.poll(2500, "CONTEXT_STD")
        self.assertEqual(self.library.probe_time_calls(), 1)

    def test_each_profile_editor_changes_only_its_selected_mapping(self):
        for playback in (False, True):
            with self.subTest(playback=playback):
                self.setUp()
                self.script([0, -1], choice=11)
                self.assertEqual(self.library.probe_gesture_profile_menu(int(playback)), 0)
                self.assertEqual(self.library.probe_mapping(1), 1 if playback else 11)
                self.assertEqual(self.library.probe_playback_gesture(1), 11 if playback else 1)
                self.assertEqual(self.library.probe_stat(2), 1)

    def test_profile_root_routes_to_selected_editor(self):
        self.script([1, 0, -1, -1], choice=16)
        self.assertEqual(self.library.probe_gesture_root_menu(), 0)
        self.assertEqual(self.library.probe_mapping(1), 1)
        self.assertEqual(self.library.probe_playback_gesture(1), 16)

    def test_reset_profile_retains_other_profile_and_its_unique_launch_path(self):
        self.install(core.default_config(replacements={1: 12}, gesture_refs={1: 4},
            playback_gestures={1: 12}, playback_gesture_refs={1: 7},
            paths={0: "/.rockbox/rocks/apps/menu.rock", 3: "/.rockbox/rocks/apps/music.rock"}))
        self.script([20, -1])
        self.assertEqual(self.library.probe_gesture_profile_menu(0), 0)
        self.assertEqual(self.library.probe_mapping(1), 1)
        self.assertEqual(self.library.probe_playback_gesture(1), 12)
        self.assertEqual(self.library.probe_path(0), b"")
        self.assertEqual(self.library.probe_path(3), b"/.rockbox/rocks/apps/music.rock")
        self.script([20, -1])
        self.assertEqual(self.library.probe_gesture_profile_menu(1), 0)
        self.assertEqual(self.library.probe_path(3), b"")

    def test_v9_keeps_independent_physical_profiles_while_copying_gestures(self):
        self.install(core.default_config(version=9, replacements={1: 11},
            buttons={(1, 0): 11}, playback_buttons={(1, 0): 16}))
        self.assertEqual(self.library.probe_mapping(1), 11)
        self.assertEqual(self.library.probe_playback_gesture(1), 11)
        self.assertEqual(self.library.probe_button_mapping(1, 0), 11)
        self.assertEqual(self.library.probe_playback_mapping(1, 0), 16)


if __name__ == "__main__":
    unittest.main(verbosity=2)
