#ifndef HIBY_BT_SERVICE_HOST_TEST
#include "config.h"
#endif
#include "hiby_bluetooth_service.h"
#include "hiby_bluetooth.h"
#include "hiby_bluetooth_settings.h"
#include "bluetooth_policy.h"
#include <stdio.h>
#include <string.h>

#if (defined(HIBY_LINUX) && !defined(SIMULATOR)) || defined(HIBY_BT_SERVICE_HOST_TEST)
#include <pthread.h>
#include <time.h>
#include "bluetooth-monitor-hiby.h"
#include "pcm-hiby.h"
#ifdef HIBY_BT_SERVICE_HOST_TEST
#include "hiby-bluetooth-service-test.h"
#else
#include "audio.h"
#include "button.h"
#include "kernel.h"
#include "lang.h"
#include "settings.h"
#include "talk.h"
#include "tts.h"
#endif

enum bluetooth_notification
{
    BLUETOOTH_NOTIFICATION_NONE,
    BLUETOOTH_NOTIFICATION_CONNECTED,
    BLUETOOTH_NOTIFICATION_LOST,
    BLUETOOTH_NOTIFICATION_RETRY_FAILED
};

static pthread_mutex_t service_mutex = PTHREAD_MUTEX_INITIALIZER;
static struct hiby_bt_service_status service_status;
static bool service_stopping;
static bool startup_pending;
static unsigned int manual_generation;
static unsigned int permission_generation;
static unsigned int startup_generation;
static unsigned int result_generation;
static enum hiby_bt_error completed_result;
static struct hiby_bt_request completed_request;
static unsigned int connection_generation;
static unsigned int completed_connection_intent;
static char completed_address[18];
static char completed_name[HIBY_BT_NAME_SIZE];
static enum bluetooth_notification notification;
static unsigned int notification_generation;
static unsigned int notification_permission;
static char notification_name[HIBY_BT_NAME_SIZE];
static unsigned int service_thread_id;
static long service_stack[4 * DEFAULT_STACK_SIZE / sizeof(long)];
static struct bluetooth_reconnect_policy reconnect;
static unsigned int seen_manual_generation;
static unsigned int seen_startup_generation;
static unsigned int seen_result_generation;
static unsigned int seen_connection_generation;
static uint32_t seen_pcm_loss;
static bool request_pending;
static enum hiby_bt_operation pending_operation;
static struct hiby_bt_request pending_request;
static bool verify_pending;
static bool connected;
static unsigned int connected_generation;
static char connected_address[18];
static char connected_name[HIBY_BT_NAME_SIZE];
static unsigned int monitor_failures;
static long long monitor_retry;
static long long next_verify;

static long long service_clock(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value))
        return -1;
    return (long long)value.tv_sec * 1000 + value.tv_nsec / 1000000;
}

void hiby_bluetooth_service_allow(bool allowed)
{
    pthread_mutex_lock(&service_mutex);
    allowed = allowed && !service_stopping;
    if (allowed != service_status.allowed)
        ++permission_generation;
    startup_pending = false;
    if (allowed && !service_status.allowed && !service_stopping)
    {
        service_status.suppressed = false;
        ++startup_generation;
    }
    service_status.allowed = allowed && !service_stopping;
    pthread_mutex_unlock(&service_mutex);
}

bool hiby_bluetooth_service_requested(struct hiby_bt_request *request,
    const struct hiby_bt_request *expected)
{
    pthread_mutex_lock(&service_mutex);
    if (service_stopping || (request->automatic && (!expected || !service_status.allowed ||
        expected->intent != manual_generation || expected->permission != permission_generation ||
        (request->operation == HIBY_BT_CONNECT_PAIRED && service_status.suppressed))))
    {
        pthread_mutex_unlock(&service_mutex);
        return false;
    }
    if (!request->automatic && request->operation != HIBY_BT_REFRESH &&
        request->operation != HIBY_BT_VERIFY_LINK)
    {
        ++manual_generation;
        notification = BLUETOOTH_NOTIFICATION_NONE;
        if (request->operation == HIBY_BT_ENABLE)
            startup_pending = true;
        else if (request->operation == HIBY_BT_DISABLE)
        {
            if (service_status.allowed)
                ++permission_generation;
            service_status.allowed = false;
        }
        else
            service_status.suppressed = request->operation != HIBY_BT_CONNECT &&
                request->operation != HIBY_BT_CONNECT_PAIRED;
    }
    request->intent = manual_generation;
    request->permission = permission_generation;
    pthread_mutex_unlock(&service_mutex);
    return true;
}

void hiby_bluetooth_service_cancelled(void)
{
    pthread_mutex_lock(&service_mutex);
    ++manual_generation;
    service_status.suppressed = true;
    notification = BLUETOOTH_NOTIFICATION_NONE;
    pthread_mutex_unlock(&service_mutex);
}

static bool request_current_locked(const struct hiby_bt_request *request)
{
    return !service_stopping && request->intent == manual_generation &&
        (!request->automatic || (service_status.allowed &&
         request->permission == permission_generation &&
         (request->operation != HIBY_BT_CONNECT_PAIRED || !service_status.suppressed)));
}

bool hiby_bluetooth_service_current(const struct hiby_bt_request *request)
{
    pthread_mutex_lock(&service_mutex);
    bool current = request_current_locked(request);
    pthread_mutex_unlock(&service_mutex);
    return current;
}

void hiby_bluetooth_service_persist(const struct hiby_bt_request *request,
    const char *address, const struct hiby_bt_snapshot *snapshot)
{
    int storage_error = 0;
    if (!request->automatic && snapshot->error == HIBY_BT_OK)
    {
        if ((request->operation == HIBY_BT_CONNECT || request->operation == HIBY_BT_CONNECT_PAIRED) &&
            hiby_bt_valid_address(address) && !strcmp(address, snapshot->connected_address))
            storage_error = hiby_bt_preferences_remember(address);
        else if (request->operation == HIBY_BT_REMOVE && hiby_bt_valid_address(address))
            storage_error = hiby_bt_preferences_forget(address);
    }
    pthread_mutex_lock(&service_mutex);
    if (storage_error)
        service_status.storage_error = storage_error;
    pthread_mutex_unlock(&service_mutex);
}

void hiby_bluetooth_service_completed(const struct hiby_bt_request *request,
    struct hiby_bt_snapshot *snapshot, struct hiby_bt_snapshot *published)
{
    pthread_mutex_lock(&service_mutex);
    if (!request_current_locked(request))
    {
        snapshot->error = HIBY_BT_CANCELLED;
        snapshot->power_known = false;
    }
    *published = *snapshot;
    if (request->automatic)
    {
        completed_request = *request;
        completed_result = snapshot->error;
        ++result_generation;
    }
    if (snapshot->error == HIBY_BT_OK &&
        (request->operation == HIBY_BT_CONNECT || request->operation == HIBY_BT_CONNECT_PAIRED) &&
        hiby_bt_valid_address(snapshot->connected_address))
    {
        ++connection_generation;
        completed_connection_intent = request->intent;
        memcpy(completed_address, snapshot->connected_address, sizeof(completed_address));
        memcpy(completed_name, snapshot->connected_name, sizeof(completed_name));
    }
    pthread_mutex_unlock(&service_mutex);
}

void hiby_bluetooth_service_observe(struct hiby_bt_service_observation *observation)
{
    pthread_mutex_lock(&service_mutex);
    *observation = (struct hiby_bt_service_observation) {
        .allowed = service_status.allowed && !service_stopping,
        .suppressed = service_status.suppressed,
        .intent = manual_generation,
        .permission = permission_generation,
        .startup = startup_generation,
        .completion = result_generation,
        .request = completed_request,
        .result = completed_result,
        .connection = connection_generation,
        .connection_intent = completed_connection_intent
    };
    memcpy(observation->address, completed_address, sizeof(observation->address));
    memcpy(observation->name, completed_name, sizeof(observation->name));
    pthread_mutex_unlock(&service_mutex);
}

void hiby_bluetooth_service_get_status(struct hiby_bt_service_status *status)
{
    if (!status)
        return;
    pthread_mutex_lock(&service_mutex);
    *status = service_status;
    pthread_mutex_unlock(&service_mutex);
}

static bool intent_matches(unsigned int generation)
{
    pthread_mutex_lock(&service_mutex);
    bool matches = generation == manual_generation && !service_stopping;
    pthread_mutex_unlock(&service_mutex);
    return matches;
}

static void announce_later(enum bluetooth_notification message, unsigned int generation,
    unsigned int permission, const char *name)
{
    pthread_mutex_lock(&service_mutex);
    if (manual_generation == generation && permission_generation == permission &&
        service_status.allowed && !service_stopping &&
        (!service_status.suppressed || message == BLUETOOTH_NOTIFICATION_LOST))
    {
        notification = message;
        notification_generation = generation;
        notification_permission = permission;
        snprintf(notification_name, sizeof(notification_name), "%s", name ? name : "");
    }
    pthread_mutex_unlock(&service_mutex);
}

struct loss_pause_context
{
    unsigned int intent;
    unsigned int permission;
    uint32_t route_intent;
};

static bool begin_loss_pause(void *context)
{
    const struct loss_pause_context *loss = context;
    struct hiby_pcm_output_status output;
    if (!hiby_pcm_get_output_status(&output) ||
        output.route_intent_generation != loss->route_intent)
        return false;
    pthread_mutex_lock(&service_mutex);
    if (loss->intent != manual_generation || loss->permission != permission_generation ||
        !service_status.allowed || service_stopping)
    {
        pthread_mutex_unlock(&service_mutex);
        return false;
    }
    return true;
}

static void end_loss_pause(void *context)
{
    (void)context;
    pthread_mutex_unlock(&service_mutex);
}

static void service_poll(void)
{
    struct hiby_bt_preferences preferences;
    int storage_error = hiby_bt_preferences_get(&preferences);
    struct hiby_bt_snapshot snapshot;
    struct hiby_bt_service_observation observation;
    hiby_bluetooth_get_observation(&snapshot, &observation);
    struct hiby_pcm_output_status output;
    bool output_known = hiby_pcm_get_output_status(&output);
    unsigned int playback_generation = audio_playback_generation();
    long long now = service_clock();
    pthread_mutex_lock(&service_mutex);
    bool allowed = observation.allowed;
    bool suppressed = observation.suppressed;
    unsigned int intent = observation.intent;
    unsigned int startup = observation.startup;
    unsigned int completion = observation.completion;
    enum hiby_bt_operation finished_operation = observation.request.operation;
    enum hiby_bt_error finished_result = observation.result;
    unsigned int connection = observation.connection;
    unsigned int connection_intent = observation.connection_intent;
    char new_address[18];
    char new_name[HIBY_BT_NAME_SIZE];
    memcpy(new_address, observation.address, sizeof(new_address));
    memcpy(new_name, observation.name, sizeof(new_name));
    service_status.storage_error = storage_error;
    pthread_mutex_unlock(&service_mutex);

    bool new_intent = intent != seen_manual_generation;
    bool new_connection = connection != seen_connection_generation && connection_intent == intent;
    if (new_intent)
    {
        seen_manual_generation = intent;
        bluetooth_reconnect_stop(&reconnect);
        connected = false;
        if (output_known && !new_connection)
            seen_pcm_loss = output.loss_generation;
    }
    if (connection != seen_connection_generation)
    {
        seen_connection_generation = connection;
        if (new_connection && !suppressed)
        {
            connected = true;
            connected_generation = intent;
            memcpy(connected_address, new_address, sizeof(connected_address));
            memcpy(connected_name, new_name, sizeof(connected_name));
        }
    }
    if (request_pending && completion != seen_result_generation)
    {
        seen_result_generation = completion;
        if (finished_operation == pending_operation && observation.request.id == pending_request.id)
        {
            request_pending = false;
            if (pending_operation == HIBY_BT_CONNECT_PAIRED && !new_intent)
            {
                bluetooth_reconnect_attempted(&reconnect, now, finished_result == HIBY_BT_OK);
                if (finished_result == HIBY_BT_OK)
                    announce_later(BLUETOOTH_NOTIFICATION_CONNECTED, intent, observation.permission, new_name);
                else if (!reconnect.active && finished_result != HIBY_BT_CANCELLED)
                    announce_later(BLUETOOTH_NOTIFICATION_RETRY_FAILED, intent, observation.permission, NULL);
            }
        }
    }

    if (!allowed || storage_error || now < 0)
    {
        bluetooth_reconnect_stop(&reconnect);
        if (request_pending)
            hiby_bluetooth_cancel_automatic();
        if (hiby_bt_monitor_active())
            hiby_bt_monitor_stop();
        monitor_failures = 0;
        monitor_retry = 0;
        verify_pending = false;
    }
    else
    {
        if (suppressed)
        {
            bluetooth_reconnect_stop(&reconnect);
            if (request_pending && pending_operation == HIBY_BT_CONNECT_PAIRED)
                hiby_bluetooth_cancel_automatic();
        }
        if (startup != seen_startup_generation)
        {
            seen_startup_generation = startup;
            monitor_failures = 0;
            monitor_retry = 0;
            bool already_selected = new_connection ||
                (snapshot.connected_address[0] && output_known &&
                 output.active_output == HIBY_PCM_OUTPUT_BLUETOOTH &&
                 !strcmp(snapshot.connected_address, preferences.last_address));
            if (!suppressed && !already_selected && hiby_bt_valid_address(preferences.last_address))
                bluetooth_reconnect_begin(&reconnect, BLUETOOTH_RECONNECT_ON_STARTUP,
                    preferences.auto_mode, preferences.retry_seconds, now);
        }
        if (preferences.auto_mode == BLUETOOTH_RECONNECT_OFF)
        {
            bluetooth_reconnect_stop(&reconnect);
            if (request_pending && pending_operation == HIBY_BT_CONNECT_PAIRED)
                hiby_bluetooth_cancel_automatic();
        }
        if (snapshot.power_known && snapshot.enabled && !hiby_bt_monitor_active() &&
            monitor_failures < 3 && now >= monitor_retry)
        {
            if (hiby_bt_monitor_start())
                verify_pending = true;
            else
            {
                ++monitor_failures;
                monitor_retry = now + 5000 * monitor_failures;
            }
        }
        if (hiby_bt_monitor_active())
        {
            enum hiby_bt_monitor_result event = hiby_bt_monitor_wait(0);
            if (event == HIBY_BT_MONITOR_CHANGED)
                verify_pending = true;
            else if (event == HIBY_BT_MONITOR_FAILED)
            {
                hiby_bt_monitor_stop();
                ++monitor_failures;
                monitor_retry = now + 5000 * monitor_failures;
                verify_pending = true;
            }
        }
    }

    bool retry_was_active = reconnect.active;
    if (retry_was_active && !bluetooth_reconnect_remaining(&reconnect, now))
    {
        if (request_pending && pending_operation == HIBY_BT_CONNECT_PAIRED)
            hiby_bluetooth_cancel_automatic();
        if (allowed && !suppressed && !storage_error)
            announce_later(BLUETOOTH_NOTIFICATION_RETRY_FAILED, intent, observation.permission, NULL);
    }
    bool pcm_loss = output_known && output.loss_generation != seen_pcm_loss &&
        output.loss_intent_generation == output.route_intent_generation;
    if (output_known)
        seen_pcm_loss = output.loss_generation;
    bool verified_loss = connected && connected_generation == intent &&
        !snapshot.busy && !snapshot.connected_address[0] && snapshot.power_known &&
        (!snapshot.enabled || snapshot.error == HIBY_BT_CONNECT_FAILED);
    if (allowed && connected && (!new_intent || new_connection) &&
        connected_generation == intent && (pcm_loss || verified_loss))
    {
        connected = false;
        struct loss_pause_context loss = {
            .intent = intent,
            .permission = observation.permission,
            .route_intent = output_known ? output.route_intent_generation : 0
        };
        if (preferences.pause_on_loss && intent_matches(intent))
            audio_pause_guarded(playback_generation, begin_loss_pause, end_loss_pause, &loss);
        if (begin_loss_pause(&loss))
        {
            end_loss_pause(&loss);
            announce_later(BLUETOOTH_NOTIFICATION_LOST, intent, observation.permission, connected_name);
            if (!suppressed && !storage_error && snapshot.power_known && snapshot.enabled &&
                !strcmp(connected_address, preferences.last_address) && intent_matches(intent))
                bluetooth_reconnect_begin(&reconnect, BLUETOOTH_RECONNECT_ON_LOSS,
                    preferences.auto_mode, preferences.retry_seconds, now);
        }
    }
    if (allowed && !snapshot.busy && snapshot.connected_address[0] && output_known &&
        output.active_output == HIBY_PCM_OUTPUT_BLUETOOTH)
    {
        connected = true;
        connected_generation = intent;
        memcpy(connected_address, snapshot.connected_address, sizeof(connected_address));
        memcpy(connected_name, snapshot.connected_name, sizeof(connected_name));
    }
    if (!snapshot.busy && snapshot.power_known && !snapshot.enabled)
    {
        bluetooth_reconnect_stop(&reconnect);
        if (hiby_bt_monitor_active())
            hiby_bt_monitor_stop();
        verify_pending = false;
    }

    if (allowed && !storage_error && now >= 0 && !snapshot.busy &&
        !request_pending && snapshot.power_known && snapshot.enabled && intent_matches(intent))
    {
        struct hiby_bt_request expected = {
            .intent = intent,
            .permission = observation.permission
        };
        if (verify_pending && now >= next_verify)
        {
            if (hiby_bluetooth_request_guarded(HIBY_BT_VERIFY_LINK, NULL, 5000,
                                             &expected, &pending_request))
            {
                request_pending = true;
                pending_operation = HIBY_BT_VERIFY_LINK;
                seen_result_generation = completion;
                verify_pending = false;
                next_verify = now + 1000;
            }
        }
        else if (!suppressed && bluetooth_reconnect_due(&reconnect, now) &&
                 hiby_bt_valid_address(preferences.last_address))
        {
            int remaining = bluetooth_reconnect_remaining(&reconnect, now);
            unsigned int budget = remaining > 15000 ? 15000 : remaining > 0 ? (unsigned int)remaining : 0;
            if (budget && hiby_bluetooth_request_guarded(HIBY_BT_CONNECT_PAIRED,
                preferences.last_address, budget, &expected, &pending_request))
            {
                request_pending = true;
                pending_operation = HIBY_BT_CONNECT_PAIRED;
                seen_result_generation = completion;
            }
        }
    }
    pthread_mutex_lock(&service_mutex);
    service_status.monitoring = hiby_bt_monitor_active();
    service_status.reconnecting = reconnect.active;
    service_status.attempts = reconnect.attempts;
    pthread_mutex_unlock(&service_mutex);
}

static void bluetooth_service_thread(void)
{
    for (;;)
    {
        pthread_mutex_lock(&service_mutex);
        bool stop = service_stopping;
        bool active = service_status.allowed || startup_pending;
        pthread_mutex_unlock(&service_mutex);
        if (stop)
            break;
        service_poll();
        sleep(active ? MAX(1, HZ / 4) : HZ);
    }
    hiby_bt_monitor_stop();
}

bool hiby_bluetooth_service_start(void)
{
    if (service_thread_id)
        return true;
    struct hiby_bt_preferences preferences;
    int storage_error = hiby_bt_preferences_get(&preferences);
    bool monitor_ready = hiby_bt_monitor_init();
    (void)monitor_ready;
    pthread_mutex_lock(&service_mutex);
    memset(&service_status, 0, sizeof(service_status));
    service_status.storage_error = storage_error;
    startup_pending = true;
    service_stopping = false;
    notification = BLUETOOTH_NOTIFICATION_NONE;
    pthread_mutex_unlock(&service_mutex);
    memset(&reconnect, 0, sizeof(reconnect));
    request_pending = verify_pending = connected = false;
    monitor_failures = 0;
    monitor_retry = next_verify = 0;
    seen_manual_generation = manual_generation;
    seen_startup_generation = startup_generation;
    seen_result_generation = result_generation;
    seen_connection_generation = connection_generation;
    service_thread_id = create_thread(bluetooth_service_thread, service_stack,
        sizeof(service_stack), 0, "bluetooth policy"
        IF_PRIO(, PRIORITY_USER_INTERFACE) IF_COP(, CPU));
    pthread_mutex_lock(&service_mutex);
    service_status.running = service_thread_id != 0;
    pthread_mutex_unlock(&service_mutex);
    if (!service_thread_id)
        hiby_bt_monitor_shutdown();
    return service_thread_id != 0;
}

void hiby_bluetooth_service_shutdown(void)
{
    if (!service_thread_id)
        return;
    pthread_mutex_lock(&service_mutex);
    service_stopping = true;
    ++permission_generation;
    service_status.allowed = false;
    notification = BLUETOOTH_NOTIFICATION_NONE;
    pthread_mutex_unlock(&service_mutex);
    hiby_bluetooth_cancel_automatic();
    thread_wait(service_thread_id);
    service_thread_id = 0;
    hiby_bt_monitor_shutdown();
    pthread_mutex_lock(&service_mutex);
    service_status.running = false;
    service_status.monitoring = false;
    service_status.reconnecting = false;
    pthread_mutex_unlock(&service_mutex);
}

int hiby_bluetooth_service_adjust_timeout(int timeout)
{
    pthread_mutex_lock(&service_mutex);
    bool active = service_status.running &&
        (service_status.allowed || startup_pending || notification != BLUETOOTH_NOTIFICATION_NONE);
    pthread_mutex_unlock(&service_mutex);
    int interval = MAX(1, HZ / 2);
    return active && (timeout < 0 || timeout > interval) ? interval : timeout;
}

void hiby_bluetooth_service_process_notifications(void)
{
    if (!button_queue_empty())
        return;
    struct hiby_bt_preferences preferences;
    int error = hiby_bt_preferences_get(&preferences);
    char name[HIBY_BT_NAME_SIZE];
    pthread_mutex_lock(&service_mutex);
    enum bluetooth_notification message = notification;
    if (notification_generation != manual_generation ||
        notification_permission != permission_generation || !service_status.allowed || service_stopping)
        message = BLUETOOTH_NOTIFICATION_NONE;
    notification = BLUETOOTH_NOTIFICATION_NONE;
    memcpy(name, notification_name, sizeof(name));
    pthread_mutex_unlock(&service_mutex);
    if (message == BLUETOOTH_NOTIFICATION_NONE || error || !preferences.announce ||
        !talk_menus_enabled(&global_settings) || !talk_dynamic_enabled(&global_settings))
        return;
    int identifier = message == BLUETOOTH_NOTIFICATION_CONNECTED ? LANG_HIBY_BT_CONNECTED :
        message == BLUETOOTH_NOTIFICATION_LOST ? LANG_HIBY_BT_CONNECTION_LOST :
        LANG_HIBY_BT_RECONNECT_FAILED;
    talk_id(identifier, false);
    if (name[0])
    {
        if (tts_is_available())
            tts_speak(name, strlen(name), true);
        else
            talk_spell(name, true);
    }
}

#else

bool hiby_bluetooth_service_start(void) { return false; }
void hiby_bluetooth_service_shutdown(void) {}
void hiby_bluetooth_service_allow(bool allowed) { (void)allowed; }
bool hiby_bluetooth_service_requested(struct hiby_bt_request *request,
    const struct hiby_bt_request *expected)
{
    (void)request;
    (void)expected;
    return false;
}
bool hiby_bluetooth_service_current(const struct hiby_bt_request *request)
{ (void)request; return false; }
void hiby_bluetooth_service_completed(const struct hiby_bt_request *request,
    struct hiby_bt_snapshot *snapshot, struct hiby_bt_snapshot *published)
{
    (void)request;
    *published = *snapshot;
}
void hiby_bluetooth_service_persist(const struct hiby_bt_request *request,
    const char *address, const struct hiby_bt_snapshot *snapshot)
{
    (void)request;
    (void)address;
    (void)snapshot;
}
void hiby_bluetooth_service_observe(struct hiby_bt_service_observation *observation)
{ memset(observation, 0, sizeof(*observation)); }
void hiby_bluetooth_service_cancelled(void) {}
void hiby_bluetooth_service_get_status(struct hiby_bt_service_status *status)
{
    if (status)
        memset(status, 0, sizeof(*status));
}
int hiby_bluetooth_service_adjust_timeout(int timeout) { return timeout; }
void hiby_bluetooth_service_process_notifications(void) {}

#endif
