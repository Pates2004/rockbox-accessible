#ifndef POWER_CONTROL_HIBY_H
#define POWER_CONTROL_HIBY_H

#include <stdbool.h>

enum hiby_wifi_state
{
    HIBY_WIFI_BLOCKED,
    HIBY_WIFI_NO_RADIO,
    HIBY_WIFI_UNCONFIRMED,
    HIBY_WIFI_ERROR,
    HIBY_WIFI_ENABLED,
    HIBY_WIFI_HARD_BLOCKED,
    HIBY_WIFI_INTERFACE_DOWN,
    HIBY_WIFI_DRIVER_SUSPENDED
};

struct hiby_wifi_result
{
    enum hiby_wifi_state state;
    unsigned int wlan_radios;
    unsigned int interfaces_down;
    int rfkill_error;
    int interface_error;
    unsigned int interfaces_up;
    unsigned int interfaces_present;
    unsigned int soft_blocked_radios;
    unsigned int hard_blocked_radios;
    int rfkill_read_error;
    int interface_read_error;
    bool rfkill_sysfs;
    int driver_error;
};

struct hiby_poweroff_result
{
    int command_error;
    int child_error;
    int reboot_error;
};

struct hiby_wifi_result hiby_wifi_disable(void);
struct hiby_wifi_result hiby_wifi_set_enabled(bool enabled);
struct hiby_wifi_result hiby_wifi_get_state(void);
int hiby_bluetooth_rfkill_blocked(bool *blocked);
void hiby_wifi_cancel(void);
bool hiby_wifi_settled(void);
struct hiby_poweroff_result hiby_poweroff(void);

#endif
