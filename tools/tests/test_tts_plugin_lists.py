import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import unittest

from test_tts_plugin_policy import with_menu_policy


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
WORKSPACE = _project_materials_root(ROOT) / "tts-plugin-lists-tests" / RUN


def extract_block(source, signature):
    start = source.index(signature)
    masked = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        lambda match: " " * len(match.group()), source, flags=re.DOTALL)
    opening = masked.index("{", start)
    depth = 1
    closing = opening + 1
    while depth:
        if masked[closing] == "{":
            depth += 1
        elif masked[closing] == "}":
            depth -= 1
        closing += 1
    return source[start:closing] + "\n"


COMMON = r'''
#ifndef PLUGIN_LIST_TEST_API
#define PLUGIN_LIST_TEST_API
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <limits.h>
#include <errno.h>
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define MAX_PATH 260
#define HZ 100
#define TIMEOUT_BLOCK (-1)
#define CONTEXT_STD 0
#define CONTEXT_LIST 1
#define CONTEXT_TREE 2
#define NOICON 0
#define Icon_NOICON 0
#define DEBUGF(...) ((void)0)
#define ID2P(value) ((const char *)(intptr_t)(value))
#define PLUGIN_APPS_DIR "."
#define MENUITEM_STRINGLIST(name, ...) const int name = 0
enum plugin_status { PLUGIN_OK, PLUGIN_ERROR, PLUGIN_USB_CONNECTED };
enum { ACTION_NONE, ACTION_STD_OK, ACTION_STD_CANCEL, ACTION_STD_MENU,
       ACTION_STD_CONTEXT, ACTION_REDRAW, ACTION_NEXT, ACTION_PREVIOUS,
       SYS_USB_CONNECTED, LANG_FILE_ERROR = 100, LANG_PROPERTIES_FILES,
       LANG_PROPERTIES_SIZE, LANG_TRACKS, LANG_PLAYLISTS,
       LANG_PROPERTIES_SUBDIRS, LANG_PROPERTIES_DIRECTORY_PROPERTIES,
       LANG_PLUGIN_STATS_IMAGES, LANG_PLUGIN_STATS_VIDEOS,
       LANG_PLUGIN_STATS_MAX_FILES, LANG_BYTE, LANG_KIBIBYTE,
       LANG_MEBIBYTE, LANG_GIBIBYTE, LANG_WAIT, LANG_DELETED,
       VOICE_BLANK, VOICE_EMPTY_LIST };
struct gui_synclist {
    int selected_item, nb_items;
    long scheduled_talk_tick;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
    void *data;
    bool talk_menu;
};
struct simplelist_info {
    const char *title;
    int count;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*action_callback)(int, struct gui_synclist *);
    void *callback_data;
};
struct user_settings { bool talk_menu, tts_enabled; };
struct mp3entry;
static struct user_settings settings = { .talk_menu = true, .tts_enabled = true };
static void set_speech_enabled(bool enabled)
{
    settings.talk_menu = enabled;
    settings.tts_enabled = enabled;
}
static char utterances[128][2048];
static int speech_count, last_id, date_count, redraw_count;
static int speech_calls, spell_fail_at = -1, disable_menu_after = -1;
static bool enqueue_flags[128];
static struct tm spoken_date;
static int actions[64], action_count, action_index;
static int menu_choice;
static bool usb_result;
static int shown_count, locale;
static char shown_rows[32][1024];
static unsigned char plugin_buffer[16384];
static size_t audio_buffer_size = sizeof(plugin_buffer);
static bool audio_available = true;
static char search_text[32] = "book";
static int close_count, read_count, seek_count;
static long ticks;

static size_t test_strlcpy(char *dest, const char *src, size_t size)
{
    size_t length = strlen(src);
    if (size) {
        size_t copied = MIN(length, size - 1);
        memcpy(dest, src, copied);
        dest[copied] = 0;
    }
    return length;
}
static int test_spell(const char *text, bool enqueue)
{
    assert(text && speech_count < 128);
    assert(speech_calls < 128);
    int call = speech_calls++;
    enqueue_flags[call] = enqueue;
    if (call == spell_fail_at)
        return -1;
#ifdef HAVE_ESPEAK
    if (settings.tts_enabled)
        assert(strlen(text) < 1024);
#endif
    test_strlcpy(utterances[speech_count++], text, sizeof(utterances[0]));
    if (call == disable_menu_after)
        set_speech_enabled(false);
    return 0;
}
static int test_id(int32_t identity, bool enqueue)
{
    (void)enqueue;
    last_id = identity;
    return test_spell(identity == VOICE_BLANK ? "blank" : "empty", enqueue);
}
static char *test_str(int identity)
{
    switch (identity) {
    case LANG_PROPERTIES_FILES: return locale ? "Pliki" : "Files";
    case LANG_PROPERTIES_SIZE: return locale ? "Rozmiar" : "Size";
    case LANG_TRACKS: return locale ? "Utwory" : "Tracks";
    case LANG_PLAYLISTS: return locale ? "Playlisty" : "Playlists";
    case LANG_PROPERTIES_SUBDIRS: return locale ? "Podkatalogi" : "Subdirs";
    case LANG_PLUGIN_STATS_IMAGES: return locale ? "Obrazy" : "Images";
    case LANG_PLUGIN_STATS_VIDEOS: return locale ? "Filmy" : "Videos";
    case LANG_PLUGIN_STATS_MAX_FILES: return locale ? "Najwięcej plików w jednym katalogu" : "Maximum files in one directory";
    case LANG_DELETED: return locale ? "Usunięto" : "Deleted";
    case LANG_KIBIBYTE: return "KiB";
    case LANG_MEBIBYTE: return "MiB";
    case LANG_GIBIBYTE: return "GiB";
    default: return "Properties";
    }
}
static void test_date(const struct tm *date, bool enqueue)
{
    (void)enqueue;
    spoken_date = *date;
    date_count++;
}
static void test_speak(struct gui_synclist *list)
{
    if (!talk_menus_enabled(&settings) || !list->talk_menu)
        return;
    if (list->nb_items == 0) {
        test_id(VOICE_EMPTY_LIST, true);
        return;
    }
    if (list->selected_item < 0 || list->selected_item >= list->nb_items)
        return;
    if (list->get_talk) {
        list->get_talk(list->selected_item, list->data);
        return;
    }
#ifdef HAVE_ESPEAK
    char text[MAX_PATH];
    const char *name = list->get_name(list->selected_item, list->data, text, sizeof(text));
    if (name && *name)
        test_spell(name, true);
#endif
}
static void test_init(struct gui_synclist *list,
                      const char *(*name)(int, void *, char *, size_t),
                      void *data, bool scroll_all, int selection_size, void *viewport)
{
    (void)scroll_all; (void)selection_size; (void)viewport;
    *list = (struct gui_synclist){ .get_name = name, .data = data,
                                .talk_menu = talk_menus_enabled(&settings) };
}
static void test_items(struct gui_synclist *list, int count)
{ list->nb_items = count; }
static void test_select(struct gui_synclist *list, int selection)
{
    if (selection < 0 || selection >= list->nb_items)
        return;
    if (selection != list->selected_item) {
        list->selected_item = selection;
        test_speak(list);
    }
}
static int test_selection(struct gui_synclist *list)
{ return list->selected_item; }
static void test_voice(struct gui_synclist *list, int (*callback)(int, void *))
{ list->get_talk = callback; }
static void test_draw(struct gui_synclist *list)
{ (void)list; redraw_count++; }
static void test_title(struct gui_synclist *list, const char *title, int icon)
{ (void)list; (void)title; (void)icon; }
static int test_action(int context, int timeout)
{
    (void)context; (void)timeout;
    assert(action_index < action_count);
    return actions[action_index++];
}
static bool test_button(struct gui_synclist *list, int *action)
{
    if (*action == ACTION_NEXT || *action == ACTION_PREVIOUS) {
        test_select(list, list->selected_item + (*action == ACTION_NEXT ? 1 : -1));
        return true;
    }
    return false;
}
static long test_event(long action)
{ return action == SYS_USB_CONNECTED ? SYS_USB_CONNECTED : 0; }
static int test_menu(const void *menu, int *selection, void *viewport, bool toolbar)
{ (void)menu; (void)selection; (void)viewport; (void)toolbar; return menu_choice; }
static void test_simple_init(struct simplelist_info *list, char *title, int count, void *data)
{ *list = (struct simplelist_info){ .title = title, .count = count, .callback_data = data }; }
static bool test_simple_show(struct simplelist_info *list)
{
    shown_count = list->count;
    assert(shown_count >= 0 && shown_count < 32);
    for (int index = 0; index < shown_count; index++) {
        const char *text = list->get_name(index, list->callback_data, shown_rows[index], sizeof(shown_rows[index]));
        assert(text);
    }
    struct gui_synclist widget;
    test_init(&widget, list->get_name, list->callback_data, false, 1, NULL);
    widget.nb_items = list->count;
    test_speak(&widget);
    return usb_result;
}
static void test_splash(int duration, const char *text)
{ (void)duration; (void)text; }
static void test_splashf(int duration, const char *format, ...)
{ (void)duration; (void)format; }
static void *test_buffer(size_t *size)
{ *size = sizeof(plugin_buffer); return plugin_buffer; }
static void *test_audio_buffer(size_t *size)
{ *size = audio_buffer_size; return audio_available ? plugin_buffer : NULL; }
static int test_kbd(char *text, int size, void *layout)
{ (void)layout; test_strlcpy(text, search_text, (size_t)size); return 0; }
static off_t test_filesize(int descriptor)
{ struct stat status; return fstat(descriptor, &status) ? -1 : status.st_size; }
static ssize_t test_read(int descriptor, void *data, size_t size)
{ read_count++; return read(descriptor, data, size); }
static int test_close(int descriptor)
{ close_count++; return close(descriptor); }
static off_t test_seek(int descriptor, off_t offset, int whence)
{ seek_count++; return lseek(descriptor, offset, whence); }
static int test_read_line(int descriptor, char *text, int size)
{
    int length = 0;
    char next;
    ssize_t result;
    while (length + 1 < size && (result = read(descriptor, &next, 1)) > 0) {
        if (next == '\n')
            break;
        text[length++] = next;
    }
    text[length] = 0;
    return length;
}
static bool test_exists(const char *path)
{ return access(path, F_OK) == 0; }
struct test_api {
    struct user_settings *global_settings;
    int (*talk_spell)(const char *, bool);
    int (*talk_id)(int32_t, bool);
    void (*talk_date)(const struct tm *, bool);
    char *(*str)(int);
    size_t (*strlen)(const char *);
    char *(*strcpy)(char *, const char *);
    size_t (*strlcpy)(char *, const char *, size_t);
    void *(*memcpy)(void *, const void *, size_t);
    void *(*memmove)(void *, const void *, size_t);
    void *(*memchr)(const void *, int, size_t);
    int (*snprintf)(char *, size_t, const char *, ...);
    int (*strcasecmp)(const char *, const char *);
    int (*strncmp)(const char *, const char *, size_t);
    void (*gui_synclist_init)(struct gui_synclist *, const char *(*)(int, void *, char *, size_t), void *, bool, int, void *);
    void (*gui_synclist_set_nb_items)(struct gui_synclist *, int);
    void (*gui_synclist_select_item)(struct gui_synclist *, int);
    void (*gui_synclist_speak_item)(struct gui_synclist *);
    int (*gui_synclist_get_sel_pos)(struct gui_synclist *);
    void (*gui_synclist_set_voice_callback)(struct gui_synclist *, int (*)(int, void *));
    void (*gui_synclist_draw)(struct gui_synclist *);
    void (*gui_synclist_set_title)(struct gui_synclist *, const char *, int);
    bool (*gui_synclist_do_button)(struct gui_synclist *, int *);
    int (*get_action)(int, int);
    long (*default_event_handler)(long);
    int (*do_menu)(const void *, int *, void *, bool);
    void (*simplelist_info_init)(struct simplelist_info *, char *, int, void *);
    bool (*simplelist_show_list)(struct simplelist_info *);
    void (*splash)(int, const char *);
    void (*splashf)(int, const char *, ...);
    int (*open)(const char *, int, ...);
    int (*close)(int);
    ssize_t (*read)(int, void *, size_t);
    off_t (*lseek)(int, off_t, int);
    off_t (*ffilesize)(int);
    int (*read_line)(int, char *, int);
    int (*kbd_input)(char *, int, void *);
    void *(*plugin_get_buffer)(size_t *);
    void *(*plugin_get_audio_buffer)(size_t *);
    bool (*file_exists)(const char *);
    long *current_tick;
};
static struct test_api api = {
    .global_settings = &settings, .talk_spell = test_spell, .talk_id = test_id,
    .talk_date = test_date, .str = test_str, .strlen = strlen, .strcpy = strcpy,
    .strlcpy = test_strlcpy, .memcpy = memcpy, .memmove = memmove, .memchr = memchr,
    .snprintf = snprintf, .strcasecmp = strcasecmp, .strncmp = strncmp,
    .gui_synclist_init = test_init, .gui_synclist_set_nb_items = test_items,
    .gui_synclist_select_item = test_select, .gui_synclist_speak_item = test_speak,
    .gui_synclist_get_sel_pos = test_selection, .gui_synclist_set_voice_callback = test_voice,
    .gui_synclist_draw = test_draw, .gui_synclist_set_title = test_title,
    .gui_synclist_do_button = test_button, .get_action = test_action,
    .default_event_handler = test_event, .do_menu = test_menu,
    .simplelist_info_init = test_simple_init, .simplelist_show_list = test_simple_show,
    .splash = test_splash, .splashf = test_splashf, .open = open, .close = test_close,
    .read = test_read, .lseek = test_seek, .ffilesize = test_filesize,
    .read_line = test_read_line, .kbd_input = test_kbd,
    .plugin_get_buffer = test_buffer, .plugin_get_audio_buffer = test_audio_buffer,
    .file_exists = test_exists, .current_tick = &ticks,
};
static struct test_api *rb = &api;
static void reset_speech(void)
{
    speech_count = date_count = last_id = speech_calls = 0;
    spell_fail_at = disable_menu_after = -1;
}
#endif
'''


EDITOR_MAIN = r'''
static void assert_valid_utf8(const char *text)
{
    const unsigned char *cursor = (const unsigned char *)text;
    while (*cursor) {
        unsigned int trailing;
        if (*cursor < 0x80)
            trailing = 0;
        else if (*cursor >= 0xc2 && *cursor <= 0xdf)
            trailing = 1;
        else if (*cursor >= 0xe0 && *cursor <= 0xef)
            trailing = 2;
        else {
            assert(*cursor >= 0xf0 && *cursor <= 0xf4);
            trailing = 3;
        }
        cursor++;
        while (trailing--) {
            assert((*cursor & 0xc0) == 0x80);
            cursor++;
        }
    }
}

int main(void)
{
    buffer = plugin_buffer;
    buffer_size = sizeof(plugin_buffer);
    assert(do_action(ACTION_INSERT, "zażółć gęślą jaźń", 0));
    assert(do_action(ACTION_INSERT, "", 1));
    assert(do_action(ACTION_INSERT, "last", 2));
    setup_lists(&lists, 0);
    assert(speech_count == 1 && !strcmp(utterances[0], "zażółć gęślą jaźń"));
    reset_speech();
    for (int redraw = 0; redraw < 10; redraw++) {
        rb->gui_synclist_draw(&lists);
        refresh_editor_list(0, false);
    }
    assert(speech_count == 0);
    setup_lists(&lists, 2);
    assert(speech_count == 1 && !strcmp(utterances[0], "last"));
    reset_speech();
    assert(do_action(ACTION_UPDATE, "changed", 2));
    refresh_editor_list(2, true);
    assert(speech_count == 1 && !strcmp(utterances[0], "changed"));
    reset_speech();
    assert(do_action(ACTION_REMOVE, NULL, 2));
    refresh_editor_list(2, true);
    assert(speech_count == 1 && last_id == VOICE_BLANK && lists.selected_item == 1);
    reset_speech();
    assert(do_action(ACTION_REMOVE, NULL, 1));
    refresh_editor_list(1, true);
    assert(speech_count == 1 && lists.selected_item == 0);
    reset_speech();
    assert(do_action(ACTION_REMOVE, NULL, 0));
    refresh_editor_list(0, true);
    assert(speech_count == 1 && last_id == VOICE_EMPTY_LIST);
    assert(!do_action(ACTION_GET, NULL, 0));
    assert(!do_action(ACTION_REMOVE, NULL, 0));
    assert(!do_action(ACTION_INSERT, "invalid", 1));
    assert(do_action(ACTION_INSERT, "valid", 0));
    assert(!do_action(ACTION_CONCAT, NULL, 0));
    char tiny[2];
    assert(list_get_name_cb(0, NULL, tiny, sizeof(tiny)) == tiny);
    assert(!strcmp(tiny, "v"));
    assert(!list_get_name_cb(-1, NULL, tiny, sizeof(tiny)));
    assert(!list_get_name_cb(0, NULL, tiny, 0));
    char long_line[MAX_LINE_LEN];
    for (int index = 0; index < 227; index++)
        memcpy(long_line + index * 9, "ż😀漢", 9);
    memcpy(long_line + 2043, "żab", 5);
    assert(strlen(long_line) == 2047);
    assert_valid_utf8(long_line);
    assert(do_action(ACTION_UPDATE, long_line, 0));
    reset_speech();
    assert(speak_editor_line(0, NULL) == 0);
#ifdef HAVE_ESPEAK
    assert(speech_calls == 3 && speech_count == 3);
#else
    assert(speech_calls == 1 && speech_count == 1);
#endif
    char joined[MAX_LINE_LEN] = "";
    for (int index = 0; index < speech_count; index++) {
        assert(enqueue_flags[index] == (index != 0));
        assert_valid_utf8(utterances[index]);
#ifdef HAVE_ESPEAK
        assert(strlen(utterances[index]) <= 768);
#endif
        strcat(joined, utterances[index]);
    }
    assert(!strcmp(joined, long_line));
    reset_speech();
    spell_fail_at = 0;
    assert(speak_editor_line(0, NULL) == -1 && speech_calls == 1 && speech_count == 0);
#ifdef HAVE_ESPEAK
    reset_speech();
    spell_fail_at = 1;
    assert(speak_editor_line(0, NULL) == -1 && speech_calls == 2 && speech_count == 1);
    assert(!enqueue_flags[0] && enqueue_flags[1]);
#endif
    reset_speech();
    disable_menu_after = 0;
    assert(speak_editor_line(0, NULL) == 0 && speech_calls == 1);
    set_speech_enabled(true);
    reset_speech();
    settings.tts_enabled = false;
    assert(speak_editor_line(0, NULL) == 0 && speech_calls == 1);
    assert(!enqueue_flags[0] && !strcmp(utterances[0], long_line));
    settings.tts_enabled = true;
    assert(do_action(ACTION_UPDATE, "", 0));
    reset_speech();
    assert(speak_editor_line(0, NULL) == 0 && speech_calls == 1 && last_id == VOICE_BLANK);
    assert(!enqueue_flags[0]);
    reset_speech();
    spell_fail_at = 0;
    assert(speak_editor_line(0, NULL) == -1 && speech_calls == 1);
    reset_speech();
    set_speech_enabled(false);
    assert(speak_editor_line(0, NULL) == 0);
    refresh_editor_list(0, true);
    assert(speech_count == 0);
    set_speech_enabled(true);
    assert(speak_editor_line(-1, NULL) == 0);
    assert(speak_editor_line(line_count, NULL) == 0);
    assert(speech_count == 0);
    puts("editor actual C: initial/refresh/blank/delete/empty/bounds/2047B UTF8/chunk order/failure/off/legacy PASS");
    return 0;
}
'''


EDITOR_LOADER_MAIN = r'''
static int loader_read_calls, loader_seek_calls;
static int loader_read_fail_at = -1, loader_seek_fail_at = -1;

static ssize_t loader_read(int descriptor, void *data, size_t size)
{
    if (loader_read_calls++ == loader_read_fail_at) {
        errno = EIO;
        return -1;
    }
    return read(descriptor, data, size);
}

static off_t loader_seek(int descriptor, off_t offset, int whence)
{
    if (loader_seek_calls++ == loader_seek_fail_at) {
        errno = EIO;
        return -1;
    }
    return lseek(descriptor, offset, whence);
}

static int loader_fixture(const char *input, size_t length)
{
    int descriptor = open("editor-boundary.dat", O_RDWR | O_CREAT | O_TRUNC, 0600);
    assert(descriptor >= 0);
    assert(write(descriptor, input, length) == (ssize_t)length);
    assert(lseek(descriptor, 0, SEEK_SET) == 0);
    loader_read_calls = loader_seek_calls = 0;
    loader_read_fail_at = loader_seek_fail_at = -1;
    return descriptor;
}

static void assert_editor_load(const char *input, size_t length,
                               char expected[][MAX_LINE_LEN], int expected_count)
{
    int descriptor = loader_fixture(input, length);
    buffer = plugin_buffer;
    buffer_size = sizeof(plugin_buffer);
    char_count = line_count = last_action_line = last_char_index = 0;
    int bytes_read;
    while ((bytes_read = read_editor_line(descriptor)) > 0) {
        assert(line_count < expected_count);
        assert(do_action(ACTION_INSERT, temp_line, line_count));
    }
    assert(bytes_read == 0 && line_count == expected_count);
    assert(lseek(descriptor, 0, SEEK_CUR) == (off_t)length);
    for (int index = 0; index < line_count; index++)
        assert(!strcmp(do_action(ACTION_GET, NULL, index), expected[index]));
    assert(close(descriptor) == 0);
}

static void check_editor_boundary(size_t length, const char *delimiter,
                                   int blank_lines, bool following)
{
    char input[9000], expected[8][MAX_LINE_LEN] = {{0}};
    size_t used = length, delimiter_size = strlen(delimiter), offset = 0;
    int expected_count = 0;
    memset(input, 'x', length);
    while (offset < length) {
        size_t segment = MIN(length - offset, MAX_LINE_LEN - 1);
        memset(expected[expected_count++], 'x', segment);
        offset += segment;
    }
    if (delimiter_size) {
        if (!length)
            expected_count++;
        for (int index = 0; index <= blank_lines; index++) {
            memcpy(input + used, delimiter, delimiter_size);
            used += delimiter_size;
        }
        expected_count += blank_lines;
    }
    if (following) {
        assert(delimiter_size);
        memcpy(input + used, "Second\nThird", 12);
        used += 12;
        strcpy(expected[expected_count++], "Second");
        strcpy(expected[expected_count++], "Third");
    }
    assert_editor_load(input, used, expected, expected_count);
}

int main(void)
{
    api.read_line = read_line;
    api.read = loader_read;
    api.lseek = loader_seek;
    const size_t lengths[] = {0, 1, 2046, 2047, 2048, 4094, 4095};
    const char *delimiters[] = {"", "\n", "\r\n"};
    for (size_t length_index = 0; length_index < sizeof(lengths) / sizeof(lengths[0]); length_index++) {
        for (size_t delimiter_index = 0; delimiter_index < sizeof(delimiters) / sizeof(delimiters[0]); delimiter_index++) {
            check_editor_boundary(lengths[length_index], delimiters[delimiter_index], 0, false);
            if (delimiter_index) {
                check_editor_boundary(lengths[length_index], delimiters[delimiter_index], 0, true);
                check_editor_boundary(lengths[length_index], delimiters[delimiter_index], 1, true);
                check_editor_boundary(lengths[length_index], delimiters[delimiter_index], 2, false);
            }
        }
    }
    char input[4096], expected[8][MAX_LINE_LEN] = {{0}};
    for (int index = 0; index < 227; index++)
        memcpy(input + index * 9, "ż😀漢", 9);
    memcpy(input + 2043, "żab", 4);
    memcpy(expected[0], input, 2047);
    strcpy(expected[1], "Second");
    strcpy(expected[2], "Third");
    memcpy(input + 2047, "\r\nSecond\nThird", 14);
    assert_editor_load(input, 2061, expected, 3);

    memset(input, 'x', 2047);
    memset(expected, 0, sizeof(expected));
    memset(expected[0], 'x', 2047);
    strcpy(expected[1], "Next");
    memcpy(input + 2047, "\rNext\n", 6);
    assert_editor_load(input, 2053, expected, 2);
    expected[1][0] = '\0';
    input[2047] = '\r';
    assert_editor_load(input, 2048, expected, 2);

    for (int fault = 0; fault < 4; fault++) {
        memcpy(input + 2047, fault == 1 ? "\r\n" : "zz", 2);
        int descriptor = loader_fixture(input, 2049);
        if (fault < 2)
            loader_read_fail_at = fault;
        else
            loader_seek_fail_at = fault - 2;
        assert(read_editor_line(descriptor) == -1);
        assert(close(descriptor) == 0);
    }
    loader_read_fail_at = loader_seek_fail_at = -1;
    assert(read_editor_line(-1) == -1);
    puts("editor loader actual read_line C: LF/CRLF/EOF/real blanks/overlong segments/2047B UTF8/positions/errors PASS");
    return 0;
}
'''


DICT_MAIN = r'''
int main(void)
{
    assert(sizeof(struct stWord) == 36);
    assert(reverse(UINT32_C(0x89abcdef)) == UINT32_C(0xefcdab89));
    char text[] = "  pierwszy akapit.\n  Drugi żółty akapit.  ";
    char line[256];
    assert(show_definition("word", text) == PLUGIN_OK && shown_count == 2);
    assert(!strcmp(shown_rows[0], "pierwszy akapit."));
    assert(!strcmp(shown_rows[1], "Drugi żółty akapit."));
    assert(!definition_get_name(-1, text, line, sizeof(line)));
    assert(!definition_get_name(2, text, line, sizeof(line)));
    assert(!definition_get_name(0, text, line, 0));
    char tiny[2];
    assert(definition_get_name(0, "żółć", tiny, sizeof(tiny)) == tiny && !tiny[0]);
    assert(show_definition("empty", " \n\t ") == PLUGIN_OK && shown_count == 0);
    unsigned char long_word[370];
    memset(long_word, 'a', 179);
    memcpy(long_word + 179, "ż", 2);
    memset(long_word + 181, 'b', 188);
    long_word[369] = 0;
    const char *next = definition_next_line((char *)long_word);
    assert(next == (char *)long_word + 179);
    assert(show_definition("long", (char *)long_word) == PLUGIN_OK && shown_count == 3);
    char joined[512] = "";
    for (int index = 0; index < shown_count; index++)
        strcat(joined, shown_rows[index]);
    assert(!strcmp(joined, (char *)long_word));
    usb_result = true;
    assert(show_definition("usb", "text") == PLUGIN_USB_CONNECTED);
    usb_result = false;
    reset_speech();
    set_speech_enabled(false);
    assert(show_definition("off", "nothing spoken") == PLUGIN_OK && speech_count == 0);
    set_speech_enabled(true);
    assert(plugin_start(NULL) == PLUGIN_OK);
    assert(shown_count == 1 && !strcmp(shown_rows[0], "A useful definition."));
    assert(close_count == 2);
    strcpy(search_text, "aardvark");
    seek_count = 0;
    assert(plugin_start(NULL) == PLUGIN_OK && seek_count == 2);
    int descriptor = open("dict.index", O_RDWR);
    assert(descriptor >= 0);
    assert(ftruncate(descriptor, 1) == 0);
    close(descriptor);
    assert(plugin_start(NULL) == PLUGIN_ERROR);
    puts("dictionary actual C: disk/UTF8/chunks/empty/off/USB/malformed index PASS");
    return 0;
}
'''


STATS_SUPPORT = r'''
static int scan_display_count;
void display_dir_stats(struct dir_stats *stats)
{ (void)stats; scan_display_count++; assert(speech_count == 0); }
bool collect_dir_stats(struct dir_stats *stats, bool (*callback)(const char *))
{
    (void)callback;
    stats->file_count = 100;
    stats->audio_file_count = 51;
    stats->m3u_file_count = 3;
    stats->img_file_count = 7;
    stats->vid_file_count = 9;
    stats->dir_count = 11;
    stats->max_files_in_dir = 66;
    stats->byte_count = 1024 * 1024;
    display_dir_stats(stats);
    return true;
}
'''


STATS_MAIN = r'''
int main(void)
{
    for (locale = 0; locale < 2; locale++) {
        reset_speech();
        assert(plugin_start(NULL) == PLUGIN_OK && shown_count == 8);
        assert(strstr(shown_rows[0], "100"));
        assert(strstr(shown_rows[1], "1024 KiB"));
        assert(strstr(shown_rows[2], "51"));
        assert(strstr(shown_rows[3], "3"));
        assert(strstr(shown_rows[4], locale ? "Obrazy: 7" : "Images: 7"));
        assert(strstr(shown_rows[5], locale ? "Filmy: 9" : "Videos: 9"));
        assert(strstr(shown_rows[6], "11"));
        assert(strstr(shown_rows[7], "66"));
        struct gui_synclist widget;
        struct dir_stats stats = { .file_count = 42 };
        test_init(&widget, stats_get_name, &stats, false, 1, NULL);
        widget.nb_items = 8;
        reset_speech();
        assert(stats_list_action(ACTION_STD_OK, &widget) == ACTION_NONE);
#ifdef HAVE_ESPEAK
        assert(speech_count == 1 && strstr(utterances[0], "42"));
#else
        assert(speech_count == 0);
#endif
        reset_speech();
        assert(stats_list_action(ACTION_REDRAW, &widget) == ACTION_REDRAW);
        assert(speech_count == 0);
        char line[20];
        assert(!stats_get_name(-1, &stats, line, sizeof(line)));
        assert(!stats_get_name(8, &stats, line, sizeof(line)));
        set_speech_enabled(false);
        assert(stats_list_action(ACTION_STD_OK, &widget) == ACTION_NONE);
        assert(speech_count == 0);
        set_speech_enabled(true);
    }
    reset_speech();
    usb_result = true;
    assert(plugin_start(NULL) == PLUGIN_USB_CONNECTED);
    assert(scan_display_count >= 9);
    puts("statistics actual C: eight localized rows/repeat/no scan flood/off/USB PASS");
    return 0;
}
'''


CALENDAR_MAIN = r'''
int main(void)
{
    struct shown date = { .mday = 9, .mon = 10, .year = 2026, .wday = 4 };
    speak_calendar_day(&date);
    assert(date_count == 1 && speech_count == 0);
    assert(spoken_date.tm_year == 126 && spoken_date.tm_mon == 9);
    assert(spoken_date.tm_mday == 9 && spoken_date.tm_wday == 5);
    memos[0] = (struct memo){ .day = 9, .month = 10, .year = 2020, .type = 2 };
    strcpy(memos[0].message, "urodziny Żanety");
    memos[1] = (struct memo){ .day = 9, .month = 10, .year = 2026, .type = 3 };
    strcpy(memos[1].message, "second event");
    memos[2] = (struct memo){ .day = 10, .type = 3 };
    memos_in_memory = 3;
    reset_speech();
    speak_calendar_day(&date);
    assert(date_count == 1 && speech_count == 1);
    assert(!strcmp(utterances[0], "urodziny Żanety (6 yrs)"));
    assert(memos_in_shown_memory == 2);
    reset_speech();
    actions[0] = ACTION_STD_CANCEL; action_count = 1; action_index = 0;
    assert(!view_events(1, &date));
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && !strcmp(utterances[0], "second event"));
#else
    assert(speech_count == 0);
#endif
    reset_speech();
    set_speech_enabled(false);
    speak_calendar_day(&date);
    assert(date_count == 0 && speech_count == 0);
    set_speech_enabled(true);
    date.mday = 11;
    speak_calendar_day(&date);
    assert(date_count == 1 && speech_count == 0);
    puts("calendar actual C: date/first event/all events initial/off PASS");
    return 0;
}
'''


SHORTCUTS_SUPPORT = r'''
#define LOOP_EXIT 1
enum sc_list_action_type { SCLA_NONE, SCLA_SELECT, SCLA_DELETE, SCLA_USB };
typedef struct { char path[MAX_PATH + 1]; char disp[MAX_PATH + 1]; } sc_entry_t;
typedef struct { sc_entry_t *entries; int entry_cnt; } sc_file_t;
static sc_file_t sc_file;
static bool user_file;
static char *link_filename = "shortcuts.link";
static bool is_valid_index(sc_file_t *file, int index)
{ return index >= 0 && index < file->entry_cnt; }
static int goto_entry(char *path)
{ (void)path; return LOOP_EXIT; }
static bool remove_entry(sc_file_t *file, int index)
{ (void)file; (void)index; return true; }
static bool dump_sc_file(sc_file_t *file, char *path)
{ (void)file; (void)path; return true; }
'''


SHORTCUTS_MAIN = r'''
int main(void)
{
    sc_entry_t entries[2] = { { "/first", "Pierwszy" }, { "/second", "Drugi" } };
    sc_file = (sc_file_t){ entries, 2 };
    int selected = 0;
    actions[0] = ACTION_STD_CANCEL; action_count = 1;
    assert(list_sc(&selected) == LOOP_EXIT);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && !strcmp(utterances[0], "Pierwszy"));
#else
    assert(speech_count == 0);
#endif
    reset_speech(); action_index = 0; selected = 1;
    assert(list_sc(&selected) == LOOP_EXIT);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && !strcmp(utterances[0], "Drugi"));
#endif
    reset_speech(); action_index = 0; sc_file.entry_cnt = 1;
    assert(list_sc(&selected) == LOOP_EXIT && selected == 0);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && !strcmp(utterances[0], "Pierwszy"));
#endif
    reset_speech(); action_index = 0; set_speech_enabled(false);
    assert(list_sc(&selected) == LOOP_EXIT && speech_count == 0);
    set_speech_enabled(true);
    action_index = 0; actions[0] = SYS_USB_CONNECTED;
    assert(list_sc(&selected) == PLUGIN_USB_CONNECTED);
    puts("shortcuts actual C: initial/nonzero/post-delete clamp/off/USB PASS");
    return 0;
}
'''


RFA_SUPPORT = r'''
#define RFA_LIST_DAT "folder_advance_list.dat"
static void generate(struct rfa_scan *scan) { (void)scan; }
static int save_dirs(struct rfa_scan *scan) { (void)scan; return 1; }
'''


RFA_MAIN = r'''
int main(void)
{
    struct rfa_scan scan = { 0 };
    assert(load_dirs(&scan) == 0 && scan.dirs->count == 3);
    char label[MAX_PATH];
    assert(!strcmp(list_get_name_cb(0, &scan, label, sizeof(label)), "/foo"));
    assert(!list_get_name_cb(3, &scan, label, sizeof(label)));
    assert(!disable_dir(-1, &scan) && !disable_dir(3, &scan));
    assert(disable_dir(0, &scan));
    assert(!strcmp(list_get_name_cb(0, &scan, label, sizeof(label)), "Deleted"));
    assert(load_dirs(&scan) == 0);
    actions[0] = ACTION_STD_CONTEXT; actions[1] = ACTION_STD_CANCEL;
    action_count = 2; menu_choice = 1;
    assert(edit(&scan) == 0);
#ifdef HAVE_ESPEAK
    assert(speech_count == 2 && !strcmp(utterances[1], "Deleted"));
#else
    assert(speech_count == 0);
#endif
    assert(scan.dirs == NULL);
    assert(((struct rfa_dirs *)plugin_buffer)->dir[1][0] == '/');
    assert(((struct rfa_dirs *)plugin_buffer)->dir[2][0] == ' ');
    reset_speech(); set_speech_enabled(false);
    assert(load_dirs(&scan) == 0);
    actions[0] = ACTION_STD_CANCEL; action_count = 1; action_index = 0;
    assert(edit(&scan) == 0 && speech_count == 0);
    set_speech_enabled(true);
    audio_available = false;
    int previous_closes = close_count;
    assert(load_dirs(&scan) == -2 && close_count == previous_closes + 1 && !scan.dirs);
    audio_available = true;
    audio_buffer_size = 1;
    assert(load_dirs(&scan) == -3 && !scan.dirs);
    audio_buffer_size = sizeof(plugin_buffer);
    int descriptor = open(RFA_LIST_DAT, O_WRONLY | O_TRUNC);
    int invalid_count = INT_MAX;
    assert(write(descriptor, &invalid_count, sizeof(invalid_count)) == sizeof(invalid_count));
    close(descriptor);
    assert(load_dirs(&scan) == -3);
    descriptor = open(RFA_LIST_DAT, O_WRONLY | O_TRUNC);
    invalid_count = 1;
    assert(write(descriptor, &invalid_count, sizeof(invalid_count)) == sizeof(invalid_count));
    memset(label, 'x', sizeof(label));
    assert(write(descriptor, label, sizeof(label)) == sizeof(label));
    close(descriptor);
    assert(load_dirs(&scan) == -3);
    puts("random folders actual C: first/deleted/tree boundary/off/file bounds/fd close PASS");
    return 0;
}
'''


class PluginListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WORKSPACE.mkdir(parents=True)
        cls.sources = {}
        paths = ["text_editor.c", "dict.c", "stats.c", "calendar.c",
                 "random_folder_advance_config.c", "shortcuts/shortcuts_view.c"]
        for relative in paths:
            cls.sources[relative] = (ROOT / "apps/plugins" / relative).read_text(encoding="utf-8")
        provenance = {
            "apps/plugins/" + name: hashlib.sha256(
                (ROOT / "apps/plugins" / name).read_bytes()).hexdigest()
            for name in paths
        }
        (WORKSPACE / "input-sha256.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    def run_source(self, name, body, address_sanitize=False):
        for espeak in (False, True):
            for sanitizer in (("", "ubsan", "asan-ubsan") if address_sanitize else ("", "ubsan")):
                mode = ("espeak" if espeak else "legacy") + ("-" + sanitizer if sanitizer else "")
                with self.subTest(plugin=name, mode=mode):
                    output = WORKSPACE / name / mode
                    output.mkdir(parents=True)
                    (output / "plugin.h").write_text(with_menu_policy(COMMON), encoding="utf-8")
                    source = output / "harness.c"
                    source.write_text('#include "plugin.h"\n' + body, encoding="utf-8")
                    definition = "A useful definition.\n"
                    definition += "A long definition containing useful navigation and żółte słowa. " * 7
                    description = definition.encode("utf-8") + b"\n"
                    (output / "dict.desc").write_bytes(description)
                    records = [struct.pack(">32sI", word.encode("ascii"), 0)
                               for word in ("alpha", "book", "zoo")]
                    (output / "dict.index").write_bytes(b"".join(records))
                    folder_data = struct.pack("=i", 3) + b"".join(
                        folder.encode().ljust(260, b"\0") for folder in ("/foo", "/foobar", "/foo/child"))
                    (output / "folder_advance_list.dat").write_bytes(folder_data)
                    executable = output / "plugin-lists-test"
                    command = shlex.split(os.environ.get("CC", "cc")) + [
                        "-std=c99", "-D_POSIX_C_SOURCE=200809L", "-O1", "-g",
                        "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                        "-Wno-unused-variable", "-Wno-pointer-sign", "-I", str(output),
                        "-I", str(ROOT / "apps/plugins"), str(source), "-o", str(executable),
                    ]
                    if espeak:
                        command.append("-DHAVE_ESPEAK")
                    if sanitizer == "ubsan":
                        command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
                    elif sanitizer == "asan-ubsan":
                        command.extend(["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                                        "-fno-omit-frame-pointer", "-no-pie"])
                    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    (output / "compile.log").write_text(
                        shlex.join(command) + "\n" + compiled.stdout + compiled.stderr, encoding="utf-8")
                    self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                    result = subprocess.run([str(executable)], cwd=output,
                                            capture_output=True, text=True, timeout=30)
                    (output / "result.json").write_text(json.dumps({
                        "returncode": result.returncode, "stdout": result.stdout,
                        "stderr": result.stderr,
                    }, indent=2), encoding="utf-8")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(result.stderr, "")

    def test_editor(self):
        source = self.sources["text_editor.c"]
        declarations = r'''
#define MAX_LINE_LEN 2048
#define ACTION_INSERT 0
#define ACTION_GET 1
#define ACTION_REMOVE 2
#define ACTION_UPDATE 3
#define ACTION_CONCAT 4
static unsigned char *buffer;
static size_t buffer_size, char_count;
static int line_count, last_action_line, last_char_index;
static struct gui_synclist lists;
'''
        signatures = ["static void cpuboost(", "static char* _do_action(",
                      "static char* do_action(", "static const char* list_get_name_cb(",
                      "static int speak_editor_line(", "static void setup_lists(",
                      "static void refresh_editor_list("]
        functions = "\n".join(extract_block(source, signature) for signature in signatures)
        self.run_source("editor", declarations + functions + EDITOR_MAIN)
        self.assertRegex(source, r"else\s+temp_line\[0\] = '\\0';")
        self.assertIn("refresh_editor_list(cur_sel, speak_selection && !exit)", source)
        self.assertIn("line_count ? cur_sel+1 : 0", source)
        self.assertIn("lists.scheduled_talk_tick ? HZ/5 + 1 : TIMEOUT_BLOCK", source)

    def test_editor_line_loading(self):
        source = self.sources["text_editor.c"]
        misc = (ROOT / "apps/misc.c").read_text(encoding="utf-8")
        actual_reader = extract_block(misc, "int read_line(int fd, char* buffer, int buffer_size)")
        provenance = {
            "source": "apps/misc.c",
            "sha256": hashlib.sha256((ROOT / "apps/misc.c").read_bytes()).hexdigest(),
            "extracted_sha256": hashlib.sha256(actual_reader.encode("utf-8")).hexdigest(),
        }
        (WORKSPACE / "editor-reader-source.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        declarations = r'''
#define MAX_LINE_LEN 2048
#define ACTION_INSERT 0
#define ACTION_GET 1
#define ACTION_REMOVE 2
#define ACTION_UPDATE 3
#define ACTION_CONCAT 4
static unsigned char *buffer;
static size_t buffer_size, char_count;
static int line_count, last_action_line, last_char_index;
static char temp_line[MAX_LINE_LEN];
'''
        functions = "\n".join(extract_block(source, signature) for signature in (
            "static void cpuboost(", "static char* _do_action(", "static char* do_action(",
            "static int read_editor_line("))
        self.run_source("editor-loader", declarations + actual_reader + functions + EDITOR_LOADER_MAIN,
                        address_sanitize=True)
        self.assertIn("while ((bytes_read = read_editor_line(fd)) > 0)", source)
        self.assertIn("if (bytes_read < 0)", source)

    def test_dictionary(self):
        source = self.sources["dict.c"]
        self.assertNotIn("view_text(", source)
        self.run_source("dictionary", source + DICT_MAIN)

    def test_statistics(self):
        source = self.sources["stats.c"]
        size_source = (ROOT / "apps/plugins/lib/mul_id3.c").read_text(encoding="utf-8")
        support = '#include "lib/mul_id3.h"\n'
        support += "static const int32_t units[] = { LANG_BYTE, LANG_KIBIBYTE, LANG_MEBIBYTE, LANG_GIBIBYTE };\n"
        support += extract_block(size_source, "unsigned long human_size(")
        support += STATS_SUPPORT
        self.run_source("statistics", support + source + STATS_MAIN)

    def test_calendar(self):
        source = self.sources["calendar.c"]
        declarations = "#define MAX_CHAR_MEMO_LEN 64\n#define MAX_MEMOS_IN_A_MONTH 128\n"
        declarations += extract_block(source, "struct shown {").rstrip() + ";\n"
        declarations += extract_block(source, "struct memo {").rstrip()
        declarations += " memos[MAX_MEMOS_IN_A_MONTH];\n"
        declarations += r'''
#define CALENDAR_EVENT_MENU_NAME "select"
static int pointer_array[MAX_MEMOS_IN_A_MONTH];
static int memos_in_memory, memos_in_shown_memory;
static bool been_in_usb_mode;
static bool edit_memo(int selected, struct shown *date)
{ (void)selected; (void)date; return false; }
'''
        functions = "\n".join(extract_block(source, signature) for signature in (
            "static const char* get_event_text(", "static bool view_events(",
            "static void update_memos_shown(", "static void speak_calendar_day("))
        self.run_source("calendar", declarations + functions + CALENDAR_MAIN)
        draw = extract_block(source, "static void draw_calendar(")
        self.assertNotIn("speak_calendar_day", draw)
        self.assertNotIn("talk_", draw)
        self.assertIn("speak_date = false", extract_block(source, "enum plugin_status plugin_start("))
        self.assertIn("gui_memos.scheduled_talk_tick ? HZ/5 + 1 : TIMEOUT_BLOCK", source)

    def test_shortcuts(self):
        source = self.sources["shortcuts/shortcuts_view.c"]
        functions = "\n".join(extract_block(source, signature) for signature in (
            "enum sc_list_action_type draw_sc_list(struct gui_synclist *gui_sc)\n{",
            "static const char* build_sc_list(int selected_item, void *data,\n                                 char *buffer, size_t buffer_len)\n{",
            "int list_sc(int *selected_item)\n{"))
        self.run_source("shortcuts", SHORTCUTS_SUPPORT + functions + SHORTCUTS_MAIN)

    def test_random_folders(self):
        source = self.sources["random_folder_advance_config.c"]
        declarations = "#define MAX_IGNORED_DIRS 10\n"
        declarations += extract_block(source, "struct rfa_dirs ").rstrip() + ";\n"
        declarations += extract_block(source, "struct rfa_scan ").rstrip() + ";\n"
        functions = "\n".join(extract_block(source, signature) for signature in (
            "static const char* list_get_name_cb(", "static int load_dirs(",
            "static bool disable_dir(", "static void set_title(", "static int edit("))
        self.run_source("random-folders", declarations + RFA_SUPPORT + functions + RFA_MAIN)
        self.assertIn("lists.scheduled_talk_tick ? HZ/5 + 1 : TIMEOUT_BLOCK", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
