#include "config.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "system.h"
#include "kernel.h"
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

static unsigned int reader_percent(const struct text_reader *reader)
{
    if (reader->size <= 0)
        return reader->state == READER_FINISHED ? 100 : 0;
    return (uint64_t)reader->cursor * 100 / reader->size;
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

static bool reader_menu(struct text_reader *reader)
{
    extern const struct menu_item_ex tts_reader_settings_menu;
    extern const struct menu_item_ex tts_settings_menu;
    MENUITEM_STRINGLIST(menu, ID2P(LANG_TTS_READER_MENU), NULL,
                        ID2P(LANG_TTS_RESUME), ID2P(LANG_BOOKMARK_MENU),
                        ID2P(LANG_PROPERTIES), ID2P(LANG_TTS_BEGINNING),
                        ID2P(LANG_TTS_END), ID2P(LANG_TTS_READER_SETTINGS),
                        ID2P(LANG_TTS));
    bool finished = reader->state == READER_FINISHED;
    reader_interrupt(reader);
    if (finished || (reader->initialized && reader->cursor == reader->size))
        reader->state = READER_FINISHED;
    action_wait_for_release();
    int selected = 0;
    bool usb = false;
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
    }
    talk_force_shutup();
    action_wait_for_release();
    reader->dirty = true;
    return usb;
}

static size_t reader_feedback_length(const struct text_reader *reader)
{
    size_t position = 0;
    while (position < (size_t)reader->length)
    {
        utf8proc_int32_t codepoint;
        int width = utf8proc_iterate((const utf8proc_uint8_t *)reader->text + position,
                                     reader->length - position, &codepoint);
        if (width <= 0 || reader_newline(codepoint) ||
            (reader_unit() == READER_WORD && reader_space(codepoint)))
            break;
        position += width;
    }
    return position;
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
        return;
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
}

static bool reader_open_file(const char *path,
                              const struct text_bookmark *bookmark)
{
    struct text_reader reader = { .descriptor = -1, .state = READER_READING };
#ifdef HAVE_TOUCHSCREEN
    reader.touch_row = -2;
    accessibility_set_target(&reader);
#endif
    bool usb = false;
    if (!path)
        return false;
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
