#include "accessibility_buttons.h"
#include <string.h>

void accessibility_buttons_reset(struct accessibility_buttons *state)
{
    if (!state)
        return;
    uint16_t hold_ms = state->hold_ms;
    memset(state, 0, sizeof(*state));
    state->hold_ms = hold_ms;
}

bool accessibility_buttons_init(struct accessibility_buttons *state,
                                unsigned int hold_ms)
{
    if (!state || hold_ms < ACCESSIBILITY_BUTTON_HOLD_MIN ||
        hold_ms > ACCESSIBILITY_BUTTON_HOLD_MAX)
        return false;
    memset(state, 0, sizeof(*state));
    state->hold_ms = hold_ms;
    return true;
}

bool accessibility_buttons_pending(const struct accessibility_buttons *state)
{
    return state && (state->down || state->pending);
}

static struct accessibility_button_event button_recognized(
    struct accessibility_buttons *state, enum accessibility_button_slot slot,
    bool repeat)
{
    struct accessibility_button_event event = {
        true, true, repeat, state->button, slot
    };
    state->pending = false;
    state->clicks = 0;
    return event;
}

struct accessibility_button_event accessibility_buttons_process(
    struct accessibility_buttons *state, enum accessibility_button_input input,
    unsigned int button, unsigned int maximum_clicks, uint32_t now_ms)
{
    struct accessibility_button_event event = {0};
    if (!state)
        return event;
    if (input == ACCESSIBILITY_BUTTON_CANCEL)
    {
        accessibility_buttons_reset(state);
        state->blocked = true;
        return event;
    }
    if (state->have_time && now_ms - state->last_ms >= UINT32_C(0x80000000))
    {
        bool active = accessibility_buttons_pending(state);
        accessibility_buttons_reset(state);
        state->blocked = active;
        event.consumed = active;
        return event;
    }
    state->last_ms = now_ms;
    state->have_time = true;
    if (input == ACCESSIBILITY_BUTTON_POLL)
    {
        if (state->down && !state->held &&
            now_ms - state->press_ms >= state->hold_ms)
        {
            state->held = true;
            return button_recognized(state, ACCESSIBILITY_BUTTON_HOLD, false);
        }
        if (state->pending && !state->down &&
            now_ms - state->release_ms >= ACCESSIBILITY_BUTTON_CLICK_MS)
            return button_recognized(state,
                (enum accessibility_button_slot)(state->clicks - 1), false);
        return event;
    }
    if (button >= ACCESSIBILITY_BUTTON_COUNT || maximum_clicks < 1 ||
        maximum_clicks > 3 || input > ACCESSIBILITY_BUTTON_REPEAT)
    {
        accessibility_buttons_reset(state);
        return event;
    }
    if (state->blocked)
    {
        if (input != ACCESSIBILITY_BUTTON_PRESS)
        {
            event.consumed = true;
            return event;
        }
        state->blocked = false;
    }
    event.consumed = true;
    if (input == ACCESSIBILITY_BUTTON_PRESS)
    {
        if (state->down)
            return event;
        if (state->pending && (state->button != button ||
            now_ms - state->release_ms >= ACCESSIBILITY_BUTTON_CLICK_MS))
        {
            event = button_recognized(state,
                (enum accessibility_button_slot)(state->clicks - 1), false);
        }
        state->button = button;
        state->maximum_clicks = maximum_clicks;
        state->down = true;
        state->held = false;
        state->press_ms = now_ms;
        return event;
    }
    if (!state->down || state->button != button)
        return event;
    if (input == ACCESSIBILITY_BUTTON_REPEAT)
    {
        if (state->held)
            return button_recognized(state, ACCESSIBILITY_BUTTON_HOLD, true);
        if (now_ms - state->press_ms >= state->hold_ms)
        {
            state->held = true;
            return button_recognized(state, ACCESSIBILITY_BUTTON_HOLD, false);
        }
        return event;
    }
    state->down = false;
    if (state->held)
    {
        state->held = false;
        return event;
    }
    if (now_ms - state->press_ms >= state->hold_ms)
        return button_recognized(state, ACCESSIBILITY_BUTTON_HOLD, false);
    ++state->clicks;
    state->pending = true;
    state->release_ms = now_ms;
    if (state->clicks >= state->maximum_clicks)
        return button_recognized(state,
            (enum accessibility_button_slot)(state->clicks - 1), false);
    return event;
}
