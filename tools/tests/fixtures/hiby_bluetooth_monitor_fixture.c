#define _GNU_SOURCE 1
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int pipe_failure = -1;
static int duplicate_failure = -1;
static bool fork_failure, exec_failure, fcntl_failure, read_failure;
static bool hold_reaping, clock_failure;
static bool checking_zero_wait;
static unsigned int read_interruptions, write_interruptions, poll_interruptions;
static unsigned int reap_interruptions, signal_calls, sleep_calls, fork_calls;
static int fixture_pipe2(int descriptors[2], int flags);
static pid_t fixture_fork(void);
static int fixture_execv(const char *path, char *const arguments[]);
static int fixture_fcntl(int descriptor, int command, int argument);
static ssize_t fixture_read(int descriptor, void *bytes, size_t length);
static ssize_t fixture_write(int descriptor, const void *bytes, size_t length);
static int fixture_poll(struct pollfd *watched, nfds_t count, int timeout);
static pid_t fixture_waitpid(pid_t child, int *status, int options);
static int fixture_kill(pid_t child, int notification);
static int fixture_clock_gettime(clockid_t clock_id, struct timespec *value);
static void fixture_abort(const char *expression, int line);

#define HIBY_BT_MONITOR_EXECUTABLE TEST_EXECUTABLE
#define pipe2 fixture_pipe2
#define fork fixture_fork
#define execv fixture_execv
#define fcntl fixture_fcntl
#define read fixture_read
#define write fixture_write
#define poll fixture_poll
#define waitpid fixture_waitpid
#define kill fixture_kill
#define clock_gettime fixture_clock_gettime
#include "bluetooth-monitor-hiby.c"
#undef pipe2
#undef fork
#undef execv
#undef fcntl
#undef read
#undef write
#undef poll
#undef waitpid
#undef kill
#undef clock_gettime

#define CHECK(expression) do { if (!(expression)) \
    fixture_abort(#expression, __LINE__); } while (0)

static void fixture_abort(const char *expression, int line)
{
    fprintf(stderr, "assertion at line %d: %s (errno=%d)\n", line, expression, errno);
    checking_zero_wait = false;
    pipe_failure = -1;
    duplicate_failure = -1;
    fork_failure = exec_failure = fcntl_failure = read_failure = false;
    hold_reaping = clock_failure = false;
    read_interruptions = write_interruptions = poll_interruptions = 0;
    reap_interruptions = 0;
    hiby_bt_monitor_shutdown();
    exit(90);
}

static int fixture_pipe2(int descriptors[2], int flags)
{
    if (!pipe_failure)
    {
        errno = EMFILE;
        return -1;
    }
    if (pipe_failure > 0)
        pipe_failure--;
    return pipe2(descriptors, flags);
}

static pid_t fixture_fork(void)
{
    fork_calls++;
    if (!fork_failure)
        return fork();
    errno = EAGAIN;
    return -1;
}

static int fixture_execv(const char *path, char *const arguments[])
{
    if (strcmp(path, TEST_EXECUTABLE))
        _exit(98);
    if (!exec_failure)
        return execv(path, arguments);
    errno = ENOENT;
    return -1;
}

static int fixture_fcntl(int descriptor, int command, int argument)
{
    if (command == F_DUPFD_CLOEXEC && duplicate_failure >= 0)
    {
        if (!duplicate_failure--)
        {
            errno = EMFILE;
            return -1;
        }
    }
    if (!fcntl_failure)
        return fcntl(descriptor, command, argument);
    errno = EMFILE;
    return -1;
}

static ssize_t fixture_read(int descriptor, void *bytes, size_t length)
{
    if (read_interruptions)
    {
        read_interruptions--;
        errno = EINTR;
        return -1;
    }
    if (read_failure)
    {
        errno = EIO;
        return -1;
    }
    return read(descriptor, bytes, length);
}

static ssize_t fixture_write(int descriptor, const void *bytes, size_t length)
{
    if (write_interruptions)
    {
        write_interruptions--;
        errno = EINTR;
        return -1;
    }
    return write(descriptor, bytes, length);
}

static int fixture_poll(struct pollfd *watched, nfds_t count, int timeout)
{
    CHECK(!checking_zero_wait || timeout == 0);
    if (poll_interruptions)
    {
        poll_interruptions--;
        errno = EINTR;
        return -1;
    }
    if (!count && timeout)
        sleep_calls++;
    return poll(watched, count, timeout);
}

static pid_t fixture_waitpid(pid_t child, int *status, int options)
{
    CHECK(!checking_zero_wait || options == WNOHANG);
    if (reap_interruptions)
    {
        reap_interruptions--;
        errno = EINTR;
        return -1;
    }
    if (hold_reaping)
        return 0;
    return waitpid(child, status, options);
}

static int fixture_kill(pid_t child, int notification)
{
    CHECK(!checking_zero_wait);
    CHECK(monitor_child > 0 && (child == monitor_child || child == -monitor_child));
    signal_calls++;
    return kill(child, notification);
}

static int fixture_clock_gettime(clockid_t clock_id, struct timespec *value)
{
    if (!clock_failure)
        return clock_gettime(clock_id, value);
    errno = EINVAL;
    return -1;
}

static enum hiby_bt_monitor_result wait_checked(int timeout)
{
    checking_zero_wait = timeout == 0;
    enum hiby_bt_monitor_result result = hiby_bt_monitor_wait(timeout);
    checking_zero_wait = false;
    return result;
}

#define hiby_bt_monitor_wait wait_checked

static double seconds(clockid_t clock_id)
{
    struct timespec value;
    CHECK(clock_gettime(clock_id, &value) == 0);
    return (double)value.tv_sec + (double)value.tv_nsec / 1000000000;
}

static void delay_ms(int milliseconds)
{
    struct timespec duration = { milliseconds / 1000,
        (milliseconds % 1000) * 1000000 };
    CHECK(nanosleep(&duration, NULL) == 0);
}

static int descriptor_count(void)
{
    DIR *directory = opendir("/proc/self/fd");
    CHECK(directory);
    int count = 0;
    struct dirent *entry;
    while ((entry = readdir(directory)))
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, ".."))
            count++;
    CHECK(closedir(directory) == 0);
    return count;
}

static long read_number(const char *name)
{
    char path[4096];
    CHECK(snprintf(path, sizeof(path), "%s/%s", TEST_DIRECTORY, name) <
        (int)sizeof(path));
    FILE *input = fopen(path, "r");
    if (!input)
        return -1;
    long value = -1;
    int received = fscanf(input, "%ld", &value);
    CHECK(fclose(input) == 0);
    return received == 1 ? value : -1;
}

static void set_mode(const char *mode)
{
    unlink(TEST_DIRECTORY "/ready");
    int input = open(TEST_DIRECTORY "/input", O_CREAT | O_WRONLY | O_TRUNC, 0600);
    CHECK(input >= 0);
    CHECK(close(input) == 0);
    FILE *configuration = fopen(TEST_DIRECTORY "/mode", "w");
    CHECK(configuration);
    CHECK(fprintf(configuration, "%s\n", mode) > 0);
    CHECK(fclose(configuration) == 0);
}

static void await_ready(void)
{
    double deadline = seconds(CLOCK_MONOTONIC) + 2;
    while (read_number("ready") != 1)
    {
        CHECK(seconds(CLOCK_MONOTONIC) < deadline);
        delay_ms(2);
    }
    CHECK(read_number("inherited") == 0);
}

static int start(const char *mode)
{
    set_mode(mode);
    CHECK(hiby_bt_monitor_init());
    CHECK(hiby_bt_monitor_start());
    await_ready();
    CHECK(hiby_bt_monitor_active());
    int input = open(TEST_DIRECTORY "/input", O_WRONLY | O_APPEND | O_CLOEXEC);
    CHECK(input >= 0);
    return input;
}

static void send_bytes(int input, const char *bytes, size_t length)
{
    size_t written = 0;
    double deadline = seconds(CLOCK_MONOTONIC) + 2;
    while (written < length)
    {
        ssize_t count = write(input, bytes + written, length - written);
        if (count > 0)
            written += (size_t)count;
        else
        {
            CHECK(count < 0 && (errno == EAGAIN || errno == EINTR));
            CHECK(seconds(CLOCK_MONOTONIC) < deadline);
            delay_ms(1);
        }
    }
}

#include "hiby_bluetooth_monitor_parser_fixture.c"

static void *delayed_wake(void *context)
{
    (void)context;
    delay_ms(60);
    hiby_bt_monitor_wake();
    return NULL;
}

static bool racing;
static void *racing_wake(void *context)
{
    (void)context;
    while (__atomic_load_n(&racing, __ATOMIC_ACQUIRE))
    {
        hiby_bt_monitor_wake();
        sched_yield();
    }
    return NULL;
}

int main(int count, char **arguments)
{
    CHECK(count == 2);
    const char *scenario = arguments[1];
    int baseline = descriptor_count();
    if (!strcmp(scenario, "parser"))
        parser_tests();
    else if (!strcmp(scenario, "inactive"))
    {
        CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_FAILED);
        CHECK(!hiby_bt_monitor_start());
        CHECK(hiby_bt_monitor_init());
        CHECK(hiby_bt_monitor_init());
        CHECK(!hiby_bt_monitor_active());
        CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
        double began = seconds(CLOCK_MONOTONIC);
        double cpu = seconds(CLOCK_PROCESS_CPUTIME_ID);
        CHECK(hiby_bt_monitor_wait(160) == HIBY_BT_MONITOR_IDLE);
        CHECK(seconds(CLOCK_MONOTONIC) - began >= 0.14);
        CHECK(seconds(CLOCK_PROCESS_CPUTIME_ID) - cpu < 0.04);
        CHECK(hiby_bt_monitor_wait(-2) == HIBY_BT_MONITOR_FAILED);
    }
    else if (!strcmp(scenario, "wake") || !strcmp(scenario, "wake-eintr"))
    {
        CHECK(hiby_bt_monitor_init());
        write_interruptions = !strcmp(scenario, "wake-eintr") ? 3 : 0;
        for (unsigned int repeat = 0; repeat < 10000; repeat++)
            hiby_bt_monitor_wake();
        CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_WAKE);
        CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
        pthread_t thread;
        CHECK(pthread_create(&thread, NULL, delayed_wake, NULL) == 0);
        double began = seconds(CLOCK_MONOTONIC);
        CHECK(hiby_bt_monitor_wait(-1) == HIBY_BT_MONITOR_WAKE);
        CHECK(seconds(CLOCK_MONOTONIC) - began < 0.5);
        CHECK(pthread_join(thread, NULL) == 0);
    }
    else if (!strcmp(scenario, "wake-race"))
    {
        racing = true;
        pthread_t thread;
        CHECK(pthread_create(&thread, NULL, racing_wake, NULL) == 0);
        for (unsigned int repeat = 0; repeat < 1000; repeat++)
        {
            CHECK(hiby_bt_monitor_init());
            hiby_bt_monitor_wait(0);
            hiby_bt_monitor_shutdown();
        }
        __atomic_store_n(&racing, false, __ATOMIC_RELEASE);
        CHECK(pthread_join(thread, NULL) == 0);
    }
    else if (!strcmp(scenario, "wake-eagain"))
    {
        CHECK(hiby_bt_monitor_init());
        char bytes[256];
        memset(bytes, 1, sizeof(bytes));
        while (write(wake_pipe[1], bytes, sizeof(bytes)) > 0) {}
        CHECK(errno == EAGAIN);
        hiby_bt_monitor_wake();
        CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_WAKE);
        CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
    }
    else if (!strcmp(scenario, "init-failure"))
    {
        pipe_failure = 0;
        CHECK(!hiby_bt_monitor_init());
        CHECK(wake_pipe[0] < 0 && wake_pipe[1] < 0);
        hiby_bt_monitor_wake();
        pipe_failure = -1;
        CHECK(hiby_bt_monitor_init());
    }
    else if (!strcmp(scenario, "spawn-failures"))
    {
        CHECK(hiby_bt_monitor_init());
        int initialized = descriptor_count();
        for (int stage = 0; stage < 2; stage++)
        {
            pipe_failure = stage;
            CHECK(!hiby_bt_monitor_start());
            CHECK(descriptor_count() == initialized);
        }
        pipe_failure = -1;
        fork_failure = true;
        CHECK(!hiby_bt_monitor_start());
        CHECK(descriptor_count() == initialized);
        fork_failure = false;
        fcntl_failure = true;
        CHECK(!hiby_bt_monitor_start());
        CHECK(descriptor_count() == initialized);
        fcntl_failure = false;
        exec_failure = true;
        CHECK(!hiby_bt_monitor_start());
        CHECK(!monitor_child && !hiby_bt_monitor_active());
        CHECK(descriptor_count() == initialized);
    }
    else if (!strcmp(scenario, "clock-failure"))
    {
        CHECK(hiby_bt_monitor_init());
        clock_failure = true;
        CHECK(!hiby_bt_monitor_start());
        CHECK(hiby_bt_monitor_wait(1) == HIBY_BT_MONITOR_FAILED);
        clock_failure = false;
    }
    else if (!strcmp(scenario, "reap-retention"))
    {
        int input = start("echo");
        hold_reaping = true;
        double began = seconds(CLOCK_MONOTONIC);
        hiby_bt_monitor_stop();
        CHECK(seconds(CLOCK_MONOTONIC) - began < 1.0);
        CHECK(monitor_child > 0);
        unsigned int forks = fork_calls;
        for (unsigned int repeat = 0; repeat < 30; repeat++)
            CHECK(!hiby_bt_monitor_start());
        CHECK(fork_calls == forks);
        hold_reaping = false;
        hiby_bt_monitor_stop();
        CHECK(!monitor_child);
        close(input);
    }
    else if (!strcmp(scenario, "external-reap"))
    {
        int input = start("exit");
        CHECK(waitpid(monitor_child, NULL, 0) == monitor_child);
        unsigned int signals = signal_calls;
        CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_FAILED);
        hiby_bt_monitor_stop();
        CHECK(signal_calls == signals && !monitor_child);
        close(input);
    }
    else if (!strcmp(scenario, "reap-eintr"))
    {
        int input = start("echo");
        reap_interruptions = 3;
        hiby_bt_monitor_stop();
        CHECK(!monitor_child);
        close(input);
    }
    else if (!strcmp(scenario, "blocked-signal"))
    {
        sigset_t mask, previous;
        sigemptyset(&mask);
        sigaddset(&mask, SIGTERM);
        CHECK(pthread_sigmask(SIG_BLOCK, &mask, &previous) == 0);
        int input = start("echo");
        double began = seconds(CLOCK_MONOTONIC);
        hiby_bt_monitor_stop();
        CHECK(seconds(CLOCK_MONOTONIC) - began < 0.2);
        CHECK(pthread_sigmask(SIG_SETMASK, &previous, NULL) == 0);
        close(input);
    }
    else if (!strcmp(scenario, "auto-reap-refused"))
    {
        CHECK(hiby_bt_monitor_init());
        struct sigaction previous, ignored;
        memset(&ignored, 0, sizeof(ignored));
        sigemptyset(&ignored.sa_mask);
        ignored.sa_handler = SIG_IGN;
        CHECK(sigaction(SIGCHLD, &ignored, &previous) == 0);
        CHECK(!hiby_bt_monitor_start());
        ignored.sa_handler = SIG_DFL;
        ignored.sa_flags = SA_NOCLDWAIT;
        CHECK(sigaction(SIGCHLD, &ignored, NULL) == 0);
        CHECK(!hiby_bt_monitor_start());
        CHECK(fork_calls == 0);
        CHECK(sigaction(SIGCHLD, &previous, NULL) == 0);
    }
    else if (!strcmp(scenario, "relocate-failure"))
    {
        int saved[3];
        for (int descriptor = 0; descriptor < 3; descriptor++)
        {
            saved[descriptor] = fcntl(descriptor, F_DUPFD_CLOEXEC, 16);
            CHECK(saved[descriptor] >= 16);
        }
        int initialized = descriptor_count();
        for (int stage = 0; stage < 2; stage++)
        {
            for (int descriptor = 0; descriptor < 3; descriptor++)
                close(descriptor);
            duplicate_failure = stage;
            int descriptors[2] = { -1, -1 };
            bool success = make_pipe(descriptors, 0);
            duplicate_failure = -1;
            for (int descriptor = 0; descriptor < 3; descriptor++)
                CHECK(dup2(saved[descriptor], descriptor) == descriptor);
            CHECK(!success && descriptors[0] == -1 && descriptors[1] == -1);
            CHECK(descriptor_count() == initialized);
        }
        for (int descriptor = 0; descriptor < 3; descriptor++)
            close(saved[descriptor]);
    }
    else if (!strcmp(scenario, "closed-stdio"))
    {
        int saved[3];
        for (int descriptor = 0; descriptor < 3; descriptor++)
            saved[descriptor] = fcntl(descriptor, F_DUPFD_CLOEXEC, 16);
        for (int descriptor = 0; descriptor < 3; descriptor++)
            close(descriptor);
        int input = start("echo");
        hiby_bt_monitor_shutdown();
        close(input);
        for (int descriptor = 0; descriptor < 3; descriptor++)
        {
            CHECK(dup2(saved[descriptor], descriptor) == descriptor);
            close(saved[descriptor]);
        }
    }
    else if (!strcmp(scenario, "descendant"))
    {
        CHECK(prctl(PR_SET_CHILD_SUBREAPER, 1) == 0);
        int input = start("descendant");
        pid_t descendant = (pid_t)read_number("descendant");
        CHECK(descendant > 0);
        hiby_bt_monitor_stop();
        bool reaped = false;
        for (unsigned int step = 0; step < 100; step++)
        {
            if (waitpid(descendant, NULL, WNOHANG) == descendant)
            {
                reaped = true;
                break;
            }
            delay_ms(2);
        }
        CHECK(reaped);
        close(input);
    }
    else if (!strcmp(scenario, "parent-exit"))
    {
        CHECK(prctl(PR_SET_CHILD_SUBREAPER, 1) == 0);
        pid_t owner = fork();
        CHECK(owner >= 0);
        if (!owner)
        {
            int input = start("echo");
            close(input);
            _exit(0);
        }
        int status = 0;
        CHECK(waitpid(owner, &status, 0) == owner);
        CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
        pid_t orphan = (pid_t)read_number("pid");
        CHECK(orphan > 0);
        bool reaped = false;
        for (unsigned int step = 0; step < 200; step++)
        {
            if (waitpid(orphan, &status, WNOHANG) == orphan)
            {
                reaped = true;
                break;
            }
            delay_ms(2);
        }
        if (!reaped)
        {
            kill(orphan, SIGKILL);
            waitpid(orphan, NULL, 0);
        }
        CHECK(reaped && WIFSIGNALED(status) && WTERMSIG(status) == SIGTERM);
    }
    else if (!strcmp(scenario, "cycles"))
    {
        CHECK(hiby_bt_monitor_init());
        int initialized = descriptor_count();
        for (unsigned int cycle = 0; cycle < 60; cycle++)
        {
            int input = start("echo");
            CHECK(hiby_bt_monitor_start());
            CHECK(fcntl(wake_pipe[0], F_GETFD) & FD_CLOEXEC);
            CHECK(fcntl(wake_pipe[1], F_GETFD) & FD_CLOEXEC);
            CHECK(fcntl(monitor_output, F_GETFL) & O_NONBLOCK);
            hiby_bt_monitor_stop();
            close(input);
            CHECK(!monitor_child);
            CHECK(descriptor_count() == initialized);
        }
    }
    else
    {
        const char *mode = "echo";
        if (!strcmp(scenario, "exit") || !strcmp(scenario, "closeoutput") ||
            !strcmp(scenario, "ignoreterm") || !strcmp(scenario, "stderr") ||
            !strcmp(scenario, "flood") || !strcmp(scenario, "eventflood"))
            mode = scenario;
        int unrelated = open(TEST_DIRECTORY "/mode", O_CREAT | O_RDWR, 0600);
        CHECK(unrelated >= 0);
        CHECK(fcntl(unrelated, F_SETFD, 0) == 0);
        int high_descriptor = -1;
        if (!strcmp(scenario, "inherited-high"))
        {
            high_descriptor = fcntl(unrelated, F_DUPFD, 2048);
            CHECK(high_descriptor >= 2048);
        }
        int input = start(mode);
        if (!strcmp(scenario, "event") || !strcmp(scenario, "read-eintr"))
        {
            send_bytes(input, header, sizeof(header) - 1);
            read_interruptions = !strcmp(scenario, "read-eintr") ? 3 : 0;
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_CHANGED);
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
        }
        else if (!strcmp(scenario, "split"))
        {
            send_bytes(input, header, sizeof(header) - 2);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_IDLE);
            send_bytes(input, "\n", 1);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_CHANGED);
        }
        else if (!strcmp(scenario, "coalesce"))
        {
            for (unsigned int repeat = 0; repeat < 10; repeat++)
                send_bytes(input, header, sizeof(header) - 1);
            delay_ms(40);
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_CHANGED);
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
        }
        else if (!strcmp(scenario, "wake-priority"))
        {
            send_bytes(input, header, sizeof(header) - 1);
            hiby_bt_monitor_wake();
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_WAKE);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_CHANGED);
        }
        else if (!strcmp(scenario, "payload"))
        {
            const char payload[] = "   string \"PropertiesChanged\"\n   string \"signal sender=:1.2 -> destination=(null destination) serial=1 path=/; interface=org.freedesktop.DBus.ObjectManager; member=InterfacesRemoved\"\n";
            send_bytes(input, payload, sizeof(payload) - 1);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_IDLE);
        }
        else if (!strcmp(scenario, "forged-name"))
        {
            char payload[1024];
            int length = snprintf(payload, sizeof(payload),
                "   string \"Headset\n%s\"\n", classic_header);
            CHECK(length > 0 && length < (int)sizeof(payload));
            send_bytes(input, payload, (size_t)length);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_IDLE);
        }
        else if (!strcmp(scenario, "name-acquired"))
        {
            const char acquired[] = "#type\ttimestamp\tserial\tsender\tdestination\tpath\tinterface\tmember\n#\t\t\t\t\tin_reply_to\nsig\t1.123456\t1\torg.freedesktop.DBus\t:1.17\t/org/freedesktop/DBus\torg.freedesktop.DBus\tNameAcquired\n";
            send_bytes(input, acquired, sizeof(acquired) - 1);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_IDLE);
        }
        else if (!strcmp(scenario, "profile-recovery"))
        {
            const char invalid[] = "sig\t1.123456\t4294967296\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded\n";
            send_bytes(input, invalid, sizeof(invalid) - 1);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_IDLE);
            send_bytes(input, header, sizeof(header) - 1);
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_CHANGED);
        }
        else if (!strcmp(scenario, "no-subscription"))
        {
            CHECK(hiby_bt_monitor_active());
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
            unsigned int forks = fork_calls;
            CHECK(hiby_bt_monitor_wait(160) == HIBY_BT_MONITOR_IDLE);
            CHECK(hiby_bt_monitor_active() && fork_calls == forks);
        }
        else if (!strcmp(scenario, "zero-idle") || !strcmp(scenario, "stderr") ||
                 !strcmp(scenario, "inherited-high"))
        {
            double began = seconds(CLOCK_MONOTONIC);
            for (unsigned int repeat = 0; repeat < 10000; repeat++)
                CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
            CHECK(seconds(CLOCK_MONOTONIC) - began < 0.5);
            double cpu = seconds(CLOCK_PROCESS_CPUTIME_ID);
            CHECK(hiby_bt_monitor_wait(160) == HIBY_BT_MONITOR_IDLE);
            CHECK(seconds(CLOCK_PROCESS_CPUTIME_ID) - cpu < 0.04);
        }
        else if (!strcmp(scenario, "poll-eintr"))
        {
            poll_interruptions = 100;
            double began = seconds(CLOCK_MONOTONIC);
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_FAILED);
            CHECK(seconds(CLOCK_MONOTONIC) - began < 0.05);
            poll_interruptions = 0;
        }
        else if (!strcmp(scenario, "read-failure"))
        {
            send_bytes(input, header, sizeof(header) - 1);
            read_failure = true;
            CHECK(hiby_bt_monitor_wait(500) == HIBY_BT_MONITOR_FAILED);
            read_failure = false;
        }
        else if (!strcmp(scenario, "ignoreterm"))
        {
            double began = seconds(CLOCK_MONOTONIC);
            hiby_bt_monitor_stop();
            CHECK(seconds(CLOCK_MONOTONIC) - began < 1.0);
            CHECK(!monitor_child && signal_calls >= 2);
        }
        else if (!strcmp(scenario, "exit") || !strcmp(scenario, "closeoutput") ||
                 !strcmp(scenario, "flood") || !strcmp(scenario, "eventflood"))
        {
            delay_ms(30);
            double began = seconds(CLOCK_MONOTONIC);
            unsigned int signals = signal_calls, sleeps = sleep_calls;
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_FAILED);
            CHECK(seconds(CLOCK_MONOTONIC) - began < 0.05);
            CHECK(signal_calls == signals && sleep_calls == sleeps);
            CHECK(!hiby_bt_monitor_active());
            CHECK(hiby_bt_monitor_wait(0) == HIBY_BT_MONITOR_IDLE);
            if (!strcmp(scenario, "closeoutput"))
            {
                CHECK(monitor_child > 0);
                CHECK(!hiby_bt_monitor_start());
            }
        }
        else
            CHECK(false);
        close(input);
        close(unrelated);
        if (high_descriptor >= 0)
            close(high_descriptor);
    }
    hiby_bt_monitor_shutdown();
    hiby_bt_monitor_wake();
    hiby_bt_monitor_shutdown();
    CHECK(!monitor_child && !hiby_bt_monitor_active());
    CHECK(descriptor_count() == baseline);
    errno = 0;
    CHECK(waitpid(-1, NULL, WNOHANG) < 0 && errno == ECHILD);
    return 0;
}
