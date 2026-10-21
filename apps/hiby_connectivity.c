#include "config.h"
#include "hiby_connectivity.h"
#include "hiby_bluetooth.h"
#include "hiby_bluetooth_service.h"
#include "file.h"
#include "rbpaths.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>

#define CONNECTIVITY_FILE ROCKBOX_DIR "/connectivity.cfg"
#define CONNECTIVITY_TEMP ROCKBOX_DIR "/connectivity.cfg.tmp"
#define CONNECTIVITY_FORMAT "RBCONNECTIVITY:1\nwifi:%u\nbluetooth:%u\nairplane:%u\n"
#define CONNECTIVITY_TEMPLATE "RBCONNECTIVITY:1\nwifi:0\nbluetooth:0\nairplane:0\n"

#if !defined(SIMULATOR) && !defined(BOOTLOADER) && \
    (defined(HIBY_LINUX) || defined(HIBY_CONNECTIVITY_HOST_TEST))
#define CONNECTIVITY_NATIVE
#include "power-control-hiby.h"
#include <limits.h>
#include <pthread.h>
#include <time.h>

#ifndef HIBY_CONNECTIVITY_BT_WAIT_MS
#define HIBY_CONNECTIVITY_BT_WAIT_MS 120000
#endif
#ifndef HIBY_CONNECTIVITY_SETTLE_MS
#define HIBY_CONNECTIVITY_SETTLE_MS 15000
#endif
#define CONNECTIVITY_WAIT_STEP_MS 20

static pthread_mutex_t state_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t state_changed = PTHREAD_COND_INITIALIZER;
static pthread_t worker;
static bool running;
static bool stopping;
static unsigned int cancellation_generation;
static unsigned int active_cancellation;
static bool cancel_sent;
#define LOCK() pthread_mutex_lock(&state_mutex)
#define UNLOCK() pthread_mutex_unlock(&state_mutex)
#else
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
#endif

enum connectivity_operation
{
    CONNECTIVITY_STARTUP,
    CONNECTIVITY_WIFI,
    CONNECTIVITY_BLUETOOTH,
    CONNECTIVITY_AIRPLANE,
    CONNECTIVITY_REFRESH
};

struct connectivity_job
{
    enum connectivity_operation operation;
    bool wifi;
    bool bluetooth;
    bool airplane;
    bool persist;
    unsigned int cancellation;
};

static struct hiby_connectivity_snapshot state;
static bool loaded;
#ifdef CONNECTIVITY_NATIVE
static struct connectivity_job next_job;
static bool pending;
#endif

static int load_preferences(void)
{
    char data[sizeof(CONNECTIVITY_TEMPLATE) + 1];
    size_t used = 0;
    int descriptor = open(CONNECTIVITY_FILE, O_RDONLY);
    if (descriptor < 0)
        return errno == ENOENT ? 0 : errno ? errno : EIO;
    int error = 0;
    unsigned int interrupted = 0;
    while (used < sizeof(data))
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0 && errno == EINTR && ++interrupted < 4)
            continue;
        if (count < 0)
        {
            error = errno ? errno : EIO;
            break;
        }
        if (!count)
            break;
        used += count;
    }
    if (close(descriptor) != 0 && !error)
        error = errno ? errno : EIO;
    if (error)
        return error;
    if (used != sizeof(CONNECTIVITY_TEMPLATE) - 1)
        return EINVAL;
    unsigned int wifi = (unsigned char)data[sizeof("RBCONNECTIVITY:1\nwifi:") - 1] - '0';
    unsigned int bluetooth = (unsigned char)data[sizeof("RBCONNECTIVITY:1\nwifi:0\nbluetooth:") - 1] - '0';
    unsigned int airplane = (unsigned char)data[sizeof("RBCONNECTIVITY:1\nwifi:0\nbluetooth:0\nairplane:") - 1] - '0';
    if (wifi > 1 || bluetooth > 1 || airplane > 1)
        return EINVAL;
    char canonical[sizeof(CONNECTIVITY_TEMPLATE)];
    int length = snprintf(canonical, sizeof(canonical), CONNECTIVITY_FORMAT,
                          wifi, bluetooth, airplane);
    if (length != (int)used || memcmp(data, canonical, used))
        return EINVAL;
    state.wifi_desired = wifi;
    state.bluetooth_desired = bluetooth;
    state.airplane_mode = airplane;
    return 0;
}

static int save_preferences(const struct connectivity_job *job)
{
    char data[sizeof(CONNECTIVITY_TEMPLATE)];
    int length = snprintf(data, sizeof(data), CONNECTIVITY_FORMAT,
                          (unsigned int)job->wifi, (unsigned int)job->bluetooth,
                          (unsigned int)job->airplane);
    if (length != (int)sizeof(data) - 1)
        return EINVAL;
    int descriptor = open(CONNECTIVITY_TEMP, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (descriptor < 0)
        return errno ? errno : EIO;
    int error = 0;
    size_t written = 0;
    unsigned int interrupted = 0;
    while (written < (size_t)length)
    {
        ssize_t count = write(descriptor, data + written, length - written);
        if (count < 0 && errno == EINTR && ++interrupted < 4)
            continue;
        if (count <= 0)
        {
            error = count < 0 && errno ? errno : EIO;
            break;
        }
        written += count;
    }
    if (fsync(descriptor) != 0 && !error)
        error = errno ? errno : EIO;
    if (close(descriptor) != 0 && !error)
        error = errno ? errno : EIO;
    if (!error && rename(CONNECTIVITY_TEMP, CONNECTIVITY_FILE) != 0)
        error = errno ? errno : EIO;
    if (error)
        remove(CONNECTIVITY_TEMP);
    return error;
}

#ifdef CONNECTIVITY_NATIVE
static bool operation_cancelled(void)
{
    return __atomic_load_n(&cancellation_generation, __ATOMIC_ACQUIRE) != active_cancellation;
}

static void inhibit_bluetooth(void)
{
    hiby_bluetooth_set_inhibited(true);
    hiby_bluetooth_cancel();
}

static bool settle_bluetooth(struct hiby_bt_snapshot *snapshot, unsigned int milliseconds)
{
    for (unsigned int remaining = milliseconds / CONNECTIVITY_WAIT_STEP_MS + 1;
         remaining; --remaining)
    {
        hiby_bluetooth_get_snapshot(snapshot);
        if (!snapshot->busy)
            return true;
        struct timespec duration = { .tv_nsec = CONNECTIVITY_WAIT_STEP_MS * 1000000 };
        nanosleep(&duration, NULL);
    }
    return false;
}

static enum hiby_bt_error bluetooth_operation(enum hiby_bt_operation operation,
                                             struct hiby_bt_snapshot *snapshot,
                                             bool cleanup)
{
    if (!cleanup && operation_cancelled())
        return HIBY_BT_CANCELLED;
    unsigned int generation = snapshot->generation;
    if (!hiby_bluetooth_request(operation, NULL))
    {
        hiby_bluetooth_get_snapshot(snapshot);
        return snapshot->busy ? HIBY_BT_BUSY :
            snapshot->error == HIBY_BT_OK ? HIBY_BT_COMMAND_FAILED : snapshot->error;
    }
    for (unsigned int remaining = HIBY_CONNECTIVITY_BT_WAIT_MS / CONNECTIVITY_WAIT_STEP_MS + 1;
         remaining; --remaining)
    {
        hiby_bluetooth_get_snapshot(snapshot);
        if (!snapshot->busy)
        {
            if (!cleanup && operation_cancelled())
                return HIBY_BT_CANCELLED;
            if (snapshot->generation == generation)
                return HIBY_BT_COMMAND_FAILED;
            return snapshot->error;
        }
        if (!cleanup && operation_cancelled())
            inhibit_bluetooth();
        struct timespec duration = { .tv_nsec = CONNECTIVITY_WAIT_STEP_MS * 1000000 };
        nanosleep(&duration, NULL);
    }
    inhibit_bluetooth();
    settle_bluetooth(snapshot, HIBY_CONNECTIVITY_SETTLE_MS);
    return HIBY_BT_TIMEOUT;
}

static enum hiby_connectivity_radio_state wifi_state(struct hiby_wifi_result result)
{
    if (result.state == HIBY_WIFI_ERROR || result.driver_error ||
        result.interface_error || result.interface_read_error ||
        (result.rfkill_error && result.rfkill_error != ENOENT &&
         result.rfkill_error != ENODEV && result.rfkill_error != ENXIO) ||
        (result.rfkill_read_error && result.rfkill_read_error != ENOENT &&
         result.rfkill_read_error != ENODEV && result.rfkill_read_error != ENXIO))
        return HIBY_CONNECTIVITY_RADIO_ERROR;
    if (result.state == HIBY_WIFI_DRIVER_SUSPENDED)
        return HIBY_CONNECTIVITY_DRIVER_SUSPENDED;
    if (result.state == HIBY_WIFI_INTERFACE_DOWN)
        return HIBY_CONNECTIVITY_INTERFACE_DOWN;
    if (result.rfkill_read_error || result.rfkill_error)
    {
        int error = result.rfkill_read_error ? result.rfkill_read_error : result.rfkill_error;
        return error == ENOENT || error == ENODEV || error == ENXIO ?
            HIBY_CONNECTIVITY_UNKNOWN : HIBY_CONNECTIVITY_RADIO_ERROR;
    }
    if (!result.wlan_radios)
        return result.interfaces_present ? HIBY_CONNECTIVITY_PARTIAL : HIBY_CONNECTIVITY_UNAVAILABLE;
    if (result.soft_blocked_radios > result.wlan_radios ||
        result.hard_blocked_radios > result.wlan_radios ||
        result.interfaces_up > result.interfaces_present ||
        result.interfaces_down != result.interfaces_present - result.interfaces_up)
        return HIBY_CONNECTIVITY_UNKNOWN;
    if (result.soft_blocked_radios == result.wlan_radios && !result.interfaces_up)
        return HIBY_CONNECTIVITY_OFF;
    if (!result.soft_blocked_radios && !result.hard_blocked_radios &&
        result.interfaces_present && result.interfaces_up == result.interfaces_present)
        return HIBY_CONNECTIVITY_ON;
    return HIBY_CONNECTIVITY_PARTIAL;
}

static enum hiby_connectivity_radio_state query_wifi(bool change, bool enabled)
{
    struct hiby_wifi_result changed = { 0 };
    if (change)
        changed = hiby_wifi_set_enabled(enabled);
    struct hiby_wifi_result observed = hiby_wifi_get_state();
    if ((change && changed.state == HIBY_WIFI_ERROR) || changed.driver_error || changed.interface_error ||
        changed.interface_read_error ||
        (changed.rfkill_error && changed.rfkill_error != ENOENT &&
         changed.rfkill_error != ENODEV && changed.rfkill_error != ENXIO) ||
        (changed.rfkill_read_error && changed.rfkill_read_error != ENOENT &&
         changed.rfkill_read_error != ENODEV && changed.rfkill_read_error != ENXIO))
        return HIBY_CONNECTIVITY_RADIO_ERROR;
    return wifi_state(observed);
}

static enum hiby_connectivity_radio_state query_bluetooth(bool change, bool enabled,
    bool cleanup, bool *settled, enum hiby_bt_error *error)
{
    struct hiby_bt_snapshot snapshot;
    memset(&snapshot, 0, sizeof(snapshot));
    if (!hiby_bluetooth_init())
    {
        hiby_bluetooth_get_snapshot(&snapshot);
        *error = snapshot.error != HIBY_BT_OK ? snapshot.error : HIBY_BT_UNAVAILABLE;
        *settled = true;
        return *error == HIBY_BT_UNAVAILABLE ?
            HIBY_CONNECTIVITY_UNAVAILABLE : HIBY_CONNECTIVITY_RADIO_ERROR;
    }
    hiby_bluetooth_get_snapshot(&snapshot);
    if (change)
        inhibit_bluetooth();
    *settled = settle_bluetooth(&snapshot, HIBY_CONNECTIVITY_SETTLE_MS);
    if (!*settled)
    {
        inhibit_bluetooth();
        *error = HIBY_BT_TIMEOUT;
        return HIBY_CONNECTIVITY_UNKNOWN;
    }
    enum hiby_bt_error changed = HIBY_BT_OK;
    if (change)
    {
        if (enabled)
        {
            LOCK();
            if (!operation_cancelled() && !state.airplane_mode && !stopping)
                hiby_bluetooth_set_inhibited(false);
            UNLOCK();
        }
        changed = bluetooth_operation(enabled ? HIBY_BT_ENABLE : HIBY_BT_DISABLE,
                                      &snapshot, cleanup);
    }
    enum hiby_bt_error observed = HIBY_BT_OK;
    if (!change || changed != HIBY_BT_OK || !snapshot.available || !snapshot.power_known ||
        snapshot.connected_address[0])
        observed = snapshot.busy ? HIBY_BT_TIMEOUT :
            bluetooth_operation(HIBY_BT_REFRESH, &snapshot, cleanup);
    *settled = !snapshot.busy;
    *error = changed != HIBY_BT_OK ? changed : observed;
    if (*error == HIBY_BT_UNAVAILABLE)
        return HIBY_CONNECTIVITY_UNAVAILABLE;
    if (*error != HIBY_BT_OK && *error != HIBY_BT_AUDIO_FAILED)
        return HIBY_CONNECTIVITY_RADIO_ERROR;
    if (!snapshot.available || !snapshot.power_known)
        return HIBY_CONNECTIVITY_UNKNOWN;
    return snapshot.enabled ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF;
}

static enum hiby_connectivity_result radio_result(enum hiby_connectivity_radio_state radio,
                                                 bool enabled)
{
    if (radio == HIBY_CONNECTIVITY_RADIO_ERROR)
        return HIBY_CONNECTIVITY_FAILED;
    if (radio == HIBY_CONNECTIVITY_UNAVAILABLE)
        return HIBY_CONNECTIVITY_NOT_AVAILABLE;
    if (!enabled && radio == HIBY_CONNECTIVITY_DRIVER_SUSPENDED)
        return HIBY_CONNECTIVITY_OK;
    if (radio != (enabled ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF))
        return HIBY_CONNECTIVITY_INCOMPLETE;
    return HIBY_CONNECTIVITY_OK;
}

static void execute_job(const struct connectivity_job *job)
{
    bool wifi_change = job->operation != CONNECTIVITY_REFRESH &&
                       job->operation != CONNECTIVITY_BLUETOOTH;
    bool bluetooth_change = job->operation != CONNECTIVITY_REFRESH &&
                            job->operation != CONNECTIVITY_WIFI;
    bool wifi_enabled = job->wifi && !job->airplane;
    bool bluetooth_enabled = job->bluetooth && !job->airplane;
    int storage_error = job->persist ? save_preferences(job) : 0;
    LOCK();
    if (job->persist)
        state.storage_error = storage_error;
    else
        storage_error = state.storage_error;
    UNLOCK();
    if (storage_error)
    {
        wifi_enabled = false;
        bluetooth_enabled = false;
        wifi_change = true;
        bluetooth_change = true;
    }
    if (bluetooth_change)
        inhibit_bluetooth();
    if (operation_cancelled())
        wifi_enabled = bluetooth_enabled = false;
    enum hiby_connectivity_radio_state wifi = query_wifi(wifi_change, wifi_enabled);
    bool wifi_settled = hiby_wifi_settled();
    if (!wifi_settled)
    {
        bluetooth_enabled = false;
        inhibit_bluetooth();
    }
    bool settled = true;
    enum hiby_bt_error bluetooth_error = HIBY_BT_OK;
    enum hiby_connectivity_radio_state bluetooth = query_bluetooth(bluetooth_change,
        bluetooth_enabled, false, &settled, &bluetooth_error);
    settled = settled && wifi_settled;
    bool timed_out = bluetooth_error == HIBY_BT_TIMEOUT || !settled;
    LOCK();
    bool was_cancelled = operation_cancelled();
    if (was_cancelled || timed_out)
    {
        UNLOCK();
        inhibit_bluetooth();
        wifi = query_wifi(true, false);
        wifi_settled = hiby_wifi_settled();
        bluetooth = query_bluetooth(true, false, true, &settled, &bluetooth_error);
        settled = settled && wifi_settled;
        LOCK();
    }
    enum hiby_connectivity_result result = radio_result(wifi, wifi_enabled);
    enum hiby_connectivity_result bluetooth_result = radio_result(bluetooth, bluetooth_enabled);
    if (bluetooth_error == HIBY_BT_AUDIO_FAILED)
        bluetooth_result = HIBY_CONNECTIVITY_FAILED;
    if (job->operation == CONNECTIVITY_BLUETOOTH)
        result = bluetooth_result;
    else if (job->operation != CONNECTIVITY_WIFI)
    {
        if (result == HIBY_CONNECTIVITY_FAILED || bluetooth_result == HIBY_CONNECTIVITY_FAILED)
            result = HIBY_CONNECTIVITY_FAILED;
        else if (result == HIBY_CONNECTIVITY_NOT_AVAILABLE || bluetooth_result == HIBY_CONNECTIVITY_NOT_AVAILABLE)
            result = HIBY_CONNECTIVITY_NOT_AVAILABLE;
        else if (bluetooth_result != HIBY_CONNECTIVITY_OK)
            result = bluetooth_result;
    }
    if (job->airplane && ((job->operation == CONNECTIVITY_WIFI && job->wifi) ||
                         (job->operation == CONNECTIVITY_BLUETOOTH && job->bluetooth)) &&
        result == HIBY_CONNECTIVITY_OK)
        result = HIBY_CONNECTIVITY_INHIBITED;
    if (timed_out || bluetooth_error == HIBY_BT_TIMEOUT || !settled)
        result = HIBY_CONNECTIVITY_TIMEOUT;
    if (was_cancelled)
        result = settled ? HIBY_CONNECTIVITY_CANCELLED : HIBY_CONNECTIVITY_TIMEOUT;
    if (storage_error)
        result = HIBY_CONNECTIVITY_STORAGE_ERROR;
    state.wifi = wifi;
    state.bluetooth = bluetooth;
    state.settled = settled;
    state.inhibited = state.airplane_mode || was_cancelled || timed_out || storage_error || !settled ||
        (state.inhibited && job->operation == CONNECTIVITY_REFRESH && bluetooth != HIBY_CONNECTIVITY_OFF);
    hiby_bluetooth_set_inhibited(state.inhibited);
    hiby_bluetooth_service_allow(!state.inhibited && !pending &&
        state.bluetooth_desired && !state.airplane_mode &&
        bluetooth == HIBY_CONNECTIVITY_ON &&
        (bluetooth_error == HIBY_BT_OK || bluetooth_error == HIBY_BT_AUDIO_FAILED));
    state.result = result;
    state.busy = pending;
    ++state.generation;
    UNLOCK();
}

static void *connectivity_worker(void *context)
{
    (void)context;
    LOCK();
    for (;;)
    {
        while (!pending && !stopping)
            pthread_cond_wait(&state_changed, &state_mutex);
        if (stopping && !pending)
            break;
        struct connectivity_job job = next_job;
        pending = false;
        active_cancellation = job.cancellation;
        cancel_sent = operation_cancelled();
        UNLOCK();
        execute_job(&job);
        LOCK();
        pthread_cond_broadcast(&state_changed);
    }
    UNLOCK();
    return NULL;
}
#endif

bool hiby_connectivity_init(void)
{
    LOCK();
    if (!loaded)
    {
        memset(&state, 0, sizeof(state));
        state.settled = true;
        state.storage_error = load_preferences();
        state.result = state.storage_error ? HIBY_CONNECTIVITY_STORAGE_ERROR : HIBY_CONNECTIVITY_OK;
        state.inhibited = state.airplane_mode;
        loaded = true;
    }
#ifdef CONNECTIVITY_NATIVE
    if (stopping)
    {
        UNLOCK();
        return false;
    }
    if (!running)
    {
        pthread_attr_t attributes;
        int error = pthread_attr_init(&attributes);
        if (!error)
        {
            size_t stack_size = (size_t)PTHREAD_STACK_MIN;
            if (stack_size < 65536)
                stack_size = 65536;
            error = pthread_attr_setstacksize(&attributes, stack_size);
            if (!error)
                error = pthread_create(&worker, &attributes, connectivity_worker, NULL);
            pthread_attr_destroy(&attributes);
        }
        if (error)
        {
            state.result = HIBY_CONNECTIVITY_FAILED;
            state.wifi = HIBY_CONNECTIVITY_UNKNOWN;
            state.bluetooth = HIBY_CONNECTIVITY_UNKNOWN;
            UNLOCK();
            return false;
        }
        running = true;
        hiby_bluetooth_set_inhibited(state.inhibited);
    }
#else
    state.wifi = HIBY_CONNECTIVITY_UNAVAILABLE;
    state.bluetooth = HIBY_CONNECTIVITY_UNAVAILABLE;
    if (!state.storage_error)
        state.result = HIBY_CONNECTIVITY_NOT_AVAILABLE;
#endif
    UNLOCK();
    return true;
}

static bool submit(enum connectivity_operation operation, bool enabled)
{
    if (!hiby_connectivity_init())
        return false;
    LOCK();
#ifdef CONNECTIVITY_NATIVE
    if (!hiby_wifi_settled() && operation != CONNECTIVITY_REFRESH &&
        !(operation == CONNECTIVITY_AIRPLANE && enabled))
    {
        state.result = HIBY_CONNECTIVITY_BUSY;
        state.settled = false;
        state.inhibited = true;
        inhibit_bluetooth();
        UNLOCK();
        return false;
    }
    if (stopping || (state.busy && !(operation == CONNECTIVITY_AIRPLANE && enabled)))
    {
        UNLOCK();
        return false;
    }
#endif
    if (operation == CONNECTIVITY_WIFI)
        state.wifi_desired = enabled;
    else if (operation == CONNECTIVITY_BLUETOOTH)
        state.bluetooth_desired = enabled;
    else if (operation == CONNECTIVITY_AIRPLANE)
        state.airplane_mode = enabled;
    struct connectivity_job job = {
        .operation = operation,
        .wifi = state.wifi_desired,
        .bluetooth = state.bluetooth_desired,
        .airplane = state.airplane_mode,
        .persist = operation == CONNECTIVITY_WIFI || operation == CONNECTIVITY_BLUETOOTH ||
                   operation == CONNECTIVITY_AIRPLANE
    };
    bool was_busy = state.busy;
    state.result = HIBY_CONNECTIVITY_BUSY;
    state.busy = true;
    state.wifi = HIBY_CONNECTIVITY_UNKNOWN;
    state.bluetooth = HIBY_CONNECTIVITY_UNKNOWN;
    ++state.generation;
#ifdef CONNECTIVITY_NATIVE
    if (!was_busy)
        cancel_sent = false;
    if (job.airplane)
    {
        state.inhibited = true;
        inhibit_bluetooth();
        if (was_busy)
        {
            __atomic_add_fetch(&cancellation_generation, 1, __ATOMIC_RELEASE);
            hiby_wifi_cancel();
        }
    }
    job.cancellation = __atomic_load_n(&cancellation_generation, __ATOMIC_ACQUIRE);
    next_job = job;
    pending = true;
    pthread_cond_signal(&state_changed);
#else
    (void)was_busy;
    if (job.persist)
        state.storage_error = save_preferences(&job);
    state.wifi = HIBY_CONNECTIVITY_UNAVAILABLE;
    state.bluetooth = HIBY_CONNECTIVITY_UNAVAILABLE;
    state.inhibited = job.airplane;
    state.result = state.storage_error ? HIBY_CONNECTIVITY_STORAGE_ERROR :
                   HIBY_CONNECTIVITY_NOT_AVAILABLE;
    state.busy = false;
#endif
    UNLOCK();
    return true;
}

bool hiby_connectivity_apply_startup_policy(void)
{
    return submit(CONNECTIVITY_STARTUP, false);
}

bool hiby_connectivity_set_wifi_enabled(bool enabled)
{
    return submit(CONNECTIVITY_WIFI, enabled);
}

bool hiby_connectivity_set_bluetooth_enabled(bool enabled)
{
    return submit(CONNECTIVITY_BLUETOOTH, enabled);
}

bool hiby_connectivity_set_airplane_mode(bool enabled)
{
    return submit(CONNECTIVITY_AIRPLANE, enabled);
}

bool hiby_connectivity_refresh(void)
{
    return submit(CONNECTIVITY_REFRESH, false);
}

void hiby_connectivity_get_snapshot(struct hiby_connectivity_snapshot *snapshot)
{
    if (!snapshot)
        return;
    LOCK();
    *snapshot = state;
    UNLOCK();
}

bool hiby_connectivity_wifi_desired(void)
{
    struct hiby_connectivity_snapshot snapshot;
    hiby_connectivity_init();
    hiby_connectivity_get_snapshot(&snapshot);
    return snapshot.wifi_desired;
}

bool hiby_connectivity_bluetooth_desired(void)
{
    struct hiby_connectivity_snapshot snapshot;
    hiby_connectivity_init();
    hiby_connectivity_get_snapshot(&snapshot);
    return snapshot.bluetooth_desired;
}

bool hiby_connectivity_airplane_mode(void)
{
    struct hiby_connectivity_snapshot snapshot;
    hiby_connectivity_init();
    hiby_connectivity_get_snapshot(&snapshot);
    return snapshot.airplane_mode;
}

void hiby_connectivity_cancel(void)
{
#ifdef CONNECTIVITY_NATIVE
    LOCK();
    if (state.busy && !cancel_sent)
    {
        cancel_sent = true;
        state.inhibited = true;
        __atomic_add_fetch(&cancellation_generation, 1, __ATOMIC_RELEASE);
        hiby_wifi_cancel();
        inhibit_bluetooth();
    }
    UNLOCK();
#endif
}

void hiby_connectivity_shutdown(void)
{
#ifdef CONNECTIVITY_NATIVE
    LOCK();
    hiby_bluetooth_service_allow(false);
    if (stopping)
    {
        while (stopping)
            pthread_cond_wait(&state_changed, &state_mutex);
        UNLOCK();
        return;
    }
    if (!running)
    {
        UNLOCK();
        return;
    }
    stopping = true;
    if (state.busy && !cancel_sent)
    {
        cancel_sent = true;
        __atomic_add_fetch(&cancellation_generation, 1, __ATOMIC_RELEASE);
        hiby_wifi_cancel();
        inhibit_bluetooth();
    }
    pthread_cond_signal(&state_changed);
    UNLOCK();
    pthread_join(worker, NULL);
    LOCK();
    running = false;
    stopping = false;
    state.busy = false;
    pthread_cond_broadcast(&state_changed);
    UNLOCK();
#endif
}

#ifndef HIBY_CONNECTIVITY_NO_UI
#include "action.h"
#include "kernel.h"
#include "lang.h"
#include "language.h"
#include "list.h"
#include "menu.h"
#include "misc.h"
#include "splash.h"
#include "talk.h"

static int radio_label(enum hiby_connectivity_radio_state radio)
{
    static const int labels[] = {
        LANG_HIBY_CONNECTIVITY_UNKNOWN, LANG_HIBY_CONNECTIVITY_ADMIN_OFF,
        LANG_HIBY_CONNECTIVITY_ADMIN_ON,
        LANG_HIBY_CONNECTIVITY_PARTIAL, LANG_HIBY_CONNECTIVITY_UNAVAILABLE,
        LANG_HIBY_CONNECTIVITY_FAILED, LANG_HIBY_WIFI_INTERFACE_DOWN,
        LANG_HIBY_WIFI_DRIVER_SUSPENDED
    };
    if ((unsigned int)radio >= sizeof(labels) / sizeof(labels[0]))
        return LANG_HIBY_CONNECTIVITY_UNKNOWN;
    return labels[radio];
}

static int result_label(enum hiby_connectivity_result result)
{
    static const int labels[] = {
        LANG_HIBY_BT_DONE, LANG_HIBY_CONNECTIVITY_FAILED,
        LANG_HIBY_CONNECTIVITY_UNAVAILABLE, LANG_HIBY_CONNECTIVITY_PARTIAL,
        LANG_HIBY_CONNECTIVITY_STORAGE_ERROR, LANG_HIBY_BT_CANCELLED,
        LANG_HIBY_BT_TIMEOUT, LANG_HIBY_BT_BUSY, LANG_HIBY_BT_AIRPLANE_MODE
    };
    if ((unsigned int)result >= sizeof(labels) / sizeof(labels[0]))
        return LANG_HIBY_CONNECTIVITY_FAILED;
    return labels[result];
}

static void show_result(int identifier)
{
    talk_id(identifier, false);
    splashf_silent(HZ, "%s", str(identifier));
}

#ifndef HIBY_CONNECTIVITY_UI_WAIT_TICKS
#define HIBY_CONNECTIVITY_UI_WAIT_TICKS (450 * HZ)
#endif
#ifndef HIBY_CONNECTIVITY_UI_SETTLE_TICKS
#define HIBY_CONNECTIVITY_UI_SETTLE_TICKS (15 * HZ)
#endif

struct connectivity_menu
{
    bool wifi_only;
    bool operation_pending;
    bool announce_success;
    bool cancelled;
    bool timed_out;
    long deadline;
    bool redraw_pending;
    struct hiby_connectivity_snapshot snapshot;
};

static int menu_label(int selected, const struct connectivity_menu *menu)
{
    if (menu->wifi_only)
        return LANG_HIBY_WIFI;
    static const int labels[] = {
        LANG_HIBY_WIFI, LANG_HIBY_BT_TITLE, LANG_HIBY_AIRPLANE_MODE
    };
    return labels[selected];
}

static int menu_value(int selected, const struct connectivity_menu *menu)
{
    if (menu->snapshot.busy)
        return LANG_HIBY_BT_WORKING;
    if (menu->wifi_only || selected == 0)
        return radio_label(menu->snapshot.wifi);
    if (selected == 1)
        return radio_label(menu->snapshot.bluetooth);
    if (menu->snapshot.airplane_mode)
        return (menu->snapshot.wifi == HIBY_CONNECTIVITY_OFF ||
                menu->snapshot.wifi == HIBY_CONNECTIVITY_DRIVER_SUSPENDED) &&
               menu->snapshot.bluetooth == HIBY_CONNECTIVITY_OFF ? LANG_ON :
               LANG_HIBY_CONNECTIVITY_PARTIAL;
    return LANG_OFF;
}

static const char *menu_name(int selected, void *data, char *buffer, size_t length)
{
    const struct connectivity_menu *menu = data;
    if (selected < 0 || selected >= (menu->wifi_only ? 1 : 3))
        return "";
    if (menu->wifi_only)
        snprintf(buffer, length, "%s: %s (%s: %s)", str(LANG_HIBY_WIFI),
                 str(menu->snapshot.wifi_desired ? LANG_ON : LANG_OFF),
                 str(LANG_HIBY_BT_STATUS), str(menu_value(selected, menu)));
    else
        snprintf(buffer, length, "%s: %s", str(menu_label(selected, menu)),
                 str(menu_value(selected, menu)));
    return buffer;
}

static int menu_talk(int selected, void *data)
{
    const struct connectivity_menu *menu = data;
    if (selected < 0 || selected >= (menu->wifi_only ? 1 : 3))
        return 0;
    talk_id(menu_label(selected, menu), false);
    if (menu->wifi_only)
    {
        talk_id(menu->snapshot.wifi_desired ? LANG_ON : LANG_OFF, true);
        talk_id(LANG_HIBY_BT_STATUS, true);
    }
    return talk_id(menu_value(selected, menu), true);
}

static void track_menu_operation(struct connectivity_menu *menu, bool accepted, bool announce_success)
{
    hiby_connectivity_get_snapshot(&menu->snapshot);
    menu->operation_pending = accepted || menu->snapshot.busy;
    menu->announce_success = announce_success && accepted;
    menu->cancelled = false;
    menu->timed_out = false;
    menu->deadline = current_tick + HIBY_CONNECTIVITY_UI_WAIT_TICKS;
    if (!menu->operation_pending)
        show_result(menu->snapshot.result == HIBY_CONNECTIVITY_OK ?
                    LANG_HIBY_CONNECTIVITY_FAILED : result_label(menu->snapshot.result));
}

static void request_menu_refresh(struct connectivity_menu *menu)
{
    track_menu_operation(menu, hiby_connectivity_refresh(), false);
}

static int menu_action(int action, struct gui_synclist *lists)
{
    struct connectivity_menu *menu = lists->data;
    unsigned int generation = menu->snapshot.generation;
    bool busy = menu->snapshot.busy;
    hiby_connectivity_get_snapshot(&menu->snapshot);
    menu->redraw_pending |= generation != menu->snapshot.generation || busy != menu->snapshot.busy;
    if (menu->operation_pending && menu->snapshot.busy && TIME_AFTER(current_tick, menu->deadline))
    {
        if (!menu->cancelled)
        {
            menu->cancelled = true;
            menu->timed_out = true;
            hiby_connectivity_cancel();
            menu->deadline = current_tick + HIBY_CONNECTIVITY_UI_SETTLE_TICKS;
        }
        else
        {
            menu->operation_pending = false;
            show_result(LANG_HIBY_BT_TIMEOUT);
        }
    }
    if (menu->operation_pending && !menu->snapshot.busy)
    {
        menu->operation_pending = false;
        enum hiby_connectivity_result result = menu->timed_out ? HIBY_CONNECTIVITY_TIMEOUT :
            menu->cancelled ? HIBY_CONNECTIVITY_CANCELLED : menu->snapshot.result;
        if (result != HIBY_CONNECTIVITY_OK || menu->announce_success)
            show_result(result_label(result));
        else if (action == ACTION_NONE)
            menu_talk(gui_synclist_get_sel_pos(lists), menu);
        menu->redraw_pending = true;
    }
    if (menu->snapshot.busy && (action == ACTION_STD_CANCEL || action == ACTION_TREE_WPS ||
                                action == SYS_USB_CONNECTED) && !menu->cancelled)
    {
        menu->cancelled = true;
        hiby_connectivity_cancel();
    }
    if (action == ACTION_STD_OK && menu->snapshot.busy &&
        (menu->wifi_only || gui_synclist_get_sel_pos(lists) == 2))
    {
        talk_id(LANG_HIBY_BT_BUSY, false);
        splashf_silent(0, "%s", str(LANG_HIBY_BT_BUSY));
        return ACTION_NONE;
    }
    if (menu->redraw_pending && (action == ACTION_NONE || action == ACTION_REDRAW))
    {
        menu->redraw_pending = false;
        return ACTION_REDRAW;
    }
    return action;
}

static int connectivity_list(bool wifi_only)
{
    struct connectivity_menu menu = { .wifi_only = wifi_only };
    if (!wifi_only)
        request_menu_refresh(&menu);
    int selected = 0;
    for (;;)
    {
        hiby_connectivity_get_snapshot(&menu.snapshot);
        struct simplelist_info info;
        simplelist_info_init(&info, str(wifi_only ? LANG_HIBY_WIFI : LANG_CONNECTIVITY),
                             wifi_only ? 1 : 3, &menu);
        info.get_name = menu_name;
        info.get_talk = menu_talk;
        info.action_callback = menu_action;
        info.selection = selected;
        if (simplelist_show_list(&info))
            return MENU_ATTACHED_USB;
        selected = info.selection;
        if (selected < 0)
            return 0;
        if (selected >= info.count)
            continue;
        int result = 0;
        if (wifi_only)
        {
            hiby_connectivity_get_snapshot(&menu.snapshot);
            if (!menu.snapshot.busy)
                track_menu_operation(&menu, hiby_connectivity_set_wifi_enabled(!menu.snapshot.wifi_desired), true);
        }
        else if (selected == 0)
            result = connectivity_list(true);
        else if (selected == 1)
            result = hiby_bluetooth_menu() ? MENU_ATTACHED_USB : 0;
        else
        {
            hiby_connectivity_get_snapshot(&menu.snapshot);
            if (!menu.snapshot.busy)
                track_menu_operation(&menu, hiby_connectivity_set_airplane_mode(!menu.snapshot.airplane_mode), true);
        }
        if (result)
            return result;
        if (!wifi_only && selected == 1)
            request_menu_refresh(&menu);
    }
}

int hiby_connectivity_menu(void)
{
    if (!hiby_connectivity_init())
    {
        show_result(LANG_HIBY_CONNECTIVITY_FAILED);
        return connectivity_list(false);
    }
    return connectivity_list(false);
}
#endif
