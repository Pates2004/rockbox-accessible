/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2010 Clément Pit-Claudel
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



const struct button_mapping *plugin_contexts[] = { pla_main_ctx };

static int current = 0;
static bool tomorrow = false;
static int alarms[2] = {0, 0}, maxval[2] = {24, 60}, prev_tick = 3600 * 24;
static bool quit = false, usb = false, waiting = false, done = false;

static void alarm_talk_field(void)
{
    if (!talk_menus_enabled(rb->global_settings))
        return;

    if (rb->talk_id(current == 0 ? VOICE_HOURS : VOICE_MINUTES, false) >= 0)
        rb->talk_number(alarms[current], true);
}

static void alarm_talk_time(bool armed)
{
    if (!talk_menus_enabled(rb->global_settings))
        return;

    struct tm alarm_time = {0};
    alarm_time.tm_hour = alarms[0];
    alarm_time.tm_min = alarms[1];
    if (rb->talk_id(armed ? LANG_ALARMCLOCK_ARMED : LANG_ALARMCLOCK, false) < 0)
        return;
    if (!armed && rb->talk_id(LANG_EDIT, true) < 0)
        return;
    rb->talk_time(&alarm_time, true);
    if (!armed &&
        rb->talk_id(current == 0 ? VOICE_HOURS : VOICE_MINUTES, true) >= 0)
        rb->talk_number(alarms[current], true);
}

static inline int get_button(void)
{
    return pluginlib_getaction(HZ/2, plugin_contexts,
                               ARRAYLEN(plugin_contexts));
}

static int rem_seconds(void)
{
    int seconds = (((alarms[0] - rb->get_time()->tm_hour) * 3600)
                  +((alarms[1] - rb->get_time()->tm_min)  * 60)
                  -(rb->get_time()->tm_sec));

    /* The tomorrow flag means that the alarm should ring on the next day */
    if (seconds > prev_tick) tomorrow = false;
    prev_tick = seconds;

    return seconds + (tomorrow ? 24 * 3600 : 0);
}

static void draw_centered_string(struct screen * display, char * string)
{
    int w, h;
    display->getstringsize(string, &w, &h);

    if (w > display->lcdwidth || h > display->lcdheight) {
        display->puts_scroll(0, 0, string);
        display->update();
    } else {
        display->putsxy((display->lcdwidth - w) / 2,
                        (display->lcdheight - h) / 2,
                        string);
        display->update();
    }
}

static void draw(struct screen * display)
{
    char info[128];
    display->clear_display();

    int secs = rem_seconds();

    if (waiting)
        rb->snprintf(info, sizeof(info), "%s: %02d:%02d:%02d",
                           rb->str(LANG_ALARMCLOCK_ARMED),
                           secs / 3600, (secs / 60) % 60, secs % 60);
    else {
        if (current == 0)
            rb->snprintf(info, sizeof(info), "%s: [%02d]:%02d",
                         rb->str(LANG_ALARMCLOCK), alarms[0], alarms[1]);
        else
            rb->snprintf(info, sizeof(info), "%s: %02d:[%02d]",
                         rb->str(LANG_ALARMCLOCK), alarms[0], alarms[1]);
    }
    draw_centered_string(display, info);
}

static bool can_play(void)
{
    int audio_status = rb->audio_status();
    if ((!audio_status && rb->global_status->resume_index != -1)
        && (rb->playlist_resume() != -1)) {
        return true;
    }
    else if (audio_status & AUDIO_STATUS_PLAY)
        return true;

    return false;
}

static void resume_audio(void)
{
    int audio_status = rb->audio_status();
    if (!audio_status && rb->global_status->resume_index != -1) {
        if (rb->playlist_resume() != -1) {
            rb->playlist_resume_track(rb->global_status->resume_index,
                rb->global_status->resume_crc32,
                rb->global_status->resume_elapsed,
                rb->global_status->resume_offset);
        }
    }
    else if (audio_status & AUDIO_STATUS_PLAY)
        rb->audio_resume();
}

static void pause_audio(void)
{
    if (rb->audio_status() & AUDIO_STATUS_PLAY)
        rb->audio_pause();
}

enum plugin_status plugin_start(const void* parameter)
{
    int button;
    (void)parameter;

    if (!can_play()) {
        rb->splash(HZ*2, ID2P(LANG_NOTHING_TO_RESUME));
        return PLUGIN_ERROR;
    }
    pause_audio();
    alarm_talk_time(false);

    while(!quit) {
        FOR_NB_SCREENS(i) {
            draw(rb->screens[i]);
        }
        button = get_button();

#if (CONFIG_KEYPAD == IPOD_1G2G_PAD) \
    || (CONFIG_KEYPAD == IPOD_3G_PAD) \
    || (CONFIG_KEYPAD == IPOD_4G_PAD)
        if (button == PLA_EXIT || button == PLA_CANCEL || button == PLA_UP)
#else
        if (button == PLA_EXIT || button == PLA_CANCEL)
#endif
            quit = true;

        if (quit)
            break;
        if (rb->default_event_handler(button) == SYS_USB_CONNECTED) {
            quit = usb = true;
            break;
        }

        if (waiting) {
            if (rem_seconds() <= 0) {
                quit = done = true;
                if (talk_menus_enabled(rb->global_settings))
                    rb->talk_id(LANG_ALARMCLOCK_WAKEUP, false);
                resume_audio();
            }
        }
        else {
            switch (button) {
                case PLA_UP:
                case PLA_UP_REPEAT:
#ifdef HAVE_SCROLLWHEEL
                case PLA_SCROLL_FWD:
                case PLA_SCROLL_FWD_REPEAT:
#endif
                    alarms[current] = (alarms[current] + 1) % maxval[current];
                    alarm_talk_field();
                    break;
                case PLA_DOWN:
                case PLA_DOWN_REPEAT:
#ifdef HAVE_SCROLLWHEEL
                case PLA_SCROLL_BACK:
                case PLA_SCROLL_BACK_REPEAT:
#endif
                    alarms[current] = (alarms[current] + maxval[current] - 1)
                        % maxval[current];
                    alarm_talk_field();
                    break;

                case PLA_LEFT:
                case PLA_LEFT_REPEAT:
                case PLA_RIGHT:
                case PLA_RIGHT_REPEAT:
                    current = (current + 1) % 2;
                    alarm_talk_field();
                    break;

                case PLA_SELECT:
                case PLA_SELECT_REPEAT: {
                    if (rem_seconds() < 0)
                        tomorrow = true;

                    waiting = true;
                    alarm_talk_time(true);
                    break;
                }

                default:
                    break;
            }
        }
    }

    if (!done && talk_menus_enabled(rb->global_settings))
        rb->talk_shutup();

    return (usb) ? PLUGIN_USB_CONNECTED
                 : (done ? PLUGIN_GOTO_WPS : PLUGIN_OK);
}
