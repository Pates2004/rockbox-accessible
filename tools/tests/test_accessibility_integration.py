"""Compile real accessible-touch integration functions with bounded host mocks."""

from datetime import datetime, timezone
import hashlib
import json
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
INPUTS = (
    "apps/action.c", "apps/action.h", "apps/accessibility.h",
    "apps/accessibility_touch_wake.h",
    "apps/gui/bitmap/list.c", "apps/gui/list.c", "apps/gui/list.h",
    "apps/gui/viewport.c", "apps/tts_reader.c", "apps/settings.c",
    "apps/settings.h", "apps/talk.h",
    "apps/menus/settings_menu.c", "apps/SOURCES", "firmware/export/button.h",
    "firmware/export/touchscreen.h",
    "firmware/target/hosted/hiby/r1/button-target.h",
    "firmware/target/arm/as3525/sansa-clipplus/button-target.h",
    "firmware/target/arm/as3525/sansa-clipzip/button-target.h",
    "tools/tests/test_accessibility_integration.py",
)


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def without_includes(text):
    return re.sub(r'^\s*#include[^\n]*', '', text, flags=re.MULTILINE)


def balanced_definition(text, pattern):
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda match: re.sub(r'[^\n]', ' ', match.group()), text, flags=re.DOTALL)
    matches = list(re.finditer(pattern, masked, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"Expected one definition matching {pattern}: {len(matches)}")
    match = matches[0]
    cursor = masked.index('{', match.start()) + 1
    depth = 1
    while depth:
        depth += (masked[cursor] == '{') - (masked[cursor] == '}')
        cursor += 1
    return text[match.start():cursor] + "\n"


def function(text, name):
    return balanced_definition(text, r'^[ \t]*(?:static\s+)?(?:inline\s+)?'
                               r'(?:bool|int|void|unsigned(?:\s+int)?|const\s+char\s*\*)\s*\b' + re.escape(name)
                               + r'\s*\([^;{}]*\)\s*\{')


def structure(text, name):
    return balanced_definition(text, r'^struct\s+' + re.escape(name) + r'\s*\{') + ";\n"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise AssertionError(f"Expected one mutation site: {old!r}")
    return text.replace(old, new, 1)


COMMON = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#define INIT_ATTR
#define HZ 100
#define SYS_EVENT 0x40000000
#define SYS_BATTERY_UPDATE (SYS_EVENT | 3)
#define SYS_CHARGER_CONNECTED (SYS_EVENT | 11)
#define SYS_CHARGER_DISCONNECTED (SYS_EVENT | 12)
#define ACTION_FILTER_TICKS (HZ / 2)
#define REPEAT_WINDOW_TICKS (HZ / 4)
#define GUI_EVENT_ACTIONUPDATE 1
#define LANG_KEYLOCK_ON 1
#define LANG_KEYLOCK_OFF 2
#define ID2P(value) (value)
#define logf(...) ((void)0)
#define DEBUGF(...) ((void)0)
#define NB_SCREENS 1
#define FOR_NB_SCREENS(index) for (int index = 0; index < NB_SCREENS; ++index)
enum screen_type { SCREEN_MAIN };
struct viewport { int x, y, width, height, flags; };
struct gesture { int unused; };
struct gesture_event;
static int checks;
#define CHECK(expression) do { ++checks; if (!(expression)) { \
    fprintf(stderr, "check failed line %d: %s\n", __LINE__, #expression); \
    return 1; } } while (0)
"""


ACTION_MOCKS = r"""
#ifdef BUTTON_NEXT
#define TEST_PHYSICAL_BUTTON BUTTON_NEXT
#else
#define TEST_PHYSICAL_BUTTON BUTTON_RIGHT
#endif
static action_last_t action_last;
static long current_tick = 100;
static int queued_button;
static intptr_t queued_data;
static int physical_action = ACTION_STD_NEXT;
static int physical_calls;
static int reset_calls;
static int manager_calls;
static int poll_calls, last_poll_context, last_timeout;
static int legacy_clicks, custom_clicks, pending_launch_calls;
static bool custom_buttons, custom_poll, custom_repeat, custom_launch, queued_launch;
static bool queued_navigation;
static int navigation_cancel_calls;
static int custom_action;
static int ordinary_process_calls;
static int ordinary_reset_calls;
static int statusbar_calls;
static int manager_action = ACTION_TOUCHSCREEN;
static bool accessible;
static bool pending_timer;
static bool recover_curtain;
static int timer_action = ACTION_TOUCHSCREEN;
static struct touchevent manager_event;
long button_get_w_tmo(int timeout) { last_timeout = timeout; return queued_button; }
intptr_t button_get_data(void) { return queued_data; }
void button_clear_queue(void) {}
void button_clear_queue_preserve_events(void) {}
int button_queue_count(void) { return 0; }
void button_queue_post(long button, intptr_t data) { (void)button; (void)data; }
bool accessibility_screen_unlock_any_button(void) { return false; }
bool accessibility_screen_locked_buttons(void) { return false; }
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
bool accessibility_touch_wake_enabled(void) { return false; }
int accessibility_touch_wake_timeout(int timeout) { return timeout; }
void accessibility_touch_wake_cancel(void) { }
void touchscreen_set_wake_locked(bool locked) { (void)locked; }
bool touchscreen_wake_filter_needed(void) { return false; }
enum accessibility_touch_wake_result accessibility_touch_wake_process(
    const struct touchevent *event, bool locked, bool dark, int context)
{
    (void)event; (void)locked; (void)dark; (void)context;
    return ACCESSIBILITY_TOUCH_WAKE_PASS;
}
#endif
static int screen_autolock_seconds = -1;
int accessibility_screen_autolock_timeout(void) { return screen_autolock_seconds; }
void root_menu_cancel_navigation(void) { ++navigation_cancel_calls; queued_navigation = false; }
void button_enable_touch(bool enabled) { (void)enabled; }
void send_event(int event, void *data) { (void)event; (void)data; }
void keyclick_click(bool enabled, int action) { (void)enabled; (void)action; ++legacy_clicks; }
void keyclick_click_physical(int action, bool repeat) { (void)action; custom_repeat = repeat; ++custom_clicks; }
static bool accessibility_forced_lock;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
static bool accessibility_custom_click;
#endif
void skin_request_update_locked(bool locked) { (void)locked; }
void splash(int ticks, int label) { (void)ticks; (void)label; }
void splashf_silent(int ticks, int label, ...) { (void)ticks; (void)label; }
void accessibility_screen_lock_changed(bool locked) { (void)locked; }
static void button_flip_horizontally(int context, int *button)
{ (void)context; (void)button; }
static void action_code_lookup(action_last_t *last, action_cur_t *cur)
{ (void)last; ++physical_calls; cur->action = physical_action; }
int sb_touch_to_button(int context)
{ (void)context; ++statusbar_calls; return ACTION_STD_OK; }
#ifdef HAVE_TOUCHSCREEN
void gesture_process(struct gesture *gesture, const struct touchevent *event)
{ (void)gesture; (void)event; ++ordinary_process_calls; }
void gesture_reset(struct gesture *gesture)
{ (void)gesture; ++ordinary_reset_calls; }
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
bool accessibility_enabled(void) { return accessible; }
bool accessibility_curtain_escape(int button)
{ (void)button; return recover_curtain; }
int accessibility_adjust_timeout(int requested_timeout)
{ return accessible && pending_timer && (requested_timeout < 0 || requested_timeout > 10) ? 10 : requested_timeout; }
void accessibility_reset(void) { ++reset_calls; pending_timer = false; }
void accessibility_cancel_touch(void) { ++reset_calls; pending_timer = false; }
bool accessibility_handle_button(int button, int context, bool locked, int *action)
{
    (void)context;
    *action = ACTION_UNKNOWN;
    if (!custom_buttons || (button == BUTTON_NONE && !custom_poll)) return false;
    if ((button & BUTTON_REL) || custom_poll)
    {
        if (!locked || custom_action == ACTION_STD_KEYLOCK)
        {
            *action = custom_action;
            if (custom_launch) queued_launch = true;
        }
        custom_poll = false;
    }
    return true;
}
bool accessibility_button_is_repeat(void) { return custom_repeat; }
int accessibility_process_pending(int action, int context)
{
    (void)context;
    if (queued_navigation && (action == ACTION_NONE || action == ACTION_REDRAW))
        return ACTION_STD_MENU;
    if (!queued_launch || (action != ACTION_NONE && action != ACTION_REDRAW)) return 0;
    queued_launch = false; ++pending_launch_calls; return ACTION_REDRAW;
}
int accessibility_handle_touch(const struct touchevent *event, int context)
{
    if (!event)
    {
        ++poll_calls; last_poll_context = context;
        if (!pending_timer) return ACTION_NONE;
        pending_timer = false; return timer_action;
    }
    ++manager_calls; manager_event = *event; return manager_action;
}
#endif
static void reset_action(bool enabled)
{
    memset(&action_last, 0, sizeof(action_last));
    action_last.button = BUTTON_REL;
    action_last.context = CONTEXT_STD | ALLOW_SOFTLOCK;
    action_last.sl_filter_tick = -1;
    accessibility_forced_lock = false;
    custom_buttons = custom_poll = custom_repeat = custom_launch = queued_launch = false;
    queued_navigation = false;
    navigation_cancel_calls = 0;
    custom_action = ACTION_STD_OK;
    legacy_clicks = custom_clicks = pending_launch_calls = 0;
    physical_calls = manager_calls = reset_calls = 0;
    ordinary_process_calls = ordinary_reset_calls = statusbar_calls = 0;
    poll_calls = 0; last_poll_context = -1; last_timeout = 0; pending_timer = false;
    timer_action = ACTION_TOUCHSCREEN;
    queued_data = ((intptr_t)40 << 16) | 55;
    queued_button = BUTTON_NONE;
    manager_action = ACTION_TOUCHSCREEN;
    accessible = enabled;
    recover_curtain = false;
    screen_autolock_seconds = -1;
    memset(&manager_event, 0, sizeof(manager_event));
}
static int event(int button, int context)
{
    queued_button = button;
    ++current_tick;
    return get_action(context, 0);
}
static void print_action_mock_snapshot(void)
{
    printf("{\"last_poll_context\":%d,\"legacy_clicks\":%d,"
           "\"ordinary_process_calls\":%d,\"poll_calls\":%d,"
           "\"custom_buttons\":%d,\"custom_action\":%d,\"manager_action\":%d,"
           "\"accessible\":%d,\"pending_timer\":%d,\"recover_curtain\":%d,"
           "\"timer_action\":%d,\"accessibility_forced_lock\":%d,"
           "\"physical_calls\":%d,\"queued_navigation\":%d,\"navigation_cancel_calls\":%d}",
           last_poll_context, legacy_clicks, ordinary_process_calls, poll_calls,
           custom_buttons, custom_action, manager_action, accessible, pending_timer,
           recover_curtain, timer_action, accessibility_forced_lock, physical_calls,
           queued_navigation, navigation_cancel_calls);
}
"""


ACTION_CASES = r"""
static int dispatch_cases(void)
{
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_action(true);
    CHECK(event(BUTTON_NONE, context) == BUTTON_NONE);
    CHECK(physical_calls == 0);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    int resets = reset_calls;
    CHECK(event(BUTTON_NONE, context) == BUTTON_NONE);
    CHECK(reset_calls == resets);
    CHECK(event(BUTTON_NONE, CONTEXT_LIST | ALLOW_SOFTLOCK) == BUTTON_NONE);
    CHECK(reset_calls == resets + 1);
    CHECK(event(SYS_BATTERY_UPDATE, CONTEXT_LIST | ALLOW_SOFTLOCK) == SYS_BATTERY_UPDATE);
    CHECK(reset_calls == resets + 1);
    CHECK(event(SYS_EVENT | 4, CONTEXT_LIST | ALLOW_SOFTLOCK) == (SYS_EVENT | 4));
    CHECK(reset_calls == resets + 2);
    CHECK(event(BUTTON_REDRAW, CONTEXT_LIST | ALLOW_SOFTLOCK) == ACTION_REDRAW);
    CHECK(reset_calls == resets + 2);
    action_last.button = BUTTON_REL;
    CHECK(event(BUTTON_TOUCHSCREEN, context) == ACTION_TOUCHSCREEN);
    CHECK(manager_calls == 1 && physical_calls == 0 && statusbar_calls == 0);
    CHECK(manager_event.type == TOUCHEVENT_PRESS);
    CHECK(manager_event.x == 40 && manager_event.y == 55);
    CHECK(ordinary_process_calls == 0 && ordinary_reset_calls == 1);
    manager_action = ACTION_STD_NEXT;
    queued_data = ((intptr_t)99 << 16) | 88;
    CHECK(event(BUTTON_TOUCHSCREEN | BUTTON_REPEAT, context) == ACTION_STD_NEXT);
    CHECK(manager_event.type == TOUCHEVENT_CONTACT && manager_event.x == 99);
    queued_data = ((intptr_t)3 << 16) | 4;
    CHECK(event(BUTTON_TOUCHSCREEN | BUTTON_REL, context) == ACTION_STD_NEXT);
    CHECK(manager_event.type == TOUCHEVENT_RELEASE && manager_event.x == 99);
    CHECK(physical_calls == 0 && statusbar_calls == 0 && manager_calls == 3);
    resets = reset_calls;
    pending_timer = true;
    CHECK(event(TEST_PHYSICAL_BUTTON, context) == ACTION_STD_NEXT);
    CHECK(physical_calls == 1 && reset_calls == resets + 1 && !pending_timer);
    action_last.wait_for_release = true;
    CHECK(event(BUTTON_TOUCHSCREEN, context) == ACTION_NONE);
    CHECK(manager_calls == 3);
    CHECK(event(BUTTON_TOUCHSCREEN | BUTTON_REL, context) == ACTION_NONE);
    CHECK(!action_last.wait_for_release && manager_calls == 3);
#else
    CHECK(event(TEST_PHYSICAL_BUTTON, context) == ACTION_STD_NEXT);
    CHECK(physical_calls == 1 && manager_calls == 0 && reset_calls == 0);
    (void)manager_action;
    (void)manager_event;
#endif
    return 0;
}
static int lock_cases(void)
{
    reset_action(true);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    manager_action = ACTION_STD_OK;
    action_last.keys_locked = true;
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD | ALLOW_SOFTLOCK) == ACTION_NONE);
    CHECK(manager_calls == 0 && physical_calls == 0);
    CHECK(event(BUTTON_TOUCHSCREEN | BUTTON_REL, CONTEXT_STD | ALLOW_SOFTLOCK) == ACTION_NONE);
    CHECK(manager_calls == 0);
    action_last.softlock_mask = SEL_ACTION_ENABLED | SEL_ACTION_VOL | SEL_ACTION_NONOTIFY;
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD | ALLOW_SOFTLOCK) == ACTION_NONE);
    CHECK(manager_calls == 0 && physical_calls == 0);
    action_last.keys_locked = false;
    CHECK(event(BUTTON_TOUCHSCREEN | BUTTON_REPEAT, CONTEXT_STD | ALLOW_SOFTLOCK) == ACTION_STD_OK);
    CHECK(manager_calls == 1);
    action_last.button = BUTTON_REL;
    action_last.keys_locked = true;
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD) == ACTION_NONE);
    CHECK(manager_calls == 1);
#endif
    return 0;
}
static int legacy_cases(void)
{
    reset_action(false);
#ifdef HAVE_TOUCHSCREEN
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD | ALLOW_SOFTLOCK) == ACTION_STD_OK);
    CHECK(ordinary_process_calls == 1 && ordinary_reset_calls == 0);
    CHECK(manager_calls == 0 && statusbar_calls == 1);
    struct touchevent result;
    memset(&result, 0xaa, sizeof(result));
    CHECK(action_get_touch_event(&result) == TOUCHEVENT_PRESS);
    CHECK(result.x == 40 && result.y == 55);
    CHECK(action_get_touch_event(NULL) == TOUCHEVENT_PRESS);
#ifdef HAVE_ESPEAK
    accessible = true;
    memset(&result, 0xaa, sizeof(result));
    CHECK(action_get_touch_event(&result) == TOUCHEVENT_NONE);
    struct touchevent empty = {0};
    CHECK(memcmp(&result, &empty, sizeof(result)) == 0);
    CHECK(action_get_touch_event(NULL) == TOUCHEVENT_NONE);
#endif
#else
    CHECK(manager_calls == 0 && ordinary_process_calls == 0 && statusbar_calls == 0);
#endif
    return 0;
}
static int poll_cases(void)
{
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_action(false);
    CHECK(event(BUTTON_NONE, context) == ACTION_NONE);
    CHECK(get_action(context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && poll_calls == 0);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    accessible = true;
    CHECK(get_action(context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && poll_calls == 1);
    pending_timer = true;
    CHECK(get_action(context, TIMEOUT_BLOCK) == ACTION_TOUCHSCREEN);
    CHECK(last_timeout == 10 && poll_calls == 2 && last_poll_context == CONTEXT_STD);
    CHECK(statusbar_calls == 0 && !pending_timer);
    CHECK(get_action(context, 75) == ACTION_NONE && last_timeout == 75);
    pending_timer = true;
    CHECK(get_action(context, 0) == ACTION_TOUCHSCREEN && last_timeout == 0);
    pending_timer = true; action_last.keys_locked = true;
    int polls = poll_calls;
    int resets = reset_calls;
    CHECK(get_action(context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(poll_calls == polls && reset_calls == resets + 1 && !pending_timer);
    action_last.keys_locked = false;
    pending_timer = true; queued_button = SYS_EVENT | 8;
    CHECK(get_action(context, TIMEOUT_BLOCK) == (SYS_EVENT | 8));
    CHECK(poll_calls == polls && !pending_timer);
#else
    (void)last_poll_context;
    (void)timer_action;
#endif
    return 0;
}
static int physical_accessibility_cases(void)
{
    reset_action(true);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    custom_buttons = true;
    CHECK(event(TEST_PHYSICAL_BUTTON, CONTEXT_STD) == ACTION_NONE);
    CHECK(legacy_clicks == 0 && custom_clicks == 0);
    CHECK(event(TEST_PHYSICAL_BUTTON | BUTTON_REL, CONTEXT_STD) == ACTION_STD_OK);
    CHECK(legacy_clicks == 0 && custom_clicks == 1);
    custom_poll = true; custom_action = ACTION_STD_NEXT;
    CHECK(event(BUTTON_NONE, CONTEXT_STD) == ACTION_STD_NEXT);
    CHECK(legacy_clicks == 0 && custom_clicks == 2);
    custom_repeat = true; custom_poll = true;
    CHECK(event(BUTTON_NONE, CONTEXT_STD) == ACTION_STD_NEXT);
    CHECK(custom_clicks == 3 && custom_repeat);
    action_last.wait_for_release = true; custom_poll = true;
    CHECK(event(BUTTON_NONE, CONTEXT_STD) == ACTION_NONE);
    CHECK(custom_clicks == 3);
    action_last.wait_for_release = false; custom_poll = false;
    custom_action = ACTION_STD_KEYLOCK;
    CHECK(event(TEST_PHYSICAL_BUTTON, CONTEXT_STD) == ACTION_NONE);
    CHECK(event(TEST_PHYSICAL_BUTTON | BUTTON_REL, CONTEXT_STD) == ACTION_REDRAW);
    CHECK(action_last.keys_locked && accessibility_forced_lock);
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD) == ACTION_NONE);
    CHECK(manager_calls == 0);
    action_last.button = BUTTON_REL;
    CHECK(event(TEST_PHYSICAL_BUTTON, CONTEXT_STD) == ACTION_NONE);
    CHECK(event(TEST_PHYSICAL_BUTTON | BUTTON_REL, CONTEXT_STD) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && !accessibility_forced_lock);
    custom_action = ACTION_NONE; custom_launch = true;
    CHECK(event(TEST_PHYSICAL_BUTTON, CONTEXT_STD) == ACTION_NONE);
    CHECK(event(TEST_PHYSICAL_BUTTON | BUTTON_REL, CONTEXT_STD) == ACTION_REDRAW);
    CHECK(pending_launch_calls == 1 && !queued_launch);
    queued_button = TEST_PHYSICAL_BUTTON;
    CHECK(get_custom_action(CONTEXT_STD, 0, NULL) == ACTION_NONE);
    queued_button = TEST_PHYSICAL_BUTTON | BUTTON_REL;
    CHECK(get_custom_action(CONTEXT_STD, 0, NULL) == ACTION_REDRAW);
    CHECK(pending_launch_calls == 2 && !queued_launch);
    CHECK(legacy_clicks == 0);
    reset_action(true);
    action_last.keys_locked = true;
    custom_buttons = true;
    custom_action = ACTION_STD_KEYLOCK;
    recover_curtain = true;
    CHECK(event(TEST_PHYSICAL_BUTTON, CONTEXT_STD) == ACTION_NONE);
    CHECK(action_last.keys_locked && physical_calls == 0 && custom_clicks == 0);
    CHECK(event(TEST_PHYSICAL_BUTTON | BUTTON_REL, CONTEXT_STD) == ACTION_NONE);
    CHECK(action_last.keys_locked && physical_calls == 0 && custom_clicks == 0);
    recover_curtain = false;
#endif
    return 0;
}
static int gesture_lock_cases(void)
{
    reset_action(true);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    manager_action = ACTION_STD_KEYLOCK;
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD) == ACTION_REDRAW);
    CHECK(action_last.keys_locked && accessibility_forced_lock);
    CHECK(event(BUTTON_TOUCHSCREEN | BUTTON_REL, CONTEXT_STD) == ACTION_NONE);
    CHECK(manager_calls == 1 && action_last.keys_locked);
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD) == ACTION_NONE);
    CHECK(action_last.keys_locked && manager_calls == 1);
    action_last.button = BUTTON_REL;
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(event(TEST_PHYSICAL_BUTTON, CONTEXT_STD) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && !accessibility_forced_lock);
    physical_action = ACTION_STD_NEXT;
    reset_action(true);
    pending_timer = true;
    timer_action = ACTION_STD_KEYLOCK;
    CHECK(event(BUTTON_NONE, CONTEXT_STD) == ACTION_REDRAW);
    CHECK(action_last.keys_locked && accessibility_forced_lock);
    CHECK(action_last.unlock_combo != BUTTON_NONE);
    CHECK(event(BUTTON_NONE, CONTEXT_STD) == ACTION_NONE);
    CHECK(action_last.keys_locked);
    CHECK(event(BUTTON_TOUCHSCREEN, CONTEXT_STD) == ACTION_NONE);
    CHECK(action_last.keys_locked && manager_calls == 0);
    action_last.button = BUTTON_REL;
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(event(TEST_PHYSICAL_BUTTON, CONTEXT_STD) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && !accessibility_forced_lock);
    physical_action = ACTION_STD_NEXT;
#endif
    return 0;
}
int main(int argc, char **argv)
{
    int result = argc != 2 ? 2 : !strcmp(argv[1], "dispatch") ? dispatch_cases() :
        !strcmp(argv[1], "lock") ? lock_cases() : !strcmp(argv[1], "legacy") ? legacy_cases() :
        !strcmp(argv[1], "poll") ? poll_cases() :
        !strcmp(argv[1], "physical-accessibility") ? physical_accessibility_cases() :
        !strcmp(argv[1], "gesture-lock") ? gesture_lock_cases() : 2;
    if (!result) {
        printf("{\"checks\":%d,\"mock_state\":", checks);
        print_action_mock_snapshot();
        printf("}\n");
    }
    return result;
}
"""


LIST_MOCKS = r"""
void accessibility_explore_feedback(const void *owner, int target, bool occupied)
{ (void)owner; (void)target; (void)occupied; }
#define LANG_SCROLL_BAR 2
#define SCROLLBAR_OFF 0
#define SCROLLBAR_LEFT 1
#define SCROLLBAR_RIGHT 2
#define SCROLLBAR_WIDTH 4
#define VP_IS_RTL(viewport) ((viewport)->flags & 1)
#define LANG_ACCESSIBILITY_EMPTY 1001
#define OUTSIDE 0
#define TITLE_TEXT (1 << 0)
#define TITLE_ICON (1 << 1)
#define SCROLLBAR (1 << 2)
#define LIST_TEXT (1 << 3)
#define LIST_ICON (1 << 4)
#define TITLE (TITLE_TEXT | TITLE_ICON)
#define LIST (LIST_TEXT | LIST_ICON)
typedef const char *list_get_name(int item, void *data, char *buffer, size_t size);
typedef int list_get_icon(int item, void *data);
typedef int list_speak_item(int item, void *data);
typedef void list_draw_item(void *info);
enum themable_icons { Icon_NOICON = -1, Icon_Harness = 0 };
"""


LIST_RUNTIME = r"""
static const unsigned char *list_language_string(ptrdiff_t identifier)
{ return (const unsigned char *)(identifier == 7 ? "Title" : "Unexpected title"); }
static struct viewport list_text[NB_SCREENS], title_text[NB_SCREENS], parent[NB_SCREENS];
static struct { int unused; } screens[NB_SCREENS];
static int explore_x, explore_y;
static bool point_ready, point_force, skin_enabled;
static int skin_line, skin_x, skin_y;
static int item_calls, title_calls, empty_calls, scrollbar_calls, stop_calls, select_calls;
static const void *target;
static int target_calls;
static bool accessible = true;
static int legacy_touch_calls;
static bool empty_speech_enabled;
bool accessibility_enabled(void) { return accessible; }
bool accessibility_explore_point(int *point_x, int *point_y, bool *force)
{
    *point_x = explore_x; *point_y = explore_y; *force = point_force;
    bool result = point_ready; point_ready = false; return result;
}
void accessibility_set_target(const void *value) { target = value; ++target_calls; }
void _gui_synclist_stop_kinetic_scrolling(struct gui_synclist *list)
{ ++stop_calls; list->scroll_mode = 0; }
bool skinlist_get_item(void *screen, struct gui_synclist *list,
                       int point_x, int point_y, int *line)
{ (void)screen; (void)list; skin_x = point_x; skin_y = point_y; *line = skin_line; return skin_enabled; }
int list_icon_width(enum screen_type screen) { (void)screen; return 8; }
void gui_synclist_select_item(struct gui_synclist *list, int item)
{ ++select_calls; list->selected_item = item; }
void gui_synclist_speak_item(struct gui_synclist *list) { (void)list; ++item_calls; }
int talk_spell(const char *text, bool enqueue)
{ (void)enqueue; if (!strcmp(text, "Title")) ++title_calls; return 0; }
int talk_id(int language, bool enqueue)
{
    (void)enqueue;
    if (language == LANG_ACCESSIBILITY_EMPTY) ++empty_calls;
    if (language == LANG_SCROLL_BAR) ++scrollbar_calls;
    return 0;
}
void accessibility_speak_empty(void)
{
    if (empty_speech_enabled)
        talk_id(LANG_ACCESSIBILITY_EMPTY, false);
}
void gui_synclist_init_display_settings(struct gui_synclist *list) { (void)list; }
void list_init_viewports(struct gui_synclist *list) { (void)list; }
void list_init_item_height(struct gui_synclist *list, int screen)
{ list->line_height[screen] = 10; }
void skinlist_set_cfg(int screen, void *config) { (void)screen; (void)config; }
"""


LIST_CASES = r"""
static void setup_list(struct gui_synclist *list)
{
    memset(list, 0, sizeof(*list));
    parent[0] = (struct viewport){20, 30, 120, 100, 0};
    title_text[0] = (struct viewport){30, 30, 110, 10, 0};
    list_text[0] = (struct viewport){30, 40, 110, 90, 0};
    list->parent[0] = parent;
    list->line_height[0] = 10;
    list->nb_items = 10;
    list->selected_size = 1;
    list->title = "Title";
    list->title_icon = Icon_NOICON;
    skin_enabled = false;
    item_calls = title_calls = empty_calls = scrollbar_calls = stop_calls = select_calls = 0;
    empty_speech_enabled = false;
}
static unsigned explore(struct gui_synclist *list, int point_x, int point_y, bool force)
{
    explore_x = point_x; explore_y = point_y;
    point_ready = true; point_force = force;
    return list_accessibility_explore(list);
}
static int focus_cases(void)
{
    struct gui_synclist list;
    setup_list(&list);
    CHECK(list_accessibility_explore(&list) == ACTION_NONE && stop_calls == 0);
    CHECK(explore(&list, 35, 55, true) == ACTION_REDRAW);
    CHECK(list.selected_item == 1 && item_calls == 1 && select_calls == 1);
    CHECK(explore(&list, 80, 59, false) == ACTION_NONE && item_calls == 1);
    CHECK(explore(&list, 80, 59, true) == ACTION_REDRAW && item_calls == 2);
    CHECK(explore(&list, 80, 65, false) == ACTION_REDRAW);
    CHECK(list.selected_item == 2 && item_calls == 3);
    CHECK(explore(&list, 35, 35, false) == ACTION_REDRAW);
    CHECK(title_calls == 1 && item_calls == 3 && list.selected_item == 2);
    CHECK(explore(&list, 60, 35, false) == ACTION_NONE && title_calls == 1);
    list.show_icons = true; list.title_icon = Icon_Harness;
    CHECK(explore(&list, 23, 35, true) == ACTION_REDRAW && title_calls == 2);
    list.title = (const char *)(VIRT_PTR + 7);
    CHECK(explore(&list, 23, 35, true) == ACTION_REDRAW && title_calls == 3);
    CHECK(explore(&list, 23, 55, true) == ACTION_REDRAW && list.selected_item == 1);
    return 0;
}
static int geometry_cases(void)
{
    struct gui_synclist list;
    setup_list(&list);
    empty_speech_enabled = true;
    CHECK(explore(&list, 140, 55, true) == ACTION_REDRAW);
    CHECK(empty_calls == 1 && item_calls == 0 && select_calls == 0);
    CHECK(explore(&list, -1, 55, true) == ACTION_REDRAW && empty_calls == 2);
    CHECK(explore(&list, 35, -1, true) == ACTION_REDRAW && empty_calls == 3);
    CHECK(explore(&list, 35, 130, true) == ACTION_REDRAW && empty_calls == 4);
    list.y_pos = -20;
    CHECK(explore(&list, 35, 45, true) == ACTION_REDRAW && empty_calls == 5);
    list.y_pos = 35;
    list.start_item[0] = 3;
    CHECK(explore(&list, 35, 46, true) == ACTION_REDRAW && list.selected_item == 4);
    list.y_pos = 100;
    CHECK(explore(&list, 35, 40, true) == ACTION_REDRAW && empty_calls == 6);
    list.nb_items = 0;
    list.y_pos = 0;
    CHECK(explore(&list, 35, 40, true) == ACTION_REDRAW && empty_calls == 7);
    list.nb_items = 10; list.line_height[0] = 0;
    CHECK(explore(&list, 35, 40, true) == ACTION_REDRAW && empty_calls == 8);
    list.line_height[0] = -10;
    CHECK(explore(&list, 35, 40, true) == ACTION_REDRAW && empty_calls == 9);
    list.line_height[0] = 10; list.scrollbar = SCROLLBAR_LEFT;
    apply_draw_scrollbar(&list);
    CHECK(explore(&list, 30, 55, true) == ACTION_REDRAW && empty_calls == 9 && scrollbar_calls == 1);
    return 0;
}
static int skin_group_cases(void)
{
    struct gui_synclist list;
    setup_list(&list);
    empty_speech_enabled = true;
    skin_enabled = true; skin_line = 2; list.start_item[0] = 4;
    CHECK(explore(&list, 35, 55, true) == ACTION_REDRAW && list.selected_item == 6);
    CHECK(skin_x == 15 && skin_y == 25);
    list.selected_size = 3;
    CHECK(explore(&list, 35, 55, true) == ACTION_REDRAW && list.selected_item == 6);
    skin_line = 1;
    CHECK(explore(&list, 35, 55, true) == ACTION_REDRAW && list.selected_item == 3);
    skin_line = -10;
    CHECK(explore(&list, 35, 55, true) == ACTION_REDRAW && empty_calls == 1);
    skin_line = 8;
    CHECK(explore(&list, 35, 55, true) == ACTION_REDRAW && empty_calls == 2);
    skin_enabled = false; list.y_pos = 50;
    CHECK(explore(&list, 35, 56, true) == ACTION_REDRAW && list.selected_item == 6);
    return 0;
}
static int right_scrollbar_cases(void)
{
    struct gui_synclist list;
    setup_list(&list);
    empty_speech_enabled = true;
    list.scrollbar = SCROLLBAR_RIGHT;
    struct viewport scrollbar = apply_draw_scrollbar(&list);
    CHECK(list_text[0].x == 30 && list_text[0].width == 106);
    CHECK(scrollbar.x == 136 && scrollbar.width == SCROLLBAR_WIDTH);
    CHECK(explore(&list, 135, 55, true) == ACTION_REDRAW);
    CHECK(item_calls == 1 && select_calls == 1 && list.selected_item == 1);
    for (int point_x = 136; point_x < 140; ++point_x)
    {
        CHECK(explore(&list, point_x, 55, true) == ACTION_REDRAW);
        CHECK(scrollbar_calls == point_x - 135 && empty_calls == 0 && item_calls == 1 && select_calls == 1);
    }
    CHECK(explore(&list, 140, 55, true) == ACTION_REDRAW);
    CHECK(empty_calls == 1 && scrollbar_calls == 4 && item_calls == 1 && select_calls == 1);
    return 0;
}
static int left_scrollbar_cases(void)
{
    struct gui_synclist list;
    setup_list(&list);
    empty_speech_enabled = true;
    list.scrollbar = SCROLLBAR_LEFT;
    struct viewport scrollbar = apply_draw_scrollbar(&list);
    CHECK(list_text[0].x == 34 && list_text[0].width == 106);
    CHECK(scrollbar.x == 30 && scrollbar.width == SCROLLBAR_WIDTH);
    CHECK(explore(&list, 29, 55, true) == ACTION_REDRAW);
    CHECK(item_calls == 1 && select_calls == 1);
    for (int point_x = 30; point_x < 34; ++point_x)
    {
        CHECK(explore(&list, point_x, 55, true) == ACTION_REDRAW);
        CHECK(scrollbar_calls == point_x - 29 && empty_calls == 0 && item_calls == 1 && select_calls == 1);
    }
    CHECK(explore(&list, 34, 55, true) == ACTION_REDRAW);
    CHECK(item_calls == 2 && select_calls == 2 && empty_calls == 0 && scrollbar_calls == 4);
    CHECK(explore(&list, 19, 55, true) == ACTION_REDRAW);
    CHECK(empty_calls == 1 && scrollbar_calls == 4 && item_calls == 2);
    return 0;
}
static int route_cases(void)
{
    struct gui_synclist list;
    setup_list(&list);
    explore_x = 35; explore_y = 55; point_ready = true; point_force = true;
    CHECK(gui_synclist_do_touchscreen(&list) == ACTION_REDRAW);
    CHECK(item_calls == 1 && legacy_touch_calls == 0);
    accessible = false;
    CHECK(gui_synclist_do_touchscreen(&list) == ACTION_STD_OK);
    CHECK(legacy_touch_calls == 1 && item_calls == 1);
    return 0;
}
static int target_cases(void)
{
    struct gui_synclist list;
    memset(&list, 0xaa, sizeof(list));
    gui_synclist_init(&list, NULL, NULL, false, 1, parent);
    CHECK(target == &list && target_calls == 1);
    CHECK(list.nb_items == 0 && list.selected_item == 0);
    CHECK(list.y_pos == 0 && list.selected_size == 1 && list.title == NULL);
    CHECK(list.line_height[0] == 10 && list.parent[0] == parent);
    CHECK(list.position_source == LIST_POSITION_INTERFACE);
    gui_synclist_init(&list, NULL, NULL, false, 1, parent);
    CHECK(target == &list && target_calls == 2);
    return 0;
}
static int empty_mode_cases(void)
{
    struct gui_synclist list;
    setup_list(&list);
    CHECK(explore(&list, 140, 55, true) == ACTION_REDRAW);
    CHECK(empty_calls == 0 && item_calls == 0 && select_calls == 0);
    CHECK(explore(&list, 35, 55, true) == ACTION_REDRAW);
    CHECK(item_calls == 1 && select_calls == 1 && list.selected_item == 1);
    empty_speech_enabled = true;
    CHECK(explore(&list, 140, 55, true) == ACTION_REDRAW && empty_calls == 1);
    CHECK(explore(&list, 141, 56, false) == ACTION_NONE && empty_calls == 1);
    empty_speech_enabled = false;
    CHECK(explore(&list, 140, 55, true) == ACTION_REDRAW && empty_calls == 1);
    CHECK(explore(&list, 35, 35, true) == ACTION_REDRAW && title_calls == 1);
    CHECK(item_calls == 1 && select_calls == 1);
    return 0;
}
int main(int argc, char **argv)
{
    int result = argc != 2 ? 2 : !strcmp(argv[1], "focus") ? focus_cases() :
        !strcmp(argv[1], "empty-mode") ? empty_mode_cases() :
        !strcmp(argv[1], "geometry") ? geometry_cases() :
        !strcmp(argv[1], "skin-group") ? skin_group_cases() :
        !strcmp(argv[1], "target") ? target_cases() :
        !strcmp(argv[1], "right-scrollbar") ? right_scrollbar_cases() :
        !strcmp(argv[1], "left-scrollbar") ? left_scrollbar_cases() :
        !strcmp(argv[1], "route") ? route_cases() : 2;
    if (!result) printf("{\"checks\":%d}\n", checks);
    return result;
}
"""


READER_MOCKS = r"""
void accessibility_explore_feedback(const void *owner, int target, bool occupied)
{ (void)owner; (void)target; (void)occupied; }
static bool empty_speech_enabled;
bool accessibility_empty_speech_enabled(void) { return empty_speech_enabled; }
#define PCM_MIXER_CHAN_VOICE 1
#define CHANNEL_STOPPED 0
#define LANG_TTS_READING 1
#define LANG_TTS_PAUSED 2
#define LANG_TTS_FINISHED 3
#define LANG_TTS_ERROR 4
#define LANG_ACCESSIBILITY_EMPTY 5
#define LANG_TTS_UNIT_CHARACTER 6
#define LANG_TTS_UNIT_WORD 7
#define LANG_TTS_UNIT_LINE 8
#define LANG_TTS_UNIT_PARAGRAPH 9
#define LANG_TTS_UNIT_PAGE 10
static struct { int tts_reader_unit; } global_settings = { READER_WORD };
static const char *file_text = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
static size_t tracked_position;
static bool engine_busy, mixer_busy, available = true;
static bool load_failure;
static int speech_result, fail_calls, load_calls, pause_calls, stop_calls, speech_calls;
static int tracked_calls;
static int music_position = 431, music_volume = 77, music_state = 3;
static char last_speech[256], trace[128];
static size_t trace_length;
static int explore_x, explore_y;
static bool point_ready, point_force;
static const char *last_error = "";
typedef int32_t utf8proc_int32_t;
typedef uint8_t utf8proc_uint8_t;
static struct viewport *display_viewport;
static int character_height = 10;
static int drawn_rows;
static char drawn_text[8][256];
static void screen_set_viewport(struct viewport *viewport) { display_viewport = viewport; }
static void screen_scroll_stop(struct viewport *viewport) { (void)viewport; }
static void screen_clear(void) { drawn_rows = 0; memset(drawn_text, 0, sizeof(drawn_text)); }
static int screen_getheight(void) { return display_viewport->height; }
static int screen_getcharheight(void) { return character_height; }
static void screen_puts(int column, int row, const unsigned char *text)
{
    (void)column;
    if (row >= 0 && row < 8)
    { snprintf(drawn_text[row], sizeof(drawn_text[row]), "%s", text); ++drawn_rows; }
}
static void screen_update(void) {}
struct screen {
    void (*set_viewport)(struct viewport *);
    void (*scroll_stop_viewport)(struct viewport *);
    void (*clear_viewport)(void);
    int (*getheight)(void);
    int (*getcharheight)(void);
    void (*puts_scroll)(int, int, const unsigned char *);
    void (*update_viewport)(void);
};
static struct screen screens[NB_SCREENS] = {{screen_set_viewport, screen_scroll_stop,
    screen_clear, screen_getheight, screen_getcharheight, screen_puts, screen_update}};
static int utf8proc_iterate(const utf8proc_uint8_t *text, size_t length,
                            utf8proc_int32_t *codepoint)
{ if (!length) return -1; *codepoint = *text; return 1; }
static void trace_add(char value)
{ if (trace_length + 1 < sizeof(trace)) { trace[trace_length++] = value; trace[trace_length] = 0; } }
bool accessibility_explore_point(int *point_x, int *point_y, bool *force)
{
    *point_x = explore_x; *point_y = explore_y; *force = point_force;
    bool result = point_ready; point_ready = false; return result;
}
const unsigned char *str(int language)
{
    const char *labels[] = { "", "Reading", "Paused", "Finished", "Speech error",
        "Empty", "Characters", "Words", "Lines", "Paragraphs", "Pages" };
    return (const unsigned char *)labels[language];
}
void tts_pause(bool paused) { ++pause_calls; trace_add(paused ? 'P' : 'U'); }
void tts_stop(void) { ++stop_calls; trace_add('S'); engine_busy = mixer_busy = false; }
bool tts_is_busy(void) { return engine_busy; }
bool tts_is_available(void) { return available; }
int mixer_channel_status(int channel) { return channel == PCM_MIXER_CHAN_VOICE && mixer_busy; }
const char *tts_last_error(void) { return last_error; }
size_t tts_read_position(void) { trace_add('R'); return tracked_position; }
bool tts_read_interrupted(void) { return false; }
int tts_speak(const char *text, size_t length, bool enqueue)
{
    (void)enqueue; ++speech_calls; trace_add('T');
    size_t copied = length < sizeof(last_speech) - 1 ? length : sizeof(last_speech) - 1;
    memcpy(last_speech, text, copied); last_speech[copied] = 0;
    engine_busy = speech_result >= 0;
    return speech_result;
}
int tts_speak_tracked(const char *text, size_t length)
{ ++tracked_calls; return tts_speak(text, length, false); }
static void reader_fail(struct text_reader *reader, int language)
{ (void)language; ++fail_calls; reader->state = READER_FAILED; reader->submitted = false; }
static void reader_read_failed(struct text_reader *reader, int status)
{ reader_fail(reader, status); }
static int reader_prepare(struct text_reader *reader)
{ (void)reader; ++load_calls; trace_add('L'); return load_failure ? -1 : 0; }
static int reader_read_chunk(int descriptor, off_t start, off_t size, char *text, off_t *next)
{
    (void)descriptor;
    size_t count = start < size ? (size_t)(size - start) : 0;
    if (count > 12) count = 12;
    memcpy(text, file_text + start, count); text[count] = 0;
    *next = start + count;
    return (int)count;
}
"""


READER_CASES = r"""
static void setup_reader(struct text_reader *reader, enum reader_state state)
{
    memset(reader, 0, sizeof(*reader));
    reader->name = "book.txt"; reader->size = (off_t)strlen(file_text);
    reader->viewports[0] = (struct viewport){20, 30, 100, 50, 0};
    reader->touch_line_height = 10; reader->touch_lines = 5; reader->touch_row = -2;
    reader->state = state; reader->start = 0; reader->cursor = 0; reader->next = 12;
    memcpy(reader->text, file_text, 12); reader->text[12] = 0;
    reader->length = 12; reader->loaded = true; reader->submitted = state == READER_READING;
    engine_busy = mixer_busy = reader->submitted;
    tracked_position = 4; available = true; last_error = "";
    load_failure = false; speech_result = 0;
    fail_calls = load_calls = pause_calls = stop_calls = speech_calls = tracked_calls = 0;
    trace_length = 0; trace[0] = last_speech[0] = 0;
    empty_speech_enabled = false;
}
static void explore_reader(struct text_reader *reader, int point_x, int point_y, bool force)
{
    explore_x = point_x; explore_y = point_y;
    point_ready = true; point_force = force;
    reader_explore(reader);
}
static int interrupt_cases(void)
{
    struct text_reader reader;
    setup_reader(&reader, READER_READING);
    reader_interrupt(&reader);
    CHECK(reader.cursor == 4 && reader.state == READER_PAUSED);
    CHECK(!reader.loaded && !reader.submitted && !reader.feedback && reader.dirty);
    CHECK(!strcmp(trace, "PRS"));
    setup_reader(&reader, READER_READING);
    reader.text[3] = (char)0xc3; reader.text[4] = (char)0xb3;
    reader_interrupt(&reader);
    CHECK(reader.cursor == 3);
    setup_reader(&reader, READER_READING);
    tracked_position = 999;
    reader_interrupt(&reader);
    CHECK(reader.cursor == 12);
    setup_reader(&reader, READER_READING);
    reader.cursor = 8; tracked_position = 2;
    reader_interrupt(&reader);
    CHECK(reader.cursor == 8);
    setup_reader(&reader, READER_READING);
    engine_busy = false; mixer_busy = true;
    reader_interrupt(&reader);
    CHECK(reader.cursor == 4);
    setup_reader(&reader, READER_READING);
    engine_busy = mixer_busy = false;
    reader_interrupt(&reader);
    CHECK(reader.cursor == reader.next);
    setup_reader(&reader, READER_READING);
    engine_busy = mixer_busy = false; last_error = "failure";
    reader_interrupt(&reader);
    CHECK(reader.cursor == 4);
    setup_reader(&reader, READER_READING);
    engine_busy = mixer_busy = false; available = false;
    reader_interrupt(&reader);
    CHECK(reader.cursor == 4);
    CHECK(music_position == 431 && music_volume == 77 && music_state == 3);
    return 0;
}
static int exploration_cases(void)
{
    struct text_reader reader;
    setup_reader(&reader, READER_READING);
    reader_explore(&reader);
    CHECK(pause_calls == 0 && speech_calls == 0 && reader.cursor == 0);
    explore_reader(&reader, 25, 35, false);
    CHECK(!strcmp(last_speech, "book.txt") && reader.cursor == 4);
    CHECK(reader.state == READER_READING && !reader.submitted && reader.feedback);
    CHECK(reader.loaded && reader.start == 4 && reader.next == 16);
    CHECK(!strcmp(trace, "PRSLT"));
    explore_reader(&reader, 90, 39, false);
    CHECK(speech_calls == 1 && pause_calls == 1 && reader.cursor == 4);
    reader_step(&reader);
    CHECK(reader.cursor == 4 && tracked_calls == 0);
    engine_busy = mixer_busy = false;
    reader_step(&reader);
    CHECK(reader.cursor == 4 && reader.submitted && tracked_calls == 1);
    CHECK(!strncmp(last_speech, file_text + 4, 12));
    CHECK(music_position == 431 && music_volume == 77 && music_state == 3);
    setup_reader(&reader, READER_PAUSED);
    explore_reader(&reader, 25, 45, true);
    CHECK(!strcmp(last_speech, "Paused") && reader.state == READER_PAUSED && reader.cursor == 0);
    explore_reader(&reader, 25, 55, true);
    CHECK(!strcmp(last_speech, "0 / 52 (0%)"));
    explore_reader(&reader, 25, 65, true);
    CHECK(!strncmp(last_speech, file_text, 12));
    explore_reader(&reader, 25, 75, true);
    CHECK(!strcmp(last_speech, "Words"));
    empty_speech_enabled = true;
    explore_reader(&reader, 120, 35, true);
    CHECK(!strcmp(last_speech, "Empty") && reader.cursor == 0);
    explore_reader(&reader, -1, -1, true);
    CHECK(!strcmp(last_speech, "Empty"));
    return 0;
}
static int edge_cases(void)
{
    struct text_reader reader;
    setup_reader(&reader, READER_FAILED);
    strcpy(reader.text, "Original failure");
    explore_reader(&reader, 25, 45, true);
    CHECK(!strcmp(last_speech, "Original failure"));
    CHECK(reader.state == READER_FAILED && pause_calls == 0 && stop_calls == 0 && load_calls == 0);
    setup_reader(&reader, READER_FINISHED);
    reader.cursor = reader.size; reader.loaded = false;
    explore_reader(&reader, 25, 45, true);
    CHECK(!strcmp(last_speech, "Finished") && reader.cursor == reader.size);
    CHECK(reader.state == READER_FINISHED && !reader.submitted);
    setup_reader(&reader, READER_PAUSED);
    speech_result = -1;
    explore_reader(&reader, 25, 35, true);
    CHECK(fail_calls == 1 && reader.state == READER_FAILED);
    setup_reader(&reader, READER_READING);
    load_failure = true;
    explore_reader(&reader, 25, 35, true);
    CHECK(fail_calls == 1 && speech_calls == 0 && reader.state == READER_FAILED);
    setup_reader(&reader, READER_PAUSED);
    reader.touch_line_height = 0;
    empty_speech_enabled = true;
    explore_reader(&reader, 25, 35, true);
    CHECK(!strcmp(last_speech, "Empty"));
    setup_reader(&reader, READER_PAUSED);
    reader.touch_lines = 4; reader.viewports[0].height = 40;
    explore_reader(&reader, 25, 35, true);
    CHECK(!strcmp(last_speech, "Paused"));
    explore_reader(&reader, 25, 65, true);
    CHECK(!strcmp(last_speech, "Words"));
    return 0;
}
static int partial_line_cases(void)
{
    struct text_reader reader;
    setup_reader(&reader, READER_PAUSED);
    empty_speech_enabled = true;
    reader.touch_lines = 2; reader.viewports[0].height = 25;
    explore_reader(&reader, 25, 54, true);
    CHECK(!strcmp(last_speech, "Empty"));
    reader.touch_lines = 0; reader.viewports[0].height = 5;
    explore_reader(&reader, 25, 34, true);
    CHECK(!strcmp(last_speech, "Empty"));
    reader.touch_lines = -1;
    explore_reader(&reader, 25, 34, true);
    CHECK(!strcmp(last_speech, "Empty"));
    reader.touch_line_height = -10;
    explore_reader(&reader, 25, 34, true);
    CHECK(!strcmp(last_speech, "Empty"));
    return 0;
}
static int empty_mode_cases(void)
{
    struct text_reader reader;
    for (int state = READER_READING; state <= READER_FAILED; ++state)
        for (int loaded = 0; loaded <= 1; ++loaded)
        {
            setup_reader(&reader, state);
            reader.loaded = loaded != 0;
            load_failure = true;
            struct text_reader before = reader;
            bool before_engine = engine_busy, before_mixer = mixer_busy;
            explore_reader(&reader, 120, 35, true);
            before.touch_row = reader.touch_row;
            CHECK(!memcmp(&before, &reader, sizeof(reader)));
            CHECK(!pause_calls && !stop_calls && !load_calls && !fail_calls && !speech_calls);
            CHECK(!trace_length && tracked_position == 4);
            CHECK(engine_busy == before_engine && mixer_busy == before_mixer);
            CHECK(music_position == 431 && music_volume == 77 && music_state == 3);
            explore_reader(&reader, 121, 36, false);
            CHECK(!pause_calls && !stop_calls && !load_calls && !fail_calls && !speech_calls);
        }
    setup_reader(&reader, READER_READING);
    empty_speech_enabled = true;
    explore_reader(&reader, 120, 35, true);
    CHECK(!strcmp(last_speech, "Empty") && reader.cursor == 4);
    CHECK(reader.state == READER_READING && reader.feedback && !reader.submitted);
    CHECK(stop_calls == 1 && load_calls == 1 && speech_calls == 1);
    explore_reader(&reader, 121, 36, false);
    CHECK(stop_calls == 1 && load_calls == 1 && speech_calls == 1);
    engine_busy = mixer_busy = false;
    reader_step(&reader);
    CHECK(reader.cursor == 4 && tracked_calls == 1 && reader.submitted);
    CHECK(!strncmp(last_speech, file_text + 4, 12));
    CHECK(music_position == 431 && music_volume == 77 && music_state == 3);
    return 0;
}
static int draw_geometry_cases(void)
{
    struct text_reader reader;
    setup_reader(&reader, READER_PAUSED);
    reader_draw(&reader);
    CHECK(reader.touch_line_height == 10 && reader.touch_lines == 5);
    CHECK(drawn_rows == 5 && !strcmp(drawn_text[0], "book.txt"));
    CHECK(!strcmp(drawn_text[1], "Paused") && !strcmp(drawn_text[4], "Words"));
    CHECK(!reader.dirty && display_viewport == NULL);
    reader.viewports[0].height = 40;
    reader_draw(&reader);
    CHECK(reader.touch_lines == 4 && drawn_rows == 4);
    CHECK(!strcmp(drawn_text[0], "Paused") && !strcmp(drawn_text[3], "Words"));
    explore_reader(&reader, 25, 35, true);
    CHECK(!strcmp(last_speech, "Paused"));
    reader.viewports[0].height = 25;
    reader_draw(&reader);
    CHECK(reader.touch_lines == 2 && drawn_rows == 2);
    CHECK(!strcmp(drawn_text[0], "Paused") && !strcmp(drawn_text[1], "0 / 52 (0%)"));
    return 0;
}
int main(int argc, char **argv)
{
    int result = argc != 2 ? 2 : !strcmp(argv[1], "interrupt") ? interrupt_cases() :
        !strcmp(argv[1], "empty-mode") ? empty_mode_cases() :
        !strcmp(argv[1], "exploration") ? exploration_cases() :
        !strcmp(argv[1], "edge") ? edge_cases() :
        !strcmp(argv[1], "partial-line") ? partial_line_cases() :
        !strcmp(argv[1], "draw-geometry") ? draw_geometry_cases() : 2;
    if (!result) printf("{\"checks\":%d}\n", checks);
    return result;
}
"""


def header_sources(inputs, button_target="firmware/target/hosted/hiby/r1/button-target.h"):
    touch = inputs["firmware/export/touchscreen.h"]
    start = touch.index("enum touchevent_type")
    end = touch.index("extern struct touchscreen_parameter", start)
    return touch[start:end] + "\n" + "\n".join(without_includes(inputs[path]) for path in (
        button_target,
        "firmware/export/button.h", "apps/action.h", "apps/accessibility_touch_wake.h",
    ))


def action_harness(inputs, variant="touch", mutation=None):
    defines = {"touch": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n",
               "no-espeak": "#define HAVE_TOUCHSCREEN\n",
               "no-touch": "#define HAVE_ESPEAK\n",
               "clipplus": "#define HAVE_ESPEAK\n",
               "clipzip": "#define HAVE_ESPEAK\n"}[variant]
    action = inputs["apps/action.c"]
    if mutation == "locked-touch":
        worker = function(action, "get_action_worker")
        modified = replace_once(worker,
                                "cur->action == ACTION_TOUCHSCREEN && !locked",
                                "locked || cur->action == ACTION_TOUCHSCREEN")
        modified = replace_once(modified,
            "if (last->keys_locked && has_flag(cur->button, BUTTON_TOUCHSCREEN) && accessibility_enabled())",
            "if (false)")
        action = replace_once(action, worker.strip(), modified.strip())
    if mutation == "raw-leak":
        raw = function(action, "action_get_touch_event")
        modified = replace_once(raw, "if (accessibility_enabled())", "if (false)")
        action = replace_once(action, raw.strip(), modified.strip())
    start = action.index("typedef struct")
    end = action.index("/* holds the action state", start)
    names = (
        "has_flag", "is_action_filtered", "is_action_discarded",
        "action_handle_backlight", "action_poll_button", "update_screen_has_lock",
        "get_action_touchscreen", "action_update_touch_lock", "do_key_lock", "autosoftlock_timeout",
        "do_auto_softlock", "do_softlock",
        "update_action_last", "init_act_cur", "do_backlight", "get_action_worker",
        "get_action", "get_custom_action",
    )
    button_target = (f"firmware/target/arm/as3525/sansa-{variant}/button-target.h"
                     if variant in ("clipplus", "clipzip") else
                     "firmware/target/hosted/hiby/r1/button-target.h")
    text = (COMMON + defines + header_sources(inputs, button_target=button_target)
            + action[start:end] + ACTION_MOCKS)
    for name in names:
        if name == "action_poll_button":
            text += "#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)\n"
            text += function(action, "accessibility_physical_button")
            text += function(action, "accessibility_clear_lock_queue") + "#endif\n"
        if name == "get_action_worker":
            text += "#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)\n"
            text += function(action, "accessibility_handle_touch_wake") + "#endif\n"
            text += "#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)\n"
            text += function(action, "accessibility_finish_button") + "#endif\n"
        text += function(action, name)
    text += "#ifdef HAVE_TOUCHSCREEN\n" + function(action, "action_get_touch_event") + "#endif\n"
    return text + ACTION_CASES


def list_harness(inputs, mutation=None):
    bitmap = inputs["apps/gui/bitmap/list.c"]
    if mutation == "right-scrollbar-old":
        bitmap = replace_once(bitmap,
                              "on_scrollbar_clicked = adj_x >= text->width &&\n"
                              "                                           adj_x < text->width + SCROLLBAR_WIDTH;",
                              "on_scrollbar_clicked = adj_x > (text->x + text->width - SCROLLBAR_WIDTH);")
    if mutation == "left-scrollbar-old":
        bitmap = replace_once(bitmap, "adj_x >= -SCROLLBAR_WIDTH && adj_x < 0",
                              "adj_x <= SCROLLBAR_WIDTH")
    explore = function(bitmap, "list_accessibility_explore")
    if mutation == "empty-bypass":
        explore = replace_once(explore, "accessibility_speak_empty();",
                               "talk_id(LANG_ACCESSIBILITY_EMPTY, false);")
    if mutation == "activate":
        explore = replace_once(explore, "return ACTION_REDRAW;", "return ACTION_STD_OK;")
    route = function(bitmap, "gui_synclist_do_touchscreen")
    route = route[:route.index("    struct touchevent tevent;")]
    route += "    ++legacy_touch_calls; return ACTION_STD_OK;\n}\n"
    draw_start = bitmap.index("            struct viewport vp = *list_text_vp;")
    draw_end = bitmap.index("            struct viewport *last =", draw_start)
    draw_geometry = (
        "static struct viewport apply_draw_scrollbar(struct gui_synclist *list)\n{\n"
        "    struct viewport *list_text_vp = &list_text[SCREEN_MAIN];\n"
        "    bool scrollbar_in_right = list->scrollbar == SCROLLBAR_RIGHT;\n"
        + bitmap[draw_start:draw_end] + "    return vp;\n}\n"
    )
    settings = inputs["apps/settings.h"]
    language_macros = (
        re.search(r'^#define VIRT_SIZE[^\n]+', settings, re.MULTILINE)[0] + "\n"
        + re.findall(r'^#define VIRT_PTR[^\n]+', settings, re.MULTILINE)[-1] + "\n"
        + "#define str(identifier) list_language_string(identifier)\n"
        + re.search(r'^#define P2STR[^\n]+', settings, re.MULTILINE)[0] + "\n"
    )
    talk_declarations = "\n".join(
        re.search(r'^int ' + name + r'\([^;]+;', inputs["apps/talk.h"], re.MULTILINE)[0]
        for name in ("talk_spell", "talk_id")
    ) + "\n"
    position_source = balanced_definition(
        inputs["apps/gui/list.h"], r"^enum list_position_source\s*\{").rstrip() + ";\n"
    return (COMMON + "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n"
            + language_macros + talk_declarations
            + header_sources(inputs) + LIST_MOCKS
            + "#ifdef HAVE_ESPEAK\n" + position_source + "#endif\n"
            + structure(inputs["apps/gui/list.h"], "gui_synclist") + LIST_RUNTIME
            + function(inputs["apps/gui/viewport.c"], "viewport_point_within_vp")
            + function(bitmap, "get_click_location")
            + function(inputs["apps/gui/list.c"], "gui_synclist_init")
            + explore + route + draw_geometry + LIST_CASES)


def reader_harness(inputs, mutation=None):
    reader = inputs["apps/tts_reader.c"]
    if mutation == "empty-interrupt":
        reader = replace_once(reader,
                              "    if (row < 0 && !accessibility_empty_speech_enabled())\n"
                              "        return;\n", "")
    if mutation == "bottom-row-old":
        reader = replace_once(reader,
                              "        if (row >= reader->touch_lines)\n"
                              "            row = -1;\n"
                              "        else if (reader->touch_lines < 5)",
                              "        if (reader->touch_lines < 5)")
    if mutation == "cursor-skip":
        sync = function(reader, "reader_sync")
        modified = replace_once(sync, "reader->cursor = cursor;", "reader->cursor = reader->next;")
        reader = replace_once(reader, sync.strip(), modified.strip())
    start = reader.index("#define READER_CHUNK_SIZE")
    end = reader.index("#if !defined(HIBY_R1)", start)
    names = (
        "reader_unit", "reader_unit_label", "reader_percent", "reader_report_state",
        "reader_label", "reader_load", "reader_audio_busy", "reader_sync",
        "reader_finish", "reader_step", "reader_interrupt", "reader_current_text",
        "reader_space", "reader_draw", "reader_explore",
    )
    return (COMMON + "#define HAVE_TOUCHSCREEN\n" + reader[start:end] + READER_MOCKS
            + function(inputs["apps/gui/viewport.c"], "viewport_point_within_vp")
            + "\n".join(function(reader, name) for name in names) + READER_CASES)


class AccessibilityIntegrationTests(unittest.TestCase):
    def run(self, result=None):
        actual_result = result if result is not None else self.defaultTestResult()
        failures_before = len(actual_result.failures) + len(actual_result.errors)
        returned = super().run(actual_result)
        if hasattr(type(self), "events"):
            self.events.append({
                "kind": "unittest", "name": self.id(),
                "passed": len(actual_result.failures) + len(actual_result.errors) == failures_before,
            })
        return returned

    @classmethod
    def setUpClass(cls):
        materials = project_materials_root(ROOT)
        ensure_ignored_directories(materials.parent, [materials.name])
        cls.workspace = (materials / "r1-accessibility-integration-20261011"
                         / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.inputs = {path: source(path) for path in INPUTS}
        cls.before = cls.hashes()
        cls.events = []
        cls.compiled = {}
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        version = subprocess.run(cls.compiler + ["--version"], capture_output=True, text=True)
        (cls.workspace / "compiler.txt").write_text(version.stdout + version.stderr, encoding="utf-8")
        (cls.workspace / "source-before.json").write_text(json.dumps(cls.before, indent=2), encoding="utf-8")

    @classmethod
    def hashes(cls):
        return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in INPUTS}

    @classmethod
    def tearDownClass(cls):
        after = cls.hashes()
        report = {
            "project": str(ROOT), "workspace": str(cls.workspace),
            "source_before": cls.before, "source_after": after,
            "source_unchanged": after == cls.before, "runs": cls.events,
            "checks": sum(event.get("checks", 0) for event in cls.events),
            "all_recorded_expectations_passed": all(event.get("passed", False) for event in cls.events),
            "manager_fsm": "Public APIs mocked; integration functions extracted from real sources",
            "hardware_tested": False, "gui_tested": False, "audio_tested": False,
            "nvda_tested": False,
        }
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if after != cls.before:
            raise AssertionError("Integration sources changed during independent test run")

    def compiled_case(self, group, mode, scenario, *, variant="touch", mutation=None):
        key = (group, mode, variant, mutation)
        if key not in self.compiled:
            name = "-".join(str(item) for item in key if item is not None)
            factories = {"action": action_harness, "list": list_harness, "reader": reader_harness}
            harness = (factories[group](self.inputs, variant=variant, mutation=mutation)
                       if group == "action" else factories[group](self.inputs, mutation=mutation))
            harness_path = self.workspace / (name + ".c")
            binary = self.workspace / (name + (".exe" if os.name == "nt" else ""))
            harness_path.write_text(harness, encoding="utf-8")
            command = self.compiler + ["-std=" + ("c11" if mode == "ubsan" else mode),
                                       "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                                       str(harness_path), "-o", str(binary)]
            if mode == "ubsan":
                command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
            (self.workspace / (name + "-compile.log")).write_text(
                shlex.join(command) + "\n" + completed.stdout + completed.stderr, encoding="utf-8")
            self.events.append({"kind": "compile", "name": name, "command": command,
                                "returncode": completed.returncode, "passed": completed.returncode == 0})
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.compiled[key] = binary
        binary = self.compiled[key]
        command = [str(binary), scenario]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20,
                                   env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"})
        log_name = binary.name + "-" + scenario + ".log"
        (self.workspace / log_name).write_text(shlex.join(command) + "\n" + completed.stdout
                                               + completed.stderr, encoding="utf-8")
        expected = completed.returncode != 0 and "check failed" in completed.stderr if mutation else completed.returncode == 0
        event = {"kind": "mutation" if mutation else "runtime", "name": log_name,
                 "command": command, "returncode": completed.returncode, "passed": expected}
        if not completed.returncode:
            event.update(json.loads(completed.stdout))
        self.events.append(event)
        self.assertTrue(expected, completed.stdout + completed.stderr)

    def test_real_action_dispatch_context_and_resets(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("action", mode, "dispatch")

    def test_real_softlock_blocks_accessibility_and_native_actions(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("action", mode, "lock")

    def test_ordinary_gestures_and_raw_api_only_hidden_in_accessibility(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("action", mode, "legacy")

    def test_real_timer_poll_softlock_context_and_idle_timeout(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("action", mode, "poll")

    def test_recognized_physical_feedback_lock_recovery_and_live_launcher_wiring(self):
        for mode in ("c99", "c11", "ubsan"):
            for scenario in ("physical-accessibility", "gesture-lock"):
                with self.subTest(mode=mode, scenario=scenario):
                    self.compiled_case("action", mode, scenario)

    def test_non_touch_and_non_espeak_action_variants(self):
        for variant in ("no-touch", "no-espeak"):
            for mode in ("c99", "c11", "ubsan"):
                for scenario in ("dispatch", "legacy", "poll"):
                    with self.subTest(variant=variant, mode=mode, scenario=scenario):
                        self.compiled_case("action", mode, scenario, variant=variant)

    def test_sansa_real_button_headers_have_no_manager_dependency(self):
        for variant in ("clipplus", "clipzip"):
            for mode in ("c99", "c11", "ubsan"):
                for scenario in ("dispatch", "legacy", "poll"):
                    with self.subTest(variant=variant, mode=mode, scenario=scenario):
                        self.compiled_case("action", mode, scenario, variant=variant)

    def test_real_list_focus_title_and_duplicate_suppression(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "focus")

    def test_real_list_viewport_scroll_and_empty_boundaries(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "geometry")

    def test_real_list_default_empty_silence_and_explicit_speech_keep_occupied_labels(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "empty-mode")

    def test_real_list_skin_rows_group_rows_and_local_coordinates(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "skin-group")

    def test_real_list_initialization_resets_target(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "target")

    def test_real_list_accessibility_routing_does_not_activate(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "route")

    def test_real_list_right_scrollbar_is_not_an_item(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "right-scrollbar")

    def test_real_list_left_scrollbar_preserves_text_and_icon_boundaries(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("list", mode, "left-scrollbar")

    def test_real_reader_interrupt_partial_complete_utf8_and_music_isolation(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("reader", mode, "interrupt")

    def test_real_reader_exploration_feedback_and_lossless_resume(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("reader", mode, "exploration")

    def test_real_reader_default_empty_silence_preserves_state_and_enabled_last_heard_resume(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("reader", mode, "empty-mode")

    def test_real_reader_failed_finished_load_failure_and_small_screen(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("reader", mode, "edge")

    def test_real_reader_partial_bottom_row_is_empty(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("reader", mode, "partial-line")

    def test_real_reader_draw_caches_actual_viewport_geometry(self):
        for mode in ("c99", "c11", "ubsan"):
            with self.subTest(mode=mode):
                self.compiled_case("reader", mode, "draw-geometry")

    def test_mutations_expose_activation_locked_touch_raw_leak_and_cursor_skip(self):
        for group, scenario, mutation in (
                ("list", "focus", "activate"), ("action", "lock", "locked-touch"),
                ("action", "legacy", "raw-leak"), ("reader", "interrupt", "cursor-skip"),
                ("list", "right-scrollbar", "right-scrollbar-old"),
                ("list", "left-scrollbar", "left-scrollbar-old"),
                ("reader", "partial-line", "bottom-row-old"),
                ("list", "empty-mode", "empty-bypass"),
                ("reader", "empty-mode", "empty-interrupt")):
            with self.subTest(mutation=mutation):
                self.compiled_case(group, "c11", scenario, mutation=mutation)

    def test_source_build_settings_and_menu_guards(self):
        paths = ("apps/SOURCES", "apps/action.c", "apps/gui/list.c",
                 "apps/gui/bitmap/list.c", "apps/settings.c", "apps/menus/settings_menu.c")
        for defines in ([], ["HAVE_ESPEAK"], ["HAVE_TOUCHSCREEN"],
                        ["HAVE_ESPEAK", "HAVE_TOUCHSCREEN"],
                        ["HAVE_ESPEAK", "HAS_BUTTON_HOLD"],
                        ["HAVE_ESPEAK", "BOOTLOADER"],
                        ["HAVE_ESPEAK", "HAVE_TOUCHSCREEN", "HAS_BUTTON_HOLD"],
                        ["HAVE_ESPEAK", "HAVE_TOUCHSCREEN", "BOOTLOADER"]):
            for path in paths:
                with self.subTest(path=path, defines=defines):
                    command = self.compiler + ["-E", "-P", "-x", "c", "-"] + ["-D" + item for item in defines]
                    completed = subprocess.run(command, input=without_includes(self.inputs[path]),
                                               capture_output=True, text=True, timeout=30)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    active = {"HAVE_ESPEAK", "HAVE_TOUCHSCREEN"}.issubset(defines)
                    token = (r'accessibility(?:_gesture)?\.c' if path == "apps/SOURCES"
                             else r'\baccessibility_(?!(?:screen|shortcut|display)_)\w+\b')
                    self.assertEqual(bool(re.search(token, completed.stdout)), active)
                    if path == "apps/action.c":
                        shared = ("HAVE_ESPEAK" in defines and "HAS_BUTTON_HOLD" not in defines
                                  and "BOOTLOADER" not in defines)
                        self.assertEqual(bool(re.search(r'\baccessibility_screen_lock_changed\s*\(',
                                                       completed.stdout)), shared)
                    elif path == "apps/menus/settings_menu.c":
                        shared = "HAVE_ESPEAK" in defines and "HAS_BUTTON_HOLD" not in defines
                        self.assertEqual(bool(re.search(r'\baccessibility_screen_(?:un)?lock_menu\b',
                                                       completed.stdout)), shared)
                        for name in ("accessibility_shortcut_activate", "accessibility_shortcut_enabled_menu",
                                     "accessibility_shortcut_service_menu"):
                            self.assertNotRegex(completed.stdout, r'\b' + name + r'\b')
                        self.assertEqual(len(re.findall(r'\bMAKE_MENU\s*\(\s*accessibility_shortcut_menu\b',
                                                        completed.stdout)), int("HAVE_ESPEAK" in defines))
                        self.assertEqual(len(re.findall(r'&accessibility_shortcut_menu\b',
                                                        completed.stdout)), int("HAVE_ESPEAK" in defines))
                    elif path == "apps/SOURCES":
                        self.assertEqual(bool(re.search(r'^accessibility_screen\.c$',
                                                       completed.stdout, re.MULTILINE)),
                                         "HAVE_ESPEAK" in defines)
                        self.assertEqual(len(re.findall(r'^accessibility_shortcut\.c$', completed.stdout,
                                                        re.MULTILINE)), int("HAVE_ESPEAK" in defines))
                        self.assertEqual(len(re.findall(r'^accessibility_services\.c$', completed.stdout,
                                                        re.MULTILINE)), int("HAVE_ESPEAK" in defines))


if __name__ == "__main__":
    unittest.main()
