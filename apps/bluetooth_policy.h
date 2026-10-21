#ifndef BLUETOOTH_POLICY_H
#define BLUETOOTH_POLICY_H

#include <stdbool.h>
#include <stdint.h>

enum bluetooth_reconnect_mode
{
    BLUETOOTH_RECONNECT_OFF = 0,
    BLUETOOTH_RECONNECT_STARTUP = 1,
    BLUETOOTH_RECONNECT_STARTUP_AND_LOSS = 2
};

enum bluetooth_reconnect_reason
{
    BLUETOOTH_RECONNECT_ON_STARTUP = 0,
    BLUETOOTH_RECONNECT_ON_LOSS = 1
};

struct bluetooth_reconnect_policy
{
    bool active;
    unsigned int attempts;
    int64_t deadline_ms;
    int64_t next_attempt_ms;
    int64_t last_now_ms;
};

void bluetooth_reconnect_begin(struct bluetooth_reconnect_policy *policy,
    enum bluetooth_reconnect_reason reason, enum bluetooth_reconnect_mode mode,
    unsigned int retry_seconds, int64_t now_ms);
void bluetooth_reconnect_stop(struct bluetooth_reconnect_policy *policy);
bool bluetooth_reconnect_due(struct bluetooth_reconnect_policy *policy,
                            int64_t now_ms);
int bluetooth_reconnect_remaining(struct bluetooth_reconnect_policy *policy,
                                 int64_t now_ms);
void bluetooth_reconnect_attempted(struct bluetooth_reconnect_policy *policy,
                                  int64_t now_ms, bool success);

#endif
