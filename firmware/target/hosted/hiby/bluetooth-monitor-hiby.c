#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include "bluetooth-monitor-hiby.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef HIBY_BT_MONITOR_EXECUTABLE
#define HIBY_BT_MONITOR_EXECUTABLE "/usr/bin/dbus-monitor"
#endif

#define MONITOR_LINE_SIZE 2048
#define MONITOR_READ_BUDGET 16384
#define MONITOR_WAKE_DRAIN_BUDGET 65536
#define MONITOR_EINTR_LIMIT 4
#define MONITOR_EXEC_TIMEOUT_MS 500
#define MONITOR_REAP_STEPS 25

static pthread_mutex_t wake_mutex = PTHREAD_MUTEX_INITIALIZER;
static int wake_pipe[2] = { -1, -1 };
static bool wake_pending;
static int monitor_output = -1;
static pid_t monitor_child;
static bool monitor_group;
static char monitor_line[MONITOR_LINE_SIZE];
static size_t monitor_line_used;
static bool monitor_line_dropped;

static const char *const monitor_arguments[] =
{
    HIBY_BT_MONITOR_EXECUTABLE, "--system", "--profile",
    "type='signal',sender='org.bluez',path_namespace='/org/bluez',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',arg0='org.bluez.Device1'",
    "type='signal',sender='org.bluez',path_namespace='/org/bluez',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',arg0='org.bluez.Adapter1'",
    "type='signal',sender='org.bluez',path='/',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesAdded'",
    "type='signal',sender='org.bluez',path='/',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesRemoved'",
    "type='signal',sender='org.bluealsa',path='/org/bluealsa',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesAdded'",
    "type='signal',sender='org.bluealsa',path='/org/bluealsa',interface='org.freedesktop.DBus.ObjectManager',member='InterfacesRemoved'",
    "type='signal',sender='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.bluez'",
    "type='signal',sender='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.bluealsa'",
    NULL
};

static void close_descriptor(int *descriptor)
{
    if (*descriptor >= 0)
        close(*descriptor);
    *descriptor = -1;
}

static void reset_parser(void)
{
    monitor_line_used = 0;
    monitor_line_dropped = false;
}

static int64_t monotonic_ms(void)
{
    struct timespec current;
    if (clock_gettime(CLOCK_MONOTONIC, &current))
        return -1;
    return (int64_t)current.tv_sec * 1000 + current.tv_nsec / 1000000;
}

static bool consume(const char **cursor, const char *expected)
{
    size_t length = strlen(expected);
    if (strncmp(*cursor, expected, length))
        return false;
    *cursor += length;
    return true;
}

static bool decimal(const char **cursor, size_t maximum)
{
    size_t length = 0;
    while (**cursor >= '0' && **cursor <= '9')
    {
        if (++length > maximum)
            return false;
        ++*cursor;
    }
    return length != 0;
}

static bool field(const char **cursor, const char *terminator,
                  char *destination, size_t capacity)
{
    const char *end = strstr(*cursor, terminator);
    if (!end || end == *cursor || (size_t)(end - *cursor) >= capacity)
        return false;
    size_t length = (size_t)(end - *cursor);
    memcpy(destination, *cursor, length);
    destination[length] = '\0';
    *cursor = end + strlen(terminator);
    return true;
}

static bool bus_name(const char *name)
{
    bool unique = *name == ':';
    const char *cursor = name + unique;
    bool component_start = true;
    bool dotted = false;
    if (!*cursor)
        return false;
    for (; *cursor; cursor++)
    {
        unsigned char value = *cursor;
        if (value == '.')
        {
            if (component_start)
                return false;
            component_start = true;
            dotted = true;
            continue;
        }
        bool digit = value >= '0' && value <= '9';
        if (!((value >= 'a' && value <= 'z') ||
              (value >= 'A' && value <= 'Z') || digit ||
              value == '_' || value == '-') ||
            (component_start && digit && !unique))
            return false;
        component_start = false;
    }
    return dotted && !component_start;
}

static bool bounded_decimal(const char **cursor, uint64_t maximum,
                            bool nonzero)
{
    const char *start = *cursor;
    uint64_t number = 0;
    if (**cursor == '0' && (*cursor)[1] >= '0' && (*cursor)[1] <= '9')
        return false;
    while (**cursor >= '0' && **cursor <= '9')
    {
        unsigned int digit = *(*cursor)++ - '0';
        if (number > (maximum - digit) / 10)
            return false;
        number = number * 10 + digit;
    }
    return *cursor != start && (!nonzero || number != 0);
}

static bool service_sender(const char *sender, const char *service)
{
    return sender[0] == ':' || !strcmp(sender, service);
}

static bool bluez_path(const char *path)
{
    if (!consume(&path, "/org/bluez/hci") || !decimal(&path, 10))
        return false;
    if (!*path)
        return true;
    if (!consume(&path, "/dev_"))
        return false;
    for (size_t octet = 0; octet < 6; octet++)
    {
        for (size_t digit = 0; digit < 2; digit++)
        {
            unsigned char value = *path;
            if (!((value >= '0' && value <= '9') ||
                  (value >= 'a' && value <= 'f') ||
                  (value >= 'A' && value <= 'F')))
                return false;
            path++;
        }
        if (octet < 5 && !consume(&path, "_"))
            return false;
    }
    return !*path;
}

static bool relevant_header(const char *line)
{
    const char *cursor = line;
    char sender[256], destination[256], path[256], interface[256];
    if (!consume(&cursor, "sig\t") ||
        !bounded_decimal(&cursor, INT64_MAX, false) || !consume(&cursor, "."))
        return false;
    for (size_t digit = 0; digit < 6; digit++)
    {
        if (*cursor < '0' || *cursor > '9')
            return false;
        cursor++;
    }
    if (!consume(&cursor, "\t") ||
        !bounded_decimal(&cursor, UINT32_MAX, true) ||
        !consume(&cursor, "\t") ||
        !field(&cursor, "\t", sender, sizeof(sender)) ||
        !bus_name(sender) ||
        !field(&cursor, "\t", destination, sizeof(destination)) ||
        (strcmp(destination, "<none>") && !bus_name(destination)) ||
        !field(&cursor, "\t", path, sizeof(path)) ||
        !field(&cursor, "\t", interface, sizeof(interface)))
        return false;
    if (!strcmp(interface, "org.freedesktop.DBus.Properties"))
        return service_sender(sender, "org.bluez") &&
            !strcmp(cursor, "PropertiesChanged") && bluez_path(path);
    if (!strcmp(interface, "org.freedesktop.DBus.ObjectManager"))
        return ((!strcmp(path, "/") && service_sender(sender, "org.bluez")) ||
                (!strcmp(path, "/org/bluealsa") &&
                 service_sender(sender, "org.bluealsa"))) &&
            (!strcmp(cursor, "InterfacesAdded") ||
             !strcmp(cursor, "InterfacesRemoved"));
    return !strcmp(sender, "org.freedesktop.DBus") &&
        !strcmp(path, "/org/freedesktop/DBus") &&
        !strcmp(interface, "org.freedesktop.DBus") &&
        !strcmp(cursor, "NameOwnerChanged");
}

static bool parse_output(const char *data, size_t length)
{
    bool changed = false;
    for (size_t offset = 0; offset < length; offset++)
    {
        unsigned char value = data[offset];
        if (value == '\n')
        {
            if (!monitor_line_dropped)
            {
                monitor_line[monitor_line_used] = '\0';
                changed |= relevant_header(monitor_line);
            }
            reset_parser();
        }
        else if ((value < 32 && value != '\t') || value > 126 ||
                 monitor_line_used == sizeof(monitor_line) - 1)
            monitor_line_dropped = true;
        else if (!monitor_line_dropped)
            monitor_line[monitor_line_used++] = value;
    }
    return changed;
}

static bool reap_child(void)
{
    if (!monitor_child)
        return true;
    for (unsigned int attempt = 0; attempt < MONITOR_EINTR_LIMIT; attempt++)
    {
        pid_t result = waitpid(monitor_child, NULL, WNOHANG);
        if (result == monitor_child || (result < 0 && errno == ECHILD))
        {
            monitor_child = 0;
            monitor_group = false;
            return true;
        }
        if (result >= 0 || errno != EINTR)
            break;
    }
    return false;
}

static bool make_pipe(int descriptors[2], int flags)
{
    if (pipe2(descriptors, flags | O_CLOEXEC))
        return false;
    for (size_t end = 0; end < 2; end++)
    {
        if (descriptors[end] > STDERR_FILENO)
            continue;
        int replacement = fcntl(descriptors[end], F_DUPFD_CLOEXEC, 3);
        if (replacement < 0)
        {
            close_descriptor(&descriptors[0]);
            close_descriptor(&descriptors[1]);
            return false;
        }
        close(descriptors[end]);
        descriptors[end] = replacement;
    }
    return true;
}

static bool consume_wake(void)
{
    pthread_mutex_lock(&wake_mutex);
    bool pending = wake_pending;
    if (wake_pipe[0] >= 0)
    {
        char bytes[1024];
        size_t drained = 0;
        unsigned int interruptions = 0;
        while (drained < MONITOR_WAKE_DRAIN_BUDGET)
        {
            ssize_t count = read(wake_pipe[0], bytes, sizeof(bytes));
            if (count > 0)
            {
                pending = true;
                drained += (size_t)count;
                continue;
            }
            if (count < 0 && errno == EINTR &&
                ++interruptions < MONITOR_EINTR_LIMIT)
                continue;
            break;
        }
    }
    wake_pending = false;
    pthread_mutex_unlock(&wake_mutex);
    return pending;
}

bool hiby_bt_monitor_init(void)
{
    pthread_mutex_lock(&wake_mutex);
    bool ready = wake_pipe[0] >= 0;
    if (!ready)
    {
        ready = make_pipe(wake_pipe, O_NONBLOCK);
        if (ready)
            wake_pending = false;
    }
    pthread_mutex_unlock(&wake_mutex);
    return ready;
}

void hiby_bt_monitor_wake(void)
{
    pthread_mutex_lock(&wake_mutex);
    if (wake_pipe[1] >= 0 && !wake_pending)
    {
        char token = 1;
        for (unsigned int attempt = 0; attempt < MONITOR_EINTR_LIMIT; attempt++)
        {
            ssize_t result = write(wake_pipe[1], &token, sizeof(token));
            if (result == 1 || (result < 0 && errno == EAGAIN))
            {
                wake_pending = true;
                break;
            }
            if (result >= 0 || errno != EINTR)
                break;
        }
    }
    pthread_mutex_unlock(&wake_mutex);
}

static void close_inherited(int preserved, int descriptor_limit)
{
#ifdef SYS_close_range
    bool lower_closed = preserved == 3 ||
        syscall(SYS_close_range, 3u, (unsigned int)preserved - 1u, 0u) == 0;
    bool upper_closed = syscall(SYS_close_range,
        (unsigned int)preserved + 1u, UINT_MAX, 0u) == 0;
    if (lower_closed && upper_closed)
        return;
#endif
    for (int descriptor = 3; descriptor < descriptor_limit; descriptor++)
        if (descriptor != preserved)
            close(descriptor);
}

static void exec_monitor(int output, int status, int descriptor_limit,
                         pid_t parent)
{
    int failure = 0;
    sigset_t unblocked;
    sigemptyset(&unblocked);
    if (sigprocmask(SIG_SETMASK, &unblocked, NULL))
        failure = errno;
    struct sigaction disposition;
    memset(&disposition, 0, sizeof(disposition));
    disposition.sa_handler = SIG_DFL;
    sigemptyset(&disposition.sa_mask);
    const int notifications[] = { SIGTERM, SIGINT, SIGHUP, SIGPIPE, SIGCHLD };
    for (size_t position = 0;
         position < sizeof(notifications) / sizeof(notifications[0]); position++)
        if (sigaction(notifications[position], &disposition, NULL))
            failure = errno;
    if (prctl(PR_SET_PDEATHSIG, SIGTERM) || getppid() != parent)
        failure = ECANCELED;
    if (setpgid(0, 0))
        failure = errno;
    int null_descriptor = open("/dev/null", O_RDWR | O_CLOEXEC);
    if (null_descriptor < 0)
        failure = errno;
    if (!failure && (dup2(null_descriptor, STDIN_FILENO) < 0 ||
        dup2(output, STDOUT_FILENO) < 0 ||
        dup2(null_descriptor, STDERR_FILENO) < 0))
        failure = errno;
    if (!failure)
    {
        close_inherited(status, descriptor_limit);
        execv(monitor_arguments[0], (char *const *)monitor_arguments);
        failure = errno;
    }
    for (unsigned int attempt = 0; attempt < MONITOR_EINTR_LIMIT; attempt++)
    {
        if (write(status, &failure, sizeof(failure)) >= 0 || errno != EINTR)
            break;
    }
    _exit(127);
}

static bool exec_ready(int descriptor)
{
    int64_t started = monotonic_ms();
    if (started < 0)
        return false;
    unsigned int interruptions = 0;
    for (;;)
    {
        int64_t now = monotonic_ms();
        if (now < started || now - started >= MONITOR_EXEC_TIMEOUT_MS)
            return false;
        struct pollfd watched = { descriptor, POLLIN, 0 };
        int result = poll(&watched, 1,
            MONITOR_EXEC_TIMEOUT_MS - (int)(now - started));
        if (result < 0 && errno == EINTR &&
            ++interruptions < MONITOR_EINTR_LIMIT)
            continue;
        if (result <= 0 || (watched.revents & (POLLERR | POLLNVAL)))
            return false;
        int failure;
        ssize_t count = read(descriptor, &failure, sizeof(failure));
        if (!count)
            return true;
        if (count < 0 && (errno == EAGAIN || errno == EINTR) &&
            ++interruptions < MONITOR_EINTR_LIMIT)
            continue;
        return false;
    }
}

bool hiby_bt_monitor_start(void)
{
    if (monitor_output >= 0)
        return true;
    if (wake_pipe[0] < 0 || !reap_child())
        return false;
    struct sigaction child_disposition;
    if (sigaction(SIGCHLD, NULL, &child_disposition) ||
        child_disposition.sa_handler == SIG_IGN ||
        (child_disposition.sa_flags & SA_NOCLDWAIT))
        return false;
    struct rlimit limits;
    if (getrlimit(RLIMIT_NOFILE, &limits) ||
        limits.rlim_max == RLIM_INFINITY || limits.rlim_max > INT_MAX)
        return false;
    int output_pipe[2] = { -1, -1 };
    int status_pipe[2] = { -1, -1 };
    if (!make_pipe(output_pipe, 0) || !make_pipe(status_pipe, O_NONBLOCK) ||
        fcntl(output_pipe[0], F_SETFL, O_NONBLOCK) < 0)
    {
        close_descriptor(&output_pipe[0]);
        close_descriptor(&output_pipe[1]);
        close_descriptor(&status_pipe[0]);
        close_descriptor(&status_pipe[1]);
        return false;
    }
    pid_t parent = getpid();
    pid_t child = fork();
    if (!child)
        exec_monitor(output_pipe[1], status_pipe[1], (int)limits.rlim_max, parent);
    close_descriptor(&output_pipe[1]);
    close_descriptor(&status_pipe[1]);
    if (child < 0)
    {
        close_descriptor(&output_pipe[0]);
        close_descriptor(&status_pipe[0]);
        return false;
    }
    monitor_child = child;
    monitor_group = setpgid(child, child) == 0 || getpgid(child) == child;
    monitor_output = output_pipe[0];
    reset_parser();
    bool ready = exec_ready(status_pipe[0]);
    close_descriptor(&status_pipe[0]);
    if (!ready)
        hiby_bt_monitor_stop();
    return ready;
}

static enum hiby_bt_monitor_result monitor_failed(void)
{
    close_descriptor(&monitor_output);
    reset_parser();
    reap_child();
    return HIBY_BT_MONITOR_FAILED;
}

enum hiby_bt_monitor_result hiby_bt_monitor_wait(int timeout_ms)
{
    if (wake_pipe[0] < 0 || timeout_ms < -1)
        return HIBY_BT_MONITOR_FAILED;
    int64_t deadline = 0;
    if (timeout_ms > 0)
    {
        deadline = monotonic_ms();
        if (deadline < 0)
            return monitor_failed();
        deadline += timeout_ms;
    }
    struct pollfd watched[2] =
    {
        { wake_pipe[0], POLLIN, 0 },
        { monitor_output, POLLIN, 0 }
    };
    int result = -1;
    for (unsigned int attempt = 0; attempt < MONITOR_EINTR_LIMIT; attempt++)
    {
        result = poll(watched, 2, timeout_ms);
        if (result >= 0 || errno != EINTR)
            break;
        if (timeout_ms > 0)
        {
            int64_t now = monotonic_ms();
            if (now < 0)
                return monitor_failed();
            int64_t remaining = deadline - now;
            if (remaining <= 0)
                return HIBY_BT_MONITOR_IDLE;
            if (remaining > INT_MAX)
                return monitor_failed();
            timeout_ms = (int)remaining;
        }
    }
    if (result < 0 || (watched[0].revents & (POLLERR | POLLHUP | POLLNVAL)))
        return monitor_failed();
    if (watched[0].revents & POLLIN)
        return consume_wake() ? HIBY_BT_MONITOR_WAKE : HIBY_BT_MONITOR_IDLE;
    if (!result || monitor_output < 0)
        return HIBY_BT_MONITOR_IDLE;
    if (watched[1].revents & (POLLERR | POLLHUP | POLLNVAL))
        return monitor_failed();
    bool changed = false;
    size_t consumed = 0;
    unsigned int interruptions = 0;
    while (consumed < MONITOR_READ_BUDGET)
    {
        char bytes[1024];
        ssize_t count = read(monitor_output, bytes, sizeof(bytes));
        if (count > 0)
        {
            consumed += (size_t)count;
            changed |= parse_output(bytes, (size_t)count);
            continue;
        }
        if (!count)
            return monitor_failed();
        if (errno == EINTR && ++interruptions < MONITOR_EINTR_LIMIT)
            continue;
        if (errno != EAGAIN)
            return monitor_failed();
        return changed ? HIBY_BT_MONITOR_CHANGED : HIBY_BT_MONITOR_IDLE;
    }
    return monitor_failed();
}

void hiby_bt_monitor_stop(void)
{
    close_descriptor(&monitor_output);
    reset_parser();
    if (reap_child())
        return;
    for (unsigned int stage = 0; stage < 2; stage++)
    {
        int notification = stage ? SIGKILL : SIGTERM;
        kill(monitor_group ? -monitor_child : monitor_child, notification);
        for (unsigned int step = 0; step < MONITOR_REAP_STEPS; step++)
        {
            if (reap_child())
                return;
            poll(NULL, 0, 10);
        }
    }
    reap_child();
}

void hiby_bt_monitor_shutdown(void)
{
    hiby_bt_monitor_stop();
    pthread_mutex_lock(&wake_mutex);
    close_descriptor(&wake_pipe[0]);
    close_descriptor(&wake_pipe[1]);
    wake_pending = false;
    pthread_mutex_unlock(&wake_mutex);
}

bool hiby_bt_monitor_active(void)
{
    return monitor_child > 0 && monitor_output >= 0;
}
