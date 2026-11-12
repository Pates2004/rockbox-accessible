/* Copyright (C) 2026 Patryk (Pates2004)
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "accessibility_power.h"
#include <string.h>

void accessibility_power_reset(struct accessibility_power *state)
{
    memset(state, 0, sizeof(*state));
}

static void power_context(struct accessibility_power *state, int context,
                          bool enabled)
{
    if (!enabled || !state->valid || state->context != context)
    {
        accessibility_power_reset(state);
        state->context = context;
        state->valid = enabled;
    }
}

bool accessibility_power_waiting(struct accessibility_power *state,
                                 int context, bool enabled)
{
    power_context(state, context, enabled);
    return enabled && state->clicks && !state->down;
}

enum accessibility_power_result accessibility_power_process(
    struct accessibility_power *state, enum accessibility_power_input input,
    int context, bool enabled, uint32_t now_ms)
{
    power_context(state, context, enabled);
    if (!enabled)
        return ACCESSIBILITY_POWER_PASS;
    if (state->have_time && now_ms - state->last >= UINT32_C(0x80000000))
    {
        accessibility_power_reset(state);
        state->context = context;
        state->valid = true;
        if (input != ACCESSIBILITY_POWER_PRESS &&
            input != ACCESSIBILITY_POWER_REPEAT)
            return ACCESSIBILITY_POWER_PASS;
    }
    state->last = now_ms;
    state->have_time = true;
    if (input == ACCESSIBILITY_POWER_OTHER)
    {
        accessibility_power_reset(state);
        return ACCESSIBILITY_POWER_PASS;
    }
    if (input == ACCESSIBILITY_POWER_IGNORE)
        return ACCESSIBILITY_POWER_PASS;
    if (input == ACCESSIBILITY_POWER_IDLE)
    {
        if (state->clicks && !state->down &&
            now_ms - state->released >= ACCESSIBILITY_POWER_CLICK_MS)
        {
            state->clicks = 0;
            return ACCESSIBILITY_POWER_REPLAY;
        }
        return ACCESSIBILITY_POWER_PASS;
    }
    if (input == ACCESSIBILITY_POWER_PRESS)
    {
        if (state->down)
            return ACCESSIBILITY_POWER_CONSUME;
        bool expired = state->clicks &&
            now_ms - state->released >= ACCESSIBILITY_POWER_CLICK_MS;
        if (expired)
            state->clicks = 0;
        state->down = true;
        state->held = false;
        state->pressed = now_ms;
        return expired ? ACCESSIBILITY_POWER_REPLAY : ACCESSIBILITY_POWER_CONSUME;
    }
    if (input == ACCESSIBILITY_POWER_REPEAT)
    {
        state->clicks = 0;
        state->held = true;
        return ACCESSIBILITY_POWER_PASS;
    }
    if (input == ACCESSIBILITY_POWER_RELEASE)
    {
        if (state->held || (state->down &&
            now_ms - state->pressed >= ACCESSIBILITY_POWER_CLICK_MS))
        {
            state->held = false;
            state->down = false;
            state->clicks = 0;
            return ACCESSIBILITY_POWER_PASS;
        }
        if (!state->down)
            return ACCESSIBILITY_POWER_CONSUME;
        state->down = false;
        state->released = now_ms;
        if (++state->clicks == 3)
        {
            state->clicks = 0;
            return ACCESSIBILITY_POWER_ACTIVATE;
        }
        return ACCESSIBILITY_POWER_CONSUME;
    }
    accessibility_power_reset(state);
    return ACCESSIBILITY_POWER_PASS;
}
