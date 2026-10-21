#ifndef BLUETOOTH_MONITOR_HIBY_H
#define BLUETOOTH_MONITOR_HIBY_H

#include <stdbool.h>

enum hiby_bt_monitor_result
{
    HIBY_BT_MONITOR_IDLE = 0,
    HIBY_BT_MONITOR_WAKE,
    HIBY_BT_MONITOR_CHANGED,
    HIBY_BT_MONITOR_FAILED
};

bool hiby_bt_monitor_init(void);
bool hiby_bt_monitor_start(void);
enum hiby_bt_monitor_result hiby_bt_monitor_wait(int timeout_ms);
void hiby_bt_monitor_wake(void);
void hiby_bt_monitor_stop(void);
void hiby_bt_monitor_shutdown(void);
bool hiby_bt_monitor_active(void);

#endif
