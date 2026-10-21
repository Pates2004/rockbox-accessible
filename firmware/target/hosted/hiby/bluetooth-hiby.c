#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include "bluetooth-hiby.h"
#include "pcm-hiby.h"
#if defined(HIBY_R1) || defined(HIBY_BT_RFKILL_HOST_TEST)
#include "power-control-hiby.h"
#endif

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef HIBY_BT_BIN_DIRECTORY
#define HIBY_BT_BIN_DIRECTORY "/usr/bin"
#endif

#define BT_CTL HIBY_BT_BIN_DIRECTORY "/bluetoothctl"
#define BT_ALSA_CTL HIBY_BT_BIN_DIRECTORY "/bluealsa-cli"
#define BT_RESUME HIBY_BT_BIN_DIRECTORY "/bt_resume"
#define BT_OUTPUT_SIZE 16384
#define BT_CHILD_SLOTS 8
#ifndef HIBY_BT_SCAN_HOLD_MS
#define HIBY_BT_SCAN_HOLD_MS 8000
#endif
#ifndef HIBY_BT_ENDPOINT_TIMEOUT_MS
#define HIBY_BT_ENDPOINT_TIMEOUT_MS 6000
#endif
#ifndef HIBY_BT_COMMAND_TIMEOUT_MS
#define HIBY_BT_COMMAND_TIMEOUT_MS 10000
#endif
#ifndef HIBY_BT_RESUME_TIMEOUT_MS
#define HIBY_BT_RESUME_TIMEOUT_MS 30000
#endif

static pthread_mutex_t child_mutex = PTHREAD_MUTEX_INITIALIZER;
static pid_t child_slots[BT_CHILD_SLOTS];
static pthread_mutex_t cleanup_mutex = PTHREAD_MUTEX_INITIALIZER;
static char cleanup_address[18];

bool hiby_bt_backend_cleanup_pending(char address[18])
{
    pthread_mutex_lock(&cleanup_mutex);
    bool pending = cleanup_address[0] != '\0';
    if (address)
        memcpy(address, cleanup_address, sizeof(cleanup_address));
    pthread_mutex_unlock(&cleanup_mutex);
    return pending;
}

static void clear_cleanup_pending(const char *address)
{
    pthread_mutex_lock(&cleanup_mutex);
    if (!address || !strcasecmp(address, cleanup_address))
        memset(cleanup_address, 0, sizeof(cleanup_address));
    pthread_mutex_unlock(&cleanup_mutex);
}

static void record_cleanup_pending(const char *address)
{
    pthread_mutex_lock(&cleanup_mutex);
    if (!cleanup_address[0] || !strcasecmp(address, cleanup_address))
        snprintf(cleanup_address, sizeof(cleanup_address), "%s", address);
    pthread_mutex_unlock(&cleanup_mutex);
}

static int reserve_child(void)
{
    pthread_mutex_lock(&child_mutex);
    int available = -1;
    for (int position = 0; position < BT_CHILD_SLOTS; position++)
    {
        if (child_slots[position] > 0)
        {
            int status;
            pid_t result = waitpid(child_slots[position], &status, WNOHANG);
            if (result == child_slots[position] || (result < 0 && errno == ECHILD))
                child_slots[position] = 0;
        }
        if (!child_slots[position])
            available = position;
    }
    if (available >= 0)
        child_slots[available] = -1;
    pthread_mutex_unlock(&child_mutex);
    return available;
}

static enum hiby_bt_error route_device(const char *device,
    hiby_bt_cancel_callback cancelled, void *context)
{
    int result = pcm_alsa_switch_playback_device_cancellable(device, cancelled, context);
    if (!result)
        return HIBY_BT_OK;
    if (result == -ECANCELED)
        return HIBY_BT_CANCELLED;
    if (result == -ETIMEDOUT)
        return HIBY_BT_TIMEOUT;
    if (result == -EBUSY)
        return HIBY_BT_BUSY;
    return HIBY_BT_AUDIO_FAILED;
}

static void release_child(int slot, pid_t deferred)
{
    pthread_mutex_lock(&child_mutex);
    child_slots[slot] = deferred;
    pthread_mutex_unlock(&child_mutex);
}

static long long monotonic_ms(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
        return -1;
    return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

bool hiby_bt_valid_address(const char *address)
{
    if (!address || strlen(address) != 17)
        return false;
    for (size_t offset = 0; offset < 17; offset++)
    {
        if (offset % 3 == 2)
        {
            if (address[offset] != ':')
                return false;
        }
        else if (!isxdigit((unsigned char)address[offset]))
            return false;
    }
    return true;
}

static void copy_name(char *destination, size_t capacity,
                      const char *source, size_t length)
{
    size_t used = 0;
    for (size_t offset = 0; offset < length && used + 1 < capacity;)
    {
        unsigned char character = (unsigned char)source[offset];
        if (character == 27)
        {
            offset++;
            if (offset < length && source[offset] == '[')
            {
                offset++;
                while (offset < length && !((unsigned char)source[offset] >= 0x40 &&
                       (unsigned char)source[offset] <= 0x7e))
                    offset++;
                if (offset < length)
                    offset++;
            }
            continue;
        }
        if (character < 32 || character == 127)
        {
            offset++;
            continue;
        }
        size_t width = character < 0x80 ? 1 :
            character >= 0xc2 && character <= 0xdf ? 2 :
            character >= 0xe0 && character <= 0xef ? 3 :
            character >= 0xf0 && character <= 0xf4 ? 4 : 0;
        bool valid = width && offset + width <= length;
        for (size_t continuation = 1; valid && continuation < width; continuation++)
            valid = ((unsigned char)source[offset + continuation] & 0xc0) == 0x80;
        if (valid && width >= 3)
        {
            unsigned char second = (unsigned char)source[offset + 1];
            valid = !(character == 0xe0 && second < 0xa0) &&
                    !(character == 0xed && second >= 0xa0) &&
                    !(character == 0xf0 && second < 0x90) &&
                    !(character == 0xf4 && second >= 0x90);
        }
        if (!valid)
        {
            offset++;
            continue;
        }
        if (used + width >= capacity)
            break;
        memcpy(destination + used, source + offset, width);
        used += width;
        offset += width;
    }
    while (used && destination[used - 1] == ' ')
        used--;
    destination[used] = '\0';
}

static int safe_pipe(int descriptors[2])
{
    if (pipe2(descriptors, O_CLOEXEC) != 0)
        return -1;
    for (size_t position = 0; position < 2; position++)
    {
        if (descriptors[position] >= 3)
            continue;
        int replacement = fcntl(descriptors[position], F_DUPFD_CLOEXEC, 3);
        if (replacement < 0)
        {
            close(descriptors[0]);
            close(descriptors[1]);
            return -1;
        }
        close(descriptors[position]);
        descriptors[position] = replacement;
    }
    return 0;
}

static bool drain_output(int descriptor, char *output, size_t capacity, size_t *used)
{
    size_t budget = BT_OUTPUT_SIZE;
    unsigned int interrupted = 0;
    while (budget)
    {
        char discarded[1];
        size_t remaining = capacity - *used - 1;
        ssize_t received = read(descriptor, remaining ? output + *used : discarded,
                                remaining < budget ? remaining ? remaining : 1 : budget);
        if (received == 0 || (received < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)))
            return true;
        if (received < 0)
        {
            if (errno == EINTR && ++interrupted < 8)
                continue;
            return false;
        }
        if (!remaining)
            return false;
        *used += (size_t)received;
        budget -= (size_t)received;
        output[*used] = '\0';
    }
    return false;
}

static bool output_message(const char *output, const char *const messages[], bool agent)
{
    const char *line = output;
    while (*line)
    {
        const char *end = strchr(line, '\n');
        if (!end)
            end = line + strlen(line);
        char record[256];
        copy_name(record, sizeof(record), line, (size_t)(end - line));
        const char *message = record;
        while (*message == ' ')
            message++;
        if (agent && !strncmp(message, "[agent] ", 8))
        {
            message += 8;
            while (*message == ' ')
                message++;
        }
        for (size_t position = 0; messages[position]; position++)
            if (!strncmp(message, messages[position], strlen(messages[position])))
                return true;
        line = *end ? end + 1 : end;
    }
    return false;
}

static bool needs_pin(const char *output)
{
    const char *const messages[] = {"Enter PIN", "Enter passkey", "Confirm passkey",
                                   "Request confirmation", NULL};
    return output_message(output, messages, true);
}

static bool command_error(const char *output)
{
    const char *const messages[] = {"Invalid command", "Unknown command", "org.bluez.Error.",
        "Failed to ", "No default controller available", "not available", NULL};
    return output_message(output, messages, false);
}

static void strip_terminal_codes(char *output)
{
    size_t destination = 0;
    for (size_t offset = 0; output[offset];)
    {
        if (output[offset] == 27 && output[offset + 1] == '[')
        {
            offset += 2;
            while (output[offset] && !((unsigned char)output[offset] >= 0x40 &&
                   (unsigned char)output[offset] <= 0x7e))
                offset++;
            if (output[offset])
                offset++;
        }
        else
            output[destination++] = output[offset++];
    }
    output[destination] = '\0';
}

size_t hiby_bt_parse_devices(const char *text, struct hiby_bt_device *devices,
                            size_t count, size_t capacity, bool paired)
{
    if (!text || !devices || count > capacity)
        return count;
    const char *line = text;
    while (*line)
    {
        const char *end = strchr(line, '\n');
        if (!end)
            end = line + strlen(line);
        const char *entry = line;
        while (entry < end && (*entry == ' ' || *entry == '\t'))
            entry++;
        if (end - entry >= 25 && !strncmp(entry, "Device ", 7))
        {
            char address[18];
            memcpy(address, entry + 7, 17);
            address[17] = '\0';
            if (hiby_bt_valid_address(address) && entry[24] == ' ')
            {
                size_t position = 0;
                while (position < count && strcasecmp(devices[position].address, address))
                    position++;
                if (position < capacity)
                {
                    if (position == count)
                    {
                        memset(&devices[position], 0, sizeof(devices[position]));
                        for (size_t offset = 0; offset < sizeof(address); offset++)
                            devices[position].address[offset] = (char)toupper((unsigned char)address[offset]);
                        count++;
                    }
                    devices[position].paired |= paired;
                    copy_name(devices[position].name, sizeof(devices[position].name),
                              entry + 25, (size_t)(end - (entry + 25)));
                    if (!devices[position].name[0])
                        memcpy(devices[position].name, address, sizeof(address));
                }
            }
        }
        line = *end ? end + 1 : end;
    }
    return count;
}

static enum hiby_bt_error run_command(const char *const arguments[],
    const char *input, unsigned int hold_ms, unsigned int timeout_ms,
    char *output, size_t capacity, hiby_bt_cancel_callback cancelled, void *context)
{
    int output_pipe[2] = {-1, -1};
    int input_pipe[2] = {-1, -1};
    enum hiby_bt_error result = HIBY_BT_COMMAND_FAILED;
    size_t used = 0;
    int status = 0;
    bool reaped = false;
    bool input_closed = false;
    bool finish_sent = false;
    sigset_t blocked_signals;
    sigset_t previous_signals;
    long long start = monotonic_ms();
    if (!capacity || start < 0)
        return result;
    output[0] = '\0';
    if (cancelled && cancelled(context))
        return HIBY_BT_CANCELLED;
    if (access(arguments[0], X_OK) != 0)
        return HIBY_BT_UNAVAILABLE;
    int child_slot = reserve_child();
    if (child_slot < 0)
        return HIBY_BT_COMMAND_FAILED;
    if (safe_pipe(output_pipe) != 0)
    {
        release_child(child_slot, 0);
        return result;
    }
    if (safe_pipe(input_pipe) != 0)
    {
        close(output_pipe[0]);
        close(output_pipe[1]);
        release_child(child_slot, 0);
        return result;
    }
    sigemptyset(&blocked_signals);
    sigaddset(&blocked_signals, SIGPIPE);
    if (pthread_sigmask(SIG_BLOCK, &blocked_signals, &previous_signals) != 0)
    {
        close(input_pipe[0]);
        close(input_pipe[1]);
        close(output_pipe[0]);
        close(output_pipe[1]);
        release_child(child_slot, 0);
        return result;
    }
    char *const environment[] = {"LC_ALL=C", "LANG=C", "TERM=dumb",
        "PATH=/usr/bin:/bin:/usr/sbin:/sbin", NULL};
    pid_t process = fork();
    if (process == 0)
    {
        if (setpgid(0, 0) != 0)
            _exit(125);
        if (dup2(input_pipe[0], STDIN_FILENO) < 0 ||
            dup2(output_pipe[1], STDOUT_FILENO) < 0 ||
            dup2(output_pipe[1], STDERR_FILENO) < 0)
            _exit(126);
        close(input_pipe[0]);
        close(input_pipe[1]);
        close(output_pipe[0]);
        close(output_pipe[1]);
        sigprocmask(SIG_SETMASK, &previous_signals, NULL);
        execve(arguments[0], (char *const *)arguments, environment);
        _exit(127);
    }
    close(output_pipe[1]);
    close(input_pipe[0]);
    if (process < 0)
        goto finished;
    if (setpgid(process, process) != 0 && errno != EACCES && errno != ESRCH)
        goto terminate;
    if (fcntl(output_pipe[0], F_SETFL, O_NONBLOCK) < 0 ||
        fcntl(input_pipe[1], F_SETFL, O_NONBLOCK) < 0)
        goto terminate;
    size_t input_offset = 0;
    size_t input_size = input ? strlen(input) : 0;
    struct pollfd pending = {.fd = output_pipe[0], .events = POLLIN};
    for (;;)
    {
        long long now = monotonic_ms();
        if (cancelled && cancelled(context))
        {
            result = HIBY_BT_CANCELLED;
            break;
        }
        if (now < 0 || now - start >= timeout_ms)
        {
            result = HIBY_BT_TIMEOUT;
            break;
        }
        if (!input_closed && input_offset < input_size)
        {
            ssize_t written = write(input_pipe[1], input + input_offset, input_size - input_offset);
            if (written > 0)
                input_offset += (size_t)written;
            else if (written < 0 && errno != EAGAIN && errno != EINTR)
                break;
        }
        if (!input_closed && input_offset == input_size && (unsigned long long)(now - start) >= hold_ms)
        {
            if (hold_ms && !finish_sent)
            {
                input = "scan off\nquit\n";
                input_offset = 0;
                input_size = strlen(input);
                finish_sent = true;
            }
            else
            {
                close(input_pipe[1]);
                input_closed = true;
            }
        }
        if (!drain_output(output_pipe[0], output, capacity, &used))
            goto terminate;
        if (needs_pin(output))
        {
            result = HIBY_BT_PIN_UNSUPPORTED;
            break;
        }
        pid_t wait_result = waitpid(process, &status, WNOHANG);
        if (wait_result == process)
        {
            reaped = true;
            result = WIFEXITED(status) && WEXITSTATUS(status) == 0 ? HIBY_BT_OK : HIBY_BT_COMMAND_FAILED;
            if (!drain_output(output_pipe[0], output, capacity, &used))
                result = HIBY_BT_COMMAND_FAILED;
            if (needs_pin(output))
                result = HIBY_BT_PIN_UNSUPPORTED;
            break;
        }
        if (wait_result < 0 && errno != EINTR)
        {
            if (errno == ECHILD)
                reaped = true;
            break;
        }
        poll(&pending, 1, 25);
        if (pending.revents & POLLHUP)
            pending.fd = -1;
    }
terminate:
    if (process > 0 && (!reaped || result != HIBY_BT_OK))
        kill(-process, SIGKILL);
    if (!reaped)
    {
        kill(process, SIGKILL);
        for (unsigned int attempt = 0; attempt < 25; attempt++)
        {
            pid_t wait_result = waitpid(process, &status, WNOHANG);
            if (wait_result == process || (wait_result < 0 && errno == ECHILD))
            {
                reaped = true;
                break;
            }
            struct timespec delay = {.tv_nsec = 10000000};
            nanosleep(&delay, NULL);
        }
    }
finished:
    if (!input_closed)
        close(input_pipe[1]);
    close(output_pipe[0]);
    if (!sigismember(&previous_signals, SIGPIPE))
    {
        struct timespec no_wait = {0, 0};
        while (sigtimedwait(&blocked_signals, NULL, &no_wait) >= 0) {}
    }
    pthread_sigmask(SIG_SETMASK, &previous_signals, NULL);
    release_child(child_slot, process > 0 && !reaped ? process : 0);
    strip_terminal_codes(output);
    return result;
}

static enum hiby_bt_error ctl_timeout(const char *command, const char *address,
    char *output, size_t capacity, unsigned int timeout,
    hiby_bt_cancel_callback cancelled, void *context)
{
    const char *arguments[] = {BT_CTL, command, address, NULL};
    enum hiby_bt_error result = run_command(arguments, NULL, 0,
        timeout, output, capacity, cancelled, context);
    if (result == HIBY_BT_OK && command_error(output))
        result = HIBY_BT_COMMAND_FAILED;
    return result;
}

static enum hiby_bt_error ctl(const char *command, const char *address,
    char *output, size_t capacity, hiby_bt_cancel_callback cancelled, void *context)
{
    return ctl_timeout(command, address, output, capacity, HIBY_BT_COMMAND_TIMEOUT_MS,
                       cancelled, context);
}

static bool property_is(const char *text, const char *property, const char *value)
{
    const char *line = text;
    size_t length = strlen(property);
    size_t value_length = strlen(value);
    while (*line)
    {
        while (*line == ' ' || *line == '\t')
            line++;
        if (!strncmp(line, property, length) && !strncmp(line + length, ": ", 2) &&
            !strncmp(line + length + 2, value, value_length) &&
            (line[length + 2 + value_length] == '\0' || line[length + 2 + value_length] == '\r' ||
             line[length + 2 + value_length] == '\n'))
            return true;
        const char *next = strchr(line, '\n');
        if (!next)
            break;
        line = next + 1;
    }
    return false;
}

static bool property_yes(const char *text, const char *property)
{
    return property_is(text, property, "yes");
}

static enum hiby_bt_error boolean_property(const char *output, const char *property, bool *value)
{
    bool yes = property_yes(output, property);
    if (yes == property_is(output, property, "no"))
        return HIBY_BT_COMMAND_FAILED;
    *value = yes;
    return HIBY_BT_OK;
}

static enum hiby_bt_error connection_property(const char *output, bool *connected)
{
    return boolean_property(output, "Connected", connected);
}

static bool info_matches_address(const char *output, const char *address)
{
    bool found = false;
    const char *line = output;
    while (*line)
    {
        const char *end = strchr(line, '\n');
        if (!end)
            end = line + strlen(line);
        while (line < end && (*line == ' ' || *line == '\t'))
            line++;
        if (end - line >= 7 && !strncmp(line, "Device ", 7))
        {
            if (found || end - line < 24 || strncasecmp(line + 7, address, 17) ||
                (end - line > 24 && line[24] != ' ' && line[24] != '\r'))
                return false;
            found = true;
        }
        line = *end ? end + 1 : end;
    }
    return found;
}

static enum hiby_bt_error read_info(const char *address, char *output,
    hiby_bt_cancel_callback cancelled, void *context)
{
    enum hiby_bt_error result = ctl("info", address, output, BT_OUTPUT_SIZE, cancelled, context);
    return result == HIBY_BT_OK && !info_matches_address(output, address) ?
        HIBY_BT_COMMAND_FAILED : result;
}

static enum hiby_bt_error read_connection(const char *address, bool *connected,
    char *output, hiby_bt_cancel_callback cancelled, void *context)
{
    enum hiby_bt_error result = read_info(address, output, cancelled, context);
    return result == HIBY_BT_OK ? connection_property(output, connected) : result;
}

static bool valid_device_list(const char *output)
{
    const char *line = output;
    while (*line)
    {
        const char *end = strchr(line, '\n');
        if (!end)
            end = line + strlen(line);
        while (line < end && (*line == ' ' || *line == '\t'))
            line++;
        if (end - line >= 7 && !strncmp(line, "Device ", 7))
        {
            if (end - line < 25 || line[24] != ' ')
                return false;
            char address[18];
            memcpy(address, line + 7, 17);
            address[17] = '\0';
            if (!hiby_bt_valid_address(address))
                return false;
        }
        else if (line < end && !(end - line == 1 && *line == '\r') &&
                 strncmp(line, "[NEW] ", 6) && strncmp(line, "[CHG] ", 6) &&
                 strncmp(line, "[DEL] ", 6) && strncmp(line, "[bluetooth]#", 12))
            return false;
        line = *end ? end + 1 : end;
    }
    return true;
}

static enum hiby_bt_error find_connected_peer(char *address, char *output,
    hiby_bt_cancel_callback cancelled, void *context)
{
    address[0] = '\0';
    long long started = monotonic_ms();
    if (started < 0)
        return HIBY_BT_COMMAND_FAILED;
    enum hiby_bt_error result = ctl("devices", NULL, output, BT_OUTPUT_SIZE, cancelled, context);
    if (result != HIBY_BT_OK)
        return result;
    if (!valid_device_list(output))
        return HIBY_BT_COMMAND_FAILED;
    struct hiby_bt_device peers[HIBY_BT_MAX_DEVICES + 1];
    size_t count = hiby_bt_parse_devices(output, peers, 0, HIBY_BT_MAX_DEVICES + 1, false);
    if (count > HIBY_BT_MAX_DEVICES)
        return HIBY_BT_BUSY;
    for (size_t position = 0; position < count; position++)
    {
        if (cancelled && cancelled(context))
            return HIBY_BT_CANCELLED;
        long long now = monotonic_ms();
        if (now < 0)
            return HIBY_BT_COMMAND_FAILED;
        long long remaining = HIBY_BT_COMMAND_TIMEOUT_MS - (now - started);
        if (remaining <= 0)
            return HIBY_BT_TIMEOUT;
        result = ctl_timeout("info", peers[position].address, output, BT_OUTPUT_SIZE,
                             (unsigned int)remaining, cancelled, context);
        if (result != HIBY_BT_OK)
            return result;
        if (!info_matches_address(output, peers[position].address))
            return HIBY_BT_COMMAND_FAILED;
        bool connected = false;
        result = connection_property(output, &connected);
        if (result != HIBY_BT_OK)
            return result;
        if (connected)
        {
            if (address[0])
                return HIBY_BT_BUSY;
            memcpy(address, peers[position].address, 18);
        }
    }
    return cancelled && cancelled(context) ? HIBY_BT_CANCELLED : HIBY_BT_OK;
}

static enum hiby_bt_error disconnect_peer(const char *address, char *output,
    hiby_bt_cancel_callback cancelled, void *context)
{
    bool connected = false;
    enum hiby_bt_error result = read_connection(address, &connected, output, cancelled, context);
    if (result != HIBY_BT_OK || !connected)
    {
        if (result == HIBY_BT_OK)
            clear_cleanup_pending(address);
        return result;
    }
    result = ctl("disconnect", address, output, BT_OUTPUT_SIZE, cancelled, context);
    if (result == HIBY_BT_OK)
        result = read_connection(address, &connected, output, cancelled, context);
    if (result == HIBY_BT_OK && connected)
        return HIBY_BT_CONNECT_FAILED;
    if (result == HIBY_BT_OK)
        clear_cleanup_pending(address);
    return result;
}

static bool controller_suspended(void)
{
#if defined(HIBY_R1) || defined(HIBY_BT_RFKILL_HOST_TEST)
    bool blocked = false;
    return hiby_bluetooth_rfkill_blocked(&blocked) == 0 && blocked;
#else
    return false;
#endif
}

static enum hiby_bt_error read_power(struct hiby_bt_snapshot *state,
    char *output, hiby_bt_cancel_callback cancelled, void *context, bool *suspended)
{
    state->power_known = false;
    if (suspended)
        *suspended = false;
    if (cancelled && cancelled(context))
        return HIBY_BT_CANCELLED;
    if (controller_suspended())
    {
        state->enabled = false;
        state->power_known = true;
        if (suspended)
            *suspended = true;
        return HIBY_BT_OK;
    }
    enum hiby_bt_error result = ctl("show", NULL, output, BT_OUTPUT_SIZE, cancelled, context);
    if (result != HIBY_BT_OK)
        return result;
    bool enabled = property_yes(output, "Powered");
    if (enabled == property_is(output, "Powered", "no"))
        return HIBY_BT_COMMAND_FAILED;
    state->enabled = enabled;
    state->power_known = true;
    return HIBY_BT_OK;
}

static enum hiby_bt_error list_devices(struct hiby_bt_snapshot *state,
    char *output, hiby_bt_cancel_callback cancelled, void *context)
{
    enum hiby_bt_error result = ctl("paired-devices", NULL, output, BT_OUTPUT_SIZE, cancelled, context);
    if (result != HIBY_BT_OK)
        return result;
    if (!valid_device_list(output))
        return HIBY_BT_COMMAND_FAILED;
    struct hiby_bt_device devices[HIBY_BT_MAX_DEVICES] = {0};
    size_t count = hiby_bt_parse_devices(output, devices, 0, HIBY_BT_MAX_DEVICES, true);
    result = ctl("devices", NULL, output, BT_OUTPUT_SIZE, cancelled, context);
    if (result == HIBY_BT_OK)
    {
        if (!valid_device_list(output))
            return HIBY_BT_COMMAND_FAILED;
        count = hiby_bt_parse_devices(output, devices, count, HIBY_BT_MAX_DEVICES, false);
        memcpy(state->devices, devices, sizeof(devices));
        state->count = count;
    }
    return result;
}

static enum hiby_bt_error pcm_ready(const char *address, char *output, unsigned int timeout,
    hiby_bt_cancel_callback cancelled, void *context)
{
    char expected[96];
    char underscored[18];
    for (size_t offset = 0; offset < sizeof(underscored); offset++)
        underscored[offset] = address[offset] == ':' ? '_' : (char)toupper((unsigned char)address[offset]);
    snprintf(expected, sizeof(expected), "/org/bluealsa/hci0/dev_%s/a2dpsrc/sink", underscored);
    const char *arguments[] = {BT_ALSA_CTL, "list-pcms", NULL};
    enum hiby_bt_error result = run_command(arguments, NULL, 0, timeout, output, BT_OUTPUT_SIZE, cancelled, context);
    if (result != HIBY_BT_OK)
        return result;
    size_t expected_length = strlen(expected);
    const char *line = output;
    while (*line)
    {
        const char *next = strchr(line, '\n');
        const char *end = next ? next : line + strlen(line);
        if (end > line && end[-1] == '\r')
            end--;
        if ((size_t)(end - line) == expected_length && !memcmp(line, expected, expected_length))
            return HIBY_BT_OK;
        if (!next)
            break;
        line = next + 1;
    }
    return HIBY_BT_CONNECT_FAILED;
}

enum hiby_bt_error hiby_bt_backend_execute(enum hiby_bt_operation operation,
    const char *address, struct hiby_bt_snapshot *state,
    hiby_bt_cancel_callback cancelled, void *context)
{
    if (!state)
        return HIBY_BT_COMMAND_FAILED;
    state->power_known = false;
    if (operation < HIBY_BT_ENABLE || operation > HIBY_BT_VERIFY_LINK)
        return HIBY_BT_COMMAND_FAILED;
    bool connecting = operation == HIBY_BT_CONNECT || operation == HIBY_BT_CONNECT_PAIRED;
    if (cancelled && cancelled(context))
        return HIBY_BT_CANCELLED;
    if ((connecting || operation == HIBY_BT_REMOVE) &&
        !hiby_bt_valid_address(address))
        return HIBY_BT_INVALID_ADDRESS;
    if (connecting)
    {
        char pending[18];
        if (hiby_bt_backend_cleanup_pending(pending) && strcasecmp(pending, address))
            return HIBY_BT_BUSY;
    }
    bool disconnect_active = operation == HIBY_BT_DISCONNECT || operation == HIBY_BT_DISABLE ||
        (operation == HIBY_BT_REMOVE && !strcasecmp(state->connected_address, address));
    enum hiby_bt_error route_result = HIBY_BT_OK;
    if (disconnect_active)
    {
        route_result = route_device("plughw:0,0", cancelled, context);
        if (route_result != HIBY_BT_OK &&
            (operation != HIBY_BT_DISABLE || route_result == HIBY_BT_CANCELLED))
            return route_result;
    }
    state->available = access(BT_CTL, X_OK) == 0 &&
        (operation != HIBY_BT_ENABLE || access(BT_ALSA_CTL, X_OK) == 0);
    if (!state->available && !(operation == HIBY_BT_VERIFY_LINK && controller_suspended()))
        return HIBY_BT_UNAVAILABLE;
    char *output = malloc(BT_OUTPUT_SIZE);
    if (!output)
        return HIBY_BT_COMMAND_FAILED;
    enum hiby_bt_error result = HIBY_BT_OK;
    bool owned_connection = false;
    if (operation == HIBY_BT_SCAN || connecting)
    {
        result = read_power(state, output, cancelled, context, NULL);
        if (result != HIBY_BT_OK)
            goto complete;
        if (!state->enabled)
        {
            result = HIBY_BT_POWERED_OFF;
            goto complete;
        }
        if (access(BT_ALSA_CTL, X_OK) != 0)
        {
            state->available = false;
            result = HIBY_BT_UNAVAILABLE;
            goto complete;
        }
    }
    if (operation == HIBY_BT_ENABLE)
    {
        bool suspended = controller_suspended();
        if (!suspended)
            result = ctl("power", "on", output, BT_OUTPUT_SIZE, cancelled, context);
        if (suspended || (result != HIBY_BT_OK && result != HIBY_BT_CANCELLED))
        {
            const char *arguments[] = {BT_RESUME, NULL};
            result = run_command(arguments, NULL, 0, HIBY_BT_RESUME_TIMEOUT_MS,
                                 output, BT_OUTPUT_SIZE, cancelled, context);
            if (result == HIBY_BT_OK)
                result = ctl("power", "on", output, BT_OUTPUT_SIZE, cancelled, context);
        }
        if (result != HIBY_BT_CANCELLED)
        {
            enum hiby_bt_error observed = read_power(state, output, cancelled, context, NULL);
            if (result == HIBY_BT_OK || observed == HIBY_BT_CANCELLED)
                result = observed;
            if (result == HIBY_BT_OK && !state->enabled)
                result = HIBY_BT_COMMAND_FAILED;
        }
        if (result == HIBY_BT_OK)
            result = list_devices(state, output, cancelled, context);
    }
    else if (operation == HIBY_BT_SCAN)
    {
        const char *arguments[] = {BT_CTL, NULL};
        result = run_command(arguments, "scan on\n", HIBY_BT_SCAN_HOLD_MS,
                             HIBY_BT_SCAN_HOLD_MS + HIBY_BT_COMMAND_TIMEOUT_MS,
                             output, BT_OUTPUT_SIZE, cancelled, context);
        if (result == HIBY_BT_OK && !strstr(output, "Discovery started") &&
            !strstr(output, "Discovering: yes"))
            result = HIBY_BT_COMMAND_FAILED;
        if (result == HIBY_BT_OK)
            result = list_devices(state, output, cancelled, context);
    }
    else if (connecting)
    {
        bool already_connected = true;
        bool paired = false;
        result = read_info(address, output, cancelled, context);
        if (result == HIBY_BT_OK)
            result = connection_property(output, &already_connected);
        if (result == HIBY_BT_OK)
            result = boolean_property(output, "Paired", &paired);
        if (result == HIBY_BT_OK && operation == HIBY_BT_CONNECT_PAIRED)
        {
            bool trusted = false;
            result = boolean_property(output, "Trusted", &trusted);
            if (result == HIBY_BT_OK && (!paired || !trusted))
                result = HIBY_BT_CONNECT_FAILED;
        }
        if (result == HIBY_BT_OK && !already_connected)
            clear_cleanup_pending(address);
        if (result == HIBY_BT_OK && !paired)
        {
            result = ctl("pair", address, output, BT_OUTPUT_SIZE, cancelled, context);
            if (result == HIBY_BT_OK)
                result = read_info(address, output, cancelled, context);
            if (result == HIBY_BT_OK)
                result = boolean_property(output, "Paired", &paired);
            if (result == HIBY_BT_OK && !paired)
                result = HIBY_BT_PAIR_FAILED;
            else if (result == HIBY_BT_COMMAND_FAILED)
                result = HIBY_BT_PAIR_FAILED;
        }
        if (result == HIBY_BT_OK && operation == HIBY_BT_CONNECT)
            result = ctl("trust", address, output, BT_OUTPUT_SIZE, cancelled, context);
        if (result == HIBY_BT_OK &&
            (operation != HIBY_BT_CONNECT_PAIRED || !already_connected))
        {
            owned_connection = !already_connected &&
                strcasecmp(state->connected_address, address) != 0;
            result = ctl("connect", address, output, BT_OUTPUT_SIZE, cancelled, context);
        }
        if (result == HIBY_BT_OK)
            result = read_info(address, output, cancelled, context);
        if (result == HIBY_BT_OK)
        {
            bool connected = false;
            result = connection_property(output, &connected);
            if (result == HIBY_BT_OK && !connected)
                result = HIBY_BT_CONNECT_FAILED;
            if (result == HIBY_BT_OK && operation == HIBY_BT_CONNECT_PAIRED)
            {
                bool trusted = false;
                result = boolean_property(output, "Paired", &paired);
                if (result == HIBY_BT_OK)
                    result = boolean_property(output, "Trusted", &trusted);
                if (result == HIBY_BT_OK && (!paired || !trusted))
                    result = HIBY_BT_CONNECT_FAILED;
            }
        }
        if (result == HIBY_BT_OK)
        {
            long long started = monotonic_ms();
            if (started < 0)
            {
                result = HIBY_BT_COMMAND_FAILED;
                goto complete;
            }
            for (;;)
            {
                long long now = monotonic_ms();
                if (now < 0)
                {
                    result = HIBY_BT_COMMAND_FAILED;
                    break;
                }
                long long remaining = HIBY_BT_ENDPOINT_TIMEOUT_MS - (now - started);
                if (remaining <= 0)
                {
                    result = HIBY_BT_CONNECT_FAILED;
                    break;
                }
                unsigned int timeout = remaining < 2000 ? (unsigned int)remaining : 2000;
                result = pcm_ready(address, output, timeout, cancelled, context);
                if (result == HIBY_BT_CANCELLED)
                    break;
                now = monotonic_ms();
                if (now < 0)
                {
                    result = HIBY_BT_COMMAND_FAILED;
                    break;
                }
                remaining = HIBY_BT_ENDPOINT_TIMEOUT_MS - (now - started);
                if (result == HIBY_BT_OK && remaining <= 0)
                    result = HIBY_BT_CONNECT_FAILED;
                if (result != HIBY_BT_CONNECT_FAILED)
                    break;
                if (remaining <= 0)
                    break;
                struct timespec delay = {.tv_nsec = remaining < 100 ?
                    (long)remaining * 1000000 : 100000000};
                nanosleep(&delay, NULL);
            }
        }
        if (result == HIBY_BT_OK)
        {
            char device[96];
            snprintf(device, sizeof(device), "bluealsa:DEV=%s,PROFILE=a2dp", address);
            if (cancelled && cancelled(context))
                result = HIBY_BT_CANCELLED;
            else
            {
                result = route_device(device, cancelled, context);
                if (result == HIBY_BT_OK && !pcm_alsa_bluetooth_active())
                    result = HIBY_BT_AUDIO_FAILED;
            }
        }
        if (result == HIBY_BT_OK)
        {
            clear_cleanup_pending(address);
            snprintf(state->connected_address, sizeof(state->connected_address), "%s", address);
            snprintf(state->connected_name, sizeof(state->connected_name), "%s", address);
            for (size_t position = 0; position < state->count; position++)
                if (!strcasecmp(state->devices[position].address, address))
                    snprintf(state->connected_name, sizeof(state->connected_name), "%s", state->devices[position].name);
        }
    }
    else if (operation == HIBY_BT_DISCONNECT || operation == HIBY_BT_DISABLE || operation == HIBY_BT_REMOVE)
    {
        if (operation == HIBY_BT_DISABLE && controller_suspended())
        {
            clear_cleanup_pending(NULL);
            state->enabled = false;
            state->power_known = true;
            state->connected_address[0] = '\0';
            state->connected_name[0] = '\0';
            state->count = 0;
            result = route_result;
            goto complete;
        }
        char peer_address[18];
        snprintf(peer_address, sizeof(peer_address), "%s", state->connected_address);
        if (operation == HIBY_BT_DISCONNECT && !peer_address[0])
            result = find_connected_peer(peer_address, output, cancelled, context);
        if (disconnect_active && peer_address[0] && result == HIBY_BT_OK)
        {
            result = disconnect_peer(peer_address, output, cancelled, context);
        }
        if (disconnect_active && result == HIBY_BT_OK)
        {
            state->connected_address[0] = '\0';
            state->connected_name[0] = '\0';
        }
        if (result != HIBY_BT_OK &&
            (operation != HIBY_BT_DISABLE || result == HIBY_BT_CANCELLED))
            goto complete;
        if (operation == HIBY_BT_DISABLE)
        {
            result = ctl("power", "off", output, BT_OUTPUT_SIZE, cancelled, context);
            if (result != HIBY_BT_CANCELLED)
            {
                enum hiby_bt_error observed = read_power(state, output, cancelled, context, NULL);
                if (result == HIBY_BT_OK || observed == HIBY_BT_CANCELLED)
                    result = observed;
                if (result == HIBY_BT_OK && state->enabled)
                    result = HIBY_BT_COMMAND_FAILED;
            }
            if (state->power_known && !state->enabled)
            {
                clear_cleanup_pending(NULL);
                state->connected_address[0] = '\0';
                state->connected_name[0] = '\0';
            }
            if (result == HIBY_BT_OK)
                result = route_result;
        }
        else if (operation == HIBY_BT_REMOVE)
        {
            enum hiby_bt_error remove_result = ctl("remove", address, output, BT_OUTPUT_SIZE, cancelled, context);
            if (result == HIBY_BT_OK)
                result = remove_result;
        }
        if (result == HIBY_BT_OK && (state->enabled || operation == HIBY_BT_REMOVE))
        {
            result = list_devices(state, output, cancelled, context);
            if (result == HIBY_BT_OK && operation == HIBY_BT_REMOVE)
            {
                for (size_t position = 0; position < state->count; position++)
                    if (!strcasecmp(state->devices[position].address, address))
                        result = HIBY_BT_COMMAND_FAILED;
                if (result == HIBY_BT_OK)
                    clear_cleanup_pending(address);
            }
        }
    }
    else
    {
        bool suspended = false;
        result = read_power(state, output, cancelled, context, &suspended);
        if (result != HIBY_BT_OK)
            goto complete;
        if (!state->enabled)
            clear_cleanup_pending(NULL);
        if (state->connected_address[0])
        {
            bool lost = !state->enabled;
            if (!lost)
            {
                bool connected = false;
                result = read_connection(state->connected_address, &connected, output,
                                         cancelled, context);
                if (result != HIBY_BT_OK)
                    goto complete;
                lost = !connected;
                if (!lost && !pcm_alsa_bluetooth_active())
                {
                    result = HIBY_BT_AUDIO_FAILED;
                    goto complete;
                }
            }
            if (lost)
            {
                result = route_device("plughw:0,0", cancelled, context);
                if (result == HIBY_BT_OK)
                {
                    state->connected_address[0] = '\0';
                    state->connected_name[0] = '\0';
                    result = operation == HIBY_BT_VERIFY_LINK && !state->enabled ?
                        HIBY_BT_OK : HIBY_BT_CONNECT_FAILED;
                }
                goto complete;
            }
        }
        if (operation == HIBY_BT_VERIFY_LINK)
            goto complete;
        if (suspended)
            state->count = 0;
        else
            result = list_devices(state, output, cancelled, context);
    }
complete:
    if (connecting && result != HIBY_BT_OK && owned_connection &&
        result != HIBY_BT_CANCELLED)
    {
        record_cleanup_pending(address);
        enum hiby_bt_error cleanup = disconnect_peer(address, output, cancelled, context);
        if (cleanup != HIBY_BT_OK)
            result = cleanup;
    }
    free(output);
    return result;
}
