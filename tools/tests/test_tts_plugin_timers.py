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
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
EVIDENCE = _project_materials_root(ROOT) / "plugin-timers-tests" / STAMP
PLUGINS = ("countdown_timer", "alarmclock", "chessclock")

PREFIX = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <setjmp.h>
#define HZ 100
#define LCD_WIDTH 128
#define LCD_HEIGHT 64
#define ARRAYLEN(values) (sizeof(values) / sizeof((values)[0]))
#define MAX(first, second) ((first) > (second) ? (first) : (second))
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define SANSA_CLIP_PAD 37
#define IPOD_1G2G_PAD 38
#define SHANLING_Q1_PAD 39
#ifdef TEST_IPOD
#define CONFIG_KEYPAD IPOD_1G2G_PAD
#elif defined(TEST_TOUCH)
#define CONFIG_KEYPAD SHANLING_Q1_PAD
#define HAVE_TOUCHSCREEN
#else
#define CONFIG_KEYPAD SANSA_CLIP_PAD
#endif
#define FOR_NB_SCREENS(screen_index) for (int screen_index = 0; screen_index < NB_SCREENS; ++screen_index)
#define BUTTON_NONE 0
#define BUTTON_UP 1
#define BUTTON_DOWN 2
#define BUTTON_LEFT 4
#define BUTTON_RIGHT 8
#define BUTTON_SELECT 16
#define BUTTON_POWER 32
#define BUTTON_CENTER 64
#define BUTTON_TOPLEFT 128
#define BUTTON_TOPRIGHT 256
#define BUTTON_TOPMIDDLE 512
#define BUTTON_BOTTOMMIDDLE 1024
#define BUTTON_REPEAT 4096
#define SYS_USB_CONNECTED 8192
#define MENU_ATTACHED_USB (-10)
#define DRMODE_SOLID 0
#define DRMODE_INVERSEVID 1
#define AUDIO_STATUS_PLAY 1
#define AUDIO_STATUS_PAUSE 2
#define ID2P(identifier) ((const char *)(intptr_t)(-(identifier) - 1))
#define str(identifier) language_strings[identifier]
#define UNIT_TIME 1
enum plugin_status { PLUGIN_OK, PLUGIN_ERROR, PLUGIN_USB_CONNECTED, PLUGIN_GOTO_WPS };
enum {
    PLA_UP = 100, PLA_DOWN, PLA_LEFT, PLA_RIGHT, PLA_UP_REPEAT, PLA_DOWN_REPEAT,
    PLA_LEFT_REPEAT, PLA_RIGHT_REPEAT, PLA_CANCEL, PLA_EXIT, PLA_SELECT,
    PLA_SELECT_REPEAT, PLA_SELECT_REL, PLA_SCROLL_FWD, PLA_SCROLL_FWD_REPEAT,
    PLA_SCROLL_BACK, PLA_SCROLL_BACK_REPEAT
};
struct button_mapping { int unused; };
const struct button_mapping pla_main_ctx[] = {{0}};
struct user_settings { bool talk_menu, tts_enabled; };
struct user_status { int resume_index; int resume_crc32; int resume_elapsed; int resume_offset; };
struct screen {
    int lcdwidth, lcdheight;
    int (*getstringsize)(const unsigned char *, int *, int *);
    void (*putsxy)(int, int, const unsigned char *);
    bool (*puts_scroll)(int, int, const unsigned char *);
    void (*clear_display)(void);
    void (*update)(void);
};
struct menu_item_ex { const char *title; const char *items[5]; };
#define MENUITEM_STRINGLIST(name, title, callback, ...) \
    static const struct menu_item_ex name = { title, { __VA_ARGS__ } }
struct plugin_api {
    struct user_settings *global_settings;
    struct user_status *global_status;
    volatile long *current_tick;
    struct screen *screens[NB_SCREENS];
    unsigned char **language_strings;
    int (*talk_id)(int32_t, bool);
    int (*talk_number)(long, bool);
    int (*talk_value_decimal)(long, int, int, bool);
    void (*talk_time)(const struct tm *, bool);
    void (*talk_shutup)(void);
    int (*snprintf)(char *, size_t, const char *, ...);
    size_t (*strlen)(const char *);
    char *(*strcpy)(char *, const char *);
    void (*lcd_clear_display)(void);
    int (*lcd_getstringsize)(const unsigned char *, int *, int *);
    void (*lcd_putsxy)(int, int, const unsigned char *);
    void (*lcd_puts)(int, int, const unsigned char *);
    bool (*lcd_puts_scroll)(int, int, const unsigned char *);
    void (*lcd_update)(void);
    void (*lcd_mono_bitmap)(const unsigned char *, int, int, int, int);
    void (*lcd_set_drawmode)(int);
    void (*lcd_fillrect)(int, int, int, int);
    void (*lcd_scroll_stop)(void);
    void (*splash)(int, const char *);
    unsigned (*sleep)(unsigned);
    int (*audio_status)(void);
    void (*audio_pause)(void);
    void (*audio_resume)(void);
    void (*beep_play)(unsigned, unsigned, unsigned);
    void (*backlight_on)(void);
    struct tm *(*get_time)(void);
    int (*playlist_resume)(void);
    void (*playlist_resume_track)(int, int, int, int);
    long (*default_event_handler)(long);
    int (*button_get)(bool);
    int (*do_menu)(const struct menu_item_ex *, int *, void *, bool);
};
struct speech_event { int type; long value; int unit; bool enqueue; };
static struct speech_event speech[4096];
static int speech_count, speech_failure, shutups, beeps, pauses, resumes;
static int scroll_stops, playlist_result, menu_result, menu_calls;
static long ticks_now, menu_delay;
static int music_status;
static struct tm clock_now;
static struct user_settings user_settings = { .talk_menu = true };
static struct user_status user_status = { .resume_index = -1 };
static jmp_buf exit_environment;
static void (*cleanup_handler)(void);
struct action_step { int action; long ticks; int clock_seconds; };
static struct action_step actions[256];
static int action_count, action_index;

static int record_speech(int type, long value, int unit, bool enqueue)
{
    assert(talk_menus_enabled(&user_settings));
    assert(speech_count < (int)ARRAYLEN(speech));
    speech[speech_count++] = (struct speech_event){type, value, unit, enqueue};
    return speech_failure ? -1 : 0;
}
static int speak_id(int32_t identifier, bool enqueue)
{
    return record_speech(1, identifier, 0, enqueue);
}
static int speak_number(long number, bool enqueue)
{
    return record_speech(2, number, 0, enqueue);
}
static int speak_value(long value, int unit, int decimals, bool enqueue)
{
    assert(decimals == 0);
    return record_speech(3, value, unit, enqueue);
}
static void speak_time(const struct tm *value, bool enqueue)
{
    record_speech(4, value->tm_hour * 60 + value->tm_min, 0, enqueue);
}
static void stop_speech(void) { assert(talk_menus_enabled(&user_settings)); ++shutups; }
static void empty_display(void) {}
static void display_text(int left, int top, const unsigned char *text)
{
    (void)left; (void)top; assert(text);
}
static bool scroll_text(int left, int top, const unsigned char *text)
{
    display_text(left, top, text); return true;
}
static int measure_text(const unsigned char *text, int *width, int *height)
{
    *width = strlen((const char *)text) * 6; *height = 8; return *width;
}
static void display_bitmap(const unsigned char *bitmap, int left, int top, int width, int height)
{
    (void)bitmap; (void)left; (void)top; (void)width; (void)height;
}
static void display_mode(int mode) { (void)mode; }
static void display_rectangle(int left, int top, int width, int height)
{
    (void)left; (void)top; (void)width; (void)height;
}
static void stop_scroll(void) { ++scroll_stops; }
static unsigned mock_sleep(unsigned duration) { ticks_now += duration; return 0; }
static int audio_status(void) { return music_status; }
static void pause_audio_mock(void) { ++pauses; music_status |= AUDIO_STATUS_PAUSE; }
static void resume_audio_mock(void) { ++resumes; music_status &= ~AUDIO_STATUS_PAUSE; }
static void beep(unsigned frequency, unsigned duration, unsigned amplitude)
{
    (void)frequency; (void)duration; (void)amplitude; ++beeps;
}
static struct tm *get_clock(void) { return &clock_now; }
static int resume_playlist(void) { return playlist_result; }
static void resume_track(int track, int crc, int elapsed, int offset)
{
    (void)track; (void)crc; (void)elapsed; (void)offset; ++resumes;
}
static long default_event(long action)
{
    return action == SYS_USB_CONNECTED ? SYS_USB_CONNECTED : 0;
}
static void add_action(int action, long duration, int seconds)
{
    assert(action_count < (int)ARRAYLEN(actions));
    actions[action_count++] = (struct action_step){action, duration, seconds};
}
static int next_action(void)
{
    assert(action_index < action_count);
    struct action_step step = actions[action_index++];
    ticks_now += step.ticks;
    if (step.clock_seconds >= 0) {
        clock_now.tm_hour = step.clock_seconds / 3600;
        clock_now.tm_min = step.clock_seconds / 60 % 60;
        clock_now.tm_sec = step.clock_seconds % 60;
    }
    return step.action;
}
static int button_get(bool block) { (void)block; return next_action(); }
static int pluginlib_getaction(int timeout, const struct button_mapping **contexts, int count)
{
    (void)timeout; (void)contexts; assert(count == 1); return next_action();
}
static int fake_atexit(void (*handler)(void)) { cleanup_handler = handler; return 0; }
#define atexit fake_atexit
static void exit_on_usb(int button)
{
    if (button == SYS_USB_CONNECTED)
        longjmp(exit_environment, PLUGIN_USB_CONNECTED + 1);
}
static void playback_control(void *parameter) { (void)parameter; }
static int show_menu(const struct menu_item_ex *menu, int *selection, void *view, bool hide)
{
    (void)selection; (void)view; (void)hide;
    assert((intptr_t)menu->title < 0);
    for (int item = 0; item < 5; ++item)
        assert((intptr_t)menu->items[item] < 0);
    ++menu_calls; ticks_now += menu_delay; return menu_result;
}
static void splash(int duration, const char *text)
{
    assert((intptr_t)text < 0);
    if (talk_menus_enabled(&user_settings))
        speak_id(-(intptr_t)text - 1, false);
    mock_sleep(duration);
}
static struct screen display = {
    LCD_WIDTH, LCD_HEIGHT, measure_text, display_text, scroll_text,
    empty_display, empty_display
};
static struct plugin_api api = {
    .global_settings = &user_settings, .global_status = &user_status,
    .current_tick = &ticks_now, .language_strings = labels,
    .talk_id = speak_id, .talk_number = speak_number,
    .talk_value_decimal = speak_value, .talk_time = speak_time,
    .talk_shutup = stop_speech, .snprintf = snprintf,
    .strlen = strlen, .strcpy = strcpy, .lcd_clear_display = empty_display,
    .lcd_getstringsize = measure_text, .lcd_putsxy = display_text,
    .lcd_puts = display_text, .lcd_puts_scroll = scroll_text,
    .lcd_update = empty_display, .lcd_mono_bitmap = display_bitmap,
    .lcd_set_drawmode = display_mode, .lcd_fillrect = display_rectangle,
    .lcd_scroll_stop = stop_scroll, .splash = splash, .sleep = mock_sleep,
    .audio_status = audio_status, .audio_pause = pause_audio_mock,
    .audio_resume = resume_audio_mock, .beep_play = beep,
    .backlight_on = empty_display, .get_time = get_clock,
    .playlist_resume = resume_playlist, .playlist_resume_track = resume_track,
    .default_event_handler = default_event, .button_get = button_get,
    .do_menu = show_menu
};
static struct plugin_api *rb = &api;
static void reset_harness(bool enabled)
{
    user_settings.talk_menu = enabled;
    speech_count = speech_failure = shutups = beeps = pauses = resumes = 0;
    action_count = action_index = menu_calls = scroll_stops = 0;
    menu_result = -1; menu_delay = ticks_now = 0;
    music_status = AUDIO_STATUS_PLAY; cleanup_handler = NULL;
    user_status.resume_index = -1; playlist_result = -1;
    memset(&clock_now, 0, sizeof(clock_now));
    for (int screen_index = 0; screen_index < NB_SCREENS; ++screen_index)
        api.screens[screen_index] = &display;
}
static int label_count(int label)
{
    int count = 0;
    for (int event = 0; event < speech_count; ++event)
        count += speech[event].type == 1 && speech[event].value == label;
    return count;
}
static int run_plugin(void);
"""

RUNNER = r"""
static int run_plugin(void)
{
    int result = setjmp(exit_environment);
    if (result == 0)
        result = plugin_start(NULL) + 1;
    if (cleanup_handler)
        cleanup_handler();
    assert(action_index == action_count);
    return result - 1;
}
"""

COUNTDOWN = r"""
static void expiry_script(void)
{
    for (int count = 0; count < 10; ++count)
        add_action(PLA_DOWN, 0, -1);
    add_action(PLA_RIGHT, 0, -1);
    add_action(PLA_UP, 0, -1);
    add_action(PLA_SELECT, 0, -1);
    add_action(BUTTON_NONE, HZ + 1, -1);
    for (int count = 0; count < 8; ++count)
        add_action(BUTTON_NONE, HZ, -1);
    add_action(PLA_SELECT, 0, -1);
    add_action(PLA_SELECT, 0, -1);
    add_action(PLA_CANCEL, 0, -1);
}
int main(void)
{
    const int music_states[] = {0, AUDIO_STATUS_PLAY,
                               AUDIO_STATUS_PLAY | AUDIO_STATUS_PAUSE};
    for (size_t state_index = 0; state_index < ARRAYLEN(music_states); ++state_index) {
        int status = music_states[state_index];
        reset_harness(true);
        music_status = status;
        expiry_script();
        assert(run_plugin() == PLUGIN_OK);
        assert(label_count(LANG_COUNTDOWN_TIMER_SET) == 1);
        assert(label_count(LANG_COUNTDOWN_TIMER_RUNNING) == 1);
        assert(label_count(LANG_COUNTDOWN_TIMER_PAUSED) == 1);
        assert(label_count(LANG_COUNTDOWN_TIMER_OVERTIME) == 1);
        assert(label_count(LANG_COUNTDOWN_TIMER_FINISHED) == 1);
        assert(beeps == 3 && shutups == 1);
        assert(pauses == (status == AUDIO_STATUS_PLAY));
        assert(resumes == pauses && music_status == status);
    }
    reset_harness(false); expiry_script();
    assert(run_plugin() == PLUGIN_OK && speech_count == 0 && shutups == 0);
    reset_harness(true); add_action(SYS_USB_CONNECTED, 0, -1);
    assert(run_plugin() == PLUGIN_USB_CONNECTED && shutups == 1);
    reset_harness(true); add_action(PLA_CANCEL, 0, -1);
    assert(run_plugin() == PLUGIN_OK && beeps == 0);
    timer_ctx_t value = { .state = STATE_SETUP, .set_minutes = 99,
                          .set_seconds = 59, .current_field = 1 };
    reset_harness(true); countdown_talk_state(&value);
    assert(speech[1].type == 3 && speech[1].value == 5999);
    assert(speech[2].value == VOICE_SECONDS && speech[3].value == 59);
    value.state = STATE_PAUSED; value.remaining_ticks = -1;
    countdown_talk_state(&value);
    assert(speech[speech_count - 1].value == 1);
    reset_harness(true); speech_failure = 1; countdown_talk_state(&value);
    assert(speech_count == 1);
    puts("countdown: focus, duration, states, one expiry, idle silence, music state, cancel, USB, speech off: PASS");
    return 0;
}
"""

ALARM = r"""
static void reset_alarm(bool enabled)
{
    reset_harness(enabled);
    current = 0; tomorrow = quit = usb = waiting = done = false;
    alarms[0] = 7; alarms[1] = 0; prev_tick = 86400;
    clock_now.tm_hour = 6; clock_now.tm_min = 59; clock_now.tm_sec = 55;
}
int main(void)
{
#ifdef TEST_IPOD
    reset_alarm(true); add_action(PLA_UP, 0, 7 * 3600);
    assert(run_plugin() == PLUGIN_OK && resumes == 0);
    assert(label_count(LANG_ALARMCLOCK_WAKEUP) == 0 && shutups == 1);
#else
    for (int enabled = 0; enabled < 2; ++enabled) {
        reset_alarm(enabled);
        add_action(PLA_RIGHT, 0, -1); add_action(PLA_UP, 0, -1);
        add_action(PLA_DOWN, 0, -1); add_action(PLA_LEFT, 0, -1);
        add_action(PLA_SELECT, 0, -1);
        for (int count = 0; count < 20; ++count)
            add_action(BUTTON_NONE, HZ, -1);
        add_action(BUTTON_NONE, 0, 7 * 3600);
        assert(run_plugin() == PLUGIN_GOTO_WPS && resumes == 1);
        assert(label_count(LANG_ALARMCLOCK) == enabled);
        assert(label_count(LANG_ALARMCLOCK_ARMED) == enabled);
        assert(label_count(LANG_ALARMCLOCK_WAKEUP) == enabled);
        assert(label_count(VOICE_MINUTES) == enabled * 3);
        assert(label_count(VOICE_HOURS) == enabled * 2);
        assert(shutups == 0);
    }
    reset_alarm(true); add_action(PLA_SELECT, 0, -1);
    add_action(PLA_CANCEL, 0, 7 * 3600);
    assert(run_plugin() == PLUGIN_OK && resumes == 0 && shutups == 1);
    reset_alarm(true); add_action(PLA_SELECT, 0, -1);
    add_action(SYS_USB_CONNECTED, 0, 7 * 3600);
    assert(run_plugin() == PLUGIN_USB_CONNECTED && resumes == 0 && shutups == 1);
    reset_alarm(false); add_action(PLA_SELECT, 0, -1);
    add_action(SYS_USB_CONNECTED, 0, -1);
    assert(run_plugin() == PLUGIN_USB_CONNECTED && speech_count == 0 && shutups == 0);
    reset_alarm(true); add_action(PLA_SELECT, 0, -1);
    add_action(BUTTON_NONE, 0, 0);
    add_action(BUTTON_NONE, 0, 7 * 3600);
    assert(run_plugin() == PLUGIN_GOTO_WPS && resumes == 1);
    reset_alarm(true); clock_now.tm_hour = 8;
    clock_now.tm_min = clock_now.tm_sec = 0;
    add_action(PLA_SELECT, 0, -1);
    add_action(BUTTON_NONE, 0, 8 * 3600);
    add_action(BUTTON_NONE, 0, 0);
    add_action(BUTTON_NONE, 0, 7 * 3600);
    assert(run_plugin() == PLUGIN_GOTO_WPS && resumes == 1 && !tomorrow);
    reset_alarm(true); music_status = 0;
    assert(run_plugin() == PLUGIN_ERROR && label_count(LANG_NOTHING_TO_RESUME) == 1);
    reset_alarm(false); music_status = 0;
    assert(run_plugin() == PLUGIN_ERROR && speech_count == 0);
    reset_alarm(true); music_status = 0;
    user_status.resume_index = 42; playlist_result = 0;
    add_action(PLA_SELECT, 0, -1); add_action(BUTTON_NONE, 0, 7 * 3600);
    assert(run_plugin() == PLUGIN_GOTO_WPS && resumes == 1 && pauses == 0);
    reset_alarm(true); speech_failure = 1; alarm_talk_time(false);
    assert(speech_count == 1);
#endif
    puts("alarm: fields, edit, armed, idle silence, wakeup, midnight, deadline cancellation, USB, speech off: PASS");
    return 0;
}
"""

CHESS = r"""
static void prepare_chess(bool enabled)
{
    reset_harness(enabled);
    memset(timer_holder, 0, sizeof(timer_holder));
    settings.nr_timers = 2; settings.total_time = 5; settings.round_time = 2;
    timer_holder[0].total_time = timer_holder[1].total_time = 5;
    chesspause = true;
}
int main(void)
{
    for (int enabled = 0; enabled < 2; ++enabled) {
        prepare_chess(enabled);
        for (int count = 0; count < 12; ++count)
            add_action(BUTTON_NONE, 0, -1);
        add_action(CHC_STARTSTOP, 0, -1);
        add_action(BUTTON_NONE, 2 * HZ, -1);
        for (int count = 0; count < 12; ++count)
            add_action(BUTTON_NONE, 0, -1);
        add_action(CHC_RESET, 0, -1);
        add_action(CHC_STARTSTOP, 0, -1);
        add_action(CHC_SETTINGS_INC, 0, -1);
        assert(run_timer(1) == CHCL_NEXT && action_index == action_count);
        assert(label_count(LANG_CHESSCLOCK_PLAYER) == enabled * 5);
        assert(label_count(LANG_CHESSCLOCK_ROUND_FINISHED) == enabled);
        assert(label_count(LANG_COUNTDOWN_TIMER_PAUSED) == enabled * 2);
        assert(label_count(LANG_COUNTDOWN_TIMER_RUNNING) == enabled * 2);
        assert(timer_holder[1].used_time >= 0 && timer_holder[1].used_time < HZ);
        if (!enabled) assert(speech_count == 0);
    }
    prepare_chess(true);
    int value = 2;
    add_action(BUTTON_NONE, 0, -1); add_action(CHC_SETTINGS_INC, 0, -1);
    add_action(CHC_SETTINGS_DEC, 0, -1); add_action(CHC_SETTINGS_OK, 0, -1);
    assert(chessclock_set_int(LANG_NUMBER_OF_PLAYERS, &value, 1, 1, 2, 0) == CHCL_OK);
    assert(value == 1 && label_count(LANG_NUMBER_OF_PLAYERS) == 2 && scroll_stops == 1);
    prepare_chess(true); add_action(CHC_SETTINGS_CANCEL, 0, -1);
    assert(chessclock_set_int(LANG_CHESSCLOCK_TOTAL_TIME, &value, 1, 0, 10,
                              FLAGS_SET_INT_SECONDS) == CHCL_CANCEL);
    assert(scroll_stops == 1 && shutups == 1);
    prepare_chess(true); add_action(SYS_USB_CONNECTED, 0, -1);
    assert(chessclock_set_int(LANG_CHESSCLOCK_TOTAL_TIME, &value, 1, 0, 10,
                              FLAGS_SET_INT_SECONDS) == CHCL_USB);
    assert(scroll_stops == 1 && shutups == 1);
    prepare_chess(true); chesspause = false; menu_delay = 10 * HZ;
    add_action(CHC_MENU, 0, -1); add_action(CHC_SETTINGS_INC, 0, -1);
    assert(run_timer(0) == CHCL_NEXT && timer_holder[0].used_time < HZ);
    assert(menu_calls == 1);
    prepare_chess(true); menu_result = MENU_ATTACHED_USB;
    add_action(CHC_MENU, 0, -1);
    assert(run_timer(0) == CHCL_USB && shutups == 1);
    prepare_chess(true); menu_result = 3;
    add_action(CHC_MENU, 0, -1);
    add_action(CHC_SETTINGS_DEC, 0, -1);
    add_action(CHC_SETTINGS_OK, 0, -1);
    add_action(CHC_SETTINGS_INC, 0, -1);
    assert(run_timer(0) == CHCL_NEXT && timer_holder[0].total_time == 0);
    assert(label_count(LANG_TIMEOUT) == 1 && timer_holder[0].used_time == 0);
    prepare_chess(false); add_action(SYS_USB_CONNECTED, 0, -1);
    assert(run_timer(0) == CHCL_USB && speech_count == 0 && shutups == 0);
    prepare_chess(true); timer_holder[0].used_time = 100 * HZ;
    add_action(CHC_SETTINGS_INC, 0, -1);
    assert(run_timer(0) == CHCL_NEXT && timer_holder[0].used_time == 100 * HZ);
    assert(label_count(LANG_TIMEOUT) == 1);
    prepare_chess(true); speech_failure = 1;
    chessclock_talk_timer(0, HZ, 0, false); assert(speech_count == 1);
    assert(strcmp(show_time(7200), "120:00") == 0);
    prepare_chess(true);
    add_action(CHC_SETTINGS_OK, 0, -1); add_action(CHC_SETTINGS_OK, 0, -1);
    add_action(CHC_SETTINGS_OK, 0, -1); add_action(CHC_QUIT, 0, -1);
    assert(run_plugin() == PLUGIN_OK && shutups == 1);
    puts("chess clock: setup bounds, localized menu IDs, player/turn/time/state, one expiry, menu timing, cancel, USB, speech off: PASS");
    return 0;
}
"""


class TimerSpeechTests(unittest.TestCase):
    def run_harness(self, plugin, mode, defines):
        source = (ROOT / f"apps/plugins/{plugin}.c").read_text(encoding="utf-8")
        identifiers = sorted(set(re.findall(r"\b(?:LANG|VOICE)_[A-Z0-9_]+\b", source)))
        labels = "enum { " + ", ".join(identifiers) + ", LANGUAGE_COUNT };\n"
        labels += "static unsigned char *labels[LANGUAGE_COUNT] = {\n"
        labels += "\n".join(f'[{identifier}] = (unsigned char *)"{identifier}",'
                            for identifier in identifiers)
        labels += "};\n"
        extracted = re.sub(r'^#include "[^"]+"\s*$', "", source, flags=re.MULTILINE)
        output = EVIDENCE / f"{plugin}-{mode}"
        output.mkdir(parents=True)
        harness = output / "timers.c"
        prefix = with_menu_policy(PREFIX)
        split = prefix.index("struct plugin_api {")
        harness.write_text(prefix[:split] + labels + prefix[split:] + extracted + RUNNER +
                           {"countdown_timer": COUNTDOWN, "alarmclock": ALARM,
                            "chessclock": CHESS}[plugin], encoding="utf-8")
        executable = output / "timers-test"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-pointer-sign", "-fsanitize=address,undefined",
            "-fno-sanitize-recover=all", "-fno-pie", "-no-pie", str(harness),
            "-o", str(executable)] + ["-D" + define for define in defines]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / "compile.log").write_text(shlex.join(command) + "\n" + compiled.stdout +
                                             compiled.stderr, encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        tested = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0"))
        (output / "report.json").write_text(json.dumps({
            "source_sha256": hashlib.sha256(
                (ROOT / f"apps/plugins/{plugin}.c").read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "defines": defines, "command": command, "returncode": tested.returncode,
            "stdout": tested.stdout, "stderr": tested.stderr,
        }, indent=2), encoding="utf-8")
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_espeak_complete_plugin_control_flows_with_sanitizers(self):
        for plugin in PLUGINS:
            with self.subTest(plugin=plugin):
                self.run_harness(plugin, "espeak", ["HAVE_ESPEAK", "HAVE_BACKLIGHT",
                                                    "HAVE_SCROLLWHEEL", "NB_SCREENS=2"])

    def test_legacy_complete_plugin_control_flows_with_sanitizers(self):
        for plugin in PLUGINS:
            with self.subTest(plugin=plugin):
                self.run_harness(plugin, "legacy", ["NB_SCREENS=1"])

    def test_ipod_alarm_cancellation_with_sanitizers(self):
        self.run_harness("alarmclock", "ipod", ["TEST_IPOD", "NB_SCREENS=1"])

    def test_touch_chessclock_keymap_with_sanitizers(self):
        self.run_harness("chessclock", "touch", ["TEST_TOUCH", "NB_SCREENS=1"])

    def test_no_private_speech_engine_or_redraw_announcements(self):
        for plugin in PLUGINS:
            source = (ROOT / f"apps/plugins/{plugin}.c").read_text(encoding="utf-8")
            self.assertNotIn("tts_", source)
            self.assertNotIn("rb_espeak", source)
            self.assertIn("talk_menus_enabled(rb->global_settings)", source)
            self.assertNotRegex(source, r"HAVE_ESPEAK|PLUGIN_API_VERSION")
        alarm = (ROOT / "apps/plugins/alarmclock.c").read_text(encoding="utf-8")
        self.assertNotIn("rb->splash(0, string)", alarm)

    def test_timer_labels_have_complete_english_and_polish_entries(self):
        identifiers = set()
        for plugin in PLUGINS:
            source = (ROOT / f"apps/plugins/{plugin}.c").read_text(encoding="utf-8")
            identifiers.update(re.findall(r"\bLANG_(?:ALARMCLOCK|CHESSCLOCK)[A-Z_]*\b",
                                          source))
        for language, sections in (("english", ("source", "dest", "voice")),
                                   ("polski", ("dest", "voice"))):
            catalog = (ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8")
            for identifier in sorted(identifiers):
                with self.subTest(language=language, label=identifier):
                    phrase = re.search(r"<phrase>\s*id: " + re.escape(identifier) +
                                       r"\s.*?</phrase>", catalog, re.DOTALL)
                    self.assertIsNotNone(phrase)
                    for section in sections:
                        content = re.search(f"<{section}>(.*?)</{section}>",
                                            phrase.group(), re.DOTALL)
                        self.assertIsNotNone(content)
                        self.assertRegex(content.group(1), r'(?m)^\s*\*:\s*"[^"\n]+"\s*$')


if __name__ == "__main__":
    unittest.main()
