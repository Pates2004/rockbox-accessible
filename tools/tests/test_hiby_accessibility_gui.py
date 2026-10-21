"""Real Windows SDL HiBy R1 accessible-touch regression, never a product builder.

Wait for the build owner's explicit readiness and frozen executable hash:
  python -B tools/tests/test_hiby_accessibility_gui.py --build <D:/work/Workspace/rockbox/build>
    --build-ready --exe-sha256 <frozen-sha256> --language polski

--help and --self-test never start a simulator or consume a build/profile.
Acceptance uses foreground-verified native mouse input, HWND-scoped keys, synthesized output
and disk-driver mixer PCM. No manager, gesture recognizer or input API is mocked.
The existing fixture copies immutable runtime assets, not settings/resume data;
the development EXE is moved into that fixture and restored, never copied.
"""

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest

from test_hiby_r1_gui import R1Probe
from test_tts_bookmarks_gui import (
    has_speech, phrases, prepare_fixture, require, startup, verify_evidence, write_json,
)
from test_tts_recorder_gui import ExecutableLoan, contained, digest, display_labels
from test_tts_simulator import catalog_labels, find_window, windows_backend
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SUITE_DIRECTORY = ("r1-r34-20261011", "GUI")
TREE = "000 Accessibility"
FOLDERS = ("001 Alpha", "002 Beta", "003 Gamma")
MARKERS = tuple(folder + " marker" for folder in FOLDERS)
ACCESSIBILITY_CONFIG_VERSION = 11
ACCESSIBILITY_CONFIG_MAX = 4096
ACCESSIBILITY_MAX_PATH = 260
ACCESSIBILITY_LAUNCH_ACTION = 12
ACCESSIBILITY_PLUGIN_PREFIX = "/.rockbox/rocks/"
ACCESSIBILITY_PLUGIN_TARGET_BASE = 4
ACCESSIBILITY_PLUGIN_PATH_COUNT = 4
ACCESSIBILITY_GESTURE_COUNT = 20
ACCESSIBILITY_LEGACY_GESTURE_COUNT = 18
ACCESSIBILITY_SYSTEM_ACTION = 27
ACCESSIBILITY_DIRECT_LAUNCH_TARGETS = {
    8: "files", 9: "database", 10: "resume playback", 11: "settings", 12: "playlists",
}
ACCESSIBILITY_BUILTIN_LAUNCH_TARGETS = {
    0: "destination chooser", 1: "shortcuts", 2: "system information screens", 3: "application browser",
}
LABELS = (
    "LANG_DIR_BROWSER", "LANG_SETTINGS", "LANG_GENERAL_SETTINGS", "LANG_VOICE",
    "LANG_ACCESSIBILITY", "LANG_ACCESSIBILITY_ENABLED", "LANG_ACCESSIBILITY_GESTURES",
    "LANG_ACCESSIBILITY_UNASSIGNED", "LANG_ACCESSIBILITY_DOWN", "LANG_ACCESSIBILITY_UP",
    "LANG_ACCESSIBILITY_TRIAL", "LANG_ACCESSIBILITY_ROLLED_BACK", "LANG_KEYLOCK_ON",
    "LANG_KEYLOCK_OFF", "LANG_LEFT", "LANG_RIGHT", "LANG_RESET",
    "LANG_TTS", "LANG_ACCESSIBILITY_BUTTONS", "LANG_ACCESSIBILITY_SWIPE_LEFT",
    "LANG_ACCESSIBILITY_SWIPE_RIGHT", "LANG_KEYCLICK", "LANG_KEYCLICK_SOURCES",
    "LANG_KEYCLICK_BOTH", "LANG_KEYCLICK_PHYSICAL", "LANG_KEYCLICK_GESTURES",
)
SOURCE_PATHS = (
    "tools/tests/test_hiby_accessibility_gui.py", "tools/tests/test_hiby_r1_gui.py",
    "tools/tests/test_tts_bookmarks_gui.py", "tools/tests/test_tts_recorder_gui.py",
    "tools/tests/test_tts_simulator.py", "uisimulator/buttonmap/hiby-r1.c",
    "firmware/target/hosted/sdl/button-sdl.c", "firmware/target/hosted/sdl/sim-ui-defines.h",
    "firmware/export/config/hibyr1.h", "apps/action.c", "apps/accessibility.c",
    "apps/accessibility_gesture.c", "apps/gui/list.c", "apps/gui/bitmap/list.c",
    "apps/keymaps/keymap-hibyr1.c",
    "apps/accessibility_buttons.c", "apps/accessibility_buttons.h", "apps/misc.c",
    "apps/beep.c", "apps/menus/settings_menu.c", "apps/lang/english.lang", "apps/lang/polski.lang",
    "firmware/include/fs_defines.h", "firmware/export/rbpaths.h",
)
GEOMETRY = re.compile(
    r'^A11Y list geometry: parent=(-?\d+,-?\d+,\d+,\d+) '
    r'text=(-?\d+,-?\d+,\d+,\d+) title=(-?\d+,-?\d+,\d+,\d+) '
    r'line=(\d+) start=(\d+) y=(-?\d+) count=(\d+) selected=(-?\d+) group=(\d+)\s*$',
    re.MULTILINE,
)
DIRECTIONS = {
    "left": ((300, 400), (180, 400)),
    "right": ((180, 400), (300, 400)),
    "up": ((240, 500), (240, 380)),
    "down": ((240, 380), (240, 500)),
    "left-right": ((300, 400), (180, 400), (300, 400)),
    "right-left": ((180, 400), (300, 400), (180, 400)),
}
for _first in ("left", "right", "up", "down"):
    for _second in ("left", "right", "up", "down"):
        if _first == _second or _first + "-" + _second in DIRECTIONS:
            continue
        _start, _pivot = DIRECTIONS[_first]
        _second_start, _second_end = DIRECTIONS[_second]
        _end = tuple(_pivot[axis] + _second_end[axis] - _second_start[axis] for axis in (0, 1))
        DIRECTIONS[_first + "-" + _second] = (_start, _pivot, _end)
LABELS += tuple("LANG_ACCESSIBILITY_SWIPE_" + name.upper().replace("-", "_")
                for name in DIRECTIONS if name not in ("left", "right"))


@dataclass(frozen=True)
class ListGeometry:
    parent: tuple
    text: tuple
    title: tuple
    line: int
    start: int
    offset: int
    count: int
    selected: int
    group: int

    @classmethod
    def latest(cls, text):
        matches = list(GEOMETRY.finditer(text))
        require(bool(matches), "Missing real post-draw A11Y list geometry debug line; "
                "do not infer font/padding or use mocked list coordinates")
        values = matches[-1].groups()
        return cls(*(tuple(map(int, value.split(','))) for value in values[:3]),
                   *map(int, values[3:]))

    def point(self, item):
        require(self.line > 0 and self.group == 1 and 0 <= item < self.count,
                "Unsupported/invalid actual list geometry")
        point_x = self.text[0] + self.text[2] // 2
        point_y = self.text[1] + item * self.line - self.offset + self.line // 2
        for viewport in (self.parent, self.text):
            require(viewport[0] <= point_x < viewport[0] + viewport[2]
                    and viewport[1] <= point_y < viewport[1] + viewport[3],
                    "Requested row is not fully reachable in the actual viewport")
        return point_x, point_y


def packed_point(point):
    require(len(point) == 2 and all(isinstance(value, int) and 0 <= value < 32768 for value in point),
            "Mouse point is not a nonnegative signed-short client coordinate")
    return point[0] | (point[1] << 16)


def stroke_points(name, steps=10):
    require(name in DIRECTIONS and isinstance(steps, int) and 4 <= steps <= 30,
            "Invalid stroke or interpolation step count")
    vertices = DIRECTIONS[name]
    result = [vertices[0]]
    for first, second in zip(vertices, vertices[1:]):
        for index in range(1, steps + 1):
            result.append(tuple(round(first[axis] + (second[axis] - first[axis]) * index / steps)
                                for axis in (0, 1)))
    return result


def launch_path_valid(path):
    if not isinstance(path, str):
        return False
    encoded = path.encode("utf-8", errors="surrogateescape")
    if len(encoded) >= ACCESSIBILITY_MAX_PATH or any(byte < 32 or byte in (92, 127) for byte in encoded):
        return False
    if not path:
        return True
    return (path.startswith(ACCESSIBILITY_PLUGIN_PREFIX)
            and len(encoded) > len(ACCESSIBILITY_PLUGIN_PREFIX) + 5
            and path.endswith(".rock") and not any(part in path for part in ("/../", "/./", "//")))


def parse_accessibility_config(data):
    require(isinstance(data, bytes) and 0 < len(data) <= ACCESSIBILITY_CONFIG_MAX,
            "Missing/oversized persisted accessibility config")
    text = data.decode("utf-8", errors="surrogateescape")
    require(text.endswith("\n"), "Persisted accessibility config lacks its final newline")
    lines = text[:-1].split("\n")
    require(len(lines) >= 2 and lines[0] in tuple(f"RBACCESSIBILITY:{version}" for version in
                                              range(1, ACCESSIBILITY_CONFIG_VERSION + 1))
            and lines[1] in ("enabled:0", "enabled:1"),
            "Unexpected persisted accessibility config header/length")
    version = int(lines[0].rsplit(":", 1)[1])
    legacy = version == 1
    bindings = version >= 3
    current = version >= 7
    gesture_count = ACCESSIBILITY_GESTURE_COUNT if current else ACCESSIBILITY_LEGACY_GESTURE_COUNT
    launch_max = max(ACCESSIBILITY_DIRECT_LAUNCH_TARGETS) if current else 7
    require(len(lines) == {1: 20, 2: 42, 3: 46, 4: 46, 5: 46, 6: 46, 7: 50, 8: 52, 9: 72, 10: 92, 11: 92}[version],
            "Incomplete/extra persisted config rows")
    system_action = {1: 15, 2: 15, 3: 15, 4: 16, 5: 17, 6: 19,
                     7: 22, 8: 22, 9: 22, 10: 22, 11: ACCESSIBILITY_SYSTEM_ACTION}[version]
    result = {"enabled": lines[1] == "enabled:1", "gestures": {},
              "buttons": {(button, slot): system_action for button in range(5) for slot in range(4)},
              "gesture_launch": {slot: 0 for slot in range(1, gesture_count + 1)},
              "button_launch": {(button, slot): 0 for button in range(5) for slot in range(4)},
              "launch_paths": {target: "" for target in range(ACCESSIBILITY_PLUGIN_PATH_COUNT)},
              "click_sources": 7, "hold_ms": 700, "touch_hold_ms": 900,
              "stroke_repeat": False, "empty_pitch": True, "empty_semitones": -4, "version": version}
    start = 2
    if not legacy:
        click = re.fullmatch(r'click:([0-7])' if version >= 8 else r'click:([1-3])', lines[2])
        hold = re.fullmatch(r'hold:([1-9][0-9]*)', lines[3])
        require(click is not None and hold is not None, "Malformed input feedback/hold settings")
        result.update(click_sources=int(click[1]), hold_ms=int(hold[1]))
        require(300 <= result["hold_ms"] <= 2000 and result["hold_ms"] % 100 == 0,
                "Invalid global hold time")
        start = 4
    if current:
        touch_hold = re.fullmatch(r'touch_hold:([1-9][0-9]*)', lines[4])
        stroke_repeat = re.fullmatch(r'stroke_repeat:([01])', lines[5])
        require(touch_hold is not None and stroke_repeat is not None, "Malformed touch hold/repeat settings")
        result.update(touch_hold_ms=int(touch_hold[1]), stroke_repeat=stroke_repeat[1] == "1")
        require(300 <= result["touch_hold_ms"] <= 2000 and result["touch_hold_ms"] % 100 == 0,
                "Invalid touch hold time")
        start = 6
    if version >= 8:
        empty_pitch = re.fullmatch(r'empty_pitch:([01])', lines[6])
        empty_semitones = re.fullmatch(r'empty_semitones:(0|-?[1-9][0-9]*)', lines[7])
        require(empty_pitch is not None and empty_semitones is not None and
                -12 <= int(empty_semitones[1]) <= 12, "Malformed empty-space pitch settings")
        result.update(empty_pitch=empty_pitch[1] == "1", empty_semitones=int(empty_semitones[1]))
        start = 8
    for slot, line in enumerate(lines[start:start + gesture_count], 1):
        pattern = r'gesture:([1-9][0-9]*):(0|[1-9][0-9]*)' + (r':(0|[1-9][0-9]*)' if bindings else '')
        match = re.fullmatch(pattern, line)
        require(match is not None, "Malformed persisted gesture mapping")
        actual_slot, action = map(int, match.groups()[:2])
        require(actual_slot == slot and 0 <= action <= (10 if legacy else system_action - 1),
                "Invalid/duplicate/out-of-order persisted gesture mapping")
        result["gestures"][slot] = action
        if bindings:
            target = int(match[3])
            require(target <= launch_max, "Invalid gesture launch destination")
            result["gesture_launch"][slot] = target
    result["playback_gestures"] = dict(result["gestures"])
    result["playback_gesture_launch"] = dict(result["gesture_launch"])
    button_start = start + gesture_count
    if version >= 10:
        for slot, line in enumerate(lines[button_start:button_start + gesture_count], 1):
            match = re.fullmatch(r'playback_gesture:([1-9][0-9]*):(0|[1-9][0-9]*):(0|[1-9][0-9]*)', line)
            require(match is not None, "Malformed persisted playback gesture mapping")
            actual_slot, action, target = map(int, match.groups())
            require(actual_slot == slot and action < system_action and target <= launch_max,
                    "Invalid/duplicate/out-of-order playback gesture mapping")
            result["playback_gestures"][slot] = action
            result["playback_gesture_launch"][slot] = target
        button_start += gesture_count
    if not legacy:
        for index, line in enumerate(lines[button_start:button_start + 20]):
            pattern = r'button:([0-4]):([0-3]):(0|[1-9][0-9]*)' + (r':(0|[1-9][0-9]*)' if bindings else '')
            match = re.fullmatch(pattern, line)
            require(match is not None, "Malformed persisted physical mapping")
            button, slot, action = map(int, match.groups()[:3])
            require((button, slot) == divmod(index, 4) and action <= system_action,
                    "Invalid/duplicate/out-of-order persisted physical mapping")
            result["buttons"][(button, slot)] = action
            if bindings:
                target = int(match[4])
                require(target <= launch_max, "Invalid physical launch destination")
                result["button_launch"][(button, slot)] = target
    result["playback_buttons"] = dict(result["buttons"])
    result["playback_button_launch"] = dict(result["button_launch"])
    target_start = button_start + 20
    if version >= 9:
        for index, line in enumerate(lines[target_start:target_start + 20]):
            match = re.fullmatch(r'playback_button:([0-4]):([0-3]):(0|[1-9][0-9]*):(0|[1-9][0-9]*)', line)
            require(match is not None, "Malformed persisted playback physical mapping")
            button, slot, action, target = map(int, match.groups())
            require((button, slot) == divmod(index, 4) and action <= system_action and target <= launch_max,
                    "Invalid/duplicate/out-of-order persisted playback physical mapping")
            result["playback_buttons"][(button, slot)] = action
            result["playback_button_launch"][(button, slot)] = target
        target_start += 20
    if bindings:
        for target, line in enumerate(lines[target_start:]):
            match = re.fullmatch(r'target:([0-3]):(.*)', line)
            require(match is not None and int(match[1]) == target, "Invalid/duplicate/out-of-order launch path pool")
            path = match[2]
            require(launch_path_valid(path), "Unsafe/oversized plugin launch path")
            result["launch_paths"][target] = path
        for actions, targets in ((result["gestures"], result["gesture_launch"]),
                                (result["playback_gestures"], result["playback_gesture_launch"]),
                                (result["buttons"], result["button_launch"]),
                                (result["playback_buttons"], result["playback_button_launch"])):
            for slot, target in targets.items():
                require(target == 0 or actions[slot] == ACCESSIBILITY_LAUNCH_ACTION,
                        "Non-launch action has a launch destination")
                if ACCESSIBILITY_PLUGIN_TARGET_BASE <= target < (ACCESSIBILITY_PLUGIN_TARGET_BASE
                                                                 + ACCESSIBILITY_PLUGIN_PATH_COUNT):
                    require(bool(result["launch_paths"][target - ACCESSIBILITY_PLUGIN_TARGET_BASE]),
                            "Plugin launch reference points to an empty path slot")
    return result


def parse_bindings(data):
    return parse_accessibility_config(data)["gestures"]


def spoken_row(text, label):
    return any(phrase == label or phrase.startswith(label + ":")
               for phrase in phrases(text)) and any(
                   phrase == label or phrase.startswith((label + ":", label + " "))
                   for phrase in phrases(text, "TTS utterance"))


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]


class KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ctypes.c_size_t)]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16),
                ("wParamH", ctypes.c_uint16)]


class NativeInputData(ctypes.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]


class NativeInput(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", ctypes.c_uint32), ("data", NativeInputData)]


def assert_no_activation(text):
    spoken = " ".join(phrases(text) + phrases(text, "TTS utterance"))
    require(not any(marker in spoken for marker in MARKERS),
            "Touch exploration unexpectedly activated a folder")
    require(not re.search(r'^TTS reader (?:cursor|state):', text, re.MULTILINE),
            "Touch exploration unexpectedly opened the text reader")


def inventory(build):
    result = {}
    for path in sorted(build.rglob('*')):
        contained(path, build)
        if path.is_file():
            metadata = path.stat()
            result[path.relative_to(build).as_posix()] = {
                "sha256": digest(path), "bytes": metadata.st_size,
                "mtime_ns": metadata.st_mtime_ns,
            }
    return result


class MouseBackend:
    def __init__(self, probe):
        self.probe = probe
        self.native = windows_backend()
        require(self.native is not None, "Mouse acceptance requires native Windows")
        self.native.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.native.user32.GetClientRect.restype = wintypes.BOOL
        for name, result, parameters in (
            ("ClientToScreen", wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]),
            ("ScreenToClient", wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]),
            ("GetCursorPos", wintypes.BOOL, [ctypes.POINTER(wintypes.POINT)]),
            ("SetCursorPos", wintypes.BOOL, [ctypes.c_int, ctypes.c_int]),
            ("GetForegroundWindow", wintypes.HWND, []),
            ("SetForegroundWindow", wintypes.BOOL, [wintypes.HWND]),
            ("WindowFromPoint", wintypes.HWND, [wintypes.POINT]),
            ("GetAsyncKeyState", ctypes.c_short, [ctypes.c_int]),
            ("SendInput", wintypes.UINT,
             [wintypes.UINT, ctypes.POINTER(NativeInput), ctypes.c_int]),
        ):
            function = getattr(self.native.user32, name)
            function.restype = result
            function.argtypes = parameters
        self.down = False
        self.last_point = (240, 400)
        self.origin = time.perf_counter()
        self.original_foreground = self.native.user32.GetForegroundWindow()
        self.original_cursor = self.cursor()
        self.last_screen_point = None
        self.restored = False
        require(not (self.native.user32.GetAsyncKeyState(0x01) & 0x8000),
                "Refusing to interfere with an already held physical mouse button")
        self.focus()

    def cursor(self):
        point = wintypes.POINT()
        if not self.native.user32.GetCursorPos(ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        return point.x, point.y

    def focus(self):
        require(self.native.owns_window(self.probe.process.pid, self.probe.window),
                "Refusing to focus an unowned window")
        self.native.user32.ShowWindowAsync(self.probe.window, 9)
        self.native.user32.SetForegroundWindow(self.probe.window)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.probe.check_alive()
            if self.native.user32.GetForegroundWindow() == self.probe.window:
                return
            time.sleep(0.025)
        raise AssertionError("Windows refused foreground focus; no global input was sent")

    def require_focus(self):
        self.probe.check_alive()
        require(self.native.owns_window(self.probe.process.pid, self.probe.window)
                and self.native.user32.GetForegroundWindow() == self.probe.window,
                "Owned SDL window lost foreground focus; refusing global input")

    def extent(self):
        require(self.native.owns_window(self.probe.process.pid, self.probe.window),
                "Mouse window is not owned by the test process")
        rectangle = wintypes.RECT()
        if not self.native.user32.GetClientRect(self.probe.window, ctypes.byref(rectangle)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rectangle.right - rectangle.left, rectangle.bottom - rectangle.top

    def post(self, message, point, buttons):
        self.require_focus()
        require(self.last_screen_point is None or self.cursor() == self.last_screen_point,
                "Cursor moved externally during the exclusive mouse test; refusing further input")
        width, height = self.extent()
        require(0 <= point[0] < width and 0 <= point[1] < height,
                "Mouse point escapes owned SDL client")
        screen_point = wintypes.POINT(*point)
        if not self.native.user32.ClientToScreen(self.probe.window, ctypes.byref(screen_point)):
            raise ctypes.WinError(ctypes.get_last_error())
        require(message in (0x0200, 0x0201, 0x0202), "Unsupported native mouse operation")
        require(buttons == (1 if message == 0x0201 or (message == 0x0200 and self.down) else 0),
                "Mouse flags disagree with owned press state")
        packed_point(point)
        if not self.native.user32.SetCursorPos(screen_point.x, screen_point.y):
            raise ctypes.WinError(ctypes.get_last_error())
        self.last_screen_point = (screen_point.x, screen_point.y)
        require(self.cursor() == self.last_screen_point, "Global cursor did not reach the requested SDL client point")
        translated = wintypes.POINT(*self.cursor())
        if not self.native.user32.ScreenToClient(self.probe.window, ctypes.byref(translated)):
            raise ctypes.WinError(ctypes.get_last_error())
        require((translated.x, translated.y) == point, "DPI/client-to-screen mouse roundtrip differs")
        under_pointer = self.native.user32.WindowFromPoint(screen_point)
        require(self.native.owns_window(self.probe.process.pid, under_pointer),
                "SDL client point is obscured or outside the desktop; refusing button injection")
        self.require_focus()
        if message != 0x0200:
            event = NativeInput(type=0)
            event.mi.dwFlags = 0x0002 if message == 0x0201 else 0x0004
            if self.native.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
                raise RuntimeError("SendInput rejected native mouse button input (possibly UIPI)")
        self.last_point = point
        self.probe.report["input_events"].append({
            "seconds": time.perf_counter() - self.origin, "pid": self.probe.process.pid,
            "hwnd": int(self.probe.window), "message": message,
            "point": list(point), "buttons": buttons,
            "screen_point": [screen_point.x, screen_point.y],
            "foreground_verified": True, "cursor_roundtrip_verified": True,
            "backend": "SetCursorPos + SendInput; owned foreground and unobscured client verified",
        })

    def restore(self):
        if self.restored:
            return
        self.release()
        record = {"original_cursor": list(self.original_cursor), "restored": False}
        if self.last_screen_point is not None and self.cursor() == self.last_screen_point:
            if not self.native.user32.SetCursorPos(*self.original_cursor):
                raise ctypes.WinError(ctypes.get_last_error())
            record["restored"] = True
        else:
            record["reason"] = "Cursor moved externally; do not override user's position"
        if self.native.user32.GetForegroundWindow() == self.probe.window and self.original_foreground:
            record["foreground_restore_requested"] = bool(
                self.native.user32.SetForegroundWindow(self.original_foreground))
        self.probe.session["desktop_input_cleanup"] = record
        self.restored = True

    def press(self, point):
        require(not self.down, "Previous owned mouse press remains held")
        self.post(0x0200, point, 0)
        time.sleep(0.025)
        self.post(0x0201, point, 1)
        self.down = True

    def move(self, point):
        self.post(0x0200, point, 1 if self.down else 0)

    def release(self):
        if self.down:
            try:
                self.post(0x0202, self.last_point, 0)
            except Exception:
                event = NativeInput(type=0)
                event.mi.dwFlags = 0x0004
                released = self.native.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) == 1
                self.probe.session["emergency_mouse_release"] = {"released": released}
                self.down = not released
                raise
            else:
                self.down = False

    def tap(self, point, hold=0.055):
        self.press(point)
        try:
            time.sleep(hold)
        finally:
            self.release()

    def double_tap(self):
        self.tap((350, 650))
        time.sleep(0.085)
        self.tap((120, 650))

    def swipe(self, name):
        points = stroke_points(name)
        self.press(points[0])
        try:
            for point in points[1:]:
                time.sleep(0.012)
                self.move(point)
            time.sleep(0.02)
        finally:
            self.release()


class AccessibilityProbe(R1Probe):
    def __init__(self, *arguments):
        super().__init__(*arguments)
        self.mouse = None
        self.selection_text = ""

    def capture(self, *arguments, **keywords):
        observation = super().capture(*arguments, **keywords)
        selection = self.text(observation["log_start"])
        if phrases(selection):
            self.selection_text = selection
        return observation

    def seek(self, label, start=0, maximum=35):
        selection = self.text(start) if start else self.selection_text
        for attempt in range(maximum):
            if spoken_row(selection, label):
                return
            observation = self.capture(f"seek exact row {label}: Down {attempt + 1}",
                                       lambda: self.press("Down"),
                                       lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
            selection = self.text(observation["log_start"])
        raise AssertionError(f"Cannot find exact spoken row: {label!r}")

    def launch(self, name):
        require(self.process is None or self.process.poll() is not None, "Previous owned process still runs")
        require(not self.log.exists(), "Refusing to overwrite an earlier simulator log")
        require((self.runtime / ".tts-bookmarks-gui-fixture.json").is_file(), "Missing isolated fixture marker")
        executable = contained(self.runtime / "rockboxui.exe", self.results)
        windows_backend().ensure_unused(executable)
        self.environment = dict(os.environ, SDL_VIDEODRIVER="windows", SDL_AUDIODRIVER="disk",
                                SDL_DISKAUDIOFILE=str(self.runtime / (name + "-audio.raw")),
                                SDL_DISKAUDIODELAY="12")
        self.session = {"name": name, "pcm": self.environment["SDL_DISKAUDIOFILE"], "checks": []}
        self.report["sessions"].append(self.session)
        command = [str(executable), "--root", str(self.runtime / "simdisk"), "--audiodev",
                   self.environment["SDL_DISKAUDIOFILE"], "--nobackground", "--zoom", "1",
                   "--debugbuttons", "--debugwps"]
        self.session["command"] = command
        self.process = subprocess.Popen(command, cwd=self.runtime, env=self.environment,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        self.session["pid"] = self.process.pid
        self.window = find_window(self.process.pid, self.environment)
        self.mouse = MouseBackend(self)
        self.session["client_extent"] = list(self.mouse.extent())
        require(self.mouse.extent() == (480, 800), "SDL client/LCD coordinate scale differs from 1:1")

    def geometry(self):
        return ListGeometry.latest(self.text())

    def observe(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.check_alive()
            require("TTS: synthesis failed" not in self.text(), "Synthesis failed during observation")
            time.sleep(min(0.03, max(0, deadline - time.monotonic())))

    def quiet_input(self, name, action, duration=0.9, *, allow_lock=False):
        marker = self.mark()
        observation = {"name": name, "status": "in_progress", "session": self.session["name"],
                       "speech_required": False, "log_start": marker}
        self.report["checks"].append(observation)
        self.session["checks"].append(name)
        try:
            action()
            self.observe(duration)
            text = self.text(marker)
            assert_no_activation(text)
            spoken = phrases(text)
            if allow_lock:
                lock = self.report["labels"]["LANG_KEYLOCK_ON"]
                require(all(lock in phrase for phrase in spoken), "Locked touch changed spoken focus")
            else:
                require(not spoken and not phrases(text, "TTS utterance"), "Unassigned touch was not a no-op")
            observation["status"] = "passed"
        except Exception as error:
            observation.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            observation.update(log_end=self.mark(), segments=phrases(self.text(marker)),
                               utterances=phrases(self.text(marker), "TTS utterance"))
        return observation

    def prompt(self, name, action, label):
        observation = self.capture(name, action, lambda text: has_speech(text, (label,)), settle=False)
        self.observe(0.45)
        pcm = Path(self.session["pcm"])
        observation.update(log_end=self.mark(), pcm_end=pcm.stat().st_size if pcm.exists() else 0)
        return observation

    def close(self, graceful=True):
        try:
            if self.mouse is not None:
                self.mouse.restore()
        finally:
            super().close(graceful=graceful)


def enter_tree(probe, labels):
    probe.seek(labels["LANG_DIR_BROWSER"])
    opened = probe.capture("open Files using physical Power", lambda: probe.press("space"),
                           lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    latest = opened["segments"][-1] if opened["segments"] else ""
    already_inside = (probe.geometry().count == 3 and any(folder in latest for folder in FOLDERS)
                      and not any(marker in latest for marker in MARKERS))
    if not already_inside:
        probe.seek(TREE)
        probe.capture("open synthetic three-folder tree", lambda: probe.press("space"),
                      lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    for index in range(3):
        if probe.geometry().selected == 0:
            break
        probe.capture(f"restore Alpha tree focus {index + 1}", lambda: probe.press("Up"),
                      lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    geometry = probe.geometry()
    require(geometry.count == 3 and geometry.selected == 0,
            "Unexpected synthetic folder list count/focus")
    return geometry


def defaults(probe, labels):
    geometry = enter_tree(probe, labels)
    marker = probe.mark()
    probe.speech("held finger explores Alpha without activation", lambda: probe.mouse.press(geometry.point(0)), FOLDERS[0])
    probe.speech("unlifted finger explores Beta without activation", lambda: probe.mouse.move(geometry.point(1)), FOLDERS[1])
    probe.mouse.release()
    probe.observe(0.6)
    assert_no_activation(probe.text(marker))
    probe.speech("Left swipe moves focus up", lambda: probe.mouse.swipe("left"), FOLDERS[0])
    probe.speech("Right swipe moves focus down", lambda: probe.mouse.swipe("right"), FOLDERS[1])
    marker = probe.mark()
    started = time.perf_counter()
    probe.mouse.tap(geometry.point(0))
    probe.observe(0.12)
    require(not phrases(probe.text(marker)) and not phrases(probe.text(marker), "TTS utterance"),
            "Single tap spoke before the double-tap decision window")
    observation = probe.capture("single tap is deferred, spoken and never activated", None,
                                lambda text: has_speech(text, (FOLDERS[0],)), start=marker)
    observation["elapsed_seconds"] = time.perf_counter() - started
    assert_no_activation(probe.text(marker))
    probe.speech("Right swipe restores Beta focus", lambda: probe.mouse.swipe("right"), FOLDERS[1])
    probe.speech("double tap elsewhere activates current Beta, not touched coordinates",
                 probe.mouse.double_tap, MARKERS[1])
    probe.speech("Up swipe goes back", lambda: probe.mouse.swipe("up"), FOLDERS[1])
    probe.speech("Left swipe selects Alpha", lambda: probe.mouse.swipe("left"), FOLDERS[0])
    probe.speech("Down swipe activates Alpha", lambda: probe.mouse.swipe("down"), MARKERS[0])
    probe.speech("Left-Right stroke goes back", lambda: probe.mouse.swipe("left-right"), FOLDERS[0])
    probe.speech("Power plus Volume Up locks", lambda: probe.unit_chord("Up"), labels["LANG_KEYLOCK_ON"])
    probe.quiet_input("locked Right swipe suppressed", lambda: probe.mouse.swipe("right"), allow_lock=True)
    probe.quiet_input("locked double tap suppressed", probe.mouse.double_tap, allow_lock=True)
    probe.quiet_input("locked exploration suppressed", lambda: probe.mouse.tap(geometry.point(1)), allow_lock=True)
    probe.speech("Power plus Volume Up unlocks", lambda: probe.unit_chord("Up"), labels["LANG_KEYLOCK_OFF"])
    probe.speech("unlocked Right swipe moves exactly once", lambda: probe.mouse.swipe("right"), FOLDERS[1])
    probe.speech("Right-Left stroke returns Home", lambda: probe.mouse.swipe("right-left"), labels["LANG_DIR_BROWSER"])
    probe.report["completed_scenarios"].append("default-touch-navigation-and-lock")


def enter_editor(probe, labels):
    probe.seek(labels["LANG_SETTINGS"])
    probe.capture("open Settings", lambda: probe.press("space"),
                  lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    probe.seek(labels["LANG_GENERAL_SETTINGS"])
    probe.capture("open General Settings", lambda: probe.press("space"),
                  lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    probe.seek(labels["LANG_VOICE"])
    probe.speech("open Accessibility with eSpeak first", lambda: probe.press("space"), labels["LANG_TTS"])
    probe.seek(labels["LANG_ACCESSIBILITY"])
    probe.speech("open Touchscreen settings", lambda: probe.press("space"), labels["LANG_ACCESSIBILITY_ENABLED"])
    probe.seek(labels["LANG_ACCESSIBILITY_GESTURES"])
    probe.speech("open gesture editor", lambda: probe.press("space"),
                 labels["LANG_ACCESSIBILITY_SWIPE_LEFT"], labels["LANG_ACCESSIBILITY_UP"])
    probe.seek(labels["LANG_ACCESSIBILITY_SWIPE_RIGHT"])


def choose_binding(probe, labels, identifier):
    probe.capture("open Right gesture action choices", lambda: probe.press("space"),
                  lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    probe.seek(labels[identifier], maximum=20)
    return probe.prompt("apply candidate enters timed trial", lambda: probe.press("space"),
                        labels["LANG_ACCESSIBILITY_TRIAL"])


def leave_editor(probe, labels):
    for index in range(10):
        if spoken_row(probe.selection_text, labels["LANG_DIR_BROWSER"]):
            return
        if spoken_row(probe.selection_text, labels["LANG_SETTINGS"]):
            probe.seek(labels["LANG_DIR_BROWSER"])
            return
        probe.capture(f"physical Back leaves editor level {index + 1}", lambda: probe.press("Left"),
                      lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    raise AssertionError("Editor Back navigation did not return to the spoken Files root row")


def editor(probe, labels):
    enter_editor(probe, labels)
    choose_binding(probe, labels, "LANG_ACCESSIBILITY_UNASSIGNED")
    probe.speech("physical Power confirms Unassigned mapping", lambda: probe.press("space"),
                 labels["LANG_ACCESSIBILITY_SWIPE_RIGHT"], labels["LANG_ACCESSIBILITY_UNASSIGNED"])
    config = probe.runtime / "simdisk/.rockbox/accessibility.cfg"
    require(config.is_file() and parse_bindings(config.read_bytes())[2] == 0,
            "Confirmed Right gesture was not persisted as Unassigned")
    saved = config.read_bytes()
    choose_binding(probe, labels, "LANG_ACCESSIBILITY_DOWN")
    probe.speech("unconfirmed trial automatically rolls back", None, labels["LANG_ACCESSIBILITY_ROLLED_BACK"])
    require(config.read_bytes() == saved and parse_bindings(config.read_bytes())[2] == 0,
            "Timed trial changed the last confirmed persistent mapping")
    leave_editor(probe, labels)
    enter_tree(probe, labels)
    probe.quiet_input("confirmed Unassigned Right stroke remains a no-op after rollback",
                      lambda: probe.mouse.swipe("right"))
    probe.speech("physical Down proves Unassigned did not move focus", lambda: probe.press("Down"), FOLDERS[1])
    probe.speech("Home remains usable with Right Unassigned", lambda: probe.mouse.swipe("right-left"),
                 labels["LANG_DIR_BROWSER"])
    enter_editor(probe, labels)
    choose_binding(probe, labels, "LANG_ACCESSIBILITY_DOWN")
    probe.speech("physical Power restores default Right mapping", lambda: probe.press("space"),
                 labels["LANG_ACCESSIBILITY_SWIPE_RIGHT"], labels["LANG_ACCESSIBILITY_DOWN"])
    require(parse_bindings(config.read_bytes())[2] == 2, "Restored Right mapping was not persisted")
    leave_editor(probe, labels)
    enter_tree(probe, labels)
    probe.speech("restored default Right gesture works", lambda: probe.mouse.swipe("right"), FOLDERS[1])
    probe.report["completed_scenarios"].append("editor-unassigned-and-timed-rollback")


class HarnessUnitTests(unittest.TestCase):
    def test_spoken_rows_accept_windows_line_endings_without_partial_label_matches(self):
        for newline in ('\n', '\r\n'):
            text = 'TTS: Files' + newline + 'TTS utterance: Files' + newline
            self.assertTrue(spoken_row(text, 'Files'))
            self.assertFalse(spoken_row(text, 'File'))

    def test_phrase_parser_preserves_real_trailing_spaces(self):
        self.assertEqual(phrases('TTS: Name  \r\n'), ['Name  '])

    def current_config(self):
        from test_keyclick_gui import accessibility_configuration
        return accessibility_configuration(3, version=3).decode("utf-8")

    def config_for_version(self, version, sources=3):
        from test_keyclick_gui import accessibility_configuration
        if version in (1, 2):
            text = f"RBACCESSIBILITY:{version}\nenabled:1\n"
            if version == 2:
                text += f"click:{sources}\nhold:700\n"
            text += ''.join(f"gesture:{slot}:0\n" for slot in range(1, 19))
            if version == 2:
                text += ''.join(f"button:{button}:{slot}:15\n" for button in range(5) for slot in range(4))
            return text
        if version in (8, 9, 10, 11):
            text = (accessibility_configuration(3, version=7).decode("ascii")
                    .replace("RBACCESSIBILITY:7\n", f"RBACCESSIBILITY:{version}\n", 1)
                    .replace("click:3\n", f"click:{sources}\n", 1)
                    .replace("stroke_repeat:0\n", "stroke_repeat:0\nempty_pitch:1\nempty_semitones:-4\n", 1))
            if version >= 10:
                gestures = ''.join(line.replace("gesture:", "playback_gesture:", 1) + "\n"
                                   for line in text.splitlines() if line.startswith("gesture:"))
                text = text.replace("button:0:0:", gestures + "button:0:0:", 1)
            if version >= 9:
                playback = ''.join(line.replace("button:", "playback_button:", 1) + "\n"
                                   for line in text.splitlines() if line.startswith("button:"))
                text = text.replace("target:0:\n", playback + "target:0:\n", 1)
            if version >= 11:
                text = re.sub(r'^(button:[0-4]:[0-3]:|playback_button:[0-4]:[0-3]:)22:',
                              r'\g<1>27:', text, flags=re.MULTILINE)
            return text
        return accessibility_configuration(sources, version=version).decode("ascii")

    def test_pinned_config_contract_matches_current_manager_source(self):
        from test_accessibility_services_gui import enum_values
        source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        header = re.search(r'#define ACCESSIBILITY_HEADER "RBACCESSIBILITY:([1-9][0-9]*)\\n"', source)
        maximum = re.search(r'#define ACCESSIBILITY_CONFIG_MAX ([1-9][0-9]*)u?\b', source)
        paths = re.search(r'#define ACCESSIBILITY_LAUNCH_PATHS ([1-9][0-9]*)\b', source)
        self.assertIsNotNone(header)
        self.assertIsNotNone(maximum)
        self.assertIsNotNone(paths)
        self.assertEqual(int(header[1]), ACCESSIBILITY_CONFIG_VERSION)
        self.assertEqual(int(maximum[1]), ACCESSIBILITY_CONFIG_MAX)
        self.assertEqual(int(paths[1]), ACCESSIBILITY_PLUGIN_PATH_COUNT)
        actions = enum_values(source, "accessibility_action")
        self.assertEqual(actions["ACCESSIBILITY_ACTION_LAUNCH"], ACCESSIBILITY_LAUNCH_ACTION)
        self.assertEqual(actions["ACCESSIBILITY_ACTION_SYSTEM"], ACCESSIBILITY_SYSTEM_ACTION)
        self.assertEqual([actions["ACCESSIBILITY_ACTION_" + name]
                          for name in ("TOGGLE_TOUCH", "DATE", "SUMMARY")], [19, 20, 21])
        strokes = enum_values((ROOT / "apps/accessibility_gesture.h").read_text(encoding="utf-8"),
                              "accessibility_stroke")
        self.assertEqual(strokes["ACCESSIBILITY_STROKE_COUNT"] + 3, ACCESSIBILITY_GESTURE_COUNT)
        self.assertEqual(strokes["ACCESSIBILITY_STROKE_COUNT"] + 1, ACCESSIBILITY_LEGACY_GESTURE_COUNT)
        self.assertIn("result->click_sources = KEYCLICK_SOURCE_ALL;", source)
        self.assertIn("result->empty_pitch = true;", source)
        self.assertIn("result->empty_semitones = -4;", source)
        for definition in (
                "ACCESSIBILITY_SLOT_COUNT (ACCESSIBILITY_STROKE_COUNT + 4)",
                "ACCESSIBILITY_LEGACY_SLOT_COUNT (ACCESSIBILITY_STROKE_COUNT + 2)",
                "ACCESSIBILITY_TOUCH_HOLD_MIN 300u", "ACCESSIBILITY_TOUCH_HOLD_MAX 2000u",
                "ACCESSIBILITY_LAUNCH_PLUGIN_BASE 4", "ACCESSIBILITY_LAUNCH_FILES 8u",
                "ACCESSIBILITY_LAUNCH_DATABASE 9u", "ACCESSIBILITY_LAUNCH_RESUME 10u",
                "ACCESSIBILITY_LAUNCH_SETTINGS 11u", "ACCESSIBILITY_LAUNCH_PLAYLISTS 12u"):
            self.assertIn("#define " + definition, source)
        filesystem = (ROOT / "firmware/include/fs_defines.h").read_text(encoding="utf-8")
        self.assertEqual(int(re.search(r'#define MAX_PATH\s+([1-9][0-9]*)\b', filesystem)[1]),
                         ACCESSIBILITY_MAX_PATH)

    def test_global_mouse_input_requires_process_owned_foreground(self):
        for owned, foreground in ((False, 77), (True, 88)):
            with self.subTest(owned=owned, foreground=foreground):
                backend = object.__new__(MouseBackend)
                backend.probe = SimpleNamespace(process=SimpleNamespace(pid=123), window=77,
                                                check_alive=lambda: None)
                backend.native = SimpleNamespace(owns_window=lambda pid, window: owned,
                                                  user32=SimpleNamespace(GetForegroundWindow=lambda: foreground))
                with self.assertRaises(AssertionError):
                    backend.require_focus()

    def test_sendinput_uses_complete_native_union_layout(self):
        self.assertEqual(ctypes.sizeof(NativeInput), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.assertEqual(NativeInput.data.offset, 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4)
        event = NativeInput(type=0)
        event.mi.dwFlags = 0x0002
        self.assertEqual(event.mi.dwFlags, 0x0002)

    def test_exact_rows_do_not_confuse_directions_and_compound_swipes(self):
        valid = "TTS: Swipe right\nTTS: Down\nTTS utterance: Swipe right\nTTS utterance: Down\n"
        self.assertTrue(spoken_row(valid, "Swipe right"))
        self.assertTrue(spoken_row("TTS: Swipe right\nTTS: Down\nTTS utterance: Swipe right Down\n",
                                   "Swipe right"))
        self.assertFalse(spoken_row(valid, "Right"))
        self.assertFalse(spoken_row(valid.replace("Swipe right", "Swipe right, then left"), "Swipe right"))
        self.assertFalse(spoken_row("TTS: Swipe right\n", "Swipe right"))

    def test_geometry_uses_real_offset_and_viewports(self):
        text = ("A11Y list geometry: parent=0,16,480,784 text=10,40,460,760 "
                "title=10,16,460,24 line=24 start=2 y=48 count=20 selected=3 group=1\n")
        geometry = ListGeometry.latest(text)
        self.assertEqual(geometry.point(3), (240, 76))
        with self.assertRaises(AssertionError):
            geometry.point(0)

    def test_missing_geometry_is_not_guessed(self):
        with self.assertRaises(AssertionError):
            ListGeometry.latest("TTS: Alpha\n")

    def test_packed_mouse_coordinates_are_bounded(self):
        self.assertEqual(packed_point((479, 799)), 479 | (799 << 16))
        for point in ((-1, 1), (1, 32768), (1,), (1.1, 2)):
            with self.subTest(point=point), self.assertRaises(AssertionError):
                packed_point(point)

    def test_real_input_paths_have_distinct_direction_and_turn(self):
        self.assertEqual(len(DIRECTIONS), 16)
        for name, vertices in DIRECTIONS.items():
            with self.subTest(name=name):
                points = stroke_points(name)
                self.assertEqual(points[0], vertices[0])
                self.assertEqual(points[-1], vertices[-1])
                self.assertTrue(all(0 <= point[0] < 480 and 0 <= point[1] < 800 for point in points))
                self.assertGreaterEqual(len(points), 11)
                if len(vertices) == 3:
                    self.assertIn(vertices[1], points)

    def test_missing_utterance_is_not_speech_acceptance(self):
        self.assertFalse(has_speech("TTS: Alpha\n", ("Alpha",)))
        self.assertTrue(has_speech("TTS: Alpha\nTTS utterance: Alpha\n", ("Alpha",)))

    def test_accidental_activation_is_rejected(self):
        for text in ("TTS: 001 Alpha marker\n", "TTS utterance: 002 Beta marker\n",
                     "TTS reader state: reading\n"):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                assert_no_activation(text)
        assert_no_activation("TTS: 001 Alpha\nTTS utterance: 001 Alpha\n")

    def test_binding_parser_rejects_incomplete_or_duplicate_config(self):
        valid = "RBACCESSIBILITY:1\nenabled:1\n" + ''.join(f"gesture:{slot}:0\n" for slot in range(1, 19))
        self.assertEqual(parse_bindings(valid.encode())[2], 0)
        for text in (valid.replace("gesture:2:0", "gesture:1:0"), valid[:-13],
                     valid.replace("gesture:2:0", "gesture:2:99")):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                parse_bindings(text.encode())

    def test_v2_config_parser_checks_all_button_rows_and_feedback(self):
        valid = ("RBACCESSIBILITY:2\nenabled:1\nclick:3\nhold:700\n"
                 + ''.join(f"gesture:{slot}:0\n" for slot in range(1, 19))
                 + ''.join(f"button:{button}:{slot}:15\n" for button in range(5) for slot in range(4)))
        parsed = parse_accessibility_config(valid.encode())
        self.assertEqual(parsed["click_sources"], 3)
        self.assertEqual(parsed["hold_ms"], 700)
        self.assertEqual(len(parsed["buttons"]), 20)
        self.assertEqual(parsed["buttons"][(4, 3)], 15)
        self.assertEqual(parsed["version"], 2)
        self.assertFalse(any(parsed["gesture_launch"].values()))
        self.assertFalse(any(parsed["button_launch"].values()))
        self.assertFalse(any(parsed["launch_paths"].values()))
        for text in (valid.replace("click:3", "click:0"), valid.replace("hold:700", "hold:750"),
                     valid.replace("button:4:3:15", "button:4:3:16"),
                     valid.replace("button:4:3:15", "button:4:2:15"), valid + "unexpected\n"):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                parse_accessibility_config(text.encode())

    def test_v1_migration_uses_default_feedback_and_empty_launch_bindings(self):
        data = ("RBACCESSIBILITY:1\nenabled:1\n"
                + ''.join(f"gesture:{slot}:0\n" for slot in range(1, 19))).encode("ascii")
        parsed = parse_accessibility_config(data)
        self.assertEqual(parsed["version"], 1)
        self.assertEqual(parsed["click_sources"], 7)
        self.assertEqual(parsed["hold_ms"], 700)
        self.assertEqual(parsed["touch_hold_ms"], 900)
        self.assertFalse(parsed["stroke_repeat"])
        self.assertTrue(all(action == 15 for action in parsed["buttons"].values()))
        self.assertFalse(any(parsed["gesture_launch"].values()))
        self.assertFalse(any(parsed["launch_paths"].values()))

    def test_v3_all_builtin_launch_destinations_are_distinct_from_plugin_pool(self):
        valid = self.current_config()
        self.assertEqual(len(valid.splitlines()), 46)
        self.assertEqual(parse_accessibility_config(valid.encode())["version"], 3)
        for target in ACCESSIBILITY_BUILTIN_LAUNCH_TARGETS:
            text = valid.replace("gesture:1:1:0", f"gesture:1:12:{target}")
            text = text.replace("button:0:0:15:0", f"button:0:0:12:{target}")
            parsed = parse_accessibility_config(text.encode())
            self.assertEqual(parsed["gesture_launch"][1], target)
            self.assertEqual(parsed["button_launch"][(0, 0)], target)
        self.assertEqual(ACCESSIBILITY_BUILTIN_LAUNCH_TARGETS[0], "destination chooser")
        self.assertEqual(ACCESSIBILITY_BUILTIN_LAUNCH_TARGETS[1], "shortcuts")

    def test_v4_curtain_and_system_default_have_distinct_values(self):
        current = self.current_config().replace("RBACCESSIBILITY:3", "RBACCESSIBILITY:4")
        current = re.sub(r'(button:[0-4]:[0-3]:)15:', r'\g<1>16:', current)
        current = current.replace("gesture:1:1:0", "gesture:1:15:0")
        parsed = parse_accessibility_config(current.encode())
        self.assertEqual(parsed["version"], 4)
        self.assertEqual(parsed["gestures"][1], 15)
        self.assertTrue(all(action == 16 for action in parsed["buttons"].values()))
        for invalid in (current.replace("gesture:1:15:0", "gesture:1:16:0"),
                        current.replace("button:0:0:16:0", "button:0:0:17:0")):
            with self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode())

    def test_v5_time_curtain_and_system_values_remain_distinct(self):
        current = self.current_config().replace("RBACCESSIBILITY:3", "RBACCESSIBILITY:5")
        current = re.sub(r'(button:[0-4]:[0-3]:)15:', r'\g<1>17:', current)
        current = current.replace("gesture:1:1:0", "gesture:1:16:0")
        current = current.replace("button:0:0:17:0", "button:0:0:16:0")
        current = current.replace("button:0:1:17:0", "button:0:1:15:0")
        parsed = parse_accessibility_config(current.encode())
        self.assertEqual(parsed["version"], 5)
        self.assertEqual(parsed["gestures"][1], 16)
        self.assertEqual(parsed["buttons"][(0, 0)], 16)
        self.assertEqual(parsed["buttons"][(0, 1)], 15)
        self.assertEqual(parsed["buttons"][(4, 3)], 17)
        for invalid in (current.replace("gesture:1:16:0", "gesture:1:17:0"),
                        current.replace("button:0:0:16:0", "button:0:0:18:0"),
                        current.replace("button:0:0:16:0", "button:0:0:16:1"),
                        current.replace("RBACCESSIBILITY:5", "RBACCESSIBILITY:7")):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode())

    def test_v6_toggles_time_and_system_values_remain_distinct(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=6).decode("ascii")
        current = current.replace("gesture:1:1:0", "gesture:1:17:0")
        current = current.replace("gesture:2:2:0", "gesture:2:18:0")
        current = current.replace("gesture:18:0:0", "gesture:18:16:0")
        current = current.replace("button:0:0:19:0", "button:0:0:17:0")
        current = current.replace("button:0:1:19:0", "button:0:1:18:0")
        current = current.replace("button:0:2:19:0", "button:0:2:16:0")
        parsed = parse_accessibility_config(current.encode())
        self.assertEqual(parsed["version"], 6)
        self.assertEqual(len(current.splitlines()), 46)
        self.assertEqual([parsed["gestures"][slot] for slot in (1, 2, 18)], [17, 18, 16])
        self.assertEqual([parsed["buttons"][(0, slot)] for slot in range(4)], [17, 18, 16, 19])
        self.assertEqual(parsed["buttons"][(4, 3)], 19)
        self.assertEqual(parse_bindings(current.encode()), parsed["gestures"])

    def test_all_versions_keep_row_counts_sentinels_and_strict_action_bounds(self):
        for version, rows, sentinel, maximum in (
                (1, 20, 15, 10), (2, 42, 15, 14), (3, 46, 15, 14),
                (4, 46, 16, 15), (5, 46, 17, 16), (6, 46, 19, 18), (7, 50, 22, 21), (8, 52, 22, 21),
                (9, 72, 22, 21)):
            current = self.config_for_version(version)
            first_gesture = 2 if version == 1 else 8 if version >= 8 else 6 if version >= 7 else 4
            gesture_count = 20 if version >= 7 else 18
            lines = current.splitlines(keepends=True)
            with self.subTest(version=version):
                parsed = parse_accessibility_config(current.encode())
                self.assertEqual(len(lines), rows)
                self.assertEqual(parsed["version"], version)
                self.assertEqual(set(parsed["buttons"].values()), {sentinel})
                self.assertEqual(set(parsed["gestures"]), set(range(1, gesture_count + 1)))
                self.assertEqual(parsed["touch_hold_ms"], 900)
                self.assertFalse(parsed["stroke_repeat"])
                for invalid in (''.join(lines[:-1]), current + lines[-1]):
                    with self.assertRaises(AssertionError):
                        parse_accessibility_config(invalid.encode())
            for physical in (False, True) if version > 1 else (False,):
                for action in list(range(-1, 24)) + [255]:
                    trial = list(lines)
                    suffix = ":0\n" if version >= 3 else "\n"
                    if physical:
                        trial[first_gesture + gesture_count] = f"button:0:0:{action}" + suffix
                    else:
                        trial[first_gesture] = f"gesture:1:{action}" + suffix
                    with self.subTest(version=version, physical=physical, action=action):
                        data = ''.join(trial).encode()
                        if 0 <= action <= (sentinel if physical else maximum):
                            parsed = parse_accessibility_config(data)
                            mappings = parsed["buttons"] if physical else parsed["gestures"]
                            self.assertEqual(mappings[(0, 0) if physical else 1], action)
                        else:
                            with self.assertRaises(AssertionError):
                                parse_accessibility_config(data)

    def test_v8_accepts_all_source_masks_and_empty_pitch_settings(self):
        current = self.config_for_version(8, sources=7)
        self.assertEqual(len(current.splitlines()), 52)
        self.assertEqual(current.splitlines()[5:8], ["stroke_repeat:0", "empty_pitch:1", "empty_semitones:-4"])
        for sources in range(8):
            for pitch in (0, 1):
                for semitones in range(-12, 13):
                    text = (current.replace("click:7\n", f"click:{sources}\n")
                            .replace("empty_pitch:1\n", f"empty_pitch:{pitch}\n")
                            .replace("empty_semitones:-4\n", f"empty_semitones:{semitones}\n"))
                    with self.subTest(sources=sources, pitch=pitch, semitones=semitones):
                        parsed = parse_accessibility_config(text.encode("ascii"))
                        self.assertEqual(parsed["version"], 8)
                        self.assertEqual(parsed["click_sources"], sources)
                        self.assertIs(parsed["empty_pitch"], bool(pitch))
                        self.assertEqual(parsed["empty_semitones"], semitones)

    def test_legacy_versions_migrate_with_pitch_defaults_and_preserve_explicit_sources(self):
        for version in range(1, 8):
            for sources in ((7,) if version == 1 else (1, 2, 3)):
                text = (self.config_for_version(version, sources=sources)
                        .replace("enabled:1\n", "enabled:0\n")
                        .replace("hold:700\n", "hold:800\n")
                        .replace("touch_hold:900\n", "touch_hold:1100\n")
                        .replace("stroke_repeat:0\n", "stroke_repeat:1\n"))
                with self.subTest(version=version, sources=sources):
                    parsed = parse_accessibility_config(text.encode("ascii"))
                    self.assertEqual(parsed["version"], version)
                    self.assertFalse(parsed["enabled"])
                    self.assertEqual(parsed["click_sources"], sources)
                    self.assertEqual(parsed["hold_ms"], 700 if version == 1 else 800)
                    self.assertEqual(parsed["touch_hold_ms"], 1100 if version >= 7 else 900)
                    self.assertIs(parsed["stroke_repeat"], version >= 7)
                    self.assertTrue(parsed["empty_pitch"])
                    self.assertEqual(parsed["empty_semitones"], -4)
                if version > 1:
                    for invalid in (0, 4, 7, 8):
                        with self.subTest(version=version, invalid=invalid), self.assertRaises(AssertionError):
                            parse_accessibility_config(text.replace(f"click:{sources}\n", f"click:{invalid}\n").encode("ascii"))
                with self.subTest(version=version, extra_fields=True), self.assertRaises(AssertionError):
                    parse_accessibility_config(text.replace("enabled:0\n", "enabled:0\nempty_pitch:1\nempty_semitones:-4\n").encode("ascii"))

    def test_v8_rejects_missing_reordered_noncanonical_or_out_of_range_fields(self):
        current = self.config_for_version(8, sources=7)
        cases = [current.replace("RBACCESSIBILITY:8\n", f"RBACCESSIBILITY:{value}\n")
                 for value in ("7", "9", "08", "+8", "8 ")]
        for field, values in (
                ("click:7", ("", "-1", "8", "07", "+7", "7 ", "4294967296")),
                ("empty_pitch:1", ("", "-1", "2", "01", "+1", "true", "1 ", "4294967296")),
                ("empty_semitones:-4", ("", "-13", "13", "-0", "+4", "04", "-04", "4.0", "4 ", "4294967296"))):
            name = field.split(":", 1)[0]
            cases += [current.replace(field + "\n", f"{name}:{value}\n") for value in values]
            cases += [current.replace(field + "\n", ""), current.replace(field + "\n", field + "\n" + field + "\n")]
        cases += [current.replace("empty_pitch:1\nempty_semitones:-4\n", "empty_semitones:-4\nempty_pitch:1\n"),
                  current.replace("stroke_repeat:0\nempty_pitch:1\n", "empty_pitch:1\nstroke_repeat:0\n"),
                  current.replace("empty_pitch:1\nempty_semitones:-4\n", ""),
                  current.replace("\n", "\r\n"), current[:-1], current + "\n"]
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode("ascii"))

    def test_v7_and_v8_keep_identical_gesture_and_launch_semantics(self):
        for target in range(4, 13):
            parsed_versions = []
            for version in (7, 8):
                text = (self.config_for_version(version)
                        .replace("gesture:19:0:0\n", "gesture:19:21:0\n")
                        .replace("gesture:20:0:0\n", f"gesture:20:12:{target}\n")
                        .replace("button:4:3:22:0\n", f"button:4:3:12:{target}\n"))
                if target < 8:
                    text = text.replace(f"target:{target - 4}:\n", f"target:{target - 4}:/.rockbox/rocks/apps/Zażółć.rock\n")
                with self.subTest(version=version, target=target):
                    parsed = parse_accessibility_config(text.encode("utf-8"))
                    self.assertEqual(parsed["gestures"][19], 21)
                    self.assertEqual(parsed["gesture_launch"][20], target)
                    self.assertEqual(parsed["button_launch"][(4, 3)], target)
                    self.assertEqual(parsed["buttons"][(0, 0)], 22)
                    self.assertEqual(len(parsed["gestures"]), 20)
                    if target < 8:
                        self.assertEqual(parsed["launch_paths"][target - 4], "/.rockbox/rocks/apps/Zażółć.rock")
                    else:
                        self.assertFalse(any(parsed["launch_paths"].values()))
                    parsed_versions.append({key: value for key, value in parsed.items() if key != "version"})
            self.assertEqual(parsed_versions[0], parsed_versions[1])

    def test_v8_keeps_mapping_launch_and_byte_guards(self):
        current = self.config_for_version(8)
        path = ACCESSIBILITY_PLUGIN_PREFIX + "a" * (ACCESSIBILITY_MAX_PATH - len(ACCESSIBILITY_PLUGIN_PREFIX) - 6) + ".rock"
        valid = current.replace("target:0:\n", f"target:0:{path}\n")
        self.assertEqual(len(path.encode("ascii")), ACCESSIBILITY_MAX_PATH - 1)
        self.assertEqual(parse_accessibility_config(valid.encode("ascii"))["launch_paths"][0], path)
        cases = (current.replace("gesture:20:0:0\n", "gesture:20:22:0\n"),
                 current.replace("button:4:3:22:0\n", "button:4:3:23:0\n"),
                 current.replace("gesture:19:0:0\n", "gesture:20:0:0\n"),
                 current.replace("gesture:20:0:0\n", "gesture:20:12:13\n"),
                 current.replace("button:4:3:22:0\n", "button:4:3:21:1\n"),
                 current.replace("gesture:20:0:0\n", "gesture:20:12:4\n"),
                 current.replace("target:3:\n", "target:2:\n"), valid.replace(path, path[:-5] + "a.rock"),
                 "x" * (ACCESSIBILITY_CONFIG_MAX + 1))
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode("ascii"))

    def test_v6_rejects_noncanonical_actions_launch_references_and_future_headers(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=6).decode("ascii")
        cases = [current.replace("RBACCESSIBILITY:6", f"RBACCESSIBILITY:{version}")
                 for version in (7, "06", "6 ")]
        for action in ("017", "+17", "-1", "19", "20"):
            cases.append(current.replace("gesture:1:1:0", f"gesture:1:{action}:0"))
        for action in ("019", "+19", "-1", "20"):
            cases.append(current.replace("button:0:0:19:0", f"button:0:0:{action}:0"))
        for action in (16, 17, 18, 19):
            if action != 19:
                cases.append(current.replace("gesture:1:1:0", f"gesture:1:{action}:1"))
            cases.append(current.replace("button:0:0:19:0", f"button:0:0:{action}:1"))
        cases.extend((current.replace("\n", "\r\n"), current[:-1], current + "\n"))
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode())

    def test_v7_touch_hold_and_repeat_accept_all_steps_independently_of_physical_hold(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=7).decode("ascii")
        for duration in range(300, 2001, 100):
            for repeat in (0, 1):
                text = current.replace("touch_hold:900", f"touch_hold:{duration}")
                text = text.replace("stroke_repeat:0", f"stroke_repeat:{repeat}")
                with self.subTest(duration=duration, repeat=repeat):
                    parsed = parse_accessibility_config(text.encode("ascii"))
                    self.assertEqual(parsed["touch_hold_ms"], duration)
                    self.assertIs(parsed["stroke_repeat"], bool(repeat))
                    self.assertEqual(parsed["hold_ms"], 700)

    def test_v7_rejects_noncanonical_touch_fields_headers_and_rows(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=7).decode("ascii")
        cases = [current.replace("touch_hold:900", f"touch_hold:{value}")
                 for value in ("", "0", "299", "301", "350", "1999", "2001", "2100",
                               "0900", "+900", "-900", "900 ", "900.0", "4294967296")]
        cases += [current.replace("stroke_repeat:0", f"stroke_repeat:{value}")
                  for value in ("", "2", "-1", "+1", "01", "00", "1 ", "true", "4294967296")]
        cases += [current.replace("RBACCESSIBILITY:7", f"RBACCESSIBILITY:{value}")
                  for value in ("8", "07", "7 ", "+7")]
        cases += [current.replace("gesture:1:1:0", f"gesture:1:{value}:0")
                  for value in ("019", "+19", "-1", "22", "23", "4294967296")]
        cases += [current.replace("button:0:0:22:0", f"button:0:0:{value}:0")
                  for value in ("022", "+22", "-1", "23", "4294967296")]
        cases += [current.replace("gesture:19:0:0\n", ""),
                  current.replace("gesture:20:0:0\n", ""),
                  current.replace("gesture:20:0:0", "gesture:19:0:0"),
                  current.replace("gesture:19:0:0", "gesture:019:0:0"),
                  current.replace("gesture:19:0:0\ngesture:20:0:0", "gesture:20:0:0\ngesture:19:0:0"),
                  current.replace("touch_hold:900\nstroke_repeat:0", "stroke_repeat:0\ntouch_hold:900"),
                  current.replace("touch_hold:900\n", ""), current.replace("stroke_repeat:0\n", ""),
                  current + "gesture:21:0:0\n", current.replace("\n", "\r\n"), current[:-1], current + "\n"]
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode("ascii"))

    def test_v7_new_gesture_slots_allow_new_actions_without_system_gesture(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=7).decode("ascii")
        for slot in (19, 20):
            for action in (19, 20, 21, 22):
                data = current.replace(f"gesture:{slot}:0:0", f"gesture:{slot}:{action}:0").encode("ascii")
                with self.subTest(slot=slot, action=action):
                    if action == 22:
                        with self.assertRaises(AssertionError):
                            parse_accessibility_config(data)
                    else:
                        self.assertEqual(parse_accessibility_config(data)["gestures"][slot], action)

    def test_v7_direct_launch_targets_never_index_the_four_plugin_paths(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=7).decode("ascii")
        for target in ACCESSIBILITY_DIRECT_LAUNCH_TARGETS:
            for slot in (1, 19, 20):
                text = re.sub(rf'gesture:{slot}:[0-9]+:0\n', f"gesture:{slot}:12:{target}\n", current)
                text = text.replace("button:4:3:22:0", f"button:4:3:12:{target}")
                with self.subTest(target=target, slot=slot):
                    parsed = parse_accessibility_config(text.encode("ascii"))
                    self.assertEqual(parsed["gesture_launch"][slot], target)
                    self.assertEqual(parsed["button_launch"][(4, 3)], target)
                    self.assertFalse(any(parsed["launch_paths"].values()))

    def test_v7_plugin_references_still_require_the_exact_path_slot(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=7).decode("ascii")
        for target in range(4, 8):
            for old, new in (("gesture:20:0:0", f"gesture:20:12:{target}"),
                             ("button:4:3:22:0", f"button:4:3:12:{target}")):
                text = current.replace(old, new)
                with self.subTest(target=target, row=old):
                    with self.assertRaises(AssertionError):
                        parse_accessibility_config(text.encode("ascii"))
                    wrong = text.replace(f"target:{(target - 3) % 4}:\n",
                                         f"target:{(target - 3) % 4}:/.rockbox/rocks/apps/wrong.rock\n")
                    with self.assertRaises(AssertionError):
                        parse_accessibility_config(wrong.encode("ascii"))
                    path = f"/.rockbox/rocks/apps/target{target}.rock"
                    text = text.replace(f"target:{target - 4}:\n", f"target:{target - 4}:{path}\n")
                    self.assertEqual(parse_accessibility_config(text.encode("ascii"))["launch_paths"][target - 4], path)

    def test_v7_rejects_invalid_targets_and_nonlaunch_destinations(self):
        from test_keyclick_gui import accessibility_configuration
        current = accessibility_configuration(3, version=7).decode("ascii")
        for target in ("-1", "+8", "08", "13", "255", "4294967296"):
            for old, new in (("gesture:20:0:0", f"gesture:20:12:{target}"),
                             ("button:4:3:22:0", f"button:4:3:12:{target}")):
                with self.subTest(target=target, row=old), self.assertRaises(AssertionError):
                    parse_accessibility_config(current.replace(old, new).encode("ascii"))
        for action in (0, 19, 20, 21, 22):
            for target in range(1, 13):
                rows = [("button:4:3:22:0", f"button:4:3:{action}:{target}")]
                if action < 22:
                    rows.append(("gesture:20:0:0", f"gesture:20:{action}:{target}"))
                for old, new in rows:
                    with self.subTest(action=action, target=target, row=old), self.assertRaises(AssertionError):
                        parse_accessibility_config(current.replace(old, new).encode("ascii"))

    def test_legacy_versions_reject_v7_fields_slots_actions_and_direct_targets(self):
        from test_keyclick_gui import accessibility_configuration
        for version in range(1, 7):
            if version == 1:
                current = "RBACCESSIBILITY:1\nenabled:1\n" + ''.join(
                    f"gesture:{slot}:0\n" for slot in range(1, 19))
            elif version == 2:
                current = ("RBACCESSIBILITY:2\nenabled:1\nclick:3\nhold:700\n"
                           + ''.join(f"gesture:{slot}:0\n" for slot in range(1, 19))
                           + ''.join(f"button:{button}:{slot}:15\n" for button in range(5) for slot in range(4)))
            else:
                current = accessibility_configuration(3, version).decode("ascii")
            suffix = ":0" if version >= 3 else ""
            first = "gesture:1:" + ("0" if version <= 2 else "1") + suffix
            cases = [current.replace("enabled:1\n", "enabled:1\ntouch_hold:900\nstroke_repeat:0\n"),
                     current.replace(first, "gesture:19:0" + suffix),
                     current.replace(first, "gesture:20:0" + suffix)]
            cases += [current.replace(first, f"gesture:1:{action}" + suffix) for action in (19, 20, 21)]
            if version >= 3:
                for target in range(8, 13):
                    cases += [current.replace(first, f"gesture:1:12:{target}"),
                              re.sub(r'button:0:0:[0-9]+:0', f"button:0:0:12:{target}", current)]
            for invalid in cases:
                with self.subTest(version=version, invalid=invalid), self.assertRaises(AssertionError):
                    parse_accessibility_config(invalid.encode("ascii"))

    def test_v3_four_plugin_paths_can_be_referenced_and_shared(self):
        valid = self.current_config()
        paths = ("/.rockbox/rocks/apps/Zażółć.rock", "/.rockbox/rocks/games/rockboy.rock",
                 "/.rockbox/rocks/demos/pictureflow.rock", "/.rockbox/rocks/viewers/text_editor.rock")
        for index, path in enumerate(paths):
            valid = re.sub(rf'gesture:{index + 1}:[0-9]+:0\n',
                           f"gesture:{index + 1}:12:{index + 4}\n", valid)
            valid = valid.replace(f"target:{index}:\n", f"target:{index}:{path}\n")
        valid = valid.replace("button:4:3:15:0", "button:4:3:12:7")
        parsed = parse_accessibility_config(valid.encode("utf-8"))
        self.assertEqual(parsed["launch_paths"], dict(enumerate(paths)))
        self.assertEqual(parsed["gesture_launch"][4], 7)
        self.assertEqual(parsed["button_launch"][(4, 3)], 7)

    def test_v3_rejects_invalid_launch_references_and_nonlaunch_destinations(self):
        valid = self.current_config()
        cases = (valid.replace("gesture:1:1:0", "gesture:1:12:8"),
                 valid.replace("gesture:1:1:0", "gesture:1:12:07"),
                 valid.replace("gesture:1:1:0", "gesture:1:12:-1"),
                 valid.replace("gesture:1:1:0", "gesture:1:1:1"),
                 valid.replace("gesture:1:1:0", "gesture:1:12:4"),
                 valid.replace("button:4:3:15:0", "button:4:3:12:8"),
                 valid.replace("button:4:3:15:0", "button:4:3:15:1"),
                 valid.replace("button:4:3:15:0", "button:4:3:12:7"))
        for text in cases:
            with self.subTest(text=text), self.assertRaises(AssertionError):
                parse_accessibility_config(text.encode())

    def test_v3_rejects_malformed_plugin_paths_even_when_not_referenced(self):
        valid = self.current_config()
        paths = ("relative.rock", "/.rockbox/rocks/.rock", "/outside/app.rock",
                 "/.rockbox/rocks/../app.rock", "/.rockbox/rocks/apps/./app.rock",
                 "/.rockbox/rocks//app.rock", "/.rockbox/rocks/apps\\app.rock",
                 "/.rockbox/rocks/apps/app.ROCK", "/.rockbox/rocks/apps/app.txt",
                 "/.rockbox/rocks/apps/\0app.rock", "/.rockbox/rocks/apps/\tapp.rock",
                 "/.rockbox/rocks/apps/\rapp.rock", "/.rockbox/rocks/apps/\x7fapp.rock",
                 "/.rockbox/rocks/apps/\napp.rock")
        for path in paths:
            text = valid.replace("target:0:\n", f"target:0:{path}\n")
            with self.subTest(path=path), self.assertRaises(AssertionError):
                parse_accessibility_config(text.encode("utf-8"))

    def test_v3_plugin_path_limit_counts_utf8_bytes_not_characters(self):
        budget = ACCESSIBILITY_MAX_PATH - 1 - len(ACCESSIBILITY_PLUGIN_PREFIX) - len(".rock")
        for stem in ("a" * budget, "ą" * (budget // 2) + "a" * (budget % 2)):
            path = ACCESSIBILITY_PLUGIN_PREFIX + stem + ".rock"
            self.assertEqual(len(path.encode("utf-8")), ACCESSIBILITY_MAX_PATH - 1)
            self.assertTrue(launch_path_valid(path))
            valid = self.current_config().replace("target:0:\n", f"target:0:{path}\n")
            self.assertEqual(parse_accessibility_config(valid.encode("utf-8"))["launch_paths"][0], path)
            invalid = valid.replace(path, path[:-5] + "a.rock")
            with self.assertRaises(AssertionError):
                parse_accessibility_config(invalid.encode("utf-8"))

    def test_v3_rejects_mixed_versions_target_pool_errors_and_oversized_config(self):
        valid = self.current_config()
        cases = (valid.replace("RBACCESSIBILITY:3", "RBACCESSIBILITY:2"),
                 valid.replace("RBACCESSIBILITY:3", "RBACCESSIBILITY:7"),
                 valid.replace("target:3:\n", ""),
                 valid.replace("target:3:\n", "target:4:\n"),
                 valid.replace("target:3:\n", "target:2:\n"),
                 valid.replace("target:2:\ntarget:3:\n", "target:3:\ntarget:2:\n"),
                 valid + "target:4:\n", valid.replace("gesture:1:1:0", "gesture:1:1"),
                 valid.replace("button:0:0:15:0", "button:0:0:15"),
                 valid.replace("\n", "\r\n"), valid[:-1], "x" * (ACCESSIBILITY_CONFIG_MAX + 1))
        for text in cases:
            with self.subTest(text=text), self.assertRaises(AssertionError):
                parse_accessibility_config(text.encode())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", type=Path, help="Explicit ready fullinstalled development build inside central Workspace")
    parser.add_argument("--build-ready", action="store_true", help="Build owner authorizes real GUI use; never pass while building")
    parser.add_argument("--exe-sha256", help="Owner-supplied frozen new rockboxui.exe SHA256; required for acceptance")
    parser.add_argument("--build-receipt", type=Path, help="Optional owner build/freeze receipt, pinned in evidence")
    parser.add_argument("--preliminary", action="store_true", help="Owner-authorized source-unfrozen development run, never final release acceptance")
    parser.add_argument("--language", choices=("polski", "english"), default="polski")
    parser.add_argument("--suite", choices=("default", "editor", "keyclick", "all"), default="all",
                        help="all runs default touch + editor; keyclick is a separate speech-disabled profile matrix")
    parser.add_argument("--timeout", type=float, default=40, help="Per-observation bound,40..60seconds including timed rollback")
    parser.add_argument("--self-test", action="store_true", help="Pure harness unit tests only; no build, GUI or audio acceptance")
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        if arguments.build or arguments.build_ready or arguments.exe_sha256 or arguments.build_receipt or arguments.preliminary:
            parser.error("--self-test cannot be combined with build/acceptance arguments")
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HarnessUnitTests))
        return 0 if result.wasSuccessful() else 1
    if not arguments.build_ready or arguments.build is None or not arguments.exe_sha256:
        parser.error("Requires --build, explicit owner --build-ready and frozen --exe-sha256")
    if sys.platform != "win32":
        parser.error("Actual acceptance requires native Windows Python, not WSL/Wine")
    if not re.fullmatch(r'[0-9a-fA-F]{64}', arguments.exe_sha256) or not 40 <= arguments.timeout <= 60:
        parser.error("Invalid frozen SHA256 or timeout outside40..60seconds")
    materials = project_materials_root(ROOT)
    workspace = contained(materials, ROOT)
    build = contained(arguments.build, workspace)
    require("GUI" not in build.parts, "A previous GUI fixture is not an authorized development build")
    executable = contained(build / "rockboxui.exe", build)
    require(digest(executable) == arguments.exe_sha256.lower(), "Ready executable differs from the frozen owner hash")
    windows_backend().ensure_unused(executable)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    results = workspace.joinpath(*SUITE_DIRECTORY, stamp)
    results.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, acceptance_complete=False, target="hibyr1", language=arguments.language,
                  suite=arguments.suite, source_build=str(build), expected_exe_sha256=arguments.exe_sha256.lower(),
                  desktop_input_changes="Native mouse acceptance temporarily moves the real cursor and focuses the owned SDL window",
                  preliminary=arguments.preliminary, source_frozen=not arguments.preliminary,
                  published_release_tested=False,
                  all_accessibility_requirements_accepted=False,
                  acceptance_scope=("isolated-keyclick-routing-and-strength" if arguments.suite == "keyclick"
                                    else "touch-navigation-and-gesture-editor"),
                  accessibility_config_contract={
                      "current_version": ACCESSIBILITY_CONFIG_VERSION,
                      "legacy_versions": list(range(1, ACCESSIBILITY_CONFIG_VERSION)),
                      "maximum_bytes": ACCESSIBILITY_CONFIG_MAX, "plugin_path_pool": ACCESSIBILITY_PLUGIN_PATH_COUNT,
                      "gesture_count": ACCESSIBILITY_GESTURE_COUNT,
                      "legacy_gesture_count": ACCESSIBILITY_LEGACY_GESTURE_COUNT,
                      "touch_hold_ms": {"minimum": 300, "maximum": 2000, "step": 100, "default": 900},
                      "stroke_repeat_values": [0, 1], "system_action": ACCESSIBILITY_SYSTEM_ACTION,
                      "source_masks": {"legacy": [1, 2, 3], "current": list(range(8)), "default": 7},
                      "empty_pitch_default": True,
                      "empty_semitones": {"minimum": -12, "maximum": 12, "default": -4},
                      "direct_launch_destinations": ACCESSIBILITY_DIRECT_LAUNCH_TARGETS,
                      "builtin_launch_destinations": ACCESSIBILITY_BUILTIN_LAUNCH_TARGETS,
                      "plugin_launch_ids": list(range(ACCESSIBILITY_PLUGIN_TARGET_BASE,
                                                      ACCESSIBILITY_PLUGIN_TARGET_BASE + ACCESSIBILITY_PLUGIN_PATH_COUNT)),
                  },
                  checks=[], sessions=[], copies=[], input_events=[], completed_scenarios=[],
                  physical_hardware_tested=False, bluetooth_tested=False, nvda_tested=False,
                  limitations=["Native Windows real SDL input and mixer PCM, not physical touchscreen/hardware.",
                               "No Bluetooth, microphone, NVDA/UIA or human intelligibility acceptance.",
                               "Synthetic profile only; all failed evidence remains immutable."])
    loan = ExecutableLoan(build, results, report)
    probe = AccessibilityProbe(results / "fixture", results, report, arguments.timeout)
    before = None
    source_before = None
    print(f"Real SDL accessibility GUI evidence: {results}", flush=True)
    try:
        before = inventory(build)
        write_json(results / "build-before.json", before)
        source_before = {path: digest(ROOT / path) for path in SOURCE_PATHS}
        if arguments.suite == "keyclick":
            source_before["tools/tests/test_keyclick_gui.py"] = digest(ROOT / "tools/tests/test_keyclick_gui.py")
        report["source_inputs_before"] = source_before
        if arguments.build_receipt:
            receipt = contained(arguments.build_receipt, workspace)
            report["owner_build_receipt"] = {"path": str(receipt), "sha256": digest(receipt)}
        runtime, labels, displayed, _document = prepare_fixture(
            build, results, arguments.language, report, target_name="hibyr1", voice_files_disabled=True)
        voice = catalog_labels(build, arguments.language)
        compiled_display = display_labels(build, arguments.language)
        for identifier in LABELS:
            labels[identifier] = voice.get(identifier) or compiled_display.get(identifier)
            require(bool(labels[identifier]), f"Missing new compiled accessibility label:{identifier}; old R3 is not acceptance")
        report["labels"] = labels
        tree = runtime / "simdisk" / TREE
        tree.mkdir()
        for folder, marker in zip(FOLDERS, MARKERS):
            destination = tree / folder
            destination.mkdir()
            (destination / (marker + ".txt")).write_text("Synthetic activation witness.\n", encoding="utf-8")
        write_json(runtime / ".r1-accessibility-gui-fixture.json", {
            "purpose": "Real SDL accessibility regression; synthetic profile/data only",
            "source_build": str(build), "expected_exe_sha256": arguments.exe_sha256.lower(),
        })
        for copied in report["copies"]:
            copied["purpose"] = "Isolated real SDL accessibility GUI/PCM regression and reproduction"
        probe.runtime = runtime
        probe.log = runtime / "simulator.log"
        loan.move_to(runtime)
        if arguments.suite == "keyclick":
            from test_keyclick_gui import exercise_feedback
            exercise_feedback(probe, arguments.language)
        else:
            probe.launch("r1-accessibility-" + arguments.suite)
            startup(probe, arguments.language)
            if arguments.suite in ("default", "all"):
                defaults(probe, labels)
            if arguments.suite in ("editor", "all"):
                editor(probe, labels)
        probe.close()
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            probe.close(graceful=False)
        except Exception as error:
            report["process_cleanup_error"] = str(error)
        try:
            loan.restore(probe.process)
        except Exception as error:
            report["executable_restore_error"] = str(error)
        try:
            if loan.record["restored"] and before is not None:
                after = inventory(build)
                write_json(results / "build-after.json", after)
                report["build_unchanged"] = before == after
                require(before == after, "Development build changed during isolated GUI testing")
            if source_before is not None:
                source_after = {path: digest(ROOT / path) for path in source_before}
                report["source_inputs_after"] = source_after
                report["source_unchanged"] = source_before == source_after
                require(source_before == source_after, "Integration source/harness changed during GUI acceptance")
            if arguments.suite == "keyclick":
                from test_keyclick_gui import verify_feedback
                verify_feedback(report)
            else:
                verify_evidence(report)
        except Exception as error:
            report["evidence_error"] = str(error)
        required = ({"keyclick-source-and-strength-matrix"} if arguments.suite == "keyclick" else
                    {"default-touch-navigation-and-lock", "editor-unassigned-and-timed-rollback"}
                    if arguments.suite == "all" else
                    {"default-touch-navigation-and-lock" if arguments.suite == "default"
                     else "editor-unassigned-and-timed-rollback"})
        report["passed"] = (bool(report["sessions"]) and loan.record["restored"]
                            and report.get("build_unchanged", False)
                            and report.get("source_unchanged", False)
                            and not any(name.endswith("error") for name in report)
                            and required == set(report["completed_scenarios"])
                            and all(check["status"] == "passed" for check in report["checks"]))
        report["suite_complete"] = report["passed"] and arguments.suite in ("all", "keyclick")
        report["acceptance_complete"] = report["suite_complete"] and not arguments.preliminary
        report["exe_sha256"] = digest(executable) if loan.record["restored"] else None
        write_json(results / "report.json", report)
    print(json.dumps({"passed": report["passed"], "acceptance_complete": report["acceptance_complete"],
                      "error": report.get("error"), "report": str(results / "report.json")},
                     ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
