"""Exercise reader notification cancellation with actual core C functions."""

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

from test_tts_coverage import extract_block
from test_tts_reader import HARNESS_PREFIX as READER_PREFIX
from test_tts_reader import HARNESS_SUFFIX as READER_SUFFIX
from test_tts_reader import empty_feedback_policy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "apps/tts.c", "apps/tts.h", "apps/voice_thread.c", "apps/voice_thread.h",
    "apps/tts_reader.c", "apps/tts_reader_settings.h", "apps/talk.c", "apps/accessibility_screen.c",
    "apps/accessibility.c", "apps/accessibility.h",
    "apps/gui/list.c", "apps/gui/list.h", "apps/settings.h",
    "lib/utf8proc/utf8proc.c", "lib/utf8proc/utf8proc.h",
    "lib/utf8proc/utf8proc_data.c", "lib/espeak/rb_espeak.h",
    "tools/tests/test_tts_reader.py", "tools/tests/test_tts_coverage.py",
    "tools/project_materials.py", "tools/tests/test_tts_reader_notices.py",
)
SCENARIOS = (
    "reader_search_result_queue", "reader_search_result_rejected",
    "repeat_time", "time_then_lock", "time_then_unlock", "loop_time", "loop_lock",
    "bookmark", "notice_paused", "pending_cancel", "paused_unstarted",
    "active_synthesis", "utf8_repeated", "stale_callbacks", "stale_clock_generation",
    "new_tracked_only_reset", "invalid_queue_full", "natural_drain", "natural_stop",
    "natural_pause_stop", "appended_notice_after_drain", "appended_notice_before_drain",
    "pause_resume", "navigate", "first_and_force", "synthesis_error", "output_error",
    "voice_error", "concurrent_stop_submit", "stale_worker_result",
    "silent_tracked_drain", "talk_duplicate_stop", "uninitialized_legacy_stop",
    "disabled_while_waiting", "catalog_invalid_while_waiting",
    "status_disabled", "status_missing_catalog", "status_initialization",
    "status_initialization_failure", "status_invalid_ids", "status_reader_position",
    "status_recorded_preemption", "status_pending_and_tail", "status_silent",
    "status_synthesis_error",
    "status_group", "status_group_reader_position", "status_group_initialization",
    "status_group_invalid", "status_group_initialization_failure", "status_group_maximum",
    "status_group_overflow",
    "boundary_repeat", "boundary_wrap", "boundary_repeat_reader", "boundary_wrap_reader",
    "boundary_inward", "boundary_inward_reader",
    "boundary_wrap_deferred", "boundary_wrap_deferred_reader",
    "boundary_wrap_deferred_inward", "boundary_wrap_deferred_inward_reader",
    "boundary_wrap_position", "boundary_wrap_position_reader",
    "boundary_wrap_deferred_inward_position", "boundary_wrap_deferred_inward_position_reader",
    "screen_date", "screen_date_paused", "screen_date_invalid", "screen_date_disabled",
    "screen_summary", "screen_summary_paused", "screen_summary_unknown",
    "screen_summary_invalid", "screen_summary_disabled", "screen_summary_twice",
    "screen_date_unprimed", "screen_summary_unprimed",
)


def read_sources():
    return {relative: (ROOT / relative).read_bytes() for relative in INPUTS}


def function_matches(source, name):
    pattern = (r"^(?:static\s+)?[\w *]+\b" + re.escape(name) +
               r"\s*\([^;{}]*\)\s*\{")
    return list(re.finditer(pattern, source, re.MULTILINE))


def function(source, name):
    matches = function_matches(source, name)
    if len(matches) != 1:
        raise AssertionError(f"Expected one definition of {name}, found {len(matches)}")
    return extract_block(source, matches[0].group())


def declaration(source, name):
    pattern = r"^static[^;\n]*\b" + re.escape(name) + r"\b[^;\n]*;"
    matches = re.findall(pattern, source, re.MULTILINE)
    if len(matches) != 1:
        raise AssertionError(f"Expected one declaration of {name}, found {len(matches)}")
    return matches[0] + "\n"


def replace_fixture(text, old, new):
    if text.count(old) != 1:
        raise AssertionError(f"Reader fixture changed: {old[:80]!r}")
    return text.replace(old, new, 1)


def remove_fixture_function(source, name):
    if not function_matches(source, name):
        return source
    return replace_fixture(source, function(source, name), "")


FIXTURE_TYPES = r"""
#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
#include <time.h>
#include <pthread.h>
#include <setjmp.h>
#include <errno.h>
#include "rb_espeak.h"
#define HAVE_ESPEAK
#define CONFIG_RTC 1
#define CONTEXT_CUSTOM 0x20000000
#define CONTEXT_CUSTOM2 0x40000000
#define CONTEXT_STD 1
#define ALLOW_SOFTLOCK 0x08000000
#define LANG_LAST_INDEX_IN_ARRAY ((int)ARRAYLEN(labels))
#define LANG_LAST_VOICEONLY_INDEX_IN_ARRAY 1
#define VOICEONLY_DELIMITER 0
#define UNIT_SHIFT 27
#define DECIMAL_SHIFT 24
#define UNIT_PERCENT 1
#define VOICE_PCM_FRAME_COUNT 512
#define VOICE_EVENT_IS_PLAYING 1
#define Q_VOICE_STOP 1
#define AUDIO_STATUS_PLAY 1
#define LOGFQUEUE(...) do {} while (0)
struct mutex { pthread_mutex_t native; };
struct event_queue { int unused; };
struct queue_event { int unused; };
struct mp3entry { char path[MAX_PATH]; char *title; char id3v2buf[64]; };
static __thread bool owns_tts_mutex;
static void (*after_request_unlock_hook)(void);
static void (*before_request_lock_return_hook)(void);
static void (*snapshot_hook)(void);
static pthread_mutex_t pcm_mutex = PTHREAD_MUTEX_INITIALIZER;
static int pcm_locks;
static size_t pcm_waiting;
static unsigned int voice_thread_id = 1;
static int voice_queue;
static bool voice_playing = true;
static bool voice_pcm_paused;
static uint64_t voice_pcm_elapsed_us;
static void fixture_debug(const char *format, ...);
static int fixture_action(int context, int timeout);
static void test_yield(void);
static void yield(void);
static void test_stop_gate(void);
static bool voice_play_pcm(const short *samples, int count, unsigned int frequency,
                           uint32_t expected);
"""

FIXTURE_BOUNDARIES = r"""
typedef int list_speak_item(int, void *);
#define TIME_BEFORE(first, second) ((first) < (second))
static long current_tick = 100;
struct gui_synclist {
    enum list_position_source position_source;
    bool keyclick, talk_menu, boundary_speech_pending;
    int nb_items, selected_item, selected_size;
    long scheduled_talk_tick, last_talked_tick;
    list_speak_item *callback_speak_item;
    const char *(*callback_get_item_name)(int, void *, char *, size_t);
    void *data;
};
enum { SOUND_LIST_EDGE_BEEP_WRAP, SOUND_LIST_EDGE_BEEP_NOWRAP };
static int boundary_sounds;
static bool keyclick_list_boundary_enabled(void) { return true; }
static void system_sound_play(int sound) { (void)sound; ++boundary_sounds; }
static void mutex_init(struct mutex *value)
{ assert(!pthread_mutex_init(&value->native, NULL)); }
static void mutex_lock(struct mutex *value)
{
    assert(!pthread_mutex_lock(&value->native));
    if (value == &tts_mutex) owns_tts_mutex = true;
    if (value == &tts_request_mutex && before_request_lock_return_hook)
    {
        void (*hook)(void) = before_request_lock_return_hook;
        before_request_lock_return_hook = NULL;
        hook();
    }
}
static void mutex_unlock(struct mutex *value)
{
    if (value == &tts_mutex) owns_tts_mutex = false;
    assert(!pthread_mutex_unlock(&value->native));
    if (value == &tts_request_mutex && after_request_unlock_hook)
    {
        void (*hook)(void) = after_request_unlock_hook;
        after_request_unlock_hook = NULL;
        hook();
    }
}
static bool queue_empty(struct event_queue *value) { (void)value; return true; }
static void queue_post(struct event_queue *value, int id, int data)
{ (void)value; (void)id; (void)data; }
static void pcm_play_lock(void)
{ assert(!owns_tts_mutex); assert(!pthread_mutex_lock(&pcm_mutex)); ++pcm_locks; }
static void pcm_play_unlock(void)
{
    --pcm_locks;
    assert(!pthread_mutex_unlock(&pcm_mutex));
    if (snapshot_hook)
    {
        void (*hook)(void) = snapshot_hook;
        snapshot_hook = NULL;
        hook();
    }
}
static int mixer_channel_status(int channel_id) { (void)channel_id; return channel; }
static size_t mixer_channel_get_bytes_waiting(int channel_id)
{ (void)channel_id; return pcm_waiting; }
static unsigned int mixer_get_frequency(void) { return 48000; }
static void mixer_channel_stop(int channel_id)
{ (void)channel_id; channel = CHANNEL_STOPPED; pcm_waiting = 0; }
static void mixer_channel_play_pause(int channel_id, bool play)
{ (void)channel_id; if (channel) channel = play ? 1 : 2; }
struct mixer_play_cbs { void (*get_more)(const void **, size_t *); };
static void mixer_channel_play_data(int channel_id, const struct mixer_play_cbs *callbacks,
                                   const void *start, size_t length)
{ (void)channel_id; (void)callbacks; (void)start; channel = 1; pcm_waiting = length; }
static void send_event(int id, const bool *audible) { (void)id; (void)audible; }
static int voice_index(int32_t id)
{ return id >= 0 && id < LANG_LAST_INDEX_IN_ARRAY ? id : -1; }
struct queue_entry { int length; };
static bool has_voicefile, need_shutup, force_enqueue_next;
static int talk_handle = 1, index_handle = 1;
static unsigned int queue_write, queue_read, thumbnail_buf_used;
static bool talk_is_disabled(void) { return false; }
static int open_voicefile(void) { return -1; }
static bool load_voicefile_index(int descriptor) { (void)descriptor; return false; }
static bool load_voicefile_data(int descriptor) { (void)descriptor; return false; }
static int load_voicefile_failure(int descriptor) { (void)descriptor; return -1; }
static int get_clip(int32_t id, struct queue_entry *clip)
{ (void)id; (void)clip; return -1; }
static void queue_clip(struct queue_entry *clip, bool enqueue)
{ (void)clip; (void)enqueue; }
static void talk_queue_lock(void) {}
static void talk_queue_unlock(void) {}
static void talk_value_decimal(int32_t id, int32_t unit, int decimals, bool enqueue)
{ (void)id; (void)unit; (void)decimals; (void)enqueue; }
void talk_force_shutup(void);
void talk_shutup(void);
int talk_id(int32_t id, bool enqueue);
static void do_enqueue(bool enqueue);
static bool talk_menus_enabled(const void *settings)
{ (void)settings; return global_settings.tts_enabled; }
static bool rtc_valid = true;
static struct tm fixture_time = { .tm_hour = 12, .tm_min = 34, .tm_year = 126 };
static struct tm notice_time_snapshot, notice_date_snapshot;
static int notice_clock_reads, notice_validations, notice_time_calls, notice_date_calls;
static int notice_battery_reads, notice_peek_calls;
static bool notice_track_available;
static struct tm *get_time(void) { ++notice_clock_reads; return &fixture_time; }
static bool valid_time(const struct tm *value)
{ ++notice_validations; return value && rtc_valid; }
static void talk_time(const struct tm *value, bool enqueue)
{
    assert(value != &fixture_time);
    ++notice_time_calls;
    notice_time_snapshot = *value;
    talk_id(LANG_UNKNOWN, enqueue);
}
static void talk_date(const struct tm *value, bool enqueue)
{
    assert(value != &fixture_time);
    ++notice_date_calls;
    notice_date_snapshot = *value;
    talk_id(LANG_UNKNOWN, enqueue);
}
static bool audio_peek_track(struct mp3entry *track, int offset)
{
    ++notice_peek_calls;
    assert(offset == 0);
    if (!notice_track_available) return false;
    snprintf(track->path, sizeof(track->path), "%s", "/music/notice.mp3");
    snprintf(track->id3v2buf, sizeof(track->id3v2buf), "%s", "Owned track");
    track->title = track->id3v2buf;
    return true;
}
static int talk_spell(const char *text, bool enqueue)
{
    do_enqueue(enqueue);
    force_enqueue_next = false;
    int result = tts_speak(text, strlen(text), true);
    need_shutup = result >= 0;
    return result;
}
static int audio_status(void);
static int battery_level(void) { ++notice_battery_reads; return 75; }
static void talk_value(int value, int unit, bool enqueue)
{ (void)value; (void)unit; talk_id(LANG_UNKNOWN, enqueue); }
static void screen_state_load(void) {}
"""

VOICE_QUEUE = r"""
static intptr_t queue_send(int *queue, int id, intptr_t data)
{
    (void)queue; (void)data;
    assert(id == Q_VOICE_STOP);
    pcm_play_lock();
    voice_stop_playback();
    pcm_play_unlock();
    test_stop_gate();
    return 0;
}
"""

HARNESS_CHECKS = r"""
static jmp_buf worker_exit;
static int worker_budget;
static int worker_waits;
static bool voice_failure;
static bool synthesis_failure;
static bool output_failure;
static bool silent_synthesis;
static bool status_initialization_success = true;
static unsigned int status_initializations;
static unsigned int synth_calls;
static void (*synthesis_hook)(void);
static struct synthesis_context saved_context;
static char saved_text[TTS_TEXT_SIZE];
/* Observe every synthesis separately; stale tracked callback tests keep saved_text. */
static char synthesized_text[TTS_TEXT_SIZE];
static bool synthesized_tracked;
static unsigned int synthesized_text_count;
static bool loop_mode;
static int loop_index;
static int loop_kind;
static unsigned long long last_cursor;
static bool saw_four;
static int boosts;
static pthread_mutex_t stop_gate_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t stop_gate_condition = PTHREAD_COND_INITIALIZER;
static bool stop_gate_enabled, stop_gate_waiting, stop_gate_release;
static bool submit_started, submit_done;

bool tts_init(void)
{
    ++status_initializations;
    initialized = status_initialization_success;
    catalog_ready = false;
    return false;
}

static void test_stop_gate(void)
{
    assert(!pthread_mutex_lock(&stop_gate_mutex));
    if (stop_gate_enabled)
    {
        stop_gate_enabled = false;
        stop_gate_waiting = true;
        assert(!pthread_cond_broadcast(&stop_gate_condition));
        while (!stop_gate_release)
            assert(!pthread_cond_wait(&stop_gate_condition, &stop_gate_mutex));
    }
    assert(!pthread_mutex_unlock(&stop_gate_mutex));
}

static void *stop_thread(void *unused)
{
    (void)unused;
    tts_stop();
    return NULL;
}

static void *submit_thread(void *unused)
{
    (void)unused;
    assert(!pthread_mutex_lock(&stop_gate_mutex));
    submit_started = true;
    assert(!pthread_cond_broadcast(&stop_gate_condition));
    assert(!pthread_mutex_unlock(&stop_gate_mutex));
    assert(tts_speak_tracked("replacement", 11) == 0);
    assert(!pthread_mutex_lock(&stop_gate_mutex));
    submit_done = true;
    assert(!pthread_cond_broadcast(&stop_gate_condition));
    assert(!pthread_mutex_unlock(&stop_gate_mutex));
    return NULL;
}

static void fixture_debug(const char *format, ...)
{
    char message[256];
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(message, sizeof(message), format, arguments);
    va_end(arguments);
    unsigned long long cursor;
    if (sscanf(message, "TTS reader cursor: %llu", &cursor) == 1)
    {
        last_cursor = cursor;
        if (cursor == 4) saw_four = true;
        printf("CURSOR %llu\n", cursor);
    }
}

static void test_yield(void)
{
    ++yields;
    if (!synthesizing && worker_budget > 0 && --worker_budget == 0)
        longjmp(worker_exit, 1);
}

static void queue_wait(struct event_queue *queue, struct queue_event *event)
{
    (void)queue;
    (void)event;
    if (worker_waits++) longjmp(worker_exit, 1);
}

static bool resolve_voice(char *language, char *variant)
{
    strcpy(language, "en");
    variant[0] = '\0';
    return !voice_failure;
}

static void cpu_boost(bool enabled) { boosts += enabled ? 1 : -1; }
static int audio_status(void) { return 1; }

static bool voice_play_pcm(const short *samples, int count, unsigned int frequency,
                           uint32_t expected)
{
    (void)samples;
    assert(frequency == 48000);
    if (output_failure || tts_request_cancelled(expected)) return false;
    if (count > 0)
    {
        pcm_play_lock();
        assert(voice_unplayed_frames() < VOICE_FRAMES);
        voice_buf_commit(count);
        voice_start_playback();
        pcm_play_unlock();
    }
    return true;
}

int rb_espeak_synth_tracked(const char *text, const char *language,
    const char *variant, int rate, int pitch, int volume, int range, int wordgap,
    int punctuation, rb_espeak_callback callback,
    rb_espeak_position_callback position_callback, void *context)
{
    (void)language; (void)variant; (void)rate; (void)pitch; (void)volume;
    (void)range; (void)wordgap; (void)punctuation;
    ++synth_calls;
    snprintf(synthesized_text, sizeof(synthesized_text), "%s", text);
    synthesized_tracked = position_callback != NULL;
    ++synthesized_text_count;
    if (position_callback)
    {
        position_callback(1, 0, context);
        position_callback(3, 2, context);
        position_callback(5, 4, context);
        saved_context = *(struct synthesis_context *)context;
        snprintf(saved_text, sizeof(saved_text), "%s", text);
        saved_context.text = saved_text;
    }
    static const short samples[480] = {0};
    int result = callback(silent_synthesis ? NULL : samples, silent_synthesis ? 0 : 480, context);
    if (synthesis_hook)
    {
        void (*hook)(void) = synthesis_hook;
        synthesis_hook = NULL;
        hook();
    }
    return synthesis_failure ? -1 : result;
}

int rb_espeak_synth_character(uint32_t character, const char *language,
    const char *variant, int rate, int pitch, int volume, int range, int wordgap,
    rb_espeak_callback callback, void *context)
{
    (void)character;
    return rb_espeak_synth_tracked("character", language, variant, rate, pitch,
        volume, range, wordgap, 0, callback, NULL, context);
}

__ACTUAL_WORKER__

static void run_worker(int budget)
{
    worker_budget = budget;
    worker_waits = 0;
    if (!setjmp(worker_exit)) tts_worker();
    assert(!synthesizing && boosts == 0);
}

static void consume_frame(void)
{
    pcm_play_lock();
    assert(voice_unplayed_frames());
    const void *start = NULL;
    size_t length = 0;
    voice_pcm_callback(&start, &length);
    pcm_waiting = length;
    channel = length ? 1 : CHANNEL_STOPPED;
    pcm_play_unlock();
}

static void drain_pcm(void)
{
    assert(!voice_pcm_paused);
    for (unsigned int index = 0; voice_unplayed_frames(); ++index)
    {
        assert(index < VOICE_FRAMES);
        consume_frame();
    }
}

static void audible_us(uint64_t microseconds)
{
    assert(voice_unplayed_frames() && !voice_pcm_paused);
    struct voice_pcm_frame *frame = &voice_buf->frames[voice_buf->frame_out % VOICE_FRAMES];
    assert(microseconds <= (uint64_t)frame->size * 250000 / frame->frequency);
    pcm_waiting = frame->size - microseconds * frame->frequency / 250000;
}

static void notice(int kind)
{
    if (kind == 0) accessibility_speak_time(false);
    else accessibility_screen_lock_changed(kind == 1);
    printf("NOTICE kind=%d generation=%u position=%zu interrupted=%d\n",
        kind, generation, tts_read_position(), tts_read_interrupted());
}

static int fixture_action(int context, int timeout)
{
    (void)context;
    if (!loop_mode) return timeout == TIMEOUT_NOBLOCK ? ACTION_NONE : ACTION_STD_CANCEL;
    assert(loop_index < 8);
    switch (loop_index++)
    {
        case 0: run_worker(1); audible_us(5000); return ACTION_NONE;
        case 1: notice(0); return ACTION_NONE;
        case 2: notice(loop_kind); return loop_kind ? ACTION_REDRAW : ACTION_NONE;
        case 3: run_worker(1); drain_pcm(); return ACTION_NONE;
        default: return ACTION_STD_CANCEL;
    }
}

static void setup(void)
{
    static unsigned char book[800];
    for (size_t index = 0; index < sizeof(book); ++index) book[index] = "one "[index % 4];
    mutex_init(&tts_mutex);
    mutex_init(&tts_request_mutex);
    initialized = catalog_ready = true;
    test_reset(book, sizeof(book));
    global_settings.tts_enabled = true;
    global_settings.tts_announce_position = TTS_POSITION_OFF;
    generation = pending_count = queue_head = 0;
    synthesized_text[0] = '\0';
    synthesized_tracked = false;
    synthesized_text_count = 0;
    read_mark_count = read_mark_cursor = read_offset = 0;
    need_shutup = force_enqueue_next = false;
    for (size_t index = 0; index < ARRAYLEN(voice_offsets); ++index) voice_offsets[index] = UINT32_MAX;
    memset(&voice_storage, 0, sizeof(voice_storage));
    voice_buf = &voice_storage;
    voice_pcm_elapsed_us = pcm_waiting = 0;
    voice_pcm_paused = false;
    sample_rate = 48000;
}

static void start_reader(void)
{
    reader_step(&reader);
    assert(reader.submitted && reader.next == 768);
    run_worker(1);
    audible_us(5000);
    reader_step(&reader);
    assert(reader.cursor == 4);
}

static void screen_notice_scenario(const char *scenario)
{
    bool summary = strstr(scenario, "summary") != NULL;
    bool paused = strstr(scenario, "paused") != NULL;
    bool invalid = strstr(scenario, "invalid") != NULL;
    bool disabled = strstr(scenario, "disabled") != NULL;
    bool twice = strstr(scenario, "twice") != NULL;
    bool unprimed = strstr(scenario, "unprimed") != NULL;
    notice_track_available = strstr(scenario, "unknown") == NULL;
    if (!unprimed)
    {
        talk_id(LANG_CURRENT_TIME, false);
        run_worker(1);
        drain_pcm();
        assert(need_shutup && !force_enqueue_next);
    }
    start_reader();
    if (paused)
    {
        reader_toggle(&reader);
        assert(reader.state == READER_PAUSED && reader.cursor == 4);
    }
    notice_clock_reads = notice_validations = notice_time_calls = notice_date_calls = 0;
    notice_battery_reads = notice_peek_calls = 0;
    rtc_valid = !invalid;
    global_settings.tts_enabled = !disabled;
    uint32_t original_generation = generation;
    if (summary) accessibility_speak_summary(false);
    else assert(accessibility_speak_date(false) == (!invalid && !disabled));
    if (disabled)
    {
        assert(generation == original_generation && pending_count == 0);
        assert(!tts_read_interrupted() && reader.cursor == 4 && reader.submitted);
        assert(!notice_clock_reads && !notice_validations && !notice_peek_calls && !notice_battery_reads);
        global_settings.tts_enabled = true;
        printf("RESULT disabled notice cursor=%lld expected=4\n", (long long)reader.cursor);
        return;
    }
    const int expected_summary[] = {LANG_TRACK, LANG_UNKNOWN, LANG_CURRENT_TIME, LANG_UNKNOWN,
        LANG_DATE, LANG_UNKNOWN, LANG_BATTERY_CHARGE, LANG_UNKNOWN};
    const int expected_date[] = {LANG_DATE, LANG_UNKNOWN};
    unsigned int count = summary ? ARRAYLEN(expected_summary) : ARRAYLEN(expected_date);
    if (unprimed)
    {
        assert(generation == original_generation && !tts_read_interrupted());
        assert(tts_read_position() == 4 && need_shutup);
        printf("RESULT unprimed first notice appended position=4\n");
        if (summary) accessibility_speak_summary(false);
        else assert(accessibility_speak_date(false));
    }
    if (twice) accessibility_speak_summary(true);
    assert(pending_count == count * (twice ? 2 : 1));
    for (unsigned int index = 0; index < pending_count; ++index)
    {
        unsigned int slot = (queue_head + index) % TTS_QUEUE_COUNT;
        const char *expected = summary ? labels[expected_summary[index % count]] : labels[expected_date[index]];
        if (summary && index % count == 1 && notice_track_available) expected = "Owned track";
        assert(!strcmp(text_queue[slot], expected));
        assert(!tracked_queue[slot]);
        printf("NOTICE FIELD %u %s\n", index, text_queue[slot]);
    }
    assert(notice_clock_reads == (twice || unprimed ? 2 : 1) && notice_validations == notice_clock_reads);
    assert(notice_date_calls == (!invalid ? notice_clock_reads : 0));
    assert(notice_time_calls == (summary && !invalid ? notice_clock_reads : 0));
    assert(notice_battery_reads == (summary ? notice_clock_reads : 0));
    assert(notice_peek_calls == (summary ? notice_clock_reads : 0));
    if (summary && !invalid)
        assert(notice_time_snapshot.tm_year == notice_date_snapshot.tm_year &&
               notice_time_snapshot.tm_mon == notice_date_snapshot.tm_mon &&
               notice_time_snapshot.tm_mday == notice_date_snapshot.tm_mday &&
               notice_time_snapshot.tm_hour == notice_date_snapshot.tm_hour &&
               notice_time_snapshot.tm_min == notice_date_snapshot.tm_min);
    assert(tts_read_interrupted() && tts_read_position() == 4 && reader.cursor == 4);
    for (unsigned int index = 0; pending_count || voice_unplayed_frames(); ++index)
    {
        assert(index < TTS_QUEUE_COUNT * 2);
        if (pending_count) run_worker(1);
        if (voice_unplayed_frames()) drain_pcm();
    }
    assert(tts_read_interrupted() && tts_read_position() == 4);
    if (paused)
    {
        reader_step(&reader);
        assert(reader.state == READER_PAUSED && reader.cursor == 4);
        printf("RESULT user-paused cursor=%lld expected=4\n", (long long)reader.cursor);
        reader_toggle(&reader);
    }
    reader_step(&reader);
    assert(reader.state == READER_READING && reader.cursor == 4 && reader.start == 4 && reader.submitted);
    assert(reader.next == 772 && !tts_read_interrupted());
    printf("RESULT resumed cursor=%lld start=%lld next=%lld expected=4\n",
        (long long)reader.cursor, (long long)reader.start, (long long)reader.next);
}

static void repeated_notices(void)
{
    notice(0);
    notice(0);
    run_worker(1);
    drain_pcm();
}

static void interrupt_in_synthesis(void)
{
    audible_us(5000);
    tts_stop();
    assert(tts_read_position() == 4);
    assert(tts_read_interrupted());
}

static void replace_during_snapshot(void)
{
    assert(tts_speak_tracked("new text", 8) == 0);
    run_worker(1);
    assert(tts_read_position() == 0);
}

static void newer_error_during_synthesis(void)
{
    tts_stop();
    last_error = "newer error";
}

static void replace_after_stop_release(void)
{
    assert(tts_speak_tracked("replacement", 11) == 0);
    run_worker(1);
    assert(voice_unplayed_frames() == 1 && !tts_read_interrupted());
}

static void disable_speech_at_request_lock(void)
{
    global_settings.tts_enabled = false;
}

static void invalidate_catalog_at_request_lock(void)
{
    catalog_ready = false;
}

int main(int argc, char **argv)
{
    setbuf(stdout, NULL);
    assert(argc == 2);
    const char *scenario = argv[1];
    setup();
    if (!strcmp(scenario, "reader_search_result_queue"))
    {
        start_reader();
        test_edit("one", 0, false);
        test_menu_choice(7);
        assert(!reader_menu(&reader));
        assert(reader.cursor == 4 && reader.state == READER_PAUSED);
        assert(!reader.submitted && reader.feedback && pending_count == 1);
        assert(!strcmp(reader.job->accepted_query, "one"));
        unsigned int before_result = synthesized_text_count;
        run_worker(1);
        assert(synthesized_text_count == before_result + 1 && !synthesized_tracked);
        assert(strstr(synthesized_text, "Text found") && voice_unplayed_frames() > 0);
        assert(!strncmp(saved_text, "one ", 4)); /* tracked callback context stays intact */
        drain_pcm();
        reader_step(&reader);
        assert(reader.cursor == 4 && reader.state == READER_PAUSED);
        reader_toggle(&reader);
        reader_step(&reader);
        assert(reader.submitted && tts_read_position() == 0);
    }
    else if (!strcmp(scenario, "reader_search_result_rejected"))
    {
        start_reader();
        reader_interrupt(&reader);
        strcpy(reader.job->accepted_query, "one");
        strcpy(reader.job->edit, "ne");
        reader.job->new_query = true;
        assert(reader_stage_result(&reader, 5, LANG_TTS_FOUND, NULL) == 1);
        talk_force_shutup();
        global_settings.tts_enabled = false;
        assert(reader_commit_result(&reader) < 0);
        assert(reader.cursor == 4 && !reader.job->ready && !pending_count);
        assert(!strcmp(reader.job->accepted_query, "one"));
    }
    else if (!strncmp(scenario, "screen_", 7))
        screen_notice_scenario(scenario);
    else if (!strncmp(scenario, "status_", 7))
    {
        bool reader_position = !strcmp(scenario, "status_reader_position") ||
            !strcmp(scenario, "status_group_reader_position");
        if (reader_position)
            start_reader();
        global_settings.tts_enabled = false;
        assert(!tts_is_available() && !tts_output_uses_synthesis());
        assert(tts_speak("ordinary menu", 13, false) == -1);
        bool grouped = !strncmp(scenario, "status_group", 12);
        const int32_t status_ids[] = {LANG_CURRENT_TIME, LANG_BATTERY_CHARGE};
        if (!strcmp(scenario, "status_group_invalid"))
        {
            initialized = false;
            const int32_t invalid[] = {LANG_CURRENT_TIME, -1};
            const int32_t too_high[] = {LANG_LAST_INDEX_IN_ARRAY};
            assert(tts_speak_status_ids(NULL, 1) == -1);
            assert(tts_speak_status_ids(status_ids, 0) == -1);
            assert(tts_speak_status_ids(status_ids, 9) == -1);
            assert(tts_speak_status_ids(invalid, 2) == -1);
            assert(tts_speak_status_ids(too_high, 1) == -1);
            assert(!status_initializations && !pending_count && !status_output);
        }
        else if (!strcmp(scenario, "status_group_overflow"))
        {
            initialized = false;
            const char *saved = labels[LANG_CURRENT_TIME];
            char long_label[513];
            memset(long_label, 'a', sizeof(long_label) - 1);
            long_label[sizeof(long_label) - 1] = '\0';
            labels[LANG_CURRENT_TIME] = long_label;
            assert(tts_speak_status_ids(status_ids, 2) == -1);
            labels[LANG_CURRENT_TIME] = saved;
            assert(!status_initializations && !pending_count && !status_output);
        }
        else if (!strcmp(scenario, "status_invalid_ids"))
        {
            initialized = false;
            assert(tts_speak_status(-1) == -1);
            assert(tts_speak_status(LANG_LAST_INDEX_IN_ARRAY) == -1);
            assert(status_initializations == 0 && pending_count == 0 && !status_output);
        }
        else if (!strcmp(scenario, "status_initialization_failure") ||
                 !strcmp(scenario, "status_group_initialization_failure"))
        {
            initialized = false;
            status_initialization_success = false;
            assert((grouped ? tts_speak_status_ids(status_ids, 2) :
                             tts_speak_status(LANG_CURRENT_TIME)) == -1);
            assert(status_initializations == 1 && !initialized && !pending_count && !status_output);
        }
        else
        {
            if (!strcmp(scenario, "status_initialization") ||
                !strcmp(scenario, "status_group_initialization"))
                initialized = false;
            if (!strcmp(scenario, "status_missing_catalog"))
                catalog_ready = false;
            uint32_t before = generation;
            if (!strcmp(scenario, "status_group_maximum"))
            {
                const int32_t maximum[] = {LANG_CURRENT_TIME, LANG_CURRENT_TIME, LANG_CURRENT_TIME,
                    LANG_CURRENT_TIME, LANG_CURRENT_TIME, LANG_CURRENT_TIME, LANG_CURRENT_TIME, LANG_CURRENT_TIME};
                assert(tts_speak_status_ids(maximum, 8) == 0);
                assert(!strcmp(text_queue[queue_head],
                    "Current time\nCurrent time\nCurrent time\nCurrent time\nCurrent time\nCurrent time\nCurrent time\nCurrent time"));
            }
            else
                assert((grouped ? tts_speak_status_ids(status_ids, 2) :
                                 tts_speak_status(LANG_CURRENT_TIME)) == 0);
            assert(generation == before + 1 && !global_settings.tts_enabled);
            assert(pending_count == 1 && status_output && tts_output_uses_synthesis());
            assert(!tts_is_available());
            if (strcmp(scenario, "status_group_maximum"))
                assert(!strcmp(text_queue[queue_head], grouped ? "Current time\nBattery" : "Current time"));
            if (reader_position)
                assert(tts_read_position() == 4 && tts_read_interrupted());
            if (!strcmp(scenario, "status_initialization") ||
                !strcmp(scenario, "status_group_initialization"))
                assert(status_initializations == 1 && initialized && !catalog_ready);
            if (!strcmp(scenario, "status_recorded_preemption"))
            {
                uint32_t expected = generation;
                tts_voice_clip_started();
                assert(tts_request_cancelled(expected) && pending_count == 0 && !status_output);
                assert(!tts_output_uses_synthesis() && !global_settings.tts_enabled);
            }
            else
            {
                tts_voice_output_finished();
                assert(status_output);
                synthesizing = true;
                tts_voice_output_finished();
                assert(status_output);
                synthesizing = false;
                silent_synthesis = !strcmp(scenario, "status_silent");
                synthesis_failure = !strcmp(scenario, "status_synthesis_error");
                run_worker(1);
                if (silent_synthesis || synthesis_failure)
                    assert(!status_output && !tts_output_uses_synthesis());
                else
                {
                    assert(status_output && tts_output_uses_synthesis() && voice_unplayed_frames());
                    drain_pcm();
                    tts_voice_output_finished();
                    assert(!status_output && !tts_output_uses_synthesis());
                }
                assert(!global_settings.tts_enabled);
            }
        }
    }
    else if (!strncmp(scenario, "boundary_", 9))
    {
        bool reading = strstr(scenario, "reader") != NULL;
        bool wrap = strstr(scenario, "wrap") != NULL;
        bool inward = strstr(scenario, "inward") != NULL;
        bool recent_row = strstr(scenario, "deferred") != NULL;
        bool position = strstr(scenario, "position") != NULL;
        global_settings.tts_announce_position = position ? TTS_POSITION_EVERYWHERE : TTS_POSITION_OFF;
        const char *wrapped_text[] = {"End of list", "Current time", "1 of 2"};
        const char *inward_text[] = {"Current time", "2 of 2"};
        unsigned int wrapped_count = position ? ARRAYLEN(wrapped_text) : 2;
        if (reading)
        {
            talk_id(LANG_CURRENT_TIME, false);
            run_worker(1);
            drain_pcm();
            start_reader();
        }
        struct gui_synclist list = {.keyclick = true, .talk_menu = true,
            .nb_items = 2, .selected_size = 1, .callback_speak_item = fixture_boundary_row};
        boundary_row_calls = 0;
        boundary_row_item = -1;
        if (recent_row)
            list.last_talked_tick = current_tick;
        global_settings.list_boundary_feedback = 0;
        global_settings.keyclick = 2;
        int presses = wrap ? 1 : 20;
        for (int press = 0; press < presses; ++press)
            edge_beep(&list, wrap, wrap);
        assert(!boundary_row_calls && boundary_row_item == -1);
        if (wrap)
        {
            _gui_synclist_speak_item(&list, true);
            assert(!force_enqueue_next && !list.boundary_speech_pending);
            assert(!list.scheduled_talk_tick && list.last_talked_tick == current_tick);
            assert(boundary_row_calls == 1 && boundary_row_item == 0);
        }
        unsigned int expected = wrap ? wrapped_count : 20;
        assert(boundary_sounds == presses && pending_count == expected);
        for (unsigned int index = 0; index < expected; ++index)
        {
            unsigned int slot = (queue_head + index) % TTS_QUEUE_COUNT;
            const char *text = wrap ? (position ? wrapped_text[index] :
                (index ? "Current time" : "End of list")) : "Start of list";
            assert(!strcmp(text_queue[slot], text) && !tracked_queue[slot]);
        }
        if (inward)
        {
            gui_synclist_clear_boundary_speech(&list);
            assert(!list.boundary_speech_pending && !force_enqueue_next);
            if (wrap)
            {
                assert(pending_count == wrapped_count);
                list.selected_item = 1;
                ++current_tick;
                _gui_synclist_speak_item(&list, false);
                assert(!pending_count && list.scheduled_talk_tick && !force_enqueue_next);
                assert(boundary_row_calls == 1 && boundary_row_item == 0);
                current_tick = list.scheduled_talk_tick + 1;
                _gui_synclist_speak_item(&list, false);
                assert(!list.scheduled_talk_tick && !list.boundary_speech_pending && !force_enqueue_next);
                assert(boundary_row_calls == 2 && boundary_row_item == 1);
            }
            else
            {
                assert(!pending_count);
                assert(talk_id(LANG_CURRENT_TIME, false) == 0);
            }
            expected = position ? ARRAYLEN(inward_text) : 1;
            assert(pending_count == expected);
        }
        else if (recent_row)
        {
            assert(wrap && pending_count == wrapped_count && boundary_row_calls == 1);
            assert(!list.boundary_speech_pending && !list.scheduled_talk_tick);
            assert(!force_enqueue_next && pending_count == expected);
        }
        for (unsigned int index = 0; index < expected; ++index)
        {
            unsigned int slot = (queue_head + index) % TTS_QUEUE_COUNT;
            const char *text = inward ? (position ? inward_text[index] : "Current time") :
                wrap ? (position ? wrapped_text[index] :
                    (index ? "Current time" : "End of list")) : "Start of list";
            assert(!strcmp(text_queue[slot], text) && !tracked_queue[slot]);
        }
        if (reading)
            assert(tts_read_position() == 4 && tts_read_interrupted());
        for (unsigned int index = 0; index < expected; ++index)
        {
            run_worker(1);
            drain_pcm();
        }
        assert(!pending_count && !tts_is_busy() && !force_enqueue_next);
        assert(boundary_row_calls == (wrap ? (inward ? 2 : 1) : 0));
        if (reading)
        {
            assert(tts_read_position() == 4 && tts_read_interrupted());
            size_t marks = read_mark_count;
            receive_position(7, 0, &saved_context);
            assert(read_mark_count == marks);
            assert(receive_audio(NULL, 0, &saved_context) == 1);
            assert(tts_read_position() == 4 && tts_read_interrupted());
        }
    }
    else if (!strcmp(scenario, "loop_time") || !strcmp(scenario, "loop_lock"))
    {
        loop_mode = true;
        loop_kind = !strcmp(scenario, "loop_lock");
        tts_read_file("/example.txt");
        printf("RESULT loop cursor=%llu expected=4\n", last_cursor);
        assert(saw_four && loop_index == 5 && last_cursor == 4);
    }
    else if (!strcmp(scenario, "pending_cancel"))
    {
        reader_step(&reader);
        repeated_notices();
        reader_step(&reader);
        printf("RESULT pending cursor=%lld expected=0\n", (long long)reader.cursor);
        assert(reader.cursor == 0);
    }
    else if (!strcmp(scenario, "paused_unstarted"))
    {
        reader_step(&reader);
        reader_toggle(&reader);
        run_worker(1);
        assert(channel == CHANNEL_STOPPED && voice_unplayed_frames() == 1);
        assert(!tts_is_busy() && voice_pcm_paused);
        tts_stop();
        printf("RESULT paused position=%zu interrupted=%d\n", tts_read_position(), tts_read_interrupted());
        assert(tts_read_interrupted() && tts_read_position() == 0);
        reader_toggle(&reader);
        reader_step(&reader);
        assert(reader.cursor == 0);
    }
    else if (!strcmp(scenario, "active_synthesis"))
    {
        reader_step(&reader);
        synthesis_hook = interrupt_in_synthesis;
        run_worker(1);
        reader_step(&reader);
        assert(reader.cursor == 4);
    }
    else if (!strcmp(scenario, "utf8_repeated"))
    {
        const unsigned char text[] = "\xc4\x85 b c next";
        test_reset(text, sizeof(text) - 1);
        global_settings.tts_enabled = true;
        reader_step(&reader);
        run_worker(1);
        audible_us(3000);
        tts_stop();
        assert(tts_read_position() == 3 && tts_read_interrupted());
        for (int index = 0; index < 8; ++index)
        {
            tts_speak("notice", 6, false);
            run_worker(1);
            drain_pcm();
            tts_stop();
            assert(tts_read_position() == 3 && tts_read_interrupted());
        }
        reader_step(&reader);
        assert(reader.cursor == 3 && !memcmp(reader.text, "b c next", 8));
    }
    else if (!strcmp(scenario, "stale_clock_generation"))
    {
        start_reader();
        audible_us(9000);
        snapshot_hook = replace_during_snapshot;
        assert(tts_read_position() == 0);
        assert(!tts_read_interrupted());
    }
    else if (!strcmp(scenario, "concurrent_stop_submit"))
    {
        start_reader();
        pthread_t stopping, submitting;
        stop_gate_enabled = true;
        assert(!pthread_create(&stopping, NULL, stop_thread, NULL));
        assert(!pthread_mutex_lock(&stop_gate_mutex));
        while (!stop_gate_waiting)
            assert(!pthread_cond_wait(&stop_gate_condition, &stop_gate_mutex));
        assert(!pthread_mutex_unlock(&stop_gate_mutex));
        assert(!pthread_create(&submitting, NULL, submit_thread, NULL));
        assert(!pthread_mutex_lock(&stop_gate_mutex));
        while (!submit_started)
            assert(!pthread_cond_wait(&stop_gate_condition, &stop_gate_mutex));
        struct timespec deadline;
        assert(!clock_gettime(CLOCK_REALTIME, &deadline));
        deadline.tv_nsec += 50000000;
        if (deadline.tv_nsec >= 1000000000) { ++deadline.tv_sec; deadline.tv_nsec -= 1000000000; }
        int waited = 0;
        while (!submit_done && waited != ETIMEDOUT)
            waited = pthread_cond_timedwait(&stop_gate_condition, &stop_gate_mutex, &deadline);
        assert(!submit_done && waited == ETIMEDOUT);
        stop_gate_release = true;
        assert(!pthread_cond_broadcast(&stop_gate_condition));
        assert(!pthread_mutex_unlock(&stop_gate_mutex));
        assert(!pthread_join(stopping, NULL));
        assert(!pthread_join(submitting, NULL));
        assert(submit_done && pending_count == 1 && !tts_read_interrupted());
        run_worker(1);
        assert(voice_unplayed_frames() == 1 && tts_read_position() == 0);
        audible_us(5000);
        assert(tts_read_position() == 4);
    }
    else if (!strcmp(scenario, "stale_worker_result"))
    {
        reader_step(&reader);
        synthesis_hook = newer_error_during_synthesis;
        run_worker(1);
        assert(!strcmp(tts_last_error(), "newer error"));
    }
    else if (!strcmp(scenario, "silent_tracked_drain"))
    {
        reader_step(&reader);
        silent_synthesis = true;
        run_worker(1);
        assert(!voice_unplayed_frames());
        tts_stop();
        assert(!tts_read_interrupted());
        reader_step(&reader);
        assert(reader.cursor == 768);
    }
    else if (!strcmp(scenario, "talk_duplicate_stop"))
    {
        start_reader();
        after_request_unlock_hook = replace_after_stop_release;
        talk_force_shutup();
        printf("RESULT duplicate_stop pending_frames=%u expected=1\n", voice_unplayed_frames());
        assert(after_request_unlock_hook == NULL && voice_unplayed_frames() == 1);
    }
    else if (!strcmp(scenario, "uninitialized_legacy_stop"))
    {
        start_reader();
        initialized = false;
        talk_force_shutup();
        assert(!voice_unplayed_frames() && channel == CHANNEL_STOPPED);
    }
    else if (!strcmp(scenario, "disabled_while_waiting") ||
             !strcmp(scenario, "catalog_invalid_while_waiting"))
    {
        start_reader();
        tts_stop();
        assert(tts_read_position() == 4 && tts_read_interrupted() && !pending_count);
        uint32_t original_generation = generation;
        for (int kind = 0; kind < 4; ++kind)
        {
            global_settings.tts_enabled = catalog_ready = true;
            before_request_lock_return_hook = !strcmp(scenario, "disabled_while_waiting") ?
                disable_speech_at_request_lock : invalidate_catalog_at_request_lock;
            int result = kind == 0 ? tts_speak_tracked("replacement", 11) :
                kind == 1 ? tts_speak_tracked("", 0) :
                tts_speak("notice", 6, kind == 2);
            int request_lock_status = pthread_mutex_trylock(&tts_request_mutex.native);
            if (!request_lock_status) assert(!pthread_mutex_unlock(&tts_request_mutex.native));
            int state_lock_status = pthread_mutex_trylock(&tts_mutex.native);
            if (!state_lock_status) assert(!pthread_mutex_unlock(&tts_mutex.native));
            printf("RESULT availability kind=%d expected=-1 actual=%d pending=%u "
                   "generation=%u original_generation=%u request_lock=%d state_lock=%d\n",
                   kind, result, pending_count, generation, original_generation,
                   request_lock_status, state_lock_status);
            assert(result == -1);
            assert(!pending_count && generation == original_generation);
            assert(!request_lock_status && !state_lock_status);
            assert(!before_request_lock_return_hook);
            assert(tts_read_position() == 4 && tts_read_interrupted());
        }
    }
    else
    {
        start_reader();
        if (!strcmp(scenario, "first_and_force"))
        {
            uint32_t original = generation;
            notice(1);
            notice(0);
            assert(generation == original && !tts_read_interrupted() && reader.cursor == 4);
        }
        else if (!strcmp(scenario, "natural_drain") || !strcmp(scenario, "natural_stop"))
        {
            drain_pcm();
            if (!strcmp(scenario, "natural_stop")) tts_stop();
            assert(!tts_read_interrupted());
            reader_step(&reader);
            assert(reader.cursor == 768);
        }
        else if (!strcmp(scenario, "natural_pause_stop"))
        {
            drain_pcm();
            tts_pause(true);
            tts_stop();
            assert(!tts_read_interrupted());
            reader_step(&reader);
            assert(reader.cursor == 768);
        }
        else if (!strcmp(scenario, "appended_notice_after_drain"))
        {
            notice(0);
            run_worker(1);
            assert(voice_unplayed_frames() == 2);
            consume_frame();
            assert(channel != CHANNEL_STOPPED && voice_unplayed_frames() == 1);
            notice(0);
            assert(!tts_read_interrupted());
            run_worker(1);
            drain_pcm();
            reader_step(&reader);
            assert(reader.cursor == 768);
        }
        else if (!strcmp(scenario, "appended_notice_before_drain"))
        {
            notice(0);
            run_worker(1);
            assert(voice_unplayed_frames() == 2);
            notice(0);
            run_worker(1);
            drain_pcm();
            reader_step(&reader);
            assert(reader.cursor == 4);
        }
        else if (!strcmp(scenario, "pause_resume"))
        {
            uint32_t original = generation;
            reader_toggle(&reader);
            assert(voice_pcm_paused && voice_unplayed_frames() == 1);
            reader_step(&reader);
            reader_toggle(&reader);
            reader_step(&reader);
            assert(reader.cursor == 4 && generation == original && synth_calls == 1);
        }
        else if (!strcmp(scenario, "navigate"))
        {
            reader_navigate(&reader, true);
            assert(reader.cursor == 8 && reader.state == READER_PAUSED);
        }
        else if (!strcmp(scenario, "stale_callbacks"))
        {
            tts_stop();
            assert(tts_read_position() == 4 && tts_read_interrupted());
            receive_position(7, 0, &saved_context);
            assert(receive_audio(NULL, 0, &saved_context) == 1);
            assert(tts_read_position() == 4);
            tts_speak_tracked("replacement", 11);
            receive_position(7, 0, &saved_context);
            assert(tts_read_position() == 0 && !tts_read_interrupted());
        }
        else if (!strcmp(scenario, "new_tracked_only_reset"))
        {
            tts_stop();
            assert(tts_read_position() == 4 && tts_read_interrupted());
            tts_speak_character('x');
            tts_speak("", 0, false);
            assert(tts_read_position() == 4 && tts_read_interrupted());
            assert(tts_speak_tracked("new", 3) == 0);
            assert(tts_read_position() == 0 && !tts_read_interrupted());
            tts_stop();
            assert(tts_read_interrupted());
            assert(tts_speak_tracked("", 0) == 0);
            assert(tts_read_position() == 0 && !tts_read_interrupted());
        }
        else if (!strcmp(scenario, "invalid_queue_full"))
        {
            tts_stop();
            assert(tts_read_position() == 4 && tts_read_interrupted());
            uint32_t original = generation;
            assert(tts_speak_tracked(NULL, 4) < 0);
            assert(tts_speak_tracked("x", TTS_TEXT_SIZE) < 0);
            global_settings.tts_enabled = false;
            assert(tts_speak_tracked("x", 1) < 0);
            global_settings.tts_enabled = true;
            assert(generation == original && tts_read_position() == 4 && tts_read_interrupted());
            for (int index = 0; index < TTS_QUEUE_COUNT; ++index) assert(tts_speak("x", 1, true) == 0);
            assert(tts_speak("overflow", 8, true) < 0);
            assert(!strcmp(tts_last_error(), "Speech queue is full"));
            assert(tts_read_position() == 4 && tts_read_interrupted());
        }
        else if (!strcmp(scenario, "synthesis_error") || !strcmp(scenario, "output_error") ||
                 !strcmp(scenario, "voice_error"))
        {
            drain_pcm();
            reader_step(&reader);
            synthesis_failure = !strcmp(scenario, "synthesis_error");
            output_failure = !strcmp(scenario, "output_error");
            voice_failure = !strcmp(scenario, "voice_error");
            run_worker(1);
            drain_pcm();
            reader_step(&reader);
            assert(reader.state == READER_FAILED && *tts_last_error());
        }
        else
        {
            bool paused_case = !strcmp(scenario, "notice_paused");
            if (paused_case) reader_toggle(&reader);
            notice(0);
            notice(!strcmp(scenario, "time_then_lock") ? 1 : !strcmp(scenario, "time_then_unlock") ? 2 : 0);
            run_worker(1);
            drain_pcm();
            if (!strcmp(scenario, "bookmark"))
            {
                test_menu_choice(1); test_menu_choice(0);
                test_menu_choice(-2); test_menu_choice(-2);
                reader_menu(&reader);
                printf("RESULT bookmark=%lld expected=4\n", (long long)saved_bookmark.offset);
                assert(saved_bookmark.offset == 4);
            }
            else
            {
                if (paused_case) reader_toggle(&reader);
                reader_step(&reader);
                printf("RESULT cursor=%lld expected=4\n", (long long)reader.cursor);
                assert(reader.cursor == 4);
            }
        }
    }
    assert(pcm_locks == 0);
    printf("PASS %s\n", scenario);
    return 0;
}
"""


def harness_source(inputs):
    source = {name: data.decode("utf-8") for name, data in inputs.items()}
    prefix = replace_fixture(READER_PREFIX,
        "#define DEBUGF(...) do { if (0) printf(__VA_ARGS__); } while (0)",
        "static void fixture_debug(const char *format, ...);\n"
        "#define DEBUGF(...) fixture_debug(__VA_ARGS__)")
    prefix = replace_fixture(prefix, "LANG_TTS, LANG_ACCESSIBILITY_EMPTY };",
        "LANG_TTS, LANG_ACCESSIBILITY_EMPTY, LANG_CURRENT_TIME, LANG_UNKNOWN, "
        "LANG_BATTERY_CHARGE, LANG_ACCESSIBILITY_SCREEN_LOCKED, "
        "LANG_ACCESSIBILITY_SCREEN_UNLOCKED, LANG_DATE, LANG_TRACK, "
        "LANG_ACCESSIBILITY_LIST_START, LANG_ACCESSIBILITY_LIST_END, VOICE_OF };")
    prefix = replace_fixture(prefix, '"Reading settings", "eSpeak", "No item" };',
        '"Reading settings", "eSpeak", "No item", "Current time", "clock fields", '
        '"Battery", "Screen locked", "Screen unlocked", "Date", "Track", "Start of list", "End of list", "of" };')
    prefix = replace_fixture(prefix, "int tts_reader_page_lines; } global_settings;",
        "int tts_reader_page_lines; bool tts_enabled; char tts_language[40]; "
        "char tts_variant[40]; int tts_rate; int tts_pitch; int tts_volume; "
        "int tts_range; int tts_wordgap; int tts_punctuation; "
        "int list_boundary_feedback; int keyclick; int tts_announce_position; } global_settings;")
    prefix = replace_fixture(prefix, "static struct { int tts_reader_unit;",
                             "static struct user_settings { int tts_reader_unit;")
    enums = "\n".join(extract_block(text, signature).rstrip() + ";" for text, signature in (
        (source["apps/settings.h"], "enum tts_position_mode\n"),
        (source["apps/gui/list.h"], "enum list_position_source\n")))
    prefix = enums + "\n" + prefix
    prefix = replace_fixture(prefix, "static char last_error[128];", "")
    boundary = prefix.index("static void splash(int ticks, const char *message)\n{")
    head, tail = prefix[:boundary], prefix[boundary:]
    for name in ("tts_is_available", "tts_is_busy", "tts_read_position",
                 "tts_read_interrupted", "tts_pause", "mixer_channel_status",
                 "tts_last_error", "tts_stop", "tts_speak", "tts_speak_tracked",
                 "tts_speak_character"):
        head = remove_fixture_function(head, name)
        tail = remove_fixture_function(tail, name)
    tail = remove_fixture_function(tail, "talk_force_shutup")
    tail = replace_fixture(tail, "static void yield(void) { ++yields; }",
                           "static void yield(void) { test_yield(); }")
    original_action = function(tail, "get_custom_action")
    tail = replace_fixture(tail, original_action,
        "static int get_custom_action(int context, int timeout,\n"
        "const struct button_mapping *(*mapping)(int))\n{\n"
        "    (void)mapping(context); return fixture_action(context, timeout);\n}\n"
        "#ifdef HIBY_R1\nstatic int get_action(int context, int timeout)\n"
        "{ return fixture_action(context, timeout); }\n#endif\n")
    engine = source["apps/tts.c"]
    definitions = engine[engine.index("#define TTS_QUEUE_COUNT"):
                         engine.index("static unsigned int worker_id;")]
    definitions += "\n".join(declaration(engine, name) for name in
                             ("sample_rate", "voice_strings", "voice_offsets", "last_error"))
    voice = source["apps/voice_thread.c"]
    frame_count = re.search(r"^#define VOICE_FRAMES\s+\d+", voice, re.MULTILINE).group()
    frame_signature = re.search(r"struct voice_pcm_frame\s*\{", voice).group()
    frame_type = extract_block(voice, frame_signature).rstrip() + ";\n"
    progress = extract_block(source["apps/voice_thread.h"], "struct voice_pcm_progress").rstrip() + ";\n"
    voice_state = (frame_count + "\n" + frame_type + progress +
        "static struct { unsigned int frame_in, frame_out; "
        "struct voice_pcm_frame frames[VOICE_FRAMES]; } voice_storage;\n"
        "static __typeof__(voice_storage) *voice_buf = &voice_storage;\n")
    pieces = [head, empty_feedback_policy(), FIXTURE_TYPES, source["apps/tts.h"], definitions, voice_state,
              FIXTURE_BOUNDARIES]
    pieces.extend(function(voice, name) for name in (
        "voice_unplayed_frames", "voice_pcm_callback", "voice_start_playback",
        "voice_stop_playback", "voice_buf_commit", "voice_pause_pcm",
        "voice_pcm_elapsed_ms", "voice_pcm_get_progress"))
    pieces.extend((VOICE_QUEUE, function(voice, "voice_play_stop")))
    pieces.extend(function(engine, name) for name in (
        "tts_request_cancelled", "receive_audio", "receive_position",
        "tts_read_update_locked", "tts_read_reset_locked", "tts_read_position",
        "tts_read_interrupted", "tts_pause", "tts_is_available", "tts_output_uses_synthesis",
        "tts_is_busy", "tts_cancel_output_locked", "tts_stop_locked", "tts_voice_clip_started",
        "tts_voice_output_finished", "tts_stop", "tts_speak_queued", "tts_speak",
        "tts_speak_tracked", "tts_speak_character_options", "tts_speak_character", "tts_speak_status",
        "tts_speak_status_ids", "tts_get_voice_text", "tts_speak_id", "tts_last_error"))
    pieces.extend(function(source["apps/talk.c"], name) for name in (
        "talk_force_shutup", "talk_shutup", "do_enqueue", "talk_id", "talk_force_enqueue_next",
        "talk_cancel_enqueue_next"))
    pieces.append("static unsigned int boundary_row_calls;\nstatic int boundary_row_item;\n"
                  "static int fixture_boundary_row(int item, void *data) { "
                  "(void)data; assert(item == 0 || item == 1); "
                  "++boundary_row_calls; boundary_row_item = item; "
                  "return talk_id(LANG_CURRENT_TIME, false); }\n"
                  "static void gui_synclist_talk_text(struct gui_synclist *lists) { "
                  "(void)lists; assert(!\"Expected actual boundary row callback\"); }\n")
    pieces.append(function(source["apps/gui/list.c"], "edge_beep"))
    pieces.append(function(source["apps/gui/list.c"], "gui_synclist_clear_boundary_speech"))
    pieces.append(function(source["apps/settings.h"], "talk_list_position_enabled"))
    pieces.append(function(source["apps/gui/list.c"], "gui_synclist_talk_position"))
    pieces.append(function(source["apps/gui/list.c"], "_gui_synclist_speak_item"))
    screen = source["apps/accessibility_screen.c"]
    pieces.append(screen[screen.index("enum screen_unlock_notice"):
                         screen.index("static bool screen_state_loaded;")])
    pieces.extend(function(screen, name) for name in (
        "screen_clock_snapshot", "screen_speak_clock", "screen_track_name",
        "accessibility_speak_time", "accessibility_speak_date", "accessibility_speak_summary",
        "accessibility_speak_battery", "accessibility_screen_lock_changed"))
    reader = re.sub(r'^#include[^\n]*\n', '\n', source["apps/tts_reader.c"], flags=re.MULTILINE)
    suffix = replace_fixture(READER_SUFFIX, "last_error[0] = '\\0';", 'last_error = "";')
    suffix = replace_fixture(suffix, 'snprintf(last_error, sizeof(last_error), "%s", message);',
                              "last_error = message;")
    mapping = function(suffix, "test_mapping")
    suffix = replace_fixture(suffix, mapping, "#ifndef HIBY_R1\n" + mapping + "\n#endif\n")
    checks = HARNESS_CHECKS.replace("__ACTUAL_WORKER__", function(engine, "tts_worker"))
    pieces.extend((tail, reader, suffix, checks))
    combined = "\n".join(pieces)
    if function(combined, "tts_read_interrupted") != function(engine, "tts_read_interrupted"):
        raise AssertionError("Combined reader fixture must use the real engine interruption accessor")
    return combined


def disable_core_dumps():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_logged(command, log, timeout, environment):
    try:
        result = subprocess.run(command, cwd=log.parent, capture_output=True, text=True,
            timeout=timeout, env=environment, preexec_fn=disable_core_dumps)
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        stderr += f"\nTimed out after {timeout} seconds\n"
        exit_code = None
    log.write_text(shlex.join(command) + "\n" + stdout + stderr, encoding="utf-8")
    return {"exit": exit_code, "log": str(log),
            "ubsan_diagnostic": "runtime error:" in stderr, "stdout": stdout}


class ReaderNoticeHarnessTests(unittest.TestCase):
    def test_reader_notice_fixture_uses_actual_empty_feedback_policy(self):
        inputs = read_sources()
        generated = harness_source(inputs)
        self.assertIn("static enum accessibility_empty_feedback empty_feedback_mode;", generated)
        self.assertEqual(function(generated, "accessibility_empty_speech_enabled").strip(),
                         extract_block(inputs["apps/accessibility.c"].decode("utf-8"),
                                       "bool accessibility_empty_speech_enabled(").strip())

    def test_reader_notice_fixture_uses_actual_position_helper_with_default_off(self):
        inputs = read_sources()
        generated = harness_source(inputs)
        self.assertEqual(function(generated, "gui_synclist_talk_position"),
                         function(inputs["apps/gui/list.c"].decode("utf-8"), "gui_synclist_talk_position"))
        self.assertIn("int tts_announce_position;", generated)
        self.assertIn("global_settings.tts_announce_position = TTS_POSITION_OFF;", function(generated, "setup"))


@unittest.skipUnless(os.name == "posix", "Run the pthread C fixtures under WSL/Linux")
class ReaderNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or not shutil.which(compiler[0]):
            raise unittest.SkipTest("A C compiler is required")
        cls.inputs = read_sources()
        cls.hashes = {name: hashlib.sha256(data).hexdigest() for name, data in cls.inputs.items()}
        cls.results = {}
        cls.variants = {}
        cls.skipped_variants = {}
        destination = project_materials_root(ROOT) / "tts-reader-notice-tests"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = confined_path(destination / stamp, destination)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.environment = dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        temporary = cls.workspace / "compiler-temp"
        temporary.mkdir()
        cls.environment["TMPDIR"] = str(temporary)
        cls.environment["TMP"] = str(temporary)
        cls.environment["TEMP"] = str(temporary)
        cls.provenance = {"source_project": str(ROOT), "source_sha256": cls.hashes,
            "test_module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Actual worker/talk/reader/voice functions; synthetic PCM and controlled scheduling",
            "limitations": ["No actual eSpeak synthesis, hardware, music mixing, GUI or NVDA acceptance",
                "Actual screen notice helpers; clock/date formatting, speech gate, battery and metadata are boundary mocks",
                "Summary metadata copy correctness and localized formatting belong to test_accessibility_screen"]}
        (cls.workspace / "provenance.json").write_text(json.dumps(cls.provenance, indent=2) + "\n")
        source = cls.workspace / "reader-notices.c"
        source.write_text(harness_source(cls.inputs), encoding="utf-8")
        probe = cls.workspace / "compiler-probe.c"
        probe.write_text("int main(void) { return 0; }\n")
        sanitizer_probe = run_logged(compiler + ["-fsanitize=undefined", str(probe),
            "-o", str(cls.workspace / "compiler-probe")], cls.workspace / "ubsan-probe.log", 15, cls.environment)
        for target in ("portable", "hibyr1"):
            for sanitizer in ("ordinary", "ubsan"):
                label = f"{target}-{sanitizer}"
                if sanitizer == "ubsan" and sanitizer_probe["exit"] != 0:
                    cls.skipped_variants[label] = "Compiler lacks usable UBSan support"
                    continue
                binary = cls.workspace / label
                command = compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-function", "-UNDEBUG", "-pthread", "-DUTF8PROC_STATIC",
                    "-I", str(ROOT / "lib/utf8proc"), "-I", str(ROOT / "lib/espeak"),
                    str(source), str(ROOT / "lib/utf8proc/utf8proc.c"), "-o", str(binary)]
                if target == "hibyr1":
                    command.append("-DHIBY_R1")
                if sanitizer == "ubsan":
                    command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
                result = run_logged(command, cls.workspace / f"{label}-compile.log", 45, cls.environment)
                if result["exit"] != 0:
                    raise RuntimeError(f"Reader notice fixture compilation failed: {result['log']}")
                cls.variants[label] = binary
        print("Reader notice evidence:", cls.workspace, flush=True)

    def check_scenario(self, scenario):
        for label in ("portable-ordinary", "portable-ubsan", "hibyr1-ordinary", "hibyr1-ubsan"):
            with self.subTest(variant=label):
                if label in self.skipped_variants:
                    self.skipTest(self.skipped_variants[label])
                result = run_logged([str(self.variants[label]), scenario],
                    self.workspace / f"{label}-{scenario}.log", 8, self.environment)
                self.results[f"{label}/{scenario}"] = {
                    key: value for key, value in result.items() if key != "stdout"}
                self.results[f"{label}/{scenario}"]["pass"] = (
                    result["exit"] == 0 and not result["ubsan_diagnostic"] and
                    f"PASS {scenario}\n" in result["stdout"])
                self.assertEqual(result["exit"], 0, result["log"])
                self.assertFalse(result["ubsan_diagnostic"], result["log"])
                self.assertIn(f"PASS {scenario}\n", result["stdout"], result["log"])

    @classmethod
    def tearDownClass(cls):
        after = {name: hashlib.sha256(data).hexdigest() for name, data in read_sources().items()}
        unchanged = after == cls.hashes
        report = {"cases": cls.results, "skipped_variants": cls.skipped_variants,
            "inputs_unchanged": unchanged, "source_sha256_after": after,
            "all_cases_pass": len(cls.results) == len(SCENARIOS) * len(cls.variants) and
                all(value["pass"] for value in cls.results.values())}
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        manifest = {str(path.relative_to(cls.workspace)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in cls.workspace.rglob("*") if path.is_file()}
        (cls.workspace / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if not unchanged:
            raise AssertionError("Reader notice source inputs changed during validation")


def scenario_test(scenario):
    def test(self):
        self.check_scenario(scenario)
    return test


for scenario_name in SCENARIOS:
    setattr(ReaderNoticeTests, "test_" + scenario_name, scenario_test(scenario_name))


if __name__ == "__main__":
    unittest.main(verbosity=2)
