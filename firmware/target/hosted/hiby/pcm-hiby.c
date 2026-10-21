#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "pcm-hiby.h"

#include <alsa/asoundlib.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <math.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifdef HIBY_PCM_HOST_TEST
#include "hiby-pcm-test.h"
#else
#include "config.h"
#include "audiohw.h"
#include "pcm.h"
#include "pcm-internal.h"
#include "pcm_mixer.h"
#include "pcm_sampr.h"
#include "pcm_sink.h"
#endif

#define LOCAL_DEVICE "plughw:0,0"
#define HELPER_ARGUMENT "--hiby-pcm-helper"
#define PCM_MAGIC 0x52425043u
#define PCM_FRAMES 1024
#define PCM_BYTES (PCM_FRAMES * 4)
#define PCM_PROCESS_SLOTS 8
#define PCM_RETRY_MIN_MS 250
#define PCM_RETRY_MAX_MS 4000
#define PCM_REAP_TIMEOUT_MS 250
#ifndef HIBY_PCM_OPEN_TIMEOUT_MS
#define HIBY_PCM_OPEN_TIMEOUT_MS 2000
#endif
#ifndef HIBY_PCM_STALL_TIMEOUT_MS
#define HIBY_PCM_STALL_TIMEOUT_MS 1500
#endif
#ifndef HIBY_PCM_HEARTBEAT_MS
#define HIBY_PCM_HEARTBEAT_MS 250
#endif
#ifndef HIBY_PCM_EXECUTABLE
#define HIBY_PCM_EXECUTABLE "/proc/self/exe"
#endif

enum message_type { MESSAGE_READY = 1, MESSAGE_DATA, MESSAGE_ACK, MESSAGE_STOP,
                    MESSAGE_STOPPED, MESSAGE_ERROR, MESSAGE_ALIVE, MESSAGE_FINISH,
                    MESSAGE_XRUN };
struct pcm_message
{
    uint32_t magic;
    uint32_t type;
    int32_t value;
    uint32_t length;
    int16_t samples[PCM_FRAMES * 2];
};
#define MESSAGE_HEADER offsetof(struct pcm_message, samples)

struct helper_process { pid_t process; int descriptor; int slot; };
static const struct helper_process no_helper = {0, -1, -1};
static pthread_mutex_t pool_mutex = PTHREAD_MUTEX_INITIALIZER;
static pid_t process_pool[PCM_PROCESS_SLOTS];
static bool retired_pool[PCM_PROCESS_SLOTS];
static pthread_once_t mutex_once = PTHREAD_ONCE_INIT;
static pthread_mutex_t pcm_mutex;
static pthread_mutex_t route_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t lifecycle_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t output_status_mutex = PTHREAD_MUTEX_INITIALIZER;
static struct hiby_pcm_output_status output_status;
static pid_t output_status_process;
static bool bluetooth_episode_active;
static unsigned int bluetooth_episode_intent;
static char bluetooth_episode_device[96];
static bool error_episode_active;
static unsigned int error_episode_intent;
static pthread_cond_t changed;
static bool mutex_ready;
static pthread_t pump;
static bool initialized;
static bool stopping;
static bool playing;
static bool frequency_changed;
static bool bluetooth_active;
static bool inflight;
static bool stop_pending;
static bool completing_callback;
static bool exit_registered;
static uint32_t volume_factors;
static uint32_t sequence;
static uint32_t pending_sequence;
static unsigned long sample_rate;
static unsigned int xruns;
static unsigned int epoch;
static unsigned int route_intent_generation;
static long long last_activity;
static long long transfer_started;
static long long next_retry;
static unsigned int retry_delay = PCM_RETRY_MIN_MS;
static int last_error;
static const unsigned char *source_data;
static size_t source_size;
static char current_device[96] = LOCAL_DEVICE;
static struct helper_process active_helper = {0, -1, -1};

static long long now_ms(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value))
        return -1;
    return (long long)value.tv_sec * 1000 + value.tv_nsec / 1000000;
}

static void initialize_mutex(void)
{
    pthread_mutexattr_t attributes;
    if (pthread_mutexattr_init(&attributes))
        return;
    int result = pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE);
    if (!result)
        result = pthread_mutex_init(&pcm_mutex, &attributes);
    pthread_mutexattr_destroy(&attributes);
    if (result)
        return;
    pthread_condattr_t condition_attributes;
    result = pthread_condattr_init(&condition_attributes);
    if (!result)
    {
        result = pthread_condattr_setclock(&condition_attributes, CLOCK_MONOTONIC);
        if (!result)
            result = pthread_cond_init(&changed, &condition_attributes);
        pthread_condattr_destroy(&condition_attributes);
    }
    if (result)
        pthread_mutex_destroy(&pcm_mutex);
    else
        mutex_ready = true;
}

static bool ensure_mutex(void)
{
    return !pthread_once(&mutex_once, initialize_mutex) && mutex_ready;
}

static bool valid_device(const char *device)
{
    if (!device)
        return false;
    if (!strcmp(device, LOCAL_DEVICE))
        return true;
#ifdef HIBY_PCM_HOST_TEST
    if (!strcmp(device, "null"))
        return true;
#endif
    const char prefix[] = "bluealsa:DEV=";
    if (strncmp(device, prefix, sizeof(prefix) - 1))
        return false;
    const char *address = device + sizeof(prefix) - 1;
    if (strlen(address) != 17 + strlen(",PROFILE=a2dp") || strcmp(address + 17, ",PROFILE=a2dp"))
        return false;
    for (size_t offset = 0; offset < 17; offset++)
        if (offset % 3 == 2 ? address[offset] != ':' : !isxdigit((unsigned char)address[offset]))
            return false;
    return true;
}

static bool is_bluetooth(const char *device)
{
    return !strncmp(device, "bluealsa:", 9);
}

bool hiby_pcm_get_output_status(struct hiby_pcm_output_status *status)
{
    if (!status || pthread_mutex_lock(&output_status_mutex))
        return false;
    *status = output_status;
    pthread_mutex_unlock(&output_status_mutex);
    return true;
}

static void record_output_error_locked(int error, unsigned int intent)
{
    if (error >= 0 || error == -ECANCELED)
        return;
    if (!error_episode_active || output_status.last_error != error || error_episode_intent != intent)
        output_status.error_generation++;
    output_status.last_error = error;
    error_episode_active = true;
    error_episode_intent = intent;
}

static void publish_output_initialization_error(void)
{
    pthread_mutex_lock(&output_status_mutex);
    record_output_error_locked(-EIO, output_status.route_intent_generation);
    pthread_mutex_unlock(&output_status_mutex);
}

static void publish_output_status(int error, bool lost_bluetooth, bool recovered)
{
    enum hiby_pcm_output active_output = active_helper.descriptor < 0 ? HIBY_PCM_OUTPUT_NONE :
        is_bluetooth(current_device) ? HIBY_PCM_OUTPUT_BLUETOOTH : HIBY_PCM_OUTPUT_WIRED;
    const char *device = active_helper.descriptor < 0 ? "" : current_device;
    pid_t process = active_helper.descriptor < 0 ? 0 : active_helper.process;
    pthread_mutex_lock(&output_status_mutex);
    if (output_status.active_output != active_output || output_status.initialized != initialized ||
        output_status.stopping != stopping || output_status_process != process ||
        strcmp(output_status.active_device, device))
        output_status.state_generation++;
    output_status_process = process;
    output_status.active_output = active_output;
    output_status.initialized = initialized;
    output_status.stopping = stopping;
    output_status.route_intent_generation = route_intent_generation;
    snprintf(output_status.active_device, sizeof(output_status.active_device), "%s", device);
    if (lost_bluetooth && bluetooth_episode_active)
    {
        output_status.loss_generation++;
        output_status.loss_intent_generation = bluetooth_episode_intent;
        output_status.loss_error = error;
        snprintf(output_status.lost_device, sizeof(output_status.lost_device), "%s", bluetooth_episode_device);
        bluetooth_episode_active = false;
    }
    if (recovered)
        error_episode_active = false;
    record_output_error_locked(error, route_intent_generation);
    pthread_mutex_unlock(&output_status_mutex);
}

static int send_message(int descriptor, uint32_t type, int32_t value,
                        const int16_t *samples, size_t bytes)
{
    if (bytes > PCM_BYTES || bytes % 4)
        return -EINVAL;
    struct pcm_message message = {.magic = PCM_MAGIC, .type = type,
        .value = value, .length = (uint32_t)bytes};
    if (bytes)
        memcpy(message.samples, samples, bytes);
    ssize_t result = send(descriptor, &message, MESSAGE_HEADER + bytes, MSG_NOSIGNAL | MSG_DONTWAIT);
    return result < 0 ? -errno : (size_t)result == MESSAGE_HEADER + bytes ? 0 : -EIO;
}

static int receive_message(int descriptor, struct pcm_message *message)
{
    ssize_t result = recv(descriptor, message, sizeof(*message), MSG_DONTWAIT | MSG_TRUNC);
    if (result < 0)
        return -errno;
    if (!result)
        return -EPIPE;
    if ((size_t)result < MESSAGE_HEADER || (size_t)result > sizeof(*message) ||
        message->magic != PCM_MAGIC || message->length > PCM_BYTES || message->length % 4 ||
        MESSAGE_HEADER + message->length != (size_t)result)
        return -EPROTO;
    return 0;
}

static unsigned int reap_retired_helpers(void)
{
    pthread_mutex_lock(&pool_mutex);
    unsigned int pending = 0;
    for (int position = 0; position < PCM_PROCESS_SLOTS; position++)
    {
        if (process_pool[position] > 0 && retired_pool[position])
        {
            int status;
            pid_t result = waitpid(process_pool[position], &status, WNOHANG);
            if (result == process_pool[position] || (result < 0 && errno == ECHILD))
            {
                process_pool[position] = 0;
                retired_pool[position] = false;
            }
        }
        if (process_pool[position])
            pending++;
    }
    pthread_mutex_unlock(&pool_mutex);
    return pending;
}

static bool finish_retired_helpers(void)
{
    long long started = now_ms();
    while (reap_retired_helpers())
    {
        long long now = now_ms();
        if (started < 0 || now < 0 || now - started >= PCM_REAP_TIMEOUT_MS)
            return false;
        struct timespec delay = {.tv_sec = 0, .tv_nsec = 5000000};
        nanosleep(&delay, NULL);
    }
    return true;
}

static int reserve_process(void)
{
    reap_retired_helpers();
    pthread_mutex_lock(&pool_mutex);
    int available = -1;
    for (int position = 0; position < PCM_PROCESS_SLOTS; position++)
    {
        if (!process_pool[position])
            available = position;
    }
    if (available >= 0)
    {
        process_pool[available] = -1;
        retired_pool[available] = false;
    }
    pthread_mutex_unlock(&pool_mutex);
    return available;
}

static void retire_helper(struct helper_process helper)
{
    if (helper.slot < 0)
        return;
    if (helper.descriptor >= 0)
        close(helper.descriptor);
    int status;
    pid_t result = helper.process > 0 ? waitpid(helper.process, &status, WNOHANG) : 0;
    bool reaped = helper.process <= 0 || result == helper.process || (result < 0 && errno == ECHILD);
    if (!reaped && helper.process > 0)
    {
        kill(-helper.process, SIGKILL);
        kill(helper.process, SIGKILL);
        result = waitpid(helper.process, &status, WNOHANG);
        reaped = result == helper.process || (result < 0 && errno == ECHILD);
    }
    pthread_mutex_lock(&pool_mutex);
    process_pool[helper.slot] = reaped ? 0 : helper.process;
    retired_pool[helper.slot] = !reaped;
    pthread_mutex_unlock(&pool_mutex);
}

static int normalize_descriptor(int descriptor)
{
    if (descriptor >= 4)
        return descriptor;
    int replacement = fcntl(descriptor, F_DUPFD_CLOEXEC, 4);
    close(descriptor);
    return replacement;
}

static bool shutdown_requested(void *context)
{
    (void)context;
    return __atomic_load_n(&stopping, __ATOMIC_ACQUIRE);
}

static int open_helper(const char *device, unsigned long rate, struct helper_process *helper,
                       hiby_pcm_cancel_callback cancelled, void *context)
{
    *helper = no_helper;
    int slot = reserve_process();
    if (slot < 0)
        return -EBUSY;
    helper->slot = slot;
    int sockets[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, sockets))
    {
        int result = -errno;
        retire_helper(*helper);
        *helper = no_helper;
        return result;
    }
    sockets[0] = normalize_descriptor(sockets[0]);
    sockets[1] = normalize_descriptor(sockets[1]);
    int null_descriptor = open("/dev/null", O_RDWR | O_CLOEXEC);
    if (null_descriptor >= 0)
        null_descriptor = normalize_descriptor(null_descriptor);
    if (sockets[0] < 0 || sockets[1] < 0 || null_descriptor < 0)
    {
        if (sockets[0] >= 0) close(sockets[0]);
        if (sockets[1] >= 0) close(sockets[1]);
        if (null_descriptor >= 0) close(null_descriptor);
        retire_helper(*helper);
        *helper = no_helper;
        return -EMFILE;
    }
    int buffer_size = PCM_BYTES * 2;
    setsockopt(sockets[0], SOL_SOCKET, SO_SNDBUF, &buffer_size, sizeof(buffer_size));
    setsockopt(sockets[1], SOL_SOCKET, SO_SNDBUF, &buffer_size, sizeof(buffer_size));
    char rate_text[16];
    snprintf(rate_text, sizeof(rate_text), "%lu", rate);
    char *arguments[] = {HIBY_PCM_EXECUTABLE, HELPER_ARGUMENT, (char *)device, rate_text, "3", NULL};
    extern char **environ;
    pid_t process = fork();
    if (!process)
    {
        if (setpgid(0, 0) || dup2(sockets[1], 3) < 0 ||
            dup2(null_descriptor, 0) < 0 || dup2(null_descriptor, 1) < 0 ||
            dup2(null_descriptor, 2) < 0)
            _exit(126);
        execve(HIBY_PCM_EXECUTABLE, arguments, environ);
        _exit(127);
    }
    close(sockets[1]);
    close(null_descriptor);
    helper->descriptor = sockets[0];
    helper->process = process;
    pthread_mutex_lock(&pool_mutex);
    process_pool[slot] = process > 0 ? process : -1;
    pthread_mutex_unlock(&pool_mutex);
    if (process < 0)
    {
        retire_helper(*helper);
        *helper = no_helper;
        return -EIO;
    }
    setpgid(process, process);
    long long started = now_ms();
    int result = -ETIMEDOUT;
    struct pcm_message message;
    for (;;)
    {
        long long now = now_ms();
        if (shutdown_requested(NULL) || (cancelled && cancelled(context)))
        {
            result = -ECANCELED;
            break;
        }
        if (started < 0 || now < 0 || now - started >= HIBY_PCM_OPEN_TIMEOUT_MS)
            break;
        result = receive_message(helper->descriptor, &message);
        if (!result)
        {
            if (message.type == MESSAGE_READY && message.value == (int32_t)rate && !message.length)
                return 0;
            result = message.type == MESSAGE_ERROR && message.value < 0 ? message.value : -EPROTO;
            break;
        }
        if (result != -EAGAIN && result != -EWOULDBLOCK && result != -EINTR)
            break;
        struct pollfd pending = {.fd = helper->descriptor, .events = POLLIN};
        poll(&pending, 1, 10);
        result = -ETIMEDOUT;
    }
    retire_helper(*helper);
    *helper = no_helper;
    return result;
}

static int helper_loop(int descriptor, const char *device, unsigned int rate)
{
    DIR *directory = opendir("/proc/self/fd");
    if (!directory)
        return 70;
    struct dirent *entry;
    while ((entry = readdir(directory)))
    {
        char *end;
        long opened = strtol(entry->d_name, &end, 10);
        if (!*end && opened > 3 && opened != dirfd(directory))
            close((int)opened);
    }
    closedir(directory);
    snd_pcm_t *handle = NULL;
    int result = snd_pcm_open(&handle, device, SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK);
    if (!result)
        result = snd_pcm_set_params(handle, SND_PCM_FORMAT_S16_LE, SND_PCM_ACCESS_RW_INTERLEAVED,
                                    2, rate, 1, 60000);
    if (!result)
        result = snd_pcm_prepare(handle);
    if (result < 0)
    {
        send_message(descriptor, MESSAGE_ERROR, result, NULL, 0);
        if (handle) snd_pcm_close(handle);
        return 71;
    }
    if (send_message(descriptor, MESSAGE_READY, (int32_t)rate, NULL, 0))
    {
        snd_pcm_close(handle);
        return 72;
    }
    struct pcm_message input;
    int16_t samples[PCM_FRAMES * 2];
    size_t frames = 0;
    size_t offset = 0;
    int32_t acknowledgement = 0;
    bool finishing = false;
    long long heartbeat = now_ms();
    for (;;)
    {
        result = receive_message(descriptor, &input);
        if (!result)
        {
            if (input.type == MESSAGE_STOP && !input.length)
            {
                frames = offset = 0;
                finishing = false;
                result = snd_pcm_drop(handle);
                if (!result) result = snd_pcm_prepare(handle);
                if (result < 0 || send_message(descriptor, MESSAGE_STOPPED, input.value, NULL, 0))
                    break;
            }
            else if (input.type == MESSAGE_FINISH && !input.length && !frames)
            {
                finishing = true;
                acknowledgement = input.value;
            }
            else if (input.type == MESSAGE_DATA && input.length && !frames && !finishing)
            {
                memcpy(samples, input.samples, input.length);
                frames = input.length / 4;
                offset = 0;
                acknowledgement = input.value;
            }
            else
            {
                result = -EPROTO;
                break;
            }
        }
        else if (result != -EAGAIN && result != -EWOULDBLOCK && result != -EINTR)
            break;
        if (finishing)
        {
            result = snd_pcm_drain(handle);
            if (!result)
            {
                result = snd_pcm_prepare(handle);
                if (result < 0 || send_message(descriptor, MESSAGE_STOPPED, acknowledgement, NULL, 0))
                    break;
                finishing = false;
            }
            else if (result != -EAGAIN && result != -EINTR)
                break;
        }
        if (frames)
        {
            snd_pcm_sframes_t written = snd_pcm_writei(handle, samples + offset * 2, frames);
            if (written > 0 && (snd_pcm_uframes_t)written <= frames)
            {
                offset += (size_t)written;
                frames -= (size_t)written;
                if (!frames && send_message(descriptor, MESSAGE_ACK, acknowledgement, NULL, 0))
                {
                    result = -EPIPE;
                    break;
                }
            }
            else if (written == -EPIPE || written == -ESTRPIPE)
            {
                send_message(descriptor, MESSAGE_XRUN, (int32_t)written, NULL, 0);
                result = written == -ESTRPIPE ? snd_pcm_resume(handle) : snd_pcm_prepare(handle);
                if (result < 0 && result != -EAGAIN)
                    result = snd_pcm_prepare(handle);
                if (result < 0 && result != -EAGAIN)
                    break;
            }
            else if (written < 0 && written != -EAGAIN && written != -EINTR)
            {
                result = (int)written;
                break;
            }
            else if (written > 0)
            {
                result = -EPROTO;
                break;
            }
        }
        long long now = now_ms();
        if (now < 0 || heartbeat < 0)
        {
            result = -EIO;
            break;
        }
        if (now - heartbeat >= HIBY_PCM_HEARTBEAT_MS)
        {
            snd_pcm_sframes_t available = snd_pcm_avail_update(handle);
            if (available < 0 && available != -EAGAIN && available != -EPIPE && available != -ESTRPIPE)
            {
                result = (int)available;
                break;
            }
            send_message(descriptor, MESSAGE_ALIVE, 0, NULL, 0);
            heartbeat = now;
        }
        struct pollfd pending = {.fd = descriptor, .events = POLLIN};
        poll(&pending, 1, frames || finishing ? 5 : HIBY_PCM_HEARTBEAT_MS);
    }
    send_message(descriptor, MESSAGE_ERROR, result < 0 ? result : -EIO, NULL, 0);
    snd_pcm_drop(handle);
    snd_pcm_close(handle);
    return 73;
}

int hiby_pcm_helper_main(int argc, char **argv)
{
    if (argc < 2 || strcmp(argv[1], HELPER_ARGUMENT))
        return -1;
    if (argc != 5 || !valid_device(argv[2]) || strcmp(argv[4], "3"))
        return 64;
    unsigned long rate = 0;
    for (const unsigned char *digit = (const unsigned char *)argv[3]; *digit; digit++)
    {
        if (*digit < '0' || *digit > '9' || rate > 192000)
            return 64;
        rate = rate * 10 + *digit - '0';
    }
    if (rate < 8000 || rate > 192000)
        return 64;
    int type;
    socklen_t length = sizeof(type);
    if (getsockopt(3, SOL_SOCKET, SO_TYPE, &type, &length) || type != SOCK_SEQPACKET)
        return 65;
    return helper_loop(3, argv[2], (unsigned int)rate);
}

static uint32_t next_sequence(void)
{
    sequence = (sequence + 1) & 0x7fffffffu;
    return sequence;
}

static void clear_transfer(void)
{
    inflight = false;
    stop_pending = false;
    last_activity = now_ms();
    transfer_started = 0;
}

static int switch_playback_device(const char *device,
    hiby_pcm_cancel_callback cancelled, void *context, bool explicit_request,
    unsigned int recovery_generation)
{
    if (!valid_device(device))
        return -EINVAL;
    if (!ensure_mutex())
    {
        publish_output_initialization_error();
        return -EIO;
    }
    if (pthread_mutex_trylock(&route_mutex))
        return -EBUSY;
    pthread_mutex_lock(&pcm_mutex);
    if (!explicit_request && route_intent_generation != recovery_generation)
    {
        pthread_mutex_unlock(&pcm_mutex);
        pthread_mutex_unlock(&route_mutex);
        return -EBUSY;
    }
    if (explicit_request)
    {
        route_intent_generation++;
        next_retry = 0;
        retry_delay = PCM_RETRY_MIN_MS;
        publish_output_status(0, false, false);
    }
    unsigned long rate = sample_rate;
    unsigned int expected_epoch = epoch;
    bool allowed = initialized && !stopping;
    long long now = now_ms();
    if (allowed && active_helper.descriptor >= 0 && !frequency_changed &&
        !strcmp(current_device, device) && now >= 0 && last_activity >= 0 &&
        now - last_activity < HIBY_PCM_STALL_TIMEOUT_MS)
    {
        int result = cancelled && cancelled(context) ? -ECANCELED : 0;
        if (!result && bluetooth_episode_active && is_bluetooth(device))
            bluetooth_episode_intent = route_intent_generation;
        publish_output_status(0, false, !result);
        pthread_mutex_unlock(&pcm_mutex);
        pthread_mutex_unlock(&route_mutex);
        return result;
    }
    pthread_mutex_unlock(&pcm_mutex);
    struct helper_process candidate = no_helper;
    int result = allowed ? open_helper(device, rate, &candidate, cancelled, context) : -ENODEV;
    struct helper_process previous = no_helper;
    if (!result)
    {
        pthread_mutex_lock(&pcm_mutex);
        if (!initialized || stopping || epoch != expected_epoch ||
            (cancelled && cancelled(context)))
            result = -ECANCELED;
        else
        {
            previous = active_helper;
            active_helper = candidate;
            candidate = no_helper;
            snprintf(current_device, sizeof(current_device), "%s", device);
            __atomic_store_n(&bluetooth_active, is_bluetooth(device), __ATOMIC_RELEASE);
            clear_transfer();
            last_error = 0;
            next_retry = 0;
            retry_delay = PCM_RETRY_MIN_MS;
            frequency_changed = false;
            if (is_bluetooth(device))
            {
                if (!bluetooth_episode_active || explicit_request || strcmp(bluetooth_episode_device, device))
                    bluetooth_episode_intent = route_intent_generation;
                bluetooth_episode_active = true;
                snprintf(bluetooth_episode_device, sizeof(bluetooth_episode_device), "%s", device);
            }
            else
                bluetooth_episode_active = false;
            publish_output_status(0, false, true);
            pthread_cond_signal(&changed);
        }
        pthread_mutex_unlock(&pcm_mutex);
    }
    if (result && result != -ECANCELED && allowed)
    {
        pthread_mutex_lock(&pcm_mutex);
        if (initialized && !stopping && epoch == expected_epoch &&
            (explicit_request || route_intent_generation == recovery_generation))
        {
            bool lost_bluetooth = !explicit_request && bluetooth_episode_active &&
                active_helper.descriptor < 0 && is_bluetooth(device) &&
                !strcmp(bluetooth_episode_device, device);
            publish_output_status(result, lost_bluetooth, false);
        }
        pthread_mutex_unlock(&pcm_mutex);
    }
    retire_helper(candidate);
    retire_helper(previous);
    pthread_mutex_unlock(&route_mutex);
    return result;
}

int pcm_alsa_switch_playback_device_cancellable(const char *device,
    hiby_pcm_cancel_callback cancelled, void *context)
{
    return switch_playback_device(device, cancelled, context, true, 0);
}

int pcm_alsa_switch_playback_device(const char *device)
{
    return pcm_alsa_switch_playback_device_cancellable(device, NULL, NULL);
}

bool pcm_alsa_bluetooth_active(void)
{
    return __atomic_load_n(&bluetooth_active, __ATOMIC_ACQUIRE);
}

static uint32_t volume_factor(int centibels)
{
    if (centibels <= -1000)
        return 0;
    if (centibels >= 0)
        return 32768;
    return (uint32_t)lround(pow(10.0, (double)centibels / 200.0) * 32768.0);
}

void pcm_alsa_set_bluetooth_volume(int left_centibels, int right_centibels)
{
    uint32_t factors = volume_factor(left_centibels) | (volume_factor(right_centibels) << 16);
    __atomic_store_n(&volume_factors, factors, __ATOMIC_RELEASE);
}

static struct helper_process recover_output(int error)
{
    struct helper_process retired = active_helper;
    bool lost_bluetooth = bluetooth_episode_active && active_helper.descriptor >= 0 && is_bluetooth(current_device);
    last_error = error;
    active_helper = no_helper;
    snprintf(current_device, sizeof(current_device), "%s", LOCAL_DEVICE);
    __atomic_store_n(&bluetooth_active, false, __ATOMIC_RELEASE);
    clear_transfer();
    next_retry = 0;
    retry_delay = PCM_RETRY_MIN_MS;
    xruns++;
    publish_output_status(error, lost_bluetooth, false);
    return retired;
}

static int submit_frames(bool *invalid_buffer)
{
    if (!source_size)
    {
        const void *next = NULL;
        completing_callback = true;
        bool more = pcm_play_dma_complete_callback(PCM_DMAST_OK, &next, &source_size);
        completing_callback = false;
        if (!more)
            return 0;
        source_data = next;
        pcm_play_dma_status_callback(PCM_DMAST_STARTED);
    }
    if (!playing || !source_data || !source_size || source_size % 4)
    {
        *invalid_buffer = true;
        return -EINVAL;
    }
    size_t bytes = source_size < PCM_BYTES ? source_size : PCM_BYTES;
    int16_t samples[PCM_FRAMES * 2];
    memcpy(samples, source_data, bytes);
    if (pcm_alsa_bluetooth_active())
    {
        uint32_t factors = __atomic_load_n(&volume_factors, __ATOMIC_ACQUIRE);
        int32_t left = (int32_t)(factors & 0xffff);
        int32_t right = (int32_t)(factors >> 16);
        for (size_t position = 0; position < bytes / 2; position += 2)
        {
            samples[position] = (int16_t)((int32_t)samples[position] * left / 32768);
            samples[position + 1] = (int16_t)((int32_t)samples[position + 1] * right / 32768);
        }
    }
    uint32_t selected_sequence = next_sequence();
    int result = send_message(active_helper.descriptor, MESSAGE_DATA,
                              (int32_t)selected_sequence, samples, bytes);
    if (!result)
    {
        pending_sequence = selected_sequence;
        inflight = true;
        last_activity = now_ms();
        transfer_started = last_activity;
        source_data += bytes;
        source_size -= bytes;
    }
    return result == -EAGAIN || result == -EWOULDBLOCK || result == -EINTR ? 0 : result;
}

static void *pump_main(void *context)
{
    (void)context;
    pthread_mutex_lock(&pcm_mutex);
    while (!stopping)
    {
        struct helper_process retired = no_helper;
        bool need_open = frequency_changed || active_helper.descriptor < 0;
        long long open_time = now_ms();
        if (frequency_changed)
        {
            retired = active_helper;
            active_helper = no_helper;
            __atomic_store_n(&bluetooth_active, false, __ATOMIC_RELEASE);
            clear_transfer();
            frequency_changed = false;
            next_retry = 0;
            retry_delay = PCM_RETRY_MIN_MS;
            publish_output_status(0, false, false);
        }
        if (need_open && open_time >= 0 && open_time >= next_retry)
        {
            char device[sizeof(current_device)];
            memcpy(device, current_device, sizeof(device));
            unsigned int recovery_generation = route_intent_generation;
            pthread_mutex_unlock(&pcm_mutex);
            retire_helper(retired);
            retired = no_helper;
            int result = switch_playback_device(device, shutdown_requested, NULL, false, recovery_generation);
            if (result && result != -EBUSY && strcmp(device, LOCAL_DEVICE))
                result = switch_playback_device(LOCAL_DEVICE, shutdown_requested, NULL, false, recovery_generation);
            pthread_mutex_lock(&pcm_mutex);
            if (result && result != -EBUSY)
            {
                last_error = result;
                if (!stopping && route_intent_generation == recovery_generation)
                    publish_output_status(result, false, false);
                if (active_helper.descriptor < 0)
                {
                    long long failed_at = now_ms();
                    next_retry = failed_at < 0 ? 0 : failed_at + retry_delay;
                    if (retry_delay < PCM_RETRY_MAX_MS)
                    {
                        retry_delay *= 2;
                        if (retry_delay > PCM_RETRY_MAX_MS)
                            retry_delay = PCM_RETRY_MAX_MS;
                    }
                    snprintf(current_device, sizeof(current_device), "%s", LOCAL_DEVICE);
                }
            }
        }
        if (active_helper.descriptor >= 0)
        {
            struct pcm_message message;
            int result = -EAGAIN;
            unsigned int budget = 8;
            while (budget-- && !(result = receive_message(active_helper.descriptor, &message)))
            {
                if (!message.length && message.type == MESSAGE_ERROR && message.value < 0)
                {
                    result = message.value;
                    break;
                }
                if (message.length || (message.type != MESSAGE_ACK && message.type != MESSAGE_STOPPED &&
                                       message.type != MESSAGE_ALIVE && message.type != MESSAGE_XRUN))
                {
                    result = -EPROTO;
                    break;
                }
                last_activity = now_ms();
                if (message.type == MESSAGE_XRUN)
                    xruns++;
                if (message.type == MESSAGE_ACK && (uint32_t)message.value == pending_sequence)
                    inflight = false;
                if (message.type == MESSAGE_STOPPED && (uint32_t)message.value == pending_sequence)
                {
                    stop_pending = false;
                    inflight = false;
                }
            }
            long long now = now_ms();
            if ((result < 0 && result != -EAGAIN && result != -EWOULDBLOCK && result != -EINTR) ||
                now < 0 || last_activity < 0 || now - last_activity >= HIBY_PCM_STALL_TIMEOUT_MS ||
                ((inflight || stop_pending) && (transfer_started < 0 ||
                  now - transfer_started >= HIBY_PCM_STALL_TIMEOUT_MS)))
            {
                retired = recover_output(result < 0 && result != -EAGAIN ? result : -ETIMEDOUT);
            }
            else if (playing && !inflight && !stop_pending)
            {
                bool invalid_buffer = false;
                result = submit_frames(&invalid_buffer);
                if (result)
                {
                    if (invalid_buffer)
                    {
                        last_error = result;
                        publish_output_status(result, false, false);
                        pcm_play_dma_status_callback(PCM_DMAST_ERR_DMA);
                        pcm_play_stop_int();
                    }
                    else
                        retired = recover_output(result);
                }
            }
        }
        pthread_mutex_unlock(&pcm_mutex);
        retire_helper(retired);
        reap_retired_helpers();
        pthread_mutex_lock(&pcm_mutex);
        if (stopping)
            break;
        struct timespec deadline;
        if (clock_gettime(CLOCK_MONOTONIC, &deadline))
        {
            last_error = -EIO;
            publish_output_status(-EIO, false, false);
            pthread_cond_wait(&changed, &pcm_mutex);
            continue;
        }
        deadline.tv_nsec += active_helper.descriptor >= 0 && (playing || inflight || stop_pending) ? 5000000 :
                            HIBY_PCM_HEARTBEAT_MS * 1000000L;
        if (deadline.tv_nsec >= 1000000000)
        {
            deadline.tv_nsec -= 1000000000;
            deadline.tv_sec++;
        }
        pthread_cond_timedwait(&changed, &pcm_mutex, &deadline);
    }
    struct helper_process retired = active_helper;
    active_helper = no_helper;
    __atomic_store_n(&bluetooth_active, false, __ATOMIC_RELEASE);
    bluetooth_episode_active = false;
    publish_output_status(0, false, false);
    pthread_mutex_unlock(&pcm_mutex);
    retire_helper(retired);
    return NULL;
}

static void sink_init(void)
{
    if (!ensure_mutex())
    {
        publish_output_initialization_error();
        return;
    }
    pthread_mutex_lock(&lifecycle_mutex);
    pthread_mutex_lock(&pcm_mutex);
    if (!initialized)
    {
        __atomic_store_n(&stopping, false, __ATOMIC_RELEASE);
        sample_rate = hw_freq_sampr[HW_FREQ_DEFAULT];
        next_retry = 0;
        retry_delay = PCM_RETRY_MIN_MS;
        audiohw_preinit();
        pthread_attr_t attributes;
        int result = pthread_attr_init(&attributes);
        if (!result)
        {
            size_t stack_size = (size_t)PTHREAD_STACK_MIN;
            if (stack_size < 65536)
                stack_size = 65536;
            result = pthread_attr_setstacksize(&attributes, stack_size);
            if (!result) result = pthread_create(&pump, &attributes, pump_main, NULL);
            pthread_attr_destroy(&attributes);
        }
        if (!result)
        {
            initialized = true;
            if (!exit_registered)
            {
                atexit(hiby_pcm_shutdown);
                exit_registered = true;
            }
        }
        else
            last_error = -result;
        publish_output_status(result ? -result : 0, false, false);
    }
    pthread_mutex_unlock(&pcm_mutex);
    pthread_mutex_unlock(&lifecycle_mutex);
}

void hiby_pcm_shutdown(void)
{
    if (!ensure_mutex())
        return;
    pthread_mutex_lock(&lifecycle_mutex);
    pthread_mutex_lock(&pcm_mutex);
    if (!initialized || stopping)
    {
        pthread_mutex_unlock(&pcm_mutex);
        pthread_mutex_unlock(&lifecycle_mutex);
        return;
    }
    __atomic_store_n(&stopping, true, __ATOMIC_RELEASE);
    playing = false;
    epoch++;
    publish_output_status(0, false, false);
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&pcm_mutex);
    pthread_join(pump, NULL);
    pthread_mutex_lock(&route_mutex);
    pthread_mutex_lock(&pcm_mutex);
    initialized = false;
    source_data = NULL;
    source_size = 0;
    clear_transfer();
    publish_output_status(0, false, false);
    pthread_mutex_unlock(&pcm_mutex);
    if (!finish_retired_helpers())
    {
        pthread_mutex_lock(&pcm_mutex);
        last_error = -ETIMEDOUT;
        publish_output_status(-ETIMEDOUT, false, false);
        pthread_mutex_unlock(&pcm_mutex);
    }
    pthread_mutex_unlock(&route_mutex);
    pthread_mutex_unlock(&lifecycle_mutex);
}

static void sink_postinit(void)
{
    audiohw_postinit();
#ifdef AUDIOHW_NEEDS_INITIAL_UNMUTE
    audiohw_mute(false);
#endif
}

static void sink_lock(void) { if (ensure_mutex()) pthread_mutex_lock(&pcm_mutex); }
static void sink_unlock(void) { if (mutex_ready) pthread_mutex_unlock(&pcm_mutex); }

static void sink_set_freq(uint16_t frequency)
{
    if (frequency >= HW_NUM_FREQ)
        return;
    sink_lock();
    unsigned long requested = hw_freq_sampr[frequency];
    if (sample_rate != requested)
    {
        sample_rate = requested;
        epoch++;
        frequency_changed = true;
        next_retry = 0;
        retry_delay = PCM_RETRY_MIN_MS;
        pthread_cond_signal(&changed);
    }
    sink_unlock();
}

static void sink_play(const void *address, size_t size)
{
    sink_lock();
    source_data = address;
    source_size = size;
    playing = true;
    next_retry = 0;
    retry_delay = PCM_RETRY_MIN_MS;
    pthread_cond_signal(&changed);
    sink_unlock();
}

static void sink_stop(void)
{
    sink_lock();
    playing = false;
    source_data = NULL;
    source_size = 0;
    inflight = false;
    if (active_helper.descriptor >= 0)
    {
        pending_sequence = next_sequence();
        if (!send_message(active_helper.descriptor, completing_callback ? MESSAGE_FINISH : MESSAGE_STOP,
                          (int32_t)pending_sequence, NULL, 0))
        {
            stop_pending = true;
            last_activity = now_ms();
            transfer_started = last_activity;
        }
        else
            last_activity = 0;
    }
    pthread_cond_signal(&changed);
    sink_unlock();
}

void pcm_alsa_set_playback_device(const char *device)
{
    if (!valid_device(device))
        return;
    sink_lock();
    if (!initialized)
        snprintf(current_device, sizeof(current_device), "%s", device);
    sink_unlock();
}

unsigned int pcm_alsa_get_rate(void)
{
    sink_lock();
    unsigned int value = (unsigned int)sample_rate;
    sink_unlock();
    return value;
}

unsigned int pcm_alsa_get_xruns(void)
{
    sink_lock();
    unsigned int value = xruns;
    sink_unlock();
    return value;
}

struct pcm_sink builtin_pcm_sink = {
    .caps = {.samprs = hw_freq_sampr, .num_samprs = HW_NUM_FREQ,
             .default_freq = HW_FREQ_DEFAULT, .volume_type = PCM_NATIVE_VOLUME_TYPE},
    .ops = {.init = sink_init, .postinit = sink_postinit, .set_freq = sink_set_freq,
            .lock = sink_lock, .unlock = sink_unlock, .play = sink_play, .stop = sink_stop},
};
