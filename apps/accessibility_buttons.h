#ifndef ACCESSIBILITY_BUTTONS_H
#define ACCESSIBILITY_BUTTONS_H

#include <stdbool.h>
#include <stdint.h>

#define ACCESSIBILITY_BUTTON_COUNT 5
#define ACCESSIBILITY_BUTTON_CLICK_MS 300
#define ACCESSIBILITY_BUTTON_HOLD_MIN 300
#define ACCESSIBILITY_BUTTON_HOLD_MAX 2000

enum accessibility_button_slot
{
    ACCESSIBILITY_BUTTON_SINGLE,
    ACCESSIBILITY_BUTTON_DOUBLE,
    ACCESSIBILITY_BUTTON_TRIPLE,
    ACCESSIBILITY_BUTTON_HOLD,
    ACCESSIBILITY_BUTTON_SLOT_COUNT
};

enum accessibility_button_input
{
    ACCESSIBILITY_BUTTON_PRESS,
    ACCESSIBILITY_BUTTON_RELEASE,
    ACCESSIBILITY_BUTTON_REPEAT,
    ACCESSIBILITY_BUTTON_POLL,
    ACCESSIBILITY_BUTTON_CANCEL
};

struct accessibility_button_event
{
    bool consumed;
    bool recognized;
    bool repeat;
    uint8_t button;
    enum accessibility_button_slot slot;
};

struct accessibility_buttons
{
    uint32_t press_ms;
    uint32_t release_ms;
    uint32_t last_ms;
    uint16_t hold_ms;
    uint8_t button;
    uint8_t clicks;
    uint8_t maximum_clicks;
    bool down;
    bool held;
    bool pending;
    bool have_time;
    bool blocked;
};

bool accessibility_buttons_init(struct accessibility_buttons *state,
                                unsigned int hold_ms);
void accessibility_buttons_reset(struct accessibility_buttons *state);
bool accessibility_buttons_pending(const struct accessibility_buttons *state);
struct accessibility_button_event accessibility_buttons_process(
    struct accessibility_buttons *state, enum accessibility_button_input input,
    unsigned int button, unsigned int maximum_clicks, uint32_t now_ms);

#endif
