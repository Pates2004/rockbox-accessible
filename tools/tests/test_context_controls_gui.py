"""Pure CC-stage GUI protocol and accessibility profile migration regressions."""

import array
import math
import re
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

import test_accessibility_services_gui as services
import test_hiby_accessibility_gui as legacy
from test_hiby_accessibility_gui import parse_accessibility_config
from test_accessibility_screen_labels import language_phrases


def speech(*values):
    return "".join(f"TTS: {value}\nTTS utterance: {value}\n" for value in values)


def probe_fixture(language=None):
    probe = mock.Mock()
    probe.labels = {name: name for name in services.REQUIRED_IDS + services.VOICE_ONLY_IDS}
    if language is not None:
        catalog = language_phrases(language)[1]
        for identifier in services.TALKBOX_ROWS + services.POSITION_CHOICES + (
                "VOICE_OF", "VOICE_PERCENT", "LANG_SET_BOOL_YES", "LANG_SET_BOOL_NO",
                "LANG_TTS_SYSTEM", "LANG_TTS_DEFAULT_VARIANT"):
            probe.labels[identifier] = catalog[identifier]["voice"]
    probe.report = {}
    percent_maximum = {"LANG_TTS_PITCH": 99, "LANG_TTS_VOLUME": 200, "LANG_TTS_RANGE": 99}

    def percent_speech(identifier, expected):
        return speech(*expected)

    def row(name, key="Down", expected=()):
        for identifier in services.TALKBOX_ROWS[-2:]:
            if name.startswith("Confirm ") and name.endswith(identifier):
                if name in ("Confirm disabled LANG_TALKBOX_ANNOUNCE_POSITION",
                            "Confirm files-only LANG_TALKBOX_ANNOUNCE_POSITION"):
                    return speech(*expected)
                return speech(*expected, str(services.TALKBOX_ROWS.index(identifier) + 1), probe.labels["VOICE_OF"], "11")
        if name.startswith(("Preview percent ", "Restore percent ")):
            return percent_speech(name.rsplit(" ", 1)[-1], expected)
        return speech(*expected)

    def enter(identifier, expected=()):
        if identifier in ("LANG_TTS_LANGUAGE", "LANG_TTS_VARIANT"):
            return speech(*expected, "1", probe.labels["VOICE_OF"], "4" if identifier == "LANG_TTS_LANGUAGE" else "2")
        if identifier == "LANG_TTS_ENABLED":
            return speech(*expected, "2", probe.labels["VOICE_OF"], "2")
        return percent_speech(identifier, expected) if identifier in percent_maximum else speech(*expected)

    def cycle(name, *arguments, **keywords):
        if name == "Talkbox settings":
            return [speech(probe.labels[identifier], str(index), probe.labels["VOICE_OF"], "11")
                    for index, identifier in enumerate(services.TALKBOX_ROWS, 1)]
        return []

    probe.row.side_effect = row
    probe.enter.side_effect = enter
    probe.cycle.side_effect = cycle
    return probe


class ContextProfileTests(unittest.TestCase):
    def current(self):
        return services.mapping_profile(services.mapping_contract())

    def test_v11_keeps_four_independent_ordered_profiles_and_shared_launch_pool(self):
        data = self.current().encode("ascii")
        parsed = parse_accessibility_config(data)
        self.assertEqual(parsed["version"], 11)
        self.assertEqual(len(data.splitlines()), 92)
        for name in ("buttons", "button_launch", "playback_buttons", "playback_button_launch"):
            self.assertEqual(set(parsed[name]), {(button, slot) for button in range(5) for slot in range(4)})
        self.assertIsNot(parsed["buttons"], parsed["playback_buttons"])
        self.assertIsNot(parsed["button_launch"], parsed["playback_button_launch"])
        self.assertEqual((parsed["buttons"][(1, 0)], parsed["playback_buttons"][(1, 0)]), (27, 17))
        self.assertEqual((parsed["buttons"][(2, 1)], parsed["playback_buttons"][(2, 1)]), (17, 0))
        self.assertEqual(data.splitlines()[28], b"playback_gesture:1:0:0")
        self.assertEqual(data.splitlines()[68], b"playback_button:0:0:27:0")
        self.assertEqual(data.splitlines()[88], b"target:0:")
        self.assertIsNot(parsed["gestures"], parsed["playback_gestures"])
        self.assertIsNot(parsed["gesture_launch"], parsed["playback_gesture_launch"])

    def test_every_legacy_version_preserves_actions_launches_and_never_writes_on_read(self):
        builder = legacy.HarnessUnitTests()
        for version in range(1, 9):
            original = builder.config_for_version(version).encode("ascii")
            with self.subTest(version=version), \
                 mock.patch.object(Path, "write_bytes", side_effect=AssertionError("Read must not save")), \
                 mock.patch.object(Path, "write_text", side_effect=AssertionError("Read must not rewrite")), \
                 mock.patch.object(Path, "replace", side_effect=AssertionError("Read must not migrate on disk")):
                parsed = parse_accessibility_config(original)
                self.assertEqual(parsed["version"], version)
                self.assertEqual(parsed["buttons"], parsed["playback_buttons"])
                self.assertEqual(parsed["button_launch"], parsed["playback_button_launch"])
                self.assertIsNot(parsed["buttons"], parsed["playback_buttons"])
                self.assertIsNot(parsed["button_launch"], parsed["playback_button_launch"])
                parsed["playback_buttons"][(4, 3)] = 0
                parsed["playback_button_launch"][(4, 3)] = 12
                again = parse_accessibility_config(original)
                self.assertEqual(parsed["buttons"], again["buttons"])
                self.assertEqual(parsed["button_launch"], again["button_launch"])
                self.assertEqual(original, builder.config_for_version(version).encode("ascii"))

    def test_legacy_launch_references_migrate_without_target_reindexing(self):
        builder = legacy.HarnessUnitTests()
        path = "/.rockbox/rocks/apps/Zażółć.rock"
        for version in range(3, 9):
            data = (builder.config_for_version(version)
                    .replace("button:4:3:" + str({3: 15, 4: 16, 5: 17, 6: 19, 7: 22, 8: 22}[version]) + ":0\n",
                             "button:4:3:12:7\n")
                    .replace("target:3:\n", "target:3:" + path + "\n"))
            with self.subTest(version=version):
                parsed = parse_accessibility_config(data.encode("utf-8"))
                self.assertEqual(parsed["button_launch"][(4, 3)], 7)
                self.assertEqual(parsed["playback_button_launch"][(4, 3)], 7)
                self.assertEqual(parsed["launch_paths"][3], path)

    def test_v11_validates_plugin_references_in_both_profiles_independently(self):
        path = "/.rockbox/rocks/apps/Zażółć.rock"
        text = (re.sub(r'^button:4:3:27:0\n', "button:4:3:12:4\n", self.current(), flags=re.MULTILINE)
                .replace("playback_button:3:3:27:0\n", "playback_button:3:3:12:7\n")
                .replace("target:0:\n", "target:0:" + path + "\n")
                .replace("target:3:\n", "target:3:" + path + "\n"))
        parsed = parse_accessibility_config(text.encode("utf-8"))
        self.assertEqual(parsed["button_launch"][(4, 3)], 4)
        self.assertEqual(parsed["playback_button_launch"][(3, 3)], 7)
        self.assertEqual(parsed["launch_paths"][0], parsed["launch_paths"][3])
        for target in (0, 3):
            with self.subTest(target=target), self.assertRaises(AssertionError):
                parse_accessibility_config(text.replace("target:" + str(target) + ":" + path + "\n",
                                                        "target:" + str(target) + ":\n").encode("utf-8"))

    def test_v11_rejects_missing_mixed_reordered_duplicate_or_noncanonical_playback_rows(self):
        text = self.current()
        old = "playback_button:0:0:27:0\n"
        cases = [text.replace(old, ""), text + old,
                 text.replace("RBACCESSIBILITY:11\n", "RBACCESSIBILITY:9\n"),
                 text.replace(old, "playback_button:0:1:27:0\n"),
                 text.replace(old, "playback_button:0:0:28:0\n"),
                 text.replace(old, "playback_button:0:0:027:0\n"),
                 text.replace(old, "playback_button:0:0:27:00\n"),
                 text.replace(old, "playback_button:0:0:27:1\n"),
                 text.replace(old, "playback_button:0:0:12:13\n"),
                 text.replace(old, "playback_button:0:0:12:4\n"),
                 text.replace(old, "button:0:0:27:0\n"),
                 text.replace(old + "playback_button:0:1:27:0\n",
                              "playback_button:0:1:27:0\n" + old),
                 text.replace(old, "").replace("target:0:\n", "target:0:\n" + old)]
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode("ascii"))

    def test_v11_accepts_all_actions_direct_targets_and_distinct_none_system(self):
        text = self.current()
        for action in range(28):
            for target in ((0, 1, 2, 3, 8, 9, 10, 11, 12) if action == 12 else (0,)):
                trial = text.replace("playback_button:4:3:27:0\n", f"playback_button:4:3:{action}:{target}\n")
                with self.subTest(action=action, target=target):
                    parsed = parse_accessibility_config(trial.encode("ascii"))
                    self.assertEqual(parsed["playback_buttons"][(4, 3)], action)
                    self.assertEqual(parsed["playback_button_launch"][(4, 3)], target)
                    self.assertEqual(parsed["buttons"][(4, 3)], 27)


class RapidWrapGuiProtocolTests(unittest.TestCase):
    def test_dynamic_last_row_is_rejected_as_the_boundary_caller_before_navigation_or_profile_reads(self):
        for language in ("polski", "english"):
            probe = probe_fixture(language)
            probe.report.update(list_boundary_menu=dict(passed=True, restored=True,
                default=services.BOUNDARY_CHOICES[1], choices=list(services.BOUNDARY_CHOICES)))
            probe.latest = speech(probe.labels["LANG_TALKBOX_ANNOUNCE_DYNAMIC"], "11", probe.labels["VOICE_OF"], "11")
            with self.subTest(language=language), \
                 mock.patch.object(services, "mapping_file_identity", side_effect=AssertionError("No profile reads")), \
                 self.assertRaisesRegex(AssertionError, "caller position.*boundary row"):
                services.browse_rapid_wrap(probe, Path("unused"))
            probe.seek.assert_not_called()
            probe.rapid_navigation.assert_not_called()
            self.assertNotIn("rapid_wrap", probe.report)

    def exercise(self, language="polski", failure=None):
        probe = probe_fixture(language)
        probe.report.update(language=language, checks=[], list_boundary_menu=dict(passed=True, restored=True,
            default=services.BOUNDARY_CHOICES[1], choices=list(services.BOUNDARY_CHOICES)))
        probe.latest = speech(probe.labels["LANG_ACCESSIBILITY_LIST_BOUNDARY"], "9", probe.labels["VOICE_OF"], "11")
        self.last_probe = probe
        state = {"case": 0}

        def seek(identifier):
            if failure == "restore" and state["case"] == 4:
                probe.latest = speech("Wrong restored row")
            else:
                probe.latest = speech(probe.labels[identifier], str(services.TALKBOX_ROWS.index(identifier) + 1),
                                      probe.labels["VOICE_OF"], "11")

        def navigate(key, clicks):
            self.assertEqual((key, clicks), services.RAPID_WRAP_CASES[state["case"]])
            times = [10 + index * 0.16 for index in range(clicks)]
            result = dict(key=key, clicks=clicks, passed=failure != "timing", timing_exercised=failure != "timing",
                down_ack_monotonic=times, down_ack_spacing_seconds=[0.16] * (clicks - 1),
                maximum_down_ack_spacing_seconds=0.2, press_acknowledgement_indices=list(range(clicks)))
            probe.report.setdefault("rapid_navigation_bursts", []).append(result)
            return result

        def capture(name, action, expected):
            action()
            key, clicks = services.RAPID_WRAP_CASES[state["case"]]
            plan = services.rapid_wrap_plan(key, clicks)
            self.assertEqual(name, "Rapid Talkbox wrap " + plan["case"])
            self.assertEqual(expected, (probe.labels[plan["final_row"]],))
            request_rows = [services.TALKBOX_ROWS[0 if key == "Up" else -1], plan["wrapped_row"]]
            if clicks == 3:
                request_rows.append(plan["final_row"])
            if failure == "lost-wrap" and clicks == 3:
                request_rows.remove(plan["wrapped_row"])
            elif failure == "order" and clicks == 3:
                request_rows[-2:] = reversed(request_rows[-2:])
            elif failure == "duplicate":
                request_rows.append(plan["final_row"])
            text = ""
            suffix = (str(services.TALKBOX_ROWS.index(plan["final_row"]) + 1), probe.labels["VOICE_OF"], "11")
            for index, identifier in enumerate(request_rows):
                parts = (probe.labels[identifier], str(services.TALKBOX_ROWS.index(identifier) + 1), probe.labels["VOICE_OF"], "11")
                if index == len(request_rows) - 1:
                    if failure == "missing-request-position":
                        parts = parts[:1]
                    elif failure == "wrong-request-position":
                        parts = parts[:1] + ("0",) + parts[2:]
                    elif failure == "wrong-request-total":
                        parts = parts[:-1] + ("9",)
                    elif failure == "wrong-request-connector":
                        parts = parts[:2] + ("wrong connector",) + parts[3:]
                    elif failure == "request-setting-value":
                        parts = parts[:1] + (probe.labels["LANG_SET_BOOL_YES"],) + parts[1:]
                text += "".join("TTS: " + part + "\n" for part in parts)
            if failure != "missing-synthesis":
                if failure == "missing-synthesized-position":
                    suffix = ()
                elif failure == "wrong-synthesized-position":
                    suffix = ("0",) + suffix[1:]
                elif failure == "wrong-synthesized-total":
                    suffix = suffix[:-1] + ("9",)
                elif failure == "wrong-synthesized-connector":
                    suffix = suffix[:1] + ("wrong connector",) + suffix[2:]
                elif failure == "synthesized-setting-value":
                    suffix = (probe.labels["LANG_SET_BOOL_YES"],) + suffix
                text += "TTS utterance: " + " ".join(expected + suffix) + "\n"
            if failure == "late-speech":
                text += "TTS: Unrelated stale row\nTTS utterance: Unrelated stale row\n"
            probe.report["checks"].append(dict(name=name, passed=True))
            state["case"] += 1
            probe.latest = text
            return text

        probe.seek.side_effect = seek
        probe.rapid_navigation.side_effect = navigate
        probe.capture.side_effect = capture
        before = dict(sha256="a" * 64, bytes=100, mtime_ns=123, version=11, profiles_equal=False)
        with mock.patch.object(services, "mapping_file_identity", return_value=before), \
             mock.patch.object(Path, "read_bytes", return_value=b"synthetic profile"), \
             mock.patch.object(services, "rapid_wrap_profile", return_value=dict(action=27)), \
             mock.patch.object(services, "verify_mapping_read_only", side_effect=
                AssertionError("Profile changed") if failure == "profile" else lambda path, original: dict(original, unchanged=True)):
            services.browse_rapid_wrap(probe, Path("synthetic-rapid-layout"))
        return probe

    def test_all_four_cases_keep_exact_start_final_order_and_restore_caller_for_both_languages(self):
        for language in ("polski", "english"):
            with self.subTest(language=language):
                probe = self.exercise(language)
                result = probe.report["rapid_wrap"]
                self.assertEqual(result["schema"], "services-rapid-wrap:1")
                self.assertEqual(result["language"], language)
                self.assertTrue(result["passed"] and result["timing_exercised"] and result["restored"])
                self.assertEqual(result["menu_rows"], list(services.TALKBOX_ROWS))
                self.assertEqual(result["caller_row_before"], result["caller_row_after"])
                self.assertEqual(result["caller_row_after"], "LANG_ACCESSIBILITY_LIST_BOUNDARY")
                self.assertEqual(probe.rapid_navigation.call_args_list,
                    [mock.call(key, clicks) for key, clicks in services.RAPID_WRAP_CASES])
                self.assertEqual(probe.seek.call_args_list, [mock.call(identifier) for identifier in (
                    "LANG_TTS_ENABLED", "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TTS_ENABLED",
                    "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_ACCESSIBILITY_LIST_BOUNDARY")])
                self.assertEqual([case["final_row"] for case in result["cases"]],
                    ["LANG_TALKBOX_ANNOUNCE_DYNAMIC", "LANG_TTS", "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TTS_ENABLED"])
                for case, position in zip(result["cases"], (11, 1, 10, 2)):
                    final_parts = [probe.labels[case["final_row"]], str(position), probe.labels["VOICE_OF"], "11"]
                    self.assertEqual(case["requests"][-4:], final_parts)
                    self.assertEqual(case["utterances"], [" ".join(final_parts)])
                self.assertEqual([case["check_index"] for case in result["cases"]], [0, 1, 2, 3])
                self.assertTrue(result["profile_after"]["unchanged"])
                probe.enter.assert_not_called()
                probe.row.assert_not_called()
                probe.press.assert_not_called()
                probe.key.assert_not_called()

    def test_triple_bursts_require_wrapped_request_then_final_but_only_final_synthesis(self):
        result = self.exercise().report["rapid_wrap"]
        for case in result["cases"][2:]:
            self.assertLess(case["request_rows"].index(case["wrapped_row"]), case["request_rows"].index(case["final_row"]))
            self.assertEqual(case["synthesized_rows"], [case["final_row"]])
            self.assertNotIn(case["wrapped_row"], case["synthesized_rows"])

    def test_missing_reordered_duplicate_or_late_speech_cannot_publish_success(self):
        for failure in ("lost-wrap", "order", "duplicate", "missing-synthesis", "late-speech"):
            with self.subTest(failure=failure), self.assertRaises(AssertionError):
                self.exercise(failure=failure)
            self.assertFalse(self.last_probe.report["rapid_wrap"]["passed"])
            self.assertFalse(self.last_probe.report["rapid_wrap"]["restored"])

    def test_missing_or_incorrect_position_and_unspoken_values_fail_closed_in_both_languages(self):
        for language in ("polski", "english"):
            for failure in ("missing-request-position", "wrong-request-position", "wrong-request-total",
                            "wrong-request-connector", "request-setting-value", "missing-synthesized-position",
                            "wrong-synthesized-position", "wrong-synthesized-total", "wrong-synthesized-connector",
                            "synthesized-setting-value"):
                with self.subTest(language=language, failure=failure), self.assertRaises(AssertionError):
                    self.exercise(language, failure)
                self.assertFalse(self.last_probe.report["rapid_wrap"]["passed"])
                self.assertFalse(self.last_probe.report["rapid_wrap"]["restored"])

    def test_slow_timing_profile_change_and_wrong_restored_row_cannot_publish_success(self):
        for failure in ("timing", "profile", "restore"):
            with self.subTest(failure=failure), self.assertRaises(AssertionError):
                self.exercise(failure=failure)
            self.assertFalse(self.last_probe.report["rapid_wrap"]["passed"])
            self.assertFalse(self.last_probe.report["rapid_wrap"]["restored"])

    def test_unobserved_sound_only_default_refuses_navigation(self):
        for changed in ({}, dict(passed=True, restored=False), dict(passed=True, restored=True, default="LANG_OFF")):
            probe = probe_fixture()
            probe.report["list_boundary_menu"] = changed
            with self.subTest(changed=changed), self.assertRaisesRegex(AssertionError, "Sound-only"):
                services.browse_rapid_wrap(probe, Path("unused"))
            probe.seek.assert_not_called()
            probe.rapid_navigation.assert_not_called()
            self.assertNotIn("rapid_wrap", probe.report)

    def test_case_plan_is_exact_and_rejects_non_arrow_or_unbounded_cases(self):
        expected = (
            ("Up", 2, "LANG_TTS_ENABLED", "LANG_TALKBOX_ANNOUNCE_DYNAMIC", "LANG_TALKBOX_ANNOUNCE_DYNAMIC"),
            ("Down", 2, "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TTS", "LANG_TTS"),
            ("Up", 3, "LANG_TTS_ENABLED", "LANG_TALKBOX_ANNOUNCE_DYNAMIC", "LANG_TALKBOX_ANNOUNCE_POSITION"),
            ("Down", 3, "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TTS", "LANG_TTS_ENABLED"),
        )
        for key, clicks, start, wrapped, final in expected:
            plan = services.rapid_wrap_plan(key, clicks)
            self.assertEqual((plan["start_row"], plan["wrapped_row"], plan["final_row"]), (start, wrapped, final))
        for key, clicks in (("Left", 2), ("Insert", 3), ("Up", 4), ("Down", 0), ("Up", 2.0)):
            with self.subTest(key=key, clicks=clicks), self.assertRaises(AssertionError):
                services.rapid_wrap_plan(key, clicks)

    def test_actual_volume_masks_and_all_system_slots_allow_native_navigation_without_remapping(self):
        original = services.session_mapping_profile(services.mapping_contract(), "layout-connectivity").encode("ascii")
        before = legacy.parse_accessibility_config(original)
        with mock.patch.object(Path, "write_bytes", side_effect=AssertionError("No profile writes")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("No profile writes")):
            result = services.rapid_wrap_profile(original)
        self.assertEqual(result["up"], dict(mask=16, button_index=3))
        self.assertEqual(result["down"], dict(mask=32, button_index=4))
        self.assertEqual(result["action"], 27)
        self.assertEqual(result["slots"], [0, 1, 2, 3])
        self.assertEqual(legacy.parse_accessibility_config(original), before)
        self.assertEqual(before["buttons"][(1, 1)], services.mapping_contract()["actions"]["ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES"])
        for prefix in ("button", "playback_button"):
            for button in (3, 4):
                for slot in range(4):
                    changed = original.replace(f"{prefix}:{button}:{slot}:27:0\n".encode("ascii"),
                                               f"{prefix}:{button}:{slot}:17:0\n".encode("ascii"))
                    with self.subTest(prefix=prefix, button=button, slot=slot), \
                         self.assertRaisesRegex(AssertionError, "volume multitap override"):
                        services.rapid_wrap_profile(changed)


class ContextGuiProtocolTests(unittest.TestCase):
    def test_phase_and_eleven_talkbox_rows_are_pinned_to_current_version(self):
        self.assertEqual(services.SCOPE, "reader-tr01-tr05-20261023/services-gui")
        self.assertEqual(services.EXPECTED_VERSION, "0ed3734e5e-espeak-r34-hibyr1-win-alpha18-20261023")
        self.assertEqual(services.TALKBOX_ROWS, (
            "LANG_TTS", "LANG_TTS_ENABLED", "LANG_TTS_DUCKING", "LANG_TTS_DUCKING_LEVEL",
            "LANG_TTS_READER_SETTINGS", "LANG_ACCESSIBILITY", "LANG_ACCESSIBILITY_DISPLAY_SETTINGS",
            "LANG_ACCESSIBILITY_TYPING_SETTINGS", "LANG_ACCESSIBILITY_LIST_BOUNDARY",
            "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TALKBOX_ANNOUNCE_DYNAMIC"))

    def test_talkbox_navigation_keeps_engine_and_reader_separate_without_toggling_services(self):
        probe = probe_fixture()
        hierarchy = services.browse_talkbox_settings(probe)
        self.assertEqual(probe.method_calls, [
            mock.call.enter('LANG_TALKBOX_SETTINGS', ('LANG_TTS',)),
            mock.call.cycle('Talkbox settings', expected_order=services.TALKBOX_ROWS),
            mock.call.enter('LANG_TTS', ('LANG_TTS_LANGUAGE',)),
            mock.call.cycle('eSpeak settings', expected_order=services.ESPEAK_ROWS),
            mock.call.enter('LANG_TTS_LANGUAGE', ('LANG_TTS_SYSTEM',)),
            mock.call.row('Cancel unchanged LANG_TTS_LANGUAGE', 'Left', ('LANG_TTS_LANGUAGE',)),
            mock.call.enter('LANG_TTS_VARIANT', ('LANG_TTS_DEFAULT_VARIANT',)),
            mock.call.row('Cancel unchanged LANG_TTS_VARIANT', 'Left', ('LANG_TTS_VARIANT',)),
            mock.call.enter('LANG_TTS_PITCH', ('50', 'VOICE_PERCENT')),
            mock.call.row('Preview percent LANG_TTS_PITCH', 'Up', ('51', 'VOICE_PERCENT')),
            mock.call.row('Restore percent LANG_TTS_PITCH', 'Down', ('50', 'VOICE_PERCENT')),
            mock.call.row('Cancel unchanged percent LANG_TTS_PITCH', 'Left', ('LANG_TTS_PITCH',)),
            mock.call.enter('LANG_TTS_VOLUME', ('100', 'VOICE_PERCENT')),
            mock.call.row('Preview percent LANG_TTS_VOLUME', 'Up', ('101', 'VOICE_PERCENT')),
            mock.call.row('Restore percent LANG_TTS_VOLUME', 'Down', ('100', 'VOICE_PERCENT')),
            mock.call.row('Cancel unchanged percent LANG_TTS_VOLUME', 'Left', ('LANG_TTS_VOLUME',)),
            mock.call.enter('LANG_TTS_RANGE', ('50', 'VOICE_PERCENT')),
            mock.call.row('Preview percent LANG_TTS_RANGE', 'Up', ('51', 'VOICE_PERCENT')),
            mock.call.row('Restore percent LANG_TTS_RANGE', 'Down', ('50', 'VOICE_PERCENT')),
            mock.call.row('Cancel unchanged percent LANG_TTS_RANGE', 'Left', ('LANG_TTS_RANGE',)),
            mock.call.row('Back to Talkbox from eSpeak', 'Left', ('LANG_TTS',)),
            mock.call.enter('LANG_TTS_ENABLED', ('LANG_SET_BOOL_YES',)),
            mock.call.row('Cancel unchanged Talkbox enable switch', 'Left', ('LANG_TTS_ENABLED',)),
            mock.call.enter('LANG_TTS_READER_SETTINGS', ('LANG_TTS_READER_UNIT',)),
            mock.call.cycle('Text reading settings', expected_order=services.READER_ROWS),
            mock.call.row('Back to Talkbox from Text reading settings', 'Left', ('LANG_TTS_READER_SETTINGS',)),
            mock.call.enter('LANG_TALKBOX_ANNOUNCE_POSITION', ('LANG_TALKBOX_POSITION_EXCEPT_SLIDERS',)),
            mock.call.row('Choose position mode disabled 0', 'Down', ('LANG_OFF',)),
            mock.call.row('Confirm disabled LANG_TALKBOX_ANNOUNCE_POSITION', 'Right', ('LANG_TALKBOX_ANNOUNCE_POSITION',)),
            mock.call.enter('LANG_TALKBOX_ANNOUNCE_POSITION', ('LANG_OFF',)),
            mock.call.row('Choose position mode files-only 0', 'Up', ('LANG_TALKBOX_POSITION_EXCEPT_SLIDERS',)),
            mock.call.row('Choose position mode files-only 1', 'Up', ('LANG_TALKBOX_POSITION_FILES',)),
            mock.call.row('Confirm files-only LANG_TALKBOX_ANNOUNCE_POSITION', 'Right', ('LANG_TALKBOX_ANNOUNCE_POSITION',)),
            mock.call.enter('LANG_TALKBOX_ANNOUNCE_POSITION', ('LANG_TALKBOX_POSITION_FILES',)),
            mock.call.row('Choose position mode interface-only 0', 'Up', ('LANG_TALKBOX_POSITION_INTERFACE',)),
            mock.call.row('Confirm interface-only LANG_TALKBOX_ANNOUNCE_POSITION', 'Right', ('LANG_TALKBOX_ANNOUNCE_POSITION',)),
            mock.call.enter('LANG_TALKBOX_ANNOUNCE_POSITION', ('LANG_TALKBOX_POSITION_INTERFACE',)),
            mock.call.row('Choose position mode everywhere 0', 'Up', ('LANG_TALKBOX_POSITION_EVERYWHERE',)),
            mock.call.row('Confirm everywhere LANG_TALKBOX_ANNOUNCE_POSITION', 'Right', ('LANG_TALKBOX_ANNOUNCE_POSITION',)),
            mock.call.enter('LANG_TALKBOX_ANNOUNCE_POSITION', ('LANG_TALKBOX_POSITION_EVERYWHERE',)),
            mock.call.row('Choose position mode enabled 0', 'Down', ('LANG_TALKBOX_POSITION_INTERFACE',)),
            mock.call.row('Choose position mode enabled 1', 'Down', ('LANG_TALKBOX_POSITION_FILES',)),
            mock.call.row('Choose position mode enabled 2', 'Down', ('LANG_TALKBOX_POSITION_EXCEPT_SLIDERS',)),
            mock.call.row('Confirm enabled LANG_TALKBOX_ANNOUNCE_POSITION', 'Right', ('LANG_TALKBOX_ANNOUNCE_POSITION',)),
            *[call for identifier in ("LANG_TALKBOX_ANNOUNCE_DYNAMIC",) for call in (
                mock.call.enter(identifier, ("LANG_SET_BOOL_YES",)),
                mock.call.row("Disable " + identifier, "Down", ("LANG_SET_BOOL_NO",)),
                mock.call.row("Confirm disabled " + identifier, "Right", (identifier,)),
                mock.call.enter(identifier, ("LANG_SET_BOOL_NO",)),
                mock.call.row("Restore enabled " + identifier, "Up", ("LANG_SET_BOOL_YES",)),
                mock.call.row("Confirm enabled " + identifier, "Right", (identifier,)))],
        ])
        self.assertEqual(len(services.ESPEAK_ROWS), 9)
        self.assertTrue(set(services.ESPEAK_ROWS).isdisjoint(services.TALKBOX_ROWS))
        self.assertEqual(hierarchy, dict(talkbox_rows=list(services.TALKBOX_ROWS),
                                        espeak_rows=list(services.ESPEAK_ROWS), reader_rows=list(services.READER_ROWS)))
        self.assertNotIn('talkbox_hierarchy', probe.report)
        self.assertTrue(probe.report['percent_units']['passed'])
        self.assertTrue(probe.report['percent_units']['restored'])
        self.assertEqual(len(probe.report['percent_units']['rows']), 3)
        self.assertEqual(probe.report["announcement_settings"]["rows"], [
            dict(identifier="LANG_TALKBOX_ANNOUNCE_POSITION", default="except-sliders", modes=5, disabled=True, restored=True),
            dict(identifier="LANG_TALKBOX_ANNOUNCE_DYNAMIC", default=True, disabled=True, restored=True)])
        self.assertTrue(probe.report["announcement_settings"]["passed"])
        self.assertTrue(probe.report["announcement_settings"]["restored"])
        probe.press.assert_not_called()
        probe.capture.assert_not_called()

    def test_localized_talkbox_browse_checks_all_positions_and_restores_both_preferences(self):
        for language in ("polski", "english"):
            probe = probe_fixture(language)
            with self.subTest(language=language):
                result = services.browse_talkbox_settings(probe)
                self.assertEqual(result["talkbox_rows"], list(services.TALKBOX_ROWS))
                self.assertTrue(probe.report["announcement_settings"]["restored"])
                self.assertTrue(probe.report["percent_units"]["passed"])
                self.assertTrue(probe.report["percent_units"]["restored"])

    def test_talkbox_browse_rejects_missing_reordered_or_incomplete_position_speech(self):
        for language in ("polski", "english"):
            for failure in ("missing-row", "reordered", "missing-request", "missing-synthesis", "wrong-total", "extra-value"):
                probe = probe_fixture(language)
                rows = probe.cycle.side_effect("Talkbox settings")
                if failure == "missing-row":
                    rows.pop()
                elif failure == "reordered":
                    rows[-2:] = reversed(rows[-2:])
                elif failure == "missing-request":
                    rows[-1] = rows[-1].replace("TTS: 11\n", "")
                elif failure == "missing-synthesis":
                    rows[-1] = rows[-1].replace("TTS utterance: 11\n", "")
                elif failure == "wrong-total":
                    rows[-1] = rows[-1].replace(" 11\n", " 9\n")
                else:
                    rows[-1] += speech(probe.labels["LANG_SET_BOOL_YES"])
                probe.cycle.side_effect = None
                probe.cycle.return_value = rows
                with self.subTest(language=language, failure=failure), self.assertRaises(AssertionError):
                    services.browse_talkbox_settings(probe)
                probe.enter.assert_called_once_with("LANG_TALKBOX_SETTINGS", (probe.labels["LANG_TTS"],))
                self.assertNotIn("announcement_settings", probe.report)

    def test_session_versions_and_explicit_group_controls_are_not_factory_overwrites(self):
        contract = services.mapping_contract()
        for scenario in ('services', 'missing-voice', 'layout-connectivity', 'music'):
            parsed = parse_accessibility_config(services.session_mapping_profile(contract, scenario).encode('ascii'))
            with self.subTest(scenario=scenario):
                self.assertEqual(parsed['version'], 8 if scenario == 'missing-voice' else 11)
                for profile in ('buttons', 'playback_buttons'):
                    self.assertEqual(parsed[profile][(0, 1)], 19 if scenario == 'services' else 22 if scenario == 'missing-voice' else 27)
                    self.assertEqual(parsed[profile][(0, 2)], 26 if scenario == 'services' else 22 if scenario == 'missing-voice' else 27)

    def test_group_case_orchestration_uses_explicit_triples_and_restores_canonical_bytes(self):
        runtime = services.project_materials_root(services.ROOT) / 'group-gui-protocol-tests' / uuid.uuid4().hex
        directory = runtime / 'simdisk/.rockbox'
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / 'accessibility.cfg'
        original = services.session_mapping_profile(services.mapping_contract(), 'services').encode('ascii')
        path.write_bytes(original)
        probe = probe_fixture()
        probe.status_labels = dict(probe.labels)
        states = iter((True, False, True, False))
        def press(key, clicks=1):
            if key == 'Insert':
                enabled = next(states)
                before = path.read_bytes()
                after = re.sub(br'^enabled:[01]\n', b'enabled:' + (b'1' if enabled else b'0') + b'\n', before,
                               count=1, flags=re.MULTILINE)
                path.write_bytes(after)
            else:
                self.assertEqual((key, clicks), ('Down', 1))
                self.assertFalse(parse_accessibility_config(path.read_bytes())['enabled'])
        probe.press.side_effect = press
        def capture(name, action=None, expected=(), **keywords):
            if action:
                action()
            if keywords.get('grouped'):
                text = ''.join(prefix + ': ' + '\n'.join(expected) + '\n' for prefix in ('TTS', 'TTS utterance'))
                services.validate_group_status(text, expected)
                return text
            return speech(*expected)
        probe.capture.side_effect = capture
        services.grouped_service_case(probe, runtime)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(probe.press.call_args_list, [mock.call('Insert', clicks=3), mock.call('Insert', clicks=3),
                                                   mock.call('Down'), mock.call('Insert', clicks=3), mock.call('Insert', clicks=2)])
        proof = probe.report['grouped_shortcut']
        self.assertTrue(proof['mapping_restored'])
        self.assertEqual([item['actual_touch_enabled'] for item in proof['transitions']], [True, False, True, False])
        self.assertTrue(all(item['changed_fields'] == ['enabled'] for item in proof['transitions']))

    def test_group_status_requires_the_whole_single_job_in_both_real_traces(self):
        labels = ('Talkbox enabled', 'Touch exploration on')
        text = ''.join(prefix + ': ' + '\n'.join(labels) + '\n' for prefix in ('TTS', 'TTS utterance'))
        for newline in ('\n', '\r\n'):
            self.assertTrue(services.group_status_matches(text.replace('\n', newline), labels))
        for invalid in (speech(*labels), text.replace('Touch exploration on\n', '', 1),
                        text.replace('TTS: ', 'Other: ', 1), text.replace('TTS utterance: ', 'Other: ', 1),
                        text + speech('Unexpected ordinary row'),
                        text.replace('Talkbox enabled\nTouch exploration on', 'Touch exploration on\nTalkbox enabled')):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                services.validate_group_status(invalid, labels)

    def test_group_touch_transition_preserves_all_other_actual_profile_fields(self):
        before = services.session_mapping_profile(services.mapping_contract(), 'services').encode('ascii')
        after = before.replace(b'enabled:0\n', b'enabled:1\n', 1)
        proof = services.verify_group_mapping_transition(before, after, True)
        self.assertEqual(proof['changed_fields'], ['enabled'])
        for invalid in (after.replace(b'button:4:3:27:0', b'button:4:3:0:0'),
                        after.replace(b'hold:700', b'hold:800'), before):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                services.verify_group_mapping_transition(before, invalid, True)

    def test_numeric_values_need_both_traces_exact_sign_and_no_rockbox(self):
        for number in (-4, -3, 0, 1, 2, 15, 50, 99, 100):
            services.require_numeric_speech(speech(str(number)), number)
            for invalid in ("TTS: " + str(number) + "\n", "TTS utterance: " + str(number) + "\n",
                            speech(str(number) + "0"), speech(str(number) + ".5"), speech("Rockbox", str(number)),
                            speech(str(abs(number))) if number < 0 else speech("-" + str(number))):
                with self.subTest(number=number, invalid=invalid), self.assertRaises(AssertionError):
                    services.require_numeric_speech(invalid, number)
            with self.subTest(number=number), self.assertRaisesRegex(AssertionError, "ended with a different value"):
                services.require_numeric_speech(speech(str(number), str(number + 1)), number)

    def test_connectivity_first_selected_row_allows_only_honest_error_then_wifi(self):
        labels = probe_fixture().labels
        wifi = labels["LANG_HIBY_WIFI"]
        unavailable = labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]
        services.require_connectivity_first_row(speech(wifi, unavailable), labels)
        services.require_connectivity_first_row(speech(unavailable, wifi, unavailable), labels)
        for invalid in (speech(labels["LANG_HIBY_BT_DONE"], wifi), speech(unavailable),
                        speech(labels["LANG_HIBY_BT_TITLE"], wifi),
                        speech(labels["LANG_CONNECTIVITY"], wifi),
                        "TTS: " + wifi + "\n", "TTS utterance: " + wifi + "\n"):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                services.require_connectivity_first_row(invalid, labels)

    def test_profile_root_and_both_profile_orders_match_actual_source_contract(self):
        source = (services.ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        declaration = re.search(r'static const int button_root_labels\[\]\s*=\s*\{([^}]+)\}', source)
        self.assertIsNotNone(declaration)
        self.assertEqual(tuple(re.findall(r'LANG_[A-Z_0-9]+', declaration[1])), services.BUTTON_ROOT_ROWS)
        self.assertRegex(source, r'ACCESSIBILITY_BUTTON_COUNT \* ACCESSIBILITY_BUTTON_SLOT_COUNT \+ 1,\s*'
                         r'\(void \*\)\(intptr_t\)context')
        self.assertIn('accessibility_button_profile_menu(selection ? CONTEXT_WPS : CONTEXT_STD)', source)
        self.assertEqual(len(services.BUTTON_ROWS), 21)
        self.assertEqual(len(services.PLAYBACK_BUTTON_ROWS), 21)
        self.assertNotEqual(services.BUTTON_ROWS, services.PLAYBACK_BUTTON_ROWS)

    def test_both_touch_pitch_aliases_are_rejected_in_system_sounds(self):
        settings = (services.ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
        main = (services.ROOT / "apps/menus/main_menu.c").read_text(encoding="utf-8")
        display = (services.ROOT / "apps/menus/display_menu.c").read_text(encoding="utf-8")
        for alias in ("keyclick_empty_pitch", "keyclick_empty_semitones"):
            modified = settings
            original = re.search(r'MAKE_MENU\(keyclick_menu,.*?\);', modified, re.DOTALL)
            self.assertIsNotNone(original)
            modified = modified[:original.end() - 2] + ", &" + alias + modified[original.end() - 2:]
            with self.subTest(alias=alias), mock.patch.object(Path, "read_text", side_effect=[modified, main, display]), \
                 self.assertRaisesRegex(AssertionError, "must not remain aliased"):
                services.source_layout()

    def test_browsing_profiles_visits_both_without_writing_or_aliasing(self):
        probe = probe_fixture()
        services.browse_physical_profiles(probe)
        self.assertEqual(probe.cycle.call_args_list, [
            mock.call("Physical button settings", expected_order=services.BUTTON_ROOT_ROWS),
            mock.call("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", expected_order=services.BUTTON_ROWS),
            mock.call("LANG_ACCESSIBILITY_PLAYBACK_ACTIONS", expected_order=services.PLAYBACK_BUTTON_ROWS),
            *[call for identifier, rows in zip(services.GUIDE_CONTEXT_ROWS, services.GUIDE_ROWS) for call in (
                mock.call("Controls guide contexts " + identifier, expected_order=services.GUIDE_CONTEXT_ROWS),
                mock.call("Default controls " + identifier, expected_order=rows))]])
        self.assertEqual(probe.enter.call_args_list, [
            mock.call("LANG_ACCESSIBILITY_BUTTONS", (services.BUTTON_ROOT_ROWS[0],)),
            mock.call("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", services.BUTTON_ROWS[0]),
            mock.call("LANG_ACCESSIBILITY_PLAYBACK_ACTIONS", services.PLAYBACK_BUTTON_ROWS[0]),
            *[call for identifier, rows in zip(services.GUIDE_CONTEXT_ROWS, services.GUIDE_ROWS) for call in (
                mock.call("LANG_ACCESSIBILITY_CONTROLS_GUIDE", (services.GUIDE_CONTEXT_ROWS[0],)),
                mock.call(identifier, rows[0]))]])

    def test_pitch_previews_restore_both_values_without_changing_any_profile(self):
        probe = probe_fixture()
        data = services.mapping_profile(services.mapping_contract()).encode("ascii")
        with mock.patch.object(Path, "read_bytes", return_value=data) as reads, \
             mock.patch.object(Path, "write_bytes", side_effect=AssertionError("No harness profile writes")):
            services.browse_empty_pitch(probe, Path("unlaunched"))
        self.assertEqual(reads.call_count, 2)
        self.assertEqual(probe.row.call_args_list[0], mock.call("Preview empty pitch disabled", "Down", ("LANG_SET_BOOL_NO",)))
        self.assertIn("not actual empty-target sound-frequency acceptance", probe.report["empty_pitch_picker_scope"])

    def test_pitch_preview_rejects_missing_numeric_speech_or_unexpected_profile_rewrite(self):
        data = services.mapping_profile(services.mapping_contract()).encode("ascii")
        for mutation in ("rewritten", "numeric"):
            probe = probe_fixture()
            after = data
            if mutation == "rewritten":
                after = data.replace(b"playback_button:4:3:27:0", b"playback_button:4:3:0:0")
            else:
                probe.enter.side_effect = lambda name, expected=(): speech("Rockbox") if name == "LANG_KEYCLICK_EMPTY_SEMITONES" else speech(*expected)
            with self.subTest(mutation=mutation), mock.patch.object(Path, "read_bytes", side_effect=[data, after]), \
                 self.assertRaises(AssertionError):
                services.browse_empty_pitch(probe, Path("unlaunched"))
            self.assertNotIn("empty_pitch_picker_scope", probe.report)

    def test_brightness_and_backlight_timeout_use_distinct_actual_numeric_protocols(self):
        probe = probe_fixture()
        services.browse_brightness(probe)
        self.assertEqual(probe.enter.call_args_list, [mock.call("LANG_LCD_MENU"),
            mock.call("LANG_BRIGHTNESS", ("100",)), mock.call("LANG_BACKLIGHT", ("LANG_ALWAYS",))])
        self.assertIn("100 through 50 to 1", probe.report["brightness_speech_scope"])
        self.assertIn("Never/Always", probe.report["backlight_timeout_speech_scope"])
        self.assertIn("15 seconds", probe.report["backlight_timeout_speech_scope"])
        self.assertEqual(probe.row.call_args_list[-1],
                         mock.call("Back to Display from LCD settings", "Left", ("LANG_LCD_MENU",)))

    def test_brightness_checks_every_level_both_bounds_and_restores_default(self):
        probe = probe_fixture()
        services.browse_brightness(probe)
        values = [int(call.args[2][0]) for call in probe.row.call_args_list if call.args[0].startswith("Brightness ")]
        self.assertEqual(values, list(range(99, 0, -1)) + list(range(2, 101)) + [99, 100])
        self.assertEqual(values.count(50), 2)
        self.assertEqual(values.count(1), 1)
        self.assertEqual(values[-1], 100)
        self.assertEqual(probe.capture.call_args_list, [
            mock.call("Brightness lower boundary silent with sound disabled", mock.ANY, silent=True),
            mock.call("Brightness upper boundary silent with sound disabled", mock.ANY, silent=True)])
        for value in (1, 50, 100):
            broken = probe_fixture()
            broken.row.side_effect = lambda name, key="Down", expected=(): (
                speech(str(value) + ".5") if name == "Brightness " + str(value) else speech(*expected))
            with self.subTest(value=value), self.assertRaises(AssertionError):
                services.browse_brightness(broken)
            self.assertNotIn("brightness_speech_scope", broken.report)

    def test_backlight_checks_never_always_singular_plural_and_fifteen_seconds(self):
        probe = probe_fixture()
        services.browse_backlight_timeout(probe)
        self.assertEqual(probe.row.call_args_list[:2], [
            mock.call("Backlight timeout never", "Up", ("LANG_NEVER",)),
            mock.call("Backlight timeout always", "Down", ("LANG_ALWAYS",))])
        values = [call.args[2] for call in probe.row.call_args_list if re.fullmatch(r'Backlight timeout \d+', call.args[0])]
        self.assertEqual(values, [(str(value), "VOICE_SECOND" if value == 1 else "VOICE_SECONDS")
                                 for value in list(range(1, 11)) + [15] + list(range(10, 0, -1))])
        for missing in ("LANG_NEVER", "LANG_ALWAYS", "15", "VOICE_SECOND", "VOICE_SECONDS"):
            broken = probe_fixture()
            broken.row.side_effect = lambda name, key="Down", expected=(): speech(*(value for value in expected if value != missing))
            with self.subTest(missing=missing), self.assertRaises(AssertionError):
                services.browse_backlight_timeout(broken)
            self.assertNotIn("backlight_timeout_speech_scope", broken.report)

    def test_guide_cycles_require_twenty_complete_ordered_rows_in_both_speech_traces(self):
        builder = services.HarnessTests()
        for rows in services.GUIDE_ROWS:
            probe = builder.menu_cycle_fixture(rows)
            probe.cycle("Guide", expected_order=rows)
            for mutation in ("reordered", "missing-action", "missing-multiclick", "wrong-context", "missing-trace"):
                observations = [speech(*row) for row in rows]
                if mutation == "reordered":
                    observations[1] = speech(*reversed(rows[1]))
                elif mutation == "missing-action":
                    observations[1] = speech(*rows[1][:-1])
                elif mutation == "missing-multiclick":
                    observations[1] = speech(*rows[1][:2], rows[1][-1])
                elif mutation == "wrong-context":
                    other = services.GUIDE_ROWS[1 if rows == services.GUIDE_ROWS[0] else 0]
                    observations[1] = speech(*other[1])
                else:
                    observations[1] = ''.join("TTS: " + value + "\n" for value in rows[1])
                with self.subTest(rows=rows[0], mutation=mutation), self.assertRaises(AssertionError):
                    builder.menu_cycle_fixture(rows, observations).cycle("Broken guide", expected_order=rows)

    def test_guide_contexts_are_bound_to_actual_source_and_catalog_requirements(self):
        source = (services.ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        labels = re.search(r'static const int button_guide_context_labels\[\]\s*=\s*\{([^}]+)\}', source)
        self.assertIsNotNone(labels)
        self.assertEqual(tuple(re.findall(r'LANG_[A-Z_0-9]+', labels[1])), services.GUIDE_CONTEXT_ROWS)
        self.assertIn("talk_id(LANG_ACCESSIBILITY_DEFAULT_MULTICLICK, true);", source)
        self.assertTrue(set(identifier for rows in services.GUIDE_ROWS for row in rows for identifier in row) <= set(services.REQUIRED_IDS))

    def test_passive_connectivity_keeps_every_real_diagnostic_and_live_redraw(self):
        labels = probe_fixture().labels
        wifi, working = labels["LANG_HIBY_WIFI"], labels["LANG_HIBY_BT_WORKING"]
        for identifier in ("LANG_HIBY_CONNECTIVITY_UNAVAILABLE", "LANG_HIBY_CONNECTIVITY_PARTIAL",
                           "LANG_HIBY_CONNECTIVITY_FAILED", "LANG_HIBY_CONNECTIVITY_STORAGE_ERROR",
                           "LANG_HIBY_BT_CANCELLED", "LANG_HIBY_BT_TIMEOUT", "LANG_HIBY_BT_BUSY",
                           "LANG_HIBY_BT_AIRPLANE_MODE"):
            diagnostic = labels[identifier]
            services.require_connectivity_first_row(speech(diagnostic, wifi, diagnostic), labels)
            services.require_connectivity_first_row(speech(wifi, working, diagnostic, wifi, diagnostic), labels)
            with self.subTest(identifier=identifier), self.assertRaises(AssertionError):
                services.require_connectivity_first_row(speech(diagnostic, labels["LANG_HIBY_BT_DONE"], wifi, diagnostic), labels)

    def test_backlight_zero_and_seconds_units_are_pinned_to_actual_production_contract(self):
        settings = (services.ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
        talk = (services.ROOT / "apps/talk.c").read_text(encoding="utf-8")
        callback = re.search(r'static int32_t getlang_time_unit_0_is_always\([^)]*\)\s*\{([^}]+)\}', settings)
        self.assertIsNotNone(callback)
        self.assertRegex(callback[1], r'if \(value == 0\)\s*return LANG_ALWAYS;')
        self.assertRegex(settings, r'#ifdef SIMULATOR\s*#define DEFAULT_BACKLIGHT_TIMEOUT 0')
        self.assertRegex(talk, re.compile(r'if \(\(n==1 \|\| n==-1\).*?unit_id >= VOICE_SECONDS', re.DOTALL))
        self.assertIn('unit_id--;', talk)
        self.assertIn('VOICE_SECOND', services.VOICE_ONLY_IDS)

    def test_backlight_regression_detects_numeric_callback_speaking_rockbox_after_duration(self):
        probe = probe_fixture()
        probe.row.side_effect = lambda name, key="Down", expected=(): speech(*expected, "Rockbox")
        with self.assertRaisesRegex(AssertionError, "incorrectly announces Rockbox"):
            services.browse_backlight_timeout(probe)
        self.assertNotIn("backlight_timeout_speech_scope", probe.report)

    def test_music_profile_effects_keep_four_status_actions_and_never_use_global_input(self):
        probe = probe_fixture()
        probe.latest = speech("001 Service music", "1", probe.labels["VOICE_OF"], "1")
        probe.status_labels = {name: name for name in (
            "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON")}
        def capture(name, action=None, expected=(), **keywords):
            if action:
                action()
            return speech(*expected) + "TTS audio playback: 1\n"
        probe.capture.side_effect = capture
        services.music_case(probe)
        self.assertEqual(probe.press.call_args_list, [mock.call("Right"), mock.call("Right", clicks=2),
            mock.call("Left"), mock.call("Left"), mock.call("Right", clicks=2), mock.call("Right", clicks=2)])
        statuses = [call for call in probe.capture.call_args_list if call.kwargs.get("status")]
        self.assertEqual(len(statuses), 4)
        self.assertEqual([call.args[0] for call in statuses], ["WPS playback profile " + name for name in probe.status_labels] + list(probe.status_labels))
        probe.chord.assert_called_once_with("Insert", "Left")
        probe.key.assert_not_called()
        self.assertIn("no physical hardware acceptance", probe.report["physical_profile_effect_scope"])

    def music_pcm_fixture(self, wrong=None):
        identifiers = ("LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON")
        names = ["WPS playback profile " + name for name in identifiers] + list(identifiers)
        samples, checks = bytearray(), []
        def append(name, amplitude, status=False):
            start = len(samples)
            tone = array.array("h", (int(amplitude * math.sin(2 * math.pi * 997 * frame / 44100))
                                     for frame in range(4096) for channel in range(2)))
            if sys.byteorder != "little":
                tone.byteswap()
            samples.extend(tone.tobytes())
            checks.append({"name": name, "pcm_start": start, "pcm_end": len(samples), "status_only": status})
        append("Music baseline", 6000)
        for index, name in enumerate(names):
            append(name, 6000 if wrong == "attenuation" and index == 0 else 1200, True)
            append("Music recovery after " + name, 100 if wrong == "recovery" and index == 0 else 6000)
        if wrong == "alias":
            checks[1]["name"] = names[2]
            checks[2]["name"] = "Music recovery after " + names[2]
        if wrong == "missing":
            checks = checks[:5]
        return bytes(samples), {"checks": checks}

    def test_music_pcm_requires_measured_ducking_and_recovery_for_both_profiles(self):
        data, report = self.music_pcm_fixture()
        with mock.patch.object(Path, "read_bytes", return_value=data):
            services.verify_music(Path("unlaunched"), report)
        self.assertEqual(len(report["ducking_pcm"]), 4)
        for wrong in ("attenuation", "recovery", "alias", "missing"):
            data, report = self.music_pcm_fixture(wrong)
            with self.subTest(wrong=wrong), mock.patch.object(Path, "read_bytes", return_value=data), \
                 self.assertRaises(AssertionError):
                services.verify_music(Path("unlaunched"), report)
            self.assertNotIn("ducking_pcm", report)


class RapidSettingSpeechContractTests(unittest.TestCase):
    def test_rapid_setting_rows_follow_the_actual_name_only_menu_voice_callback(self):
        talk = (services.ROOT / "apps/talk.c").read_text(encoding="utf-8")
        callback = re.search(r'void talk_setting\([^\n]+\)\s*\{(.*?)\n\}', talk, re.DOTALL)
        self.assertIsNotNone(callback)
        self.assertEqual(re.findall(r'\btalk_[a-z_]+\s*\(', callback[1]),
                         ["talk_menus_enabled(", "talk_id("])
        self.assertRegex(callback[1], r'talk_id\(setting->lang_id,\s*false\)')
        menu = (services.ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
        for item, variable in (("tts_enabled_item", "tts_enabled"),
                               ("list_boundary_feedback_item", "list_boundary_feedback"),
                               ("tts_announce_position_item", "tts_announce_position"),
                               ("tts_announce_dynamic_item", "tts_announce_dynamic")):
            with self.subTest(item=item):
                self.assertRegex(menu, r'MENUITEM_SETTING\(' + item + r',\s*&global_settings\.' + variable + r',')

    def test_setting_labels_with_exact_positions_pass_but_unspoken_values_remain_rejected(self):
        for language in ("polski", "english"):
            labels = probe_fixture(language).labels
            for key, clicks in services.RAPID_WRAP_CASES:
                plan = services.rapid_wrap_plan(key, clicks)
                rows = [plan["wrapped_row"]] + ([plan["final_row"]] if clicks == 3 else [])
                text = "".join("TTS: " + labels[identifier] + "\n" for identifier in rows)
                suffix = (str(services.TALKBOX_ROWS.index(plan["final_row"]) + 1), labels["VOICE_OF"], "11")
                text += "".join("TTS: " + part + "\n" for part in suffix)
                text += "TTS utterance: " + " ".join((labels[plan["final_row"]],) + suffix) + "\n"
                with self.subTest(language=language, key=key, clicks=clicks):
                    result = services.rapid_wrap_speech(text, labels, key, clicks)
                    self.assertEqual(result["synthesized_rows"], [plan["final_row"]])
                    extra = text + "TTS: Unexpected value\nTTS utterance: Unexpected value\n"
                    with self.assertRaisesRegex(AssertionError, "Unexpected speech"):
                        services.rapid_wrap_speech(extra, labels, key, clicks)
                    valued = text.replace(labels[plan["final_row"]], labels[plan["final_row"]] + " " + labels["LANG_SET_BOOL_YES"])
                    with self.assertRaisesRegex(AssertionError, "final row|Unexpected speech"):
                        services.rapid_wrap_speech(valued, labels, key, clicks)


if __name__ == "__main__":
    unittest.main()
