#include "config.h"
#include "accessibility_typing.h"

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)

#include <stdio.h>
#include <string.h>
#include "accessibility_touch.h"
#include "action.h"
#include "file.h"
#include "kernel.h"
#include "lang.h"
#include "menu.h"
#include "rbpaths.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"
#include "touchscreen.h"
#include "tts.h"
#include "utf8proc.h"

#define TYPING_FILE ROCKBOX_DIR "/accessibility-typing.cfg"
#define TYPING_TEMP ROCKBOX_DIR "/accessibility-typing.cfg.tmp"
#define TYPING_HEADER "RBACCESSIBILITY-TYPING:1\nmode:"
#define TYPING_ECHO_FILE ROCKBOX_DIR "/accessibility-typing-echo.cfg"
#define TYPING_ECHO_TEMP ROCKBOX_DIR "/accessibility-typing-echo.cfg.tmp"
#define TYPING_ECHO_HEADER "RBACCESSIBILITY-TYPING-ECHO:1\n"
#define TYPING_EXPLORE_MS 220u
#define TYPING_TAP_MS 180u
#define TYPING_DOUBLE_MS 320u
#define TYPING_TAP_SLOP 8

static enum accessibility_typing_mode selected_mode;
static bool loaded;
static bool echo_loaded;
static struct accessibility_typing_echo_settings echo_settings;
static bool session_active;
static bool raw_pending;
static struct touchevent raw_event;
static struct
{
    bool down;
    bool discard;
    bool exploring;
    bool moved;
    bool pending_tap;
    bool have_time;
    int start_x;
    int start_y;
    int target;
    int focus;
    int tap_target;
    uint32_t press_ms;
    uint32_t tap_ms;
    uint32_t last_ms;
} touch;

static bool typing_load(enum accessibility_typing_mode *mode)
{
    char data[sizeof(TYPING_HEADER) + 3];
    size_t used = 0;
    int descriptor = open(TYPING_FILE, O_RDONLY);
    if (descriptor < 0)
        return false;
    bool valid = true;
    while (used < sizeof(data))
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - used);
        if (count < 0)
        {
            valid = false;
            break;
        }
        if (!count)
            break;
        used += count;
    }
    if (close(descriptor) != 0)
        valid = false;
    const size_t prefix = sizeof(TYPING_HEADER) - 1;
    if (!valid || used != prefix + 2 || memcmp(data, TYPING_HEADER, prefix) ||
        data[prefix] < '0' || data[prefix] >= '0' + ACCESSIBILITY_TYPING_MODE_COUNT ||
        data[prefix + 1] != '\n')
        return false;
    *mode = data[prefix] - '0';
    return true;
}

enum accessibility_typing_mode accessibility_typing_mode(void)
{
    if (!loaded)
    {
        selected_mode = ACCESSIBILITY_TYPING_LIFT;
        typing_load(&selected_mode);
        loaded = true;
    }
    return selected_mode;
}

void accessibility_typing_cancel_touch(void)
{
    memset(&touch, 0, sizeof(touch));
    touch.target = ACCESSIBILITY_TYPING_NO_TARGET;
    touch.focus = ACCESSIBILITY_TYPING_NO_TARGET;
    touch.tap_target = ACCESSIBILITY_TYPING_NO_TARGET;
    raw_pending = false;
}

static bool typing_save(const char *path, const char *temporary,
                        const char *data, size_t length)
{
    int descriptor = open(temporary, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (descriptor < 0)
        return false;
    size_t written = 0;
    bool valid = true;
    while (written < length)
    {
        ssize_t count = write(descriptor, data + written, length - written);
        if (count <= 0)
        {
            valid = false;
            break;
        }
        written += count;
    }
    if (fsync(descriptor) != 0)
        valid = false;
    if (close(descriptor) != 0)
        valid = false;
    if (!valid || rename(temporary, path) != 0)
    {
        remove(temporary);
        return false;
    }
    return true;
}

bool accessibility_typing_set_mode(enum accessibility_typing_mode mode)
{
    if ((unsigned int)mode >= ACCESSIBILITY_TYPING_MODE_COUNT)
        return false;
    char data[sizeof(TYPING_HEADER) + 3];
    int length = snprintf(data, sizeof(data), TYPING_HEADER "%u\n", (unsigned int)mode);
    if (length <= 0 || (size_t)length >= sizeof(data) ||
        !typing_save(TYPING_FILE, TYPING_TEMP, data, length))
        return false;
    selected_mode = mode;
    loaded = true;
    accessibility_typing_cancel_touch();
    return true;
}

int accessibility_typing_menu(void)
{
    static const struct opt_items modes[] = {
        { STR(LANG_ACCESSIBILITY_TYPING_LIFT) },
        { STR(LANG_ACCESSIBILITY_TYPING_DOUBLE_TAP) },
        { STR(LANG_ACCESSIBILITY_TYPING_ARROWS) }
    };
    int choice = accessibility_typing_mode();
    if (set_option(str(LANG_ACCESSIBILITY_TYPING_MODE), &choice, RB_INT,
                   modes, ACCESSIBILITY_TYPING_MODE_COUNT, NULL))
        return MENU_ATTACHED_USB;
    if (choice != (int)accessibility_typing_mode() &&
        !accessibility_typing_set_mode(choice))
    {
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    }
    return 0;
}

static bool typing_echo_valid(const struct accessibility_typing_echo_settings *settings)
{
    return settings && (unsigned int)settings->echo < ACCESSIBILITY_ECHO_MODE_COUNT &&
        (unsigned int)settings->deletion < ACCESSIBILITY_DELETION_MODE_COUNT &&
        (unsigned int)settings->capitals < ACCESSIBILITY_CAPITALS_MODE_COUNT &&
        settings->pitch_percent >= -80 && settings->pitch_percent <= 100;
}

static bool typing_echo_number(const char **cursor, const char *key, int *value)
{
    size_t length = strlen(key);
    if (strncmp(*cursor, key, length))
        return false;
    const char *number = *cursor + length;
    bool negative = *number == '-';
    if (negative)
        ++number;
    const char *digits = number;
    int result = 0;
    while (*number >= '0' && *number <= '9')
    {
        result = result * 10 + *number++ - '0';
        if (result > 100 || number - digits > 3)
            return false;
    }
    if (number == digits || *number != '\n' ||
        (number - digits > 1 && *digits == '0') || (negative && !result))
        return false;
    *value = negative ? -result : result;
    *cursor = number + 1;
    return true;
}

static bool typing_echo_load(struct accessibility_typing_echo_settings *settings)
{
    char data[128];
    size_t used = 0;
    int descriptor = open(TYPING_ECHO_FILE, O_RDONLY);
    if (descriptor < 0)
        return false;
    bool valid = true;
    while (used < sizeof(data) - 1)
    {
        ssize_t count = read(descriptor, data + used, sizeof(data) - 1 - used);
        if (count < 0)
        {
            valid = false;
            break;
        }
        if (!count)
            break;
        used += count;
    }
    if (close(descriptor) != 0)
        valid = false;
    data[used] = '\0';
    if (!valid || used == sizeof(data) - 1 || strlen(data) != used ||
        strncmp(data, TYPING_ECHO_HEADER, sizeof(TYPING_ECHO_HEADER) - 1))
        return false;
    const char *cursor = data + sizeof(TYPING_ECHO_HEADER) - 1;
    int echo, deletion, capitals, pitch;
    if (!typing_echo_number(&cursor, "echo:", &echo) ||
        !typing_echo_number(&cursor, "delete:", &deletion) ||
        !typing_echo_number(&cursor, "capitals:", &capitals) ||
        !typing_echo_number(&cursor, "pitch:", &pitch) || *cursor)
        return false;
    struct accessibility_typing_echo_settings candidate = {echo, deletion, capitals, pitch};
    if (!typing_echo_valid(&candidate))
        return false;
    *settings = candidate;
    return true;
}

void accessibility_typing_get_echo_settings(struct accessibility_typing_echo_settings *settings)
{
    if (!echo_loaded)
    {
        echo_settings = (struct accessibility_typing_echo_settings){
            ACCESSIBILITY_ECHO_BOTH, ACCESSIBILITY_DELETION_ANNOUNCE,
            ACCESSIBILITY_CAPITALS_NONE, 20
        };
        typing_echo_load(&echo_settings);
        echo_loaded = true;
    }
    if (settings)
        *settings = echo_settings;
}

bool accessibility_typing_set_echo_settings(const struct accessibility_typing_echo_settings *settings)
{
    if (!typing_echo_valid(settings))
        return false;
    struct accessibility_typing_echo_settings current;
    accessibility_typing_get_echo_settings(&current);
    if (settings->echo == current.echo && settings->deletion == current.deletion &&
        settings->capitals == current.capitals && settings->pitch_percent == current.pitch_percent)
        return true;
    char data[128];
    int length = snprintf(data, sizeof(data), TYPING_ECHO_HEADER
        "echo:%d\ndelete:%d\ncapitals:%d\npitch:%d\n", settings->echo,
        settings->deletion, settings->capitals, settings->pitch_percent);
    if (length <= 0 || (size_t)length >= sizeof(data) ||
        !typing_save(TYPING_ECHO_FILE, TYPING_ECHO_TEMP, data, length))
        return false;
    echo_settings = *settings;
    return true;
}

static int typing_echo_save_menu(const struct accessibility_typing_echo_settings *settings)
{
    if (!accessibility_typing_set_echo_settings(settings))
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    return 0;
}

int accessibility_typing_echo_menu(void)
{
    static const struct opt_items options[] = {
        { STR(LANG_ACCESSIBILITY_ECHO_NONE) },
        { STR(LANG_ACCESSIBILITY_ECHO_CHARACTERS) },
        { STR(LANG_ACCESSIBILITY_ECHO_WORDS) },
        { STR(LANG_ACCESSIBILITY_ECHO_BOTH) }
    };
    struct accessibility_typing_echo_settings settings;
    accessibility_typing_get_echo_settings(&settings);
    int choice = settings.echo;
    if (set_option(str(LANG_ACCESSIBILITY_ECHO), &choice, RB_INT,
                   options, ACCESSIBILITY_ECHO_MODE_COUNT, NULL))
        return MENU_ATTACHED_USB;
    settings.echo = choice;
    return typing_echo_save_menu(&settings);
}

int accessibility_typing_deletion_menu(void)
{
    static const struct opt_items options[] = {
        { STR(LANG_ACCESSIBILITY_DELETED_CHARACTER) },
        { STR(LANG_ACCESSIBILITY_CHARACTER_ONLY) },
        { STR(LANG_ACCESSIBILITY_ECHO_NONE) }
    };
    struct accessibility_typing_echo_settings settings;
    accessibility_typing_get_echo_settings(&settings);
    int choice = settings.deletion;
    if (set_option(str(LANG_ACCESSIBILITY_DELETE_ECHO), &choice, RB_INT,
                   options, ACCESSIBILITY_DELETION_MODE_COUNT, NULL))
        return MENU_ATTACHED_USB;
    settings.deletion = choice;
    return typing_echo_save_menu(&settings);
}

int accessibility_typing_capitals_menu(void)
{
    static const struct opt_items options[] = {
        { STR(LANG_ACCESSIBILITY_ECHO_NONE) },
        { STR(LANG_ACCESSIBILITY_CAPITAL_SPOKEN) },
        { STR(LANG_ACCESSIBILITY_CAPITAL_PITCH) }
    };
    struct accessibility_typing_echo_settings settings;
    accessibility_typing_get_echo_settings(&settings);
    int choice = settings.capitals;
    if (set_option(str(LANG_ACCESSIBILITY_CAPITALS), &choice, RB_INT,
                   options, ACCESSIBILITY_CAPITALS_MODE_COUNT, NULL))
        return MENU_ATTACHED_USB;
    settings.capitals = choice;
    return typing_echo_save_menu(&settings);
}

int accessibility_typing_capital_pitch_menu(void)
{
    struct accessibility_typing_echo_settings settings;
    accessibility_typing_get_echo_settings(&settings);
    if (set_int(str(LANG_ACCESSIBILITY_CAPITAL_PITCH_PERCENT), "%", UNIT_PERCENT,
                &settings.pitch_percent, NULL, 1, -80, 100, NULL))
        return MENU_ATTACHED_USB;
    return typing_echo_save_menu(&settings);
}

void accessibility_typing_speak_character(uint32_t character, bool enqueue)
{
    if (!character || character > 0x10ffff ||
        (character >= 0xd800 && character <= 0xdfff) ||
        !talk_menus_enabled(&global_settings))
        return;
    unsigned char text[5];
    int length = utf8proc_encode_char(character, text);
    if (length <= 0)
        return;
    text[length] = '\0';
    accessibility_typing_get_echo_settings(NULL);
    if (character == ' ')
    {
        talk_id(VOICE_BLANK, enqueue);
        return;
    }
    utf8proc_category_t category = utf8proc_category(character);
    bool capital = category == UTF8PROC_CATEGORY_LU || category == UTF8PROC_CATEGORY_LT;
    if (talk_spell("", enqueue) < 0)
        return;
    if (capital && echo_settings.capitals == ACCESSIBILITY_CAPITALS_SPOKEN &&
        talk_id(LANG_ACCESSIBILITY_CAPITAL, true) < 0)
        return;
    if (tts_is_available())
    {
        int pitch = capital && echo_settings.capitals == ACCESSIBILITY_CAPITALS_PITCH ?
            echo_settings.pitch_percent : 0;
        tts_speak_character_options(character, true, pitch);
    }
    else
        talk_spell((const char *)text, true);
}

static bool typing_word_character(uint32_t character)
{
    utf8proc_category_t category = utf8proc_category(character);
    return (category >= UTF8PROC_CATEGORY_LU && category <= UTF8PROC_CATEGORY_PC) ||
        character == '\'' || character == 0x2019;
}

static bool typing_echo_position(const char *text, int cursor,
                                 size_t *last, size_t *end, uint32_t *character)
{
    if (!text || cursor <= 0)
        return false;
    size_t offset = 0;
    for (int index = 0; index < cursor; ++index)
    {
        utf8proc_int32_t codepoint;
        utf8proc_ssize_t length = utf8proc_iterate((const unsigned char *)text + offset,
                                                  -1, &codepoint);
        if (length <= 0 || !codepoint)
            return false;
        *last = offset;
        *character = codepoint;
        offset += length;
    }
    *end = offset;
    return true;
}

uint32_t accessibility_typing_character_before(const char *text, int cursor)
{
    size_t last, end;
    uint32_t character;
    return typing_echo_position(text, cursor, &last, &end, &character) ? character : 0;
}

static void typing_echo_word(const char *text, size_t end, bool enqueue)
{
    size_t start = 0, offset = 0;
    while (offset < end)
    {
        utf8proc_int32_t character;
        utf8proc_ssize_t length = utf8proc_iterate((const unsigned char *)text + offset,
                                                  end - offset, &character);
        if (length <= 0)
            return;
        offset += length;
        if (!typing_word_character(character))
            start = offset;
    }
    if (start == end)
        return;
    char word[256];
    while (start < end)
    {
        size_t count = end - start;
        if (count >= sizeof(word))
        {
            count = sizeof(word) - 1;
            while (((unsigned char)text[start + count] & 0xc0) == 0x80)
                --count;
        }
        memcpy(word, text + start, count);
        word[count] = '\0';
        if (talk_spell(word, enqueue) < 0)
            return;
        enqueue = true;
        start += count;
    }
}

bool accessibility_typing_echo_inserted(const char *text, int cursor)
{
    accessibility_typing_get_echo_settings(NULL);
    if (!talk_menus_enabled(&global_settings))
        return false;
    size_t last, end;
    uint32_t character;
    if (!typing_echo_position(text, cursor, &last, &end, &character))
        return false;
    bool characters = (echo_settings.echo & ACCESSIBILITY_ECHO_CHARACTERS) != 0;
    bool words = (echo_settings.echo & ACCESSIBILITY_ECHO_WORDS) != 0;
    if (characters)
        accessibility_typing_speak_character(character, false);
    if (words && !typing_word_character(character))
        typing_echo_word(text, last, characters);
    return words && typing_word_character(character);
}

void accessibility_typing_echo_deleted(uint32_t character)
{
    accessibility_typing_get_echo_settings(NULL);
    if (!character || character > 0x10ffff ||
        (character >= 0xd800 && character <= 0xdfff) ||
        !talk_menus_enabled(&global_settings) ||
        echo_settings.deletion == ACCESSIBILITY_DELETION_NONE)
        return;
    bool enqueue = echo_settings.deletion == ACCESSIBILITY_DELETION_ANNOUNCE;
    if (enqueue && talk_id(LANG_ACCESSIBILITY_DELETED, false) < 0)
        return;
    accessibility_typing_speak_character(character, enqueue);
}

void accessibility_typing_echo_finish(const char *text, int cursor)
{
    accessibility_typing_get_echo_settings(NULL);
    if (!talk_menus_enabled(&global_settings) ||
        !(echo_settings.echo & ACCESSIBILITY_ECHO_WORDS))
        return;
    size_t last, end;
    uint32_t character;
    if (typing_echo_position(text, cursor, &last, &end, &character) &&
        typing_word_character(character))
        typing_echo_word(text, end, false);
}

void accessibility_typing_begin(void)
{
    accessibility_typing_mode();
    accessibility_typing_cancel_touch();
    session_active = true;
}

void accessibility_typing_end(void)
{
    session_active = false;
    accessibility_typing_cancel_touch();
}

bool accessibility_typing_active(void)
{
    return session_active;
}

bool accessibility_typing_needs_poll(void)
{
    return session_active && selected_mode == ACCESSIBILITY_TYPING_DOUBLE_TAP &&
        touch.down && !touch.discard && !touch.exploring;
}

int accessibility_typing_handle_touch(const struct touchevent *event, int context)
{
    unsigned int base = (unsigned int)context & ~(CONTEXT_REMOTE | CONTEXT_CUSTOM |
        CONTEXT_CUSTOM2 | CONTEXT_LOCKED | ALLOW_SOFTLOCK);
    if (!session_active || base != CONTEXT_KEYBOARD || (context & CONTEXT_LOCKED))
    {
        accessibility_typing_cancel_touch();
        return ACTION_NONE;
    }
    if (raw_pending)
        accessibility_typing_cancel_touch();
    if (event)
        raw_event = *event;
    else
        raw_event = (struct touchevent){ .type = TOUCHEVENT_NONE, .tick = current_tick };
    if (raw_event.type < TOUCHEVENT_NONE || raw_event.type > TOUCHEVENT_RELEASE)
    {
        accessibility_typing_cancel_touch();
        return ACTION_NONE;
    }
    raw_pending = true;
    return ACTION_TOUCHSCREEN;
}

bool accessibility_typing_take_touch(struct touchevent *event)
{
    if (!event || !session_active || !raw_pending)
        return false;
    *event = raw_event;
    raw_pending = false;
    return true;
}

static bool typing_valid_target(int target)
{
    return target >= ACCESSIBILITY_TYPING_CURSOR_RIGHT &&
        target != ACCESSIBILITY_TYPING_NO_TARGET;
}

static bool typing_moved(int point_x, int point_y, int distance)
{
    return (int64_t)point_x - touch.start_x > distance ||
        (int64_t)touch.start_x - point_x > distance ||
        (int64_t)point_y - touch.start_y > distance ||
        (int64_t)touch.start_y - point_y > distance;
}

struct accessibility_typing_result accessibility_typing_process(
    enum accessibility_typing_input input, int target, int point_x, int point_y,
    uint32_t now_ms)
{
    struct accessibility_typing_result result = {
        .focus = touch.focus, .commit = ACCESSIBILITY_TYPING_NO_TARGET
    };
    if (!session_active || accessibility_typing_mode() == ACCESSIBILITY_TYPING_ARROWS)
        return result;
    if (touch.have_time && now_ms - touch.last_ms > INT32_MAX)
    {
        accessibility_typing_cancel_touch();
        result.focus = touch.focus;
    }
    touch.have_time = true;
    touch.last_ms = now_ms;
    if (touch.pending_tap && now_ms - touch.tap_ms > TYPING_DOUBLE_MS)
        touch.pending_tap = false;
    if (input == ACCESSIBILITY_TYPING_PRESS)
    {
        if (touch.down)
        {
            accessibility_typing_cancel_touch();
            touch.have_time = true;
            touch.last_ms = now_ms;
        }
        touch.down = true;
        touch.discard = !typing_valid_target(target);
        touch.exploring = false;
        touch.moved = false;
        touch.start_x = point_x;
        touch.start_y = point_y;
        touch.press_ms = now_ms;
        touch.target = target;
        if (!touch.discard && (selected_mode == ACCESSIBILITY_TYPING_LIFT ||
                              !typing_valid_target(touch.focus)))
        {
            touch.focus = target;
            result.speak = true;
        }
    }
    else if (input == ACCESSIBILITY_TYPING_CONTACT ||
             input == ACCESSIBILITY_TYPING_RELEASE || input == ACCESSIBILITY_TYPING_POLL)
    {
        if (!touch.down)
            return result;
        uint32_t duration = now_ms - touch.press_ms;
        if (input != ACCESSIBILITY_TYPING_POLL)
        {
            if (target != touch.target)
                touch.moved = true;
            touch.target = target;
            if (!typing_valid_target(target))
                touch.discard = true;
            if (typing_moved(point_x, point_y,
                             accessibility_touch_distance(TYPING_TAP_SLOP)))
                touch.moved = true;
        }
        if (touch.discard)
        {
            touch.pending_tap = false;
        }
        else
        {
            if (touch.moved || duration >= TYPING_EXPLORE_MS)
            {
                touch.exploring = true;
                touch.pending_tap = false;
            }
            if ((selected_mode == ACCESSIBILITY_TYPING_LIFT || touch.exploring) &&
                touch.focus != touch.target)
            {
                touch.focus = touch.target;
                result.speak = true;
            }
            if (input == ACCESSIBILITY_TYPING_RELEASE)
            {
                if (selected_mode == ACCESSIBILITY_TYPING_LIFT)
                    result.commit = touch.focus;
                else if (selected_mode == ACCESSIBILITY_TYPING_DOUBLE_TAP &&
                         !touch.moved && duration <= TYPING_TAP_MS)
                {
                    if (touch.pending_tap && touch.tap_target == touch.focus)
                    {
                        result.commit = touch.focus;
                        touch.pending_tap = false;
                    }
                    else
                    {
                        touch.pending_tap = true;
                        touch.tap_ms = now_ms;
                        touch.tap_target = touch.focus;
                    }
                }
                else
                    touch.pending_tap = false;
            }
        }
        if (input == ACCESSIBILITY_TYPING_RELEASE)
            touch.down = false;
    }
    else
        accessibility_typing_cancel_touch();
    result.focus = touch.focus;
    return result;
}

#else

enum accessibility_typing_mode accessibility_typing_mode(void)
{
    return ACCESSIBILITY_TYPING_LIFT;
}
bool accessibility_typing_set_mode(enum accessibility_typing_mode mode)
{
    (void)mode;
    return false;
}
int accessibility_typing_menu(void) { return 0; }
void accessibility_typing_get_echo_settings(struct accessibility_typing_echo_settings *settings)
{
    if (settings)
        *settings = (struct accessibility_typing_echo_settings){
            ACCESSIBILITY_ECHO_BOTH, ACCESSIBILITY_DELETION_ANNOUNCE,
            ACCESSIBILITY_CAPITALS_NONE, 20
        };
}
bool accessibility_typing_set_echo_settings(const struct accessibility_typing_echo_settings *settings)
{
    (void)settings;
    return false;
}
int accessibility_typing_echo_menu(void) { return 0; }
int accessibility_typing_deletion_menu(void) { return 0; }
int accessibility_typing_capitals_menu(void) { return 0; }
int accessibility_typing_capital_pitch_menu(void) { return 0; }
void accessibility_typing_speak_character(uint32_t character, bool enqueue)
{
    (void)character;
    (void)enqueue;
}
uint32_t accessibility_typing_character_before(const char *text, int cursor)
{
    (void)text;
    (void)cursor;
    return 0;
}
bool accessibility_typing_echo_inserted(const char *text, int cursor)
{
    (void)text;
    (void)cursor;
    return false;
}
void accessibility_typing_echo_deleted(uint32_t character) { (void)character; }
void accessibility_typing_echo_finish(const char *text, int cursor)
{
    (void)text;
    (void)cursor;
}
void accessibility_typing_begin(void) {}
void accessibility_typing_end(void) {}
bool accessibility_typing_active(void) { return false; }
bool accessibility_typing_needs_poll(void) { return false; }
void accessibility_typing_cancel_touch(void) {}
int accessibility_typing_handle_touch(const struct touchevent *event, int context)
{
    (void)event;
    (void)context;
    return 0;
}
bool accessibility_typing_take_touch(struct touchevent *event)
{
    (void)event;
    return false;
}
struct accessibility_typing_result accessibility_typing_process(
    enum accessibility_typing_input input, int target, int point_x, int point_y, uint32_t now_ms)
{
    (void)input;
    (void)target;
    (void)point_x;
    (void)point_y;
    (void)now_ms;
    return (struct accessibility_typing_result){
        .focus = ACCESSIBILITY_TYPING_NO_TARGET, .commit = ACCESSIBILITY_TYPING_NO_TARGET
    };
}

#endif
