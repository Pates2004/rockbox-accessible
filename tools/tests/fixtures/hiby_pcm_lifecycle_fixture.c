static unsigned int lifecycle_waits;
static long lifecycle_realtime_offset;
static long long lifecycle_reap_after;
static bool lifecycle_stubborn;

static int lifecycle_timedwait(pthread_cond_t *condition, pthread_mutex_t *mutex,
                               const struct timespec *deadline)
{
    __atomic_add_fetch(&lifecycle_waits, 1, __ATOMIC_RELEASE);
    return pthread_cond_timedwait(condition, mutex, deadline);
}

static int lifecycle_clock_gettime(clockid_t clock_id, struct timespec *value)
{
    int result = clock_gettime(clock_id, value);
    if (!result && clock_id == CLOCK_REALTIME)
        value->tv_sec += __atomic_load_n(&lifecycle_realtime_offset, __ATOMIC_ACQUIRE);
    return result;
}

static pid_t lifecycle_waitpid(pid_t process, int *status, int options)
{
    if (__atomic_load_n(&lifecycle_stubborn, __ATOMIC_ACQUIRE) ||
        now_ms() < __atomic_load_n(&lifecycle_reap_after, __ATOMIC_ACQUIRE))
        return 0;
    return waitpid(process, status, options);
}

static unsigned int lifecycle_retired_count(void)
{
    unsigned int count = 0;
    assert(!pthread_mutex_lock(&pool_mutex));
    for (unsigned int position = 0; position < PCM_PROCESS_SLOTS; position++)
        if (process_pool[position] > 0 && retired_pool[position])
            count++;
    assert(!pthread_mutex_unlock(&pool_mutex));
    return count;
}

static bool lifecycle_has_children(void)
{
    siginfo_t information;
    memset(&information, 0, sizeof(information));
    int result = waitid(P_ALL, 0, &information, WEXITED | WNOHANG | WNOWAIT);
    assert(!result || errno == ECHILD);
    return !result;
}

static void lifecycle_start(void)
{
    builtin_pcm_sink.ops.init();
    assert(wait_output(false, 1000));
}

static void lifecycle_signal(void)
{
    sink_lock();
    assert(!pthread_cond_signal(&changed));
    sink_unlock();
}

static long long lifecycle_cpu_ns(clockid_t clock_id)
{
    struct timespec value;
    assert(!clock_gettime(clock_id, &value));
    return (long long)value.tv_sec * 1000000000 + value.tv_nsec;
}

int main(int argc, char **argv)
{
    int helper = hiby_pcm_helper_main(argc, argv);
    if (helper >= 0)
        return helper;
    assert(argc == 2);
    const char *scenario = argv[1];
    if (!strcmp(scenario, "shutdown-natural"))
    {
        unsigned int incomplete = 0;
        for (unsigned int cycle = 0; cycle < 24; cycle++)
        {
            lifecycle_start();
            hiby_pcm_shutdown();
            unsigned int retired = lifecycle_retired_count();
            bool children = lifecycle_has_children();
            if (retired || children)
                incomplete++;
            verify_reaped();
        }
        printf("TRACE production_shutdown_cycles=24 incomplete_before_test_cleanup=%u\n", incomplete);
        return incomplete ? 201 : 0;
    }
    lifecycle_start();
    if (!strcmp(scenario, "shutdown-deferred"))
    {
        __atomic_store_n(&lifecycle_reap_after, now_ms() + 80, __ATOMIC_RELEASE);
        long long started = now_ms();
        hiby_pcm_shutdown();
        long long elapsed = now_ms() - started;
        unsigned int retired = lifecycle_retired_count();
        bool children = lifecycle_has_children();
        printf("TRACE production_shutdown_ms=%lld retired_before_test_cleanup=%u kernel_children=%d\n",
               elapsed, retired, children);
        __atomic_store_n(&lifecycle_reap_after, 0, __ATOMIC_RELEASE);
        verify_reaped();
        assert(elapsed < 700);
        return retired || children ? 201 : 0;
    }
    if (!strcmp(scenario, "shutdown-stubborn"))
    {
        __atomic_store_n(&lifecycle_stubborn, true, __ATOMIC_RELEASE);
        long long started = now_ms();
        hiby_pcm_shutdown();
        long long elapsed = now_ms() - started;
        unsigned int retired = lifecycle_retired_count();
        sink_lock();
        int error = last_error;
        sink_unlock();
        printf("TRACE stubborn_shutdown_ms=%lld tracked_retired=%u last_error=%d budget_ms=%d\n",
               elapsed, retired, error, PCM_REAP_TIMEOUT_MS);
        __atomic_store_n(&lifecycle_stubborn, false, __ATOMIC_RELEASE);
        verify_reaped();
        assert(elapsed < 700);
        return retired && error == -ETIMEDOUT && elapsed >= PCM_REAP_TIMEOUT_MS ? 0 : 204;
    }
    if (!strcmp(scenario, "idle-retired"))
    {
        __atomic_store_n(&lifecycle_stubborn, true, __ATOMIC_RELEASE);
        assert(!pcm_alsa_switch_playback_device(bt_device));
        assert(!pcm_alsa_switch_playback_device(LOCAL_DEVICE));
        delay_ms(40);
        unsigned int before = lifecycle_retired_count();
        assert(before >= 1);
        __atomic_store_n(&lifecycle_stubborn, false, __ATOMIC_RELEASE);
        unsigned int waits_before = __atomic_load_n(&lifecycle_waits, __ATOMIC_ACQUIRE);
        delay_ms(650);
        unsigned int after = lifecycle_retired_count();
        unsigned int waits_after = __atomic_load_n(&lifecycle_waits, __ATOMIC_ACQUIRE);
        printf("TRACE idle_retired_before=%u idle_retired_after=%u idle_waits=%u\n",
               before, after, waits_after - waits_before);
        hiby_pcm_shutdown();
        verify_reaped();
        assert(waits_after - waits_before <= 8);
        return after ? 202 : 0;
    }
    if (!strcmp(scenario, "clock-offset-negative"))
    {
        clockid_t cpu_clock;
        assert(!pthread_getcpuclockid(pump, &cpu_clock));
        __atomic_store_n(&lifecycle_realtime_offset, -2, __ATOMIC_RELEASE);
        unsigned int before = __atomic_load_n(&lifecycle_waits, __ATOMIC_ACQUIRE);
        long long cpu_before = lifecycle_cpu_ns(cpu_clock);
        lifecycle_signal();
        delay_ms(350);
        long long cpu_after = lifecycle_cpu_ns(cpu_clock);
        unsigned int after = __atomic_load_n(&lifecycle_waits, __ATOMIC_ACQUIRE);
        __atomic_store_n(&lifecycle_realtime_offset, 0, __ATOMIC_RELEASE);
        printf("TRACE synthetic_realtime_sample_offset=-2 idle_ms=350 waits=%u pump_cpu_ns=%lld\n",
               after - before, cpu_after - cpu_before);
        hiby_pcm_shutdown();
        verify_reaped();
        return after - before <= 8 && cpu_after - cpu_before < 100000000 ? 0 : 203;
    }
    if (!strcmp(scenario, "clock-offset-positive"))
    {
        assert(!pcm_alsa_switch_playback_device(bt_device));
        __atomic_store_n(&lifecycle_realtime_offset, 2, __ATOMIC_RELEASE);
        unsigned int before = __atomic_load_n(&lifecycle_waits, __ATOMIC_ACQUIRE);
        lifecycle_signal();
        long long deadline = now_ms() + 1000;
        while (__atomic_load_n(&lifecycle_waits, __ATOMIC_ACQUIRE) == before)
        {
            assert(now_ms() < deadline);
            delay_ms(2);
        }
        sink_lock();
        pid_t process = active_helper.process;
        sink_unlock();
        assert(process > 0 && !kill(process, SIGKILL));
        delay_ms(1700);
        bool stale = pcm_alsa_bluetooth_active();
        printf("TRACE synthetic_realtime_sample_offset=2 dead_helper_after_ms=1700 stale_bluetooth=%d\n", stale);
        __atomic_store_n(&lifecycle_realtime_offset, 0, __ATOMIC_RELEASE);
        lifecycle_signal();
        assert(wait_output(false, 1000));
        hiby_pcm_shutdown();
        verify_reaped();
        return stale ? 203 : 0;
    }
    assert(false);
}
