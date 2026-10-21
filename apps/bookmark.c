/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C)2003 by Benjamin Metzler
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This software is distributed on an "AS IS" basis, WITHOUT WARRANTY OF ANY
 * KIND, either express or implied.
 *
 ****************************************************************************/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <limits.h>

#include "config.h"
#include "action.h"
#include "audio.h"
#include "playlist.h"
#include "settings.h"
#include "tree.h"
#include "bookmark.h"
#include "system.h"
#include "icons.h"
#include "menu.h"
#include "lang.h"
#include "talk.h"
#include "misc.h"
#include "splash.h"
#include "yesno.h"
#include "list.h"
#include "plugin.h"
#include "file.h"
#include "pathfuncs.h"
#include "playlist_menu.h"
#include "iap-usb.h"
#ifdef HAVE_ESPEAK
#include "tts.h"
#endif

/*#define LOGF_ENABLE*/
#include "logf.h"

#define MAX_BOOKMARKS 10
#define MAX_BOOKMARK_SIZE  350
#define MAX_BOOKMARK_TEMP_FILES 16
#define RECENT_BOOKMARK_FILE ROCKBOX_DIR "/most-recent.bmark"
#define BOOKMARK_IGNORE "/bookmark.ignore"
#define BOOKMARK_UNIGNORE "/bookmark.unignore"

/* flags for write_bookmark() */
#define BMARK_WRITE        0x0
#define BMARK_ASK_USER     0x1
#define BMARK_CREATE_FILE  0x2
#define BMARK_CHECK_IGNORE 0x4

/* Used to buffer bookmarks while displaying the bookmark list. */
struct bookmark_list
{
    const char* filename;
    size_t buffer_size;
    int start;
    int count;
    int total_count;
    bool show_dont_resume;
    bool reload;
    bool show_playlist_name;
    char* items[];
};

/* flags for optional bookmark tokens */
#define BM_PITCH    0x01
#define BM_SPEED    0x02

/* bookmark values */
struct resume_info{
    const struct mp3entry *id3;
    int  resume_index;
    unsigned long resume_offset;
    int  resume_seed;
    long resume_elapsed;
    int  repeat_mode;
    bool shuffle;
    /* optional values */
    int  pitch;
    int  speed;
};

/* Temp buffer used for reading, create_bookmark and filename creation */
#ifdef HAVE_ESPEAK
#define TEMP_BUF_SIZE (MAX(MAX_BOOKMARK_SIZE, MAX_PATH + 100))
#else
#define TEMP_BUF_SIZE (MAX(MAX_BOOKMARK_SIZE, MAX_PATH + 1))
#endif
static char global_temp_buffer[TEMP_BUF_SIZE];

#ifdef HAVE_ESPEAK
static bool text_bookmark_path_valid(const char *path)
{
    if (!path || path[0] != '/' || !path[1] || strlen(path) >= MAX_PATH)
        return false;

    const char *component = path + 1;
    for (const char *cursor = component; ; cursor++)
    {
        unsigned char character = *cursor;
        if (character && (character < 32 || character == 127 || character == '\\'))
            return false;
        if (character == '/' || !character)
        {
            size_t length = cursor - component;
            if (!length || (length == 1 && component[0] == '.') ||
                (length == 2 && component[0] == '.' && component[1] == '.'))
                return false;
            if (!character)
                return true;
            component = cursor + 1;
        }
    }
}

static bool text_bookmark_valid(const struct text_bookmark *bookmark)
{
    return bookmark && bookmark->offset >= 0 && bookmark->size >= 0 &&
           bookmark->offset <= bookmark->size &&
           bookmark->unit >= 0 && bookmark->unit <= 4;
}

static bool text_bookmark_number(const char **cursor, uint64_t maximum,
                                 uint64_t *number)
{
    const char *token = *cursor;
    uint64_t value = 0;
    if (*token < '0' || *token > '9')
        return false;
    do
    {
        unsigned int digit = *token++ - '0';
        if (value > maximum / 10 ||
            (value == maximum / 10 && digit > maximum % 10))
            return false;
        value = value * 10 + digit;
    }
    while (*token >= '0' && *token <= '9');
    if (*token++ != ';')
        return false;
    *cursor = token;
    *number = value;
    return true;
}

static bool parse_text_bookmark(const char *line, struct text_bookmark *bookmark,
                                const char **path)
{
    if (!line || strncmp(line, "T1;", 3))
        return false;
    const char *cursor = line + 3;
    uint64_t offset, size, unit, signature;
    uint64_t maximum = (UINT64_C(1) << (sizeof(off_t) * CHAR_BIT - 1)) - 1;
    if (!text_bookmark_number(&cursor, maximum, &offset) ||
        !text_bookmark_number(&cursor, maximum, &size) ||
        !text_bookmark_number(&cursor, 4, &unit) ||
        !text_bookmark_number(&cursor, UINT32_MAX, &signature) ||
        !text_bookmark_path_valid(cursor))
        return false;
    struct text_bookmark parsed = { offset, size, signature, unit };
    if (!text_bookmark_valid(&parsed))
        return false;
    if (bookmark)
        *bookmark = parsed;
    if (path)
        *path = cursor;
    return true;
}
#endif

static int read_bookmark_line(int file)
{
    size_t length = 0;
    while (length < sizeof(global_temp_buffer) - 1)
    {
        unsigned char chunk[32];
        size_t available = MIN(sizeof(chunk), sizeof(global_temp_buffer) - 1 - length);
        ssize_t count = read(file, chunk, available);
        if (count < 0)
            return -1;
        if (!count)
        {
            global_temp_buffer[length] = '\0';
            return length;
        }
        unsigned char *newline = memchr(chunk, '\n', count);
        size_t used = newline ? (size_t)(newline - chunk + 1) : (size_t)count;
        if (used < (size_t)count && lseek(file, (off_t)used - count, SEEK_CUR) < 0)
            return -1;
        memcpy(global_temp_buffer + length, chunk, used);
        length += used;
        global_temp_buffer[length] = '\0';
        if (newline)
            return length;
    }
    return -1;
}

static int bookmark_line_length(int length)
{
    if (length && global_temp_buffer[length - 1] == '\n')
        length--;
    if (length && global_temp_buffer[length - 1] == '\r')
        length--;
    return length;
}

static int read_bookmark(int file)
{
    int length = read_bookmark_line(file);
    if (length > 0)
    {
        int end = bookmark_line_length(length);
        if (memchr(global_temp_buffer, '\0', end))
            end = 0;
        global_temp_buffer[end] = '\0';
    }
    return length;
}

static inline void get_hash(const char *key, uint32_t *hash, int len)
{
    *hash = crc_32(key, len, *hash); /* this is probably sufficient */
}

static const char* skip_tokens(const char* s, int ntokens)
{
    for (int i = 0; i < ntokens; i++)
    {
        while (*s && *s != ';')
        {
            s++;
        }

        if (*s)
        {
            s++;
        }
    }
    return s;
}

static int int_token(const char **s)
{
    int ret = atoi(*s);
    *s = skip_tokens(*s, 1);
    return ret;
}

static long long_token(const char **s)
{
    /* Should be atol, but we don't have it. */
    return int_token(s);
}

/*-------------------------------------------------------------------------*/
/* Get the name of the playlist and the name of the track from a bookmark. */
/* Returns true iff both were extracted.                                   */
/*-------------------------------------------------------------------------*/
static bool bookmark_get_playlist_and_track_hash(const char *bookmark,
                                            uint32_t *pl_hash,
                                            uint32_t *track_hash)
{
    *pl_hash = 0;
    *track_hash = 0;
    int  pl_len;
    const char *pl_start, *pl_end, *track;

    logf("%s", __func__);

    pl_start = strchr(bookmark,'/');
    if (!(pl_start))
        return false;

    pl_end = skip_tokens(pl_start, 1) - 1;
    pl_len = pl_end - pl_start;

    track = pl_end + 1;
    get_hash(pl_start, pl_hash, pl_len);

    if (global_settings.usemrb == BOOKMARK_ONE_PER_TRACK)
    {
        get_hash(track, track_hash, strlen(track));
    }


    return true;
}

/* ----------------------------------------------------------------------- */
/* This function takes a bookmark and parses it.  This function also       */
/* validates the bookmark.  Valid filenamebuf indicates whether            */
/* the filename tokens are to be extracted.                                */
/* Returns true on successful bookmark parse.                              */
/* ----------------------------------------------------------------------- */
static bool parse_bookmark(char *filenamebuf,
                           size_t filenamebufsz,
                           const char *bookmark,
                           struct resume_info *resume_info,
                           const bool strip_dir)
{
    if (!bookmark || bookmark[0] == 'T')
        return false;
    const char* s = bookmark;
    const char* end;

#define GET_INT_TOKEN(var)   var = int_token(&s)
#define GET_LONG_TOKEN(var)  var = long_token(&s)
#define GET_BOOL_TOKEN(var) var = (int_token(&s) != 0)

    /* if new format bookmark, extract the optional content flags,
       otherwise treat as an original format bookmark */
    int opt_flags = 0;
    int opt_pitch = 0;
    int opt_speed = 0;
    int old_format = ((strchr(s, '>') == s) ? 0 : 1);
    if (old_format == 0) /* this is a new format bookmark */
    {
        s++;
        GET_INT_TOKEN(opt_flags);
        opt_pitch = (opt_flags & BM_PITCH) ? 1:0;
        opt_speed = (opt_flags & BM_SPEED) ? 1:0;
    }

    /* extract all original bookmark tokens */
    if (resume_info)
    {
        GET_INT_TOKEN(resume_info->resume_index);
        GET_LONG_TOKEN(resume_info->resume_offset);
        GET_INT_TOKEN(resume_info->resume_seed);

        s = skip_tokens(s, old_format); /* skip deprecated token */

        GET_LONG_TOKEN(resume_info->resume_elapsed);
        GET_INT_TOKEN(resume_info->repeat_mode);
        GET_BOOL_TOKEN(resume_info->shuffle);

        /* extract all optional bookmark tokens */
        if (opt_pitch != 0)
            GET_INT_TOKEN(resume_info->pitch);
        if (opt_speed != 0)
            GET_INT_TOKEN(resume_info->speed);
    }
    else /* no resume info we just want the file name strings */
    {
        #define DEFAULT_BM_TOKENS 6
        int skipct = DEFAULT_BM_TOKENS + old_format + opt_pitch + opt_speed;
        s = skip_tokens(s, skipct);
        #undef DEFAULT_BM_TOKENS
    }

    if (*s == 0)
    {
        return false;
    }

    end = strchr(s, ';');

    /* extract file names */
    if(filenamebuf)
    {
        size_t len = (end == NULL) ? strlen(s) : (size_t) (end - s);
        len = MIN(TEMP_BUF_SIZE - 1, len);
        strmemccpy(global_temp_buffer, s, len + 1);

        if (end != NULL)
        {
            end++;
            if (strip_dir)
            {
                s = strrchr(end, '/');
                if (s)
                {
                    end = s;
                    end++;
                }
            }
            strmemccpy(filenamebuf, end, filenamebufsz);
        }
     }

    return true;
}

/* ------------------------------------------------------------------------- */
/* This function appends a temporary suffix to a filename and also opens    */
/* the resulting file based on oflags, filename will be in buf on return     */
/* Returns file descriptor                                                   */
/* --------------------------------------------------------------------------*/
static int open_temp_bookmark(char *buf,
                              size_t bufsz,
                              int oflags,
                              const char* filename)
{
    if (!filename || !*filename)
        return -1;
    for (unsigned int candidate = 0; candidate < MAX_BOOKMARK_TEMP_FILES; candidate++)
    {
        int length = candidate ?
            snprintf(buf, bufsz, "%s.t%02x", filename, candidate) :
            snprintf(buf, bufsz, "%s.tmp", filename);
        if (length < 0 || (size_t)length >= bufsz)
            return -1;
        int fd = open(buf, oflags, 0666);
#ifdef LOGF_ENABLE
        if (oflags & O_PATH)
            logf("tempfile path %s", buf);
        else
            logf("opening tempfile %s", buf);
#endif
        if (fd >= 0 || !(oflags & O_EXCL) || errno != EEXIST)
            return fd;
    }
    return -1;
}

/* ----------------------------------------------------------------------- */
/* This function adds a bookmark to a file.                                */
/* Returns true on successful bookmark add.                                */
/* ------------------------------------------------------------------------*/
static bool rewrite_bookmarks(const char *bookmark_file_name,
                               const char *bookmark, bool most_recent,
                               int delete_id)
{
    char fnamebuf[MAX_PATH];
    char new_bookmark[TEMP_BUF_SIZE];
#ifdef HAVE_ESPEAK
    const char *new_path = NULL;
    struct text_bookmark new_text;
    bool text = false;
#endif
    bool compare_audio = false;
    uint32_t pl_hash = 0, track_hash = 0;
    int bookmark_count = bookmark ? 1 : 0;
    int line_index = 0;
    if (bookmark)
    {
        if (strlen(bookmark) >= sizeof(new_bookmark) - 1)
            return false;
        strcpy(new_bookmark, bookmark);
#ifdef HAVE_ESPEAK
        text = parse_text_bookmark(new_bookmark, &new_text, &new_path);
#endif
        compare_audio = new_bookmark[0] != 'T' && most_recent &&
            (global_settings.usemrb == BOOKMARK_ONE_PER_PLAYLIST ||
             global_settings.usemrb == BOOKMARK_ONE_PER_TRACK) &&
            bookmark_get_playlist_and_track_hash(new_bookmark, &pl_hash, &track_hash);
    }
    else if (delete_id < 0)
        return false;

    int bookmark_file = open(bookmark_file_name, O_RDONLY);
    if (bookmark_file < 0 && (!bookmark || errno != ENOENT))
        return false;
    int temp_bookmark_file = open_temp_bookmark(fnamebuf, sizeof(fnamebuf),
                                               O_WRONLY | O_CREAT | O_EXCL,
                                               bookmark_file_name);
    if (temp_bookmark_file < 0)
    {
        if (bookmark_file >= 0)
            close(bookmark_file);
        return false;
    }
    bool success = !bookmark ||
        (write(temp_bookmark_file, new_bookmark, strlen(new_bookmark)) ==
         (ssize_t)strlen(new_bookmark) && write(temp_bookmark_file, "\n", 1) == 1);
    int length = 0;
    while (success && bookmark_file >= 0 &&
           (length = read_bookmark_line(bookmark_file)) > 0)
    {
        bool equal = !bookmark && line_index == delete_id;
        int end = bookmark_line_length(length);
        char saved = global_temp_buffer[end];
        global_temp_buffer[end] = '\0';
        bool valid = false;
        if (bookmark && !memchr(global_temp_buffer, '\0', end))
        {
            bool old_is_text = global_temp_buffer[0] == 'T';
            valid = parse_bookmark(NULL, 0, global_temp_buffer, NULL, false);
#ifdef HAVE_ESPEAK
            struct text_bookmark old_text;
            const char *old_path;
            bool valid_text = parse_text_bookmark(global_temp_buffer, &old_text, &old_path);
            valid |= valid_text;
            if (text && valid_text)
            {
                equal = !strcmp(new_path, old_path) &&
                    (new_text.offset == old_text.offset ||
                     (most_recent && (global_settings.usemrb == BOOKMARK_ONE_PER_PLAYLIST ||
                                      global_settings.usemrb == BOOKMARK_ONE_PER_TRACK)));
            }
            else
#endif
            if (compare_audio && !old_is_text && valid)
            {
                uint32_t old_pl_hash, old_track_hash;
                if (bookmark_get_playlist_and_track_hash(global_temp_buffer,
                                                         &old_pl_hash, &old_track_hash))
                {
                    equal = pl_hash == old_pl_hash &&
                        (global_settings.usemrb != BOOKMARK_ONE_PER_TRACK ||
                         track_hash == old_track_hash);
                }
            }
            if (most_recent && valid && bookmark_count >= MAX_BOOKMARKS)
                equal = true;
        }
        global_temp_buffer[end] = saved;
        if (!equal)
        {
            success = write(temp_bookmark_file, global_temp_buffer, length) == length;
            if (valid)
                bookmark_count++;
        }
        if (line_index == INT_MAX)
            success = false;
        else
            line_index++;
    }
    success = success && length >= 0 && (bookmark || delete_id < line_index);
    if (bookmark_file >= 0 && close(bookmark_file) < 0)
        success = false;
    if (close(temp_bookmark_file) < 0)
        success = false;
    if (success)
        success = rename(fnamebuf, bookmark_file_name) == 0;
    if (!success)
        remove(fnamebuf);
    return success;
}

static bool add_bookmark(const char *bookmark_file_name, const char *bookmark,
                         bool most_recent)
{
    return bookmark && rewrite_bookmarks(bookmark_file_name, bookmark, most_recent, -1);
}

/* ----------------------------------------------------------------------- */
/* This function is used by multiple functions and is used to generate a   */
/* bookmark named based off of the input.                                  */
/* Changing this function could result in how the bookmarks are stored.    */
/* it would be here that the centralized/decentralized bookmark code       */
/* could be placed.                                                        */
/* Returns true if the file name is generated, false if it was too long    */
/* ----------------------------------------------------------------------- */
static bool generate_bookmark_file_name(char *filenamebuf,
                                        size_t filenamebufsz,
                                        const char *bmarknamein,
                                        size_t bmarknamelen)
{
    /* if this is a root dir MP3, rename the bookmark file root_dir.bmark */
    /* otherwise, name it based on the bmarknamein variable */
    if (!strncmp("/", bmarknamein, bmarknamelen))
        strmemccpy(filenamebuf, "/root_dir.bmark", filenamebufsz);
    else
    {
        size_t buflen, len;
        /* strmemccpy considers the NULL so bmarknamelen is one off */
        buflen = MIN(filenamebufsz -1 , bmarknamelen);
        if (buflen >= filenamebufsz)
            return false;

        strmemccpy(filenamebuf, bmarknamein, buflen + 1);

        len = strlen(filenamebuf);

#ifdef HAVE_MULTIVOLUME
        /* The "root" of an extra volume need special handling too. */
        const char *filename;
        path_strip_volume(filenamebuf, &filename, true);
        bool volume_root = *filename == '\0';
#endif
        if(filenamebuf[len-1] == '/') {
            filenamebuf[len-1] = '\0';
        }

        const char *name = ".bmark";
#ifdef HAVE_MULTIVOLUME
        if (volume_root)
            name = "/volume_dir.bmark";
#endif
        len = strlcat(filenamebuf, name, filenamebufsz);

        if(len >= filenamebufsz)
            return false;
    }
    logf ("generated name '%s' from '%.*s'",
          filenamebuf, (int)bmarknamelen, bmarknamein);
    return true;
}

/* GCC 7 and up complain about the snprintf in create_bookmark() when
   compiled with -D_FORTIFY_SOURCE or -Wformat-truncation
   This is a false positive, so disable it here only */
/* SHOULD NO LONGER BE NEEDED --Bilgus 11-2022 */
#if 0 /* __GNUC__ >= 7 */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wformat-truncation"
#endif
/* ----------------------------------------------------------------------- */
/* This function takes the system resume data and formats it into a valid  */
/* bookmark.                                                               */
/* playlist name and  name len are passed back through the name/namelen    */
/* Return is not NULL on successful bookmark format.                      */
/* ----------------------------------------------------------------------- */
static char* create_bookmark(char **name,
                             size_t *namelen,
                             struct resume_info *resume_info)
{
    const char *file;
    char *buf = global_temp_buffer;
    size_t bufsz = sizeof(global_temp_buffer);

    if(!resume_info->id3)
        return NULL;

    size_t bmarksz= snprintf(buf, bufsz,
                             /* new optional bookmark token descriptors should
                                be inserted just after ';"' in this line... */
#if defined(HAVE_PITCHCONTROL)
                             ">%d;%d;%ld;%d;%ld;%d;%d;%ld;%ld;",
#else
                             ">%d;%d;%ld;%d;%ld;%d;%d;",
#endif
                             /* ... their flags should go here ... */
#if defined(HAVE_PITCHCONTROL)
                             BM_PITCH | BM_SPEED,
#else
                             0,
#endif
                             resume_info->resume_index,
                             resume_info->id3->offset,
                             resume_info->resume_seed,
                             resume_info->id3->elapsed,
                             resume_info->repeat_mode,
                             resume_info->shuffle
                             /* ...and their values should go here */
#if defined(HAVE_PITCHCONTROL)
                             , (long)resume_info->pitch,
                             (long)resume_info->speed
#endif
                    ); /*sprintf*/
/* mandatory tokens */
    if (bmarksz >= bufsz) /* include NULL*/
        return NULL;
    buf += bmarksz;
    bufsz -= bmarksz;

    /* create the bookmark */
    playlist_get_name(NULL, buf, bufsz);
    bmarksz = strlen(buf);

    if (bmarksz == 0 || (bmarksz + 1) >= bufsz) /* include the separator & NULL*/
        return NULL;

    *name = buf;     /* return the playlist name through the *pointer */
    *namelen = bmarksz; /* return the name length through the pointer */

    /* Get the currently playing file minus the path */
    /* This is used when displaying the available bookmarks */
    file = strrchr(resume_info->id3->path,'/');
    if(NULL == file)
        return NULL;

    if (buf[bmarksz - 1] != '/')
        file = resume_info->id3->path;
    else file++;

    buf += bmarksz;
    bufsz -= (bmarksz + 1);
    buf[0] = ';';
    buf[1] = '\0';

    strlcat(buf, file, bufsz);

    logf("%s [%s]", __func__, global_temp_buffer);
    /* checking to see if the bookmark is valid */
    if (parse_bookmark(NULL, 0, global_temp_buffer, NULL, false))
        return global_temp_buffer;
    else
        return NULL;
}
#if 0/* __GNUC__ >= 7*/
#pragma GCC diagnostic pop /* -Wformat-truncation */
#endif

/* ----------------------------------------------------------------------- */
/* This function gets some basic resume information for the current song   */
/* from rockbox,  */
/* ----------------------------------------------------------------------- */
static void get_track_resume_info(struct resume_info *resume_info)
{
    if (global_settings.playlist_shuffle)
        playlist_get_resume_info(&(resume_info->resume_index));
    else
        resume_info->resume_index = playlist_get_display_index() - 1;

    resume_info->resume_seed = playlist_get_seed(NULL);
    resume_info->id3 = audio_current_track();
    resume_info->repeat_mode = global_settings.repeat_mode;
    resume_info->shuffle = global_settings.playlist_shuffle;
#if defined(HAVE_PITCHCONTROL)
    resume_info->pitch = sound_get_pitch();
    resume_info->speed = dsp_get_timestretch();
#endif
}

/* ----------------------------------------------------------------------- */
/* This function checks for bookmark ignore and unignore files to allow    */
/* directories to be ignored or included in bookmarks */
/* ----------------------------------------------------------------------- */
static bool bookmark_has_ignore(struct resume_info *resume_info)
{
    if (!resume_info->id3)
        return false;

    char *buf = global_temp_buffer;
    size_t bufsz = sizeof(global_temp_buffer);

    strmemccpy(buf, resume_info->id3->path, bufsz);

    char *slash;
    while ((slash = strrchr(buf, '/')))
    {
        size_t rem = bufsz - (slash - buf);
        if (strmemccpy(slash, BOOKMARK_UNIGNORE, rem) != NULL && file_exists(buf))
        {
            /* unignore exists we want bookmarks */
            logf("unignore bookmark found %s\n", buf);
            return false;
        }
        if (strmemccpy(slash, BOOKMARK_IGNORE, rem) != NULL && file_exists(buf))
        {
            /* ignore exists we do not want bookmarks */
            logf("ignore bookmark found %s\n", buf);
            return true;
        }
        *slash = '\0';
    }
    return false;
}

/* ----------------------------------------------------------------------- */
/* This function takes the current current resume information and writes   */
/* that to the beginning of the bookmark file.                             */
/* This file will contain N number of bookmarks in the following format:   */
/* resume_index*resume_offset*resume_seed*resume_first_index*              */
/* resume_file*milliseconds*MP3 Title*                                     */
/* Returns true on successful bookmark write.                              */
/* Returns false if any part of the bookmarking process fails.  It is      */
/* possible that a bookmark is successfully added to the most recent       */
/* bookmark list but fails to be added to the bookmark file or vice versa. */
/* ------------------------------------------------------------------------*/
static bool write_bookmark(unsigned int flags)
{
    logf("%s flags: %d", __func__, flags);
    char bm_filename[MAX_PATH];
    bool ret=true;

    bool create_bookmark_file = flags & BMARK_CREATE_FILE;
    bool check_ignore = flags & BMARK_CHECK_IGNORE;
    bool ask_user = flags & BMARK_ASK_USER;
    bool usemrb = global_settings.usemrb;

    char *name = NULL;
    size_t namelen = 0;
    char* bm;
    struct resume_info resume_info;

    if (bookmark_is_bookmarkable_state())
    {
        get_track_resume_info(&resume_info);

        if (check_ignore
            && (create_bookmark_file || ask_user || usemrb))
        {
            if (bookmark_has_ignore(&resume_info))
                return false;
        }

        if (ask_user)
        {
            if (yesno_pop(ID2P(LANG_AUTO_BOOKMARK_QUERY)))
            {
                if (global_settings.autocreatebookmark != BOOKMARK_RECENT_ONLY_ASK)
                    create_bookmark_file = true;
            }
            else
                return false;
        }

        /* writing the most recent bookmark */
        if (usemrb)
        {
            /* since we use the same buffer bookmark needs created each time */
            bm = create_bookmark(&name, &namelen, &resume_info);
            ret = add_bookmark(RECENT_BOOKMARK_FILE, bm, true);
        }

        /* writing the directory bookmark */
        if (create_bookmark_file)
        {
            bm = create_bookmark(&name, &namelen, &resume_info);
            if (generate_bookmark_file_name(bm_filename,
                                            sizeof(bm_filename), name, namelen))
            {
                ret &= add_bookmark(bm_filename, bm, false);
            }
            else
            {
                ret = false; /* generating bookmark file failed */
            }
        }
    }
    else
        ret = false;

    splash(HZ, ret ? ID2P(LANG_BOOKMARK_CREATE_SUCCESS)
           : ID2P(LANG_BOOKMARK_CREATE_FAILURE));

    return ret;
}

static int get_bookmark_count(const char* bookmark_file_name)
{
    int read_count = 0;
    int length;
    int file = open(bookmark_file_name, O_RDONLY);

    if(file < 0)
        return -1;

    while ((length = read_bookmark(file)) > 0)
    {
        if (read_count >= INT_MAX / 2 - 1)
        {
            length = -1;
            break;
        }
        read_count++;
    }

    if (close(file) < 0 || length < 0)
        return -1;
    return read_count;
}

static int buffer_bookmarks(struct bookmark_list* bookmarks, int first_line)
{
    char* dest = ((char*) bookmarks) + bookmarks->buffer_size - 1;
    int read_count = 0;
    int file = open(bookmarks->filename, O_RDONLY);

    if (file < 0)
    {
        return -1;
    }

    if (first_line != 0 && bookmarks->total_count >= 0 &&
        (size_t)bookmarks->total_count <
            (bookmarks->buffer_size - sizeof(*bookmarks)) / sizeof(char*) &&
        (size_t)ffilesize(file) < bookmarks->buffer_size
            - sizeof(*bookmarks) - sizeof(char*) * bookmarks->total_count)
    {
        /* Entire file fits in buffer */
        first_line = 0;
    }

    bookmarks->start = first_line;
    bookmarks->count = 0;
    bookmarks->reload = false;

    int length;
    while ((length = read_bookmark(file)) > 0)
    {
        if (read_count++ >= first_line)
        {
            size_t required = strlen(global_temp_buffer) + 1;
            char *pointers_end = ((char*)bookmarks) + sizeof(*bookmarks)
                + sizeof(char*) * (bookmarks->count + 1);
            if (dest < pointers_end || (size_t)(dest - pointers_end) < required)
            {
                break;
            }

            dest -= required;
            strcpy(dest, global_temp_buffer);
            bookmarks->items[bookmarks->count] = dest;
            bookmarks->count++;
        }
    }

    if (close(file) < 0 || length < 0)
    {
        bookmarks->count = 0;
        bookmarks->reload = true;
        return -1;
    }
    return bookmarks->start + bookmarks->count;
}

static char *bookmark_at_index(struct bookmark_list *bookmarks, int index)
{
    if (index < 0 || index >= bookmarks->total_count)
        return NULL;
    if (bookmarks->reload || index < bookmarks->start ||
        index >= bookmarks->start + bookmarks->count)
    {
        if (buffer_bookmarks(bookmarks, index) <= index)
            return NULL;
    }
    return bookmarks->items[index - bookmarks->start];
}

#ifdef HAVE_ESPEAK
static int text_bookmark_percent(const struct text_bookmark *bookmark)
{
    if (!bookmark->size)
        return 0;
    uint64_t size = bookmark->size;
    uint64_t whole = size / 100;
    uint64_t remainder = size % 100;
    int percent = 0;
    while (percent < 100 && (uint64_t)bookmark->offset >=
           whole * (percent + 1) + (remainder * (percent + 1) + 99) / 100)
        percent++;
    return percent;
}
#endif

static const char* get_bookmark_info(int list_index,
                                     void* data,
                                     char *buffer,
                                     size_t buffer_len)
{
    char fnamebuf[MAX_PATH];
    struct resume_info resume_info;
    struct bookmark_list* bookmarks = (struct bookmark_list*) data;
    int     index = list_index / 2;

    if (bookmarks->show_dont_resume)
    {
        if (index == 0)
        {
            return list_index % 2 == 0
                ? (char*) str(LANG_BOOKMARK_DONT_RESUME) : " ";
        }

        index--;
    }

    if (bookmarks->reload || (index >= bookmarks->start + bookmarks->count)
        || (index < bookmarks->start))
    {
        int read_index = index;

        /* Using count as a guide on how far to move could possibly fail
         * sometimes. Use byte count if that is a problem?
         */

        if (read_index != 0)
        {
            /* Move count * 3 / 4 items in the direction the user is moving,
             * but don't go too close to the end.
             */
            int offset = bookmarks->count;
            int max = bookmarks->total_count - (bookmarks->count / 2);

            if (read_index < bookmarks->start)
            {
                offset *= 3;
            }

            read_index = index - offset / 4;

            if (read_index > max)
            {
                read_index = max;
            }

            if (read_index < 0)
            {
                read_index = 0;
            }
        }

        if (buffer_bookmarks(bookmarks, read_index) <= index)
        {
            return "";
        }
    }

    const char *entry = bookmark_at_index(bookmarks, index);
#ifdef HAVE_ESPEAK
    struct text_bookmark text;
    const char *path;
    if (parse_text_bookmark(entry, &text, &path))
    {
        if (list_index % 2 == 0)
        {
            const char *name = bookmarks->show_playlist_name ? path : strrchr(path, '/') + 1;
            snprintf(buffer, buffer_len, "%s: %s", str(LANG_TTS_TEXT_BOOKMARK), name);
        }
        else
            snprintf(buffer, buffer_len, "%s: %d%% (%llu/%llu)", str(LANG_TTS_POSITION),
                     text_bookmark_percent(&text), (unsigned long long)text.offset,
                     (unsigned long long)text.size);
        return buffer;
    }
#endif
    if (!parse_bookmark(fnamebuf, sizeof(fnamebuf), entry, &resume_info, true))
    {
        return list_index % 2 == 0 ? (char*) str(LANG_BOOKMARK_INVALID) : " ";
    }

    if (list_index % 2 == 0)
    {
        char *name;
        char *format;
        int len = strlen(global_temp_buffer);

        if (bookmarks->show_playlist_name && len > 0)
        {
            name = global_temp_buffer;
            len--;

            if (name[len] != '/')
            {
                strrsplt(name, '.');
            }
            else if (len > 1)
            {
                name[len] = '\0';
            }

            if (len > 1)
            {
                name = strrsplt(name, '/');
            }

            format = "%s : %s";
        }
        else
        {
            name = fnamebuf;
            format = "%s";
        }

        strrsplt(fnamebuf, '.');
        snprintf(buffer, buffer_len, format, name, fnamebuf);
        return buffer;
    }
    else
    {
        char time_buf[32];

        format_time(time_buf, sizeof(time_buf), resume_info.resume_elapsed);
        snprintf(buffer, buffer_len, "%s, %d%s", time_buf,
                 resume_info.resume_index + 1,
                 resume_info.shuffle ? (char*) str(LANG_BOOKMARK_SHUFFLE) : "");
        return buffer;
    }
}

/* ----------------------------------------------------------------------- */
/* This function parses a bookmark, says the voice UI part of it.          */
/* ------------------------------------------------------------------------*/
static void say_bookmark(const char* bookmark,
                         int bookmark_id,
                         bool show_playlist_name)
{
    char fnamebuf[MAX_PATH];
    struct resume_info resume_info;
#ifdef HAVE_ESPEAK
    struct text_bookmark text;
    const char *path;
    if (parse_text_bookmark(bookmark, &text, &path))
    {
        talk_value(bookmark_id + 1, UNIT_INT, false);
        talk_id(LANG_TTS_TEXT_BOOKMARK, true);
        talk_file_or_spell(NULL, path, TALK_IDARRAY(VOICE_FILE), true);
        talk_id(LANG_TTS_POSITION, true);
        talk_value(text_bookmark_percent(&text), UNIT_PERCENT, true);
        if ((uint64_t)text.offset <= LONG_MAX)
            talk_value(text.offset, UNIT_INT, true);
        else
        {
            char position[32];
            snprintf(position, sizeof(position), "%llu", (unsigned long long)text.offset);
            talk_spell(position, true);
        }
        return;
    }
#endif
    if (!parse_bookmark(fnamebuf, sizeof(fnamebuf), bookmark, &resume_info, false))
    {
        talk_id(LANG_BOOKMARK_INVALID, false);
        return;
    }

    talk_number(bookmark_id + 1, false);

    bool is_dir = (global_temp_buffer[0]
              && global_temp_buffer[strlen(global_temp_buffer)-1] == '/');

    /* HWCODEC cannot enqueue voice file entries and .talk thumbnails
       together, because there is no guarantee that the same mp3
       parameters are used. */
    if(show_playlist_name)
    {   /* It's useful to know which playlist this is */
        if(is_dir)
            talk_dir_or_spell(global_temp_buffer,
                              TALK_IDARRAY(VOICE_DIR), true);
        else talk_file_or_spell(NULL, global_temp_buffer,
                                TALK_IDARRAY(LANG_PLAYLIST), true);
    }

    if(resume_info.shuffle)
        talk_id(LANG_SHUFFLE, true);

    talk_id(VOICE_BOOKMARK_SELECT_INDEX_TEXT, true);
    talk_number(resume_info.resume_index + 1, true);
    talk_id(LANG_TIME, true);
    talk_value(resume_info.resume_elapsed / 1000, UNIT_TIME, true);

    /* Track filename */
    if(!is_dir)
        global_temp_buffer[0] = 0;
    talk_file_or_spell(global_temp_buffer, fnamebuf,
                       TALK_IDARRAY(VOICE_FILE), true);
}

static int bookmark_list_voice_cb(int list_index, void* data)
{
    struct bookmark_list* bookmarks = (struct bookmark_list*) data;
    int index = list_index / 2;

    if (bookmarks->show_dont_resume)
    {
        if (index == 0)
            return talk_id(LANG_BOOKMARK_DONT_RESUME, false);
        index--;
    }
    say_bookmark(bookmark_at_index(bookmarks, index), index,
                 bookmarks->show_playlist_name);
    return 0;
}

/* ----------------------------------------------------------------------- */
/* This function takes a location in a bookmark file and deletes that      */
/* bookmark.                                                               */
/* Returns true on successful bookmark deletion.                           */
/* ------------------------------------------------------------------------*/
static bool delete_bookmark(const char* bookmark_file_name, int bookmark_id)
{
    return rewrite_bookmarks(bookmark_file_name, NULL, false, bookmark_id);
}

/* ----------------------------------------------------------------------- */
/* Displays bookmarks in a file, so user can select one to play.           */
/*                                                                         */
/* Returns                                                                 */
/* BOOKMARK_SUCCESS              A bookmark or 'Don't Resume' was selected */
/* BOOKMARK_FAIL                 No selection was made                     */
/* BOOKMARK_USB_CONNECTED        USB connection forced exit of menu        */
/*                                                                         */
/* *selected_bookmark will point to bookmark if selected, or will be NULL  */
/* ----------------------------------------------------------------------- */
static int select_bookmark(const char* bookmark_file_name,
                           bool show_dont_resume,
                           char** selected_bookmark)
{
    struct bookmark_list* bookmarks;
    struct gui_synclist list;
    int item = show_dont_resume ? 1 : 0;
    int action;
    size_t size;
    bool exit = false;
    bool refresh = true;
    int ret = BOOKMARK_FAIL;
    *selected_bookmark = NULL;

    bookmarks = plugin_get_buffer(&size);
    if (!bookmarks || size < sizeof(*bookmarks) + sizeof(char*) + TEMP_BUF_SIZE)
        return BOOKMARK_FAIL;
    bookmarks->buffer_size = size;
    bookmarks->show_dont_resume = show_dont_resume;
    bookmarks->filename = bookmark_file_name;
    bookmarks->start = 0;
    bookmarks->count = 0;
    bookmarks->reload = true;
    bookmarks->show_playlist_name
        = (strcmp(bookmark_file_name, RECENT_BOOKMARK_FILE) == 0);

    gui_synclist_init(&list, &get_bookmark_info,
                      (void*) bookmarks, false, 2, NULL);

    if(talk_menus_enabled(&global_settings))
        gui_synclist_set_voice_callback(&list, bookmark_list_voice_cb);

    while (!exit)
    {
        if (refresh)
        {
            refresh = false;
            int count = get_bookmark_count(bookmark_file_name);
            bookmarks->total_count = count;

            if (bookmarks->total_count < 1)
            {
                splash(HZ, ID2P(LANG_BOOKMARK_LOAD_EMPTY));
                break;
            }

            if (bookmarks->show_dont_resume)
            {
                count++;
            }

            gui_synclist_set_nb_items(&list, count * 2);

            if (item >= count)
            {
                /* Selected item has been deleted */
                item = count - 1;
            }
            gui_synclist_select_item(&list, item * 2);

            if (buffer_bookmarks(bookmarks, bookmarks->start) < 0)
                break;
            gui_synclist_set_title(&list, str(LANG_BOOKMARK_SELECT_BOOKMARK),
                                   Icon_Bookmark);
            gui_synclist_draw(&list);
            cond_talk_ids_fq(VOICE_EXT_BMARK);
            gui_synclist_speak_item(&list);
        }

        list_do_action(CONTEXT_BOOKMARKSCREEN, HZ / 2, &list, &action);
        item = gui_synclist_get_sel_pos(&list) / 2;

        int bookmark_index = item - (bookmarks->show_dont_resume ? 1 : 0);

        if (action == ACTION_STD_CONTEXT)
        {
            if (bookmark_index < 0)
                continue;
            gui_synclist_scroll_stop(&list);
            MENUITEM_STRINGLIST(menu_items, ID2P(LANG_BOOKMARK_CONTEXT_MENU), NULL,
                                ID2P(LANG_BOOKMARK_CONTEXT_RESUME),
                                ID2P(LANG_DELETE));
            static const int menu_actions[] = {ACTION_STD_OK,
                                               ACTION_BMS_DELETE};
            int selection = do_menu(&menu_items, NULL, NULL, false);
            refresh = true;
            if (selection == MENU_ATTACHED_USB)
            {
                ret = BOOKMARK_USB_CONNECTED;
                break;
            }
            action = ACTION_NONE;
            if (selection >= 0 && selection <
                (int) (sizeof(menu_actions) / sizeof(menu_actions[0])))
                action = menu_actions[selection];
        }
        switch (action)
        {
        case ACTION_STD_OK:
            ret = BOOKMARK_SUCCESS;
            if (bookmark_index >= 0)
            {
                *selected_bookmark = bookmark_at_index(bookmarks, bookmark_index);
                if (!*selected_bookmark)
                    ret = BOOKMARK_FAIL;
            }
            /* fall through */
        case ACTION_TREE_WPS:
        case ACTION_STD_CANCEL:
            exit = true;
            break;
        case ACTION_BMS_DELETE:
            if (bookmark_index < 0)
                break;
            int confirmation = confirm_delete_yesno("", str(LANG_BOOKMARK_CONTEXT_MENU));
            if (confirmation == YESNO_USB)
            {
                ret = BOOKMARK_USB_CONNECTED;
                exit = true;
                break;
            }
            if (confirmation == YESNO_YES)
            {
                if (!delete_bookmark(bookmark_file_name, bookmark_index))
                    splash(HZ, ID2P(LANG_FAILED));
                bookmarks->reload = true;
            }
            refresh = true;
            break;
        default:
            if (default_event_handler(action) == SYS_USB_CONNECTED)
            {
                ret = BOOKMARK_USB_CONNECTED;
                exit = true;
            }
            break;
        }
    }
    gui_synclist_scroll_stop(&list);
    talk_shutup();
    return ret;
}

/* ----------------------------------------------------------------------- */
/* This function parses a bookmark and then plays it.                      */
/* Returns true on successful bookmark play.                               */
/* ------------------------------------------------------------------------*/
static bool play_bookmark(const char* bookmark)
{
    char fnamebuf[MAX_PATH];
    struct resume_info resume_info;
#ifdef HAVE_ESPEAK
    struct text_bookmark text;
    const char *path;
    if (parse_text_bookmark(bookmark, &text, &path))
    {
        strcpy(fnamebuf, path);
        tts_read_bookmark(fnamebuf, &text);
        return true;
    }
#endif
    if (!bookmark || bookmark[0] == 'T')
        return false;
#if defined(HAVE_PITCHCONTROL)
    /* preset pitch and speed to 100% in case bookmark doesn't have info */
    resume_info.pitch = sound_get_pitch();
    resume_info.speed = dsp_get_timestretch();
#endif

    if (parse_bookmark(fnamebuf, sizeof(fnamebuf), bookmark, &resume_info, true))
    {
        global_settings.repeat_mode = resume_info.repeat_mode;
        iap_on_repeat_state(global_settings.repeat_mode);
        global_settings.playlist_shuffle = resume_info.shuffle;
        iap_on_shuffle_state(global_settings.playlist_shuffle);
#if defined(HAVE_PITCHCONTROL)
        sound_set_pitch(resume_info.pitch);
        dsp_set_timestretch(resume_info.speed);
#endif
        if (!warn_on_pl_erase())
            return false;
        bool success = bookmark_play(global_temp_buffer, resume_info.resume_index,
                             resume_info.resume_elapsed, resume_info.resume_offset,
                             resume_info.resume_seed, fnamebuf);
        if (success) /* verify we loaded the correct track */
        {
            const struct mp3entry *id3 = audio_current_track();
            if (id3)
            {
                const char *path;
                const char *track;
                path_basename(id3->path, &path);
                path_basename(fnamebuf, &track);
                if (strcmp(path, track) == 0)
                {
                    return true;
                }
            }
            audio_stop();
        }
    }

    return false;
}

/*-------------------------------------------------------------------------*/
/* PUBLIC INTERFACE -------------------------------------------------------*/
/*-------------------------------------------------------------------------*/

#ifdef HAVE_ESPEAK
static bool text_bookmark_file_name(char *buffer, size_t size, const char *path)
{
    if (!text_bookmark_path_valid(path))
        return false;
    int length = snprintf(buffer, size, "%s.bmark", path);
    return length >= 0 && (size_t)length + sizeof(".tmp") <= size;
}

enum text_bookmark_save_result bookmark_text_create_ex(
    const char *path, const struct text_bookmark *bookmark)
{
    char filename[MAX_PATH];
    if (!text_bookmark_valid(bookmark) ||
        !text_bookmark_file_name(filename, sizeof(filename), path))
        return TEXT_BOOKMARK_FAILED;
    int length = snprintf(global_temp_buffer, sizeof(global_temp_buffer),
                          "T1;%llu;%llu;%d;%lu;%s", (unsigned long long)bookmark->offset,
                          (unsigned long long)bookmark->size, bookmark->unit,
                          (unsigned long)bookmark->signature, path);
    if (length < 0 || (size_t)length >= sizeof(global_temp_buffer) - 1)
        return TEXT_BOOKMARK_FAILED;
    char entry[TEMP_BUF_SIZE];
    strcpy(entry, global_temp_buffer);
    if (!add_bookmark(filename, entry, false))
        return TEXT_BOOKMARK_FAILED;
    if (global_settings.usemrb && !add_bookmark(RECENT_BOOKMARK_FILE, entry, true))
        return TEXT_BOOKMARK_SAVED_LOCAL_ONLY;
    return TEXT_BOOKMARK_SAVED;
}

bool bookmark_text_create(const char *path, const struct text_bookmark *bookmark)
{
    return bookmark_text_create_ex(path, bookmark) == TEXT_BOOKMARK_SAVED;
}

int bookmark_text_select(const char *path, struct text_bookmark *bookmark)
{
    char filename[MAX_PATH];
    char *entry;
    const char *selected_path;
    struct text_bookmark selected;
    if (!bookmark || !text_bookmark_file_name(filename, sizeof(filename), path))
        return BOOKMARK_FAIL;
    push_current_activity(ACTIVITY_BOOKMARKSLIST);
    int result = select_bookmark(filename, false, &entry);
    if (result == BOOKMARK_SUCCESS)
    {
        if (!parse_text_bookmark(entry, &selected, &selected_path) ||
            strcmp(path, selected_path))
            result = BOOKMARK_FAIL;
        else
            *bookmark = selected;
    }
    pop_current_activity();
    return result;
}
#endif

/* ----------------------------------------------------------------------- */
/* This is an interface function from the context menu.                    */
/* Returns true on successful bookmark creation.                           */
/* ----------------------------------------------------------------------- */
bool bookmark_create_menu(void)
{
    if (!bookmark_is_bookmarkable_state())
        save_playlist_screen(NULL);

    return write_bookmark(BMARK_CREATE_FILE);
}
/* ----------------------------------------------------------------------- */
/* This function acts as the load interface from the context menu.         */
/* This function determines the bookmark file name and then loads that file*/
/* for the user.  The user can then select or delete previous bookmarks.   */
/* This function returns BOOKMARK_SUCCESS on the selection of a track to   */
/* resume, BOOKMARK_FAIL if the menu is exited without a selection and     */
/* BOOKMARK_USB_CONNECTED if the menu is forced to exit due to a USB       */
/* connection.                                                             */
/* ----------------------------------------------------------------------- */
int bookmark_load_menu(void)
{
    char bm_filename[MAX_PATH];
    char* bookmark;
    int ret = BOOKMARK_FAIL;

    /* To prevent root dir ("/") bookmarks  from being displayed
       when 'List Bookmarks' hotkey or button is pressed, check:
    */
    if (playlist_dynamic_only())
    {
        splash(HZ, ID2P(LANG_BOOKMARK_LOAD_EMPTY));
        return ret;
    }

    push_current_activity(ACTIVITY_BOOKMARKSLIST);

    char* name = playlist_get_name(NULL, global_temp_buffer,
                                       sizeof(global_temp_buffer));
    if (generate_bookmark_file_name(bm_filename, sizeof(bm_filename), name, -1))
    {
        ret = select_bookmark(bm_filename, false, &bookmark);
        if (bookmark != NULL)
        {
            ret = play_bookmark(bookmark) ? BOOKMARK_SUCCESS : BOOKMARK_FAIL;
        }
    }

    pop_current_activity();
    return ret;
}

/* ----------------------------------------------------------------------- */
/* Gives the user a list of the Most Recent Bookmarks.  This is an         */
/* interface function                                                      */
/* Returns true on the successful selection of a recent bookmark.          */
/* ----------------------------------------------------------------------- */
bool bookmark_mrb_load()
{
    char* bookmark;
    bool ret = false;

    push_current_activity(ACTIVITY_BOOKMARKSLIST);
    select_bookmark(RECENT_BOOKMARK_FILE, false, &bookmark);
    if (bookmark != NULL)
    {
#ifdef HAVE_ESPEAK
        if (parse_text_bookmark(bookmark, NULL, NULL))
            play_bookmark(bookmark);
        else
#endif
        ret = play_bookmark(bookmark);
    }

    pop_current_activity();
    return ret;
}

/* ----------------------------------------------------------------------- */
/* This function handles an autobookmark creation.  This is an interface   */
/* function.                                                               */
/* Returns true on successful bookmark creation.                           */
/* ----------------------------------------------------------------------- */
bool bookmark_autobookmark(bool prompt_ok)
{
    logf("%s", __func__);
    bool update;

    if (!bookmark_is_bookmarkable_state())
        return false;

    audio_pause();    /* first pause playback */
    update = (global_settings.autoupdatebookmark && bookmark_exists());

    if (update)
        return write_bookmark(BMARK_CREATE_FILE | BMARK_CHECK_IGNORE);

    switch (global_settings.autocreatebookmark)
    {
        case BOOKMARK_YES:
            return write_bookmark(BMARK_CREATE_FILE | BMARK_CHECK_IGNORE);

        case BOOKMARK_NO:
            return false;

        case BOOKMARK_RECENT_ONLY_YES:
            return write_bookmark(BMARK_CHECK_IGNORE);
    }

    if(prompt_ok)
        return write_bookmark(BMARK_ASK_USER | BMARK_CHECK_IGNORE);

    return false;
}

/* ----------------------------------------------------------------------- */
/* This function will determine if an autoload is necessary.  This is an   */
/* interface function.                                                     */
/* Returns                                                                 */
/* BOOKMARK_DO_RESUME    on bookmark load or bookmark selection.           */
/* BOOKMARK_DONT_RESUME  if we're not going to resume                      */
/* BOOKMARK_CANCEL       if user canceled                                  */
/* ------------------------------------------------------------------------*/
int bookmark_autoload(const char* file)
{
    logf("%s", __func__);
    char bm_filename[MAX_PATH];
    char* bookmark;

    if(global_settings.autoloadbookmark == BOOKMARK_NO)
        return BOOKMARK_DONT_RESUME;

    /*Checking to see if a bookmark file exists.*/
    if(!generate_bookmark_file_name(bm_filename, sizeof(bm_filename), file, -1))
    {
        return BOOKMARK_DONT_RESUME;
    }

    if(!file_exists(bm_filename))
        return BOOKMARK_DONT_RESUME;

    if(global_settings.autoloadbookmark == BOOKMARK_YES)
    {
        return (bookmark_load(bm_filename, true)
                ? BOOKMARK_DO_RESUME : BOOKMARK_DONT_RESUME);
    }
    else
    {
        int ret = select_bookmark(bm_filename, true, &bookmark);

        if (bookmark != NULL)
        {
            if (!play_bookmark(bookmark))
                return BOOKMARK_CANCEL;
            return BOOKMARK_DO_RESUME;
        }

        return (ret != BOOKMARK_SUCCESS) ? BOOKMARK_CANCEL : BOOKMARK_DONT_RESUME;
    }
}

/* ----------------------------------------------------------------------- */
/* This function loads the bookmark information into the resume memory.    */
/* This is an interface function.                                          */
/* Returns true on successful bookmark load.                               */
/* ------------------------------------------------------------------------*/
bool bookmark_load(const char* file, bool autoload)
{
    logf("%s", __func__);
    int  fd;
    char* bookmark = NULL;

    if(autoload)
    {
        fd = open(file, O_RDONLY);
        if(fd >= 0)
        {
            if(read_bookmark(fd) > 0)
                bookmark=global_temp_buffer;
            if (close(fd) < 0)
                bookmark = NULL;
        }
    }
    else
    {
        /* This is not an auto-load, so list the bookmarks */
        select_bookmark(file, false, &bookmark);
    }

    if (bookmark != NULL)
    {
        if (!play_bookmark(bookmark))
        {
            /* Selected bookmark not found. */
            if (!autoload)
            {
                splash(HZ*2, ID2P(LANG_NOTHING_TO_RESUME));
            }

            return false;
        }
    }

    return true;
}

/* ----------------------------------------------------------------------- */
/* Returns true if a bookmark file exists for the current playlist.        */
/* This is an interface function.                                          */
/* ----------------------------------------------------------------------- */
bool bookmark_exists(void)
{
    char bm_filename[MAX_PATH];
    bool exist=false;

    char* name = playlist_get_name(NULL, global_temp_buffer,
                                   sizeof(global_temp_buffer));
    if (!playlist_dynamic_only() &&
        generate_bookmark_file_name(bm_filename, sizeof(bm_filename), name, -1))
    {
        exist = file_exists(bm_filename);
    }
    return exist;
}

/* ----------------------------------------------------------------------- */
/* Checks the current state of the system and returns true if it is in a   */
/* bookmarkable state.                                                     */
/* This is an interface funtion.                                           */
/* ----------------------------------------------------------------------- */
bool bookmark_is_bookmarkable_state(void)
{
    int resume_index = 0;

    if (!(audio_status() && audio_current_track()) ||
        /* no track playing */
       (playlist_get_resume_info(&resume_index) == -1) ||
        /* invalid queue info */
       (playlist_modified(NULL)) ||
        /* can't bookmark playlists modified by user */
       (playlist_dynamic_only()))
        /* can't bookmark playlists without associated folder or playlist file */
    {
        return false;
    }

    return true;
}
