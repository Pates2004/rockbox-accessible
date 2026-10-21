"""Exercise native eSpeak against narrow Rockbox mocks, on a POSIX test host."""

import datetime
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "lib/espeak/native"
RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
WORKSPACE = _project_materials_root(ROOT) / "espeak-native-runtime" / RUN

HEADERS = {
    "config.h": "#pragma once\n#define CONFIG_PLATFORM 0\n#define PLATFORM_HOSTED 8\n",
    "system.h": """#pragma once
int mock_disable_irq_save(void);
void mock_restore_irq(int previous);
#define disable_irq_save mock_disable_irq_save
#define restore_irq mock_restore_irq
""",
    "kernel.h": "#pragma once\nvoid mock_yield(void);\n#define yield mock_yield\n",
    "panic.h": "#pragma once\nvoid panicf(const char *format, ...) __attribute__((noreturn));\n",
    "file.h": """#pragma once
#include <sys/types.h>
#include <fcntl.h>
#include <unistd.h>
int mock_open(const char *path, int flags);
int mock_close(int descriptor);
ssize_t mock_read(int descriptor, void *buffer, size_t count);
off_t mock_lseek(int descriptor, off_t offset, int origin);
off_t mock_ffilesize(int descriptor);
#define open mock_open
#define close mock_close
#define read mock_read
#define lseek mock_lseek
#define ffilesize mock_ffilesize
""",
    "dir.h": """#pragma once
#include <dirent.h>
DIR *mock_opendir(const char *path);
struct dirent *mock_readdir(DIR *directory);
int mock_closedir(DIR *directory);
#define opendir mock_opendir
#define readdir mock_readdir
#define closedir mock_closedir
""",
}

MOCK_SOURCE = r"""
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

int mock_irq_level;
int mock_irq_transitions;
int mock_yields;
int mock_files;
int mock_directories;
int mock_fail_read;
int mock_fail_seek;
int mock_fail_size;
int mock_fail_close;
int mock_fail_readdir;
int mock_read_calls;
int mock_seek_calls;
size_t mock_read_limit;

int mock_disable_irq_save(void)
{
    int previous = mock_irq_level;
    mock_irq_level = 1;
    ++mock_irq_transitions;
    return previous;
}
void mock_restore_irq(int previous) { mock_irq_level = previous; }
void mock_yield(void) { assert(!mock_irq_level); ++mock_yields; }
void panicf(const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    abort();
}
int mock_open(const char *path, int flags)
{
    assert(flags == O_RDONLY);
    int descriptor = open(path, flags);
    if (descriptor >= 0)
        ++mock_files;
    return descriptor;
}
int mock_close(int descriptor)
{
    int result = close(descriptor);
    if (!result)
        --mock_files;
    if (mock_fail_close)
    {
        errno = EIO;
        return -1;
    }
    return result;
}
ssize_t mock_read(int descriptor, void *buffer, size_t count)
{
    ++mock_read_calls;
    if (mock_fail_read)
    {
        errno = EIO;
        return -1;
    }
    if (mock_read_limit && count > mock_read_limit)
        count = mock_read_limit;
    return read(descriptor, buffer, count);
}
off_t mock_lseek(int descriptor, off_t offset, int origin)
{
    ++mock_seek_calls;
    if (mock_fail_seek)
    {
        errno = EIO;
        return -1;
    }
    return lseek(descriptor, offset, origin);
}
off_t mock_ffilesize(int descriptor)
{
    struct stat details;
    if (mock_fail_size)
    {
        errno = EIO;
        return -1;
    }
    return fstat(descriptor, &details) ? -1 : details.st_size;
}
DIR *mock_opendir(const char *path)
{
    DIR *directory = opendir(path);
    if (directory)
        ++mock_directories;
    return directory;
}
struct dirent *mock_readdir(DIR *directory)
{
    if (mock_fail_readdir)
    {
        errno = EIO;
        return NULL;
    }
    return readdir(directory);
}
int mock_closedir(DIR *directory)
{
    int result = closedir(directory);
    if (!result)
        --mock_directories;
    return result;
}
"""

RUNTIME_PROBE = r"""
#include <assert.h>
#include <errno.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "native_runtime.h"

extern int mock_irq_level, mock_irq_transitions, mock_yields, mock_files, mock_directories;
extern int mock_fail_read, mock_fail_seek, mock_fail_size, mock_fail_close, mock_fail_readdir;
extern int mock_read_calls, mock_seek_calls;
extern size_t mock_read_limit;

static void test_heap(void)
{
    size_t baseline = rb_espeak_heap_used();
    size_t available = rb_espeak_heap_available();
    assert(rb_espeak_heap_capacity() == RB_ESPEAK_HEAP_BYTES);
    assert(available + baseline == rb_espeak_heap_capacity());
    assert(baseline > 0 && baseline < 16384);
    unsigned char *first = rb_espeak_malloc(32768);
    unsigned char *middle = rb_espeak_malloc(32768);
    unsigned char *barrier = rb_espeak_malloc(32768);
    void *tail_barrier = rb_espeak_malloc(32768);
    assert(first && middle && barrier && tail_barrier);
    assert((uintptr_t)first % _Alignof(double) == 0);
    memset(first, 0x5a, 32768);
    memset(barrier, 0x6c, 32768);
    rb_espeak_free(middle);
    unsigned char *grown = rb_espeak_realloc(first, 60000);
    assert(grown == first);
    for (size_t index = 0; index < 32768; ++index)
        assert(grown[index] == 0x5a);
    unsigned char *shrunk = rb_espeak_realloc(grown, 1024);
    assert(shrunk == grown);
    unsigned char *moved = rb_espeak_realloc(barrier, 200000);
    assert(moved && moved != barrier);
    for (size_t index = 0; index < 32768; ++index)
        assert(moved[index] == 0x6c);
    assert(!rb_espeak_realloc(moved, SIZE_MAX));
    assert(rb_espeak_errno == ENOMEM && moved[0] == 0x6c);
    assert(!rb_espeak_calloc(SIZE_MAX, 2));
    assert(!rb_espeak_malloc(SIZE_MAX));
    assert(rb_espeak_heap_failures() >= 3);
    rb_espeak_free(moved);
    rb_espeak_free(tail_barrier);
    assert(!rb_espeak_realloc(shrunk, 0));
    rb_espeak_free(NULL);
    assert(rb_espeak_heap_used() == baseline);
    void *zero = rb_espeak_calloc(0, SIZE_MAX);
    assert(zero);
    rb_espeak_free(zero);
    unsigned char *cleared = rb_espeak_calloc(16, 16);
    assert(cleared);
    for (size_t index = 0; index < 256; ++index)
        assert(cleared[index] == 0);
    rb_espeak_free(cleared);
    void *blocks[2048];
    size_t count = 0;
    while (count < 2048 && (blocks[count] = rb_espeak_malloc(1024)))
        ++count;
    assert(count < 2048 && count > 1000);
    for (size_t index = 0; index < count; index += 2)
        rb_espeak_free(blocks[index]);
    assert(!rb_espeak_malloc(32768));
    for (size_t index = 1; index < count; index += 2)
        rb_espeak_free(blocks[index]);
    assert(rb_espeak_heap_available() == available);
    void *large = rb_espeak_malloc(available - available / 16);
    assert(large);
    rb_espeak_free(large);
    assert(rb_espeak_heap_used() == baseline);
    assert(rb_espeak_heap_peak() > baseline + 1000000);
    unsigned char *slots[64] = { 0 };
    size_t sizes[64] = { 0 };
    uint32_t random_state = 0x73acd138;
    for (size_t iteration = 0; iteration < 16000; ++iteration)
    {
        random_state ^= random_state << 13;
        random_state ^= random_state >> 17;
        random_state ^= random_state << 5;
        size_t slot = random_state % 64;
        size_t size = (random_state >> 6) % 32768;
        size_t retained = sizes[slot] < size ? sizes[slot] : size;
        unsigned char *resized = rb_espeak_realloc(slots[slot], size);
        if (resized || !size)
        {
            for (size_t index = 0; index < retained; ++index)
                assert(resized[index] == (unsigned char)slot);
            slots[slot] = resized;
            sizes[slot] = size;
            if (size)
                memset(resized, (int)slot, size);
        }
        else
        {
            for (size_t index = 0; index < sizes[slot]; ++index)
                assert(slots[slot][index] == (unsigned char)slot);
        }
    }
    for (size_t slot = 0; slot < 64; ++slot)
        rb_espeak_free(slots[slot]);
    assert(rb_espeak_heap_used() == baseline);
}

static void test_files(const char *path, const char *directory_path)
{
    size_t baseline = rb_espeak_heap_used();
    struct rb_espeak_stat details;
    assert(!rb_espeak_stat(path, &details) && details.st_size == 1539);
    assert(details.st_mode == RB_ESPEAK_S_IFREG);
    assert(!rb_espeak_lstat(directory_path, &details) && details.st_mode == RB_ESPEAK_S_IFDIR);
    assert(!rb_espeak_access(path, 4));
    assert(rb_espeak_access(path, 2) == -1 && rb_espeak_errno == EROFS);
    assert(rb_espeak_remove(path) == -1 && rb_espeak_errno == EROFS);
    assert(!rb_espeak_fopen(path, "w") && rb_espeak_errno == EROFS);
    assert(!rb_espeak_fopen(path, "r+") && rb_espeak_errno == EROFS);
    assert(!rb_espeak_fopen(NULL, "rb") && rb_espeak_errno == EINVAL);
    assert(!rb_espeak_fopen("/missing-rb-espeak-fixture", "rb"));
    rb_espeak_FILE *stream = rb_espeak_fopen(path, "rb");
    assert(stream && mock_files == 1);
    char buffer[2048];
    assert(rb_espeak_fread(buffer, 1, 3, stream) == 3 && !memcmp(buffer, "abc", 3));
    assert(rb_espeak_ftell(stream) == 3 && !rb_espeak_feof(stream));
    assert(rb_espeak_ungetc('X', stream) == 'X' && rb_espeak_ftell(stream) == 2);
    assert(rb_espeak_ungetc('Y', stream) == EOF);
    assert(rb_espeak_fgetc(stream) == 'X');
    assert(!rb_espeak_fseek(stream, -2, SEEK_CUR) && rb_espeak_fgetc(stream) == 'b');
    assert(!rb_espeak_fseek(stream, -3, SEEK_END));
    assert(rb_espeak_fread(buffer, 2, 2, stream) == 1);
    assert(!memcmp(buffer, "xyz", 3) && rb_espeak_feof(stream));
    assert(rb_espeak_ungetc('z', stream) == 'z' && !rb_espeak_feof(stream));
    assert(rb_espeak_fgetc(stream) == 'z' && rb_espeak_fgetc(stream) == EOF);
    rb_espeak_rewind(stream);
    assert(!rb_espeak_ftell(stream) && !rb_espeak_feof(stream));
    assert(rb_espeak_fgets(buffer, 8, stream) == buffer && !strcmp(buffer, "abc\n"));
    assert(rb_espeak_fgets(buffer, 1, stream) == buffer && !buffer[0]);
    assert(rb_espeak_fseek(stream, -1, SEEK_SET) == -1);
    assert(rb_espeak_fseek(stream, 1, 9) == -1);
    assert(rb_espeak_ferror(stream));
    rb_espeak_clearerr(stream);
    assert(!rb_espeak_ferror(stream));
    assert(!rb_espeak_fwrite("BAD", 1, 3, stream));
    assert(rb_espeak_ferror(stream) && rb_espeak_errno == EROFS);
    assert(rb_espeak_fputc('B', stream) == EOF);
    assert(rb_espeak_fputs("BAD", stream) == EOF);
    assert(rb_espeak_fflush(stream) == EOF);
    assert(!rb_espeak_fclose(stream) && mock_files == 0);
    mock_read_limit = 7;
    stream = rb_espeak_fopen(path, "r");
    assert(rb_espeak_fread(buffer, 1, sizeof(buffer), stream) == 1539);
    assert(buffer[1538] == 'z');
    assert(!rb_espeak_fclose(stream));
    mock_read_limit = 0;
    rb_espeak_DIR *directory = rb_espeak_opendir(directory_path);
    assert(directory && mock_directories == 1);
    int found = 0;
    struct rb_espeak_dirent *entry;
    while ((entry = rb_espeak_readdir(directory)))
        found |= !strcmp(entry->d_name, "fixture.dat");
    assert(found && rb_espeak_errno == 0);
    assert(!rb_espeak_closedir(directory) && !mock_directories);
    assert(rb_espeak_heap_used() == baseline);
    assert(mock_yields > 0);
}

static void test_errors(const char *path, const char *directory_path)
{
    rb_espeak_FILE *stream = rb_espeak_fopen(path, "rb");
    char data[8];
    assert(stream);
    mock_fail_read = 1;
    assert(rb_espeak_fread(data, 1, 4, stream) == 0);
    assert(rb_espeak_ferror(stream) && !rb_espeak_feof(stream) && rb_espeak_errno == EIO);
    mock_fail_read = 0;
    rb_espeak_clearerr(stream);
    assert(rb_espeak_fgetc(stream) == 'a');
    mock_fail_seek = 1;
    assert(rb_espeak_fseek(stream, 1024, SEEK_SET) == -1 && rb_espeak_ftell(stream) == 1);
    assert(rb_espeak_fgetc(stream) == 'b');
    mock_fail_seek = 0;
    mock_fail_size = 1;
    assert(rb_espeak_fseek(stream, 0, SEEK_END) == -1 && rb_espeak_errno == EIO);
    struct rb_espeak_stat details;
    assert(rb_espeak_stat(path, &details) == -1 && rb_espeak_errno == EIO && mock_files == 1);
    mock_fail_size = 0;
    assert(!rb_espeak_fread(data, SIZE_MAX, 2, stream) && rb_espeak_errno == EINVAL);
    mock_fail_close = 1;
    assert(rb_espeak_fclose(stream) == EOF && mock_files == 0);
    mock_fail_close = 0;
    assert(rb_espeak_fclose(NULL) == EOF && rb_espeak_errno == EBADF);
    assert(rb_espeak_fgetc(rb_espeak_stdin) == EOF);
    rb_espeak_DIR *directory = rb_espeak_opendir(directory_path);
    assert(directory);
    mock_fail_readdir = 1;
    assert(!rb_espeak_readdir(directory) && rb_espeak_errno == EIO);
    mock_fail_readdir = 0;
    assert(!rb_espeak_closedir(directory));
    assert(!rb_espeak_readdir(NULL) && rb_espeak_errno == EBADF);
    assert(rb_espeak_fprintf(rb_espeak_stderr, "native error %d", 42) == 15);
    assert(!strcmp(rb_espeak_native_diagnostic(), "native error 42"));
    assert(!rb_espeak_fflush(rb_espeak_stderr));
    char huge[300];
    memset(huge, 'x', sizeof(huge) - 1);
    huge[sizeof(huge) - 1] = 0;
    assert(rb_espeak_printf("%s", huge) == EOF && rb_espeak_errno == EOVERFLOW);
    assert(!rb_espeak_getenv("HOME") && !rb_espeak_getenv("ESPEAK_DATA_PATH"));
    struct timespec request = { 1, 2 }, remaining = { 3, 4 };
    assert(rb_espeak_nanosleep(&request, &remaining) == -1 && rb_espeak_errno == ENOSYS);
    assert(remaining.tv_sec == 3 && remaining.tv_nsec == 4);
    assert(rb_espeak_sleep(7) == 7 && rb_espeak_usleep(100) == -1);
    size_t baseline = rb_espeak_heap_used();
    void *blocks[4096];
    size_t count = 0;
    while (count < 4096 && (blocks[count] = rb_espeak_malloc(1024)))
        ++count;
    while (count < 4096 && (blocks[count] = rb_espeak_malloc(16)))
        ++count;
    assert(count < 4096);
    assert(!rb_espeak_fopen(path, "rb") && rb_espeak_errno == ENOMEM && !mock_files);
    assert(!rb_espeak_opendir(directory_path) && rb_espeak_errno == ENOMEM && !mock_directories);
    while (count)
        rb_espeak_free(blocks[--count]);
    assert(rb_espeak_heap_used() == baseline);
}

static void test_unicode(void)
{
    assert(rb_espeak_iswalpha(0x105) && rb_espeak_towlower(0x17b) == 0x17c);
    assert(rb_espeak_iswalpha(0x4e2d) && rb_espeak_iswalpha(0x3a9));
    assert(rb_espeak_towlower(0x416) == 0x436 && rb_espeak_towupper(0x3c9) == 0x3a9);
    assert(rb_espeak_towlower(0x10400) == 0x10428);
    assert(rb_espeak_iswupper(0x10400) && rb_espeak_iswlower(0x10428));
    assert(rb_espeak_iswdigit(0x661) && rb_espeak_iswalnum(0x966));
    assert(rb_espeak_iswspace(0xa0) && rb_espeak_iswspace(0x2003) && rb_espeak_iswspace(0x2028));
    assert(!rb_espeak_iswspace(0x200b));
    assert(rb_espeak_iswpunct(0x2014) && rb_espeak_iswpunct('$'));
    assert(!rb_espeak_iswalpha(0xd800) && !rb_espeak_iswalpha(UINT32_MAX));
    assert(rb_espeak_towupper(UINT32_MAX) == UINT32_MAX);
    assert(!rb_espeak_isalpha(0xe9) && !rb_espeak_isalpha(-1));
    assert(rb_espeak_isalpha('Q') && rb_espeak_tolower('Q') == 'q');
    assert(rb_espeak_tolower(-1) == -1 && rb_espeak_isspace('\v'));
    wchar_t output[16];
    const char *text = "A\xc4\x85\xce\xa9\xf0\x90\x90\xa8";
    assert(rb_espeak_mbstowcs(output, text, 16) == 4);
    assert(output[0] == 'A' && output[1] == 0x105 && output[2] == 0x3a9 && output[3] == 0x10428);
    assert(rb_espeak_mbstowcs(NULL, text, 0) == 4);
    char encoded[32];
    assert(rb_espeak_wcstombs(encoded, output, sizeof(encoded)) == strlen(text));
    assert(!strcmp(encoded, text));
    assert(rb_espeak_wcstombs(encoded, output, 2) == 1);
    assert(rb_espeak_wcstombs(NULL, output, 0) == strlen(text));
    rb_espeak_mbstate_t state = { { 0 }, 0 };
    wchar_t character;
    assert(rb_espeak_mbrtowc(&character, "\xf0\x90", 2, &state) == (size_t)-2);
    assert(!rb_espeak_mbsinit(&state));
    assert(rb_espeak_mbrtowc(&character, "\x90\xa8", 2, &state) == 2 && character == 0x10428);
    assert(rb_espeak_mbsinit(&state));
    const char *bad[] = { "\xc0\xaf", "\xed\xa0\x80", "\xf4\x90\x80\x80", "\x80", "\xe2" };
    for (size_t index = 0; index < sizeof(bad) / sizeof(*bad); ++index)
        assert(rb_espeak_mbtowc(&character, bad[index], strlen(bad[index])) == -1 && rb_espeak_errno == EILSEQ);
    assert(rb_espeak_wctomb(encoded, 0xd800) == -1 && rb_espeak_errno == EILSEQ);
    assert(rb_espeak_mbrtowc(&character, "", 1, &state) == 0 && character == 0);
    assert(rb_espeak_mbrtowc(&character, "a", 0, &state) == (size_t)-2);
    assert(rb_espeak_wcslen(output) == 4 && rb_espeak_wcschr(output, 0) == output + 4);
    wchar_t copied[8];
    rb_espeak_wcsncpy(copied, output, 8);
    assert(!rb_espeak_wcsncmp(copied, output, 8) && copied[7] == 0);
    assert(rb_espeak_wcsncmp(L"a", L"b", 1) < 0);
}

static void test_buffered_seek(const char *path)
{
    rb_espeak_FILE *stream = rb_espeak_fopen(path, "rb");
    assert(stream);
    assert(rb_espeak_fgetc(stream) == 'a');
    assert(mock_read_calls == 1 && mock_seek_calls == 0);
    for (int entry = 0; entry < 40; ++entry)
    {
        assert(!rb_espeak_fseek(stream, 7, SEEK_CUR));
        assert(rb_espeak_fgetc(stream) == 'q');
        assert(rb_espeak_ftell(stream) == 9 + entry * 8);
    }
    assert(mock_read_calls == 1 && mock_seek_calls == 0);
    assert(!rb_espeak_fseek(stream, 4, SEEK_SET));
    assert(rb_espeak_fgetc(stream) == 'q');
    assert(rb_espeak_ungetc('X', stream) == 'X' && rb_espeak_ftell(stream) == 4);
    assert(!rb_espeak_fseek(stream, 0, SEEK_CUR));
    assert(rb_espeak_fgetc(stream) == 'q');
    assert(rb_espeak_ungetc('X', stream) == 'X');
    assert(!rb_espeak_fseek(stream, -3, SEEK_CUR));
    assert(rb_espeak_fgetc(stream) == 'b');
    assert(mock_read_calls == 1 && mock_seek_calls == 0);
    assert(!rb_espeak_fseek(stream, 512, SEEK_SET));
    assert(mock_read_calls == 1 && mock_seek_calls == 0);
    assert(rb_espeak_fgetc(stream) == 'q' && mock_read_calls == 2 && mock_seek_calls == 0);
    assert(!rb_espeak_fseek(stream, 511, SEEK_SET));
    assert(mock_seek_calls == 1 && rb_espeak_fgetc(stream) == 'q' && mock_read_calls == 3);
    assert(!rb_espeak_fseek(stream, 1530, SEEK_SET));
    char buffer[32];
    assert(rb_espeak_fread(buffer, 1, 32, stream) == 9 && rb_espeak_feof(stream));
    int reads = mock_read_calls;
    int seeks = mock_seek_calls;
    assert(!rb_espeak_fseek(stream, -3, SEEK_CUR) && !rb_espeak_feof(stream));
    assert(rb_espeak_fread(buffer, 1, 3, stream) == 3 && !memcmp(buffer, "xyz", 3));
    assert(mock_read_calls == reads && mock_seek_calls == seeks);
    assert(rb_espeak_fputc('x', stream) == EOF && rb_espeak_ferror(stream));
    assert(!rb_espeak_fseek(stream, -1, SEEK_CUR) && rb_espeak_ferror(stream));
    assert(rb_espeak_fgetc(stream) == 'z');
    assert(mock_read_calls == reads && mock_seek_calls == seeks);
    rb_espeak_clearerr(stream);
    assert(!rb_espeak_fclose(stream));
}

static void test_numbers(void)
{
    char *end;
    wchar_t *wide_end;
    assert(rb_espeak_wcstod(L"  -12.5%", &wide_end) == -12.5 && *wide_end == '%');
    assert(rb_espeak_strtod("1,5", &end) == 1 && *end == ',');
    assert(rb_espeak_strtod("3e+", &end) == 3 && *end == 'e');
    assert(fabs(rb_espeak_strtod(".125e2x", &end) - 12.5) < 1e-12 && *end == 'x');
    assert(rb_espeak_strtod("0x1.8p+2x", &end) == 6 && *end == 'x');
    assert(isinf(rb_espeak_strtod("-infinity", &end)) && !*end);
    assert(isnan(rb_espeak_strtod("nan(payload)", &end)) && !*end);
    const char *invalid = " -bad";
    assert(rb_espeak_strtod(invalid, &end) == 0 && end == invalid);
    assert(signbit(rb_espeak_strtod("-0", &end)));
    rb_espeak_errno = 0;
    assert(isinf(rb_espeak_strtod("1e999999999", &end)) && rb_espeak_errno == ERANGE);
    rb_espeak_errno = 0;
    assert(rb_espeak_strtod("1e-99999999", &end) == 0 && rb_espeak_errno == ERANGE);
    assert(rb_espeak_strtol("0x123tail", &end, 0) == 0x123 && *end == 't');
    assert(rb_espeak_strtoul("123!", &end, 10) == 123 && *end == '!');
    assert(rb_espeak_strtol("999999999999999999999999", &end, 10) == LONG_MAX && rb_espeak_errno == ERANGE);
    assert(rb_espeak_abs(-42) == 42 && rb_espeak_abs(42) == 42);
    assert(rb_espeak_abs(INT_MIN) == INT_MAX && rb_espeak_errno == ERANGE);
    assert(rb_espeak_strspn("abbccx", "cab") == 5);
    assert(rb_espeak_strspn("abc", "") == 0 && rb_espeak_strspn("", "a") == 0);
    char tokens[] = ",;alpha,beta;;gamma";
    assert(!strcmp(rb_espeak_strtok(tokens, ",;"), "alpha"));
    assert(!strcmp(rb_espeak_strtok(NULL, ",;"), "beta"));
    assert(!strcmp(rb_espeak_strtok(NULL, ",;"), "gamma"));
    assert(!rb_espeak_strtok(NULL, ",;") && !rb_espeak_strtok(NULL, ",;"));
    char unbroken[] = "whole string";
    assert(rb_espeak_strtok(unbroken, "") == unbroken);
    assert(!rb_espeak_strtok(NULL, ""));
}

static void callback(void *context) { ++*(int *)context; }
static void test_flags(void)
{
    assert(!rb_espeak_engine_ready());
    assert(rb_espeak_engine_acquire() && !rb_espeak_engine_acquire());
    rb_espeak_engine_release();
    mock_irq_level = 1;
    assert(rb_espeak_engine_acquire() && mock_irq_level == 1);
    rb_espeak_engine_mark_ready();
    assert(rb_espeak_engine_ready() && mock_irq_level == 1);
    rb_espeak_engine_release();
    assert(mock_irq_level == 1 && mock_irq_transitions == 8);
    mock_irq_level = 0;
    int count = 0;
    rb_espeak_native_set_yield(callback, &count);
    rb_espeak_native_yield();
    assert(count == 1 && mock_yields == 0);
    rb_espeak_native_set_yield(NULL, NULL);
    rb_espeak_native_yield();
    assert(mock_yields == 1);
}

int main(int argc, char **argv)
{
    assert(argc == 4);
    if (!strcmp(argv[1], "heap")) test_heap();
    else if (!strcmp(argv[1], "files")) test_files(argv[2], argv[3]);
    else if (!strcmp(argv[1], "errors")) test_errors(argv[2], argv[3]);
    else if (!strcmp(argv[1], "unicode")) test_unicode();
    else if (!strcmp(argv[1], "buffered-seek")) test_buffered_seek(argv[2]);
    else if (!strcmp(argv[1], "numbers")) test_numbers();
    else if (!strcmp(argv[1], "flags")) test_flags();
    else return 2;
    puts("PASS native runtime");
    return 0;
}
"""

HEADER_PROBE = r"""
#include <stdlib.h>
#include <string.h>
#include <locale.h>
#include <stdio.h>
#include <ctype.h>
#include <wctype.h>
#include <wchar.h>
#include <errno.h>
#include <sys/stat.h>
#include <dirent.h>
#include <unistd.h>
#include <stdio.h>
#include <wchar.h>
int probe(const char *path)
{
    struct stat details;
    FILE *stream = fopen(path, "rb");
    DIR *directory = opendir(path);
    mbstate_t state = {};
    wchar_t character;
    void *memory = malloc(32);
    char tokens[] = "a,b";
    char *first = strtok(tokens, ",");
    free(memory);
    if (stream) fclose(stream);
    if (directory) closedir(directory);
    return stat(path, &details) + isalpha('a') + iswalpha(0x105) +
        towlower(0x17b) + (int)mbrtowc(&character, "a", 1, &state) + errno +
        (int)strspn(first, "a") + abs(-7);
}
"""


def command(arguments, build, label, environment=None):
    result = subprocess.run([str(argument) for argument in arguments], capture_output=True,
                            text=True, timeout=180, env=environment)
    (build / (label + ".log")).write_text(shlex.join(map(str, arguments)) + "\n" +
                                         result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise AssertionError(f"{label} failed ({result.returncode}):\n{result.stdout}{result.stderr}")
    return result.stdout


def build_runtime(build, flags=(), compiler="gcc", hosted=False):
    """Return reusable adapter/TLSF/utf8proc/mock objects; no engine shadow includes."""
    build.mkdir(parents=True, exist_ok=True)
    mocks = build / "mocks"
    mocks.mkdir(exist_ok=True)
    for name, content in HEADERS.items():
        if hosted and name == "config.h":
            content = content.replace("#define CONFIG_PLATFORM 0", "#define CONFIG_PLATFORM 8")
        (mocks / name).write_text(content, encoding="utf-8")
    (build / "mock_rockbox.c").write_text(MOCK_SOURCE, encoding="utf-8")
    sources = [NATIVE / "native_runtime.c", NATIVE / "native_text.c",
               ROOT / "lib/tlsf/src/tlsf.c", ROOT / "lib/utf8proc/utf8proc.c",
               build / "mock_rockbox.c"]
    objects = []
    for source in sources:
        output = build / (source.stem + ".o")
        command([compiler, "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-fno-common",
                 "-ffunction-sections", "-fdata-sections", "-fno-strict-overflow", "-DROCKBOX=1", "-DTLSF_STATISTIC=1",
                 "-DUTF8PROC_STATIC", "-I" + str(mocks), "-include", str(mocks / "config.h"),
                 *flags, "-c", source, "-o", output], build, "compile-" + source.stem)
        objects.append(output)
    return objects


class NativeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name == "nt" or not shutil.which("gcc"):
            raise unittest.SkipTest("Run this native mock harness under WSL/POSIX with GCC")
        cls.builds = []
        for mode, flags in (("normal", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"]),
                            ("asan", ["-fsanitize=address", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"])):
            build = WORKSPACE / mode
            objects = build_runtime(build, flags)
            (build / "probe.c").write_text(RUNTIME_PROBE, encoding="utf-8")
            (build / "fixture.dat").write_bytes(b"abc\n" + b"q" * 1532 + b"xyz")
            executable = build / "runtime-probe"
            command(["gcc", "-std=gnu11", "-g", "-Wall", "-Wextra", "-Werror", *flags,
                     "-I" + str(NATIVE), build / "probe.c", *objects, "-Wl,--gc-sections", "-lm",
                     "-o", executable], build, "link-probe")
            cls.builds.append((mode, build, executable, flags, objects))
        print("Reusable native runtime mocks and evidence: " + str(WORKSPACE), flush=True)

    def run_probe(self, name):
        for mode, build, executable, _, _ in self.builds:
            with self.subTest(mode=mode):
                environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                                   UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                command([executable, name, build / "fixture.dat", build], build, name, environment)

    def test_heap(self): self.run_probe("heap")
    def test_files(self): self.run_probe("files")
    def test_errors(self): self.run_probe("errors")
    def test_unicode(self): self.run_probe("unicode")
    def test_buffered_seek(self): self.run_probe("buffered-seek")
    def test_numbers(self): self.run_probe("numbers")
    def test_flags(self): self.run_probe("flags")

    def test_shadow_headers(self):
        build = self.builds[0][1]
        source = build / "headers.cpp"
        source.write_text(HEADER_PROBE, encoding="utf-8")
        compilers = ["g++"]
        if shutil.which("arm-none-eabi-g++"):
            compilers.append("arm-none-eabi-g++")
        for compiler in compilers:
            with self.subTest(compiler=compiler):
                flags = ["-mcpu=arm926ej-s", "-nostdinc++"] if compiler.startswith("arm-") else []
                output = build / (compiler + "-headers.o")
                command([compiler, *flags, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                         "-DRB_ESPEAK_NATIVE=1", "-I" + str(NATIVE / "include"), "-c", source,
                         "-o", output], build, compiler + "-headers")

    def test_shadow_headers_reject_core_use(self):
        build = self.builds[0][1]
        source = build / "wrong-includes.c"
        source.write_text("#include <stdio.h>\n", encoding="utf-8")
        result = subprocess.run(["gcc", "-I" + str(NATIVE / "include"), "-c", str(source),
                                 "-o", str(build / "wrong-includes.o")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shadow headers require RB_ESPEAK_NATIVE=1", result.stderr)
        (build / "wrong-includes.log").write_text(result.stderr, encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
