#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "kernel.h"
#include "thread.h"
#include "audio_thread.h"
#include "hiby_connectivity.h"
#include "power-control-hiby.h"
#define audio_pause_guarded integration_guarded_pause
#include "hiby_bluetooth_service.c"
#undef audio_pause_guarded

enum { PLAY_STOPPED = 0, PLAY_PLAYING = 1, PLAY_PAUSED = 3 };
static unsigned int play_status = PLAY_PLAYING;
static unsigned int pauses;
static unsigned int effects;
static bool ff_rw_mode;
static bool codec_skip_pending;
static int codec_skip_status;
static struct { bool fade_on_stop; } pause_settings;
static void iap_on_play_status(unsigned int value) { assert(value == PLAY_PAUSED || value == PLAY_PLAYING); }
static void audio_on_codec_complete(int value) { (void)value; }
static void pcmbuf_pause(bool value) { (void)value; }
static void pcmbuf_fade(bool fade, bool resume);
struct audio_resume_info { unsigned long elapsed; unsigned long offset; };
#define global_settings pause_settings
#define AUDIO_PAUSE_HOST_TEST
#include "playback.c"
#undef global_settings

struct service_test_settings global_settings = {true, true};
static const char peer[] = "AA:BB:CC:DD:EE:FF";
static int case_number;
static const char *variant = "default";
static bool negative_pause;
static bool real_backend;
static bool monitor_running;
static struct hiby_pcm_output_status output;
static struct event_queue test_audio_queue;
static struct queue_sender_list test_audio_senders;
static long audio_stack[32768];
static atomic_bool dispatch_arrived;
static atomic_bool dispatch_release;
static atomic_bool guarded_call_ready;
static atomic_bool guarded_send_entered;
static bool forced_before_capture;
static bool ui_before_send;
static unsigned int manual_plays;
static atomic_bool gate_reached;
static atomic_bool gate_release;
static atomic_bool fsync_reached;
static atomic_bool fsync_release;
static atomic_bool reader_entered;
static atomic_bool reader_done;
static atomic_bool backend_gate;
static atomic_bool publication_gate;
static atomic_bool observation_gate;
static atomic_bool persistence_gate;
static atomic_bool backend_timeout;
static atomic_uint backend_calls;
static unsigned int speech_count;
static pthread_t framework_pthread;
static unsigned int framework_main;
static unsigned int audio_identifier;
static unsigned int sender_identifier;
static unsigned int observed_sender;
static struct hiby_bt_snapshot reader_snapshot;
static struct hiby_bt_service_observation reader_observation;

volatile long current_tick;
uintptr_t *stackbegin;
uintptr_t *stackend;

void panicf(const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    abort();
}

void fixture_core_idle(void) { abort(); }

static void wait_flag(atomic_bool *flag)
{
    struct timespec limit;
    clock_gettime(CLOCK_MONOTONIC, &limit);
    for (;;)
    {
        if (atomic_load(flag))
            return;
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        assert(now.tv_sec - limit.tv_sec < 8);
        struct timespec delay = {.tv_nsec = 1000000};
        nanosleep(&delay, NULL);
    }
}

static void foreign_gate(void)
{
    atomic_store(&gate_reached, true);
    wait_flag(&gate_release);
}

enum hiby_bt_error __real_hiby_bt_backend_execute(enum hiby_bt_operation operation,
    const char *address, struct hiby_bt_snapshot *snapshot,
    hiby_bt_cancel_callback cancelled, void *context);

enum hiby_bt_error __wrap_hiby_bt_backend_execute(enum hiby_bt_operation operation,
    const char *address, struct hiby_bt_snapshot *snapshot,
    hiby_bt_cancel_callback cancelled, void *context)
{
    assert(!pthread_equal(pthread_self(), framework_pthread));
    atomic_fetch_add(&backend_calls, 1);
    enum hiby_bt_error result = HIBY_BT_OK;
    if (atomic_load(&backend_timeout))
        return HIBY_BT_TIMEOUT;
    if (real_backend && (operation == HIBY_BT_REFRESH || operation == HIBY_BT_VERIFY_LINK))
        result = __real_hiby_bt_backend_execute(operation, address, snapshot, cancelled, context);
    else
    {
        snapshot->available = snapshot->power_known = true;
        snapshot->enabled = operation != HIBY_BT_DISABLE;
        if (operation == HIBY_BT_CONNECT || operation == HIBY_BT_CONNECT_PAIRED)
        {
            strcpy(snapshot->connected_address, address);
            strcpy(snapshot->connected_name, "Integration peer");
        }
        if (operation == HIBY_BT_DISCONNECT || operation == HIBY_BT_REMOVE || operation == HIBY_BT_DISABLE)
            snapshot->connected_address[0] = snapshot->connected_name[0] = '\0';
    }
    if (atomic_load(&backend_gate))
        foreign_gate();
    return result;
}

void __real_hiby_bluetooth_service_completed(const struct hiby_bt_request *request,
    struct hiby_bt_snapshot *snapshot, struct hiby_bt_snapshot *published);
void __wrap_hiby_bluetooth_service_completed(const struct hiby_bt_request *request,
    struct hiby_bt_snapshot *snapshot, struct hiby_bt_snapshot *published)
{
    __real_hiby_bluetooth_service_completed(request, snapshot, published);
    if (atomic_load(&publication_gate))
        foreign_gate();
}

void __real_hiby_bluetooth_service_observe(struct hiby_bt_service_observation *observation);
void __wrap_hiby_bluetooth_service_observe(struct hiby_bt_service_observation *observation)
{
    if (atomic_load(&observation_gate))
        foreign_gate();
    __real_hiby_bluetooth_service_observe(observation);
}

int __real_fsync(int descriptor);
int __wrap_fsync(int descriptor)
{
    if (atomic_load(&persistence_gate))
    {
        atomic_store(&fsync_reached, true);
        wait_flag(&fsync_release);
    }
    return __real_fsync(descriptor);
}

static struct hiby_bt_snapshot settled(void)
{
    struct hiby_bt_snapshot snapshot;
    for (unsigned int step = 0; step < 8000; ++step)
    {
        hiby_bluetooth_get_snapshot(&snapshot);
        if (!snapshot.busy)
            return snapshot;
        struct timespec delay = {.tv_nsec = 1000000};
        nanosleep(&delay, NULL);
    }
    abort();
}

static void selected(void)
{
    assert(hiby_bluetooth_request(HIBY_BT_CONNECT, peer));
    assert(settled().error == HIBY_BT_OK);
    output.active_output = HIBY_PCM_OUTPUT_BLUETOOTH;
    output.route_intent_generation = 7;
    service_poll();
    settled();
    service_poll();
    assert(connected);
}

static void lose_output(void)
{
    output.active_output = HIBY_PCM_OUTPUT_WIRED;
    output.loss_intent_generation = output.route_intent_generation;
    ++output.loss_generation;
}

static void pcmbuf_fade(bool fade, bool resume)
{
    (void)fade;
    if (!resume)
        ++pauses;
    ++effects;
    assert(pthread_equal(pthread_self(), framework_pthread));
    assert(!pthread_mutex_trylock(&service_mutex));
    pthread_mutex_unlock(&service_mutex);
    if (case_number == 3)
        hiby_bluetooth_cancel();
}

intptr_t audio_queue_send(long identifier, intptr_t payload)
{
    if (identifier == Q_AUDIO_PAUSE_GUARDED || (negative_pause && identifier == Q_AUDIO_PAUSE))
    {
        observed_sender = thread_self();
        atomic_store(&guarded_send_entered, true);
    }
    else if ((identifier == Q_AUDIO_PAUSE && !payload) || identifier == Q_AUDIO_PLAY)
        atomic_store(&dispatch_release, true);
    assert(thread_self() != audio_identifier);
    return queue_send(&test_audio_queue, identifier, payload);
}

static void audio_receiver(void)
{
    struct queue_event event;
    for (;;)
    {
        queue_wait(&test_audio_queue, &event);
        assert(thread_self() == audio_identifier);
        if (event.id == Q_AUDIO_PAUSE_GUARDED)
        {
            atomic_store(&dispatch_arrived, true);
            while (!atomic_load(&dispatch_release))
                yield();
            audio_on_pause_guarded((struct guarded_pause_request *)event.data);
        }
        else if (event.id == Q_AUDIO_PLAY)
        {
            ++manual_plays;
            play_status = PLAY_PLAYING;
        }
        else
            audio_on_pause(event.data != 0);
        queue_reply(&test_audio_queue, 0);
    }
}

bool integration_guarded_pause(unsigned int generation, bool (*begin)(void *context),
    void (*end)(void *context), void *context)
{
    if (case_number == 1)
        hiby_bluetooth_cancel();
    if (case_number == 4)
        hiby_bluetooth_service_allow(false);
    if (case_number == 14 && !strcmp(variant, "route"))
        ++output.route_intent_generation;
    if (strstr(variant, "capture"))
    {
        atomic_store(&guarded_call_ready, true);
        if (!strstr(variant, "ready"))
        {
            forced_before_capture = true;
            while (!atomic_load(&dispatch_release))
                yield();
        }
    }
    if (negative_pause)
    {
        audio_pause();
        return true;
    }
    return audio_pause_guarded(generation, begin, end, context);
}

static void *canceller(void *unused)
{
    (void)unused;
    wait_flag(&dispatch_arrived);
    hiby_bluetooth_cancel();
    atomic_store(&dispatch_release, true);
    return NULL;
}

static void *reader(void *unused)
{
    (void)unused;
    atomic_store(&reader_entered, true);
    hiby_bluetooth_get_observation(&reader_snapshot, &reader_observation);
    atomic_store(&reader_done, true);
    return NULL;
}

static void sender(void)
{
    sender_identifier = thread_self();
    service_poll();
}

unsigned int service_test_create_thread(void (*entry)(void), void *stack,
    size_t size, unsigned int flags, const char *name)
{ (void)entry; (void)stack; (void)size; (void)flags; (void)name; return 17; }
void service_test_thread_wait(unsigned int identifier) { (void)identifier; }
void service_test_sleep(int ticks) { (void)ticks; }
bool button_queue_empty(void) { return true; }
unsigned int audio_status(void) { return play_status; }
bool talk_menus_enabled(const struct service_test_settings *settings) { return settings->menus; }
bool talk_dynamic_enabled(const struct service_test_settings *settings) { return settings->dynamic; }
int talk_id(int identifier, bool enqueue) { (void)identifier; (void)enqueue; ++speech_count; return 0; }
int talk_spell(const char *text, bool enqueue) { (void)text; (void)enqueue; return 0; }
bool tts_is_available(void) { return false; }
bool tts_speak(const char *text, size_t length, bool enqueue)
{ (void)text; (void)length; (void)enqueue; return false; }
bool hiby_bt_monitor_init(void) { return true; }
bool hiby_bt_monitor_start(void) { monitor_running = true; return true; }
enum hiby_bt_monitor_result hiby_bt_monitor_wait(int timeout)
{ (void)timeout; return HIBY_BT_MONITOR_IDLE; }
void hiby_bt_monitor_stop(void) { monitor_running = false; }
void hiby_bt_monitor_shutdown(void) { monitor_running = false; }
void hiby_bt_monitor_wake(void) {}
bool hiby_bt_monitor_active(void) { return monitor_running; }
bool hiby_pcm_get_output_status(struct hiby_pcm_output_status *status) { *status = output; return true; }
bool pcm_alsa_bluetooth_active(void) { return output.active_output == HIBY_PCM_OUTPUT_BLUETOOTH; }
int pcm_alsa_switch_playback_device_cancellable(const char *device,
    hiby_pcm_cancel_callback cancelled, void *context)
{ (void)device; return cancelled && cancelled(context) ? -ECANCELED : 0; }
int pcm_alsa_switch_playback_device(const char *device) { (void)device; return 0; }
void pcm_alsa_set_bluetooth_volume(int left, int right) { (void)left; (void)right; }
struct hiby_wifi_result hiby_wifi_get_state(void)
{ return (struct hiby_wifi_result){ .state = HIBY_WIFI_NO_RADIO }; }
struct hiby_wifi_result hiby_wifi_set_enabled(bool enabled)
{ (void)enabled; return hiby_wifi_get_state(); }
bool hiby_wifi_settled(void) { return true; }
void hiby_wifi_cancel(void) {}
void integration_connectivity_refresh(int barrier);

int main(int count, char **arguments)
{
    assert(count == 2 || count == 3);
    case_number = atoi(arguments[1]);
    if (count == 3)
        variant = arguments[2];
    negative_pause = !strcmp(variant, "unsafe-pause");
    framework_pthread = pthread_self();
    static uintptr_t main_stack_sentinel[2] __attribute__((aligned(16))) = {
        (uintptr_t)0xdeadbeefdeadbeefull, (uintptr_t)0xdeadbeefdeadbeefull
    };
    stackbegin = stackend = main_stack_sentinel;
    extern void init_threads(void);
    init_threads();
    init_queues();
    framework_main = thread_self();
    queue_init(&test_audio_queue, false);
    audio_identifier = create_thread(audio_receiver, audio_stack, sizeof(audio_stack), 0, "test audio"
        IF_PRIO(, PRIORITY_BUFFERING));
    assert(audio_identifier);
    queue_enable_queue_send(&test_audio_queue, &test_audio_senders, audio_identifier);
    bool manual_boundary = !strcmp(variant, "resume") || strstr(variant, "capture") || strstr(variant, "enqueue");
    atomic_store(&dispatch_release, case_number != 2 && !manual_boundary);
    assert(hiby_bt_preferences_set(HIBY_BT_PREF_AUTOCONNECT, BLUETOOTH_RECONNECT_OFF) == 0);
    assert(hiby_bluetooth_init());
    hiby_bluetooth_service_allow(true);
    seen_manual_generation = manual_generation;
    if (case_number <= 4 || case_number == 14)
    {
        selected();
        if (case_number == 14 && !strcmp(variant, "idle"))
            play_status = PLAY_STOPPED;
        if (case_number == 14 && !strcmp(variant, "paused"))
            play_status = PLAY_PAUSED;
        lose_output();
        pthread_t cancellation;
        if (case_number == 2)
            assert(!pthread_create(&cancellation, NULL, canceller, NULL));
        unsigned int policy = create_thread(sender, service_stack, sizeof(service_stack), 0, "test policy"
            IF_PRIO(, PRIORITY_USER_INTERFACE));
        assert(policy);
        if (manual_boundary)
        {
            atomic_bool *boundary = strstr(variant, "capture") ? &guarded_call_ready : &dispatch_arrived;
            while (!atomic_load(boundary))
                yield();
            ui_before_send = !atomic_load(&guarded_send_entered);
            assert(ui_before_send == (strstr(variant, "capture") && !strstr(variant, "ready")));
            if (strstr(variant, "play"))
                audio_play(123, 456);
            else
                audio_resume();
        }
        thread_wait(policy);
        if (case_number == 2)
            assert(!pthread_join(cancellation, NULL));
        assert(sender_identifier != framework_main && sender_identifier != audio_identifier);
        assert(observed_sender == sender_identifier);
        bool valid_loss = case_number == 3 || !strcmp(variant, "duplicate");
        assert(pauses == (unsigned int)valid_loss);
        unsigned int expected_state = valid_loss || !strcmp(variant, "paused") ? PLAY_PAUSED :
            !strcmp(variant, "idle") ? PLAY_STOPPED : PLAY_PLAYING;
        assert(play_status == expected_state);
        if (manual_boundary)
        {
            assert(forced_before_capture == ui_before_send);
            assert(manual_plays == (unsigned int)(strstr(variant, "play") != NULL));
        }
        if (case_number == 1 || case_number == 2 || case_number == 4 || !strcmp(variant, "route"))
            assert(notification == BLUETOOTH_NOTIFICATION_NONE);
        if (!strcmp(variant, "duplicate"))
        {
            service_poll();
            assert(pauses == 1);
        }
    }
    else if (case_number == 5)
    {
        atomic_store(&backend_gate, true);
        assert(hiby_bluetooth_request(HIBY_BT_CONNECT, peer));
        wait_flag(&gate_reached);
        hiby_bluetooth_cancel();
        atomic_store(&gate_release, true);
        assert(settled().error == HIBY_BT_CANCELLED);
        struct hiby_bt_preferences preferences;
        assert(!hiby_bt_preferences_get(&preferences) && !preferences.last_address[0]);
        assert(!connection_generation && !speech_count);
    }
    else if (case_number == 6 || case_number == 7)
    {
        atomic_store(case_number == 6 ? &publication_gate : &backend_gate, true);
        assert(hiby_bluetooth_request(HIBY_BT_CONNECT, peer));
        wait_flag(&gate_reached);
        pthread_t observer;
        if (case_number == 7)
        {
            atomic_store(&observation_gate, true);
            atomic_store(&gate_reached, false);
        }
        assert(!pthread_create(&observer, NULL, reader, NULL));
        wait_flag(&reader_entered);
        if (case_number == 7)
            wait_flag(&gate_reached);
        assert(!atomic_load(&reader_done));
        atomic_store(&gate_release, true);
        assert(!pthread_join(observer, NULL));
        atomic_store(&observation_gate, false);
        if (!reader_snapshot.busy)
            assert(reader_observation.connection && !strcmp(reader_snapshot.connected_name, reader_observation.name));
        else
            assert(!reader_observation.connection);
        assert(settled().error == HIBY_BT_OK);
    }
    else if (case_number == 8 || case_number == 9)
    {
        struct hiby_bt_service_observation observation;
        hiby_bluetooth_service_observe(&observation);
        struct hiby_bt_request expected = {.intent = observation.intent, .permission = observation.permission};
        if (case_number == 9)
        {
            unsigned int calls_before = atomic_load(&backend_calls);
            hiby_bluetooth_cancel();
            assert(!hiby_bluetooth_request_guarded(HIBY_BT_VERIFY_LINK, NULL, 5000, &expected, &pending_request));
            assert(!settled().busy);
            assert(atomic_load(&backend_calls) == calls_before);
        }
        else
        {
            struct hiby_bt_request old;
            assert(hiby_bluetooth_request_guarded(HIBY_BT_VERIFY_LINK, NULL, 5000, &expected, &old));
            struct hiby_bt_snapshot snapshot = settled();
            atomic_store(&backend_gate, true);
            assert(hiby_bluetooth_request_guarded(HIBY_BT_VERIFY_LINK, NULL, 5000, &expected, &pending_request));
            wait_flag(&gate_reached);
            pending_operation = HIBY_BT_VERIFY_LINK;
            request_pending = true;
            monitor_running = true;
            service_poll();
            assert(request_pending && pending_request.id != old.id && snapshot.error == HIBY_BT_OK);
            atomic_store(&gate_release, true);
            settled();
            service_poll();
            assert(!request_pending);
        }
    }
    else if (case_number >= 10 && case_number <= 13)
    {
        selected();
        real_backend = true;
        monitor_running = true;
        unsigned int startup_before = startup_generation;
        lose_output();
        integration_connectivity_refresh(0);
        struct hiby_connectivity_snapshot connectivity;
        hiby_connectivity_get_snapshot(&connectivity);
        assert(connectivity.bluetooth == HIBY_CONNECTIVITY_ON);
        assert(connectivity.result == HIBY_CONNECTIVITY_FAILED);
        assert(service_status.allowed && startup_generation == startup_before);
        if (case_number == 11)
        {
            service_poll();
            assert(pauses == 1);
            output.active_output = HIBY_PCM_OUTPUT_BLUETOOTH;
            service_poll();
            assert(pauses == 1 && service_status.allowed && monitor_running);
            assert(play_status == PLAY_PAUSED);
        }
        if (case_number == 12)
        {
            FILE *power = fopen("radio-power", "w");
            assert(power); fputs("unknown\n", power); fclose(power);
            integration_connectivity_refresh(0);
            assert(!service_status.allowed);
            power = fopen("radio-power", "w");
            assert(power); fputs("no\n", power); fclose(power);
            integration_connectivity_refresh(0);
            assert(!service_status.allowed);
            for (int barrier = 1; barrier <= 3; ++barrier)
            {
                integration_connectivity_refresh(barrier);
                assert(!service_status.allowed);
            }
            hiby_connectivity_shutdown();
            assert(!service_status.allowed);
            atomic_store(&backend_timeout, true);
            integration_connectivity_refresh(0);
            assert(!service_status.allowed);
            atomic_store(&backend_timeout, false);
            hiby_bluetooth_cancel();
            assert(service_status.suppressed);
        }
        if (case_number == 13)
        {
            real_backend = false;
            assert(hiby_bluetooth_request(HIBY_BT_DISCONNECT, NULL));
            settled();
            real_backend = true;
            output.active_output = HIBY_PCM_OUTPUT_BLUETOOTH;
            integration_connectivity_refresh(0);
            assert(service_status.suppressed && service_status.allowed);
            assert(startup_generation == startup_before);
        }
    }
    else if (case_number == 15)
    {
        atomic_store(&persistence_gate, true);
        assert(hiby_bluetooth_request(HIBY_BT_CONNECT, peer));
        wait_flag(&fsync_reached);
        assert(!settled().busy);
        assert(hiby_bluetooth_request(HIBY_BT_REMOVE, peer));
        atomic_store(&persistence_gate, false);
        atomic_store(&fsync_release, true);
        assert(settled().error == HIBY_BT_OK);
        hiby_bluetooth_shutdown();
        struct hiby_bt_preferences preferences;
        assert(!hiby_bt_preferences_get(&preferences) && !preferences.last_address[0]);
    }
    else
        abort();
    hiby_bluetooth_shutdown();
    printf("IT%02d actual-controller-service actual-kernel-queue-thread hosted-context "
           "mock-monitor-PCM-IAP dispatch-seam pauses=%u effects=%u "
           "ui-before-send=%u forced-switch=%u plays=%u\n", case_number, pauses, effects,
           ui_before_send, forced_before_capture, manual_plays);
    return 0;
}
