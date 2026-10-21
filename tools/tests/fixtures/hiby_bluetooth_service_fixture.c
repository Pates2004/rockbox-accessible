#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "hiby_bluetooth.h"
#include "hiby_bluetooth_settings.h"
#include "bluetooth-monitor-hiby.h"
#include "pcm-hiby.h"
#include "hiby_bluetooth_service_framework.h"

static const char peer[] = "AA:BB:CC:DD:EE:FF";
static const char other_peer[] = "11:22:33:44:55:66";
static const char *scenario;
static long long test_now = 1000;
static bool clock_failure;
static bool registered_context;
static unsigned int pauses;
static unsigned int resumes;
static unsigned int speech_count;
static int speech_identifiers[64];
static unsigned int tts_count;
static unsigned int spell_count;
static char spoken_name[128];
static bool tts_available = true;
static bool buttons_pending;
static bool create_failure;
static unsigned int create_calls;
static unsigned int thread_wait_calls;
static void (*thread_entry)(void);
static unsigned int sleep_calls;
static unsigned int loop_iterations = 2;
static int last_sleep;
static int read_fault;
static int write_fault;
static bool monitor_startable = true;
static bool monitor_running;
static unsigned int monitor_init_calls;
static unsigned int monitor_start_calls;
static unsigned int monitor_stop_calls;
static unsigned int monitor_shutdown_calls;
static unsigned int monitor_wait_calls;
static enum hiby_bt_monitor_result next_event;
static struct hiby_bt_snapshot controller;
static unsigned int cancellation_calls;
static bool reject_request;
static bool controller_automatic;

struct service_test_settings global_settings = {true, true};

struct request_record
{
    struct hiby_bt_request identity;
    enum hiby_bt_operation operation;
    unsigned int timeout;
    long long when;
    char address[18];
};

static struct request_record requests[128];
static unsigned int request_count;

static void fail_check(const char *expression, int line)
{
    fprintf(stderr, "service-check-failed scenario=%s line=%d expression=%s\n",
        scenario, line, expression);
    exit(86);
}

#define CHECK(expression) do { if (!(expression)) fail_check(#expression, __LINE__); } while (0)

static int service_fixture_clock_gettime(clockid_t clock, struct timespec *value)
{
    CHECK(clock == CLOCK_MONOTONIC);
    if (clock_failure)
    {
        errno = EIO;
        return -1;
    }
    value->tv_sec = (time_t)(test_now / 1000);
    value->tv_nsec = (long)(test_now % 1000) * 1000000;
    return 0;
}

int __real_open(const char *path, int flags, ...);
int __real_fsync(int descriptor);

int __wrap_open(const char *path, int flags, ...)
{
    if (read_fault && !(flags & O_WRONLY))
    {
        errno = read_fault;
        return -1;
    }
    return __real_open(path, flags, 0600);
}

int __wrap_fsync(int descriptor)
{
    if (write_fault)
    {
        errno = write_fault;
        return -1;
    }
    return __real_fsync(descriptor);
}

#define clock_gettime service_fixture_clock_gettime
#include "hiby_bluetooth_service.c"
#undef clock_gettime

static struct hiby_bt_request fixture_identity;
static unsigned int fixture_sequence;

static void fixture_service_requested(enum hiby_bt_operation operation, bool automatic)
{
    fixture_identity = (struct hiby_bt_request) {
        .id = ++fixture_sequence, .operation = operation, .automatic = automatic
    };
    struct hiby_bt_service_observation observation;
    hiby_bluetooth_service_observe(&observation);
    struct hiby_bt_request expected = {
        .intent = observation.intent, .permission = observation.permission
    };
    CHECK(hiby_bluetooth_service_requested(&fixture_identity, &expected));
}

static void fixture_service_completed(enum hiby_bt_operation operation,
    const char *address, enum hiby_bt_error result,
    const struct hiby_bt_snapshot *snapshot, bool automatic)
{
    struct hiby_bt_request identity = automatic ? requests[request_count - 1].identity : fixture_identity;
    CHECK(identity.operation == operation);
    struct hiby_bt_snapshot next = *snapshot;
    next.busy = false;
    next.error = result;
    hiby_bluetooth_service_completed(&identity, &next, &controller);
    hiby_bluetooth_service_persist(&identity, address, &next);
}

#define hiby_bluetooth_service_requested fixture_service_requested
#define hiby_bluetooth_service_completed fixture_service_completed

static unsigned int playback;
static bool monitor_ready = true;
static struct hiby_pcm_output_status output;
static bool output_known = true;

unsigned int service_test_create_thread(void (*entry)(void), void *stack,
    size_t stack_size, unsigned int flags, const char *name)
{
    CHECK(registered_context);
    CHECK(stack && stack_size >= DEFAULT_STACK_SIZE);
    CHECK(flags == 0 && name && name[0]);
    ++create_calls;
    if (create_failure)
        return 0;
    thread_entry = entry;
    return 17;
}

void service_test_thread_wait(unsigned int identifier)
{
    CHECK(registered_context && identifier == 17);
    ++thread_wait_calls;
    CHECK(thread_entry);
    thread_entry();
    thread_entry = NULL;
}

void service_test_sleep(int ticks)
{
    CHECK(registered_context && ticks > 0);
    last_sleep = ticks;
    ++sleep_calls;
    test_now += (long long)ticks * 1000 / HZ;
    if (sleep_calls >= loop_iterations)
        service_stopping = true;
}

bool button_queue_empty(void) { CHECK(registered_context); return !buttons_pending; }
unsigned int audio_status(void) { CHECK(registered_context); return playback; }
void audio_pause(void)
{
    CHECK(registered_context);
    ++pauses;
    playback |= AUDIO_STATUS_PAUSE;
}
unsigned int audio_playback_generation(void) { return 0; }
bool audio_pause_guarded(unsigned int generation, bool (*begin)(void *context),
    void (*end)(void *context), void *context)
{
    (void)generation;
    CHECK(registered_context);
    if (!(playback & AUDIO_STATUS_PLAY) || (playback & AUDIO_STATUS_PAUSE) || !begin(context))
        return false;
    playback |= AUDIO_STATUS_PAUSE;
    ++pauses;
    end(context);
    return true;
}
void audio_resume(void) { CHECK(registered_context); ++resumes; playback &= ~AUDIO_STATUS_PAUSE; }
bool talk_menus_enabled(const struct service_test_settings *settings) { return settings->menus; }
bool talk_dynamic_enabled(const struct service_test_settings *settings) { return settings->dynamic; }
bool tts_is_available(void) { CHECK(registered_context); return tts_available; }
int talk_id(int identifier, bool enqueue)
{
    CHECK(registered_context && !enqueue);
    CHECK(identifier >= 0 && identifier < SERVICE_LANGUAGE_COUNT);
    CHECK(service_language[identifier][0] && service_voice_language[identifier][0]);
    CHECK(speech_count < sizeof(speech_identifiers) / sizeof(speech_identifiers[0]));
    speech_identifiers[speech_count++] = identifier;
    return 0;
}
int talk_spell(const char *text, bool enqueue)
{
    CHECK(registered_context && enqueue && text && strlen(text) < sizeof(spoken_name));
    ++spell_count;
    strcpy(spoken_name, text);
    return 0;
}
bool tts_speak(const char *text, size_t length, bool enqueue)
{
    CHECK(registered_context && enqueue && text && length == strlen(text));
    CHECK(length < sizeof(spoken_name));
    ++tts_count;
    strcpy(spoken_name, text);
    return true;
}

bool hiby_bt_valid_address(const char *address)
{
    if (!address || strlen(address) != 17)
        return false;
    for (size_t position = 0; position < 17; ++position)
        if (position % 3 == 2 ? address[position] != ':' :
            !strchr("0123456789abcdefABCDEF", address[position]))
            return false;
    return true;
}

bool hiby_bt_monitor_init(void) { ++monitor_init_calls; return monitor_ready; }
bool hiby_bt_monitor_start(void)
{
    CHECK(registered_context);
    ++monitor_start_calls;
    monitor_running = monitor_ready && monitor_startable;
    return monitor_running;
}
enum hiby_bt_monitor_result hiby_bt_monitor_wait(int timeout_ms)
{
    CHECK(registered_context && timeout_ms == 0);
    ++monitor_wait_calls;
    enum hiby_bt_monitor_result event = next_event;
    next_event = HIBY_BT_MONITOR_IDLE;
    return event;
}
void hiby_bt_monitor_wake(void) {}
void hiby_bt_monitor_stop(void)
{
    CHECK(registered_context);
    ++monitor_stop_calls;
    monitor_running = false;
}
void hiby_bt_monitor_shutdown(void)
{
    CHECK(registered_context);
    ++monitor_shutdown_calls;
    monitor_running = false;
}
bool hiby_bt_monitor_active(void) { return monitor_running; }
bool hiby_pcm_get_output_status(struct hiby_pcm_output_status *status)
{
    *status = output;
    return output_known;
}
void hiby_bluetooth_get_snapshot(struct hiby_bt_snapshot *snapshot) { *snapshot = controller; }
void hiby_bluetooth_get_observation(struct hiby_bt_snapshot *snapshot,
    struct hiby_bt_service_observation *observation)
{
    *snapshot = controller;
    hiby_bluetooth_service_observe(observation);
}
bool hiby_bluetooth_cancel_automatic(void)
{
    ++cancellation_calls;
    bool cancelled = controller.busy && controller_automatic;
    return cancelled;
}
bool hiby_bluetooth_request_guarded(enum hiby_bt_operation operation,
    const char *address, unsigned int timeout_ms, const struct hiby_bt_request *expected,
    struct hiby_bt_request *issued)
{
    CHECK(registered_context);
    CHECK(operation == HIBY_BT_CONNECT_PAIRED || operation == HIBY_BT_VERIFY_LINK);
    CHECK(timeout_ms > 0 && timeout_ms <= 15000);
    CHECK(!controller.busy);
    CHECK(operation != HIBY_BT_CONNECT_PAIRED || hiby_bt_valid_address(address));
    if (reject_request || expected->intent != manual_generation ||
        expected->permission != permission_generation || !service_status.allowed)
        return false;
    CHECK(request_count < sizeof(requests) / sizeof(requests[0]));
    struct request_record *record = &requests[request_count++];
    record->operation = operation;
    fixture_service_requested(operation, true);
    record->identity = fixture_identity;
    if (issued)
        *issued = fixture_identity;
    record->timeout = timeout_ms;
    record->when = test_now;
    snprintf(record->address, sizeof(record->address), "%s", address ? address : "");
    controller.busy = true;
    controller_automatic = true;
    controller.power_known = false;
    return true;
}

static unsigned int operation_count(enum hiby_bt_operation operation)
{
    unsigned int count = 0;
    for (unsigned int position = 0; position < request_count; ++position)
        count += requests[position].operation == operation;
    return count;
}

static void poll_at(long long now)
{
    test_now = now;
    CHECK(!registered_context);
    registered_context = true;
    service_poll();
    registered_context = false;
}

static void notifications(void)
{
    CHECK(!registered_context);
    registered_context = true;
    hiby_bluetooth_service_process_notifications();
    registered_context = false;
}

static struct hiby_bt_service_status status(void)
{
    struct hiby_bt_service_status value;
    hiby_bluetooth_service_get_status(&value);
    return value;
}

static void start_service(void)
{
    registered_context = true;
    CHECK(hiby_bluetooth_service_start());
    CHECK(status().running && create_calls == 1);
    registered_context = false;
}

static void stop_service(void)
{
    registered_context = true;
    hiby_bluetooth_service_shutdown();
    registered_context = false;
    CHECK(!status().running && !status().monitoring && !status().reconnecting);
    CHECK(!monitor_running);
}

static void finish_request(enum hiby_bt_error result, bool connected_result)
{
    CHECK(!registered_context && controller.busy && request_count);
    struct request_record *record = &requests[request_count - 1];
    struct hiby_bt_snapshot next = controller;
    next.enabled = true;
    next.power_known = true;
    if (connected_result)
    {
        memcpy(next.connected_address, peer, sizeof(peer));
        strcpy(next.connected_name, "Test headphones");
        output.active_output = HIBY_PCM_OUTPUT_BLUETOOTH;
    }
    hiby_bluetooth_service_completed(record->operation,
        record->address[0] ? record->address : NULL, result, &next, true);
    next.busy = false;
    next.error = result;
    ++next.generation;
    controller = next;
}

static void ready_startup(int mode, bool remembered)
{
    CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, mode) == 0);
    if (remembered)
        CHECK(hiby_bt_preferences_remember(peer) == 0);
    start_service();
    controller.available = controller.enabled = controller.power_known = true;
    hiby_bluetooth_service_allow(true);
    poll_at(1000);
    CHECK(operation_count(HIBY_BT_VERIFY_LINK) == 1);
    CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
    finish_request(HIBY_BT_OK, false);
    poll_at(1001);
}

static void manual_connected(bool first_poll)
{
    CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, 0) == 0);
    start_service();
    controller.available = controller.enabled = controller.power_known = true;
    hiby_bluetooth_service_allow(true);
    hiby_bluetooth_service_requested(HIBY_BT_CONNECT, false);
    memcpy(controller.connected_address, peer, sizeof(peer));
    strcpy(controller.connected_name, "Test headphones");
    output.active_output = HIBY_PCM_OUTPUT_BLUETOOTH;
    output.initialized = true;
    output.route_intent_generation = 7;
    hiby_bluetooth_service_completed(HIBY_BT_CONNECT, peer, HIBY_BT_OK, &controller, false);
    if (first_poll)
    {
        poll_at(1000);
        if (controller.busy)
            finish_request(HIBY_BT_OK, false);
        poll_at(1001);
    }
    CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, 2) == 0);
}

static void lose_pcm(void)
{
    output.active_output = HIBY_PCM_OUTPUT_WIRED;
    output.loss_intent_generation = output.route_intent_generation;
    ++output.loss_generation;
    output.loss_error = -EIO;
}

static unsigned int count_descriptors(void)
{
    DIR *directory = opendir("/proc/self/fd");
    CHECK(directory);
    unsigned int count = 0;
    while (readdir(directory))
        ++count;
    CHECK(closedir(directory) == 0);
    return count;
}

static void report(void)
{
    printf("service-metrics requests=%u pauses=%u resumes=%u speech=%u tts=%u spell=%u "
        "monitor_starts=%u monitor_stops=%u monitor_waits=%u cancellations=%u\n",
        request_count, pauses, resumes, speech_count, tts_count, spell_count,
        monitor_start_calls, monitor_stop_calls, monitor_wait_calls, cancellation_calls);
    for (unsigned int position = 0; position < request_count; ++position)
        printf("service-request operation=%u when=%lld budget=%u address=%s\n",
            (unsigned int)requests[position].operation, requests[position].when,
            requests[position].timeout, requests[position].address);
}

static void run_scenario(void)
{
    if (!strcmp(scenario, "defaults"))
    {
        struct hiby_bt_preferences preferences;
        CHECK(hiby_bt_preferences_get(&preferences) == 0);
        CHECK(preferences.auto_mode == BLUETOOTH_RECONNECT_STARTUP_AND_LOSS);
        CHECK(preferences.retry_seconds == 120 && preferences.pause_on_loss && preferences.announce);
        CHECK(!preferences.last_address[0]);
    }
    else if (!strncmp(scenario, "startup_", 8))
    {
        int mode = !strcmp(scenario, "startup_off") ? 0 :
            !strcmp(scenario, "startup_only") ? 1 : 2;
        bool remembered = strcmp(scenario, "startup_no_peer") != 0;
        ready_startup(mode, remembered);
        bool expected = mode != 0 && remembered;
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == (unsigned int)expected);
        if (expected)
        {
            CHECK(!strcmp(requests[request_count - 1].address, peer));
            CHECK(requests[request_count - 1].timeout == 15000);
            finish_request(HIBY_BT_OK, true);
            poll_at(1002);
            CHECK(!status().reconnecting && status().attempts == 1);
            CHECK(pauses == 0 && resumes == 0);
        }
        stop_service();
    }
    else if (!strcmp(scenario, "backoff"))
    {
        ready_startup(2, true);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        finish_request(HIBY_BT_CONNECT_FAILED, false);
        poll_at(1002);
        CHECK(status().attempts == 1);
        poll_at(3001);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        poll_at(3002);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 2);
        finish_request(HIBY_BT_CONNECT_FAILED, false);
        poll_at(3003);
        poll_at(7002);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 2);
        poll_at(7003);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 3);
        stop_service();
    }
    else if (!strncmp(scenario, "window_", 7))
    {
        unsigned int seconds = (unsigned int)strtoul(scenario + 7, NULL, 10);
        CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, (int)seconds) == 0);
        ready_startup(2, true);
        for (long long now = 1500; now <= 1000 + (long long)seconds * 1000 + 20000; now += 500)
        {
            if (controller.busy)
            {
                struct request_record *record = &requests[request_count - 1];
                CHECK(record->timeout <= (unsigned int)(1000 + (long long)seconds * 1000 - record->when));
                finish_request(HIBY_BT_CONNECT_FAILED, false);
            }
            poll_at(now);
        }
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) > 1);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) <= 8);
        CHECK(!status().reconnecting);
        CHECK(pauses == 0 && resumes == 0);
        stop_service();
    }
    else if (!strcmp(scenario, "remaining_budget"))
    {
        CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, 30) == 0);
        CHECK(hiby_bt_preferences_remember(peer) == 0);
        start_service();
        controller.enabled = controller.power_known = true;
        hiby_bluetooth_service_allow(true);
        poll_at(1000);
        finish_request(HIBY_BT_OK, false);
        poll_at(30999);
        CHECK(request_count == 2 && requests[1].timeout == 1);
        finish_request(HIBY_BT_TIMEOUT, false);
        poll_at(31000);
        CHECK(!status().reconnecting);
        stop_service();
    }
    else if (!strncmp(scenario, "loss_", 5))
    {
        bool first_poll = strcmp(scenario, "loss_before_first_poll") != 0;
        manual_connected(first_poll);
        if (!strcmp(scenario, "loss_startup_only"))
            CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, 1) == 0);
        if (!strcmp(scenario, "loss_disabled"))
            CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, 0) == 0);
        if (!strcmp(scenario, "loss_keep_playing"))
            CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_PAUSE_ON_LOSS, 0) == 0);
        playback = !strcmp(scenario, "loss_idle") ? 0 : AUDIO_STATUS_PLAY;
        if (!strcmp(scenario, "loss_already_paused"))
            playback |= AUDIO_STATUS_PAUSE;
        lose_pcm();
        poll_at(1002);
        bool should_pause = strcmp(scenario, "loss_idle") &&
            strcmp(scenario, "loss_already_paused") && strcmp(scenario, "loss_keep_playing");
        CHECK(pauses == (unsigned int)should_pause && resumes == 0);
        if (controller.busy && requests[request_count - 1].operation == HIBY_BT_VERIFY_LINK)
            finish_request(HIBY_BT_OK, false);
        poll_at(1003);
        CHECK(pauses == (unsigned int)should_pause);
        notifications();
        CHECK(speech_count == 1 && speech_identifiers[0] == LANG_HIBY_BT_CONNECTION_LOST);
        CHECK(tts_count == 1 && !strcmp(spoken_name, "Test headphones"));
        bool retry = strcmp(scenario, "loss_startup_only") && strcmp(scenario, "loss_disabled");
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == (unsigned int)retry);
        if (controller.busy)
        {
            finish_request(HIBY_BT_OK, true);
            poll_at(1004);
            CHECK(resumes == 0 && pauses == (unsigned int)should_pause);
        }
        stop_service();
    }
    else if (!strncmp(scenario, "manual_", 7) && strcmp(scenario, "manual_success_before_startup_poll"))
    {
        manual_connected(true);
        playback = AUDIO_STATUS_PLAY;
        enum hiby_bt_operation operation = !strcmp(scenario, "manual_forget") ? HIBY_BT_REMOVE :
            !strcmp(scenario, "manual_off") ? HIBY_BT_DISABLE : HIBY_BT_DISCONNECT;
        hiby_bluetooth_service_requested(operation, false);
        controller.connected_address[0] = '\0';
        output.active_output = HIBY_PCM_OUTPUT_WIRED;
        hiby_bluetooth_service_completed(operation, peer, HIBY_BT_OK, &controller, false);
        if (operation == HIBY_BT_DISABLE)
            controller.enabled = false;
        poll_at(1002);
        lose_pcm();
        poll_at(2000);
        poll_at(200000);
        notifications();
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
        CHECK(pauses == 0 && resumes == 0 && speech_count == 0);
        if (operation == HIBY_BT_REMOVE)
        {
            struct hiby_bt_preferences preferences;
            CHECK(hiby_bt_preferences_get(&preferences) == 0 && !preferences.last_address[0]);
        }
        stop_service();
    }
    else if (!strcmp(scenario, "suppression_reset_radio_cycle"))
    {
        manual_connected(true);
        hiby_bluetooth_service_requested(HIBY_BT_DISCONNECT, false);
        controller.connected_address[0] = '\0';
        output.active_output = HIBY_PCM_OUTPUT_WIRED;
        poll_at(1002);
        CHECK(status().suppressed);
        hiby_bluetooth_service_allow(true);
        poll_at(1003);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
        hiby_bluetooth_service_allow(false);
        hiby_bluetooth_service_allow(true);
        poll_at(1004);
        CHECK(!status().suppressed);
        if (controller.busy)
            finish_request(HIBY_BT_OK, false);
        poll_at(2004);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        stop_service();
    }
    else if (!strcmp(scenario, "cancel_pending"))
    {
        ready_startup(2, true);
        hiby_bluetooth_service_cancelled();
        poll_at(1002);
        CHECK(status().suppressed && cancellation_calls > 0);
        finish_request(HIBY_BT_CANCELLED, false);
        poll_at(1003);
        poll_at(200000);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        CHECK(pauses == 0 && speech_count == 0);
        stop_service();
    }
    else if (!strcmp(scenario, "airplane_pending"))
    {
        ready_startup(2, true);
        hiby_bluetooth_service_allow(false);
        poll_at(1002);
        CHECK(cancellation_calls > 0 && !monitor_running);
        finish_request(HIBY_BT_CANCELLED, false);
        poll_at(200000);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        CHECK(pauses == 0 && resumes == 0);
        stop_service();
    }
    else if (!strcmp(scenario, "airplane_loss"))
    {
        manual_connected(true);
        playback = AUDIO_STATUS_PLAY;
        hiby_bluetooth_service_allow(false);
        lose_pcm();
        poll_at(1002);
        notifications();
        CHECK(pauses == 0 && speech_count == 0);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
        stop_service();
    }
    else if (!strncmp(scenario, "pcm_", 4))
    {
        manual_connected(true);
        playback = AUDIO_STATUS_PLAY;
        if (!strcmp(scenario, "pcm_old_loss_intent"))
        {
            lose_pcm();
            ++output.route_intent_generation;
        }
        else if (!strcmp(scenario, "pcm_manual_wired"))
        {
            ++output.route_intent_generation;
            output.active_output = HIBY_PCM_OUTPUT_WIRED;
        }
        else if (!strcmp(scenario, "pcm_unknown"))
            output_known = false;
        else if (!strcmp(scenario, "pcm_transient"))
        {
            output.active_output = HIBY_PCM_OUTPUT_NONE;
            ++output.error_generation;
            output.last_error = -EAGAIN;
        }
        else if (!strcmp(scenario, "pcm_rate_change"))
            ++output.state_generation;
        else
            CHECK(false);
        poll_at(1002);
        notifications();
        CHECK(pauses == 0 && resumes == 0 && speech_count == 0);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
        stop_service();
    }
    else if (!strcmp(scenario, "verified_loss"))
    {
        manual_connected(true);
        playback = AUDIO_STATUS_PLAY;
        controller.connected_address[0] = '\0';
        controller.error = HIBY_BT_CONNECT_FAILED;
        output.active_output = HIBY_PCM_OUTPUT_WIRED;
        poll_at(1002);
        CHECK(pauses == 1 && operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        notifications();
        CHECK(speech_count == 1 && speech_identifiers[0] == LANG_HIBY_BT_CONNECTION_LOST);
        stop_service();
    }
    else if (!strncmp(scenario, "suppressed_loss_", 16))
    {
        manual_connected(true);
        playback = AUDIO_STATUS_PLAY;
        if (!strcmp(scenario, "suppressed_loss_scan"))
        {
            hiby_bluetooth_service_requested(HIBY_BT_SCAN, false);
            controller.busy = true;
            poll_at(1002);
            controller.busy = false;
            controller.power_known = true;
            hiby_bluetooth_service_completed(HIBY_BT_SCAN, NULL, HIBY_BT_OK, &controller, false);
        }
        else
            hiby_bluetooth_service_cancelled();
        poll_at(1003);
        CHECK(status().suppressed && pauses == 0);
        CHECK(monitor_running);
        lose_pcm();
        poll_at(1004);
        notifications();
        CHECK(pauses == 1 && speech_count == 1);
        CHECK(speech_identifiers[0] == LANG_HIBY_BT_CONNECTION_LOST);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
        stop_service();
    }
    else if (!strcmp(scenario, "stale_loss_after_new_peer"))
    {
        manual_connected(true);
        hiby_bluetooth_service_requested(HIBY_BT_CONNECT, false);
        memcpy(controller.connected_address, other_peer, sizeof(other_peer));
        strcpy(controller.connected_name, "New headphones");
        ++output.route_intent_generation;
        hiby_bluetooth_service_completed(HIBY_BT_CONNECT, other_peer, HIBY_BT_OK, &controller, false);
        output.loss_generation++;
        output.loss_intent_generation = output.route_intent_generation - 1;
        playback = AUDIO_STATUS_PLAY;
        poll_at(1002);
        notifications();
        CHECK(pauses == 0 && speech_count == 0);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
        stop_service();
    }
    else if (!strcmp(scenario, "manual_success_before_startup_poll"))
    {
        manual_connected(false);
        poll_at(1000);
        if (controller.busy)
            finish_request(HIBY_BT_OK, false);
        poll_at(1001);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 0);
        CHECK(!status().reconnecting);
        stop_service();
    }
    else if (!strncmp(scenario, "monitor_", 8))
    {
        if (!strcmp(scenario, "monitor_failures"))
            monitor_startable = false;
        start_service();
        controller.enabled = controller.power_known = true;
        if (strcmp(scenario, "monitor_off"))
            hiby_bluetooth_service_allow(true);
        if (!strcmp(scenario, "monitor_unknown"))
            controller.power_known = false;
        if (!strcmp(scenario, "monitor_disabled"))
            controller.enabled = false;
        poll_at(1000);
        if (!strcmp(scenario, "monitor_failures"))
        {
            CHECK(monitor_start_calls == 1);
            poll_at(5999);
            CHECK(monitor_start_calls == 1);
            poll_at(6000);
            CHECK(monitor_start_calls == 2);
            poll_at(15999);
            CHECK(monitor_start_calls == 2);
            poll_at(16000);
            CHECK(monitor_start_calls == 3);
            poll_at(900000);
            CHECK(monitor_start_calls == 3 && request_count == 0);
        }
        else if (!strcmp(scenario, "monitor_idle"))
        {
            finish_request(HIBY_BT_OK, false);
            poll_at(1001);
            for (long long now = 1250; now < 1250000; now += 250)
                poll_at(now);
            CHECK(monitor_start_calls == 1 && request_count == 1);
        }
        else if (!strcmp(scenario, "monitor_burst"))
        {
            CHECK(request_count == 1 && controller.busy);
            for (long long now = 1001; now < 1030; ++now)
            {
                next_event = HIBY_BT_MONITOR_CHANGED;
                poll_at(now);
            }
            CHECK(request_count == 1);
            finish_request(HIBY_BT_OK, false);
            poll_at(1030);
            CHECK(request_count == 1);
            poll_at(2000);
            CHECK(request_count == 2 && requests[1].operation == HIBY_BT_VERIFY_LINK);
            finish_request(HIBY_BT_OK, false);
            poll_at(2001);
            poll_at(10000);
            CHECK(request_count == 2);
        }
        else if (!strcmp(scenario, "monitor_exit"))
        {
            finish_request(HIBY_BT_OK, false);
            poll_at(1001);
            next_event = HIBY_BT_MONITOR_FAILED;
            poll_at(1002);
            CHECK(!monitor_running && monitor_start_calls == 1);
            if (controller.busy)
                finish_request(HIBY_BT_OK, false);
            poll_at(6001);
            CHECK(monitor_start_calls == 1);
            if (controller.busy)
                finish_request(HIBY_BT_OK, false);
            poll_at(6002);
            CHECK(monitor_start_calls == 2);
        }
        else
            CHECK(monitor_start_calls == 0 && request_count == 0);
        stop_service();
    }
    else if (!strncmp(scenario, "notify_", 7))
    {
        if (!strcmp(scenario, "notify_manual_success"))
        {
            manual_connected(true);
            notifications();
            CHECK(speech_count == 0);
        }
        else
        {
            ready_startup(2, true);
            finish_request(HIBY_BT_OK, true);
            poll_at(1002);
            if (!strcmp(scenario, "notify_dynamic_off"))
                global_settings.dynamic = false;
            if (!strcmp(scenario, "notify_menus_off"))
                global_settings.menus = false;
            if (!strcmp(scenario, "notify_pref_off"))
                CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_ANNOUNCE, 0) == 0);
            if (!strcmp(scenario, "notify_spell"))
                tts_available = false;
            if (!strcmp(scenario, "notify_defer_input"))
            {
                buttons_pending = true;
                notifications();
                CHECK(speech_count == 0);
                buttons_pending = false;
            }
            if (!strcmp(scenario, "notify_new_manual"))
                hiby_bluetooth_service_requested(HIBY_BT_DISCONNECT, false);
            notifications();
            bool expected = !strcmp(scenario, "notify_connected") ||
                !strcmp(scenario, "notify_spell") || !strcmp(scenario, "notify_defer_input");
            CHECK(speech_count == (unsigned int)expected);
            if (expected)
            {
                CHECK(speech_identifiers[0] == LANG_HIBY_BT_CONNECTED);
                CHECK(!strcmp(spoken_name, "Test headphones"));
                CHECK(spell_count == (unsigned int)!tts_available);
                CHECK(tts_count == (unsigned int)tts_available);
            }
            global_settings.menus = global_settings.dynamic = true;
            CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_ANNOUNCE, 1) == 0);
            notifications();
            CHECK(speech_count == (unsigned int)expected);
        }
        stop_service();
    }
    else if (!strcmp(scenario, "clock_failure"))
    {
        ready_startup(2, true);
        finish_request(HIBY_BT_CONNECT_FAILED, false);
        clock_failure = true;
        poll_at(1002);
        CHECK(!monitor_running && !status().reconnecting);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        stop_service();
    }
    else if (!strncmp(scenario, "expiry_", 7))
    {
        CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_RETRY_SECONDS, 30) == 0);
        ready_startup(2, true);
        unsigned int intent_before = manual_generation;
        poll_at(31000);
        CHECK(cancellation_calls > 0 && manual_generation == intent_before);
        CHECK(!reconnect.active);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        CHECK(!status().reconnecting);
        if (!strcmp(scenario, "expiry_unknown"))
            output_known = false;
        finish_request(HIBY_BT_TIMEOUT, false);
        poll_at(31001);
        poll_at(200000);
        CHECK(!status().reconnecting);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        notifications();
        CHECK(speech_count == 1 && speech_identifiers[0] == LANG_HIBY_BT_RECONNECT_FAILED);
        stop_service();
    }
    else if (!strncmp(scenario, "config_off_", 11))
    {
        bool automatic = !strcmp(scenario, "config_off_auto_busy");
        if (automatic)
            ready_startup(2, true);
        else
        {
            manual_connected(true);
            controller.busy = true;
            controller.power_known = false;
            controller_automatic = false;
        }
        unsigned int intent_before = manual_generation;
        CHECK(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, 0) == 0);
        poll_at(1002);
        CHECK(cancellation_calls == (unsigned int)automatic);
        CHECK(manual_generation == intent_before && !status().suppressed);
        if (automatic)
        {
            finish_request(HIBY_BT_CANCELLED, false);
            poll_at(1003);
            CHECK(!status().reconnecting);
            CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        }
        else
            CHECK(controller.busy);
        CHECK(pauses == 0 && resumes == 0);
        stop_service();
    }
    else if (!strcmp(scenario, "request_rejected"))
    {
        ready_startup(2, true);
        finish_request(HIBY_BT_CONNECT_FAILED, false);
        poll_at(1002);
        reject_request = true;
        poll_at(3002);
        poll_at(3003);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 1);
        CHECK(status().attempts == 1);
        reject_request = false;
        poll_at(3004);
        CHECK(operation_count(HIBY_BT_CONNECT_PAIRED) == 2);
        stop_service();
    }
    else if (!strncmp(scenario, "storage_", 8))
    {
        if (!strcmp(scenario, "storage_read_error"))
        {
            read_fault = EIO;
            start_service();
            controller.enabled = controller.power_known = true;
            hiby_bluetooth_service_allow(true);
            poll_at(1002);
            CHECK(status().storage_error == EIO && !monitor_running && !status().reconnecting);
        }
        else if (!strcmp(scenario, "storage_corrupt"))
        {
            FILE *configuration = fopen("./bluetooth.cfg", "w");
            CHECK(configuration && fputs("invalid\n", configuration) >= 0 && fclose(configuration) == 0);
            start_service();
            controller.enabled = controller.power_known = true;
            hiby_bluetooth_service_allow(true);
            poll_at(1002);
            CHECK(status().storage_error == EINVAL && !monitor_running && !status().reconnecting);
        }
        else if (!strcmp(scenario, "storage_remember_failure"))
        {
            manual_connected(true);
            write_fault = EIO;
            hiby_bluetooth_service_requested(HIBY_BT_CONNECT, false);
            memcpy(controller.connected_address, other_peer, sizeof(other_peer));
            hiby_bluetooth_service_completed(HIBY_BT_CONNECT, other_peer, HIBY_BT_OK, &controller, false);
            CHECK(status().storage_error == EIO);
            poll_at(1002);
            CHECK(status().storage_error == EIO);
            struct hiby_bt_preferences preferences;
            CHECK(hiby_bt_preferences_get(&preferences) == EIO && !strcmp(preferences.last_address, peer));
        }
        else
            CHECK(false);
        stop_service();
    }
    else if (!strcmp(scenario, "create_failure"))
    {
        create_failure = true;
        registered_context = true;
        CHECK(!hiby_bluetooth_service_start());
        CHECK(!status().running && monitor_shutdown_calls == 1);
        hiby_bluetooth_service_shutdown();
        registered_context = false;
        CHECK(thread_wait_calls == 0 && request_count == 0);
    }
    else if (!strcmp(scenario, "idempotent_start_stop"))
    {
        start_service();
        registered_context = true;
        CHECK(hiby_bluetooth_service_start());
        CHECK(create_calls == 1 && monitor_init_calls == 1);
        registered_context = false;
        stop_service();
        unsigned int waits = thread_wait_calls;
        registered_context = true;
        hiby_bluetooth_service_shutdown();
        registered_context = false;
        CHECK(thread_wait_calls == waits && monitor_shutdown_calls == 1);
    }
    else if (!strcmp(scenario, "shutdown_pending"))
    {
        ready_startup(2, true);
        playback = AUDIO_STATUS_PLAY;
        stop_service();
        CHECK(cancellation_calls > 0 && pauses == 0 && resumes == 0);
        finish_request(HIBY_BT_CANCELLED, false);
        notifications();
        CHECK(speech_count == 0);
    }
    else if (!strncmp(scenario, "loop_", 5))
    {
        start_service();
        if (!strcmp(scenario, "loop_active"))
        {
            controller.enabled = controller.power_known = true;
            hiby_bluetooth_service_allow(true);
        }
        else
            hiby_bluetooth_service_allow(false);
        registered_context = true;
        CHECK(thread_entry);
        thread_entry();
        registered_context = false;
        CHECK(sleep_calls == loop_iterations);
        CHECK(last_sleep == (!strcmp(scenario, "loop_active") ? HZ / 4 : HZ));
        stop_service();
    }
    else if (!strcmp(scenario, "timeout_cap"))
    {
        start_service();
        hiby_bluetooth_service_allow(true);
        CHECK(hiby_bluetooth_service_adjust_timeout(-1) == HZ / 2);
        CHECK(hiby_bluetooth_service_adjust_timeout(HZ * 10) == HZ / 2);
        CHECK(hiby_bluetooth_service_adjust_timeout(0) == 0);
        CHECK(hiby_bluetooth_service_adjust_timeout(7) == 7);
        hiby_bluetooth_service_allow(false);
        CHECK(hiby_bluetooth_service_adjust_timeout(-1) == -1);
        stop_service();
        CHECK(hiby_bluetooth_service_adjust_timeout(-1) == -1);
    }
    else if (!strcmp(scenario, "fd_cycles"))
    {
        unsigned int before = count_descriptors();
        start_service();
        controller.enabled = controller.power_known = true;
        hiby_bluetooth_service_allow(true);
        for (long long now = 1000; now < 201000; now += 250)
        {
            poll_at(now);
            if (controller.busy)
                finish_request(HIBY_BT_OK, false);
        }
        stop_service();
        CHECK(count_descriptors() == before);
        CHECK(request_count == 1);
    }
    else
        CHECK(false);
}

int main(int count, char **arguments)
{
    CHECK(count == 2);
    scenario = arguments[1];
    CHECK(atexit(report) == 0);
    output.initialized = true;
    output.active_output = HIBY_PCM_OUTPUT_WIRED;
    run_scenario();
    CHECK(resumes == 0);
    printf("verified-service=%s\n", scenario);
    return 0;
}
