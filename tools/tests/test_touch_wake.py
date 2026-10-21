"""Compile real touch-wake state, persistence and menus without hardware input."""

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
from test_accessibility_integration import function

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/accessibility_touch_wake.c"
HEADER = ROOT / "apps/accessibility_touch_wake.h"
PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#define HZ 100
#define ROCKBOX_DIR "/.rockbox"
#define MENU_ATTACHED_USB 313
#define ID2P(value) (value)
#define RB_INT 0
void action_update_touch_lock(void);
enum {TOUCHEVENT_NONE, TOUCHEVENT_PRESS, TOUCHEVENT_CONTACT, TOUCHEVENT_RELEASE};
struct touchevent { int type; short x, y; long tick; };
struct opt_items { const unsigned char *string; int voice_id; };
struct simplelist_info {
    int selection;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
};
static long current_tick;
static char persisted[256], temporary[256];
static size_t read_offset, written;
static int failure, reads, writes, syncs, renames, removes, closes;
static bool temporary_exists, usb, option_usb;
#define firmware_enabled touchscreen_wake_enabled()
static int selection, choice, list_calls, splashes, spoken[128], speech_count;
static const char *str(int label) { (void)label; return "label"; }
static unsigned int accessibility_touch_distance(unsigned int distance) { return distance; }
static void splash(int ticks, int label) { assert(ticks > 0 && label == LANG_ERROR_WRITING_CONFIG); ++splashes; }
static void talk_id(int label, bool enqueue) {
    assert(speech_count < 128); assert(enqueue == (speech_count % 2 != 0));
    spoken[speech_count++] = label;
}
static bool set_option(const char *title, int *value, int kind,
                       const struct opt_items *options, int count, void *callback) {
    assert(title && kind == RB_INT && count == 3 && !callback);
    assert(options[0].voice_id == LANG_OFF && options[1].voice_id == LANG_TOUCH_WAKE_LIGHT &&
           options[2].voice_id == LANG_TOUCH_WAKE_UNLOCK);
    *value = choice;
    return option_usb;
}
static void simplelist_info_init(struct simplelist_info *list, const char *title, int count, void *data) {
    assert(title && count == 3 && !data); memset(list, 0, sizeof(*list));
}
static bool simplelist_show_list(struct simplelist_info *list) {
    char buffer[256];
    for (int index = 0; index < 3; ++index) {
        assert(list->get_name(index, NULL, buffer, sizeof(buffer)) == buffer);
        assert(buffer[0]); list->get_talk(index, NULL);
    }
    list->selection = list_calls++ ? -1 : selection;
    return usb;
}
static int fixture_open(const char *path, int flags, ...) {
    if (flags & O_WRONLY) {
        assert(!strcmp(path, "/.rockbox/touch-wake.cfg.tmp") && (flags & O_EXCL));
        if (failure == 1 || temporary_exists) { errno = EEXIST; return -1; }
        temporary_exists = true; written = 0; memset(temporary, 0, sizeof(temporary));
        return 11;
    }
    assert(!strcmp(path, "/.rockbox/touch-wake.cfg")); ++reads; read_offset = 0;
    if (!persisted[0]) { errno = ENOENT; return -1; }
    return 10;
}
static ssize_t fixture_read(int descriptor, void *data, size_t capacity) {
    assert(descriptor == 10);
    if (failure == 6) { errno = EIO; return -1; }
    if (failure == 8) { errno = EINTR; return -1; }
    size_t available = strlen(persisted) - read_offset;
    if (capacity > available) capacity = available;
    if (capacity > 2) capacity = 2;
    memcpy(data, persisted + read_offset, capacity); read_offset += capacity;
    return capacity;
}
static ssize_t fixture_write(int descriptor, const void *data, size_t count) {
    assert(descriptor == 11); ++writes;
    if (failure == 2) return 0;
    if (failure == 9) { errno = EINTR; return -1; }
    if (count > 2) count = 2;
    assert(written + count < sizeof(temporary));
    memcpy(temporary + written, data, count); written += count;
    return count;
}
static int fixture_fsync(int descriptor) { assert(descriptor == 11); ++syncs; return failure == 3 ? -1 : 0; }
static int fixture_close(int descriptor) { ++closes; return (failure == 4 && descriptor == 11) || (failure == 7 && descriptor == 10) ? -1 : 0; }
static int fixture_remove(const char *path) { assert(strstr(path, ".tmp")); ++removes; temporary_exists = false; return 0; }
static int fixture_rename(const char *source, const char *target) {
    assert(strstr(source, ".tmp") && !strcmp(target, "/.rockbox/touch-wake.cfg")); ++renames;
    if (failure == 5) return -1;
    strcpy(persisted, temporary); temporary_exists = false; return 0;
}
#define open fixture_open
#define read fixture_read
#define write fixture_write
#define fsync fixture_fsync
#define close fixture_close
#define remove fixture_remove
#define rename fixture_rename
'''
INTEGRATION_MOCKS = r'''
struct gesture { int unused; };
typedef struct {
    bool keys_locked, repeated;
    int button, action;
    unsigned int softlock_mask;
    long tick, inactivity_tick;
    struct gesture gesture;
    struct touchevent touchevent;
} action_last_t;
typedef struct { int button, action, context; } action_cur_t;
static action_last_t action_last;
static bool accessibility_forced_lock, backlight_lit, curtain, driver_touch_enabled = true;
static int backlights, notices, lock_queue_clears, navigation_cancels, ui_resets;
static intptr_t button_data = (100 << 16) | 100;
static bool touch_wake_enabled, touch_wake_locked;
static void accessibility_reset(void) { ++ui_resets; }
static void gesture_reset(struct gesture *state) { (void)state; }
static intptr_t button_get_data(void) { return button_data; }
static bool is_backlight_on(bool ignore) { (void)ignore; return backlight_lit; }
static bool backlight_screen_curtain_active(void) { return curtain; }
static void backlight_on_ignore(bool ignore, int ticks) { (void)ignore; (void)ticks; }
static void backlight_on(void) { ++backlights; if (!curtain) backlight_lit = true; }
static void root_menu_cancel_navigation(void) { ++navigation_cancels; }
static void accessibility_clear_lock_queue(void) { ++lock_queue_clears; }
static void button_enable_touch(bool enabled) { driver_touch_enabled = enabled; }
static void accessibility_screen_lock_changed(bool locked) { (void)locked; ++notices; }
static void skin_request_update_locked(bool locked) { assert(!locked); }
#define SYS_BATTERY_UPDATE 0x40000003
#define SYS_CHARGER_CONNECTED 0x4000000b
#define SYS_CHARGER_DISCONNECTED 0x4000000c
'''
INTEGRATION_CASES = r'''
static void preferences(unsigned int single, unsigned int twice, unsigned int triple);
static int action_sample(int button, int milliseconds) {
    current_tick = milliseconds / 10;
    action_cur_t input = {.button = button, .context = 0};
    bool consumed = accessibility_handle_touch_wake(&action_last, &input);
    return consumed ? input.action : -100;
}
static int integration_case(const char *scenario) {
    if (!strcmp(scenario, "integration-factory")) {
        do_key_lock(true);
        assert(!driver_touch_enabled && !touchscreen_wake_filter_needed());
        assert(action_sample(BUTTON_TOUCHSCREEN, 0) == -100);
        do_key_lock(false);
        assert(driver_touch_enabled && notices == 2);
    } else if (!strcmp(scenario, "integration-light") || !strcmp(scenario, "integration-unlock")) {
        bool unlock = !strcmp(scenario, "integration-unlock");
        preferences(unlock ? 2 : 1, 0, 0);
        do_key_lock(true);
        assert(driver_touch_enabled && touchscreen_wake_filter_needed());
        assert(action_sample(BUTTON_TOUCHSCREEN, 0) == ACTION_NONE);
        assert(action_sample(BUTTON_TOUCHSCREEN | BUTTON_REL, 40) == ACTION_NONE);
        assert(action_sample(BUTTON_NONE, 400) == ACTION_REDRAW);
        assert(action_last.keys_locked == !unlock && backlight_lit && backlights == 1);
        assert(notices == (unlock ? 2 : 1));
        assert(touchscreen_wake_filter_needed() == !unlock);
        assert(action_sample(BUTTON_NONE, 500) == -100);
    } else if (!strcmp(scenario, "integration-grid-and-curtain")) {
        preferences(2, 0, 0);
        assert(touchscreen_wake_filter_needed());
        assert(action_sample(BUTTON_CENTER, 0) == ACTION_NONE);
        assert(action_sample(BUTTON_CENTER | BUTTON_REL, 40) == ACTION_NONE);
        assert(action_sample(BUTTON_NONE, 400) == ACTION_REDRAW && backlight_lit);
        backlight_lit = false; curtain = true;
        assert(!touchscreen_wake_filter_needed());
        assert(action_sample(BUTTON_TOUCHSCREEN, 1000) == -100);
        do_key_lock(true);
        assert(touchscreen_wake_filter_needed());
        assert(action_sample(BUTTON_TOUCHSCREEN, 1100) == ACTION_NONE);
        assert(action_sample(BUTTON_TOUCHSCREEN | BUTTON_REL, 1140) == ACTION_NONE);
        assert(action_sample(BUTTON_NONE, 1500) == ACTION_REDRAW);
        assert(curtain && !backlight_lit && !action_last.keys_locked);
    } else if (!strcmp(scenario, "integration-physical-cancel")) {
        preferences(2, 0, 0); do_key_lock(true);
        assert(action_sample(BUTTON_TOUCHSCREEN, 0) == ACTION_NONE);
        assert(action_sample(BUTTON_TOUCHSCREEN | BUTTON_REL, 40) == ACTION_NONE);
        assert(action_sample(BUTTON_POWER, 100) == -100);
        assert(action_sample(BUTTON_NONE, 500) == -100);
        assert(action_last.keys_locked && !backlights);
    } else if (!strcmp(scenario, "integration-unlock-tail")) {
        preferences(2, 0, 0); do_key_lock(true);
        action_sample(BUTTON_TOUCHSCREEN, 0);
        action_sample(BUTTON_TOUCHSCREEN | BUTTON_REL, 40);
        assert(action_sample(BUTTON_TOUCHSCREEN, 500) == ACTION_REDRAW);
        assert(!action_last.keys_locked && backlight_lit);
        assert(action_sample(BUTTON_TOUCHSCREEN | BUTTON_REL, 540) == ACTION_NONE);
        assert(action_sample(BUTTON_TOUCHSCREEN, 1000) == -100);
    } else if (!strcmp(scenario, "integration-policy-edit")) {
        preferences(2, 0, 0); do_key_lock(true);
        assert(driver_touch_enabled);
        uint8_t disabled[3] = {0}, enabled[3] = {2, 0, 0};
        assert(wake_save(disabled) && !driver_touch_enabled && action_last.keys_locked);
        failure = 9;
        assert(!wake_save(enabled) && !driver_touch_enabled && !firmware_enabled);
        failure = 0;
        action_last.softlock_mask = SEL_ACTION_ENABLED;
        driver_touch_enabled = true;
        assert(wake_save(enabled) && driver_touch_enabled);
        assert(wake_save(disabled) && driver_touch_enabled && action_last.keys_locked);
        assert(notices == 1);
    } else assert(false);
    puts("PASS real firmware and action wake integration");
    return 0;
}
'''
SUFFIX = r'''
static void preferences(unsigned int single, unsigned int twice, unsigned int triple) {
    snprintf(persisted, sizeof(persisted), "RBTOUCH-WAKE:1\nsingle:%u\ndouble:%u\ntriple:%u\n", single, twice, triple);
    wake_loaded = false; memset(wake_actions, 0, sizeof(wake_actions));
    accessibility_touch_wake_cancel();
    accessibility_touch_wake_enabled();
}
static int event(int type, int horizontal, int vertical, int milliseconds, bool locked, bool dark, int context) {
    current_tick = milliseconds / 10;
    struct touchevent input = {type, horizontal, vertical, current_tick};
    return accessibility_touch_wake_process(&input, locked, dark, context);
}
static int poll_at(int milliseconds, bool locked, bool dark, int context) {
    current_tick = milliseconds / 10;
    return accessibility_touch_wake_process(NULL, locked, dark, context);
}
static void tap(int start, bool locked, bool dark, int context) {
    assert(event(TOUCHEVENT_PRESS, 100, 100, start, locked, dark, context) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
    assert(event(TOUCHEVENT_RELEASE, 100, 100, start + 40, locked, dark, context) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
}
int main(int count, char **arguments) {
    assert(count == 2);
    const char *scenario = arguments[1];
    if (!strncmp(scenario, "integration-", 12))
        return integration_case(scenario);
    if (!strcmp(scenario, "defaults")) {
        assert(!accessibility_touch_wake_enabled() && !firmware_enabled && reads == 1 && !writes);
        assert(accessibility_touch_wake_timeout(-1) == -1);
        assert(event(TOUCHEVENT_PRESS, 10, 20, 0, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_PASS);
        assert(!accessibility_touch_wake_enabled() && reads == 1);
    } else if (!strcmp(scenario, "combinations")) {
        for (unsigned int single = 0; single <= 2; ++single)
        for (unsigned int twice = 0; twice <= 2; ++twice)
        for (unsigned int triple = 0; triple <= 2; ++triple) {
            unsigned int options[] = {single, twice, triple};
            for (unsigned int taps = 1; taps <= 3; ++taps) {
                preferences(single, twice, triple);
                if (!(single || twice || triple)) continue;
                for (unsigned int index = 0; index < taps; ++index) {
                    assert(event(TOUCHEVENT_PRESS, 50 + index * 50, 100, index * 100, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
                    int result = event(TOUCHEVENT_RELEASE, 50 + index * 50, 100, index * 100 + 40, true, true, 0);
                    unsigned int expected = options[taps - 1];
                    int complete = expected == 2 ? ACCESSIBILITY_TOUCH_WAKE_UNLOCK : expected == 1 ? ACCESSIBILITY_TOUCH_WAKE_LIGHT : ACCESSIBILITY_TOUCH_WAKE_CONSUMED;
                    assert(result == (index == 2 ? complete : ACCESSIBILITY_TOUCH_WAKE_CONSUMED));
                }
                if (taps < 3) {
                    assert(poll_at((taps - 1) * 100 + 360, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
                    int expected = options[taps - 1] == 2 ? ACCESSIBILITY_TOUCH_WAKE_UNLOCK : options[taps - 1] == 1 ? ACCESSIBILITY_TOUCH_WAKE_LIGHT : ACCESSIBILITY_TOUCH_WAKE_CONSUMED;
                    assert(poll_at((taps - 1) * 100 + 370, true, true, 0) == expected);
                }
                assert(!wake_active && !writes);
            }
        }
    } else if (!strcmp(scenario, "lit-pass-through")) {
        preferences(2, 2, 2);
        assert(event(TOUCHEVENT_PRESS, 10, 20, 0, false, false, 0) == ACCESSIBILITY_TOUCH_WAKE_PASS);
        assert(poll_at(400, false, false, 0) == ACCESSIBILITY_TOUCH_WAKE_PASS);
        tap(1000, false, true, 0);
        assert(poll_at(1400, false, true, 0) == ACCESSIBILITY_TOUCH_WAKE_UNLOCK);
    } else if (!strcmp(scenario, "invalid-contact")) {
        preferences(2, 2, 2);
        tap(0, true, true, 0);
        event(TOUCHEVENT_PRESS, 10, 20, 100, true, true, 0);
        event(TOUCHEVENT_CONTACT, 50, 20, 120, true, true, 0);
        event(TOUCHEVENT_RELEASE, 10, 20, 150, true, true, 0);
        assert(poll_at(600, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_PASS);
        event(TOUCHEVENT_PRESS, 10, 20, 1000, true, true, 0);
        event(TOUCHEVENT_RELEASE, 10, 20, 1400, true, true, 0);
        assert(poll_at(2000, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_PASS);
    } else if (!strcmp(scenario, "cancellation")) {
        preferences(2, 2, 2);
        tap(0, true, true, 0);
        assert(poll_at(400, true, true, 1) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
        assert(!wake_active);
        tap(1000, true, true, 0);
        accessibility_touch_wake_cancel();
        assert(poll_at(1500, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_PASS);
        tap(2000, true, true, 0);
        assert(poll_at(2500, false, false, 0) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
        assert(!wake_active);
    } else if (!strcmp(scenario, "late-press-is-consumed")) {
        preferences(1, 2, 2);
        tap(0, true, true, 0);
        assert(event(TOUCHEVENT_PRESS, 100, 100, 500, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_LIGHT);
        assert(event(TOUCHEVENT_RELEASE, 100, 100, 540, true, false, 0) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
        assert(!wake_active);
    } else if (!strcmp(scenario, "idle-timeout")) {
        preferences(1, 2, 0);
        assert(accessibility_touch_wake_timeout(-1) == -1);
        tap(0, true, true, 0);
        assert(accessibility_touch_wake_timeout(-1) == HZ / 20);
        assert(accessibility_touch_wake_timeout(0) == 0);
        assert(accessibility_touch_wake_timeout(1) == 1);
        assert(poll_at(400, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_LIGHT);
        assert(accessibility_touch_wake_timeout(-1) == -1);
    } else if (!strcmp(scenario, "held-without-idle-polling")) {
        preferences(1, 2, 0);
        assert(event(TOUCHEVENT_PRESS, 100, 100, 0, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
        assert(accessibility_touch_wake_timeout(-1) == -1);
        assert(poll_at(400, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
        assert(accessibility_touch_wake_timeout(-1) == -1);
        assert(event(TOUCHEVENT_RELEASE, 100, 100, 500, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_CONSUMED);
        assert(poll_at(1000, true, true, 0) == ACCESSIBILITY_TOUCH_WAKE_PASS);
    } else if (!strcmp(scenario, "menu")) {
        selection = 1; choice = 2;
        assert(accessibility_touch_wake_menu() == 0 && firmware_enabled && !temporary_exists);
        assert(wake_actions[0] == 0 && wake_actions[1] == 2 && wake_actions[2] == 0);
        assert(syncs == 1 && renames == 1 && writes > 1 && !splashes);
        assert(!strcmp(persisted, "RBTOUCH-WAKE:1\nsingle:0\ndouble:2\ntriple:0\n"));
        wake_loaded = false; memset(wake_actions, 0, sizeof(wake_actions));
        assert(accessibility_touch_wake_enabled() && wake_actions[1] == 2);
    } else if (!strcmp(scenario, "write-failures")) {
        for (int problem = 1; problem <= 9; ++problem) {
            if (problem >= 6 && problem <= 8) continue;
            preferences(0, 0, 0); failure = problem; selection = 0; choice = 2; list_calls = 0;
            int prior = writes;
            assert(accessibility_touch_wake_menu() == 0 && !firmware_enabled && !wake_actions[0]);
            assert(!strcmp(persisted, TOUCH_WAKE_DEFAULT) && !temporary_exists);
            if (problem == 9) assert(writes - prior == 4);
            failure = 0;
        }
        assert(splashes == 6);
    } else if (!strcmp(scenario, "stale-temp")) {
        preferences(0, 0, 0); temporary_exists = true; strcpy(temporary, "keep me");
        selection = 0; choice = 2;
        assert(accessibility_touch_wake_menu() == 0 && !firmware_enabled);
        assert(temporary_exists && !strcmp(temporary, "keep me") && !removes);
    } else if (!strcmp(scenario, "usb")) {
        selection = 0; choice = 2; usb = true;
        assert(accessibility_touch_wake_menu() == MENU_ATTACHED_USB && !writes);
        usb = false; list_calls = 0; option_usb = true;
        assert(accessibility_touch_wake_menu() == MENU_ATTACHED_USB && !writes && !firmware_enabled);
    } else if (!strcmp(scenario, "invalid-files")) {
        const char *invalid[] = {"garbage", "RBTOUCH-WAKE:1\nsingle:3\ndouble:0\ntriple:0\n",
            "RBTOUCH-WAKE:1\nsingle:01\ndouble:0\ntriple:0\n",
            "RBTOUCH-WAKE:1\nsingle:1\ndouble:0\ntriple:0\nx"};
        for (unsigned int index = 0; index < sizeof(invalid) / sizeof(*invalid); ++index) {
            wake_loaded = false; memset(wake_actions, 0, sizeof(wake_actions)); strcpy(persisted, invalid[index]);
            assert(!accessibility_touch_wake_enabled() && !writes);
        }
        for (failure = 6; failure <= 8; ++failure) {
            preferences(1, 1, 1); assert(!firmware_enabled && !wake_actions[0]);
        }
    } else assert(false);
    puts("PASS real touch wake");
    return 0;
}
'''
CASES = ("defaults", "combinations", "lit-pass-through", "invalid-contact", "cancellation",
         "late-press-is-consumed", "idle-timeout", "menu", "write-failures", "stale-temp", "usb", "invalid-files",
         "integration-factory", "integration-light", "integration-unlock", "integration-grid-and-curtain",
         "integration-physical-cancel", "integration-unlock-tail", "held-without-idle-polling", "integration-policy-edit")


def disable_core_dump():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class TouchWakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            raise unittest.SkipTest("C host compiler unavailable")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.area = project_materials_root(ROOT) / "r1-context-controls-20261017/touch-wake" / stamp
        cls.area.mkdir(parents=True)
        paths = (SOURCE, HEADER, Path(__file__), ROOT / "apps/action.c", ROOT / "apps/action.h",
                 ROOT / "firmware/drivers/touchscreen.c", ROOT / "firmware/drivers/button.c",
                 ROOT / "firmware/export/button.h", ROOT / "firmware/target/hosted/hiby/r1/button-target.h")
        cls.original = {path: path.read_bytes() for path in paths}
        source = re.sub(r'^\s*#include[^\n]*', '', SOURCE.read_text(encoding="utf-8"), flags=re.MULTILINE)
        header = re.sub(r'^\s*#include[^\n]*', '', HEADER.read_text(encoding="utf-8"), flags=re.MULTILINE)
        cls.header = header
        cls.compiler = compiler
        labels = sorted(set(re.findall(r'\bLANG_[A-Z0-9_]+', source)))
        constants = "\n".join(f"#define {label} {index + 1}" for index, label in enumerate(labels))
        action = (ROOT / "apps/action.c").read_text(encoding="utf-8")
        firmware = (ROOT / "firmware/drivers/touchscreen.c").read_text(encoding="utf-8")
        button_headers = (ROOT / "firmware/export/button.h").read_text(encoding="utf-8") + "\n" + (
            ROOT / "firmware/target/hosted/hiby/r1/button-target.h").read_text(encoding="utf-8")
        button_constants = "\n".join(re.findall(r'^#define BUTTON_[A-Z_]+\s+0x[0-9a-fA-F]+[^\n]*', button_headers, re.MULTILINE))
        action_header = (ROOT / "apps/action.h").read_text(encoding="utf-8")
        action_enums = action_header[action_header.index("enum {"):action_header.index("struct button_mapping {")]
        action_constants = "\n".join(re.findall(r'^#define SEL_ACTION_(?:ENABLED|NOTOUCH)\s+[^\n]*', action_header, re.MULTILINE))
        firmware_code = "\n".join(function(firmware, name) for name in (
            "touchscreen_set_wake_enabled", "touchscreen_wake_enabled", "touchscreen_set_wake_locked", "touchscreen_wake_filter_needed"))
        action_code = "\n".join(function(action, name) for name in (
            "has_flag", "action_handle_backlight", "action_update_touch_lock", "do_key_lock", "accessibility_handle_touch_wake"))
        harness = (constants + "\n" + button_constants + "\n" + action_enums + "\n" + action_constants + "\n" +
                   PREAMBLE + "\n" + header + "\n" + INTEGRATION_MOCKS + "\n" + firmware_code + "\n" +
                   source + "\n" + action_code + "\n" + INTEGRATION_CASES + "\n" + SUFFIX)
        fixture = cls.area / "fixture.c"
        fixture.write_text(harness, encoding="utf-8")
        cls.executables = {}
        cls.results = []
        cls.stub_results = []
        for target, flags in (("ordinary", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"])):
            executable = cls.area / (target + (".exe" if os.name == "nt" else ""))
            command = [*compiler, "-std=c99", "-O1", "-Wall", "-Wextra", "-Werror",
                       "-DHAVE_TOUCHSCREEN", "-DHAVE_ESPEAK", "-DHAVE_BACKLIGHT", *flags, str(fixture), "-o", str(executable)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (cls.area / (target + "-compile.json")).write_text(json.dumps(dict(command=command,
                exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2), encoding="utf-8")
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.executables[target] = executable

    @classmethod
    def tearDownClass(cls):
        unchanged = all(path.read_bytes() == data for path, data in cls.original.items())
        report = dict(passed=unchanged and len(cls.results) == len(CASES) * 2 and
                      len(cls.stub_results) == 4 and all(item["exit_code"] == 0 for item in cls.results) and
                      all(item["passed"] for item in cls.stub_results), cases=cls.results,
                      unsupported_capabilities=cls.stub_results,
                      source_unchanged=unchanged, physical_hardware_tested=False,
                      inputs={str(path): hashlib.sha256(data).hexdigest() for path, data in cls.original.items()})
        (cls.area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Touch wake evidence:", cls.area, flush=True)

    def test_real_module_scenarios(self):
        for target, executable in self.executables.items():
            for case in CASES:
                with self.subTest(target=target, case=case):
                    result = subprocess.run([executable, case], cwd=self.area, capture_output=True,
                                            text=True, timeout=5,
                                            preexec_fn=disable_core_dump if sys.platform == "linux" else None)
                    self.results.append(dict(target=target, case=case, exit_code=result.returncode,
                                             stdout=result.stdout, stderr=result.stderr))
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_capabilities_are_link_free_inert_stubs(self):
        variants = {
            "no-touch": "#define HAVE_ESPEAK\n",
            "no-espeak": "#define HAVE_TOUCHSCREEN\n",
            "hold": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n#define HAS_BUTTON_HOLD\n",
            "bootloader": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n#define BOOTLOADER\n",
        }
        for name, defines in variants.items():
            with self.subTest(variant=name):
                path = self.area / (name + "-stub.c")
                path.write_text("#include <stdbool.h>\n#include <stddef.h>\n" + defines + self.header + r'''
int main(void) {
    accessibility_touch_wake_cancel();
    return accessibility_touch_wake_enabled() || accessibility_touch_wake_timeout(-1) != -1 ||
        accessibility_touch_wake_menu() != 0 || accessibility_touch_wake_process(NULL, true, true, 0) != ACCESSIBILITY_TOUCH_WAKE_PASS;
}
''', encoding="utf-8")
                binary = path.with_suffix(".exe" if os.name == "nt" else ".bin")
                command = [*self.compiler, "-std=c99", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)]
                compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
                execution = subprocess.run([binary], cwd=self.area, capture_output=True, text=True, timeout=5) if compiled.returncode == 0 else None
                record = dict(variant=name, command=command, compile_exit=compiled.returncode,
                              compiler_output=compiled.stdout + compiled.stderr,
                              exit_code=execution.returncode if execution else None,
                              passed=compiled.returncode == 0 and execution.returncode == 0)
                self.stub_results.append(record)
                self.assertTrue(record["passed"], record)


@unittest.skipUnless(sys.platform == "linux", "Actual MIPS/MinGW header compilation runs under WSL")
class TouchWakeTargetHeadersTests(unittest.TestCase):
    def test_curtain_capability_is_available_before_other_public_headers(self):
        central = project_materials_root(ROOT)
        native = central / "toolchains/hiby-r1-20261010/prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        windows = shutil.which("x86_64-w64-mingw32-gcc")
        if not native.is_file() or not windows:
            self.skipTest("Actual MIPS/MinGW toolchains unavailable")
        area = central / "r1-context-controls-20261017/curtain-config" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8])
        area.mkdir(parents=True)
        source = area / "config-first.c"
        source.write_text('#include "config.h"\n'
            '#if defined(BOOTLOADER)\n#ifdef HAVE_SCREEN_CURTAIN\n#error CURTAIN_IN_BOOTLOADER\n#endif\n'
            '#else\n#ifndef HAVE_SCREEN_CURTAIN\n#error CURTAIN_CAPABILITY_MISSING_BEFORE_SETTINGS\n#endif\n#endif\n'
            'int curtain_config_guard(void) { return 0; }\n', encoding="ascii")
        config = ROOT / "firmware/export/config.h"
        original = config.read_bytes()
        records = []
        targets = (("native", str(native), central / "build-espeak-hibyr1", ["-DAPPLICATION"]),
                   ("windows", windows, central / "build-espeak-windows-hibyr1", ["-DSIMULATOR"]))
        for name, compiler, build, flags in targets:
            for bootloader in (False, True):
                command = [compiler, "-std=gnu11", "-Werror", "-DROCKBOX", "-DHIBY_R1", "-DMEMORYSIZE=16",
                           "-I", str(build), "-I", str(ROOT / "firmware/export"), *flags]
                if bootloader:
                    command.append("-DBOOTLOADER")
                command.extend(("-c", str(source), "-o", str(area / (name + str(bootloader) + ".o"))))
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                records.append(dict(target=name, bootloader=bootloader, command=command,
                                    exit_code=result.returncode, stderr=result.stderr, passed=result.returncode == 0))
        report = dict(passed=all(item["passed"] for item in records) and config.read_bytes() == original,
                      commands=records, config_sha256=hashlib.sha256(original).hexdigest(),
                      scope="Actual config/autoconf before any backlight/settings include; no fake generated headers",
                      hardware_tested=False)
        (area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        self.assertTrue(report["passed"], "Curtain feature depends on header include order; see " + str(area))

    def test_real_translation_unit_and_missing_header_mutant(self):
        central = project_materials_root(ROOT)
        native = central / "toolchains/hiby-r1-20261010/prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        windows = shutil.which("x86_64-w64-mingw32-gcc")
        if not native.is_file() or not windows or not shutil.which("perl"):
            self.skipTest("Actual MIPS/MinGW toolchains and Perl unavailable")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        area = central / "r1-context-controls-20261017/touch-wake-headers" / stamp
        area.mkdir(parents=True)
        language = area / "lang"
        language.mkdir()
        records = []

        def compile_source(command, name):
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            records.append(dict(name=name, command=command, exit_code=result.returncode,
                                stdout=result.stdout, stderr=result.stderr))
            return result

        english = ROOT / "apps/lang/english.lang"
        generated = compile_source(["perl", "-s", str(ROOT / "tools/genlang"), "-p=" + str(language),
            "-t=hibyr1:hibylinux:swcodec:lcd_bitmap:lcd_color:touchscreen:espeak",
            "-e=" + str(english), str(english)], "language")
        self.assertEqual(generated.returncode, 0, generated.stderr)
        directories = ("firmware", "firmware/export", "firmware/drivers", "firmware/include",
            "firmware/kernel/include", "firmware/target/hosted/hiby/r1", "firmware/target/hosted/hiby",
            "firmware/target/hosted", "apps", "apps/gui", "apps/recorder", "apps/radio",
            "lib/rbcodec", "lib/rbcodec/codecs", "lib/rbcodec/dsp", "lib/rbcodec/metadata",
            "lib/fixedpoint", "lib/skin_parser", "lib/utf8proc")
        common = ["-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wformat=2",
                  "-Wno-error=format-security", "-Wno-pointer-sign",
                  "-DROCKBOX", "-DMEMORYSIZE=16", "-DHIBY_R1", "-DTARGET_ID=124", "-I", str(language)]
        for directory in directories:
            common.extend(("-I", str(ROOT / directory)))
        targets = {
            "native": [str(native), *common, "-DAPPLICATION", "-D_GNU_SOURCE=1", "-march=mips32r2",
                       "-mhard-float", "-I", str(central / "build-espeak-hibyr1")],
            "windows": [windows, *common, "-DSIMULATOR", "-DDEBUG", "-I",
                str(central / "build-espeak-windows-hibyr1"), "-I", str(ROOT / "firmware/target/hosted/sdl"),
                "-I", str(ROOT / "uisimulator/sdl"), "-I",
                str(central / "toolchains/SDL2-2.32.10/x86_64-w64-mingw32/include/SDL2")],
        }
        original = SOURCE.read_bytes()
        mutant = area / "missing-settings-header.c"
        mutant.write_bytes(re.sub(rb'^#include "settings.h"\r?\n', b"", original, flags=re.MULTILINE))
        results = []
        for target, command in targets.items():
            for mutation, path in ((False, SOURCE), (True, mutant)):
                name = target + ("-mutant" if mutation else "-ordinary")
                result = compile_source([*command, "-c", str(path), "-o", str(area / (name + ".o"))], name)
                results.append(dict(name=name, passed=(result.returncode != 0 and "opt_items" in result.stderr)
                                    if mutation else result.returncode == 0))
            for headers in (("settings.h", "backlight.h"), ("backlight.h", "settings.h")):
                name = target + "-layout-" + headers[0].split(".")[0]
                path = area / (name + ".c")
                path.write_text(''.join('#include "' + header + '"\n' for header in headers) +
                    '_Static_assert(sizeof(((struct user_settings *)0)->accessibility_shortcut_curtain) == '
                    'sizeof(bool), "CURTAIN_SETTING_LAYOUT_MISSING");\n'
                    'int curtain_settings_guard(void) { return sizeof(struct user_settings); }\n', encoding="ascii")
                result = compile_source([*command, "-c", str(path), "-o", str(area / (name + ".o"))], name)
                results.append(dict(name=name, passed=result.returncode == 0))
        unchanged = SOURCE.read_bytes() == original
        report = dict(passed=unchanged and all(item["passed"] for item in results),
            source_unchanged=unchanged, source_sha256=hashlib.sha256(original).hexdigest(),
            target_results=results, commands=records, physical_hardware_tested=False,
            visible_nonfatal_diagnostic="Rockbox splash(ID2P(...)) uses an intentional virtual language pointer, not a printf literal; all other warnings remain fatal")
        (area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Touch wake target-header evidence:", area, flush=True)
        self.assertTrue(report["passed"], "Actual translation-unit/header regression failed; see " + str(area))


if __name__ == "__main__":
    unittest.main(verbosity=2)
