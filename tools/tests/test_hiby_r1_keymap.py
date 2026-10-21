"""Execute R1 physical mappings with Rockbox's shared action lookup on a host."""

import ctypes
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]

CALLERS = (
    ("apps/recorder/keyboard.c", "CONTEXT_KEYBOARD", 50),
    ("apps/gui/quickscreen.c", "CONTEXT_QUICKSCREEN", 20),
    ("apps/gui/color_picker.c", "CONTEXT_SETTINGS_COLOURCHOOSER", -1),
    ("apps/menus/eq_menu.c", "CONTEXT_SETTINGS_EQ", -1),
    ("apps/screens.c", "CONTEXT_SETTINGS_TIME", -1),
    ("apps/gui/yesno.c", "CONTEXT_YESNOSCREEN", 50),
    ("apps/plugins/pitch_screen.c", "CONTEXT_PITCHSCREEN", 100),
)


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def without_includes(text):
    return re.sub(r'^\s*#include[^\n]*', '', text, flags=re.MULTILINE)


def function(text, name):
    pattern = (r'^(?:static\s+)?(?:inline\s+)?(?:const\s+struct\s+button_mapping\s*\*|bool\s+|(?:unsigned\s+)?int\s+|void\s+)'
               + re.escape(name)
               + r'\s*\([^;{}]*\)\s*\{')
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"Expected one definition of {name}, got {len(matches)}")
    match = matches[0]
    depth = 1
    cursor = match.end()
    while depth:
        depth += (text[cursor] == '{') - (text[cursor] == '}')
        cursor += 1
    return text[match.start():cursor] + "\n"


def espeak_projection(text):
    """Select real speech-dependent lookup helpers without input interception."""
    return "#define HAVE_ESPEAK\n" + text + "#undef HAVE_ESPEAK\n"


def action_call(text, context):
    calls = []
    for match in re.finditer(r'\b(?:rb->)?get_action\s*\(', text):
        depth = 1
        cursor = match.end()
        while depth:
            depth += (text[cursor] == '(') - (text[cursor] == ')')
            cursor += 1
        call = text[match.start():cursor]
        if re.search(r'\b' + re.escape(context) + r'\b', call):
            calls.append(call)
    if len(calls) != 1:
        raise AssertionError(f"Expected one caller for {context}, got {len(calls)}")
    return calls[0]


def caller_wrappers():
    wrappers = []
    for index, (path, context, _) in enumerate(CALLERS):
        call = action_call(source(path), context)
        local_setup = ""
        if context == "CONTEXT_KEYBOARD":
            keyboard = source(path)
            start = keyboard.index("        int timeout = HZ/2;")
            local_setup = keyboard[start:keyboard.index("        button = get_action(", start)]
        definition = (
            f"int test_caller_{index}(bool morse)\n{{\n"
            "    struct { bool morse_mode; } state = { morse };\n"
            "    (void)state;\n"
            + local_setup +
            f"    return {call};\n}}\n"
        )
        wrappers.append(definition)
        if context == "CONTEXT_KEYBOARD":
            wrappers.append("#define HAVE_MORSE_INPUT\n" + definition.replace(
                f"test_caller_{index}(", f"test_caller_{index}_morse(")
                + "#undef HAVE_MORSE_INPUT\n")
    return "\n".join(wrappers)


PREAMBLE = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define HIBY_R1
#define CONFIG_KEYPAD 79
#define SANSA_CLIP_PAD 42
#define HAVE_TOUCHSCREEN
#define HAVE_BACKLIGHT
#define NO_BUTTON_LR
#define HAVE_VOLUME_IN_LIST
#define HAVE_HOTKEY
#define HAVE_KBD_POINT_MODE
#define INIT_ATTR
#define HZ 100
#define SYS_EVENT 0x40000000
#define SYS_BATTERY_UPDATE (SYS_EVENT | 3)
#define IS_SYSEVENT(event) ((event) & SYS_EVENT)
#define REPEAT_WINDOW_TICKS (HZ / 4)
#define ACTION_FILTER_TICKS (HZ / 2)
#define LANG_KEYLOCK_ON 1
#define LANG_KEYLOCK_OFF 2
#define LANG_ACTION_AUTOLOCK_ON 3
#define LANG_ACTION_AUTOLOCK_OFF 4
#define GUI_EVENT_ACTIONUPDATE 1
#define ID2P(value) (value)
#define logf(...) ((void)0)
struct viewport;
struct gesture_event;
struct touchevent { int unused; };
struct gesture { int unused; };
static long current_tick;
"""


MOCKS = r"""
static action_last_t action_last;
static int queued_button;
static bool touch_enabled;
static bool backlight_enabled;
static int volume_steps;
static int volume_calls;
static struct button_mapping *remapped_items;
static struct { bool hold_lr_for_scroll_in_list; bool list_wraparound;
                int keyclick; bool keyclick_repeats; } global_settings;
typedef bool (*keyclick_callback)(int action, void *data);
#define KEYCLICK_SOURCE_PHYSICAL 1
#define KEYCLICK_SOURCE_GESTURE 2
#define SOUND_KEYCLICK 1
static int feedback_sounds;
static void system_sound_play(int sound) { if (sound == SOUND_KEYCLICK) ++feedback_sounds; }
static void beep_play(unsigned int frequency, unsigned int duration, unsigned int amplitude)
{
    (void)frequency; (void)duration; (void)amplitude;
    ++feedback_sounds;
}
static bool accessibility_screen_locked_buttons(void) { return false; }
int get_action_statuscode(int *button);
long button_get_w_tmo(int timeout) { (void)timeout; ++current_tick; return queued_button; }
intptr_t button_get_data(void) { return 0; }
void button_clear_queue(void) {}
void button_enable_touch(bool enabled) { touch_enabled = enabled; }
bool is_keys_locked(void) { return action_last.keys_locked; }
static void *core_get_data(int handle) { (void)handle; return remapped_items; }
static void skin_request_update_locked(bool locked) { (void)locked; }
static void splash(int ticks, int message) { (void)ticks; (void)message; }
void adjust_volume(int steps) { volume_steps += steps; ++volume_calls; }
bool is_backlight_on(bool remote) { (void)remote; return backlight_enabled; }
void backlight_on_ignore(bool ignore, int timeout) { (void)ignore; (void)timeout; }
void backlight_on(void) { backlight_enabled = true; }
int backlight_get_current_timeout(void) { return 1000; }
void sleep(int ticks) { current_tick += ticks; }
void send_event(int event, void *data) { (void)event; (void)data; }
bool lang_is_rtl(void) { return false; }
int sb_touch_to_button(int context) { (void)context; return ACTION_NONE; }
static bool get_action_touchscreen(action_last_t *last, action_cur_t *cur)
{
    (void)last;
    (void)cur;
    return false;
}
"""


WRAPPERS = r"""
void test_reset(bool scroll)
{
    memset(&action_last, 0, sizeof(action_last));
    action_last.button = BUTTON_REL;
    global_settings.hold_lr_for_scroll_in_list = scroll;
    global_settings.keyclick = 0;
    current_tick = 0;
    touch_enabled = true;
    backlight_enabled = true;
    volume_steps = 0;
    volume_calls = 0;
}
int test_event(int context, int button, bool reader, bool allow_lock)
{
    queued_button = button;
    if (reader)
        return reader_action(0);
    return get_action(context | (allow_lock ? ALLOW_SOFTLOCK : 0), 0);
}
int test_custom_event(int context, int button)
{
    queued_button = button;
    return get_custom_action(context | ALLOW_SOFTLOCK, 0, NULL);
}
int test_mapping_event(int context, int button)
{
    queued_button = button;
    action_cur_t current;
    init_act_cur(&current, context | ALLOW_SOFTLOCK, 0, NULL);
    return get_action_worker(&action_last, &current);
}
int test_default_event(int context, int button, bool held)
{ return accessibility_default_button_action(button, context, held); }
int test_volume_steps(void) { return volume_steps; }
int test_volume_calls(void) { return volume_calls; }
struct gui_synclist { int selected_item, nb_items, selected_size; bool wraparound; };
bool gui_synclist_keyclick_callback(int action, void *data);
static struct gui_synclist feedback_list;
void test_feedback_reset(bool repeats, bool edge)
{
    test_reset(false);
    global_settings.keyclick = 1;
    global_settings.keyclick_repeats = repeats;
    feedback_sounds = 0;
    feedback_list = (struct gui_synclist){ edge ? 0 : 1, 8, 1, false };
}
int test_feedback_event(int context, int button)
{
    keyclick_set_callback(gui_synclist_keyclick_callback, &feedback_list);
    return test_mapping_event(context, button);
}
int test_feedback_sounds(void) { return feedback_sounds; }
void test_feedback_consumed_action(void)
{
    keyclick_set_callback(gui_synclist_keyclick_callback, &feedback_list);
    keyclick_click_physical(ACTION_NONE, false);
}
void test_backlight(bool enabled, bool first_key_only)
{
    backlight_enabled = enabled;
    action_last.backlight_mask = SEL_ACTION_ENABLED |
        (first_key_only ? SEL_ACTION_FFKEYPRESS : 0);
}
void test_lock_mask(int mask) { action_last.softlock_mask = mask; }
int test_touch_enabled(void) { return touch_enabled; }
int test_locked(void) { return action_last.keys_locked; }
void test_wait_for_release(void) { action_last.wait_for_release = true; }
void test_remap_event(int context, int action, int button, int prerequisite)
{
    static struct button_mapping mapping[4];
    mapping[0] = (struct button_mapping){CORE_CONTEXT_REMAP(context), 2, 0};
    mapping[1] = (struct button_mapping)LAST_ITEM_IN_LIST;
    mapping[2] = (struct button_mapping){action, button, prerequisite};
    mapping[3] = (struct button_mapping)LAST_ITEM_IN_LIST;
    remapped_items = mapping;
    action_last.key_remap = 1;
}
void test_remap(int context, int action)
{
    test_remap_event(context, action, BUTTON_VOL_UP | BUTTON_REL, BUTTON_VOL_UP);
}
int test_physical_table_buttons(void)
{
    const int contexts[] = {
        CONTEXT_STD, CONTEXT_LIST, CONTEXT_TREE, CONTEXT_MAINMENU, CONTEXT_WPS,
        CONTEXT_SETTINGS, CONTEXT_SETTINGS_EQ, CONTEXT_SETTINGS_COLOURCHOOSER,
        CONTEXT_SETTINGS_TIME, CONTEXT_SETTINGS_RECTRIGGER,
        CONTEXT_CUSTOM | CONTEXT_SETTINGS, CONTEXT_CUSTOM | CONTEXT_TREE,
        CONTEXT_BOOKMARKSCREEN, CONTEXT_YESNOSCREEN, CONTEXT_QUICKSCREEN,
        CONTEXT_PITCHSCREEN, CONTEXT_KEYBOARD, CONTEXT_MORSE_INPUT
    };
    int buttons = 0;
    for (size_t index = 0; index < sizeof(contexts) / sizeof(contexts[0]); ++index)
    {
        const struct button_mapping *mapping = target_get_context_mapping(contexts[index]);
        for (; mapping->button_code != BUTTON_NONE; ++mapping)
            buttons |= mapping->button_code | mapping->pre_button_code;
    }
    const struct button_mapping *mapping = target_get_context_mapping(CONTEXT_CUSTOM | CONTEXT_STD);
    for (; mapping->button_code != BUTTON_NONE; ++mapping)
        buttons |= mapping->button_code | mapping->pre_button_code;
    return buttons & ~(BUTTON_REL | BUTTON_REPEAT);
}
"""

KEYBOARD_MOCKS = r"""
#define CHANGED_PICKER 1
#define KBD_SPACE 0x2423
struct keyboard_parameters {
    int x, y, max_chars, page, pages, lines;
    bool line_edit;
};
struct edit_state { int changed; };
static struct keyboard_parameters keyboard;
static struct edit_state keyboard_state;
static int get_kbd_ch(struct keyboard_parameters *parameter, int column, int row)
{
    (void)parameter;
    return row == 0 && (column == 2 || column == 3) ? KBD_SPACE : 'a';
}
"""

KEYBOARD_WRAPPERS = r"""
void test_keyboard_reset(bool space_row)
{
    keyboard = (struct keyboard_parameters){
        .x = 1, .y = space_row ? 0 : 1, .max_chars = 6, .pages = 2, .lines = 3
    };
    keyboard_state.changed = 0;
}
int test_keyboard_coordinate(bool vertical) { return vertical ? keyboard.y : keyboard.x; }
void test_keyboard_action(int action)
{
    struct keyboard_parameters *pm = &keyboard;
    struct edit_state state = keyboard_state;
    switch (action)
    {
KEYBOARD_CASES
    }
    keyboard_state = state;
}
"""

CALLER_PROBE = r"""
static int caller_timeout;
int get_action(int context, int timeout)
{
    caller_timeout = timeout;
    return context;
}
struct caller_api { int (*get_action)(int, int); };
static const struct caller_api caller_api = { get_action };
static const struct caller_api *rb = &caller_api;
int test_caller_timeout(void) { return caller_timeout; }
"""

ENTRY_PROBE = r"""
static action_last_t action_last;
static int probe_action;
static int probe_volume;
void adjust_volume(int steps) { probe_volume += steps; }
static void init_act_cur(action_cur_t *cur, int context, int timeout,
                        const struct button_mapping *(*mapping)(int))
{
    (void)cur;
    (void)context;
    (void)timeout;
    (void)mapping;
}
static int get_action_worker(action_last_t *last, action_cur_t *cur)
{
    (void)last;
    (void)cur;
    return probe_action;
}
static int do_backlight(action_last_t *last, action_cur_t *cur, int action)
{
    (void)last;
    (void)cur;
    return action;
}
int sb_touch_to_button(int context) { (void)context; return ACTION_NONE; }
int test_entry(int action, bool custom)
{
    probe_action = action;
    probe_volume = 0;
    return custom ? get_custom_action(CONTEXT_LIST, 0, NULL) : get_action(CONTEXT_LIST, 0);
}
int test_entry_volume(void) { return probe_volume; }
"""

TIME_WRAPPERS = r"""
static int time_cursor;
static int time_value;
static void say_time(int cursor, void *time) { (void)cursor; (void)time; }
void test_time_reset(void) { time_cursor = 2; time_value = 30; }
int test_time_value(bool cursor) { return cursor ? time_cursor : time_value; }
void test_time_action(int button)
{
    int cursorpos = time_cursor;
    int *valptr = &time_value;
    int last_item = 5;
    int max = 59;
    int min = 0;
    void *tm = NULL;
    switch (button)
    {
TIME_CASES
        default: break;
    }
    time_cursor = cursorpos;
}
"""

READER_WRAPPERS = r"""
struct reader_probe { int position, unit, toggles; };
static struct reader_probe reader_probe;
static void reader_toggle(struct reader_probe *reader) { ++reader->toggles; }
static void reader_change_unit(struct reader_probe *reader, bool forward)
{
    reader->unit += forward ? 1 : -1;
}
static void reader_navigate(struct reader_probe *reader, bool forward)
{
    reader->position += forward ? 1 : -1;
}
void test_reader_reset(void) { memset(&reader_probe, 0, sizeof(reader_probe)); }
int test_reader_value(int field)
{
    return field == 0 ? reader_probe.position : field == 1 ? reader_probe.unit : reader_probe.toggles;
}
void test_reader_action(int action)
{
    struct reader_probe reader = reader_probe;
    switch (action)
    {
READER_CASES
        default: break;
    }
    reader_probe = reader;
}
"""


class HibyR1KeymapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        materials = project_materials_root(ROOT)
        ensure_ignored_directories(materials.parent, [materials.name])
        cls.workspace = materials / "hiby-r1-keymap-tests" / datetime.now(
            timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace.mkdir(parents=True, exist_ok=False)
        action = source("apps/action.c")
        types_start = action.index("typedef struct")
        types_end = action.index("/* holds the action state", types_start)
        lookup_functions = [
            "has_flag", "action_poll_button", "update_screen_has_lock",
            "action_code_worker", "get_next_context", "action_code_lookup",
            "is_action_filtered", "is_action_discarded", "action_handle_backlight",
            "action_update_touch_lock", "do_key_lock", "autosoftlock_timeout", "do_auto_softlock", "do_softlock", "update_action_last",
            "init_act_cur", "accessibility_physical_button", "accessibility_default_button_action",
            "do_backlight", "button_flip_horizontally", "get_action_worker",
            "do_global_volume", "get_action", "get_custom_action",
            "get_action_statuscode",
        ]
        reader = source("apps/tts_reader.c")
        headers = "\n".join(without_includes(source(path)) for path in [
            "firmware/target/hosted/hiby/r1/button-target.h",
            "firmware/export/button.h", "apps/action.h",
        ])
        touchscreen = without_includes(source("apps/keymaps/keymap-touchscreen.c"))
        touchscreen = touchscreen.replace("button_context_", "touch_button_context_")
        harness = PREAMBLE + headers + espeak_projection(action[types_start:types_end]) + MOCKS
        harness += re.search(r"^#define KEYCLICK_DURATION [^\n]+",
                             source("apps/settings.h"), re.MULTILINE)[0] + "\n"
        misc = source("apps/misc.c")
        harness += misc[misc.index("static keyclick_callback keyclick_current_callback"):
                        misc.index("/* Return the ReplayGain mode")]
        harness += without_includes(source("apps/keymaps/keymap-hibyr1.c"))
        harness += touchscreen
        harness += function(reader, "reader_action")
        espeak_functions = {"action_code_lookup", "init_act_cur",
                            "accessibility_physical_button", "accessibility_default_button_action"}
        harness += "\n".join(espeak_projection(function(action, name)) if name in espeak_functions
                             else function(action, name) for name in lookup_functions)
        control_labels = function(source("apps/accessibility.c"), "button_default_label")
        language_labels = sorted(set(re.findall(r'\bLANG_[A-Z0-9_]+', control_labels)))
        harness += "\nenum {" + ",".join(f"{name}={10000 + index}" for index, name in
                                         enumerate(language_labels)) + "};\n"
        harness += without_includes(source("apps/accessibility_buttons.h"))
        harness += control_labels
        harness += ("int test_control_label(int button, int slot, int context, bool unassigned)"
                    " { return button_default_label(button, slot, context, unassigned); }\n")
        harness += WRAPPERS
        list_source = source("apps/gui/list.c")
        harness += function(list_source, "gui_synclist_keyclick_callback")
        volume_start = list_source.index("        case ACTION_LIST_VOLUP:")
        volume_end = list_source.index("#endif", volume_start)
        harness += ("bool test_list_action(int action)\n{\n    switch (action)\n    {\n"
                    + list_source[volume_start:volume_end]
                    + "        default: return false;\n    }\n}\n")
        keyboard = source("apps/recorder/keyboard.c")
        harness += KEYBOARD_MOCKS
        harness += function(keyboard, "kbd_move_picker_horizontal")
        harness += function(keyboard, "kbd_move_picker_vertical")
        cases_start = keyboard.index("            case ACTION_KBD_RIGHT:")
        cases_end = keyboard.index("#ifdef HAVE_MORSE_INPUT", cases_start)
        harness += KEYBOARD_WRAPPERS.replace("KEYBOARD_CASES", keyboard[cases_start:cases_end])
        time_source = source("apps/screens.c")
        time_start = time_source.index("            case ACTION_STD_PREV:")
        time_end = time_source.index("            case ACTION_STD_OK:", time_start)
        harness += function(source("apps/misc.c"), "clamp_value_wrap")
        harness += TIME_WRAPPERS.replace("TIME_CASES", time_source[time_start:time_end])
        reader_start = reader.index("            case ACTION_STD_OK:")
        reader_end = reader.index("            case ACTION_REDRAW:", reader_start)
        harness += READER_WRAPPERS.replace("READER_CASES", reader[reader_start:reader_end])
        names = sorted(set(re.findall(
            r'\b(?:ACTION_[A-Z0-9_]+|CONTEXT_[A-Z0-9_]+|BUTTON_[A-Z0-9_]+|POWEROFF_COUNT|POWEROFF_BUTTON)\b',
            source("apps/keymaps/keymap-hibyr1.c")
        )) | {"ACTION_UNKNOWN", "ACTION_REDRAW", "CONTEXT_LOCKED", "CONTEXT_CUSTOM",
              "BUTTON_PREV", "BUTTON_MAIN", "POWEROFF_COUNT", "POWEROFF_BUTTON",
              "ALLOW_SOFTLOCK", "SEL_ACTION_ENABLED", "SEL_ACTION_VOL", "SYS_EVENT"})
        names = sorted(set(names) | set(language_labels) | {"CONTEXT_CUSTOM2"})
        harness += "\n".join(f"int constant_{name}(void) {{ return {name}; }}" for name in names)
        harness_path = cls.workspace / "keymap.c"
        harness_path.write_text(harness, encoding="utf-8")
        library_path = cls.workspace / "keymap.so"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
            str(harness_path), "-o", str(library_path),
        ]
        if os.environ.get("HIBY_R1_KEYMAP_SANITIZE"):
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        result = subprocess.run(command, capture_output=True, text=True)
        (cls.workspace / "compile.log").write_text(
            shlex.join(command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.library = ctypes.CDLL(str(library_path))
        cls.constants = {name: getattr(cls.library, f"constant_{name}")() for name in names}
        cls.library.test_reset.argtypes = [ctypes.c_bool]
        cls.library.test_event.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool]
        cls.library.test_remap.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.library.test_remap_event.argtypes = [ctypes.c_int] * 4
        cls.library.test_custom_event.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.library.test_mapping_event.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.library.test_feedback_reset.argtypes = [ctypes.c_bool, ctypes.c_bool]
        cls.library.test_feedback_event.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.library.test_list_action.argtypes = [ctypes.c_int]
        cls.library.test_backlight.argtypes = [ctypes.c_bool, ctypes.c_bool]
        cls.library.test_lock_mask.argtypes = [ctypes.c_int]
        cls.library.test_keyboard_reset.argtypes = [ctypes.c_bool]
        cls.library.test_keyboard_coordinate.argtypes = [ctypes.c_bool]
        cls.library.test_keyboard_action.argtypes = [ctypes.c_int]
        cls.library.test_time_value.argtypes = [ctypes.c_bool]
        cls.library.test_time_action.argtypes = [ctypes.c_int]
        cls.library.test_reader_value.argtypes = [ctypes.c_int]
        cls.library.test_reader_action.argtypes = [ctypes.c_int]
        cls.caller_libraries = {}
        cls.entry_libraries = {}
        probe_preamble = PREAMBLE.replace("#define HIBY_R1\n", "").replace(
            "static long current_tick;\n", "")
        wrappers = caller_wrappers()
        for target, defines in (("r1", "#define HIBY_R1\n"),
                                ("clip", "#define SANSA_CLIPPLUS\n"),
                                ("r3", "#define HIBY_R3PROII\n")):
            preamble = probe_preamble
            if target == "clip":
                preamble = preamble.replace("#define CONFIG_KEYPAD 79", "#define CONFIG_KEYPAD 42")
            probe_path = cls.workspace / f"{target}-callers.c"
            probe_path.write_text(preamble + defines + headers + CALLER_PROBE + wrappers,
                                  encoding="utf-8")
            probe_library = cls.workspace / f"{target}-callers.so"
            probe_command = [str(probe_path) if item == str(harness_path) else
                             str(probe_library) if item == str(library_path) else item
                             for item in command]
            result = subprocess.run(probe_command, capture_output=True, text=True)
            (cls.workspace / f"compile-{target}-callers.log").write_text(
                shlex.join(probe_command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                raise RuntimeError(result.stderr)
            probe = ctypes.CDLL(str(probe_library))
            for index in range(len(CALLERS)):
                getattr(probe, f"test_caller_{index}").argtypes = [ctypes.c_bool]
            probe.test_caller_0_morse.argtypes = [ctypes.c_bool]
            cls.caller_libraries[target] = probe
            if target != "r1":
                entry_path = cls.workspace / f"{target}-entries.c"
                entry_prefix, entry_wrappers = ENTRY_PROBE.split("int test_entry(", 1)
                entry_path.write_text(
                    preamble + defines + headers + action[types_start:types_end] + entry_prefix
                    + function(action, "get_action") + function(action, "get_custom_action")
                    + "int test_entry(" + entry_wrappers, encoding="utf-8")
                entry_library = cls.workspace / f"{target}-entries.so"
                entry_command = [str(entry_path) if item == str(harness_path) else
                                 str(entry_library) if item == str(library_path) else item
                                 for item in command]
                result = subprocess.run(entry_command, capture_output=True, text=True)
                (cls.workspace / f"compile-{target}-entries.log").write_text(
                    shlex.join(entry_command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
                if result.returncode:
                    raise RuntimeError(result.stderr)
                entry_probe = ctypes.CDLL(str(entry_library))
                entry_probe.test_entry.argtypes = [ctypes.c_int, ctypes.c_bool]
                cls.entry_libraries[target] = entry_probe

    def setUp(self):
        self.library.test_reset(False)

    def value(self, name):
        return self.constants[name]

    def check_control_labels(self, context, keys, labels, slot=0, unassigned=False):
        for key, label in zip(keys, labels):
            with self.subTest(context=context, key=key, slot=slot):
                self.assertEqual(self.library.test_control_label(self.value(key), slot, context, unassigned),
                                 self.value(label))

    def test_default_menu_descriptions_follow_real_target_mapping(self):
        keys = ("BUTTON_POWER", "BUTTON_PLAY", "BUTTON_NEXT", "BUTTON_VOL_UP", "BUTTON_VOL_DOWN")
        self.check_control_labels(self.value("CONTEXT_STD"), keys,
            ("LANG_ACCESSIBILITY_ACTIVATE", "LANG_BACK", "LANG_ACCESSIBILITY_ACTIVATE",
             "LANG_ACCESSIBILITY_UP", "LANG_ACCESSIBILITY_DOWN"))
        self.check_control_labels(self.value("CONTEXT_STD"), keys,
            ("LANG_ACCESSIBILITY_DEFAULT_POWER_HOLD", "LANG_MAIN_MENU", "LANG_ACCESSIBILITY_CONTEXT",
             "LANG_ACCESSIBILITY_VOLUME_UP", "LANG_ACCESSIBILITY_VOLUME_DOWN"), slot=3)

    def test_default_music_descriptions_are_not_menu_arrows(self):
        keys = ("BUTTON_POWER", "BUTTON_PLAY", "BUTTON_NEXT", "BUTTON_VOL_UP", "BUTTON_VOL_DOWN")
        self.check_control_labels(self.value("CONTEXT_WPS"), keys,
            ("LANG_ACCESSIBILITY_DEFAULT_MUSIC_PAUSE", "LANG_ACCESSIBILITY_DEFAULT_TRACK_PREVIOUS",
             "LANG_ACCESSIBILITY_DEFAULT_TRACK_NEXT", "LANG_ACCESSIBILITY_VOLUME_UP",
             "LANG_ACCESSIBILITY_VOLUME_DOWN"))
        self.check_control_labels(self.value("CONTEXT_WPS"), keys,
            ("LANG_ACCESSIBILITY_DEFAULT_POWER_HOLD", "LANG_ACCESSIBILITY_DEFAULT_SEEK_BACK",
             "LANG_ACCESSIBILITY_DEFAULT_SEEK_FORWARD", "LANG_ACCESSIBILITY_VOLUME_UP",
             "LANG_ACCESSIBILITY_VOLUME_DOWN"), slot=3)

    def test_default_reader_descriptions_distinguish_range_and_text(self):
        context = self.value("CONTEXT_CUSTOM") | self.value("CONTEXT_CUSTOM2") | self.value("CONTEXT_STD")
        self.check_control_labels(context,
            ("BUTTON_POWER", "BUTTON_PLAY", "BUTTON_NEXT", "BUTTON_VOL_UP", "BUTTON_VOL_DOWN"),
            ("LANG_ACCESSIBILITY_DEFAULT_TEXT_PAUSE", "LANG_ACCESSIBILITY_DEFAULT_TEXT_PREVIOUS",
             "LANG_ACCESSIBILITY_DEFAULT_TEXT_NEXT", "LANG_ACCESSIBILITY_DEFAULT_RANGE_PREVIOUS",
             "LANG_ACCESSIBILITY_DEFAULT_RANGE_NEXT"))

    def test_default_keyboard_descriptions_keep_hold_to_finish(self):
        keys = ("BUTTON_POWER", "BUTTON_PLAY", "BUTTON_NEXT", "BUTTON_VOL_UP", "BUTTON_VOL_DOWN")
        self.check_control_labels(self.value("CONTEXT_KEYBOARD"), keys,
            ("LANG_ACCESSIBILITY_DEFAULT_INSERT", "LANG_ACCESSIBILITY_LEFT", "LANG_ACCESSIBILITY_RIGHT",
             "LANG_ACCESSIBILITY_UP", "LANG_ACCESSIBILITY_DOWN"))
        self.check_control_labels(self.value("CONTEXT_KEYBOARD"), keys,
            ("LANG_ACCESSIBILITY_DEFAULT_FINISH", "LANG_ACCESSIBILITY_DEFAULT_CARET_LEFT",
             "LANG_ACCESSIBILITY_DEFAULT_CARET_RIGHT", "LANG_ACCESSIBILITY_VOLUME_UP",
             "LANG_ACCESSIBILITY_VOLUME_DOWN"), slot=3)

    def test_unassigned_volume_and_default_multi_press_descriptions(self):
        for context in (self.value("CONTEXT_STD"), self.value("CONTEXT_WPS"), self.value("CONTEXT_KEYBOARD")):
            for slot in range(4):
                self.check_control_labels(context, ("BUTTON_VOL_UP", "BUTTON_VOL_DOWN"),
                    ("LANG_ACCESSIBILITY_VOLUME_UP", "LANG_ACCESSIBILITY_VOLUME_DOWN"), slot, True)
            for button in ("BUTTON_POWER", "BUTTON_PLAY", "BUTTON_NEXT"):
                expected = self.library.test_control_label(self.value(button), 0, context, False)
                for slot in (1, 2):
                    self.assertEqual(self.library.test_control_label(self.value(button), slot, context, False), expected)

    def test_control_guide_lookup_does_not_change_live_key_prerequisites(self):
        button = self.value("BUTTON_POWER")
        self.library.test_event(self.value("CONTEXT_STD"), button, False, False)
        self.library.test_control_label(self.value("BUTTON_NEXT"), 3, self.value("CONTEXT_WPS"), False)
        self.assertEqual(self.library.test_event(self.value("CONTEXT_STD"),
            button | self.value("BUTTON_REL"), False, False), self.value("ACTION_STD_OK"))

    def feedback(self, context, button):
        return self.library.test_feedback_event(self.value(context), button)

    def test_actual_release_keymap_clicks_once_at_recognized_action(self):
        self.library.test_feedback_reset(False, False)
        for key in ("BUTTON_VOL_DOWN", "BUTTON_VOL_UP", "BUTTON_NEXT", "BUTTON_PLAY", "BUTTON_POWER"):
            before = self.library.test_feedback_sounds()
            button = self.value(key)
            self.assertEqual(self.feedback("CONTEXT_LIST", button), self.value("ACTION_NONE"))
            self.assertEqual(self.library.test_feedback_sounds(), before)
            self.feedback("CONTEXT_LIST", button | self.value("BUTTON_REL"))
            self.assertEqual(self.library.test_feedback_sounds(), before + 1)

    def test_actual_hold_repeat_feedback_respects_repeat_setting(self):
        for enabled in (False, True):
            self.library.test_feedback_reset(enabled, False)
            button = self.value("BUTTON_VOL_DOWN")
            for event in (button, button | self.value("BUTTON_REPEAT"),
                          button | self.value("BUTTON_REPEAT"), button | self.value("BUTTON_REL")):
                self.feedback("CONTEXT_LIST", event)
            self.assertEqual(self.library.test_feedback_sounds(), 2 if enabled else 1)

    def test_actual_first_hold_action_clicks_with_repeats_disabled(self):
        self.library.test_feedback_reset(False, False)
        button = self.value("BUTTON_NEXT")
        self.feedback("CONTEXT_LIST", button)
        self.assertEqual(self.library.test_feedback_sounds(), 0)
        self.assertEqual(self.feedback("CONTEXT_LIST", button | self.value("BUTTON_REPEAT")),
                         self.value("ACTION_STD_CONTEXT"))
        self.assertEqual(self.library.test_feedback_sounds(), 1)
        self.feedback("CONTEXT_LIST", button | self.value("BUTTON_REPEAT"))
        self.feedback("CONTEXT_LIST", button | self.value("BUTTON_REL"))
        self.assertEqual(self.library.test_feedback_sounds(), 1)

    def test_actual_list_callback_allows_recognized_consumed_action(self):
        self.library.test_feedback_reset(False, False)
        self.library.test_feedback_consumed_action()
        self.assertEqual(self.library.test_feedback_sounds(), 1)

    def test_actual_wps_volume_press_has_no_duplicate_release_click(self):
        self.library.test_feedback_reset(False, False)
        button = self.value("BUTTON_VOL_DOWN")
        self.feedback("CONTEXT_WPS", button)
        self.assertEqual(self.library.test_feedback_sounds(), 1)
        self.feedback("CONTEXT_WPS", button | self.value("BUTTON_REL"))
        self.assertEqual(self.library.test_feedback_sounds(), 1)

    def test_actual_list_edge_callback_still_vetoes_release_click(self):
        self.library.test_feedback_reset(False, True)
        button = self.value("BUTTON_VOL_UP")
        self.feedback("CONTEXT_LIST", button)
        self.feedback("CONTEXT_LIST", button | self.value("BUTTON_REL"))
        self.assertEqual(self.library.test_feedback_sounds(), 0)

    def event(self, context, button, reader=False):
        return self.library.test_event(self.value(context), button, reader, True)

    def sequence(self, context, buttons, reader=False):
        actions = [self.event(context, button, reader) for button in buttons]
        return [action for action in actions if action not in (
            self.value("ACTION_NONE"), self.value("ACTION_UNKNOWN"))]

    def tap(self, context, key, reader=False):
        button = self.value(key)
        return self.sequence(context, [button, button | self.value("BUTTON_REL")], reader)

    def hold(self, context, key, reader=False):
        button = self.value(key)
        repeat = button | self.value("BUTTON_REPEAT")
        return self.sequence(context, [button, repeat, repeat,
                                      button | self.value("BUTTON_REL")], reader)

    def chord(self, context, modifier, key, reader=False, reverse_release=False,
              repeat=False):
        modifier = self.value(modifier)
        button = self.value(key)
        events = [modifier, modifier | button]
        if repeat:
            events += [modifier | button | self.value("BUTTON_REPEAT")] * 2
        releases = [button, modifier] if not reverse_release else [modifier, button]
        events += [released | self.value("BUTTON_REL") for released in releases]
        return self.sequence(context, events, reader)

    def assert_actions(self, actual, *expected):
        self.assertEqual(actual, [self.value(name) for name in expected])

    def test_every_list_context_uses_five_physical_keys(self):
        for scroll in (False, True):
            for context in ("CONTEXT_STD", "CONTEXT_LIST", "CONTEXT_TREE",
                            "CONTEXT_MAINMENU", "CONTEXT_BOOKMARKSCREEN"):
                with self.subTest(context=context, scroll=scroll):
                    self.library.test_reset(scroll)
                    self.assert_actions(self.tap(context, "BUTTON_VOL_UP"), "ACTION_STD_PREV")
                    self.assert_actions(self.tap(context, "BUTTON_VOL_DOWN"), "ACTION_STD_NEXT")
                    self.assert_actions(self.tap(context, "BUTTON_NEXT"), "ACTION_STD_OK")
                    self.assert_actions(self.tap(context, "BUTTON_PLAY"), "ACTION_STD_CANCEL")
                    self.assert_actions(self.tap(context, "BUTTON_POWER"), "ACTION_STD_OK")
                    self.assert_actions(self.chord(context, "BUTTON_POWER", "BUTTON_PLAY"),
                                        "ACTION_STD_MENU")
                    self.assert_actions(self.hold(context, "BUTTON_NEXT"), "ACTION_STD_CONTEXT")
                    self.assert_actions(self.hold(context, "BUTTON_PLAY"), "ACTION_STD_MENU")
                    self.assert_actions(self.hold(context, "BUTTON_VOL_UP"))
                    self.assert_actions(self.hold(context, "BUTTON_VOL_DOWN"))
                    self.assertEqual(self.library.test_volume_calls(), 4)
                    self.assertEqual(self.library.test_volume_steps(), 0)

    def test_wps_transport_seek_and_volume(self):
        context = "CONTEXT_WPS"
        for key, action in (("BUTTON_PLAY", "ACTION_WPS_SKIPPREV"),
                            ("BUTTON_NEXT", "ACTION_WPS_SKIPNEXT"),
                            ("BUTTON_POWER", "ACTION_WPS_PLAY"),
                            ("BUTTON_VOL_UP", "ACTION_WPS_VOLUP"),
                            ("BUTTON_VOL_DOWN", "ACTION_WPS_VOLDOWN")):
            self.assert_actions(self.tap(context, key), action)
        for key, action in (("BUTTON_PLAY", "ACTION_WPS_SEEKBACK"),
                            ("BUTTON_NEXT", "ACTION_WPS_SEEKFWD")):
            self.assert_actions(self.hold(context, key), action, action, "ACTION_WPS_STOPSEEK")
        for key, action in (("BUTTON_VOL_UP", "ACTION_WPS_VOLUP"),
                            ("BUTTON_VOL_DOWN", "ACTION_WPS_VOLDOWN")):
            self.assert_actions(self.hold(context, key), action, action, action)

    def test_chords_do_not_leak_short_release_actions(self):
        for reverse in (False, True):
            for context, modifier, key, action in (
                ("CONTEXT_LIST", "BUTTON_POWER", "BUTTON_PLAY", "ACTION_STD_MENU"),
                ("CONTEXT_WPS", "BUTTON_POWER", "BUTTON_PLAY", "ACTION_WPS_MENU"),
                ("CONTEXT_WPS", "BUTTON_POWER", "BUTTON_NEXT", "ACTION_WPS_CONTEXT"),
                ("CONTEXT_WPS", "BUTTON_PLAY", "BUTTON_NEXT", "ACTION_WPS_BROWSE"),
                ("CONTEXT_WPS", "BUTTON_PLAY", "BUTTON_VOL_UP", "ACTION_WPS_PITCHSCREEN"),
                ("CONTEXT_WPS", "BUTTON_PLAY", "BUTTON_VOL_DOWN", "ACTION_WPS_STOP"),
                ("CONTEXT_WPS", "BUTTON_POWER", "BUTTON_VOL_DOWN", "ACTION_WPS_QUICKSCREEN"),
                ("CONTEXT_LIST", "BUTTON_POWER", "BUTTON_VOL_DOWN", "ACTION_STD_QUICKSCREEN"),
            ):
                with self.subTest(context=context, key=key, reverse=reverse):
                    self.library.test_reset(False)
                    self.assert_actions(self.chord(context, modifier, key,
                                                   reverse_release=reverse, repeat=True), action)

    def test_reader_cursor_range_context_pause_and_exit(self):
        context = "CONTEXT_SETTINGS"
        self.assert_actions(self.tap(context, "BUTTON_VOL_UP", True), "ACTION_SETTINGS_DEC")
        self.assert_actions(self.tap(context, "BUTTON_VOL_DOWN", True), "ACTION_SETTINGS_INC")
        self.assert_actions(self.hold(context, "BUTTON_VOL_UP", True))
        self.assert_actions(self.hold(context, "BUTTON_VOL_DOWN", True))
        self.assertEqual(self.library.test_volume_calls(), 4)
        self.assert_actions(self.tap(context, "BUTTON_NEXT", True), "ACTION_STD_NEXT")
        self.assert_actions(self.hold(context, "BUTTON_NEXT", True), "ACTION_STD_CONTEXT")
        self.assert_actions(self.tap(context, "BUTTON_PLAY", True), "ACTION_STD_PREV")
        self.assert_actions(self.hold(context, "BUTTON_PLAY", True),
                            "ACTION_STD_PREVREPEAT", "ACTION_STD_PREVREPEAT")
        self.assert_actions(self.tap(context, "BUTTON_POWER", True), "ACTION_STD_OK")
        for reverse in (False, True):
            self.assert_actions(self.chord(context, "BUTTON_POWER", "BUTTON_PLAY", True,
                                           reverse_release=reverse, repeat=True), "ACTION_STD_CANCEL")

    def test_settings_values_fields_accept_and_cancel(self):
        for context in ("CONTEXT_SETTINGS", "CONTEXT_SETTINGS_EQ", "CONTEXT_SETTINGS_TIME",
                        "CONTEXT_SETTINGS_COLOURCHOOSER"):
            with self.subTest(context=context):
                self.library.test_reset(False)
                self.assert_actions(self.tap(context, "BUTTON_VOL_UP"), "ACTION_SETTINGS_INC")
                self.assert_actions(self.tap(context, "BUTTON_VOL_DOWN"), "ACTION_SETTINGS_DEC")
                self.assert_actions(self.hold(context, "BUTTON_VOL_UP"))
                self.assert_actions(self.hold(context, "BUTTON_VOL_DOWN"))
                self.assertEqual(self.library.test_volume_calls(), 4)
                self.assert_actions(self.tap(context, "BUTTON_PLAY"), "ACTION_STD_PREV")
                self.assert_actions(self.tap(context, "BUTTON_NEXT"), "ACTION_STD_NEXT")
                self.assert_actions(self.tap(context, "BUTTON_POWER"), "ACTION_STD_OK")
                self.assert_actions(self.hold(context, "BUTTON_PLAY"), "ACTION_STD_CANCEL")

    def test_confirmation_accepts_only_short_activate(self):
        context = "CONTEXT_YESNOSCREEN"
        self.assert_actions(self.tap(context, "BUTTON_NEXT"), "ACTION_YESNO_ACCEPT")
        self.assert_actions(self.hold(context, "BUTTON_NEXT"))
        self.assert_actions(self.tap(context, "BUTTON_PLAY"), "ACTION_STD_CANCEL")
        self.assert_actions(self.tap(context, "BUTTON_POWER"), "ACTION_YESNO_ACCEPT")
        self.assert_actions(self.hold(context, "BUTTON_POWER"))

    def test_volume_taps_wait_for_release_and_holds_are_global_without_gui_leaks(self):
        contexts = [context for _, context, _ in CALLERS] + [
            "CONTEXT_STD", "CONTEXT_LIST", "CONTEXT_TREE", "CONTEXT_MAINMENU",
            "CONTEXT_BOOKMARKSCREEN", "CONTEXT_SETTINGS", "CONTEXT_MORSE_INPUT",
        ]
        for context, reader in [(context, False) for context in contexts] + [("CONTEXT_SETTINGS", True)]:
            for key, direction in (("BUTTON_VOL_UP", 1), ("BUTTON_VOL_DOWN", -1)):
                with self.subTest(context=context, reader=reader, key=key):
                    self.library.test_reset(False)
                    button = self.value(key)
                    self.assertEqual(self.event(context, button, reader), self.value("ACTION_NONE"))
                    self.assertEqual(self.library.test_volume_calls(), 0)
                    for _ in range(3):
                        action = self.event(context, button | self.value("BUTTON_REPEAT"), reader)
                        self.assertEqual(action, self.value("ACTION_NONE"))
                        self.assertFalse(self.library.test_list_action(action))
                    self.assertEqual(self.event(context, button | self.value("BUTTON_REL"), reader),
                                     self.value("ACTION_NONE"))
                    self.assertEqual(self.library.test_volume_calls(), 3)
                    self.assertEqual(self.library.test_volume_steps(), 3 * direction)

    def test_mapping_emits_existing_volume_actions_only_on_repeat(self):
        context = self.value("CONTEXT_LIST")
        for key, action in (("BUTTON_VOL_UP", "ACTION_LIST_VOLUP"),
                            ("BUTTON_VOL_DOWN", "ACTION_LIST_VOLDOWN")):
            self.library.test_reset(False)
            button = self.value(key)
            events = [button, button | self.value("BUTTON_REPEAT"),
                      button | self.value("BUTTON_REPEAT"), button | self.value("BUTTON_REL")]
            self.assertEqual([self.library.test_mapping_event(context, event) for event in events],
                             [self.value("ACTION_NONE"), self.value(action), self.value(action),
                              self.value("ACTION_NONE")])
            self.assertEqual(self.library.test_volume_calls(), 0)

    def test_global_volume_runs_in_custom_action_and_is_r1_only(self):
        for key, direction in (("BUTTON_VOL_UP", 1), ("BUTTON_VOL_DOWN", -1)):
            self.library.test_reset(False)
            button = self.value(key)
            for event in (button, button | self.value("BUTTON_REPEAT"), button | self.value("BUTTON_REL")):
                self.assertEqual(self.library.test_custom_event(self.value("CONTEXT_KEYBOARD"), event),
                                 self.value("ACTION_NONE"))
            self.assertEqual(self.library.test_volume_steps(), direction)
            self.assertEqual(self.library.test_volume_calls(), 1)
        for target, probe in self.entry_libraries.items():
            for action in ("ACTION_LIST_VOLUP", "ACTION_LIST_VOLDOWN", "ACTION_STD_OK"):
                for custom in (False, True):
                    with self.subTest(target=target, action=action, custom=custom):
                        self.assertEqual(probe.test_entry(self.value(action), custom), self.value(action))
                        self.assertEqual(probe.test_entry_volume(), 0)

    def test_global_volume_respects_softlock_and_first_key_backlight_filter(self):
        context = "CONTEXT_MAINMENU"
        self.chord(context, "BUTTON_POWER", "BUTTON_VOL_UP")
        self.hold(context, "BUTTON_VOL_UP")
        self.assertEqual(self.library.test_volume_calls(), 0)
        self.library.test_lock_mask(self.value("SEL_ACTION_ENABLED") | self.value("SEL_ACTION_VOL"))
        self.assert_actions(self.hold(context, "BUTTON_VOL_UP"))
        self.assertEqual(self.library.test_volume_steps(), 2)
        self.assertEqual(self.library.test_volume_calls(), 2)
        for custom in (False, True):
            self.library.test_reset(False)
            self.library.test_backlight(False, True)
            button = self.value("BUTTON_VOL_UP")
            for event in (button, button | self.value("BUTTON_REPEAT"), button | self.value("BUTTON_REL")):
                if custom:
                    action = self.library.test_custom_event(self.value(context), event)
                else:
                    action = self.event(context, event)
                self.assertEqual(action, self.value("ACTION_NONE"))
            self.assertEqual(self.library.test_volume_calls(), 0)
            self.assert_actions(self.hold(context, "BUTTON_VOL_UP"))
            self.assertEqual(self.library.test_volume_steps(), 2)

    def test_native_remaps_can_replace_or_request_global_volume(self):
        context = self.value("CONTEXT_LIST")
        button = self.value("BUTTON_VOL_UP")
        self.library.test_remap_event(context, self.value("ACTION_STD_NEXT"),
                                      button | self.value("BUTTON_REPEAT"), self.value("BUTTON_NONE"))
        self.assert_actions(self.hold("CONTEXT_LIST", "BUTTON_VOL_UP"), "ACTION_STD_NEXT", "ACTION_STD_NEXT")
        self.assertEqual(self.library.test_volume_calls(), 0)
        self.library.test_reset(False)
        self.library.test_remap(context, self.value("ACTION_LIST_VOLUP"))
        self.assert_actions(self.tap("CONTEXT_LIST", "BUTTON_VOL_UP"))
        self.assertEqual(self.library.test_volume_calls(), 1)
        self.assertEqual(self.library.test_volume_steps(), 1)

    def test_chords_never_adjust_global_volume(self):
        for reverse in (False, True):
            for context, modifier, key in (
                ("CONTEXT_LIST", "BUTTON_POWER", "BUTTON_VOL_UP"),
                ("CONTEXT_LIST", "BUTTON_POWER", "BUTTON_VOL_DOWN"),
                ("CONTEXT_KEYBOARD", "BUTTON_POWER", "BUTTON_VOL_DOWN"),
                ("CONTEXT_WPS", "BUTTON_PLAY", "BUTTON_VOL_UP"),
                ("CONTEXT_WPS", "BUTTON_PLAY", "BUTTON_VOL_DOWN"),
            ):
                with self.subTest(context=context, key=key, reverse=reverse):
                    self.library.test_reset(False)
                    self.chord(context, modifier, key, reverse_release=reverse, repeat=True)
                    self.assertEqual(self.library.test_volume_calls(), 0)

    def test_time_editor_actions_move_fields_and_values_but_holds_change_only_volume(self):
        self.library.test_time_reset()
        for key, field, value in (("BUTTON_PLAY", 1, 30), ("BUTTON_NEXT", 2, 30),
                                  ("BUTTON_VOL_UP", 2, 31), ("BUTTON_VOL_DOWN", 2, 30)):
            for action in self.tap("CONTEXT_SETTINGS_TIME", key):
                self.library.test_time_action(action)
            self.assertEqual(self.library.test_time_value(True), field)
            self.assertEqual(self.library.test_time_value(False), value)
        for key in ("BUTTON_VOL_UP", "BUTTON_VOL_DOWN"):
            for action in self.hold("CONTEXT_SETTINGS_TIME", key):
                self.library.test_time_action(action)
        self.assertEqual(self.library.test_time_value(True), 2)
        self.assertEqual(self.library.test_time_value(False), 30)
        self.assertEqual(self.library.test_volume_calls(), 4)

    def test_reader_actions_dispatch_consistent_text_axes(self):
        self.library.test_reader_reset()
        for key, position, unit, toggles in (
            ("BUTTON_PLAY", -1, 0, 0), ("BUTTON_NEXT", 0, 0, 0),
            ("BUTTON_VOL_UP", 0, -1, 0), ("BUTTON_VOL_DOWN", 0, 0, 0),
            ("BUTTON_POWER", 0, 0, 1),
        ):
            for action in self.tap("CONTEXT_SETTINGS", key, True):
                self.library.test_reader_action(action)
            self.assertEqual([self.library.test_reader_value(field) for field in range(3)],
                             [position, unit, toggles])
        for key in ("BUTTON_VOL_UP", "BUTTON_VOL_DOWN"):
            for action in self.hold("CONTEXT_SETTINGS", key, True):
                self.library.test_reader_action(action)
        self.assertEqual([self.library.test_reader_value(field) for field in range(3)], [0, 0, 1])
        self.assertEqual(self.library.test_volume_calls(), 4)

    def test_quickscreen_and_pitch_controls(self):
        for key, action in (("BUTTON_VOL_UP", "ACTION_QS_TOP"),
                            ("BUTTON_VOL_DOWN", "ACTION_QS_DOWN"),
                            ("BUTTON_PLAY", "ACTION_QS_LEFT"),
                            ("BUTTON_NEXT", "ACTION_QS_RIGHT"),
                            ("BUTTON_POWER", "ACTION_STD_CANCEL")):
            self.assert_actions(self.tap("CONTEXT_QUICKSCREEN", key), action)
        for key, action in (("BUTTON_VOL_UP", "ACTION_PS_INC_SMALL"),
                            ("BUTTON_VOL_DOWN", "ACTION_PS_DEC_SMALL"),
                            ("BUTTON_PLAY", "ACTION_PS_SLOWER"),
                            ("BUTTON_NEXT", "ACTION_PS_FASTER"),
                            ("BUTTON_POWER", "ACTION_PS_EXIT")):
            self.assert_actions(self.tap("CONTEXT_PITCHSCREEN", key), action)
        self.assert_actions(self.chord("CONTEXT_PITCHSCREEN", "BUTTON_POWER", "BUTTON_PLAY"),
                            "ACTION_PS_RESET")
        self.assert_actions(self.chord("CONTEXT_PITCHSCREEN", "BUTTON_POWER", "BUTTON_NEXT"),
                            "ACTION_PS_TOGGLE_MODE")

    def test_keyboard_has_all_navigation_and_editing_actions(self):
        context = "CONTEXT_KEYBOARD"
        for key, action in (("BUTTON_VOL_UP", "ACTION_KBD_UP"),
                            ("BUTTON_VOL_DOWN", "ACTION_KBD_DOWN"),
                            ("BUTTON_PLAY", "ACTION_KBD_LEFT"),
                            ("BUTTON_NEXT", "ACTION_KBD_RIGHT"),
                            ("BUTTON_POWER", "ACTION_KBD_SELECT")):
            self.assert_actions(self.tap(context, key), action)
        for key, action in (("BUTTON_PLAY", "ACTION_KBD_CURSOR_LEFT"),
                            ("BUTTON_NEXT", "ACTION_KBD_CURSOR_RIGHT")):
            self.assert_actions(self.hold(context, key), action, action)
        self.assert_actions(self.hold(context, "BUTTON_POWER"), "ACTION_KBD_DONE")
        for reverse in (False, True):
            for modifier, key, action in (
                ("BUTTON_POWER", "BUTTON_NEXT", "ACTION_KBD_DONE"),
                ("BUTTON_POWER", "BUTTON_PLAY", "ACTION_KBD_ABORT"),
                ("BUTTON_POWER", "BUTTON_VOL_DOWN", "ACTION_KBD_BACKSPACE"),
                ("BUTTON_PLAY", "BUTTON_NEXT", "ACTION_KBD_PAGE_FLIP"),
            ):
                self.assert_actions(self.chord(context, modifier, key,
                                               reverse_release=reverse, repeat=True), action)

    def test_lock_unlock_works_when_caller_allows_it_including_reader(self):
        for context, reader in (("CONTEXT_LIST", False), ("CONTEXT_WPS", False),
                                ("CONTEXT_KEYBOARD", False), ("CONTEXT_SETTINGS", True)):
            with self.subTest(context=context, reader=reader):
                self.library.test_reset(False)
                self.assert_actions(self.chord(context, "BUTTON_POWER", "BUTTON_VOL_UP", reader),
                                    "ACTION_REDRAW", "ACTION_REDRAW", "ACTION_REDRAW")
                self.assertTrue(self.library.test_locked())
                self.assertFalse(self.library.test_touch_enabled())
                actions = self.tap(context, "BUTTON_NEXT", reader)
                self.assertTrue(all(action == self.value("ACTION_REDRAW") for action in actions))
                self.chord(context, "BUTTON_POWER", "BUTTON_VOL_UP", reader)
                self.assertFalse(self.library.test_locked())
                self.assertTrue(self.library.test_touch_enabled())

    def test_lock_requires_softlock_permission_from_calling_screen(self):
        power = self.value("BUTTON_POWER")
        lock = power | self.value("BUTTON_VOL_UP")
        context = self.value("CONTEXT_KEYBOARD")
        self.library.test_event(context, power, False, False)
        self.assertEqual(self.library.test_event(context, lock, False, False),
                         self.value("ACTION_STD_KEYLOCK"))
        self.assertFalse(self.library.test_locked())
        self.assertTrue(self.library.test_touch_enabled())

    def test_actual_caller_wiring_preserves_other_targets_and_timeouts(self):
        for target, probe in self.caller_libraries.items():
            permission = self.value("ALLOW_SOFTLOCK") if target == "r1" else 0
            for index, (path, context, timeout) in enumerate(CALLERS):
                for morse in (False, True):
                    with self.subTest(target=target, path=path, morse=morse):
                        self.assertEqual(getattr(probe, f"test_caller_{index}")(morse),
                                         self.value(context) | permission)
                        self.assertEqual(probe.test_caller_timeout(), timeout)
            for morse in (False, True):
                with self.subTest(target=target, keyboard_morse=morse):
                    context = "CONTEXT_MORSE_INPUT" if morse else "CONTEXT_KEYBOARD"
                    self.assertEqual(probe.test_caller_0_morse(morse), self.value(context) | permission)
                    self.assertEqual(probe.test_caller_timeout(), 50)

    def test_actual_r1_callers_lock_unlock_and_filter_actions(self):
        probe = self.caller_libraries["r1"]
        contexts = [(path, getattr(probe, f"test_caller_{index}")(False))
                    for index, (path, _, _) in enumerate(CALLERS)]
        contexts.append(("keyboard Morse", probe.test_caller_0_morse(True)))
        power = self.value("BUTTON_POWER")
        volume = self.value("BUTTON_VOL_UP")
        release = self.value("BUTTON_REL")
        for path, context in contexts:
            for reverse in (False, True):
                with self.subTest(path=path, reverse=reverse):
                    self.library.test_reset(False)
                    released = (power, volume) if reverse else (volume, power)
                    chord = [power, power | volume] + [button | release for button in released]
                    for button in chord:
                        self.library.test_event(context, button, False, False)
                    self.assertTrue(self.library.test_locked())
                    self.assertFalse(self.library.test_touch_enabled())
                    for button in (self.value("BUTTON_NEXT"), self.value("BUTTON_NEXT") | release):
                        self.assertEqual(self.library.test_event(context, button, False, False),
                                         self.value("ACTION_REDRAW"))
                    for button in chord:
                        self.library.test_event(context, button, False, False)
                    self.assertFalse(self.library.test_locked())
                    self.assertTrue(self.library.test_touch_enabled())

    def test_point_keyboard_physical_actions_move_actual_grid_selection(self):
        self.library.test_keyboard_reset(False)
        for key, column, row in (("BUTTON_NEXT", 2, 1), ("BUTTON_VOL_DOWN", 2, 2),
                                 ("BUTTON_PLAY", 1, 2), ("BUTTON_VOL_UP", 1, 1)):
            for action in self.tap("CONTEXT_KEYBOARD", key):
                self.library.test_keyboard_action(action)
            self.assertEqual(self.library.test_keyboard_coordinate(False), column)
            self.assertEqual(self.library.test_keyboard_coordinate(True), row)
        for key in ("BUTTON_VOL_UP", "BUTTON_VOL_DOWN"):
            for action in self.hold("CONTEXT_KEYBOARD", key):
                self.library.test_keyboard_action(action)
        self.assertEqual(self.library.test_keyboard_coordinate(False), 1)
        self.assertEqual(self.library.test_keyboard_coordinate(True), 1)
        self.assertEqual(self.library.test_volume_calls(), 4)
        self.library.test_keyboard_reset(True)
        for action in self.tap("CONTEXT_KEYBOARD", "BUTTON_NEXT"):
            self.library.test_keyboard_action(action)
        self.assertEqual(self.library.test_keyboard_coordinate(False), 2)
        for action in self.tap("CONTEXT_KEYBOARD", "BUTTON_NEXT"):
            self.library.test_keyboard_action(action)
        self.assertEqual(self.library.test_keyboard_coordinate(False), 4)
        for action in self.tap("CONTEXT_KEYBOARD", "BUTTON_PLAY"):
            self.library.test_keyboard_action(action)
        self.assertEqual(self.library.test_keyboard_coordinate(False), 3)
        for action in self.tap("CONTEXT_KEYBOARD", "BUTTON_PLAY"):
            self.library.test_keyboard_action(action)
        self.assertEqual(self.library.test_keyboard_coordinate(False), 1)

    def test_power_hold_only_finishes_keyboard_and_preserves_shutdown_threshold(self):
        self.assertEqual(self.value("POWEROFF_BUTTON"), self.value("BUTTON_POWER"))
        self.assertEqual(self.value("POWEROFF_COUNT"), 25)
        for context, reader in (("CONTEXT_LIST", False), ("CONTEXT_WPS", False),
                                ("CONTEXT_SETTINGS", True), ("CONTEXT_KEYBOARD", False)):
            self.library.test_reset(False)
            power = self.value("BUTTON_POWER")
            events = [power] + [power | self.value("BUTTON_REPEAT")] * 27
            events += [power | self.value("BUTTON_REL")]
            expected = ("ACTION_KBD_DONE",) if context == "CONTEXT_KEYBOARD" else ()
            self.assert_actions(self.sequence(context, events, reader), *expected)
        driver = source("firmware/drivers/button.c")
        self.assertRegex(driver, r'btn & POWEROFF_BUTTON')
        self.assertRegex(driver, r'repeat_count > POWEROFF_COUNT\)\s*\{[^}]*sys_poweroff\(\)')

    def test_context_change_and_release_wait_do_not_activate(self):
        button = self.value("BUTTON_NEXT")
        release = button | self.value("BUTTON_REL")
        repeat = button | self.value("BUTTON_REPEAT")
        self.event("CONTEXT_LIST", button)
        self.assert_actions(self.sequence("CONTEXT_WPS", [repeat, release]))
        self.assert_actions(self.tap("CONTEXT_WPS", "BUTTON_NEXT"), "ACTION_WPS_SKIPNEXT")
        self.event("CONTEXT_LIST", button)
        self.library.test_wait_for_release()
        self.assert_actions(self.sequence("CONTEXT_LIST", [repeat, release]))
        self.assert_actions(self.tap("CONTEXT_LIST", "BUTTON_NEXT"), "ACTION_STD_OK")

    def test_native_core_remapping_still_precedes_default_map(self):
        self.library.test_remap(self.value("CONTEXT_LIST"), self.value("ACTION_STD_NEXT"))
        self.assert_actions(self.tap("CONTEXT_LIST", "BUTTON_VOL_UP"), "ACTION_STD_NEXT")
        self.assert_actions(self.tap("CONTEXT_LIST", "BUTTON_NEXT"), "ACTION_STD_OK")

    def test_reader_uses_shared_core_remapping(self):
        context = self.value("CONTEXT_CUSTOM") | self.value("CONTEXT_CUSTOM2") | self.value("CONTEXT_STD")
        self.library.test_remap(context, self.value("ACTION_SETTINGS_INC"))
        self.assert_actions(self.tap("CONTEXT_SETTINGS", "BUTTON_VOL_UP", True), "ACTION_SETTINGS_INC")
        self.assert_actions(self.tap("CONTEXT_SETTINGS", "BUTTON_NEXT", True), "ACTION_STD_NEXT")

    def test_no_phantom_previous_or_virtual_key_dependency(self):
        physical = 0
        for key in ("BUTTON_POWER", "BUTTON_PLAY", "BUTTON_NEXT", "BUTTON_VOL_UP", "BUTTON_VOL_DOWN"):
            physical |= self.value(key)
        self.assertEqual(self.library.test_physical_table_buttons(), physical)
        self.assertEqual(physical & self.value("BUTTON_PREV"), 0)

    def test_custom_binding_native_fallback_uses_real_context_and_preserves_remap(self):
        self.library.test_default_event.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_bool]
        for context, button, held, expected in [
            ("CONTEXT_STD", "BUTTON_NEXT", False, "ACTION_STD_OK"),
            ("CONTEXT_STD", "BUTTON_PLAY", False, "ACTION_STD_CANCEL"),
            ("CONTEXT_WPS", "BUTTON_PLAY", False, "ACTION_WPS_SKIPPREV"),
        ]:
            self.assertEqual(self.library.test_default_event(self.value(context),
                self.value(button) | self.value("BUTTON_REL"), held), self.value(expected))
        button = self.value("BUTTON_PLAY")
        self.assertEqual(self.library.test_default_event(self.value("CONTEXT_WPS"),
            button | self.value("BUTTON_REPEAT"), False), self.value("ACTION_WPS_SEEKBACK"))
        self.assertEqual(self.library.test_default_event(self.value("CONTEXT_WPS"),
            button | self.value("BUTTON_REL"), True), self.value("ACTION_WPS_STOPSEEK"))
        context = self.value("CONTEXT_STD")
        self.library.test_remap(context, self.value("ACTION_STD_MENU"))
        self.assertEqual(self.library.test_default_event(context,
            self.value("BUTTON_VOL_UP") | self.value("BUTTON_REL"), False), self.value("ACTION_STD_PREV"))
        self.assert_actions(self.tap("CONTEXT_STD", "BUTTON_VOL_UP"), "ACTION_STD_MENU")

    def test_control_docs_link_current_shared_gestures_typing_and_curtain(self):
        for path, expected, superseded in (
            ("docs/HIBY-R1-CONTROLS.md", (
                "right swipe = Down", "left swipe = Up", "upward = Left", "downward = Right",
                "double tap = OK", "left-then-right = Back", "right-then-left = Home",
                "up-down, down-up", "left-up, right-up, up-left, up-right, left-down",
                "Additional paths start unassigned", "ACCESSIBILITY-CURTAIN.md", "ACCESSIBILITY-TYPING.md",
            ), "left swipe = Down"),
            ("docs/HIBY-R1-CONTROLS-PL.md", (
                "ruch w prawo = Dół", "w lewo = Góra", "w górę = Lewo", "w dół = Prawo",
                "podwójne stuknięcie = OK", "lewo–prawo = Wstecz", "prawo–lewo = Ekran główny",
                "góra–dół, dół–góra", "lewo–góra, prawo–góra, góra–lewo, góra–prawo, lewo–dół",
                "Dodatkowe ścieżki są domyślnie nieprzypisane", "ACCESSIBILITY-CURTAIN-PL.md", "ACCESSIBILITY-TYPING-PL.md",
            ), "ruch w lewo = Dół"),
        ):
            with self.subTest(path=path):
                text = " ".join(source(path).split())
                for phrase in expected:
                    self.assertIn(phrase, text)
                self.assertNotIn(superseded, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
