/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2005 Jonas Haggqvist
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
#include "lib/mul_id3.h" /* collect_dir_stats & display_dir_stats */

static const char *stats_get_name(int selected_item, void *data,
                                  char *buffer, size_t buffer_len)
{
    const struct dir_stats *stats = data;
    const char *label;
    unsigned int count;
    switch (selected_item)
    {
        case 0:
            label = rb->str(LANG_PROPERTIES_FILES);
            count = stats->file_count;
            break;
        case 1:
        {
            int32_t unit;
            unsigned long size = human_size(stats->byte_count, &unit);
            rb->snprintf(buffer, buffer_len, "%s: %lu %s",
                         rb->str(LANG_PROPERTIES_SIZE), size, rb->str(unit));
            return buffer;
        }
        case 2:
            label = rb->str(LANG_TRACKS);
            count = stats->audio_file_count;
            break;
        case 3:
            label = rb->str(LANG_PLAYLISTS);
            count = stats->m3u_file_count;
            break;
        case 4:
            label = rb->str(LANG_PLUGIN_STATS_IMAGES);
            count = stats->img_file_count;
            break;
        case 5:
            label = rb->str(LANG_PLUGIN_STATS_VIDEOS);
            count = stats->vid_file_count;
            break;
        case 6:
            label = rb->str(LANG_PROPERTIES_SUBDIRS);
            count = stats->dir_count;
            break;
        case 7:
            label = rb->str(LANG_PLUGIN_STATS_MAX_FILES);
            count = stats->max_files_in_dir;
            break;
        default:
            return NULL;
    }
    rb->snprintf(buffer, buffer_len, "%s: %u", label, count);
    return buffer;
}

static int stats_list_action(int action, struct gui_synclist *lists)
{
    if (action == ACTION_STD_OK)
    {
        rb->gui_synclist_speak_item(lists);
        return ACTION_NONE;
    }
    return action;
}

enum plugin_status plugin_start(const void* parameter)
{    
    (void)parameter;
    int success;
    static struct dir_stats stats;
    stats.dirname[0] = '/';
    stats.count_all = true;
    rb->splash(0, ID2P(LANG_WAIT));
#ifdef HAVE_ADJUSTABLE_CPU_FREQ
    rb->cpu_boost(true);
#endif
    display_dir_stats(&stats);
    success = collect_dir_stats(&stats, NULL);
#ifdef HAVE_ADJUSTABLE_CPU_FREQ
    rb->cpu_boost(false);
#endif
    if (!success)
        return PLUGIN_OK;

    display_dir_stats(&stats);
#ifdef HAVE_BACKLIGHT
#ifdef HAVE_REMOTE_LCD
    rb->remote_backlight_on();
#endif
    rb->backlight_on();
#endif
    rb->splash(HZ, "Done");
    struct simplelist_info list;
    rb->simplelist_info_init(&list, rb->str(LANG_PROPERTIES_DIRECTORY_PROPERTIES),
                             8, &stats);
    list.get_name = stats_get_name;
    list.action_callback = stats_list_action;
    return rb->simplelist_show_list(&list) ? PLUGIN_USB_CONNECTED : PLUGIN_OK;
}
