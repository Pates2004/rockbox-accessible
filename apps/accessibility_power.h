/* Physical Power shortcut policy, independent of target and speech backend.
 * Copyright (C) 2026 Patryk (Pates2004)
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef ACCESSIBILITY_POWER_H
#define ACCESSIBILITY_POWER_H
#include <stdbool.h>
#include <stdint.h>

#define ACCESSIBILITY_POWER_CLICK_MS 300u
enum accessibility_power_input
{
    ACCESSIBILITY_POWER_OTHER,
    ACCESSIBILITY_POWER_PRESS,
    ACCESSIBILITY_POWER_RELEASE,
    ACCESSIBILITY_POWER_REPEAT,
    ACCESSIBILITY_POWER_IDLE,
    ACCESSIBILITY_POWER_IGNORE
};
enum accessibility_power_result
{
    ACCESSIBILITY_POWER_PASS,
    ACCESSIBILITY_POWER_CONSUME,
    ACCESSIBILITY_POWER_REPLAY,
    ACCESSIBILITY_POWER_ACTIVATE
};
struct accessibility_power
{
    uint32_t pressed, released, last;
    int context;
    unsigned char clicks;
    bool down, held, valid, have_time;
};

void accessibility_power_reset(struct accessibility_power *state);
bool accessibility_power_waiting(struct accessibility_power *state,
                                 int context, bool enabled);
enum accessibility_power_result accessibility_power_process(
    struct accessibility_power *state, enum accessibility_power_input input,
    int context, bool enabled, uint32_t now_ms);
#endif
