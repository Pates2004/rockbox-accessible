import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import unittest

from test_tts_coverage import extract_block


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
PREFIX = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define HAVE_ESPEAK 1
#define VOICE_FRAMES 8
#define PCM_MIXER_CHAN_VOICE 0
#define CHANNEL_STOPPED 0
#define CHANNEL_PLAYING 1
#define CHANNEL_PAUSED 2
#define VOICE_EVENT_IS_PLAYING 1
static bool voice_pcm_paused;
static bool voice_playing = true;
static uint64_t voice_pcm_elapsed_us;
struct voice_pcm_frame { size_t size; unsigned frequency; int16_t pcm[1024]; };
static struct { unsigned frame_in, frame_out; struct voice_pcm_frame frames[8]; } storage;
static __typeof__(storage) *voice_buf = &storage;
static int status, locks, starts;
static bool audible;
static size_t waiting;
static unsigned frequency = 48000;
static uint32_t current_generation;
static int voice_queue;
#define QPEEK_FILTER2(first, last) 0
#define Q_VOICE_PLAY 0
#define Q_VOICE_KILL 2
static bool queued_stop;
static bool tts_request_cancelled(uint32_t generation) { return generation != current_generation; }
static bool queue_peek_ex(int *queue, void *event, int head, int filter)
{ (void)queue; (void)event; (void)head; (void)filter; return queued_stop; }
struct mixer_play_cbs { void (*get_more)(const void **, size_t *); };
static void pcm_play_lock(void) { ++locks; }
static void pcm_play_unlock(void) { --locks; }
static int mixer_channel_status(int channel) { (void)channel; return status; }
static size_t mixer_channel_get_bytes_waiting(int channel) { (void)channel; return waiting; }
static unsigned mixer_get_frequency(void) { return frequency; }
static void mixer_channel_stop(int channel) { (void)channel; status = 0; waiting = 0; }
static void mixer_channel_play_pause(int channel, bool play)
{ (void)channel; if (status) status = play ? 1 : 2; }
static void mixer_channel_play_data(int channel, const struct mixer_play_cbs *callbacks,
                                    const void *start, size_t size)
{ (void)channel; (void)callbacks; (void)start; status = 1; waiting = size; ++starts; }
static void send_event(int event, const bool *playing) { (void)event; audible = *playing; }
"""
SUFFIX = r"""
void test_reset(void)
{
    memset(&storage, 0, sizeof(storage));
    status = locks = starts = 0;
    waiting = voice_pcm_elapsed_us = 0;
    voice_pcm_paused = audible = false;
    frequency = 48000;
    current_generation = 1;
    queued_stop = false;
}
void test_frame(int samples) { voice_buf_commit(samples); voice_start_playback(); }
void test_remaining(size_t bytes) { waiting = bytes; }
void test_complete(void)
{
    const void *start = NULL;
    size_t size = 0;
    voice_pcm_callback(&start, &size);
    waiting = size;
    if (!size) status = 0;
}
void test_frequency(unsigned value) { frequency = value; }
void test_stop(void) { voice_stop_playback(); }
int test_status(void) { return status; }
int test_starts(void) { return starts; }
int test_locks(void) { return locks; }
int test_audible(void) { return audible; }
unsigned test_pending(void) { return voice_unplayed_frames(); }
void test_generation(uint32_t generation) { current_generation = generation; }
void test_queued_stop(bool stop) { queued_stop = stop; }
int test_interrupted(uint32_t generation) { return voice_pcm_interrupted(generation); }
"""


class PlaybackClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = _project_materials_root(ROOT) / "tts-playback-clock-tests" / timestamp
        cls.workspace.mkdir(parents=True)
        source = (ROOT / "apps/voice_thread.c").read_text()
        signatures = (
            "static unsigned int voice_unplayed_frames(",
            "static void voice_pcm_callback(", "static void voice_start_playback(",
            "static void voice_stop_playback(", "static void voice_buf_commit(",
            "void voice_pause_pcm(", "uint32_t voice_pcm_elapsed_ms(",
            "static bool voice_pcm_interrupted(",
        )
        harness = cls.workspace / "harness.c"
        harness.write_text(PREFIX + "\n".join(extract_block(source, item) for item in signatures) + SUFFIX)
        library = cls.workspace / "clock.so"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror", str(harness), "-o", str(library)]
        subprocess.run(command, check=True)
        cls.library = ctypes.CDLL(str(library))
        (cls.workspace / "command.json").write_text(json.dumps(command))

    def setUp(self):
        self.library.test_reset()

    def test_clock_follows_consumed_not_queued_frames(self):
        library = self.library
        library.test_frame(480)
        library.test_frame(480)
        self.assertEqual(library.voice_pcm_elapsed_ms(), 0)
        library.test_remaining(960)
        self.assertEqual(library.voice_pcm_elapsed_ms(), 5)
        library.test_complete()
        self.assertEqual(library.voice_pcm_elapsed_ms(), 10)
        library.test_complete()
        self.assertEqual(library.voice_pcm_elapsed_ms(), 20)
        self.assertEqual(library.test_locks(), 0)

    def test_pause_preserves_pending_pcm_and_resumes_existing_channel(self):
        library = self.library
        library.test_frame(480)
        library.test_remaining(960)
        library.voice_pause_pcm(True)
        self.assertEqual(library.test_status(), 2)
        self.assertEqual(library.test_audible(), 0)
        library.test_frame(480)
        self.assertEqual(library.voice_pcm_elapsed_ms(), 5)
        self.assertEqual(library.test_pending(), 2)
        library.voice_pause_pcm(False)
        self.assertEqual(library.test_status(), 1)
        self.assertEqual(library.test_audible(), 1)
        self.assertEqual(library.test_starts(), 1)
        self.assertEqual(library.voice_pcm_elapsed_ms(), 5)
        self.assertEqual(library.test_locks(), 0)

    def test_pause_before_first_pcm_does_not_start_audio(self):
        library = self.library
        library.voice_pause_pcm(True)
        library.test_frame(480)
        self.assertEqual(library.test_starts(), 0)
        library.voice_pause_pcm(False)
        self.assertEqual(library.test_starts(), 1)
        library.test_stop()
        self.assertEqual(library.test_pending(), 0)

    def test_empty_timeout_does_not_clear_pause_while_synthesis_is_delayed(self):
        library = self.library
        library.voice_pause_pcm(True)
        library.test_stop()
        library.test_frame(480)
        self.assertEqual(library.test_starts(), 0)
        self.assertEqual(library.test_pending(), 1)
        library.voice_pause_pcm(False)
        self.assertEqual(library.test_starts(), 1)

    def test_consumer_rejects_packet_enqueued_after_cancellation(self):
        library = self.library
        self.assertEqual(library.test_interrupted(1), 0)
        library.test_generation(2)
        self.assertEqual(library.test_interrupted(1), 1)
        self.assertEqual(library.test_interrupted(2), 0)
        library.test_queued_stop(True)
        self.assertEqual(library.test_interrupted(2), 1)

    def test_clock_accounts_for_frame_output_frequency(self):
        library = self.library
        library.test_frame(480)
        library.test_frequency(24000)
        library.test_frame(480)
        library.test_complete()
        self.assertEqual(library.voice_pcm_elapsed_ms(), 10)
        library.test_complete()
        self.assertEqual(library.voice_pcm_elapsed_ms(), 30)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PlaybackClockTests))
    (PlaybackClockTests.workspace / "report.json").write_text(json.dumps({
        "tests": result.testsRun, "passed": result.wasSuccessful()}, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
