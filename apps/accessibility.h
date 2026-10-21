#ifndef ACCESSIBILITY_H
#define ACCESSIBILITY_H

#include <stdbool.h>

struct touchevent;

enum accessibility_empty_feedback
{
    ACCESSIBILITY_EMPTY_SOUND_ONLY,
    ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH,
    ACCESSIBILITY_EMPTY_SPEECH_ONLY
};

void accessibility_init(void);
bool accessibility_enabled(void);
bool accessibility_set_enabled(bool enabled);
int accessibility_adjust_timeout(int requested_timeout);
void accessibility_reset(void);
void accessibility_cancel_touch(void);
void accessibility_set_target(const void *target);
int accessibility_handle_touch(const struct touchevent *ev, int context);
bool accessibility_explore_point(int *x, int *y, bool *force);
void accessibility_explore_feedback(const void *owner, int target, bool occupied);
void accessibility_speak_empty(void);
enum accessibility_empty_feedback accessibility_empty_feedback_mode(void);
bool accessibility_empty_sound_enabled(void);
bool accessibility_empty_speech_enabled(void);
int accessibility_empty_feedback_menu(void);
int accessibility_menu(void);
int accessibility_touch_menu(void);
int accessibility_buttons_menu(void);
unsigned int accessibility_keyclick_sources(void);
int accessibility_keyclick_empty_pitch(void);
int accessibility_keyclick_menu(void);
int accessibility_keyclick_empty_menu(void);
int accessibility_keyclick_pitch_menu(void);
int accessibility_curtain_menu(void);
bool accessibility_set_curtain(bool enabled);
bool accessibility_set_curtain_state(bool enabled, bool announce);
bool accessibility_curtain_escape(int button);
void accessibility_curtain_clear_queue(void);
bool accessibility_handle_button(int button, int context, bool locked, int *action);
bool accessibility_button_is_repeat(void);
int accessibility_default_button_action(int button, int context, bool held_release);
int accessibility_process_pending(int event, int context);

#endif
