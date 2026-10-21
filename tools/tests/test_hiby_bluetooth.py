"""Exercise the actual bounded HiBy backend and controller without Bluetooth hardware."""

import ctypes
import errno
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "firmware/target/hosted/hiby/bluetooth-hiby.c"
CONTROLLER = ROOT / "apps/hiby_bluetooth.c"
HEADER = BACKEND.with_suffix(".h")
ADDRESS = b"AA:BB:CC:DD:EE:FF"
OTHER = b"11:22:33:44:55:66"
OK, UNAVAILABLE, CANCELLED, TIMEOUT, INVALID, FAILED, PAIR_FAILED, PIN, CONNECT_FAILED, AUDIO_FAILED, BUSY, THREAD_FAILED = range(12)
POWERED_OFF = 12
INHIBITED = 13
ENABLE, SCAN, CONNECT, DISCONNECT, DISABLE, REMOVE, REFRESH = range(7)
CONNECT_PAIRED, VERIFY_LINK = range(7, 9)


class Device(ctypes.Structure):
    _fields_ = [("address", ctypes.c_char * 18), ("name", ctypes.c_char * 128), ("paired", ctypes.c_bool)]


class Snapshot(ctypes.Structure):
    _fields_ = [("available", ctypes.c_bool), ("enabled", ctypes.c_bool),
                ("busy", ctypes.c_bool), ("power_known", ctypes.c_bool), ("error", ctypes.c_int),
                ("generation", ctypes.c_uint), ("count", ctypes.c_size_t),
                ("connected_address", ctypes.c_char * 18),
                ("connected_name", ctypes.c_char * 128), ("devices", Device * 32)]


CANCEL = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)

HELPER = r'''
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>

static void delay(unsigned int milliseconds)
{
    struct timespec duration = { milliseconds / 1000, (milliseconds % 1000) * 1000000 };
    nanosleep(&duration, NULL);
}

static void mark(const char *name)
{
    char path[2048];
    snprintf(path, sizeof(path), "%s/%s", TEST_DIRECTORY, name);
    FILE *marker = fopen(path, "w");
    if (!marker)
        exit(76);
    fclose(marker);
}

static bool peer_live(const char *address)
{
    FILE *peers = fopen(TEST_DIRECTORY "/live-peers", "r");
    if (!peers)
        return false;
    char peer[64];
    bool found = false;
    while (fgets(peer, sizeof(peer), peers))
    {
        peer[strcspn(peer, "\r\n")] = '\0';
        found |= !strcmp(peer, address);
    }
    fclose(peers);
    return found;
}

static void update_peer(const char *address, bool connected)
{
    FILE *peers = fopen(TEST_DIRECTORY "/live-peers", "r");
    if (!peers)
        return;
    FILE *updated = fopen(TEST_DIRECTORY "/live-peers.tmp", "w");
    if (!updated)
        exit(77);
    char peer[64];
    while (fgets(peer, sizeof(peer), peers))
    {
        peer[strcspn(peer, "\r\n")] = '\0';
        if (strcmp(peer, address))
            fprintf(updated, "%s\n", peer);
    }
    if (connected)
        fprintf(updated, "%s\n", address);
    if (fclose(peers) || fclose(updated) ||
        rename(TEST_DIRECTORY "/live-peers.tmp", TEST_DIRECTORY "/live-peers"))
        exit(78);
}

int main(int count, char **arguments)
{
    char mode[80] = "good";
    FILE *configuration = fopen(TEST_DIRECTORY "/mode", "r");
    if (configuration)
    {
        if (!fgets(mode, sizeof(mode), configuration))
            return 71;
        fclose(configuration);
        mode[strcspn(mode, "\r\n")] = '\0';
    }
    FILE *record = fopen(TEST_DIRECTORY "/commands", "a");
    if (!record)
        return 72;
    for (int position = 0; position < count; position++)
        fprintf(record, "%s%c", arguments[position], position + 1 == count ? '\n' : '|');
    fclose(record);
    const char *command = count > 1 ? arguments[1] : "scan";
    if (!strcmp(command, "list-pcms") && !strncmp(mode, "pcm-", 4))
    {
        const char *path = "/org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/a2dpsrc/sink";
        if (!strcmp(mode, "pcm-prefix"))
            printf("/junk%s\n", path);
        else if (!strcmp(mode, "pcm-error-prefix"))
            printf("error opening endpoint: %s\n", path);
        else if (!strcmp(mode, "pcm-suffix"))
            printf("%s/unexpected\n", path);
        else if (!strcmp(mode, "pcm-wrong-peer"))
            puts("/org/bluealsa/hci0/dev_11_22_33_44_55_66/a2dpsrc/sink");
        else if (!strcmp(mode, "pcm-crlf"))
            printf("%s\r\n", path);
        else if (!strcmp(mode, "pcm-no-newline"))
            fputs(path, stdout);
        else
        {
            puts("/org/bluealsa/hci0/dev_11_22_33_44_55_66/a2dpsrc/sink");
            puts(path);
        }
        return 0;
    }
    if (!strcmp(command, "info") && !strncmp(mode, "auto-", 5))
    {
        bool after_connect = access(TEST_DIRECTORY "/connect-observed", F_OK) == 0;
        printf("Device %s\n", arguments[2]);
        printf("\tPaired: %s\n", !strcmp(mode, "auto-unpaired") ||
               (!strcmp(mode, "auto-paired-lost") && after_connect) ? "no" : "yes");
        if (strcmp(mode, "auto-trust-missing"))
            printf("\tTrusted: %s\n", !strcmp(mode, "auto-untrusted") ||
                   (!strcmp(mode, "auto-trust-lost") && after_connect) ? "no" : "yes");
        if (!strcmp(mode, "auto-trust-ambiguous"))
            puts("\tTrusted: no");
        printf("\tConnected: %s\n", peer_live(arguments[2]) ? "yes" : "no");
        return 0;
    }
    if (!strcmp(command, "pin-colored"))
    {
        fputs("\033[32m[agent]\033[0m Enter \033[32mPIN\033[0m code:", stdout);
        fflush(stdout);
        delay(5000);
        return 0;
    }
    if ((!strcmp(command, "devices") || !strcmp(command, "paired-devices")) &&
        !strncmp(mode, "name-", 5))
    {
        printf("Device AA:BB:CC:DD:EE:FF %s\n", mode + 5);
        return 0;
    }
    if ((!strcmp(command, "devices") || !strcmp(command, "paired-devices")) &&
        !strcmp(mode, "empty-lists"))
        return 0;
    if (!strcmp(command, "paired-devices") && !strcmp(mode, "paired-stdout-error"))
    {
        puts("No default controller available");
        return 0;
    }
    if ((!strcmp(command, "paired-devices") && !strcmp(mode, "paired-malformed")) ||
        (!strcmp(command, "devices") && !strcmp(mode, "devices-invalid-address")))
    {
        puts("Device AA:BB:GG:DD:EE:FF Invalid address");
        return 0;
    }
    if (!strcmp(command, "info") && (!strcmp(mode, "wrong-info-peer") ||
        !strcmp(mode, "ambiguous-paired") || !strcmp(mode, "missing-paired")))
    {
        printf("Device %s\n", !strcmp(mode, "wrong-info-peer") ?
               "11:22:33:44:55:66" : arguments[2]);
        if (strcmp(mode, "missing-paired"))
            puts("\tPaired: yes");
        if (!strcmp(mode, "ambiguous-paired"))
            puts("\tPaired: no");
        printf("\tConnected: %s\n", peer_live(arguments[2]) ? "yes" : "no");
        return 0;
    }
    if (!strcmp(command, "connect") && (!strcmp(mode, "connect-applied-error") ||
        !strcmp(mode, "post-connect-info-once") || !strcmp(mode, "post-connect-info-error")))
    {
        update_peer(arguments[2], true);
        mark("connect-observed");
        return !strcmp(mode, "connect-applied-error") ? 19 : 0;
    }
    if (!strcmp(command, "info") && access(TEST_DIRECTORY "/connect-observed", F_OK) == 0 &&
        (!strcmp(mode, "post-connect-info-error") || (!strcmp(mode, "post-connect-info-once") &&
         access(TEST_DIRECTORY "/post-info-failed", F_OK) != 0)))
    {
        mark("post-info-failed");
        return 19;
    }
    if (!strcmp(command, "list-pcms") && !strcmp(mode, "endpoint-late"))
    {
        delay(350);
        puts("/org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/a2dpsrc/sink");
        return 0;
    }
    if (!strcmp(command, "list-pcms") && !strcmp(mode, "endpoint-production-late"))
    {
        unsigned int probes = 0;
        FILE *counter = fopen(TEST_DIRECTORY "/endpoint-probes", "r");
        if (counter)
        {
            if (fscanf(counter, "%u", &probes) != 1)
                return 80;
            fclose(counter);
        }
        counter = fopen(TEST_DIRECTORY "/endpoint-probes", "w");
        if (!counter)
            return 81;
        fprintf(counter, "%u\n", probes + 1);
        fclose(counter);
        delay(1600);
        if (probes >= 3)
            puts("/org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/a2dpsrc/sink");
        return 0;
    }
    if (strstr(arguments[0], "/bt_resume"))
    {
        mark("resume-started");
        if (!strcmp(mode, "resume-hang"))
            delay(5000);
        if (!strcmp(mode, "enable-fails-on") || !strcmp(mode, "enable-fails-off") ||
            !strcmp(mode, "resume-failed"))
            return 1;
        mark("resumed");
        return 0;
    }
    if (!strcmp(command, "power") && count > 2 && !strcmp(arguments[2], "on") &&
        (!strcmp(mode, "enable-fails-on") || !strcmp(mode, "enable-fails-off")))
        return 1;
    if (!strcmp(command, "power") && count > 2 && !strcmp(arguments[2], "on") &&
        !strcmp(mode, "resume-needed") && access(TEST_DIRECTORY "/resumed", F_OK) != 0)
        return 1;
    if (!strcmp(command, "power") && count > 2 && !strcmp(arguments[2], "on"))
        unlink(TEST_DIRECTORY "/powered-off");
    if (!strcmp(command, "connect"))
    {
        unlink(TEST_DIRECTORY "/disconnected");
        mark("connect-observed");
        if (count > 2 && strcmp(mode, "connect-false"))
            update_peer(arguments[2], true);
    }
    if (!strcmp(command, "sleep"))
    {
        delay(5000);
        return 0;
    }
    if (!strcmp(command, "sleep-child") || !strcmp(command, "failed-child"))
    {
        pid_t child = fork();
        if (child == 0)
        {
            delay(5000);
            return 0;
        }
        printf("child=%ld\n", (long)child);
        fflush(stdout);
        if (!strcmp(command, "failed-child"))
            return 19;
        delay(5000);
        return 0;
    }
    if (!strcmp(command, "flood"))
    {
        char output[4096];
        memset(output, 'X', sizeof(output));
        for (int iteration = 0; iteration < 20; iteration++)
            if (write(STDOUT_FILENO, output, sizeof(output)) < 0)
                return 0;
        return 0;
    }
    if (!strcmp(command, "closed-input"))
    {
        close(STDIN_FILENO);
        delay(100);
        return 0;
    }
    if (!strcmp(command, "closed-output"))
    {
        close(STDOUT_FILENO);
        close(STDERR_FILENO);
        delay(5000);
        return 0;
    }
    if (!strcmp(command, "fast-output"))
    {
        fputs("\033[0;32mPowered: yes\033[0m\nfinal line\n", stdout);
        return 0;
    }
    if (!strcmp(command, "exit-failed"))
        return 19;
    if (!strcmp(command, "pin"))
    {
        puts("Enter PIN code:");
        return 0;
    }
    if (!strcmp(mode, "hang"))
    {
        delay(5000);
        return 0;
    }
    if ((!strcmp(command, "power") && count > 2 && !strcmp(arguments[2], "off") &&
         !strcmp(mode, "power-off-hang")) ||
        (!strcmp(command, "show") && !strcmp(mode, "show-hang")) ||
        (!strcmp(command, "disconnect") && !strcmp(mode, "disconnect-hang")) ||
        (!strcmp(command, "info") && !strcmp(mode, "info-hang")))
    {
        delay(5000);
        return 0;
    }
    if (!strcmp(command, "scan"))
    {
        char input[64];
        bool started = false;
        bool stopped = false;
        while (fgets(input, sizeof(input), stdin))
        {
            if (!strcmp(input, "scan on\n"))
            {
                started = true;
                if (!strcmp(mode, "scan-false"))
                    puts("Failed to start discovery: org.bluez.Error.NotReady");
                else
                    puts("Discovery started");
                fflush(stdout);
            }
            if (!strcmp(input, "scan off\n"))
                stopped = true;
            if (!strcmp(input, "quit\n"))
                return started && stopped ? 0 : 73;
        }
        return 74;
    }
    if (!strcmp(command, "power") && count > 2 && !strcmp(arguments[2], "off"))
    {
        if (!strcmp(mode, "power-off-command-failed"))
            return 1;
        if (strcmp(mode, "power-off-false") && strcmp(mode, "disconnect-and-power-fail"))
            mark("powered-off");
        if (!strcmp(mode, "power-off-applied-error"))
            return 1;
    }
    if (!strcmp(command, "show") && (!strcmp(mode, "show-failed") ||
        (!strcmp(mode, "off-show-failed") && access(TEST_DIRECTORY "/powered-off", F_OK) == 0)))
        return 1;
    if (!strcmp(command, "show") && (!strcmp(mode, "show-incomplete") ||
        (!strcmp(mode, "off-show-incomplete") && access(TEST_DIRECTORY "/powered-off", F_OK) == 0)))
        puts("Controller 00:00:00:00:00:00");
    else if (!strcmp(command, "show") && !strcmp(mode, "show-ambiguous"))
        puts("Controller 00:00:00:00:00:00\n\tPowered: yes\n\tPowered: no");
    else if (!strcmp(command, "show"))
        printf("Controller 00:00:00:00:00:00\n\tPowered: %s\n",
               !strcmp(mode, "power-false") || !strcmp(mode, "enable-fails-off") ||
               access(TEST_DIRECTORY "/powered-off", F_OK) == 0 ? "no" : "yes");
    else if (!strcmp(command, "info"))
    {
        if (!strcmp(mode, "observation-budget"))
            delay(100);
        if (!strcmp(mode, "info-failed"))
            return 1;
        if (!strcmp(mode, "info-incomplete"))
        {
            puts("Device AA:BB:CC:DD:EE:FF\n\tPaired: yes");
            return 0;
        }
        if (!strcmp(mode, "info-ambiguous"))
        {
            puts("Connected: yes\nConnected: no");
            return 0;
        }
        bool paired = strcmp(mode, "need-pair") && strcmp(mode, "pair-false") && strcmp(mode, "pin");
        if (access(TEST_DIRECTORY "/paired", F_OK) == 0 && strcmp(mode, "pair-false"))
            paired = true;
        bool connected = access(TEST_DIRECTORY "/live-peers", F_OK) == 0 ?
            count > 2 && peer_live(arguments[2]) :
            strcmp(mode, "connect-false") && access(TEST_DIRECTORY "/disconnected", F_OK) != 0;
        printf("Device %s\n\tPaired: %s\n\tTrusted: yes\n\tConnected: %s\n",
               count > 2 ? arguments[2] : "AA:BB:CC:DD:EE:FF",
               paired ? "yes" : "no", connected ? "yes" : "no");
    }
    else if (!strcmp(command, "pair"))
    {
        if (!strcmp(mode, "pin"))
            puts("Enter PIN code:");
        else
        {
            FILE *paired = fopen(TEST_DIRECTORY "/paired", "w");
            if (!paired)
                return 75;
            fclose(paired);
        }
    }
    else if (!strcmp(command, "paired-devices"))
    {
        if (!strcmp(mode, "paired-list-failed"))
            return 1;
        if (!strcmp(mode, "unsupported-command"))
            puts("Invalid command in menu main: paired-devices");
        else
            puts("Device AA:BB:CC:DD:EE:FF Headphones");
    }
    else if (!strcmp(command, "devices"))
    {
        if (!strcmp(mode, "device-list-failed"))
            return 1;
        if (!strcmp(mode, "device-list-overflow"))
        {
            for (unsigned int peer = 0; peer < 33; peer++)
                printf("Device 00:00:00:00:00:%02X Headphones\n", peer);
            return 0;
        }
        if (!strcmp(mode, "observation-budget"))
        {
            for (unsigned int peer = 0; peer < 8; peer++)
                printf("Device 00:00:00:00:00:%02X Headphones\n", peer);
            return 0;
        }
        if (!strcmp(mode, "device-list-error"))
        {
            puts("No default controller available");
            return 0;
        }
        if (!strcmp(mode, "device-list-malformed"))
        {
            puts("Device AA:BB:CC:DD:EE:FF");
            return 0;
        }
        puts("Device AA:BB:CC:DD:EE:FF Headphones");
        if (access(TEST_DIRECTORY "/removed-other", F_OK) != 0)
            puts("Device 11:22:33:44:55:66 Other headphones");
    }
    else if (!strcmp(command, "list-pcms") && strcmp(mode, "no-pcm") &&
             access(TEST_DIRECTORY "/endpoint-missing", F_OK) != 0)
        puts("/org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/a2dpsrc/sink");
    else if (!strcmp(command, "remove") && !strcmp(mode, "remove-fails"))
        return 1;
    else if (!strcmp(command, "remove") && strcmp(mode, "remove-false"))
        mark("removed-other");
    else if (!strcmp(command, "disconnect") &&
             (!strcmp(mode, "disconnect-fails") || !strcmp(mode, "disconnect-and-power-fail")))
        return 1;
    else if (!strcmp(command, "disconnect") && strcmp(mode, "disconnect-false"))
    {
        if (count > 2)
            update_peer(arguments[2], false);
        mark("disconnected");
    }
    return 0;
}
'''.replace("#include <fcntl.h>", "#include <fcntl.h>\n#include <stdbool.h>")

WRAPPER = r'''
#define _GNU_SOURCE 1
#include <stdbool.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <errno.h>
#include <unistd.h>
#include <time.h>
static bool endpoint_clock_failure;
static bool endpoint_clock_pending;
static unsigned int endpoint_clock_failures;
static int test_nanosleep(const struct timespec *duration, struct timespec *remaining)
{
    if (endpoint_clock_failure && duration->tv_sec == 0 && duration->tv_nsec == 100000000)
        endpoint_clock_pending = true;
    return nanosleep(duration, remaining);
}
static int test_clock_gettime(clockid_t clock, struct timespec *now)
{
    if (endpoint_clock_pending && clock == CLOCK_MONOTONIC)
    {
        endpoint_clock_pending = false;
        ++endpoint_clock_failures;
        errno = EIO;
        return -1;
    }
    return clock_gettime(clock, now);
}
static unsigned int read_interruptions_remaining;
static unsigned int read_interruptions_seen;
static ssize_t test_read(int descriptor, void *buffer, size_t length)
{
    if (read_interruptions_remaining)
    {
        --read_interruptions_remaining;
        ++read_interruptions_seen;
        errno = EINTR;
        return -1;
    }
    return read(descriptor, buffer, length);
}
static bool allocation_failed;
static unsigned int outstanding_allocations;
static void *test_malloc(size_t size)
{
    if (__atomic_load_n(&allocation_failed, __ATOMIC_SEQ_CST))
        return NULL;
    void *allocation = malloc(size);
    if (allocation)
        __atomic_add_fetch(&outstanding_allocations, 1, __ATOMIC_SEQ_CST);
    return allocation;
}
static void test_free(void *allocation)
{
    if (allocation)
        __atomic_sub_fetch(&outstanding_allocations, 1, __ATOMIC_SEQ_CST);
    free(allocation);
}
static int hold_children;
static pid_t test_waitpid(pid_t process, int *status, int options)
{
    return hold_children ? 0 : waitpid(process, status, options);
}
#define waitpid test_waitpid
#define malloc test_malloc
#define free test_free
#define read test_read
#define nanosleep test_nanosleep
#define clock_gettime test_clock_gettime
#define HIBY_BT_RFKILL_HOST_TEST 1
#include "BACKEND_PATH"
#undef waitpid
#undef malloc
#undef free
#undef read
#undef nanosleep
#undef clock_gettime
void test_endpoint_clock_failure(bool failed)
{
    endpoint_clock_failure = failed;
    endpoint_clock_pending = false;
    endpoint_clock_failures = 0;
}
void test_clear_cleanup_pending(void) { clear_cleanup_pending(NULL); }
unsigned int test_endpoint_clock_failures(void) { return endpoint_clock_failures; }
void test_read_interruptions(unsigned int count)
{
    read_interruptions_remaining = count;
    read_interruptions_seen = 0;
}
unsigned int test_read_interruptions_seen(void) { return read_interruptions_seen; }
static int rfkill_read_error = ENODEV;
static bool rfkill_is_blocked;
static bool rfkill_resume_unblocks;
void test_rfkill_resume_unblocks(bool unblocks)
{
    rfkill_resume_unblocks = unblocks;
}
void test_rfkill_state(int error, bool blocked)
{
    rfkill_read_error = error;
    rfkill_is_blocked = blocked;
}
int hiby_bluetooth_rfkill_blocked(bool *blocked)
{
    if (rfkill_read_error)
        return rfkill_read_error;
    *blocked = rfkill_is_blocked &&
        !(rfkill_resume_unblocks && access(HIBY_BT_BIN_DIRECTORY "/resumed", F_OK) == 0);
    return 0;
}
void test_fail_allocation(bool failed) { __atomic_store_n(&allocation_failed, failed, __ATOMIC_SEQ_CST); }
unsigned int test_allocations(void) { return __atomic_load_n(&outstanding_allocations, __ATOMIC_SEQ_CST); }
unsigned int test_child_slots_used(void)
{
    unsigned int used = 0;
    pthread_mutex_lock(&child_mutex);
    for (size_t position = 0; position < BT_CHILD_SLOTS; position++)
        if (child_slots[position])
            used++;
    pthread_mutex_unlock(&child_mutex);
    return used;
}
void test_hold_children(int hold) { hold_children = hold; }
static int route_failure;
static bool route_active;
void test_route_failure(int failure) { route_failure = failure; }
void test_route_active(bool active) { route_active = active; }
int pcm_alsa_switch_playback_device_cancellable(const char *device,
    hiby_pcm_cancel_callback cancel, void *context)
{
    if (cancel && cancel(context)) return -ECANCELED;
    if (route_failure)
        return route_failure;
    route_active = !strncmp(device, "bluealsa:", 9);
    return 0;
}
bool pcm_alsa_bluetooth_active(void) { return route_active; }
void pcm_alsa_set_bluetooth_volume(int left, int right) { (void)left; (void)right; }
int test_command(const char *path, const char *command, const char *input,
                 unsigned int hold, unsigned int timeout, char *output, size_t capacity,
                 hiby_bt_cancel_callback cancel, void *context)
{
    const char *arguments[] = {path, command, NULL};
    return run_command(arguments, input, hold, timeout, output, capacity, cancel, context);
}
'''

FAKE = r'''
#define _POSIX_C_SOURCE 200809L
#include "bluetooth-hiby.h"
#include <string.h>
#include <time.h>
static int active;
static int maximum;
static unsigned int calls;
static bool held;
static bool ignore_cancellation;
void test_hold_backend(bool hold) { __atomic_store_n(&held, hold, __ATOMIC_SEQ_CST); }
void test_ignore_cancellation(bool ignore) { __atomic_store_n(&ignore_cancellation, ignore, __ATOMIC_SEQ_CST); }
int test_active(void) { return __atomic_load_n(&active, __ATOMIC_SEQ_CST); }
bool hiby_bt_valid_address(const char *address)
{
    return address && !strcmp(address, "AA:BB:CC:DD:EE:FF");
}
enum hiby_bt_error hiby_bt_backend_execute(enum hiby_bt_operation operation,
    const char *address, struct hiby_bt_snapshot *state,
    hiby_bt_cancel_callback cancel, void *context)
{
    (void)address;
    int now = __atomic_add_fetch(&active, 1, __ATOMIC_SEQ_CST);
    int observed = __atomic_load_n(&maximum, __ATOMIC_SEQ_CST);
    while (observed < now && !__atomic_compare_exchange_n(&maximum, &observed, now,
            false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)) {}
    __atomic_add_fetch(&calls, 1, __ATOMIC_SEQ_CST);
    enum hiby_bt_error result = HIBY_BT_OK;
    while (__atomic_load_n(&held, __ATOMIC_SEQ_CST))
    {
        struct timespec delay = {0, 1000000};
        nanosleep(&delay, NULL);
    }
    for (unsigned int iteration = 0; iteration < 40; iteration++)
    {
        if (cancel(context) && !__atomic_load_n(&ignore_cancellation, __ATOMIC_SEQ_CST))
        {
            result = HIBY_BT_CANCELLED;
            break;
        }
        struct timespec delay = {0, 1000000};
        nanosleep(&delay, NULL);
    }
    if (result == HIBY_BT_OK)
    {
        state->available = true;
        if (operation != HIBY_BT_VERIFY_LINK)
            state->enabled = operation != HIBY_BT_DISABLE;
        state->power_known = true;
    }
    __atomic_sub_fetch(&active, 1, __ATOMIC_SEQ_CST);
    return result;
}
int test_maximum(void) { return __atomic_load_n(&maximum, __ATOMIC_SEQ_CST); }
unsigned int test_calls(void) { return __atomic_load_n(&calls, __ATOMIC_SEQ_CST); }
'''

SANITIZER_MAIN = r'''
#include "hiby_bluetooth.h"
#include <assert.h>
static void configure_backend(const char *mode)
{
    FILE *configuration = fopen(HIBY_BT_BIN_DIRECTORY "/mode", "w");
    assert(configuration);
    assert(fprintf(configuration, "%s\n", mode) > 0);
    assert(fclose(configuration) == 0);
    unlink(HIBY_BT_BIN_DIRECTORY "/powered-off");
    unlink(HIBY_BT_BIN_DIRECTORY "/resumed");
    unlink(HIBY_BT_BIN_DIRECTORY "/resume-started");
}
static void configure_live_peers(const char *peers)
{
    FILE *configuration = fopen(HIBY_BT_BIN_DIRECTORY "/live-peers", "w");
    assert(configuration);
    assert(fputs(peers, configuration) >= 0);
    assert(fclose(configuration) == 0);
}
static bool cancel_resume(void *context)
{
    (void)context;
    return access(HIBY_BT_BIN_DIRECTORY "/resume-started", F_OK) == 0;
}
static bool cancel_poweroff(void *context)
{
    (void)context;
    return access(HIBY_BT_BIN_DIRECTORY "/powered-off", F_OK) == 0;
}
static bool cancel_endpoint_clock(void *context)
{
    (void)context;
    return test_endpoint_clock_failures() >= 3;
}
static void wait_for_operation(void)
{
    struct hiby_bt_snapshot snapshot;
    unsigned int attempts = 0;
    do
    {
        struct timespec delay = {0, 1000000};
        nanosleep(&delay, NULL);
        hiby_bluetooth_get_snapshot(&snapshot);
        assert(++attempts < 3000);
    } while (snapshot.busy);
    assert(snapshot.error == HIBY_BT_OK);
    assert(test_allocations() == 0);
}
int main(void)
{
    struct hiby_bt_device devices[32];
    memset(devices, 0, sizeof(devices));
    for (size_t length = 0; length < 1024; length++)
    {
        char input[1200];
        memset(input, 'X', sizeof(input));
        memcpy(input, "Device AA:BB:CC:DD:EE:FF ", 25);
        input[25 + length] = '\0';
        assert(hiby_bt_parse_devices(input, devices, 0, 32, false) == 1);
        assert(strlen(devices[0].name) < sizeof(devices[0].name));
    }
    char output[16384];
    const char *arguments[] = {HIBY_BT_BIN_DIRECTORY "/helper", "fast-output", NULL};
    assert(run_command(arguments, NULL, 0, 500, output, sizeof(output), NULL, NULL) == HIBY_BT_OK);
    assert(strstr(output, "final line"));
    test_read_interruptions(3);
    assert(run_command(arguments, NULL, 0, 500, output, sizeof(output), NULL, NULL) == HIBY_BT_OK);
    assert(test_read_interruptions_seen() == 3);
    assert(strstr(output, "final line"));
    test_read_interruptions(64);
    assert(run_command(arguments, NULL, 0, 500, output, sizeof(output), NULL, NULL) == HIBY_BT_COMMAND_FAILED);
    assert(test_read_interruptions_seen() == 8);
    test_read_interruptions(0);
    for (unsigned int cycle = 0; cycle < 16; cycle++)
    {
        assert(hiby_bluetooth_init());
        assert(hiby_bluetooth_request(HIBY_BT_ENABLE, NULL));
        wait_for_operation();
        assert(hiby_bluetooth_request(HIBY_BT_CONNECT, "AA:BB:CC:DD:EE:FF"));
        wait_for_operation();
        assert(hiby_bluetooth_request(HIBY_BT_DISCONNECT, NULL));
        wait_for_operation();
        assert(hiby_bluetooth_request(HIBY_BT_DISABLE, NULL));
        wait_for_operation();
        hiby_bluetooth_shutdown();
        assert(test_allocations() == 0);
    }
    struct hiby_bt_snapshot state = {0};
    assert(hiby_bt_backend_execute(HIBY_BT_SCAN, NULL, &state, NULL, NULL) == HIBY_BT_POWERED_OFF);
    assert(state.power_known && !state.enabled);
    assert(hiby_bt_backend_execute(HIBY_BT_CONNECT, "AA:BB:CC:DD:EE:FF", &state,
                                   NULL, NULL) == HIBY_BT_POWERED_OFF);
    assert(state.power_known && !state.enabled);
    assert(hiby_bt_backend_execute(HIBY_BT_REFRESH, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    assert(state.power_known && !state.enabled && state.count == 2);
    test_route_failure(-EIO);
    assert(hiby_bt_backend_execute(HIBY_BT_DISABLE, NULL, &state, NULL, NULL) == HIBY_BT_AUDIO_FAILED);
    assert(state.power_known && !state.enabled);
    test_route_failure(0);
    configure_backend("power-off-command-failed");
    assert(hiby_bt_backend_execute(HIBY_BT_DISABLE, NULL, &state, NULL, NULL) == HIBY_BT_COMMAND_FAILED);
    assert(state.power_known && state.enabled);
    configure_backend("off-show-incomplete");
    assert(hiby_bt_backend_execute(HIBY_BT_DISABLE, NULL, &state, NULL, NULL) == HIBY_BT_COMMAND_FAILED);
    assert(!state.power_known && state.enabled);
    configure_backend("show-hang");
    assert(hiby_bt_backend_execute(HIBY_BT_SCAN, NULL, &state, NULL, NULL) == HIBY_BT_TIMEOUT);
    assert(!state.power_known);
    configure_backend("good");
    assert(hiby_bt_backend_execute(HIBY_BT_DISABLE, NULL, &state, cancel_poweroff, NULL) == HIBY_BT_CANCELLED);
    assert(!state.power_known && state.enabled);
    assert(hiby_bt_backend_execute(HIBY_BT_REFRESH, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    assert(state.power_known && !state.enabled);
    configure_backend("resume-needed");
    test_rfkill_state(0, true);
    test_rfkill_resume_unblocks(true);
    assert(hiby_bt_backend_execute(HIBY_BT_ENABLE, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    assert(state.power_known && state.enabled && state.count == 2);
    configure_backend("resume-failed");
    assert(hiby_bt_backend_execute(HIBY_BT_ENABLE, NULL, &state, NULL, NULL) == HIBY_BT_COMMAND_FAILED);
    assert(state.power_known && !state.enabled);
    configure_backend("resume-hang");
    assert(hiby_bt_backend_execute(HIBY_BT_ENABLE, NULL, &state, NULL, NULL) == HIBY_BT_TIMEOUT);
    assert(state.power_known && !state.enabled);
    configure_backend("resume-hang");
    assert(hiby_bt_backend_execute(HIBY_BT_ENABLE, NULL, &state, cancel_resume, NULL) == HIBY_BT_CANCELLED);
    assert(!state.power_known);
    assert(test_allocations() == 0);
    assert(test_child_slots_used() == 0);
    configure_backend("no-pcm");
    test_rfkill_state(ENODEV, false);
    test_rfkill_resume_unblocks(false);
    snprintf(state.connected_address, sizeof(state.connected_address), "11:22:33:44:55:66");
    test_route_active(true);
    test_endpoint_clock_failure(true);
    assert(hiby_bt_backend_execute(HIBY_BT_CONNECT, "AA:BB:CC:DD:EE:FF", &state,
                                   cancel_endpoint_clock, NULL) == HIBY_BT_COMMAND_FAILED);
    assert(test_endpoint_clock_failures() == 1);
    assert(!strcmp(state.connected_address, "11:22:33:44:55:66"));
    assert(pcm_alsa_bluetooth_active());
    assert(test_allocations() == 0);
    assert(test_child_slots_used() == 0);
    test_endpoint_clock_failure(false);
    configure_backend("no-pcm");
    configure_live_peers("AA:BB:CC:DD:EE:FF\n");
    memset(&state, 0, sizeof(state));
    test_route_active(false);
    assert(hiby_bt_backend_execute(HIBY_BT_CONNECT, "AA:BB:CC:DD:EE:FF", &state, NULL, NULL) == HIBY_BT_CONNECT_FAILED);
    assert(!state.connected_address[0]);
    bool connected = false;
    assert(read_connection("AA:BB:CC:DD:EE:FF", &connected, output, NULL, NULL) == HIBY_BT_OK && connected);
    assert(hiby_bt_backend_execute(HIBY_BT_DISCONNECT, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    assert(read_connection("AA:BB:CC:DD:EE:FF", &connected, output, NULL, NULL) == HIBY_BT_OK && !connected);
    configure_live_peers("11:22:33:44:55:66\n");
    snprintf(state.connected_address, sizeof(state.connected_address), "11:22:33:44:55:66");
    test_route_active(true);
    assert(hiby_bt_backend_execute(HIBY_BT_CONNECT, "AA:BB:CC:DD:EE:FF", &state, NULL, NULL) == HIBY_BT_CONNECT_FAILED);
    assert(!strcmp(state.connected_address, "11:22:33:44:55:66") && pcm_alsa_bluetooth_active());
    assert(read_connection("AA:BB:CC:DD:EE:FF", &connected, output, NULL, NULL) == HIBY_BT_OK && !connected);
    assert(read_connection("11:22:33:44:55:66", &connected, output, NULL, NULL) == HIBY_BT_OK && connected);
    configure_backend("good");
    memset(&state, 0, sizeof(state));
    test_route_active(false);
    assert(hiby_bt_backend_execute(HIBY_BT_DISCONNECT, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    configure_live_peers("AA:BB:CC:DD:EE:FF\n11:22:33:44:55:66\n");
    assert(hiby_bt_backend_execute(HIBY_BT_DISCONNECT, NULL, &state, NULL, NULL) == HIBY_BT_BUSY);
    configure_live_peers("AA:BB:CC:DD:EE:FF\n");
    snprintf(state.connected_address, sizeof(state.connected_address), "AA:BB:CC:DD:EE:FF");
    assert(hiby_bt_backend_execute(HIBY_BT_REFRESH, NULL, &state, NULL, NULL) == HIBY_BT_AUDIO_FAILED);
    assert(!strcmp(state.connected_address, "AA:BB:CC:DD:EE:FF"));
    assert(hiby_bt_backend_execute(HIBY_BT_DISCONNECT, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    assert(test_allocations() == 0 && test_child_slots_used() == 0);
    configure_backend("good");
    configure_live_peers("11:22:33:44:55:66\n");
    snprintf(state.connected_address, sizeof(state.connected_address), "11:22:33:44:55:66");
    test_route_active(true);
    assert(hiby_bt_backend_execute(HIBY_BT_CONNECT_PAIRED, "AA:BB:CC:DD:EE:FF", &state,
                                   NULL, NULL) == HIBY_BT_OK);
    assert(!strcmp(state.connected_address, "AA:BB:CC:DD:EE:FF"));
    assert(hiby_bt_backend_execute(HIBY_BT_VERIFY_LINK, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    configure_live_peers("11:22:33:44:55:66\n");
    assert(hiby_bt_backend_execute(HIBY_BT_VERIFY_LINK, NULL, &state, NULL, NULL) == HIBY_BT_CONNECT_FAILED);
    assert(!state.connected_address[0] && !pcm_alsa_bluetooth_active());
    configure_backend("auto-untrusted");
    assert(hiby_bt_backend_execute(HIBY_BT_CONNECT_PAIRED, "AA:BB:CC:DD:EE:FF", &state,
                                   NULL, NULL) == HIBY_BT_CONNECT_FAILED);
    configure_backend("post-connect-info-error");
    unlink(HIBY_BT_BIN_DIRECTORY "/connect-observed");
    snprintf(state.connected_address, sizeof(state.connected_address), "11:22:33:44:55:66");
    test_route_active(true);
    assert(hiby_bt_backend_execute(HIBY_BT_CONNECT, "AA:BB:CC:DD:EE:FF", &state,
                                   NULL, NULL) == HIBY_BT_COMMAND_FAILED);
    char pending[18];
    assert(hiby_bt_backend_cleanup_pending(pending));
    assert(!strcmp(pending, "AA:BB:CC:DD:EE:FF"));
    assert(!strcmp(state.connected_address, "11:22:33:44:55:66") && pcm_alsa_bluetooth_active());
    configure_backend("good");
    assert(hiby_bt_backend_execute(HIBY_BT_DISABLE, NULL, &state, NULL, NULL) == HIBY_BT_OK);
    assert(!hiby_bt_backend_cleanup_pending(pending));
    assert(test_allocations() == 0 && test_child_slots_used() == 0);
    unlink(HIBY_BT_BIN_DIRECTORY "/live-peers");
    assert(hiby_bluetooth_init());
    assert(hiby_bluetooth_request(HIBY_BT_SCAN, NULL));
    hiby_bluetooth_cancel();
    hiby_bluetooth_shutdown();
    close(STDIN_FILENO);
    close(STDOUT_FILENO);
    close(STDERR_FILENO);
    return run_command(arguments, NULL, 0, 500, output, sizeof(output), NULL, NULL) == HIBY_BT_OK ? 0 : 1;
}
'''

CONTROLLER_CLOCK_WRAPPER = r'''
#define _POSIX_C_SOURCE 200809L
#include <stdbool.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
static bool controller_clock_fake;
static long long controller_clock_value;
static long long controller_enqueue_advance;
static unsigned int controller_clock_reads;
static unsigned int controller_clock_failure;
static unsigned int controller_clock_backwards;
static int test_controller_clock_gettime(clockid_t clock, struct timespec *value)
{
    if (clock != CLOCK_MONOTONIC)
        return clock_gettime(clock, value);
    unsigned int reads = __atomic_add_fetch(&controller_clock_reads, 1, __ATOMIC_SEQ_CST);
    if (reads == __atomic_load_n(&controller_clock_failure, __ATOMIC_SEQ_CST))
    {
        errno = EIO;
        return -1;
    }
    if (!__atomic_load_n(&controller_clock_fake, __ATOMIC_SEQ_CST))
        return clock_gettime(clock, value);
    long long milliseconds = __atomic_load_n(&controller_clock_value, __ATOMIC_SEQ_CST);
    if (reads == __atomic_load_n(&controller_clock_backwards, __ATOMIC_SEQ_CST))
        milliseconds--;
    value->tv_sec = (time_t)(milliseconds / 1000);
    value->tv_nsec = (long)(milliseconds % 1000) * 1000000;
    return 0;
}
static int test_controller_cond_signal(pthread_cond_t *condition)
{
    long long advance = __atomic_exchange_n(&controller_enqueue_advance, 0, __ATOMIC_SEQ_CST);
    __atomic_add_fetch(&controller_clock_value, advance, __ATOMIC_SEQ_CST);
    return pthread_cond_signal(condition);
}
#define clock_gettime test_controller_clock_gettime
#define pthread_cond_signal test_controller_cond_signal
#include "CONTROLLER_PATH"
#undef pthread_cond_signal
#undef clock_gettime
void test_controller_clock(bool fake, unsigned int failure, unsigned int backwards,
                           long long advance)
{
    __atomic_store_n(&controller_clock_fake, fake, __ATOMIC_SEQ_CST);
    __atomic_store_n(&controller_clock_value, 5000, __ATOMIC_SEQ_CST);
    __atomic_store_n(&controller_enqueue_advance, advance, __ATOMIC_SEQ_CST);
    __atomic_store_n(&controller_clock_reads, 0, __ATOMIC_SEQ_CST);
    __atomic_store_n(&controller_clock_failure, failure, __ATOMIC_SEQ_CST);
    __atomic_store_n(&controller_clock_backwards, backwards, __ATOMIC_SEQ_CST);
}
unsigned int test_controller_clock_read_count(void)
{
    return __atomic_load_n(&controller_clock_reads, __ATOMIC_SEQ_CST);
}
'''

UI_STATUS_PRELUDE = r'''
#include "hiby_bluetooth.h"
#include "hiby_connectivity.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define HZ 100
#define CONTEXT_STD 0
#define ACTION_STD_CANCEL 10
#define ACTION_TREE_WPS 11
#define SYS_USB_CONNECTED 12
#define ACTION_NONE 0
#define ACTION_REDRAW 13
#define ACTION_STD_OK 14
#define HIBY_BT_UI_WAIT_STEPS 10
#define HIBY_BT_UI_SETTLE_STEPS 5
#define TIME_AFTER(after, before) ((long)(before) - (long)(after) < 0)
static long current_tick;

struct gui_synclist
{
    int selected_item;
};
static int gui_synclist_get_sel_pos(struct gui_synclist *lists)
{
    return lists->selected_item;
}
struct simplelist_info
{
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
    int selection;
    int (*action_callback)(int, struct gui_synclist *);
};

static struct hiby_bt_snapshot ui_snapshot;
static struct hiby_bt_snapshot ui_refreshed;
static int spoken[16];
static size_t spoken_count;
static unsigned int menu_visits;
static unsigned int refresh_requests;
static bool request_accepted;
static char spoken_name[HIBY_BT_NAME_SIZE];

static const char *str(int identifier)
{
    (void)identifier;
    return "label";
}

static int talk_id(int identifier, bool enqueue)
{
    (void)enqueue;
    assert(spoken_count < sizeof(spoken) / sizeof(spoken[0]));
    spoken[spoken_count++] = identifier;
    return 0;
}

static void splashf_silent(int ticks, const char *format, ...)
{
    (void)ticks;
    (void)format;
}

static void simplelist_info_init(struct simplelist_info *info, const char *title, ...)
{
    (void)title;
    memset(info, 0, sizeof(*info));
}

static bool simplelist_show_list(struct simplelist_info *info)
{
    info->selection = menu_visits++ ? -1 : 4;
    assert(menu_visits <= 2);
    return false;
}

static bool tts_is_available(void) { return true; }
static void tts_speak(const char *text, size_t length, bool enqueue)
{
    (void)enqueue;
    assert(length < sizeof(spoken_name));
    memcpy(spoken_name, text, length);
    spoken_name[length] = '\0';
}
static void talk_spell(const char *text, bool enqueue) { (void)text; (void)enqueue; }

bool hiby_bluetooth_init(void) { return true; }
void hiby_bluetooth_cancel(void) {}
void hiby_bluetooth_set_inhibited(bool inhibited) { (void)inhibited; }
bool hiby_connectivity_init(void) { return true; }
void hiby_connectivity_get_snapshot(struct hiby_connectivity_snapshot *snapshot)
{
    memset(snapshot, 0, sizeof(*snapshot));
}
bool hiby_connectivity_set_bluetooth_enabled(bool enabled) { (void)enabled; return false; }
void hiby_connectivity_cancel(void) {}
bool hiby_bluetooth_request(enum hiby_bt_operation operation, const char *address)
{
    (void)address;
    assert(operation == HIBY_BT_REFRESH);
    refresh_requests++;
    ui_snapshot = ui_refreshed;
    return request_accepted;
}
void hiby_bluetooth_get_snapshot(struct hiby_bt_snapshot *snapshot) { *snapshot = ui_snapshot; }
'''

UI_STATUS_MAIN = r'''
static unsigned int checked_cases;
static bool ui_power_known = true;

static void check_status(bool enabled, bool connected, enum hiby_bt_error error,
                         bool accepted, bool busy, int expected_label)
{
    memset(&ui_snapshot, 0, sizeof(ui_snapshot));
    memset(spoken, 0, sizeof(spoken));
    memset(spoken_name, 0, sizeof(spoken_name));
    ui_snapshot.enabled = enabled;
    ui_snapshot.available = true;
    ui_snapshot.power_known = ui_power_known;
    ui_snapshot.busy = busy;
    if (connected)
    {
        memcpy(ui_snapshot.connected_address, "AA:BB:CC:DD:EE:FF", 18);
        memcpy(ui_snapshot.connected_name, "Known headphones", 17);
    }
    ui_refreshed = ui_snapshot;
    ui_refreshed.error = error;
    request_accepted = accepted;
    spoken_count = 0;
    menu_visits = 0;
    refresh_requests = 0;
    assert(hiby_bluetooth_menu() == 0);
    assert(menu_visits == 2);
    assert(refresh_requests == (busy ? 0u : 2u));
    assert(spoken_count >= 1);
    assert(spoken[spoken_count - 1] == expected_label);
    for (size_t position = 0; position < spoken_count; position++)
    {
        if (error != HIBY_BT_OK || busy || !ui_power_known)
        {
            assert(spoken[position] != LANG_HIBY_BT_DISABLED);
            assert(spoken[position] != LANG_HIBY_BT_ENABLED);
            assert(spoken[position] != LANG_HIBY_BT_CONNECTED);
        }
    }
    if (error != HIBY_BT_OK || busy || !ui_power_known)
        assert(!spoken_name[0]);
    checked_cases++;
}

int main(void)
{
    for (unsigned int enabled = 0; enabled < 2; enabled++)
    {
        for (unsigned int connected = 0; connected < 2; connected++)
        {
            check_status(enabled != 0, connected != 0, HIBY_BT_COMMAND_FAILED,
                         true, false, LANG_HIBY_BT_COMMAND_FAILED);
            check_status(enabled != 0, connected != 0, HIBY_BT_TIMEOUT,
                         true, false, LANG_HIBY_BT_TIMEOUT);
            check_status(enabled != 0, connected != 0, HIBY_BT_CANCELLED,
                         true, false, LANG_HIBY_BT_CANCELLED);
        }
    }
    check_status(false, false, HIBY_BT_UNAVAILABLE, false, false, LANG_HIBY_BT_UNAVAILABLE);
    check_status(false, false, HIBY_BT_OK, true, true, LANG_HIBY_BT_WORKING);
    check_status(false, false, HIBY_BT_OK, true, false, LANG_HIBY_BT_DISABLED);
    check_status(true, false, HIBY_BT_OK, true, false, LANG_HIBY_BT_ENABLED);
    check_status(true, true, HIBY_BT_OK, true, false, LANG_HIBY_BT_CONNECTED);
    assert(!strcmp(spoken_name, "Known headphones"));
    ui_power_known = false;
    check_status(false, false, HIBY_BT_OK, true, false, LANG_HIBY_BT_POWER_UNKNOWN);
    check_status(true, true, HIBY_BT_OK, true, false, LANG_HIBY_BT_POWER_UNKNOWN);
    assert(checked_cases == 19);
    printf("verified-status-cases=%u\n", checked_cases);
    return 0;
}
'''


@unittest.skipUnless(os.name == "posix" and shutil.which("gcc"), "requires a POSIX host C compiler; Windows simulator is separately unavailable")
class BluetoothTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        central = project_materials_root(ROOT)
        evidence_root = confined_path(Path(os.environ.get("HIBY_RADIO_TEST_ROOT", central)), central, allow_root=True)
        cls.evidence = evidence_root / "hiby-bluetooth-tests" / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True)
        cls.binary_directory = cls.evidence / "commands"
        cls.binary_directory.mkdir()
        cls.configuration = cls.binary_directory / "mode"
        cls.command_log = cls.binary_directory / "commands"
        cls.commands = []
        cls.outcomes = []
        cls.measurements = {}
        cls.source_paths = (BACKEND, HEADER, CONTROLLER, CONTROLLER.with_suffix(".h"),
                            CONTROLLER.with_name("hiby_bluetooth_service.h"),
                            HEADER.with_name("pcm-hiby.h"), HEADER.with_name("power-control-hiby.h"),
                            Path(__file__).resolve())
        cls.source_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in cls.source_paths}
        helper = cls.evidence / "helper.c"
        helper.write_text(HELPER, encoding="utf-8")
        wrapper = cls.evidence / "wrapper.c"
        wrapper.write_text(WRAPPER.replace("BACKEND_PATH", BACKEND.as_posix()), encoding="utf-8")
        fake = cls.evidence / "fake.c"
        fake.write_text(FAKE, encoding="utf-8")
        clock_wrapper = cls.evidence / "controller-clock.c"
        clock_wrapper.write_text(CONTROLLER_CLOCK_WRAPPER.replace("CONTROLLER_PATH", CONTROLLER.as_posix()),
                                 encoding="utf-8")
        (cls.evidence / "config.h").write_text("", encoding="ascii")
        flags = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wshadow", "-Wconversion", "-O1", "-g", "-pthread"]

        def compile_command(arguments):
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
            cls.commands.append({"arguments": arguments, "returncode": result.returncode,
                                 "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                (cls.evidence / "build-failure.json").write_text(json.dumps(cls.commands, indent=2), encoding="utf-8")
                raise RuntimeError(result.stderr)

        cls.compile_command = staticmethod(compile_command)
        cls.flags = flags
        cls.includes = ["-I", str(HEADER.parent), "-I", str(ROOT / "apps"), "-I", str(cls.evidence)]

        compile_command(flags + ['-DTEST_DIRECTORY="' + cls.binary_directory.as_posix() + '"', str(helper), "-o", str(cls.binary_directory / "helper")])
        for command in ("bluetoothctl", "bluealsa-cli", "bt_resume"):
            os.link(cls.binary_directory / "helper", cls.binary_directory / command)
        includes = ["-I", str(HEADER.parent), "-I", str(ROOT / "apps"), "-I", str(cls.evidence)]
        compile_command(flags + includes + ["-shared", "-fPIC", '-DHIBY_BT_BIN_DIRECTORY="' + cls.binary_directory.as_posix() + '"',
                        "-DHIBY_BT_COMMAND_TIMEOUT_MS=250", "-DHIBY_BT_RESUME_TIMEOUT_MS=300", "-DHIBY_BT_SCAN_HOLD_MS=50", "-DHIBY_BT_ENDPOINT_TIMEOUT_MS=200",
                        str(wrapper), "-o", str(cls.evidence / "backend.so")])
        compile_command(flags + includes + ["-shared", "-fPIC", "-DHIBY_BT_HOST_TEST", "-DHIBY_BT_NO_UI", str(CONTROLLER), str(fake), "-o", str(cls.evidence / "controller.so")])
        compile_command(flags + includes + ["-shared", "-fPIC", "-DHIBY_BT_HOST_TEST", "-DHIBY_BT_NO_UI",
                        str(clock_wrapper), str(fake), "-o", str(cls.evidence / "controller-clock.so")])
        compile_command(flags + includes + ["-shared", "-fPIC", "-DHIBY_BT_HOST_TEST", "-DHIBY_BT_NO_UI",
                        '-DHIBY_BT_BIN_DIRECTORY="' + cls.binary_directory.as_posix() + '"',
                        "-DHIBY_BT_COMMAND_TIMEOUT_MS=250", "-DHIBY_BT_RESUME_TIMEOUT_MS=300", "-DHIBY_BT_SCAN_HOLD_MS=50", "-DHIBY_BT_ENDPOINT_TIMEOUT_MS=200",
                        str(CONTROLLER), str(wrapper), "-o", str(cls.evidence / "integrated.so")])
        compile_command(flags + includes + ["-shared", "-fPIC", "-DSIMULATOR", "-DHIBY_BT_NO_UI", str(CONTROLLER), "-o", str(cls.evidence / "unavailable.so")])
        cls.library = ctypes.CDLL(str(cls.evidence / "backend.so"))
        cls.library.hiby_bt_valid_address.argtypes = [ctypes.c_char_p]
        cls.library.hiby_bt_valid_address.restype = ctypes.c_bool
        cls.library.hiby_bt_parse_devices.argtypes = [ctypes.c_char_p, ctypes.POINTER(Device), ctypes.c_size_t, ctypes.c_size_t, ctypes.c_bool]
        cls.library.hiby_bt_parse_devices.restype = ctypes.c_size_t
        cls.library.hiby_bt_backend_execute.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(Snapshot), CANCEL, ctypes.c_void_p]
        cls.library.test_command.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_char_p, ctypes.c_size_t, CANCEL, ctypes.c_void_p]
        cls.library.test_route_active.argtypes = [ctypes.c_bool]
        cls.library.test_rfkill_state.argtypes = [ctypes.c_int, ctypes.c_bool]
        cls.library.test_rfkill_resume_unblocks.argtypes = [ctypes.c_bool]
        cls.library.test_route_failure.argtypes = [ctypes.c_int]
        cls.library.test_hold_children.argtypes = [ctypes.c_int]
        cls.library.test_fail_allocation.argtypes = [ctypes.c_bool]
        cls.library.test_read_interruptions.argtypes = [ctypes.c_uint]
        cls.library.test_read_interruptions_seen.restype = ctypes.c_uint
        cls.library.test_endpoint_clock_failure.argtypes = [ctypes.c_bool]
        cls.library.test_endpoint_clock_failures.restype = ctypes.c_uint
        cls.library.hiby_bt_backend_cleanup_pending.argtypes = [ctypes.c_char_p]
        cls.library.hiby_bt_backend_cleanup_pending.restype = ctypes.c_bool
        cls.controller = ctypes.CDLL(str(cls.evidence / "controller.so"))
        cls.clock_controller = ctypes.CDLL(str(cls.evidence / "controller-clock.so"))
        cls.integrated = ctypes.CDLL(str(cls.evidence / "integrated.so"))
        cls.controller.test_hold_backend.argtypes = [ctypes.c_bool]
        cls.controller.test_ignore_cancellation.argtypes = [ctypes.c_bool]
        cls.clock_controller.test_hold_backend.argtypes = [ctypes.c_bool]
        cls.clock_controller.test_ignore_cancellation.argtypes = [ctypes.c_bool]
        cls.clock_controller.test_controller_clock.argtypes = [ctypes.c_bool, ctypes.c_uint,
                                                              ctypes.c_uint, ctypes.c_longlong]
        cls.clock_controller.test_controller_clock_read_count.restype = ctypes.c_uint
        cls.simulator = ctypes.CDLL(str(cls.evidence / "unavailable.so"))
        for library in (cls.controller, cls.simulator, cls.integrated, cls.clock_controller):
            library.hiby_bluetooth_init.restype = ctypes.c_bool
            library.hiby_bluetooth_request.argtypes = [ctypes.c_int, ctypes.c_char_p]
            library.hiby_bluetooth_request.restype = ctypes.c_bool
            library.hiby_bluetooth_request_automatic.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            library.hiby_bluetooth_request_automatic.restype = ctypes.c_bool
            library.hiby_bluetooth_cancel_automatic.restype = ctypes.c_bool
            library.hiby_bluetooth_get_snapshot.argtypes = [ctypes.POINTER(Snapshot)]
            library.hiby_bluetooth_set_inhibited.argtypes = [ctypes.c_bool]
            library.hiby_bluetooth_is_inhibited.restype = ctypes.c_bool
        cls.cancel_never = CANCEL(lambda context: False)

    @classmethod
    def tearDownClass(cls):
        cls.controller.hiby_bluetooth_shutdown()
        cls.integrated.hiby_bluetooth_shutdown()
        cls.clock_controller.hiby_bluetooth_shutdown()
        source_after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in cls.source_paths}
        report = {"hardware_tested": False, "helper_commands_only": True,
                  "source_sha256": cls.source_hashes, "source_sha256_after": source_after,
                  "source_unchanged": cls.source_hashes == source_after,
                  "builds": cls.commands, "cases": cls.outcomes,
                  "measurements": cls.measurements,
                  "passed": cls.source_hashes == source_after and all(case["passed"] for case in cls.outcomes)}
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Bluetooth evidence:", cls.evidence)

    def setUp(self):
        self.configuration.write_text("good\n", encoding="ascii")
        self.command_log.write_text("", encoding="ascii")
        for filename in ("paired", "powered-off", "disconnected", "removed-other", "resumed", "resume-started",
                         "live-peers", "live-peers.tmp", "endpoint-missing", "connect-observed",
                         "post-info-failed", "endpoint-probes"):
            marker = self.binary_directory / filename
            if marker.exists():
                marker.unlink()
        self.library.test_route_failure(0)
        self.library.test_route_active(False)
        self.library.test_rfkill_state(errno.ENODEV, False)
        self.library.test_rfkill_resume_unblocks(False)
        self.library.test_hold_children(0)
        self.library.test_fail_allocation(False)
        self.library.test_read_interruptions(0)
        self.library.test_endpoint_clock_failure(False)
        self.library.test_clear_cleanup_pending()
        self.integrated.test_clear_cleanup_pending()
        self.integrated.hiby_bluetooth_shutdown()
        self.controller.test_hold_backend(False)
        self.controller.hiby_bluetooth_shutdown()
        self.controller.test_ignore_cancellation(False)
        self.integrated.hiby_bluetooth_shutdown()
        self.state = Snapshot()
        self.clock_controller.test_hold_backend(False)
        self.clock_controller.hiby_bluetooth_shutdown()
        self.clock_controller.test_ignore_cancellation(False)
        self.clock_controller.test_controller_clock(False, 0, 0, 0)
        for library in (self.controller, self.integrated, self.simulator, self.clock_controller):
            library.hiby_bluetooth_set_inhibited(False)

    def tearDown(self):
        self.clock_controller.test_hold_backend(False)
        self.clock_controller.hiby_bluetooth_shutdown()
        self.controller.hiby_bluetooth_shutdown()
        result = self._outcome.result
        failed = any(test.id() == self.id() or getattr(test, "test_case", None) is self
                     for test, details in result.failures + result.errors)
        self.outcomes.append({"test": self.id(), "passed": not failed})

    def mode(self, value):
        self.configuration.write_text(value + "\n", encoding="ascii")

    def assert_backend_resources_released(self, descriptors):
        self.assertEqual(self.library.test_allocations(), 0)
        self.assertEqual(self.library.test_child_slots_used(), 0)
        self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), descriptors)
        with self.assertRaises(ChildProcessError):
            os.waitpid(-1, os.WNOHANG)

    def execute(self, operation, address=None, cancel=None):
        return self.library.hiby_bt_backend_execute(operation, address, ctypes.byref(self.state), cancel or self.cancel_never, None)

    def run_command(self, command, *, input_text=None, hold=0, timeout=250, capacity=16384, cancel=None, path=None):
        output = ctypes.create_string_buffer(capacity)
        result = self.library.test_command(os.fsencode(path or self.binary_directory / "helper"), command,
                    input_text, hold, timeout, output, capacity, cancel or self.cancel_never, None)
        return result, output.value

    def snapshot(self, library=None):
        value = Snapshot()
        (library or self.controller).hiby_bluetooth_get_snapshot(ctypes.byref(value))
        return value

    def wait_idle(self, timeout=1, library=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.snapshot(library)
            if not state.busy:
                return state
            time.sleep(0.001)
        self.fail("controller did not become idle")

    def test_addresses(self):
        for address in (ADDRESS, b"aa:bb:00:99:cc:dd", OTHER):
            self.assertTrue(self.library.hiby_bt_valid_address(address))
        for address in (None, b"", b"AA:BB:GG:HH:II:JJ", b"AA:BB:CC:DD:EE:F", ADDRESS + b";x", b"AA-BB-CC-DD-EE-FF", b"AA:BB:CC:DD:EE:\xffF"):
            self.assertFalse(self.library.hiby_bt_valid_address(address))

    def test_parser_unique_paired_unicode_and_escape(self):
        devices = (Device * 32)()
        text = "Device aa:bb:cc:dd:ee:ff \x1b[32mSłuchawki\x1b[0m\nDevice AA:BB:CC:DD:EE:FF Słuchawki\nDevice AA:BB:GG:HH:II:JJ bad\n".encode()
        count = self.library.hiby_bt_parse_devices(text, devices, 0, 32, True)
        self.assertEqual(count, 1)
        self.assertEqual(devices[0].address, ADDRESS)
        self.assertEqual(devices[0].name.decode(), "Słuchawki")
        self.assertTrue(devices[0].paired)
        count = self.library.hiby_bt_parse_devices(b"Device AA:BB:CC:DD:EE:FF updated\n", devices, count, 32, False)
        self.assertEqual(count, 1)
        self.assertTrue(devices[0].paired)

    def test_parser_long_utf8_and_limit(self):
        devices = (Device * 32)()
        text = ("Device AA:BB:CC:DD:EE:FF " + "ą" * 500 + "\n").encode()
        self.assertEqual(self.library.hiby_bt_parse_devices(text, devices, 0, 32, False), 1)
        self.assertEqual(devices[0].name.decode(), "ą" * 63)
        text = b"\n".join(f"Device 00:00:00:00:00:{number:02X} name".encode() for number in range(64))
        self.assertEqual(self.library.hiby_bt_parse_devices(text, devices, 0, 32, False), 32)
        self.assertEqual(self.library.hiby_bt_parse_devices(text, devices, 0, 0, False), 0)

    def test_command_fast_final_output_and_nonzero(self):
        for iteration in range(20):
            self.assertEqual(self.run_command(b"fast-output"), (OK, b"Powered: yes\nfinal line\n"), iteration)
        self.assertEqual(self.run_command(b"exit-failed")[0], FAILED)

    def test_command_output_interrupt_storm_has_a_finite_retry_budget(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.library.test_read_interruptions(64)
        try:
            result, output = self.run_command(b"fast-output")
            interruptions = self.library.test_read_interruptions_seen()
            self.measurements["output_interrupt_storm"] = {
                "injected_interruptions": 64, "observed_interruptions": interruptions,
                "result": result, "output": output.decode("utf-8", errors="replace"),
                "hardware_energy_measured": False,
            }
        finally:
            self.library.test_read_interruptions(0)
        self.assert_backend_resources_released(descriptors)
        self.assertEqual(result, FAILED)
        self.assertLessEqual(interruptions, 8)

    def test_command_transient_output_interruptions_preserve_final_output(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.library.test_read_interruptions(3)
        try:
            self.assertEqual(self.run_command(b"fast-output"), (OK, b"Powered: yes\nfinal line\n"))
            self.assertEqual(self.library.test_read_interruptions_seen(), 3)
        finally:
            self.library.test_read_interruptions(0)
        self.assert_backend_resources_released(descriptors)

    def test_command_unavailable_timeout_cancel_pin_flood(self):
        self.assertEqual(self.run_command(b"ignored", path=self.evidence / "absent")[0], UNAVAILABLE)
        started = time.monotonic()
        self.assertEqual(self.run_command(b"sleep", timeout=80)[0], TIMEOUT)
        self.assertLess(time.monotonic() - started, 0.5)
        started = time.monotonic()
        cancel = CANCEL(lambda context: time.monotonic() - started > 0.05)
        self.assertEqual(self.run_command(b"sleep", timeout=1000, cancel=cancel)[0], CANCELLED)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(self.run_command(b"pin")[0], PIN)
        self.assertEqual(self.run_command(b"flood")[0], FAILED)

    def test_command_pipe_closed_and_fd_lifetime(self):
        before = len(list(Path("/proc/self/fd").iterdir()))
        self.assertEqual(self.run_command(b"closed-input", input_text=b"scan on\n", hold=40)[0], FAILED)
        for iteration in range(20):
            self.assertEqual(self.run_command(b"exit-failed")[0], FAILED, iteration)
        self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)
        with self.assertRaises(ChildProcessError):
            os.waitpid(-1, os.WNOHANG)

    def test_command_closed_output_does_not_spin_until_timeout(self):
        started = time.monotonic()
        cpu_started = time.process_time()
        self.assertEqual(self.run_command(b"closed-output", timeout=200)[0], TIMEOUT)
        cpu_used = time.process_time() - cpu_started
        elapsed = time.monotonic() - started
        self.measurements["closed_output_wait"] = {"cpu_seconds": cpu_used, "wall_seconds": elapsed}
        self.assertLess(cpu_used, elapsed * 0.5)

    def test_command_cancellation_kills_child_group(self):
        started = time.monotonic()
        cancel = CANCEL(lambda context: time.monotonic() - started > 0.06)
        result, output = self.run_command(b"sleep-child", timeout=1000, cancel=cancel)
        self.assertEqual(result, CANCELLED)
        child = int(output.split(b"child=")[1].splitlines()[0])
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            status = Path(f"/proc/{child}/stat")
            if not status.exists() or status.read_text().split()[2] == "Z":
                break
            time.sleep(0.01)
        else:
            self.fail("cancelled CLI child remained running")

    def test_failed_command_kills_descendants_after_leader_exits(self):
        result, output = self.run_command(b"failed-child", timeout=1000)
        self.assertEqual(result, FAILED)
        child = int(output.split(b"child=")[1].splitlines()[0])
        try:
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                status = Path(f"/proc/{child}/stat")
                if not status.exists() or status.read_text().split()[2] == "Z":
                    break
                time.sleep(0.01)
            else:
                self.fail("failed CLI left its descendant running")
        finally:
            try:
                os.kill(child, 9)
            except ProcessLookupError:
                pass

    def test_delayed_child_reaping_never_blocks_shutdown_forever(self):
        self.library.test_hold_children(1)
        try:
            for attempt in range(8):
                started = time.monotonic()
                result, output = self.run_command(b"sleep", timeout=20)
                self.assertEqual(result, TIMEOUT, attempt)
                self.assertLess(time.monotonic() - started, 0.6)
            started = time.monotonic()
            self.assertEqual(self.run_command(b"fast-output")[0], FAILED)
            self.assertLess(time.monotonic() - started, 0.2)
        finally:
            self.library.test_hold_children(0)
            self.run_command(b"fast-output")
        self.assertEqual(self.run_command(b"fast-output")[0], OK)
        with self.assertRaises(ChildProcessError):
            os.waitpid(-1, os.WNOHANG)

    def test_enable_scan_and_disable(self):
        self.assertEqual(self.execute(ENABLE), OK)
        self.assertTrue(self.state.available)
        self.assertTrue(self.state.enabled)
        self.assertEqual(self.state.count, 2)
        self.assertEqual(self.execute(SCAN), OK)
        self.assertEqual(self.execute(DISABLE), OK)
        self.assertFalse(self.state.enabled)
        self.assertIn("|power|off", self.command_log.read_text())

    def test_enable_power_not_confirmed(self):
        self.mode("power-false")
        self.assertEqual(self.execute(ENABLE), FAILED)
        self.assertFalse(self.state.enabled)

    def test_suspended_controller_refresh_does_not_require_bluez(self):
        self.mode("hang")
        self.library.test_rfkill_state(0, True)
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertTrue(self.state.available)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertEqual(self.state.count, 0)
        self.assertEqual(self.command_log.read_text(), "")

    def test_suspended_controller_disable_restores_wired_without_cli(self):
        self.mode("hang")
        self.library.test_rfkill_state(0, True)
        self.state.enabled = True
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.assertEqual(self.execute(DISABLE), OK)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.command_log.read_text(), "")

    def test_suspended_controller_does_not_fake_successful_enable(self):
        self.library.test_rfkill_state(0, True)
        self.assertEqual(self.execute(ENABLE), FAILED)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertIn("|power|on", self.command_log.read_text())

    def test_suspended_enable_resumes_before_power_without_failed_attempt(self):
        self.mode("resume-needed")
        self.library.test_rfkill_state(0, True)
        self.library.test_rfkill_resume_unblocks(True)
        started = time.monotonic()
        self.assertEqual(self.execute(ENABLE), OK)
        elapsed = time.monotonic() - started
        commands = self.command_log.read_text().splitlines()
        self.assertEqual(len(commands), 5)
        self.assertTrue(commands[0].endswith("/bt_resume"), commands)
        self.assertTrue(commands[1].endswith("|power|on"), commands)
        self.assertEqual([line.split("|")[-1] for line in commands[2:]],
                         ["show", "paired-devices", "devices"])
        self.assertTrue(self.state.power_known and self.state.enabled)
        self.measurements["suspended_enable"] = {
            "wall_seconds": elapsed, "commands": commands,
            "scope": "Controlled helpers, not real R1 radio startup timing"}

    def test_suspended_resume_failures_remain_bounded_and_not_enabled(self):
        for mode, expected in (("resume-failed", FAILED), ("resume-hang", TIMEOUT)):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                self.library.test_rfkill_state(0, True)
                descriptors = len(list(Path("/proc/self/fd").iterdir()))
                self.assertEqual(self.execute(ENABLE), expected)
                self.assertTrue(self.state.power_known)
                self.assertFalse(self.state.enabled)
                commands = self.command_log.read_text().splitlines()
                self.assertEqual(len(commands), 1)
                self.assertTrue(commands[0].endswith("/bt_resume"), commands)
                self.assert_backend_resources_released(descriptors)

    def test_suspended_resume_cancel_never_powers_on_or_claims_state(self):
        self.mode("resume-hang")
        self.library.test_rfkill_state(0, True)
        cancel = CANCEL(lambda context: "/bt_resume\n" in self.command_log.read_text())
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.assertEqual(self.execute(ENABLE, cancel=cancel), CANCELLED)
        self.assertFalse(self.state.power_known)
        self.assertNotIn("|power|on", self.command_log.read_text())
        self.assert_backend_resources_released(descriptors)

    def test_unknown_rfkill_does_not_fake_off(self):
        for error in (errno.ENODEV, errno.EACCES, errno.EPROTO, errno.EIO):
            with self.subTest(error=error):
                self.mode("hang")
                self.library.test_rfkill_state(error, True)
                self.state.enabled = True
                self.assertEqual(self.execute(REFRESH), TIMEOUT)
                self.assertFalse(self.state.power_known)
                self.assertTrue(self.state.enabled)

    def test_unblocked_controller_keeps_bluez_pairing_refresh(self):
        self.library.test_rfkill_state(0, False)
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertTrue(self.state.power_known)
        self.assertTrue(self.state.enabled)
        self.assertGreater(self.state.count, 0)
        self.assertIn("|paired-devices", self.command_log.read_text())

    def test_suspended_controller_preserves_audio_failure(self):
        self.library.test_rfkill_state(0, True)
        self.library.test_route_failure(errno.EIO)
        self.assertEqual(self.execute(DISABLE), AUDIO_FAILED)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertEqual(self.command_log.read_text(), "")

    def test_suspended_controller_preserves_early_cancellation(self):
        self.library.test_rfkill_state(0, True)
        self.assertEqual(self.execute(REFRESH, cancel=CANCEL(lambda context: True)), CANCELLED)
        self.assertFalse(self.state.power_known)
        self.assertEqual(self.command_log.read_text(), "")

    def test_suspended_controller_missing_readback_negative_control(self):
        modified, substitutions = re.subn(
            r"static bool controller_suspended\(void\)\n\{.*?\n\}",
            "static bool controller_suspended(void)\n{\n    return false;\n}",
            BACKEND.read_text(encoding="utf-8"), count=1, flags=re.DOTALL)
        self.assertEqual(substitutions, 1)
        source = self.evidence / "without-suspended-readback.c"
        source.write_text(modified, encoding="utf-8")
        wrapper = self.evidence / "without-suspended-readback-wrapper.c"
        wrapper.write_text(WRAPPER.replace("BACKEND_PATH", source.as_posix()), encoding="utf-8")
        library_path = self.evidence / "without-suspended-readback.so"
        self.compile_command(self.flags + self.includes + ["-shared", "-fPIC",
            '-DHIBY_BT_BIN_DIRECTORY="' + self.binary_directory.as_posix() + '"',
            "-DHIBY_BT_COMMAND_TIMEOUT_MS=250", str(wrapper), "-o", str(library_path)])
        library = ctypes.CDLL(str(library_path))
        library.test_rfkill_state.argtypes = [ctypes.c_int, ctypes.c_bool]
        library.hiby_bt_backend_execute.argtypes = [ctypes.c_int, ctypes.c_char_p,
                                                   ctypes.POINTER(Snapshot), CANCEL, ctypes.c_void_p]
        library.test_rfkill_state(0, True)
        self.mode("hang")
        state = Snapshot()
        self.assertEqual(library.hiby_bt_backend_execute(REFRESH, None, ctypes.byref(state),
                                                       self.cancel_never, None), TIMEOUT)
        self.assertFalse(state.power_known)
        self.assertIn("|show", self.command_log.read_text())

    def test_disable_attempts_poweroff_after_wired_route_failure(self):
        for route_error, expected in ((errno.EIO, AUDIO_FAILED), (errno.ETIMEDOUT, TIMEOUT),
                                      (errno.EBUSY, BUSY)):
            with self.subTest(route_error=route_error):
                self.state.enabled = True
                self.state.connected_address = ADDRESS
                self.library.test_route_active(True)
                self.library.test_route_failure(-route_error)
                self.command_log.write_text("", encoding="ascii")
                self.assertEqual(self.execute(DISABLE), expected)
                self.assertIn("|power|off", self.command_log.read_text())
                self.assertTrue(self.state.power_known)
                self.assertFalse(self.state.enabled)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                self.assertEqual(self.state.connected_address, b"")

    def test_scan_and_connect_off_require_explicit_enable(self):
        for operation, address in ((SCAN, None), (CONNECT, ADDRESS)):
            with self.subTest(operation=operation):
                self.mode("power-false")
                self.command_log.write_text("", encoding="ascii")
                self.state.enabled = True
                self.assertEqual(self.execute(operation, address), POWERED_OFF)
                self.assertTrue(self.state.power_known)
                self.assertFalse(self.state.enabled)
                self.assertTrue(self.command_log.read_text().endswith("|show\n"))
                self.assertNotIn("|power|", self.command_log.read_text())
                self.assertNotIn("/bt_resume", self.command_log.read_text())

    def test_successful_refresh_marks_power_as_observed(self):
        self.assertFalse(self.state.power_known)
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertTrue(self.state.power_known)
        self.assertTrue(self.state.enabled)
        self.assertNotIn("|power|", self.command_log.read_text())
        self.assertNotIn("/bt_resume", self.command_log.read_text())

    def test_startup_off_requires_actual_disable_readback(self):
        self.assertTrue(self.integrated.hiby_bluetooth_init())
        initial = self.snapshot(self.integrated)
        self.assertFalse(initial.enabled)
        self.assertFalse(initial.power_known)
        self.assertEqual(self.command_log.read_text(), "")
        self.assertTrue(self.integrated.hiby_bluetooth_request(DISABLE, None))
        published = self.wait_idle(timeout=3, library=self.integrated)
        self.assertEqual(published.error, OK)
        self.assertTrue(published.power_known)
        self.assertFalse(published.enabled)
        self.assertIn("|power|off\n", self.command_log.read_text())
        self.assertIn("|show\n", self.command_log.read_text())
        self.assertNotIn("/bt_resume", self.command_log.read_text())

    def test_passive_refresh_lists_paired_devices_while_powered_off(self):
        self.mode("power-false")
        self.state.enabled = True
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertEqual(self.state.count, 2)
        self.assertTrue(self.state.devices[0].paired)
        self.assertEqual([line.split("|")[-1] for line in self.command_log.read_text().splitlines()],
                         ["show", "paired-devices", "devices"])

    def test_passive_refresh_failures_never_resume_or_enable(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        for mode, expected, known in (("show-failed", FAILED, False), ("show-incomplete", FAILED, False),
                                      ("show-ambiguous", FAILED, False), ("show-hang", TIMEOUT, False),
                                      ("paired-list-failed", FAILED, True), ("device-list-failed", FAILED, True)):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                self.state = Snapshot()
                self.state.power_known = True
                self.assertEqual(self.execute(REFRESH), expected)
                self.assertEqual(self.state.power_known, known)
                self.assertEqual(self.state.enabled, known)
                self.assertNotIn("|power|", self.command_log.read_text())
                self.assertNotIn("/bt_resume", self.command_log.read_text())
                self.assert_backend_resources_released(descriptors)

    def test_off_scan_and_connect_do_not_require_audio_endpoint(self):
        helper = self.binary_directory / "bluealsa-cli"
        parked = helper.with_name("bluealsa-cli-unavailable")
        helper.rename(parked)
        try:
            for operation, address in ((SCAN, None), (CONNECT, ADDRESS)):
                with self.subTest(operation=operation):
                    self.mode("power-false")
                    self.assertEqual(self.execute(operation, address), POWERED_OFF)
                    self.assertTrue(self.state.power_known)
                    self.assertFalse(self.state.enabled)
        finally:
            parked.rename(helper)
        self.assertNotIn("|power|", self.command_log.read_text())
        self.assertNotIn("/bt_resume", self.command_log.read_text())

    def test_scan_and_connect_read_actual_power_instead_of_stale_cache(self):
        for operation, address in ((SCAN, None), (CONNECT, ADDRESS)):
            with self.subTest(operation=operation):
                self.state = Snapshot()
                self.state.power_known = True
                self.assertEqual(self.execute(operation, address), OK)
                self.assertTrue(self.state.power_known)
                self.assertTrue(self.state.enabled)
        self.assertNotIn("|power|", self.command_log.read_text())
        self.assertNotIn("/bt_resume", self.command_log.read_text())

    def test_unknown_power_blocks_scan_and_connect_without_side_effects(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        for operation, address in ((SCAN, None), (CONNECT, ADDRESS)):
            for mode, expected in (("show-failed", FAILED), ("show-incomplete", FAILED),
                                   ("show-ambiguous", FAILED), ("show-hang", TIMEOUT)):
                with self.subTest(operation=operation, mode=mode):
                    self.mode(mode)
                    self.command_log.write_text("", encoding="ascii")
                    self.state = Snapshot()
                    self.state.power_known = True
                    self.state.connected_address = OTHER
                    self.library.test_route_active(True)
                    self.assertEqual(self.execute(operation, address), expected)
                    self.assertFalse(self.state.power_known)
                    self.assertFalse(self.state.enabled)
                    self.assertEqual(self.state.connected_address, OTHER)
                    self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                    self.assertEqual(len(self.command_log.read_text().splitlines()), 1)
                    self.assertTrue(self.command_log.read_text().endswith("|show\n"))
                    self.assert_backend_resources_released(descriptors)

    def test_cancelled_power_read_blocks_scan_and_connect(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        for operation, address in ((SCAN, None), (CONNECT, ADDRESS), (REFRESH, None)):
            with self.subTest(operation=operation):
                self.command_log.write_text("", encoding="ascii")
                self.state.power_known = True
                cancel = CANCEL(lambda context: "|show\n" in self.command_log.read_text())
                self.assertEqual(self.execute(operation, address, cancel), CANCELLED)
                self.assertFalse(self.state.power_known)
                self.assertEqual(len(self.command_log.read_text().splitlines()), 1)
                self.assertTrue(self.command_log.read_text().endswith("|show\n"))
                self.assert_backend_resources_released(descriptors)

    def test_invalid_and_early_cancel_invalidate_power_knowledge(self):
        for enabled in (False, True):
            for operation, address, expected, cancel in (
                    (-1, None, FAILED, None), (VERIFY_LINK + 1, None, FAILED, None),
                    (CONNECT, b"bad", INVALID, None), (REMOVE, b"bad", INVALID, None),
                    (ENABLE, None, CANCELLED, CANCEL(lambda context: True)),
                    (DISABLE, None, CANCELLED, CANCEL(lambda context: True))):
                with self.subTest(enabled=enabled, operation=operation):
                    self.state.enabled = enabled
                    self.state.power_known = True
                    self.assertEqual(self.execute(operation, address, cancel), expected)
                    self.assertFalse(self.state.power_known)
                    self.assertEqual(self.state.enabled, enabled)
        self.assertEqual(self.command_log.read_text(), "")

    def test_disable_failures_publish_actual_or_unknown_power(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        cases = (("power-off-command-failed", FAILED, True, True),
                 ("power-off-applied-error", FAILED, True, False),
                 ("power-off-hang", TIMEOUT, True, True),
                 ("off-show-failed", FAILED, False, False),
                 ("off-show-incomplete", FAILED, False, False),
                 ("show-ambiguous", FAILED, False, False),
                 ("show-hang", TIMEOUT, False, False))
        for mode, expected, known, enabled in cases:
            with self.subTest(mode=mode):
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                (self.binary_directory / "powered-off").unlink(missing_ok=True)
                self.state = Snapshot()
                self.state.power_known = True
                self.assertEqual(self.execute(DISABLE), expected)
                self.assertEqual(self.state.power_known, known)
                self.assertEqual(self.state.enabled, enabled)
                self.assertIn("|power|off\n", self.command_log.read_text())
                self.assertIn("|show\n", self.command_log.read_text())
                self.assertNotIn("/bt_resume", self.command_log.read_text())
                self.assert_backend_resources_released(descriptors)

    def test_disable_power_failure_takes_precedence_over_audio_failure(self):
        self.mode("power-off-command-failed")
        self.library.test_route_failure(-errno.EIO)
        self.assertEqual(self.execute(DISABLE), FAILED)
        self.assertTrue(self.state.power_known)
        self.assertTrue(self.state.enabled)
        self.assertIn("|power|off\n", self.command_log.read_text())

    def test_disable_still_powers_off_after_disconnect_timeout(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.mode("disconnect-hang")
        self.state.enabled = True
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.assertEqual(self.execute(DISABLE), OK)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertEqual(self.state.connected_address, b"")
        self.assertFalse(self.library.pcm_alsa_bluetooth_active())
        self.assertIn("|power|off\n", self.command_log.read_text())
        self.assert_backend_resources_released(descriptors)

    def test_disable_route_cancellation_stops_without_confirming_off(self):
        self.library.test_route_failure(-errno.ECANCELED)
        self.state.power_known = True
        self.assertEqual(self.execute(DISABLE), CANCELLED)
        self.assertFalse(self.state.power_known)
        self.assertEqual(self.command_log.read_text(), "")

    def test_disable_cancel_after_poweroff_requires_new_readback(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.state.enabled = True
        self.state.power_known = True
        cancel = CANCEL(lambda context: (self.binary_directory / "powered-off").exists())
        self.assertEqual(self.execute(DISABLE, cancel=cancel), CANCELLED)
        self.assertFalse(self.state.power_known)
        self.assertTrue(self.state.enabled)
        self.assertIn("|power|off\n", self.command_log.read_text())
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assert_backend_resources_released(descriptors)

    def test_failed_enable_still_reads_actual_power(self):
        for mode, enabled in (("enable-fails-on", True), ("enable-fails-off", False)):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.state.enabled = not enabled
                self.assertEqual(self.execute(ENABLE), FAILED)
                self.assertTrue(self.state.power_known)
                self.assertEqual(self.state.enabled, enabled)
                self.assertIn("|show\n", self.command_log.read_text())

    def test_worker_publishes_failed_and_successful_disable_state(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.assertTrue(self.integrated.hiby_bluetooth_init())
        self.integrated.test_route_failure(-errno.EIO)
        try:
            self.assertTrue(self.integrated.hiby_bluetooth_request(DISABLE, None))
            published = self.wait_idle(timeout=3, library=self.integrated)
            self.assertEqual(published.error, AUDIO_FAILED)
            self.assertTrue(published.power_known)
            self.assertFalse(published.enabled)
        finally:
            self.integrated.test_route_failure(0)
        self.mode("power-off-command-failed")
        (self.binary_directory / "powered-off").unlink()
        self.assertTrue(self.integrated.hiby_bluetooth_request(DISABLE, None))
        published = self.wait_idle(timeout=3, library=self.integrated)
        self.assertEqual(published.error, FAILED)
        self.assertTrue(published.power_known)
        self.assertTrue(published.enabled)
        self.mode("good")
        self.assertTrue(self.integrated.hiby_bluetooth_request(DISABLE, None))
        published = self.wait_idle(timeout=3, library=self.integrated)
        self.assertEqual(published.error, OK)
        self.assertTrue(published.power_known)
        self.assertFalse(published.enabled)
        self.integrated.hiby_bluetooth_shutdown()
        self.assertEqual(self.integrated.test_allocations(), 0)
        self.assertEqual(self.integrated.test_child_slots_used(), 0)
        self.assert_backend_resources_released(descriptors)

    def test_enable_unknown_power_does_not_claim_radio_is_off(self):
        for mode in ("show-failed", "show-incomplete"):
            with self.subTest(mode=mode):
                self.state.enabled = True
                self.mode(mode)
                self.assertEqual(self.execute(ENABLE), FAILED)
                self.assertTrue(self.state.enabled)

    def test_disable_powers_off_even_if_disconnect_failed(self):
        for mode in ("disconnect-fails", "disconnect-false"):
            with self.subTest(mode=mode):
                self.configuration.write_text(mode + "\n", encoding="ascii")
                self.command_log.write_text("", encoding="ascii")
                self.state.enabled = True
                self.state.connected_address = ADDRESS
                self.state.connected_name = b"Headphones"
                self.library.test_route_active(True)
                self.assertEqual(self.execute(DISABLE), OK)
                self.assertIn("|power|off", self.command_log.read_text())
                self.assertFalse(self.state.enabled)
                self.assertFalse(self.library.pcm_alsa_bluetooth_active())
                self.assertEqual(self.state.connected_address, b"")
                self.assertEqual(self.state.connected_name, b"")

    def test_disable_does_not_claim_poweroff_when_both_commands_fail(self):
        self.state.enabled = True
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.mode("disconnect-and-power-fail")
        self.assertEqual(self.execute(DISABLE), FAILED)
        self.assertIn("|power|off", self.command_log.read_text())
        self.assertTrue(self.state.enabled)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertFalse(self.library.pcm_alsa_bluetooth_active())

    def test_disable_cancelled_disconnect_does_not_continue_to_poweroff(self):
        self.state.enabled = True
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        cancel = CANCEL(lambda context: "|disconnect|" in self.command_log.read_text())
        self.assertEqual(self.execute(DISABLE, cancel=cancel), CANCELLED)
        self.assertNotIn("|power|off", self.command_log.read_text())
        self.assertTrue(self.state.enabled)

    def test_backend_allocation_failure_does_not_leak_resources(self):
        before = len(list(Path("/proc/self/fd").iterdir()))
        self.library.test_fail_allocation(True)
        try:
            for operation in range(VERIFY_LINK + 1):
                with self.subTest(operation=operation):
                    self.assertEqual(self.execute(operation, ADDRESS), FAILED)
                    self.assertEqual(self.library.test_allocations(), 0)
        finally:
            self.library.test_fail_allocation(False)
        self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)
        self.assertEqual(self.execute(ENABLE), OK)
        self.assertEqual(self.library.test_allocations(), 0)

    def test_real_worker_repeated_lifecycle_and_resource_counts(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        threads = len(list(Path("/proc/self/task").iterdir()))
        operations = []
        self.measurements["repeated_lifecycle_operations"] = operations
        for cycle in range(12):
            with self.subTest(cycle=cycle):
                self.assertTrue(self.integrated.hiby_bluetooth_init())
                for operation, address in ((ENABLE, None), (SCAN, None), (CONNECT, ADDRESS),
                                           (DISCONNECT, None), (DISABLE, None)):
                    started = time.monotonic()
                    self.assertTrue(self.integrated.hiby_bluetooth_request(operation, address))
                    state = self.wait_idle(timeout=3, library=self.integrated)
                    operations.append({"cycle": cycle, "operation": operation, "result": state.error,
                                       "seconds": time.monotonic() - started,
                                       "command_tail": self.command_log.read_text().splitlines()[-3:]})
                    self.assertEqual(state.error, OK, operations[-1])
                    self.assertEqual(self.integrated.test_allocations(), 0)
                self.integrated.hiby_bluetooth_shutdown()
                self.assertFalse(self.snapshot(self.integrated).busy)
                self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), descriptors)
                self.assertEqual(len(list(Path("/proc/self/task").iterdir())), threads)
        with self.assertRaises(ChildProcessError):
            os.waitpid(-1, os.WNOHANG)
        self.measurements["real_lifecycle"] = {"cycles": 12, "operations": 60,
                                               "descriptors": descriptors, "threads": threads}

    def test_real_worker_cancel_shutdown_request_races(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        threads = len(list(Path("/proc/self/task").iterdir()))
        self.mode("hang")
        for cycle in range(12):
            with self.subTest(cycle=cycle):
                self.command_log.write_text("", encoding="ascii")
                self.assertTrue(self.integrated.hiby_bluetooth_init())
                self.assertTrue(self.integrated.hiby_bluetooth_request(SCAN, None))
                deadline = time.monotonic() + 1
                while not self.command_log.read_text() and time.monotonic() < deadline:
                    time.sleep(0.001)
                self.assertTrue(self.command_log.read_text())
                rejected = []
                contenders = [threading.Thread(target=lambda: rejected.append(
                    self.integrated.hiby_bluetooth_request(ENABLE, None))) for position in range(4)]
                for contender in contenders:
                    contender.start()
                for contender in contenders:
                    contender.join(1)
                self.assertEqual(rejected, [False] * 4)
                closers = [threading.Thread(target=self.integrated.hiby_bluetooth_shutdown) for position in range(3)]
                started = time.monotonic()
                for closer in closers:
                    closer.start()
                for closer in closers:
                    closer.join(1)
                self.assertTrue(all(not closer.is_alive() for closer in closers))
                self.assertLess(time.monotonic() - started, 0.75)
                self.assertFalse(self.snapshot(self.integrated).busy)
                self.assertEqual(self.integrated.test_allocations(), 0)
                self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), descriptors)
                self.assertEqual(len(list(Path("/proc/self/task").iterdir())), threads)
        with self.assertRaises(ChildProcessError):
            os.waitpid(-1, os.WNOHANG)
        self.measurements["real_cancel_shutdown"] = {"cycles": 12, "shutdown_callers_per_cycle": 3}

    def test_idle_worker_does_not_poll_or_spawn_commands(self):
        self.assertTrue(self.integrated.hiby_bluetooth_init())
        commands = self.command_log.read_bytes()
        cpu_started = time.process_time()
        started = time.monotonic()
        time.sleep(0.3)
        elapsed = time.monotonic() - started
        cpu_used = time.process_time() - cpu_started
        self.assertEqual(self.command_log.read_bytes(), commands)
        self.assertFalse(self.snapshot(self.integrated).busy)
        self.assertLess(cpu_used, elapsed * 0.2)
        self.measurements["idle_worker"] = {"cpu_seconds": cpu_used, "wall_seconds": elapsed,
                                             "commands_spawned": 0, "hardware_energy_measured": False}

    def test_scan_false_success_is_rejected(self):
        self.mode("scan-false")
        self.assertEqual(self.execute(SCAN), FAILED)
        self.assertEqual(self.state.count, 0)

    def test_unsupported_cli_command_is_not_an_empty_success(self):
        self.mode("unsupported-command")
        self.assertEqual(self.execute(ENABLE), FAILED)
        self.assertEqual(self.state.count, 0)

    def test_vendor_resume_fallback_and_missing_cli(self):
        self.mode("resume-needed")
        self.assertEqual(self.execute(ENABLE), OK)
        self.assertIn("/bt_resume\n", self.command_log.read_text())
        helper = self.binary_directory / "bluealsa-cli"
        parked = self.binary_directory / "bluealsa-cli-unavailable"
        helper.rename(parked)
        try:
            self.assertEqual(self.execute(ENABLE), UNAVAILABLE)
            self.assertFalse(self.state.available)
        finally:
            parked.rename(helper)

    def test_disconnect_disable_and_forget_require_confirmed_state(self):
        self.assertEqual(self.execute(ENABLE), OK)
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.mode("disconnect-false")
        self.assertEqual(self.execute(DISCONNECT), CONNECT_FAILED)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.state.connected_address = b""
        self.mode("power-off-false")
        self.assertEqual(self.execute(DISABLE), FAILED)
        self.assertTrue(self.state.enabled)
        self.mode("remove-false")
        self.assertEqual(self.execute(REMOVE, OTHER), FAILED)

    def test_connect_pair_and_route(self):
        self.assertEqual(self.execute(ENABLE), OK)
        self.mode("need-pair")
        self.assertEqual(self.execute(CONNECT, ADDRESS), OK)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertEqual(self.state.connected_name, b"Headphones")
        self.assertIn("|pair|AA:BB:CC:DD:EE:FF", self.command_log.read_text())
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.state.connected_address, b"")

    def test_refresh_list_errors_preserve_the_last_complete_device_list(self):
        self.assertEqual(self.execute(ENABLE), OK)
        previous_count = self.state.count
        previous_devices = bytes(self.state.devices)
        for mode in ("device-list-error", "paired-stdout-error", "device-list-malformed",
                     "paired-malformed", "devices-invalid-address", "device-list-failed"):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.assertEqual(self.execute(REFRESH), FAILED)
                self.assertEqual(self.state.count, previous_count)
                self.assertEqual(bytes(self.state.devices), previous_devices)

    def test_refresh_successful_empty_lists_clear_previous_devices(self):
        self.assertEqual(self.execute(ENABLE), OK)
        self.mode("empty-lists")
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertEqual(self.state.count, 0)

    def test_device_names_are_not_agent_prompts_or_command_errors(self):
        for name in ("Enter PIN headphones", "Enter passkey headphones", "Confirm passkey headphones",
                     "Request confirmation headphones", "Unknown command headphones",
                     "Invalid command headphones", "No default controller available",
                     "org.bluez.Error.Failed headphones", "not available"):
            with self.subTest(name=name):
                self.mode("name-" + name)
                self.assertEqual(self.execute(REFRESH), OK)
                self.assertEqual(self.state.count, 1)
                self.assertEqual(self.state.devices[0].name.decode(), name)
                self.assertTrue(self.state.devices[0].paired)

    def test_colored_agent_prompt_is_rejected_before_command_timeout(self):
        started = time.monotonic()
        result, output = self.run_command(b"pin-colored", timeout=700)
        self.measurements["colored_agent_prompt"] = {
            "result": result, "seconds": time.monotonic() - started,
            "output": output.decode("utf-8", errors="replace")}
        self.assertEqual(result, PIN)
        self.assertLess(time.monotonic() - started, 0.5)

    def test_connect_info_requires_matching_identity_and_unambiguous_pairing(self):
        self.set_live_peers()
        for mode in ("wrong-info-peer", "ambiguous-paired", "missing-paired"):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                self.assertEqual(self.execute(CONNECT, ADDRESS), FAILED)
                commands = self.command_log.read_text()
                for command in ("pair", "trust", "connect"):
                    self.assertNotIn("|" + command + "|", commands)
                self.assertEqual(self.live_peers(), set())
                self.assertFalse(self.library.pcm_alsa_bluetooth_active())

    def test_disconnect_mismatched_info_cannot_confirm_or_disconnect_the_target(self):
        self.set_live_peers(ADDRESS)
        self.state.connected_address = ADDRESS
        self.mode("wrong-info-peer")
        self.assertEqual(self.execute(DISCONNECT), FAILED)
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertNotIn("|disconnect|", self.command_log.read_text())

    def test_connect_applied_error_reconciles_only_the_new_owned_peer(self):
        self.set_live_peers(OTHER)
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        self.mode("connect-applied-error")
        self.assertEqual(self.execute(CONNECT, ADDRESS), FAILED)
        self.assertEqual(self.live_peers(), {OTHER.decode()})
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        commands = self.command_log.read_text()
        self.assertIn("|disconnect|" + ADDRESS.decode(), commands)
        self.assertNotIn("|disconnect|" + OTHER.decode(), commands)

    def test_connect_post_info_failure_reconciles_only_the_new_owned_peer(self):
        self.set_live_peers(OTHER)
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        self.mode("post-connect-info-once")
        self.assertEqual(self.execute(CONNECT, ADDRESS), FAILED)
        self.assertEqual(self.live_peers(), {OTHER.decode()})
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        commands = self.command_log.read_text()
        self.assertIn("|disconnect|" + ADDRESS.decode(), commands)
        self.assertNotIn("|disconnect|" + OTHER.decode(), commands)

    def test_failed_connect_never_rolls_back_a_verified_preexisting_peer(self):
        self.set_live_peers(ADDRESS, OTHER)
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        self.mode("connect-applied-error")
        self.assertEqual(self.execute(CONNECT, ADDRESS), FAILED)
        self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertNotIn("|disconnect|", self.command_log.read_text())

    def test_endpoint_deadline_rejects_slow_success_and_preserves_previous_route(self):
        self.set_live_peers(OTHER)
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        self.mode("endpoint-late")
        started = time.monotonic()
        result = self.execute(CONNECT, ADDRESS)
        self.measurements["slow_endpoint_deadline"] = {
            "result": result, "seconds": time.monotonic() - started, "endpoint_budget_ms": 200}
        self.assertNotEqual(result, OK)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(self.live_peers(), {OTHER.decode()})
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())

    def test_production_endpoint_deadline_rejects_late_success(self):
        self.set_live_peers()
        self.mode("endpoint-production-late")
        executable = self.evidence / "production-endpoint.so"
        self.compile_command(self.flags + self.includes + ["-shared", "-fPIC",
            '-DHIBY_BT_BIN_DIRECTORY="' + self.binary_directory.as_posix() + '"',
            "-DHIBY_BT_COMMAND_TIMEOUT_MS=250", str(self.evidence / "wrapper.c"), "-o", str(executable)])
        library = ctypes.CDLL(str(executable))
        library.hiby_bt_backend_execute.argtypes = [ctypes.c_int, ctypes.c_char_p,
            ctypes.POINTER(Snapshot), CANCEL, ctypes.c_void_p]
        started = time.monotonic()
        result = library.hiby_bt_backend_execute(CONNECT, ADDRESS, ctypes.byref(self.state),
                                                self.cancel_never, None)
        self.measurements["production_endpoint_deadline"] = {
            "result": result, "seconds": time.monotonic() - started, "endpoint_budget_ms": 6000,
            "commands": self.command_log.read_text().splitlines()}
        self.assertNotEqual(result, OK)
        self.assertLess(time.monotonic() - started, 8.0)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.live_peers(), set())
        self.assertEqual(library.test_allocations(), 0)
        self.assertEqual(library.test_child_slots_used(), 0)

    def test_unverified_owned_cleanup_retains_queryable_evidence_and_previous_route(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.set_live_peers(OTHER)
        self.state.connected_address = OTHER
        self.state.connected_name = b"Previous headphones"
        self.library.test_route_active(True)
        self.mode("post-connect-info-error")
        self.assertEqual(self.execute(CONNECT, ADDRESS), FAILED)
        pending = ctypes.create_string_buffer(18)
        self.assertTrue(self.library.hiby_bt_backend_cleanup_pending(pending))
        self.assertEqual(pending.value, ADDRESS)
        self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertEqual(self.state.connected_name, b"Previous headphones")
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        commands = self.command_log.read_text()
        self.assertNotIn("|disconnect|", commands)
        self.assertEqual(self.execute(CONNECT, OTHER), BUSY)
        self.assertEqual(self.command_log.read_text(), commands)
        self.assertTrue(self.library.hiby_bt_backend_cleanup_pending(pending))
        self.assertEqual(pending.value, ADDRESS)
        self.assert_backend_resources_released(descriptors)

    def test_owned_cleanup_evidence_clears_only_after_confirmed_resolution(self):
        for resolution in ("adopt", "poweroff"):
            with self.subTest(resolution=resolution):
                self.library.test_clear_cleanup_pending()
                (self.binary_directory / "connect-observed").unlink(missing_ok=True)
                (self.binary_directory / "post-info-failed").unlink(missing_ok=True)
                self.set_live_peers(OTHER)
                self.state.connected_address = OTHER
                self.library.test_route_active(True)
                self.mode("post-connect-info-error")
                self.assertEqual(self.execute(CONNECT, ADDRESS), FAILED)
                self.assertTrue(self.library.hiby_bt_backend_cleanup_pending(None))
                self.mode("good")
                if resolution == "adopt":
                    self.assertEqual(self.execute(CONNECT, ADDRESS), OK)
                    self.assertEqual(self.state.connected_address, ADDRESS)
                    self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
                else:
                    self.assertEqual(self.execute(DISABLE), OK)
                    self.assertTrue(self.state.power_known)
                    self.assertFalse(self.state.enabled)
                pending = ctypes.create_string_buffer(18)
                self.assertFalse(self.library.hiby_bt_backend_cleanup_pending(pending))
                self.assertEqual(pending.value, b"")

    def test_cancelled_connect_preserves_the_existing_cleanup_contract(self):
        self.set_live_peers()
        cancel = CANCEL(lambda context: "|list-pcms\n" in self.command_log.read_text())
        self.assertEqual(self.execute(CONNECT, ADDRESS, cancel), CANCELLED)
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.assertFalse(self.library.hiby_bt_backend_cleanup_pending(None))
        self.assertNotIn("|disconnect|", self.command_log.read_text())
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.live_peers(), set())

    def backend_commands(self):
        return [line.split("|")[1] for line in self.command_log.read_text().splitlines()]

    def test_auto_connect_paired_trusted_peer_uses_only_the_bounded_connection_chain(self):
        self.set_live_peers(OTHER)
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        self.assertEqual(self.execute(CONNECT_PAIRED, ADDRESS), OK)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
        self.assertEqual(self.backend_commands(), ["show", "info", "connect", "info", "list-pcms"])

    def test_auto_connect_preexisting_trusted_peer_does_not_reconnect_or_acquire_trust(self):
        self.set_live_peers(ADDRESS)
        self.assertEqual(self.execute(CONNECT_PAIRED, ADDRESS), OK)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertEqual(self.backend_commands(), ["show", "info", "info", "list-pcms"])

    def test_auto_connect_rejects_unknown_unpaired_and_untrusted_info_without_side_effects(self):
        self.set_live_peers(OTHER)
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        for mode in ("auto-unpaired", "auto-untrusted", "auto-trust-missing",
                     "auto-trust-ambiguous", "wrong-info-peer", "ambiguous-paired",
                     "missing-paired", "info-incomplete", "info-failed"):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                self.assertIn(self.execute(CONNECT_PAIRED, ADDRESS), (FAILED, CONNECT_FAILED))
                self.assertEqual(self.backend_commands(), ["show", "info"])
                self.assertEqual(self.live_peers(), {OTHER.decode()})
                self.assertEqual(self.state.connected_address, OTHER)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())

    def test_auto_connect_never_resumes_or_powers_on_for_off_unknown_or_cancelled_radio(self):
        self.set_live_peers()
        for mode, expected in (("power-false", POWERED_OFF), ("show-incomplete", FAILED),
                               ("show-ambiguous", FAILED), ("show-failed", FAILED),
                               ("show-hang", TIMEOUT)):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                self.assertEqual(self.execute(CONNECT_PAIRED, ADDRESS), expected)
                self.assertEqual(self.backend_commands(), ["show"])
                self.assertEqual(self.live_peers(), set())
        self.command_log.write_text("", encoding="ascii")
        self.assertEqual(self.execute(CONNECT_PAIRED, ADDRESS, CANCEL(lambda context: True)), CANCELLED)
        self.assertEqual(self.backend_commands(), [])

    def test_auto_connect_post_connect_trust_or_pairing_loss_cleans_only_the_owned_attempt(self):
        for mode in ("auto-trust-lost", "auto-paired-lost"):
            with self.subTest(mode=mode):
                (self.binary_directory / "connect-observed").unlink(missing_ok=True)
                self.set_live_peers(OTHER)
                self.state.connected_address = OTHER
                self.library.test_route_active(True)
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                self.assertEqual(self.execute(CONNECT_PAIRED, ADDRESS), CONNECT_FAILED)
                self.assertEqual(self.live_peers(), {OTHER.decode()})
                self.assertEqual(self.state.connected_address, OTHER)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                self.assertNotIn("|disconnect|" + OTHER.decode(), self.command_log.read_text())
                self.assertTrue(set(self.backend_commands()) <= {"show", "info", "connect", "disconnect"})

    def test_auto_connect_endpoint_cancellation_keeps_the_explicit_cancellation_contract(self):
        self.set_live_peers()
        self.mode("endpoint-late")
        started = time.monotonic()
        cancel = CANCEL(lambda context: time.monotonic() - started > 0.25)
        self.assertEqual(self.execute(CONNECT_PAIRED, ADDRESS, cancel), CANCELLED)
        self.assertLess(time.monotonic() - started, 0.8)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.assertFalse(self.library.hiby_bt_backend_cleanup_pending(None))
        self.assertNotIn("disconnect", self.backend_commands())
        self.assertTrue(set(self.backend_commands()) <= {"show", "info", "connect", "list-pcms"})

    def test_verify_link_healthy_peer_does_not_enumerate_or_change_output(self):
        self.set_live_peers(ADDRESS)
        self.state.connected_address = ADDRESS
        self.state.connected_name = b"Existing headphones"
        self.state.count = 3
        self.library.test_route_active(True)
        self.assertEqual(self.execute(VERIFY_LINK), OK)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertEqual(self.state.connected_name, b"Existing headphones")
        self.assertEqual(self.state.count, 3)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(self.backend_commands(), ["show", "info"])

    def test_verify_link_without_tracked_peer_never_adopts_an_incoming_connection(self):
        self.set_live_peers(ADDRESS)
        self.assertEqual(self.execute(VERIFY_LINK), OK)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.assertFalse(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(self.backend_commands(), ["show"])

    def test_verify_link_verified_loss_restores_wired_before_clearing_the_record(self):
        self.set_live_peers()
        self.state.connected_address = ADDRESS
        self.state.connected_name = b"Existing headphones"
        self.library.test_route_active(True)
        self.assertEqual(self.execute(VERIFY_LINK), CONNECT_FAILED)
        self.assertTrue(self.state.power_known)
        self.assertTrue(self.state.enabled)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.state.connected_name, b"")
        self.assertFalse(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(self.backend_commands(), ["show", "info"])

    def test_verify_link_confirmed_radio_off_returns_ok_without_peer_query(self):
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        (self.binary_directory / "powered-off").write_text("", encoding="ascii")
        self.assertEqual(self.execute(VERIFY_LINK), OK)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertEqual(self.state.connected_address, b"")
        self.assertFalse(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(self.backend_commands(), ["show"])

    def test_verify_link_suspended_radio_off_requires_no_bluez_executable(self):
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.library.test_rfkill_state(0, True)
        executable = self.binary_directory / "bluetoothctl"
        parked = self.binary_directory / "bluetoothctl-unavailable"
        executable.rename(parked)
        try:
            self.assertEqual(self.execute(VERIFY_LINK), OK)
        finally:
            parked.rename(executable)
        self.assertTrue(self.state.power_known)
        self.assertFalse(self.state.enabled)
        self.assertEqual(self.state.connected_address, b"")
        self.assertFalse(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(self.backend_commands(), [])

    def test_verify_link_unknown_queries_preserve_tracked_peer_and_current_output(self):
        self.set_live_peers(ADDRESS)
        self.state.connected_address = ADDRESS
        self.state.connected_name = b"Existing headphones"
        self.library.test_route_active(True)
        for mode, expected in (("show-incomplete", FAILED), ("show-failed", FAILED),
                               ("info-incomplete", FAILED), ("info-ambiguous", FAILED),
                               ("info-failed", FAILED), ("info-hang", TIMEOUT),
                               ("wrong-info-peer", FAILED)):
            with self.subTest(mode=mode):
                self.mode(mode)
                self.command_log.write_text("", encoding="ascii")
                self.assertEqual(self.execute(VERIFY_LINK), expected)
                self.assertEqual(self.state.connected_address, ADDRESS)
                self.assertEqual(self.state.connected_name, b"Existing headphones")
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                self.assertTrue(set(self.backend_commands()) <= {"show", "info"})

    def test_verify_link_route_failure_or_cancellation_keeps_the_connection_record(self):
        self.set_live_peers()
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.library.test_route_failure(-errno.EIO)
        self.assertEqual(self.execute(VERIFY_LINK), AUDIO_FAILED)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.library.test_route_failure(0)
        self.command_log.write_text("", encoding="ascii")
        cancel = CANCEL(lambda context: "|info|" in self.command_log.read_text())
        self.assertEqual(self.execute(VERIFY_LINK, cancel=cancel), CANCELLED)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertTrue(set(self.backend_commands()) <= {"show", "info"})

    def test_verify_link_connected_peer_with_inactive_pcm_reports_audio_failure(self):
        self.set_live_peers(ADDRESS)
        self.state.connected_address = ADDRESS
        self.assertEqual(self.execute(VERIFY_LINK), AUDIO_FAILED)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertFalse(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(self.backend_commands(), ["show", "info"])

    def test_pcm_readiness_rejects_prefixed_error_suffixed_and_other_peer_paths(self):
        for mode in ("pcm-prefix", "pcm-error-prefix", "pcm-suffix", "pcm-wrong-peer"):
            with self.subTest(mode=mode):
                self.set_live_peers(OTHER)
                self.state.connected_address = OTHER
                self.library.test_route_active(True)
                self.mode(mode)
                self.assertNotEqual(self.execute(CONNECT_PAIRED, ADDRESS), OK)
                self.assertEqual(self.state.connected_address, OTHER)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                self.assertEqual(self.live_peers(), {OTHER.decode()})

    def test_pcm_readiness_accepts_only_complete_matching_path_lines(self):
        for mode in ("pcm-crlf", "pcm-no-newline", "pcm-plain"):
            with self.subTest(mode=mode):
                self.set_live_peers()
                self.state.connected_address = b""
                self.library.test_route_active(False)
                self.mode(mode)
                self.assertEqual(self.execute(CONNECT, ADDRESS), OK)
                self.assertEqual(self.state.connected_address, ADDRESS)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())

    def test_pair_pin_false_and_connection_false(self):
        self.mode("pin")
        self.assertEqual(self.execute(CONNECT, ADDRESS), PIN)
        self.mode("pair-false")
        self.assertEqual(self.execute(CONNECT, ADDRESS), PAIR_FAILED)
        self.mode("connect-false")
        self.assertEqual(self.execute(CONNECT, ADDRESS), CONNECT_FAILED)
        self.assertEqual(self.state.connected_address, b"")

    def test_endpoint_clock_failure_stops_retries_and_preserves_previous_route(self):
        descriptors = len(list(Path("/proc/self/fd").iterdir()))
        self.mode("no-pcm")
        self.state.connected_address = OTHER
        self.state.connected_name = b"previous"
        self.library.test_route_active(True)
        self.library.test_endpoint_clock_failure(True)
        cancel = CANCEL(lambda context: self.library.test_endpoint_clock_failures() >= 3)
        try:
            result = self.execute(CONNECT, ADDRESS, cancel)
            failures = self.library.test_endpoint_clock_failures()
            commands = self.command_log.read_text().splitlines()
            self.measurements["endpoint_clock_failure"] = {
                "result": result, "clock_read_failures": failures,
                "commands": commands, "hardware_energy_measured": False,
                "guard": "Cancel after three injected clock failures if production keeps retrying",
            }
        finally:
            self.library.test_endpoint_clock_failure(False)
        self.assert_backend_resources_released(descriptors)
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertEqual(self.state.connected_name, b"previous")
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertEqual(result, FAILED)
        self.assertEqual(failures, 1)
        self.assertEqual(sum(line.endswith("|list-pcms") for line in commands), 1)

    def test_no_pcm_and_route_failure_preserve_previous(self):
        self.state.connected_address = OTHER
        self.state.connected_name = b"previous"
        self.mode("no-pcm")
        self.assertEqual(self.execute(CONNECT, ADDRESS), CONNECT_FAILED)
        self.assertEqual(self.state.connected_address, OTHER)
        self.mode("good")
        self.library.test_route_failure(1)
        self.assertEqual(self.execute(CONNECT, ADDRESS), AUDIO_FAILED)
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertEqual(self.execute(DISCONNECT), AUDIO_FAILED)
        self.assertEqual(self.state.connected_address, OTHER)

    def set_live_peers(self, *addresses):
        (self.binary_directory / "live-peers").write_text(
            "".join(address.decode("ascii") + "\n" for address in addresses), encoding="ascii")

    def live_peers(self):
        return set((self.binary_directory / "live-peers").read_text(encoding="ascii").splitlines())

    def test_live_peer_failed_endpoint_disconnects_verified_preexisting_peer(self):
        self.set_live_peers(ADDRESS)
        self.mode("no-pcm")
        self.assertEqual(self.execute(CONNECT, ADDRESS), CONNECT_FAILED)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.assertNotIn("|disconnect|", self.command_log.read_text())
        self.mode("good")
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.live_peers(), set())
        self.assertIn("|disconnect|" + ADDRESS.decode() + "\n", self.command_log.read_text())

    def test_live_peer_failed_pcm_disconnects_verified_preexisting_peer(self):
        self.set_live_peers(ADDRESS)
        self.library.test_route_failure(-errno.EIO)
        self.assertEqual(self.execute(CONNECT, ADDRESS), AUDIO_FAILED)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.library.test_route_failure(0)
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.live_peers(), set())

    def test_live_peer_failed_new_session_cleans_only_owned_peer(self):
        for failure in ("endpoint", "pcm"):
            with self.subTest(failure=failure):
                self.set_live_peers(OTHER)
                self.command_log.write_text("", encoding="ascii")
                self.state.connected_address = OTHER
                self.state.connected_name = b"Previous headphones"
                self.library.test_route_active(True)
                self.library.test_route_failure(-errno.EIO if failure == "pcm" else 0)
                self.mode("good" if failure == "pcm" else "no-pcm")
                self.assertEqual(self.execute(CONNECT, ADDRESS),
                                 AUDIO_FAILED if failure == "pcm" else CONNECT_FAILED)
                self.assertEqual(self.live_peers(), {OTHER.decode()})
                self.assertEqual(self.state.connected_address, OTHER)
                self.assertEqual(self.state.connected_name, b"Previous headphones")
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                commands = self.command_log.read_text()
                self.assertIn("|disconnect|" + ADDRESS.decode() + "\n", commands)
                self.assertNotIn("|disconnect|" + OTHER.decode(), commands)

    def test_live_peer_failed_preexisting_session_does_not_roll_back_either_peer(self):
        self.set_live_peers(ADDRESS, OTHER)
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        self.mode("no-pcm")
        self.assertEqual(self.execute(CONNECT, ADDRESS), CONNECT_FAILED)
        self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertNotIn("|disconnect|", self.command_log.read_text())

    def test_live_peer_untracked_incoming_disconnect_is_targeted(self):
        self.set_live_peers(OTHER)
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.live_peers(), set())
        commands = self.command_log.read_text()
        self.assertIn("|info|" + OTHER.decode() + "\n", commands)
        self.assertIn("|disconnect|" + OTHER.decode() + "\n", commands)
        self.assertNotIn("|disconnect|" + ADDRESS.decode(), commands)
        self.assertNotIn("|connect|", commands)

    def test_live_peer_ambiguous_incoming_does_not_disconnect_all(self):
        self.set_live_peers(ADDRESS, OTHER)
        self.assertEqual(self.execute(DISCONNECT), BUSY)
        self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
        self.assertNotIn("|disconnect|", self.command_log.read_text())

    def test_live_peer_refresh_inactive_pcm_retains_live_session_for_disconnect(self):
        self.set_live_peers(ADDRESS)
        self.state.connected_address = ADDRESS
        self.state.connected_name = b"Headphones"
        self.library.test_route_active(False)
        self.assertEqual(self.execute(REFRESH), AUDIO_FAILED)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertEqual(self.state.connected_name, b"Headphones")
        self.assertIn("|info|" + ADDRESS.decode() + "\n", self.command_log.read_text())
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.live_peers(), set())

    def test_live_peer_observation_errors_never_report_disconnect_success(self):
        for mode, expected in (("info-incomplete", FAILED), ("info-ambiguous", FAILED),
                               ("info-failed", FAILED), ("info-hang", TIMEOUT),
                               ("device-list-failed", FAILED), ("device-list-error", FAILED),
                               ("device-list-malformed", FAILED),
                               ("device-list-overflow", BUSY)):
            with self.subTest(mode=mode):
                self.set_live_peers(ADDRESS)
                self.command_log.write_text("", encoding="ascii")
                self.mode(mode)
                self.assertEqual(self.execute(DISCONNECT), expected)
                self.assertEqual(self.live_peers(), {ADDRESS.decode()})
                self.assertNotIn("|disconnect|", self.command_log.read_text())

    def test_live_peer_cancelled_observation_preserves_incoming_peer(self):
        self.set_live_peers(OTHER)
        cancel = CANCEL(lambda context: "|devices\n" in self.command_log.read_text())
        self.assertEqual(self.execute(DISCONNECT, cancel=cancel), CANCELLED)
        self.assertEqual(self.live_peers(), {OTHER.decode()})
        self.assertNotIn("|disconnect|", self.command_log.read_text())

    def test_live_peer_false_disconnect_and_timeout_do_not_report_success(self):
        for mode, expected in (("disconnect-false", CONNECT_FAILED), ("disconnect-hang", TIMEOUT)):
            with self.subTest(mode=mode):
                self.set_live_peers(ADDRESS)
                self.command_log.write_text("", encoding="ascii")
                self.mode(mode)
                self.assertEqual(self.execute(DISCONNECT), expected)
                self.assertEqual(self.live_peers(), {ADDRESS.decode()})
                self.assertIn("|disconnect|" + ADDRESS.decode() + "\n", self.command_log.read_text())

    def test_live_peer_cancelled_connect_is_discoverable_without_blind_cleanup(self):
        self.set_live_peers()
        cancel = CANCEL(lambda context: "|list-pcms\n" in self.command_log.read_text())
        self.assertEqual(self.execute(CONNECT, ADDRESS, cancel), CANCELLED)
        self.assertEqual(self.state.connected_address, b"")
        self.assertEqual(self.live_peers(), {ADDRESS.decode()})
        self.assertNotIn("|disconnect|", self.command_log.read_text())
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.live_peers(), set())

    def test_live_peer_verified_empty_disconnect_is_idempotent(self):
        self.set_live_peers()
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertIn("|devices\n", self.command_log.read_text())
        self.assertNotIn("|disconnect|", self.command_log.read_text())

    def test_live_peer_owned_cleanup_failure_preserves_previous_session(self):
        (self.binary_directory / "endpoint-missing").write_text("", encoding="ascii")
        for mode, expected in (("disconnect-fails", FAILED), ("disconnect-false", CONNECT_FAILED),
                               ("disconnect-hang", TIMEOUT)):
            with self.subTest(mode=mode):
                self.set_live_peers(OTHER)
                self.command_log.write_text("", encoding="ascii")
                self.mode(mode)
                self.state.connected_address = OTHER
                self.library.test_route_active(True)
                self.assertEqual(self.execute(CONNECT, ADDRESS), expected)
                self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
                self.assertEqual(self.state.connected_address, OTHER)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                commands = self.command_log.read_text()
                self.assertIn("|disconnect|" + ADDRESS.decode() + "\n", commands)
                self.assertNotIn("|disconnect|" + OTHER.decode(), commands)

    def test_live_peer_owned_cleanup_cancellation_preserves_previous_session(self):
        self.set_live_peers(OTHER)
        (self.binary_directory / "endpoint-missing").write_text("", encoding="ascii")
        self.mode("disconnect-hang")
        self.state.connected_address = OTHER
        self.library.test_route_active(True)
        cancel = CANCEL(lambda context: "|disconnect|" + ADDRESS.decode() in self.command_log.read_text())
        self.assertEqual(self.execute(CONNECT, ADDRESS, cancel), CANCELLED)
        self.assertEqual(self.live_peers(), {ADDRESS.decode(), OTHER.decode()})
        self.assertEqual(self.state.connected_address, OTHER)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertNotIn("|disconnect|" + OTHER.decode(), self.command_log.read_text())

    def test_live_peer_known_disconnect_preserves_unrelated_live_peer(self):
        self.set_live_peers(ADDRESS, OTHER)
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.assertEqual(self.execute(DISCONNECT), OK)
        self.assertEqual(self.live_peers(), {OTHER.decode()})
        self.assertEqual(self.state.connected_address, b"")
        self.assertNotIn("|disconnect|" + OTHER.decode(), self.command_log.read_text())

    def test_live_peer_inactive_refresh_unknown_connection_preserves_record(self):
        for mode, expected in (("info-incomplete", FAILED), ("info-ambiguous", FAILED),
                               ("info-failed", FAILED), ("info-hang", TIMEOUT)):
            with self.subTest(mode=mode):
                self.set_live_peers(ADDRESS)
                self.mode(mode)
                self.state.connected_address = ADDRESS
                self.state.connected_name = b"Headphones"
                self.assertEqual(self.execute(REFRESH), expected)
                self.assertEqual(self.state.connected_address, ADDRESS)
                self.assertEqual(self.state.connected_name, b"Headphones")
                self.assertEqual(self.live_peers(), {ADDRESS.decode()})

    def test_live_peer_observation_has_one_deadline_for_all_peers(self):
        self.set_live_peers()
        self.mode("observation-budget")
        started = time.monotonic()
        self.assertEqual(self.execute(DISCONNECT), TIMEOUT)
        elapsed = time.monotonic() - started
        queries = [command for command in self.command_log.read_text().splitlines() if "|info|" in command]
        self.assertLess(len(queries), 8)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(self.live_peers(), set())
        self.assertNotIn("|disconnect|", self.command_log.read_text())
        self.measurements["live_peer_observation_deadline"] = {
            "seconds": elapsed, "queried": len(queries), "listed": 8, "budget_ms": 250}

    def test_remove_unrelated_preserves_connection(self):
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.assertEqual(self.execute(REMOVE, OTHER), OK)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())
        self.assertNotIn("|disconnect", self.command_log.read_text())

    def test_route_cancellation_timeout_and_busy_are_not_success(self):
        for route_error, expected in ((errno.ECANCELED, CANCELLED), (errno.ETIMEDOUT, TIMEOUT), (errno.EBUSY, BUSY)):
            with self.subTest(route_error=route_error):
                self.library.test_route_failure(-route_error)
                self.state.connected_address = OTHER
                self.assertEqual(self.execute(CONNECT, ADDRESS), expected)
                self.assertEqual(self.state.connected_address, OTHER)
                self.assertEqual(self.execute(DISCONNECT), expected)

    def test_invalid_address_and_early_cancel_do_not_spawn(self):
        self.assertEqual(self.execute(CONNECT, ADDRESS + b";rm"), INVALID)
        self.assertEqual(self.execute(ENABLE, cancel=CANCEL(lambda context: True)), CANCELLED)
        self.assertEqual(self.command_log.read_text(), "")

    def test_refresh_detects_missing_output(self):
        self.state.connected_address = ADDRESS
        self.assertEqual(self.execute(REFRESH), AUDIO_FAILED)
        self.assertEqual(self.state.connected_address, ADDRESS)

    def test_refresh_observes_external_power_and_connection_loss(self):
        for mode, enabled in (("power-false", False), ("connect-false", True)):
            with self.subTest(mode=mode):
                self.state.enabled = True
                self.state.connected_address = ADDRESS
                self.state.connected_name = b"Headphones"
                self.library.test_route_active(True)
                self.mode(mode)
                self.assertEqual(self.execute(REFRESH), CONNECT_FAILED)
                self.assertEqual(self.state.enabled, enabled)
                self.assertFalse(self.library.pcm_alsa_bluetooth_active())
                self.assertEqual(self.state.connected_address, b"")
                self.assertEqual(self.state.connected_name, b"")

    def test_refresh_route_failure_and_cancel_preserve_connection(self):
        for route_error, expected in ((errno.EIO, AUDIO_FAILED), (errno.ECANCELED, CANCELLED),
                                      (errno.ETIMEDOUT, TIMEOUT), (errno.EBUSY, BUSY)):
            with self.subTest(route_error=route_error):
                self.state.connected_address = ADDRESS
                self.library.test_route_active(True)
                self.library.test_route_failure(-route_error)
                self.mode("connect-false")
                self.assertEqual(self.execute(REFRESH), expected)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                self.assertEqual(self.state.connected_address, ADDRESS)

    def test_refresh_updates_external_power_without_connection(self):
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertTrue(self.state.enabled)
        self.mode("power-false")
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertFalse(self.state.enabled)

    def test_disconnect_restores_output_without_bluealsa_cli(self):
        helper = self.binary_directory / "bluealsa-cli"
        parked = helper.with_name("bluealsa-cli-unavailable")
        helper.rename(parked)
        try:
            for operation, address in ((DISCONNECT, None), (DISABLE, None), (REMOVE, OTHER)):
                with self.subTest(operation=operation):
                    self.state.connected_address = OTHER
                    self.library.test_route_active(True)
                    self.assertEqual(self.execute(operation, address), OK)
                    self.assertFalse(self.library.pcm_alsa_bluetooth_active())
                    self.assertEqual(self.state.connected_address, b"")
        finally:
            parked.rename(helper)

    def test_missing_bluez_cli_still_restores_wired_output(self):
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        helper = self.binary_directory / "bluetoothctl"
        parked = helper.with_name("bluetoothctl-unavailable")
        helper.rename(parked)
        try:
            self.assertEqual(self.execute(DISCONNECT), UNAVAILABLE)
            self.assertFalse(self.library.pcm_alsa_bluetooth_active())
            self.assertEqual(self.state.connected_address, ADDRESS)
            self.assertFalse(self.state.available)
            self.assertEqual(self.command_log.read_text(), "")
        finally:
            parked.rename(helper)

    def test_refresh_unknown_properties_preserve_connection(self):
        for mode in ("show-failed", "show-incomplete", "info-incomplete"):
            with self.subTest(mode=mode):
                self.state.enabled = True
                self.state.connected_address = ADDRESS
                self.library.test_route_active(True)
                self.mode(mode)
                self.assertEqual(self.execute(REFRESH), FAILED)
                self.assertTrue(self.state.enabled)
                self.assertTrue(self.library.pcm_alsa_bluetooth_active())
                self.assertEqual(self.state.connected_address, ADDRESS)

    def test_first_refresh_unknown_power_is_an_error_not_confirmed_off(self):
        for mode in ("show-failed", "show-incomplete"):
            with self.subTest(mode=mode):
                self.state = Snapshot()
                self.mode(mode)
                self.assertEqual(self.execute(REFRESH), FAILED)
                self.assertFalse(self.state.enabled)
                self.assertEqual(self.state.connected_address, b"")
                self.assertTrue(self.integrated.hiby_bluetooth_init())
                self.assertTrue(self.integrated.hiby_bluetooth_request(REFRESH, None))
                published = self.wait_idle(timeout=3, library=self.integrated)
                self.assertEqual(published.error, FAILED)
                self.assertFalse(published.enabled)
                self.integrated.hiby_bluetooth_shutdown()

    def test_refresh_error_preserves_both_stale_radio_values(self):
        for enabled in (False, True):
            for mode in ("show-failed", "show-incomplete"):
                with self.subTest(enabled=enabled, mode=mode):
                    self.state = Snapshot()
                    self.state.enabled = enabled
                    self.mode(mode)
                    self.assertEqual(self.execute(REFRESH), FAILED)
                    self.assertEqual(self.state.enabled, enabled)

    def test_actual_status_ui_does_not_announce_unknown_or_stale_radio_state(self):
        controller_text = CONTROLLER.read_text(encoding="utf-8")
        ui_source = controller_text[controller_text.index("enum bluetooth_ui_result"):]
        ui_source = ui_source.rsplit("#endif", 1)[0]
        identifiers = sorted(set(re.findall(r"\bLANG_[A-Z0-9_]+\b", ui_source)))
        enum_source = "enum { " + ", ".join(identifiers) + " };\n"
        source = self.evidence / "status-ui.c"
        source.write_text(UI_STATUS_PRELUDE + enum_source + ui_source + UI_STATUS_MAIN, encoding="utf-8")
        executions = []
        for sanitized in (False, True):
            executable = self.evidence / ("status-ui-sanitized" if sanitized else "status-ui")
            options = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"] if sanitized else []
            self.compile_command(self.flags + self.includes + options + [str(source), "-o", str(executable)])
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10,
                                    env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1"})
            executions.append({"sanitized": sanitized, "returncode": result.returncode,
                               "stdout": result.stdout, "stderr": result.stderr})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "verified-status-cases=19\n")
        (self.evidence / "status-ui-result.json").write_text(json.dumps(executions, indent=2), encoding="utf-8")

    def test_refresh_healthy_connection_preserves_output(self):
        self.state.connected_address = ADDRESS
        self.library.test_route_active(True)
        self.assertEqual(self.execute(REFRESH), OK)
        self.assertEqual(self.state.connected_address, ADDRESS)
        self.assertTrue(self.library.pcm_alsa_bluetooth_active())

    def test_concurrent_shutdown_waits_for_worker(self):
        self.assertTrue(self.controller.hiby_bluetooth_init())
        self.controller.test_hold_backend(True)
        finished = [threading.Event(), threading.Event()]
        threads = []
        def shutdown(position):
            self.controller.hiby_bluetooth_shutdown()
            finished[position].set()
        try:
            self.assertTrue(self.controller.hiby_bluetooth_request(ENABLE, None))
            deadline = time.monotonic() + 1
            while not self.controller.test_active() and time.monotonic() < deadline:
                time.sleep(0.001)
            self.assertEqual(self.controller.test_active(), 1)
            first = threading.Thread(target=shutdown, args=(0,))
            threads.append(first)
            first.start()
            deadline = time.monotonic() + 1
            while self.controller.hiby_bluetooth_init() and time.monotonic() < deadline:
                time.sleep(0.001)
            self.assertFalse(self.controller.hiby_bluetooth_init())
            second = threading.Thread(target=shutdown, args=(1,))
            threads.append(second)
            second.start()
            self.assertFalse(finished[1].wait(0.08))
            self.assertFalse(finished[0].is_set())
        finally:
            self.controller.test_hold_backend(False)
            for thread in threads:
                thread.join(1)
        self.assertTrue(all(event.is_set() for event in finished))
        self.assertFalse(self.snapshot().busy)
        self.assertTrue(self.controller.hiby_bluetooth_init())

    def wait_for_fake_backend(self, library):
        deadline = time.monotonic() + 1
        while not library.test_active() and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertEqual(library.test_active(), 1)

    def test_automatic_worker_restricts_operations_and_accepts_only_bounded_timeouts(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        library.test_controller_clock(True, 0, 0, 0)
        calls = library.test_calls()
        for operation in (-1, *range(CONNECT_PAIRED), VERIFY_LINK + 1):
            self.assertFalse(library.hiby_bluetooth_request_automatic(operation, ADDRESS, 100))
        for timeout in (0, 15001, 0xffffffff):
            for operation in (CONNECT_PAIRED, VERIFY_LINK):
                self.assertFalse(library.hiby_bluetooth_request_automatic(operation, ADDRESS, timeout))
        self.assertFalse(library.hiby_bluetooth_request_automatic(CONNECT_PAIRED, b"bad", 100))
        self.assertEqual(self.snapshot(library).error, INVALID)
        self.assertFalse(library.hiby_bluetooth_request(VERIFY_LINK + 1, None))
        self.assertEqual(self.snapshot(library).error, INVALID)
        self.assertEqual(library.test_calls(), calls)
        for operation, address in ((CONNECT_PAIRED, ADDRESS), (VERIFY_LINK, None)):
            for timeout in (1, 15000):
                self.assertTrue(library.hiby_bluetooth_request_automatic(operation, address, timeout))
                self.assertEqual(self.wait_idle(library=library).error, OK)
        self.assertEqual(library.test_calls() - calls, 4)

    def test_automatic_worker_budget_starts_at_enqueue_before_worker_execution(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        library.test_controller_clock(True, 0, 0, 80)
        self.assertTrue(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 50))
        observed = self.wait_idle(library=library)
        self.measurements["automatic_enqueue_budget"] = {
            "budget_ms": 50, "injected_pre_worker_ms": 80, "result": observed.error,
            "clock_reads": library.test_controller_clock_read_count()}
        self.assertEqual(observed.error, TIMEOUT)

    def test_automatic_worker_clock_failure_at_enqueue_rejects_without_backend_calls(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        calls = library.test_calls()
        generation = self.snapshot(library).generation
        library.test_controller_clock(True, 1, 0, 0)
        self.assertFalse(library.hiby_bluetooth_request_automatic(CONNECT_PAIRED, ADDRESS, 100))
        observed = self.snapshot(library)
        self.assertEqual(observed.error, TIMEOUT)
        self.assertFalse(observed.busy)
        self.assertGreater(observed.generation, generation)
        self.assertEqual(library.test_calls(), calls)

    def test_automatic_worker_clock_failure_at_start_or_callback_fails_closed(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        for failing_read in (2, 3):
            with self.subTest(failing_read=failing_read):
                library.test_controller_clock(True, failing_read, 0, 0)
                self.assertTrue(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 100))
                self.assertEqual(self.wait_idle(library=library).error, TIMEOUT)

    def test_automatic_worker_backwards_clock_at_callback_fails_closed(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        library.test_controller_clock(True, 0, 3, 0)
        self.assertTrue(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 100))
        self.assertEqual(self.wait_idle(library=library).error, TIMEOUT)

    def test_automatic_worker_backwards_clock_between_enqueue_and_start_fails_closed(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        library.test_controller_clock(True, 0, 2, 0)
        self.assertTrue(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 100))
        observed = self.wait_idle(library=library)
        self.measurements["automatic_backwards_before_start"] = {
            "enqueue_clock_ms": 5000, "worker_start_clock_ms": 4999, "result": observed.error}
        self.assertEqual(observed.error, TIMEOUT)

    def test_automatic_worker_real_deadline_and_late_backend_success_remain_timeout(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        for ignore in (False, True):
            with self.subTest(ignore=ignore):
                library.test_ignore_cancellation(ignore)
                library.test_controller_clock(False, 0, 0, 0)
                started = time.monotonic()
                self.assertTrue(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 8))
                self.assertEqual(self.wait_idle(library=library).error, TIMEOUT)
                self.assertLess(time.monotonic() - started, 0.5)

    def test_cancel_automatic_only_cancels_busy_automatic_work(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        self.assertFalse(library.hiby_bluetooth_cancel_automatic())
        for automatic in (False, True):
            with self.subTest(automatic=automatic):
                library.test_controller_clock(True, 0, 0, 0)
                library.test_hold_backend(True)
                try:
                    if automatic:
                        self.assertTrue(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 15000))
                    else:
                        self.assertTrue(library.hiby_bluetooth_request(ENABLE, None))
                    self.wait_for_fake_backend(library)
                    generation = self.snapshot(library).generation
                    self.assertFalse(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 100))
                    self.assertEqual(self.snapshot(library).generation, generation)
                    self.assertEqual(library.hiby_bluetooth_cancel_automatic(), automatic)
                    self.assertTrue(self.snapshot(library).busy)
                finally:
                    library.test_hold_backend(False)
                self.assertEqual(self.wait_idle(library=library).error, CANCELLED if automatic else OK)
                self.assertFalse(library.hiby_bluetooth_cancel_automatic())

    def test_automatic_worker_inhibition_blocks_connect_but_allows_link_verification(self):
        library = self.clock_controller
        self.assertTrue(library.hiby_bluetooth_init())
        library.test_controller_clock(True, 0, 0, 0)
        library.hiby_bluetooth_set_inhibited(True)
        self.assertFalse(library.hiby_bluetooth_request_automatic(CONNECT_PAIRED, ADDRESS, 100))
        self.assertEqual(self.snapshot(library).error, INHIBITED)
        self.assertTrue(library.hiby_bluetooth_request_automatic(VERIFY_LINK, None, 100))
        self.assertEqual(self.wait_idle(library=library).error, OK)
        self.assertTrue(library.hiby_bluetooth_is_inhibited())

    def test_simulator_automatic_worker_operations_are_explicitly_unavailable(self):
        for operation, address in ((CONNECT_PAIRED, ADDRESS), (VERIFY_LINK, None)):
            self.assertFalse(self.simulator.hiby_bluetooth_request_automatic(operation, address, 100))
        self.assertFalse(self.simulator.hiby_bluetooth_cancel_automatic())

    def test_worker_busy_cancel_and_restart(self):
        self.assertTrue(self.controller.hiby_bluetooth_init())
        self.assertTrue(self.controller.hiby_bluetooth_init())
        self.assertTrue(self.controller.hiby_bluetooth_request(ENABLE, None))
        self.assertFalse(self.controller.hiby_bluetooth_request(SCAN, None))
        self.assertTrue(self.snapshot().busy)
        self.controller.hiby_bluetooth_cancel()
        self.assertEqual(self.wait_idle().error, CANCELLED)
        self.assertTrue(self.controller.hiby_bluetooth_request(ENABLE, None))
        self.assertTrue(self.wait_idle().enabled)
        self.assertEqual(self.controller.test_maximum(), 1)
        self.controller.hiby_bluetooth_shutdown()
        self.assertFalse(self.controller.hiby_bluetooth_request(ENABLE, None))
        self.assertTrue(self.controller.hiby_bluetooth_init())

    def test_worker_inhibit_rejects_enable_scan_connect_until_cleared(self):
        for library in (self.controller, self.integrated):
            with self.subTest(library=library._name):
                library.hiby_bluetooth_set_inhibited(True)
                self.assertTrue(library.hiby_bluetooth_init())
                self.assertTrue(library.hiby_bluetooth_is_inhibited())
                calls = self.controller.test_calls()
                for operation, address in ((ENABLE, None), (SCAN, None), (CONNECT, ADDRESS)):
                    generation = self.snapshot(library).generation
                    self.assertFalse(library.hiby_bluetooth_request(operation, address))
                    rejected = self.snapshot(library)
                    self.assertEqual(rejected.error, INHIBITED)
                    self.assertFalse(rejected.busy)
                    self.assertGreater(rejected.generation, generation)
                self.assertEqual(self.controller.test_calls(), calls)
                self.assertEqual(self.command_log.read_text(), "")
                library.hiby_bluetooth_shutdown()
                self.assertTrue(library.hiby_bluetooth_init())
                self.assertTrue(library.hiby_bluetooth_is_inhibited())
                self.assertFalse(library.hiby_bluetooth_request(ENABLE, None))
                self.assertTrue(library.hiby_bluetooth_request(DISABLE, None))
                self.assertEqual(self.wait_idle(timeout=3, library=library).error, OK)
                self.assertTrue(library.hiby_bluetooth_is_inhibited())
                library.hiby_bluetooth_set_inhibited(False)
                self.assertTrue(library.hiby_bluetooth_request(ENABLE, None))
                enabled = self.wait_idle(timeout=3, library=library)
                self.assertEqual(enabled.error, OK)
                self.assertTrue(enabled.enabled)
                self.assertTrue(enabled.power_known)
                library.hiby_bluetooth_shutdown()
                self.command_log.write_text("", encoding="ascii")

    def test_worker_late_backend_success_after_cancel_stays_cancelled_unknown(self):
        self.assertTrue(self.controller.hiby_bluetooth_init())
        self.controller.test_ignore_cancellation(True)
        self.controller.test_hold_backend(True)
        try:
            self.assertTrue(self.controller.hiby_bluetooth_request(ENABLE, None))
            deadline = time.monotonic() + 1
            while not self.controller.test_active() and time.monotonic() < deadline:
                time.sleep(0.001)
            self.assertEqual(self.controller.test_active(), 1)
            self.controller.hiby_bluetooth_set_inhibited(True)
            self.assertTrue(self.snapshot().busy)
            self.assertFalse(self.controller.hiby_bluetooth_request(ENABLE, None))
        finally:
            self.controller.test_hold_backend(False)
        settled = self.wait_idle()
        self.assertEqual(settled.error, CANCELLED)
        self.assertFalse(settled.power_known)
        self.assertTrue(self.controller.hiby_bluetooth_is_inhibited())
        self.assertFalse(self.controller.hiby_bluetooth_request(ENABLE, None))
        self.assertTrue(self.controller.hiby_bluetooth_request(DISABLE, None))
        settled = self.wait_idle()
        self.assertEqual(settled.error, OK)
        self.assertTrue(settled.power_known)
        self.assertFalse(settled.enabled)

    def test_worker_resets_power_knowledge_on_request_cancel_and_restart(self):
        self.assertTrue(self.controller.hiby_bluetooth_init())
        self.assertFalse(self.snapshot().power_known)
        self.assertTrue(self.controller.hiby_bluetooth_request(REFRESH, None))
        self.assertTrue(self.wait_idle().power_known)
        self.controller.test_hold_backend(True)
        try:
            self.assertTrue(self.controller.hiby_bluetooth_request(SCAN, None))
            self.assertTrue(self.snapshot().busy)
            self.assertFalse(self.snapshot().power_known)
            self.controller.hiby_bluetooth_cancel()
        finally:
            self.controller.test_hold_backend(False)
        cancelled = self.wait_idle()
        self.assertEqual(cancelled.error, CANCELLED)
        self.assertFalse(cancelled.power_known)
        self.controller.hiby_bluetooth_shutdown()
        self.assertTrue(self.controller.hiby_bluetooth_init())
        self.assertFalse(self.snapshot().power_known)

    def test_actual_worker_scan_connect_off_never_auto_enable(self):
        self.assertTrue(self.integrated.hiby_bluetooth_init())
        self.assertTrue(self.integrated.hiby_bluetooth_request(DISABLE, None))
        self.assertEqual(self.wait_idle(timeout=3, library=self.integrated).error, OK)
        self.command_log.write_text("", encoding="ascii")
        for operation, address in ((SCAN, None), (CONNECT, ADDRESS), (REFRESH, None)):
            with self.subTest(operation=operation):
                self.assertTrue(self.integrated.hiby_bluetooth_request(operation, address))
                observed = self.wait_idle(timeout=3, library=self.integrated)
                self.assertEqual(observed.error, OK if operation == REFRESH else POWERED_OFF)
                self.assertTrue(observed.power_known)
                self.assertFalse(observed.enabled)
                commands = self.command_log.read_text()
                for forbidden in ("power on", "bt_resume", "scan on", "pair ", "trust ", "connect "):
                    self.assertNotIn(forbidden, commands)

    def test_worker_shutdown_cancels_bounded_and_invalid_is_rejected(self):
        self.assertTrue(self.controller.hiby_bluetooth_init())
        self.assertFalse(self.controller.hiby_bluetooth_request(CONNECT, b"bad"))
        self.assertEqual(self.snapshot().error, INVALID)
        self.assertTrue(self.controller.hiby_bluetooth_request(SCAN, None))
        started = time.monotonic()
        self.controller.hiby_bluetooth_shutdown()
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(self.snapshot().busy)

    def test_simulator_is_explicitly_unavailable(self):
        self.assertFalse(self.simulator.hiby_bluetooth_init())
        self.assertFalse(self.simulator.hiby_bluetooth_request(ENABLE, None))
        state = self.snapshot(self.simulator)
        self.assertFalse(state.available)
        self.assertFalse(state.enabled)
        self.assertFalse(state.busy)
        self.assertEqual(state.error, UNAVAILABLE)

    def test_actual_c_sanitizers_and_closed_standard_fds(self):
        source = self.evidence / "sanitizer.c"
        source.write_text(WRAPPER.replace("BACKEND_PATH", BACKEND.as_posix()) + SANITIZER_MAIN, encoding="utf-8")
        executable = self.evidence / "sanitizer"
        self.compile_command(self.flags + self.includes + ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
            "-DHIBY_BT_HOST_TEST", "-DHIBY_BT_NO_UI", '-DHIBY_BT_BIN_DIRECTORY="' + self.binary_directory.as_posix() + '"',
            "-DHIBY_BT_SCAN_HOLD_MS=50", "-DHIBY_BT_COMMAND_TIMEOUT_MS=500", "-DHIBY_BT_RESUME_TIMEOUT_MS=300",
            "-DHIBY_BT_ENDPOINT_TIMEOUT_MS=200",
            str(source), str(CONTROLLER), "-o", str(executable)])
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60,
                                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1"})
        (self.evidence / "sanitizer-result.json").write_text(json.dumps({"returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}, indent=2), encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("runtime error", result.stderr)

    def test_full_ui_compiles_with_actual_native_and_windows_headers(self):
        central = project_materials_root(ROOT)
        native = central / "toolchains/hiby-r1-20261010/prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        windows = shutil.which("x86_64-w64-mingw32-gcc")
        if not native.is_file() or not windows or not shutil.which("perl"):
            self.skipTest("actual MIPS/MinGW toolchains and Perl unavailable; NO_UI tests are not UI validation")
        language = self.evidence / "ui-lang"
        language.mkdir()
        english = ROOT / "apps/lang/english.lang"
        self.compile_command(["perl", "-s", str(ROOT / "tools/genlang"), "-p=" + str(language),
                              "-t=hibyr1:hibylinux:swcodec:lcd_bitmap:lcd_color:touchscreen:espeak",
                              "-e=" + str(english), str(english)])
        shared = ["firmware", "firmware/export", "firmware/drivers", "firmware/include",
                  "firmware/kernel/include", "firmware/target/hosted/hiby/r1", "firmware/target/hosted/hiby",
                  "firmware/target/hosted", "apps", "apps/gui", "apps/recorder", "apps/radio",
                  "lib/rbcodec", "lib/rbcodec/codecs", "lib/rbcodec/dsp", "lib/rbcodec/metadata",
                  "lib/fixedpoint", "lib/skin_parser", "lib/utf8proc"]
        common = ["-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wno-pointer-sign",
                  "-DROCKBOX", "-DMEMORYSIZE=16", "-DHIBY_R1", "-DTARGET_ID=124", "-I", str(language)]
        for directory in shared:
            common += ["-I", str(ROOT / directory)]
        native_build = central / "build-espeak-hibyr1"
        self.compile_command([str(native)] + common + ["-DAPPLICATION", "-D_GNU_SOURCE=1", "-march=mips32r2", "-mhard-float",
            "-I", str(native_build), "-c", str(CONTROLLER), "-o", str(self.evidence / "ui-native.o")])
        self.compile_command([str(native)] + common + ["-DAPPLICATION", "-D_GNU_SOURCE=1", "-march=mips32r2", "-mhard-float",
            "-I", str(native_build), "-c", str(BACKEND), "-o", str(self.evidence / "backend-native.o")])
        windows_build = central / "build-espeak-windows-hibyr1"
        self.compile_command([windows] + common + ["-DSIMULATOR", "-DDEBUG", "-I", str(windows_build),
            "-I", str(ROOT / "firmware/target/hosted/sdl"), "-I", str(ROOT / "uisimulator/sdl"),
            "-I", str(central / "toolchains/SDL2-2.32.10/x86_64-w64-mingw32/include/SDL2"),
            "-c", str(CONTROLLER), "-o", str(self.evidence / "ui-windows.o")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
