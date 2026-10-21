"""Run production keyboard echo behavior and the existing typing regressions."""

import ctypes
import json
import sys
import unittest

import test_accessibility_typing as legacy
from typing_echo_fixture import install


install(legacy)

HEADER = b"RBACCESSIBILITY-TYPING-ECHO:1\n"


class TypingEchoTests(legacy.AccessibilityTypingTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.library.echo_probe_save.argtypes = [ctypes.c_int] * 4
        cls.library.echo_probe_save.restype = ctypes.c_bool
        cls.library.echo_probe_disk.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        cls.library.echo_probe_disk_text.restype = ctypes.c_char_p
        cls.library.echo_probe_policy.argtypes = [ctypes.c_bool] * 3
        cls.library.echo_probe_text.restype = ctypes.c_char_p
        cls.library.echo_probe_run.argtypes = [ctypes.c_char_p, ctypes.c_int,
                                               ctypes.POINTER(ctypes.c_uint16)]
        cls.library.accessibility_typing_speak_character.argtypes = [ctypes.c_uint32, ctypes.c_bool]
        cls.library.accessibility_typing_echo_inserted.argtypes = [ctypes.c_char_p, ctypes.c_int]
        cls.library.accessibility_typing_echo_inserted.restype = ctypes.c_bool
        cls.library.accessibility_typing_echo_finish.argtypes = [ctypes.c_char_p, ctypes.c_int]
        cls.library.accessibility_typing_echo_deleted.argtypes = [ctypes.c_uint32]

    def settings(self):
        return tuple(self.library.echo_probe_setting(index) for index in range(4))

    def configure(self, echo=3, deletion=0, capitals=0, pitch=20):
        self.assertTrue(self.library.echo_probe_save(echo, deletion, capitals, pitch))

    def events(self):
        return [tuple(self.library.echo_probe_event(index, field) for field in range(4)) +
                (self.library.echo_probe_text(index).decode("utf-8"),)
                for index in range(self.library.echo_probe_count())]

    def characters(self):
        return [(chr(event[1]), event[3]) for event in self.events() if event[0] == 2]

    def words(self):
        return [event[4] for event in self.events() if event[0] == 3]

    def labels(self):
        return [event[1] for event in self.events() if event[0] == 1]

    def speak(self, text):
        return self.library.accessibility_typing_echo_inserted(text.encode("utf-8"), len(text))

    def run_layout(self, layout, initial="", capacity=1024):
        codepoints = [ord(character) for character in layout]
        keys = (ctypes.c_uint16 * (len(codepoints) + 2))(len(codepoints), *codepoints, 0xfeff)
        buffer = ctypes.create_string_buffer(initial.encode("utf-8"), capacity)
        result = self.library.echo_probe_run(buffer, capacity, keys)
        self.assertFalse(self.library.accessibility_typing_active())
        return result, buffer.value.decode("utf-8")

    def test_echo_defaults_and_legacy_config_remain_independent(self):
        self.assertEqual(self.settings(), (3, 0, 0, 20))
        self.assertEqual(self.library.probe_stat(0), 0)
        self.mode(2)
        before = self.library.probe_disk_text()
        self.configure(0, 2, 2, -80)
        self.assertEqual(self.library.probe_disk_text(), before)
        self.assertEqual(self.library.accessibility_typing_mode(), 2)
        self.mode(1)
        self.assertEqual(self.settings(), (0, 2, 2, -80))

    def test_echo_round_trip_with_short_reads_and_writes(self):
        self.library.probe_fault(0, 1, 1)
        self.configure(1, 1, 2, -80)
        saved = self.library.echo_probe_disk_text()
        self.assertEqual(saved, HEADER + b"echo:1\ndelete:1\ncapitals:2\npitch:-80\n")
        self.assertEqual(self.library.probe_stat(1), 1)
        self.assertEqual(self.library.probe_stat(2), 1)
        self.library.echo_probe_disk(saved, len(saved))
        self.assertEqual(self.settings(), (1, 1, 2, -80))

    def test_echo_invalid_schema_defaults_without_writes(self):
        good = HEADER + b"echo:2\ndelete:1\ncapitals:2\npitch:100\n"
        invalid = [b"", good[:-1], good + b"extra", good + b"\0", b"x" * 200,
                   good.replace(b":1\n", b":2\n", 1),
                   good.replace(b"echo:2", b"echo:4"),
                   good.replace(b"delete:1", b"delete:3"),
                   good.replace(b"capitals:2", b"capitals:3"),
                   good.replace(b"pitch:100", b"pitch:101"),
                   good.replace(b"pitch:100", b"pitch:-81"),
                   good.replace(b"pitch:100", b"pitch:-0"),
                   good.replace(b"pitch:100", b"pitch:+20"),
                   good.replace(b"pitch:100", b"pitch:020"),
                   good.replace(b"pitch:100", b"pitch:9999999999999999999999"),
                   good.replace(b"\n", b"\r\n"),
                   good.replace(b"echo:2", b"echo:\0")]
        for data in invalid:
            with self.subTest(data=data):
                self.library.echo_probe_disk(data, len(data))
                self.assertEqual(self.settings(), (3, 0, 0, 20))
        self.assertEqual(self.library.probe_stat(0), 0)
        self.library.echo_probe_disk(good, len(good))
        self.assertEqual(self.settings(), (2, 1, 2, 100))

    def test_echo_all_load_failures_use_defaults(self):
        data = HEADER + b"echo:0\ndelete:2\ncapitals:2\npitch:-80\n"
        for fault in [1, 2, 3]:
            self.library.echo_probe_disk(data, len(data))
            self.library.probe_fault(fault, 0, 0)
            self.assertEqual(self.settings(), (3, 0, 0, 20))
        self.assertEqual(self.library.probe_stat(0), 0)

    def test_echo_save_failures_retain_disk_and_all_runtime_settings(self):
        self.configure(2, 1, 1, -10)
        original = self.library.echo_probe_disk_text()
        for fault in range(4, 10):
            self.library.probe_fault(fault, 0, 0)
            self.assertFalse(self.library.echo_probe_save(0, 2, 2, 100), fault)
            self.assertEqual(self.settings(), (2, 1, 1, -10))
            self.assertEqual(self.library.echo_probe_disk_text(), original)
        self.library.probe_fault(0, 0, 0)
        self.configure(0, 2, 2, 100)

    def test_echo_rejects_invalid_values_before_writing(self):
        for setting in [(-1, 0, 0, 20), (4, 0, 0, 20), (3, -1, 0, 20),
                        (3, 3, 0, 20), (3, 0, -1, 20), (3, 0, 3, 20),
                        (3, 0, 0, -81), (3, 0, 0, 101), (3, 0, 0, 2147483647)]:
            self.assertFalse(self.library.echo_probe_save(*setting), setting)
        self.assertEqual(self.library.probe_stat(0), 0)

    def test_echo_unchanged_settings_do_not_write(self):
        self.configure()
        self.assertEqual(self.library.probe_stat(0), 0)

    def test_echo_menus_persist_real_settings_and_propagate_usb(self):
        for callback, field, choice in [
                ("accessibility_typing_echo_menu", 0, 0),
                ("accessibility_typing_deletion_menu", 1, 2),
                ("accessibility_typing_capitals_menu", 2, 2),
                ("accessibility_typing_capital_pitch_menu", 3, -80)]:
            self.library.probe_menu(choice, 1)
            before = self.settings()
            self.assertEqual(getattr(self.library, callback)(), 313)
            self.assertEqual(self.settings(), before)
            self.library.probe_menu(choice, 0)
            self.assertEqual(getattr(self.library, callback)(), 0)
            self.assertEqual(self.settings()[field], choice)

    def test_echo_menu_save_failure_reports_error_and_retains_setting(self):
        self.library.probe_fault(8, 0, 0)
        self.library.probe_menu(0, 0)
        self.assertEqual(self.library.accessibility_typing_echo_menu(), 0)
        self.assertEqual(self.settings(), (3, 0, 0, 20))
        self.assertEqual(self.library.probe_stat(3), self.constant("LANG_ERROR_WRITING_CONFIG"))

    def test_echo_none_characters_words_and_both_have_distinct_effects(self):
        for mode in range(4):
            with self.subTest(mode=mode):
                self.configure(mode)
                self.library.echo_probe_clear()
                self.speak("ż")
                self.speak("żółw ")
                self.assertEqual(self.characters(), [("ż", 0)] if mode & 1 else [])
                self.assertEqual(self.words(), ["żółw"] if mode & 2 else [])
                self.assertEqual(self.labels(), [self.constant("VOICE_BLANK")] if mode & 1 else [])
                if mode == 3:
                    self.assertEqual(self.events()[-1][2], 1)

    def test_echo_words_use_caret_boundary_and_preserve_utf8_input(self):
        self.configure(2)
        text = "pierwszy żółw reszta".encode("utf-8")
        self.library.accessibility_typing_echo_inserted(text, len("pierwszy żółw "))
        self.assertEqual(self.words(), ["żółw"])
        self.assertEqual(text.decode("utf-8"), "pierwszy żółw reszta")

    def test_echo_word_separators_and_combining_marks(self):
        self.configure(2)
        for text, expected in [("kot,", "kot"), ("łódź\u00a0", "łódź"),
                               ("e\u0301!", "e\u0301"), ("don't ", "don't"),
                               ("rock_box\n", "rock_box"), ("猫。", "猫")]:
            self.library.echo_probe_clear()
            self.speak(text)
            self.assertEqual(self.words(), [expected], text)
        for text in [" ", "\t", "kot  ", "kot,,", "kot🙂 "]:
            self.library.echo_probe_clear()
            self.speak(text)
            self.assertEqual(self.words(), [], text)

    def test_echo_long_word_is_complete_and_chunks_on_utf8_boundaries(self):
        self.configure(2)
        word = "aąż" * 240
        self.speak(word + " ")
        chunks = self.words()
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), word)
        self.assertTrue(all(len(part.encode("utf-8")) <= 255 for part in chunks))
        self.assertEqual([event[2] for event in self.events()], [0] + [1] * (len(chunks) - 1))

    def test_echo_invalid_or_outside_caret_does_not_speak(self):
        for text, position in [(b"", 1), (b"a", 0), (b"a", -1), (b"a", 2),
                               (b"\xff", 1), (b"\xc4", 1), (None, 1)]:
            self.assertFalse(self.library.accessibility_typing_echo_inserted(text, position))
        self.assertEqual(self.events(), [])

    def test_echo_capital_prefix_and_pitch_apply_to_unicode_characters(self):
        for capitals in range(3):
            for character in ["A", "Ą", "Ł", "Ź", "ǅ"]:
                self.configure(1, capitals=capitals, pitch=-80)
                self.library.echo_probe_clear()
                self.speak(character)
                self.assertEqual(self.characters(), [(character, -80 if capitals == 2 else 0)])
                self.assertEqual(self.labels(), [self.constant("LANG_ACCESSIBILITY_CAPITAL")]
                                 if capitals == 1 else [])
                if capitals == 1:
                    self.assertEqual([event[2] for event in self.events()], [1, 1])
        for character in ["a", "ą", "ł", "ź", ".", "4", "猫", "🙂"]:
            self.library.echo_probe_clear()
            self.speak(character)
            self.assertEqual(self.characters(), [(character, 0)])

    def test_echo_pitch_limits_and_neutral_request_do_not_leak_to_next_character(self):
        for pitch in [-80, -1, 0, 20, 100]:
            self.configure(1, capitals=2, pitch=pitch)
            self.library.echo_probe_clear()
            self.speak("Ą")
            self.speak("a")
            self.assertEqual(self.characters(), [("Ą", pitch), ("a", 0)])

    def test_echo_invalid_codepoints_do_not_emit_deleted_prefix_or_speech(self):
        for character in [0, 0xd800, 0xdfff, 0x110000, 0xffffffff]:
            self.library.accessibility_typing_speak_character(character, False)
            self.library.accessibility_typing_echo_deleted(character)
        self.assertEqual(self.events(), [])

    def test_echo_deleted_character_modes_and_capital_prefix_queue_order(self):
        for deletion in range(3):
            self.configure(deletion=deletion, capitals=1)
            self.library.echo_probe_clear()
            self.library.accessibility_typing_echo_deleted(ord("Ż"))
            expected = [] if deletion == 2 else [self.constant("LANG_ACCESSIBILITY_CAPITAL")]
            if deletion == 0:
                expected.insert(0, self.constant("LANG_ACCESSIBILITY_DELETED"))
            self.assertEqual(self.labels(), expected)
            self.assertEqual(self.characters(), [] if deletion == 2 else [("Ż", 0)])
            if deletion == 0:
                self.assertEqual([event[2] for event in self.events()], [0, 1, 1])
        self.library.echo_probe_clear()
        self.library.accessibility_typing_echo_deleted(0)
        self.assertEqual(self.events(), [])

    def test_echo_temporary_speech_suppression_blocks_direct_tts_and_prefixes(self):
        self.configure(capitals=1)
        for menus, muted in [(True, True), (False, False)]:
            self.library.echo_probe_policy(menus, muted, True)
            self.library.echo_probe_clear()
            self.speak("Ą")
            self.speak("kot ")
            self.library.accessibility_typing_echo_deleted(ord("B"))
            self.library.accessibility_typing_echo_finish(b"kot", 3)
            self.assertEqual(self.events(), [])

    def test_echo_prerecorded_fallback_retains_capital_and_deletion_labels(self):
        self.configure(capitals=1)
        self.library.echo_probe_policy(True, False, False)
        self.library.accessibility_typing_echo_deleted(ord("Ą"))
        self.assertEqual(self.labels(), [self.constant("LANG_ACCESSIBILITY_DELETED"),
                                        self.constant("LANG_ACCESSIBILITY_CAPITAL")])
        self.assertEqual(self.words(), ["Ą"])
        self.assertEqual(self.characters(), [])

    def test_actual_echo_occurs_after_successful_insert_in_each_typing_mode(self):
        for mode in range(3):
            self.library.probe_reset()
            self.mode(mode)
            self.configure(1)
            if mode == 0:
                self.touch("PRESS", 10, 60, 0)
                self.touch("RELEASE", 10, 60, 2)
            elif mode == 1:
                self.touch("PRESS", 10, 60, 0)
                self.touch("NONE", 10, 60, 23)
                self.touch("RELEASE", 10, 60, 24)
                self.touch("PRESS", 10, 60, 30)
                self.touch("RELEASE", 10, 60, 31)
                self.touch("PRESS", 10, 60, 40)
                self.touch("RELEASE", 10, 60, 41)
            else:
                self.action("ACTION_KBD_SELECT")
            self.action("ACTION_KBD_DONE")
            self.assertEqual(self.run_layout("Ą"), (0, "Ą"))
            self.assertEqual(self.characters(), [("Ą", 0)] * (1 if mode == 2 else 2))

    def test_actual_echo_none_preserves_focus_and_cursor_identification(self):
        self.configure(0, capitals=1)
        self.action("ACTION_KBD_RIGHT")
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_CURSOR_LEFT")
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_layout("aĄ"), (0, "Ą"))
        self.assertEqual(self.characters(), [("Ą", 0), ("Ą", 0)])
        self.assertEqual(self.labels(), [self.constant("LANG_ACCESSIBILITY_CAPITAL")] * 2)

    def test_actual_echo_word_is_said_at_separator_and_unfinished_word_on_done(self):
        self.configure(2)
        for action in ["ACTION_KBD_SELECT", "ACTION_KBD_RIGHT", "ACTION_KBD_SELECT",
                       "ACTION_KBD_RIGHT", "ACTION_KBD_SELECT", "ACTION_KBD_DONE"]:
            self.action(action)
        self.assertEqual(self.run_layout("ąż "), (0, "ąż "))
        self.assertEqual(self.words(), ["ąż"])
        self.library.probe_reset()
        self.configure(2)
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_layout("ż"), (0, "ż"))
        self.assertEqual(self.words(), ["ż"])

    def test_actual_keyboard_all_four_echo_modes_preserve_input_and_focus_feedback(self):
        for echo in range(4):
            self.library.probe_reset()
            self.configure(echo)
            for action in ["ACTION_KBD_SELECT", "ACTION_KBD_RIGHT", "ACTION_KBD_SELECT",
                           "ACTION_KBD_DONE"]:
                self.action(action)
            self.assertEqual(self.run_layout("ą "), (0, "ą "))
            self.assertEqual(self.characters(), [("ą", 0)] if echo & 1 else [])
            self.assertEqual(self.words(), ["ą"] if echo & 2 else [])
            self.assertEqual(self.labels(), [self.constant("VOICE_BLANK")] * (2 if echo & 1 else 1))

    def test_actual_keyboard_deletion_modes_act_on_the_removed_codepoint(self):
        for deletion in range(3):
            self.library.probe_reset()
            self.configure(0, deletion=deletion)
            self.library.echo_probe_script_clear()
            self.action("ACTION_KBD_BACKSPACE")
            self.action("ACTION_KBD_DONE")
            self.assertEqual(self.run_layout("x", "kotż"), (0, "kot"))
            self.assertEqual(self.characters(), [] if deletion == 2 else [("ż", 0)])
            self.assertEqual(self.labels(), [self.constant("LANG_ACCESSIBILITY_DELETED")]
                             if deletion == 0 else [])

    def test_actual_echo_no_done_word_for_initial_text_cancel_or_cursor_move(self):
        for actions, initial, expected in [
                (["ACTION_KBD_DONE"], "initial", (0, "initial")),
                (["ACTION_KBD_SELECT", "ACTION_KBD_ABORT"], "", (-1, "ż")),
                (["ACTION_KBD_SELECT", "ACTION_KBD_CURSOR_LEFT", "ACTION_KBD_DONE"], "", (0, "ż"))]:
            self.library.probe_reset()
            self.configure(2)
            for action in actions:
                self.action(action)
            self.assertEqual(self.run_layout("ż", initial), expected)
            self.assertEqual(self.words(), ["initial"] if initial else [])

    def test_actual_keyboard_caret_wrap_clears_pending_word_echo(self):
        for mode in range(3):
            for echo in [2, 3]:
                for character in ["a", "ż"]:
                    with self.subTest(mode=mode, echo=echo, character=character):
                        self.library.probe_reset()
                        self.mode(mode)
                        self.configure(echo)
                        self.library.probe_wrap(True)
                        self.action("ACTION_KBD_SELECT")
                        self.library.echo_probe_script_clear()
                        self.action("ACTION_KBD_CURSOR_RIGHT")
                        self.action("ACTION_KBD_CURSOR_LEFT")
                        self.action("ACTION_KBD_DONE")
                        self.assertEqual(self.run_layout(character), (0, character))
                        self.assertEqual(self.words(), [])
                        self.assertEqual(self.characters(), [(character, 0)])
                        self.assertEqual(self.labels(),
                                         [self.constant("LANG_ACCESSIBILITY_TYPING_TEXT_END")])

    def test_actual_keyboard_rejected_caret_move_retains_pending_word_echo(self):
        for echo in [2, 3]:
            with self.subTest(echo=echo):
                self.library.probe_reset()
                self.configure(echo)
                self.library.probe_wrap(False)
                self.action("ACTION_KBD_SELECT")
                self.library.echo_probe_script_clear()
                self.action("ACTION_KBD_CURSOR_RIGHT")
                self.action("ACTION_KBD_DONE")
                self.assertEqual(self.run_layout("ż"), (0, "ż"))
                self.assertEqual(self.words(), ["ż"])
                self.assertEqual(self.characters(), [])
                self.assertEqual(self.labels(), [])

    def test_actual_echo_caret_insert_and_deleted_utf8_character(self):
        self.configure(1)
        for action in ["ACTION_KBD_CURSOR_LEFT", "ACTION_KBD_BACKSPACE",
                       "ACTION_KBD_SELECT", "ACTION_KBD_DONE"]:
            self.action(action)
        self.assertEqual(self.run_layout("Ź", "aąb"), (0, "aŹb"))
        self.assertEqual(self.characters(), [("b", 0), ("ą", 0), ("Ź", 0)])
        self.assertIn(self.constant("LANG_ACCESSIBILITY_DELETED"), self.labels())
        self.assertEqual(self.words(), ["aąb"])

    def test_actual_echo_empty_deletion_and_failed_capacity_never_claim_an_edit(self):
        for initial, capacity, action in [("", 4, "ACTION_KBD_BACKSPACE"),
                                          ("ą", 3, "ACTION_KBD_SELECT")]:
            self.library.probe_reset()
            self.configure(3)
            self.library.echo_probe_script_clear()
            self.action(action)
            self.action("ACTION_KBD_DONE")
            self.assertEqual(self.run_layout("Ź", initial, capacity), (0, initial))
            self.assertEqual(self.events(), [])

    def test_actual_keyboard_deletion_and_caret_preserve_supplementary_codepoints(self):
        for action in ["ACTION_KBD_CURSOR_LEFT", "ACTION_KBD_BACKSPACE", "ACTION_KBD_DONE"]:
            self.action(action)
        self.assertEqual(self.run_layout("x", "a🙂b"), (0, "ab"))
        self.assertEqual(self.characters(), [("b", 0), ("🙂", 0)])
        self.library.probe_reset()
        self.configure(0)
        for action in ["ACTION_KBD_CURSOR_LEFT", "ACTION_KBD_CURSOR_LEFT", "ACTION_KBD_DONE"]:
            self.action(action)
        self.assertEqual(self.run_layout("x", "a🙂b"), (0, "a🙂b"))
        self.assertEqual(self.characters(), [("b", 0), ("🙂", 0)])

    def test_actual_echo_delete_at_caret_start_does_not_announce_deletion(self):
        self.action("ACTION_KBD_CURSOR_LEFT")
        self.library.echo_probe_script_clear()
        self.action("ACTION_KBD_BACKSPACE")
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_layout("x", "ż"), (0, "ż"))
        self.assertEqual(self.events(), [])

    def test_actual_echo_cancelled_touch_does_not_speak_edit_or_final_word(self):
        self.touch("PRESS", 10, 60, 0)
        self.library.probe_cancel()
        self.touch("RELEASE", 10, 60, 2)
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_layout("ż"), (0, ""))
        self.assertEqual(self.words(), [])
        self.assertEqual(self.characters(), [("ż", 0)])

    def test_actual_echo_usb_aborts_without_flushing_word_or_leaking_next_session(self):
        self.configure(2)
        self.action("ACTION_KBD_SELECT")
        self.library.probe_action(0x40000001)
        self.assertEqual(self.run_layout("ż"), (-1, "ż"))
        self.assertEqual(self.words(), [])
        self.library.echo_probe_clear()
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_layout("a"), (0, ""))
        self.assertEqual(self.events(), [])

    def test_echo_touch_sensitivity_scales_only_tap_movement_threshold(self):
        self.mode(1)
        for percent, distance, exploring in [(100, 8, False), (100, 9, True),
                                              (200, 4, False), (200, 5, True),
                                              (50, 16, False), (50, 17, True)]:
            self.library.accessibility_typing_cancel_touch()
            self.library.echo_probe_sensitivity(percent)
            self.process("PRESS", 1, x=0, time=0)
            self.process("CONTACT", 1, x=distance, time=1)
            self.assertEqual(self.library.accessibility_typing_needs_poll(), not exploring,
                             (percent, distance))

    def test_actual_keyboard_reports_stable_hit_ids_and_empty_to_feedback_owner(self):
        self.touch("PRESS", 10, 60, 0)
        self.touch("CONTACT", 11, 61, 1)
        self.touch("CONTACT", 55, 60, 2)
        self.touch("CONTACT", 479, 60, 3)
        self.touch("NONE", 479, 60, 4)
        self.touch("RELEASE", 479, 60, 5)
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_layout("ab"), (0, ""))
        self.assertEqual(self.library.echo_probe_feedback_count(), 5)
        self.assertEqual([self.library.echo_probe_feedback_target(index) for index in range(5)],
                         [0, 0, 1, -1, -1])
        self.assertEqual([self.library.echo_probe_feedback_occupied(index) for index in range(5)],
                         [1, 1, 1, 0, 0])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TypingEchoTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if hasattr(TypingEchoTests, "workspace"):
        (TypingEchoTests.workspace / "result.json").write_text(json.dumps({
            "tests_run": result.testsRun, "passed": result.wasSuccessful(),
            "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors],
            "skipped": [reason for _, reason in result.skipped],
        }, indent=2) + "\n", encoding="utf-8")
    sys.exit(not result.wasSuccessful())
