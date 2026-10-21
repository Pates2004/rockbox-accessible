#include "config.h"
#include <stdio.h>
#include <string.h>
#include "string-extra.h"
#include <limits.h>
#include "system.h"
#include "kernel.h"
#include "thread.h"
#include "file.h"
#include "settings.h"
#include "talk.h"
#include "voice_thread.h"
#include "audio.h"
#include "pcmbuf.h"
#include "rbpaths.h"
#include "lang.h"
#include "list.h"
#include "splash.h"
#include "debug.h"
#include "tts.h"
#include "rb_espeak.h"

#define TTS_QUEUE_COUNT 32
#define TTS_TEXT_SIZE 1024
#define TTS_STRINGS_SIZE (96 * 1024)
#define TTS_STRING_COUNT (LANG_LAST_INDEX_IN_ARRAY + \
    LANG_LAST_VOICEONLY_INDEX_IN_ARRAY - VOICEONLY_DELIMITER - 1)

static struct mutex tts_mutex;
static struct event_queue tts_wakeup;
static char text_queue[TTS_QUEUE_COUNT][TTS_TEXT_SIZE];
static bool tracked_queue[TTS_QUEUE_COUNT];
static uint32_t character_queue[TTS_QUEUE_COUNT];
static int8_t pitch_queue[TTS_QUEUE_COUNT];
static struct {
    size_t offset;
    uint32_t milliseconds;
} read_marks[TTS_TEXT_SIZE];
static size_t read_mark_count;
static size_t read_mark_cursor;
static size_t read_offset;

enum tts_read_state {
    TTS_READ_NONE,
    TTS_READ_QUEUED,
    TTS_READ_SYNTHESIZING,
    TTS_READ_DRAINING,
    TTS_READ_FINISHED,
    TTS_READ_INTERRUPTED
};
static enum tts_read_state read_state;
static uint64_t read_end_us;
static struct mutex tts_request_mutex;

struct synthesis_context {
    uint32_t generation;
    const char *text;
};
static unsigned int queue_head;
static unsigned int pending_count;
static uint32_t generation;
static bool synthesizing;
static bool initialized;
static bool catalog_ready;
static bool status_output;
static unsigned int worker_id;
static unsigned int sample_rate;
static long tts_stack[(128 * 1024) / sizeof(long)];
static unsigned char voice_strings[TTS_STRINGS_SIZE];
static uint32_t voice_offsets[TTS_STRING_COUNT];
static const char *last_error = "";
static const char *last_warning = "";

#ifndef SIMULATOR
static struct semaphore initialization_done;
static int initialization_frequency;

static void initialize_native_engine(void)
{
    cpu_boost(true);
    initialization_frequency = rb_espeak_init(ROCKBOX_DIR);
    cpu_boost(false);
    semaphore_release(&initialization_done);
    thread_exit();
}
#endif

#ifdef SIMULATOR
extern const char *sim_root_dir;
#endif

static const char *system_language_name(void)
{
    const char *language = global_settings.lang_file;
    return !*language || (unsigned char)*language == 0xff ? "english" : language;
}

static const char *system_language_voice(void)
{
    static const struct {
        const char *language;
        const char *voice;
    } languages[] = {
        { "arabic", "" },
        { "basque", "" },
        { "bulgarian", "" },
        { "catala", "ca" },
        { "chinese-simp", "zh" },
        { "chinese-trad", "zh" },
        { "czech", "cs" },
        { "dansk", "da" },
        { "deutsch", "de" },
        { "eesti", "" },
        { "english-us", "en-us" },
        { "english", "en" },
        { "espanol", "es" },
        { "esperanto", "eo" },
        { "finnish", "fi" },
        { "francais", "fr" },
        { "galego", "" },
        { "greek", "el" },
        { "hebrew", "" },
        { "hindi", "hi" },
        { "hrvatski", "hr" },
        { "islenska", "is" },
        { "italiano", "it" },
        { "japanese", "" },
        { "korean", "" },
        { "latviesu", "lv" },
        { "lietuviu", "" },
        { "magyar", "hu" },
        { "moldoveneste", "ro" },
        { "nederlands", "nl" },
        { "norsk-nynorsk", "no" },
        { "norsk", "no" },
        { "polski", "pl" },
        { "portugues-brasileiro", "pt" },
        { "portugues", "pt-pt" },
        { "romaneste", "ro" },
        { "russian", "ru" },
        { "slovak", "sk" },
        { "slovenscina", "" },
        { "srpski", "sr" },
        { "svenska", "sv" },
        { "tagalog", "" },
        { "thai", "" },
        { "turkce", "tr" },
        { "ukrainian", "" },
        { "vietnamese", "vi" },
        { "vlaams", "nl" },
        { "walon", "" },
    };
    const char *language = system_language_name();
    for (size_t index = 0; index < ARRAYLEN(languages); ++index)
        if (!strcmp(language, languages[index].language))
            return languages[index].voice;
    return "";
}

static bool resolve_voice(char *language, char *variant)
{
    const char *selected = global_settings.tts_language;
    if (!*selected || (unsigned char)*selected == 0xff ||
        !strcmp(selected, "system"))
        selected = system_language_voice();
    strlcpy(language, selected, sizeof(global_settings.tts_language));
    strlcpy(variant, global_settings.tts_variant, sizeof(global_settings.tts_variant));
    const char *warning = "";
    if (rb_espeak_validate_voice(language, "") != RB_ESPEAK_OK)
    {
        strlcpy(language, "en", sizeof(global_settings.tts_language));
        warning = "eSpeak language unavailable; using English";
        if (rb_espeak_validate_voice(language, "") != RB_ESPEAK_OK)
            return false;
    }
    if (rb_espeak_validate_voice(language, variant) != RB_ESPEAK_OK)
    {
        variant[0] = '\0';
        warning = *warning
            ? "eSpeak language and variant unavailable; using English and default variant"
            : "eSpeak variant unavailable; using default variant";
    }
    if (strcmp(last_warning, warning))
    {
        last_warning = warning;
        if (*warning)
            DEBUGF("TTS: %s\n", warning);
    }
    return true;
}

static int rate_percent_tenths(int rate)
{
    int difference = rate - 175;
    int magnitude = difference < 0 ? -difference : difference;
    int percent = (magnitude * 1000 + 175 / 2) / 175;
    return difference < 0 ? -percent : percent;
}

const char *tts_format_rate(char *buffer, size_t size, int value,
                            const char *unit)
{
    (void)unit;
    if (global_settings.tts_rate_scale == TTS_RATE_WPM)
        snprintf(buffer, size, "%d %s", value, str(LANG_TTS_RATE_WPM_UNIT));
    else
    {
        int percent = rate_percent_tenths(value);
        const char *sign = percent < 0 ? "-" : percent > 0 ? "+" : "";
        int magnitude = percent < 0 ? -percent : percent;
        if (magnitude % 10)
            snprintf(buffer, size, "%s%d.%d %%", sign, magnitude / 10, magnitude % 10);
        else
            snprintf(buffer, size, "%s%d %%", sign, magnitude / 10);
    }
    return buffer;
}

int32_t tts_rate_talk_id(int value, int unit)
{
    (void)unit;
    if (global_settings.tts_rate_scale == TTS_RATE_WPM)
    {
        talk_value(value, UNIT_INT, false);
        talk_id(LANG_TTS_RATE_WPM_UNIT, true);
        return -1;
    }
    int percent = rate_percent_tenths(value);
    int32_t identifier = percent % 10 ? TALK_ID_DECIMAL(percent, 1, UNIT_PERCENT)
                                     : TALK_ID(percent / 10, UNIT_PERCENT);
    if (percent > 0)
    {
        talk_id(VOICE_PLUS, false);
        talk_id(identifier, true);
        return -1;
    }
    return identifier;
}

static int voice_index(int32_t id)
{
    if (id >= 0 && id < LANG_LAST_INDEX_IN_ARRAY)
        return id;
    if (id > VOICEONLY_DELIMITER && id < LANG_LAST_VOICEONLY_INDEX_IN_ARRAY)
        return LANG_LAST_INDEX_IN_ARRAY + id - VOICEONLY_DELIMITER - 1;
    return -1;
}

static bool load_voice_strings(const char *language)
{
    char path[MAX_PATH];
    snprintf(path, sizeof(path), LANG_DIR "/%s.vstrings", language);
    int descriptor = open(path, O_RDONLY);
    if (descriptor < 0)
        return false;
    off_t length = ffilesize(descriptor);
    if (length < 10 || length > (off_t)sizeof(voice_strings))
    {
        close(descriptor);
        return false;
    }
    ssize_t loaded = read(descriptor, voice_strings, length);
    close(descriptor);
    if (loaded != length || voice_strings[0] != 0x9a ||
        voice_strings[1] != 0x06 || voice_strings[2] != TARGET_ID)
        return false;

    memset(voice_offsets, 0xff, sizeof(voice_offsets));
    unsigned int count = (voice_strings[4] << 8) | voice_strings[5];
    size_t position = (voice_strings[8] << 8) | voice_strings[9];
    if (position < 10 || position >= (size_t)length)
        return false;
    for (unsigned int entry = 0; entry < count; ++entry)
    {
        if (position + 2 >= (size_t)length)
            return false;
        int identifier = (voice_strings[position] << 8) | voice_strings[position + 1];
        position += 2;
        unsigned char *end = memchr(voice_strings + position, 0, length - position);
        if (!end)
            return false;
        int index = voice_index(identifier);
        if (index >= 0)
            voice_offsets[index] = position;
        position = end - voice_strings + 1;
    }
    return true;
}

bool tts_request_cancelled(uint32_t expected)
{
    mutex_lock(&tts_mutex);
    bool cancelled = generation != expected;
    mutex_unlock(&tts_mutex);
    return cancelled;
}

static int receive_audio(const short *samples, int count, void *context)
{
    uint32_t expected = ((struct synthesis_context *)context)->generation;
    if (tts_request_cancelled(expected))
        return 1;
    if (samples && count > 0 && !voice_play_pcm(samples, count, sample_rate, expected))
        return 1;
    yield();
    return tts_request_cancelled(expected) ? 1 : 0;
}

static void receive_position(int character, int milliseconds, void *context)
{
    struct synthesis_context *request = context;
    if (character <= 0 || milliseconds < 0)
        return;
    size_t offset = 0;
    for (int position = 1; position < character && request->text[offset]; ++position)
    {
        ++offset;
        while (((unsigned char)request->text[offset] & 0xc0) == 0x80)
            ++offset;
    }
    if (!request->text[offset])
        return;
    mutex_lock(&tts_mutex);
    if (request->generation == generation && read_mark_count < ARRAYLEN(read_marks) &&
        (!read_mark_count || offset > read_marks[read_mark_count - 1].offset))
    {
        read_marks[read_mark_count].offset = offset;
        read_marks[read_mark_count++].milliseconds = milliseconds;
    }
    mutex_unlock(&tts_mutex);
}

static void tts_read_update_locked(const struct voice_pcm_progress *progress)
{
    if (read_state == TTS_READ_NONE || read_state == TTS_READ_INTERRUPTED ||
        read_state == TTS_READ_FINISHED)
        return;
    uint64_t elapsed = progress->elapsed_us / 1000;
    while (read_mark_cursor < read_mark_count &&
           read_marks[read_mark_cursor].milliseconds <= elapsed)
        read_offset = read_marks[read_mark_cursor++].offset;
    if (read_state == TTS_READ_DRAINING && progress->elapsed_us >= read_end_us)
        read_state = TTS_READ_FINISHED;
}

static void tts_read_reset_locked(enum tts_read_state state)
{
    read_mark_count = read_mark_cursor = read_offset = 0;
    read_end_us = 0;
    read_state = state;
}

size_t tts_read_position(void)
{
    if (!initialized)
        return 0;
    mutex_lock(&tts_mutex);
    uint32_t expected = generation;
    mutex_unlock(&tts_mutex);
    struct voice_pcm_progress progress;
    voice_pcm_get_progress(&progress);
    mutex_lock(&tts_mutex);
    if (generation == expected)
        tts_read_update_locked(&progress);
    size_t offset = read_offset;
    mutex_unlock(&tts_mutex);
    return offset;
}

bool tts_read_interrupted(void)
{
    if (!initialized)
        return false;
    mutex_lock(&tts_mutex);
    bool interrupted = read_state == TTS_READ_INTERRUPTED;
    mutex_unlock(&tts_mutex);
    return interrupted;
}

void tts_pause(bool paused)
{
    if (initialized)
        voice_pause_pcm(paused);
}

static void tts_worker(void)
{
    char text[TTS_TEXT_SIZE];
    char language[sizeof(global_settings.tts_language)];
    char variant[sizeof(global_settings.tts_variant)];
    struct queue_event wakeup;
    while (true)
    {
        queue_wait(&tts_wakeup, &wakeup);
        while (true)
        {
            mutex_lock(&tts_mutex);
            if (!pending_count)
            {
                mutex_unlock(&tts_mutex);
                break;
            }
            size_t length = 0;
            bool tracked = tracked_queue[queue_head];
            uint32_t character = character_queue[queue_head];
            int pitch_percent = pitch_queue[queue_head];
            while (pending_count)
            {
                if (length && (tracked || tracked_queue[queue_head] || character ||
                               character_queue[queue_head] || pitch_queue[queue_head] != pitch_percent))
                    break;
                const char *segment = text_queue[queue_head];
                size_t segment_length = strlen(segment);
                if (length && length + 1 + segment_length >= sizeof(text))
                    break;
                if (length)
                    text[length++] = ' ';
                memcpy(text + length, segment, segment_length + 1);
                length += segment_length;
                DEBUGF("TTS: %s\n", segment);
                queue_head = (queue_head + 1) % TTS_QUEUE_COUNT;
                --pending_count;
            }
            uint32_t expected = generation;
            struct synthesis_context context = { expected, text };
            if (tracked)
                read_state = TTS_READ_SYNTHESIZING;
            synthesizing = true;
            mutex_unlock(&tts_mutex);

#ifndef SIMULATOR
            cpu_boost(true);
#endif
            bool valid_voice = resolve_voice(language, variant);
            int pitch = global_settings.tts_pitch;
            if (pitch_percent)
            {
                pitch = (pitch * (100 + pitch_percent) + 50) / 100;
                if (pitch < 0)
                    pitch = 0;
                else if (pitch > 99)
                    pitch = 99;
            }
            DEBUGF("TTS utterance: %s\n", text);
            DEBUGF("TTS audio playback: %d\n", (audio_status() & AUDIO_STATUS_PLAY) != 0);
            DEBUGF("TTS parameters: language=%s variant=%s rate=%d pitch=%d volume=%d range=%d wordgap=%d punctuation=%d\n",
                language, variant, global_settings.tts_rate, pitch,
                global_settings.tts_volume, global_settings.tts_range,
                global_settings.tts_wordgap, global_settings.tts_punctuation);
            int result = RB_ESPEAK_INVALID_VOICE;
            if (valid_voice && character)
                result = rb_espeak_synth_character(character, language, variant,
                    global_settings.tts_rate, pitch,
                    global_settings.tts_volume, global_settings.tts_range,
                    global_settings.tts_wordgap, receive_audio, &context);
            else if (valid_voice)
                result = rb_espeak_synth_tracked(text, language, variant,
                    global_settings.tts_rate, pitch,
                    global_settings.tts_volume, global_settings.tts_range,
                    global_settings.tts_wordgap, global_settings.tts_punctuation,
                    receive_audio, tracked ? receive_position : NULL, &context);
#ifndef SIMULATOR
            cpu_boost(false);
#endif
            struct voice_pcm_progress progress;
            voice_pcm_get_progress(&progress);
            mutex_lock(&tts_mutex);
            if (generation == expected)
            {
                if (tracked && read_state == TTS_READ_SYNTHESIZING)
                {
                    read_end_us = progress.end_us;
                    read_state = TTS_READ_DRAINING;
                    tts_read_update_locked(&progress);
                }
                last_error = result == 0 ? "" : "eSpeak synthesis failed";
                if (result != 0)
                    DEBUGF("TTS: synthesis failed (%d)\n", result);
                if (!pending_count &&
                    (result != 0 || progress.elapsed_us == progress.end_us))
                    status_output = false;
            }
            synthesizing = false;
            mutex_unlock(&tts_mutex);
            yield();
        }
    }
}

bool tts_init(void)
{
    catalog_ready = false;
    if (!initialized)
    {
#ifdef SIMULATOR
        char path[MAX_PATH];
        int written = snprintf(path, sizeof(path), "%s%s", sim_root_dir, ROCKBOX_DIR);
        if (written < 0 || written >= (int)sizeof(path))
        {
            last_error = "eSpeak data path is too long";
            return false;
        }
        int frequency = rb_espeak_init(path);
#else
        semaphore_init(&initialization_done, 1, 0);
        unsigned int initializer = create_thread(initialize_native_engine,
            tts_stack, sizeof(tts_stack), 0, "espeak init"
            IF_PRIO(, PRIORITY_PLAYBACK) IF_COP(, CPU));
        if (!initializer)
        {
            last_error = "Cannot create the synthesis initialization thread";
            return false;
        }
        semaphore_wait(&initialization_done, TIMEOUT_BLOCK);
        thread_wait(initializer);
        int frequency = initialization_frequency;
#endif
        if (frequency <= 0)
        {
            last_error = "Cannot initialize the supplied eSpeak data";
            return false;
        }
        sample_rate = frequency;
        if (!voice_thread_init())
        {
            last_error = "Cannot initialize speech output";
            return false;
        }
        mutex_init(&tts_mutex);
        mutex_init(&tts_request_mutex);
        queue_init(&tts_wakeup, false);
        worker_id = create_thread(tts_worker, tts_stack, sizeof(tts_stack),
            0, "espeak" IF_PRIO(, PRIORITY_PLAYBACK) IF_COP(, CPU));
        if (!worker_id)
        {
            queue_delete(&tts_wakeup);
            last_error = "Cannot create the synthesis thread";
            return false;
        }
        initialized = true;
    }
    char language[sizeof(global_settings.tts_language)];
    char variant[sizeof(global_settings.tts_variant)];
    if (!resolve_voice(language, variant))
    {
        last_error = "No usable eSpeak language is available, including English";
        return false;
    }
    const char *catalog = system_language_name();
    if (!load_voice_strings(catalog))
    {
        memset(voice_offsets, 0xff, sizeof(voice_offsets));
        last_error = "Missing or incompatible voice text catalog";
        DEBUGF("TTS: voice text catalog unavailable for %s\n", catalog);
        return false;
    }
    last_error = "";
    catalog_ready = true;
    return true;
}

bool tts_is_available(void)
{
    return initialized && catalog_ready && global_settings.tts_enabled;
}

bool tts_output_uses_synthesis(void)
{
    if (tts_is_available())
        return true;
    if (!initialized)
        return false;
    mutex_lock(&tts_mutex);
    bool active = status_output;
    mutex_unlock(&tts_mutex);
    return active;
}

bool tts_is_busy(void)
{
    if (!initialized)
        return false;
    mutex_lock(&tts_mutex);
    bool busy = synthesizing || pending_count;
    mutex_unlock(&tts_mutex);
    return busy;
}

static void tts_cancel_output_locked(const struct voice_pcm_progress *progress)
{
    tts_read_update_locked(progress);
    if (read_state == TTS_READ_QUEUED || read_state == TTS_READ_SYNTHESIZING ||
        read_state == TTS_READ_DRAINING)
        read_state = TTS_READ_INTERRUPTED;
    ++generation;
    pending_count = 0;
    queue_head = 0;
    status_output = false;
}

static void tts_stop_locked(void)
{
    struct voice_pcm_progress progress;
    voice_pcm_get_progress(&progress);
    mutex_lock(&tts_mutex);
    tts_cancel_output_locked(&progress);
    mutex_unlock(&tts_mutex);
    voice_play_stop();
}

void tts_voice_clip_started(void)
{
    if (!initialized)
        return;
    struct voice_pcm_progress progress;
    voice_pcm_get_progress(&progress);
    mutex_lock(&tts_mutex);
    tts_cancel_output_locked(&progress);
    mutex_unlock(&tts_mutex);
}

void tts_voice_output_finished(void)
{
    if (!initialized)
        return;
    mutex_lock(&tts_mutex);
    if (!synthesizing && !pending_count)
        status_output = false;
    mutex_unlock(&tts_mutex);
}

void tts_stop(void)
{
    if (!initialized)
    {
        voice_play_stop();
        return;
    }
    mutex_lock(&tts_request_mutex);
    tts_stop_locked();
    mutex_unlock(&tts_request_mutex);
}

static int tts_speak_queued(const char *text, size_t length, bool enqueue, bool tracked,
                          uint32_t character, bool forced, int pitch_percent)
{
    if ((forced ? !initialized : !tts_is_available()) ||
        !text || length >= TTS_TEXT_SIZE)
        return -1;
    mutex_lock(&tts_request_mutex);
    if (forced ? !initialized : !tts_is_available())
    {
        mutex_unlock(&tts_request_mutex);
        return -1;
    }
    if (!enqueue)
        tts_stop_locked();
    if (!length)
    {
        if (tracked)
        {
            mutex_lock(&tts_mutex);
            tts_read_reset_locked(TTS_READ_FINISHED);
            mutex_unlock(&tts_mutex);
        }
        mutex_unlock(&tts_request_mutex);
        return 0;
    }
    mutex_lock(&tts_mutex);
    if (pending_count == TTS_QUEUE_COUNT)
    {
        last_error = "Speech queue is full";
        mutex_unlock(&tts_mutex);
        mutex_unlock(&tts_request_mutex);
        return -1;
    }
    unsigned int slot = (queue_head + pending_count) % TTS_QUEUE_COUNT;
    char *destination = text_queue[slot];
    tracked_queue[slot] = tracked;
    character_queue[slot] = character;
    pitch_queue[slot] = pitch_percent;
    memcpy(destination, text, length);
    destination[length] = '\0';
    if (tracked)
        tts_read_reset_locked(TTS_READ_QUEUED);
    if (forced)
        status_output = true;
    ++pending_count;
    if (queue_empty(&tts_wakeup))
        queue_post(&tts_wakeup, 1, 0);
    mutex_unlock(&tts_mutex);
    mutex_unlock(&tts_request_mutex);
    return 0;
}

int tts_speak(const char *text, size_t length, bool enqueue)
{
    return tts_speak_queued(text, length, enqueue, false, 0, false, 0);
}

int tts_speak_tracked(const char *text, size_t length)
{
    return tts_speak_queued(text, length, false, true, 0, false, 0);
}

int tts_speak_character_options(uint32_t codepoint, bool enqueue, int pitch_percent)
{
    if (!codepoint || codepoint > 0x10ffff ||
        (codepoint >= 0xd800 && codepoint <= 0xdfff) ||
        pitch_percent < -80 || pitch_percent > 100)
        return -1;
    char label[32];
    int length = snprintf(label, sizeof(label), "U+%04lx", (unsigned long)codepoint);
    return tts_speak_queued(label, length, enqueue, false, codepoint, false, pitch_percent);
}

int tts_speak_character(uint32_t codepoint)
{
    return tts_speak_character_options(codepoint, false, 0);
}

int tts_speak_status(int32_t id)
{
    if (id < 0 || id >= LANG_LAST_INDEX_IN_ARRAY)
        return -1;
    if (!initialized)
        tts_init();
    if (!initialized)
        return -1;
    const char *text = (const char *)str(id);
    if (!text || !*text)
        return -1;
    return tts_speak_queued(text, strlen(text), false, false, 0, true, 0);
}

int tts_speak_status_ids(const int32_t *ids, size_t count)
{
    if (!ids || !count || count > 8)
        return -1;
    char message[512];
    size_t used = 0;
    for (size_t index = 0; index < count; ++index)
    {
        if (ids[index] < 0 || ids[index] >= LANG_LAST_INDEX_IN_ARRAY)
            return -1;
        const char *text = (const char *)str(ids[index]);
        if (!text || !*text)
            return -1;
        size_t length = strlen(text);
        if (length >= sizeof(message) - used - (index != 0))
            return -1;
        if (index)
            message[used++] = '\n';
        memcpy(message + used, text, length);
        used += length;
    }
    message[used] = '\0';
    if (!initialized)
        tts_init();
    if (!initialized)
        return -1;
    return tts_speak_queued(message, used, false, false, 0, true, 0);
}

const char *tts_get_voice_text(int32_t id)
{
    int index = voice_index(id);
    if (index < 0)
        return NULL;
    const char *text = NULL;
    if (voice_offsets[index] != UINT32_MAX)
        text = (const char *)voice_strings + voice_offsets[index];
    else if (id < LANG_LAST_INDEX_IN_ARRAY)
        text = (const char *)str(id);
    return text;
}

int tts_speak_id(int32_t id, bool enqueue)
{
    const char *text = tts_get_voice_text(id);
    if (!text)
        return -1;
    return tts_speak(text, strlen(text), enqueue);
}

void tts_settings_changed(void)
{
    tts_stop();
    talk_init();
    voice_set_mixer_level(global_settings.talk_mixer_amp);
    pcmbuf_update_voice_volume();
}

void tts_ducking_changed(bool value)
{
    (void)value;
    pcmbuf_update_voice_volume();
}

void tts_ducking_level_changed(int value)
{
    (void)value;
    pcmbuf_update_voice_volume();
}

const char *tts_last_error(void)
{
    return last_error;
}

const char *tts_last_warning(void)
{
    return last_warning;
}

static const char *voice_choice_id(bool variants, int selected)
{
    if (!variants)
    {
        if (selected == 0)
            return "system";
        --selected;
    }
    return rb_espeak_voice_id(variants, selected);
}

static const char *voice_choice_name(int selected, void *context,
                                   char *buffer, size_t size)
{
    bool variants = *(bool *)context;
    const char *name;
    if (!variants && selected == 0)
        name = (const char *)str(LANG_TTS_SYSTEM);
    else if (variants && !*voice_choice_id(variants, selected))
        name = (const char *)str(LANG_TTS_DEFAULT_VARIANT);
    else
        name = rb_espeak_voice_name(variants, selected - (variants ? 0 : 1));
    strlcpy(buffer, name, size);
    return buffer;
}

static int speak_voice_choice(int selected, void *context)
{
    bool variants = *(bool *)context;
    if (!variants && selected == 0)
        return talk_id(LANG_TTS_SYSTEM, false);
    if (variants && !*voice_choice_id(variants, selected))
        return talk_id(LANG_TTS_DEFAULT_VARIANT, false);
    char name[128];
    voice_choice_name(selected, context, name, sizeof(name));
    if (tts_is_available())
        return tts_speak(name, strlen(name), false);
    return talk_spell(name, false);
}

bool tts_choose_voice(bool variants)
{
    if (!initialized && !tts_init())
    {
        splashf(HZ * 2, "%s", str(LANG_TTS_ERROR));
        return false;
    }
    int count = rb_espeak_voice_count(variants);
    if (count <= 0)
        return false;
    if (!variants)
        ++count;
    char *selected = variants ? global_settings.tts_variant : global_settings.tts_language;
    struct simplelist_info list;
    simplelist_info_init(&list,
        (char *)str(variants ? LANG_TTS_VARIANT : LANG_TTS_LANGUAGE), count, &variants);
    list.get_name = voice_choice_name;
    list.get_talk = speak_voice_choice;
    for (int index = 0; index < count; ++index)
        if (!strcmp(selected, voice_choice_id(variants, index)))
            list.selection = index;
    if (simplelist_show_list(&list))
        return true;
    if (list.selection >= 0)
    {
        tts_stop();
        strlcpy(selected, voice_choice_id(variants, list.selection),
            variants ? sizeof(global_settings.tts_variant) : sizeof(global_settings.tts_language));
        settings_save();
        if (tts_init())
            speak_voice_choice(list.selection, &variants);
        else
            splashf(HZ * 2, "%s", str(LANG_TTS_ERROR));
    }
    return false;
}
