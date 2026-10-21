"""Exercise real keyclick routing and beep generation without opening audio."""

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]


def without_includes(source):
    return re.sub(r"^\s*#include[^\n]*", "", source, flags=re.MULTILINE)


def definition(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    position = opening + 1
    while depth:
        depth += (source[position] == "{") - (source[position] == "}")
        position += 1
    return source[start:position] + "\n"


PREAMBLE = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define HAVE_TOUCHSCREEN
#define HAVE_ESPEAK
#define HIBY_R1
#define BUTTON_NONE 0
#define BUTTON_REL 0x10000
#define BUTTON_REPEAT 0x20000
#define BUTTON_TOUCHSCREEN 0x100
#define BUTTON_MULTIMEDIA 0x40000
#define SYS_EVENT 0x80000
#define ACTION_NONE 0
#define ACTION_TOUCHSCREEN 999
#define ACTION_UNKNOWN 1000
#define ACTION_WPS_STOPSEEK 1001
#define FORCE_INLINE inline
#define IBSS_ATTR
#define PLAY_SAMPR_MAX 48000
#define PCM_MIXER_CHAN_BEEP 1
#define MIX_AMP_UNITY 1
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define fp_div(numerator, denominator, fraction) \
    ((uint32_t)(((uint64_t)(numerator) << (fraction)) / (denominator)))
typedef bool (*keyclick_callback)(int action, void *data);
static struct { int keyclick, beep; bool keyclick_repeats; } global_settings;
static unsigned int sources;
static int empty_pitch;
static bool empty_sound = true;
static unsigned char captured[4096];
static size_t captured_size;
struct mixer_play_cbs { void (*get_more)(const void **start, size_t *size); };
static unsigned int mixer_get_frequency(void) { return PLAY_SAMPR_MAX; }
static void mixer_channel_stop(int channel) { (void)channel; captured_size = 0; }
static void mixer_channel_set_amplitude(int channel, unsigned int amplitude)
{ (void)channel; (void)amplitude; }
static void mixer_channel_play_data(int channel, const struct mixer_play_cbs *callbacks,
                                    const void *start, size_t size)
{
    (void)channel;
    if (size > sizeof(captured)) abort();
    memcpy(captured, start, size);
    captured_size = size;
    if (callbacks->get_more) abort();
}
static unsigned int accessibility_keyclick_sources(void) { return sources; }
static bool accessibility_enabled(void) { return true; }
static int accessibility_keyclick_empty_pitch(void) { return empty_pitch; }
static bool accessibility_empty_sound_enabled(void) { return empty_sound; }
static void get_action_statuscode(int *button) { *button = BUTTON_NONE; }
"""

MAIN = r"""
int main(int argc, char **argv)
{
    if (argc != 6 && argc != 7) return 2;
    sources = (unsigned int)atoi(argv[1]);
    bool occupied = atoi(argv[2]) != 0;
    empty_pitch = atoi(argv[3]);
    bool single_tap = atoi(argv[4]) != 0;
    global_settings.keyclick = atoi(argv[5]);
    empty_sound = argc == 6 || atoi(argv[6]) != 0;
    keyclick_click_touch_target(occupied, single_tap);
    return fwrite(captured, 1, captured_size, stdout) == captured_size ? 0 : 3;
}
"""


class KeyclickPcmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            raise unittest.SkipTest("C compiler unavailable; run compiled tests under WSL")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = project_materials_root(ROOT) / "r1-empty-radio-20261017" / "empty-feedback" / "keyclick-pcm" / stamp
        cls.workspace.mkdir(parents=True, exist_ok=False)
        paths = ("apps/misc.c", "apps/misc.h", "apps/settings.h", "apps/beep.c", "firmware/asm/beep.c")
        cls.inputs = {path: (ROOT / path).read_bytes() for path in paths}
        sources = {path: value.decode("utf-8") for path, value in cls.inputs.items()}
        cls.duration = int(re.search(r"#define KEYCLICK_DURATION\s+(\d+)", sources["apps/settings.h"])[1])
        enums = definition(sources["apps/misc.h"], "enum system_sound") + ";\n"
        enums += definition(sources["apps/misc.h"], "enum keyclick_source") + ";\n"
        source = sources["apps/misc.c"]
        begin = source.index("static keyclick_callback keyclick_current_callback")
        end = source.index("/* Return the ReplayGain mode", begin)
        harness = PREAMBLE + enums + f"\n#define KEYCLICK_DURATION {cls.duration}\n"
        harness += without_includes(sources["firmware/asm/beep.c"])
        harness += without_includes(sources["apps/beep.c"])
        harness += definition(source, "void system_sound_play(") + source[begin:end] + MAIN
        harness_path = cls.workspace / "pcm.c"
        harness_path.write_text(harness, encoding="utf-8")
        cls.executable = cls.workspace / ("pcm.exe" if os.name == "nt" else "pcm")
        command = compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                              "-fno-sanitize-recover=all", str(harness_path), "-o", str(cls.executable)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (cls.workspace / "compile.log").write_text(shlex.join(command) + "\n" + result.stdout + result.stderr,
                                                  encoding="utf-8")
        (cls.workspace / "provenance.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_sha256": {path: hashlib.sha256(value).hexdigest()
                for path, value in cls.inputs.items()}, "compile_returncode": result.returncode,
            "harness_sha256": hashlib.sha256(harness.encode()).hexdigest(),
            "scope": "real misc routing, system sound table, beep PCM generation and generic sample loop; mocked mixer destination, no host audio",
        }, indent=2), encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def pcm(self, mask=7, occupied=False, pitch=-4, single_tap=False, strength=2, empty_sound=True):
        result = subprocess.run([str(self.executable), str(mask), str(int(occupied)), str(pitch),
                                 str(int(single_tap)), str(strength), str(int(empty_sound))],
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def assert_wave(self, pcm, frequency, strength):
        frames = (48000 // 1000) * self.duration
        self.assertEqual(len(pcm), frames * 4)
        samples = struct.unpack("=" + "h" * frames * 2, pcm)
        step = (frequency << 32) // 48000
        for index in range(frames):
            phase = (index * step) & 0xFFFFFFFF
            expected = 2500 * strength * (-1 if phase > 0x7FFFFFFF else 1)
            self.assertEqual(samples[index * 2:index * 2 + 2], (expected, expected))

    def test_default_empty_pitch_changes_actual_pcm_and_keeps_duration_and_strength(self):
        ordinary = self.pcm(occupied=True)
        empty = self.pcm()
        self.assertNotEqual(ordinary, empty)
        self.assert_wave(ordinary, 4000, 2)
        self.assert_wave(empty, 3175, 2)
        (self.workspace / "occupied.pcm").write_bytes(ordinary)
        (self.workspace / "empty-minus-four.pcm").write_bytes(empty)

    def test_each_semitone_and_strength_matches_real_generated_samples(self):
        for pitch in range(-12, 13):
            for strength in (1, 2, 3):
                with self.subTest(pitch=pitch, strength=strength):
                    frequency = math.floor(4000 * 2 ** (pitch / 12) + 0.5)
                    self.assert_wave(self.pcm(pitch=pitch, strength=strength), frequency, strength)

    def test_all_eight_source_masks_emit_at_most_one_pcm_click(self):
        for mask in range(8):
            for single_tap in (False, True):
                with self.subTest(mask=mask, single_tap=single_tap):
                    pcm = self.pcm(mask=mask, single_tap=single_tap)
                    if mask & 4:
                        self.assert_wave(pcm, 3175, 2)
                    else:
                        self.assertEqual(pcm, b"")
                    occupied = self.pcm(mask=mask, occupied=True, single_tap=single_tap)
                    if mask & (6 if single_tap else 4):
                        self.assert_wave(occupied, 4000, 2)
                    else:
                        self.assertEqual(occupied, b"")

    def test_disabled_pitch_restores_normal_pcm_and_strength_off_is_silent(self):
        self.assertEqual(self.pcm(pitch=0), self.pcm(occupied=True))
        self.assertEqual(self.pcm(strength=0), b"")

    def test_speech_only_suppresses_empty_pcm_but_never_occupied_pcm(self):
        for mask in range(8):
            for single_tap in (False, True):
                for strength in range(4):
                    with self.subTest(mask=mask, single_tap=single_tap, strength=strength):
                        self.assertEqual(self.pcm(mask=mask, single_tap=single_tap,
                                                 strength=strength, empty_sound=False), b"")
                        self.assertEqual(self.pcm(mask=mask, occupied=True, single_tap=single_tap,
                                                 strength=strength, empty_sound=False),
                                         self.pcm(mask=mask, occupied=True, single_tap=single_tap,
                                                  strength=strength, empty_sound=True))

    @classmethod
    def tearDownClass(cls):
        changed = [path for path, value in cls.inputs.items() if (ROOT / path).read_bytes() != value]
        if changed:
            raise AssertionError("PCM inputs changed during bounded tests: " + ", ".join(changed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
