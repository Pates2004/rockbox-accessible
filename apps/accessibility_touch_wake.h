#ifndef ACCESSIBILITY_TOUCH_WAKE_H
#define ACCESSIBILITY_TOUCH_WAKE_H

#include "config.h"
#include <stdbool.h>

struct touchevent;

enum accessibility_touch_wake_result
{
    ACCESSIBILITY_TOUCH_WAKE_PASS,
    ACCESSIBILITY_TOUCH_WAKE_CONSUMED,
    ACCESSIBILITY_TOUCH_WAKE_LIGHT,
    ACCESSIBILITY_TOUCH_WAKE_UNLOCK
};

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && \
    !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
bool accessibility_touch_wake_enabled(void);
int accessibility_touch_wake_timeout(int timeout);
void accessibility_touch_wake_cancel(void);
enum accessibility_touch_wake_result accessibility_touch_wake_process(
    const struct touchevent *event, bool locked, bool dark, int context);
int accessibility_touch_wake_menu(void);
#else
static inline bool accessibility_touch_wake_enabled(void) { return false; }
static inline int accessibility_touch_wake_timeout(int timeout) { return timeout; }
static inline void accessibility_touch_wake_cancel(void) { }
static inline enum accessibility_touch_wake_result accessibility_touch_wake_process(
    const struct touchevent *event, bool locked, bool dark, int context)
{
    (void)event;
    (void)locked;
    (void)dark;
    (void)context;
    return ACCESSIBILITY_TOUCH_WAKE_PASS;
}
static inline int accessibility_touch_wake_menu(void) { return 0; }
#endif

#endif
