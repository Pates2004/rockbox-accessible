#ifndef HIBY_CONNECTIVITY_H
#define HIBY_CONNECTIVITY_H

#include <stdbool.h>

enum hiby_connectivity_radio_state
{
    HIBY_CONNECTIVITY_UNKNOWN,
    HIBY_CONNECTIVITY_OFF,
    HIBY_CONNECTIVITY_ON,
    HIBY_CONNECTIVITY_PARTIAL,
    HIBY_CONNECTIVITY_UNAVAILABLE,
    HIBY_CONNECTIVITY_RADIO_ERROR,
    HIBY_CONNECTIVITY_INTERFACE_DOWN,
    HIBY_CONNECTIVITY_DRIVER_SUSPENDED
};

enum hiby_connectivity_result
{
    HIBY_CONNECTIVITY_OK,
    HIBY_CONNECTIVITY_FAILED,
    HIBY_CONNECTIVITY_NOT_AVAILABLE,
    HIBY_CONNECTIVITY_INCOMPLETE,
    HIBY_CONNECTIVITY_STORAGE_ERROR,
    HIBY_CONNECTIVITY_CANCELLED,
    HIBY_CONNECTIVITY_TIMEOUT,
    HIBY_CONNECTIVITY_BUSY,
    HIBY_CONNECTIVITY_INHIBITED
};

struct hiby_connectivity_snapshot
{
    bool wifi_desired;
    bool bluetooth_desired;
    bool airplane_mode;
    bool busy;
    bool inhibited;
    bool settled;
    enum hiby_connectivity_radio_state wifi;
    enum hiby_connectivity_radio_state bluetooth;
    enum hiby_connectivity_result result;
    int storage_error;
    unsigned int generation;
};

bool hiby_connectivity_init(void);
bool hiby_connectivity_apply_startup_policy(void);
bool hiby_connectivity_set_wifi_enabled(bool enabled);
bool hiby_connectivity_set_bluetooth_enabled(bool enabled);
bool hiby_connectivity_set_airplane_mode(bool enabled);
bool hiby_connectivity_refresh(void);
bool hiby_connectivity_wifi_desired(void);
bool hiby_connectivity_bluetooth_desired(void);
bool hiby_connectivity_airplane_mode(void);
void hiby_connectivity_get_snapshot(struct hiby_connectivity_snapshot *snapshot);
void hiby_connectivity_cancel(void);
void hiby_connectivity_shutdown(void);
int hiby_connectivity_menu(void);

#endif
