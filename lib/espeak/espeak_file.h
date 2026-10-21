#ifndef RB_ESPEAK_FILE_H
#define RB_ESPEAK_FILE_H

#include <stdio.h>
#include <sys/stat.h>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

typedef struct _stat64 EspeakFileInfo;

static inline bool espeak_wide_path(const char *path, wchar_t *wide, int capacity)
{
    return MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1,
                               wide, capacity) != 0;
}

static inline FILE *espeak_fopen(const char *path, const char *mode)
{
    wchar_t wide_path[MAX_PATH];
    wchar_t wide_mode[8];
    if (!espeak_wide_path(path, wide_path, MAX_PATH) ||
        !espeak_wide_path(mode, wide_mode, 8))
        return NULL;
    return _wfopen(wide_path, wide_mode);
}

static inline int espeak_stat(const char *path, EspeakFileInfo *details)
{
    wchar_t wide_path[MAX_PATH];
    if (!espeak_wide_path(path, wide_path, MAX_PATH))
        return -1;
    return _wstat64(wide_path, details);
}

static inline int espeak_lstat(const char *path, EspeakFileInfo *details)
{
    wchar_t wide_path[MAX_PATH];
    if (!espeak_wide_path(path, wide_path, MAX_PATH))
        return -1;
    DWORD attributes = GetFileAttributesW(wide_path);
    if (attributes == INVALID_FILE_ATTRIBUTES)
        return -1;
    if (attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    {
        details->st_mode = 0;
        return 0;
    }
    return _wstat64(wide_path, details);
}

#else

typedef struct stat EspeakFileInfo;
#define espeak_fopen fopen
#define espeak_stat stat
#define espeak_lstat lstat

#endif
#endif
