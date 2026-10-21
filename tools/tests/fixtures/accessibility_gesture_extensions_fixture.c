#include "accessibility_gesture.h"
#include <inttypes.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int checks;

static void check(bool condition, int line)
{
    ++checks;
    if (!condition)
    {
        fprintf(stderr, "extension check %u failed at line %d\n", checks, line);
        exit(7);
    }
}

#define CHECK(condition) check((condition), __LINE__)

static void event_is(struct accessibility_gesture_event event,
                     enum accessibility_gesture_type type,
                     enum accessibility_stroke stroke, bool repeat)
{
    if (event.type != type || event.stroke != stroke || event.repeat != repeat)
        fprintf(stderr, "got %d/%d/%d, expected %d/%d/%d\n",
                event.type, event.stroke, event.repeat, type, stroke, repeat);
    CHECK(event.type == type && event.stroke == stroke && event.repeat == repeat);
    if (type != ACCESSIBILITY_GESTURE_SINGLE_TAP && type != ACCESSIBILITY_GESTURE_EXPLORE)
        CHECK(event.x == 0 && event.y == 0);
}

static void none(struct accessibility_gesture_event event)
{
    event_is(event, ACCESSIBILITY_GESTURE_NONE, ACCESSIBILITY_STROKE_NONE, false);
}

static void point(struct accessibility_gesture_event event,
                  enum accessibility_gesture_type type, int32_t point_x, int32_t point_y)
{
    event_is(event, type, ACCESSIBILITY_STROKE_NONE, false);
    CHECK(event.x == point_x && event.y == point_y);
}

static struct accessibility_gesture configured(bool triple)
{
    struct accessibility_gesture state;
    struct accessibility_gesture_config config = accessibility_gesture_default_config();
    config.triple_tap = triple;
    config.double_tap_hold_ms = 900;
    config.stroke_hold_ms = 900;
    config.repeat_strokes = UINT32_C(0x1fffe);
    CHECK(accessibility_gesture_init(&state, &config));
    return state;
}

static void press(struct accessibility_gesture *state, int32_t point_x,
                  int32_t point_y, uint32_t now)
{
    none(accessibility_gesture_process(state, ACCESSIBILITY_TOUCH_PRESS, point_x, point_y, now));
}

static void contact(struct accessibility_gesture *state, int32_t point_x,
                    int32_t point_y, uint32_t now)
{
    none(accessibility_gesture_process(state, ACCESSIBILITY_TOUCH_CONTACT, point_x, point_y, now));
}

static void tap(struct accessibility_gesture *state, int32_t point_x,
                int32_t point_y, uint32_t now)
{
    press(state, point_x, point_y, now);
    none(accessibility_gesture_process(state, ACCESSIBILITY_TOUCH_RELEASE, point_x, point_y, now + 20));
}

static void stroke_event(struct accessibility_gesture_event event,
                         enum accessibility_stroke stroke, bool repeat)
{
    event_is(event, ACCESSIBILITY_GESTURE_STROKE, stroke, repeat);
}

static void advance_point(enum accessibility_stroke direction,
                          int32_t *point_x, int32_t *point_y)
{
    switch (direction)
    {
    case ACCESSIBILITY_STROKE_LEFT: *point_x -= 60; break;
    case ACCESSIBILITY_STROKE_RIGHT: *point_x += 60; break;
    case ACCESSIBILITY_STROKE_UP: *point_y -= 60; break;
    case ACCESSIBILITY_STROKE_DOWN: *point_y += 60; break;
    default: exit(8);
    }
}

static enum accessibility_stroke shape_id(unsigned int first, unsigned int second)
{
    if (second == 0)
        return (enum accessibility_stroke)first;
    unsigned int identifier = 5;
    for (unsigned int outer = 1; outer <= 4; ++outer)
        for (unsigned int inner = 1; inner <= 4; ++inner)
            if (outer != inner)
            {
                if (outer == first && inner == second)
                    return (enum accessibility_stroke)identifier;
                ++identifier;
            }
    exit(8);
}

static void draw(struct accessibility_gesture *state, unsigned int first,
                 unsigned int second, uint32_t now, int32_t *point_x, int32_t *point_y)
{
    *point_x = 0;
    *point_y = 0;
    press(state, *point_x, *point_y, now);
    advance_point((enum accessibility_stroke)first, point_x, point_y);
    contact(state, *point_x, *point_y, now + 20);
    if (second != 0)
    {
        advance_point((enum accessibility_stroke)second, point_x, point_y);
        contact(state, *point_x, *point_y, now + 60);
    }
}

static void scenario_config(void)
{
    struct accessibility_gesture state = {0};
    struct accessibility_gesture_config config = accessibility_gesture_default_config();
    CHECK(ACCESSIBILITY_GESTURE_NONE == 0 && ACCESSIBILITY_GESTURE_LONG_HOLD == 5);
    CHECK(ACCESSIBILITY_GESTURE_TRIPLE_TAP == 6 && ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD == 7);
    CHECK(ACCESSIBILITY_STROKE_LEFT == 1 && ACCESSIBILITY_STROKE_DOWN_UP == 16);
    CHECK(offsetof(struct accessibility_gesture_event, repeat) > offsetof(struct accessibility_gesture_event, y));
    CHECK(offsetof(struct accessibility_gesture_config, triple_tap) > offsetof(struct accessibility_gesture_config, long_hold_ms));
    CHECK(!config.triple_tap && config.double_tap_hold_ms == 0 && config.stroke_hold_ms == 0);
    CHECK(config.repeat_strokes == 0 && config.repeat_interval_ms == 160);
    CHECK(!accessibility_gesture_pending(NULL) && !accessibility_gesture_pending(&state));
    for (unsigned int invalid = 0; invalid < 8; ++invalid)
    {
        config = accessibility_gesture_default_config();
        switch (invalid)
        {
        case 0: config.double_tap_hold_ms = UINT32_MAX; break;
        case 1: config.stroke_hold_ms = UINT32_MAX; break;
        case 2: config.repeat_interval_ms = 0; break;
        case 3: config.repeat_interval_ms = UINT32_MAX; break;
        case 4: config.repeat_strokes = 1; break;
        case 5: config.repeat_strokes = UINT32_C(1) << 17; break;
        case 6: config.repeat_strokes = UINT32_MAX; break;
        case 7: config.repeat_strokes = UINT32_C(1) << ACCESSIBILITY_STROKE_RIGHT; break;
        default: exit(8);
        }
        CHECK(!accessibility_gesture_init(&state, &config));
        CHECK(!accessibility_gesture_pending(&state));
        none(accessibility_gesture_poll(&state, 1000));
    }
    config = accessibility_gesture_default_config();
    config.double_tap_hold_ms = INT32_MAX;
    config.stroke_hold_ms = INT32_MAX;
    config.repeat_interval_ms = INT32_MAX;
    config.repeat_strokes = UINT32_C(0x1fffe);
    CHECK(accessibility_gesture_init(&state, &config));
    config.double_tap_hold_ms = 1;
    config.stroke_hold_ms = 1;
    config.repeat_interval_ms = 1;
    CHECK(accessibility_gesture_init(&state, &config));
}

static void scenario_gap(void)
{
    for (uint32_t gap = 319; gap <= 321; ++gap)
        for (uint32_t duration = 179; duration <= 181; ++duration)
        {
            struct accessibility_gesture state = configured(false);
            state.config.double_tap_hold_ms = 0;
            tap(&state, -10, 20, 0);
            uint32_t start = 20 + gap;
            struct accessibility_gesture_event event = accessibility_gesture_process(
                &state, ACCESSIBILITY_TOUCH_PRESS, 100, -200, start);
            if (gap <= 320)
                none(event);
            else
                point(event, ACCESSIBILITY_GESTURE_SINGLE_TAP, -10, 20);
            event = accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                                   100, -200, start + duration);
            if (gap <= 320 && duration <= 180)
                event_is(event, ACCESSIBILITY_GESTURE_DOUBLE_TAP, ACCESSIBILITY_STROKE_NONE, false);
            else
                none(event);
            event = accessibility_gesture_poll(&state, start + duration + 321);
            if (gap > 320 && duration <= 180)
                point(event, ACCESSIBILITY_GESTURE_SINGLE_TAP, 100, -200);
            else
                none(event);
            CHECK(!accessibility_gesture_pending(&state));
        }
}

static void scenario_triple(void)
{
    struct accessibility_gesture state = configured(true);
    tap(&state, INT32_MIN, INT32_MAX, 0);
    tap(&state, 1000, -2000, 100);
    CHECK(accessibility_gesture_pending(&state) && state.pending_tap);
    none(accessibility_gesture_poll(&state, 440));
    press(&state, INT32_MAX, INT32_MIN, 440);
    none(accessibility_gesture_poll(&state, 619));
    event_is(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                          INT32_MAX, INT32_MIN, 620),
             ACCESSIBILITY_GESTURE_TRIPLE_TAP, ACCESSIBILITY_STROKE_NONE, false);
    CHECK(!accessibility_gesture_pending(&state));
    none(accessibility_gesture_poll(&state, 1000));
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 0, 0, 1001));
    accessibility_gesture_reset(&state);
    tap(&state, 1, 2, 0);
    tap(&state, 3, 4, 100);
    event_is(accessibility_gesture_poll(&state, 441), ACCESSIBILITY_GESTURE_DOUBLE_TAP,
             ACCESSIBILITY_STROKE_NONE, false);
    none(accessibility_gesture_poll(&state, 442));
    accessibility_gesture_reset(&state);
    tap(&state, 1, 2, 0);
    tap(&state, 3, 4, 100);
    event_is(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_PRESS, 5, 6, 441),
             ACCESSIBILITY_GESTURE_DOUBLE_TAP, ACCESSIBILITY_STROKE_NONE, false);
    accessibility_gesture_reset(&state);
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 5, 6, 450));
    none(accessibility_gesture_poll(&state, 1000));
    state = configured(false);
    tap(&state, 1, 2, 0);
    press(&state, 3, 4, 100);
    event_is(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 3, 4, 120),
             ACCESSIBILITY_GESTURE_DOUBLE_TAP, ACCESSIBILITY_STROKE_NONE, false);
    tap(&state, 5, 6, 200);
    point(accessibility_gesture_poll(&state, 541), ACCESSIBILITY_GESTURE_SINGLE_TAP, 5, 6);
}

static void scenario_third_invalid(void)
{
    for (unsigned int invalid = 0; invalid < 5; ++invalid)
    {
        struct accessibility_gesture state = configured(true);
        state.config.long_hold_ms = 300;
        tap(&state, 1, 2, 0);
        tap(&state, 3, 4, 100);
        press(&state, 0, 0, 200);
        if (invalid == 0)
        {
            contact(&state, 9, 0, 210);
            contact(&state, 0, 0, 211);
        }
        else if (invalid == 1)
        {
            none(accessibility_gesture_poll(&state, 380));
            none(accessibility_gesture_poll(&state, 381));
        }
        else if (invalid == 2)
            press(&state, 0, 0, 210);
        else if (invalid == 3)
            none(accessibility_gesture_process(&state, (enum accessibility_touch_type)99, 0, 0, 210));
        none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 0, 0, 1100));
        none(accessibility_gesture_poll(&state, 2000));
        CHECK(!accessibility_gesture_pending(&state));
    }
}

static void scenario_production_triple(void)
{
    for (unsigned int wrapped = 0; wrapped < 2; ++wrapped)
    {
        struct accessibility_gesture state = configured(true);
        uint32_t origin = wrapped ? UINT32_MAX - 50 : 0;
        const uint32_t times[] = {0, 20, 340, 520, 840, 1020};
        unsigned int triples = 0;
        unsigned int doubles = 0;
        for (unsigned int index = 0; index < 6; ++index)
        {
            if (index == 4)
                none(accessibility_gesture_poll(&state, origin + times[index]));
            enum accessibility_touch_type type = index % 2 ?
                ACCESSIBILITY_TOUCH_RELEASE : ACCESSIBILITY_TOUCH_PRESS;
            int32_t point_x = (int32_t)(index / 2) * 100;
            struct accessibility_gesture_event event = accessibility_gesture_process(
                &state, type, point_x, -point_x, origin + times[index]);
            doubles += event.type == ACCESSIBILITY_GESTURE_DOUBLE_TAP ? 1U : 0U;
            triples += event.type == ACCESSIBILITY_GESTURE_TRIPLE_TAP ? 1U : 0U;
            if (index < 5)
                none(event);
            else
                event_is(event, ACCESSIBILITY_GESTURE_TRIPLE_TAP, ACCESSIBILITY_STROKE_NONE, false);
        }
        CHECK(triples == 1 && doubles == 0);
        none(accessibility_gesture_poll(&state, origin + 2000));
        CHECK(!accessibility_gesture_pending(&state));
    }
}

static void scenario_second_hold(void)
{
    for (unsigned int released = 0; released < 2; ++released)
    {
        struct accessibility_gesture state = configured(true);
        state.config.long_hold_ms = 300;
        tap(&state, 1, 2, 0);
        press(&state, 1000, -1000, 340);
        none(accessibility_gesture_poll(&state, 640));
        contact(&state, 1008, -1008, 1239);
        struct accessibility_gesture_event event = released ?
            accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 1008, -1008, 1240) :
            accessibility_gesture_poll(&state, 1240);
        event_is(event, ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD, ACCESSIBILITY_STROKE_NONE, false);
        none(accessibility_gesture_poll(&state, 1240));
        none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 1008, -1008, 1400));
        none(accessibility_gesture_poll(&state, 2000));
    }
    struct accessibility_gesture state = configured(true);
    tap(&state, 1, 2, 0);
    press(&state, 3, 4, 100);
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 3, 4, 999));
    none(accessibility_gesture_poll(&state, 2000));
    state = configured(true);
    state.config.long_hold_ms = 300;
    press(&state, 1, 2, 0);
    event_is(accessibility_gesture_poll(&state, 300), ACCESSIBILITY_GESTURE_LONG_HOLD,
             ACCESSIBILITY_STROKE_NONE, false);
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 1, 2, 900));
}

static void scenario_continuation(void)
{
    for (unsigned int held = 0; held < 2; ++held)
    {
        struct accessibility_gesture state = configured(true);
        tap(&state, 1, 2, 0);
        state.config.repeat_strokes = UINT32_C(0x1fffe);
        press(&state, 0, 0, 100);
        contact(&state, 60, 0, 120);
        if (held)
        {
            point(accessibility_gesture_poll(&state, 750), ACCESSIBILITY_GESTURE_EXPLORE, 60, 0);
            none(accessibility_gesture_poll(&state, 1200));
            none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 0, 1400));
        }
        else
            stroke_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 0, 160),
                         ACCESSIBILITY_STROKE_RIGHT, false);
        none(accessibility_gesture_poll(&state, 2000));
    }
    struct accessibility_gesture state = configured(false);
    state.config.double_tap_hold_ms = 0;
    tap(&state, 1, 2, 0);
    press(&state, 3, 4, 100);
    point(accessibility_gesture_poll(&state, 320), ACCESSIBILITY_GESTURE_EXPLORE, 3, 4);
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 3, 4, 1100));
}

static void scenario_shapes(void)
{
    uint32_t seen = 0;
    for (unsigned int first = 1; first <= 4; ++first)
        for (unsigned int second = 0; second <= 4; ++second)
        {
            if (first == second)
                continue;
            struct accessibility_gesture state = configured(false);
            enum accessibility_stroke stroke = shape_id(first, second);
            state.config.repeat_strokes = UINT32_C(1) << (unsigned int)stroke;
            int32_t point_x;
            int32_t point_y;
            draw(&state, first, second, 0, &point_x, &point_y);
            uint32_t committed = (second ? UINT32_C(60) : UINT32_C(20)) + 900;
            none(accessibility_gesture_poll(&state, 650));
            none(accessibility_gesture_poll(&state, committed - 1));
            stroke_event(accessibility_gesture_poll(&state, committed), stroke, false);
            none(accessibility_gesture_poll(&state, committed));
            none(accessibility_gesture_poll(&state, committed + 159));
            stroke_event(accessibility_gesture_poll(&state, committed + 160), stroke, true);
            stroke_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_CONTACT,
                                                       point_x, point_y, committed + 320), stroke, true);
            none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                               point_x, point_y, committed + 480));
            none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE,
                                               point_x, point_y, committed + 481));
            none(accessibility_gesture_poll(&state, committed + 1000));
            CHECK(!accessibility_gesture_pending(&state));
            seen |= UINT32_C(1) << (unsigned int)stroke;
        }
    CHECK(seen == UINT32_C(0x1fffe));
}

static void scenario_dwell(void)
{
    struct accessibility_gesture state = configured(false);
    int32_t point_x;
    int32_t point_y;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    contact(&state, 100, 0, 200);
    none(accessibility_gesture_poll(&state, 650));
    contact(&state, 108, 8, 700);
    none(accessibility_gesture_poll(&state, 1099));
    stroke_event(accessibility_gesture_poll(&state, 1100), ACCESSIBILITY_STROKE_RIGHT, false);
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 108, 8, 1260));
    state = configured(false);
    state.config.stroke_hold_ms = 300;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    none(accessibility_gesture_poll(&state, 320));
    contact(&state, 60, -60, 600);
    none(accessibility_gesture_poll(&state, 650));
    none(accessibility_gesture_poll(&state, 899));
    stroke_event(accessibility_gesture_poll(&state, 900), ACCESSIBILITY_STROKE_RIGHT_UP, false);
    state = configured(false);
    state.config.stroke_hold_ms = 300;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    none(accessibility_gesture_poll(&state, 320));
    stroke_event(accessibility_gesture_poll(&state, 650), ACCESSIBILITY_STROKE_RIGHT, false);
}

static void scenario_movement(void)
{
    struct accessibility_gesture state = configured(false);
    int32_t point_x;
    int32_t point_y;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    point(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_CONTACT, 84, 0, 650),
          ACCESSIBILITY_GESTURE_EXPLORE, 84, 0);
    none(accessibility_gesture_poll(&state, 2000));
    for (unsigned int committed = 0; committed < 2; ++committed)
    {
        state = configured(false);
        draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
        none(accessibility_gesture_poll(&state, 650));
        if (committed)
            stroke_event(accessibility_gesture_poll(&state, 920), ACCESSIBILITY_STROKE_RIGHT, false);
        contact(&state, 51, 0, 1080);
        contact(&state, 0, 0, 1100);
        none(accessibility_gesture_poll(&state, 1500));
        none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 0, 0, 1600));
        none(accessibility_gesture_poll(&state, 2000));
    }
    state = configured(false);
    press(&state, 0, 0, 0);
    contact(&state, 60, 60, 20);
    none(accessibility_gesture_poll(&state, 2000));
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 60, 2100));
    state = configured(false);
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, ACCESSIBILITY_STROKE_UP, 0, &point_x, &point_y);
    contact(&state, 0, -60, 80);
    none(accessibility_gesture_poll(&state, 2000));
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 0, -60, 2100));
}

static void scenario_masks(void)
{
    struct accessibility_gesture state = configured(false);
    state.config.repeat_strokes = UINT32_C(1) << ACCESSIBILITY_STROKE_UP;
    int32_t point_x;
    int32_t point_y;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    stroke_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 0, 100),
                 ACCESSIBILITY_STROKE_RIGHT, false);
    accessibility_gesture_reset(&state);
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    point(accessibility_gesture_poll(&state, 650), ACCESSIBILITY_GESTURE_EXPLORE, 60, 0);
    none(accessibility_gesture_poll(&state, 2000));
    state = configured(false);
    state.config.repeat_strokes = 0;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    state.config.repeat_strokes = UINT32_C(0x1fffe);
    point(accessibility_gesture_poll(&state, 650), ACCESSIBILITY_GESTURE_EXPLORE, 60, 0);
    none(accessibility_gesture_poll(&state, 2000));
    accessibility_gesture_reset(&state);
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    stroke_event(accessibility_gesture_poll(&state, 920), ACCESSIBILITY_STROKE_RIGHT, false);
}

static void scenario_repeat_clock(void)
{
    struct accessibility_gesture state = configured(false);
    int32_t point_x;
    int32_t point_y;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    stroke_event(accessibility_gesture_poll(&state, 920), ACCESSIBILITY_STROKE_RIGHT, false);
    stroke_event(accessibility_gesture_poll(&state, 10920), ACCESSIBILITY_STROKE_RIGHT, true);
    none(accessibility_gesture_poll(&state, 10920));
    none(accessibility_gesture_poll(&state, 11079));
    stroke_event(accessibility_gesture_poll(&state, 11080), ACCESSIBILITY_STROKE_RIGHT, true);
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 0, 11240));
    none(accessibility_gesture_poll(&state, 20000));
    state = configured(false);
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    none(accessibility_gesture_poll(&state, 650));
    stroke_event(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 0, 920),
                 ACCESSIBILITY_STROKE_RIGHT, false);
    none(accessibility_gesture_poll(&state, 1080));
}

static void scenario_cancel(void)
{
    for (unsigned int reason = 0; reason < 5; ++reason)
    {
        struct accessibility_gesture state = configured(false);
        int32_t point_x;
        int32_t point_y;
        draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
        stroke_event(accessibility_gesture_poll(&state, 920), ACCESSIBILITY_STROKE_RIGHT, false);
        if (reason == 0)
            accessibility_gesture_reset(&state);
        else if (reason == 1)
            none(accessibility_gesture_process(&state, (enum accessibility_touch_type)99, 60, 0, 1080));
        else if (reason == 2)
            press(&state, 60, 0, 1080);
        else if (reason == 3)
            contact(&state, 69, 0, 1080);
        else
            none(accessibility_gesture_poll(&state, 919));
        none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 0, 1080));
        none(accessibility_gesture_poll(&state, 2000));
    }
}

static void scenario_reset(void)
{
    for (unsigned int phase = 0; phase < 7; ++phase)
    {
        struct accessibility_gesture state = configured(true);
        if (phase < 4)
        {
            tap(&state, 1, 2, 0);
            if (phase > 0)
                press(&state, 3, 4, 100);
            if (phase > 1)
                none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 3, 4, 120));
            if (phase > 2)
                press(&state, 5, 6, 200);
        }
        else
        {
            int32_t point_x;
            int32_t point_y;
            draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
            if (phase > 4)
                none(accessibility_gesture_poll(&state, 650));
            if (phase > 5)
                stroke_event(accessibility_gesture_poll(&state, 920), ACCESSIBILITY_STROKE_RIGHT, false);
        }
        CHECK(accessibility_gesture_pending(&state));
        accessibility_gesture_reset(&state);
        CHECK(!accessibility_gesture_pending(&state));
        CHECK(!state.pending_tap && !state.second_tap && !state.second_hold);
        CHECK(state.tap_count == 0 && state.contact_ordinal == 0 && state.repeat_mask == 0);
        CHECK(state.movement_ms == 0 && state.repeat_ms == 0);
        CHECK(state.endpoint_x == 0 && state.endpoint_y == 0 && state.committed_stroke == 0);
        CHECK(state.config.triple_tap && state.config.stroke_hold_ms == 900);
        contact(&state, 60, 0, 2000);
        none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 60, 0, 2001));
        none(accessibility_gesture_poll(&state, 3000));
    }
}

static void scenario_wrap(void)
{
    uint32_t origin = UINT32_MAX - 100;
    struct accessibility_gesture state = configured(true);
    tap(&state, 1, 2, origin);
    tap(&state, 3, 4, origin + 100);
    press(&state, 5, 6, origin + 200);
    event_is(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, 5, 6, origin + 220),
             ACCESSIBILITY_GESTURE_TRIPLE_TAP, ACCESSIBILITY_STROKE_NONE, false);
    state = configured(false);
    tap(&state, 1, 2, origin);
    press(&state, 3, 4, origin + 100);
    event_is(accessibility_gesture_poll(&state, origin + 1000), ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD,
             ACCESSIBILITY_STROKE_NONE, false);
    state = configured(false);
    int32_t point_x;
    int32_t point_y;
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, origin, &point_x, &point_y);
    stroke_event(accessibility_gesture_poll(&state, origin + 920), ACCESSIBILITY_STROKE_RIGHT, false);
    stroke_event(accessibility_gesture_poll(&state, origin + 1080), ACCESSIBILITY_STROKE_RIGHT, true);
    none(accessibility_gesture_poll(&state, origin + 1079));
    CHECK(!accessibility_gesture_pending(&state));
    draw(&state, ACCESSIBILITY_STROKE_RIGHT, 0, 0, &point_x, &point_y);
    none(accessibility_gesture_poll(&state, UINT32_C(0x80000014)));
    CHECK(!accessibility_gesture_pending(&state));
    state = configured(false);
    press(&state, INT32_MIN, INT32_MAX, 0);
    contact(&state, INT32_MAX, INT32_MAX, 20);
    stroke_event(accessibility_gesture_poll(&state, 920), ACCESSIBILITY_STROKE_RIGHT, false);
    none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, INT32_MIN, INT32_MIN, 1080));
}

static uint32_t random_word(uint32_t *seed)
{
    *seed = *seed * UINT32_C(1664525) + UINT32_C(1013904223);
    return *seed;
}

static void scenario_stress(void)
{
    uint32_t seed = UINT32_C(0x41f39bad);
    for (unsigned int trace = 0; trace < 4000; ++trace)
    {
        struct accessibility_gesture state = configured(false);
        unsigned int first = random_word(&seed) % 4 + 1;
        unsigned int second = random_word(&seed) % 5;
        if (first == second)
            second = 0;
        enum accessibility_stroke stroke = shape_id(first, second);
        uint32_t origin = random_word(&seed);
        int32_t point_x;
        int32_t point_y;
        draw(&state, first, second, origin, &point_x, &point_y);
        uint32_t now = origin + (second ? UINT32_C(60) : UINT32_C(20)) + 900;
        stroke_event(accessibility_gesture_poll(&state, now), stroke, false);
        for (unsigned int repeated = 0; repeated < 5; ++repeated)
        {
            now += 160 + random_word(&seed) % 2000;
            stroke_event(accessibility_gesture_poll(&state, now), stroke, true);
            none(accessibility_gesture_poll(&state, now));
        }
        none(accessibility_gesture_process(&state, ACCESSIBILITY_TOUCH_RELEASE, point_x, point_y, now + 160));
        none(accessibility_gesture_poll(&state, now + 1000));
    }
}

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    if (strcmp(argv[1], "config") == 0) scenario_config();
    else if (strcmp(argv[1], "gap") == 0) scenario_gap();
    else if (strcmp(argv[1], "triple") == 0) scenario_triple();
    else if (strcmp(argv[1], "third-invalid") == 0) scenario_third_invalid();
    else if (strcmp(argv[1], "production-triple") == 0) scenario_production_triple();
    else if (strcmp(argv[1], "second-hold") == 0) scenario_second_hold();
    else if (strcmp(argv[1], "continuation") == 0) scenario_continuation();
    else if (strcmp(argv[1], "shapes") == 0) scenario_shapes();
    else if (strcmp(argv[1], "dwell") == 0) scenario_dwell();
    else if (strcmp(argv[1], "movement") == 0) scenario_movement();
    else if (strcmp(argv[1], "masks") == 0) scenario_masks();
    else if (strcmp(argv[1], "repeat-clock") == 0) scenario_repeat_clock();
    else if (strcmp(argv[1], "cancel") == 0) scenario_cancel();
    else if (strcmp(argv[1], "reset") == 0) scenario_reset();
    else if (strcmp(argv[1], "wrap") == 0) scenario_wrap();
    else if (strcmp(argv[1], "stress") == 0) scenario_stress();
    else exit(8);
    printf("%s: %u observable extension checks passed\n", argv[1], checks);
    return 0;
}
