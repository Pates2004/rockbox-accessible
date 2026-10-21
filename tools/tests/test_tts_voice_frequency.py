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
#include <limits.h>
#include <string.h>
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define VOICE_FRAME_COUNT 320
#define VOICE_PCM_FRAME_COUNT 1920
#define VOICE_EVENT_IS_PLAYING 1
#define QUIET_COUNT 3
#define MIX_AMP_UNITY 0x00010000
#define PCM_MIXER_CHAN_VOICE 1
enum { DSP_GET_OUT_FREQUENCY, DSP_SET_OUT_FREQUENCY, DSP_FLUSH, DSP_SET_FREQUENCY };
static int quiet_counter;
static bool voice_playing, voice_pcm_paused, interrupted;
static unsigned output_rate, dsp_rate, input_rate, configurations, frames, events;
static unsigned mixer_amplitude, amplitude_calls;
static struct { int16_t spx_outbuf[320]; } storage;
static __typeof__(storage) *voice_buf = &storage;
struct dsp_buffer {
    int remcount, bufcount;
    const int16_t *pin[2];
    int16_t *p16out;
    unsigned proc_mask;
};
struct voice_thread_data {
    void *dsp;
    unsigned pcm_sample_rate;
    struct dsp_buffer src;
    struct dsp_buffer *dst;
};
struct voice_pcm_info {
    const int16_t *samples;
    size_t count;
    unsigned sample_rate;
    uint32_t generation;
};
static struct voice_thread_data data;
static bool voice_pcm_interrupted(uint32_t generation) { (void)generation; return interrupted; }
static unsigned mixer_get_frequency(void) { return output_rate; }
static void mixer_channel_set_amplitude(int channel, unsigned amplitude)
{
    if (channel == PCM_MIXER_CHAN_VOICE) {
        mixer_amplitude = amplitude;
        ++amplitude_calls;
    }
}
static intptr_t dsp_configure(void *dsp, int operation, intptr_t value)
{
    (void)dsp;
    if (operation == DSP_GET_OUT_FREQUENCY) return dsp_rate;
    if (operation == DSP_SET_OUT_FREQUENCY) { dsp_rate = value; ++configurations; }
    if (operation == DSP_SET_FREQUENCY) input_rate = value;
    return 0;
}
static void trigger_cpu_boost(void) {}
static void send_event(int event, const bool *playing) { (void)event; (void)playing; ++events; }
static int16_t *voice_buf_get(void) { static int16_t buffer[3840]; return buffer; }
static void sleep(int ticks) { (void)ticks; }
static void yield(void) {}
static void pcm_play_lock(void) {}
static void pcm_play_unlock(void) {}
static void voice_buf_commit(int count) { frames += count; }
static void voice_start_playback(void) {}
static void dsp_process(void *dsp, struct dsp_buffer *source, struct dsp_buffer *target, bool enabled)
{
    (void)dsp; (void)enabled;
    target->remcount = source->remcount;
    target->bufcount -= source->remcount;
    source->remcount = 0;
}
"""
SUFFIX = r"""
void test_reset(unsigned previous, unsigned current, int quiet)
{
    memset(&data, 0, sizeof(data));
    dsp_rate = previous; output_rate = current; quiet_counter = quiet;
    configurations = frames = events = input_rate = 0;
    mixer_amplitude = amplitude_calls = 0;
    interrupted = voice_playing = voice_pcm_paused = false;
}
int test_packet(unsigned rate)
{
    static const int16_t samples[640] = { 100, -100 };
    struct voice_pcm_info pcm = { samples, 640, rate, 1 };
    return voice_process_pcm(&data, &pcm);
}
void test_cancel(void) { interrupted = true; }
unsigned test_dsp_rate(void) { return dsp_rate; }
unsigned test_input_rate(void) { return input_rate; }
unsigned test_configurations(void) { return configurations; }
unsigned test_frames(void) { return frames; }
unsigned test_events(void) { return events; }
unsigned test_amplitude(void) { return mixer_amplitude; }
unsigned test_amplitude_calls(void) { return amplitude_calls; }
"""


class VoiceFrequencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = _project_materials_root(ROOT) / "tts-voice-frequency-tests" / stamp
        cls.workspace.mkdir(parents=True)
        source = (ROOT / "apps/voice_thread.c").read_text(encoding="utf-8")
        harness = cls.workspace / "frequency.c"
        harness.write_text(PREFIX + extract_block(source, "static bool voice_process_pcm(") + SUFFIX,
                           encoding="utf-8")
        library = cls.workspace / "frequency.so"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
            "-fno-sanitize-recover=all", str(harness), "-o", str(library)]
        subprocess.run(command, check=True)
        (cls.workspace / "command.json").write_text(json.dumps(command), encoding="utf-8")
        cls.library = ctypes.CDLL(str(library))

    def test_recording_transition_does_not_reuse_quiet_tail_dsp_rate(self):
        library = self.library
        for frequency in (16000, 22050, 24000, 32000, 44100, 48000, 64000, 88200, 96000):
            with self.subTest(frequency=frequency):
                library.test_reset(44100, frequency, 3)
                self.assertEqual(library.test_packet(22050), 1)
                self.assertEqual(library.test_dsp_rate(), frequency)
                self.assertEqual(library.test_input_rate(), 22050)
                self.assertEqual(library.test_frames(), 640)
                self.assertEqual(library.test_configurations(), int(frequency != 44100))
                self.assertEqual(library.test_amplitude(), 0x10000)
                self.assertEqual(library.test_amplitude_calls(), 1)

    def test_idle_and_contiguous_packets_use_current_rate_without_resetting_it(self):
        library = self.library
        library.test_reset(88200, 44100, 0)
        self.assertEqual(library.test_packet(22050), 1)
        self.assertEqual(library.test_events(), 1)
        self.assertEqual(library.test_amplitude(), 0x10000)
        self.assertEqual(library.test_amplitude_calls(), 1)
        self.assertEqual(library.test_packet(22050), 1)
        self.assertEqual(library.test_configurations(), 1)
        self.assertEqual(library.test_frames(), 1280)
        self.assertEqual(library.test_amplitude(), 0x10000)
        self.assertEqual(library.test_amplitude_calls(), 2)

    def test_invalid_rate_or_cancelled_packet_does_not_reconfigure_or_play(self):
        library = self.library
        for current, cancelled in ((0, False), (96000, True)):
            library.test_reset(44100, current, 3)
            if cancelled:
                library.test_cancel()
            self.assertEqual(library.test_packet(22050), 0)
            self.assertEqual(library.test_configurations(), 0)
            self.assertEqual(library.test_frames(), 0)
            self.assertEqual(library.test_amplitude_calls(), 0)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(VoiceFrequencyTests))
    (VoiceFrequencyTests.workspace / "report.json").write_text(json.dumps({
        "tests": result.testsRun, "passed": result.wasSuccessful()}, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
