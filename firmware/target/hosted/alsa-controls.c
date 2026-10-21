/* Modified for Rockbox Accessible; change notice dated 2026-10-21. */
/***************************************************************************
 *             __________               __   ___.
 *   Open      \______   \ ____   ____ |  | _\_ |__   _______  ___
 *   Source     |       _//  _ \_/ ___\|  |/ /| __ \ /  _ \  \/  /
 *   Jukebox    |    |   (  <_> )  \___|    < | \_\ (  <_> > <  <
 *   Firmware   |____|_  /\____/ \___  >__|_ \|___  /\____/__/\_ \
 *                     \/            \/     \/    \/            \/
 *
 * Copyright (C) 2016 Amaury Pouly
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
#include "alsa-controls.h"
#include "panic.h"
#include "debug.h"
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#include <stdint.h>

/* alsa control handle, we keep it open at all times */
static snd_ctl_t *alsa_ctl;
/* list of all controls, we allocate and fill it once, so we can easily lookup */
static snd_ctl_elem_list_t *alsa_ctl_list;
static unsigned alsa_ctl_count;
/* for each control, we store some info to avoid constantly using ALSA's horrible lookup functions */
static struct ctl_t
{
    snd_ctl_elem_id_t *id; /* ID associated with the control */
    const char *name; /* name of the control */
    snd_ctl_elem_type_t type; /* control type (boolean, enum, ...) */
    unsigned count; /* dimension of the control */
    unsigned items; /* number of items (for enums) */
    const char **enum_name; /* names of the enum, indexed by ALSA index */
} *alsa_ctl_info;

#if defined(DEBUG)
static const char *alsa_ctl_type_name(snd_ctl_elem_type_t type)
{
    switch(type)
    {
        case SND_CTL_ELEM_TYPE_BOOLEAN: return "BOOLEAN";
        case SND_CTL_ELEM_TYPE_INTEGER: return "INTEGER";
        case SND_CTL_ELEM_TYPE_ENUMERATED: return "ENUMERATED";
        default: return "???";
    }
}
#endif

static void alsa_controls_cache(void)
{
    /* allocate list on heap because it is used it is used in other functions */
    if(snd_ctl_elem_list_malloc(&alsa_ctl_list) < 0)
        panicf("Cannot allocate control list");
    /* ALSA is braindead: first "get" the list -> only retrieve count */
    if(snd_ctl_elem_list(alsa_ctl, alsa_ctl_list) < 0)
        panicf("Cannot get element list\n");
    /* now we can allocate the list since the know the size */
    alsa_ctl_count = snd_ctl_elem_list_get_count(alsa_ctl_list);
    if(alsa_ctl_count > INT_MAX ||
        (alsa_ctl_count && sizeof(struct ctl_t) > SIZE_MAX / alsa_ctl_count))
        panicf("Too many ALSA controls");
    if(snd_ctl_elem_list_alloc_space(alsa_ctl_list, alsa_ctl_count) < 0)
        panicf("Cannot allocate space for element list\n");
    /* ... and get the list again! */
    if(snd_ctl_elem_list(alsa_ctl, alsa_ctl_list) < 0)
        panicf("Cannot get element list\n");
    if(snd_ctl_elem_list_get_count(alsa_ctl_list) != alsa_ctl_count ||
        snd_ctl_elem_list_get_used(alsa_ctl_list) != alsa_ctl_count)
        panicf("ALSA control list changed or incomplete");
    if(alsa_ctl_count == 0)
        return;
    /* now cache the info */
    alsa_ctl_info = calloc(alsa_ctl_count, sizeof(struct ctl_t));
    if(!alsa_ctl_info)
        panicf("Cannot allocate control cache");
    snd_ctl_elem_info_t *info;
    if(snd_ctl_elem_info_malloc(&info) < 0)
        panicf("Cannot allocate control info");
    for(unsigned i = 0; i < alsa_ctl_count; i++)
    {
        /* allocate the ID and retrieve it */
        if(snd_ctl_elem_id_malloc(&alsa_ctl_info[i].id) < 0)
        {
            snd_ctl_elem_info_free(info);
            panicf("Cannot allocate control ID %u", i);
        }
        snd_ctl_elem_list_get_id(alsa_ctl_list, i, alsa_ctl_info[i].id);
        /* NOTE: name is valid as long as the ID lives; since we keep both, no need to copy */
        alsa_ctl_info[i].name = snd_ctl_elem_id_get_name(alsa_ctl_info[i].id);
        /* get info */
        snd_ctl_elem_info_set_id(info, alsa_ctl_info[i].id);
        if(snd_ctl_elem_info(alsa_ctl, info) < 0)
        {
            snd_ctl_elem_info_free(info);
            panicf("Cannot get control '%s' info", alsa_ctl_info[i].name);
        }
        alsa_ctl_info[i].type = snd_ctl_elem_info_get_type(info);
        alsa_ctl_info[i].count = snd_ctl_elem_info_get_count(info);
        if(alsa_ctl_info[i].count > INT_MAX ||
            ((alsa_ctl_info[i].type == SND_CTL_ELEM_TYPE_BOOLEAN ||
              alsa_ctl_info[i].type == SND_CTL_ELEM_TYPE_INTEGER ||
              alsa_ctl_info[i].type == SND_CTL_ELEM_TYPE_ENUMERATED) &&
             alsa_ctl_info[i].count > 128))
        {
            snd_ctl_elem_info_free(info);
            panicf("Control '%s' has too many values", alsa_ctl_info[i].name);
        }
        if(alsa_ctl_info[i].type == SND_CTL_ELEM_TYPE_ENUMERATED)
        {
            alsa_ctl_info[i].items = snd_ctl_elem_info_get_items(info);
            if(alsa_ctl_info[i].items > INT_MAX ||
                (alsa_ctl_info[i].items && sizeof(char *) > SIZE_MAX / alsa_ctl_info[i].items))
            {
                snd_ctl_elem_info_free(info);
                panicf("Control '%s' has too many enum items", alsa_ctl_info[i].name);
            }
            if(alsa_ctl_info[i].items == 0)
                continue;
            alsa_ctl_info[i].enum_name = calloc(alsa_ctl_info[i].items, sizeof(char *));
            if(!alsa_ctl_info[i].enum_name)
            {
                snd_ctl_elem_info_free(info);
                panicf("Cannot allocate control '%s' enum cache", alsa_ctl_info[i].name);
            }
            for(unsigned j = 0; j < alsa_ctl_info[i].items; j++)
            {
                snd_ctl_elem_info_set_item(info, j);
                if(snd_ctl_elem_info(alsa_ctl, info) < 0)
                {
                    snd_ctl_elem_info_free(info);
                    panicf("Cannot get control '%s' info for item %u", alsa_ctl_info[i].name, j);
                }
                /* NOTE: copy string because it becomes invalid after info is freed */
                alsa_ctl_info[i].enum_name[j] = strdup(snd_ctl_elem_info_get_item_name(info));
                if(!alsa_ctl_info[i].enum_name[j])
                {
                    snd_ctl_elem_info_free(info);
                    panicf("Cannot copy control '%s' enum item %u", alsa_ctl_info[i].name, j);
                }
            }
        }
        else
            alsa_ctl_info[i].items = 0;
    }
    snd_ctl_elem_info_free(info);

    DEBUGF("ALSA controls:\n");
    for(unsigned i = 0; i < alsa_ctl_count; i++)
    {
        DEBUGF("- name='%s', type=%s, count=%u\n", alsa_ctl_info[i].name,
            alsa_ctl_type_name(alsa_ctl_info[i].type), alsa_ctl_info[i].count);
        if(alsa_ctl_info[i].type == SND_CTL_ELEM_TYPE_ENUMERATED)
        {
            DEBUGF("  items:");
            for(unsigned j = 0; j < alsa_ctl_info[i].items; j++)
            {
                if(j != 0)
                    DEBUGF(",");
                DEBUGF(" '%s'", alsa_ctl_info[i].enum_name[j]);
            }
            DEBUGF("\n");
        }
    }

}

void alsa_controls_init(const char *name)
{
    int result = snd_ctl_open(&alsa_ctl, name, 0);
    if(result < 0)
        panicf("Cannot open ctl %s\n%d: %s", name, result, snd_strerror(result));
    alsa_controls_cache();
}

void alsa_controls_init_hw(unsigned int card)
{
    snd_config_t *configuration = NULL;
    snd_input_t *input = NULL;
    char definition[64];
    snprintf(definition, sizeof(definition),
             "ctl.rockbox { type hw card %u }", card);
    int result = snd_config_top(&configuration);
    if(result >= 0)
        result = snd_input_buffer_open(&input, definition, -1);
    if(result >= 0)
        result = snd_config_load(configuration, input);
    if(input)
        snd_input_close(input);
    if(result >= 0)
        result = snd_ctl_open_lconf(&alsa_ctl, "rockbox", 0, configuration);
    if(configuration)
        snd_config_delete(configuration);
    if(result < 0)
        panicf("Cannot open ctl hw:%u\n%d: %s", card, result, snd_strerror(result));
    alsa_controls_cache();
}

void alsa_controls_close(void)
{
    if(alsa_ctl_info)
    {
        for(unsigned index = 0; index < alsa_ctl_count; index++)
        {
            if(alsa_ctl_info[index].enum_name)
            {
                for(unsigned item = 0; item < alsa_ctl_info[index].items; item++)
                    free((void *)alsa_ctl_info[index].enum_name[item]);
                free(alsa_ctl_info[index].enum_name);
            }
            if(alsa_ctl_info[index].id)
                snd_ctl_elem_id_free(alsa_ctl_info[index].id);
        }
        free(alsa_ctl_info);
        alsa_ctl_info = NULL;
    }
    alsa_ctl_count = 0;
    if(alsa_ctl_list)
    {
        snd_ctl_elem_list_free_space(alsa_ctl_list);
        snd_ctl_elem_list_free(alsa_ctl_list);
        alsa_ctl_list = NULL;
    }
    if(alsa_ctl)
    {
        snd_ctl_close(alsa_ctl);
        alsa_ctl = NULL;
    }
}

/* find a control element ID by name, return -1 of not found or index into array */
int alsa_controls_find(const char *name)
{
    /* enumerate controls */
    for(unsigned i = 0; i < alsa_ctl_count; i++)
        if(strcmp(alsa_ctl_info[i].name, name) == 0)
            return i;
    /* not found */
    return -1;
}

bool alsa_has_control(const char *name)
{
    return alsa_controls_find(name) >= 0;
}

/* find a control element enum index by name, return -1 if not found */
int alsa_controls_find_enum(const char *name, const char *enum_name)
{
    /* find control */
    int idx = alsa_controls_find(name);
    if(idx < 0)
        panicf("Cannot find control '%s'", name);
    /* list items */
    for(unsigned i = 0; i < alsa_ctl_info[idx].items; i++)
    {
        if(strcmp(alsa_ctl_info[idx].enum_name[i], enum_name) == 0)
            return i;
    }
    return -1;
}

/* set/get a control, potentially supports several values */
void alsa_controls_get_set(bool get, const char *name, snd_ctl_elem_type_t type,
    unsigned nr_values, long *val)
{
    snd_ctl_elem_value_t *value;
    /* allocate things on stack to speedup */
    snd_ctl_elem_value_alloca(&value);
    /* find control */
    int idx = alsa_controls_find(name);
    if(idx < 0)
        panicf("Cannot find control '%s'", name);
    /* check the type of the control */
    if(alsa_ctl_info[idx].type != type)
        panicf("Control '%s' has wrong type (got %d, expected %d", name,
            alsa_ctl_info[idx].type, type);
    if(alsa_ctl_info[idx].count != nr_values)
        panicf("Control '%s' has wrong count (got %u, expected %u)",
            name, alsa_ctl_info[idx].count, nr_values);
    snd_ctl_elem_value_set_id(value, alsa_ctl_info[idx].id);
    /* set value */
    if(get)
    {
        /* read value */
        if(snd_ctl_elem_read(alsa_ctl, value) < 0)
            panicf("Cannot read control '%s'", name);
        for(unsigned i = 0; i < nr_values; i++)
        {
            /* ALSA is braindead: there are "typed" setters but they all take long anyway */
            if(type == SND_CTL_ELEM_TYPE_BOOLEAN)
                val[i] = snd_ctl_elem_value_get_boolean(value, i);
            else if(type == SND_CTL_ELEM_TYPE_INTEGER)
                val[i] = snd_ctl_elem_value_get_integer(value, i);
            else if(type == SND_CTL_ELEM_TYPE_ENUMERATED)
                val[i] = snd_ctl_elem_value_get_enumerated(value, i);
        }
    }
    else
    {
        for(unsigned i = 0; i < nr_values; i++)
        {
            /* ALSA is braindead: there are "typed" setters but they all take long anyway */
            if(type == SND_CTL_ELEM_TYPE_BOOLEAN)
                snd_ctl_elem_value_set_boolean(value, i, val[i]);
            else if(type == SND_CTL_ELEM_TYPE_INTEGER)
                snd_ctl_elem_value_set_integer(value, i, val[i]);
            else if(type == SND_CTL_ELEM_TYPE_ENUMERATED)
                snd_ctl_elem_value_set_enumerated(value, i, val[i]);
        }
        /* write value */
        if(snd_ctl_elem_write(alsa_ctl, value) < 0)
            panicf("Cannot write control '%s'", name);
    }
}

/* set a control, potentially supports several values */
void alsa_controls_set(const char *name, snd_ctl_elem_type_t type,
    unsigned nr_values, long *val)
{
    return alsa_controls_get_set(false, name, type, nr_values, val);
}

/* get a control, potentially supports several values */
void alsa_controls_get(const char *name, snd_ctl_elem_type_t type,
    unsigned nr_values, long *val)
{
    return alsa_controls_get_set(true, name, type, nr_values, val);
}

/* get control information */
void alsa_controls_get_info(const char *name, int *out_count)
{
    /* find control */
    int idx = alsa_controls_find(name);
    if(idx < 0)
        panicf("Cannot find control '%s'", name);
    /* get info */
    *out_count = alsa_ctl_info[idx].count;
}

/* helper function: set a control with a single boolean value */
void alsa_controls_set_bool(const char *name, bool val)
{
    long lval = val;
    alsa_controls_set(name, SND_CTL_ELEM_TYPE_BOOLEAN, 1, &lval);
}

/* helper function: set a control with a single enum value */
void alsa_controls_set_enum(const char *name, const char *enum_name)
{
    long idx = alsa_controls_find_enum(name, enum_name);
    if(idx < 0)
        panicf("Cannot find enum '%s' for control '%s'", enum_name, name);
    alsa_controls_set(name, SND_CTL_ELEM_TYPE_ENUMERATED, 1, &idx);
}

/* helper function: set a control with one or more integers */
void alsa_controls_set_ints(const char *name, int count, long *val)
{
    return alsa_controls_set(name, SND_CTL_ELEM_TYPE_INTEGER, count, val);
}

/* helper function: get a control with a single boolean value */
bool alsa_controls_get_bool(const char *name)
{
    long lval = 0;
    alsa_controls_get(name, SND_CTL_ELEM_TYPE_BOOLEAN, 1, &lval);
    return lval != 0;
}
