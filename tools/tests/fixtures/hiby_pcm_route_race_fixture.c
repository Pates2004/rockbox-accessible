static pthread_mutex_t race_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t race_changed = PTHREAD_COND_INITIALIZER;
static pthread_t race_owner;
static unsigned int race_attempts, race_gate_attempt = 1;
static bool race_entered, race_release, race_completed, race_acknowledged;
static bool recovered_bluetooth;
static unsigned int recovered_epoch;
static char recovered_device[96];

static void race_wait(bool *condition)
{
    struct timespec deadline;
    assert(!clock_gettime(CLOCK_REALTIME, &deadline));
    deadline.tv_sec += 5;
    while (!*condition)
        assert(!pthread_cond_timedwait(&race_changed, &race_mutex, &deadline));
}

static int race_mutex_trylock(pthread_mutex_t *mutex)
{
    if (mutex == &route_mutex && !pthread_equal(pthread_self(), race_owner))
    {
        assert(!pthread_mutex_lock(&race_mutex));
        if (++race_attempts == race_gate_attempt && !race_entered)
        {
            race_entered = true;
            assert(!pthread_cond_broadcast(&race_changed));
            race_wait(&race_release);
        }
        assert(!pthread_mutex_unlock(&race_mutex));
    }
    return pthread_mutex_trylock(mutex);
}

static int race_mutex_unlock(pthread_mutex_t *mutex)
{
    int result = pthread_mutex_unlock(mutex);
    if (mutex == &route_mutex && !pthread_equal(pthread_self(), race_owner))
    {
        assert(!pthread_mutex_lock(&race_mutex));
        if (race_gate_attempt == 2 && race_attempts == 1 && !race_entered)
        {
            race_entered = true;
            assert(!pthread_cond_broadcast(&race_changed));
            race_wait(&race_release);
        }
        if (race_entered && race_attempts >= race_gate_attempt && !race_completed)
        {
            assert(!pthread_mutex_lock(&pcm_mutex));
            recovered_bluetooth = pcm_alsa_bluetooth_active();
            recovered_epoch = epoch;
            snprintf(recovered_device, sizeof(recovered_device), "%s", current_device);
            assert(!pthread_mutex_unlock(&pcm_mutex));
            race_completed = true;
            assert(!pthread_cond_broadcast(&race_changed));
            race_wait(&race_acknowledged);
        }
        assert(!pthread_mutex_unlock(&race_mutex));
    }
    return result;
}

int main(int argc, char **argv)
{
    int helper = hiby_pcm_helper_main(argc, argv);
    if (helper >= 0)
        return helper;
    assert(argc == 2);
    const char *scenario = argv[1];
    bool fallback = !strcmp(scenario, "stale-fallback");
    assert(fallback || !strcmp(scenario, "unchanged-local") ||
           !strcmp(scenario, "same-local") || !strcmp(scenario, "stale-local") ||
           !strcmp(scenario, "stale-bluetooth"));
    bool initial_bluetooth = fallback || !strcmp(scenario, "stale-bluetooth");
    bool explicit_request = strcmp(scenario, "unchanged-local") != 0;
    bool target_bluetooth = fallback || !strcmp(scenario, "stale-local");
    const char *initial_device = initial_bluetooth ? bt_device : LOCAL_DEVICE;
    const char *target_device = target_bluetooth ? bt_device : LOCAL_DEVICE;
    race_owner = pthread_self();
    if (fallback)
    {
        race_gate_attempt = 2;
        assert(!setenv("PCM_MODE", "open-fail", 1));
    }
    pcm_alsa_set_playback_device(initial_device);
    builtin_pcm_sink.ops.init();
    assert(!pthread_mutex_lock(&race_mutex));
    race_wait(&race_entered);
    assert(race_attempts == 1);
    assert(!pthread_mutex_unlock(&race_mutex));
    sink_lock();
    assert(initialized && active_helper.descriptor < 0);
    unsigned int before_epoch = epoch;
    assert(!strcmp(current_device, initial_device));
    sink_unlock();
    if (fallback)
        assert(!setenv("PCM_MODE", "good", 1));
    int explicit_result = explicit_request ? pcm_alsa_switch_playback_device(target_device) : 0;
    assert(!explicit_result);
    sink_lock();
    unsigned int explicit_epoch = epoch;
    if (explicit_request)
    {
        assert(active_helper.descriptor >= 0);
        assert(pcm_alsa_bluetooth_active() == target_bluetooth);
        assert(!strcmp(current_device, target_device));
    }
    sink_unlock();
    printf("TRACE explicit_success scenario=%s target=%s epoch_before=%u epoch_after=%u\n",
           scenario, target_device, before_epoch, explicit_epoch);
    assert(!pthread_mutex_lock(&race_mutex));
    race_release = true;
    assert(!pthread_cond_broadcast(&race_changed));
    race_wait(&race_completed);
    bool preserved = recovered_bluetooth == target_bluetooth &&
                     !strcmp(recovered_device, target_device);
    printf("TRACE automatic_finished scenario=%s device=%s bluetooth=%d epoch=%u preserved=%d\n",
           scenario, recovered_device, recovered_bluetooth, recovered_epoch, preserved);
    race_acknowledged = true;
    assert(!pthread_cond_broadcast(&race_changed));
    assert(!pthread_mutex_unlock(&race_mutex));
    hiby_pcm_shutdown();
    verify_reaped();
    puts("TRACE shutdown_complete helpers_reaped=1");
    if (!preserved)
    {
        fprintf(stderr, "CHECK_FAILED stale automatic recovery overwrote successful explicit route: %s\n",
                scenario);
        return 101;
    }
    printf("PASS %s\n", scenario);
    return 0;
}
