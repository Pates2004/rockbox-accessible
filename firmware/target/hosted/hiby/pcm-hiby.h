#ifndef PCM_HIBY_H
#define PCM_HIBY_H

#include <stdbool.h>
#include <stdint.h>

enum hiby_pcm_output {
    HIBY_PCM_OUTPUT_NONE,
    HIBY_PCM_OUTPUT_WIRED,
    HIBY_PCM_OUTPUT_BLUETOOTH
};

struct hiby_pcm_output_status {
    enum hiby_pcm_output active_output;
    bool initialized;
    bool stopping;
    uint32_t state_generation;
    uint32_t route_intent_generation;
    uint32_t loss_generation;
    uint32_t loss_intent_generation;
    uint32_t error_generation;
    int loss_error;
    int last_error;
    char active_device[96];
    char lost_device[96];
};

typedef bool (*hiby_pcm_cancel_callback)(void *context);

int hiby_pcm_helper_main(int argc, char **argv);
void hiby_pcm_shutdown(void);
bool hiby_pcm_get_output_status(struct hiby_pcm_output_status *status);
int pcm_alsa_switch_playback_device_cancellable(const char *device,
    hiby_pcm_cancel_callback cancelled, void *context);
int pcm_alsa_switch_playback_device(const char *device);
bool pcm_alsa_bluetooth_active(void);
void pcm_alsa_set_bluetooth_volume(int left_centibels, int right_centibels);

#endif
