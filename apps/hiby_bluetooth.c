#ifndef HIBY_BT_HOST_TEST
#include "config.h"
#endif

#include "hiby_bluetooth.h"
#include "hiby_bluetooth_service.h"
#include <string.h>

#if (defined(HIBY_LINUX) && !defined(SIMULATOR)) || defined(HIBY_BT_HOST_TEST)
#include <limits.h>
#include <pthread.h>
#include <time.h>

static pthread_mutex_t state_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t state_changed = PTHREAD_COND_INITIALIZER;
static pthread_t worker;
static bool running;
static bool stopping;
static bool pending;
static bool cancel_requested;
static bool radio_inhibited;
static bool automatic_operation;
static long long operation_deadline;
static long long operation_queued;
static enum hiby_bt_operation requested_operation;
static char requested_address[18];
static struct hiby_bt_snapshot current_state;
static struct hiby_bt_request requested_identity;
static unsigned int request_sequence;

struct bluetooth_operation_context
{
    long long deadline;
    long long started;
    bool timed_out;
    struct hiby_bt_request request;
};

static long long operation_clock(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) || value.tv_sec < 0 ||
        value.tv_nsec < 0 || value.tv_nsec >= 1000000000)
        return -1;
    long long milliseconds;
    if (__builtin_mul_overflow(value.tv_sec, 1000LL, &milliseconds) ||
        __builtin_add_overflow(milliseconds, value.tv_nsec / 1000000,
                               &milliseconds))
        return -1;
    return milliseconds;
}

static bool operation_cancelled(void *context)
{
    struct bluetooth_operation_context *operation = context;
    if (__atomic_load_n(&cancel_requested, __ATOMIC_ACQUIRE))
        return true;
    if (operation && operation->timed_out)
        return true;
    if (operation && !hiby_bluetooth_service_current(&operation->request))
        return true;
    if (operation && operation->deadline)
    {
        long long now = operation_clock();
        if (now < operation->started || now >= operation->deadline)
        {
            operation->timed_out = true;
            return true;
        }
    }
    return false;
}

static void *bluetooth_worker(void *context)
{
    (void)context;
    pthread_mutex_lock(&state_mutex);
    for (;;)
    {
        while (!pending && !stopping)
            pthread_cond_wait(&state_changed, &state_mutex);
        if (stopping)
            break;
        enum hiby_bt_operation operation = requested_operation;
        struct hiby_bt_request identity = requested_identity;
        long long deadline = operation_deadline;
        long long queued = operation_queued;
        char address[18];
        memcpy(address, requested_address, sizeof(address));
        struct hiby_bt_snapshot next = current_state;
        pending = false;
        pthread_mutex_unlock(&state_mutex);
        long long now = deadline ? operation_clock() : 0;
        struct bluetooth_operation_context operation_context = {
            .deadline = deadline,
            .started = queued,
            .timed_out = deadline && (now < queued || now >= deadline),
            .request = identity
        };
        enum hiby_bt_error result = hiby_bt_backend_execute(operation,
            address[0] ? address : NULL, &next, operation_cancelled, &operation_context);
        operation_cancelled(&operation_context);
        if (operation_context.timed_out)
            result = HIBY_BT_TIMEOUT;
        if (operation_cancelled(NULL))
            result = HIBY_BT_CANCELLED;
        pthread_mutex_lock(&state_mutex);
        if (operation_cancelled(NULL))
        {
            result = HIBY_BT_CANCELLED;
            next.power_known = false;
        }
        next.busy = false;
        next.error = result;
        next.generation = current_state.generation + 1;
        hiby_bluetooth_service_completed(&identity, &next, &current_state);
        pthread_cond_broadcast(&state_changed);
        pthread_mutex_unlock(&state_mutex);
        hiby_bluetooth_service_persist(&identity, address, &next);
        pthread_mutex_lock(&state_mutex);
    }
    current_state.busy = false;
    pthread_mutex_unlock(&state_mutex);
    return NULL;
}

bool hiby_bluetooth_init(void)
{
    pthread_mutex_lock(&state_mutex);
    if (running || stopping)
    {
        bool result = running && !stopping;
        pthread_mutex_unlock(&state_mutex);
        return result;
    }
    memset(&current_state, 0, sizeof(current_state));
    pending = false;
    __atomic_store_n(&cancel_requested, false, __ATOMIC_RELEASE);
    pthread_attr_t attributes;
    int result = pthread_attr_init(&attributes);
    if (!result)
    {
        size_t stack_size = (size_t)PTHREAD_STACK_MIN;
        if (stack_size < 65536)
            stack_size = 65536;
        result = pthread_attr_setstacksize(&attributes, stack_size);
        if (!result)
            result = pthread_create(&worker, &attributes, bluetooth_worker, NULL);
        pthread_attr_destroy(&attributes);
    }
    if (result)
        current_state.error = HIBY_BT_THREAD_FAILED;
    else
        running = true;
    pthread_mutex_unlock(&state_mutex);
    return !result;
}

static void cancel_locked(void)
{
    hiby_bluetooth_service_cancelled();
    __atomic_store_n(&cancel_requested, true, __ATOMIC_RELEASE);
}

void hiby_bluetooth_cancel(void)
{
    pthread_mutex_lock(&state_mutex);
    cancel_locked();
    pthread_mutex_unlock(&state_mutex);
}

bool hiby_bluetooth_cancel_automatic(void)
{
    pthread_mutex_lock(&state_mutex);
    bool cancelled = current_state.busy && automatic_operation;
    if (cancelled)
        __atomic_store_n(&cancel_requested, true, __ATOMIC_RELEASE);
    pthread_mutex_unlock(&state_mutex);
    return cancelled;
}

void hiby_bluetooth_set_inhibited(bool inhibited)
{
    pthread_mutex_lock(&state_mutex);
    radio_inhibited = inhibited;
    if (inhibited)
    {
        hiby_bluetooth_service_allow(false);
        cancel_locked();
    }
    pthread_mutex_unlock(&state_mutex);
}

bool hiby_bluetooth_is_inhibited(void)
{
    pthread_mutex_lock(&state_mutex);
    bool inhibited = radio_inhibited;
    pthread_mutex_unlock(&state_mutex);
    return inhibited;
}

void hiby_bluetooth_shutdown(void)
{
    pthread_mutex_lock(&state_mutex);
    if (stopping)
    {
        while (stopping)
            pthread_cond_wait(&state_changed, &state_mutex);
        pthread_mutex_unlock(&state_mutex);
        return;
    }
    if (!running)
    {
        pthread_mutex_unlock(&state_mutex);
        return;
    }
    stopping = true;
    cancel_locked();
    pthread_cond_broadcast(&state_changed);
    pthread_mutex_unlock(&state_mutex);
    pthread_join(worker, NULL);
    pthread_mutex_lock(&state_mutex);
    running = false;
    stopping = false;
    pending = false;
    pthread_cond_broadcast(&state_changed);
    pthread_mutex_unlock(&state_mutex);
}

static bool request_operation(enum hiby_bt_operation operation, const char *address,
    bool automatic, unsigned int timeout_ms, const struct hiby_bt_request *expected,
    struct hiby_bt_request *issued)
{
    pthread_mutex_lock(&state_mutex);
    if (!running || stopping)
    {
        if (current_state.error != HIBY_BT_THREAD_FAILED)
            current_state.error = HIBY_BT_UNAVAILABLE;
        pthread_mutex_unlock(&state_mutex);
        return false;
    }
    if (current_state.busy)
    {
        pthread_mutex_unlock(&state_mutex);
        return false;
    }
    long long now = timeout_ms ? operation_clock() : 0;
    if (timeout_ms && (now < 0 || now > LLONG_MAX - timeout_ms))
    {
        current_state.error = HIBY_BT_TIMEOUT;
        ++current_state.generation;
        pthread_mutex_unlock(&state_mutex);
        return false;
    }
    if (radio_inhibited && (operation == HIBY_BT_ENABLE ||
        operation == HIBY_BT_SCAN || operation == HIBY_BT_CONNECT ||
        operation == HIBY_BT_CONNECT_PAIRED))
    {
        current_state.error = HIBY_BT_INHIBITED;
        current_state.generation++;
        pthread_mutex_unlock(&state_mutex);
        return false;
    }
    if (operation < HIBY_BT_ENABLE || operation > HIBY_BT_VERIFY_LINK ||
        ((operation == HIBY_BT_CONNECT || operation == HIBY_BT_CONNECT_PAIRED ||
          operation == HIBY_BT_REMOVE) &&
         !hiby_bt_valid_address(address)))
    {
        current_state.error = HIBY_BT_INVALID_ADDRESS;
        current_state.generation++;
        pthread_mutex_unlock(&state_mutex);
        return false;
    }
    struct hiby_bt_request identity = {
        .id = request_sequence + 1,
        .operation = operation,
        .automatic = automatic
    };
    if (!hiby_bluetooth_service_requested(&identity, expected))
    {
        pthread_mutex_unlock(&state_mutex);
        return false;
    }
    request_sequence = identity.id;
    requested_identity = identity;
    if (issued)
        *issued = identity;
    requested_operation = operation;
    automatic_operation = automatic;
    operation_deadline = timeout_ms ? now + timeout_ms : 0;
    operation_queued = now;
    requested_address[0] = '\0';
    if (operation == HIBY_BT_CONNECT || operation == HIBY_BT_CONNECT_PAIRED ||
        operation == HIBY_BT_REMOVE)
        memcpy(requested_address, address, sizeof(requested_address));
    __atomic_store_n(&cancel_requested, false, __ATOMIC_RELEASE);
    current_state.busy = true;
    current_state.power_known = false;
    current_state.error = HIBY_BT_OK;
    current_state.generation++;
    pending = true;
    pthread_cond_signal(&state_changed);
    pthread_mutex_unlock(&state_mutex);
    return true;
}

bool hiby_bluetooth_request(enum hiby_bt_operation operation, const char *address)
{
    return request_operation(operation, address, false, 0, NULL, NULL);
}

bool hiby_bluetooth_request_automatic(enum hiby_bt_operation operation,
                                      const char *address, unsigned int timeout_ms)
{
    if ((operation != HIBY_BT_CONNECT_PAIRED && operation != HIBY_BT_VERIFY_LINK) ||
        !timeout_ms || timeout_ms > 15000)
        return false;
    struct hiby_bt_service_observation observation = {0};
    hiby_bluetooth_service_observe(&observation);
    struct hiby_bt_request expected = {
        .intent = observation.intent,
        .permission = observation.permission
    };
    return hiby_bluetooth_request_guarded(operation, address, timeout_ms, &expected, NULL);
}

bool hiby_bluetooth_request_guarded(enum hiby_bt_operation operation,
    const char *address, unsigned int timeout_ms,
    const struct hiby_bt_request *expected, struct hiby_bt_request *issued)
{
    if ((operation != HIBY_BT_CONNECT_PAIRED && operation != HIBY_BT_VERIFY_LINK) ||
        !timeout_ms || timeout_ms > 15000 || !expected)
        return false;
    return request_operation(operation, address, true, timeout_ms, expected, issued);
}

void hiby_bluetooth_get_snapshot(struct hiby_bt_snapshot *snapshot)
{
    if (!snapshot)
        return;
    pthread_mutex_lock(&state_mutex);
    *snapshot = current_state;
    pthread_mutex_unlock(&state_mutex);
}

void hiby_bluetooth_get_observation(struct hiby_bt_snapshot *snapshot,
    struct hiby_bt_service_observation *observation)
{
    pthread_mutex_lock(&state_mutex);
    *snapshot = current_state;
    hiby_bluetooth_service_observe(observation);
    pthread_mutex_unlock(&state_mutex);
}

#else

static bool radio_inhibited;

bool hiby_bluetooth_init(void)
{
    return false;
}

void hiby_bluetooth_cancel(void) {}
void hiby_bluetooth_shutdown(void) {}

void hiby_bluetooth_set_inhibited(bool inhibited)
{
    radio_inhibited = inhibited;
}

bool hiby_bluetooth_is_inhibited(void)
{
    return radio_inhibited;
}

bool hiby_bluetooth_request(enum hiby_bt_operation operation, const char *address)
{
    (void)operation;
    (void)address;
    return false;
}

bool hiby_bluetooth_request_automatic(enum hiby_bt_operation operation,
                                      const char *address, unsigned int timeout_ms)
{
    (void)operation;
    (void)address;
    (void)timeout_ms;
    return false;
}

bool hiby_bluetooth_cancel_automatic(void) { return false; }

bool hiby_bluetooth_request_guarded(enum hiby_bt_operation operation,
    const char *address, unsigned int timeout_ms,
    const struct hiby_bt_request *expected, struct hiby_bt_request *issued)
{
    (void)operation;
    (void)address;
    (void)timeout_ms;
    (void)expected;
    (void)issued;
    return false;
}

void hiby_bluetooth_get_observation(struct hiby_bt_snapshot *snapshot,
    struct hiby_bt_service_observation *observation)
{
    hiby_bluetooth_get_snapshot(snapshot);
    memset(observation, 0, sizeof(*observation));
}

void hiby_bluetooth_get_snapshot(struct hiby_bt_snapshot *snapshot)
{
    if (snapshot)
    {
        memset(snapshot, 0, sizeof(*snapshot));
        snapshot->error = HIBY_BT_UNAVAILABLE;
    }
}

#endif

#ifndef HIBY_BT_NO_UI
#include <stdio.h>
#include "action.h"
#include "kernel.h"
#include "lang.h"
#include "list.h"
#include "misc.h"
#include "splash.h"
#include "talk.h"
#include "tts.h"
#include "hiby_connectivity.h"
#include "hiby_bluetooth_settings.h"

#ifndef HIBY_BT_UI_WAIT_STEPS
#define HIBY_BT_UI_WAIT_STEPS 1200
#endif
#ifndef HIBY_BT_UI_SETTLE_STEPS
#define HIBY_BT_UI_SETTLE_STEPS 150
#endif

enum bluetooth_ui_result
{
    BLUETOOTH_UI_FAILED = -1,
    BLUETOOTH_UI_CANCELLED = -2,
    BLUETOOTH_UI_OK = 0,
    BLUETOOTH_UI_USB = 1
};

static struct hiby_bt_snapshot menu_state;
static struct hiby_connectivity_snapshot connectivity_state;
static bool power_change_pending;
static bool power_change_enabled;
static bool power_change_cancelled;
static bool power_change_timed_out;
static long power_change_deadline;
static bool main_redraw_pending;
struct bluetooth_wait
{
    bool cancelling;
    bool usb;
    bool timed_out;
    bool done;
    long deadline;
};
static struct bluetooth_wait *operation_wait;
static int main_action(int action, struct gui_synclist *lists);
static const int main_labels[] = {
    LANG_HIBY_BT_TITLE, LANG_HIBY_BT_PAIRED_DEVICES, LANG_HIBY_BT_PAIR_NEW,
    LANG_HIBY_BT_DISCONNECT, LANG_HIBY_BT_STATUS, LANG_HIBY_BT_SETTINGS,
    LANG_HIBY_BT_CONNECT_LAST
};
static const int device_labels[] = { LANG_HIBY_BT_CONNECT, LANG_HIBY_BT_REMOVE };
static const int error_labels[] = {
    LANG_HIBY_BT_DONE, LANG_HIBY_BT_UNAVAILABLE, LANG_HIBY_BT_CANCELLED,
    LANG_HIBY_BT_TIMEOUT, LANG_HIBY_BT_INVALID_ADDRESS, LANG_HIBY_BT_COMMAND_FAILED,
    LANG_HIBY_BT_PAIR_FAILED, LANG_HIBY_BT_PIN_UNSUPPORTED, LANG_HIBY_BT_CONNECT_FAILED,
    LANG_HIBY_BT_AUDIO_FAILED, LANG_HIBY_BT_BUSY, LANG_HIBY_BT_THREAD_FAILED,
    LANG_HIBY_BT_POWERED_OFF, LANG_HIBY_BT_INHIBITED
};
_Static_assert(sizeof(error_labels) / sizeof(error_labels[0]) == HIBY_BT_INHIBITED + 1,
               "Bluetooth errors must all have spoken labels");

struct bluetooth_label_list
{
    const int *labels;
    int count;
};

static const char *label_name(int selected, void *data, char *buffer, size_t size)
{
    (void)buffer;
    (void)size;
    const struct bluetooth_label_list *list = data;
    if (selected < 0 || selected >= list->count)
        return "";
    return (const char *)str(list->labels[selected]);
}

static int label_talk(int selected, void *data)
{
    const struct bluetooth_label_list *list = data;
    if (selected < 0 || selected >= list->count)
        return 0;
    return talk_id(list->labels[selected], false);
}

static int choose_label(int title, const int *labels, int count, int selection)
{
    struct simplelist_info info;
    struct bluetooth_label_list list = { labels, count };
    simplelist_info_init(&info, str(title), count, &list);
#ifdef HAVE_ESPEAK
    if (title == LANG_HIBY_BT_RETRY_WINDOW)
        info.position_source = LIST_POSITION_SLIDER;
#endif
    info.get_name = label_name;
    info.get_talk = label_talk;
    info.selection = selection;
    if (simplelist_show_list(&info))
        return -2;
    return info.selection;
}

static struct hiby_bt_preferences displayed_preferences;
static const int preference_labels[] = {
    LANG_HIBY_BT_AUTOCONNECT, LANG_HIBY_BT_RETRY_WINDOW, LANG_HIBY_BT_LOSS_BEHAVIOR,
    LANG_HIBY_BT_ANNOUNCEMENTS, LANG_HIBY_BT_LAST_DEVICE
};
static const int reconnect_labels[] = {
    LANG_OFF, LANG_HIBY_BT_AUTO_STARTUP, LANG_HIBY_BT_AUTO_STARTUP_LOSS
};
static const int retry_labels[] = {
    LANG_HIBY_BT_RETRY_30, LANG_HIBY_BT_RETRY_60,
    LANG_HIBY_BT_RETRY_120, LANG_HIBY_BT_RETRY_300
};
static const unsigned int retry_values[] = { 30, 60, 120, 300 };
static const int loss_labels[] = {
    LANG_HIBY_BT_LOSS_PAUSE, LANG_HIBY_BT_LOSS_CONTINUE
};
static const int boolean_labels[] = { LANG_OFF, LANG_ON };

static int preference_value_label(int selected)
{
    if (selected == 0)
        return reconnect_labels[displayed_preferences.auto_mode];
    if (selected == 1)
    {
        for (size_t position = 0; position < sizeof(retry_values) / sizeof(retry_values[0]); ++position)
            if (displayed_preferences.retry_seconds == retry_values[position])
                return retry_labels[position];
        return LANG_HIBY_BT_RETRY_120;
    }
    if (selected == 2)
        return loss_labels[displayed_preferences.pause_on_loss ? 0 : 1];
    if (selected == 3)
        return boolean_labels[displayed_preferences.announce ? 1 : 0];
    return LANG_HIBY_BT_NO_LAST_DEVICE;
}

static const char *preference_name(int selected, void *data, char *buffer, size_t size)
{
    (void)data;
    if (selected < 0 || (size_t)selected >= sizeof(preference_labels) / sizeof(preference_labels[0]))
        return "";
    const char *value = selected == 4 && displayed_preferences.last_address[0] ?
        displayed_preferences.last_address : (const char *)str(preference_value_label(selected));
    snprintf(buffer, size, "%s: %s", str(preference_labels[selected]), value);
    return buffer;
}

static int preference_talk(int selected, void *data)
{
    (void)data;
    if (selected < 0 || (size_t)selected >= sizeof(preference_labels) / sizeof(preference_labels[0]))
        return 0;
    talk_id(preference_labels[selected], false);
    if (selected == 4 && displayed_preferences.last_address[0])
        talk_spell(displayed_preferences.last_address, true);
    else
        talk_id(preference_value_label(selected), true);
    return 0;
}

static int bluetooth_preferences_menu(void)
{
    int selected = 0;
    for (;;)
    {
        int storage_error = hiby_bt_preferences_get(&displayed_preferences);
        if (storage_error)
        {
            talk_id(LANG_HIBY_BT_SETTINGS_ERROR, false);
            splashf_silent(HZ, "%s", str(LANG_HIBY_BT_SETTINGS_ERROR));
        }
        struct simplelist_info info;
        simplelist_info_init(&info, str(LANG_HIBY_BT_SETTINGS),
            sizeof(preference_labels) / sizeof(preference_labels[0]), NULL);
        info.get_name = preference_name;
        info.get_talk = preference_talk;
        info.selection = selected;
        if (simplelist_show_list(&info))
            return BLUETOOTH_UI_USB;
        selected = info.selection;
        if (selected < 0)
            return BLUETOOTH_UI_OK;
        int choice = -1;
        enum hiby_bt_preference preference = HIBY_BT_PREF_AUTOCONNECT;
        int value = 0;
        if (selected == 0)
        {
            choice = choose_label(preference_labels[selected], reconnect_labels, 3,
                                  displayed_preferences.auto_mode);
            value = choice;
        }
        else if (selected == 1)
        {
            int current = 2;
            for (size_t position = 0; position < sizeof(retry_values) / sizeof(retry_values[0]); ++position)
                if (displayed_preferences.retry_seconds == retry_values[position])
                    current = (int)position;
            choice = choose_label(preference_labels[selected], retry_labels, 4, current);
            preference = HIBY_BT_PREF_RETRY_SECONDS;
            if (choice >= 0 && choice < 4)
                value = (int)retry_values[choice];
        }
        else if (selected == 2)
        {
            choice = choose_label(preference_labels[selected], loss_labels, 2,
                                  displayed_preferences.pause_on_loss ? 0 : 1);
            preference = HIBY_BT_PREF_PAUSE_ON_LOSS;
            value = choice == 0;
        }
        else if (selected == 3)
        {
            choice = choose_label(preference_labels[selected], boolean_labels, 2,
                                  displayed_preferences.announce ? 1 : 0);
            preference = HIBY_BT_PREF_ANNOUNCE;
            value = choice;
        }
        if (choice == -2)
            return BLUETOOTH_UI_USB;
        if (choice >= 0 && hiby_bt_preferences_set(preference, value))
        {
            talk_id(LANG_HIBY_BT_SETTINGS_ERROR, false);
            splashf_silent(HZ, "%s", str(LANG_HIBY_BT_SETTINGS_ERROR));
        }
    }
}

static int power_status_label(void)
{
    if (connectivity_state.busy || menu_state.busy)
        return LANG_HIBY_BT_WORKING;
    if (menu_state.error != HIBY_BT_OK && menu_state.error != HIBY_BT_POWERED_OFF)
        return (unsigned int)menu_state.error < sizeof(error_labels) / sizeof(error_labels[0]) ?
            error_labels[menu_state.error] : LANG_HIBY_BT_COMMAND_FAILED;
    if (!menu_state.power_known)
        return LANG_HIBY_BT_POWER_UNKNOWN;
    if (!menu_state.available)
        return LANG_HIBY_BT_UNAVAILABLE;
    return menu_state.enabled ? LANG_ON : LANG_OFF;
}

static const char *main_name(int selected, void *data, char *buffer, size_t size)
{
    (void)data;
    if (selected < 0 || (size_t)selected >= sizeof(main_labels) / sizeof(main_labels[0]))
        return "";
    if (selected != 0)
        return (const char *)str(main_labels[selected]);
    snprintf(buffer, size, "%s: %s (%s: %s%s%s)", str(LANG_HIBY_BT_TITLE),
             str(connectivity_state.bluetooth_desired ? LANG_ON : LANG_OFF),
             str(LANG_HIBY_BT_STATUS), str(power_status_label()),
             connectivity_state.airplane_mode ? ", " : "",
             connectivity_state.airplane_mode ? (const char *)str(LANG_HIBY_BT_AIRPLANE_MODE) : "");
    return buffer;
}

static int main_talk(int selected, void *data)
{
    (void)data;
    if (selected < 0 || (size_t)selected >= sizeof(main_labels) / sizeof(main_labels[0]))
        return 0;
    talk_id(main_labels[selected], false);
    if (selected == 0)
    {
        talk_id(connectivity_state.bluetooth_desired ? LANG_ON : LANG_OFF, true);
        talk_id(LANG_HIBY_BT_STATUS, true);
        talk_id(power_status_label(), true);
        if (connectivity_state.airplane_mode)
            talk_id(LANG_HIBY_BT_AIRPLANE_MODE, true);
    }
    return 0;
}

static int choose_main(int selection)
{
    struct simplelist_info info;
    hiby_connectivity_get_snapshot(&connectivity_state);
    hiby_bluetooth_get_snapshot(&menu_state);
    simplelist_info_init(&info, str(LANG_HIBY_BT_TITLE),
                         sizeof(main_labels) / sizeof(main_labels[0]), NULL);
    info.get_name = main_name;
    info.get_talk = main_talk;
    info.action_callback = main_action;
    info.selection = selection;
    if (simplelist_show_list(&info))
        return -2;
    return info.selection;
}

static const char *device_name(int selected, void *data, char *buffer, size_t size)
{
    const struct hiby_bt_snapshot *state = data;
    if (selected < 0 || (size_t)selected >= state->count)
        return "";
    const struct hiby_bt_device *device = &state->devices[selected];
    snprintf(buffer, size, "%s%s%s", device->name[0] ? device->name : device->address,
             device->paired ? ", " : "",
             device->paired ? (const char *)str(LANG_HIBY_BT_PAIRED) : "");
    return buffer;
}

static int device_talk(int selected, void *data)
{
    const struct hiby_bt_snapshot *state = data;
    if (selected < 0 || (size_t)selected >= state->count)
        return 0;
    const struct hiby_bt_device *device = &state->devices[selected];
    const char *name = device->name[0] ? device->name : device->address;
    if (tts_is_available())
        tts_speak(name, strlen(name), false);
    else
        talk_spell(name, false);
    if (device->paired)
        talk_id(LANG_HIBY_BT_PAIRED, true);
    return 0;
}

static void show_message(int ticks, int identifier)
{
    talk_id(identifier, false);
    splashf_silent(ticks, "%s", str(identifier));
}

static int show_result(enum hiby_bt_error error)
{
    if ((unsigned int)error >= sizeof(error_labels) / sizeof(error_labels[0]))
        error = HIBY_BT_COMMAND_FAILED;
    show_message(HZ, error_labels[error]);
    return 0;
}

static int run_operation(enum hiby_bt_operation operation, const char *address, bool announce_success)
{
    hiby_connectivity_get_snapshot(&connectivity_state);
    if (connectivity_state.busy)
    {
        show_message(HZ, LANG_HIBY_BT_BUSY);
        return BLUETOOTH_UI_FAILED;
    }
    if (!hiby_bluetooth_request(operation, address))
    {
        hiby_bluetooth_get_snapshot(&menu_state);
        show_result(menu_state.busy ? HIBY_BT_BUSY :
                    menu_state.error == HIBY_BT_OK ? HIBY_BT_COMMAND_FAILED : menu_state.error);
        return BLUETOOTH_UI_FAILED;
    }
    struct bluetooth_wait wait = {
        .deadline = current_tick + HIBY_BT_UI_WAIT_STEPS * (HZ / 10 ? HZ / 10 : 1)
    };
    hiby_bluetooth_get_snapshot(&menu_state);
    operation_wait = &wait;
    int selected = 0;
    while (menu_state.busy && !wait.done)
    {
        int choice = choose_main(selected);
        if (choice == -2)
            wait.usb = true;
        if (choice >= 0)
            selected = choice;
        hiby_bluetooth_get_snapshot(&menu_state);
    }
    operation_wait = NULL;
    enum hiby_bt_error error = wait.timed_out ? HIBY_BT_TIMEOUT :
        wait.cancelling ? HIBY_BT_CANCELLED : menu_state.error;
    if (!wait.usb && (error != HIBY_BT_OK || announce_success))
        show_result(error);
    return wait.usb ? BLUETOOTH_UI_USB : error == HIBY_BT_OK ?
        BLUETOOTH_UI_OK : wait.cancelling ? BLUETOOTH_UI_CANCELLED : BLUETOOTH_UI_FAILED;
}

static int perform_operation(enum hiby_bt_operation operation, const char *address)
{
    return run_operation(operation, address, true);
}

static int connectivity_result_label(enum hiby_connectivity_result result)
{
    switch (result)
    {
        case HIBY_CONNECTIVITY_OK: return LANG_HIBY_BT_DONE;
        case HIBY_CONNECTIVITY_NOT_AVAILABLE: return LANG_HIBY_BT_UNAVAILABLE;
        case HIBY_CONNECTIVITY_INCOMPLETE: return LANG_HIBY_CONNECTIVITY_PARTIAL;
        case HIBY_CONNECTIVITY_STORAGE_ERROR: return LANG_HIBY_CONNECTIVITY_STORAGE_ERROR;
        case HIBY_CONNECTIVITY_CANCELLED: return LANG_HIBY_BT_CANCELLED;
        case HIBY_CONNECTIVITY_TIMEOUT: return LANG_HIBY_BT_TIMEOUT;
        case HIBY_CONNECTIVITY_BUSY: return LANG_HIBY_BT_BUSY;
        case HIBY_CONNECTIVITY_INHIBITED: return LANG_HIBY_BT_AIRPLANE_MODE;
        default: return LANG_HIBY_CONNECTIVITY_FAILED;
    }
}

static enum hiby_connectivity_result power_change_result(bool enabled)
{
    enum hiby_connectivity_result result = connectivity_state.result;
    if (connectivity_state.storage_error)
        result = HIBY_CONNECTIVITY_STORAGE_ERROR;
    if (result == HIBY_CONNECTIVITY_OK && enabled && connectivity_state.airplane_mode)
        result = HIBY_CONNECTIVITY_INHIBITED;
    if (result == HIBY_CONNECTIVITY_OK &&
        (!connectivity_state.settled ||
         (enabled && connectivity_state.inhibited) || connectivity_state.bluetooth !=
         (enabled && !connectivity_state.airplane_mode ?
          HIBY_CONNECTIVITY_ON : HIBY_CONNECTIVITY_OFF)))
        result = HIBY_CONNECTIVITY_INCOMPLETE;
    return result;
}

static int toggle_power(void)
{
    hiby_connectivity_get_snapshot(&connectivity_state);
    hiby_bluetooth_get_snapshot(&menu_state);
    if (connectivity_state.busy || (menu_state.busy && !hiby_bluetooth_cancel_automatic()))
    {
        show_message(HZ, LANG_HIBY_BT_BUSY);
        return BLUETOOTH_UI_FAILED;
    }
    bool enabled = !connectivity_state.bluetooth_desired;
    if (!hiby_connectivity_set_bluetooth_enabled(enabled))
    {
        hiby_connectivity_get_snapshot(&connectivity_state);
        show_message(HZ, connectivity_state.busy ? LANG_HIBY_BT_BUSY :
                     LANG_HIBY_CONNECTIVITY_FAILED);
        return BLUETOOTH_UI_FAILED;
    }
    hiby_connectivity_get_snapshot(&connectivity_state);
    power_change_pending = connectivity_state.busy;
    power_change_enabled = enabled;
    power_change_cancelled = false;
    power_change_timed_out = false;
    power_change_deadline = current_tick + HIBY_BT_UI_WAIT_STEPS * (HZ / 10 ? HZ / 10 : 1);
    if (power_change_pending)
        return BLUETOOTH_UI_OK;
    enum hiby_connectivity_result result = power_change_result(enabled);
    show_message(HZ, connectivity_result_label(result));
    return result == HIBY_CONNECTIVITY_OK ? BLUETOOTH_UI_OK : BLUETOOTH_UI_FAILED;
}

static int main_action(int action, struct gui_synclist *lists)
{
    unsigned int generation = connectivity_state.generation;
    bool busy = connectivity_state.busy;
    unsigned int bluetooth_generation = menu_state.generation;
    bool bluetooth_busy = menu_state.busy;
    hiby_connectivity_get_snapshot(&connectivity_state);
    hiby_bluetooth_get_snapshot(&menu_state);
    main_redraw_pending |= generation != connectivity_state.generation ||
        busy != connectivity_state.busy || bluetooth_generation != menu_state.generation ||
        bluetooth_busy != menu_state.busy;
    if (operation_wait)
    {
        bool cancel = action == ACTION_STD_CANCEL || action == ACTION_TREE_WPS ||
                      action == SYS_USB_CONNECTED;
        operation_wait->usb |= action == SYS_USB_CONNECTED;
        if (menu_state.busy && TIME_AFTER(current_tick, operation_wait->deadline))
        {
            if (operation_wait->cancelling)
            {
                operation_wait->timed_out = true;
                operation_wait->done = true;
            }
            else
            {
                operation_wait->timed_out = true;
                hiby_bluetooth_set_inhibited(true);
                hiby_connectivity_cancel();
                cancel = true;
            }
        }
        if (cancel && !operation_wait->cancelling)
        {
            operation_wait->cancelling = true;
            operation_wait->deadline = current_tick + HIBY_BT_UI_SETTLE_STEPS * (HZ / 10 ? HZ / 10 : 1);
            hiby_bluetooth_cancel();
        }
        if (!menu_state.busy || operation_wait->done)
        {
            operation_wait->done = true;
            return operation_wait->usb ? SYS_USB_CONNECTED : ACTION_STD_CANCEL;
        }
        if (cancel)
            return ACTION_NONE;
    }
    if (power_change_pending && connectivity_state.busy &&
        TIME_AFTER(current_tick, power_change_deadline))
    {
        if (!power_change_cancelled)
        {
            power_change_cancelled = true;
            power_change_timed_out = true;
            hiby_connectivity_cancel();
            power_change_deadline = current_tick + HIBY_BT_UI_SETTLE_STEPS * (HZ / 10 ? HZ / 10 : 1);
        }
        else
        {
            power_change_pending = false;
            show_message(HZ, LANG_HIBY_BT_TIMEOUT);
        }
    }
    if (power_change_pending && !connectivity_state.busy)
    {
        power_change_pending = false;
        enum hiby_connectivity_result result = power_change_timed_out ? HIBY_CONNECTIVITY_TIMEOUT :
            power_change_cancelled ? HIBY_CONNECTIVITY_CANCELLED : power_change_result(power_change_enabled);
        if (result != HIBY_CONNECTIVITY_OK)
            show_message(HZ, connectivity_result_label(result));
        else if (action == ACTION_NONE && gui_synclist_get_sel_pos(lists) == 0)
            main_talk(0, NULL);
        main_redraw_pending = true;
    }
    if (connectivity_state.busy && (action == ACTION_STD_CANCEL || action == ACTION_TREE_WPS ||
                                   action == SYS_USB_CONNECTED) && !power_change_cancelled)
    {
        power_change_cancelled = true;
        hiby_connectivity_cancel();
    }
    if (action == ACTION_STD_OK && (connectivity_state.busy || menu_state.busy))
    {
        int selected = gui_synclist_get_sel_pos(lists);
        if (!operation_wait && (selected == 5 || (selected == 0 && !connectivity_state.busy)))
            return action;
        show_message(0, LANG_HIBY_BT_BUSY);
        return ACTION_NONE;
    }
    if (main_redraw_pending && (action == ACTION_NONE || action == ACTION_REDRAW))
    {
        main_redraw_pending = false;
        return ACTION_REDRAW;
    }
    return action;
}

static int show_devices(bool paired)
{
    int result = run_operation(paired ? HIBY_BT_REFRESH : HIBY_BT_SCAN, NULL, false);
    if (result != BLUETOOTH_UI_OK)
        return result;
    size_t count = 0;
    for (size_t position = 0; position < menu_state.count && position < HIBY_BT_MAX_DEVICES;
         ++position)
    {
        if (menu_state.devices[position].paired == paired)
            menu_state.devices[count++] = menu_state.devices[position];
    }
    menu_state.count = count;
    if (!menu_state.count)
    {
        show_message(HZ, paired ? LANG_HIBY_BT_PAIRED_EMPTY : LANG_HIBY_BT_UNPAIRED_EMPTY);
        return 0;
    }
    struct simplelist_info info;
    int title = paired ? LANG_HIBY_BT_PAIRED_DEVICES : LANG_HIBY_BT_PAIR_NEW;
    simplelist_info_init(&info, str(title), (int)menu_state.count, &menu_state);
    info.get_name = device_name;
    info.get_talk = device_talk;
    if (simplelist_show_list(&info))
        return 1;
    if (info.selection < 0 || (size_t)info.selection >= menu_state.count)
        return 0;
    char address[18];
    memcpy(address, menu_state.devices[info.selection].address, sizeof(address));
    if (!paired)
        return perform_operation(HIBY_BT_CONNECT, address);
    const int device_count = sizeof(device_labels) / sizeof(device_labels[0]);
    int choice = choose_label(title, device_labels, device_count, 0);
    if (choice == -2)
        return 1;
    if (choice == 0)
        return perform_operation(HIBY_BT_CONNECT, address);
    if (choice == 1)
    {
        const int confirmation[] = { LANG_HIBY_BT_KEEP_DEVICE, LANG_HIBY_BT_REMOVE };
        int confirmed = choose_label(LANG_HIBY_BT_REMOVE_CONFIRM, confirmation, 2, 0);
        if (confirmed == -2)
            return BLUETOOTH_UI_USB;
        if (confirmed == 1)
            return perform_operation(HIBY_BT_REMOVE, address);
    }
    return 0;
}

int hiby_bluetooth_menu(void)
{
    if (!hiby_connectivity_init())
    {
        show_message(HZ, LANG_HIBY_CONNECTIVITY_FAILED);
        return 0;
    }
#ifndef SIMULATOR
    if (!hiby_bluetooth_init())
    {
        hiby_bluetooth_get_snapshot(&menu_state);
        return show_result(menu_state.error);
    }
    hiby_connectivity_get_snapshot(&connectivity_state);
    hiby_bluetooth_get_snapshot(&menu_state);
    if (!connectivity_state.busy && !menu_state.busy &&
        run_operation(HIBY_BT_REFRESH, NULL, false) == BLUETOOTH_UI_USB)
        return BLUETOOTH_UI_USB;
#endif
    int selected = 0;
    for (;;)
    {
        selected = choose_main(selected);
        if (selected < 0)
            return selected == -2;
        int result = 0;
        switch (selected)
        {
            case 0: result = toggle_power(); break;
            case 1: result = show_devices(true); break;
            case 2: result = show_devices(false); break;
            case 3: result = perform_operation(HIBY_BT_DISCONNECT, NULL); break;
            case 5: result = bluetooth_preferences_menu(); break;
            case 6:
            {
                struct hiby_bt_preferences preferences;
                if (hiby_bt_preferences_get(&preferences))
                    show_message(HZ, LANG_HIBY_BT_SETTINGS_ERROR);
                else if (!preferences.last_address[0])
                    show_message(HZ, LANG_HIBY_BT_NO_LAST_DEVICE);
                else
                    result = perform_operation(HIBY_BT_CONNECT_PAIRED, preferences.last_address);
                break;
            }
            case 4:
                hiby_bluetooth_get_snapshot(&menu_state);
                if (!menu_state.busy)
                {
                    result = run_operation(HIBY_BT_REFRESH, NULL, false);
                    hiby_bluetooth_get_snapshot(&menu_state);
                    if (result != BLUETOOTH_UI_OK || menu_state.error != HIBY_BT_OK)
                        break;
                }
                if (menu_state.busy)
                    show_message(HZ, LANG_HIBY_BT_WORKING);
                else if (menu_state.error != HIBY_BT_OK)
                    show_result(menu_state.error);
                else if (!menu_state.available)
                    show_message(HZ, LANG_HIBY_BT_UNAVAILABLE);
                else if (!menu_state.power_known)
                    show_message(HZ, LANG_HIBY_BT_POWER_UNKNOWN);
                else if (menu_state.enabled && menu_state.connected_address[0])
                {
                    talk_id(LANG_HIBY_BT_CONNECTED, false);
                    if (tts_is_available())
                        tts_speak(menu_state.connected_name, strlen(menu_state.connected_name), true);
                    else
                        talk_spell(menu_state.connected_name, true);
                    splashf_silent(HZ, "%s: %s", str(LANG_HIBY_BT_CONNECTED), menu_state.connected_name);
                }
                else
                    show_message(HZ, menu_state.enabled ? LANG_HIBY_BT_ENABLED : LANG_HIBY_BT_DISABLED);
                if (!menu_state.busy && menu_state.enabled)
                {
                    struct hiby_bt_service_status status;
                    hiby_bluetooth_service_get_status(&status);
                    if (status.running && status.allowed)
                    {
                        talk_id(status.monitoring ? LANG_HIBY_BT_MONITOR_ACTIVE :
                                LANG_HIBY_BT_MONITOR_UNAVAILABLE, true);
                        if (status.reconnecting)
                            talk_id(LANG_HIBY_BT_RECONNECTING, true);
                        if (status.storage_error)
                            talk_id(LANG_HIBY_BT_SETTINGS_ERROR, true);
                    }
                }
                break;
        }
        if (result == BLUETOOTH_UI_USB)
            return result;
    }
}
#endif
