import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import hashlib
import itertools
import re
import shlex
import subprocess
import unittest

from test_tts_coverage import extract_block


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VOICES = {
    "arabic": "", "basque": "", "bulgarian": "", "catala": "ca",
    "chinese-simp": "zh", "chinese-trad": "zh", "czech": "cs",
    "dansk": "da", "deutsch": "de", "eesti": "", "english-us": "en-us",
    "english": "en", "espanol": "es", "esperanto": "eo", "finnish": "fi",
    "francais": "fr", "galego": "", "greek": "el", "hebrew": "",
    "hindi": "hi", "hrvatski": "hr", "islenska": "is", "italiano": "it",
    "japanese": "", "korean": "", "latviesu": "lv", "lietuviu": "",
    "magyar": "hu", "moldoveneste": "ro", "nederlands": "nl",
    "norsk-nynorsk": "no", "norsk": "no", "polski": "pl",
    "portugues-brasileiro": "pt", "portugues": "pt-pt", "romaneste": "ro",
    "russian": "ru", "slovak": "sk", "slovenscina": "", "srpski": "sr",
    "svenska": "sv", "tagalog": "", "thai": "", "turkce": "tr",
    "ukrainian": "", "vietnamese": "vi", "vlaams": "nl", "walon": "",
}

HARNESS_PREFIX = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <setjmp.h>
#include <sys/types.h>
#include "apps/tts.h"
#include "lib/espeak/rb_espeak.h"
#include "apps/talk.h"

#define ARRAYLEN(array) (sizeof(array) / sizeof((array)[0]))
#define MAX_PATH 260
#define ROCKBOX_DIR "/.rockbox"
#define LANG_DIR ROCKBOX_DIR "/langs"
#define TARGET_ID 42
#define O_RDONLY 0
#define HZ 100
#define TIMEOUT_BLOCK -1
#define AUDIO_STATUS_PLAY 1
#define IF_PRIO(...)
#define IF_COP(...)
#define DEBUGF(...) test_debug(__VA_ARGS__)

enum {
    LANG_TTS_RATE_WPM_UNIT, LANG_TTS_SYSTEM, LANG_TTS_DEFAULT_VARIANT,
    LANG_TTS_ERROR, LANG_TTS_VARIANT, LANG_TTS_LANGUAGE,
    LANG_LAST_INDEX_IN_ARRAY,
    VOICEONLY_DELIMITER = 0x8000,
    VOICE_PLUS = VOICEONLY_DELIMITER + 1,
    LANG_LAST_VOICEONLY_INDEX_IN_ARRAY = VOICEONLY_DELIMITER + 4
};

struct mutex { int unused; };
struct event_queue { int unused; };
struct semaphore { int count; };
struct queue_event { int unused; };
struct simplelist_info {
    int position_source;
    int count;
    int selection;
    void *callback_data;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
};

static int updates, saves, spoken_id, spoken_value, spoken_unit;
static int spoken_count, spoken_ids[4];
static bool spoken_queues[4];
static int selected_choice, initial_choice, choice_count, catalog_failure, choice_source;
static int worker_waits, synth_calls, synth_rate, synth_punctuation;
static uint32_t elapsed_ms;
static bool pcm_paused;
static int boost_balance, initialization_runs, initialization_joins, thread_failure;
static jmp_buf initialization_exit;
static bool choice_usb, missing_english, cancel_before_audio;
static char synth_language[40], synth_variant[40], missing_voice[40];
static char synth_text[32][1024];
static int synth_pitches[32];
static char debug_segments[64][1100];
static int debug_count;
static char init_path[260], catalog_path[260], choice_names[4][128];
static jmp_buf worker_exit;
#ifdef SIMULATOR
const char *sim_root_dir = "/simdisk";
#endif
static const char *voice_ids[] = { "en", "pl", "fr" };
static const char *voice_names[] = { "English", "Polish", "French" };
static const char *variant_ids[] = { "", "adam" };
static const char *variant_names[] = { "Default", "Adam" };
static const unsigned char catalog_data[] = {
    0x9a, 0x06, TARGET_ID, 0, 0, 1, 0, 0, 0, 10, 0, 0, 'h', 'i', 0
};

static void test_debug(const char *format, ...)
{
    if (strcmp(format, "TTS: %s\n") || debug_count >= 64)
        return;
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(debug_segments[debug_count++], sizeof(debug_segments[0]), format, arguments);
    va_end(arguments);
}

static size_t strlcpy(char *destination, const char *source, size_t size)
{
    snprintf(destination, size, "%s", source);
    return strlen(source);
}
static const unsigned char *str(int identifier)
{
    static const char *strings[] = {
        "words/min", "System", "Default variant", "Unavailable", "Variant", "Language"
    };
    return (const unsigned char *)strings[identifier];
}
static int mock_open(const char *path, int flags)
{
    (void)flags;
    strlcpy(catalog_path, path, sizeof(catalog_path));
    return catalog_failure ? -1 : 1;
}
static off_t ffilesize(int descriptor) { (void)descriptor; return sizeof(catalog_data); }
static int mock_close(int descriptor) { (void)descriptor; return 0; }
static ssize_t mock_read(int descriptor, void *buffer, size_t length)
{
    (void)descriptor;
    memcpy(buffer, catalog_data, length);
    return length;
}
#define open mock_open
#define close mock_close
#define read mock_read
static void mutex_init(struct mutex *mutex) { (void)mutex; }
static void mutex_lock(struct mutex *mutex) { (void)mutex; }
static void mutex_unlock(struct mutex *mutex) { (void)mutex; }
static void queue_init(struct event_queue *queue, bool broadcast)
{ (void)queue; (void)broadcast; }
static void queue_delete(struct event_queue *queue) { (void)queue; }
static void queue_wait(struct event_queue *queue, struct queue_event *event)
{
    (void)queue;
    (void)event;
    if (worker_waits++)
        longjmp(worker_exit, 1);
}
static bool queue_empty(struct event_queue *queue) { (void)queue; return true; }
static void queue_post(struct event_queue *queue, int identifier, intptr_t data)
{ (void)queue; (void)identifier; (void)data; }
static bool voice_thread_init(void) { return true; }
static void voice_set_mixer_level(int percent) { (void)percent; }
static uint64_t mock_end_us;
static void voice_play_stop(void) { elapsed_ms = 0; mock_end_us = 0; }
static bool voice_play_pcm(const short *samples, int count, unsigned int frequency,
                           uint32_t request_generation)
{ (void)samples; mock_end_us += 1000000; return count > 0 && frequency == 22050 && !tts_request_cancelled(request_generation); }
VOICE_PROGRESS_TYPE
static void voice_pcm_get_progress(struct voice_pcm_progress *progress)
{ progress->elapsed_us = (uint64_t)elapsed_ms * 1000; progress->end_us = mock_end_us; }
static void voice_pause_pcm(bool paused) { pcm_paused = paused; }
static void yield(void) {}
#ifndef SIMULATOR
static void cpu_boost(bool enabled) { boost_balance += enabled ? 1 : -1; }
static void semaphore_init(struct semaphore *semaphore, int maximum, int count)
{ (void)maximum; semaphore->count = count; }
static void semaphore_release(struct semaphore *semaphore) { ++semaphore->count; }
static int semaphore_wait(struct semaphore *semaphore, int timeout)
{ (void)timeout; if (semaphore->count != 1) __builtin_trap(); --semaphore->count; return 0; }
static void thread_wait(unsigned int identifier) { (void)identifier; ++initialization_joins; }
static void thread_exit(void) { longjmp(initialization_exit, 1); }
#endif
static int audio_status(void) { return 0; }
static unsigned int create_thread(void (*function)(void), void *stack,
                                  size_t size, unsigned flags, const char *name)
{
    (void)stack; (void)flags;
    bool initializer = strcmp(name, "espeak init") == 0;
    if (thread_failure == (initializer ? 1 : 2))
        return 0;
    if (initializer)
    {
        if (size != 128 * 1024) __builtin_trap();
        ++initialization_runs;
        if (!setjmp(initialization_exit)) function();
    }
    return 1;
}
static void pcmbuf_update_voice_volume(void) { ++updates; }
static void settings_save(void) { ++saves; }
void talk_init(void) {}
int talk_id(int32_t identifier, bool enqueue)
{
    spoken_id = identifier;
    if (spoken_count < 4)
    {
        spoken_ids[spoken_count] = identifier;
        spoken_queues[spoken_count++] = enqueue;
    }
    return 0;
}
int talk_value(long value, int unit, bool enqueue)
{ (void)enqueue; spoken_value = value; spoken_unit = unit; return 0; }
int talk_spell(const char *text, bool enqueue)
{ (void)text; (void)enqueue; return 0; }
static void splashf(int ticks, const char *format, ...)
{ (void)ticks; (void)format; }
static void simplelist_info_init(struct simplelist_info *list, char *title,
                                 int count, void *data)
{ (void)title; memset(list, 0, sizeof(*list)); list->count = count; list->callback_data = data; }
static bool simplelist_show_list(struct simplelist_info *list)
{
    choice_source = list->position_source;
    initial_choice = list->selection;
    choice_count = list->count;
    for (int index = 0; index < list->count; ++index)
        list->get_name(index, list->callback_data, choice_names[index], sizeof(choice_names[index]));
    list->selection = selected_choice;
    return choice_usb;
}
int rb_espeak_init(const char *path)
{ strlcpy(init_path, path, sizeof(init_path)); return 22050; }
int rb_espeak_validate_voice(const char *language, const char *variant)
{
    if (!strcmp(language, missing_voice) || (missing_english && !strcmp(language, "en")))
        return RB_ESPEAK_INVALID_VOICE;
    for (size_t index = 0; index < ARRAYLEN(available_voices); ++index)
        if (!strcmp(language, available_voices[index]) &&
            (!*variant || !strcmp(variant, "adam")))
            return RB_ESPEAK_OK;
    return RB_ESPEAK_INVALID_VOICE;
}
int rb_espeak_synth(const char *text, const char *language, const char *variant,
                    int rate, int pitch, int volume, int range, int wordgap,
                    int punctuation, rb_espeak_callback callback, void *user)
{
    (void)volume; (void)range; (void)wordgap;
    if (synth_calls < 32)
    {
        strlcpy(synth_text[synth_calls], text, sizeof(synth_text[0]));
        synth_pitches[synth_calls] = pitch;
    }
    ++synth_calls;
    synth_rate = rate;
    synth_punctuation = punctuation;
    strlcpy(synth_language, language, sizeof(synth_language));
    strlcpy(synth_variant, variant, sizeof(synth_variant));
    if (cancel_before_audio)
        tts_stop();
    const short samples[] = { 20, -20 };
    return callback(samples, 2, user);
}
int rb_espeak_voice_count(bool variants) { return variants ? 2 : 3; }
int rb_espeak_synth_character(unsigned int character, const char *language, const char *variant,
                    int rate, int pitch, int volume, int range, int wordgap,
                    rb_espeak_callback callback, void *user)
{
    char text[32];
    snprintf(text, sizeof(text), "character:%u", character);
    return rb_espeak_synth(text, language, variant, rate, pitch, volume, range,
                           wordgap, RB_ESPEAK_PUNCT_NONE, callback, user);
}
int rb_espeak_synth_tracked(const char *text, const char *language, const char *variant,
                    int rate, int pitch, int volume, int range, int wordgap,
                    int punctuation, rb_espeak_callback callback,
                    rb_espeak_position_callback position_callback, void *user)
{
    if (position_callback) {
        position_callback(1, 0, user);
        position_callback(3, 200, user);
        position_callback(5, 400, user);
    }
    return rb_espeak_synth(text, language, variant, rate, pitch, volume, range,
                           wordgap, punctuation, callback, user);
}
const char *rb_espeak_voice_id(bool variants, int index)
{ return variants ? variant_ids[index] : voice_ids[index]; }
const char *rb_espeak_voice_name(bool variants, int index)
{ return variants ? variant_names[index] : voice_names[index]; }
"""

HARNESS_PREFIX = HARNESS_PREFIX.replace("VOICE_PROGRESS_TYPE", extract_block(
    (ROOT / "apps/voice_thread.h").read_text(encoding="utf-8"),
    "struct voice_pcm_progress {") + ";\n")

HARNESS_SUFFIX = r"""
void test_reset(void)
{
    memset(&global_settings, 0, sizeof(global_settings));
    global_settings.tts_enabled = true;
    global_settings.tts_rate = 175;
    strlcpy(global_settings.tts_language, "system", sizeof(global_settings.tts_language));
    strlcpy(global_settings.lang_file, "polski", sizeof(global_settings.lang_file));
    initialized = catalog_ready = synthesizing = false;
    queue_head = pending_count = generation = 0;
    read_state = TTS_READ_NONE;
    read_end_us = mock_end_us = 0;
    elapsed_ms = read_mark_count = read_mark_cursor = read_offset = 0;
    pcm_paused = false;
    last_error = last_warning = "";
    updates = saves = synth_calls = catalog_failure = debug_count = 0;
    boost_balance = initialization_runs = initialization_joins = thread_failure = 0;
    spoken_id = spoken_value = spoken_unit = -1;
    selected_choice = -1;
    choice_usb = missing_english = cancel_before_audio = false;
    missing_voice[0] = '\0';
}
void test_configure(const char *language, const char *variant, const char *system)
{
    strlcpy(global_settings.tts_language, language, sizeof(global_settings.tts_language));
    strlcpy(global_settings.tts_variant, variant, sizeof(global_settings.tts_variant));
    strlcpy(global_settings.lang_file, system, sizeof(global_settings.lang_file));
}
bool test_resolve(char *language, char *variant) { return resolve_voice(language, variant); }
void test_missing(const char *language) { strlcpy(missing_voice, language, sizeof(missing_voice)); }
void test_missing_english(void) { missing_english = true; }
void test_catalog_failure(void) { catalog_failure = 1; }
void test_set_rate(int rate, int scale)
{ global_settings.tts_rate = rate; global_settings.tts_rate_scale = scale; }
int test_rate(void) { return global_settings.tts_rate; }
const char *test_format_rate(void)
{
    static char buffer[80];
    return tts_format_rate(buffer, sizeof(buffer), global_settings.tts_rate, "");
}
int32_t test_talk_rate(void)
{ spoken_count = 0; return tts_rate_talk_id(global_settings.tts_rate, UNIT_INT); }
int test_spoken_count(void) { return spoken_count; }
int test_spoken_at(int index) { return spoken_ids[index]; }
int test_spoken_enqueue(int index) { return spoken_queues[index]; }
int test_spoken_value(void) { return spoken_value; }
int test_spoken_id(void) { return spoken_id; }
int test_spoken_unit(void) { return spoken_unit; }
int test_updates(void) { return updates; }
int test_boost_balance(void) { return boost_balance; }
int test_initialization_runs(void) { return initialization_runs; }
int test_initialization_joins(void) { return initialization_joins; }
void test_thread_failure(int failure) { thread_failure = failure; }
void test_worker(void)
{
    worker_waits = 0;
    if (!setjmp(worker_exit))
        tts_worker();
}
void test_speak(int punctuation)
{
    global_settings.tts_punctuation = punctuation;
    tts_speak("hello", 5, false);
    test_worker();
}
int test_enqueue(const char *text) { return tts_speak(text, strlen(text), true); }
void test_cancel_during_synthesis(bool cancel) { cancel_before_audio = cancel; }
int test_pending(void) { return pending_count; }
void test_elapsed(uint32_t milliseconds) { elapsed_ms = milliseconds; }
int test_paused(void) { return pcm_paused; }
const char *test_synth_text(int index) { return synth_text[index]; }
int test_debug_count(void) { return debug_count; }
const char *test_debug_segment(int index) { return debug_segments[index]; }
int test_synth_calls(void) { return synth_calls; }
int test_synth_rate(void) { return synth_rate; }
void test_set_pitch(int pitch) { global_settings.tts_pitch = pitch; }
int test_pitch(void) { return global_settings.tts_pitch; }
int test_synth_pitch(int index) { return synth_pitches[index]; }
int test_synth_punctuation(void) { return synth_punctuation; }
const char *test_synth_language(void) { return synth_language; }
const char *test_synth_variant(void) { return synth_variant; }
const char *test_init_path(void) { return init_path; }
const char *test_catalog_path(void) { return catalog_path; }
void test_choose(int selection, bool usb) { selected_choice = selection; choice_usb = usb; }
int test_initial_choice(void) { return initial_choice; }
int test_choice_count(void) { return choice_count; }
int test_choice_source(void) { return choice_source; }
const char *test_choice_name(int index) { return choice_names[index]; }
const char *test_language(void) { return global_settings.tts_language; }
const char *test_variant(void) { return global_settings.tts_variant; }
int test_saves(void) { return saves; }
"""


def phrases(language):
    text = (ROOT / "apps/lang" / (language + ".lang")).read_text(encoding="utf-8")
    return {
        match.group(1): match.group(0)
        for match in re.finditer(r"<phrase>\s+id: (\w+)\n.*?</phrase>", text, re.S)
    }


class TtsSettingsTests(unittest.TestCase):
    def test_character_pitch_is_queued_without_changing_global_settings(self):
        for library in self.libraries:
            library.test_reset()
            self.assertTrue(library.tts_init())
            library.test_set_pitch(50)
            self.assertEqual(library.test_enqueue(b"capital"), 0)
            self.assertEqual(library.tts_speak_character_options(0x104, True, 20), 0)
            self.assertEqual(library.test_enqueue(b"ordinary"), 0)
            library.test_worker()
            self.assertEqual(library.test_synth_calls(), 3)
            self.assertEqual([library.test_synth_pitch(index) for index in range(3)], [50, 60, 50])
            self.assertEqual(library.test_pitch(), 50)
            self.assertEqual(library.test_synth_text(0), b"capital")
            self.assertEqual(library.test_synth_text(1), b"character:260")
            self.assertEqual(library.test_synth_text(2), b"ordinary")

    def test_character_pitch_bounds_and_cancellation(self):
        for library in self.libraries:
            for base, change, expected in ((50, -80, 10), (50, 100, 99),
                                           (99, 100, 99), (0, 100, 0), (1, -80, 0)):
                library.test_reset()
                self.assertTrue(library.tts_init())
                library.test_set_pitch(base)
                self.assertEqual(library.tts_speak_character_options(65, False, change), 0)
                library.test_worker()
                self.assertEqual(library.test_synth_pitch(0), expected)
                self.assertEqual(library.test_pitch(), base)
            for invalid in (-81, 101, -2147483648, 2147483647):
                self.assertEqual(library.tts_speak_character_options(65, False, invalid), -1)
                self.assertEqual(library.test_pending(), 0)
            library.test_set_pitch(50)
            self.assertEqual(library.tts_speak_character_options(65, True, 20), 0)
            self.assertEqual(library.tts_speak(b"replacement", 11, False), 0)
            library.test_worker()
            self.assertEqual(library.test_synth_pitch(1), 50)

    def test_character_uses_native_mode_without_changing_punctuation(self):
        for library in self.libraries:
            library.test_reset()
            self.assertTrue(library.tts_init())
            self.assertEqual(library.tts_speak_character(0x105), 0)
            self.assertEqual(library.test_enqueue(b"ordinary"), 0)
            library.test_worker()
            self.assertEqual(library.test_synth_calls(), 2)
            self.assertEqual(library.test_synth_text(0), b"character:261")
            self.assertEqual(library.test_synth_text(1), b"ordinary")
            for invalid in (0, 0x110000, 0xd800, 0xdfff):
                self.assertEqual(library.tts_speak_character(invalid), -1)

    def test_tracked_cursor_uses_playback_clock_and_utf8(self):
        for library in self.libraries:
            library.test_reset()
            self.assertTrue(library.tts_init())
            self.assertEqual(library.tts_speak_tracked("ą b c".encode(), 6), 0)
            library.test_worker()
            self.assertEqual(library.tts_read_position(), 0)
            library.test_elapsed(199)
            self.assertEqual(library.tts_read_position(), 0)
            library.test_elapsed(200)
            self.assertEqual(library.tts_read_position(), 3)
            library.tts_pause(True)
            self.assertEqual(library.test_paused(), 1)
            self.assertEqual(library.tts_read_position(), 3)
            library.tts_pause(False)
            self.assertEqual(library.test_paused(), 0)
            library.test_elapsed(400)
            self.assertEqual(library.tts_read_position(), 5)
            library.tts_stop()
            self.assertEqual(library.tts_read_position(), 5)
            self.assertTrue(library.tts_read_interrupted())

    def test_tracked_utterance_is_not_coalesced(self):
        for library in self.libraries:
            library.test_reset()
            self.assertTrue(library.tts_init())
            self.assertEqual(library.tts_speak_tracked(b"hello", 5), 0)
            self.assertEqual(library.test_enqueue(b"other"), 0)
            library.test_worker()
            self.assertEqual(library.test_synth_calls(), 2)
            self.assertEqual(library.test_synth_text(0), b"hello")
            self.assertEqual(library.test_synth_text(1), b"other")

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "apps/tts.c").read_text(encoding="utf-8")
        cls.settings = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
        cls.voices = {}
        data = Path(os.environ.get("ESPEAK_DATA", ROOT.parent / "espeak-1.44.05-source/espeak-data"))
        for path in sorted((data / "voices").rglob("*")):
            if not path.is_file() or path.relative_to(data / "voices").parts[0] in ("!v", "mb"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            languages = re.findall(r"^language\s+(\S+)", text, re.M)
            dictionary = re.search(r"^dictionary\s+(\S+)", text, re.M)
            if not languages or path.name == "default":
                continue
            dictionary = dictionary.group(1) if dictionary else languages[0].split("-")[0]
            if (data / (dictionary + "_dict")).is_file():
                cls.voices[path.name] = languages
        if not cls.voices:
            raise RuntimeError("The supplied eSpeak voice data is required")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = _project_materials_root(ROOT) / "tts-settings-tests" / timestamp
        cls.workspace.mkdir(parents=True)
        settings_source = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        fields = re.search(r"#ifdef HAVE_ESPEAK\n(.*?)#endif", settings_source, re.S).group(1)
        policy_fields = "\n".join(re.search(
            r"^\s*(?:bool|int)\s+" + name + r"\s*;", settings_source, re.M).group().strip()
            for name in ("talk_menu", "talk_file", "talk_dir", "talk_filetype", "talk_mixer_amp"))
        globals_source = ("struct user_settings { char lang_file[64];\n" + fields +
                          policy_fields + "\n} global_settings;\n")
        available = "static const char *available_voices[] = {" + ",".join(json.dumps(voice) for voice in cls.voices) + "};\n"
        harness = cls.workspace / "harness.c"
        roles = extract_block((ROOT / "apps/gui/list.h").read_text(encoding="utf-8"),
                              "enum list_position_source\n").rstrip() + ";\n"
        prefix = HARNESS_PREFIX.replace("struct mutex", available + "\n" + roles + "struct mutex", 1)
        source = re.sub(r'^#include [^\n]+\n', '', cls.source, flags=re.M)
        harness.write_text(prefix + globals_source + source + HARNESS_SUFFIX, encoding="utf-8")
        sources = ("apps/tts.c", "apps/tts.h", "apps/settings.h", "apps/settings_list.c",
                   "apps/talk.h", "apps/voice_thread.h", "tools/tests/test_tts_settings.py")
        (cls.workspace / "provenance.json").write_text(json.dumps({
            "source_project": str(ROOT), "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
            "scope": "Actual TTS source and settings policy with explicit output/synthesis mocks",
        }, indent=2) + "\n", encoding="utf-8")
        cls.libraries = []
        commands = []
        for simulator in (False, True):
            library = cls.workspace / ("simulator.so" if simulator else "portable.so")
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                "-DHAVE_ESPEAK", "-I", str(ROOT), str(harness), "-o", str(library),
            ]
            if simulator:
                command.append("-DSIMULATOR")
            if os.environ.get("TTS_SETTINGS_SANITIZE"):
                command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
            result = subprocess.run(command, capture_output=True, text=True)
            commands.append({"command": command, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
            (cls.workspace / "build.json").write_text(json.dumps(commands, indent=2), encoding="utf-8")
            if result.returncode:
                raise RuntimeError(result.stderr)
            loaded = ctypes.CDLL(str(library))
            for name in (
                "test_format_rate", "test_synth_language", "test_synth_variant",
                "test_init_path", "test_catalog_path", "test_choice_name",
                "test_language", "test_variant", "tts_last_error", "tts_last_warning",
                "test_synth_text", "test_debug_segment",
            ):
                getattr(loaded, name).restype = ctypes.c_char_p
            loaded.tts_init.restype = ctypes.c_bool
            loaded.tts_is_available.restype = ctypes.c_bool
            loaded.test_resolve.restype = ctypes.c_bool
            loaded.tts_choose_voice.restype = ctypes.c_bool
            cls.libraries.append(loaded)
        print("TTS settings evidence:", cls.workspace, flush=True)

    def setUp(self):
        for library in self.libraries:
            library.test_reset()
        self.library = self.libraries[1]

    def resolve(self):
        language = ctypes.create_string_buffer(40)
        variant = ctypes.create_string_buffer(40)
        self.assertTrue(self.library.test_resolve(language, variant))
        return language.value, variant.value

    def test_complete_system_mapping_matches_supplied_engine(self):
        self.assertEqual(set(EXPECTED_VOICES), {path.stem for path in (ROOT / "apps/lang").glob("*.lang")})
        for language, voice in EXPECTED_VOICES.items():
            with self.subTest(language=language):
                if voice:
                    self.assertIn(voice, self.voices)
                self.library.test_configure(b"system", b"", language.encode())
                self.assertEqual(self.resolve(), ((voice or "en").encode(), b""))
                self.assertEqual(bool(self.library.tts_last_warning()), not bool(voice))

    def test_system_changes_and_explicit_selection_remains_independent(self):
        for system in (b"polski", b"francais", b"english-us"):
            self.library.test_configure(b"system", b"adam", system)
            self.assertEqual(self.resolve(), (EXPECTED_VOICES[system.decode()].encode(), b"adam"))
            self.library.test_configure(b"de", b"adam", system)
            self.assertEqual(self.resolve(), (b"de", b"adam"))

    def test_empty_sentinel_and_unknown_system_language(self):
        for system in (b"", b"\xff", b"missing-language"):
            self.library.test_configure(b"system", b"", system)
            self.assertEqual(self.resolve(), (b"en", b""))

    def test_unavailable_language_preserves_setting_and_falls_back(self):
        self.library.test_missing(b"pl")
        self.assertEqual(self.resolve(), (b"en", b""))
        self.assertTrue(self.library.tts_last_warning())
        self.assertEqual(self.library.test_language(), b"system")
        self.library.test_configure(b"missing", b"adam", b"polski")
        self.assertEqual(self.resolve(), (b"en", b"adam"))
        self.assertEqual(self.library.test_language(), b"missing")

    def test_bad_variant_does_not_disable_speech_or_reader(self):
        self.library.test_configure(b"system", b"missing", b"polski")
        self.assertTrue(self.library.tts_init())
        self.assertTrue(self.library.tts_is_available())
        self.library.test_speak(0)
        self.assertEqual(self.library.test_synth_variant(), b"")
        self.assertEqual(self.library.test_variant(), b"missing")
        self.assertTrue(self.library.tts_last_warning())
        self.assertEqual(self.library.tts_last_error(), b"")
        self.library.test_configure(b"system", b"adam", b"polski")
        self.assertEqual(self.resolve(), (b"pl", b"adam"))
        self.assertEqual(self.library.tts_last_warning(), b"")

    def test_no_usable_english_and_missing_catalog_remain_fatal(self):
        self.library.test_missing(b"pl")
        self.library.test_missing_english()
        self.assertFalse(self.library.tts_init())
        self.assertFalse(self.library.tts_is_available())
        self.assertTrue(self.library.tts_last_error())
        self.library.test_reset()
        self.library.test_catalog_failure()
        self.assertFalse(self.library.tts_init())
        self.assertFalse(self.library.tts_is_available())
        self.assertTrue(self.library.tts_last_error())

    def test_rate_display_and_voice_agree_for_every_editable_wpm(self):
        previous = -1000
        for rate in range(80, 1351):
            self.library.test_set_rate(rate, 0)
            magnitude = (abs(rate - 175) * 1000 + 87) // 175
            percent = -magnitude if rate < 175 else magnitude
            self.assertGreater(percent, previous)
            previous = percent
            sign = "-" if percent < 0 else "+" if percent > 0 else ""
            digits = f"{magnitude // 10}.{magnitude % 10}" if magnitude % 10 else str(magnitude // 10)
            expected = f"{sign}{digits} %"
            self.assertEqual(self.library.test_format_rate().decode(), expected)
            identifier = self.library.test_talk_rate()
            if percent > 0:
                self.assertEqual(identifier, -1)
                self.assertEqual(self.library.test_spoken_count(), 2)
                self.assertEqual(self.library.test_spoken_at(0), 0x8001)
                self.assertEqual(self.library.test_spoken_enqueue(0), 0)
                self.assertEqual(self.library.test_spoken_enqueue(1), 1)
                identifier = self.library.test_spoken_at(1)
            else:
                self.assertEqual(self.library.test_spoken_count(), 0)
            self.assertEqual((identifier >> 27) & 31, 9)
            self.assertEqual((identifier >> 24) & 7, int(bool(percent % 10)))
            decoded = identifier & 0xFFFFFF
            if decoded & 0x800000:
                decoded -= 0x1000000
            self.assertEqual(decoded, percent if percent % 10 else percent // 10)
        self.library.test_set_rate(175, 0)
        self.assertEqual(self.library.test_format_rate(), b"0 %")

    def test_signed_rate_reference_values_and_subzero_fraction(self):
        for rate, label in ((80, b"-54.3 %"), (174, b"-0.6 %"), (175, b"0 %"),
                            (176, b"+0.6 %"), (350, b"+100 %"), (450, b"+157.1 %"),
                            (1350, b"+671.4 %")):
            self.library.test_set_rate(rate, 0)
            self.assertEqual(self.library.test_format_rate(), label)

    def test_rate_scale_switching_does_not_change_canonical_speed(self):
        self.assertTrue(self.library.tts_init())
        for rate in range(80, 1351):
            for scale in (0, 1, 0, 1):
                self.library.test_set_rate(rate, scale)
                self.library.test_format_rate()
                self.library.test_talk_rate()
                self.library.test_speak(0)
                self.assertEqual(self.library.test_rate(), rate)
                self.assertEqual(self.library.test_synth_rate(), rate)
            self.assertEqual(self.library.test_format_rate(), f"{rate} words/min".encode())
            self.assertEqual(self.library.test_spoken_value(), rate)
            self.assertEqual(self.library.test_spoken_unit(), 1)
            self.assertEqual(self.library.test_spoken_id(), 0)

    def test_native_initialization_uses_dedicated_stack_and_joins_before_reuse(self):
        library = self.libraries[0]
        self.assertTrue(library.tts_init())
        self.assertEqual(library.test_initialization_runs(), 1)
        self.assertEqual(library.test_initialization_joins(), 1)
        self.assertEqual(library.test_boost_balance(), 0)
        self.assertTrue(library.tts_init())
        self.assertEqual(library.test_initialization_runs(), 1)
        for cancelled in (False, True):
            library.test_cancel_during_synthesis(cancelled)
            library.test_speak(0)
            self.assertEqual(library.test_boost_balance(), 0)

    def test_native_thread_creation_failures_are_reported(self):
        library = self.libraries[0]
        for failure in (1, 2):
            library.test_reset()
            library.test_thread_failure(failure)
            self.assertFalse(library.tts_init())
            self.assertFalse(library.tts_is_available())
            self.assertEqual(library.test_boost_balance(), 0)
            self.assertIn(b"Cannot create", library.tts_last_error())
            library.test_thread_failure(0)
            self.assertTrue(library.tts_init())

    def test_worker_passes_all_four_punctuation_values(self):
        self.assertTrue(self.library.tts_init())
        for punctuation in range(4):
            self.library.test_speak(punctuation)
            self.assertEqual(self.library.test_synth_punctuation(), punctuation)
            self.assertEqual(self.library.test_synth_language(), b"pl")
        self.assertEqual(self.library.test_synth_calls(), 4)

    def test_worker_coalesces_pending_segments_in_order(self):
        self.assertTrue(self.library.tts_init())
        segments = ["Głośność", "99", "point", "4", "percent"]
        for segment in segments:
            self.assertEqual(self.library.test_enqueue(segment.encode()), 0)
        self.library.test_worker()
        self.assertEqual(self.library.test_synth_calls(), 1)
        self.assertEqual(self.library.test_synth_text(0), " ".join(segments).encode())
        self.assertEqual(self.library.test_pending(), 0)
        self.assertEqual(self.library.test_debug_count(), len(segments))
        for index, segment in enumerate(segments):
            self.assertEqual(self.library.test_debug_segment(index), f"TTS: {segment}\n".encode())

    def test_worker_coalescing_respects_exact_text_buffer_limits(self):
        for first_length, expected_calls in ((1021, 1), (1022, 2), (1023, 2)):
            with self.subTest(first_length=first_length):
                self.library.test_reset()
                self.assertTrue(self.library.tts_init())
                first = b"a" * first_length
                self.assertEqual(self.library.test_enqueue(first), 0)
                self.assertEqual(self.library.test_enqueue(b"b"), 0)
                self.library.test_worker()
                self.assertEqual(self.library.test_synth_calls(), expected_calls)
                if expected_calls == 1:
                    self.assertEqual(self.library.test_synth_text(0), first + b" b")
                else:
                    self.assertEqual(self.library.test_synth_text(0), first)
                    self.assertEqual(self.library.test_synth_text(1), b"b")
        self.assertEqual(self.library.test_enqueue(b"x" * 1024), -1)
        self.assertEqual(self.library.test_pending(), 0)

    def test_worker_queue_wraparound_and_capacity(self):
        self.assertTrue(self.library.tts_init())
        for cycle in range(3):
            for index in range(32):
                self.assertEqual(self.library.test_enqueue(str(cycle * 32 + index).encode()), 0)
            self.assertEqual(self.library.test_enqueue(b"overflow"), -1)
            self.library.test_worker()
            expected = " ".join(str(cycle * 32 + index) for index in range(32))
            self.assertEqual(self.library.test_synth_text(cycle), expected.encode())
        self.assertEqual(self.library.test_pending(), 0)
        self.assertEqual(self.library.tts_last_error(), b"")

    def test_worker_cancellation_discards_joined_and_remaining_segments(self):
        self.assertTrue(self.library.tts_init())
        for segment in (b"first", b"second", b"x" * 1023):
            self.assertEqual(self.library.test_enqueue(segment), 0)
        self.library.test_cancel_during_synthesis(True)
        self.library.test_worker()
        self.assertEqual(self.library.test_synth_calls(), 1)
        self.assertEqual(self.library.test_synth_text(0), b"first second")
        self.assertEqual(self.library.test_pending(), 0)
        self.assertEqual(self.library.tts_last_error(), b"")
        self.library.test_cancel_during_synthesis(False)
        self.assertEqual(self.library.test_enqueue(b"after cancel"), 0)
        self.library.test_worker()
        self.assertEqual(self.library.test_synth_text(1), b"after cancel")
        self.assertEqual(self.library.test_enqueue(b"discard before worker"), 0)
        self.library.tts_stop()
        self.library.test_worker()
        self.assertEqual(self.library.test_synth_calls(), 2)

    def test_simulator_and_portable_data_path_boundary(self):
        for library, expected in zip(self.libraries, (b"/.rockbox", b"/simdisk/.rockbox")):
            self.assertTrue(library.tts_init())
            self.assertEqual(library.test_init_path(), expected)
            self.assertEqual(library.test_catalog_path(), b"/.rockbox/langs/polski.vstrings")

    def test_language_selector_system_offset_commit_and_cancel(self):
        self.assertTrue(self.library.tts_init())
        self.library.test_choose(2, False)
        self.assertFalse(self.library.tts_choose_voice(False))
        self.assertEqual(self.library.test_initial_choice(), 0)
        self.assertEqual(self.library.test_choice_count(), 4)
        self.assertEqual(self.library.test_choice_source(), 0)
        self.assertEqual(self.library.test_choice_name(0), b"System")
        self.assertEqual(self.library.test_choice_name(1), b"English")
        self.assertEqual(self.library.test_language(), b"pl")
        self.assertEqual(self.library.test_saves(), 1)
        self.library.test_choose(-1, False)
        self.library.tts_choose_voice(False)
        self.assertEqual(self.library.test_initial_choice(), 2)
        self.assertEqual(self.library.test_language(), b"pl")
        self.assertEqual(self.library.test_saves(), 1)
        self.library.test_choose(0, False)
        self.library.tts_choose_voice(False)
        self.assertEqual(self.library.test_language(), b"system")
        self.assertEqual(self.library.test_spoken_id(), 1)

    def test_variant_selector_and_usb_preserve_index_contract(self):
        self.assertTrue(self.library.tts_init())
        self.library.test_choose(1, False)
        self.library.tts_choose_voice(True)
        self.assertEqual(self.library.test_choice_count(), 2)
        self.assertEqual(self.library.test_choice_source(), 0)
        self.assertEqual(self.library.test_choice_name(0), b"Default variant")
        self.assertEqual(self.library.test_variant(), b"adam")
        self.library.test_choose(0, True)
        self.assertTrue(self.library.tts_choose_voice(True))
        self.assertEqual(self.library.test_variant(), b"adam")
        self.assertEqual(self.library.test_saves(), 1)

    def test_ducking_callbacks_recompute_live_volume(self):
        self.library.tts_ducking_changed(False)
        self.library.tts_ducking_changed(True)
        for level in (0, 25, 100):
            self.library.tts_ducking_level_changed(level)
        self.library.tts_settings_changed()
        self.assertEqual(self.library.test_updates(), 6)

    def test_settings_defaults_ranges_and_callbacks(self):
        settings = re.sub(r"\s+", " ", self.settings)
        for expected in (
            'tts_rate, LANG_TTS_RATE, 175, "tts rate", UNIT_INT, 80, 1350, 1, tts_format_rate, tts_rate_talk_id, NULL',
            'tts_rate_scale, LANG_TTS_RATE_SCALE, TTS_RATE_PERCENT, "tts rate scale", "percent,wpm"',
            'tts_punctuation, LANG_TTS_PUNCTUATION, 0, "tts punctuation", "none,some,most,all", NULL, 4',
            'tts_ducking, LANG_TTS_DUCKING, true, "tts ducking", tts_ducking_changed',
            'tts_ducking_level, LANG_TTS_DUCKING_LEVEL, 25, "tts ducking level", UNIT_PERCENT, 0, 100, 5, NULL, NULL, tts_ducking_level_changed',
            'tts_language, "tts language", "system"',
        ):
            self.assertIn(expected, settings)
        self.assertEqual(settings.count('"tts range"'), 1)
        self.assertNotIn('"tts modulation"', settings)

    def test_synthesis_level_units_match_display_and_speech(self):
        settings = re.sub(r"\s+", " ", self.settings)
        for field, identifier, default, maximum in (
            ("pitch", "PITCH", 50, 99),
            ("volume", "VOLUME", 100, 200),
            ("range", "RANGE", 50, 99),
        ):
            with self.subTest(field=field):
                expected = (f'tts_{field}, LANG_TTS_{identifier}, {default}, "tts {field}", '
                            f'UNIT_PERCENT, 0, {maximum}, 1, NULL, NULL, NULL')
                self.assertIn(expected, settings)

    def test_all_espeak_strings_have_complete_bilingual_voice_text(self):
        english, polish = phrases("english"), phrases("polski")
        identifiers = {identifier for identifier in english if identifier.startswith(("LANG_TTS", "LANG_TALKBOX"))}
        for identifier in identifiers:
            for language in (english, polish):
                for tag in ("source", "dest", "voice"):
                    self.assertRegex(language[identifier], rf'<{tag}>\s+\*: "[^"\n]+"\s+</{tag}>')
            source = re.search(r"<source>(.*?)</source>", english[identifier], re.S).group(1)
            self.assertIn(source, polish[identifier])
        self.assertIn('"Talkbox settings"', english["LANG_TALKBOX_SETTINGS"])
        self.assertIn('"Ustawienia Talkbox"', polish["LANG_TALKBOX_SETTINGS"])
        self.assertIn('"eSpeak settings"', english["LANG_TTS"])
        self.assertIn('"Ustawienia eSpeak"', polish["LANG_TTS"])
        self.assertIn('"Modulation"', english["LANG_TTS_RANGE"])
        self.assertIn('"Modulacja"', polish["LANG_TTS_RANGE"])

    def test_genlang_preserves_every_bilingual_espeak_voice_string(self):
        for language in ("english", "polski"):
            result = subprocess.run([
                "perl", "-s", str(ROOT / "tools/genlang"),
                "-e=" + str(ROOT / "apps/lang/english.lang"),
                "-t=sansaclipplus", "-o",
                str(ROOT / "apps/lang" / (language + ".lang")),
            ], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("LANG_TTS", result.stderr)
            compiled = dict(re.findall(r'^id: (LANG_(?:TTS\w*|TALKBOX\w*))\nvoice: "([^"\n]*)"', result.stdout, re.M))
            expected = {
                identifier: re.search(r'<voice>\s+\*: "([^"\n]*)"', phrase).group(1)
                for identifier, phrase in phrases(language).items()
                if identifier.startswith(("LANG_TTS", "LANG_TALKBOX"))
            }
            self.assertEqual(compiled, expected)

    def test_menu_separation_survives_all_capability_combinations(self):
        source = (ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
        start = source.index("#ifdef HAVE_ESPEAK\nstatic int tts_enabled_callback")
        end = source.index(");", source.index("MAKE_MENU(voice_settings_menu,")) + 2
        fragment = source[start:end]
        voice_files = ["talk_menu_item", "talk_dir_item", "talk_dir_clip_item", "talk_file_item",
                       "talk_file_clip_item", "talk_filetype_item", "talk_battery_level_item", "talk_mixer_amp_item"]
        engine = ["tts_language_item", "tts_variant_item", "tts_rate_item", "tts_rate_scale_item",
                  "tts_pitch_item", "tts_volume_item", "tts_range_item", "tts_wordgap_item", "tts_punctuation_item"]
        evidence = []
        for espeak, touch, curtain, hold in itertools.product((False, True), repeat=4):
            capabilities = dict(HAVE_ESPEAK=espeak, HAVE_TOUCHSCREEN=touch,
                                HAVE_SCREEN_CURTAIN=curtain, HAS_BUTTON_HOLD=hold)
            command = shlex.split(os.environ.get("CC", "cc")) + ["-E", "-P", "-x", "c", "-"]
            command += ["-D" + name for name, enabled in capabilities.items() if enabled]
            result = subprocess.run(command, input=fragment, capture_output=True, text=True)
            evidence.append(dict(capabilities=capabilities, command=command, exit=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
            (self.workspace / "menu-capabilities.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            with self.subTest(capabilities=capabilities):
                self.assertEqual(result.returncode, 0, result.stderr)
                menus = {name: re.findall(r"&([a-zA-Z_][a-zA-Z_0-9]*)", arguments)
                         for name, arguments in re.findall(r"MAKE_MENU\(\s*(\w+),\s*(.*?)\);", result.stdout, re.S)}
                self.assertEqual(menus["voice_settings_menu"],
                                 (["talkbox_settings_menu", "accessibility_shortcut_menu"] if espeak else []) + voice_files)
                if not espeak:
                    self.assertNotIn("talkbox_settings_menu", menus)
                    self.assertNotIn("tts_settings_menu", menus)
                    continue
                expected = ["tts_settings_menu", "tts_enabled_item", "tts_ducking_item", "tts_ducking_level_item",
                            "tts_reader_settings_menu"]
                if touch:
                    expected += ["accessibility_touch_item"]
                if not hold or touch and curtain:
                    expected += ["accessibility_display_menu"]
                if touch:
                    expected += ["accessibility_typing_item"]
                expected += ["list_boundary_feedback_item", "tts_announce_position_item", "tts_announce_dynamic_item"]
                self.assertEqual(menus["talkbox_settings_menu"], expected)
                self.assertEqual(menus["tts_settings_menu"], engine)
                self.assertEqual(menus["tts_reader_settings_menu"], ["tts_reader_unit_item", "tts_reader_page_lines_item"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TtsSettingsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if hasattr(TtsSettingsTests, "workspace"):
        report = {"tests": result.testsRun, "failures": len(result.failures),
                  "errors": len(result.errors), "successful": result.wasSuccessful()}
        (TtsSettingsTests.workspace / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
