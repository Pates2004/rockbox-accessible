#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define HZ 100
#define MAX_PATH 260
#define MAXBUFFER 1024
#define SIMPLELIST_MAX_LINES 32
#define SIMPLELIST_MAX_LINELENGTH 32
#define NB_SCREENS 1
#define FOR_NB_SCREENS(screen) for (int screen = 0; screen < NB_SCREENS; screen++)
#define MIN(left, right) ((left) < (right) ? (left) : (right))
#define MAX(left, right) ((left) > (right) ? (left) : (right))
#define TIME_BEFORE(left, right) ((int32_t)((uint32_t)(left) - (uint32_t)(right)) < 0)
#define TIME_AFTER(left, right) TIME_BEFORE(right, left)
#define ID2P(identifier) ((const char *)(uintptr_t)(4096 + (identifier)))
#define P2ID(text) (((uintptr_t)(text) >= 4096 && (uintptr_t)(text) < 4112) ? (long)(uintptr_t)(text) - 4096 : -1)
#define P2STR(text) resolve_text((const char *)(text))
#define str(identifier) coverage_language_text(identifier)
#define cond_talk_ids_fq(identifier) do { if (global_settings.talk_menu) talk_id(identifier, false); } while (0)
#define MENU_TYPE_MASK 15
#define MENU_DYNAMIC_DESC 32
#define TALK_ID(value, unit) (value)
#define talk_ids(enqueue, identifier, value) mock_talk_ids(enqueue, identifier, value)

enum { VOICE_EMPTY_LIST = 1, LANG_LOADING_PERCENT, UNIT_PERCENT,
       ACTION_REDRAW, ACTION_STD_OK, ACTION_STD_CANCEL, ACTION_TREE_WPS, CONTEXT_TREE,
       ALLOW_SOFTLOCK = 16, TIMEOUT_NOBLOCK, Icon_NOICON, SYS_USB_CONNECTED };
enum { MT_MENU, MT_RETURN_ID, MT_SETTING, MT_SETTING_W_TEXT, MT_FUNCTION_CALL };
enum { LANG_PLAYLIST_INSERT_COUNT = 8, LANG_ALL, LANG_OFF_ABORT, LANG_PLUGIN_CANT_OPEN };
enum { VOICE_OF = 12, LANG_TAGCACHE_INIT, LANG_BUILDING_DATABASE, LANG_PLAYLIST_SEARCH_MSG };
typedef const char *list_get_name(int, void *, char *, size_t);
typedef int list_speak_item(int, void *);
typedef int list_get_icon(int, void *);

struct gui_synclist {
    int position_source;
    int nb_items, selected_item, selected_size, offset_position[NB_SCREENS];
    bool talk_menu, boundary_speech_pending;
    long scheduled_talk_tick, last_talked_tick;
    void *data;
    list_get_name *callback_get_item_name;
    list_speak_item *callback_speak_item;
};
struct simplelist_info {
    int position_source;
    const char *title;
    int count, selection_size;
    bool scroll_all, hide_theme, speak_onshow;
    int timeout, selection;
    int (*action_callback)(int, struct gui_synclist *);
    int title_icon;
    list_get_icon *get_icon;
    list_get_name *get_name;
    list_speak_item *get_talk;
    void *callback_data;
};
struct text_message { const char **message_lines; int nb_lines; };
struct menu_get_name_and_icon {
    char *(*list_get_name)(int, void *, char *, size_t);
    list_speak_item *list_speak_item;
    void *list_get_name_data;
};
struct menu_callback_with_desc { const unsigned char *desc; };
struct menu_item_ex {
    int flags;
    const struct menu_item_ex **submenus;
    void *variable;
    const char **strings;
    const struct menu_get_name_and_icon *menu_get_name_and_icon;
    const struct menu_callback_with_desc *callback_and_desc;
};
static int current_subitems[8], current_subitems_count;
static struct { bool talk_menu; } global_settings;
static long current_tick;
#ifdef HAVE_ESPEAK
static bool available;
static bool tts_is_available(void) { return available; }
static const char *tts_get_voice_text(int32_t identifier)
{ assert(identifier == VOICE_OF); return "of"; }
static int tagcache_get_max_commit_step(void) { return 5; }
#endif
static char utterances[128][MAXBUFFER];
static bool enqueued[128];
static int speech_count, stops, callback_count, name_count, redraws, pending_redraws;
static const char *names[8];
static int callback_result;
static bool callback_silent;
static int setting_count, forced_enqueue;
static char drawn[MAXBUFFER];

static const char *coverage_language_text(int identifier)
{
    if (identifier == LANG_OFF_ABORT)
        return "Cancel";
    if (identifier == LANG_PLAYLIST_SEARCH_MSG)
        return "%d found %s";
    return "Cannot open %s";
}

static const char *resolve_text(const char *text)
{
    long identifier = P2ID(text);
    if (identifier == LANG_PLAYLIST_INSERT_COUNT)
        return "%d tracks %s";
    return identifier >= 0 ? "Localized label" : text;
}

static int record(const char *text, bool enqueue)
{
    assert(speech_count < 128);
    snprintf(utterances[speech_count], MAXBUFFER, "%s", text);
    enqueued[speech_count++] = enqueue;
    return 0;
}
static int talk_spell(const char *text, bool enqueue) { return record(text, enqueue); }
static void talk_id(long identifier, bool enqueue)
{
    char buffer[32];
    snprintf(buffer, sizeof(buffer), "id:%ld", identifier);
    record(buffer, enqueue);
}
static void mock_talk_ids(bool enqueue, int identifier, int value)
{
    assert(identifier == LANG_LOADING_PERCENT);
    char buffer[32];
    snprintf(buffer, sizeof(buffer), "loading:%d", value);
    record(buffer, enqueue);
}
static void talk_shutup(void) { stops++; }
#ifdef HAVE_ESPEAK
static void talk_force_shutup(void) { talk_shutup(); }
#endif
static void talk_force_enqueue_next(void) { forced_enqueue++; }
#ifdef HAVE_ESPEAK
static void talk_cancel_enqueue_next(void) { forced_enqueue = 0; }
#endif
static void talk_number(int number, bool enqueue)
{
    char buffer[32];
    snprintf(buffer, sizeof(buffer), "number:%d", number);
    record(buffer, enqueue);
}
static void talk_setting(void *variable) { assert(variable == names); setting_count++; }
static int voice_callback(int selected, void *data)
{
    assert(selected >= 0 && data == names);
    callback_count++;
    if (!callback_silent)
        record("callback", false);
    return callback_result;
}
static const char *name_callback(int selected, void *data, char *buffer, size_t size)
{
    assert(selected >= 0 && selected < 8 && data == names);
    name_count++;
    if (names[selected] && names[selected] != ID2P(2) && strcmp(names[selected], "buffer") == 0)
    {
        snprintf(buffer, size, "Formatted %d", selected);
        return buffer;
    }
    return names[selected];
}
static void gui_list_put_selection_on_screen(struct gui_synclist *list, int screen)
{ (void)list; (void)screen; }
static void gui_synclist_init(struct gui_synclist *list, list_get_name *name,
                              void *data, bool scroll, int size, void *parent)
{
    (void)scroll; (void)parent;
    memset(list, 0, sizeof(*list));
    list->selected_size = size;
    list->talk_menu = global_settings.talk_menu;
    list->callback_get_item_name = name;
    list->data = data;
}
static void gui_synclist_set_title(struct gui_synclist *list, const char *title, int icon)
{ (void)list; (void)title; (void)icon; }
static void gui_synclist_set_icon_callback(struct gui_synclist *list, list_get_icon *icon)
{ (void)list; (void)icon; }
static void gui_synclist_draw(struct gui_synclist *list) { (void)list; redraws++; }
static bool list_is_dirty(struct gui_synclist *list) { (void)list; return false; }
static void gui_synclist_scroll_stop(struct gui_synclist *list) { (void)list; }
static void sb_set_persistent_title(const char *title, int icon, int screen)
{ (void)title; (void)icon; (void)screen; }
static void viewportmanager_theme_enable(int screen, bool enable, void *parent)
{ (void)screen; (void)enable; (void)parent; }
static void viewportmanager_theme_undo(int screen, bool update)
{ (void)screen; (void)update; }
static void list_do_action(int context, int timeout, struct gui_synclist *list, int *action)
{
    (void)context; (void)timeout; (void)list;
    *action = pending_redraws-- > 0 ? ACTION_REDRAW : ACTION_STD_CANCEL;
    current_tick += HZ;
}
static int default_event_handler(int action) { return action; }
static void yield(void) {}
struct viewport { int unused; };
struct screen {
    int screen_type;
    struct viewport *(*set_viewport)(struct viewport *);
    void (*update_viewport)(void);
};
static struct viewport *set_viewport(struct viewport *viewport) { return viewport; }
static void update_viewport(void) {}
static struct screen screens[] = { { 0, set_viewport, update_viewport } };
static void viewport_set_defaults(struct viewport *viewport, int screen)
{ (void)viewport; (void)screen; }
static bool splash_internal(struct screen *screen, const char *format, va_list arguments,
                            struct viewport *viewport, int progress)
{
    (void)screen; (void)viewport; (void)progress;
    vsnprintf(drawn, sizeof(drawn), format, arguments);
    return true;
}
static void sleep(int ticks) { current_tick += ticks; }

#include "coverage_functions.h"

static void reset(void)
{
    current_tick = 1000;
    global_settings.talk_menu = true;
#ifdef HAVE_ESPEAK
    available = true;
    global_settings.tts_announce_position = TTS_POSITION_OFF;
    global_settings.tts_announce_dynamic = true;
#endif
    speech_count = stops = callback_count = name_count = redraws = pending_redraws = 0;
    callback_result = 0;
    callback_silent = false;
    setting_count = forced_enqueue = current_subitems_count = 0;
    drawn[0] = '\0';
    memset(names, 0, sizeof(names));
    simplelist_reset_lines();
    splash_progress_set_delay(0);
}

static struct gui_synclist make_list(void)
{
    struct gui_synclist list;
    gui_synclist_init(&list, name_callback, names, false, 1, NULL);
    list.nb_items = 4;
    names[0] = "Polski katalog";
    names[1] = "buffer";
    names[2] = "Third item";
    names[3] = "Fourth item";
    return list;
}

static void test_lists(void)
{
    reset();
    struct gui_synclist list = make_list();
    gui_synclist_set_voice_callback(&list, voice_callback);
    gui_synclist_speak_item(&list);
    assert(callback_count == 1 && name_count == 0 && speech_count == 1);
    current_tick += HZ;
    callback_silent = true;
    callback_result = -1;
    _gui_synclist_speak_item(&list, false);
    assert(callback_count == 2 && name_count == 0 && speech_count == 1);
    list.talk_menu = false;
    current_tick += HZ;
    gui_synclist_select_item(&list, 1);
    assert(callback_count == 3);

    reset();
    list = make_list();
    list.talk_menu = false;
    gui_synclist_select_item(&list, 1);
    _gui_synclist_speak_item(&list, false);
    assert(speech_count == 0 && name_count == 0 && stops == 0);
    list.talk_menu = true;
    global_settings.talk_menu = false;
    list.scheduled_talk_tick = current_tick + HZ;
    _gui_synclist_speak_item(&list, false);
    assert(speech_count == 0 && name_count == 0 && list.scheduled_talk_tick == 0);
    global_settings.talk_menu = true;
#ifdef HAVE_ESPEAK
    available = false;
    gui_synclist_speak_item(&list);
    assert(speech_count == 0 && name_count == 0 && stops == 0);
    available = true;
#endif
    gui_synclist_speak_item(&list);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], "Formatted 1") == 0);
    current_tick++;
    gui_synclist_select_item(&list, 2);
    current_tick++;
    gui_synclist_select_item(&list, 3);
    assert(speech_count == 1 && list.scheduled_talk_tick > current_tick);
    current_tick = list.scheduled_talk_tick + 1;
    _gui_synclist_speak_item(&list, false);
    assert(speech_count == 2 && strcmp(utterances[1], "Fourth item") == 0);
    assert(list.scheduled_talk_tick == 0);
#else
    assert(speech_count == 0 && name_count == 0);
#endif
    list.nb_items = 0;
    list.scheduled_talk_tick = current_tick + HZ;
    _gui_synclist_speak_item(&list, false);
    assert(list.scheduled_talk_tick == 0);
    int previous = speech_count;
    gui_synclist_speak_item(&list);
    assert(speech_count == previous + 1 && strcmp(utterances[previous], "id:1") == 0);
    list.nb_items = 4;
    list.selected_item = -1;
    _gui_synclist_speak_item(&list, false);
    list.selected_item = 4;
    _gui_synclist_speak_item(&list, false);
    assert(speech_count == previous + 1);

#ifdef HAVE_ESPEAK
    reset();
    list = make_list();
    list.selected_size = 2;
    gui_synclist_speak_item(&list);
    assert(speech_count == 2 && enqueued[0] && enqueued[1]);
    current_tick += HZ;
    list.selected_item = 3;
    gui_synclist_speak_item(&list);
    assert(speech_count == 3);
    current_tick += HZ;
    list.selected_item = 0;
    names[0] = NULL;
    names[1] = "";
    gui_synclist_speak_item(&list);
    assert(speech_count == 3);
    current_tick += HZ;
    names[0] = ID2P(2);
    names[1] = "Za\305\274\303\263\305\202\304\207";
    gui_synclist_speak_item(&list);
    assert(speech_count == 5 && strcmp(utterances[3], "id:2") == 0);
    assert(strcmp(utterances[4], names[1]) == 0);
#endif
    puts("lists: callback authority, menu gating, legacy silence, debounce, bounds, grouped labels");
}

static int populate_list(int action, struct gui_synclist *list)
{
    (void)list;
    if (action == ACTION_REDRAW)
    {
        simplelist_reset_lines();
        simplelist_addline("Files: %d", 42);
        simplelist_addline("Second line");
    }
    return action;
}

static void test_simplelists(void)
{
    reset();
    struct simplelist_info info;
    simplelist_info_init(&info, NULL, 0, NULL);
    simplelist_addline("Entry %d", 12);
    assert(simplelist_get_line_count() == 1);
    assert(strcmp(simplelist_static_getname(0, NULL, NULL, 0), "Entry 12") == 0);
    simplelist_reset_lines();
    for (int line = 0; line < SIMPLELIST_MAX_LINES + 10; line++)
        simplelist_addline("Entry %d", line);
    assert(simplelist_get_line_count() == SIMPLELIST_MAX_LINES);
    assert(strcmp(simplelist_text[31], "Entry 31") == 0);
    simplelist_setline("Overflow");
    assert(simplelist_get_line_count() == SIMPLELIST_MAX_LINES);
    simplelist_reset_lines();
    char huge[4096];
    memset(huge, 'x', sizeof(huge) - 1);
    huge[sizeof(huge) - 1] = '\0';
    simplelist_addline("%s", huge);
    assert(simplelist_get_line_count() == 1 && simplelist_line_remaining == 0);
    assert(strlen(simplelist_text[0]) == sizeof(simplelist_buffer) - 1);
    simplelist_addline("Cannot fit");
    assert(simplelist_get_line_count() == 1);
    simplelist_info_init(&info, NULL, 0, NULL);
    simplelist_addline("Reset");
    assert(simplelist_get_line_count() == 1 && strcmp(simplelist_text[0], "Reset") == 0);

    reset();
    simplelist_info_init(&info, NULL, 0, NULL);
    info.action_callback = populate_list;
    pending_redraws = 8;
    assert(!simplelist_show_list(&info));
    assert(redraws == 9);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], "Files: 42") == 0);
#else
    assert(speech_count == 0);
#endif
    reset();
    simplelist_info_init(&info, NULL, 0, NULL);
    info.action_callback = populate_list;
    info.selection = 1;
    info.speak_onshow = false;
    assert(!simplelist_show_list(&info));
    assert(speech_count == 0);
    reset();
    simplelist_info_init(&info, NULL, 0, NULL);
    info.action_callback = populate_list;
    info.selection = 1;
    assert(!simplelist_show_list(&info));
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], "Second line") == 0);
#else
    assert(speech_count == 0);
#endif
    puts("simplelists: capacity, formatting truncation, reset, generated first item, redraws, speak_onshow");
}

static void test_dialogs(void)
{
    reset();
    const char *lines[] = { NULL, "", ID2P(2), "Delete Report.txt?", ID2P(3) };
    struct text_message message = { lines, 5 };
    talk_text_message(&message, false);
    assert(strcmp(utterances[0], "id:2") == 0 && !enqueued[0]);
#ifdef HAVE_ESPEAK
    assert(speech_count == 3 && strcmp(utterances[1], "Delete Report.txt?") == 0);
    assert(enqueued[1] && enqueued[2]);
    available = false;
#else
    assert(speech_count == 2 && enqueued[1]);
#endif
    speech_count = 0;
    talk_text_message(&message, false);
    assert(speech_count == 2 && strcmp(utterances[1], "id:3") == 0);
    reset();
    const char *raw[] = { "", "Raw question?", "filename.txt" };
    message.message_lines = raw;
    message.nb_lines = 3;
    bool repeat = true;
    long next_tick = current_tick - 1;
    coverage_dialog_tick(&message, false, &repeat, &next_tick);
    assert(speech_count == 0 && repeat);
    coverage_dialog_tick(&message, true, &repeat, &next_tick);
    for (int redraw = 0; redraw < 20; redraw++)
    {
        current_tick += 6 * HZ;
        coverage_dialog_tick(&message, true, &repeat, &next_tick);
    }
#ifdef HAVE_ESPEAK
    assert(speech_count == 2 && !enqueued[0] && enqueued[1] && !repeat);
#else
    assert(speech_count == 0 && repeat);
#endif
    reset();
    const char *localized[] = { ID2P(2) };
    message.message_lines = localized;
    message.nb_lines = 1;
#ifdef HAVE_ESPEAK
    available = false;
#endif
    repeat = true;
    next_tick = current_tick - 1;
    coverage_dialog_tick(&message, true, &repeat, &next_tick);
    current_tick += 6 * HZ;
    coverage_dialog_tick(&message, true, &repeat, &next_tick);
    assert(speech_count == 2 && repeat);
    puts("dialogs: raw/ID/null/empty lines, enqueue order, legacy repetition, TTS question once");
}

static void progress(int current, int total, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    splash_progress_talk(current, total, format, arguments);
    va_end(arguments);
}

static void test_progress(void)
{
    reset();
    splash_progress_set_delay(HZ);
    assert(progress_next_tick == current_tick + HZ);
    global_settings.talk_menu = false;
    progress(5, 10, "Copying %s", "File");
    global_settings.talk_menu = true;
    progress(1, 0, "Invalid total");
    progress(1, -1, "Invalid total");
    assert(speech_count == 0);
    progress(1, 10, "\fCopying\n%s", "Report.txt");
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], " Copying Report.txt 10%") == 0);
    assert(!enqueued[0]);
    for (int frame = 0; frame < 100; frame++)
    {
        current_tick++;
        progress(2, 10, "Copying %s", "Next.txt");
    }
    assert(speech_count == 1);
    current_tick += 5 * HZ;
    progress(2, 10, "Copying %s", "Next.txt");
    assert(speech_count == 2 && strcmp(utterances[1], "Copying Next.txt 20%") == 0);
    current_tick += 6 * HZ;
    progress(2, 10, "Copying %s", "Next.txt");
    assert(speech_count == 2);
    progress(10, 10, "Finished %s", "Report.txt");
    progress(10, 10, "Finished %s", "Report.txt");
    assert(speech_count == 3 && strcmp(utterances[2], "Finished Report.txt 100%") == 0);
    splash_progress_set_delay(0);
    progress(INT_MAX, INT_MAX, "Large total");
    assert(strcmp(utterances[3], "Large total 100%") == 0);
    splash_progress_set_delay(0);
    progress(INT_MIN, INT_MAX, "Negative current");
    assert(strcmp(utterances[4], "Negative current 0%") == 0);
    splash_progress_set_delay(0);
    progress(INT_MAX, 1, "Past total");
    assert(strcmp(utterances[5], "Past total 100%") == 0);
    available = false;
    speech_count = 0;
    splash_progress_set_delay(0);
#else
    assert(speech_count == 1 && strcmp(utterances[0], "loading:10") == 0);
    speech_count = 0;
    splash_progress_set_delay(0);
#endif
    progress(INT_MAX, INT_MAX, "Unused format");
    assert(speech_count == 1 && strcmp(utterances[0], "loading:100") == 0);
    progress(1, 10, "Unused format");
    assert(speech_count == 1);
    current_tick += 6 * HZ;
    progress(INT_MIN, INT_MAX, "Unused format");
    assert(speech_count == 2 && strcmp(utterances[1], "loading:0") == 0);
    puts("progress: settings gate, formatting, cadence, deduplication, completion, integer bounds, legacy");
}

static char *menu_name_callback(int selected, void *data, char *buffer, size_t size)
{
    return (char *)name_callback(selected, data, buffer, size);
}

static void test_menus(void)
{
    reset();
    const char *strings[] = { "Raw menu item", "", ID2P(2) };
    struct menu_item_ex menu = { .flags = MT_RETURN_ID, .strings = strings };
    talk_menu_item(0, &menu);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], strings[0]) == 0);
#else
    assert(speech_count == 0);
#endif
    speech_count = 0;
    current_subitems[0] = 2;
    current_subitems_count = 1;
    talk_menu_item(0, &menu);
    assert(speech_count == 1 && strcmp(utterances[0], "id:2") == 0);
    talk_menu_item(1, &menu);
    assert(speech_count == 1);
    global_settings.talk_menu = false;
    talk_menu_item(0, &menu);
    assert(speech_count == 1);
    reset();
    names[0] = "buffer";
    struct menu_get_name_and_icon dynamic = { menu_name_callback, voice_callback, names };
    menu.flags = MT_RETURN_ID | MENU_DYNAMIC_DESC;
    menu.menu_get_name_and_icon = &dynamic;
    talk_menu_item(0, &menu);
    assert(callback_count == 1 && speech_count == 1 && name_count == 0);
    callback_silent = true;
    callback_result = -1;
    talk_menu_item(0, &menu);
    assert(callback_count == 2 && speech_count == 1 && name_count == 0);
    dynamic.list_speak_item = NULL;
    speech_count = 0;
    talk_menu_item(0, &menu);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], "Formatted 0") == 0);
    available = false;
    speech_count = 0;
    talk_menu_item(0, &menu);
    assert(speech_count == 0);
    available = true;
#else
    assert(speech_count == 0);
#endif
    names[0] = ID2P(2);
    speech_count = 0;
    talk_menu_item(0, &menu);
    assert(speech_count == 1 && strcmp(utterances[0], "id:2") == 0);
    names[0] = NULL;
    talk_menu_item(0, &menu);
    assert(speech_count == 1);

    struct menu_callback_with_desc description = { (const unsigned char *)ID2P(3) };
    struct menu_item_ex setting = { .flags = MT_SETTING, .variable = names };
    struct menu_item_ex submenu = { .flags = MT_RETURN_ID, .callback_and_desc = &description };
    const struct menu_item_ex *children[] = { &setting, &submenu, &menu };
    struct menu_item_ex parent = { .flags = MT_MENU, .submenus = children };
    speech_count = 0;
    talk_menu_item(0, &parent);
    assert(setting_count == 1 && speech_count == 0);
    setting.flags = MT_SETTING_W_TEXT;
    talk_menu_item(0, &parent);
    assert(setting_count == 2);
    talk_menu_item(1, &parent);
    assert(speech_count == 1 && strcmp(utterances[0], "id:3") == 0);
    names[2] = "Nested dynamic";
    talk_menu_item(2, &parent);
#ifdef HAVE_ESPEAK
    assert(speech_count == 2 && strcmp(utterances[1], names[2]) == 0);
#else
    assert(speech_count == 1);
#endif
    int previous = speech_count;
    global_settings.talk_menu = false;
    talk_menu_item(0, &parent);
    talk_menu_item(2, &parent);
    assert(speech_count == previous && setting_count == 2);
    global_settings.talk_menu = true;
    submenu.flags = MT_FUNCTION_CALL;
    description.desc = (const unsigned char *)"Raw submenu label";
    talk_menu_item(1, &parent);
#ifdef HAVE_ESPEAK
    assert(speech_count == previous + 1 && strcmp(utterances[previous], "Raw submenu label") == 0);
#else
    assert(speech_count == previous);
#endif
    puts("menus: raw/static/dynamic strings, callbacks, settings, hidden mapping, submenu descriptions, gate");
}

static void test_playlist_and_splashes(void)
{
    reset();
    splashf_silent(0, "Silent %d %s", 17, "redraw");
    assert(speech_count == 0 && forced_enqueue == 0 && strcmp(drawn, "Silent 17 redraw") == 0);
    splashf_silent(0, ID2P(2));
    assert(speech_count == 0 && forced_enqueue == 0 && strcmp(drawn, "Localized label") == 0);
    global_settings.talk_menu = false;
    splashf(0, "Speech disabled");
    assert(speech_count == 0);
    global_settings.talk_menu = true;
    display_playlist_count(0, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), false);
    assert(speech_count == 0);
    display_playlist_count(1, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), false);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], "1 tracks Cancel") == 0);
#else
    assert(speech_count == 2 && strcmp(utterances[0], "number:1") == 0);
#endif
    int previous = speech_count;
    for (int count = 2; count < 50; count++)
    {
        current_tick++;
        display_playlist_count(count, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), false);
    }
    assert(speech_count == previous && strcmp(drawn, "49 tracks Cancel") == 0);
    current_tick += 6 * HZ;
    display_playlist_count(100, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), false);
#ifdef HAVE_ESPEAK
    assert(speech_count == previous + 1 && strcmp(utterances[previous], "100 tracks Cancel") == 0);
#else
    assert(speech_count == previous + 2);
#endif
    previous = speech_count;
    display_playlist_count(200, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), true);
#ifdef HAVE_ESPEAK
    assert(speech_count == previous + 1 && strcmp(utterances[previous], "200 tracks Cancel") == 0);
#else
    assert(speech_count == previous + 3);
#endif
    previous = speech_count;
    global_settings.talk_menu = false;
    display_playlist_count(300, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), true);
    assert(speech_count == previous && strcmp(drawn, "300 tracks Cancel") == 0);
#ifdef HAVE_ESPEAK
    available = false;
    global_settings.talk_menu = true;
    display_playlist_count(400, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), true);
    assert(speech_count == previous + 3);
#endif
    puts("playlist/splash: natural count once, cadence, visual-only redraws, completion, legacy, gate");
}

static void test_plugin_errors(void)
{
    reset();
    assert(coverage_plugin_open_error() == -1);
#ifdef HAVE_ESPEAK
    assert(speech_count == 1 && strcmp(utterances[0], "Cannot open missing-plugin.rock") == 0);
    available = false;
    speech_count = 0;
    assert(coverage_plugin_open_error() == -1);
#endif
    assert(speech_count == 2 && strcmp(utterances[1], "missing-plugin.rock") == 0);
    speech_count = 0;
    global_settings.talk_menu = false;
    assert(coverage_plugin_open_error() == -1);
    assert(speech_count == 0);
    puts("plugin errors: formatted TTS once, legacy ID/name speech, menu gate");
}

#ifdef HAVE_ESPEAK
static void test_dynamic_announcements(void)
{
    for (int dynamic = 0; dynamic < 2; ++dynamic)
    {
        reset();
        global_settings.talk_menu = false;
        global_settings.tts_enabled = true;
        global_settings.tts_announce_dynamic = dynamic;
        progress(5, 10, "Copying %s", "Report.txt");
        assert(speech_count == dynamic);
        if (dynamic)
            assert(!strcmp(utterances[0], "Copying Report.txt 50%"));
        current_tick += 6 * HZ;
        progress(9, 10, "Copying %s", "Report.txt");
        assert(speech_count == 2 * dynamic);
        progress(10, 10, "Finished %s", "Report.txt");
        assert(speech_count == 2 * dynamic + 1);
        assert(!strcmp(utterances[speech_count - 1], "Finished Report.txt 100%"));
        progress(10, 10, "Finished %s", "Report.txt");
        assert(speech_count == 2 * dynamic + 1);
        speech_count = 0;
        current_tick += (dynamic + 1) * 60 * HZ;
        display_playlist_count(2, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), false);
        assert(speech_count == dynamic && !strcmp(drawn, "2 tracks Cancel"));
        current_tick += 6 * HZ;
        display_playlist_count(3, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), false);
        assert(speech_count == 2 * dynamic && !strcmp(drawn, "3 tracks Cancel"));
        display_playlist_count(3, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), true);
        assert(speech_count == 2 * dynamic + 1 && !strcmp(drawn, "3 tracks Cancel"));
        assert(!strcmp(utterances[speech_count - 1], "3 tracks Cancel"));
    }

    reset();
    global_settings.tts_enabled = true;
    global_settings.talk_menu = false;
    global_settings.tts_announce_dynamic = false;
    progress(2, 10, "Progress");
    assert(!speech_count);
    global_settings.tts_announce_dynamic = true;
    progress(2, 10, "Progress");
    assert(speech_count == 1 && !strcmp(utterances[0], "Progress 20%"));
    global_settings.tts_announce_dynamic = false;
    current_tick += 6 * HZ;
    progress(3, 10, "Progress");
    assert(speech_count == 1);
    progress(10, 10, "Progress");
    assert(speech_count == 2 && !strcmp(utterances[1], "Progress 100%"));
    puts("dynamic: OFF suppresses interim only, ON cadence, completion, live preference, visual updates");
}

static void test_dynamic_database_and_search(void)
{
    reset();
    global_settings.tts_enabled = true;
    global_settings.talk_menu = false;
    global_settings.tts_announce_dynamic = false;
    coverage_database_progress(8, 0);
    coverage_database_progress(8, 2);
    assert(!speech_count);
    global_settings.tts_announce_dynamic = true;
    coverage_database_progress(8, 0);
    assert(speech_count == 2 && !strcmp(utterances[0], "number:8"));
    assert(!strcmp(utterances[1], "id:14"));
    coverage_database_progress(8, 2);
    assert(speech_count == 2);
    current_tick += 8 * HZ;
    coverage_database_progress(8, 2);
    assert(speech_count == 6 && !strcmp(utterances[2], "id:13"));
    assert(!strcmp(utterances[3], "number:2") && !strcmp(utterances[4], "id:12"));
    assert(!strcmp(utterances[5], "number:5"));
    global_settings.tts_announce_dynamic = false;
    current_tick += 8 * HZ;
    coverage_database_progress(9, 0);
    assert(speech_count == 6);

    speech_count = 0;
    coverage_search_progress(1);
    assert(!speech_count && !strcmp(drawn, "1 found Cancel"));
    global_settings.tts_announce_dynamic = true;
    coverage_search_progress(2);
    assert(speech_count == 2 && !strcmp(drawn, "2 found Cancel"));
    assert(!strcmp(utterances[0], "number:2") && !strcmp(utterances[1], "id:15"));
    current_tick++;
    coverage_search_progress(3);
    assert(speech_count == 2 && !strcmp(drawn, "3 found Cancel"));
    global_settings.tts_announce_dynamic = false;
    current_tick += 6 * HZ;
    coverage_search_progress(4);
    assert(speech_count == 2 && !strcmp(drawn, "4 found Cancel"));
    global_settings.tts_announce_dynamic = true;
    coverage_search_progress(5);
    assert(speech_count == 4 && !strcmp(drawn, "5 found Cancel"));
    puts("dynamic database/search: actual gates, cadence, formatted silent redraw, no duplicate TTS");
}

static void test_dynamic_off_preserves_explicit_speech(void)
{
    reset();
    global_settings.tts_enabled = true;
    global_settings.talk_menu = false;
    global_settings.tts_announce_dynamic = false;
    struct gui_synclist list = make_list();
    gui_synclist_select_item(&list, 1);
    assert(speech_count == 1 && !strcmp(utterances[0], "Formatted 1"));
    const char *lines[] = {"Explicit question"};
    struct text_message question = {lines, 1};
    bool repeat = true;
    long tick = current_tick - 1;
    coverage_dialog_tick(&question, talk_menus_enabled(&global_settings), &repeat, &tick);
    assert(speech_count == 2 && !repeat && !strcmp(utterances[1], lines[0]));
    assert(coverage_plugin_open_error() == -1);
    assert(speech_count == 3 && !strcmp(utterances[2], "Cannot open missing-plugin.rock"));
    splashf(0, "Explicit warning %d", 17);
    assert(speech_count == 4 && !strcmp(utterances[3], "Explicit warning 17"));
    puts("dynamic OFF preserves explicit navigation, dialog, plugin error and warning speech");
}
#endif

int main(void)
{
    test_lists();
    test_simplelists();
    test_dialogs();
    test_progress();
    test_menus();
    test_playlist_and_splashes();
    test_plugin_errors();
#ifdef HAVE_ESPEAK
    test_dynamic_announcements();
    test_dynamic_database_and_search();
    test_dynamic_off_preserves_explicit_speech();
#endif
    puts("All coverage harness checks passed");
    return 0;
}
