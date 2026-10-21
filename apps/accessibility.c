#include "config.h"
#include "accessibility.h"
#include "action.h"

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "accessibility_gesture.h"
#include "accessibility_buttons.h"
#include "accessibility_screen.h"
#include "accessibility_shortcut.h"
#include "accessibility_services.h"
#include "accessibility_typing.h"
#include "accessibility_touch.h"
#include "backlight.h"
#include "button.h"
#include "file.h"
#include "kernel.h"
#include "lang.h"
#include "language.h"
#include "list.h"
#include "menu.h"
#include "misc.h"
#include "plugin.h"
#include "powermgmt.h"
#include "rbpaths.h"
#include "root_menu.h"
#include "settings.h"
#include "splash.h"
#include "talk.h"
#include "shortcuts.h"
#include "touchscreen.h"
#include "tts.h"
#include "tree.h"
#include "yesno.h"

#define ACCESSIBILITY_FILE ROCKBOX_DIR "/accessibility.cfg"
#define ACCESSIBILITY_TEMP ROCKBOX_DIR "/accessibility.cfg.tmp"
#define ACCESSIBILITY_HEADER "RBACCESSIBILITY:11\n"
#define ACCESSIBILITY_V10_HEADER "RBACCESSIBILITY:10\n"
#define ACCESSIBILITY_V9_HEADER "RBACCESSIBILITY:9\n"
#define ACCESSIBILITY_V8_HEADER "RBACCESSIBILITY:8\n"
#define ACCESSIBILITY_V7_HEADER "RBACCESSIBILITY:7\n"
#define ACCESSIBILITY_V6_HEADER "RBACCESSIBILITY:6\n"
#define ACCESSIBILITY_V5_HEADER "RBACCESSIBILITY:5\n"
#define ACCESSIBILITY_V4_HEADER "RBACCESSIBILITY:4\n"
#define ACCESSIBILITY_V3_HEADER "RBACCESSIBILITY:3\n"
#define ACCESSIBILITY_V2_HEADER "RBACCESSIBILITY:2\n"
#define ACCESSIBILITY_LEGACY_HEADER "RBACCESSIBILITY:1\n"
#define ACCESSIBILITY_CONFIG_MAX 4096u
#define ACCESSIBILITY_LAUNCH_PATHS 4
#define ACCESSIBILITY_LAUNCH_PLUGIN_BASE 4
#define ACCESSIBILITY_LAUNCH_PLUGIN_LAST (ACCESSIBILITY_LAUNCH_PLUGIN_BASE + ACCESSIBILITY_LAUNCH_PATHS - 1)
#define ACCESSIBILITY_LAUNCH_FILES 8u
#define ACCESSIBILITY_LAUNCH_DATABASE 9u
#define ACCESSIBILITY_LAUNCH_RESUME 10u
#define ACCESSIBILITY_LAUNCH_SETTINGS 11u
#define ACCESSIBILITY_LAUNCH_PLAYLISTS 12u
#define ACCESSIBILITY_LAUNCH_MAX ACCESSIBILITY_LAUNCH_PLAYLISTS
#define ACCESSIBILITY_TRIAL_TICKS (20 * HZ)
#define ACCESSIBILITY_DOUBLE_SLOT ACCESSIBILITY_STROKE_COUNT
#define ACCESSIBILITY_HOLD_SLOT (ACCESSIBILITY_STROKE_COUNT + 1)
#define ACCESSIBILITY_TRIPLE_SLOT (ACCESSIBILITY_STROKE_COUNT + 2)
#define ACCESSIBILITY_DOUBLE_HOLD_SLOT (ACCESSIBILITY_STROKE_COUNT + 3)
#define ACCESSIBILITY_SLOT_COUNT (ACCESSIBILITY_STROKE_COUNT + 4)
#define ACCESSIBILITY_LEGACY_SLOT_COUNT (ACCESSIBILITY_STROKE_COUNT + 2)
#define ACCESSIBILITY_TOUCH_HOLD_MIN 300u
#define ACCESSIBILITY_TOUCH_HOLD_MAX 2000u
#define ACCESSIBILITY_EMPTY_FILE ROCKBOX_DIR "/empty-feedback.cfg"
#define ACCESSIBILITY_EMPTY_TEMP ROCKBOX_DIR "/empty-feedback.cfg.tmp"
#define ACCESSIBILITY_EMPTY_HEADER "RBEMPTY-FEEDBACK:1\nmode:"

enum accessibility_action
{
    ACCESSIBILITY_ACTION_NONE,
    ACCESSIBILITY_ACTION_UP,
    ACCESSIBILITY_ACTION_DOWN,
    ACCESSIBILITY_ACTION_LEFT,
    ACCESSIBILITY_ACTION_RIGHT,
    ACCESSIBILITY_ACTION_OK,
    ACCESSIBILITY_ACTION_BACK,
    ACCESSIBILITY_ACTION_HOME,
    ACCESSIBILITY_ACTION_CONTEXT,
    ACCESSIBILITY_ACTION_VOLUP,
    ACCESSIBILITY_ACTION_VOLDOWN,
    ACCESSIBILITY_ACTION_BATTERY,
    ACCESSIBILITY_ACTION_LAUNCH,
    ACCESSIBILITY_ACTION_SHUTDOWN,
    ACCESSIBILITY_ACTION_LOCK,
    ACCESSIBILITY_ACTION_CURTAIN,
    ACCESSIBILITY_ACTION_TIME,
    ACCESSIBILITY_ACTION_TOGGLE_ESPEAK,
    ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES,
    ACCESSIBILITY_ACTION_TOGGLE_TOUCH,
    ACCESSIBILITY_ACTION_DATE,
    ACCESSIBILITY_ACTION_SUMMARY,
    ACCESSIBILITY_ACTION_FIRST,
    ACCESSIBILITY_ACTION_LAST,
    ACCESSIBILITY_ACTION_PAGE_FIRST,
    ACCESSIBILITY_ACTION_PAGE_LAST,
    ACCESSIBILITY_ACTION_SHORTCUT,
    ACCESSIBILITY_ACTION_COUNT,
    ACCESSIBILITY_ACTION_SYSTEM = ACCESSIBILITY_ACTION_COUNT
};

struct accessibility_config
{
    bool enabled;
    uint8_t click_sources;
    bool empty_pitch;
    int8_t empty_semitones;
    uint16_t hold_ms;
    uint16_t touch_hold_ms;
    bool stroke_repeat;
    uint8_t mapping[ACCESSIBILITY_SLOT_COUNT];
    uint8_t buttons[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT];
    uint8_t gesture_launch[ACCESSIBILITY_SLOT_COUNT];
    uint8_t playback_mapping[ACCESSIBILITY_SLOT_COUNT];
    uint8_t playback_gesture_launch[ACCESSIBILITY_SLOT_COUNT];
    uint8_t button_launch[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT];
    uint8_t playback_buttons[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT];
    uint8_t playback_launch[ACCESSIBILITY_BUTTON_COUNT][ACCESSIBILITY_BUTTON_SLOT_COUNT];
    char launch_paths[ACCESSIBILITY_LAUNCH_PATHS][MAX_PATH];
};

static struct accessibility_config active_config;
static struct accessibility_config saved_trial;
static struct accessibility_config edit_config;
static struct accessibility_config parse_config;
static char config_buffer[ACCESSIBILITY_CONFIG_MAX + 1];
static struct accessibility_gesture recognizer;
static struct accessibility_buttons button_recognizers[ACCESSIBILITY_BUTTON_COUNT];
static bool initialized;
static bool have_context;
static int active_context;
static bool point_pending;
static bool point_force;
static bool point_single_tap;
static bool feedback_pending;
static bool feedback_valid;
static const void *feedback_owner;
static int feedback_target;
static bool feedback_occupied;
static bool empty_speech_pending;
static bool empty_feedback_loaded;
static enum accessibility_empty_feedback empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
static bool exploring;
static int point_x;
static int point_y;
static bool trial_active;
static uint32_t trial_deadline;
static bool launch_pending;
static bool launch_running;
static bool physical_context_valid;
#ifdef HIBY_R1
static int physical_context;
static bool physical_locked;
static int physical_contact;
static int physical_blocked;
#endif
static bool physical_repeat;
static unsigned int pending_launch;
static char pending_launch_path[MAX_PATH];
static bool editing_launch;
#ifdef HIBY_R1
static int curtain_release_mask;
static bool curtain_wait_for_press;
#endif

static void accessibility_default_gestures(uint8_t *mapping)
{
    memset(mapping, 0, ACCESSIBILITY_SLOT_COUNT);
    mapping[ACCESSIBILITY_STROKE_LEFT] = ACCESSIBILITY_ACTION_UP;
    mapping[ACCESSIBILITY_STROKE_RIGHT] = ACCESSIBILITY_ACTION_DOWN;
    mapping[ACCESSIBILITY_STROKE_UP] = ACCESSIBILITY_ACTION_LEFT;
    mapping[ACCESSIBILITY_STROKE_DOWN] = ACCESSIBILITY_ACTION_RIGHT;
    mapping[ACCESSIBILITY_STROKE_LEFT_RIGHT] = ACCESSIBILITY_ACTION_BACK;
    mapping[ACCESSIBILITY_STROKE_RIGHT_LEFT] = ACCESSIBILITY_ACTION_HOME;
    mapping[ACCESSIBILITY_STROKE_UP_DOWN] = ACCESSIBILITY_ACTION_FIRST;
    mapping[ACCESSIBILITY_STROKE_DOWN_UP] = ACCESSIBILITY_ACTION_LAST;
    mapping[ACCESSIBILITY_DOUBLE_SLOT] = ACCESSIBILITY_ACTION_OK;
    mapping[ACCESSIBILITY_DOUBLE_HOLD_SLOT] = ACCESSIBILITY_ACTION_CONTEXT;
}

static void accessibility_defaults(struct accessibility_config *result)
{
    memset(result, 0, sizeof(*result));
    result->click_sources = KEYCLICK_SOURCE_ALL;
    result->empty_pitch = true;
    result->empty_semitones = -4;
    result->hold_ms = 700;
    result->touch_hold_ms = 900;
    memset(result->buttons, ACCESSIBILITY_ACTION_SYSTEM, sizeof(result->buttons));
    memset(result->playback_buttons, ACCESSIBILITY_ACTION_SYSTEM, sizeof(result->playback_buttons));
#ifdef HIBY_R1
    result->enabled = true;
    result->buttons[0][ACCESSIBILITY_BUTTON_TRIPLE] = ACCESSIBILITY_ACTION_SHORTCUT;
    result->playback_buttons[0][ACCESSIBILITY_BUTTON_TRIPLE] = ACCESSIBILITY_ACTION_SHORTCUT;
#endif
    accessibility_default_gestures(result->mapping);
    memcpy(result->playback_mapping, result->mapping, sizeof(result->playback_mapping));
}

static const int empty_feedback_labels[] = {
    LANG_ACCESSIBILITY_EMPTY_SOUND_ONLY,
    LANG_ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH,
    LANG_ACCESSIBILITY_EMPTY_SPEECH_ONLY
};

static void accessibility_empty_load(void)
{
    if (empty_feedback_loaded)
        return;
    empty_feedback_loaded = true;
    int descriptor = open(ACCESSIBILITY_EMPTY_FILE, O_RDONLY);
    if (descriptor < 0)
        return;
    char data[sizeof(ACCESSIBILITY_EMPTY_HEADER) + 2];
    size_t used = 0;
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
    const size_t prefix = sizeof(ACCESSIBILITY_EMPTY_HEADER) - 1;
    if (!valid || used != prefix + 2 ||
        memcmp(data, ACCESSIBILITY_EMPTY_HEADER, prefix) ||
        data[prefix] < '0' || data[prefix] > '2' || data[prefix + 1] != '\n')
        return;
    empty_feedback_mode = data[prefix] - '0';
}

static bool accessibility_empty_save(int mode)
{
    if (mode < ACCESSIBILITY_EMPTY_SOUND_ONLY || mode > ACCESSIBILITY_EMPTY_SPEECH_ONLY)
        return false;
    char data[] = ACCESSIBILITY_EMPTY_HEADER "0\n";
    data[sizeof(ACCESSIBILITY_EMPTY_HEADER) - 1] = '0' + mode;
    int descriptor = open(ACCESSIBILITY_EMPTY_TEMP, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (descriptor < 0)
        return false;
    size_t written = 0;
    bool valid = true;
    while (written < sizeof(data) - 1)
    {
        ssize_t count = write(descriptor, data + written, sizeof(data) - 1 - written);
        if (count <= 0)
        {
            valid = false;
            break;
        }
        written += count;
    }
    if (valid && fsync(descriptor) != 0)
        valid = false;
    if (close(descriptor) != 0)
        valid = false;
    if (!valid || rename(ACCESSIBILITY_EMPTY_TEMP, ACCESSIBILITY_EMPTY_FILE) != 0)
    {
        remove(ACCESSIBILITY_EMPTY_TEMP);
        return false;
    }
    empty_feedback_mode = mode;
    empty_feedback_loaded = true;
    empty_speech_pending = false;
    return true;
}

enum accessibility_empty_feedback accessibility_empty_feedback_mode(void)
{
    accessibility_empty_load();
    return empty_feedback_mode;
}

bool accessibility_empty_sound_enabled(void)
{
    return accessibility_empty_feedback_mode() != ACCESSIBILITY_EMPTY_SPEECH_ONLY;
}

bool accessibility_empty_speech_enabled(void)
{
    return accessibility_empty_feedback_mode() != ACCESSIBILITY_EMPTY_SOUND_ONLY;
}

int accessibility_empty_feedback_menu(void)
{
    struct opt_items options[ARRAYLEN(empty_feedback_labels)];
    for (unsigned int index = 0; index < ARRAYLEN(options); ++index)
        options[index] = (struct opt_items){
            (const unsigned char *)str(empty_feedback_labels[index]), empty_feedback_labels[index]
        };
    int choice = accessibility_empty_feedback_mode();
    if (set_option(str(LANG_ACCESSIBILITY_EMPTY_FEEDBACK), &choice, RB_INT,
                   options, ARRAYLEN(options), NULL))
        return MENU_ATTACHED_USB;
    if (choice != (int)empty_feedback_mode && !accessibility_empty_save(choice))
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
    return 0;
}

static bool parse_number(const char **cursor, const char *end,
                         unsigned int maximum, unsigned int *value)
{
    const char *start = *cursor;
    unsigned int result = 0;
    while (*cursor < end && **cursor >= '0' && **cursor <= '9')
    {
        unsigned int digit = (unsigned int)(**cursor - '0');
        if (result > maximum / 10 ||
            (result == maximum / 10 && digit > maximum % 10))
            return false;
        result = result * 10 + digit;
        ++*cursor;
    }
    if (*cursor == start || (*cursor - start > 1 && *start == '0'))
        return false;
    *value = result;
    return true;
}

static bool parse_literal(const char **cursor, const char *end, const char *text)
{
    size_t length = strlen(text);
    if ((size_t)(end - *cursor) < length || memcmp(*cursor, text, length))
        return false;
    *cursor += length;
    return true;
}

static bool accessibility_launch_path_valid(const char *path)
{
    const char *end = memchr(path, '\0', MAX_PATH);
    if (!end)
        return false;
    size_t length = end - path;
    if (!length)
        return true;
    const char *prefix = PLUGIN_DIR "/";
    size_t prefix_length = strlen(prefix);
    if (length <= prefix_length + 5 || strncmp(path, prefix, prefix_length) ||
        strcmp(end - 5, ".rock") || strstr(path, "/../") || strstr(path, "/./") ||
        strstr(path, "//"))
        return false;
    for (const char *cursor = path; cursor < end; ++cursor)
        if ((unsigned char)*cursor < 32 || *cursor == '\\' || (unsigned char)*cursor == 127)
            return false;
    return true;
}

static bool accessibility_plugin_target(unsigned int target)
{
    return target >= ACCESSIBILITY_LAUNCH_PLUGIN_BASE && target <= ACCESSIBILITY_LAUNCH_PLUGIN_LAST;
}

static bool accessibility_launch_valid(const struct accessibility_config *value)
{
    bool referenced[ACCESSIBILITY_LAUNCH_PATHS] = {false};
    for (unsigned int slot = 1; slot < ACCESSIBILITY_SLOT_COUNT; ++slot)
    {
        for (unsigned int profile = 0; profile < 2; ++profile)
        {
            unsigned int mapping = profile ? value->playback_mapping[slot] : value->mapping[slot];
            unsigned int target = profile ? value->playback_gesture_launch[slot] : value->gesture_launch[slot];
            if (mapping >= ACCESSIBILITY_ACTION_COUNT || target > ACCESSIBILITY_LAUNCH_MAX ||
                (target && mapping != ACCESSIBILITY_ACTION_LAUNCH))
                return false;
            if (accessibility_plugin_target(target))
                referenced[target - ACCESSIBILITY_LAUNCH_PLUGIN_BASE] = true;
        }
    }
    for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
    {
        for (unsigned int slot = 0; slot < ACCESSIBILITY_BUTTON_SLOT_COUNT; ++slot)
        {
            for (unsigned int profile = 0; profile < 2; ++profile)
            {
                unsigned int mapping = profile ? value->playback_buttons[button][slot] :
                    value->buttons[button][slot];
                unsigned int target = profile ? value->playback_launch[button][slot] :
                    value->button_launch[button][slot];
                if (mapping > ACCESSIBILITY_ACTION_SYSTEM || target > ACCESSIBILITY_LAUNCH_MAX ||
                    (target && mapping != ACCESSIBILITY_ACTION_LAUNCH))
                    return false;
                if (accessibility_plugin_target(target))
                    referenced[target - ACCESSIBILITY_LAUNCH_PLUGIN_BASE] = true;
            }
        }
    }
    for (unsigned int target = 0; target < ACCESSIBILITY_LAUNCH_PATHS; ++target)
        if (!accessibility_launch_path_valid(value->launch_paths[target]) ||
            (referenced[target] && !value->launch_paths[target][0]))
            return false;
    return true;
}

static bool accessibility_parse(const char *buffer, size_t length,
                                struct accessibility_config *result)
{
    struct accessibility_config *candidate = &parse_config;
    accessibility_defaults(candidate);
    const char *cursor = buffer;
    const char *end = buffer + length;
    unsigned int number;
    if (!length || length > ACCESSIBILITY_CONFIG_MAX)
        return false;
    bool legacy = parse_literal(&cursor, end, ACCESSIBILITY_LEGACY_HEADER);
    bool version2 = !legacy && parse_literal(&cursor, end, ACCESSIBILITY_V2_HEADER);
    bool version3 = !legacy && !version2 && parse_literal(&cursor, end, ACCESSIBILITY_V3_HEADER);
    bool version4 = !legacy && !version2 && !version3 &&
        parse_literal(&cursor, end, ACCESSIBILITY_V4_HEADER);
    bool version5 = !legacy && !version2 && !version3 && !version4 &&
        parse_literal(&cursor, end, ACCESSIBILITY_V5_HEADER);
    bool version6 = !legacy && !version2 && !version3 && !version4 && !version5 &&
        parse_literal(&cursor, end, ACCESSIBILITY_V6_HEADER);
    bool version7 = !legacy && !version2 && !version3 && !version4 && !version5 && !version6 &&
        parse_literal(&cursor, end, ACCESSIBILITY_V7_HEADER);
    bool bindings = !legacy && !version2;
    bool current = bindings && !version3 && !version4 && !version5 && !version6;
    bool version8 = current && !version7 &&
        parse_literal(&cursor, end, ACCESSIBILITY_V8_HEADER);
    bool version9 = current && !version7 && !version8 &&
        parse_literal(&cursor, end, ACCESSIBILITY_V9_HEADER);
    bool version10 = current && !version7 && !version8 && !version9 &&
        parse_literal(&cursor, end, ACCESSIBILITY_V10_HEADER);
    bool version11 = current && !version7 && !version8 && !version9 && !version10;
    bool exploration = version8 || version9 || version10 || version11;
    unsigned int system_action = current ? (version11 ? ACCESSIBILITY_ACTION_SYSTEM : 22u) :
        version6 ? 19u : version5 ? 17u : version4 ? ACCESSIBILITY_ACTION_TIME : ACCESSIBILITY_ACTION_CURTAIN;
    unsigned int slot_count = current ? ACCESSIBILITY_SLOT_COUNT : ACCESSIBILITY_LEGACY_SLOT_COUNT;
    unsigned int launch_max = current ? ACCESSIBILITY_LAUNCH_MAX : ACCESSIBILITY_LAUNCH_PLUGIN_LAST;
    if (!bindings)
    {
        memset(candidate->buttons, ACCESSIBILITY_ACTION_SYSTEM, sizeof(candidate->buttons));
        memset(candidate->playback_buttons, ACCESSIBILITY_ACTION_SYSTEM, sizeof(candidate->playback_buttons));
    }
    if ((version11 && !parse_literal(&cursor, end, ACCESSIBILITY_HEADER)) ||
        !parse_literal(&cursor, end, "enabled:") ||
        !parse_number(&cursor, end, 1, &number) ||
        !parse_literal(&cursor, end, "\n"))
        return false;
    candidate->enabled = number != 0;
    if (!legacy)
    {
        if (!parse_literal(&cursor, end, "click:") ||
            !parse_number(&cursor, end, exploration ? KEYCLICK_SOURCE_ALL : KEYCLICK_SOURCE_BOTH, &number) ||
            (!exploration && !number) ||
            !parse_literal(&cursor, end, "\n"))
            return false;
        candidate->click_sources = number;
        if (!parse_literal(&cursor, end, "hold:") ||
            !parse_number(&cursor, end, ACCESSIBILITY_BUTTON_HOLD_MAX, &number) ||
            number < ACCESSIBILITY_BUTTON_HOLD_MIN || number % 100 ||
            !parse_literal(&cursor, end, "\n"))
            return false;
        candidate->hold_ms = number;
    }
    if (current)
    {
        if (!parse_literal(&cursor, end, "touch_hold:") ||
            !parse_number(&cursor, end, ACCESSIBILITY_TOUCH_HOLD_MAX, &number) ||
            number < ACCESSIBILITY_TOUCH_HOLD_MIN || number % 100 ||
            !parse_literal(&cursor, end, "\n"))
            return false;
        candidate->touch_hold_ms = number;
        if (!parse_literal(&cursor, end, "stroke_repeat:") ||
            !parse_number(&cursor, end, 1, &number) ||
            !parse_literal(&cursor, end, "\n"))
            return false;
        candidate->stroke_repeat = number != 0;
    }
    if (exploration)
    {
        if (!parse_literal(&cursor, end, "empty_pitch:") ||
            !parse_number(&cursor, end, 1, &number) ||
            !parse_literal(&cursor, end, "\n"))
            return false;
        candidate->empty_pitch = number != 0;
        if (!parse_literal(&cursor, end, "empty_semitones:"))
            return false;
        bool negative = parse_literal(&cursor, end, "-");
        if (!parse_number(&cursor, end, 12, &number) || (negative && !number) ||
            !parse_literal(&cursor, end, "\n"))
            return false;
        candidate->empty_semitones = negative ? -(int)number : (int)number;
    }
    for (unsigned int slot = 1; slot < slot_count; ++slot)
    {
        if (!parse_literal(&cursor, end, "gesture:") ||
            !parse_number(&cursor, end, slot_count - 1, &number) ||
            number != slot || !parse_literal(&cursor, end, ":") ||
            !parse_number(&cursor, end, legacy ? 10 : system_action - 1, &number))
            return false;
        candidate->mapping[slot] = number;
        if (bindings)
        {
            if (!parse_literal(&cursor, end, ":") ||
                !parse_number(&cursor, end, launch_max, &number))
                return false;
            candidate->gesture_launch[slot] = number;
        }
        if (!parse_literal(&cursor, end, "\n"))
            return false;
    }
    if (version10 || version11)
    {
        for (unsigned int slot = 1; slot < ACCESSIBILITY_SLOT_COUNT; ++slot)
        {
            if (!parse_literal(&cursor, end, "playback_gesture:") ||
                !parse_number(&cursor, end, ACCESSIBILITY_SLOT_COUNT - 1, &number) ||
                number != slot || !parse_literal(&cursor, end, ":") ||
                !parse_number(&cursor, end, system_action - 1, &number))
                return false;
            candidate->playback_mapping[slot] = number;
            if (!parse_literal(&cursor, end, ":") ||
                !parse_number(&cursor, end, ACCESSIBILITY_LAUNCH_MAX, &number) ||
                !parse_literal(&cursor, end, "\n"))
                return false;
            candidate->playback_gesture_launch[slot] = number;
        }
    }
    else
    {
        memcpy(candidate->playback_mapping, candidate->mapping, sizeof(candidate->playback_mapping));
        memcpy(candidate->playback_gesture_launch, candidate->gesture_launch,
               sizeof(candidate->playback_gesture_launch));
    }
    if (!legacy)
    {
        for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
        {
            for (unsigned int slot = 0; slot < ACCESSIBILITY_BUTTON_SLOT_COUNT; ++slot)
            {
                if (!parse_literal(&cursor, end, "button:") ||
                    !parse_number(&cursor, end, ACCESSIBILITY_BUTTON_COUNT - 1, &number) ||
                    number != button || !parse_literal(&cursor, end, ":") ||
                    !parse_number(&cursor, end, ACCESSIBILITY_BUTTON_SLOT_COUNT - 1, &number) ||
                    number != slot || !parse_literal(&cursor, end, ":") ||
                    !parse_number(&cursor, end, system_action, &number))
                    return false;
                if (number == system_action)
                    number = ACCESSIBILITY_ACTION_SYSTEM;
                candidate->buttons[button][slot] = number;
                if (bindings && (!parse_literal(&cursor, end, ":") ||
                    !parse_number(&cursor, end, launch_max, &number)))
                    return false;
                if (bindings)
                    candidate->button_launch[button][slot] = number;
                if (!parse_literal(&cursor, end, "\n"))
                    return false;
            }
        }
        if (version9 || version10 || version11)
        {
            for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
            {
                for (unsigned int slot = 0; slot < ACCESSIBILITY_BUTTON_SLOT_COUNT; ++slot)
                {
                    if (!parse_literal(&cursor, end, "playback_button:") ||
                        !parse_number(&cursor, end, ACCESSIBILITY_BUTTON_COUNT - 1, &number) ||
                        number != button || !parse_literal(&cursor, end, ":") ||
                        !parse_number(&cursor, end, ACCESSIBILITY_BUTTON_SLOT_COUNT - 1, &number) ||
                        number != slot || !parse_literal(&cursor, end, ":") ||
                        !parse_number(&cursor, end, system_action, &number))
                        return false;
                    candidate->playback_buttons[button][slot] = number == system_action ?
                        ACCESSIBILITY_ACTION_SYSTEM : number;
                    if (!parse_literal(&cursor, end, ":") ||
                        !parse_number(&cursor, end, ACCESSIBILITY_LAUNCH_MAX, &number) ||
                        !parse_literal(&cursor, end, "\n"))
                        return false;
                    candidate->playback_launch[button][slot] = number;
                }
            }
        }
        for (unsigned int target = 0; bindings && target < ACCESSIBILITY_LAUNCH_PATHS; ++target)
        {
            if (!parse_literal(&cursor, end, "target:") ||
                !parse_number(&cursor, end, ACCESSIBILITY_LAUNCH_PATHS - 1, &number) ||
                number != target || !parse_literal(&cursor, end, ":"))
                return false;
            const char *start = cursor;
            while (cursor < end && *cursor != '\n')
                ++cursor;
            size_t path_length = cursor - start;
            if (cursor == end || path_length >= MAX_PATH || memchr(start, '\0', path_length))
                return false;
            memcpy(candidate->launch_paths[target], start, path_length);
            candidate->launch_paths[target][path_length] = '\0';
            ++cursor;
        }
    }
    if (!version9 && !version10 && !version11)
    {
        memcpy(candidate->playback_buttons, candidate->buttons, sizeof(candidate->playback_buttons));
        memcpy(candidate->playback_launch, candidate->button_launch, sizeof(candidate->playback_launch));
    }
    if (cursor != end || !accessibility_launch_valid(candidate))
        return false;
    *result = *candidate;
    return true;
}

static bool accessibility_load(struct accessibility_config *result)
{
    char *buffer = config_buffer;
    size_t used = 0;
    int descriptor = open(ACCESSIBILITY_FILE, O_RDONLY);
    if (descriptor < 0)
        return false;
    bool valid = true;
    while (used < sizeof(config_buffer))
    {
        ssize_t count = read(descriptor, buffer + used, sizeof(config_buffer) - used);
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
    return valid && accessibility_parse(buffer, used, result);
}

static bool accessibility_save(const struct accessibility_config *value)
{
    char *buffer = config_buffer;
    if (!accessibility_launch_valid(value) ||
        value->click_sources > KEYCLICK_SOURCE_ALL ||
        value->empty_semitones < -12 || value->empty_semitones > 12 ||
        value->hold_ms < ACCESSIBILITY_BUTTON_HOLD_MIN ||
        value->hold_ms > ACCESSIBILITY_BUTTON_HOLD_MAX || value->hold_ms % 100 ||
        value->touch_hold_ms < ACCESSIBILITY_TOUCH_HOLD_MIN ||
        value->touch_hold_ms > ACCESSIBILITY_TOUCH_HOLD_MAX || value->touch_hold_ms % 100)
        return false;
    int length = snprintf(buffer, ACCESSIBILITY_CONFIG_MAX, ACCESSIBILITY_HEADER
        "enabled:%u\nclick:%u\nhold:%u\ntouch_hold:%u\nstroke_repeat:%u\n"
        "empty_pitch:%u\nempty_semitones:%d\n", value->enabled ? 1u : 0u,
        (unsigned int)value->click_sources, (unsigned int)value->hold_ms,
        (unsigned int)value->touch_hold_ms, value->stroke_repeat ? 1u : 0u,
        value->empty_pitch ? 1u : 0u, (int)value->empty_semitones);
    if (length < 0 || (size_t)length >= ACCESSIBILITY_CONFIG_MAX)
        return false;
    for (unsigned int slot = 1; slot < ACCESSIBILITY_SLOT_COUNT; ++slot)
    {
        if (value->mapping[slot] >= ACCESSIBILITY_ACTION_COUNT)
            return false;
        int count = snprintf(buffer + length, ACCESSIBILITY_CONFIG_MAX - length,
            "gesture:%u:%u:%u\n", slot, (unsigned int)value->mapping[slot],
            (unsigned int)value->gesture_launch[slot]);
        if (count < 0 || (size_t)count >= ACCESSIBILITY_CONFIG_MAX - length)
            return false;
        length += count;
    }
    for (unsigned int slot = 1; slot < ACCESSIBILITY_SLOT_COUNT; ++slot)
    {
        int count = snprintf(buffer + length, ACCESSIBILITY_CONFIG_MAX - length,
            "playback_gesture:%u:%u:%u\n", slot, (unsigned int)value->playback_mapping[slot],
            (unsigned int)value->playback_gesture_launch[slot]);
        if (count < 0 || (size_t)count >= ACCESSIBILITY_CONFIG_MAX - length)
            return false;
        length += count;
    }
    for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
    {
        for (unsigned int slot = 0; slot < ACCESSIBILITY_BUTTON_SLOT_COUNT; ++slot)
        {
            if (value->buttons[button][slot] > ACCESSIBILITY_ACTION_SYSTEM)
                return false;
            int count = snprintf(buffer + length, ACCESSIBILITY_CONFIG_MAX - length,
                "button:%u:%u:%u:%u\n", button, slot, (unsigned int)value->buttons[button][slot],
                (unsigned int)value->button_launch[button][slot]);
            if (count < 0 || (size_t)count >= ACCESSIBILITY_CONFIG_MAX - length)
                return false;
            length += count;
        }
    }
    for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
    {
        for (unsigned int slot = 0; slot < ACCESSIBILITY_BUTTON_SLOT_COUNT; ++slot)
        {
            int count = snprintf(buffer + length, ACCESSIBILITY_CONFIG_MAX - length,
                "playback_button:%u:%u:%u:%u\n", button, slot,
                (unsigned int)value->playback_buttons[button][slot],
                (unsigned int)value->playback_launch[button][slot]);
            if (count < 0 || (size_t)count >= ACCESSIBILITY_CONFIG_MAX - length)
                return false;
            length += count;
        }
    }
    for (unsigned int target = 0; target < ACCESSIBILITY_LAUNCH_PATHS; ++target)
    {
        int count = snprintf(buffer + length, ACCESSIBILITY_CONFIG_MAX - length,
            "target:%u:%s\n", target, value->launch_paths[target]);
        if (count < 0 || (size_t)count >= ACCESSIBILITY_CONFIG_MAX - length)
            return false;
        length += count;
    }
    int descriptor = open(ACCESSIBILITY_TEMP, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (descriptor < 0)
        return false;
    bool valid = true;
    size_t used = 0;
    while (used < (size_t)length)
    {
        ssize_t count = write(descriptor, buffer + used, (size_t)length - used);
        if (count <= 0)
        {
            valid = false;
            break;
        }
        used += count;
    }
    if (valid && fsync(descriptor) != 0)
        valid = false;
    if (close(descriptor) != 0)
        valid = false;
    if (valid && rename(ACCESSIBILITY_TEMP, ACCESSIBILITY_FILE) == 0)
        return true;
    remove(ACCESSIBILITY_TEMP);
    return false;
}

void accessibility_cancel_touch(void)
{
    accessibility_typing_cancel_touch();
    accessibility_gesture_reset(&recognizer);
    point_pending = false;
    feedback_pending = false;
    feedback_valid = false;
    empty_speech_pending = false;
    exploring = false;
    have_context = false;
}

static bool accessibility_playback_context(int context)
{
    return ((unsigned int)context & ~(CONTEXT_REMOTE | CONTEXT_LOCKED | CONTEXT_REMAPPED)) == CONTEXT_WPS;
}

static const uint8_t *gesture_mappings(int context)
{
    return accessibility_playback_context(context) ? active_config.playback_mapping : active_config.mapping;
}

static const uint8_t *gesture_launches(int context)
{
    return accessibility_playback_context(context) ? active_config.playback_gesture_launch : active_config.gesture_launch;
}

static void accessibility_configure_touch(void)
{
    const uint8_t *mapping = gesture_mappings(have_context ? active_context : CONTEXT_STD);
    struct accessibility_gesture_config config = accessibility_gesture_default_config();
    config.tap_slop_px = accessibility_touch_distance(config.tap_slop_px);
    config.stroke_min_px = accessibility_touch_distance(config.stroke_min_px);
    if (config.stroke_min_px <= config.tap_slop_px)
        config.stroke_min_px = config.tap_slop_px + 1;
    config.triple_tap = true;
    if (mapping[ACCESSIBILITY_HOLD_SLOT] != ACCESSIBILITY_ACTION_NONE)
        config.long_hold_ms = active_config.touch_hold_ms;
    if (mapping[ACCESSIBILITY_DOUBLE_HOLD_SLOT] != ACCESSIBILITY_ACTION_NONE)
        config.double_tap_hold_ms = active_config.touch_hold_ms;
    if (active_config.stroke_repeat)
        config.stroke_hold_ms = active_config.touch_hold_ms;
    accessibility_gesture_init(&recognizer, &config);
}

static void accessibility_configure_recognizers(void)
{
    accessibility_configure_touch();
    for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
        accessibility_buttons_init(&button_recognizers[button], active_config.hold_ms);
}

static void accessibility_cancel_buttons(void)
{
    for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
        accessibility_buttons_reset(&button_recognizers[button]);
#ifdef HIBY_R1
    physical_blocked |= physical_contact;
#endif
}

static bool accessibility_buttons_waiting(void)
{
    for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
        if (accessibility_buttons_pending(&button_recognizers[button]))
            return true;
    return false;
}

void accessibility_reset(void)
{
    accessibility_cancel_touch();
    accessibility_cancel_buttons();
    if (initialized)
        accessibility_configure_recognizers();
    physical_context_valid = false;
    launch_pending = false;
}

static void accessibility_apply(void)
{
    accessibility_reset();
    touchscreen_set_mode(active_config.enabled ? TOUCHSCREEN_POINT :
                          global_settings.touch_mode);
}

static void accessibility_rollback(void)
{
    active_config = saved_trial;
    trial_active = false;
    accessibility_apply();
}

static void accessibility_check_trial(void)
{
    if (trial_active && (uint32_t)((uint32_t)current_tick - trial_deadline) < UINT32_C(0x80000000))
        accessibility_rollback();
}

void accessibility_init(void)
{
    if (!initialized)
    {
        accessibility_defaults(&active_config);
        if (accessibility_load(&edit_config))
            active_config = edit_config;
        initialized = true;
    }
    accessibility_check_trial();
    accessibility_apply();
}

bool accessibility_enabled(void)
{
    accessibility_check_trial();
    bool enabled = initialized && active_config.enabled;
    if (enabled && touchscreen_get_mode() != TOUCHSCREEN_POINT)
        touchscreen_set_mode(TOUCHSCREEN_POINT);
    return enabled;
}

int accessibility_adjust_timeout(int requested_timeout)
{
    if (backlight_screen_curtain_active() && !tts_is_available())
        backlight_set_screen_curtain(false);
    bool enabled = accessibility_enabled();
    int interval = HZ / 20;
    if (interval < 1)
        interval = 1;
    if (trial_active || launch_pending || root_menu_navigation_pending() ||
        accessibility_buttons_waiting() ||
        (enabled && accessibility_gesture_pending(&recognizer)))
    {
        if (requested_timeout < 0 || requested_timeout > interval)
            return interval;
    }
    return requested_timeout;
}

void accessibility_set_target(const void *target)
{
    (void)target;
    accessibility_reset();
}

static void accessibility_queue_launch(unsigned int target)
{
    if (trial_active || launch_running || editing_launch || target > ACCESSIBILITY_LAUNCH_MAX)
        return;
    pending_launch = target;
    pending_launch_path[0] = '\0';
    if (accessibility_plugin_target(target))
    {
        const char *path = active_config.launch_paths[target - ACCESSIBILITY_LAUNCH_PLUGIN_BASE];
        if (!path[0] || !accessibility_launch_path_valid(path))
            return;
        memcpy(pending_launch_path, path, strlen(path) + 1);
    }
    launch_pending = true;
}

static void accessibility_toggle_touch(void)
{
    if (trial_active || editing_launch || launch_running)
        return;
    edit_config = active_config;
    edit_config.enabled = !edit_config.enabled;
    if (!accessibility_save(&edit_config))
    {
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
        return;
    }
    active_config = edit_config;
    accessibility_apply();
    talk_id(LANG_ACCESSIBILITY_ENABLED, false);
    talk_id(active_config.enabled ? LANG_ON : LANG_OFF, true);
}

bool accessibility_set_enabled(bool enabled)
{
    if (trial_active || editing_launch || launch_running)
        return false;
    if (!initialized)
        accessibility_init();
    if (active_config.enabled == enabled)
        return true;
    edit_config = active_config;
    edit_config.enabled = enabled;
    if (!accessibility_save(&edit_config))
        return false;
    active_config = edit_config;
    accessibility_apply();
    return true;
}

static int accessibility_action_for(enum accessibility_action action, int context)
{
    unsigned int base = (unsigned int)context & ~(CONTEXT_REMOTE | CONTEXT_CUSTOM |
        CONTEXT_CUSTOM2 | CONTEXT_LOCKED | CONTEXT_REMAPPED);
    bool reader = (context & (CONTEXT_CUSTOM | CONTEXT_CUSTOM2)) ==
        (CONTEXT_CUSTOM | CONTEXT_CUSTOM2) && base == CONTEXT_STD;
    if (action == ACCESSIBILITY_ACTION_NONE)
        return ACTION_NONE;
    if ((trial_active || editing_launch || launch_running) &&
        (action == ACCESSIBILITY_ACTION_SHORTCUT || action == ACCESSIBILITY_ACTION_TOGGLE_ESPEAK ||
         action == ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES || action == ACCESSIBILITY_ACTION_SHUTDOWN))
        return ACTION_NONE;
    if (action == ACCESSIBILITY_ACTION_SHORTCUT)
    {
        accessibility_services_activate();
        return ACTION_NONE;
    }
    if (action >= ACCESSIBILITY_ACTION_FIRST && action <= ACCESSIBILITY_ACTION_PAGE_LAST)
    {
        if (reader || (base != CONTEXT_STD && base != CONTEXT_LIST && base != CONTEXT_TREE &&
            base != CONTEXT_MAINMENU && base != CONTEXT_SETTINGS && base != CONTEXT_BOOKMARKSCREEN))
            return ACTION_NONE;
        static const int endpoints[] = {ACTION_LIST_FIRST, ACTION_LIST_LAST,
            ACTION_LIST_PAGE_FIRST, ACTION_LIST_PAGE_LAST};
        return endpoints[action - ACCESSIBILITY_ACTION_FIRST];
    }
    if (action == ACCESSIBILITY_ACTION_TOGGLE_TOUCH)
    {
        accessibility_toggle_touch();
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_DATE)
    {
        accessibility_speak_date(false);
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_SUMMARY)
    {
        accessibility_speak_summary(false);
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_TOGGLE_ESPEAK)
    {
        accessibility_shortcut_toggle_espeak();
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES)
    {
        accessibility_shortcut_toggle_voice_files();
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_CURTAIN)
    {
        accessibility_set_curtain(!backlight_screen_curtain_active());
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_TIME)
    {
        accessibility_speak_time(false);
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_BATTERY)
    {
        accessibility_speak_battery(false);
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_LAUNCH)
    {
        accessibility_queue_launch(0);
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_SHUTDOWN)
    {
        sys_poweroff();
        return ACTION_NONE;
    }
    if (action == ACCESSIBILITY_ACTION_LOCK)
        return ACTION_STD_KEYLOCK;
    if (action == ACCESSIBILITY_ACTION_VOLUP || action == ACCESSIBILITY_ACTION_VOLDOWN)
    {
        adjust_volume(action == ACCESSIBILITY_ACTION_VOLUP ? 1 : -1);
        return ACTION_NONE;
    }
    if (reader)
    {
        switch (action)
        {
            case ACCESSIBILITY_ACTION_UP: return ACTION_SETTINGS_DEC;
            case ACCESSIBILITY_ACTION_DOWN: return ACTION_SETTINGS_INC;
            case ACCESSIBILITY_ACTION_LEFT: return ACTION_STD_PREV;
            case ACCESSIBILITY_ACTION_RIGHT: return ACTION_STD_NEXT;
            default: break;
        }
    }
    else if (base == CONTEXT_WPS)
    {
        switch (action)
        {
            case ACCESSIBILITY_ACTION_UP: return ACTION_WPS_VOLUP;
            case ACCESSIBILITY_ACTION_DOWN: return ACTION_WPS_VOLDOWN;
            case ACCESSIBILITY_ACTION_LEFT: return ACTION_WPS_SKIPPREV;
            case ACCESSIBILITY_ACTION_RIGHT: return ACTION_WPS_SKIPNEXT;
            case ACCESSIBILITY_ACTION_OK: return ACTION_WPS_PLAY;
            case ACCESSIBILITY_ACTION_BACK: return ACTION_WPS_BROWSE;
            case ACCESSIBILITY_ACTION_HOME: return ACTION_WPS_MENU;
            case ACCESSIBILITY_ACTION_CONTEXT: return ACTION_WPS_CONTEXT;
            default: break;
        }
    }
    else if (base == CONTEXT_KEYBOARD || base == CONTEXT_MORSE_INPUT)
    {
        switch (action)
        {
            case ACCESSIBILITY_ACTION_UP: return ACTION_KBD_UP;
            case ACCESSIBILITY_ACTION_DOWN: return ACTION_KBD_DOWN;
            case ACCESSIBILITY_ACTION_LEFT: return ACTION_KBD_LEFT;
            case ACCESSIBILITY_ACTION_RIGHT: return ACTION_KBD_RIGHT;
            case ACCESSIBILITY_ACTION_OK: return ACTION_KBD_SELECT;
            case ACCESSIBILITY_ACTION_BACK: return ACTION_KBD_ABORT;
            case ACCESSIBILITY_ACTION_HOME: return ACTION_KBD_DONE;
            case ACCESSIBILITY_ACTION_CONTEXT: return ACTION_KBD_BACKSPACE;
            default: break;
        }
    }
    else if (base == CONTEXT_SETTINGS || base == CONTEXT_SETTINGS_EQ ||
             base == CONTEXT_SETTINGS_COLOURCHOOSER || base == CONTEXT_SETTINGS_TIME ||
             base == CONTEXT_SETTINGS_RECTRIGGER)
    {
        switch (action)
        {
            case ACCESSIBILITY_ACTION_UP: return ACTION_SETTINGS_INC;
            case ACCESSIBILITY_ACTION_DOWN: return ACTION_SETTINGS_DEC;
            case ACCESSIBILITY_ACTION_LEFT: return ACTION_STD_PREV;
            case ACCESSIBILITY_ACTION_RIGHT: return ACTION_STD_NEXT;
            default: break;
        }
    }
    else if (base == CONTEXT_YESNOSCREEN)
    {
        return action == ACCESSIBILITY_ACTION_OK ? ACTION_YESNO_ACCEPT : ACTION_STD_CANCEL;
    }
    else if (base == CONTEXT_QUICKSCREEN)
    {
        switch (action)
        {
            case ACCESSIBILITY_ACTION_UP: return ACTION_QS_TOP;
            case ACCESSIBILITY_ACTION_DOWN: return ACTION_QS_DOWN;
            case ACCESSIBILITY_ACTION_LEFT: return ACTION_QS_LEFT;
            case ACCESSIBILITY_ACTION_RIGHT: return ACTION_QS_RIGHT;
            default: break;
        }
    }
    switch (action)
    {
        case ACCESSIBILITY_ACTION_UP: return ACTION_STD_PREV;
        case ACCESSIBILITY_ACTION_DOWN: return ACTION_STD_NEXT;
        case ACCESSIBILITY_ACTION_LEFT: return ACTION_STD_CANCEL;
        case ACCESSIBILITY_ACTION_RIGHT: return ACTION_STD_OK;
        case ACCESSIBILITY_ACTION_OK: return ACTION_STD_OK;
        case ACCESSIBILITY_ACTION_BACK: return ACTION_STD_CANCEL;
        case ACCESSIBILITY_ACTION_HOME: return ACTION_STD_MENU;
        case ACCESSIBILITY_ACTION_CONTEXT: return ACTION_STD_CONTEXT;
        default: return ACTION_NONE;
    }
}

static bool accessibility_repeat_safe(enum accessibility_action action, int context)
{
    if (context & (CONTEXT_PLUGIN | CONTEXT_LOCKED))
        return false;
    if (action == ACCESSIBILITY_ACTION_VOLUP || action == ACCESSIBILITY_ACTION_VOLDOWN)
        return true;
    if (action < ACCESSIBILITY_ACTION_UP || action > ACCESSIBILITY_ACTION_RIGHT)
        return false;
    unsigned int base = (unsigned int)context & ~(CONTEXT_REMOTE | CONTEXT_CUSTOM |
        CONTEXT_CUSTOM2 | CONTEXT_LOCKED | CONTEXT_REMAPPED);
    bool reader = (context & (CONTEXT_CUSTOM | CONTEXT_CUSTOM2)) ==
        (CONTEXT_CUSTOM | CONTEXT_CUSTOM2) && base == CONTEXT_STD;
    if (reader)
        return true;
    if (context & (CONTEXT_CUSTOM | CONTEXT_CUSTOM2))
        return false;
    if (base == CONTEXT_WPS)
        return action == ACCESSIBILITY_ACTION_UP || action == ACCESSIBILITY_ACTION_DOWN;
    if (base == CONTEXT_STD || base == CONTEXT_TREE || base == CONTEXT_MAINMENU ||
        base == CONTEXT_LIST || base == CONTEXT_ID3DB)
        return action == ACCESSIBILITY_ACTION_UP || action == ACCESSIBILITY_ACTION_DOWN;
    return base == CONTEXT_SETTINGS_EQ || base == CONTEXT_SETTINGS_COLOURCHOOSER ||
        base == CONTEXT_SETTINGS_TIME;
}

static int accessibility_repeat_result(int action, bool repeat, int context)
{
    if (!repeat)
        return action;
    unsigned int base = (unsigned int)context & ~(CONTEXT_REMOTE | CONTEXT_CUSTOM |
        CONTEXT_CUSTOM2 | CONTEXT_LOCKED | CONTEXT_REMAPPED);
    if (base == CONTEXT_SETTINGS_TIME &&
        (action == ACTION_STD_PREV || action == ACTION_STD_NEXT))
        return action;
    switch (action)
    {
        case ACTION_STD_PREV: return ACTION_STD_PREVREPEAT;
        case ACTION_STD_NEXT: return ACTION_STD_NEXTREPEAT;
        case ACTION_SETTINGS_INC: return ACTION_SETTINGS_INCREPEAT;
        case ACTION_SETTINGS_DEC: return ACTION_SETTINGS_DECREPEAT;
        default: return action;
    }
}

static uint32_t accessibility_repeat_mask(int context)
{
    if (!active_config.stroke_repeat)
        return 0;
    uint32_t mask = 0;
    for (unsigned int stroke = 1; stroke < ACCESSIBILITY_STROKE_COUNT; ++stroke)
        if (accessibility_repeat_safe(gesture_mappings(context)[stroke], context))
            mask |= UINT32_C(1) << stroke;
    return mask;
}

static int accessibility_gesture_action_for(enum accessibility_action action, int context,
                                             unsigned int slot)
{
    if (context & (CONTEXT_PLUGIN | CONTEXT_LOCKED))
        return ACTION_NONE;
    if (slot == ACCESSIBILITY_DOUBLE_HOLD_SLOT && action == ACCESSIBILITY_ACTION_CONTEXT)
    {
        unsigned int base = (unsigned int)context & ~(CONTEXT_REMOTE | CONTEXT_CUSTOM |
            CONTEXT_CUSTOM2 | CONTEXT_LOCKED | CONTEXT_REMAPPED);
        bool reader = (context & (CONTEXT_CUSTOM | CONTEXT_CUSTOM2)) ==
            (CONTEXT_CUSTOM | CONTEXT_CUSTOM2) && base == CONTEXT_STD;
#if CONFIG_TUNER
        if (base == CONTEXT_FM)
            return ACTION_FM_MENU;
#endif
        if (!reader && ((context & (CONTEXT_CUSTOM | CONTEXT_CUSTOM2)) ||
            (base != CONTEXT_STD && base != CONTEXT_TREE && base != CONTEXT_MAINMENU &&
             base != CONTEXT_LIST && base != CONTEXT_ID3DB && base != CONTEXT_WPS)))
            return ACTION_NONE;
    }
    return accessibility_action_for(action, context);
}

static uint32_t accessibility_milliseconds(long tick)
{
#if 1000 % HZ == 0
    return (uint32_t)tick * (1000 / HZ);
#else
    return (uint32_t)((uint64_t)(uint32_t)tick * 1000 / HZ);
#endif
}

#ifdef HIBY_R1
static const int physical_buttons[ACCESSIBILITY_BUTTON_COUNT] = {
    BUTTON_POWER, BUTTON_PLAY, BUTTON_NEXT, BUTTON_VOL_UP, BUTTON_VOL_DOWN
};

static const uint8_t (*physical_mappings(int context))[ACCESSIBILITY_BUTTON_SLOT_COUNT]
{
    return (const uint8_t (*)[ACCESSIBILITY_BUTTON_SLOT_COUNT])
        (accessibility_playback_context(context) ? active_config.playback_buttons : active_config.buttons);
}

static bool physical_override(unsigned int button, int context)
{
    const uint8_t (*mapping)[ACCESSIBILITY_BUTTON_SLOT_COUNT] = physical_mappings(context);
    for (unsigned int slot = 0; slot < ACCESSIBILITY_BUTTON_SLOT_COUNT; ++slot)
        if (mapping[button][slot] != ACCESSIBILITY_ACTION_SYSTEM)
            return true;
    return false;
}

static int physical_action(const struct accessibility_button_event *event,
                           int context, bool locked)
{
    unsigned int mapping = physical_mappings(context)[event->button][event->slot];
    int raw = physical_buttons[event->button];
    if (mapping == ACCESSIBILITY_ACTION_NONE &&
        (event->slot == ACCESSIBILITY_BUTTON_DOUBLE || event->slot == ACCESSIBILITY_BUTTON_TRIPLE))
        return ACTION_NONE;
    bool volume_button = raw == BUTTON_VOL_UP || raw == BUTTON_VOL_DOWN;
    if (locked && mapping != ACCESSIBILITY_ACTION_LOCK &&
        mapping != ACCESSIBILITY_ACTION_SHORTCUT &&
        mapping != ACCESSIBILITY_ACTION_VOLUP && mapping != ACCESSIBILITY_ACTION_VOLDOWN &&
        !(volume_button && (mapping == ACCESSIBILITY_ACTION_NONE || mapping == ACCESSIBILITY_ACTION_SYSTEM)))
        return ACTION_UNKNOWN;
    if (event->repeat && mapping != ACCESSIBILITY_ACTION_SYSTEM &&
        mapping != ACCESSIBILITY_ACTION_NONE && !accessibility_repeat_safe(mapping, context))
        return ACTION_UNKNOWN;
    if (mapping == ACCESSIBILITY_ACTION_LAUNCH)
    {
        accessibility_queue_launch(accessibility_playback_context(context) ?
            active_config.playback_launch[event->button][event->slot] :
            active_config.button_launch[event->button][event->slot]);
        return ACTION_NONE;
    }
    if (mapping == ACCESSIBILITY_ACTION_VOLUP ||
        (mapping == ACCESSIBILITY_ACTION_NONE && raw == BUTTON_VOL_UP))
        return accessibility_playback_context(context) ? ACTION_WPS_VOLUP : ACTION_LIST_VOLUP;
    if (mapping == ACCESSIBILITY_ACTION_VOLDOWN ||
        (mapping == ACCESSIBILITY_ACTION_NONE && raw == BUTTON_VOL_DOWN))
        return accessibility_playback_context(context) ? ACTION_WPS_VOLDOWN : ACTION_LIST_VOLDOWN;
    if (mapping == ACCESSIBILITY_ACTION_NONE || mapping == ACCESSIBILITY_ACTION_SYSTEM)
        return accessibility_default_button_action(raw |
            (event->slot == ACCESSIBILITY_BUTTON_HOLD ? BUTTON_REPEAT : BUTTON_REL),
            context, event->repeat);
    return accessibility_repeat_result(accessibility_action_for(mapping, context), event->repeat, context);
}
#endif

bool accessibility_handle_button(int button, int context, bool locked, int *action)
{
    if (button != BUTTON_NONE && !(button & SYS_EVENT))
        root_menu_cancel_navigation();
    if (!action)
        return false;
    *action = ACTION_UNKNOWN;
    physical_repeat = false;
#ifdef HIBY_R1
    accessibility_check_trial();
    if (!initialized || (context & CONTEXT_PLUGIN))
    {
        accessibility_cancel_buttons();
        physical_context_valid = false;
        return false;
    }
    if (!physical_context_valid || physical_context != context || physical_locked != locked)
    {
        accessibility_cancel_buttons();
        physical_context = context;
        physical_locked = locked;
        physical_context_valid = true;
    }
    uint32_t now = accessibility_milliseconds(current_tick);
    struct accessibility_button_event event = {0};
    if (button == BUTTON_NONE)
    {
        for (unsigned int selected = 0; selected < ACCESSIBILITY_BUTTON_COUNT; ++selected)
        {
            event = accessibility_buttons_process(&button_recognizers[selected],
                ACCESSIBILITY_BUTTON_POLL, selected, 1, now);
            if (event.recognized)
                break;
        }
        if (!event.recognized)
            return false;
    }
    else
    {
        int raw = button & ~(BUTTON_REL | BUTTON_REPEAT);
        if (button & BUTTON_REL)
            physical_contact &= ~raw;
        else if (!(button & BUTTON_REPEAT))
            physical_contact |= raw & BUTTON_MAIN;
        if (raw & physical_blocked)
        {
            if (button & (BUTTON_REL | BUTTON_REPEAT))
            {
                if (button & BUTTON_REL)
                    physical_blocked &= ~raw;
                return true;
            }
            physical_blocked &= ~raw;
        }
        unsigned int selected;
        for (selected = 0; selected < ACCESSIBILITY_BUTTON_COUNT; ++selected)
            if (raw == physical_buttons[selected])
                break;
        if (selected == ACCESSIBILITY_BUTTON_COUNT)
        {
            for (unsigned int index = 0; index < ACCESSIBILITY_BUTTON_COUNT; ++index)
                accessibility_buttons_process(&button_recognizers[index],
                    ACCESSIBILITY_BUTTON_CANCEL, 0, 1, now);
            return false;
        }
        if (!physical_override(selected, context))
            return false;
        struct accessibility_buttons *state = &button_recognizers[selected];
        const uint8_t (*mapping)[ACCESSIBILITY_BUTTON_SLOT_COUNT] = physical_mappings(context);
        unsigned int hold_mapping = mapping[selected][ACCESSIBILITY_BUTTON_HOLD];
        bool native_hold = hold_mapping == ACCESSIBILITY_ACTION_SYSTEM ||
            (hold_mapping == ACCESSIBILITY_ACTION_NONE && raw != BUTTON_VOL_UP && raw != BUTTON_VOL_DOWN);
        bool held_release = (button & BUTTON_REL) && state->down && native_hold &&
            (state->held || now - state->press_ms >= state->hold_ms);
        unsigned int maximum_clicks = 1;
        if (mapping[selected][ACCESSIBILITY_BUTTON_DOUBLE] != ACCESSIBILITY_ACTION_SYSTEM)
            maximum_clicks = 2;
        if (mapping[selected][ACCESSIBILITY_BUTTON_TRIPLE] != ACCESSIBILITY_ACTION_SYSTEM)
            maximum_clicks = 3;
        enum accessibility_button_input input = (button & BUTTON_REL) ?
            ACCESSIBILITY_BUTTON_RELEASE : (button & BUTTON_REPEAT) ?
            ACCESSIBILITY_BUTTON_REPEAT : ACCESSIBILITY_BUTTON_PRESS;
        event = accessibility_buttons_process(state, input,
            selected, maximum_clicks, now);
        if (held_release && !locked)
        {
            *action = accessibility_default_button_action(button, context, true);
            return true;
        }
        if (!event.recognized)
            return event.consumed;
    }
    *action = physical_action(&event, context, locked);
    physical_repeat = event.repeat;
    return true;
#else
    (void)button;
    (void)context;
    (void)locked;
    return false;
#endif
}

bool accessibility_button_is_repeat(void)
{
    return physical_repeat;
}

static int accessibility_navigation_exit(int context)
{
    unsigned int base = (unsigned int)context & ~(CONTEXT_REMOTE | CONTEXT_CUSTOM |
        CONTEXT_CUSTOM2 | CONTEXT_LOCKED | CONTEXT_REMAPPED);
    if (context & (CONTEXT_PLUGIN | CONTEXT_LOCKED))
        return ACTION_NONE;
    if ((context & (CONTEXT_CUSTOM | CONTEXT_CUSTOM2)) == (CONTEXT_CUSTOM | CONTEXT_CUSTOM2) &&
        base == CONTEXT_STD)
        return ACTION_STD_CANCEL;
    if (context & (CONTEXT_CUSTOM | CONTEXT_CUSTOM2))
        return ACTION_NONE;
    if (base == CONTEXT_WPS)
        return ACTION_WPS_MENU;
    if (base == CONTEXT_STD || base == CONTEXT_TREE || base == CONTEXT_MAINMENU ||
        base == CONTEXT_LIST || base == CONTEXT_ID3DB)
        return ACTION_STD_MENU;
    if (base == CONTEXT_SETTINGS || base == CONTEXT_SETTINGS_EQ ||
        base == CONTEXT_SETTINGS_COLOURCHOOSER || base == CONTEXT_SETTINGS_TIME ||
        base == CONTEXT_SETTINGS_RECTRIGGER || base == CONTEXT_QUICKSCREEN)
        return ACTION_STD_CANCEL;
    return ACTION_NONE;
}

static int accessibility_launch_screen(unsigned int target)
{
    switch (target)
    {
        case ACCESSIBILITY_LAUNCH_FILES: return GO_TO_FILEBROWSER;
#ifdef HAVE_TAGCACHE
        case ACCESSIBILITY_LAUNCH_DATABASE: return GO_TO_DBBROWSER;
#endif
        case ACCESSIBILITY_LAUNCH_RESUME: return GO_TO_WPS;
        case ACCESSIBILITY_LAUNCH_SETTINGS: return GO_TO_MAINMENU;
        case ACCESSIBILITY_LAUNCH_PLAYLISTS: return GO_TO_PLAYLISTS_SCREEN;
        default: return GO_TO_PREVIOUS;
    }
}

int accessibility_process_pending(int event, int context)
{
    if (event != ACTION_NONE && event != ACTION_REDRAW)
    {
        if ((event & SYS_EVENT) && event != SYS_BATTERY_UPDATE &&
            event != SYS_CHARGER_CONNECTED && event != SYS_CHARGER_DISCONNECTED)
        {
            root_menu_cancel_navigation();
            accessibility_reset();
        }
        else if (!(event & SYS_EVENT))
            root_menu_cancel_navigation();
        return 0;
    }
    if (root_menu_navigation_pending())
    {
        int action = accessibility_navigation_exit(context);
        if (action == ACTION_NONE)
            root_menu_cancel_navigation();
        return action;
    }
    if (!launch_pending || launch_running)
        return 0;
    launch_pending = false;
    launch_running = true;
    accessibility_reset();
    MENUITEM_STRINGLIST(launcher, ID2P(LANG_ACCESSIBILITY_LAUNCH), NULL,
        ID2P(LANG_SHORTCUTS), ID2P(LANG_ACCESSIBILITY_APPLICATIONS),
        ID2P(LANG_ACCESSIBILITY_SYSTEM_SCREENS), ID2P(LANG_DIR_BROWSER),
        ID2P(LANG_TAGCACHE), ID2P(LANG_RESUME_PLAYBACK), ID2P(LANG_SETTINGS),
        ID2P(LANG_PLAYLISTS));
    unsigned int target = pending_launch;
    int result = 0;
    if (!target)
    {
        int selection = do_menu(&launcher, NULL, NULL, false);
        if (selection >= 0 && selection <= 2)
            target = selection == 0 ? 1 : selection == 1 ? 3 : 2;
        else if (selection >= 3 && selection <= 7)
            target = ACCESSIBILITY_LAUNCH_FILES + selection - 3;
        else
            result = selection;
    }
    if (target >= ACCESSIBILITY_LAUNCH_FILES)
    {
        int screen = accessibility_launch_screen(target);
        int action = accessibility_navigation_exit(context);
        bool requested = screen != GO_TO_PREVIOUS && action != ACTION_NONE &&
            root_menu_request_screen(screen);
        launch_running = false;
        accessibility_reset();
        if (!requested)
            splash(HZ * 2, ID2P(LANG_ACCESSIBILITY_DESTINATION_UNAVAILABLE));
        return requested ? action : ACTION_REDRAW;
    }
    if (target == 1)
        result = do_shortcut_menu(NULL);
    else if (target == 3)
    {
        struct browse_context browse = {
            .dirfilter = SHOW_PLUGINS,
            .flags = BROWSE_DIRFILTER,
            .title = str(LANG_ACCESSIBILITY_APPLICATIONS),
            .root = PLUGIN_APPS_DIR
        };
        result = rockbox_browse(&browse);
    }
    else if (target == 2)
    {
        extern const struct menu_item_ex info_menu;
        result = do_menu(&info_menu, NULL, NULL, false);
    }
    else if (accessibility_plugin_target(target))
    {
        result = plugin_load(pending_launch_path, NULL);
        if (result == PLUGIN_USB_CONNECTED)
            result = MENU_ATTACHED_USB;
    }
    launch_running = false;
    accessibility_reset();
    action_wait_for_release();
    return result == MENU_ATTACHED_USB ? SYS_USB_CONNECTED : ACTION_REDRAW;
}

int accessibility_handle_touch(const struct touchevent *ev, int context)
{
    if (!accessibility_enabled())
        return ACTION_NONE;
    if (context & (CONTEXT_PLUGIN | CONTEXT_LOCKED))
    {
        accessibility_reset();
        return ACTION_NONE;
    }
    if (ev && ev->type != TOUCHEVENT_NONE)
    {
        if (ev->type == TOUCHEVENT_PRESS)
            root_menu_cancel_navigation();
        accessibility_cancel_buttons();
    }
    if (!have_context || active_context != context)
    {
        accessibility_cancel_touch();
        active_context = context;
        have_context = true;
        accessibility_configure_touch();
    }
    if (accessibility_typing_active() &&
        accessibility_typing_mode() != ACCESSIBILITY_TYPING_ARROWS)
    {
        feedback_pending = ev && (ev->type == TOUCHEVENT_PRESS || ev->type == TOUCHEVENT_CONTACT);
        point_force = ev && ev->type == TOUCHEVENT_PRESS;
        point_single_tap = false;
        return accessibility_typing_handle_touch(ev, context);
    }
    struct accessibility_gesture_event gesture;
    if (!ev || ev->type == TOUCHEVENT_NONE)
    {
        gesture = accessibility_gesture_poll(&recognizer,
            accessibility_milliseconds(current_tick));
    }
    else
    {
        enum accessibility_touch_type type;
        switch (ev->type)
        {
            case TOUCHEVENT_PRESS:
                type = ACCESSIBILITY_TOUCH_PRESS;
                exploring = false;
                feedback_pending = false;
                recognizer.config.repeat_strokes = accessibility_repeat_mask(context);
                break;
            case TOUCHEVENT_CONTACT: type = ACCESSIBILITY_TOUCH_CONTACT; break;
            case TOUCHEVENT_RELEASE: type = ACCESSIBILITY_TOUCH_RELEASE; break;
            default:
                accessibility_reset();
                return ACTION_NONE;
        }
        gesture = accessibility_gesture_process(&recognizer, type, ev->x, ev->y,
            accessibility_milliseconds(ev->tick));
    }
    switch (gesture.type)
    {
        case ACCESSIBILITY_GESTURE_EXPLORE:
        case ACCESSIBILITY_GESTURE_SINGLE_TAP:
            point_x = gesture.x;
            point_y = gesture.y;
            point_force = !exploring || gesture.type == ACCESSIBILITY_GESTURE_SINGLE_TAP;
            point_single_tap = gesture.type == ACCESSIBILITY_GESTURE_SINGLE_TAP;
            point_pending = true;
            exploring = true;
            break;
        case ACCESSIBILITY_GESTURE_DOUBLE_TAP:
        case ACCESSIBILITY_GESTURE_LONG_HOLD:
        case ACCESSIBILITY_GESTURE_TRIPLE_TAP:
        case ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD:
        case ACCESSIBILITY_GESTURE_STROKE:
        {
            point_pending = false;
            feedback_pending = false;
            unsigned int slot = gesture.type == ACCESSIBILITY_GESTURE_DOUBLE_TAP ?
                ACCESSIBILITY_DOUBLE_SLOT : gesture.type == ACCESSIBILITY_GESTURE_LONG_HOLD ?
                ACCESSIBILITY_HOLD_SLOT : gesture.type == ACCESSIBILITY_GESTURE_TRIPLE_TAP ?
                ACCESSIBILITY_TRIPLE_SLOT : gesture.type == ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD ?
                ACCESSIBILITY_DOUBLE_HOLD_SLOT : (unsigned int)gesture.stroke;
            if (!slot || slot >= ACCESSIBILITY_SLOT_COUNT)
                return ACTION_NONE;
            if (gesture.repeat && !accessibility_repeat_safe(gesture_mappings(context)[slot], context))
            {
                accessibility_cancel_touch();
                return ACTION_NONE;
            }
            root_menu_cancel_navigation();
            int result;
            if (gesture_mappings(context)[slot] == ACCESSIBILITY_ACTION_LAUNCH)
            {
                accessibility_queue_launch(gesture_launches(context)[slot]);
                result = ACTION_NONE;
            }
            else
                result = accessibility_gesture_action_for(gesture_mappings(context)[slot], context, slot);
            result = accessibility_repeat_result(result, gesture.repeat, context);
            keyclick_click_gesture_repeat(result, gesture.repeat);
            return result;
        }
        default: break;
    }
    return point_pending ? ACTION_TOUCHSCREEN : ACTION_NONE;
}

bool accessibility_explore_point(int *x, int *y, bool *force)
{
    if (!x || !y || !force || !accessibility_enabled() || !point_pending)
        return false;
    *x = point_x;
    *y = point_y;
    *force = point_force;
    point_pending = false;
    feedback_pending = true;
    return true;
}

static void accessibility_feedback(const void *owner, int target, bool occupied,
                                   bool force, bool single_tap)
{
    bool changed = force || !feedback_valid || feedback_owner != owner ||
        feedback_target != target || feedback_occupied != occupied;
    feedback_valid = true;
    feedback_owner = owner;
    feedback_target = target;
    feedback_occupied = occupied;
    empty_speech_pending = changed && !occupied;
    if (changed)
        keyclick_click_touch_target(occupied, single_tap);
}

void accessibility_explore_feedback(const void *owner, int target, bool occupied)
{
    if (!feedback_pending || !accessibility_enabled())
        return;
    feedback_pending = false;
    accessibility_feedback(owner, target, occupied, point_force, point_single_tap);
}

void accessibility_speak_empty(void)
{
    bool pending = empty_speech_pending;
    empty_speech_pending = false;
    if (pending && accessibility_enabled() && accessibility_empty_speech_enabled())
        talk_id(LANG_ACCESSIBILITY_EMPTY, false);
}

static const int action_labels[ACCESSIBILITY_ACTION_COUNT] =
{
    LANG_ACCESSIBILITY_UNASSIGNED, LANG_ACCESSIBILITY_UP, LANG_ACCESSIBILITY_DOWN,
    LANG_ACCESSIBILITY_LEFT, LANG_ACCESSIBILITY_RIGHT, LANG_ACCESSIBILITY_ACTIVATE, LANG_BACK, LANG_MAIN_MENU,
    LANG_ACCESSIBILITY_CONTEXT, LANG_ACCESSIBILITY_VOLUME_UP, LANG_ACCESSIBILITY_VOLUME_DOWN,
    LANG_ACCESSIBILITY_BATTERY, LANG_ACCESSIBILITY_LAUNCH, LANG_ACCESSIBILITY_SHUTDOWN,
    LANG_ACCESSIBILITY_LOCK, LANG_ACCESSIBILITY_CURTAIN, LANG_ACCESSIBILITY_ACTION_TIME,
    LANG_ACCESSIBILITY_TOGGLE_ESPEAK, LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES,
    LANG_ACCESSIBILITY_TOGGLE_TOUCH, LANG_ACCESSIBILITY_ACTION_DATE,
    LANG_ACCESSIBILITY_ACTION_SUMMARY,
    LANG_ACCESSIBILITY_ACTION_FIRST, LANG_ACCESSIBILITY_ACTION_LAST,
    LANG_ACCESSIBILITY_ACTION_PAGE_FIRST, LANG_ACCESSIBILITY_ACTION_PAGE_LAST,
    LANG_ACCESSIBILITY_SHORTCUT_ACTION
};

static unsigned int accessibility_selectable_actions(void)
{
#ifdef HAVE_SCREEN_CURTAIN
    return ACCESSIBILITY_ACTION_COUNT;
#else
    return ACCESSIBILITY_ACTION_COUNT - 1;
#endif
}

static unsigned int accessibility_action_index(unsigned int action)
{
#ifndef HAVE_SCREEN_CURTAIN
    if (action == ACCESSIBILITY_ACTION_CURTAIN)
        return accessibility_selectable_actions();
    if (action > ACCESSIBILITY_ACTION_CURTAIN)
        return action - 1;
#endif
    return action;
}

static unsigned int accessibility_action_at(unsigned int index)
{
#ifndef HAVE_SCREEN_CURTAIN
    if (index >= ACCESSIBILITY_ACTION_CURTAIN)
        return index + 1;
#endif
    return index;
}

static int accessibility_launch_label(unsigned int target)
{
    if (target == 1)
        return LANG_SHORTCUTS;
    if (target == 2)
        return LANG_ACCESSIBILITY_SYSTEM_SCREENS;
    switch (target)
    {
        case ACCESSIBILITY_LAUNCH_FILES: return LANG_DIR_BROWSER;
        case ACCESSIBILITY_LAUNCH_DATABASE: return LANG_TAGCACHE;
        case ACCESSIBILITY_LAUNCH_RESUME: return LANG_RESUME_PLAYBACK;
        case ACCESSIBILITY_LAUNCH_SETTINGS: return LANG_SETTINGS;
        case ACCESSIBILITY_LAUNCH_PLAYLISTS: return LANG_PLAYLISTS;
        default: return LANG_ACCESSIBILITY_APPLICATIONS;
    }
}

static const char *accessibility_launch_name(unsigned int target)
{
    if (accessibility_plugin_target(target))
    {
        const char *path = active_config.launch_paths[target - ACCESSIBILITY_LAUNCH_PLUGIN_BASE];
        const char *name = strrchr(path, '/');
        return name ? name + 1 : path;
    }
    return str(accessibility_launch_label(target));
}

static void accessibility_speak_launch(unsigned int target)
{
    if (accessibility_plugin_target(target))
        talk_file_or_spell(NULL, active_config.launch_paths[target - ACCESSIBILITY_LAUNCH_PLUGIN_BASE], NULL, true);
    else
        talk_id(accessibility_launch_label(target), true);
}

static const int stroke_labels[ACCESSIBILITY_STROKE_COUNT] =
{
    0,
    LANG_ACCESSIBILITY_SWIPE_LEFT, LANG_ACCESSIBILITY_SWIPE_RIGHT,
    LANG_ACCESSIBILITY_SWIPE_UP, LANG_ACCESSIBILITY_SWIPE_DOWN,
    LANG_ACCESSIBILITY_SWIPE_LEFT_RIGHT, LANG_ACCESSIBILITY_SWIPE_LEFT_UP,
    LANG_ACCESSIBILITY_SWIPE_LEFT_DOWN, LANG_ACCESSIBILITY_SWIPE_RIGHT_LEFT,
    LANG_ACCESSIBILITY_SWIPE_RIGHT_UP, LANG_ACCESSIBILITY_SWIPE_RIGHT_DOWN,
    LANG_ACCESSIBILITY_SWIPE_UP_LEFT, LANG_ACCESSIBILITY_SWIPE_UP_RIGHT,
    LANG_ACCESSIBILITY_SWIPE_UP_DOWN, LANG_ACCESSIBILITY_SWIPE_DOWN_LEFT,
    LANG_ACCESSIBILITY_SWIPE_DOWN_RIGHT, LANG_ACCESSIBILITY_SWIPE_DOWN_UP
};

static int gesture_label(int slot)
{
    if (slot == ACCESSIBILITY_DOUBLE_SLOT)
        return LANG_ACCESSIBILITY_DOUBLE_TAP;
    if (slot == ACCESSIBILITY_HOLD_SLOT)
        return LANG_ACCESSIBILITY_HOLD;
    if (slot == ACCESSIBILITY_TRIPLE_SLOT)
        return LANG_ACCESSIBILITY_TRIPLE_TAP;
    if (slot == ACCESSIBILITY_DOUBLE_HOLD_SLOT)
        return LANG_ACCESSIBILITY_DOUBLE_TAP_HOLD;
    return stroke_labels[slot];
}

static const char *gesture_name(int slot, char *buffer, size_t length)
{
    (void)buffer;
    (void)length;
    return str(gesture_label(slot));
}

static const char *gesture_get_name(int selected, void *data, char *buffer, size_t length)
{
    if (selected == ACCESSIBILITY_SLOT_COUNT - 1)
        return str(LANG_RESET);
    int context = (intptr_t)data;
    if (!length)
        return buffer;
    int slot = selected + 1;
    char name[160];
    snprintf(buffer, length, "%s: %s", gesture_name(slot, name, sizeof(name)),
             str(action_labels[gesture_mappings(context)[slot]]));
    if (gesture_mappings(context)[slot] == ACCESSIBILITY_ACTION_LAUNCH)
    {
        size_t used = strlen(buffer);
        snprintf(buffer + used, length - used, ", %s", accessibility_launch_name(gesture_launches(context)[slot]));
    }
    return buffer;
}

static int gesture_speak(int selected, void *data)
{
    if (selected == ACCESSIBILITY_SLOT_COUNT - 1)
    {
        talk_id(LANG_RESET, false);
        return 0;
    }
    int context = (intptr_t)data;
    int slot = selected + 1;
    talk_id(gesture_label(slot), false);
    talk_id(action_labels[gesture_mappings(context)[slot]], true);
    if (gesture_mappings(context)[slot] == ACCESSIBILITY_ACTION_LAUNCH)
        accessibility_speak_launch(gesture_launches(context)[slot]);
    return 0;
}

static int accessibility_trial_apply(const struct accessibility_config *candidate, bool *saved)
{
    if (saved)
        *saved = false;
    if (trial_active)
        return 0;
    saved_trial = active_config;
    active_config = *candidate;
    trial_deadline = (uint32_t)current_tick + ACCESSIBILITY_TRIAL_TICKS;
    trial_active = true;
    accessibility_apply();
    const char *lines[] = {str(LANG_ACCESSIBILITY_TRIAL)};
    const struct text_message message = {lines, 1};
    enum yesno_res answer = gui_syncyesno_run_w_tmo(ACCESSIBILITY_TRIAL_TICKS,
        YESNO_NO, str(LANG_ACCESSIBILITY), &message, NULL, NULL);
    accessibility_check_trial();
    if (answer == YESNO_YES && trial_active)
    {
        if (accessibility_save(&active_config))
        {
            trial_active = false;
            if (saved)
                *saved = true;
            accessibility_apply();
            return 0;
        }
        accessibility_rollback();
        splash(HZ * 2, ID2P(LANG_ERROR_WRITING_CONFIG));
        return 0;
    }
    if (trial_active)
        accessibility_rollback();
    else
        accessibility_apply();
    if (answer != YESNO_USB)
        splash(HZ, ID2P(LANG_ACCESSIBILITY_ROLLED_BACK));
    return answer == YESNO_USB ? MENU_ATTACHED_USB : 0;
}

static int accessibility_trial(const struct accessibility_config *candidate)
{
    return accessibility_trial_apply(candidate, NULL);
}

static void accessibility_clean_launch_paths(struct accessibility_config *value)
{
    bool used[ACCESSIBILITY_LAUNCH_PATHS] = {false};
    for (unsigned int slot = 1; slot < ACCESSIBILITY_SLOT_COUNT; ++slot)
    {
        if (accessibility_plugin_target(value->gesture_launch[slot]))
            used[value->gesture_launch[slot] - ACCESSIBILITY_LAUNCH_PLUGIN_BASE] = true;
        if (accessibility_plugin_target(value->playback_gesture_launch[slot]))
            used[value->playback_gesture_launch[slot] - ACCESSIBILITY_LAUNCH_PLUGIN_BASE] = true;
    }
    for (unsigned int button = 0; button < ACCESSIBILITY_BUTTON_COUNT; ++button)
        for (unsigned int slot = 0; slot < ACCESSIBILITY_BUTTON_SLOT_COUNT; ++slot)
        {
            if (accessibility_plugin_target(value->button_launch[button][slot]))
                used[value->button_launch[button][slot] - ACCESSIBILITY_LAUNCH_PLUGIN_BASE] = true;
            if (accessibility_plugin_target(value->playback_launch[button][slot]))
                used[value->playback_launch[button][slot] - ACCESSIBILITY_LAUNCH_PLUGIN_BASE] = true;
        }
    for (unsigned int target = 0; target < ACCESSIBILITY_LAUNCH_PATHS; ++target)
        if (!used[target])
            memset(value->launch_paths[target], 0, MAX_PATH);
}

static int accessibility_select_launch(uint8_t *target)
{
    MENUITEM_STRINGLIST(destinations, ID2P(LANG_ACCESSIBILITY_LAUNCH), NULL,
        ID2P(LANG_SHORTCUTS), ID2P(LANG_ACCESSIBILITY_APPLICATIONS),
        ID2P(LANG_ACCESSIBILITY_SYSTEM_SCREENS), ID2P(LANG_DIR_BROWSER),
        ID2P(LANG_TAGCACHE), ID2P(LANG_RESUME_PLAYBACK), ID2P(LANG_SETTINGS),
        ID2P(LANG_PLAYLISTS));
    editing_launch = true;
    int result = do_menu(&destinations, NULL, NULL, false);
    if (result >= 3 && result <= 7)
    {
        *target = ACCESSIBILITY_LAUNCH_FILES + result - 3;
        editing_launch = false;
        return 1;
    }
    if (result == 0 || result == 2)
    {
        *target = result == 0 ? 1 : 2;
        editing_launch = false;
        return 1;
    }
    if (result == 1)
    {
        char path[MAX_PATH] = {0};
        struct browse_context browse = {
            .dirfilter = SHOW_PLUGINS,
            .flags = BROWSE_DIRFILTER | BROWSE_SELECTONLY | BROWSE_NO_CONTEXT_MENU,
            .title = str(LANG_ACCESSIBILITY_APPLICATIONS),
            .root = PLUGIN_DIR,
            .buf = path,
            .bufsize = sizeof(path)
        };
        result = rockbox_browse(&browse);
        if (result != MENU_ATTACHED_USB && (browse.flags & BROWSE_SELECTED))
        {
            if (!path[0] || !accessibility_launch_path_valid(path))
            {
                splash(HZ * 2, ID2P(LANG_PLUGIN_CANT_OPEN));
                editing_launch = false;
                return 0;
            }
            *target = 0;
            accessibility_clean_launch_paths(&edit_config);
            unsigned int selected = ACCESSIBILITY_LAUNCH_PATHS;
            for (unsigned int index = 0; index < ACCESSIBILITY_LAUNCH_PATHS; ++index)
                if (!strcmp(edit_config.launch_paths[index], path))
                    selected = index;
            if (selected == ACCESSIBILITY_LAUNCH_PATHS)
                for (unsigned int index = 0; index < ACCESSIBILITY_LAUNCH_PATHS; ++index)
                    if (!edit_config.launch_paths[index][0])
                    {
                        selected = index;
                        break;
                    }
            if (selected == ACCESSIBILITY_LAUNCH_PATHS)
            {
                splash(HZ * 2, ID2P(LANG_ACCESSIBILITY_LAUNCH_CAPACITY));
                editing_launch = false;
                return 0;
            }
            memcpy(edit_config.launch_paths[selected], path, strlen(path) + 1);
            *target = ACCESSIBILITY_LAUNCH_PLUGIN_BASE + selected;
            editing_launch = false;
            return 1;
        }
    }
    editing_launch = false;
    return result == MENU_ATTACHED_USB ? MENU_ATTACHED_USB : 0;
}

static int accessibility_gesture_profile_menu(int context)
{
    int selection = 0;
    while (true)
    {
        struct simplelist_info list;
        simplelist_info_init(&list, str(accessibility_playback_context(context) ?
            LANG_ACCESSIBILITY_PLAYBACK_ACTIONS : LANG_ACCESSIBILITY_INTERFACE_ACTIONS),
            ACCESSIBILITY_SLOT_COUNT, (void *)(intptr_t)context);
        list.selection = selection;
        list.get_name = gesture_get_name;
        list.get_talk = gesture_speak;
        if (simplelist_show_list(&list))
            return MENU_ATTACHED_USB;
        selection = list.selection;
        if (selection < 0)
            return 0;
        edit_config = active_config;
        uint8_t *mapping = accessibility_playback_context(context) ?
            edit_config.playback_mapping : edit_config.mapping;
        uint8_t *launches = accessibility_playback_context(context) ?
            edit_config.playback_gesture_launch : edit_config.gesture_launch;
        if (selection == ACCESSIBILITY_SLOT_COUNT - 1)
        {
            accessibility_default_gestures(mapping);
            memset(launches, 0, ACCESSIBILITY_SLOT_COUNT);
            accessibility_clean_launch_paths(&edit_config);
            if (memcmp(&edit_config, &active_config, sizeof(edit_config)))
            {
                int result = accessibility_trial(&edit_config);
                if (result == MENU_ATTACHED_USB)
                    return result;
            }
            continue;
        }
        int slot = selection + 1;
        int choice = accessibility_action_index(mapping[slot]);
        unsigned int action_count = accessibility_selectable_actions();
        if ((unsigned int)choice >= action_count)
            choice = ACCESSIBILITY_ACTION_NONE;
        struct opt_items options[ACCESSIBILITY_ACTION_COUNT];
        for (unsigned int index = 0; index < action_count; ++index)
        {
            int label = action_labels[accessibility_action_at(index)];
            options[index] = (struct opt_items){(const unsigned char *)str(label), label};
        }
        char name[160];
        if (set_option(gesture_name(slot, name, sizeof(name)), &choice, RB_INT, options,
                       action_count, NULL))
            return MENU_ATTACHED_USB;
        choice = accessibility_action_at(choice);
        mapping[slot] = choice;
        if (choice == ACCESSIBILITY_ACTION_LAUNCH)
        {
            int result = accessibility_select_launch(&launches[slot]);
            if (result == MENU_ATTACHED_USB)
                return result;
            if (result != 1)
                continue;
        }
        else
            launches[slot] = 0;
        accessibility_clean_launch_paths(&edit_config);
        if (memcmp(&edit_config, &active_config, sizeof(edit_config)))
        {
            int result = accessibility_trial(&edit_config);
            if (result == MENU_ATTACHED_USB)
                return result;
        }
    }
}

static const int gesture_profile_labels[] = {
    LANG_ACCESSIBILITY_INTERFACE_ACTIONS, LANG_ACCESSIBILITY_PLAYBACK_ACTIONS
};

static const char *gesture_profile_name(int selected, void *data, char *buffer, size_t length)
{
    (void)data;
    (void)buffer;
    (void)length;
    return str(gesture_profile_labels[selected]);
}

static int gesture_profile_speak(int selected, void *data)
{
    (void)data;
    talk_id(gesture_profile_labels[selected], false);
    return 0;
}

static int accessibility_edit_gestures(void)
{
    int selection = 0;
    for (;;)
    {
        struct simplelist_info list;
        simplelist_info_init(&list, str(LANG_ACCESSIBILITY_GESTURES),
                             ARRAYLEN(gesture_profile_labels), NULL);
        list.selection = selection;
        list.get_name = gesture_profile_name;
        list.get_talk = gesture_profile_speak;
        if (simplelist_show_list(&list))
            return MENU_ATTACHED_USB;
        selection = list.selection;
        if (selection < 0)
            return 0;
        if (selection < (int)ARRAYLEN(gesture_profile_labels) &&
            accessibility_gesture_profile_menu(selection ? CONTEXT_WPS : CONTEXT_STD) == MENU_ATTACHED_USB)
            return MENU_ATTACHED_USB;
    }
}

static const int menu_labels[] = {LANG_ACCESSIBILITY_ENABLED, LANG_ACCESSIBILITY_GESTURES,
    LANG_ACCESSIBILITY_TOUCH_HOLD_TIME, LANG_ACCESSIBILITY_STROKE_REPEAT,
    LANG_ACCESSIBILITY_EMPTY_FEEDBACK, LANG_KEYCLICK_EMPTY_PITCH,
    LANG_KEYCLICK_EMPTY_SEMITONES, LANG_RESET};

static const char *accessibility_get_name(int selected, void *data, char *buffer, size_t length)
{
    (void)data;
    if (selected == 0 || selected == 3 || selected == 5)
    {
        bool value = selected == 0 ? active_config.enabled :
            selected == 3 ? active_config.stroke_repeat : active_config.empty_pitch;
        snprintf(buffer, length, "%s: %s", str(menu_labels[selected]),
                 str(value ? LANG_ON : LANG_OFF));
        return buffer;
    }
    if (selected == 2)
    {
        snprintf(buffer, length, "%s: %u ms", str(menu_labels[selected]),
                 (unsigned int)active_config.touch_hold_ms);
        return buffer;
    }
    if (selected == 4)
    {
        snprintf(buffer, length, "%s: %s", str(menu_labels[selected]),
                 str(empty_feedback_labels[accessibility_empty_feedback_mode()]));
        return buffer;
    }
    if (selected == 6)
    {
        snprintf(buffer, length, "%s: %d", str(menu_labels[selected]),
                 (int)active_config.empty_semitones);
        return buffer;
    }
    return str(menu_labels[selected]);
}

static int accessibility_speak(int selected, void *data)
{
    (void)data;
    talk_id(menu_labels[selected], false);
    if (selected == 0)
        talk_id(active_config.enabled ? LANG_ON : LANG_OFF, true);
    else if (selected == 2)
        talk_value(active_config.touch_hold_ms, UNIT_MS, true);
    else if (selected == 3)
        talk_id(active_config.stroke_repeat ? LANG_ON : LANG_OFF, true);
    else if (selected == 4)
        talk_id(empty_feedback_labels[accessibility_empty_feedback_mode()], true);
    else if (selected == 5)
        talk_id(active_config.empty_pitch ? LANG_ON : LANG_OFF, true);
    else if (selected == 6)
        talk_value(active_config.empty_semitones, UNIT_INT, true);
    return 0;
}

int accessibility_touch_menu(void)
{
    accessibility_init();
    int selection = 0;
    while (true)
    {
        struct simplelist_info list;
        simplelist_info_init(&list, str(LANG_ACCESSIBILITY), ARRAYLEN(menu_labels), NULL);
        list.selection = selection;
        list.get_name = accessibility_get_name;
        list.get_talk = accessibility_speak;
        if (simplelist_show_list(&list))
            return MENU_ATTACHED_USB;
        selection = list.selection;
        if (selection < 0)
            return 0;
        int result = 0;
        if (selection == 0)
        {
            edit_config = active_config;
            if (set_bool(str(LANG_ACCESSIBILITY_ENABLED), &edit_config.enabled))
                return MENU_ATTACHED_USB;
            if (edit_config.enabled != active_config.enabled)
                result = accessibility_trial(&edit_config);
        }
        else if (selection == 1)
            result = accessibility_edit_gestures();
        else if (selection == 2)
        {
            edit_config = active_config;
            int duration = edit_config.touch_hold_ms;
            if (set_int((const unsigned char *)str(LANG_ACCESSIBILITY_TOUCH_HOLD_TIME), "ms", UNIT_MS,
                        &duration, NULL, 100, ACCESSIBILITY_TOUCH_HOLD_MIN,
                        ACCESSIBILITY_TOUCH_HOLD_MAX, NULL))
                return MENU_ATTACHED_USB;
            edit_config.touch_hold_ms = duration;
            if (duration != active_config.touch_hold_ms)
                result = accessibility_trial(&edit_config);
        }
        else if (selection == 3)
        {
            edit_config = active_config;
            if (set_bool(str(LANG_ACCESSIBILITY_STROKE_REPEAT), &edit_config.stroke_repeat))
                return MENU_ATTACHED_USB;
            if (edit_config.stroke_repeat != active_config.stroke_repeat)
                result = accessibility_trial(&edit_config);
        }
        else if (selection == 4)
            result = accessibility_empty_feedback_menu();
        else if (selection == 5)
            result = accessibility_keyclick_empty_menu();
        else if (selection == 6)
            result = accessibility_keyclick_pitch_menu();
        else if (selection == 7)
        {
            accessibility_defaults(&edit_config);
            memcpy(edit_config.buttons, active_config.buttons, sizeof(edit_config.buttons));
            memcpy(edit_config.button_launch, active_config.button_launch, sizeof(edit_config.button_launch));
            memcpy(edit_config.playback_buttons, active_config.playback_buttons,
                   sizeof(edit_config.playback_buttons));
            memcpy(edit_config.playback_launch, active_config.playback_launch,
                   sizeof(edit_config.playback_launch));
            memcpy(edit_config.launch_paths, active_config.launch_paths, sizeof(edit_config.launch_paths));
            accessibility_clean_launch_paths(&edit_config);
            edit_config.hold_ms = active_config.hold_ms;
            edit_config.click_sources = active_config.click_sources;
            bool saved;
            result = accessibility_trial_apply(&edit_config, &saved);
            if (saved && accessibility_empty_feedback_mode() != ACCESSIBILITY_EMPTY_SOUND_ONLY &&
                !accessibility_empty_save(ACCESSIBILITY_EMPTY_SOUND_ONLY))
                splash(HZ * 2, ID2P(LANG_ACCESSIBILITY_RESET_PARTIAL));
        }
        if (result == MENU_ATTACHED_USB)
            return result;
    }
}

int accessibility_menu(void)
{
    return accessibility_touch_menu();
}

bool accessibility_set_curtain_state(bool enabled, bool announce)
{
#ifdef HAVE_SCREEN_CURTAIN
    if (!announce && enabled == backlight_screen_curtain_active())
        return true;
    if (enabled && !tts_is_available())
    {
        if (announce)
            splash(HZ * 2, ID2P(LANG_ACCESSIBILITY_CURTAIN_REQUIRES_SPEECH));
        return false;
    }
    backlight_set_screen_curtain(enabled);
    if (announce)
    {
        talk_id(LANG_ACCESSIBILITY_CURTAIN, false);
        talk_id(enabled ? LANG_ON : LANG_OFF, true);
    }
    return true;
#else
    (void)enabled;
    if (announce)
        splash(HZ * 2, ID2P(LANG_ACCESSIBILITY_CURTAIN_UNAVAILABLE));
    return false;
#endif
}

bool accessibility_set_curtain(bool enabled)
{
    return accessibility_set_curtain_state(enabled, true);
}

int accessibility_curtain_menu(void)
{
    bool enabled = backlight_screen_curtain_active();
    if (set_bool(str(LANG_ACCESSIBILITY_CURTAIN), &enabled))
        return MENU_ATTACHED_USB;
    if (enabled != backlight_screen_curtain_active())
        accessibility_set_curtain(enabled);
    return 0;
}

bool accessibility_curtain_escape(int button)
{
#ifdef HIBY_R1
    int chord = BUTTON_POWER | BUTTON_NEXT;
    if (curtain_wait_for_press)
    {
        unsigned int pressed = (unsigned int)button & BUTTON_MAIN;
        if ((button & (BUTTON_REL | BUTTON_REPEAT)) || !pressed ||
            (pressed & (pressed - 1)))
            return true;
        curtain_wait_for_press = false;
    }
    if (curtain_release_mask)
    {
        if (button & BUTTON_REL)
            curtain_release_mask &= ~(button & BUTTON_MAIN);
        return true;
    }
    if (backlight_screen_curtain_active() && !(button & BUTTON_REL) &&
        (button & BUTTON_MAIN) == chord)
    {
        curtain_release_mask = chord;
        accessibility_set_curtain(false);
        return true;
    }
#else
    (void)button;
#endif
    return false;
}

void accessibility_curtain_clear_queue(void)
{
#ifdef HIBY_R1
    if (curtain_release_mask)
    {
        curtain_release_mask = 0;
        curtain_wait_for_press = true;
    }
#endif
}

unsigned int accessibility_keyclick_sources(void)
{
    accessibility_check_trial();
    return initialized ? active_config.click_sources : KEYCLICK_SOURCE_ALL;
}

int accessibility_keyclick_empty_pitch(void)
{
    accessibility_check_trial();
    return !initialized ? -4 : active_config.empty_pitch ? active_config.empty_semitones : 0;
}

int accessibility_keyclick_menu(void)
{
    accessibility_init();
    static const struct opt_items options[] = {
        {STR(LANG_KEYCLICK_BOTH)}, {STR(LANG_KEYCLICK_PHYSICAL)},
        {STR(LANG_KEYCLICK_GESTURES)}, {STR(LANG_KEYCLICK_NONE)},
        {STR(LANG_KEYCLICK_EXPLORATION)}, {STR(LANG_KEYCLICK_PHYSICAL_EXPLORATION)},
        {STR(LANG_KEYCLICK_GESTURES_EXPLORATION)}, {STR(LANG_KEYCLICK_ALL)}
    };
    static const unsigned int sources_by_choice[] = {3, 1, 2, 0, 4, 5, 6, 7};
    int choice = 0;
    for (unsigned int index = 0; index < ARRAYLEN(sources_by_choice); ++index)
        if (sources_by_choice[index] == active_config.click_sources)
            choice = index;
    if (set_option(str(LANG_KEYCLICK_SOURCES), &choice, RB_INT, options, ARRAYLEN(options), NULL))
        return MENU_ATTACHED_USB;
    if ((unsigned int)choice >= ARRAYLEN(sources_by_choice))
        return 0;
    unsigned int sources = sources_by_choice[choice];
    if (sources != active_config.click_sources)
    {
        edit_config = active_config;
        edit_config.click_sources = sources;
        return accessibility_trial(&edit_config);
    }
    return 0;
}

int accessibility_keyclick_empty_menu(void)
{
    accessibility_init();
    static const struct opt_items options[] = {{STR(LANG_SET_BOOL_NO)}, {STR(LANG_SET_BOOL_YES)}};
    int choice = active_config.empty_pitch;
    if (set_option(str(LANG_KEYCLICK_EMPTY_PITCH), &choice, RB_INT, options, ARRAYLEN(options), NULL))
        return MENU_ATTACHED_USB;
    if (choice != active_config.empty_pitch && (choice == 0 || choice == 1))
    {
        edit_config = active_config;
        edit_config.empty_pitch = choice != 0;
        return accessibility_trial(&edit_config);
    }
    return 0;
}

int accessibility_keyclick_pitch_menu(void)
{
    accessibility_init();
    int semitones = active_config.empty_semitones;
    if (set_int((const unsigned char *)str(LANG_KEYCLICK_EMPTY_SEMITONES),
                str(LANG_KEYCLICK_SEMITONES), UNIT_INT, &semitones, NULL, 1, -12, 12, NULL))
        return MENU_ATTACHED_USB;
    if (semitones != active_config.empty_semitones && semitones >= -12 && semitones <= 12)
    {
        edit_config = active_config;
        edit_config.empty_semitones = semitones;
        return accessibility_trial(&edit_config);
    }
    return 0;
}

#ifdef HIBY_R1
static const int button_labels[ACCESSIBILITY_BUTTON_COUNT] = {
    LANG_ACCESSIBILITY_BUTTON_POWER, LANG_ACCESSIBILITY_BUTTON_PLAY,
    LANG_ACCESSIBILITY_BUTTON_NEXT, LANG_ACCESSIBILITY_BUTTON_VOLUME_UP,
    LANG_ACCESSIBILITY_BUTTON_VOLUME_DOWN
};
static const int press_labels[ACCESSIBILITY_BUTTON_SLOT_COUNT] = {
    LANG_ACCESSIBILITY_SINGLE_PRESS, LANG_ACCESSIBILITY_DOUBLE_PRESS,
    LANG_ACCESSIBILITY_TRIPLE_PRESS, LANG_ACCESSIBILITY_HOLD
};

static int physical_label(unsigned int action)
{
    return action == ACCESSIBILITY_ACTION_SYSTEM ? LANG_ACCESSIBILITY_SYSTEM_DEFAULT :
        action_labels[action];
}

static int button_default_label(int button, unsigned int slot, int context, bool unassigned)
{
    if (unassigned && button == BUTTON_VOL_UP)
        return LANG_ACCESSIBILITY_VOLUME_UP;
    if (unassigned && button == BUTTON_VOL_DOWN)
        return LANG_ACCESSIBILITY_VOLUME_DOWN;
    if (button == BUTTON_POWER && slot == ACCESSIBILITY_BUTTON_HOLD && context != CONTEXT_KEYBOARD)
        return LANG_ACCESSIBILITY_DEFAULT_POWER_HOLD;
    bool reader = context == (CONTEXT_CUSTOM | CONTEXT_CUSTOM2 | CONTEXT_STD);
    int action = accessibility_default_button_action(button |
        (slot == ACCESSIBILITY_BUTTON_HOLD ? BUTTON_REPEAT : BUTTON_REL), context, false);
    if (slot != ACCESSIBILITY_BUTTON_HOLD && (action == ACTION_NONE || action == ACTION_UNKNOWN))
        action = accessibility_default_button_action(button, context, false);
    switch (action)
    {
        case ACTION_STD_PREV:
        case ACTION_STD_PREVREPEAT:
            return reader ? LANG_ACCESSIBILITY_DEFAULT_TEXT_PREVIOUS : LANG_ACCESSIBILITY_UP;
        case ACTION_STD_NEXT:
        case ACTION_STD_NEXTREPEAT:
            return reader ? LANG_ACCESSIBILITY_DEFAULT_TEXT_NEXT : LANG_ACCESSIBILITY_DOWN;
        case ACTION_STD_OK:
            return reader ? LANG_ACCESSIBILITY_DEFAULT_TEXT_PAUSE : LANG_ACCESSIBILITY_ACTIVATE;
        case ACTION_STD_CANCEL:
            return LANG_BACK;
        case ACTION_STD_MENU:
            return LANG_MAIN_MENU;
        case ACTION_STD_CONTEXT:
            return LANG_ACCESSIBILITY_CONTEXT;
        case ACTION_SETTINGS_DEC:
            return reader ? LANG_ACCESSIBILITY_DEFAULT_RANGE_PREVIOUS : LANG_ACCESSIBILITY_DOWN;
        case ACTION_SETTINGS_INC:
            return reader ? LANG_ACCESSIBILITY_DEFAULT_RANGE_NEXT : LANG_ACCESSIBILITY_UP;
        case ACTION_LIST_VOLUP:
        case ACTION_WPS_VOLUP:
            return LANG_ACCESSIBILITY_VOLUME_UP;
        case ACTION_LIST_VOLDOWN:
        case ACTION_WPS_VOLDOWN:
            return LANG_ACCESSIBILITY_VOLUME_DOWN;
        case ACTION_WPS_PLAY:
            return LANG_ACCESSIBILITY_DEFAULT_MUSIC_PAUSE;
        case ACTION_WPS_SKIPPREV:
            return LANG_ACCESSIBILITY_DEFAULT_TRACK_PREVIOUS;
        case ACTION_WPS_SKIPNEXT:
            return LANG_ACCESSIBILITY_DEFAULT_TRACK_NEXT;
        case ACTION_WPS_SEEKBACK:
            return LANG_ACCESSIBILITY_DEFAULT_SEEK_BACK;
        case ACTION_WPS_SEEKFWD:
            return LANG_ACCESSIBILITY_DEFAULT_SEEK_FORWARD;
        case ACTION_KBD_UP:
            return LANG_ACCESSIBILITY_UP;
        case ACTION_KBD_DOWN:
            return LANG_ACCESSIBILITY_DOWN;
        case ACTION_KBD_LEFT:
            return LANG_ACCESSIBILITY_LEFT;
        case ACTION_KBD_RIGHT:
            return LANG_ACCESSIBILITY_RIGHT;
        case ACTION_KBD_CURSOR_LEFT:
            return LANG_ACCESSIBILITY_DEFAULT_CARET_LEFT;
        case ACTION_KBD_CURSOR_RIGHT:
            return LANG_ACCESSIBILITY_DEFAULT_CARET_RIGHT;
        case ACTION_KBD_SELECT:
            return LANG_ACCESSIBILITY_DEFAULT_INSERT;
        case ACTION_KBD_DONE:
            return LANG_ACCESSIBILITY_DEFAULT_FINISH;
        default:
            return LANG_ACCESSIBILITY_DEFAULT_NO_ACTION;
    }
}

static bool button_uses_default(unsigned int mapping, unsigned int slot)
{
    return mapping == ACCESSIBILITY_ACTION_SYSTEM || (mapping == ACCESSIBILITY_ACTION_NONE &&
        slot != ACCESSIBILITY_BUTTON_DOUBLE && slot != ACCESSIBILITY_BUTTON_TRIPLE);
}

static const char *button_guide_name(int selected, void *data, char *buffer, size_t length)
{
    if (selected < 0 || selected >= ACCESSIBILITY_BUTTON_COUNT * ACCESSIBILITY_BUTTON_SLOT_COUNT)
    {
        if (length)
            buffer[0] = '\0';
        return buffer;
    }
    unsigned int button = selected / ACCESSIBILITY_BUTTON_SLOT_COUNT;
    unsigned int slot = selected % ACCESSIBILITY_BUTTON_SLOT_COUNT;
    int label = button_default_label(physical_buttons[button], slot, (int)(intptr_t)data, false);
    snprintf(buffer, length, "%s, %s: %s%s%s", str(button_labels[button]),
        str(press_labels[slot]),
        slot == ACCESSIBILITY_BUTTON_DOUBLE || slot == ACCESSIBILITY_BUTTON_TRIPLE ?
            (const char *)str(LANG_ACCESSIBILITY_DEFAULT_MULTICLICK) : "",
        slot == ACCESSIBILITY_BUTTON_DOUBLE || slot == ACCESSIBILITY_BUTTON_TRIPLE ? ": " : "",
        str(label));
    return buffer;
}

static int button_guide_speak(int selected, void *data)
{
    if (selected < 0 || selected >= ACCESSIBILITY_BUTTON_COUNT * ACCESSIBILITY_BUTTON_SLOT_COUNT)
        return 0;
    unsigned int button = selected / ACCESSIBILITY_BUTTON_SLOT_COUNT;
    unsigned int slot = selected % ACCESSIBILITY_BUTTON_SLOT_COUNT;
    talk_id(button_labels[button], false);
    talk_id(press_labels[slot], true);
    if (slot == ACCESSIBILITY_BUTTON_DOUBLE || slot == ACCESSIBILITY_BUTTON_TRIPLE)
        talk_id(LANG_ACCESSIBILITY_DEFAULT_MULTICLICK, true);
    talk_id(button_default_label(physical_buttons[button], slot, (int)(intptr_t)data, false), true);
    return 0;
}

static const int button_guide_context_labels[] = {
    LANG_ACCESSIBILITY_DEFAULT_MENUS, LANG_ACCESSIBILITY_DEFAULT_MUSIC,
    LANG_ACCESSIBILITY_DEFAULT_TEXT, LANG_ACCESSIBILITY_DEFAULT_KEYBOARD
};

static const char *button_guide_context_name(int selected, void *data, char *buffer, size_t length)
{
    (void)data;
    (void)buffer;
    (void)length;
    return str(button_guide_context_labels[selected]);
}

static int button_guide_context_speak(int selected, void *data)
{
    (void)data;
    talk_id(button_guide_context_labels[selected], false);
    return 0;
}

static int button_controls_guide(void)
{
    static const int contexts[] = {
        CONTEXT_STD, CONTEXT_WPS, CONTEXT_CUSTOM | CONTEXT_CUSTOM2 | CONTEXT_STD,
        CONTEXT_KEYBOARD
    };
    struct simplelist_info list;
    simplelist_info_init(&list, str(LANG_ACCESSIBILITY_CONTROLS_GUIDE),
        ARRAYLEN(contexts), NULL);
    list.get_name = button_guide_context_name;
    list.get_talk = button_guide_context_speak;
    if (simplelist_show_list(&list))
        return MENU_ATTACHED_USB;
    if (list.selection < 0 || (unsigned int)list.selection >= ARRAYLEN(contexts))
        return 0;
    int choice = list.selection;
    simplelist_info_init(&list, str(button_guide_context_labels[choice]),
        ACCESSIBILITY_BUTTON_COUNT * ACCESSIBILITY_BUTTON_SLOT_COUNT,
        (void *)(intptr_t)contexts[choice]);
    list.get_name = button_guide_name;
    list.get_talk = button_guide_speak;
    return simplelist_show_list(&list) ? MENU_ATTACHED_USB : 0;
}

static const char *button_get_name(int selected, void *data, char *buffer, size_t length)
{
    if (!length)
        return buffer;
    int context = (int)(intptr_t)data;
    if (selected == ACCESSIBILITY_BUTTON_COUNT * ACCESSIBILITY_BUTTON_SLOT_COUNT)
        return str(LANG_RESET);
    unsigned int button = selected / ACCESSIBILITY_BUTTON_SLOT_COUNT;
    unsigned int slot = selected % ACCESSIBILITY_BUTTON_SLOT_COUNT;
    unsigned int mapping = physical_mappings(context)[button][slot];
    unsigned int target = accessibility_playback_context(context) ?
        active_config.playback_launch[button][slot] : active_config.button_launch[button][slot];
    snprintf(buffer, length, "%s, %s: %s", str(button_labels[button]),
        str(press_labels[slot]), str(physical_label(mapping)));
    if (button_uses_default(mapping, slot))
    {
        size_t used = strlen(buffer);
        snprintf(buffer + used, length - used, ", %s: %s",
            str(accessibility_playback_context(context) ? LANG_ACCESSIBILITY_DEFAULT_MUSIC :
                LANG_ACCESSIBILITY_DEFAULT_IN_MENU),
            str(button_default_label(physical_buttons[button], slot, context,
                mapping == ACCESSIBILITY_ACTION_NONE)));
    }
    if (mapping == ACCESSIBILITY_ACTION_LAUNCH)
    {
        size_t used = strlen(buffer);
        snprintf(buffer + used, length - used, ", %s",
            accessibility_launch_name(target));
    }
    return buffer;
}

static int button_speak(int selected, void *data)
{
    int context = (int)(intptr_t)data;
    if (selected == ACCESSIBILITY_BUTTON_COUNT * ACCESSIBILITY_BUTTON_SLOT_COUNT)
        talk_id(LANG_RESET, false);
    else
    {
        unsigned int button = selected / ACCESSIBILITY_BUTTON_SLOT_COUNT;
        unsigned int slot = selected % ACCESSIBILITY_BUTTON_SLOT_COUNT;
        unsigned int mapping = physical_mappings(context)[button][slot];
        talk_id(button_labels[button], false);
        talk_id(press_labels[slot], true);
        talk_id(physical_label(mapping), true);
        if (button_uses_default(mapping, slot))
        {
            talk_id(accessibility_playback_context(context) ? LANG_ACCESSIBILITY_DEFAULT_MUSIC :
                LANG_ACCESSIBILITY_DEFAULT_IN_MENU, true);
            if (slot == ACCESSIBILITY_BUTTON_DOUBLE || slot == ACCESSIBILITY_BUTTON_TRIPLE)
                talk_id(LANG_ACCESSIBILITY_DEFAULT_MULTICLICK, true);
            talk_id(button_default_label(physical_buttons[button], slot, context,
                mapping == ACCESSIBILITY_ACTION_NONE), true);
        }
        if (mapping == ACCESSIBILITY_ACTION_LAUNCH)
            accessibility_speak_launch(accessibility_playback_context(context) ?
                active_config.playback_launch[button][slot] : active_config.button_launch[button][slot]);
    }
    return 0;
}

static int accessibility_button_profile_menu(int context)
{
    int selection = 0;
    while (true)
    {
        struct simplelist_info list;
        simplelist_info_init(&list, str(accessibility_playback_context(context) ?
            LANG_ACCESSIBILITY_PLAYBACK_ACTIONS : LANG_ACCESSIBILITY_INTERFACE_ACTIONS),
            ACCESSIBILITY_BUTTON_COUNT * ACCESSIBILITY_BUTTON_SLOT_COUNT + 1,
            (void *)(intptr_t)context);
        list.selection = selection;
        list.get_name = button_get_name;
        list.get_talk = button_speak;
        if (simplelist_show_list(&list))
            return MENU_ATTACHED_USB;
        selection = list.selection;
        if (selection < 0)
            return 0;
        edit_config = active_config;
        uint8_t (*mapping)[ACCESSIBILITY_BUTTON_SLOT_COUNT] = accessibility_playback_context(context) ?
            edit_config.playback_buttons : edit_config.buttons;
        uint8_t (*launches)[ACCESSIBILITY_BUTTON_SLOT_COUNT] = accessibility_playback_context(context) ?
            edit_config.playback_launch : edit_config.button_launch;
        if (selection == ACCESSIBILITY_BUTTON_COUNT * ACCESSIBILITY_BUTTON_SLOT_COUNT)
        {
            memset(mapping, ACCESSIBILITY_ACTION_SYSTEM, sizeof(edit_config.buttons));
            memset(launches, 0, sizeof(edit_config.button_launch));
            accessibility_clean_launch_paths(&edit_config);
        }
        else
        {
            unsigned int button = selection / ACCESSIBILITY_BUTTON_SLOT_COUNT;
            unsigned int slot = selection % ACCESSIBILITY_BUTTON_SLOT_COUNT;
            unsigned int action_count = accessibility_selectable_actions();
            struct opt_items options[ACCESSIBILITY_ACTION_COUNT + 1];
            for (unsigned int action = 0; action < action_count; ++action)
            {
                int label = physical_label(accessibility_action_at(action));
                options[action] = (struct opt_items){
                    (const unsigned char *)str(label), label
                };
            }
            options[action_count] = (struct opt_items){
                (const unsigned char *)str(LANG_ACCESSIBILITY_SYSTEM_DEFAULT),
                LANG_ACCESSIBILITY_SYSTEM_DEFAULT
            };
            int choice = accessibility_action_index(mapping[button][slot]);
            if ((unsigned int)choice >= action_count)
                choice = action_count;
            if (set_option(str(button_labels[button]), &choice, RB_INT, options,
                action_count + 1, NULL))
                return MENU_ATTACHED_USB;
            if ((unsigned int)choice == action_count)
                choice = ACCESSIBILITY_ACTION_SYSTEM;
            else
                choice = accessibility_action_at(choice);
            mapping[button][slot] = choice;
            if (choice == ACCESSIBILITY_ACTION_LAUNCH)
            {
                int result = accessibility_select_launch(&launches[button][slot]);
                if (result == MENU_ATTACHED_USB)
                    return result;
                if (result != 1)
                    continue;
            }
            else
                launches[button][slot] = 0;
            accessibility_clean_launch_paths(&edit_config);
        }
        if (memcmp(&edit_config, &active_config, sizeof(edit_config)))
        {
            int result = accessibility_trial(&edit_config);
            if (result == MENU_ATTACHED_USB)
                return result;
        }
    }
}

static const int button_root_labels[] = {
    LANG_ACCESSIBILITY_INTERFACE_ACTIONS, LANG_ACCESSIBILITY_PLAYBACK_ACTIONS,
    LANG_ACCESSIBILITY_HOLD_TIME, LANG_RESET, LANG_ACCESSIBILITY_CONTROLS_GUIDE
};

static const char *button_root_name(int selected, void *data, char *buffer, size_t length)
{
    (void)data;
    if (selected == 2)
    {
        snprintf(buffer, length, "%s: %u ms", str(button_root_labels[selected]),
                 (unsigned int)active_config.hold_ms);
        return buffer;
    }
    return str(button_root_labels[selected]);
}

static int button_root_speak(int selected, void *data)
{
    (void)data;
    talk_id(button_root_labels[selected], false);
    if (selected == 2)
        talk_value(active_config.hold_ms, UNIT_MS, true);
    return 0;
}
#endif

int accessibility_buttons_menu(void)
{
#ifdef HIBY_R1
    accessibility_init();
    int selection = 0;
    while (true)
    {
        struct simplelist_info list;
        simplelist_info_init(&list, str(LANG_ACCESSIBILITY_BUTTONS), ARRAYLEN(button_root_labels), NULL);
        list.selection = selection;
        list.get_name = button_root_name;
        list.get_talk = button_root_speak;
        if (simplelist_show_list(&list))
            return MENU_ATTACHED_USB;
        selection = list.selection;
        if (selection < 0)
            return 0;
        int result = 0;
        if (selection == 0 || selection == 1)
            result = accessibility_button_profile_menu(selection ? CONTEXT_WPS : CONTEXT_STD);
        else if (selection == 4)
            result = button_controls_guide();
        else
        {
            edit_config = active_config;
            if (selection == 2)
            {
                int hold_ms = edit_config.hold_ms;
                if (set_int((const unsigned char *)str(LANG_ACCESSIBILITY_HOLD_TIME), "ms", UNIT_MS,
                            &hold_ms, NULL, 100, ACCESSIBILITY_BUTTON_HOLD_MIN,
                            ACCESSIBILITY_BUTTON_HOLD_MAX, NULL))
                    return MENU_ATTACHED_USB;
                edit_config.hold_ms = hold_ms;
            }
            else if (selection == 3)
            {
                memset(edit_config.buttons, ACCESSIBILITY_ACTION_SYSTEM, sizeof(edit_config.buttons));
                memset(edit_config.button_launch, 0, sizeof(edit_config.button_launch));
                memset(edit_config.playback_buttons, ACCESSIBILITY_ACTION_SYSTEM,
                       sizeof(edit_config.playback_buttons));
                memset(edit_config.playback_launch, 0, sizeof(edit_config.playback_launch));
                accessibility_clean_launch_paths(&edit_config);
            }
            if (memcmp(&edit_config, &active_config, sizeof(edit_config)))
                result = accessibility_trial(&edit_config);
        }
        if (result == MENU_ATTACHED_USB)
            return result;
    }
#else
    return 0;
#endif
}

#else

void accessibility_init(void) {}
bool accessibility_enabled(void) { return false; }
bool accessibility_set_enabled(bool enabled) { (void)enabled; return false; }
int accessibility_adjust_timeout(int requested_timeout) { return requested_timeout; }
void accessibility_reset(void) {}
void accessibility_cancel_touch(void) {}
void accessibility_set_target(const void *target) { (void)target; }
int accessibility_handle_touch(const struct touchevent *ev, int context)
{
    (void)ev;
    (void)context;
    return ACTION_NONE;
}
bool accessibility_explore_point(int *x, int *y, bool *force)
{
    (void)x;
    (void)y;
    (void)force;
    return false;
}
void accessibility_speak_empty(void) {}
enum accessibility_empty_feedback accessibility_empty_feedback_mode(void)
{
    return ACCESSIBILITY_EMPTY_SOUND_ONLY;
}
bool accessibility_empty_sound_enabled(void) { return false; }
bool accessibility_empty_speech_enabled(void) { return false; }
int accessibility_empty_feedback_menu(void) { return 0; }
void accessibility_explore_feedback(const void *owner, int target, bool occupied)
{
    (void)owner;
    (void)target;
    (void)occupied;
}
int accessibility_menu(void) { return 0; }
int accessibility_touch_menu(void) { return 0; }
int accessibility_buttons_menu(void) { return 0; }
unsigned int accessibility_keyclick_sources(void) { return 3; }
int accessibility_keyclick_empty_pitch(void) { return 0; }
int accessibility_keyclick_menu(void) { return 0; }
int accessibility_keyclick_empty_menu(void) { return 0; }
int accessibility_keyclick_pitch_menu(void) { return 0; }
int accessibility_curtain_menu(void) { return 0; }
bool accessibility_set_curtain(bool enabled) { (void)enabled; return false; }
bool accessibility_set_curtain_state(bool enabled, bool announce)
{ (void)enabled; (void)announce; return false; }
bool accessibility_curtain_escape(int button) { (void)button; return false; }
void accessibility_curtain_clear_queue(void) {}
bool accessibility_handle_button(int button, int context, bool locked, int *action)
{
    (void)button;
    (void)context;
    (void)locked;
    (void)action;
    return false;
}
bool accessibility_button_is_repeat(void) { return false; }
int accessibility_process_pending(int event, int context) { (void)event; (void)context; return 0; }

#endif
