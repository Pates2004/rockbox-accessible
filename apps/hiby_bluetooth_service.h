#ifndef HIBY_BLUETOOTH_SERVICE_H
#define HIBY_BLUETOOTH_SERVICE_H

#include "hiby_bluetooth.h"

struct hiby_bt_service_status
{
    bool running;
    bool allowed;
    bool suppressed;
    bool monitoring;
    bool reconnecting;
    unsigned int attempts;
    int storage_error;
};

struct hiby_bt_service_observation
{
    bool allowed;
    bool suppressed;
    unsigned int intent;
    unsigned int permission;
    unsigned int startup;
    unsigned int completion;
    struct hiby_bt_request request;
    enum hiby_bt_error result;
    unsigned int connection;
    unsigned int connection_intent;
    char address[18];
    char name[HIBY_BT_NAME_SIZE];
};

#if defined(HIBY_BT_HOST_TEST) && !defined(HIBY_BT_SERVICE_HOST_TEST)
static inline void hiby_bluetooth_service_allow(bool allowed) { (void)allowed; }
static inline bool hiby_bluetooth_service_requested(struct hiby_bt_request *request,
    const struct hiby_bt_request *expected)
{
    (void)request;
    (void)expected;
    return true;
}
static inline bool hiby_bluetooth_service_current(const struct hiby_bt_request *request)
{
    (void)request;
    return true;
}
static inline void hiby_bluetooth_service_completed(const struct hiby_bt_request *request,
    struct hiby_bt_snapshot *snapshot, struct hiby_bt_snapshot *published)
{
    (void)request;
    *published = *snapshot;
}
static inline void hiby_bluetooth_service_persist(const struct hiby_bt_request *request,
    const char *address, const struct hiby_bt_snapshot *snapshot)
{
    (void)request;
    (void)address;
    (void)snapshot;
}
static inline void hiby_bluetooth_service_observe(struct hiby_bt_service_observation *observation)
{ *observation = (struct hiby_bt_service_observation){0}; }
static inline void hiby_bluetooth_service_cancelled(void) {}
#else
bool hiby_bluetooth_service_start(void);
void hiby_bluetooth_service_shutdown(void);
void hiby_bluetooth_service_allow(bool allowed);
bool hiby_bluetooth_service_requested(struct hiby_bt_request *request,
    const struct hiby_bt_request *expected);
bool hiby_bluetooth_service_current(const struct hiby_bt_request *request);
void hiby_bluetooth_service_completed(const struct hiby_bt_request *request,
    struct hiby_bt_snapshot *snapshot, struct hiby_bt_snapshot *published);
void hiby_bluetooth_service_persist(const struct hiby_bt_request *request,
    const char *address, const struct hiby_bt_snapshot *snapshot);
void hiby_bluetooth_service_observe(struct hiby_bt_service_observation *observation);
void hiby_bluetooth_service_cancelled(void);
void hiby_bluetooth_service_get_status(struct hiby_bt_service_status *status);
int hiby_bluetooth_service_adjust_timeout(int timeout);
void hiby_bluetooth_service_process_notifications(void);
#endif

#endif
