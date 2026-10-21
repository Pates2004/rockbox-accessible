#ifndef ACCESSIBILITY_GESTURE_H
#define ACCESSIBILITY_GESTURE_H

#include <stdbool.h>
#include <stdint.h>

enum accessibility_touch_type
{
    ACCESSIBILITY_TOUCH_PRESS,
    ACCESSIBILITY_TOUCH_CONTACT,
    ACCESSIBILITY_TOUCH_RELEASE
};

enum accessibility_gesture_type
{
    ACCESSIBILITY_GESTURE_NONE,
    ACCESSIBILITY_GESTURE_EXPLORE,
    ACCESSIBILITY_GESTURE_SINGLE_TAP,
    ACCESSIBILITY_GESTURE_DOUBLE_TAP,
    ACCESSIBILITY_GESTURE_STROKE,
    ACCESSIBILITY_GESTURE_LONG_HOLD,
    ACCESSIBILITY_GESTURE_TRIPLE_TAP,
    ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD
};

enum accessibility_stroke
{
    ACCESSIBILITY_STROKE_NONE,
    ACCESSIBILITY_STROKE_LEFT,
    ACCESSIBILITY_STROKE_RIGHT,
    ACCESSIBILITY_STROKE_UP,
    ACCESSIBILITY_STROKE_DOWN,
    ACCESSIBILITY_STROKE_LEFT_RIGHT,
    ACCESSIBILITY_STROKE_LEFT_UP,
    ACCESSIBILITY_STROKE_LEFT_DOWN,
    ACCESSIBILITY_STROKE_RIGHT_LEFT,
    ACCESSIBILITY_STROKE_RIGHT_UP,
    ACCESSIBILITY_STROKE_RIGHT_DOWN,
    ACCESSIBILITY_STROKE_UP_LEFT,
    ACCESSIBILITY_STROKE_UP_RIGHT,
    ACCESSIBILITY_STROKE_UP_DOWN,
    ACCESSIBILITY_STROKE_DOWN_LEFT,
    ACCESSIBILITY_STROKE_DOWN_RIGHT,
    ACCESSIBILITY_STROKE_DOWN_UP,
    ACCESSIBILITY_STROKE_COUNT
};

struct accessibility_gesture_config
{
    uint32_t tap_slop_px;
    uint32_t stroke_min_px;
    uint32_t tap_max_ms;
    uint32_t double_tap_ms;
    uint32_t explore_delay_ms;
    uint32_t stroke_max_ms;
    uint32_t long_hold_ms;
    bool triple_tap;
    uint32_t double_tap_hold_ms;
    uint32_t stroke_hold_ms;
    uint32_t repeat_interval_ms;
    uint32_t repeat_strokes;
};

struct accessibility_gesture_event
{
    enum accessibility_gesture_type type;
    enum accessibility_stroke stroke;
    int32_t x;
    int32_t y;
    bool repeat;
};

struct accessibility_gesture
{
    struct accessibility_gesture_config config;
    uint32_t press_ms;
    uint32_t last_ms;
    uint32_t tap_ms;
    int32_t origin_x;
    int32_t origin_y;
    int32_t x;
    int32_t y;
    int32_t pivot_x;
    int32_t pivot_y;
    int32_t explore_x;
    int32_t explore_y;
    int32_t tap_x;
    int32_t tap_y;
    enum accessibility_stroke first;
    enum accessibility_stroke second;
    uint8_t phase;
    bool initialized;
    bool active;
    bool moved;
    bool pending_tap;
    bool second_tap;
    bool have_time;
    uint32_t movement_ms;
    uint32_t repeat_ms;
    uint32_t repeat_mask;
    int32_t endpoint_x;
    int32_t endpoint_y;
    enum accessibility_stroke committed_stroke;
    uint8_t tap_count;
    uint8_t contact_ordinal;
    bool second_hold;
};

struct accessibility_gesture_config accessibility_gesture_default_config(void);
bool accessibility_gesture_init(struct accessibility_gesture *state,
                                const struct accessibility_gesture_config *config);
void accessibility_gesture_reset(struct accessibility_gesture *state);
bool accessibility_gesture_pending(const struct accessibility_gesture *state);
struct accessibility_gesture_event accessibility_gesture_process(
    struct accessibility_gesture *state, enum accessibility_touch_type type,
    int32_t x, int32_t y, uint32_t now_ms);
struct accessibility_gesture_event accessibility_gesture_poll(
    struct accessibility_gesture *state, uint32_t now_ms);

#endif
