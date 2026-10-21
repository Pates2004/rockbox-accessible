static pthread_mutex_t status_gate_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t status_gate_changed = PTHREAD_COND_INITIALIZER;
static pthread_t status_owner;
static bool status_gate_armed;
static bool status_gate_entered;
static bool status_gate_release;
static bool status_gate_completed;
static bool status_create_fail;
static bool status_condition_fail;
static bool status_observer_stop;
static unsigned int status_observations;

static int status_pthread_create(pthread_t *thread, const pthread_attr_t *attributes,
                                 void *(*entry)(void *), void *context)
{
    if (__atomic_load_n(&status_create_fail, __ATOMIC_ACQUIRE))
        return EAGAIN;
    return pthread_create(thread, attributes, entry, context);
}

static int status_condattr_setclock(pthread_condattr_t *attributes, clockid_t clock_id)
{
    if (__atomic_load_n(&status_condition_fail, __ATOMIC_ACQUIRE))
        return EINVAL;
    return pthread_condattr_setclock(attributes, clock_id);
}

static int status_mutex_unlock(pthread_mutex_t *mutex)
{
    int result = pthread_mutex_unlock(mutex);
    if (!result && mutex == &route_mutex && !pthread_equal(pthread_self(), status_owner))
    {
        assert(!pthread_mutex_lock(&status_gate_mutex));
        if (status_gate_armed && !status_gate_entered)
        {
            struct hiby_pcm_output_status status;
            assert(hiby_pcm_get_output_status(&status));
            if (status.loss_generation)
            {
                status_gate_entered = true;
                assert(!pthread_cond_broadcast(&status_gate_changed));
                while (!status_gate_release)
                    assert(!pthread_cond_wait(&status_gate_changed, &status_gate_mutex));
            }
        }
        else if (status_gate_entered && status_gate_release)
        {
            status_gate_completed = true;
            assert(!pthread_cond_broadcast(&status_gate_changed));
        }
        assert(!pthread_mutex_unlock(&status_gate_mutex));
    }
    return result;
}

static void status_wait_gate(bool *condition)
{
    struct timespec deadline;
    assert(!clock_gettime(CLOCK_REALTIME, &deadline));
    deadline.tv_sec += 5;
    while (!*condition)
        assert(!pthread_cond_timedwait(&status_gate_changed, &status_gate_mutex, &deadline));
}

static struct hiby_pcm_output_status status_snapshot(void)
{
    struct hiby_pcm_output_status status;
    assert(hiby_pcm_get_output_status(&status));
    if (status.active_output == HIBY_PCM_OUTPUT_NONE)
        assert(!status.active_device[0]);
    else if (status.active_output == HIBY_PCM_OUTPUT_WIRED)
        assert(!strcmp(status.active_device, LOCAL_DEVICE));
    else
    {
        assert(status.active_output == HIBY_PCM_OUTPUT_BLUETOOTH);
        assert(!strcmp(status.active_device, bt_device));
    }
    if (!status.initialized)
        assert(status.active_output == HIBY_PCM_OUTPUT_NONE);
    return status;
}

static struct hiby_pcm_output_status status_wait(enum hiby_pcm_output output)
{
    long long deadline = now_ms() + 2000;
    for (;;)
    {
        struct hiby_pcm_output_status status = status_snapshot();
        if (status.active_output == output)
            return status;
        assert(now_ms() < deadline);
        delay_ms(2);
    }
}

static void status_start(void)
{
    builtin_pcm_sink.ops.init();
    status_wait(HIBY_PCM_OUTPUT_WIRED);
}

static void status_kill_helper(void)
{
    sink_lock();
    pid_t process = active_helper.process;
    sink_unlock();
    assert(process > 0 && !kill(process, SIGKILL));
}

static bool status_loss_matches_current_intent(struct hiby_pcm_output_status status, uint32_t seen_loss)
{
    return status.initialized && !status.stopping && status.loss_generation != seen_loss &&
        status.loss_intent_generation == status.route_intent_generation;
}

static int status_finish(bool valid, int failure)
{
    struct hiby_pcm_output_status before = status_snapshot();
    hiby_pcm_shutdown();
    verify_reaped();
    struct hiby_pcm_output_status status = status_snapshot();
    assert(!status.initialized && status.stopping);
    assert(status.loss_generation == before.loss_generation);
    return valid ? 0 : failure;
}

static void *status_observer(void *context)
{
    (void)context;
    while (!__atomic_load_n(&status_observer_stop, __ATOMIC_ACQUIRE))
    {
        struct hiby_pcm_output_status status = status_snapshot();
        assert(!status.loss_generation);
        __atomic_add_fetch(&status_observations, 1, __ATOMIC_RELAXED);
        delay_ms(1);
    }
    return NULL;
}

int main(int argc, char **argv)
{
    int helper = hiby_pcm_helper_main(argc, argv);
    if (helper >= 0)
        return helper;
    assert(argc == 2);
    const char *scenario = argv[1];
    status_owner = pthread_self();
    if (!strcmp(scenario, "preinit"))
    {
        assert(!mutex_ready && !initialized && !spawn_attempts && !sample_rate);
        assert(!hiby_pcm_get_output_status(NULL));
        struct hiby_pcm_output_status status = status_snapshot();
        assert(!status.initialized && !status.stopping && !status.state_generation);
        assert(!status.route_intent_generation && !status.loss_generation && !status.error_generation);
        assert(!status.last_error && !status.loss_error && !status.lost_device[0]);
        assert(!mutex_ready && !initialized && !spawn_attempts && !sample_rate);
        puts("TRACE preinit_snapshot_no_pcm_initialization=1 helper_spawns=0");
        return 0;
    }
    if (!strcmp(scenario, "sync-init-failure"))
    {
        __atomic_store_n(&status_condition_fail, true, __ATOMIC_RELEASE);
        builtin_pcm_sink.ops.init();
        struct hiby_pcm_output_status first = status_snapshot();
        builtin_pcm_sink.ops.init();
        assert(pcm_alsa_switch_playback_device(LOCAL_DEVICE) == -EIO);
        struct hiby_pcm_output_status repeated = status_snapshot();
        assert(!first.initialized && first.active_output == HIBY_PCM_OUTPUT_NONE);
        assert(first.last_error == -EIO && first.error_generation == 1);
        assert(repeated.error_generation == first.error_generation && !repeated.loss_generation);
        assert(!mutex_ready && !spawn_attempts);
        puts("TRACE failed_sync_init_error_generation=1 repeated_failure_coalesced=1 no_loss=1");
        return 0;
    }
    if (!strcmp(scenario, "init-failure"))
    {
        __atomic_store_n(&status_create_fail, true, __ATOMIC_RELEASE);
        builtin_pcm_sink.ops.init();
        struct hiby_pcm_output_status first = status_snapshot();
        builtin_pcm_sink.ops.init();
        struct hiby_pcm_output_status repeated = status_snapshot();
        assert(!first.initialized && first.active_output == HIBY_PCM_OUTPUT_NONE);
        assert(first.last_error == -EAGAIN && first.error_generation == 1);
        assert(repeated.error_generation == first.error_generation && !repeated.loss_generation);
        assert(!spawn_attempts);
        puts("TRACE failed_thread_init_error_generation=1 repeated_failure_coalesced=1 no_loss=1");
        return 0;
    }
    if (!strcmp(scenario, "startup-failure"))
    {
        assert(!setenv("PCM_MODE", "open-fail", 1));
        pcm_alsa_set_playback_device(bt_device);
        builtin_pcm_sink.ops.init();
        struct hiby_pcm_output_status status = status_wait(HIBY_PCM_OUTPUT_WIRED);
        printf("TRACE startup_bt_failure_loss=%u error_generation=%u error=%d\n",
               status.loss_generation, status.error_generation, status.last_error);
        return status_finish(!status.loss_generation && status.error_generation == 1 &&
                             status.last_error == -ENODEV, 152);
    }
    status_start();
    if (!strcmp(scenario, "cancelled-candidate"))
    {
        struct hiby_pcm_output_status before = status_snapshot();
        __atomic_store_n(&cancel_route, true, __ATOMIC_RELEASE);
        assert(pcm_alsa_switch_playback_device_cancellable(bt_device, cancelled, NULL) == -ECANCELED);
        struct hiby_pcm_output_status after = status_snapshot();
        printf("TRACE cancelled_candidate_loss=%u error_generation=%u\n", after.loss_generation, after.error_generation);
        return status_finish(after.active_output == HIBY_PCM_OUTPUT_WIRED && !after.loss_generation &&
                             after.error_generation == before.error_generation, 152);
    }
    assert(!pcm_alsa_switch_playback_device(bt_device));
    struct hiby_pcm_output_status bluetooth = status_snapshot();
    assert(bluetooth.active_output == HIBY_PCM_OUTPUT_BLUETOOTH);
    if (!strcmp(scenario, "manual-wired"))
    {
        assert(!pcm_alsa_switch_playback_device(bt_device));
        struct hiby_pcm_output_status same = status_snapshot();
        assert(same.state_generation == bluetooth.state_generation);
        assert(same.route_intent_generation == bluetooth.route_intent_generation + 1);
        assert(!pcm_alsa_switch_playback_device(LOCAL_DEVICE));
        struct hiby_pcm_output_status wired = status_snapshot();
        printf("TRACE manual_wired_loss=%u state_generation=%u intent_generation=%u\n",
               wired.loss_generation, wired.state_generation, wired.route_intent_generation);
        return status_finish(!wired.loss_generation && !wired.error_generation &&
                             wired.active_output == HIBY_PCM_OUTPUT_WIRED, 152);
    }
    if (!strcmp(scenario, "sticky-loss"))
    {
        status_kill_helper();
        struct hiby_pcm_output_status lost = status_wait(HIBY_PCM_OUTPUT_WIRED);
        delay_ms(350);
        struct hiby_pcm_output_status repeated = status_snapshot();
        bool valid = lost.loss_generation == 1 && lost.loss_intent_generation == bluetooth.route_intent_generation &&
            lost.loss_error == -EPIPE && lost.last_error == -EPIPE && lost.error_generation == 1 &&
            !strcmp(lost.lost_device, bt_device) && repeated.loss_generation == lost.loss_generation &&
            repeated.error_generation == lost.error_generation;
        assert(!pcm_alsa_switch_playback_device(bt_device));
        struct hiby_pcm_output_status renewed = status_snapshot();
        status_kill_helper();
        struct hiby_pcm_output_status second = status_wait(HIBY_PCM_OUTPUT_WIRED);
        valid = valid && second.loss_generation == 2 && second.error_generation == 2 &&
            second.loss_intent_generation == renewed.route_intent_generation;
        hiby_pcm_shutdown();
        struct hiby_pcm_output_status closed = status_snapshot();
        valid = valid && closed.loss_generation == second.loss_generation && closed.last_error == -EPIPE;
        printf("TRACE sticky_loss_first=%u second=%u after_shutdown=%u error_generation=%u\n",
               lost.loss_generation, second.loss_generation, closed.loss_generation, second.error_generation);
        return status_finish(valid, 151);
    }
    if (!strcmp(scenario, "reopen-success") || !strcmp(scenario, "reopen-failure"))
    {
        bool failing = !strcmp(scenario, "reopen-failure");
        assert(!pthread_mutex_lock(&route_mutex));
        if (failing)
            assert(!setenv("PCM_MODE", "open-fail", 1));
        builtin_pcm_sink.ops.set_freq(1);
        struct hiby_pcm_output_status detached = status_wait(HIBY_PCM_OUTPUT_NONE);
        assert(!detached.loss_generation && !detached.error_generation);
        assert(!pthread_mutex_unlock(&route_mutex));
        struct hiby_pcm_output_status after = status_wait(failing ? HIBY_PCM_OUTPUT_WIRED : HIBY_PCM_OUTPUT_BLUETOOTH);
        bool valid = failing ? after.loss_generation == 1 && after.loss_error == -ENODEV &&
            after.loss_intent_generation == bluetooth.route_intent_generation :
            !after.loss_generation && !after.error_generation;
        valid = valid && after.state_generation > bluetooth.state_generation;
        printf("TRACE reopen_failing=%d loss=%u error_generation=%u\n",
               failing, after.loss_generation, after.error_generation);
        return status_finish(valid, 153);
    }
    if (!strcmp(scenario, "newer-manual-intent"))
    {
        assert(!setenv("PCM_MODE", "local-open-fail", 1));
        assert(pcm_alsa_switch_playback_device(LOCAL_DEVICE) == -ENODEV);
        struct hiby_pcm_output_status manual = status_snapshot();
        assert(manual.route_intent_generation > bluetooth.route_intent_generation);
        status_kill_helper();
        long long deadline = now_ms() + 1500;
        struct hiby_pcm_output_status lost;
        do
        {
            lost = status_snapshot();
            assert(now_ms() < deadline);
            delay_ms(2);
        } while (!lost.loss_generation);
        bool valid = lost.loss_intent_generation == bluetooth.route_intent_generation &&
            !status_loss_matches_current_intent(lost, 0);
        printf("TRACE newer_manual_intent=%u captured_loss_intent=%u controller_pause_eligible=%d\n",
               lost.route_intent_generation, lost.loss_intent_generation, status_loss_matches_current_intent(lost, 0));
        return status_finish(valid, 154);
    }
    if (!strcmp(scenario, "pool-exhausted-reopen"))
    {
        __atomic_store_n(&hold_reaping, true, __ATOMIC_RELEASE);
        for (;;)
        {
            unsigned int occupied = 0;
            assert(!pthread_mutex_lock(&pool_mutex));
            for (unsigned int position = 0; position < PCM_PROCESS_SLOTS; position++)
                if (process_pool[position])
                    occupied++;
            assert(!pthread_mutex_unlock(&pool_mutex));
            if (occupied == PCM_PROCESS_SLOTS)
                break;
            sink_lock();
            uint32_t before_state = status_snapshot().state_generation;
            last_activity = 0;
            assert(!pcm_alsa_switch_playback_device(bt_device));
            assert(status_snapshot().state_generation != before_state);
            sink_unlock();
        }
        struct hiby_pcm_output_status committed = status_snapshot();
        builtin_pcm_sink.ops.set_freq(1);
        long long deadline = now_ms() + 1500;
        struct hiby_pcm_output_status lost;
        do
        {
            lost = status_snapshot();
            assert(now_ms() < deadline);
            delay_ms(2);
        } while (!lost.loss_generation);
        bool valid = lost.loss_generation == 1 && lost.loss_error == -EBUSY &&
            lost.loss_intent_generation == committed.route_intent_generation;
        printf("TRACE exhausted_helper_pool_loss=%u error=%d output=%d\n",
               lost.loss_generation, lost.loss_error, lost.active_output);
        __atomic_store_n(&hold_reaping, false, __ATOMIC_RELEASE);
        return status_finish(valid, 153);
    }
    if (!strcmp(scenario, "stale-fallback"))
    {
        assert(!pthread_mutex_lock(&status_gate_mutex));
        status_gate_armed = true;
        assert(!setenv("PCM_MODE", "open-fail", 1));
        builtin_pcm_sink.ops.set_freq(1);
        status_wait_gate(&status_gate_entered);
        assert(!pthread_mutex_unlock(&status_gate_mutex));
        struct hiby_pcm_output_status lost = status_snapshot();
        assert(lost.loss_generation == 1 && lost.loss_intent_generation == bluetooth.route_intent_generation);
        assert(!setenv("PCM_MODE", "good", 1));
        assert(!pcm_alsa_switch_playback_device(bt_device));
        struct hiby_pcm_output_status manual = status_snapshot();
        bool valid = manual.route_intent_generation > lost.loss_intent_generation &&
            !status_loss_matches_current_intent(manual, 0);
        assert(!pthread_mutex_lock(&status_gate_mutex));
        status_gate_release = true;
        assert(!pthread_cond_broadcast(&status_gate_changed));
        status_wait_gate(&status_gate_completed);
        assert(!pthread_mutex_unlock(&status_gate_mutex));
        struct hiby_pcm_output_status after = status_snapshot();
        valid = valid && after.active_output == HIBY_PCM_OUTPUT_BLUETOOTH && after.loss_generation == 1 &&
            after.loss_intent_generation == lost.loss_intent_generation && !status_loss_matches_current_intent(after, 0);
        printf("TRACE stale_fallback_active=%d loss=%u loss_intent=%u current_intent=%u\n",
               after.active_output, after.loss_generation, after.loss_intent_generation, after.route_intent_generation);
        return status_finish(valid, 155);
    }
    if (!strcmp(scenario, "error-retries"))
    {
        assert(!setenv("PCM_MODE", "local-open-fail", 1));
        status_kill_helper();
        long long deadline = now_ms() + 1500;
        struct hiby_pcm_output_status failed;
        do
        {
            failed = status_snapshot();
            assert(now_ms() < deadline);
            delay_ms(2);
        } while (failed.last_error != -ENODEV);
        delay_ms(900);
        struct hiby_pcm_output_status repeated = status_snapshot();
        printf("TRACE failed_wired_retry_loss=%u errors_before=%u errors_after=%u output=%d\n",
               repeated.loss_generation, failed.error_generation, repeated.error_generation, repeated.active_output);
        return status_finish(failed.loss_generation == 1 && repeated.loss_generation == 1 &&
                             failed.error_generation == repeated.error_generation &&
                             repeated.active_output == HIBY_PCM_OUTPUT_NONE, 151);
    }
    if (!strcmp(scenario, "generation-wrap"))
    {
        assert(!pthread_mutex_lock(&output_status_mutex));
        output_status.loss_generation = UINT32_MAX;
        output_status.error_generation = UINT32_MAX;
        output_status.state_generation = UINT32_MAX;
        assert(!pthread_mutex_unlock(&output_status_mutex));
        status_kill_helper();
        struct hiby_pcm_output_status lost = status_wait(HIBY_PCM_OUTPUT_WIRED);
        bool valid = !lost.loss_generation && !lost.error_generation && lost.last_error == -EPIPE &&
            lost.loss_error == -EPIPE && status_loss_matches_current_intent(lost, UINT32_MAX);
        printf("TRACE wrapped_loss_generation=%u error_generation=%u pending_from_max=%d\n",
               lost.loss_generation, lost.error_generation, status_loss_matches_current_intent(lost, UINT32_MAX));
        return status_finish(valid, 151);
    }
    if (!strcmp(scenario, "coherent-snapshots"))
    {
        pthread_t observer;
        assert(!pthread_create(&observer, NULL, status_observer, NULL));
        for (unsigned int iteration = 0; iteration < 24; iteration++)
        {
            assert(!pcm_alsa_switch_playback_device(LOCAL_DEVICE));
            assert(!pcm_alsa_switch_playback_device(bt_device));
        }
        __atomic_store_n(&status_observer_stop, true, __ATOMIC_RELEASE);
        assert(!pthread_join(observer, NULL));
        assert(status_observations >= 8);
        printf("TRACE coherent_concurrent_snapshots=%u manual_route_changes=48\n", status_observations);
        return status_finish(true, 151);
    }
    assert(false);
}
