"""Execute real action softlock paths with bounded button queues and UBSan."""

from datetime import datetime, timezone
import hashlib
import json
import os
import shlex
import subprocess
import unittest

from test_accessibility_integration import (
    ACTION_MOCKS, COMMON, INPUTS, ROOT, function, header_sources, replace_once,
)
from project_materials import ensure_ignored_directories, project_materials_root


MOCKS = r'''
#include <limits.h>
#define LANG_ACTION_AUTOLOCK_ON 3
#define LANG_ACTION_AUTOLOCK_OFF 4
#define SYS_USB_CONNECTED (SYS_EVENT | 1)
#define SYS_POWEROFF (SYS_EVENT | 2)
#define SYS_CHARGER_CONNECTED (SYS_EVENT | 11)
#define SYS_CHARGER_DISCONNECTED (SYS_EVENT | 12)
static int backlight_timeout = HZ;
static int button_polls, queue_clears, silent_splashes, legacy_splashes;
static int last_splash, transition_count;
static bool transitions[64];
static unsigned long poll_advance = ULONG_MAX;
static bool backlight_lit = true;
int backlight_get_current_timeout(void) { return backlight_timeout; }
bool is_backlight_on(bool ignore) { (void)ignore; return backlight_lit; }
void backlight_on_ignore(bool ignore, int ticks) { (void)ignore; (void)ticks; }
void backlight_on(void) { backlight_lit = true; }
bool backlight_screen_curtain_active(void) { return false; }
void sleep(int ticks) { (void)ticks; }
#ifdef HAVE_TOUCHPAD
int touchpad_filter(int button) { return button; }
#endif
static const struct button_mapping lock_map[] = {
    {ACTION_STD_KEYLOCK, BUTTON_POWER | BUTTON_REL, BUTTON_NONE},
    LAST_ITEM_IN_LIST
};
const struct button_mapping *get_context_mapping(int context)
{ (void)context; return lock_map; }
'''


CASES = r'''
static int notices(void)
{
#if defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    return 1;
#else
    return 0;
#endif
}

static void reset_lock(void)
{
    reset_action(false);
    current_tick = 100;
    action_last.tick = current_tick;
    button_polls = queue_clears = silent_splashes = legacy_splashes = 0;
    last_splash = transition_count = 0;
    memset(transitions, 0, sizeof(transitions));
    poll_advance = ULONG_MAX;
    backlight_timeout = HZ;
    backlight_lit = true;
    physical_action = ACTION_STD_NEXT;
}

static int feed(int button, unsigned long advance, int context, int timeout)
{
    queued_button = button;
    poll_advance = advance;
    return get_action(context, timeout);
}

#ifndef HAS_BUTTON_HOLD
static void arm(bool always)
{
    set_selective_softlock_actions(true, SEL_ACTION_AUTOLOCK |
        (always ? SEL_ACTION_ALWAYSAUTOLOCK : 0));
    action_autosoftlock_init();
}
#endif

static int startup_case(void)
{
    reset_lock();
#ifndef HAS_BUTTON_HOLD
    set_selective_softlock_actions(false, 0);
    set_selective_softlock_actions(false, 0);
    CHECK(!action_last.keys_locked && transition_count == 0);
    do_key_lock(false);
    CHECK(transition_count == 0);
    do_key_lock(true);
    CHECK(transition_count == notices());
    CHECK(!notices() || transitions[0]);
    do_key_lock(true);
    CHECK(transition_count == notices());
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    accessibility_forced_lock = true;
#endif
    set_selective_softlock_actions(true, SEL_ACTION_VOL);
    CHECK(!action_last.keys_locked && transition_count == 2 * notices());
    CHECK(!notices() || !transitions[1]);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    CHECK(!accessibility_forced_lock);
#endif
    set_selective_softlock_actions(true, SEL_ACTION_VOL);
    CHECK(transition_count == 2 * notices());
#endif
    CHECK(silent_splashes == 0 && legacy_splashes == 0);
    return 0;
}

static int manual_case(void)
{
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
#ifndef HAS_BUTTON_HOLD
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(feed(TEST_PHYSICAL_BUTTON, 1, context, 0) == ACTION_REDRAW);
    CHECK(action_last.keys_locked && transition_count == notices());
    CHECK(last_splash == LANG_KEYLOCK_ON);
    CHECK(silent_splashes == notices() && legacy_splashes == !notices());
    physical_action = ACTION_STD_NEXT;
    for (int repeat = 0; repeat < 8; ++repeat)
    {
        CHECK(feed(BUTTON_PLAY, 1, context, 0) == ACTION_REDRAW);
        CHECK(feed(BUTTON_PLAY | BUTTON_REPEAT, 1, context, 0) == ACTION_REDRAW);
        CHECK(feed(BUTTON_PLAY | BUTTON_REL, 1, context, 0) == ACTION_REDRAW);
    }
    CHECK(transition_count == notices() && action_last.keys_locked);
    int visuals = silent_splashes + legacy_splashes;
    CHECK(visuals > 1 && last_splash == LANG_KEYLOCK_ON);
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && transition_count == notices());
    CHECK(silent_splashes + legacy_splashes == visuals);
    physical_action = ACTION_UNKNOWN;
    CHECK(feed(TEST_PHYSICAL_BUTTON, 1, CONTEXT_STD, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && transition_count == 2 * notices());
    CHECK(last_splash == LANG_KEYLOCK_OFF);
    CHECK(!notices() || (transitions[0] && !transitions[1]));
    reset_lock();
    action_last.softlock_mask = SEL_ACTION_ALLNONOTIFY;
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(feed(TEST_PHYSICAL_BUTTON, 1, context, 0) == ACTION_REDRAW);
    CHECK(action_last.keys_locked && transition_count == notices());
    CHECK(silent_splashes == 0 && legacy_splashes == 0);
#else
    CHECK(feed(TEST_PHYSICAL_BUTTON, 1, context, 37) == ACTION_STD_NEXT);
    CHECK(last_timeout == 37 && transition_count == 0);
#endif
    return 0;
}

static int idle_case(void)
{
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
#ifndef HAS_BUTTON_HOLD
    arm(true);
    CHECK(transition_count == 0 && action_last.unlock_combo != BUTTON_NONE);
    CHECK(has_flag(action_last.softlock_mask, SEL_ACTION_ALOCK_OK));
#ifdef HAVE_BACKLIGHT
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == HZ && current_tick == 200 && button_polls == 1);
    CHECK(action_last.keys_locked && action_last.tick == 100);
    CHECK(transition_count == notices());
    CHECK(!notices() || transitions[0]);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && button_polls == 2);
    CHECK(transition_count == notices() && action_last.keys_locked);
#else
    CHECK(feed(BUTTON_NONE, 200, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && !action_last.keys_locked);
    CHECK(transition_count == 0);
#endif
#else
    CHECK(feed(BUTTON_NONE, 200, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && transition_count == 0);
#endif
    return 0;
}

static int queued_navigation_autolock_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && \
    !defined(HAS_BUTTON_HOLD) && defined(HAVE_BACKLIGHT)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE);
    arm(true);
    queued_navigation = true;
    int previous_cancels = navigation_cancel_calls;
    int action = feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK);
    fprintf(stderr, "queued-navigation autolock: locked=%d pending=%d cancels=%d "
        "action=%d menu_injected=%d timeout=%d tick=%ld\n",
        action_last.keys_locked, queued_navigation,
        navigation_cancel_calls - previous_cancels, action,
        action == ACTION_STD_MENU, last_timeout, current_tick);
    CHECK(last_timeout == HZ && current_tick == 200);
    CHECK(action_last.keys_locked);
    CHECK(!queued_navigation);
    CHECK(navigation_cancel_calls == previous_cancels + 1);
    CHECK(action != ACTION_STD_MENU);
    CHECK(action == ACTION_NONE || action == ACTION_REDRAW);
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE);
    CHECK(!queued_navigation && navigation_cancel_calls == previous_cancels + 1);
#endif
    return 0;
}

static int queued_navigation_unlocked_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE);
    arm(true);
    queued_navigation = true;
    int previous_cancels = navigation_cancel_calls;
    CHECK(feed(BUTTON_NONE, HZ - 1, context, TIMEOUT_BLOCK) == ACTION_STD_MENU);
    CHECK(!action_last.keys_locked && queued_navigation);
    CHECK(navigation_cancel_calls == previous_cancels);
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_STD_MENU);
    CHECK(!action_last.keys_locked && queued_navigation);
    CHECK(navigation_cancel_calls == previous_cancels);
#endif
    return 0;
}

static int queued_navigation_lock_transition_case(void)
{
#ifndef HAS_BUTTON_HOLD
    reset_lock();
    queued_navigation = true;
    do_key_lock(false);
    CHECK(!action_last.keys_locked && queued_navigation);
    CHECK(navigation_cancel_calls == 0);
    do_key_lock(true);
    CHECK(action_last.keys_locked);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    CHECK(!queued_navigation && navigation_cancel_calls == 1);
    queued_navigation = true;
    do_key_lock(true);
    CHECK(action_last.keys_locked && !queued_navigation);
    CHECK(navigation_cancel_calls == 2);
#else
    CHECK(queued_navigation && navigation_cancel_calls == 0);
#endif
    queued_navigation = true;
    int previous_cancels = navigation_cancel_calls;
    do_key_lock(false);
    CHECK(!action_last.keys_locked && queued_navigation);
    CHECK(navigation_cancel_calls == previous_cancels);
#endif
    return 0;
}

static int deadline_case(void)
{
#if !defined(HAS_BUTTON_HOLD) && defined(HAVE_BACKLIGHT)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    arm(true);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, 40) == ACTION_NONE);
    CHECK(current_tick == 140 && last_timeout == 40 && action_last.tick == 100);
    CHECK(feed(SYS_EVENT | 8, 15, context, TIMEOUT_BLOCK) == (SYS_EVENT | 8));
    CHECK(last_timeout == 60 && !action_last.keys_locked && action_last.tick == 100);
    CHECK(feed(BUTTON_REDRAW, 10, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 45 && !action_last.keys_locked && action_last.tick == 100);
    CHECK(feed(BUTTON_MULTIMEDIA | 1, 5, context, TIMEOUT_BLOCK) == (BUTTON_MULTIMEDIA | 1));
    CHECK(last_timeout == 35 && !action_last.keys_locked && action_last.tick == 100);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 30 && current_tick == 200 && action_last.keys_locked);
    CHECK(transition_count == notices());
    reset_lock();
    arm(true);
    CHECK(feed(SYS_EVENT | 4, HZ, context, TIMEOUT_BLOCK) == (SYS_EVENT | 4));
    CHECK(!action_last.keys_locked && transition_count == 0);
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 0 && button_polls == 2 && action_last.keys_locked);
    reset_lock();
    arm(true);
    CHECK(feed(BUTTON_NONE, 2 * HZ, CONTEXT_STD, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && !action_last.keys_locked);
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 0 && action_last.keys_locked && transition_count == notices());
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    reset_lock();
    arm(true);
    accessible = pending_timer = true;
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_TOUCHSCREEN);
    CHECK(last_timeout == 10 && current_tick == 110 && action_last.tick == 100);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 90 && action_last.keys_locked && transition_count == notices());
#endif
#endif
    return 0;
}

static int no_poll_case(void)
{
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && button_polls == 1);
#ifndef HAS_BUTTON_HOLD
    arm(false);
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && button_polls == 2);
    arm(true);
    CHECK(feed(BUTTON_NONE, 0, CONTEXT_STD, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && button_polls == 3);
    backlight_timeout = 0;
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK);
    backlight_timeout = -1;
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK);
    backlight_timeout = HZ;
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE && last_timeout == 0);
    CHECK(feed(BUTTON_NONE, 0, context, 5) == ACTION_NONE && last_timeout == 5);
    action_last.unlock_combo = BUTTON_NONE;
    CHECK(feed(BUTTON_NONE, HZ, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && !action_last.keys_locked);
    do_key_lock(true);
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && action_last.keys_locked);
    action_cur_t current;
    init_act_cur(&current, context, 0, NULL);
    current.action = ACTION_NONE;
    do_softlock(&action_last, &current);
    CHECK(action_last.keys_locked && transition_count == notices());
#endif
    return 0;
}

static int first_key_case(void)
{
#if !defined(HAS_BUTTON_HOLD) && defined(HAVE_BACKLIGHT)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    arm(true);
    CHECK(feed(BUTTON_PLAY, HZ - 1, context, TIMEOUT_BLOCK) == ACTION_STD_NEXT);
    CHECK(last_timeout == HZ && !action_last.keys_locked && action_last.tick == 199);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == HZ && current_tick == 299 && action_last.keys_locked);
    reset_lock();
    arm(true);
    int combo = action_last.unlock_combo;
    CHECK(feed(BUTTON_PLAY, HZ, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == HZ && action_last.keys_locked);
    CHECK(action_last.button == BUTTON_PLAY && action_last.unlock_combo == combo);
    CHECK(physical_calls == 1 && transition_count == notices());
    physical_action = ACTION_UNKNOWN;
    CHECK(feed(combo, 1, context, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && transition_count == 2 * notices());
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    reset_lock();
    arm(true);
    accessible = true;
    CHECK(feed(BUTTON_TOUCHSCREEN, HZ, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(action_last.keys_locked && transition_count == notices() && manager_calls == 0);
    CHECK(action_last.touchevent.tick == 200 && action_last.tick == 200);
    reset_lock();
    arm(true);
    custom_buttons = true;
    CHECK(feed(TEST_PHYSICAL_BUTTON, HZ - 1, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(!action_last.keys_locked && action_last.tick == 199);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == HZ && action_last.keys_locked && transition_count == notices());
    reset_lock();
    arm(true);
    custom_buttons = true;
    CHECK(feed(TEST_PHYSICAL_BUTTON, HZ, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(action_last.keys_locked && transition_count == notices());
#endif
#endif
    return 0;
}

static int arming_case(void)
{
#if !defined(HAS_BUTTON_HOLD) && defined(HAVE_BACKLIGHT)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    arm(false);
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(feed(TEST_PHYSICAL_BUTTON, 1, context, 0) == ACTION_REDRAW);
    CHECK(has_flag(action_last.softlock_mask, SEL_ACTION_ALOCK_OK));
    CHECK(!action_last.keys_locked && transition_count == 0);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == HZ && action_last.keys_locked && transition_count == notices());
#endif
    return 0;
}

static int wrap_case(void)
{
#if !defined(HAS_BUTTON_HOLD) && defined(HAVE_BACKLIGHT)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    long starts[] = {LONG_MAX - 30, -40};
    for (unsigned int index = 0; index < sizeof(starts) / sizeof(starts[0]); ++index)
    {
        reset_lock();
        current_tick = action_last.tick = starts[index];
        arm(true);
        CHECK(feed(BUTTON_NONE, ULONG_MAX, context, 45) == ACTION_NONE);
        CHECK(last_timeout == 45 && !action_last.keys_locked);
        int action = feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK);
        CHECK(action == ACTION_NONE || action == ACTION_REDRAW);
        CHECK(last_timeout == 55 && action_last.keys_locked && transition_count == notices());
        CHECK((unsigned long)current_tick - (unsigned long)action_last.tick == HZ);
        CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
        CHECK(last_timeout == TIMEOUT_BLOCK && transition_count == notices());
    }
    reset_lock();
    action_last.action = ACTION_STD_NEXT;
    action_last.tick = LONG_MAX - 5;
    current_tick = LONG_MIN + 1;
    action_cur_t current;
    init_act_cur(&current, context, 0, NULL);
    current.action = ACTION_STD_NEXT;
    current.button = BUTTON_PLAY;
    CHECK(update_action_last(&action_last, &current) == ACTION_STD_NEXT);
    CHECK(action_last.repeated);
    reset_lock();
    do_key_lock(true);
    action_last.softlock_mask = SEL_ACTION_ENABLED | SEL_ACTION_VOL | SEL_ACTION_NONOTIFY;
    current_tick = action_last.tick = LONG_MAX - 10;
    physical_action = ACTION_WPS_VOLUP;
    CHECK(feed(BUTTON_PLAY | BUTTON_REL, 1, context, 0) == ACTION_WPS_VOLUP);
    CHECK(action_last.keys_locked && transition_count == notices());
    physical_action = ACTION_STD_NEXT;
    CHECK(feed(BUTTON_PLAY | BUTTON_REL, HZ, context, 0) == ACTION_NONE);
    CHECK(action_last.keys_locked && transition_count == notices());
#endif
    return 0;
}

static int curtain_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD)
    reset_lock();
    arm(true);
    accessible = true;
    recover_curtain = true;
    action_last.wait_for_release = true;
    CHECK(feed(BUTTON_POWER | BUTTON_NEXT, 0, CONTEXT_KEYBOARD, 0) == ACTION_NONE);
    CHECK(!action_last.wait_for_release && !action_last.keys_locked);
    CHECK(transition_count == 0 && physical_calls == 0 && custom_clicks == 0);
#endif
    return 0;
}

static int explicit_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    int masks[] = {0, SEL_ACTION_AUTOLOCK, SEL_ACTION_AUTOLOCK | SEL_ACTION_ALWAYSAUTOLOCK,
        SEL_ACTION_ENABLED | SEL_ACTION_VOL | SEL_ACTION_AUTOLOCK | SEL_ACTION_ALOCK_OK};
    int lights[] = {-1, 0, HZ, 20 * HZ};
    for (unsigned int mask = 0; mask < sizeof(masks) / sizeof(*masks); ++mask)
        for (unsigned int light = 0; light < sizeof(lights) / sizeof(*lights); ++light)
        {
            reset_lock();
            action_last.softlock_mask = masks[mask];
            action_autosoftlock_init();
            unsigned int original_mask = action_last.softlock_mask;
            screen_autolock_seconds = 5;
            backlight_timeout = lights[light];
            CHECK(feed(BUTTON_NONE, 2 * HZ, context, 2 * HZ) == ACTION_NONE);
            CHECK(!action_last.keys_locked && last_timeout == 2 * HZ);
            backlight_timeout = lights[(light + 1) % 4];
            CHECK(feed(SYS_CHARGER_CONNECTED, HZ, context, TIMEOUT_BLOCK) == SYS_CHARGER_CONNECTED);
            CHECK(!action_last.keys_locked && last_timeout == 3 * HZ);
            queued_navigation = true;
            CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
            CHECK(last_timeout == 2 * HZ && action_last.keys_locked && !queued_navigation);
            CHECK(transition_count == 1 && action_last.softlock_mask == original_mask);
        }
    reset_lock(); arm(true); screen_autolock_seconds = 0;
    CHECK(feed(BUTTON_NONE, 20 * HZ, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && !action_last.keys_locked);
    reset_lock(); screen_autolock_seconds = 5;
    CHECK(feed(BUTTON_NONE, HZ * 9, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && !action_last.keys_locked);
    action_last.unlock_combo = BUTTON_TOUCHSCREEN;
    CHECK(feed(BUTTON_NONE, HZ * 9, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == TIMEOUT_BLOCK && !action_last.keys_locked);
    action_autosoftlock_init();
    int physical_unlock = action_last.unlock_combo;
    action_last.unlock_combo = BUTTON_TOUCHSCREEN;
    CHECK(feed(BUTTON_NONE, 0, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(last_timeout == 5 * HZ && action_last.unlock_combo == physical_unlock);
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(feed(TEST_PHYSICAL_BUTTON, 0, context, 0) == ACTION_REDRAW);
    CHECK(action_last.keys_locked);
    physical_action = ACTION_UNKNOWN;
    CHECK(feed(TEST_PHYSICAL_BUTTON, 1, context, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked);
    reset_lock(); action_autosoftlock_init(); screen_autolock_seconds = 5;
    CHECK(feed(BUTTON_NONE, HZ, context, 0) == ACTION_NONE);
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(feed(BUTTON_POWER | BUTTON_REL, 5 * HZ, context, 0) == ACTION_REDRAW);
    CHECK(action_last.keys_locked && transition_count == 1);
    screen_autolock_seconds = 10;
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE);
    CHECK(action_last.keys_locked && transition_count == 1);
    physical_action = ACTION_UNKNOWN;
    CHECK(feed(BUTTON_POWER | BUTTON_REL, 1, context, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && transition_count == 2);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 10 * HZ && action_last.keys_locked && transition_count == 3);
#endif
    return 0;
}

static int explicit_activity_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock(); action_autosoftlock_init(); screen_autolock_seconds = 5;
    CHECK(feed(BUTTON_NONE, HZ, context, 0) == ACTION_NONE);
    physical_action = ACTION_STD_NEXT;
    CHECK(feed(BUTTON_PLAY, HZ, context, 0) == ACTION_STD_NEXT);
    long activity = action_last.inactivity_tick;
    CHECK(activity == current_tick);
    CHECK(feed(BUTTON_PLAY | BUTTON_REPEAT, HZ, context, 0) == ACTION_STD_NEXT);
    CHECK(action_last.inactivity_tick == current_tick);
    CHECK(feed(BUTTON_PLAY | BUTTON_REL, HZ, context, 0) == ACTION_STD_NEXT);
    activity = action_last.inactivity_tick;
    CHECK(feed(BUTTON_PLAY | BUTTON_REL, HZ, context, 0) == ACTION_STD_NEXT);
    CHECK(action_last.inactivity_tick == activity);
    physical_action = ACTION_UNKNOWN;
    CHECK(feed(BUTTON_NEXT, HZ, context, 0) == ACTION_UNKNOWN);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(SYS_BATTERY_UPDATE, HZ, context, 0) == SYS_BATTERY_UPDATE);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 2 * HZ && action_last.keys_locked);
    reset_lock(); action_autosoftlock_init(); screen_autolock_seconds = 5;
    accessible = true;
    CHECK(feed(BUTTON_TOUCHSCREEN, HZ, context, 0) == ACTION_TOUCHSCREEN);
    for (int contact = 0; contact < 8; ++contact)
    {
        CHECK(feed(BUTTON_TOUCHSCREEN | BUTTON_REPEAT, HZ, context, 0) == ACTION_TOUCHSCREEN);
        CHECK(!action_last.keys_locked && action_last.inactivity_tick == current_tick);
    }
    CHECK(feed(BUTTON_TOUCHSCREEN | BUTTON_REL, HZ, context, 0) == ACTION_TOUCHSCREEN);
    activity = action_last.inactivity_tick;
    physical_action = ACTION_UNKNOWN;
    CHECK(feed(BUTTON_TOUCHSCREEN | BUTTON_REL, HZ, context, 0) == ACTION_UNKNOWN);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 4 * HZ && action_last.keys_locked);
    reset_lock(); action_autosoftlock_init(); screen_autolock_seconds = 5;
    CHECK(feed(BUTTON_NONE, HZ, context, 0) == ACTION_NONE);
    action_last.action = ACTION_STD_NEXT;
    action_last.tick = LONG_MAX - 5;
    long repeat_tick = action_last.tick;
    screen_autolock_seconds = 10;
    CHECK(feed(BUTTON_NONE, HZ, context, 0) == ACTION_NONE);
    CHECK(action_last.tick == repeat_tick && action_last.inactivity_tick == current_tick - HZ);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 9 * HZ && action_last.keys_locked);
#endif
    return 0;
}

static int explicit_rejected_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock(); action_autosoftlock_init(); screen_autolock_seconds = 5;
    CHECK(feed(BUTTON_NONE, HZ, context, 0) == ACTION_NONE);
    long activity = action_last.inactivity_tick;
    action_last.wait_for_release = true;
    CHECK(feed(BUTTON_PLAY, HZ, context, 0) == ACTION_NONE);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(BUTTON_PLAY | BUTTON_REL, HZ, context, 0) == ACTION_NONE);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(BUTTON_MULTIMEDIA_PLAYPAUSE, HZ, context, 0) == BUTTON_MULTIMEDIA_PLAYPAUSE);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == HZ && action_last.keys_locked);
    reset_lock(); action_autosoftlock_init(); screen_autolock_seconds = 5;
    CHECK(feed(BUTTON_NONE, HZ, context, 0) == ACTION_NONE);
    activity = action_last.inactivity_tick;
    recover_curtain = true;
    CHECK(feed(BUTTON_POWER | BUTTON_NEXT, HZ, context, 0) == ACTION_NONE);
    CHECK(action_last.inactivity_tick == activity);
    recover_curtain = false;
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 3 * HZ && action_last.keys_locked);
#endif
    return 0;
}

static int explicit_wrap_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    long starts[] = {LONG_MAX - 50, -50};
    for (unsigned int index = 0; index < sizeof(starts) / sizeof(*starts); ++index)
    {
        reset_lock(); action_autosoftlock_init(); screen_autolock_seconds = 5;
        current_tick = starts[index];
        CHECK(feed(BUTTON_NONE, ULONG_MAX, context, 3 * HZ) == ACTION_NONE);
        CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
        CHECK(last_timeout == 2 * HZ && action_last.keys_locked && transition_count == 1);
    }
#endif
    return 0;
}

static int passive_event_case(int system_event)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE);
    accessible = pending_timer = true;
    int previous_resets = reset_calls;
    action_last_t previous = action_last;
    CHECK(feed(system_event, 1, context, TIMEOUT_BLOCK) == system_event);
    CHECK(reset_calls == previous_resets);
    CHECK(pending_timer);
    CHECK(action_last.action == previous.action && action_last.button == previous.button);
    CHECK(action_last.context == previous.context && action_last.tick == previous.tick);
    CHECK(feed(BUTTON_NONE, 10, context, TIMEOUT_BLOCK) == ACTION_TOUCHSCREEN);
    CHECK(!pending_timer);
    CHECK(feed(BUTTON_NONE, 10, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(poll_calls == 2);
#else
    (void)system_event;
#endif
    return 0;
}

static int interrupting_event_case(int system_event)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    CHECK(feed(BUTTON_NONE, 0, context, 0) == ACTION_NONE);
    accessible = pending_timer = true;
    int previous_resets = reset_calls;
    CHECK(feed(system_event, 1, context, TIMEOUT_BLOCK) == system_event);
    CHECK(reset_calls == previous_resets + 1 && !pending_timer);
    CHECK(feed(BUTTON_NONE, 10, context, TIMEOUT_BLOCK) == ACTION_NONE);
    CHECK(feed(BUTTON_NONE, 10, context, TIMEOUT_BLOCK) == ACTION_NONE);
#else
    (void)system_event;
#endif
    return 0;
}

static int pending_context_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    reset_lock();
    CHECK(feed(BUTTON_NONE, 0, CONTEXT_STD, 0) == ACTION_NONE);
    accessible = pending_timer = true;
    int previous_resets = reset_calls;
    CHECK(feed(BUTTON_NONE, 1, CONTEXT_LIST, 0) == ACTION_NONE);
    CHECK(reset_calls == previous_resets + 1 && !pending_timer);
#endif
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    int result = !strcmp(argv[1], "startup") ? startup_case() :
        !strcmp(argv[1], "explicit") ? explicit_case() :
        !strcmp(argv[1], "explicit-activity") ? explicit_activity_case() :
        !strcmp(argv[1], "explicit-wrap") ? explicit_wrap_case() :
        !strcmp(argv[1], "explicit-rejected") ? explicit_rejected_case() :
        !strcmp(argv[1], "manual") ? manual_case() :
        !strcmp(argv[1], "idle") ? idle_case() :
        !strcmp(argv[1], "queued-navigation-autolock") ? queued_navigation_autolock_case() :
        !strcmp(argv[1], "queued-navigation-unlocked") ? queued_navigation_unlocked_case() :
        !strcmp(argv[1], "queued-navigation-lock-transition") ? queued_navigation_lock_transition_case() :
        !strcmp(argv[1], "deadline") ? deadline_case() :
        !strcmp(argv[1], "no-poll") ? no_poll_case() :
        !strcmp(argv[1], "first-key") ? first_key_case() :
        !strcmp(argv[1], "arming") ? arming_case() :
        !strcmp(argv[1], "wrap") ? wrap_case() :
        !strcmp(argv[1], "charger-connected") ? passive_event_case(SYS_CHARGER_CONNECTED) :
        !strcmp(argv[1], "charger-disconnected") ? passive_event_case(SYS_CHARGER_DISCONNECTED) :
        !strcmp(argv[1], "battery-update") ? passive_event_case(SYS_BATTERY_UPDATE) :
        !strcmp(argv[1], "usb-interrupt") ? interrupting_event_case(SYS_USB_CONNECTED) :
        !strcmp(argv[1], "poweroff-interrupt") ? interrupting_event_case(SYS_POWEROFF) :
        !strcmp(argv[1], "other-interrupt") ? interrupting_event_case(SYS_EVENT | 4) :
        !strcmp(argv[1], "other-eight-interrupt") ? interrupting_event_case(SYS_EVENT | 8) :
        !strcmp(argv[1], "pending-context") ? pending_context_case() :
        !strcmp(argv[1], "curtain") ? curtain_case() : 2;
    if (!result) printf("{\"checks\":%d,\"long_bits\":%zu}\n", checks, sizeof(long) * CHAR_BIT);
    return result;
}
'''


VARIANTS = {
    "touch": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n#define HAVE_BACKLIGHT\n",
    "buttons": "#define HAVE_ESPEAK\n#define HAVE_BACKLIGHT\n",
    "prerecorded": "#define HAVE_TOUCHSCREEN\n#define HAVE_BACKLIGHT\n",
    "no-backlight": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n",
    "bootloader": "#define HAVE_ESPEAK\n#define HAVE_BACKLIGHT\n#define BOOTLOADER\n",
    "bootloader-touch": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n#define HAVE_BACKLIGHT\n#define BOOTLOADER\n",
    "hold": "#define HAVE_ESPEAK\n#define HAVE_BACKLIGHT\n#define HAS_BUTTON_HOLD\n",
    "hold-touch": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n#define HAVE_BACKLIGHT\n#define HAS_BUTTON_HOLD\n",
    "hold-no-backlight": "#define HAS_BUTTON_HOLD\n",
    "touchpad": "#define HAVE_ESPEAK\n#define HAVE_BACKLIGHT\n#define HAVE_TOUCHPAD\n",
}


def harness(inputs, variant):
    action = inputs["apps/action.c"]
    start = action.index("typedef struct")
    end = action.index("/* holds the action state", start)
    mocks = replace_once(ACTION_MOCKS,
        "long button_get_w_tmo(int timeout) { last_timeout = timeout; return queued_button; }",
        "long button_get_w_tmo(int timeout)\n{\n"
        "    last_timeout = timeout; ++button_polls;\n"
        "    unsigned long advance = poll_advance;\n"
        "    if (advance == ULONG_MAX)\n"
        "        advance = queued_button == BUTTON_NONE && timeout > 0 ? (unsigned long)timeout : 0;\n"
        "    current_tick = (long)((unsigned long)current_tick + advance);\n"
        "    return queued_button;\n}")
    mocks = replace_once(mocks, "void button_clear_queue(void) {}",
                         "void button_clear_queue(void) { ++queue_clears; }")
    mocks = replace_once(mocks,
        "void splash(int ticks, int label) { (void)ticks; (void)label; }",
        "void splash(int ticks, int label)\n"
        "{ (void)ticks; ++legacy_splashes; last_splash = label; }")
    mocks = replace_once(mocks,
        "void splashf_silent(int ticks, int label, ...) { (void)ticks; (void)label; }",
        "void splashf_silent(int ticks, int label, ...)\n"
        "{ (void)ticks; ++silent_splashes; last_splash = label; }")
    mocks = replace_once(mocks,
        "void accessibility_screen_lock_changed(bool locked) { (void)locked; }",
        "void accessibility_screen_lock_changed(bool locked)\n"
        "{ if (transition_count >= 64) abort(); transitions[transition_count++] = locked; }")
    mocks = replace_once(mocks, "    action_last.sl_filter_tick = -1;",
                         "#ifndef HAS_BUTTON_HOLD\n    action_last.sl_filter_tick = -1;\n#endif")
    for name, implementation in (
        ("accessibility_screen_unlock_any_button", "bool accessibility_screen_unlock_any_button(void) { return false; }"),
        ("accessibility_screen_locked_buttons", "bool accessibility_screen_locked_buttons(void) { return false; }"),
        ("button_queue_count", "int button_queue_count(void) { return 0; }"),
        ("button_clear_queue_preserve_events", "void button_clear_queue_preserve_events(void) {}"),
        ("button_queue_post", "void button_queue_post(long button, intptr_t data) { (void)button; (void)data; }"),
    ):
        if name + "(" not in mocks:
            mocks += implementation + "\n"
    names = (
        "has_flag", "accessibility_physical_button", "accessibility_clear_lock_queue",
        "is_action_filtered", "is_action_discarded",
        "action_handle_backlight", "action_poll_button", "update_screen_has_lock",
        "get_action_touchscreen", "action_update_touch_lock", "do_key_lock", "autosoftlock_timeout", "do_auto_softlock",
        "do_softlock", "update_action_last", "init_act_cur", "do_backlight",
        "get_action_worker", "get_action", "get_custom_action",
        "set_selective_softlock_actions", "find_button_for_action", "action_autosoftlock_init",
    )
    guarded = {"action_update_touch_lock", "do_key_lock", "autosoftlock_timeout", "do_auto_softlock",
               "set_selective_softlock_actions", "find_button_for_action", "action_autosoftlock_init"}
    text = COMMON + VARIANTS[variant] + header_sources(inputs) + action[start:end] + MOCKS + mocks
    for name in names:
        policy_helper = name in ("accessibility_physical_button", "accessibility_clear_lock_queue")
        if policy_helper:
            text += "#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)\n"
        if name == "get_action_worker":
            text += "#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)\n"
            text += function(action, "accessibility_handle_touch_wake") + "#endif\n"
            text += "#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)\n"
            text += function(action, "accessibility_finish_button") + "#endif\n"
        if name in guarded:
            text += "#ifndef HAS_BUTTON_HOLD\n"
        if name in ("is_action_filtered", "is_action_discarded", "action_handle_backlight"):
            text += "#if defined(HAVE_BACKLIGHT) || !defined(HAS_BUTTON_HOLD)\n"
        text += function(action, name)
        if policy_helper or name in guarded or name in ("is_action_filtered", "is_action_discarded", "action_handle_backlight"):
            text += "#endif\n"
    return text + CASES


class AccessibilityScreenLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        materials = project_materials_root(ROOT)
        ensure_ignored_directories(materials.parent, [materials.name])
        cls.workspace = materials / "r1-empty-radio-20261017" / "screen-lock" / (
            "action-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.inputs = {path: (ROOT / path).read_text(encoding="utf-8") for path in INPUTS}
        cls.hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                      for path in (*INPUTS, "tools/tests/test_accessibility_screen_lock.py")}
        cls.events = []
        cls.binaries = {}
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))

    @classmethod
    def tearDownClass(cls):
        report = {"source_hashes": cls.hashes, "runs": cls.events,
                  "all_passed": all(event["passed"] for event in cls.events),
                  "hardware_tested": False, "audio_tested": False,
                  "global_input_tested": False, "release_built": False}
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def run_case(self, variant, scenario):
        if variant not in self.binaries:
            path = self.workspace / (variant + ".c")
            binary = self.workspace / (variant + (".exe" if os.name == "nt" else ""))
            path.write_text(harness(self.inputs, variant), encoding="utf-8")
            command = self.compiler + ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-function", "-pedantic"]
            if os.environ.get("ROCKBOX_SCREEN_SANITIZERS", "1") != "0":
                command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            command += [str(path), "-o", str(binary)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (self.workspace / (variant + "-compile.log")).write_text(
                shlex.join(command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
            self.events.append({"kind": "compile", "variant": variant, "passed": result.returncode == 0})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.binaries[variant] = binary
        command = [str(self.binaries[variant]), scenario]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10,
            env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"})
        (self.workspace / (variant + "-" + scenario + ".log")).write_text(
            shlex.join(command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
        event = {"kind": "runtime", "variant": variant, "scenario": scenario,
                 "passed": result.returncode == 0}
        if not result.returncode:
            event.update(json.loads(result.stdout))
        self.events.append(event)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_initial_unlock_or_same_state_notice(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "startup")

    def test_explicit_policy_replaces_legacy_timer_and_preserves_manual_lock(self):
        for variant in ("touch", "no-backlight"):
            self.run_case(variant, "explicit")

    def test_explicit_timer_uses_accepted_input_and_not_repeat_bookkeeping(self):
        for variant in ("touch", "no-backlight"):
            self.run_case(variant, "explicit-activity")

    def test_explicit_deadline_wraps_without_undefined_behavior(self):
        for variant in ("touch", "no-backlight"):
            self.run_case(variant, "explicit-wrap")

    def test_rejected_contacts_system_events_and_curtain_escape_are_not_activity(self):
        for variant in ("touch", "no-backlight"):
            self.run_case(variant, "explicit-rejected")

    def test_manual_transitions_and_blocked_key_releases(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "manual")

    def test_idle_deadline_locks_once_without_zero_combo_unlock(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "idle")

    def test_autolock_cancels_queued_navigation_before_pending_dispatch(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "queued-navigation-autolock")

    def test_unlocked_pending_navigation_survives_ordinary_idle_polls(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "queued-navigation-unlocked")

    def test_lock_cancels_queued_navigation_but_unlock_preserves_it(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "queued-navigation-lock-transition")

    def test_finite_wait_and_system_events_preserve_existing_deadline(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "deadline")

    def test_no_new_periodic_wakeups_without_applicable_armed_deadline(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "no-poll")

    def test_real_key_before_at_deadline_and_touch_cannot_erase_expiry(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "first-key")

    def test_arming_does_not_announce_lock_until_actual_transition(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "arming")

    def test_tick_signed_and_unsigned_wrap_with_ubsan(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.run_case(variant, "wrap")

    def test_curtain_recovery_remains_ahead_of_input_filters(self):
        self.run_case("touch", "curtain")

    def test_passive_power_events_preserve_action_worker_pending_input(self):
        for scenario in ("battery-update", "charger-connected", "charger-disconnected"):
            with self.subTest(scenario=scenario):
                self.run_case("touch", scenario)

    def test_interrupting_events_still_reset_action_worker_pending_input(self):
        for scenario in ("usb-interrupt", "poweroff-interrupt", "other-interrupt", "other-eight-interrupt"):
            with self.subTest(scenario=scenario):
                self.run_case("touch", scenario)

    def test_context_change_still_resets_action_worker_pending_input(self):
        self.run_case("touch", "pending-context")


if __name__ == "__main__":
    unittest.main()
