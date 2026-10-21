#define _GNU_SOURCE 1
#include "power-control-hiby.h"
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/rfkill.h>
#include <net/if.h>
#include <signal.h>
#include <spawn.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum file_kind { FREE, RADIO, NETWORK, DRIVER, MODULE, FUNCTION1, FUNCTION2,
    ATTRIBUTE, BIND, PIPE_READ, PIPE_WRITE, RADIO_DIRECTORY };
struct fixture_file { enum file_kind kind; unsigned int position; const char *attribute;
    int parent; unsigned int identity; };
static struct fixture_file files[64];
static const char *scenario;
static const char *operation;
static bool detached = true;
static bool interface_up;
static bool wlan_blocked = true;
static bool child_active;
static bool child_killed;
static bool allow_late_completion;
static bool actions_active;
static bool attributes_active;
static bool directory_active;
static unsigned int directory_position;
static unsigned int children;
static unsigned int waits;
static unsigned int kills;
static unsigned int pauses;
static unsigned int directory_reads;
static unsigned int opens;
static unsigned int closes;
static unsigned int interface_reads;
static unsigned int char_reads;
static unsigned int rfkill_writes;
static unsigned int binds;
static unsigned int flags_changes;
static unsigned int assertions;
static unsigned int duplicate_calls;
static int inherited_target = -1;
static int inherited_input = -1;
static int queued_target = -1;
static enum file_kind queued_kind;
static const char *queued_interface;
static bool queued_up;
static unsigned char pipe_data[64];
static size_t pipe_size;
static struct dirent directory_entry;

#define CHECK(condition) do { ++assertions; assert(condition); } while (0)

static bool named(const char *name) { return !strcmp(scenario, name); }
static bool prefix(const char *name) { return !strncmp(scenario, name, strlen(name)); }
static int fail(int error) { errno = error; return -1; }
static int file_new(enum file_kind kind)
{
    unsigned int first = kind == BIND && (named("target-nine") || prefix("dup-")) ? 9 : 10;
    for (unsigned int position = first; position < 64; ++position)
        if (files[position].kind == FREE)
        {
            files[position] = (struct fixture_file) { .kind = kind };
            ++opens;
            return position;
        }
    CHECK(false);
    return -1;
}
static struct fixture_file *file_get(int descriptor)
{
    CHECK(descriptor >= 9 && descriptor < 64 && files[descriptor].kind != FREE);
    return &files[descriptor];
}
static bool bluetooth_test(void) { return !strcmp(operation, "bt"); }

int __wrap_open(const char *path, int flags, ...)
{
    CHECK(!strcmp(path, "/dev/rfkill"));
    CHECK((flags & (O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)) ==
        (O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC));
    if (prefix("sysfs-") || named("missing") || (!bluetooth_test() && detached))
        return fail(ENOENT);
    if (named("denied"))
        return fail(EACCES);
    if (named("symlink"))
        return fail(ELOOP);
    return file_new(RADIO);
}
int __wrap___open_2(const char *path, int flags) { return __wrap_open(path, flags); }

int __wrap_openat(int parent, const char *path, int flags, ...)
{
    if (parent == AT_FDCWD)
    {
        CHECK(!bluetooth_test());
        CHECK((flags & (O_DIRECTORY | O_NONBLOCK | O_CLOEXEC)) ==
            (O_DIRECTORY | O_NONBLOCK | O_CLOEXEC));
        enum file_kind kind;
        if (!strcmp(path, "/sys/bus/sdio/drivers/bcmsdh_sdmmc"))
        {
            CHECK(flags & O_NOFOLLOW);
            if (named("missing-driver")) return fail(ENOENT);
            if (named("driver-denied")) return fail(EACCES);
            if (named("open-storm")) return fail(EINTR);
            kind = DRIVER;
        }
        else if (!strcmp(path, "/sys/module/cywdhd"))
        {
            CHECK(flags & O_NOFOLLOW);
            if (named("missing-module")) return fail(ENOENT);
            kind = MODULE;
        }
        else if (!strcmp(path, "/sys/bus/sdio/devices/mmc0:0001:1"))
        {
            CHECK(!(flags & O_NOFOLLOW));
            if (named("missing-function1")) return fail(ENOENT);
            kind = FUNCTION1;
        }
        else
        {
            CHECK(!strcmp(path, "/sys/bus/sdio/devices/mmc0:0001:2"));
            CHECK(!(flags & O_NOFOLLOW));
            if (named("missing-function2")) return fail(ENOENT);
            kind = FUNCTION2;
        }
        int descriptor = file_new(kind);
        files[descriptor].identity = kind;
        return descriptor;
    }
    if (parent == 100)
    {
        CHECK(bluetooth_test() && prefix("sysfs-") && directory_active);
        CHECK(!strncmp(path, "rfkill", 6) && path[6] >= '0' && path[6] <= '2' && !path[7]);
        int descriptor = file_new(RADIO_DIRECTORY);
        files[descriptor].identity = path[6] - '0';
        return descriptor;
    }
    struct fixture_file *directory = file_get(parent);
    if (directory->kind == RADIO_DIRECTORY)
    {
        CHECK(!strcmp(path, "type") || !strcmp(path, "soft") || !strcmp(path, "hard"));
        CHECK((flags & O_ACCMODE) == O_RDONLY && (flags & O_NOFOLLOW));
        CHECK(!strcmp(path, "type") || directory->identity != 2);
        if (named("sysfs-missing-attribute")) return fail(ENOENT);
        int descriptor = file_new(ATTRIBUTE);
        files[descriptor].attribute = path;
        files[descriptor].parent = RADIO_DIRECTORY;
        files[descriptor].identity = directory->identity;
        return descriptor;
    }
    if (!strcmp(path, "module"))
    {
        CHECK(directory->kind == DRIVER);
        int descriptor = file_new(MODULE);
        files[descriptor].identity = named("wrong-module") ? 99 : MODULE;
        return descriptor;
    }
    if (!strcmp(path, "driver"))
    {
        CHECK(directory->kind == FUNCTION1 || directory->kind == FUNCTION2);
        if (directory->kind == FUNCTION2 && detached && !named("already-bound"))
            return fail(named("detach-denied") ? EACCES : ENOENT);
        int descriptor = file_new(DRIVER);
        files[descriptor].identity = named("wrong-driver") ? 99 : DRIVER;
        return descriptor;
    }
    if (!strcmp(path, "bind"))
    {
        CHECK(directory->kind == DRIVER && (flags & O_ACCMODE) == O_WRONLY);
        CHECK((flags & (O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW)) ==
            (O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW));
        if (named("bind-denied")) return fail(EACCES);
        if (named("bind-symlink")) return fail(ELOOP);
        if (named("cancel-before-bind")) hiby_wifi_cancel();
        return file_new(BIND);
    }
    CHECK(directory->kind == FUNCTION1 || directory->kind == FUNCTION2);
    CHECK(!strcmp(path, "vendor") || !strcmp(path, "device") || !strcmp(path, "class"));
    CHECK((flags & (O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW)) ==
        (O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW));
    if (named("attribute-symlink")) return fail(ELOOP);
    int descriptor = file_new(ATTRIBUTE);
    files[descriptor].attribute = path;
    files[descriptor].parent = directory->kind;
    return descriptor;
}
int __wrap___openat_2(int parent, const char *path, int flags)
{ return __wrap_openat(parent, path, flags); }

int __wrap_fstatat(int directory, const char *path, struct stat *status, int flags)
{
    (void)status;
    CHECK(file_get(directory)->kind == FUNCTION2 && !strcmp(path, "driver"));
    CHECK(flags == AT_SYMLINK_NOFOLLOW && detached);
    return fail(ENOENT);
}
int __wrap___fxstatat(int version, int directory, const char *path, struct stat *status, int flags)
{ (void)version; return __wrap_fstatat(directory, path, status, flags); }

int __wrap_fstat(int descriptor, struct stat *status)
{
    struct fixture_file *file = file_get(descriptor);
    if (named("stat-storm")) return fail(EINTR);
    memset(status, 0, sizeof(*status));
    status->st_mode = file->kind == RADIO ? S_IFCHR :
        file->kind == ATTRIBUTE || file->kind == BIND ? S_IFREG : S_IFDIR;
    status->st_dev = 7;
    status->st_ino = file->identity;
    if (named("regular-radio") && file->kind == RADIO) status->st_mode = S_IFREG;
    if (named("nonregular-attribute") && file->kind == ATTRIBUTE) status->st_mode = S_IFIFO;
    if (named("nonregular-bind") && file->kind == BIND) status->st_mode = S_IFCHR;
    return 0;
}
int __wrap___fxstat(int version, int descriptor, struct stat *status)
{ (void)version; return __wrap_fstat(descriptor, status); }
int __wrap_close(int descriptor)
{
    struct fixture_file *file = file_get(descriptor);
    bool attribute = file->kind == ATTRIBUTE;
    file->kind = FREE;
    ++closes;
    return named("attribute-close") && attribute ? fail(EIO) : 0;
}

static const char *attribute_data(struct fixture_file *file)
{
    if (file->parent == RADIO_DIRECTORY)
    {
        if (!strcmp(file->attribute, "type"))
            return file->identity == 2 ? "wlan\n" : "bluetooth\n";
        if (named("sysfs-bad-value")) return "2\n";
        if (!strcmp(file->attribute, "soft"))
            return named("sysfs-unblocked") || named("sysfs-hard") ||
                (named("sysfs-mixed") && file->identity == 1) ? "0\n" : "1\n";
        return named("sysfs-hard") ? "1\n" : "0\n";
    }
    if (named("bad-hex")) return "0x02z0\n";
    if (named("overlong")) return "0x02d0123456789\n";
    if (!strcmp(file->attribute, "vendor")) return named("wrong-vendor") ? "0x024c\n" : "0x02d0\n";
    if (!strcmp(file->attribute, "class")) return named("wrong-class") ? "0x07\n" : "0x00\n";
    if (named("zero-device")) return "0x0000\n";
    if (named("ffff-device")) return "0xffff\n";
    return named("different-device") && file->parent == FUNCTION2 ? "0xa9bf\n" : "0xa9a6\n";
}

ssize_t __wrap_read(int descriptor, void *buffer, size_t capacity)
{
    struct fixture_file *file = file_get(descriptor);
    if (file->kind == ATTRIBUTE)
    {
        if (named("read-storm")) return fail(EINTR);
        const char *data = attribute_data(file);
        size_t count = strlen(data) - file->position;
        if (count > capacity) count = capacity;
        if (named("short-attributes") && count > 1) count = 1;
        memcpy(buffer, data + file->position, count);
        file->position += count;
        return count;
    }
    CHECK(file->kind == RADIO && capacity == RFKILL_EVENT_SIZE_V1);
    ++char_reads;
    unsigned int index = file->position++;
    if (named("read-error") || named("legacy-rfkill-read-error")) return fail(EIO);
    if (named("read-eof")) return 0;
    if (named("read-short")) return 3;
    if (named("read-storm")) return fail(EINTR);
    if (named("empty") || named("none") || (named("deleted") && index > 1) ||
        (!named("endless") && !named("overflow") && index >= (named("mixed") ||
            named("mixed-reasons") ? 3u : 2u)))
        return fail(EAGAIN);
    struct rfkill_event event = { .idx = index, .type = bluetooth_test() ?
        index == 0 ? RFKILL_TYPE_WLAN : RFKILL_TYPE_BLUETOOTH : RFKILL_TYPE_WLAN,
        .op = RFKILL_OP_ADD, .soft = bluetooth_test() ? 1 : wlan_blocked };
    if (named("wlan-only")) event.type = RFKILL_TYPE_WLAN;
    if (named("unblocked")) event.soft = 0;
    if (named("hard")) { event.soft = 0; event.hard = 1; }
    if (named("both")) event.hard = 1;
    if (named("mixed") && index == 2) event.soft = 0;
    if (named("mixed-reasons") && index == 2) { event.soft = 0; event.hard = 1; }
    if (named("deleted")) { event.type = RFKILL_TYPE_BLUETOOTH; event.idx = 1;
        if (index) event.op = RFKILL_OP_DEL; }
    if (named("endless")) { event.idx = 1; event.op = index ? RFKILL_OP_CHANGE : RFKILL_OP_ADD; }
    if (named("invalid-soft")) event.soft = 2;
    if (named("invalid-hard")) event.hard = 2;
    if (named("invalid-type")) event.type = RFKILL_TYPE_ALL;
    if (named("invalid-op")) event.op = RFKILL_OP_CHANGE_ALL;
    if (named("overflow")) event.type = RFKILL_TYPE_BLUETOOTH;
    memcpy(buffer, &event, sizeof(event));
    return sizeof(event);
}
ssize_t __wrap___read_chk(int descriptor, void *buffer, size_t capacity, size_t size)
{ CHECK(capacity <= size); return __wrap_read(descriptor, buffer, capacity); }

ssize_t __wrap_write(int descriptor, const void *buffer, size_t size)
{
    CHECK(file_get(descriptor)->kind == PIPE_WRITE && size <= sizeof(pipe_data));
    if (named("pipe-write-storm")) return fail(EINTR);
    if (named("pipe-write-short")) return size - 1;
    memcpy(pipe_data, buffer, size);
    pipe_size = size;
    return size;
}
int __wrap_pipe2(int descriptors[2], int flags)
{
    CHECK(flags == (O_NONBLOCK | O_CLOEXEC));
    if (named("pipe-failed")) return fail(EMFILE);
    descriptors[0] = file_new(PIPE_READ);
    descriptors[1] = file_new(PIPE_WRITE);
    return 0;
}

static int duplicate_control_target(int descriptor, int operation_code, int minimum)
{
    CHECK(descriptor == 9 && operation_code == F_DUPFD_CLOEXEC && minimum == 10);
    struct fixture_file original = *file_get(descriptor);
    ++duplicate_calls;
    if (named("dup-failed")) return fail(EMFILE);
    if (named("dup-storm") || (named("dup-eintr") && duplicate_calls == 1)) return fail(EINTR);
    int duplicated = file_new(original.kind);
    CHECK(duplicated >= minimum);
    files[duplicated] = original;
    return duplicated;
}

int __wrap_fcntl(int descriptor, int operation_code, ...)
{
    va_list arguments;
    va_start(arguments, operation_code);
    int minimum = va_arg(arguments, int);
    va_end(arguments);
    return duplicate_control_target(descriptor, operation_code, minimum);
}

int __wrap_fcntl64(int descriptor, int operation_code, ...)
{
    va_list arguments;
    va_start(arguments, operation_code);
    int minimum = va_arg(arguments, int);
    va_end(arguments);
    return duplicate_control_target(descriptor, operation_code, minimum);
}
int __wrap_socket(int domain, int type, int protocol)
{
    CHECK(!bluetooth_test() && domain == AF_INET && type == (SOCK_DGRAM | SOCK_CLOEXEC) && !protocol);
    return file_new(NETWORK);
}
int __wrap_ioctl(int descriptor, unsigned long command, ...)
{
    CHECK(file_get(descriptor)->kind == NETWORK && command == SIOCGIFFLAGS);
    va_list arguments;
    va_start(arguments, command);
    struct ifreq *request = va_arg(arguments, struct ifreq *);
    va_end(arguments);
    ++interface_reads;
    if (named("legacy-interface-read-error")) return fail(EACCES);
    CHECK(!strcmp(request->ifr_name, "wlan0") || !strcmp(request->ifr_name, "wlan1"));
    if (detached || !strcmp(request->ifr_name, "wlan1")) return fail(ENODEV);
    request->ifr_flags = IFF_BROADCAST | IFF_MULTICAST | (interface_up ? IFF_UP : 0);
    return 0;
}

DIR *__wrap_opendir(const char *path)
{
    CHECK(!strcmp(path, "/sys/class/rfkill"));
    if (!prefix("sysfs-")) { errno = ENOENT; return NULL; }
    directory_active = true;
    directory_position = 0;
    return (DIR *)&directory_active;
}
struct dirent *__wrap_readdir(DIR *directory)
{
    CHECK(directory == (DIR *)&directory_active && directory_active);
    ++directory_reads;
    if (named("sysfs-read-error")) { errno = EIO; return NULL; }
    if (directory_position == (named("sysfs-empty") ? 0u : 3u)) return NULL;
    snprintf(directory_entry.d_name, sizeof(directory_entry.d_name), "rfkill%u", directory_position++);
    return &directory_entry;
}
int __wrap_closedir(DIR *directory)
{
    CHECK(directory == (DIR *)&directory_active && directory_active);
    directory_active = false;
    return named("sysfs-close-error") ? fail(EIO) : 0;
}
int __wrap_dirfd(DIR *directory)
{ CHECK(directory == (DIR *)&directory_active && directory_active); return 100; }

int __wrap_posix_spawnattr_init(posix_spawnattr_t *attributes)
{
    (void)attributes;
    CHECK(!attributes_active);
    attributes_active = true;
    if (named("cancel-before-spawn"))
        hiby_wifi_cancel();
    return 0;
}
int __wrap_posix_spawnattr_destroy(posix_spawnattr_t *attributes)
{ (void)attributes; CHECK(attributes_active); attributes_active = false; return named("attribute-destroy") ? EIO : 0; }
int __wrap_posix_spawnattr_setflags(posix_spawnattr_t *attributes, short flags)
{ (void)attributes; CHECK(attributes_active && flags == POSIX_SPAWN_SETPGROUP); return 0; }
int __wrap_posix_spawnattr_setpgroup(posix_spawnattr_t *attributes, pid_t group)
{ (void)attributes; CHECK(attributes_active && !group); return 0; }
int __wrap_posix_spawn_file_actions_init(posix_spawn_file_actions_t *actions)
{ (void)actions; CHECK(!actions_active); actions_active = true; inherited_target = inherited_input = -1; return 0; }
int __wrap_posix_spawn_file_actions_destroy(posix_spawn_file_actions_t *actions)
{ (void)actions; CHECK(actions_active); actions_active = false; return named("actions-destroy") ? EIO : 0; }
int __wrap_posix_spawn_file_actions_adddup2(posix_spawn_file_actions_t *actions, int source, int target)
{
    (void)actions; CHECK(actions_active);
    if (target == STDIN_FILENO) { CHECK(file_get(source)->kind == PIPE_READ); inherited_input = source; }
    else if (target == 9) { file_get(source); inherited_target = source; }
    else CHECK(source == STDOUT_FILENO && target == STDERR_FILENO);
    return named("action-failed") ? EBADF : 0;
}
int __wrap_posix_spawn_file_actions_addclose(posix_spawn_file_actions_t *actions, int descriptor)
{ (void)actions; CHECK(actions_active); file_get(descriptor); return 0; }
int __wrap_posix_spawn_file_actions_addopen(posix_spawn_file_actions_t *actions,
    int descriptor, const char *path, int flags, mode_t mode)
{
    (void)actions; CHECK(actions_active && !strcmp(path, "/dev/null") && !mode);
    CHECK(descriptor == STDOUT_FILENO || descriptor == STDIN_FILENO);
    CHECK(flags & O_NONBLOCK); CHECK(flags & O_NOFOLLOW);
    return 0;
}
int __wrap_posix_spawn(pid_t *process, const char *path, const posix_spawn_file_actions_t *actions,
    const posix_spawnattr_t *attributes, char *const arguments[], char *const environment[])
{
    (void)actions; (void)attributes; (void)environment;
    CHECK(!bluetooth_test() && !strcmp(path, "/bin/busybox") && !child_active);
    CHECK(actions_active && attributes_active && !strcmp(arguments[0], path));
    CHECK(!hiby_wifi_settled());
    queued_interface = NULL;
    queued_target = -1;
    if (!strcmp(arguments[1], "dd"))
    {
        CHECK(!strcmp(arguments[2], "of=/proc/self/fd/9") && !strcmp(arguments[3], "bs=64") &&
            !strcmp(arguments[4], "count=1") && !arguments[5]);
        CHECK(inherited_input >= 0 && inherited_target >= 0);
        queued_target = inherited_target;
        queued_kind = file_get(queued_target)->kind;
        CHECK(queued_kind == BIND || queued_kind == RADIO);
        if (queued_kind == BIND) CHECK(pipe_size == 12 && !memcmp(pipe_data, "mmc0:0001:2\n", 12));
        else
        {
            CHECK(pipe_size == RFKILL_EVENT_SIZE_V1);
            const struct rfkill_event *event = (const struct rfkill_event *)pipe_data;
            CHECK(event->type == RFKILL_TYPE_WLAN && event->op == RFKILL_OP_CHANGE_ALL && !event->hard);
        }
    }
    else
    {
        CHECK(!strcmp(arguments[1], "ifconfig") && !strcmp(arguments[2], "wlan0") && !arguments[4]);
        CHECK(!strcmp(arguments[3], "up") || !strcmp(arguments[3], "down"));
        queued_interface = arguments[2];
        queued_up = !strcmp(arguments[3], "up");
    }
    if (named("spawn-failed")) return EAGAIN;
    ++children;
    child_active = true;
    child_killed = false;
    *process = 5000 + children;
    return 0;
}
pid_t __wrap_waitpid(pid_t process, int *status, int flags)
{
    CHECK(flags == WNOHANG && process == (pid_t)(5000 + children));
    ++waits;
    if ((named("cancel") || named("late-bind-cancel")) && waits == 1) hiby_wifi_cancel();
    if (named("wait-storm")) return fail(EINTR);
    if (named("wait-eintr") && waits == 1) return fail(EINTR);
    if (named("cancel") || named("hang") || named("stubborn") || named("kill-failed") || named("sleep-failed"))
        if (!child_killed || named("stubborn") || named("kill-failed")) return 0;
    if (prefix("late-bind-") && !allow_late_completion) return 0;
    CHECK(child_active);
    child_active = false;
    *status = child_killed ? SIGKILL : named("child-failed") ||
        (named("legacy-interface-set-error") && queued_interface) ||
        (named("legacy-rfkill-write-error") && !queued_interface) ? 1 << 8 : 0;
    if (!*status || (prefix("late-bind-") && allow_late_completion))
    {
        if (queued_interface) { ++flags_changes; interface_up = queued_up; }
        else if (queued_kind == BIND) { ++binds; detached = false;
            if (named("cancel-after-bind")) hiby_wifi_cancel(); }
        else { ++rfkill_writes; wlan_blocked = ((struct rfkill_event *)pipe_data)->soft; }
    }
    return process;
}
int __wrap_kill(pid_t process, int signal)
{
    CHECK(process == -(pid_t)(5000 + children) && child_active && signal == SIGKILL);
    ++kills;
    if (named("kill-failed")) return fail(EPERM);
    child_killed = true;
    return 0;
}
int __wrap_clock_nanosleep(clockid_t clock, int flags, const struct timespec *duration,
    struct timespec *remaining)
{
    CHECK(clock == CLOCK_MONOTONIC && !flags && !remaining && !duration->tv_sec &&
        duration->tv_nsec == 50000000);
    ++pauses;
    CHECK(pauses <= 103);
    return named("sleep-failed") ? EIO : 0;
}
void __wrap_sync(void) { CHECK(false); }
int __wrap_reboot(int command) { (void)command; CHECK(false); return -1; }

static void check_files(void)
{
    CHECK(opens == closes && !directory_active && !attributes_active && !actions_active);
    for (unsigned int position = 0; position < 64; ++position) CHECK(files[position].kind == FREE);
}

int main(int count, char **arguments)
{
    CHECK(count == 3);
    operation = arguments[1]; scenario = arguments[2];
    if (bluetooth_test())
    {
        if (named("null")) CHECK(hiby_bluetooth_rfkill_blocked(NULL) == EINVAL);
        else
        {
            bool blocked = true;
            int error = hiby_bluetooth_rfkill_blocked(&blocked);
            bool good = named("blocked") || named("hard") || named("both") || named("unblocked") ||
                named("mixed-reasons") || named("sysfs-blocked") || named("sysfs-unblocked") || named("sysfs-hard");
            if (good) CHECK(!error && blocked == !(named("unblocked") || named("sysfs-unblocked")));
            else
            {
                CHECK(error && blocked);
                if (named("empty") || named("none") || named("wlan-only") || named("deleted") ||
                    named("missing") || named("regular-radio") || named("sysfs-empty")) CHECK(error == ENODEV);
                if (named("mixed") || named("sysfs-mixed")) CHECK(error == EAGAIN);
                if (named("denied")) CHECK(error == EACCES);
            }
        }
        CHECK(!children && !interface_reads && !binds && !rfkill_writes && !kills);
    }
    else
    {
        CHECK(!strcmp(operation, "query") || !strcmp(operation, "disable") ||
            !strcmp(operation, "enable") || !strcmp(operation, "legacy-disable"));
        if (prefix("legacy-"))
        {
            detached = false;
            interface_up = true;
        }
        struct hiby_wifi_result result = !strcmp(operation, "query") ? hiby_wifi_get_state() :
            !strcmp(operation, "legacy-disable") ? hiby_wifi_disable() : hiby_wifi_set_enabled(!strcmp(operation, "enable"));
        bool accepted = named("suspended") || named("short-attributes");
        if (prefix("legacy-"))
        {
            CHECK(!strcmp(operation, "legacy-disable") && result.state == HIBY_WIFI_ERROR);
            CHECK(result.interface_error || result.interface_read_error ||
                result.rfkill_error || result.rfkill_read_error);
        }
        else if (strcmp(operation, "enable"))
        {
            CHECK(!children && !binds && !rfkill_writes && !flags_changes);
            if (accepted) CHECK(result.state == HIBY_WIFI_DRIVER_SUSPENDED && !result.driver_error);
        }
        else if (accepted || named("wait-eintr") || named("target-nine") || named("dup-eintr"))
        {
            CHECK(result.state == HIBY_WIFI_ENABLED && !result.driver_error && !result.rfkill_error && !result.interface_error);
            CHECK(binds == 1 && rfkill_writes == 1 && flags_changes == 1 && children == 3 && !child_active);
            if (named("target-nine")) CHECK(duplicate_calls == 1);
            if (named("dup-eintr")) CHECK(duplicate_calls == 2);
        }
        else
        {
            CHECK(result.state != HIBY_WIFI_ENABLED);
            if (prefix("missing-") || prefix("wrong-") || named("different-device") ||
                named("zero-device") || named("ffff-device") || named("already-bound")) CHECK(!binds);
            if (named("cancel")) CHECK(result.driver_error == ECANCELED && kills == 1);
            if (named("hang") || named("stubborn") || named("kill-failed")) CHECK(result.driver_error == ETIMEDOUT && kills == 1);
            if (named("stubborn") || named("kill-failed") || named("wait-storm"))
            {
                struct hiby_wifi_result repeated = hiby_wifi_set_enabled(true);
                CHECK(repeated.driver_error == EBUSY && children == 1);
            }
            if (named("cancel-before-spawn")) CHECK(result.driver_error == ECANCELED && !children && !binds);
            if (named("cancel-before-bind")) CHECK(result.driver_error == ECANCELED && !children && !binds);
            if (named("dup-failed")) CHECK(result.driver_error == EMFILE && !children && duplicate_calls == 1);
            if (named("dup-storm")) CHECK(result.driver_error == EINTR && !children && duplicate_calls == 8);
            if (named("cancel-after-bind"))
            {
                CHECK(result.driver_error == ECANCELED && children == 1 && binds == 1);
                CHECK(!rfkill_writes && !flags_changes && hiby_wifi_settled());
                CHECK(hiby_wifi_get_state().state == HIBY_WIFI_BLOCKED);
            }
            if (prefix("late-bind-"))
            {
                CHECK(result.driver_error == (named("late-bind-cancel") ? ECANCELED : ETIMEDOUT));
                CHECK(children == 1 && !binds && child_active && !hiby_wifi_settled());
                struct hiby_wifi_result observed = hiby_wifi_get_state();
                CHECK(observed.state == HIBY_WIFI_ERROR && observed.driver_error == EBUSY);
                observed = hiby_wifi_set_enabled(false);
                CHECK(observed.state == HIBY_WIFI_ERROR && observed.driver_error == EBUSY);
                observed = hiby_wifi_disable();
                CHECK(observed.state == HIBY_WIFI_ERROR && observed.driver_error == EBUSY);
                CHECK(!hiby_wifi_settled() && children == 1 && !rfkill_writes && !flags_changes);
                allow_late_completion = true;
                CHECK(hiby_wifi_settled() && !child_active && binds == 1);
                CHECK(hiby_wifi_get_state().state == HIBY_WIFI_BLOCKED);
                CHECK(hiby_wifi_settled() && children == 1 && !rfkill_writes && !flags_changes);
            }
        }
    }
    check_files();
    CHECK(directory_reads <= 256 && pauses <= 103);
    printf("PASS handoff %s %s checks=%u children=%u\n", operation, scenario, assertions, children);
    return 0;
}
