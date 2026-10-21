#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PLATFORM_NATIVE 1
#define PLATFORM_HOSTED 2
#ifdef FIXTURE_NATIVE
#define CONFIG_PLATFORM PLATFORM_NATIVE
#else
#define CONFIG_PLATFORM PLATFORM_HOSTED
#endif
#ifdef FIXTURE_DUALCORE
#define NUM_CORES 2
#define HAVE_CORELOCK_OBJECT
#define IF_COP(...) __VA_ARGS__
#else
#define NUM_CORES 1
#define IF_COP(...)
#endif
#ifndef FIXTURE_NO_TOUCH
#define HAVE_TOUCHSCREEN
#endif
#ifndef BOOTLOADER
#define HAVE_EXTENDED_MESSAGING_AND_NAME
#endif
#define SHAREDBSS_ATTR
#define INIT_ATTR
#define IF_PRIO(...)
#define LIKELY(value) (value)
#define UNLIKELY(value) (value)
#define logf(...) ((void)0)
#define DEBUGF(...) fprintf(stderr, __VA_ARGS__)
#define DEBUG

@CONSTANTS@
@CORELOCK_HEADER@

struct thread_entry;
struct __wait_queue { struct thread_entry *first; };
struct thread_entry
{
    intptr_t retval;
    unsigned int wakeups;
    unsigned int last_reason;
    struct __wait_queue *waiting_queue;
};

@QUEUE_HEADER@
@QUEUE_ASSERT@
@WAKEUP_PROTOCOL@

#define WQ_THREAD_FIRST(queue) ((queue)->first)

#ifdef HAVE_TOUCHSCREEN
_Static_assert(QUEUE_LENGTH == 32, "R1 requires the actual 32-slot queue");
#else
_Static_assert(QUEUE_LENGTH == 16, "Non-touch queue capacity changed");
#endif

static _Thread_local unsigned int fixture_core;
static _Thread_local int fixture_irq_level;
static _Thread_local unsigned int fixture_irq_depth;
static _Thread_local unsigned int fixture_irq_calls;
#ifdef FIXTURE_NATIVE
static pthread_mutex_t irq_mutexes[2];
static pthread_once_t irq_once = PTHREAD_ONCE_INIT;
#endif
static unsigned int poweroff_calls;
static unsigned int pmu_calls;
static unsigned int recording_status;
static struct event_queue *observed_queue;
static bool cancel_on_wakeup;

#ifdef FIXTURE_NATIVE
static void initialize_irq_mutexes(void)
{
    pthread_mutexattr_t attributes;
    assert(pthread_mutexattr_init(&attributes) == 0);
    assert(pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE) == 0);
    for (unsigned int index = 0; index < 2; index++)
        assert(pthread_mutex_init(&irq_mutexes[index], &attributes) == 0);
    assert(pthread_mutexattr_destroy(&attributes) == 0);
}
#endif

static int disable_irq_save(void)
{
    fixture_irq_calls++;
    fixture_irq_depth++;
#ifdef FIXTURE_NATIVE
    assert(pthread_once(&irq_once, initialize_irq_mutexes) == 0);
    assert(pthread_mutex_lock(&irq_mutexes[fixture_core]) == 0);
    int previous = fixture_irq_level;
    fixture_irq_level = 1;
    return previous;
#else
    return 0;
#endif
}

static void restore_irq(int previous)
{
    fixture_irq_calls++;
    assert(fixture_irq_depth > 0);
    fixture_irq_depth--;
#ifdef FIXTURE_NATIVE
    fixture_irq_level = previous;
    assert(pthread_mutex_unlock(&irq_mutexes[fixture_core]) == 0);
#else
    assert(previous == 0);
#endif
}

#ifdef HAVE_CORELOCK_OBJECT
static struct
{
    struct corelock *object;
    pthread_mutex_t mutex;
} fixture_locks[] = {
    {NULL, PTHREAD_MUTEX_INITIALIZER}, {NULL, PTHREAD_MUTEX_INITIALIZER},
    {NULL, PTHREAD_MUTEX_INITIALIZER}, {NULL, PTHREAD_MUTEX_INITIALIZER}
};
static pthread_mutex_t registry_mutex = PTHREAD_MUTEX_INITIALIZER;

static pthread_mutex_t *find_corelock(struct corelock *object)
{
    pthread_mutex_t *mutex = NULL;
    assert(pthread_mutex_lock(&registry_mutex) == 0);
    for (unsigned int index = 0; index < 4; index++)
    {
        if (fixture_locks[index].object == NULL)
            fixture_locks[index].object = object;
        if (fixture_locks[index].object == object)
        {
            mutex = &fixture_locks[index].mutex;
            break;
        }
    }
    assert(pthread_mutex_unlock(&registry_mutex) == 0);
    assert(mutex != NULL);
    return mutex;
}

void corelock_init(struct corelock *object)
{
    memset(object, 0, sizeof(*object));
}

void corelock_lock(struct corelock *object)
{
    assert(pthread_mutex_lock(find_corelock(object)) == 0);
}

void corelock_unlock(struct corelock *object)
{
    assert(pthread_mutex_unlock(find_corelock(object)) == 0);
}
#endif

static bool shutdown_timeout_active(void);
void cancel_shutdown(void);
static void power_off(void);
static unsigned int audio_status(void) __attribute__((unused));
static void pcf50606_reset_timeout(void) __attribute__((unused));

static void panicf(const char *message, ...) __attribute__((noreturn));
static void panicf(const char *message, ...)
{
    if (strncmp(message, "queue_post ovf", 14) == 0)
    {
        fprintf(stderr, "queue_post ovf: depth=%u capacity=%u\n",
                observed_queue->write - observed_queue->read, QUEUE_LENGTH);
        exit(86);
    }
    fprintf(stderr, "Unexpected panic: %s\n", message);
    exit(87);
}

static void wait_queue_init(struct __wait_queue *queue)
{
    queue->first = NULL;
}

static void **find_array_ptr(void **array, void *object)
{
    while (*array != NULL && *array != object)
        array++;
    return array;
}

static unsigned int wakeup_thread(struct thread_entry *thread, enum wakeup_thread_protocol reason)
{
    (void)shutdown_timeout_active();
    thread->wakeups++;
    thread->last_reason = reason;
    if (thread->waiting_queue != NULL)
    {
        assert(thread->waiting_queue->first == thread);
        thread->waiting_queue->first = NULL;
        thread->waiting_queue = NULL;
    }
    if (cancel_on_wakeup)
    {
        cancel_on_wakeup = false;
        cancel_shutdown();
    }
    return 0;
}

@QUEUE_SOURCE@
@POWER_STATE@
@POWER_REQUESTS@
@BUTTON_SOURCE@

static void power_off(void)
{
    (void)shutdown_timeout_active();
    __atomic_add_fetch(&poweroff_calls, 1, __ATOMIC_RELAXED);
}

static unsigned int audio_status(void)
{
    (void)shutdown_timeout_active();
    return __atomic_load_n(&recording_status, __ATOMIC_RELAXED);
}

static void pcf50606_reset_timeout(void)
{
    (void)shutdown_timeout_active();
    __atomic_add_fetch(&pmu_calls, 1, __ATOMIC_RELAXED);
}

#ifndef BOOTLOADER
static int base_timeout(void)
{
#ifdef IPOD_NANO2G
    return HZ * 60;
#else
    return HZ * 20;
#endif
}

static unsigned int expected_pmu(unsigned int count)
{
#if (defined(IAUDIO_X5) || defined(IAUDIO_M5) || defined(COWON_D2)) && !defined(SIMULATOR)
    return count;
#else
    (void)count;
    return 0;
#endif
}
#endif

static void check_state(enum shutdown_request_type request, int timeout)
{
    int previous = shutdown_state_lock();
    assert(shutdown_request == request);
    assert(shutdown_timeout == timeout);
    shutdown_state_unlock(previous);
}

static void reset_fixture(void)
{
    cancel_shutdown();
    poweroff_calls = 0;
    pmu_calls = 0;
    recording_status = 0;
    memset(&button_queue, 0, sizeof(button_queue));
    memset(&all_queues, 0, sizeof(all_queues));
    init_queues();
    button_queue_init();
    observed_queue = &button_queue;
    assert(queue_count(&button_queue) == 0);
    check_state(SHUTDOWN_REQUEST_NONE, 0);
}

#ifndef BOOTLOADER
static void check_event(unsigned int index, long event)
{
    assert(button_queue.events[(button_queue.read + index) & QUEUE_LENGTH_MASK].id == event);
}

static pthread_barrier_t start_barrier;

struct worker_arguments
{
    unsigned int core;
    unsigned int role;
    unsigned int accepted;
};

static void *request_worker(void *argument)
{
    struct worker_arguments *worker = argument;
    fixture_core = worker->core;
    int result = pthread_barrier_wait(&start_barrier);
    assert(result == 0 || result == PTHREAD_BARRIER_SERIAL_THREAD);
    for (unsigned int index = 0; index < 128; index++)
    {
        switch (worker->role)
        {
            case 0:
                sys_poweroff();
                break;
            case 1:
                worker->accepted += sys_shutdown_common(SHUTDOWN_REQUEST_POWEROFF);
                break;
            case 2:
                worker->accepted += sys_shutdown_common(SHUTDOWN_REQUEST_REBOOT);
                break;
            case 3:
                if (index & 1)
                    cancel_shutdown();
                else
                    sys_shutdown_common(SHUTDOWN_REQUEST_POWEROFF);
                break;
            case 4:
                shutdown_timeout_step();
                (void)shutdown_timeout_active();
                break;
            case 5:
                assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, index));
                break;
            case 6:
                assert(button_queue_try_post(BUTTON_VOL_UP | BUTTON_REPEAT, index));
                break;
            default:
                abort();
        }
    }
    assert(fixture_irq_depth == 0);
    assert(fixture_irq_level == 0);
    return NULL;
}

static unsigned int run_workers(unsigned int first_role, unsigned int second_role)
{
    pthread_t threads[2];
    struct worker_arguments workers[2] = {
        {0, first_role, 0}, {NUM_CORES - 1, second_role, 0}
    };
    assert(pthread_barrier_init(&start_barrier, NULL, 2) == 0);
    for (unsigned int index = 0; index < 2; index++)
        assert(pthread_create(&threads[index], NULL, request_worker, &workers[index]) == 0);
    for (unsigned int index = 0; index < 2; index++)
        assert(pthread_join(threads[index], NULL) == 0);
    assert(pthread_barrier_destroy(&start_barrier) == 0);
    return workers[0].accepted + workers[1].accepted;
}
#endif

int main(int argument_count, char **arguments)
{
    assert(argument_count == 2);
    const char *scenario = arguments[1];
    reset_fixture();
    if (strcmp(scenario, "bootloader") == 0)
    {
#ifdef BOOTLOADER
        sys_poweroff();
        sys_reboot();
        shutdown_timeout_step();
        cancel_shutdown();
        check_state(SHUTDOWN_REQUEST_NONE, 0);
        assert(queue_count(&button_queue) == 0);
        assert(poweroff_calls == 0 && pmu_calls == 0);
#else
        abort();
#endif
    }
#ifndef BOOTLOADER
    else if (strcmp(scenario, "repeat-poweroff") == 0)
    {
        for (unsigned int index = 0; index < 64; index++)
            sys_poweroff();
        assert(queue_count(&button_queue) == 1);
        check_event(0, SYS_POWEROFF);
        check_state(SHUTDOWN_REQUEST_POWEROFF, base_timeout());
        assert(pmu_calls == expected_pmu(1));
    }
    else if (strcmp(scenario, "repeat-reboot") == 0)
    {
        for (unsigned int index = 0; index < 64; index++)
            sys_reboot();
        assert(queue_count(&button_queue) == 1);
        check_event(0, SYS_REBOOT);
        check_state(SHUTDOWN_REQUEST_REBOOT, base_timeout());
    }
    else if (strcmp(scenario, "upgrade") == 0)
    {
        sys_poweroff();
        shutdown_timeout_step();
        sys_reboot();
        sys_reboot();
        sys_poweroff();
        assert(queue_count(&button_queue) == 2);
        check_event(0, SYS_POWEROFF);
        check_event(1, SYS_REBOOT);
        check_state(SHUTDOWN_REQUEST_REBOOT, base_timeout() - POWER_THREAD_STEP_TICKS);
        assert(pmu_calls == expected_pmu(1));
    }
    else if (strcmp(scenario, "no-downgrade") == 0)
    {
        sys_reboot();
        sys_poweroff();
        assert(queue_count(&button_queue) == 1);
        check_event(0, SYS_REBOOT);
        check_state(SHUTDOWN_REQUEST_REBOOT, base_timeout());
    }
    else if (strcmp(scenario, "cancel-rearm") == 0)
    {
        sys_poweroff();
        shutdown_timeout_step();
        cancel_shutdown();
        check_state(SHUTDOWN_REQUEST_NONE, 0);
        sys_reboot();
        assert(queue_count(&button_queue) == 2);
        check_event(1, SYS_REBOOT);
        check_state(SHUTDOWN_REQUEST_REBOOT, base_timeout());
        assert(pmu_calls == expected_pmu(3));
        cancel_shutdown();
        sys_poweroff();
        check_state(SHUTDOWN_REQUEST_POWEROFF, base_timeout());
        assert(queue_count(&button_queue) == 3);
        assert(pmu_calls == expected_pmu(5));
    }
    else if (strcmp(scenario, "cancel-inactive") == 0)
    {
        cancel_shutdown();
        cancel_shutdown();
        check_state(SHUTDOWN_REQUEST_NONE, 0);
        assert(pmu_calls == 0);
        assert(queue_count(&button_queue) == 0);
    }
    else if (strcmp(scenario, "cancel-in-flight") == 0)
    {
        struct thread_entry waiter = {0};
        waiter.waiting_queue = &button_queue.queue;
        button_queue.queue.first = &waiter;
        cancel_on_wakeup = true;
        sys_poweroff();
        check_state(SHUTDOWN_REQUEST_NONE, 0);
        assert(queue_count(&button_queue) == 1);
        sys_reboot();
        check_state(SHUTDOWN_REQUEST_REBOOT, base_timeout());
        assert(queue_count(&button_queue) == 2);
        check_event(0, SYS_POWEROFF);
        check_event(1, SYS_REBOOT);
        assert(pmu_calls == expected_pmu(3));
        assert(waiter.wakeups == 1 && waiter.last_reason == WAKEUP_DEFAULT);
    }
    else if (strcmp(scenario, "recording") == 0)
    {
        recording_status = AUDIO_STATUS_RECORD | AUDIO_STATUS_PAUSE;
        sys_poweroff();
        int expected = base_timeout();
#ifdef HAVE_RECORDING
        expected += HZ * 8;
#endif
        check_state(SHUTDOWN_REQUEST_POWEROFF, expected);
        recording_status = 0;
        sys_reboot();
        check_state(SHUTDOWN_REQUEST_REBOOT, expected);
    }
    else if (strcmp(scenario, "deadline") == 0)
    {
        sys_poweroff();
        for (unsigned int index = 0; index < 8; index++)
        {
            shutdown_timeout_step();
            sys_poweroff();
        }
        check_state(SHUTDOWN_REQUEST_POWEROFF, base_timeout() - 8 * POWER_THREAD_STEP_TICKS);
        assert(queue_count(&button_queue) == 1 && poweroff_calls == 0);
    }
    else if (strcmp(scenario, "expiry") == 0)
    {
        sys_reboot();
        for (int remaining = base_timeout(); remaining > POWER_THREAD_STEP_TICKS;
             remaining -= POWER_THREAD_STEP_TICKS)
            shutdown_timeout_step();
        assert(poweroff_calls == 0);
        shutdown_timeout_step();
        assert(poweroff_calls == 1);
        check_state(SHUTDOWN_REQUEST_REBOOT, 0);
        sys_reboot();
        sys_poweroff();
        check_state(SHUTDOWN_REQUEST_REBOOT, 0);
        assert(queue_count(&button_queue) == 1);
    }
    else if (strcmp(scenario, "cancel-before-expiry") == 0)
    {
        sys_poweroff();
        for (int remaining = base_timeout(); remaining > POWER_THREAD_STEP_TICKS;
             remaining -= POWER_THREAD_STEP_TICKS)
            shutdown_timeout_step();
        cancel_shutdown();
        shutdown_timeout_step();
        assert(poweroff_calls == 0);
        check_state(SHUTDOWN_REQUEST_NONE, 0);
    }
    else if (strcmp(scenario, "preserve-events") == 0)
    {
        struct event_queue other_queue = {0};
        queue_init(&other_queue, true);
        queue_post(&button_queue, SYS_BATTERY_UPDATE, 17);
        queue_post(&button_queue, SYS_USB_CONNECTED, 18);
        sys_poweroff();
        sys_poweroff();
        assert(queue_count(&button_queue) == 3);
        assert(queue_count(&other_queue) == 1);
        check_event(0, SYS_BATTERY_UPDATE);
        check_event(1, SYS_USB_CONNECTED);
        check_event(2, SYS_POWEROFF);
        assert(button_queue.events[0].data == 17 && button_queue.events[1].data == 18);
    }
    else if (strcmp(scenario, "nested-irq") == 0)
    {
        int previous = disable_irq_save();
        sys_poweroff();
        sys_reboot();
        cancel_shutdown();
        shutdown_timeout_step();
        assert(fixture_irq_depth == 1);
#ifdef FIXTURE_NATIVE
        assert(fixture_irq_level == 1);
#endif
        restore_irq(previous);
    }
    else if (strcmp(scenario, "guard-irq-boundary") == 0)
    {
        unsigned int before = fixture_irq_calls;
        int previous = shutdown_state_lock();
        shutdown_state_unlock(previous);
#ifdef FIXTURE_NATIVE
        assert(fixture_irq_calls == before + 2);
#else
        assert(fixture_irq_calls == before);
#endif
    }
    else if (strcmp(scenario, "concurrent-repeat") == 0)
    {
        run_workers(0, 0);
        assert(queue_count(&button_queue) == 1);
        check_state(SHUTDOWN_REQUEST_POWEROFF, base_timeout());
    }
    else if (strcmp(scenario, "concurrent-upgrade") == 0)
    {
        unsigned int accepted = run_workers(1, 2);
        assert(accepted == 1 || accepted == 2);
        check_state(SHUTDOWN_REQUEST_REBOOT, base_timeout());
        assert(queue_count(&button_queue) == 0);
    }
    else if (strcmp(scenario, "concurrent-cancel-step") == 0)
    {
        run_workers(3, 4);
        cancel_shutdown();
        shutdown_timeout_step();
        check_state(SHUTDOWN_REQUEST_NONE, 0);
    }
    else if (strcmp(scenario, "mixed-raw") == 0 || strcmp(scenario, "raw-only") == 0 ||
             strcmp(scenario, "mixed-drained") == 0)
    {
        if (strcmp(scenario, "raw-only") != 0)
            sys_poweroff();
        if (strcmp(scenario, "mixed-drained") == 0)
            queue_clear(&button_queue);
        for (unsigned int index = 0; index < 64; index++)
        {
            if (strcmp(scenario, "mixed-raw") == 0)
                sys_poweroff();
            assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, index));
        }
        unsigned int repeat_index = strcmp(scenario, "mixed-raw") == 0 ? 1 : 0;
        assert(queue_count(&button_queue) == (int)repeat_index + 1);
        if (repeat_index != 0)
            check_event(0, SYS_POWEROFF);
        check_event(repeat_index, BUTTON_POWER | BUTTON_REPEAT);
        assert(button_queue.events[(button_queue.read + repeat_index) & QUEUE_LENGTH_MASK].data == 63);
    }
    else if (strcmp(scenario, "exact-repeat-ids") == 0)
    {
        sys_poweroff();
        assert(button_queue_try_post(BUTTON_VOL_UP | BUTTON_REPEAT, 111));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_VOL_UP | BUTTON_REPEAT, 222));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 333));
        assert(button_queue_try_post(BUTTON_VOL_DOWN | BUTTON_REPEAT, 444));
        for (unsigned int index = 0; index < 64; index++)
            assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, index));
        const long events[] = {SYS_POWEROFF, BUTTON_VOL_UP | BUTTON_REPEAT,
            BUTTON_POWER | BUTTON_VOL_UP | BUTTON_REPEAT, BUTTON_VOL_DOWN | BUTTON_REPEAT,
            BUTTON_POWER | BUTTON_REPEAT};
        const intptr_t data[] = {0, 111, 222, 444, 63};
        assert(queue_count(&button_queue) == 5);
        for (unsigned int index = 0; index < 5; index++)
        {
            check_event(index, events[index]);
            assert(button_queue.events[(button_queue.read + index) & QUEUE_LENGTH_MASK].data == data[index]);
        }
    }
    else if (strcmp(scenario, "many-matching-repeats") == 0)
    {
        queue_post(&button_queue, SYS_BATTERY_UPDATE, 11);
        queue_post(&button_queue, BUTTON_POWER | BUTTON_REPEAT, 22);
        queue_post(&button_queue, BUTTON_POWER | BUTTON_REL, 33);
        queue_post(&button_queue, BUTTON_POWER | BUTTON_REPEAT, 44);
        queue_post(&button_queue, BUTTON_VOL_UP | BUTTON_REPEAT, 55);
        queue_post(&button_queue, BUTTON_POWER | BUTTON_REPEAT, 66);
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 77));
        const long events[] = {SYS_BATTERY_UPDATE, BUTTON_POWER | BUTTON_REL,
            BUTTON_VOL_UP | BUTTON_REPEAT, BUTTON_POWER | BUTTON_REPEAT};
        const intptr_t data[] = {11, 33, 55, 77};
        assert(queue_count(&button_queue) == 4);
        for (unsigned int index = 0; index < 4; index++)
        {
            check_event(index, events[index]);
            assert(button_queue.events[(button_queue.read + index) & QUEUE_LENGTH_MASK].data == data[index]);
        }
    }
    else if (strcmp(scenario, "repeat-edges") == 0)
    {
        queue_post(&button_queue, SYS_BATTERY_UPDATE, 314);
        assert(button_queue_try_post(BUTTON_POWER, 11));
        assert(button_queue_try_post(BUTTON_POWER, 12));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 101));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REL, 22));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REL, 23));
        assert(button_queue_try_post(BUTTON_POWER, 33));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 202));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REL | BUTTON_REPEAT, 44));
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 303));
        const long events[] = {SYS_BATTERY_UPDATE, BUTTON_POWER, BUTTON_POWER,
            BUTTON_POWER | BUTTON_REL, BUTTON_POWER | BUTTON_REL, BUTTON_POWER,
            BUTTON_POWER | BUTTON_REL | BUTTON_REPEAT, BUTTON_POWER | BUTTON_REPEAT};
        const intptr_t data[] = {314, 11, 12, 22, 23, 33, 44, 303};
        assert(queue_count(&button_queue) == 8);
        for (unsigned int index = 0; index < 8; index++)
        {
            check_event(index, events[index]);
            assert(button_queue.events[(button_queue.read + index) & QUEUE_LENGTH_MASK].data == data[index]);
        }
    }
    else if (strcmp(scenario, "system-repeat-bit") == 0)
    {
        queue_post(&button_queue, SYS_BATTERY_UPDATE, 11);
        long system_event = SYS_POWEROFF | BUTTON_REPEAT;
        assert(button_queue_try_post(system_event, 22));
        assert(button_queue_try_post(system_event, 33));
        assert(queue_count(&button_queue) == 3);
        check_event(0, SYS_BATTERY_UPDATE);
        check_event(1, system_event);
        check_event(2, system_event);
        assert(button_queue.events[0].data == 11);
        assert(button_queue.events[1].data == 22);
        assert(button_queue.events[2].data == 33);
    }
    else if (strcmp(scenario, "touch-coordinates") == 0)
    {
        sys_poweroff();
        assert(button_queue_try_post(BUTTON_TOUCHSCREEN, 0x12345678));
        for (unsigned int index = 0; index < 64; index++)
            assert(button_queue_try_post(BUTTON_TOUCHSCREEN | BUTTON_REPEAT, (index << 16) | (index + 1234)));
        assert(queue_count(&button_queue) == 3);
        check_event(0, SYS_POWEROFF);
        check_event(1, BUTTON_TOUCHSCREEN);
        check_event(2, BUTTON_TOUCHSCREEN | BUTTON_REPEAT);
        assert(button_queue.events[(button_queue.read + 1) & QUEUE_LENGTH_MASK].data == 0x12345678);
        assert(button_queue.events[(button_queue.read + 2) & QUEUE_LENGTH_MASK].data == ((63 << 16) | 1297));
    }
    else if (strcmp(scenario, "full-matching-repeat") == 0 ||
             strcmp(scenario, "full-nonmatching-repeat") == 0)
    {
        queue_post(&button_queue, SYS_BATTERY_UPDATE, 123);
        for (unsigned int index = 1; index < QUEUE_LENGTH - 1; index++)
            queue_post(&button_queue, 0x100000 + index, index);
        long last_event = strcmp(scenario, "full-matching-repeat") == 0 ?
                          BUTTON_POWER | BUTTON_REPEAT : BUTTON_POWER;
        queue_post(&button_queue, last_event, 999);
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 456));
        assert(queue_count(&button_queue) == QUEUE_LENGTH);
        check_event(0, SYS_BATTERY_UPDATE);
        assert(button_queue.events[button_queue.read & QUEUE_LENGTH_MASK].data == 123);
        for (unsigned int index = 1; index < QUEUE_LENGTH - 1; index++)
        {
            check_event(index, 0x100000 + index);
            assert(button_queue.events[(button_queue.read + index) & QUEUE_LENGTH_MASK].data == (intptr_t)index);
        }
        check_event(QUEUE_LENGTH - 1, BUTTON_POWER | BUTTON_REPEAT);
        assert(button_queue.events[(button_queue.read + QUEUE_LENGTH - 1) & QUEUE_LENGTH_MASK].data == 456);
    }
    else if (strcmp(scenario, "non-touch-policy") == 0)
    {
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 11));
        assert(!button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 22));
        assert(!button_queue_try_post(BUTTON_POWER, 33));
        assert(queue_count(&button_queue) == 1);
        check_event(0, BUTTON_POWER | BUTTON_REPEAT);
        assert(button_queue.events[button_queue.read & QUEUE_LENGTH_MASK].data == 11);
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REL, 44));
        assert(queue_count(&button_queue) == 2);
        check_event(1, BUTTON_POWER | BUTTON_REL);
        assert(button_queue.events[(button_queue.read + 1) & QUEUE_LENGTH_MASK].data == 44);
    }
    else if (strcmp(scenario, "repeat-wakeup") == 0)
    {
        sys_poweroff();
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 11));
        struct thread_entry waiter = {0};
        waiter.waiting_queue = &button_queue.queue;
        button_queue.queue.first = &waiter;
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 22));
        assert(queue_count(&button_queue) == 2);
        assert(waiter.wakeups == 1 && waiter.last_reason == WAKEUP_DEFAULT);
        assert(waiter.waiting_queue == NULL && button_queue.queue.first == NULL);
        check_event(0, SYS_POWEROFF);
        check_event(1, BUTTON_POWER | BUTTON_REPEAT);
        assert(button_queue.events[(button_queue.read + 1) & QUEUE_LENGTH_MASK].data == 22);
    }
    else if (strcmp(scenario, "repeat-senders") == 0)
    {
        struct queue_sender_list senders;
        struct thread_entry system_sender = {0}, repeat_sender = {0}, release_sender = {0}, current_sender = {0};
        queue_enable_queue_send(&button_queue, &senders, 0);
        queue_post(&button_queue, SYS_BATTERY_UPDATE, 51);
        senders.senders[0] = &system_sender;
        queue_post(&button_queue, BUTTON_POWER | BUTTON_REPEAT, 10);
        senders.senders[1] = &repeat_sender;
        queue_post(&button_queue, BUTTON_POWER | BUTTON_REL, 20);
        senders.senders[2] = &release_sender;
        senders.curr_sender = &current_sender;
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 30));
        assert(queue_count(&button_queue) == 3);
        assert(repeat_sender.wakeups == 1 && repeat_sender.last_reason == WAKEUP_RELEASE);
        assert(repeat_sender.retval == 0);
        assert(system_sender.wakeups == 0 && release_sender.wakeups == 0 && current_sender.wakeups == 0);
        assert(senders.curr_sender == &current_sender);
        assert(senders.senders[button_queue.read & QUEUE_LENGTH_MASK] == &system_sender);
        assert(senders.senders[(button_queue.read + 1) & QUEUE_LENGTH_MASK] == &release_sender);
        assert(senders.senders[(button_queue.read + 2) & QUEUE_LENGTH_MASK] == NULL);
        check_event(0, SYS_BATTERY_UPDATE);
        check_event(1, BUTTON_POWER | BUTTON_REL);
        check_event(2, BUTTON_POWER | BUTTON_REPEAT);
        assert(button_queue_try_post(BUTTON_POWER | BUTTON_REPEAT, 40));
        assert(repeat_sender.wakeups == 1);
        queue_clear(&button_queue);
        assert(system_sender.wakeups == 1 && release_sender.wakeups == 1);
        assert(current_sender.wakeups == 0 && senders.curr_sender == &current_sender);
        assert(queue_count(&button_queue) == 0);
    }
    else if (strcmp(scenario, "concurrent-button-repeats") == 0)
    {
        sys_poweroff();
        run_workers(5, 6);
        assert(queue_count(&button_queue) == 3);
        check_event(0, SYS_POWEROFF);
        long first = button_queue.events[(button_queue.read + 1) & QUEUE_LENGTH_MASK].id;
        long second = button_queue.events[(button_queue.read + 2) & QUEUE_LENGTH_MASK].id;
        assert((first == (BUTTON_POWER | BUTTON_REPEAT) && second == (BUTTON_VOL_UP | BUTTON_REPEAT)) ||
               (first == (BUTTON_VOL_UP | BUTTON_REPEAT) && second == (BUTTON_POWER | BUTTON_REPEAT)));
        assert(button_queue.events[(button_queue.read + 1) & QUEUE_LENGTH_MASK].data == 127);
        assert(button_queue.events[(button_queue.read + 2) & QUEUE_LENGTH_MASK].data == 127);
    }
    else if (strcmp(scenario, "queue-capacity") == 0 || strcmp(scenario, "queue-overflow") == 0)
    {
        for (unsigned int index = 0; index < QUEUE_LENGTH; index++)
            queue_post(&button_queue, index + 1, 0);
        assert(queue_count(&button_queue) == QUEUE_LENGTH);
        if (strcmp(scenario, "queue-overflow") == 0)
            queue_post(&button_queue, 0, 0);
    }
#endif
    else
        abort();
    assert(fixture_irq_depth == 0);
    assert(fixture_irq_level == 0);
    printf("PASS %s capacity=%u\n", scenario, QUEUE_LENGTH);
    return 0;
}
