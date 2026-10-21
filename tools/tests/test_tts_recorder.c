#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HZ 100
#define MAX_PATH 260
#define HAVE_RECORDING
#define HAVE_TAGCACHE
#define HAVE_DISK_STORAGE
#define HAVE_MIC_REC
#define HAVE_LINE_REC
#define HAVE_FMRADIO_REC
#define HAVE_SPDIF_REC
#define HAVE_AGC
#define CONFIG_CHARGING 1
#define CONFIG_RTC 0
#define HAVE_LINE_REC_(...) __VA_ARGS__
#define HAVE_FMRADIO_REC_(...) __VA_ARGS__
#define HAVE_LINE_IN_(...) __VA_ARGS__
#define HAVE_FMRADIO_IN_(...) __VA_ARGS__
#define FOR_NB_SCREENS(screen) for (int screen = 0; screen < 1; screen++)
#define str(identifier) translations[identifier]
#define ID2P(identifier) str(identifier)
#define splash(ticks, text) splashf(ticks, "%s", text)

#if defined(HAVE_ESPEAK) && (defined(SIMULATOR) || defined(HAVE_PCM_RECORDING_VOICE))
#define HAVE_RECORDING_TTS
#endif

#include "recorder_language.h"

enum { AUDIO_STATUS_RECORD = 1, AUDIO_STATUS_PAUSE = 2,
       AUDIO_STATUS_PRERECORD = 4, AUDIO_STATUS_ERROR = 8,
       AUDIO_STATUS_WARNING = 16 };
enum { AUDIO_SRC_MIC, AUDIO_SRC_LINEIN, AUDIO_SRC_FMRADIO, AUDIO_SRC_SPDIF };
enum { SOUND_VOLUME, SOUND_MIC_GAIN, SOUND_LEFT_GAIN, SOUND_RIGHT_GAIN };
enum { AUDIO_GAIN_MIC, AUDIO_GAIN_LINEIN, UNIT_TIME };
enum { TRIG_OFF, TRIG_READY, TRIG_STEADY, TRIG_GO };
enum { TRIG_TYPE_STOP, TRIG_TYPE_PAUSE, TRIG_TYPE_NEW_FILE, TRIG_MODE_REARM = 4 };
enum shutdown_type { SHUTDOWN_POWER_OFF };

struct user_settings {
    bool talk_menu, show_shutdown_message;
#ifdef HAVE_ESPEAK
    bool tts_enabled;
#endif
    int rec_source, rec_mic_gain, rec_left_gain, rec_right_gain;
    int rec_trigger_type, rec_trigger_mode, peak_meter_clip_hold;
    char rec_directory[MAX_PATH];
};
static struct user_settings global_settings;
#include "recorder_policy.h"
static struct { int volume; } global_status;
static const char *const *translations = english;
static const char *const *voice_translations = english_voice;
static int rec_status, simulated_status, requested_status, recording_starts;
static int filename_calls, clip_resets, clip_activations;
static unsigned int last_seconds;
static bool update_list, battery_safe = true;
#ifdef HAVE_ESPEAK
static bool backend_available = true;
#endif
static bool sleep_timer, plugged_in, tagcache_ready = true;
static bool stopped, closed, flushed, powered_off;
static int disable_count, battery_percent = 75, silent_splashes, voiced_splashes;
static int abort_ticks, directory_result, directory_calls, cancelled_shutdown;
static bool directory_exists;
static int agc_preset, agc_maxgain;
static const char *agc_preset_str[] = { "Off", "Safety" };
static char path_buffer[MAX_PATH];
#ifdef HAVE_RECORDING_TTS
static unsigned long recorded_ticks, prerecord_ticks, recorded_bytes;
#endif
static void (*trigger_callback)(int);
static bool trigger_enabled;

struct speech_event {
    char text[600];
    bool enqueue;
    int identifier;
};
static struct speech_event events[256];
static size_t event_count;

static void reset_events(void)
{
    event_count = 0;
    voiced_splashes = silent_splashes = 0;
}

static void speak(const char *text, bool enqueue, int identifier)
{
    if (disable_count || !*text)
        return;
    assert(event_count < sizeof(events) / sizeof(events[0]));
    struct speech_event *event = &events[event_count++];
    snprintf(event->text, sizeof(event->text), "%s", text);
    event->enqueue = enqueue;
    event->identifier = identifier;
}

static void talk_id(int identifier, bool enqueue)
{
    speak(voice_translations[identifier], enqueue, identifier);
}

static void talk_disable(bool disable) { disable_count += disable ? 1 : -1; }
static void talk_force_shutup(void) {}
static void voice_wait(void) { assert(flushed || !battery_safe); }

#ifdef HAVE_RECORDING_TTS
static bool tts_is_available(void)
{
    return talk_tts_enabled(&global_settings) && backend_available;
}
static void talk_spell(const char *text, bool enqueue) { speak(text, enqueue, -1); }
static void talk_value(long value, int unit, bool enqueue)
{
    char buffer[64];
    assert(unit == UNIT_TIME);
    snprintf(buffer, sizeof(buffer), "%ld seconds", value);
    speak(buffer, enqueue, -1);
}
static size_t strlcpy(char *destination, const char *source, size_t size)
{
    snprintf(destination, size, "%s", source);
    return strlen(source);
}
static unsigned long audio_recorded_time(void) { return recorded_ticks; }
static unsigned long audio_prerecorded_time(void) { return prerecord_ticks; }
static unsigned long audio_num_recorded_bytes(void) { return recorded_bytes; }
static const int byte_unit_ids[] = { LANG_BYTE, LANG_KIBIBYTE, LANG_MEBIBYTE, LANG_GIBIBYTE };
static const unsigned char *byte_units[4];
static int byte_unit_id(const unsigned char *unit)
{
    for (size_t index = 0; index < 4; index++)
        if (unit == byte_units[index])
            return byte_unit_ids[index];
    abort();
}
#define P2STR(unit) ((const char *)(unit))
#define P2ID(unit) byte_unit_id(unit)
static void talk_fractional(const char *fraction, int value, int identifier)
{
    char text[64];
    snprintf(text, sizeof(text), "%d%s%s", value, *fraction ? str(LANG_POINT) : "", fraction);
    speak(text, true, -1);
    talk_id(identifier, true);
}
#endif

static void splashf(int ticks, const char *format, ...)
{
    (void)ticks;
    char buffer[600];
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(buffer, sizeof(buffer), format, arguments);
    va_end(arguments);
    voiced_splashes++;
#ifdef HAVE_ESPEAK
    if (talk_menus_enabled(&global_settings) && backend_available)
        speak(buffer, false, -1);
#endif
}

static void splashf_silent(int ticks, const char *format, ...)
{
    (void)ticks;
    (void)format;
    silent_splashes++;
}

static bool get_sleep_timer_active(void) { return sleep_timer; }
static void status_save(bool force) { (void)force; }
static bool charger_inserted(void) { return plugged_in; }
static bool battery_level_safe(void) { return battery_safe; }
static int battery_level(void) { return battery_percent; }
static bool tagcache_prepare_shutdown(void) { return tagcache_ready; }
static void cancel_shutdown(void) { cancelled_shutdown++; }
static void viewportmanager_theme_enable(int screen, bool enabled, void *viewport)
{ (void)screen; (void)enabled; (void)viewport; }
static void viewportmanager_theme_undo(int screen, bool disabled)
{ (void)screen; (void)disabled; }
static void clear_screen_buffer(bool theme) { (void)theme; }
static void empty_screen_action(void) {}
static struct { void (*update)(void); void (*scroll_stop)(void); } screens[] = {
    { empty_screen_action, empty_screen_action }
};
static int audio_status(void) { return simulated_status; }
static void audio_stop_recording(void) { requested_status = 0; stopped = true; }
static void audio_close_recording(void) { closed = true; simulated_status = 0; }
static void sleep(int ticks) { (void)ticks; simulated_status = requested_status; }
static void bookmark_autobookmark(bool prompt) { (void)prompt; }
static void audio_stop(void) { stopped = true; }
static void system_flush(void) { flushed = true; }
static void shutdown_hw(enum shutdown_type type) { (void)type; powered_off = true; }
static void sys_poweroff(void) { powered_off = true; }
static void pm_activate_clipcount(bool enabled) { if (enabled) clip_activations++; }
static void pm_reset_clipcount(void) { clip_resets++; }
static char *rec_create_filename(char *buffer)
{
    filename_calls++;
    snprintf(buffer, MAX_PATH, "/recording-%d.wav", recording_starts + 1);
    return buffer;
}
static void audio_record(const char *filename)
{
    assert(filename[0] == '/');
    recording_starts++;
    requested_status = AUDIO_STATUS_RECORD;
}
static void audio_pause_recording(void)
{ requested_status = AUDIO_STATUS_RECORD | AUDIO_STATUS_PAUSE; }
static void audio_resume_recording(void) { requested_status = AUDIO_STATUS_RECORD; }
static void peak_meter_trigger(bool enabled) { trigger_enabled = enabled; }
static void peak_meter_set_trigger_listener(void (*callback)(int))
{ trigger_callback = callback; }
static bool dir_exists(const char *folder) { (void)folder; return directory_exists; }
static int mkdir(const char *folder)
{ (void)folder; directory_calls++; return directory_result; }
static bool action_userabort(int ticks) { assert(ticks == HZ); return --abort_ticks <= 0; }
static int sound_steps(int setting) { (void)setting; return 1; }
static int sound_max(int setting) { (void)setting; return 20; }
static int sound_min(int setting) { (void)setting; return -20; }
static void setvol(void) {}
static void audio_set_recording_gain(int left, int right, int type)
{ (void)left; (void)right; (void)type; }
static void peak_meter_set_clip_hold(int hold) { (void)hold; }
static unsigned long pcm_rec_sample_rate(void) { return 48000; }
static char *fmt_gain(int setting, int value, char *buffer, int size)
{ (void)setting; snprintf(buffer, size, "%d dB", value); return buffer; }

#include "recorder_functions.h"

static size_t count_text(const char *text)
{
    size_t count = 0;
    for (size_t index = 0; index < event_count; index++)
        if (strstr(events[index].text, text))
            count++;
    return count;
}

static void test_shutdown(void)
{
    for (int battery_case = 0; battery_case < 4; battery_case++)
    {
        reset_events();
        battery_percent = battery_case == 0 ? 75 : battery_case == 1 ? 8 : -1;
        battery_safe = battery_case != 2;
        global_settings.talk_menu = global_settings.show_shutdown_message = true;
        stopped = closed = flushed = powered_off = false;
        simulated_status = AUDIO_STATUS_RECORD;
        clean_shutdown(SHUTDOWN_POWER_OFF, NULL, NULL);
        assert(powered_off);
        assert(silent_splashes == 1 && voiced_splashes == 0);
        assert(count_text(voice_translations[LANG_SHUTTINGDOWN]) == 1);
        assert(event_count == (battery_case == 1 || battery_case == 2 ? 2u : 1u));
        assert(!events[0].enqueue);
        if (event_count == 2)
        {
            assert(events[0].identifier == (battery_safe ? LANG_WARNING_BATTERY_LOW :
                                                         LANG_WARNING_BATTERY_EMPTY));
            assert(events[1].enqueue);
        }
        if (battery_safe)
            assert(stopped && closed && flushed);
    }
    reset_events();
    global_settings.talk_menu = false;
#ifdef HAVE_ESPEAK
    global_settings.tts_enabled = false;
#endif
    clean_shutdown(SHUTDOWN_POWER_OFF, NULL, NULL);
    assert(event_count == 0);
    global_settings.talk_menu = true;
#ifdef HAVE_ESPEAK
    global_settings.tts_enabled = true;
#endif
    global_settings.show_shutdown_message = false;
    sleep_timer = true;
    clean_shutdown(SHUTDOWN_POWER_OFF, NULL, NULL);
    assert(event_count == 0 && disable_count == 1);
    sleep_timer = false;
    disable_count = 0;
    global_settings.show_shutdown_message = true;
    tagcache_ready = false;
    powered_off = false;
    clean_shutdown(SHUTDOWN_POWER_OFF, NULL, NULL);
    assert(!powered_off && cancelled_shutdown == 1);
    assert(count_text(voice_translations[LANG_SHUTTINGDOWN]) == 0);
    tagcache_ready = true;
    reset_events();
    plugged_in = true;
    clean_shutdown(SHUTDOWN_POWER_OFF, NULL, NULL);
    assert(!powered_off && event_count == 0);
    plugged_in = false;
}

static void test_directory(void)
{
    reset_events();
    snprintf(global_settings.rec_directory, MAX_PATH, "/unwritable");
    directory_result = -1;
    abort_ticks = 6;
    assert(rec_create_directory() == -1);
    assert(voiced_splashes == 1 && silent_splashes == 5);
#ifdef HAVE_ESPEAK
    assert(count_text(str(LANG_REC_DIR_NOT_WRITABLE)) == 1);
#endif
    directory_result = 0;
    rec_status = 0;
    assert(rec_create_directory() == 1);
    assert(rec_status & RCSTAT_CREATED_DIRECTORY);
    directory_exists = true;
    int previous_calls = directory_calls;
    assert(rec_create_directory() == 0 && directory_calls == previous_calls);
}

static void test_unavailable_start(void)
{
#if defined(HAVE_RECORDING_TTS) && !defined(AUDIO_HAVE_RECORDING)
    const enum recording_command commands[] = { RECORDING_CMD_START, RECORDING_CMD_START_NEWFILE };
    for (size_t index = 0; index < sizeof(commands) / sizeof(commands[0]); index++)
    {
        reset_events();
        recording_starts = filename_calls = clip_resets = clip_activations = 0;
        simulated_status = requested_status = 0;
        rec_status = RCSTAT_IN_RECSCREEN;
        update_list = false;
        snprintf(path_buffer, sizeof(path_buffer), "/unchanged.wav");
        rec_command(commands[index]);
        assert(recording_starts == 0 && filename_calls == 0);
        assert(clip_resets == 0 && clip_activations == 0);
        assert(simulated_status == 0 && requested_status == 0 && !update_list);
        assert(rec_status == RCSTAT_IN_RECSCREEN && !strcmp(path_buffer, "/unchanged.wav"));
        assert(event_count == 1 && count_text(str(LANG_TTS_RECORDER_UNAVAILABLE)) == 1);
    }
    reset_events();
    global_settings.talk_menu = false;
    rec_command(RECORDING_CMD_START);
    assert(voiced_splashes == 1 && event_count == 1 && filename_calls == 0);
    assert(count_text(str(LANG_TTS_RECORDER_UNAVAILABLE)) == 1);
    global_settings.talk_menu = true;
    backend_available = false;
    reset_events();
    rec_command(RECORDING_CMD_START);
    assert(voiced_splashes == 1 && event_count == 0 && filename_calls == 0);
    backend_available = true;
    reset_events();
    stopped = closed = false;
    rec_command(RECORDING_CMD_STOP);
    audio_close_recording();
    assert(stopped && closed && event_count == 0);
#endif
}

static void test_trigger(void)
{
#if defined(HAVE_RECORDING_TTS) && !defined(AUDIO_HAVE_RECORDING)
    reset_events();
    recording_starts = filename_calls = clip_resets = clip_activations = 0;
    rec_status = RCSTAT_IN_RECSCREEN;
    simulated_status = requested_status = 0;
    last_seconds = 99;
    snprintf(path_buffer, sizeof(path_buffer), "/unchanged.wav");
    trigger_listener(TRIG_GO);
    assert(rec_status == RCSTAT_IN_RECSCREEN && !recording_starts && !filename_calls);
    assert(last_seconds == 99 && !clip_resets && !clip_activations && !requested_status);
    assert(!strcmp(path_buffer, "/unchanged.wav"));
    assert(event_count == 1 && count_text(str(LANG_TTS_RECORDER_UNAVAILABLE)) == 1);
#else
    recording_starts = 0;
    rec_status = 0;
    simulated_status = 0;
    global_settings.rec_trigger_mode = 0;
    last_seconds = 99;
    trigger_listener(TRIG_GO);
    assert(recording_starts == 1 && last_seconds == 0);
    assert(rec_status & RCSTAT_HAVE_RECORDED);
    assert(update_list);
    simulated_status = AUDIO_STATUS_RECORD | AUDIO_STATUS_PAUSE;
    global_settings.rec_trigger_type = TRIG_TYPE_PAUSE;
    trigger_listener(TRIG_GO);
    assert(recording_starts == 1 && requested_status == AUDIO_STATUS_RECORD);
    simulated_status = AUDIO_STATUS_RECORD;
    trigger_listener(TRIG_READY);
    assert(requested_status == (AUDIO_STATUS_RECORD | AUDIO_STATUS_PAUSE));
    assert(!trigger_enabled && trigger_callback == NULL);
    global_settings.rec_trigger_type = TRIG_TYPE_NEW_FILE;
    trigger_listener(TRIG_GO);
    assert(recording_starts == 1);
    trigger_listener(TRIG_READY);
    assert(recording_starts == 2);
    global_settings.rec_trigger_type = TRIG_TYPE_STOP;
    trigger_listener(TRIG_GO);
    assert(recording_starts == 3);
    global_settings.rec_trigger_mode = TRIG_MODE_REARM;
    trigger_enabled = true;
    trigger_callback = trigger_listener;
    trigger_listener(TRIG_READY);
    assert(requested_status == 0 && trigger_enabled && trigger_callback == trigger_listener);
#endif
}

static void test_labels_and_gain(void)
{
    for (int index = 0; index < ITEM_COUNT; index++)
        listid_to_enum[index] = index;
    char buffer[MAX_PATH];
    assert(!*reclist_get_name(-1, NULL, buffer, sizeof(buffer)));
    assert(!*reclist_get_name(ITEM_COUNT, NULL, buffer, sizeof(buffer)));
    global_settings.rec_source = AUDIO_SRC_MIC;
    global_settings.rec_mic_gain = 20;
    recording_step_levels(SOUND_MIC_GAIN, 1);
    set_gain();
    assert(global_settings.rec_mic_gain == 20);
    recording_step_levels(SOUND_MIC_GAIN, -50);
    set_gain();
    assert(global_settings.rec_mic_gain == -20);
    global_settings.rec_source = AUDIO_SRC_LINEIN;
    global_settings.rec_left_gain = 50;
    global_settings.rec_right_gain = -50;
    set_gain();
    assert(global_settings.rec_left_gain == 20 && global_settings.rec_right_gain == -20);
    for (int index = 0; index < ITEM_COUNT; index++)
        assert(*reclist_get_name(index, NULL, buffer, sizeof(buffer)));
    global_settings.rec_source = -1;
    assert(!*reclist_get_name(ITEM_GAIN, NULL, buffer, sizeof(buffer)));
    simulated_status = AUDIO_STATUS_RECORD;
    snprintf(path_buffer, MAX_PATH, "/long/recording/\xc5\xbc\xc3\xb3\xc5\x82w.wav");
    for (size_t size = 0; size <= sizeof(buffer); size++)
    {
        memset(buffer, 0x55, sizeof(buffer));
        reclist_get_name(ITEM_FILENAME, NULL, buffer, size);
        if (size)
            assert(memchr(buffer, 0, size));
        if (size < sizeof(buffer))
            assert((unsigned char)buffer[size] == 0x55);
    }
    memset(path_buffer, 'a', sizeof(path_buffer) - 1);
    path_buffer[sizeof(path_buffer) - 1] = 0;
    for (size_t size = 0; size < 40; size++)
        reclist_get_name(ITEM_FILENAME, NULL, buffer, size);
}

#ifdef HAVE_RECORDING_TTS
static void test_empty_voice_catalog(void)
{
    const int identifiers[] = { LANG_RECORDING_FILENAME, LANG_RECORDING_TIME,
        LANG_RECORDING_SIZE, LANG_RECORD_PRERECORD, LANG_BYTE };
    reset_events();
    for (size_t index = 0; index < sizeof(identifiers) / sizeof(identifiers[0]); index++)
    {
        int identifier = identifiers[index];
        assert(!*voice_translations[identifier] && *str(identifier));
        talk_id(identifier, true);
    }
    assert(event_count == 0);
    output_dyn_value(NULL, 0, 0, byte_units, 4, true);
    assert(event_count == 1 && !strcmp(events[0].text, "0"));
}

static void test_callbacks(void)
{
    reset_events();
    global_settings.rec_source = AUDIO_SRC_MIC;
    global_settings.rec_mic_gain = -13;
    reclist_speak(ITEM_GAIN, NULL);
    assert(event_count == 1 && strstr(events[0].text, str(LANG_GAIN)));
    assert(strstr(events[0].text, "-13 dB"));
    reset_events();
    snprintf(path_buffer, MAX_PATH, "/long/recording/\xc5\xbc\xc3\xb3\xc5\x82w.wav");
    reclist_speak(ITEM_FILENAME, NULL);
    assert(event_count == 2 && !strcmp(events[1].text, path_buffer));
    assert(events[0].identifier == -1 && !strcmp(events[0].text, str(LANG_RECORDING_FILENAME)));
    assert(!events[0].enqueue && events[1].enqueue);
    simulated_status = 0;
    reset_events();
    reclist_speak(ITEM_FILENAME, NULL);
    assert(event_count == 1 && !strcmp(events[0].text, str(LANG_RECORDING_FILENAME)));
    simulated_status = AUDIO_STATUS_RECORD;
    reset_events();
    recorded_ticks = 3661 * HZ;
    reclist_speak(ITEM_TIME, NULL);
    assert(event_count == 2 && !strcmp(events[0].text, str(LANG_RECORDING_TIME)));
    assert(events[0].identifier == -1 && !events[0].enqueue && events[1].enqueue);
    assert(!strcmp(events[1].text, "3661 seconds"));
    simulated_status = AUDIO_STATUS_PRERECORD;
    prerecord_ticks = 7 * HZ;
    reset_events();
    reclist_speak(ITEM_TIME, NULL);
    assert(event_count == 2 && !strcmp(events[0].text, str(LANG_RECORD_PRERECORD)));
    assert(events[0].identifier == -1 && !events[0].enqueue && events[1].enqueue);
    assert(!strcmp(events[1].text, "7 seconds"));
    const unsigned long sizes[] = { 0, 1, 1023, 1024, 1048576, 2147483648UL };
    const int unit_indices[] = { 0, 0, 0, 1, 2, 3 };
    for (size_t index = 0; index < sizeof(sizes) / sizeof(sizes[0]); index++)
    {
        reset_events();
        recorded_bytes = sizes[index];
        reclist_speak(ITEM_SIZE, NULL);
        char expected[MAX_PATH];
        reclist_get_name(ITEM_SIZE, NULL, expected, sizeof(expected));
        assert(event_count == 1 && !strcmp(events[0].text, expected));
        assert(strstr(events[0].text, str(LANG_RECORDING_SIZE)));
        assert(strstr(events[0].text, str(byte_unit_ids[unit_indices[index]])));
        assert(events[0].identifier == -1 && !events[0].enqueue);
        if (!recorded_bytes)
            assert(strstr(events[0].text, "0B"));
    }
    reset_events();
    reclist_speak(-1, NULL);
    reclist_speak(ITEM_COUNT, NULL);
    global_settings.talk_menu = false;
    reclist_speak(ITEM_GAIN, NULL);
    assert(event_count == 1 && strstr(events[0].text, str(LANG_GAIN)));
    global_settings.talk_menu = true;
    reset_events();
    backend_available = false;
    reclist_speak(ITEM_GAIN, NULL);
    assert(event_count == 0);
    backend_available = true;
    global_settings.tts_enabled = false;
    reclist_speak(ITEM_GAIN, NULL);
    assert(event_count == 0);
    global_settings.tts_enabled = true;
}

static void test_state_feedback(void)
{
    reset_events();
    struct recording_speech_state state = { .audio_status = -1 };
    recording_speak_state(&state, 0, TRIG_OFF);
    assert(event_count == 0);
    recording_speak_state(&state, 0, TRIG_READY);
    assert(event_count == 2 && events[0].identifier == LANG_RECORD_TRIGGER);
    reset_events();
    recording_speak_state(&state, 0, TRIG_STEADY);
    assert(event_count == 0);
    recording_speak_state(&state, AUDIO_STATUS_RECORD, TRIG_GO);
    assert(event_count == 3 && events[0].identifier == LANG_RECORDING);
    assert(events[1].identifier == -1 && events[1].enqueue);
    assert(!strcmp(events[1].text, str(LANG_RECORDING_FILENAME)));
    assert(!strcmp(events[2].text, path_buffer));
    reset_events();
    for (int repaint = 0; repaint < 100; repaint++)
        recording_speak_state(&state, AUDIO_STATUS_RECORD | AUDIO_STATUS_WARNING, TRIG_GO);
    assert(event_count == 0);
    rec_command(RECORDING_CMD_PAUSE);
    recording_speak_state(&state, AUDIO_STATUS_RECORD, TRIG_GO);
    assert(event_count == 0);
    recording_speak_state(&state, requested_status, TRIG_GO);
    assert(event_count == 2 && events[1].identifier == LANG_PAUSE);
    reset_events();
    recording_speak_state(&state, AUDIO_STATUS_RECORD, TRIG_GO);
    assert(event_count == 1 && events[0].identifier == LANG_RECORDING);
    reset_events();
    snprintf(path_buffer, MAX_PATH, "/next-recording.wav");
    recording_speak_state(&state, AUDIO_STATUS_RECORD, TRIG_GO);
    assert(event_count == 2 && events[0].identifier == -1 && !events[0].enqueue);
    assert(!strcmp(events[0].text, str(LANG_RECORDING_FILENAME)));
    assert(!strcmp(events[1].text, path_buffer) && events[1].enqueue);
    reset_events();
    recording_speak_state(&state, 0, TRIG_OFF);
    assert(event_count == 4 && events[1].identifier == LANG_OFF);
    assert(events[2].identifier == LANG_RECORD_TRIGGER && events[3].identifier == LANG_OFF);
    reset_events();
    recording_speak_state(&state, AUDIO_STATUS_PRERECORD, TRIG_OFF);
    assert(event_count == 2 && events[1].identifier == -1 && events[1].enqueue);
    assert(!strcmp(events[1].text, str(LANG_RECORD_PRERECORD)));
    reset_events();
    recording_speak_state(&state, AUDIO_STATUS_ERROR, TRIG_OFF);
    assert(event_count == 0);
    global_settings.talk_menu = false;
    recording_speak_state(&state, AUDIO_STATUS_RECORD, TRIG_READY);
    assert(event_count == 5 && events[0].identifier == LANG_RECORDING);
    reset_events();
    global_settings.talk_menu = true;
    recording_speak_state(&state, AUDIO_STATUS_RECORD, TRIG_READY);
    assert(event_count == 0);
    backend_available = false;
    recording_speak_state(&state, 0, TRIG_OFF);
    assert(event_count == 0);
    backend_available = true;
}
#endif

#ifdef HAVE_ESPEAK
static void test_tts_only_policy(void)
{
    reset_events();
    global_settings.talk_menu = false;
    global_settings.tts_enabled = true;
    battery_safe = true;
    battery_percent = 75;
    clean_shutdown(SHUTDOWN_POWER_OFF, NULL, NULL);
    assert(event_count == 1 && count_text(voice_translations[LANG_SHUTTINGDOWN]) == 1);
    assert(silent_splashes == 1 && voiced_splashes == 0);
    reset_events();
    splashf(0, "%s", "TTS-only recorder notice");
    assert(event_count == 1 && !strcmp(events[0].text, "TTS-only recorder notice"));
#ifdef HAVE_RECORDING_TTS
    reset_events();
    global_settings.rec_source = AUDIO_SRC_MIC;
    reclist_speak(ITEM_GAIN, NULL);
    assert(event_count == 1 && strstr(events[0].text, str(LANG_GAIN)));
    reset_events();
    talk_disable(true);
    reclist_speak(ITEM_GAIN, NULL);
    assert(event_count == 0);
    talk_disable(false);
#endif
    global_settings.talk_menu = true;
    reset_events();
}
#endif

int main(void)
{
    for (int language = 0; language < 2; language++)
    {
        translations = language ? polski : english;
        voice_translations = language ? polski_voice : english_voice;
#ifdef HAVE_RECORDING_TTS
        for (size_t index = 0; index < 4; index++)
            byte_units[index] = (const unsigned char *)str(byte_unit_ids[index]);
#endif
        cancelled_shutdown = 0;
        directory_exists = false;
#ifdef HAVE_ESPEAK
        global_settings.tts_enabled = true;
#endif
        test_shutdown();
        test_directory();
        test_unavailable_start();
        test_trigger();
        test_labels_and_gain();
#ifdef HAVE_RECORDING_TTS
        test_empty_voice_catalog();
        test_callbacks();
        test_state_feedback();
#endif
#ifdef HAVE_ESPEAK
        test_tts_only_policy();
#endif
        puts(language ? "Polish producer/callback checks passed" :
                        "English producer/callback checks passed");
    }
    return 0;
}
