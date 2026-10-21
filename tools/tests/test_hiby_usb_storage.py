"""Exercise R1 USB storage safety using compiled, syscall-mocked probes only."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
HEADER = "firmware/target/hosted/hiby/usb-storage-hiby.h"
ENGINE = "firmware/target/hosted/hiby/usb-storage-hiby.c"
GADGET = "firmware/target/hosted/hiby/usb-hiby-gadget.c"
SOURCES = (HEADER, ENGINE, GADGET, "tools/tests/test_hiby_usb_storage.py",
           "docs/ESPEAK-HIBY-USB.md", "docs/ESPEAK-HIBY-USB-PL.md")


def function(source, name):
    match = re.search(r"^(?:static\s+)?(?:struct\s+\w+\s+|\w+\s+)+" +
                      re.escape(name) + r"\([^;]*?\)\s*\{", source, re.MULTILINE)
    if not match:
        raise AssertionError("Missing function: " + name)
    position = source.index("{", match.start())
    depth = 1
    end = position + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


HARNESS = r"""
#define _DEFAULT_SOURCE 1
#include "usb-storage-hiby.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static unsigned int checks;
#define CHECK(value) do { ++checks; assert(value); } while (0)

enum operation { DETACH, LOCAL, QUIESCE, LEASE, RELEASE, CAPTURE, OVERLAPS,
                 SYNC, CLOSE_LOCAL, UNMOUNT, MOUNT, REOPEN, ATTACH, OPERATION_COUNT };
struct fixture
{
    bool mounted, exported, held, closed, remount_during_attach, corrupt_mount;
    unsigned int aliases, calls[OPERATION_COUNT], trace[512], trace_count;
    int fault_operation, fault_nth, fault_error, invalid_lease_nth;
    unsigned int remount_overlap_nth;
    struct hiby_usb_storage_mount current, restored;
};

static int call(struct fixture *fixture, enum operation operation)
{
    CHECK(fixture->trace_count < 512);
    fixture->trace[fixture->trace_count++] = (unsigned int)operation;
    ++fixture->calls[operation];
    if ((int)operation == fixture->fault_operation &&
        (int)fixture->calls[operation] == fixture->fault_nth)
        return fixture->fault_error;
    return 0;
}

static int fake_detach(void *context)
{
    struct fixture *fixture = context;
    int result = call(fixture, DETACH);
    if (!result)
        fixture->exported = false;
    return result;
}

static int fake_local(void *context)
{
    struct fixture *fixture = context;
    int result = call(fixture, LOCAL);
    return result ? result : fixture->mounted && !fixture->exported ? 0 : ENODEV;
}

static int fake_quiesce(void *context)
{
    struct fixture *fixture = context;
    int result = call(fixture, QUIESCE);
    if (!result)
        fixture->held = true;
    return result;
}

static int fake_lease(void *context)
{
    struct fixture *fixture = context;
    int result = call(fixture, LEASE);
    if (fixture->invalid_lease_nth &&
        (int)fixture->calls[LEASE] >= fixture->invalid_lease_nth)
        return EPERM;
    return result ? result : fixture->held ? 0 : EPERM;
}

static int fake_release(void *context)
{
    struct fixture *fixture = context;
    int result = call(fixture, RELEASE);
    if (!result)
        fixture->held = false;
    return result;
}

static int fake_capture(void *context, struct hiby_usb_storage_mount *mount)
{
    struct fixture *fixture = context;
    int result = call(fixture, CAPTURE);
    if (result || !fixture->mounted)
        return result ? result : ENODEV;
    *mount = fixture->current;
    return 0;
}

static int fake_overlaps(void *context, const struct hiby_usb_storage_mount *mount,
                         unsigned int *count)
{
    struct fixture *fixture = context;
    (void)mount;
    int result = call(fixture, OVERLAPS);
    if (fixture->remount_overlap_nth == fixture->calls[OVERLAPS])
        fixture->mounted = true;
    *count = (fixture->mounted ? 1u : 0u) + fixture->aliases;
    return result;
}

static int fake_sync(void *context) { return call(context, SYNC); }

static int fake_close_local(void *context)
{
    struct fixture *fixture = context;
    int result = call(fixture, CLOSE_LOCAL);
    fixture->closed = true;
    return result;
}

static int fake_unmount(void *context, const struct hiby_usb_storage_mount *mount)
{
    struct fixture *fixture = context;
    CHECK(fixture->held && fixture->mounted && !fixture->exported && fixture->closed);
    CHECK(mount->device_major == 179 && mount->device_minor == 1);
    int result = call(fixture, UNMOUNT);
    if (!result)
        fixture->mounted = false;
    return result;
}

static int fake_mount(void *context, const struct hiby_usb_storage_mount *mount)
{
    struct fixture *fixture = context;
    CHECK(fixture->held && !fixture->mounted && !fixture->exported && fixture->aliases == 0);
    int result = call(fixture, MOUNT);
    if (!result)
    {
        fixture->restored = *mount;
        fixture->current = *mount;
        fixture->mounted = true;
        if (fixture->corrupt_mount)
            ++fixture->current.flags;
    }
    return result;
}

static int fake_reopen(void *context)
{
    struct fixture *fixture = context;
    int result = call(fixture, REOPEN);
    if (!result)
        fixture->closed = false;
    return result;
}

static int fake_attach(void *context, const struct hiby_usb_storage_mount *mount)
{
    struct fixture *fixture = context;
    CHECK(fixture->held && !fixture->mounted && fixture->aliases == 0);
    CHECK(strcmp(mount->device, "/dev/mmcblk0p1") == 0);
    int result = call(fixture, ATTACH);
    fixture->exported = true;
    if (fixture->remount_during_attach)
        fixture->mounted = true;
    return result;
}

static const struct hiby_usb_storage_operations operations =
{
    fake_detach, fake_local, fake_quiesce, fake_lease, fake_release,
    fake_capture, fake_overlaps, fake_sync, fake_close_local, fake_unmount,
    fake_mount, fake_reopen, fake_attach
};

static void fresh(struct fixture *fixture, struct hiby_usb_storage *storage, bool verified)
{
    memset(fixture, 0, sizeof(*fixture));
    fixture->mounted = true;
    fixture->fault_operation = -1;
    fixture->fault_nth = 1;
    fixture->fault_error = EIO;
    strcpy(fixture->current.device, "/dev/mmcblk0p1");
    strcpy(fixture->current.directory, "/data/mnt/sd_0");
    strcpy(fixture->current.filesystem, "vfat");
    strcpy(fixture->current.options, "uid=1000,gid=1000,utf8,errors=remount-ro");
    fixture->current.flags = 15;
    fixture->current.device_major = 179;
    fixture->current.device_minor = 1;
    hiby_usb_storage_init(storage, &operations, fixture, verified);
}

static void scenario_unknown(void)
{
    struct fixture fixture;
    struct hiby_usb_storage storage;
    fresh(&fixture, &storage, false);
    CHECK(!storage.status.safe_to_resume && !storage.status.configuration_verified);
    struct hiby_usb_storage_status status = hiby_usb_storage_prepare(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_UNVERIFIED);
    CHECK(status.safe_to_resume && status.state == HIBY_USB_STORAGE_LOCAL);
    CHECK(fixture.calls[QUIESCE] == 0 && fixture.calls[CAPTURE] == 0);
    CHECK(fixture.calls[OVERLAPS] == 0 && fixture.calls[UNMOUNT] == 0 && fixture.calls[ATTACH] == 0);
    status = hiby_usb_storage_export(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_UNVERIFIED);
    CHECK(hiby_usb_storage_restore(&storage).success);
    CHECK(fixture.mounted && !fixture.exported);
    struct hiby_usb_storage_operations incomplete = { .detach = fake_detach, .local_ready = fake_local };
    hiby_usb_storage_init(&storage, &incomplete, &fixture, true);
    status = hiby_usb_storage_prepare(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_CONFIGURATION);
    CHECK(status.safe_to_resume && fixture.calls[UNMOUNT] == 0);
}

static void scenario_cycles(void)
{
    for (unsigned int iteration = 0; iteration < 40; ++iteration)
    {
        struct fixture fixture;
        struct hiby_usb_storage storage;
        fresh(&fixture, &storage, true);
        if (iteration & 1u)
            strcpy(fixture.current.filesystem, "exfat");
        fixture.current.flags = iteration;
        struct hiby_usb_storage_mount original = fixture.current;
        CHECK(hiby_usb_storage_prepare(&storage).success);
        CHECK(storage.status.state == HIBY_USB_STORAGE_PREPARED && !storage.status.safe_to_resume);
        CHECK(!fixture.mounted && fixture.closed && fixture.held && !fixture.exported);
        CHECK(hiby_usb_storage_export(&storage).success);
        CHECK(storage.status.state == HIBY_USB_STORAGE_EXPORTED && !storage.status.safe_to_resume);
        CHECK(!fixture.mounted && fixture.exported);
        CHECK(hiby_usb_storage_restore(&storage).success);
        CHECK(storage.status.safe_to_resume && fixture.mounted && !fixture.exported);
        CHECK(!fixture.held && !fixture.closed && !storage.saved && !storage.lease);
        CHECK(memcmp(&original, &fixture.restored, sizeof(original)) == 0);
        CHECK(fixture.calls[UNMOUNT] == 1 && fixture.calls[MOUNT] == 1 && fixture.calls[ATTACH] == 1);
        CHECK(hiby_usb_storage_restore(&storage).success);
        CHECK(fixture.calls[MOUNT] == 1 && fixture.calls[REOPEN] == 1);
    }
}

static void scenario_prepare_faults(void)
{
    const enum operation faults[] = {DETACH, LOCAL, QUIESCE, LEASE, CAPTURE, OVERLAPS,
                                     SYNC, CLOSE_LOCAL, UNMOUNT};
    for (unsigned int index = 0; index < sizeof(faults) / sizeof(faults[0]); ++index)
    {
        struct fixture fixture;
        struct hiby_usb_storage storage;
        fresh(&fixture, &storage, true);
        fixture.fault_operation = (int)faults[index];
        fixture.fault_error = faults[index] == UNMOUNT ? EBUSY : EIO;
        struct hiby_usb_storage_status status = hiby_usb_storage_prepare(&storage);
        CHECK(!status.success && status.error != HIBY_USB_STORAGE_ERROR_NONE);
        CHECK(fixture.calls[ATTACH] == 0 && fixture.mounted && !fixture.exported);
        CHECK(status.system_error == fixture.fault_error);
        if (faults[index] != DETACH && faults[index] != LOCAL)
            CHECK(status.safe_to_resume);
        else
            CHECK(!status.safe_to_resume);
        if (faults[index] == UNMOUNT)
            CHECK(status.error == HIBY_USB_STORAGE_ERROR_UNMOUNT && fixture.calls[MOUNT] == 0);
        fixture.fault_operation = -1;
        CHECK(hiby_usb_storage_restore(&storage).success);
    }
    for (int nth = 2; nth <= 3; ++nth)
    {
        struct fixture fixture;
        struct hiby_usb_storage storage;
        fresh(&fixture, &storage, true);
        fixture.fault_operation = LEASE;
        fixture.fault_nth = nth;
        struct hiby_usb_storage_status status = hiby_usb_storage_prepare(&storage);
        CHECK(!status.success && status.safe_to_resume && !fixture.exported && fixture.mounted);
    }
}

static void scenario_aliases(void)
{
    for (unsigned int aliases = 1; aliases < 5; ++aliases)
    {
        struct fixture fixture;
        struct hiby_usb_storage storage;
        fresh(&fixture, &storage, true);
        fixture.aliases = aliases;
        struct hiby_usb_storage_status status = hiby_usb_storage_prepare(&storage);
        CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_ALIAS);
        CHECK(status.safe_to_resume && fixture.calls[UNMOUNT] == 0 && fixture.calls[ATTACH] == 0);
        CHECK(fixture.mounted && !fixture.exported);
    }
    struct fixture fixture;
    struct hiby_usb_storage storage;
    fresh(&fixture, &storage, true);
    memset(fixture.current.options, 'x', sizeof(fixture.current.options));
    struct hiby_usb_storage_status status = hiby_usb_storage_prepare(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_MOUNT_SNAPSHOT);
    CHECK(status.safe_to_resume && fixture.calls[UNMOUNT] == 0);
}

static void scenario_adversarial(void)
{
    struct fixture fixture;
    struct hiby_usb_storage storage;
    fresh(&fixture, &storage, true);
    fixture.remount_overlap_nth = 2;
    struct hiby_usb_storage_status status = hiby_usb_storage_prepare(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_REMOUNT_DETECTED);
    CHECK(status.safe_to_resume && fixture.calls[ATTACH] == 0 && fixture.mounted);

    fresh(&fixture, &storage, true);
    CHECK(hiby_usb_storage_prepare(&storage).success);
    fixture.mounted = true;
    status = hiby_usb_storage_export(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_REMOUNT_DETECTED);
    CHECK(fixture.calls[ATTACH] == 0 && !fixture.exported && status.safe_to_resume);

    fresh(&fixture, &storage, true);
    CHECK(hiby_usb_storage_prepare(&storage).success);
    fixture.remount_during_attach = true;
    status = hiby_usb_storage_export(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_REMOUNT_DETECTED);
    CHECK(!fixture.exported && status.safe_to_resume);

    fresh(&fixture, &storage, true);
    CHECK(hiby_usb_storage_prepare(&storage).success);
    fixture.invalid_lease_nth = (int)fixture.calls[LEASE] + 1;
    status = hiby_usb_storage_export(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_LEASE);
    CHECK(!status.safe_to_resume && status.state == HIBY_USB_STORAGE_RECOVERY);
    CHECK(status.recovery_error == EPERM);
    CHECK(fixture.calls[ATTACH] == 0 && fixture.calls[MOUNT] == 0 && storage.lease);
}

static void scenario_recovery(void)
{
    const enum operation faults[] = {DETACH, MOUNT, CAPTURE, LOCAL, REOPEN, RELEASE};
    for (unsigned int index = 0; index < sizeof(faults) / sizeof(faults[0]); ++index)
    {
        struct fixture fixture;
        struct hiby_usb_storage storage;
        fresh(&fixture, &storage, true);
        CHECK(hiby_usb_storage_prepare(&storage).success);
        CHECK(hiby_usb_storage_export(&storage).success);
        fixture.fault_operation = (int)faults[index];
        fixture.fault_nth = (int)fixture.calls[faults[index]] + 1;
        struct hiby_usb_storage_status status = hiby_usb_storage_restore(&storage);
        CHECK(!status.success && !status.safe_to_resume && status.state == HIBY_USB_STORAGE_RECOVERY);
        if (faults[index] == DETACH)
            CHECK(fixture.calls[MOUNT] == 0 && fixture.exported);
        fixture.fault_operation = -1;
        CHECK(hiby_usb_storage_restore(&storage).success);
        CHECK(fixture.mounted && !fixture.exported && !fixture.held);
    }
    struct fixture fixture;
    struct hiby_usb_storage storage;
    fresh(&fixture, &storage, true);
    CHECK(hiby_usb_storage_prepare(&storage).success);
    fixture.fault_operation = ATTACH;
    struct hiby_usb_storage_status status = hiby_usb_storage_export(&storage);
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_EXPORT);
    CHECK(status.safe_to_resume && !fixture.exported && fixture.mounted);

    fresh(&fixture, &storage, true);
    CHECK(hiby_usb_storage_prepare(&storage).success);
    fixture.corrupt_mount = true;
    status = hiby_usb_storage_restore(&storage);
    CHECK(!status.success && !status.safe_to_resume && status.error == HIBY_USB_STORAGE_ERROR_RESTORE);
    CHECK(!fixture.exported && fixture.mounted && fixture.held);
}

static void scenario_ordering(void)
{
    struct fixture fixture;
    struct hiby_usb_storage storage;
    fresh(&fixture, &storage, true);
    struct hiby_usb_storage_status status = hiby_usb_storage_export(&storage);
    CHECK(!status.success && fixture.calls[ATTACH] == 0);
    CHECK(hiby_usb_storage_prepare(&storage).success);
    CHECK(!hiby_usb_storage_prepare(&storage).success);
    CHECK(hiby_usb_storage_export(&storage).success);
    CHECK(!hiby_usb_storage_export(&storage).success);
    CHECK(hiby_usb_storage_restore(&storage).success);
    const unsigned int ordered[] = {QUIESCE, CAPTURE, SYNC, CLOSE_LOCAL, UNMOUNT, ATTACH, MOUNT, REOPEN, RELEASE};
    unsigned int next = 0;
    for (unsigned int index = 0; index < fixture.trace_count && next < 9; ++index)
        if (fixture.trace[index] == ordered[next])
            ++next;
    CHECK(next == 9);
}

struct transport
{
    char data[256];
    size_t size, position, chunk;
    unsigned int opens, closes, reads, writes;
    int fault, fault_nth;
    bool short_write, wrong_echo, oversized_read;
};

static int io_open(void *context, const char *path, bool write)
{
    struct transport *transport = context;
    CHECK(strcmp(path, "mock-only") == 0);
    ++transport->opens;
    if (transport->fault == 1 && (int)transport->opens == transport->fault_nth)
        return -EACCES;
    if (!write)
        transport->position = 0;
    return 3;
}

static int io_read(void *context, int descriptor, char *buffer, size_t size)
{
    struct transport *transport = context;
    CHECK(descriptor == 3);
    ++transport->reads;
    if (transport->fault == 2)
        return -EIO;
    if (transport->oversized_read)
        return (int)size + 1;
    size_t count = transport->size - transport->position;
    if (count > size)
        count = size;
    if (transport->chunk && count > transport->chunk)
        count = transport->chunk;
    memcpy(buffer, transport->data + transport->position, count);
    transport->position += count;
    return (int)count;
}

static int io_write(void *context, int descriptor, const char *buffer, size_t size)
{
    struct transport *transport = context;
    CHECK(descriptor == 3);
    ++transport->writes;
    if (transport->fault == 3)
        return -ENOSPC;
    if (!transport->wrong_echo)
    {
        memcpy(transport->data, buffer, size);
        transport->size = size;
    }
    return (int)size - (transport->short_write ? 1 : 0);
}

static int io_close(void *context, int descriptor)
{
    struct transport *transport = context;
    CHECK(descriptor == 3);
    ++transport->closes;
    return transport->fault == 4 && (int)transport->closes == transport->fault_nth ? EIO : 0;
}

static const struct hiby_usb_storage_io io = {io_open, io_read, io_write, io_close};

static void scenario_transport(void)
{
    for (int fault = 0; fault <= 4; ++fault)
        for (int nth = 1; nth <= 2; ++nth)
        {
            struct transport transport = { .fault = fault, .fault_nth = nth, .chunk = 1 };
            int result = hiby_usb_storage_checked_value(&io, &transport, "mock-only", "abc", "abc");
            CHECK((result == 0) == (fault == 0));
            CHECK(transport.opens == transport.closes ||
                  (fault == 1 && transport.opens == transport.closes + 1));
        }
    struct transport transport = { .short_write = true };
    CHECK(hiby_usb_storage_checked_value(&io, &transport, "mock-only", "abc", "abc") == EIO);
    CHECK(transport.closes == 1 && transport.reads == 0);
    memset(&transport, 0, sizeof(transport));
    CHECK(hiby_usb_storage_checked_value(&io, &transport, "mock-only", "\n", "") == 0);
    CHECK(transport.reads == 2 && transport.closes == 2);
    transport.wrong_echo = true;
    transport.size = 3;
    memcpy(transport.data, "ab\0", 3);
    CHECK(hiby_usb_storage_checked_value(&io, &transport, "mock-only", "ab", "ab") == EIO);
    memset(transport.data, 'x', sizeof(transport.data));
    transport.size = sizeof(transport.data);
    CHECK(hiby_usb_storage_checked_value(&io, &transport, "mock-only", "x", "x") == EOVERFLOW);
    transport.oversized_read = true;
    CHECK(hiby_usb_storage_checked_value(&io, &transport, "mock-only", "x", "x") == EOVERFLOW);
    CHECK(hiby_usb_storage_checked_value(&io, &transport, "mock-only", "", "") == EINVAL);
    CHECK(hiby_usb_storage_checked_value(NULL, &transport, "mock-only", "x", "x") == EINVAL);
}

struct native_fixture
{
    char udc[128], lun[128];
    char *selected;
    size_t position;
    bool stream_open, root_mounted, lun_exists;
    unsigned int writes, closes, raw_assignments;
    int fail_close, fail_access;
};
static struct native_fixture native;

static FILE *native_fopen(const char *path, const char *mode)
{
    CHECK(!native.stream_open);
    CHECK(strcmp(mode, "we") == 0 || strcmp(mode, "re") == 0);
    if (strstr(path, "/UDC"))
        native.selected = native.udc;
    else
    {
        CHECK(strstr(path, "/lun.0/file") != NULL);
        native.selected = native.lun;
    }
    native.stream_open = true;
    native.position = 0;
    return (FILE *)&native;
}

static size_t native_fread(void *buffer, size_t size, size_t count, FILE *stream)
{
    CHECK(stream == (FILE *)&native && size == 1 && native.stream_open);
    size_t amount = strlen(native.selected) - native.position;
    if (amount > count)
        amount = count;
    memcpy(buffer, native.selected + native.position, amount);
    native.position += amount;
    return amount;
}

static size_t native_fwrite(const void *buffer, size_t size, size_t count, FILE *stream)
{
    CHECK(stream == (FILE *)&native && size == 1 && native.stream_open);
    ++native.writes;
    if (count >= 5 && memcmp(buffer, "/dev/", 5) == 0)
        ++native.raw_assignments;
    CHECK(count == 1 && memcmp(buffer, "\n", 1) == 0);
    native.selected[0] = 0;
    return count;
}

static int native_fclose(FILE *stream)
{
    CHECK(stream == (FILE *)&native && native.stream_open);
    native.stream_open = false;
    ++native.closes;
    if ((int)native.closes == native.fail_close)
    {
        errno = EIO;
        return EOF;
    }
    return 0;
}

static int native_ferror(FILE *stream) { CHECK(stream == (FILE *)&native); return 0; }

static int native_access(const char *path, int mode)
{
    CHECK(strstr(path, "/sys/") != NULL && mode == 0);
    if (native.fail_access)
    {
        errno = native.fail_access;
        return -1;
    }
    if (strstr(path, "/lun.0/file") && !native.lun_exists)
    {
        errno = ENOENT;
        return -1;
    }
    return 0;
}

static int native_stat(const char *path, struct stat *buffer)
{
    memset(buffer, 0, sizeof(*buffer));
    buffer->st_mode = S_IFDIR;
    if (strcmp(path, "/data/mnt/sd_0") == 0)
        buffer->st_dev = native.root_mounted ? 2 : 1;
    else
        CHECK(strcmp(path, "/data/mnt/sd_0/..") == 0);
    if (!buffer->st_dev)
        buffer->st_dev = 1;
    return 0;
}

static bool native_sysfs_string(const char *path, const char *value)
{
    CHECK(strstr(path, "/sys/") != NULL);
    if (strncmp(value, "/dev/", 5) == 0)
        ++native.raw_assignments;
    return true;
}

static bool native_sysfs_int(const char *path, int value)
{ CHECK(strstr(path, "/sys/") != NULL); (void)value; return true; }

static int native_system(const char *command)
{ CHECK(strstr(command, "/dev/mmcblk") == NULL); return 0; }

#define HIBY_R1 1
#define HAVE_MULTIDRIVE 1
#define F_OK 0
#define PIVOT_ROOT "/data/mnt/sd_0"
#define USB_MODE_MASS_STORAGE 0
#define USB_MODE_CHARGE 1
#define USB_MODE_ADB 2
#define logf(...) ((void)0)
#define fopen(path, mode) native_fopen(path, mode)
#define fread(buffer, size, count, stream) native_fread(buffer, size, count, stream)
#define fwrite(buffer, size, count, stream) native_fwrite(buffer, size, count, stream)
#define fclose(stream) native_fclose(stream)
#define ferror(stream) native_ferror(stream)
#define stat(path, buffer) native_stat(path, buffer)
#define access(path, mode) native_access(path, mode)
#define sysfs_set_string(path, value) native_sysfs_string(path, value)
#define sysfs_set_int(path, value) native_sysfs_int(path, value)
#define system(command) native_system(command)
static int _usb_mode = USB_MODE_MASS_STORAGE;
static bool is_adb_running;
static bool usb_audio_get_active(void) { return false; }
static void disable_adb(void) { }
static void disable_usb_audio(void) { }
void usb_enable(bool on);
int disk_mount_all(void);
int disk_unmount_all(void);
void enable_mass_storage(void);
void disable_mass_storage(void);

NATIVE_GADGET

static void native_fresh(void)
{
    memset(&native, 0, sizeof(native));
    native.root_mounted = true;
    native.lun_exists = true;
    strcpy(native.udc, "13500000.otg_new");
    strcpy(native.lun, "/dev/mmcblk0p1");
    storage_initialized = false;
    storage_stream = NULL;
    _usb_mode = USB_MODE_MASS_STORAGE;
}

static void scenario_native(void)
{
    native_fresh();
    CHECK(disk_unmount_all() == 0);
    struct hiby_usb_storage_status status = hiby_usb_storage_target_status();
    CHECK(!status.success && status.error == HIBY_USB_STORAGE_ERROR_UNVERIFIED);
    CHECK(status.safe_to_resume && !status.configuration_verified);
    CHECK(native.udc[0] == 0 && native.lun[0] == 0 && native.raw_assignments == 0);
    CHECK(disk_mount_all() == 1 && hiby_usb_storage_target_safe_to_resume());
    CHECK(hiby_usb_storage_target_status().error == HIBY_USB_STORAGE_ERROR_UNVERIFIED);
    for (unsigned int iteration = 0; iteration < 12; ++iteration)
    {
        enable_mass_storage();
        usb_enable(true);
        CHECK(hiby_usb_storage_target_status().error == HIBY_USB_STORAGE_ERROR_UNVERIFIED);
        CHECK(native.udc[0] == 0 && native.lun[0] == 0 && native.raw_assignments == 0);
        usb_enable(false);
        CHECK(hiby_usb_storage_target_safe_to_resume());
    }
    disable_mass_storage();
    CHECK(native.raw_assignments == 0 && !native.stream_open);

    native_fresh();
    native.fail_close = 1;
    CHECK(disk_unmount_all() == 0 && !hiby_usb_storage_target_safe_to_resume());
    CHECK(hiby_usb_storage_target_status().error == HIBY_USB_STORAGE_ERROR_DETACH);
    native.fail_close = 0;
    CHECK(hiby_usb_storage_target_restore().success);
    CHECK(hiby_usb_storage_target_status().error == HIBY_USB_STORAGE_ERROR_DETACH);

    native_fresh();
    native.root_mounted = false;
    CHECK(disk_unmount_all() == 0 && !hiby_usb_storage_target_safe_to_resume());
    CHECK(hiby_usb_storage_target_status().error == HIBY_USB_STORAGE_ERROR_LOCAL);

    native_fresh();
    native.lun_exists = false;
    CHECK(disk_unmount_all() == 0 && hiby_usb_storage_target_safe_to_resume());
    native.fail_access = EACCES;
    CHECK(!hiby_usb_storage_target_restore().success && !hiby_usb_storage_target_safe_to_resume());
}

int main(int count, char **arguments)
{
    CHECK(count == 2);
    if (strcmp(arguments[1], "unknown") == 0) scenario_unknown();
    else if (strcmp(arguments[1], "cycles") == 0) scenario_cycles();
    else if (strcmp(arguments[1], "prepare-faults") == 0) scenario_prepare_faults();
    else if (strcmp(arguments[1], "aliases") == 0) scenario_aliases();
    else if (strcmp(arguments[1], "adversarial") == 0) scenario_adversarial();
    else if (strcmp(arguments[1], "recovery") == 0) scenario_recovery();
    else if (strcmp(arguments[1], "ordering") == 0) scenario_ordering();
    else if (strcmp(arguments[1], "transport") == 0) scenario_transport();
    else if (strcmp(arguments[1], "native") == 0) scenario_native();
    else CHECK(false);
    printf("PASS %s %u checks\n", arguments[1], checks);
    return 0;
}
"""


class HibyUsbStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("A native C compiler is required")
        central = project_materials_root(ROOT)
        cls.central = central
        ensure_ignored_directories(central.parent, [central.name])
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = confined_path(central / "r1-usb-safety-20261011" /
                                      (stamp + "-" + uuid.uuid4().hex[:8]), central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.before = cls.hashes()
        cls.commands = []
        cls.outcomes = []
        cls.executables = {}
        gadget = (ROOT / GADGET).read_text(encoding="utf-8")
        start = gadget.index('#include "usb-storage-hiby.h"')
        start = gadget.index("\n", start) + 1
        end = gadget.index("\n#endif\n\n/* Configfs root", start)
        fragment = gadget[start:end]
        fragment += "\n" + "\n".join(function(gadget, name) for name in (
            "usb_enable", "disk_mount_all", "disk_unmount_all", "enable_mass_storage", "disable_mass_storage"))
        cls.harness = cls.workspace / "usb-storage-test.c"
        cls.harness.write_text(HARNESS.replace("NATIVE_GADGET", fragment), encoding="utf-8")
        cls.addClassCleanup(cls.finish)
        print("USB storage mock evidence:", cls.workspace, flush=True)

    @staticmethod
    def hashes():
        return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}

    @classmethod
    def finish(cls):
        after = cls.hashes()
        stable = cls.before == after
        report = {"source_project": str(ROOT), "source_before": cls.before, "source_after": after,
                  "sources_stable": stable, "commands": cls.commands, "tests": cls.outcomes,
                  "passed": stable and all(record["accepted"] for record in cls.commands) and
                            all(record["passed"] for record in cls.outcomes),
                  "syscalls_mocked": True, "hardware_tested": False, "mount_actions": False,
                  "sysfs_writes": False, "native_mass_storage_available": False,
                  "automounter_verified": False, "generic_usb_wiring_tested": False}
        with (cls.workspace / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        if not stable:
            raise AssertionError("Owned USB safety sources changed during validation")

    def run(self, result=None):
        result = result or self.defaultTestResult()
        super().run(result)
        failed = any(test is self for test, unused in result.failures + result.errors)
        skipped = any(test is self for test, unused in result.skipped)
        self.outcomes.append({"name": self.id(), "passed": not failed and not skipped, "skipped": skipped})
        return result

    def execute(self, label, command, directory, *, expected=0):
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=120,
                                env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
        (directory / (label + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
        (directory / (label + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
        accepted = result.returncode != 0 if expected is None else result.returncode == expected
        self.commands.append({"label": label, "argv": command, "cwd": str(directory),
                              "returncode": result.returncode, "expected_returncode": expected,
                              "accepted": accepted,
                              "observable_checks": sum(map(int, re.findall(r"PASS [\w-]+ (\d+) checks", result.stdout))),
                              "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                              "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()})
        self.assertTrue(accepted, result.stdout + result.stderr)
        return result

    def variant(self, label):
        if label in self.executables:
            return self.executables[label]
        directory = self.workspace / label
        directory.mkdir(exist_ok=False)
        windows = label == "windows"
        compiler = ["x86_64-w64-mingw32-gcc"] if windows else self.compiler
        executable = directory / ("usb-test.exe" if windows or os.name == "nt" else "usb-test")
        command = compiler + ["-std=c99" if label == "c99" else "-std=c11", "-O1", "-g",
                              "-Wall", "-Wextra", "-Werror", "-Wshadow", "-Wstrict-prototypes",
                              "-Wmissing-prototypes", "-pedantic-errors", "-pthread",
                              "-I", str(ROOT / Path(HEADER).parent), str(ROOT / ENGINE),
                              str(self.harness), "-o", str(executable)]
        if label == "ubsan":
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        if windows:
            command += ["-static"]
        self.execute("compile", command, directory)
        self.executables[label] = directory, executable
        return directory, executable

    def scenario(self, name):
        variants = ["c99", "c11", "ubsan"]
        if os.environ.get("HIBY_USB_TEST_WINDOWS"):
            variants.append("windows")
        for label in variants:
            with self.subTest(variant=label):
                directory, executable = self.variant(label)
                if label == "windows":
                    path = str(executable)
                    if not path.startswith("/mnt/d/"):
                        self.fail("Windows probe must remain within the central D: workspace")
                    windows_path = "D:\\" + path[len("/mnt/d/"):].replace("/", "\\")
                    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                               "& '" + windows_path.replace("'", "''") + "' '" + name +
                               "'; exit $LASTEXITCODE"]
                else:
                    command = [str(executable), name]
                result = self.execute(name, command, directory)
                self.assertRegex(result.stdout, r"PASS " + re.escape(name) + r" \d+ checks")

    def test_unknown_and_incomplete_configuration_fail_closed(self): self.scenario("unknown")
    def test_verified_mock_cycles_preserve_exact_mount_options(self): self.scenario("cycles")
    def test_prepare_faults_and_busy_unmount_rollback(self): self.scenario("prepare-faults")
    def test_alias_mounts_and_invalid_snapshots(self): self.scenario("aliases")
    def test_adversarial_remount_and_lost_quiescence(self): self.scenario("adversarial")
    def test_detach_remount_reopen_and_release_failure_recovery(self): self.scenario("recovery")
    def test_invalid_ordering_and_transaction_call_sequence(self): self.scenario("ordering")
    def test_transport_readback_short_io_and_close_errors(self): self.scenario("transport")
    def test_actual_r1_gadget_guards_and_sticky_status(self): self.scenario("native")

    def test_other_gadget_targets_keep_existing_lun_path(self):
        gadget = (ROOT / GADGET).read_text(encoding="utf-8")
        self.assertIn("#ifndef HIBY_R1\nstatic void set_mass_storage_lun", gadget)
        self.assertIn("#else\n    set_mass_storage_lun();\n#endif", function(gadget, "enable_mass_storage"))
        for name in ("hiby_set_usb_mode", "enable_adb", "enable_usb_audio"):
            self.assertRegex(function(gadget, name),
                             r"#ifdef HIBY_R1\s+if \(!hiby_usb_storage_target_restore\(\)\.success\)")
        native = gadget[gadget.index("static const struct hiby_usb_storage_operations storage_operations"):]
        self.assertIn("hiby_usb_storage_init(&storage, &storage_operations, NULL, false);", native)
        self.assertNotIn("umount(", native)
        self.assertNotIn("mount(PIVOT_ROOT", native)

    def test_non_r1_gadget_preprocessing_matches_git_baseline(self):
        baseline = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:" + GADGET],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        directory = self.workspace / "legacy-targets"
        directory.mkdir(exist_ok=False)
        sources = {}
        for name, content in (("baseline", baseline.stdout),
                              ("current", (ROOT / GADGET).read_text(encoding="utf-8"))):
            path = directory / (name + ".c")
            path.write_text(re.sub(r"^\s*#include[^\n]*", "", content, flags=re.MULTILINE),
                            encoding="utf-8")
            sources[name] = path
        for target in ("HIBY_R3PROII", "HIDIZS_AP80MAX"):
            outputs = []
            for name, path in sources.items():
                result = self.execute(target + "-" + name, self.compiler + [
                    "-E", "-P", "-x", "c", "-D" + target, "-DHAVE_MULTIDRIVE",
                    "-DHAVE_GENERAL_PURPOSE_LED", str(path)], directory)
                outputs.append(re.findall(r'"(?:\\.|[^"\\])*"|\S+', result.stdout))
            self.assertEqual(outputs[0], outputs[1], target + " gadget behavior changed")

    def test_negative_controls_reject_removed_safety_guards(self):
        source = (ROOT / ENGINE).read_text(encoding="utf-8")
        mutations = (
            ("unverified", "unknown", source.replace(
                "if (!storage->status.configuration_verified)", "if (false)")),
            ("close", "transport", source.replace(
                "if ((size_t)result != length || closed)", "if ((size_t)result != length)")),
            ("mount-race", "adversarial", source[:source.index(
                "struct hiby_usb_storage_status hiby_usb_storage_export(")] + source[source.index(
                "struct hiby_usb_storage_status hiby_usb_storage_export("):].replace(
                    "if (result || count != 0)", "if (result)")),
        )
        for label, scenario, mutated in mutations:
            with self.subTest(mutation=label):
                self.assertNotEqual(source, mutated)
                directory = self.workspace / ("negative-" + label)
                directory.mkdir(exist_ok=False)
                candidate = directory / "mutated.c"
                candidate.write_text(mutated, encoding="utf-8")
                executable = directory / "usb-test"
                command = self.compiler + ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror",
                                          "-pthread", "-I", str(ROOT / Path(HEADER).parent),
                                          str(candidate), str(self.harness), "-o", str(executable)]
                self.execute("compile", command, directory)
                result = self.execute("rejected", [str(executable), scenario], directory, expected=None)
                self.assertIn("Assertion", result.stderr)

    def test_actual_native_r1_translation_units_compile(self):
        compiler = self.central / "toolchains/hiby-r1-20261010/prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        if not compiler.exists() or os.name == "nt":
            self.skipTest("The retained native MIPS compiler is required")
        build = self.central / "build-espeak-hibyr1"
        includes = [build, build / "lang", ROOT / "firmware/target/hosted/hiby/r1",
                    ROOT / "firmware/target/hosted/hiby", ROOT / "firmware/target/hosted",
                    ROOT / "firmware", ROOT / "firmware/export", ROOT / "firmware/drivers",
                    ROOT / "firmware/include", ROOT / "firmware/kernel/include", ROOT / "apps"]
        command = [str(compiler), "-fsyntax-only", "-std=gnu11", "-W", "-Wall", "-Wextra",
                   "-Werror", "-Wundef", "-Wstrict-prototypes", "-march=mips32r2", "-mhard-float",
                   "-mno-mips16", "-fPIC", "-D_GNU_SOURCE=1", "-D_REENTRANT", "-DROCKBOX",
                   "-DMEMORYSIZE=16", "-DHIBY_R1", "-DTARGET_ID=124", "-DAPPLICATION", "-DHAVE_CONFIG_H"]
        for include in includes:
            command.extend(("-I", str(include)))
        for mode, defines in (("app", []), ("bootloader", ["-DBOOTLOADER"])):
            for path in (ENGINE, GADGET):
                self.execute("mips-syntax-" + mode + "-" + Path(path).stem,
                             command + defines + [str(ROOT / path)], self.workspace)


if __name__ == "__main__":
    unittest.main(verbosity=2)
