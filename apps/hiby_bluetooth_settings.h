#ifndef HIBY_BLUETOOTH_SETTINGS_H
#define HIBY_BLUETOOTH_SETTINGS_H

#include "bluetooth_policy.h"

enum hiby_bt_preference
{
    HIBY_BT_PREF_AUTOCONNECT,
    HIBY_BT_PREF_RETRY_SECONDS,
    HIBY_BT_PREF_PAUSE_ON_LOSS,
    HIBY_BT_PREF_ANNOUNCE
};

struct hiby_bt_preferences
{
    enum bluetooth_reconnect_mode auto_mode;
    unsigned int retry_seconds;
    bool pause_on_loss;
    bool announce;
    char last_address[18];
    unsigned int generation;
};

int hiby_bt_preferences_get(struct hiby_bt_preferences *preferences);
int hiby_bt_preferences_set(enum hiby_bt_preference preference, int value);
int hiby_bt_preferences_remember(const char *address);
int hiby_bt_preferences_forget(const char *address);

#endif
