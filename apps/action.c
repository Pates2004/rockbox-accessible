/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2006 Jonathan Gordon
 * Copyright (C) 2017 William Wilgus
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
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "config.h"
#include "lang.h"

#if !defined(BOOTLOADER)
#include "language.h"
#include "skin_engine/skin_engine.h"
#endif

#include "appevents.h"
#include "button.h"
#include "action.h"
#include "kernel.h"
#include "core_alloc.h"

#include "splash.h"
#include "settings.h"
#include "misc.h"
#if defined(HIBY_R1) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
#include "hiby_bluetooth_service.h"
#endif

#if defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
#include "accessibility_screen.h"
#include "accessibility_touch_wake.h"
#endif

#ifdef HAVE_TOUCHSCREEN
#include "statusbar-skinned.h"
#include "viewport.h"
#ifdef HAVE_ESPEAK
#include "accessibility.h"
#include "root_menu.h"
#endif
#endif

#ifdef HAVE_BACKLIGHT
#include "backlight.h"
#if CONFIG_CHARGING
#include "power.h"
#endif
#endif /* HAVE_BACKLIGHT */

/*#define LOGF_ENABLE*/
#include "logf.h"

#define REPEAT_WINDOW_TICKS HZ/4
#define ACTION_FILTER_TICKS HZ/2 /* timeout between filtered actions SL/BL */

/* act_cur holds action state during get_action() call */
typedef struct
{
    int                            action;
    int                            button;
    int                            context;
    int                            timeout;
    const struct button_mapping   *items;
    const struct button_mapping* (*get_context_map)(int);
    bool                           is_prebutton;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    bool                           physical_button;
    bool                           fresh_physical_button;
    bool                           user_activity;
#endif
} action_cur_t;

/* act_last holds action state between get_action() calls */
typedef struct
{
    int      action;
    long     tick;
    int      button;
    int      context;
    intptr_t data;

#if defined(HAVE_BACKLIGHT)
    unsigned int backlight_mask;
    long         bl_filter_tick;
#endif

#if !defined(HAS_BUTTON_HOLD)
    long         sl_filter_tick;
    unsigned int softlock_mask;
    int          unlock_combo;
    bool         keys_locked;
    bool         screen_has_lock;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    unsigned int physical_buttons;
    unsigned int unlock_contact;
    bool         unlock_wait_for_press;
    long         inactivity_tick;
    int          inactivity_timeout;
    bool         inactivity_initialized;
    bool         inactivity_armed;
    int          inactivity_unlock_combo;
#endif

#endif

    bool          repeated;
    bool          wait_for_release;

#ifndef DISABLE_ACTION_REMAP
    int     key_remap;
#endif

#ifdef HAVE_TOUCHSCREEN
    int ts_data;
    long ts_start_tick;
    struct touchevent touchevent;
    struct gesture gesture;
#endif
} action_last_t;

/* holds the action state between calls to get_action \ get_action_custom) */
static action_last_t action_last =
{
    .action           = ACTION_NONE,
    .button           = BUTTON_NONE | BUTTON_REL, /* allow the ipod wheel to
                                                     work on startup */
    .context          = CONTEXT_STD,
    .data             = 0,
    .repeated         = false,
    .tick             = 0,
    .wait_for_release = false,

#ifndef DISABLE_ACTION_REMAP
    .key_remap = 0,
#endif

#ifdef HAVE_TOUCHSCREEN
    .ts_data = 0,
    .ts_start_tick = 0,
#endif

#ifdef HAVE_BACKLIGHT
    .backlight_mask = SEL_ACTION_NONE,
    .bl_filter_tick = 0,
#endif

#ifndef HAS_BUTTON_HOLD
    .keys_locked     = false,
    .screen_has_lock = false,
    .sl_filter_tick  = 0,
    .softlock_mask   = SEL_ACTION_NONE,
    .unlock_combo    = BUTTON_NONE,
#endif
}; /* action_last_t action_last */

/******************************************************************************
** INTERNAL ACTION FUNCTIONS **************************************************
*******************************************************************************
*/

/******************************************
* has_flag compares value to a (SINGLE) flag
* returns true if set, false otherwise
*/
static inline bool has_flag(unsigned int value, unsigned int flag)
{
    return ((value & flag) == flag);
}

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD)
static bool accessibility_forced_lock;
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
static bool accessibility_custom_click;
#endif

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
static unsigned int accessibility_physical_button(int button)
{
    unsigned int touch = BUTTON_TOUCHSCREEN | BUTTON_TOPLEFT | BUTTON_TOPMIDDLE |
        BUTTON_TOPRIGHT | BUTTON_MIDLEFT | BUTTON_CENTER | BUTTON_MIDRIGHT |
        BUTTON_BOTTOMLEFT | BUTTON_BOTTOMMIDDLE | BUTTON_BOTTOMRIGHT;
#ifdef BUTTON_TOUCH
    touch |= BUTTON_TOUCH;
#endif
    unsigned int physical = BUTTON_MAIN | BUTTON_REMOTE;
    if ((button & touch) || (button & ~(physical | BUTTON_REL | BUTTON_REPEAT)))
        return 0;
    return button & physical;
}

static void accessibility_clear_lock_queue(void)
{
    button_clear_queue_preserve_events();
}
#endif

#if defined(HAVE_BACKLIGHT) || !defined(HAS_BUTTON_HOLD)

/* HELPER FUNCTIONS selective softlock and backlight */

/****************************************************************
* is_action_filtered, selective softlock and backlight use this
* to lookup which actions are filtered, matches are only true if
* action is found and supplied SEL_ACTION mask has the flag.
* returns false if the action isn't found or isn't enabled,
* true if the action is found and is enabled
*/
static bool is_action_filtered(int action, unsigned int mask, int context)
{
    bool match = false;

    switch (action)
    {
        case ACTION_NONE:
            break;
        /* Actions that are not mapped will not turn on the backlight */
        case ACTION_UNKNOWN:
            match = has_flag(mask, SEL_ACTION_NOUNMAPPED);
            break;
        case ACTION_WPS_PLAY:
        case ACTION_FM_PLAY:
            match = has_flag(mask, SEL_ACTION_PLAY);
            break;
        /* case ACTION_STD_PREVREPEAT:*/ /* seek not exempted outside of WPS */
        /* case ACTION_STD_NEXTREPEAT: */
        case ACTION_WPS_SEEKBACK:
        case ACTION_WPS_SEEKFWD:
        case ACTION_WPS_STOPSEEK:
            match = has_flag(mask, SEL_ACTION_SEEK);
            break;
        /* case ACTION_STD_PREV: */ /* skip/scrollwheel not */
        /* case ACTION_STD_NEXT: */ /* exempted outside of WPS */
        case ACTION_WPS_SKIPNEXT:
        case ACTION_WPS_SKIPPREV:
        case ACTION_FM_NEXT_PRESET:
        case ACTION_FM_PREV_PRESET:
            match = has_flag(mask, SEL_ACTION_SKIP);
            break;
#ifdef HAVE_VOLUME_IN_LIST
        case ACTION_LIST_VOLUP:   /* volume exempted outside of WPS */
        case ACTION_LIST_VOLDOWN: /* ( if the device supports it )*/
#endif
        case ACTION_WPS_VOLUP:
        case ACTION_WPS_VOLDOWN:
            match = has_flag(mask, SEL_ACTION_VOL);
            break;
        case ACTION_SETTINGS_INC:/*FMS*/
        case ACTION_SETTINGS_INCREPEAT:/*FMS*/
        case ACTION_SETTINGS_DEC:/*FMS*/
        case ACTION_SETTINGS_DECREPEAT:/*FMS*/
            match = (context == CONTEXT_FM) && has_flag(mask, SEL_ACTION_VOL);
            break;
        default:
            /* display action code of unfiltered actions */
            logf ("unfiltered actions: context: %d action: %d, last btn: %d, \
                  mask: %d", context, action, action_last.button, mask);
            break;
    }/*switch*/

    return match;
}

/*******************************************************************************
* is_action_discarded:
* Most every action takes two rounds through get_action_worker,
* once for the keypress and once for the key release,
* actions with pre_button codes take even more, some actions however, only
* take once; actions defined with only a button and no release/repeat event,
* these actions should be acted upon immediately except when we have
* selective backlighting/softlock enabled and in this case we only act upon
* them immediately if there is no chance they have another event tied to them
* determined using !is_prebutton or if action is completed
* returns true if event was discarded and false if it was kept
*/
static bool is_action_discarded(action_cur_t *cur, bool filtered, long *tick)
{
    bool ret = true;
    bool completed = (cur->button & (BUTTON_REPEAT | BUTTON_REL)) != 0;

#ifdef HAVE_SCROLLWHEEL
    /* Scrollwheel doesn't generate release events  */
    completed |= (cur->button & (BUTTON_SCROLL_BACK | BUTTON_SCROLL_FWD)) != 0;
#endif

    /*directly after a match a key release event may trigger another*/
    if (filtered && cur->action != ACTION_UNKNOWN)
    {
        *tick = (long)((unsigned long)current_tick + ACTION_FILTER_TICKS);
    }
    /* has button been released/repeat or is this the only action it could be */
    if (completed || !cur->is_prebutton)
    {
        /* if the action is not filtered and this isn't just a
        * key release event then return false
        * keeping action, and reset tick
        */
        if (!filtered &&
            (long)((unsigned long)*tick - (unsigned long)current_tick) < 0)
        {
            *tick = 0;
             ret  = false;
        }
    }

    return ret;
}

/*******************************************************
* action_handle_backlight is used to both delay
* and activate the backlight if HAVE_BACKLIGHT
* and SEL_ACTION_ENABLED; backlight state is
* set true/false and ignore_next sets the backlight
* driver to ignore backlight_on commands from
* other modules for a finite duration;
* Ignore is set each time the action system
* handles the backlight as a precaution since, if
* the action system was not triggered the device would
* appear unresponsive to the user.
* If a backlight_on event hasn't been handled in the
* ignore duration it will timeout and the next call
* to backlight_on will trigger as normal
*/
static void action_handle_backlight(bool backlight, bool ignore_next)
{
#if !defined(HAVE_BACKLIGHT)
    (void) backlight;
    (void) ignore_next;
    return;
#else /* HAVE_BACKLIGHT */
    if (backlight)
    {
        backlight_on_ignore(false, 0);
        backlight_on();
    }

    backlight_on_ignore(ignore_next, 5*HZ);/*must be set everytime we handle bl*/

#ifdef HAVE_BUTTON_LIGHT
    if (backlight)
    {
        buttonlight_on_ignore(false, 0);
        buttonlight_on();
    }

    buttonlight_on_ignore(ignore_next, 5*HZ);/* as a precautionary fallback */
#endif /* HAVE_BUTTON_LIGHT */

#endif/* HAVE_BACKLIGHT */
}

#endif /*defined(HAVE_BACKLIGHT) || !defined(HAS_BUTTON_HOLD) HELPER FUNCTIONS*/

/******************************************************************
* action_poll_button filters button presses for get_action_worker;
* if button_get_w_tmo returns...
* BUTTON_NONE, SYS_EVENTS, MULTIMEDIA BUTTONS, ACTION_REDRAW
* they are allowed to pass immediately through to handler.
* if waiting for button release ACTION_NONE is returned until
* button is released/repeated.
*/
static inline bool action_poll_button(action_last_t *last, action_cur_t *cur)
{
    bool ret = true;
    int *button = &cur->button;

    *button = button_get_w_tmo(cur->timeout);

   /* ********************************************************
    * Can return button immediately, sys_event & multimedia
    * button presses don't use the action system, Data from
    * sys events can be pulled with button_get_data.
    * BUTTON_REDRAW should result in a screen refresh
    */
    if (*button == BUTTON_NONE || (*button & (SYS_EVENT|BUTTON_MULTIMEDIA)) != 0)
    {
        return true;
    }
    else if (*button == BUTTON_REDRAW)
    {   /* screen refresh */
        *button = ACTION_REDRAW;
        return true;
    }
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    unsigned int physical = accessibility_physical_button(*button);
    if (physical)
        accessibility_touch_wake_cancel();
    cur->physical_button = physical != 0;
    cur->fresh_physical_button = physical &&
        !(*button & (BUTTON_REL | BUTTON_REPEAT)) &&
        (physical & ~last->physical_buttons);
    cur->user_activity = physical && (cur->fresh_physical_button ||
        (physical & last->physical_buttons));
    if (*button & BUTTON_REL)
        last->physical_buttons &= ~physical;
    else if (physical && !(*button & BUTTON_REPEAT))
        last->physical_buttons = physical;
    if (last->unlock_wait_for_press)
    {
        if (!last->unlock_contact && cur->fresh_physical_button)
            last->unlock_wait_for_press = false;
        else if (*button & BUTTON_REL)
            last->unlock_contact &= ~physical;
        else if (last->unlock_contact)
            last->unlock_contact |= physical;
    }
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    if (accessibility_curtain_escape(*button))
    {
        accessibility_reset();
        last->wait_for_release = false;
        last->button = *button;
        last->action = ACTION_NONE;
        *button = ACTION_NONE;
        return true;
    }
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    if (last->unlock_wait_for_press && (last->unlock_contact || physical))
    {
        last->button = BUTTON_NONE | BUTTON_REL;
        last->action = ACTION_NONE;
        *button = ACTION_NONE;
        return true;
    }
    if (last->keys_locked && cur->fresh_physical_button &&
        accessibility_screen_unlock_any_button())
    {
        last->wait_for_release = false;
        last->context = cur->context;
        return false;
    }
#endif
   /* *************************************************
    * If waiting for release, Don't send any buttons
    * through until we see the release event
    */
    if (last->wait_for_release)
    {
        if (has_flag(*button, BUTTON_REL))
        { /* remember the button for button eating on context change */
            last->wait_for_release = false;
            last->button = *button;
        }

        *button = ACTION_NONE;
    }
#ifdef HAVE_SCROLLWHEEL
   /* *********************************************
    * Scrollwheel doesn't generate release events
    * further processing needed
    */
    else if ((last->button & (BUTTON_SCROLL_BACK | BUTTON_SCROLL_FWD)) != 0)
    {
        ret = false;
    }
#endif
   /* *************************************************************
    * On Context Changed eat all buttons until the previous button
    * was |BUTTON_REL (also eat the |BUTTON_REL button)
    */
    else if ((cur->context != last->context) && ((last->button & BUTTON_REL) == 0))
    {
        if (has_flag(*button, BUTTON_REL))
        {
            last->button = *button;
            last->action = ACTION_NONE;
        }

        *button = ACTION_NONE; /* "safest" return value */
    }
   /* ****************************
    * regular button press,
    * further processing needed
    */
    else
    {
        ret = false;
    }

    /* current context might contain ALLOW_SOFTLOCK save prior to stripping it */
    if (!ret)
    {
        last->context = cur->context;
    }
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    else
        cur->user_activity = false;
#endif

    return ret;
}

/*********************************************
* update_screen_has_lock sets screen_has_lock
* if passed context contains ALLOW_SOFTLOCK
* and removes ALLOW_SOFTLOCK from the passed
* context flag
*/
static inline void update_screen_has_lock(action_last_t *last, action_cur_t *cur)
{
#if defined(HAS_BUTTON_HOLD)
    (void) last;
    (void) cur;
    return;
#else
    last->screen_has_lock = has_flag(cur->context, ALLOW_SOFTLOCK);
    cur->context &= ~ALLOW_SOFTLOCK;
#endif
}

/***********************************************
* handles touch event processing
*/
static inline bool get_action_touchscreen(action_last_t *last, action_cur_t *cur)
{
#if !defined(HAVE_TOUCHSCREEN)
    (void) last;
    (void) cur;
    return false;
#else
    if (has_flag(cur->button, BUTTON_TOUCHSCREEN))
    {
        intptr_t data = button_get_data();
        long now = current_tick;
        last->repeated = false;

        if (has_flag(last->button, BUTTON_TOUCHSCREEN) &&
            !has_flag(last->button, BUTTON_REL))
        {
            /* Only update the coordinates if this is not a release event.
             * For release events, we reuse the previous event coordinates. */
            if (!has_flag(cur->button, BUTTON_REL))
                last->ts_data = data;

            if (has_flag(cur->button, BUTTON_REPEAT))
                last->repeated = true;
        }
        else
        {
            /* Ignore isolated release events. No good can come of this. */
            if (has_flag(cur->button, BUTTON_REL))
                return false;

            last->ts_data = data;
            last->ts_start_tick = now;
        }

        last->button = cur->button;
        cur->action = ACTION_TOUCHSCREEN;

        /* Update touchevent data */
        if (has_flag(last->button, BUTTON_REL))
            last->touchevent.type = TOUCHEVENT_RELEASE;
        else if (has_flag(last->button, BUTTON_REPEAT))
            last->touchevent.type = TOUCHEVENT_CONTACT;
        else
            last->touchevent.type = TOUCHEVENT_PRESS;

        last->touchevent.x = (last->ts_data >> 16) & 0xffff;
        last->touchevent.y = last->ts_data & 0xffff;
        last->touchevent.tick = now;

        /* Update gesture state */
#ifdef HAVE_ESPEAK
        if (accessibility_enabled())
            gesture_reset(&last->gesture);
        else
#endif
            gesture_process(&last->gesture, &last->touchevent);

        return true;
    }
    else
    {
        last->touchevent.type = TOUCHEVENT_NONE;
    }

    return false;
#endif
}

/******************************************************************************
* button_flip_horizontally, passed button is horizontally inverted to support
* RTL language if the given language and context combination require it
* Affected contexts: CONTEXT_STD, CONTEXT_TREE, CONTEXT_LIST, CONTEXT_MAINMENU
* Affected buttons with rtl language:
* BUTTON_LEFT, BUTTON_RIGHT,
* Affected buttons with rtl language and !simulator:
* BUTTON_SCROLL_BACK, BUTTON_SCROLL_FWD, BUTTON_MINUS, BUTTON_PLUS
*/
static inline void button_flip_horizontally(int context, int *button)
{

#if defined(BOOTLOADER)
    (void) context;
    (void) *button;
    return;
#else
    int newbutton = *button;
    if (!(lang_is_rtl() && ((context == CONTEXT_STD) ||
        (context == CONTEXT_TREE) || (context == CONTEXT_LIST) ||
        (context == CONTEXT_MAINMENU))))
    {
        return;
    }

#if defined(BUTTON_LEFT) && defined(BUTTON_RIGHT)
    newbutton &= ~(BUTTON_LEFT | BUTTON_RIGHT);
    if (has_flag(*button, BUTTON_LEFT))
    {
        newbutton |= BUTTON_RIGHT;
    }

    if (has_flag(*button, BUTTON_RIGHT))
    {
        newbutton |= BUTTON_LEFT;
    }
#elif !defined(NO_BUTTON_LR)
#warning "BUTTON_LEFT / BUTTON_RIGHT not defined!"
#endif

#ifndef SIMULATOR
#ifdef HAVE_SCROLLWHEEL
    newbutton &= ~(BUTTON_SCROLL_BACK | BUTTON_SCROLL_FWD);
    if (has_flag(*button, BUTTON_SCROLL_BACK))
    {
        newbutton |= BUTTON_SCROLL_FWD;
    }

    if (has_flag(*button, BUTTON_SCROLL_FWD))
    {
        newbutton |= BUTTON_SCROLL_BACK;
    }
#endif

#if defined(BUTTON_MINUS) && defined(BUTTON_PLUS)
    newbutton &= ~(BUTTON_MINUS | BUTTON_PLUS);
    if (has_flag(*button, BUTTON_MINUS))
    {
        newbutton |= BUTTON_PLUS;
    }

    if (has_flag(*button, BUTTON_PLUS))
    {
        newbutton |= BUTTON_MINUS;
    }
#endif
#endif /* !SIMULATOR */

    *button = newbutton;
#endif /* !BOOTLOADER */
} /* button_flip_horizontally */

/**********************************************************************
* action_code_worker is the worker function for action_code_lookup.
* returns ACTION_UNKNOWN or the requested return value from the list.
* BE AWARE IF YOUR DESIRED ACTION IS IN A LOWER 'CHAINED' CONTEXT::
* *** is_prebutton can miss pre_buttons
* ** An action without pre_button_code (pre_button_code = BUTTON_NONE)
* *  will be returned from the higher context
*/
static inline int action_code_worker(action_last_t *last,
                                     action_cur_t  *cur,
                                              int  *end  )
{
    int ret = ACTION_UNKNOWN;
    int i = *end;
    unsigned int found = 0;
    while (cur->items[i].button_code != BUTTON_NONE)
    {
        if (cur->items[i].button_code == cur->button)
        {
            /********************************************************
            * { Action Code,   Button code,    Prereq button code }
            * CAVEAT: This will allways return the action without
            * pre_button_code (pre_button_code = BUTTON_NONE)
            * if it is found before 'falling through'
            * to a lower 'chained' context.
            *
            * Example: button = UP|REL, last_button = UP;
            *  while looking in CONTEXT_WPS there is an action defined
            *  {ACTION_FOO, BUTTON_UP|BUTTON_REL, BUTTON_NONE}
            *  then ACTION_FOO in CONTEXT_WPS will be returned
            *  EVEN THOUGH you are expecting a fully matched
            *  ACTION_BAR from CONTEXT_STD
            *  {ACTION_BAR, BUTTON_UP|BUTTON_REL, BUTTON_UP}
            */
            if (cur->items[i].pre_button_code == last->button)
            {   /* Always allow an exact match */
                found++;
                *end = i;
            }
            else if (!found && cur->items[i].pre_button_code == BUTTON_NONE)
            {   /* Only allow Loose match if exact match wasn't found */
                found++;
                *end = i;
            }
        }
        else if (has_flag(cur->items[i].pre_button_code, cur->button))
        { /* This could be another action depending on next button press */
            cur->is_prebutton = true;
            if (found > 1) /* There is already an exact match */
            {
                break;
            }
        }
        i++;
    }

    if (!found)
    {
        *end = i;
    }
    else
    {
        ret = cur->items[*end].action_code;
    }

    return ret;
}

/***************************************************************************
* get_next_context returns the next CONTEXT to be searched for action_code
* by action_code_lookup(); if needed it first continues incrementing till
* the end of current context map is reached; If there is another
* 'chained' context below the current context this new context is returned
* if there is not a 'chained' context to return, CONTEXT_STD is returned;
*/
static inline int get_next_context(const struct button_mapping *items, int i)
{
    while (items[i].button_code != BUTTON_NONE)
    {
        i++;
    }

    return (items[i].action_code == ACTION_NONE ) ?
            CONTEXT_STD : items[i].action_code;
}

/************************************************************************
* action_code_lookup passes current button, last button and is_prebutton
* to action_code_worker() which uses the current button map to
* lookup action_code.
* BE AWARE IF YOUR DESIRED ACTION IS IN A LOWER 'CHAINED' CONTEXT::
* *** is_prebutton can miss pre_buttons
* ** An action without pre_button_code (pre_button_code = BUTTON_NONE)
* *  will be returned from the higher context see action_code_worker()
*  for a more in-depth explanation
* places action into current_action
*/

static inline void action_code_lookup(action_last_t *last, action_cur_t *cur)
{
    int  action, i;
    int  context = cur->context;
    cur->is_prebutton = false;

#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    /* This only applies to the first context, to allow locked contexts to
     * specify a fall through to their non-locked version */
    if (is_keys_locked()
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD)
        && !(cur->physical_button && accessibility_screen_locked_buttons())
#endif
        )
        context |= CONTEXT_LOCKED;
#endif

#ifndef DISABLE_ACTION_REMAP
        /* attempt to look up the button in user supplied remap */
        if(last->key_remap && (context & CONTEXT_PLUGIN) == 0)
        {
            if ((cur->button & BUTTON_REMOTE) != 0)
            {
                context |= CONTEXT_REMOTE;
            }
            cur->items = core_get_data(last->key_remap);
            i = 0;
            action = ACTION_UNKNOWN;
            /* check the lut at the beginning for the desired context */
            while (cur->items[i].button_code != BUTTON_NONE)
            {
                if (cur->items[i].action_code == CORE_CONTEXT_REMAP(context))
                {
                    i = cur->items[i].button_code;
                    action = action_code_worker(last, cur, &i);
                    if (action != ACTION_UNKNOWN)
                    {
                        cur->action = action;
                        return;
                    }
                }
                i++;
            }
        }
#endif

    i = 0;
    action  = ACTION_NONE;
    /* attempt to look up the button in the in-built keymaps */
    for(;;)
    {
        /* logf("context = %x",context); */
#if (BUTTON_REMOTE != 0)
        if ((cur->button & BUTTON_REMOTE) != 0)
        {
            context |= CONTEXT_REMOTE;
        }
#endif

        if ((context & CONTEXT_PLUGIN) && cur->get_context_map)
        {
            cur->items = cur->get_context_map(context);
        }
        else
        {
            cur->items = get_context_mapping(context);
        }

        if (cur->items != NULL)
        {
            action = action_code_worker(last, cur, &i);

            if (action == ACTION_UNKNOWN)
            {
                context = get_next_context(cur->items, i);

                if (context != (int)CONTEXT_STOPSEARCHING)
                {
                    i = 0;
                    continue;
                }
            }
        }
        /* No more items, action was found, or STOPSEARCHING was specified */
        break;
    }
    cur->action = action;
}

#ifndef HAS_BUTTON_HOLD
/*************************************
* do_key_lock (dis)/enables softlock
* based on lock flag, last button and
* buttons still in queue are purged
* if HAVE_TOUCHSCREEN then depending
* on user selection it will be locked
* or unlocked as well
*/
void action_update_touch_lock(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    if (!has_flag(action_last.softlock_mask, SEL_ACTION_ENABLED) ||
        has_flag(action_last.softlock_mask, SEL_ACTION_NOTOUCH))
        button_enable_touch(!action_last.keys_locked || accessibility_touch_wake_enabled());
#endif
}

static inline void do_key_lock(bool lock)
{
#if defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    bool changed = action_last.keys_locked != lock;
#endif
    action_last.keys_locked = lock;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    touchscreen_set_wake_locked(lock);
    if (!lock)
        action_last.inactivity_tick = current_tick;
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    if (lock)
        root_menu_cancel_navigation();
    else
        accessibility_forced_lock = false;
#endif
    action_last.button = BUTTON_NONE;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    accessibility_clear_lock_queue();
#else
    button_clear_queue();
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    action_update_touch_lock();
#elif defined(HAVE_TOUCHPAD) || defined(HAVE_TOUCHSCREEN)
 /* disable touch device on keylock if std behavior or selected disable touch */
    if (!has_flag(action_last.softlock_mask, SEL_ACTION_ENABLED) ||
         has_flag(action_last.softlock_mask, SEL_ACTION_NOTOUCH))
    {
        button_enable_touch(!lock);
    }
#endif
#if defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    if (changed)
        accessibility_screen_lock_changed(lock);
#endif
}

static int autosoftlock_timeout(action_last_t *last)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    int seconds = accessibility_screen_autolock_timeout();
    if (!last->inactivity_initialized || last->inactivity_timeout != seconds)
    {
        last->inactivity_initialized = true;
        last->inactivity_timeout = seconds;
        last->inactivity_tick = current_tick;
        last->inactivity_armed = false;
    }
    if (seconds >= 0)
    {
        if (!seconds || last->keys_locked)
        {
            last->inactivity_armed = false;
            return TIMEOUT_BLOCK;
        }
        if (!accessibility_physical_button(last->unlock_combo))
        {
            if (!accessibility_physical_button(last->inactivity_unlock_combo))
            {
                last->inactivity_armed = false;
                return TIMEOUT_BLOCK;
            }
            last->unlock_combo = last->inactivity_unlock_combo;
        }
        if (!last->inactivity_armed)
        {
            last->inactivity_armed = true;
            last->inactivity_tick = current_tick;
        }
        unsigned long elapsed = (unsigned long)current_tick - (unsigned long)last->inactivity_tick;
        int timeout = seconds * HZ;
        return elapsed >= (unsigned long)timeout ? 0 : timeout - (int)elapsed;
    }
#endif
#if defined(HAVE_BACKLIGHT)
    if (!last->keys_locked && last->unlock_combo != BUTTON_NONE &&
        has_flag(last->softlock_mask, SEL_ACTION_AUTOLOCK | SEL_ACTION_ALOCK_OK))
    {
        int timeout = backlight_get_current_timeout();
        if (timeout > 0)
        {
            unsigned long elapsed = (unsigned long)current_tick -
                                    (unsigned long)last->tick;
            return elapsed >= (unsigned long)timeout ? 0 : timeout - (int)elapsed;
        }
    }
#else
    (void)last;
#endif
    return TIMEOUT_BLOCK;
}

/**********************************************
* do_auto_softlock when user selects autolock
* unlock_combo stored for later unlock
* activates autolock on backlight timeout
* toggles autolock on / off by
* ACTION_STD_KEYLOCK presses;
*/
static inline int do_auto_softlock(action_last_t *last, action_cur_t *cur)
{

#if !defined(HAVE_BACKLIGHT) && !(defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER))
    (void) last;
    return cur->action;
#else
    int  action     = cur->action;
    if (autosoftlock_timeout(last) == 0)
    {
        do_key_lock(true);
        if (action == ACTION_STD_KEYLOCK)
            action = ACTION_REDRAW;

#if defined(HAVE_TOUCHPAD) || defined(HAVE_TOUCHSCREEN)
        /* if the touchpad is supposed to be off and the current buttonpress
         * is from the touchpad, nullify both button and action. */
        if (!has_flag(action_last.softlock_mask, SEL_ACTION_ENABLED) ||
            has_flag(action_last.softlock_mask, SEL_ACTION_NOTOUCH))
        {
#if defined(HAVE_TOUCHPAD)
            cur->button = touchpad_filter(cur->button);
#endif
#if defined(HAVE_TOUCHSCREEN)
            const int touch_fakebuttons =
                BUTTON_TOPLEFT    | BUTTON_TOPMIDDLE    | BUTTON_TOPRIGHT    |
                BUTTON_MIDLEFT    | BUTTON_CENTER       | BUTTON_MIDRIGHT    |
                BUTTON_BOTTOMLEFT | BUTTON_BOTTOMMIDDLE | BUTTON_BOTTOMRIGHT;
            if (has_flag(cur->button, BUTTON_TOUCHSCREEN))
                cur->button = BUTTON_NONE;
            else
                cur->button &= ~touch_fakebuttons;
#endif
            if (cur->button == BUTTON_NONE)
            {
                action = ACTION_NONE;
            }
        }
#endif
    }
#ifdef HAVE_BACKLIGHT
    else if (action == ACTION_STD_KEYLOCK && has_flag(last->softlock_mask, SEL_ACTION_AUTOLOCK)
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
             && accessibility_screen_autolock_timeout() < 0
#endif
             )
    {
        if (!has_flag(last->softlock_mask, SEL_ACTION_ALWAYSAUTOLOCK)) // normal operation, clear/arm autolock
        {
            last->unlock_combo = cur->button;/* set unlock combo to allow unlock */
            last->softlock_mask ^= SEL_ACTION_ALOCK_OK;
            action_handle_backlight(true, false);
                /* If we don't wait for a moment for the backlight queue
                 *  to process, the user will never see the message */
            if (!is_backlight_on(false))
            {
                sleep(HZ/2);
            }

            if (has_flag(last->softlock_mask, SEL_ACTION_ALOCK_OK))
            {
                splash(HZ/2, ID2P(LANG_ACTION_AUTOLOCK_ON));
                action = ACTION_REDRAW;
            }
            else
            {
                splash(HZ/2, ID2P(LANG_ACTION_AUTOLOCK_OFF));
            }
        } else if (!has_flag(last->softlock_mask, SEL_ACTION_ALOCK_OK)) // always autolock, but not currently armed
        {
            last->unlock_combo = cur->button;/* set unlock combo to allow unlock */
            last->softlock_mask ^= SEL_ACTION_ALOCK_OK;
        }
    }

#endif
    return action;
#endif /* HAVE_BACKLIGHT */
}

#endif /* HAS_BUTTON_HOLD */

/*****************************************************
* do_softlock Handles softlock once action is known
* selective softlock allows user selected actions to
* bypass a currently locked state, special lock state
* autolock is handled here as well if HAVE_BACKLIGHT
*/
static inline void do_softlock(action_last_t *last, action_cur_t *cur)
{
#if defined(HAS_BUTTON_HOLD)
    (void) last;
    (void) cur;
    return;
#else
    int  action = cur->action;

    /* check to make sure we don't get stuck without a way to unlock - if locked,
     * we can still use unlock_combo to unlock */
    if (!last->screen_has_lock && !last->keys_locked)
    {
        /* no need to check softlock return immediately */
        return;
    }

    bool filtered = true;
    bool notify_user = false;
    bool sl_activate = true; /* standard softlock behavior */
    bool locked_before_action = last->keys_locked;

    if (!last->keys_locked)
    {
        action = do_auto_softlock(last, cur);
    }

    /* Lock/Unlock toggled by ACTION_STD_KEYLOCK presses*/
    if ((action == ACTION_STD_KEYLOCK)
         || (locked_before_action && last->unlock_combo != BUTTON_NONE &&
             last->unlock_combo == cur->button))
    {
#ifdef HAVE_BACKLIGHT
	// if backlight is off and keys are unlocked, do nothing and exit.
	// The backlight should come on without locking keypad.
	if ((!last->keys_locked) && (!is_backlight_on(false)))
	{
	    return;
	}
#endif
        last->unlock_combo = cur->button;
        do_key_lock(!last->keys_locked);
        notify_user = true;
    }
#if (BUTTON_REMOTE != 0)/* Allow remote actions through */
    else if (has_flag(cur->button, BUTTON_REMOTE))
    {
        return;
    }
#endif

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    else if (last->keys_locked && cur->physical_button &&
             accessibility_screen_locked_buttons())
    {
        cur->action = action;
        return;
    }
#endif
    else if (last->keys_locked && action != ACTION_REDRAW)
    {
        if (has_flag(last->softlock_mask, SEL_ACTION_ENABLED))
        {
            filtered = is_action_filtered(action, last->softlock_mask, cur->context);

            sl_activate = !is_action_discarded(cur, filtered, &last->sl_filter_tick);
        }

        if (sl_activate)
        { /*All non-std softlock options are set to 0 if advanced sl is disabled*/
            if (!has_flag(last->softlock_mask, SEL_ACTION_NONOTIFY))
            {   /* always true on standard softlock behavior*/
                notify_user = has_flag(cur->button, BUTTON_REL);
                action = ACTION_REDRAW;
            }
            else
                action = ACTION_NONE;
        }
        else if (!filtered)
        { /* catch blocked actions on fast repeated presses */
            action = ACTION_NONE;
        }
     }/* keys_locked */

#ifdef BUTTON_POWER /*always notify if power button pressed while keys locked*/
    notify_user |= (has_flag(cur->button, BUTTON_POWER|BUTTON_REL)
                    && last->keys_locked);
#endif

    if (notify_user)
    {
#ifndef BOOTLOADER
        skin_request_update_locked(last->keys_locked);
#endif
        action_handle_backlight(true, false);

        if (!has_flag(last->softlock_mask, SEL_ACTION_ALLNONOTIFY))
        {
#ifdef HAVE_BACKLIGHT
           /* If we don't wait for a moment for the backlight queue to process,
            * the user will never see the message
            */
            if (!is_backlight_on(false))
                sleep(HZ/2);
#endif
            int message = last->keys_locked ? LANG_KEYLOCK_ON : LANG_KEYLOCK_OFF;
#if defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
            splashf_silent(HZ/2, ID2P(message));
#else
            splash(HZ/2, ID2P(message));
#endif
        }

        action       = ACTION_REDRAW;
        last->button = BUTTON_NONE;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
        accessibility_clear_lock_queue();
#else
        button_clear_queue();
#endif
    }

    cur->action = action;
#endif/*!HAS_BUTTON_HOLD*/
}

/**********************************************************************
* update_action_last copies the current action values into action_last
* saving the current state & allowing get_action_worker() to return
* while waiting for the next button press; Since some actions take
* multiple buttons, this allows those actions to be looked up and
* returned in a non-blocking way;
* Returns action, checks\sets repeated, plays keyclick (if applicable)
*/
static inline int update_action_last(action_last_t *last, action_cur_t *cur)
{
    int  action = cur->action;

    logf ("action system: context: %d last context: %d, action: %d, \
           last action: %d, button %d, last btn: %d, last repeated: %d, \
           last_data: %d", cur->context, last->context, cur->action,
           last->action, cur->button, last->button, last->repeated, last->data);

    if (action == last->action)
    {
        last->repeated = ((unsigned long)current_tick - (unsigned long)last->tick <
                          REPEAT_WINDOW_TICKS);
    }
    else
    {
        last->repeated = false;
    }

    last->action = action;
    last->button = cur->button;
    last->data   = button_get_data();
    last->tick   = current_tick;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    if (cur->user_activity && !last->keys_locked && action != ACTION_UNKNOWN)
        last->inactivity_tick = current_tick;
#endif

    /* Produce keyclick */
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    if (!accessibility_custom_click)
#endif
        keyclick_click(false, action);

    return action;
}

/********************************************************
* init_act_cur initializes passed struct action_cur_t
* with context, timeout,and get_context_map.
* other values set to default
* if get_context_map is NULL standard
* context mapping will be used
*/
static void init_act_cur(action_cur_t *cur,
                         int  context, int  timeout,
                         const struct button_mapping* (*get_context_map)(int))
{
    cur->action              = ACTION_UNKNOWN;
    cur->button              = BUTTON_NONE;
    cur->context             = context;
    cur->is_prebutton        = false;
    cur->items               = NULL;
    cur->timeout             = timeout;
    cur->get_context_map = get_context_map;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    cur->physical_button = false;
    cur->fresh_physical_button = false;
    cur->user_activity = false;
#endif
}

#if defined(HIBY_R1) && defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
int accessibility_default_button_action(int button, int context, bool held_release)
{
    action_last_t previous = action_last;
    action_cur_t current;
    init_act_cur(&current, context & ~ALLOW_SOFTLOCK, 0, NULL);
    current.button = button;
#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    current.physical_button = accessibility_physical_button(button) != 0;
#endif
    previous.button = button & ~(BUTTON_REL | BUTTON_REPEAT);
    if (held_release)
        previous.button |= BUTTON_REPEAT;
#ifndef DISABLE_ACTION_REMAP
    previous.key_remap = 0;
#endif
    action_code_lookup(&previous, &current);
    return current.action;
}
#endif

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
static int accessibility_finish_button(action_last_t *last, action_cur_t *cur)
{
    if (cur->action == ACTION_UNKNOWN)
    {
#ifndef HAS_BUTTON_HOLD
        if (last->screen_has_lock && autosoftlock_timeout(last) == 0)
        {
            cur->action = ACTION_NONE;
            do_softlock(last, cur);
        }
#endif
        if (cur->button != BUTTON_NONE)
        {
            last->button = cur->button;
            last->tick = current_tick;
#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
            if (cur->user_activity && !last->keys_locked)
                last->inactivity_tick = current_tick;
#endif
        }
        return ACTION_NONE;
    }
#ifndef HAS_BUTTON_HOLD
    if (cur->action == ACTION_STD_KEYLOCK)
    {
        last->screen_has_lock = true;
        accessibility_forced_lock = true;
    }
#endif
    int raw = cur->button;
    if (cur->button == BUTTON_NONE)
        cur->button = last->button & ~(BUTTON_REL | BUTTON_REPEAT);
#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    cur->physical_button = accessibility_physical_button(cur->button) != 0;
#endif
    bool feedback = cur->action != ACTION_WPS_STOPSEEK;
    do_softlock(last, cur);
    accessibility_custom_click = true;
    int result = update_action_last(last, cur);
    accessibility_custom_click = false;
    last->button = raw == BUTTON_NONE ? (cur->button | BUTTON_REL) : raw;
    if (feedback)
        keyclick_click_physical(result, accessibility_button_is_repeat());
    return result;
}
#endif

/*******************************************************
* do_backlight allows exemptions to the backlight on
* user selected actions; Actions need to be looked up
* before the decision to turn on backlight is made,
* if selective backlighting is enabled then
* filter first keypress events may need
* to be taken into account as well
* IF SEL_ACTION_ENABLED then:
* Returns action or is FFKeypress is enabled,
* ACTION_NONE on first keypress
* delays backlight_on until action is known
* handles backlight_on if needed
*/
static inline int do_backlight(action_last_t *last, action_cur_t *cur, int action)
{

#if !defined(HAVE_BACKLIGHT)
    (void) last;
    (void) cur;
    return action;
#else
    if (!has_flag(last->backlight_mask, SEL_ACTION_ENABLED)
        || (action & (SYS_EVENT|BUTTON_MULTIMEDIA)) != 0
        || action == ACTION_REDRAW)
    {
        return action;
    }

    bool filtered;
    bool bl_activate = false;
    bool bl_is_off = !is_backlight_on(false);

#if CONFIG_CHARGING /* disable if on external power */
    bl_is_off &= !(has_flag(last->backlight_mask, SEL_ACTION_NOEXT)
                     && power_input_present());
#endif
    /* skip if backlight on | incorrect context | SEL_ACTION_NOEXT + ext pwr */
    if (bl_is_off && (cur->context == CONTEXT_FM || cur->context == CONTEXT_WPS ||
       cur->context == CONTEXT_MAINMENU))
    {
        filtered = is_action_filtered(action, last->backlight_mask, cur->context);
        bl_activate = !is_action_discarded(cur, filtered, &last->bl_filter_tick);
    }
    else /* standard backlight behaviour */
    {
        bl_activate = true;
    }

    if (action != ACTION_NONE && bl_activate)
    {
        action_handle_backlight(true, true);
        /* Handle first keypress enables backlight only */
        if (has_flag(last->backlight_mask, SEL_ACTION_FFKEYPRESS) && bl_is_off)
        {
            action       = ACTION_NONE;
            last->button = BUTTON_NONE;
        }
    }
    else
    {
        action_handle_backlight(false, true);/* set ignore next true */
    }

    return action;
#endif /* !HAVE_BACKLIGHT */
}

/********************************************************************
* get_action_worker() searches the button list of the passed context
* for the just pressed button. If there is a match it returns the
* value from the list. If there is no match, the last item in the
* list "points" to the next context in a chain so the "chain" is
* followed until the button is found. ACTION_NONE int the button
* list will get CONTEXT_STD which is always the last list checked.
*
* BE AWARE IF YOUR DESIRED ACTION IS IN A LOWER 'CHAINED' CONTEXT::
* *** is_prebutton can miss pre_buttons
* ** An action without pre_button_code (pre_button_code = BUTTON_NONE)
* *  will be returned from the higher context see action_code_worker()
*  for a more in-depth explanation
*
*   Timeout can be: TIMEOUT_NOBLOCK to return immediatly
*                   TIMEOUT_BLOCK   to wait for a button press
*                   Any number >0   to wait that many ticks for a press
*/
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
static bool accessibility_handle_touch_wake(action_last_t *last, action_cur_t *cur)
{
    if (!accessibility_touch_wake_enabled())
        return false;
    const int touch_buttons = BUTTON_TOUCHSCREEN |
        BUTTON_TOPLEFT | BUTTON_TOPMIDDLE | BUTTON_TOPRIGHT |
        BUTTON_MIDLEFT | BUTTON_CENTER | BUTTON_MIDRIGHT |
        BUTTON_BOTTOMLEFT | BUTTON_BOTTOMMIDDLE | BUTTON_BOTTOMRIGHT;
    if (cur->button != BUTTON_NONE && !(cur->button & touch_buttons))
    {
        if (cur->button != SYS_BATTERY_UPDATE && cur->button != SYS_CHARGER_CONNECTED &&
            cur->button != SYS_CHARGER_DISCONNECTED)
            accessibility_touch_wake_cancel();
        return false;
    }
    bool dark = false;
#ifdef HAVE_BACKLIGHT
    dark = !is_backlight_on(false) && !backlight_screen_curtain_active();
#endif
    struct touchevent event;
    const struct touchevent *contact = NULL;
    if (cur->button != BUTTON_NONE)
    {
        intptr_t data = button_get_data();
        event = (struct touchevent){
            .type = cur->button & BUTTON_REL ? TOUCHEVENT_RELEASE :
                    cur->button & BUTTON_REPEAT ? TOUCHEVENT_CONTACT : TOUCHEVENT_PRESS,
            .x = (data >> 16) & 0xffff,
            .y = data & 0xffff,
            .tick = current_tick
        };
        contact = &event;
    }
    enum accessibility_touch_wake_result result = accessibility_touch_wake_process(
        contact, last->keys_locked, dark, cur->context);
    if (result == ACCESSIBILITY_TOUCH_WAKE_PASS)
        return false;
    accessibility_reset();
    gesture_reset(&last->gesture);
    last->touchevent.type = TOUCHEVENT_NONE;
    if (result == ACCESSIBILITY_TOUCH_WAKE_UNLOCK && last->keys_locked)
    {
        do_key_lock(false);
        skin_request_update_locked(false);
    }
    cur->action = ACTION_NONE;
    if (result == ACCESSIBILITY_TOUCH_WAKE_LIGHT || result == ACCESSIBILITY_TOUCH_WAKE_UNLOCK)
    {
        action_handle_backlight(true, false);
        if (!last->keys_locked)
            last->inactivity_tick = current_tick;
        cur->action = ACTION_REDRAW;
    }
    last->button = BUTTON_NONE | BUTTON_REL;
    last->action = cur->action;
    last->tick = current_tick;
    last->repeated = false;
    return true;
}
#endif

static int get_action_worker(action_last_t *last, action_cur_t *cur)
{
#if defined(HIBY_R1) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    hiby_bluetooth_service_process_notifications();
    cur->timeout = hiby_bluetooth_service_adjust_timeout(cur->timeout);
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    static int accessibility_context = -1;
    if (accessibility_context != cur->context)
    {
        accessibility_reset();
        accessibility_context = cur->context;
    }
    cur->timeout = accessibility_adjust_timeout(cur->timeout);
#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    cur->timeout = accessibility_touch_wake_timeout(cur->timeout);
#endif
#endif
    send_event(GUI_EVENT_ACTIONUPDATE, NULL);

#ifndef HAS_BUTTON_HOLD
    if (has_flag(cur->context, ALLOW_SOFTLOCK))
    {
        int remaining = autosoftlock_timeout(last);
        if (remaining >= 0 && (cur->timeout < 0 || cur->timeout > remaining))
            cur->timeout = remaining;
    }
#endif

    /*if button = none/special; returns immediately*/
    if (action_poll_button(last, cur))
    {
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
        if (cur->button == BUTTON_NONE && accessibility_handle_touch_wake(last, cur))
            return cur->action;
        if (cur->button != BUTTON_NONE && cur->button != SYS_BATTERY_UPDATE &&
            cur->button != SYS_CHARGER_CONNECTED && cur->button != SYS_CHARGER_DISCONNECTED)
            accessibility_touch_wake_cancel();
#endif
        if (cur->button == BUTTON_NONE)
        {
            update_screen_has_lock(last, cur);
#ifndef HAS_BUTTON_HOLD
            if (last->screen_has_lock && autosoftlock_timeout(last) == 0)
            {
                cur->action = ACTION_NONE;
                do_softlock(last, cur);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
                accessibility_reset();
#endif
                return cur->action;
            }
#endif
        }
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
        if (cur->button == BUTTON_NONE)
        {
            if (last->wait_for_release)
            {
                accessibility_reset();
                return ACTION_NONE;
            }
#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
            if (last->unlock_wait_for_press)
                return ACTION_NONE;
#endif
            bool locked = false;
#ifndef HAS_BUTTON_HOLD
            locked = last->keys_locked;
            if (accessibility_forced_lock)
                last->screen_has_lock = true;
#endif
            if (accessibility_handle_button(BUTTON_NONE, cur->context,
                    locked
#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
                    && !accessibility_screen_locked_buttons()
#endif
                    , &cur->action))
                return accessibility_finish_button(last, cur);
        }
        if (cur->button == BUTTON_NONE && accessibility_enabled())
        {
            bool locked = false;
#ifndef HAS_BUTTON_HOLD
            locked = last->keys_locked;
#endif
            if (!locked)
            {
                cur->action = accessibility_handle_touch(NULL,
                    cur->context & ~ALLOW_SOFTLOCK);
                if (cur->action == ACTION_STD_KEYLOCK)
                {
                    cur->button = BUTTON_TOUCHSCREEN;
#ifndef HAS_BUTTON_HOLD
                    last->screen_has_lock = true;
                    accessibility_forced_lock = true;
#endif
                    do_softlock(last, cur);
                }
                return cur->action;
            }
            accessibility_cancel_touch();
        }
        if (cur->button != BUTTON_NONE && cur->button != ACTION_REDRAW &&
            cur->button != SYS_BATTERY_UPDATE &&
            cur->button != SYS_CHARGER_CONNECTED &&
            cur->button != SYS_CHARGER_DISCONNECTED)
            accessibility_reset();
#endif
        return cur->button;
    }

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
    if (accessibility_handle_touch_wake(last, cur))
        return cur->action;
#endif
    update_screen_has_lock(last, cur);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD)
    if (accessibility_forced_lock)
        last->screen_has_lock = true;
#ifndef BOOTLOADER
    if (last->keys_locked && cur->fresh_physical_button &&
        accessibility_screen_unlock_any_button())
    {
        last->unlock_contact = accessibility_physical_button(cur->button);
        last->unlock_wait_for_press = true;
        accessibility_reset();
        do_key_lock(false);
        last->button = BUTTON_NONE | BUTTON_REL;
        last->action = ACTION_NONE;
        last->tick = current_tick;
        last->repeated = false;
        skin_request_update_locked(false);
        action_handle_backlight(true, false);
        return ACTION_REDRAW;
    }
    if (last->keys_locked && !cur->physical_button &&
        accessibility_screen_locked_buttons())
    {
        accessibility_cancel_touch();
        return ACTION_NONE;
    }
#endif
    if (last->keys_locked && has_flag(cur->button, BUTTON_TOUCHSCREEN) && accessibility_enabled())
    {
        accessibility_reset();
        last->button = cur->button;
        return ACTION_NONE;
    }
#endif

    if (get_action_touchscreen(last, cur))
    {
        do_softlock(last, cur);
        last->tick = current_tick;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
        if (!last->keys_locked)
            last->inactivity_tick = current_tick;
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
        if (accessibility_enabled())
        {
            bool locked = false;
#ifndef HAS_BUTTON_HOLD
            locked = last->keys_locked;
#endif
            if (cur->action == ACTION_TOUCHSCREEN && !locked)
            {
                cur->action = accessibility_handle_touch(&last->touchevent,
                                                          cur->context);
                if (cur->action == ACTION_STD_KEYLOCK)
                {
#ifndef HAS_BUTTON_HOLD
                    last->screen_has_lock = true;
                    accessibility_forced_lock = true;
#endif
                    do_softlock(last, cur);
                }
            }
            else
            {
                accessibility_reset();
                cur->action = ACTION_NONE;
            }
        }
#endif
        return cur->action;
    }

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    accessibility_cancel_touch();
    bool locked = false;
#ifndef HAS_BUTTON_HOLD
    locked = last->keys_locked;
#endif
    if (accessibility_handle_button(cur->button, cur->context,
            locked
#if !defined(HAS_BUTTON_HOLD) && !defined(BOOTLOADER)
            && !accessibility_screen_locked_buttons()
#endif
            , &cur->action))
        return accessibility_finish_button(last, cur);
#endif
    button_flip_horizontally(cur->context, &cur->button);

    action_code_lookup(last, cur);

    do_softlock(last, cur);

    return update_action_last(last, cur);
}
/*
*******************************************************************************
* END INTERNAL ACTION FUNCTIONS ***********************************************
*******************************************************************************/

/******************************************************************************
* EXPORTED ACTION FUNCTIONS ***************************************************
*******************************************************************************
*/
#ifdef HAVE_TOUCHSCREEN
int action_get_touch_event(struct touchevent *ev)
{
#ifdef HAVE_ESPEAK
    if (accessibility_enabled())
    {
        if (ev)
            memset(ev, 0, sizeof(*ev));
        return TOUCHEVENT_NONE;
    }
#endif
    if (ev)
        *ev = action_last.touchevent;

    return action_last.touchevent.type;
}

void action_gesture_reset(void)
{
    gesture_reset(&action_last.gesture);
}

bool action_gesture_get_event_in_vp(struct gesture_event *gevt,
                                    const struct viewport *vp)
{
    return gesture_get_event_in_vp(&action_last.gesture, gevt, vp);
}

bool action_gesture_is_valid(void)
{
    return gesture_is_valid(&action_last.gesture);
}

bool action_gesture_is_pressed(void)
{
    return gesture_is_pressed(&action_last.gesture);
}

/* return BUTTON_NONE               on error
 *        BUTTON_REPEAT             if repeated press
 *        BUTTON_REPEAT|BUTTON_REL  if release after repeated press
 *        BUTTON_REL                if it's a short press = release after press
 *        BUTTON_TOUCHSCREEN        if press
 * DEPRECATED, do not use it anymore.
 */
int action_get_touchscreen_press(short *x, short *y)
{
    /* historical default value */
    const long long_press_time = 30 * HZ / 100;

    int ret;
    struct touchevent ev;
    switch (action_get_touch_event(&ev))
    {
    case TOUCHEVENT_PRESS:
    case TOUCHEVENT_CONTACT:
        if (TIME_AFTER(ev.tick, action_last.ts_start_tick + long_press_time))
            ret = BUTTON_REPEAT;
        else
            ret = BUTTON_TOUCHSCREEN;
        break;

    case TOUCHEVENT_RELEASE:
        if (TIME_AFTER(ev.tick, action_last.ts_start_tick + long_press_time))
            ret = BUTTON_REPEAT|BUTTON_REL;
        else
            ret = BUTTON_REL;
        break;

    default:
        ret = BUTTON_NONE;
        break;
    }

    if (ret != BUTTON_NONE) {
        *x = ev.x;
        *y = ev.y;
    }

    return ret;
}

/* DEPRECATED, do not use it anymore. */
int action_get_touchscreen_press_in_vp(short *x1, short *y1, struct viewport *vp)
{
    short x, y;
    int ret;

    ret = action_get_touchscreen_press(&x, &y);

    if (ret != BUTTON_NONE && viewport_point_within_vp(vp, x, y))
    {
        *x1 = x - vp->x;
        *y1 = y - vp->y;
        return ret;
    }

    if (has_flag(ret, BUTTON_TOUCHSCREEN))
    {
        return ACTION_UNKNOWN;
    }

    return BUTTON_NONE;
}
#endif

bool action_userabort(int timeout)
{
    int  action = get_custom_action(CONTEXT_STD, timeout, NULL);
    bool ret    = (action == ACTION_STD_CANCEL);
    if (!ret)
    {
        default_event_handler(action);
    }

    return ret;
}

void action_wait_for_release(void)
{
    if (!(action_last.button & BUTTON_REL))
        action_last.wait_for_release = true;
    button_clear_pressed();
}

#if defined(HIBY_R1)
static int do_global_volume(int action)
{
    if (action == ACTION_LIST_VOLUP || action == ACTION_LIST_VOLDOWN)
    {
        adjust_volume(action == ACTION_LIST_VOLUP ? 1 : -1);
        return ACTION_NONE;
    }
    return action;
}
#endif

int get_action(int context, int timeout)
{
    action_cur_t current;
    init_act_cur(&current, context, timeout, NULL);

    int action = get_action_worker(&action_last, &current);

#ifdef HAVE_TOUCHSCREEN
    if (action == ACTION_TOUCHSCREEN)
    {
#ifdef HAVE_ESPEAK
        if (!accessibility_enabled())
#endif
            action = sb_touch_to_button(context);
    }
#endif

    action = do_backlight(&action_last, &current, action);

#if defined(HIBY_R1)
    action = do_global_volume(action);
#endif

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    int pending = accessibility_process_pending(action, context);
    if (pending)
        action = pending;
#endif

    return action;
}

int action_set_keymap(struct button_mapping* core_keymap, int count)
{
#ifdef DISABLE_ACTION_REMAP
    (void)core_keymap;
    (void)count;
    return -1;
#else
    if (count <= 0 || core_keymap == NULL)
        return action_set_keymap_handle(0, 0);

    size_t keyremap_buf_size = count * sizeof(struct button_mapping);
    int handle = core_alloc(keyremap_buf_size);
    if (handle < 0)
        return -6;

    memcpy(core_get_data(handle), core_keymap, keyremap_buf_size);
    return action_set_keymap_handle(handle, count);
#endif
}

int action_set_keymap_handle(int handle, int count)
{
#ifdef DISABLE_ACTION_REMAP
    (void)core_keymap;
    (void)count;
    return -1;
#else
    /* free an existing remap */
    action_last.key_remap = core_free(action_last.key_remap);

    /* if clearing the remap, we're done */
    if (count <= 0 || handle <= 0)
        return 0;

    /* validate the keymap */
    struct button_mapping* core_keymap = core_get_data(handle);
    struct button_mapping* entry = &core_keymap[count - 1];
    if (entry->action_code != (int) CONTEXT_STOPSEARCHING ||
        entry->button_code != BUTTON_NONE) /* check for sentinel at end*/
    {
        /* missing sentinel entry */
        return -1;
    }

    /* check the lut at the beginning for invalid offsets */
    for (int i = 0; i < count; ++i)
    {
        entry = &core_keymap[i];
        if (entry->action_code == (int)CONTEXT_STOPSEARCHING)
            break;

        if ((entry->action_code & CONTEXT_REMAPPED) == CONTEXT_REMAPPED)
        {
            int firstbtn = entry->button_code;
            int endpos = firstbtn + entry->pre_button_code;
            if (firstbtn > count || firstbtn < i || endpos > count)
            {
                /* offset out of bounds */
                return -2;
            }

            if (core_keymap[endpos].button_code != BUTTON_NONE)
            {
                /* stop sentinel is not at end of action lut */
                return -3;
            }
        }
        else
        {
            /* something other than a context remap in the lut */
            return -4;
        }

        if (i+1 >= count)
        {
            /* no sentinel in the lut */
            return -5;
        }
    }

    /* success */
    action_last.key_remap = handle;
    return count;
#endif
}

int get_custom_action(int context,int timeout,
                      const struct button_mapping* (*get_context_map)(int))
{
    action_cur_t current;
    init_act_cur(&current, context, timeout, get_context_map);

    int action = get_action_worker(&action_last, &current);

    action = do_backlight(&action_last, &current, action);

#if defined(HIBY_R1)
    action = do_global_volume(action);
#endif

#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    int pending = accessibility_process_pending(action, context);
    if (pending)
        action = pending;
#endif

    return action;
}

intptr_t get_action_data(void)
{
    return action_last.data;
}

int get_action_statuscode(int *button)
{
    int ret = 0;
    if (button)
    {
        *button = action_last.button;
    }

    if (has_flag(action_last.button, BUTTON_REMOTE))
    {
        ret |= ACTION_REMOTE;
    }

    if (action_last.repeated)
    {
        ret |= ACTION_REPEAT;
    }

    return ret;
}

#ifdef HAVE_BACKLIGHT
/* Enable selected actions to leave the backlight off */
void set_selective_backlight_actions(bool selective, unsigned int mask,
                                                              bool filter_fkp)
{
    action_handle_backlight(true, selective);
    if (selective) /* we will handle filter_first_keypress here so turn it off*/
    {
        set_backlight_filter_keypress(false);/* turnoff ffkp in button.c */
        action_last.backlight_mask = mask | SEL_ACTION_ENABLED;
        if (filter_fkp)
        {
            action_last.backlight_mask |= SEL_ACTION_FFKEYPRESS;
        }
    }
    else
    {
        set_backlight_filter_keypress(filter_fkp);
        action_last.backlight_mask = SEL_ACTION_NONE;
    }
}
#endif /* HAVE_BACKLIGHT */

#ifndef HAS_BUTTON_HOLD
bool is_keys_locked(void)
{
    return (action_last.keys_locked);
}

/* Enable selected actions to bypass a locked state */
void set_selective_softlock_actions(bool selective, unsigned int mask)
{
#if defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    bool was_locked = action_last.keys_locked;
#endif
    action_last.keys_locked = false;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    touchscreen_set_wake_locked(false);
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    action_last.inactivity_tick = current_tick;
#endif
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    accessibility_forced_lock = false;
#endif
#if defined(HAVE_TOUCHPAD) || defined(HAVE_TOUCHSCREEN)
    button_enable_touch(true);
#endif
    if (selective)
    {
        action_last.softlock_mask = mask | SEL_ACTION_ENABLED;
    }
    else
    {
        action_last.softlock_mask = SEL_ACTION_NONE;
    }
#if defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    if (was_locked)
        accessibility_screen_lock_changed(false);
#endif
}

/* look for an action in the given context, return button which triggers it.
 * (note: pre_button isn't taken into account here) */
static int find_button_for_action(int context, int action)
{
    const struct button_mapping *items;
    int i;

    do
    {
        items = get_context_mapping(context);
        if (items == NULL)
            break;

        for (i = 0; items[i].button_code != BUTTON_NONE; ++i)
        {
            if (items[i].action_code == action)
                return items[i].button_code;
        }

        /* get chained context, if none it will be CONTEXT_STOPSEARCHING */
        context = items[i].action_code;
    } while (context != (int)CONTEXT_STOPSEARCHING);

    return BUTTON_NONE;
}

void action_autosoftlock_init(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
    action_last.inactivity_unlock_combo = BUTTON_NONE;
#endif
    /* search in WPS and STD contexts for the keylock button combo */
    static const int contexts[2] = { CONTEXT_WPS, CONTEXT_STD };

    for (int i = 0; i < 2; ++i)
    {
        int button = find_button_for_action(contexts[i], ACTION_STD_KEYLOCK);
        if (button != BUTTON_NONE)
        {
            action_last.unlock_combo = button;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(BOOTLOADER)
            if (accessibility_physical_button(button))
                action_last.inactivity_unlock_combo = button;
#endif
            break;
        }
    }

    /* if we have autolock and alwaysautolock, go ahead and arm it */
    if (has_flag(action_last.softlock_mask, SEL_ACTION_AUTOLOCK) &&
        has_flag(action_last.softlock_mask, SEL_ACTION_ALWAYSAUTOLOCK) &&
        (action_last.unlock_combo != BUTTON_NONE))
    {
        action_last.softlock_mask = action_last.softlock_mask | SEL_ACTION_ALOCK_OK;
    }

    return;
}
#endif /* !HAS_BUTTON_HOLD */

/*
*******************************************************************************
* END EXPORTED ACTION FUNCTIONS ***********************************************
*******************************************************************************/
