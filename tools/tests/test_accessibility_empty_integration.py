"""Compile real exploration callers and reader with bounded speech/file fixtures."""

import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root
from test_keyclick_pcm import definition, without_includes
import test_keyclick_exploration as widgets
import test_tts_reader as reader_fixture


ROOT = Path(__file__).resolve().parents[2]
GUARD = "    if (row < 0 && !accessibility_empty_speech_enabled())\n        return;\n"


def policy_projection(manager, header):
    return (definition(header, "enum accessibility_empty_feedback\n") + ";\n" +
            "static enum accessibility_empty_feedback empty_feedback_mode;\n" +
            "static void accessibility_empty_load(void) {}\n" +
            "\n".join(definition(manager, signature) for signature in (
                "enum accessibility_empty_feedback accessibility_empty_feedback_mode(",
                "bool accessibility_empty_sound_enabled(", "bool accessibility_empty_speech_enabled(")))


def implementation(source, signature):
    matched = re.search(re.escape(signature) + r"[^;{]*\)\s*\{", source)
    if matched is None:
        raise AssertionError("Missing function implementation: " + signature)
    return definition(source[matched.start():], signature)


WIDGET_STATE = r'''
#include <stdbool.h>
static bool feedback_pending, feedback_valid, feedback_occupied, empty_speech_pending;
static const void *feedback_owner;
static int feedback_target;
static bool point_single_tap;
static int fixture_empty_speeches, fixture_occupied_speeches, fixture_clicks;
static unsigned int fixture_sources = 7;
static int fixture_strength = 2;
#define LANG_ACCESSIBILITY_EMPTY (-1)
'''
WIDGET_ENDPOINTS = r'''
static void keyclick_click_touch_target(bool occupied, bool single_tap)
{
    (void)single_tap;
    if (fixture_strength && (fixture_sources & 4) &&
        (occupied || accessibility_empty_sound_enabled()))
        ++fixture_clicks;
}
static void fixture_mode(int mode)
{
    empty_feedback_mode = mode;
    feedback_pending = feedback_valid = empty_speech_pending = false;
    fixture_empty_speeches = fixture_occupied_speeches = fixture_clicks = 0;
    point_force = true;
    fixture_strength = 2;
    fixture_sources = 7;
}
'''
LIST_PREFIX = r'''
#define TITLE 1
#define SCROLLBAR 2
#define LIST 4
#define ACTION_REDRAW 5
#define LANG_SCROLL_BAR 22
enum screen_type { FIXTURE_MAIN };
struct gui_synclist {
    struct viewport *parent[1];
    int line_height[1], start_item[1], y_pos, nb_items, selected_size, selected_item;
    const unsigned char *title;
};
static struct screen screens[1];
static struct viewport list_text[1] = {{0, 20, 200, 80}};
static void _gui_synclist_stop_kinetic_scrolling(struct gui_synclist *list) { (void)list; }
static int get_click_location(struct gui_synclist *list, int position_x, int position_y)
{
    (void)list;
    if (position_x < 0 || position_x >= 200 || position_y < 0 || position_y >= 100)
        return 0;
    return position_y < 20 ? TITLE : LIST;
}
static bool skinlist_get_item(struct screen *screen, struct gui_synclist *list,
                              int position_x, int position_y, int *line)
{ (void)screen; (void)list; (void)position_x; (void)position_y; (void)line; return false; }
static void gui_synclist_select_item(struct gui_synclist *list, int item) { list->selected_item = item; }
static void gui_synclist_speak_item(struct gui_synclist *list) { (void)list; talk_id(20, false); }
'''
LIST_CASES = r'''
int main(void)
{
    struct viewport parent = {0, 0, 200, 100};
    struct gui_synclist list = {.parent = {&parent}, .line_height = {10},
        .nb_items = 3, .selected_size = 1, .title = (const unsigned char *)"Title"};
    for (int mode = 0; mode <= 2; ++mode)
    {
        fixture_mode(mode);
        point(10, 25); list_accessibility_explore(&list);
        CHECK(list.selected_item == 0 && spoken == 20 && fixture_occupied_speeches == 1);
        point_force = false;
        int before_clicks = fixture_clicks;
        point(210, 25); list_accessibility_explore(&list);
        CHECK(fixture_empty_speeches == (mode != 0));
        CHECK(fixture_clicks == before_clicks + (mode != 2));
        for (int index = 0; index < 100; ++index)
        { point(211, 26); list_accessibility_explore(&list); }
        CHECK(fixture_empty_speeches == (mode != 0));
        point_force = true;
        fixture_strength = 0;
        before_clicks = fixture_clicks;
        point(210, 25); list_accessibility_explore(&list);
        CHECK(fixture_clicks == before_clicks && fixture_empty_speeches == 2 * (mode != 0));
        point(10, 25); list_accessibility_explore(&list);
        CHECK(fixture_occupied_speeches == 2 && list.selected_item == 0);
    }
    return 0;
}
'''
SKIN_CASES = r'''
int main(void)
{
    struct skin_viewport viewport = {0, {20, 30, 200, 160}};
    struct touchregion region = {&viewport, 10, 20, 30, 40, 2, 3, 4, false};
    struct wps_token token = {{&region}};
    struct skin_token_list entry = {&token, NULL};
    struct wps_data data = {&entry, false};
    struct gui_wps wps = {&data};
    for (int mode = 0; mode <= 2; ++mode)
    {
        fixture_mode(mode);
        point(30, 55); skin_accessibility_explore(&wps);
        CHECK(feedback_occupied && fixture_clicks == 1 && !fixture_empty_speeches);
        point_force = false;
        point(27, 48); skin_accessibility_explore(&wps);
        CHECK(!feedback_occupied && fixture_empty_speeches == (mode != 0));
        CHECK(fixture_clicks == 1 + (mode != 2));
        for (int index = 0; index < 100; ++index)
        { point(26, 47); skin_accessibility_explore(&wps); }
        CHECK(fixture_empty_speeches == (mode != 0));
        point_force = true;
        fixture_sources = 2;
        int before_clicks = fixture_clicks;
        point(27, 48); skin_accessibility_explore(&wps);
        CHECK(fixture_clicks == before_clicks && fixture_empty_speeches == 2 * (mode != 0));
    }
    return 0;
}
'''
KEYBOARD_PREFIX = r'''
#define HZ 100
enum { ACTION_KBD_SELECT = 30, ACTION_KBD_DONE, ACTION_KBD_BACKSPACE,
       ACTION_KBD_ABORT, ACTION_KBD_PAGE_FLIP, ACTION_KBD_CURSOR_LEFT, ACTION_KBD_CURSOR_RIGHT };
struct keyboard_parameters { int x, y; };
struct edit_state { bool redraw; };
static int global_settings, fixture_target, fixture_focus_calls, fixture_gesture_calls;
static bool fixture_touch_ready;
static struct touchevent fixture_touch;
static struct accessibility_typing_result fixture_result;
bool accessibility_typing_take_touch(struct touchevent *event)
{
    if (!fixture_touch_ready) return false;
    fixture_touch_ready = false;
    *event = fixture_touch;
    feedback_pending = event->type != TOUCHEVENT_NONE;
    return true;
}
static int kbd_typing_hit(struct keyboard_parameters *parameters, struct screen *screen,
                           int position_x, int position_y)
{ (void)parameters; (void)screen; (void)position_x; (void)position_y; return fixture_target; }
struct accessibility_typing_result accessibility_typing_process(enum accessibility_typing_input input,
    int target, int position_x, int position_y, uint32_t milliseconds)
{ (void)input; (void)target; (void)position_x; (void)position_y; (void)milliseconds; return fixture_result; }
static void kbd_typing_focus(struct keyboard_parameters *parameters, int target)
{ (void)parameters; (void)target; ++fixture_focus_calls; }
static bool talk_menus_enabled(const void *settings) { (void)settings; return true; }
static uint32_t get_kbd_ch(struct keyboard_parameters *parameters, int position_x, int position_y)
{ (void)parameters; (void)position_x; (void)position_y; return 'a'; }
static void kbd_spellchar(uint32_t character) { (void)character; talk_id(20, false); }
static void kbd_speak_typing_target(int target) { (void)target; talk_id(21, false); }
static void keyclick_click_gesture(int action) { (void)action; ++fixture_gesture_calls; }
'''
KEYBOARD_CASES = r'''
int main(void)
{
    struct keyboard_parameters keyboard = {0};
    struct screen screen = {0};
    struct edit_state state = {0};
    for (int mode = 0; mode <= 2; ++mode)
    {
        fixture_mode(mode);
        fixture_result = (struct accessibility_typing_result){-1, -1, false};
        fixture_target = ACCESSIBILITY_TYPING_NO_TARGET;
        fixture_touch = (struct touchevent){TOUCHEVENT_PRESS, 5, 5, 0};
        fixture_touch_ready = true;
        CHECK(keyboard_accessible_touch(&keyboard, &screen, &state) == ACTION_NONE);
        CHECK(fixture_empty_speeches == (mode != 0) && fixture_clicks == (mode != 2));
        point_force = false;
        for (int index = 0; index < 100; ++index)
        {
            fixture_touch.type = TOUCHEVENT_CONTACT;
            fixture_touch_ready = true;
            CHECK(keyboard_accessible_touch(&keyboard, &screen, &state) == ACTION_NONE);
        }
        CHECK(fixture_empty_speeches == (mode != 0));
        for (int target = 0; target >= ACCESSIBILITY_TYPING_CURSOR_RIGHT; --target)
        {
            if (target == ACCESSIBILITY_TYPING_NO_TARGET) continue;
            fixture_target = target;
            fixture_touch_ready = true;
            fixture_result.focus = target;
            fixture_result.speak = true;
            int before = fixture_occupied_speeches;
            CHECK(keyboard_accessible_touch(&keyboard, &screen, &state) == ACTION_NONE);
            CHECK(fixture_occupied_speeches == before + 1 && state.redraw);
            CHECK(fixture_empty_speeches == (mode != 0));
        }
        fixture_result = (struct accessibility_typing_result){-1, -1, false};
        fixture_target = ACCESSIBILITY_TYPING_NO_TARGET;
        fixture_touch.type = TOUCHEVENT_NONE;
        fixture_touch_ready = true;
        CHECK(keyboard_accessible_touch(&keyboard, &screen, &state) == ACTION_NONE);
        CHECK(fixture_empty_speeches == (mode != 0));
        fixture_target = ACCESSIBILITY_TYPING_DELETE;
        fixture_result.commit = ACCESSIBILITY_TYPING_DELETE;
        fixture_touch.type = TOUCHEVENT_RELEASE;
        fixture_touch_ready = true;
        int before = fixture_gesture_calls;
        CHECK(keyboard_accessible_touch(&keyboard, &screen, &state) == ACTION_KBD_BACKSPACE);
        CHECK(fixture_gesture_calls == before + 1 && fixture_empty_speeches == (mode != 0));
    }
    return 0;
}
'''

READER_WRAPPERS = r'''
void test_empty_mode(int mode) { empty_feedback_mode = mode; }
void test_touch_setup(void)
{
    test_reader_touch_setup();
    fixture_reports = 0;
}
void test_explore(int row, bool force)
{
    test_reader_touch(row, force);
}
int test_explore_preserves(int row, bool force)
{
    struct text_reader before = reader;
    size_t before_input = input_position, before_audible = audible_position;
    size_t before_interrupted = interrupted_position;
    int before_stops = stops, before_reads = fixture_reads, before_seeks = fixture_seeks;
    int before_speech = speech_count, before_tracked = tracked_count, before_pcm = pcm_remaining;
    int before_channel = channel, before_pauses = pause_calls;
    bool before_busy = busy, before_paused = paused, before_interrupted_flag = read_interrupted_flag;
    test_explore(row, force);
    before.touch_row = reader.touch_row;
    return !memcmp(&before, &reader, sizeof(reader)) && input_position == before_input &&
        audible_position == before_audible && interrupted_position == before_interrupted &&
        stops == before_stops && fixture_reads == before_reads && fixture_seeks == before_seeks &&
        speech_count == before_speech && tracked_count == before_tracked && pcm_remaining == before_pcm &&
        channel == before_channel && pause_calls == before_pauses && busy == before_busy &&
        paused == before_paused && read_interrupted_flag == before_interrupted_flag;
}
void test_set_state(int state) { reader.state = state; }
void test_clear_cache(void) { reader.loaded = false; reader.cache_length = 0; }
int test_reports(void) { return fixture_reports; }
int test_feedback_flag(void) { return reader.feedback; }
'''


class EmptyCallerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if sys.platform == "win32" or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("POSIX integration compiler runs under WSL")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.area = project_materials_root(ROOT) / "r1-empty-radio-20261017" / "empty-feedback" / ("integration-" + stamp)
        cls.area.mkdir(parents=True, exist_ok=False)
        paths = ("apps/accessibility.c", "apps/accessibility.h", "apps/accessibility_typing.h",
                 "apps/gui/bitmap/list.c", "apps/gui/skin_engine/skin_touchsupport.c",
                 "apps/recorder/keyboard.c", "apps/tts_reader.c", "firmware/export/touchscreen.h",
                 "tools/tests/test_tts_reader.py", "tools/tests/test_keyclick_exploration.py",
                 "tools/tests/test_accessibility_empty_integration.py", "lib/utf8proc/utf8proc.c",
                 "lib/utf8proc/utf8proc.h", "lib/utf8proc/utf8proc_data.c")
        cls.inputs = {path: (ROOT / path).read_bytes() for path in paths}
        sources = {path: content.decode("utf-8") for path, content in cls.inputs.items()}
        manager = sources["apps/accessibility.c"]
        policy = policy_projection(manager, sources["apps/accessibility.h"])
        common = widgets.COMMON
        for signature in ("void accessibility_explore_feedback(", "void accessibility_speak_empty("):
            common = common.replace(definition(common, signature), "")
        common = common.replace(", reports, reported_target", "")
        common = common.replace(", reported_occupied", "")
        common = common.replace("static const void *reported_owner;", "")
        common = common.replace("*force = point_force;", "*force = point_force; feedback_pending = true;")
        common = common.replace("(void)enqueue; spoken = label;", "(void)enqueue; spoken = label; "
            "if (label == LANG_ACCESSIBILITY_EMPTY) ++fixture_empty_speeches; else ++fixture_occupied_speeches;")
        common = WIDGET_STATE + common + policy + WIDGET_ENDPOINTS
        common += "\n".join(definition(manager, signature) for signature in (
            "static void accessibility_feedback(", "void accessibility_explore_feedback(",
            "void accessibility_speak_empty("))
        list_function = definition(sources["apps/gui/bitmap/list.c"], "static unsigned list_accessibility_explore(")
        keyboard_header = without_includes(sources["apps/accessibility_typing.h"])
        keyboard_header += definition(sources["firmware/export/touchscreen.h"], "enum touchevent_type") + ";\n"
        keyboard_header += definition(sources["firmware/export/touchscreen.h"], "struct touchevent\n") + ";\n"
        cases = {
            "list": common + LIST_PREFIX + list_function + LIST_CASES,
            "skin": common + widgets.SKIN + definition(sources["apps/gui/skin_engine/skin_touchsupport.c"],
                "static void skin_accessibility_explore(") + SKIN_CASES,
            "keyboard": common.replace(definition(common, "static void point("), "") +
                keyboard_header + KEYBOARD_PREFIX + implementation(sources["apps/recorder/keyboard.c"],
                "static int keyboard_accessible_touch(") + KEYBOARD_CASES,
            "list-bypass-mutant": common + LIST_PREFIX + list_function.replace("accessibility_speak_empty();",
                "talk_id(LANG_ACCESSIBILITY_EMPTY, false);") + LIST_CASES,
        }
        cls.executables = {}
        for name, harness in cases.items():
            for configuration in ("normal", "ubsan"):
                key = name + "-" + configuration
                cls.executables[key] = cls.compile(key, harness, configuration)
        prefix = reader_fixture.HARNESS_PREFIX
        prefix = prefix.replace("{ (void)owner; (void)target; (void)occupied; }",
                                "{ (void)owner; (void)target; (void)occupied; ++fixture_reports; }")
        prefix = "static int fixture_reads, fixture_seeks, fixture_reports;\n" + prefix
        prefix = prefix.replace("static off_t mock_seek(int descriptor, off_t offset, int origin)\n{",
            "static off_t mock_seek(int descriptor, off_t offset, int origin)\n{\n    ++fixture_seeks;")
        prefix = prefix.replace("static ssize_t mock_read(int descriptor, void *buffer, size_t count)\n{",
            "static ssize_t mock_read(int descriptor, void *buffer, size_t count)\n{\n    ++fixture_reads;")
        prefix += policy
        reader_source = without_includes(sources["apps/tts_reader.c"])
        if reader_source.count(GUARD) != 1:
            raise AssertionError("Expected one production early-return policy gate")
        cls.libraries = {}
        for configuration in ("normal", "ubsan"):
            for name, actual in (("reader", reader_source), ("reader-clip", reader_source),
                                 ("reader-bypass-mutant", reader_source.replace(GUARD, "", 1))):
                harness = prefix + actual + reader_fixture.HARNESS_SUFFIX + READER_WRAPPERS
                if name == "reader-clip":
                    harness = harness.replace("#define CONFIG_KEYPAD 1", "#define CONFIG_KEYPAD 2")
                key = name + "-" + configuration
                library = ctypes.CDLL(str(cls.compile(key, harness, configuration, shared=True)))
                library.test_reset.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
                library.test_explore.argtypes = library.test_explore_preserves.argtypes = [ctypes.c_int, ctypes.c_bool]
                library.test_audible.argtypes = [ctypes.c_size_t]
                library.test_position.restype = ctypes.c_long
                library.test_speech.restype = library.test_text.restype = ctypes.c_char_p
                cls.libraries[key] = library
        (cls.area / "provenance.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_sha256": {path: hashlib.sha256(content).hexdigest()
                for path, content in cls.inputs.items()},
            "scope": "actual list/skin/keyboard callers plus production shared mode and stable-feedback functions; "
                "whole reader/utf8proc and existing bounded runtime fixture; selected cached mode/file/UI/speech "
                "endpoints mocked, persistence and real keyclick PCM covered by adjacent tests; no host input/audio/radio",
        }, indent=2), encoding="utf-8")

    @classmethod
    def compile(cls, name, harness, configuration, shared=False):
        source = cls.area / (name + ".c")
        source.write_text(harness, encoding="utf-8")
        executable = cls.area / (name + (".so" if shared else ""))
        command = cls.compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
        if configuration == "ubsan":
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        if shared:
            command += ["-shared", "-fPIC", "-DUTF8PROC_STATIC", "-I", str(ROOT / "lib/utf8proc"),
                        str(ROOT / "lib/utf8proc/utf8proc.c")]
        command += [str(source), "-o", str(executable)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=90)
        (cls.area / (name + "-build.json")).write_text(json.dumps(dict(
            command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            harness_sha256=hashlib.sha256(harness.encode()).hexdigest()), indent=2), encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stderr)
        imports = subprocess.run(["nm", "-u", str(executable)], text=True, capture_output=True, timeout=30)
        symbols = {line.split()[-1].split("@")[0] for line in imports.stdout.splitlines() if line.split()}
        forbidden = {"open", "open64", "read", "write", "close", "fsync", "rename", "remove",
                     "system", "execve", "fork", "socket", "ioctl", "reboot", "kill"}
        (cls.area / (name + "-imports.log")).write_text(imports.stdout + imports.stderr, encoding="utf-8")
        if imports.returncode or symbols & forbidden:
            raise AssertionError("Unmocked core operations: " + repr(symbols & forbidden))
        return executable

    def widget(self, name, mutant=False):
        for configuration in ("normal", "ubsan"):
            with self.subTest(configuration=configuration):
                result = subprocess.run([str(self.executables[name + "-" + configuration])],
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode == 0, not mutant, result.stdout + result.stderr)

    def reset_reader(self, library, mode=0, data=b"one two three four"):
        self.data = ctypes.create_string_buffer(data)
        library.test_reset(self.data, len(self.data.value))
        library.test_touch_setup()
        library.test_empty_mode(mode)

    def test_lists_obey_shared_modes_occupied_speech_and_stable_contact(self):
        self.widget("list")

    def test_skins_report_empty_only_once_without_changing_occupied_behavior(self):
        self.widget("skin")

    def test_keyboard_no_target_only_keeps_keys_controls_commits_and_poll_inert(self):
        self.widget("keyboard")

    def test_direct_list_empty_speech_mutation_is_detected(self):
        self.widget("list-bypass-mutant", mutant=True)

    def test_silent_empty_touch_cannot_interrupt_sync_reload_or_change_any_reader_state(self):
        for configuration in ("normal", "ubsan"):
            library = self.libraries["reader-" + configuration]
            for state in range(4):
                for cached in (False, True):
                    with self.subTest(configuration=configuration, state=state, cached=cached):
                        self.reset_reader(library)
                        library.test_step()
                        library.test_audible(4)
                        library.test_set_state(state)
                        if not cached:
                            library.test_clear_cache()
                        self.assertEqual(library.test_explore_preserves(-1, True), 1)
                        self.assertEqual(library.test_reports(), 1)
                        self.assertEqual(library.test_position(), 0)
                        self.assertEqual(library.test_explore_preserves(-1, False), 1)

    def test_reader_policy_guard_removal_causally_reproduces_the_interruption(self):
        for configuration in ("normal", "ubsan"):
            with self.subTest(configuration=configuration):
                library = self.libraries["reader-bypass-mutant-" + configuration]
                self.reset_reader(library)
                library.test_step()
                library.test_audible(4)
                self.assertEqual(library.test_explore_preserves(-1, True), 0)
                self.assertEqual(library.test_stops(), 1)
                self.assertEqual(library.test_position(), 4)
                self.assertEqual(library.test_speech(1), b"No item")

    def test_silent_empty_touch_preserves_actual_paused_synthesis_and_pcm(self):
        for configuration in ("normal", "ubsan"):
            with self.subTest(configuration=configuration):
                library = self.libraries["reader-" + configuration]
                self.reset_reader(library)
                library.test_step()
                library.test_audible(4)
                library.test_toggle()
                self.assertEqual(library.test_paused(), 1)
                self.assertEqual(library.test_state(), 1)
                self.assertEqual(library.test_position(), 4)
                self.assertEqual(library.test_explore_preserves(-1, True), 1)
                self.assertEqual(library.test_paused(), 1)
                self.assertEqual(library.test_pcm(), 4096)

    def test_enabled_empty_speech_retains_last_heard_resume_and_jitter_suppression(self):
        for configuration in ("normal", "ubsan"):
            library = self.libraries["reader-" + configuration]
            for mode in (1, 2):
                with self.subTest(configuration=configuration, mode=mode):
                    self.reset_reader(library, mode)
                    library.test_step()
                    library.test_audible(4)
                    library.test_explore(-1, True)
                    self.assertEqual(library.test_stops(), 1)
                    self.assertEqual(library.test_position(), 4)
                    self.assertEqual(library.test_state(), 0)
                    self.assertEqual(library.test_feedback_flag(), 1)
                    self.assertEqual(library.test_speech(1), b"No item")
                    self.assertEqual(library.test_tracked_count(), 1)
                    library.test_explore(-1, False)
                    self.assertEqual(library.test_stops(), 1)
                    self.assertEqual(library.test_speech_count(), 2)
                    library.test_audio(0, 0)
                    library.test_step()
                    self.assertEqual(library.test_tracked_count(), 2)
                    self.assertEqual(library.test_speech(2), b"two three four")

    def test_occupied_reader_rows_still_speak_in_sound_only_mode(self):
        for configuration in ("normal", "ubsan"):
            library = self.libraries["reader-" + configuration]
            for row in range(5):
                with self.subTest(configuration=configuration, row=row):
                    self.reset_reader(library)
                    library.test_step()
                    library.test_audible(4)
                    library.test_explore(row, True)
                    self.assertEqual(library.test_stops(), 1)
                    self.assertEqual(library.test_position(), 4)
                    self.assertNotEqual(library.test_speech(1), b"No item")

    def test_enabled_empty_feedback_after_external_notice_keeps_interrupted_last_heard_cursor(self):
        for configuration in ("normal", "ubsan"):
            for mode in (1, 2):
                with self.subTest(configuration=configuration, mode=mode):
                    library = self.libraries["reader-" + configuration]
                    self.reset_reader(library, mode)
                    library.test_step()
                    library.test_audible(4)
                    library.test_external_notice()
                    library.test_explore(-1, True)
                    self.assertEqual(library.test_position(), 4)
                    self.assertEqual(library.test_stops(), 2)
                    self.assertEqual(library.test_speech(2), b"No item")
                    library.test_audio(0, 0)
                    library.test_step()
                    self.assertEqual(library.test_speech(3), b"two three four")
                    self.assertEqual(library.test_tracked_count(), 2)

    def test_enabled_empty_feedback_resumes_at_a_complete_utf8_last_heard_character(self):
        data = "one żółw dalej".encode("utf-8")
        for configuration in ("normal", "ubsan"):
            for mode in (1, 2):
                with self.subTest(configuration=configuration, mode=mode):
                    library = self.libraries["reader-" + configuration]
                    self.reset_reader(library, mode, data)
                    library.test_step()
                    library.test_audible(5)
                    library.test_explore(-1, True)
                    self.assertEqual(library.test_position(), 4)
                    library.test_audio(0, 0)
                    library.test_step()
                    self.assertEqual(library.test_speech(2), data[4:])

    def test_all_existing_reader_assertions_pass_with_the_extended_policy_provider(self):
        for configuration in ("normal", "ubsan"):
            with self.subTest(configuration=configuration):
                result = unittest.TestResult()
                library = self.libraries["reader-" + configuration]
                library.test_chunk.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_long)]
                library.test_seek.argtypes = [ctypes.c_int, ctypes.c_long, ctypes.c_int, ctypes.POINTER(ctypes.c_long)]
                library.test_short_reads.argtypes = [ctypes.c_size_t]
                library.test_fail_after.argtypes = [ctypes.c_long]
                library.test_error.argtypes = [ctypes.c_char_p]
                library.test_bookmark_offset.restype = ctypes.c_long
                library.test_signature.restype = ctypes.c_uint32
                library.test_restore.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_int, ctypes.c_uint32]
                library.test_property.restype = library.test_label.restype = library.test_row.restype = ctypes.c_char_p
                library.test_largest_read.restype = ctypes.c_size_t
                for name in unittest.defaultTestLoader.getTestCaseNames(reader_fixture.TextReaderTests):
                    case = reader_fixture.TextReaderTests(name)
                    case.library = library
                    case.clip_library = self.libraries["reader-clip-" + configuration]
                    case.run(result)
                report = dict(tests=result.testsRun, failures=[(str(test), trace) for test, trace in result.failures],
                              errors=[(str(test), trace) for test, trace in result.errors], skips=result.skipped)
                (self.area / ("legacy-reader-" + configuration + ".json")).write_text(
                    json.dumps(report, indent=2), encoding="utf-8")
                self.assertTrue(result.wasSuccessful(), report)

    @classmethod
    def tearDownClass(cls):
        changed = [path for path, content in cls.inputs.items() if (ROOT / path).read_bytes() != content]
        if changed:
            raise AssertionError("Integration sources changed during test: " + ", ".join(changed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
