/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2007 Michael Sevakis
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
#ifndef VOICE_THREAD_H
#define VOICE_THREAD_H

#include "config.h"
#include <stdbool.h>

#ifdef HAVE_ESPEAK
#include <stddef.h>
#include <stdint.h>
#endif

#ifndef VOICE_PLAY_CALLBACK_DEFINED
#define VOICE_PLAY_CALLBACK_DEFINED
typedef void (*voice_play_callback_t)(const void **start, size_t *size);
#endif

void voice_play_data(const void *start, size_t size,
                     voice_play_callback_t get_more);
#ifdef HAVE_ESPEAK
bool voice_play_pcm(const int16_t *samples, size_t count,
                    unsigned int sample_rate, uint32_t generation);
void voice_pause_pcm(bool paused);
uint32_t voice_pcm_elapsed_ms(void);
struct voice_pcm_progress {
    uint64_t elapsed_us;
    uint64_t end_us;
};
void voice_pcm_get_progress(struct voice_pcm_progress *progress);

#endif
void voice_play_stop(void);

void voice_wait(void);
void voice_stop(void);

bool voice_thread_init(void);
void voice_thread_kill(void);

void voice_set_mixer_level(int percent);

#ifdef HAVE_PRIORITY_SCHEDULING
void voice_thread_set_priority(int priority);
#endif

#endif /* VOICE_THREAD_H */
