#include "config.h"
#include "accessibility_shortcut.h"

#ifdef HAVE_ESPEAK

#include "kernel.h"
#include "lang.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"
#include "tts.h"

static void shortcut_announce(int32_t label)
{
    if (tts_speak_status(label) < 0)
        splashf_silent(HZ * 2, "%s", str(label));
}

static bool shortcut_set_espeak(bool enabled, bool announce)
{
    bool previous = global_settings.tts_enabled;
    global_settings.tts_enabled = enabled;
    tts_settings_changed();
    bool available = tts_is_available();
    if (!previous && !available)
    {
        global_settings.tts_enabled = previous;
        tts_settings_changed();
        if (announce)
            shortcut_announce(LANG_ACCESSIBILITY_SHORTCUT_FAILED);
        return false;
    }
    settings_save();
    if (announce)
        shortcut_announce(previous ? LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF :
                                     LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON);
    return true;
}

static bool shortcut_set_voice_files(bool enabled, bool announce)
{
    bool previous = global_settings.talk_menu;
    global_settings.talk_menu = enabled;
    if (!previous && !global_settings.tts_enabled)
    {
        struct talk_debug_data data;
        talk_init();
        if (!talk_get_debug_data(&data))
        {
            global_settings.talk_menu = previous;
            if (announce)
                shortcut_announce(LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING);
            return false;
        }
    }
    settings_save();
    if (announce)
        shortcut_announce(previous ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF :
                                     LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON);
    return true;
}

bool accessibility_shortcut_toggle_espeak(void)
{
    return shortcut_set_espeak(!global_settings.tts_enabled, true);
}

bool accessibility_shortcut_toggle_voice_files(void)
{
    return shortcut_set_voice_files(!global_settings.talk_menu, true);
}

bool accessibility_shortcut_set_espeak(bool enabled)
{
    return global_settings.tts_enabled == enabled || shortcut_set_espeak(enabled, false);
}

bool accessibility_shortcut_set_voice_files(bool enabled)
{
    return global_settings.talk_menu == enabled || shortcut_set_voice_files(enabled, false);
}

#else

bool accessibility_shortcut_toggle_espeak(void) { return false; }
bool accessibility_shortcut_toggle_voice_files(void) { return false; }
bool accessibility_shortcut_set_espeak(bool enabled) { (void)enabled; return false; }
bool accessibility_shortcut_set_voice_files(bool enabled) { (void)enabled; return false; }

#endif
