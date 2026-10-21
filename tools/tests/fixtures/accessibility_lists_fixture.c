#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#ifdef _WIN32
#include <windows.h>
#endif

static char scenario_context[256];
#undef assert
#define assert(condition) do { if (!(condition)) { \
    fprintf(stderr, "CHECK_FAILED %s:%d: %s [%s]\n", __FILE__, __LINE__, #condition, scenario_context); \
    exit(101); } } while (0)

#define HAVE_ESPEAK 1
#define HAVE_TOUCHSCREEN 1
#define HIBY_R1 1
#define HZ 100
#define NB_SCREENS 2
#define MAX_PATH 260
#define MAX(first, second) ((first) > (second) ? (first) : (second))
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define FOR_NB_SCREENS(screen) for (int screen = 0; screen < 2; ++screen)
#define TIME_BEFORE(first, second) ((first) < (second))
#define TIME_AFTER(first, second) ((first) > (second))
#define CONFIG_CPU (-1)
ACTUAL_LANGUAGE_POINTER_SOURCE
#define IS_SYSEVENT(action) ((action) >= 1000)
#define BUTTON_NONE 0
#define BUTTON_REL 0x10000
#define BUTTON_REPEAT 0x20000
#define BUTTON_TOUCHSCREEN 0x100
#define BUTTON_MULTIMEDIA 0x40000
#define SYS_EVENT 0x80000
#define KEYCLICK_DURATION 2
#define KEYCLICK_SOURCE_NONE 0u
#define KEYCLICK_SOURCE_PHYSICAL 1u
#define KEYCLICK_SOURCE_GESTURE 2u
#define KEYCLICK_SOURCE_EXPLORATION 4u
#define FRAMEDROP_TRIGGER 6
enum screen_type { SCREEN_MAIN, SCREEN_REMOTE };
enum { ACTION_NONE, ACTION_STD_PREV, ACTION_STD_PREVREPEAT, ACTION_STD_NEXT,
       ACTION_STD_NEXTREPEAT, ACTION_LISTTREE_PGUP, ACTION_LISTTREE_PGDOWN,
       ACTION_TOUCHSCREEN, ACTION_UNKNOWN, ACTION_WPS_STOPSEEK,
       ACTION_LIST_FIRST, ACTION_LIST_LAST, ACTION_LIST_PAGE_FIRST, ACTION_LIST_PAGE_LAST };
enum { SOUND_KEYCLICK, SOUND_LIST_EDGE_BEEP_WRAP, SOUND_LIST_EDGE_BEEP_NOWRAP };
enum { VOICE_EMPTY_LIST = 50, LANG_ACCESSIBILITY_LIST_START, LANG_ACCESSIBILITY_LIST_END, VOICE_BLANK, VOICE_OF };
#define LANG_LAST_INDEX_IN_ARRAY 3
#define VOICEONLY_DELIMITER (VOICE_EMPTY_LIST - 1)
#define LANG_LAST_VOICEONLY_INDEX_IN_ARRAY (VOICE_OF + 1)
#define TTS_STRING_COUNT (LANG_LAST_INDEX_IN_ARRAY + LANG_LAST_VOICEONLY_INDEX_IN_ARRAY - VOICEONLY_DELIMITER - 1)

static const unsigned char *const language_strings[] = {
    (const unsigned char *)"translated zero", (const unsigned char *)"translated one", (const unsigned char *)""
};
static const unsigned char *str(int identifier)
{
    assert(identifier >= 0 && (size_t)identifier < sizeof(language_strings) / sizeof(language_strings[0]));
    return language_strings[identifier];
}
typedef bool (*keyclick_callback)(int action, void *data);
typedef int list_speak_item(int item, void *data);
typedef const char *list_get_name(int item, void *data, char *buffer, size_t size);
typedef int list_get_icon(int item, void *data);
enum themable_icons { Icon_NOICON };
struct viewport { int unused; };
ACTUAL_POSITION_ENUMS
struct gui_synclist {
    int scrollbar, cursor_style;
    bool show_icons, scroll_paginated;
    int nb_items, selected_item, selected_size, start_item[2], visible_lines[2];
    bool keyclick, talk_menu, wraparound, boundary_speech_pending;
    enum list_position_source position_source;
    long scheduled_talk_tick, last_talked_tick;
    list_speak_item *callback_speak_item;
    const char *(*callback_get_item_name)(int item, void *data, char *buffer, size_t size);
    void *data;
    bool scroll_all;
    int offset_position[NB_SCREENS], line_height[NB_SCREENS];
    int y_pos, scroll_base_y, scroll_mode;
    struct viewport *parent[NB_SCREENS];
    const char *title;
    enum themable_icons title_icon;
    list_get_icon *callback_get_item_icon;
    void *callback_draw_item;
};
ACTUAL_SIMPLELIST_STRUCT
static struct user_settings { int keyclick, list_boundary_feedback, scrollbar, cursor_style;
    bool keyclick_repeats, list_wraparound, talk_menu, tts_enabled, show_icons, scroll_paginated;
    int tts_announce_position;
    bool tts_announce_dynamic;
} global_settings;
ACTUAL_POSITION_POLICY
static long current_tick;
static unsigned int source_mask = 7;
static int raw_button, sounds, clicks, boundaries[256], boundary_count, utterances[256], spoken_count;
static bool disabled, force_enqueue_next, synth_available = true;
static bool need_shutup;
static int queue_write, queue_read, thumbnail_buf_used, current_language;
static char spoken_text[256][MAX_PATH];
static int speech_history[256], history_count;
static char text_history[256][MAX_PATH];
static bool text_enqueued[256];
static int spell_calls, voicefile_count, voicefile_ids[256];
static const char *const boundary_labels[2][2] = ACTUAL_BOUNDARY_LABELS;
static const char *const row_labels[2][2] = ACTUAL_ROW_LABELS;
static const char *const position_labels[2][1] = ACTUAL_POSITION_LABELS;
static uint32_t voice_offset_sets[2][TTS_STRING_COUNT];
static unsigned char voice_string_sets[2][512];
#define voice_offsets voice_offset_sets[current_language]
#define voice_strings voice_string_sets[current_language]
ACTUAL_VOICE_TEXT_SOURCE
static bool talk_menus_enabled(const void *settings)
{ (void)settings; return global_settings.talk_menu || global_settings.tts_enabled; }
static bool tts_is_available(void) { return synth_available; }
static void tts_stop(void) { spoken_count = 0; }
static void talk_queue_lock(void) { }
static void talk_queue_unlock(void) { }
ACTUAL_ENQUEUE_SOURCE
static int tts_speak_id(int32_t label, bool enqueue)
{
    assert(enqueue);
    assert(spoken_count < 256);
    assert(history_count < 256);
    speech_history[history_count++] = label;
    utterances[spoken_count] = label;
    text_enqueued[spoken_count] = false;
    spoken_text[spoken_count][0] = '\0';
    if (label == LANG_ACCESSIBILITY_LIST_START || label == LANG_ACCESSIBILITY_LIST_END)
    {
        boundaries[boundary_count++] = label;
        snprintf(spoken_text[spoken_count], MAX_PATH, "%s",
                 boundary_labels[current_language][label == LANG_ACCESSIBILITY_LIST_END]);
    }
    else if (label == VOICE_OF)
        snprintf(spoken_text[spoken_count], MAX_PATH, "%s", position_labels[current_language][0]);
    ++spoken_count;
    return 0;
}
static int talk_id(int32_t id, bool enqueue)
{
    if (disabled) return -1;
    ACTUAL_TALK_ID_TTS_SOURCE
    assert(voicefile_count < 256);
    voicefile_ids[voicefile_count++] = id;
    return 0;
}
static int tts_speak(const char *text, size_t length, bool enqueue)
{
    assert(length < MAX_PATH);
    char *end;
    long value = strtol(text, &end, 10);
    int identifier = end != text && *end == '\0' && value >= INT_MIN && value <= INT_MAX - 100 ?
        (int)value + 100 : 100;
    int result = tts_speak_id(identifier, true);
    memcpy(spoken_text[spoken_count - 1], text, length);
    spoken_text[spoken_count - 1][length] = '\0';
    text_enqueued[spoken_count - 1] = enqueue;
    snprintf(text_history[history_count - 1], MAX_PATH, "%s", spoken_text[spoken_count - 1]);
    return result;
}
ACTUAL_VOICE_ID_WRAPPER
static int talk_spell(const char *spell, bool enqueue)
{
    ++spell_calls;
    if (disabled) return -1;
    size_t len = strlen(spell);
    do_enqueue(enqueue);
    ACTUAL_TALK_SPELL_TTS_SOURCE
    return 0;
}
static unsigned int accessibility_keyclick_sources(void) { return source_mask; }
static bool accessibility_enabled(void) { return true; }
static bool accessibility_empty_sound_enabled(void) { return true; }
static int accessibility_keyclick_empty_pitch(void) { return -4; }
static void get_action_statuscode(int *button) { *button = raw_button; }
static void beep_play(unsigned int frequency, unsigned int duration, unsigned int amplitude)
{ (void)frequency; (void)duration; (void)amplitude; ++clicks; }
static void system_sound_play(int sound)
{
    if (!global_settings.keyclick) return;
    if (sound == SOUND_KEYCLICK) ++clicks;
    else ++sounds;
}
static int list_get_nb_lines(struct gui_synclist *list, enum screen_type screen)
{ return list->visible_lines[screen]; }
static void gui_list_put_selection_on_screen(struct gui_synclist *list, int screen)
{ (void)list; (void)screen; }
static void gui_synclist_draw(struct gui_synclist *list) { (void)list; }
static void yield(void) { }
static int button_queue_count(void) { return 0; }
static struct viewport parent[NB_SCREENS];
static void accessibility_set_target(struct gui_synclist *list) { (void)list; }
static void list_init_viewports(struct gui_synclist *list) { (void)list; }
static void list_init_item_height(struct gui_synclist *list, int screen) { (void)list; (void)screen; }
static void skinlist_set_cfg(int screen, void *data) { (void)screen; (void)data; }
static int simplelist_line_count;
static void simplelist_reset_lines(void) { simplelist_line_count = 0; }
static const char *simplelist_static_getname(int item, void *data, char *buffer, size_t size)
{ (void)item; (void)data; (void)buffer; (void)size; return "static row"; }
static void sb_set_persistent_title(const char *title, int icon, int screen)
{ (void)title; (void)icon; (void)screen; }
static void viewportmanager_theme_enable(int screen, bool enabled, void *data)
{ (void)screen; (void)enabled; (void)data; }

ACTUAL_KEYCLICK_SOURCE

ACTUAL_LIST_SOURCE

static int speak_row(int item, void *data)
{ (void)data; return talk_id(100 + item, false); }
static int silent_row(int item, void *data)
{ (void)item; (void)data; return 0; }
static int failing_row(int item, void *data)
{ (void)item; (void)data; return -1; }
static int fixed_row(int item, void *data)
{ (void)item; (void)data; return talk_id(100, false); }
static const char *name_row(int item, void *data, char *buffer, size_t size)
{ (void)item; (void)buffer; (void)size; return data; }
static const char *localized_row(int item, void *data, char *buffer, size_t size)
{ (void)data; (void)buffer; (void)size; return row_labels[current_language][item == 19]; }
static const char *numbered_row(int item, void *data, char *buffer, size_t size)
{ (void)data; snprintf(buffer, size, "%d", item); return buffer; }
ACTUAL_CONSTRUCTION_SOURCE
static struct gui_synclist setup(void)
{
    assert(!strcmp(P2STR(ID2P(1)), "translated one"));
    current_tick = 100;
    sounds = clicks = boundary_count = spoken_count = history_count = 0;
    spell_calls = voicefile_count = 0;
    memset(voice_offset_sets, 0xff, sizeof(voice_offset_sets));
    for (int language = 0; language < 2; ++language)
    {
        snprintf((char *)voice_string_sets[language], sizeof(voice_string_sets[language]),
                 "%s", position_labels[language][0]);
        voice_offset_sets[language][voice_index(VOICE_OF)] = 0;
    }
    disabled = force_enqueue_next = need_shutup = false;
    synth_available = true;
    source_mask = 7;
    global_settings.keyclick = 2;
    global_settings.keyclick_repeats = false;
    global_settings.list_wraparound = false;
    global_settings.list_boundary_feedback = 0;
    global_settings.talk_menu = false;
    global_settings.tts_enabled = true;
    global_settings.tts_announce_position = TTS_POSITION_OFF;
    global_settings.tts_announce_dynamic = true;
    return (struct gui_synclist){.nb_items = 20, .selected_size = 1, .keyclick = true,
        .talk_menu = true, .wraparound = true, .visible_lines = {5, 3}, .callback_speak_item = speak_row};
}
static void move(struct gui_synclist *list, int offset, bool wrap, bool gesture, bool repeat)
{
    int action = offset < 0 ? ACTION_STD_PREV : ACTION_STD_NEXT;
    if (repeat) action = offset < 0 ? ACTION_STD_PREVREPEAT : ACTION_STD_NEXTREPEAT;
    keyclick_set_callback(gui_synclist_keyclick_callback, list);
    if (gesture) keyclick_click_gesture_repeat(action, repeat);
    else keyclick_click_physical(action, repeat);
    if (offset == -1 || offset == 1)
    {
        bool previous_wrap = list->wraparound;
        list->wraparound = wrap;
        assert(fixture_do_navigation(list, &action));
        list->wraparound = previous_wrap;
    }
    else
        gui_list_select_at_offset(list, offset, wrap);
    ++current_tick;
}
static void rapid_wrap(const char *scenario)
{
    bool up = strstr(scenario, "-up") != NULL;
    bool labels = strstr(scenario, "-labels") != NULL;
    bool cancel = strstr(scenario, "-cancel") != NULL;
    bool taps = strstr(scenario, "-taps") != NULL;
    bool loss = strstr(scenario, "-loss") != NULL;
    int direction = up ? -1 : 1;
    for (int language = 0; language < 2; ++language)
    for (int feedback = 0; feedback < 4; ++feedback)
    for (int wrap = 0; wrap < 2; ++wrap)
    for (int repeat = 0; repeat < 2; ++repeat)
    for (int sound = 0; sound < 2; ++sound)
    for (int gap = 0; gap <= HZ / 5 + 1; ++gap)
    {
        snprintf(scenario_context, sizeof(scenario_context),
                 "%s language=%d feedback=%d wrap=%d repeat=%d sound=%d gap=%d",
                 scenario, language, feedback, wrap, repeat, sound, gap);
        struct gui_synclist list = setup();
        current_language = language;
        global_settings.list_boundary_feedback = feedback;
        global_settings.list_wraparound = wrap;
        global_settings.keyclick = sound ? 2 : 0;
        if (labels)
        {
            list.callback_speak_item = NULL;
            list.callback_get_item_name = localized_row;
        }
        list.selected_item = up ? 1 : 18;
        move(&list, direction, true, false, false);
        assert(list.selected_item == (up ? 0 : 19));
        current_tick += gap;
        int prefix = up ? LANG_ACCESSIBILITY_LIST_START : LANG_ACCESSIBILITY_LIST_END;
        int destination = up ? 19 : 0;
        bool wrapping = wrap && !repeat;
        bool speech = feedback == 0 || feedback == 2;
        int previous_sounds = sounds;
        int previous_boundaries = boundary_count;
        int previous_history = history_count;
        move(&list, direction, true, false, repeat);
        assert(list.selected_item == (wrapping ? destination : (up ? 0 : 19)));
        assert(boundary_count == previous_boundaries + speech);
        assert(sounds == previous_sounds + (sound && !repeat && (feedback == 0 || feedback == 1)));
        if (wrapping && loss)
        {
            move(&list, direction, true, false, false);
            current_tick += HZ;
            assert(!fixture_speak_pending(&list));
            assert(list.selected_item == destination + direction);
            assert(spoken_count == 1 && utterances[0] == 100 + destination + direction);
            bool requested_destination = false;
            for (int event = previous_history; event < history_count; ++event)
                requested_destination |= speech_history[event] == 100 + destination;
            if (language == 0 && feedback == 0 && sound == 0 && gap == 0)
            {
                printf("TRACE %s", scenario);
                for (int event = 0; event < history_count; ++event)
                    printf(" %d", speech_history[event]);
                printf("\n");
            }
            assert(requested_destination);
            assert(!list.scheduled_talk_tick && !list.boundary_speech_pending && !force_enqueue_next);
            continue;
        }
        if (wrapping)
        {
            assert(!list.scheduled_talk_tick && !list.boundary_speech_pending && !force_enqueue_next);
            assert(spoken_count == 1 + speech);
            if (speech)
            {
                assert(utterances[0] == prefix);
                assert(!strcmp(spoken_text[0], boundary_labels[language][up ? 0 : 1]));
            }
            if (labels)
                assert(!strcmp(spoken_text[spoken_count - 1], row_labels[language][up ? 1 : 0]));
            else
                assert(utterances[spoken_count - 1] == 100 + destination);
            if (cancel)
            {
                move(&list, direction, true, false, false);
                assert(list.selected_item == destination + direction);
                assert(!spoken_count && list.scheduled_talk_tick && !force_enqueue_next);
                current_tick += HZ;
                assert(!fixture_speak_pending(&list));
                assert(spoken_count == 1 && utterances[0] == 100 + destination + direction);
                assert(!list.scheduled_talk_tick && !list.boundary_speech_pending);
            }
            if (taps)
            {
                for (int press = 0; press < 40; ++press)
                {
                    int offset = press % 2 == 0 ? -direction : direction;
                    int target = press % 2 == 0 ? (up ? 0 : 19) : destination;
                    int label = offset < 0 ? LANG_ACCESSIBILITY_LIST_START : LANG_ACCESSIBILITY_LIST_END;
                    move(&list, offset, true, false, false);
                    assert(list.selected_item == target && !list.scheduled_talk_tick);
                    assert(spoken_count == 1 + speech && !force_enqueue_next);
                    if (speech) assert(utterances[0] == label);
                    assert(utterances[spoken_count - 1] == 100 + target);
                }
            }
        }
        current_tick += HZ;
        assert(!fixture_speak_pending(&list));
        assert(!list.scheduled_talk_tick && !force_enqueue_next);
        if (!wrapping && speech)
            assert(spoken_count == 1 && utterances[0] == prefix);
    }
}
static void check_position(int offset, long position, long total)
{
    char expected[96];
    int length = snprintf(expected, sizeof(expected), "%ld %s %ld", position,
                          tts_get_voice_text(VOICE_OF), total);
    assert(length >= 0 && (size_t)length < sizeof(expected));
    assert(spoken_count == offset + 1);
    assert(!strcmp(spoken_text[offset], expected) && text_enqueued[offset]);
    assert(utterances[offset] != VOICE_OF);
    assert(!force_enqueue_next);
}

static void position_case(const char *scenario)
{
    for (int language = 0; language < 2; ++language)
    {
        snprintf(scenario_context, sizeof(scenario_context), "%s language=%d", scenario, language);
        struct gui_synclist list = setup();
        current_language = language;
        global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
        global_settings.tts_announce_dynamic = false;
        if (!strcmp(scenario, "position-callback-enabled") ||
            !strcmp(scenario, "position-callback-disabled") ||
            !strcmp(scenario, "position-fallback-enabled") ||
            !strcmp(scenario, "position-fallback-disabled"))
        {
            bool enabled = strstr(scenario, "-disabled") == NULL;
            bool fallback = strstr(scenario, "-fallback-") != NULL;
            global_settings.tts_announce_position = enabled ? TTS_POSITION_EVERYWHERE : TTS_POSITION_OFF;
            list.selected_item = 19;
            list.callback_get_item_name = localized_row;
            if (fallback) list.callback_speak_item = NULL;
            gui_synclist_speak_item(&list);
            if (fallback)
                assert(!strcmp(spoken_text[0], row_labels[language][1]));
            else
                assert(utterances[0] == 119);
            assert(spell_calls == (int)enabled + (int)fallback);
            if (enabled) check_position(1, 20, 20);
            else assert(spoken_count == 1);
            assert(!list.scheduled_talk_tick && !list.boundary_speech_pending);
        }
        else if (!strcmp(scenario, "position-groups"))
        {
            const int groups[][5] = {
                {8, 3, 0, 1, 3}, {8, 3, 3, 2, 3}, {8, 3, 6, 3, 3}, {8, 3, 7, 3, 3},
                {9, 3, 6, 3, 3}, {1, 3, 0, 1, 1}, {20, 0, 7, 8, 20}, {20, -3, 7, 8, 20},
                {INT_MAX, 1, 0, 1, INT_MAX}, {INT_MAX, INT_MAX, 0, 1, 1},
                {INT_MAX, INT_MAX - 1, INT_MAX - 1, 2, 2}
            };
            for (size_t group = 0; group < sizeof(groups) / sizeof(groups[0]); ++group)
            {
                list = setup();
                global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
                list.nb_items = groups[group][0];
                list.selected_size = groups[group][1];
                list.selected_item = groups[group][2];
                list.callback_speak_item = fixed_row;
                gui_synclist_speak_item(&list);
                assert(utterances[0] == 100 && spell_calls == 1);
                check_position(1, groups[group][3], groups[group][4]);
            }
        }
        else if (!strcmp(scenario, "position-partial-group-labels"))
        {
            list.nb_items = 8;
            list.selected_size = 3;
            list.selected_item = 6;
            list.callback_speak_item = NULL;
            list.callback_get_item_name = numbered_row;
            gui_synclist_speak_item(&list);
            assert(!strcmp(spoken_text[0], "6") && !strcmp(spoken_text[1], "7"));
            assert(spell_calls == 3);
            check_position(2, 3, 3);
        }
        else if (!strcmp(scenario, "position-empty-invalid"))
        {
            const int invalid[][2] = {{0, 0}, {-1, 0}, {20, -1}, {20, 20}, {20, INT_MAX}};
            for (size_t entry = 0; entry < sizeof(invalid) / sizeof(invalid[0]); ++entry)
            {
                list = setup();
                global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
                list.nb_items = invalid[entry][0];
                list.selected_item = invalid[entry][1];
                list.scheduled_talk_tick = current_tick + HZ;
                _gui_synclist_speak_item(&list, true);
                assert(!spoken_count && !spell_calls && !list.scheduled_talk_tick);
                gui_synclist_speak_item(&list);
                assert(!spell_calls);
                if (!list.nb_items)
                    assert(spoken_count == 1 && utterances[0] == VOICE_EMPTY_LIST);
                else
                    assert(!spoken_count);
            }
            list = setup();
            global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
            list.callback_speak_item = NULL;
            gui_synclist_speak_item(&list);
            assert(!spoken_count && !spell_calls);
            list.callback_get_item_name = localized_row;
            list.talk_menu = false;
            gui_synclist_speak_item(&list);
            assert(!spoken_count && !spell_calls);
        }
        else if (!strcmp(scenario, "position-failed-callback"))
        {
            list.callback_speak_item = failing_row;
            list.callback_get_item_name = localized_row;
            gui_synclist_speak_item(&list);
            assert(!spoken_count && !spell_calls && !list.scheduled_talk_tick);
            disabled = true;
            list.callback_speak_item = speak_row;
            current_tick += HZ;
            gui_synclist_speak_item(&list);
            assert(!spoken_count && !spell_calls);
        }
        else if (!strcmp(scenario, "position-wrapped-failed-callback"))
        {
            for (int feedback = 0; feedback < 4; ++feedback)
            for (int direction = -1; direction <= 1; direction += 2)
            {
                list = setup();
                global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
                global_settings.list_wraparound = true;
                global_settings.list_boundary_feedback = feedback;
                list.selected_item = direction > 0 ? 19 : 0;
                list.callback_speak_item = failing_row;
                move(&list, direction, true, false, false);
                bool speech = feedback == 0 || feedback == 2;
                assert(spoken_count == speech && !spell_calls);
                if (speech)
                    assert(utterances[0] == (direction > 0 ? LANG_ACCESSIBILITY_LIST_END :
                                            LANG_ACCESSIBILITY_LIST_START));
                assert(!force_enqueue_next && !list.boundary_speech_pending && !list.scheduled_talk_tick);
                list.callback_speak_item = speak_row;
                current_tick += HZ;
                move(&list, direction, true, false, false);
                assert(utterances[0] == 100 + list.selected_item);
                check_position(1, list.selected_item + 1, 20);
            }
        }
        else if (!strcmp(scenario, "position-local-mute"))
        {
            list.talk_menu = false;
            gui_synclist_select_item(&list, 1);
            assert(spoken_count == 1 && utterances[0] == 101 && !spell_calls);
            current_tick += HZ;
            _gui_synclist_speak_item(&list, true);
            assert(spoken_count == 1 && utterances[0] == 101 && !spell_calls);
            gui_synclist_speak_item(&list);
            assert(spoken_count == 1 && !spell_calls && !force_enqueue_next);
        }
        else if (!strcmp(scenario, "position-unlabelled-row"))
        {
            list.callback_speak_item = silent_row;
            gui_synclist_speak_item(&list);
            check_position(0, 1, 20);
            const char *labels[] = {NULL, "", (const char *)ID2P(VOICE_BLANK)};
            for (size_t entry = 0; entry < sizeof(labels) / sizeof(labels[0]); ++entry)
            {
                list = setup();
                global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
                list.callback_speak_item = NULL;
                list.callback_get_item_name = name_row;
                list.data = (void *)labels[entry];
                gui_synclist_speak_item(&list);
                if (entry == 2) assert(utterances[0] == VOICE_BLANK);
                check_position(entry == 2 ? 1 : 0, 1, 20);
                assert(spell_calls == 1);
            }
        }
        else if (!strcmp(scenario, "position-voicefiles-only"))
        {
            for (int enabled = 0; enabled < 2; ++enabled)
            for (int position = 0; position < 2; ++position)
            {
                list = setup();
                synth_available = false;
                global_settings.tts_enabled = enabled;
                global_settings.talk_menu = true;
                global_settings.tts_announce_position = position ? TTS_POSITION_EVERYWHERE : TTS_POSITION_OFF;
                gui_synclist_speak_item(&list);
                assert(voicefile_count == 1 && voicefile_ids[0] == 100);
                assert(!spoken_count && !spell_calls);
                list.callback_speak_item = NULL;
                list.callback_get_item_name = localized_row;
                current_tick += HZ;
                gui_synclist_speak_item(&list);
                assert(voicefile_count == 1 && !spoken_count && !spell_calls);
            }
        }
        else if (!strcmp(scenario, "position-missing-connector"))
        {
            for (int missing = 0; missing < 2; ++missing)
            {
                list = setup();
                global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
                if (missing) voice_offsets[voice_index(VOICE_OF)] = UINT32_MAX;
                else voice_strings[0] = '\0';
                gui_synclist_speak_item(&list);
                assert(spoken_count == 1 && utterances[0] == 100 && !spell_calls);
                global_settings.list_wraparound = true;
                list.selected_item = 19;
                current_tick += HZ;
                move(&list, 1, true, false, false);
                assert(spoken_count == 2 && utterances[0] == LANG_ACCESSIBILITY_LIST_END && utterances[1] == 100);
                assert(!spell_calls && !force_enqueue_next && !list.scheduled_talk_tick && !list.boundary_speech_pending);
            }
        }
        else if (!strcmp(scenario, "position-oversized-connector"))
        {
            const int limits[][4] = {{20, 0, 90, 1}, {20, 0, 91, 0},
                {INT_MAX, INT_MAX - 1, 73, 1}, {INT_MAX, INT_MAX - 1, 74, 0}, {20, 0, 511, 0}};
            for (size_t entry = 0; entry < sizeof(limits) / sizeof(limits[0]); ++entry)
            {
                list = setup();
                global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
                list.nb_items = limits[entry][0];
                list.selected_item = limits[entry][1];
                list.callback_speak_item = fixed_row;
                memset(voice_strings, 'x', (size_t)limits[entry][2]);
                voice_strings[limits[entry][2]] = '\0';
                gui_synclist_speak_item(&list);
                assert(utterances[0] == 100);
                assert(spoken_count == 1 + limits[entry][3] && spell_calls == limits[entry][3]);
                if (limits[entry][3])
                {
                    check_position(1, (long)list.selected_item + 1, list.nb_items);
                    assert(strlen(spoken_text[1]) == 95);
                }
                assert(!force_enqueue_next);
            }
        }
        else assert(false);
    }
}

static void position_rapid(const char *scenario)
{
    bool up = strstr(scenario, "-up") != NULL;
    bool labels = strstr(scenario, "-labels") != NULL;
    bool cancel = strstr(scenario, "-cancel") != NULL;
    bool new_request = strstr(scenario, "-new-request") != NULL;
    int direction = up ? -1 : 1;
    int destination = up ? 19 : 0;
    for (int language = 0; language < 2; ++language)
    for (int feedback = 0; feedback < 4; ++feedback)
    for (int sound = 0; sound < 2; ++sound)
    for (int gap = 0; gap <= HZ / 5 + 1; ++gap)
    {
        snprintf(scenario_context, sizeof(scenario_context),
                 "%s language=%d feedback=%d sound=%d gap=%d", scenario, language, feedback, sound, gap);
        struct gui_synclist list = setup();
        current_language = language;
        global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
                global_settings.list_wraparound = true;
        global_settings.list_boundary_feedback = feedback;
        global_settings.keyclick = sound ? 2 : 0;
        if (labels)
        {
            list.callback_speak_item = NULL;
            list.callback_get_item_name = localized_row;
        }
        list.selected_item = up ? 1 : 18;
        move(&list, direction, true, false, false);
        check_position(1, up ? 1 : 20, 20);
        current_tick += gap;
        int before_history = history_count;
        move(&list, direction, true, false, false);
        bool speech = feedback == 0 || feedback == 2;
        assert(list.selected_item == destination);
        assert(!list.scheduled_talk_tick && !list.boundary_speech_pending);
        assert(history_count == before_history + 2 + speech);
        assert(spell_calls == (labels ? 4 : 2));
        if (speech)
        {
            assert(utterances[0] == (up ? LANG_ACCESSIBILITY_LIST_START : LANG_ACCESSIBILITY_LIST_END));
            assert(!strcmp(spoken_text[0], boundary_labels[language][up ? 0 : 1]));
        }
        if (labels)
            assert(!strcmp(spoken_text[speech], row_labels[language][up ? 1 : 0]));
        else
            assert(utterances[speech] == 100 + destination);
        check_position(speech + 1, destination + 1, 20);
        assert(!strcmp(text_history[history_count - 1], spoken_text[spoken_count - 1]));
        assert(sounds == (sound && (feedback == 0 || feedback == 1)));
        if (cancel)
        {
            int wrapped_history = history_count;
            for (int press = 0; press < 2; ++press)
            {
                move(&list, direction, true, false, false);
                assert(!spoken_count && list.scheduled_talk_tick && !force_enqueue_next);
                assert(history_count == wrapped_history && spell_calls == 2);
            }
            current_tick += HZ;
            assert(!fixture_speak_pending(&list));
            assert(utterances[0] == 100 + destination + 2 * direction);
            assert(history_count == wrapped_history + 2 && spell_calls == 3);
            check_position(1, destination + 2 * direction + 1, 20);
        }
        if (new_request)
        {
            talk_id(177, false);
            assert(spoken_count == 1 && utterances[0] == 177 && spell_calls == 2);
            struct gui_synclist other = list;
            other.callback_speak_item = speak_row;
            other.callback_get_item_name = NULL;
            other.last_talked_tick = other.scheduled_talk_tick = 0;
            other.selected_item = 5;
            gui_synclist_speak_item(&other);
            assert(utterances[0] == 105 && spell_calls == 3);
            check_position(1, 6, 20);
        }
        int final_history = history_count;
        current_tick += HZ;
        assert(!fixture_speak_pending(&list));
        assert(history_count == final_history && !list.scheduled_talk_tick && !force_enqueue_next);
    }
}

static void voice_text_lookup(void)
{
    for (int language = 0; language < 2; ++language)
    {
        setup();
        current_language = language;
        unsigned char before_strings[sizeof(voice_strings)];
        uint32_t before_offsets[TTS_STRING_COUNT];
        memcpy(before_strings, voice_strings, sizeof(before_strings));
        memcpy(before_offsets, voice_offsets, sizeof(before_offsets));
        assert(!strcmp(tts_get_voice_text(VOICE_OF), position_labels[language][0]));
        assert(tts_get_voice_text(1) == (const char *)str(1));
        const int invalid[] = {-1, INT_MIN, LANG_LAST_INDEX_IN_ARRAY, VOICEONLY_DELIMITER,
                               LANG_LAST_VOICEONLY_INDEX_IN_ARRAY, INT_MAX};
        for (size_t index = 0; index < sizeof(invalid) / sizeof(invalid[0]); ++index)
            assert(tts_get_voice_text(invalid[index]) == NULL);
        assert(!spoken_count && !history_count && !spell_calls);
        assert(!memcmp(before_strings, voice_strings, sizeof(before_strings)));
        assert(!memcmp(before_offsets, voice_offsets, sizeof(before_offsets)));
        assert(!fixture_actual_tts_speak_id(VOICE_OF, false));
        assert(spoken_count == 1 && !strcmp(spoken_text[0], position_labels[language][0]) && !text_enqueued[0]);
        voice_offsets[voice_index(VOICE_OF)] = UINT32_MAX;
        assert(tts_get_voice_text(VOICE_OF) == NULL);
        assert(fixture_actual_tts_speak_id(VOICE_OF, true) == -1 && spoken_count == 1);
        snprintf((char *)voice_strings + 64, sizeof(voice_strings) - 64, "%s", row_labels[language][1]);
        voice_offsets[1] = 64;
        assert(!strcmp(tts_get_voice_text(1), row_labels[language][1]));
        assert(!fixture_actual_tts_speak_id(1, true));
        assert(spoken_count == 2 && !strcmp(spoken_text[1], row_labels[language][1]) && text_enqueued[1]);
        voice_offsets[voice_index(VOICE_OF)] = 0;
        voice_strings[0] = '\0';
        assert(tts_get_voice_text(VOICE_OF) != NULL && !*tts_get_voice_text(VOICE_OF));
    }
}

static void position_mode_matrix(void)
{
    static const bool expected[5][3] = {
        {true, true, true}, {true, false, true}, {false, true, false},
        {true, true, false}, {false, false, false}
    };
    for (int language = 0; language < 2; ++language)
    for (int mode = 0; mode < 5; ++mode)
    for (int source = 0; source < 3; ++source)
    for (int fallback = 0; fallback < 2; ++fallback)
    for (int dynamic = 0; dynamic < 2; ++dynamic)
    {
        struct gui_synclist list = setup();
        current_language = language;
        global_settings.tts_announce_position = mode;
        global_settings.tts_announce_dynamic = dynamic;
        list.position_source = source;
        assert(talk_list_position_enabled(&global_settings, list.position_source) == expected[mode][source]);
        list.selected_item = 19;
        list.callback_get_item_name = localized_row;
        if (fallback) list.callback_speak_item = NULL;
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1 + (int)expected[mode][source]);
        assert(spell_calls == fallback + (int)expected[mode][source]);
        if (expected[mode][source]) check_position(1, 20, 20);
    }
    for (int invalid = -1; invalid <= 5; invalid += 6)
    {
        struct gui_synclist list = setup();
        global_settings.tts_announce_position = invalid;
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1);
        global_settings.tts_announce_position = TTS_POSITION_EVERYWHERE;
        list.position_source = invalid < 0 ? -1 : 3;
        current_tick += HZ;
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1 && spell_calls == 0);
    }
}

static void construction_roles(void)
{
    struct gui_synclist list;
    memset(&list, 0xa5, sizeof(list));
    gui_synclist_init(&list, localized_row, NULL, false, 1, NULL);
    assert(list.position_source == LIST_POSITION_INTERFACE);
    list.position_source = LIST_POSITION_SLIDER;
    gui_synclist_init_display_settings(&list);
    assert(list.position_source == LIST_POSITION_SLIDER);
    struct simplelist_info info;
    memset(&info, 0xa5, sizeof(info));
    simplelist_info_init(&info, NULL, 1, NULL);
    assert(info.position_source == LIST_POSITION_INTERFACE);
    info.position_source = LIST_POSITION_FILE;
    list = fixture_simplelist_construct(&info);
    assert(list.position_source == LIST_POSITION_FILE);
    struct gui_synclist built[] = {
        fixture_construct_option(F_T_INT | F_T_SOUND), fixture_construct_option(F_T_INT | F_INT_SETTING),
        fixture_construct_option(F_T_INT | F_TABLE_SETTING), fixture_construct_option(F_BOOL_SETTING),
        fixture_construct_option(F_T_INT | F_CHOICE_SETTING),
        fixture_construct_option(F_T_INT | F_CHOICE_SETTING | F_INT_SETTING),
        fixture_construct_tree(false), fixture_construct_tree(true),
        fixture_construct_folder(), fixture_construct_mask(), fixture_construct_plugin_folder(),
        fixture_construct_random_folder(), fixture_construct_puzzle()
    };
    static const enum list_position_source expected[] = {
        LIST_POSITION_SLIDER, LIST_POSITION_SLIDER, LIST_POSITION_SLIDER,
        LIST_POSITION_INTERFACE, LIST_POSITION_INTERFACE, LIST_POSITION_INTERFACE,
        LIST_POSITION_FILE, LIST_POSITION_INTERFACE,
        LIST_POSITION_FILE, LIST_POSITION_INTERFACE, LIST_POSITION_FILE,
        LIST_POSITION_FILE, LIST_POSITION_INTERFACE
    };
    for (unsigned int index = 0; index < sizeof(built) / sizeof(built[0]); ++index)
    {
        list = setup();
        assert(built[index].position_source == expected[index]);
        list.position_source = built[index].position_source;
        global_settings.tts_announce_position = TTS_POSITION_EXCEPT_SLIDERS;
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1 + (expected[index] != LIST_POSITION_SLIDER));
        current_tick += HZ;
        global_settings.tts_announce_position = TTS_POSITION_FILES;
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1 + (expected[index] == LIST_POSITION_FILE));
    }
}

int main(int argc, char **argv)
{
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
#endif
    assert(argc == 2);
    struct gui_synclist list = setup();
    const char *scenario = argv[1];
    if (!strcmp(scenario, "position-mode-matrix"))
        position_mode_matrix();
    else if (!strcmp(scenario, "construction-roles"))
        construction_roles();
    else if (!strncmp(scenario, "rapid-wrap-", strlen("rapid-wrap-")))
        rapid_wrap(scenario);
    else if (!strncmp(scenario, "position-rapid-", strlen("position-rapid-")))
        position_rapid(scenario);
    else if (!strncmp(scenario, "position-", strlen("position-")))
        position_case(scenario);
    else if (!strcmp(scenario, "voice-text-lookup"))
        voice_text_lookup();
    else if (!strcmp(scenario, "blocked-every-press"))
    {
        for (int press = 0; press < 20; ++press) move(&list, -1, false, false, false);
        assert(list.selected_item == 0 && sounds == 20 && clicks == 0 && boundary_count == 20);
        assert(spoken_count == 20);
        list.selected_item = 19;
        for (int press = 0; press < 20; ++press) move(&list, 1, false, true, false);
        assert(list.selected_item == 19 && sounds == 40 && boundary_count == 40 && spoken_count == 40);
    }
    else if (!strcmp(scenario, "wrapped-order"))
    {
        global_settings.list_wraparound = true;
        list.selected_item = 19;
        move(&list, 1, true, true, false);
        assert(list.selected_item == 0 && sounds == 1 && clicks == 0 && spoken_count == 2);
        assert(utterances[0] == LANG_ACCESSIBILITY_LIST_END && utterances[1] == 100);
        current_tick += HZ;
        move(&list, -1, true, false, false);
        assert(list.selected_item == 19 && sounds == 2 && clicks == 0 && spoken_count == 2);
        assert(utterances[0] == LANG_ACCESSIBILITY_LIST_START && utterances[1] == 119);
    }
    else if (!strcmp(scenario, "arrival-is-not-crossing"))
    {
        list.selected_item = 18;
        move(&list, 1, false, false, false);
        assert(list.selected_item == 19 && !sounds && !boundary_count && clicks == 1);
        move(&list, 1, false, false, false);
        assert(sounds == 1 && boundary_count == 1 && clicks == 1);
        list.selected_item = 1;
        move(&list, -100, false, true, false);
        assert(list.selected_item == 0 && sounds == 1 && boundary_count == 1);
    }
    else if (!strcmp(scenario, "modes"))
    {
        for (int mode = 0; mode < 4; ++mode)
        {
            list = setup(); global_settings.list_boundary_feedback = mode;
            move(&list, -1, false, false, false);
            assert(sounds == (mode == 0 || mode == 1));
            assert(boundary_count == (mode == 0 || mode == 2));
            assert(!clicks);
        }
    }
    else if (!strcmp(scenario, "source-masks"))
    {
        for (int mask = 0; mask < 8; ++mask)
            for (int gesture = 0; gesture < 2; ++gesture)
            {
                list = setup(); source_mask = mask;
                move(&list, -1, false, gesture, false);
                assert(sounds == !!(mask & (gesture ? 2 : 1)));
                assert(boundary_count == 1 && !clicks);
                global_settings.keyclick = 0;
                move(&list, -1, false, gesture, false);
                assert(sounds == !!(mask & (gesture ? 2 : 1)) && boundary_count == 2);
            }
    }
    else if (!strcmp(scenario, "repeat-policy"))
    {
        move(&list, -1, false, false, true);
        assert(!sounds && boundary_count == 1);
        global_settings.keyclick_repeats = true;
        move(&list, -1, false, false, true);
        assert(sounds == 1 && boundary_count == 2);
        global_settings.keyclick_repeats = false;
        move(&list, -1, false, false, false);
        assert(sounds == 2 && boundary_count == 3);
        move(&list, -1, false, true, true);
        assert(sounds == 2 && boundary_count == 4);
    }
    else if (!strcmp(scenario, "list-local-policy"))
    {
        list.keyclick = false; list.talk_menu = false;
        move(&list, -1, false, false, false);
        assert(!sounds && !boundary_count);
        list.keyclick = list.talk_menu = true; disabled = true;
        move(&list, -1, false, false, false);
        assert(sounds == 1 && !boundary_count);
        disabled = false; global_settings.tts_enabled = false;
        move(&list, -1, false, false, false);
        assert(sounds == 2 && !boundary_count);
        global_settings.talk_menu = true;
        move(&list, -1, false, false, false);
        assert(sounds == 3 && boundary_count == 1);
    }
    else if (!strcmp(scenario, "empty-and-single"))
    {
        list.nb_items = 0;
        move(&list, -1, false, false, false);
        assert(!sounds && !boundary_count && !clicks);
        list.nb_items = 1;
        move(&list, 1, false, false, false);
        move(&list, -1, false, true, false);
        assert(sounds == 2 && boundary_count == 2 && !list.selected_item);
    }
    else if (!strcmp(scenario, "multi-line-and-overflow"))
    {
        list.nb_items = 8; list.selected_size = 3;
        move(&list, INT_MAX, true, false, false);
        assert(list.selected_item == 6 && !boundary_count);
        move(&list, INT_MAX, true, false, false);
        assert(list.selected_item == 6 && boundary_count == 1);
        move(&list, INT_MIN, true, false, false);
        assert(list.selected_item == 0 && boundary_count == 1);
        global_settings.list_wraparound = true;
        move(&list, INT_MIN, true, false, false);
        assert(list.selected_item == 6 && boundary_count == 2);
    }
    else if (!strcmp(scenario, "endpoints"))
    {
        list.selected_item = 8;
        gui_synclist_select_endpoint(&list, ACTION_LIST_LAST, SCREEN_MAIN);
        assert(list.selected_item == 19 && !sounds && !boundary_count);
        current_tick += HZ;
        gui_synclist_select_endpoint(&list, ACTION_LIST_FIRST, SCREEN_MAIN);
        assert(list.selected_item == 0 && utterances[0] == 100);
        current_tick += HZ;
        gui_synclist_select_endpoint(&list, ACTION_LIST_FIRST, SCREEN_MAIN);
        assert(list.selected_item == 0 && spoken_count == 1);
    }
    else if (!strcmp(scenario, "page-endpoints"))
    {
        list.start_item[0] = 7; list.start_item[1] = 14;
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_FIRST, SCREEN_MAIN);
        assert(list.selected_item == 7);
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_LAST, SCREEN_MAIN);
        assert(list.selected_item == 11);
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_LAST, SCREEN_REMOTE);
        assert(list.selected_item == 16);
        list.start_item[0] = 19;
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_LAST, SCREEN_MAIN);
        assert(list.selected_item == 19);
        list.nb_items = 8; list.selected_size = 3; list.start_item[0] = 1;
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_FIRST, SCREEN_MAIN);
        assert(list.selected_item == 3);
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_LAST, SCREEN_MAIN);
        assert(list.selected_item == 3);
        list.start_item[0] = INT_MAX;
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_FIRST, SCREEN_MAIN);
        assert(list.selected_item == 6);
        list.nb_items = INT_MAX; list.selected_size = INT_MAX - 1;
        gui_synclist_select_endpoint(&list, ACTION_LIST_PAGE_FIRST, SCREEN_MAIN);
        assert(list.selected_item == INT_MAX - 1);
    }
    else if (!strcmp(scenario, "boundary-to-row") || !strcmp(scenario, "boundary-to-muted-row"))
    {
        bool muted = !strcmp(scenario, "boundary-to-muted-row");
        for (int press = 0; press < 20; ++press) move(&list, -1, false, false, false);
        assert(spoken_count == 20 && boundary_count == 20);
        if (muted)
        {
            list.talk_menu = false;
            list.callback_speak_item = NULL;
        }
        move(&list, 1, false, false, false);
        assert(list.selected_item == 1 && spoken_count == !muted);
        if (!muted) assert(utterances[0] == 101);
        assert(!list.boundary_speech_pending);
        assert(sounds == 20 && boundary_count == 20);
    }
    else if (!strcmp(scenario, "live-preferences"))
    {
        global_settings.tts_enabled = false;
        global_settings.keyclick = 0;
        gui_synclist_init_display_settings(&list);
        gui_synclist_speak_item(&list);
        assert(!spoken_count && list.talk_menu && list.keyclick && list.wraparound);
        global_settings.tts_enabled = true;
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1 && utterances[0] == 100);
        global_settings.keyclick = 2;
        global_settings.list_wraparound = true;
        current_tick += HZ;
        move(&list, -1, list.wraparound, false, false);
        assert(list.selected_item == 19 && sounds == 1 && boundary_count == 1);
        assert(utterances[0] == LANG_ACCESSIBILITY_LIST_START && utterances[1] == 119);
        global_settings.list_wraparound = false;
        move(&list, 1, list.wraparound, false, false);
        assert(list.selected_item == 19 && sounds == 2 && boundary_count == 2);
    }
    else if (!strcmp(scenario, "voice-only-row") || !strcmp(scenario, "visual-label-row"))
    {
        int label = !strcmp(scenario, "voice-only-row") ? VOICE_BLANK : 1;
        list.callback_speak_item = NULL;
        list.callback_get_item_name = name_row;
        list.data = ID2P(label);
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1 && utterances[0] == label);
    }
    else if (!strcmp(scenario, "literal-and-empty-rows"))
    {
        list.callback_speak_item = NULL;
        list.callback_get_item_name = name_row;
        list.data = "21";
        gui_synclist_speak_item(&list);
        assert(spoken_count == 1 && utterances[0] == 121);
        current_tick += HZ;
        list.data = "";
        gui_synclist_speak_item(&list);
        assert(!spoken_count);
        current_tick += HZ;
        list.data = NULL;
        gui_synclist_speak_item(&list);
        assert(!spoken_count);
    }
    else if (!strcmp(scenario, "deferred-boundary-idle"))
    {
        list.selected_item = 18;
        list.last_talked_tick = current_tick;
        move(&list, 1, false, false, false);
        assert(list.scheduled_talk_tick);
        move(&list, 1, false, false, false);
        assert(spoken_count == 1 && utterances[0] == LANG_ACCESSIBILITY_LIST_END);
        current_tick += HZ;
        assert(!fixture_speak_pending(&list));
        assert(spoken_count == 1 && utterances[0] == LANG_ACCESSIBILITY_LIST_END);
        assert(!list.scheduled_talk_tick && list.boundary_speech_pending);
    }
    else if (!strcmp(scenario, "deferred-wrap-cancel") || !strcmp(scenario, "deferred-wrap-idle"))
    {
        global_settings.list_wraparound = true;
        list.selected_item = 19;
        list.last_talked_tick = current_tick;
        move(&list, 1, true, false, false);
        assert(list.selected_item == 0 && !list.scheduled_talk_tick);
        assert(spoken_count == 2 && utterances[0] == LANG_ACCESSIBILITY_LIST_END && utterances[1] == 100);
        move(&list, 1, true, false, false);
        assert(!spoken_count && list.scheduled_talk_tick && !force_enqueue_next);
        bool cancel = !strcmp(scenario, "deferred-wrap-cancel");
        if (cancel)
        {
            move(&list, 1, true, false, false);
            assert(!spoken_count && !force_enqueue_next);
        }
        current_tick += HZ;
        assert(!fixture_speak_pending(&list));
        assert(spoken_count == 1);
        assert(utterances[0] == (cancel ? 102 : 101));
        assert(!list.scheduled_talk_tick && !list.boundary_speech_pending && !force_enqueue_next);
    }
    else if (!strcmp(scenario, "wrapped-silent-row") || !strcmp(scenario, "wrapped-failing-row"))
    {
        global_settings.list_wraparound = true;
        list.selected_item = 19;
        list.callback_speak_item = !strcmp(scenario, "wrapped-failing-row") ? failing_row : silent_row;
        move(&list, 1, true, false, false);
        assert(spoken_count == 1 && utterances[0] == LANG_ACCESSIBILITY_LIST_END);
        assert(!force_enqueue_next);
        list.callback_speak_item = speak_row;
        move(&list, 1, true, false, false);
        assert(!spoken_count && !force_enqueue_next);
        current_tick += HZ;
        assert(!fixture_speak_pending(&list));
        assert(spoken_count == 1 && utterances[0] == 101);
    }
    else if (!strcmp(scenario, "deferred-sound-wrap"))
    {
        global_settings.list_boundary_feedback = 1;
        global_settings.list_wraparound = true;
        list.selected_item = 19;
        list.last_talked_tick = current_tick;
        move(&list, 1, true, false, false);
        assert(!list.scheduled_talk_tick && !list.boundary_speech_pending);
        assert(spoken_count == 1 && utterances[0] == 100 && !force_enqueue_next && sounds == 1);
        move(&list, 1, true, false, false);
        assert(!spoken_count && !force_enqueue_next && list.scheduled_talk_tick);
        current_tick += HZ;
        assert(!fixture_speak_pending(&list));
        assert(spoken_count == 1 && utterances[0] == 101 && sounds == 1);
    }
    else if (!strcmp(scenario, "cross-list-prefix"))
    {
        global_settings.list_wraparound = true;
        list.selected_item = 19;
        list.last_talked_tick = current_tick;
        move(&list, 1, true, false, false);
        assert(!list.scheduled_talk_tick && !list.boundary_speech_pending);
        assert(spoken_count == 2 && utterances[0] == LANG_ACCESSIBILITY_LIST_END &&
               utterances[1] == 100 && !force_enqueue_next);
        struct gui_synclist other = list;
        other.boundary_speech_pending = false;
        other.scheduled_talk_tick = other.last_talked_tick = 0;
        other.selected_item = 5;
        gui_synclist_speak_item(&other);
        assert(spoken_count == 1 && utterances[0] == 105 && !force_enqueue_next);
        gui_synclist_speak_item(&list);
        assert(!spoken_count && !list.boundary_speech_pending && !force_enqueue_next);
        current_tick += HZ;
        assert(!fixture_speak_pending(&list));
        assert(spoken_count == 1 && utterances[0] == 100 && !force_enqueue_next);
    }
    else if (!strcmp(scenario, "keyclick-veto"))
    {
        const int actions[] = {ACTION_STD_PREV, ACTION_STD_PREVREPEAT, ACTION_LISTTREE_PGUP};
        for (unsigned int index = 0; index < sizeof(actions) / sizeof(actions[0]); ++index)
            assert(!gui_synclist_keyclick_callback(actions[index], &list));
        assert(gui_synclist_keyclick_callback(ACTION_STD_NEXT, &list));
        list.selected_item = 19;
        assert(!gui_synclist_keyclick_callback(ACTION_STD_NEXT, &list));
        assert(!gui_synclist_keyclick_callback(ACTION_STD_NEXTREPEAT, &list));
        assert(!gui_synclist_keyclick_callback(ACTION_LISTTREE_PGDOWN, &list));
    }
    else return 2;
    printf("PASS %s\n", scenario);
    return 0;
}
