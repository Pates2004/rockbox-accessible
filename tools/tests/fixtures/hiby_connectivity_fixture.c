#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "hiby_bluetooth.h"
#include "hiby_bluetooth_service.h"
#include "power-control-hiby.h"
#include "connectivity-labels.h"

static char stored[128];
static size_t stored_length;
static bool stored_exists;
static char temporary[128];
static size_t temporary_length;
static bool temporary_exists;
static size_t read_position;
static const char *fault = "none";
static unsigned int interrupted;
static unsigned int writes;
static unsigned int renames;
static bool thread_failure;

#ifndef SIMULATOR
static int create_worker(pthread_t *thread, const pthread_attr_t *attributes,
                         void *(*entry)(void *), void *context)
{
    return thread_failure ? EAGAIN : pthread_create(thread, attributes, entry, context);
}
#endif

static int storage_open(const char *path, int flags, ...)
{
    assert(!strcmp(path, "/.rockbox/connectivity.cfg") ||
           !strcmp(path, "/.rockbox/connectivity.cfg.tmp"));
    if (!strcmp(path, "/.rockbox/connectivity.cfg"))
    {
        assert(flags == O_RDONLY);
        if (!strcmp(fault, "read-open"))
        {
            errno = EACCES;
            return -1;
        }
        if (!stored_exists)
        {
            errno = ENOENT;
            return -1;
        }
        read_position = 0;
        return 41;
    }
    assert((flags & (O_CREAT | O_WRONLY | O_EXCL)) == (O_CREAT | O_WRONLY | O_EXCL));
    if (!strcmp(fault, "open") || temporary_exists)
    {
        errno = temporary_exists ? EEXIST : EACCES;
        return -1;
    }
    temporary_exists = true;
    temporary_length = 0;
    return 42;
}

static ssize_t storage_read(int descriptor, void *buffer, size_t length)
{
    assert(descriptor == 41);
    if (!strcmp(fault, "read-error") ||
        ((!strcmp(fault, "read-eintr") || !strcmp(fault, "read-storm")) &&
         (!interrupted++ || !strcmp(fault, "read-storm"))))
    {
        errno = !strcmp(fault, "read-error") ? EIO : EINTR;
        return -1;
    }
    if (!strcmp(fault, "read-short") && length > 1)
        length = 1;
    if (length > stored_length - read_position)
        length = stored_length - read_position;
    memcpy(buffer, stored + read_position, length);
    read_position += length;
    return length;
}

static ssize_t storage_write(int descriptor, const void *buffer, size_t length)
{
    assert(descriptor == 42);
    ++writes;
    if (!strcmp(fault, "write") ||
        ((!strcmp(fault, "write-eintr") || !strcmp(fault, "write-storm")) &&
         (!interrupted++ || !strcmp(fault, "write-storm"))))
    {
        errno = !strcmp(fault, "write") ? ENOSPC : EINTR;
        return -1;
    }
    if (!strcmp(fault, "zero"))
        return 0;
    if (!strcmp(fault, "short") && length > 1)
        length = 1;
    assert(temporary_length + length <= sizeof(temporary));
    memcpy(temporary + temporary_length, buffer, length);
    temporary_length += length;
    return length;
}

static int storage_close(int descriptor)
{
    assert(descriptor == 41 || descriptor == 42);
    if ((!strcmp(fault, "close") && descriptor == 42) ||
        (!strcmp(fault, "read-close") && descriptor == 41))
    {
        errno = EIO;
        return -1;
    }
    return 0;
}

static int storage_fsync(int descriptor)
{
    assert(descriptor == 42);
    if (!strcmp(fault, "fsync"))
    {
        errno = EIO;
        return -1;
    }
    return 0;
}

static int storage_rename(const char *source, const char *destination)
{
    assert(!strcmp(source, "/.rockbox/connectivity.cfg.tmp"));
    assert(!strcmp(destination, "/.rockbox/connectivity.cfg"));
    ++renames;
    if (!strcmp(fault, "rename"))
    {
        errno = EACCES;
        return -1;
    }
    memcpy(stored, temporary, temporary_length);
    stored_length = temporary_length;
    stored_exists = true;
    temporary_exists = false;
    return 0;
}

static int storage_remove(const char *path)
{
    assert(!strcmp(path, "/.rockbox/connectivity.cfg.tmp"));
    temporary_exists = false;
    return 0;
}

struct gui_synclist
{
    int selected_item;
    void *data;
};

struct simplelist_info
{
    const char *title;
    int count;
    int selection;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
    void *callback_data;
    int (*action_callback)(int, struct gui_synclist *);
};

#define HZ 100
#define CONTEXT_STD 1
#define ACTION_STD_CANCEL 2
#define ACTION_TREE_WPS 3
#define SYS_USB_CONNECTED 4
#define MENU_ATTACHED_USB 5
#define ACTION_NONE 0
#define ACTION_REDRAW 6
#define ACTION_STD_NEXT 7
#define ACTION_STD_OK 8
#define HIBY_CONNECTIVITY_UI_WAIT_TICKS 100
#define HIBY_CONNECTIVITY_UI_SETTLE_TICKS 50
#define TIME_AFTER(after, before) ((long)(before) - (long)(after) < 0)
static long current_tick;

static int gui_synclist_get_sel_pos(struct gui_synclist *lists)
{
    return lists->selected_item;
}

static char *str(int identifier);
static int talk_id(int identifier, bool enqueue);
static void splashf_silent(int ticks, const char *format, ...);
static void simplelist_info_init(struct simplelist_info *info, const char *title,
                                 int count, void *data);
static bool simplelist_show_list(struct simplelist_info *info);

#define open storage_open
#define read storage_read
#define write storage_write
#define close storage_close
#define fsync storage_fsync
#define rename storage_rename
#define remove storage_remove
#define pthread_create create_worker
#define __ACTION_H__
#define __MENU_H__
#define MISC_H
#define __TALK_H__
#define __LANGUAGE_H
#ifndef CONNECTIVITY_TEST_SOURCE
#define CONNECTIVITY_TEST_SOURCE "hiby_connectivity.c"
#endif
#include CONNECTIVITY_TEST_SOURCE
#undef pthread_create

static pthread_mutex_t backend_mutex = PTHREAD_MUTEX_INITIALIZER;
static struct hiby_wifi_result wifi;
static struct hiby_bt_snapshot bluetooth;
static bool inhibited;
static bool bluetooth_available = true;
static bool bluetooth_cancelled;
static bool bluetooth_pending;
static enum hiby_bt_operation bluetooth_operation_pending;
static unsigned int bluetooth_remaining;
static unsigned int wifi_sets;
static unsigned int wifi_queries;
static unsigned int wifi_enables;
static unsigned int bluetooth_calls;
static unsigned int bluetooth_requests[HIBY_BT_CONNECT_PAIRED + 1];
static unsigned int bluetooth_enables;
static unsigned int inhibit_order;
static unsigned int disable_order;
static unsigned int sequence;
static const char *radio_fault = "none";
static unsigned int speech_count;
static int spoken[256];
static int announcements[512];
static size_t announcement_count;
static int selections[16];
static size_t selection_count;
static size_t selection_position;
static unsigned int child_menus;
static int child_result;
static bool ui_cancel;
static bool ui_usb;
static unsigned int lists;
static bool hold_bluetooth_completion;
static bool live_entry;
static unsigned int live_entry_navigation;
static unsigned int service_allowed_count;
static unsigned int service_inhibited_count;
static bool service_allowed;
static bool service_checks_enabled;

void hiby_bluetooth_service_allow(bool allowed)
{
    pthread_mutex_lock(&backend_mutex);
    service_allowed = allowed;
    if (allowed)
    {
        ++service_allowed_count;
        if (service_checks_enabled)
        {
#ifdef CONNECTIVITY_NATIVE
            assert(!state.inhibited && !pending && !stopping);
            assert(!operation_cancelled());
#else
            assert(!"Simulator must never authorize a native Bluetooth service");
#endif
            assert(state.bluetooth_desired && !state.airplane_mode);
            assert(state.settled && !state.storage_error);
            assert(state.bluetooth == HIBY_CONNECTIVITY_ON);
            assert(!inhibited && !bluetooth.busy && bluetooth.power_known && bluetooth.enabled);
            assert(bluetooth.error == HIBY_BT_OK);
        }
    }
    else
        ++service_inhibited_count;
    pthread_mutex_unlock(&backend_mutex);
}

#ifdef CONNECTIVITY_NATIVE
static pthread_mutex_t race_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t race_changed = PTHREAD_COND_INITIALIZER;
static pthread_t race_control_thread;
static bool race_armed;
static bool race_worker_at_setter;
static bool race_release_setter;
static bool race_control_started;
static bool race_allow_control;
static bool race_protected;
static unsigned int race_stale_uninhibits;

static void race_wait(const bool *condition)
{
    struct timespec deadline;
    assert(clock_gettime(CLOCK_REALTIME, &deadline) == 0);
    deadline.tv_sec += 2;
    while (!*condition)
        assert(pthread_cond_timedwait(&race_changed, &race_mutex, &deadline) == 0);
}
#endif

static void delay_ms(unsigned int milliseconds)
{
    struct timespec duration = {
        .tv_sec = milliseconds / 1000,
        .tv_nsec = (milliseconds % 1000) * 1000000
    };
    nanosleep(&duration, NULL);
}

static void preferences(bool wifi_enabled, bool bluetooth_enabled, bool airplane)
{
    stored_length = snprintf(stored, sizeof(stored), CONNECTIVITY_FORMAT,
        (unsigned int)wifi_enabled, (unsigned int)bluetooth_enabled, (unsigned int)airplane);
    stored_exists = true;
}

static struct hiby_connectivity_snapshot wait_complete(void)
{
    struct hiby_connectivity_snapshot snapshot;
    for (unsigned int iteration = 0; iteration < 2000; ++iteration)
    {
        hiby_connectivity_get_snapshot(&snapshot);
        if (!snapshot.busy)
            return snapshot;
        delay_ms(1);
    }
    assert(!"Controller never settled within fixture deadline");
    return snapshot;
}

static bool wifi_child_pending;
static unsigned int wifi_cancellations;

void hiby_wifi_cancel(void)
{
    __atomic_add_fetch(&wifi_cancellations, 1, __ATOMIC_RELEASE);
}

bool hiby_wifi_settled(void)
{
    return !__atomic_load_n(&wifi_child_pending, __ATOMIC_ACQUIRE);
}

struct hiby_wifi_result hiby_wifi_set_enabled(bool enabled)
{
    pthread_mutex_lock(&backend_mutex);
    ++wifi_sets;
    wifi_enables += enabled;
    if (!enabled && !disable_order)
        disable_order = ++sequence;
    wifi.soft_blocked_radios = enabled ? 0 : wifi.wlan_radios;
    wifi.interfaces_up = enabled ? wifi.interfaces_present : 0;
    wifi.interfaces_down = enabled ? 0 : wifi.interfaces_present;
    if (!strcmp(radio_fault, "mixed-soft"))
        wifi.soft_blocked_radios = 1;
    if (!strcmp(radio_fault, "hard-any"))
    {
        wifi.hard_blocked_radios = 1;
        wifi.soft_blocked_radios = 0;
    }
    if (!strcmp(radio_fault, "interface-up"))
    {
        wifi.interfaces_up = 1;
        wifi.interfaces_down = wifi.interfaces_present - 1;
    }
    struct hiby_wifi_result result = wifi;
    if (!strcmp(radio_fault, "wifi-write"))
        result.rfkill_error = EACCES;
    if (!strcmp(radio_fault, "wifi-interface-write"))
        result.interface_error = EIO;
    if (!strcmp(radio_fault, "wifi-write-read"))
        result.rfkill_read_error = EIO;
    if (!strcmp(radio_fault, "wifi-state-error"))
        result.state = HIBY_WIFI_ERROR;
    if (!strcmp(radio_fault, "wifi-driver-error"))
        result.driver_error = EIO;
    if (!strcmp(radio_fault, "wifi-unsettled"))
    {
        __atomic_store_n(&wifi_child_pending, true, __ATOMIC_RELEASE);
        result.driver_error = ETIMEDOUT;
    }
    pthread_mutex_unlock(&backend_mutex);
    return result;
}

struct hiby_wifi_result hiby_wifi_get_state(void)
{
    pthread_mutex_lock(&backend_mutex);
    ++wifi_queries;
    struct hiby_wifi_result result = wifi;
    if (!strcmp(radio_fault, "wifi-read"))
        result.rfkill_read_error = EIO;
    if (!strcmp(radio_fault, "wifi-interface-read"))
        result.interface_read_error = EIO;
    if (!strcmp(radio_fault, "wifi-counts"))
        ++result.interfaces_down;
    pthread_mutex_unlock(&backend_mutex);
    return result;
}

bool hiby_bluetooth_init(void)
{
    pthread_mutex_lock(&backend_mutex);
    ++bluetooth_calls;
    bool thread_failed = !strcmp(radio_fault, "bt-thread");
    if (thread_failed)
        bluetooth.error = HIBY_BT_THREAD_FAILED;
    bool available = bluetooth_available && !thread_failed;
    pthread_mutex_unlock(&backend_mutex);
    return available;
}

void hiby_bluetooth_set_inhibited(bool enabled)
{
#ifdef CONNECTIVITY_NATIVE
    if (race_armed && !enabled)
    {
        pthread_mutex_lock(&race_mutex);
        if (!race_worker_at_setter)
        {
            race_worker_at_setter = true;
            pthread_cond_broadcast(&race_changed);
            race_wait(&race_release_setter);
        }
        race_stale_uninhibits += race_protected;
        pthread_mutex_unlock(&race_mutex);
    }
#endif
    pthread_mutex_lock(&backend_mutex);
    ++bluetooth_calls;
    inhibited = enabled;
    if (enabled && !inhibit_order)
        inhibit_order = ++sequence;
    pthread_mutex_unlock(&backend_mutex);
    if (enabled)
        hiby_bluetooth_service_allow(false);
#ifdef CONNECTIVITY_NATIVE
    if (race_armed && enabled)
    {
        pthread_mutex_lock(&race_mutex);
        if (race_control_started && pthread_equal(pthread_self(), race_control_thread))
        {
            race_protected = true;
            pthread_cond_broadcast(&race_changed);
        }
        pthread_mutex_unlock(&race_mutex);
    }
#endif
}

void hiby_bluetooth_cancel(void)
{
    pthread_mutex_lock(&backend_mutex);
    ++bluetooth_calls;
    bluetooth_cancelled = true;
    pthread_mutex_unlock(&backend_mutex);
}

bool hiby_bluetooth_request(enum hiby_bt_operation operation, const char *address)
{
    (void)address;
#ifdef CONNECTIVITY_NATIVE
    if (race_armed && operation == HIBY_BT_ENABLE)
    {
        pthread_mutex_lock(&race_mutex);
        race_wait(&race_protected);
        pthread_mutex_unlock(&race_mutex);
    }
#endif
    pthread_mutex_lock(&backend_mutex);
    ++bluetooth_calls;
    assert(!bluetooth.busy);
    if (inhibited && (operation == HIBY_BT_ENABLE || operation == HIBY_BT_SCAN ||
                      operation == HIBY_BT_CONNECT))
    {
        bluetooth.error = HIBY_BT_INHIBITED;
        ++bluetooth.generation;
        pthread_mutex_unlock(&backend_mutex);
        return false;
    }
    ++bluetooth_requests[operation];
    if (operation == HIBY_BT_ENABLE)
        ++bluetooth_enables;
    if (!strcmp(radio_fault, "bt-reject") || !strcmp(radio_fault, "bt-reject-ok"))
    {
        bluetooth.error = !strcmp(radio_fault, "bt-reject-ok") ? HIBY_BT_OK : HIBY_BT_COMMAND_FAILED;
        pthread_mutex_unlock(&backend_mutex);
        return false;
    }
    bluetooth.busy = true;
    bluetooth.power_known = false;
    bluetooth_pending = true;
    bluetooth_cancelled = false;
    bluetooth_operation_pending = operation;
    bluetooth_remaining = !strcmp(radio_fault, "bt-slow") ? 3 : 0;
    if (strcmp(radio_fault, "bt-stale"))
        ++bluetooth.generation;
    pthread_mutex_unlock(&backend_mutex);
    return true;
}

void hiby_bluetooth_get_snapshot(struct hiby_bt_snapshot *snapshot)
{
    pthread_mutex_lock(&backend_mutex);
    ++bluetooth_calls;
    if (bluetooth.busy && !__atomic_load_n(&hold_bluetooth_completion, __ATOMIC_ACQUIRE) &&
        strcmp(radio_fault, "bt-hang") &&
        strcmp(radio_fault, "bt-timeout"))
    {
        if (bluetooth_remaining)
            --bluetooth_remaining;
        else
        {
            bluetooth.busy = false;
            if (bluetooth_pending && bluetooth_operation_pending != HIBY_BT_REFRESH)
                bluetooth.enabled = bluetooth_operation_pending == HIBY_BT_ENABLE;
            bluetooth.power_known = strcmp(radio_fault, "bt-unknown") != 0;
            bluetooth.available = bluetooth_available;
            if (!strcmp(radio_fault, "bt-available-false"))
                bluetooth.available = false;
            bluetooth.error = HIBY_BT_OK;
            if (!strcmp(radio_fault, "bt-write") && bluetooth_operation_pending != HIBY_BT_REFRESH)
                bluetooth.error = HIBY_BT_COMMAND_FAILED;
            if (!strcmp(radio_fault, "bt-read"))
            {
                bluetooth.error = HIBY_BT_COMMAND_FAILED;
                bluetooth.power_known = false;
            }
            if (bluetooth_cancelled)
                bluetooth.error = HIBY_BT_CANCELLED;
            bluetooth_pending = false;
            if (strcmp(radio_fault, "bt-stale"))
                ++bluetooth.generation;
        }
    }
    if (!strcmp(radio_fault, "bt-timeout") && bluetooth_cancelled)
    {
        bluetooth.busy = false;
        bluetooth.enabled = true;
        bluetooth.power_known = false;
        bluetooth.error = HIBY_BT_CANCELLED;
    }
    *snapshot = bluetooth;
    pthread_mutex_unlock(&backend_mutex);
}

int hiby_bluetooth_menu(void)
{
    ++child_menus;
    return child_result;
}

static char *str(int identifier)
{
    assert(identifier >= 1000 && identifier < 1000 + CONNECTIVITY_LABEL_COUNT);
    return (char *)connectivity_labels[identifier - 1000];
}

static int talk_id(int identifier, bool enqueue)
{
    (void)str(identifier);
    assert(announcement_count < sizeof(announcements) / sizeof(announcements[0]));
    announcements[announcement_count++] = identifier;
    if (!enqueue)
        speech_count = 0;
    assert(speech_count < sizeof(spoken) / sizeof(spoken[0]));
    spoken[speech_count++] = identifier;
    return 0;
}

static void splashf_silent(int ticks, const char *format, ...)
{
    assert(ticks >= 0);
    assert(!strcmp(format, "%s"));
}

static void simplelist_info_init(struct simplelist_info *info, const char *title,
                                 int count, void *data)
{
    memset(info, 0, sizeof(*info));
    info->title = title;
    info->count = count;
    info->callback_data = data;
}

static bool simplelist_show_list(struct simplelist_info *info)
{
    ++lists;
    assert(info->count == 1 || info->count == 3);
    assert(!strcmp(info->title, str(info->count == 1 ? LANG_HIBY_WIFI : LANG_CONNECTIVITY)));
    struct gui_synclist list = { .selected_item = info->selection, .data = info->callback_data };
    assert(info->action_callback);
    assert(info->action_callback(ACTION_REDRAW, &list) == ACTION_REDRAW);
    if (live_entry && lists == 1)
    {
        struct hiby_connectivity_snapshot snapshot;
        hiby_connectivity_get_snapshot(&snapshot);
        assert(snapshot.busy);
        for (int selected = 1; selected < info->count; ++selected)
        {
            list.selected_item = selected;
            info->get_talk(selected, info->callback_data);
            assert(spoken[0] == (selected == 1 ? LANG_HIBY_BT_TITLE : LANG_HIBY_AIRPLANE_MODE));
            assert(spoken[speech_count - 1] == LANG_HIBY_BT_WORKING);
            assert(info->action_callback(ACTION_STD_NEXT, &list) == ACTION_STD_NEXT);
            assert(list.selected_item == selected);
            ++live_entry_navigation;
        }
        __atomic_store_n(&hold_bluetooth_completion, false, __ATOMIC_RELEASE);
    }
    for (unsigned int iteration = 0; iteration < 1000; ++iteration)
    {
        struct hiby_connectivity_snapshot snapshot;
        hiby_connectivity_get_snapshot(&snapshot);
        int action = info->action_callback(ACTION_NONE, &list);
        assert(action == ACTION_NONE || action == ACTION_REDRAW);
        if (!snapshot.busy)
            break;
        assert(iteration < 999);
        delay_ms(1);
    }
    char invalid_buffer[16];
    assert(!info->get_name(-1, info->callback_data, invalid_buffer, sizeof(invalid_buffer))[0]);
    assert(!info->get_name(info->count, info->callback_data, invalid_buffer, sizeof(invalid_buffer))[0]);
    assert(!info->get_talk(-1, info->callback_data));
    assert(!info->get_talk(info->count, info->callback_data));
    for (int selected = 0; selected < info->count; ++selected)
    {
        char buffer[256];
        const char *name = info->get_name(selected, info->callback_data, buffer, sizeof(buffer));
        assert(name[0]);
        info->get_talk(selected, info->callback_data);
        assert(speech_count >= 2);
        assert(strstr(name, str(spoken[0])));
        assert(strstr(name, str(spoken[speech_count - 1])));
    }
    assert(selection_position < selection_count);
    info->selection = selections[selection_position++];
    return false;
}

static void storage_case(const char *mode)
{
    preferences(false, false, false);
    if (!strncmp(mode, "read-", 5))
    {
        fault = mode;
        assert(hiby_connectivity_init());
        struct hiby_connectivity_snapshot snapshot;
        hiby_connectivity_get_snapshot(&snapshot);
        bool success = !strcmp(mode, "read-short") || !strcmp(mode, "read-eintr");
        assert((snapshot.storage_error == 0) == success);
        assert(!snapshot.wifi_desired && !snapshot.bluetooth_desired && !snapshot.airplane_mode);
        assert(!wifi_sets && !bluetooth_enables);
        return;
    }
    char previous[128];
    memcpy(previous, stored, stored_length);
    size_t previous_length = stored_length;
    assert(hiby_connectivity_init());
    fault = mode;
    if (!strcmp(mode, "stale-temp"))
        temporary_exists = true;
    assert(hiby_connectivity_set_bluetooth_enabled(true));
    struct hiby_connectivity_snapshot snapshot = wait_complete();
    bool success = !strcmp(mode, "none") || !strcmp(mode, "short") || !strcmp(mode, "write-eintr");
    assert((snapshot.storage_error == 0) == success);
    if (success)
    {
        assert(renames == 1);
        assert(memcmp(previous, stored, stored_length));
        assert(snapshot.bluetooth_desired);
    }
    else
    {
        assert(snapshot.result == HIBY_CONNECTIVITY_STORAGE_ERROR);
        assert(stored_length == previous_length && !memcmp(previous, stored, previous_length));
        assert(!bluetooth_enables && !wifi_enables);
    }
}

static void invalid_case(const char *mode)
{
    preferences(true, true, true);
    if (!strcmp(mode, "version"))
        stored[15] = '2';
    else if (!strcmp(mode, "trailing"))
        stored[stored_length++] = '\n';
    else if (!strcmp(mode, "truncated"))
        --stored_length;
    else if (!strcmp(mode, "nul"))
        stored[10] = '\0';
    else if (!strcmp(mode, "value"))
        stored[sizeof("RBCONNECTIVITY:1\nwifi:") - 1] = '2';
    else if (!strcmp(mode, "space"))
        stored[sizeof("RBCONNECTIVITY:1\nwifi:") - 2] = ' ';
    else if (!strcmp(mode, "empty"))
        stored_length = 0;
    else if (!strcmp(mode, "oversized"))
    {
        memset(stored, '0', sizeof(stored));
        stored_length = sizeof(stored);
    }
    else
        assert(!"Unknown malformed configuration test");
    assert(hiby_connectivity_init());
    struct hiby_connectivity_snapshot snapshot;
    hiby_connectivity_get_snapshot(&snapshot);
    assert(snapshot.storage_error == EINVAL);
    assert(!snapshot.wifi_desired && !snapshot.bluetooth_desired && !snapshot.airplane_mode);
    assert(!writes && !wifi_sets && !bluetooth_enables);
    assert(hiby_connectivity_apply_startup_policy());
    snapshot = wait_complete();
    assert(snapshot.result == HIBY_CONNECTIVITY_STORAGE_ERROR);
    assert(!wifi_enables && !bluetooth_enables);
}

static void policy_case(const char *mode)
{
    bool restore_wifi = !strcmp(mode, "restore-both") || !strcmp(mode, "restore-wifi");
    bool restore_bluetooth = !strcmp(mode, "restore-both") || !strcmp(mode, "restore-bt");
    if (restore_wifi || restore_bluetooth || !strcmp(mode, "restore-neither") ||
        !strcmp(mode, "saved-airplane"))
        preferences(restore_wifi, restore_bluetooth, !strcmp(mode, "saved-airplane"));
    assert(hiby_connectivity_init());
    struct hiby_connectivity_snapshot snapshot;
    hiby_connectivity_get_snapshot(&snapshot);
#ifdef CONNECTIVITY_NATIVE
    assert(snapshot.wifi == HIBY_CONNECTIVITY_UNKNOWN && snapshot.bluetooth == HIBY_CONNECTIVITY_UNKNOWN);
#endif
    assert(!wifi_sets && !bluetooth_requests[HIBY_BT_ENABLE] && !bluetooth_requests[HIBY_BT_DISABLE]);
    assert(hiby_connectivity_apply_startup_policy());
    snapshot = wait_complete();
#ifdef CONNECTIVITY_NATIVE
    assert(wifi_sets == 1 && bluetooth_requests[HIBY_BT_DISABLE] + bluetooth_requests[HIBY_BT_ENABLE] == 1);
    assert(snapshot.wifi == (restore_wifi ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF));
    assert(snapshot.bluetooth == (restore_bluetooth ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF));
#else
    assert(snapshot.result == HIBY_CONNECTIVITY_NOT_AVAILABLE);
    assert(!wifi_sets && !wifi_queries && !bluetooth_calls);
#endif
    if (restore_wifi || restore_bluetooth || !strcmp(mode, "restore-neither"))
    {
        assert(hiby_connectivity_set_airplane_mode(true));
        snapshot = wait_complete();
        assert(snapshot.wifi_desired == restore_wifi && snapshot.bluetooth_desired == restore_bluetooth);
        assert(snapshot.airplane_mode && snapshot.inhibited);
#ifdef CONNECTIVITY_NATIVE
        assert(snapshot.wifi == HIBY_CONNECTIVITY_OFF && snapshot.bluetooth == HIBY_CONNECTIVITY_OFF);
#endif
        unsigned int previous_wifi_enables = wifi_enables;
        unsigned int previous_bluetooth_enables = bluetooth_enables;
        assert(hiby_connectivity_set_wifi_enabled(restore_wifi));
        wait_complete();
        assert(hiby_connectivity_set_bluetooth_enabled(restore_bluetooth));
        snapshot = wait_complete();
        assert(wifi_enables == previous_wifi_enables && bluetooth_enables == previous_bluetooth_enables);
        assert(hiby_connectivity_set_airplane_mode(false));
        snapshot = wait_complete();
        assert(!snapshot.airplane_mode && !snapshot.inhibited);
#ifdef CONNECTIVITY_NATIVE
        assert(snapshot.wifi == (restore_wifi ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF));
        assert(snapshot.bluetooth == (restore_bluetooth ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF));
#endif
    }
    assert(hiby_connectivity_wifi_desired() == snapshot.wifi_desired);
    assert(hiby_connectivity_bluetooth_desired() == snapshot.bluetooth_desired);
    assert(hiby_connectivity_airplane_mode() == snapshot.airplane_mode);
}

static void radio_case(const char *mode)
{
    radio_fault = mode;
    if (!strcmp(mode, "wifi-suspended"))
    {
        wifi.state = HIBY_WIFI_DRIVER_SUSPENDED;
        wifi.wlan_radios = wifi.soft_blocked_radios = 0;
        wifi.interfaces_present = wifi.interfaces_up = wifi.interfaces_down = 0;
    }
    if (!strcmp(mode, "no-wlan"))
        wifi.wlan_radios = wifi.soft_blocked_radios = 0;
    if (!strcmp(mode, "no-bt"))
        bluetooth_available = false;
    assert(hiby_connectivity_set_airplane_mode(true));
    struct hiby_connectivity_snapshot snapshot = wait_complete();
    assert(wifi_sets >= 1);
    assert(inhibit_order && disable_order && inhibit_order < disable_order);
    if (strcmp(mode, "no-bt") && strcmp(mode, "bt-hang") && strcmp(mode, "bt-thread"))
        assert(bluetooth_requests[HIBY_BT_DISABLE] >= 1);
    assert(snapshot.airplane_mode && snapshot.inhibited);
    if (!strcmp(mode, "none") || !strcmp(mode, "wifi-suspended"))
        assert(snapshot.result == HIBY_CONNECTIVITY_OK);
    else
        assert(snapshot.result != HIBY_CONNECTIVITY_OK);
    if (!strcmp(mode, "mixed-soft") || !strcmp(mode, "hard-any") || !strcmp(mode, "interface-up"))
        assert(snapshot.wifi == HIBY_CONNECTIVITY_PARTIAL);
    if (!strcmp(mode, "no-wlan"))
        assert(snapshot.wifi == HIBY_CONNECTIVITY_PARTIAL);
    if (!strcmp(mode, "bt-thread"))
        assert(snapshot.bluetooth == HIBY_CONNECTIVITY_RADIO_ERROR && snapshot.result == HIBY_CONNECTIVITY_FAILED);
    if (!strcmp(mode, "bt-unknown"))
        assert(snapshot.bluetooth == HIBY_CONNECTIVITY_UNKNOWN);
    if (!strcmp(mode, "wifi-suspended"))
        assert(snapshot.wifi == HIBY_CONNECTIVITY_DRIVER_SUSPENDED);
    if (!strcmp(mode, "wifi-driver-error"))
        assert(snapshot.wifi == HIBY_CONNECTIVITY_RADIO_ERROR);
    if (!strcmp(mode, "wifi-unsettled"))
    {
        assert(!snapshot.settled && snapshot.result == HIBY_CONNECTIVITY_TIMEOUT);
        assert(!hiby_connectivity_set_bluetooth_enabled(true));
        assert(!hiby_connectivity_set_airplane_mode(false));
        assert(!bluetooth_enables && snapshot.inhibited);
        __atomic_store_n(&wifi_child_pending, false, __ATOMIC_RELEASE);
        radio_fault = "none";
        assert(hiby_connectivity_set_airplane_mode(false));
        snapshot = wait_complete();
        assert(snapshot.settled && snapshot.result == HIBY_CONNECTIVITY_OK);
        assert(!snapshot.airplane_mode && !snapshot.bluetooth_desired && !bluetooth_enables);
    }
}

static void observed_transaction_case(const char *mode)
{
    assert(hiby_connectivity_apply_startup_policy());
    struct hiby_connectivity_snapshot snapshot = wait_complete();
    assert(snapshot.result == HIBY_CONNECTIVITY_OK);
    unsigned int refreshes = bluetooth_requests[HIBY_BT_REFRESH];
    unsigned int enables = bluetooth_requests[HIBY_BT_ENABLE];
    unsigned int disables = bluetooth_requests[HIBY_BT_DISABLE];
    if (!strcmp(mode, "refresh"))
        assert(hiby_connectivity_refresh());
    else
    {
        radio_fault = mode;
        if (!strcmp(mode, "connected-route"))
        {
            pthread_mutex_lock(&backend_mutex);
            strcpy(bluetooth.connected_address, "AA:BB:CC:DD:EE:FF");
            pthread_mutex_unlock(&backend_mutex);
        }
        assert(hiby_connectivity_set_bluetooth_enabled(strcmp(mode, "disable") != 0));
    }
    snapshot = wait_complete();
    bool reuse = !strcmp(mode, "enable") || !strcmp(mode, "disable");
    assert(bluetooth_requests[HIBY_BT_REFRESH] == refreshes + (reuse ? 0u : 1u));
    assert(bluetooth_requests[HIBY_BT_ENABLE] == enables +
        (strcmp(mode, "refresh") && strcmp(mode, "disable") ? 1u : 0u));
    assert(bluetooth_requests[HIBY_BT_DISABLE] == disables + (!strcmp(mode, "disable") ? 1u : 0u));
    assert(snapshot.settled && !snapshot.busy);
    if (reuse || !strcmp(mode, "refresh") || !strcmp(mode, "connected-route"))
        assert(snapshot.result == HIBY_CONNECTIVITY_OK);
    else
        assert(snapshot.result != HIBY_CONNECTIVITY_OK);
    if (!strcmp(mode, "enable"))
        assert(snapshot.bluetooth == HIBY_CONNECTIVITY_ON && snapshot.bluetooth_desired);
    if (!strcmp(mode, "disable"))
        assert(snapshot.bluetooth == HIBY_CONNECTIVITY_OFF && !snapshot.bluetooth_desired);
}

static void cancellation_case(const char *mode)
{
    radio_fault = !strcmp(mode, "unsettled") ? "bt-hang" : "bt-slow";
    assert(hiby_connectivity_init());
    if (!strcmp(mode, "existing") || !strcmp(mode, "preempt"))
    {
        pthread_mutex_lock(&backend_mutex);
        bluetooth.busy = true;
        bluetooth_pending = true;
        bluetooth_operation_pending = HIBY_BT_ENABLE;
        bluetooth_remaining = 2;
        pthread_mutex_unlock(&backend_mutex);
        assert(hiby_connectivity_set_airplane_mode(true));
    }
    else
    {
        assert(hiby_connectivity_set_bluetooth_enabled(true));
        if (!strcmp(mode, "queued"))
            hiby_connectivity_cancel();
        else
        {
            for (unsigned int iteration = 0; iteration < 1000; ++iteration)
            {
                pthread_mutex_lock(&backend_mutex);
                bool enabled = bluetooth_requests[HIBY_BT_ENABLE] > 0;
                pthread_mutex_unlock(&backend_mutex);
                if (enabled)
                    break;
                delay_ms(1);
            }
            if (!strcmp(mode, "airplane"))
                assert(hiby_connectivity_set_airplane_mode(true));
            else if (!strcmp(mode, "shutdown"))
                hiby_connectivity_shutdown();
            else
                hiby_connectivity_cancel();
        }
    }
    struct hiby_connectivity_snapshot snapshot = wait_complete();
    if (!strcmp(mode, "unsettled"))
    {
        assert(!snapshot.settled && snapshot.inhibited);
        assert(snapshot.result == HIBY_CONNECTIVITY_TIMEOUT);
        assert(snapshot.bluetooth != HIBY_CONNECTIVITY_OFF);
        return;
    }
    assert(snapshot.settled);
    assert(snapshot.bluetooth == HIBY_CONNECTIVITY_OFF && snapshot.wifi == HIBY_CONNECTIVITY_OFF);
    assert(snapshot.inhibited);
    delay_ms(100);
    pthread_mutex_lock(&backend_mutex);
    assert(!bluetooth.enabled && !bluetooth.busy);
    pthread_mutex_unlock(&backend_mutex);
    if (!strcmp(mode, "queued") || !strcmp(mode, "active") || !strcmp(mode, "shutdown"))
        assert(snapshot.result == HIBY_CONNECTIVITY_CANCELLED);
    else
        assert(snapshot.airplane_mode && snapshot.result == HIBY_CONNECTIVITY_OK);
}

static void busy_activation_case(const char *mode)
{
    assert(hiby_connectivity_init());
    pthread_mutex_lock(&backend_mutex);
    assert(hiby_connectivity_set_bluetooth_enabled(true));
    struct hiby_connectivity_snapshot queued;
    hiby_connectivity_get_snapshot(&queued);
    assert(queued.busy && queued.bluetooth_desired);
    assert(!hiby_connectivity_set_bluetooth_enabled(true));
    assert(!hiby_connectivity_set_bluetooth_enabled(false));
    assert(!hiby_connectivity_refresh());
    struct hiby_connectivity_snapshot unchanged;
    hiby_connectivity_get_snapshot(&unchanged);
    assert(unchanged.generation == queued.generation && unchanged.bluetooth_desired);
    assert(!bluetooth_requests[HIBY_BT_ENABLE] && !bluetooth_requests[HIBY_BT_DISABLE]);
    if (!strcmp(mode, "error"))
        radio_fault = "bt-write";
    pthread_mutex_unlock(&backend_mutex);
    struct hiby_connectivity_snapshot snapshot = wait_complete();
    assert(!snapshot.busy && snapshot.settled && snapshot.bluetooth_desired);
    assert(snapshot.result == (!strcmp(mode, "error") ? HIBY_CONNECTIVITY_FAILED : HIBY_CONNECTIVITY_OK));
    assert(bluetooth_requests[HIBY_BT_ENABLE] == 1 && !bluetooth_requests[HIBY_BT_DISABLE]);
    assert(renames == 1);
    if (!strcmp(mode, "fast-disable"))
    {
        pthread_mutex_lock(&backend_mutex);
        assert(hiby_connectivity_set_bluetooth_enabled(false));
        assert(!hiby_connectivity_set_bluetooth_enabled(true));
        pthread_mutex_unlock(&backend_mutex);
        snapshot = wait_complete();
        assert(snapshot.result == HIBY_CONNECTIVITY_OK && !snapshot.bluetooth_desired);
        assert(snapshot.bluetooth == HIBY_CONNECTIVITY_OFF && snapshot.settled && !snapshot.busy);
        assert(bluetooth_requests[HIBY_BT_DISABLE] == 1 && renames == 2);
    }
}

#ifdef CONNECTIVITY_NATIVE
static void *race_control(void *context)
{
    const char *mode = context;
    pthread_mutex_lock(&race_mutex);
    race_wait(&race_worker_at_setter);
    race_control_started = true;
    pthread_cond_broadcast(&race_changed);
    race_wait(&race_allow_control);
    pthread_mutex_unlock(&race_mutex);
    if (!strcmp(mode, "airplane"))
        assert(hiby_connectivity_set_airplane_mode(true));
    else if (!strcmp(mode, "shutdown"))
        hiby_connectivity_shutdown();
    else
        hiby_connectivity_cancel();
    return NULL;
}

static void race_case(const char *mode)
{
    assert(hiby_connectivity_init());
    race_armed = true;
    assert(pthread_create(&race_control_thread, NULL, race_control, (void *)mode) == 0);
    assert(hiby_connectivity_set_bluetooth_enabled(true));
    pthread_mutex_lock(&race_mutex);
    race_wait(&race_worker_at_setter);
    race_wait(&race_control_started);
    int controller_lock = pthread_mutex_trylock(&state_mutex);
    assert(controller_lock == 0 || controller_lock == EBUSY);
    if (!controller_lock)
        pthread_mutex_unlock(&state_mutex);
    race_allow_control = true;
    pthread_cond_broadcast(&race_changed);
    if (!controller_lock)
        race_wait(&race_protected);
    race_release_setter = true;
    pthread_cond_broadcast(&race_changed);
    pthread_mutex_unlock(&race_mutex);
    assert(pthread_join(race_control_thread, NULL) == 0);
    struct hiby_connectivity_snapshot snapshot = wait_complete();
    printf("RACE %s protected=%u stale_uninhibits=%u accepted_enables=%u settled=%u inhibited=%u\n",
        mode, (unsigned int)race_protected, race_stale_uninhibits, bluetooth_enables,
        (unsigned int)snapshot.settled, (unsigned int)snapshot.inhibited);
    fflush(stdout);
    assert(race_stale_uninhibits == 0);
    assert(race_protected && !bluetooth_enables);
    assert(snapshot.inhibited && snapshot.settled && !snapshot.busy);
    assert(snapshot.wifi == HIBY_CONNECTIVITY_OFF && snapshot.bluetooth == HIBY_CONNECTIVITY_OFF);
    pthread_mutex_lock(&backend_mutex);
    assert(inhibited && !bluetooth.busy && !bluetooth.enabled);
    pthread_mutex_unlock(&backend_mutex);
    assert(snapshot.airplane_mode == !strcmp(mode, "airplane"));
}

static void service_gate_case(const char *mode)
{
    service_checks_enabled = true;
    if (!strncmp(mode, "race-", 5))
    {
        race_case(mode + 5);
        assert(!service_allowed && !service_allowed_count);
        return;
    }
    if (!strcmp(mode, "cancel") || !strcmp(mode, "shutdown") || !strcmp(mode, "unsettled"))
    {
        cancellation_case(!strcmp(mode, "cancel") ? "active" : mode);
        assert(!service_allowed && !service_allowed_count);
        return;
    }
    bool startup = !strcmp(mode, "startup");
    bool airplane = !strcmp(mode, "airplane");
    bool disabled = !strcmp(mode, "disabled");
    bool transition = !strcmp(mode, "transition") || !strcmp(mode, "pending-airplane");
    if (startup || airplane)
        preferences(false, true, airplane);
    if (!strcmp(mode, "storage"))
        fault = "write";
    if (!strcmp(mode, "error"))
        radio_fault = "bt-write";
    if (!strcmp(mode, "unknown"))
        radio_fault = "bt-unknown";
    if (!strcmp(mode, "stale"))
        radio_fault = "bt-stale";
    if (!strcmp(mode, "unavailable"))
        bluetooth_available = false;
    if (!strcmp(mode, "wifi-unsettled"))
        radio_fault = "wifi-unsettled";
    assert(hiby_connectivity_init());
    assert(!service_allowed_count && !service_allowed);
    if (transition)
        __atomic_store_n(&hold_bluetooth_completion, true, __ATOMIC_RELEASE);
    if (startup || airplane || !strcmp(mode, "wifi-unsettled"))
        assert(hiby_connectivity_apply_startup_policy());
    else
        assert(hiby_connectivity_set_bluetooth_enabled(!disabled));
    if (transition)
    {
        bool started = false;
        for (unsigned int iteration = 0; iteration < 1000; ++iteration)
        {
            pthread_mutex_lock(&backend_mutex);
            started = bluetooth_requests[HIBY_BT_ENABLE] != 0;
            bool early = service_allowed || service_allowed_count;
            pthread_mutex_unlock(&backend_mutex);
            assert(!early);
            if (started)
                break;
            delay_ms(1);
        }
        assert(started);
        if (!strcmp(mode, "pending-airplane"))
            assert(hiby_connectivity_set_airplane_mode(true));
        __atomic_store_n(&hold_bluetooth_completion, false, __ATOMIC_RELEASE);
    }
    struct hiby_connectivity_snapshot snapshot = wait_complete();
    bool expected = !strcmp(mode, "enabled") || startup || !strcmp(mode, "transition");
    pthread_mutex_lock(&backend_mutex);
    assert(service_allowed == expected);
    assert(service_allowed_count == (expected ? 1u : 0u));
    assert(service_inhibited_count);
    pthread_mutex_unlock(&backend_mutex);
    if (expected)
        assert(snapshot.bluetooth_desired && snapshot.bluetooth == HIBY_CONNECTIVITY_ON &&
               snapshot.settled && !snapshot.inhibited && snapshot.result == HIBY_CONNECTIVITY_OK);
    hiby_connectivity_shutdown();
    assert(!service_allowed);
}
#endif

static void ui_case(const char *mode)
{
    if (!strcmp(mode, "entry-success") || !strcmp(mode, "entry-failed") || !strcmp(mode, "entry-live"))
    {
        wifi.soft_blocked_radios = wifi.wlan_radios;
        wifi.interfaces_down = wifi.interfaces_present;
        wifi.interfaces_up = 0;
        bluetooth.enabled = false;
        live_entry = !strcmp(mode, "entry-live");
        __atomic_store_n(&hold_bluetooth_completion, live_entry, __ATOMIC_RELEASE);
        if (!strcmp(mode, "entry-failed"))
            radio_fault = "bt-read";
        selections[0] = -1;
        selection_count = 1;
        assert(hiby_connectivity_menu() == 0);
        assert(lists == 1 && selection_position == 1);
        bool wifi_announced = false;
        bool failure_announced = false;
        for (size_t position = 0; position < announcement_count; ++position)
        {
            assert(announcements[position] != LANG_HIBY_BT_DONE);
            if (announcements[position] == LANG_HIBY_CONNECTIVITY_FAILED)
            {
                if (!failure_announced)
                    assert(!wifi_announced);
                failure_announced = true;
            }
            wifi_announced |= announcements[position] == LANG_HIBY_WIFI;
        }
        assert(wifi_announced);
        assert(failure_announced == !strcmp(mode, "entry-failed"));
        assert(live_entry_navigation == (live_entry ? 2u : 0u));
        return;
    }
    if (!strcmp(mode, "thread-failed") || !strcmp(mode, "unknown") ||
        !strcmp(mode, "interface-down") || !strcmp(mode, "driver-suspended"))
    {
        thread_failure = !strcmp(mode, "thread-failed");
        if (!strcmp(mode, "unknown"))
        {
            wifi.rfkill_read_error = ENOENT;
            wifi.rfkill_error = ENOENT;
        }
        if (!strcmp(mode, "interface-down"))
            wifi.state = HIBY_WIFI_INTERFACE_DOWN;
        if (!strcmp(mode, "driver-suspended"))
            wifi.state = HIBY_WIFI_DRIVER_SUSPENDED;
        int script[] = { 0, -1, -1 };
        memcpy(selections, script, sizeof(script));
        selection_count = sizeof(script) / sizeof(script[0]);
        assert(hiby_connectivity_menu() == 0);
        assert(lists == 3 && selection_position == selection_count);
        struct hiby_connectivity_snapshot snapshot;
        hiby_connectivity_get_snapshot(&snapshot);
        assert(snapshot.wifi == (!strcmp(mode, "interface-down") ?
            HIBY_CONNECTIVITY_INTERFACE_DOWN : !strcmp(mode, "driver-suspended") ?
            HIBY_CONNECTIVITY_DRIVER_SUSPENDED : HIBY_CONNECTIVITY_UNKNOWN));
        return;
    }
    if (!strcmp(mode, "child-usb") || !strcmp(mode, "list-usb"))
    {
        child_result = !strcmp(mode, "child-usb") ? 1 : MENU_ATTACHED_USB;
        selections[0] = 1;
        selection_count = 1;
        assert(hiby_connectivity_menu() == MENU_ATTACHED_USB);
        assert(child_menus == 1 && selection_position == 1);
        return;
    }
    if (!strcmp(mode, "cancel") || !strcmp(mode, "usb"))
    {
        assert(hiby_connectivity_init());
        assert(hiby_connectivity_apply_startup_policy());
        wait_complete();
        radio_fault = "bt-slow";
        ui_cancel = !strcmp(mode, "cancel");
        ui_usb = !strcmp(mode, "usb");
        struct connectivity_menu menu = {0};
        track_menu_operation(&menu, hiby_connectivity_set_bluetooth_enabled(true), true);
        struct gui_synclist list = { .data = &menu };
        int action = ui_usb ? SYS_USB_CONNECTED : ACTION_STD_CANCEL;
        assert(menu_action(action, &list) == action);
        struct hiby_connectivity_snapshot snapshot = wait_complete();
        menu_action(ACTION_NONE, &list);
        assert(snapshot.bluetooth == HIBY_CONNECTIVITY_OFF && snapshot.settled);
        assert(spoken[0] == LANG_HIBY_BT_CANCELLED);
        return;
    }
    int script[] = { 0, 0, -1, 1, 2, -1 };
    memcpy(selections, script, sizeof(script));
    selection_count = sizeof(script) / sizeof(script[0]);
    assert(hiby_connectivity_menu() == 0);
    assert(selection_position == selection_count && child_menus == 1 && lists == 6);
    struct hiby_connectivity_snapshot snapshot;
    hiby_connectivity_get_snapshot(&snapshot);
    assert(snapshot.airplane_mode && snapshot.wifi_desired);
}

int main(int count, char **arguments)
{
    assert(count == 3);
    wifi.wlan_radios = 2;
    wifi.interfaces_present = 2;
    wifi.interfaces_up = 2;
    bluetooth.available = true;
    bluetooth.enabled = true;
    if (!strcmp(arguments[1], "storage"))
        storage_case(arguments[2]);
    else if (!strcmp(arguments[1], "invalid"))
        invalid_case(arguments[2]);
    else if (!strcmp(arguments[1], "policy"))
        policy_case(arguments[2]);
    else if (!strcmp(arguments[1], "radio"))
        radio_case(arguments[2]);
    else if (!strcmp(arguments[1], "observed-transaction"))
        observed_transaction_case(arguments[2]);
    else if (!strcmp(arguments[1], "cancel"))
        cancellation_case(arguments[2]);
    else if (!strcmp(arguments[1], "busy-activation"))
        busy_activation_case(arguments[2]);
    else if (!strcmp(arguments[1], "ui"))
        ui_case(arguments[2]);
    else if (!strcmp(arguments[1], "race"))
    {
#ifdef CONNECTIVITY_NATIVE
        race_case(arguments[2]);
#else
        assert(!"Race test requires the native controller worker");
#endif
    }
    else if (!strcmp(arguments[1], "service-gate"))
    {
#ifdef CONNECTIVITY_NATIVE
        service_gate_case(arguments[2]);
#else
        assert(!"Service gate requires the native controller worker");
#endif
    }
    else if (!strcmp(arguments[1], "idle"))
    {
        assert(hiby_connectivity_apply_startup_policy());
        wait_complete();
        unsigned int before = bluetooth_calls + wifi_queries;
        delay_ms(100);
        assert(before == bluetooth_calls + wifi_queries);
    }
    else if (!strcmp(arguments[1], "thread"))
    {
        if (!strcmp(arguments[2], "restart-failure"))
        {
            assert(hiby_connectivity_apply_startup_policy());
            struct hiby_connectivity_snapshot previous = wait_complete();
            assert(previous.wifi == HIBY_CONNECTIVITY_OFF && previous.bluetooth == HIBY_CONNECTIVITY_OFF);
            hiby_connectivity_shutdown();
        }
        unsigned int previous_sets = wifi_sets;
        unsigned int previous_writes = writes;
        thread_failure = true;
        assert(!hiby_connectivity_init());
        assert(!hiby_connectivity_set_bluetooth_enabled(true));
        struct hiby_connectivity_snapshot snapshot;
        hiby_connectivity_get_snapshot(&snapshot);
        assert(snapshot.result == HIBY_CONNECTIVITY_FAILED);
        assert(!snapshot.bluetooth_desired && wifi_sets == previous_sets && !bluetooth_enables && writes == previous_writes);
        assert(snapshot.wifi == HIBY_CONNECTIVITY_UNKNOWN && snapshot.bluetooth == HIBY_CONNECTIVITY_UNKNOWN);
        thread_failure = false;
        assert(hiby_connectivity_apply_startup_policy());
        snapshot = wait_complete();
        assert(snapshot.result == HIBY_CONNECTIVITY_OK);
    }
    else
        assert(!"Unknown test family");
    hiby_connectivity_shutdown();
#ifdef SIMULATOR
    assert(!bluetooth_calls && !wifi_sets && !wifi_queries);
#endif
    printf("PASS %s %s\n", arguments[1], arguments[2]);
    return 0;
}
