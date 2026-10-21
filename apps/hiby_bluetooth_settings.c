#ifndef HIBY_BT_SETTINGS_HOST_TEST
#include "config.h"
#include "file.h"
#include "rbpaths.h"
#else
#include <fcntl.h>
#include <unistd.h>
#endif

#include "hiby_bluetooth_settings.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

#define BT_SETTINGS_FILE ROCKBOX_DIR "/bluetooth.cfg"
#define BT_SETTINGS_TEMP ROCKBOX_DIR "/bluetooth.cfg.tmp"
#define BT_SETTINGS_FORMAT "RBBLUETOOTH:1\nauto:%u\nretry:%u\npause:%u\nannounce:%u\nlast:%s\n"
#define BT_SETTINGS_CAPACITY 128
#define BT_SETTINGS_IO_ATTEMPTS 4

#if !defined(SIMULATOR) && (defined(HIBY_LINUX) || defined(HIBY_BT_SETTINGS_HOST_TEST))
#include <pthread.h>
static pthread_mutex_t preferences_mutex = PTHREAD_MUTEX_INITIALIZER;
#define LOCK() pthread_mutex_lock(&preferences_mutex)
#define UNLOCK() pthread_mutex_unlock(&preferences_mutex)
#else
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
#endif

static const struct hiby_bt_preferences defaults = {
    .auto_mode = BLUETOOTH_RECONNECT_STARTUP_AND_LOSS,
    .retry_seconds = 120,
    .pause_on_loss = true,
    .announce = true
};
static struct hiby_bt_preferences current = {
    .auto_mode = BLUETOOTH_RECONNECT_STARTUP_AND_LOSS,
    .retry_seconds = 120,
    .pause_on_loss = true,
    .announce = true
};
static int storage_error;
static bool loaded;

static int io_error(void)
{
    return errno > 0 ? errno : EIO;
}

static bool valid_retry(unsigned int seconds)
{
    return seconds == 30 || seconds == 60 || seconds == 120 || seconds == 300;
}

static bool normalize_address(const char *address, char normalized[18])
{
    if (!address)
        return false;
    for (size_t position = 0; position < 17; position++)
    {
        unsigned char character = (unsigned char)address[position];
        if (position % 3 == 2)
        {
            if (character != ':')
                return false;
        }
        else if (character >= 'a' && character <= 'f')
            character -= 'a' - 'A';
        else if (!((character >= '0' && character <= '9') ||
                   (character >= 'A' && character <= 'F')))
            return false;
        normalized[position] = (char)character;
    }
    normalized[17] = '\0';
    return address[17] == '\0';
}

static int open_file(const char *path, int flags)
{
    int descriptor;
    unsigned int attempts = 0;
    do
    {
        descriptor = open(path, flags, 0600);
    } while (descriptor < 0 && errno == EINTR && ++attempts < BT_SETTINGS_IO_ATTEMPTS);
    return descriptor;
}

static int render(const struct hiby_bt_preferences *preferences, char *data, size_t capacity)
{
    return snprintf(data, capacity, BT_SETTINGS_FORMAT,
        (unsigned int)preferences->auto_mode, preferences->retry_seconds,
        (unsigned int)preferences->pause_on_loss, (unsigned int)preferences->announce,
        preferences->last_address);
}

static bool consume(const char **cursor, const char *end, const char *literal)
{
    size_t length = strlen(literal);
    if ((size_t)(end - *cursor) < length || memcmp(*cursor, literal, length))
        return false;
    *cursor += length;
    return true;
}

static bool number(const char **cursor, const char *end, const char *key, unsigned int *value)
{
    if (!consume(cursor, end, key))
        return false;
    *value = 0;
    size_t digits = 0;
    bool leading_zero = *cursor < end && **cursor == '0';
    while (*cursor < end && **cursor >= '0' && **cursor <= '9')
    {
        unsigned int digit = (unsigned int)(**cursor - '0');
        if (*value > (UINT_MAX - digit) / 10 || ++digits > 3)
            return false;
        *value = *value * 10 + digit;
        (*cursor)++;
    }
    return digits && !(leading_zero && digits > 1) && consume(cursor, end, "\n");
}

static int parse(const char *data, size_t length, struct hiby_bt_preferences *preferences)
{
    const char *cursor = data;
    const char *end = data + length;
    unsigned int mode, pause, announce, retry;
    if (!consume(&cursor, end, "RBBLUETOOTH:1\n") ||
        !number(&cursor, end, "auto:", &mode) || mode > 2 ||
        !number(&cursor, end, "retry:", &retry) || !valid_retry(retry) ||
        !number(&cursor, end, "pause:", &pause) || pause > 1 ||
        !number(&cursor, end, "announce:", &announce) || announce > 1 ||
        !consume(&cursor, end, "last:") ||
        (end - cursor != 1 && end - cursor != 18) || end[-1] != '\n')
        return EINVAL;
    if (end - cursor == 18)
    {
        char address[18];
        memcpy(address, cursor, 17);
        address[17] = '\0';
        if (!normalize_address(address, preferences->last_address) ||
            memcmp(address, preferences->last_address, sizeof(address)))
            return EINVAL;
    }
    preferences->auto_mode = (enum bluetooth_reconnect_mode)mode;
    preferences->retry_seconds = retry;
    preferences->pause_on_loss = pause != 0;
    preferences->announce = announce != 0;
    char canonical[BT_SETTINGS_CAPACITY];
    int canonical_length = render(preferences, canonical, sizeof(canonical));
    return canonical_length == (int)length && !memcmp(data, canonical, length) ? 0 : EINVAL;
}

static int load(struct hiby_bt_preferences *preferences)
{
    *preferences = defaults;
    int descriptor = open_file(BT_SETTINGS_FILE, O_RDONLY);
    if (descriptor < 0)
        return errno == ENOENT ? 0 : io_error();
    char data[BT_SETTINGS_CAPACITY];
    size_t used = 0;
    unsigned int interrupted = 0;
    int error = 0;
    while (used < sizeof(data))
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0 && errno == EINTR && ++interrupted < BT_SETTINGS_IO_ATTEMPTS)
            continue;
        if (count < 0)
        {
            error = io_error();
            break;
        }
        if (!count)
            break;
        used += (size_t)count;
    }
    if (close(descriptor) != 0 && !error)
        error = io_error();
    if (error)
        return error;
    return parse(data, used, preferences);
}

static bool equal(const struct hiby_bt_preferences *left,
                  const struct hiby_bt_preferences *right)
{
    return left->auto_mode == right->auto_mode && left->retry_seconds == right->retry_seconds &&
        left->pause_on_loss == right->pause_on_loss && left->announce == right->announce &&
        !strcmp(left->last_address, right->last_address);
}

static void publish(struct hiby_bt_preferences *preferences)
{
    preferences->generation = current.generation;
    if (!equal(preferences, &current) && preferences->generation < UINT_MAX)
        preferences->generation++;
    current = *preferences;
    loaded = true;
}

int hiby_bt_preferences_get(struct hiby_bt_preferences *preferences)
{
    if (!preferences)
        return EINVAL;
    LOCK();
    if (!loaded)
    {
        struct hiby_bt_preferences initial;
        int error = load(&initial);
        loaded = true;
        if (!error)
            publish(&initial);
        else
            storage_error = error;
    }
    *preferences = current;
    int error = storage_error;
    UNLOCK();
    return error;
}

static int persist(int descriptor, const struct hiby_bt_preferences *preferences)
{
    char data[BT_SETTINGS_CAPACITY];
    int length = render(preferences, data, sizeof(data));
    int error = length < 0 || length >= (int)sizeof(data) ? EINVAL : 0;
    size_t written = 0;
    unsigned int interrupted = 0;
    while (!error && written < (size_t)length)
    {
        ssize_t count = write(descriptor, data + written, (size_t)length - written);
        if (count < 0 && errno == EINTR && ++interrupted < BT_SETTINGS_IO_ATTEMPTS)
            continue;
        if (count <= 0)
            error = count < 0 ? io_error() : EIO;
        else
            written += (size_t)count;
    }
    if (!error)
    {
        unsigned int attempts = 0;
        int result;
        do
        {
            result = fsync(descriptor);
        } while (result != 0 && errno == EINTR && ++attempts < BT_SETTINGS_IO_ATTEMPTS);
        if (result != 0)
            error = io_error();
    }
    if (close(descriptor) != 0 && !error)
        error = io_error();
    if (!error && rename(BT_SETTINGS_TEMP, BT_SETTINGS_FILE) != 0)
        error = io_error();
    if (error)
        remove(BT_SETTINGS_TEMP);
    return error;
}

static int update(enum hiby_bt_preference preference, int value,
                  const char *address, bool forget)
{
    LOCK();
    int descriptor = open_file(BT_SETTINGS_TEMP, O_WRONLY | O_CREAT | O_EXCL);
    if (descriptor < 0)
    {
        int error = io_error();
        storage_error = error;
        UNLOCK();
        return error;
    }
    struct hiby_bt_preferences next;
    int error = load(&next);
    struct hiby_bt_preferences previous = next;
    if (!error)
    {
        if (address)
        {
            if (!forget)
                memcpy(next.last_address, address, sizeof(next.last_address));
            else if (!strcmp(next.last_address, address))
                memset(next.last_address, 0, sizeof(next.last_address));
        }
        else switch (preference)
        {
            case HIBY_BT_PREF_AUTOCONNECT: next.auto_mode = (enum bluetooth_reconnect_mode)value; break;
            case HIBY_BT_PREF_RETRY_SECONDS: next.retry_seconds = (unsigned int)value; break;
            case HIBY_BT_PREF_PAUSE_ON_LOSS: next.pause_on_loss = value != 0; break;
            case HIBY_BT_PREF_ANNOUNCE: next.announce = value != 0; break;
        }
    }
    if (error || (equal(&next, &previous) && !storage_error))
    {
        if (close(descriptor) != 0 && !error)
            error = io_error();
        if (remove(BT_SETTINGS_TEMP) != 0 && !error)
            error = io_error();
    }
    else
        error = persist(descriptor, &next);
    if (!error)
        publish(&next);
    storage_error = error;
    UNLOCK();
    return error;
}

int hiby_bt_preferences_set(enum hiby_bt_preference preference, int value)
{
    if ((preference == HIBY_BT_PREF_AUTOCONNECT && value >= 0 && value <= 2) ||
        (preference == HIBY_BT_PREF_RETRY_SECONDS && value > 0 && valid_retry((unsigned int)value)) ||
        ((preference == HIBY_BT_PREF_PAUSE_ON_LOSS || preference == HIBY_BT_PREF_ANNOUNCE) &&
         (value == 0 || value == 1)))
        return update(preference, value, NULL, false);
    return EINVAL;
}

int hiby_bt_preferences_remember(const char *address)
{
    char normalized[18];
    return normalize_address(address, normalized) ?
        update(HIBY_BT_PREF_AUTOCONNECT, 0, normalized, false) : EINVAL;
}

int hiby_bt_preferences_forget(const char *address)
{
    char normalized[18];
    return normalize_address(address, normalized) ?
        update(HIBY_BT_PREF_AUTOCONNECT, 0, normalized, true) : EINVAL;
}
