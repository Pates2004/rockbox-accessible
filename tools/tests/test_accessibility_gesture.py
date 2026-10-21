"""Compile and exercise the shared accessible-touch state machine directly."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCES = ("apps/accessibility_gesture.c", "apps/accessibility_gesture.h",
           "tools/tests/test_accessibility_gesture.py",
           "tools/tests/fixtures/accessibility_gesture_extensions_fixture.c")

HARNESS = r"""
#include "accessibility_gesture.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;

static void expect_event(struct accessibility_gesture_event event,
                         enum accessibility_gesture_type type,
                         enum accessibility_stroke stroke, int32_t x, int32_t y)
{
    ++checks;
    if (event.type != type || event.stroke != stroke || event.x != x || event.y != y || event.repeat)
    {
        fprintf(stderr, "check %u: got %d/%d/%" PRId32 "/%" PRId32
                        ", expected %d/%d/%" PRId32 "/%" PRId32 "\n",
                checks, event.type, event.stroke, event.x, event.y,
                type, stroke, x, y);
        abort();
    }
}

static void expect_none(struct accessibility_gesture_event event)
{
    expect_event(event, ACCESSIBILITY_GESTURE_NONE, ACCESSIBILITY_STROKE_NONE, 0, 0);
}

static struct accessibility_gesture fresh(void)
{
    struct accessibility_gesture state;
    assert(accessibility_gesture_init(&state, 0));
    return state;
}

static void press(struct accessibility_gesture *state, int32_t x, int32_t y,
                  uint32_t now)
{
    expect_none(accessibility_gesture_process(state, ACCESSIBILITY_TOUCH_PRESS,
                                              x, y, now));
}

static void contact(struct accessibility_gesture *state, int32_t x, int32_t y,
                    uint32_t now)
{
    expect_none(accessibility_gesture_process(state, ACCESSIBILITY_TOUCH_CONTACT,
                                              x, y, now));
}

static void tap(struct accessibility_gesture *state, int32_t x, int32_t y,
                uint32_t now)
{
    press(state, x, y, now);
    expect_none(accessibility_gesture_process(state, ACCESSIBILITY_TOUCH_RELEASE,
                                              x, y, now + 20));
}

static void step(enum accessibility_stroke direction, int32_t amount,
                 int32_t *x, int32_t *y)
{
    switch (direction)
    {
    case ACCESSIBILITY_STROKE_LEFT: *x -= amount; break;
    case ACCESSIBILITY_STROKE_RIGHT: *x += amount; break;
    case ACCESSIBILITY_STROKE_UP: *y -= amount; break;
    case ACCESSIBILITY_STROKE_DOWN: *y += amount; break;
    default: abort();
    }
}

static enum accessibility_stroke pair_id(enum accessibility_stroke first,
                                          enum accessibility_stroke second)
{
    if (second == ACCESSIBILITY_STROKE_NONE)
        return first;
    unsigned int slot = 5;
    for (int outer = 1; outer <= 4; ++outer)
        for (int inner = 1; inner <= 4; ++inner)
            if (outer != inner)
            {
                if (outer == (int)first && inner == (int)second)
                    return (enum accessibility_stroke)slot;
                ++slot;
            }
    abort();
}

static void scenario_config(void)
{
    struct accessibility_gesture state = {0};
    struct accessibility_gesture_config config = accessibility_gesture_default_config();
    assert(config.tap_slop_px == 8 && config.stroke_min_px == 24);
    assert(config.tap_max_ms == 180 && config.double_tap_ms == 320);
    assert(config.explore_delay_ms == 220 && config.stroke_max_ms == 650);
    assert(config.long_hold_ms == 0 && ACCESSIBILITY_STROKE_COUNT == 17);
    assert(!accessibility_gesture_init(0, &config));
    accessibility_gesture_reset(0);
    expect_none(accessibility_gesture_poll(0, 1));
    expect_none(accessibility_gesture_process(0, ACCESSIBILITY_TOUCH_PRESS, 0, 0, 1));
    press(&state, 1, 2, 0);
    expect_none(accessibility_gesture_poll(&state, 1000));
    for (unsigned int invalid = 0; invalid < 14; ++invalid)
    {
        config = accessibility_gesture_default_config();
        switch (invalid)
        {
        case 0: config.tap_slop_px = 0; break;
        case 1: config.stroke_min_px = config.tap_slop_px; break;
        case 2: config.stroke_min_px = UINT32_MAX; break;
        case 3: config.tap_max_ms = 0; break;
        case 4: config.tap_max_ms = config.explore_delay_ms + 1; break;
        case 5: config.double_tap_ms = 0; break;
        case 6: config.double_tap_ms = UINT32_MAX; break;
        case 7: config.explore_delay_ms = config.stroke_max_ms + 1; break;
        case 8: config.stroke_max_ms = UINT32_MAX; break;
        case 9: config.long_hold_ms = config.explore_delay_ms - 1; break;
        case 10: config.long_hold_ms = UINT32_MAX; break;
        case 11: config.stroke_min_px = 0; break;
        case 12: config.explore_delay_ms = 0; break;
        case 13: config.stroke_max_ms = 0; break;
        default: abort();
        }
        assert(!accessibility_gesture_init(&state, &config));
        press(&state, 4, 5, 0);
        expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                  4, 5, 20));
        expect_none(accessibility_gesture_poll(&state, 1000));
    }
    config = accessibility_gesture_default_config();
    config.stroke_min_px = INT32_MAX;
    config.stroke_max_ms = INT32_MAX;
    config.double_tap_ms = INT32_MAX;
    config.long_hold_ms = INT32_MAX;
    assert(accessibility_gesture_init(&state, &config));
    assert(accessibility_gesture_init(&state, &state.config));
    assert(state.config.long_hold_ms == INT32_MAX);
}

static void scenario_taps(void)
{
    struct accessibility_gesture state = fresh();
    press(&state, 15, 27, 1000);
    contact(&state, 20, 30, 1010);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                              21, 31, 1020));
    expect_none(accessibility_gesture_poll(&state, 1340));
    expect_event(accessibility_gesture_poll(&state, 1341),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 15, 27);
    expect_none(accessibility_gesture_poll(&state, 2000));
    accessibility_gesture_reset(&state);
    tap(&state, 15, 27, 0);
    press(&state, 900, -400, 100);
    contact(&state, 902, -403, 110);
    expect_none(accessibility_gesture_poll(&state, 120));
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                               903, -402, 150),
                 ACCESSIBILITY_GESTURE_DOUBLE_TAP, ACCESSIBILITY_STROKE_NONE, 0, 0);
    expect_none(accessibility_gesture_poll(&state, 1000));
    tap(&state, 7, 8, 1100);
    expect_event(accessibility_gesture_poll(&state, 1441),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 7, 8);
    accessibility_gesture_reset(&state);
    tap(&state, 10, 11, 0);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_PRESS,
                                               300, 400, 341),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 10, 11);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                              300, 400, 350));
    expect_event(accessibility_gesture_poll(&state, 671),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 300, 400);
}

static void scenario_tap_boundaries(void)
{
    struct accessibility_gesture state = fresh();
    press(&state, 0, 0, 0);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 8, -8, 180));
    expect_event(accessibility_gesture_poll(&state, 501),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 0, 0);
    accessibility_gesture_reset(&state);
    press(&state, 0, 0, 0);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 0, 0, 181));
    expect_none(accessibility_gesture_poll(&state, 1000));
    accessibility_gesture_reset(&state);
    press(&state, 0, 0, 0);
    contact(&state, 9, 0, 10);
    contact(&state, 0, 0, 20);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 0, 0, 30));
    expect_none(accessibility_gesture_poll(&state, 1000));
    for (uint32_t late = 0; late <= 1; ++late)
    {
        accessibility_gesture_reset(&state);
        tap(&state, 10, 20, 0);
        press(&state, 1000, 2000, 300);
        struct accessibility_gesture_event event = accessibility_gesture_process(
            &state, ACCESSIBILITY_TOUCH_RELEASE, 1000, 2000, 340 + late);
        expect_event(event, ACCESSIBILITY_GESTURE_DOUBLE_TAP,
                     ACCESSIBILITY_STROKE_NONE, 0, 0);
        expect_none(accessibility_gesture_poll(&state, 662));
    }
    accessibility_gesture_reset(&state);
    tap(&state, 10, 20, 0);
    press(&state, 1000, 2000, 330);
    expect_none(accessibility_gesture_poll(&state, 341));
    expect_none(accessibility_gesture_poll(&state, 549));
    expect_event(accessibility_gesture_poll(&state, 550),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 1000, 2000);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                              1000, 2000, 560));
    expect_none(accessibility_gesture_poll(&state, 1000));
}

static void scenario_strokes(void)
{
    uint32_t seen = 0;
    for (int first = 1; first <= 4; ++first)
        for (int second = 0; second <= 4; ++second)
        {
            if (first == second)
                continue;
            struct accessibility_gesture state = fresh();
            int32_t x = 200;
            int32_t y = 200;
            press(&state, x, y, 0);
            step((enum accessibility_stroke)first, 23, &x, &y);
            contact(&state, x, y, 10);
            step((enum accessibility_stroke)first, 37, &x, &y);
            contact(&state, x, y, 20);
            step((enum accessibility_stroke)first, 17, &x, &y);
            contact(&state, x, y, 30);
            if (second != 0)
            {
                step((enum accessibility_stroke)second, 23, &x, &y);
                contact(&state, x, y, 40);
                step((enum accessibility_stroke)second, 1, &x, &y);
                contact(&state, x, y, 50);
                step((enum accessibility_stroke)second, 60, &x, &y);
                contact(&state, x, y, 60);
            }
            enum accessibility_stroke expected = pair_id(
                (enum accessibility_stroke)first, (enum accessibility_stroke)second);
            expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                       x, y, 100),
                         ACCESSIBILITY_GESTURE_STROKE, expected, 0, 0);
            seen |= UINT32_C(1) << (unsigned int)expected;
            expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                      x, y, 101));
            expect_none(accessibility_gesture_poll(&state, 1000));
        }
    assert(seen == UINT32_C(0x1fffe));
    for (int direction = 1; direction <= 4; ++direction)
    {
        struct accessibility_gesture state = fresh();
        int32_t x = 0;
        int32_t y = 0;
        press(&state, x, y, 0);
        step((enum accessibility_stroke)direction, 24, &x, &y);
        expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                   x, y, 20),
                     ACCESSIBILITY_GESTURE_STROKE,
                     (enum accessibility_stroke)direction, 0, 0);
    }
    struct accessibility_gesture state = fresh();
    press(&state, 0, 0, 0);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 23, 0, 20));
    expect_none(accessibility_gesture_poll(&state, 1000));
}

static void scenario_ambiguous(void)
{
    for (int sign_x = -1; sign_x <= 1; sign_x += 2)
        for (int sign_y = -1; sign_y <= 1; sign_y += 2)
        {
            struct accessibility_gesture state = fresh();
            press(&state, 0, 0, 0);
            contact(&state, sign_x * 40, sign_y * 21, 30);
            contact(&state, sign_x * 100, 0, 50);
            expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                      0, 0, 80));
            expect_none(accessibility_gesture_poll(&state, 1000));
            accessibility_gesture_reset(&state);
            press(&state, 0, 0, 0);
            expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                       sign_x * 40, sign_y * 20, 30),
                         ACCESSIBILITY_GESTURE_STROKE,
                         sign_x < 0 ? ACCESSIBILITY_STROKE_LEFT : ACCESSIBILITY_STROKE_RIGHT,
                         0, 0);
        }
    for (int first = 1; first <= 4; ++first)
        for (int second = 1; second <= 4; ++second)
            for (int third = 1; third <= 4; ++third)
            {
                if (first == second || second == third)
                    continue;
                struct accessibility_gesture state = fresh();
                int32_t x = 0;
                int32_t y = 0;
                press(&state, x, y, 0);
                step((enum accessibility_stroke)first, 60, &x, &y);
                contact(&state, x, y, 20);
                step((enum accessibility_stroke)second, 60, &x, &y);
                contact(&state, x, y, 40);
                step((enum accessibility_stroke)third, 24, &x, &y);
                contact(&state, x, y, 60);
                expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                          x, y, 100));
                expect_none(accessibility_gesture_poll(&state, 2000));
            }
    struct accessibility_gesture state = fresh();
    press(&state, 0, 0, 0);
    contact(&state, 60, 0, 20);
    contact(&state, 90, 30, 40);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 90, 30, 60));
    accessibility_gesture_reset(&state);
    press(&state, 0, 0, 0);
    for (int32_t point = 1; point <= 40; ++point)
        contact(&state, point, point, (uint32_t)point);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 40, 40, 50));
}

static void scenario_explore(void)
{
    struct accessibility_gesture state = fresh();
    press(&state, 30, 40, 0);
    expect_none(accessibility_gesture_poll(&state, 219));
    expect_event(accessibility_gesture_poll(&state, 220),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 30, 40);
    expect_none(accessibility_gesture_poll(&state, 221));
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_CONTACT, 31, 41, 240),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 31, 41);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_CONTACT, 31, 41, 260));
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_CONTACT, 200, 41, 280),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 200, 41);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 210, 42, 300),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 210, 42);
    expect_none(accessibility_gesture_poll(&state, 1000));
    accessibility_gesture_reset(&state);
    press(&state, 10, 20, 0);
    contact(&state, 25, 20, 100);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_CONTACT, 35, 20, 220),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 35, 20);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 35, 20, 240));
    for (uint32_t elapsed = 649; elapsed <= 650; ++elapsed)
    {
        accessibility_gesture_reset(&state);
        press(&state, 0, 0, 0);
        contact(&state, 100, 0, 20);
        struct accessibility_gesture_event event = accessibility_gesture_process(
            &state, ACCESSIBILITY_TOUCH_RELEASE, 100, 0, elapsed);
        if (elapsed == 649)
            expect_event(event, ACCESSIBILITY_GESTURE_STROKE, ACCESSIBILITY_STROKE_RIGHT, 0, 0);
        else
            expect_event(event, ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 100, 0);
    }
    accessibility_gesture_reset(&state);
    press(&state, 0, 0, 0);
    contact(&state, 100, 0, 20);
    expect_event(accessibility_gesture_poll(&state, 650),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 100, 0);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 100, 0, 660));
}

static void scenario_hold(void)
{
    struct accessibility_gesture state;
    struct accessibility_gesture_config config = accessibility_gesture_default_config();
    config.long_hold_ms = 600;
    assert(accessibility_gesture_init(&state, &config));
    press(&state, 300, 400, 0);
    expect_none(accessibility_gesture_poll(&state, 220));
    contact(&state, 301, 402, 599);
    expect_event(accessibility_gesture_poll(&state, 600),
                 ACCESSIBILITY_GESTURE_LONG_HOLD, ACCESSIBILITY_STROKE_NONE, 0, 0);
    expect_none(accessibility_gesture_poll(&state, 601));
    contact(&state, 1000, 2000, 700);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 1000, 2000, 800));
    expect_none(accessibility_gesture_poll(&state, 2000));
    accessibility_gesture_reset(&state);
    press(&state, 1, 2, 0);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 1, 2, 600),
                 ACCESSIBILITY_GESTURE_LONG_HOLD, ACCESSIBILITY_STROKE_NONE, 0, 0);
    accessibility_gesture_reset(&state);
    press(&state, 1, 2, 0);
    contact(&state, 10, 2, 10);
    expect_event(accessibility_gesture_poll(&state, 220),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 10, 2);
    expect_none(accessibility_gesture_poll(&state, 600));
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 10, 2, 700));
    accessibility_gesture_reset(&state);
    tap(&state, 1, 2, 0);
    press(&state, 30, 40, 100);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 30, 40, 120),
                 ACCESSIBILITY_GESTURE_DOUBLE_TAP, ACCESSIBILITY_STROKE_NONE, 0, 0);
}

static void scenario_cancel(void)
{
    struct accessibility_gesture state = fresh();
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 5, 6, 0));
    contact(&state, 5, 6, 1);
    tap(&state, 5, 6, 10);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 5, 6, 1000));
    expect_event(accessibility_gesture_poll(&state, 351),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 5, 6);
    for (unsigned int phase = 0; phase < 5; ++phase)
    {
        accessibility_gesture_reset(&state);
        tap(&state, 1, 2, 0);
        if (phase > 0)
        {
            press(&state, 100, 200, 100);
            if (phase == 2)
                contact(&state, 200, 200, 120);
            if (phase == 3)
                expect_event(accessibility_gesture_poll(&state, 320),
                             ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 100, 200);
            if (phase == 4)
                contact(&state, 200, 300, 120);
        }
        accessibility_gesture_reset(&state);
        expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 100, 200, 330));
        expect_none(accessibility_gesture_poll(&state, 1000));
        tap(&state, 7, 8, 1100);
        expect_event(accessibility_gesture_poll(&state, 1441),
                     ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 7, 8);
    }
    accessibility_gesture_reset(&state);
    press(&state, 1, 2, 0);
    press(&state, 100, 200, 10);
    contact(&state, 200, 200, 20);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 100, 200, 30));
    expect_none(accessibility_gesture_poll(&state, 1000));
    tap(&state, 7, 8, 1100);
    expect_none(accessibility_gesture_process(&state, (enum accessibility_touch_type)99, 0, 0, 1200));
    expect_none(accessibility_gesture_poll(&state, 2000));
}

static void scenario_wrap(void)
{
    struct accessibility_gesture state = fresh();
    uint32_t origin = UINT32_MAX - 40;
    tap(&state, 5, 6, origin);
    press(&state, -100, 400, origin + 100);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                               -100, 400, origin + 120),
                 ACCESSIBILITY_GESTURE_DOUBLE_TAP, ACCESSIBILITY_STROKE_NONE, 0, 0);
    accessibility_gesture_reset(&state);
    tap(&state, 5, 6, origin);
    expect_none(accessibility_gesture_poll(&state, origin + 340));
    expect_event(accessibility_gesture_poll(&state, origin + 341),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 5, 6);
    accessibility_gesture_reset(&state);
    press(&state, 0, 0, origin);
    contact(&state, 60, 0, origin + 20);
    contact(&state, 60, -60, origin + 60);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                               60, -60, origin + 80),
                 ACCESSIBILITY_GESTURE_STROKE, ACCESSIBILITY_STROKE_RIGHT_UP, 0, 0);
    accessibility_gesture_reset(&state);
    tap(&state, 1, 2, 100);
    expect_none(accessibility_gesture_poll(&state, 119));
    expect_none(accessibility_gesture_poll(&state, 1000));
    accessibility_gesture_reset(&state);
    press(&state, 1, 2, 0);
    expect_none(accessibility_gesture_poll(&state, UINT32_C(0x80000000)));
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 1, 2, 1));
    accessibility_gesture_reset(&state);
    press(&state, 1, 2, 0);
    expect_event(accessibility_gesture_poll(&state, INT32_MAX),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 1, 2);
}

static void scenario_extremes(void)
{
    struct accessibility_gesture state = fresh();
    press(&state, INT32_MIN, INT32_MAX, 0);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                               INT32_MAX, INT32_MAX, 20),
                 ACCESSIBILITY_GESTURE_STROKE, ACCESSIBILITY_STROKE_RIGHT, 0, 0);
    accessibility_gesture_reset(&state);
    press(&state, INT32_MAX, INT32_MIN, 0);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                               INT32_MIN, INT32_MIN, 20),
                 ACCESSIBILITY_GESTURE_STROKE, ACCESSIBILITY_STROKE_LEFT, 0, 0);
    accessibility_gesture_reset(&state);
    press(&state, INT32_MIN, INT32_MIN, 0);
    expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                              INT32_MAX, INT32_MAX, 20));
    accessibility_gesture_reset(&state);
    press(&state, INT32_MAX, INT32_MAX, 0);
    expect_event(accessibility_gesture_poll(&state, 220),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, INT32_MAX, INT32_MAX);
    expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_CONTACT,
                                               INT32_MIN, INT32_MIN, 230),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, INT32_MIN, INT32_MIN);
}

static void scenario_pending_stroke(void)
{
    for (int first = 1; first <= 4; ++first)
        for (int second = 0; second <= 4; ++second)
        {
            if (first == second)
                continue;
            struct accessibility_gesture state = fresh();
            tap(&state, 500, 500, 0);
            int32_t x = 0;
            int32_t y = 0;
            press(&state, x, y, 100);
            step((enum accessibility_stroke)first, 60, &x, &y);
            contact(&state, x, y, 120);
            if (second != 0)
            {
                step((enum accessibility_stroke)second, 60, &x, &y);
                contact(&state, x, y, 140);
            }
            expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                       x, y, 160),
                         ACCESSIBILITY_GESTURE_STROKE,
                         pair_id((enum accessibility_stroke)first,
                                 (enum accessibility_stroke)second), 0, 0);
            expect_none(accessibility_gesture_poll(&state, 1000));
        }
}

static void scenario_independent(void)
{
    struct accessibility_gesture first = fresh();
    struct accessibility_gesture second = fresh();
    struct accessibility_gesture_config config = accessibility_gesture_default_config();
    config.tap_slop_px = 1;
    config.stroke_min_px = 2;
    config.tap_max_ms = 10;
    config.double_tap_ms = 20;
    config.explore_delay_ms = 30;
    config.stroke_max_ms = 40;
    assert(accessibility_gesture_init(&second, &config));
    tap(&first, 100, 200, 0);
    press(&second, 0, 0, 0);
    expect_event(accessibility_gesture_process(&second, ACCESSIBILITY_TOUCH_RELEASE, 2, 0, 1),
                 ACCESSIBILITY_GESTURE_STROKE, ACCESSIBILITY_STROKE_RIGHT, 0, 0);
    accessibility_gesture_reset(&second);
    assert(second.config.stroke_min_px == 2);
    expect_event(accessibility_gesture_poll(&first, 341),
                 ACCESSIBILITY_GESTURE_SINGLE_TAP, ACCESSIBILITY_STROKE_NONE, 100, 200);
    press(&second, 0, 0, 0);
    expect_event(accessibility_gesture_poll(&second, 30),
                 ACCESSIBILITY_GESTURE_EXPLORE, ACCESSIBILITY_STROKE_NONE, 0, 0);
    expect_none(accessibility_gesture_poll(&first, 400));
}

static uint32_t random_word(uint32_t *seed)
{
    *seed = *seed * UINT32_C(1664525) + UINT32_C(1013904223);
    return *seed;
}

static void assert_safe(struct accessibility_gesture_event event)
{
    ++checks;
    assert(event.type >= ACCESSIBILITY_GESTURE_NONE && event.type <= ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD);
    assert(!event.repeat);
    if (event.type == ACCESSIBILITY_GESTURE_STROKE)
    {
        assert(event.stroke >= ACCESSIBILITY_STROKE_LEFT && event.stroke < ACCESSIBILITY_STROKE_COUNT);
        assert(event.x == 0 && event.y == 0);
    }
    else
        assert(event.stroke == ACCESSIBILITY_STROKE_NONE);
    if (event.type == ACCESSIBILITY_GESTURE_DOUBLE_TAP || event.type == ACCESSIBILITY_GESTURE_LONG_HOLD ||
        event.type == ACCESSIBILITY_GESTURE_TRIPLE_TAP || event.type == ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD)
        assert(event.x == 0 && event.y == 0);
}

static void scenario_stress(void)
{
    uint32_t seed = UINT32_C(0x456789ab);
    uint32_t now = UINT32_MAX - 1000;
    struct accessibility_gesture state = fresh();
    for (unsigned int trace = 0; trace < 30000; ++trace)
    {
        accessibility_gesture_reset(&state);
        int32_t x = (int32_t)(random_word(&seed) & INT32_MAX);
        int32_t y = (int32_t)(random_word(&seed) & INT32_MAX);
        press(&state, x, y, now);
        unsigned int samples = random_word(&seed) % 16;
        bool explored = false;
        for (unsigned int sample = 0; sample < samples; ++sample)
        {
            now += random_word(&seed) % 40;
            x = (int32_t)(random_word(&seed) & INT32_MAX);
            y = -(int32_t)(random_word(&seed) & INT32_MAX);
            struct accessibility_gesture_event event = accessibility_gesture_process(
                &state, ACCESSIBILITY_TOUCH_CONTACT, x, y, now);
            assert_safe(event);
            assert(event.type != ACCESSIBILITY_GESTURE_DOUBLE_TAP);
            assert(event.type != ACCESSIBILITY_GESTURE_STROKE);
            explored |= event.type == ACCESSIBILITY_GESTURE_EXPLORE;
            assert_safe(accessibility_gesture_poll(&state, now));
        }
        now += 1;
        struct accessibility_gesture_event event = accessibility_gesture_process(
            &state, ACCESSIBILITY_TOUCH_RELEASE, x, y, now);
        assert_safe(event);
        if (explored)
            assert(event.type != ACCESSIBILITY_GESTURE_STROKE);
        expect_none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, x, y, now));
        assert_safe(accessibility_gesture_poll(&state, now + 1000));
        now += 2000;
    }
    for (unsigned int trace = 0; trace < 10000; ++trace)
    {
        struct accessibility_gesture_config config = accessibility_gesture_default_config();
        config.tap_slop_px = random_word(&seed) % 12 + 1;
        config.stroke_min_px = config.tap_slop_px + random_word(&seed) % 30 + 1;
        assert(accessibility_gesture_init(&state, &config));
        enum accessibility_stroke first = (enum accessibility_stroke)(random_word(&seed) % 4 + 1);
        enum accessibility_stroke second = (enum accessibility_stroke)(random_word(&seed) % 5);
        if (second == first)
            second = ACCESSIBILITY_STROKE_NONE;
        int32_t x = (int32_t)(random_word(&seed) % 10000) - 5000;
        int32_t y = (int32_t)(random_word(&seed) % 10000) - 5000;
        now = random_word(&seed);
        press(&state, x, y, now);
        step(first, (int32_t)config.stroke_min_px, &x, &y);
        contact(&state, x, y, now + 10);
        if (second != ACCESSIBILITY_STROKE_NONE)
        {
            step(second, (int32_t)config.stroke_min_px, &x, &y);
            contact(&state, x, y, now + 20);
        }
        expect_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                   x, y, now + 30),
                     ACCESSIBILITY_GESTURE_STROKE, pair_id(first, second), 0, 0);
    }
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (strcmp(argv[1], "config") == 0) scenario_config();
    else if (strcmp(argv[1], "taps") == 0) scenario_taps();
    else if (strcmp(argv[1], "tap-boundaries") == 0) scenario_tap_boundaries();
    else if (strcmp(argv[1], "strokes") == 0) scenario_strokes();
    else if (strcmp(argv[1], "ambiguous") == 0) scenario_ambiguous();
    else if (strcmp(argv[1], "explore") == 0) scenario_explore();
    else if (strcmp(argv[1], "hold") == 0) scenario_hold();
    else if (strcmp(argv[1], "cancel") == 0) scenario_cancel();
    else if (strcmp(argv[1], "wrap") == 0) scenario_wrap();
    else if (strcmp(argv[1], "extremes") == 0) scenario_extremes();
    else if (strcmp(argv[1], "pending-stroke") == 0) scenario_pending_stroke();
    else if (strcmp(argv[1], "independent") == 0) scenario_independent();
    else if (strcmp(argv[1], "stress") == 0) scenario_stress();
    else abort();
    printf("%s: %u observable checks passed\n", argv[1], checks);
    return 0;
}
"""


class AccessibilityGestureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("A native C compiler is required")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = confined_path(
            central / "r1-gesture-extensions-20261016" / "gesture-core" /
            (stamp + "-" + uuid.uuid4().hex[:8]), central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.inputs = cls.source_hashes()
        cls.executables = {}
        cls.results = []
        cls.expected_negative_controls = 0
        cls.harness = cls.workspace / "gesture-test.c"
        cls.harness.write_text(HARNESS, encoding="utf-8")
        cls.write_json(cls.workspace / "inputs-before.json", cls.inputs)
        cls.addClassCleanup(cls.finish_report)
        print("Accessible gesture evidence:", cls.workspace, flush=True)

    @classmethod
    def source_hashes(cls):
        return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}

    @staticmethod
    def write_json(path, value):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")

    @classmethod
    def finish_report(cls):
        after = cls.source_hashes()
        stable = cls.inputs == after
        negative_controls = sum(result["expected_success"] is False for result in cls.results)
        cls.write_json(cls.workspace / "report.json", {
            "source_project": str(ROOT), "source_before": cls.inputs, "source_after": after,
            "sources_stable": stable, "commands": cls.results,
            "passed": stable and bool(cls.results) and all(result["passed"] for result in cls.results) and
                      negative_controls == cls.expected_negative_controls,
            "expected_negative_controls": cls.expected_negative_controls,
            "observed_negative_controls": negative_controls,
            "production_triple_contract": "Manager always enables triple_tap, including NONE; three qualifying contacts emit only TRIPLE_TAP. Manager dispatch is outside this fixture.",
            "gap_migration": {
                "preserved_trace": "First release20, second press300, second release340/341 ms",
                "previous_release341_result": "Pending single at second contact, observed at662 ms",
                "current_release341_result": "Double tap: second PRESS qualifies and remains latched",
                "qualification_boundary": "PRESS gap <=320 ms; pending expiry strictly >320 ms",
            },
            "physical_touchscreen_tested": False, "integration_tested": False,
        })
        if not stable:
            raise AssertionError("Gesture sources changed during validation")

    def execute(self, label, command, *, directory=None, expected_success=True):
        directory = directory or self.workspace
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=90,
                                env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
        (directory / (label + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
        (directory / (label + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
        record = {"label": label, "argv": command, "cwd": str(directory),
                  "returncode": result.returncode,
                  "expected_success": expected_success,
                  "passed": result.returncode == 0 if expected_success else
                            result.returncode != 0 and "extension check" in result.stderr,
                  "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
                  "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()}
        self.results.append(record)
        if expected_success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, "Negative control unexpectedly passed")
            self.assertIn("extension check", result.stderr)
        return result

    def variant(self, sanitizer, extensions=False, mutation=None):
        label = "c11-ubsan" if sanitizer else "c99-normal"
        if extensions:
            label = "extensions-" + label
        if mutation:
            label += "-negative-" + mutation[0]
        if label not in self.executables:
            directory = self.workspace / label
            directory.mkdir(exist_ok=False)
            executable = directory / ("gesture-test.exe" if os.name == "nt" else "gesture-test")
            source = ROOT / SOURCES[0]
            if mutation:
                name, before, after, scenario = mutation
                content = source.read_text(encoding="utf-8")
                self.assertEqual(content.count(before), 1, name)
                source = directory / "mutated-accessibility-gesture.c"
                source.write_text(content.replace(before, after), encoding="utf-8")
            harness = ROOT / SOURCES[3] if extensions else self.harness
            command = self.compiler + [
                "-std=" + ("c11" if sanitizer else "c99"), "-O1" if sanitizer else "-O2", "-g",
                "-Wall", "-Wextra", "-Werror", "-Wstrict-prototypes", "-Wmissing-prototypes",
                "-Wshadow", "-Wconversion", "-Wsign-conversion", "-Wvla", "-pedantic-errors",
                "-I", str(ROOT / "apps"), str(source), str(harness),
                "-o", str(executable),
            ]
            if sanitizer:
                command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            self.execute("compile", command, directory=directory)
            self.executables[label] = directory, executable
        return self.executables[label]

    def run_scenario(self, scenario, extensions=False):
        for sanitizer in (False, True):
            with self.subTest(scenario=scenario, sanitizer=sanitizer):
                directory, executable = self.variant(sanitizer, extensions)
                self.execute(scenario, [str(executable), scenario], directory=directory)

    def test_configuration_and_inert_uninitialized_state(self):
        self.run_scenario("config")

    def test_core_object_has_no_dynamic_allocation_dependencies(self):
        inspector = shutil.which("nm")
        if not inspector:
            self.skipTest("An object symbol inspector is required")
        directory = self.workspace / "allocation-check"
        directory.mkdir(exist_ok=False)
        object_path = directory / "accessibility-gesture.o"
        self.execute("compile", self.compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                     "-pedantic-errors", "-I", str(ROOT / "apps"), "-c", str(ROOT / SOURCES[0]),
                     "-o", str(object_path)], directory=directory)
        result = self.execute("undefined-symbols", [inspector, "-u", str(object_path)], directory=directory)
        symbols = {line.split()[-1].lstrip("_") for line in result.stdout.splitlines() if line.split()}
        forbidden = symbols & {"malloc", "calloc", "realloc", "free", "aligned_alloc", "alloca"}
        self.results[-1]["passed"] = not forbidden
        self.results[-1]["forbidden_allocation_symbols"] = sorted(forbidden)
        self.assertFalse(forbidden)

    def test_deferred_single_and_double_anywhere_preserve_focus(self):
        self.run_scenario("taps")

    def test_tap_slop_timeouts_and_pending_second_contact(self):
        self.run_scenario("tap-boundaries")

    def test_all_sixteen_strokes_and_release_only_emission(self):
        self.run_scenario("strokes")

    def test_diagonal_and_third_segment_cannot_activate(self):
        self.run_scenario("ambiguous")

    def test_slow_exploration_is_exclusive_and_position_changes_only(self):
        self.run_scenario("explore")

    def test_optional_hold_is_once_and_uses_current_focus(self):
        self.run_scenario("hold")

    def test_cancellation_duplicate_press_and_orphan_release(self):
        self.run_scenario("cancel")

    def test_timestamp_wrap_and_backward_time_cancellation(self):
        self.run_scenario("wrap")

    def test_full_int32_coordinate_range_without_overflow(self):
        self.run_scenario("extremes")

    def test_fast_strokes_after_pending_tap_never_activate_or_explore(self):
        self.run_scenario("pending-stroke")

    def test_multiple_states_and_configurations_are_independent(self):
        self.run_scenario("independent")

    def test_deterministic_stress_and_translated_threshold_strokes(self):
        self.run_scenario("stress")

    def test_extended_configuration_preserves_ids_and_rejects_invalid_repeat_masks(self):
        self.run_scenario("config", True)

    def test_press_gap_latches_at_deadline_with_independent_tap_duration(self):
        self.run_scenario("gap", True)

    def test_triple_pending_expiry_anywhere_and_mapping_dependent_latency(self):
        self.run_scenario("triple", True)

    def test_production_triple_reservation_never_emits_earlier_double(self):
        self.run_scenario("production-triple", True)

    def test_invalid_third_contact_is_consumed_without_focus_or_hold_fallback(self):
        self.run_scenario("third-invalid", True)

    def test_second_contact_hold_priority_boundary_and_standalone_independence(self):
        self.run_scenario("second-hold", True)

    def test_moved_multitap_continuation_never_arms_stroke_repeat(self):
        self.run_scenario("continuation", True)

    def test_all_sixteen_complete_held_shapes_repeat_and_release_silently(self):
        self.run_scenario("shapes", True)

    def test_endpoint_dwell_and_two_segment_window_precede_commit(self):
        self.run_scenario("dwell", True)

    def test_motion_at_deadline_or_after_candidate_cancels_repeat(self):
        self.run_scenario("movement", True)

    def test_repeat_mask_is_exact_and_latched_only_on_initial_press(self):
        self.run_scenario("masks", True)

    def test_repeats_schedule_from_now_without_bursts_or_trailing_release(self):
        self.run_scenario("repeat-clock", True)

    def test_release_reset_malformed_and_backward_input_precede_due_repeat(self):
        self.run_scenario("cancel", True)

    def test_pending_accessor_and_reset_clear_every_new_timer_and_sequence(self):
        self.run_scenario("reset", True)

    def test_new_gestures_wrap_and_reject_half_range_and_extreme_motion(self):
        self.run_scenario("wrap", True)

    def test_deterministic_extended_stress_has_exact_repeat_counts(self):
        self.run_scenario("stress", True)

    def test_negative_controls_detect_broken_recognition_and_repeat_policy(self):
        mutations = (
            ("gap-boundary", "now_ms - state->tap_ms > state->config.double_tap_ms",
             "now_ms - state->tap_ms >= state->config.double_tap_ms", "gap"),
            ("second-hold-latch", "if (state->second_hold)",
             "if (state->second_hold && now_ms - state->tap_ms <= state->config.double_tap_ms)", "second-hold"),
            ("early-double", "if (state->second_tap && !state->config.triple_tap)",
             "if (state->second_tap)", "triple"),
            ("continuation-repeat", "state->contact_ordinal == 1 ? state->config.repeat_strokes : 0",
             "state->config.repeat_strokes", "continuation"),
            ("dwell-origin", "now_ms - state->movement_ms < state->config.stroke_hold_ms",
             "now_ms - state->press_ms < state->config.stroke_hold_ms", "dwell"),
            ("release-precedence", "if (released)\n        return no_event();",
             "if (released && false)\n        return no_event();", "repeat-clock"),
            ("repeat-flag", ".repeat = true", ".repeat = false", "shapes"),
            ("catchup", "    state->repeat_ms = now_ms;\n    return (struct accessibility_gesture_event)",
             "    state->repeat_ms += state->config.repeat_interval_ms;\n    return (struct accessibility_gesture_event)",
             "repeat-clock"),
        )
        type(self).expected_negative_controls = len(mutations) * 2
        for mutation in mutations:
            for sanitizer in (False, True):
                with self.subTest(mutation=mutation[0], sanitizer=sanitizer):
                    directory, executable = self.variant(sanitizer, True, mutation)
                    self.execute(mutation[3], [str(executable), mutation[3]], directory=directory, expected_success=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
