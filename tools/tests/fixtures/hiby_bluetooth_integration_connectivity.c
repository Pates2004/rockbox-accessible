#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#define HIBY_CONNECTIVITY_NO_UI
#include "hiby_connectivity.c"

void integration_connectivity_refresh(int barrier)
{
    state.bluetooth_desired = true;
    state.airplane_mode = barrier == 1;
    state.inhibited = barrier == 2;
    state.storage_error = barrier == 3 ? EIO : 0;
    struct connectivity_job job = {
        .operation = CONNECTIVITY_REFRESH,
        .bluetooth = true,
        .airplane = state.airplane_mode
    };
    execute_job(&job);
}
