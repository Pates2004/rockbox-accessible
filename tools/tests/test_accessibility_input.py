"""Exercise actual input dispatch and v1-v10 configuration with isolated core mocks."""

import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root
import test_accessibility_settings as core
from test_tts_coverage import extract_block


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tools/tests/fixtures/accessibility_input_fixture.c"
SERVICES = ((17, 0), (18, 1))
BUTTONS = (1, 8, 4, 16, 32)
RELEASE = 0x2000000
REPEAT = 0x4000000
PASSIVE_POWER_EVENTS = (0x40000003, 0x4000000b, 0x4000000c)


def configuration(version=11, **options):
    if version >= 6:
        buttons = {(button, slot): core.VERSION_ACTION_LIMITS[version] + 1
                   for button in range(5) for slot in range(4)}
        buttons.update(options.pop("buttons", None) or {})
        options["buttons"] = buttons
    return core.default_config(version=version, **options)


class AccessibilityInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            raise unittest.SkipTest("C host compiler unavailable")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.workspace = confined_path(central / "r1-gesture-extensions-20261016/input" / stamp, central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.commands = []
        cls.cases = []
        paths = (
            "apps/accessibility.c", "apps/accessibility.h", "apps/accessibility_screen.c",
            "apps/accessibility_screen.h", "apps/accessibility_shortcut.h", "apps/accessibility_services.h",
            "apps/accessibility_gesture.c", "apps/accessibility_gesture.h",
            "apps/accessibility_buttons.c", "apps/accessibility_buttons.h",
            "apps/action.h", "apps/root_menu.h", "apps/screens.c", "firmware/export/touchscreen.h",
            "tools/tests/test_tts_coverage.py",
            "tools/tests/test_accessibility_settings.py",
            "tools/tests/test_accessibility_input.py",
            "tools/tests/fixtures/accessibility_input_fixture.c",
        )
        cls.inputs = {name: (ROOT / name).read_bytes() for name in paths}
        cls.addClassCleanup(cls.report)
        sources = {name: value.decode("utf-8") for name, value in cls.inputs.items()}
        action_header = sources["apps/action.h"]
        context_defines = "\n".join(re.findall(r'^#define CONTEXT_[^\n]+', action_header, re.MULTILINE))
        action_enums = action_header[action_header.index("enum {"):action_header.index("struct button_mapping {")]
        root_enum = re.search(r'enum\s*\{.*?\};', sources["apps/root_menu.h"], re.DOTALL)
        if root_enum is None:
            raise AssertionError("Missing actual root navigation enum")
        battery = re.search(r'^void accessibility_speak_battery\(bool enqueue\)\s*\{.*?^\}',
                            sources["apps/accessibility_screen.c"], re.MULTILINE | re.DOTALL)
        if battery is None:
            raise AssertionError("Missing actual battery helper")
        labels = sorted(set(re.findall(r'\bLANG_[A-Z0-9_]+', sources["apps/accessibility.c"] + battery[0])))
        language = "\n".join(f"#define {label} {index + 1000}" for index, label in enumerate(labels))
        harness = "#define HAVE_ESPEAK\n#define BUTTON_NONE 0\n#define HAVE_VOLUME_IN_LIST\n#define HAVE_TAGCACHE\n"
        harness += context_defines + "\n" + action_enums + "\n" + root_enum[0] + "\n"
        harness += core.PREAMBLE + "\n" + language + "\n"
        for name in ("firmware/export/touchscreen.h", "apps/accessibility_gesture.h",
                     "apps/accessibility_buttons.h", "apps/accessibility.h",
                     "apps/accessibility_screen.h", "apps/accessibility_shortcut.h", "apps/accessibility_services.h"):
            harness += core.without_includes(sources[name]) + "\n"
        harness += battery[0] + "\n"
        for name in ("apps/accessibility_gesture.c", "apps/accessibility_buttons.c", "apps/accessibility.c"):
            harness += core.without_includes(sources[name]) + "\n"
        harness += core.WRAPPERS + "\n" + sources[str(FIXTURE.relative_to(ROOT)).replace("\\", "/")]
        harness += "\nint input_button_pending(void) { return accessibility_buttons_waiting(); }\n"
        harness += "int input_context_valid(void) { return physical_context_valid; }\n"
        harness += "int input_touch_pending(void) { return accessibility_gesture_pending(&recognizer); }\n"
        harness += "int input_navigation_exit(int context) { return accessibility_navigation_exit(context); }\n"
        harness += "int input_gesture_action(int action, int context, unsigned int slot)\n"
        harness += "{ return accessibility_gesture_action_for(action, context, slot); }\n"
        harness += "void input_keyclick_repeats(bool enabled) { global_settings.keyclick_repeats = enabled; }\n"
        harness += r'''
#include <time.h>
static int clamp_value_wrap(int value, int maximum, int minimum)
{ return value < minimum ? maximum : value > maximum ? minimum : value; }
static void say_time(int cursor, const struct tm *value) { (void)cursor; (void)value; }
static int default_event_handler(int event) { return event; }
int input_time_consume(int button, int cursorpos)
{
    struct tm value = {.tm_hour = 12};
    struct tm *tm = &value;
    int last_item = 5, min = 0, max = 23;
    int *valptr = &tm->tm_hour;
    bool done = false, usb = false;
'''
        harness += extract_block(sources["apps/screens.c"], "switch ( button )")
        harness += "\n(void)done; (void)usb; return cursorpos;\n}\n"
        names = sorted(set(re.findall(r'\b(?:ACTION_[A-Z0-9_]+|CONTEXT_[A-Z0-9_]+|'
                                     r'ACCESSIBILITY_ACTION_[A-Z0-9_]+|TOUCHEVENT_[A-Z0-9_]+)\b',
                                     sources["apps/accessibility.c"])) | set(labels) |
                       {"GO_TO_FILEBROWSER", "GO_TO_DBBROWSER", "GO_TO_WPS", "GO_TO_MAINMENU",
                        "GO_TO_PLAYLISTS_SCREEN", "GO_TO_PREVIOUS"})
        harness += "\n" + "\n".join(f"int constant_{name}(void) {{ return {name}; }}" for name in names)
        harness_path = cls.workspace / "input.c"
        harness_path.write_text(harness, encoding="utf-8")
        cls.sanitized = bool(os.environ.get("ACCESSIBILITY_INPUT_SANITIZE"))
        cls.no_curtain = bool(os.environ.get("ACCESSIBILITY_INPUT_NO_CURTAIN"))
        command = compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                              str(harness_path), "-o", str(cls.workspace / "input.so")]
        if cls.sanitized:
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        if cls.no_curtain:
            command += ["-DACCESSIBILITY_SETTINGS_NO_CURTAIN"]
        compiled = cls.command(command)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        imported = cls.command(["nm", "-u", str(cls.workspace / "input.so")])
        if imported.returncode:
            raise AssertionError(imported.stderr)
        symbols = {line.split()[-1].split("@")[0] for line in imported.stdout.splitlines() if line.split()}
        forbidden = {"open", "open64", "read", "write", "close", "fsync", "rename", "remove",
                     "system", "execve", "fork", "socket", "ioctl", "reboot", "kill"}
        if symbols & forbidden:
            raise AssertionError("Unmocked core operations: " + repr(symbols & forbidden))
        cls.library = ctypes.CDLL(str(cls.workspace / "input.so"))
        for name in re.findall(r'^bool\s+(accessibility_[a-z_]+)\s*\(',
                               sources["apps/accessibility.h"], re.MULTILINE):
            getattr(cls.library, name).restype = ctypes.c_bool
        cls.constants = {name: getattr(cls.library, "constant_" + name)() for name in names}
        for name in ("probe_parse", "input_install", "probe_disk"):
            getattr(cls.library, name).argtypes = [ctypes.c_char_p, ctypes.c_int]
        cls.library.probe_disk_content.restype = ctypes.c_char_p
        cls.library.probe_path.restype = ctypes.c_char_p
        cls.library.probe_script.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int]
        cls.library.probe_touch.argtypes = [ctypes.c_int] * 3 + [ctypes.c_uint32, ctypes.c_int]
        cls.library.probe_poll.argtypes = [ctypes.c_uint32, ctypes.c_int]
        cls.library.probe_button.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_int, ctypes.c_bool]
        cls.library.probe_speech_available.argtypes = [ctypes.c_bool]
        cls.library.probe_enable.argtypes = [ctypes.c_bool]
        cls.library.input_success.argtypes = [ctypes.c_bool]
        cls.library.accessibility_process_pending.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.library.probe_time.argtypes = [ctypes.c_uint32]
        cls.library.probe_touch_options.argtypes = [ctypes.c_uint, ctypes.c_bool]
        cls.library.probe_touch_trial.argtypes = [ctypes.c_uint, ctypes.c_bool]
        cls.library.probe_navigation_available.argtypes = [ctypes.c_bool]
        cls.library.input_keyclick_repeats.argtypes = [ctypes.c_bool]
        print("Input evidence:", cls.workspace, flush=True)

    @classmethod
    def command(cls, arguments):
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=60, cwd=cls.workspace)
        cls.commands.append({"arguments": arguments, "returncode": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        return result

    @classmethod
    def report(cls):
        unchanged = all((ROOT / name).read_bytes() == value for name, value in cls.inputs.items())
        report = {
            "source_project": str(ROOT),
            "source_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in cls.inputs.items()},
            "sources_unchanged": unchanged,
            "commands": cls.commands, "cases": cls.cases,
            "sanitized": getattr(cls, "sanitized", False),
            "screen_curtain": not getattr(cls, "no_curtain", False),
            "passed": bool(cls.cases) and unchanged and all(case["passed"] for case in cls.cases),
            "scope": "Actual accessibility.c and both recognizers; actual service header; mocked core/UI/filesystem and service endpoints",
            "limitations": "No real synthesis, voice-file service effect, GUI, physical input, release or hardware acceptance",
        }
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
        if not unchanged:
            raise AssertionError("Input dependencies changed during tests")

    def setUp(self):
        self.library.input_reset()

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id()
                     for test, unused in result.failures + result.errors)
        self.cases.append({"name": self.id(), "passed": not failed})

    def constant(self, name):
        return self.constants[name]

    def install(self, content):
        self.assertEqual(self.library.input_install(content, len(content)), 1)

    def calls(self):
        return tuple(self.library.input_calls(service) for service in range(2))

    def script(self, selections, choice):
        values = (ctypes.c_int * len(selections))(*selections)
        self.library.probe_script(values, len(selections), choice)

    def process_pending(self, event, context=None):
        return self.library.accessibility_process_pending(event,
            self.constant("CONTEXT_STD") if context is None else context)

    def touch(self, event, milliseconds, position_x=100, position_y=200, context=None):
        return self.library.probe_touch(self.constant(event), position_x, position_y, milliseconds,
                                       self.constant("CONTEXT_STD") if context is None else context)

    def gesture(self, kind, context=None):
        if kind == "stroke":
            self.touch("TOUCHEVENT_PRESS", 10, 300, 400, context)
            self.touch("TOUCHEVENT_CONTACT", 40, 250, 400, context)
            self.touch("TOUCHEVENT_CONTACT", 70, 200, 400, context)
            self.touch("TOUCHEVENT_RELEASE", 100, 200, 400, context)
        elif kind == "double":
            for start in (10, 110):
                self.touch("TOUCHEVENT_PRESS", start, context=context)
                self.touch("TOUCHEVENT_RELEASE", start + 40, context=context)
            self.library.probe_poll(480, self.constant("CONTEXT_STD") if context is None else context)
        else:
            self.touch("TOUCHEVENT_PRESS", 10, context=context)
            self.library.probe_poll(910, self.constant("CONTEXT_STD") if context is None else context)
            self.touch("TOUCHEVENT_CONTACT", 1200, context=context)
            self.touch("TOUCHEVENT_RELEASE", 1500, context=context)

    def physical(self, button, slot, *, context=None, locked=False, first_repeat=False):
        context = self.constant("CONTEXT_STD") if context is None else context
        raw = BUTTONS[button]
        if slot == 3:
            self.library.probe_button(raw, 0, context, locked)
            self.library.probe_button(raw | REPEAT if first_repeat else 0, 700, context, locked)
            for milliseconds in (800, 900, 1100):
                self.library.probe_button(raw | REPEAT, milliseconds, context, locked)
            self.library.probe_button(raw | RELEASE, 1200, context, locked)
        else:
            for click in range(slot + 1):
                self.library.probe_button(raw, click * 100, context, locked)
                self.library.probe_button(raw | REPEAT, click * 100 + 20, context, locked)
                self.library.probe_button(raw | RELEASE, click * 100 + 50, context, locked)
        self.library.probe_button(0, 1600, context, locked)

    def test_stable_ids_labels_and_unchanged_default_maps(self):
        for name, value in (("TIME", 16), ("TOGGLE_ESPEAK", 17), ("TOGGLE_VOICE_FILES", 18),
                            ("TOGGLE_TOUCH", 19), ("DATE", 20), ("SUMMARY", 21),
                            ("FIRST", 22), ("LAST", 23), ("PAGE_FIRST", 24), ("PAGE_LAST", 25), ("SHORTCUT", 26),
                            ("COUNT", 27), ("SYSTEM", 27)):
            self.assertEqual(self.constant("ACCESSIBILITY_ACTION_" + name), value)
        self.assertEqual(self.calls(), (0, 0))
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_disk_content(), core.default_config(factory=True))

    def test_every_supported_action_migrates_and_round_trips_for_all_versions(self):
        for version, maximum in core.VERSION_ACTION_LIMITS.items():
            for action in range(maximum + 1):
                with self.subTest(version=version, action=action):
                    self.setUp()
                    mappings = {slot: action for slot in range(1, 21 if version >= 7 else 19)}
                    buttons = {(1, 2): action} if version > 1 else None
                    self.install(configuration(version=version, replacements=mappings, buttons=buttons))
                    self.assertEqual([self.library.probe_mapping(slot) for slot in range(1, 19)], [action] * 18)
                    self.assertEqual(self.library.probe_button_mapping(0, 0), 27)
                    self.assertEqual(self.library.probe_save(), 1)
                    clicks = 7 if version == 1 or version >= 8 else 3
                    self.assertEqual(self.library.probe_disk_content(), configuration(replacements=mappings, buttons=buttons, clicks=clicks))
                    self.library.probe_reload()
                    self.assertEqual(self.library.probe_button_mapping(1, 2), action if version > 1 else 27)
                    self.assertEqual(self.calls(), (0, 0))

    def test_factory_endpoint_gestures_and_legacy_v10_choices_are_independent(self):
        for slot, action in ((13, 22), (16, 23)):
            self.assertEqual(self.library.probe_mapping(slot), action)
            self.assertEqual(self.library.probe_playback_gesture(slot), action)
        legacy = configuration(version=10)
        self.library.probe_disk(legacy, len(legacy))
        self.library.probe_reload()
        self.assertEqual(self.library.probe_disk_content(), legacy)
        for slot in (13, 16):
            self.assertEqual(self.library.probe_mapping(slot), 0)
            self.assertEqual(self.library.probe_playback_gesture(slot), 0)
        self.assertEqual(self.library.probe_button_mapping(0, 2), 27)
        self.assertEqual(self.library.probe_playback_mapping(0, 2), 27)
        self.assertEqual(self.library.probe_stat(2), 0)
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_disk_content(), configuration())
        self.assertEqual(self.library.input_gate_calls(), 0)

    def test_all_four_endpoint_actions_dispatch_only_to_list_contexts(self):
        names = ("ACTION_LIST_FIRST", "ACTION_LIST_LAST", "ACTION_LIST_PAGE_FIRST", "ACTION_LIST_PAGE_LAST")
        for action, name in enumerate(names, 22):
            for context in ("CONTEXT_STD", "CONTEXT_LIST", "CONTEXT_TREE", "CONTEXT_MAINMENU",
                            "CONTEXT_SETTINGS", "CONTEXT_BOOKMARKSCREEN"):
                with self.subTest(action=action, context=context):
                    self.assertEqual(self.library.probe_action(action, self.constant(context)), self.constant(name))
            for context in ("CONTEXT_WPS", "CONTEXT_KEYBOARD", "CONTEXT_MORSE_INPUT", "CONTEXT_YESNOSCREEN"):
                with self.subTest(action=action, excluded=context):
                    self.assertEqual(self.library.probe_action(action, self.constant(context)), self.constant("ACTION_NONE"))
        reader = self.constant("CONTEXT_STD") | self.constant("CONTEXT_CUSTOM") | self.constant("CONTEXT_CUSTOM2")
        for action in range(22, 26):
            self.assertEqual(self.library.probe_action(action, reader), self.constant("ACTION_NONE"))
        self.assertEqual(self.calls(), (0, 0))
        self.assertEqual(self.library.input_gate_calls(), 0)
        self.assertEqual(self.library.probe_stat(2), 0)

    def test_mapping_trial_cannot_switch_services_or_request_shutdown(self):
        self.library.probe_start_trial(26)
        for action in (13, 17, 18, 26):
            self.assertEqual(self.library.probe_action(action, self.constant("CONTEXT_STD")), self.constant("ACTION_NONE"))
        self.assertEqual(self.calls(), (0, 0))
        self.assertEqual(self.library.input_gate_calls(), 0)
        self.assertEqual(self.library.probe_extra(1), 0)
        self.assertEqual(self.library.probe_stat(2), 0)

    def test_legacy_system_sentinels_never_become_toggles(self):
        for version, sentinel in ((2, 15), (3, 15), (4, 16), (5, 17), (6, 19)):
            with self.subTest(version=version):
                self.setUp()
                self.install(configuration(version=version, buttons={(button, slot): sentinel
                    for button in range(5) for slot in range(4)}))
                for button in range(5):
                    for slot in range(4):
                        self.assertEqual(self.library.probe_button_mapping(button, slot), 27)
                self.physical(1, 0)
                self.assertEqual(self.calls(), (0, 0))
                self.assertEqual(self.library.input_gate_calls(), 0)

    def test_v5_time16_and_system17_preserve_their_meanings(self):
        self.install(configuration(version=5, replacements={1: 16}, buttons={(1, 0): 16, (4, 3): 17}))
        self.assertEqual(self.library.probe_mapping(1), 16)
        self.assertEqual(self.library.probe_button_mapping(1, 0), 16)
        self.assertEqual(self.library.probe_button_mapping(4, 3), 27)
        self.gesture("stroke")
        self.assertEqual(self.library.probe_time_calls(), 1)
        self.assertEqual(self.calls(), (0, 0))
        self.assertEqual(self.library.probe_save(), 1)
        self.library.probe_reload()
        self.assertEqual(self.library.probe_button_mapping(4, 3), 27)

    def test_action_limits_remain_version_specific_and_strict(self):
        values = list(range(-1, 30)) + [255, 256, 999999999999999999999999]
        for version, maximum in core.VERSION_ACTION_LIMITS.items():
            for action in values:
                with self.subTest(version=version, action=action):
                    content = configuration(version=version, replacements={18: action})
                    self.assertEqual(self.library.probe_parse(content, len(content)), int(0 <= action <= maximum))
                    if version > 1:
                        content = configuration(version=version, buttons={(4, 3): action})
                        self.assertEqual(self.library.probe_parse(content, len(content)), int(0 <= action <= maximum + 1))

    def test_v6_rejects_truncations_noncanonical_numbers_and_trailing_bytes(self):
        valid = configuration(version=6, replacements={1: 17, 18: 18}, buttons={(1, 0): 17, (4, 3): 18})
        for length in range(len(valid)):
            self.assertEqual(self.library.probe_parse(valid, length), 0, length)
        invalid = [valid + b"\n", valid + b"\0", valid.replace(b"\n", b"\r\n"), b"x" * 4097,
                   valid.replace(b"gesture:1:17", b"gesture:1:017"),
                   valid.replace(b"gesture:1:17", b"gesture:1:+17"),
                   valid.replace(b"enabled:1", b"enabled:01"),
                   valid.replace(b"gesture:2:2", b"gesture:1:2")]
        invalid += [valid.replace(b"RBACCESSIBILITY:6", f"RBACCESSIBILITY:{version}".encode())
                    for version in (0, 7, 10, "06", "6 ")]
        for content in invalid:
            self.assertEqual(self.library.probe_parse(content, len(content)), 0)
        self.assertEqual(self.calls(), (0, 0))

    def test_toggle_actions_cannot_carry_launch_bindings(self):
        for action, service in SERVICES:
            for options in (dict(replacements={1: action}, gesture_refs={1: 1}),
                            dict(buttons={(1, 0): action}, button_refs={(1, 0): 2})):
                content = configuration(**options)
                self.assertEqual(self.library.probe_parse(content, len(content)), 0)
        self.assertEqual(self.calls(), (0, 0))

    def test_launch_bindings_feedback_and_hold_survive_migration(self):
        options = dict(enabled=0, replacements={1: 12, 18: 12}, buttons={(1, 2): 12},
                       gesture_refs={1: 4, 18: 1}, button_refs={(1, 2): 7}, clicks=1, hold=1100,
                       paths={0: "/.rockbox/rocks/apps/calculator.rock",
                              3: "/.rockbox/rocks/apps/stopwatch.rock"})
        for version in (3, 4, 5, 6, 7, 8):
            self.setUp()
            self.install(configuration(version=version, **options))
            self.assertEqual(self.library.probe_save(), 1)
            self.assertEqual(self.library.probe_disk_content(), configuration(**options))
            self.library.probe_reload()
            self.assertEqual(self.library.probe_ref(-1, 1), 4)
            self.assertEqual(self.library.probe_ref(1, 2), 7)
            self.assertEqual(self.library.probe_path(3), options["paths"][3].encode())
            self.assertEqual(self.library.accessibility_keyclick_sources(), 1)
            self.assertEqual(self.library.probe_extra(5), 1100)

    def test_partial_save_and_reload_preserve_both_toggle_mappings(self):
        content = configuration(replacements={1: 17, 18: 18}, buttons={(1, 0): 17, (4, 3): 18})
        self.install(content)
        self.library.probe_chunks(1, 1)
        self.assertEqual(self.library.probe_save(), 1)
        self.assertEqual(self.library.probe_disk_content(), content)
        self.assertEqual(self.library.probe_syncs(), 1)
        self.library.probe_reload()
        self.assertEqual(self.library.probe_mapping(18), 18)
        self.assertEqual(self.library.probe_button_mapping(4, 3), 18)
        self.assertEqual(self.calls(), (0, 0))

    def test_save_faults_preserve_every_legacy_file(self):
        for version in range(1, 7):
            for fault in range(4, 11):
                with self.subTest(version=version, fault=fault):
                    self.setUp()
                    old = configuration(version=version)
                    self.library.probe_disk(old, len(old))
                    self.library.probe_reload()
                    self.library.probe_assign(1, 17)
                    self.library.probe_chunks(0, 7)
                    self.library.probe_fault(fault)
                    self.assertEqual(self.library.probe_save(), 0)
                    self.assertEqual(self.library.probe_disk_content(), old)
                    self.assertEqual(self.library.probe_temporary_exists(), 0)
                    self.assertEqual(self.calls(), (0, 0))

    def test_invalid_save_does_not_open_or_replace_configuration(self):
        for button, action in ((False, 27), (True, 28)):
            self.setUp()
            if button:
                self.library.probe_button_assign(1, 0, action)
            else:
                self.library.probe_assign(1, action)
            opened = self.library.probe_stat(0)
            self.assertEqual(self.library.probe_save(), 0)
            self.assertEqual(self.library.probe_stat(0), opened)
            self.assertEqual(self.library.probe_stat(2), 0)

    def test_direct_dispatch_bypasses_speech_and_shortcut_enable_gates(self):
        contexts = [self.constant(name) for name in ("CONTEXT_STD", "CONTEXT_WPS", "CONTEXT_KEYBOARD",
                    "CONTEXT_SETTINGS", "CONTEXT_YESNOSCREEN", "CONTEXT_QUICKSCREEN")]
        contexts.append(self.constant("CONTEXT_STD") | self.constant("CONTEXT_CUSTOM") |
                        self.constant("CONTEXT_CUSTOM2"))
        for action, service in SERVICES:
            for success in (True, False):
                self.setUp()
                self.library.probe_speech_available(False)
                self.library.input_success(success)
                for count, context in enumerate(contexts, 1):
                    self.assertEqual(self.library.probe_action(action, context), self.constant("ACTION_NONE"))
                    self.assertEqual(self.library.input_calls(service), count)
                    self.assertEqual(self.library.input_calls(1 - service), 0)
                self.assertEqual(self.library.input_gate_calls(), 0)
                self.assertEqual(self.library.probe_stat(13), 0)
                self.assertEqual(self.library.probe_extra(1), 0)

    def test_physical_recognition_fires_once_for_every_button_and_slot(self):
        for action, service in SERVICES:
            for button in range(5):
                for slot in range(4):
                    with self.subTest(action=action, button=button, slot=slot):
                        self.setUp()
                        self.library.probe_button_assign(button, slot, action)
                        self.physical(button, slot)
                        self.assertEqual(self.library.input_calls(service), 1)
                        self.assertEqual(self.library.input_calls(1 - service), 0)
                        self.assertEqual(self.library.input_gate_calls(), 0)

    def test_physical_repeat_gate_rejects_every_toggle_mapping(self):
        for action, service in SERVICES:
            for button in range(5):
                for slot in range(4):
                    self.setUp()
                    self.library.probe_button_assign(button, slot, action)
                    self.assertEqual(self.library.input_repeat(button, slot, self.constant("CONTEXT_STD")),
                                     self.constant("ACTION_UNKNOWN"))
                    self.assertEqual(self.calls(), (0, 0))

    def test_first_hold_recognition_from_repeat_still_runs_only_once(self):
        for action, service in SERVICES:
            self.setUp()
            self.library.probe_button_assign(1, 3, action)
            self.physical(1, 3, first_repeat=True)
            self.assertEqual(self.library.input_calls(service), 1)

    def test_physical_toggles_remain_available_with_touch_and_speech_disabled(self):
        for action, service in SERVICES:
            self.setUp()
            self.install(configuration(enabled=0, buttons={(1, 0): action}))
            self.library.probe_speech_available(False)
            self.physical(1, 0)
            self.assertEqual(self.library.input_calls(service), 1)
            self.assertEqual(self.library.accessibility_enabled(), 0)
            self.assertEqual(self.library.input_gate_calls(), 0)

    def test_physical_locked_and_plugin_contexts_do_not_toggle(self):
        for action, service in SERVICES:
            for context, locked in ((self.constant("CONTEXT_STD"), True),
                                    (self.constant("CONTEXT_STD") | self.constant("CONTEXT_PLUGIN"), False)):
                self.setUp()
                self.library.probe_button_assign(1, 0, action)
                self.physical(1, 0, context=context, locked=locked)
                self.assertEqual(self.calls(), (0, 0))

    def test_passive_power_events_preserve_deferred_system_back(self):
        context = self.constant("CONTEXT_STD")
        for event in PASSIVE_POWER_EVENTS:
            with self.subTest(event=hex(event)):
                self.setUp()
                self.install(configuration(enabled=0, buttons={(1, 1): 18}))
                self.assertEqual(self.library.probe_button_mapping(1, 0), 27)
                self.library.probe_button(8, 0, context, False)
                self.library.probe_button(8 | RELEASE, 80, context, False)
                self.assertEqual(self.library.input_button_pending(), 1)
                self.library.probe_time(20)
                self.assertEqual(self.process_pending(event), 0)
                self.assertEqual(self.library.input_context_valid(), 1)
                self.assertEqual(self.library.input_button_pending(), 1)
                self.assertEqual(self.library.probe_button(0, 370, context, False), -1)
                self.assertEqual(self.library.probe_button(0, 400, context, False),
                                 self.constant("ACTION_STD_OK"))
                for milliseconds in (450, 700, 1000):
                    self.assertEqual(self.library.probe_button(0, milliseconds, context, False), -1)
                self.assertEqual(self.calls(), (0, 0))

    def test_passive_power_events_preserve_pending_touch(self):
        for event in PASSIVE_POWER_EVENTS:
            with self.subTest(event=hex(event)):
                self.setUp()
                self.library.probe_assign(1, 17)
                self.touch("TOUCHEVENT_PRESS", 10, 300, 400)
                self.touch("TOUCHEVENT_CONTACT", 40, 250, 400)
                self.library.probe_time(5)
                self.assertEqual(self.process_pending(event), 0)
                self.touch("TOUCHEVENT_CONTACT", 70, 200, 400)
                self.touch("TOUCHEVENT_RELEASE", 100, 200, 400)
                self.library.probe_poll(1000, self.constant("CONTEXT_STD"))
                self.library.probe_poll(2000, self.constant("CONTEXT_STD"))
                self.assertEqual(self.calls(), (1, 0))

    def test_passive_power_events_preserve_pending_double_tap_once(self):
        for event in PASSIVE_POWER_EVENTS:
            with self.subTest(event=hex(event)):
                self.setUp()
                self.library.probe_assign(17, 17)
                self.touch("TOUCHEVENT_PRESS", 10)
                self.touch("TOUCHEVENT_RELEASE", 50)
                self.assertEqual(self.library.input_touch_pending(), 1)
                self.library.probe_time(8)
                self.assertEqual(self.process_pending(event), 0)
                self.assertEqual(self.library.input_touch_pending(), 1)
                self.touch("TOUCHEVENT_PRESS", 110)
                self.touch("TOUCHEVENT_RELEASE", 150)
                for milliseconds in (500, 1000, 1500):
                    self.library.probe_poll(milliseconds, self.constant("CONTEXT_STD"))
                self.assertEqual(self.calls(), (1, 0))

    def test_passive_power_events_preserve_double_and_hold_without_duplicates(self):
        context = self.constant("CONTEXT_STD")
        for event in PASSIVE_POWER_EVENTS:
            for slot in (1, 3):
                with self.subTest(event=hex(event), slot=slot):
                    self.setUp()
                    self.install(configuration(enabled=0, buttons={(1, slot): 18}))
                    self.library.probe_button(8, 0, context, False)
                    if slot == 1:
                        self.library.probe_button(8 | RELEASE, 50, context, False)
                    self.library.probe_time(8)
                    self.assertEqual(self.process_pending(event), 0)
                    self.assertEqual(self.library.input_button_pending(), 1)
                    if slot == 1:
                        self.library.probe_button(8, 100, context, False)
                        self.library.probe_button(8 | RELEASE, 150, context, False)
                    else:
                        self.library.probe_button(0, 700, context, False)
                        self.library.probe_button(8 | REPEAT, 800, context, False)
                        self.library.probe_button(8 | RELEASE, 850, context, False)
                    self.library.probe_button(0, 1000, context, False)
                    self.library.probe_button(0, 1500, context, False)
                    self.assertEqual(self.calls(), (0, 1))

    def test_interrupting_system_events_still_cancel_physical_and_touch(self):
        context = self.constant("CONTEXT_STD")
        for event in (0x40000001, 0x40000002, 0x40000004, 0x40000008):
            with self.subTest(event=hex(event), source="physical"):
                self.setUp()
                self.install(configuration(enabled=0, buttons={(1, 1): 18}))
                self.library.probe_button(8, 0, context, False)
                self.library.probe_button(8 | RELEASE, 80, context, False)
                self.assertEqual(self.library.input_button_pending(), 1)
                self.assertEqual(self.process_pending(event), 0)
                self.assertEqual(self.library.input_button_pending(), 0)
                self.assertEqual(self.library.input_context_valid(), 0)
                for milliseconds in (400, 700, 1000):
                    self.assertEqual(self.library.probe_button(0, milliseconds, context, False), -1)
                self.assertEqual(self.calls(), (0, 0))
            with self.subTest(event=hex(event), source="touch"):
                self.setUp()
                self.library.probe_assign(1, 17)
                self.touch("TOUCHEVENT_PRESS", 10, 300, 400)
                self.touch("TOUCHEVENT_CONTACT", 40, 250, 400)
                self.assertEqual(self.library.input_touch_pending(), 1)
                self.assertEqual(self.process_pending(event), 0)
                self.assertEqual(self.library.input_touch_pending(), 0)
                self.touch("TOUCHEVENT_CONTACT", 70, 200, 400)
                self.touch("TOUCHEVENT_RELEASE", 100, 200, 400)
                self.library.probe_poll(1000, context)
                self.assertEqual(self.calls(), (0, 0))

    def test_context_and_target_changes_still_cancel_physical_and_touch(self):
        context = self.constant("CONTEXT_STD")
        for reset in ("context", "target"):
            with self.subTest(reset=reset, source="physical"):
                self.setUp()
                self.install(configuration(enabled=0, buttons={(1, 1): 18}))
                self.library.probe_button(8, 0, context, False)
                self.library.probe_button(8 | RELEASE, 80, context, False)
                self.assertEqual(self.library.input_button_pending(), 1)
                if reset == "context":
                    self.library.probe_button(0, 200, self.constant("CONTEXT_WPS"), False)
                else:
                    self.library.probe_target(1)
                self.assertEqual(self.library.input_button_pending(), 0)
                self.assertEqual(self.library.probe_button(0, 700, context, False), -1)
                self.assertEqual(self.calls(), (0, 0))
            with self.subTest(reset=reset, source="touch"):
                self.setUp()
                self.library.probe_assign(1, 17)
                self.touch("TOUCHEVENT_PRESS", 10, 300, 400)
                self.touch("TOUCHEVENT_CONTACT", 40, 250, 400)
                if reset == "context":
                    self.library.probe_poll(50, self.constant("CONTEXT_WPS"))
                else:
                    self.library.probe_target(1)
                self.assertEqual(self.library.input_touch_pending(), 0)
                self.touch("TOUCHEVENT_CONTACT", 70, 200, 400)
                self.touch("TOUCHEVENT_RELEASE", 100, 200, 400)
                self.library.probe_poll(1000, context)
                self.assertEqual(self.calls(), (0, 0))

    def test_stroke_double_and_hold_dispatch_once_without_tts(self):
        for action, service in SERVICES:
            for kind, slot in (("stroke", 1), ("double", 17), ("hold", 18)):
                with self.subTest(action=action, kind=kind):
                    self.setUp()
                    self.library.probe_assign(slot, action)
                    self.library.probe_speech_available(False)
                    self.gesture(kind)
                    self.library.probe_poll(2000, self.constant("CONTEXT_STD"))
                    self.library.probe_poll(3000, self.constant("CONTEXT_STD"))
                    self.assertEqual(self.library.input_calls(service), 1)
                    self.assertEqual(self.library.input_calls(1 - service), 0)
                    self.assertEqual(self.library.input_gate_calls(), 0)

    def test_disabled_gestures_never_dispatch_toggles(self):
        for action, service in SERVICES:
            for kind, slot in (("stroke", 1), ("double", 17), ("hold", 18)):
                self.setUp()
                self.install(configuration(enabled=0, replacements={slot: action}))
                self.gesture(kind)
                self.assertEqual(self.calls(), (0, 0))

    def test_gesture_locked_and_plugin_contexts_do_not_toggle(self):
        for action, service in SERVICES:
            for flag in ("CONTEXT_PLUGIN", "CONTEXT_LOCKED"):
                self.setUp()
                self.library.probe_assign(1, action)
                self.gesture("stroke", self.constant("CONTEXT_STD") | self.constant(flag))
                self.assertEqual(self.calls(), (0, 0))

    def test_both_selectors_expose_labels_save_and_reselect_each_toggle(self):
        labels = ("LANG_ACCESSIBILITY_TOGGLE_ESPEAK", "LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES")
        for action, service in SERVICES:
            for physical in (False, True):
                with self.subTest(action=action, physical=physical):
                    self.setUp()
                    choice = self.library.input_action_index(action)
                    self.script([0, 4, -1, -1] if physical else [0, 0, -1, -1], choice)
                    result = self.library.accessibility_buttons_menu() if physical else self.library.input_edit_gesture()
                    self.assertEqual(result, 0)
                    self.assertEqual(self.library.probe_option_voice(choice), self.constant(labels[service]))
                    self.assertEqual(self.library.probe_button_mapping(1, 0) if physical else
                                     self.library.probe_mapping(1), action)
                    self.assertTrue(self.library.probe_disk_content().startswith(b"RBACCESSIBILITY:11\n"))
                    self.script([0, 4, -1, -1] if physical else [0, 0, -1, -1], choice)
                    if physical:
                        self.library.accessibility_buttons_menu()
                    else:
                        self.library.input_edit_gesture()
                    self.assertEqual(self.library.probe_option_initial_choice(), choice)
                    self.assertEqual(self.calls(), (0, 0))

    def test_cancelled_mapping_trials_do_not_toggle_or_persist(self):
        for action, service in SERVICES:
            for physical in (False, True):
                self.setUp()
                self.library.probe_prompt(1, 0)
                self.script([0, 4, -1, -1] if physical else [0, 0, -1, -1], self.library.input_action_index(action))
                if physical:
                    self.library.accessibility_buttons_menu()
                    self.assertEqual(self.library.probe_button_mapping(1, 0), 27)
                else:
                    self.library.input_edit_gesture()
                    self.assertEqual(self.library.probe_mapping(1), 1)
                self.assertEqual(self.library.probe_stat(2), 0)
                self.assertEqual(self.calls(), (0, 0))

    def test_default_triple_power_activates_group_once_in_both_profiles(self):
        for context in ("CONTEXT_STD", "CONTEXT_WPS"):
            with self.subTest(context=context):
                self.setUp()
                self.physical(0, 2, context=self.constant(context))
                self.assertEqual(self.calls(), (0, 0))
                self.assertEqual(self.library.input_gate_calls(), 1)
                self.assertEqual(self.library.probe_button_mapping(0, 2), 26)

    def taps(self, count, context=None):
        actions = []
        for click in range(count):
            actions.append(self.touch("TOUCHEVENT_PRESS", 10 + click * 100, context=context))
            actions.append(self.touch("TOUCHEVENT_RELEASE", 50 + click * 100, context=context))
        return actions

    def held_stroke(self, context, *, milliseconds=970):
        self.touch("TOUCHEVENT_PRESS", 10, 300, 400, context)
        self.touch("TOUCHEVENT_CONTACT", 40, 250, 400, context)
        self.touch("TOUCHEVENT_CONTACT", 70, 200, 400, context)
        return self.library.probe_poll(milliseconds, context)

    def test_unassigned_triple_never_runs_assigned_double_or_single(self):
        context = self.constant("CONTEXT_STD")
        for triple_action in (0, 18, 20, 21):
            with self.subTest(triple_action=triple_action):
                self.setUp()
                self.install(configuration(replacements={17: 17, 19: triple_action}))
                self.assertEqual(self.taps(3), [self.constant("ACTION_NONE")] * 6)
                for milliseconds in (260, 570, 580, 1000, 3000):
                    self.assertEqual(self.library.probe_poll(milliseconds, context), self.constant("ACTION_NONE"))
                self.assertEqual(self.calls(), (0, int(triple_action == 18)))
                self.assertEqual(self.library.probe_date_calls(), int(triple_action == 20))
                self.assertEqual(self.library.probe_summary_calls(), int(triple_action == 21))
                self.assertEqual(self.library.probe_extra(0), 1)
                self.assertEqual(self.library.input_touch_pending(), 0)

    def test_double_waits_for_third_window_even_when_triple_unassigned(self):
        self.library.probe_assign(17, 17)
        context = self.constant("CONTEXT_STD")
        self.taps(2)
        self.assertEqual(self.calls(), (0, 0))
        self.library.probe_poll(470, context)
        self.assertEqual(self.calls(), (0, 0))
        self.library.probe_poll(480, context)
        self.assertEqual(self.calls(), (1, 0))
        self.assertEqual(self.library.input_touch_pending(), 0)
        self.library.probe_poll(1000, context)
        self.assertEqual(self.calls(), (1, 0))

    def test_unassigned_physical_multiclicks_do_not_fall_back(self):
        context = self.constant("CONTEXT_STD")
        for button in range(5):
            for slot in (1, 2):
                with self.subTest(button=button, slot=slot):
                    self.setUp()
                    self.install(configuration(buttons={(button, 0): 17, (button, 1): 0,
                                                        (button, 2): 0}))
                    self.physical(button, slot, context=context)
                    self.assertEqual(self.calls(), (0, 0))
                    self.assertEqual(self.library.probe_default_button_calls(), 0)
                    self.assertEqual(self.library.probe_stat(5), 0)

    def test_default_double_hold_context_does_not_delete_or_confirm(self):
        for context_name, expected in (("CONTEXT_STD", "ACTION_STD_CONTEXT"),
                ("CONTEXT_TREE", "ACTION_STD_CONTEXT"), ("CONTEXT_WPS", "ACTION_WPS_CONTEXT"),
                ("CONTEXT_KEYBOARD", "ACTION_NONE"), ("CONTEXT_MORSE_INPUT", "ACTION_NONE"),
                ("CONTEXT_YESNOSCREEN", "ACTION_NONE"), ("CONTEXT_SETTINGS", "ACTION_NONE"),
                ("CONTEXT_QUICKSCREEN", "ACTION_NONE")):
            with self.subTest(context=context_name):
                self.setUp()
                context = self.constant(context_name)
                self.touch("TOUCHEVENT_PRESS", 10, context=context)
                self.touch("TOUCHEVENT_RELEASE", 50, context=context)
                self.touch("TOUCHEVENT_PRESS", 110, context=context)
                self.assertEqual(self.library.probe_poll(1000, context), self.constant("ACTION_NONE"))
                self.assertEqual(self.library.probe_poll(1010, context), self.constant(expected))
                self.assertEqual(self.library.probe_poll(2000, context), self.constant("ACTION_NONE"))
                self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 2100, context=context),
                                 self.constant("ACTION_NONE"))
                self.assertEqual(self.calls(), (0, 0))
                self.assertEqual(self.library.probe_extra(0), 1)
        for flag in ("CONTEXT_PLUGIN", "CONTEXT_LOCKED", "CONTEXT_CUSTOM"):
            context = self.constant("CONTEXT_STD") | self.constant(flag)
            self.assertEqual(self.library.input_gesture_action(8, context, 20), self.constant("ACTION_NONE"))
        reader = self.constant("CONTEXT_STD") | self.constant("CONTEXT_CUSTOM") | self.constant("CONTEXT_CUSTOM2")
        self.assertEqual(self.library.input_gesture_action(8, reader, 20), self.constant("ACTION_STD_CONTEXT"))
        self.assertEqual(self.library.input_gesture_action(8, self.constant("CONTEXT_KEYBOARD"), 18),
                         self.constant("ACTION_KBD_BACKSPACE"))

    def test_touch_browsing_off_blocks_new_gestures_timers_and_typing(self):
        for source in ("triple", "double_hold", "repeat", "typing"):
            with self.subTest(source=source):
                self.setUp()
                self.install(configuration(enabled=0, stroke_repeat=1,
                    replacements={1: 17, 19: 18, 20: 20}))
                context = self.constant("CONTEXT_STD")
                if source == "triple":
                    self.taps(3)
                elif source == "double_hold":
                    self.taps(1)
                    self.touch("TOUCHEVENT_PRESS", 110)
                elif source == "repeat":
                    self.held_stroke(context)
                else:
                    self.library.probe_typing(True)
                    self.library.probe_typing_mode(0)
                    context = self.constant("CONTEXT_KEYBOARD")
                    self.taps(3, context)
                self.library.probe_poll(2000, context)
                self.assertEqual(self.library.probe_typing_dispatches(), 0)
                self.assertEqual(self.library.probe_date_calls(), 0)
                self.assertEqual(self.calls(), (0, 0))
                self.assertEqual(self.library.input_touch_pending(), 0)

    def test_held_stroke_repeats_audited_navigation_and_stops_on_release(self):
        for clicks in (False, True):
            with self.subTest(click_repeats=clicks):
                self.setUp()
                self.install(configuration(stroke_repeat=1))
                self.library.input_keyclick_repeats(clicks)
                context = self.constant("CONTEXT_STD")
                self.assertEqual(self.held_stroke(context), self.constant("ACTION_STD_PREV"))
                self.assertEqual(self.library.probe_poll(1120, context), self.constant("ACTION_NONE"))
                for milliseconds in (1130, 1290, 5000):
                    self.assertEqual(self.library.probe_poll(milliseconds, context),
                                     self.constant("ACTION_STD_PREVREPEAT"))
                self.assertEqual(self.touch("TOUCHEVENT_RELEASE", 5160, 200, 400, context),
                                 self.constant("ACTION_NONE"))
                self.assertEqual(self.library.probe_poll(6000, context), self.constant("ACTION_NONE"))
                self.assertEqual(self.library.probe_extra(0), 4 if clicks else 1)

    def test_repeat_never_repeats_activation_modal_changes_or_service_toggles(self):
        for context_name in ("CONTEXT_STD", "CONTEXT_KEYBOARD", "CONTEXT_YESNOSCREEN",
                             "CONTEXT_SETTINGS", "CONTEXT_QUICKSCREEN"):
            for action in (3, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21):
                with self.subTest(context=context_name, action=action):
                    self.setUp()
                    self.install(configuration(stroke_repeat=1, replacements={1: action}))
                    context = self.constant(context_name)
                    self.held_stroke(context)
                    for milliseconds in (1130, 1290, 5000):
                        self.library.probe_poll(milliseconds, context)
                    self.touch("TOUCHEVENT_RELEASE", 5160, 200, 400, context)
                    self.assertEqual(self.calls(), (0, 0))
                    self.assertEqual(self.library.probe_date_calls(), 0)
                    self.assertEqual(self.library.probe_summary_calls(), 0)
                    self.assertEqual(self.library.probe_extra(1), 0)
                    self.assertEqual(self.library.probe_extra(4), 0)

    def test_repeat_cancellation_on_context_target_lock_system_or_disable(self):
        context = self.constant("CONTEXT_STD")
        for reset in ("context", "target", "lock", "system", "disable"):
            with self.subTest(reset=reset):
                self.setUp()
                self.install(configuration(stroke_repeat=1))
                self.held_stroke(context)
                before = self.library.probe_extra(0)
                if reset == "context":
                    self.library.probe_poll(1000, self.constant("CONTEXT_WPS"))
                elif reset == "target":
                    self.library.probe_target(1)
                elif reset == "lock":
                    self.library.probe_poll(1000, context | self.constant("CONTEXT_LOCKED"))
                elif reset == "system":
                    self.process_pending(0x40000001)
                else:
                    self.library.probe_enable(False)
                self.library.probe_poll(2000, context)
                self.assertEqual(self.library.probe_extra(0), before)
                self.assertEqual(self.library.input_touch_pending(), 0)

    def test_custom_physical_hold_repeats_only_safe_context_actions(self):
        reader = self.constant("CONTEXT_STD") | self.constant("CONTEXT_CUSTOM") | self.constant("CONTEXT_CUSTOM2")
        cases = ((self.constant("CONTEXT_STD"), 1, "ACTION_STD_PREV", "ACTION_STD_PREVREPEAT"),
                 (self.constant("CONTEXT_TREE"), 2, "ACTION_STD_NEXT", "ACTION_STD_NEXTREPEAT"),
                 (reader, 3, "ACTION_STD_PREV", "ACTION_STD_PREVREPEAT"),
                 (reader, 1, "ACTION_SETTINGS_DEC", "ACTION_SETTINGS_DECREPEAT"),
                 (self.constant("CONTEXT_WPS"), 1, "ACTION_WPS_VOLUP", "ACTION_WPS_VOLUP"),
                 (self.constant("CONTEXT_STD"), 5, "ACTION_STD_OK", "ACTION_UNKNOWN"),
                 (self.constant("CONTEXT_SETTINGS"), 1, "ACTION_SETTINGS_INC", "ACTION_UNKNOWN"),
                 (self.constant("CONTEXT_KEYBOARD"), 3, "ACTION_KBD_LEFT", "ACTION_UNKNOWN"))
        for context, mapping, first, repeated in cases:
            with self.subTest(context=context, mapping=mapping):
                self.setUp()
                self.install(configuration(buttons={(1, 3): mapping}))
                self.library.probe_button(8, 0, context, False)
                self.assertEqual(self.library.probe_button(0, 700, context, False), self.constant(first))
                self.assertEqual(self.library.probe_button(8 | REPEAT, 800, context, False),
                                 self.constant(repeated))
                self.assertEqual(self.library.probe_button(8 | RELEASE, 900, context, False),
                                 self.constant("ACTION_UNKNOWN"))
                self.assertEqual(self.library.probe_button(0, 1200, context, False), -1)

    def test_time_field_repeat_is_consumed_by_the_actual_time_screen_switch(self):
        context = self.constant("CONTEXT_SETTINGS_TIME")
        for mapping, first, step in ((3, "ACTION_STD_PREV", -1), (4, "ACTION_STD_NEXT", 1)):
            for source in ("touch", "physical"):
                with self.subTest(mapping=mapping, source=source):
                    self.setUp()
                    self.install(configuration(stroke_repeat=1, replacements={1: mapping},
                                               buttons={(1, 3): mapping}))
                    if source == "touch":
                        action = self.held_stroke(context)
                    else:
                        self.library.probe_button(8, 0, context, False)
                        action = self.library.probe_button(0, 700, context, False)
                    self.assertEqual(action, self.constant(first))
                    cursor = self.library.input_time_consume(action, 2)
                    self.assertEqual(cursor, (2 + step) % 6)
                    for index in range(1, 8):
                        action = self.library.probe_poll(970 + 160 * index, context) if source == "touch" else \
                            self.library.probe_button(8 | REPEAT, 700 + 160 * index, context, False)
                        cursor = self.library.input_time_consume(action, cursor)
                        self.assertEqual(cursor, (2 + (index + 1) * step) % 6)

    def queue_destination(self, target, context):
        self.install(configuration(replacements={1: 12}, gesture_refs={1: target}))
        self.gesture("stroke", context)
        self.assertEqual(self.library.probe_navigation_requests(), 0)
        return self.process_pending(self.constant("ACTION_NONE"), context)

    def test_direct_destinations_request_root_screen_and_unwind_without_recursion(self):
        for target, screen in ((8, "GO_TO_FILEBROWSER"), (9, "GO_TO_DBBROWSER"), (10, "GO_TO_WPS"),
                               (11, "GO_TO_MAINMENU"), (12, "GO_TO_PLAYLISTS_SCREEN")):
            for context_name, expected in (("CONTEXT_STD", "ACTION_STD_MENU"),
                    ("CONTEXT_TREE", "ACTION_STD_MENU"), ("CONTEXT_WPS", "ACTION_WPS_MENU"),
                    ("CONTEXT_SETTINGS", "ACTION_STD_CANCEL")):
                with self.subTest(target=target, context=context_name):
                    self.setUp()
                    context = self.constant(context_name)
                    self.assertEqual(self.queue_destination(target, context), self.constant(expected))
                    self.assertEqual(self.library.probe_requested_screen(), self.constant(screen))
                    self.assertEqual(self.library.probe_navigation_requests(), 1)
                    self.assertEqual(self.library.probe_stat(13), 0)
                    self.assertEqual(self.library.probe_extra(2), 0)
                    self.assertEqual(self.library.probe_extra(4), 0)
                    self.assertEqual(self.library.accessibility_adjust_timeout(-1), 5)
                    self.assertEqual(self.process_pending(self.constant("ACTION_NONE"), context),
                                     self.constant(expected))
                    self.assertEqual(self.library.probe_navigation_requests(), 1)

    def test_direct_navigation_cannot_confirm_or_cancel_modal_editors(self):
        for name in ("CONTEXT_KEYBOARD", "CONTEXT_MORSE_INPUT", "CONTEXT_YESNOSCREEN"):
            with self.subTest(context=name):
                self.setUp()
                self.assertEqual(self.queue_destination(8, self.constant(name)), self.constant("ACTION_REDRAW"))
                self.assertEqual(self.library.probe_navigation_requests(), 0)
                self.assertEqual(self.library.probe_stat(7),
                                 self.constant("LANG_ACCESSIBILITY_DESTINATION_UNAVAILABLE"))
        for base in ("CONTEXT_STD", "CONTEXT_WPS", "CONTEXT_SETTINGS"):
            for flag in ("CONTEXT_CUSTOM", "CONTEXT_CUSTOM2", "CONTEXT_PLUGIN", "CONTEXT_LOCKED"):
                with self.subTest(base=base, flag=flag):
                    self.assertEqual(self.library.input_navigation_exit(
                        self.constant(base) | self.constant(flag)), self.constant("ACTION_NONE"))
        reader = self.constant("CONTEXT_STD") | self.constant("CONTEXT_CUSTOM") | self.constant("CONTEXT_CUSTOM2")
        self.assertEqual(self.library.input_navigation_exit(reader), self.constant("ACTION_STD_CANCEL"))

    def test_navigation_queue_passive_events_preserved_but_manual_and_usb_cancel(self):
        for event in PASSIVE_POWER_EVENTS + (0x40000001, 0x40000002):
            with self.subTest(event=hex(event)):
                self.setUp()
                context = self.constant("CONTEXT_STD")
                self.queue_destination(8, context)
                self.assertEqual(self.process_pending(event, context), 0)
                expected = "ACTION_STD_MENU" if event in PASSIVE_POWER_EVENTS else "ACTION_NONE"
                self.assertEqual(self.process_pending(self.constant("ACTION_NONE"), context), self.constant(expected))
        for source in ("physical", "touch", "action"):
            with self.subTest(source=source):
                self.setUp()
                context = self.constant("CONTEXT_STD")
                self.queue_destination(8, context)
                if source == "physical":
                    self.library.probe_button(8, 500, context, False)
                elif source == "touch":
                    self.touch("TOUCHEVENT_PRESS", 500)
                else:
                    self.process_pending(self.constant("ACTION_STD_NEXT"), context)
                self.assertEqual(self.process_pending(self.constant("ACTION_NONE"), context),
                                 self.constant("ACTION_NONE"))


if __name__ == "__main__":
    unittest.main()
