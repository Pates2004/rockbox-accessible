#define _DEFAULT_SOURCE 1
#include <assert.h>
#include <limits.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <spawn.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <time.h>
#include <sys/ioctl.h>
#include <sys/reboot.h>
#include "power-control-hiby.h"
#include "power-ui-labels.h"
#if defined(POWER_UI_SHUTDOWN) || defined(POWER_UI_INIT)
#include "power-ui-shutdown-environment.h"
#endif

static unsigned int wifi_calls;
static unsigned int poweroff_calls;
static unsigned int hardware_calls;
static unsigned int allocation_calls;
static unsigned int speech_count;
static int speech_labels[16];
static long speech_numbers[16];
static bool speech_enqueued[16];
static bool speech_numeric[16];
static unsigned int notice_count;
static intptr_t notice_label;
static int notice_ticks;
static unsigned int list_init_count;
static unsigned int list_show_count;
static bool list_usb;
static struct hiby_wifi_result next_wifi;
static struct hiby_poweroff_result next_poweroff;
static __thread jmp_buf shutdown_jump;
static __thread char trace[128];
static __thread unsigned int trace_used;
static __thread char panic_message[256];
static __thread bool fixture_curtain = true;
static __thread bool fixture_lock_held;
static bool concurrent_shutdown;
static bool force_lock_error;
static unsigned int lock_attempts;
static unsigned int active_backends;
static unsigned int maximum_backends;
static unsigned int completed_shutdowns;
static unsigned int wait_sleeps;
static unsigned int button_reads;
static const int delayed_buttons[] = { 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1 };
static const int immediate_buttons[] = { 0, 1, 0, 1 };
static const int *button_sequence;
static size_t button_sequence_size;
static pthread_mutex_t coordination_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t coordination_condition = PTHREAD_COND_INITIALIZER;
static struct sigaction signal_actions[NSIG];
static unsigned int signal_action_counts[NSIG];
uintptr_t *stackbegin;
uintptr_t *stackend;

int __wrap_sigaction(int signal_number, const struct sigaction *action, struct sigaction *previous)
{
    assert(signal_number > 0 && signal_number < NSIG && action && !previous);
    signal_actions[signal_number] = *action;
    ++signal_action_counts[signal_number];
    return 0;
}

static void sig_handler(int signal_number, siginfo_t *information, void *context)
{
    (void)signal_number; (void)information; (void)context;
    assert(!"Signal delivery forbidden in assignment fixture");
}

int __real_pthread_mutex_lock(pthread_mutex_t *mutex);
static void record(char event);

int __wrap_pthread_mutex_lock(pthread_mutex_t *mutex)
{
    __atomic_add_fetch(&lock_attempts, 1, __ATOMIC_SEQ_CST);
    record('K');
    if (force_lock_error)
        return EDEADLK;
    if (concurrent_shutdown)
    {
        assert(__real_pthread_mutex_lock(&coordination_mutex) == 0);
        assert(pthread_cond_broadcast(&coordination_condition) == 0);
        assert(pthread_mutex_unlock(&coordination_mutex) == 0);
    }
    int result = __real_pthread_mutex_lock(mutex);
    fixture_lock_held = result == 0;
    return result;
}

static void record(char event)
{
    assert(trace_used + 1 < sizeof(trace));
    trace[trace_used++] = event;
    trace[trace_used] = '\0';
}

struct hiby_wifi_result hiby_wifi_disable(void)
{
    ++wifi_calls;
    return next_wifi;
}

struct hiby_poweroff_result hiby_poweroff(void)
{
    __atomic_add_fetch(&poweroff_calls, 1, __ATOMIC_SEQ_CST);
    unsigned int active = __atomic_add_fetch(&active_backends, 1, __ATOMIC_SEQ_CST);
    unsigned int previous = __atomic_load_n(&maximum_backends, __ATOMIC_SEQ_CST);
    while (active > previous && !__atomic_compare_exchange_n(&maximum_backends,
        &previous, active, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)) {}
    record('P');
    if (concurrent_shutdown)
    {
        assert(__real_pthread_mutex_lock(&coordination_mutex) == 0);
        struct timespec deadline;
        assert(clock_gettime(CLOCK_REALTIME, &deadline) == 0);
        deadline.tv_sec += 5;
        while (__atomic_load_n(&lock_attempts, __ATOMIC_SEQ_CST) < 2)
            assert(pthread_cond_timedwait(&coordination_condition,
                &coordination_mutex, &deadline) == 0);
        assert(pthread_mutex_unlock(&coordination_mutex) == 0);
    }
    __atomic_sub_fetch(&active_backends, 1, __ATOMIC_SEQ_CST);
    return next_poweroff;
}

void *__wrap_malloc(size_t size)
{
    (void)size;
    ++allocation_calls;
    assert(!"Unexpected allocation in power UI");
    return NULL;
}

void *__wrap_calloc(size_t count, size_t size)
{
    (void)count; (void)size;
    return __wrap_malloc(0);
}

void *__wrap_realloc(void *pointer, size_t size)
{
    (void)pointer; (void)size;
    return __wrap_malloc(0);
}

void __wrap_free(void *pointer)
{
    (void)pointer;
    ++allocation_calls;
    assert(!"Unexpected deallocation in power UI");
}

char *__wrap_strdup(const char *text)
{
    (void)text;
    return __wrap_malloc(0);
}

int __wrap_reboot(int command)
{
    (void)command;
    ++hardware_calls;
    assert(!"Real reboot forbidden in UI fixture");
    return -1;
}

int __wrap_ioctl(int descriptor, unsigned long request, ...)
{
    (void)descriptor; (void)request;
    ++hardware_calls;
    assert(!"Real ioctl forbidden in UI fixture");
    return -1;
}

int __wrap_posix_spawn(pid_t *process, const char *path,
    const posix_spawn_file_actions_t *actions, const posix_spawnattr_t *attributes,
    char *const arguments[], char *const environment[])
{
    (void)process; (void)path; (void)actions; (void)attributes;
    (void)arguments; (void)environment;
    ++hardware_calls;
    assert(!"Process spawning forbidden in UI fixture");
    return -1;
}

int __wrap_posix_spawnp(pid_t *process, const char *path,
    const posix_spawn_file_actions_t *actions, const posix_spawnattr_t *attributes,
    char *const arguments[], char *const environment[])
{
    return __wrap_posix_spawn(process, path, actions, attributes, arguments, environment);
}

int __wrap_system(const char *command)
{
#ifdef POWER_UI_SHUTDOWN
    assert(strcmp(command, "/sbin/poweroff") == 0);
    record('C');
    return -1;
#else
    (void)command;
    ++hardware_calls;
    assert(!"System command forbidden in UI fixture");
    return -1;
#endif
}

void __wrap_sync(void)
{
#ifdef POWER_UI_SHUTDOWN
    record('S');
#else
    ++hardware_calls;
    assert(!"System sync forbidden in UI fixture");
#endif
}

int __wrap_usleep(useconds_t duration)
{
#ifdef POWER_UI_SHUTDOWN
    assert(duration == 1000);
    record('W');
    longjmp(shutdown_jump, 2);
#elif defined(POWER_UI_WAIT)
    assert(duration == 20000);
    ++wait_sleeps;
    record('Z');
    return 0;
#else
    (void)duration;
    ++hardware_calls;
    assert(!"Unexpected sleep in power UI");
#endif
    return -1;
}

static void backlight_hw_off(void) { record('O'); }
static void backlight_hw_on(void) { record('L'); }
static void button_close_device(void) { record('B'); }
static void backlight_hw_brightness(int brightness)
{
    assert(brightness == DEFAULT_BRIGHTNESS_SETTING);
    record('D');
}

#ifdef HAVE_BUTTON_DATA
static int button_read_device(int *data)
#else
static int button_read_device(void)
#endif
{
#ifdef HAVE_BUTTON_DATA
    assert(data);
    *data = 99;
#endif
    assert(button_reads < button_sequence_size);
    int value = button_sequence[button_reads++];
    record(value ? '1' : '0');
    return value;
}
void backlight_set_screen_curtain(bool enabled)
{
    assert(!enabled);
    fixture_curtain = false;
    record('R');
}

static void panicf(const char *format, ...) __attribute__((noreturn, format(printf, 1, 2)));
static void panicf(const char *format, ...)
{
#if defined(POWER_UI_SHUTDOWN) && defined(HIBY_R1) && !defined(BOOTLOADER)
    if (!force_lock_error)
    {
        assert(fixture_lock_held);
        assert(pthread_mutex_trylock(&poweroff_mutex) == EBUSY);
    }
#endif
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(panic_message, sizeof(panic_message), format, arguments);
    va_end(arguments);
    record('F');
    longjmp(shutdown_jump, 1);
}

#ifdef POWER_UI_SHUTDOWN

#define system __wrap_system
#include "power-ui-shutdown-body.h"

static void run_shutdown_once(void)
{
    int jumped = setjmp(shutdown_jump);
    if (!jumped)
    {
        power_off();
        assert(!"Shutdown must not silently return");
    }
#if defined(HIBY_R1) && !defined(BOOTLOADER)
    assert(jumped == 1);
#ifdef HAVE_ESPEAK
    assert(!strcmp(trace, force_lock_error ? "KRLF" : "KOPRLF"));
    assert(!fixture_curtain);
#else
    assert(!strcmp(trace, force_lock_error ? "KLF" : "KOPLF"));
    assert(fixture_curtain);
#endif
    char expected[256];
    snprintf(expected, sizeof(expected), "Power off failed: reboot=%d command=%d wait=%d",
        force_lock_error ? EDEADLK : next_poweroff.reboot_error,
        force_lock_error ? 0 : next_poweroff.command_error,
        force_lock_error ? 0 : next_poweroff.child_error);
    assert(!strcmp(panic_message, expected));
    if (fixture_lock_held)
    {
        assert(pthread_mutex_unlock(&poweroff_mutex) == 0);
        fixture_lock_held = false;
    }
#else
    assert(jumped == 2);
    assert(!strcmp(trace, "OBSCW"));
    assert(poweroff_calls == 0 && panic_message[0] == '\0');
#endif
    __atomic_add_fetch(&completed_shutdowns, 1, __ATOMIC_SEQ_CST);
}

static void *shutdown_worker(void *argument)
{
    (void)argument;
    run_shutdown_once();
    return NULL;
}

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2);
    if (!strcmp(arguments[1], "negative") || !strcmp(arguments[1], "concurrent"))
        next_poweroff = (struct hiby_poweroff_result){ -27, -11, -38 };
    else if (!strcmp(arguments[1], "extreme"))
        next_poweroff = (struct hiby_poweroff_result){ INT_MIN, INT_MAX, -1 };
    else if (!strcmp(arguments[1], "lock-error"))
        force_lock_error = true;
    else
        assert(!strcmp(arguments[1], "zero"));
    concurrent_shutdown = !strcmp(arguments[1], "concurrent");
    if (concurrent_shutdown)
    {
        pthread_t first, second;
        assert(pthread_create(&first, NULL, shutdown_worker, NULL) == 0);
        struct timespec deadline;
        assert(clock_gettime(CLOCK_MONOTONIC, &deadline) == 0);
        while (__atomic_load_n(&active_backends, __ATOMIC_SEQ_CST) == 0)
        {
            struct timespec now;
            assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
            assert(now.tv_sec - deadline.tv_sec < 5);
            sched_yield();
        }
        assert(pthread_create(&second, NULL, shutdown_worker, NULL) == 0);
        assert(pthread_join(first, NULL) == 0 && pthread_join(second, NULL) == 0);
        assert(completed_shutdowns == 2 && poweroff_calls == 2 && lock_attempts == 2);
        assert(maximum_backends == 1 && active_backends == 0);
    }
    else
    {
        run_shutdown_once();
#if defined(HIBY_R1) && !defined(BOOTLOADER)
        assert(poweroff_calls == (force_lock_error ? 0u : 1u));
        assert(lock_attempts == 1);
#endif
        assert(completed_shutdowns == 1);
    }
    assert(hardware_calls == 0 && allocation_calls == 0 && wifi_calls == 0);
    puts("strict fake shutdown route passed");
    return 0;
}

#elif defined(POWER_UI_INIT)

#include "power-ui-system-init-body.h"

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2 && !strcmp(arguments[1], "signals"));
    system_init();
    const int expected[] = { SIGILL, SIGABRT, SIGSEGV, SIGPIPE, SIGTERM, SIGFPE, SIGBUS };
    sigset_t filled;
    assert(sigfillset(&filled) == 0);
    for (int signal_number = 1; signal_number < NSIG; ++signal_number)
    {
        bool registered = false;
        for (unsigned int index = 0; index < sizeof(expected) / sizeof(expected[0]); ++index)
            registered = registered || expected[index] == signal_number;
        assert(signal_action_counts[signal_number] == (registered ? 1u : 0u));
        if (!registered)
            continue;
#ifdef HIBY_R1
        if (signal_number == SIGTERM)
        {
            assert(signal_actions[signal_number].sa_handler == SIG_DFL);
            assert((signal_actions[signal_number].sa_flags & SA_SIGINFO) == 0);
            for (int member = 1; member < NSIG; ++member)
                assert(sigismember(&signal_actions[signal_number].sa_mask, member) == 0);
            continue;
        }
#endif
        assert(signal_actions[signal_number].sa_sigaction == sig_handler);
        assert((signal_actions[signal_number].sa_flags & SA_SIGINFO) != 0);
        for (int member = 1; member < NSIG; ++member)
            assert(sigismember(&signal_actions[signal_number].sa_mask, member) ==
                sigismember(&filled, member));
    }
    assert(hardware_calls == 0 && allocation_calls == 0 && wifi_calls == 0 && poweroff_calls == 0);
    puts("actual system_init handler assignments passed without real sigaction");
    return 0;
}

#elif defined(POWER_UI_WAIT)

#include "power-ui-exception-wait-body.h"

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2);
    bool immediate = !strcmp(arguments[1], "immediate");
    assert(immediate || !strcmp(arguments[1], "phases"));
    button_sequence = immediate ? immediate_buttons : delayed_buttons;
    button_sequence_size = immediate ? sizeof(immediate_buttons) / sizeof(immediate_buttons[0]) :
        sizeof(delayed_buttons) / sizeof(delayed_buttons[0]);
    system_exception_wait();
    assert(button_reads == button_sequence_size);
    char expected[128] = "LD";
    size_t used = 2;
    for (size_t index = 0; index < button_sequence_size; ++index)
    {
        expected[used++] = button_sequence[index] ? '1' : '0';
#ifdef HIBY_R1
        if (!immediate && index % 3 != 2)
            expected[used++] = 'Z';
#endif
    }
    expected[used] = '\0';
    assert(!strcmp(trace, expected));
#ifdef HIBY_R1
    assert(wait_sleeps == (immediate ? 0u : 8u));
#else
    assert(wait_sleeps == 0);
#endif
    assert(hardware_calls == 0 && allocation_calls == 0 && wifi_calls == 0 && poweroff_calls == 0);
    puts("actual four exception input phases and bounded fake sleeps passed");
    return 0;
}

#else

#define HZ 100
#define MENU_ATTACHED_USB 487

struct simplelist_info
{
    const char *title;
    int count;
    bool speak_onshow;
    void *callback_data;
    const char *(*get_name)(int selected, void *data, char *buffer, size_t length);
    int (*get_talk)(int selected, void *data);
};

static struct simplelist_info captured_list;

static char *str(int label)
{
    assert(label >= 1000 && label < 1000 + POWER_UI_LABEL_COUNT);
    return (char *)power_ui_labels[label - 1000];
}

static int talk_id(int32_t label, bool enqueue)
{
    assert(speech_count < 16);
    speech_labels[speech_count] = label;
    speech_numeric[speech_count] = false;
    speech_enqueued[speech_count++] = enqueue;
    return 0;
}

static int talk_number(long number, bool enqueue)
{
    assert(speech_count < 16);
    speech_numbers[speech_count] = number;
    speech_numeric[speech_count] = true;
    speech_enqueued[speech_count++] = enqueue;
    return 0;
}

static void splash(int duration, const unsigned char *label);

static void simplelist_info_init(struct simplelist_info *list, char *title,
    int count, void *data)
{
    ++list_init_count;
    memset(list, 0, sizeof(*list));
    list->title = title;
    list->count = count;
    list->callback_data = data;
    list->speak_onshow = true;
}

static bool simplelist_show_list(struct simplelist_info *list)
{
    ++list_show_count;
    assert(list->get_name && list->get_talk && list->speak_onshow);
    captured_list = *list;
    return list_usb;
}

#include "power-ui-app-body.h"

static void splash(int duration, const unsigned char *label)
{
    ++notice_count;
    notice_ticks = duration;
    notice_label = P2ID(label);
}

static void check_row(int selected, int value_label, int number, bool numeric)
{
    char buffer[256], expected[256];
    const int labels[] = { LANG_HIBY_WIFI_STARTUP_STATE, LANG_HIBY_WIFI_RADIOS,
        LANG_HIBY_WIFI_INTERFACES, LANG_HIBY_WIFI_RADIO_ERROR, LANG_HIBY_WIFI_INTERFACE_ERROR };
    assert(status_name(selected, (void *)(uintptr_t)7, buffer, sizeof(buffer)) == buffer);
    if (numeric)
        snprintf(expected, sizeof(expected), "%s: %d", str(labels[selected]), number);
    else
        snprintf(expected, sizeof(expected), "%s: %s", str(labels[selected]), str(value_label));
    assert(!strcmp(buffer, expected));
    speech_count = 0;
    assert(status_speak(selected, (void *)(uintptr_t)7) == 0);
    assert(speech_count == 2 && !speech_numeric[0] && !speech_enqueued[0]);
    assert(speech_labels[0] == labels[selected] && speech_enqueued[1]);
    assert(speech_numeric[1] == numeric);
    if (numeric)
        assert(speech_numbers[1] == number);
    else
        assert(speech_labels[1] == value_label);
}

static void check_bounds(void)
{
    const int invalid[] = { -1, INT_MIN, INT_MAX, status_count() };
    for (unsigned int index = 0; index < sizeof(invalid) / sizeof(invalid[0]); ++index)
    {
        char buffer[] = "keep";
        speech_count = 0;
        assert(status_name(invalid[index], NULL, buffer, sizeof(buffer)) == buffer);
        assert(buffer[0] == '\0' && !strcmp(buffer + 1, "eep"));
        assert(status_speak(invalid[index], NULL) == 0 && speech_count == 0);
        buffer[0] = 'k';
        assert(status_name(invalid[index], NULL, buffer, 0) == buffer && !strcmp(buffer, "keep"));
        assert(status_name(invalid[index], NULL, NULL, 0) == NULL);
    }
    for (unsigned int selected = 0; selected < status_count(); ++selected)
    {
        char buffer[] = "keep";
        assert(status_name(selected, NULL, buffer, 0) == buffer && !strcmp(buffer, "keep"));
        assert(status_name(selected, NULL, NULL, 0) == NULL);
        assert(status_name(selected, NULL, buffer + 1, 1) == buffer + 1);
        assert(buffer[0] == 'k' && buffer[1] == '\0' && buffer[2] == 'e' && buffer[3] == 'p');
        buffer[1] = 'e';
        assert(status_name(selected, NULL, buffer + 1, 2) == buffer + 1);
        assert(buffer[0] == 'k' && buffer[1] != '\0' && buffer[2] == '\0' && buffer[3] == 'p');
    }
}

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2);
    int expected_state = LANG_HIBY_WIFI_UNCONFIRMED;
    bool initialize = strcmp(arguments[1], "unknown") != 0;
    next_wifi = (struct hiby_wifi_result){ .state = HIBY_WIFI_BLOCKED,
        .wlan_radios = 3, .interfaces_down = 4 };
    if (!strcmp(arguments[1], "no-radio"))
    {
        next_wifi = (struct hiby_wifi_result){ .state = HIBY_WIFI_NO_RADIO,
            .interfaces_down = 2 };
        expected_state = LANG_HIBY_WIFI_NO_RADIO;
    }
    else if (!strcmp(arguments[1], "unconfirmed"))
        next_wifi = (struct hiby_wifi_result){ .state = HIBY_WIFI_UNCONFIRMED,
            .wlan_radios = 8, .interfaces_down = 1,
            .rfkill_error = -13, .interface_error = -2 };
    else if (!strcmp(arguments[1], "interface-down"))
    {
        next_wifi = (struct hiby_wifi_result){ .state = HIBY_WIFI_INTERFACE_DOWN,
            .interfaces_present = 1, .interfaces_down = 1, .rfkill_error = ENOENT };
        expected_state = LANG_HIBY_WIFI_INTERFACE_DOWN;
    }
    else if (!strcmp(arguments[1], "error"))
        next_wifi = (struct hiby_wifi_result){ .state = HIBY_WIFI_ERROR,
            .wlan_radios = 8, .interfaces_down = 1,
            .rfkill_error = 13, .interface_error = 2 };
    else if (!strcmp(arguments[1], "extreme"))
        next_wifi = (struct hiby_wifi_result){ .state = HIBY_WIFI_ERROR,
            .rfkill_error = INT_MIN, .interface_error = INT_MAX };
    else if (initialize)
        expected_state = LANG_HIBY_WIFI_BLOCKED;

    if (initialize && next_wifi.state == HIBY_WIFI_ERROR)
        expected_state = LANG_HIBY_WIFI_CONTROL_FAILED;
#if defined(SIMULATOR) || defined(BOOTLOADER)
    expected_state = LANG_HIBY_WIFI_SIMULATOR;
#endif
    if (initialize)
        hiby_power_init();
    assert(startup_state_label() == expected_state);
    hiby_power_startup_notice();
#if defined(SIMULATOR) || defined(BOOTLOADER)
    assert(status_count() == 1 && wifi_calls == 0 && notice_count == 0);
#else
    assert(status_count() == 5 && wifi_calls == (initialize ? 1u : 0u));
    assert(notice_count == (expected_state == LANG_HIBY_WIFI_BLOCKED ? 0u : 1u));
    if (notice_count)
        assert(notice_label == expected_state && notice_ticks == 3 * HZ);
#endif
    check_row(0, expected_state, 0, false);
#if !defined(SIMULATOR) && !defined(BOOTLOADER)
    check_row(1, 0, initialize ? next_wifi.wlan_radios : 0, true);
    check_row(2, 0, initialize ? next_wifi.interfaces_down : 0, true);
    check_row(3, 0, initialize ? next_wifi.rfkill_error : 0, true);
    check_row(4, 0, initialize ? next_wifi.interface_error : 0, true);
#endif
    check_bounds();
    assert(hiby_power_status_menu() == 0);
    assert(list_init_count == 1 && list_show_count == 1);
    assert(captured_list.count == (int)status_count() && captured_list.callback_data == NULL);
    assert(!strcmp(captured_list.title, str(LANG_HIBY_WIFI_STARTUP)));
    assert(captured_list.get_name == status_name && captured_list.get_talk == status_speak);
    list_usb = true;
    assert(hiby_power_status_menu() == MENU_ATTACHED_USB);
    unsigned int startup_calls = wifi_calls;
    int cached_values[] = { 0, initialize ? (int)next_wifi.wlan_radios : 0,
        initialize ? (int)next_wifi.interfaces_down : 0,
        initialize ? next_wifi.rfkill_error : 0, initialize ? next_wifi.interface_error : 0 };
    next_wifi = (struct hiby_wifi_result){ .state = HIBY_WIFI_ERROR,
        .wlan_radios = 99, .interfaces_down = 99,
        .rfkill_error = -99, .interface_error = -99 };
    for (unsigned int iteration = 0; iteration < 1000; ++iteration)
    {
        for (unsigned int selected = 0; selected < status_count(); ++selected)
            check_row(selected, expected_state, cached_values[selected], selected != 0);
        assert(startup_state_label() == expected_state);
        assert(wifi_calls == startup_calls && allocation_calls == 0 && hardware_calls == 0);
    }
    assert(poweroff_calls == 0);
    puts("actual power UI snapshot, bounds, speech and 1000 reads passed");
    return 0;
}

#endif
