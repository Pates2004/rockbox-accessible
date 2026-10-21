#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "audio.h"
struct queue_event;
#include "audio_thread.h"

enum { PLAY_STOPPED = 0, PLAY_PLAYING = 1, PLAY_PAUSED = 3 };
static unsigned int play_status;
static bool codec_skip_pending;
static bool ff_rw_mode;
static int codec_skip_status;
static struct { bool fade_on_stop; } global_settings;
struct audio_resume_info { unsigned long elapsed; unsigned long offset; };
static void iap_on_play_status(unsigned int value) { (void)value; }
static void audio_on_codec_complete(int value) { (void)value; }
static void pcmbuf_fade(bool fade, bool resume) { (void)fade; (void)resume; }
static void pcmbuf_pause(bool pause) { (void)pause; }
#define AUDIO_PAUSE_HOST_TEST
#include "playback.c"

intptr_t audio_queue_send(long identifier, intptr_t payload)
{
    if (identifier == Q_AUDIO_PLAY)
        play_status = PLAY_PLAYING;
    else if (identifier == Q_AUDIO_STOP)
        play_status = PLAY_STOPPED;
    else if (identifier == Q_AUDIO_PAUSE)
        audio_on_pause(payload != 0);
#if (defined(HIBY_R1) && defined(HAVE_ESPEAK) && !defined(SIMULATOR) && !defined(BOOTLOADER)) || defined(HIBY_BT_SERVICE_HOST_TEST)
    else if (identifier == Q_AUDIO_PAUSE_GUARDED)
        audio_on_pause_guarded((struct guarded_pause_request *)payload);
#endif
    else
        assert(false);
    return 0;
}

#if (defined(HIBY_R1) && defined(HAVE_ESPEAK) && !defined(SIMULATOR) && !defined(BOOTLOADER)) || defined(HIBY_BT_SERVICE_HOST_TEST)
static bool begin(void *context) { (void)context; return true; }
static void end(void *context) { (void)context; }
#endif

int main(void)
{
    audio_play(0, 0);
    assert(play_status == PLAY_PLAYING);
    audio_pause();
    assert(play_status == PLAY_PAUSED);
    audio_resume();
    assert(play_status == PLAY_PLAYING);
#if (defined(HIBY_R1) && defined(HAVE_ESPEAK) && !defined(SIMULATOR) && !defined(BOOTLOADER)) || defined(HIBY_BT_SERVICE_HOST_TEST)
    assert(audio_pause_guarded(audio_playback_generation(), begin, end, NULL));
    assert(play_status == PLAY_PAUSED);
#endif
    audio_stop();
    assert(play_status == PLAY_STOPPED);
    puts("normal API linked and state transitions verified");
    return 0;
}
