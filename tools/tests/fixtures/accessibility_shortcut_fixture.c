#include "host.h"
#include "accessibility_shortcut.h"

struct user_settings global_settings;
static int counts[C_COUNT];
static int events[1024], event_count;
static bool engine_ready = true, catalog_ready = true;
static bool voice_present = true, voice_loaded;
static int status_result, save_result, status_label, splash_label;
static struct user_settings status_settings, saved_settings;
static bool changed_states[16];
static int change_count;

static void event(int kind)
{
    assert(event_count < (int)(sizeof(events) / sizeof(events[0])));
    events[event_count++] = kind;
    ++counts[kind];
}

const unsigned char *str(int label)
{
    static const unsigned char labels[LANG_TEST_COUNT][40] = {
        [LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON] = "eSpeak on",
        [LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF] = "eSpeak off",
        [LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON] = "Voice files on",
        [LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF] = "Voice files off",
        [LANG_ACCESSIBILITY_SHORTCUT_FAILED] = "Cannot enable eSpeak",
        [LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING] = "Voice file missing"
    };
    assert(label >= 0 && label < LANG_TEST_COUNT);
    return labels[label];
}

void talk_init(void)
{
    event(C_TALK_INIT);
    voice_loaded = !global_settings.tts_enabled && voice_present;
}

bool talk_get_debug_data(struct talk_debug_data *data)
{
    event(C_DEBUG);
    assert(!global_settings.tts_enabled);
    assert(counts[C_TALK_INIT] > 0);
    memset(data, 0, sizeof(*data));
    data->status = voice_loaded ? TALK_STATUS_OK : TALK_STATUS_ERR_NOFILE;
    return voice_loaded;
}

void tts_settings_changed(void)
{
    event(C_CHANGED);
    assert(change_count < (int)(sizeof(changed_states) / sizeof(changed_states[0])));
    changed_states[change_count++] = global_settings.tts_enabled;
    talk_init();
}

bool tts_is_available(void)
{
    event(C_AVAILABLE);
    return global_settings.tts_enabled && engine_ready && catalog_ready;
}

int tts_speak_status(int32_t label)
{
    event(C_STATUS);
    status_label = label;
    status_settings = global_settings;
    return status_result;
}

int settings_save(void)
{
    event(C_SAVE);
    saved_settings = global_settings;
    return save_result;
}

void splashf_silent(int ticks, const char *format, ...)
{
    assert(ticks == HZ * 2 && !strcmp(format, "%s"));
    event(C_SPLASH);
    va_list arguments;
    va_start(arguments, format);
    const unsigned char *text = va_arg(arguments, const unsigned char *);
    assert(!strcmp((const char *)text, (const char *)str(status_label)));
    splash_label = status_label;
    va_end(arguments);
}

static void unchanged_settings(struct user_settings before, bool tts, bool menu)
{
    before.tts_enabled = tts;
    before.talk_menu = menu;
    assert(!memcmp(&before, &global_settings, sizeof(before)));
}

static void confirmed(int label)
{
    assert(counts[C_STATUS] == 1 && status_label == label);
    assert(!memcmp(&status_settings, &global_settings, sizeof(global_settings)));
    assert(status_settings.talk_mixer_amp == 0);
    assert(events[event_count - 1] == (status_result < 0 ? C_SPLASH : C_STATUS));
    assert(counts[C_SPLASH] == (status_result < 0 ? 1 : 0));
    if (status_result < 0)
        assert(splash_label == label);
}

static int position(int kind)
{
    for (int event_index = 0; event_index < event_count; ++event_index)
        if (events[event_index] == kind)
            return event_index;
    return -1;
}

int main(int argument_count, char **arguments)
{
    assert(argument_count >= 2);
    const char *scenario = arguments[1];
    global_settings.tts_volume = 37;
    global_settings.talk_dir = 2;
    global_settings.talk_file = 1;
    global_settings.talk_dir_clip = true;
    global_settings.talk_file_clip = true;
    global_settings.tts_ducking = true;
    global_settings.tts_ducking_level = 23;
    struct user_settings original = global_settings;

    if (!strcmp(scenario, "espeak"))
    {
        assert(argument_count == 9);
        bool previous = atoi(arguments[2]) != 0;
        global_settings.tts_enabled = previous;
        global_settings.talk_menu = atoi(arguments[3]) != 0;
        engine_ready = atoi(arguments[4]) != 0;
        catalog_ready = atoi(arguments[5]) != 0;
        status_result = atoi(arguments[6]);
        global_settings.tts_volume = atoi(arguments[7]);
        save_result = atoi(arguments[8]);
        original = global_settings;
        bool success = previous || (engine_ready && catalog_ready);
        assert(accessibility_shortcut_toggle_espeak() == success);
        bool expected = success ? !previous : previous;
        unchanged_settings(original, expected, original.talk_menu);
        assert(counts[C_CHANGED] == (success ? 1 : 2));
        assert(changed_states[0] == !previous);
        if (!success)
            assert(changed_states[1] == previous);
        assert(counts[C_TALK_INIT] == counts[C_CHANGED]);
        assert(counts[C_AVAILABLE] == 1 && counts[C_DEBUG] == 0);
        assert(position(C_CHANGED) == 0 && position(C_AVAILABLE) == 2);
        assert(counts[C_SAVE] == (success ? 1 : 0));
        if (success)
        {
            assert(!memcmp(&saved_settings, &global_settings, sizeof(global_settings)));
            assert(position(C_SAVE) < position(C_STATUS));
        }
        confirmed(!success ? LANG_ACCESSIBILITY_SHORTCUT_FAILED :
            (previous ? LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF :
                        LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON));
    }
    else if (!strcmp(scenario, "voice"))
    {
        assert(argument_count == 8);
        bool tts = atoi(arguments[2]) != 0, previous = atoi(arguments[3]) != 0;
        global_settings.tts_enabled = tts;
        global_settings.talk_menu = previous;
        voice_present = atoi(arguments[4]) != 0;
        catalog_ready = false;
        status_result = atoi(arguments[5]);
        global_settings.tts_volume = atoi(arguments[6]);
        save_result = atoi(arguments[7]);
        original = global_settings;
        bool success = tts || previous || voice_present;
        bool expected = success ? !previous : previous;
        assert(accessibility_shortcut_toggle_voice_files() == success);
        unchanged_settings(original, tts, expected);
        assert(counts[C_CHANGED] == 0 && counts[C_AVAILABLE] == 0);
        assert(counts[C_TALK_INIT] == (!tts && !previous ? 1 : 0));
        assert(counts[C_DEBUG] == counts[C_TALK_INIT]);
        if (counts[C_DEBUG])
            assert(position(C_TALK_INIT) == 0 && position(C_DEBUG) == 1);
        assert(counts[C_SAVE] == (success ? 1 : 0));
        if (success)
        {
            assert(!memcmp(&saved_settings, &global_settings, sizeof(global_settings)));
            assert(position(C_SAVE) < position(C_STATUS));
        }
        confirmed(!success ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING :
            (previous ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF :
                        LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON));
    }
    else if (!strcmp(scenario, "repeat"))
    {
        assert(argument_count == 4);
        bool voice = atoi(arguments[2]) != 0;
        global_settings.tts_enabled = atoi(arguments[3]) != 0;
        original = global_settings;
        for (int repeat = 0; repeat < 6; ++repeat)
        {
            bool previous = voice ? global_settings.talk_menu : global_settings.tts_enabled;
            assert(voice ? accessibility_shortcut_toggle_voice_files() :
                           accessibility_shortcut_toggle_espeak());
            unchanged_settings(original, voice ? original.tts_enabled : !previous,
                                voice ? !previous : original.talk_menu);
            assert(counts[C_SAVE] == repeat + 1 && counts[C_STATUS] == repeat + 1);
            assert(!memcmp(&saved_settings, &global_settings, sizeof(global_settings)));
            assert(status_label == (voice ?
                (previous ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF :
                            LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON) :
                (previous ? LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF :
                            LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON)));
        }
        assert(counts[C_CHANGED] == (voice ? 0 : 6));
        assert(counts[C_AVAILABLE] == counts[C_CHANGED]);
        unchanged_settings(original, original.tts_enabled, original.talk_menu);
    }
    else if (!strcmp(scenario, "retry"))
    {
        assert(argument_count == 3);
        bool voice = atoi(arguments[2]) != 0;
        engine_ready = catalog_ready = voice_present = false;
        assert(!(voice ? accessibility_shortcut_toggle_voice_files() :
                         accessibility_shortcut_toggle_espeak()));
        unchanged_settings(original, false, false);
        assert(counts[C_SAVE] == 0 && counts[C_STATUS] == 1);
        assert(status_label == (voice ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING :
                                       LANG_ACCESSIBILITY_SHORTCUT_FAILED));
        engine_ready = catalog_ready = voice_present = true;
        assert(voice ? accessibility_shortcut_toggle_voice_files() :
                       accessibility_shortcut_toggle_espeak());
        unchanged_settings(original, !voice, voice);
        assert(counts[C_SAVE] == 1 && counts[C_STATUS] == 2);
        assert(status_label == (voice ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON :
                                       LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON));
        assert(!memcmp(&saved_settings, &global_settings, sizeof(global_settings)));
    }
    else
        assert(!"Unknown fixture scenario");
    return 0;
}
