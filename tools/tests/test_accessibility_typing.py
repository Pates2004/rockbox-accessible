"""Compile production typing, keyboard input and UTF-8 editing with a private host."""

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
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root
from test_keyclick_pcm import definition


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "apps/accessibility_typing.c", "apps/accessibility_typing.h",
    "apps/recorder/keyboard.c", "apps/keyboard.h", "firmware/common/unicode.c",
    "tools/tests/test_accessibility_typing.py",
    "apps/accessibility.c", "apps/accessibility.h",
)
HEADER = b"RBACCESSIBILITY-TYPING:1\nmode:"


def function(source, name):
    match = re.search(r"^[\w *]+\b" + re.escape(name) + r"\([^;]*?\n\{.*?^\}",
                      source, re.MULTILINE | re.DOTALL)
    if not match:
        raise AssertionError(f"Cannot extract production function {name}")
    return match[0] + "\n"


PREAMBLE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <fcntl.h>
#include <assert.h>
#define HAVE_TOUCHSCREEN
#define HAVE_ESPEAK
#define HAVE_KBD_POINT_MODE
#define HIBY_R1
#define ROCKBOX_DIR "/.rockbox"
#define HZ 100
#define BUTTON_NONE 0
#define ALLOW_SOFTLOCK 0x08000000
#define SYS_USB_CONNECTED 0x40000001
#define MENU_ATTACHED_USB 313
#define ID2P(value) (value)
#define STR(value) ((const unsigned char *)(uintptr_t)(value)), (value)
#define SCREEN_MAIN 0
#define LCD_WIDTH 480
#define LCD_HEIGHT 800
#define NB_SCREENS 1
#define FOR_NB_SCREENS(screen_index) for (int screen_index = 0; screen_index < NB_SCREENS; ++screen_index)
#define FONT_UI 1
#define FONT_SYSFIXED 0
#define MIN_GRID_SIZE 44
#define GRID_SIZE(screen, value) ((value) > MIN_GRID_SIZE ? (value) : MIN_GRID_SIZE)
#define MAX(first, second) ((first) > (second) ? (first) : (second))
#define KBD_BUF_SIZE 500
#define KBD_SPACE 0x2423
#define CHANGED_PICKER 1
#define CHANGED_CURSOR 2
#define CHANGED_TEXT 3
#define MASK 0xc0
#define COMP 0x80
typedef uint16_t ucschar_t;
static long current_tick;
static struct { bool list_wraparound; } global_settings;
struct opt_items { const unsigned char *string; int32_t voice_id; };
enum optiontype { RB_INT };
static unsigned char disk_data[128], temp_data[128];
static size_t disk_size, temp_size, disk_offset;
static bool disk_exists;
static int fault, read_chunk, write_chunk, write_calls, rename_calls, sync_calls;
static int menu_choice, menu_result, splash_label, spoken[1024], spoken_count;
static int clicks, wait_calls, legacy_calls, minimum_timeout, action_offset, action_count;
static int theme_disabled, theme_restored, last_font;
static int screen_clears, screen_updates, picker_draws, timeout_count;
static int observed_timeouts[1024];
static bool observed_blinks[1024];
static bool viewport_failure;
static bool enabled = true;
static unsigned char spelled[1024];
static int touch_mode;
struct scripted_action { int action, type, x, y; long tick; };
static struct scripted_action script[1024];

static int host_open(const char *path, int flags, ...)
{
    if (flags == O_RDONLY)
    {
        if (strcmp(path, ROCKBOX_DIR "/accessibility-typing.cfg") || !disk_exists || fault == 1)
            return -1;
        disk_offset = 0;
        return 10;
    }
    if (strcmp(path, ROCKBOX_DIR "/accessibility-typing.cfg.tmp") || fault == 4)
        return -1;
    temp_size = 0;
    return 11;
}
static ssize_t host_read(int descriptor, void *buffer, size_t capacity)
{
    assert(descriptor == 10);
    if (fault == 2) return -1;
    size_t count = disk_size - disk_offset;
    if (count > capacity) count = capacity;
    if (read_chunk && count > (size_t)read_chunk) count = read_chunk;
    memcpy(buffer, disk_data + disk_offset, count);
    disk_offset += count;
    return count;
}
static ssize_t host_write(int descriptor, const void *buffer, size_t count)
{
    assert(descriptor == 11);
    ++write_calls;
    if (fault == 5) return -1;
    if (fault == 9) return 0;
    if (write_chunk && count > (size_t)write_chunk) count = write_chunk;
    assert(temp_size + count < sizeof(temp_data));
    memcpy(temp_data + temp_size, buffer, count);
    temp_size += count;
    return count;
}
static int host_fsync(int descriptor)
{
    assert(descriptor == 11);
    ++sync_calls;
    return fault == 6 ? -1 : 0;
}
static int host_close(int descriptor)
{
    return (descriptor == 10 && fault == 3) || (descriptor == 11 && fault == 7) ? -1 : 0;
}
static int host_rename(const char *source, const char *destination)
{
    assert(!strcmp(source, ROCKBOX_DIR "/accessibility-typing.cfg.tmp"));
    assert(!strcmp(destination, ROCKBOX_DIR "/accessibility-typing.cfg"));
    ++rename_calls;
    if (fault == 8) return -1;
    memcpy(disk_data, temp_data, temp_size);
    disk_size = temp_size;
    disk_exists = true;
    return 0;
}
static int host_remove(const char *path)
{
    assert(!strcmp(path, ROCKBOX_DIR "/accessibility-typing.cfg.tmp"));
    temp_size = 0;
    return 0;
}
#define open host_open
#define read host_read
#define write host_write
#define fsync host_fsync
#define close host_close
#define rename host_rename
#define remove host_remove
static const unsigned char *str(int label) { return (const unsigned char *)(uintptr_t)label; }
static bool set_option(const unsigned char *title, int *choice, enum optiontype kind,
                       const struct opt_items *items, int count, void *callback)
{
    (void)title; (void)kind; (void)items; (void)callback;
    assert(count == 3);
    if (menu_choice >= 0) *choice = menu_choice;
    return menu_result;
}
static void talk_id(int label, bool enqueue)
{
    (void)enqueue;
    assert(spoken_count < 1024);
    spoken[spoken_count++] = label;
}
static void host_splash(int ticks, intptr_t label) { (void)ticks; splash_label = label; }
#define splash(ticks, label) host_splash(ticks, (intptr_t)(label))
static bool talk_menus_enabled(const void *settings) { (void)settings; return true; }
static void talk_spell(const void *text, bool enqueue)
{
    (void)enqueue;
    snprintf((char *)spelled, sizeof(spelled), "%s", (const char *)text);
}
static bool accessibility_enabled(void) { return enabled; }
static void action_wait_for_release(void) { ++wait_calls; }
static int default_event_handler(int action) { return action; }
static void keyclick_click_gesture(int action) { (void)action; ++clicks; }
static void beep_play(int frequency, int duration, int amplitude)
{ (void)frequency; (void)duration; (void)amplitude; }
static bool text_is_rtl(const unsigned char *text) { (void)text; return false; }
static ucschar_t hangul_join(ucschar_t lead, ucschar_t vowel, ucschar_t tail)
{ (void)lead; (void)vowel; (void)tail; return 0xfffd; }
static void viewportmanager_theme_enable(int screen, bool enabled_value, void *viewport)
{ (void)screen; (void)enabled_value; (void)viewport; ++theme_disabled; }
static void viewportmanager_theme_undo(int screen, bool enabled_value)
{ (void)screen; (void)enabled_value; ++theme_restored; }
struct viewport { int x, y, width, height, font; };
struct screen
{
    int screen_type;
    int (*getwidth)(void);
    int (*getheight)(void);
    int (*getcharheight)(void);
    void (*clear_display)(void);
    void (*update)(void);
    void (*setfont)(int);
};
static int screen_width(void) { return LCD_WIDTH; }
static int screen_height(void) { return LCD_HEIGHT; }
static int character_height(void) { return 16; }
static void screen_clear(void) { ++screen_clears; }
static void screen_update(void) { ++screen_updates; }
static void screen_font(int font) { last_font = font; }
static struct screen screens[1] = {
    { 0, screen_width, screen_height, character_height, screen_clear, screen_update, screen_font }
};
'''

KEYBOARD_HOST = r'''
enum touchscreen_mode touchscreen_get_mode(void) { return touch_mode; }
void touchscreen_set_mode(enum touchscreen_mode mode) { touch_mode = mode; }
static struct keyboard_parameters kbd_param[NB_SCREENS];
static bool kbd_loaded;
static int test_picker_lines = 8, test_picker_pages = 3;
static struct viewport test_viewports[3];
static int kbd_create_viewports(struct keyboard_parameters *parameters)
{
    if (viewport_failure) return 0;
    parameters->kbd_viewports = test_viewports;
    return 1;
}
static void kbd_calc_pm_params(struct keyboard_parameters *parameters,
                               struct screen *screen, struct edit_state *state)
{
    (void)screen; (void)state;
    parameters->font_w = 44;
    parameters->font_h = 44;
    parameters->max_chars = 10;
    parameters->lines = test_picker_lines;
    parameters->pages = test_picker_pages;
    parameters->show_buttons = true;
}
static void keyboard_layout(struct viewport *viewports,
                             struct keyboard_parameters *parameters, struct screen *screen)
{
    (void)parameters; (void)screen;
    viewports[eKBD_VP_TEXT] = (struct viewport){ .width = LCD_WIDTH, .height = 44 };
    viewports[eKBD_VP_PICKER] = (struct viewport){ .y = 48, .width = LCD_WIDTH, .height = 352 };
}
static void kbd_calc_vp_params(struct keyboard_parameters *parameters,
                               struct screen *screen, struct edit_state *state)
{ (void)parameters; (void)screen; (void)state; }
static void kbd_draw_picker(struct keyboard_parameters *parameters,
                            struct screen *screen, struct edit_state *state)
{
    (void)parameters; (void)screen;
    assert(picker_draws < 1024);
    observed_blinks[picker_draws++] = state->cur_blink;
}
static void kbd_draw_edit_line(struct keyboard_parameters *parameters,
                               struct screen *screen, struct edit_state *state)
{ (void)parameters; (void)screen; (void)state; }
static void kbd_draw_buttons(struct keyboard_parameters *parameters, struct screen *screen)
{ (void)parameters; (void)screen; }
static int keyboard_touchscreen(struct keyboard_parameters *parameters,
                                struct screen *screen, struct edit_state *state)
{ (void)parameters; (void)screen; (void)state; ++legacy_calls; return ACTION_NONE; }
static int get_action(int context, int timeout)
{
    assert(timeout_count < 1024);
    observed_timeouts[timeout_count++] = timeout;
    if (!minimum_timeout || timeout < minimum_timeout) minimum_timeout = timeout;
    if (action_offset >= action_count) return ACTION_KBD_DONE;
    struct scripted_action event = script[action_offset++];
    empty_feedback_force = event.type == TOUCHEVENT_PRESS;
    current_tick = event.tick < 0 ? current_tick + timeout : event.tick;
    if (event.type == -2)
    {
        accessibility_typing_cancel_touch();
        return ACTION_NONE;
    }
    if (event.type < 0) return event.action;
    struct touchevent raw = { .type = event.type, .x = event.x, .y = event.y, .tick = event.tick };
    return accessibility_typing_handle_touch(&raw, context);
}
'''

PROBES = r'''
void probe_reset(void)
{
    accessibility_typing_end();
    empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
    feedback_valid = feedback_occupied = empty_speech_pending = empty_feedback_force = false;
    feedback_owner = NULL;
    feedback_target = 0;
    loaded = false;
    selected_mode = ACCESSIBILITY_TYPING_LIFT;
    disk_exists = false;
    disk_size = temp_size = disk_offset = 0;
    fault = read_chunk = write_chunk = write_calls = rename_calls = sync_calls = 0;
    menu_choice = -1;
    menu_result = splash_label = spoken_count = clicks = wait_calls = legacy_calls = 0;
    minimum_timeout = action_offset = action_count = 0;
    screen_clears = screen_updates = picker_draws = timeout_count = 0;
    current_tick = 0;
    theme_disabled = theme_restored = last_font = 0;
    viewport_failure = false;
    enabled = true;
    touch_mode = TOUCHSCREEN_POINT;
    global_settings.list_wraparound = false;
    memset(spelled, 0, sizeof(spelled));
    memset(kbd_param, 0, sizeof(kbd_param));
    kbd_loaded = false;
    test_picker_lines = 8;
    test_picker_pages = 3;
}
void probe_empty_mode(int mode) { empty_feedback_mode = mode; }
int probe_empty_speeches(void)
{
    int count = 0;
    for (int index = 0; index < spoken_count; ++index)
        count += spoken[index] == LANG_ACCESSIBILITY_EMPTY;
    return count;
}
void probe_empty_repeat(void) { accessibility_speak_empty(); }
void probe_disk(const char *data, size_t length)
{
    assert(length <= sizeof(disk_data));
    memcpy(disk_data, data, length);
    disk_size = length;
    disk_exists = true;
    loaded = false;
}
const char *probe_disk_text(void)
{
    disk_data[disk_size] = 0;
    return (const char *)disk_data;
}
void probe_fault(int value, int chunk_read, int chunk_write)
{ fault = value; read_chunk = chunk_read; write_chunk = chunk_write; }
void probe_menu(int choice, int result) { menu_choice = choice; menu_result = result; }
int probe_stat(int index)
{
    int values[] = {write_calls, rename_calls, sync_calls, splash_label, clicks, wait_calls,
        legacy_calls, minimum_timeout, action_offset, spoken_count, theme_disabled,
        theme_restored, last_font, screen_clears, screen_updates, picker_draws, timeout_count};
    assert(index >= 0 && index < (int)(sizeof(values)/sizeof(values[0])));
    return values[index];
}
int probe_spoken(int index) { assert(index >= 0 && index < spoken_count); return spoken[index]; }
const unsigned char *probe_spelled(void) { return spelled; }
void probe_action(int action)
{
    assert(action_count < 1024);
    script[action_count++] = (struct scripted_action){ .action = action, .type = -1 };
}
void probe_idle(void)
{
    assert(action_count < 1024);
    script[action_count++] = (struct scripted_action){ .action = ACTION_NONE, .type = -1, .tick = -1 };
}
int probe_timeout(int index) { assert(index >= 0 && index < timeout_count); return observed_timeouts[index]; }
bool probe_blink(int index) { assert(index >= 0 && index < picker_draws); return observed_blinks[index]; }
void probe_touch(int type, int x, int y, long tick)
{
    assert(action_count < 1024);
    script[action_count++] = (struct scripted_action){ .type = type, .x = x, .y = y, .tick = tick };
}
void probe_cancel(void)
{
    assert(action_count < 1024);
    script[action_count++] = (struct scripted_action){ .type = -2 };
}
int probe_run(char *text, int capacity) { return kbd_input(text, capacity, NULL); }
int probe_run_ex(char *text, int capacity, bool *usb)
{ return kbd_input_ex(text, capacity, NULL, usb); }
void probe_fail_viewport(void) { viewport_failure = true; }
void probe_enabled(bool value) { enabled = value; }
void probe_wrap(bool value) { global_settings.list_wraparound = value; }
int probe_run_numeric(char *text, int capacity)
{
    static ucschar_t digits[] = {
        10, '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 0xfeff
    };
    /* Geometry is fixture input; navigation and input loop remain production C. */
    test_picker_lines = test_picker_pages = 1;
    return kbd_input_ex(text, capacity, digits, NULL);
}
static struct edit_state picker_probe_state;
void probe_picker_set(int lines, int editing, int row, int control, int wrap)
{
    struct keyboard_parameters *pm = kbd_param;
    pm->lines = lines;
    pm->line_edit = editing;
    pm->y = row;
    pm->typing_control = control;
    global_settings.list_wraparound = wrap;
    memset(&picker_probe_state, 0, sizeof(picker_probe_state));
}
void probe_picker_vertical(int direction)
{
    kbd_move_picker_vertical(kbd_param, &picker_probe_state, direction);
}
int probe_picker_value(int index)
{
    int values[] = {kbd_param->y, kbd_param->line_edit, kbd_param->typing_control};
    assert(index >= 0 && index < 3);
    return values[index];
}
int probe_hit(int x, int y) { return kbd_typing_hit(kbd_param, screens, x, y); }
void probe_short_row(void)
{
    static ucschar_t row[] = {3, 'a', 'b', 'c', 0xfeff};
    kbd_param->kbd_viewports = test_viewports;
    kbd_param->kbd_buf_ptr = row;
    kbd_param->font_w = kbd_param->font_h = 44;
    kbd_param->max_chars = 10;
    kbd_param->lines = kbd_param->pages = 1;
    kbd_param->page = 0;
    kbd_param->show_buttons = true;
    keyboard_layout(test_viewports, kbd_param, screens);
}
int probe_forward(int type, int context)
{
    struct touchevent event = { .type = type, .x = 99, .y = 88, .tick = 42 };
    return accessibility_typing_handle_touch(type < 0 ? NULL : &event, context);
}
int probe_take(void)
{
    struct touchevent event;
    if (!accessibility_typing_take_touch(&event)) return -1;
    return event.type;
}
'''


class TypingResult(ctypes.Structure):
    _fields_ = [("focus", ctypes.c_int), ("commit", ctypes.c_int), ("speak", ctypes.c_bool)]


class AccessibilityTypingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or not shutil.which(compiler[0]):
            raise unittest.SkipTest("A native C compiler is required; run under WSL")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, [central.name])
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = confined_path(central / "r1-hardening-20261015" / "typing-curtain" / "typing-tests" /
                                     (stamp + "-" + uuid.uuid4().hex[:8]), central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
        cls.compiler = compiler
        cls.records = []
        cls.addClassCleanup(cls.report)
        typing = (ROOT / INPUTS[0]).read_text(encoding="utf-8")
        header = (ROOT / INPUTS[1]).read_text(encoding="utf-8")
        keyboard = (ROOT / INPUTS[2]).read_text(encoding="utf-8")
        unicode = (ROOT / "firmware/common/unicode.c").read_text(encoding="utf-8")
        manager = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        manager_header = (ROOT / "apps/accessibility.h").read_text(encoding="utf-8")
        action = (ROOT / "apps/action.h").read_text(encoding="utf-8")
        action_defines = "\n".join(re.findall(r"^#define CONTEXT_[^\n]+", action, re.MULTILINE))
        action_enums = action[action.index("enum {"):action.index("struct button_mapping {")]
        labels = sorted(set(re.findall(r"\b(?:LANG|VOICE)_[A-Z0-9_]+", keyboard + typing)) |
                        {"LANG_ACCESSIBILITY_EMPTY"})
        cls.constants = {name: index + 1000 for index, name in enumerate(labels)}
        label_defines = "\n".join(f"#define {name} {value}" for name, value in cls.constants.items())
        structs = "\n".join(re.search(r"^struct " + name + r"\n\{.*?^\};",
                                      keyboard, re.MULTILINE | re.DOTALL)[0]
                            for name in ["keyboard_parameters", "edit_state"])
        viewport_enum = re.search(r"^enum ekbd_viewports\n\{.*?^\};", keyboard,
                                  re.MULTILINE | re.DOTALL)[0]
        unicode_functions = "\n".join(function(unicode, name) for name in [
            "utf8_ucs_get_extra_bytes_count", "utf8encode_internal", "utf8encode",
            "utf8decode", "utf8length", "utf8seek"])
        keyboard_functions = "\n".join(function(keyboard, name) for name in [
            "kbd_spellchar", "kbd_inschar", "kbd_delchar", "get_kbd_ch", "get_kbd_row_len",
            "kbd_insert_selected", "kbd_backspace", "kbd_move_cursor", "kbd_speak_typing_target",
            "kbd_typing_hit", "kbd_typing_focus", "keyboard_accessible_touch",
            "kbd_move_picker_horizontal", "kbd_move_picker_vertical", "kbd_input_ex", "kbd_input"])
        feedback = function(PREAMBLE, "accessibility_explore_feedback")
        state = (
            "static bool feedback_valid, feedback_occupied, empty_speech_pending, empty_feedback_force;\n"
            "static const void *feedback_owner;\nstatic int feedback_target;\n"
            "static void accessibility_feedback(const void *owner, int target, bool occupied, "
            "bool force, bool single_tap);\n")
        forwarding = feedback.rstrip()[:-1] + (
            "    accessibility_feedback(owner, target, occupied, empty_feedback_force, false);\n}\n")
        preamble = PREAMBLE.replace(feedback.rstrip(), state + forwarding, 1)
        policy = definition(manager_header, "enum accessibility_empty_feedback\n") + ";\n"
        policy += (
            "static enum accessibility_empty_feedback empty_feedback_mode;\n"
            "static void accessibility_empty_load(void) {}\n"
            "static void keyclick_click_touch_target(bool occupied, bool single_tap) "
            "{ (void)occupied; (void)single_tap; }\n")
        policy += "\n".join(function(manager, name) for name in (
            "accessibility_empty_feedback_mode", "accessibility_empty_speech_enabled",
            "accessibility_feedback", "accessibility_speak_empty"))
        unit = preamble + action_defines + "\n" + action_enums + label_defines + "\n" + policy
        unit += header + "\n" + (ROOT / "firmware/export/touchscreen.h").read_text(encoding="utf-8")
        unit += re.sub(r"^\s*#include[^\n]*", "", typing, flags=re.MULTILINE)
        unit += "\n" + viewport_enum + "\n" + structs + "\n" + KEYBOARD_HOST
        unit += "static const unsigned char utf8comp[6] = {0, 0xc0, 0xe0, 0xf0, 0xf8, 0xfc};\n"
        unit += unicode_functions + keyboard_functions + PROBES
        names = sorted((set(re.findall(r"\b(?:ACTION_KBD|CONTEXT|TOUCHEVENT|ACCESSIBILITY_TYPING)_[A-Z0-9_]+",
                                       keyboard + typing + header)) - {"ACCESSIBILITY_TYPING_H"}) |
                       {"ACTION_NONE", "ACTION_TOUCHSCREEN", "CONTEXT_STD", "CONTEXT_PLUGIN"})
        unit += ("\nint probe_constant(int index) { static const int values[] = {" +
                 ",".join(names) + "}; return values[index]; }\n")
        source = cls.workspace / "typing-keyboard-host.c"
        source.write_text(unit, encoding="utf-8")
        output = cls.workspace / ("typing-host.dll" if os.name == "nt" else "typing-host.so")
        command = compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-pointer-sign",
                              "-Wno-sign-compare", "-shared", "-fPIC", str(source), "-o", str(output)]
        cls.sanitize = bool(os.environ.get("TYPING_SANITIZE"))
        if cls.sanitize:
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (cls.workspace / "compile.stdout.log").write_text(compiled.stdout, encoding="utf-8")
        (cls.workspace / "compile.stderr.log").write_text(compiled.stderr, encoding="utf-8")
        cls.records.append({"argv": command, "returncode": compiled.returncode})
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        cls.library = ctypes.CDLL(str(output))
        cls.library.accessibility_typing_process.argtypes = [ctypes.c_int] * 4 + [ctypes.c_uint32]
        cls.library.accessibility_typing_process.restype = TypingResult
        cls.library.accessibility_typing_set_mode.argtypes = [ctypes.c_int]
        cls.library.accessibility_typing_set_mode.restype = ctypes.c_bool
        cls.library.accessibility_typing_active.restype = ctypes.c_bool
        cls.library.accessibility_typing_needs_poll.restype = ctypes.c_bool
        cls.library.probe_blink.restype = ctypes.c_bool
        cls.library.probe_disk.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        cls.library.probe_disk_text.restype = ctypes.c_char_p
        cls.library.probe_spelled.restype = ctypes.c_char_p
        cls.library.probe_touch.argtypes = [ctypes.c_int] * 3 + [ctypes.c_long]
        cls.library.probe_run.argtypes = [ctypes.c_char_p, ctypes.c_int]
        cls.library.probe_run_ex.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_bool)]
        cls.library.probe_wrap.argtypes = [ctypes.c_bool]
        cls.constants.update({name: cls.library.probe_constant(index) for index, name in enumerate(names)})
        print("Typing behavior evidence:", cls.workspace, flush=True)

    @classmethod
    def report(cls):
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
        (cls.workspace / "report.json").write_text(json.dumps({
            "source_project": str(ROOT), "inputs_before": cls.hashes, "inputs_after": after,
            "sources_stable": cls.hashes == after, "commands": cls.records,
            "sanitizer": getattr(cls, "sanitize", False),
            "production_keyboard_event_loop": True, "display_and_core_services_stubbed": True,
            "physical_hardware_tested": False, "foreground_input_used": False,
        }, indent=2) + "\n", encoding="utf-8")
        if cls.hashes != after:
            raise AssertionError("Assigned typing sources changed during validation")

    def setUp(self):
        self.library.probe_reset()
        self.library.accessibility_typing_begin()

    def constant(self, name):
        return self.constants[name]

    def process(self, kind, target=7, x=0, y=0, time=0):
        return self.library.accessibility_typing_process(
            self.constant("ACCESSIBILITY_TYPING_" + kind), target, x, y, time)

    def mode(self, value):
        self.assertTrue(self.library.accessibility_typing_set_mode(value))

    def tap(self, time, target=7, x=0, y=0):
        self.process("PRESS", target, x, y, time)
        return self.process("RELEASE", target, x, y, time + 20)

    def expect_none(self, result):
        self.assertEqual(result.commit, -1)

    def test_lift_commits_once_and_ignores_unpaired_release(self):
        self.expect_none(self.process("RELEASE"))
        self.assertTrue(self.process("PRESS").speak)
        self.assertEqual(self.process("RELEASE", time=10).commit, 7)
        self.expect_none(self.process("RELEASE", time=20))
        self.expect_none(self.process("POLL", time=300))

    def test_lift_explores_fast_without_dwell_or_repeated_speech(self):
        self.process("PRESS", 1)
        result = self.process("CONTACT", 2, 60, 0, 10)
        self.assertTrue(result.speak)
        self.assertEqual(result.focus, 2)
        self.expect_none(result)
        self.assertFalse(self.process("CONTACT", 2, 65, 0, 20).speak)
        self.assertEqual(self.process("RELEASE", 3, 110, 0, 30).commit, 3)

    def test_lift_long_contact_remains_single_commit(self):
        self.process("PRESS")
        for time in [50, 180, 200, 220, 1000, 100000]:
            self.expect_none(self.process("POLL", time=time))
        self.assertEqual(self.process("RELEASE", time=100001).commit, 7)

    def test_outside_or_gap_cancels_even_if_contact_returns(self):
        for invalid in [-1, -8]:
            self.library.accessibility_typing_cancel_touch()
            self.process("PRESS")
            self.expect_none(self.process("CONTACT", invalid, -1, 0, 10))
            self.expect_none(self.process("RELEASE", time=20))
            self.assertEqual(self.tap(100).commit, 7)

    def test_invalid_start_and_release_never_commit(self):
        self.process("PRESS", -1)
        self.expect_none(self.process("RELEASE", time=20))
        self.process("PRESS", time=100)
        self.expect_none(self.process("RELEASE", -1, time=120))

    def test_cancel_clears_lift_and_pending_double_tap(self):
        for mode in [0, 1]:
            self.mode(mode)
            self.tap(0)
            self.process("PRESS", time=100)
            self.library.accessibility_typing_cancel_touch()
            self.expect_none(self.process("RELEASE", time=120))
            if mode:
                self.expect_none(self.tap(200))

    def test_double_tap_commits_focused_key_at_different_coordinates_once(self):
        self.mode(1)
        self.process("PRESS", 4)
        self.process("CONTACT", 8, 60, 0, 10)
        self.expect_none(self.process("RELEASE", 8, 60, 0, 20))
        self.expect_none(self.tap(100, 99, 250, 200))
        self.assertEqual(self.tap(200, 55, 350, 300).commit, 8)
        self.expect_none(self.process("RELEASE", 55, 350, 300, 230))
        self.expect_none(self.tap(250, 55, 350, 300))

    def test_double_tap_deadline_boundary_and_expiry(self):
        self.mode(1)
        self.expect_none(self.tap(100))
        self.assertEqual(self.tap(420).commit, 7)
        self.expect_none(self.tap(500))
        self.expect_none(self.tap(821))

    def test_double_tap_exploration_resets_candidate(self):
        self.mode(1)
        self.tap(0)
        self.process("PRESS", 9, time=100)
        result = self.process("CONTACT", 10, 60, 0, 110)
        self.assertEqual(result.focus, 10)
        self.assertTrue(result.speak)
        self.expect_none(self.process("RELEASE", 10, 60, 0, 120))
        self.expect_none(self.tap(200))
        self.assertEqual(self.tap(300).commit, 10)

    def test_double_tap_stationary_hold_focuses_without_typing(self):
        self.mode(1)
        self.tap(0, 4)
        self.process("PRESS", 12, time=100)
        result = self.process("POLL", time=320)
        self.assertEqual(result.focus, 12)
        self.assertTrue(result.speak)
        self.expect_none(self.process("RELEASE", 12, time=330))

    def test_double_tap_small_keys_focus_immediately_when_crossing_boundary(self):
        self.mode(1)
        self.tap(0, 4)
        self.process("PRESS", 4, x=0, time=100)
        result = self.process("CONTACT", 5, x=2, time=110)
        self.assertEqual(result.focus, 5)
        self.assertTrue(result.speak)
        self.expect_none(self.process("RELEASE", 5, x=2, time=120))

    def test_double_tap_outside_and_long_taps_do_not_commit(self):
        self.mode(1)
        self.tap(0)
        self.process("PRESS", time=100)
        self.expect_none(self.process("RELEASE", -1, time=120))
        self.expect_none(self.tap(200))
        self.process("PRESS", time=300)
        self.expect_none(self.process("RELEASE", time=481))

    def test_time_wrap_and_backward_time_are_safe(self):
        self.mode(1)
        self.expect_none(self.tap(0xfffffff0))
        self.assertEqual(self.tap(50).commit, 7)
        self.process("PRESS", time=1000)
        self.expect_none(self.process("RELEASE", time=500))

    def test_repeated_press_does_not_accept_stale_time_or_old_double_tap(self):
        self.process("PRESS", time=1000)
        self.process("PRESS", time=1100)
        self.expect_none(self.process("RELEASE", time=500))
        self.mode(1)
        self.tap(2000)
        self.process("PRESS", time=2100)
        self.process("PRESS", time=2110)
        self.expect_none(self.process("RELEASE", time=2120))

    def test_coordinates_at_integer_extremes_do_not_overflow(self):
        self.mode(1)
        self.process("PRESS", x=-2147483648, y=-2147483648)
        result = self.process("CONTACT", 8, 2147483647, 2147483647, 10)
        self.assertEqual(result.focus, 8)
        self.expect_none(self.process("RELEASE", 8, 2147483647, 2147483647, 20))

    def test_arrows_mode_raw_events_are_inert(self):
        self.mode(2)
        for kind in ["PRESS", "CONTACT", "RELEASE", "POLL"]:
            result = self.process(kind)
            self.expect_none(result)
            self.assertFalse(result.speak)

    def test_mode_changes_and_end_invalidate_pending_input(self):
        self.process("PRESS")
        self.mode(1)
        self.expect_none(self.process("RELEASE", time=20))
        self.tap(100)
        self.library.accessibility_typing_end()
        self.expect_none(self.tap(200))
        self.assertFalse(self.library.accessibility_typing_active())

    def test_strict_bounded_config_accepts_only_known_complete_schema(self):
        for mode in range(3):
            data = HEADER + str(mode).encode() + b"\n"
            self.library.probe_disk(data, len(data))
            self.library.probe_fault(0, 1, 0)
            self.assertEqual(self.library.accessibility_typing_mode(), mode)
        invalid = [b"", HEADER, HEADER + b"3\n", HEADER + b"-1\n", HEADER + b"01\n",
                   HEADER + b"1", HEADER + b"1\r\n", HEADER + b"1\nextra", HEADER + b"1\x00\n",
                   HEADER.replace(b":1", b":2") + b"1\n", b"x" * 128]
        for data in invalid:
            self.library.probe_disk(data, len(data))
            self.assertEqual(self.library.accessibility_typing_mode(), 0, data)

    def test_config_read_failures_fall_back_without_writing(self):
        for fault in [1, 2, 3]:
            data = HEADER + b"2\n"
            self.library.probe_disk(data, len(data))
            self.library.probe_fault(fault, 0, 0)
            self.assertEqual(self.library.accessibility_typing_mode(), 0)
            self.assertEqual(self.library.probe_stat(0), 0)

    def test_atomic_save_handles_short_writes_and_reloads(self):
        self.library.probe_fault(0, 1, 1)
        self.mode(2)
        self.assertGreater(self.library.probe_stat(0), 20)
        self.assertEqual(self.library.probe_stat(1), 1)
        self.assertEqual(self.library.probe_stat(2), 1)
        data = self.library.probe_disk_text()
        self.assertEqual(data, HEADER + b"2\n")
        self.library.probe_disk(data, len(data))
        self.assertEqual(self.library.accessibility_typing_mode(), 2)

    def test_all_write_failures_retain_saved_and_active_mode(self):
        for fault in [4, 5, 6, 7, 8, 9]:
            self.library.probe_fault(0, 0, 0)
            self.mode(1)
            original = self.library.probe_disk_text()
            self.library.probe_fault(fault, 0, 0)
            self.assertFalse(self.library.accessibility_typing_set_mode(2), fault)
            self.assertEqual(self.library.accessibility_typing_mode(), 1)
            self.assertEqual(self.library.probe_disk_text(), original)

    def test_invalid_mode_never_writes_and_menu_reports_save_failure(self):
        for mode in [-1, 3, 2147483647]:
            self.assertFalse(self.library.accessibility_typing_set_mode(mode))
        self.assertEqual(self.library.probe_stat(0), 0)
        self.library.probe_fault(4, 0, 0)
        self.library.probe_menu(2, 0)
        self.assertEqual(self.library.accessibility_typing_menu(), 0)
        self.assertEqual(self.library.accessibility_typing_mode(), 0)
        self.assertEqual(self.library.probe_stat(3), self.constant("LANG_ERROR_WRITING_CONFIG"))
        self.assertEqual(self.library.probe_stat(9), 0)

    def test_menu_preserves_usb_and_unchanged_choice(self):
        self.library.probe_menu(2, 1)
        self.assertEqual(self.library.accessibility_typing_menu(), 313)
        self.assertEqual(self.library.probe_stat(0), 0)
        self.library.probe_menu(0, 0)
        self.assertEqual(self.library.accessibility_typing_menu(), 0)
        self.assertEqual(self.library.probe_stat(0), 0)

    def test_forwarding_filters_context_and_consumes_raw_events_once(self):
        keyboard = self.constant("CONTEXT_KEYBOARD")
        self.assertEqual(self.library.probe_forward(1, keyboard), self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.library.probe_take(), 1)
        self.assertEqual(self.library.probe_take(), -1)
        self.assertEqual(self.library.probe_forward(-1, keyboard), self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.library.probe_take(), 0)
        for context in [self.constant("CONTEXT_STD"), keyboard | self.constant("CONTEXT_LOCKED"),
                        keyboard | self.constant("CONTEXT_PLUGIN")]:
            self.assertEqual(self.library.probe_forward(1, context), 0)
            self.assertEqual(self.library.probe_take(), -1)

    def test_raw_queue_overwrite_invalidates_previous_contact(self):
        context = self.constant("CONTEXT_KEYBOARD")
        self.process("PRESS")
        self.library.probe_forward(1, context)
        self.library.probe_forward(3, context)
        self.expect_none(self.process("RELEASE", time=20))

    def action(self, name):
        self.library.probe_action(self.constant(name))

    def touch(self, kind, x, y, ticks):
        self.library.probe_touch(self.constant("TOUCHEVENT_" + kind), x, y, ticks)

    def run_keyboard(self, initial="", capacity=256):
        buffer = ctypes.create_string_buffer(initial.encode("utf-8"), capacity)
        result = self.library.probe_run(buffer, capacity)
        self.assertFalse(self.library.accessibility_typing_active())
        self.assertEqual(self.library.probe_stat(6), 0)
        self.assertIn(self.library.probe_stat(7), [5, 50])
        return result, buffer.value.decode("utf-8")

    def test_actual_keyboard_empty_policy_is_default_silent_and_stable_when_enabled(self):
        for mode in range(3):
            with self.subTest(mode=mode):
                self.library.probe_reset()
                self.library.probe_empty_mode(mode)
                self.touch("PRESS", 479, 47, 0)
                for ticks in range(1, 101):
                    self.touch("CONTACT", 478 + ticks % 2, 46 + ticks % 2, ticks)
                for ticks in range(101, 121):
                    self.touch("NONE", 479, 47, ticks)
                self.touch("RELEASE", 479, 47, 121)
                self.action("ACTION_KBD_DONE")
                self.assertEqual(self.run_keyboard("keep"), (0, "keep"))
                self.assertEqual(self.library.probe_empty_speeches(), int(mode != 0))
                self.assertEqual(self.library.echo_probe_feedback_count(), 102)
                self.assertEqual(self.library.echo_probe_feedback_occupied(101), 0)
                self.library.probe_empty_repeat()
                self.library.probe_empty_repeat()
                self.assertEqual(self.library.probe_empty_speeches(), int(mode != 0))

    def test_actual_keyboard_outside_poll_never_creates_empty_feedback_or_speech(self):
        for mode in range(3):
            with self.subTest(mode=mode):
                self.library.probe_reset()
                self.library.probe_empty_mode(mode)
                for ticks in range(100):
                    self.touch("NONE", 479, 47, ticks)
                self.action("ACTION_KBD_DONE")
                self.assertEqual(self.run_keyboard("keep"), (0, "keep"))
                self.assertEqual(self.library.probe_empty_speeches(), 0)
                self.assertEqual(self.library.echo_probe_feedback_count(), 0)

    def test_actual_keyboard_empty_modes_leave_occupied_editing_and_feedback_unchanged(self):
        observations = []
        for mode in range(3):
            self.library.probe_reset()
            self.library.probe_empty_mode(mode)
            self.touch("PRESS", 10, 60, 0)
            self.touch("CONTACT", 60, 60, 1)
            self.touch("RELEASE", 105, 60, 2)
            self.action("ACTION_KBD_DONE")
            result = self.run_keyboard()
            self.assertEqual(result, (0, "3"))
            self.assertEqual(self.library.probe_empty_speeches(), 0)
            observations.append((result, self.library.probe_stat(4), self.library.probe_stat(5),
                                 self.library.probe_spelled(), self.library.echo_probe_feedback_count()))
        self.assertEqual(observations, [observations[0]] * 3)

    def test_short_polling_is_limited_to_pending_double_tap_contact(self):
        self.assertFalse(self.library.accessibility_typing_needs_poll())
        self.process("PRESS", time=0)
        self.assertFalse(self.library.accessibility_typing_needs_poll())
        self.mode(1)
        self.process("PRESS", time=10)
        self.assertTrue(self.library.accessibility_typing_needs_poll())
        self.process("POLL", time=230)
        self.assertFalse(self.library.accessibility_typing_needs_poll())
        self.process("RELEASE", time=240)
        self.process("PRESS", time=250)
        self.assertTrue(self.library.accessibility_typing_needs_poll())
        self.process("CONTACT", target=-1, time=260)
        self.assertFalse(self.library.accessibility_typing_needs_poll())
        self.library.accessibility_typing_cancel_touch()
        self.assertFalse(self.library.accessibility_typing_needs_poll())
        self.mode(2)
        self.process("PRESS", time=270)
        self.assertFalse(self.library.accessibility_typing_needs_poll())
        self.library.accessibility_typing_end()
        self.assertFalse(self.library.accessibility_typing_needs_poll())

    def test_actual_keyboard_idle_uses_half_second_wake_and_visible_blink(self):
        for mode in range(3):
            self.library.probe_reset()
            self.mode(mode)
            for _ in range(10):
                self.library.probe_idle()
            self.action("ACTION_KBD_DONE")
            self.assertEqual(self.run_keyboard("keep"), (0, "keep"))
            self.assertEqual(self.library.probe_stat(7), 50)
            self.assertEqual(self.library.probe_stat(14), 11)
            self.assertEqual([self.library.probe_blink(index) for index in range(11)],
                             [index % 2 == 0 for index in range(11)])
            self.assertEqual(self.library.probe_stat(13), self.library.probe_stat(14))

    def test_actual_keyboard_repeated_inert_polls_do_not_redraw_or_speak(self):
        self.mode(1)
        for tick in range(50):
            self.touch("NONE", 0, 0, tick)
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_keyboard("keep"), (0, "keep"))
        self.assertEqual(self.library.probe_stat(14), 1)
        self.assertEqual(self.library.probe_stat(9), 0)
        self.assertEqual(self.library.probe_stat(4), 0)

    def test_actual_keyboard_hold_polling_stops_after_exploration(self):
        self.mode(1)
        self.touch("PRESS", 10, 60, 0)
        for tick in [5, 10, 15, 20, 25, 30]:
            self.touch("NONE", 10, 60, tick)
        self.touch("RELEASE", 10, 60, 31)
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_keyboard("keep"), (0, "keep"))
        self.assertEqual([self.library.probe_timeout(index) for index in range(9)],
                         [50, 5, 5, 5, 5, 5, 50, 50, 50])
        self.assertEqual(self.library.probe_stat(14), 2)

    def test_repeated_sessions_release_queue_state_without_writing_settings(self):
        for iteration in range(1000):
            self.library.accessibility_typing_begin()
            self.process("PRESS", target=iteration % 10, time=iteration * 10)
            self.library.probe_forward(1, self.constant("CONTEXT_KEYBOARD"))
            self.library.accessibility_typing_end()
            self.assertFalse(self.library.accessibility_typing_active())
            self.assertFalse(self.library.accessibility_typing_needs_poll())
            self.assertEqual(self.library.probe_take(), -1)
            self.library.accessibility_typing_begin()
            self.expect_none(self.process("RELEASE", time=iteration * 10 + 1))
        self.assertEqual(self.library.probe_stat(0), 0)

    def test_actual_one_row_numeric_keyboard_home_inserts_zero(self):
        self.mode(2)
        for _ in range(12):
            self.action("ACTION_KBD_UP")
        self.action("ACTION_KBD_DOWN")
        for _ in range(32):
            self.action("ACTION_KBD_LEFT")
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_DONE")
        self.library.probe_run_numeric.argtypes = [ctypes.c_char_p, ctypes.c_int]
        buffer = ctypes.create_string_buffer(21)
        self.assertEqual(self.library.probe_run_numeric(buffer, 21), 0)
        self.assertEqual(buffer.value, b"0")
        self.assertFalse(self.library.accessibility_typing_active())

    def test_actual_picker_edit_line_transitions_for_one_and_eight_rows(self):
        self.mode(2)
        no_target = self.constant("ACCESSIBILITY_TYPING_NO_TARGET")
        for lines in (1, 8):
            for wrap in (False, True):
                for direction in (-1, 1):
                    with self.subTest(lines=lines, wrap=wrap, direction=direction):
                        self.library.probe_picker_set(lines, True, 0, no_target, wrap)
                        self.library.probe_picker_vertical(direction)
                        expected = ((0, True, no_target) if direction < 0 and not wrap else
                                    (lines - 1 if direction < 0 else 0, False, no_target))
                        actual = tuple(self.library.probe_picker_value(index) for index in range(3))
                        self.assertEqual(actual, expected)
                        if direction < 0 and not wrap:
                            self.library.probe_picker_vertical(-1)
                            self.assertEqual(tuple(self.library.probe_picker_value(index) for index in range(3)),
                                             (0, True, no_target))
                            self.library.probe_picker_vertical(1)
                            self.assertEqual(tuple(self.library.probe_picker_value(index) for index in range(3)),
                                             (0, False, no_target))

    def test_actual_picker_control_vertical_transitions_preserve_wrap_policy(self):
        self.mode(2)
        no_target = self.constant("ACCESSIBILITY_TYPING_NO_TARGET")
        for lines in (1, 8):
            for wrap in (False, True):
                for name in ("ACCESSIBILITY_TYPING_DONE", "ACCESSIBILITY_TYPING_CANCEL"):
                    control = self.constant(name)
                    for direction in (-1, 1):
                        with self.subTest(lines=lines, wrap=wrap, control=name, direction=direction):
                            self.library.probe_picker_set(lines, False, lines - 1, control, wrap)
                            self.library.probe_picker_vertical(direction)
                            expected = ((lines - 1, False, no_target) if direction < 0 else
                                        (0, True, no_target) if wrap else
                                        (lines - 1, False, control))
                            self.assertEqual(tuple(self.library.probe_picker_value(index) for index in range(3)),
                                             expected)

    def test_actual_one_row_numeric_arrows_keep_done_delete_and_cancel(self):
        self.library.probe_run_numeric.argtypes = [ctypes.c_char_p, ctypes.c_int]
        for horizontal_steps, expected_result, expected_text in ((0, 0, b"abc"), (1, 0, b"ab"), (2, -1, b"abc")):
            with self.subTest(control=horizontal_steps):
                self.library.probe_reset()
                self.library.accessibility_typing_begin()
                self.mode(2)
                self.action("ACTION_KBD_DOWN")
                for _ in range(horizontal_steps):
                    self.action("ACTION_KBD_RIGHT")
                self.action("ACTION_KBD_SELECT")
                if horizontal_steps == 1:
                    self.action("ACTION_KBD_DONE")
                buffer = ctypes.create_string_buffer(b"abc", 21)
                self.assertEqual(self.library.probe_run_numeric(buffer, 21), expected_result)
                self.assertEqual(buffer.value, expected_text)
                self.assertFalse(self.library.accessibility_typing_active())

    def test_actual_keyboard_fast_touch_commits_last_character_once(self):
        self.touch("PRESS", 10, 60, 0)
        self.touch("CONTACT", 60, 60, 1)
        self.touch("RELEASE", 105, 60, 2)
        self.touch("RELEASE", 105, 60, 3)
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_keyboard(), (0, "3"))
        self.assertEqual(self.library.probe_stat(4), 1)
        self.assertEqual(self.library.probe_stat(5), 1)

    def test_actual_keyboard_cancel_between_press_and_release_prevents_insert(self):
        self.touch("PRESS", 10, 60, 0)
        self.library.probe_cancel()
        self.touch("RELEASE", 10, 60, 10)
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_keyboard("keep"), (0, "keep"))
        self.assertEqual(self.library.probe_stat(4), 0)

    def test_actual_keyboard_double_tap_uses_explored_letter(self):
        self.mode(1)
        self.touch("PRESS", 10, 60, 0)
        self.touch("CONTACT", 60, 60, 1)
        self.touch("RELEASE", 60, 60, 2)
        for tick in [10, 20]:
            self.touch("PRESS", 400, 200, tick)
            self.touch("RELEASE", 400, 200, tick + 2)
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_keyboard(), (0, "2"))
        self.assertEqual(self.library.probe_stat(4), 1)

    def test_actual_keyboard_polish_uppercase_punctuation_and_space(self):
        self.mode(2)
        for action in ["ACTION_KBD_PAGE_FLIP", "ACTION_KBD_PAGE_FLIP"]:
            self.action(action)
        for _ in range(6):
            self.action("ACTION_KBD_DOWN")
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_PAGE_FLIP")
        self.action("ACTION_KBD_PAGE_FLIP")
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_DOWN")
        for _ in range(3):
            self.action("ACTION_KBD_RIGHT")
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_keyboard(), (0, "ĄÚ "))

    def test_actual_keyboard_utf8_delete_caret_and_capacity(self):
        self.mode(2)
        for action in ["ACTION_KBD_CURSOR_LEFT", "ACTION_KBD_BACKSPACE", "ACTION_KBD_SELECT",
                       "ACTION_KBD_DONE"]:
            self.action(action)
        self.assertEqual(self.run_keyboard("aąb"), (0, "a1b"))
        self.library.probe_reset()
        self.library.accessibility_typing_begin()
        self.mode(2)
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_DONE")
        self.assertEqual(self.run_keyboard("ą", 3), (0, "ą"))

    def test_actual_keyboard_controls_delete_cancel_and_done(self):
        for column, result, final in [(10, 0, "abc"), (200, 0, "ab"), (400, -1, "abc")]:
            self.library.probe_reset()
            self.library.accessibility_typing_begin()
            self.touch("PRESS", column, 750, 0)
            self.touch("RELEASE", column, 750, 2)
            if column == 200:
                self.action("ACTION_KBD_DONE")
            self.assertEqual(self.run_keyboard("abc"), (result, final))
            self.assertEqual(self.library.probe_stat(4), 1)

    def test_actual_keyboard_arrows_reach_spoken_controls(self):
        self.mode(2)
        for _ in range(8):
            self.action("ACTION_KBD_DOWN")
        self.action("ACTION_KBD_RIGHT")
        self.action("ACTION_KBD_SELECT")
        self.action("ACTION_KBD_RIGHT")
        self.action("ACTION_KBD_SELECT")
        self.assertEqual(self.run_keyboard("abc"), (-1, "ab"))
        spoken = [self.library.probe_spoken(index) for index in range(self.library.probe_stat(9))]
        for name in ["LANG_KBD_OK", "LANG_KBD_DELETE", "LANG_KBD_CANCEL"]:
            self.assertIn(self.constant(name), spoken)

    def test_actual_keyboard_semantic_long_enter_done_leaves_no_insert(self):
        self.mode(2)
        self.action("ACTION_KBD_DONE")
        self.action("ACTION_KBD_SELECT")
        self.assertEqual(self.run_keyboard("original"), (0, "original"))
        self.assertEqual(self.library.probe_stat(8), 1)
        self.assertEqual(self.library.probe_stat(5), 1)

    def test_actual_keyboard_usb_aborts_and_clears_touch(self):
        self.touch("PRESS", 10, 60, 0)
        self.library.probe_action(0x40000001)
        self.touch("RELEASE", 10, 60, 20)
        self.assertEqual(self.run_keyboard("original"), (-1, "original"))
        self.assertEqual(self.library.probe_stat(8), 2)
        self.assertEqual(self.library.probe_take(), -1)

    def test_actual_keyboard_explicit_usb_and_non_usb_status(self):
        for mode in range(3):
            with self.subTest(mode=mode):
                self.library.probe_reset()
                self.mode(mode)
                self.library.probe_action(0x40000001)
                buffer = ctypes.create_string_buffer(b"original", 256)
                usb = ctypes.c_bool(False)
                self.assertEqual(self.library.probe_run_ex(buffer, 256, ctypes.byref(usb)), -1)
                self.assertTrue(usb.value)
                self.assertEqual(buffer.value, b"original")
                self.assertFalse(self.library.accessibility_typing_active())
                self.assertEqual(self.library.probe_take(), -1)
        self.library.probe_reset()
        self.library.probe_enabled(False)
        self.library.probe_action(0x40000001)
        buffer = ctypes.create_string_buffer(b"original", 256)
        usb = ctypes.c_bool(False)
        self.assertEqual(self.library.probe_run_ex(buffer, 256, ctypes.byref(usb)), -1)
        self.assertTrue(usb.value)
        self.assertFalse(self.library.accessibility_typing_active())
        for failure in ("Done", "Cancel", "viewport"):
            with self.subTest(non_usb=failure):
                self.library.probe_reset()
                if failure == "viewport":
                    self.library.probe_fail_viewport()
                else:
                    self.action("ACTION_KBD_DONE" if failure == "Done" else "ACTION_KBD_ABORT")
                buffer = ctypes.create_string_buffer(b"original", 256)
                usb = ctypes.c_bool(True)
                result = self.library.probe_run_ex(buffer, 256, ctypes.byref(usb))
                self.assertEqual(result, 0 if failure == "Done" else -1)
                self.assertFalse(usb.value)
                self.assertEqual(buffer.value, b"original")

    def test_actual_keyboard_viewport_failure_cancels_and_restores_theme(self):
        for was_active in [False, True]:
            self.library.probe_reset()
            if was_active:
                self.library.accessibility_typing_begin()
            self.library.probe_fail_viewport()
            buffer = ctypes.create_string_buffer("original ą".encode("utf-8"), 256)
            self.assertEqual(self.library.probe_run(buffer, 256), -1)
            self.assertEqual(buffer.value.decode("utf-8"), "original ą")
            self.assertFalse(self.library.accessibility_typing_active())
            self.assertEqual(self.library.probe_stat(8), 0)
            self.assertEqual(self.library.probe_stat(10), 1)
            self.assertEqual(self.library.probe_stat(11), 1)
            self.assertEqual(self.library.probe_stat(12), 1)
            self.assertEqual(self.library.probe_stat(3), self.constant("LANG_KBD_UNAVAILABLE"))
            self.assertEqual(self.library.probe_stat(9), 0)

    def test_geometry_rejects_short_row_padding_and_outside_screen(self):
        self.library.probe_short_row()
        self.assertEqual(self.library.probe_hit(100, 60), 2)
        for x, y in [(132, 60), (479, 60), (-1, 60), (480, 60), (10, -1), (10, 800), (10, 46)]:
            self.assertEqual(self.library.probe_hit(x, y), -1, (x, y))

    def test_disabled_capabilities_compile_and_remain_inert(self):
        header = (ROOT / "apps/accessibility_typing.h").read_text(encoding="utf-8")
        source = re.sub(r"^\s*#include[^\n]*", "",
                        (ROOT / "apps/accessibility_typing.c").read_text(encoding="utf-8"),
                        flags=re.MULTILINE)
        main = r'''
int main(void)
{
    accessibility_typing_begin();
    struct accessibility_typing_result result = accessibility_typing_process(
        ACCESSIBILITY_TYPING_PRESS, 2, 1, 1, 1);
    if (accessibility_typing_active() || accessibility_typing_set_mode(1) ||
        accessibility_typing_needs_poll() ||
        accessibility_typing_menu() || accessibility_typing_handle_touch(0, 0) ||
        accessibility_typing_take_touch(0) || result.commit != -1 || result.speak ||
        accessibility_typing_mode() != ACCESSIBILITY_TYPING_LIFT)
        return 1;
    accessibility_typing_cancel_touch();
    accessibility_typing_end();
    return 0;
}
'''
        for defines in [[], ["HAVE_TOUCHSCREEN"], ["HAVE_ESPEAK"]]:
            label = "guard-" + ("-".join(defines) or "neither")
            unit = self.workspace / (label + ".c")
            output = self.workspace / (label + (".exe" if os.name == "nt" else ".bin"))
            unit.write_text(header + "\n" + source + main, encoding="utf-8")
            command = self.compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
            command += ["-D" + define for define in defines] + [str(unit), "-o", str(output)]
            for phase, argv in [("compile", command), ("run", [str(output)])]:
                result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
                self.records.append({"argv": argv, "returncode": result.returncode})
                (self.workspace / (label + "-" + phase + ".log")).write_text(
                    result.stdout + result.stderr, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_lift_random_contacts_follow_fresh_press_and_valid_region_rule(self):
        import random

        generator = random.Random(20261015)
        time = 0
        for _ in range(1000):
            start = generator.randrange(10)
            self.process("PRESS", start, time=time)
            valid = True
            for offset in range(generator.randrange(5)):
                target = generator.choice([-1, 0, 1, 2, -2, -3, -4])
                self.expect_none(self.process("CONTACT", target, offset * 100, 20, time + offset + 1))
                valid = valid and target != -1
            target = generator.choice([-1, 0, 1, 2, -2, -3, -4])
            if generator.randrange(4) == 0:
                self.library.accessibility_typing_cancel_touch()
                valid = False
            result = self.process("RELEASE", target, 300, 20, time + 10)
            self.assertEqual(result.commit, target if valid and target != -1 else -1)
            self.expect_none(self.process("RELEASE", target, time=time + 11))
            time += 100

    def test_typing_catalogs_have_matching_sources_and_nonempty_speech(self):
        records = {}
        for language in ["english", "polski"]:
            records[language] = {}
            source = (ROOT / "apps/lang" / (language + ".lang")).read_text(encoding="utf-8")
            for phrase in re.findall(r"<phrase>.*?</phrase>", source, re.DOTALL):
                identifier = re.search(r"\bid: (LANG_ACCESSIBILITY_TYPING_[A-Z_]+|LANG_KBD_UNAVAILABLE)", phrase)
                if not identifier:
                    continue
                self.assertNotIn(identifier[1], records[language])
                sections = {}
                for section in ["source", "dest", "voice"]:
                    match = re.search(r"<" + section + r">\s*\*: \"([^\"\n]+)\"\s*</" + section + ">", phrase)
                    self.assertIsNotNone(match, (language, identifier[1], section))
                    sections[section] = match[1]
                self.assertEqual(sections["dest"], sections["voice"])
                records[language][identifier[1]] = sections
        self.assertEqual(len(records["english"]), 10)
        self.assertEqual(records["english"].keys(), records["polski"].keys())
        for identifier in records["english"]:
            self.assertEqual(records["english"][identifier]["source"], records["polski"][identifier]["source"])


from typing_echo_fixture import install
install(sys.modules[__name__])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if hasattr(AccessibilityTypingTests, "workspace"):
        (AccessibilityTypingTests.workspace / "result.json").write_text(json.dumps({
            "tests_run": result.testsRun, "passed": result.wasSuccessful(),
            "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors],
            "skipped": [reason for _, reason in result.skipped],
        }, indent=2) + "\n", encoding="utf-8")
    sys.exit(not result.wasSuccessful())
