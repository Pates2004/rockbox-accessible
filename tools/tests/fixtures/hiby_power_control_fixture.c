#define _DEFAULT_SOURCE 1

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
#include <stddef.h>
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

enum descriptor_kind { CLOSED, RADIO_WRITE, RADIO_READ, INTERFACE, RADIO_DIRECTORY };
static enum descriptor_kind descriptors[8];
static const char *scenario;
static unsigned int checks, opens, closes, writes, reads, sockets, ioctls;
static unsigned int stat_calls, spawn_calls, wait_calls, kill_calls, sleep_calls;
static unsigned int init_calls, destroy_calls, flags_calls, group_calls;
static unsigned int sync_calls, reboot_calls, event_position;
static bool radio_blocked, child_active, child_killed, attributes_active;
static bool radio_hard_blocked, requested_enabled, query_only, extended_wifi;
static bool snapshot_blocked[8], snapshot_hard_blocked[8];
static unsigned int interface_sessions;
static short interface_flags[2];
static unsigned long long elapsed_ns;

#define CHECK(value) do { ++checks; assert(value); } while (0)

static bool is_case(const char *name)
{
    return strcmp(scenario, name) == 0;
}

static int failure(int error)
{
    errno = error;
    return -1;
}

static int allocate(enum descriptor_kind kind)
{
    for (int position = 0; position < 8; ++position)
    {
        if (descriptors[position] == CLOSED)
        {
            descriptors[position] = kind;
            ++opens;
            return position;
        }
    }
    CHECK(false);
    return -1;
}

static void descriptor_is(int descriptor, enum descriptor_kind kind)
{
    CHECK(descriptor >= 0 && descriptor < 8);
    CHECK(descriptors[descriptor] == kind);
}

DIR *__wrap_opendir(const char *path)
{
    CHECK(!strcmp(path, "/sys/class/rfkill"));
    errno = ENOENT;
    return NULL;
}

int __wrap_dirfd(DIR *directory)
{
    (void)directory;
    CHECK(false);
    return -1;
}

int __wrap_openat(int directory, const char *path, int flags, ...)
{
    (void)directory;
    (void)path;
    (void)flags;
    CHECK(false);
    return -1;
}

int __wrap___openat_2(int directory, const char *path, int flags)
{
    return __wrap_openat(directory, path, flags);
}

int __wrap_fstatat(int directory, const char *path, struct stat *status, int flags)
{
    (void)directory;
    (void)path;
    (void)status;
    (void)flags;
    CHECK(false);
    return -1;
}

int __wrap___fxstatat(int version, int directory, const char *path, struct stat *status, int flags)
{
    (void)version;
    return __wrap_fstatat(directory, path, status, flags);
}

struct dirent *__wrap_readdir(DIR *directory)
{
    (void)directory;
    CHECK(false);
    return NULL;
}

int __wrap_closedir(DIR *directory)
{
    (void)directory;
    CHECK(false);
    return -1;
}

int __wrap_open(const char *path, int flags, ...)
{
    CHECK(strcmp(path, "/dev/rfkill") == 0);
    CHECK((flags & (O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW)) ==
          (O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW));
    int mode = flags & O_ACCMODE;
    CHECK(mode == O_RDONLY || mode == O_WRONLY);
    CHECK(!query_only || mode == O_RDONLY);
    static unsigned int attempts;
    ++attempts;
    if (is_case("open-eintr") && attempts == 1)
        return failure(EINTR);
    if (is_case("open-interrupt-storm"))
        return failure(EINTR);
    if (is_case("missing"))
        return failure(ENOENT);
    if ((mode == O_RDONLY && (is_case("write-denied-read-missing") ||
                             is_case("read-only-missing"))) ||
        (mode == O_WRONLY && (is_case("write-missing-read-blocked") ||
                             is_case("write-missing-read-unblocked"))))
        return failure(ENOENT);
    if (is_case("denied") || (is_case("read-open-denied") && mode == O_RDONLY))
        return failure(EACCES);
    if (is_case("symlink"))
        return failure(ELOOP);
    if (mode == O_RDONLY)
    {
        event_position = 0;
        for (unsigned int position = 0; position < 8; ++position)
            CHECK(descriptors[position] != RADIO_WRITE);
    }
    int descriptor = allocate(mode == O_RDONLY ? RADIO_READ : RADIO_WRITE);
    snapshot_blocked[descriptor] = radio_blocked;
    snapshot_hard_blocked[descriptor] = radio_hard_blocked;
    return descriptor;
}

int __wrap___open_2(const char *path, int flags)
{
    return __wrap_open(path, flags);
}

int __wrap_fstat(int descriptor, struct stat *status)
{
    CHECK(descriptor >= 0 && descriptor < 8);
    CHECK(descriptors[descriptor] == RADIO_READ || descriptors[descriptor] == RADIO_WRITE);
    ++stat_calls;
    if (is_case("fstat-eintr") && stat_calls == 1)
        return failure(EINTR);
    if (is_case("fstat-interrupt-storm"))
        return failure(EINTR);
    if (is_case("fstat-failure"))
        return failure(EIO);
    memset(status, 0, sizeof(*status));
    status->st_mode = is_case("regular") ? S_IFREG : S_IFCHR;
    return 0;
}

int __wrap___fxstat(int version, int descriptor, struct stat *status)
{
    (void)version;
    return __wrap_fstat(descriptor, status);
}

int __wrap_close(int descriptor)
{
    CHECK(descriptor >= 0 && descriptor < 8);
    CHECK(descriptors[descriptor] != CLOSED);
    enum descriptor_kind kind = descriptors[descriptor];
    descriptors[descriptor] = CLOSED;
    ++closes;
    if ((is_case("read-close-failure") && kind == RADIO_READ) ||
        (is_case("write-close-failure") && kind == RADIO_WRITE) ||
        (is_case("interface-close-failure") && kind == INTERFACE))
        return failure(EIO);
    return is_case("close-eintr") ? failure(EINTR) : 0;
}

ssize_t __wrap_write(int descriptor, const void *buffer, size_t size)
{
    descriptor_is(descriptor, RADIO_WRITE);
    CHECK(!query_only);
    CHECK(size == RFKILL_EVENT_SIZE_V1);
    const struct rfkill_event *event = buffer;
    CHECK(event->idx == 0 && event->type == RFKILL_TYPE_WLAN);
    CHECK(event->op == RFKILL_OP_CHANGE_ALL &&
          event->soft == !requested_enabled && event->hard == 0);
    ++writes;
    if (is_case("write-eintr") && writes == 1)
        return failure(EINTR);
    if (is_case("write-interrupt-storm"))
        return failure(EINTR);
    if (is_case("write-denied") || is_case("already-blocked-write-denied") ||
        is_case("already-enabled-write-denied") || is_case("write-error-read-error") ||
        is_case("write-denied-read-missing"))
        return failure(EPERM);
    if (is_case("write-short"))
        return RFKILL_EVENT_SIZE_V1 - 1;
    if (is_case("write-zero"))
        return 0;
    if (extended_wifi)
    {
        if (!is_case("stale-blocked") && !is_case("stale-unblocked") &&
            !is_case("hard-and-soft"))
            radio_blocked = !requested_enabled;
    }
    else
        radio_blocked = !is_case("unblocked") && !is_case("hard-only");
    return RFKILL_EVENT_SIZE_V1;
}

static ssize_t read_control_event(int descriptor, void *buffer)
{
    if (is_case("no-radio"))
        return failure(EAGAIN);
    unsigned int total = is_case("bt-events") ? 3 :
        is_case("mixed-radios") || is_case("hard-clears") ||
        is_case("hard-appears") || is_case("changed-state") ||
        is_case("deleted-radio") ? 2 : 1;
    if (event_position >= total)
        return failure(EAGAIN);
    struct rfkill_event event =
    {
        .idx = 10,
        .type = RFKILL_TYPE_WLAN,
        .op = RFKILL_OP_ADD,
        .soft = snapshot_blocked[descriptor],
        .hard = snapshot_hard_blocked[descriptor]
    };
    if (is_case("bt-only") || (is_case("bt-events") && event_position != 1))
    {
        event.type = RFKILL_TYPE_BLUETOOTH;
        event.soft = event_position != 0;
        event.hard = event_position == 0;
        event.op = event_position == 2 ? RFKILL_OP_CHANGE : RFKILL_OP_ADD;
    }
    else if (is_case("bt-events"))
        event.idx = 11;
    if (is_case("mixed-radios"))
    {
        event.idx += event_position;
        event.soft = event_position != 0;
    }
    if (is_case("hard-clears") || is_case("hard-appears") ||
        is_case("changed-state") || is_case("deleted-radio"))
    {
        if (event_position == 1)
            event.op = is_case("deleted-radio") ? RFKILL_OP_DEL : RFKILL_OP_CHANGE;
        if (is_case("hard-clears"))
            event.hard = event_position == 0;
        if (is_case("hard-appears"))
            event.hard = event_position != 0;
        if (is_case("changed-state"))
            event.soft = event_position == 0;
    }
    if (is_case("invalid"))
        event.op = RFKILL_OP_CHANGE_ALL;
    if (is_case("invalid-soft"))
        event.soft = 2;
    if (is_case("invalid-hard"))
        event.hard = 2;
    if (is_case("invalid-type"))
        event.type = RFKILL_TYPE_ALL;
    if (is_case("change-missing"))
        event.op = RFKILL_OP_CHANGE;
    memcpy(buffer, &event, sizeof(event));
    ++event_position;
    return sizeof(event);
}

ssize_t __wrap_read(int descriptor, void *buffer, size_t size)
{
    descriptor_is(descriptor, RADIO_READ);
    CHECK(size == RFKILL_EVENT_SIZE_V1);
    ++reads;
    if (is_case("read-eintr") && reads == 1)
        return failure(EINTR);
    if (is_case("read-interrupt-storm"))
        return failure(EINTR);
    if (is_case("read-short"))
        return RFKILL_EVENT_SIZE_V1 - 1;
    if (is_case("read-zero"))
        return 0;
    if (is_case("read-error") || is_case("write-error-read-error"))
        return failure(EIO);
    if (extended_wifi && !is_case("endless") && !is_case("overflow"))
        return read_control_event(descriptor, buffer);
    if (is_case("no-radio") ||
        (is_case("bt-only") && event_position == 1))
        return failure(EAGAIN);

    unsigned int total = is_case("overflow") ? 65 :
        is_case("multi-radio") ? 3 : is_case("changes") ? 5 :
        is_case("transient-no-wlan") ? 2 : 1;
    if (!is_case("endless") && event_position >= total)
        return failure(EAGAIN);
    struct rfkill_event event =
    {
        .idx = event_position + 10,
        .type = is_case("bt-only") || is_case("endless") ?
            RFKILL_TYPE_BLUETOOTH : RFKILL_TYPE_WLAN,
        .op = RFKILL_OP_ADD,
        .soft = snapshot_blocked[descriptor],
        .hard = is_case("hard-only")
    };
    if (is_case("invalid"))
        event.op = RFKILL_OP_CHANGE_ALL;
    if (is_case("invalid-soft"))
        event.soft = 2;
    if (is_case("invalid-type"))
        event.type = RFKILL_TYPE_ALL;
    if (is_case("change-missing"))
        event.op = RFKILL_OP_CHANGE;
    if (is_case("multi-radio") && event_position == 2)
        event.type = RFKILL_TYPE_BLUETOOTH;
    if (is_case("changes"))
    {
        event.idx = event_position < 3 ? 10 : 11;
        if (event_position == 1)
            event.op = RFKILL_OP_CHANGE;
        if (event_position == 2 || event_position == 4)
            event.op = RFKILL_OP_DEL;
    }
    if (is_case("transient-no-wlan") && event_position == 1)
    {
        event.idx = 10;
        event.op = RFKILL_OP_DEL;
    }
    memcpy(buffer, &event, sizeof(event));
    ++event_position;
    return sizeof(event);
}

ssize_t __wrap___read_chk(int descriptor, void *buffer, size_t size, size_t capacity)
{
    CHECK(size <= capacity);
    return __wrap_read(descriptor, buffer, size);
}

int __wrap_socket(int family, int type, int protocol)
{
    CHECK(family == AF_INET && type == (SOCK_DGRAM | SOCK_CLOEXEC) && protocol == 0);
    ++sockets;
    if (is_case("socket-eintr") && sockets == 1)
        return failure(EINTR);
    if (is_case("socket-interrupt-storm"))
        return failure(EINTR);
    if (is_case("socket-failure"))
        return failure(EPERM);
    ++interface_sessions;
    return allocate(INTERFACE);
}

int __wrap_ioctl(int descriptor, unsigned long operation, ...)
{
    descriptor_is(descriptor, INTERFACE);
    CHECK(operation == SIOCGIFFLAGS || operation == SIOCSIFFLAGS);
    CHECK(!query_only || operation == SIOCGIFFLAGS);
    va_list arguments;
    va_start(arguments, operation);
    struct ifreq *request = va_arg(arguments, struct ifreq *);
    va_end(arguments);
    CHECK(strcmp(request->ifr_name, "wlan0") == 0 || strcmp(request->ifr_name, "wlan1") == 0);
    unsigned int interface = strcmp(request->ifr_name, "wlan1") == 0;
    bool observation = query_only || interface_sessions > 1;
    ++ioctls;
    if (is_case("ioctl-eintr") && ioctls == 1)
        return failure(EINTR);
    if (is_case("ioctl-interrupt-storm"))
        return failure(EINTR);
    if (is_case("interface-missing") ||
        (is_case("interface-late-appears") && !observation) ||
        (is_case("interface-disappears") && observation) ||
        (interface == 1 && !is_case("two-interfaces") && !is_case("mixed-interfaces")))
        return failure(ENODEV);
    if (is_case("interface-denied"))
        return failure(EPERM);
    if ((is_case("interface-set-failure") || is_case("interface-set-and-read-failure")) &&
        operation == SIOCSIFFLAGS)
        return failure(EACCES);
    if ((is_case("interface-readback-failure") || is_case("interface-set-and-read-failure")) &&
        observation && interface == 0)
        return failure(EIO);
    if (operation == SIOCGIFFLAGS)
        request->ifr_flags = interface_flags[interface];
    else
    {
        short expected = requested_enabled ? interface_flags[interface] | IFF_UP :
                                            interface_flags[interface] & ~IFF_UP;
        CHECK(request->ifr_flags == expected);
        if (!is_case("interface-stuck") && !is_case("stale-interface"))
            interface_flags[interface] = request->ifr_flags;
    }
    return 0;
}

int __wrap_posix_spawnattr_init(posix_spawnattr_t *attributes)
{
    (void)attributes;
    ++init_calls;
    CHECK(!attributes_active);
    if (is_case("attribute-init"))
        return ENOMEM;
    attributes_active = true;
    return 0;
}

int __wrap_posix_spawnattr_setflags(posix_spawnattr_t *attributes, short flags)
{
    (void)attributes;
    ++flags_calls;
    CHECK(attributes_active && flags == POSIX_SPAWN_SETPGROUP);
    return is_case("attribute-flags") ? EINVAL : 0;
}

int __wrap_posix_spawnattr_setpgroup(posix_spawnattr_t *attributes, pid_t group)
{
    (void)attributes;
    ++group_calls;
    CHECK(attributes_active && group == 0);
    return is_case("attribute-group") ? EINVAL : 0;
}

int __wrap_posix_spawnattr_destroy(posix_spawnattr_t *attributes)
{
    (void)attributes;
    ++destroy_calls;
    CHECK(attributes_active);
    attributes_active = false;
    return is_case("attribute-destroy") ? EINVAL : 0;
}

int __wrap_posix_spawn(pid_t *process, const char *path,
                       const posix_spawn_file_actions_t *actions,
                       const posix_spawnattr_t *attributes,
                       char *const arguments[], char *const environment[])
{
    CHECK(strcmp(path, "/sbin/poweroff") == 0);
    CHECK(actions == NULL && attributes != NULL && environment != NULL);
    CHECK(strcmp(arguments[0], path) == 0 && arguments[1] == NULL);
    CHECK(attributes_active && !child_active && sync_calls != 0);
    ++spawn_calls;
    if (is_case("spawn-failure"))
        return ENOENT;
    if (is_case("spawn-badpid"))
    {
        *process = 0;
        return 0;
    }
    *process = 42;
    child_active = true;
    return 0;
}

pid_t __wrap_waitpid(pid_t process, int *status, int options)
{
    CHECK(process == 42 && options == WNOHANG && child_active);
    ++wait_calls;
    if (is_case("wait-eintr") && wait_calls == 1)
        return failure(EINTR);
    if (is_case("wait-interrupt-storm"))
        return failure(EINTR);
    if (is_case("wait-echild"))
    {
        child_active = false;
        return failure(ECHILD);
    }
    bool hung = is_case("hang") || is_case("stubborn") || is_case("kill-failure") ||
        is_case("kill-eintr") || is_case("kill-interrupt-storm") ||
        is_case("sleep-failure-hang");
    if (hung && (!child_killed || is_case("stubborn")))
        return 0;
    child_active = false;
    *status = is_case("normal-failed") ? 1 << 8 :
        is_case("child-signal") ? SIGSEGV : child_killed ? SIGKILL : 0;
    return process;
}

int __wrap_kill(pid_t process, int signal)
{
    CHECK(process == -42 && signal == SIGKILL && child_active);
    ++kill_calls;
    if (is_case("kill-eintr") && kill_calls == 1)
        return failure(EINTR);
    if (is_case("kill-interrupt-storm"))
        return failure(EINTR);
    if (is_case("kill-failure"))
        return failure(EPERM);
    child_killed = true;
    return 0;
}

int __wrap_clock_nanosleep(clockid_t clock, int flags,
                           const struct timespec *requested, struct timespec *remaining)
{
    CHECK(clock == CLOCK_MONOTONIC && flags == 0);
    CHECK(requested->tv_sec >= 0 && requested->tv_sec <= 1);
    CHECK(requested->tv_nsec >= 0 && requested->tv_nsec < 1000000000);
    ++sleep_calls;
    unsigned long long duration = (unsigned long long)requested->tv_sec * 1000000000 +
        requested->tv_nsec;
    if (is_case("sleep-eintr") && sleep_calls == 1)
    {
        elapsed_ns += 250000000;
        remaining->tv_sec = 0;
        remaining->tv_nsec = 750000000;
        return EINTR;
    }
    if (is_case("sleep-interrupt-storm") || is_case("sleep-invalid"))
    {
        *remaining = *requested;
        if (is_case("sleep-invalid"))
            remaining->tv_sec = -1;
        return EINTR;
    }
    if (is_case("sleep-failure") || is_case("sleep-failure-hang"))
        return EINVAL;
    elapsed_ns += duration;
    return 0;
}

void __wrap_sync(void)
{
    ++sync_calls;
}

int __wrap_reboot(int operation)
{
    CHECK(operation == RB_POWER_OFF && sync_calls >= 2 && !attributes_active);
    ++reboot_calls;
    if (is_case("reboot-eintr") && reboot_calls == 1)
        return failure(EINTR);
    if (is_case("reboot-interrupt-storm"))
        return failure(EINTR);
    return is_case("reboot-returned-success") ? 0 : failure(EPERM);
}

static void no_descriptors(void)
{
    for (unsigned int position = 0; position < 8; ++position)
        CHECK(descriptors[position] == CLOSED);
    CHECK(opens == closes);
}

static void test_wifi(void)
{
    interface_flags[0] = IFF_UP | IFF_BROADCAST | IFF_MULTICAST;
    if (is_case("already-down"))
        interface_flags[0] &= ~IFF_UP;
    interface_flags[1] = interface_flags[0];
    struct hiby_wifi_result result = hiby_wifi_disable();
    static bool reported;
    if (!reported)
    {
        printf("WIFI state=%d radios=%u down=%u rferror=%d iferror=%d writes=%u reads=%u opens=%u closes=%u\n",
               result.state, result.wlan_radios, result.interfaces_down, result.rfkill_error,
               result.interface_error, writes, reads, opens, closes);
        fflush(stdout);
        reported = true;
    }
    no_descriptors();
    CHECK(spawn_calls == 0 && reboot_calls == 0 && kill_calls == 0 && sync_calls == 0);
    CHECK(writes <= 8 && reads <= 8 * 256 && sockets <= 16 && ioctls <= 8 * 6);
    if (is_case("missing") || is_case("regular") || is_case("read-only-missing"))
    {
        CHECK(result.state == HIBY_WIFI_INTERFACE_DOWN);
        CHECK(result.rfkill_error == (is_case("regular") ? ENODEV : ENOENT));
    }
    else if (is_case("no-radio") || is_case("bt-only") || is_case("changes") ||
             is_case("transient-no-wlan"))
        CHECK(result.state == HIBY_WIFI_INTERFACE_DOWN && result.wlan_radios == 0);
    else if (is_case("unblocked") || is_case("hard-only") || is_case("write-missing-read-unblocked"))
        CHECK(result.state == HIBY_WIFI_UNCONFIRMED && result.wlan_radios == 1);
    else if (is_case("denied") || is_case("read-open-denied") || is_case("symlink") ||
             is_case("fstat-failure") || is_case("read-short") || is_case("read-zero") ||
             is_case("read-error") || is_case("endless") || is_case("overflow") ||
             is_case("invalid") || is_case("invalid-soft") || is_case("invalid-type") ||
             is_case("change-missing") || is_case("read-interrupt-storm") ||
             is_case("open-interrupt-storm") || is_case("fstat-interrupt-storm") ||
             is_case("close-eintr") || is_case("write-denied") || is_case("write-short") ||
             is_case("write-zero") || is_case("write-interrupt-storm") ||
             is_case("write-denied-read-missing"))
        CHECK(result.state == HIBY_WIFI_ERROR && result.rfkill_error != 0);
    else
        CHECK(result.state == HIBY_WIFI_BLOCKED &&
              result.wlan_radios == (is_case("multi-radio") ? 2u : 1u));

    if (is_case("interface-denied") || is_case("interface-stuck") ||
        is_case("socket-failure") || is_case("socket-interrupt-storm") ||
        is_case("ioctl-interrupt-storm") || is_case("interface-set-failure") ||
        is_case("interface-readback-failure"))
        CHECK(result.interface_error != 0 && result.interfaces_down == 0);
    else if (is_case("interface-missing"))
        CHECK(result.interface_error == 0 && result.interfaces_down == 0);
    else
        CHECK(result.interfaces_down == (is_case("two-interfaces") ? 2u : 1u));
    if (is_case("write-short") || is_case("write-zero"))
        CHECK(writes == 1);
    if (is_case("read-short") || is_case("read-zero"))
        CHECK(reads == 1);
    if (is_case("already-blocked-write-denied"))
        CHECK(result.state == HIBY_WIFI_BLOCKED && result.rfkill_error == EPERM);
}

static enum hiby_wifi_state expected_control_state(void)
{
    static const struct
    {
        const char *name;
        enum hiby_wifi_state enabled;
        enum hiby_wifi_state disabled;
        enum hiby_wifi_state queried;
    } expectations[] =
    {
        { "missing", HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_INTERFACE_DOWN, HIBY_WIFI_UNCONFIRMED },
        { "regular", HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_INTERFACE_DOWN, HIBY_WIFI_UNCONFIRMED },
        { "read-only-missing", HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_INTERFACE_DOWN, HIBY_WIFI_UNCONFIRMED },
        { "no-radio", HIBY_WIFI_NO_RADIO, HIBY_WIFI_INTERFACE_DOWN, HIBY_WIFI_NO_RADIO },
        { "bt-only", HIBY_WIFI_NO_RADIO, HIBY_WIFI_INTERFACE_DOWN, HIBY_WIFI_NO_RADIO },
        { "deleted-radio", HIBY_WIFI_NO_RADIO, HIBY_WIFI_INTERFACE_DOWN, HIBY_WIFI_NO_RADIO },
        { "hard-blocked", HIBY_WIFI_HARD_BLOCKED, HIBY_WIFI_HARD_BLOCKED, HIBY_WIFI_HARD_BLOCKED },
        { "hard-and-soft", HIBY_WIFI_HARD_BLOCKED, HIBY_WIFI_HARD_BLOCKED, HIBY_WIFI_HARD_BLOCKED },
        { "hard-appears", HIBY_WIFI_HARD_BLOCKED, HIBY_WIFI_HARD_BLOCKED, HIBY_WIFI_HARD_BLOCKED },
        { "stale-blocked", HIBY_WIFI_BLOCKED, HIBY_WIFI_BLOCKED, HIBY_WIFI_BLOCKED },
        { "stale-unblocked", HIBY_WIFI_ENABLED, HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_ENABLED },
        { "blocked", HIBY_WIFI_ENABLED, HIBY_WIFI_BLOCKED, HIBY_WIFI_BLOCKED },
        { "changed-state", HIBY_WIFI_ENABLED, HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_ENABLED },
        { "mixed-radios", HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_UNCONFIRMED },
        { "mixed-interfaces", HIBY_WIFI_ENABLED, HIBY_WIFI_BLOCKED, HIBY_WIFI_UNCONFIRMED },
        { "interface-down", HIBY_WIFI_ENABLED, HIBY_WIFI_BLOCKED, HIBY_WIFI_UNCONFIRMED },
        { "interface-missing", HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_BLOCKED, HIBY_WIFI_UNCONFIRMED },
        { "interface-disappears", HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_BLOCKED, HIBY_WIFI_UNCONFIRMED },
        { "interface-late-appears", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_UNCONFIRMED },
        { "stale-interface", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ENABLED },
        { "interface-stuck", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ENABLED },
        { "interface-denied", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR },
        { "interface-set-failure", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ENABLED },
        { "interface-readback-failure", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR },
        { "interface-set-and-read-failure", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR },
        { "interface-close-failure", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR },
        { "socket-failure", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR },
        { "socket-interrupt-storm", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR },
        { "ioctl-interrupt-storm", HIBY_WIFI_ERROR, HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR },
        { "write-denied", HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR, HIBY_WIFI_ENABLED },
        { "write-short", HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR, HIBY_WIFI_ENABLED },
        { "write-zero", HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR, HIBY_WIFI_ENABLED },
        { "write-interrupt-storm", HIBY_WIFI_BLOCKED, HIBY_WIFI_ERROR, HIBY_WIFI_ENABLED },
        { "write-denied-read-missing", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_UNCONFIRMED },
        { "write-missing-read-blocked", HIBY_WIFI_BLOCKED, HIBY_WIFI_BLOCKED, HIBY_WIFI_BLOCKED },
        { "write-missing-read-unblocked", HIBY_WIFI_ENABLED, HIBY_WIFI_UNCONFIRMED, HIBY_WIFI_ENABLED },
        { "already-enabled-write-denied", HIBY_WIFI_ENABLED, HIBY_WIFI_ERROR, HIBY_WIFI_ENABLED },
        { "already-blocked-write-denied", HIBY_WIFI_BLOCKED, HIBY_WIFI_BLOCKED, HIBY_WIFI_BLOCKED },
        { "denied", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "read-open-denied", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "symlink", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "fstat-failure", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "read-short", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "read-zero", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "read-error", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "write-error-read-error", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "endless", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "overflow", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "invalid", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "invalid-soft", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "invalid-hard", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "invalid-type", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "change-missing", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "read-interrupt-storm", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "open-interrupt-storm", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "fstat-interrupt-storm", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "close-eintr", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR },
        { "read-close-failure", HIBY_WIFI_ERROR, HIBY_WIFI_ERROR, HIBY_WIFI_ERROR }
    };
    for (unsigned int position = 0; position < sizeof(expectations) / sizeof(expectations[0]); ++position)
        if (is_case(expectations[position].name))
            return query_only ? expectations[position].queried : requested_enabled ?
                expectations[position].enabled : expectations[position].disabled;
    return requested_enabled || query_only ? HIBY_WIFI_ENABLED : HIBY_WIFI_BLOCKED;
}

static void test_wifi_control(void)
{
    CHECK(HIBY_WIFI_BLOCKED == 0 && HIBY_WIFI_NO_RADIO == 1 &&
          HIBY_WIFI_UNCONFIRMED == 2 && HIBY_WIFI_ERROR == 3);
    CHECK(offsetof(struct hiby_wifi_result, interfaces_up) >
          offsetof(struct hiby_wifi_result, interface_error));
    short other_flags = IFF_BROADCAST | IFF_MULTICAST;
    interface_flags[0] = other_flags;
    if (!requested_enabled || query_only || is_case("already-enabled") ||
        is_case("already-enabled-write-denied"))
        interface_flags[0] |= IFF_UP;
    if (is_case("interface-down"))
        interface_flags[0] &= ~IFF_UP;
    interface_flags[1] = interface_flags[0];
    if (is_case("mixed-interfaces"))
        interface_flags[1] ^= IFF_UP;
    short initial_flags[2] = { interface_flags[0], interface_flags[1] };
    bool initial_soft = radio_blocked;
    bool initial_hard = radio_hard_blocked;
    struct hiby_wifi_result result = query_only ? hiby_wifi_get_state() :
        hiby_wifi_set_enabled(requested_enabled);
    static bool reported;
    if (!reported)
    {
        printf("CONTROL state=%d radios=%u soft=%u hard=%u present=%u up=%u down=%u "
               "rferror=%d iferror=%d rfread=%d ifread=%d\n", result.state,
               result.wlan_radios, result.soft_blocked_radios, result.hard_blocked_radios,
               result.interfaces_present, result.interfaces_up, result.interfaces_down,
               result.rfkill_error, result.interface_error, result.rfkill_read_error,
               result.interface_read_error);
        fflush(stdout);
        reported = true;
    }
    CHECK(result.state == expected_control_state());
    CHECK(result.interfaces_up + result.interfaces_down == result.interfaces_present);
    CHECK((interface_flags[0] & ~IFF_UP) == other_flags);
    CHECK((interface_flags[1] & ~IFF_UP) == other_flags);
    CHECK(spawn_calls == 0 && reboot_calls == 0 && kill_calls == 0 && sync_calls == 0);
    CHECK(writes <= 8 && reads <= 8 * 256 && sockets <= 16 && ioctls <= 8 * 6);
    if (query_only)
    {
        CHECK(writes == 0 && radio_blocked == initial_soft && radio_hard_blocked == initial_hard);
        CHECK(interface_flags[0] == initial_flags[0] && interface_flags[1] == initial_flags[1]);
    }
    if (result.state == HIBY_WIFI_ENABLED)
        CHECK(result.wlan_radios > 0 && result.soft_blocked_radios == 0 &&
              result.hard_blocked_radios == 0 && result.rfkill_read_error == 0 &&
              result.interface_read_error == 0 && result.interfaces_present > 0 &&
              result.interfaces_up == result.interfaces_present);
    if (result.state == HIBY_WIFI_HARD_BLOCKED)
        CHECK(result.hard_blocked_radios > 0 && result.rfkill_read_error == 0);
    if (result.state == HIBY_WIFI_NO_RADIO)
        CHECK(result.wlan_radios == 0 && result.rfkill_read_error == 0);
    if (is_case("interface-missing") || is_case("interface-disappears"))
        CHECK(result.interfaces_present == 0 && result.interface_read_error == 0);
    if (is_case("mixed-radios"))
        CHECK(result.wlan_radios == 2 && result.soft_blocked_radios == 1);
    if (is_case("bt-events"))
        CHECK(result.wlan_radios == 1 && result.hard_blocked_radios == 0);
    if (is_case("hard-clears"))
        CHECK(result.hard_blocked_radios == 0);
    if (is_case("write-short") || is_case("write-zero"))
        CHECK(writes == 1 && result.rfkill_error == EIO);
    if (is_case("write-denied") || is_case("already-enabled-write-denied") ||
        is_case("already-blocked-write-denied"))
        CHECK(result.rfkill_error == EPERM && result.rfkill_read_error == 0);
    if (is_case("read-short") || is_case("read-zero"))
        CHECK(reads == 1 && result.rfkill_read_error == EIO && result.wlan_radios == 0);
    if (is_case("write-error-read-error"))
        CHECK(result.rfkill_error == EPERM && result.rfkill_read_error == EIO);
    if (is_case("interface-set-and-read-failure"))
        CHECK(result.interface_error == EACCES && result.interface_read_error == EIO);
    if (is_case("stale-interface") || is_case("interface-stuck") ||
        is_case("interface-late-appears"))
        CHECK(query_only || result.interface_error == EBUSY);
    if (is_case("read-close-failure"))
        CHECK(result.rfkill_read_error == EIO && result.wlan_radios == 0);
    if (is_case("refresh"))
    {
        radio_blocked = true;
        CHECK(hiby_wifi_get_state().state == HIBY_WIFI_BLOCKED);
        radio_hard_blocked = true;
        CHECK(hiby_wifi_get_state().state == HIBY_WIFI_HARD_BLOCKED);
        radio_hard_blocked = radio_blocked = false;
        interface_flags[0] &= ~IFF_UP;
        CHECK(hiby_wifi_get_state().state == HIBY_WIFI_UNCONFIRMED);
        interface_flags[0] |= IFF_UP;
        CHECK(hiby_wifi_get_state().state == HIBY_WIFI_ENABLED);
        CHECK(writes == 0);
    }
    no_descriptors();
}

static void test_power(void)
{
    struct hiby_poweroff_result result = hiby_poweroff();
    no_descriptors();
    CHECK(!attributes_active);
    CHECK(init_calls == 1 && destroy_calls == (is_case("attribute-init") ? 0u : 1u));
    CHECK(result.reboot_error == (is_case("reboot-returned-success") ? EIO :
                                 is_case("reboot-interrupt-storm") ? EINTR : EPERM));
    CHECK(reboot_calls == (is_case("reboot-eintr") ? 2u :
                           is_case("reboot-interrupt-storm") ? 8u : 1u));
    CHECK(sync_calls == 2 && wait_calls <= 8 * 33 && sleep_calls <= 8 * 32);
    CHECK(flags_calls <= 1 && group_calls <= 1 && spawn_calls <= 1 && kill_calls <= 8);
    bool no_spawn = is_case("spawn-failure") || is_case("spawn-badpid") ||
        is_case("attribute-init") || is_case("attribute-flags") || is_case("attribute-group");
    bool sleep_error = is_case("sleep-failure") || is_case("sleep-failure-hang") ||
        is_case("sleep-interrupt-storm") || is_case("sleep-invalid");
    if (no_spawn)
        CHECK(elapsed_ns == 0 && result.command_error != 0 && !child_active);
    else if (!sleep_error)
        CHECK(elapsed_ns >= 30000000000ULL && elapsed_ns <= 32000000000ULL);
    if (is_case("normal") || is_case("sleep-eintr") || is_case("reboot-eintr") ||
        is_case("reboot-interrupt-storm") || is_case("reboot-returned-success") ||
        is_case("wait-eintr") || is_case("power-repeated"))
        CHECK(result.command_error == 0 && result.child_error == 0 && !child_active);
    if (is_case("normal-failed") || is_case("child-signal"))
        CHECK(result.command_error == EIO && !child_active && kill_calls == 0);
    if (is_case("hang") || is_case("kill-eintr"))
        CHECK(result.command_error == ETIMEDOUT && result.child_error == 0 &&
              child_killed && !child_active);
    if (is_case("stubborn"))
        CHECK(result.child_error == ETIMEDOUT && child_active && child_killed);
    if (is_case("kill-failure"))
        CHECK(result.child_error == EPERM && child_active && !child_killed);
    if (is_case("kill-interrupt-storm") || is_case("wait-interrupt-storm"))
        CHECK(result.child_error == EINTR && child_active);
    if (is_case("wait-echild"))
        CHECK(result.child_error == ECHILD && !child_active);
    if (is_case("attribute-destroy"))
        CHECK(result.command_error == EINVAL && !child_active);
    if (sleep_error)
        CHECK(result.command_error != 0);
}

int main(int count, char **arguments)
{
    CHECK(count == 3);
    scenario = arguments[2];
    bool power = strcmp(arguments[1], "power") == 0;
    requested_enabled = strcmp(arguments[1], "enable") == 0;
    query_only = strcmp(arguments[1], "query") == 0;
    extended_wifi = requested_enabled || query_only || strcmp(arguments[1], "disable") == 0;
    CHECK(power || extended_wifi || strcmp(arguments[1], "wifi") == 0);
    unsigned int cycles = is_case("repeated") || is_case("power-repeated") ? 1024 : 1;
    for (unsigned int cycle = 0; cycle < cycles; ++cycle)
    {
        opens = closes = writes = reads = sockets = ioctls = stat_calls = 0;
        spawn_calls = wait_calls = kill_calls = sleep_calls = 0;
        init_calls = destroy_calls = flags_calls = group_calls = 0;
        sync_calls = reboot_calls = event_position = interface_sessions = 0;
        child_active = child_killed = attributes_active = false;
        radio_blocked = (extended_wifi && requested_enabled &&
                         !is_case("already-enabled") && !is_case("already-enabled-write-denied")) ||
            is_case("already-blocked-write-denied") || is_case("write-missing-read-blocked") ||
            (extended_wifi && (is_case("blocked") || is_case("stale-blocked") ||
                               is_case("hard-and-soft")));
        if (is_case("write-missing-read-unblocked") || is_case("stale-unblocked"))
            radio_blocked = false;
        radio_hard_blocked = is_case("hard-blocked") || is_case("hard-and-soft");
        elapsed_ns = 0;
        if (power)
            test_power();
        else if (extended_wifi)
            test_wifi_control();
        else
            test_wifi();
    }
    printf("PASS %s %s checks=%u cycles=%u\n", arguments[1], scenario, checks, cycles);
    return 0;
}
