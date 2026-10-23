/* Modified for Rockbox Accessible; change notice dated 2026-10-23. */
#include "config.h"
#include "file.h"
#include "rbpaths.h"
#include "tts_reader_settings.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>

#define READER_SETTINGS_FILE ROCKBOX_DIR "/tts-reader.cfg"
#define READER_SETTINGS_TEMP ROCKBOX_DIR "/tts-reader.cfg.tmp"
#define READER_SETTINGS_FORMAT "RBTTSREADER:1\ncase:%u\nwrap:%u\n"
#define READER_SETTINGS_CAPACITY 64
#define READER_SETTINGS_ATTEMPTS 4

/* Main-context-only, independent of user_settings and the plugin ABI. */
static struct tts_reader_preferences current_preferences;
static bool preferences_loaded;

static int reader_settings_error(void)
{
    return errno > 0 ? errno : EIO;
}

static int reader_settings_open(const char *path, int flags)
{
    int descriptor;
    unsigned int attempts = 0;
    do
    {
        descriptor = open(path, flags, 0600);
    } while (descriptor < 0 && errno == EINTR &&
             ++attempts < READER_SETTINGS_ATTEMPTS);
    return descriptor;
}

static int reader_settings_render(const struct tts_reader_preferences *preferences,
                                  char *data, size_t capacity)
{
    return snprintf(data, capacity, READER_SETTINGS_FORMAT,
                    (unsigned int)preferences->match_case,
                    (unsigned int)preferences->wrap);
}

static int reader_settings_load(struct tts_reader_preferences *out)
{
    memset(out, 0, sizeof(*out));
    int descriptor = reader_settings_open(READER_SETTINGS_FILE, O_RDONLY);
    if (descriptor < 0)
        return errno == ENOENT ? 0 : reader_settings_error();
    char data[READER_SETTINGS_CAPACITY];
    size_t used = 0;
    unsigned int interrupted = 0;
    int error = 0;
    while (used < sizeof(data))
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0 && errno == EINTR &&
            ++interrupted < READER_SETTINGS_ATTEMPTS)
            continue;
        if (count < 0)
        {
            error = reader_settings_error();
            break;
        }
        if (!count)
            break;
        used += (size_t)count;
    }
    /* A simulator descriptor is invalidated even when close fails. */
    if (close(descriptor) != 0 && !error)
        error = reader_settings_error();
    if (error)
        return error;
    if (used != 28 || data[19] < '0' || data[19] > '1' ||
        data[26] < '0' || data[26] > '2')
        return EINVAL;
    out->match_case = data[19] == '1';
    out->wrap = (enum tts_reader_wrap)(data[26] - '0');
    char canonical[READER_SETTINGS_CAPACITY];
    int length = reader_settings_render(out, canonical, sizeof(canonical));
    return length == (int)used && !memcmp(data, canonical, used) ? 0 : EINVAL;
}

int tts_reader_preferences_get(struct tts_reader_preferences *out)
{
    if (!out)
        return EINVAL;
    if (!preferences_loaded)
    {
        struct tts_reader_preferences initial;
        int error = reader_settings_load(&initial);
        preferences_loaded = true;
        if (!error)
            current_preferences = initial;
        else
            current_preferences.storage_error = error;
    }
    *out = current_preferences;
    return out->storage_error;
}

static int reader_settings_write(int descriptor,
                                 const struct tts_reader_preferences *preferences)
{
    char data[READER_SETTINGS_CAPACITY];
    int length = reader_settings_render(preferences, data, sizeof(data));
    int error = length < 0 || length >= (int)sizeof(data) ? EINVAL : 0;
    size_t used = 0;
    unsigned int interrupted = 0;
    while (!error && used < (size_t)length)
    {
        ssize_t count = write(descriptor, data + used, (size_t)length - used);
        if (count < 0 && errno == EINTR &&
            ++interrupted < READER_SETTINGS_ATTEMPTS)
            continue;
        if (count <= 0)
            error = count < 0 ? reader_settings_error() : EIO;
        else
            used += (size_t)count;
    }
    if (!error)
    {
        unsigned int attempts = 0;
        int result;
        do
        {
            result = fsync(descriptor);
        } while (result != 0 && errno == EINTR &&
                 ++attempts < READER_SETTINGS_ATTEMPTS);
        if (result != 0)
            error = reader_settings_error();
    }
    if (close(descriptor) != 0 && !error)
        error = reader_settings_error();
    return error;
}

int tts_reader_preferences_set(enum tts_reader_preference preference, int value)
{
    if (!((preference == TTS_READER_PREF_MATCH_CASE && value >= 0 && value <= 1) ||
          (preference == TTS_READER_PREF_WRAP && value >= TTS_READER_WRAP_STOP &&
           value <= TTS_READER_WRAP_AUTO)))
        return EINVAL;
    /* Populate a safe previous pair before attempting an update. */
    struct tts_reader_preferences previous;
    tts_reader_preferences_get(&previous);
    int descriptor = reader_settings_open(READER_SETTINGS_TEMP,
                                          O_WRONLY | O_CREAT | O_EXCL);
    if (descriptor < 0)
    {
        current_preferences.storage_error = reader_settings_error();
        current_preferences.cleanup_error = 0;
        return current_preferences.storage_error;
    }
    current_preferences.cleanup_error = 0;
    /* Owning the exclusive temp serializes cooperating reader writers. */
    struct tts_reader_preferences next;
    int error = reader_settings_load(&next);
    if (!error)
    {
        if (preference == TTS_READER_PREF_MATCH_CASE)
            next.match_case = value != 0;
        else
            next.wrap = (enum tts_reader_wrap)value;
        error = reader_settings_write(descriptor, &next); /* exactly one close */
    }
    else if (close(descriptor) != 0)
    {
        /* Preserve the validation error and disclose the cleanup failure too. */
        current_preferences.cleanup_error = reader_settings_error();
    }
    if (!error && rename(READER_SETTINGS_TEMP, READER_SETTINGS_FILE) != 0)
        error = reader_settings_error();
    int cleanup_error = current_preferences.cleanup_error;
    if (error && remove(READER_SETTINGS_TEMP) != 0)
        cleanup_error = reader_settings_error();
    if (!error)
    {
        current_preferences = next;
        preferences_loaded = true;
    }
    else
    {
        current_preferences = previous;
        current_preferences.storage_error = error;
        current_preferences.cleanup_error = cleanup_error;
    }
    return error;
}
