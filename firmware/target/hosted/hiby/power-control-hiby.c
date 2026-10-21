#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif

#include "power-control-hiby.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/rfkill.h>
#include <net/if.h>
#include <signal.h>
#include <spawn.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define HIBY_POWER_IO_ATTEMPTS 8
#define HIBY_POWER_RADIO_CAPACITY 64
#define HIBY_POWER_EVENT_LIMIT 256
#define HIBY_POWER_GRACE_SECONDS 30

extern char **environ;

#ifdef HIBY_R1
static unsigned int wifi_cancellation;
static int wifi_control_busy;
static pid_t wifi_pending_child;

static int wifi_control_wait(pid_t process, bool *active)
{
    int status = 0;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        pid_t observed = waitpid(process, &status, WNOHANG);
        if (observed == process)
        {
            *active = false;
            return WIFEXITED(status) && !WEXITSTATUS(status) ? 0 : EIO;
        }
        if (!observed)
            return 0;
        if (errno != EINTR)
        {
            if (errno == ECHILD)
                *active = false;
            return errno;
        }
    }
    return EINTR;
}

static int wifi_control_pause(void)
{
    struct timespec duration = { .tv_nsec = 50000000 };
    int error = clock_nanosleep(CLOCK_MONOTONIC, 0, &duration, NULL);
    return error == EINTR ? 0 : error;
}

static int wifi_control_command(char *const arguments[], int target,
                                 const void *data, size_t length, unsigned int generation)
{
    if (__sync_lock_test_and_set(&wifi_control_busy, 1))
        return EBUSY;
    int error = 0;
    bool active = wifi_pending_child > 0;
    if (active)
    {
        error = wifi_control_wait(wifi_pending_child, &active);
        if (active)
        {
            error = EBUSY;
            goto unlock;
        }
        wifi_pending_child = 0;
        error = 0;
    }
    if (generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
    {
        error = ECANCELED;
        goto unlock;
    }
    int pipes[2] = { -1, -1 };
    int temporary_target = -1;
    bool attributes_ready = false;
    bool actions_ready = false;
    posix_spawnattr_t attributes;
    posix_spawn_file_actions_t actions;
    pid_t process = -1;
    if (data)
    {
        if (target <= STDERR_FILENO || !length || length > 64)
        {
            error = EINVAL;
            goto cleanup;
        }
        if (target == 9)
        {
            for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
            {
                temporary_target = fcntl(target, F_DUPFD_CLOEXEC, 10);
                if (temporary_target >= 0 || errno != EINTR)
                    break;
            }
            if (temporary_target < 0)
            {
                error = errno;
                goto cleanup;
            }
            target = temporary_target;
        }
        if (pipe2(pipes, O_CLOEXEC | O_NONBLOCK) < 0)
        {
            error = errno;
            goto cleanup;
        }
        if (pipes[0] <= STDERR_FILENO || pipes[1] <= STDERR_FILENO)
        {
            error = EBADF;
            goto cleanup;
        }
        ssize_t count = -1;
        for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
        {
            count = write(pipes[1], data, length);
            if (count >= 0 || errno != EINTR)
                break;
        }
        if (count != (ssize_t)length)
        {
            error = count < 0 ? errno : EIO;
            goto cleanup;
        }
        if (close(pipes[1]) < 0)
        {
            pipes[1] = -1;
            error = errno;
            goto cleanup;
        }
        pipes[1] = -1;
    }
    error = posix_spawnattr_init(&attributes);
    if (error)
        goto cleanup;
    attributes_ready = true;
    error = posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETPGROUP);
    if (!error)
        error = posix_spawnattr_setpgroup(&attributes, 0);
    if (error)
        goto cleanup;
    error = posix_spawn_file_actions_init(&actions);
    if (error)
        goto cleanup;
    actions_ready = true;
    if (data)
    {
        error = posix_spawn_file_actions_adddup2(&actions, pipes[0], STDIN_FILENO);
        if (!error)
            error = posix_spawn_file_actions_adddup2(&actions, target, 9);
        if (!error && pipes[0] != 9)
            error = posix_spawn_file_actions_addclose(&actions, pipes[0]);
        if (!error && target != 9)
            error = posix_spawn_file_actions_addclose(&actions, target);
    }
    else
        error = posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null",
            O_RDONLY | O_NONBLOCK | O_NOFOLLOW, 0);
    if (!error)
        error = posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, "/dev/null",
            O_WRONLY | O_NONBLOCK | O_NOFOLLOW, 0);
    if (!error)
        error = posix_spawn_file_actions_adddup2(&actions, STDOUT_FILENO, STDERR_FILENO);
    if (error)
        goto cleanup;
    if (generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
    {
        error = ECANCELED;
        goto cleanup;
    }
    error = posix_spawn(&process, "/bin/busybox", &actions, &attributes, arguments, environ);
    if (error)
        goto cleanup;
    if (process <= 0)
    {
        error = ECHILD;
        goto cleanup;
    }
    active = true;
    for (unsigned int step = 0; step < 100 && active; ++step)
    {
        error = wifi_control_wait(process, &active);
        if (error || !active)
            break;
        if (generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
        {
            error = ECANCELED;
            break;
        }
        error = wifi_control_pause();
        if (error)
            break;
    }
    if (active)
    {
        if (!error)
            error = ETIMEDOUT;
        for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
            if (!kill(-process, SIGKILL) || errno != EINTR)
                break;
        for (unsigned int attempt = 0; attempt < 3 && active; ++attempt)
        {
            wifi_control_wait(process, &active);
            if (active && attempt < 2 && wifi_control_pause())
                break;
        }
        if (active)
            wifi_pending_child = process;
    }
    if (!error && generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
        error = ECANCELED;
cleanup:
    if (actions_ready)
    {
        int cleanup_error = posix_spawn_file_actions_destroy(&actions);
        if (!error)
            error = cleanup_error;
    }
    if (attributes_ready)
    {
        int cleanup_error = posix_spawnattr_destroy(&attributes);
        if (!error)
            error = cleanup_error;
    }
    for (unsigned int position = 0; position < 2; ++position)
        if (pipes[position] >= 0 && close(pipes[position]) < 0 && !error)
            error = errno;
    if (temporary_target >= 0 && close(temporary_target) < 0 && !error)
        error = errno;
unlock:
    __sync_lock_release(&wifi_control_busy);
    return error;
}

static int wifi_control_write(int descriptor, const void *data, size_t length,
                               unsigned int generation)
{
    char *arguments[] = { "/bin/busybox", "dd", "of=/proc/self/fd/9", "bs=64", "count=1", NULL };
    return wifi_control_command(arguments, descriptor, data, length, generation);
}
#endif

void hiby_wifi_cancel(void)
{
#ifdef HIBY_R1
    __atomic_add_fetch(&wifi_cancellation, 1, __ATOMIC_RELEASE);
#endif
}

bool hiby_wifi_settled(void)
{
#ifdef HIBY_R1
    if (__sync_lock_test_and_set(&wifi_control_busy, 1))
        return false;
    bool active = wifi_pending_child > 0;
    if (active)
    {
        wifi_control_wait(wifi_pending_child, &active);
        if (!active)
            wifi_pending_child = 0;
    }
    __sync_lock_release(&wifi_control_busy);
    return !active;
#else
    return true;
#endif
}

static int rfkill_open(int flags)
{
    int descriptor = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        descriptor = open("/dev/rfkill", flags | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        if (descriptor >= 0 || errno != EINTR)
            break;
    }
    if (descriptor < 0)
        return -1;

    struct stat status;
    int result = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        result = fstat(descriptor, &status);
        if (result == 0 || errno != EINTR)
            break;
    }
    if (result < 0 || !S_ISCHR(status.st_mode))
    {
        int error = result < 0 ? errno : ENODEV;
        close(descriptor);
        errno = error;
        return -1;
    }
    return descriptor;
}

static int close_result(int descriptor, int error)
{
    if (close(descriptor) < 0 && !error)
        error = errno;
    return error;
}

static bool radio_unavailable(int error)
{
    return error == ENOENT || error == ENODEV || error == ENXIO;
}

static int rfkill_attribute(int radio, const char *attribute,
                            bool change, bool blocked, int *value, unsigned int generation)
{
#ifndef HIBY_R1
    (void)generation;
#endif
    int descriptor = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        descriptor = openat(radio, attribute, (change ? O_WRONLY : O_RDONLY) |
                          O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        if (descriptor >= 0 || errno != EINTR)
            break;
    }
    if (descriptor < 0)
        return errno;
    struct stat status;
    int checked = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        checked = fstat(descriptor, &status);
        if (!checked || errno != EINTR)
            break;
    }
    if (checked < 0 || !S_ISREG(status.st_mode))
        return close_result(descriptor, checked < 0 ? errno : ENODEV);
    if (change)
    {
        const char *command = blocked ? "1\n" : "0\n";
#ifdef HIBY_R1
        return close_result(descriptor, wifi_control_write(descriptor, command, 2, generation));
#else
        ssize_t count = -1;
        for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
        {
            count = write(descriptor, command, 2);
            if (count >= 0 || errno != EINTR)
                break;
        }
        return close_result(descriptor, count < 0 ? errno : count == 2 ? 0 : EIO);
#endif
    }
    char data[32];
    size_t used = 0;
    int error = EOVERFLOW;
    unsigned int interruptions = 0;
    for (unsigned int attempt = 0;
         attempt < HIBY_POWER_IO_ATTEMPTS + sizeof(data) && used < sizeof(data); ++attempt)
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0 && errno == EINTR)
        {
            if (++interruptions < HIBY_POWER_IO_ATTEMPTS)
                continue;
            error = EINTR;
            break;
        }
        if (count < 0)
        {
            error = errno;
            break;
        }
        if (!count)
        {
            error = 0;
            break;
        }
        used += count;
    }
    error = close_result(descriptor, error);
    if (error)
        return error;
    if (used && data[used - 1] == '\n')
        --used;
    if (!strcmp(attribute, "type"))
    {
        if (!used || memchr(data, '\0', used) || memchr(data, '\n', used))
            return EPROTO;
        *value = used == 4 && !memcmp(data, "wlan", 4) ? RFKILL_TYPE_WLAN :
            used == 9 && !memcmp(data, "bluetooth", 9) ? RFKILL_TYPE_BLUETOOTH : -1;
    }
    else
    {
        if (used != 1 || (data[0] != '0' && data[0] != '1'))
            return EPROTO;
        *value = data[0] - '0';
    }
    return 0;
}

static int rfkill_sysfs_type(bool change, bool blocked, struct hiby_wifi_result *result,
                             unsigned int type, unsigned int *blocked_radios,
                             unsigned int generation)
{
    DIR *directory = NULL;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        directory = opendir("/sys/class/rfkill");
        if (directory || errno != EINTR)
            break;
    }
    if (!directory)
        return errno;
    struct hiby_wifi_result observed = { 0 };
    unsigned int observed_blocked = 0;
    int error = EOVERFLOW;
    unsigned int interruptions = 0;
    for (unsigned int iteration = 0; iteration < HIBY_POWER_EVENT_LIMIT; ++iteration)
    {
        errno = 0;
        struct dirent *entry = readdir(directory);
        if (!entry)
        {
            if (errno == EINTR && ++interruptions < HIBY_POWER_IO_ATTEMPTS)
                continue;
            error = errno;
            break;
        }
        const char *name = entry->d_name;
        if (strncmp(name, "rfkill", 6) || !name[6])
            continue;
        size_t position = 6;
        while (name[position] >= '0' && name[position] <= '9')
            ++position;
        if (name[position])
            continue;
        int radio = -1;
        for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
        {
            radio = openat(dirfd(directory), name, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
            if (radio >= 0 || errno != EINTR)
                break;
        }
        if (radio < 0)
        {
            error = errno;
            break;
        }
        int observed_type = -1;
        error = rfkill_attribute(radio, "type", false, false, &observed_type, generation);
        if (!error && observed_type == (int)type)
        {
            if (observed.wlan_radios == HIBY_POWER_RADIO_CAPACITY)
                error = EOVERFLOW;
            else
            {
                ++observed.wlan_radios;
                if (change)
                {
#ifdef HIBY_R1
                    if (generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
                        error = ECANCELED;
                    else
#endif
                    error = rfkill_attribute(radio, "soft", true, blocked, NULL, generation);
                }
                else
                {
                    int soft = 0;
                    int hard = 0;
                    error = rfkill_attribute(radio, "soft", false, false, &soft, generation);
                    if (!error)
                        error = rfkill_attribute(radio, "hard", false, false, &hard, generation);
                    observed.soft_blocked_radios += soft;
                    observed.hard_blocked_radios += hard;
                    observed_blocked += soft || hard;
                }
            }
        }
        error = close_result(radio, error);
        if (error)
            break;
        error = EOVERFLOW;
    }
    if (closedir(directory) < 0 && !error)
        error = errno;
    if (!error && result)
    {
        result->wlan_radios = observed.wlan_radios;
        result->soft_blocked_radios = observed.soft_blocked_radios;
        result->hard_blocked_radios = observed.hard_blocked_radios;
        result->rfkill_sysfs = true;
        if (blocked_radios)
            *blocked_radios = observed_blocked;
    }
    return error;
}

static int rfkill_sysfs_access(bool change, bool blocked, struct hiby_wifi_result *result,
                                unsigned int generation)
{
    return rfkill_sysfs_type(change, blocked, result, RFKILL_TYPE_WLAN, NULL, generation);
}

static int rfkill_set_blocked(bool blocked, unsigned int generation)
{
#ifndef HIBY_R1
    (void)generation;
#endif
    int descriptor = rfkill_open(O_WRONLY);
    if (descriptor < 0)
        return errno;

    const struct rfkill_event event =
    {
        .type = RFKILL_TYPE_WLAN,
        .op = RFKILL_OP_CHANGE_ALL,
        .soft = blocked
    };
#ifdef HIBY_R1
    return close_result(descriptor, wifi_control_write(descriptor, &event, RFKILL_EVENT_SIZE_V1, generation));
#else
    ssize_t count = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        count = write(descriptor, &event, RFKILL_EVENT_SIZE_V1);
        if (count >= 0 || errno != EINTR)
            break;
    }
    int error = count < 0 ? errno : count == RFKILL_EVENT_SIZE_V1 ? 0 : EIO;
    return close_result(descriptor, error);
#endif
}

static int rfkill_snapshot_type(struct hiby_wifi_result *result, unsigned int type,
                                unsigned int *blocked_radios)
{
    struct radio_state
    {
        unsigned int index;
        bool soft_blocked;
        bool hard_blocked;
    } states[HIBY_POWER_RADIO_CAPACITY];
    unsigned int used = 0;
    bool complete = false;
    int error = 0;
    int descriptor = rfkill_open(O_RDONLY);
    if (descriptor < 0)
        return errno;

    for (unsigned int iteration = 0; iteration < HIBY_POWER_EVENT_LIMIT; ++iteration)
    {
        struct rfkill_event event;
        ssize_t count = -1;
        for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
        {
            count = read(descriptor, &event, RFKILL_EVENT_SIZE_V1);
            if (count >= 0 || errno != EINTR)
                break;
        }
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
        {
            complete = true;
            break;
        }
        if (count != RFKILL_EVENT_SIZE_V1)
        {
            error = count < 0 ? errno : EIO;
            break;
        }
        if (event.type == RFKILL_TYPE_ALL || event.op > RFKILL_OP_CHANGE ||
            event.soft > 1 || event.hard > 1)
        {
            error = EPROTO;
            break;
        }
        if (event.type != type)
            continue;

        unsigned int position = 0;
        while (position < used && states[position].index != event.idx)
            ++position;
        if (event.op == RFKILL_OP_DEL)
        {
            if (position < used)
                states[position] = states[--used];
            continue;
        }
        if (position == used)
        {
            if (event.op != RFKILL_OP_ADD || used == HIBY_POWER_RADIO_CAPACITY)
            {
                error = event.op != RFKILL_OP_ADD ? EPROTO : EOVERFLOW;
                break;
            }
            states[used++].index = event.idx;
        }
        states[position].soft_blocked = event.soft != 0;
        states[position].hard_blocked = event.hard != 0;
    }
    if (!complete && !error)
        error = EOVERFLOW;
    error = close_result(descriptor, error);
    if (!error)
    {
        result->wlan_radios = used;
        for (unsigned int position = 0; position < used; ++position)
        {
            result->soft_blocked_radios += states[position].soft_blocked;
            result->hard_blocked_radios += states[position].hard_blocked;
            if (blocked_radios)
                *blocked_radios += states[position].soft_blocked || states[position].hard_blocked;
        }
    }
    return error;
}

static int rfkill_snapshot(struct hiby_wifi_result *result)
{
    return rfkill_snapshot_type(result, RFKILL_TYPE_WLAN, NULL);
}

int hiby_bluetooth_rfkill_blocked(bool *blocked)
{
    if (!blocked)
        return EINVAL;
    struct hiby_wifi_result result = { 0 };
    unsigned int blocked_radios = 0;
    int error = rfkill_snapshot_type(&result, RFKILL_TYPE_BLUETOOTH, &blocked_radios);
    if (radio_unavailable(error))
        error = rfkill_sysfs_type(false, false, &result, RFKILL_TYPE_BLUETOOTH, &blocked_radios, 0);
    if (error)
        return radio_unavailable(error) ? ENODEV : error;
    if (!result.wlan_radios)
        return ENODEV;
    if (blocked_radios && blocked_radios != result.wlan_radios)
        return EAGAIN;
    *blocked = blocked_radios == result.wlan_radios;
    return 0;
}

static int interface_ioctl(int descriptor, unsigned long operation,
                           struct ifreq *request)
{
    int result = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        result = ioctl(descriptor, operation, request);
        if (result == 0 || errno != EINTR)
            break;
    }
    return result;
}

static int interfaces_access(bool change, bool enabled, struct hiby_wifi_result *result,
                              unsigned int generation)
{
#ifndef HIBY_R1
    (void)generation;
#endif
    static const char *const names[] = { "wlan0", "wlan1" };
    int descriptor = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        descriptor = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
        if (descriptor >= 0 || errno != EINTR)
            break;
    }
    if (descriptor < 0)
        return errno;

    int error = 0;
    for (size_t position = 0; position < sizeof(names) / sizeof(names[0]); ++position)
    {
        struct ifreq request;
        memset(&request, 0, sizeof(request));
        strcpy(request.ifr_name, names[position]);
        if (interface_ioctl(descriptor, SIOCGIFFLAGS, &request) < 0)
        {
            if (errno != ENODEV && errno != ENXIO && !error)
                error = errno;
            continue;
        }
        if (change)
        {
            short flags = enabled ? request.ifr_flags | IFF_UP :
                                    request.ifr_flags & ~IFF_UP;
            if (request.ifr_flags != flags)
            {
                request.ifr_flags = flags;
#ifdef HIBY_R1
                if (generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
                {
                    if (!error)
                        error = ECANCELED;
                    break;
                }
                char *arguments[] = { "/bin/busybox", "ifconfig", (char *)names[position],
                    enabled ? "up" : "down", NULL };
                int changed = wifi_control_command(arguments, -1, NULL, 0, generation);
                if (changed && !error)
                    error = changed;
#else
                if (interface_ioctl(descriptor, SIOCSIFFLAGS, &request) < 0 && !error)
                    error = errno;
#endif
            }
        }
        else
        {
            ++result->interfaces_present;
            if (request.ifr_flags & IFF_UP)
                ++result->interfaces_up;
            else
                ++result->interfaces_down;
        }
    }
    return close_result(descriptor, error);
}

#ifdef HIBY_R1
static int sdio_open_directory(int parent, const char *path, bool follow)
{
    int descriptor = -1;
    int flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NONBLOCK;
    if (!follow)
        flags |= O_NOFOLLOW;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        descriptor = openat(parent, path, flags);
        if (descriptor >= 0 || errno != EINTR)
            break;
    }
    return descriptor;
}

static int sdio_stat(int descriptor, struct stat *status)
{
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        if (!fstat(descriptor, status))
            return 0;
        if (errno != EINTR)
            return errno;
    }
    return EINTR;
}

static int sdio_same_directory(int first, int second)
{
    struct stat first_status;
    struct stat second_status;
    int error = sdio_stat(first, &first_status);
    if (!error)
        error = sdio_stat(second, &second_status);
    if (error)
        return error;
    if (!S_ISDIR(first_status.st_mode) || !S_ISDIR(second_status.st_mode) ||
        first_status.st_dev != second_status.st_dev || first_status.st_ino != second_status.st_ino)
        return ENODEV;
    return 0;
}

static int sdio_hex_attribute(int directory, const char *attribute,
                              unsigned int digits, unsigned int *value)
{
    int descriptor = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        descriptor = openat(directory, attribute, O_RDONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
        if (descriptor >= 0 || errno != EINTR)
            break;
    }
    if (descriptor < 0)
        return errno;
    struct stat status;
    int error = sdio_stat(descriptor, &status);
    if (error || !S_ISREG(status.st_mode))
        return close_result(descriptor, error ? error : ENODEV);
    char data[8];
    size_t used = 0;
    unsigned int interruptions = 0;
    error = EOVERFLOW;
    for (unsigned int attempt = 0; attempt < sizeof(data) + HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        if (used == sizeof(data))
            break;
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0)
        {
            if (errno == EINTR && ++interruptions < HIBY_POWER_IO_ATTEMPTS)
                continue;
            error = errno;
            break;
        }
        if (!count)
        {
            error = 0;
            break;
        }
        used += count;
    }
    error = close_result(descriptor, error);
    if (error)
        return error;
    if (used && data[used - 1] == '\n')
        --used;
    if (used != digits + 2 || data[0] != '0' || data[1] != 'x')
        return EPROTO;
    unsigned int parsed = 0;
    for (unsigned int position = 2; position < used; ++position)
    {
        unsigned char character = data[position];
        unsigned int digit = character >= '0' && character <= '9' ? character - '0' :
            character >= 'a' && character <= 'f' ? character - 'a' + 10 :
            character >= 'A' && character <= 'F' ? character - 'A' + 10 : 16;
        if (digit == 16)
            return EPROTO;
        parsed = parsed * 16 + digit;
    }
    *value = parsed;
    return 0;
}

static int sdio_missing_link(int directory, const char *name)
{
    struct stat status;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        if (!fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW))
            return ENODEV;
        if (errno != EINTR)
            return errno == ENOENT ? 0 : errno;
    }
    return EINTR;
}

static int sdio_suspended_driver(int *driver)
{
    static const char *const paths[] = {
        "/sys/bus/sdio/drivers/bcmsdh_sdmmc", "/sys/module/cywdhd",
        "/sys/bus/sdio/devices/mmc0:0001:1", "/sys/bus/sdio/devices/mmc0:0001:2"
    };
    int descriptors[7] = { -1, -1, -1, -1, -1, -1, -1 };
    int error = 0;
    bool module_link_missing = false;
    *driver = -1;
    for (unsigned int position = 0; position < 4; ++position)
    {
        if (position == 1)
            continue;
        descriptors[position] = sdio_open_directory(AT_FDCWD, paths[position], position >= 2);
        if (descriptors[position] < 0)
        {
            error = errno;
            goto cleanup;
        }
    }
    descriptors[4] = sdio_open_directory(descriptors[0], "module", true);
    if (descriptors[4] < 0)
    {
        error = errno;
        if (error != ENOENT)
            goto cleanup;
        error = sdio_missing_link(descriptors[0], "module");
        if (error)
            goto cleanup;
        module_link_missing = true;
    }
    else
    {
        descriptors[1] = sdio_open_directory(AT_FDCWD, paths[1], false);
        if (descriptors[1] < 0)
        {
            error = errno;
            goto cleanup;
        }
        error = sdio_same_directory(descriptors[1], descriptors[4]);
        if (error)
            goto cleanup;
    }
    descriptors[5] = sdio_open_directory(descriptors[2], "driver", true);
    if (descriptors[5] < 0)
    {
        error = errno;
        goto cleanup;
    }
    error = sdio_same_directory(descriptors[0], descriptors[5]);
    if (error)
        goto cleanup;
    unsigned int first_device = 0;
    for (unsigned int position = 2; position < 4; ++position)
    {
        unsigned int vendor = 0;
        unsigned int device = 0;
        unsigned int function_class = 0;
        error = sdio_hex_attribute(descriptors[position], "vendor", 4, &vendor);
        if (!error)
            error = sdio_hex_attribute(descriptors[position], "device", 4, &device);
        if (!error)
            error = sdio_hex_attribute(descriptors[position], "class", 2, &function_class);
        if (error)
            goto cleanup;
        if (vendor != 0x02d0 || !device || device == 0xffff || function_class ||
            (position == 3 && device != first_device))
        {
            error = ENODEV;
            goto cleanup;
        }
        first_device = device;
    }
    if (module_link_missing && first_device != 0xa9a6)
    {
        error = ENODEV;
        goto cleanup;
    }
    descriptors[6] = sdio_open_directory(descriptors[3], "driver", true);
    if (descriptors[6] >= 0)
    {
        error = ENODEV;
        goto cleanup;
    }
    if (errno != ENOENT)
    {
        error = errno;
        goto cleanup;
    }
    error = sdio_missing_link(descriptors[3], "driver");
    if (error)
        goto cleanup;
    *driver = descriptors[0];
    descriptors[0] = -1;
cleanup:
    for (unsigned int position = 0; position < 7; ++position)
        if (descriptors[position] >= 0)
            error = close_result(descriptors[position], error);
    if (error && *driver >= 0)
    {
        close(*driver);
        *driver = -1;
    }
    return error;
}

static int sdio_attach(unsigned int generation)
{
    int driver = -1;
    int error = sdio_suspended_driver(&driver);
    if (error)
        return error;
    int descriptor = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        descriptor = openat(driver, "bind", O_WRONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
        if (descriptor >= 0 || errno != EINTR)
            break;
    }
    if (descriptor < 0)
        error = errno;
    else
    {
        struct stat status;
        error = sdio_stat(descriptor, &status);
        if (!error && !S_ISREG(status.st_mode))
            error = ENODEV;
        if (!error)
            error = wifi_control_write(descriptor, "mmc0:0001:2\n", sizeof("mmc0:0001:2\n") - 1, generation);
        error = close_result(descriptor, error);
    }
    return close_result(driver, error);
}
#endif

struct hiby_wifi_result hiby_wifi_get_state(void)
{
    struct hiby_wifi_result result = { .state = HIBY_WIFI_UNCONFIRMED };
#ifdef HIBY_R1
    if (!hiby_wifi_settled())
    {
        result.state = HIBY_WIFI_ERROR;
        result.driver_error = EBUSY;
        return result;
    }
#endif
    result.rfkill_read_error = rfkill_snapshot(&result);
    if (radio_unavailable(result.rfkill_read_error))
    {
        int fallback_error = rfkill_sysfs_access(false, false, &result, 0);
        if (!radio_unavailable(fallback_error))
            result.rfkill_read_error = fallback_error;
    }
    result.interface_read_error = interfaces_access(false, false, &result, 0);
    result.rfkill_error = result.rfkill_read_error;
    result.interface_error = result.interface_read_error;
    if (result.rfkill_read_error)
        result.state = radio_unavailable(result.rfkill_read_error) ?
            HIBY_WIFI_UNCONFIRMED : HIBY_WIFI_ERROR;
    else if (!result.wlan_radios)
        result.state = HIBY_WIFI_NO_RADIO;
    else if (result.hard_blocked_radios)
        result.state = HIBY_WIFI_HARD_BLOCKED;
    else if (result.soft_blocked_radios == result.wlan_radios)
        result.state = HIBY_WIFI_BLOCKED;
    else if (result.interface_read_error)
        result.state = HIBY_WIFI_ERROR;
    else if (!result.soft_blocked_radios && result.interfaces_present &&
             result.interfaces_up == result.interfaces_present)
        result.state = HIBY_WIFI_ENABLED;
    if ((radio_unavailable(result.rfkill_read_error) ||
         (!result.rfkill_read_error && !result.wlan_radios)) &&
        !result.interface_read_error && result.interfaces_present &&
        result.interfaces_down == result.interfaces_present)
        result.state = HIBY_WIFI_INTERFACE_DOWN;
#ifdef HIBY_R1
    if ((radio_unavailable(result.rfkill_read_error) ||
         (!result.rfkill_read_error && !result.wlan_radios)) &&
        !result.interface_read_error && !result.interfaces_present)
    {
        int driver = -1;
        int error = sdio_suspended_driver(&driver);
        if (!error)
        {
            error = close_result(driver, 0);
            if (!error)
                result.state = HIBY_WIFI_DRIVER_SUSPENDED;
        }
        if (error && !radio_unavailable(error))
        {
            result.driver_error = error;
            result.state = HIBY_WIFI_ERROR;
        }
    }
#endif
    return result;
}

struct hiby_wifi_result hiby_wifi_set_enabled(bool enabled)
{
    unsigned int generation = 0;
#ifdef HIBY_R1
    generation = __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE);
    struct hiby_wifi_result initial = hiby_wifi_get_state();
    if (initial.driver_error)
        return initial;
    if (generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
    {
        initial.state = HIBY_WIFI_ERROR;
        initial.driver_error = ECANCELED;
        return initial;
    }
    if (initial.state == HIBY_WIFI_DRIVER_SUSPENDED)
    {
        if (!enabled)
            return initial;
        int error = sdio_attach(generation);
        if (error)
        {
            initial.state = HIBY_WIFI_ERROR;
            initial.driver_error = error;
            return initial;
        }
    }
    if (generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE))
    {
        initial.state = HIBY_WIFI_ERROR;
        initial.driver_error = ECANCELED;
        return initial;
    }
#endif
    int radio_error = rfkill_set_blocked(!enabled, generation);
    if (radio_unavailable(radio_error))
    {
        int fallback_error = rfkill_sysfs_access(true, !enabled, NULL, generation);
        if (!radio_unavailable(fallback_error))
            radio_error = fallback_error;
    }
    int interface_error;
#ifdef HIBY_R1
    interface_error = generation != __atomic_load_n(&wifi_cancellation, __ATOMIC_ACQUIRE) ?
        ECANCELED : interfaces_access(true, enabled, NULL, generation);
#else
    interface_error = interfaces_access(true, enabled, NULL, generation);
#endif
    struct hiby_wifi_result result = hiby_wifi_get_state();
    if (radio_error)
        result.rfkill_error = radio_error;
    if (interface_error)
        result.interface_error = interface_error;
    if (!result.interface_error && result.interfaces_present &&
        (enabled ? result.interfaces_up : result.interfaces_down) != result.interfaces_present)
        result.interface_error = EBUSY;
    if ((result.state == HIBY_WIFI_UNCONFIRMED || result.state == HIBY_WIFI_INTERFACE_DOWN) &&
        ((result.rfkill_error && !radio_unavailable(result.rfkill_error)) ||
         result.interface_error))
        result.state = HIBY_WIFI_ERROR;
    return result;
}

struct hiby_wifi_result hiby_wifi_disable(void)
{
    struct hiby_wifi_result result = hiby_wifi_set_enabled(false);
#ifdef HIBY_R1
    if (result.state == HIBY_WIFI_ERROR || result.driver_error || result.interface_error ||
        result.interface_read_error ||
        (result.rfkill_error && !radio_unavailable(result.rfkill_error)) ||
        (result.rfkill_read_error && !radio_unavailable(result.rfkill_read_error)))
    {
        result.state = HIBY_WIFI_ERROR;
        return result;
    }
#endif
    if (result.driver_error || result.state == HIBY_WIFI_INTERFACE_DOWN ||
        result.state == HIBY_WIFI_DRIVER_SUSPENDED)
        return result;
    if (!result.rfkill_read_error)
        result.state = !result.wlan_radios ? HIBY_WIFI_NO_RADIO :
            result.soft_blocked_radios == result.wlan_radios ?
            HIBY_WIFI_BLOCKED : HIBY_WIFI_UNCONFIRMED;
    else
        result.state = radio_unavailable(result.rfkill_read_error) ?
            HIBY_WIFI_UNCONFIRMED : HIBY_WIFI_ERROR;
    if (result.state == HIBY_WIFI_UNCONFIRMED && result.rfkill_error &&
        !radio_unavailable(result.rfkill_error))
        result.state = HIBY_WIFI_ERROR;
    return result;
}

static int power_sleep(void)
{
    struct timespec remaining = { .tv_sec = 1 };
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        struct timespec requested = remaining;
        int error = clock_nanosleep(CLOCK_MONOTONIC, 0, &requested, &remaining);
        if (error != EINTR)
            return error;
        if (remaining.tv_sec < 0 || remaining.tv_sec > 1 ||
            remaining.tv_nsec < 0 || remaining.tv_nsec >= 1000000000 ||
            remaining.tv_sec > requested.tv_sec ||
            (remaining.tv_sec == requested.tv_sec && remaining.tv_nsec > requested.tv_nsec))
            return EIO;
    }
    return EINTR;
}

static int child_wait(pid_t process, bool *active, int *command_error)
{
    int status;
    pid_t result = -1;
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        result = waitpid(process, &status, WNOHANG);
        if (result >= 0 || errno != EINTR)
            break;
    }
    if (result == process)
    {
        *active = false;
        if ((!WIFEXITED(status) || WEXITSTATUS(status) != 0) && !*command_error)
            *command_error = EIO;
        return 0;
    }
    if (result < 0)
    {
        if (errno == ECHILD)
            *active = false;
        return errno;
    }
    return 0;
}

struct hiby_poweroff_result hiby_poweroff(void)
{
    struct hiby_poweroff_result result = { 0 };
    posix_spawnattr_t attributes;
    pid_t process = -1;
    bool active = false;
    char executable[] = "/sbin/poweroff";
    char *arguments[] = { executable, NULL };

    sync();
    result.command_error = posix_spawnattr_init(&attributes);
    if (!result.command_error)
    {
        result.command_error = posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETPGROUP);
        if (!result.command_error)
            result.command_error = posix_spawnattr_setpgroup(&attributes, 0);
        if (!result.command_error)
            result.command_error = posix_spawn(&process, executable, NULL,
                                                &attributes, arguments, environ);
        int error = posix_spawnattr_destroy(&attributes);
        active = !result.command_error && process > 0;
        if (!result.command_error)
            result.command_error = process <= 0 ? ECHILD : error;
    }

    if (active)
    {
        for (unsigned int second = 0; second < HIBY_POWER_GRACE_SECONDS; ++second)
        {
            if (active)
            {
                int error = child_wait(process, &active, &result.command_error);
                if (!result.child_error)
                    result.child_error = error;
            }
            int error = power_sleep();
            if (error)
            {
                if (!result.command_error)
                    result.command_error = error;
                break;
            }
        }
    }

    if (active)
    {
        if (!result.command_error)
            result.command_error = ETIMEDOUT;
        int killed = -1;
        for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
        {
            killed = kill(-process, SIGKILL);
            if (killed == 0 || errno != EINTR)
                break;
        }
        if (killed < 0 && errno != ESRCH && !result.child_error)
            result.child_error = errno;
        for (unsigned int attempt = 0; attempt < 3 && active; ++attempt)
        {
            int error = child_wait(process, &active, &result.command_error);
            if (error && !result.child_error)
                result.child_error = error;
            if (active && attempt < 2)
            {
                error = power_sleep();
                if (error)
                {
                    if (!result.child_error)
                        result.child_error = error;
                    break;
                }
            }
        }
        if (active && !result.child_error)
            result.child_error = ETIMEDOUT;
    }

    sync();
    for (unsigned int attempt = 0; attempt < HIBY_POWER_IO_ATTEMPTS; ++attempt)
    {
        int status = reboot(RB_POWER_OFF);
        result.reboot_error = status < 0 ? errno : EIO;
        if (status == 0 || errno != EINTR)
            break;
    }
    return result;
}
