#include <assert.h>
#include <limits.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "hiby_bluetooth.h"

bool hiby_bt_valid_address(const char *address)
{
    (void)address;
    assert(!"Address validation is not used by refresh-only worker tests");
    return false;
}

enum hiby_bt_error hiby_bt_backend_execute(enum hiby_bt_operation operation,
    const char *address, struct hiby_bt_snapshot *snapshot,
    hiby_bt_cancel_callback cancelled, void *context)
{
    (void)address;
    if (cancelled && cancelled(context))
        return HIBY_BT_CANCELLED;
    assert(operation == HIBY_BT_REFRESH);
    snapshot->available = true;
    snapshot->power_known = true;
    snapshot->enabled = false;
    return HIBY_BT_OK;
}

int main(void)
{
    for (unsigned int cycle = 0; cycle < 4; ++cycle)
    {
        assert(hiby_bluetooth_init());
        assert(hiby_bluetooth_request(HIBY_BT_REFRESH, NULL));
        struct hiby_bt_snapshot snapshot;
        for (unsigned int iteration = 0; iteration < 1000; ++iteration)
        {
            hiby_bluetooth_get_snapshot(&snapshot);
            if (!snapshot.busy)
                break;
            struct timespec delay = { .tv_nsec = 1000000 };
            nanosleep(&delay, NULL);
        }
        assert(!snapshot.busy && snapshot.generation == 2 && snapshot.error == HIBY_BT_OK);
        assert(snapshot.power_known && !snapshot.enabled && snapshot.available);
        hiby_bluetooth_shutdown();
    }
    printf("PASS bluetooth worker minimum=%lu\n", (unsigned long)PTHREAD_STACK_MIN);
    return 0;
}
