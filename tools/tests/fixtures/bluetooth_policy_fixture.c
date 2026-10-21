#include "bluetooth_policy.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

int main(void)
{
    const unsigned int windows[] = {30, 60, 120, 300};
    unsigned int completed = 0;
    for (unsigned int window = 0; window < 4; window++)
    {
        for (int64_t offset = 0; offset <= 10000; offset += 137)
        {
            struct bluetooth_reconnect_policy policy = {0};
            bluetooth_reconnect_begin(&policy, BLUETOOTH_RECONNECT_ON_LOSS,
                BLUETOOTH_RECONNECT_STARTUP_AND_LOSS, windows[window], offset);
            int64_t deadline = policy.deadline_ms;
            int64_t now = offset;
            while (policy.active)
            {
                assert(policy.deadline_ms == deadline);
                assert(policy.attempts <= 8);
                if (bluetooth_reconnect_due(&policy, now))
                    bluetooth_reconnect_attempted(&policy, now, false);
                assert(bluetooth_reconnect_remaining(&policy, now) >= 0);
                now += 19;
            }
            completed++;
        }
    }
    for (int64_t offset = 0; offset < 10000; offset += 13)
    {
        struct bluetooth_reconnect_policy policy = {0};
        int64_t now = INT64_MAX - offset;
        bluetooth_reconnect_begin(&policy, BLUETOOTH_RECONNECT_ON_STARTUP,
            BLUETOOTH_RECONNECT_STARTUP, 300, now);
        assert(policy.deadline_ms == INT64_MAX);
        bluetooth_reconnect_attempted(&policy, now, false);
        assert(!bluetooth_reconnect_due(&policy, INT64_MAX));
        assert(!policy.active);
        completed++;
    }
    printf("PASS policy sanitizer timelines: %u\n", completed);
    return 0;
}
