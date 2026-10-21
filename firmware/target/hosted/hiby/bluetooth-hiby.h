#ifndef BLUETOOTH_HIBY_H
#define BLUETOOTH_HIBY_H

#include <stdbool.h>
#include <stddef.h>

#define HIBY_BT_MAX_DEVICES 32
#define HIBY_BT_NAME_SIZE 128

enum hiby_bt_operation
{
    HIBY_BT_ENABLE,
    HIBY_BT_SCAN,
    HIBY_BT_CONNECT,
    HIBY_BT_DISCONNECT,
    HIBY_BT_DISABLE,
    HIBY_BT_REMOVE,
    HIBY_BT_REFRESH,
    HIBY_BT_CONNECT_PAIRED,
    HIBY_BT_VERIFY_LINK
};

enum hiby_bt_error
{
    HIBY_BT_OK,
    HIBY_BT_UNAVAILABLE,
    HIBY_BT_CANCELLED,
    HIBY_BT_TIMEOUT,
    HIBY_BT_INVALID_ADDRESS,
    HIBY_BT_COMMAND_FAILED,
    HIBY_BT_PAIR_FAILED,
    HIBY_BT_PIN_UNSUPPORTED,
    HIBY_BT_CONNECT_FAILED,
    HIBY_BT_AUDIO_FAILED,
    HIBY_BT_BUSY,
    HIBY_BT_THREAD_FAILED,
    HIBY_BT_POWERED_OFF,
    HIBY_BT_INHIBITED
};

struct hiby_bt_device
{
    char address[18];
    char name[HIBY_BT_NAME_SIZE];
    bool paired;
};

struct hiby_bt_snapshot
{
    bool available;
    bool enabled;
    bool busy;
    bool power_known;
    enum hiby_bt_error error;
    unsigned int generation;
    size_t count;
    char connected_address[18];
    char connected_name[HIBY_BT_NAME_SIZE];
    struct hiby_bt_device devices[HIBY_BT_MAX_DEVICES];
};

typedef bool (*hiby_bt_cancel_callback)(void *context);

bool hiby_bt_valid_address(const char *address);
size_t hiby_bt_parse_devices(const char *text, struct hiby_bt_device *devices,
                            size_t count, size_t capacity, bool paired);
enum hiby_bt_error hiby_bt_backend_execute(enum hiby_bt_operation operation,
    const char *address, struct hiby_bt_snapshot *state,
    hiby_bt_cancel_callback cancelled, void *context);
bool hiby_bt_backend_cleanup_pending(char address[18]);

int pcm_alsa_switch_playback_device(const char *device);
void pcm_alsa_set_bluetooth_volume(int left_centibels, int right_centibels);
bool pcm_alsa_bluetooth_active(void);

#endif
