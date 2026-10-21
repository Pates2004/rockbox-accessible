/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2017 Marcin Bukat
 * Copyright (C) 2020 Solomon Peachy

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
#include <poll.h>
#include <errno.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <linux/input.h>
#include <fcntl.h>
#include <string.h>
#include <stdlib.h>
#ifdef HIBY_R1
#include <sys/ioctl.h>
#endif

#include "kernel.h"
#include "sysfs.h"
#include "button.h"
#include "panic.h"

#ifdef HAVE_SCROLLWHEEL
#include "powermgmt.h"
#if defined(HAVE_BACKLIGHT) || defined(HAVE_BUTTON_LIGHT)
#include "backlight.h"
#endif
#endif /* HAVE_SCROLLWHEEL */

/* TODO:  HAVE_SCROLLWHEEL is a hack.  Instead of posting the exact number
   of clicks, instead do it similar to the ipod clickwheel and post
   the wheel angular velocity (degrees per second)

   * Track the relative position  (ie based on click events)
   * Use WHEELCLICKS_PER_ROTATION to convert clicks to angular distance
   * Compute to angular velocity (degrees per second)

 */
#define NR_POLL_DESC    5

static int num_devices = 0;
static struct pollfd poll_fds[NR_POLL_DESC];
#ifdef HIBY_R1
static void r1_reset_device(int index);
#endif

void button_add_input_device(int i)
{
    if (i < 0 || i >= NR_POLL_DESC)
        return;
#ifdef HIBY_R1
    r1_reset_device(i);
#endif
    int fd = poll_fds[i].fd;
    if (fd >= 0)
        close(fd);

    char path[32];
    snprintf(path, sizeof(path), "/dev/input/event%d", i);
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NONBLOCK);
    poll_fds[i].fd = fd >= 0 ? fd : -1;
    if(fd >= 0)
    {
        poll_fds[i].events = POLLIN;
        poll_fds[i].revents = 0;
        if (num_devices <= i)
            num_devices = i + 1;
    }
}

void button_init_device(void)
{
    for(int i = 0; i < NR_POLL_DESC; i++)
    {
        poll_fds[i].fd = -1;
        button_add_input_device(i);
    }
}

void button_remove_input_device(int i)
{
    if (i < 0 || i >= NR_POLL_DESC)
        return;
#ifdef HIBY_R1
    r1_reset_device(i);
#endif
    int fd = poll_fds[i].fd;
    if (fd < 0)
        return;

    if (i == num_devices - 1)
        num_devices = i;

    close(fd);
    poll_fds[i].fd = -1;
}

void button_close_device(void)
{
    num_devices = 0;
    /* close descriptors */
    for(int i = 0; i < NR_POLL_DESC; i++)
    {
        button_remove_input_device(i);
    }
}

#ifdef BUTTON_DELAY_RELEASE
static int button_delay_release = 0;
static int delay_tick = 0;
#endif

#ifdef HAVE_TOUCHSCREEN
/* Last known touchscreen coordinates. */
static int _last_x = 0;
static int _last_y = 0;

/* Last known touchscreen state. */
static enum
{
    TOUCHSCREEN_STATE_UNKNOWN = 0,
    TOUCHSCREEN_STATE_UP,
    TOUCHSCREEN_STATE_DOWN
} _last_touch_state = TOUCHSCREEN_STATE_UNKNOWN;

/* Do _NOT_ change this.  Unofficial Linux API */
#define EVENT_VALUE_TOUCHSCREEN_RELEASE  -1
/* This is only used as an arbitrary placeholder */
#define EVENT_VALUE_TOUCHSCREEN_PRESS    1

static int ts_enabled = 1;
#ifdef HIBY_R1
struct r1_input_state
{
    int buttons;
    int horizontal;
    int vertical;
    int touch_state;
    bool touch_dirty;
    bool touch_blocked;
    bool touch_device;
    bool multitouch;
    bool dropped;
};

static struct r1_input_state r1_inputs[NR_POLL_DESC];
static int r1_touch_owner = -1;
static unsigned int r1_next_descriptor;

static void r1_cancel_touch(int index)
{
    if (r1_touch_owner == index)
    {
        _last_touch_state = TOUCHSCREEN_STATE_UNKNOWN;
        r1_touch_owner = -1;
    }
    r1_inputs[index].touch_state = TOUCHSCREEN_STATE_UNKNOWN;
    r1_inputs[index].touch_dirty = false;
}

static void r1_reset_device(int index)
{
    r1_cancel_touch(index);
    memset(&r1_inputs[index], 0, sizeof(r1_inputs[index]));
}
#endif

void touchscreen_last_state(int *x, int *y, int *state)
{
    *x = _last_x;
    *y = _last_y;
    *state = _last_touch_state;
}

void touchscreen_enable_device(bool en)
{
    ts_enabled = en;
#ifdef HIBY_R1
    if (!en)
    {
        for (int index = 0; index < NR_POLL_DESC; ++index)
        {
            if (r1_inputs[index].touch_state == TOUCHSCREEN_STATE_DOWN)
                r1_inputs[index].touch_blocked = true;
            r1_cancel_touch(index);
        }
    }
#endif
}

#ifndef HIBY_R1
static void handle_touchscreen_event(__u16 code, __s32 value)
{
    switch(code)
    {
        case ABS_X:
        case ABS_MT_POSITION_X:
        {
            _last_x = value;
            break;
        }

        case ABS_Y:
        case ABS_MT_POSITION_Y:
        {
            _last_y = value;
            break;
        }

        case ABS_MT_TRACKING_ID:
        {
            if(value == EVENT_VALUE_TOUCHSCREEN_RELEASE)
            {
                _last_touch_state = TOUCHSCREEN_STATE_UP;
            }
            else
            {
                _last_touch_state = TOUCHSCREEN_STATE_DOWN;
            }
            break;
        }
    }
}
#endif
#endif

#ifdef HIBY_R1
static int r1_buttons(void)
{
    int buttons = 0;
    for (int index = 0; index < NR_POLL_DESC; ++index)
        buttons |= r1_inputs[index].buttons;
    return buttons;
}

static int r1_sample(int *data)
{
    int touch = touchscreen_to_pixels(_last_x, _last_y, data);
    return r1_buttons() |
        (_last_touch_state == TOUCHSCREEN_STATE_DOWN ? touch : 0);
}

static void r1_stage_touch(int index, unsigned int code, int value)
{
    struct r1_input_state *input = &r1_inputs[index];
    input->touch_device = true;
    if (code == ABS_MT_TRACKING_ID)
    {
        if (value == EVENT_VALUE_TOUCHSCREEN_RELEASE)
        {
            input->touch_blocked = false;
            input->touch_state = TOUCHSCREEN_STATE_UP;
        }
        else if (!ts_enabled || input->touch_blocked)
        {
            input->touch_blocked = true;
            input->touch_state = TOUCHSCREEN_STATE_UNKNOWN;
        }
        else
            input->touch_state = TOUCHSCREEN_STATE_DOWN;
    }
    else if (!ts_enabled || input->touch_blocked)
        return;
    else if (code == ABS_X || code == ABS_MT_POSITION_X)
        input->horizontal = value;
    else if (code == ABS_Y || code == ABS_MT_POSITION_Y)
        input->vertical = value;
    else
        return;
    input->touch_dirty = true;
}

static void r1_commit_touch(int index)
{
    struct r1_input_state *input = &r1_inputs[index];
    if (!input->touch_dirty)
        return;
    input->touch_dirty = false;
    if (!ts_enabled || input->touch_blocked ||
        (r1_touch_owner >= 0 && r1_touch_owner != index &&
         _last_touch_state == TOUCHSCREEN_STATE_DOWN))
        return;
    _last_x = input->horizontal;
    _last_y = input->vertical;
    _last_touch_state = input->touch_state;
    r1_touch_owner = index;
}

static void r1_recover_device(int index)
{
    struct r1_input_state *input = &r1_inputs[index];
    unsigned long keys[(KEY_MAX + 1 + sizeof(unsigned long) * 8 - 1) /
                       (sizeof(unsigned long) * 8)];
    memset(keys, 0, sizeof(keys));
    int result = ioctl(poll_fds[index].fd, EVIOCGKEY(sizeof(keys)), keys);
    input->buttons = 0;
    if (result >= 0)
    {
        for (unsigned int code = 0; code <= KEY_MAX; ++code)
        {
            if (keys[code / (sizeof(*keys) * 8)] &
                (1ul << (code % (sizeof(*keys) * 8))))
                input->buttons |= button_map(code) & ~BUTTON_TOUCH;
        }
    }
    if (input->touch_device)
    {
        r1_cancel_touch(index);
        input->touch_blocked = true;
        if (input->multitouch)
        {
            struct input_absinfo tracking;
            if (ioctl(poll_fds[index].fd, EVIOCGABS(ABS_MT_TRACKING_ID),
                      &tracking) >= 0 && tracking.value < 0)
                input->touch_blocked = false;
        }
        else if (result >= 0)
            input->touch_blocked = !!(keys[BTN_TOUCH / (sizeof(*keys) * 8)] &
                (1ul << (BTN_TOUCH % (sizeof(*keys) * 8))));
    }
    input->dropped = false;
}

static void r1_process_event(int index, const struct input_event *event)
{
    struct r1_input_state *input = &r1_inputs[index];
    if (event->type == EV_SYN && event->code == SYN_DROPPED)
    {
        input->dropped = true;
        input->touch_dirty = false;
        return;
    }
    if (input->dropped)
    {
        if (event->type == EV_SYN && event->code == SYN_REPORT)
            r1_recover_device(index);
        return;
    }
    if (event->type == EV_ABS)
    {
        if (event->code == ABS_MT_TRACKING_ID)
            input->multitouch = true;
        r1_stage_touch(index, event->code, event->value);
    }
    else if (event->type == EV_SYN && event->code == SYN_REPORT)
        r1_commit_touch(index);
    else if (event->type == EV_KEY)
    {
        int mapped = button_map(event->code);
        if (event->code == BTN_TOUCH)
        {
            if (event->value && !(mapped & BUTTON_TOUCH))
                input->touch_blocked = true;
            r1_stage_touch(index, ABS_MT_TRACKING_ID, event->value ?
                EVENT_VALUE_TOUCHSCREEN_PRESS : EVENT_VALUE_TOUCHSCREEN_RELEASE);
            mapped &= ~BUTTON_TOUCH;
        }
        if (event->value)
            input->buttons |= mapped;
        else
            input->buttons &= ~mapped;
    }
}

static int button_read_r1(int *data)
{
    int sampled_buttons = r1_buttons();
    int sampled_x = _last_x;
    int sampled_y = _last_y;
    int sampled_touch_state = _last_touch_state;
    for (unsigned int work = 0; work < 64 && num_devices > 0; ++work)
    {
        if (poll(poll_fds, num_devices, 0) <= 0)
            break;
        for (int offset = 0; offset < num_devices; ++offset)
        {
            int index = (r1_next_descriptor + offset) % num_devices;
            short flags = poll_fds[index].revents;
            if (!flags)
                continue;
            r1_next_descriptor = (index + 1) % num_devices;
            if (flags & POLLNVAL)
                button_remove_input_device(index);
            else if (flags & POLLIN)
            {
                struct input_event event;
                ssize_t size = read(poll_fds[index].fd, &event, sizeof(event));
                if (size == (ssize_t)sizeof(event))
                    r1_process_event(index, &event);
                else if (size >= 0 || (errno != EAGAIN && errno != EINTR))
                    button_remove_input_device(index);
                else if (flags & (POLLERR | POLLHUP))
                    button_remove_input_device(index);
            }
            else if (flags & (POLLERR | POLLHUP))
                button_remove_input_device(index);
            break;
        }
        if (r1_buttons() != sampled_buttons || _last_x != sampled_x ||
            _last_y != sampled_y || (int)_last_touch_state != sampled_touch_state)
            return r1_sample(data);
    }
    return r1_sample(data);
}
#endif

#ifdef HAVE_BUTTON_DATA
#define BDATA int *data
#else
#define BDATA void
#endif
int button_read_device(BDATA)
{
#ifdef HIBY_R1
    return button_read_r1(data);
#else
    static int button_bitmap = 0;
    struct input_event event;

#if defined(HAVE_BUTTON_DATA) && !defined(HAVE_TOUCHSCREEN)
    (void)data;
#endif

#ifdef HAVE_SCROLLWHEEL
    int wheel_ticks = 0;
#endif

#ifdef BUTTON_DELAY_RELEASE
    /* First de-assert delayed-release buttons */
    if (button_delay_release && current_tick >= delay_tick)
    {
        button_bitmap &= ~button_delay_release;
        button_delay_release = 0;
    }
#endif

    /* check if there are any events pending and process them */
    while(poll(poll_fds, num_devices, 0) > 0) {
        for(int i = 0; i < num_devices; i++) {
            /* read only if non-blocking */
            if(poll_fds[i].revents & POLLIN) {
                int size = read(poll_fds[i].fd, &event, sizeof(event));
                if(size == (int)sizeof(event)) {
                    switch(event.type) {
                    case EV_KEY: {
                        /* map linux event code to rockbox button bitmap */
                        int bmap = button_map(event.code);

                        /* event.value == 0x10000 means press
                         * event.value == 0 means release
                         */
                        if(event.value) {
#ifdef HAVE_SCROLLWHEEL
                            /* Filter out wheel ticks */
                            if (bmap & BUTTON_SCROLL_BACK)
                                wheel_ticks--;
                            else if (bmap & BUTTON_SCROLL_FWD)
                                wheel_ticks++;
                            bmap &= ~(BUTTON_SCROLL_BACK|BUTTON_SCROLL_FWD);
#endif
#ifdef BUTTON_DELAY_RELEASE
                            bmap &= ~BUTTON_DELAY_RELEASE;
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(BUTTON_TOUCH)
                            /* Some touchscreens give us actual touch/untouch as a "key" */
                            if (bmap & BUTTON_TOUCH) {
                                handle_touchscreen_event(ABS_MT_TRACKING_ID, EVENT_VALUE_TOUCHSCREEN_PRESS);
                                bmap &= ~BUTTON_TOUCH;
                            }
#endif
                            button_bitmap |= bmap;
                        } else {
#if defined(HAVE_TOUCHSCREEN) && defined(BUTTON_TOUCH)
                            /* Some touchscreens give us actual touch/untouch as a "key" */
                            if (bmap & BUTTON_TOUCH) {
                                handle_touchscreen_event(ABS_MT_TRACKING_ID, EVENT_VALUE_TOUCHSCREEN_RELEASE);
                                bmap &= ~BUTTON_TOUCH;
                            }
#endif
#ifdef BUTTON_DELAY_RELEASE
                            /* Delay the release of any requested buttons */
                            if (bmap & BUTTON_DELAY_RELEASE) {
                                button_delay_release |= bmap & ~BUTTON_DELAY_RELEASE;
                                delay_tick = current_tick + HZ/20;
                                bmap = 0;
                            }
#endif
#ifdef HAVE_SCROLLWHEEL
                            /* Wheel gives us press+release back to back; ignore the release */
                            bmap &= ~(BUTTON_SCROLL_BACK|BUTTON_SCROLL_FWD);
#endif
                            button_bitmap &= ~bmap;
                        }
                        break;
                    }
#ifdef HAVE_TOUCHSCREEN
                    case EV_ABS: {
                        if (ts_enabled) {
                            handle_touchscreen_event(event.code, event.value);
                        } else {
                             /* If disabled... ignore */
                            _last_touch_state = TOUCHSCREEN_STATE_UNKNOWN;
                        }
                        break;
                    }
#endif
                    default:
                        /* Ignore other event types */
                        break;
                    }
                }
            }
            /* device was removed/disconnected — close it to stop poll returning POLLHUP forever */
            else if (poll_fds[i].revents & (POLLERR | POLLHUP)) {
                button_remove_input_device(i);
            }
        }
    }

#ifdef HAVE_SCROLLWHEEL
    /* Reset backlight and poweroff timers */
    if (wheel_ticks) {
#ifdef HAVE_BACKLIGHT
        backlight_on();
#endif
#ifdef HAVE_BUTTON_LIGHT
        buttonlight_on();
#endif
        reset_poweroff_timer();
    }

    if (wheel_ticks > 0)
    {
        while (wheel_ticks-- > 0)
        {
            button_queue_post(BUTTON_SCROLL_FWD, 0);
        }
    }
    else if (wheel_ticks < 0)
    {
        while (wheel_ticks++ < 0)
        {
            button_queue_post(BUTTON_SCROLL_BACK, 0);
        }
    }
#endif /* HAVE_SCROLLWHEEL */

#ifdef HAVE_TOUCHSCREEN
    int touch = touchscreen_to_pixels(_last_x, _last_y, data);

    if(_last_touch_state == TOUCHSCREEN_STATE_DOWN)
    {
        return button_bitmap | touch;
    }
#endif

    return button_bitmap;
#endif
}
