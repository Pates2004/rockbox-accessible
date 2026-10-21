#include "config.h"
#include "accessibility_services.h"

#ifdef HAVE_ESPEAK

#include "accessibility_shortcut.h"
#ifdef HAVE_TOUCHSCREEN
#include "accessibility.h"
#include "backlight.h"
#endif
#include "kernel.h"
#include "lang.h"
#include "settings.h"
#include "splash.h"
#include "tts.h"

enum accessibility_service
{
    ACCESSIBILITY_SERVICE_ESPEAK = 1,
    ACCESSIBILITY_SERVICE_VOICE_FILES = 2,
    ACCESSIBILITY_SERVICE_TOUCH = 4,
    ACCESSIBILITY_SERVICE_CURTAIN = 8
};

static unsigned int services_selection(void)
{
    unsigned int selected = 0;
    if (global_settings.accessibility_shortcut_espeak)
        selected |= ACCESSIBILITY_SERVICE_ESPEAK;
    if (global_settings.accessibility_shortcut_voice_files)
        selected |= ACCESSIBILITY_SERVICE_VOICE_FILES;
#ifdef HAVE_TOUCHSCREEN
    if (global_settings.accessibility_shortcut_touch)
        selected |= ACCESSIBILITY_SERVICE_TOUCH;
#ifdef HAVE_SCREEN_CURTAIN
    if (global_settings.accessibility_shortcut_curtain)
        selected |= ACCESSIBILITY_SERVICE_CURTAIN;
#endif
#endif
    return selected;
}

static unsigned int services_state(void)
{
    unsigned int enabled = 0;
    if (global_settings.tts_enabled)
        enabled |= ACCESSIBILITY_SERVICE_ESPEAK;
    if (global_settings.talk_menu)
        enabled |= ACCESSIBILITY_SERVICE_VOICE_FILES;
#ifdef HAVE_TOUCHSCREEN
    if (accessibility_enabled())
        enabled |= ACCESSIBILITY_SERVICE_TOUCH;
#ifdef HAVE_SCREEN_CURTAIN
    if (backlight_screen_curtain_active())
        enabled |= ACCESSIBILITY_SERVICE_CURTAIN;
#endif
#endif
    return enabled;
}

static bool services_apply(unsigned int selected, bool enabled)
{
    bool success = true;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_SCREEN_CURTAIN)
    if (!enabled && (selected & ACCESSIBILITY_SERVICE_CURTAIN))
        success = accessibility_set_curtain_state(false, false) && success;
#endif
    if (enabled && (selected & ACCESSIBILITY_SERVICE_ESPEAK))
        success = accessibility_shortcut_set_espeak(true) && success;
#ifdef HAVE_TOUCHSCREEN
    if (selected & ACCESSIBILITY_SERVICE_TOUCH)
        success = accessibility_set_enabled(enabled) && success;
#endif
    if (selected & ACCESSIBILITY_SERVICE_VOICE_FILES)
        success = accessibility_shortcut_set_voice_files(enabled) && success;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_SCREEN_CURTAIN)
    if (enabled && (selected & ACCESSIBILITY_SERVICE_CURTAIN))
        success = accessibility_set_curtain_state(true, false) && success;
#endif
    if (!enabled && (selected & ACCESSIBILITY_SERVICE_ESPEAK))
        success = accessibility_shortcut_set_espeak(false) && success;
    return success;
}

bool accessibility_services_activate(void)
{
    int32_t labels[5];
    size_t count = 0;
    if (!global_settings.accessibility_shortcut_enabled)
    {
        labels[count++] = LANG_ACCESSIBILITY_SHORTCUT_DISABLED;
    }
    else
    {
        unsigned int selected = services_selection();
        if (!selected)
            labels[count++] = LANG_ACCESSIBILITY_SHORTCUT_EMPTY;
        else
        {
            unsigned int previous = services_state();
            bool enabled = (previous & selected) != selected;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_SCREEN_CURTAIN)
            if (!enabled && (selected & ACCESSIBILITY_SERVICE_ESPEAK) &&
                (previous & ACCESSIBILITY_SERVICE_CURTAIN))
                selected |= ACCESSIBILITY_SERVICE_CURTAIN;
#endif
            bool success = services_apply(selected, enabled);
            unsigned int actual = services_state();
            success = success && ((actual & selected) == (enabled ? selected : 0));
            if (!success)
                labels[count++] = LANG_ACCESSIBILITY_SHORTCUT_PARTIAL;
            if (selected & ACCESSIBILITY_SERVICE_ESPEAK)
                labels[count++] = actual & ACCESSIBILITY_SERVICE_ESPEAK ?
                    LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON : LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF;
            if (selected & ACCESSIBILITY_SERVICE_VOICE_FILES)
                labels[count++] = actual & ACCESSIBILITY_SERVICE_VOICE_FILES ?
                    LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON : LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF;
            if (selected & ACCESSIBILITY_SERVICE_TOUCH)
                labels[count++] = actual & ACCESSIBILITY_SERVICE_TOUCH ?
                    LANG_ACCESSIBILITY_TOUCH_ON : LANG_ACCESSIBILITY_TOUCH_OFF;
            if (selected & ACCESSIBILITY_SERVICE_CURTAIN)
                labels[count++] = actual & ACCESSIBILITY_SERVICE_CURTAIN ?
                    LANG_ACCESSIBILITY_CURTAIN_ON : LANG_ACCESSIBILITY_CURTAIN_OFF;
            if (tts_speak_status_ids(labels, count) < 0)
                splashf_silent(HZ * 2, "%s", str(LANG_ACCESSIBILITY_SHORTCUT_FAILED));
            return success;
        }
    }
    if (tts_speak_status_ids(labels, count) < 0)
        splashf_silent(HZ * 2, "%s", str(labels[0]));
    return false;
}

#else

bool accessibility_services_activate(void) { return false; }

#endif
