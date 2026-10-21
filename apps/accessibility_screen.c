#include "config.h"
#include "accessibility_screen.h"

#ifdef HAVE_ESPEAK

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "audio.h"
#include "file.h"
#include "kernel.h"
#include "lang.h"
#include "menu.h"
#include "metadata.h"
#include "powermgmt.h"
#include "rbpaths.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"
#include "timefuncs.h"

#define SCREEN_STATE_FILE ROCKBOX_DIR "/accessibility-screen.cfg"
#define SCREEN_STATE_TEMP ROCKBOX_DIR "/accessibility-screen.cfg.tmp"
#define SCREEN_STATE_HEADER "RBACCESSIBILITY-SCREEN:1\nunlock:"
#define SCREEN_STATE_SUFFIX "\nlock:"

enum screen_unlock_notice
{
    SCREEN_UNLOCK_STATE,
    SCREEN_UNLOCK_TIME,
    SCREEN_UNLOCK_BATTERY,
    SCREEN_UNLOCK_TIME_BATTERY,
    SCREEN_UNLOCK_ALL,
    SCREEN_UNLOCK_SILENT,
    SCREEN_UNLOCK_COUNT
};

enum screen_lock_notice
{
    SCREEN_LOCK_STATE,
    SCREEN_LOCK_SILENT,
    SCREEN_LOCK_COUNT
};

static enum screen_unlock_notice unlock_notice;
static enum screen_lock_notice lock_notice;
static bool screen_state_loaded;

static void screen_state_load(void)
{
    if (screen_state_loaded)
        return;
    screen_state_loaded = true;
    char data[sizeof(SCREEN_STATE_HEADER) + sizeof(SCREEN_STATE_SUFFIX) + 3];
    size_t used = 0;
    int descriptor = open(SCREEN_STATE_FILE, O_RDONLY);
    if (descriptor < 0)
        return;
    bool valid = true;
    while (used < sizeof(data))
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0)
        {
            valid = false;
            break;
        }
        if (!count)
            break;
        used += count;
    }
    if (close(descriptor) != 0)
        valid = false;
    const size_t prefix = sizeof(SCREEN_STATE_HEADER) - 1;
    const size_t suffix = sizeof(SCREEN_STATE_SUFFIX) - 1;
    if (!valid || used != prefix + suffix + 3 ||
        memcmp(data, SCREEN_STATE_HEADER, prefix) ||
        data[prefix] < '0' || data[prefix] >= '0' + SCREEN_UNLOCK_COUNT ||
        memcmp(data + prefix + 1, SCREEN_STATE_SUFFIX, suffix) ||
        data[prefix + suffix + 1] < '0' ||
        data[prefix + suffix + 1] >= '0' + SCREEN_LOCK_COUNT ||
        data[prefix + suffix + 2] != '\n')
        return;
    unlock_notice = data[prefix] - '0';
    lock_notice = data[prefix + suffix + 1] - '0';
}

static bool screen_state_save(int unlocked, int locked)
{
    if ((unsigned int)unlocked >= SCREEN_UNLOCK_COUNT ||
        (unsigned int)locked >= SCREEN_LOCK_COUNT)
        return false;
    char data[sizeof(SCREEN_STATE_HEADER) + sizeof(SCREEN_STATE_SUFFIX) + 3];
    int length = snprintf(data, sizeof(data), SCREEN_STATE_HEADER "%u"
        SCREEN_STATE_SUFFIX "%u\n", (unsigned int)unlocked, (unsigned int)locked);
    if (length <= 0 || (size_t)length >= sizeof(data))
        return false;
    int descriptor = open(SCREEN_STATE_TEMP, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (descriptor < 0)
        return false;
    bool valid = true;
    size_t used = 0;
    while (used < (size_t)length)
    {
        ssize_t count = write(descriptor, data + used, (size_t)length - used);
        if (count <= 0)
        {
            valid = false;
            break;
        }
        used += count;
    }
    if (valid && fsync(descriptor) != 0)
        valid = false;
    if (close(descriptor) != 0)
        valid = false;
    if (!valid || rename(SCREEN_STATE_TEMP, SCREEN_STATE_FILE) != 0)
    {
        remove(SCREEN_STATE_TEMP);
        return false;
    }
    unlock_notice = unlocked;
    lock_notice = locked;
    screen_state_loaded = true;
    return true;
}

#if defined(HAVE_TOUCHSCREEN) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
#define SCREEN_LOCK_POLICY_FILE ROCKBOX_DIR "/accessibility-lock.cfg"
#define SCREEN_LOCK_POLICY_TEMP ROCKBOX_DIR "/accessibility-lock.cfg.tmp"
#define SCREEN_LOCK_POLICY_V1 \
    "RBACCESSIBILITY-LOCK:1\nunlock-button:0\nphysical-buttons:0\n"
#define SCREEN_LOCK_POLICY_DEFAULT \
    "RBACCESSIBILITY-LOCK:2\nunlock-button:0\nphysical-buttons:0\ntimeout:-1\n"
#define SCREEN_LOCK_TIMEOUT_MAX 600

static bool unlock_any_button;
static bool locked_physical_buttons;
static bool screen_lock_policy_loaded;
static int screen_autolock_timeout = -1;

static void screen_lock_policy_load(void)
{
    if (screen_lock_policy_loaded)
        return;
    screen_lock_policy_loaded = true;
    char data[sizeof(SCREEN_LOCK_POLICY_DEFAULT) + 2];
    size_t used = 0;
    int descriptor = open(SCREEN_LOCK_POLICY_FILE, O_RDONLY);
    if (descriptor < 0)
        return;
    bool valid = true;
    while (used < sizeof(data))
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0)
        {
            valid = false;
            break;
        }
        if (!count)
            break;
        used += count;
    }
    if (close(descriptor) != 0)
        valid = false;
    const size_t prefix = sizeof(SCREEN_LOCK_POLICY_V1) - 1;
    if (!valid || used < prefix)
        return;
    const size_t unlock_offset = sizeof("RBACCESSIBILITY-LOCK:1\nunlock-button:") - 1;
    const size_t physical_offset = sizeof("RBACCESSIBILITY-LOCK:1\nunlock-button:0\nphysical-buttons:") - 1;
    char unlocked = data[unlock_offset];
    char physical = data[physical_offset];
    const size_t version_offset = sizeof("RBACCESSIBILITY-LOCK:") - 1;
    char version = data[version_offset];
    data[unlock_offset] = data[physical_offset] = '0';
    data[version_offset] = '1';
    if ((unlocked != '0' && unlocked != '1') ||
        (physical != '0' && physical != '1') ||
        memcmp(data, SCREEN_LOCK_POLICY_V1, prefix))
        return;
    int timeout = -1;
    if (version == '1')
    {
        if (used != prefix)
            return;
    }
    else if (version == '2')
    {
        const size_t number_offset = prefix + sizeof("timeout:") - 1;
        if (used <= number_offset + 1 || memcmp(data + prefix, "timeout:", 8) ||
            data[used - 1] != '\n')
            return;
        if (used == number_offset + 3 && !memcmp(data + number_offset, "-1\n", 3))
            timeout = -1;
        else
        {
            timeout = 0;
            if (used > number_offset + 2 && data[number_offset] == '0')
                return;
            for (size_t position = number_offset; position < used - 1; ++position)
            {
                if (data[position] < '0' || data[position] > '9' ||
                    timeout > (SCREEN_LOCK_TIMEOUT_MAX - (data[position] - '0')) / 10)
                    return;
                timeout = timeout * 10 + data[position] - '0';
            }
        }
    }
    else
        return;
    unlock_any_button = unlocked == '1';
    locked_physical_buttons = physical == '1';
    screen_autolock_timeout = timeout;
}

static bool screen_lock_policy_save(bool unlock_button, bool physical_buttons, int timeout)
{
    if (timeout < -1 || timeout > SCREEN_LOCK_TIMEOUT_MAX)
        return false;
    char data[sizeof(SCREEN_LOCK_POLICY_DEFAULT) + 2];
    int length = snprintf(data, sizeof(data),
        "RBACCESSIBILITY-LOCK:2\nunlock-button:%u\nphysical-buttons:%u\ntimeout:%d\n",
        (unsigned int)unlock_button, (unsigned int)physical_buttons, timeout);
    if (length <= 0 || (size_t)length >= sizeof(data))
        return false;
    int descriptor = open(SCREEN_LOCK_POLICY_TEMP, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (descriptor < 0)
        return false;
    bool valid = true;
    size_t used = 0;
    while (used < (size_t)length)
    {
        ssize_t count = write(descriptor, data + used, (size_t)length - used);
        if (count <= 0)
        {
            valid = false;
            break;
        }
        used += count;
    }
    if (valid && fsync(descriptor) != 0)
        valid = false;
    if (close(descriptor) != 0)
        valid = false;
    if (!valid || rename(SCREEN_LOCK_POLICY_TEMP, SCREEN_LOCK_POLICY_FILE) != 0)
    {
        remove(SCREEN_LOCK_POLICY_TEMP);
        return false;
    }
    unlock_any_button = unlock_button;
    locked_physical_buttons = physical_buttons;
    screen_autolock_timeout = timeout;
    screen_lock_policy_loaded = true;
    return true;
}

bool accessibility_screen_unlock_any_button(void)
{
    screen_lock_policy_load();
    return unlock_any_button;
}

bool accessibility_screen_locked_buttons(void)
{
    screen_lock_policy_load();
    return locked_physical_buttons;
}

int accessibility_screen_autolock_timeout(void)
{
    screen_lock_policy_load();
    return screen_autolock_timeout;
}

int accessibility_screen_autolock_menu(void)
{
    static const int durations[] = {-1, 0, 5, 10, 15, 30, 45, 60, 120, 180, 300, 600};
    screen_lock_policy_load();
    struct opt_items options[ARRAYLEN(durations) + 1];
    char labels[ARRAYLEN(durations) + 1][16];
    int choice = -1;
    unsigned int count = ARRAYLEN(durations);
    for (unsigned int index = 0; index < count; ++index)
    {
        if (durations[index] == screen_autolock_timeout)
            choice = index;
        options[index].voice_id = index == 0 ? LANG_ACCESSIBILITY_AUTOLOCK_LEGACY :
            index == 1 ? LANG_OFF : TALK_ID(durations[index], UNIT_SEC);
        snprintf(labels[index], sizeof(labels[index]), "%d s", durations[index]);
        options[index].string = index < 2 ?
            (const unsigned char *)str(options[index].voice_id) : (const unsigned char *)labels[index];
    }
    if (choice < 0)
    {
        choice = count++;
        snprintf(labels[choice], sizeof(labels[choice]), "%d s", screen_autolock_timeout);
        options[choice].string = (const unsigned char *)labels[choice];
        options[choice].voice_id = TALK_ID(screen_autolock_timeout, UNIT_SEC);
    }
    if (set_option(str(LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT), &choice, RB_INT,
                   options, count, NULL))
        return MENU_ATTACHED_USB;
    if (choice < 0 || (unsigned int)choice >= count)
        return 0;
    int timeout = choice < (int)ARRAYLEN(durations) ? durations[choice] : screen_autolock_timeout;
    if (timeout != screen_autolock_timeout &&
        !screen_lock_policy_save(unlock_any_button, locked_physical_buttons, timeout))
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    return 0;
}

int accessibility_screen_unlock_any_button_menu(void)
{
    screen_lock_policy_load();
    bool choice = unlock_any_button;
    if (set_bool(str(LANG_ACCESSIBILITY_UNLOCK_ANY_BUTTON), &choice))
        return MENU_ATTACHED_USB;
    if (choice != unlock_any_button &&
        !screen_lock_policy_save(choice, locked_physical_buttons, screen_autolock_timeout))
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    return 0;
}

int accessibility_screen_locked_buttons_menu(void)
{
    screen_lock_policy_load();
    bool choice = locked_physical_buttons;
    if (set_bool(str(LANG_ACCESSIBILITY_LOCKED_BUTTONS), &choice))
        return MENU_ATTACHED_USB;
    if (choice != locked_physical_buttons &&
        !screen_lock_policy_save(unlock_any_button, choice, screen_autolock_timeout))
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    return 0;
}
#endif

static bool screen_clock_snapshot(struct tm *snapshot)
{
#if CONFIG_RTC
    const struct tm *current = get_time();
    if (current)
        *snapshot = *current;
    return valid_time(current ? snapshot : NULL);
#else
    (void)snapshot;
    return false;
#endif
}

static void screen_speak_clock(const struct tm *snapshot, bool date, bool enqueue)
{
    talk_id(date ? LANG_DATE : LANG_CURRENT_TIME, enqueue);
    if (!snapshot)
        talk_id(LANG_UNKNOWN, true);
    else if (date)
        talk_date(snapshot, true);
    else
        talk_time(snapshot, true);
}

bool accessibility_speak_time(bool enqueue)
{
    if (!talk_menus_enabled(&global_settings))
        return false;
    struct tm snapshot;
    bool valid = screen_clock_snapshot(&snapshot);
    screen_speak_clock(valid ? &snapshot : NULL, false, enqueue);
    return valid;
}

bool accessibility_speak_date(bool enqueue)
{
    if (!talk_menus_enabled(&global_settings))
        return false;
    struct tm snapshot;
    bool valid = screen_clock_snapshot(&snapshot);
    screen_speak_clock(valid ? &snapshot : NULL, true, enqueue);
    return valid;
}

static void screen_track_name(const struct mp3entry *track, char *name, size_t capacity)
{
    const char *source = NULL;
    uintptr_t start = (uintptr_t)track;
    uintptr_t title = (uintptr_t)track->title;
    if (title >= start && title - start < sizeof(*track) &&
        memchr(track->title, '\0', sizeof(*track) - (title - start)) &&
        track->title[0])
        source = track->title;
    if (!source && memchr(track->path, '\0', sizeof(track->path)))
    {
        const char *separator = strrchr(track->path, '/');
        source = separator ? separator + 1 : track->path;
    }
    if (!source)
    {
        name[0] = '\0';
        return;
    }
    size_t length = strlen(source);
    if (length >= capacity)
    {
        length = capacity - 1;
        while (length && ((unsigned char)source[length] & 0xc0) == 0x80)
            --length;
    }
    memcpy(name, source, length);
    name[length] = '\0';
}

void accessibility_speak_summary(bool enqueue)
{
    if (!talk_menus_enabled(&global_settings))
        return;
    static struct mp3entry track;
    static char name[MAX_PATH];
    memset(&track, 0, sizeof(track));
    name[0] = '\0';
    if ((audio_status() & AUDIO_STATUS_PLAY) && audio_peek_track(&track, 0))
        screen_track_name(&track, name, sizeof(name));
    struct tm snapshot;
    bool valid = screen_clock_snapshot(&snapshot);
    int level = battery_level();
    talk_id(LANG_TRACK, enqueue);
    if (name[0])
        talk_spell(name, true);
    else
        talk_id(LANG_UNKNOWN, true);
    screen_speak_clock(valid ? &snapshot : NULL, false, true);
    screen_speak_clock(valid ? &snapshot : NULL, true, true);
    talk_id(LANG_BATTERY_CHARGE, true);
    if (level >= 0 && level <= 100)
        talk_value(level, UNIT_PERCENT, true);
    else
        talk_id(LANG_UNKNOWN, true);
}

void accessibility_speak_battery(bool enqueue)
{
    if (!talk_menus_enabled(&global_settings))
        return;
    talk_id(LANG_BATTERY_CHARGE, enqueue);
    int level = battery_level();
    if (level >= 0 && level <= 100)
        talk_value(level, UNIT_PERCENT, true);
    else
        talk_id(LANG_UNKNOWN, true);
}

void accessibility_screen_lock_changed(bool locked)
{
    screen_state_load();
    if (!talk_menus_enabled(&global_settings))
        return;
    if (locked)
    {
        if (lock_notice == SCREEN_LOCK_STATE)
        {
            talk_id(LANG_ACCESSIBILITY_SCREEN_LOCKED, false);
            talk_force_enqueue_next();
        }
        return;
    }
    bool enqueue = false;
    if (unlock_notice == SCREEN_UNLOCK_STATE || unlock_notice == SCREEN_UNLOCK_ALL)
    {
        talk_id(LANG_ACCESSIBILITY_SCREEN_UNLOCKED, enqueue);
        enqueue = true;
    }
    if (unlock_notice == SCREEN_UNLOCK_TIME ||
        unlock_notice == SCREEN_UNLOCK_TIME_BATTERY || unlock_notice == SCREEN_UNLOCK_ALL)
    {
        accessibility_speak_time(enqueue);
        enqueue = true;
    }
    if (unlock_notice == SCREEN_UNLOCK_BATTERY ||
        unlock_notice == SCREEN_UNLOCK_TIME_BATTERY || unlock_notice == SCREEN_UNLOCK_ALL)
        accessibility_speak_battery(enqueue);
    if (unlock_notice != SCREEN_UNLOCK_SILENT)
        talk_force_enqueue_next();
}

int accessibility_screen_unlock_menu(void)
{
    static const struct opt_items options[] = {
        { STR(LANG_ACCESSIBILITY_SCREEN_SAY_UNLOCKED) },
        { STR(LANG_ACCESSIBILITY_ACTION_TIME) },
        { STR(LANG_ACCESSIBILITY_BATTERY) },
        { STR(LANG_ACCESSIBILITY_NOTICE_TIME_BATTERY) },
        { STR(LANG_ACCESSIBILITY_NOTICE_ALL) },
        { STR(LANG_ACCESSIBILITY_NOTICE_SILENT) }
    };
    screen_state_load();
    int choice = unlock_notice;
    if (set_option(str(LANG_ACCESSIBILITY_SCREEN_UNLOCK_NOTICE), &choice, RB_INT,
                   options, SCREEN_UNLOCK_COUNT, NULL))
        return MENU_ATTACHED_USB;
    if (choice != (int)unlock_notice && !screen_state_save(choice, lock_notice))
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    return 0;
}

int accessibility_screen_lock_menu(void)
{
    static const struct opt_items options[] = {
        { STR(LANG_ACCESSIBILITY_SCREEN_SAY_LOCKED) },
        { STR(LANG_ACCESSIBILITY_NOTICE_SILENT) }
    };
    screen_state_load();
    int choice = lock_notice;
    if (set_option(str(LANG_ACCESSIBILITY_SCREEN_LOCK_NOTICE), &choice, RB_INT,
                   options, SCREEN_LOCK_COUNT, NULL))
        return MENU_ATTACHED_USB;
    if (choice != (int)lock_notice && !screen_state_save(unlock_notice, choice))
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    return 0;
}

#endif
