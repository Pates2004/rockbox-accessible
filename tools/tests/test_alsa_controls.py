"""Exercise actual ALSA controls with real configuration parsing and mocked hardware."""

from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/target/hosted/alsa-controls.c"
HEADER = SOURCE.with_suffix(".h")
WRAPPED = (
    "calloc", "strdup", "free",
    "snd_config_top", "snd_input_buffer_open", "snd_input_close", "snd_config_load",
    "snd_config_delete", "snd_ctl_open", "snd_ctl_open_lconf", "snd_ctl_close",
    "snd_ctl_elem_list_malloc", "snd_ctl_elem_list_alloc_space", "snd_ctl_elem_list",
    "snd_ctl_elem_list_get_count", "snd_ctl_elem_list_get_used", "snd_ctl_elem_list_get_id",
    "snd_ctl_elem_list_free_space", "snd_ctl_elem_list_free",
    "snd_ctl_elem_info_malloc", "snd_ctl_elem_id_malloc", "snd_ctl_elem_id_free", "snd_ctl_elem_info",
    "snd_ctl_elem_info_get_type", "snd_ctl_elem_info_get_count", "snd_ctl_elem_info_get_items",
    "snd_ctl_elem_info_set_item", "snd_ctl_elem_info_get_item_name", "snd_ctl_elem_info_free",
    "snd_ctl_elem_read", "snd_ctl_elem_write",
)

HARNESS = r'''
#include "alsa-controls.h"
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void *__real_calloc(size_t count, size_t size);
char *__real_strdup(const char *string);
void __real_free(void *pointer);
int __real_snd_config_top(snd_config_t **configuration);
int __real_snd_input_buffer_open(snd_input_t **input, const char *buffer, ssize_t size);
int __real_snd_input_close(snd_input_t *input);
int __real_snd_config_load(snd_config_t *configuration, snd_input_t *input);
int __real_snd_config_delete(snd_config_t *configuration);
int __real_snd_ctl_elem_list_malloc(snd_ctl_elem_list_t **list);
int __real_snd_ctl_elem_list_alloc_space(snd_ctl_elem_list_t *list, unsigned int count);
void __real_snd_ctl_elem_list_free_space(snd_ctl_elem_list_t *list);
void __real_snd_ctl_elem_list_free(snd_ctl_elem_list_t *list);
int __real_snd_ctl_elem_info_malloc(snd_ctl_elem_info_t **info);
int __real_snd_ctl_elem_id_malloc(snd_ctl_elem_id_t **identifier);
void __real_snd_ctl_elem_id_free(snd_ctl_elem_id_t *identifier);
void __real_snd_ctl_elem_info_set_item(snd_ctl_elem_info_t *info, unsigned int item);
void __real_snd_ctl_elem_info_free(snd_ctl_elem_info_t *info);

struct control_fixture
{
    unsigned int numid;
    const char *name;
    snd_ctl_elem_type_t type;
    unsigned int count;
    long values[128];
};

static struct control_fixture controls[] = {
    { 11, "Playback Switch", SND_CTL_ELEM_TYPE_BOOLEAN, 1, { 1, 0 } },
    { 47, "Playback Volume", SND_CTL_ELEM_TYPE_INTEGER, 2, { -17, 23 } },
    { 99, "Output Route", SND_CTL_ELEM_TYPE_ENUMERATED, 1, { 1, 0 } },
};
static const char *enum_names[] = { "Headphones", "Line Out", "Bluetooth" };
static const unsigned int control_count = sizeof(controls) / sizeof(controls[0]);
static snd_ctl_t *const fake_handle = (snd_ctl_t *)(uintptr_t)0x1234;
static const char *fault;
static const char *requested_name;
static unsigned int requested_card;
static bool hardware;
static int open_error;
static jmp_buf panic_jump;
static char panic_message[512];
static snd_config_t *private_configuration;
static snd_config_t *vendor_configuration;
static snd_input_t *private_input;
static unsigned int top_calls, input_calls, input_closes, load_calls, config_deletes;
static unsigned int generic_opens, private_opens, closes, list_allocations, list_calls;
static unsigned int info_calls, reads, writes, enum_item;
static unsigned int array_allocations, string_allocations, id_allocations, item_queries;
static snd_ctl_elem_list_t *live_list;
static snd_ctl_elem_info_t *live_info;
static snd_ctl_elem_id_t *live_ids[3];
static void *live_heap[5];
static bool live_list_space;
static char enum_buffer[64];

static bool failing(const char *name)
{
    return strcmp(fault, name) == 0;
}

static void track_heap(void *pointer)
{
    assert(pointer);
    for (unsigned int index = 0; index < 5; ++index)
    {
        if (live_heap[index])
            continue;
        live_heap[index] = pointer;
        return;
    }
    assert(!"Unexpected heap allocation");
}

void *__wrap_calloc(size_t count, size_t size)
{
    ++array_allocations;
    if ((failing("control-size-overflow") || failing("enum-size-overflow")) && count == INT_MAX)
        return NULL;
    assert(array_allocations <= 2 && count == 3 && size > 0);
    if ((failing("cache-alloc") && array_allocations == 1) ||
        (failing("enum-alloc") && array_allocations == 2))
        return NULL;
    void *pointer = __real_calloc(count, size);
    track_heap(pointer);
    return pointer;
}

char *__wrap_strdup(const char *string)
{
    ++string_allocations;
    assert(string && string_allocations <= 3);
    if ((failing("enum-name-first") && string_allocations == 1) ||
        (failing("enum-name-last") && string_allocations == 3))
        return NULL;
    char *pointer = __real_strdup(string);
    track_heap(pointer);
    return pointer;
}

void __wrap_free(void *pointer)
{
    if (!pointer)
        return;
    for (unsigned int index = 0; index < 5; ++index)
    {
        if (live_heap[index] != pointer)
            continue;
        live_heap[index] = NULL;
        __real_free(pointer);
        return;
    }
    assert(!"Freeing an unknown or already freed cache allocation");
}

void panicf(const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(panic_message, sizeof(panic_message), format, arguments);
    va_end(arguments);
    longjmp(panic_jump, 1);
}

int __wrap_snd_config_top(snd_config_t **configuration)
{
    ++top_calls;
    assert(hardware && !private_configuration);
    if (failing("config-top"))
        return -ENOMEM;
    int result = __real_snd_config_top(configuration);
    assert(result == 0);
    private_configuration = *configuration;
    assert(private_configuration != vendor_configuration);
    return result;
}

int __wrap_snd_input_buffer_open(snd_input_t **input, const char *buffer, ssize_t size)
{
    ++input_calls;
    assert(private_configuration && !private_input);
    if (failing("input-open"))
        return -ENOMEM;
    int result = __real_snd_input_buffer_open(input, buffer, size);
    assert(result == 0);
    private_input = *input;
    return result;
}

int __wrap_snd_config_load(snd_config_t *configuration, snd_input_t *input)
{
    ++load_calls;
    assert(configuration == private_configuration && input == private_input);
    if (failing("config-load"))
        return -EINVAL;
    return __real_snd_config_load(configuration, input);
}

int __wrap_snd_input_close(snd_input_t *input)
{
    assert(input && input == private_input && !input_closes);
    ++input_closes;
    private_input = NULL;
    return __real_snd_input_close(input);
}

int __wrap_snd_config_delete(snd_config_t *configuration)
{
    assert(configuration && configuration == private_configuration && !private_input);
    assert(!config_deletes);
    ++config_deletes;
    private_configuration = NULL;
    return __real_snd_config_delete(configuration);
}

static unsigned int child_count(snd_config_t *configuration)
{
    unsigned int count = 0;
    snd_config_iterator_t position, next;
    snd_config_for_each(position, next, configuration)
        ++count;
    return count;
}

int __wrap_snd_ctl_open_lconf(snd_ctl_t **handle, const char *name, int mode,
                            snd_config_t *configuration)
{
    ++private_opens;
    assert(hardware && !generic_opens && !strcmp(name, "rockbox") && mode == 0);
    assert(configuration && configuration == private_configuration);
    assert(configuration != snd_config && !private_input && input_closes == 1);
    assert(child_count(configuration) == 1);
    snd_config_t *node, *control;
    assert(snd_config_search(configuration, "ctl", &node) == 0);
    assert(child_count(node) == 1);
    assert(snd_config_search(configuration, "ctl.rockbox", &control) == 0);
    assert(child_count(control) == 2);
    assert(snd_config_search(control, "type", &node) == 0);
    const char *type;
    assert(snd_config_get_string(node, &type) == 0 && !strcmp(type, "hw"));
    assert(snd_config_search(control, "card", &node) == 0);
    long long card;
    if (snd_config_get_type(node) == SND_CONFIG_TYPE_INTEGER64)
        assert(snd_config_get_integer64(node, &card) == 0);
    else
    {
        long native_card;
        assert(snd_config_get_integer(node, &native_card) == 0);
        card = native_card;
    }
    assert((unsigned long long)card == (unsigned long long)requested_card);
    assert(snd_config_search(control, "hint", &node) < 0);
    assert(snd_config_search(control, "hint.description", &node) < 0);
    if (failing("open"))
        return open_error;
    *handle = fake_handle;
    return 0;
}

int __wrap_snd_ctl_open(snd_ctl_t **handle, const char *name, int mode)
{
    ++generic_opens;
    assert(!hardware && !private_opens && !top_calls && !input_calls && !load_calls);
    assert(name == requested_name && mode == 0);
    if (failing("open"))
        return open_error;
    *handle = fake_handle;
    return 0;
}

int __wrap_snd_ctl_close(snd_ctl_t *handle)
{
    assert(handle == fake_handle && !closes);
    assert(!live_list && !live_info && !live_list_space);
    for (unsigned int index = 0; index < 3; ++index)
        assert(!live_ids[index]);
    for (unsigned int index = 0; index < 5; ++index)
        assert(!live_heap[index]);
    ++closes;
    return 0;
}

int __wrap_snd_ctl_elem_list_malloc(snd_ctl_elem_list_t **list)
{
    ++list_allocations;
    assert(!private_configuration && !private_input);
    assert(hardware ? config_deletes == 1 : config_deletes == 0);
    if (failing("list-malloc"))
        return -ENOMEM;
    assert(!live_list);
    int result = __real_snd_ctl_elem_list_malloc(list);
    assert(result == 0);
    live_list = *list;
    return result;
}

int __wrap_snd_ctl_elem_list_alloc_space(snd_ctl_elem_list_t *list, unsigned int count)
{
    if (failing("control-size-overflow"))
    {
        assert(list == live_list && count == INT_MAX && list_calls == 1);
        live_list_space = true;
        return 0;
    }
    assert(list == live_list && count == (failing("empty-list") ? 0u : control_count));
    assert(list_calls == 1 && !live_list_space);
    if (failing("list-space"))
        return -ENOMEM;
    int result = __real_snd_ctl_elem_list_alloc_space(list, count);
    assert(result == 0);
    live_list_space = true;
    return result;
}

void __wrap_snd_ctl_elem_list_free_space(snd_ctl_elem_list_t *list)
{
    assert(list && list == live_list);
    live_list_space = false;
    __real_snd_ctl_elem_list_free_space(list);
}

void __wrap_snd_ctl_elem_list_free(snd_ctl_elem_list_t *list)
{
    assert(list && list == live_list && !live_list_space);
    live_list = NULL;
    __real_snd_ctl_elem_list_free(list);
}

int __wrap_snd_ctl_elem_list(snd_ctl_t *handle, snd_ctl_elem_list_t *list)
{
    assert(handle == fake_handle && list);
    ++list_calls;
    if ((failing("list-first") && list_calls == 1) ||
        (failing("list-second") && list_calls == 2))
        return -EIO;
    assert(list_calls <= 2);
    return 0;
}

unsigned int __wrap_snd_ctl_elem_list_get_count(const snd_ctl_elem_list_t *list)
{
    assert(list == live_list && (list_calls == 1 || list_calls == 2));
    if (failing("control-count-overflow"))
        return UINT_MAX;
    if (failing("control-size-overflow"))
        return INT_MAX;
    if (failing("empty-list"))
        return 0;
    if (list_calls == 2 && failing("list-grew"))
        return control_count + 1;
    if (list_calls == 2 && failing("list-shrank"))
        return control_count - 1;
    return control_count;
}

unsigned int __wrap_snd_ctl_elem_list_get_used(const snd_ctl_elem_list_t *list)
{
    assert(list == live_list && list_calls == 2);
    if (failing("control-size-overflow"))
        return INT_MAX;
    if (failing("empty-list"))
        return 0;
    if (failing("list-incomplete"))
        return control_count - 1;
    if (failing("list-used-overflow"))
        return UINT_MAX;
    return control_count;
}

int __wrap_snd_ctl_elem_info_malloc(snd_ctl_elem_info_t **info)
{
    assert(!live_info && array_allocations == 1);
    if (failing("info-malloc"))
        return -ENOMEM;
    int result = __real_snd_ctl_elem_info_malloc(info);
    assert(result == 0);
    live_info = *info;
    return result;
}

int __wrap_snd_ctl_elem_id_malloc(snd_ctl_elem_id_t **identifier)
{
    unsigned int index = id_allocations++;
    assert(live_info && index < control_count && !live_ids[index]);
    if ((failing("id-first") && index == 0) || (failing("id-last") && index == 2))
        return -ENOMEM;
    int result = __real_snd_ctl_elem_id_malloc(identifier);
    assert(result == 0);
    live_ids[index] = *identifier;
    return result;
}

void __wrap_snd_ctl_elem_id_free(snd_ctl_elem_id_t *identifier)
{
    assert(identifier);
    for (unsigned int index = 0; index < control_count; ++index)
    {
        if (live_ids[index] != identifier)
            continue;
        live_ids[index] = NULL;
        __real_snd_ctl_elem_id_free(identifier);
        return;
    }
    assert(!"Freeing an unknown or already freed ALSA ID");
}

void __wrap_snd_ctl_elem_list_get_id(const snd_ctl_elem_list_t *list,
                                    unsigned int index, snd_ctl_elem_id_t *identifier)
{
    assert(list == live_list && list_calls == 2 && index < control_count);
    assert(identifier && identifier == live_ids[index]);
    snd_ctl_elem_id_set_numid(identifier, controls[index].numid);
    snd_ctl_elem_id_set_name(identifier, controls[index].name);
    snd_ctl_elem_id_set_interface(identifier, SND_CTL_ELEM_IFACE_MIXER);
    snd_ctl_elem_id_set_device(identifier, 2);
    snd_ctl_elem_id_set_subdevice(identifier, 3);
    snd_ctl_elem_id_set_index(identifier, index + 4);
}

static struct control_fixture *control_by_id(const snd_ctl_elem_id_t *identifier)
{
    for (unsigned int index = 0; index < control_count; ++index)
    {
        if (snd_ctl_elem_id_get_numid(identifier) != controls[index].numid)
            continue;
        assert(!strcmp(snd_ctl_elem_id_get_name(identifier), controls[index].name));
        assert(snd_ctl_elem_id_get_interface(identifier) == SND_CTL_ELEM_IFACE_MIXER);
        assert(snd_ctl_elem_id_get_device(identifier) == 2);
        assert(snd_ctl_elem_id_get_subdevice(identifier) == 3);
        assert(snd_ctl_elem_id_get_index(identifier) == index + 4);
        return &controls[index];
    }
    assert(!"Unknown control ID");
    abort();
}

static struct control_fixture *control_by_info(const snd_ctl_elem_info_t *info)
{
    snd_ctl_elem_id_t *identifier;
    snd_ctl_elem_id_alloca(&identifier);
    snd_ctl_elem_info_get_id(info, identifier);
    return control_by_id(identifier);
}

int __wrap_snd_ctl_elem_info(snd_ctl_t *handle, snd_ctl_elem_info_t *info)
{
    assert(handle == fake_handle && info == live_info);
    ++info_calls;
    if (failing("info"))
        return -EIO;
    struct control_fixture *control = control_by_info(info);
    if (control->type == SND_CTL_ELEM_TYPE_ENUMERATED)
    {
        assert(enum_item < 3);
        if (item_queries && failing("enum-info"))
            return -EIO;
        snprintf(enum_buffer, sizeof(enum_buffer), "%s", enum_names[enum_item]);
    }
    return 0;
}

snd_ctl_elem_type_t __wrap_snd_ctl_elem_info_get_type(const snd_ctl_elem_info_t *info)
{
    return control_by_info(info)->type;
}

unsigned int __wrap_snd_ctl_elem_info_get_count(const snd_ctl_elem_info_t *info)
{
    if (failing("value-count-overflow"))
        return UINT_MAX;
    if (failing("boolean-capacity") && control_by_info(info)->type == SND_CTL_ELEM_TYPE_BOOLEAN)
        return 129;
    if (failing("integer-capacity") && control_by_info(info)->type == SND_CTL_ELEM_TYPE_INTEGER)
        return 129;
    if (failing("enum-capacity") && control_by_info(info)->type == SND_CTL_ELEM_TYPE_ENUMERATED)
        return 129;
    return control_by_info(info)->count;
}

unsigned int __wrap_snd_ctl_elem_info_get_items(const snd_ctl_elem_info_t *info)
{
    assert(control_by_info(info)->type == SND_CTL_ELEM_TYPE_ENUMERATED);
    if (failing("enum-count-overflow"))
        return UINT_MAX;
    if (failing("enum-size-overflow"))
        return INT_MAX;
    if (failing("empty-enum"))
        return 0;
    return 3;
}

void __wrap_snd_ctl_elem_info_set_item(snd_ctl_elem_info_t *info, unsigned int item)
{
    assert(control_by_info(info)->type == SND_CTL_ELEM_TYPE_ENUMERATED && item < 3);
    enum_item = item;
    ++item_queries;
    __real_snd_ctl_elem_info_set_item(info, item);
}

const char *__wrap_snd_ctl_elem_info_get_item_name(const snd_ctl_elem_info_t *info)
{
    assert(control_by_info(info)->type == SND_CTL_ELEM_TYPE_ENUMERATED);
    return enum_buffer;
}

void __wrap_snd_ctl_elem_info_free(snd_ctl_elem_info_t *info)
{
    assert(info && info == live_info);
    live_info = NULL;
    memset(enum_buffer, 'X', sizeof(enum_buffer) - 1);
    __real_snd_ctl_elem_info_free(info);
}

static struct control_fixture *control_by_value(snd_ctl_elem_value_t *value)
{
    snd_ctl_elem_id_t *identifier;
    snd_ctl_elem_id_alloca(&identifier);
    snd_ctl_elem_value_get_id(value, identifier);
    return control_by_id(identifier);
}

int __wrap_snd_ctl_elem_read(snd_ctl_t *handle, snd_ctl_elem_value_t *value)
{
    assert(handle == fake_handle);
    ++reads;
    if (failing("read"))
        return -EIO;
    struct control_fixture *control = control_by_value(value);
    for (unsigned int index = 0; index < control->count; ++index)
    {
        if (control->type == SND_CTL_ELEM_TYPE_BOOLEAN)
            snd_ctl_elem_value_set_boolean(value, index, control->values[index]);
        else if (control->type == SND_CTL_ELEM_TYPE_INTEGER)
            snd_ctl_elem_value_set_integer(value, index, control->values[index]);
        else
            snd_ctl_elem_value_set_enumerated(value, index, control->values[index]);
    }
    return 0;
}

int __wrap_snd_ctl_elem_write(snd_ctl_t *handle, snd_ctl_elem_value_t *value)
{
    assert(handle == fake_handle);
    ++writes;
    if (failing("write"))
        return -EIO;
    struct control_fixture *control = control_by_value(value);
    for (unsigned int index = 0; index < control->count; ++index)
    {
        if (control->type == SND_CTL_ELEM_TYPE_BOOLEAN)
            control->values[index] = snd_ctl_elem_value_get_boolean(value, index);
        else if (control->type == SND_CTL_ELEM_TYPE_INTEGER)
            control->values[index] = snd_ctl_elem_value_get_integer(value, index);
        else
            control->values[index] = snd_ctl_elem_value_get_enumerated(value, index);
    }
    return 1;
}

static void create_vendor_config(void)
{
    const char definition[] =
        "ctl.rockbox { type hw card 99 hint.description vendor-only }";
    snd_input_t *input;
    assert(snd_config == NULL);
    assert(__real_snd_config_top(&vendor_configuration) == 0);
    assert(__real_snd_input_buffer_open(&input, definition, -1) == 0);
    assert(__real_snd_config_load(vendor_configuration, input) == 0);
    assert(__real_snd_input_close(input) == 0);
    snd_config = vendor_configuration;
}

static void check_vendor_config(void)
{
    assert(snd_config == vendor_configuration);
    assert(child_count(vendor_configuration) == 1);
    snd_config_t *node;
    long card;
    const char *description;
    assert(snd_config_search(vendor_configuration, "ctl.rockbox.card", &node) == 0);
    assert(snd_config_get_integer(node, &card) == 0 && card == 99);
    assert(snd_config_search(vendor_configuration, "ctl.rockbox.hint.description", &node) == 0);
    assert(snd_config_get_string(node, &description) == 0 && !strcmp(description, "vendor-only"));
    snd_config = NULL;
    assert(__real_snd_config_delete(vendor_configuration) == 0);
}

static void exercise_controls(void)
{
    unsigned int expected_info_calls = failing("empty-enum") ? 3u : 6u;
    assert(list_calls == 2 && info_calls == expected_info_calls && !live_info);
    for (unsigned int index = 0; index < control_count; ++index)
    {
        int count = 0;
        assert(alsa_controls_find(controls[index].name) == (int)index);
        assert(alsa_has_control(controls[index].name));
        alsa_controls_get_info(controls[index].name, &count);
        assert(count == (int)controls[index].count);
    }
    assert(alsa_controls_find("Missing") == -1 && !alsa_has_control("Missing"));
    assert(alsa_controls_find_enum("Output Route", "Missing") == -1);
    for (unsigned int index = 0; index < 3; ++index)
        assert(alsa_controls_find_enum("Output Route", enum_names[index]) ==
               (failing("empty-enum") ? -1 : (int)index));
    assert(alsa_controls_get_bool("Playback Switch"));
    alsa_controls_set_bool("Playback Switch", false);
    assert(controls[0].values[0] == 0 && !alsa_controls_get_bool("Playback Switch"));
    alsa_controls_set_bool("Playback Switch", true);
    assert(controls[0].values[0] == 1 && alsa_controls_get_bool("Playback Switch"));
    long values[2] = { 0, 0 };
    alsa_controls_get("Playback Volume", SND_CTL_ELEM_TYPE_INTEGER, 2, values);
    assert(values[0] == -17 && values[1] == 23);
    values[0] = -41;
    values[1] = 37;
    alsa_controls_set_ints("Playback Volume", 2, values);
    assert(controls[1].values[0] == -41 && controls[1].values[1] == 37);
    values[0] = values[1] = 0;
    alsa_controls_get("Playback Volume", SND_CTL_ELEM_TYPE_INTEGER, 2, values);
    assert(values[0] == -41 && values[1] == 37);
    if (failing("empty-enum"))
    {
        assert(string_allocations == 0 && array_allocations == 1);
        return;
    }
    alsa_controls_get("Output Route", SND_CTL_ELEM_TYPE_ENUMERATED, 1, values);
    assert(values[0] == 1);
    alsa_controls_set_enum("Output Route", "Bluetooth");
    assert(controls[2].values[0] == 2);
    alsa_controls_get("Output Route", SND_CTL_ELEM_TYPE_ENUMERATED, 1, values);
    assert(values[0] == 2 && list_calls == 2 && info_calls == 6);
    assert(reads == 7 && writes == 4);
}

static void check_resources(void)
{
    assert(!private_configuration && !private_input);
    assert(!live_list && !live_info && !live_list_space);
    for (unsigned int index = 0; index < 3; ++index)
        assert(!live_ids[index]);
    for (unsigned int index = 0; index < 5; ++index)
        assert(!live_heap[index]);
    if (!hardware)
    {
        assert(generic_opens == 1 && !private_opens);
        assert(!top_calls && !input_calls && !input_closes && !load_calls && !config_deletes);
        return;
    }
    assert(!generic_opens && top_calls == 1);
    assert(input_calls == (failing("config-top") ? 0u : 1u));
    assert(config_deletes == (failing("config-top") ? 0u : 1u));
    bool has_input = !failing("config-top") && !failing("input-open");
    assert(load_calls == (has_input ? 1u : 0u));
    assert(input_closes == (has_input ? 1u : 0u));
    assert(private_opens == (has_input && !failing("config-load") ? 1u : 0u));
}

static void exercise_capacity(void)
{
    long values[128];
    for (unsigned int index = 0; index < control_count; ++index)
    {
        int count = 0;
        alsa_controls_get_info(controls[index].name, &count);
        assert(count == 128);
        alsa_controls_get(controls[index].name, controls[index].type, 128, values);
        for (unsigned int item = 0; item < 128; ++item)
        {
            assert(values[item] == controls[index].values[item]);
            if (controls[index].type == SND_CTL_ELEM_TYPE_BOOLEAN)
                values[item] = item % 2;
            else if (controls[index].type == SND_CTL_ELEM_TYPE_ENUMERATED)
                values[item] = item % 3;
            else
                values[item] = (long)item - 64;
        }
        alsa_controls_set(controls[index].name, controls[index].type, 128, values);
        for (unsigned int item = 0; item < 128; ++item)
            assert(controls[index].values[item] == values[item]);
    }
    assert(reads == 3 && writes == 3);
}

static void reset_cycle(void)
{
    top_calls = input_calls = input_closes = load_calls = config_deletes = 0;
    generic_opens = private_opens = closes = list_allocations = list_calls = 0;
    info_calls = reads = writes = enum_item = 0;
    array_allocations = string_allocations = id_allocations = item_queries = 0;
    controls[0].values[0] = 1;
    controls[1].values[0] = -17;
    controls[1].values[1] = 23;
    controls[2].values[0] = 1;
    controls[0].count = controls[2].count = 1;
    controls[1].count = 2;
    if (failing("maximum-dimensions"))
    {
        for (unsigned int index = 0; index < control_count; ++index)
            controls[index].count = 128;
    }
}

static void run_cycle(void)
{
    reset_cycle();
    if (setjmp(panic_jump) == 0)
    {
        if (hardware)
            alsa_controls_init_hw(requested_card);
        else
            alsa_controls_init(requested_name);
        if (failing("read"))
            alsa_controls_get_bool("Playback Switch");
        if (failing("write"))
            alsa_controls_set_bool("Playback Switch", false);
        assert(failing("none") || failing("reopen") || failing("empty-list") ||
               failing("empty-enum") || failing("maximum-dimensions"));
        if (failing("empty-list"))
            assert(!info_calls && !array_allocations && !id_allocations);
        else if (failing("maximum-dimensions"))
            exercise_capacity();
        else
            exercise_controls();
    }
    else
    {
        char expected[512];
        int result = 0;
        if (failing("open"))
            result = open_error;
        else if (failing("config-top") || failing("input-open"))
            result = -ENOMEM;
        else if (failing("config-load"))
            result = -EINVAL;
        if (result)
        {
            if (hardware)
                snprintf(expected, sizeof(expected), "Cannot open ctl hw:%u\n%d: %s",
                         requested_card, result, snd_strerror(result));
            else
                snprintf(expected, sizeof(expected), "Cannot open ctl %s\n%d: %s",
                         requested_name, result, snd_strerror(result));
            assert(!list_allocations && !list_calls && !info_calls && !reads && !writes);
        }
        else if (failing("list-malloc"))
        {
            strcpy(expected, "Cannot allocate control list");
            assert(list_allocations == 1 && !list_calls && !info_calls);
        }
        else if (failing("list-space"))
            strcpy(expected, "Cannot allocate space for element list\n");
        else if (failing("list-first") || failing("list-second"))
            strcpy(expected, "Cannot get element list\n");
        else if (failing("control-count-overflow"))
        {
            strcpy(expected, "Too many ALSA controls");
            assert(list_calls == 1 && !live_list_space && !array_allocations && !id_allocations);
        }
        else if (failing("control-size-overflow"))
        {
            strcpy(expected, SIZE_MAX / (size_t)INT_MAX < sizeof(void *) ?
                   "Too many ALSA controls" : "Cannot allocate control cache");
        }
        else if (failing("list-grew") || failing("list-shrank") ||
                 failing("list-incomplete") || failing("list-used-overflow"))
        {
            strcpy(expected, "ALSA control list changed or incomplete");
            assert(list_calls == 2 && !array_allocations && !id_allocations);
        }
        else if (failing("cache-alloc"))
        {
            strcpy(expected, "Cannot allocate control cache");
            assert(array_allocations == 1 && !info_calls && !id_allocations);
        }
        else if (failing("info-malloc"))
        {
            strcpy(expected, "Cannot allocate control info");
            assert(!info_calls && !id_allocations);
        }
        else if (failing("id-first") || failing("id-last"))
        {
            unsigned int index = failing("id-first") ? 0u : 2u;
            snprintf(expected, sizeof(expected), "Cannot allocate control ID %u", index);
            assert(id_allocations == index + 1 && info_calls == index);
        }
        else if (failing("info"))
            strcpy(expected, "Cannot get control 'Playback Switch' info");
        else if (failing("value-count-overflow") || failing("boolean-capacity"))
            strcpy(expected, "Control 'Playback Switch' has too many values");
        else if (failing("integer-capacity"))
            strcpy(expected, "Control 'Playback Volume' has too many values");
        else if (failing("enum-capacity"))
            strcpy(expected, "Control 'Output Route' has too many values");
        else if (failing("enum-count-overflow"))
        {
            strcpy(expected, "Control 'Output Route' has too many enum items");
            assert(array_allocations == 1 && !string_allocations && !item_queries);
        }
        else if (failing("enum-size-overflow"))
            strcpy(expected, SIZE_MAX / (size_t)INT_MAX < sizeof(char *) ?
                   "Control 'Output Route' has too many enum items" :
                   "Cannot allocate control 'Output Route' enum cache");
        else if (failing("enum-alloc"))
        {
            strcpy(expected, "Cannot allocate control 'Output Route' enum cache");
            assert(array_allocations == 2 && !string_allocations && !item_queries);
        }
        else if (failing("enum-info"))
            strcpy(expected, "Cannot get control 'Output Route' info for item 0");
        else if (failing("enum-name-first") || failing("enum-name-last"))
        {
            unsigned int item = failing("enum-name-first") ? 0u : 2u;
            snprintf(expected, sizeof(expected), "Cannot copy control 'Output Route' enum item %u", item);
            assert(string_allocations == item + 1 && item_queries == item + 1);
        }
        else if (failing("read"))
        {
            strcpy(expected, "Cannot read control 'Playback Switch'");
            assert(reads == 1 && !writes);
        }
        else if (failing("write"))
        {
            strcpy(expected, "Cannot write control 'Playback Switch'");
            assert(!reads && writes == 1 && controls[0].values[0] == 1);
        }
        else
        {
            fprintf(stderr, "Unexpected panic: %s\n", panic_message);
            abort();
        }
        if (strcmp(panic_message, expected))
            fprintf(stderr, "Expected panic: %s\nActual panic: %s\n", expected, panic_message);
        assert(!strcmp(panic_message, expected));
        printf("Expected panic: %s\n", panic_message);
    }
    assert(!live_info);
    alsa_controls_close();
    bool opened = !failing("open") && !failing("config-top") &&
                  !failing("input-open") && !failing("config-load");
    assert(closes == (opened ? 1u : 0u));
    alsa_controls_close();
    assert(closes == (opened ? 1u : 0u));
    assert(alsa_controls_find("Playback Switch") == -1);
    assert(!alsa_has_control("Output Route"));
    check_resources();
}

int main(int argument_count, char **arguments)
{
    assert(argument_count == 6);
    hardware = !strcmp(arguments[1], "hardware");
    assert(hardware || !strcmp(arguments[1], "generic"));
    fault = arguments[2];
    requested_name = arguments[3];
    requested_card = (unsigned int)strtoul(arguments[3], NULL, 10);
    open_error = atoi(arguments[4]);
    assert(open_error < 0);
    bool vendor = !strcmp(arguments[5], "vendor");
    assert(vendor || !strcmp(arguments[5], "empty"));
    if (vendor)
        create_vendor_config();
    alsa_controls_close();
    unsigned int cycles = failing("reopen") ? 3u : 1u;
    for (unsigned int cycle = 0; cycle < cycles; ++cycle)
        run_cycle();
    if (!failing("none") && !failing("reopen"))
    {
        fault = "none";
        run_cycle();
    }
    if (vendor)
        check_vendor_config();
    else
        assert(snd_config == NULL);
    printf("PASS %s %s %s %s\n", arguments[1], arguments[2], requested_name, arguments[5]);
    return 0;
}
'''


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux and libasound are required; run under WSL")
class AlsaControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc")
        if not compiler:
            raise unittest.SkipTest("gcc is unavailable")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.evidence = confined_path(central / "r1-accessibility-20261015/alsa" / stamp, central)
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands = []
        cls.runs = []
        cls.cases = []
        cls.inputs = (SOURCE, HEADER, Path(__file__).resolve())
        cls.before = cls.source_hashes()
        cls.addClassCleanup(cls.write_report)
        print("ALSA controls evidence:", cls.evidence, flush=True)
        probe = cls.evidence / "libasound-probe"
        probe_source = ("#include <alsa/asoundlib.h>\n"
                        "int main(void) { snd_config_t *root; "
                        "if (snd_config_top(&root) < 0) return 1; return snd_config_delete(root); }\n")
        result = cls.command([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                              "-x", "c", "-", "-lasound", "-o", str(probe)], input=probe_source)
        if result.returncode:
            raise unittest.SkipTest("libasound development headers/library are unavailable: " + result.stderr)
        result = cls.command([str(probe)])
        if result.returncode:
            raise unittest.SkipTest("libasound configuration API is unavailable: " + result.stderr)
        (cls.evidence / "config.h").write_text("", encoding="utf-8")
        (cls.evidence / "panic.h").write_text(
            "void panicf(const char *format, ...) __attribute__((noreturn, format(printf, 1, 2)));\n",
            encoding="utf-8")
        (cls.evidence / "debug.h").write_text("#define DEBUGF(...) ((void)0)\n", encoding="utf-8")
        harness = cls.evidence / "alsa-controls-harness.c"
        harness.write_text(HARNESS, encoding="utf-8")
        cls.bad_config = cls.evidence / "invalid-vendor-alsa.conf"
        cls.bad_config.write_text("This is deliberately invalid ALSA syntax {\n", encoding="utf-8")
        cls.binaries = {}
        for variant in ("strict", "ubsan"):
            binary = cls.evidence / ("alsa-controls-" + variant)
            command = [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                       "-I", str(cls.evidence), "-I", str(HEADER.parent), str(SOURCE), str(harness)]
            command.extend("-Wl,--wrap=" + symbol for symbol in WRAPPED)
            if variant == "ubsan":
                command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
            command.extend(["-lasound", "-o", str(binary)])
            result = cls.command(command)
            if result.returncode:
                raise AssertionError("Actual ALSA controls harness did not compile:\n" + result.stderr)
            cls.binaries[variant] = binary

    @classmethod
    def source_hashes(cls):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in cls.inputs}

    @classmethod
    def command(cls, arguments, **options):
        result = subprocess.run(arguments, cwd=cls.evidence, capture_output=True, text=True,
                                timeout=60, **options)
        cls.commands.append({"arguments": arguments, "cwd": str(cls.evidence),
                             "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        return result

    @classmethod
    def write_report(cls):
        after = cls.source_hashes()
        report = {
            "scope": "Actual alsa-controls.c; real libasound config, IDs and values; mocked control device I/O",
            "limitations": "Host regression tests do not establish bundled ALSA 1.0.26 or physical R1 acceptance",
            "source_project": str(ROOT), "source_before": cls.before, "source_after": after,
            "sources_unchanged": cls.before == after, "commands": cls.commands,
            "runs": cls.runs, "cases": cls.cases,
            "passed": bool(cls.cases) and cls.before == after and all(case["passed"] for case in cls.cases),
        }
        with (cls.evidence / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        if cls.before != after:
            raise AssertionError("ALSA controls inputs changed during validation")

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id()
                     for test, unused in result.failures + result.errors)
        self.cases.append({"name": self.id(), "passed": not failed})

    def run_case(self, mode, fault="none", target="0", error=-errno.ENODEV, vendor=False):
        for variant, binary in self.binaries.items():
            with self.subTest(variant=variant, mode=mode, fault=fault, target=target, error=error, vendor=vendor):
                arguments = [str(binary), mode, fault, target, str(error), "vendor" if vendor else "empty"]
                environment = dict(os.environ, ALSA_CONFIG_PATH=str(self.bad_config),
                                   UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                result = self.command(arguments, env=environment)
                self.runs.append({"variant": variant, "mode": mode, "fault": fault, "target": target,
                                  "error": error, "vendor": vendor, "returncode": result.returncode})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS " + mode + " " + fault + " " + target, result.stdout)

    def test_private_config_card_type_and_cached_controls(self):
        for card in ("0", "7", "4294967295"):
            self.run_case("hardware", target=card)

    def test_private_config_ignores_global_vendor_hints(self):
        self.run_case("hardware", target="5", vendor=True)

    def test_generic_open_preserves_default_and_custom_names(self):
        for name in ("default", "hw:CARD=vendor,DEV=1"):
            self.run_case("generic", target=name, vendor=True)

    def test_hardware_open_error_reports_card_code_and_strerror(self):
        for error in (-errno.ENOENT, -errno.EACCES, -errno.EINVAL):
            self.run_case("hardware", "open", "7", error, vendor=True)

    def test_generic_open_error_reports_name_code_and_strerror(self):
        for name in ("default", "hw:CARD=vendor,DEV=1"):
            self.run_case("generic", "open", name, -errno.ENODEV, vendor=True)

    def test_local_config_failures_cleanup_and_do_not_open_or_cache(self):
        for fault in ("config-top", "input-open", "config-load"):
            self.run_case("hardware", fault, "3", vendor=True)

    def test_control_list_allocation_failure_panics_before_use(self):
        for mode in ("hardware", "generic"):
            self.run_case(mode, "list-malloc", "0" if mode == "hardware" else "default")

    def test_control_enumeration_failures_remain_fatal(self):
        for fault in ("list-space", "list-first", "list-second", "info"):
            self.run_case("hardware", fault)

    def test_control_read_and_write_failures_remain_fatal(self):
        for mode in ("hardware", "generic"):
            for fault in ("read", "write"):
                self.run_case(mode, fault, "0" if mode == "hardware" else "default")

    def test_cache_allocation_failures_panic_before_use_and_allow_close(self):
        for mode in ("hardware", "generic"):
            for fault in ("cache-alloc", "info-malloc", "id-first", "id-last", "enum-alloc",
                          "enum-name-first", "enum-name-last"):
                self.run_case(mode, fault, "0" if mode == "hardware" else "default")

    def test_enum_item_query_failure_releases_temporary_info(self):
        self.run_case("hardware", "enum-info")

    def test_control_list_changes_and_incomplete_results_panic_before_cache(self):
        for fault in ("list-grew", "list-shrank", "list-incomplete", "list-used-overflow"):
            self.run_case("hardware", fault)

    def test_unrepresentable_counts_panic_before_use(self):
        for fault in ("control-count-overflow", "value-count-overflow", "enum-count-overflow"):
            self.run_case("hardware", fault)

    def test_oversized_dimensions_panic_before_alsa_value_access(self):
        for fault in ("boolean-capacity", "integer-capacity", "enum-capacity"):
            self.run_case("hardware", fault)

    def test_cache_size_overflow_or_allocation_failure_is_fatal(self):
        for fault in ("control-size-overflow", "enum-size-overflow"):
            self.run_case("hardware", fault)

    def test_maximum_supported_dimensions_preserve_values(self):
        for mode in ("hardware", "generic"):
            self.run_case(mode, "maximum-dimensions", "0" if mode == "hardware" else "default")

    def test_empty_controls_and_enum_items_are_safe_to_close(self):
        for mode in ("hardware", "generic"):
            for fault in ("empty-list", "empty-enum"):
                self.run_case(mode, fault, "0" if mode == "hardware" else "default")

    def test_close_releases_cache_and_reopen_rebuilds_it(self):
        for mode in ("hardware", "generic"):
            self.run_case(mode, "reopen", "0" if mode == "hardware" else "default", vendor=True)


if __name__ == "__main__":
    unittest.main()
