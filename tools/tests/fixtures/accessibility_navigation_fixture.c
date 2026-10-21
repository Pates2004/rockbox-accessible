#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include "root_menu.h"

#define HZ 100
#define ARRAYLEN(values) (sizeof(values) / sizeof((values)[0]))
#define DEBUGF(...) ((void)0)
#define ID2P(value) ((char *)(uintptr_t)(value))
#define PLAYLIST_CONTROL_FILE "/fixture/playlist-control"
#define PLAYBACK_EVENT_TRACK_CHANGE 1
#define PLAYBACK_EVENT_START_PLAYBACK 2
enum { LANG_SHORTCUTS = 100, LANG_START_SCREEN, LANG_ONPLAY_MENU_TITLE,
       LANG_PREVIOUS_SCREEN, LANG_OPEN_PLUGIN, LANG_NOTHING_TO_RESUME,
       LANG_REPLAY_FINISHED_PLAYLIST };
enum current_activity { ACTIVITY_UNKNOWN, ACTIVITY_MAINMENU, ACTIVITY_SETTINGS,
    ACTIVITY_PLUGINBROWSER, ACTIVITY_SYSTEMSCREEN, ACTIVITY_WPS, ACTIVITY_CONTEXTMENU };
struct menu_item_ex { int unused; };
struct menu_item_ex file_menu, main_menu_, manage_settings, tagcache_menu,
    playback_settings, bookmark_settings_menu, plugin_menu, playlist_options,
    info_menu, system_menu, radio_settings_menu;
struct menu_item_ex root_menu_;
struct open_plugin_entry_t { int lang_id; };
static struct open_plugin_entry_t plugin_entry;
static struct fixture_tree_context { int out_of_tree; } tree_context;
static struct {
    int last_screen, last_browser, resume_index;
    unsigned long resume_crc32, resume_elapsed, resume_offset;
} global_status;
static struct { int start_in_screen; } global_settings;
static jmp_buf loop_exit;
static bool running_loop;
static int failure_line, operations, menu_calls, saved_status, selection_calls;
static int dispatched[16], dispatch_count, dispatch_return, chained_target;
static int expected_pending, dispatch_origin[16], status_at_dispatch[16];
static int activity_depth, pushes, pops, refreshless_pops;
static int audio_state, wps_calls, resume_calls, resume_result, start_calls;
static int resume_track_calls, speech_stops, splash_calls, last_splash;
static int resumed_index, answer, control_exists, wps_return;
static unsigned long resumed_crc32, resumed_elapsed, resumed_offset;

static void fail_at(int line)
{
    failure_line = line;
    if (running_loop) longjmp(loop_exit, 2);
}

#define CHECK(expression) do { if (!(expression)) { fail_at(__LINE__); return 1; } } while (0)
#define REQUIRE(expression) do { if (!(expression)) { fail_at(__LINE__); return; } } while (0)

ROOT_STATE
ROOT_ITEMS_TYPE
NAVIGATION_API

static void budget(void)
{
    if (++operations > 40) fail_at(__LINE__);
}

static void push_current_activity(enum current_activity activity)
{
    (void)activity;
    budget();
    ++pushes;
    ++activity_depth;
}

static void pop_current_activity(void)
{
    REQUIRE(activity_depth > 1);
    --activity_depth;
    ++pops;
}

static void pop_current_activity_without_refresh(void)
{
    pop_current_activity();
    ++refreshless_pops;
}

static int dispatch_screen(int screen)
{
    budget();
    if (dispatch_count >= 16) { fail_at(__LINE__); return GO_TO_ROOT; }
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    if (root_menu_navigation_pending() != (bool)expected_pending)
        fail_at(__LINE__);
#endif
    dispatched[dispatch_count] = screen;
    dispatch_origin[dispatch_count] = last_screen;
    status_at_dispatch[dispatch_count++] = global_status.last_screen;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    if (chained_target != GO_TO_PREVIOUS)
    {
        int target = chained_target;
        chained_target = GO_TO_PREVIOUS;
        if (!root_menu_request_screen(target)) fail_at(__LINE__);
    }
#endif
    return dispatch_return;
}

static int browser(void *parameter) { return dispatch_screen((int)(intptr_t)parameter); }
static int miscscrn(void *parameter)
{
    if (parameter == &main_menu_) return dispatch_screen(GO_TO_MAINMENU);
    if (parameter == &plugin_menu) return dispatch_screen(GO_TO_BROWSEPLUGINS);
    return dispatch_screen(GO_TO_SYSTEM_SCREEN);
}
static int playlist_view_catalog(void *parameter)
{ (void)parameter; return dispatch_screen(GO_TO_PLAYLISTS_SCREEN); }
static int playlist_view(void *parameter)
{ (void)parameter; return dispatch_screen(GO_TO_PLAYLIST_VIEWER); }
static int load_bmarks(void *parameter)
{ (void)parameter; return dispatch_screen(GO_TO_RECENTBMARKS); }
static int do_shortcut_menu(void *parameter)
{ (void)parameter; return dispatch_screen(GO_TO_SHORTCUTMENU); }
#if CONFIG_TUNER
static int radio(void *parameter) { (void)parameter; return dispatch_screen(GO_TO_FM); }
#endif

static void status_save(bool force) { (void)force; ++saved_status; }
static int get_selection(int screen) { ++selection_calls; return screen; }
static int do_menu(const struct menu_item_ex *menu, int *selected, void *parent, bool hide)
{
    (void)selected; (void)parent; (void)hide;
    if (menu != &root_menu_) fail_at(__LINE__);
    ++menu_calls;
    longjmp(loop_exit, 1);
}
static int load_context_screen(int selection) { (void)selection; return GO_TO_ROOT; }
static int load_plugin_screen(char *key) { (void)key; fail_at(__LINE__); return GO_TO_ROOT; }
static struct open_plugin_entry_t *open_plugin_get_entry(void) { return &plugin_entry; }
static struct fixture_tree_context *tree_get_context(void) { return &tree_context; }
static int audio_status(void) { return audio_state; }
static void talk_shutup(void) { ++speech_stops; }
static int gui_wps_show(void) { ++wps_calls; return wps_return; }
static int playlist_resume(void) { ++resume_calls; return resume_result; }
static void playlist_resume_track(int index, unsigned long crc32, unsigned long elapsed, unsigned long offset)
{
    ++resume_track_calls;
    resumed_index = index;
    resumed_crc32 = crc32;
    resumed_elapsed = elapsed;
    resumed_offset = offset;
}
static void playlist_start(int index, unsigned long elapsed, unsigned long offset)
{ (void)index; (void)elapsed; (void)offset; ++start_calls; }
static bool file_exists(const char *path) { (void)path; return control_exists; }
static bool yesno_pop(char *message) { (void)message; return answer; }
static void splash(int ticks, char *message)
{ (void)ticks; ++splash_calls; last_splash = (int)(uintptr_t)message; }
static void rootmenu_track_changed_callback(unsigned short event, void *data)
{ (void)event; (void)data; }
#if CONFIG_TUNER
static void rootmenu_start_playback_callback(unsigned short event, void *data)
{ (void)event; (void)data; }
#endif
static void add_event(unsigned short event, void (*callback)(unsigned short, void *))
{ (void)event; (void)callback; }

WPS_FUNCTION
DISPATCH_TABLE
LOAD_SCREEN_FUNCTION
IGNORE_BACK_FUNCTION
SETUP_FUNCTION
ROOT_FUNCTION

static void reset_fixture(void)
{
    memset(&global_status, 0, sizeof(global_status));
    global_status.last_screen = global_status.last_browser = GO_TO_ROOT;
    global_status.resume_index = -1;
    global_settings.start_in_screen = 1;
    next_screen = last_screen = GO_TO_ROOT;
    previous_music = GO_TO_WPS;
    dispatch_return = GO_TO_ROOT;
    chained_target = GO_TO_PREVIOUS;
    failure_line = operations = dispatch_count = menu_calls = saved_status = selection_calls = 0;
    expected_pending = activity_depth = pushes = pops = refreshless_pops = 0;
    audio_state = wps_calls = resume_calls = start_calls = resume_track_calls = speech_stops = 0;
    splash_calls = last_splash = resumed_index = answer = control_exists = 0;
    resumed_crc32 = resumed_elapsed = resumed_offset = 0;
    resume_result = 0;
    wps_return = GO_TO_ROOT;
    running_loop = false;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    root_menu_cancel_navigation();
#endif
}

static int run_root(void)
{
    running_loop = true;
    int result = setjmp(loop_exit);
    if (!result) root_menu();
    running_loop = false;
    CHECK(result == 1 && !failure_line);
    CHECK(activity_depth == 1);
    return 0;
}

int allowed_screens[] = {
    GO_TO_FILEBROWSER, GO_TO_WPS, GO_TO_MAINMENU, GO_TO_PLAYLISTS_SCREEN,
#ifdef HAVE_TAGCACHE
    GO_TO_DBBROWSER,
#endif
};

static int api_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    reset_fixture();
    CHECK(!root_menu_navigation_pending());
    CHECK(root_menu_take_navigation() == GO_TO_PREVIOUS);
    for (unsigned int index = 0; index < ARRAYLEN(allowed_screens); ++index)
    {
        int target = allowed_screens[index];
        CHECK(root_menu_request_screen(target));
        CHECK(root_menu_navigation_pending());
        CHECK(!root_menu_request_screen(target));
        CHECK(!root_menu_request_screen(allowed_screens[(index + 1) % ARRAYLEN(allowed_screens)]));
        CHECK(!root_menu_request_screen(GO_TO_PLUGIN));
        CHECK(root_menu_take_navigation() == target);
        CHECK(!root_menu_navigation_pending());
        CHECK(root_menu_take_navigation() == GO_TO_PREVIOUS);
        CHECK(root_menu_request_screen(target));
        root_menu_cancel_navigation();
        root_menu_cancel_navigation();
        CHECK(!root_menu_navigation_pending());
        CHECK(root_menu_take_navigation() == GO_TO_PREVIOUS);
    }
    for (int target = -32; target < NUM_ITEMS + 32; ++target)
    {
        bool allowed = false;
        for (unsigned int index = 0; index < ARRAYLEN(allowed_screens); ++index)
            allowed = allowed || target == allowed_screens[index];
        CHECK(root_menu_request_screen(target) == allowed);
        CHECK(root_menu_navigation_pending() == allowed);
        CHECK(root_menu_take_navigation() == (allowed ? target : GO_TO_PREVIOUS));
    }
    CHECK(!root_menu_request_screen(INT32_MIN));
    CHECK(!root_menu_request_screen(INT32_MAX));
#endif
    return 0;
}

static int dispatch_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    for (unsigned int index = 0; index < ARRAYLEN(allowed_screens); ++index)
    {
        reset_fixture();
        int target = allowed_screens[index];
        audio_state = 1;
        CHECK(root_menu_request_screen(target));
        CHECK(!run_root());
        CHECK(!root_menu_navigation_pending());
        CHECK(saved_status == 1 && menu_calls == 1);
        if (target == GO_TO_WPS)
            CHECK(wps_calls == 1 && speech_stops == 1 && !resume_calls);
        else
        {
            CHECK(dispatch_count == 1 && dispatched[0] == target);
            CHECK(status_at_dispatch[0] == target);
        }
        if (target == GO_TO_FILEBROWSER || target == GO_TO_PLAYLISTS_SCREEN
#ifdef HAVE_TAGCACHE
            || target == GO_TO_DBBROWSER
#endif
            )
            CHECK(global_status.last_browser == target);
        CHECK(global_status.last_screen == GO_TO_ROOT);
    }
#endif
    return 0;
}

static int chain_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    reset_fixture();
    chained_target = GO_TO_PLAYLISTS_SCREEN;
    CHECK(root_menu_request_screen(GO_TO_MAINMENU));
    CHECK(!run_root());
    CHECK(dispatch_count == 2 && dispatched[0] == GO_TO_MAINMENU && dispatched[1] == GO_TO_PLAYLISTS_SCREEN);
    CHECK(!root_menu_navigation_pending() && saved_status == 2 && menu_calls == 1);
#endif
    return 0;
}

static int cancellation_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    reset_fixture();
    CHECK(root_menu_request_screen(GO_TO_MAINMENU));
    root_menu_cancel_navigation();
    CHECK(!run_root());
    CHECK(!dispatch_count && !saved_status && menu_calls == 1);
#endif
    return 0;
}

static int return_case(int result)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    reset_fixture();
    dispatch_return = result;
    CHECK(root_menu_request_screen(GO_TO_MAINMENU));
    CHECK(!run_root());
    CHECK(dispatch_count == 1 && !root_menu_navigation_pending() && menu_calls == 1);
    CHECK(global_status.last_screen == GO_TO_ROOT);
#else
    (void)result;
#endif
    return 0;
}

static int resume_case(void)
{
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
    for (int state = 0; state < 7; ++state)
    {
        reset_fixture();
        if (state == 1 || state == 2) global_status.resume_index = 7;
        if (state == 2) resume_result = -1;
        if (state == 3 || state == 4) audio_state = state == 3 ? 1 : 3;
        if (state == 5 || state == 6) control_exists = true;
        if (state == 6) answer = true;
        global_status.resume_crc32 = 0xaabbccddUL;
        global_status.resume_elapsed = 12345;
        global_status.resume_offset = 67890;
        CHECK(root_menu_request_screen(GO_TO_WPS));
        CHECK(!run_root());
        CHECK(!root_menu_navigation_pending() && saved_status == 1);
        CHECK(wps_calls == (state == 1 || state == 3 || state == 4 || state == 6));
        CHECK(resume_calls == (state == 1 || state == 2 || state == 6));
        CHECK(resume_track_calls == (state == 1));
        CHECK(start_calls == (state == 6));
        CHECK(speech_stops == (state == 3 || state == 4));
        CHECK(splash_calls == (state == 0));
        if (state == 0) CHECK(last_splash == LANG_NOTHING_TO_RESUME);
        if (state == 1)
            CHECK(resumed_index == 7 && resumed_crc32 == 0xaabbccddUL &&
                  resumed_elapsed == 12345 && resumed_offset == 67890);
    }
#endif
    return 0;
}

static int startup_case(void)
{
    reset_fixture();
    global_settings.start_in_screen = GO_TO_WPS + 2;
    CHECK(!run_root());
    CHECK(!wps_calls && !saved_status && menu_calls == 1);
    reset_fixture();
    global_settings.start_in_screen = 0;
    global_status.last_screen = GO_TO_FILEBROWSER;
    CHECK(!run_root());
    CHECK(dispatch_count == 1 && dispatched[0] == GO_TO_FILEBROWSER);
    CHECK(saved_status == 1 && menu_calls == 1);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    int result = !strcmp(argv[1], "api") ? api_case() :
        !strcmp(argv[1], "dispatch") ? dispatch_case() :
        !strcmp(argv[1], "chain") ? chain_case() :
        !strcmp(argv[1], "cancel") ? cancellation_case() :
        !strcmp(argv[1], "previous") ? return_case(GO_TO_PREVIOUS) :
        !strcmp(argv[1], "usb") ? return_case(MENU_ATTACHED_USB) :
        !strcmp(argv[1], "exit") ? return_case(MENU_SELECTED_EXIT) :
        !strcmp(argv[1], "resume") ? resume_case() :
        !strcmp(argv[1], "startup") ? startup_case() : 2;
    if (failure_line) fprintf(stderr, "fixture check failed at line %d\n", failure_line);
    if (!result) puts("navigation checks passed");
    return result;
}
