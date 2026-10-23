"""Extend the existing production keyboard fixture with echo dependencies."""

from pathlib import Path


HOST = r'''
static unsigned char echo_disk_data[256], echo_temp_data[256];
static size_t echo_disk_size, echo_temp_size, echo_disk_offset;
static bool echo_disk_exists;
static bool echo_muted, echo_menu_enabled = true, echo_synthesis = true;
static unsigned int echo_sensitivity = 100;
static int echo_feedback_count, echo_feedback_target[1024];
static bool echo_feedback_occupied[1024];
static const void *echo_feedback_owner;
static void accessibility_explore_feedback(const void *owner, int target, bool occupied)
{
    assert(owner && echo_feedback_count < 1024);
    if (echo_feedback_owner) assert(echo_feedback_owner == owner);
    echo_feedback_owner = owner;
    echo_feedback_target[echo_feedback_count] = target;
    echo_feedback_occupied[echo_feedback_count++] = occupied;
}
struct echo_speech_event
{
    int kind;
    uint32_t character;
    bool enqueue;
    int pitch;
    char text[1024];
};
static struct echo_speech_event echo_events[1024];
static int echo_event_count;
static void echo_record(int kind, uint32_t character, bool enqueue, int pitch,
                         const char *text)
{
    assert(echo_event_count < 1024);
    struct echo_speech_event *event = &echo_events[echo_event_count++];
    *event = (struct echo_speech_event){kind, character, enqueue, pitch, {0}};
    if (text) snprintf(event->text, sizeof(event->text), "%s", text);
}
static bool tts_is_available(void) { return echo_synthesis; }
static int tts_speak_character_options(uint32_t character, bool enqueue, int pitch)
{
    assert(pitch >= -80 && pitch <= 100);
    echo_record(2, character, enqueue, pitch, NULL);
    return 0;
}
static unsigned int accessibility_touch_distance(unsigned int distance)
{
    return (distance * 100u + echo_sensitivity / 2u) / echo_sensitivity;
}
static bool set_int(const unsigned char *title, const char *unit, int voice_unit,
                     const int *value, void (*callback)(int), int step,
                     int minimum, int maximum,
                     const char *(*formatter)(char *, size_t, int, const char *))
{
    (void)title; (void)callback; (void)formatter;
    assert(!strcmp(unit, "%") && voice_unit == UNIT_PERCENT);
    assert(step == 1 && minimum == -80 && maximum == 100);
    if (menu_choice >= -80) *(int *)value = menu_choice;
    return menu_result;
}
'''

FUNCTIONS = {
    "host_open": r'''
static int host_open(const char *path, int flags, ...)
{
    if (flags == O_RDONLY)
    {
        if (fault == 1) return -1;
        if (!strcmp(path, ROCKBOX_DIR "/accessibility-typing.cfg") && disk_exists)
        {
            disk_offset = 0;
            return 10;
        }
        if (!strcmp(path, ROCKBOX_DIR "/accessibility-typing-echo.cfg") && echo_disk_exists)
        {
            echo_disk_offset = 0;
            return 12;
        }
        return -1;
    }
    if (fault == 4) return -1;
    if (!strcmp(path, ROCKBOX_DIR "/accessibility-typing.cfg.tmp"))
    {
        temp_size = 0;
        return 11;
    }
    assert(!strcmp(path, ROCKBOX_DIR "/accessibility-typing-echo.cfg.tmp"));
    echo_temp_size = 0;
    return 13;
}
''',
    "host_read": r'''
static ssize_t host_read(int descriptor, void *buffer, size_t capacity)
{
    assert(descriptor == 10 || descriptor == 12);
    if (fault == 2) return -1;
    unsigned char *data = descriptor == 10 ? disk_data : echo_disk_data;
    size_t *offset = descriptor == 10 ? &disk_offset : &echo_disk_offset;
    size_t size = descriptor == 10 ? disk_size : echo_disk_size;
    size_t count = size - *offset;
    if (count > capacity) count = capacity;
    if (read_chunk && count > (size_t)read_chunk) count = read_chunk;
    memcpy(buffer, data + *offset, count);
    *offset += count;
    return count;
}
''',
    "host_write": r'''
static ssize_t host_write(int descriptor, const void *buffer, size_t count)
{
    assert(descriptor == 11 || descriptor == 13);
    ++write_calls;
    if (fault == 5) return -1;
    if (fault == 9) return 0;
    if (write_chunk && count > (size_t)write_chunk) count = write_chunk;
    unsigned char *data = descriptor == 11 ? temp_data : echo_temp_data;
    size_t *size = descriptor == 11 ? &temp_size : &echo_temp_size;
    assert(*size + count < (descriptor == 11 ? sizeof(temp_data) : sizeof(echo_temp_data)));
    memcpy(data + *size, buffer, count);
    *size += count;
    return count;
}
''',
    "host_fsync": r'''
static int host_fsync(int descriptor)
{
    assert(descriptor == 11 || descriptor == 13);
    ++sync_calls;
    return fault == 6 ? -1 : 0;
}
''',
    "host_close": r'''
static int host_close(int descriptor)
{
    return ((descriptor == 10 || descriptor == 12) && fault == 3) ||
        ((descriptor == 11 || descriptor == 13) && fault == 7) ? -1 : 0;
}
''',
    "host_rename": r'''
static int host_rename(const char *source, const char *destination)
{
    ++rename_calls;
    if (fault == 8) return -1;
    if (!strcmp(source, ROCKBOX_DIR "/accessibility-typing.cfg.tmp"))
    {
        assert(!strcmp(destination, ROCKBOX_DIR "/accessibility-typing.cfg"));
        memcpy(disk_data, temp_data, temp_size);
        disk_size = temp_size;
        disk_exists = true;
    }
    else
    {
        assert(!strcmp(source, ROCKBOX_DIR "/accessibility-typing-echo.cfg.tmp"));
        assert(!strcmp(destination, ROCKBOX_DIR "/accessibility-typing-echo.cfg"));
        memcpy(echo_disk_data, echo_temp_data, echo_temp_size);
        echo_disk_size = echo_temp_size;
        echo_disk_exists = true;
    }
    return 0;
}
''',
    "host_remove": r'''
static int host_remove(const char *path)
{
    if (!strcmp(path, ROCKBOX_DIR "/accessibility-typing.cfg.tmp")) temp_size = 0;
    else
    {
        assert(!strcmp(path, ROCKBOX_DIR "/accessibility-typing-echo.cfg.tmp"));
        echo_temp_size = 0;
    }
    return 0;
}
''',
    "talk_id": r'''
static int talk_id(int label, bool enqueue)
{
    if (echo_muted) return -1;
    assert(spoken_count < 1024);
    spoken[spoken_count++] = label;
    echo_record(1, label, enqueue, 0, NULL);
    return 0;
}
''',
    "talk_spell": r'''
static int talk_spell(const void *text, bool enqueue)
{
    if (echo_muted) return -1;
    if (*(const char *)text)
    {
        snprintf((char *)spelled, sizeof(spelled), "%s", (const char *)text);
        echo_record(3, 0, enqueue, 0, text);
    }
    return 0;
}
''',
}

PROBES = r'''
void echo_probe_reset(void)
{
    echo_loaded = false;
    echo_disk_exists = false;
    echo_disk_size = echo_temp_size = echo_disk_offset = 0;
    echo_muted = false;
    echo_menu_enabled = echo_synthesis = true;
    echo_sensitivity = 100;
    echo_event_count = 0;
    echo_feedback_count = 0;
    echo_feedback_owner = NULL;
}
void echo_probe_policy(bool menus, bool muted, bool synthesis)
{ echo_menu_enabled = menus; echo_muted = muted; echo_synthesis = synthesis; }
void echo_probe_sensitivity(unsigned int percent) { echo_sensitivity = percent; }
int echo_probe_feedback_count(void) { return echo_feedback_count; }
int echo_probe_feedback_target(int index)
{ assert(index >= 0 && index < echo_feedback_count); return echo_feedback_target[index]; }
int echo_probe_feedback_occupied(int index)
{ assert(index >= 0 && index < echo_feedback_count); return echo_feedback_occupied[index]; }
bool echo_probe_save(int echo, int deletion, int capitals, int pitch)
{
    struct accessibility_typing_echo_settings settings = {echo, deletion, capitals, pitch};
    return accessibility_typing_set_echo_settings(&settings);
}
int echo_probe_setting(int index)
{
    struct accessibility_typing_echo_settings settings;
    accessibility_typing_get_echo_settings(&settings);
    int values[] = {settings.echo, settings.deletion, settings.capitals, settings.pitch_percent};
    assert(index >= 0 && index < 4);
    return values[index];
}
void echo_probe_disk(const char *data, size_t length)
{
    assert(length < sizeof(echo_disk_data));
    memcpy(echo_disk_data, data, length);
    echo_disk_size = length;
    echo_disk_exists = true;
    echo_loaded = false;
}
const char *echo_probe_disk_text(void)
{ echo_disk_data[echo_disk_size] = 0; return (const char *)echo_disk_data; }
void echo_probe_clear(void) { echo_event_count = 0; }
int echo_probe_count(void) { return echo_event_count; }
int echo_probe_event(int index, int field)
{
    assert(index >= 0 && index < echo_event_count);
    struct echo_speech_event *event = &echo_events[index];
    int values[] = {event->kind, event->character, event->enqueue, event->pitch};
    assert(field >= 0 && field < 4);
    return values[field];
}
const char *echo_probe_text(int index)
{ assert(index >= 0 && index < echo_event_count); return echo_events[index].text; }
int echo_probe_run(char *text, int capacity, const uint16_t *layout)
{ return kbd_input(text, capacity, (ucschar_t *)layout); }
int echo_probe_run_ex(char *text, int capacity, const uint16_t *layout, bool *usb)
{ return kbd_input_ex(text, capacity, (ucschar_t *)layout, usb); }
void echo_probe_script_clear(void)
{
    assert(action_count < 1024);
    script[action_count++] = (struct scripted_action){.type = -3};
}
'''


class _Namespace:
    def __init__(self, values):
        object.__setattr__(self, "values", values)

    def __getattr__(self, name):
        try:
            return self.values[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        self.values[name] = value


def install(legacy):
    if isinstance(legacy, dict):
        legacy = _Namespace(legacy)
    if getattr(legacy, "typing_echo_installed", False):
        return
    legacy.typing_echo_installed = True
    unicode_source = (legacy.ROOT / "lib/utf8proc/utf8proc.c").as_posix()
    preamble = '#define UTF8PROC_STATIC\n#include "' + unicode_source + '"\n' + legacy.PREAMBLE
    preamble = preamble.replace("static int host_open(", "#define UNIT_PERCENT 14\n" + HOST + "\nstatic int host_open(", 1)
    for name, replacement in FUNCTIONS.items():
        original = legacy.function(preamble, name).rstrip()
        preamble = preamble.replace(original, replacement.strip(), 1)
    preamble = preamble.replace("assert(count == 3);", "assert(count == 3 || count == 4);")
    preamble = preamble.replace("(void)settings; return true;", "(void)settings; return echo_menu_enabled;")
    legacy.PREAMBLE = preamble
    legacy.KEYBOARD_HOST = legacy.KEYBOARD_HOST.replace(
        "    if (event.type == -2)",
        "    if (event.type == -3) { echo_event_count = 0; return ACTION_NONE; }\n"
        "    if (event.type == -2)", 1)
    legacy.PROBES = ("void echo_probe_reset(void);\n" +
                     legacy.PROBES.replace("    accessibility_typing_end();", "    echo_probe_reset();\n    accessibility_typing_end();", 1) +
                     PROBES)
    original_confined = legacy.confined_path

    def confined(path, *roots, **options):
        path = Path(path)
        if "typing-tests" in path.parts and "r1-hardening-20261015" in path.parts:
            path = roots[0] / "r1-input-refinements-20261017" / "typing-echo-tests" / path.name
        return original_confined(path, *roots, **options)

    legacy.confined_path = confined
    legacy.INPUTS += (
        "tools/tests/typing_echo_fixture.py", "tools/tests/typing_echo.py",
        "lib/utf8proc/utf8proc.c", "lib/utf8proc/utf8proc.h", "lib/utf8proc/utf8proc_data.c",
    )
