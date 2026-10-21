"""Compile the real accessibility manager and recognizer with a faultable core host."""

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
from project_materials import ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
NO_SCREEN_CURTAIN = bool(os.environ.get("ACCESSIBILITY_SETTINGS_NO_CURTAIN"))
NO_TAGCACHE = bool(os.environ.get("ACCESSIBILITY_SETTINGS_NO_TAGCACHE"))
VERSION_ACTION_LIMITS = {1: 10, 2: 14, 3: 14, 4: 15, 5: 16, 6: 18, 7: 21, 8: 21, 9: 21, 10: 21, 11: 26}


def without_includes(value):
    return re.sub(r'^\s*#include[^\n]*', '', value, flags=re.MULTILINE)


PREAMBLE = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <fcntl.h>
#define HAVE_TOUCHSCREEN
#define HAVE_ESPEAK
#ifndef ACCESSIBILITY_SETTINGS_NO_CURTAIN
#define HAVE_SCREEN_CURTAIN
#endif
#define HAVE_VOLUME_IN_LIST
#ifndef TEST_OTHER_TARGET
#define HIBY_R1
#endif
#define BUTTON_NONE 0
#define ARRAYLEN(values) (sizeof(values) / sizeof((values)[0]))
#define BUTTON_POWER 1
#define BUTTON_PLAY 8
#define BUTTON_NEXT 4
#define BUTTON_VOL_UP 16
#define BUTTON_VOL_DOWN 32
#define BUTTON_MAIN (BUTTON_POWER | BUTTON_PLAY | BUTTON_NEXT | BUTTON_VOL_UP | BUTTON_VOL_DOWN)
#define BUTTON_REL 0x2000000
#define BUTTON_REPEAT 0x4000000
#define SYS_EVENT 0x40000000
#define SYS_USB_CONNECTED (SYS_EVENT | 1)
#define SYS_POWEROFF (SYS_EVENT | 2)
#define SYS_BATTERY_UPDATE (SYS_EVENT | 3)
#define SYS_CHARGER_CONNECTED (SYS_EVENT | 11)
#define SYS_CHARGER_DISCONNECTED (SYS_EVENT | 12)
#define UNIT_PERCENT 1
#define UNIT_MS 2
#define UNIT_INT 3
#define SHOW_PLUGINS 1
#define KEYCLICK_SOURCE_PHYSICAL 1
#define KEYCLICK_SOURCE_GESTURE 2
#define KEYCLICK_SOURCE_BOTH 3
#define KEYCLICK_SOURCE_ALL 7
#define HZ 100
#define ROCKBOX_DIR "/.rockbox"
#define MAX_PATH 260
#define PLUGIN_DIR ROCKBOX_DIR "/rocks"
#define PLUGIN_APPS_DIR ROCKBOX_DIR "/rocks/apps"
#define MENU_ATTACHED_USB 313
#define PLUGIN_USB_CONNECTED 99
#define ID2P(value) (value)
#define STR(value) ((const unsigned char *)(uintptr_t)(value)), (value)
#define MENUITEM_STRINGLIST(name, ...) const struct menu_item_ex name = {0}
static long current_tick;
static struct { int touch_mode; bool keyclick_repeats; } global_settings;
static int touch_mode;
static int volume;
struct opt_items { const unsigned char *string; int32_t voice_id; };
enum optiontype { RB_INT, RB_BOOL };
enum yesno_res { YESNO_YES, YESNO_NO, YESNO_USB, YESNO_TMO };
struct text_message { const char **message_lines; int nb_lines; };
struct simplelist_info
{
    int selection;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
    int count;
    void *data;
};
static unsigned char disk[4097], temporary[4097];
static size_t disk_length, temporary_length, read_offset;
static bool disk_exists;
static bool temporary_exists, temporary_open, temporary_synced;
static unsigned char empty_disk[65], empty_temporary[65];
static size_t empty_disk_length, empty_temporary_length, empty_read_offset;
static bool empty_disk_exists, empty_temporary_exists, empty_temporary_open, empty_temporary_synced;
static int empty_fault;
static int syncs;
static int fault, read_chunk, write_chunk, opens, closes, writes, renames, removes;
static int answer, prompt_ticks, writes_at_prompt, pending_at_return, observed_mapping;
static uint32_t advance_ticks;
static int spoken[256], spoken_count, splash_label;
static bool spoken_enqueue[256];
static int selections[64], selection_count, selection_offset, option_choice;
static int option_count, option_initial_choice, option_voice_ids[32];
static int menu_voices, plugin_calls;
static char plugin_path[MAX_PATH];
static char selected_plugin[MAX_PATH];
static char spoken_file[MAX_PATH];
static int launcher_choice, browse_result;
static int default_button_calls;
static int gesture_clicks, shutdown_calls, launcher_calls, battery_value, spoken_value;
static int battery_reads, value_calls, value_unit;
static bool value_enqueue;
static bool curtain_active, speech_available;
static bool talk_menus_enabled(const void *settings) { (void)settings; return speech_available; }
static int curtain_set_calls;
static int time_calls;
static bool time_enqueue;
bool accessibility_speak_time(bool enqueue) { ++time_calls; time_enqueue = enqueue; return speech_available; }
static int date_calls, summary_calls;
static bool date_enqueue, summary_enqueue;
bool accessibility_speak_date(bool enqueue) { ++date_calls; date_enqueue = enqueue; return speech_available; }
void accessibility_speak_summary(bool enqueue) { ++summary_calls; summary_enqueue = enqueue; }
static int requested_screen, navigation_requests, navigation_cancels;
static bool navigation_pending, navigation_available;
bool root_menu_request_screen(int screen)
{
    ++navigation_requests;
    requested_screen = screen;
    navigation_pending = navigation_available;
    return navigation_available;
}
bool root_menu_navigation_pending(void) { return navigation_pending; }
void root_menu_cancel_navigation(void) { ++navigation_cancels; navigation_pending = false; }
static bool backlight_screen_curtain_active(void) { return curtain_active; }
static void backlight_set_screen_curtain(bool enabled) { ++curtain_set_calls; curtain_active = enabled; }
static bool tts_is_available(void) { return speech_available; }
static bool typing_active;
static int typing_dispatches;
struct touchevent;
#define ACCESSIBILITY_TYPING_ARROWS 2
static int typing_mode;
static bool typing_feedback_probe;
static int typing_feedback_target;
static bool typing_feedback_occupied;
void accessibility_explore_feedback(const void *owner, int target, bool occupied);
static bool accessibility_typing_active(void) { return typing_active; }
static int accessibility_typing_mode(void) { return typing_mode; }
static void accessibility_typing_cancel_touch(void) {}
static int accessibility_typing_handle_touch(const struct touchevent *event, int context)
{
    (void)event; (void)context;
    ++typing_dispatches;
    if (typing_feedback_probe)
        accessibility_explore_feedback(&typing_mode, typing_feedback_target, typing_feedback_occupied);
    return ACTION_TOUCHSCREEN;
}
struct menu_item_ex { int unused; };
const struct menu_item_ex info_menu = {0};
struct browse_context { int dirfilter; unsigned flags; char *title; const char *root; char *buf; size_t bufsize; };
#define BROWSE_DIRFILTER 1
#define BROWSE_SELECTONLY 2
#define BROWSE_NO_CONTEXT_MENU 4
#define BROWSE_SELECTED 8
static void keyclick_click_gesture_repeat(int action, bool repeat)
{ (void)action; if (!repeat || global_settings.keyclick_repeats) ++gesture_clicks; }
static int target_clicks, empty_clicks;
static void keyclick_click_touch_target(bool occupied, bool single_tap)
{ (void)single_tap; ++gesture_clicks; ++target_clicks; empty_clicks += !occupied; }
static unsigned int sensitivity_percent = 100;
static unsigned int accessibility_touch_distance(unsigned int normal)
{ return (normal * 100 + sensitivity_percent / 2) / sensitivity_percent; }
static int battery_level(void) { ++battery_reads; return battery_value; }
static void talk_value(int value, int unit, bool enqueue)
{ ++value_calls; spoken_value = value; value_unit = unit; value_enqueue = enqueue; }
static void sys_poweroff(void) { ++shutdown_calls; }
static int do_menu(const struct menu_item_ex *menu, void *selected, void *viewport, bool theme)
{ (void)menu; (void)selected; (void)viewport; (void)theme; ++launcher_calls; return launcher_choice; }
static int do_shortcut_menu(void *data) { (void)data; ++launcher_calls; return 0; }
static int rockbox_browse(struct browse_context *browse)
{
    ++launcher_calls;
    if (browse->buf && selected_plugin[0])
    {
        snprintf(browse->buf, browse->bufsize, "%s", selected_plugin);
        browse->flags |= BROWSE_SELECTED;
    }
    return browse_result;
}
static void action_wait_for_release(void) {}
static int talk_file_or_spell(const char *directory, const char *filename, const long *prefix, bool enqueue)
{ (void)directory; (void)prefix; (void)enqueue; snprintf(spoken_file, sizeof(spoken_file), "%s", filename); return 0; }
int accessibility_default_button_action(int button, int context, bool held_release)
{
    (void)button;
    ++default_button_calls;
    return context == CONTEXT_WPS && held_release ? ACTION_WPS_STOPSEEK : ACTION_STD_OK;
}
#ifdef TEST_UNSIGNED_STR
static unsigned char *str(int identifier)
{
    (void)identifier;
    return (unsigned char *)"label";
}
#else
static char *str(int identifier)
{
    (void)identifier;
    return "label";
}
#endif
static void talk_id(int identifier, bool enqueue)
{
    if (spoken_count < 256)
    {
        spoken_enqueue[spoken_count] = enqueue;
        spoken[spoken_count++] = identifier;
    }
}
static void adjust_volume(int steps) { volume += steps; }
static void splash(int ticks, int identifier) { (void)ticks; splash_label = identifier; }
static int mock_open(const char *path, int flags, ...)
{
    ++opens;
    if (flags == O_RDONLY && !strcmp(path, ROCKBOX_DIR "/empty-feedback.cfg"))
    {
        if (!empty_disk_exists)
            return -1;
        empty_read_offset = 0;
        return 5;
    }
    if (flags != O_RDONLY && !strcmp(path, ROCKBOX_DIR "/empty-feedback.cfg.tmp"))
    {
        if (empty_fault == 1)
            return -1;
        empty_temporary_length = 0;
        empty_temporary_exists = empty_temporary_open = true;
        empty_temporary_synced = false;
        return 6;
    }
    if (flags == O_RDONLY)
    {
        if (strcmp(path, ROCKBOX_DIR "/accessibility.cfg") || !disk_exists || fault == 1)
            return -1;
        read_offset = 0;
        return 3;
    }
    if (strcmp(path, ROCKBOX_DIR "/accessibility.cfg.tmp") || fault == 4)
        return -1;
    temporary_length = 0;
    temporary_exists = temporary_open = true;
    temporary_synced = false;
    return 4;
}
static ssize_t mock_read(int descriptor, void *buffer, size_t length)
{
    if (descriptor == 5)
    {
        size_t count = empty_disk_length - empty_read_offset;
        if (count > length) count = length;
        if (read_chunk && count > (size_t)read_chunk) count = read_chunk;
        memcpy(buffer, empty_disk + empty_read_offset, count);
        empty_read_offset += count;
        return count;
    }
    if (descriptor != 3 || fault == 2)
        return -1;
    size_t count = disk_length - read_offset;
    if (count > length) count = length;
    if (read_chunk && count > (size_t)read_chunk) count = read_chunk;
    memcpy(buffer, disk + read_offset, count);
    read_offset += count;
    return (ssize_t)count;
}
static ssize_t mock_write(int descriptor, const void *buffer, size_t length)
{
    ++writes;
    if (descriptor == 6)
    {
        if (empty_fault == 2 || (empty_fault == 4 && empty_temporary_length))
            return -1;
        if (empty_fault == 3)
            return 0;
        if (write_chunk && length > (size_t)write_chunk) length = write_chunk;
        if (length > sizeof(empty_temporary) - 1 - empty_temporary_length)
            return -1;
        memcpy(empty_temporary + empty_temporary_length, buffer, length);
        empty_temporary_length += length;
        return length;
    }
    if (descriptor != 4 || fault == 5 || (fault == 10 && temporary_length))
        return -1;
    if (fault == 6)
        return 0;
    if (write_chunk && length > (size_t)write_chunk) length = write_chunk;
    if (length > sizeof(temporary) - temporary_length)
        return -1;
    memcpy(temporary + temporary_length, buffer, length);
    temporary_length += length;
    return (ssize_t)length;
}
static int mock_fsync(int descriptor)
{
    ++syncs;
    if (descriptor == 6)
    {
        empty_temporary_synced = empty_temporary_open && empty_fault != 5;
        return empty_temporary_synced ? 0 : -1;
    }
    temporary_synced = descriptor == 4 && temporary_open && fault != 7;
    return temporary_synced ? 0 : -1;
}
static int mock_close(int descriptor)
{
    ++closes;
    if (descriptor == 6)
    {
        empty_temporary_open = false;
        return empty_fault == 6 ? -1 : 0;
    }
    if (descriptor == 4) temporary_open = false;
    return (descriptor == 3 && fault == 3) || (descriptor == 4 && fault == 8) ? -1 : 0;
}
static int mock_rename(const char *old_path, const char *new_path)
{
    ++renames;
    if (!strcmp(old_path, ROCKBOX_DIR "/empty-feedback.cfg.tmp") &&
        !strcmp(new_path, ROCKBOX_DIR "/empty-feedback.cfg"))
    {
        if (empty_fault == 7 || !empty_temporary_exists || empty_temporary_open ||
            !empty_temporary_synced)
            return -1;
        memcpy(empty_disk, empty_temporary, empty_temporary_length);
        empty_disk_length = empty_temporary_length;
        empty_disk_exists = true;
        empty_temporary_exists = false;
        return 0;
    }
    if (strcmp(old_path, ROCKBOX_DIR "/accessibility.cfg.tmp") ||
        strcmp(new_path, ROCKBOX_DIR "/accessibility.cfg") || fault == 9 ||
        !temporary_exists || temporary_open || !temporary_synced)
        return -1;
    memcpy(disk, temporary, temporary_length);
    disk_length = temporary_length;
    disk_exists = true;
    temporary_exists = false;
    return 0;
}
static int mock_remove(const char *path)
{
    ++removes;
    if (!strcmp(path, ROCKBOX_DIR "/empty-feedback.cfg.tmp"))
    {
        empty_temporary_exists = false;
        return 0;
    }
    if (strcmp(path, ROCKBOX_DIR "/accessibility.cfg.tmp")) return -1;
    temporary_exists = false;
    return 0;
}
#define open mock_open
#define read mock_read
#define write mock_write
#define fsync mock_fsync
#define close mock_close
#define rename mock_rename
#define remove mock_remove
static enum yesno_res gui_syncyesno_run_w_tmo(int ticks, enum yesno_res fallback,
    const char *title, const struct text_message *message,
    const struct text_message *yes_message, const struct text_message *no_message);
static void simplelist_info_init(struct simplelist_info *list, char *title,
                                int count, void *data)
{
    (void)title;
    memset(list, 0, sizeof(*list));
    list->count = count;
    list->data = data;
}
static bool simplelist_show_list(struct simplelist_info *list)
{
    char buffer[256];
    for (int selected = 0; selected < list->count; ++selected)
    {
        list->get_name(selected, list->data, buffer, sizeof(buffer));
        list->get_talk(selected, list->data);
        ++menu_voices;
    }
    if (selection_offset >= selection_count)
    {
        list->selection = -1;
        return false;
    }
    list->selection = selections[selection_offset++];
    return list->selection == -313;
}
static bool set_option(const char *title, const void *variable, enum optiontype type,
    const struct opt_items *options, int count, void (*callback)(int))
{
    (void)title;
    (void)callback;
    if (type != RB_INT || (count != 26 && count != 27 && count != 28 && count != 3 && count != 8 && count != 2))
        return true;
    option_count = count;
    option_initial_choice = *(const int *)variable;
    for (int index = 0; index < count; ++index)
        option_voice_ids[index] = options[index].voice_id;
    if (option_choice == -313)
        return true;
    *(int *)variable = option_choice;
    return false;
}
static bool set_bool(const char *title, const bool *value)
{
    (void)title;
    *(bool *)value = !*value;
    return false;
}
bool set_int(const unsigned char *title, const char *unit, int voice_unit,
    const int *value, void (*callback)(int), int step, int minimum, int maximum,
    const char *(*formatter)(char *, size_t, int, const char *))
{
    (void)title; (void)unit; (void)voice_unit; (void)callback; (void)step;
    (void)minimum; (void)maximum; (void)formatter;
    if (option_choice == -313) return true;
    *(int *)value = option_choice;
    return false;
}
static int plugin_load(const char *path, const void *parameter)
{
    (void)parameter;
    ++plugin_calls;
    snprintf(plugin_path, sizeof(plugin_path), "%s", path);
    return browse_result == MENU_ATTACHED_USB ? PLUGIN_USB_CONNECTED : 0;
}
"""


WRAPPERS = r"""
void touchscreen_set_mode(enum touchscreen_mode mode) { touch_mode = mode; }
enum touchscreen_mode touchscreen_get_mode(void) { return (enum touchscreen_mode)touch_mode; }
static enum yesno_res gui_syncyesno_run_w_tmo(int ticks, enum yesno_res fallback,
    const char *title, const struct text_message *message,
    const struct text_message *yes_message, const struct text_message *no_message)
{
    (void)title;
    (void)message;
    (void)yes_message;
    (void)no_message;
    if (fallback != YESNO_NO)
        return YESNO_USB;
    prompt_ticks = ticks;
    writes_at_prompt = writes;
    observed_mapping = active_config.mapping[ACCESSIBILITY_STROKE_LEFT];
    current_tick = (uint32_t)current_tick + advance_ticks;
    accessibility_enabled();
    pending_at_return = point_pending || recognizer.pending_tap || recognizer.active;
    return (enum yesno_res)answer;
}
void probe_reset(void)
{
    memset(&active_config, 0, sizeof(active_config));
    memset(&saved_trial, 0, sizeof(saved_trial));
    memset(&recognizer, 0, sizeof(recognizer));
    memset(button_recognizers, 0, sizeof(button_recognizers));
    initialized = false;
    have_context = point_pending = point_force = exploring = trial_active = false;
    feedback_pending = feedback_valid = point_single_tap = false;
    empty_speech_pending = empty_feedback_loaded = false;
    empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
    empty_disk_exists = empty_temporary_exists = empty_temporary_open = empty_temporary_synced = false;
    empty_disk_length = empty_temporary_length = empty_read_offset = 0;
    empty_fault = 0;
    sensitivity_percent = 100;
    target_clicks = empty_clicks = 0;
    current_tick = 0;
    touch_mode = global_settings.touch_mode = TOUCHSCREEN_BUTTON;
    global_settings.keyclick_repeats = false;
    disk_exists = false;
    temporary_exists = temporary_open = temporary_synced = false;
    syncs = time_calls = 0;
    time_enqueue = true;
    date_calls = summary_calls = 0;
    date_enqueue = summary_enqueue = true;
    requested_screen = -999;
    navigation_requests = navigation_cancels = 0;
    navigation_pending = false;
    navigation_available = true;
    disk_length = temporary_length = read_offset = 0;
    opens = closes = writes = renames = removes = fault = 0;
    read_chunk = write_chunk = volume = spoken_count = splash_label = 0;
    answer = YESNO_YES;
    advance_ticks = prompt_ticks = writes_at_prompt = pending_at_return = observed_mapping = 0;
    selection_count = selection_offset = menu_voices = plugin_calls = 0;
    option_choice = 0;
    option_count = option_initial_choice = 0;
    memset(option_voice_ids, 0, sizeof(option_voice_ids));
    physical_context_valid = launch_pending = launch_running = physical_repeat = false;
    editing_launch = false;
    gesture_clicks = shutdown_calls = launcher_calls = 0;
    curtain_active = false;
    curtain_set_calls = 0;
    speech_available = true;
    typing_active = false;
    typing_dispatches = 0;
    typing_mode = 0;
    typing_feedback_probe = false;
#ifdef HIBY_R1
    curtain_release_mask = 0;
    physical_contact = physical_blocked = 0;
    physical_locked = false;
#endif
    battery_value = 63;
    spoken_value = -1;
    battery_reads = value_calls = value_unit = 0;
    value_enqueue = false;
    memset(spoken_enqueue, 0, sizeof(spoken_enqueue));
    selected_plugin[0] = '\0';
    launcher_choice = browse_result = 0;
    default_button_calls = 0;
    plugin_path[0] = '\0';
    spoken_file[0] = '\0';
}
void probe_disk(const char *buffer, int length)
{
    disk_exists = length >= 0;
    if (length >= 0 && (size_t)length <= sizeof(disk))
    {
        memcpy(disk, buffer, length);
        disk_length = length;
    }
}
int probe_disk_length(void) { return (int)disk_length; }
const char *probe_disk_content(void) { disk[disk_length] = 0; return (const char *)disk; }
void probe_fault(int value) { fault = value; }
void probe_chunks(int input, int output) { read_chunk = input; write_chunk = output; }
int probe_mapping(int slot) { return active_config.mapping[slot]; }
void probe_assign(int slot, int action)
{
    active_config.mapping[slot] = action;
    accessibility_apply();
}
int probe_parse(const char *buffer, int length)
{
    struct accessibility_config result;
    memset(&result, 0x5a, sizeof(result));
    struct accessibility_config before = result;
    bool valid = accessibility_parse(buffer, length, &result);
    if (!valid && memcmp(&before, &result, sizeof(result)))
        return -1;
    return valid;
}
int probe_save(void) { return accessibility_save(&active_config); }
void probe_enable(bool enabled) { active_config.enabled = enabled; accessibility_apply(); }
int probe_mode(void) { return touch_mode; }
void probe_stock_mode(int mode) { global_settings.touch_mode = mode; touch_mode = mode; }
int probe_stat(int index)
{
    const int values[] = {opens, closes, writes, renames, removes, volume, spoken_count,
        splash_label, prompt_ticks, writes_at_prompt, pending_at_return, observed_mapping,
        menu_voices, plugin_calls, trial_active};
    return values[index];
}
int probe_spoken(int index) { return spoken[index]; }
int probe_action(int action, int context) { return accessibility_action_for(action, context); }
int probe_touch(int type, int x, int y, uint32_t milliseconds, int context)
{
    current_tick = milliseconds / 10;
    struct touchevent event = {type, x, y, current_tick};
    return accessibility_handle_touch(&event, context);
}
int probe_poll(uint32_t milliseconds, int context)
{
    current_tick = milliseconds / 10;
    return accessibility_handle_touch(NULL, context);
}
void probe_target(uintptr_t value) { accessibility_set_target((void *)value); }
void probe_time(uint32_t ticks) { current_tick = ticks; }
int probe_trial(int action, int result, uint32_t elapsed)
{
    struct accessibility_config candidate = active_config;
    candidate.mapping[ACCESSIBILITY_STROKE_LEFT] = action;
    answer = result;
    advance_ticks = elapsed;
    return accessibility_trial(&candidate);
}
void probe_start_trial(int action)
{
    saved_trial = active_config;
    active_config.mapping[ACCESSIBILITY_STROKE_LEFT] = action;
    trial_deadline = (uint32_t)current_tick + ACCESSIBILITY_TRIAL_TICKS;
    trial_active = true;
    accessibility_apply();
}
void probe_script(const int *values, int count, int choice)
{
    if (count > 64) return;
    memcpy(selections, values, sizeof(int) * count);
    selection_count = count;
    selection_offset = 0;
    option_choice = choice;
}
const char *probe_plugin_path(void) { return plugin_path; }
int probe_button_mapping(int button, int slot) { return active_config.buttons[button][slot]; }
void probe_button_assign(int button, int slot, int action)
{ active_config.buttons[button][slot] = action; accessibility_apply(); }
int probe_playback_mapping(int button, int slot)
{ return active_config.playback_buttons[button][slot]; }
int probe_playback_ref(int button, int slot)
{ return active_config.playback_launch[button][slot]; }
void probe_playback_assign(int button, int slot, int action)
{ active_config.playback_buttons[button][slot] = action; accessibility_apply(); }
void probe_playback_bind(int button, int slot, int target)
{ active_config.playback_launch[button][slot] = target; }
int probe_playback_gesture(int slot) { return active_config.playback_mapping[slot]; }
int probe_playback_gesture_ref(int slot) { return active_config.playback_gesture_launch[slot]; }
int probe_context_gesture(int context, int slot) { return gesture_mappings(context)[slot]; }
int probe_gesture_profile_menu(int playback)
{ return accessibility_gesture_profile_menu(playback ? CONTEXT_WPS : CONTEXT_STD); }
int probe_gesture_root_menu(void) { return accessibility_edit_gestures(); }
const char *probe_touch_row(int selected)
{
    static char row[512];
    const char *name = accessibility_get_name(selected, NULL, row, sizeof(row));
    if (name != row)
        snprintf(row, sizeof(row), "%s", name);
    accessibility_speak(selected, NULL);
    return row;
}
void probe_button_root_speak(int selected)
{
#ifdef HIBY_R1
    button_root_speak(selected, NULL);
#else
    (void)selected;
#endif
}
const char *probe_profile_row(int button, int slot, int context)
{
    static char row[512];
#ifdef HIBY_R1
    button_get_name(button * ACCESSIBILITY_BUTTON_SLOT_COUNT + slot,
        (void *)(intptr_t)context, row, sizeof(row));
    button_speak(button * ACCESSIBILITY_BUTTON_SLOT_COUNT + slot, (void *)(intptr_t)context);
#else
    (void)button; (void)slot; (void)context;
    row[0] = '\0';
#endif
    return row;
}
int probe_button(int button, uint32_t milliseconds, int context, bool locked)
{
    current_tick = milliseconds / 10;
    int action;
    bool consumed = accessibility_handle_button(button, context, locked, &action);
    return consumed ? action : -1;
}
int probe_extra(int index)
{
    const int values[] = {gesture_clicks, shutdown_calls, launcher_calls, spoken_value,
        launch_pending, active_config.hold_ms};
    return values[index];
}
void probe_feedback(int owner, int target, bool occupied)
{ accessibility_explore_feedback((const void *)(uintptr_t)owner, target, occupied); }
void probe_empty_mode(int mode)
{
    if (mode >= ACCESSIBILITY_EMPTY_SOUND_ONLY && mode <= ACCESSIBILITY_EMPTY_SPEECH_ONLY)
    {
        empty_feedback_mode = mode;
        empty_feedback_loaded = true;
    }
}
void probe_empty_fault(int value) { empty_fault = value; }
void probe_confirmation(int value) { answer = value; }
void probe_confirmation_elapsed(uint32_t value) { advance_ticks = value; }
void probe_empty_reload(void)
{
    empty_feedback_loaded = false;
    empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
}
const char *probe_empty_disk_content(void)
{
    empty_disk[empty_disk_length] = '\0';
    return (const char *)empty_disk;
}
int probe_feedback_stat(int index)
{
    const int values[] = {target_clicks, empty_clicks, active_config.empty_pitch,
        active_config.empty_semitones, recognizer.config.tap_slop_px, recognizer.config.stroke_min_px};
    return values[index];
}
void probe_sensitivity(unsigned int percent)
{ sensitivity_percent = percent; accessibility_reset(); }
void probe_typing_feedback(int target, bool occupied)
{
    typing_active = typing_feedback_probe = true;
    typing_mode = 0;
    typing_feedback_target = target;
    typing_feedback_occupied = occupied;
}
void probe_launcher(int choice, const char *path, int result)
{
    launcher_choice = choice;
    browse_result = result;
    snprintf(selected_plugin, sizeof(selected_plugin), "%s", path ? path : "");
}
int probe_ref(int button, int slot)
{ return button < 0 ? active_config.gesture_launch[slot] : active_config.button_launch[button][slot]; }
const char *probe_path(int index) { return active_config.launch_paths[index]; }
const char *probe_spoken_file(void) { return spoken_file; }
const char *probe_row(int button, int slot)
{
    static char row[512];
    if (button < 0)
    {
        gesture_get_name(slot - 1, NULL, row, sizeof(row));
        gesture_speak(slot - 1, NULL);
    }
#ifdef HIBY_R1
    else
    {
        button_get_name(button * 4 + slot, NULL, row, sizeof(row));
        button_speak(button * 4 + slot, NULL);
    }
#endif
    return row;
}
const char *probe_guide_row(int selected, int context)
{
    static char row[512];
#ifdef HIBY_R1
    button_guide_name(selected, (void *)(intptr_t)context, row, sizeof(row));
    button_guide_speak(selected, (void *)(intptr_t)context);
#else
    (void)selected;
    (void)context;
    row[0] = '\0';
#endif
    return row;
}
void probe_bind(int button, int slot, int target)
{ if (button < 0) active_config.gesture_launch[slot] = target; else active_config.button_launch[button][slot] = target; }
void probe_prompt(int response, uint32_t elapsed) { answer = response; advance_ticks = elapsed; }
void probe_click_sources(int sources) { active_config.click_sources = sources; }
void probe_reload(void) { initialized = false; accessibility_init(); }
int probe_curtain(void) { return curtain_active; }
int probe_curtain_set_calls(void) { return curtain_set_calls; }
int probe_option_count(void) { return option_count; }
int probe_option_initial_choice(void) { return option_initial_choice; }
int probe_option_voice(int index)
{ return index >= 0 && index < option_count ? option_voice_ids[index] : -1; }
void probe_speech_available(bool enabled) { speech_available = enabled; }
void probe_typing(bool active) { typing_active = active; }
int probe_typing_dispatches(void) { return typing_dispatches; }
void probe_typing_mode(int mode) { typing_mode = mode; }
void probe_battery(int value) { battery_value = value; }
int probe_battery_reads(void) { return battery_reads; }
int probe_value_calls(void) { return value_calls; }
int probe_value_unit(void) { return value_unit; }
int probe_value_enqueue(void) { return value_enqueue; }
int probe_spoken_enqueue(int index) { return spoken_enqueue[index]; }
int probe_time_calls(void) { return time_calls; }
int probe_time_enqueue(void) { return time_enqueue; }
int probe_syncs(void) { return syncs; }
int probe_temporary_exists(void) { return temporary_exists; }
int probe_temporary_open(void) { return temporary_open; }
int probe_touch_hold(void) { return active_config.touch_hold_ms; }
int probe_stroke_repeat(void) { return active_config.stroke_repeat; }
void probe_touch_options(unsigned int hold_ms, bool repeat)
{ active_config.touch_hold_ms = hold_ms; active_config.stroke_repeat = repeat; accessibility_apply(); }
int probe_touch_trial(unsigned int hold_ms, bool repeat)
{
    struct accessibility_config candidate = active_config;
    candidate.touch_hold_ms = hold_ms;
    candidate.stroke_repeat = repeat;
    return accessibility_trial(&candidate);
}
int probe_date_calls(void) { return date_calls; }
int probe_summary_calls(void) { return summary_calls; }
int probe_date_enqueue(void) { return date_enqueue; }
int probe_summary_enqueue(void) { return summary_enqueue; }
int probe_requested_screen(void) { return requested_screen; }
int probe_navigation_requests(void) { return navigation_requests; }
int probe_navigation_cancels(void) { return navigation_cancels; }
void probe_navigation_available(bool enabled) { navigation_available = enabled; }
unsigned int probe_config_capacity(void) { return ACCESSIBILITY_CONFIG_MAX; }
unsigned int probe_max_path(void) { return MAX_PATH; }
int probe_plugin_target(unsigned int target) { return accessibility_plugin_target(target); }
int probe_default_button_calls(void) { return default_button_calls; }
"""


def default_config(enabled=1, replacements=None, legacy=False, buttons=None, clicks=None, hold=700,
                   gesture_refs=None, button_refs=None, paths=None, version=11,
                   touch_hold=900, stroke_repeat=0, empty_pitch=1, empty_semitones=-4,
                   playback_buttons=None, playback_refs=None,
                   playback_gestures=None, playback_gesture_refs=None, factory=False):
    mappings = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 8: 7, 17: 5}
    version = 1 if legacy else version
    if clicks is None:
        clicks = 7 if version >= 8 else 3
    if version >= 7:
        mappings[20] = 8
    if version >= 11 and factory:
        mappings[13] = 22
        mappings[16] = 23
    playback_defaults = dict(mappings)
    mappings.update(replacements or {})
    header = f"RBACCESSIBILITY:{version}\nenabled:{enabled}\n"
    if version != 1:
        header += f"click:{clicks}\nhold:{hold}\n"
    if version >= 7:
        header += f"touch_hold:{touch_hold}\nstroke_repeat:{stroke_repeat}\n"
    if version >= 8:
        header += f"empty_pitch:{empty_pitch}\nempty_semitones:{empty_semitones}\n"
    header += "".join(f"gesture:{slot}:{mappings.get(slot, 0)}" +
                      ("" if version < 3 else f":{(gesture_refs or {}).get(slot, 0)}") + "\n"
                      for slot in range(1, 21 if version >= 7 else 19))
    if version >= 10:
        playback_mapping = dict(mappings if playback_gestures is None else playback_defaults)
        playback_mapping.update(playback_gestures or {})
        if playback_gesture_refs is None:
            playback_gesture_refs = gesture_refs if playback_gestures is None else {}
        header += "".join(f"playback_gesture:{slot}:{playback_mapping.get(slot, 0)}:"
                          f"{(playback_gesture_refs or {}).get(slot, 0)}\n"
                          for slot in range(1, 21))
    if version != 1:
        system_action = VERSION_ACTION_LIMITS[version] + 1
        button_defaults = {(0, 2): 26} if version >= 11 and factory else {}
        button_defaults.update(buttons or {})
        header += "".join(f"button:{button}:{slot}:{button_defaults.get((button, slot), system_action)}" +
                          ("" if version < 3 else f":{(button_refs or {}).get((button, slot), 0)}") + "\n"
                          for button in range(5) for slot in range(4))
        if version >= 9:
            playback_buttons = button_defaults if playback_buttons is None else playback_buttons
            playback_refs = button_refs if playback_refs is None else playback_refs
            header += "".join(f"playback_button:{button}:{slot}:"
                              f"{(playback_buttons or {}).get((button, slot), system_action)}:"
                              f"{(playback_refs or {}).get((button, slot), 0)}\n"
                              for button in range(5) for slot in range(4))
        if version >= 3:
            header += "".join(f"target:{index}:{(paths or {}).get(index, '')}\n" for index in range(4))
    return header.encode()


class AccessibilitySettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            raise unittest.SkipTest("C host compiler unavailable; run compiled tests under WSL")
        materials = project_materials_root(ROOT)
        ensure_ignored_directories(materials.parent, [materials.name])
        cls.workspace = materials / "r1-context-controls-20261017/controls/config-codec" / (
            "settings-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.workspace.mkdir(parents=True, exist_ok=False)
        paths = ["apps/accessibility.c", "apps/accessibility.h", "apps/accessibility_screen.h",
                 "apps/accessibility_screen.c", "apps/accessibility_gesture.c",
                 "apps/accessibility_gesture.h", "apps/accessibility_buttons.c",
                 "apps/accessibility_buttons.h", "apps/accessibility_shortcut.h", "apps/accessibility_services.h",
                 "apps/action.h", "apps/root_menu.h",
                 "apps/lang/english.lang", "apps/lang/polski.lang",
                 "firmware/export/touchscreen.h", "tools/tests/test_accessibility_settings.py",
                 "tools/tests/test_accessibility_context_profiles.py", "apps/menus/settings_menu.c",
                 "tools/tests/fixtures/accessibility_input_fixture.c"]
        source_bytes = {path: (ROOT / path).read_bytes() for path in paths}
        cls.source_bytes = source_bytes
        sources = {path: content.decode("utf-8") for path, content in source_bytes.items()}
        action_header = sources["apps/action.h"]
        defines = "\n".join(re.findall(r'^#define CONTEXT_[^\n]+', action_header, re.MULTILINE))
        enums = action_header[action_header.index("enum {"):action_header.index("struct button_mapping {")]
        root_enum = re.search(r'enum\s*\{.*?\};', sources["apps/root_menu.h"], re.DOTALL)
        if root_enum is None:
            raise AssertionError("Expected the real root navigation enum")
        battery_helper = re.search(r'^void accessibility_speak_battery\(bool enqueue\)\s*\{.*?^\}',
                                  sources["apps/accessibility_screen.c"], re.MULTILINE | re.DOTALL)
        if battery_helper is None:
            raise AssertionError("Expected the shared accessibility_speak_battery definition")
        labels = sorted(set(re.findall(r'\bLANG_[A-Z0-9_]+',
                                       sources["apps/accessibility.c"] + battery_helper[0])))
        language = "\n".join(f"#define {label} {index + 1000}" for index, label in enumerate(labels))
        harness = "#define HAVE_ESPEAK\n#define BUTTON_NONE 0\n#define HAVE_VOLUME_IN_LIST\n" + defines + "\n" + enums + "\n" + root_enum[0] + "\n" + PREAMBLE + "\n" + language + "\n"
        harness += without_includes(sources["firmware/export/touchscreen.h"])
        harness += without_includes(sources["apps/accessibility_gesture.h"])
        harness += without_includes(sources["apps/accessibility_buttons.h"])
        harness += without_includes(sources["apps/accessibility.h"])
        harness += without_includes(sources["apps/accessibility_screen.h"])
        harness += without_includes(sources["apps/accessibility_shortcut.h"])
        harness += without_includes(sources["apps/accessibility_services.h"])
        harness += "\n" + battery_helper[0] + "\n"
        harness += without_includes(sources["apps/accessibility_gesture.c"])
        harness += without_includes(sources["apps/accessibility_buttons.c"])
        harness += without_includes(sources["apps/accessibility.c"])
        harness += WRAPPERS
        harness += sources["tools/tests/fixtures/accessibility_input_fixture.c"]
        names = sorted(set(re.findall(r'\b(?:ACTION_[A-Z0-9_]+|CONTEXT_[A-Z0-9_]+|'
                                     r'ACCESSIBILITY_ACTION_[A-Z0-9_]+|TOUCHEVENT_[A-Z0-9_]+)\b',
                                     sources["apps/accessibility.c"])) | set(labels) | {"ACTION_WPS_STOPSEEK"})
        names += ["GO_TO_FILEBROWSER", "GO_TO_WPS", "GO_TO_MAINMENU", "GO_TO_PLAYLISTS_SCREEN", "GO_TO_PREVIOUS"]
        if not NO_TAGCACHE:
            names.append("GO_TO_DBBROWSER")
        harness += "\n".join(f"int constant_{name}(void) {{ return {name}; }}" for name in names)
        harness_path = cls.workspace / "manager.c"
        harness_path.write_text(harness, encoding="utf-8")
        standard = os.environ.get("ACCESSIBILITY_SETTINGS_STANDARD", "c99")
        command = compiler + [f"-std={standard}", "-O2", "-Wall", "-Wextra", "-Werror", "-fstack-usage", "-shared", "-fPIC",
                              str(harness_path), "-o", str(cls.workspace / "manager.so")]
        if os.environ.get("ACCESSIBILITY_SETTINGS_SANITIZE"):
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        if os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"):
            command += ["-DTEST_OTHER_TARGET"]
        if NO_SCREEN_CURTAIN:
            command += ["-DACCESSIBILITY_SETTINGS_NO_CURTAIN"]
        if not NO_TAGCACHE:
            command += ["-DHAVE_TAGCACHE"]
        if os.environ.get("ACCESSIBILITY_SETTINGS_UNSIGNED_STR"):
            command += ["-DTEST_UNSIGNED_STR", "-Wno-pointer-sign"]
        result = subprocess.run(command, capture_output=True, text=True)
        (cls.workspace / "compile.log").write_text(shlex.join(command) + "\n" + result.stdout + result.stderr,
                                                 encoding="utf-8")
        (cls.workspace / "provenance.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_sha256": {path: hashlib.sha256(
                content).hexdigest() for path, content in source_bytes.items()},
            "harness_sha256": hashlib.sha256(harness_path.read_bytes()).hexdigest(),
            "command": command, "returncode": result.returncode,
            "screen_curtain": not NO_SCREEN_CURTAIN,
            "tagcache": not NO_TAGCACHE, "rtc": False,
            "unsigned_str": bool(os.environ.get("ACCESSIBILITY_SETTINGS_UNSIGNED_STR")),
            "host_os": os.name, "platform": sys.platform,
            "source_unchanged": all((ROOT / path).read_bytes() == content
                                    for path, content in source_bytes.items()),
            "artifact_sha256": hashlib.sha256((cls.workspace / "manager.so").read_bytes()).hexdigest()
                if result.returncode == 0 else None,
            "scope": "real manager, recognizers, root enum, service header and shared battery helper; mocked service endpoints, time/date/summary speech, root navigation and core UI/filesystem; no RTC implementation or physical acceptance",
        }, indent=2), encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stderr)
        if any((ROOT / path).read_bytes() != content for path, content in source_bytes.items()):
            raise AssertionError("Manager/recognizer sources changed during host compilation")
        imports = subprocess.run(["nm", "-u", str(cls.workspace / "manager.so")],
                                 capture_output=True, text=True, timeout=60)
        (cls.workspace / "imports.log").write_text(imports.stdout + imports.stderr, encoding="utf-8")
        if imports.returncode:
            raise AssertionError(imports.stderr)
        symbols = {line.split()[-1].split("@")[0] for line in imports.stdout.splitlines() if line.split()}
        forbidden = {"open", "open64", "read", "write", "close", "fsync", "rename", "remove",
                     "system", "execve", "fork", "socket", "ioctl", "reboot", "kill"}
        if symbols & forbidden:
            raise AssertionError("Unmocked core operations: " + repr(symbols & forbidden))
        cls.library = ctypes.CDLL(str(cls.workspace / "manager.so"))
        for name in re.findall(r'^bool\s+(accessibility_[a-z_]+)\s*\(',
                               sources["apps/accessibility.h"], re.MULTILINE):
            getattr(cls.library, name).restype = ctypes.c_bool
        cls.constants = {name: getattr(cls.library, f"constant_{name}")() for name in names}
        cls.library.probe_disk.argtypes = [ctypes.c_char_p, ctypes.c_int]
        cls.library.probe_parse.argtypes = [ctypes.c_char_p, ctypes.c_int]
        cls.library.probe_touch.argtypes = [ctypes.c_int] * 3 + [ctypes.c_uint32, ctypes.c_int]
        cls.library.probe_poll.argtypes = [ctypes.c_uint32, ctypes.c_int]
        cls.library.probe_time.argtypes = [ctypes.c_uint32]
        cls.library.probe_trial.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
        cls.library.probe_target.argtypes = [ctypes.c_size_t]
        cls.library.probe_script.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int]
        cls.library.probe_disk_content.restype = ctypes.c_char_p
        cls.library.probe_plugin_path.restype = ctypes.c_char_p
        cls.library.probe_launcher.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        cls.library.probe_path.restype = ctypes.c_char_p
        cls.library.probe_spoken_file.restype = ctypes.c_char_p
        cls.library.probe_row.restype = ctypes.c_char_p
        cls.library.probe_profile_row.restype = ctypes.c_char_p
        cls.library.probe_touch_row.restype = ctypes.c_char_p
        cls.library.probe_guide_row.restype = ctypes.c_char_p
        cls.library.probe_button.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_int, ctypes.c_bool]
        cls.library.accessibility_explore_point.argtypes = [ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_bool)]
        cls.library.accessibility_explore_point.restype = ctypes.c_bool
        cls.library.accessibility_set_curtain.argtypes = [ctypes.c_bool]
        cls.library.accessibility_set_curtain.restype = ctypes.c_bool
        cls.library.accessibility_set_curtain_state.argtypes = [ctypes.c_bool, ctypes.c_bool]
        cls.library.accessibility_set_curtain_state.restype = ctypes.c_bool
        cls.library.accessibility_set_enabled.argtypes = [ctypes.c_bool]
        cls.library.accessibility_set_enabled.restype = ctypes.c_bool
        cls.library.accessibility_curtain_escape.argtypes = [ctypes.c_int]
        cls.library.accessibility_curtain_escape.restype = ctypes.c_bool
        cls.library.probe_speech_available.argtypes = [ctypes.c_bool]
        cls.library.accessibility_process_pending.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.library.probe_touch_options.argtypes = [ctypes.c_uint, ctypes.c_bool]
        cls.library.probe_touch_trial.argtypes = [ctypes.c_uint, ctypes.c_bool]
        cls.library.probe_navigation_available.argtypes = [ctypes.c_bool]

    @classmethod
    def tearDownClass(cls):
        changed = [path for path, content in cls.source_bytes.items() if (ROOT / path).read_bytes() != content]
        if changed:
            raise AssertionError("Sources changed during the test run: " + ", ".join(changed))

    def setUp(self):
        self.library.input_reset()
        if os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"):
            self.library.probe_enable(True)

    def constant(self, name):
        return self.constants[name]

    def parse(self, value):
        return self.library.probe_parse(value, len(value))

    def process_pending(self, event, context="CONTEXT_STD"):
        return self.library.accessibility_process_pending(event,
            self.constant(context) if isinstance(context, str) else context)

    def touch(self, event, x, y, milliseconds, context="CONTEXT_STD"):
        return self.library.probe_touch(self.constant(event), x, y, milliseconds,
                                       self.constant(context) if isinstance(context, str) else context)

    def poll(self, milliseconds, context="CONTEXT_STD"):
        return self.library.probe_poll(milliseconds, self.constant(context) if isinstance(context, str) else context)

    def point(self):
        position_x, position_y, force = ctypes.c_int(), ctypes.c_int(), ctypes.c_bool()
        valid = self.library.accessibility_explore_point(ctypes.byref(position_x), ctypes.byref(position_y),
                                                        ctypes.byref(force))
        return (position_x.value, position_y.value, force.value) if valid else None

    def script(self, values, choice=0):
        self.library.probe_script((ctypes.c_int * len(values))(*values), len(values), choice)

    def gesture_script(self, values, choice=0, playback=False):
        self.assertEqual(values[0], 1)
        self.script([values[0], int(playback), *values[1:], -1], choice=choice)

    def test_default_target_and_point_mode(self):
        self.library.probe_reset()
        self.assertFalse(self.library.accessibility_enabled())
        self.library.accessibility_init()
        expected = not bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"))
        self.assertEqual(bool(self.library.accessibility_enabled()), expected)
        self.assertEqual(self.library.probe_mode(), 0 if expected else 1)
        self.assertEqual(self.library.probe_stat(2), 0)

    def test_exact_default_and_all_action_values_parse(self):
        self.assertEqual(self.parse(default_config()), 1)
        for action in range(self.constant("ACCESSIBILITY_ACTION_COUNT")):
            self.assertEqual(self.parse(default_config(replacements={slot: action for slot in range(1, 21)})), 1)

    def test_every_truncation_rejected_without_partial_output(self):
        content = default_config()
        for length in range(len(content)):
            self.assertEqual(self.parse(content[:length]), 0, length)

    def test_time_action_dispatches_once_without_enqueue_in_each_context(self):
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_CURTAIN"), 15)
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_TIME"), 16)
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_TOGGLE_ESPEAK"), 17)
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES"), 18)
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_TOGGLE_TOUCH"), 19)
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_DATE"), 20)
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_SUMMARY"), 21)
        self.assertEqual(self.constant("ACCESSIBILITY_ACTION_SYSTEM"), 27)
        contexts = [self.constant(name) for name in (
            "CONTEXT_STD", "CONTEXT_WPS", "CONTEXT_KEYBOARD", "CONTEXT_SETTINGS",
            "CONTEXT_YESNOSCREEN", "CONTEXT_QUICKSCREEN")]
        contexts += [self.constant("CONTEXT_STD") | self.constant("CONTEXT_CUSTOM") |
                     self.constant("CONTEXT_CUSTOM2")]
        for count, context in enumerate(contexts, 1):
            self.assertEqual(self.library.probe_action(16, context), self.constant("ACTION_NONE"))
            self.assertEqual(self.library.probe_time_calls(), count)
            self.assertEqual(self.library.probe_time_enqueue(), 0)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_stat(6), 0)
        self.assertEqual(self.library.probe_stat(13), 0)
        self.assertEqual(self.library.probe_extra(1), 0)
        self.assertEqual(self.library.probe_curtain_set_calls(), 0)

    def test_quiet_touch_service_setter_is_idempotent_and_preserves_both_profiles(self):
        before = default_config(enabled=0, replacements={1: 8}, playback_gestures={1: 16},
                                buttons={(1, 0): 11}, playback_buttons={(1, 0): 16})
        self.library.probe_disk(before, len(before))
        self.library.probe_reload()
        writes = self.library.probe_stat(2)
        spoken = self.library.probe_stat(6)
        self.assertTrue(self.library.accessibility_set_enabled(False))
        self.assertEqual(self.library.probe_stat(2), writes)
        self.assertTrue(self.library.accessibility_set_enabled(True))
        self.assertTrue(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_disk_content(), before.replace(b"enabled:0", b"enabled:1", 1))
        self.assertEqual(self.library.probe_stat(6), spoken)
        writes = self.library.probe_stat(2)
        self.assertTrue(self.library.accessibility_set_enabled(True))
        self.assertEqual(self.library.probe_stat(2), writes)

    def test_quiet_touch_service_save_failures_preserve_runtime_and_file(self):
        for fault in range(4, 11):
            with self.subTest(fault=fault):
                self.setUp()
                previous = default_config(enabled=0)
                self.library.probe_disk(previous, len(previous))
                self.library.probe_reload()
                self.library.probe_chunks(0, 7)
                self.library.probe_fault(fault)
                self.assertFalse(self.library.accessibility_set_enabled(True))
                self.assertFalse(self.library.accessibility_enabled())
                self.assertEqual(self.library.probe_disk_content(), previous)

    def test_quiet_touch_service_cannot_commit_mapping_trial(self):
        self.library.probe_start_trial(8)
        self.assertFalse(self.library.accessibility_set_enabled(False))
        self.assertEqual(self.library.probe_stat(2), 0)

    @unittest.skipIf(NO_SCREEN_CURTAIN, "Screen curtain unavailable in this configuration")
    def test_quiet_curtain_noop_preserves_existing_state_when_speech_unavailable(self):
        self.assertTrue(self.library.accessibility_set_curtain_state(True, False))
        spoken = self.library.probe_stat(6)
        writes = self.library.probe_stat(2)
        calls = self.library.probe_curtain_set_calls()
        self.library.probe_speech_available(False)
        self.assertTrue(self.library.accessibility_set_curtain_state(True, False))
        self.assertTrue(self.library.probe_curtain())
        self.assertEqual(self.library.probe_curtain_set_calls(), calls)
        self.assertTrue(self.library.accessibility_set_curtain_state(False, False))
        self.assertFalse(self.library.probe_curtain())
        self.assertEqual(self.library.probe_stat(6), spoken)
        self.assertEqual(self.library.probe_stat(2), writes)

    def test_time_gesture_consumes_release_once_and_keeps_configuration(self):
        content = default_config(replacements={1: 16})
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.touch("TOUCHEVENT_PRESS", 300, 400, 10)
        self.touch("TOUCHEVENT_CONTACT", 200, 400, 40)
        self.assertEqual(self.library.probe_time_calls(), 0)
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 200, 400, 100),
                         self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_time_calls(), 1)
        self.assertEqual(self.library.probe_time_enqueue(), 0)
        self.assertIsNone(self.point())
        self.poll(1000)
        self.assertEqual(self.library.probe_time_calls(), 1)
        self.assertEqual(self.library.probe_disk_content(), content)
        self.assertEqual(self.library.probe_stat(2), 0)

    def test_unavailable_time_speech_still_consumes_action_without_fallback(self):
        self.library.probe_speech_available(False)
        self.assertEqual(self.library.probe_action(16, self.constant("CONTEXT_WPS")),
                         self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_time_calls(), 1)
        self.assertEqual(self.library.probe_time_enqueue(), 0)
        self.assertEqual(self.library.probe_stat(13), 0)
        self.assertEqual(self.library.probe_stat(2), 0)

    def test_time_gesture_selector_speaks_persists_and_reselects_same_action(self):
        time_option = 15 if NO_SCREEN_CURTAIN else 16
        self.gesture_script([1, 0, -1, -1], choice=time_option)
        self.assertEqual(self.library.accessibility_menu(), 0)
        self.assertEqual(self.library.probe_option_voice(time_option),
                         self.constant("LANG_ACCESSIBILITY_ACTION_TIME"))
        self.assertEqual(self.library.probe_mapping(1), 16)
        self.assertEqual(self.library.probe_time_calls(), 0)
        self.library.probe_row(-1, 1)
        self.assertEqual(self.library.probe_spoken(self.library.probe_stat(6) - 1),
                         self.constant("LANG_ACCESSIBILITY_ACTION_TIME"))
        self.assertIn(b"gesture:1:16:0\n", self.library.probe_disk_content())
        writes = self.library.probe_stat(2)
        self.library.probe_reload()
        self.gesture_script([1, 0, -1, -1], choice=time_option)
        self.assertEqual(self.library.accessibility_menu(), 0)
        self.assertEqual(self.library.probe_option_initial_choice(), time_option)
        self.assertEqual(self.library.probe_stat(2), writes)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_time_physical_selector_is_distinct_from_system_and_preserves_touch_scope(self):
        time_option = 15 if NO_SCREEN_CURTAIN else 16
        self.library.probe_assign(2, 8)
        self.script([0, 0, -1, -1], choice=time_option)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_option_voice(time_option),
                         self.constant("LANG_ACCESSIBILITY_ACTION_TIME"))
        self.assertEqual(self.library.probe_button_mapping(0, 0), 16)
        self.assertEqual(self.library.probe_mapping(2), 8)
        self.assertEqual(self.library.probe_time_calls(), 0)
        self.library.probe_row(0, 0)
        self.assertEqual(self.library.probe_spoken(self.library.probe_stat(6) - 1),
                         self.constant("LANG_ACCESSIBILITY_ACTION_TIME"))
        self.library.probe_reload()
        self.script([0, 0, -1, -1], choice=time_option)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_option_initial_choice(), time_option)
        self.script([0, 0, -1, -1], choice=len(self.selectable_action_labels()))
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_button_mapping(0, 0), 27)
        self.assertIn(b"button:0:0:27:0\n", self.library.probe_disk_content())

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_time_physical_single_double_triple_hold_and_repeat_filter(self):
        context = self.constant("CONTEXT_STD")
        for slot in range(4):
            with self.subTest(slot=slot):
                self.setUp()
                self.library.probe_button_assign(1, slot, 16)
                if slot == 3:
                    self.library.probe_button(8, 0, context, False)
                    self.assertEqual(self.library.probe_button(0, 700, context, False),
                                     self.constant("ACTION_NONE"))
                    self.library.probe_button(8 | 0x4000000, 800, context, False)
                    self.library.probe_button(8 | 0x2000000, 850, context, False)
                else:
                    for click in range(slot + 1):
                        self.library.probe_button(8, click * 100, context, False)
                        self.library.probe_button(8 | 0x2000000, click * 100 + 50, context, False)
                self.library.probe_button(0, 1300, context, False)
                self.assertEqual(self.library.probe_time_calls(), 1)
                self.assertEqual(self.library.probe_time_enqueue(), 0)
                self.assertEqual(self.library.probe_stat(2), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_time_physical_locked_and_plugin_contexts_do_not_speak(self):
        for context, locked in [(self.constant("CONTEXT_STD"), True),
                                (self.constant("CONTEXT_STD") | self.constant("CONTEXT_PLUGIN"), False)]:
            with self.subTest(context=context, locked=locked):
                self.setUp()
                self.library.probe_button_assign(1, 0, 16)
                self.library.probe_button(8, 0, context, locked)
                self.library.probe_button(8 | 0x2000000, 50, context, locked)
                self.library.probe_button(0, 400, context, locked)
                self.assertEqual(self.library.probe_time_calls(), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_battery_update_preserves_time_hold_and_multiclick(self):
        context = self.constant("CONTEXT_STD")
        for slot in (1, 3):
            with self.subTest(slot=slot):
                self.setUp()
                self.library.probe_button_assign(1, slot, 16)
                self.library.probe_button(8, 0, context, False)
                if slot == 1:
                    self.library.probe_button(8 | 0x2000000, 50, context, False)
                self.assertEqual(self.process_pending(0x40000003), 0)
                if slot == 1:
                    self.library.probe_button(8, 100, context, False)
                    self.library.probe_button(8 | 0x2000000, 150, context, False)
                self.library.probe_button(0, 700, context, False)
                self.assertEqual(self.library.probe_time_calls(), 1)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_usb_event_still_cancels_pending_time_hold(self):
        context = self.constant("CONTEXT_STD")
        self.library.probe_button_assign(1, 3, 16)
        self.library.probe_button(8, 0, context, False)
        self.assertEqual(self.process_pending(0x40000001), 0)
        self.library.probe_button(0, 700, context, False)
        self.library.probe_button(8 | 0x2000000, 750, context, False)
        self.assertEqual(self.library.probe_time_calls(), 0)

    def test_battery_update_preserves_touch_stroke(self):
        self.library.probe_assign(1, 16)
        self.touch("TOUCHEVENT_PRESS", 300, 400, 10)
        self.touch("TOUCHEVENT_CONTACT", 250, 400, 40)
        self.assertEqual(self.process_pending(0x40000003), 0)
        self.touch("TOUCHEVENT_CONTACT", 200, 400, 70)
        self.touch("TOUCHEVENT_RELEASE", 200, 400, 100)
        self.assertEqual(self.library.probe_time_calls(), 1)

    def test_battery_update_preserves_deferred_launch(self):
        self.library.probe_action(12, self.constant("CONTEXT_STD"))
        self.assertEqual(self.process_pending(0x40000003), 0)
        self.assertEqual(self.library.probe_extra(4), 1)
        self.assertEqual(self.library.probe_extra(2), 0)
        self.assertEqual(self.process_pending(self.constant("ACTION_NONE")),
                         self.constant("ACTION_REDRAW"))
        self.assertEqual(self.library.probe_extra(2), 2)

    @unittest.skipIf(NO_SCREEN_CURTAIN, "Screen curtain backend unavailable")
    def test_curtain_action_requires_speech_but_can_always_restore_screen(self):
        context = self.constant("CONTEXT_STD")
        self.library.probe_speech_available(False)
        self.library.probe_action(15, context)
        self.assertFalse(self.library.probe_curtain())
        self.assertEqual(self.library.probe_stat(7), self.constant("LANG_ACCESSIBILITY_CURTAIN_REQUIRES_SPEECH"))
        self.library.probe_speech_available(True)
        self.library.probe_action(15, context)
        self.assertTrue(self.library.probe_curtain())
        self.assertEqual(self.library.probe_spoken(0), self.constant("LANG_ACCESSIBILITY_CURTAIN"))
        self.assertEqual(self.library.probe_spoken(1), self.constant("LANG_ON"))
        self.library.probe_speech_available(False)
        self.library.probe_action(15, context)
        self.assertFalse(self.library.probe_curtain())
        self.assertEqual(self.library.probe_stat(2), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "R1 recovery chord")
    @unittest.skipIf(NO_SCREEN_CURTAIN, "Screen curtain backend unavailable")
    def test_curtain_recovery_consumes_both_releases_and_respects_normal_chords(self):
        self.assertFalse(self.library.accessibility_curtain_escape(1 | 4))
        self.library.accessibility_set_curtain(True)
        self.assertTrue(self.library.accessibility_curtain_escape(1 | 4))
        self.assertFalse(self.library.probe_curtain())
        self.assertTrue(self.library.accessibility_curtain_escape(4 | 0x2000000))
        self.assertTrue(self.library.accessibility_curtain_escape(1 | 0x4000000))
        self.assertTrue(self.library.accessibility_curtain_escape(1 | 0x2000000))
        self.assertFalse(self.library.accessibility_curtain_escape(1 | 4))

    def test_old_version_does_not_reinterpret_system_default_as_curtain(self):
        for version in (2, 3):
            self.setUp()
            content = default_config(version=version, buttons={(0, 0): 15, (1, 2): 0})
            self.library.probe_disk(content, len(content))
            self.library.probe_reload()
            self.assertEqual(self.library.probe_button_mapping(0, 0), self.constant("ACCESSIBILITY_ACTION_SYSTEM"))
            self.assertEqual(self.library.probe_button_mapping(1, 2), 0)
            self.assertFalse(self.library.probe_curtain())
            self.assertEqual(self.parse(default_config(version=version, replacements={1: 15})), 0)

    @unittest.skipIf(NO_SCREEN_CURTAIN, "Screen curtain backend unavailable")
    def test_curtain_is_restored_when_synthesis_is_disabled(self):
        self.assertTrue(self.library.accessibility_set_curtain(True))
        self.library.probe_speech_available(False)
        self.library.accessibility_adjust_timeout(0)
        self.assertFalse(self.library.probe_curtain())

    def test_curtain_setter_obeys_capability_without_persisting_state(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                self.assertEqual(self.library.accessibility_set_curtain(enabled), not NO_SCREEN_CURTAIN)
                self.assertEqual(bool(self.library.probe_curtain()), enabled and not NO_SCREEN_CURTAIN)
                if NO_SCREEN_CURTAIN:
                    self.assertEqual(self.library.probe_stat(7),
                                     self.constant("LANG_ACCESSIBILITY_CURTAIN_UNAVAILABLE"))
                    self.assertEqual(self.library.probe_stat(6), 0)
        self.assertEqual(self.library.probe_curtain_set_calls(), 0 if NO_SCREEN_CURTAIN else 2)
        self.assertEqual(self.library.probe_stat(2), 0)

    def test_imported_v4_curtain_gesture_respects_display_capability(self):
        content = default_config(replacements={1: 15}, version=4)
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.assertEqual(self.library.probe_mapping(1), 15)
        self.assertFalse(self.library.probe_curtain())
        self.assertEqual(self.library.probe_curtain_set_calls(), 0)
        self.touch("TOUCHEVENT_PRESS", 300, 400, 10)
        self.touch("TOUCHEVENT_CONTACT", 250, 400, 40)
        self.touch("TOUCHEVENT_CONTACT", 200, 400, 70)
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 200, 400, 100),
                         self.constant("ACTION_NONE"))
        self.assertEqual(bool(self.library.probe_curtain()), not NO_SCREEN_CURTAIN)
        self.assertEqual(self.library.probe_curtain_set_calls(), 0 if NO_SCREEN_CURTAIN else 1)
        if NO_SCREEN_CURTAIN:
            self.assertEqual(self.library.probe_stat(7),
                             self.constant("LANG_ACCESSIBILITY_CURTAIN_UNAVAILABLE"))
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_disk_content(), content)

    def selectable_action_labels(self):
        labels = [
            "LANG_ACCESSIBILITY_UNASSIGNED", "LANG_ACCESSIBILITY_UP", "LANG_ACCESSIBILITY_DOWN",
            "LANG_ACCESSIBILITY_LEFT", "LANG_ACCESSIBILITY_RIGHT", "LANG_ACCESSIBILITY_ACTIVATE",
            "LANG_BACK", "LANG_MAIN_MENU", "LANG_ACCESSIBILITY_CONTEXT", "LANG_ACCESSIBILITY_VOLUME_UP",
            "LANG_ACCESSIBILITY_VOLUME_DOWN", "LANG_ACCESSIBILITY_BATTERY", "LANG_ACCESSIBILITY_LAUNCH",
            "LANG_ACCESSIBILITY_SHUTDOWN", "LANG_ACCESSIBILITY_LOCK",
        ]
        if not NO_SCREEN_CURTAIN:
            labels.append("LANG_ACCESSIBILITY_CURTAIN")
        labels.extend(["LANG_ACCESSIBILITY_ACTION_TIME", "LANG_ACCESSIBILITY_TOGGLE_ESPEAK",
                       "LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES", "LANG_ACCESSIBILITY_TOGGLE_TOUCH",
                       "LANG_ACCESSIBILITY_ACTION_DATE", "LANG_ACCESSIBILITY_ACTION_SUMMARY",
                       "LANG_ACCESSIBILITY_ACTION_FIRST", "LANG_ACCESSIBILITY_ACTION_LAST",
                       "LANG_ACCESSIBILITY_ACTION_PAGE_FIRST", "LANG_ACCESSIBILITY_ACTION_PAGE_LAST",
                       "LANG_ACCESSIBILITY_SHORTCUT_ACTION"])
        return [self.constant(label) for label in labels]

    def test_gesture_selector_options_match_display_capability(self):
        self.gesture_script([1, 0, -1, -1], choice=1)
        self.assertEqual(self.library.accessibility_menu(), 0)
        expected = self.selectable_action_labels()
        self.assertEqual(self.library.probe_option_count(), 26 if NO_SCREEN_CURTAIN else 27)
        self.assertEqual([self.library.probe_option_voice(index) for index in range(len(expected))], expected)
        self.assertEqual(self.library.probe_option_initial_choice(), 1)
        self.assertEqual(self.library.probe_stat(2), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_selector_options_keep_system_default_distinct_from_curtain(self):
        system_option = 26 if NO_SCREEN_CURTAIN else 27
        self.script([0, 0, -1, -1], choice=system_option)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        expected = self.selectable_action_labels() + [self.constant("LANG_ACCESSIBILITY_SYSTEM_DEFAULT")]
        self.assertEqual(self.library.probe_option_count(), system_option + 1)
        self.assertEqual([self.library.probe_option_voice(index) for index in range(len(expected))], expected)
        self.assertEqual(self.library.probe_option_initial_choice(), system_option)
        self.assertEqual(self.library.probe_button_mapping(0, 0), self.constant("ACCESSIBILITY_ACTION_SYSTEM"))
        self.assertEqual(self.library.probe_stat(2), 0)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "Physical guide is R1-only")
    def test_default_button_rows_speak_real_action_after_system_label(self):
        self.library.probe_row(0, 3)
        spoken = [self.library.probe_spoken(index) for index in range(self.library.probe_stat(6))]
        self.assertIn(self.constant("LANG_ACCESSIBILITY_SYSTEM_DEFAULT"), spoken)
        self.assertIn(self.constant("LANG_ACCESSIBILITY_DEFAULT_IN_MENU"), spoken)
        self.assertEqual(spoken[-1], self.constant("LANG_ACCESSIBILITY_DEFAULT_POWER_HOLD"))

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "Physical guide is R1-only")
    def test_unassigned_volume_row_speaks_volume_not_menu_navigation(self):
        self.library.probe_button_assign(3, 0, 0)
        self.library.probe_row(3, 0)
        self.assertEqual(self.library.probe_spoken(self.library.probe_stat(6) - 1),
                         self.constant("LANG_ACCESSIBILITY_VOLUME_UP"))

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "Physical guide is R1-only")
    def test_guide_rejects_invalid_rows_without_speech_or_memory_access(self):
        for selected in (-1, 20, 999):
            count = self.library.probe_stat(6)
            self.assertEqual(self.library.probe_guide_row(selected, self.constant("CONTEXT_STD")), b"")
            self.assertEqual(self.library.probe_stat(6), count)

    @unittest.skipIf(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"), "Physical guide is R1-only")
    def test_guide_cancellation_never_saves_or_changes_mappings(self):
        self.script([4, -1, -1])
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_button_mapping(0, 0), self.constant("ACCESSIBILITY_ACTION_SYSTEM"))

    def test_keyboard_session_uses_private_touch_queue_not_global_gestures(self):
        self.library.probe_typing(True)
        self.assertEqual(self.touch("TOUCHEVENT_PRESS", 40, 45, 10, "CONTEXT_KEYBOARD"),
                         self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 40, 45, 40, "CONTEXT_KEYBOARD"),
                         self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.poll(100, "CONTEXT_KEYBOARD"), self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.library.probe_typing_dispatches(), 3)
        self.assertIsNone(self.point())
        self.library.probe_typing(False)
        self.assertEqual(self.touch("TOUCHEVENT_PRESS", 40, 45, 110), self.constant("ACTION_NONE"))

    def test_simulated_keyboard_preserves_configured_navigation_gestures(self):
        self.library.probe_typing(True)
        self.library.probe_typing_mode(2)
        self.touch("TOUCHEVENT_PRESS", 300, 400, 10, "CONTEXT_KEYBOARD")
        self.touch("TOUCHEVENT_CONTACT", 250, 400, 40, "CONTEXT_KEYBOARD")
        self.touch("TOUCHEVENT_CONTACT", 200, 400, 70, "CONTEXT_KEYBOARD")
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 200, 400, 100, "CONTEXT_KEYBOARD"),
                         self.constant("ACTION_KBD_UP"))
        self.assertEqual(self.library.probe_typing_dispatches(), 0)

    def test_invalid_versions_types_bounds_and_trailing_content(self):
        valid = default_config()
        cases = [b"", valid.replace(b"RBACCESSIBILITY:11", b"RBACCESSIBILITY:12", 1), valid.replace(b"enabled:1", b"enabled:2"),
                 valid.replace(b"enabled:1", b"enabled:-1"), valid.replace(b"enabled:1", b"enabled:true"),
                 valid.replace(b"enabled:1", b"enabled:01"), valid.replace(b"gesture:1:1", b"gesture:1:27"),
                 valid.replace(b"gesture:1:1", b"gesture:1:9999999999999999999999999999"),
                 valid.replace(b"gesture:1:1", b"gesture:1:+1"), valid.replace(b"gesture:1:1", b"gesture:01:1"),
                 valid.replace(b"gesture:2:2", b"gesture:1:2"), valid.replace(b"gesture:1:1", b"gesture:0:1"),
                 valid.replace(b"gesture:18:0", b"gesture:19:0"), valid + b"\n", valid + b"\0",
                 valid.replace(b"\n", b"\r\n"), valid.replace(b"gesture:", b"unknown:", 1), b"x" * 513]
        for index, content in enumerate(cases):
            with self.subTest(index=index):
                self.assertEqual(self.parse(content), 0)

    def test_load_complete_partial_reads_and_only_once(self):
        self.library.probe_reset()
        content = default_config(enabled=0, replacements={1: 10})
        self.library.probe_disk(content, len(content))
        self.library.probe_chunks(1, 0)
        self.library.accessibility_init()
        self.assertFalse(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_mapping(1), 10)
        self.library.probe_disk(b"broken", 6)
        self.library.accessibility_init()
        self.assertEqual(self.library.probe_mapping(1), 10)
        self.assertEqual(self.library.probe_stat(0), 1)

    def test_bad_read_close_missing_and_oversized_use_clean_defaults(self):
        cases = [(default_config(enabled=0), 1), (default_config(enabled=0), 2),
                 (default_config(enabled=0), 3), (b"x" * 513, 0), (b"bad", 0)]
        for content, fault in cases:
            with self.subTest(fault=fault, length=len(content)):
                self.library.probe_reset()
                self.library.probe_disk(content, len(content))
                self.library.probe_fault(fault)
                self.library.accessibility_init()
                self.assertEqual(self.library.probe_mapping(1), 1)
                expected = not bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"))
                self.assertEqual(bool(self.library.accessibility_enabled()), expected)
                self.assertEqual(self.library.probe_stat(2), 0)

    def test_reapply_mode_restore_and_no_reload(self):
        self.library.probe_stock_mode(1)
        self.assertTrue(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_mode(), 0)
        self.library.accessibility_init()
        self.assertEqual(self.library.probe_mode(), 0)
        self.library.probe_enable(False)
        self.assertEqual(self.library.probe_mode(), 1)
        self.library.probe_stock_mode(0)
        self.library.accessibility_init()
        self.assertEqual(self.library.probe_mode(), 0)

    def test_atomic_save_partial_writes_and_reload(self):
        self.library.probe_chunks(0, 1)
        self.assertEqual(self.library.probe_save(), 1)
        content = self.library.probe_disk_content()
        self.assertEqual(content, default_config(clicks=7, factory=True))
        self.assertGreater(self.library.probe_stat(2), 100)
        self.assertEqual(self.library.probe_stat(3), 1)
        self.assertEqual(self.library.probe_stat(4), 0)
        self.assertEqual(self.parse(content), 1)

    def test_save_failure_preserves_previous_file(self):
        for fault in range(4, 11):
            with self.subTest(fault=fault):
                self.setUp()
                old = default_config(replacements={1: 7})
                self.library.probe_disk(old, len(old))
                self.library.probe_chunks(0, 7)
                self.library.probe_fault(fault)
                self.assertEqual(self.library.probe_save(), 0)
                self.assertEqual(self.library.probe_disk_content(), old)
                self.assertEqual(self.library.probe_stat(3), 1 if fault == 9 else 0)
                if fault != 4:
                    self.assertEqual(self.library.probe_stat(1), 1)
                    self.assertEqual(self.library.probe_stat(4), 1)

    def test_save_invalid_mapping_never_opens_destination(self):
        self.library.probe_assign(18, 255)
        self.assertEqual(self.library.probe_save(), 0)
        self.assertEqual(self.library.probe_stat(0), 1)
        self.assertEqual(self.library.probe_stat(2), 0)

    def test_trial_confirm_persists_only_after_prompt(self):
        self.assertEqual(self.library.probe_trial(8, 0, 100), 0)
        self.assertEqual(self.library.probe_stat(9), 0)
        self.assertEqual(self.library.probe_stat(11), 8)
        self.assertEqual(self.library.probe_stat(8), 2000)
        self.assertEqual(self.library.probe_mapping(1), 8)
        self.assertEqual(self.library.probe_disk_content(),
                         default_config(replacements={1: 8}, playback_gestures={}, factory=True))
        self.assertEqual(self.library.probe_stat(14), 0)

    def test_trial_cancel_timeout_usb_and_late_confirm_rollback(self):
        for answer, elapsed in [(1, 0), (2, 0), (1, 2000), (0, 2000), (0, 2100)]:
            with self.subTest(answer=answer, elapsed=elapsed):
                self.setUp()
                self.assertEqual(self.library.probe_trial(0, answer, elapsed), 313 if answer == 2 else 0)
                self.assertEqual(self.library.probe_mapping(1), 1)
                self.assertEqual(self.library.probe_stat(2), 0)
                self.assertEqual(self.library.probe_stat(14), 0)
                self.assertEqual(self.library.probe_mode(), 0)

    def test_trial_save_failure_reverts_live_mapping(self):
        for fault in range(4, 11):
            with self.subTest(fault=fault):
                self.setUp()
                self.library.probe_chunks(0, 7)
                self.library.probe_fault(fault)
                self.library.probe_trial(8, 0, 0)
                self.assertEqual(self.library.probe_mapping(1), 1)
                self.assertEqual(self.library.probe_stat(7), self.constant("LANG_ERROR_WRITING_CONFIG"))
                self.assertEqual(self.library.probe_stat(14), 0)

    def test_trial_expiry_from_enabled_cancels_contact_and_handles_wrap(self):
        self.library.probe_time(0xfffffff0)
        self.library.probe_start_trial(8)
        self.library.probe_time((0xfffffff0 + 1999) & 0xffffffff)
        self.library.accessibility_enabled()
        self.assertEqual(self.library.probe_mapping(1), 8)
        self.touch("TOUCHEVENT_PRESS", 10, 20, 0)
        self.library.probe_time((0xfffffff0 + 2000) & 0xffffffff)
        self.library.accessibility_enabled()
        self.assertEqual(self.library.probe_mapping(1), 1)
        self.assertEqual(self.library.probe_stat(14), 0)
        self.assertEqual(self.poll(600), self.constant("ACTION_NONE"))

    def test_standard_semantic_mapping_and_explicit_volume(self):
        expected = ["ACTION_NONE", "ACTION_STD_PREV", "ACTION_STD_NEXT", "ACTION_STD_CANCEL",
                    "ACTION_STD_OK", "ACTION_STD_OK", "ACTION_STD_CANCEL", "ACTION_STD_MENU",
                    "ACTION_STD_CONTEXT", "ACTION_NONE", "ACTION_NONE"]
        for action, result in enumerate(expected):
            self.assertEqual(self.library.probe_action(action, self.constant("CONTEXT_STD")), self.constant(result))
        self.assertEqual(self.library.probe_stat(5), 0)

    def test_reader_semantic_mapping(self):
        context = self.constant("CONTEXT_CUSTOM") | self.constant("CONTEXT_CUSTOM2") | self.constant("CONTEXT_STD")
        expected = ["ACTION_SETTINGS_DEC", "ACTION_SETTINGS_INC", "ACTION_STD_PREV", "ACTION_STD_NEXT",
                    "ACTION_STD_OK", "ACTION_STD_CANCEL", "ACTION_STD_MENU", "ACTION_STD_CONTEXT"]
        for action, result in enumerate(expected, 1):
            self.assertEqual(self.library.probe_action(action, context), self.constant(result))

    def test_wps_semantic_mapping(self):
        expected = ["ACTION_WPS_VOLUP", "ACTION_WPS_VOLDOWN", "ACTION_WPS_SKIPPREV", "ACTION_WPS_SKIPNEXT",
                    "ACTION_WPS_PLAY", "ACTION_WPS_BROWSE", "ACTION_WPS_MENU", "ACTION_WPS_CONTEXT"]
        for action, result in enumerate(expected, 1):
            self.assertEqual(self.library.probe_action(action, self.constant("CONTEXT_WPS")), self.constant(result))

    def test_keyboard_semantic_mapping(self):
        expected = ["ACTION_KBD_UP", "ACTION_KBD_DOWN", "ACTION_KBD_LEFT", "ACTION_KBD_RIGHT",
                    "ACTION_KBD_SELECT", "ACTION_KBD_ABORT", "ACTION_KBD_DONE", "ACTION_KBD_BACKSPACE"]
        for context in ["CONTEXT_KEYBOARD", "CONTEXT_MORSE_INPUT"]:
            for action, result in enumerate(expected, 1):
                self.assertEqual(self.library.probe_action(action, self.constant(context)), self.constant(result))

    def test_settings_quickscreen_and_yesno_semantics(self):
        for context in ["CONTEXT_SETTINGS", "CONTEXT_SETTINGS_EQ", "CONTEXT_SETTINGS_COLOURCHOOSER",
                        "CONTEXT_SETTINGS_TIME", "CONTEXT_SETTINGS_RECTRIGGER"]:
            for action, result in enumerate(["ACTION_SETTINGS_INC", "ACTION_SETTINGS_DEC",
                                             "ACTION_STD_PREV", "ACTION_STD_NEXT"], 1):
                self.assertEqual(self.library.probe_action(action, self.constant(context)), self.constant(result))
        for action, result in enumerate(["ACTION_QS_TOP", "ACTION_QS_DOWN", "ACTION_QS_LEFT", "ACTION_QS_RIGHT"], 1):
            self.assertEqual(self.library.probe_action(action, self.constant("CONTEXT_QUICKSCREEN")), self.constant(result))
        self.assertEqual(self.library.probe_action(5, self.constant("CONTEXT_YESNOSCREEN")),
                         self.constant("ACTION_YESNO_ACCEPT"))

    def test_single_tap_deferred_and_never_activates(self):
        self.assertEqual(self.touch("TOUCHEVENT_PRESS", 40, 50, 0), self.constant("ACTION_NONE"))
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 40, 50, 50), self.constant("ACTION_NONE"))
        self.assertEqual(self.poll(370), self.constant("ACTION_NONE"))
        self.assertEqual(self.poll(380), self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.point(), (40, 50, True))
        self.assertIsNone(self.point())
        self.assertEqual(self.poll(400), self.constant("ACTION_NONE"))

    def test_double_tap_activates_focus_without_exploration(self):
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 50)
        self.touch("TOUCHEVENT_PRESS", 300, 700, 100)
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 300, 700, 150), self.constant("ACTION_NONE"))
        self.assertEqual(self.poll(470), self.constant("ACTION_NONE"))
        self.assertEqual(self.poll(480), self.constant("ACTION_STD_OK"))
        self.assertIsNone(self.point())
        self.assertEqual(self.poll(600), self.constant("ACTION_NONE"))

    def test_default_unassigned_triple_consumes_all_taps_without_activating_double(self):
        self.assertEqual(self.library.probe_mapping(17), 5)
        self.assertEqual(self.library.probe_mapping(19), 0)
        for press_ms, position_x, position_y in ((0, 40, 50), (100, 300, 700), (200, 60, 90)):
            self.assertEqual(self.touch("TOUCHEVENT_PRESS", position_x, position_y, press_ms),
                             self.constant("ACTION_NONE"))
            self.assertEqual(self.touch("TOUCHEVENT_RELEASE", position_x, position_y, press_ms + 50),
                             self.constant("ACTION_NONE"))
            self.assertIsNone(self.point())
        for milliseconds in (570, 580, 1000):
            self.assertEqual(self.poll(milliseconds), self.constant("ACTION_NONE"))
            self.assertIsNone(self.point())
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_stat(5), 0)
        self.assertEqual(self.library.probe_time_calls(), 0)
        self.assertEqual(self.library.probe_date_calls(), 0)
        self.assertEqual(self.library.probe_summary_calls(), 0)
        self.assertEqual(self.library.probe_extra(1), 0)
        self.assertEqual(self.library.probe_navigation_requests(), 0)

    def test_new_triple_date_mapping_executes_once_without_double_or_exploration(self):
        content = default_config(replacements={19: 20})
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        for press_ms in (0, 100, 200):
            self.assertEqual(self.touch("TOUCHEVENT_PRESS", 100, 100, press_ms), self.constant("ACTION_NONE"))
            self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 100, 100, press_ms + 50), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_date_calls(), 1)
        self.assertEqual(self.library.probe_date_enqueue(), 0)
        self.assertIsNone(self.point())
        self.assertEqual(self.poll(1000), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_date_calls(), 1)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_disk_content(), content)

    def test_exploration_first_forced_then_changed_point(self):
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.assertEqual(self.poll(220), self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.point(), (40, 50, True))
        self.assertEqual(self.touch("TOUCHEVENT_CONTACT", 42, 52, 230), self.constant("ACTION_TOUCHSCREEN"))
        self.assertEqual(self.point(), (42, 52, False))
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 42, 52, 240), self.constant("ACTION_NONE"))

    def test_default_strokes_and_pairs(self):
        cases = [([(100, 100), (60, 100)], "ACTION_STD_PREV"),
                 ([(100, 100), (140, 100)], "ACTION_STD_NEXT"),
                 ([(100, 100), (100, 60)], "ACTION_STD_CANCEL"),
                 ([(100, 100), (100, 140)], "ACTION_STD_OK"),
                 ([(100, 100), (60, 100), (100, 100)], "ACTION_STD_CANCEL"),
                 ([(100, 100), (140, 100), (100, 100)], "ACTION_STD_MENU")]
        for coordinates, expected in cases:
            with self.subTest(expected=expected, coordinates=coordinates):
                self.library.accessibility_reset()
                self.touch("TOUCHEVENT_PRESS", *coordinates[0], 0)
                for index, point in enumerate(coordinates[1:], 1):
                    self.touch("TOUCHEVENT_CONTACT", *point, index * 30)
                self.assertEqual(self.touch("TOUCHEVENT_RELEASE", *coordinates[-1], 150), self.constant(expected))
                self.assertIsNone(self.point())

    def test_unassigned_stroke_and_double_tap_are_consumed_without_fallback(self):
        self.library.probe_assign(1, 0)
        self.touch("TOUCHEVENT_PRESS", 100, 100, 0)
        self.touch("TOUCHEVENT_CONTACT", 60, 100, 30)
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 60, 100, 100), self.constant("ACTION_NONE"))
        self.assertIsNone(self.point())
        self.assertEqual(self.poll(500), self.constant("ACTION_NONE"))
        self.library.probe_assign(17, 0)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 600)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 650)
        self.touch("TOUCHEVENT_PRESS", 300, 700, 700)
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 300, 700, 750), self.constant("ACTION_NONE"))
        self.assertIsNone(self.point())
        self.assertEqual(self.poll(1200), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_stat(5), 0)

    def test_editor_speaks_unassigned_without_changing_default_bindings(self):
        self.gesture_script([1, -1, -1])
        self.library.accessibility_menu()
        spoken = [self.library.probe_spoken(index) for index in range(self.library.probe_stat(6))]
        self.assertIn(self.constant("LANG_ACCESSIBILITY_UNASSIGNED"), spoken)
        for slot, action in [(1, 1), (2, 2), (3, 3), (4, 4), (5, 6), (8, 7), (17, 5)]:
            self.assertEqual(self.library.probe_mapping(slot), action)

    def test_context_reused_target_reset_and_plugin_suppression(self):
        self.library.probe_target(1)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 50)
        self.library.probe_target(1)
        self.assertEqual(self.poll(400), self.constant("ACTION_NONE"))
        self.library.probe_target(2)
        self.assertIsNone(self.point())
        self.touch("TOUCHEVENT_PRESS", 40, 50, 500)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 550)
        self.assertEqual(self.poll(900, "CONTEXT_WPS"), self.constant("ACTION_NONE"))
        context = self.constant("CONTEXT_PLUGIN") | self.constant("CONTEXT_STD")
        self.assertEqual(self.touch("TOUCHEVENT_PRESS", 10, 10, 1000, context), self.constant("ACTION_NONE"))
        self.assertEqual(self.poll(1500), self.constant("ACTION_NONE"))

    def test_all_sixteen_strokes_use_their_own_editor_slot(self):
        steps = {1: (-40, 0), 2: (40, 0), 3: (0, -40), 4: (0, 40)}
        strokes = [(1,), (2,), (3,), (4,), (1, 2), (1, 3), (1, 4), (2, 1),
                   (2, 3), (2, 4), (3, 1), (3, 2), (3, 4), (4, 1), (4, 2), (4, 3)]
        for slot, directions in enumerate(strokes, 1):
            with self.subTest(slot=slot, directions=directions):
                self.setUp()
                self.library.probe_assign(slot, 8)
                position_x, position_y = 100, 100
                self.touch("TOUCHEVENT_PRESS", position_x, position_y, 0)
                for index, direction in enumerate(directions, 1):
                    delta_x, delta_y = steps[direction]
                    position_x += delta_x
                    position_y += delta_y
                    self.touch("TOUCHEVENT_CONTACT", position_x, position_y, index * 30)
                self.assertEqual(self.touch("TOUCHEVENT_RELEASE", position_x, position_y, 150),
                                 self.constant("ACTION_STD_CONTEXT"))
                self.assertIsNone(self.point())

    def test_editor_spoken_pairs_identify_order_and_assignment(self):
        self.gesture_script([1, -1, -1])
        self.library.accessibility_menu()
        spoken = [self.library.probe_spoken(index) for index in range(self.library.probe_stat(6))]
        expected = [self.constant("LANG_ACCESSIBILITY_SWIPE_LEFT_RIGHT"), self.constant("LANG_BACK")]
        self.assertTrue(any(spoken[index:index + 2] == expected for index in range(len(spoken) - 1)))
        expected = [self.constant("LANG_ACCESSIBILITY_SWIPE_RIGHT_LEFT"), self.constant("LANG_MAIN_MENU")]
        self.assertTrue(any(spoken[index:index + 2] == expected for index in range(len(spoken) - 1)))
        self.assertIn(self.constant("LANG_ACCESSIBILITY_DOUBLE_TAP"), spoken)
        self.assertIn(self.constant("LANG_ACCESSIBILITY_HOLD"), spoken)

    def test_poll_timeout_only_for_pending_contact_tap_or_trial(self):
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), -1)
        self.assertEqual(self.library.accessibility_adjust_timeout(100), 100)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), 5)
        self.assertEqual(self.library.accessibility_adjust_timeout(100), 5)
        self.assertEqual(self.library.accessibility_adjust_timeout(2), 2)
        self.assertEqual(self.library.accessibility_adjust_timeout(0), 0)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 50)
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), 5)
        self.poll(400)
        self.point()
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), -1)
        self.library.probe_enable(False)
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), -1)
        self.library.probe_start_trial(8)
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), 5)
        self.library.probe_time(2400)
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), -1)

    def test_reset_disable_invalid_event_and_null_outputs(self):
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.poll(220)
        self.assertFalse(self.library.accessibility_explore_point(None, None, None))
        self.assertEqual(self.point(), (40, 50, True))
        self.library.accessibility_reset()
        self.assertEqual(self.poll(230), self.constant("ACTION_NONE"))
        self.touch("TOUCHEVENT_PRESS", 40, 50, 300)
        self.assertEqual(self.library.probe_touch(999, 0, 0, 310, self.constant("CONTEXT_STD")), self.constant("ACTION_NONE"))
        self.assertEqual(self.poll(600), self.constant("ACTION_NONE"))
        self.library.probe_enable(False)
        self.assertEqual(self.touch("TOUCHEVENT_PRESS", 40, 50, 700), self.constant("ACTION_NONE"))

    def test_optional_hold_maps_current_focus_and_is_default_disabled(self):
        self.assertEqual(self.library.probe_mapping(18), 0)
        self.library.probe_assign(18, 8)
        self.touch("TOUCHEVENT_PRESS", 300, 700, 0)
        self.assertEqual(self.poll(900), self.constant("ACTION_STD_CONTEXT"))
        self.assertIsNone(self.point())
        self.assertEqual(self.poll(1200), self.constant("ACTION_NONE"))

    def test_empty_announcement_uses_complete_language_id(self):
        self.library.accessibility_speak_empty()
        self.assertEqual(self.library.probe_stat(6), 0)
        self.library.probe_empty_mode(1)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.poll(230)
        self.assertEqual(self.point(), (40, 50, True))
        self.library.probe_feedback(1, -1, False)
        self.library.accessibility_speak_empty()
        self.assertEqual(self.library.probe_spoken(0), self.constant("LANG_ACCESSIBILITY_EMPTY"))
        self.assertEqual(self.library.probe_spoken_enqueue(0), 0)
        self.assertEqual(self.library.probe_stat(6), 1)
        self.library.accessibility_speak_empty()
        self.assertEqual(self.library.probe_stat(6), 1)

    def test_actual_editor_all_slots_and_persisted_selection(self):
        self.gesture_script([1, 0, -1, -1], choice=8)
        self.assertEqual(self.library.accessibility_menu(), 0)
        self.assertEqual(self.library.probe_mapping(1), 8)
        self.assertGreaterEqual(self.library.probe_stat(12), 40)
        self.assertEqual(self.library.probe_disk_content(),
                         default_config(replacements={1: 8}, playback_gestures={}, factory=True))

    def test_actual_menu_reset_enable_and_no_phantom_physical_plugin(self):
        self.library.probe_assign(1, 8)
        self.script([7, -1])
        self.assertEqual(self.library.accessibility_menu(), 0)
        self.assertEqual(self.library.probe_mapping(1), 1)
        self.script([0, -1])
        self.assertEqual(self.library.accessibility_menu(), 0)
        expected = bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET"))
        self.assertEqual(bool(self.library.accessibility_enabled()), expected)
        self.script([7, -1])
        self.assertEqual(self.library.accessibility_menu(), 0)
        self.assertEqual(self.library.probe_stat(13), 0)
        self.assertEqual(self.library.probe_plugin_path(), b"")

    def test_menu_usb_and_option_usb_do_not_persist(self):
        for choices in [[-313], [1, -313], [1, 0]]:
            with self.subTest(choices=choices):
                self.setUp()
                if choices[0] == 1:
                    self.gesture_script(choices, choice=-313)
                else:
                    self.script(choices, choice=-313)
                self.assertEqual(self.library.accessibility_menu(), 313)
                self.assertEqual(self.library.probe_stat(2), 0)

    def test_v1_v2_and_v3_migrate_without_losing_gestures_or_feedback(self):
        for legacy, version in [(True, 1), (False, 2), (False, 3)]:
            self.setUp()
            content = default_config(replacements={1: 8, 17: 0}, legacy=legacy,
                                     version=version, clicks=2, hold=900)
            self.library.probe_disk(content, len(content))
            self.library.probe_reload()
            self.assertEqual(self.library.probe_mapping(1), 8)
            self.assertEqual(self.library.probe_mapping(17), 0)
            self.assertEqual(self.library.accessibility_keyclick_sources(), 7 if legacy else 2)
            self.assertEqual(self.library.probe_extra(5), 700 if legacy else 900)
            self.assertEqual(self.library.probe_button_mapping(4, 0), self.constant("ACCESSIBILITY_ACTION_SYSTEM"))
            self.assertEqual(self.library.probe_stat(2), 0)
            self.assertEqual(self.library.probe_save(), 1)
            self.assertTrue(self.library.probe_disk_content().startswith(b"RBACCESSIBILITY:11\n"))

    def test_v4_feedback_hold_button_and_launch_ranges_are_strict(self):
        valid = default_config(version=4)
        invalid = [default_config(clicks=value, version=4) for value in [0, 4, -1, 999999999999999999999]]
        invalid += [default_config(hold=value, version=4) for value in [0, 299, 301, 2001, 99999999999999999]]
        invalid += [valid.replace(b"button:0:0:16:0", replacement) for replacement in [
            b"button:0:0:17:0", b"button:5:0:16:0", b"button:0:4:16:0",
            b"button:0:0:16:8", b"button:0:0:16:4", b"button:00:0:16:0"]]
        invalid += [default_config(version=4, replacements={1: 12}, gesture_refs={1: 4}),
                    default_config(version=4, replacements={1: 12}, gesture_refs={1: 8}),
                    default_config(version=4, gesture_refs={1: 1}), b"x" * 4097]
        for content in invalid:
            self.assertEqual(self.parse(content), 0, content[:100])

    def test_all_versions_preserve_each_accepted_action_and_system_default(self):
        for version, maximum in VERSION_ACTION_LIMITS.items():
            for action in range(maximum + 1):
                with self.subTest(version=version, action=action):
                    self.setUp()
                    content = default_config(version=version,
                        replacements={slot: action for slot in range(1, 21 if version >= 7 else 19)},
                        buttons={(button, slot): action for button in range(5) for slot in range(4)
                                 if (button, slot) != (0, 0)})
                    self.library.probe_disk(content, len(content))
                    self.library.probe_chunks(1, 1)
                    self.library.probe_reload()
                    for slot in range(1, 21 if version >= 7 else 19):
                        self.assertEqual(self.library.probe_mapping(slot), action)
                    for button in range(5):
                        for slot in range(4):
                            self.assertEqual(self.library.probe_button_mapping(button, slot),
                                27 if version == 1 or (button, slot) == (0, 0) else action)
                    if version < 7:
                        self.assertEqual(self.library.probe_mapping(19), 0)
                        self.assertEqual(self.library.probe_mapping(20), 8)
                    self.assertEqual(self.library.probe_touch_hold(), 900)
                    self.assertEqual(self.library.probe_stroke_repeat(), 0)
                    self.assertEqual(self.library.probe_time_calls(), 0)
                    self.assertEqual(self.library.probe_stat(2), 0)
                    self.assertEqual(self.library.probe_save(), 1)
                    migrated = default_config(
                        replacements={slot: action for slot in range(1, 21 if version >= 7 else 19)},
                        clicks=7 if version == 1 or version >= 8 else 3,
                        buttons=None if version == 1 else {
                            (button, slot): action for button in range(5) for slot in range(4)
                            if (button, slot) != (0, 0)})
                    self.assertEqual(self.library.probe_disk_content(), migrated)
                    self.library.probe_reload()
                    self.assertEqual(self.library.probe_mapping(18), action)
                    self.assertEqual(self.library.probe_button_mapping(0, 0), 27)

    def test_action_limits_are_strict_for_every_config_version(self):
        actions = list(range(-1, 30)) + [255, 256, 99999999999999999999999999999999]
        for version, maximum in VERSION_ACTION_LIMITS.items():
            for action in actions:
                with self.subTest(version=version, gesture=action):
                    self.assertEqual(self.parse(default_config(version=version, replacements={18: action})),
                                     int(0 <= action <= maximum))
            if version == 1:
                continue
            for action in actions:
                with self.subTest(version=version, button=action):
                    self.assertEqual(self.parse(default_config(version=version, buttons={(4, 3): action})),
                                     int(0 <= action <= maximum + 1))
        for version in [0, 12, 13, -1, "05", "5 ", "06", "6 ", "07", "7 ", "08", "8 ", "09", "9 ", "010", "10 "]:
            self.assertEqual(self.parse(default_config().replace(b"RBACCESSIBILITY:11\n",
                f"RBACCESSIBILITY:{version}\n".encode(), 1)), 0)

    def test_v3_v4_v5_v6_migrate_launch_paths_refs_feedback_and_hold_losslessly(self):
        for version in (3, 4, 5, 6):
            with self.subTest(version=version):
                self.setUp()
                arguments = dict(enabled=0, replacements={1: 12, 2: 12, 3: 12, 17: 14},
                    buttons={(1, 0): 12, (4, 3): 12}, gesture_refs={1: 4, 2: 1, 3: 2},
                    button_refs={(1, 0): 7, (4, 3): 3}, clicks=1, hold=1100,
                    paths={0: "/.rockbox/rocks/apps/calculator.rock",
                           3: "/.rockbox/rocks/apps/stopwatch.rock"})
                content = default_config(version=version, **arguments)
                self.library.probe_disk(content, len(content))
                self.library.probe_chunks(7, 5)
                self.library.probe_reload()
                self.assertEqual(self.library.probe_ref(-1, 1), 4)
                self.assertEqual(self.library.probe_ref(1, 0), 7)
                self.assertEqual(self.library.accessibility_keyclick_sources(), 1)
                self.assertEqual(self.library.probe_extra(5), 1100)
                self.assertEqual(self.library.probe_save(), 1)
                self.assertEqual(self.library.probe_disk_content(), default_config(**arguments))
                self.library.probe_reload()
                self.assertEqual(self.library.probe_path(3), arguments["paths"][3].encode())
                self.assertEqual(self.library.probe_mapping(17), 14)

    def test_v4_system16_migrates_to22_while_curtain15_stays15(self):
        content = default_config(version=4, replacements={1: 15},
                                 buttons={(0, 0): 16, (1, 0): 15, (4, 2): 0})
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.assertEqual(self.library.probe_mapping(1), 15)
        self.assertEqual(self.library.probe_button_mapping(0, 0), 27)
        self.assertEqual(self.library.probe_button_mapping(1, 0), 15)
        self.assertEqual(self.library.probe_button_mapping(4, 2), 0)
        self.assertFalse(self.library.probe_curtain())
        self.assertEqual(self.library.probe_time_calls(), 0)
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_disk_content(), default_config(
            replacements={1: 15}, buttons={(0, 0): 27, (1, 0): 15, (4, 2): 0}, clicks=3))

    def test_time_curtain_toggles_system_cannot_inherit_launch_references(self):
        for version, sentinel in ((4, 16), (5, 17), (6, 19), (7, 22)):
            for action in range(15, sentinel + 1):
                for target in (1, 2, 3, 4, 7, 8, 9, 10, 11, 12):
                    with self.subTest(version=version, action=action, target=target):
                        arguments = dict(version=version, paths={
                            0: "/.rockbox/rocks/apps/calculator.rock",
                            3: "/.rockbox/rocks/apps/stopwatch.rock"})
                        if action != sentinel:
                            self.assertEqual(self.parse(default_config(replacements={1: action},
                                gesture_refs={1: target}, **arguments)), 0)
                        self.assertEqual(self.parse(default_config(buttons={(4, 3): action},
                            button_refs={(4, 3): target}, **arguments)), 0)

    def test_v5_time_and_system_atomic_save_sync_close_rename_and_reload(self):
        arguments = dict(replacements={1: 16, 18: 15}, buttons={(0, 0): 16, (1, 2): 15}, clicks=3)
        content = default_config(version=5, **arguments)
        self.library.probe_disk(content, len(content))
        self.library.probe_chunks(3, 1)
        self.library.probe_reload()
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_syncs(), 1)
        self.assertEqual(self.library.probe_stat(3), 1)
        self.assertEqual(self.library.probe_stat(4), 0)
        self.assertFalse(self.library.probe_temporary_exists())
        self.assertFalse(self.library.probe_temporary_open())
        self.assertEqual(self.library.probe_disk_content(), default_config(**arguments))
        self.library.probe_reload()
        self.assertEqual(self.library.probe_mapping(1), 16)
        self.assertEqual(self.library.probe_mapping(18), 15)
        self.assertEqual(self.library.probe_button_mapping(0, 0), 16)
        self.assertEqual(self.library.probe_button_mapping(1, 2), 15)
        self.assertEqual(self.library.probe_button_mapping(4, 3), 27)
        self.assertEqual(self.library.probe_time_calls(), 0)

    def test_v5_system17_migrates_to22_without_toggling_either_service(self):
        arguments = dict(replacements={1: 16}, buttons={
            (button, slot): 17 for button in range(5) for slot in range(4)})
        content = default_config(version=5, **arguments)
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.assertEqual(self.library.probe_mapping(1), 16)
        for button in range(5):
            for slot in range(4):
                self.assertEqual(self.library.probe_button_mapping(button, slot), 27)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_save(), 1)
        migrated = default_config(replacements={1: 16}, clicks=3)
        self.assertEqual(self.library.probe_disk_content(), migrated)
        self.library.probe_reload()
        for service in range(2):
            self.assertEqual(self.library.input_calls(service), 0)
        self.assertEqual(self.library.input_gate_calls(), 0)
        self.assertEqual(self.library.probe_time_calls(), 0)

    def test_failed_v7_save_preserves_each_legacy_file_and_removes_temporary(self):
        for version in range(1, 8):
            for fault in range(4, 11):
                with self.subTest(version=version, fault=fault):
                    self.setUp()
                    previous = default_config(version=version, replacements={1: 8})
                    self.library.probe_disk(previous, len(previous))
                    self.library.probe_reload()
                    self.library.probe_assign(1, 16)
                    self.library.probe_chunks(0, 7)
                    self.library.probe_fault(fault)
                    self.assertEqual(self.library.probe_save(), 0)
                    self.assertEqual(self.library.probe_disk_content(), previous)
                    self.assertFalse(self.library.probe_temporary_exists())
                    self.assertFalse(self.library.probe_temporary_open())
                    self.assertEqual(self.library.probe_mapping(1), 16)
                    self.assertEqual(self.library.probe_stat(3), int(fault == 9))
                    self.assertEqual(self.library.probe_syncs(), int(fault in (7, 8, 9)))
                    self.library.probe_fault(0)
                    self.library.probe_reload()
                    self.assertEqual(self.library.probe_mapping(1), 8)

    def test_v7_save_rejects_invalid_actions_without_opening_temporary(self):
        previous = default_config(replacements={1: 16})
        for button, actions in [(False, (27, 28, 255)), (True, (28, 255))]:
            for action in actions:
                with self.subTest(button=button, action=action):
                    self.setUp()
                    self.library.probe_disk(previous, len(previous))
                    if button:
                        self.library.probe_button_assign(4, 3, action)
                    else:
                        self.library.probe_assign(18, action)
                    self.assertEqual(self.library.probe_save(), 0)
                    self.assertEqual(self.library.probe_disk_content(), previous)
                    self.assertEqual(self.library.probe_stat(0), 1)
                    self.assertEqual(self.library.probe_stat(2), 0)
                    self.assertEqual(self.library.probe_syncs(), 0)

    def test_v7_default_fields_and_new_slots_have_exact_wire_positions(self):
        content = default_config(version=7)
        self.assertTrue(content.startswith(
            b"RBACCESSIBILITY:7\nenabled:1\nclick:3\nhold:700\ntouch_hold:900\nstroke_repeat:0\n"))
        self.assertIn(b"gesture:18:0:0\ngesture:19:0:0\ngesture:20:8:0\nbutton:0:0:22:0\n", content)
        self.assertEqual(content.count(b"gesture:"), 20)
        self.assertEqual(content.count(b"button:"), 20)
        self.assertEqual(content.count(b"target:"), 4)
        self.assertEqual(self.library.probe_touch_hold(), 900)
        self.assertEqual(self.library.probe_stroke_repeat(), 0)
        self.assertEqual(self.library.probe_mapping(18), 0)
        self.assertEqual(self.library.probe_mapping(19), 0)
        self.assertEqual(self.library.probe_mapping(20), 8)

    def test_v7_touch_hold_boundaries_repeat_and_new_slot_actions_round_trip(self):
        for touch_hold in range(300, 2001, 100):
            for repeat in (0, 1):
                with self.subTest(touch_hold=touch_hold, repeat=repeat):
                    self.setUp()
                    content = default_config(hold=1300, touch_hold=touch_hold, stroke_repeat=repeat,
                        replacements={19: 20, 20: 21}, buttons={(0, 0): 19, (4, 3): 21})
                    self.assertEqual(self.parse(content), 1)
                    self.library.probe_disk(content, len(content))
                    self.library.probe_chunks(1, 1)
                    self.library.probe_reload()
                    self.assertEqual(self.library.probe_touch_hold(), touch_hold)
                    self.assertEqual(self.library.probe_stroke_repeat(), repeat)
                    self.assertEqual(self.library.probe_extra(5), 1300)
                    self.assertEqual(self.library.probe_mapping(19), 20)
                    self.assertEqual(self.library.probe_mapping(20), 21)
                    self.assertEqual(self.library.probe_button_mapping(0, 0), 19)
                    self.assertEqual(self.library.probe_button_mapping(4, 3), 21)
                    self.assertEqual(self.library.probe_date_calls(), 0)
                    self.assertEqual(self.library.probe_summary_calls(), 0)
                    self.assertEqual(self.library.probe_stat(2), 0)
                    self.assertEqual(self.library.probe_save(), 1)
                    self.assertEqual(self.library.probe_disk_content(), content)

    def test_v7_new_fields_reject_noncanonical_and_out_of_range_values(self):
        invalid_numbers = ["", "-1", "+1", " 1", "1 ", "1\r", "01", "true", "1.0",
                           "0x1", "1\0", "99999999999999999999999999999999999999"]
        for field, numbers in (
            ("touch_hold", invalid_numbers + ["0", "299", "301", "899", "901", "1999", "2001", "65536"]),
            ("stroke_repeat", invalid_numbers + ["2", "255", "256", "-0", "00"])):
            for value in numbers:
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.parse(default_config(**{field: value})), 0)
        for slot in (19, 20):
            for action in (-1, 27, 28, 255, 256, "00", "+1", "99999999999999999999"):
                with self.subTest(slot=slot, action=action):
                    self.assertEqual(self.parse(default_config(replacements={slot: action})), 0)

    def test_v7_every_record_is_required_unique_and_in_order(self):
        records = default_config().splitlines(keepends=True)
        for index in range(len(records)):
            with self.subTest(index=index, mutation="missing"):
                self.assertEqual(self.parse(b"".join(records[:index] + records[index + 1:])), 0)
            with self.subTest(index=index, mutation="duplicate"):
                self.assertEqual(self.parse(b"".join(records[:index] + [records[index]] + records[index:])), 0)
            if index + 1 < len(records):
                with self.subTest(index=index, mutation="reordered"):
                    reordered = records.copy()
                    reordered[index:index + 2] = reordered[index:index + 2][::-1]
                    self.assertEqual(self.parse(b"".join(reordered)), 0)
        content = b"".join(records)
        for index in range(len(content)):
            with self.subTest(nul_offset=index):
                self.assertEqual(self.parse(content[:index] + b"\0" + content[index + 1:]), 0)

    def test_v1_through_v6_require_historical_records_and_default_only_new_features(self):
        for version in range(1, 7):
            with self.subTest(version=version):
                self.setUp()
                content = default_config(version=version, enabled=0, replacements={1: 8, 18: 10},
                                         clicks=1, hold=1600)
                self.assertEqual(content.count(b"gesture:"), 18)
                self.assertNotIn(b"touch_hold:", content)
                self.assertNotIn(b"stroke_repeat:", content)
                self.library.probe_disk(content, len(content))
                self.library.probe_reload()
                self.assertFalse(self.library.accessibility_enabled())
                self.assertEqual(self.library.probe_mapping(1), 8)
                self.assertEqual(self.library.probe_mapping(18), 10)
                self.assertEqual(self.library.probe_mapping(19), 0)
                self.assertEqual(self.library.probe_mapping(20), 8)
                self.assertEqual(self.library.probe_touch_hold(), 900)
                self.assertEqual(self.library.probe_stroke_repeat(), 0)
                self.assertEqual(self.library.probe_stat(2), 0)
                self.assertEqual(self.library.probe_disk_content(), content)
                for length in range(len(content)):
                    self.assertEqual(self.parse(content[:length]), 0, (version, length))
                for extra in (b"touch_hold:900\n", b"stroke_repeat:0\n",
                              b"gesture:19:0\n", b"gesture:19:0:0\n", b"gesture:20:8:0\n"):
                    self.assertEqual(self.parse(content.replace(b"gesture:1:", extra + b"gesture:1:", 1)), 0)
                self.assertEqual(self.library.probe_save(), 1)
                self.assertEqual(self.library.probe_disk_content(), default_config(enabled=0,
                    replacements={1: 8, 18: 10}, clicks=7 if version == 1 else 1,
                    hold=700 if version == 1 else 1600))

    def test_every_historical_system_sentinel_migrates_all_buttons_without_new_action_effects(self):
        for version, sentinel in ((2, 15), (3, 15), (4, 16), (5, 17), (6, 19)):
            with self.subTest(version=version, sentinel=sentinel):
                self.setUp()
                content = default_config(version=version, enabled=0, clicks=2, hold=1200,
                    buttons={(button, slot): sentinel for button in range(5) for slot in range(4)})
                self.library.probe_disk(content, len(content))
                self.library.probe_reload()
                for button in range(5):
                    for slot in range(4):
                        self.assertEqual(self.library.probe_button_mapping(button, slot), 27)
                self.assertFalse(self.library.accessibility_enabled())
                self.assertEqual(self.library.probe_stat(2), 0)
                self.assertEqual(self.library.probe_time_calls(), 0)
                self.assertEqual(self.library.probe_date_calls(), 0)
                self.assertEqual(self.library.probe_summary_calls(), 0)
                self.assertEqual([self.library.input_calls(service) for service in range(2)], [0, 0])
                self.assertFalse(self.library.probe_curtain())
                self.assertEqual(self.library.probe_save(), 1)
                self.assertEqual(self.library.probe_disk_content(), default_config(enabled=0, clicks=2, hold=1200))

    def test_launch_target_limits_follow_each_version_and_only_four_ids_reference_plugins(self):
        paths = {index: f"/.rockbox/rocks/apps/app{index}.rock" for index in range(4)}
        for target in range(256):
            self.assertEqual(bool(self.library.probe_plugin_target(target)), 4 <= target <= 7, target)
        for version in range(3, 8):
            maximum = 12 if version == 7 else 7
            for target in list(range(-1, 15)) + [255, 256, "00", "+1", "99999999999999999999"]:
                valid = isinstance(target, int) and 0 <= target <= maximum
                with self.subTest(version=version, target=target, binding="gesture"):
                    self.assertEqual(self.parse(default_config(version=version, replacements={1: 12},
                        gesture_refs={1: target}, paths=paths)), int(valid))
                with self.subTest(version=version, target=target, binding="button"):
                    self.assertEqual(self.parse(default_config(version=version, buttons={(4, 3): 12},
                        button_refs={(4, 3): target}, paths=paths)), int(valid))
        for target in range(8, 13):
            content = default_config(replacements={19: 12, 20: 12},
                gesture_refs={19: target, 20: target}, buttons={(4, 3): 12}, button_refs={(4, 3): target})
            with self.subTest(target=target, paths="empty"):
                self.assertEqual(self.parse(content), 1)
                self.library.probe_disk(content, len(content))
                self.library.probe_reload()
                self.assertEqual(self.library.probe_ref(-1, 19), target)
                self.assertEqual(self.library.probe_ref(-1, 20), target)
                self.assertEqual(self.library.probe_ref(4, 3), target)
                self.assertEqual(self.library.probe_save(), 1)
                self.assertEqual(self.library.probe_disk_content(), content)
                self.assertEqual([self.library.probe_path(index) for index in range(4)], [b""] * 4)

    def test_direct_destination_ids_dispatch_through_root_mock_without_plugin_path_access(self):
        destinations = [(8, "GO_TO_FILEBROWSER"), (9, "GO_TO_DBBROWSER"),
                        (10, "GO_TO_WPS"), (11, "GO_TO_MAINMENU"), (12, "GO_TO_PLAYLISTS_SCREEN")]
        for target, screen in destinations:
            with self.subTest(target=target):
                self.setUp()
                content = default_config(replacements={1: 12}, gesture_refs={1: target})
                self.library.probe_disk(content, len(content))
                self.library.probe_reload()
                self.touch("TOUCHEVENT_PRESS", 100, 100, 0)
                self.touch("TOUCHEVENT_CONTACT", 60, 100, 30)
                self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 60, 100, 100), self.constant("ACTION_NONE"))
                self.assertEqual(self.library.probe_navigation_requests(), 0)
                result = self.process_pending(self.constant("ACTION_NONE"))
                if target == 9 and NO_TAGCACHE:
                    self.assertEqual(result, self.constant("ACTION_REDRAW"))
                    self.assertEqual(self.library.probe_navigation_requests(), 0)
                    self.assertEqual(self.library.probe_stat(7), self.constant("LANG_ACCESSIBILITY_DESTINATION_UNAVAILABLE"))
                else:
                    self.assertEqual(result, self.constant("ACTION_STD_MENU"))
                    self.assertEqual(self.library.probe_navigation_requests(), 1)
                    self.assertEqual(self.library.probe_requested_screen(), self.constant(screen))
                self.assertEqual(self.library.probe_stat(13), 0)
                self.assertEqual(self.library.probe_plugin_path(), b"")
                self.assertEqual(self.library.probe_disk_content(), content)
                self.assertEqual(self.library.probe_stat(2), 0)

    def test_unavailable_direct_destination_leaves_persisted_binding_intact(self):
        content = default_config(replacements={1: 12}, gesture_refs={1: 8})
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.library.probe_navigation_available(False)
        self.touch("TOUCHEVENT_PRESS", 100, 100, 0)
        self.touch("TOUCHEVENT_CONTACT", 60, 100, 30)
        self.touch("TOUCHEVENT_RELEASE", 60, 100, 100)
        self.assertEqual(self.process_pending(self.constant("ACTION_NONE")), self.constant("ACTION_REDRAW"))
        self.assertEqual(self.library.probe_navigation_requests(), 1)
        self.assertEqual(self.library.probe_requested_screen(), self.constant("GO_TO_FILEBROWSER"))
        self.assertEqual(self.library.probe_stat(7), self.constant("LANG_ACCESSIBILITY_DESTINATION_UNAVAILABLE"))
        self.assertEqual(self.library.probe_disk_content(), content)
        self.assertEqual(self.library.probe_ref(-1, 1), 8)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_stat(13), 0)

    def test_v7_new_actions_and_system_reject_all_nonzero_launch_references(self):
        for action in (19, 20, 21, 22):
            for target in range(1, 13):
                for slot in (19, 20):
                    with self.subTest(action=action, target=target, slot=slot):
                        self.assertEqual(self.parse(default_config(replacements={slot: action},
                            gesture_refs={slot: target})), 0)
                with self.subTest(action=action, target=target, binding="button"):
                    self.assertEqual(self.parse(default_config(buttons={(0, 0): action},
                        button_refs={(0, 0): target})), 0)

    def test_v7_invalid_touch_timing_never_opens_or_changes_persisted_file(self):
        previous = default_config(touch_hold=1200, stroke_repeat=1)
        for hold_ms in (0, 299, 301, 899, 1999, 2001, 65535):
            with self.subTest(hold_ms=hold_ms):
                self.setUp()
                self.library.probe_disk(previous, len(previous))
                self.library.probe_reload()
                self.library.probe_touch_options(hold_ms, True)
                opens = self.library.probe_stat(0)
                self.assertEqual(self.library.probe_save(), 0)
                self.assertEqual(self.library.probe_stat(0), opens)
                self.assertEqual(self.library.probe_stat(2), 0)
                self.assertEqual(self.library.probe_syncs(), 0)
                self.assertFalse(self.library.probe_temporary_exists())
                self.assertEqual(self.library.probe_disk_content(), previous)

    def test_v7_touch_settings_trial_confirm_is_atomic_and_preserves_physical_settings(self):
        content = default_config(hold=1400, clicks=1, buttons={(4, 0): 11})
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.library.probe_chunks(0, 1)
        self.library.probe_prompt(0, 1999)
        self.assertEqual(self.library.probe_touch_trial(1500, True), 0)
        self.assertEqual(self.library.probe_stat(9), 0)
        self.assertEqual(self.library.probe_stat(8), 2000)
        self.assertEqual(self.library.probe_touch_hold(), 1500)
        self.assertEqual(self.library.probe_stroke_repeat(), 1)
        self.assertEqual(self.library.probe_disk_content(), default_config(
            hold=1400, clicks=1, buttons={(4, 0): 11}, touch_hold=1500, stroke_repeat=1))
        self.assertEqual(self.library.probe_syncs(), 1)
        self.assertEqual(self.library.probe_stat(3), 1)
        self.library.probe_reload()
        self.assertEqual(self.library.probe_touch_hold(), 1500)
        self.assertEqual(self.library.probe_stroke_repeat(), 1)
        self.assertEqual(self.library.probe_extra(5), 1400)
        self.assertEqual(self.library.probe_button_mapping(4, 0), 11)

    def test_v7_touch_settings_cancel_usb_timeout_and_every_save_fault_roll_back(self):
        cases = [(1, 0, 0), (2, 0, 0), (1, 2000, 0), (0, 2000, 0), (0, 2100, 0)]
        cases += [(0, 0, fault) for fault in range(4, 11)]
        for response, elapsed, fault in cases:
            with self.subTest(response=response, elapsed=elapsed, fault=fault):
                self.setUp()
                previous = default_config(touch_hold=600, stroke_repeat=1, hold=1800, clicks=2)
                self.library.probe_disk(previous, len(previous))
                self.library.probe_reload()
                self.library.probe_prompt(response, elapsed)
                self.library.probe_chunks(0, 7)
                self.library.probe_fault(fault)
                self.assertEqual(self.library.probe_touch_trial(2000, False), 313 if response == 2 else 0)
                self.assertEqual(self.library.probe_touch_hold(), 600)
                self.assertEqual(self.library.probe_stroke_repeat(), 1)
                self.assertEqual(self.library.probe_extra(5), 1800)
                self.assertEqual(self.library.accessibility_keyclick_sources(), 2)
                self.assertEqual(self.library.probe_stat(14), 0)
                self.assertEqual(self.library.probe_disk_content(), previous)
                self.assertFalse(self.library.probe_temporary_exists())
                self.assertFalse(self.library.probe_temporary_open())
                if fault:
                    self.assertEqual(self.library.probe_stat(7), self.constant("LANG_ERROR_WRITING_CONFIG"))
                else:
                    self.assertEqual(self.library.probe_stat(2), 0)

    def test_touch_reset_restores_new_defaults_but_keeps_button_timing_sources_and_shared_paths(self):
        path = "/.rockbox/rocks/apps/calculator.rock"
        content = default_config(hold=1700, clicks=1, touch_hold=2000, stroke_repeat=1,
            replacements={19: 12, 20: 21}, gesture_refs={19: 4},
            buttons={(4, 3): 12}, button_refs={(4, 3): 4}, paths={0: path})
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.script([7, -1])
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        expected = default_config(enabled=0 if os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET") else 1,
            replacements={13: 22, 16: 23}, hold=1700, clicks=1,
            buttons={(4, 3): 12}, button_refs={(4, 3): 4}, paths={0: path})
        self.assertEqual(self.library.probe_disk_content(), expected)
        self.assertEqual(self.library.probe_touch_hold(), 900)
        self.assertEqual(self.library.probe_stroke_repeat(), 0)
        self.assertEqual(self.library.probe_mapping(19), 0)
        self.assertEqual(self.library.probe_mapping(20), 8)
        self.assertEqual(self.library.probe_extra(5), 1700)
        self.assertEqual(self.library.probe_ref(-1, 19), 0)
        self.assertEqual(self.library.probe_ref(4, 3), 4)
        self.assertEqual(self.library.probe_path(0), path.encode())

    def test_v7_bad_new_fields_and_oversized_load_use_complete_defaults(self):
        valid = default_config(enabled=0, touch_hold=1200, stroke_repeat=1, replacements={19: 20, 20: 21})
        invalid = [valid.replace(b"touch_hold:1200", b"touch_hold:1201"),
                   valid.replace(b"stroke_repeat:1", b"stroke_repeat:2"),
                   valid.replace(b"gesture:20:21:0\n", b""), valid + b"\0",
                   valid + b"x" * (4096 - len(valid)), valid + b"x" * (4097 - len(valid))]
        for content in invalid:
            for chunk in (0, 1, 7):
                with self.subTest(length=len(content), chunk=chunk):
                    self.setUp()
                    self.library.probe_disk(content, len(content))
                    self.library.probe_chunks(chunk, 0)
                    self.library.probe_reload()
                    self.assertEqual(self.library.probe_touch_hold(), 900)
                    self.assertEqual(self.library.probe_stroke_repeat(), 0)
                    self.assertEqual(self.library.probe_mapping(19), 0)
                    self.assertEqual(self.library.probe_mapping(20), 8)
                    self.assertEqual(bool(self.library.accessibility_enabled()),
                                     not bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")))
                    self.assertEqual(self.library.probe_stat(2), 0)
                    self.assertEqual(self.library.probe_disk_length(), len(content))

    def test_v7_save_rejects_invalid_direct_references_before_opening_temporary(self):
        for button, slot in ((-1, 19), (-1, 20), (4, 3)):
            for action, target in ((12, 13), (12, 255), (19, 8), (20, 12), (21, 1), (22, 4)):
                with self.subTest(button=button, slot=slot, action=action, target=target):
                    self.setUp()
                    previous = default_config()
                    self.library.probe_disk(previous, len(previous))
                    if button < 0:
                        self.library.probe_assign(slot, action)
                    else:
                        self.library.probe_button_assign(button, slot, action)
                    self.library.probe_bind(button, slot, target)
                    opens = self.library.probe_stat(0)
                    self.assertEqual(self.library.probe_save(), 0)
                    self.assertEqual(self.library.probe_stat(0), opens)
                    self.assertEqual(self.library.probe_stat(2), 0)
                    self.assertEqual(self.library.probe_disk_content(), previous)
                    self.assertFalse(self.library.probe_temporary_exists())

    def test_touch_toggle_commits_whole_v7_configuration_and_restores_stock_mode(self):
        arguments = dict(hold=1700, clicks=1, touch_hold=1200, stroke_repeat=1,
            replacements={19: 20, 20: 21}, buttons={(0, 0): 19, (4, 3): 12},
            button_refs={(4, 3): 7}, paths={3: "/.rockbox/rocks/apps/calculator.rock"})
        previous = default_config(**arguments)
        self.library.probe_disk(previous, len(previous))
        self.library.probe_reload()
        self.library.probe_stock_mode(1)
        self.library.probe_chunks(0, 1)
        self.library.probe_speech_available(False)
        self.touch("TOUCHEVENT_PRESS", 100, 100, 0)
        self.assertEqual(self.library.probe_action(19, self.constant("CONTEXT_STD")), self.constant("ACTION_NONE"))
        self.assertFalse(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_mode(), 1)
        self.assertEqual(self.library.probe_disk_content(), default_config(enabled=0, **arguments))
        self.assertEqual(self.library.probe_syncs(), 1)
        self.assertEqual(self.library.probe_stat(3), 1)
        self.assertEqual(self.library.probe_stat(8), 0)
        self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 100, 100, 50), self.constant("ACTION_NONE"))
        self.assertIsNone(self.point())
        self.library.probe_reload()
        self.assertFalse(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_action(19, self.constant("CONTEXT_STD")), self.constant("ACTION_NONE"))
        self.assertTrue(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_mode(), 0)
        self.assertEqual(self.library.probe_disk_content(), previous)
        self.assertEqual(self.library.probe_stat(8), 0)
        self.assertEqual(self.library.probe_mapping(19), 20)
        self.assertEqual(self.library.probe_mapping(20), 21)
        self.assertEqual(self.library.probe_button_mapping(0, 0), 19)
        self.assertEqual(self.poll(1000), self.constant("ACTION_NONE"))

    def test_touch_toggle_every_save_failure_preserves_live_and_persisted_state(self):
        for enabled in (0, 1):
            for fault in range(4, 11):
                with self.subTest(enabled=enabled, fault=fault):
                    self.setUp()
                    previous = default_config(enabled=enabled, touch_hold=1600, stroke_repeat=1)
                    self.library.probe_disk(previous, len(previous))
                    self.library.probe_reload()
                    self.library.probe_chunks(0, 7)
                    self.library.probe_fault(fault)
                    self.library.probe_action(19, self.constant("CONTEXT_STD"))
                    self.assertEqual(bool(self.library.accessibility_enabled()), bool(enabled))
                    self.assertEqual(self.library.probe_mode(), 0 if enabled else 1)
                    self.assertEqual(self.library.probe_touch_hold(), 1600)
                    self.assertEqual(self.library.probe_stroke_repeat(), 1)
                    self.assertEqual(self.library.probe_stat(8), 0)
                    self.assertEqual(self.library.probe_disk_content(), previous)
                    self.assertFalse(self.library.probe_temporary_exists())
                    self.assertFalse(self.library.probe_temporary_open())
                    self.assertEqual(self.library.probe_stat(7), self.constant("LANG_ERROR_WRITING_CONFIG"))
                    self.library.probe_fault(0)
                    self.library.probe_reload()
                    self.assertEqual(bool(self.library.accessibility_enabled()), bool(enabled))

    def test_touch_toggle_during_trial_never_persists_unconfirmed_mappings(self):
        previous = default_config(replacements={19: 20})
        self.library.probe_disk(previous, len(previous))
        self.library.probe_reload()
        self.library.probe_start_trial(21)
        self.library.probe_action(19, self.constant("CONTEXT_STD"))
        self.assertEqual(self.library.probe_mapping(1), 21)
        self.assertTrue(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_stat(14), 1)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_disk_content(), previous)
        self.library.probe_time(2000)
        self.library.accessibility_enabled()
        self.assertEqual(self.library.probe_mapping(1), 1)
        self.assertEqual(self.library.probe_mapping(19), 20)
        self.assertEqual(self.library.probe_disk_content(), previous)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_touch_toggle_reenables_with_speech_off_and_ignores_repeat(self):
        content = default_config(enabled=0, buttons={(1, 3): 19})
        self.library.probe_disk(content, len(content))
        self.library.probe_reload()
        self.library.probe_speech_available(False)
        context = self.constant("CONTEXT_STD")
        self.library.probe_button(8, 0, context, False)
        self.library.probe_button(8 | 0x4000000, 700, context, False)
        self.assertTrue(self.library.accessibility_enabled())
        for milliseconds in (800, 900, 1000):
            self.library.probe_button(8 | 0x4000000, milliseconds, context, False)
        self.library.probe_button(8 | 0x2000000, 1100, context, False)
        self.assertTrue(self.library.accessibility_enabled())
        self.assertEqual(self.library.probe_syncs(), 1)
        self.assertEqual(self.library.probe_stat(3), 1)
        self.assertEqual(self.library.probe_stat(8), 0)
        self.assertEqual(self.library.probe_disk_content(), default_config(buttons={(1, 3): 19}))

    def test_date_and_summary_dispatch_use_declared_apis_without_enqueuing_or_saving(self):
        for speech in (False, True):
            for action, probe in ((20, self.library.probe_date_calls), (21, self.library.probe_summary_calls)):
                for context in ("CONTEXT_STD", "CONTEXT_WPS", "CONTEXT_KEYBOARD", "CONTEXT_SETTINGS"):
                    with self.subTest(speech=speech, action=action, context=context):
                        self.setUp()
                        self.library.probe_speech_available(speech)
                        self.assertEqual(self.library.probe_action(action, self.constant(context)), self.constant("ACTION_NONE"))
                        self.assertEqual(probe(), 1)
                        enqueue = self.library.probe_date_enqueue if action == 20 else self.library.probe_summary_enqueue
                        self.assertEqual(enqueue(), 0)
                        self.assertEqual(self.library.probe_stat(2), 0)
                        self.assertEqual(self.library.probe_extra(1), 0)
                        self.assertEqual(self.library.probe_stat(13), 0)
                        self.assertEqual(self.library.probe_navigation_requests(), 0)

    def test_new_gesture_slots_select_persist_and_reselect_each_new_action(self):
        for slot in (19, 20):
            for action, label in ((19, "LANG_ACCESSIBILITY_TOGGLE_TOUCH"),
                                  (20, "LANG_ACCESSIBILITY_ACTION_DATE"),
                                  (21, "LANG_ACCESSIBILITY_ACTION_SUMMARY")):
                with self.subTest(slot=slot, action=action):
                    self.setUp()
                    choice = action - int(NO_SCREEN_CURTAIN)
                    self.gesture_script([1, slot - 1, -1, -1], choice=choice)
                    self.assertEqual(self.library.accessibility_touch_menu(), 0)
                    self.assertEqual(self.library.probe_mapping(slot), action)
                    self.assertEqual(self.library.probe_option_voice(choice), self.constant(label))
                    self.assertIn(f"gesture:{slot}:{action}:0\n".encode(), self.library.probe_disk_content())
                    self.assertTrue(self.library.accessibility_enabled())
                    self.assertEqual(self.library.probe_date_calls(), 0)
                    self.assertEqual(self.library.probe_summary_calls(), 0)
                    writes = self.library.probe_stat(2)
                    self.library.probe_reload()
                    self.gesture_script([1, slot - 1, -1, -1], choice=choice)
                    self.assertEqual(self.library.accessibility_touch_menu(), 0)
                    self.assertEqual(self.library.probe_option_initial_choice(), choice)
                    self.assertEqual(self.library.probe_stat(2), writes)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_selector_persists_new_actions_and_keeps_system_distinct(self):
        for action, label in ((19, "LANG_ACCESSIBILITY_TOGGLE_TOUCH"),
                              (20, "LANG_ACCESSIBILITY_ACTION_DATE"),
                              (21, "LANG_ACCESSIBILITY_ACTION_SUMMARY")):
            with self.subTest(action=action):
                self.setUp()
                choice = action - int(NO_SCREEN_CURTAIN)
                self.script([0, 0, -1, -1], choice=choice)
                self.assertEqual(self.library.accessibility_buttons_menu(), 0)
                self.assertEqual(self.library.probe_button_mapping(0, 0), action)
                self.assertEqual(self.library.probe_option_voice(choice), self.constant(label))
                self.library.probe_reload()
                self.script([0, 0, -1, -1], choice=choice)
                self.assertEqual(self.library.accessibility_buttons_menu(), 0)
                self.assertEqual(self.library.probe_option_initial_choice(), choice)
                self.script([0, 0, -1, -1], choice=27 - int(NO_SCREEN_CURTAIN))
                self.assertEqual(self.library.accessibility_buttons_menu(), 0)
                self.assertEqual(self.library.probe_button_mapping(0, 0), 27)

    def test_touch_hold_and_repeat_menu_rows_commit_and_preserve_physical_hold(self):
        self.script([2, -1], choice=1500)
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        self.assertEqual(self.library.probe_touch_hold(), 1500)
        self.assertEqual(self.library.probe_extra(5), 700)
        self.assertEqual(self.library.probe_stat(8), 2000)
        self.assertEqual(self.library.probe_stat(9), 0)
        self.script([3, -1])
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        self.assertEqual(self.library.probe_stroke_repeat(), 1)
        self.assertEqual(self.library.probe_disk_content(),
                         default_config(touch_hold=1500, stroke_repeat=1, factory=True))
        self.library.probe_reload()
        self.assertEqual(self.library.probe_touch_hold(), 1500)
        self.assertEqual(self.library.probe_stroke_repeat(), 1)

    def test_touch_hold_option_usb_leaves_both_new_settings_and_file_unchanged(self):
        previous = default_config(touch_hold=1200, stroke_repeat=1)
        self.library.probe_disk(previous, len(previous))
        self.library.probe_reload()
        self.script([2], choice=-313)
        self.assertEqual(self.library.accessibility_touch_menu(), 313)
        self.assertEqual(self.library.probe_touch_hold(), 1200)
        self.assertEqual(self.library.probe_stroke_repeat(), 1)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_disk_content(), previous)

    def test_four_maximum_length_application_paths_round_trip_without_truncation(self):
        prefix = "/.rockbox/rocks/apps/"
        paths = {index: prefix + str(index) + "x" * (259 - len(prefix) - 6) + ".rock"
                 for index in range(4)}
        self.assertTrue(all(len(path) == 259 for path in paths.values()))
        content = default_config(hold=2000, touch_hold=2000, stroke_repeat=1,
            replacements={slot: 12 for slot in range(1, 21)},
            gesture_refs={slot: 12 for slot in range(1, 21)},
            buttons={(button, slot): 12 for button in range(5) for slot in range(4)},
            button_refs={(button, slot): 12 for button in range(5) for slot in range(4)}, paths=paths)
        self.assertEqual(self.library.probe_max_path(), 260)
        self.assertEqual(self.library.probe_config_capacity(), 4096)
        self.assertEqual(content.count(b"\ngesture:"), 20)
        self.assertEqual(content.count(b"\nplayback_gesture:"), 20)
        self.assertEqual(content.count(b"\nbutton:"), 20)
        self.assertEqual(content.count(b"\nplayback_button:"), 20)
        self.assertEqual(content.count(b"target:"), 4)
        self.assertEqual(len(content), 2890)
        self.assertLess(len(content) + 1, 4096)
        self.assertEqual(self.parse(content), 1)
        self.library.probe_disk(content, len(content))
        self.library.probe_chunks(1, 1)
        self.library.probe_reload()
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_disk_content(), content)
        self.assertEqual(self.library.probe_disk_length(), 2890)
        self.assertEqual(self.library.probe_syncs(), 1)
        self.assertEqual(self.library.probe_stat(3), 1)
        self.assertFalse(self.library.probe_temporary_exists())
        self.library.probe_reload()
        for index, path in paths.items():
            self.assertEqual(self.library.probe_path(index), path.encode())
        self.assertEqual(self.parse(content.replace(paths[0].encode(), (paths[0] + "x").encode())), 0)

    def test_application_paths_reject_escape_control_and_wrong_type(self):
        for path in ["/etc/test.rock", "/.rockbox/rocks/apps/../test.rock",
                     "/.rockbox/rocks/apps/./test.rock", "/.rockbox/rocks//test.rock",
                     "/.rockbox/rocks/test.txt", "/.rockbox/rocks/test\r.rock",
                     "/.rockbox/rocks/test\\name.rock", "/.rockbox/rocks/a\0b.rock"]:
            self.assertEqual(self.parse(default_config(replacements={1: 12}, gesture_refs={1: 4}, paths={0: path})), 0)

    def test_feedback_picker_confirm_failure_and_touch_reset_preserve_scope(self):
        self.script([], choice=2)
        self.assertEqual(self.library.accessibility_keyclick_menu(), 0)
        self.assertEqual(self.library.accessibility_keyclick_sources(), 2)
        self.library.probe_button_assign(4, 0, 0)
        self.library.probe_assign(1, 8)
        self.script([7, -1])
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        self.assertEqual(self.library.probe_mapping(1), 1)
        self.assertEqual(self.library.probe_button_mapping(4, 0), 0)
        self.assertEqual(self.library.accessibility_keyclick_sources(), 2)
        self.script([], choice=1)
        self.library.probe_fault(9)
        self.assertEqual(self.library.accessibility_keyclick_menu(), 0)
        self.assertEqual(self.library.accessibility_keyclick_sources(), 2)

    def test_feedback_fresh_defaults_and_all_eight_masks_round_trip(self):
        self.assertEqual(self.library.accessibility_keyclick_sources(), 7)
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), -4)
        choices = {3: 0, 1: 1, 2: 2, 0: 3, 4: 4, 5: 5, 6: 6, 7: 7}
        for mask, choice in choices.items():
            with self.subTest(mask=mask):
                self.setUp()
                self.script([], choice=choice)
                self.assertEqual(self.library.accessibility_keyclick_menu(), 0)
                self.assertEqual(self.library.accessibility_keyclick_sources(), mask)
                self.assertEqual(self.library.probe_save(), 1)
                self.assertEqual(self.library.probe_disk_content(), default_config(clicks=mask, factory=True))
                self.library.probe_reload()
                self.assertEqual(self.library.accessibility_keyclick_sources(), mask)

    def test_feedback_legacy_explicit_masks_keep_their_meaning_and_gain_pitch_defaults(self):
        for version in range(2, 8):
            for mask in (1, 2, 3):
                with self.subTest(version=version, mask=mask):
                    self.setUp()
                    content = default_config(version=version, clicks=mask)
                    self.library.probe_disk(content, len(content))
                    self.library.probe_reload()
                    self.assertEqual(self.library.accessibility_keyclick_sources(), mask)
                    self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), -4)
                    self.assertEqual(self.library.probe_save(), 1)
                    self.assertIn(f"click:{mask}\n".encode(), self.library.probe_disk_content())

    def test_feedback_pitch_menu_persists_every_semitone_and_can_be_disabled(self):
        for semitones in range(-12, 13):
            self.script([], choice=semitones)
            self.assertEqual(self.library.accessibility_keyclick_pitch_menu(), 0)
            self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), semitones)
            self.assertEqual(self.library.probe_save(), 1)
            self.library.probe_reload()
            self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), semitones)
        self.script([], choice=0)
        self.assertEqual(self.library.accessibility_keyclick_empty_menu(), 0)
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), 0)
        self.assertEqual(self.library.probe_feedback_stat(3), 12)
        self.script([], choice=1)
        self.assertEqual(self.library.accessibility_keyclick_empty_menu(), 0)
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), 12)

    def test_feedback_pitch_invalid_and_failed_saves_preserve_state(self):
        for pitch in (-13, 13, "-0", "+4", "04", "-04", "99999999999999999999"):
            self.assertEqual(self.parse(default_config(empty_semitones=pitch)), 0)
        for enabled in (-1, 2, "true", "01"):
            self.assertEqual(self.parse(default_config(empty_pitch=enabled)), 0)
        for fault in (4, 5, 6, 7, 8, 9):
            self.setUp()
            self.library.probe_fault(fault)
            self.script([], choice=7)
            self.assertEqual(self.library.accessibility_keyclick_pitch_menu(), 0)
            self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), -4)
        self.script([], choice=-313)
        self.assertEqual(self.library.accessibility_keyclick_pitch_menu(), 313)
        self.assertEqual(self.library.accessibility_keyclick_empty_pitch(), -4)

    def test_feedback_exploration_tracks_targets_contacts_and_empty_space_without_jitter(self):
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.poll(230)
        self.assertEqual(self.point(), (40, 50, True))
        self.library.probe_feedback(1, 10, True)
        self.assertEqual(self.library.probe_feedback_stat(0), 1)
        for offset, target, occupied, expected in (
                (1, 10, True, 1), (2, 11, True, 2),
                (3, -1, False, 3), (4, -1, False, 3)):
            self.touch("TOUCHEVENT_CONTACT", 40 + offset, 50, 230 + offset * 10)
            self.assertIsNotNone(self.point())
            self.library.probe_feedback(1, target, occupied)
            self.assertEqual(self.library.probe_feedback_stat(0), expected)
        self.library.probe_feedback(2, 12, True)
        self.assertEqual(self.library.probe_feedback_stat(0), 3)
        self.touch("TOUCHEVENT_RELEASE", 44, 50, 300)
        self.touch("TOUCHEVENT_PRESS", 44, 50, 500)
        self.poll(730)
        self.assertIsNotNone(self.point())
        self.library.probe_feedback(1, -1, False)
        self.assertEqual(self.library.probe_feedback_stat(0), 4)
        self.assertEqual(self.library.probe_feedback_stat(1), 2)
        self.touch("TOUCHEVENT_CONTACT", 45, 50, 740)
        self.assertIsNotNone(self.point())
        self.library.accessibility_cancel_touch()
        self.library.probe_feedback(1, 99, True)
        self.assertEqual(self.library.probe_feedback_stat(0), 4)

    def test_feedback_recognizer_reset_applies_touch_sensitivity_without_recursion(self):
        self.assertEqual(self.library.probe_feedback_stat(4), 8)
        self.assertEqual(self.library.probe_feedback_stat(5), 24)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.library.probe_sensitivity(200)
        self.assertEqual(self.library.probe_feedback_stat(4), 4)
        self.assertEqual(self.library.probe_feedback_stat(5), 12)
        self.assertIsNone(self.point())
        self.assertEqual(self.poll(500), self.constant("ACTION_NONE"))
        self.library.probe_sensitivity(50)
        self.assertEqual(self.library.probe_feedback_stat(4), 16)
        self.assertEqual(self.library.probe_feedback_stat(5), 48)

    def test_feedback_private_typing_arms_only_contact_and_press_forces_new_contact(self):
        self.library.probe_typing_feedback(10, True)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0, "CONTEXT_KEYBOARD")
        self.assertEqual(self.library.probe_feedback_stat(0), 1)
        self.poll(100, "CONTEXT_KEYBOARD")
        self.touch("TOUCHEVENT_CONTACT", 41, 51, 110, "CONTEXT_KEYBOARD")
        self.assertEqual(self.library.probe_feedback_stat(0), 1)
        self.library.probe_typing_feedback(-1, False)
        self.touch("TOUCHEVENT_CONTACT", 42, 51, 120, "CONTEXT_KEYBOARD")
        self.assertEqual(self.library.probe_feedback_stat(0), 2)
        self.assertEqual(self.library.probe_feedback_stat(1), 1)
        self.library.probe_typing_feedback(11, True)
        self.touch("TOUCHEVENT_RELEASE", 42, 51, 130, "CONTEXT_KEYBOARD")
        self.poll(300, "CONTEXT_KEYBOARD")
        self.assertEqual(self.library.probe_feedback_stat(0), 2)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 400, "CONTEXT_KEYBOARD")
        self.assertEqual(self.library.probe_feedback_stat(0), 3)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 410, "CONTEXT_KEYBOARD")
        self.touch("TOUCHEVENT_PRESS", 40, 50, 500, "CONTEXT_KEYBOARD")
        self.assertEqual(self.library.probe_feedback_stat(0), 4)

    def test_feedback_exactly_one_for_resolved_tap_double_and_unassigned_stroke(self):
        self.touch("TOUCHEVENT_PRESS", 40, 50, 0)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 50)
        self.assertEqual(self.library.probe_extra(0), 0)
        self.poll(380)
        self.assertEqual(self.library.probe_extra(0), 0)
        self.assertEqual(self.point(), (40, 50, True))
        self.library.accessibility_explore_feedback(None, 1, True)
        self.assertEqual(self.library.probe_extra(0), 1)
        self.assertEqual(self.poll(400), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_extra(0), 1)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 500)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 550)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 600)
        self.touch("TOUCHEVENT_RELEASE", 40, 50, 650)
        self.assertEqual(self.library.probe_extra(0), 1)
        self.assertEqual(self.poll(970), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_extra(0), 1)
        self.assertEqual(self.poll(980), self.constant("ACTION_STD_OK"))
        self.assertEqual(self.library.probe_extra(0), 2)
        self.library.probe_assign(1, 0)
        self.touch("TOUCHEVENT_PRESS", 100, 100, 1000)
        self.touch("TOUCHEVENT_CONTACT", 60, 100, 1050)
        self.touch("TOUCHEVENT_RELEASE", 60, 100, 1100)
        self.assertEqual(self.library.probe_extra(0), 3)
        self.touch("TOUCHEVENT_PRESS", 40, 50, 1400)
        self.poll(1630)
        self.touch("TOUCHEVENT_CONTACT", 42, 52, 1640)
        self.touch("TOUCHEVENT_RELEASE", 42, 52, 1650)
        self.assertEqual(self.library.probe_extra(0), 3)

    def test_battery_dispatch_uses_shared_bounds_and_unknown_for_invalid_levels(self):
        for level in list(range(101)) + [-2147483648, -2, -1, 101, 102, 2147483647]:
            with self.subTest(level=level):
                self.setUp()
                self.library.probe_battery(level)
                self.assertEqual(self.library.probe_action(11, self.constant("CONTEXT_STD")),
                                 self.constant("ACTION_NONE"))
                self.assertEqual(self.library.probe_battery_reads(), 1)
                self.assertEqual(self.library.probe_spoken(0), self.constant("LANG_BATTERY_CHARGE"))
                self.assertEqual(self.library.probe_spoken_enqueue(0), 0)
                if 0 <= level <= 100:
                    self.assertEqual(self.library.probe_extra(3), level)
                    self.assertEqual(self.library.probe_value_calls(), 1)
                    self.assertEqual(self.library.probe_value_unit(), 1)
                    self.assertEqual(self.library.probe_value_enqueue(), 1)
                    self.assertEqual(self.library.probe_stat(6), 1)
                else:
                    self.assertEqual(self.library.probe_value_calls(), 0)
                    self.assertEqual(self.library.probe_spoken(1), self.constant("LANG_UNKNOWN"))
                    self.assertEqual(self.library.probe_spoken_enqueue(1), 1)
                    self.assertEqual(self.library.probe_stat(6), 2)
                self.assertEqual(self.library.probe_time_calls(), 0)
                self.assertEqual(self.library.probe_stat(2), 0)

    def test_battery_dispatch_respects_shared_speech_gate(self):
        self.library.probe_speech_available(False)
        self.assertEqual(self.library.probe_action(11, self.constant("CONTEXT_WPS")),
                         self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_battery_reads(), 0)
        self.assertEqual(self.library.probe_value_calls(), 0)
        self.assertEqual(self.library.probe_stat(6), 0)

    def test_new_semantic_battery_shutdown_lock_and_deferred_launch_effects(self):
        self.assertEqual(self.library.probe_action(11, self.constant("CONTEXT_STD")), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_extra(3), 63)
        self.assertEqual(self.library.probe_spoken(0), self.constant("LANG_BATTERY_CHARGE"))
        self.assertEqual(self.library.probe_action(13, self.constant("CONTEXT_STD")), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_extra(1), 1)
        self.assertEqual(self.library.probe_action(14, self.constant("CONTEXT_STD")), self.constant("ACTION_STD_KEYLOCK"))
        self.library.probe_action(12, self.constant("CONTEXT_STD"))
        self.assertEqual(self.library.probe_extra(2), 0)
        self.assertEqual(self.library.accessibility_adjust_timeout(-1), 5)
        self.assertEqual(self.process_pending(self.constant("ACTION_NONE")), self.constant("ACTION_REDRAW"))
        self.assertEqual(self.library.probe_extra(2), 2)
        self.assertEqual(self.process_pending(self.constant("ACTION_NONE")), 0)
        self.library.probe_action(12, self.constant("CONTEXT_STD"))
        self.assertEqual(self.process_pending(0x40000001), 0)
        self.assertEqual(self.library.probe_extra(4), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_defaults_and_unassigned_volume_only(self):
        self.assertEqual(self.library.probe_button_mapping(0, 2), 26)
        self.library.probe_button_assign(0, 2, self.constant("ACCESSIBILITY_ACTION_SYSTEM"))
        for button in [1, 8, 4, 16, 32]:
            self.assertEqual(self.library.probe_button(button, 0, self.constant("CONTEXT_STD"), False), -1)
        self.library.probe_button_assign(3, 0, 0)
        self.assertEqual(self.library.probe_button(16, 10, self.constant("CONTEXT_STD"), False), self.constant("ACTION_UNKNOWN"))
        self.assertEqual(self.library.probe_button(16 | 0x2000000, 60, self.constant("CONTEXT_STD"), False), self.constant("ACTION_LIST_VOLUP"))
        self.assertEqual(self.library.probe_stat(5), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_system_multiclick_slots_do_not_delay_intrinsic_volume_presses(self):
        context = self.constant("CONTEXT_STD")
        self.library.probe_button_assign(3, 0, 0)
        self.library.probe_button_assign(3, 3, 0)
        self.assertEqual(self.library.probe_button_mapping(3, 1), 27)
        self.assertEqual(self.library.probe_button_mapping(3, 2), 27)
        for start in [0, 100, 200]:
            self.assertEqual(self.library.probe_button(16, start, context, False),
                             self.constant("ACTION_UNKNOWN"))
            self.assertEqual(self.library.probe_button(16 | 0x2000000, start + 50, context, False),
                             self.constant("ACTION_LIST_VOLUP"))
        self.assertEqual(self.library.probe_button(0, 650, context, False), -1)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_explicit_none_physical_double_and_triple_reserve_clicks_without_native_or_lower_action(self):
        context = self.constant("CONTEXT_STD")
        for button, raw in enumerate((1, 8, 4, 16, 32)):
            for slot in (1, 2):
                with self.subTest(button=button, slot=slot):
                    self.setUp()
                    if button == 0 and slot == 1:
                        self.library.probe_button_assign(0, 2, self.constant("ACCESSIBILITY_ACTION_SYSTEM"))
                    self.library.probe_button_assign(button, 0, 11)
                    if slot == 2:
                        self.library.probe_button_assign(button, 1, 16)
                    self.library.probe_button_assign(button, slot, 0)
                    for click in range(slot + 1):
                        self.assertEqual(self.library.probe_button(raw, click * 100, context, False),
                                         self.constant("ACTION_UNKNOWN"))
                        expected = "ACTION_NONE" if click == slot else "ACTION_UNKNOWN"
                        self.assertEqual(self.library.probe_button(raw | 0x2000000, click * 100 + 50, context, False),
                                         self.constant(expected))
                    self.assertEqual(self.library.probe_button(0, 1000, context, False), -1)
                    self.assertEqual(self.library.probe_default_button_calls(), 0)
                    self.assertEqual(self.library.probe_battery_reads(), 0)
                    self.assertEqual(self.library.probe_time_calls(), 0)
                    self.assertEqual(self.library.probe_stat(5), 0)
                    self.assertEqual(self.library.probe_stat(2), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_system_double_uses_native_action_when_triple_mapping_reserves_third_gap(self):
        context = self.constant("CONTEXT_STD")
        self.library.probe_button_assign(1, 0, 16)
        self.library.probe_button_assign(1, 2, 11)
        self.assertEqual(self.library.probe_button_mapping(1, 1), 27)
        for press_ms in (0, 100):
            self.assertEqual(self.library.probe_button(8, press_ms, context, False), self.constant("ACTION_UNKNOWN"))
            self.assertEqual(self.library.probe_button(8 | 0x2000000, press_ms + 50, context, False),
                             self.constant("ACTION_UNKNOWN"))
        self.assertEqual(self.library.probe_default_button_calls(), 0)
        self.assertEqual(self.library.probe_button(0, 450, context, False), self.constant("ACTION_STD_OK"))
        self.assertEqual(self.library.probe_default_button_calls(), 1)
        self.assertEqual(self.library.probe_time_calls(), 0)
        self.assertEqual(self.library.probe_battery_reads(), 0)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_native_hold_release_stops_seek_even_without_an_intermediate_poll(self):
        context = self.constant("CONTEXT_WPS")
        for hold_action in [0, self.constant("ACCESSIBILITY_ACTION_SYSTEM")]:
            for intermediate_poll in [False, True]:
                self.setUp()
                self.library.probe_button_assign(1, 0, 5)
                self.library.probe_button_assign(1, 3, hold_action)
                self.library.probe_playback_assign(1, 0, 5)
                self.library.probe_playback_assign(1, 3, hold_action)
                self.library.probe_button(8, 0, context, False)
                if intermediate_poll:
                    self.library.probe_button(0, 700, context, False)
                self.assertEqual(self.library.probe_button(8 | 0x2000000, 800, context, False),
                                 self.constant("ACTION_WPS_STOPSEEK"))
                self.assertEqual(self.library.probe_button(0, 1200, context, False), -1)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_recovery_chord_cancels_custom_sequence_without_release_or_repeat_action(self):
        context = self.constant("CONTEXT_STD")
        self.library.probe_button_assign(0, 0, 13)
        self.library.probe_button_assign(3, 0, 11)
        self.library.probe_button(1, 0, context, False)
        self.assertEqual(self.library.probe_button(1 | 16, 50, context, False), -1)
        for button, time in [(1 | 0x4000000, 800), (1 | 0x2000000, 850), (16 | 0x2000000, 900)]:
            self.assertEqual(self.library.probe_button(button, time, context, False), self.constant("ACTION_UNKNOWN"))
        self.assertEqual(self.library.probe_button(0, 1300, context, False), -1)
        self.assertEqual(self.library.probe_extra(1), 0)
        self.assertEqual(self.library.probe_extra(3), -1)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_multiclick_hold_repeat_context_and_locked_filter(self):
        self.library.probe_button_assign(1, 0, 5)
        self.library.probe_button_assign(1, 1, 11)
        self.library.probe_button_assign(1, 2, 8)
        self.library.probe_button_assign(1, 3, 9)
        context = self.constant("CONTEXT_STD")
        for start in [0, 100]:
            self.assertEqual(self.library.probe_button(8, start, context, False), self.constant("ACTION_UNKNOWN"))
            self.assertEqual(self.library.probe_button(8 | 0x2000000, start + 50, context, False), self.constant("ACTION_UNKNOWN"))
        self.assertEqual(self.library.probe_button(0, 450, context, False), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_extra(3), 63)
        self.library.probe_button(8, 500, context, False)
        self.assertEqual(self.library.probe_button(0, 1200, context, False), self.constant("ACTION_LIST_VOLUP"))
        self.assertFalse(self.library.accessibility_button_is_repeat())
        self.assertEqual(self.library.probe_button(8 | 0x4000000, 1250, context, False), self.constant("ACTION_LIST_VOLUP"))
        self.assertTrue(self.library.accessibility_button_is_repeat())
        self.library.probe_button(8 | 0x2000000, 1300, context, False)
        self.assertEqual(self.library.probe_stat(5), 0)
        self.library.probe_button(8, 1400, context, False)
        self.library.probe_button(8 | 0x2000000, 1450, context, False)
        self.assertEqual(self.library.probe_button(0, 1750, self.constant("CONTEXT_WPS"), False), -1)
        self.library.probe_button(8, 1800, context, True)
        self.library.probe_button(8 | 0x2000000, 1850, context, True)
        self.assertEqual(self.library.probe_button(0, 2150, context, True), self.constant("ACTION_UNKNOWN"))
        self.library.probe_button_assign(1, 0, 14)
        self.library.probe_button(8, 2200, context, True)
        self.library.probe_button(8 | 0x2000000, 2250, context, True)
        self.assertEqual(self.library.probe_button(0, 2550, context, True), self.constant("ACTION_STD_KEYLOCK"))

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_editor_and_reset_isolate_touch_and_feedback(self):
        self.library.probe_assign(1, 8)
        self.library.probe_click_sources(1)
        self.script([0, 0, -1, -1], choice=11)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_button_mapping(0, 0), 11)
        self.assertEqual(self.library.probe_mapping(1), 8)
        self.assertEqual(self.library.accessibility_keyclick_sources(), 1)
        self.script([2, -1], choice=900)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_extra(5), 900)
        self.script([3, -1])
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_button_mapping(0, 0), self.constant("ACCESSIBILITY_ACTION_SYSTEM"))
        self.assertEqual(self.library.probe_mapping(1), 8)
        self.assertEqual(self.library.accessibility_keyclick_sources(), 1)
        spoken = [self.library.probe_spoken(index) for index in range(self.library.probe_stat(6))]
        self.assertIn(self.constant("LANG_ACCESSIBILITY_BUTTON_POWER"), spoken)
        self.assertIn(self.constant("LANG_ACCESSIBILITY_BUTTON_VOLUME_DOWN"), spoken)

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_trial_cancel_usb_timeout_and_write_failure_restore_previous(self):
        for response, elapsed, fault in [(1, 0, 0), (2, 0, 0), (0, 2000, 0), (0, 0, 9)]:
            self.setUp()
            self.library.probe_prompt(response, elapsed)
            self.library.probe_fault(fault)
            self.script([0, 0, -1, -1], choice=11)
            result = self.library.accessibility_buttons_menu()
            self.assertEqual(result, 313 if response == 2 else 0)
            self.assertEqual(self.library.probe_button_mapping(0, 0), self.constant("ACCESSIBILITY_ACTION_SYSTEM"))
            self.assertEqual(self.library.probe_stat(3), 1 if fault == 9 else 0)

    def test_per_gesture_application_binding_is_selected_before_trial_and_not_retargeted(self):
        for slot, path in [(0, b"/.rockbox/rocks/apps/calculator.rock"),
                           (1, b"/.rockbox/rocks/apps/stopwatch.rock")]:
            self.library.probe_launcher(1, path, 0)
            self.gesture_script([1, slot, -1, -1], choice=12)
            self.assertEqual(self.library.accessibility_touch_menu(), 0)
            self.assertEqual(self.library.probe_mapping(slot + 1), 12)
            self.assertEqual(self.library.probe_stat(13), 0)
        first, second = self.library.probe_ref(-1, 1), self.library.probe_ref(-1, 2)
        self.assertNotEqual(first, second)
        self.assertEqual(self.library.probe_path(first - 4), b"/.rockbox/rocks/apps/calculator.rock")
        self.assertEqual(self.library.probe_path(second - 4), b"/.rockbox/rocks/apps/stopwatch.rock")
        self.assertIn(b"calculator.rock", self.library.probe_row(-1, 1))
        self.assertEqual(self.library.probe_spoken_file(), b"/.rockbox/rocks/apps/calculator.rock")
        self.touch("TOUCHEVENT_PRESS", 100, 100, 0)
        self.touch("TOUCHEVENT_CONTACT", 60, 100, 30)
        self.touch("TOUCHEVENT_RELEASE", 60, 100, 100)
        self.assertEqual(self.library.probe_stat(13), 0)
        self.process_pending(self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_plugin_path(), b"/.rockbox/rocks/apps/calculator.rock")

    @unittest.skipIf(bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")), "Physical mapping is R1-only")
    def test_physical_application_binding_announces_target_and_survives_touch_reset(self):
        path = b"/.rockbox/rocks/apps/calculator.rock"
        self.library.probe_launcher(1, path, 0)
        self.script([0, 4, -1, -1], choice=12)
        self.assertEqual(self.library.accessibility_buttons_menu(), 0)
        self.assertEqual(self.library.probe_button_mapping(1, 0), 12)
        target = self.library.probe_ref(1, 0)
        self.assertIn(b"calculator.rock", self.library.probe_row(1, 0))
        self.assertEqual(self.library.probe_spoken_file(), path)
        self.script([4, -1])
        self.assertEqual(self.library.accessibility_touch_menu(), 0)
        self.assertEqual(self.library.probe_ref(1, 0), target)
        self.assertEqual(self.library.probe_path(target - 4), path)
        context = self.constant("CONTEXT_STD")
        self.library.probe_button(8, 0, context, False)
        self.assertEqual(self.library.probe_button(8 | 0x2000000, 50, context, False), self.constant("ACTION_NONE"))
        self.assertEqual(self.library.probe_stat(13), 0)
        self.assertEqual(self.process_pending(self.constant("ACTION_NONE")), self.constant("ACTION_REDRAW"))
        self.assertEqual(self.library.probe_plugin_path(), path)

    def test_system_and_shortcuts_destinations_are_announced_in_assigned_rows(self):
        for choice, target, label in [(0, 1, "LANG_SHORTCUTS"),
                                      (2, 2, "LANG_ACCESSIBILITY_SYSTEM_SCREENS")]:
            self.setUp()
            self.library.probe_launcher(choice, b"", 0)
            self.gesture_script([1, 0, -1, -1], choice=12)
            self.assertEqual(self.library.accessibility_touch_menu(), 0)
            self.assertEqual(self.library.probe_ref(-1, 1), target)
            count = self.library.probe_stat(6)
            self.library.probe_row(-1, 1)
            self.assertEqual(self.library.probe_spoken(count + 2), self.constant(label))

    def test_application_pool_capacity_dedup_cancel_and_usb_leave_old_bindings(self):
        for slot in range(4):
            self.library.probe_launcher(1, f"/.rockbox/rocks/apps/app{slot}.rock".encode(), 0)
            self.gesture_script([1, slot, -1, -1], choice=12)
            self.library.accessibility_touch_menu()
        original = self.library.probe_disk_content()
        self.library.probe_launcher(1, b"/.rockbox/rocks/apps/app4.rock", 0)
        self.gesture_script([1, 4, -1, -1], choice=12)
        self.library.accessibility_touch_menu()
        self.assertEqual(self.library.probe_disk_content(), original)
        self.assertEqual(self.library.probe_mapping(5), 6)
        self.assertEqual(self.library.probe_stat(7), self.constant("LANG_ACCESSIBILITY_LAUNCH_CAPACITY"))
        self.library.probe_launcher(1, b"/.rockbox/rocks/apps/app0.rock", 0)
        self.gesture_script([1, 4, -1, -1], choice=12)
        self.library.accessibility_touch_menu()
        self.assertEqual(self.library.probe_ref(-1, 5), self.library.probe_ref(-1, 1))
        original = self.library.probe_disk_content()
        self.library.probe_launcher(1, b"", 313)
        self.gesture_script([1, 5], choice=12)
        self.assertEqual(self.library.accessibility_touch_menu(), 313)
        self.assertEqual(self.library.probe_disk_content(), original)

    def test_trial_blocks_application_execution_and_gui_mutation_is_not_persisted_early(self):
        self.library.probe_start_trial(12)
        self.library.probe_action(12, self.constant("CONTEXT_STD"))
        self.assertEqual(self.library.probe_extra(4), 0)
        self.assertEqual(self.library.probe_stat(2), 0)


class AccessibilityCatalogTests(unittest.TestCase):
    def test_disabled_capability_combinations_compile_and_are_inert(self):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            self.skipTest("C host compiler unavailable; compile capability guards under WSL")
        materials = project_materials_root(ROOT)
        ensure_ignored_directories(materials.parent, [materials.name])
        workspace = materials / "r1-gesture-extensions-20261016/config-codec" / (
            "settings-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-guards")
        workspace.mkdir(parents=True, exist_ok=False)
        source = without_includes((ROOT / "apps/accessibility.c").read_text(encoding="utf-8"))
        header = (ROOT / "apps/accessibility.h").read_text(encoding="utf-8")
        results = []
        for defines in [[], ["HAVE_TOUCHSCREEN"], ["HAVE_ESPEAK"]]:
            name = "-".join(defines) or "neither"
            unit = workspace / f"{name}.c"
            unit.write_text("#define ACTION_NONE 0\n" + header + "\n" + source + r'''
int main(void)
{
    int point_x = 7, point_y = 8;
    bool force = true;
    accessibility_init();
    accessibility_reset();
    accessibility_set_target(&point_x);
    accessibility_speak_empty();
    return accessibility_enabled() || accessibility_menu() ||
        accessibility_handle_touch(0, 0) ||
        accessibility_adjust_timeout(-1) != -1 ||
        accessibility_adjust_timeout(0) != 0 ||
        accessibility_explore_point(&point_x, &point_y, &force) ||
        point_x != 7 || point_y != 8 || !force;
}
''', encoding="utf-8")
            executable = workspace / (name + (".exe" if os.name == "nt" else ".bin"))
            command = compiler + ["-std=" + os.environ.get("ACCESSIBILITY_SETTINGS_STANDARD", "c99"),
                                  "-O2", "-Wall", "-Wextra", "-Werror"]
            if os.environ.get("ACCESSIBILITY_SETTINGS_SANITIZE"):
                command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            command += [f"-D{define}" for define in defines]
            command += [str(unit), "-o", str(executable)]
            compiled = subprocess.run(command, capture_output=True, text=True)
            (workspace / f"{name}.log").write_text(shlex.join(command) + "\n" + compiled.stdout + compiled.stderr,
                                                  encoding="utf-8")
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            results.append({"defines": defines, "compiled": compiled.returncode, "executed": executed.returncode,
                            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest()})
        (workspace / "result.json").write_text(json.dumps({"passed": True, "guards": results}, indent=2),
                                               encoding="utf-8")

    def test_new_catalog_ids_are_complete_and_have_matching_english_sources(self):
        records = {}
        for language in ["english", "polski"]:
            catalog = (ROOT / "apps/lang" / f"{language}.lang").read_text(encoding="utf-8")
            records[language] = {}
            for phrase in re.findall(r'<phrase>.*?</phrase>', catalog, re.DOTALL):
                identifier = re.search(r'\bid: (LANG_ACCESSIBILITY[A-Z0-9_]*)\b', phrase)
                if not identifier:
                    continue
                self.assertNotIn(identifier[1], records[language])
                sections = {}
                for section in ["source", "dest", "voice"]:
                    match = re.search(r'<' + section + r'>\s*\*: "([^"\n]+)"\s*</' + section + r'>', phrase)
                    self.assertIsNotNone(match, (language, identifier[1], section))
                    sections[section] = match[1]
                records[language][identifier[1]] = sections
        self.assertGreaterEqual(len(records["english"]), 34)
        self.assertEqual(set(records["english"]), set(records["polski"]))
        manager = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        required = set(re.findall(r'\bLANG_ACCESSIBILITY[A-Z0-9_]*\b', manager))
        self.assertFalse(required - set(records["english"]), sorted(required - set(records["english"])))
        self.assertEqual(records["english"]["LANG_ACCESSIBILITY_UNASSIGNED"]["dest"], "Unassigned")
        self.assertEqual(records["polski"]["LANG_ACCESSIBILITY_UNASSIGNED"]["dest"], "Nieprzypisany")
        for identifier, sections in records["english"].items():
            self.assertEqual(sections["source"], records["polski"][identifier]["source"])
            self.assertEqual(sections["dest"], sections["voice"])
            self.assertEqual(records["polski"][identifier]["dest"], records["polski"][identifier]["voice"])

    def test_no_shared_settings_layout_or_recursive_input_dependency(self):
        source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        self.assertNotRegex(source, r'\bget_(?:custom_)?action\s*\(')
        self.assertNotRegex(source, r'global_settings\.[A-Za-z_][A-Za-z0-9_]*\s*=')
        self.assertEqual(set(re.findall(r'global_settings\.([A-Za-z_][A-Za-z0-9_]*)', source)),
                         {"touch_mode"})
        for function in ["init", "enabled", "reset", "set_target", "handle_touch", "explore_point", "menu"]:
            self.assertIn(f"accessibility_{function}(", (ROOT / "apps/accessibility.h").read_text(encoding="utf-8"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if hasattr(AccessibilitySettingsTests, "workspace"):
        (AccessibilitySettingsTests.workspace / "result.json").write_text(json.dumps({
            "tests_run": result.testsRun, "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors], "skipped": [reason for _, reason in result.skipped],
            "skipped_tests": [{"name": test.id(), "reason": reason} for test, reason in result.skipped],
            "passed": result.wasSuccessful(), "sanitizer": bool(os.environ.get("ACCESSIBILITY_SETTINGS_SANITIZE")),
            "other_target": bool(os.environ.get("ACCESSIBILITY_SETTINGS_OTHER_TARGET")),
            "screen_curtain": not NO_SCREEN_CURTAIN,
            "tagcache": not NO_TAGCACHE, "rtc": False,
            "unsigned_str": bool(os.environ.get("ACCESSIBILITY_SETTINGS_UNSIGNED_STR")),
            "host_os": os.name, "platform": sys.platform,
            "source_unchanged": all((ROOT / path).read_bytes() == content
                for path, content in getattr(AccessibilitySettingsTests, "source_bytes", {}).items()),
        }, indent=2), encoding="utf-8")
    sys.exit(not result.wasSuccessful())
