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
#include <assert.h>
#define LOGFQUEUE(...)
#define SRCF_RECORDING 8
enum { Q_AUDIO_INIT_RECORDING = 1, Q_AUDIO_CLOSE_RECORDING,
       Q_AUDIO_RECORDING_OPTIONS };
struct audio_recording_options { int rec_source; unsigned rec_source_flags; };
static int events[16];
static int event_count;
static intptr_t dispatched_data;
static unsigned source_flags;
static void record_event(int event) { assert(event_count < 16); events[event_count++] = event; }
static void voice_stop(void) { record_event(10); }
static void mixer_reset(void) { record_event(12); }
static void talk_force_shutup(void) { record_event(11); }
static void rec_set_source(int source, unsigned flags)
{ record_event(source + 20); source_flags = flags; }
static intptr_t audio_queue_send(int message, intptr_t data)
{ record_event(message); dispatched_data = data; return 0; }
"""
SUFFIX = r"""
void test_reset(void) { event_count = 0; dispatched_data = 0; source_flags = 0; }
int test_count(void) { return event_count; }
int test_event(int index) { assert(index < event_count); return events[index]; }
intptr_t test_data(void) { return dispatched_data; }
unsigned test_flags(void) { return source_flags; }
void test_options(void)
{
    static struct audio_recording_options options = { .rec_source = 2, .rec_source_flags = 16 };
    rec_set_recording_options(&options);
    assert(dispatched_data == (intptr_t)&options);
}
"""


class RecordingLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = _project_materials_root(ROOT) / "tts-recording-lifecycle-tests" / stamp
        cls.workspace.mkdir(parents=True)
        backend = (ROOT / "apps/recorder/pcm_record.c").read_text(encoding="utf-8")
        screen = (ROOT / "apps/recorder/recording.c").read_text(encoding="utf-8")
        functions = "\n".join(extract_block(backend, signature) for signature in (
            "void audio_init_recording(", "void audio_close_recording(",
            "void audio_set_recording_options("))
        functions += extract_block(screen, "void rec_set_recording_options(")
        cls.libraries = {}
        for name, defines in (
                ("duplex", ["HAVE_ESPEAK", "HAVE_PCM_RECORDING_VOICE", "HAVE_RECORDING_TTS"]),
                ("legacy", []), ("nonduplex", ["HAVE_ESPEAK"]),
                ("simulator", ["HAVE_ESPEAK", "HAVE_RECORDING_TTS"])):
            source = cls.workspace / (name + ".c")
            source.write_text(PREFIX + functions + SUFFIX, encoding="utf-8")
            library = cls.workspace / (name + ".so")
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-function", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                *["-D" + define for define in defines], str(source), "-o", str(library)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (cls.workspace / (name + ".log")).write_text(
                shlex.join(command) + "\n" + compiled.stdout + compiled.stderr, encoding="utf-8")
            if compiled.returncode:
                raise RuntimeError(compiled.stderr)
            cls.libraries[name] = ctypes.CDLL(str(library))

    def events(self, library):
        return [library.test_event(index) for index in range(library.test_count())]

    def test_native_backend_uses_the_public_mixer_quiesce_api(self):
        backend = (ROOT / "apps/recorder/pcm_record.c").read_text(encoding="utf-8")
        header = (ROOT / "firmware/export/pcm_mixer.h").read_text(encoding="utf-8")
        self.assertIn('#include "pcm_mixer.h"', backend)
        self.assertIn("void mixer_reset(void);", header)
        self.assertNotIn('#include "pcm-internal.h"', backend)
        self.assertNotIn("pcm_play_stop();", backend)

    def test_duplex_init_and_close_quiesce_voice_before_clock_dispatch(self):
        library = self.libraries["duplex"]
        for operation, message, data in (("audio_init_recording", 1, 1),
                                         ("audio_close_recording", 2, 0)):
            with self.subTest(operation=operation):
                library.test_reset()
                getattr(library, operation)()
                self.assertEqual(self.events(library), [10, 12, message])
                self.assertEqual(library.test_data(), data)

    def test_duplex_options_quiesce_before_input_and_hardware_clock_changes(self):
        library = self.libraries["duplex"]
        library.test_reset()
        library.test_options()
        self.assertEqual(self.events(library), [11, 22, 10, 12, 3])
        self.assertEqual(library.test_flags(), 16 | 8)

    def test_other_native_backends_keep_existing_voice_policy(self):
        for name in ("legacy", "nonduplex"):
            library = self.libraries[name]
            with self.subTest(backend=name):
                library.test_reset()
                library.audio_init_recording()
                library.audio_close_recording()
                library.test_options()
                self.assertEqual(self.events(library), [1, 2, 22, 3])

    def test_simulator_keeps_speaking_ui_without_enabling_capture(self):
        library = self.libraries["simulator"]
        library.test_reset()
        library.test_options()
        self.assertEqual(self.events(library), [11, 22, 3])


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RecordingLifecycleTests))
    (RecordingLifecycleTests.workspace / "report.json").write_text(json.dumps({
        "tests": result.testsRun, "passed": result.wasSuccessful()}, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
