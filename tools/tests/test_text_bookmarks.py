import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest

from test_tts_coverage import extract_block


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = _project_materials_root(ROOT) / "text-bookmark-tests"

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#ifdef TEST_OFF32
#define off_t int32_t
#endif
#ifdef TEST_SIZE32
#define size_t uint32_t
#endif
#include "bookmark.h"
#define MAX_PATH 260
#define ROCKBOX_DIR "/.rockbox"
#define MAX(first, second) ((first) > (second) ? (first) : (second))
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define HZ 100
#define logf(...) ((void)0)
#define TALK_IDARRAY(...) ((const long[]){__VA_ARGS__, 0})
#define ID2P(identifier) str(identifier)
#define MENUITEM_STRINGLIST(name, ...) const int name = 0
enum { BOOKMARK_NO, BOOKMARK_YES, BOOKMARK_RECENT_ONLY_YES,
       BOOKMARK_RECENT_ONLY_ASK, BOOKMARK_ONE_PER_PLAYLIST, BOOKMARK_ONE_PER_TRACK };
enum { ACTION_NONE, ACTION_STD_OK, ACTION_STD_CANCEL, ACTION_STD_CONTEXT,
       ACTION_TREE_WPS, ACTION_BMS_DELETE, SYS_USB_CONNECTED,
       MENU_ATTACHED_USB, CONTEXT_BOOKMARKSCREEN, ACTIVITY_BOOKMARKSLIST,
       Icon_Bookmark, YESNO_NO, YESNO_YES, YESNO_USB,
       UNIT_INT, UNIT_TIME, UNIT_PERCENT };
@LANGUAGE_ENUM@
static char *str(int identifier)
{
    if (identifier == LANG_TTS_TEXT_BOOKMARK) return "Text bookmark";
    if (identifier == LANG_TTS_POSITION) return "Position";
    if (identifier == LANG_BOOKMARK_INVALID) return "Invalid bookmark";
    return "label";
}
struct user_settings {
    int usemrb, repeat_mode, autocreatebookmark, autoloadbookmark;
    bool playlist_shuffle, autoupdatebookmark, talk_menu;
#ifdef HAVE_ESPEAK
    bool tts_enabled;
#endif
};
static struct user_settings global_settings;
@TALK_POLICY@
struct mp3entry { const char *path; long offset; long elapsed; };
static struct mp3entry playing = { "/Music/song.mp3", 42, 9000 };
static int audio_calls, reader_calls, activities;
static int fail_open, fail_read, fail_seek, fail_write, fail_close, fail_rename;
static bool short_write, zero_write;
static int read_calls, write_calls, read_limit;
static int descriptor_kind[1024];
static int original_removes;
static char resumed_path[MAX_PATH];
static struct text_bookmark resumed_text;
static char mapped[4][1024];
static unsigned map_slot;
static const char *map_path(const char *path)
{
    char *buffer = mapped[map_slot++ % 4];
    assert(snprintf(buffer, 1024, "disk%s", path) < 1024);
    return buffer;
}
static int mock_open(const char *path, int flags, ...)
{
    int kind = flags & O_CREAT ? 2 : 1;
    if (kind == fail_open) { errno = EACCES; return -1; }
    int file = open(map_path(path), flags, 0600);
    if (file >= 0) { assert(file < 1024); descriptor_kind[file] = kind; }
    return file;
}
static ssize_t mock_read(int file, void *buffer, size_t size)
{
    if (++read_calls == fail_read) { errno = EIO; return -1; }
    if (read_limit && size > (size_t)read_limit) size = read_limit;
    return read(file, buffer, size);
}
static off_t mock_lseek(int file, off_t offset, int whence)
{
    if (fail_seek) { errno = EIO; return -1; }
    return lseek(file, offset, whence);
}
static ssize_t mock_write(int file, const void *buffer, size_t size)
{
    if (++write_calls == fail_write)
    {
        if (zero_write) return 0;
        if (short_write && size) return write(file, buffer, size - 1);
        errno = ENOSPC;
        return -1;
    }
    return write(file, buffer, size);
}
static int mock_close(int file)
{
    int kind = descriptor_kind[file];
    descriptor_kind[file] = 0;
    int result = close(file);
    if (kind == fail_close) { errno = EIO; return -1; }
    return result;
}
static int mock_rename(const char *old_path, const char *new_path)
{
    if (fail_rename) { errno = EIO; return -1; }
    return rename(map_path(old_path), map_path(new_path));
}
static int mock_remove(const char *path)
{
    const char *suffix = strrchr(path, '.');
    bool temporary = suffix && (!strcmp(suffix, ".tmp") ||
        (strlen(suffix) == 4 && suffix[1] == 't' &&
         strspn(suffix + 2, "0123456789abcdef") == 2));
    if (!temporary) original_removes++;
    return unlink(map_path(path));
}
static off_t mock_ffilesize(int file)
{
    struct stat status;
    return fstat(file, &status) < 0 ? -1 : status.st_size;
}
static void put_bytes(const char *path, const void *buffer, size_t length)
{
    int file = open(map_path(path), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    assert(file >= 0);
    assert(write(file, buffer, length) == (ssize_t)length);
    assert(close(file) == 0);
}
static void put(const char *path, const char *text) { put_bytes(path, text, strlen(text)); }
static size_t get(const char *path, char *buffer, size_t capacity)
{
    int file = open(map_path(path), O_RDONLY);
    assert(file >= 0);
    ssize_t length = read(file, buffer, capacity - 1);
    assert(length >= 0);
    buffer[length] = '\0';
    assert(close(file) == 0);
    return length;
}
static bool file_exists(const char *path) { return access(map_path(path), F_OK) == 0; }
static void reset_faults(void)
{
    fail_open = fail_read = fail_seek = fail_write = fail_close = fail_rename = 0;
    read_calls = write_calls = read_limit = 0;
    short_write = zero_write = false;
}
static char *strmemccpy(char *destination, const char *source, size_t size)
{
    size_t length = strlen(source);
    if (!size) return NULL;
    size_t copied = MIN(length, size - 1);
    memcpy(destination, source, copied);
    destination[copied] = '\0';
    return length < size ? destination + copied : NULL;
}
#define strlcat mock_strlcat
static size_t mock_strlcat(char *destination, const char *source, size_t size)
{
    size_t length = strlen(destination), added = strlen(source);
    if (length < size) strmemccpy(destination + length, source, size - length);
    return length + added;
}
static char *strrsplt(char *text, int delimiter)
{
    char *found = strrchr(text, delimiter);
    if (!found) return text;
    *found = '\0';
    return found + 1;
}
static uint32_t crc_32(const char *text, int length, uint32_t hash)
{
    while (length--) hash = hash * 33 + (unsigned char)*text++;
    return hash;
}
static void format_time(char *buffer, size_t size, long time)
{ snprintf(buffer, size, "%ld", time); }
static void path_basename(const char *path, const char **name)
{ const char *slash = strrchr(path, '/'); *name = slash ? slash + 1 : path; }
static int sound_get_pitch(void) { audio_calls++; return 100; }
static int dsp_get_timestretch(void) { audio_calls++; return 100; }
static void sound_set_pitch(int value) { (void)value; audio_calls++; }
static void dsp_set_timestretch(int value) { (void)value; audio_calls++; }
static void iap_on_repeat_state(int value) { (void)value; audio_calls++; }
static void iap_on_shuffle_state(int value) { (void)value; audio_calls++; }
static bool warn_on_pl_erase(void) { audio_calls++; return true; }
static bool bookmark_play(const char *path, int index, long elapsed,
                          unsigned long offset, int seed, const char *file)
{
    assert(!strcmp(path, "/Music/"));
    assert(!strcmp(file, "song.mp3"));
    assert(index == 2 && elapsed == 9000 && offset == 42 && seed == 7);
    audio_calls++;
    return true;
}
static void audio_stop(void) { audio_calls++; }
static void audio_pause(void) { audio_calls++; }
static int audio_status(void) { return 1; }
static const struct mp3entry *audio_current_track(void) { audio_calls++; return &playing; }
static bool playlist_dynamic_only(void) { return false; }
static bool playlist_modified(void *unused) { (void)unused; return false; }
static int playlist_get_resume_info(int *index) { *index = 2; return 0; }
static int playlist_get_display_index(void) { return 3; }
static int playlist_get_seed(void *unused) { (void)unused; return 7; }
static char *playlist_get_name(void *unused, char *buffer, size_t size)
{ (void)unused; strmemccpy(buffer, "/Music/", size); return buffer; }
static void save_playlist_screen(void *unused) { (void)unused; }
static bool yesno_pop(const char *text) { (void)text; return true; }
static void splash(int ticks, const char *text) { (void)ticks; (void)text; }
static void push_current_activity(int activity) { (void)activity; activities++; }
static void pop_current_activity(void) { activities--; }
static int voice_ids[32], voice_units[32], voice_count;
static unsigned voice_callback_count;
static long voice_values[32];
static char voiced_path[MAX_PATH];
static int talk_id(int identifier, bool enqueue)
{
    if (!enqueue) voice_count = 0;
    assert(voice_count < 32);
    voice_ids[voice_count++] = identifier;
    return 0;
}
static int talk_value(long value, int unit, bool enqueue)
{
    if (!enqueue) voice_count = 0;
    assert(voice_count < 32);
    voice_ids[voice_count] = -1;
    voice_units[voice_count] = unit;
    voice_values[voice_count++] = value;
    return 0;
}
static int talk_number(long value, bool enqueue) { return talk_value(value, UNIT_INT, enqueue); }
static int talk_spell(const char *text, bool enqueue)
{ (void)text; (void)enqueue; return 0; }
static void talk_file_or_spell(const char *directory, const char *path,
                               const long *prefix, bool enqueue)
{ (void)directory; (void)prefix; (void)enqueue; strmemccpy(voiced_path, path, MAX_PATH); }
static void talk_dir_or_spell(const char *path, const long *prefix, bool enqueue)
{ talk_file_or_spell(NULL, path, prefix, enqueue); }
static void talk_shutup(void) {}
static void cond_talk_ids_fq(int identifier) { (void)identifier; }
struct gui_synclist {
    int selected, count;
    const char *(*name)(int, void *, char *, size_t);
    int (*voice)(int, void *);
    void *data;
};
static union { long double alignment; char bytes[16384]; } plugin_memory;
static size_t plugin_size = sizeof(plugin_memory.bytes);
static bool null_plugin;
static void *plugin_get_buffer(size_t *size)
{ *size = plugin_size; return null_plugin ? NULL : plugin_memory.bytes; }
static struct { int action, selected; } actions[16];
static int action_count, action_index, menu_result, confirmation_result;
static char display[2][512];
static void gui_synclist_init(struct gui_synclist *list,
    const char *(*name)(int, void *, char *, size_t), void *data,
    bool scroll_all, int selected_size, void *parent)
{
    (void)scroll_all; (void)selected_size; (void)parent;
    memset(list, 0, sizeof(*list)); list->name = name; list->data = data;
}
static void gui_synclist_set_voice_callback(struct gui_synclist *list, int (*voice)(int, void *))
{ list->voice = voice; voice_callback_count++; }
static void gui_synclist_set_nb_items(struct gui_synclist *list, int count) { list->count = count; }
static void gui_synclist_select_item(struct gui_synclist *list, int selected) { list->selected = selected; }
static int gui_synclist_get_sel_pos(struct gui_synclist *list) { return list->selected; }
static void gui_synclist_set_title(struct gui_synclist *list, const char *title, int icon)
{ (void)list; (void)title; (void)icon; }
static void gui_synclist_draw(struct gui_synclist *list)
{
    for (int row = 0; row < 2 && list->selected + row < list->count; row++)
    {
        char buffer[512];
        const char *text = list->name(list->selected + row, list->data, buffer, sizeof(buffer));
        strmemccpy(display[row], text, sizeof(display[row]));
    }
}
static void gui_synclist_speak_item(struct gui_synclist *list)
{ if (list->voice) list->voice(list->selected, list->data); }
static void gui_synclist_scroll_stop(struct gui_synclist *list) { (void)list; }
static void list_do_action(int context, int ticks, struct gui_synclist *list, int *action)
{
    (void)context; (void)ticks;
    assert(action_index < action_count);
    *action = actions[action_index].action;
    if (actions[action_index].selected >= 0) list->selected = actions[action_index].selected;
    action_index++;
    gui_synclist_draw(list);
    gui_synclist_speak_item(list);
}
static int do_menu(const int *menu, void *selected, void *parent, bool hide)
{ (void)menu; (void)selected; (void)parent; (void)hide; return menu_result; }
static int confirm_delete_yesno(const char *name, const char *title)
{ (void)name; (void)title; return confirmation_result; }
static int default_event_handler(int action)
{ return action == SYS_USB_CONNECTED ? SYS_USB_CONNECTED : 0; }
static void action(int first, int selected, int second)
{
    actions[0].action = first; actions[0].selected = selected;
    actions[1].action = second; actions[1].selected = -1;
    action_count = 2; action_index = 0;
}
#ifdef HAVE_ESPEAK
static bool tts_read_bookmark(const char *path, const struct text_bookmark *bookmark);
#endif
#define open mock_open
#define read mock_read
#define write mock_write
#define lseek mock_lseek
#define close mock_close
#define rename mock_rename
#define remove mock_remove
#define ffilesize mock_ffilesize
@BOOKMARK_SOURCE@
#ifdef HAVE_ESPEAK
static bool reader_usb;
static bool tts_read_bookmark(const char *path, const struct text_bookmark *bookmark)
{
    memset(global_temp_buffer, 'x', sizeof(global_temp_buffer));
    memset(plugin_memory.bytes, 'y', sizeof(plugin_memory.bytes));
    strmemccpy(resumed_path, path, sizeof(resumed_path));
    resumed_text = *bookmark;
    reader_calls++;
    return reader_usb;
}
#endif
static const char *old_audio = "2;42;7;0;9000;1;0;/Music/;song.mp3";
static const char *new_audio = ">3;2;42;7;9000;1;0;105;110;/Music/;song.mp3";
static const char *book_path = "/books/Zażółć;世界.txt";
static const char *book_file = "/books/Zażółć;世界.txt.bmark";
static const char *text_entry = "T1;25;100;3;4294967295;/books/Zażółć;世界.txt";
static void unchanged(const char *path, const void *expected, size_t length)
{
    char buffer[4096];
    assert(get(path, buffer, sizeof(buffer)) == length);
    assert(!memcmp(buffer, expected, length));
}
static void test_audio(void)
{
    char filename[MAX_PATH];
    struct resume_info resume = { 0 };
    assert(parse_bookmark(filename, sizeof(filename), old_audio, &resume, false));
    assert(resume.resume_index == 2 && resume.resume_offset == 42 && resume.resume_seed == 7);
    assert(resume.resume_elapsed == 9000 && resume.repeat_mode == 1 && !resume.shuffle);
    assert(!strcmp(filename, "song.mp3") && !strcmp(global_temp_buffer, "/Music/"));
    assert(parse_bookmark(filename, sizeof(filename), new_audio, &resume, true));
    assert(resume.pitch == 105 && resume.speed == 110);
    assert(play_bookmark(old_audio));
    assert(play_bookmark(new_audio));
    assert(!parse_bookmark(filename, sizeof(filename), text_entry, &resume, false));
    const char *preserved = "malformed\r\nT2;future\nT1;1;4;0;3;/book.txt\n";
    put("/audio.bmark", preserved);
    assert(add_bookmark("/audio.bmark", old_audio, false));
    char buffer[2048];
    get("/audio.bmark", buffer, sizeof(buffer));
    assert(!strncmp(buffer, old_audio, strlen(old_audio)));
    assert(!strcmp(buffer + strlen(old_audio) + 1, preserved));
    put(RECENT_BOOKMARK_FILE, preserved);
    global_settings.usemrb = BOOKMARK_ONE_PER_TRACK;
    assert(add_bookmark(RECENT_BOOKMARK_FILE, old_audio, true));
    assert(add_bookmark(RECENT_BOOKMARK_FILE, old_audio, true));
    assert(get_bookmark_count(RECENT_BOOKMARK_FILE) == 4);
}
#ifdef HAVE_ESPEAK
static void test_parser(void)
{
    struct text_bookmark bookmark = { 1, 2, 3, 4 }, sentinel = bookmark;
    const char *path = "sentinel";
    assert(parse_text_bookmark(text_entry, &bookmark, &path));
    assert(bookmark.offset == 25 && bookmark.size == 100 && bookmark.unit == 3);
    assert(bookmark.signature == UINT32_MAX && !strcmp(path, book_path));
    const char *invalid[] = {
        "", "T", "T0;0;0;0;0;/a", "T2;0;0;0;0;/a", "T1;0;0;0;0;",
        "T1;-1;100;0;0;/a", "T1;+1;100;0;0;/a", "T1; 1;100;0;0;/a",
        "T1;1x;100;0;0;/a", "T1;1;0;0;0;/a", "T1;0;-1;0;0;/a",
        "T1;0;0;-1;0;/a", "T1;0;0;5;0;/a", "T1;0;0;0;4294967296;/a",
        "T1;0;0;0;18446744073709551616;/a", "T1;0;0;0;;/a",
        "T1;18446744073709551616;100;0;0;/a", "T1;0;18446744073709551616;0;0;/a",
        "T1;0;0;0;0;a", "T1;0;0;0;0;/", "T1;0;0;0;0;/../a",
        "T1;0;0;0;0;/a/./b", "T1;0;0;0;0;/a//b", "T1;0;0;0;0;/a/",
        "T1;0;0;0;0;/a\\b", "T1;0;0;0;0;/a\nb", "T1;0;0;0;0;/a\rb",
        "T1;0;0;0;0;/a\tb", "T1;0;0;0;0;/a\177b", "T1;0;0;0;0;/a\001b"
    };
    for (size_t index = 0; index < sizeof(invalid) / sizeof(invalid[0]); index++)
    {
        bookmark = sentinel; path = "sentinel";
        assert(!parse_text_bookmark(invalid[index], &bookmark, &path));
        assert(!memcmp(&bookmark, &sentinel, sizeof(bookmark)) && !strcmp(path, "sentinel"));
    }
    unsigned long maximum = ((unsigned long)1 << (sizeof(off_t) * CHAR_BIT - 1)) - 1;
    char line[256];
    snprintf(line, sizeof(line), "T1;%lu;%lu;4;0;/a", maximum, maximum);
    assert(parse_text_bookmark(line, &bookmark, &path));
    snprintf(line, sizeof(line), "T1;%lu;%lu;4;0;/a", maximum + 1, maximum + 1);
    assert(!parse_text_bookmark(line, &bookmark, &path));
    assert(parse_text_bookmark("T1;0;0;0;0;/a;semicolon.txt", &bookmark, &path));
    assert(!strcmp(path, "/a;semicolon.txt"));
}
static void test_roundtrip(void)
{
    struct text_bookmark expected = { 25, 100, UINT32_MAX, 3 }, selected = { 0 };
    global_settings.usemrb = BOOKMARK_YES;
    assert(bookmark_text_create_ex(book_path, &expected) == TEXT_BOOKMARK_SAVED);
    assert(bookmark_text_create(book_path, &expected));
    char buffer[2048];
    get(book_file, buffer, sizeof(buffer));
    assert(!strncmp(buffer, text_entry, strlen(text_entry)));
    assert(file_exists(book_file) && !file_exists("/books/Zażółć;世界.bmark"));
    assert(bookmark_text_create(book_path, &expected));
    assert(get_bookmark_count(book_file) == 1);
    action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
    assert(bookmark_text_select(book_path, &selected) == BOOKMARK_SUCCESS);
    assert(!memcmp(&selected, &expected, sizeof(selected)));
    expected.offset = 50;
    assert(bookmark_text_create(book_path, &expected));
    assert(get_bookmark_count(book_file) == 2);
    action(ACTION_STD_OK, 2, ACTION_STD_CANCEL);
    assert(bookmark_text_select(book_path, &selected) == BOOKMARK_SUCCESS && selected.offset == 25);
    global_settings.usemrb = BOOKMARK_NO;
    put(RECENT_BOOKMARK_FILE, "unchanged\n");
    assert(bookmark_text_create(book_path, &expected));
    unchanged(RECENT_BOOKMARK_FILE, "unchanged\n", 10);
}
static void test_cancel_and_usb(void)
{
    char buffer[2048];
    size_t length = get(book_file, buffer, sizeof(buffer));
    struct text_bookmark sentinel = { 77, 88, 99, 4 }, selected;
    const int exits[] = { ACTION_STD_CANCEL, ACTION_TREE_WPS, SYS_USB_CONNECTED };
    for (size_t index = 0; index < sizeof(exits) / sizeof(exits[0]); index++)
    {
        selected = sentinel;
        action(exits[index], 0, ACTION_STD_CANCEL);
        int result = bookmark_text_select(book_path, &selected);
        assert(result == (exits[index] == SYS_USB_CONNECTED ? BOOKMARK_USB_CONNECTED : BOOKMARK_FAIL));
        assert(!memcmp(&selected, &sentinel, sizeof(selected)));
        unchanged(book_file, buffer, length);
    }
    put(book_file, "T1;1;9;0;2;/different.txt\n");
    action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
    assert(bookmark_text_select(book_path, &selected) == BOOKMARK_FAIL);
    assert(!memcmp(&selected, &sentinel, sizeof(selected)));
    put(book_file, "T1;overflow\n");
    action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
    assert(bookmark_text_select(book_path, &selected) == BOOKMARK_FAIL);
    assert(!memcmp(&selected, &sentinel, sizeof(selected)));
    put(book_file, "");
    assert(bookmark_text_select(book_path, &selected) == BOOKMARK_FAIL && file_exists(book_file));
    assert(!bookmark_text_create(NULL, &sentinel));
    assert(bookmark_text_create_ex(NULL, &sentinel) == TEXT_BOOKMARK_FAILED);
    assert(!bookmark_text_create(book_path, NULL));
    assert(bookmark_text_create_ex(book_path, NULL) == TEXT_BOOKMARK_FAILED);
    assert(bookmark_text_select(book_path, NULL) == BOOKMARK_FAIL);
    assert(bookmark_text_select("relative", &selected) == BOOKMARK_FAIL);
}
static void test_recent(void)
{
    struct text_bookmark first = { 25, 100, 7, 2 }, second = first;
    for (int policy = BOOKMARK_ONE_PER_PLAYLIST; policy <= BOOKMARK_ONE_PER_TRACK; policy++)
    {
        put(RECENT_BOOKMARK_FILE, "");
        global_settings.usemrb = policy;
        assert(add_bookmark(RECENT_BOOKMARK_FILE, old_audio, true));
        assert(bookmark_text_create(book_path, &first));
        second.offset = 75;
        assert(bookmark_text_create(book_path, &second));
        assert(bookmark_text_create("/books/other.txt", &first));
        assert(get_bookmark_count(RECENT_BOOKMARK_FILE) == 3);
        char buffer[2048]; get(RECENT_BOOKMARK_FILE, buffer, sizeof(buffer));
        assert(strstr(buffer, old_audio) && strstr(buffer, "T1;75;100;2;7;"));
        assert(!strstr(buffer, text_entry));
    }
    global_settings.talk_menu = true;
    int previous_audio_calls = audio_calls;
    global_settings.repeat_mode = 17;
    global_settings.playlist_shuffle = true;
    for (int usb = 0; usb < 2; usb++)
    {
        reader_usb = usb;
        action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
        assert(!bookmark_mrb_load());
        assert(!strcmp(resumed_path, "/books/other.txt"));
        assert(resumed_text.offset == 25 && resumed_text.unit == 2);
        assert(audio_calls == previous_audio_calls);
        assert(global_settings.repeat_mode == 17 && global_settings.playlist_shuffle);
    }
    assert(reader_calls == 2);
    strcpy(global_temp_buffer, text_entry);
    assert(play_bookmark(global_temp_buffer));
    assert(!strcmp(resumed_path, book_path) && resumed_text.signature == UINT32_MAX);
    assert(!play_bookmark("T2;0;0;0;0;/a"));
    assert(audio_calls == previous_audio_calls);
    put(RECENT_BOOKMARK_FILE, old_audio);
    action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
    assert(bookmark_mrb_load());
    assert(audio_calls > previous_audio_calls && reader_calls == 3);
    assert(global_settings.repeat_mode == 1 && !global_settings.playlist_shuffle);
}
static void test_display(void)
{
    const char *entries[] = { text_entry, old_audio };
    struct bookmark_list *list = (void *)plugin_memory.bytes;
    list->total_count = list->count = 2; list->start = 0; list->reload = false;
    list->show_dont_resume = false; list->show_playlist_name = true;
    list->items[0] = (char *)entries[0]; list->items[1] = (char *)entries[1];
    char buffer[512];
    assert(strstr(get_bookmark_info(0, list, buffer, sizeof(buffer)), book_path));
    assert(!strcmp(get_bookmark_info(1, list, buffer, sizeof(buffer)), "Position: 25% (25/100)"));
    bookmark_list_voice_cb(0, list);
    assert(voice_count == 5 && voice_ids[1] == LANG_TTS_TEXT_BOOKMARK);
    assert(voice_ids[2] == LANG_TTS_POSITION && voice_units[3] == UNIT_PERCENT);
    assert(voice_values[3] == 25 && voice_units[4] == UNIT_INT && voice_values[4] == 25);
    assert(!strcmp(voiced_path, book_path));
    list->show_dont_resume = true;
    assert(bookmark_list_voice_cb(0, list) == 0 && voice_ids[0] == LANG_BOOKMARK_DONT_RESUME);
    bookmark_list_voice_cb(2, list);
    assert(voice_ids[1] == LANG_TTS_TEXT_BOOKMARK);
    struct text_bookmark bookmark = { 0, 0, 0, 0 };
    assert(text_bookmark_percent(&bookmark) == 0);
    for (int size = 1; size < 300; size++)
    {
        bookmark.size = size;
        for (int offset = 0; offset <= size; offset++)
        {
            bookmark.offset = offset;
            assert(text_bookmark_percent(&bookmark) == offset * 100 / size);
        }
    }
    bookmark.offset = bookmark.size = ((unsigned long)1 << (sizeof(off_t) * CHAR_BIT - 1)) - 1;
    assert(text_bookmark_percent(&bookmark) == 100);
    bookmark.offset--;
    assert(text_bookmark_percent(&bookmark) == 99);
}
static void test_text_limits(void)
{
    struct text_bookmark bookmark = { 0, 0, 0, 0 };
    char path[MAX_PATH + 10];
    memset(path, 'x', sizeof(path)); path[0] = '/'; path[sizeof(path) - 1] = 0;
    assert(!bookmark_text_create(path, &bookmark));
    path[MAX_PATH - 10] = 0;
    assert(!bookmark_text_create(path, &bookmark));
    assert(bookmark_text_create_ex(path, &bookmark) == TEXT_BOOKMARK_FAILED);
    path[MAX_PATH - 11] = 0;
    char filename[MAX_PATH];
    assert(text_bookmark_file_name(filename, sizeof(filename), path));
    assert(!bookmark_text_create("/a\nb", &bookmark));
    assert(!bookmark_text_create("/a\001b", &bookmark));
    bookmark.unit = 5;
    assert(!bookmark_text_create(book_path, &bookmark));
    bookmark.unit = 0; bookmark.offset = 1;
    assert(!bookmark_text_create(book_path, &bookmark));
    global_settings.usemrb = BOOKMARK_YES;
    bookmark.offset = 0; fail_rename = 1;
    assert(!bookmark_text_create(book_path, &bookmark));
    reset_faults();
}
static void test_large_roundtrip(void)
{
    off_t maximum = (UINT64_C(1) << (sizeof(off_t) * CHAR_BIT - 1)) - 1;
    struct text_bookmark expected = { maximum - 1, maximum, UINT32_MAX, 4 }, selected;
    global_settings.usemrb = BOOKMARK_NO;
    assert(bookmark_text_create("/books/large.txt", &expected));
    action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
    assert(bookmark_text_select("/books/large.txt", &selected) == BOOKMARK_SUCCESS);
    assert(selected.offset == expected.offset && selected.size == expected.size);
    assert(selected.signature == expected.signature && selected.unit == expected.unit);
    char buffer[2048], serialized[256];
    get("/books/large.txt.bmark", buffer, sizeof(buffer));
    snprintf(serialized, sizeof(serialized), "T1;%llu;%llu;4;4294967295;/books/large.txt\n",
             (unsigned long long)expected.offset, (unsigned long long)expected.size);
    assert(!strcmp(buffer, serialized));
    assert(strstr(display[1], "99%"));
}
#endif
static void test_preservation_and_failures(void)
{
    const char original[] = "malformed\r\nT2;future\n2;42;7;0;9000;1;0;/Music/;song.mp3\n"
                            "binary\0legacy\nT1;25;100;3;4294967295;/books/Zażółć;世界.txt";
    const size_t length = sizeof(original) - 1;
    for (int operation = 0; operation < 2; operation++)
    {
        for (int fault = 0; fault < 14; fault++)
        {
            reset_faults(); put("/failure.bmark", "");
            put_bytes("/failure.bmark", original, length);
            switch (fault)
            {
            case 0: fail_open = 1; break;
            case 1: fail_open = 2; break;
            case 2: fail_read = 1; break;
            case 3: fail_read = 3; break;
            case 4: fail_seek = 1; break;
            case 5: fail_write = 1; break;
            case 6: fail_write = 2; break;
            case 7: fail_write = 3; break;
            case 8: fail_write = 1; short_write = true; break;
            case 9: fail_write = 1; zero_write = true; break;
            case 10: fail_close = 1; break;
            case 11: fail_close = 2; break;
            case 12: fail_rename = 1; break;
            case 13:
                for (unsigned int slot = 0; slot < MAX_BOOKMARK_TEMP_FILES; slot++)
                {
                    char temporary[MAX_PATH];
                    if (!slot) snprintf(temporary, sizeof(temporary), "/failure.bmark.tmp");
                    else snprintf(temporary, sizeof(temporary), "/failure.bmark.t%02x", slot);
                    put(temporary, "do not overwrite");
                }
                break;
            }
            assert(!(operation ? delete_bookmark("/failure.bmark", 2) :
                                 add_bookmark("/failure.bmark", old_audio, false)));
            reset_faults(); unchanged("/failure.bmark", original, length);
            if (fault == 13)
            {
                for (unsigned int slot = 0; slot < MAX_BOOKMARK_TEMP_FILES; slot++)
                {
                    char temporary[MAX_PATH];
                    if (!slot) snprintf(temporary, sizeof(temporary), "/failure.bmark.tmp");
                    else snprintf(temporary, sizeof(temporary), "/failure.bmark.t%02x", slot);
                    unchanged(temporary, "do not overwrite", 16);
                    mock_remove(temporary);
                }
            }
            else assert(!file_exists("/failure.bmark.tmp"));
        }
    }
    read_limit = 1;
    assert(add_bookmark("/failure.bmark", old_audio, false));
    reset_faults();
    char buffer[4096];
    size_t saved_length = get("/failure.bmark", buffer, sizeof(buffer));
    assert(saved_length == length + strlen(old_audio) + 1);
    assert(!memcmp(buffer + strlen(old_audio) + 1, original, length));
    assert(delete_bookmark("/failure.bmark", 0));
    unchanged("/failure.bmark", original, length);
    assert(!delete_bookmark("/failure.bmark", -1));
    assert(!delete_bookmark("/failure.bmark", 99));
    unchanged("/failure.bmark", original, length);
    char oversized[1024]; memset(oversized, 'z', sizeof(oversized));
    put_bytes("/failure.bmark", oversized, sizeof(oversized));
    assert(!add_bookmark("/failure.bmark", old_audio, false));
    assert(!delete_bookmark("/failure.bmark", 0));
    unchanged("/failure.bmark", oversized, sizeof(oversized));
    assert(!original_removes);
}
static void test_recent_limit(void)
{
    global_settings.usemrb = BOOKMARK_YES;
    char original[4096] = "malformed\r\n";
    for (int index = 0; index < 12; index++)
    {
        strcat(original, old_audio); strcat(original, "\n");
        if (index == 11) strcat(original, "invalid tail\n");
    }
    put(RECENT_BOOKMARK_FILE, original);
    assert(add_bookmark(RECENT_BOOKMARK_FILE, old_audio, true));
    char buffer[4096]; get(RECENT_BOOKMARK_FILE, buffer, sizeof(buffer));
    assert(strstr(buffer, "malformed\r\n") && strstr(buffer, "invalid tail\n"));
    assert(get_bookmark_count(RECENT_BOOKMARK_FILE) == 12);
    put(RECENT_BOOKMARK_FILE, original);
    reset_faults();
    fail_read = 22;
    assert(!add_bookmark(RECENT_BOOKMARK_FILE, old_audio, true));
    reset_faults(); unchanged(RECENT_BOOKMARK_FILE, original, strlen(original));
}
static void test_atomic_temp_recovery(void)
{
    const char *target = "/audio-retry.bmark";
    for (unsigned int slot = 0; slot < MAX_BOOKMARK_TEMP_FILES - 1; slot++)
    {
        char temporary[MAX_PATH];
        if (!slot) snprintf(temporary, sizeof(temporary), "%s.tmp", target);
        else snprintf(temporary, sizeof(temporary), "%s.t%02x", target, slot);
        put(temporary, "keep audio recovery\n");
    }
    assert(add_bookmark(target, old_audio, false));
    char buffer[1024];
    get(target, buffer, sizeof(buffer));
    assert(!strncmp(buffer, old_audio, strlen(old_audio)));
    assert(delete_bookmark(target, 0));
    unchanged(target, "", 0);
    for (unsigned int slot = 0; slot < MAX_BOOKMARK_TEMP_FILES - 1; slot++)
    {
        char temporary[MAX_PATH];
        if (!slot) snprintf(temporary, sizeof(temporary), "%s.tmp", target);
        else snprintf(temporary, sizeof(temporary), "%s.t%02x", target, slot);
        unchanged(temporary, "keep audio recovery\n", 20);
        mock_remove(temporary);
    }
    assert(!file_exists("/audio-retry.bmark.t0f"));
}
static void test_window(void)
{
    char original[4096] = "";
    for (int index = 0; index < 20; index++)
    {
        char line[96]; snprintf(line, sizeof(line), "2;42;7;0;9000;1;0;/Music/;song%02d.mp3\n", index);
        strcat(original, line);
    }
    put("/window.bmark", original);
    plugin_size = 620;
    struct bookmark_list *list = (void *)plugin_memory.bytes;
    list->filename = "/window.bmark"; list->buffer_size = plugin_size;
    list->total_count = 20; list->count = 0;
    assert(buffer_bookmarks(list, 10) > 10);
    assert(strstr(list->items[0], "song10.mp3"));
    assert(strstr(bookmark_at_index(list, 19), "song19.mp3"));
    assert(strstr(bookmark_at_index(list, 0), "song00.mp3"));
    char *selected;
    action(ACTION_STD_OK, 38, ACTION_STD_CANCEL);
    assert(select_bookmark("/window.bmark", false, &selected) == BOOKMARK_SUCCESS);
    assert(strstr(selected, "song19.mp3"));
    action(ACTION_STD_OK, 2, ACTION_STD_CANCEL);
    assert(select_bookmark("/window.bmark", true, &selected) == BOOKMARK_SUCCESS);
    assert(strstr(selected, "song00.mp3"));
    action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
    assert(select_bookmark("/window.bmark", true, &selected) == BOOKMARK_SUCCESS && !selected);
    plugin_size = sizeof(plugin_memory.bytes);
}
static void test_menu(void)
{
    char *selected;
    put("/menu.bmark", "2;42;7;0;9000;1;0;/Music/;song.mp3\n");
    menu_result = 2;
    action(ACTION_STD_CONTEXT, 0, ACTION_STD_CANCEL);
    assert(select_bookmark("/menu.bmark", false, &selected) == BOOKMARK_FAIL && !selected);
    menu_result = MENU_ATTACHED_USB;
    action(ACTION_STD_CONTEXT, 0, ACTION_STD_CANCEL);
    assert(select_bookmark("/menu.bmark", false, &selected) == BOOKMARK_USB_CONNECTED && !selected);
    confirmation_result = YESNO_USB;
    action(ACTION_BMS_DELETE, 0, ACTION_STD_CANCEL);
    assert(select_bookmark("/menu.bmark", false, &selected) == BOOKMARK_USB_CONNECTED && !selected);
    confirmation_result = YESNO_YES;
    action(ACTION_BMS_DELETE, 0, ACTION_STD_CANCEL);
    assert(select_bookmark("/menu.bmark", false, &selected) == BOOKMARK_FAIL && !selected);
    assert(file_exists("/menu.bmark"));
    null_plugin = true;
    assert(select_bookmark("/menu.bmark", false, &selected) == BOOKMARK_FAIL);
    null_plugin = false; plugin_size = 16;
    assert(select_bookmark("/menu.bmark", false, &selected) == BOOKMARK_FAIL);
    plugin_size = sizeof(plugin_memory.bytes);
}
static void test_speech_policy(void)
{
    char *selected;
    put("/policy.bmark", old_audio);
    for (int menu = 0; menu < 2; menu++)
#ifdef HAVE_ESPEAK
    for (int synthesis = 0; synthesis < 2; synthesis++)
#endif
    {
        global_settings.talk_menu = menu != 0;
#ifdef HAVE_ESPEAK
        global_settings.tts_enabled = synthesis != 0;
        bool expected = menu != 0 || synthesis != 0;
#else
        bool expected = menu != 0;
#endif
        unsigned previous = voice_callback_count;
        action(ACTION_STD_CANCEL, 0, ACTION_STD_CANCEL);
        assert(select_bookmark("/policy.bmark", false, &selected) == BOOKMARK_FAIL && !selected);
        assert(voice_callback_count == previous + (expected ? 1u : 0u));
    }
    global_settings.talk_menu = false;
#ifdef HAVE_ESPEAK
    global_settings.tts_enabled = false;
#endif
}
int main(void)
{
    assert(mkdir("disk", 0700) == 0);
    assert(mkdir("disk/books", 0700) == 0);
    assert(mkdir("disk/.rockbox", 0700) == 0);
    test_speech_policy(); puts("actual bookmark menu speech policy matrix passed");
    test_audio(); puts("audio parsing, playback and mixed preservation passed");
#ifdef HAVE_ESPEAK
    test_parser(); puts("strict text parser and overflow passed");
    test_roundtrip(); puts("real text save/select and dedup passed");
    test_cancel_and_usb(); puts("cancel, USB and invalid selection preserve state passed");
    test_recent(); puts("mixed recent policies and copied reader dispatch passed");
    test_display(); puts("two-line display, speech and overflow-safe percentage passed");
    test_text_limits(); puts("text API input and path bounds passed");
    test_large_roundtrip(); puts("maximum off_t serialization and select roundtrip passed");
#else
    assert(!play_bookmark(text_entry) && !reader_calls);
    puts("stock builds preserve text without reader linkage passed");
#endif
    test_preservation_and_failures(); puts("28 I/O failure cases, deletion and binary preservation passed");
    test_atomic_temp_recovery(); puts("audio first save and deletion with 15 occupied temporary slots passed");
    test_recent_limit(); puts("recent cap and malformed legacy preservation passed");
    test_window(); puts("partial buffer selection and voice indexing passed");
    test_menu(); puts("context menu bounds, USB and deletion passed");
    assert(!activities && !original_removes);
    for (int index = 0; index < 1024; index++) assert(!descriptor_kind[index]);
    return 0;
}
'''


class TextBookmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.output = WORKSPACE / timestamp
        cls.output.mkdir(parents=True)
        source = (ROOT / "apps/bookmark.c").read_text(encoding="utf-8")
        settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        policy = "\n".join(extract_block(settings, signature) for signature in (
            "static inline bool talk_tts_enabled(", "static inline bool talk_menus_enabled("))
        identifiers = sorted(set(re.findall(r"\b(?:LANG|VOICE)_[A-Z_]+\b", source)) |
                             {"LANG_TTS_TEXT_BOOKMARK", "LANG_TTS_POSITION"})
        source = re.sub(r'^#include "[^"]+"\s*$', "", source, flags=re.MULTILINE)
        cls.harness = cls.output / "bookmark_host.c"
        cls.harness.write_text(
            HARNESS.replace("@LANGUAGE_ENUM@", "enum { " + ", ".join(identifiers) + " };")
            .replace("@TALK_POLICY@", policy)
            .replace("@BOOKMARK_SOURCE@", source), encoding="utf-8")
        cls.hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                      for name in ("apps/bookmark.c", "apps/bookmark.h", "apps/settings.h",
                                   "tools/tests/test_text_bookmarks.py")}

    def run_harness(self, mode, defines, sanitizer=None):
        output = self.output / mode
        output.mkdir()
        executable = output / "bookmark-test"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu99", "-Os", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-unused-variable", "-I", str(ROOT / "apps"),
            str(self.harness), "-o", str(executable),
        ] + ["-D" + define for define in defines]
        if sanitizer:
            command += [f"-fsanitize={sanitizer}", "-fno-sanitize-recover=all"]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / "compile.log").write_text(
            shlex.join(command) + "\n" + compiled.stdout + compiled.stderr, encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        tested = subprocess.run([str(executable)], cwd=output, capture_output=True,
                                text=True, timeout=30)
        (output / "result.json").write_text(json.dumps({
            "source_sha256": self.hashes, "returncode": tested.returncode,
            "stdout": tested.stdout, "stderr": tested.stderr,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_espeak(self):
        self.run_harness("espeak", ["HAVE_ESPEAK", "HAVE_PITCHCONTROL"])

    def test_espeak_ubsan(self):
        self.run_harness("espeak-ubsan", ["HAVE_ESPEAK", "HAVE_PITCHCONTROL"], "undefined")

    def test_native_offset_bounds(self):
        self.run_harness("offset32-ubsan", ["HAVE_ESPEAK", "TEST_OFF32"], "undefined")

    def test_stock(self):
        self.run_harness("stock-ubsan", [], "undefined")

    def test_large_file_offsets_with_32_bit_size(self):
        self.run_harness("size32-offset64-ubsan", ["HAVE_ESPEAK", "TEST_SIZE32"], "undefined")


if __name__ == "__main__":
    unittest.main(verbosity=2)
