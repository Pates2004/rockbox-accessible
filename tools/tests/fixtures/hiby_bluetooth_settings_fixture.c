#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int fault_operation;
static int fault_mode;
static unsigned int fault_budget;
static unsigned int fault_calls;
static int temporary_descriptor = -1;
static unsigned int requested_mode;
static unsigned int io_calls[10];

static bool fail_operation(int operation)
{
    if (operation != fault_operation)
        return false;
    fault_calls++;
    if (fault_mode == 2 && fault_calls > fault_budget)
        return false;
    if (fault_mode == 4)
        return false;
    errno = fault_mode == 2 ? EINTR : fault_mode == 5 ? 0 : EIO;
    return true;
}

static int test_open(const char *path, int flags, ...)
{
    bool temporary = strstr(path, ".tmp") != NULL;
    io_calls[temporary ? 2 : 1]++;
    if (temporary)
    {
        va_list arguments;
        va_start(arguments, flags);
        requested_mode = (unsigned int)va_arg(arguments, int);
        va_end(arguments);
        assert(requested_mode == 0600);
        assert((flags & (O_CREAT | O_EXCL)) == (O_CREAT | O_EXCL));
    }
    if (fail_operation(temporary ? 2 : 1))
        return -1;
    int descriptor = open(path, flags, 0600);
    if (temporary && descriptor >= 0)
        temporary_descriptor = descriptor;
    return descriptor;
}

static ssize_t test_read(int descriptor, void *data, size_t count)
{
    io_calls[3]++;
    if (fault_operation == 3 && fault_mode == 3)
    {
        fault_calls++;
        return 0;
    }
    if (fail_operation(3))
        return -1;
    return read(descriptor, data, fault_operation == 3 && fault_mode == 4 ? 1 : count);
}

static ssize_t test_write(int descriptor, const void *data, size_t count)
{
    io_calls[4]++;
    if (fault_operation == 4 && fault_mode == 3)
    {
        fault_calls++;
        return 0;
    }
    if (fail_operation(4))
        return -1;
    return write(descriptor, data, fault_operation == 4 && fault_mode == 4 ? 1 : count);
}

static int test_fsync(int descriptor)
{
    io_calls[5]++;
    return fail_operation(5) ? -1 : fsync(descriptor);
}

static int test_close(int descriptor)
{
    int operation = descriptor == temporary_descriptor ? 7 : 6;
    io_calls[operation]++;
    if (descriptor == temporary_descriptor)
        temporary_descriptor = -1;
    int result = close(descriptor);
    return fail_operation(operation) ? -1 : result;
}

static int test_rename(const char *source, const char *destination)
{
    io_calls[8]++;
    return fail_operation(8) ? -1 : rename(source, destination);
}

static int test_remove(const char *path)
{
    io_calls[9]++;
    return fail_operation(9) ? -1 : remove(path);
}

#define open test_open
#define read test_read
#define write test_write
#define fsync test_fsync
#define close test_close
#define rename test_rename
#define remove test_remove
#include "hiby_bluetooth_settings.c"
#undef open
#undef read
#undef write
#undef fsync
#undef close
#undef rename
#undef remove

static void print_preferences(int error, const struct hiby_bt_preferences *preferences)
{
    printf("{\"error\":%d,\"auto\":%u,\"retry\":%u,\"pause\":%u,\"announce\":%u,"
           "\"peer\":\"%s\",\"generation\":%u,\"fault_calls\":%u,\"requested_mode\":%u,"
           "\"read_opens\":%u,\"reads\":%u,\"read_closes\":%u}\n", error,
        (unsigned int)preferences->auto_mode, preferences->retry_seconds,
        (unsigned int)preferences->pause_on_loss, (unsigned int)preferences->announce,
        preferences->last_address, preferences->generation, fault_calls, requested_mode,
        io_calls[1], io_calls[3], io_calls[6]);
}

#ifndef SIMULATOR
static void *concurrent_update(void *context)
{
    int role = *(int *)context;
    for (unsigned int iteration = 0; iteration < 80; iteration++)
    {
        if (role == 0)
            assert(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, iteration % 3) == 0);
        else if (role == 1)
        {
            const unsigned int windows[] = {30, 60, 120, 300};
            assert(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, windows[iteration % 4]) == 0);
        }
        else if (role == 2)
            assert(hiby_bt_preferences_remember("aa:bb:cc:dd:ee:ff") == 0);
        else
        {
            assert(hiby_bt_preferences_set(HIBY_BT_PREF_PAUSE_ON_LOSS, 0) == 0);
            assert(hiby_bt_preferences_set(HIBY_BT_PREF_ANNOUNCE, 0) == 0);
        }
        struct hiby_bt_preferences observed;
        assert(hiby_bt_preferences_get(&observed) == 0);
        assert(observed.auto_mode >= 0 && observed.auto_mode <= 2);
        assert(valid_retry(observed.retry_seconds));
    }
    if (role == 0)
        assert(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, 1) == 0);
    return NULL;
}
#endif

int main(int argc, char **argv)
{
    assert(argc >= 2);
    struct hiby_bt_preferences preferences;
    int error = 0;
    if (!strcmp(argv[1], "read"))
        error = hiby_bt_preferences_get(&preferences);
    else if (!strcmp(argv[1], "set"))
    {
        assert(argc == 4);
        hiby_bt_preferences_get(&preferences);
        error = hiby_bt_preferences_set((enum hiby_bt_preference)atoi(argv[2]), atoi(argv[3]));
        preferences = current;
    }
    else if (!strcmp(argv[1], "remember") || !strcmp(argv[1], "forget"))
    {
        assert(argc == 3);
        error = !strcmp(argv[1], "remember") ? hiby_bt_preferences_remember(argv[2]) :
                                               hiby_bt_preferences_forget(argv[2]);
        preferences = current;
    }
    else if (!strcmp(argv[1], "fault"))
    {
        assert(argc == 5);
        assert(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, 30) == 0);
        struct hiby_bt_preferences before = current;
        fault_operation = atoi(argv[2]);
        fault_mode = atoi(argv[3]);
        fault_budget = (unsigned int)atoi(argv[4]);
        error = hiby_bt_preferences_set(HIBY_BT_PREF_ANNOUNCE, 0);
        fault_operation = 0;
        if (error)
        {
            assert(equal(&before, &current));
            assert(before.generation == current.generation);
            struct hiby_bt_preferences observed;
            assert(hiby_bt_preferences_get(&observed) == error);
            assert(equal(&before, &observed));
        }
        preferences = current;
    }
    else if (!strcmp(argv[1], "sticky-read-error"))
    {
        assert(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, 30) == 0);
        loaded = false;
        current = defaults;
        fault_operation = 3;
        fault_mode = 1;
        assert(hiby_bt_preferences_get(&preferences) == EIO);
        fault_operation = 0;
        assert(hiby_bt_preferences_get(&preferences) == EIO);
        assert(preferences.retry_seconds == 120);
        assert(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, 30) == 0);
        assert(hiby_bt_preferences_get(&preferences) == 0);
        assert(preferences.retry_seconds == 30);
    }
    else if (!strcmp(argv[1], "cached-get"))
    {
        error = hiby_bt_preferences_get(&preferences);
        struct hiby_bt_preferences before = preferences;
        unsigned int previous_calls[10];
        memcpy(previous_calls, io_calls, sizeof(previous_calls));
        for (unsigned int iteration = 0; iteration < 1000; iteration++)
        {
            assert(hiby_bt_preferences_get(&preferences) == error);
            assert(equal(&before, &preferences));
            assert(before.generation == preferences.generation);
        }
        assert(!memcmp(previous_calls, io_calls, sizeof(previous_calls)));
    }
    else if (!strcmp(argv[1], "cached-external-edit"))
    {
        assert(hiby_bt_preferences_get(&preferences) == 0);
        assert(preferences.auto_mode == 2 && preferences.retry_seconds == 120);
        FILE *external = fopen("bluetooth.cfg", "w");
        assert(external);
        assert(fputs("RBBLUETOOTH:1\nauto:1\nretry:30\npause:0\nannounce:0\nlast:\n", external) >= 0);
        assert(fclose(external) == 0);
        unsigned int opens = io_calls[1];
        assert(hiby_bt_preferences_get(&preferences) == 0);
        assert(preferences.auto_mode == 2 && preferences.retry_seconds == 120);
        assert(io_calls[1] == opens);
        assert(hiby_bt_preferences_remember("aa:bb:cc:dd:ee:ff") == 0);
        assert(hiby_bt_preferences_get(&preferences) == 0);
        assert(preferences.auto_mode == 1 && preferences.retry_seconds == 30);
        assert(!preferences.pause_on_loss && !preferences.announce);
        assert(!strcmp(preferences.last_address, "AA:BB:CC:DD:EE:FF"));
    }
    else if (!strcmp(argv[1], "sticky-remember-error"))
    {
        assert(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, 30) == 0);
        struct hiby_bt_preferences before = current;
        fault_operation = 8;
        fault_mode = 1;
        assert(hiby_bt_preferences_remember("aa:bb:cc:dd:ee:ff") == EIO);
        fault_operation = 0;
        assert(hiby_bt_preferences_get(&preferences) == EIO);
        assert(equal(&before, &preferences));
        assert(before.generation == preferences.generation);
        assert(hiby_bt_preferences_remember("aa:bb:cc:dd:ee:ff") == 0);
        assert(hiby_bt_preferences_get(&preferences) == 0);
        assert(!strcmp(preferences.last_address, "AA:BB:CC:DD:EE:FF"));
    }
    else if (!strcmp(argv[1], "noop-remove-fault"))
    {
        assert(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, 30) == 0);
        struct hiby_bt_preferences before = current;
        fault_operation = 9;
        fault_mode = 1;
        error = hiby_bt_preferences_forget("11:22:33:44:55:66");
        assert(error == EIO);
        assert(equal(&before, &current) && before.generation == current.generation);
        preferences = current;
    }
    else if (!strcmp(argv[1], "null"))
    {
        assert(hiby_bt_preferences_get(NULL) == EINVAL);
        assert(hiby_bt_preferences_remember(NULL) == EINVAL);
        assert(hiby_bt_preferences_forget(NULL) == EINVAL);
        preferences = current;
    }
#ifndef SIMULATOR
    else if (!strcmp(argv[1], "concurrent"))
    {
        pthread_t workers[4];
        int roles[] = {0, 1, 2, 3};
        for (int role = 0; role < 4; role++)
            assert(pthread_create(&workers[role], NULL, concurrent_update, &roles[role]) == 0);
        for (int role = 0; role < 4; role++)
            assert(pthread_join(workers[role], NULL) == 0);
        assert(hiby_bt_preferences_get(&preferences) == 0);
        assert(preferences.auto_mode == 1 && preferences.retry_seconds == 300);
        assert(!preferences.pause_on_loss && !preferences.announce);
        assert(!strcmp(preferences.last_address, "AA:BB:CC:DD:EE:FF"));
    }
#endif
    else
        return 64;
    print_preferences(error, &preferences);
    return 0;
}
