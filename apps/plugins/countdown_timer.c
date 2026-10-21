/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2026 Teun van Dalen
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This software is distributed on an "AS IS" basis, WITHOUT WARRANTY OF ANY
 * KIND, either express or implied.
 *
 ****************************************************************************/

#include "plugin.h"
#include "lib/pluginlib_actions.h"
#include "lib/pluginlib_exit.h"

const struct button_mapping *plugin_contexts[] = { pla_main_ctx };

#define MAX_MINUTES 99
#define MAX_SECONDS 59

typedef enum {
    STATE_SETUP,
    STATE_RUNNING,
    STATE_PAUSED,
    STATE_FINISHED,
} timer_state_t;

typedef struct {
    int set_minutes;
    int set_seconds;
    int current_field;
    long remaining_ticks;
    long last_tick;
    timer_state_t state;
} timer_ctx_t;

static void countdown_talk_selection(const timer_ctx_t *ctx)
{
    if (!talk_menus_enabled(rb->global_settings))
        return;

    int field = ctx->current_field == 0 ? VOICE_MINUTES : VOICE_SECONDS;
    int value = ctx->current_field == 0 ? ctx->set_minutes : ctx->set_seconds;
    if (rb->talk_id(field, false) >= 0)
        rb->talk_number(value, true);
}

static void countdown_talk_state(const timer_ctx_t *ctx)
{
    if (!talk_menus_enabled(rb->global_settings))
        return;

    int label;
    long duration;
    switch (ctx->state) {
        case STATE_SETUP:
            label = LANG_COUNTDOWN_TIMER_SET;
            duration = ctx->set_minutes * 60 + ctx->set_seconds;
            break;
        case STATE_PAUSED:
            label = LANG_COUNTDOWN_TIMER_PAUSED;
            duration = (ctx->remaining_ticks + HZ - 1) / HZ;
            break;
        case STATE_FINISHED:
            rb->talk_id(LANG_COUNTDOWN_TIMER_FINISHED, false);
            return;
        default:
            label = ctx->remaining_ticks < 0 ? LANG_COUNTDOWN_TIMER_OVERTIME
                                             : LANG_COUNTDOWN_TIMER_RUNNING;
            duration = (ctx->remaining_ticks + HZ - 1) / HZ;
            break;
    }
    if (ctx->remaining_ticks < 0 && ctx->state != STATE_SETUP)
        duration = -(ctx->remaining_ticks / HZ) +
                   (ctx->remaining_ticks % HZ != 0);
    if (rb->talk_id(label, false) < 0 ||
        rb->talk_value_decimal(duration, UNIT_TIME, 0, true) < 0)
        return;
    if (ctx->state == STATE_SETUP &&
        rb->talk_id(ctx->current_field == 0 ? VOICE_MINUTES : VOICE_SECONDS,
                    true) >= 0)
        rb->talk_number(ctx->current_field == 0 ? ctx->set_minutes
                                               : ctx->set_seconds, true);
}

static void countdown_cleanup(void)
{
    if (talk_menus_enabled(rb->global_settings))
        rb->talk_shutup();
}

static inline int get_button(void)
{
    return pluginlib_getaction(HZ / 10, plugin_contexts,
                               ARRAYLEN(plugin_contexts));
}

static void draw(const timer_ctx_t *ctx)
{
    char time_str[12];
    const char *status_str;
    int disp_min, disp_sec;
    int w, h, x, y;

    rb->lcd_clear_display();

    if (ctx->state == STATE_SETUP) {
        disp_min = ctx->set_minutes;
        disp_sec = ctx->set_seconds;
        if (ctx->current_field == 0)
            rb->snprintf(time_str, sizeof(time_str), "[%02d]:%02d",
                         disp_min, disp_sec);
        else
            rb->snprintf(time_str, sizeof(time_str), "%02d:[%02d]",
                         disp_min, disp_sec);
        status_str = rb->str(LANG_COUNTDOWN_TIMER_SET);
    } else if (ctx->state == STATE_FINISHED) {
        rb->snprintf(time_str, sizeof(time_str), "00:00");
        status_str = rb->str(LANG_COUNTDOWN_TIMER_FINISHED);
    } else {
        if (ctx->remaining_ticks >= 0) {
            int remaining_secs = (ctx->remaining_ticks + HZ - 1) / HZ;
            disp_min = remaining_secs / 60;
            disp_sec = remaining_secs % 60;
            rb->snprintf(time_str, sizeof(time_str), "%02d:%02d",
                         disp_min, disp_sec);
        } else {
            int over_secs = ((-ctx->remaining_ticks) + HZ - 1) / HZ;
            disp_min = over_secs / 60;
            disp_sec = over_secs % 60;
            rb->snprintf(time_str, sizeof(time_str), "-%02d:%02d",
                         disp_min, disp_sec);
        }

        if (ctx->state == STATE_RUNNING && ctx->remaining_ticks < 0)
            status_str = rb->str(LANG_COUNTDOWN_TIMER_OVERTIME);
        else if (ctx->state == STATE_RUNNING)
            status_str = rb->str(LANG_COUNTDOWN_TIMER_RUNNING);
        else
            status_str = rb->str(LANG_COUNTDOWN_TIMER_PAUSED);
    }

    /* Draw status string above center */
    rb->lcd_getstringsize(status_str, &w, &h);
    x = (LCD_WIDTH - w) / 2;
    y = (LCD_HEIGHT / 2) - h - 2;
    rb->lcd_putsxy(x, y, status_str);

    /* Draw time string at center */
    rb->lcd_getstringsize(time_str, &w, &h);
    x = (LCD_WIDTH - w) / 2;
    y = LCD_HEIGHT / 2;
    rb->lcd_putsxy(x, y, time_str);

    rb->lcd_update();
}

enum plugin_status plugin_start(const void *parameter)
{
    timer_ctx_t ctx = {
        .set_minutes     = 10,
        .set_seconds     = 0,
        .current_field   = 0,
        .remaining_ticks = 60 * HZ,
        .last_tick       = 0,
        .state           = STATE_SETUP,
    };
    bool overtime_alerted = false;
    int button;

    (void)parameter;

    atexit(countdown_cleanup);
    countdown_talk_state(&ctx);

    while (true) {
        if (ctx.state == STATE_RUNNING) {
            long now = *rb->current_tick;
            ctx.remaining_ticks -= now - ctx.last_tick;
            ctx.last_tick = now;

            if (ctx.remaining_ticks < 0 && !overtime_alerted) {
                overtime_alerted = true;
                ctx.state = STATE_FINISHED;
                draw(&ctx);
                int audio_status = rb->audio_status();
                bool resume_music = (audio_status & AUDIO_STATUS_PLAY) &&
                                    !(audio_status & AUDIO_STATUS_PAUSE);
                if (resume_music)
                    rb->audio_pause();
#ifdef HAVE_BACKLIGHT
                rb->backlight_on();
#endif
                rb->beep_play(1000, 200, 1000);
                rb->sleep(HZ / 4);
                rb->beep_play(1000, 200, 1000);
                rb->sleep(HZ / 4);
                rb->beep_play(1000, 400, 1000);
                rb->sleep(HZ + HZ / 2);
                if (resume_music)
                    rb->audio_resume();
                countdown_talk_state(&ctx);
                ctx.state = STATE_RUNNING;
                /* Reset last_tick so the beep/sleep time is not counted
                 * against remaining_ticks on the next iteration. */
                ctx.last_tick = *rb->current_tick;
            }
        }

        draw(&ctx);
        button = get_button();

        if (button == PLA_CANCEL || button == PLA_EXIT) {
            return PLUGIN_OK;
        }

        switch (ctx.state) {
            case STATE_SETUP: {
                bool time_changed = false;
                switch (button) {
#ifdef HAVE_SCROLLWHEEL
                    case PLA_SCROLL_FWD:
                    case PLA_SCROLL_FWD_REPEAT:
#endif
                    case PLA_UP:
                    case PLA_UP_REPEAT:
                        if (ctx.current_field == 0)
                            ctx.set_minutes = (ctx.set_minutes + 1) % (MAX_MINUTES + 1);
                        else
                            ctx.set_seconds = (ctx.set_seconds + 1) % (MAX_SECONDS + 1);
                        time_changed = true;
                        break;
#ifdef HAVE_SCROLLWHEEL
                    case PLA_SCROLL_BACK:
                    case PLA_SCROLL_BACK_REPEAT:
#endif
                    case PLA_DOWN:
                    case PLA_DOWN_REPEAT:
                        if (ctx.current_field == 0)
                            ctx.set_minutes = (ctx.set_minutes + MAX_MINUTES) % (MAX_MINUTES + 1);
                        else
                            ctx.set_seconds = (ctx.set_seconds + MAX_SECONDS) % (MAX_SECONDS + 1);
                        time_changed = true;
                        break;
                    case PLA_LEFT:
                    case PLA_LEFT_REPEAT:
                    case PLA_RIGHT:
                    case PLA_RIGHT_REPEAT:
                        ctx.current_field = (ctx.current_field + 1) % 2;
                        countdown_talk_selection(&ctx);
                        break;
                    case PLA_SELECT:
                        if (ctx.set_minutes > 0 || ctx.set_seconds > 0) {
                            ctx.remaining_ticks = (ctx.set_minutes * 60 + ctx.set_seconds) * HZ;
                            ctx.last_tick = *rb->current_tick;
                            ctx.state = STATE_RUNNING;
                            countdown_talk_state(&ctx);
                        }
                        break;
                    default:
                        exit_on_usb(button);
                        break;
                }
                if (time_changed) {
                    ctx.remaining_ticks = (ctx.set_minutes * 60 + ctx.set_seconds) * HZ;
                    countdown_talk_selection(&ctx);
                }
                break;
            }

            case STATE_RUNNING:
                switch (button) {
                    case PLA_SELECT:
                        ctx.state = STATE_PAUSED;
                        countdown_talk_state(&ctx);
                        break;
                    default:
                        exit_on_usb(button);
                        break;
                }
                break;

            case STATE_FINISHED:
                exit_on_usb(button);
                break;

            case STATE_PAUSED:
                switch (button) {
                    case PLA_SELECT:
                        ctx.last_tick = *rb->current_tick;
                        ctx.state = STATE_RUNNING;
                        countdown_talk_state(&ctx);
                        break;
                    case PLA_UP:
                    case PLA_UP_REPEAT:
                    case PLA_CANCEL:
                    case PLA_EXIT:
                        return PLUGIN_OK;
                    default:
                        exit_on_usb(button);
                        break;
                }
                break;
        }
    }
}
