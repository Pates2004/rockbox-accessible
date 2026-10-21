"""Execute the independent button recognizer with bounded, virtual time."""

import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root

ROOT = Path(__file__).resolve().parents[2]


class AccessibilityButtonsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            raise unittest.SkipTest("C compiler unavailable; run under WSL")
        cls.workspace = project_materials_root(ROOT) / "r1-accessibility-buttons" / datetime.now(
            timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace.mkdir(parents=True, exist_ok=False)
        wrapper = cls.workspace / "buttons.c"
        wrapper.write_text(r'''
#include "accessibility_buttons.h"
static struct accessibility_buttons state;
int probe_init(unsigned int hold) { return accessibility_buttons_init(&state, hold); }
void probe_reset(void) { accessibility_buttons_reset(&state); }
int probe_pending(void) { return accessibility_buttons_pending(&state); }
unsigned int probe_event(unsigned int type, unsigned int button, unsigned int clicks, uint32_t time)
{
    struct accessibility_button_event event = accessibility_buttons_process(&state, type, button, clicks, time);
    return event.consumed | (event.recognized << 1) | (event.repeat << 2) |
        ((unsigned int)event.button << 4) | ((unsigned int)event.slot << 8);
}
int probe_null(void)
{
    accessibility_buttons_reset(0);
    struct accessibility_button_event event = accessibility_buttons_process(0,
        ACCESSIBILITY_BUTTON_POLL, 0, 1, 0);
    return accessibility_buttons_init(0, 700) || accessibility_buttons_pending(0) || event.recognized;
}
''', encoding="utf-8")
        library = cls.workspace / ("buttons.dll" if os.name == "nt" else "buttons.so")
        paths = [ROOT / "apps/accessibility_buttons.c", ROOT / "apps/accessibility_buttons.h"]
        hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        command = compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                              "-I", str(ROOT / "apps"), str(wrapper), str(paths[0]), "-o", str(library)]
        if os.environ.get("ACCESSIBILITY_BUTTONS_SANITIZE"):
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        result = subprocess.run(command, capture_output=True, text=True)
        (cls.workspace / "compile.log").write_text(shlex.join(command) + "\n" + result.stdout + result.stderr,
                                                  encoding="utf-8")
        (cls.workspace / "provenance.json").write_text(json.dumps({"source_root": str(ROOT),
            "source_sha256": hashes, "command": command, "returncode": result.returncode,
            "scope": "real independent C recognizer; virtual clock; not hardware acceptance"}, indent=2),
            encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.library = ctypes.CDLL(str(library))
        cls.library.probe_event.argtypes = [ctypes.c_uint] * 3 + [ctypes.c_uint32]
        cls.library.probe_event.restype = ctypes.c_uint

    def setUp(self):
        self.assertEqual(self.library.probe_init(700), 1)

    def event(self, kind, button=0, clicks=3, time=0):
        value = self.library.probe_event(kind, button, clicks, time)
        return bool(value & 1), bool(value & 2), bool(value & 4), (value >> 4) & 15, value >> 8

    def click(self, start, button=0, clicks=3):
        pressed = self.event(0, button, clicks, start)
        released = self.event(1, button, clicks, start + 50)
        return pressed, released

    def test_null_and_hold_bounds(self):
        self.assertEqual(self.library.probe_null(), 0)
        for value in [0, 299, 2001, 0xffffffff]:
            self.assertEqual(self.library.probe_init(value), 0)
        for value in [300, 700, 2000]:
            self.assertEqual(self.library.probe_init(value), 1)

    def test_each_real_button_single_on_release_without_multiclick_delay(self):
        for button in range(5):
            self.setUp()
            self.assertEqual(self.click(0, button, 1), ((True, False, False, 0, 0),
                                                      (True, True, False, button, 0)))
            self.assertFalse(self.library.probe_pending())
            self.assertFalse(self.event(3, time=500)[1])

    def test_single_waits_for_double_triple_window(self):
        self.click(0)
        self.assertTrue(self.library.probe_pending())
        self.assertFalse(self.event(3, time=349)[1])
        self.assertEqual(self.event(3, time=350), (True, True, False, 0, 0))
        self.assertFalse(self.event(3, time=700)[1])

    def test_double_and_triple_emit_once_without_intermediate_single(self):
        self.click(0)
        self.assertFalse(self.click(100)[1][1])
        self.assertEqual(self.event(3, time=450), (True, True, False, 0, 1))
        self.setUp()
        self.click(0)
        self.click(100)
        self.assertEqual(self.click(200)[1], (True, True, False, 0, 2))
        self.assertFalse(self.event(3, time=900)[1])

    def test_double_without_triple_emits_immediately_on_second_release(self):
        self.click(0, clicks=2)
        self.assertEqual(self.click(100, clicks=2)[1], (True, True, False, 0, 1))

    def test_hold_by_poll_repeat_and_release_at_exact_threshold(self):
        for finish in [2, 3, 1]:
            self.setUp()
            self.event(0)
            self.assertFalse(self.event(3, time=699)[1])
            self.assertEqual(self.event(finish, time=700), (True, True, False, 0, 3))
            if finish != 1:
                self.assertFalse(self.event(3, time=800)[1])
                self.assertEqual(self.event(2, time=900), (True, True, True, 0, 3))
                self.assertFalse(self.event(1, time=950)[1])
            self.assertFalse(self.event(3, time=2000)[1])

    def test_double_click_followed_by_hold_cancels_pending_clicks(self):
        self.click(0)
        self.click(100)
        self.event(0, time=200)
        self.assertEqual(self.event(3, time=900), (True, True, False, 0, 3))
        self.event(1, time=950)
        self.assertFalse(self.event(3, time=1300)[1])

    def test_pending_clicks_wait_for_the_current_contact_before_hold(self):
        for clicks in (1, 2):
            with self.subTest(clicks=clicks):
                self.setUp()
                for index in range(clicks):
                    self.click(index * 100)
                pressed_at = clicks * 100
                self.event(0, time=pressed_at)
                for now in range(pressed_at + 50, pressed_at + 700, 50):
                    self.assertFalse(self.event(3, time=now)[1], now)
                self.assertEqual(self.event(3, time=pressed_at + 700),
                                 (True, True, False, 0, 3))
                self.assertFalse(self.event(1, time=pressed_at + 750)[1])
                self.assertFalse(self.event(3, time=pressed_at + 1100)[1])

    def test_slow_second_contact_within_hold_limit_still_forms_one_double_click(self):
        self.click(0)
        self.event(0, time=100)
        for now in range(150, 700, 50):
            self.assertFalse(self.event(3, time=now)[1], now)
        self.assertFalse(self.event(1, time=700)[1])
        self.assertEqual(self.event(3, time=1000), (True, True, False, 0, 1))
        self.assertFalse(self.event(3, time=1400)[1])

    def test_chord_cancel_consumes_releases_and_repeat_until_new_press(self):
        self.event(0)
        self.event(4, time=50)
        self.assertFalse(self.library.probe_pending())
        self.assertFalse(self.event(1, time=60)[1])
        self.assertFalse(self.event(2, time=800)[1])
        self.assertFalse(self.event(3, time=900)[1])
        self.assertEqual(self.click(1000, 2, 1)[1], (True, True, False, 2, 0))

    def test_reset_cancels_contact_and_pending_multiclick(self):
        self.click(0)
        self.library.probe_reset()
        self.assertFalse(self.event(3, time=1000)[1])
        self.event(0, time=1100)
        self.library.probe_reset()
        self.assertFalse(self.event(1, time=1200)[1])

    def test_different_button_flushes_old_pending_and_tracks_new_button(self):
        self.click(0, 1)
        self.assertEqual(self.event(0, 3, 3, 100), (True, True, False, 1, 0))
        self.assertFalse(self.event(1, 3, 3, 150)[1])
        self.assertEqual(self.event(3, time=450), (True, True, False, 3, 0))

    def test_boundary_new_press_does_not_extend_expired_sequence(self):
        self.click(0)
        self.assertEqual(self.event(0, 0, 3, 350), (True, True, False, 0, 0))
        self.event(1, time=400)
        self.assertEqual(self.event(3, time=700), (True, True, False, 0, 0))

    def test_wraparound_and_clock_regression_do_not_spuriously_hold(self):
        self.event(0, time=0xfffffff0)
        self.assertFalse(self.event(3, time=0x20)[1])
        self.assertEqual(self.event(3, time=0x2ac), (True, True, False, 0, 3))
        self.setUp()
        self.event(0, time=1000)
        self.assertFalse(self.event(3, time=999)[1])
        self.assertFalse(self.event(1, time=1100)[1])
        self.assertFalse(self.event(3, time=2000)[1])

    def test_invalid_input_cancels_safely(self):
        for kind, button, clicks in [(9, 0, 3), (0, 5, 3), (0, 255, 3), (0, 0, 0), (0, 0, 4)]:
            self.setUp()
            self.click(0)
            self.assertFalse(self.event(kind, button, clicks, 100)[1])
            self.assertFalse(self.event(3, time=1000)[1])


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if hasattr(AccessibilityButtonsTests, "workspace"):
        (AccessibilityButtonsTests.workspace / "result.json").write_text(json.dumps({
            "tests_run": result.testsRun, "passed": result.wasSuccessful(),
            "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors],
            "sanitizer": bool(os.environ.get("ACCESSIBILITY_BUTTONS_SANITIZE")),
            "host_os": os.name, "platform": sys.platform}, indent=2), encoding="utf-8")
    sys.exit(not result.wasSuccessful())
