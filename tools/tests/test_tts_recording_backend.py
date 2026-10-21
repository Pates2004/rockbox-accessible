"""Run extracted AS3525 PCM/mixer functions with register mocks on a POSIX host."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import unittest


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = _project_materials_root(ROOT) / "tts-recording-backend" / datetime.datetime.now(
    datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def without_includes(text):
    return re.sub(r'^\s*#(?:include|pragma once)[^\n]*', '', text, flags=re.MULTILINE)


def function(text, name):
    pattern = (r'^(?:static\s+)?(?:(?:inline|FORCE_INLINE)\s+)?'
               r'(?:void|bool|int|unsigned int|enum pcm_dma_status)\s+'
               r'(?:MIXER_CALLBACK_ICODE\s+)?' + re.escape(name)
               + r'\s*\([^;{}]*\)\s*\{')
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"Expected one definition of {name}, got {len(matches)}")
    match = matches[0]
    depth = 1
    cursor = match.end()
    while depth:
        depth += (text[cursor] == '{') - (text[cursor] == '}')
        cursor += 1
    return text[match.start():cursor] + "\n"


PREAMBLE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#define HAVE_RECORDING
#define CONFIG_SAMPR_TYPES
#define AS3525 3525
#define AS3525v2 35252
#define INPUT_SRC_CAPS 3
#define SRC_CAP_MIC 1
#define SRC_CAP_FMRADIO 2
#define CONFIG_TUNER 1
#define SRCF_RECORDING 0x1000
#define AUDIO_NUM_SOURCES 2
#define AUDIO_SRC_PLAYBACK -1
#define AUDIO_SRC_MIC 0
#define AUDIO_SRC_FMRADIO 1
#define SAMPR_TYPE_MASK 0x70000000
#define SAMPR_TYPE_REC 0x10000000
#define HW_SAMPR_RESET 0
#define REC_SAMPR_DEFAULT 44100
#define SAMPR_96 96000
#define SAMPR_88 88200
#define SAMPR_64 64000
#define SAMPR_48 48000
#define SAMPR_44 44100
#define SAMPR_32 32000
#define SAMPR_24 24000
#define SAMPR_22 22050
#define SAMPR_16 16000
#define SAMPR_12 12000
#define SAMPR_11 11025
#define SAMPR_8 8000
#define REC_NUM_FREQ 9
#define SAMPR_NUM_FREQ 12
#define HW_NUM_FREQ 12
#define HW_FREQ_DEFAULT HW_FREQ_44
#define PCM_NATIVE_VOLUME_TYPE 0
#define AS3525_MCLK_FREQ 192000000
#define AS3525_MCLK_SEL 1
#define CGU_I2SOUT_APB_CLOCK_ENABLE 1
#define CGU_I2SIN_APB_CLOCK_ENABLE 2
#define INTERRUPT_I2SIN 0x2000
#define DMA_PERI_I2SOUT 3
#define DMAC_FLOWCTRL_DMAC_MEM_TO_PERI 1
#define DMA_S16 1
#define IBSS_ATTR
#define MEM_ALIGN_ATTR
#define FORCE_INLINE inline
#define LIKELY(value) (value)
#define UNLIKELY(value) (value)
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define ALIGN_AUDIOBUF(start, size) do { \
    (start) = (void *)(((uintptr_t)(start) + 3) & ~(uintptr_t)3); \
    (size) &= ~(size_t)3; } while (0)
#define pcm_rec_dma_addr(addr) (addr)
#define logf(...) ((void)0)
enum { HW_FREQ_96, HW_FREQ_88, HW_FREQ_64, HW_FREQ_48, HW_FREQ_44,
       HW_FREQ_32, HW_FREQ_24, HW_FREQ_22, HW_FREQ_16, HW_FREQ_12,
       HW_FREQ_11, HW_FREQ_8 };
static const unsigned long hw_freq_sampr[] = {
    96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050,
    16000, 12000, 11025, 8000
};
static const unsigned long rec_freq_sampr[] = {
    48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000
};
enum pcm_dma_status { PCM_DMAST_ERR = -1, PCM_DMAST_OK, PCM_DMAST_STARTED };
typedef void (*pcm_play_callback_type)(const void **addr, size_t *size);
typedef void (*pcm_rec_callback_type)(void **addr, size_t *size);
typedef enum pcm_dma_status (*pcm_status_callback_type)(enum pcm_dma_status);
struct pcm_peaks { int unused; };
static unsigned irq_level;
static unsigned codec_calls, frequency_writes, dma_references, dma_starts;
static volatile uint32_t CGU_PERI, CGU_AUDIO, VIC_INT_ENABLE, VIC_INT_EN_CLEAR;
static volatile uint8_t I2SOUT_CONTROL, I2SIN_CONTROL, I2SIN_MASK, I2SIN_CLEAR;
static volatile uint32_t output_data, input_data;
static uintptr_t dma_source_address[2];
#define DMAC_CH_SRC_ADDR(channel) dma_source_address[channel]
#define I2SOUT_DATA (&output_data)
#define I2SOUT_RAW_STATUS 0
static unsigned fifo_remaining, input_reads;
static unsigned mock_input_status(void) { return fifo_remaining ? 0 : 1 << 5; }
static volatile uint32_t *mock_input_data(void)
{
    assert(fifo_remaining);
    --fifo_remaining;
    input_data = 0x12340000u | ++input_reads;
    return &input_data;
}
#define I2SIN_RAW_STATUS mock_input_status()
#define I2SIN_DATA mock_input_data()
static int disable_irq_save(void)
{
    unsigned previous = irq_level;
    irq_level = 1;
    return previous;
}
static void restore_irq(int previous) { irq_level = previous; }
static void bitset32(volatile uint32_t *address, uint32_t value) { *address |= value; }
static void bitclr32(volatile uint32_t *address, uint32_t value) { *address &= ~value; }
static void bitmod32(volatile uint32_t *address, uint32_t value, uint32_t mask)
{
    assert(address == &CGU_AUDIO);
    ++frequency_writes;
    *address = (*address & ~mask) | value;
}
static void audiohw_preinit(void) { ++codec_calls; }
static void audiohw_postinit(void) { ++codec_calls; }
static void audiohw_set_monitor(bool enabled) { (void)enabled; ++codec_calls; }
static void audiohw_disable_recording(void) { ++codec_calls; }
static void audiohw_enable_recording(bool mic) { (void)mic; ++codec_calls; }
static int round_value_to_list32(unsigned long value, const unsigned long *values,
                                 int count, bool round_up)
{
    (void)round_up;
    for (int index = 0; index < count; ++index)
        if (value == values[index]) return index;
    return 0;
}
static void *mock_dma_buffer;
static size_t mock_dma_size;
static bool mock_dma_enabled;
static void (*mock_dma_callback)(void);
static void dma_retain(void) { ++dma_references; }
static void dma_release(void) { assert(dma_references); --dma_references; }
static void commit_dcache_range(const void *addr, size_t size) { assert(addr && size); }
static void dma_enable_channel(int channel, void *src, void *dst, int peri,
                               int flow, bool src_inc, bool dst_inc, size_t words,
                               int width, void (*callback)(void))
{
    assert(channel == 0 && dst == (void *)I2SOUT_DATA && peri == DMA_PERI_I2SOUT);
    assert(flow == DMAC_FLOWCTRL_DMAC_MEM_TO_PERI && src_inc && !dst_inc);
    assert(width == DMA_S16 && words);
    mock_dma_buffer = src;
    mock_dma_size = words * 4;
    mock_dma_callback = callback;
    mock_dma_enabled = true;
    ++dma_starts;
}
static void dma_disable_channel(int channel)
{
    assert(channel == 0);
    mock_dma_enabled = false;
}
static void **find_array_ptr(void **array, void *value)
{
    while (*array && *array != value) ++array;
    return array;
}
static void remove_array_ptr(void **array, void *value)
{
    array = find_array_ptr(array, value);
    if (*array) do { *array = array[1]; ++array; } while (*array);
}
static int16_t clip_sample_16(int32_t sample)
{
    return sample > INT16_MAX ? INT16_MAX : sample < INT16_MIN ? INT16_MIN : sample;
}
void pcm_play_lock(void);
void pcm_play_unlock(void);
bool pcm_is_playing(void);
bool pcm_is_recording(void);
unsigned int pcm_get_frequency(void);
void pcm_apply_settings(void);
void pcm_play_stop_int(void);
void pcm_play_stop(void);
void pcm_play_data(pcm_play_callback_type, pcm_status_callback_type, const void *, size_t);
bool pcm_play_dma_complete_callback(enum pcm_dma_status, const void **, size_t *);
bool pcm_rec_dma_complete_callback(enum pcm_dma_status, void **, size_t *);
static inline enum pcm_dma_status pcm_play_dma_status_callback(enum pcm_dma_status);
static inline enum pcm_dma_status pcm_rec_dma_status_callback(enum pcm_dma_status);
"""


CHECKS = r"""
static uint32_t recording_buffer[2], captured[4096], rendered[65536];
static size_t captured_count, rendered_count;
static unsigned expected_clock, expected_codec_calls, expected_frequency_writes;
static void more_recording(void **addr, size_t *size)
{
    assert(captured_count + 2 <= sizeof(captured) / sizeof(*captured));
    memcpy(captured + captured_count, recording_buffer, sizeof(recording_buffer));
    captured_count += 2;
    *addr = recording_buffer;
    *size = sizeof(recording_buffer);
}
static void feed_capture(unsigned words)
{
    fifo_remaining = words;
    int previous = disable_irq_save();
    while (fifo_remaining) INT_I2SIN();
    restore_irq(previous);
}
static void assert_capture_unchanged(uint32_t *address, size_t size, int keep)
{
    assert(is_recording && pcm_is_recording());
    assert(rec_dma_addr == address && rec_dma_size == size && keep_sample == keep);
    assert(I2SIN_MASK == 4 && I2SIN_CONTROL == ((1 << 5) | (1 << 2)));
    assert(CGU_PERI & CGU_I2SIN_APB_CLOCK_ENABLE);
    assert(CGU_AUDIO == expected_clock && codec_calls == expected_codec_calls);
    assert(frequency_writes == expected_frequency_writes);
    assert(!irq_level);
}
static void assert_captured_samples(void)
{
    for (size_t index = 0; index < captured_count; ++index)
    {
        uint32_t sample = 0x12340000u | (2 * index + 1);
#if CONFIG_CPU == AS3525
        if (audio_channels == 1)
            sample = (uint16_t)(sample << 2) | (sample << 18);
        else
#endif
            sample = (sample << 2) & ~0x00030000u;
        assert(captured[index] == sample);
    }
}
static void transfer_playback(void)
{
    assert(mock_dma_enabled);
    assert(rendered_count + mock_dma_size / 4 <= sizeof(rendered) / sizeof(*rendered));
    memcpy(rendered + rendered_count, mock_dma_buffer, mock_dma_size);
    rendered_count += mock_dma_size / 4;
    mock_dma_enabled = false;
    int previous = disable_irq_save();
    mock_dma_callback();
    restore_irq(previous);
}
static void drain_playback(void)
{
    unsigned frames = 0;
    while (pcm_is_playing())
    {
        assert(++frames < 32);
        transfer_playback();
        feed_capture(4);
    }
    assert(!mock_dma_enabled && !dma_references);
}
static void setup(unsigned rate, int input_source)
{
    builtin_pcm_sink.ops.init();
    builtin_pcm_sink.pending_freq = HW_FREQ_DEFAULT;
    builtin_pcm_sink.configured_freq = (unsigned long)-1;
    pcm_set_frequency(rate | SAMPR_TYPE_REC);
    pcm_apply_settings();
    assert(pcm_get_frequency() == rate * 2);
    audio_input_mux(input_source, SRCF_RECORDING);
    audio_set_output_source(input_source);
    pcm_rec_dma_init();
    pcm_record_data(more_recording, NULL, recording_buffer, sizeof(recording_buffer));
    assert(is_recording && pcm_is_recording() && I2SIN_MASK == 4);
    assert((I2SOUT_CONTROL & (1 << 5)) ==
           (CONFIG_CPU == AS3525 && audio_channels == 1 ? 0 : 1 << 5));
    expected_clock = CGU_AUDIO;
    expected_codec_calls = codec_calls;
    expected_frequency_writes = frequency_writes;
    mixer_channel_set_amplitude(PCM_MIXER_CHAN_VOICE, MIX_AMP_UNITY);
    feed_capture(1);
}
int main(int argc, char **argv)
{
    assert(argc == 3);
    unsigned rate;
    assert(sscanf(argv[2], "%u", &rate) == 1);
    int input_source = !strcmp(argv[1], "fm") ? AUDIO_SRC_FMRADIO : AUDIO_SRC_MIC;
    setup(rate, input_source);
    static uint32_t speech[MIX_FRAME_SAMPLES * 4 + 7];
    for (size_t index = 0; index < sizeof(speech) / 4; ++index)
        speech[index] = 0x01230123;
    mixer_channel_play_data(PCM_MIXER_CHAN_VOICE, NULL, NULL, 0);
    assert(!pcm_is_playing() && !mock_dma_enabled);
    mixer_channel_play_data(PCM_MIXER_CHAN_BEEP, NULL, speech, sizeof(speech));
    assert(!pcm_is_playing() && !mock_dma_enabled);
    mixer_channel_stop(PCM_MIXER_CHAN_BEEP);
    size_t speech_size = !strcmp(argv[1], "short") ? 28 : sizeof(speech);
    uint32_t *capture_address = rec_dma_addr;
    size_t capture_size = rec_dma_size;
    int capture_keep = keep_sample;
    mixer_channel_play_data(PCM_MIXER_CHAN_VOICE, NULL, speech, speech_size);
    assert_capture_unchanged(capture_address, capture_size, capture_keep);
#ifndef HAVE_PCM_RECORDING_VOICE
    assert(!pcm_is_playing() && !mock_dma_enabled && !dma_starts);
    assert((I2SOUT_CONTROL & (1 << 5)) ==
           (CONFIG_CPU == AS3525 && audio_channels == 1 ? 0 : 1 << 5));
    feed_capture(7);
    assert(captured_count == 4);
#else
    assert(pcm_is_playing() && mock_dma_enabled && dma_references == 1);
    assert(!(I2SOUT_CONTROL & (1 << 5)));
    assert(audio_output_source == input_source);
    if (!strcmp(argv[1], "natural") || !strcmp(argv[1], "short") || !strcmp(argv[1], "fm"))
    {
        drain_playback();
        for (size_t index = 0; index < speech_size / 4; ++index)
            assert(rendered[index] == speech[index]);
        for (size_t index = speech_size / 4; index < rendered_count; ++index)
            assert(rendered[index] == 0);
    }
    else if (!strcmp(argv[1], "pause"))
    {
        mixer_channel_play_pause(PCM_MIXER_CHAN_VOICE, false);
        drain_playback();
        assert(I2SOUT_CONTROL & (1 << 5));
        mixer_channel_play_pause(PCM_MIXER_CHAN_VOICE, true);
        assert(pcm_is_playing() && !(I2SOUT_CONTROL & (1 << 5)));
        drain_playback();
    }
    else if (!strcmp(argv[1], "source"))
    {
        audio_set_output_source(AUDIO_SRC_FMRADIO);
        assert(!(I2SOUT_CONTROL & (1 << 5)));
        drain_playback();
        assert(audio_output_source == AUDIO_SRC_FMRADIO);
        assert(I2SOUT_CONTROL & (1 << 5));
        audio_set_output_source(AUDIO_SRC_PLAYBACK);
        mixer_channel_play_data(PCM_MIXER_CHAN_VOICE, NULL, speech, sizeof(speech));
        drain_playback();
        assert(!(I2SOUT_CONTROL & (1 << 5)));
        audio_set_output_source(AUDIO_SRC_MIC);
    }
    else if (!strcmp(argv[1], "locked"))
    {
        pcm_play_lock();
        pcm_play_lock();
        transfer_playback();
        assert(play_callback_pending && !mock_dma_enabled);
        feed_capture(7);
        pcm_play_unlock();
        assert(play_callback_pending && !mock_dma_enabled);
        pcm_play_unlock();
        assert(!play_callback_pending && mock_dma_enabled);
        drain_playback();
    }
    else if (!strcmp(argv[1], "stop"))
    {
        pcm_play_stop();
        assert(I2SOUT_CONTROL & (1 << 5));
        mixer_channel_stop(PCM_MIXER_CHAN_VOICE);
        for (unsigned repeat = 0; repeat < 20; ++repeat)
        {
            mixer_channel_play_data(PCM_MIXER_CHAN_VOICE, NULL, speech, sizeof(speech));
            assert(!(I2SOUT_CONTROL & (1 << 5)));
            feed_capture(4);
            mixer_reset();
            assert(I2SOUT_CONTROL & (1 << 5));
            assert_capture_unchanged(rec_dma_addr, rec_dma_size, keep_sample);
        }
    }
    else if (!strcmp(argv[1], "cancel"))
    {
        mixer_channel_stop(PCM_MIXER_CHAN_VOICE);
        drain_playback();
    }
    else if (!strcmp(argv[1], "error"))
    {
        const void *address = NULL;
        size_t size = 0;
        int previous = disable_irq_save();
        assert(!pcm_play_dma_complete_callback(PCM_DMAST_ERR, &address, &size));
        assert(irq_level == 1);
        restore_irq(previous);
        mixer_channel_stop(PCM_MIXER_CHAN_VOICE);
    }
    else if (!strcmp(argv[1], "locked-stop"))
    {
        pcm_play_lock();
        transfer_playback();
        assert(play_callback_pending);
        pcm_play_stop();
        assert(!play_callback_pending && !is_playing);
        pcm_play_unlock();
        assert(!mock_dma_enabled);
        mixer_channel_stop(PCM_MIXER_CHAN_VOICE);
    }
    else
        assert(!"Unknown scenario");
    assert(!pcm_is_playing() && !mock_dma_enabled && !dma_references);
    assert(I2SOUT_CONTROL & (1 << 5));
    assert((I2SOUT_CONTROL & ~(1 << 5)) == ((1 << 6) | (1 << 3)));
    assert_capture_unchanged(rec_dma_addr, rec_dma_size, keep_sample);
    feed_capture(7);
    assert(captured_count >= 4);
#endif
    assert_captured_samples();
    pcm_stop_recording();
    assert(!is_recording && !pcm_is_recording());
    audio_input_mux(AUDIO_SRC_PLAYBACK, 0);
    audio_set_output_source(AUDIO_SRC_PLAYBACK);
    mixer_channel_play_data(PCM_MIXER_CHAN_VOICE, NULL, speech, sizeof(speech));
    assert(pcm_is_playing() && mock_dma_enabled && !(I2SOUT_CONTROL & (1 << 5)));
    transfer_playback();
    pcm_play_stop();
    assert(!pcm_is_playing() && !mock_dma_enabled && !dma_references);
    puts("PASS: mocked capture survives PCM output; no physical hardware validation");
    return 0;
}
"""


def harness_source():
    mixer = source("firmware/pcm_mixer.c")
    pcm = source("firmware/pcm.c")
    internal = source("firmware/export/pcm-internal.h")
    mixer_header = source("firmware/export/pcm_mixer.h")
    mixer_header = without_includes(mixer_header)
    pcm_state = r"""
static struct pcm_sink *sinks[] = { &builtin_pcm_sink };
static enum pcm_sink_ids cur_sink = PCM_SINK_BUILTIN;
volatile bool pcm_playing, pcm_recording;
volatile pcm_play_callback_type pcm_callback_for_more;
volatile pcm_status_callback_type pcm_play_status_callback, pcm_rec_status_callback;
static volatile pcm_rec_callback_type pcm_callback_more_ready;
static const void *volatile pcm_rec_peak_addr;
static void pcm_wait_for_init(void) {}
"""
    parts = [PREAMBLE, without_includes(source("firmware/export/pcm_sink.h")),
             mixer_header, without_includes(source("firmware/target/arm/as3525/audio-as3525.c")),
             without_includes(source("firmware/target/arm/as3525/pcm-as3525.c")), pcm_state]
    parts.extend(function(internal, name) for name in (
        "pcm_get_more_int", "pcm_call_status_cb", "pcm_play_call_status_cb",
        "pcm_play_dma_status_callback", "pcm_rec_dma_status_callback"))
    parts.extend(function(pcm, name) for name in (
        "pcm_play_dma_start_int", "pcm_play_dma_stop_int", "pcm_play_stop_int",
        "pcm_play_dma_complete_callback", "pcm_play_lock", "pcm_play_unlock",
        "pcm_is_playing", "pcm_is_recording", "pcm_set_frequency", "pcm_get_frequency",
        "pcm_apply_settings", "pcm_play_data", "pcm_play_stop", "pcm_recording_stopped",
        "pcm_record_data", "pcm_stop_recording", "pcm_rec_dma_complete_callback"))
    parts.append(mixer[mixer.index("static unsigned int mix_frame_size"):
                       mixer.index("static inline unsigned int max_idle_frames")])
    parts.append(function(mixer, "max_idle_frames"))
    parts.append(without_includes(source("firmware/asm/pcm-mixer.c")))
    parts.append("static enum pcm_dma_status "
                 "mixer_buffer_callback(enum pcm_dma_status status);")
    parts.extend(function(mixer, name) for name in (
        "mixer_activate_channel", "mixer_deactivate_channel", "channel_stopped",
        "mixer_pcm_callback", "chan_call_buffer_hook", "mixer_buffer_callback",
        "mixer_start_pcm", "mixer_channel_play_data", "mixer_channel_play_pause",
        "mixer_channel_stop", "mixer_channel_set_amplitude", "mixer_reset"))
    parts.append(CHECKS)
    return "\n".join(parts)


@unittest.skipUnless(os.name == "posix", "Run the C harness under WSL/Linux")
class RecordingBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise RuntimeError("A host C compiler is required")
        generated = harness_source()
        WORKSPACE.mkdir(parents=True)
        cls.harness = WORKSPACE / "backend.c"
        cls.harness.write_text(generated, encoding="utf-8")
        (WORKSPACE / "autoconf.h").write_text("#define MEMORYSIZE 8\n", encoding="utf-8")
        inputs = ("firmware/export/config.h", "firmware/export/pcm_mixer.h",
                  "firmware/export/pcm-internal.h", "firmware/export/pcm_sink.h",
                  "firmware/pcm.c", "firmware/pcm_mixer.c", "firmware/asm/pcm-mixer.c",
                  "firmware/target/arm/as3525/audio-as3525.c",
                  "firmware/target/arm/as3525/pcm-as3525.c")
        (WORKSPACE / "sources.json").write_text(json.dumps({
            "method": "Extracted production C; generic mixer arithmetic; ASan/UBSan; register mocks",
            "hardware_validated": False,
            "sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in inputs},
            "harness_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        }, indent=2) + "\n", encoding="utf-8")
        cls.executables = {}
        cls.evidence = []

    @classmethod
    def tearDownClass(cls):
        (WORKSPACE / "results.json").write_text(json.dumps(cls.evidence, indent=2) + "\n",
                                                encoding="utf-8")

    def run_command(self, arguments, label):
        result = subprocess.run(arguments, text=True, capture_output=True, timeout=60,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
                                         UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
        output = result.stdout
        if label.startswith("config-"):
            output = "\n".join(line for line in output.splitlines() if any(
                word in line for word in ("HAVE_PCM_RECORDING_VOICE", "CONFIG_CPU", "CONFIG_PLATFORM")))
        self.evidence.append(dict(label=label, command=arguments, returncode=result.returncode,
                                  stdout=output, stderr=result.stderr))
        self.assertEqual(result.returncode, 0, result.stderr + output[-2000:])
        return result

    def executable(self, variant):
        if variant not in self.executables:
            executable = WORKSPACE / variant
            arguments = self.compiler + ["-std=gnu99", "-O1", "-g", "-Wall", "-Wextra",
                "-Werror", "-Wno-unused-function", "-Wno-unused-variable", "-fno-pie", "-no-pie",
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            arguments += ["-DCONFIG_CPU=" + ("AS3525" if variant == "v1-off" else "AS3525v2")]
            if variant == "v2-on":
                arguments += ["-DHAVE_PCM_RECORDING_VOICE"]
            self.run_command(arguments + [str(self.harness), "-o", str(executable)], variant + "-compile")
            self.executables[variant] = executable
        return self.executables[variant]

    def test_recording_voice_output_and_capture(self):
        for variant in ("v2-on", "v2-off", "v1-off"):
            executable = self.executable(variant)
            for scenario in ("natural", "short", "fm", "stop", "cancel", "pause", "source",
                             "locked", "error", "locked-stop"):
                for rate in (8000, 16000, 44100, 48000):
                    with self.subTest(variant=variant, scenario=scenario, rate=rate):
                        self.run_command([str(executable), scenario, str(rate)],
                                         f"{variant}-{scenario}-{rate}")

    def test_capability_is_target_and_build_specific(self):
        for target in ("SANSA_CLIPPLUS", "SANSA_CLIPZIP", "SANSA_CLIP", "SANSA_FUZEV2"):
            for mode in (None, "BOOTLOADER", "SIMULATOR", "__PCTOOL__"):
                with self.subTest(target=target, mode=mode):
                    arguments = self.compiler + ["-E", "-dM", "-x", "c", "-I",
                        str(ROOT / "firmware/export"), "-I", str(WORKSPACE), "-D" + target]
                    if mode:
                        arguments += ["-D" + mode]
                    result = self.run_command(arguments + ["-include", str(ROOT / "firmware/export/config.h"),
                                                           os.devnull], f"config-{target}-{mode}")
                    enabled = "#define HAVE_PCM_RECORDING_VOICE" in result.stdout
                    self.assertEqual(enabled, target != "SANSA_CLIP" and mode is None)


if __name__ == "__main__":
    print(f"Extracted C / register mock evidence: {WORKSPACE}", flush=True)
    unittest.main(verbosity=2)
