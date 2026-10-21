"""Exercise real manager forwarding, typing queue and deferred keyboard feedback."""

import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest

import test_accessibility_settings as manager
from test_keyclick_pcm import definition


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = r"""
struct keyboard_parameters { int unused; };
struct screen { int unused; };
struct edit_state { bool redraw; };
static int bridge_target;
static struct keyboard_parameters bridge_keyboard;
static struct screen bridge_screen;
static struct edit_state bridge_state;
static int kbd_typing_hit(struct keyboard_parameters *parameters, struct screen *screen, int position_x, int position_y)
{ (void)parameters; (void)screen; (void)position_x; (void)position_y; return bridge_target; }
static void kbd_typing_focus(struct keyboard_parameters *parameters, int target)
{ (void)parameters; (void)target; }
static void kbd_spellchar(unsigned short character) { (void)character; }
static unsigned short get_kbd_ch(struct keyboard_parameters *parameters, int column, int row)
{ (void)parameters; (void)column; (void)row; return 'k'; }
static void kbd_speak_typing_target(int target) { (void)target; }
"""
WRAPPERS = r"""
void bridge_begin(void)
{
    input_reset();
    session_active = typing_active = true;
    selected_mode = ACCESSIBILITY_TYPING_LIFT;
    typing_mode = ACCESSIBILITY_TYPING_LIFT;
    accessibility_typing_cancel_touch();
}
int bridge_consume(int target)
{
    bridge_target = target;
    return keyboard_accessible_touch(&bridge_keyboard, &bridge_screen, &bridge_state);
}
"""


class KeyclickTypingBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = type("ManagerBridgeFixture", (), {})
        manager.AccessibilitySettingsTests.setUpClass.__func__(fixture)
        cls.workspace = fixture.workspace / "deferred-typing"
        cls.workspace.mkdir(exist_ok=False)
        cls.constants = fixture.constants
        harness = (fixture.workspace / "manager.c").read_text(encoding="utf-8")
        harness = harness.replace(definition(harness, "static void accessibility_typing_cancel_touch("),
                                  "void accessibility_typing_cancel_touch(void);\n", 1)
        harness = harness.replace(definition(harness, "static int accessibility_typing_handle_touch("),
                                  "int accessibility_typing_handle_touch(const struct touchevent *event, int context);\n", 1)
        typing = (ROOT / "apps/accessibility_typing.c").read_text(encoding="utf-8")
        header = (ROOT / "apps/accessibility_typing.h").read_text(encoding="utf-8")
        keyboard = (ROOT / "apps/recorder/keyboard.c").read_text(encoding="utf-8")
        harness += "\n#undef ACCESSIBILITY_TYPING_ARROWS\n"
        action_header = (ROOT / "apps/action.h").read_text(encoding="utf-8")
        harness += re.search(r"^#define ALLOW_SOFTLOCK[^\n]*", action_header, re.MULTILINE)[0] + "\n"
        for signature in ("enum accessibility_typing_mode", "enum accessibility_typing_input",
                          "enum accessibility_typing_target", "struct accessibility_typing_result"):
            harness += definition(header, signature) + ";\n"
        harness += "static enum accessibility_typing_mode selected_mode;\n"
        start = typing.index("static bool session_active;")
        end = typing.index("static bool typing_load(", start)
        harness += typing[start:end]
        harness += "\n".join(re.findall(r"^#define TYPING_(?:EXPLORE_MS|TAP_MS|DOUBLE_MS|TAP_SLOP)\b[^\n]*",
                                        typing, re.MULTILINE)) + "\n"
        for signature in ("void accessibility_typing_cancel_touch(", "int accessibility_typing_handle_touch(",
                          "bool accessibility_typing_take_touch(", "static bool typing_valid_target(",
                          "static bool typing_moved(", "struct accessibility_typing_result accessibility_typing_process("):
            harness += definition(typing, signature)
        bridge = BRIDGE.replace("struct keyboard_parameters { int unused; };",
                                "struct keyboard_parameters { int x, y; };")
        consumer = re.search(r"^static int keyboard_accessible_touch\([^;{}]*\)\s*\{", keyboard, re.MULTILINE)
        if consumer is None:
            raise AssertionError("Expected the real keyboard deferred consumer definition")
        harness += bridge + definition(keyboard[consumer.start():], "static int keyboard_accessible_touch(") + WRAPPERS
        cls.inputs = {path: (ROOT / path).read_bytes() for path in
                      ("apps/accessibility.c", "apps/accessibility_typing.c", "apps/accessibility_typing.h",
                       "apps/recorder/keyboard.c")}
        cls.library = cls.compile("bridge", harness)
        original = "return accessibility_typing_handle_touch(ev, context);"
        if harness.count(original) != 1:
            raise AssertionError("Expected exactly one manager forwarding point")
        mutant = harness.replace(original, "int result = accessibility_typing_handle_touch(ev, context);\n"
                                 "        feedback_pending = false;\n        return result;", 1)
        cls.mutant = cls.compile("cleared-before-consumption", mutant)
        (cls.workspace / "provenance.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_sha256": {path: hashlib.sha256(value).hexdigest()
                for path, value in cls.inputs.items()},
            "scope": "real full manager, real typing queue/process and real keyboard consumer; mocked keyboard hit identity and speech; deferred consumption and mutation regression",
        }, indent=2), encoding="utf-8")

    @classmethod
    def compile(cls, name, harness):
        source = cls.workspace / (name + ".c")
        source.write_text(harness, encoding="utf-8")
        library = cls.workspace / (name + ".so")
        command = shlex.split(os.environ.get("CC", "cc")) + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
            "-DHAVE_TAGCACHE", "-shared", "-fPIC", "-fsanitize=undefined", "-fno-sanitize-recover=all",
            str(source), "-o", str(library)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (cls.workspace / (name + ".log")).write_text(shlex.join(command) + "\n" + result.stdout + result.stderr,
                                                    encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        loaded = ctypes.CDLL(str(library))
        loaded.probe_touch.argtypes = [ctypes.c_int] * 3 + [ctypes.c_uint32, ctypes.c_int]
        loaded.probe_poll.argtypes = [ctypes.c_uint32, ctypes.c_int]
        return loaded

    def setUp(self):
        self.library.bridge_begin()

    def request(self, kind, milliseconds, library=None):
        selected = library or self.library
        return selected.probe_touch(self.constants["TOUCHEVENT_" + kind], 40, 50, milliseconds,
                                    self.constants["CONTEXT_KEYBOARD"])

    def test_real_request_is_audible_only_after_deferred_keyboard_consumption(self):
        self.assertEqual(self.request("PRESS", 0), self.constants["ACTION_TOUCHSCREEN"])
        self.assertEqual(self.library.probe_feedback_stat(0), 0)
        self.library.bridge_consume(0)
        self.assertEqual(self.library.probe_feedback_stat(0), 1)
        self.library.bridge_consume(1)
        self.assertEqual(self.library.probe_feedback_stat(0), 1)
        self.request("CONTACT", 10)
        self.library.bridge_consume(0)
        self.assertEqual(self.library.probe_feedback_stat(0), 1)
        self.request("CONTACT", 20)
        self.library.bridge_consume(1)
        self.assertEqual(self.library.probe_feedback_stat(0), 2)
        self.request("CONTACT", 30)
        self.library.bridge_consume(-1)
        self.assertEqual(self.library.probe_feedback_stat(1), 1)
        self.request("RELEASE", 40)
        self.library.bridge_consume(2)
        self.library.probe_poll(100, self.constants["CONTEXT_KEYBOARD"])
        self.library.bridge_consume(2)
        self.assertEqual(self.library.probe_feedback_stat(0), 3)
        self.request("PRESS", 200)
        self.library.bridge_consume(-1)
        self.assertEqual(self.library.probe_feedback_stat(0), 4)

    def test_cancel_discards_queued_feedback_before_keyboard_resolution(self):
        self.request("PRESS", 0)
        self.library.accessibility_cancel_touch()
        self.library.bridge_consume(0)
        self.assertEqual(self.library.probe_feedback_stat(0), 0)

    def test_regression_rejects_clearing_feedback_before_queued_touch_is_consumed(self):
        self.mutant.bridge_begin()
        self.request("PRESS", 0, self.mutant)
        self.mutant.bridge_consume(0)
        self.assertEqual(self.mutant.probe_feedback_stat(0), 0)
        self.request("PRESS", 0)
        self.library.bridge_consume(0)
        self.assertEqual(self.library.probe_feedback_stat(0), 1)

    @classmethod
    def tearDownClass(cls):
        changed = [path for path, value in cls.inputs.items() if (ROOT / path).read_bytes() != value]
        if changed:
            raise AssertionError("Deferred typing inputs changed during bounded tests: " + ", ".join(changed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
