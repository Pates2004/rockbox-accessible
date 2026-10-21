#include "hiby_bluetooth.h"
#include "hiby_connectivity.h"
#include "hiby_bluetooth_settings.h"
#include "hiby_bluetooth_service.h"
#include "bluetooth-ui-language.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HZ 100
#define HAVE_ESPEAK 1
#define CONTEXT_STD 0
#define ACTION_STD_CANCEL 10
#define ACTION_TREE_WPS 11
#define SYS_USB_CONNECTED 12
#define ACTION_NONE 0
#define ACTION_REDRAW 13
#define ACTION_STD_NEXT 14
#define ACTION_STD_PREV 15
#define ACTION_STD_OK 16
#define HIBY_BT_UI_WAIT_STEPS 4
#define HIBY_BT_UI_SETTLE_STEPS 3
#define TIME_AFTER(after, before) ((long)(before) - (long)(after) < 0)
static long current_tick;

struct gui_synclist
{
    int selected_item;
};

struct simplelist_info
{
    enum { LIST_POSITION_INTERFACE, LIST_POSITION_FILE, LIST_POSITION_SLIDER } position_source;
    const char *(*get_name)(int, void *, char *, size_t);
    int (*get_talk)(int, void *);
    int selection;
    const char *title;
    int count;
    void *data;
    int (*action_callback)(int, struct gui_synclist *);
};

struct list_step
{
    int title;
    int count;
    int selection;
    const char *first_name;
    int initial_selection;
    bool usb;
};

static struct hiby_bt_snapshot observed;
static struct hiby_bt_snapshot refreshed;
static struct hiby_connectivity_snapshot controller;
static struct list_step steps[32];
static size_t step_count;
static size_t step_position;
static int messages[128];
static size_t message_count;
static int spoken[2048];
static bool spoken_enqueue[2048];
static size_t spoken_count;
static char device_speech[128];
static char switch_text[512];
static enum hiby_bt_operation operations[8];
static size_t operation_count;
static char last_address[18];
static unsigned int power_requests;
static unsigned int bt_cancellations;
static unsigned int controller_cancellations;
static unsigned int action_count;
static unsigned int finish_after = 3;
static int requested_action;
static int busy_operation = -1;
static enum hiby_bt_error operation_error;
static enum hiby_connectivity_result power_result;
static bool reject_bt;
static bool reject_power;
static bool busy_power;
static bool never_finish;
static bool late_success;
static bool inhibited;
static bool bt_cancelled;
static bool power_cancelled;
static bool incomplete_power;
static bool initialized = true;
static int expected_requested_label = -1;
static int expected_observed_label = -1;
static bool menu_running;
#ifndef SIMULATOR
static unsigned int entry_refreshes;
#endif
static struct hiby_bt_snapshot entry_snapshot;
static int after_status_label = -1;
static bool live_power_menu;
static bool repeated_power_menu;
static int live_power_exit;
static unsigned int live_navigation;
static unsigned int live_completion;
static struct hiby_bt_preferences fixture_preferences = {
    .auto_mode = BLUETOOTH_RECONNECT_STARTUP_AND_LOSS,
    .retry_seconds = 120,
    .pause_on_loss = true,
    .announce = true
};
static struct hiby_bt_service_status service_status;
static int preferences_read_error;
static int preferences_write_error;
static unsigned int preference_writes;
static enum hiby_bt_preference written_preference;
static int written_value;
static bool automatic_operation;
static unsigned int automatic_cancellations;
static unsigned int automatic_cancel_checks;
static unsigned int preference_reads;
static bool modal_settings_probe;
static unsigned int modal_probe_count;
static unsigned int service_status_reads;

int hiby_bt_preferences_get(struct hiby_bt_preferences *result)
{
    ++preference_reads;
    *result = fixture_preferences;
    return preferences_read_error;
}

int hiby_bt_preferences_set(enum hiby_bt_preference preference, int value)
{
    ++preference_writes;
    written_preference = preference;
    written_value = value;
    if (preferences_write_error)
        return preferences_write_error;
    switch (preference)
    {
        case HIBY_BT_PREF_AUTOCONNECT:
            assert(value >= 0 && value <= 2);
            fixture_preferences.auto_mode = (enum bluetooth_reconnect_mode)value;
            break;
        case HIBY_BT_PREF_RETRY_SECONDS:
            assert(value == 30 || value == 60 || value == 120 || value == 300);
            fixture_preferences.retry_seconds = (unsigned int)value;
            break;
        case HIBY_BT_PREF_PAUSE_ON_LOSS:
            assert(value == 0 || value == 1);
            fixture_preferences.pause_on_loss = value != 0;
            break;
        case HIBY_BT_PREF_ANNOUNCE:
            assert(value == 0 || value == 1);
            fixture_preferences.announce = value != 0;
            break;
        default:
            assert(false);
    }
    ++fixture_preferences.generation;
    return 0;
}

void hiby_bluetooth_service_get_status(struct hiby_bt_service_status *status)
{
    ++service_status_reads;
    *status = service_status;
}

static int gui_synclist_get_sel_pos(struct gui_synclist *lists)
{
    return lists->selected_item;
}

static int get_action(int context, int timeout);

static const char *str(int identifier)
{
    assert(identifier >= 0 && (size_t)identifier < sizeof(test_language) / sizeof(test_language[0]));
    return test_language[identifier];
}

static int talk_id(int identifier, bool enqueue)
{
    assert(spoken_count < sizeof(spoken) / sizeof(spoken[0]));
    assert(test_voice_language[identifier][0]);
    spoken[spoken_count] = identifier;
    spoken_enqueue[spoken_count++] = enqueue;
    return 0;
}

static void splashf_silent(int ticks, const char *format, ...)
{
    (void)ticks;
    assert(!strcmp(format, "%s") || !strcmp(format, "%s: %s"));
    va_list arguments;
    va_start(arguments, format);
    const char *label = va_arg(arguments, const char *);
    if (!strcmp(format, "%s: %s"))
        assert(!strcmp(va_arg(arguments, const char *), device_speech));
    va_end(arguments);
    assert(message_count < sizeof(messages) / sizeof(messages[0]));
    assert(spoken_count);
    int identifier = spoken[spoken_count - 1];
    assert(!strcmp(label, str(identifier)));
    messages[message_count++] = identifier;
}

static void simplelist_info_init(struct simplelist_info *info, const char *title,
                                 int count, void *data)
{
    memset(info, 0, sizeof(*info));
    info->title = title;
    info->count = count;
    info->data = data;
}

static bool fixture_operation_waiting(void);

static bool simplelist_show_list(struct simplelist_info *info)
{
    assert(info->position_source == (!strcmp(info->title, str(LANG_HIBY_BT_RETRY_WINDOW)) ?
        LIST_POSITION_SLIDER : LIST_POSITION_INTERFACE));
    if (observed.busy && busy_operation >= 0 && info->action_callback && fixture_operation_waiting())
    {
        struct gui_synclist list = {0};
        if (modal_settings_probe)
        {
            list.selected_item = 5;
            assert(info->action_callback(ACTION_STD_OK, &list) == ACTION_NONE);
            assert(!preference_reads && !preference_writes && !automatic_cancel_checks);
            ++modal_probe_count;
        }
        for (unsigned int iteration = 0; iteration < 12; ++iteration)
        {
            list.selected_item = (list.selected_item + 1) % info->count;
            size_t before = spoken_count;
            info->get_talk(list.selected_item, info->data);
            assert(spoken_count > before);
            int action = get_action(CONTEXT_STD, HZ / 10);
            int result = info->action_callback(action, &list);
            if (result == SYS_USB_CONNECTED || result == ACTION_STD_CANCEL)
            {
                info->selection = -1;
                return result == SYS_USB_CONNECTED;
            }
            assert(result == ACTION_NONE || result == ACTION_REDRAW);
        }
        assert(!"Bluetooth wait failed to finish");
    }
    assert(step_position < step_count);
    const struct list_step *step = &steps[step_position++];
    if (after_status_label >= 0)
        expected_observed_label = step_position == 1 ? LANG_ON : after_status_label;
    assert(!strcmp(info->title, str(step->title)));
    assert(info->count == step->count);
    if (step->initial_selection >= 0)
        assert(info->selection == step->initial_selection);
    assert(info->get_name && info->get_talk);
    unsigned int cancel_checks_before = automatic_cancel_checks;
    struct gui_synclist list = { .selected_item = info->selection };
    if (info->action_callback)
        assert(info->action_callback(ACTION_REDRAW, &list) == ACTION_REDRAW);
    if (live_power_menu && controller.busy && info->action_callback &&
        !(repeated_power_menu && step_position == 2))
    {
        for (unsigned int iteration = 0; iteration < 3; ++iteration)
        {
            list.selected_item = (list.selected_item + 1) % info->count;
            size_t before = spoken_count;
            info->get_talk(list.selected_item, info->data);
            assert(spoken_count > before && !spoken_enqueue[before]);
            static const int navigation_labels[] = {
                LANG_HIBY_BT_TITLE, LANG_HIBY_BT_PAIRED_DEVICES, LANG_HIBY_BT_PAIR_NEW,
                LANG_HIBY_BT_DISCONNECT, LANG_HIBY_BT_STATUS, LANG_HIBY_BT_SETTINGS,
                LANG_HIBY_BT_CONNECT_LAST
            };
            assert(spoken[before] == navigation_labels[list.selected_item]);
            int action = live_power_exit ? live_power_exit : ACTION_STD_NEXT;
            assert(info->action_callback(action, &list) == action);
            assert(spoken_count >= before);
            ++live_navigation;
            if (live_power_exit)
                break;
            get_action(CONTEXT_STD, HZ / 10);
        }
        if (!live_power_exit)
        {
            assert(!controller.busy);
            int action = info->action_callback(ACTION_NONE, &list);
            assert(action == ACTION_REDRAW);
            ++live_completion;
        }
        else if (live_power_exit == SYS_USB_CONNECTED)
            return true;
    }
    char buffer[512];
    for (int position = 0; position < info->count; ++position)
    {
        const char *name = info->get_name(position, info->data, buffer, sizeof(buffer));
        assert(name && name[0]);
        if (!position && step->first_name)
            assert(strstr(name, step->first_name));
        bool power_row = !strcmp(info->title, str(LANG_HIBY_BT_TITLE)) && !position;
        if (power_row)
            snprintf(switch_text, sizeof(switch_text), "%s", name);
        size_t spoken_before = spoken_count;
        info->get_talk(position, info->data);
        if (!strcmp(info->title, str(LANG_HIBY_BT_TITLE)) && position > 0)
        {
            static const int expected[] = {
                LANG_HIBY_BT_TITLE, LANG_HIBY_BT_PAIRED_DEVICES, LANG_HIBY_BT_PAIR_NEW,
                LANG_HIBY_BT_DISCONNECT, LANG_HIBY_BT_STATUS, LANG_HIBY_BT_SETTINGS,
                LANG_HIBY_BT_CONNECT_LAST
            };
            assert(!strcmp(name, str(expected[position])));
            assert(spoken_count == spoken_before + 1);
            assert(spoken[spoken_before] == expected[position] && !spoken_enqueue[spoken_before]);
        }
        if (!strcmp(info->title, str(LANG_HIBY_BT_SETTINGS)))
        {
            static const int expected[] = {
                LANG_HIBY_BT_AUTOCONNECT, LANG_HIBY_BT_RETRY_WINDOW,
                LANG_HIBY_BT_LOSS_BEHAVIOR, LANG_HIBY_BT_ANNOUNCEMENTS,
                LANG_HIBY_BT_LAST_DEVICE
            };
            static const int auto_values[] = {
                LANG_OFF, LANG_HIBY_BT_AUTO_STARTUP, LANG_HIBY_BT_AUTO_STARTUP_LOSS
            };
            static const int retries[] = {
                LANG_HIBY_BT_RETRY_30, LANG_HIBY_BT_RETRY_60,
                LANG_HIBY_BT_RETRY_120, LANG_HIBY_BT_RETRY_300
            };
            int value = LANG_HIBY_BT_NO_LAST_DEVICE;
            if (position == 0)
                value = auto_values[fixture_preferences.auto_mode];
            if (position == 1)
                value = retries[fixture_preferences.retry_seconds == 30 ? 0 :
                    fixture_preferences.retry_seconds == 60 ? 1 : fixture_preferences.retry_seconds == 120 ? 2 : 3];
            if (position == 2)
                value = fixture_preferences.pause_on_loss ? LANG_HIBY_BT_LOSS_PAUSE : LANG_HIBY_BT_LOSS_CONTINUE;
            if (position == 3)
                value = fixture_preferences.announce ? LANG_ON : LANG_OFF;
            char expected_name[512];
            snprintf(expected_name, sizeof(expected_name), "%s: %s", str(expected[position]),
                position == 4 && fixture_preferences.last_address[0] ? fixture_preferences.last_address : str(value));
            assert(!strcmp(name, expected_name));
            assert(spoken[spoken_before] == expected[position] && !spoken_enqueue[spoken_before]);
            if (position == 4 && fixture_preferences.last_address[0])
            {
                assert(spoken_count == spoken_before + 1);
                assert(!strcmp(device_speech, fixture_preferences.last_address));
            }
            else
            {
                assert(spoken_count == spoken_before + 2);
                assert(spoken[spoken_before + 1] == value && spoken_enqueue[spoken_before + 1]);
            }
        }
        const int *option_labels = NULL;
        static const int auto_options[] = {
            LANG_OFF, LANG_HIBY_BT_AUTO_STARTUP, LANG_HIBY_BT_AUTO_STARTUP_LOSS
        };
        static const int retry_options[] = {
            LANG_HIBY_BT_RETRY_30, LANG_HIBY_BT_RETRY_60,
            LANG_HIBY_BT_RETRY_120, LANG_HIBY_BT_RETRY_300
        };
        static const int loss_options[] = { LANG_HIBY_BT_LOSS_PAUSE, LANG_HIBY_BT_LOSS_CONTINUE };
        static const int announce_options[] = { LANG_OFF, LANG_ON };
        static const int forget_options[] = { LANG_HIBY_BT_KEEP_DEVICE, LANG_HIBY_BT_REMOVE };
        if (!strcmp(info->title, str(LANG_HIBY_BT_AUTOCONNECT)))
            option_labels = auto_options;
        if (!strcmp(info->title, str(LANG_HIBY_BT_RETRY_WINDOW)))
            option_labels = retry_options;
        if (!strcmp(info->title, str(LANG_HIBY_BT_LOSS_BEHAVIOR)))
            option_labels = loss_options;
        if (!strcmp(info->title, str(LANG_HIBY_BT_ANNOUNCEMENTS)))
            option_labels = announce_options;
        if (!strcmp(info->title, str(LANG_HIBY_BT_REMOVE_CONFIRM)))
            option_labels = forget_options;
        if (option_labels)
        {
            assert(!strcmp(name, str(option_labels[position])));
            assert(spoken_count == spoken_before + 1);
            assert(spoken[spoken_before] == option_labels[position] && !spoken_enqueue[spoken_before]);
        }
        if (power_row && expected_requested_label >= 0)
        {
            char expected[512];
            snprintf(expected, sizeof(expected), "%s: %s (%s: %s%s%s)",
                     str(LANG_HIBY_BT_TITLE), str(expected_requested_label),
                     str(LANG_HIBY_BT_STATUS), str(expected_observed_label),
                     controller.airplane_mode ? ", " : "",
                     controller.airplane_mode ? str(LANG_HIBY_BT_AIRPLANE_MODE) : "");
            assert(!strcmp(name, expected));
            assert(spoken_count == spoken_before + (controller.airplane_mode ? 5u : 4u));
            assert(spoken[spoken_before] == LANG_HIBY_BT_TITLE);
            assert(!spoken_enqueue[spoken_before]);
            assert(spoken[spoken_before + 1] == expected_requested_label);
            assert(spoken[spoken_before + 2] == LANG_HIBY_BT_STATUS);
            assert(spoken[spoken_before + 3] == expected_observed_label);
            for (size_t offset = 1; offset < spoken_count - spoken_before; ++offset)
                assert(spoken_enqueue[spoken_before + offset]);
            if (controller.airplane_mode)
                assert(spoken[spoken_before + 4] == LANG_HIBY_BT_AIRPLANE_MODE);
        }
    }
    assert(!strcmp(info->get_name(-1, info->data, buffer, sizeof(buffer)), ""));
    assert(!strcmp(info->get_name(info->count, info->data, buffer, sizeof(buffer)), ""));
    assert(info->get_talk(-1, info->data) == 0);
    assert(info->get_talk(info->count, info->data) == 0);
    assert(automatic_cancel_checks == cancel_checks_before);
    info->selection = step->selection;
    if (info->action_callback && step->selection >= 0 && !step->usb)
    {
        list.selected_item = step->selection;
        int action = info->action_callback(ACTION_STD_OK, &list);
        if (action == ACTION_NONE)
            return simplelist_show_list(info);
        assert(action == ACTION_STD_OK);
    }
    return step->usb;
}

static bool tts_is_available(void) { return true; }
static void tts_speak(const char *text, size_t length, bool enqueue)
{
    (void)enqueue;
    assert(length < sizeof(device_speech));
    memcpy(device_speech, text, length);
    device_speech[length] = '\0';
}
static void talk_spell(const char *text, bool enqueue)
{
    tts_speak(text, strlen(text), enqueue);
}

static int get_action(int context, int timeout)
{
    assert(context == CONTEXT_STD && timeout > 0);
    current_tick += timeout;
    ++action_count;
    assert(action_count <= HIBY_BT_UI_WAIT_STEPS + HIBY_BT_UI_SETTLE_STEPS + 2);
    if (!never_finish && action_count >= finish_after)
    {
        if (observed.busy)
        {
            observed.busy = false;
            observed.error = bt_cancelled && !late_success ? HIBY_BT_CANCELLED : operation_error;
        }
        if (controller.busy)
        {
            controller.busy = false;
            controller.result = power_cancelled && !late_success ?
                HIBY_CONNECTIVITY_CANCELLED : power_result;
            ++controller.generation;
        }
    }
    return action_count == 1 ? requested_action : 0;
}

#ifndef SIMULATOR
bool hiby_bluetooth_init(void) { return initialized; }
void hiby_bluetooth_get_snapshot(struct hiby_bt_snapshot *snapshot) { *snapshot = observed; }
void hiby_bluetooth_cancel(void) { ++bt_cancellations; bt_cancelled = true; }
void hiby_bluetooth_set_inhibited(bool enabled)
{
    inhibited = enabled;
    if (enabled)
        hiby_bluetooth_cancel();
}
bool hiby_bluetooth_is_inhibited(void) { return inhibited; }
bool hiby_bluetooth_cancel_automatic(void)
{
    ++automatic_cancel_checks;
    if (!automatic_operation)
        return false;
    ++automatic_cancellations;
    automatic_operation = false;
    observed.busy = false;
    return true;
}

bool hiby_bluetooth_request(enum hiby_bt_operation operation, const char *address)
{
    assert(operation != HIBY_BT_ENABLE && operation != HIBY_BT_DISABLE);
    if (menu_running && !entry_refreshes && operation == HIBY_BT_REFRESH)
    {
        ++entry_refreshes;
        observed = entry_snapshot;
        return true;
    }
    assert(operation_count < sizeof(operations) / sizeof(operations[0]));
    operations[operation_count++] = operation;
    if (address)
        snprintf(last_address, sizeof(last_address), "%s", address);
    if (reject_bt)
        return false;
    if (operation == HIBY_BT_SCAN || operation == HIBY_BT_REFRESH)
        observed = refreshed;
    else
        observed.error = operation_error;
    observed.busy = (int)operation == busy_operation;
    return true;
}
#endif

bool hiby_connectivity_init(void) { return true; }
void hiby_connectivity_get_snapshot(struct hiby_connectivity_snapshot *snapshot)
{
    *snapshot = controller;
}
bool hiby_connectivity_set_bluetooth_enabled(bool enabled)
{
    ++power_requests;
    if (reject_power)
        return false;
    controller.bluetooth_desired = enabled;
#ifdef SIMULATOR
    controller.bluetooth = HIBY_CONNECTIVITY_UNAVAILABLE;
    controller.result = HIBY_CONNECTIVITY_NOT_AVAILABLE;
#else
    controller.bluetooth = incomplete_power ? HIBY_CONNECTIVITY_UNKNOWN :
        enabled && !controller.airplane_mode ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF;
    controller.result = enabled && controller.airplane_mode ? HIBY_CONNECTIVITY_INHIBITED : power_result;
    observed.enabled = controller.bluetooth == HIBY_CONNECTIVITY_ON;
    observed.power_known = controller.bluetooth == HIBY_CONNECTIVITY_ON ||
                           controller.bluetooth == HIBY_CONNECTIVITY_OFF;
    observed.error = HIBY_BT_OK;
#endif
    controller.busy = busy_power;
    ++controller.generation;
    return true;
}
void hiby_connectivity_cancel(void)
{
    ++controller_cancellations;
    power_cancelled = true;
    controller.inhibited = true;
}

#include "bluetooth-ui-source.inc"

static bool fixture_operation_waiting(void)
{
    return operation_wait != NULL;
}

static void add_step(int title, int count, int selection, const char *first_name)
{
    assert(step_count < sizeof(steps) / sizeof(steps[0]));
    steps[step_count++] = (struct list_step){ title, count, selection, first_name, -1, false };
}

static void main_step(int selection)
{
    add_step(LANG_HIBY_BT_TITLE, 7, selection, str(LANG_HIBY_BT_TITLE));
}

static void finish_menu(int expected_usb)
{
    menu_running = true;
    entry_snapshot = observed;
    assert(hiby_bluetooth_menu() == expected_usb);
    assert(step_position == step_count);
#ifndef SIMULATOR
    assert(entry_refreshes == (initialized && !entry_snapshot.busy ? 1u : 0u));
#endif
    menu_running = false;
}

static void expect_message(int identifier)
{
    assert(message_count && messages[message_count - 1] == identifier);
}

static void no_success(void)
{
    for (size_t position = 0; position < message_count; ++position)
        assert(messages[position] != LANG_HIBY_BT_DONE);
}

static void fill_device(size_t position, const char *address, const char *name, bool paired)
{
    struct hiby_bt_device *device = &refreshed.devices[position];
    snprintf(device->address, sizeof(device->address), "%s", address);
    snprintf(device->name, sizeof(device->name), "%s", name);
    device->paired = paired;
    if (refreshed.count <= position)
        refreshed.count = position + 1;
}

static void preference_step(int selection, int initial)
{
    add_step(LANG_HIBY_BT_SETTINGS, 5, selection, str(LANG_HIBY_BT_AUTOCONNECT));
    steps[step_count - 1].initial_selection = initial;
}

static void preference_case(const char *scenario)
{
    const char *name = scenario + strlen("prefs_");
    int row = -1;
    int choice = 0;
    static const int titles[] = {
        LANG_HIBY_BT_AUTOCONNECT, LANG_HIBY_BT_RETRY_WINDOW,
        LANG_HIBY_BT_LOSS_BEHAVIOR, LANG_HIBY_BT_ANNOUNCEMENTS
    };
    static const int counts[] = { 3, 4, 2, 2 };
    static const unsigned int retries[] = { 30, 60, 120, 300 };
    if (!strncmp(name, "auto_", 5))
        row = 0;
    if (!strncmp(name, "retry_", 6))
        row = 1;
    if (!strncmp(name, "loss_", 5))
        row = 2;
    if (!strncmp(name, "announce_", 9))
        row = 3;
    if (row < 0)
    {
        bool last = !strcmp(name, "last");
        bool read_error = !strcmp(name, "read_error");
        bool busy = !strcmp(name, "busy") || !strcmp(name, "connectivity_busy");
        assert(last || read_error || busy || !strcmp(name, "defaults"));
        if (last)
            snprintf(fixture_preferences.last_address, sizeof(fixture_preferences.last_address), "AA:BB:CC:DD:EE:FF");
        if (read_error)
            preferences_read_error = EIO;
        if (busy)
        {
            observed.busy = true;
            automatic_operation = true;
            controller.busy = !strcmp(name, "connectivity_busy");
        }
        struct hiby_bt_preferences before = fixture_preferences;
        main_step(5);
        preference_step(last ? 4 : -1, 0);
        if (last)
            preference_step(-1, 4);
        main_step(-1);
        finish_menu(0);
        assert(!preference_writes && !memcmp(&fixture_preferences, &before, sizeof(before)));
        assert(!operation_count && !power_requests && !automatic_cancel_checks);
        if (read_error)
            expect_message(LANG_HIBY_BT_SETTINGS_ERROR);
        no_success();
        return;
    }
    const char *mode = strrchr(name, '_') + 1;
    bool cancelled = !strcmp(mode, "cancel");
    bool usb = !strcmp(mode, "usb");
    bool write_error = !strcmp(mode, "writeerror");
    if (!cancelled && !usb && !write_error)
    {
        assert(strlen(mode) == 1 && mode[0] >= '0' && mode[0] <= '3');
        choice = mode[0] - '0';
        assert(choice < counts[row]);
    }
    int previous_choice = (choice + 1) % counts[row];
    if (row == 0)
        fixture_preferences.auto_mode = (enum bluetooth_reconnect_mode)previous_choice;
    if (row == 1)
        fixture_preferences.retry_seconds = retries[previous_choice];
    if (row == 2)
        fixture_preferences.pause_on_loss = previous_choice == 0;
    if (row == 3)
        fixture_preferences.announce = previous_choice != 0;
    if (write_error)
        preferences_write_error = ENOSPC;
    struct hiby_bt_preferences before = fixture_preferences;
    main_step(5);
    preference_step(row, 0);
    add_step(titles[row], counts[row], cancelled ? -1 : choice, NULL);
    steps[step_count - 1].initial_selection = previous_choice;
    steps[step_count - 1].usb = usb;
    if (!usb)
    {
        preference_step(-1, row);
        main_step(-1);
    }
    finish_menu(usb);
    assert(!operation_count && !power_requests && !automatic_cancel_checks);
    if (cancelled || usb || write_error)
        assert(!memcmp(&fixture_preferences, &before, sizeof(before)));
    else
    {
        struct hiby_bt_preferences expected = before;
        if (row == 0)
            expected.auto_mode = (enum bluetooth_reconnect_mode)choice;
        if (row == 1)
            expected.retry_seconds = retries[choice];
        if (row == 2)
            expected.pause_on_loss = choice == 0;
        if (row == 3)
            expected.announce = choice != 0;
        ++expected.generation;
        assert(!memcmp(&fixture_preferences, &expected, sizeof(expected)));
        assert(fixture_preferences.generation == before.generation + 1);
        if (row == 0)
            assert(fixture_preferences.auto_mode == (enum bluetooth_reconnect_mode)choice);
        if (row == 1)
            assert(fixture_preferences.retry_seconds == retries[choice]);
        if (row == 2)
            assert(fixture_preferences.pause_on_loss == (choice == 0));
        if (row == 3)
            assert(fixture_preferences.announce == (choice != 0));
    }
    assert(preference_writes == (cancelled || usb ? 0u : 1u));
    if (preference_writes)
    {
        static const enum hiby_bt_preference expected[] = {
            HIBY_BT_PREF_AUTOCONNECT, HIBY_BT_PREF_RETRY_SECONDS,
            HIBY_BT_PREF_PAUSE_ON_LOSS, HIBY_BT_PREF_ANNOUNCE
        };
        assert(written_preference == expected[row]);
        assert(written_value == (row == 1 ? (int)retries[choice] : row == 2 ? choice == 0 : choice));
    }
    if (write_error)
        expect_message(LANG_HIBY_BT_SETTINGS_ERROR);
    no_success();
}

static void connect_last_case(const char *scenario)
{
    bool missing = !strcmp(scenario, "last_missing");
    bool read_error = !strcmp(scenario, "last_read_error");
    if (!missing)
        snprintf(fixture_preferences.last_address, sizeof(fixture_preferences.last_address), "AA:BB:CC:DD:EE:FF");
    if (read_error)
        preferences_read_error = EIO;
    if (!strcmp(scenario, "last_powered_off"))
        operation_error = HIBY_BT_POWERED_OFF;
    if (!strcmp(scenario, "last_inhibited"))
        operation_error = HIBY_BT_INHIBITED;
    if (!strcmp(scenario, "last_unpaired"))
        operation_error = HIBY_BT_PAIR_FAILED;
    struct hiby_bt_preferences before = fixture_preferences;
    main_step(6);
    main_step(-1);
    finish_menu(0);
    assert(!preference_writes && !power_requests && !memcmp(&fixture_preferences, &before, sizeof(before)));
    assert(operation_count == (missing || read_error ? 0u : 1u));
    if (operation_count)
    {
        assert(operations[0] == HIBY_BT_CONNECT_PAIRED);
        assert(!strcmp(last_address, fixture_preferences.last_address));
    }
    if (missing || read_error)
        expect_message(read_error ? LANG_HIBY_BT_SETTINGS_ERROR : LANG_HIBY_BT_NO_LAST_DEVICE);
    else
        expect_message(operation_error == HIBY_BT_POWERED_OFF ? LANG_HIBY_BT_POWERED_OFF :
            operation_error == HIBY_BT_INHIBITED ? LANG_HIBY_BT_INHIBITED :
            operation_error == HIBY_BT_PAIR_FAILED ? LANG_HIBY_BT_PAIR_FAILED : LANG_HIBY_BT_DONE);
    if (missing || read_error || operation_error)
        no_success();
}

static void forget_case(const char *scenario)
{
    bool usb = !strcmp(scenario, "forget_usb");
    bool accept = !strcmp(scenario, "forget_accept") || !strcmp(scenario, "forget_failure");
    bool cancel = !strcmp(scenario, "forget_cancel");
    if (!strcmp(scenario, "forget_failure"))
        operation_error = HIBY_BT_COMMAND_FAILED;
    main_step(1);
    add_step(LANG_HIBY_BT_PAIRED_DEVICES, 1, 0, "Paired headphones");
    add_step(LANG_HIBY_BT_PAIRED_DEVICES, 2, 1, str(LANG_HIBY_BT_CONNECT));
    add_step(LANG_HIBY_BT_REMOVE_CONFIRM, 2, cancel ? -1 : accept ? 1 : 0,
        str(LANG_HIBY_BT_KEEP_DEVICE));
    steps[step_count - 1].initial_selection = 0;
    steps[step_count - 1].usb = usb;
    if (!usb)
        main_step(-1);
    finish_menu(usb);
    assert(operation_count == (accept ? 2u : 1u));
    assert(operations[0] == HIBY_BT_REFRESH);
    if (accept)
    {
        assert(operations[1] == HIBY_BT_REMOVE);
        assert(!strcmp(last_address, "AA:BB:CC:DD:EE:FF"));
        expect_message(operation_error ? LANG_HIBY_BT_COMMAND_FAILED : LANG_HIBY_BT_DONE);
    }
    if (!accept || operation_error)
        no_success();
    assert(!power_requests && !preference_writes);
}

static void service_status_case(const char *scenario)
{
    service_status.running = true;
    service_status.allowed = true;
    service_status.monitoring = strcmp(scenario, "status_service_unavailable") != 0;
    service_status.reconnecting = !strcmp(scenario, "status_service_reconnecting");
    service_status.storage_error = !strcmp(scenario, "status_service_storage_error") ? EIO : 0;
    if (!strcmp(scenario, "status_service_stopped"))
        service_status.running = false;
    if (!strcmp(scenario, "status_service_inhibited"))
        service_status.allowed = false;
    bool enabled = strcmp(scenario, "status_service_off") != 0;
    bool failed = !strcmp(scenario, "status_service_backend_error");
    observed.enabled = refreshed.enabled = enabled;
    controller.bluetooth_desired = enabled;
    controller.bluetooth = enabled ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF;
    if (failed)
        refreshed.error = HIBY_BT_COMMAND_FAILED;
    bool connected = !strcmp(scenario, "status_service_connected");
    if (connected)
    {
        snprintf(refreshed.connected_address, sizeof(refreshed.connected_address), "AA:BB:CC:DD:EE:FF");
        snprintf(refreshed.connected_name, sizeof(refreshed.connected_name), "Paired headphones");
    }
    main_step(4);
    main_step(-1);
    finish_menu(0);
    assert(operation_count == 1 && operations[0] == HIBY_BT_REFRESH && !power_requests);
    assert(service_status_reads == (enabled && !failed ? 1u : 0u));
    bool announce = enabled && !failed && service_status.running && service_status.allowed;
    size_t base = spoken_count;
    for (size_t position = 0; position < spoken_count; ++position)
    {
        if (!spoken_enqueue[position] && spoken[position] == (connected ? LANG_HIBY_BT_CONNECTED :
            failed ? LANG_HIBY_BT_COMMAND_FAILED : enabled ? LANG_HIBY_BT_ENABLED : LANG_HIBY_BT_DISABLED))
            base = position;
        if (spoken[position] == LANG_HIBY_BT_MONITOR_ACTIVE ||
            spoken[position] == LANG_HIBY_BT_MONITOR_UNAVAILABLE)
            assert(announce);
    }
    assert(base < spoken_count && !spoken_enqueue[base]);
    if (announce)
    {
        size_t next = base + 1;
        assert(spoken[next] == (service_status.monitoring ?
            LANG_HIBY_BT_MONITOR_ACTIVE : LANG_HIBY_BT_MONITOR_UNAVAILABLE));
        assert(spoken_enqueue[next++]);
        if (service_status.reconnecting)
        {
            assert(spoken[next] == LANG_HIBY_BT_RECONNECTING && spoken_enqueue[next]);
            ++next;
        }
        if (service_status.storage_error)
            assert(spoken[next] == LANG_HIBY_BT_SETTINGS_ERROR && spoken_enqueue[next]);
    }
    assert(!automatic_cancel_checks && !preference_writes);
    no_success();
}

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2);
    const char *scenario = arguments[1];
    observed.available = true;
    observed.power_known = true;
    refreshed = observed;
    controller.settled = true;
    fill_device(0, "11:22:33:44:55:66", "New headphones", false);
    fill_device(1, "AA:BB:CC:DD:EE:FF", "Paired headphones", true);
    fill_device(2, "22:33:44:55:66:77", "Another new device", false);

    if (!strncmp(scenario, "prefs_", 6))
        preference_case(scenario);
    else if (!strncmp(scenario, "last_", 5))
        connect_last_case(scenario);
    else if (!strncmp(scenario, "forget_", 7))
        forget_case(scenario);
    else if (!strncmp(scenario, "status_service_", 15))
        service_status_case(scenario);
    else if (!strcmp(scenario, "auto_power_off") || !strcmp(scenario, "manual_power_busy"))
    {
        controller.bluetooth_desired = true;
        controller.bluetooth = HIBY_CONNECTIVITY_ON;
        observed.enabled = true;
        observed.busy = true;
        automatic_operation = !strcmp(scenario, "auto_power_off");
        main_step(0);
        main_step(-1);
        finish_menu(0);
        assert(automatic_cancel_checks == 1 && !operation_count);
        if (!strcmp(scenario, "auto_power_off"))
        {
            assert(power_requests == 1 && automatic_cancellations == 1);
            assert(!controller.bluetooth_desired && !observed.enabled);
        }
        else
        {
            assert(!power_requests && !automatic_cancellations && controller.bluetooth_desired);
            expect_message(LANG_HIBY_BT_BUSY);
            no_success();
        }
    }
    else if (!strcmp(scenario, "menu_unknown"))
    {
        observed.power_known = false;
        main_step(-1);
        finish_menu(0);
        assert(strstr(switch_text, str(LANG_OFF)));
        assert(strstr(switch_text, str(LANG_HIBY_BT_POWER_UNKNOWN)));
        assert(!operation_count && !power_requests);
    }
    else if (!strcmp(scenario, "requested_on_actual_off") ||
             !strcmp(scenario, "requested_off_actual_on") ||
             !strcmp(scenario, "requested_on_unknown") ||
             !strcmp(scenario, "requested_off_failure") ||
             !strcmp(scenario, "requested_on_airplane_unknown"))
    {
        bool desired = strstr(scenario, "requested_on") != NULL;
        controller.bluetooth_desired = desired;
        expected_requested_label = desired ? LANG_ON : LANG_OFF;
        if (!strcmp(scenario, "requested_on_actual_off"))
        {
            controller.bluetooth = HIBY_CONNECTIVITY_OFF;
            expected_observed_label = LANG_OFF;
        }
        else if (!strcmp(scenario, "requested_off_actual_on"))
        {
            controller.bluetooth = HIBY_CONNECTIVITY_ON;
            expected_observed_label = LANG_ON;
        }
        else if (!strcmp(scenario, "requested_off_failure"))
        {
            controller.bluetooth = HIBY_CONNECTIVITY_RADIO_ERROR;
            controller.result = HIBY_CONNECTIVITY_FAILED;
            expected_observed_label = LANG_HIBY_BT_COMMAND_FAILED;
        }
        else
        {
            controller.bluetooth = HIBY_CONNECTIVITY_UNKNOWN;
            expected_observed_label = LANG_HIBY_BT_POWER_UNKNOWN;
        }
        controller.airplane_mode = strstr(scenario, "airplane") != NULL;
        observed.enabled = controller.bluetooth == HIBY_CONNECTIVITY_ON;
        observed.power_known = controller.bluetooth == HIBY_CONNECTIVITY_ON ||
                               controller.bluetooth == HIBY_CONNECTIVITY_OFF;
        observed.error = controller.bluetooth == HIBY_CONNECTIVITY_RADIO_ERROR ?
            HIBY_BT_COMMAND_FAILED : HIBY_BT_OK;
        main_step(-1);
        finish_menu(0);
        assert(!operation_count && !power_requests);
    }
    else if (!strcmp(scenario, "status_on_to_off") || !strcmp(scenario, "status_on_to_unknown") ||
             !strcmp(scenario, "status_on_to_error"))
    {
        controller.bluetooth_desired = true;
        controller.bluetooth = HIBY_CONNECTIVITY_ON;
        observed.enabled = true;
        expected_requested_label = LANG_ON;
        refreshed.enabled = false;
        if (!strcmp(scenario, "status_on_to_off"))
            after_status_label = LANG_OFF;
        else if (!strcmp(scenario, "status_on_to_unknown"))
        {
            refreshed.enabled = true;
            refreshed.power_known = false;
            after_status_label = LANG_HIBY_BT_POWER_UNKNOWN;
        }
        else
        {
            refreshed.enabled = true;
            refreshed.power_known = false;
            refreshed.error = HIBY_BT_COMMAND_FAILED;
            after_status_label = LANG_HIBY_BT_COMMAND_FAILED;
        }
        main_step(4);
        main_step(-1);
        finish_menu(0);
        assert(controller.bluetooth_desired && controller.bluetooth == HIBY_CONNECTIVITY_ON);
        assert(operation_count == 1 && operations[0] == HIBY_BT_REFRESH && !power_requests);
    }
    else if (!strcmp(scenario, "switch_on") || !strcmp(scenario, "switch_off") ||
             !strcmp(scenario, "airplane") || !strcmp(scenario, "storage_failure") ||
             !strcmp(scenario, "switch_partial") || !strcmp(scenario, "switch_unsettled") ||
             !strcmp(scenario, "switch_rejected") || !strcmp(scenario, "switch_storage_state") ||
             !strcmp(scenario, "switch_inhibited_state"))
    {
        bool was_enabled = !strcmp(scenario, "switch_off");
        controller.bluetooth_desired = was_enabled;
        controller.bluetooth = was_enabled ? HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF;
        controller.airplane_mode = !strcmp(scenario, "airplane");
        if (!strcmp(scenario, "storage_failure"))
            power_result = HIBY_CONNECTIVITY_STORAGE_ERROR;
        incomplete_power = !strcmp(scenario, "switch_partial");
        controller.settled = strcmp(scenario, "switch_unsettled") != 0;
        controller.storage_error = !strcmp(scenario, "switch_storage_state") ? 5 : 0;
        controller.inhibited = !strcmp(scenario, "switch_inhibited_state");
        reject_power = !strcmp(scenario, "switch_rejected");
        main_step(0);
        main_step(-1);
        finish_menu(0);
        assert(power_requests == 1 && !operation_count);
        assert(controller.bluetooth_desired == (reject_power ? was_enabled : !was_enabled));
        if (controller.airplane_mode)
        {
            expect_message(LANG_HIBY_BT_AIRPLANE_MODE);
            assert(strstr(switch_text, str(LANG_OFF)));
            assert(strstr(switch_text, str(LANG_HIBY_BT_AIRPLANE_MODE)));
        }
        else if (power_result == HIBY_CONNECTIVITY_STORAGE_ERROR || controller.storage_error)
            expect_message(LANG_HIBY_CONNECTIVITY_STORAGE_ERROR);
        else if (incomplete_power || !controller.settled || controller.inhibited)
            expect_message(LANG_HIBY_CONNECTIVITY_PARTIAL);
        else if (reject_power)
            expect_message(LANG_HIBY_CONNECTIVITY_FAILED);
        else
            expect_message(LANG_HIBY_BT_DONE);
        if (controller.airplane_mode || power_result || incomplete_power || !controller.settled ||
            reject_power || controller.storage_error || controller.inhibited)
            no_success();
    }
    else if (!strcmp(scenario, "paired_connect") || !strcmp(scenario, "paired_remove") ||
             !strcmp(scenario, "pair_new") || !strcmp(scenario, "missing_device") ||
             !strcmp(scenario, "nameless_device") || !strcmp(scenario, "device_cancel"))
    {
        bool paired = strcmp(scenario, "pair_new") != 0 && strcmp(scenario, "nameless_device") != 0;
        int title = paired ? LANG_HIBY_BT_PAIRED_DEVICES : LANG_HIBY_BT_PAIR_NEW;
        if (!strcmp(scenario, "missing_device"))
            operation_error = HIBY_BT_CONNECT_FAILED;
        if (!strcmp(scenario, "nameless_device"))
            refreshed.devices[0].name[0] = '\0';
        observed.count = 1;
        snprintf(observed.devices[0].name, sizeof(observed.devices[0].name), "Stale device");
        main_step(paired ? 1 : 2);
        add_step(title, paired ? 1 : 2, !strcmp(scenario, "device_cancel") ? -1 : 0,
                 paired ? "Paired headphones" : !strcmp(scenario, "nameless_device") ?
                 "11:22:33:44:55:66" : "New headphones");
        bool cancelled = !strcmp(scenario, "device_cancel");
        bool remove = !strcmp(scenario, "paired_remove");
        if (paired && !cancelled)
            add_step(title, 2, remove ? 1 : 0, str(LANG_HIBY_BT_CONNECT));
        if (remove)
        {
            add_step(LANG_HIBY_BT_REMOVE_CONFIRM, 2, 1, str(LANG_HIBY_BT_KEEP_DEVICE));
            steps[step_count - 1].initial_selection = 0;
        }
        main_step(-1);
        finish_menu(0);
        assert(operation_count == (cancelled ? 1u : 2u));
        assert(operations[0] == (paired ? HIBY_BT_REFRESH : HIBY_BT_SCAN));
        if (!cancelled)
        {
            assert(operations[1] == (remove ? HIBY_BT_REMOVE : HIBY_BT_CONNECT));
            assert(!strcmp(last_address, paired ? "AA:BB:CC:DD:EE:FF" : "11:22:33:44:55:66"));
            expect_message(operation_error ? LANG_HIBY_BT_CONNECT_FAILED : LANG_HIBY_BT_DONE);
        }
        if (operation_error || cancelled)
            no_success();
        assert(!power_requests);
    }
    else if (!strcmp(scenario, "paired_empty") || !strcmp(scenario, "unpaired_empty") ||
             !strcmp(scenario, "refresh_failure") || !strcmp(scenario, "scan_failure") ||
             !strcmp(scenario, "scan_powered_off") || !strcmp(scenario, "scan_inhibited"))
    {
        bool paired = !strcmp(scenario, "paired_empty") || !strcmp(scenario, "refresh_failure");
        int expected = paired ? LANG_HIBY_BT_PAIRED_EMPTY : LANG_HIBY_BT_UNPAIRED_EMPTY;
        for (size_t position = 0; position < refreshed.count; ++position)
            refreshed.devices[position].paired = !paired;
        if (strstr(scenario, "failure"))
        {
            refreshed.error = HIBY_BT_COMMAND_FAILED;
            expected = LANG_HIBY_BT_COMMAND_FAILED;
        }
        if (!strcmp(scenario, "scan_powered_off"))
        {
            refreshed.error = HIBY_BT_POWERED_OFF;
            expected = LANG_HIBY_BT_POWERED_OFF;
        }
        if (!strcmp(scenario, "scan_inhibited"))
        {
            assert(!controller.airplane_mode);
            reject_bt = true;
            observed.error = HIBY_BT_INHIBITED;
            expected = LANG_HIBY_BT_INHIBITED;
        }
        main_step(paired ? 1 : 2);
        main_step(-1);
        finish_menu(0);
        assert(operation_count == 1 && !power_requests);
        expect_message(expected);
        no_success();
    }
    else if (!strcmp(scenario, "live_power_navigation") || !strcmp(scenario, "live_power_repeat") ||
             !strcmp(scenario, "live_power_fast_disable") ||
             !strcmp(scenario, "live_power_failure") || !strcmp(scenario, "live_power_timeout") ||
             !strcmp(scenario, "live_power_cancel") || !strcmp(scenario, "live_power_usb") ||
             !strcmp(scenario, "live_power_scan_conflict"))
    {
        live_power_menu = true;
        busy_power = true;
        repeated_power_menu = !strcmp(scenario, "live_power_repeat") ||
                              !strcmp(scenario, "live_power_scan_conflict");
        if (!strcmp(scenario, "live_power_failure"))
            power_result = HIBY_CONNECTIVITY_FAILED;
        if (!strcmp(scenario, "live_power_timeout"))
            power_result = HIBY_CONNECTIVITY_TIMEOUT;
        if (!strcmp(scenario, "live_power_cancel"))
            live_power_exit = ACTION_STD_CANCEL;
        if (!strcmp(scenario, "live_power_usb"))
            live_power_exit = SYS_USB_CONNECTED;
        main_step(0);
        bool fast_disable = !strcmp(scenario, "live_power_fast_disable");
        if (fast_disable)
            main_step(0);
        if (repeated_power_menu)
            main_step(!strcmp(scenario, "live_power_scan_conflict") ? 2 : 0);
        main_step(-1);
        finish_menu(live_power_exit == SYS_USB_CONNECTED);
        assert(power_requests == (fast_disable ? 2u : 1u) && !operation_count);
        assert(live_navigation > 0);
        if (live_power_exit)
        {
            assert(controller_cancellations == 1 && controller.busy);
            assert(!live_completion);
        }
        else
        {
            assert(live_navigation == (fast_disable ? 6u : 3u) &&
                   live_completion == (fast_disable ? 2u : 1u) && !controller.busy);
            if (fast_disable)
                assert(!controller.bluetooth_desired && controller.bluetooth == HIBY_CONNECTIVITY_OFF);
            if (power_result != HIBY_CONNECTIVITY_OK)
                expect_message(power_result == HIBY_CONNECTIVITY_TIMEOUT ?
                    LANG_HIBY_BT_TIMEOUT : LANG_HIBY_CONNECTIVITY_FAILED);
            if (repeated_power_menu)
                expect_message(LANG_HIBY_BT_BUSY);
        }
        no_success();
    }
    else if (!strcmp(scenario, "cancel_scan") || !strcmp(scenario, "usb_scan") ||
             !strcmp(scenario, "modal_settings_busy") ||
             !strcmp(scenario, "timeout_scan") || !strcmp(scenario, "late_scan_success") ||
             !strcmp(scenario, "cancel_power") || !strcmp(scenario, "usb_power") ||
             !strcmp(scenario, "timeout_power") || !strcmp(scenario, "late_power_success"))
    {
        bool power = strstr(scenario, "power") != NULL;
        bool usb = strstr(scenario, "usb") != NULL;
        bool timeout = strstr(scenario, "timeout") != NULL;
        modal_settings_probe = !strcmp(scenario, "modal_settings_busy");
        late_success = strstr(scenario, "late") != NULL;
        never_finish = timeout;
        busy_operation = power ? -1 : HIBY_BT_SCAN;
        busy_power = power;
        requested_action = timeout ? 0 : usb ? SYS_USB_CONNECTED : ACTION_STD_CANCEL;
        if (power)
        {
            assert(toggle_power() == BLUETOOTH_UI_OK);
            struct gui_synclist list = {0};
            assert(main_action(requested_action, &list) == requested_action);
            for (unsigned int iteration = 0; power_change_pending && iteration < 12; ++iteration)
            {
                get_action(CONTEXT_STD, HZ / 10);
                main_action(ACTION_NONE, &list);
            }
            assert(!power_change_pending);
        }
        else
        {
            main_step(2);
            if (!usb)
                main_step(-1);
            finish_menu(usb ? 1 : 0);
        }
        assert((power && timeout) || action_count >= finish_after);
        if (modal_settings_probe)
            assert(modal_probe_count == 1 && !preference_reads && !preference_writes);
        else
            assert(power ? timeout || controller_cancellations > 0 : bt_cancellations > 0);
        if (timeout)
        {
            assert(power ? controller.inhibited : inhibited);
            assert(power ? controller.busy : observed.busy);
            expect_message(LANG_HIBY_BT_TIMEOUT);
        }
        else
        {
            assert(power ? !controller.busy : !observed.busy);
            if (!usb)
                expect_message(LANG_HIBY_BT_CANCELLED);
        }
        assert(power ? power_requests == 1 && !operation_count : operation_count == 1 && !power_requests);
        no_success();
    }
    else if (!strcmp(scenario, "rejected_without_error"))
    {
        reject_bt = true;
        assert(run_operation(HIBY_BT_REFRESH, NULL, false) == BLUETOOTH_UI_FAILED);
        expect_message(LANG_HIBY_BT_COMMAND_FAILED);
        no_success();
    }
    else if (!strcmp(scenario, "disconnect") || !strcmp(scenario, "disconnect_failure"))
    {
        if (!strcmp(scenario, "disconnect_failure"))
            operation_error = HIBY_BT_COMMAND_FAILED;
        main_step(3);
        main_step(-1);
        finish_menu(0);
        assert(operation_count == 1 && operations[0] == HIBY_BT_DISCONNECT && !power_requests);
        expect_message(operation_error ? LANG_HIBY_BT_COMMAND_FAILED : LANG_HIBY_BT_DONE);
        if (operation_error)
            no_success();
    }
    else if (!strcmp(scenario, "unavailable") || !strcmp(scenario, "native_thread_failure"))
    {
        initialized = false;
        observed.error = !strcmp(scenario, "native_thread_failure") ? HIBY_BT_THREAD_FAILED : HIBY_BT_UNAVAILABLE;
        finish_menu(0);
        expect_message(observed.error == HIBY_BT_THREAD_FAILED ? LANG_HIBY_BT_THREAD_FAILED : LANG_HIBY_BT_UNAVAILABLE);
        assert(!operation_count && !power_requests);
    }
    else if (!strcmp(scenario, "sim_menu") || !strcmp(scenario, "sim_switch") ||
             !strcmp(scenario, "sim_scan") || !strcmp(scenario, "sim_paired"))
    {
        controller.bluetooth = HIBY_CONNECTIVITY_UNAVAILABLE;
        controller.result = HIBY_CONNECTIVITY_NOT_AVAILABLE;
        bool toggle = !strcmp(scenario, "sim_switch");
        bool passive = !strcmp(scenario, "sim_menu");
        main_step(passive ? -1 : toggle ? 0 : !strcmp(scenario, "sim_scan") ? 2 : 1);
        if (!passive)
            main_step(-1);
        finish_menu(0);
        if (!passive)
            expect_message(LANG_HIBY_BT_UNAVAILABLE);
        assert(controller.bluetooth_desired == toggle);
        assert(controller.bluetooth == HIBY_CONNECTIVITY_UNAVAILABLE);
        assert(power_requests == (toggle ? 1u : 0u));
        assert(!operation_count);
        no_success();
        hiby_bluetooth_get_snapshot(&observed);
        assert(!observed.enabled && !observed.available && !observed.power_known && !observed.busy);
        assert(observed.error == HIBY_BT_UNAVAILABLE);
    }
    else
        assert(false);
    printf("verified-bluetooth-ui=%s\n", scenario);
    return 0;
}
