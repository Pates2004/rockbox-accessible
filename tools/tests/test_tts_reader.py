import ctypes
from datetime import datetime, timezone
import os
from pathlib import Path
import random
import re
import shlex
import subprocess
import unittest


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root
from test_keyclick_pcm import definition



ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps" / "tts_reader.c"
WORKSPACE = _project_materials_root(ROOT) / "tts-reader-tests"


def empty_feedback_policy():
    manager = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
    header = (ROOT / "apps/accessibility.h").read_text(encoding="utf-8")
    return (definition(header, "enum accessibility_empty_feedback\n") + ";\n" +
            "static enum accessibility_empty_feedback empty_feedback_mode;\n" +
            "static void accessibility_empty_load(void) {}\n" +
            "\n".join(definition(manager, signature) for signature in (
                "enum accessibility_empty_feedback accessibility_empty_feedback_mode(",
                "bool accessibility_empty_speech_enabled(")))



def reader_id2p_macro():
    """Keep the production macro's operand precedence in the C fixture."""
    settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
    definitions = re.findall(r'^#define ID2P\(id\) [^\n]*', settings,
                             flags=re.MULTILINE)
    if len(definitions) != 1:
        raise RuntimeError("Expected one ID2P definition in apps/settings.h")
    return definitions[0] + "\n"


def reader_support_glue():
    """Only preferences/UI endpoints are scripted; decoder/matcher are actual C."""
    header = (ROOT / "apps/tts_reader_settings.h").read_text(encoding="utf-8")
    header = re.sub(r'^#include[^\n]*\n', '', header, flags=re.MULTILINE)
    return header + r"""
typedef uint16_t ucschar_t;
enum yesno_res { YESNO_YES, YESNO_NO, YESNO_USB, YESNO_TMO };
struct text_message { const char **message_lines; int nb_lines; };
static struct tts_reader_preferences fixture_preferences;
static int fixture_preferences_error, fixture_preferences_writes;
static int keyboard_result, confirmation_result = YESNO_NO;
static bool keyboard_usb;
static char keyboard_text[129];
static int kbd_input_ex(char *text, int capacity, ucschar_t *layout, bool *usb)
{
    (void)layout;
    fixture_observe_reader(false);
    *usb = keyboard_usb;
    if (capacity > 0) snprintf(text, capacity, "%.*s", capacity - 1, keyboard_text);
    return keyboard_result;
}
static enum yesno_res gui_syncyesno_run(const struct text_message *question,
    const struct text_message *yes, const struct text_message *no)
{
    (void)question; (void)yes; (void)no;
    return (enum yesno_res)confirmation_result;
}
int tts_reader_preferences_get(struct tts_reader_preferences *out)
{
    *out = fixture_preferences;
    return fixture_preferences_error;
}
int tts_reader_preferences_set(enum tts_reader_preference preference, int value)
{
    if (fixture_preferences_error) return fixture_preferences_error;
    ++fixture_preferences_writes;
    if (preference == TTS_READER_PREF_MATCH_CASE)
        fixture_preferences.match_case = value != 0;
    else fixture_preferences.wrap = (enum tts_reader_wrap)value;
    return 0;
}
"""


HARNESS_PREFIX = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include "utf8proc.h"

#define DEBUGF(...) do { if (0) printf(__VA_ARGS__); } while (0)
#define ARRAYLEN(value) (sizeof(value) / sizeof((value)[0]))
#define MAX_PATH 260
#define CONFIG_KEYPAD 1
#define SANSA_CLIP_PAD 2
#define NB_SCREENS 1
#define SCREEN_MAIN 0
#define FOR_NB_SCREENS(index) for (int index = 0; index < NB_SCREENS; ++index)
#define PCM_MIXER_CHAN_VOICE 1
#define CHANNEL_STOPPED 0
#define HZ 100
#define TIMEOUT_NOBLOCK 0
#define MAX(first, second) ((first) > (second) ? (first) : (second))
#define CONTEXT_SETTINGS 20
#define CONTEXT_PLUGIN 0x10000000
#define CONTEXT_REMOTE 0x80000000
#define BUTTON_NONE 0
#define BUTTON_VOL_UP 1
#define BUTTON_VOL_DOWN 2
#define BUTTON_CENTER 4
#define BUTTON_UP 32
#define BUTTON_SELECT 64
#define BUTTON_REPEAT 8
#define BUTTON_REL 16
#define HAVE_TOUCHSCREEN
#define LAST_ITEM_IN_LIST__NEXTLIST(context) { context, BUTTON_NONE, BUTTON_NONE }
#define O_RDONLY 0
#define SYS_USB_CONNECTED 99
#define ACTION_UNKNOWN (-1)
enum { ACTION_NONE, ACTION_STD_CANCEL, ACTION_STD_OK, ACTION_STD_PREV,
       ACTION_STD_PREVREPEAT, ACTION_STD_NEXT, ACTION_STD_NEXTREPEAT,
       ACTION_SETTINGS_INC, ACTION_SETTINGS_INCREPEAT, ACTION_SETTINGS_DEC,
       ACTION_SETTINGS_DECREPEAT, ACTION_REDRAW, ACTION_STD_CONTEXT,
       ACTION_TOUCHSCREEN };
enum { LANG_TTS_READING, LANG_TTS_PAUSED, LANG_TTS_FINISHED,
       LANG_TTS_ERROR, LANG_TTS_INVALID_TEXT, LANG_READ_FAILED,
       LANG_TTS_UNIT_CHARACTER, LANG_TTS_UNIT_WORD, LANG_TTS_UNIT_LINE,
       LANG_TTS_UNIT_PARAGRAPH, LANG_TTS_UNIT_PAGE, LANG_TTS_NEWLINE,
       LANG_BOOKMARK_MENU, LANG_BOOKMARK_MENU_CREATE, LANG_BOOKMARK_MENU_LIST,
       LANG_BOOKMARK_CREATE_SUCCESS, LANG_BOOKMARK_CREATE_FAILURE,
       LANG_TTS_BOOKMARK_LOCAL_ONLY,
       LANG_TTS_BOOKMARK_CHANGED, LANG_PROPERTIES_FILENAME, LANG_PROPERTIES_PATH,
       LANG_PROPERTIES_SIZE, LANG_TTS_BYTES, LANG_TTS_POSITION,
       LANG_TTS_READER_UNIT, LANG_TTS_READER_MENU, LANG_TTS_RESUME,
       LANG_PROPERTIES, LANG_TTS_BEGINNING, LANG_TTS_END,
       LANG_TTS_FIND,
       LANG_TTS_FIND_NEXT,
       LANG_TTS_FIND_PREVIOUS,
       LANG_TTS_GOTO_LINE,
       LANG_TTS_GOTO_PAGE,
       LANG_TTS_GOTO_PERCENT,
       LANG_TTS_SEARCH_CASE,
       LANG_TTS_IGNORE_CASE,
       LANG_TTS_MATCH_CASE,
       LANG_TTS_SEARCH_WRAP,
       LANG_TTS_WRAP_STOP,
       LANG_TTS_WRAP_ASK,
       LANG_TTS_WRAP_AUTO,
       LANG_TTS_WRAP_QUESTION,
       LANG_TTS_FOUND,
       LANG_TTS_FOUND_WRAPPED,
       LANG_TTS_NO_MORE_MATCHES,
       LANG_TTS_QUERY_REQUIRED,
       LANG_TTS_QUERY_INVALID,
       LANG_TTS_DESTINATION_INVALID,
       LANG_TTS_READER_STORAGE_ERROR,
       LANG_TTS_OPERATION_FAILED,
       LANG_TTS_READER_BUSY,
       LANG_TTS_READER_TEMP_ERROR,
       LANG_TTS_READER_SETTINGS, LANG_TTS, LANG_ACCESSIBILITY_EMPTY };
static const char *labels[] = { "Reading", "Paused", "End of text",
    "Speech error", "Invalid text", "Failed reading %s", "Character", "Word",
    "Line", "Paragraph", "Page", "New line", "Bookmarks", "Create bookmark",
    "List bookmarks", "Bookmark saved", "Bookmark failed",
    "Bookmark saved, but recent bookmarks could not be updated", "Text changed",
    "Filename", "Path", "Size", "bytes", "Position", "Unit", "Text options",
    "Resume reading", "Properties", "Go to beginning", "Go to end",
    "Find",
    "Find next",
    "Find previous",
    "Go to line",
    "Go to page",
    "Go to percent",
    "Search case sensitivity",
    "Ignore case",
    "Match case",
    "Search at document boundary",
    "Stop and announce",
    "Ask to wrap",
    "Wrap automatically",
    "No further match. Search from the other end?",
    "Text found",
    "Text found after wrapping",
    "No further matches",
    "Enter a search first",
    "Enter valid text, up to 128 UTF-8 bytes",
    "Invalid destination",
    "Reader preferences could not be saved or loaded",
    "Text operation failed; position unchanged",
    "The text reader is already open",
    "Temporary reader preferences could not be removed",
    "Reading settings", "eSpeak", "No item" };
#define str(identifier) labels[identifier]
struct viewport { int x; int y; int width; int height; };
static bool reader_point_pending, reader_point_force;
static int reader_point_x, reader_point_y, reader_read_calls, reader_seek_calls;
static bool accessibility_explore_point(int *x, int *y, bool *force)
{
    if (!reader_point_pending) return false;
    reader_point_pending = false;
    *x = reader_point_x;
    *y = reader_point_y;
    *force = reader_point_force;
    return true;
}
static void accessibility_reset(void) {}
static void accessibility_explore_feedback(const void *owner, int target, bool occupied)
{ (void)owner; (void)target; (void)occupied; }
static void accessibility_set_target(const void *target) { (void)target; }
static bool viewport_point_within_vp(const struct viewport *viewport, int x, int y)
{
    return x >= viewport->x && y >= viewport->y &&
           x < viewport->x + viewport->width && y < viewport->y + viewport->height;
}
struct button_mapping { int action_code; int button_code; int prereq_button_code; };
static struct { int tts_reader_unit; int tts_reader_page_lines; } global_settings;
static int saves;
static int settings_save(void) { return ++saves; }

static const unsigned char *input;
static size_t input_size;
static size_t input_position;
static size_t read_limit;
static size_t largest_read;
static long fail_after;
static bool seek_failure;
static bool speech_failure;
static bool busy;
/* Model tts_stop returning while an earlier synthesis is still in flight. */
static bool initial_synthesis_busy;
static bool query_observed_initialized, close_observed_initialized;
static off_t query_observed_first, query_observed_cursor;
static off_t close_observed_first, close_observed_cursor;
static void fixture_observe_reader(bool closing);
static bool paused;
static bool unavailable;
static bool open_failure;
static bool size_failure;
static size_t audible_position;
static size_t interrupted_position;
static bool read_interrupted_flag;
static int channel;
static int stops;
static int pause_calls;
static int tracked_count;
static int character_count;
static uint32_t last_character;
static int pcm_remaining;
static int speech_count;
static int yields;
static int polls;
static int scan_action;
static int scan_after;
static int closed;
static int theme_undos;
static int actions[64];
static int action_count;
static int action_index;
static char speech[256][1024];
static char last_error[128];
static char rows[8][1024];
enum { BOOKMARK_FAIL = -1, BOOKMARK_SUCCESS, BOOKMARK_USB_CONNECTED };
enum text_bookmark_save_result {
    TEXT_BOOKMARK_FAILED, TEXT_BOOKMARK_SAVED, TEXT_BOOKMARK_SAVED_LOCAL_ONLY
};
#define MENU_ATTACHED_USB (-10)
struct text_bookmark { off_t offset; off_t size; uint32_t signature; int unit; };
struct menu_item_ex { int unused; };
const struct menu_item_ex tts_reader_settings_menu = {0};
const struct menu_item_ex tts_settings_menu = {0};
#define VIRT_PTR ((char *)0x10000)
""" + reader_id2p_macro() + r"""
#define MENUITEM_STRINGLIST(name, ...) struct menu_item_ex name = {0}
static int menu_choices[32];
static int menu_count;
static int menu_index;
static int release_waits;
static int bookmark_writes;
static int bookmark_result;
static bool bookmark_failure;
static bool bookmark_local_only;
static struct text_bookmark saved_bookmark;
static char saved_path[MAX_PATH];
static int do_menu(const struct menu_item_ex *menu, int *selected,
                   struct viewport *parent, bool hide)
{
    (void)menu; (void)selected; (void)parent; (void)hide;
    return menu_index < menu_count ? menu_choices[menu_index++] : -2;
}
static void action_wait_for_release(void) { ++release_waits; }
static enum text_bookmark_save_result bookmark_text_create_ex(
    const char *path, const struct text_bookmark *bookmark)
{
    ++bookmark_writes;
    saved_bookmark = *bookmark;
    snprintf(saved_path, sizeof(saved_path), "%s", path);
    return bookmark_failure ? TEXT_BOOKMARK_FAILED :
           bookmark_local_only ? TEXT_BOOKMARK_SAVED_LOCAL_ONLY :
           TEXT_BOOKMARK_SAVED;
}
static int bookmark_text_select(const char *path, struct text_bookmark *bookmark)
{
    (void)path;
    if (bookmark_result == BOOKMARK_SUCCESS)
        *bookmark = saved_bookmark;
    return bookmark_result;
}
static void splash(int ticks, const char *message);
struct simplelist_info {
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
    void *data;
};
static void simplelist_info_init(struct simplelist_info *info, const void *title,
                                 int count, void *data)
{
    (void)title; (void)count;
    info->data = data;
}
static bool simplelist_show_list(struct simplelist_info *info)
{
    char buffer[1024];
    for (int index = 0; index < 5; ++index)
    {
        info->get_name(index, info->data, buffer, sizeof(buffer));
        info->get_talk(index, info->data);
    }
    return false;
}

static off_t mock_seek(int descriptor, off_t offset, int origin)
{
    ++reader_seek_calls;
    (void)descriptor;
    (void)origin;
    if (seek_failure || offset < 0)
        return -1;
    input_position = offset;
    return offset;
}
static ssize_t mock_read(int descriptor, void *buffer, size_t count)
{
    ++reader_read_calls;
    (void)descriptor;
    if (count > largest_read)
        largest_read = count;
    if (fail_after >= 0 && input_position >= (size_t)fail_after)
        return -1;
    if (input_position >= input_size)
        return 0;
    if (count > input_size - input_position)
        count = input_size - input_position;
    if (read_limit && count > read_limit)
        count = read_limit;
    memcpy(buffer, input + input_position, count);
    input_position += count;
    return count;
}
static int mock_open(const char *path, int flags)
{
    (void)path;
    (void)flags;
    return open_failure ? -1 : 3;
}
static int mock_close(int descriptor)
{
    (void)descriptor;
    fixture_observe_reader(true);
    return ++closed;
}
static off_t ffilesize(int descriptor)
{
    (void)descriptor;
    return size_failure ? -1 : (off_t)input_size;
}
#define lseek mock_seek
#define read mock_read
#define open mock_open
#define close mock_close

static bool tts_is_available(void) { return !unavailable; }
static bool tts_is_busy(void) { return busy || initial_synthesis_busy; }
static size_t tts_read_position(void)
{ return read_interrupted_flag ? interrupted_position : audible_position; }
static bool tts_read_interrupted(void) { return read_interrupted_flag; }
static void tts_pause(bool value) { paused = value; ++pause_calls; }
static int mixer_channel_status(int channel_id) { (void)channel_id; return channel; }
static const char *tts_last_error(void) { return last_error; }
static void tts_stop(void)
{
    ++stops;
    busy = paused = false;
    channel = CHANNEL_STOPPED;
    audible_position = 0;
    pcm_remaining = 0;
    last_error[0] = '\0';
}
static int tts_speak(const char *text, size_t length, bool enqueue)
{
    (void)enqueue;
    if (speech_failure || length >= 1024)
        return -1;
    memcpy(speech[speech_count % 256], text, length);
    speech[speech_count++ % 256][length] = '\0';
    busy = true;
    return 0;
}
static int tts_speak_tracked(const char *text, size_t length)
{
    ++tracked_count;
    read_interrupted_flag = false;
    interrupted_position = 0;
    audible_position = 0;
    paused = false;
    pcm_remaining = 4096;
    return tts_speak(text, length, false);
}
static int tts_speak_character(uint32_t codepoint)
{
    ++character_count;
    last_character = codepoint;
    return tts_speak("character", 9, false);
}
static void splash(int ticks, const char *message)
{
    (void)ticks;
    uintptr_t value = (uintptr_t)message;
    if (value >= 0x10000 && value - 0x10000 < ARRAYLEN(labels))
        message = labels[value - 0x10000];
    tts_speak(message, strlen(message), false);
}
static void talk_force_shutup(void) { tts_stop(); }
static void yield(void) { ++yields; }
static void reset_poweroff_timer(void) {}
static int get_custom_action(int context, int timeout,
                             const struct button_mapping *(*mapping)(int))
{
    (void)mapping(context);
    if (timeout == TIMEOUT_NOBLOCK)
    {
        ++polls;
        if (scan_action && polls >= scan_after)
        {
            int action = scan_action;
            scan_action = ACTION_NONE;
            return action;
        }
        return ACTION_NONE;
    }
    return action_index < action_count ? actions[action_index++] : ACTION_STD_CANCEL;
}
static int default_event_handler_ex(int action, void (*cleanup)(void *), void *data)
{
    if (action == SYS_USB_CONNECTED)
        cleanup(data);
    return action;
}
static void screen_viewport(struct viewport *viewport) { (void)viewport; }
static void screen_void(void) {}
static int screen_height(void) { return 64; }
static int screen_charheight(void) { return 8; }
static void screen_puts(int column, int row, const unsigned char *text)
{
    (void)column;
    if (row >= 0 && row < 8)
        snprintf(rows[row], sizeof(rows[row]), "%s", text);
}
static struct screen {
    void (*set_viewport)(struct viewport *);
    void (*scroll_stop_viewport)(struct viewport *);
    void (*clear_viewport)(void);
    int (*getheight)(void);
    int (*getcharheight)(void);
    void (*puts_scroll)(int, int, const unsigned char *);
    void (*update_viewport)(void);
    void (*scroll_stop)(void);
} screens[] = {{ screen_viewport, screen_viewport, screen_void, screen_height,
                screen_charheight, screen_puts, screen_void, screen_void }};
static void viewportmanager_theme_enable(int screen, bool enable, struct viewport *viewport)
{
    (void)screen;
    (void)enable;
    (void)viewport;
}
static void viewportmanager_theme_undo(int screen, bool redraw)
{
    (void)screen;
    (void)redraw;
    ++theme_undos;
}
"""

HARNESS_PREFIX += reader_support_glue()

HARNESS_SUFFIX = r"""
static struct text_reader reader;

void test_reset(const unsigned char *data, size_t length)
{
    empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
    reader_point_pending = reader_point_force = false;
    reader_point_x = reader_point_y = reader_read_calls = reader_seek_calls = 0;
    input = data;
    input_size = length;
    input_position = 0;
    read_limit = largest_read = 0;
    fail_after = -1;
    seek_failure = speech_failure = busy = paused = false;
    initial_synthesis_busy = false;
    query_observed_initialized = close_observed_initialized = false;
    query_observed_first = query_observed_cursor = -1;
    close_observed_first = close_observed_cursor = -1;
    unavailable = open_failure = size_failure = false;
    audible_position = 0;
    channel = stops = speech_count = tracked_count = pause_calls = pcm_remaining = 0;
    interrupted_position = 0;
    read_interrupted_flag = false;
    character_count = last_character = 0;
    yields = polls = scan_action = scan_after = closed = theme_undos = saves = 0;
    action_count = action_index = 0;
    menu_count = menu_index = release_waits = bookmark_writes = 0;
    bookmark_failure = bookmark_local_only = false;
    bookmark_result = BOOKMARK_FAIL;
    memset(&saved_bookmark, 0, sizeof(saved_bookmark));
    last_error[0] = '\0';
    memset(rows, 0, sizeof(rows));
    memset(&reader, 0, sizeof(reader));
    memset(&reader_job, 0, sizeof(reader_job));
    reader.job = &reader_job;
    memset(&fixture_preferences, 0, sizeof(fixture_preferences));
    fixture_preferences_error = fixture_preferences_writes = 0;
    keyboard_result = 0;
    keyboard_usb = false;
    keyboard_text[0] = '\0';
    confirmation_result = YESNO_NO;
    reader.descriptor = 3;
    reader.name = "example.txt";
    reader.path = "/example.txt";
    reader.size = length;
    global_settings.tts_reader_unit = READER_WORD;
    global_settings.tts_reader_page_lines = 20;
}
int test_chunk(long start, long size, char *text, long *next)
{
    off_t end = *next;
    int result = reader_read_chunk(3, start, size, text, &end);
    *next = end;
    return result;
}
void test_short_reads(size_t limit) { read_limit = limit; }
void test_fail_after(long position) { fail_after = position; reader.cache_length = 0; }
void test_seek_failure(void) { seek_failure = true; reader.cache_length = 0; }
size_t test_largest_read(void) { return largest_read; }
long test_position(void) { return reader.cursor; }
int test_percent(void) { return reader_percent(&reader); }
int test_state(void) { return reader.state; }
const char *test_label(void) { return reader_label(&reader); }
const char *test_text(void) { return reader_current_text(&reader); }
int test_load(void) { return reader_load(&reader); }
void test_step(void) { reader_step(&reader); }
void test_reader_empty_mode(int mode) { empty_feedback_mode = mode; }
void test_reader_touch_setup(void)
{
    reader.viewports[0] = (struct viewport){0, 0, 200, 100};
    reader.touch_line_height = 10;
    reader.touch_lines = 5;
    reader.touch_row = -99;
    reader_point_pending = false;
}
void test_reader_touch(int row, bool force)
{
    reader_point_x = row < 0 ? 210 : 5;
    reader_point_y = row < 0 ? 5 : row * 10 + 1;
    reader_point_force = force;
    reader_point_pending = true;
    reader_explore(&reader);
}
void test_reader_state(int state, bool cached)
{
    reader.state = state;
    if (!cached) { reader.loaded = false; reader.cache_length = 0; }
}
int test_reader_touch_preserves(int row, bool force)
{
    struct text_reader before = reader;
    size_t before_input = input_position, before_audible = audible_position;
    size_t before_interrupted = interrupted_position;
    int before_stops = stops, before_reads = reader_read_calls, before_seeks = reader_seek_calls;
    int before_speech = speech_count, before_tracked = tracked_count, before_pcm = pcm_remaining;
    int before_channel = channel, before_pauses = pause_calls;
    bool before_busy = busy, before_paused = paused, before_interrupted_flag = read_interrupted_flag;
    test_reader_touch(row, force);
    before.touch_row = reader.touch_row;
    return !memcmp(&before, &reader, sizeof(reader)) && input_position == before_input &&
        audible_position == before_audible && interrupted_position == before_interrupted &&
        stops == before_stops && reader_read_calls == before_reads && reader_seek_calls == before_seeks &&
        speech_count == before_speech && tracked_count == before_tracked && pcm_remaining == before_pcm &&
        channel == before_channel && pause_calls == before_pauses && busy == before_busy &&
        paused == before_paused && read_interrupted_flag == before_interrupted_flag;
}
void test_external_notice(void)
{
    size_t position = tts_read_position();
    tts_stop();
    read_interrupted_flag = true;
    interrupted_position = position;
    tts_speak("Notice", 6, true);
}
void test_toggle(void) { reader_toggle(&reader); }
void test_navigate(int forward) { reader_navigate(&reader, forward); }
void test_unit(int unit) { global_settings.tts_reader_unit = unit; }
void test_page_lines(int lines) { global_settings.tts_reader_page_lines = lines; }
void test_change_unit(int increase) { reader_change_unit(&reader, increase); }
int test_get_unit(void) { return reader_unit(); }
int test_saves(void) { return saves; }
int test_seek(int unit, long cursor, int forward, long *target)
{
    int status = reader_prepare(&reader);
    if (status < 0)
        return status;
    global_settings.tts_reader_unit = unit;
    reader.cursor = cursor;
    reader.scanning = true;
    reader.scan_work = 0;
    off_t result = cursor;
    status = reader_seek_unit(&reader, forward, &result);
    reader.scanning = false;
    *target = result;
    return status;
}
void test_audio(int synthesizing, int status) { busy = synthesizing; channel = status; }
void test_audible(size_t position) { if (!paused) audible_position = position; }
void test_consume(int samples) { if (!paused) pcm_remaining -= samples; }
int test_pcm(void) { return pcm_remaining; }
int test_paused(void) { return paused; }
int test_pause_calls(void) { return pause_calls; }
int test_tracked_count(void) { return tracked_count; }
int test_character_count(void) { return character_count; }
uint32_t test_character(void) { return last_character; }
void test_error(const char *message) { snprintf(last_error, sizeof(last_error), "%s", message); }
void test_speech_failure(void) { speech_failure = true; }
int test_stops(void) { return stops; }
int test_speech_count(void) { return speech_count; }
const char *test_speech(int index) { return speech[index % 256]; }
void test_scan_action(int action, int after) { scan_action = action; scan_after = after; }
int test_yields(void) { return yields; }
int test_pending(void) { return reader.pending_action; }
void test_draw(void) { reader_draw(&reader); }
const char *test_row(int row) { return rows[row]; }
void test_action(int action) { actions[action_count++] = action; }
/* Defined after test_action and the fixture action enum. */
void test_context_action(void) { test_action(ACTION_STD_CONTEXT); }
int test_run(void) { return tts_read_file("/example.txt"); }
int test_closed(void) { return closed; }
int test_theme_undos(void) { return theme_undos; }
void test_open_failure(void) { open_failure = true; }
void test_size_failure(void) { size_failure = true; }
void test_unavailable(void) { unavailable = true; }
void test_available(void) { unavailable = false; }
void test_menu_choice(int choice) { menu_choices[menu_count++] = choice; }
int test_menu(void) { return reader_menu(&reader); }
int test_release_waits(void) { return release_waits; }
int test_bookmark_writes(void) { return bookmark_writes; }
long test_bookmark_offset(void) { return saved_bookmark.offset; }
void test_bookmark_failure(void) { bookmark_failure = true; }
void test_bookmark_local_only(void) { bookmark_local_only = true; }
void test_bookmark_result(int result) { bookmark_result = result; }
uint32_t test_signature(long offset)
{
    uint32_t result = 0;
    reader_signature(&reader, offset, &result);
    return result;
}
int test_restore(long offset, long size, int unit, uint32_t signature)
{
    struct text_bookmark bookmark = {offset, size, signature, unit};
    return reader_restore_bookmark(&reader, &bookmark);
}
const char *test_property(int index)
{
    static char buffer[1024];
    return reader_property(index, &reader, buffer, sizeof(buffer));
}

static void fixture_observe_reader(bool closing)
{
    const struct text_reader *active = reader_job.owner;
    if (!active)
        return;
    if (closing)
    {
        close_observed_initialized = active->initialized;
        close_observed_first = active->first;
        close_observed_cursor = active->cursor;
    }
    else
    {
        query_observed_initialized = active->initialized;
        query_observed_first = active->first;
        query_observed_cursor = active->cursor;
    }
}

void test_initial_speech_busy(void) { initial_synthesis_busy = true; }
int64_t test_initial_snapshot(int field)
{
    switch (field)
    {
        case 0: return query_observed_initialized;
        case 1: return query_observed_first;
        case 2: return query_observed_cursor;
        case 3: return close_observed_initialized;
        case 4: return close_observed_first;
        default: return close_observed_cursor;
    }
}

void test_edit(const char *text, int result, bool usb)
{
    snprintf(keyboard_text, sizeof(keyboard_text), "%s", text);
    menu_count = menu_index = 0;
    keyboard_result = result;
    keyboard_usb = usb;
}
void test_search_preferences(bool match_case, int wrap, int answer)
{
    fixture_preferences.match_case = match_case;
    fixture_preferences.wrap = (enum tts_reader_wrap)wrap;
    confirmation_result = answer;
}
const char *test_accepted_query(void) { return reader.job->accepted_query; }
void test_cursor64(int64_t cursor)
{
    reader_prepare(&reader);
    reader.cursor = (off_t)cursor;
}
int64_t test_position64(void) { return reader.cursor; }
int test_match_range(const char *query, int64_t low, int64_t high, bool previous,
                     bool match_case, int64_t *target)
{
    reader_prepare(&reader);
    reader.job->preferences.match_case = match_case;
    int status = reader_compile_query(reader.job, query);
    off_t result = -1;
    reader.scanning = true;
    reader.scan_work = 0;
    if (status >= 0)
        status = reader_search_range(&reader, low, high, previous, &result);
    reader.scanning = false;
    *target = result;
    return status;
}
int test_ordinal64(uint64_t ordinal, bool page, int64_t *target)
{
    reader_prepare(&reader);
    off_t result = -1;
    reader.scanning = true;
    reader.scan_work = 0;
    int status = reader_ordinal(&reader, ordinal, page, &result);
    reader.scanning = false;
    *target = result;
    return status;
}
int test_percent64(int64_t cursor, int64_t size)
{
    reader.cursor = cursor;
    reader.size = size;
    return reader_percent(&reader);
}
int64_t test_percent_target64(int64_t size, unsigned int percent)
{
    return reader_percent_offset(size, percent, false);
}
int test_decimal64(const char *text, uint64_t *value)
{
    return reader_decimal(text, value);
}
int test_offset_bits(void) { return 8 * sizeof(off_t); }
void test_menu_script_reset(void) { menu_count = menu_index = 0; }
int test_job_size(void) { return sizeof(reader_job); }
int test_nested_owner(void)
{
    if (!reader_job_acquire(&reader)) return 0;
    reader_job.accepted_query[0] = 'x';
    bool usb = tts_read_file("/nested.txt");
    bool intact = !usb && reader_job.owner == &reader &&
        reader_job.accepted_query[0] == 'x';
    reader_job_release(&reader);
    return intact;
}
int test_preference_writes(void) { return fixture_preferences_writes; }

int test_mapping(int context, int button)
{
    const struct button_mapping *mapping = reader_context(context);
    while (mapping->button_code)
    {
        if (mapping->button_code == button)
            return mapping->action_code;
        ++mapping;
    }
    return mapping->action_code;
}
"""


class TextReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = WORKSPACE / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace.mkdir(parents=True, exist_ok=False)
        source = re.sub(r'^#include[^\n]*\n', '', SOURCE.read_text(encoding="utf-8"),
                        flags=re.MULTILINE)
        prefix = HARNESS_PREFIX + empty_feedback_policy()
        harness = cls.workspace / "reader.c"
        harness.write_text(prefix + source + HARNESS_SUFFIX, encoding="utf-8")
        library = cls.workspace / "reader.so"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
            "-DUTF8PROC_STATIC", "-I", str(ROOT / "lib" / "utf8proc"),
            str(harness), str(ROOT / "lib" / "utf8proc" / "utf8proc.c"),
            "-o", str(library),
        ]
        if os.environ.get("TTS_READER_SANITIZE"):
            command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
        result = subprocess.run(command, capture_output=True, text=True)
        (cls.workspace / "compile.log").write_text(
            shlex.join(command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.library = ctypes.CDLL(str(library))
        clip_source = cls.workspace / "reader-clip.c"
        clip_source.write_text((prefix + source + HARNESS_SUFFIX).replace(
            "#define CONFIG_KEYPAD 1", "#define CONFIG_KEYPAD 2"), encoding="utf-8")
        clip_library = cls.workspace / "reader-clip.so"
        clip_command = [str(clip_source) if item == str(harness) else
                        str(clip_library) if item == str(library) else item for item in command]
        result = subprocess.run(clip_command, capture_output=True, text=True)
        (cls.workspace / "compile-clip.log").write_text(
            shlex.join(clip_command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.clip_library = ctypes.CDLL(str(clip_library))
        cls.library.test_reset.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        cls.library.test_chunk.argtypes = [ctypes.c_long, ctypes.c_long,
                                         ctypes.c_void_p, ctypes.POINTER(ctypes.c_long)]
        cls.library.test_seek.argtypes = [ctypes.c_int, ctypes.c_long, ctypes.c_int,
                                        ctypes.POINTER(ctypes.c_long)]
        cls.library.test_short_reads.argtypes = [ctypes.c_size_t]
        cls.library.test_fail_after.argtypes = [ctypes.c_long]
        cls.library.test_error.argtypes = [ctypes.c_char_p]
        cls.library.test_audible.argtypes = [ctypes.c_size_t]
        cls.library.test_position.restype = ctypes.c_long
        cls.library.test_bookmark_offset.restype = ctypes.c_long
        cls.library.test_signature.restype = ctypes.c_uint32
        cls.library.test_restore.argtypes = [ctypes.c_long, ctypes.c_long,
                                            ctypes.c_int, ctypes.c_uint32]
        cls.library.test_property.restype = ctypes.c_char_p
        cls.library.test_largest_read.restype = ctypes.c_size_t
        for name in ("test_label", "test_speech", "test_text", "test_row"):
            getattr(cls.library, name).restype = ctypes.c_char_p


    def configure_extended_reader(self):
        lib = self.library
        lib.test_edit.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_bool]
        lib.test_search_preferences.argtypes = [ctypes.c_bool, ctypes.c_int, ctypes.c_int]
        lib.test_accepted_query.restype = ctypes.c_char_p
        lib.test_cursor64.argtypes = [ctypes.c_int64]
        lib.test_position64.restype = ctypes.c_int64
        lib.test_context_action.argtypes = []
        lib.test_context_action.restype = None
        lib.test_initial_snapshot.argtypes = [ctypes.c_int]
        lib.test_initial_snapshot.restype = ctypes.c_int64
        lib.test_match_range.argtypes = [ctypes.c_char_p, ctypes.c_int64, ctypes.c_int64,
                                       ctypes.c_bool, ctypes.c_bool,
                                       ctypes.POINTER(ctypes.c_int64)]
        lib.test_ordinal64.argtypes = [ctypes.c_uint64, ctypes.c_bool,
                                     ctypes.POINTER(ctypes.c_int64)]
        lib.test_percent64.argtypes = [ctypes.c_int64, ctypes.c_int64]
        lib.test_percent_target64.argtypes = [ctypes.c_int64, ctypes.c_uint]
        lib.test_percent_target64.restype = ctypes.c_int64
        lib.test_decimal64.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]

    def find_range(self, query, low=0, high=None, previous=False, match_case=False):
        self.configure_extended_reader()
        target = ctypes.c_int64(-1)
        status = self.library.test_match_range(query.encode("utf-8"), low,
            len(self.data) if high is None else high, previous, match_case,
            ctypes.byref(target))
        return status, target.value

    def reader_operation(self, row, text="", result=0, usb=False):
        self.configure_extended_reader()
        self.library.test_edit(text.encode("utf-8"), result, usb)
        self.library.test_menu_choice(row)
        self.library.test_menu_choice(-1)
        return self.library.test_menu()

    def test_search_real_polish_pairs_and_diacritic_distinction(self):
        for upper, lower in zip("ĄĆĘŁŃÓŚŹŻ", "ąćęłńóśźż"):
            with self.subTest(upper=upper):
                self.reset(("x" + lower + " z").encode())
                self.assertEqual(self.find_range(upper), (1, 1))
                self.assertEqual(self.find_range(upper, match_case=True), (0, -1))
        self.reset("żółć z Żółć".encode())
        self.assertEqual(self.find_range("ŻÓŁĆ"), (1, 0))
        self.assertEqual(self.find_range("zolc"), (0, -1))
        self.assertEqual(self.find_range("ZÓŁĆ"), (0, -1))
        self.assertEqual(self.find_range("Żółć", match_case=True), (1, len("żółć z ".encode())))

    def test_search_source_offsets_width_changes_and_overlap_ranges(self):
        self.reset("xȺxyⱥz".encode())
        # U+023A (two bytes) lowercases to U+2C65 (three bytes).
        self.assertEqual(self.find_range("ⱥ"), (1, 1))
        self.reset(b"ababa")
        self.assertEqual(self.find_range("aba", high=2, previous=True), (1, 0))
        self.assertEqual(self.find_range("aba", low=1), (1, 2))
        self.assertEqual(self.find_range("aba", high=1), (1, 0))
        self.assertEqual(self.find_range("aba", low=3), (0, -1))

    def test_search_cache_bom_invalid_and_bounds(self):
        self.reset(b"\xef\xbb\xbf" + b"x" * 763 + "żółć".encode() + b" tail")
        self.assertEqual(self.find_range("ŻÓŁĆ", low=3), (1, 766))
        self.assertEqual(self.find_range("\ufeff", low=3), (0, -1))
        self.reset(b"a\xef\xbb\xbfb")
        self.assertEqual(self.find_range("\ufeff"), (1, 1))
        self.reset(b"a" * 800 + b"\xf0\x9f")
        self.assertEqual(self.find_range("missing")[0], -2)
        self.reset(b"abc")
        self.assertEqual(self.find_range(""), (-2, -1))
        self.assertEqual(self.find_range("a" * 129), (-2, -1))

    def test_menu_search_commit_pause_repeat_wrap_and_query_rollback(self):
        self.reset(b"ababa")
        self.reader_operation(7, "aba")
        self.assertEqual(self.library.test_accepted_query(), b"aba")
        self.assertEqual(self.library.test_position64(), 0)
        self.assertEqual(self.library.test_state(), 1)
        self.assertIn(b"Text found", self.library.test_speech(self.library.test_speech_count() - 1))
        self.reader_operation(8)
        self.assertEqual(self.library.test_position64(), 2)
        self.reader_operation(8)  # default Stop
        self.assertEqual(self.library.test_position64(), 2)
        self.library.test_search_preferences(False, 2, 1)
        self.reader_operation(8)
        self.assertEqual(self.library.test_position64(), 0)
        self.assertIn(b"after wrapping", self.library.test_speech(self.library.test_speech_count() - 1))
        for text, result in [("not present", 0), ("edited", -1), ("", 0)]:
            self.reader_operation(7, text, result)
            self.assertEqual(self.library.test_accepted_query(), b"aba")
            self.assertEqual(self.library.test_position64(), 0)

    def test_menu_search_enqueue_failure_and_final_cancel_preserve_query(self):
        self.reset(b"one two")
        self.reader_operation(7, "one")
        self.library.test_cursor64(0)
        self.library.test_speech_failure()
        self.reader_operation(7, "two")
        self.assertEqual(self.library.test_position64(), 0)
        self.assertEqual(self.library.test_accepted_query(), b"one")
        self.reset(b"one two")
        self.library.test_scan_action(1, 1)
        self.reader_operation(7, "two")
        self.assertEqual(self.library.test_pending(), 1)
        self.assertEqual(self.library.test_position64(), 0)
        self.assertEqual(self.library.test_accepted_query(), b"")

    def test_menu_invalid_text_announces_exact_label_and_preserves_position(self):
        for row, text, prompt in ((7, "missing", b"Find"),
                                  (10, "2", b"Go to line")):
            with self.subTest(row=row):
                self.reset(b"a" * 1600 + b"\xff\nlast")
                self.configure_extended_reader()
                self.library.test_cursor64(4)
                self.assertFalse(self.reader_operation(row, text))
                self.assertEqual(self.library.test_speech_count(), 2)
                self.assertEqual([self.library.test_speech(index) for index in range(2)],
                                 [prompt, b"Invalid text"])
                self.assertEqual(self.library.test_position64(), 4)
                self.assertEqual(self.library.test_accepted_query(), b"")

    def test_menu_io_failure_announces_exact_label_and_preserves_position(self):
        for row, text, prompt in ((7, "missing", b"Find"),
                                  (10, "2", b"Go to line")):
            with self.subTest(row=row):
                self.reset(b"a" * 1600 + b"\nlast")
                self.configure_extended_reader()
                self.library.test_cursor64(4)
                self.library.test_fail_after(768)
                self.assertFalse(self.reader_operation(row, text))
                self.assertEqual(self.library.test_speech_count(), 2)
                self.assertEqual([self.library.test_speech(index) for index in range(2)],
                                 [prompt, b"Text operation failed; position unchanged"])
                self.assertEqual(self.library.test_position64(), 4)
                self.assertEqual(self.library.test_accepted_query(), b"")

    def test_menu_usb_edit_confirmation_and_preferences_do_not_commit(self):
        self.reset(b"abc abc")
        self.assertTrue(self.reader_operation(7, "abc", -1, True))
        self.assertEqual(self.library.test_accepted_query(), b"")
        self.reader_operation(7, "abc")
        self.library.test_cursor64(4)
        self.library.test_search_preferences(False, 1, 2)  # Ask / YESNO_USB
        self.assertTrue(self.reader_operation(8))
        self.assertEqual(self.library.test_position64(), 4)
        self.library.test_menu_script_reset()
        self.library.test_menu_choice(13)
        self.library.test_menu_choice(-10)
        self.assertTrue(self.library.test_menu())
        self.assertEqual(self.library.test_preference_writes(), 0)

    def test_content_ordinals_all_separators_and_no_phantom_final_line(self):
        self.configure_extended_reader()
        for separator in ["\r\n", "\r", "\n", "\x85", "\u2028", "\u2029"]:
            data = ("a" + separator + separator + "b" + separator).encode()
            self.reset(data)
            self.library.test_page_lines(1)
            starts = [0, len(("a" + separator).encode()),
                      len(("a" + separator + separator).encode())]
            for page in (False, True):
                for ordinal, expected in enumerate(starts, 1):
                    target = ctypes.c_int64()
                    self.assertEqual(self.library.test_ordinal64(ordinal, page, ctypes.byref(target)), 1)
                    self.assertEqual(target.value, expected)
                self.assertEqual(self.library.test_ordinal64(4, page, ctypes.byref(target)), 0)
        for data in [b"", b"\xef\xbb\xbf"]:
            self.reset(data)
            target = ctypes.c_int64()
            self.assertEqual(self.library.test_ordinal64(1, False, ctypes.byref(target)), 0)

    def test_typed_destinations_invalid_input_percent_alignment_and_pause(self):
        self.reset("a\r\nżb".encode())
        self.reader_operation(10, "2")
        self.assertEqual(self.library.test_position64(), 3)
        for text in ["0", "-1", "+2", "2x", "", "18446744073709551616", "9"]:
            self.reader_operation(10, text)
            self.assertEqual(self.library.test_position64(), 3)
        self.reader_operation(12, "40")  # byte 2 is LF in CRLF; align before CR.
        self.assertEqual(self.library.test_position64(), 1)
        self.reader_operation(12, "70")  # byte 4 is a UTF-8 continuation.
        self.assertEqual(self.library.test_position64(), 3)
        self.reader_operation(12, "100")
        self.assertEqual(self.library.test_position64(), len(self.data))
        self.assertEqual(self.library.test_state(), 2)
        self.reader_operation(12, "0")
        self.assertEqual(self.library.test_position64(), 0)
        self.assertEqual(self.library.test_state(), 1)

    def test_checked_large_percentages_and_numeric_overflow(self):
        self.configure_extended_reader()
        size = (1 << (self.library.test_offset_bits() - 1)) - 1
        for percent in range(101):
            target = self.library.test_percent_target64(size, percent)
            self.assertEqual(target, size * percent // 100)
            self.assertEqual(self.library.test_percent64(target, size), target * 100 // size)
        value = ctypes.c_uint64()
        self.assertTrue(self.library.test_decimal64(b"18446744073709551615", ctypes.byref(value)))
        self.assertEqual(value.value, (1 << 64) - 1)
        self.assertFalse(self.library.test_decimal64(b"18446744073709551616", ctypes.byref(value)))

    def test_reader_job_is_bounded_and_rejects_nested_owner(self):
        self.reset(b"abc")
        self.assertLessEqual(self.library.test_job_size(), 2304)
        self.assertTrue(self.library.test_nested_owner())
        self.assertEqual(self.library.test_closed(), 0)


    def test_initial_busy_bom_context_failure_keeps_initialized_origin(self):
        self.configure_extended_reader()
        for failure in ("no_match", "cancel_edit", "invalid_query", "enqueue", "final_cancel"):
            with self.subTest(failure=failure):
                self.reset(b"\xef\xbb\xbfone two")
                self.library.test_initial_speech_busy()
                query = "missing" if failure == "no_match" else (
                    "" if failure == "invalid_query" else "two")
                self.library.test_edit(query.encode("utf-8"),
                    -1 if failure == "cancel_edit" else 0, False)
                self.library.test_menu_choice(7)
                self.library.test_menu_choice(-1)
                self.library.test_context_action()  # actual fixture ACTION_STD_CONTEXT
                self.library.test_action(1)   # then ACTION_STD_CANCEL
                if failure == "enqueue":
                    self.library.test_speech_failure()
                elif failure == "final_cancel":
                    self.library.test_scan_action(1, 1)
                self.assertEqual(self.library.test_run(), 0)
                # Captured inside kbd_input_ex, before search's reader_prepare.
                self.assertEqual([self.library.test_initial_snapshot(i) for i in range(3)],
                                 [1, 3, 3])
                # Captured at document close while the job still owns this reader.
                self.assertEqual([self.library.test_initial_snapshot(i) for i in range(3, 6)],
                                 [1, 3, 3])
                self.assertEqual(self.library.test_accepted_query(), b"")
                self.assertEqual(self.library.test_tracked_count(), 0)
                self.assertEqual(self.library.test_closed(), 1)
                self.assertEqual(self.library.test_theme_undos(), 1)


    def reset(self, data):
        self.data = data
        self.input = ctypes.create_string_buffer(data)
        self.library.test_reset(self.input, len(data))

    def chunk(self, start=0, size=None):
        output = ctypes.create_string_buffer(769)
        following = ctypes.c_long(-1)
        result = self.library.test_chunk(start, len(self.data) if size is None else size,
                                         output, ctypes.byref(following))
        return result, output.raw[:max(0, result)], following.value

    def chunks(self):
        position = 0
        pieces = []
        while position < len(self.data):
            length, text, following = self.chunk(position)
            self.assertGreaterEqual(length, 0)
            self.assertLessEqual(length, 768)
            self.assertGreater(following, position)
            text.decode("utf-8", errors="strict")
            pieces.append(text)
            position = following
        return pieces

    def seek(self, unit, cursor, forward, expected):
        following = ctypes.c_long(-1)
        self.assertEqual(self.library.test_seek(unit, cursor, forward,
                                                ctypes.byref(following)), 0)
        self.assertEqual(following.value, expected)

    def drain(self):
        self.library.test_audio(0, 0)

    def test_empty_sound_only_preserves_all_reader_state_io_and_playback(self):
        for state in range(4):
            for cached in (False, True):
                with self.subTest(state=state, cached=cached):
                    self.reset(b"one two three four")
                    self.library.test_reader_touch_setup()
                    self.library.test_step()
                    self.library.test_audible(4)
                    self.library.test_reader_state(state, cached)
                    self.assertEqual(self.library.test_reader_touch_preserves(-1, True), 1)
                    for _ in range(100):
                        self.assertEqual(self.library.test_reader_touch_preserves(-1, False), 1)
                    self.assertEqual(self.library.test_position(), 0)
                    self.assertEqual(self.library.test_stops(), 0)
                    self.assertEqual(self.library.test_speech_count(), 1)

    def test_empty_sound_only_preserves_paused_pcm_and_last_heard_position(self):
        self.reset(b"one two three four")
        self.library.test_reader_touch_setup()
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_toggle()
        self.assertEqual(self.library.test_paused(), 1)
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_reader_touch_preserves(-1, True), 1)
        self.assertEqual(self.library.test_paused(), 1)
        self.assertEqual(self.library.test_pcm(), 4096)

    def test_empty_speech_modes_resume_from_last_heard_without_jitter_repetition(self):
        for mode in (1, 2):
            with self.subTest(mode=mode):
                self.reset(b"one two three four")
                self.library.test_reader_touch_setup()
                self.library.test_reader_empty_mode(mode)
                self.library.test_step()
                self.library.test_audible(4)
                self.library.test_reader_touch(-1, True)
                self.assertEqual(self.library.test_stops(), 1)
                self.assertEqual(self.library.test_position(), 4)
                self.assertEqual(self.library.test_speech(1), b"No item")
                for _ in range(100):
                    self.assertEqual(self.library.test_reader_touch_preserves(-1, False), 1)
                self.drain()
                self.library.test_step()
                self.assertEqual(self.library.test_speech(2), b"two three four")

    def test_occupied_touch_keeps_speaking_in_every_empty_mode(self):
        for mode in range(3):
            with self.subTest(mode=mode):
                self.reset(b"one two three four")
                self.library.test_reader_touch_setup()
                self.library.test_reader_empty_mode(mode)
                self.library.test_step()
                self.library.test_reader_touch(0, True)
                self.assertEqual(self.library.test_speech(1), b"example.txt")
                self.assertEqual(self.library.test_stops(), 1)

    def test_empty_and_bom_only(self):
        for data in (b"", b"\xef\xbb\xbf"):
            with self.subTest(data=data):
                self.reset(data)
                self.assertEqual(self.chunk(), (0, b"", len(data)))
                self.library.test_step()
                self.assertEqual(self.library.test_state(), 2)
                self.assertEqual(self.library.test_position(), len(data))
                self.assertEqual(self.library.test_percent(), 100)
                self.assertEqual(self.library.test_tracked_count(), 0)
                self.assertEqual(self.library.test_speech(0), b"End of text")

    def test_utf8_and_optional_bom(self):
        text = "Za\u017c\u00f3\u0142\u0107 g\u0119\u015bl\u0105 ja\u017a\u0144. \u03a9 \u4e2d\U0001f600\n".encode()
        for prefix in (b"", b"\xef\xbb\xbf"):
            self.reset(prefix + text * 100)
            self.assertEqual(b"".join(self.chunks()), text * 100)
            self.assertLessEqual(self.library.test_largest_read(), 768)

    def test_multibyte_splits_at_every_tail_position(self):
        for character in ("\u0105", "\u4e2d", "\U0001f600"):
            for prefix_length in range(762, 770):
                with self.subTest(character=character, prefix_length=prefix_length):
                    data = b"x" * prefix_length + character.encode() + b"y" * 1000
                    self.reset(data)
                    self.assertEqual(b"".join(self.chunks()), data)
                    self.seek(0, prefix_length, 1, prefix_length + len(character.encode()))
                    self.seek(0, prefix_length + len(character.encode()), 0, prefix_length)

    def test_whitespace_boundaries_and_long_words(self):
        for space in (" ", "\t", "\r\n", "\u2003", "\u2028", "\u00a0"):
            data = b"a" * 500 + space.encode() + b"b" * 900
            self.reset(data)
            length, text, following = self.chunk()
            self.assertEqual(text, b"a" * 500 + space.encode())
            self.assertEqual(length, following)
            self.assertEqual(b"".join(self.chunks()), data)
        self.reset(b"x" * 5000)
        self.assertEqual(self.chunk()[0], 768)
        self.assertEqual(b"".join(self.chunks()), self.data)

    def test_invalid_utf8_utf16_and_binary(self):
        invalid = [b"\xff\xfeA\0", b"\xfe\xff\0A", b"A\0B\0", b"\0A\0B",
                   b"\x80", b"\xc0\xaf", b"\xe0\x80\x80", b"\xed\xa0\x80",
                   b"\xf0\x80\x80\x80", b"\xf4\x90\x80\x80", b"\xf5\x80\x80\x80",
                   b"\xe2\x82", b"\xef\xbb", b"\xf0\x9f\x98", b"text\0tail",
                   b"text\x01", b"\x1b[31m", b"\x7f", b"\xc2\x80", b"\xef\xbf\xbe",
                   b"\xef\xb7\x90", b"\xf4\x8f\xbf\xbf"]
        for data in invalid:
            with self.subTest(data=data):
                self.reset(data)
                self.assertEqual(self.chunk()[0], -2)
                self.assertEqual(self.library.test_load(), 0)
                self.assertEqual(self.library.test_state(), 3)
                self.assertEqual(self.library.test_speech(0), b"Invalid text")

    def test_invalid_sequence_crossing_chunk_boundary(self):
        for bad in (b"\xf0\x9f", b"\xe2\x28\xa1", b"\xf4\x90\x80\x80"):
            self.reset(b"a" * 767 + bad)
            length, text, following = self.chunk()
            self.assertEqual((length, text, following), (767, b"a" * 767, 767))
            self.assertEqual(self.chunk(following)[0], -2)

    def test_random_valid_streams_reassemble_exactly(self):
        generator = random.Random(83127)
        alphabet = list("Ab z\t\r\n") + ["\u0105", "\u03a9", "\u4e2d", "\U0001f600", "\u2003", "\u2028"]
        for iteration in range(60):
            text = "".join(generator.choices(alphabet, k=generator.randrange(1, 12000)))
            self.reset(text.encode())
            with self.subTest(iteration=iteration):
                self.assertEqual(b"".join(self.chunks()), self.data)

    def test_short_reads_seek_errors_and_truncation(self):
        self.reset("\u0105\u4e2d\U0001f600 abc\n".encode() * 100)
        self.library.test_short_reads(1)
        self.assertEqual(b"".join(self.chunks()), self.data)
        self.seek(0, 2, 0, 0)
        self.library.test_fail_after(2)
        self.assertEqual(self.chunk()[0], -1)
        self.library.test_seek_failure()
        self.assertEqual(self.chunk()[0], -1)
        self.reset(b"abc")
        self.assertEqual(self.chunk(size=100)[0], -1)
        self.assertEqual(self.chunk(start=-1)[0], -1)
        self.assertEqual(self.chunk(start=4)[0], -1)

    def test_character_codepoints_atomic_crlf_bom_and_unlimited_backward(self):
        text = "\u0105\u4e2d\U0001f600e\u0301\r\n" * 80
        self.reset(b"\xef\xbb\xbf" + text.encode())
        positions = [3]
        for character in re.findall(r'\r\n|.', text, flags=re.DOTALL):
            positions.append(positions[-1] + len(character.encode()))
        for start, end in zip(positions, positions[1:]):
            self.seek(0, start, 1, end)
            self.seek(0, end, 0, start)
        self.seek(0, 3, 0, 3)
        self.seek(0, len(self.data), 1, len(self.data))

    def test_word_boundaries_whitespace_and_punctuation(self):
        text = "  one,two\t\u017c\u00f3\u0142\u0107\u2003\u4e2d\U0001f600 end\r\n"
        self.reset(text.encode())
        starts = [len(text[:match.start()].encode()) for match in re.finditer(r'\S+', text)]
        for start, end in zip([0] + starts, starts + [len(self.data)]):
            self.seek(1, start, 1, end)
        for start, end in zip(starts + [len(self.data)], [0] + starts):
            self.seek(1, start, 0, end)
        self.seek(1, starts[1] + 2, 0, starts[1])

    def test_character_feedback_uses_native_mode_including_whitespace(self):
        for character in "a \t.,!?\u2003\u0105\u4e2d\U0001f600":
            with self.subTest(character=character):
                self.reset(b"\xef\xbb\xbf" + character.encode() + b"x")
                self.library.test_unit(0)
                self.library.test_navigate(0)
                self.assertEqual(self.library.test_state(), 1)
                self.assertEqual(self.library.test_position(), 3)
                self.assertEqual(self.library.test_character_count(), 1)
                self.assertEqual(self.library.test_character(), ord(character))
                self.assertEqual(self.library.test_tracked_count(), 0)

    def test_character_newline_feedback_uses_structural_label(self):
        for delimiter in ("\r", "\n", "\r\n", "\u0085", "\u2028", "\u2029"):
            with self.subTest(delimiter=delimiter):
                self.reset(b"\xef\xbb\xbfa" + delimiter.encode() + b"b")
                self.library.test_unit(0)
                self.library.test_navigate(1)
                self.assertEqual(self.library.test_position(), 4)
                self.assertEqual(self.library.test_state(), 1)
                self.assertEqual(self.library.test_speech(0), b"New line")
                self.assertEqual(self.library.test_character_count(), 0)
                self.library.test_navigate(1)
                self.assertEqual(self.library.test_position(), 4 + len(delimiter.encode()))
                self.assertEqual(self.library.test_character(), ord("b"))
                self.library.test_navigate(0)
                self.assertEqual(self.library.test_position(), 4)
                self.assertEqual(self.library.test_speech(2), b"New line")
                self.assertEqual(self.library.test_tracked_count(), 0)

    def test_character_crlf_across_cache_boundary_and_from_mid_delimiter(self):
        for prefix_length in range(763, 770):
            self.reset(b"x" * prefix_length + b"\r\nz")
            self.seek(0, prefix_length, 1, prefix_length + 2)
            self.seek(0, prefix_length + 2, 0, prefix_length)
            self.seek(0, prefix_length + 1, 0, prefix_length)
            self.seek(0, prefix_length + 1, 1, prefix_length + 2)
        self.reset(b"\xef\xbb\xbf\r\n")
        self.seek(0, 3, 1, 5)
        self.seek(0, 5, 0, 3)
        self.seek(0, 3, 0, 3)
        self.seek(0, 5, 1, 5)

    def test_unmapped_button_release_does_not_abort_scan(self):
        self.reset(b"x" * 10000 + b" word")
        self.library.test_scan_action(-1, 1)
        self.seek(1, 0, 1, 10001)
        self.assertEqual(self.library.test_pending(), 0)

    def test_preview_is_bounded_first_line_and_navigation_stays_paused(self):
        for unit in (2, 3, 4):
            self.reset(b"first line\nsecond line\n\nnext paragraph")
            self.library.test_unit(unit)
            self.library.test_navigate(0)
            self.assertEqual(self.library.test_state(), 1)
            self.assertEqual(self.library.test_speech(0), b"first line")
            self.assertEqual(self.library.test_tracked_count(), 0)
        self.reset(b"x" * 10000)
        self.library.test_navigate(0)
        self.assertEqual(len(self.library.test_speech(0)), 768)

    def test_logical_lines_crlf_empty_and_unicode_separators(self):
        text = "one\r\n\r\ntwo\rthree\nfour\u0085five\u2028six\u2029last"
        self.reset(text.encode())
        boundaries = [0] + [len(text[:match.end()].encode())
                             for match in re.finditer(r'\r\n|[\r\n\u0085\u2028\u2029]', text)]
        for start, end in zip(boundaries, boundaries[1:] + [len(self.data)]):
            self.seek(2, start, 1, end)
            self.seek(2, end, 0, start)
        self.seek(2, 4, 0, 0)
        self.seek(2, 4, 1, 5)
        self.seek(2, len(self.data) - 1, 0, boundaries[-1])

    def test_paragraphs_blank_lines_indentation_and_eof(self):
        text = "\r\n  first\r\nsecond\r\n \t\r\n\u2003\n  third\nfourth\n\nlast"
        self.reset(text.encode())
        starts = [len(text[:text.index(part)].encode()) for part in ("  first", "  third", "last")]
        for start, end in zip([0] + starts, starts + [len(self.data)]):
            self.seek(3, start, 1, end)
        for start, end in zip(starts + [len(self.data)], [0] + starts):
            self.seek(3, start, 0, end)
        self.seek(3, text.index("second") + 2, 0, starts[0])
        self.seek(3, starts[1] + 4, 0, starts[1])

    def test_pages_are_anchored_configurable_logical_lines(self):
        lines = [f"line {index}\r\n".encode() for index in range(207)]
        self.reset(b"\xef\xbb\xbf" + b"".join(lines))
        for page_lines in (1, 2, 20, 100):
            self.library.test_page_lines(page_lines)
            boundaries = [3 + sum(map(len, lines[:index]))
                          for index in range(0, len(lines), page_lines)]
            for start, end in zip(boundaries, boundaries[1:] + [len(self.data)]):
                self.seek(4, start, 1, end)
                self.seek(4, end, 0, start)
                if end - start > 2:
                    self.seek(4, start + 2, 0, start)
                    self.seek(4, start + 2, 1, end)

    def test_random_navigation_matches_independent_boundaries(self):
        generator = random.Random(83128)
        alphabet = ["a", " ", "\u0105", "\U0001f600", "\r\n", "\n", "\u2003", "\u2028"]
        for iteration in range(20):
            text = "".join(generator.choices(alphabet, k=70))
            self.reset(text.encode())
            offsets = [len(text[:index].encode()) for index in range(len(text) + 1)]
            character_starts = [offset for index, offset in enumerate(offsets)
                                if not (index > 0 and text[index - 1:index + 1] == "\r\n")]
            line_starts = [0] + [match.end() for match in re.finditer(r'\r\n|[\r\n\u2028]', text)]
            paragraph_starts = []
            was_blank = True
            for start, end in zip(line_starts, line_starts[1:] + [len(text)]):
                blank = not text[start:end].strip()
                if was_blank and not blank:
                    paragraph_starts.append(offsets[start])
                was_blank = blank
            word_starts = [offsets[match.start()] for match in re.finditer(r'\S+', text)]
            self.library.test_page_lines(3)
            boundaries = [character_starts, word_starts, [offsets[start] for start in line_starts],
                          paragraph_starts, [offsets[start] for start in line_starts[::3]]]
            for unit, starts in enumerate(boundaries):
                stops = sorted(set([0, len(self.data)] + starts))
                for cursor in offsets:
                    with self.subTest(iteration=iteration, unit=unit, cursor=cursor):
                        previous = max((start for start in stops if start < cursor), default=0)
                        following = min((start for start in stops if start > cursor), default=len(self.data))
                        self.seek(unit, cursor, 0, previous)
                        self.seek(unit, cursor, 1, following)

    def test_long_scans_yield_and_cancel_without_committing_cursor(self):
        self.reset(b"x" * 2000000)
        for unit in (1, 2, 3, 4):
            for forward, cursor in ((1, 0), (0, len(self.data))):
                self.library.test_scan_action(1, 1)
                target = ctypes.c_long(-1)
                self.assertEqual(self.library.test_seek(unit, cursor, forward,
                                                        ctypes.byref(target)), -3)
                self.assertEqual(self.library.test_position(), cursor)
                self.assertEqual(self.library.test_pending(), 1)
                self.assertGreater(self.library.test_yields(), 0)
        self.assertLessEqual(self.library.test_largest_read(), 768)

    def test_long_scans_complete_without_fixed_history_or_line_limit(self):
        self.reset(b"x" * 100000 + b"\n\nend")
        self.seek(1, 0, 1, 100002)
        self.seek(1, 100002, 0, 0)
        self.seek(2, 0, 1, 100001)
        self.seek(3, 0, 1, 100002)
        self.seek(3, 100002, 0, 0)
        self.assertGreater(self.library.test_yields(), 100)

    def test_navigation_reports_invalid_text_and_io_failure(self):
        for unit in (1, 2, 3, 4):
            self.reset(b"a" * 1000 + b"\xff" + b"tail")
            target = ctypes.c_long(-1)
            self.assertEqual(self.library.test_seek(unit, 0, 1, ctypes.byref(target)), -2)
            self.assertEqual(self.library.test_seek(unit, len(self.data), 0,
                                                    ctypes.byref(target)), -2)
        self.reset(b"a" * 3000)
        self.library.test_load()
        self.library.test_fail_after(768)
        self.library.test_navigate(1)
        self.assertEqual(self.library.test_state(), 3)
        self.assertIn(b"Failed reading", self.library.test_label())

    def test_synthesis_and_final_pcm_tail_gate_advancement(self):
        self.reset(b"a" * 768 + b"b" * 20)
        self.library.test_step()
        self.assertEqual(self.library.test_speech(0), b"a" * 768)
        for synthesizing, channel in ((1, 0), (0, 1), (0, 2)):
            self.library.test_audio(synthesizing, channel)
            self.library.test_step()
            self.assertEqual(self.library.test_position(), 0)
            self.assertEqual(self.library.test_speech_count(), 1)
        self.drain()
        self.library.test_step()
        self.assertEqual(self.library.test_position(), 768)
        self.assertEqual(self.library.test_speech(1), b"b" * 20)
        self.library.test_audio(0, 1)
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 0)
        self.drain()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 2)
        self.assertEqual(self.library.test_percent(), 100)
        self.assertEqual(self.library.test_stops(), 0)
        self.assertEqual(self.library.test_speech(2), b"End of text")
        self.drain()
        for unused in range(10):
            self.library.test_step()
        self.assertEqual(self.library.test_speech_count(), 3)

    def test_audible_cursor_advances_while_synthesis_busy_and_updates_screen(self):
        self.reset(b"\xef\xbb\xbfone two three")
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_step()
        self.assertEqual(self.library.test_position(), 7)
        self.assertEqual(self.library.test_text(), b"two three")
        self.library.test_draw()
        self.assertIn(b"7 / 16", self.library.test_row(2))
        self.assertEqual(self.library.test_row(3), b"two three")
        self.library.test_audible(0)
        self.library.test_step()
        self.assertEqual(self.library.test_position(), 7)

    def test_pause_resume_preserves_queued_pcm_without_speech_or_resynthesis(self):
        self.reset(b"one two three " * 100)
        self.library.test_step()
        self.library.test_consume(100)
        self.library.test_audible(4)
        self.library.test_toggle()
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_paused(), 1)
        self.library.test_consume(200)
        self.library.test_audible(8)
        for unused in range(10):
            self.library.test_step()
        self.assertEqual(self.library.test_pcm(), 3996)
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_stops(), 0)
        self.assertEqual(self.library.test_speech_count(), 1)
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 0)
        self.assertEqual(self.library.test_paused(), 0)
        self.assertEqual(self.library.test_pcm(), 3996)
        self.assertEqual(self.library.test_tracked_count(), 1)
        self.assertEqual(self.library.test_speech_count(), 1)
        self.assertEqual(self.library.test_pause_calls(), 2)
        self.library.test_consume(200)
        self.library.test_audible(8)
        self.library.test_step()
        self.assertEqual(self.library.test_position(), 8)

    def test_pause_at_drained_boundary_does_not_advance_until_resumed(self):
        self.reset(b"x" * 800)
        self.library.test_step()
        self.drain()
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_tracked_count(), 1)
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_tracked_count(), 2)
        self.assertEqual(self.library.test_position(), 768)

    def test_repeated_notice_resumes_the_unread_part_of_a_chunk(self):
        data = b"one two three " * 80
        self.reset(data)
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_step()
        self.library.test_external_notice()
        self.library.test_external_notice()
        self.drain()
        self.library.test_step()
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_tracked_count(), 2)
        self.assertTrue(self.library.test_speech(
            self.library.test_speech_count() - 1).startswith(data[4:24]))
        self.library.test_audible(8)
        self.library.test_step()
        self.assertEqual(self.library.test_position(), 12)

    def test_notice_does_not_resume_a_paused_reader_or_skip_on_play(self):
        data = b"one two three " * 80
        self.reset(data)
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_toggle()
        self.library.test_external_notice()
        self.drain()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_tracked_count(), 1)
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 0)
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_tracked_count(), 2)
        self.assertTrue(self.library.test_speech(
            self.library.test_speech_count() - 1).startswith(data[4:24]))

    def test_navigation_after_a_drained_notice_uses_the_audible_cursor(self):
        self.reset(b"one two three " * 80)
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_step()
        self.library.test_external_notice()
        self.drain()
        self.library.test_navigate(1)
        self.assertEqual(self.library.test_position(), 8)
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_speech(
            self.library.test_speech_count() - 1), b"three")

    def test_navigation_interrupts_at_audible_cursor_and_play_restarts_there(self):
        self.reset(b"one two three four")
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_navigate(1)
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_position(), 8)
        self.assertEqual(self.library.test_speech(1), b"three")
        self.assertEqual(self.library.test_stops(), 1)
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_speech(2), b"three four")
        self.assertEqual(self.library.test_tracked_count(), 2)
        self.assertEqual(self.library.test_position(), 8)

    def test_granularity_persists_wraps_and_does_not_rewind(self):
        self.reset(b"one two three")
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_change_unit(1)
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_get_unit(), 2)
        self.assertEqual(self.library.test_speech(1), b"Line")
        self.library.test_unit(4)
        self.library.test_change_unit(1)
        self.assertEqual(self.library.test_get_unit(), 0)
        self.library.test_change_unit(0)
        self.assertEqual(self.library.test_get_unit(), 4)
        self.assertEqual(self.library.test_saves(), 3)
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_speech(4), b"two three")

    def test_eof_back_navigation_and_restart_skip_bom(self):
        self.reset(b"\xef\xbb\xbfone two")
        self.library.test_navigate(1)
        self.library.test_navigate(1)
        self.assertEqual(self.library.test_state(), 2)
        self.assertEqual(self.library.test_position(), len(self.data))
        self.library.test_navigate(0)
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_position(), 7)
        self.library.test_navigate(1)
        self.library.test_change_unit(1)
        self.assertEqual(self.library.test_state(), 2)
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_position(), 3)
        self.assertEqual(self.library.test_speech(self.library.test_speech_count() - 1), b"one two")

    def test_sync_and_async_synthesis_errors(self):
        self.reset(b"hello")
        self.library.test_speech_failure()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 3)
        self.assertEqual(self.library.test_label(), b"Speech error")
        self.reset(b"hello")
        self.library.test_step()
        self.library.test_error(b"Synthesis failed")
        self.drain()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 3)
        self.assertEqual(self.library.test_label(), b"Speech error")
        self.assertEqual(self.library.test_speech(1), b"Speech error")

    def test_full_event_loop_silent_start_toggle_and_cleanup(self):
        self.reset(b"one two")
        for action in (2, 2, 11, 1):
            self.library.test_action(action)
        self.assertEqual(self.library.test_run(), 0)
        self.assertEqual(self.library.test_tracked_count(), 1)
        self.assertEqual(self.library.test_speech_count(), 1)
        self.assertEqual(self.library.test_speech(0), b"one two")
        self.assertEqual(self.library.test_pause_calls(), 2)
        self.assertEqual(self.library.test_closed(), 1)
        self.assertEqual(self.library.test_theme_undos(), 1)

    def test_full_event_loop_settings_and_navigation_actions(self):
        self.reset(b"one two three\nnext\n")
        for action in (7, 9, 8, 10, 5, 3, 6, 4, 2, 1):
            self.library.test_action(action)
        self.library.test_run()
        self.assertEqual(self.library.test_saves(), 4)
        self.assertEqual(self.library.test_get_unit(), 1)
        self.assertEqual(self.library.test_tracked_count(), 2)
        self.assertEqual(self.library.test_speech(9), self.data)

    def test_cancel_and_usb_during_scan_are_not_lost(self):
        for action, expected_usb in ((1, 0), (99, 1)):
            self.reset(b"x" * 1000000)
            self.library.test_action(5)
            self.library.test_scan_action(action, 1)
            self.assertEqual(self.library.test_run(), expected_usb)
            self.assertEqual(self.library.test_closed(), 1)
            self.assertEqual(self.library.test_theme_undos(), 1)
            self.assertEqual(self.library.test_yields(), 1)
            self.assertEqual(self.library.test_tracked_count(), 1)

    def test_open_size_and_availability_errors_cleanup_once(self):
        for failure, closes in (("test_open_failure", 0), ("test_size_failure", 1),
                                ("test_unavailable", 0)):
            self.reset(b"hello")
            getattr(self.library, failure)()
            self.library.test_run()
            self.assertEqual(self.library.test_closed(), closes)
            self.assertEqual(self.library.test_theme_undos(), 1)
            self.assertEqual(self.library.test_tracked_count(), 0)
            self.assertEqual(self.library.test_speech_count(), 1)

    def test_target_independent_overlay_and_settings_context(self):
        for button, action in ((1, 7), (1 | 8, 8), (2, 9), (2 | 8, 10), (4 | 16, 2)):
            self.assertEqual(self.library.test_mapping(0, button), action)
        self.assertEqual(self.library.test_mapping(0, 0), 20)
        self.assertEqual(self.library.test_mapping(ctypes.c_int(0x80000000), 1),
                         ctypes.c_int(0x80000000 | 20).value)
        clip = (ROOT / "apps/keymaps/keymap-clip.c").read_text()
        settings = clip.split("button_context_settings[]", 1)[1].split("};", 1)[0]
        for action, button in (("ACTION_SETTINGS_INC", "BUTTON_UP"),
                               ("ACTION_SETTINGS_DEC", "BUTTON_DOWN"),
                               ("ACTION_STD_PREV", "BUTTON_LEFT"),
                               ("ACTION_STD_NEXT", "BUTTON_RIGHT"),
                               ("ACTION_STD_CANCEL", "BUTTON_POWER")):
            self.assertRegex(settings, rf'\{{\s*{action},\s*{button},')
        self.assertRegex(clip, r'ACTION_STD_OK,\s*BUTTON_SELECT\|BUTTON_REL')
        for target in ("xduoox3", "shanlingq1"):
            source = (ROOT / f"apps/keymaps/keymap-{target}.c").read_text()
            for action, button in (("ACTION_STD_PREV", "BUTTON_PREV"),
                                   ("ACTION_STD_NEXT", "BUTTON_NEXT"),
                                   ("ACTION_STD_OK", "BUTTON_PLAY")):
                self.assertRegex(source, rf'\{{\s*{action},\s*{button}')
            self.assertIn("ACTION_STD_CANCEL", source)

    def test_menu_saves_audible_not_enqueued_cursor(self):
        self.reset(b"one two three " * 100)
        self.library.test_step()
        self.library.test_audible(8)
        for choice in (1, 0, -2, -2):
            self.library.test_menu_choice(choice)
        self.assertEqual(self.library.test_menu(), 0)
        self.assertEqual(self.library.test_bookmark_writes(), 1)
        self.assertEqual(self.library.test_bookmark_offset(), 8)
        self.assertEqual(self.library.test_position(), 8)
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_release_waits(), 2)
        self.assertEqual(self.library.test_speech(self.library.test_speech_count() - 1),
                         b"Bookmark saved")

    def test_drained_chunk_commits_before_bookmark_but_pcm_tail_does_not(self):
        for channel, expected in ((0, 13), (1, 8)):
            self.reset(b"one two three")
            self.library.test_step()
            self.library.test_audible(8)
            self.library.test_audio(0, channel)
            for choice in (1, 0, -2, -2):
                self.library.test_menu_choice(choice)
            self.library.test_menu()
            self.assertEqual(self.library.test_bookmark_offset(), expected)

    def test_partial_bookmark_save_reports_local_success_without_rewinding(self):
        self.reset(b"one two three " * 100)
        self.library.test_step()
        self.library.test_audible(8)
        self.library.test_bookmark_local_only()
        for choice in (1, 0, -2, -2):
            self.library.test_menu_choice(choice)
        self.assertEqual(self.library.test_menu(), 0)
        self.assertEqual(self.library.test_bookmark_writes(), 1)
        self.assertEqual(self.library.test_bookmark_offset(), 8)
        self.assertEqual(self.library.test_position(), 8)
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_speech(self.library.test_speech_count() - 1),
                         b"Bookmark saved, but recent bookmarks could not be updated")

    def test_bookmark_signature_failure_does_not_attempt_partial_or_full_save(self):
        self.reset(b"one two three " * 100)
        self.library.test_step()
        self.library.test_audible(8)
        self.library.test_bookmark_local_only()
        self.library.test_seek_failure()
        for choice in (1, 0, -2, -2):
            self.library.test_menu_choice(choice)
        self.assertEqual(self.library.test_menu(), 0)
        self.assertEqual(self.library.test_bookmark_writes(), 0)
        self.assertEqual(self.library.test_position(), 8)
        self.assertEqual(self.library.test_speech(self.library.test_speech_count() - 1),
                         b"Bookmark failed")

    def test_menu_cancel_preserves_finished_restart(self):
        self.reset(b"one two three")
        self.library.test_step()
        self.drain()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 2)
        self.library.test_menu_choice(-2)
        self.library.test_menu()
        self.assertEqual(self.library.test_state(), 2)
        self.library.test_toggle()
        self.assertEqual(self.library.test_position(), 0)
        self.assertEqual(self.library.test_state(), 0)

    def test_disabling_speech_does_not_fail_or_commit_cancelled_chunk(self):
        self.reset(b"one two three")
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_unavailable()
        self.library.test_audio(0, 0)
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_position(), 4)
        self.library.test_toggle()
        self.assertEqual(self.library.test_state(), 1)
        for choice in (2, -2):
            self.library.test_menu_choice(choice)
        self.library.test_menu()
        self.assertIn(b"Position", self.library.test_property(3))
        self.library.test_available()
        self.library.test_toggle()
        self.library.test_step()
        self.assertEqual(self.library.test_state(), 0)
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_speech(self.library.test_speech_count() - 1),
                         b"two three")

    def test_clip_select_short_release_and_long_press_are_distinct(self):
        for button, expected in ((64, 0), (64 | 16, 2), (64 | 8, 12)):
            self.assertEqual(self.clip_library.test_mapping(0, button), expected)

    def test_clip_up_navigation_uses_stock_settings_mapping(self):
        for button in (32, 32 | 16, 32 | 8):
            self.assertEqual(self.clip_library.test_mapping(0, button), 20)

    def test_menu_cancel_does_not_rewind_or_resume(self):
        self.reset(b"one two three")
        self.library.test_step()
        self.library.test_audible(4)
        self.library.test_menu_choice(-2)
        self.assertFalse(self.library.test_menu())
        self.assertEqual(self.library.test_position(), 4)
        self.assertEqual(self.library.test_state(), 1)
        self.assertEqual(self.library.test_tracked_count(), 1)

    def test_bookmark_restore_utf8_size_signature_and_unit_validation(self):
        data = "\ufeffone żółw next".encode("utf-8")
        self.reset(data)
        offset = data.index("ż".encode())
        signature = self.library.test_signature(offset)
        self.assertTrue(self.library.test_restore(offset, len(data), 3, signature))
        self.assertEqual(self.library.test_position(), offset)
        self.assertEqual(self.library.test_get_unit(), 3)
        for position, size, unit, expected in (
                (-1, len(data), 1, signature), (0, len(data), 1, signature),
                (len(data) + 1, len(data), 1, signature),
                (offset, len(data) + 1, 1, signature),
                (offset, len(data), 5, signature),
                (offset, len(data), -1, signature),
                (offset, len(data), 1, signature ^ 1),
                (offset + 1, len(data), 1, self.library.test_signature(offset + 1))):
            self.assertFalse(self.library.test_restore(position, size, unit, expected))
            self.assertEqual(self.library.test_position(), offset)
        signature = self.library.test_signature(len(data))
        self.assertTrue(self.library.test_restore(len(data), len(data), 0, signature))

    def test_bookmark_context_change_same_size_is_rejected(self):
        self.reset(b"one two three")
        signature = self.library.test_signature(4)
        self.reset(b"one NEW three")
        self.assertFalse(self.library.test_restore(4, len(self.data), 1, signature))

    def test_menu_properties_resume_and_usb(self):
        self.reset(b"one two three")
        self.library.test_step()
        for choice in (2, 0):
            self.library.test_menu_choice(choice)
        self.assertFalse(self.library.test_menu())
        self.assertEqual(self.library.test_state(), 0)
        self.assertIn(b"/example.txt", self.library.test_property(1))
        self.assertIn(b"13 bytes", self.library.test_property(2))
        self.assertIn(b"0%", self.library.test_property(3))
        self.library.test_menu_choice(-10)
        self.assertTrue(self.library.test_menu())

    def test_menu_beginning_end_and_save_failure_feedback(self):
        self.reset(b"\xef\xbb\xbfhello world")
        self.library.test_step()
        self.library.test_menu_choice(4)
        self.library.test_menu()
        self.assertEqual(self.library.test_position(), len(self.data))
        self.library.test_menu_choice(3)
        self.library.test_menu()
        self.assertEqual(self.library.test_position(), 3)
        self.library.test_bookmark_failure()
        for choice in (1, 0, -2, -2):
            self.library.test_menu_choice(choice)
        self.library.test_menu()
        self.assertEqual(self.library.test_speech(self.library.test_speech_count() - 1),
                         b"Bookmark failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
