#include "bluetooth_policy.h"

#include <limits.h>
#include <stddef.h>

static int64_t bounded_add(int64_t value, int64_t increment)
{
    return value > INT64_MAX - increment ? INT64_MAX : value + increment;
}

void bluetooth_reconnect_stop(struct bluetooth_reconnect_policy *policy)
{
    if (policy)
        policy->active = false;
}

static bool check_time(struct bluetooth_reconnect_policy *policy, int64_t now_ms)
{
    if (!policy || !policy->active)
        return false;
    if (now_ms < 0 || now_ms < policy->last_now_ms ||
        now_ms >= policy->deadline_ms || policy->attempts >= 8 ||
        policy->next_attempt_ms < 0)
    {
        bluetooth_reconnect_stop(policy);
        return false;
    }
    policy->last_now_ms = now_ms;
    return true;
}

void bluetooth_reconnect_begin(struct bluetooth_reconnect_policy *policy,
    enum bluetooth_reconnect_reason reason, enum bluetooth_reconnect_mode mode,
    unsigned int retry_seconds, int64_t now_ms)
{
    if (!policy)
        return;
    if (now_ms < 0 || mode < BLUETOOTH_RECONNECT_STARTUP ||
        mode > BLUETOOTH_RECONNECT_STARTUP_AND_LOSS ||
        reason < BLUETOOTH_RECONNECT_ON_STARTUP || reason > BLUETOOTH_RECONNECT_ON_LOSS ||
        (reason == BLUETOOTH_RECONNECT_ON_LOSS && mode != BLUETOOTH_RECONNECT_STARTUP_AND_LOSS) ||
        (retry_seconds != 30 && retry_seconds != 60 && retry_seconds != 120 && retry_seconds != 300))
    {
        bluetooth_reconnect_stop(policy);
        return;
    }
    if (policy->active)
    {
        check_time(policy, now_ms);
        return;
    }
    policy->attempts = 0;
    policy->last_now_ms = now_ms;
    policy->deadline_ms = bounded_add(now_ms, (int64_t)retry_seconds * 1000);
    policy->next_attempt_ms = now_ms;
    policy->active = policy->deadline_ms > now_ms;
}

bool bluetooth_reconnect_due(struct bluetooth_reconnect_policy *policy,
                            int64_t now_ms)
{
    return check_time(policy, now_ms) && now_ms >= policy->next_attempt_ms;
}

int bluetooth_reconnect_remaining(struct bluetooth_reconnect_policy *policy,
                                 int64_t now_ms)
{
    if (!check_time(policy, now_ms))
        return 0;
    int64_t remaining = policy->deadline_ms - now_ms;
    return remaining > INT_MAX ? INT_MAX : (int)remaining;
}

void bluetooth_reconnect_attempted(struct bluetooth_reconnect_policy *policy,
                                  int64_t now_ms, bool success)
{
    if (!bluetooth_reconnect_due(policy, now_ms))
        return;
    policy->attempts++;
    if (success || policy->attempts >= 8)
    {
        bluetooth_reconnect_stop(policy);
        return;
    }
    int64_t delay_ms = policy->attempts < 5 ?
        (int64_t)1000 << policy->attempts : 30000;
    policy->next_attempt_ms = bounded_add(now_ms, delay_ms);
    if (policy->next_attempt_ms >= policy->deadline_ms)
        policy->next_attempt_ms = policy->deadline_ms;
}
