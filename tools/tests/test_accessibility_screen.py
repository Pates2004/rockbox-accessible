"""Exercise the entire production screen policy with faultable C host services."""

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


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "apps/accessibility_screen.c", "apps/accessibility_screen.h", "apps/talk.c",
    "apps/talk.h", "apps/settings.h", "firmware/common/timefuncs.c",
    "apps/lang/english.lang", "tools/project_materials.py",
    "apps/lang/polski.lang", "apps/playback.c", "apps/audio_thread.c",
    "firmware/export/audio.h", "lib/rbcodec/metadata/metadata.c",
    "lib/rbcodec/metadata/metadata.h", "apps/tts.c",
    "tools/tests/test_accessibility_screen.py",
)
COUNTERS = (
    "open_read", "read", "close_read", "open_write", "write", "fsync",
    "close_write", "rename", "remove", "menu", "splash", "splash_label",
    "splash_ticks", "menu_initial", "menu_title", "menu_count", "get_time",
    "valid_time", "talk_time", "snapshot", "time_enqueue", "battery", "force",
    "talk_date", "date_snapshot", "audio_status", "peek", "metadata", "locks",
)
FAULTS = (
    "none", "open_read", "read_error", "read_zero", "close_read", "open_write",
    "write_error", "write_zero", "fsync", "close_write", "rename",
)
PREFIX = 424240
REDRAW = 424241
ID, NUMBER, VALUE, FORCE = range(1, 5)
TEXT = 5
EVIDENCE_AREA = "r1-gesture-extensions-20261016/date-summary"


def extract_function(source, name):
    match = re.search(r"^[\w *]+\b" + re.escape(name) + r"\([^;]*?\n\{.*?^\}",
                      source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"Cannot extract production function {name}")
    return match[0] + "\n"


def policy(unlocked=0, locked=0):
    return f"RBACCESSIBILITY-SCREEN:1\nunlock:{unlocked}\nlock:{locked}\n".encode("ascii")


HOST_HEADER = r'''
#ifndef SCREEN_TEST_HOST_H
#define SCREEN_TEST_HOST_H
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sys/types.h>
#include <fcntl.h>
#include "config.h"
#include "lang.h"
#include "settings.h"
#include "metadata.h"
#include "audio.h"
#define ROCKBOX_DIR "/.rockbox"
#define HZ 100
#define MENU_ATTACHED_USB 313
#define ID2P(value) ((const unsigned char *)(uintptr_t)(value))
#define STR(value) ID2P(value), (value)
struct opt_items { const unsigned char *string; int32_t voice_id; };
enum optiontype { RB_INT };
const unsigned char *str(int label);
bool set_option(const unsigned char *title, int *choice, enum optiontype kind,
                const struct opt_items *items, int count, void *callback);
void splash(int ticks, const unsigned char *label);
int battery_level(void);
int talk_id(int32_t label, bool enqueue);
int talk_number(long value, bool enqueue);
int talk_value(long value, int unit, bool enqueue);
int talk_spell(const char *text, bool enqueue);
void talk_time(const struct tm *value, bool enqueue);
void talk_force_enqueue_next(void);
void host_talk_ids(bool enqueue, const long *labels, size_t count);
#define talk_ids(enqueue, ...) host_talk_ids(enqueue, (const long[]){__VA_ARGS__}, \
    sizeof((const long[]){__VA_ARGS__}) / sizeof(long))
#if CONFIG_RTC
struct tm *get_time(void);
bool valid_time(const struct tm *value);
#endif
int set_time(const struct tm *value);
int rtc_write_datetime(const struct tm *value);
void talk_date(const struct tm *value, bool enqueue);
int host_open(const char *path, int flags, ...);
ssize_t host_read(int descriptor, void *data, size_t capacity);
ssize_t host_write(int descriptor, const void *data, size_t count);
int host_fsync(int descriptor);
int host_close(int descriptor);
int host_rename(const char *source, const char *destination);
int host_remove(const char *path);
#define open host_open
#define read host_read
#define write host_write
#define fsync host_fsync
#define close host_close
#define rename host_rename
#define remove host_remove
#endif
'''


HOST_SERVICES = r'''
static unsigned char disk_data[16384], temp_data[16384];
static size_t disk_size, temp_size, disk_offset;
static bool disk_exists, temp_exists, read_active, write_active;
static int fault, fault_after, read_chunk, write_chunk;
static int counts[C_COUNT];
static const char *operations[1024];
static int operation_count;
static int menu_choice, menu_result, menu_items[8];
static int battery;
static struct tm clock_value;
static struct tm spoken_time;
static bool mutate_clock, force_next;
#if CONFIG_RTC
static bool clock_null;
#endif
static char date_format[8] = "dAY";
static char spoken_text[256][MAX_PATH];
static struct mp3entry live_track;
static int play_status, skip_offset, peek_offset;
static bool metadata_available, mutate_inputs;
#define PLAY_STOPPED 0
static void id3_mutex_lock(void) { ++counts[C_LOCKS]; }
static void id3_mutex_unlock(void) { --counts[C_LOCKS]; }
static bool audio_get_track_metadata(int offset, struct mp3entry *track)
{
    assert(counts[C_LOCKS] == 1);
    ++counts[C_METADATA];
    peek_offset = offset;
    if (!metadata_available) return false;
    copy_mp3entry(track, &live_track);
    return true;
}
PEEK_IMPLEMENTATION
int audio_status(void) { ++counts[C_AUDIO_STATUS]; return play_status; }
bool audio_peek_track(struct mp3entry *track, int offset)
{ ++counts[C_PEEK]; return production_audio_peek_track(track, offset); }
struct speech_event { int kind; long value; int unit; bool enqueue; };
static struct speech_event events[256], queued[256];
static int event_count, queue_count;
struct user_settings global_settings;

static void operation(const char *name)
{
    assert(operation_count < 1024);
    operations[operation_count++] = name;
}

int host_open(const char *path, int flags, ...)
{
    if (flags == O_RDONLY)
    {
        operation("open_read");
        ++counts[C_OPEN_READ];
        assert(!strcmp(path, ROCKBOX_DIR "/accessibility-screen.cfg"));
        assert(!read_active);
        if (!disk_exists || fault == F_OPEN_READ) return -1;
        disk_offset = 0;
        read_active = true;
        return 10;
    }
    operation("open_write");
    ++counts[C_OPEN_WRITE];
    assert(!strcmp(path, ROCKBOX_DIR "/accessibility-screen.cfg.tmp"));
    assert(flags == (O_WRONLY | O_CREAT | O_TRUNC));
    assert(!write_active);
    if (fault == F_OPEN_WRITE) return -1;
    temp_size = 0;
    temp_exists = write_active = true;
    return 11;
}

ssize_t host_read(int descriptor, void *data, size_t capacity)
{
    operation("read");
    ++counts[C_READ];
    assert(descriptor == 10 && read_active && disk_offset <= disk_size);
    if ((fault == F_READ_ERROR || fault == F_READ_ZERO) &&
        disk_offset >= (size_t)fault_after)
        return fault == F_READ_ERROR ? -1 : 0;
    size_t count = disk_size - disk_offset;
    if (count > capacity) count = capacity;
    if (read_chunk && count > (size_t)read_chunk) count = read_chunk;
    if ((fault == F_READ_ERROR || fault == F_READ_ZERO) &&
        disk_offset + count > (size_t)fault_after)
        count = (size_t)fault_after - disk_offset;
    memcpy(data, disk_data + disk_offset, count);
    disk_offset += count;
    return (ssize_t)count;
}

ssize_t host_write(int descriptor, const void *data, size_t count)
{
    operation("write");
    ++counts[C_WRITE];
    assert(descriptor == 11 && write_active && temp_exists);
    if ((fault == F_WRITE_ERROR || fault == F_WRITE_ZERO) &&
        temp_size >= (size_t)fault_after)
        return fault == F_WRITE_ERROR ? -1 : 0;
    if (write_chunk && count > (size_t)write_chunk) count = write_chunk;
    if ((fault == F_WRITE_ERROR || fault == F_WRITE_ZERO) &&
        temp_size + count > (size_t)fault_after)
        count = (size_t)fault_after - temp_size;
    assert(temp_size + count <= sizeof(temp_data));
    memcpy(temp_data + temp_size, data, count);
    temp_size += count;
    return (ssize_t)count;
}

int host_fsync(int descriptor)
{
    operation("fsync");
    ++counts[C_FSYNC];
    assert(descriptor == 11 && write_active);
    return fault == F_FSYNC ? -1 : 0;
}

int host_close(int descriptor)
{
    if (descriptor == 10)
    {
        operation("close_read");
        ++counts[C_CLOSE_READ];
        assert(read_active);
        read_active = false;
        return fault == F_CLOSE_READ ? -1 : 0;
    }
    operation("close_write");
    ++counts[C_CLOSE_WRITE];
    assert(descriptor == 11 && write_active);
    write_active = false;
    return fault == F_CLOSE_WRITE ? -1 : 0;
}

int host_rename(const char *source, const char *destination)
{
    operation("rename");
    ++counts[C_RENAME];
    assert(!strcmp(source, ROCKBOX_DIR "/accessibility-screen.cfg.tmp"));
    assert(!strcmp(destination, ROCKBOX_DIR "/accessibility-screen.cfg"));
    assert(temp_exists && !write_active && !read_active && counts[C_FSYNC]);
    if (fault == F_RENAME) return -1;
    memcpy(disk_data, temp_data, temp_size);
    disk_size = temp_size;
    disk_exists = true;
    temp_exists = false;
    temp_size = 0;
    return 0;
}

int host_remove(const char *path)
{
    operation("remove");
    ++counts[C_REMOVE];
    assert(!strcmp(path, ROCKBOX_DIR "/accessibility-screen.cfg.tmp"));
    assert(!write_active);
    temp_exists = false;
    temp_size = 0;
    return 0;
}

const unsigned char *str(int label) { return ID2P(label); }

bool set_option(const unsigned char *title, int *choice, enum optiontype kind,
                const struct opt_items *items, int count, void *callback)
{
    ++counts[C_MENU];
    counts[C_MENU_INITIAL] = *choice;
    counts[C_MENU_TITLE] = (int)(uintptr_t)title;
    counts[C_MENU_COUNT] = count;
    assert(kind == RB_INT && callback == NULL && count > 0 && count <= 8);
    for (int index = 0; index < count; ++index)
    {
        assert(items[index].string == ID2P(items[index].voice_id));
        menu_items[index] = items[index].voice_id;
    }
    if (menu_result != 2 && menu_choice != -999) *choice = menu_choice;
    return menu_result == 1;
}

void splash(int ticks, const unsigned char *label)
{
    ++counts[C_SPLASH];
    counts[C_SPLASH_LABEL] = (int)(uintptr_t)label;
    counts[C_SPLASH_TICKS] = ticks;
}

static void speech(int kind, long value, int unit, bool enqueue)
{
    assert(counts[C_LOCKS] == 0);
    if (mutate_inputs)
    {
        mutate_inputs = false;
        memset(live_track.id3v2buf, 'z', sizeof(live_track.id3v2buf) - 1);
        clock_value.tm_year = 127;
        clock_value.tm_mon = 0;
        clock_value.tm_mday = 1;
        clock_value.tm_hour = clock_value.tm_min = clock_value.tm_sec = 0;
        battery = -1;
    }
    assert(event_count < 256 && queue_count < 256);
    struct speech_event event = {kind, value, unit, enqueue};
    events[event_count++] = event;
    if (!enqueue && !force_next) queue_count = 0;
    force_next = false;
    queued[queue_count++] = event;
}

int talk_id(int32_t label, bool enqueue)
{ speech(1, label, 0, enqueue); return 0; }
int talk_number(long value, bool enqueue)
{ speech(2, value, 0, enqueue); return 0; }
int talk_value(long value, int unit, bool enqueue)
{ speech(3, value, unit, enqueue); return 0; }
int talk_spell(const char *text, bool enqueue)
{
    assert(strlen(text) < MAX_PATH);
    int index = event_count;
    snprintf(spoken_text[index], sizeof(spoken_text[index]), "%s", text);
    speech(5, index, 0, enqueue);
    return 0;
}
static void do_enqueue(bool enqueue)
{ if (!enqueue && !force_next) queue_count = 0; }
static const char *production_date_format(int label)
{ assert(label == LANG_VOICED_DATE_FORMAT); return date_format; }
DATE_IMPLEMENTATION

void host_talk_ids(bool enqueue, const long *labels, size_t count)
{
    for (size_t index = 0; index < count; ++index)
        talk_id((int32_t)labels[index], index ? true : enqueue);
}

void talk_force_enqueue_next(void)
{
    assert(event_count < 256);
    ++counts[C_FORCE];
    force_next = true;
    events[event_count++] = (struct speech_event){4, 0, 0, false};
}

int battery_level(void) { ++counts[C_BATTERY]; return battery; }

#if CONFIG_RTC
struct tm *get_time(void)
{ ++counts[C_GET_TIME]; return clock_null ? NULL : &clock_value; }
bool valid_time(const struct tm *value)
{ ++counts[C_VALID_TIME]; return production_valid_time(value); }
#endif

void talk_time(const struct tm *value, bool enqueue)
{
    ++counts[C_TALK_TIME];
    counts[C_TIME_ENQUEUE] = enqueue;
    spoken_time = *value;
    counts[C_SNAPSHOT] = value != &clock_value &&
        value->tm_sec == clock_value.tm_sec && value->tm_min == clock_value.tm_min &&
        value->tm_hour == clock_value.tm_hour && value->tm_mday == clock_value.tm_mday &&
        value->tm_mon == clock_value.tm_mon && value->tm_year == clock_value.tm_year &&
        value->tm_wday == clock_value.tm_wday && value->tm_yday == clock_value.tm_yday &&
        value->tm_isdst == clock_value.tm_isdst;
    if (mutate_clock) clock_value.tm_hour = 23;
    production_talk_time(value, enqueue);
}

void talk_date(const struct tm *value, bool enqueue)
{
    ++counts[C_TALK_DATE];
    counts[C_DATE_SNAPSHOT] = value != &clock_value &&
        (!counts[C_TALK_TIME] || (value->tm_year == spoken_time.tm_year &&
        value->tm_mon == spoken_time.tm_mon && value->tm_mday == spoken_time.tm_mday &&
        value->tm_hour == spoken_time.tm_hour && value->tm_min == spoken_time.tm_min &&
        value->tm_sec == spoken_time.tm_sec));
    production_talk_date(value, enqueue);
}

void probe_clear(void)
{
    assert(!read_active && !write_active);
    memset(counts, 0, sizeof(counts));
    operation_count = event_count = queue_count = 0;
    menu_choice = -999;
    menu_result = 0;
    force_next = false;
}

void probe_restart(void)
{
    screen_state_loaded = false;
    unlock_notice = SCREEN_UNLOCK_STATE;
    lock_notice = SCREEN_LOCK_STATE;
    probe_clear();
}

void probe_reset(void)
{
    disk_size = temp_size = disk_offset = 0;
    disk_exists = temp_exists = read_active = write_active = false;
    fault = fault_after = read_chunk = write_chunk = 0;
    mutate_clock = false;
#if CONFIG_RTC
    clock_null = false;
#endif
    mutate_inputs = metadata_available = false;
    play_status = skip_offset = peek_offset = 0;
    memset(&live_track, 0, sizeof(live_track));
    memset(spoken_text, 0, sizeof(spoken_text));
    snprintf(date_format, sizeof(date_format), "%s", "dAY");
    battery = 73;
    memset(&clock_value, 0, sizeof(clock_value));
    clock_value.tm_year = 126;
    clock_value.tm_mon = 9;
    clock_value.tm_mday = 15;
    clock_value.tm_wday = 4;
    clock_value.tm_yday = 287;
    clock_value.tm_hour = 13;
    clock_value.tm_min = 5;
    clock_value.tm_sec = 47;
    clock_value.tm_isdst = -1;
    global_settings = (struct user_settings){.tts_enabled = true};
    probe_restart();
}

void probe_disk(const char *data, size_t length)
{
    assert(length <= sizeof(disk_data) && !read_active && !write_active);
    memcpy(disk_data, data, length);
    disk_size = length;
    disk_exists = true;
}
const void *probe_disk_data(void) { return disk_data; }
size_t probe_disk_size(void) { return disk_size; }
bool probe_disk_exists(void) { return disk_exists; }
bool probe_temp_exists(void) { return temp_exists; }
bool probe_descriptors_closed(void) { return !read_active && !write_active; }
bool probe_forced(void) { return force_next; }
void probe_fault(int value, int after, int reading, int writing)
{ fault = value; fault_after = after; read_chunk = reading; write_chunk = writing; }
void probe_menu(int choice, int result) { menu_choice = choice; menu_result = result; }
int probe_stat(int index) { assert(index >= 0 && index < C_COUNT); return counts[index]; }
int probe_menu_item(int index)
{ assert(index >= 0 && index < counts[C_MENU_COUNT]); return menu_items[index]; }
int probe_operations(void) { return operation_count; }
const char *probe_operation(int index)
{ assert(index >= 0 && index < operation_count); return operations[index]; }
int probe_event_count(bool queue) { return queue ? queue_count : event_count; }
long probe_event(int index, int field, bool queue)
{
    assert(index >= 0 && index < (queue ? queue_count : event_count));
    struct speech_event event = queue ? queued[index] : events[index];
    switch (field)
    {
        case 0: return event.kind;
        case 1: return event.value;
        case 2: return event.unit;
        case 3: return event.enqueue;
        default: assert(false); return 0;
    }
}
void probe_gate(bool tts, bool menus)
{ global_settings.tts_enabled = tts; global_settings.talk_menu = menus; }
void probe_battery(int level) { battery = level; }
void probe_clock(int field, int value)
{
    switch (field)
    {
        case 0: clock_value.tm_hour = value; break;
        case 1: clock_value.tm_min = value; break;
        case 2: clock_value.tm_sec = value; break;
        case 3: clock_value.tm_year = value; break;
        case 4: clock_value.tm_mon = value; break;
        case 5: clock_value.tm_mday = value; break;
        case 6: clock_value.tm_wday = value; break;
        case 7: clock_value.tm_yday = value; break;
        case 8: clock_value.tm_isdst = value; break;
        case 9:
#if CONFIG_RTC
            clock_null = value;
#endif
            break;
        case 10: mutate_clock = value; break;
        default: assert(false);
    }
}
int probe_clock_field(int field)
{
    int fields[] = {clock_value.tm_hour, clock_value.tm_min, clock_value.tm_sec,
        clock_value.tm_year, clock_value.tm_mon, clock_value.tm_mday,
        clock_value.tm_wday, clock_value.tm_yday, clock_value.tm_isdst};
    assert(field >= 0 && field < 9);
    return fields[field];
}
void probe_format(int value) { global_settings.timeformat = value; }
void probe_prefix(void) { talk_id(424240, false); }
void probe_redraw(void) { talk_id(424241, false); }
int probe_percent(void) { return UNIT_PERCENT; }
void probe_track(const char *title, const char *path, int status, int offset, bool available)
{
    memset(&live_track, 0, sizeof(live_track));
    if (title)
    {
        snprintf(live_track.id3v2buf, sizeof(live_track.id3v2buf), "%s", title);
        live_track.title = live_track.id3v2buf;
    }
    if (path) snprintf(live_track.path, sizeof(live_track.path), "%s", path);
    play_status = status;
    skip_offset = offset;
    metadata_available = available;
}
void probe_mutate_inputs(bool mutate) { mutate_inputs = mutate; }
void probe_date_format(const char *format)
{ snprintf(date_format, sizeof(date_format), "%s", format); }
const char *probe_text(int index)
{ assert(index >= 0 && index < event_count); return spoken_text[index]; }
int probe_peek_offset(void) { return peek_offset; }
size_t probe_track_size(void) { return sizeof(struct mp3entry); }
void probe_unterminated_path(void) { memset(live_track.path, 'x', sizeof(live_track.path)); }
'''


class Host:
    def __init__(self, path, rtc, labels):
        self.rtc = rtc
        self.labels = labels
        self.library = ctypes.CDLL(str(path))
        signatures = {
            "probe_reset": (None, []), "probe_clear": (None, []),
            "probe_restart": (None, []),
            "probe_disk": (None, [ctypes.c_char_p, ctypes.c_size_t]),
            "probe_disk_data": (ctypes.c_void_p, []),
            "probe_disk_size": (ctypes.c_size_t, []),
            "probe_disk_exists": (ctypes.c_bool, []),
            "probe_temp_exists": (ctypes.c_bool, []),
            "probe_descriptors_closed": (ctypes.c_bool, []),
            "probe_forced": (ctypes.c_bool, []),
            "probe_fault": (None, [ctypes.c_int] * 4),
            "probe_menu": (None, [ctypes.c_int] * 2),
            "probe_stat": (ctypes.c_int, [ctypes.c_int]),
            "probe_menu_item": (ctypes.c_int, [ctypes.c_int]),
            "probe_operations": (ctypes.c_int, []),
            "probe_operation": (ctypes.c_char_p, [ctypes.c_int]),
            "probe_event_count": (ctypes.c_int, [ctypes.c_bool]),
            "probe_event": (ctypes.c_long, [ctypes.c_int, ctypes.c_int, ctypes.c_bool]),
            "probe_gate": (None, [ctypes.c_bool] * 2),
            "probe_battery": (None, [ctypes.c_int]),
            "probe_clock": (None, [ctypes.c_int] * 2),
            "probe_clock_field": (ctypes.c_int, [ctypes.c_int]),
            "probe_format": (None, [ctypes.c_int]),
            "probe_prefix": (None, []), "probe_redraw": (None, []),
            "probe_percent": (ctypes.c_int, []),
            "accessibility_speak_time": (ctypes.c_bool, [ctypes.c_bool]),
            "accessibility_speak_date": (ctypes.c_bool, [ctypes.c_bool]),
            "accessibility_speak_summary": (None, [ctypes.c_bool]),
            "probe_track": (None, [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_bool]),
            "probe_mutate_inputs": (None, [ctypes.c_bool]),
            "probe_date_format": (None, [ctypes.c_char_p]),
            "probe_text": (ctypes.c_char_p, [ctypes.c_int]),
            "probe_peek_offset": (ctypes.c_int, []),
            "probe_track_size": (ctypes.c_size_t, []),
            "probe_unterminated_path": (None, []),
            "accessibility_speak_battery": (None, [ctypes.c_bool]),
            "accessibility_screen_lock_changed": (None, [ctypes.c_bool]),
            "accessibility_screen_unlock_menu": (ctypes.c_int, []),
            "accessibility_screen_lock_menu": (ctypes.c_int, []),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.library, name)
            function.restype, function.argtypes = result, arguments
        self.percent = self.library.probe_percent()

    def reset(self, data=None):
        self.library.probe_reset()
        if data is not None:
            self.disk(data)

    def disk(self, data):
        self.library.probe_disk(data, len(data))

    def disk_bytes(self):
        return ctypes.string_at(self.library.probe_disk_data(), self.library.probe_disk_size())

    def stat(self, name):
        return self.library.probe_stat(COUNTERS.index(name))

    def fault(self, name="none", after=0, read_chunk=0, write_chunk=0):
        self.library.probe_fault(FAULTS.index(name), after, read_chunk, write_chunk)

    def menu(self, kind, choice=-999, result=0):
        self.library.probe_menu(choice, result)
        return getattr(self.library, f"accessibility_screen_{kind}_menu")()

    def selection(self, kind):
        self.menu(kind)
        return self.stat("menu_initial")

    def lock(self, locked):
        self.library.accessibility_screen_lock_changed(locked)

    def events(self, queue=False):
        return [tuple(self.library.probe_event(index, field, queue) for field in range(4))
                for index in range(self.library.probe_event_count(queue))]

    def operations(self):
        return [self.library.probe_operation(index).decode("ascii")
                for index in range(self.library.probe_operations())]

    def identifier(self, name, enqueue=True):
        return ID, self.labels[name], 0, int(enqueue)

    def number(self, value):
        return NUMBER, value, 0, 1

    def value(self, value):
        return VALUE, value, self.percent, 1

    def time_message(self, enqueue=False):
        prefix = self.identifier("LANG_CURRENT_TIME", enqueue)
        if not self.rtc:
            return [prefix, self.identifier("LANG_UNKNOWN")]
        return [prefix, self.number(13), self.identifier("VOICE_OH"), self.number(5)]

    def battery_message(self, enqueue=False, level=73):
        return [self.identifier("LANG_BATTERY_CHARGE", enqueue), self.value(level)]

    def date_message(self, enqueue=False):
        prefix = self.identifier("LANG_DATE", enqueue)
        if not self.rtc:
            return [prefix, self.identifier("LANG_UNKNOWN")]
        return [prefix, self.number(15), (ID, self.labels["LANG_MONTH_JANUARY"] + 9, 0, 1), self.number(2026)]

    def unlock_message(self, choice):
        messages = {
            0: [self.identifier("LANG_ACCESSIBILITY_SCREEN_UNLOCKED", False)],
            1: self.time_message(),
            2: self.battery_message(),
            3: self.time_message() + self.battery_message(True),
            4: [self.identifier("LANG_ACCESSIBILITY_SCREEN_UNLOCKED", False)] +
               self.time_message(True) + self.battery_message(True),
            5: [],
        }
        return messages[choice]


def input_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}


def build_hosts(workspace, windows=False):
    compiler = shlex.split(os.environ.get("SCREEN_WINDOWS_CC" if windows else "CC",
                                         "x86_64-w64-mingw32-gcc" if windows else "cc"))
    if not compiler or not shutil.which(compiler[0]):
        raise unittest.SkipTest(f"C compiler unavailable: {compiler}; use existing WSL tools")
    inputs = input_hashes()
    module = (ROOT / INPUTS[0]).read_text(encoding="utf-8")
    settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
    talk = (ROOT / "apps/talk.c").read_text(encoding="utf-8")
    time_source = (ROOT / "firmware/common/timefuncs.c").read_text(encoding="utf-8")
    talk_time = extract_function(talk, "talk_time")
    talk_date = extract_function(talk, "talk_date")
    talk_year = extract_function(talk, "talk_year")
    names = sorted(set(re.findall(r"\b(?:LANG|VOICE)_[A-Z0-9_]+", module + talk_time + talk_date + talk_year)))
    catalog = (ROOT / "apps/lang/english.lang").read_text(encoding="utf-8")
    for name in names:
        if not re.search(r"^\s*id:\s*" + re.escape(name) + r"\s*$", catalog, re.MULTILINE):
            raise AssertionError(f"Production speech identifier missing from catalog: {name}")
    labels = {name: index + 1000 for index, name in enumerate(names)}
    includes = workspace / "include"
    includes.mkdir()
    (includes / "config.h").write_text("#pragma once\n#ifndef SCREEN_NO_ESPEAK\n#define HAVE_ESPEAK 1\n#endif\n"
                                       "#define MAX_PATH 260\n#define MEMORYSIZE 16\n",
                                       encoding="utf-8")
    (includes / "platform.h").write_text('#include "host.h"\n', encoding="utf-8")
    metadata_path = (ROOT / "lib/rbcodec/metadata/metadata.h").as_posix()
    (includes / "metadata.h").write_text(f'#include "{metadata_path}"\n', encoding="utf-8")
    audio_header = (ROOT / "firmware/export/audio.h").read_text(encoding="utf-8")
    audio_defines = "\n".join(re.findall(r'^#define AUDIO_STATUS_[A-Z_]+\s+0x[0-9a-fA-F]+', audio_header, re.MULTILINE))
    (includes / "audio.h").write_text('#pragma once\n' + audio_defines +
        '\nstruct mp3entry;\nint audio_status(void);\nbool audio_peek_track(struct mp3entry *track, int offset);\n',
        encoding="utf-8")
    (includes / "lang.h").write_text("#pragma once\n" + "\n".join(
        f"#define {name} {value}" for name, value in labels.items()) + "\n", encoding="utf-8")
    settings_header = "#pragma once\n#include <stdbool.h>\nstruct user_settings {\n"
    for field in ("tts_enabled", "talk_menu", "timeformat"):
        declaration = re.findall(r"^\s*(?:bool|int)\s+" + field + r"\s*;", settings, re.MULTILINE)
        if len(declaration) != 1:
            raise AssertionError(f"Expected one production settings field: {field}")
        settings_header += declaration[0].strip() + "\n"
    settings_header += "};\nextern struct user_settings global_settings;\n"
    settings_header += extract_function(settings, "talk_tts_enabled")
    settings_header += extract_function(settings, "talk_menus_enabled")
    (includes / "settings.h").write_text(settings_header, encoding="utf-8")
    header_path = (ROOT / "apps/accessibility_screen.h").as_posix()
    (includes / "accessibility_screen.h").write_text(f'#include "{header_path}"\n', encoding="utf-8")
    for name in ("file.h", "kernel.h", "menu.h", "powermgmt.h", "rbpaths.h",
                 "splash.h", "talk.h", "timefuncs.h"):
        (includes / name).write_text('#include "host.h"\n', encoding="utf-8")
    (includes / "host.h").write_text(HOST_HEADER, encoding="utf-8")
    enums = "enum {" + ",".join("C_" + name.upper() for name in COUNTERS) + ",C_COUNT};\n"
    enums += "enum {" + ",".join("F_" + name.upper() for name in FAULTS) + "};\n"
    talk_header = (ROOT / "apps/talk.h").read_text(encoding="utf-8")
    unit_enum = re.search(r"^enum\s*\{.*?^\};", talk_header, re.MULTILINE | re.DOTALL)
    if unit_enum is None or "UNIT_PERCENT" not in unit_enum[0]:
        raise AssertionError("Cannot locate production talk unit enum")
    source = '#include "host.h"\n' + enums + unit_enum[0] + "\n"
    source += module + "\n#define talk_time production_talk_time\n" + talk_time
    source += "#undef talk_time\n#if CONFIG_RTC\n#define valid_time production_valid_time\n"
    source += extract_function(time_source, "valid_time") + "#undef valid_time\n#endif\n"
    metadata_source = (ROOT / "lib/rbcodec/metadata/metadata.c").read_text(encoding="utf-8")
    move_entry = re.search(r'^#define MOVE_ENTRY[^\n]+', metadata_source, re.MULTILINE)
    if move_entry is None:
        raise AssertionError("Cannot extract production metadata pointer relocation")
    source += move_entry[0] + "\n" + extract_function(metadata_source, "adjust_mp3entry")
    source += extract_function(metadata_source, "copy_mp3entry")
    playback = (ROOT / "apps/playback.c").read_text(encoding="utf-8")
    peek = "#define audio_peek_track production_audio_peek_track\n"
    peek += extract_function(playback, "audio_peek_track") + "#undef audio_peek_track\n"
    date = talk_year + "\n#define str production_date_format\n#define talk_date production_talk_date\n"
    date += talk_date + "#undef talk_date\n#undef str\n"
    source += HOST_SERVICES.replace("PEEK_IMPLEMENTATION", peek).replace("DATE_IMPLEMENTATION", date)
    generated = workspace / "screen-host.c"
    generated.write_text(source, encoding="utf-8")
    commands = []
    sanitize = not windows and os.environ.get("SCREEN_SANITIZE", "1") != "0"
    manifest = {"source_project": str(ROOT), "inputs": inputs, "labels": labels,
                "windows": windows, "ubsan": sanitize, "commands": commands, "binaries": {}}
    for rtc in (True, False):
        name = "rtc" if rtc else "no-rtc"
        output = workspace / (name + (".dll" if windows or os.name == "nt" else ".so"))
        command = compiler + ["-std=c99", "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-fstack-usage",
                              "-Wstrict-prototypes", "-shared", "-I", str(includes),
                              f"-DCONFIG_RTC={int(rtc)}", str(generated), "-o", str(output)]
        if windows:
            command += ["-static-libgcc", "-Wl,--no-undefined"]
        else:
            command += ["-fPIC", "-Wl,--no-undefined"]
        if windows or os.name == "nt":
            # Sanitizer exports must not hide the test API used by ctypes.
            command += ["-Wl,--export-all-symbols"]
        if sanitize:
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        commands.append({"argv": command, "returncode": result.returncode})
        (workspace / (name + "-compile.stdout.log")).write_text(result.stdout, encoding="utf-8")
        (workspace / (name + "-compile.stderr.log")).write_text(result.stderr, encoding="utf-8")
        (workspace / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if result.returncode:
            raise AssertionError(f"{name} compilation failed: {result.stderr}")
        manifest["binaries"][output.name] = hashlib.sha256(output.read_bytes()).hexdigest()
    if inputs != input_hashes():
        raise AssertionError("Production inputs changed during host compilation")
    command = compiler + ["-std=c99", "-Wall", "-Wextra", "-Werror", "-fsyntax-only",
                          "-DSCREEN_NO_ESPEAK", "-I", str(includes), str(ROOT / INPUTS[0])]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    commands.append({"argv": command, "returncode": result.returncode})
    (workspace / "no-espeak-compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise AssertionError("No-eSpeak compilation failed: " + result.stderr)
    manifest["summary_stack_frames"] = [int(line.split("\t")[1])
        for path in sorted(workspace.glob("*.su")) for line in path.read_text(encoding="utf-8").splitlines()
        if re.search(r'\baccessibility_speak_summary\t', line)]
    (workspace / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def new_workspace():
    central = project_materials_root(ROOT)
    ensure_ignored_directories(central.parent, (central.name,))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    workspace = confined_path(central / EVIDENCE_AREA / stamp, central)
    workspace.mkdir(parents=True, exist_ok=False)
    return workspace


class AccessibilityScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = new_workspace()
        cls.inputs = input_hashes()
        cls.addClassCleanup(cls.report)
        prebuilt = os.environ.get("SCREEN_TEST_PREBUILT")
        if prebuilt:
            central = project_materials_root(ROOT)
            cls.binary_root = confined_path(Path(prebuilt), central / EVIDENCE_AREA)
            manifest = json.loads((cls.binary_root / "build.json").read_text(encoding="utf-8"))
            if not manifest["windows"] or manifest["inputs"] != cls.inputs:
                raise AssertionError("Windows binaries do not match the current production/test sources")
            for name, checksum in manifest["binaries"].items():
                binary = confined_path(cls.binary_root / name, cls.binary_root)
                if hashlib.sha256(binary.read_bytes()).hexdigest() != checksum:
                    raise AssertionError(f"Prebuilt host binary changed: {binary}")
        else:
            cls.binary_root = cls.workspace
            manifest = build_hosts(cls.workspace)
        cls.manifest = manifest
        suffix = ".dll" if os.name == "nt" else ".so"
        cls.hosts = [Host(cls.binary_root / (name + suffix), rtc, manifest["labels"])
                     for rtc, name in ((True, "rtc"), (False, "no-rtc"))]
        print("Screen policy evidence:", cls.workspace, flush=True)

    @classmethod
    def report(cls):
        after = input_hashes()
        report = {"source_project": str(ROOT), "inputs_before": cls.inputs, "inputs_after": after,
                  "sources_stable": cls.inputs == after, "platform": sys.platform,
                  "binary_root": str(getattr(cls, "binary_root", "")),
                  "build": getattr(cls, "manifest", None),
                  "entire_screen_module": True, "production_talk_time": True,
                  "production_talk_date": True, "production_audio_peek_track": True,
                  "production_mp3entry_copy": True,
                  "production_valid_time": True, "production_talk_menus_gate": True,
                  "filesystem_clock_battery_menu_speech_sinks_mocked": True,
                  "restart": "Reset production static policy state; preserve mock disk bytes",
                  "no_clock_setter": "Declared, intentionally undefined; linker rejects references",
                  "limits": ["No hardware, GUI, synthesis, NVDA or physical battery/RTC test",
                             "Language IDs are unique fixture tokens validated against the English catalog",
                             "Menu cancellation models set_option restoring the original selection",
                             "No timers or lock-hook integration; separate owner"]}
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if cls.inputs != after:
            raise AssertionError("Production/test inputs changed during behavioral validation")

    def setUp(self):
        for host in self.hosts:
            host.reset()

    def assert_clean(self, host):
        self.assertTrue(host.library.probe_descriptors_closed())
        self.assertFalse(host.library.probe_temp_exists())

    def assert_policy(self, host, unlocked, locked):
        self.assertEqual(host.selection("unlock"), unlocked)
        self.assertEqual(host.selection("lock"), locked)

    def assert_speech(self, host, expected, force=False):
        self.assertEqual(host.events(), expected + ([(FORCE, 0, 0, 0)] if force else []))
        self.assertEqual(host.events(queue=True), expected)
        self.assertEqual(host.stat("force"), int(force))
        self.assertEqual(host.library.probe_forced(), force)

    def test_six_unlock_choices_and_both_lock_choices_queue_exact_messages(self):
        for host in self.hosts:
            for unlocked in range(6):
                for locked in range(2):
                    with self.subTest(rtc=host.rtc, unlocked=unlocked, locked=locked):
                        host.reset(policy(unlocked, locked))
                        host.lock(False)
                        self.assert_speech(host, host.unlock_message(unlocked), unlocked != 5)
                        self.assertEqual(host.stat("battery"), int(unlocked in (2, 3, 4)))
                        self.assertEqual(host.stat("talk_time"), int(host.rtc and unlocked in (1, 3, 4)))
                        self.assertEqual(host.stat("open_write"), 0)
                        host.library.probe_clear()
                        host.lock(True)
                        expected = [] if locked else [host.identifier("LANG_ACCESSIBILITY_SCREEN_LOCKED", False)]
                        self.assert_speech(host, expected, locked == 0)
                        self.assertEqual(host.stat("battery"), 0)
                        self.assertEqual(host.stat("get_time"), 0)

    def test_transition_force_flag_follows_entire_message_and_survives_one_redraw(self):
        for host in self.hosts:
            for locked, choice in [(False, value) for value in range(5)] + [(True, 0)]:
                with self.subTest(rtc=host.rtc, locked=locked, choice=choice):
                    host.reset(policy(choice, 0))
                    host.lock(locked)
                    message = host.events(queue=True)
                    self.assertEqual(host.events()[-1], (FORCE, 0, 0, 0))
                    self.assertEqual(host.stat("force"), 1)
                    host.library.probe_redraw()
                    redraw = (ID, REDRAW, 0, 0)
                    self.assertEqual(host.events(queue=True), message + [redraw])
                    self.assertFalse(host.library.probe_forced())
                    host.library.probe_redraw()
                    self.assertEqual(host.events(queue=True), [redraw])

    def test_silent_transition_does_not_force_or_disturb_existing_speech(self):
        for host in self.hosts:
            for locked in (False, True):
                with self.subTest(rtc=host.rtc, locked=locked):
                    host.reset(policy(5, 1))
                    host.library.probe_prefix()
                    before = host.events()
                    host.lock(locked)
                    self.assertEqual(host.events(), before)
                    self.assertEqual(host.events(queue=True), before)
                    self.assertEqual(host.stat("force"), 0)
                    host.library.probe_redraw()
                    self.assertEqual(host.events(queue=True), [(ID, REDRAW, 0, 0)])

    def test_real_talk_menus_gate_complete_matrix_for_all_entry_points(self):
        for host in self.hosts:
            for tts in (False, True):
                for menus in (False, True):
                    for operation in ("time", "date", "summary", "battery", "unlock", "lock"):
                        with self.subTest(rtc=host.rtc, tts=tts, menus=menus, operation=operation):
                            host.reset(policy(4, 0))
                            host.library.probe_gate(tts, menus)
                            if operation == "time":
                                result = host.library.accessibility_speak_time(False)
                                self.assertEqual(result, host.rtc and (tts or menus))
                            elif operation == "date":
                                result = host.library.accessibility_speak_date(False)
                                self.assertEqual(result, host.rtc and (tts or menus))
                            elif operation == "summary":
                                host.library.accessibility_speak_summary(False)
                            elif operation == "battery":
                                host.library.accessibility_speak_battery(False)
                            else:
                                host.lock(operation == "lock")
                            if tts or menus:
                                self.assertGreater(len(host.events()), 0)
                                self.assertEqual(host.stat("force"), int(operation in ("unlock", "lock")))
                            else:
                                self.assertEqual(host.events(), [])
                                for counter in ("get_time", "talk_time", "talk_date", "battery", "audio_status", "peek", "force"):
                                    self.assertEqual(host.stat(counter), 0)
                            self.assertEqual(host.stat("open_write"), 0)

    def test_direct_time_preserves_or_replaces_prefix_without_forcing_next(self):
        for host in self.hosts:
            for enqueue in (False, True):
                with self.subTest(rtc=host.rtc, enqueue=enqueue):
                    host.reset()
                    host.library.probe_prefix()
                    self.assertEqual(host.library.accessibility_speak_time(enqueue), host.rtc)
                    message = host.time_message(enqueue)
                    self.assertEqual(host.events(), [(ID, PREFIX, 0, 0)] + message)
                    self.assertEqual(host.events(queue=True), ([(ID, PREFIX, 0, 0)] if enqueue else []) + message)
                    self.assertEqual(host.stat("force"), 0)
                    self.assertEqual(host.stat("open_read"), 0)
                    self.assertEqual(host.stat("get_time"), int(host.rtc))
                    self.assertEqual(host.stat("talk_time"), int(host.rtc))
                    if host.rtc:
                        self.assertEqual(host.stat("time_enqueue"), 1)
                        self.assertEqual(host.stat("snapshot"), 1)

    def test_clock_snapshot_is_independent_when_live_clock_changes_during_speech(self):
        host = self.hosts[0]
        host.library.probe_clock(10, 1)
        self.assertTrue(host.library.accessibility_speak_time(False))
        self.assert_speech(host, host.time_message())
        self.assertEqual(host.stat("snapshot"), 1)
        self.assertEqual(host.library.probe_clock_field(0), 23)

    def test_actual_talk_time_12_and_24_hour_formats_and_boundaries(self):
        host = self.hosts[0]
        cases = [
            (0, 0, 0, ["VOICE_OH", 0, "VOICE_HUNDRED", "VOICE_HOURS"]),
            (0, 9, 5, ["VOICE_OH", 9, "VOICE_OH", 5]),
            (0, 12, 0, [12, "VOICE_HUNDRED", "VOICE_HOURS"]),
            (0, 13, 5, [13, "VOICE_OH", 5]),
            (0, 23, 59, [23, 59]),
            (1, 0, 0, [12, "VOICE_OCLOCK", "VOICE_AM"]),
            (1, 0, 5, [12, "VOICE_OH", 5, "VOICE_AM"]),
            (1, 9, 15, [9, 15, "VOICE_AM"]),
            (1, 12, 0, [12, "VOICE_OCLOCK", "VOICE_PM"]),
            (1, 12, 5, [12, "VOICE_OH", 5, "VOICE_PM"]),
            (1, 13, 5, [1, "VOICE_OH", 5, "VOICE_PM"]),
            (1, 23, 59, [11, 59, "VOICE_PM"]),
        ]
        for timeformat, hour, minute, tokens in cases:
            with self.subTest(timeformat=timeformat, hour=hour, minute=minute):
                host.reset()
                host.library.probe_format(timeformat)
                host.library.probe_clock(0, hour)
                host.library.probe_clock(1, minute)
                self.assertTrue(host.library.accessibility_speak_time(False))
                expected = [host.identifier("LANG_CURRENT_TIME", False)] + [
                    host.number(token) if isinstance(token, int) else host.identifier(token)
                    for token in tokens]
                self.assert_speech(host, expected)
                self.assertEqual(host.stat("talk_time"), 1)
                self.assertEqual(host.stat("snapshot"), 1)

    def test_unknown_clock_uses_actual_valid_time_and_never_reads_date_or_sets_clock(self):
        host = self.hosts[0]
        cases = [(9, 1), (0, -1), (0, 24), (1, -1), (1, 60), (2, -1), (2, 60),
                 (3, 99), (3, 200), (4, -1), (4, 12), (5, 0), (5, 32), (6, -1), (6, 7)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                host.reset()
                host.library.probe_clock(field, value)
                before = [host.library.probe_clock_field(index) for index in range(9)]
                self.assertFalse(host.library.accessibility_speak_time(False))
                self.assert_speech(host, [host.identifier("LANG_CURRENT_TIME", False),
                                          host.identifier("LANG_UNKNOWN")])
                self.assertEqual(host.stat("valid_time"), 1)
                self.assertEqual(host.stat("talk_time"), 0)
                self.assertEqual(before, [host.library.probe_clock_field(index) for index in range(9)])

    def test_unknown_clock_preserves_unlock_time_battery_order(self):
        for host in self.hosts:
            for choice in (1, 3, 4):
                with self.subTest(rtc=host.rtc, choice=choice):
                    host.reset(policy(choice, 0))
                    host.library.probe_clock(9, 1)
                    host.lock(False)
                    expected = ([host.identifier("LANG_ACCESSIBILITY_SCREEN_UNLOCKED", False)]
                                if choice == 4 else [])
                    expected += [host.identifier("LANG_CURRENT_TIME", choice == 4),
                                 host.identifier("LANG_UNKNOWN")]
                    if choice != 1:
                        expected += host.battery_message(True)
                    self.assert_speech(host, expected, True)

    def test_direct_battery_boundaries_unknown_values_and_prefix_flags(self):
        for host in self.hosts:
            for level in (-2147483648, -100, -1, 0, 1, 73, 99, 100, 101, 2147483647):
                for enqueue in (False, True):
                    with self.subTest(rtc=host.rtc, level=level, enqueue=enqueue):
                        host.reset()
                        host.library.probe_battery(level)
                        host.library.probe_prefix()
                        host.library.accessibility_speak_battery(enqueue)
                        message = [host.identifier("LANG_BATTERY_CHARGE", enqueue),
                                   host.value(level) if 0 <= level <= 100 else host.identifier("LANG_UNKNOWN")]
                        self.assertEqual(host.events(), [(ID, PREFIX, 0, 0)] + message)
                        self.assertEqual(host.events(queue=True), ([(ID, PREFIX, 0, 0)] if enqueue else []) + message)
                        self.assertEqual(host.stat("battery"), 1)
                        self.assertEqual(host.stat("force"), 0)
                        self.assertEqual(host.stat("open_read"), 0)
                        self.assertEqual(host.stat("get_time"), 0)

    def test_unknown_battery_in_unlock_policies_keeps_entire_message(self):
        for host in self.hosts:
            for choice in (2, 3, 4):
                for level in (-1, 101):
                    with self.subTest(rtc=host.rtc, choice=choice, level=level):
                        host.reset(policy(choice, 0))
                        host.library.probe_battery(level)
                        host.lock(False)
                        expected = host.unlock_message(choice)
                        expected[-1] = host.identifier("LANG_UNKNOWN")
                        self.assert_speech(host, expected, True)

    def test_default_policy_is_lazy_and_announces_both_states_without_creating_file(self):
        for host in self.hosts:
            with self.subTest(rtc=host.rtc):
                self.assertEqual(host.operations(), [])
                host.library.accessibility_speak_time(False)
                host.library.accessibility_speak_battery(False)
                self.assertEqual(host.operations(), [])
                host.library.probe_clear()
                host.lock(True)
                self.assert_speech(host, [host.identifier("LANG_ACCESSIBILITY_SCREEN_LOCKED", False)], True)
                self.assertEqual(host.operations(), ["open_read"])
                host.library.probe_clear()
                host.lock(False)
                self.assert_speech(host, host.unlock_message(0), True)
                self.assertEqual(host.operations(), [])
                self.assertFalse(host.library.probe_disk_exists())
                self.assert_policy(host, 0, 0)
                self.assert_clean(host)

    def test_policy_is_cached_until_restart_and_then_reloads_disk(self):
        for host in self.hosts:
            with self.subTest(rtc=host.rtc):
                host.reset(policy(4, 1))
                self.assert_policy(host, 4, 1)
                host.disk(policy(2, 0))
                self.assert_policy(host, 4, 1)
                self.assertEqual(host.stat("open_read"), 1)
                host.library.probe_restart()
                self.assert_policy(host, 2, 0)
                self.assertEqual(host.stat("open_read"), 1)
                self.assertEqual(host.stat("open_write"), 0)

    def test_exact_v1_bytes_persist_every_policy_pair_and_restart_behavior(self):
        for host in self.hosts:
            for unlocked in range(6):
                for locked in range(2):
                    with self.subTest(rtc=host.rtc, unlocked=unlocked, locked=locked):
                        host.reset(policy((unlocked + 1) % 6, 1 - locked))
                        self.assertEqual(host.menu("unlock", unlocked), 0)
                        self.assertEqual(host.menu("lock", locked), 0)
                        self.assertEqual(host.disk_bytes(), policy(unlocked, locked))
                        self.assertEqual(host.stat("rename"), 2)
                        self.assertEqual(host.stat("fsync"), 2)
                        self.assertEqual(host.stat("splash"), 0)
                        self.assertEqual(host.events(), [])
                        self.assert_clean(host)
                        host.library.probe_restart()
                        self.assert_policy(host, unlocked, locked)
                        host.library.probe_clear()
                        host.lock(False)
                        self.assert_speech(host, host.unlock_message(unlocked), unlocked != 5)

    def test_successful_commit_orders_write_sync_close_rename(self):
        for host in self.hosts:
            with self.subTest(rtc=host.rtc):
                host.reset(policy(2, 1))
                self.assert_policy(host, 2, 1)
                host.library.probe_clear()
                self.assertEqual(host.menu("unlock", 4), 0)
                self.assertEqual(host.operations(), ["open_write", "write", "fsync", "close_write", "rename"])
                self.assertEqual(host.disk_bytes(), policy(4, 1))
                self.assert_policy(host, 4, 1)
                self.assert_clean(host)

    def test_partial_reads_and_writes_complete_exact_policy_without_false_errors(self):
        for host in self.hosts:
            for chunk in (1, 2, 3, 7, len(policy()) - 1):
                with self.subTest(rtc=host.rtc, chunk=chunk):
                    host.reset(policy(4, 1))
                    host.fault(read_chunk=chunk, write_chunk=chunk)
                    self.assert_policy(host, 4, 1)
                    self.assertGreater(host.stat("read"), 1)
                    self.assertEqual(host.menu("unlock", 2), 0)
                    self.assertGreater(host.stat("write"), 1)
                    self.assertEqual(host.stat("fsync"), 1)
                    self.assertEqual(host.stat("rename"), 1)
                    self.assertEqual(host.disk_bytes(), policy(2, 1))
                    self.assert_clean(host)
                    host.library.probe_restart()
                    self.assert_policy(host, 2, 1)

    def test_all_truncated_prefixes_reject_whole_policy(self):
        full = policy(4, 1)
        for host in self.hosts:
            for length in range(len(full)):
                with self.subTest(rtc=host.rtc, length=length):
                    host.reset(full[:length])
                    self.assert_policy(host, 0, 0)
                    self.assertEqual(host.disk_bytes(), full[:length])
                    self.assertEqual(host.stat("open_read"), 1)
                    self.assertEqual(host.stat("open_write"), 0)
                    self.assert_clean(host)

    def test_malformed_oversized_nul_and_trailing_data_reject_whole_file(self):
        full = policy(4, 1)
        cases = {
            "version": full.replace(b":1\n", b":2\n", 1),
            "version-zero": full.replace(b":1\n", b":0\n", 1),
            "wrong-header": full.replace(b"SCREEN", b"screen"),
            "wrong-key": full.replace(b"unlock:", b"Unlock:"),
            "missing-lock": full[:full.index(b"lock:1")],
            "reversed": b"RBACCESSIBILITY-SCREEN:1\nlock:1\nunlock:4\n",
            "duplicate": full + b"unlock:4\n",
            "crlf": full.replace(b"\n", b"\r\n"),
            "leading-space": b" " + full,
            "trailing-newline": full + b"\n",
            "trailing-space": full + b" ",
            "trailing-nul": full + b"\x00",
            "trailing-data": full + b"x",
            "oversized": full + b"x" * 4096,
            "bom": b"\xef\xbb\xbf" + full,
        }
        for index in range(len(full)):
            cases[f"nul-{index}"] = full[:index] + b"\0" + full[index + 1:]
        for host in self.hosts:
            for name, data in cases.items():
                with self.subTest(rtc=host.rtc, case=name):
                    host.reset(data)
                    self.assert_policy(host, 0, 0)
                    self.assertEqual(host.disk_bytes(), data)
                    self.assertEqual(host.stat("open_write"), 0)
                    self.assert_clean(host)

    def test_every_invalid_single_byte_and_multibyte_range_rejects_both_fields(self):
        full = policy(4, 1)
        for host in self.hosts:
            for kind, offset, accepted in (("unlock", full.index(b"4"), b"012345"),
                                           ("lock", len(full) - 2, b"01")):
                for value in range(256):
                    if value in accepted:
                        continue
                    with self.subTest(rtc=host.rtc, kind=kind, byte=value):
                        data = full[:offset] + bytes([value]) + full[offset + 1:]
                        host.reset(data)
                        self.assert_policy(host, 0, 0)
                        self.assertEqual(host.disk_bytes(), data)
                        self.assert_clean(host)
                for value in ("-1", "+1", "00", "01", "10", "256", "2147483648", " 1", "1 "):
                    with self.subTest(rtc=host.rtc, kind=kind, value=value):
                        data = full[:offset] + value.encode("ascii") + full[offset + 1:]
                        host.reset(data)
                        self.assert_policy(host, 0, 0)
                        self.assertEqual(host.disk_bytes(), data)

    def test_read_errors_and_premature_eof_reject_partial_and_complete_prefixes(self):
        full = policy(4, 1)
        for host in self.hosts:
            for fault in ("read_error", "read_zero"):
                limits = range(len(full) + (fault == "read_error"))
                for after in limits:
                    with self.subTest(rtc=host.rtc, fault=fault, after=after):
                        host.reset(full)
                        host.fault(fault, after=after, read_chunk=3)
                        self.assert_policy(host, 0, 0)
                        self.assertEqual(host.stat("close_read"), 1)
                        self.assertEqual(host.disk_bytes(), full)
                        self.assertEqual(host.stat("open_write"), 0)
                        self.assert_clean(host)

    def test_open_and_close_read_failures_leave_defaults_and_disk_unchanged(self):
        for host in self.hosts:
            for fault in ("open_read", "close_read"):
                with self.subTest(rtc=host.rtc, fault=fault):
                    host.reset(policy(4, 1))
                    host.fault(fault)
                    self.assert_policy(host, 0, 0)
                    self.assertEqual(host.stat("close_read"), int(fault == "close_read"))
                    self.assertEqual(host.disk_bytes(), policy(4, 1))
                    self.assert_clean(host)
                    host.fault()
                    self.assert_policy(host, 0, 0)
                    self.assertEqual(host.stat("open_read"), 1)
                    host.library.probe_restart()
                    self.assert_policy(host, 4, 1)

    def test_write_faults_at_every_byte_preserve_old_memory_disk_and_cleanup_temp(self):
        for host in self.hosts:
            for kind, choice, old, new in (("unlock", 4, (2, 1), (4, 1)),
                                            ("lock", 1, (4, 0), (4, 1))):
                for fault in ("write_error", "write_zero"):
                    for after in range(len(policy(*new))):
                        with self.subTest(rtc=host.rtc, kind=kind, fault=fault, after=after):
                            host.reset(policy(*old))
                            self.assert_policy(host, *old)
                            host.library.probe_clear()
                            host.fault(fault, after=after, write_chunk=3)
                            self.assertEqual(host.menu(kind, choice), 0)
                            self.assertEqual(host.disk_bytes(), policy(*old))
                            self.assert_policy(host, *old)
                            self.assertEqual(host.stat("splash"), 1)
                            self.assertEqual(host.stat("splash_label"), host.labels["LANG_ERROR_WRITING_CONFIG"])
                            self.assertEqual(host.stat("splash_ticks"), 200)
                            self.assertEqual(host.stat("close_write"), 1)
                            self.assertEqual(host.stat("remove"), 1)
                            self.assertEqual(host.stat("fsync"), 0)
                            self.assertEqual(host.stat("rename"), 0)
                            self.assertEqual(host.events(), [])
                            self.assert_clean(host)
                            host.fault()
                            host.library.probe_restart()
                            self.assert_policy(host, *old)

    def test_open_sync_close_and_rename_failures_preserve_old_policy_and_allow_retry(self):
        for host in self.hosts:
            for kind, choice, old, new in (("unlock", 4, (2, 1), (4, 1)),
                                            ("lock", 1, (4, 0), (4, 1))):
                for fault in ("open_write", "fsync", "close_write", "rename"):
                    with self.subTest(rtc=host.rtc, kind=kind, fault=fault):
                        host.reset(policy(*old))
                        self.assert_policy(host, *old)
                        host.library.probe_clear()
                        host.fault(fault)
                        self.assertEqual(host.menu(kind, choice), 0)
                        self.assert_policy(host, *old)
                        self.assertEqual(host.disk_bytes(), policy(*old))
                        self.assertEqual(host.stat("splash"), 1)
                        self.assertEqual(host.stat("splash_label"), host.labels["LANG_ERROR_WRITING_CONFIG"])
                        self.assertEqual(host.stat("remove"), int(fault != "open_write"))
                        self.assertEqual(host.stat("rename"), int(fault == "rename"))
                        self.assertEqual(host.stat("close_write"), int(fault != "open_write"))
                        self.assert_clean(host)
                        host.fault()
                        host.library.probe_restart()
                        self.assert_policy(host, *old)
                        self.assertEqual(host.menu(kind, choice), 0)
                        self.assert_policy(host, *new)
                        self.assertEqual(host.disk_bytes(), policy(*new))
                        self.assert_clean(host)

    def test_failed_first_save_does_not_create_policy_file(self):
        for host in self.hosts:
            for fault in ("open_write", "write_error", "write_zero", "fsync", "close_write", "rename"):
                with self.subTest(rtc=host.rtc, fault=fault):
                    host.reset()
                    host.fault(fault)
                    self.assertEqual(host.menu("unlock", 4), 0)
                    self.assertFalse(host.library.probe_disk_exists())
                    self.assert_policy(host, 0, 0)
                    self.assert_clean(host)

    def test_cancel_usb_and_unchanged_menus_never_commit_or_change_either_policy(self):
        for host in self.hosts:
            for data in (None, policy(4, 1)):
                old = (0, 0) if data is None else (4, 1)
                for kind in ("unlock", "lock"):
                    for result in (0, 1, 2):
                        with self.subTest(rtc=host.rtc, present=data is not None, kind=kind, result=result):
                            host.reset(data)
                            self.assert_policy(host, *old)
                            host.library.probe_clear()
                            initial = old[0 if kind == "unlock" else 1]
                            proposed = initial if result == 0 else (initial + 1) % (6 if kind == "unlock" else 2)
                            self.assertEqual(host.menu(kind, proposed, result), 313 if result == 1 else 0)
                            self.assert_policy(host, *old)
                            self.assertEqual(host.operations(), [])
                            self.assertEqual(host.stat("splash"), 0)
                            self.assertEqual(host.events(), [])
                            self.assertEqual(host.library.probe_disk_exists(), data is not None)
                            if data is not None:
                                self.assertEqual(host.disk_bytes(), data)
                            self.assert_clean(host)

    def test_out_of_range_menu_values_fail_without_io_or_policy_changes(self):
        for host in self.hosts:
            for kind, values in (("unlock", (-2147483648, -1, 6, 10, 2147483647)),
                                 ("lock", (-2147483648, -1, 2, 6, 2147483647))):
                for choice in values:
                    with self.subTest(rtc=host.rtc, kind=kind, choice=choice):
                        host.reset(policy(4, 1))
                        self.assert_policy(host, 4, 1)
                        host.library.probe_clear()
                        self.assertEqual(host.menu(kind, choice), 0)
                        self.assert_policy(host, 4, 1)
                        self.assertEqual(host.disk_bytes(), policy(4, 1))
                        self.assertEqual(host.operations(), [])
                        self.assertEqual(host.stat("splash"), 1)
                        self.assert_clean(host)

    def test_menu_titles_options_and_initial_selection_are_actual_catalog_ids(self):
        expected = {
            "unlock": (4, "LANG_ACCESSIBILITY_SCREEN_UNLOCK_NOTICE", [
                "LANG_ACCESSIBILITY_SCREEN_SAY_UNLOCKED", "LANG_ACCESSIBILITY_ACTION_TIME",
                "LANG_ACCESSIBILITY_BATTERY", "LANG_ACCESSIBILITY_NOTICE_TIME_BATTERY",
                "LANG_ACCESSIBILITY_NOTICE_ALL", "LANG_ACCESSIBILITY_NOTICE_SILENT"]),
            "lock": (1, "LANG_ACCESSIBILITY_SCREEN_LOCK_NOTICE", [
                "LANG_ACCESSIBILITY_SCREEN_SAY_LOCKED", "LANG_ACCESSIBILITY_NOTICE_SILENT"]),
        }
        for host in self.hosts:
            host.reset(policy(4, 1))
            for kind, (selection, title, labels) in expected.items():
                with self.subTest(rtc=host.rtc, kind=kind):
                    self.assertEqual(host.menu(kind), 0)
                    self.assertEqual(host.stat("menu_initial"), selection)
                    self.assertEqual(host.stat("menu_title"), host.labels[title])
                    self.assertEqual(host.stat("menu_count"), len(labels))
                    self.assertEqual([host.library.probe_menu_item(index) for index in range(len(labels))],
                                     [host.labels[name] for name in labels])

    def test_no_operation_changes_system_clock_or_emits_date(self):
        for host in self.hosts:
            for unlocked in range(6):
                with self.subTest(rtc=host.rtc, unlocked=unlocked):
                    host.reset(policy(unlocked, 0))
                    before = [host.library.probe_clock_field(index) for index in range(9)]
                    host.library.accessibility_speak_time(False)
                    host.library.accessibility_speak_battery(False)
                    host.lock(False)
                    host.lock(True)
                    host.menu("unlock", (unlocked + 1) % 6)
                    host.menu("lock", 1)
                    self.assertEqual(before, [host.library.probe_clock_field(index) for index in range(9)])
                    self.assertEqual(host.stat("get_time"), 1 + int(unlocked in (1, 3, 4)) if host.rtc else 0)
                    self.assertEqual(host.stat("talk_date"), 0)

    def test_direct_date_uses_actual_localized_format_and_enqueue_contract(self):
        for host in self.hosts:
            for language in ("english", "polski"):
                catalog = (ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8")
                found = re.search(r'id: LANG_VOICED_DATE_FORMAT\b.*?<dest>\s*\*:\s*"([^"]+)"',
                                  catalog, re.DOTALL)
                self.assertIsNotNone(found)
                self.assertEqual(found[1], "dAY")
                for enqueue in (False, True):
                    with self.subTest(rtc=host.rtc, language=language, enqueue=enqueue):
                        host.reset()
                        host.library.probe_date_format(found[1].encode("ascii"))
                        host.library.probe_prefix()
                        self.assertEqual(host.library.accessibility_speak_date(enqueue), host.rtc)
                        message = host.date_message(enqueue)
                        self.assertEqual(host.events(), [(ID, PREFIX, 0, 0)] + message)
                        self.assertEqual(host.events(True), ([(ID, PREFIX, 0, 0)] if enqueue else []) + message)
                        self.assertEqual(host.stat("talk_date"), int(host.rtc))
                        self.assertEqual(host.stat("date_snapshot"), int(host.rtc))
                        self.assertEqual(host.stat("get_time"), int(host.rtc))
                        self.assertEqual(host.stat("battery"), 0)
                        self.assertEqual(host.stat("audio_status"), 0)
                        self.assertEqual(host.stat("force"), 0)

    def test_production_date_formatter_obeys_numeric_order_and_year_boundaries(self):
        host = self.hosts[0]
        for year in (100, 126, 199):
            with self.subTest(year=year):
                host.reset()
                host.library.probe_clock(3, year)
                host.library.probe_date_format(b"ymd")
                self.assertTrue(host.library.accessibility_speak_date(False))
                self.assert_speech(host, [host.identifier("LANG_DATE", False), host.number(1900 + year),
                                          host.number(10), host.number(15)])

    def test_direct_date_invalid_rtc_is_unknown_without_clock_mutation(self):
        host = self.hosts[0]
        for field, value in ((0, -1), (0, 24), (3, 99), (3, 200), (4, -1), (5, 32), (9, 1)):
            for enqueue in (False, True):
                with self.subTest(field=field, value=value, enqueue=enqueue):
                    host.reset()
                    host.library.probe_clock(field, value)
                    before = [host.library.probe_clock_field(index) for index in range(9)]
                    self.assertFalse(host.library.accessibility_speak_date(enqueue))
                    self.assert_speech(host, [host.identifier("LANG_DATE", enqueue), host.identifier("LANG_UNKNOWN")])
                    self.assertEqual(host.stat("talk_date"), 0)
                    self.assertEqual(before, [host.library.probe_clock_field(index) for index in range(9)])

    def test_summary_orders_four_fields_once_with_playing_or_paused_metadata(self):
        for host in self.hosts:
            for status in (1, 3):
                for enqueue in (False, True):
                    with self.subTest(rtc=host.rtc, status=status, enqueue=enqueue):
                        host.reset()
                        host.library.probe_track(b"Owned title", b"/music/example.mp3", status, 0, True)
                        host.library.probe_prefix()
                        host.library.accessibility_speak_summary(enqueue)
                        message = [host.identifier("LANG_TRACK", enqueue), (TEXT, 2, 0, 1)]
                        message += host.time_message(True) + host.date_message(True) + host.battery_message(True)
                        self.assertEqual(host.events(), [(ID, PREFIX, 0, 0)] + message)
                        self.assertEqual(host.events(True), ([(ID, PREFIX, 0, 0)] if enqueue else []) + message)
                        self.assertEqual(host.library.probe_text(2), b"Owned title")
                        for counter in ("audio_status", "peek", "metadata", "battery"):
                            self.assertEqual(host.stat(counter), 1)
                        self.assertEqual(host.stat("locks"), 0)
                        self.assertEqual(host.stat("get_time"), int(host.rtc))
                        self.assertEqual(host.stat("valid_time"), int(host.rtc))
                        self.assertEqual(host.stat("talk_date"), int(host.rtc))
                        self.assertEqual(host.stat("force"), 0)

    def test_summary_uses_one_owned_snapshot_across_midnight_and_metadata_changes(self):
        host = self.hosts[0]
        host.library.probe_track(b"Before skip", b"/music/original.mp3", 1, 0, True)
        for field, value in ((0, 23), (1, 59), (2, 59), (4, 11), (5, 31)):
            host.library.probe_clock(field, value)
        host.library.probe_mutate_inputs(True)
        host.library.accessibility_speak_summary(False)
        expected = [host.identifier("LANG_TRACK", False), (TEXT, 1, 0, 1),
                    host.identifier("LANG_CURRENT_TIME"), host.number(23), host.number(59),
                    host.identifier("LANG_DATE"), host.number(31),
                    (ID, host.labels["LANG_MONTH_JANUARY"] + 11, 0, 1), host.number(2026)]
        self.assert_speech(host, expected + host.battery_message(True))
        self.assertEqual(host.library.probe_text(1), b"Before skip")
        self.assertEqual(host.stat("date_snapshot"), 1)
        self.assertEqual(host.stat("get_time"), 1)
        self.assertEqual(host.stat("battery"), 1)
        self.assertEqual(host.library.probe_clock_field(3), 127)

    def test_summary_skip_offset_matches_real_peek_not_audible_track_claim(self):
        for host in self.hosts:
            for offset in (-2147483648, -3, 0, 4, 2147483647):
                with self.subTest(rtc=host.rtc, offset=offset):
                    host.reset()
                    host.library.probe_track(b"Playback selection", b"/music/selected.mp3", 1, offset, True)
                    host.library.accessibility_speak_summary(False)
                    self.assertEqual(host.library.probe_peek_offset(), offset)
                    self.assertEqual(host.library.probe_text(1), b"Playback selection")
                    self.assertEqual(host.stat("peek"), 1)

    def test_summary_stopped_recording_and_missing_metadata_never_reuse_old_track(self):
        for host in self.hosts:
            for status, available, path in ((0, True, b"/old.mp3"), (4, True, b"/recording.wav"),
                                            (1, False, b"/lost.mp3"), (3, False, b"/lost.mp3"),
                                            (1, True, b"")):
                with self.subTest(rtc=host.rtc, status=status, available=available, path=path):
                    host.reset()
                    host.library.probe_track(b"Previous title", b"/previous.mp3", 1, 0, True)
                    host.library.accessibility_speak_summary(False)
                    host.library.probe_clear()
                    host.library.probe_track(b"Must not be spoken", path, status, 0, available)
                    host.library.accessibility_speak_summary(False)
                    expected = [host.identifier("LANG_TRACK", False), host.identifier("LANG_UNKNOWN")]
                    self.assert_speech(host, expected + host.time_message(True) + host.date_message(True) +
                                       host.battery_message(True))
                    self.assertEqual(host.stat("peek"), int(bool(status & 1)))

    def test_summary_title_fallback_basename_and_missing_name_are_bounded(self):
        host = self.hosts[0]
        cases = ((None, b"/music/untagged.mp3", b"untagged.mp3"),
                 (b"", b"single.flac", b"single.flac"),
                 (b"Title", b"/music/fallback.mp3", b"Title"),
                 (None, b"/music/", None),
                 (b"x" * 4000, b"/long.mp3", b"x" * 259),
                 (("ą" * 1000).encode("utf-8"), b"/unicode.mp3", ("ą" * 129).encode("utf-8")),
                 (b"x" * 258 + "ą".encode("utf-8"), b"/boundary.mp3", b"x" * 258))
        for title, path, expected in cases:
            with self.subTest(title_length=len(title) if title else 0, path=path):
                host.reset()
                host.library.probe_track(title, path, 1, 0, True)
                host.library.accessibility_speak_summary(False)
                if expected is None:
                    self.assertEqual(host.events()[1], host.identifier("LANG_UNKNOWN"))
                else:
                    self.assertEqual(host.library.probe_text(1), expected)
                    expected.decode("utf-8")
                    self.assertLess(len(expected), 1024)
        host.reset()
        host.library.probe_track(None, b"/unterminated.mp3", 1, 0, True)
        host.library.probe_unterminated_path()
        host.library.accessibility_speak_summary(False)
        self.assertEqual(host.events()[1], host.identifier("LANG_UNKNOWN"))

    def test_summary_invalid_clock_and_battery_continue_with_honest_unknowns(self):
        for host in self.hosts:
            for field, value in ((0, 24), (1, -1), (3, 99), (3, 200), (4, 12), (5, 0), (9, 1)):
                for battery in (-2147483648, -1, 101, 2147483647):
                    with self.subTest(rtc=host.rtc, field=field, value=value, battery=battery):
                        host.reset()
                        host.library.probe_clock(field, value)
                        host.library.probe_battery(battery)
                        host.library.accessibility_speak_summary(False)
                        expected = []
                        for label in ("LANG_TRACK", "LANG_CURRENT_TIME", "LANG_DATE", "LANG_BATTERY_CHARGE"):
                            expected += [host.identifier(label, bool(expected)), host.identifier("LANG_UNKNOWN")]
                        self.assert_speech(host, expected)
                        self.assertEqual(host.stat("get_time"), int(host.rtc))
                        self.assertEqual(host.stat("talk_time"), 0)
                        self.assertEqual(host.stat("talk_date"), 0)
                        self.assertEqual(host.stat("battery"), 1)

    def test_queued_summary_text_survives_later_static_scratch_reuse(self):
        host = self.hosts[0]
        host.library.probe_track(b"First", b"/first.mp3", 1, 0, True)
        host.library.accessibility_speak_summary(False)
        previous = host.events(True)
        host.library.probe_track(b"Second", b"/second.mp3", 3, 0, True)
        host.library.accessibility_speak_summary(True)
        self.assertEqual(host.events(True)[:len(previous)], previous)
        texts = [host.library.probe_text(value) for kind, value, unit, enqueue in host.events(True) if kind == TEXT]
        self.assertEqual(texts, [b"First", b"Second"])

    def test_summary_battery_zero_and_full_are_sampled_once(self):
        for host in self.hosts:
            for battery in (0, 100):
                with self.subTest(rtc=host.rtc, battery=battery):
                    host.reset()
                    host.library.probe_battery(battery)
                    host.library.accessibility_speak_summary(False)
                    self.assertEqual(host.events()[-2:], host.battery_message(True, battery))
                    self.assertEqual(host.stat("battery"), 1)

    def test_full_metadata_snapshot_is_static_not_a_large_stack_frame(self):
        frames = self.manifest["summary_stack_frames"]
        self.assertEqual(len(frames), 2)
        self.assertTrue(all(0 < frame <= 512 for frame in frames), frames)
        self.assertGreater(self.hosts[0].library.probe_track_size(), 1800)


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.checks = []

    def addSubTest(self, test, subtest, error):
        super().addSubTest(test, subtest, error)
        self.checks.append({"test": subtest.id(), "passed": error is None})


if __name__ == "__main__":
    if sys.argv[1:] == ["--build-windows"]:
        workspace = new_workspace()
        build_hosts(workspace, windows=True)
        print("Windows host binaries:", workspace, flush=True)
    else:
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
        if hasattr(AccessibilityScreenTests, "workspace"):
            (AccessibilityScreenTests.workspace / "result.json").write_text(json.dumps({
                "tests_run": result.testsRun, "passed": result.wasSuccessful(),
                "failures": [{"test": test.id(), "traceback": detail} for test, detail in result.failures],
                "errors": [{"test": test.id(), "traceback": detail} for test, detail in result.errors],
                "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
                "subtests": result.checks,
            }, indent=2) + "\n", encoding="utf-8")
        sys.exit(not result.wasSuccessful())
