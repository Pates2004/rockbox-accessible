import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest

from test_tts_plugin_policy import with_menu_policy


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
EVIDENCE = _project_materials_root(ROOT) / "plugin-utilities-tests" / RUN
PLUGINS = ("calculator", "stopwatch", "metronome")


def extract_function(source, signature):
    start = source.index(signature)
    masked = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        lambda match: " " * len(match.group()), source, flags=re.DOTALL)
    opening = masked.index("{", start)
    depth = 1
    closing = opening + 1
    while depth:
        if masked[closing] == "{":
            depth += 1
        elif masked[closing] == "}":
            depth -= 1
        closing += 1
    return source[start:closing] + "\n"


COMMON = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <fcntl.h>
#define CONFIG_KEYPAD 37
#define SANSA_CLIP_PAD 37
#define HZ 100
#define LCD_WIDTH 128
#define LCD_HEIGHT 96
#define LCD_DEPTH 16
#define FONT_SYSFIXED 0
#define FONT_UI 1
#define DRMODE_SOLID 0
#define DRMODE_COMPLEMENT 1
#define DRMODE_INVERSEVID 2
#define SCREEN_MAIN 0
#define Icon_NOICON 0
#define GUI_EVENT_ACTIONUPDATE 1
#define PLUGIN_APPS_DATA_DIR "."
#define FOR_NB_SCREENS(screen_index) for (int screen_index = 0; screen_index < 1; ++screen_index)
#define BUTTON_NONE 0
#define BUTTON_LEFT 1
#define BUTTON_RIGHT 2
#define BUTTON_UP 4
#define BUTTON_DOWN 8
#define BUTTON_SELECT 16
#define BUTTON_HOME 32
#define BUTTON_POWER 64
#define BUTTON_REL 256
#define BUTTON_REPEAT 512
#define SYS_USB_CONNECTED 1024
#define TIME_BEFORE(first_tick, second_tick) ((long)((first_tick) - (second_tick)) < 0)
#define UNIT_SEC 1
#define UNIT_MIN 2
#define UNIT_HOUR 3
#define UNIT_DB 4
#define SOUND_VOLUME 0
#define TIMEOUT_NOBLOCK 0
#define INPUT_SRC_CAPS 0
#define SAMPR_44 44100
#define PLA_ARRAY_COUNT 1
#define PLA_EXIT 1
#define PLA_UP 2
#define PLA_DOWN 3
#define PLA_UP_REPEAT 4
#define PLA_DOWN_REPEAT 5
#define PLA_LEFT 6
#define PLA_RIGHT 7
#define PLA_LEFT_REPEAT 8
#define PLA_RIGHT_REPEAT 9
#define PLA_SELECT_REL 10
#define PLA_CANCEL 11
#define PLA_SELECT_REPEAT 12
#define PLA_SELECT 13
enum plugin_status { PLUGIN_OK, PLUGIN_ERROR, PLUGIN_USB_CONNECTED };
struct viewport { int height; };
struct user_settings { bool talk_menu, tts_enabled; };
struct global_status { int volume; };
struct screen {
    void (*setfont)(int font);
    int (*getstringsize)(const char *text, int *width, int *height);
    struct viewport *(*set_viewport)(struct viewport *view);
    void (*clear_viewport)(void);
    void (*puts)(int column, int row, const char *text);
    void (*puts_scroll)(int column, int row, const char *text);
    void (*update_viewport)(void);
};
struct plugin_api {
    struct user_settings *global_settings;
    struct global_status *global_status;
    struct screen *screens[1];
    volatile long *current_tick;
    int (*talk_id)(int32_t label, bool enqueue);
    int (*talk_number)(long number, bool enqueue);
    int (*talk_spell)(const char *text, bool enqueue);
    int (*talk_value_decimal)(long value, int unit, int decimals, bool enqueue);
    int (*snprintf)(char *text, size_t size, const char *format, ...);
    int (*atoi)(const char *text);
    char *(*strchr)(const char *text, int character);
    char *(*strncpy)(char *target, const char *source, size_t size);
    void (*lcd_clear_display)(void);
    void (*lcd_setfont)(int font);
    void (*lcd_set_drawmode)(int mode);
    int (*lcd_getstringsize)(const unsigned char *text, int *width, int *height);
    void (*lcd_fillrect)(int left, int top, int width, int height);
    void (*lcd_hline)(int left, int right, int row);
    void (*lcd_vline)(int column, int top, int bottom);
    void (*lcd_putsxy)(int left, int top, const unsigned char *text);
    void (*lcd_update)(void);
    void (*lcd_update_rect)(int left, int top, int width, int height);
    void (*screen_clear_area)(struct screen *display, int left, int top, int width, int height);
    unsigned int (*sleep)(unsigned int ticks);
    void (*button_clear_queue)(void);
    int (*button_get_w_tmo)(int timeout);
    long (*default_event_handler)(long button);
    int (*open)(const char *path, int flags, ...);
    ssize_t (*read)(int descriptor, void *data, size_t size);
    ssize_t (*write)(int descriptor, const void *data, size_t size);
    int (*close)(int descriptor);
    void (*reset_poweroff_timer)(void);
    void (*sb_set_persistent_title)(const char *title, int icon, int screen_index);
    void (*viewportmanager_theme_enable)(int screen_index, bool enable, void *data);
    void (*viewportmanager_theme_undo)(int screen_index, bool force);
    void (*viewport_set_defaults)(struct viewport *view, int screen_index);
    void (*send_event)(int event, void *data);
    int (*sound_min)(int setting);
    int (*sound_max)(int setting);
    void (*audio_stop)(void);
    void (*mixer_set_frequency)(int frequency);
    void (*pcmbuf_fade)(bool fade, bool audible);
    int (*read_line)(int descriptor, char *text, int size);
    void (*splash)(int ticks, const char *text);
    void (*yield)(void);
};
struct spoken_event {
    char type;
    long value;
    int unit;
    int decimals;
    bool enqueue;
    char text[128];
};
static struct user_settings settings = { .talk_menu = true };
static struct global_status status = { -25 };
static volatile long current_tick;
static struct spoken_event spoken[4096];
static size_t spoken_count;
static bool fail_speech;
static int queued_buttons[4096];
static size_t button_count, button_index;
static int draws;
static struct spoken_event *record_event(char type, long value, bool enqueue)
{
    assert(spoken_count < sizeof(spoken) / sizeof(spoken[0]));
    struct spoken_event *event = &spoken[spoken_count++];
    memset(event, 0, sizeof(*event));
    event->type = type;
    event->value = value;
    event->enqueue = enqueue;
    return event;
}
static int speech_id(int32_t label, bool enqueue)
{ record_event('i', label, enqueue); return fail_speech ? -1 : 0; }
static int speech_number(long number, bool enqueue)
{ record_event('n', number, enqueue); return fail_speech ? -1 : 0; }
static int speech_text(const char *text, bool enqueue)
{
    struct spoken_event *event = record_event('s', 0, enqueue);
    snprintf(event->text, sizeof(event->text), "%s", text);
    return fail_speech ? -1 : 0;
}
static int speech_value(long value, int unit, int decimals, bool enqueue)
{
    struct spoken_event *event = record_event('v', value, enqueue);
    event->unit = unit;
    event->decimals = decimals;
    return fail_speech ? -1 : 0;
}
static void nothing(void) { ++draws; }
static void integer_noop(int value) { (void)value; }
static void triple_noop(int first, int second, int third)
{ (void)first; (void)second; (void)third; }
static void rectangle_noop(int left, int top, int width, int height)
{ (void)left; (void)top; (void)width; (void)height; ++draws; }
static void clear_area(struct screen *display, int left, int top, int width, int height)
{ (void)display; rectangle_noop(left, top, width, height); }
static void puts_noop(int left, int top, const char *text)
{ (void)left; (void)top; (void)text; ++draws; }
static void puts_unsigned(int left, int top, const unsigned char *text)
{ puts_noop(left, top, (const char *)text); }
static int string_size(const char *text, int *width, int *height)
{
    if (width) *width = (int)strlen(text) * 4;
    if (height) *height = 8;
    return 0;
}
static int string_size_unsigned(const unsigned char *text, int *width, int *height)
{ return string_size((const char *)text, width, height); }
static struct viewport *viewport_noop(struct viewport *view) { return view; }
static unsigned int sleep_noop(unsigned int ticks) { (void)ticks; return 0; }
static long event_noop(long button) { (void)button; return 0; }
static int open_no_file(const char *path, int flags, ...)
{ (void)path; (void)flags; return -1; }
static int close_noop(int descriptor) { (void)descriptor; return 0; }
static void title_noop(const char *title, int icon, int screen_index)
{ (void)title; (void)icon; (void)screen_index; }
static void theme_enable_noop(int screen_index, bool enable, void *data)
{ (void)screen_index; (void)enable; (void)data; }
static void theme_undo_noop(int screen_index, bool force)
{ (void)screen_index; (void)force; }
static void viewport_defaults(struct viewport *view, int screen_index)
{ (void)screen_index; view->height = 40; }
static void send_noop(int event, void *data) { (void)event; (void)data; }
static int sound_minimum(int setting) { (void)setting; return -60; }
static int sound_maximum(int setting) { (void)setting; return 6; }
static void fade_noop(bool fade, bool audible) { (void)fade; (void)audible; }
static int read_line_noop(int descriptor, char *text, int size)
{ (void)descriptor; (void)text; (void)size; return 0; }
static void splash_noop(int ticks, const char *text) { (void)ticks; (void)text; }
static int next_button(int timeout)
{
    (void)timeout;
    assert(button_index < button_count);
    current_tick += 10;
    return queued_buttons[button_index++];
}
static struct screen display = {
    integer_noop, string_size, viewport_noop, nothing,
    puts_noop, puts_noop, nothing
};
static struct plugin_api api = {
    .global_settings = &settings, .global_status = &status,
    .screens = { &display }, .current_tick = &current_tick,
    .talk_id = speech_id, .talk_number = speech_number,
    .talk_spell = speech_text, .talk_value_decimal = speech_value,
    .snprintf = snprintf, .atoi = atoi, .strchr = strchr, .strncpy = strncpy,
    .lcd_clear_display = nothing, .lcd_setfont = integer_noop,
    .lcd_set_drawmode = integer_noop, .lcd_getstringsize = string_size_unsigned,
    .lcd_fillrect = rectangle_noop, .lcd_hline = triple_noop,
    .lcd_vline = triple_noop, .lcd_putsxy = puts_unsigned, .lcd_update = nothing,
    .lcd_update_rect = rectangle_noop, .screen_clear_area = clear_area,
    .sleep = sleep_noop, .button_clear_queue = nothing,
    .button_get_w_tmo = next_button, .default_event_handler = event_noop,
    .open = open_no_file, .close = close_noop, .reset_poweroff_timer = nothing,
    .sb_set_persistent_title = title_noop,
    .viewportmanager_theme_enable = theme_enable_noop,
    .viewportmanager_theme_undo = theme_undo_noop,
    .viewport_set_defaults = viewport_defaults, .send_event = send_noop,
    .sound_min = sound_minimum, .sound_max = sound_maximum,
    .audio_stop = nothing, .mixer_set_frequency = integer_noop,
    .pcmbuf_fade = fade_noop, .read_line = read_line_noop,
    .splash = splash_noop, .yield = nothing
};
static const struct plugin_api *rb = &api;
static void reset_events(void) { spoken_count = 0; }
static bool contains_id(int label)
{
    for (size_t index = 0; index < spoken_count; ++index)
        if (spoken[index].type == 'i' && spoken[index].value == label)
            return true;
    return false;
}
static bool contains_text(const char *text)
{
    for (size_t index = 0; index < spoken_count; ++index)
        if (spoken[index].type == 's' && strcmp(spoken[index].text, text) == 0)
            return true;
    return false;
}
static bool contains_number(long value)
{
    for (size_t index = 0; index < spoken_count; ++index)
        if (spoken[index].type == 'n' && spoken[index].value == value)
            return true;
    return false;
}
static void queue_button(int button)
{
    assert(button_count < sizeof(queued_buttons) / sizeof(queued_buttons[0]));
    queued_buttons[button_count++] = button;
}
'''


CALCULATOR_TEST = r'''
static void select_calculator_button(int selected)
{
    btn_row = selected / BUTTON_COLS;
    btn_col = selected % BUTTON_COLS;
}
static void activate_calculator_button(int selected)
{
    select_calculator_button(selected);
    lastbtn = CALCULATOR_INPUT_CALC_PRE;
    btn = CALCULATOR_INPUT;
    handleButton(btn);
}
int main(void)
{
    cal_initial();
    assert(spoken_count == 1 && contains_number(5));
    reset_events();
    for (int redraw = 0; redraw < 100; ++redraw)
    { drawButtons(buttonGroup); drawLines(); printResult(); handleButton(BUTTON_NONE); }
    assert(spoken_count == 0);
    handleButton(CALCULATOR_RIGHT);
    assert(contains_number(6) && spoken_count == 1 && !spoken[0].enqueue);
    reset_events();
    handleButton(CALCULATOR_RIGHT);
    assert(contains_id(LANG_CALCULATOR_MULTIPLY));
    reset_events();
    activate_calculator_button(btn_C);
    activate_calculator_button(btn_2);
    activate_calculator_button(btn_add);
    activate_calculator_button(btn_3);
    reset_events();
    activate_calculator_button(btn_equal);
    assert(contains_id(LANG_CALCULATOR_EQUALS));
    assert(contains_id(LANG_CALCULATOR_RESULT) && contains_text("5"));
    assert(spoken_count == 3 && !spoken[0].enqueue && spoken[1].enqueue);
    reset_events();
    btn = CALCULATOR_CALC;
    lastbtn = CALCULATOR_INPUT_CALC_PRE;
    handleButton(btn);
    assert(spoken_count == 2 && contains_text("5") && !spoken[0].enqueue);
    reset_events();
    lastbtn = BUTTON_NONE;
    handleButton(CALCULATOR_INPUT);
    assert(spoken_count == 0);
    activate_calculator_button(btn_C);
    activate_calculator_button(btn_2);
    activate_calculator_button(btn_3);
    reset_events();
    btn = CALCULATOR_CLEAR;
    handleButton(btn);
    assert(contains_id(LANG_CALCULATOR_RESULT) && contains_text("2"));
    activate_calculator_button(btn_C);
    reset_events();
    activate_calculator_button(btn_rec);
    assert(calStatus == cal_error && contains_id(LANG_ERROR_FORMATSTR));
    activate_calculator_button(btn_C);
    activate_calculator_button(btn_bas);
    assert(buttonGroup == sciButtons && contains_id(LANG_CALCULATOR_SCIENTIFIC));
    assert(contains_id(LANG_CALCULATOR_BASIC));
    reset_events();
    for (int group = basicButtons; group <= sciButtons; ++group)
    {
        buttonGroup = group;
        for (int selected = 0; selected < BUTTON_ROWS * BUTTON_COLS; ++selected)
        {
            select_calculator_button(selected);
            size_t previous_count = spoken_count;
            calculator_talk_button(false);
            assert(spoken_count == previous_count + 1);
        }
    }
    reset_events();
    result = 0.123456789; power = 15; calStatus = cal_normal;
    printResult(); calculator_talk_result(false);
    assert(contains_text("1.23456789"));
    assert(contains_id(LANG_CALCULATOR_EXPONENT) && contains_number(14));
    reset_events();
    result = -0.5; power = -100; calStatus = cal_normal;
    printResult(); calculator_talk_result(false);
    assert(contains_text("-5") && contains_number(-101));
    reset_events();
    calStatus = cal_error;
    calculator_talk_result(false);
    assert(spoken_count == 1 && contains_id(LANG_ERROR_FORMATSTR));
    reset_events();
    settings.talk_menu = false;
    calculator_talk_button(false); calculator_talk_result(false);
    handleButton(CALCULATOR_LEFT);
    assert(spoken_count == 0);
    settings.talk_menu = true;
    fail_speech = true; calStatus = cal_normal; printResult();
    calculator_talk_result(false);
    assert(spoken_count == 1);
    reset_events(); fail_speech = false;
    btn_row = -1; calculator_talk_button(false);
    btn_row = BUTTON_ROWS; calculator_talk_button(false);
    btn_row = 0; buttonGroup = -1; calculator_talk_button(false);
    assert(spoken_count == 0);
    puts("calculator: focus, actions, full results, exponent, error, disabled and failure pass");
    return 0;
}
'''


STOPWATCH_TEST = r'''
int main(void)
{
    stopwatch = 0; counting = false;
    stopwatch_talk_state();
    assert(contains_id(LANG_COUNTDOWN_TIMER_PAUSED));
    assert(spoken[spoken_count - 1].type == 'v');
    assert(spoken[spoken_count - 1].value == 0);
    reset_events();
    stopwatch_talk_time(366125, false);
    assert(spoken_count == 3);
    assert(spoken[0].value == 1 && spoken[0].unit == UNIT_HOUR);
    assert(spoken[1].value == 1 && spoken[1].unit == UNIT_MIN);
    assert(spoken[2].value == 125 && spoken[2].unit == UNIT_SEC);
    assert(spoken[2].decimals == 2 && spoken[2].enqueue);
    reset_events();
    stopwatch_talk_time(-1, false);
    assert(spoken_count == 1 && spoken[0].value == 0);
    reset_events();
    curr_lap = 3;
    lap_times[0] = 100; lap_times[1] = 275; lap_times[2] = 500;
    stopwatch_talk_lap(2);
    assert(contains_id(LANG_STOPWATCH_LAP) && contains_number(2));
    assert(contains_id(LANG_STOPWATCH_SPLIT));
    assert(spoken[spoken_count - 1].value == 175);
    reset_events();
    stopwatch_talk_lap(0); stopwatch_talk_lap(4);
    assert(spoken_count == 0);
    curr_lap = MAX_LAPS + 2;
    stopwatch_talk_lap(2);
    assert(spoken_count == 0);
    stopwatch_talk_lap(3);
    assert(!contains_id(LANG_STOPWATCH_SPLIT));
    reset_events();
    settings.talk_menu = false;
    stopwatch_talk_state(); stopwatch_talk_lap(3); stopwatch_talk_time(100, false);
    assert(spoken_count == 0);
    settings.talk_menu = true; fail_speech = true;
    stopwatch_talk_state();
    assert(spoken_count == 1);
    reset_events(); fail_speech = false;
    curr_lap = 0; lap_scroll = 0; prev_total = 0; counting = false;
    current_tick = 0; button_count = button_index = 0;
    queue_button(STOPWATCH_START_STOP);
    for (int idle = 0; idle < 10; ++idle) queue_button(BUTTON_NONE);
    queue_button(STOPWATCH_LAP_TIMER);
    queue_button(STOPWATCH_LAP_TIMER);
    queue_button(STOPWATCH_START_STOP);
    queue_button(STOPWATCH_SCROLL_DOWN);
    queue_button(STOPWATCH_RESET_TIMER);
    queue_button(STOPWATCH_QUIT);
    assert(plugin_start(NULL) == PLUGIN_OK);
    assert(contains_id(LANG_COUNTDOWN_TIMER_RUNNING));
    assert(contains_id(LANG_STOPWATCH_LAP));
    assert(contains_id(LANG_STOPWATCH_SPLIT));
    assert(lap_times[0] == 110 && lap_times[1] == 120);
    assert(!counting && curr_lap == 0 && stopwatch == 0);
    assert(spoken_count < 40);
    reset_events();
    button_count = button_index = 0;
    for (int idle = 0; idle < 100; ++idle) queue_button(BUTTON_NONE);
    queue_button(STOPWATCH_QUIT);
    plugin_start(NULL);
    assert(spoken_count == 3);
    puts("stopwatch: state, exact action time, laps, split, wrap, idle, disabled and failure pass");
    return 0;
}
'''


METRONOME_STUBS = r'''
static const unsigned int timerfreq_div = 1024;
static bool reset_tap, sound_trigger;
static int tap_count, tap_time, tap_timeout, bpm_step_counter;
static char buffer[64], storage[16384];
static char *linebuf;
static size_t linebuf_size;
static char *mem_end, *mem_free_region;
static int fd = -1;
static const int plugin_contexts[] = { 0 };
static void cleanup(void) { }
static void mem_init(void)
{ mem_end = storage + sizeof(storage); mem_free_region = storage; }
static void *mem_allocate(size_t size)
{
    assert(size <= (size_t)(mem_end - mem_free_region));
    void *allocated = mem_free_region;
    mem_free_region += size;
    return allocated;
}
static void prepare_buffers(void) { }
static void tweak_volume(int offset) { (void)offset; }
static void calc_period(void) { bpm = part->bpm; period = 100; }
static void trigger_display(int state) { display_state = state; display_trigger = true; }
static void draw_display(void) { ++draws; }
static void play_ticktock(void) { ++draws; }
static void metronome_pause(void) { sound_paused = true; }
static void metronome_unpause(void) { sound_paused = false; }
static void parse_part(char *line, unsigned int number) { (void)line; (void)number; }
static void exit_on_usb(int button) { (void)button; }
static int pluginlib_getaction(int timeout, const int *contexts, size_t count)
{ (void)contexts; (void)count; return next_button(timeout); }
'''


METRONOME_TEST = r'''
int main(void)
{
    struct part first_part, second_part;
    part_init(&first_part); part_init(&second_part);
    part = &first_part; bpm = 120; sound_paused = true;
    speech_pending = METRONOME_SPEAK_STATE | METRONOME_SPEAK_TEMPO |
                     METRONOME_SPEAK_METER | METRONOME_SPEAK_VOLUME;
    metronome_speech_flush();
    assert(contains_id(LANG_COUNTDOWN_TIMER_PAUSED));
    assert(contains_id(LANG_METRONOME_TEMPO) && contains_number(120));
    assert(contains_id(LANG_METRONOME_METER) && contains_id(LANG_VOLUME));
    assert(!spoken[0].enqueue && spoken[spoken_count - 1].value == -25);
    reset_events();
    for (int idle = 0; idle < 1000; ++idle)
    { ++bpm; ++bar; ++current_tick; metronome_speech_flush(); }
    assert(spoken_count == 0);
    bpm = part->bpm = 120;
    for (int repeat = 0; repeat < 30; ++repeat)
    {
        struct metronome_speech_state previous = metronome_speech_snapshot();
        change_bpm(1);
        metronome_speech_request(previous);
        current_tick += 2;
        metronome_speech_flush();
    }
    assert(spoken_count == 0);
    current_tick += HZ / 5;
    metronome_speech_flush();
    assert(spoken_count == 2 && contains_id(LANG_METRONOME_TEMPO));
    assert(contains_number(bpm));
    reset_events();
    bpm = part->bpm = 400;
    struct metronome_speech_state capped = metronome_speech_snapshot();
    for (int repeat = 0; repeat < 100; ++repeat)
    {
        change_bpm(1); metronome_speech_request(capped);
        ++current_tick; metronome_speech_flush();
    }
    assert(spoken_count == 0);
    track_mode = true;
    struct metronome_speech_state previous = metronome_speech_snapshot();
    second_part.id = 1; second_part.bpm = 90;
    second_part.beats_per_bar = 3; second_part.base_beat = 8;
    char long_label[200]; memset(long_label, 'A', sizeof(long_label));
    long_label[sizeof(long_label) - 1] = '\0'; second_part.label = long_label;
    part = &second_part; bpm = 90; bar = 2;
    metronome_speech_request(previous);
    current_tick += HZ / 5;
    metronome_speech_flush();
    assert(contains_id(LANG_METRONOME_PART) && contains_id(LANG_METRONOME_BAR));
    assert(contains_id(LANG_METRONOME_METER));
    for (size_t index = 0; index < spoken_count; ++index)
        if (spoken[index].type == 's') assert(strlen(spoken[index].text) == 63);
    reset_events();
    long_label[62] = (char)0xc4; long_label[63] = (char)0x85;
    speech_pending = METRONOME_SPEAK_POSITION;
    metronome_speech_flush();
    for (size_t index = 0; index < spoken_count; ++index)
        if (spoken[index].type == 's') assert(strlen(spoken[index].text) == 62);
    reset_events();
    previous = metronome_speech_snapshot();
    sound_paused = false;
    metronome_speech_request(previous); metronome_speech_flush();
    assert(spoken_count == 1 && contains_id(LANG_COUNTDOWN_TIMER_RUNNING));
    reset_events();
    previous = metronome_speech_snapshot();
    change_volume(1); metronome_speech_request(previous);
    settings.talk_menu = false;
    current_tick += HZ;
    metronome_speech_flush();
    assert(spoken_count == 0 && speech_pending == 0);
    settings.talk_menu = true;
    metronome_speech_flush(); assert(spoken_count == 0);
    fail_speech = true; speech_pending = METRONOME_SPEAK_TEMPO;
    metronome_speech_flush();
    assert(spoken_count == 1 && speech_pending == 0);
    reset_events(); fail_speech = false;
    part = part_list = NULL; parts = bad_parts = 0;
    track_mode = false; sound_paused = true;
    button_count = button_index = 0; current_tick = 0;
    queue_button(METRONOME_RIGHT);
    queue_button(METRONOME_RIGHT_REP);
    queue_button(METRONOME_VOL_UP);
    for (int idle = 0; idle < 5; ++idle) queue_button(BUTTON_NONE);
    queue_button(METRONOME_PLAY);
    for (int idle = 0; idle < 100; ++idle) queue_button(BUTTON_NONE);
    queue_button(METRONOME_PAUSE);
    queue_button(METRONOME_QUIT);
    assert(plugin_start(NULL) == PLUGIN_OK);
    assert(spoken_count == 14);
    assert(part->bpm == 122 && sound_paused);
    assert(contains_id(LANG_COUNTDOWN_TIMER_RUNNING));
    puts("metronome: action loop, tempo, meter, volume, state, coalescing, idle, disabled and failure pass");
    return 0;
}
'''


class PluginUtilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {
            name: (ROOT / f"apps/plugins/{name}.c").read_text(encoding="utf-8")
            for name in PLUGINS
        }
        EVIDENCE.mkdir(parents=True)
        identifiers = sorted(set(re.findall(
            r"\b(?:LANG|VOICE)_[A-Z_]+\b", "\n".join(cls.sources.values()))))
        declarations = "\n".join(
            f"#define {identifier} {index + 100}"
            for index, identifier in enumerate(identifiers))
        (EVIDENCE / "plugin.h").write_text(with_menu_policy(COMMON) + declarations, encoding="utf-8")
        for name in ("calculator", "stopwatch"):
            (EVIDENCE / f"{name}-actual.c").write_text(cls.sources[name], encoding="utf-8")
        metronome = cls.sources["metronome"]
        metronome_parts = [
            '#include "plugin.h"\n',
            metronome[metronome.index("#if (CONFIG_KEYPAD == IPOD_1G2G_PAD)"):
                      metronome.index("#ifdef MET_SYNC\nenum")],
            metronome[metronome.index("struct part;"):
                      metronome.index("/* global static buffer")],
            METRONOME_STUBS,
        ]
        for signature in (
            "static void change_volume(", "static void change_bpm(",
            "static void step_back(", "static void step_forw(",
            "static void tap(", "enum plugin_status plugin_start(",
        ):
            metronome_parts.append(extract_function(metronome, signature))
        (EVIDENCE / "metronome-actual.c").write_text(
            "\n".join(metronome_parts), encoding="utf-8")
        for name, body in zip(PLUGINS, (CALCULATOR_TEST, STOPWATCH_TEST, METRONOME_TEST)):
            (EVIDENCE / f"{name}-test.c").write_text(
                f'#include "{name}-actual.c"\n' + body, encoding="utf-8")
        (EVIDENCE / "inputs.json").write_text(json.dumps({
            f"apps/plugins/{name}.c": hashlib.sha256(source.encode()).hexdigest()
            for name, source in cls.sources.items()
        }, indent=2), encoding="utf-8")

    def run_harness(self, name, espeak, sanitize):
        mode = ("espeak" if espeak else "legacy") + ("-ubsan" if sanitize else "")
        output = EVIDENCE / f"{name}-{mode}"
        output.mkdir()
        executable = output / "utility-test"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-unused-variable", "-Wno-pointer-sign",
            "-Wno-implicit-fallthrough", "-I", str(EVIDENCE),
            str(EVIDENCE / f"{name}-test.c"), "-lm", "-o", str(executable),
        ]
        if espeak:
            command.append("-DHAVE_ESPEAK")
        if sanitize:
            command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
        compiled = subprocess.run(
            command, cwd=output, capture_output=True, text=True, timeout=60)
        (output / "compile.log").write_text(
            shlex.join(command) + "\n" + compiled.stdout + compiled.stderr, encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        tested = subprocess.run(
            [str(executable)], cwd=output, capture_output=True, text=True, timeout=30)
        (output / "result.json").write_text(json.dumps({
            "plugin": name, "mode": mode, "returncode": tested.returncode,
            "stdout": tested.stdout, "stderr": tested.stderr,
        }, indent=2), encoding="utf-8")
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_calculator(self):
        for espeak in (False, True):
            for sanitize in (False, True):
                with self.subTest(espeak=espeak, sanitize=sanitize):
                    self.run_harness("calculator", espeak, sanitize)

    def test_stopwatch(self):
        for espeak in (False, True):
            for sanitize in (False, True):
                with self.subTest(espeak=espeak, sanitize=sanitize):
                    self.run_harness("stopwatch", espeak, sanitize)

    def test_metronome(self):
        for espeak in (False, True):
            for sanitize in (False, True):
                with self.subTest(espeak=espeak, sanitize=sanitize):
                    self.run_harness("metronome", espeak, sanitize)

    def test_paint_and_timer_paths_remain_silent(self):
        for name, signatures in {
            "calculator": ("static void drawButtons(", "static void printResult("),
            "stopwatch": ("static void ticks_to_string(",),
            "metronome": ("static void metronome_draw(", "static void draw_display(",
                          "static void timer_callback(", "static void play_ticktock("),
        }.items():
            for signature in signatures:
                start = self.sources[name].rfind(signature)
                function = extract_function(self.sources[name][start:], signature)
                self.assertNotIn("talk_", function)
                self.assertNotIn("speech_flush", function)

    def test_only_existing_plugin_api_speech_entries_are_used(self):
        for source in self.sources.values():
            speech_calls = set(re.findall(r"rb->(talk_\w+)\(", source))
            self.assertTrue(speech_calls <= {
                "talk_id", "talk_number", "talk_spell", "talk_value_decimal"})
            self.assertNotIn("rb->tts_", source)
            self.assertNotIn("rb->global_settings->talk_menu =", source)


if __name__ == "__main__":
    unittest.main()
