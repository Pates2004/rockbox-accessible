#ifndef HIBY_BLUETOOTH_H
#define HIBY_BLUETOOTH_H

#include "bluetooth-hiby.h"

struct hiby_bt_request
{
    unsigned int id;
    unsigned int intent;
    unsigned int permission;
    enum hiby_bt_operation operation;
    bool automatic;
};

struct hiby_bt_service_observation;

bool hiby_bluetooth_init(void);
void hiby_bluetooth_shutdown(void);
void hiby_bluetooth_cancel(void);
void hiby_bluetooth_set_inhibited(bool inhibited);
bool hiby_bluetooth_is_inhibited(void);
bool hiby_bluetooth_request(enum hiby_bt_operation operation, const char *address);
bool hiby_bluetooth_request_automatic(enum hiby_bt_operation operation,
                                      const char *address, unsigned int timeout_ms);
bool hiby_bluetooth_request_guarded(enum hiby_bt_operation operation,
    const char *address, unsigned int timeout_ms,
    const struct hiby_bt_request *expected, struct hiby_bt_request *issued);
bool hiby_bluetooth_cancel_automatic(void);
void hiby_bluetooth_get_snapshot(struct hiby_bt_snapshot *snapshot);
void hiby_bluetooth_get_observation(struct hiby_bt_snapshot *snapshot,
    struct hiby_bt_service_observation *observation);
int hiby_bluetooth_menu(void);

#endif
