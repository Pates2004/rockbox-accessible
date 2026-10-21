#include <stdbool.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "CHECK_FAILED %d: %s\n", __LINE__, #condition); exit(101); } } while (0)
#define HZ 100
#define TIME_BEFORE(first, second) ((long)((unsigned long)(first) - (unsigned long)(second)) < 0)
#define TIMEOUT_NOBLOCK 0
#define CONTEXT_STD 0
#define BUTTON_NONE 0
#define BUTTON_UP 1
#define BUTTON_DOWN 2
#define BUTTON_SELECT 4
#define BUTTON_POWER 8
#define BUTTON_REL 0x02000000
#define BUTTON_REPEAT 0x04000000
#define BUTTON_MULTIMEDIA 0x10000000
#define SYS_EVENT 0x80000000u
#define SYS_USB_CONNECTED ((int)(SYS_EVENT | 1u))
#define SYS_POWEROFF ((int)(SYS_EVENT | 2u))
#define SYS_REBOOT ((int)(SYS_EVENT | 3u))
#define SYS_FS_CHANGED ((int)(SYS_EVENT | 4u))
#define SYS_BATTERY_UPDATE ((int)(SYS_EVENT | 5u))
#define IS_SYSEVENT(event) (((unsigned int)(event) & SYS_EVENT) != 0)
#define MAX_PRESETS 64
#define FREQ_DISP_DIVISOR 10000
#define UNIT_INT 0
#define FOR_NB_SCREENS(index) for (int index = 0; index < 1; index++)
#define ID2P(identifier) str(identifier)
#define MENU_ATTACHED_USB -10
#define LANG_FM_FIRST_AUTOSCAN LANG_FM_CLEAR_PRESETS
#define SKIN_REFRESH_ALL 1

enum {
    ACTION_NONE, ACTION_UNKNOWN, ACTION_REDRAW, ACTION_STD_OK, ACTION_STD_CANCEL,
    ACTION_STD_PREV, ACTION_STD_NEXT, ACTION_STD_PREVREPEAT, ACTION_STD_NEXTREPEAT,
    ACTION_STD_CONTEXT, ACTION_STD_MENU, ACTION_FM_MENU
};
enum {
    LANG_FM_CLEAR_PRESETS, LANG_FM_SCANNING, LANG_FM_SCAN_COMPLETE,
    LANG_FM_RDS_INFO, LANG_FM_RDS_NAME, LANG_FM_RDS_TEXT, LANG_FM_RDS_NO_DATA
};
enum { FMRADIO_OFF, FMRADIO_PLAYING, FMRADIO_PAUSED };
enum { RADIO_MUTE, RADIO_SCAN_FREQUENCY, RADIO_RDS_NAME, RADIO_RDS_TEXT };
enum { AUDIO_SRC_FMRADIO, SRCF_FMRADIO_PLAYING, RADIO_PRESET_MODE };

struct user_settings {
    bool tts_enabled;
    bool tts_announce_dynamic;
    bool talk_menu;
    int fm_region;
};
static struct user_settings global_settings;
ACTUAL_POLICY_SOURCE

struct viewport { int unused; };
struct fmstation { int frequency; char name[28]; };
struct fmstation_buf { struct fmstation fmstation[MAX_PRESETS]; };
struct fm_region_data { int freq_min, freq_max, freq_step; };
static struct fm_region_data fm_region_data[1];
static struct fmstation_buf preset_data;
static int num_presets;
static bool presets_loaded, presets_changed;
static long current_tick;
static int current_frequency, radio_status, radio_mode;
static int scanned, next_calls, mute_calls, unmute_calls, unpins, yields;
static int speak_calls, complete_calls, stop_calls;
static int spoken[256], status_reads, event_calls, poll_count;
static int last_button, busy_steps;
static bool no_stations, allocation_fails, confirm_scan, hardware_present;
#ifdef HAVE_ESPEAK
static bool all_busy;
#endif
static int physical_reads;
static int automatic_speech_calls, spoken_ids[128], id_calls;
static bool force_enqueue_next, need_shutup;
static int fixture_language;
static int utterance_queue[256], utterance_count;

typedef int list_speak_item(int, void *);
struct gui_synclist {
    void *data;
    int selected_item;
    int nb_items;
    bool talk_menu;
    bool boundary_speech_pending;
    long scheduled_talk_tick, last_talked_tick;
    list_speak_item *callback_speak_item;
    const char *(*callback_get_item_name)(int, void *, char *, size_t);
};

struct input_event { int action, button; };
static struct input_event input[128];

static const char *str(int identifier)
{
    static const char *labels[2][7] = ACTUAL_RADIO_LABELS;
    CHECK(identifier >= 0 && identifier < 7);
    return labels[fixture_language][identifier];
}

static void set_viewport(struct viewport *viewport) { (void)viewport; }
static void clear_viewport(void) {}
static void update_viewport(void) {}
static struct {
    void (*set_viewport)(struct viewport *);
    void (*clear_viewport)(void);
    void (*update_viewport)(void);
} screens[] = { { set_viewport, clear_viewport, update_viewport } };

static struct fmstation_buf *presets_get(void) { return allocation_fails ? NULL : &preset_data; }
static void presets_put(struct fmstation_buf *presets) { CHECK(presets == &preset_data); unpins++; }
static bool yesno_pop(const char *text) { (void)text; return confirm_scan; }
static int radio_get_current_frequency(void) { return current_frequency; }
static int radio_preset_count(void) { return num_presets; }
static void radio_set_current_frequency(int frequency) { current_frequency = frequency; }
static int get_radio_status(void) { return radio_status; }
static void radio_set_mode(int mode) { radio_mode = mode; }
static void next_station(int direction) { CHECK(direction == 0); next_calls++; }
static void audio_stop(void) {}
static bool pcm_is_initialized(void) { return true; }
static void sleep(int ticks) { (void)ticks; }
static void audio_set_input_source(int source, int flags)
{
    CHECK(source == AUDIO_SRC_FMRADIO && flags == SRCF_FMRADIO_PLAYING);
    radio_status = FMRADIO_PLAYING;
}
static void yield(void) { yields++; }
static void splashf_silent(int ticks, const char *format, int frequency, int fraction)
{
    CHECK(ticks == 0 && format == str(LANG_FM_SCANNING));
    CHECK(frequency > 0 && fraction >= 0 && fraction < 100);
}
void splashf(int ticks, const char *format, int frequency, int fraction)
{
    automatic_speech_calls++;
    splashf_silent(ticks, format, frequency, fraction);
}
static int tuner_set(int operation, int value)
{
    if (operation == RADIO_SCAN_FREQUENCY)
    {
        CHECK(value == fm_region_data[0].freq_min + scanned * fm_region_data[0].freq_step);
        CHECK(scanned < 128);
        scanned++;
        current_tick += HZ;
        return !no_stations;
    }
    CHECK(operation == RADIO_MUTE);
    if (value) mute_calls++;
    else unmute_calls++;
    return 1;
}
static int get_custom_action(int context, int timeout, void *mapping)
{
    CHECK(context == CONTEXT_STD && timeout == TIMEOUT_NOBLOCK && mapping == NULL);
    CHECK(poll_count < 128);
    struct input_event event = input[poll_count++];
    if (event.button != BUTTON_NONE)
        last_button = event.button;
    return event.action;
}
static int get_action_statuscode(int *button)
{
    status_reads++;
    *button = last_button;
    return 0;
}
static long default_event_handler(long event) { event_calls++; return event; }
static void talk_force_shutup(void)
{
    stop_calls++;
    busy_steps = 0;
    utterance_count = 0;
    need_shutup = false;
}
ACTUAL_ENQUEUE_SOURCE
static int talk_value_decimal(int frequency, int unit, int decimals, bool enqueue)
{
    CHECK(unit == UNIT_INT && decimals == 6 && !enqueue && !force_enqueue_next);
    do_enqueue(enqueue);
    force_enqueue_next = false;
    need_shutup = true;
    CHECK(utterance_count < 256);
    utterance_queue[utterance_count++] = frequency;
    CHECK(speak_calls < 256);
    spoken[speak_calls++] = frequency;
    busy_steps = 3;
    return 0;
}
static int talk_id(int identifier, bool enqueue)
{
    do_enqueue(enqueue);
    force_enqueue_next = false;
    need_shutup = true;
    CHECK(utterance_count < 256);
    utterance_queue[utterance_count++] = identifier;
    CHECK(id_calls < 128);
    spoken_ids[id_calls++] = identifier;
    if (identifier == LANG_FM_SCAN_COMPLETE)
    {
        CHECK(!enqueue);
        complete_calls++;
    }
    return 0;
}
#ifdef HAVE_ESPEAK
static bool tts_is_available(void) { return global_settings.tts_enabled; }
static bool tts_is_busy(void)
{
    if (all_busy) return true;
    if (busy_steps > 0) { busy_steps--; return true; }
    return false;
}
#endif

ACTUAL_SCAN_SOURCE

#ifdef HAVE_ESPEAK
static void gui_synclist_talk_text(struct gui_synclist *lists) { (void)lists; }
static void gui_synclist_talk_position(struct gui_synclist *lists) { (void)lists; }
#endif
ACTUAL_LIST_ROW_SOURCE

enum { FMS_EXIT, FMS_ENTER };
static int radio_settings_menu, fixture_menu_result, fixture_display_calls;
static bool fixture_menu_done, fixture_menu_freeze;
static void fms_fix_displays(int state)
{
    CHECK(state == (fixture_display_calls == 0 ? FMS_EXIT : FMS_ENTER));
    fixture_display_calls++;
}
static int do_menu(int *menu, void *selection, void *parent, bool hide_theme)
{
    CHECK(menu == &radio_settings_menu && selection == NULL && parent == NULL && !hide_theme);
    return fixture_menu_result;
}
static int preset_find(int frequency) { CHECK(frequency == current_frequency); return 123; }
static void preset_set_current(int preset) { CHECK(preset == 123); }
static void fixture_radio_menu(void)
{
    bool done = false, screen_freeze = false;
    int curr_freq = current_frequency;
    int update_type = 0;
    fixture_display_calls = 0;
    switch (ACTION_FM_MENU)
    {
ACTUAL_RADIO_MENU_CASE
    default: CHECK(false);
    }
    CHECK(fixture_display_calls == 2 && update_type == SKIN_REFRESH_ALL);
    fixture_menu_done = done;
    fixture_menu_freeze = screen_freeze;
}
static void fixture_startup_scan(void)
{
ACTUAL_STARTUP_SCAN_SOURCE
}
static int fixture_menu_speak(int selected_item, void *data)
{
    (void)selected_item;
    talk_id(*(int *)data, false);
    return 0;
}

static void reset(void)
{
    memset(&preset_data, 0, sizeof(preset_data));
    memset(input, 0, sizeof(input));
    memset(spoken, 0, sizeof(spoken));
    global_settings = (struct user_settings){ true, true, true, 0 };
    fm_region_data[0] = (struct fm_region_data){ 87500000, 88000000, 100000 };
    num_presets = 0;
    presets_loaded = presets_changed = false;
    current_tick = 1;
    current_frequency = 90000000;
    radio_status = FMRADIO_PLAYING;
    radio_mode = -1;
    scanned = next_calls = mute_calls = unmute_calls = unpins = yields = 0;
    speak_calls = complete_calls = stop_calls = 0;
    status_reads = event_calls = poll_count = last_button = busy_steps = physical_reads = 0;
    no_stations = allocation_fails = false;
#ifdef HAVE_ESPEAK
    all_busy = false;
#endif
    automatic_speech_calls = id_calls = 0;
    force_enqueue_next = need_shutup = true;
    utterance_count = 0;
    confirm_scan = hardware_present = true;
}

static void check_completed(void)
{
    CHECK(scanned == 6 && yields == scanned && num_presets == 6);
    CHECK(presets_changed && presets_loaded);
    CHECK(unpins == 1 && mute_calls == 1 && unmute_calls == 1 && next_calls == 1);
    CHECK(current_frequency == fm_region_data[0].freq_min && radio_mode == RADIO_PRESET_MODE);
    CHECK(complete_calls == 1);
    for (int preset = 0; preset < num_presets; preset++)
        CHECK(preset_data.fmstation[preset].frequency == fm_region_data[0].freq_min + preset * 100000);
}

static void scan_scenario(const char *scenario)
{
    reset();
    if (!strcmp(scenario, "menu-normal") || !strcmp(scenario, "menu-usb"))
    {
        fixture_menu_result = !strcmp(scenario, "menu-usb") ? MENU_ATTACHED_USB : 0;
        fixture_radio_menu();
        CHECK(fixture_menu_done == (fixture_menu_result == MENU_ATTACHED_USB));
        CHECK(fixture_menu_freeze == fixture_menu_done);
        return;
    }
    if (!strcmp(scenario, "completion-menu"))
    {
        input[0] = (struct input_event){ ACTION_STD_OK, BUTTON_SELECT };
        presets_scan(NULL);
        CHECK(complete_calls == 1 && utterance_count == 1 && utterance_queue[0] == LANG_FM_SCAN_COMPLETE);
        int label = LANG_FM_RDS_INFO;
        struct gui_synclist lists = { .data = &label, .nb_items = 1, .talk_menu = true,
                                     .callback_speak_item = fixture_menu_speak };
        _gui_synclist_speak_item(&lists, true);
        CHECK(utterance_count == 2 && utterance_queue[0] == LANG_FM_SCAN_COMPLETE);
        CHECK(utterance_queue[1] == LANG_FM_RDS_INFO && !force_enqueue_next);
        label = LANG_FM_RDS_TEXT;
        _gui_synclist_speak_item(&lists, true);
        CHECK(utterance_count == 1 && utterance_queue[0] == LANG_FM_RDS_TEXT);
        return;
    }
    if (!strcmp(scenario, "completion-startup"))
    {
        fixture_startup_scan();
        CHECK(complete_calls == 1 && utterance_count == 1 && utterance_queue[0] == LANG_FM_SCAN_COMPLETE);
        CHECK(!force_enqueue_next);
        talk_id(LANG_FM_RDS_TEXT, false);
        CHECK(utterance_count == 1 && utterance_queue[0] == LANG_FM_RDS_TEXT);
        return;
    }
    if (!strcmp(scenario, "duplicate-press"))
    {
        struct presets_scan_speech speech = { 0 };
        presets_scan_speech_action(&speech, ACTION_STD_PREV, BUTTON_UP);
        CHECK(speech.paused && stop_calls == 1);
        presets_scan_speech_action(&speech, ACTION_STD_PREV, BUTTON_UP);
        CHECK(speech.paused && stop_calls == 1);
        presets_scan_speech_action(&speech, ACTION_UNKNOWN, BUTTON_UP | BUTTON_REL);
        CHECK(speech.paused && stop_calls == 1);
        presets_scan_speech_action(&speech, ACTION_STD_PREV, BUTTON_UP);
        CHECK(!speech.paused && stop_calls == 1);
        for (int repeat = 0; repeat < 1000; repeat++)
            presets_scan_speech_action(&speech, ACTION_STD_PREVREPEAT, BUTTON_UP | BUTTON_REPEAT);
        CHECK(!speech.paused && stop_calls == 1);
        return;
    }
    if (!strcmp(scenario, "tick-wrap"))
    {
        struct presets_scan_speech speech = { 0 };
        global_settings.tts_enabled = false;
        speech.spoke = true;
        speech.pending_frequency = 90000000;
        speech.talked_tick = LONG_MAX - HZ;
        current_tick = (long)((unsigned long)LONG_MAX + 1);
        presets_scan_speak(&speech);
        CHECK(speak_calls == 0);
        current_tick = (long)((unsigned long)LONG_MAX + HZ * 5);
        presets_scan_speak(&speech);
        CHECK(speak_calls == 1 && speech.pending_frequency == 0);
        return;
    }
    if (!strcmp(scenario, "allocation"))
    {
        allocation_fails = true;
        CHECK(presets_scan(NULL) == 1);
        CHECK(scanned == 0 && complete_calls == 0 && mute_calls == 0);
        return;
    }
    if (!strcmp(scenario, "decline"))
    {
        num_presets = 1;
        confirm_scan = false;
        CHECK(presets_scan(NULL) == 1);
        CHECK(scanned == 0 && num_presets == 1 && complete_calls == 0 && mute_calls == 0);
        return;
    }
    if (!strcmp(scenario, "pause-resume"))
    {
        input[1] = (struct input_event){ ACTION_STD_PREV, BUTTON_UP };
        input[2] = (struct input_event){ ACTION_STD_PREVREPEAT, BUTTON_UP | BUTTON_REPEAT };
        input[3] = (struct input_event){ ACTION_UNKNOWN, BUTTON_UP | BUTTON_REL };
        input[4] = (struct input_event){ ACTION_STD_NEXT, BUTTON_DOWN };
    }
    if (!strcmp(scenario, "release-ok"))
    {
        input[1] = (struct input_event){ ACTION_UNKNOWN, BUTTON_SELECT };
        input[2] = (struct input_event){ ACTION_STD_OK, BUTTON_SELECT | BUTTON_REL };
        input[3] = (struct input_event){ ACTION_STD_PREV, BUTTON_UP };
        input[4] = (struct input_event){ ACTION_UNKNOWN, BUTTON_UP | BUTTON_REL };
        input[5] = (struct input_event){ ACTION_STD_NEXT, BUTTON_DOWN };
    }
    if (!strcmp(scenario, "unknown-toggle"))
    {
        input[1] = (struct input_event){ ACTION_UNKNOWN, BUTTON_SELECT };
        input[2] = (struct input_event){ ACTION_STD_MENU, BUTTON_SELECT | BUTTON_REL };
        input[3] = (struct input_event){ ACTION_UNKNOWN, BUTTON_SELECT };
        input[4] = (struct input_event){ ACTION_STD_MENU, BUTTON_SELECT | BUTTON_REL };
    }
    if (!strcmp(scenario, "unknown-hold"))
    {
        input[1] = (struct input_event){ ACTION_UNKNOWN, BUTTON_SELECT };
        input[2] = (struct input_event){ ACTION_STD_MENU, BUTTON_SELECT | BUTTON_REL };
        input[3] = (struct input_event){ ACTION_UNKNOWN, BUTTON_SELECT };
        input[4] = (struct input_event){ ACTION_STD_CONTEXT, BUTTON_SELECT | BUTTON_REPEAT };
        input[5] = (struct input_event){ ACTION_UNKNOWN, BUTTON_SELECT | BUTTON_REL };
    }
    if (!strcmp(scenario, "enter-mute") || !strcmp(scenario, "reset"))
        input[0] = (struct input_event){ ACTION_STD_OK, BUTTON_SELECT };
    if (!strcmp(scenario, "dynamic-off"))
    {
        global_settings.tts_announce_dynamic = false;
        global_settings.talk_menu = false;
    }
    if (!strcmp(scenario, "voice-fallback"))
    {
        global_settings.tts_enabled = false;
        global_settings.tts_announce_dynamic = false;
    }
    if (!strcmp(scenario, "all-speech-off"))
        global_settings.tts_enabled = global_settings.talk_menu = false;
    if (!strcmp(scenario, "paused-radio")) radio_status = FMRADIO_PAUSED;
    if (!strcmp(scenario, "stopped-radio")) radio_status = FMRADIO_OFF;
    if (!strcmp(scenario, "usb-empty")) no_stations = true;
    int interrupt = ACTION_NONE;
    if (!strcmp(scenario, "cancel")) interrupt = ACTION_STD_CANCEL;
    if (!strcmp(scenario, "cancel-repeat")) interrupt = ACTION_STD_CANCEL;
    if (!strcmp(scenario, "usb")) interrupt = SYS_USB_CONNECTED;
    if (!strcmp(scenario, "usb-empty")) interrupt = SYS_USB_CONNECTED;
    if (!strcmp(scenario, "power")) interrupt = SYS_POWEROFF;
    if (!strcmp(scenario, "reboot")) interrupt = SYS_REBOOT;
    if (!strcmp(scenario, "filesystem")) interrupt = SYS_FS_CHANGED;
    if (interrupt != ACTION_NONE)
    {
        input[3] = (struct input_event){ interrupt, BUTTON_POWER | BUTTON_REPEAT };
        CHECK(presets_scan(NULL) == 1);
        CHECK(scanned == 3 && num_presets == (no_stations ? 0 : 3) && unpins == 1 && complete_calls == 0);
        CHECK(event_calls == (IS_SYSEVENT(interrupt) ? 1 : 0));
        CHECK(unmute_calls == (IS_SYSEVENT(interrupt) ? 0 : 1));
        CHECK(next_calls == (IS_SYSEVENT(interrupt) ? 0 : 1));
        return;
    }
    if (!strcmp(scenario, "system-update"))
        input[1] = (struct input_event){ SYS_BATTERY_UPDATE, BUTTON_NONE };
    if (!strcmp(scenario, "redraw"))
        input[1] = (struct input_event){ ACTION_REDRAW, BUTTON_UP };
    if (!strcmp(scenario, "multimedia"))
        input[1] = (struct input_event){ BUTTON_MULTIMEDIA | 1, BUTTON_NONE };
    if (!strcmp(scenario, "no-stations")) no_stations = true;
    if (!strcmp(scenario, "capacity")) fm_region_data[0].freq_max = 96000000;
#ifdef HAVE_ESPEAK
    if (!strcmp(scenario, "busy")) all_busy = true;
#endif
    CHECK(presets_scan(NULL) == 1);
    if (!strcmp(scenario, "all-speech-off"))
    {
        CHECK(scanned == 6 && speak_calls == 0 && complete_calls == 0);
        return;
    }
    if (!strcmp(scenario, "dynamic-off"))
    {
        CHECK(scanned == 6 && speak_calls == 0);
#ifdef HAVE_ESPEAK
        CHECK(complete_calls == 1);
#else
        CHECK(complete_calls == 0);
#endif
        return;
    }
    if (!strcmp(scenario, "paused-radio"))
    {
        CHECK(scanned == 6 && num_presets == 6 && unmute_calls == 0 && complete_calls == 1);
        CHECK(radio_status == FMRADIO_PAUSED);
        return;
    }
    if (!strcmp(scenario, "capacity"))
    {
        CHECK(scanned == MAX_PRESETS && num_presets == MAX_PRESETS && unpins == 1);
        CHECK(complete_calls == 1);
        return;
    }
    if (!strcmp(scenario, "no-stations"))
    {
        CHECK(scanned == 6 && num_presets == 0 && !presets_loaded && speak_calls == 0);
        CHECK(current_frequency == fm_region_data[0].freq_min && complete_calls == 1);
        return;
    }
    check_completed();
    if (!strcmp(scenario, "enter-mute") || !strcmp(scenario, "reset")) CHECK(speak_calls == 0);
    else if (!strcmp(scenario, "release-ok") || !strcmp(scenario, "unknown-hold")) CHECK(speak_calls == 1);
    else if (!strcmp(scenario, "busy"))
    {
#ifdef HAVE_ESPEAK
        CHECK(speak_calls == 0);
#else
        CHECK(speak_calls == 2);
#endif
    }
    else
    {
        CHECK(speak_calls == 2);
        CHECK(spoken[0] == 87500000);
        CHECK(spoken[1] == 87900000 || spoken[1] == 88000000);
    }
    if (!strcmp(scenario, "system-update") || !strcmp(scenario, "multimedia")) CHECK(event_calls == 1);
    if (!strcmp(scenario, "found")) CHECK(status_reads == 0);
    if (!strcmp(scenario, "reset"))
    {
        reset();
        presets_scan(NULL);
        CHECK(speak_calls == 2 && complete_calls == 1);
    }
}

#ifdef HAVE_RDS_CAP
struct simplelist_info {
    const char *title;
    int count;
    bool scroll_all;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
    int (*action_callback)(int, struct gui_synclist *);
    void *callback_data;
};
static char station_name[512], station_text[512], last_spelling[512];
static bool no_rds_data, unterminated_rds, refresh_during_list, list_usb;
static int spell_calls, refresh_reads;
static bool radio_hardware_present(void) { return hardware_present; }
static size_t tuner_get_rds_info(int setting, void *buffer, size_t size)
{
    physical_reads++;
    CHECK(setting == RADIO_RDS_NAME || setting == RADIO_RDS_TEXT);
    CHECK(size == (setting == RADIO_RDS_NAME ? 25u : 193u));
    if (no_rds_data)
    {
        memcpy(buffer, "stale", 6);
        return 0;
    }
    const char *source = setting == RADIO_RDS_NAME ? station_name : station_text;
    if (unterminated_rds) memset(buffer, 'X', size);
    else
    {
        size_t length = strlen(source);
        if (length >= size) length = size - 1;
        memcpy(buffer, source, length);
        ((char *)buffer)[length] = '\0';
    }
    return strlen(source);
}
static int talk_spell(const char *text, bool enqueue)
{
    CHECK(enqueue);
    spell_calls++;
    snprintf(last_spelling, sizeof(last_spelling), "%s", text);
    return 0;
}
static void simplelist_info_init(struct simplelist_info *list, const char *title, int count, void *data)
{
    memset(list, 0, sizeof(*list));
    list->title = title;
    list->count = count;
    list->callback_data = data;
}
static void gui_synclist_speak_item(struct gui_synclist *lists);
static bool simplelist_show_list(struct simplelist_info *list);
ACTUAL_RDS_SOURCE
static void gui_synclist_speak_item(struct gui_synclist *lists)
{
    CHECK(lists->selected_item == 1);
    radio_info_speak(lists->selected_item, lists->data);
}
static bool simplelist_show_list(struct simplelist_info *list)
{
    char display[256];
    CHECK(list->title == str(LANG_FM_RDS_INFO) && list->count == 2 && list->scroll_all);
    CHECK(list->get_name && list->action_callback && list->get_talk);
    for (int row = 0; row < 2; row++)
    {
        CHECK(list->get_name(row, list->callback_data, display, sizeof(display)) == display);
        CHECK(strstr(display, row == 0 ? str(LANG_FM_RDS_NAME) : str(LANG_FM_RDS_TEXT)) != NULL);
        CHECK(list->get_talk(row, list->callback_data) == 0);
        if (no_rds_data || !hardware_present || radio_status == FMRADIO_OFF)
            CHECK(strstr(display, str(LANG_FM_RDS_NO_DATA)) != NULL);
    }
    struct gui_synclist lists = { .data = list->callback_data, .selected_item = 1 };
    refresh_reads = physical_reads;
    int previous_spell_calls = spell_calls;
    char previous_display[256];
    list->get_name(1, list->callback_data, previous_display, sizeof(previous_display));
    strcpy(station_text, "Background radio text");
    for (int poll = 0; poll < 20; poll++) CHECK(list->action_callback(ACTION_NONE, &lists) == ACTION_NONE);
    CHECK(physical_reads == refresh_reads);
    CHECK(spell_calls == previous_spell_calls);
    list->get_name(1, list->callback_data, display, sizeof(display));
    CHECK(!strcmp(previous_display, display));
    CHECK(list->action_callback(SYS_USB_CONNECTED, &lists) == SYS_USB_CONNECTED);
    if (refresh_during_list)
    {
        strcpy(station_text, "Fresh radio text");
        CHECK(list->action_callback(ACTION_STD_OK, &lists) == ACTION_REDRAW);
        CHECK(physical_reads == refresh_reads + 2);
        CHECK(!strcmp(last_spelling, "Fresh radio text"));
    }
    return list_usb;
}
static void rds_scenario(const char *scenario)
{
    reset();
    strcpy(station_name, "Station");
    strcpy(station_text, "Radio text with Polish UTF-8: Łódź");
    no_rds_data = unterminated_rds = refresh_during_list = list_usb = false;
    spell_calls = refresh_reads = 0;
    global_settings.tts_announce_dynamic = false;
    if (!strcmp(scenario, "rds-empty")) no_rds_data = true;
    if (!strcmp(scenario, "rds-off")) radio_status = FMRADIO_OFF;
    if (!strcmp(scenario, "rds-missing")) hardware_present = false;
    if (!strcmp(scenario, "rds-long")) unterminated_rds = true;
    if (!strcmp(scenario, "rds-refresh")) refresh_during_list = true;
    if (!strcmp(scenario, "rds-partial")) station_name[0] = '\0';
    if (!strcmp(scenario, "rds-usb")) list_usb = true;
    int result = radio_show_info();
    CHECK(result == (list_usb ? MENU_ATTACHED_USB : 0));
    fixture_menu_result = result;
    fixture_radio_menu();
    CHECK(fixture_menu_done == list_usb && fixture_menu_freeze == list_usb);
    if (no_rds_data || !hardware_present || radio_status == FMRADIO_OFF)
    {
        CHECK(spell_calls == 0);
        CHECK(id_calls == 4 && spoken_ids[0] == LANG_FM_RDS_NAME && spoken_ids[1] == LANG_FM_RDS_NO_DATA);
        CHECK(spoken_ids[2] == LANG_FM_RDS_TEXT && spoken_ids[3] == LANG_FM_RDS_NO_DATA);
    }
    else if (!strcmp(scenario, "rds-partial"))
    {
        CHECK(spell_calls == 1 && id_calls == 3);
        CHECK(spoken_ids[0] == LANG_FM_RDS_NAME && spoken_ids[1] == LANG_FM_RDS_NO_DATA && spoken_ids[2] == LANG_FM_RDS_TEXT);
    }
    else
        CHECK(spell_calls == (refresh_during_list ? 3 : 2));
    if (!hardware_present || radio_status == FMRADIO_OFF) CHECK(physical_reads == 0);
    if (unterminated_rds) CHECK(strlen(last_spelling) == 192);
}
#endif

int main(int argument_count, char **arguments)
{
    CHECK(argument_count == 3);
    CHECK(!strcmp(arguments[2], "english") || !strcmp(arguments[2], "polski"));
    fixture_language = !strcmp(arguments[2], "polski");
#ifdef HAVE_RDS_CAP
    if (!strncmp(arguments[1], "rds-", 4)) rds_scenario(arguments[1]);
    else
#endif
        scan_scenario(arguments[1]);
    CHECK(automatic_speech_calls == 0);
    puts("PASS");
    return 0;
}
