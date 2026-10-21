#define _GNU_SOURCE 1
#include <alsa/asoundlib.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static pthread_mutex_t trace_mutex = PTHREAD_MUTEX_INITIALIZER;
static unsigned int write_events;
static unsigned int control_events;
static int stereo_s16;

static void trace_event(const char *format, ...)
{
    int saved_error = errno;
    Dl_info library;
    char path[512];
    char line[768];
    if (!dladdr((void *)trace_event, &library) || !library.dli_fname)
        goto complete;
    const char *separator = strrchr(library.dli_fname, '/');
    if (!separator || separator - library.dli_fname > 400)
        goto complete;
    int length = snprintf(path, sizeof(path), "%.*s/r1-audio-diagnostic.log",
                          (int)(separator - library.dli_fname), library.dli_fname);
    if (length < 0 || (size_t)length >= sizeof(path))
        goto complete;
    struct timespec current = {0};
    clock_gettime(CLOCK_MONOTONIC, &current);
    int prefix = snprintf(line, sizeof(line), "[%lld.%03ld pid=%ld] ",
                          (long long)current.tv_sec, current.tv_nsec / 1000000, (long)getpid());
    if (prefix < 0 || (size_t)prefix >= sizeof(line) - 2)
        goto complete;
    va_list arguments;
    va_start(arguments, format);
    int body = vsnprintf(line + prefix, sizeof(line) - (size_t)prefix - 1, format, arguments);
    va_end(arguments);
    if (body < 0)
        goto complete;
    size_t used = (size_t)prefix + ((size_t)body < sizeof(line) - (size_t)prefix - 1 ?
                                  (size_t)body : sizeof(line) - (size_t)prefix - 2);
    line[used++] = '\n';
    pthread_mutex_lock(&trace_mutex);
    int descriptor = (int)syscall(SYS_openat, AT_FDCWD, path,
                                 O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (descriptor >= 0)
    {
        struct stat details;
        if (!fstat(descriptor, &details) && S_ISREG(details.st_mode) &&
            details.st_size >= 0 && details.st_size <= 65536 - (off_t)used)
            syscall(SYS_write, descriptor, line, used);
        syscall(SYS_close, descriptor);
    }
    pthread_mutex_unlock(&trace_mutex);
complete:
    errno = saved_error;
}

static void *resolve_symbol(void **cache, const char *name)
{
    void *address = __atomic_load_n(cache, __ATOMIC_ACQUIRE);
    if (!address)
    {
        address = dlsym(RTLD_NEXT, name);
        if (address)
            __atomic_store_n(cache, address, __ATOMIC_RELEASE);
    }
    return address;
}

__attribute__((constructor)) static void trace_start(void)
{
    trace_event("trace.start v1");
}

int snd_pcm_open(snd_pcm_t **handle, const char *name, snd_pcm_stream_t stream, int mode)
{
    static void *cache;
    int (*original)(snd_pcm_t **, const char *, snd_pcm_stream_t, int) = resolve_symbol(&cache, "snd_pcm_open");
    int result = original ? original(handle, name, stream, mode) : -ENOSYS;
    trace_event("pcm.open device=%s stream=%d mode=%d result=%d", name ? name : "(null)", stream, mode, result);
    return result;
}

int snd_pcm_set_params(snd_pcm_t *handle, snd_pcm_format_t format, snd_pcm_access_t access,
                       unsigned int channels, unsigned int rate, int resample, unsigned int latency)
{
    static void *cache;
    int (*original)(snd_pcm_t *, snd_pcm_format_t, snd_pcm_access_t, unsigned int, unsigned int, int, unsigned int) =
        resolve_symbol(&cache, "snd_pcm_set_params");
    int result = original ? original(handle, format, access, channels, rate, resample, latency) : -ENOSYS;
    __atomic_store_n(&stereo_s16, !result && format == SND_PCM_FORMAT_S16_LE && channels == 2, __ATOMIC_RELEASE);
    trace_event("pcm.params format=%d channels=%u rate=%u latency=%u result=%d", format, channels, rate, latency, result);
    return result;
}

int snd_pcm_prepare(snd_pcm_t *handle)
{
    static void *cache;
    int (*original)(snd_pcm_t *) = resolve_symbol(&cache, "snd_pcm_prepare");
    int result = original ? original(handle) : -ENOSYS;
    trace_event("pcm.prepare result=%d", result);
    return result;
}

snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *handle, const void *buffer, snd_pcm_uframes_t frames)
{
    static void *cache;
    snd_pcm_sframes_t (*original)(snd_pcm_t *, const void *, snd_pcm_uframes_t) = resolve_symbol(&cache, "snd_pcm_writei");
    snd_pcm_sframes_t result = original ? original(handle, buffer, frames) : -ENOSYS;
    unsigned int number = __atomic_fetch_add(&write_events, 1, __ATOMIC_RELAXED);
    if (number < 8)
    {
        unsigned int nonzero = 0;
        if (result > 0 && buffer && __atomic_load_n(&stereo_s16, __ATOMIC_ACQUIRE))
        {
            snd_pcm_uframes_t count = frames < 256 ? frames : 256;
            const int16_t *samples = buffer;
            for (snd_pcm_uframes_t offset = 0; offset < count * 2; offset++)
                nonzero += samples[offset] != 0;
        }
        trace_event("pcm.write requested=%lu result=%ld nonzero_first256=%u", (unsigned long)frames, (long)result, nonzero);
    }
    return result;
}

int snd_ctl_open_lconf(snd_ctl_t **handle, const char *name, int mode, snd_config_t *configuration)
{
    static void *cache;
    int (*original)(snd_ctl_t **, const char *, int, snd_config_t *) = resolve_symbol(&cache, "snd_ctl_open_lconf");
    int result = original ? original(handle, name, mode, configuration) : -ENOSYS;
    trace_event("ctl.open name=%s result=%d", name ? name : "(null)", result);
    return result;
}

int snd_ctl_elem_write(snd_ctl_t *handle, snd_ctl_elem_value_t *value)
{
    static void *cache;
    int (*original)(snd_ctl_t *, snd_ctl_elem_value_t *) = resolve_symbol(&cache, "snd_ctl_elem_write");
    int result = original ? original(handle, value) : -ENOSYS;
    if (value && __atomic_fetch_add(&control_events, 1, __ATOMIC_RELAXED) < 32)
        trace_event("ctl.write name=%s value0=%ld result=%d", snd_ctl_elem_value_get_name(value),
                    snd_ctl_elem_value_get_integer(value, 0), result);
    return result;
}

int open(const char *path, int flags, ...)
{
    static void *cache;
    int (*original)(const char *, int, ...) = resolve_symbol(&cache, "open");
    mode_t mode = 0;
    if (flags & O_CREAT)
    {
        va_list arguments;
        va_start(arguments, flags);
        mode = (mode_t)va_arg(arguments, unsigned int);
        va_end(arguments);
    }
    int result = original ? original(path, flags, mode) : -1;
    if (!original)
        errno = ENOSYS;
    int saved_error = errno;
    if (result < 0 && strstr(path, "/.rockbox/"))
        trace_event("file.open.error path=%s errno=%d", path, saved_error);
    errno = saved_error;
    return result;
}
