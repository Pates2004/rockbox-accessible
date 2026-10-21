"""Exercise the real C mixer/voice handoff with a deterministic PCM sink."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import unittest

from test_tts_coverage import extract_block


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "firmware/pcm_mixer.c", "firmware/pcm.c", "firmware/export/pcm-internal.h",
    "firmware/export/pcm_mixer.h", "firmware/asm/pcm-mixer.c",
    "firmware/general.c", "apps/voice_thread.c",
)


def function(source, name):
    returns = r"(?:void\s*\*{0,2}|bool|int|unsigned int|enum pcm_dma_status|enum channel_status)"
    pattern = (r"^(?:static\s+)?(?:(?:inline|FORCE_INLINE)\s+)?" + returns
               + r"\s*(?:MIXER_CALLBACK_ICODE\s+)?" + re.escape(name)
               + r"\s*\([^;{}]*\)\s*\{")
    matches = list(re.finditer(pattern, source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"Expected one definition of {name}, found {len(matches)}")
    return extract_block(source, matches[0].group())


PREAMBLE = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#define HAVE_ESPEAK 1
#define HAVE_RECORDING 1
#define HAVE_PCM_RECORDING_VOICE 1
#define HW_HAVE_192 1
#define SAMPR_48 48000
#define SAMPR_96 96000
#define IBSS_ATTR
#define DOWNMIX_BUF_IBSS
#define MEM_ALIGN_ATTR
#define MIXER_CALLBACK_ICODE
#define FORCE_INLINE inline
#define LIKELY(value) (value)
#define UNLIKELY(value) (value)
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define MIX_AMP_UNITY 0x10000
#define MIX_AMP_MUTE 0
#define VOICE_FRAMES 4
#define VOICE_PCM_FRAME_COUNT (MIX_FRAME_SAMPLES * 4)
#define VOICE_EVENT_IS_PLAYING 1
#define ALIGN_AUDIOBUF(start, size) do { \
    (start) = (void *)(((uintptr_t)(start) + 3) & ~(uintptr_t)3); \
    (size) &= ~(size_t)3; } while (0)
#define logf(...) ((void)0)
#define mixer_buffer_callback_exit() ((void)0)
enum pcm_dma_status { PCM_DMAST_ERR = -1, PCM_DMAST_OK, PCM_DMAST_STARTED };
typedef void (*pcm_play_callback_type)(const void **, size_t *);
typedef enum pcm_dma_status (*pcm_status_callback_type)(enum pcm_dma_status);
volatile pcm_play_callback_type pcm_callback_for_more;
volatile pcm_status_callback_type pcm_play_status_callback;
static bool pcm_playing, mock_recording, voice_pcm_paused, voice_playing;
static uint64_t voice_pcm_elapsed_us;
static unsigned frequency, lock_depth, sink_starts, sink_stops, events;
static const void *sink_data;
static size_t sink_size, heard_nonzero;
static int16_t first_heard;
static void require(bool condition, const char *message)
{
    if (!condition) { fprintf(stderr, "FAIL: %s\n", message); exit(1); }
}
static void pcm_play_lock(void) { ++lock_depth; }
static void pcm_play_unlock(void)
{
    require(lock_depth != 0, "balanced PCM lock");
    --lock_depth;
}
static bool pcm_is_recording(void) { return mock_recording; }
static unsigned pcm_get_frequency(void) { return frequency; }
static void pcm_set_frequency(unsigned value) { frequency = value; }
static bool pcm_is_initialized(void) { return true; }
static void pcm_apply_settings(void) {}
static void pcm_play_dma_start_int(const void *address, size_t size)
{
    require(lock_depth != 0, "start under PCM lock");
    sink_data = address;
    sink_size = size;
    ++sink_starts;
}
static void pcm_play_dma_stop_int(void)
{
    require(lock_depth != 0, "stop under PCM lock");
    sink_data = NULL;
    sink_size = 0;
    ++sink_stops;
}
static void send_event(int event, const bool *playing)
{
    (void)event; (void)playing; ++events;
}
static int16_t clip_sample_16(int32_t value)
{
    return value < INT16_MIN ? INT16_MIN : value > INT16_MAX ? INT16_MAX : value;
}
static void pcm_play_stop_int(void);
static enum pcm_dma_status pcm_play_dma_status_callback(enum pcm_dma_status status);
static enum pcm_dma_status MIXER_CALLBACK_ICODE
mixer_buffer_callback(enum pcm_dma_status status);
"""

BASELINE_CALLBACK = r"""
static void mixer_pcm_callback(const void **addr, size_t *size)
{
    *addr = downmix_buf[downmix_index];
    *size = next_size;
}
"""

VOICE_STATE = r"""
static struct {
    unsigned int volatile frame_in, frame_out;
    struct voice_pcm_frame {
        size_t size;
        unsigned int frequency;
        int16_t pcm[2 * VOICE_PCM_FRAME_COUNT];
    } frames[VOICE_FRAMES];
} voice_storage, *voice_buf = &voice_storage;
"""

CHECKS = r"""
static uint32_t audio_source[VOICE_PCM_FRAME_COUNT], beep_source[VOICE_PCM_FRAME_COUNT];

static size_t count_nonzero(const void *address, size_t size)
{
    const int16_t *samples = address;
    size_t count = 0;
    for (size_t index = 0; index < size / sizeof(*samples); ++index)
        count += samples[index] != 0;
    return count;
}

static bool sink_step(void)
{
    if (!pcm_is_playing()) return false;
    pcm_play_lock();
    require(sink_data && sink_size, "playing sink has a complete buffer");
    size_t nonzero = count_nonzero(sink_data, sink_size);
    if (!heard_nonzero && nonzero)
        first_heard = ((const int16_t *)sink_data)[0];
    heard_nonzero += nonzero;
    const void *address = NULL;
    size_t size = 0;
    bool available = pcm_play_dma_complete_callback(PCM_DMAST_OK, &address, &size);
    if (available)
    {
        sink_data = address;
        sink_size = size;
        require(pcm_play_dma_status_callback(PCM_DMAST_STARTED) == PCM_DMAST_OK,
                "successful buffering callback");
    }
    pcm_play_unlock();
    return available;
}

static void drain_sink(void)
{
    for (unsigned count = 0; pcm_is_playing() && count < 10000; ++count)
        sink_step();
    require(!pcm_is_playing(), "bounded natural sink completion");
    require(lock_depth == 0, "locks balanced after completion");
}

static void reset(void)
{
    memset(channels, 0, sizeof(channels));
    memset(active_channels, 0, sizeof(active_channels));
    memset(downmix_buf, 0, sizeof(downmix_buf));
    memset(&voice_storage, 0, sizeof(voice_storage));
    downmix_index = 0; next_size = 0; idle_counter = 0;
    mix_frame_size = MIX_FRAME_SAMPLES * 4;
    frequency = 44100;
    lock_depth = sink_starts = sink_stops = events = 0;
    sink_data = NULL; sink_size = heard_nonzero = 0; first_heard = 0;
    pcm_callback_for_more = NULL; pcm_play_status_callback = NULL;
    pcm_playing = mock_recording = voice_pcm_paused = false;
    voice_playing = true; voice_pcm_elapsed_us = 0;
    for (unsigned channel = 0; channel < PCM_MIXER_NUM_CHANNELS; ++channel)
        mixer_channel_set_amplitude(channel, MIX_AMP_UNITY);
    for (unsigned index = 0; index < VOICE_PCM_FRAME_COUNT; ++index)
    {
        audio_source[index] = 0x03e803e8;
        beep_source[index] = 0x0bb80bb8;
    }
}

static void queue_voice(unsigned count, int16_t value)
{
    require(count && count <= VOICE_PCM_FRAME_COUNT, "voice frame capacity");
    require(voice_unplayed_frames() < VOICE_FRAMES, "free voice ring frame");
    struct voice_pcm_frame *frame = &voice_buf->frames[voice_buf->frame_in % VOICE_FRAMES];
    for (unsigned index = 0; index < 2 * count; ++index)
        frame->pcm[index] = value;
    pcm_play_lock();
    voice_buf_commit(count);
    voice_start_playback();
    pcm_play_unlock();
}

static void prepare_tail(bool terminal)
{
    queue_voice(8, 400);
    for (unsigned count = 0; count < 10000; ++count)
    {
        bool boundary = terminal ? next_size == 0 :
                        next_size != 0 && idle_counter == max_idle_frames();
        if (boundary && !active_channels[0] && pcm_is_playing())
        {
            require(sink_size != 0 && count_nonzero(sink_data, sink_size) == 0,
                    "last valid sink buffer is silence");
            require(!voice_unplayed_frames(), "seed voice fully consumed");
            heard_nonzero = 0; first_heard = 0;
            return;
        }
        require(pcm_is_playing(), "tail boundary reached before sink stopped");
        sink_step();
    }
    require(false, "tail boundary reached in bounded steps");
}

static void terminal_voice(unsigned count, bool recording)
{
    mock_recording = recording;
    prepare_tail(true);
    unsigned starts = sink_starts;
    queue_voice(count, 2000);
    require(next_size == 0 && pcm_is_playing(), "activation preserves handoff gap");
    require(mixer_channel_status(PCM_MIXER_CHAN_VOICE) == CHANNEL_PLAYING,
            "new voice channel active before completion");
    require(count_nonzero(sink_data, sink_size) == 0, "activation does not overwrite live silence");
    require(sink_step(), "new voice data returned at terminal handoff");
    require(count_nonzero(sink_data, sink_size) != 0, "handoff returns actual nonzero PCM");
    drain_sink();
    require(heard_nonzero == 2 * count, "all submitted stereo samples heard once");
    require(first_heard == 2000, "heard new voice rather than old silence");
    require(!voice_unplayed_frames(), "voice source callback consumed ring");
    require(mixer_channel_status(PCM_MIXER_CHAN_VOICE) == CHANNEL_STOPPED,
            "no stranded PLAYING voice channel");
    require(sink_starts == starts, "hot handoff does not restart DMA");
}

static void demonstrate_baseline(void)
{
    prepare_tail(true);
    queue_voice(8, 2000);
    require(!sink_step(), "old callback stops on stale terminal zero");
    require(!pcm_is_playing() && heard_nonzero == 0, "old sink stops without new speech");
    require(mixer_channel_status(PCM_MIXER_CHAN_VOICE) == CHANNEL_PLAYING,
            "old channel stranded PLAYING");
    require(voice_unplayed_frames() == 1, "old voice source remains unconsumed");
    for (unsigned count = 1; count < VOICE_FRAMES; ++count)
        queue_voice(8, 2000);
    require(voice_unplayed_frames() == VOICE_FRAMES, "old producer fills ring");
    voice_start_playback();
    require(!pcm_is_playing(), "old voice helper cannot restart PLAYING channel");
    voice_stop_playback();
    require(!voice_unplayed_frames(), "explicit cancellation resets old ring");
    queue_voice(8, 2000);
    drain_sink();
    require(heard_nonzero == 16, "next utterance recovers after cancellation");
}

static void pause_at_tail(void)
{
    prepare_tail(true);
    queue_voice(8, 2000);
    unsigned starts = sink_starts;
    voice_pause_pcm(true);
    require(mixer_channel_status(PCM_MIXER_CHAN_VOICE) == CHANNEL_PAUSED,
            "pause deactivates channel");
    require(!sink_step() && heard_nonzero == 0, "paused channel does not revive sink");
    require(voice_unplayed_frames() == 1, "pause retains unconsumed frame");
    voice_pause_pcm(false);
    require(sink_starts == starts + 1, "resume cold-starts stopped sink");
    drain_sink();
    require(heard_nonzero == 16 && !voice_unplayed_frames(), "resume hears retained frame once");
}

static void stop_at_tail(void)
{
    prepare_tail(true);
    queue_voice(8, 2000);
    voice_stop_playback();
    require(!sink_step() && heard_nonzero == 0, "stopped channel cannot revive sink");
    require(!voice_unplayed_frames() && !active_channels[0], "stop clears ring and channel");
}

static void timing_neighbor(bool after)
{
    prepare_tail(after);
    unsigned starts = sink_starts;
    if (after) require(!sink_step(), "natural tail completes before late activation");
    queue_voice(8, 2000);
    drain_sink();
    require(heard_nonzero == 16 && !voice_unplayed_frames(), "neighbor timing preserves voice");
    require(sink_starts == starts + (after ? 1 : 0), "appropriate cold versus hot start");
}

static void multiple_channels(bool playback_only)
{
    prepare_tail(true);
    static const struct mixer_play_cbs callbacks = { 0 };
    mixer_channel_play_data(PCM_MIXER_CHAN_PLAYBACK, &callbacks, audio_source, 32);
    if (!playback_only)
    {
        queue_voice(8, 2000);
        mixer_channel_play_data(PCM_MIXER_CHAN_BEEP, &callbacks, beep_source, 32);
    }
    require(sink_step(), "active channels survive terminal completion");
    drain_sink();
    require(heard_nonzero == 16, "mixed output samples heard exactly once");
    require(first_heard == (playback_only ? 1000 : 6000), "real mixer sums expected samples");
    require(!active_channels[0] && !voice_unplayed_frames(), "all mixed sources complete");
}

static void frequency_transition(unsigned rate)
{
    prepare_tail(true);
    unsigned starts = sink_starts;
    mixer_set_frequency(rate);
    require(!pcm_is_playing() && mixer_get_frequency() == rate, "frequency change stops old sink");
    unsigned multiplier = rate > SAMPR_96 ? 4 : rate > SAMPR_48 ? 2 : 1;
    require(mix_frame_size == MIX_FRAME_SAMPLES * 4 * multiplier, "rate sets correct frame capacity");
    queue_voice(mix_frame_size / 4, 2000);
    drain_sink();
    require(heard_nonzero == mix_frame_size / 2, "new rate preserves complete voice PCM");
    require(sink_starts == starts + 1 && !voice_unplayed_frames(), "new rate restarts and drains normally");
}

int main(int argc, char **argv)
{
    require(argc >= 2, "scenario argument");
    reset();
    if (!strcmp(argv[1], "baseline")) demonstrate_baseline();
    else if (!strcmp(argv[1], "terminal"))
    {
        require(argc == 4, "terminal frame count and recording arguments");
        terminal_voice((unsigned)strtoul(argv[2], NULL, 10), atoi(argv[3]) != 0);
    }
    else if (!strcmp(argv[1], "cold"))
    {
        pcm_play_data(mixer_pcm_callback, mixer_buffer_callback, NULL, 0);
        require(!pcm_is_playing() && !active_channels[0] && !sink_starts,
                "cold empty mixer naturally stays stopped");
    }
    else if (!strcmp(argv[1], "natural"))
    {
        prepare_tail(true);
        require(!sink_step() && !pcm_is_playing() && !active_channels[0],
                "empty natural tail still stops");
    }
    else if (!strcmp(argv[1], "pause")) pause_at_tail();
    else if (!strcmp(argv[1], "stop")) stop_at_tail();
    else if (!strcmp(argv[1], "before")) timing_neighbor(false);
    else if (!strcmp(argv[1], "after")) timing_neighbor(true);
    else if (!strcmp(argv[1], "playback")) multiple_channels(true);
    else if (!strcmp(argv[1], "multiple")) multiple_channels(false);
    else if (!strcmp(argv[1], "frequency"))
    {
        require(argc == 3, "frequency argument");
        frequency_transition((unsigned)strtoul(argv[2], NULL, 10));
    }
    else require(false, "known scenario");
    require(lock_depth == 0, "balanced final PCM lock");
    printf("PASS %s\n", argv[1]);
    return 0;
}
"""


def harness_source(inputs):
    mixer = inputs["firmware/pcm_mixer.c"]
    pcm = inputs["firmware/pcm.c"]
    internal = inputs["firmware/export/pcm-internal.h"]
    header = inputs["firmware/export/pcm_mixer.h"]
    voice = inputs["apps/voice_thread.c"]
    pieces = [PREAMBLE]
    for signature in ("enum pcm_mixer_channel", "enum channel_status",
                      "struct mixer_play_cbs", "struct mixer_buffer_cbs"):
        pieces.append(extract_block(header, signature) + ";\n")
    pieces.extend(function(internal, name) for name in (
        "pcm_get_more_int", "pcm_call_status_cb", "pcm_play_call_status_cb",
        "pcm_play_dma_status_callback"))
    pieces.extend(function(pcm, name) for name in (
        "pcm_play_stop_int", "pcm_play_dma_complete_callback", "pcm_is_playing",
        "pcm_play_data", "pcm_play_stop"))
    pieces.append(mixer[mixer.index("static unsigned int mix_frame_size"):
                        mixer.index("static inline unsigned int max_idle_frames")])
    pieces.append(function(mixer, "max_idle_frames"))
    pieces.extend(function(inputs["firmware/asm/pcm-mixer.c"], name)
                  for name in ("mix_samples", "write_samples"))
    pieces.extend(function(inputs["firmware/general.c"], name)
                  for name in ("find_array_ptr", "remove_array_ptr"))
    pieces.extend(function(mixer, name) for name in (
        "mixer_activate_channel", "mixer_deactivate_channel", "channel_stopped"))
    pieces.extend(("#ifdef RETAINED_BASELINE\n", BASELINE_CALLBACK, "#else\n",
                   function(mixer, "mixer_pcm_callback"), "#endif\n"))
    pieces.extend(function(mixer, name) for name in (
        "chan_call_buffer_hook", "mixer_buffer_callback", "mixer_start_pcm",
        "mixer_handle_sampr_change", "mixer_channel_play_data", "mixer_channel_play_pause",
        "mixer_channel_stop", "mixer_channel_set_amplitude", "mixer_channel_status",
        "mixer_set_frequency", "mixer_get_frequency"))
    pieces.append(VOICE_STATE)
    pieces.extend(function(voice, name) for name in (
        "voice_unplayed_frames", "voice_pcm_callback", "voice_start_playback",
        "voice_stop_playback", "voice_buf_commit", "voice_pause_pcm"))
    pieces.append(CHECKS)
    return "\n".join(pieces)


@unittest.skipUnless(os.name == "posix", "Run the ASan/UBSan C harness under WSL/Linux")
class MixerRestartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("A C compiler is required")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = _project_materials_root(ROOT) / "tts-mixer-restart-tests" / stamp
        cls.workspace.mkdir(parents=True)
        cls.evidence = []
        cls.executables = {}
        inputs = {path: (ROOT / path).read_bytes().decode("utf-8") for path in INPUTS}
        cls.harness = cls.workspace / "mixer-restart.c"
        generated = harness_source(inputs)
        cls.harness.write_text(generated, encoding="utf-8")
        (cls.workspace / "sources.json").write_text(json.dumps({
            "method": "Extracted actual mixer, PCM dispatch and voice C; deterministic sink; ASan/UBSan",
            "hardware_validated": False,
            "mocked_components": ["PCM sink", "lock nesting", "sample-rate backend", "event delivery"],
            "limitations": ["No GUI, engine/DSP synthesis, real threads, DMA or hardware recording"],
            "source_sha256": {path: hashlib.sha256(text.encode()).hexdigest()
                              for path, text in inputs.items()},
            "harness_sha256": hashlib.sha256(generated.encode()).hexdigest(),
            "retained_baseline_callback": BASELINE_CALLBACK,
        }, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        (cls.workspace / "results.json").write_text(
            json.dumps(cls.evidence, indent=2) + "\n", encoding="utf-8")

    def run_command(self, arguments, label, expected=0):
        result = subprocess.run(arguments, text=True, capture_output=True, timeout=45,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
                                         UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
        self.evidence.append(dict(label=label, command=arguments, returncode=result.returncode,
                                  expected_returncode=expected, stdout=result.stdout, stderr=result.stderr))
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return result

    def executable(self, frame_samples, baseline=False):
        variant = f"{'baseline' if baseline else 'current'}-{frame_samples}"
        if variant not in self.executables:
            executable = self.workspace / variant
            command = self.compiler + [
                "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-fno-pie", "-no-pie", "-fsanitize=address,undefined",
                "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                f"-DMIX_FRAME_SAMPLES={frame_samples}",
            ]
            if baseline:
                command.append("-DRETAINED_BASELINE")
            self.run_command(command + [str(self.harness), "-o", str(executable)], variant + "-compile")
            self.executables[variant] = executable
        return self.executables[variant]

    def test_baseline_callback_strands_voice_and_fails_delivery_invariant(self):
        for frame_samples in (256, 1024):
            with self.subTest(frame_samples=frame_samples):
                executable = self.executable(frame_samples, baseline=True)
                self.run_command([str(executable), "baseline"], f"baseline-proof-{frame_samples}")
                result = self.run_command([str(executable), "terminal", "8", "0"],
                                          f"baseline-invariant-fails-{frame_samples}", expected=1)
                self.assertIn("new voice data returned at terminal handoff", result.stderr)

    def test_current_terminal_handoff_delivers_short_full_and_partial_voice(self):
        for frame_samples in (256, 1024):
            executable = self.executable(frame_samples)
            for count in (1, 8, frame_samples, frame_samples + 3, 3 * frame_samples):
                for recording in (0, 1):
                    with self.subTest(frame_samples=frame_samples, count=count, recording=recording):
                        self.run_command([str(executable), "terminal", str(count), str(recording)],
                                         f"current-terminal-{frame_samples}-{count}-{recording}")

    def test_empty_pause_cancel_neighbor_and_multiple_channel_invariants(self):
        for frame_samples in (256, 1024):
            executable = self.executable(frame_samples)
            for scenario in ("cold", "natural", "pause", "stop", "before", "after", "playback", "multiple"):
                with self.subTest(frame_samples=frame_samples, scenario=scenario):
                    self.run_command([str(executable), scenario], f"current-{frame_samples}-{scenario}")

    def test_samplerate_changes_leave_no_stale_terminal_handoff(self):
        for frame_samples in (256, 1024):
            executable = self.executable(frame_samples)
            for rate in (16000, 48000, 96000, 192000):
                with self.subTest(frame_samples=frame_samples, rate=rate):
                    self.run_command([str(executable), "frequency", str(rate)],
                                     f"current-{frame_samples}-frequency-{rate}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
