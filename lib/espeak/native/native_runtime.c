#include "config.h"
#include "system.h"
#include "kernel.h"
#include "file.h"
#include "dir.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "native_runtime.h"
#include "../../tlsf/src/tlsf.h"

#ifdef RB_ESPEAK_SHADOW_STDLIB_H
#error Compile native adapter C with ordinary Rockbox headers, not eSpeak shadow headers
#endif

static unsigned char heap[RB_ESPEAK_HEAP_BYTES] __attribute__((aligned(16)));
static int heap_initialized;
static size_t allocation_failures;
static volatile int engine_busy;
static volatile int engine_ready;
static rb_espeak_yield_callback yield_callback;
static void *yield_context;
static char diagnostic[256];
int rb_espeak_errno;

int rb_espeak_engine_acquire(void)
{
#if CONFIG_PLATFORM & PLATFORM_HOSTED
    return !__atomic_exchange_n(&engine_busy, 1, __ATOMIC_ACQUIRE);
#else
    int previous = disable_irq_save();
    int acquired = !engine_busy;
    if (acquired)
        engine_busy = 1;
    restore_irq(previous);
    return acquired;
#endif
}

void rb_espeak_engine_release(void)
{
#if CONFIG_PLATFORM & PLATFORM_HOSTED
    __atomic_store_n(&engine_busy, 0, __ATOMIC_RELEASE);
#else
    int previous = disable_irq_save();
    engine_busy = 0;
    restore_irq(previous);
#endif
}

int rb_espeak_engine_ready(void)
{
#if CONFIG_PLATFORM & PLATFORM_HOSTED
    return __atomic_load_n(&engine_ready, __ATOMIC_ACQUIRE);
#else
    int previous = disable_irq_save();
    int ready = engine_ready;
    restore_irq(previous);
    return ready;
#endif
}

void rb_espeak_engine_mark_ready(void)
{
#if CONFIG_PLATFORM & PLATFORM_HOSTED
    __atomic_store_n(&engine_ready, 1, __ATOMIC_RELEASE);
#else
    int previous = disable_irq_save();
    engine_ready = 1;
    restore_irq(previous);
#endif
}

void rb_espeak_native_set_yield(rb_espeak_yield_callback callback, void *context)
{
    yield_callback = callback;
    yield_context = context;
}

void rb_espeak_native_yield(void)
{
    if (yield_callback)
        yield_callback(yield_context);
    else
        yield();
}

static int initialize_heap(void)
{
    if (!heap_initialized)
    {
        if (init_memory_pool(sizeof(heap), heap) == (size_t)-1)
        {
            rb_espeak_errno = ENOMEM;
            return 0;
        }
        heap_initialized = 1;
    }
    return 1;
}

size_t rb_espeak_heap_capacity(void) { return sizeof(heap); }
size_t rb_espeak_heap_used(void) { return initialize_heap() ? get_used_size(heap) : sizeof(heap); }
size_t rb_espeak_heap_available(void) { return sizeof(heap) - rb_espeak_heap_used(); }
size_t rb_espeak_heap_peak(void) { return initialize_heap() ? get_max_size(heap) : sizeof(heap); }
size_t rb_espeak_heap_failures(void) { return allocation_failures; }

static void *allocation_failed(void)
{
    rb_espeak_errno = ENOMEM;
    ++allocation_failures;
    return NULL;
}

void *rb_espeak_malloc(size_t size)
{
    void *memory;
    if (size > sizeof(heap) || !initialize_heap())
        return allocation_failed();
    memory = malloc_ex(size ? size : 1, heap);
    return memory ? memory : allocation_failed();
}

void *rb_espeak_calloc(size_t count, size_t size)
{
    void *memory;
    if (size && count > sizeof(heap) / size)
        return allocation_failed();
    memory = rb_espeak_malloc(count * size);
    if (memory)
        memset(memory, 0, count * size);
    return memory;
}

void *rb_espeak_realloc(void *memory, size_t size)
{
    void *resized;
    if (!memory)
        return rb_espeak_malloc(size);
    if (!size)
    {
        rb_espeak_free(memory);
        return NULL;
    }
    if (size > sizeof(heap))
        return allocation_failed();
    resized = realloc_ex(memory, size, heap);
    return resized ? resized : allocation_failed();
}

void rb_espeak_free(void *memory)
{
    if (memory)
        free_ex(memory, heap);
}

const char *rb_espeak_native_diagnostic(void) { return diagnostic; }

struct rb_espeak_FILE {
    int descriptor;
    int error;
    int eof;
    int pushed;
    long position;
    long buffer_start;
    size_t cursor;
    size_t buffered;
    unsigned char buffer[512];
};

static rb_espeak_FILE input_stream = { .descriptor = -1 };
static rb_espeak_FILE output_stream = { .descriptor = -1 };
static rb_espeak_FILE error_stream = { .descriptor = -1 };
rb_espeak_FILE * const rb_espeak_stdin = &input_stream;
rb_espeak_FILE * const rb_espeak_stdout = &output_stream;
rb_espeak_FILE * const rb_espeak_stderr = &error_stream;

static int stream_error(rb_espeak_FILE *stream, int error)
{
    rb_espeak_errno = error;
    if (stream)
        stream->error = 1;
    return EOF;
}

static int readable(rb_espeak_FILE *stream)
{
    if (!stream || stream->descriptor < 0)
    {
        stream_error(stream, EBADF);
        return 0;
    }
    return 1;
}

rb_espeak_FILE *rb_espeak_fopen(const char *path, const char *mode)
{
    rb_espeak_FILE *stream;
    int descriptor;
    if (!path || !mode || !*path)
    {
        rb_espeak_errno = EINVAL;
        return NULL;
    }
    if (strcmp(mode, "r") && strcmp(mode, "rb"))
    {
        rb_espeak_errno = EROFS;
        return NULL;
    }
    descriptor = open(path, O_RDONLY);
    if (descriptor < 0)
    {
        rb_espeak_errno = errno;
        return NULL;
    }
    stream = rb_espeak_calloc(1, sizeof(*stream));
    if (!stream)
    {
        close(descriptor);
        return NULL;
    }
    stream->descriptor = descriptor;
    stream->pushed = EOF;
    return stream;
}

int rb_espeak_fclose(rb_espeak_FILE *stream)
{
    int result;
    if (!readable(stream))
        return EOF;
    result = close(stream->descriptor);
    if (result < 0)
        rb_espeak_errno = errno;
    rb_espeak_free(stream);
    return result < 0 ? EOF : 0;
}

int rb_espeak_fgetc(rb_espeak_FILE *stream)
{
    int character;
    if (!readable(stream))
        return EOF;
    if (stream->position == LONG_MAX)
        return stream_error(stream, EOVERFLOW);
    if (stream->pushed != EOF)
    {
        character = stream->pushed;
        stream->pushed = EOF;
    }
    else
    {
        if (stream->cursor == stream->buffered)
        {
            ssize_t received;
            if (stream->eof)
                return EOF;
            received = read(stream->descriptor, stream->buffer, sizeof(stream->buffer));
            if (received < 0)
                return stream_error(stream, errno);
            if (!received)
            {
                stream->eof = 1;
                return EOF;
            }
            stream->cursor = 0;
            stream->buffered = (size_t)received;
            stream->buffer_start = stream->position;
            rb_espeak_native_yield();
        }
        character = stream->buffer[stream->cursor++];
    }
    ++stream->position;
    return character;
}

size_t rb_espeak_fread(void *data, size_t size, size_t count, rb_espeak_FILE *stream)
{
    size_t total;
    size_t completed = 0;
    unsigned char *destination = data;
    if (!size || !count)
        return 0;
    if (!data || count > SIZE_MAX / size)
    {
        stream_error(stream, EINVAL);
        return 0;
    }
    total = size * count;
    while (completed < total)
    {
        size_t chunk;
        if (!readable(stream))
            break;
        if (stream->pushed != EOF || stream->cursor == stream->buffered)
        {
            int character = rb_espeak_fgetc(stream);
            if (character == EOF)
                break;
            destination[completed++] = (unsigned char)character;
            continue;
        }
        chunk = stream->buffered - stream->cursor;
        if (chunk > total - completed)
            chunk = total - completed;
        if (chunk > (size_t)(LONG_MAX - stream->position))
            chunk = (size_t)(LONG_MAX - stream->position);
        if (!chunk)
        {
            stream_error(stream, EOVERFLOW);
            break;
        }
        memcpy(destination + completed, stream->buffer + stream->cursor, chunk);
        stream->cursor += chunk;
        stream->position += (long)chunk;
        completed += chunk;
    }
    return completed / size;
}

int rb_espeak_ungetc(int character, rb_espeak_FILE *stream)
{
    if (!readable(stream) || character == EOF || stream->pushed != EOF || !stream->position)
        return EOF;
    stream->pushed = (unsigned char)character;
    --stream->position;
    stream->eof = 0;
    return stream->pushed;
}

char *rb_espeak_fgets(char *data, int capacity, rb_espeak_FILE *stream)
{
    int completed = 0;
    if (!data || capacity < 1)
    {
        stream_error(stream, EINVAL);
        return NULL;
    }
    if (!readable(stream))
        return NULL;
    while (completed < capacity - 1)
    {
        int character = rb_espeak_fgetc(stream);
        if (character == EOF)
        {
            if (stream->error || !completed)
                return NULL;
            break;
        }
        data[completed++] = (char)character;
        if (character == '\n')
            break;
    }
    data[completed] = 0;
    return data;
}

int rb_espeak_fseek(rb_espeak_FILE *stream, long offset, int origin)
{
    int64_t target = offset;
    if (!readable(stream))
        return -1;
    if (origin == SEEK_CUR)
    {
        if (offset > LONG_MAX - stream->position)
            return stream_error(stream, EOVERFLOW);
        target += stream->position;
    }
    else if (origin == SEEK_END)
    {
        off_t length = ffilesize(stream->descriptor);
        if (length < 0)
            return stream_error(stream, errno);
        if (length > LONG_MAX || offset > LONG_MAX - length)
            return stream_error(stream, EOVERFLOW);
        target += length;
    }
    else if (origin != SEEK_SET)
        return stream_error(stream, EINVAL);
    if (target < 0 || target > LONG_MAX || (int64_t)(off_t)target != target)
        return stream_error(stream, EINVAL);
    if (stream->buffered && target >= stream->buffer_start &&
        (uint64_t)(target - stream->buffer_start) <= stream->buffered)
        stream->cursor = (size_t)(target - stream->buffer_start);
    else
    {
        if (lseek(stream->descriptor, (off_t)target, SEEK_SET) < 0)
            return stream_error(stream, errno);
        stream->cursor = stream->buffered = 0;
        stream->buffer_start = (long)target;
    }
    stream->position = (long)target;
    stream->pushed = EOF;
    stream->eof = 0;
    return 0;
}

long rb_espeak_ftell(rb_espeak_FILE *stream) { return readable(stream) ? stream->position : -1; }
void rb_espeak_rewind(rb_espeak_FILE *stream)
{
    rb_espeak_fseek(stream, 0, SEEK_SET);
    rb_espeak_clearerr(stream);
}
int rb_espeak_feof(rb_espeak_FILE *stream) { return stream ? stream->eof : 0; }
int rb_espeak_ferror(rb_espeak_FILE *stream) { return stream ? stream->error : 1; }
void rb_espeak_clearerr(rb_espeak_FILE *stream)
{
    if (stream)
        stream->eof = stream->error = 0;
}

size_t rb_espeak_fwrite(const void *data, size_t size, size_t count, rb_espeak_FILE *stream)
{
    (void)data;
    if (size && count)
        stream_error(stream, EROFS);
    return 0;
}
int rb_espeak_fputc(int character, rb_espeak_FILE *stream)
{
    (void)character;
    return stream_error(stream, EROFS);
}
int rb_espeak_fputs(const char *text, rb_espeak_FILE *stream)
{
    (void)text;
    return stream_error(stream, EROFS);
}
int rb_espeak_fflush(rb_espeak_FILE *stream)
{
    if (!stream || stream == rb_espeak_stdout || stream == rb_espeak_stderr)
        return 0;
    return stream_error(stream, ENOTSUP);
}
int rb_espeak_vfprintf(rb_espeak_FILE *stream, const char *format, va_list arguments)
{
    int length;
    if (stream != rb_espeak_stdout && stream != rb_espeak_stderr)
        return stream_error(stream, EROFS);
    if (!format)
        return stream_error(stream, EINVAL);
    length = vsnprintf(diagnostic, sizeof(diagnostic), format, arguments);
    if (length < 0 || (size_t)length >= sizeof(diagnostic))
        return stream_error(stream, EOVERFLOW);
    return length;
}
int rb_espeak_fprintf(rb_espeak_FILE *stream, const char *format, ...)
{
    int result;
    va_list arguments;
    va_start(arguments, format);
    result = rb_espeak_vfprintf(stream, format, arguments);
    va_end(arguments);
    return result;
}
int rb_espeak_printf(const char *format, ...)
{
    int result;
    va_list arguments;
    va_start(arguments, format);
    result = rb_espeak_vfprintf(rb_espeak_stdout, format, arguments);
    va_end(arguments);
    return result;
}

struct rb_espeak_DIR {
    DIR *handle;
    struct rb_espeak_dirent entry;
};

rb_espeak_DIR *rb_espeak_opendir(const char *path)
{
    rb_espeak_DIR *directory;
    DIR *handle;
    if (!path || !*path)
    {
        rb_espeak_errno = EINVAL;
        return NULL;
    }
    handle = opendir(path);
    if (!handle)
    {
        rb_espeak_errno = errno;
        return NULL;
    }
    directory = rb_espeak_malloc(sizeof(*directory));
    if (!directory)
    {
        closedir(handle);
        return NULL;
    }
    directory->handle = handle;
    return directory;
}

struct rb_espeak_dirent *rb_espeak_readdir(rb_espeak_DIR *directory)
{
    struct dirent *entry;
    size_t length;
    if (!directory)
    {
        rb_espeak_errno = EBADF;
        return NULL;
    }
    errno = 0;
    entry = readdir(directory->handle);
    rb_espeak_errno = errno;
    if (!entry)
        return NULL;
    length = strlen(entry->d_name);
    if (length >= sizeof(directory->entry.d_name))
    {
        rb_espeak_errno = ENAMETOOLONG;
        return NULL;
    }
    memcpy(directory->entry.d_name, entry->d_name, length + 1);
    return &directory->entry;
}

int rb_espeak_closedir(rb_espeak_DIR *directory)
{
    int result;
    if (!directory)
    {
        rb_espeak_errno = EBADF;
        return -1;
    }
    result = closedir(directory->handle);
    if (result < 0)
        rb_espeak_errno = errno;
    rb_espeak_free(directory);
    return result;
}

int rb_espeak_stat(const char *path, struct rb_espeak_stat *details)
{
    DIR *directory;
    int descriptor;
    off_t length;
    int saved_error;
    if (!path || !*path || !details)
    {
        rb_espeak_errno = EINVAL;
        return -1;
    }
    directory = opendir(path);
    if (directory)
    {
        if (closedir(directory) < 0)
        {
            rb_espeak_errno = errno;
            return -1;
        }
        details->st_mode = RB_ESPEAK_S_IFDIR;
        details->st_size = 0;
        return 0;
    }
    descriptor = open(path, O_RDONLY);
    if (descriptor < 0)
    {
        rb_espeak_errno = errno;
        return -1;
    }
    length = ffilesize(descriptor);
    saved_error = errno;
    if (close(descriptor) < 0 && length >= 0)
    {
        rb_espeak_errno = errno;
        return -1;
    }
    if (length < 0)
    {
        rb_espeak_errno = saved_error;
        return -1;
    }
    details->st_mode = RB_ESPEAK_S_IFREG;
    details->st_size = length;
    return 0;
}

int rb_espeak_lstat(const char *path, struct rb_espeak_stat *details)
{
    return rb_espeak_stat(path, details);
}

char *rb_espeak_getenv(const char *name) { (void)name; return NULL; }
int rb_espeak_access(const char *path, int mode)
{
    struct rb_espeak_stat details;
    if (mode != 0 && mode != 4)
    {
        rb_espeak_errno = (mode & 2) ? EROFS : EINVAL;
        return -1;
    }
    return rb_espeak_stat(path, &details);
}
int rb_espeak_remove(const char *path)
{
    (void)path;
    rb_espeak_errno = EROFS;
    return -1;
}
unsigned int rb_espeak_sleep(unsigned int seconds)
{
    rb_espeak_errno = ENOSYS;
    return seconds;
}
int rb_espeak_usleep(unsigned long microseconds)
{
    (void)microseconds;
    rb_espeak_errno = ENOSYS;
    return -1;
}
int rb_espeak_nanosleep(const struct timespec *request, struct timespec *remaining)
{
    (void)request;
    (void)remaining;
    rb_espeak_errno = ENOSYS;
    return -1;
}
