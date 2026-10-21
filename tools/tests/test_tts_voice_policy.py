"""Run actual speech policy functions in isolated strict-C UBSan harnesses."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import ensure_ignored_directories, project_materials_root
from test_tts_coverage import extract_block


ROOT = Path(__file__).resolve().parents[2]
COMMON = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ARRAYLEN(values) (sizeof(values) / sizeof((values)[0]))
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s line %d: %s\n", scenario, __LINE__, #condition); exit(1); \
} } while (0)
static const char *scenario = "startup";
static unsigned cases;
static bool available;
#ifdef HAVE_ESPEAK
static inline bool tts_is_available(void) { return available; }
#endif
"""

AUDIO_PREFIX = r"""
#define MIX_AMP_UNITY 0x00010000
#define PCM_MIXER_CHAN_VOICE 1
static int amplitude, amplitude_calls, order[16], order_count;
static void mixer_channel_set_amplitude(int channel, int value)
{
    CHECK(channel == PCM_MIXER_CHAN_VOICE);
    CHECK(order_count < (int)ARRAYLEN(order));
    order[order_count++] = 3;
    amplitude = value;
    ++amplitude_calls;
}
#ifdef HAVE_ESPEAK
static struct { int talk_mixer_amp; bool tts_enabled; bool talk_menu; } global_settings;
static bool target_available;
static bool forced_status_output;
static inline bool tts_output_uses_synthesis(void)
{
    return tts_is_available() || forced_status_output;
}
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define VOICE_FRAME_COUNT 320
#define VOICE_PCM_FRAME_COUNT 1920
#define VOICE_EVENT_IS_PLAYING 1
#define QUIET_COUNT 3
enum { DSP_GET_OUT_FREQUENCY, DSP_SET_OUT_FREQUENCY, DSP_FLUSH, DSP_SET_FREQUENCY };
static int quiet_counter;
static bool voice_playing, voice_pcm_paused;
static unsigned output_rate, dsp_rate, input_rate, configurations, frames, events;
static unsigned starts, waits, locks, interrupt_checks, cancel_at, buffer_misses;
static struct { int16_t spx_outbuf[VOICE_FRAME_COUNT]; } storage;
static void *dsp_identity = &storage;
static struct voice_buffer { int16_t spx_outbuf[VOICE_FRAME_COUNT]; } sample_storage;
static struct voice_buffer *voice_buf = &sample_storage;
struct dsp_buffer {
    int remcount, bufcount;
    const int16_t *pin[2];
    int16_t *p16out;
    unsigned proc_mask;
};
struct voice_thread_data {
    void *dsp;
    unsigned pcm_sample_rate;
    struct dsp_buffer src;
    struct dsp_buffer *dst;
};
struct voice_pcm_info {
    const int16_t *samples;
    size_t count;
    unsigned sample_rate;
    uint32_t generation;
};
static bool voice_pcm_interrupted(uint32_t generation)
{
    CHECK(generation == 42);
    return cancel_at != 0 && ++interrupt_checks >= cancel_at;
}
static unsigned mixer_get_frequency(void) { return output_rate; }
static intptr_t dsp_configure(void *dsp, int operation, intptr_t value)
{
    CHECK(dsp == dsp_identity);
    if (operation == DSP_GET_OUT_FREQUENCY)
        return dsp_rate;
    if (operation == DSP_SET_OUT_FREQUENCY) {
        dsp_rate = (unsigned)value;
        ++configurations;
    }
    if (operation == DSP_SET_FREQUENCY)
        input_rate = (unsigned)value;
    return 0;
}
static void trigger_cpu_boost(void) {}
static void send_event(int event, const bool *playing)
{
    CHECK(event == VOICE_EVENT_IS_PLAYING);
    CHECK(*playing == !voice_pcm_paused);
    ++events;
}
static int16_t *voice_buf_get(void)
{
    static int16_t output[VOICE_PCM_FRAME_COUNT * 2];
    if (buffer_misses) { --buffer_misses; return NULL; }
    return output;
}
static void sleep(int ticks) { CHECK(ticks == 0); ++waits; }
static void yield(void) {}
static void pcm_play_lock(void) { CHECK(locks == 0); ++locks; }
static void pcm_play_unlock(void) { CHECK(locks == 1); --locks; }
static void voice_buf_commit(int count)
{
    CHECK(locks == 1);
    CHECK(amplitude == MIX_AMP_UNITY);
    CHECK(amplitude_calls == 1);
    CHECK(count >= 0);
    frames += (unsigned)count;
}
static void voice_start_playback(void)
{
    CHECK(locks == 1);
    CHECK(amplitude == MIX_AMP_UNITY);
    CHECK(amplitude_calls == 1);
    ++starts;
}
static void dsp_process(void *dsp, struct dsp_buffer *source,
                        struct dsp_buffer *target, bool enabled)
{
    CHECK(dsp == dsp_identity && enabled);
    CHECK(source->remcount >= 0 && source->remcount <= VOICE_FRAME_COUNT);
    if (source->remcount) {
        CHECK(source->pin[0] == voice_buf->spx_outbuf);
        CHECK(source->pin[1] == voice_buf->spx_outbuf);
        CHECK(source->pin[0][0] == 123);
    }
    target->remcount = source->remcount;
    target->bufcount -= source->remcount;
    source->remcount = 0;
}
static void tts_stop(void) { order[order_count++] = 1; forced_status_output = false; }
static void talk_init(void) { order[order_count++] = 2; available = target_available; }
static void pcmbuf_update_voice_volume(void) { order[order_count++] = 4; }
#endif
"""

AUDIO_TESTS = r"""
static void reset_audio(void)
{
#ifdef HAVE_ESPEAK
    forced_status_output = false;
#endif
    order_count = amplitude_calls = 0;
    amplitude = -99;
}
static void test_mixer(void)
{
    for (int engine = 0; engine < 2; ++engine)
    for (int percent = 0; percent <= 100; ++percent) {
        reset_audio();
        available = engine != 0;
        voice_set_mixer_level(percent);
        int expected = percent * MIX_AMP_UNITY / 100;
#ifdef HAVE_ESPEAK
        if (available) expected = MIX_AMP_UNITY;
#endif
        CHECK(amplitude == expected);
        CHECK(amplitude_calls == 1 && order_count == 1 && order[0] == 3);
        ++cases;
    }
}
#ifdef HAVE_ESPEAK
static void test_forced_status(void)
{
    for (int legacy = 0; legacy < 2; ++legacy)
    for (int recorded = 0; recorded <= 100; ++recorded) {
        reset_audio();
        available = target_available = false;
        global_settings.talk_mixer_amp = recorded;
        global_settings.tts_enabled = false;
        global_settings.talk_menu = legacy != 0;
        int saved_gain = recorded * MIX_AMP_UNITY / 100;
        voice_set_mixer_level(recorded);
        CHECK(amplitude == saved_gain);
        forced_status_output = true;
        voice_set_mixer_level(recorded);
        CHECK(amplitude == MIX_AMP_UNITY && !available);
        CHECK(!global_settings.tts_enabled && global_settings.talk_menu == (legacy != 0));
        CHECK(global_settings.talk_mixer_amp == recorded);
        forced_status_output = false;
        voice_set_mixer_level(recorded);
        CHECK(amplitude == saved_gain && !available);
        forced_status_output = true;
        order_count = amplitude_calls = 0;
        tts_settings_changed();
        CHECK(!forced_status_output && !available && amplitude == saved_gain);
        CHECK(order_count == 4 && amplitude_calls == 1);
        CHECK(order[0] == 1 && order[1] == 2 && order[2] == 3 && order[3] == 4);
        CHECK(!global_settings.tts_enabled && global_settings.talk_menu == (legacy != 0));
        CHECK(global_settings.talk_mixer_amp == recorded);
        ++cases;
    }
}

static void reset_pcm(struct voice_thread_data *data, int recorded, int quiet)
{
    memset(data, 0, sizeof(*data));
    data->dsp = dsp_identity;
    available = false;
    reset_audio();
    voice_set_mixer_level(recorded);
    CHECK(amplitude == recorded * MIX_AMP_UNITY / 100);
    order_count = amplitude_calls = 0;
    quiet_counter = quiet;
    output_rate = dsp_rate = 44100;
    input_rate = configurations = frames = events = starts = waits = locks = 0;
    interrupt_checks = cancel_at = buffer_misses = 0;
    voice_playing = voice_pcm_paused = false;
}
static bool packet(struct voice_thread_data *data, unsigned rate, size_t count)
{
    int16_t samples[2048];
    CHECK(count <= ARRAYLEN(samples));
    for (size_t sample = 0; sample < count; ++sample) samples[sample] = 123;
    struct voice_pcm_info pcm = {samples, count, rate, 42};
    return voice_process_pcm(data, &pcm);
}
static void test_pcm(void)
{
    static const int levels[] = {0, 25, 100};
    static const size_t counts[] = {1, 319, 320, 321, 640, 1920};
    struct voice_thread_data data;
    for (size_t level = 0; level < ARRAYLEN(levels); ++level)
    for (size_t count = 0; count < ARRAYLEN(counts); ++count)
    for (int quiet = 0; quiet <= QUIET_COUNT; quiet += QUIET_COUNT)
    for (int paused = 0; paused < 2; ++paused) {
        reset_pcm(&data, levels[level], quiet);
        voice_pcm_paused = paused != 0;
        buffer_misses = 1;
        CHECK(packet(&data, 22050, counts[count]));
        CHECK(amplitude == MIX_AMP_UNITY && amplitude_calls == 1);
        CHECK(order_count == 1 && order[0] == 3);
        CHECK(frames == counts[count] && starts > 0 && waits == 1 && locks == 0);
        CHECK(events == (quiet == 0 ? 1u : 0u));
        CHECK(input_rate == 22050 && quiet_counter == QUIET_COUNT);
        ++cases;
    }
}
static void test_pcm_errors(void)
{
    struct voice_thread_data data;
    for (unsigned failure = 0; failure < 5; ++failure) {
        reset_pcm(&data, 25, QUIET_COUNT);
        unsigned rate = 22050;
        if (failure == 0) cancel_at = 1;
        if (failure == 1) output_rate = 0;
        if (failure == 2) rate = 0;
        if (failure == 3) { rate = 1; output_rate = UINT_MAX; }
        if (failure == 4) { rate = UINT_MAX; output_rate = 1; }
        CHECK(!packet(&data, rate, 640));
        CHECK(amplitude_calls == 0 && amplitude == MIX_AMP_UNITY / 4);
        CHECK(frames == 0 && starts == 0 && events == 0 && configurations == 0);
        ++cases;
    }
    reset_pcm(&data, 0, QUIET_COUNT);
    cancel_at = 3;
    CHECK(!packet(&data, 22050, 640));
    CHECK(amplitude_calls == 1 && amplitude == MIX_AMP_UNITY);
    CHECK(frames == VOICE_FRAME_COUNT && starts == 1 && locks == 0);
    CHECK(data.src.remcount == 0 && data.dst == NULL);
    ++cases;
}
static void test_pcm_frequency(void)
{
    static const unsigned rates[] = {16000, 22050, 24000, 32000, 44100,
                                     48000, 64000, 88200, 96000};
    struct voice_thread_data data;
    for (size_t rate = 0; rate < ARRAYLEN(rates); ++rate) {
        reset_pcm(&data, 0, QUIET_COUNT);
        output_rate = rates[rate];
        CHECK(packet(&data, 22050, 640));
        CHECK(dsp_rate == output_rate && input_rate == 22050);
        CHECK(configurations == (output_rate == 44100 ? 0u : 1u));
        CHECK(frames == 640 && amplitude_calls == 1);
        amplitude = 0;
        amplitude_calls = order_count = 0;
        CHECK(packet(&data, 22050, 640));
        CHECK(frames == 1280 && amplitude == MIX_AMP_UNITY && amplitude_calls == 1);
        CHECK(configurations == (output_rate == 44100 ? 0u : 1u));
        ++cases;
    }
}
static void test_settings(void)
{
    for (int previous = 0; previous < 2; ++previous)
    for (int target = 0; target < 2; ++target)
    for (int recorded = 0; recorded <= 100; ++recorded) {
        reset_audio();
        available = previous != 0;
        target_available = target != 0;
        global_settings.talk_mixer_amp = recorded;
        tts_settings_changed();
        CHECK(order_count == 4);
        CHECK(order[0] == 1 && order[1] == 2 && order[2] == 3 && order[3] == 4);
        CHECK(global_settings.talk_mixer_amp == recorded);
        CHECK(amplitude == (target ? MIX_AMP_UNITY : recorded * MIX_AMP_UNITY / 100));
        CHECK(amplitude_calls == 1 && available == target_available);
        ++cases;
    }
}
#endif
int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    if (!strcmp(scenario, "mixer")) test_mixer();
#ifdef HAVE_ESPEAK
    else if (!strcmp(scenario, "pcm")) test_pcm();
    else if (!strcmp(scenario, "pcm-errors")) test_pcm_errors();
    else if (!strcmp(scenario, "pcm-frequency")) test_pcm_frequency();
    else if (!strcmp(scenario, "settings")) test_settings();
    else if (!strcmp(scenario, "forced-status")) test_forced_status();
#endif
    else CHECK(false);
    printf("{\"cases\":%u,\"status\":\"passed\"}\n", cases);
    return 0;
}
"""

TALK_PREFIX = r"""
#define MAX_PATH 512
#define PATH_SEPCH '/'
#define PATH_SEPSTR "/"
#define NULL_TERMINATED ((size_t)-1)
#define LANG_LAST_INDEX_IN_ARRAY 9000
#define QUEUE_SIZE 64
#define QUEUE_LEVEL 0
#define BUTTON_NONE 0
#define IS_SYSEVENT(button) ((button) < 0)
static const char *gobble_path_separators(const char *pointer) { return pointer + strspn(pointer, "/"); }
static const char *gobble_path_component(const char *pointer) { return pointer + strcspn(pointer, "/"); }
#define GOBBLE_PATH_SEPCH gobble_path_separators
#define GOBBLE_PATH_COMP gobble_path_component
typedef uint32_t ucschar_t;
enum { VOICE_CHAR_A = 1000, VOICE_ZERO = 1100, VOICE_MINUS = 1200,
       VOICE_PLUS, VOICE_DOT, VOICE_PAUSE, VOICE_CHAR_SLASH };
enum event_kind { SHUTUP, IDENTIFIER, SYNTHESIS, THUMBNAIL };
struct event { enum event_kind kind; long value; bool enqueue; char text[512]; };
static struct event events[128];
static size_t event_count;
static int talk_temp_disable_count, synthesis_result, thumbnail_result, id_result;
static unsigned decoded;
static bool force_enqueue_next, need_shutup;
static const long *thumbnail_prefix;
static const char *const dir_thumbnail_name = "_dirname.talk";
static const char *const file_thumbnail_ext = ".talk";
static struct { int talk_file, talk_dir; bool talk_file_clip, talk_dir_clip; } global_settings;
static void record(enum event_kind kind, long value, bool enqueue, const char *text, size_t len)
{
    CHECK(event_count < ARRAYLEN(events) && len < sizeof(events[0].text));
    struct event *event = &events[event_count++];
    *event = (struct event){kind, value, enqueue, {0}};
    if (text) memcpy(event->text, text, len);
}
static void talk_shutup(void) { record(SHUTUP, 0, false, NULL, 0); }
static int talk_id(long id, bool enqueue)
{
    if (id == -1)
        return -1;
    if (!enqueue) talk_shutup();
    record(IDENTIFIER, id, enqueue, NULL, 0);
    return id_result;
}
#ifdef HAVE_ESPEAK
static int tts_speak(const char *text, size_t len, bool enqueue)
{
    record(SYNTHESIS, 0, enqueue, text, len);
    return synthesis_result;
}
#endif
static bool check_audio_status(void) { return true; }
static const char *utf8decode(const char *text, ucschar_t *codepoint)
{
    CHECK((unsigned char)*text < 128);
    ++decoded;
    *codepoint = (unsigned char)*text;
    return text + 1;
}
static int button_get(bool block) { (void)block; CHECK(false); return 0; }
static void yield(void) { CHECK(false); }
static int _talk_file(const char *path, const long *prefix, bool enqueue)
{
    thumbnail_prefix = prefix;
    record(THUMBNAIL, 0, enqueue, path, strlen(path));
    return thumbnail_result;
}
"""

TALK_TESTS = r"""
static const long prefixes[] = {7001, 7002, TALK_FINAL_ID};
static const long file_ids[] = {1017, 1004, 1000, 1003, VOICE_PAUSE,
                                 1101, 1102, VOICE_DOT, 1019, 1023, 1019};
static const long directory_ids[] = {1001, 1014, 1014, 1010, 1018};
static bool synthesis_active(void)
{
#ifdef HAVE_ESPEAK
    return available;
#else
    return false;
#endif
}
static void reset_talk(void)
{
    event_count = decoded = 0;
    talk_temp_disable_count = 0;
    thumbnail_result = 57;
    synthesis_result = 17;
    id_result = 0;
    force_enqueue_next = need_shutup = true;
    thumbnail_prefix = NULL;
    memset(&global_settings, 0, sizeof(global_settings));
}
static void expect_event(size_t index, enum event_kind kind, long value, bool enqueue)
{
    CHECK(index < event_count);
    CHECK(events[index].kind == kind && events[index].value == value);
    CHECK(events[index].enqueue == enqueue);
}
static size_t expect_name(size_t offset, const char *name, const long *ids, size_t count,
                          const long *prefix, bool enqueue)
{
    if (prefix) {
        if (!enqueue) expect_event(offset++, SHUTUP, 0, false);
        expect_event(offset++, IDENTIFIER, 7001, true);
        expect_event(offset++, IDENTIFIER, 7002, true);
        enqueue = true;
    }
    if (!enqueue) expect_event(offset++, SHUTUP, 0, false);
    if (synthesis_active()) {
        expect_event(offset, SYNTHESIS, 0, true);
        CHECK(!strcmp(events[offset++].text, name));
        CHECK(decoded == 0 && !force_enqueue_next);
        CHECK(need_shutup == (synthesis_result >= 0));
    } else {
        for (size_t index = 0; index < count; ++index)
            expect_event(offset++, IDENTIFIER, ids[index], true);
    }
    CHECK(offset == event_count);
    return offset;
}
static int invoke(bool directory, const char *path, const long *prefix, bool enqueue)
{
    return directory ? talk_dir_or_spell(path, prefix, enqueue)
                     : talk_file_or_spell("/library", path, prefix, enqueue);
}
static void test_names(void)
{
    static const int clip_results[] = {-7, 0, 57};
    for (int engine = 0; engine < 2; ++engine)
    for (int file_mode = 0; file_mode < 3; ++file_mode)
    for (int directory_mode = 0; directory_mode < 3; ++directory_mode)
    for (int file_clip = 0; file_clip < 2; ++file_clip)
    for (int directory_clip = 0; directory_clip < 2; ++directory_clip)
    for (int directory = 0; directory < 2; ++directory)
    for (int enqueue = 0; enqueue < 2; ++enqueue)
    for (int prefix = 0; prefix < 2; ++prefix)
    for (size_t clip = 0; clip < ARRAYLEN(clip_results); ++clip) {
        reset_talk();
        available = engine != 0;
        global_settings.talk_file = file_mode;
        global_settings.talk_dir = directory_mode;
        global_settings.talk_file_clip = file_clip != 0;
        global_settings.talk_dir_clip = directory_clip != 0;
        thumbnail_result = clip_results[clip];
        const long *selected_prefix = prefix ? prefixes : NULL;
        const char *path = directory ? "/Books///" : "Read 12.txt";
        int result = invoke(directory != 0, path, selected_prefix, enqueue != 0);
        if (synthesis_active()) {
            CHECK(result == synthesis_result);
            expect_name(0, directory ? "Books" : "Read 12.txt", NULL, 0,
                        selected_prefix, enqueue != 0);
        } else {
            CHECK(result == 0);
            size_t offset = 0;
            bool clip_enabled = directory ? directory_clip : file_clip;
            int mode = directory ? directory_mode : file_mode;
            if (clip_enabled) {
                expect_event(offset++, THUMBNAIL, 0, enqueue != 0);
                CHECK(thumbnail_prefix == selected_prefix);
                CHECK(!strcmp(events[0].text, directory ? "/Books///_dirname.talk"
                                                        : "/library/Read 12.txt.talk"));
            }
            if (mode == TALK_SPEAK_SPELL && (!clip_enabled || thumbnail_result <= 0))
                expect_name(offset, directory ? "Books" : "Read 12.txt",
                            directory ? directory_ids : file_ids,
                            directory ? ARRAYLEN(directory_ids) : ARRAYLEN(file_ids),
                            selected_prefix, enqueue != 0);
            else CHECK(event_count == offset);
        }
        ++cases;
    }
}
static void test_paths(void)
{
    static const struct { const char *path, *name; } samples[] = {
        {"Books", "Books"}, {"/Books", "Books"}, {"/parent//Books///", "Books"},
        {"", ""}, {"/", "/"}, {"////", "/"}
    };
    static const long slash_ids[] = {VOICE_CHAR_SLASH};
    for (int engine = 0; engine < 2; ++engine)
    for (int directory = 0; directory < 2; ++directory)
    for (size_t sample = 0; sample < ARRAYLEN(samples); ++sample) {
        reset_talk();
        available = engine != 0;
        global_settings.talk_file = global_settings.talk_dir = TALK_SPEAK_SPELL;
        CHECK(invoke(directory != 0, samples[sample].path, prefixes, false) ==
              (synthesis_active() ? synthesis_result : 0));
        const long *ids = sample < 3 ? directory_ids : slash_ids;
        size_t count = sample < 3 ? ARRAYLEN(directory_ids) : sample == 3 ? 0 : 1;
        expect_name(0, samples[sample].name, ids, count, prefixes, false);
        ++cases;
    }
#ifdef HAVE_ESPEAK
    for (int directory = 0; directory < 2; ++directory) {
        reset_talk();
        available = true;
        CHECK(invoke(directory != 0, "/parent/Zażółć gęślą.txt///", NULL, true) == synthesis_result);
        expect_name(0, "Zażółć gęślą.txt", NULL, 0, NULL, true);
        ++cases;
    }
#endif
}
static void test_errors(void)
{
    static const int results[] = {-37, 0, 19};
    for (int engine = 0; engine < 2; ++engine)
    for (int directory = 0; directory < 2; ++directory)
    for (int enqueue = 0; enqueue < 2; ++enqueue)
    for (int prefix = 0; prefix < 2; ++prefix)
    for (size_t result = 0; result < ARRAYLEN(results); ++result) {
        reset_talk();
        available = engine != 0;
        synthesis_result = results[result];
        global_settings.talk_file = global_settings.talk_dir = TALK_SPEAK_SPELL;
        const long *selected_prefix = prefix ? prefixes : NULL;
        CHECK(invoke(directory != 0, "/parent/Books/", selected_prefix, enqueue != 0) ==
              (synthesis_active() ? synthesis_result : 0));
        expect_name(0, "Books", directory_ids, ARRAYLEN(directory_ids),
                    selected_prefix, enqueue != 0);
        ++cases;
    }
    for (int engine = 0; engine < 2; ++engine)
    for (int directory = 0; directory < 2; ++directory)
    for (int enqueue = 0; enqueue < 2; ++enqueue) {
        reset_talk();
        available = engine != 0;
        talk_temp_disable_count = 1;
        global_settings.talk_file = global_settings.talk_dir = TALK_SPEAK_SPELL;
        CHECK(invoke(directory != 0, "Books", NULL, enqueue != 0) == -1);
        CHECK(event_count == 0 && decoded == 0);
        ++cases;
    }
    reset_talk();
    available = false;
    global_settings.talk_file = TALK_SPEAK_SPELL;
    CHECK(talk_file_or_spell("/library", "Read 12.txt", prefixes, false) == 0);
    CHECK(event_count == 1 + ARRAYLEN(prefixes) - 1 + ARRAYLEN(file_ids));
    ++cases;
    for (int engine = 0; engine < 2; ++engine)
    for (int directory = 0; directory < 2; ++directory) {
        reset_talk();
        available = engine != 0;
        id_result = -51;
        global_settings.talk_file = global_settings.talk_dir = TALK_SPEAK_SPELL;
        CHECK(invoke(directory != 0, "Books", prefixes, false) ==
              (synthesis_active() ? synthesis_result : 0));
        expect_event(0, SHUTUP, 0, false);
        expect_event(1, IDENTIFIER, 7001, true);
        expect_name(2, "Books", directory_ids, ARRAYLEN(directory_ids), NULL, true);
        ++cases;
    }
}
static void test_empty_and_invalid_prefixes(void)
{
    static const long empty[] = {TALK_FINAL_ID};
    static const long silent[] = {-1, TALK_FINAL_ID};
    static const long partial[] = {7001, -1, TALK_FINAL_ID};
    static const long *const samples[] = {empty, silent, partial};
    for (int engine = 0; engine < 2; ++engine)
    for (int directory = 0; directory < 2; ++directory)
    for (int enqueue = 0; enqueue < 2; ++enqueue)
    for (size_t sample = 0; sample < ARRAYLEN(samples); ++sample) {
        reset_talk();
        available = engine != 0;
        global_settings.talk_file = global_settings.talk_dir = TALK_SPEAK_SPELL;
        CHECK(invoke(directory != 0, "Books", samples[sample], enqueue != 0) ==
              (synthesis_active() ? synthesis_result : 0));
        size_t offset = 0;
        if (!enqueue) expect_event(offset++, SHUTUP, 0, false);
        if (sample == 2) expect_event(offset++, IDENTIFIER, 7001, true);
        expect_name(offset, "Books", directory_ids, ARRAYLEN(directory_ids), NULL, true);
        ++cases;
        reset_talk();
        talk_temp_disable_count = 1;
        global_settings.talk_file = global_settings.talk_dir = TALK_SPEAK_SPELL;
        CHECK(invoke(directory != 0, "Books", samples[sample], enqueue != 0) == -1);
        CHECK(event_count == 0);
        ++cases;
    }
}
static void test_talk_file_entry(void)
{
    for (int engine = 0; engine < 2; ++engine)
    for (int directory = 0; directory < 2; ++directory)
    for (int prefix = 0; prefix < 2; ++prefix)
    for (int enqueue = 0; enqueue < 2; ++enqueue) {
        reset_talk();
        available = engine != 0;
        const long *selected_prefix = prefix ? prefixes : NULL;
        int result = talk_file("/library", directory ? "Books" : NULL,
                               directory ? dir_thumbnail_name : "Read 12.txt",
                               directory ? NULL : file_thumbnail_ext,
                               selected_prefix, enqueue != 0);
        if (synthesis_active()) {
            CHECK(result == 1);
            expect_name(0, directory ? "Books" : "Read 12.txt", NULL, 0,
                        selected_prefix, enqueue != 0);
        } else {
            CHECK(result == thumbnail_result && event_count == 1);
            CHECK(thumbnail_prefix == selected_prefix);
            expect_event(0, THUMBNAIL, 0, enqueue != 0);
            CHECK(!strcmp(events[0].text, directory ? "/library/Books/_dirname.talk"
                                                    : "/library/Read 12.txt.talk"));
        }
        ++cases;
    }
#ifdef HAVE_ESPEAK
    reset_talk();
    available = true;
    synthesis_result = -37;
    CHECK(talk_file(NULL, NULL, "Books", NULL, NULL, false) == -1);
    CHECK(talk_file(NULL, NULL, NULL, NULL, NULL, true) == 0);
    CHECK(event_count == 2);
    ++cases;
#endif
}
int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    if (!strcmp(scenario, "names")) test_names();
    else if (!strcmp(scenario, "paths")) test_paths();
    else if (!strcmp(scenario, "errors")) test_errors();
    else if (!strcmp(scenario, "prefixes")) test_empty_and_invalid_prefixes();
    else if (!strcmp(scenario, "talk-file")) test_talk_file_entry();
    else CHECK(false);
    printf("{\"cases\":%u,\"status\":\"passed\"}\n", cases);
    return 0;
}
"""

TREE_PREFIX = r"""
#define MAX_PATH 512
#define MAX_DIR_LEVELS 32
#define AVERAGE_FILENAME_LENGTH 64
#define ATTR_DIRECTORY 0x10
#define FILE_ATTR_THUMBNAIL 0x0080
#define FILE_ATTR_AUDIO 0x0300
enum { SHOW_ALL, SHOW_SUPPORTED, SHOW_MUSIC, SHOW_PLAYLIST, SHOW_ID3DB, NUM_FILTER_MODES };
enum { VOICE_DIR = 500, VOICE_FILE };
enum event_kind { DIR_CLIP, FILE_CLIP, IDENTIFIER, NUMBER, SHUTUP, FILETYPE, NAME };
struct event { enum event_kind kind; long value; bool enqueue; char text[512]; };
struct user_settings {
    bool tts_enabled, talk_menu, talk_filetype, talk_file_clip, talk_dir_clip;
    int talk_file, talk_dir, show_filename_ext;
};
static struct user_settings global_settings;
static struct event events[16];
static size_t event_count;
static int clip_result, directory_filter;
static bool supported;
static char entry_name[MAX_PATH];
static struct entry selected_entry;
static struct tree_context context;
#ifdef HAVE_TAGCACHE
static int custom_action, encoded_id;
#define P2ID(pointer) ((void)(pointer), encoded_id)
#endif
static void record(enum event_kind kind, long value, bool enqueue, const void *text)
{
    CHECK(event_count < ARRAYLEN(events));
    struct event *event = &events[event_count++];
    *event = (struct event){kind, value, enqueue, {0}};
    if (text) {
        CHECK(strlen(text) < sizeof(event->text));
        strcpy(event->text, text);
    }
}
static struct entry *get_valid_entry(const char *function, struct tree_context *data, int index)
{
    CHECK(!strcmp(function, "tree_voice_cb") && data == &context && index >= 0);
    return &selected_entry;
}
static int ft_play_dirname(const void *name)
{
    record(DIR_CLIP, 0, true, name);
    return clip_result;
}
static int ft_play_filename(char *directory, const void *name, int attr)
{
    CHECK(!strcmp(directory, "/library"));
    record(FILE_CLIP, attr, true, name);
    return clip_result;
}
static int talk_id(long identifier, bool enqueue)
{
    record(IDENTIFIER, identifier, enqueue, NULL);
    return 0;
}
static int talk_number(long number, bool enqueue)
{
    record(NUMBER, number, enqueue, NULL);
    return 0;
}
static void talk_shutup(void) { record(SHUTUP, 0, false, NULL); }
static void say_filetype(int attr) { record(FILETYPE, attr, true, NULL); }
static int talk_spell(const void *name, bool enqueue)
{
    record(NAME, 0, enqueue, name);
    return -37;
}
static bool filetype_supported(int attr) { (void)attr; return supported; }
static char *byte_strrchr(const void *name, int character) { return strrchr(name, character); }
#define strrchr byte_strrchr
#ifdef HAVE_TAGCACHE
static int tagtree_get_attr(struct tree_context *data) { CHECK(data == &context); return selected_entry.attr; }
static unsigned char *tagtree_get_entry_name(struct tree_context *data, int index, char *buf, size_t size)
{
    CHECK(data == &context && index >= 0);
    CHECK(strlen(entry_name) < size);
    strcpy(buf, entry_name);
    return (unsigned char *)buf;
}
static int tagtree_get_custom_action(struct tree_context *data) { CHECK(data == &context); return custom_action; }
#endif
"""

TREE_TESTS = r"""
static void reset_tree(bool directory)
{
    memset(&global_settings, 0, sizeof(global_settings));
    memset(&context, 0, sizeof(context));
    event_count = 0;
    clip_result = 1;
    available = false;
    supported = true;
    strcpy(entry_name, directory ? "Books.v1" : "Report.txt");
    selected_entry.name = entry_name;
    selected_entry.attr = directory ? ATTR_DIRECTORY : FILE_ATTR_AUDIO;
    strcpy(context.currdir, "/library");
    directory_filter = SHOW_ALL;
    context.dirfilter = &directory_filter;
    context.dirsindir = 2;
    global_settings.show_filename_ext = 1;
#ifdef HAVE_TAGCACHE
    custom_action = ONPLAY_NO_CUSTOMACTION;
    encoded_id = -1;
#endif
}
static bool synthesis_enabled(void)
{
#ifdef HAVE_ESPEAK
    return global_settings.tts_enabled;
#else
    return false;
#endif
}
static void expect_event(size_t index, enum event_kind kind, long value, bool enqueue)
{
    CHECK(index < event_count);
    CHECK(events[index].kind == kind && events[index].value == value);
    CHECK(events[index].enqueue == enqueue);
}
static void test_tree(void)
{
    static const int clip_results[] = {-7, 0, 1};
    for (int enabled = 0; enabled < 2; ++enabled)
    for (int file_mode = 0; file_mode < 3; ++file_mode)
    for (int directory_mode = 0; directory_mode < 3; ++directory_mode)
    for (int types = 0; types < 2; ++types)
    for (int file_clip = 0; file_clip < 2; ++file_clip)
    for (int directory_clip = 0; directory_clip < 2; ++directory_clip)
    for (int directory = 0; directory < 2; ++directory)
    for (int thumbnail = 0; thumbnail < 2; ++thumbnail)
    for (size_t clip = 0; clip < ARRAYLEN(clip_results); ++clip) {
        reset_tree(directory != 0);
        global_settings.tts_enabled = enabled != 0;
        global_settings.talk_file = file_mode;
        global_settings.talk_dir = directory_mode;
        global_settings.talk_filetype = types != 0;
        global_settings.talk_file_clip = file_clip != 0;
        global_settings.talk_dir_clip = directory_clip != 0;
        if (thumbnail) selected_entry.attr |= FILE_ATTR_THUMBNAIL;
        clip_result = clip_results[clip];
        int selection = directory ? 2 : 5;
        CHECK(tree_voice_cb(selection, &context) == 0);
        size_t offset = 0;
        if (synthesis_enabled()) {
            CHECK(event_count == 1);
            expect_event(offset++, NAME, 0, true);
        } else {
            bool clip_attempt = directory ? directory_clip : file_clip && thumbnail;
            bool did_clip = clip_attempt && clip_result > 0;
            int mode = directory ? directory_mode : file_mode;
            if (clip_attempt)
                expect_event(offset++, directory ? DIR_CLIP : FILE_CLIP,
                             directory ? 0 : selected_entry.attr, true);
            if (!did_clip && mode == 1) {
                expect_event(offset++, IDENTIFIER, directory ? VOICE_DIR : VOICE_FILE, false);
                expect_event(offset++, NUMBER, directory ? 3 : 4, true);
            }
            if (!did_clip && mode == 2) {
                expect_event(offset++, SHUTUP, 0, false);
                if (types && directory) expect_event(offset++, IDENTIFIER, VOICE_DIR, true);
            }
            if (types && !directory) expect_event(offset++, FILETYPE, selected_entry.attr, true);
            if (!did_clip && mode == 2) expect_event(offset++, NAME, 0, true);
            CHECK(event_count == offset);
        }
        for (size_t event = 0; event < event_count; ++event)
            if (events[event].kind == NAME || events[event].kind == DIR_CLIP || events[event].kind == FILE_CLIP)
                CHECK(!strcmp(events[event].text, entry_name));
        CHECK(!strcmp(entry_name, directory ? "Books.v1" : "Report.txt"));
        ++cases;
    }
}
static void test_extensions(void)
{
    static const int filters[] = {SHOW_ALL, SHOW_SUPPORTED, NUM_FILTER_MODES};
    for (int enabled = 0; enabled < 2; ++enabled)
    for (int directory = 0; directory < 2; ++directory)
    for (int extension = 0; extension < 4; ++extension)
    for (int known = 0; known < 2; ++known)
    for (size_t filter = 0; filter < ARRAYLEN(filters); ++filter) {
        reset_tree(directory != 0);
        global_settings.tts_enabled = enabled != 0;
        global_settings.talk_file = global_settings.talk_dir = 2;
        global_settings.show_filename_ext = extension;
        supported = known != 0;
        directory_filter = filters[filter];
        CHECK(tree_voice_cb(5, &context) == 0);
        bool strip = !directory && (extension == 0 || (extension == 2 && known) ||
                                    (extension == 3 && directory_filter != SHOW_ALL));
        size_t name_event = synthesis_enabled() ? 0 : 1;
        CHECK(event_count == name_event + 1);
        expect_event(name_event, NAME, 0, true);
        CHECK(!strcmp(events[name_event].text, directory ? "Books.v1" : strip ? "Report" : "Report.txt"));
        CHECK(!strcmp(entry_name, directory ? "Books.v1" : "Report.txt"));
        ++cases;
    }
}
#ifdef HAVE_TAGCACHE
static void test_database(void)
{
    for (int enabled = 0; enabled < 2; ++enabled)
    for (int menu = 0; menu < 2; ++menu)
    for (int encoded = 0; encoded < 2; ++encoded)
    for (int firstletter = 0; firstletter < 2; ++firstletter) {
        reset_tree(false);
        directory_filter = SHOW_ID3DB;
        global_settings.tts_enabled = enabled != 0;
        global_settings.talk_menu = menu != 0;
        custom_action = firstletter ? ONPLAY_CUSTOMACTION_FIRSTLETTER : ONPLAY_NO_CUSTOMACTION;
        encoded_id = encoded ? 8123 : -1;
        CHECK(tree_voice_cb(5, &context) == 0);
        if (encoded) {
            if (synthesis_enabled() || menu) {
                CHECK(event_count == 1);
                expect_event(0, IDENTIFIER, encoded_id, true);
            } else CHECK(event_count == 0);
        } else if (synthesis_enabled() || firstletter) {
            CHECK(event_count == 1);
            expect_event(0, NAME, 0, true);
            CHECK(!strcmp(events[0].text, "Report.txt"));
        } else CHECK(event_count == 0);
        CHECK(!strcmp(entry_name, "Report.txt"));
        ++cases;
    }
}
#endif
int main(int argc, char **argv)
{
    CHECK(argc == 2);
    scenario = argv[1];
    if (!strcmp(scenario, "tree")) test_tree();
    else if (!strcmp(scenario, "extensions")) test_extensions();
#ifdef HAVE_TAGCACHE
    else if (!strcmp(scenario, "database")) test_database();
#endif
    else CHECK(false);
    printf("{\"cases\":%u,\"status\":\"passed\"}\n", cases);
    return 0;
}
"""


class VoicePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or shutil.which(cls.compiler[0]) is None:
            raise unittest.SkipTest("A GCC-compatible UBSan compiler is required; run under WSL")
        materials = project_materials_root(ROOT)
        ensure_ignored_directories(materials.parent, (materials.name,))
        base = materials / "tts-voice-policy-tests"
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = Path(tempfile.mkdtemp(prefix=stamp + "-", dir=base))
        paths = ("apps/voice_thread.c", "apps/tts.c", "apps/talk.c", "apps/talk.h",
                 "apps/tree.c", "apps/tree.h", "apps/settings.h", "apps/onplay.h",
                 "firmware/common/pathfuncs.c")
        cls.sources = {name: (ROOT / name).read_bytes() for name in paths}
        cls.functions = {}

        def actual(path, signature):
            block = extract_block(cls.sources[path].decode("utf-8"), signature)
            cls.functions[(path, signature)] = block
            return block

        mixer = actual("apps/voice_thread.c", "void voice_set_mixer_level(")
        pcm = actual("apps/voice_thread.c", "static bool voice_process_pcm(")
        settings = actual("apps/tts.c", "void tts_settings_changed(")
        cls.parts = {
            "audio": [COMMON, AUDIO_PREFIX, mixer, "#ifdef HAVE_ESPEAK\n", pcm,
                      settings, "#endif\n", AUDIO_TESTS],
            "talk": [COMMON, TALK_PREFIX,
                     next(line for line in cls.sources["apps/talk.h"].decode("utf-8").splitlines()
                          if line.startswith("#define TALK_FINAL_ID ")) + "\n",
                     actual("apps/talk.h", "enum talk_speakmode") + ";\n",
                     actual("firmware/common/pathfuncs.c", "size_t path_basename("),
                     actual("apps/talk.c", "static bool talk_is_disabled("),
                     actual("apps/talk.c", "static void do_enqueue("),
                     actual("apps/talk.c", "static int _talk_spell("),
                     "int talk_idarray(const long *ids, bool enqueue);\n",
                     actual("apps/talk.c", "static int talk_spell_basename("),
                     actual("apps/talk.c", "int talk_idarray("),
                     actual("apps/talk.c", "int talk_file("),
                     actual("apps/talk.c", "int talk_file_or_spell("),
                     actual("apps/talk.c", "int talk_dir_or_spell("), TALK_TESTS],
            "tree": [COMMON,
                     "#define MAX_PATH 512\n#define MAX_DIR_LEVELS 32\n",
                     actual("apps/onplay.h", "enum onplay_custom_action") + ";\n",
                     actual("apps/tree.h", "struct entry {") + ";\n",
                     actual("apps/tree.h", "struct tree_cache {") + ";\n",
                     actual("apps/tree.h", "struct tree_context {") + ";\n",
                     TREE_PREFIX,
                     actual("apps/settings.h", "static inline bool talk_tts_enabled("),
                     actual("apps/settings.h", "static inline bool talk_menus_enabled("),
                     actual("apps/tree.c", "static bool ext_stripit("),
                     actual("apps/tree.c", "static int tree_voice_cb("), TREE_TESTS],
        }
        cls.compiled = {}
        cls.compile_failures = {}
        cls.runs = []
        cls.provenance = {
            "source_project": str(ROOT),
            "source_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in cls.sources.items()},
            "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "compiler": cls.compiler,
            "compiler_version": subprocess.check_output(
                cls.compiler + ["--version"], text=True, timeout=30).splitlines()[0],
            "extracted_sha256": {path + ":" + signature: hashlib.sha256(block.encode()).hexdigest()
                                 for (path, signature), block in cls.functions.items()},
            "mocked_boundaries": ["TTS availability and synthesis request", "mixer setter and playback",
                                  "DSP, queue, scheduler and PCM cancellation", "thumbnail I/O",
                                  "ASCII UTF-8 decoder, recorded ID dispatch", "tree cache and database"],
            "limits": ["No full build, actual synthesis, voicefiles, DSP output, audio hardware or NVDA",
                       "Path scanning macros use equivalent standard C strspn/strcspn",
                       "Tree char/unsigned-char assignment requires -Wno-pointer-sign; byte-string mocks accept void pointers",
                       "Tree callback retains its existing zero return even when mocked talk_spell fails"],
        }
        (cls.workspace / "provenance.json").write_text(json.dumps(cls.provenance, indent=2), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        stable = {}
        for (path, signature), previous in cls.functions.items():
            current = extract_block((ROOT / path).read_text(encoding="utf-8"), signature)
            stable[path + ":" + signature] = current == previous
        report = {
            **cls.provenance,
            "runs": cls.runs,
            "compilation_failures": {str(key): value for key, value in cls.compile_failures.items()},
            "production_function_stability": stable,
            "production_functions_unchanged_during_run": all(stable.values()),
            "passing_c_cases": sum(run.get("harness", {}).get("cases", 0)
                                   for run in cls.runs if not run["mutation"]),
            "mutation_rejections": sum(run["mutation"] is not None and run["returncode"] == 1
                                       for run in cls.runs),
        }
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Voice policy evidence: " + str(cls.workspace), file=sys.stderr)

    def run_harness(self, family, scenario, standard="c11", espeak=True, tagcache=False,
                    mutation=None, expected_failure=None):
        key = (family, standard, espeak, tagcache, mutation)
        if key in self.compile_failures:
            self.fail(self.compile_failures[key])
        if key not in self.compiled:
            mode = "-".join((family, standard, "espeak" if espeak else "legacy",
                             "tagcache" if tagcache else "files", mutation or "current"))
            directory = self.workspace / mode
            directory.mkdir()
            source = "\n".join(self.parts[family])
            if mutation:
                replacements = {
                    "recorded-gain": ("if (tts_output_uses_synthesis())\n        percent = 100;", "if (false)\n        percent = 100;"),
                    "normal-output-gate": ("if (tts_output_uses_synthesis())\n        percent = 100;", "if (tts_is_available())\n        percent = 100;"),
                    "pcm-gain": ("mixer_channel_set_amplitude(PCM_MIXER_CHAN_VOICE, MIX_AMP_UNITY);", "(void)0;"),
                    "settings-gain": ("voice_set_mixer_level(global_settings.talk_mixer_amp);", "(void)0;"),
                    "filename-policy": ("if (tts_is_available())\n        return talk_spell_basename(filename, prefix_ids, enqueue);", "if (false)\n        return talk_spell_basename(filename, prefix_ids, enqueue);"),
                    "directory-policy": ("if (tts_is_available())\n        return talk_spell_basename(dirname, prefix_ids, enqueue);", "if (false)\n        return talk_spell_basename(dirname, prefix_ids, enqueue);"),
                    "tree-policy": ("bool use_synthesis = talk_tts_enabled(&global_settings);", "bool use_synthesis = false;"),
                    "prefix-replacement": ("do_enqueue(enqueue);\n        talk_idarray(prefix_ids, true);",
                                           "talk_idarray(prefix_ids, enqueue);"),
                }
                before, after = replacements[mutation]
                self.assertEqual(source.count(before), 1, "Mutation must identify exactly one production statement")
                source = source.replace(before, after, 1)
            fixture = directory / "policy.c"
            fixture.write_text(source, encoding="utf-8")
            executable = directory / "policy"
            command = self.compiler + [
                "-std=" + standard, "-pedantic-errors", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                str(fixture), "-o", str(executable),
            ]
            if family == "tree": command.append("-Wno-pointer-sign")
            if espeak: command.append("-DHAVE_ESPEAK")
            if tagcache: command.append("-DHAVE_TAGCACHE")
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (directory / "compile.json").write_text(json.dumps({
                "command": command, "returncode": compiled.returncode,
                "stdout": compiled.stdout, "stderr": compiled.stderr,
                "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            }, indent=2), encoding="utf-8")
            if compiled.returncode:
                self.compile_failures[key] = compiled.stdout + compiled.stderr
                self.fail(self.compile_failures[key])
            self.compiled[key] = (directory, executable)
        directory, executable = self.compiled[key]
        environment = dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        tested = subprocess.run([str(executable), scenario], env=environment,
                                capture_output=True, text=True, timeout=30)
        report = {
            "family": family, "scenario": scenario, "standard": standard, "espeak": espeak,
            "tagcache": tagcache, "mutation": mutation, "returncode": tested.returncode,
            "stdout": tested.stdout, "stderr": tested.stderr,
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        }
        if tested.returncode == 0:
            report["harness"] = json.loads(tested.stdout)
        self.runs.append(report)
        (directory / (scenario + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.assertNotIn("runtime error:", tested.stderr)
        if expected_failure:
            self.assertEqual(tested.returncode, 1, tested.stdout + tested.stderr)
            self.assertIn(expected_failure, tested.stderr)
        else:
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertEqual(report["harness"]["status"], "passed")
            self.assertGreater(report["harness"]["cases"], 0)

    def matrix(self, family, scenario, espeak_only=False, tagcache_modes=(False,)):
        for standard in ("c99", "c11"):
            for espeak in ((True,) if espeak_only else (False, True)):
                for tagcache in tagcache_modes:
                    with self.subTest(standard=standard, espeak=espeak, tagcache=tagcache):
                        self.run_harness(family, scenario, standard, espeak, tagcache)

    def test_mixer_callback_recorded_range_and_available_tts_unity(self):
        self.matrix("audio", "mixer")

    def test_pcm_restores_unity_before_each_commit_and_playback(self):
        self.matrix("audio", "pcm", espeak_only=True)

    def test_pcm_invalid_rates_and_cancellation(self):
        self.matrix("audio", "pcm-errors", espeak_only=True)

    def test_pcm_quiet_tail_frequency_and_contiguous_packets(self):
        self.matrix("audio", "pcm-frequency", espeak_only=True)

    def test_settings_change_reapplies_saved_gain_after_stop_and_init(self):
        self.matrix("audio", "settings", espeak_only=True)

    def test_forced_status_bypasses_only_recorded_gain_and_restores_saved_preferences(self):
        self.matrix("audio", "forced-status", espeak_only=True)

    def test_normal_availability_mutant_passes_ordinary_cases_but_fails_forced_status(self):
        for standard in ("c99", "c11"):
            with self.subTest(standard=standard):
                self.run_harness("audio", "mixer", standard=standard, mutation="normal-output-gate")
                self.run_harness("audio", "forced-status", standard=standard, mutation="normal-output-gate",
                                 expected_failure="amplitude == MIX_AMP_UNITY")

    def test_file_and_directory_all_modes_clip_flags_prefixes_and_enqueue(self):
        self.matrix("talk", "names")

    def test_basename_roots_trailing_slashes_and_utf8(self):
        self.matrix("talk", "paths")

    def test_name_synthesis_errors_disabled_and_legacy_returns(self):
        self.matrix("talk", "errors")

    def test_empty_invalid_and_partial_prefixes_preserve_replacement(self):
        self.matrix("talk", "prefixes")

    def test_actual_talk_file_synthesis_and_thumbnail_dispatch(self):
        self.matrix("talk", "talk-file")

    def test_tree_all_modes_types_thumbnails_and_clip_results(self):
        self.matrix("tree", "tree", tagcache_modes=(False, True))

    def test_tree_extension_policy_and_name_restoration(self):
        self.matrix("tree", "extensions", tagcache_modes=(False, True))

    def test_tree_database_labels_and_firstletter_custom_action(self):
        self.matrix("tree", "database", tagcache_modes=(True,))

    def test_reject_recorded_gain_for_available_tts(self):
        self.run_harness("audio", "mixer", mutation="recorded-gain", expected_failure="amplitude == expected")

    def test_reject_pcm_without_explicit_unity(self):
        self.run_harness("audio", "pcm", mutation="pcm-gain", expected_failure="amplitude == MIX_AMP_UNITY")

    def test_reject_settings_without_mixer_refresh(self):
        self.run_harness("audio", "settings", mutation="settings-gain", expected_failure="order_count == 4")

    def test_reject_filename_gated_by_legacy_settings(self):
        self.run_harness("talk", "names", mutation="filename-policy", expected_failure="result == synthesis_result")

    def test_reject_directory_gated_by_legacy_settings(self):
        self.run_harness("talk", "names", mutation="directory-policy", expected_failure="result == synthesis_result")

    def test_reject_tree_gated_by_legacy_settings(self):
        self.run_harness("tree", "tree", mutation="tree-policy", expected_failure="event_count == 1")

    def test_reject_prefix_that_loses_requested_replacement(self):
        self.run_harness("talk", "prefixes", mutation="prefix-replacement",
                         expected_failure="events[index].kind == kind")


if __name__ == "__main__":
    suite_result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(VoicePolicyTests))
    if hasattr(VoicePolicyTests, "workspace"):
        (VoicePolicyTests.workspace / "suite.json").write_text(json.dumps({
            "tests": suite_result.testsRun, "failures": len(suite_result.failures),
            "errors": len(suite_result.errors), "skipped": len(suite_result.skipped),
            "passed": suite_result.wasSuccessful(),
        }, indent=2), encoding="utf-8")
    raise SystemExit(0 if suite_result.wasSuccessful() else 1)
