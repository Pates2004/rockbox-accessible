#include "config.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "system.h"
#include "kernel.h"
#include "rbunicode.h"
#include "keyboard.h"
#include "tts_reader_settings.h"
#include "yesno.h"
#include "file.h"
#include "action.h"
#include "button.h"
#include "bookmark.h"
#include "debug.h"
#include "lang.h"
#include "list.h"
#include "menu.h"
#include "misc.h"
#include "pcm_mixer.h"
#include "powermgmt.h"
#include "root_menu.h"
#include "screen_access.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"
#include "tts.h"
#include "utf8proc.h"
#include "viewport.h"
#ifdef HAVE_TOUCHSCREEN
#include "accessibility.h"
#endif

#define READER_CHUNK_SIZE 768
#define READER_SCAN_BUDGET 1024
#define READER_READ_ERROR (-1)
#define READER_INVALID_TEXT (-2)
#define READER_CANCELLED (-3)

#define READER_QUERY_BYTES 128
#define READER_RESULT_BYTES 1024

struct text_reader;
struct reader_job
{
    struct text_reader *owner;
    char accepted_query[READER_QUERY_BYTES + 1];
    char edit[READER_QUERY_BYTES + 1];
    union
    {
        struct
        {
            utf8proc_int32_t pattern[READER_QUERY_BYTES];
            uint8_t prefix[READER_QUERY_BYTES];
            off_t starts[READER_QUERY_BYTES];
        } matcher;
        struct
        {
            char chunk[READER_CHUNK_SIZE + 1];
            char result[READER_RESULT_BYTES];
        } staging;
    } scratch;
    struct tts_reader_preferences preferences;
    off_t target;
    off_t next;
    int length;
    size_t result_length;
    unsigned int pattern_length;
    bool new_query;
    bool ready;
};

/* Owned by the main UI reader for its entire lifetime, including nested menus. */
static struct reader_job reader_job;
typedef char reader_job_must_fit[(sizeof(struct reader_job) <= 2304) ? 1 : -1];

enum reader_state
{
    READER_READING,
    READER_PAUSED,
    READER_FINISHED,
    READER_FAILED
};

enum reader_unit
{
    READER_CHARACTER,
    READER_WORD,
    READER_LINE,
    READER_PARAGRAPH,
    READER_PAGE
};

struct text_reader
{
    struct viewport viewports[NB_SCREENS];
#ifdef HAVE_TOUCHSCREEN
    int touch_line_height;
    int touch_lines;
    int touch_row;
#endif
    struct reader_job *job;
    const char *path;
    const char *name;
    int descriptor;
    off_t size;
    off_t first;
    off_t cursor;
    off_t start;
    off_t next;
    off_t cache_start;
    int cache_length;
    int length;
    int scan_work;
    int pending_action;
    enum reader_state state;
    bool initialized;
    bool scanning;
    bool loaded;
    bool submitted;
    bool feedback;
    bool active;
    bool dirty;
    unsigned char cache[READER_CHUNK_SIZE];
    char text[READER_CHUNK_SIZE + 1];
};

#if !defined(HIBY_R1)
static const struct button_mapping *reader_context(int context)
{
    static const struct button_mapping buttons[] = {
#if CONFIG_KEYPAD == SANSA_CLIP_PAD
        { ACTION_NONE, BUTTON_SELECT, BUTTON_NONE },
        { ACTION_STD_OK, BUTTON_SELECT | BUTTON_REL, BUTTON_SELECT },
        { ACTION_STD_CONTEXT, BUTTON_SELECT | BUTTON_REPEAT, BUTTON_SELECT },
#elif defined(BUTTON_PLAY)
        { ACTION_NONE, BUTTON_PLAY, BUTTON_NONE },
        { ACTION_STD_OK, BUTTON_PLAY | BUTTON_REL, BUTTON_PLAY },
        { ACTION_STD_CONTEXT, BUTTON_PLAY | BUTTON_REPEAT, BUTTON_PLAY },
#endif
#if defined(BUTTON_VOL_UP) && defined(BUTTON_VOL_DOWN)
        { ACTION_SETTINGS_INC, BUTTON_VOL_UP, BUTTON_NONE },
        { ACTION_SETTINGS_INCREPEAT, BUTTON_VOL_UP | BUTTON_REPEAT, BUTTON_NONE },
        { ACTION_SETTINGS_DEC, BUTTON_VOL_DOWN, BUTTON_NONE },
        { ACTION_SETTINGS_DECREPEAT, BUTTON_VOL_DOWN | BUTTON_REPEAT, BUTTON_NONE },
#endif
#ifdef HAVE_TOUCHSCREEN
        { ACTION_STD_OK, BUTTON_CENTER | BUTTON_REL, BUTTON_CENTER },
#endif
        LAST_ITEM_IN_LIST__NEXTLIST(CONTEXT_SETTINGS)
    };
    static const struct button_mapping remote[] = {
        LAST_ITEM_IN_LIST__NEXTLIST(CONTEXT_SETTINGS | CONTEXT_REMOTE)
    };
    return context & CONTEXT_REMOTE ? remote : buttons;
}
#endif

static int reader_action(int timeout)
{
#if defined(HIBY_R1)
    return get_action(CONTEXT_CUSTOM | CONTEXT_CUSTOM2 | CONTEXT_STD | ALLOW_SOFTLOCK,
                      timeout);
#else
    return get_custom_action(CONTEXT_PLUGIN | CONTEXT_SETTINGS, timeout,
                             reader_context);
#endif
}

static bool reader_space(utf8proc_int32_t codepoint)
{
    return codepoint == ' ' || (codepoint >= '\t' && codepoint <= '\r') ||
        codepoint == 0x85 || codepoint == 0xa0 || codepoint == 0x1680 ||
        (codepoint >= 0x2000 && codepoint <= 0x200a) ||
        codepoint == 0x2028 || codepoint == 0x2029 || codepoint == 0x202f ||
        codepoint == 0x205f || codepoint == 0x3000;
}

static bool reader_newline(utf8proc_int32_t codepoint)
{
    return codepoint == '\r' || codepoint == '\n' || codepoint == 0x85 ||
        codepoint == 0x2028 || codepoint == 0x2029;
}

static bool reader_valid(utf8proc_int32_t codepoint)
{
    return !((codepoint < 0x20 && !reader_space(codepoint)) ||
        (codepoint >= 0x7f && codepoint <= 0x9f && codepoint != 0x85) ||
        (codepoint >= 0xfdd0 && codepoint <= 0xfdef) ||
        (codepoint & 0xfffe) == 0xfffe);
}

static int reader_width(unsigned char leading)
{
    return leading < 0x80 ? 1 : leading >= 0xc2 && leading <= 0xdf ? 2 :
        leading >= 0xe0 && leading <= 0xef ? 3 :
        leading >= 0xf0 && leading <= 0xf4 ? 4 : 0;
}

static int reader_read_chunk(int descriptor, off_t start, off_t size,
                             char *text, off_t *next)
{
    if (start < 0 || start > size)
        return READER_READ_ERROR;
    *next = start;
    text[0] = '\0';
    if (start == size)
        return 0;
    if (lseek(descriptor, start, SEEK_SET) != start)
        return READER_READ_ERROR;

    size_t requested = size - start > READER_CHUNK_SIZE ?
        READER_CHUNK_SIZE : (size_t)(size - start);
    size_t length = 0;
    while (length < requested)
    {
        ssize_t received = read(descriptor, text + length, requested - length);
        if (received <= 0)
            return READER_READ_ERROR;
        length += received;
    }

    size_t first = 0;
    if (start == 0 && length >= 3 && !memcmp(text, "\xef\xbb\xbf", 3))
        first = 3;
    bool at_end = size - start == (off_t)length;
    size_t position = first;
    size_t boundary = first;
    while (position < length)
    {
        utf8proc_int32_t codepoint;
        utf8proc_ssize_t width = utf8proc_iterate(
            (const utf8proc_uint8_t *)text + position,
            length - position, &codepoint);
        if (width <= 0)
        {
            size_t expected = reader_width((unsigned char)text[position]);
            if (!at_end && expected > length - position)
                break;
            return READER_INVALID_TEXT;
        }
        if (!reader_valid(codepoint))
            return READER_INVALID_TEXT;
        position += width;
        if (reader_space(codepoint))
            boundary = position;
    }
    if (!at_end && boundary > first)
        position = boundary;
    *next = start + position;
    length = position - first;
    memmove(text, text + first, length);
    text[length] = '\0';
    return length;
}

static int reader_checkpoint(struct text_reader *reader)
{
    if (!reader->scanning || ++reader->scan_work < READER_SCAN_BUDGET)
        return 0;
    reader->scan_work = 0;
    yield();
    reset_poweroff_timer();
    int action = reader_action(TIMEOUT_NOBLOCK);
    if (action == ACTION_REDRAW)
        reader->dirty = true;
    else if (action != ACTION_NONE && action != ACTION_UNKNOWN)
    {
        reader->pending_action = action;
        return READER_CANCELLED;
    }
    return 0;
}

static int reader_byte(struct text_reader *reader, off_t position)
{
    if (position < 0 || position >= reader->size)
        return READER_READ_ERROR;
    if (!reader->cache_length || position < reader->cache_start ||
        position - reader->cache_start >= reader->cache_length)
    {
        reader->cache_length = 0;
        reader->cache_start = position - position % READER_CHUNK_SIZE;
        if (lseek(reader->descriptor, reader->cache_start, SEEK_SET) !=
            reader->cache_start)
            return READER_READ_ERROR;
        size_t requested = reader->size - reader->cache_start > READER_CHUNK_SIZE ?
            READER_CHUNK_SIZE : (size_t)(reader->size - reader->cache_start);
        size_t length = 0;
        while (length < requested)
        {
            ssize_t received = read(reader->descriptor, reader->cache + length,
                                    requested - length);
            if (received <= 0)
                return READER_READ_ERROR;
            length += received;
        }
        reader->cache_length = length;
    }
    return reader->cache[position - reader->cache_start];
}

static int reader_decode(struct text_reader *reader, off_t position,
                         utf8proc_int32_t *codepoint)
{
    int status = reader_checkpoint(reader);
    if (status < 0)
        return status;
    if (position == reader->size)
        return 0;
    int leading = reader_byte(reader, position);
    if (leading < 0)
        return leading;
    int expected = reader_width(leading);
    if (!expected || expected > reader->size - position)
        return READER_INVALID_TEXT;
    utf8proc_uint8_t bytes[4];
    bytes[0] = leading;
    for (int index = 1; index < expected; ++index)
    {
        int value = reader_byte(reader, position + index);
        if (value < 0)
            return value;
        bytes[index] = value;
    }
    int width = utf8proc_iterate(bytes, expected, codepoint);
    return width > 0 && reader_valid(*codepoint) ? width : READER_INVALID_TEXT;
}

static int reader_previous(struct text_reader *reader, off_t position,
                           off_t *previous, utf8proc_int32_t *codepoint)
{
    if (position <= reader->first)
    {
        *previous = reader->first;
        return 0;
    }
    off_t start = position;
    int value;
    do
    {
        value = reader_byte(reader, --start);
        if (value < 0)
            return value;
    }
    while ((value & 0xc0) == 0x80 && start > reader->first && position - start < 4);
    int width = reader_decode(reader, start, codepoint);
    if (width < 0)
        return width;
    if (start + width != position)
        return READER_INVALID_TEXT;
    *previous = start;
    return width;
}

static int reader_prepare(struct text_reader *reader)
{
    if (reader->initialized)
        return 0;
    utf8proc_int32_t codepoint;
    int width = reader_decode(reader, 0, &codepoint);
    if (width < 0)
        return width;
    reader->first = width && codepoint == 0xfeff ? width : 0;
    reader->cursor = reader->first;
    reader->initialized = true;
    return 0;
}

static int reader_line_after(struct text_reader *reader, off_t position,
                             off_t *after, bool *blank)
{
    *blank = true;
    while (position < reader->size)
    {
        utf8proc_int32_t codepoint;
        int width = reader_decode(reader, position, &codepoint);
        if (width < 0)
            return width;
        position += width;
        if (reader_newline(codepoint))
        {
            if (codepoint == '\r' && position < reader->size)
            {
                width = reader_decode(reader, position, &codepoint);
                if (width < 0)
                    return width;
                if (codepoint == '\n')
                    position += width;
            }
            break;
        }
        if (!reader_space(codepoint))
            *blank = false;
    }
    *after = position;
    return 0;
}

static int reader_line_before(struct text_reader *reader, off_t cursor,
                              off_t *before)
{
    off_t position = cursor;
    while (position > reader->first)
    {
        off_t end = position;
        utf8proc_int32_t codepoint;
        int status = reader_previous(reader, position, &position, &codepoint);
        if (status < 0)
            return status;
        if (!reader_newline(codepoint))
            continue;
        if (codepoint == '\r' && end < reader->size)
        {
            status = reader_decode(reader, end, &codepoint);
            if (status < 0)
                return status;
            if (codepoint == '\n')
                end += status;
        }
        if (end < cursor)
        {
            *before = end;
            return 0;
        }
    }
    *before = reader->first;
    return 0;
}

static int reader_line_current(struct text_reader *reader, off_t cursor,
                               off_t *start)
{
    *start = cursor;
    if (cursor == reader->first)
        return 0;
    off_t previous;
    utf8proc_int32_t codepoint;
    int status = reader_previous(reader, cursor, &previous, &codepoint);
    if (status < 0)
        return status;
    if (reader_newline(codepoint))
    {
        if (codepoint != '\r' || cursor == reader->size)
            return 0;
        status = reader_decode(reader, cursor, &codepoint);
        if (status < 0)
            return status;
        if (codepoint != '\n')
            return 0;
    }
    return reader_line_before(reader, cursor, start);
}

static int reader_word(struct text_reader *reader, bool forward, off_t *target)
{
    off_t position = reader->cursor;
    bool crossed = false;
    while (forward ? position < reader->size : position > reader->first)
    {
        off_t previous = position;
        utf8proc_int32_t codepoint;
        int width = forward ? reader_decode(reader, position, &codepoint) :
            reader_previous(reader, position, &previous, &codepoint);
        if (width < 0)
            return width;
        bool space = reader_space(codepoint);
        if (crossed && (forward ? !space : space))
            break;
        if (forward ? space : !space)
            crossed = true;
        position = forward ? position + width : previous;
    }
    *target = position;
    return 0;
}

static int reader_paragraph(struct text_reader *reader, bool forward,
                            off_t *target)
{
    off_t position;
    int status = reader_line_current(reader, reader->cursor, &position);
    if (status < 0)
        return status;
    bool crossed = false;
    off_t candidate = reader->first;
    for (;;)
    {
        off_t after;
        bool blank;
        status = reader_line_after(reader, position, &after, &blank);
        if (status < 0)
            return status;
        if (forward)
        {
            if (!blank && crossed && position > reader->cursor)
            {
                *target = position;
                return 0;
            }
            crossed = blank;
            if (after == reader->size)
            {
                *target = reader->size;
                return 0;
            }
            position = after;
        }
        else
        {
            if (blank && crossed)
                break;
            if (!blank && position < reader->cursor)
            {
                crossed = true;
                candidate = position;
            }
            if (position == reader->first)
                break;
            status = reader_line_before(reader, position, &position);
            if (status < 0)
                return status;
        }
    }
    *target = candidate;
    return 0;
}

static int reader_unit(void)
{
    int unit = global_settings.tts_reader_unit;
    return unit >= READER_CHARACTER && unit <= READER_PAGE ? unit : READER_WORD;
}

static int reader_unit_label(void)
{
    static const int labels[] = { LANG_TTS_UNIT_CHARACTER, LANG_TTS_UNIT_WORD,
        LANG_TTS_UNIT_LINE, LANG_TTS_UNIT_PARAGRAPH, LANG_TTS_UNIT_PAGE };
    return labels[reader_unit()];
}

static int reader_page(struct text_reader *reader, bool forward, off_t *target)
{
    int lines = global_settings.tts_reader_page_lines;
    if (lines < 1 || lines > 100)
        lines = 20;
    off_t position = reader->first;
    off_t previous = position;
    int count = 0;
    while (position < reader->size)
    {
        bool blank;
        int status = reader_line_after(reader, position, &position, &blank);
        if (status < 0)
            return status;
        if (++count != lines && position != reader->size)
            continue;
        count = 0;
        if (forward && position > reader->cursor)
        {
            *target = position;
            return 0;
        }
        if (!forward && position >= reader->cursor)
            break;
        previous = position;
    }
    *target = forward ? reader->size : previous;
    return 0;
}

static int reader_seek_unit(struct text_reader *reader, bool forward,
                            off_t *target)
{
    *target = reader->cursor;
    switch (reader_unit())
    {
        case READER_CHARACTER:
        {
            utf8proc_int32_t codepoint;
            int width = forward ? reader_decode(reader, *target, &codepoint) :
                reader_previous(reader, *target, target, &codepoint);
            if (width <= 0)
                return width;
            if (forward)
            {
                *target += width;
                if (codepoint == '\r' && *target < reader->size)
                {
                    width = reader_decode(reader, *target, &codepoint);
                    if (width < 0)
                        return width;
                    if (codepoint == '\n')
                        *target += width;
                }
            }
            else if (codepoint == '\n' && *target > reader->first)
            {
                off_t previous;
                width = reader_previous(reader, *target, &previous, &codepoint);
                if (width < 0)
                    return width;
                if (width && codepoint == '\r')
                    *target = previous;
            }
            return 0;
        }
        case READER_WORD:
            return reader_word(reader, forward, target);
        case READER_LINE:
        {
            bool blank;
            return forward ? reader_line_after(reader, *target, target, &blank) :
                reader_line_before(reader, *target, target);
        }
        case READER_PARAGRAPH:
            return reader_paragraph(reader, forward, target);
        default:
            return reader_page(reader, forward, target);
    }
}

/* Both products are bounded by size, including signed 64-bit file offsets. */
static uint64_t reader_percent_offset(uint64_t size, unsigned int percent,
                                      bool round_up)
{
    return (size / 100) * percent +
        ((size % 100) * percent + (round_up ? 99 : 0)) / 100;
}

static unsigned int reader_percent(const struct text_reader *reader)
{
    if (reader->size <= 0)
        return reader->state == READER_FINISHED ? 100 : 0;
    if (reader->cursor <= 0)
        return 0;
    if (reader->cursor >= reader->size)
        return 100;
    unsigned int low = 0, high = 100;
    while (low < high)
    {
        unsigned int middle = low + (high - low + 1) / 2;
        if ((uint64_t)reader->cursor >=
            reader_percent_offset((uint64_t)reader->size, middle, true))
            low = middle;
        else
            high = middle - 1;
    }
    return low;
}

static void reader_report_state(const struct text_reader *reader)
{
    static const char * const states[] = { "reading", "paused", "finished", "failed" };
    (void)states;
    (void)reader;
    DEBUGF("TTS reader state: %s offset=%llu\n", states[reader->state],
           (unsigned long long)reader->cursor);
}

static const char *reader_label(const struct text_reader *reader)
{
    switch (reader->state)
    {
        case READER_READING:
            return (const char *)str(LANG_TTS_READING);
        case READER_PAUSED:
            return (const char *)str(LANG_TTS_PAUSED);
        case READER_FINISHED:
            return (const char *)str(LANG_TTS_FINISHED);
        default:
            return reader->text;
    }
}

static void reader_fail(struct text_reader *reader, int language_id)
{
    if (language_id == LANG_READ_FAILED)
        snprintf(reader->text, sizeof(reader->text),
                 (const char *)str(language_id), reader->name);
    else
        snprintf(reader->text, sizeof(reader->text), "%s", str(language_id));
    size_t length = strlen(reader->text);
    size_t position = 0;
    while (position < length)
    {
        utf8proc_int32_t codepoint;
        int width = utf8proc_iterate((const utf8proc_uint8_t *)reader->text + position,
                                     length - position, &codepoint);
        if (width <= 0)
            break;
        position += width;
    }
    reader->text[position] = '\0';
    tts_stop();
    reader->state = READER_FAILED;
    reader_report_state(reader);
    reader->submitted = false;
    reader->loaded = false;
    reader->dirty = true;
    tts_speak(reader->text, position, false);
}

static void reader_read_failed(struct text_reader *reader, int status)
{
    reader_fail(reader, status == READER_INVALID_TEXT ?
                LANG_TTS_INVALID_TEXT : LANG_READ_FAILED);
}

static bool reader_load(struct text_reader *reader)
{
    if (reader->loaded)
        return true;
    int status = reader_prepare(reader);
    if (status < 0)
    {
        reader_read_failed(reader, status);
        return false;
    }
    reader->start = reader->cursor;
    reader->length = reader_read_chunk(reader->descriptor, reader->start,
        reader->size, reader->text, &reader->next);
    if (reader->length < 0)
    {
        reader_read_failed(reader, reader->length);
        return false;
    }
    reader->loaded = true;
    return true;
}

static bool reader_audio_busy(void)
{
    return tts_is_busy() ||
        mixer_channel_status(PCM_MIXER_CHAN_VOICE) != CHANNEL_STOPPED;
}

static void reader_sync(struct text_reader *reader)
{
    if (!reader->submitted)
        return;
    size_t position = tts_read_position();
    if (position > (size_t)reader->length)
        position = reader->length;
    while (position && position < (size_t)reader->length &&
           ((unsigned char)reader->text[position] & 0xc0) == 0x80)
        --position;
    off_t cursor = reader->start + position;
    if (cursor > reader->cursor)
    {
        reader->cursor = cursor;
        reader->dirty = true;
        DEBUGF("TTS reader cursor: %llu\n", (unsigned long long)cursor);
    }
}

static void reader_finish(struct text_reader *reader)
{
    reader->cursor = reader->size;
    reader->state = READER_FINISHED;
    reader_report_state(reader);
    reader->submitted = false;
    reader->dirty = true;
    reader->feedback = true;
    const char *label = reader_label(reader);
    if (tts_speak(label, strlen(label), false) < 0)
        reader_fail(reader, LANG_TTS_ERROR);
}

static void reader_step(struct text_reader *reader)
{
    reader_sync(reader);
    if (reader->state == READER_READING && !tts_is_available())
    {
        tts_stop();
        reader->submitted = reader->loaded = reader->feedback = false;
        reader->state = READER_PAUSED;
        reader->dirty = true;
        return;
    }
    if (reader->state != READER_READING || reader_audio_busy())
        return;
    if (*tts_last_error())
    {
        reader_fail(reader, LANG_TTS_ERROR);
        return;
    }
    if (reader->submitted)
    {
        reader->submitted = false;
        if (!tts_read_interrupted())
        {
            reader->cursor = reader->next;
            DEBUGF("TTS reader cursor: %llu\n", (unsigned long long)reader->cursor);
        }
        reader->loaded = false;
        reader->dirty = true;
    }
    if (!reader_load(reader))
        return;
    if (reader->length == 0)
        reader_finish(reader);
    else if (tts_speak_tracked(reader->text, reader->length) < 0)
        reader_fail(reader, LANG_TTS_ERROR);
    else
        reader->submitted = true;
}

static void reader_toggle(struct text_reader *reader)
{
    if (reader->state == READER_FAILED)
        return;
    if (reader->state != READER_READING && !tts_is_available())
        return;
    if (reader->state == READER_READING)
    {
        tts_pause(true);
        reader_sync(reader);
        reader->state = READER_PAUSED;
    }
    else
    {
        if (reader->feedback)
        {
            tts_stop();
            reader->feedback = false;
        }
        if (reader->state == READER_FINISHED)
        {
            reader->cursor = reader->first;
            reader->loaded = false;
        }
        tts_pause(false);
        reader->state = READER_READING;
    }
    reader_report_state(reader);
    reader->dirty = true;
}

static void reader_interrupt(struct text_reader *reader)
{
    tts_pause(true);
    reader_sync(reader);
    if (reader->submitted && !tts_read_interrupted() &&
        tts_is_available() && !reader_audio_busy() &&
        !*tts_last_error())
    {
        reader->cursor = reader->next;
        DEBUGF("TTS reader cursor: %llu\n", (unsigned long long)reader->cursor);
    }
    tts_stop();
    reader->submitted = false;
    reader->feedback = false;
    reader->loaded = false;
    reader->state = READER_PAUSED;
    reader->dirty = true;
}

static int reader_signature(struct text_reader *reader, off_t cursor,
                            uint32_t *signature)
{
    uint32_t hash = 2166136261u;
    off_t starts[] = { 0, cursor > 64 ? cursor - 64 : 0,
                      reader->size > 64 ? reader->size - 64 : 0 };
    for (unsigned int region = 0; region < ARRAYLEN(starts); ++region)
    {
        int count = region == 1 ? 128 : 64;
        for (int index = 0; index < count &&
             starts[region] + index < reader->size; ++index)
        {
            int value = reader_byte(reader, starts[region] + index);
            if (value < 0)
                return value;
            hash = (hash ^ (unsigned char)value) * 16777619u;
        }
    }
    *signature = hash;
    return 0;
}

static bool reader_restore_bookmark(struct text_reader *reader,
                                    const struct text_bookmark *bookmark)
{
    if (reader_prepare(reader) < 0 || bookmark->size != reader->size ||
        bookmark->offset < reader->first || bookmark->offset > reader->size ||
        bookmark->unit < READER_CHARACTER || bookmark->unit > READER_PAGE)
        return false;
    uint32_t signature;
    if (reader_signature(reader, bookmark->offset, &signature) < 0 ||
        signature != bookmark->signature)
        return false;
    if (bookmark->offset < reader->size)
    {
        utf8proc_int32_t codepoint;
        if (reader_decode(reader, bookmark->offset, &codepoint) <= 0)
            return false;
    }
    reader->cursor = bookmark->offset;
    reader->loaded = reader->submitted = reader->feedback = false;
    reader->state = READER_PAUSED;
    reader->dirty = true;
    global_settings.tts_reader_unit = bookmark->unit;
    settings_save();
    DEBUGF("TTS reader bookmark restored: %llu\n",
           (unsigned long long)reader->cursor);
    return true;
}

static bool reader_bookmarks(struct text_reader *reader)
{
    MENUITEM_STRINGLIST(menu, ID2P(LANG_BOOKMARK_MENU), NULL,
                        ID2P(LANG_BOOKMARK_MENU_CREATE),
                        ID2P(LANG_BOOKMARK_MENU_LIST));
    int selected = 0;
    while (true)
    {
        int choice = do_menu(&menu, &selected, NULL, false);
        if (choice == MENU_ATTACHED_USB)
            return true;
        if (choice < 0)
            return false;
        struct text_bookmark bookmark;
        if (choice == 0)
        {
            bookmark.offset = reader->cursor;
            bookmark.size = reader->size;
            bookmark.unit = reader_unit();
            enum text_bookmark_save_result result = TEXT_BOOKMARK_FAILED;
            if (reader_signature(reader, bookmark.offset,
                                 &bookmark.signature) >= 0)
                result = bookmark_text_create_ex(reader->path, &bookmark);
            int message = result == TEXT_BOOKMARK_SAVED ?
                          LANG_BOOKMARK_CREATE_SUCCESS :
                          result == TEXT_BOOKMARK_SAVED_LOCAL_ONLY ?
                          LANG_TTS_BOOKMARK_LOCAL_ONLY :
                          LANG_BOOKMARK_CREATE_FAILURE;
            splash(result == TEXT_BOOKMARK_SAVED ? HZ : HZ * 2,
                   ID2P(message));
            DEBUGF("TTS reader bookmark saved: %d offset=%llu\n", result,
                   (unsigned long long)reader->cursor);
        }
        else if (choice == 1)
        {
            int result = bookmark_text_select(reader->path, &bookmark);
            if (result == BOOKMARK_USB_CONNECTED)
                return true;
            if (result == BOOKMARK_SUCCESS)
            {
                if (!reader_restore_bookmark(reader, &bookmark))
                    splash(HZ * 2, ID2P(LANG_TTS_BOOKMARK_CHANGED));
                return false;
            }
        }
    }
}

static const char *reader_property(int selected, void *data,
                                   char *buffer, size_t size)
{
    const struct text_reader *reader = data;
    switch (selected)
    {
        case 0:
            snprintf(buffer, size, "%s: %s", str(LANG_PROPERTIES_FILENAME),
                     reader->name);
            break;
        case 1:
            snprintf(buffer, size, "%s: %s", str(LANG_PROPERTIES_PATH),
                     reader->path);
            break;
        case 2:
            snprintf(buffer, size, "%s: %llu %s", str(LANG_PROPERTIES_SIZE),
                     (unsigned long long)reader->size, str(LANG_TTS_BYTES));
            break;
        case 3:
            snprintf(buffer, size, "%s: %u%%, %llu / %llu %s",
                     str(LANG_TTS_POSITION), reader_percent(reader),
                     (unsigned long long)reader->cursor,
                     (unsigned long long)reader->size, str(LANG_TTS_BYTES));
            break;
        default:
            snprintf(buffer, size, "%s: %s", str(LANG_TTS_READER_UNIT),
                     str(reader_unit_label()));
            break;
    }
    return buffer;
}

static int reader_property_speak(int selected, void *data)
{
    char buffer[MAX_PATH + 128];
    reader_property(selected, data, buffer, sizeof(buffer));
    return tts_speak(buffer, strlen(buffer), false);
}


static bool reader_job_acquire(struct text_reader *reader)
{
    if (reader_job.owner)
        return false;
    /* No yield between ownership check and assignment: main UI context only. */
    memset(&reader_job, 0, sizeof(reader_job));
    reader_job.owner = reader;
    reader->job = &reader_job;
    return true;
}

static void reader_job_release(struct text_reader *reader)
{
    if (reader->job && reader->job->owner == reader)
    {
        reader->job->owner = NULL;
        reader->job = NULL;
    }
}

static size_t reader_preview_length(const char *text, size_t length)
{
    size_t position = 0;
    while (position < length)
    {
        utf8proc_int32_t codepoint;
        int width = utf8proc_iterate((const utf8proc_uint8_t *)text + position,
                                     length - position, &codepoint);
        if (width <= 0 || reader_newline(codepoint) ||
            (reader_unit() == READER_WORD && reader_space(codepoint)))
            break;
        position += width;
    }
    return position;
}

static int reader_compile_query(struct reader_job *job, const char *query)
{
    size_t bytes = strlen(query), position = 0;
    job->pattern_length = 0;
    if (!bytes || bytes > READER_QUERY_BYTES)
        return READER_INVALID_TEXT;
    while (position < bytes)
    {
        utf8proc_int32_t codepoint;
        int width = utf8proc_iterate((const utf8proc_uint8_t *)query + position,
                                     bytes - position, &codepoint);
        if (width <= 0 || !reader_valid(codepoint) ||
            job->pattern_length == READER_QUERY_BYTES)
            return READER_INVALID_TEXT;
        job->scratch.matcher.pattern[job->pattern_length++] =
            job->preferences.match_case ? codepoint : utf8proc_tolower(codepoint);
        position += width;
    }
    job->scratch.matcher.prefix[0] = 0;
    unsigned int matched = 0;
    for (unsigned int index = 1; index < job->pattern_length; ++index)
    {
        while (matched && job->scratch.matcher.pattern[index] !=
               job->scratch.matcher.pattern[matched])
            matched = job->scratch.matcher.prefix[matched - 1];
        if (job->scratch.matcher.pattern[index] ==
            job->scratch.matcher.pattern[matched])
            ++matched;
        job->scratch.matcher.prefix[index] = matched;
    }
    return 0;
}

/* Eligibility constrains match STARTS, with bounded lookahead past hi.
 * A forward pass can also retain the last match for Previous. */
static int reader_search_range(struct text_reader *reader, off_t low, off_t high,
                               bool previous, off_t *target)
{
    struct reader_job *job = reader->job;
    if (low >= high)
        return 0;
    unsigned int matched = 0, ring = 0;
    off_t position = low;
    bool found = false;
    while (position < reader->size)
    {
        if (position >= high &&
            (!matched || job->scratch.matcher.starts[
                (ring + READER_QUERY_BYTES - matched) % READER_QUERY_BYTES] >= high))
            break;
        utf8proc_int32_t codepoint;
        int width = reader_decode(reader, position, &codepoint);
        if (width < 0)
            return width;
        job->scratch.matcher.starts[ring] = position;
        ring = (ring + 1) % READER_QUERY_BYTES;
        if (!job->preferences.match_case)
            codepoint = utf8proc_tolower(codepoint);
        while (matched && codepoint != job->scratch.matcher.pattern[matched])
            matched = job->scratch.matcher.prefix[matched - 1];
        if (codepoint == job->scratch.matcher.pattern[matched])
            ++matched;
        if (matched == job->pattern_length)
        {
            off_t start = job->scratch.matcher.starts[
                (ring + READER_QUERY_BYTES - matched) % READER_QUERY_BYTES];
            if (start >= low && start < high)
            {
                *target = start;
                found = true;
                if (!previous)
                    return 1;
            }
            matched = job->scratch.matcher.prefix[matched - 1];
        }
        position += width;
    }
    return found ? 1 : 0;
}

static int reader_stage_result(struct text_reader *reader, off_t target,
                               int label, const char *value)
{
    struct reader_job *job = reader->job;
    job->target = target;
    job->length = reader_read_chunk(reader->descriptor, target, reader->size,
                                    job->scratch.staging.chunk, &job->next);
    if (job->length < 0)
        return job->length;
    char *result = job->scratch.staging.result;
    int length = snprintf(result, READER_RESULT_BYTES, "%s%s%s",
                          str(label), value ? ": " : "", value ? value : "");
    if (length <= 0 || length >= READER_RESULT_BYTES)
        return READER_INVALID_TEXT;
    size_t used = length;
    size_t preview = reader_preview_length(job->scratch.staging.chunk, job->length);
    if (preview && used + 2 < READER_RESULT_BYTES)
    {
        result[used++] = '.';
        result[used++] = ' ';
        size_t position = 0;
        while (position < preview)
        {
            utf8proc_int32_t codepoint;
            int width = utf8proc_iterate(
                (const utf8proc_uint8_t *)job->scratch.staging.chunk + position,
                preview - position, &codepoint);
            if (width <= 0 || used + width >= READER_RESULT_BYTES)
                break;
            memcpy(result + used, job->scratch.staging.chunk + position, width);
            used += width;
            position += width;
        }
    }
    result[used] = '\0';
    job->result_length = used;
    job->ready = true;
    return 1;
}

static int reader_commit_result(struct text_reader *reader)
{
    struct reader_job *job = reader->job;
    if (!job->ready)
        return 0;
    job->ready = false;
    reader->scanning = true;
    reader->scan_work = READER_SCAN_BUDGET - 1;
    int status = reader_checkpoint(reader);
    reader->scanning = false;
    if (status < 0)
        return status;
    if (tts_speak(job->scratch.staging.result, job->result_length, false) != 0)
        return READER_READ_ERROR;
    /* Queue acceptance is the transaction boundary, not proof of hearing. */
    reader->cursor = reader->start = job->target;
    DEBUGF("TTS reader cursor: %llu\n", (unsigned long long)reader->cursor);
    reader->next = job->next;
    reader->length = job->length;
    memcpy(reader->text, job->scratch.staging.chunk, job->length + 1);
    reader->loaded = true;
    reader->submitted = false;
    reader->feedback = true;
    reader->dirty = true;
    reader->state = job->target == reader->size ? READER_FINISHED : READER_PAUSED;
    if (job->new_query)
        memcpy(job->accepted_query, job->edit, strlen(job->edit) + 1);
    reader_report_state(reader);
    return 1;
}

static int reader_search(struct text_reader *reader, int direction, bool new_query,
                         bool *usb)
{
    struct reader_job *job = reader->job;
    job->ready = false;
    job->new_query = new_query;
    if (new_query)
    {
        memcpy(job->edit, job->accepted_query, sizeof(job->edit));
        splash(HZ, ID2P(LANG_TTS_FIND));
        if (kbd_input_ex(job->edit, sizeof(job->edit), NULL, usb) != 0)
            return 0;
    }
    else if (!job->accepted_query[0])
    {
        splash(HZ * 2, ID2P(LANG_TTS_QUERY_REQUIRED));
        return 0;
    }
    if (tts_reader_preferences_get(&job->preferences))
    {
        splash(HZ * 2, ID2P(LANG_TTS_READER_STORAGE_ERROR));
        if (job->preferences.cleanup_error)
            splash(HZ * 2, ID2P(LANG_TTS_READER_TEMP_ERROR));
    }
    int status = reader_compile_query(job, new_query ? job->edit : job->accepted_query);
    if (status < 0)
    {
        splash(HZ * 2, ID2P(LANG_TTS_QUERY_INVALID));
        return 0;
    }
    reader->scanning = true;
    reader->scan_work = 0;
    status = reader_prepare(reader);
    off_t boundary = reader->cursor;
    bool previous = direction < 0, wrapped = false;
    if (status >= 0 && direction > 0 && boundary < reader->size)
    {
        utf8proc_int32_t codepoint;
        status = reader_decode(reader, boundary, &codepoint);
        if (status > 0)
            boundary += status;
    }
    off_t target = reader->cursor;
    if (status >= 0)
        status = reader_search_range(reader, previous ? reader->first : boundary,
                                      previous ? boundary : reader->size,
                                      previous, &target);
    if (status == 0 && job->preferences.wrap != TTS_READER_WRAP_STOP)
    {
        bool wrap = job->preferences.wrap == TTS_READER_WRAP_AUTO;
        if (!wrap)
        {
            const char *question = (const char *)str(LANG_TTS_WRAP_QUESTION);
            const struct text_message message = { &question, 1 };
            enum yesno_res answer = gui_syncyesno_run(&message, NULL, NULL);
            *usb = answer == YESNO_USB;
            wrap = answer == YESNO_YES;
        }
        if (wrap && !*usb)
        {
            wrapped = true;
            status = reader_search_range(reader, previous ? boundary : reader->first,
                                          previous ? reader->size : boundary,
                                          previous, &target);
        }
    }
    if (status > 0)
        status = reader_stage_result(reader, target, wrapped ?
            LANG_TTS_FOUND_WRAPPED : LANG_TTS_FOUND, NULL);
    reader->scanning = false;
    if (status == 0 && !*usb)
        splash(HZ * 2, ID2P(LANG_TTS_NO_MORE_MATCHES));
    return status;
}

static bool reader_decimal(const char *text, uint64_t *value)
{
    *value = 0;
    if (!*text)
        return false;
    while (*text)
    {
        if (*text < '0' || *text > '9')
            return false;
        unsigned int digit = *text++ - '0';
        if (*value > (UINT64_MAX - digit) / 10)
            return false;
        *value = *value * 10 + digit;
    }
    return true;
}

static int reader_ordinal(struct text_reader *reader, uint64_t ordinal,
                          bool page, off_t *target)
{
    if (!ordinal)
        return 0;
    int lines = page ? global_settings.tts_reader_page_lines : 1;
    if (lines < 1 || lines > 100)
        lines = 20;
    off_t position = reader->first;
    uint64_t current = 1;
    int count = 0;
    while (position < reader->size)
    {
        if (current == ordinal)
        {
            *target = position;
            return 1;
        }
        bool blank;
        int status = reader_line_after(reader, position, &position, &blank);
        if (status < 0)
            return status;
        if (++count == lines)
        {
            count = 0;
            if (current == UINT64_MAX)
                return READER_READ_ERROR;
            ++current;
        }
    }
    return 0;
}

static int reader_percentage(struct text_reader *reader, unsigned int percent,
                             off_t *target)
{
    if (percent > 100)
        return 0;
    if (!percent || reader->first == reader->size)
    {
        *target = percent == 100 ? reader->size : reader->first;
        return 1;
    }
    if (percent == 100)
    {
        *target = reader->size;
        return 1;
    }
    off_t position = reader_percent_offset((uint64_t)reader->size, percent, false);
    if (position < reader->first)
        position = reader->first;
    off_t original = position;
    int value = reader_byte(reader, position);
    if (value < 0)
        return value;
    while ((value & 0xc0) == 0x80 && position > reader->first &&
           original - position < 3)
    {
        value = reader_byte(reader, --position);
        if (value < 0)
            return value;
    }
    utf8proc_int32_t codepoint;
    int width = reader_decode(reader, position, &codepoint);
    if (width < 0)
        return width;
    if (width == 0 || original - position >= width)
        return READER_INVALID_TEXT;
    if (codepoint == '\n' && position > reader->first)
    {
        value = reader_byte(reader, position - 1);
        if (value < 0)
            return value;
        if (value == '\r')
            --position;
    }
    *target = position;
    return 1;
}

static int reader_go_to(struct text_reader *reader, int kind, bool *usb)
{
    static ucschar_t digits[] = {
        10, '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 0xfeff
    };
    static const int labels[] = {
        LANG_TTS_GOTO_LINE, LANG_TTS_GOTO_PAGE, LANG_TTS_GOTO_PERCENT
    };
    struct reader_job *job = reader->job;
    job->ready = job->new_query = false;
    job->edit[0] = '\0';
    splash(HZ, ID2P(labels[kind]));
    if (kbd_input_ex(job->edit, 21, digits, usb) != 0)
        return 0;
    uint64_t value;
    if (!reader_decimal(job->edit, &value) ||
        (kind == 2 ? value > 100 : value == 0))
    {
        splash(HZ * 2, ID2P(LANG_TTS_DESTINATION_INVALID));
        return 0;
    }
    reader->scanning = true;
    reader->scan_work = 0;
    int status = reader_prepare(reader);
    off_t target = reader->cursor;
    if (status >= 0)
        status = kind == 2 ? reader_percentage(reader, value, &target) :
            reader_ordinal(reader, value, kind == 1, &target);
    if (status > 0)
        status = reader_stage_result(reader, target, labels[kind], job->edit);
    reader->scanning = false;
    if (status == 0)
        splash(HZ * 2, ID2P(LANG_TTS_DESTINATION_INVALID));
    return status;
}

static bool reader_preference_menu(bool match_case)
{
    MENUITEM_STRINGLIST(case_menu, ID2P(LANG_TTS_SEARCH_CASE), NULL,
                        ID2P(LANG_TTS_IGNORE_CASE), ID2P(LANG_TTS_MATCH_CASE));
    MENUITEM_STRINGLIST(wrap_menu, ID2P(LANG_TTS_SEARCH_WRAP), NULL,
                        ID2P(LANG_TTS_WRAP_STOP), ID2P(LANG_TTS_WRAP_ASK),
                        ID2P(LANG_TTS_WRAP_AUTO));
    struct tts_reader_preferences preferences;
    if (tts_reader_preferences_get(&preferences))
    {
        splash(HZ * 2, ID2P(LANG_TTS_READER_STORAGE_ERROR));
        if (preferences.cleanup_error)
            splash(HZ * 2, ID2P(LANG_TTS_READER_TEMP_ERROR));
    }
    int selected = match_case ? preferences.match_case : (int)preferences.wrap;
    int choice = do_menu(match_case ? &case_menu : &wrap_menu, &selected, NULL, false);
    if (choice == MENU_ATTACHED_USB)
        return true;
    /* selected is a cursor, including on Cancel; only choice is acceptance. */
    if (choice >= 0 && choice < (match_case ? 2 : 3) &&
        tts_reader_preferences_set(match_case ? TTS_READER_PREF_MATCH_CASE :
                                   TTS_READER_PREF_WRAP, choice))
    {
        tts_reader_preferences_get(&preferences);
        splash(HZ * 2, ID2P(LANG_TTS_READER_STORAGE_ERROR));
        if (preferences.cleanup_error)
            splash(HZ * 2, ID2P(LANG_TTS_READER_TEMP_ERROR));
    }
    return false;
}

static bool reader_menu(struct text_reader *reader)
{
    extern const struct menu_item_ex tts_reader_settings_menu;
    extern const struct menu_item_ex tts_settings_menu;
    MENUITEM_STRINGLIST(menu, ID2P(LANG_TTS_READER_MENU), NULL,
                        ID2P(LANG_TTS_RESUME), ID2P(LANG_BOOKMARK_MENU),
                        ID2P(LANG_PROPERTIES), ID2P(LANG_TTS_BEGINNING),
                        ID2P(LANG_TTS_END), ID2P(LANG_TTS_READER_SETTINGS),
                        ID2P(LANG_TTS), ID2P(LANG_TTS_FIND),
                        ID2P(LANG_TTS_FIND_NEXT), ID2P(LANG_TTS_FIND_PREVIOUS),
                        ID2P(LANG_TTS_GOTO_LINE), ID2P(LANG_TTS_GOTO_PAGE),
                        ID2P(LANG_TTS_GOTO_PERCENT), ID2P(LANG_TTS_SEARCH_CASE),
                        ID2P(LANG_TTS_SEARCH_WRAP));
    bool finished = reader->state == READER_FINISHED;
    reader_interrupt(reader);
    if (finished || (reader->initialized && reader->cursor == reader->size))
        reader->state = READER_FINISHED;
    action_wait_for_release();
    int selected = 0;
    bool usb = false;
    reader->job->ready = false;
    while (!usb)
    {
        int choice = do_menu(&menu, &selected, NULL, false);
        if (choice == MENU_ATTACHED_USB)
            usb = true;
        else if (choice < 0)
            break;
        else if (choice == 0)
        {
            reader_toggle(reader);
            break;
        }
        else if (choice == 1)
            usb = reader_bookmarks(reader);
        else if (choice == 2)
        {
            struct simplelist_info info;
            simplelist_info_init(&info, str(LANG_PROPERTIES), 5, reader);
            info.get_name = reader_property;
            info.get_talk = reader_property_speak;
            usb = simplelist_show_list(&info);
        }
        else if (choice == 3 || choice == 4)
        {
            if (reader_prepare(reader) < 0)
                reader_fail(reader, LANG_READ_FAILED);
            else
            {
                reader->cursor = choice == 3 ? reader->first : reader->size;
                reader->state = choice == 3 ? READER_PAUSED : READER_FINISHED;
            }
            break;
        }
        else if (choice == 5 || choice == 6)
            usb = do_menu(choice == 5 ? &tts_reader_settings_menu :
                          &tts_settings_menu, NULL, NULL, false) == MENU_ATTACHED_USB;
        else if (choice >= 7 && choice <= 12)
        {
            int status = choice <= 9 ?
                reader_search(reader, choice == 7 ? 0 : choice == 8 ? 1 : -1,
                              choice == 7, &usb) :
                reader_go_to(reader, choice - 10, &usb);
            if (status == READER_CANCELLED || status > 0 || usb)
                break;
            if (status < 0)
            {
                int message = status == READER_INVALID_TEXT ?
                    LANG_TTS_INVALID_TEXT : LANG_TTS_OPERATION_FAILED;
                splash(HZ * 2, ID2P(message));
            }
        }
        else if (choice == 13 || choice == 14)
            usb = reader_preference_menu(choice == 13);
    }
    talk_force_shutup();
    action_wait_for_release();
    if (!usb && reader->job->ready)
    {
        int status = reader_commit_result(reader);
        if (status < 0 && status != READER_CANCELLED)
            splash(HZ * 2, ID2P(LANG_TTS_OPERATION_FAILED));
    }
    reader->dirty = true;
    return usb;
}

static size_t reader_feedback_length(const struct text_reader *reader)
{
    return reader_preview_length(reader->text, reader->length);
}

static void reader_navigate(struct text_reader *reader, bool forward)
{
    if (reader->state == READER_FAILED ||
        (forward && reader->state == READER_FINISHED))
        return;
    reader_interrupt(reader);
    int status = reader_prepare(reader);
    off_t target = reader->cursor;
    if (status >= 0)
    {
        reader->scanning = true;
        reader->scan_work = 0;
        status = reader_seek_unit(reader, forward, &target);
        reader->scanning = false;
    }
    if (status == READER_CANCELLED)
        return;
    if (status < 0)
    {
        reader_read_failed(reader, status);
        return;
    }
    reader->cursor = target;
    DEBUGF("TTS reader cursor: %llu\n", (unsigned long long)target);
    reader_report_state(reader);
    if (!reader_load(reader))
        return;
    if (target == reader->size)
        reader_finish(reader);
    else
    {
        reader->feedback = true;
        int result = 0;
        if (reader_unit() == READER_CHARACTER)
        {
            utf8proc_int32_t codepoint;
            int width = utf8proc_iterate((const utf8proc_uint8_t *)reader->text,
                                         reader->length, &codepoint);
            if (width <= 0)
            {
                reader_read_failed(reader, READER_INVALID_TEXT);
                return;
            }
            if (reader_newline(codepoint))
            {
                const char *label = (const char *)str(LANG_TTS_NEWLINE);
                result = tts_speak(label, strlen(label), false);
            }
            else
                result = tts_speak_character(codepoint);
        }
        else
        {
            size_t length = reader_feedback_length(reader);
            if (length)
                result = tts_speak(reader->text, length, false);
        }
        if (result < 0)
            reader_fail(reader, LANG_TTS_ERROR);
    }
}

static void reader_change_unit(struct text_reader *reader, bool increase)
{
    if (reader->state == READER_FAILED)
        return;
    bool finished = reader->state == READER_FINISHED;
    reader_interrupt(reader);
    if (finished)
        reader->state = READER_FINISHED;
    int unit = reader_unit() + (increase ? 1 : -1);
    if (unit > READER_PAGE)
        unit = READER_CHARACTER;
    if (unit < READER_CHARACTER)
        unit = READER_PAGE;
    global_settings.tts_reader_unit = unit;
    DEBUGF("TTS reader unit: %d offset=%llu\n", unit,
           (unsigned long long)reader->cursor);
    reader_report_state(reader);
    settings_save();
    if (!reader_load(reader))
        return;
    const char *label = (const char *)str(reader_unit_label());
    reader->feedback = true;
    if (tts_speak(label, strlen(label), false) < 0)
        reader_fail(reader, LANG_TTS_ERROR);
}

static const char *reader_current_text(const struct text_reader *reader)
{
    if (!reader->loaded || reader->cursor < reader->start ||
        reader->cursor > reader->next)
        return "";
    return reader->text + (reader->cursor - reader->start);
}

static void reader_draw(struct text_reader *reader)
{
    char position[80];
    snprintf(position, sizeof(position), "%llu / %llu (%u%%)",
             (unsigned long long)reader->cursor,
             (unsigned long long)reader->size, reader_percent(reader));
    char preview[160];
    const char *text = reader_current_text(reader);
    size_t length = strlen(text);
    size_t source = 0;
    size_t output = 0;
    while (source < length)
    {
        utf8proc_int32_t codepoint;
        int width = utf8proc_iterate((const utf8proc_uint8_t *)text + source,
                                     length - source, &codepoint);
        if (width <= 0 || output + width >= sizeof(preview))
            break;
        if (reader_space(codepoint))
            preview[output++] = ' ';
        else
        {
            memcpy(preview + output, text + source, width);
            output += width;
        }
        source += width;
    }
    preview[output] = '\0';
    FOR_NB_SCREENS(screen_index)
    {
        struct screen *display = &screens[screen_index];
        display->set_viewport(&reader->viewports[screen_index]);
        display->scroll_stop_viewport(&reader->viewports[screen_index]);
        display->clear_viewport();
        int lines = display->getheight() / display->getcharheight();
#ifdef HAVE_TOUCHSCREEN
        if (screen_index == SCREEN_MAIN)
        {
            reader->touch_line_height = display->getcharheight();
            reader->touch_lines = lines;
        }
#endif
        int row = 0;
        if (lines >= 5)
            display->puts_scroll(0, row++, (const unsigned char *)reader->name);
        display->puts_scroll(0, row++, (const unsigned char *)reader_label(reader));
        if (row < lines)
            display->puts_scroll(0, row++, (const unsigned char *)position);
        if (row < lines)
            display->puts_scroll(0, row++, (const unsigned char *)preview);
        if (row < lines)
            display->puts_scroll(0, row,
                                 (const unsigned char *)str(reader_unit_label()));
        display->update_viewport();
        display->set_viewport(NULL);
    }
    reader->dirty = false;
}

#ifdef HAVE_TOUCHSCREEN
static void reader_explore(struct text_reader *reader)
{
    int touch_x, touch_y;
    bool force;
    if (!accessibility_explore_point(&touch_x, &touch_y, &force))
        return;
    const struct viewport *viewport = &reader->viewports[SCREEN_MAIN];
    int row = -1;
    if (viewport_point_within_vp(viewport, touch_x, touch_y) &&
        reader->touch_line_height > 0)
    {
        row = (touch_y - viewport->y) / reader->touch_line_height;
        if (row >= reader->touch_lines)
            row = -1;
        else if (reader->touch_lines < 5)
            ++row;
        if (row > 4)
            row = -1;
    }
    accessibility_explore_feedback(reader, row, row >= 0);
    if (!force && reader->touch_row == row)
        return;
    reader->touch_row = row;
    if (row < 0 && !accessibility_empty_speech_enabled())
        return;
    enum reader_state previous = reader->state;
    const char *state_label = reader_label(reader);
    if (previous != READER_FAILED)
    {
        reader_interrupt(reader);
        if (!reader_load(reader))
            return;
        reader->state = previous;
    }
    char position[80];
    const char *text;
    switch (row)
    {
        case 0:
            text = reader->name;
            break;
        case 1:
            text = state_label;
            break;
        case 2:
            snprintf(position, sizeof(position), "%llu / %llu (%u%%)",
                     (unsigned long long)reader->cursor,
                     (unsigned long long)reader->size, reader_percent(reader));
            text = position;
            break;
        case 3:
            text = reader_current_text(reader);
            break;
        case 4:
            text = (const char *)str(reader_unit_label());
            break;
        default:
            text = (const char *)str(LANG_ACCESSIBILITY_EMPTY);
            break;
    }
    reader->feedback = true;
    if (tts_speak(text, strlen(text), false) < 0)
        reader_fail(reader, LANG_TTS_ERROR);
}
#endif

static void reader_cleanup(void *context)
{
    struct text_reader *reader = context;
    if (!reader->active)
    {
        reader_job_release(reader);
        return;
    }
#ifdef HAVE_TOUCHSCREEN
    accessibility_reset();
#endif
    tts_stop();
    if (reader->descriptor >= 0)
    {
        close(reader->descriptor);
        reader->descriptor = -1;
    }
    FOR_NB_SCREENS(screen_index)
    {
        screens[screen_index].scroll_stop_viewport(&reader->viewports[screen_index]);
        screens[screen_index].set_viewport(NULL);
        viewportmanager_theme_undo(screen_index, true);
    }
    reader->active = false;
    /* Release LAST: normal cleanup may yield through speech/views/files. */
    reader_job_release(reader);
}

static bool reader_open_file(const char *path,
                              const struct text_bookmark *bookmark)
{
    struct text_reader reader = { .descriptor = -1, .state = READER_READING };
    bool usb = false;
    int preparation_status;
    if (!path)
        return false;
    if (!reader_job_acquire(&reader))
    {
        splash(HZ * 2, ID2P(LANG_TTS_READER_BUSY));
        return false;
    }
#ifdef HAVE_TOUCHSCREEN
    reader.touch_row = -2;
    accessibility_set_target(&reader);
#endif
    const char *separator = strrchr(path, '/');
    reader.path = path;
    reader.name = separator ? separator + 1 : path;
    talk_force_shutup();
    FOR_NB_SCREENS(screen_index)
    {
        screens[screen_index].set_viewport(NULL);
        screens[screen_index].scroll_stop();
        viewportmanager_theme_enable(screen_index, false,
                                     &reader.viewports[screen_index]);
    }
    reader.active = true;
    reader.dirty = true;
    if (!tts_is_available())
        reader_fail(&reader, LANG_TTS_ERROR);
    else if ((reader.descriptor = open(path, O_RDONLY)) < 0)
        reader_fail(&reader, LANG_READ_FAILED);
    else
    {
        reader.size = ffilesize(reader.descriptor);
        if (reader.size < 0)
        {
            reader.size = 0;
            reader_fail(&reader, LANG_READ_FAILED);
        }
        /* Establish BOM/content origin before speech busy can defer reader_step. */
        else if ((preparation_status = reader_prepare(&reader)) < 0)
            reader_read_failed(&reader, preparation_status);
        else if (bookmark && !reader_restore_bookmark(&reader, bookmark))
            reader_fail(&reader, LANG_TTS_BOOKMARK_CHANGED);
        else
        {
            reader.state = READER_READING;
            reader_step(&reader);
            if (reader.state == READER_READING)
                reader_report_state(&reader);
        }
    }
    while (reader.active)
    {
        reader_sync(&reader);
        if (reader.dirty)
            reader_draw(&reader);
        int action = reader.pending_action;
        reader.pending_action = ACTION_NONE;
        if (action == ACTION_NONE)
            action = reader_action(MAX(1, HZ / 20));
        if (action == ACTION_STD_CANCEL)
            break;
        if (default_event_handler_ex(action, reader_cleanup, &reader)
            == SYS_USB_CONNECTED)
        {
            usb = true;
            break;
        }
        if (!reader.active)
            break;
        switch (action)
        {
#ifdef HAVE_TOUCHSCREEN
            case ACTION_TOUCHSCREEN:
                reader_explore(&reader);
                break;
#endif
            case ACTION_STD_CONTEXT:
                if (reader.state != READER_FAILED && reader_menu(&reader))
                {
                    usb = true;
                    reader_cleanup(&reader);
                }
                break;
            case ACTION_STD_OK:
                reader_toggle(&reader);
                break;
            case ACTION_SETTINGS_INC:
            case ACTION_SETTINGS_INCREPEAT:
                reader_change_unit(&reader, true);
                break;
            case ACTION_SETTINGS_DEC:
            case ACTION_SETTINGS_DECREPEAT:
                reader_change_unit(&reader, false);
                break;
            case ACTION_STD_PREV:
            case ACTION_STD_PREVREPEAT:
                reader_navigate(&reader, false);
                break;
            case ACTION_STD_NEXT:
            case ACTION_STD_NEXTREPEAT:
                reader_navigate(&reader, true);
                break;
            case ACTION_REDRAW:
                reader.dirty = true;
                break;
        }
        if (reader.state == READER_READING)
            reset_poweroff_timer();
        reader_step(&reader);
    }
    reader_cleanup(&reader);
    return usb;
}

bool tts_read_file(const char *path)
{
    return reader_open_file(path, NULL);
}

bool tts_read_bookmark(const char *path, const struct text_bookmark *bookmark)
{
    return reader_open_file(path, bookmark);
}
