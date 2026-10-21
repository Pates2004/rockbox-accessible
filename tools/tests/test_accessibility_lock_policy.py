"""Execute touchscreen lock policies, queued events and raw Power shutdown."""

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import subprocess
import unittest

from test_accessibility_integration import ROOT, INPUTS, balanced_definition, function, without_includes
from test_accessibility_screen_lock import harness
from project_materials import project_materials_root


QUEUE = r'''
static bool unlock_policy, passthrough_policy;
static int policy_queue_count, policy_queue_buttons[64];
static intptr_t policy_queue_data[64];
static void policy_push(int button, intptr_t data)
{
    if (policy_queue_count >= 64) abort();
    policy_queue_buttons[policy_queue_count] = button;
    policy_queue_data[policy_queue_count++] = data;
}
static int policy_pop(void)
{
    int button = policy_queue_buttons[0];
    queued_data = policy_queue_data[0];
    --policy_queue_count;
    memmove(policy_queue_buttons, policy_queue_buttons + 1,
        policy_queue_count * sizeof(*policy_queue_buttons));
    memmove(policy_queue_data, policy_queue_data + 1,
        policy_queue_count * sizeof(*policy_queue_data));
    return button;
}
static void policy_clear_queue(void)
{
    int retained = 0;
    for (int position = 0; position < policy_queue_count; ++position)
    {
        int button = policy_queue_buttons[position];
        if ((button & (SYS_EVENT | BUTTON_MULTIMEDIA | BUTTON_REL)) || button == BUTTON_REDRAW)
        {
            policy_queue_buttons[retained] = button;
            policy_queue_data[retained++] = policy_queue_data[position];
        }
    }
    policy_queue_count = retained;
}
'''


ACTION_CASES = r'''
static void policy_reset(bool unlock, bool passthrough)
{
    reset_lock();
    unlock_policy = unlock;
    passthrough_policy = passthrough;
    policy_queue_count = 0;
    do_key_lock(true);
    transition_count = 0;
}

static int unlock_case(void)
{
    int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    int buttons[] = { BUTTON_POWER, BUTTON_PLAY, BUTTON_NEXT, BUTTON_VOL_UP, BUTTON_VOL_DOWN };
    for (unsigned int index = 0; index < sizeof(buttons) / sizeof(*buttons); ++index)
        for (int passthrough = 0; passthrough < 2; ++passthrough)
        {
            policy_reset(true, passthrough);
            custom_buttons = true;
            custom_action = ACTION_STD_OK;
            physical_action = ACTION_STD_OK;
            CHECK(feed(buttons[index], 1, context, 0) == ACTION_REDRAW);
            CHECK(!action_last.keys_locked && transition_count == 1 && !transitions[0]);
            CHECK(physical_calls == 0 && custom_clicks == 0);
            CHECK(feed(BUTTON_NONE, 1, context, 0) == ACTION_NONE);
            CHECK(feed(buttons[index] | BUTTON_REPEAT, 1, context, 0) == ACTION_NONE);
            CHECK(feed(buttons[index] | BUTTON_REPEAT | BUTTON_REL, 1, context, 0) == ACTION_NONE);
            CHECK(feed(buttons[index] | BUTTON_REL, 1, context, 0) == ACTION_NONE);
            CHECK(feed(buttons[index] | BUTTON_REPEAT, 1, context, 0) == ACTION_NONE);
            CHECK(feed(BUTTON_NONE, 1, context, 0) == ACTION_NONE);
            CHECK(physical_calls == 0 && custom_clicks == 0 && pending_launch_calls == 0);
            CHECK(feed(buttons[index], 1, context, 0) == ACTION_NONE);
            CHECK(feed(buttons[index] | BUTTON_REL, 1, context, 0) == ACTION_STD_OK);
            CHECK(transition_count == 1 && !action_last.keys_locked);
        }
    policy_reset(true, false);
    accessible = true;
    manager_action = ACTION_TOUCHSCREEN;
    CHECK(feed(BUTTON_POWER, 1, context, 0) == ACTION_REDRAW);
    CHECK(feed(BUTTON_POWER | BUTTON_REL, 1, context, 0) == ACTION_NONE);
    CHECK(!action_last.unlock_contact);
    int previous_calls = manager_calls;
    feed(BUTTON_TOUCHSCREEN, 1, context, 0);
    CHECK(manager_calls == previous_calls + 1 && !action_last.keys_locked);
    feed(BUTTON_TOUCHSCREEN | BUTTON_REL, 1, context, 0);
    CHECK(manager_calls == previous_calls + 2 && !action_last.keys_locked);
    policy_reset(true, false);
    accessible = true;
    manager_action = ACTION_TOUCHSCREEN;
    CHECK(feed(BUTTON_POWER, 1, context, 0) == ACTION_REDRAW);
    recover_curtain = true;
    int previous_resets = reset_calls;
    CHECK(feed(BUTTON_POWER | BUTTON_NEXT, 1, context, 0) == ACTION_NONE);
    CHECK(reset_calls == previous_resets + 1 && !action_last.keys_locked);
    recover_curtain = false;
    CHECK(feed(BUTTON_POWER | BUTTON_REL, 1, context, 0) == ACTION_NONE);
    CHECK(feed(BUTTON_NEXT | BUTTON_REL, 1, context, 0) == ACTION_NONE);
    previous_calls = manager_calls;
    feed(BUTTON_TOUCHSCREEN, 1, context, 0);
    CHECK(manager_calls == previous_calls + 1 && !action_last.keys_locked);
    return 0;
}

static int fresh_case(void)
{
    int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    int excluded[] = { BUTTON_NONE, BUTTON_POWER | BUTTON_REPEAT,
        BUTTON_POWER | BUTTON_REL, BUTTON_TOUCHSCREEN, BUTTON_CENTER,
        BUTTON_TOPLEFT | BUTTON_REL, BUTTON_TOUCH, SYS_USB_CONNECTED,
        SYS_POWEROFF, SYS_BATTERY_UPDATE, BUTTON_MULTIMEDIA_PLAYPAUSE, BUTTON_REDRAW };
    for (unsigned int index = 0; index < sizeof(excluded) / sizeof(*excluded); ++index)
    {
        policy_reset(true, false);
        feed(excluded[index], 1, context, 0);
        CHECK(action_last.keys_locked && transition_count == 0);
    }
    reset_lock();
    unlock_policy = true;
    physical_action = ACTION_NONE;
    feed(BUTTON_POWER, 1, context, 0);
    do_key_lock(true);
    transition_count = 0;
    feed(BUTTON_POWER, 1, context, 0);
    CHECK(action_last.keys_locked && transition_count == 0);
    feed(BUTTON_POWER | BUTTON_REL, 1, context, 0);
    CHECK(feed(BUTTON_POWER, 1, context, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && transition_count == 1);
    policy_reset(true, false);
    action_last.wait_for_release = true;
    action_last.context = CONTEXT_WPS;
    CHECK(feed(BUTTON_NEXT, 1, CONTEXT_KEYBOARD, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && !action_last.wait_for_release);
    CHECK(feed(BUTTON_NEXT | BUTTON_REL, 1, CONTEXT_KEYBOARD, 0) == ACTION_NONE);
    return 0;
}

static int passthrough_case(void)
{
    int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    int actions[] = { ACTION_STD_OK, ACTION_STD_NEXT, ACTION_STD_CONTEXT,
        ACTION_WPS_PLAY, ACTION_WPS_SKIPNEXT, ACTION_WPS_VOLUP, ACTION_WPS_SEEKFWD };
    for (unsigned int index = 0; index < sizeof(actions) / sizeof(*actions); ++index)
    {
        policy_reset(false, true);
        unsigned int mask = SEL_ACTION_ENABLED | SEL_ACTION_VOL | SEL_ACTION_NONOTIFY;
        action_last.softlock_mask = mask;
        physical_action = actions[index];
        CHECK(feed(BUTTON_NEXT, 1, context, 0) == actions[index]);
        CHECK(feed(BUTTON_NEXT | BUTTON_REPEAT, 1, context, 0) == actions[index]);
        CHECK(feed(BUTTON_NEXT | BUTTON_REL, 1, context, 0) == actions[index]);
        CHECK(action_last.keys_locked && transition_count == 0 && action_last.softlock_mask == mask);
        for (int accessible_mode = 0; accessible_mode < 2; ++accessible_mode)
        {
            accessible = accessible_mode;
            CHECK(feed(BUTTON_TOUCHSCREEN, 1, context, 0) == ACTION_NONE);
            CHECK(feed(BUTTON_TOUCHSCREEN | BUTTON_REL, 1, context, 0) == ACTION_NONE);
            CHECK(feed(BUTTON_CENTER, 1, context, 0) == ACTION_NONE);
            CHECK(feed(BUTTON_CENTER | BUTTON_REL, 1, context, 0) == ACTION_NONE);
            CHECK(manager_calls == 0 && ordinary_process_calls == 0);
        }
        CHECK(action_last.keys_locked && transition_count == 0);
    }
    return 0;
}

static int deferred_case(void)
{
    int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    policy_reset(false, true);
    custom_buttons = true;
    custom_action = ACTION_STD_OK;
    CHECK(feed(BUTTON_NEXT, 1, context, 0) == ACTION_NONE);
    custom_poll = true;
    CHECK(feed(BUTTON_NONE, 1, context, 0) == ACTION_STD_OK);
    CHECK(action_last.keys_locked && transition_count == 0);
    custom_action = ACTION_STD_KEYLOCK;
    CHECK(feed(BUTTON_NEXT | BUTTON_REL, 1, context, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && transition_count == 1 && !transitions[0]);
    policy_reset(false, true);
    physical_action = ACTION_STD_KEYLOCK;
    CHECK(feed(BUTTON_POWER | BUTTON_VOL_UP, 1, context, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && transition_count == 1);
    return 0;
}

static int queued_events_case(void)
{
    int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    policy_reset(true, false);
    policy_push(BUTTON_POWER, 0);
    policy_push(BUTTON_NEXT, 111);
    policy_push(SYS_USB_CONNECTED, 222);
    policy_push(SYS_POWEROFF, 333);
    policy_push(BUTTON_MULTIMEDIA_PLAYPAUSE, 444);
    policy_push(BUTTON_REDRAW, 555);
    policy_push(BUTTON_POWER | BUTTON_REL, 666);
    policy_push(BUTTON_POWER | BUTTON_REPEAT, 777);
    CHECK(get_action(context, 0) == ACTION_REDRAW);
    CHECK(policy_queue_count == 5);
    CHECK(get_action(context, 0) == SYS_USB_CONNECTED && queued_data == 222);
    CHECK(get_action(context, 0) == SYS_POWEROFF && queued_data == 333);
    CHECK(get_action(context, 0) == BUTTON_MULTIMEDIA_PLAYPAUSE && queued_data == 444);
    CHECK(get_action(context, 0) == ACTION_REDRAW && queued_data == 555);
    CHECK(get_action(context, 0) == ACTION_NONE && queued_data == 666);
    CHECK(!action_last.keys_locked && transition_count == 1 && policy_queue_count == 0);
    return 0;
}

static int context_escape_case(void)
{
    int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    policy_reset(true, false);
    CHECK(feed(BUTTON_POWER, 1, context, 0) == ACTION_REDRAW);
    CHECK(feed(BUTTON_POWER | BUTTON_REPEAT, 1, CONTEXT_WPS | ALLOW_SOFTLOCK, 0) == ACTION_NONE);
    recover_curtain = true;
    int previous_resets = reset_calls;
    CHECK(feed(BUTTON_POWER | BUTTON_NEXT, 1, CONTEXT_KEYBOARD, 0) == ACTION_NONE);
    CHECK(reset_calls > previous_resets);
    recover_curtain = false;
    CHECK(feed(BUTTON_NEXT | BUTTON_REL, 1, context, 0) == ACTION_NONE);
    CHECK(feed(BUTTON_POWER | BUTTON_REL, 1, context, 0) == ACTION_NONE);
    CHECK(physical_calls == 0 && !action_last.keys_locked);
    return 0;
}

static int explicit_policies_case(void)
{
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    for (int unlock = 0; unlock < 2; ++unlock)
        for (int passthrough = 0; passthrough < 2; ++passthrough)
        {
            reset_lock(); unlock_policy = unlock; passthrough_policy = passthrough;
            policy_queue_count = 0;
            action_autosoftlock_init(); screen_autolock_seconds = 5;
            CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
            CHECK(action_last.keys_locked && transition_count == 1);
            physical_action = ACTION_STD_NEXT;
            int result = feed(BUTTON_PLAY, 1, context, 0);
            if (unlock)
            {
                CHECK(result == ACTION_REDRAW && !action_last.keys_locked && transition_count == 2);
                CHECK(feed(BUTTON_PLAY | BUTTON_REPEAT, HZ, context, 0) == ACTION_NONE);
                CHECK(feed(BUTTON_PLAY | BUTTON_REL, 1, context, 0) == ACTION_NONE);
                accessible = true;
                CHECK(feed(BUTTON_TOUCHSCREEN, 1, context, 0) == ACTION_TOUCHSCREEN);
                CHECK(action_last.inactivity_tick == current_tick && !action_last.keys_locked);
                CHECK(feed(BUTTON_TOUCHSCREEN | BUTTON_REL, 1, context, 0) == ACTION_TOUCHSCREEN);
            }
            else
            {
                CHECK(action_last.keys_locked && transition_count == 1);
                CHECK(passthrough ? result == ACTION_STD_NEXT : result != ACTION_STD_NEXT);
                accessible = true;
                CHECK(feed(BUTTON_TOUCHSCREEN, 1, context, 0) == ACTION_NONE);
                CHECK(action_last.keys_locked);
            }
        }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    int result = !strcmp(argv[1], "unlock") ? unlock_case() :
        !strcmp(argv[1], "fresh") ? fresh_case() :
        !strcmp(argv[1], "passthrough") ? passthrough_case() :
        !strcmp(argv[1], "deferred") ? deferred_case() :
        !strcmp(argv[1], "queued-events") ? queued_events_case() :
        !strcmp(argv[1], "explicit-policies") ? explicit_policies_case() :
        !strcmp(argv[1], "context-escape") ? context_escape_case() : 2;
    if (!result) printf("{\"checks\":%d}\n", checks);
    return result;
}
'''


PERSISTENCE = r'''
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/types.h>
#include <fcntl.h>
#define ROCKBOX_DIR "/.rockbox"
#define HZ 100
#define MENU_ATTACHED_USB 313
#define LANG_ACCESSIBILITY_UNLOCK_ANY_BUTTON 101
#define LANG_ACCESSIBILITY_LOCKED_BUTTONS 102
#define LANG_ERROR_WRITING_CONFIG 103
#define LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT 104
#define LANG_ACCESSIBILITY_AUTOLOCK_LEGACY 105
#define LANG_OFF 106
#define UNIT_SEC 4
#define TALK_ID(number, unit) ((int32_t)((uint32_t)(unit) << 27 | (uint32_t)(number)))
#define ARRAYLEN(value) (sizeof(value) / sizeof(*(value)))
#define ID2P(value) (value)
#define str(value) ((const char *)(uintptr_t)(value))
struct opt_items { const unsigned char *string; int32_t voice_id; };
enum optiontype { RB_INT };
static char disk[128], temporary[128];
static size_t disk_size, read_offset, temporary_size;
static bool disk_exists, temporary_exists, choice;
static int fault, writes, errors, menu_usb, reads, read_limit, write_limit;
static int fault_after;
static int timeout_choice, timeout_initial, timeout_count;
static int open(const char *path, int flags, ...)
{
    if (!strcmp(path, ROCKBOX_DIR "/accessibility-lock.cfg"))
    {
        if (!disk_exists || fault == 1) return -1;
        read_offset = 0;
        return 1;
    }
    if (strcmp(path, ROCKBOX_DIR "/accessibility-lock.cfg.tmp") || !(flags & O_TRUNC)) return -1;
    if (fault == 3) return -1;
    temporary_exists = true;
    temporary_size = 0;
    return 2;
}
static ssize_t read(int descriptor, void *data, size_t capacity)
{
    (void)descriptor; ++reads;
    if (fault == 2) return -1;
    if (capacity > disk_size - read_offset) capacity = disk_size - read_offset;
    if (read_limit > 0 && capacity > (size_t)read_limit) capacity = read_limit;
    memcpy(data, disk + read_offset, capacity);
    read_offset += capacity;
    return capacity;
}
static ssize_t write(int descriptor, const void *data, size_t size)
{
    (void)descriptor; ++writes;
    if (fault == 4 && (fault_after < 0 || writes > fault_after)) return -1;
    if (fault == 5) return 0;
    if (write_limit > 0 && size > (size_t)write_limit) size = write_limit;
    memcpy(temporary + temporary_size, data, size);
    temporary_size += size;
    return size;
}
static int fsync(int descriptor) { (void)descriptor; return fault == 6 ? -1 : 0; }
static int close(int descriptor)
{ return (descriptor == 1 && fault == 9) || (descriptor == 2 && fault == 7) ? -1 : 0; }
static int rename(const char *source, const char *target)
{
    if (strcmp(source, ROCKBOX_DIR "/accessibility-lock.cfg.tmp") ||
        strcmp(target, ROCKBOX_DIR "/accessibility-lock.cfg") || fault == 8) return -1;
    memcpy(disk, temporary, temporary_size);
    disk_size = temporary_size;
    disk_exists = true; temporary_exists = false;
    return 0;
}
static int remove(const char *path)
{ (void)path; temporary_exists = false; return 0; }
static bool set_bool(const char *title, bool *value)
{ (void)title; *value = choice; return menu_usb != 0; }
static bool set_option(const char *title, int *value, enum optiontype type,
                       const struct opt_items *items, int count, void *callback)
{
    (void)type; (void)callback;
    if (title != str(LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT) || count < 12 || count > 13 ||
        items[0].voice_id != LANG_ACCESSIBILITY_AUTOLOCK_LEGACY || items[1].voice_id != LANG_OFF)
        __builtin_abort();
    timeout_initial = *value; timeout_count = count;
    if (timeout_choice >= 0) *value = timeout_choice;
    return menu_usb != 0;
}
static void splash(int ticks, int label)
{ (void)ticks; if (label != LANG_ERROR_WRITING_CONFIG) __builtin_abort(); ++errors; }
'''


PERSISTENCE_CASES = r'''
static void restart(void)
{
    screen_lock_policy_loaded = false;
    unlock_any_button = locked_physical_buttons = false;
    screen_autolock_timeout = -1;
}
static void reset(void)
{
    restart();
    memset(disk, 0, sizeof(disk));
    disk_exists = temporary_exists = false;
    disk_size = temporary_size = 0;
    fault = writes = errors = reads = menu_usb = read_limit = write_limit = 0;
    timeout_choice = -1;
    fault_after = -1;
}
static int persist_case(void)
{
    reset();
    CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
    CHECK(!disk_exists && writes == 0);
    for (int unlocked = 0; unlocked < 2; ++unlocked)
        for (int physical = 0; physical < 2; ++physical)
        {
            reset();
            choice = true;
            CHECK(accessibility_screen_unlock_any_button_menu() == 0);
            choice = unlocked;
            CHECK(accessibility_screen_unlock_any_button_menu() == 0);
            choice = physical;
            CHECK(accessibility_screen_locked_buttons_menu() == 0);
            CHECK(!temporary_exists && errors == 0);
            char expected[128];
            int length = snprintf(expected, sizeof(expected),
                "RBACCESSIBILITY-LOCK:2\nunlock-button:%d\nphysical-buttons:%d\ntimeout:-1\n", unlocked, physical);
            CHECK(disk_exists && disk_size == (size_t)length && !memcmp(disk, expected, length));
            restart();
            CHECK(accessibility_screen_unlock_any_button() == (bool)unlocked);
            int previous_reads = reads;
            CHECK(accessibility_screen_locked_buttons() == (bool)physical && reads == previous_reads);
        }
    return 0;
}
static int fault_case(void)
{
    for (int failure = 3; failure <= 8; ++failure)
    {
        reset(); fault = failure; choice = true;
        CHECK(accessibility_screen_unlock_any_button_menu() == 0);
        CHECK(!disk_exists && !temporary_exists && errors == 1);
        CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
        reset();
        choice = true;
        CHECK(accessibility_screen_unlock_any_button_menu() == 0);
        char original[128];
        memcpy(original, disk, disk_size);
        size_t original_size = disk_size;
        fault = failure;
        CHECK(accessibility_screen_locked_buttons_menu() == 0);
        CHECK(errors == 1 && !temporary_exists);
        CHECK(accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
        CHECK(disk_size == original_size && !memcmp(disk, original, disk_size));
        fault = 0;
        CHECK(accessibility_screen_locked_buttons_menu() == 0);
        CHECK(accessibility_screen_locked_buttons());
    }
    reset();
    read_limit = write_limit = 1;
    choice = true;
    CHECK(accessibility_screen_unlock_any_button_menu() == 0);
    restart();
    CHECK(accessibility_screen_unlock_any_button() && reads > 2 && writes > 2);
    for (int failure = 1; failure <= 9; ++failure)
        if (failure == 1 || failure == 2 || failure == 9)
        {
            restart(); fault = failure;
            CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
        }
    reset(); choice = true; menu_usb = 1;
    CHECK(accessibility_screen_unlock_any_button_menu() == MENU_ATTACHED_USB);
    CHECK(accessibility_screen_locked_buttons_menu() == MENU_ATTACHED_USB);
    CHECK(!disk_exists && writes == 0 && !accessibility_screen_unlock_any_button());
    reset(); choice = false;
    CHECK(accessibility_screen_unlock_any_button_menu() == 0);
    CHECK(accessibility_screen_locked_buttons_menu() == 0);
    CHECK(!disk_exists && writes == 0 && errors == 0);
    return 0;
}
static int corrupt_case(void)
{
    reset();
    const char *legacy = "RBACCESSIBILITY-LOCK:1\nunlock-button:1\nphysical-buttons:1\n";
    memcpy(disk, legacy, strlen(legacy)); disk_size = strlen(legacy); disk_exists = true;
    char original[128]; size_t original_size = disk_size;
    memcpy(original, disk, disk_size);
    for (size_t length = 0; length < original_size; ++length)
    {
        restart(); disk_size = length;
        CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
    }
    disk_size = original_size + 1; disk[original_size] = '\n'; restart();
    CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
    for (size_t offset = 0; offset < original_size; ++offset)
        for (int value = 0; value < 256; ++value)
        {
            if (value == original[offset] ||
                (original[offset] == '1' && value == '0' &&
                 (offset == sizeof("RBACCESSIBILITY-LOCK:1\nunlock-button:") - 1 ||
                  offset == sizeof("RBACCESSIBILITY-LOCK:1\nunlock-button:0\nphysical-buttons:") - 1))) continue;
            memcpy(disk, original, original_size); disk_size = original_size;
            disk[offset] = value; restart();
            CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
        }
    return 0;
}

static int timeout_case(void)
{
    const char *legacy = "RBACCESSIBILITY-LOCK:1\nunlock-button:1\nphysical-buttons:1\n";
    reset(); memcpy(disk, legacy, strlen(legacy)); disk_size = strlen(legacy); disk_exists = true;
    CHECK(accessibility_screen_autolock_timeout() == -1 && writes == 0);
    CHECK(accessibility_screen_unlock_any_button() && accessibility_screen_locked_buttons());
    CHECK(accessibility_screen_autolock_menu() == 0 && writes == 0 && timeout_initial == 0);
    CHECK(disk_size == strlen(legacy) && !memcmp(disk, legacy, disk_size));
    fault = 8; timeout_choice = 5;
    CHECK(accessibility_screen_autolock_menu() == 0 && errors == 1);
    CHECK(accessibility_screen_autolock_timeout() == -1);
    CHECK(accessibility_screen_unlock_any_button() && accessibility_screen_locked_buttons());
    CHECK(disk_size == strlen(legacy) && !memcmp(disk, legacy, disk_size));
    fault = errors = 0;
    timeout_choice = 5;
    CHECK(accessibility_screen_autolock_menu() == 0 && accessibility_screen_autolock_timeout() == 30);
    CHECK(accessibility_screen_unlock_any_button() && accessibility_screen_locked_buttons());
    restart(); CHECK(accessibility_screen_autolock_timeout() == 30);
    int durations[] = {-1, 0, 5, 10, 15, 30, 45, 60, 120, 180, 300, 600};
    for (unsigned int index = 0; index < ARRAYLEN(durations); ++index)
    {
        timeout_choice = index;
        CHECK(accessibility_screen_autolock_menu() == 0);
        restart(); CHECK(accessibility_screen_autolock_timeout() == durations[index]);
        CHECK(accessibility_screen_unlock_any_button() && accessibility_screen_locked_buttons());
    }
    for (int seconds = 1; seconds <= 600; ++seconds)
    {
        reset(); disk_exists = true;
        disk_size = snprintf(disk, sizeof(disk),
            "RBACCESSIBILITY-LOCK:2\nunlock-button:1\nphysical-buttons:0\ntimeout:%d\n", seconds);
        CHECK(accessibility_screen_autolock_timeout() == seconds && writes == 0);
        CHECK(accessibility_screen_autolock_menu() == 0 && writes == 0);
        CHECK(accessibility_screen_autolock_timeout() == seconds);
        CHECK(timeout_count == 12 || timeout_count == 13);
    }
    const char *invalid[] = {"", "-2", "601", "99999999999999999999", "+1", "00", "01", " 1", "1 ", "1\nextra", "1\r", "-0", "1x"};
    for (unsigned int index = 0; index < ARRAYLEN(invalid); ++index)
    {
        reset(); disk_exists = true;
        disk_size = snprintf(disk, sizeof(disk),
            "RBACCESSIBILITY-LOCK:2\nunlock-button:1\nphysical-buttons:1\ntimeout:%s\n", invalid[index]);
        CHECK(accessibility_screen_autolock_timeout() == -1 && writes == 0);
        CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
    }
    for (int failure = 3; failure <= 8; ++failure)
    {
        reset(); timeout_choice = 5;
        CHECK(accessibility_screen_autolock_menu() == 0 && accessibility_screen_autolock_timeout() == 30);
        char original[128]; size_t length = disk_size; memcpy(original, disk, length);
        fault = failure; timeout_choice = 7;
        CHECK(accessibility_screen_autolock_menu() == 0 && errors == 1);
        CHECK(accessibility_screen_autolock_timeout() == 30 && !temporary_exists);
        CHECK(disk_size == length && !memcmp(disk, original, length));
    }
    const char *complete = "RBACCESSIBILITY-LOCK:2\nunlock-button:1\nphysical-buttons:1\ntimeout:600\n";
    for (size_t length = 0; length < strlen(complete); ++length)
    {
        reset(); disk_exists = true; disk_size = length;
        memcpy(disk, complete, length);
        CHECK(accessibility_screen_autolock_timeout() == -1 && writes == 0);
        CHECK(!accessibility_screen_unlock_any_button() && !accessibility_screen_locked_buttons());
    }
    for (size_t failure = 0; failure < strlen(complete); ++failure)
    {
        reset(); choice = true;
        CHECK(accessibility_screen_unlock_any_button_menu() == 0);
        CHECK(accessibility_screen_locked_buttons_menu() == 0);
        char original[128]; size_t length = disk_size; memcpy(original, disk, length);
        writes = 0; write_limit = 1; fault = 4; fault_after = failure; timeout_choice = 11;
        CHECK(accessibility_screen_autolock_menu() == 0 && errors == 1 && !temporary_exists);
        CHECK(accessibility_screen_autolock_timeout() == -1);
        CHECK(accessibility_screen_unlock_any_button() && accessibility_screen_locked_buttons());
        CHECK(disk_size == length && !memcmp(disk, original, length));
    }
    reset(); timeout_choice = 5; menu_usb = 1;
    CHECK(accessibility_screen_autolock_menu() == MENU_ATTACHED_USB);
    CHECK(!disk_exists && !writes && accessibility_screen_autolock_timeout() == -1);
    reset(); timeout_choice = 0;
    CHECK(accessibility_screen_autolock_menu() == 0 && !disk_exists && !writes);
    return 0;
}
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    int result = !strcmp(argv[1], "persist") ? persist_case() :
        !strcmp(argv[1], "fault") ? fault_case() :
        !strcmp(argv[1], "timeout") ? timeout_case() :
        !strcmp(argv[1], "corrupt") ? corrupt_case() : 2;
    if (!result) printf("{\"checks\":%d}\n", checks);
    return result;
}
'''


def action_source(inputs, variant="touch"):
    source = harness(inputs, variant).replace("int main(int argc, char **argv)",
                                             "int legacy_main(int argc, char **argv)")
    source = source.replace("static intptr_t queued_data;", "static intptr_t queued_data;\n" + QUEUE)
    for name, replacement in (
        ("accessibility_screen_unlock_any_button", "bool accessibility_screen_unlock_any_button(void) { return unlock_policy; }"),
        ("accessibility_screen_locked_buttons", "bool accessibility_screen_locked_buttons(void) { return passthrough_policy; }"),
        ("button_queue_count", "int button_queue_count(void) { return policy_queue_count; }"),
        ("button_clear_queue_preserve_events", "void button_clear_queue_preserve_events(void) { policy_clear_queue(); }"),
        ("button_queue_post", "void button_queue_post(long button, intptr_t data) { policy_push(button, data); }"),
    ):
        source = source.replace(function(source, name).strip(), replacement)
    source = source.replace("    last_timeout = timeout; ++button_polls;",
        "    if (policy_queue_count) return policy_pop();\n    last_timeout = timeout; ++button_polls;")
    return source


def persistence_source():
    source = (ROOT / "apps/accessibility_screen.c").read_text(encoding="utf-8")
    start = source.index("#define SCREEN_LOCK_POLICY_FILE")
    end = source.index("\n#endif", start)
    generated = PERSISTENCE + source[start:end]
    generated = generated.replace("static int open(", "static int policy_open(").replace("static int rename(", "static int policy_rename(").replace("static int remove(", "static int policy_remove(")
    return generated.replace("#define ROCKBOX_DIR", "#define open policy_open\n#define rename policy_rename\n#define remove policy_remove\n#define ROCKBOX_DIR")


def native_source(inputs):
    source = action_source(inputs)
    action = inputs["apps/action.c"]
    keymap = without_includes((ROOT / "apps/keymaps/keymap-hibyr1.c").read_text(encoding="utf-8"))
    keymap += r'''
static bool native_saw_locked_context;
const struct button_mapping *get_context_mapping(int context)
{
    native_saw_locked_context |= (context & CONTEXT_LOCKED) != 0;
    return target_get_context_mapping(context);
}
'''
    mapping = balanced_definition(source,
        r"^const struct button_mapping \*get_context_mapping\([^;{}]*\)\s*\{")
    source = source.replace(mapping, keymap)
    lookup = ("bool is_keys_locked(void);\n"
              "static inline bool has_flag(unsigned int value, unsigned int flag);\n"
              "bool accessibility_screen_locked_buttons(void);\n")
    lookup += function(action, "action_code_worker")
    lookup += function(action, "get_next_context") + function(action, "action_code_lookup")
    source = source.replace(function(source, "action_code_lookup").strip(), lookup)
    source = "#define DISABLE_ACTION_REMAP\n#define HAVE_VOLUME_IN_LIST\n" + source
    source += function(action, "is_keys_locked")
    return source


NATIVE_CASES = r'''
int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    const int contexts[] = { CONTEXT_STD, CONTEXT_WPS, CONTEXT_KEYBOARD, CONTEXT_YESNOSCREEN };
    const int expected[] = { ACTION_STD_OK, ACTION_WPS_PLAY, ACTION_KBD_SELECT, ACTION_YESNO_ACCEPT };
    for (unsigned int selected = 0; selected < sizeof(contexts) / sizeof(*contexts); ++selected)
    {
        reset_lock(); unlock_policy = false; passthrough_policy = true;
        int context = contexts[selected] | ALLOW_SOFTLOCK;
        action_last.context = context;
        do_key_lock(true); transition_count = 0;
        native_saw_locked_context = false;
        CHECK(feed(BUTTON_POWER, 1, context, 0) == ACTION_NONE);
        CHECK(feed(BUTTON_POWER | BUTTON_REL, 1, context, 0) == expected[selected]);
        CHECK(action_last.keys_locked && transition_count == 0);
        CHECK(!native_saw_locked_context);
        passthrough_policy = false;
        CHECK(feed(BUTTON_POWER, 1, context, 0) == ACTION_REDRAW);
        CHECK(native_saw_locked_context && action_last.keys_locked);
        feed(BUTTON_POWER | BUTTON_REL, 1, context, 0);
        passthrough_policy = true;
        unlock_policy = true;
        CHECK(feed(BUTTON_POWER, 1, context, 0) == ACTION_REDRAW);
        CHECK(feed(BUTTON_POWER | BUTTON_REPEAT, 1, context, 0) == ACTION_NONE);
        CHECK(feed(BUTTON_POWER | BUTTON_REL, 1, context, 0) == ACTION_NONE);
        CHECK(!action_last.keys_locked && transition_count == 1);
    }
    printf("{\"checks\":%d}\n", checks);
    return 0;
}
'''


FIRMWARE = r'''
#define HAVE_SW_POWEROFF
#define CONFIG_CHARGING 0
#define CONFIG_PLATFORM 0
#define PLATFORM_NATIVE 1
#define REPEAT_START (30*HZ/100)
#define REPEAT_INTERVAL_START (16*HZ/100)
#define REPEAT_INTERVAL_FINISH (5*HZ/100)
#define REPEAT_INTERVAL_TOUCH (4*HZ/100)
static int raw_button, lastbtn, lastdata, shutdown_requests;
static bool enable_sw_poweroff = true;
static void button_remote_post(void) {}
static int button_read(int *data) { *data = 0; return raw_button; }
static void check_audio_peripheral_state(void) {}
bool button_queue_try_post(long button, int data) { policy_push(button, data); return true; }
static void reset_poweroff_timer(void) {}
static void sys_poweroff(void)
{
    if (!shutdown_requests++) policy_push(SYS_POWEROFF, 987);
}
'''


POWER_CASE = r'''
int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    reset_lock(); unlock_policy = true; passthrough_policy = false;
    do_key_lock(true); transition_count = 0;
    raw_button = BUTTON_POWER;
    button_tick();
    CHECK(get_action(CONTEXT_STD | ALLOW_SOFTLOCK, 0) == ACTION_REDRAW);
    CHECK(!action_last.keys_locked && transition_count == 1);
    bool received_shutdown = false;
    for (int tick = 0; tick < 1000; ++tick)
    {
        ++current_tick;
        button_tick();
        while (policy_queue_count)
        {
            int action = get_action(CONTEXT_STD | ALLOW_SOFTLOCK, 0);
            CHECK(action == ACTION_NONE || action == SYS_POWEROFF);
            if (action == SYS_POWEROFF)
            {
                received_shutdown = true;
                CHECK(queued_data == 987);
            }
        }
    }
    CHECK(received_shutdown && shutdown_requests > 0);
    CHECK(physical_calls == 0 && custom_clicks == 0);
    raw_button = BUTTON_NONE;
    button_tick();
    CHECK(get_action(CONTEXT_STD | ALLOW_SOFTLOCK, 0) == ACTION_NONE);
    printf("{\"checks\":%d,\"shutdown_requests\":%d}\n", checks, shutdown_requests);
    return 0;
}
'''


def recognizer_source(inputs):
    source = native_source(inputs)
    module = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
    module = module[:module.rfind("\n#else")]
    button_header = without_includes((ROOT / "apps/accessibility_buttons.h").read_text(encoding="utf-8"))
    button_code = without_includes((ROOT / "apps/accessibility_buttons.c").read_text(encoding="utf-8"))
    enumeration = re.search(r"enum accessibility_action\s*\{.*?\};", module, re.DOTALL)[0]
    prelude = button_header + button_code + enumeration + r'''
static struct { uint8_t buttons[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT];
    uint8_t button_launch[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT];
    uint8_t playback_buttons[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT];
    uint8_t playback_launch[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT]; } active_config;
static struct accessibility_buttons button_recognizers[ACCESSIBILITY_BUTTON_COUNT];
static bool initialized = true, physical_context_valid, physical_repeat;
static bool physical_locked;
static int physical_context, physical_contact, physical_blocked;
static const int physical_buttons[ACCESSIBILITY_BUTTON_COUNT] = {
    BUTTON_POWER, BUTTON_PLAY, BUTTON_NEXT, BUTTON_VOL_UP, BUTTON_VOL_DOWN };
static void accessibility_check_trial(void) {}
static int do_global_volume(int action) { return action; }
static bool accessibility_repeat_safe(unsigned int mapping, int context)
{ (void)context; return mapping == ACCESSIBILITY_ACTION_VOLUP || mapping == ACCESSIBILITY_ACTION_VOLDOWN; }
static int accessibility_repeat_result(int action, bool repeat, int context)
{ (void)repeat; (void)context; return action; }
static void accessibility_queue_launch(unsigned int target) { (void)target; }
static int accessibility_action_for(unsigned int mapping, int context)
{
    (void)context;
    switch (mapping)
    {
        case ACCESSIBILITY_ACTION_OK: return ACTION_STD_OK;
        case ACCESSIBILITY_ACTION_HOME: return ACTION_STD_MENU;
        case ACCESSIBILITY_ACTION_CONTEXT: return ACTION_STD_CONTEXT;
        case ACCESSIBILITY_ACTION_BACK: return ACTION_STD_CANCEL;
        case ACCESSIBILITY_ACTION_LOCK: return ACTION_STD_KEYLOCK;
        default: return ACTION_NONE;
    }
}
int accessibility_default_button_action(int button, int context, bool held_release);
'''
    source = source.replace("static action_last_t action_last;", prelude + "\nstatic action_last_t action_last;")
    implementation = balanced_definition(module,
        r"^static uint32_t accessibility_milliseconds\([^;{}]*\)\s*\{") + "\n"
    implementation += function(module, "accessibility_playback_context")
    implementation += balanced_definition(module,
        r"^static const uint8_t \(\*physical_mappings\b[^{;]*\{") + "\n"
    implementation += function(module, "accessibility_cancel_buttons")
    implementation += function(module, "physical_override")
    implementation += function(module, "physical_action").replace("physical_action", "recognized_physical_action")
    implementation += function(module, "accessibility_handle_button").replace("physical_action(", "recognized_physical_action(")
    source = source.replace(function(source, "accessibility_handle_button").strip(), implementation)
    source = source.replace(function(source, "accessibility_reset").strip(),
        "void accessibility_reset(void) { ++reset_calls; pending_timer = false; "
        "for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button) "
        "accessibility_buttons_reset(&button_recognizers[button]); "
        "physical_context_valid = false; physical_contact = physical_blocked = 0; }")
    source = source.replace(function(source, "accessibility_button_is_repeat").strip(),
                            function(module, "accessibility_button_is_repeat"))
    source += function(inputs["apps/action.c"], "accessibility_default_button_action")
    inactive_service = r'''
#include "hiby_bluetooth_service.h"
static unsigned int bluetooth_notification_calls, bluetooth_timeout_calls;
void hiby_bluetooth_service_process_notifications(void)
{ ++bluetooth_notification_calls; }
int hiby_bluetooth_service_adjust_timeout(int timeout)
{ ++bluetooth_timeout_calls; return timeout; }
'''
    return "#define HIBY_R1\n" + inactive_service + source


RECOGNIZER_CASES = r'''
int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    for (int clicks = 1; clicks <= 3; ++clicks)
    {
        reset_lock(); unlock_policy = false; passthrough_policy = true;
        memset(active_config.buttons, ACCESSIBILITY_ACTION_SYSTEM, sizeof(active_config.buttons));
        active_config.buttons[2][ACCESSIBILITY_BUTTON_SINGLE] = ACCESSIBILITY_ACTION_OK;
        active_config.buttons[2][ACCESSIBILITY_BUTTON_DOUBLE] = ACCESSIBILITY_ACTION_HOME;
        active_config.buttons[2][ACCESSIBILITY_BUTTON_TRIPLE] = ACCESSIBILITY_ACTION_CONTEXT;
        active_config.buttons[2][ACCESSIBILITY_BUTTON_HOLD] = ACCESSIBILITY_ACTION_BACK;
        for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
            CHECK(accessibility_buttons_init(&button_recognizers[button], 500));
        physical_context_valid = false;
        do_key_lock(true); transition_count = 0;
        for (int click = 0; click < clicks; ++click)
        {
            CHECK(feed(BUTTON_NEXT, 1, context, 0) == ACTION_NONE);
            CHECK(feed(BUTTON_TOUCHSCREEN, 1, context, 0) == ACTION_NONE);
            CHECK(feed(BUTTON_TOUCHSCREEN | BUTTON_REL, 1, context, 0) == ACTION_NONE);
            int result = feed(BUTTON_NEXT | BUTTON_REL, 1, context, 0);
            CHECK(result == (click == 2 ? ACTION_STD_CONTEXT : ACTION_NONE));
        }
        int expected = clicks == 1 ? ACTION_STD_OK : clicks == 2 ? ACTION_STD_MENU : ACTION_NONE;
        CHECK(feed(BUTTON_NONE, 31, context, 0) == expected);
        CHECK(action_last.keys_locked && transition_count == 0);
        CHECK(feed(BUTTON_NEXT, 1, context, 0) == ACTION_NONE);
        CHECK(feed(BUTTON_NONE, 51, context, 0) == ACTION_STD_CANCEL);
        CHECK(feed(BUTTON_NEXT | BUTTON_REL, 1, context, 0) == ACTION_NONE);
        CHECK(action_last.keys_locked && transition_count == 0);
        unlock_policy = true;
        CHECK(feed(BUTTON_NEXT, 1, context, 0) == ACTION_REDRAW);
        CHECK(feed(BUTTON_NONE, 51, context, 0) == ACTION_NONE);
        CHECK(feed(BUTTON_NEXT | BUTTON_REL, 1, context, 0) == ACTION_NONE);
        CHECK(!action_last.keys_locked && transition_count == 1);
        CHECK(bluetooth_notification_calls > 0);
        CHECK(bluetooth_notification_calls == bluetooth_timeout_calls);
    }
    printf("{\"checks\":%d}\n", checks);
    return 0;
}
'''


class AccessibilityLockPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = project_materials_root(ROOT) / "r1-empty-radio-20261017" / "screen-lock" / (
            "lock-policy-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.workspace.mkdir(parents=True)
        cls.inputs = {path: (ROOT / path).read_text(encoding="utf-8") for path in INPUTS}
        cls.runs = []
        cls.binaries = {}
        cls.test_methods = 0
        cls.failed_tests = []
        cls.hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
            "apps/action.c", "apps/accessibility_screen.c", "apps/accessibility_screen.h",
            "apps/accessibility.c", "apps/accessibility_buttons.c", "apps/accessibility_buttons.h",
            "apps/hiby_bluetooth_service.h", "apps/hiby_bluetooth.h",
            "firmware/target/hosted/hiby/bluetooth-hiby.h",
            "apps/keymaps/keymap-hibyr1.c", "firmware/drivers/button.c",
            "tools/tests/test_accessibility_lock_policy.py")}

    @classmethod
    def tearDownClass(cls):
        report = {"source_project": str(ROOT), "source_hashes": cls.hashes, "runs": cls.runs,
                  "passed": not cls.failed_tests and
                      cls.test_methods == len(unittest.defaultTestLoader.getTestCaseNames(cls)) and
                      bool(cls.runs) and all(run["passed"] for run in cls.runs),
                  "test_methods": cls.test_methods, "failed_tests": cls.failed_tests,
                  "hardware_tested": False, "full_build": False, "host_audio_used": False,
                  "global_input_used": False}
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        self.__class__.test_methods += 1
        prefix = self.__class__.__module__ + "." + self.__class__.__name__ + "."
        result = self._outcome.result
        self.__class__.failed_tests = [case.id() for case, _ in result.failures + result.errors
                                      if case.id().startswith(prefix)]

    def run_case(self, name, source, scenario):
        if name not in self.binaries:
            generated = self.workspace / (name + ".c")
            binary = self.workspace / name
            generated.write_text(source, encoding="utf-8")
            command = ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                       "-Wno-unused-function", "-Wno-unused-const-variable", "-pedantic",
                       "-I", str(ROOT / "apps"),
                       "-I", str(ROOT / "firmware/target/hosted/hiby")]
            if os.environ.get("ROCKBOX_SCREEN_SANITIZERS", "1") != "0":
                command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            command += [str(generated), "-o", str(binary)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (self.workspace / (name + "-compile.log")).write_text(result.stdout + result.stderr, encoding="utf-8")
            self.runs.append({"kind": "compile", "name": name, "command": command, "passed": result.returncode == 0})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.binaries[name] = binary
        result = subprocess.run([str(self.binaries[name]), scenario], capture_output=True,
                                text=True, timeout=20, env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1"})
        (self.workspace / (name + "-" + scenario + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        run = {"kind": "runtime", "name": name, "scenario": scenario, "passed": result.returncode == 0}
        if result.returncode == 0:
            run.update(json.loads(result.stdout))
        self.runs.append(run)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_real_action_unlock_and_contact_consumption(self):
        for scenario in ("unlock", "fresh", "passthrough", "deferred", "queued-events", "context-escape", "explicit-policies"):
            with self.subTest(scenario=scenario):
                self.run_case("action", action_source(self.inputs) + ACTION_CASES, scenario)

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_atomic_persistence_corruption_and_error_paths(self):
        prefix = '#include <stdlib.h>\nstatic int checks;\n#define CHECK(value) do { ++checks; if (!(value)) { fprintf(stderr, "line %d: %s\\n", __LINE__, #value); return 1; } } while (0)\n'
        generated = prefix + persistence_source() + PERSISTENCE_CASES
        for scenario in ("persist", "fault", "corrupt", "timeout"):
            with self.subTest(scenario=scenario):
                self.run_case("persistence", generated, scenario)

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_failed_duration_save_preserves_real_action_deadline(self):
        source = action_source(self.inputs)
        source = source.replace(function(source, "accessibility_screen_autolock_timeout").strip(),
                                "int accessibility_screen_autolock_timeout(void);")
        for name in ("accessibility_screen_unlock_any_button", "accessibility_screen_locked_buttons"):
            source = source.replace(function(source, name).strip(), "bool " + name + "(void);")
        policy = persistence_source().replace("static void splash(", "static void policy_splash(")
        policy = policy.replace("#define ROCKBOX_DIR", "#define splash policy_splash\n#define ROCKBOX_DIR")
        source += policy + r'''
int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    (void)unlock_policy; (void)passthrough_policy;
    const int context = CONTEXT_STD | ALLOW_SOFTLOCK;
    reset_lock();
    screen_lock_policy_loaded = false;
    screen_autolock_timeout = -1;
    fault_after = -1;
    action_autosoftlock_init();
    timeout_choice = 2;
    CHECK(accessibility_screen_autolock_menu() == 0 && accessibility_screen_autolock_timeout() == 5);
    CHECK(feed(BUTTON_NONE, HZ, context, 0) == ACTION_NONE);
    long activity = action_last.inactivity_tick;
    fault = 8; timeout_choice = 5;
    CHECK(accessibility_screen_autolock_menu() == 0 && errors == 1);
    CHECK(accessibility_screen_autolock_timeout() == 5 && !temporary_exists);
    CHECK(action_last.inactivity_tick == activity);
    CHECK(feed(BUTTON_NONE, ULONG_MAX, context, TIMEOUT_BLOCK) == ACTION_REDRAW);
    CHECK(last_timeout == 4 * HZ && action_last.keys_locked && transition_count == 1);
    printf("{\"checks\":%d}\n", checks);
    return 0;
}
'''
        self.run_case("save-deadline", source, "save-deadline")

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_real_native_keymap_keeps_touch_locked_and_unlock_contact_inert(self):
        self.run_case("native", native_source(self.inputs) + NATIVE_CASES, "native")

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_real_physical_recognizer_single_double_triple_and_hold(self):
        self.run_case("recognizer", recognizer_source(self.inputs) + RECOGNIZER_CASES, "recognizer")

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_raw_firmware_power_shutdown_survives_consumed_unlock_contact(self):
        firmware = (ROOT / "firmware/drivers/button.c").read_text(encoding="utf-8")
        source = action_source(self.inputs, "no-backlight") + FIRMWARE
        source += function(firmware, "button_tick") + POWER_CASE
        self.run_case("firmware-power", source, "power")

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_firmware_touch_wake_bypasses_first_press_filter_without_lighting_screen(self):
        firmware = (ROOT / "firmware/drivers/button.c").read_text(encoding="utf-8")
        source = action_source(self.inputs, "touch")
        source = source.replace("bool touchscreen_wake_filter_needed(void) { return false; }",
            "static bool wake_filter = true;\nbool touchscreen_wake_filter_needed(void) { return wake_filter; }")
        source += FIRMWARE + r'''
static int first_key_filters;
static bool first_key_filter(int button, int data)
{ (void)button; (void)data; ++first_key_filters; return true; }
static bool (*keypress_filter_fn)(int, int) = first_key_filter;
static void buttonlight_on(void) { }
'''
        source += function(firmware, "button_tick") + r'''
int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    reset_lock(); backlight_lit = false;
    raw_button = BUTTON_TOUCHSCREEN;
    button_tick();
    CHECK(policy_queue_count == 1 && !first_key_filters && !backlight_lit);
    CHECK(policy_pop() == BUTTON_TOUCHSCREEN);
    for (int tick = 0; tick < 12; ++tick)
    {
        ++current_tick;
        button_tick();
        CHECK(!first_key_filters && !backlight_lit);
        while (policy_queue_count)
            CHECK(policy_pop() == (BUTTON_TOUCHSCREEN | BUTTON_REPEAT));
    }
    raw_button = BUTTON_NONE;
    button_tick();
    CHECK(policy_queue_count == 1 && (policy_pop() & BUTTON_REL));
    wake_filter = false;
    raw_button = BUTTON_POWER;
    button_tick();
    CHECK(first_key_filters == 1 && backlight_lit);
    printf("{\"checks\":%d}\n", checks);
    return 0;
}
'''
        self.run_case("firmware-touch-wake", source, "touch-wake")

    @unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "POSIX C compiler required; run under WSL")
    def test_unsupported_header_stubs_do_not_link_to_policy(self):
        header = (ROOT / "apps/accessibility_screen.h").read_text(encoding="utf-8").replace('#include "config.h"', "")
        variants = {"no-touch": "#define HAVE_ESPEAK\n",
                    "no-espeak": "#define HAVE_TOUCHSCREEN\n",
                    "hold": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n#define HAS_BUTTON_HOLD\n",
                    "bootloader": "#define HAVE_TOUCHSCREEN\n#define HAVE_ESPEAK\n#define BOOTLOADER\n"}
        for variant, defines in variants.items():
            source = '#include <stdio.h>\n' + defines + header
            source += '\nint main(int argc, char **argv) { (void)argc; (void)argv; if (accessibility_screen_unlock_any_button() || accessibility_screen_locked_buttons() || accessibility_screen_unlock_any_button_menu() || accessibility_screen_locked_buttons_menu() || accessibility_screen_autolock_timeout() != -1 || accessibility_screen_autolock_menu()) return 1; puts("{\\"checks\\":6}"); return 0; }\n'
            with self.subTest(variant=variant):
                self.run_case("stub-" + variant, source, "stub")


if __name__ == "__main__":
    unittest.main()
