#ifndef ACCESSIBILITY_TYPING_H
#define ACCESSIBILITY_TYPING_H

#include <stdbool.h>
#include <stdint.h>

struct touchevent;

enum accessibility_typing_mode
{
    ACCESSIBILITY_TYPING_LIFT,
    ACCESSIBILITY_TYPING_DOUBLE_TAP,
    ACCESSIBILITY_TYPING_ARROWS,
    ACCESSIBILITY_TYPING_MODE_COUNT
};

enum accessibility_echo_mode
{
    ACCESSIBILITY_ECHO_NONE,
    ACCESSIBILITY_ECHO_CHARACTERS,
    ACCESSIBILITY_ECHO_WORDS,
    ACCESSIBILITY_ECHO_BOTH,
    ACCESSIBILITY_ECHO_MODE_COUNT
};

enum accessibility_deletion_mode
{
    ACCESSIBILITY_DELETION_ANNOUNCE,
    ACCESSIBILITY_DELETION_CHARACTER,
    ACCESSIBILITY_DELETION_NONE,
    ACCESSIBILITY_DELETION_MODE_COUNT
};

enum accessibility_capitals_mode
{
    ACCESSIBILITY_CAPITALS_NONE,
    ACCESSIBILITY_CAPITALS_SPOKEN,
    ACCESSIBILITY_CAPITALS_PITCH,
    ACCESSIBILITY_CAPITALS_MODE_COUNT
};

struct accessibility_typing_echo_settings
{
    enum accessibility_echo_mode echo;
    enum accessibility_deletion_mode deletion;
    enum accessibility_capitals_mode capitals;
    int pitch_percent;
};

enum accessibility_typing_target
{
    ACCESSIBILITY_TYPING_NO_TARGET = -1,
    ACCESSIBILITY_TYPING_DONE = -2,
    ACCESSIBILITY_TYPING_DELETE = -3,
    ACCESSIBILITY_TYPING_CANCEL = -4,
    ACCESSIBILITY_TYPING_PAGE = -5,
    ACCESSIBILITY_TYPING_CURSOR_LEFT = -6,
    ACCESSIBILITY_TYPING_CURSOR_RIGHT = -7
};

enum accessibility_typing_input
{
    ACCESSIBILITY_TYPING_PRESS,
    ACCESSIBILITY_TYPING_CONTACT,
    ACCESSIBILITY_TYPING_RELEASE,
    ACCESSIBILITY_TYPING_POLL
};

struct accessibility_typing_result
{
    int focus;
    int commit;
    bool speak;
};

enum accessibility_typing_mode accessibility_typing_mode(void);
bool accessibility_typing_set_mode(enum accessibility_typing_mode mode);
int accessibility_typing_menu(void);
void accessibility_typing_get_echo_settings(struct accessibility_typing_echo_settings *settings);
bool accessibility_typing_set_echo_settings(const struct accessibility_typing_echo_settings *settings);
int accessibility_typing_echo_menu(void);
int accessibility_typing_deletion_menu(void);
int accessibility_typing_capitals_menu(void);
int accessibility_typing_capital_pitch_menu(void);
void accessibility_typing_speak_character(uint32_t character, bool enqueue);
uint32_t accessibility_typing_character_before(const char *text, int cursor);
bool accessibility_typing_echo_inserted(const char *text, int cursor);
void accessibility_typing_echo_deleted(uint32_t character);
void accessibility_typing_echo_finish(const char *text, int cursor);
void accessibility_typing_begin(void);
void accessibility_typing_end(void);
bool accessibility_typing_active(void);
bool accessibility_typing_needs_poll(void);
void accessibility_typing_cancel_touch(void);
int accessibility_typing_handle_touch(const struct touchevent *event, int context);
bool accessibility_typing_take_touch(struct touchevent *event);
struct accessibility_typing_result accessibility_typing_process(
    enum accessibility_typing_input input, int target, int point_x, int point_y,
    uint32_t now_ms);

#endif
