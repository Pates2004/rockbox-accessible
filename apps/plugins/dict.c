/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2005 Tomas Salfischberger
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

#include "plugin.h"



#define MIN_DESC_BUF_SIZE 0x400 /* arbitrary minimum size for description */

/* Some lenghts */
#define WORDLEN 32 /* has to be the same in rdf2binary.c */

/* Struct packing */
#ifdef __GNUC__
#define STRUCT_PACKED __attribute__((packed))
#else
#define STRUCT_PACKED
#pragma pack (push, 2)
#endif

/* The word struct :) */
struct stWord
{
    char word[WORDLEN];
    uint32_t offset;
} STRUCT_PACKED;

/* for endian problems */
#ifdef ROCKBOX_BIG_ENDIAN
#define reverse(x) x
#else
static uint32_t reverse(uint32_t value)
{
    return ((value & 0xff) << 24) | ((value & 0xff00) << 8) |
           ((value & 0xff0000) >> 8) | ((value & 0xff000000) >> 24);
}
#endif


/* data files */
#define DICT_INDEX PLUGIN_APPS_DIR "/dict.index"
#define DICT_DESC PLUGIN_APPS_DIR "/dict.desc"

#define DEFINITION_LINE_BYTES 180

static const char *definition_next_line(const char *text)
{
    const char *end = text;
    while (*end && *end != '\n' && end - text < DEFINITION_LINE_BYTES)
        end++;
    if (*end && *end != '\n')
    {
        while (end > text && ((unsigned char)*end & 0xc0) == 0x80)
            end--;
        const char *space = end;
        while (space > text && !isspace((unsigned char)*space))
            space--;
        if (space > text)
            end = space;
    }
    if (end == text && *end && !isspace((unsigned char)*end))
        end++;
    while (isspace((unsigned char)*end))
        end++;
    return end;
}

static const char *definition_get_name(int selected_item, void *data,
                                       char *buffer, size_t buffer_len)
{
    if (selected_item < 0 || buffer_len == 0)
        return NULL;
    const char *text = data;
    while (isspace((unsigned char)*text))
        text++;
    while (selected_item-- > 0 && *text)
        text = definition_next_line(text);
    if (!*text)
        return NULL;
    const char *end = definition_next_line(text);
    while (end > text && isspace((unsigned char)end[-1]))
        end--;
    size_t length = MIN((size_t)(end - text), buffer_len - 1);
    while (length > 0 && ((unsigned char)text[length] & 0xc0) == 0x80)
        length--;
    rb->memcpy(buffer, text, length);
    buffer[length] = '\0';
    return buffer;
}

static enum plugin_status show_definition(const char *word, char *description)
{
    int line_count = 0;
    const char *text = description;
    while (isspace((unsigned char)*text))
        text++;
    while (*text)
    {
        line_count++;
        text = definition_next_line(text);
    }
    struct simplelist_info list;
    rb->simplelist_info_init(&list, (char *)word, line_count, description);
    list.get_name = definition_get_name;
    return rb->simplelist_show_list(&list) ? PLUGIN_USB_CONNECTED : PLUGIN_OK;
}

static bool read_index_word(int descriptor, int index, struct stWord *word)
{
    if (index < 0 || rb->lseek(descriptor,
                             (off_t)sizeof(*word) * index, SEEK_SET) < 0)
        return false;
    return rb->read(descriptor, word, sizeof(*word)) == (ssize_t)sizeof(*word) &&
           rb->memchr(word->word, '\0', sizeof(word->word)) != NULL;
}

/* the main plugin function */
enum plugin_status plugin_start(const void* parameter)
{
    char searchword[WORDLEN]; /* word to search for */
    char *description; /* pointer to description buffer */
    struct stWord word; /* the struct to read into */
    int fIndex, fData; /* files */
    int filesize, high, low, probe;
    char *buffer;
    size_t buffer_size;

    /* plugin stuff */
    (void)parameter;

    /* allocate buffer. */
    buffer = rb->plugin_get_buffer(&buffer_size);
    if (buffer == NULL || buffer_size < MIN_DESC_BUF_SIZE)
    {
        DEBUGF("Err: Failed to allocate buffer.\n");
        rb->splash(HZ*2, "Failed to allocate buffer.");
        return PLUGIN_ERROR;
    }

    description = buffer;

    /* "clear" input buffer */
    searchword[0] = '\0';

    /* get the word to search */
    if (rb->kbd_input(searchword, sizeof(searchword), NULL) < 0)
        return PLUGIN_OK; /* input cancelled */

    fIndex = rb->open(DICT_INDEX, O_RDONLY); /* index file */
    if (fIndex < 0)
    {
        DEBUGF("Err: Failed to open index file.\n");
        rb->splash(HZ*2, "Failed to open index.");
        return PLUGIN_ERROR;
    }

    filesize = rb->ffilesize(fIndex); /* get filesize */
    if (filesize < 0 || filesize % sizeof(struct stWord) != 0)
    {
        rb->close(fIndex);
        rb->splash(HZ*2, ID2P(LANG_FILE_ERROR));
        return PLUGIN_ERROR;
    }

    DEBUGF("Filesize: %d bytes = %d words \n", filesize,
           (filesize / (int)sizeof(struct stWord)));

    /* for the searching algorithm */
    high = filesize / sizeof( struct stWord );
    low = -1;

    while (high - low > 1)
    {
        probe = (high + low) / 2;

        /* Jump to word pointed by probe, and read it. */
        if (!read_index_word(fIndex, probe, &word))
        {
            rb->close(fIndex);
            rb->splash(HZ*2, ID2P(LANG_FILE_ERROR));
            return PLUGIN_ERROR;
        }

        /* jump according to the found word. */
        if (rb->strcasecmp(searchword, word.word) < 0)
        {
            high = probe;
        }
        else
        {
            low = probe;
        }
    }

    /* read in the word */
    bool found = read_index_word(fIndex, low, &word);
    rb->close(fIndex);

    /* Check if we found something */
    if (!found || rb->strcasecmp(searchword, word.word) != 0)
    {
        DEBUGF("Not found.\n");
        rb->splash(HZ*2, "Not found.");
        return PLUGIN_OK;
    }

    DEBUGF("Found %s at offset %lu\n", word.word, (unsigned long)reverse(word.offset));

    /* now open the description file */
    fData = rb->open(DICT_DESC, O_RDONLY);
    if (fData < 0)
    {
        DEBUGF("Err: Failed to open description file.\n");
        rb->splash(HZ*2, "Failed to open descriptions.");
        return PLUGIN_ERROR;
    }

    /* seek to the right offset */
    if (rb->lseek(fData, (off_t)reverse(word.offset), SEEK_SET) < 0)
    {
        rb->close(fData);
        rb->splash(HZ*2, ID2P(LANG_FILE_ERROR));
        return PLUGIN_ERROR;
    }

    /* Read in the description */
    description[0] = '\0';
    if (rb->read_line(fData, description, buffer_size) < 0)
    {
        rb->close(fData);
        rb->splash(HZ*2, ID2P(LANG_FILE_ERROR));
        return PLUGIN_ERROR;
    }

    /* And print it to debug. */
    DEBUGF("Description: %s\n", description);

    rb->close(fData);

    /* display description. */
    return show_definition(searchword, description);
}
