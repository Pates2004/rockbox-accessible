#ifndef ACCESSIBILITY_SCREEN_H
#define ACCESSIBILITY_SCREEN_H

#include "config.h"
#include <stdbool.h>

bool accessibility_speak_time(bool enqueue);
bool accessibility_speak_date(bool enqueue);
void accessibility_speak_summary(bool enqueue);
void accessibility_speak_battery(bool enqueue);
void accessibility_screen_lock_changed(bool locked);
int accessibility_screen_unlock_menu(void);
int accessibility_screen_lock_menu(void);

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && \
    !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
bool accessibility_screen_unlock_any_button(void);
bool accessibility_screen_locked_buttons(void);
int accessibility_screen_autolock_timeout(void);
int accessibility_screen_unlock_any_button_menu(void);
int accessibility_screen_locked_buttons_menu(void);
int accessibility_screen_autolock_menu(void);
#else
static inline bool accessibility_screen_unlock_any_button(void) { return false; }
static inline bool accessibility_screen_locked_buttons(void) { return false; }
static inline int accessibility_screen_autolock_timeout(void) { return -1; }
static inline int accessibility_screen_unlock_any_button_menu(void) { return 0; }
static inline int accessibility_screen_locked_buttons_menu(void) { return 0; }
static inline int accessibility_screen_autolock_menu(void) { return 0; }
#endif

#endif
