#define __wrap_open handoff_open
#define __wrap___open_2 handoff_open_2
#define __wrap_openat handoff_openat
#define __wrap___openat_2 handoff_openat_2
#define __wrap_read handoff_read
#define __wrap___read_chk handoff_read_chk
#define __wrap_fstatat handoff_fstatat
#define __wrap___fxstatat handoff_fxstatat
#define main handoff_main
#include "hiby_wifi_handoff_fixture.c"
#undef main
#undef __wrap_fstatat
#undef __wrap___fxstatat
#undef __wrap_open
#undef __wrap___open_2
#undef __wrap_openat
#undef __wrap___openat_2
#undef __wrap_read
#undef __wrap___read_chk

static unsigned int missing_module_stats;
static unsigned int missing_driver_stats;

static bool device_case(void) { return prefix("device-"); }
static bool has_module_link(void)
{
    return named("device-existing-cywdhd") || named("device-unknown-cywdhd") ||
        named("device-module-wrong-owner") || named("device-module-directory-missing") ||
        named("device-module-directory-denied");
}

int __wrap_open(const char *path, int flags, ...)
{
    if (!device_case()) return handoff_open(path, flags);
    CHECK(!strcmp(path, "/dev/rfkill"));
    CHECK((flags & (O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)) ==
        (O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
    return file_new(RADIO);
}
int __wrap___open_2(const char *path, int flags) { return __wrap_open(path, flags); }

static int mapped_openat(int parent, const char *path, int flags, const char *mapped)
{
    const char *original = scenario;
    scenario = mapped;
    int result = handoff_openat(parent, path, flags);
    scenario = original;
    return result;
}

int __wrap_openat(int parent, const char *path, int flags, ...)
{
    if (!device_case()) return handoff_openat(parent, path, flags);
    if (parent == AT_FDCWD)
    {
        if (!strcmp(path, "/sys/module/cywdhd"))
        {
            if (named("device-no-module-directory") || named("device-module-directory-missing")) return fail(ENOENT);
            if (named("device-module-directory-denied")) return fail(EACCES);
        }
        if (!strcmp(path, "/sys/bus/sdio/drivers/bcmsdh_sdmmc") && named("device-canonical-driver-symlink"))
        {
            CHECK(flags & O_NOFOLLOW);
            return fail(ELOOP);
        }
        return handoff_openat(parent, path, flags);
    }
    struct fixture_file *directory = file_get(parent);
    if (!strcmp(path, "module"))
    {
        CHECK(directory->kind == DRIVER && (flags & O_DIRECTORY));
        if (named("device-module-link-denied")) return fail(EACCES);
        if (named("device-module-link-io")) return fail(EIO);
        if (named("device-module-link-loop")) return fail(ELOOP);
        if (named("device-module-link-enodev")) return fail(ENODEV);
        if (named("device-module-link-enxio")) return fail(ENXIO);
        if (named("device-module-link-regular")) return fail(ENOTDIR);
        if (!has_module_link()) return fail(ENOENT);
        return named("device-module-wrong-owner") ? mapped_openat(parent, path, flags, "wrong-module") :
            handoff_openat(parent, path, flags);
    }
    if (!strcmp(path, "driver"))
    {
        if (directory->kind == FUNCTION1)
        {
            if (named("device-f1-driver-missing")) return fail(ENOENT);
            if (named("device-f1-driver-wrong")) return mapped_openat(parent, path, flags, "wrong-driver");
        }
        if (directory->kind == FUNCTION2)
        {
            if (named("device-f2-driver-present")) return mapped_openat(parent, path, flags, "already-bound");
            if (named("device-f2-driver-denied")) return fail(EACCES);
        }
    }
    if (named("device-attribute-missing") && !strcmp(path, "vendor")) return fail(ENOENT);
    return handoff_openat(parent, path, flags);
}
int __wrap___openat_2(int parent, const char *path, int flags) { return __wrap_openat(parent, path, flags); }

int __wrap_fstatat(int parent, const char *path, struct stat *status, int flags)
{
    CHECK(flags == AT_SYMLINK_NOFOLLOW);
    struct fixture_file *directory = file_get(parent);
    bool module = directory->kind == DRIVER && !strcmp(path, "module");
    bool driver = directory->kind == FUNCTION2 && !strcmp(path, "driver");
    CHECK(module || driver);
    if (!device_case())
    {
        CHECK(driver);
        return fail(ENOENT);
    }
    unsigned int *calls = module ? &missing_module_stats : &missing_driver_stats;
    ++*calls;
    if ((module && named("device-module-stat-denied")) || (driver && named("device-f2-stat-denied"))) return fail(EACCES);
    if ((module && named("device-module-stat-io")) || (driver && named("device-f2-stat-io"))) return fail(EIO);
    if ((module && named("device-module-stat-storm")) || (driver && named("device-f2-stat-storm"))) return fail(EINTR);
    if (((module && named("device-module-stat-eintr")) || (driver && named("device-f2-stat-eintr"))) && *calls == 1)
        return fail(EINTR);
    if ((module && named("device-module-link-dangling")) || (driver && named("device-f2-driver-dangling")))
    {
        memset(status, 0, sizeof(*status));
        status->st_mode = S_IFLNK;
        return 0;
    }
    return fail(ENOENT);
}
int __wrap___fxstatat(int version, int parent, const char *path, struct stat *status, int flags)
{ (void)version; return __wrap_fstatat(parent, path, status, flags); }

ssize_t __wrap_read(int descriptor, void *buffer, size_t capacity)
{
    if (!device_case()) return handoff_read(descriptor, buffer, capacity);
    struct fixture_file *file = file_get(descriptor);
    if (file->kind == RADIO && detached)
    {
        CHECK(capacity == RFKILL_EVENT_SIZE_V1);
        if (file->position++) return fail(EAGAIN);
        struct rfkill_event event = { .idx = 0, .type = RFKILL_TYPE_BLUETOOTH,
            .op = RFKILL_OP_ADD, .soft = 1, .hard = 0 };
        memcpy(buffer, &event, sizeof(event));
        return sizeof(event);
    }
    if (file->kind == ATTRIBUTE)
    {
        const char *data = NULL;
        if (!strcmp(file->attribute, "vendor"))
            data = named("device-wrong-vendor") ? "0x024c\n" : "0x02d0\n";
        if (!strcmp(file->attribute, "device"))
            data = named("device-unknown-no-module") || named("device-unknown-cywdhd") ? "0xa9bf\n" :
                named("device-zero-id") ? "0x0000\n" : named("device-ffff-id") ? "0xffff\n" :
                named("device-different-f2-id") && file->parent == FUNCTION2 ? "0xa9bf\n" : "0xa9a6\n";
        if (!strcmp(file->attribute, "class"))
            data = named("device-wrong-class") ? "0x07\n" : "0x00\n";
        if (data)
        {
            size_t count = strlen(data) - file->position;
            if (count > capacity) count = capacity;
            memcpy(buffer, data + file->position, count);
            file->position += count;
            return count;
        }
    }
    return handoff_read(descriptor, buffer, capacity);
}
ssize_t __wrap___read_chk(int descriptor, void *buffer, size_t capacity, size_t size)
{ CHECK(capacity <= size); return __wrap_read(descriptor, buffer, capacity); }

int main(int count, char **arguments)
{
    CHECK(count == 3);
    scenario = arguments[2];
    if (!device_case()) return handoff_main(count, arguments);
    operation = arguments[1];
    bool enabled = !strcmp(operation, "enable");
    bool query = !strcmp(operation, "query");
    bool legacy = !strcmp(operation, "legacy-disable");
    CHECK(enabled || query || legacy || !strcmp(operation, "disable"));
    bool bt_blocked = false;
    CHECK(!hiby_bluetooth_rfkill_blocked(&bt_blocked) && bt_blocked);
    struct hiby_wifi_result result = query ? hiby_wifi_get_state() : legacy ? hiby_wifi_disable() :
        hiby_wifi_set_enabled(enabled);
    bool accepted = named("device-no-module-link") || named("device-no-module-directory") ||
        named("device-existing-cywdhd") || named("device-unknown-cywdhd") ||
        named("device-module-stat-eintr") || named("device-f2-stat-eintr");
    if (accepted)
    {
        CHECK(!result.driver_error);
        if (enabled)
            CHECK(result.state == HIBY_WIFI_ENABLED && binds == 1 && flags_changes == 1 && children == 3);
        else
            CHECK(result.state == HIBY_WIFI_DRIVER_SUSPENDED && !binds && !children && !rfkill_writes && !flags_changes);
    }
    else
    {
        CHECK(result.state != HIBY_WIFI_DRIVER_SUSPENDED && result.state != HIBY_WIFI_ENABLED && !binds);
        if (query) CHECK(!children && !rfkill_writes && !flags_changes);
    }
    check_files();
    CHECK(missing_module_stats <= 64 && missing_driver_stats <= 64 && !child_active);
    printf("PASS device %s %s state=%d driver_error=%d binds=%u children=%u\n",
        operation, scenario, result.state, result.driver_error, binds, children);
    return 0;
}
