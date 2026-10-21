#include "accessibility_gesture.h"

enum accessibility_phase
{
    PHASE_WAITING,
    PHASE_STROKE,
    PHASE_EXPLORING,
    PHASE_HELD,
    PHASE_INVALID,
    PHASE_STROKE_HELD,
    PHASE_REPEATING
};

static struct accessibility_gesture_event no_event(void)
{
    return (struct accessibility_gesture_event){0};
}

static struct accessibility_gesture_event position_event(
    enum accessibility_gesture_type type, int32_t x, int32_t y)
{
    return (struct accessibility_gesture_event){
        .type = type, .stroke = ACCESSIBILITY_STROKE_NONE, .x = x, .y = y
    };
}

struct accessibility_gesture_config accessibility_gesture_default_config(void)
{
    return (struct accessibility_gesture_config){
        .tap_slop_px = 8,
        .stroke_min_px = 24,
        .tap_max_ms = 180,
        .double_tap_ms = 320,
        .explore_delay_ms = 220,
        .stroke_max_ms = 650,
        .long_hold_ms = 0,
        .triple_tap = false,
        .double_tap_hold_ms = 0,
        .stroke_hold_ms = 0,
        .repeat_interval_ms = 160,
        .repeat_strokes = 0
    };
}

static bool valid_config(const struct accessibility_gesture_config *config)
{
    const uint32_t strokes = (UINT32_C(1) << ACCESSIBILITY_STROKE_COUNT) - 2;
    return config->tap_slop_px > 0 &&
        config->stroke_min_px > config->tap_slop_px &&
        config->stroke_min_px <= INT32_MAX &&
        config->tap_max_ms > 0 &&
        config->double_tap_ms > 0 &&
        config->double_tap_ms <= INT32_MAX &&
        config->explore_delay_ms >= config->tap_max_ms &&
        config->stroke_max_ms >= config->explore_delay_ms &&
        config->stroke_max_ms <= INT32_MAX &&
        (config->long_hold_ms == 0 ||
         (config->long_hold_ms >= config->explore_delay_ms &&
           config->long_hold_ms <= INT32_MAX)) &&
        config->double_tap_hold_ms <= INT32_MAX &&
        config->stroke_hold_ms <= INT32_MAX &&
        config->repeat_interval_ms > 0 &&
        config->repeat_interval_ms <= INT32_MAX &&
        (config->repeat_strokes & ~strokes) == 0 &&
        (config->repeat_strokes == 0 || config->stroke_hold_ms > 0);
}

bool accessibility_gesture_init(struct accessibility_gesture *state,
                                const struct accessibility_gesture_config *config)
{
    if (!state)
        return false;

    struct accessibility_gesture_config requested = config ? *config :
        accessibility_gesture_default_config();
    *state = (struct accessibility_gesture){0};
    if (!valid_config(&requested))
        return false;

    state->config = requested;
    state->initialized = true;
    return true;
}

void accessibility_gesture_reset(struct accessibility_gesture *state)
{
    if (!state)
        return;

    struct accessibility_gesture_config config = state->config;
    bool initialized = state->initialized;
    *state = (struct accessibility_gesture){0};
    state->config = config;
    state->initialized = initialized;
}


bool accessibility_gesture_pending(const struct accessibility_gesture *state)
{
    return state && state->initialized && (state->active || state->pending_tap);
}

static bool accept_time(struct accessibility_gesture *state, uint32_t now_ms)
{
    if (state->have_time && now_ms - state->last_ms > INT32_MAX)
    {
        accessibility_gesture_reset(state);
        return false;
    }

    state->have_time = true;
    state->last_ms = now_ms;
    return true;
}

static uint64_t magnitude(int64_t distance)
{
    return distance < 0 ? (uint64_t)-distance : (uint64_t)distance;
}

static bool within_slop(const struct accessibility_gesture *state)
{
    return magnitude((int64_t)state->x - state->origin_x) <=
               state->config.tap_slop_px &&
           magnitude((int64_t)state->y - state->origin_y) <=
               state->config.tap_slop_px;
}

static enum accessibility_stroke direction(int64_t delta_x, int64_t delta_y,
                                            uint32_t minimum)
{
    uint64_t distance_x = magnitude(delta_x);
    uint64_t distance_y = magnitude(delta_y);

    if (distance_x < minimum && distance_y < minimum)
        return ACCESSIBILITY_STROKE_NONE;
    if (distance_x > 0 && distance_y <= distance_x / 2)
        return delta_x < 0 ? ACCESSIBILITY_STROKE_LEFT :
                             ACCESSIBILITY_STROKE_RIGHT;
    if (distance_y > 0 && distance_x <= distance_y / 2)
        return delta_y < 0 ? ACCESSIBILITY_STROKE_UP :
                             ACCESSIBILITY_STROKE_DOWN;
    return ACCESSIBILITY_STROKE_COUNT;
}

static enum accessibility_stroke combined_stroke(
    enum accessibility_stroke first, enum accessibility_stroke second)
{
    if (second == ACCESSIBILITY_STROKE_NONE)
        return first;

    unsigned int offset = (unsigned int)second - 1;
    if (second > first)
        --offset;
    return (enum accessibility_stroke)(ACCESSIBILITY_STROKE_LEFT_RIGHT +
        ((unsigned int)first - 1) * 3 + offset);
}

static void cancel_tap(struct accessibility_gesture *state)
{
    state->pending_tap = false;
    state->second_tap = false;
    state->second_hold = false;
    state->tap_count = 0;
}

static struct accessibility_gesture_event explore(
    struct accessibility_gesture *state)
{
    bool changed = state->phase != PHASE_EXPLORING ||
        state->x != state->explore_x || state->y != state->explore_y;
    state->phase = PHASE_EXPLORING;
    cancel_tap(state);
    if (!changed)
        return no_event();

    state->explore_x = state->x;
    state->explore_y = state->y;
    return position_event(ACCESSIBILITY_GESTURE_EXPLORE, state->x, state->y);
}

static void track_stroke(struct accessibility_gesture *state)
{
    int64_t delta_x = (int64_t)state->x - state->pivot_x;
    int64_t delta_y = (int64_t)state->y - state->pivot_y;
    enum accessibility_stroke current = state->second !=
        ACCESSIBILITY_STROKE_NONE ? state->second : state->first;
    enum accessibility_stroke next = direction(delta_x, delta_y,
                                                state->config.stroke_min_px);

    if (next == ACCESSIBILITY_STROKE_COUNT)
    {
        state->phase = PHASE_INVALID;
        return;
    }
    if (next != ACCESSIBILITY_STROKE_NONE && next != current)
    {
        if (state->second != ACCESSIBILITY_STROKE_NONE)
        {
            state->phase = PHASE_INVALID;
            return;
        }

        state->second = next;
        state->pivot_x = state->x;
        state->pivot_y = state->y;
        return;
    }

    if (((current == ACCESSIBILITY_STROKE_LEFT && delta_x < 0) ||
         (current == ACCESSIBILITY_STROKE_RIGHT && delta_x > 0)) &&
        magnitude(delta_y) <= state->config.tap_slop_px)
        state->pivot_x = state->x;
    else if (((current == ACCESSIBILITY_STROKE_UP && delta_y < 0) ||
              (current == ACCESSIBILITY_STROKE_DOWN && delta_y > 0)) &&
             magnitude(delta_x) <= state->config.tap_slop_px)
        state->pivot_y = state->y;
}

static bool within_endpoint(const struct accessibility_gesture *state)
{
    return magnitude((int64_t)state->x - state->endpoint_x) <=
               state->config.tap_slop_px &&
           magnitude((int64_t)state->y - state->endpoint_y) <=
               state->config.tap_slop_px;
}

static bool repeat_eligible(const struct accessibility_gesture *state)
{
    enum accessibility_stroke stroke = combined_stroke(state->first, state->second);
    return state->config.stroke_hold_ms != 0 &&
        (state->repeat_mask & (UINT32_C(1) << (unsigned int)stroke)) != 0;
}

static struct accessibility_gesture_event held_stroke(
    struct accessibility_gesture *state, uint32_t now_ms, bool released)
{
    if (!within_endpoint(state))
    {
        state->phase = PHASE_INVALID;
        state->repeat_mask = 0;
        return no_event();
    }
    if (released)
        return no_event();
    if (state->phase == PHASE_STROKE_HELD)
    {
        if (now_ms - state->movement_ms < state->config.stroke_hold_ms)
            return no_event();
        state->phase = PHASE_REPEATING;
        state->committed_stroke = combined_stroke(state->first, state->second);
        state->repeat_ms = now_ms;
        return (struct accessibility_gesture_event){
            .type = ACCESSIBILITY_GESTURE_STROKE, .stroke = state->committed_stroke
        };
    }
    if (now_ms - state->repeat_ms < state->config.repeat_interval_ms)
        return no_event();
    state->repeat_ms = now_ms;
    return (struct accessibility_gesture_event){
        .type = ACCESSIBILITY_GESTURE_STROKE, .stroke = state->committed_stroke,
        .repeat = true
    };
}

static struct accessibility_gesture_event advance_contact(
    struct accessibility_gesture *state, uint32_t now_ms, bool released)
{
    uint32_t elapsed = now_ms - state->press_ms;
    if (state->phase == PHASE_INVALID || state->phase == PHASE_HELD)
        return no_event();
    if (state->phase == PHASE_EXPLORING)
        return explore(state);
    if (state->phase == PHASE_STROKE_HELD || state->phase == PHASE_REPEATING)
        return held_stroke(state, now_ms, released);

    if (state->contact_ordinal == 3)
    {
        if (!within_slop(state) || elapsed > state->config.tap_max_ms)
        {
            state->phase = PHASE_INVALID;
            cancel_tap(state);
        }
        return no_event();
    }

    if (!within_slop(state))
    {
        state->moved = true;
        cancel_tap(state);
    }
    if (state->second_hold)
    {
        if (elapsed < state->config.double_tap_hold_ms)
            return no_event();
        state->phase = PHASE_HELD;
        cancel_tap(state);
        return position_event(ACCESSIBILITY_GESTURE_DOUBLE_TAP_HOLD, 0, 0);
    }
    if (!within_endpoint(state))
    {
        state->endpoint_x = state->x;
        state->endpoint_y = state->y;
        state->movement_ms = now_ms;
    }

    if (state->phase == PHASE_STROKE)
    {
        track_stroke(state);
        if (state->phase == PHASE_INVALID)
            return no_event();
        if (elapsed >= state->config.stroke_max_ms)
        {
            if (!repeat_eligible(state) ||
                state->movement_ms - state->press_ms >= state->config.stroke_max_ms)
                return explore(state);
            state->phase = PHASE_STROKE_HELD;
            return held_stroke(state, now_ms, released);
        }
        return no_event();
    }

    if (state->config.long_hold_ms != 0 && !state->moved &&
        elapsed >= state->config.long_hold_ms)
    {
        state->phase = PHASE_HELD;
        cancel_tap(state);
        return position_event(ACCESSIBILITY_GESTURE_LONG_HOLD, 0, 0);
    }
    if (elapsed >= state->config.explore_delay_ms)
    {
        if (state->config.long_hold_ms != 0 && !state->moved)
            return no_event();
        return explore(state);
    }

    enum accessibility_stroke first = direction(
        (int64_t)state->x - state->origin_x,
        (int64_t)state->y - state->origin_y, state->config.stroke_min_px);
    if (first == ACCESSIBILITY_STROKE_COUNT)
    {
        state->phase = PHASE_INVALID;
        cancel_tap(state);
    }
    else if (first != ACCESSIBILITY_STROKE_NONE)
    {
        state->phase = PHASE_STROKE;
        state->first = first;
        state->pivot_x = state->x;
        state->pivot_y = state->y;
        cancel_tap(state);
    }
    return no_event();
}

static struct accessibility_gesture_event expire_tap(
    struct accessibility_gesture *state, uint32_t now_ms)
{
    if (state->pending_tap &&
        now_ms - state->tap_ms > state->config.double_tap_ms)
    {
        struct accessibility_gesture_event event = state->tap_count == 2 ?
            position_event(ACCESSIBILITY_GESTURE_DOUBLE_TAP, 0, 0) :
            position_event(ACCESSIBILITY_GESTURE_SINGLE_TAP, state->tap_x, state->tap_y);
        cancel_tap(state);
        return event;
    }
    return no_event();
}

struct accessibility_gesture_event accessibility_gesture_poll(
    struct accessibility_gesture *state, uint32_t now_ms)
{
    if (!state || !state->initialized || !accept_time(state, now_ms))
        return no_event();
    if (state->active)
        return advance_contact(state, now_ms, false);
    return expire_tap(state, now_ms);
}

struct accessibility_gesture_event accessibility_gesture_process(
    struct accessibility_gesture *state, enum accessibility_touch_type type,
    int32_t x, int32_t y, uint32_t now_ms)
{
    if (!state || !state->initialized)
        return no_event();
    if (type != ACCESSIBILITY_TOUCH_PRESS &&
        type != ACCESSIBILITY_TOUCH_CONTACT &&
        type != ACCESSIBILITY_TOUCH_RELEASE)
    {
        accessibility_gesture_reset(state);
        return no_event();
    }
    if (type != ACCESSIBILITY_TOUCH_PRESS && !state->active)
        return no_event();
    if (!accept_time(state, now_ms))
        return no_event();

    if (type == ACCESSIBILITY_TOUCH_PRESS)
    {
        if (state->active)
        {
            state->phase = PHASE_INVALID;
            cancel_tap(state);
            return no_event();
        }

        struct accessibility_gesture_event event = expire_tap(state, now_ms);
        state->active = true;
        state->phase = PHASE_WAITING;
        state->press_ms = now_ms;
        state->movement_ms = now_ms;
        state->repeat_ms = 0;
        state->origin_x = state->x = x;
        state->origin_y = state->y = y;
        state->endpoint_x = x;
        state->endpoint_y = y;
        state->first = state->second = ACCESSIBILITY_STROKE_NONE;
        state->committed_stroke = ACCESSIBILITY_STROKE_NONE;
        state->moved = false;
        state->contact_ordinal = state->pending_tap ? (uint8_t)(state->tap_count + 1) : 1;
        state->second_tap = state->contact_ordinal == 2;
        state->second_hold = state->second_tap && state->config.double_tap_hold_ms != 0;
        state->repeat_mask = state->contact_ordinal == 1 ? state->config.repeat_strokes : 0;
        state->pending_tap = false;
        return event;
    }

    state->x = x;
    state->y = y;
    bool released = type == ACCESSIBILITY_TOUCH_RELEASE;
    if (released)
        state->active = false;
    struct accessibility_gesture_event event = advance_contact(state, now_ms, released);
    if (!released)
        return event;

    if (event.type != ACCESSIBILITY_GESTURE_NONE)
        return event;
    if (state->phase == PHASE_STROKE || state->phase == PHASE_STROKE_HELD)
    {
        event.type = ACCESSIBILITY_GESTURE_STROKE;
        event.stroke = combined_stroke(state->first, state->second);
        return event;
    }
    if (state->phase != PHASE_WAITING || state->moved ||
        now_ms - state->press_ms > state->config.tap_max_ms)
    {
        cancel_tap(state);
        return no_event();
    }
    if (state->contact_ordinal == 3)
    {
        cancel_tap(state);
        return position_event(ACCESSIBILITY_GESTURE_TRIPLE_TAP, 0, 0);
    }
    if (state->second_tap && !state->config.triple_tap)
    {
        cancel_tap(state);
        return position_event(ACCESSIBILITY_GESTURE_DOUBLE_TAP, 0, 0);
    }

    state->pending_tap = true;
    state->second_tap = false;
    state->second_hold = false;
    state->tap_count = state->contact_ordinal == 2 ? 2 : 1;
    state->tap_ms = now_ms;
    state->tap_x = state->origin_x;
    state->tap_y = state->origin_y;
    return no_event();
}
