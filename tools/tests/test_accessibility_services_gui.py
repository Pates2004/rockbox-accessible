"""Gated R1 Windows service/menu acceptance on an undisplayed private desktop.

Safe preparation:
  python -B tools/tests/test_accessibility_services_gui.py --readiness
  python -B tools/tests/test_accessibility_services_gui.py --self-test

Only the parent may request execution after reviewing a new build and freeze:
  python -B tools/tests/test_accessibility_services_gui.py --execute --build-ready \
    --freeze FREEZE.json --freeze-sha256 SHA256 --exe-sha256 SHA256

The freeze is one JSON object with scope=SCOPE, version, build, exe_sha256,
sources={project-relative path: SHA256}, build_files={build-relative path: SHA256},
and with_music=true for the parent's eight-session plan. --readiness lists every required input. All runtime
assets must be bound; lang_enum.h, both compiled lng/vstrings pairs and
rockbox-info.txt must also be bound. The build must be a new central development
build/fullinstall, never an installed release. An existing manifest must be bound.

Assets are copied once for synthetic PL/EN profiles; the EXE is moved and restored
using ExecutableLoan. No user profile is copied. Sessions, raw keys/logs/PCM,
source identities and failures remain in central Workspace. Acceptance excludes
touch, physical hardware/RF, NVDA, human listening and flash durability.
Live settling reads the separately retained optional stdio observation tap;
the original exclusive SDL disk PCM is read only after shutdown for acceptance.
"""

import argparse
import array
import ast
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import traceback
import unittest
from unittest import mock
import uuid
import wave

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SCOPE = "publication-position-20261021/services-gui"
EXPECTED_VERSION = "0ed3734e5e-espeak-r34-hibyr1-win-alpha17-20261021"
LANGUAGES = ("polski", "english")
SOURCE_PATHS = (
    "apps/accessibility.c", "apps/accessibility.h", "apps/accessibility_buttons.c",
    "apps/accessibility_buttons.h", "apps/accessibility_gesture.h",
    "apps/accessibility_typing.c", "apps/accessibility_typing.h",
    "apps/accessibility_touch.c", "apps/accessibility_touch.h",
    "apps/accessibility_touch_wake.c", "apps/accessibility_touch_wake.h",
    "apps/accessibility_screen.c", "apps/accessibility_screen.h",
    "apps/accessibility_shortcut.c", "apps/accessibility_shortcut.h",
    "apps/accessibility_services.c", "apps/accessibility_services.h",
    "apps/tts.c", "apps/tts.h", "apps/talk.c", "apps/voice_thread.c", "apps/settings.c", "apps/gui/option_select.c",
    "apps/action.c", "apps/action.h", "apps/gui/list.c", "apps/gui/list.h", "apps/menu.c", "apps/menus/display_menu.c",
    "apps/settings.h", "apps/settings_list.c", "apps/plugin.h", "apps/hiby_connectivity.c",
    "apps/hiby_connectivity.h", "apps/hiby_bluetooth.c", "apps/main.c", "apps/SOURCES",
    "apps/hiby_bluetooth.h", "apps/hiby_bluetooth_service.c", "apps/hiby_bluetooth_service.h",
    "apps/hiby_bluetooth_settings.c", "apps/hiby_bluetooth_settings.h",
    "apps/bluetooth_policy.c", "apps/bluetooth_policy.h",
    "firmware/target/hosted/hiby/bluetooth-hiby.c", "firmware/target/hosted/hiby/bluetooth-hiby.h",
    "firmware/target/hosted/hiby/bluetooth-monitor-hiby.c",
    "firmware/target/hosted/hiby/bluetooth-monitor-hiby.h",
    "firmware/target/hosted/hiby/pcm-hiby.c", "firmware/target/hosted/hiby/pcm-hiby.h",
    "apps/menus/main_menu.c", "apps/menus/settings_menu.c",
    "apps/menus/exported_menus.h",
    "apps/keymaps/keymap-hibyr1.c", "apps/lang/english.lang", "apps/lang/polski.lang",
    "uisimulator/buttonmap/hiby-r1.c", "firmware/target/hosted/sdl/button-sdl.c",
    "firmware/target/hosted/sdl/system-sdl.c", "firmware/target/hosted/sdl/pcm-sdl.c",
    "firmware/target/hosted/hiby/r1/button-target.h", "firmware/drivers/button.c",
    "firmware/drivers/touchscreen.c", "firmware/export/touchscreen.h",
    "firmware/target/hosted/button-devinput.c", "firmware/target/hosted/hiby/r1/button-r1.c",
    "firmware/kernel/include/tick.h", "firmware/export/backlight.h", "firmware/export/config.h",
    "firmware/export/config/hibyr1.h",
    "docs/ACCESSIBILITY-SHORTCUT.md", "docs/ACCESSIBILITY-SHORTCUT-PL.md",
    "docs/ACCESSIBILITY-BUTTONS.md", "docs/ACCESSIBILITY-BUTTONS-PL.md",
    "docs/ACCESSIBILITY-TOUCH.md", "docs/ACCESSIBILITY-TOUCH-PL.md",
    "docs/HIBY-R1-CONTROLS.md", "docs/HIBY-R1-CONTROLS-PL.md",
    "docs/INTERFACE-APPEARANCE.md", "docs/INTERFACE-APPEARANCE-PL.md",
    "docs/HIBY-R1-CONNECTIVITY.md", "docs/HIBY-R1-CONNECTIVITY-PL.md",
    "docs/ACCESSIBILITY-CURTAIN.md", "docs/ACCESSIBILITY-CURTAIN-PL.md",
    "docs/ACCESSIBILITY-SCREEN.md", "docs/ACCESSIBILITY-SCREEN-PL.md",
    "tools/project_materials.py", "tools/tests/test_tts_simulator.py",
    "tools/tests/test_tts_recorder_gui.py", "tools/tests/test_tts_bookmarks_gui.py",
    "tools/tests/test_hiby_accessibility_gui.py",
    "tools/tests/test_accessibility_services_gui.py",
    "tools/tests/test_context_controls_gui.py",
    "tools/tests/test_touch_wake.py", "tools/tests/test_accessibility_gesture_profiles.py",
    "tools/tests/test_keyclick_gui.py", "apps/misc.c", "apps/misc.h", "apps/beep.c", "firmware/asm/beep.c",
    "tools/tests/test_sdl_audio_debug.py", "tools/tests/fixtures/sdl_audio_debug_fixture.c",
)
TRACE_SOURCES = {
    "firmware/target/hosted/sdl/pcm-sdl.c": "90483d7b1855a01c3ef50fb183fedc8160f8d705cb66a3d576448deb34b8ada7",
    "firmware/target/hosted/sdl/system-sdl.c": "3edbef03262a2ffaf8c316b2e5f0e993a98b9cae24dbeb9d59fdeaba23088a0e",
}
TRACE_FEATURES = (b"--debugaudio", b"audiodebug.raw", b"wbN\0", b"abN\0",
                  b"Audio debug file open", b"Audio debug file closed",
                  b"Audio debug file open failed", b"Audio debug file write failed",
                  b"Audio debug file close failed",
                  b"Audio debug format: rate=%d format=%u channels=%u frame_bytes=%lu")
RESOURCE_DIRECTORIES = (
    "backdrops", "codecs", "codepages", "espeak-data", "fonts", "icons", "langs", "themes", "wps",
)
RESOURCE_FILES = ("viewers.config", "tagnavi.config", "rockbox-info.txt")
METADATA_FILES = ("rockbox-info.txt", "lang_enum.h") + tuple(
    f"apps/lang/{language}.{extension}" for language in LANGUAGES for extension in ("lng", "vstrings"))
ACCESSIBILITY_BASELINE = (
    "talkbox_settings_menu", "accessibility_shortcut_menu",
    "talk_menu_item", "talk_dir_item", "talk_dir_clip_item", "talk_file_item",
    "talk_file_clip_item", "talk_filetype_item", "talk_battery_level_item", "talk_mixer_amp_item",
)
TALKBOX_BASELINE = (
    "tts_settings_menu", "tts_enabled_item", "tts_ducking_item", "tts_ducking_level_item",
    "tts_reader_settings_menu", "accessibility_touch_item", "accessibility_display_menu",
    "accessibility_typing_item", "list_boundary_feedback_item",
    "tts_announce_position_item", "tts_announce_dynamic_item",
)
ESPEAK_BASELINE = (
    "tts_language_item", "tts_variant_item", "tts_rate_item", "tts_rate_scale_item",
    "tts_pitch_item", "tts_volume_item", "tts_range_item", "tts_wordgap_item", "tts_punctuation_item",
)
SYSTEM_BASELINE = (
    "battery_menu", "disk_menu", "limits_menu", "volume_adjust_mode", "volume_adjust_norm_steps",
    "shortcuts_replaces_quickscreen", "morse_input", "car_adapter_mode_menu", "serial_bitrate",
    "accessory_supply", "lineout_onoff", "buttonlight_timeout", "buttonlight_brightness",
    "keyclick_menu", "touchpad_sensitivity", "touchpad_deadzone", "sel_softlock", "usb_menu",
    "governor", "use_led_indicators",
)
ACCESSIBILITY_ROWS = (
    "LANG_TALKBOX_SETTINGS", "LANG_ACCESSIBILITY_SHORTCUT",
    "LANG_VOICE_MENU", "LANG_VOICE_DIR", "LANG_VOICE_DIR_TALK", "LANG_VOICE_FILE",
    "LANG_VOICE_FILE_TALK", "LANG_VOICE_FILETYPE", "LANG_TALK_BATTERY_LEVEL", "LANG_TALK_MIXER_LEVEL",
)
TALKBOX_ROWS = (
    "LANG_TTS", "LANG_TTS_ENABLED", "LANG_TTS_DUCKING", "LANG_TTS_DUCKING_LEVEL",
    "LANG_TTS_READER_SETTINGS", "LANG_ACCESSIBILITY", "LANG_ACCESSIBILITY_DISPLAY_SETTINGS",
    "LANG_ACCESSIBILITY_TYPING_SETTINGS", "LANG_ACCESSIBILITY_LIST_BOUNDARY",
    "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TALKBOX_ANNOUNCE_DYNAMIC",
)
ESPEAK_ROWS = (
    "LANG_TTS_LANGUAGE", "LANG_TTS_VARIANT", "LANG_TTS_RATE", "LANG_TTS_RATE_SCALE",
    "LANG_TTS_PITCH", "LANG_TTS_VOLUME", "LANG_TTS_RANGE", "LANG_TTS_WORDGAP", "LANG_TTS_PUNCTUATION",
)
READER_ROWS = ("LANG_TTS_READER_UNIT", "LANG_TTS_READER_PAGE_LINES")
SHORTCUT_ROWS = ("LANG_ACCESSIBILITY_SHORTCUT_ENABLED", "LANG_ACCESSIBILITY_SHORTCUT_SERVICES")
SHORTCUT_SERVICE_ROWS = ("LANG_ACCESSIBILITY_SHORTCUT_ESPEAK", "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES",
                         "LANG_ACCESSIBILITY_ENABLED", "LANG_ACCESSIBILITY_CURTAIN")
BOUNDARY_CHOICES = ("LANG_ACCESSIBILITY_FEEDBACK_BOTH", "LANG_ACCESSIBILITY_FEEDBACK_SOUND",
                    "LANG_ACCESSIBILITY_FEEDBACK_SPEECH", "LANG_OFF")
POSITION_CHOICES = ("LANG_TALKBOX_POSITION_EVERYWHERE", "LANG_TALKBOX_POSITION_INTERFACE",
                    "LANG_TALKBOX_POSITION_FILES", "LANG_TALKBOX_POSITION_EXCEPT_SLIDERS", "LANG_OFF")
BUTTON_ROWS = tuple(
    (button, slot,
     "LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES" if button_index == 1 and slot_index == 1 else
     "LANG_ACCESSIBILITY_TOGGLE_ESPEAK" if button_index == 2 and slot_index == 1 else
     "LANG_ACCESSIBILITY_SYSTEM_DEFAULT")
    for button_index, button in enumerate((
        "LANG_ACCESSIBILITY_BUTTON_POWER", "LANG_ACCESSIBILITY_BUTTON_PLAY", "LANG_ACCESSIBILITY_BUTTON_NEXT",
        "LANG_ACCESSIBILITY_BUTTON_VOLUME_UP", "LANG_ACCESSIBILITY_BUTTON_VOLUME_DOWN"))
    for slot_index, slot in enumerate((
        "LANG_ACCESSIBILITY_SINGLE_PRESS", "LANG_ACCESSIBILITY_DOUBLE_PRESS",
        "LANG_ACCESSIBILITY_TRIPLE_PRESS", "LANG_ACCESSIBILITY_HOLD"))
) + (("LANG_RESET",),)
BUTTON_ROOT_ROWS = (
    "LANG_ACCESSIBILITY_INTERFACE_ACTIONS", "LANG_ACCESSIBILITY_PLAYBACK_ACTIONS",
    "LANG_ACCESSIBILITY_HOLD_TIME", "LANG_RESET", "LANG_ACCESSIBILITY_CONTROLS_GUIDE",
)
GUIDE_CONTEXT_ROWS = tuple("LANG_ACCESSIBILITY_DEFAULT_" + name for name in ("MENUS", "MUSIC", "TEXT", "KEYBOARD"))
GUIDE_ACTIONS = (
    (("LANG_ACCESSIBILITY_ACTIVATE", "LANG_ACCESSIBILITY_DEFAULT_POWER_HOLD"),
     ("LANG_BACK", "LANG_MAIN_MENU"),
     ("LANG_ACCESSIBILITY_ACTIVATE", "LANG_ACCESSIBILITY_CONTEXT"),
     ("LANG_ACCESSIBILITY_UP", "LANG_ACCESSIBILITY_VOLUME_UP"),
     ("LANG_ACCESSIBILITY_DOWN", "LANG_ACCESSIBILITY_VOLUME_DOWN")),
    (("LANG_ACCESSIBILITY_DEFAULT_MUSIC_PAUSE", "LANG_ACCESSIBILITY_DEFAULT_POWER_HOLD"),
     ("LANG_ACCESSIBILITY_DEFAULT_TRACK_PREVIOUS", "LANG_ACCESSIBILITY_DEFAULT_SEEK_BACK"),
     ("LANG_ACCESSIBILITY_DEFAULT_TRACK_NEXT", "LANG_ACCESSIBILITY_DEFAULT_SEEK_FORWARD"),
     ("LANG_ACCESSIBILITY_VOLUME_UP", "LANG_ACCESSIBILITY_VOLUME_UP"),
     ("LANG_ACCESSIBILITY_VOLUME_DOWN", "LANG_ACCESSIBILITY_VOLUME_DOWN")),
)
GUIDE_ROWS = tuple(tuple(row[:2] + (("LANG_ACCESSIBILITY_DEFAULT_MULTICLICK",) if index % 4 in (1, 2) else ()) +
                         (actions[index // 4][index % 4 == 3],)
                         for index, row in enumerate(BUTTON_ROWS[:20])) for actions in GUIDE_ACTIONS)
PLAYBACK_BUTTON_ROWS = tuple(
    row[:2] + (("LANG_ACCESSIBILITY_TOGGLE_ESPEAK" if index == 4 else
                "LANG_ACCESSIBILITY_UNASSIGNED" if index == 9 else row[2]),)
    for index, row in enumerate(BUTTON_ROWS[:20])
) + BUTTON_ROWS[20:]
TOUCH_ROWS = (
    "LANG_ACCESSIBILITY_ENABLED", "LANG_ACCESSIBILITY_GESTURES", "LANG_ACCESSIBILITY_TOUCH_HOLD_TIME",
    "LANG_ACCESSIBILITY_STROKE_REPEAT", "LANG_ACCESSIBILITY_EMPTY_FEEDBACK",
    "LANG_KEYCLICK_EMPTY_PITCH", "LANG_KEYCLICK_EMPTY_SEMITONES", "LANG_RESET",
)
EMPTY_FEEDBACK_CHOICES = (
    "LANG_ACCESSIBILITY_EMPTY_SOUND_ONLY", "LANG_ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH",
    "LANG_ACCESSIBILITY_EMPTY_SPEECH_ONLY",
)
SCREEN_STATE_ROWS = (
    "LANG_ACCESSIBILITY_SCREEN_UNLOCK_NOTICE", "LANG_ACCESSIBILITY_SCREEN_LOCK_NOTICE",
)
ACCESSIBILITY_DISPLAY_ROWS = ("LANG_ACCESSIBILITY_CURTAIN", "LANG_ACCESSIBILITY_SCREEN_STATE")
TOUCH_WAKE_ROWS = ("LANG_TOUCH_WAKE_SINGLE", "LANG_TOUCH_WAKE_DOUBLE", "LANG_TOUCH_WAKE_TRIPLE")
TOUCH_WAKE_CHOICES = ("LANG_OFF", "LANG_TOUCH_WAKE_LIGHT", "LANG_TOUCH_WAKE_UNLOCK")
SYSTEM_TOUCH_ROWS = (
    "LANG_TOUCHSCREEN_MODE", "LANG_TOUCHSCREEN_FLICK_SHORTCUTS", "LANG_LIST_LINE_PADDING",
    "LANG_TOUCHSCREEN_CALIBRATE", "LANG_TOUCHSCREEN_RESET_CALIBRATION", "LANG_TOUCH_GESTURE_SENSITIVITY",
    "LANG_ACCESSIBILITY_UNLOCK_ANY_BUTTON", "LANG_ACCESSIBILITY_LOCKED_BUTTONS", "LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT",
    "LANG_TOUCH_WAKE_SETTINGS",
)
AUTOLOCK_DURATIONS = (-1, 0, 5, 10, 15, 30, 45, 60, 120, 180, 300, 600)
AUTOLOCK_CHOICES = ("LANG_ACCESSIBILITY_AUTOLOCK_LEGACY", "LANG_OFF") + tuple(
    (seconds, "VOICE_SECONDS") for seconds in AUTOLOCK_DURATIONS[2:])
VOICE_ONLY_IDS = ("VOICE_SECONDS", "VOICE_SECOND", "VOICE_PERCENT", "VOICE_OF")
TYPING_ROWS = (
    "LANG_ACCESSIBILITY_TYPING_MODE", "LANG_ACCESSIBILITY_ECHO", "LANG_ACCESSIBILITY_CAPITALS",
    "LANG_ACCESSIBILITY_CAPITAL_PITCH_PERCENT", "LANG_ACCESSIBILITY_DELETE_ECHO",
)
TYPING_CHOICES = (
    ("LANG_ACCESSIBILITY_TYPING_MODE", ("LANG_ACCESSIBILITY_TYPING_LIFT",
       "LANG_ACCESSIBILITY_TYPING_DOUBLE_TAP", "LANG_ACCESSIBILITY_TYPING_ARROWS")),
    ("LANG_ACCESSIBILITY_ECHO", ("LANG_ACCESSIBILITY_ECHO_BOTH", "LANG_ACCESSIBILITY_ECHO_NONE",
       "LANG_ACCESSIBILITY_ECHO_CHARACTERS", "LANG_ACCESSIBILITY_ECHO_WORDS")),
    ("LANG_ACCESSIBILITY_CAPITALS", ("LANG_ACCESSIBILITY_ECHO_NONE", "LANG_ACCESSIBILITY_CAPITAL_SPOKEN",
       "LANG_ACCESSIBILITY_CAPITAL_PITCH")),
    ("LANG_ACCESSIBILITY_DELETE_ECHO", ("LANG_ACCESSIBILITY_DELETED_CHARACTER",
       "LANG_ACCESSIBILITY_CHARACTER_ONLY", "LANG_ACCESSIBILITY_ECHO_NONE")),
)
GESTURE_ROWS = (
    "LANG_ACCESSIBILITY_SWIPE_LEFT", "LANG_ACCESSIBILITY_SWIPE_RIGHT",
    "LANG_ACCESSIBILITY_SWIPE_UP", "LANG_ACCESSIBILITY_SWIPE_DOWN",
    "LANG_ACCESSIBILITY_SWIPE_LEFT_RIGHT", "LANG_ACCESSIBILITY_SWIPE_LEFT_UP",
    "LANG_ACCESSIBILITY_SWIPE_LEFT_DOWN", "LANG_ACCESSIBILITY_SWIPE_RIGHT_LEFT",
    "LANG_ACCESSIBILITY_SWIPE_RIGHT_UP", "LANG_ACCESSIBILITY_SWIPE_RIGHT_DOWN",
    "LANG_ACCESSIBILITY_SWIPE_UP_LEFT", "LANG_ACCESSIBILITY_SWIPE_UP_RIGHT",
    "LANG_ACCESSIBILITY_SWIPE_UP_DOWN", "LANG_ACCESSIBILITY_SWIPE_DOWN_LEFT",
    "LANG_ACCESSIBILITY_SWIPE_DOWN_RIGHT", "LANG_ACCESSIBILITY_SWIPE_DOWN_UP",
    "LANG_ACCESSIBILITY_DOUBLE_TAP", "LANG_ACCESSIBILITY_HOLD", "LANG_ACCESSIBILITY_TRIPLE_TAP",
    "LANG_ACCESSIBILITY_DOUBLE_TAP_HOLD",
)
GESTURE_ACTION_ROWS = (
    "LANG_ACCESSIBILITY_UNASSIGNED", "LANG_ACCESSIBILITY_UP", "LANG_ACCESSIBILITY_DOWN",
    "LANG_ACCESSIBILITY_LEFT", "LANG_ACCESSIBILITY_RIGHT", "LANG_ACCESSIBILITY_ACTIVATE", "LANG_BACK",
    "LANG_MAIN_MENU", "LANG_ACCESSIBILITY_CONTEXT", "LANG_ACCESSIBILITY_VOLUME_UP",
    "LANG_ACCESSIBILITY_VOLUME_DOWN", "LANG_ACCESSIBILITY_BATTERY", "LANG_ACCESSIBILITY_LAUNCH",
    "LANG_ACCESSIBILITY_SHUTDOWN", "LANG_ACCESSIBILITY_LOCK", "LANG_ACCESSIBILITY_CURTAIN",
    "LANG_ACCESSIBILITY_ACTION_TIME", "LANG_ACCESSIBILITY_TOGGLE_ESPEAK", "LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES",
    "LANG_ACCESSIBILITY_TOGGLE_TOUCH", "LANG_ACCESSIBILITY_ACTION_DATE", "LANG_ACCESSIBILITY_ACTION_SUMMARY",
    "LANG_ACCESSIBILITY_ACTION_FIRST", "LANG_ACCESSIBILITY_ACTION_LAST",
    "LANG_ACCESSIBILITY_ACTION_PAGE_FIRST", "LANG_ACCESSIBILITY_ACTION_PAGE_LAST",
    "LANG_ACCESSIBILITY_SHORTCUT_ACTION",
)
BLUETOOTH_ROOT_ROWS = (
    ("LANG_HIBY_BT_TITLE", "LANG_ON", "LANG_HIBY_BT_STATUS", "LANG_HIBY_BT_UNAVAILABLE"),
    ("LANG_HIBY_BT_PAIRED_DEVICES",), ("LANG_HIBY_BT_PAIR_NEW",),
    ("LANG_HIBY_BT_DISCONNECT",), ("LANG_HIBY_BT_STATUS",),
    ("LANG_HIBY_BT_SETTINGS",), ("LANG_HIBY_BT_CONNECT_LAST",),
)
BLUETOOTH_PREFERENCE_ROWS = (
    ("LANG_HIBY_BT_AUTOCONNECT", "LANG_HIBY_BT_AUTO_STARTUP_LOSS"),
    ("LANG_HIBY_BT_RETRY_WINDOW", "LANG_HIBY_BT_RETRY_120"),
    ("LANG_HIBY_BT_LOSS_BEHAVIOR", "LANG_HIBY_BT_LOSS_PAUSE"),
    ("LANG_HIBY_BT_ANNOUNCEMENTS", "LANG_ON"),
    ("LANG_HIBY_BT_LAST_DEVICE", "LANG_HIBY_BT_NO_LAST_DEVICE"),
)
BLUETOOTH_CHOICES = (
    ("LANG_OFF", "LANG_HIBY_BT_AUTO_STARTUP", "LANG_HIBY_BT_AUTO_STARTUP_LOSS"),
    ("LANG_HIBY_BT_RETRY_30", "LANG_HIBY_BT_RETRY_60", "LANG_HIBY_BT_RETRY_120", "LANG_HIBY_BT_RETRY_300"),
    ("LANG_HIBY_BT_LOSS_PAUSE", "LANG_HIBY_BT_LOSS_CONTINUE"),
    ("LANG_OFF", "LANG_ON"),
)
REQUIRED_IDS = tuple(dict.fromkeys(ACCESSIBILITY_ROWS + TALKBOX_ROWS + ESPEAK_ROWS + READER_ROWS +
                                 tuple(identifier for rows in (BLUETOOTH_ROOT_ROWS, BLUETOOTH_PREFERENCE_ROWS, BLUETOOTH_CHOICES)
                                       for row in rows for identifier in row) +
                                 SHORTCUT_ROWS + SHORTCUT_SERVICE_ROWS + BOUNDARY_CHOICES + POSITION_CHOICES +
                                 TOUCH_ROWS + TYPING_ROWS + EMPTY_FEEDBACK_CHOICES + SCREEN_STATE_ROWS + SYSTEM_TOUCH_ROWS +
                                 ACCESSIBILITY_DISPLAY_ROWS + TOUCH_WAKE_ROWS + TOUCH_WAKE_CHOICES +
                                 tuple(identifier for _, choices in TYPING_CHOICES for identifier in choices) +
                                 GESTURE_ROWS + GESTURE_ACTION_ROWS + BUTTON_ROOT_ROWS + GUIDE_CONTEXT_ROWS +
                                 tuple(identifier for rows in GUIDE_ROWS for row in rows for identifier in row) +
                                 tuple(identifier for row in BUTTON_ROWS for identifier in row) + (
    "LANG_SETTINGS", "LANG_GENERAL_SETTINGS", "LANG_VOICE", "LANG_SYSTEM",
    "LANG_TTS_SYSTEM", "LANG_TTS_DEFAULT_VARIANT",
    "LANG_DISPLAY", "LANG_LCD_MENU", "LANG_BRIGHTNESS", "LANG_TOUCHSCREEN_SETTINGS", "LANG_ACCESSIBILITY_BUTTONS", "LANG_KEYCLICK",
    "LANG_SET_BOOL_NO", "LANG_SET_BOOL_YES", "LANG_HIBY_BT_DONE", "LANG_HIBY_CONNECTIVITY_FAILED", "LANG_HIBY_BT_WORKING",
    "LANG_BACKLIGHT", "LANG_ALWAYS", "LANG_NEVER",
    "LANG_HIBY_CONNECTIVITY_STORAGE_ERROR", "LANG_HIBY_BT_CANCELLED", "LANG_HIBY_BT_TIMEOUT",
    "LANG_HIBY_BT_BUSY", "LANG_HIBY_BT_AIRPLANE_MODE",
    "LANG_DIR_BROWSER", "LANG_CONNECTIVITY", "LANG_HIBY_WIFI", "LANG_HIBY_BT_TITLE",
    "LANG_HIBY_AIRPLANE_MODE", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE",
    "LANG_ACCESSIBILITY_AUTOLOCK_LEGACY", "LANG_HIBY_WIFI_DRIVER_SUSPENDED", "LANG_ACCESSIBILITY_RESET_PARTIAL",
    "LANG_HIBY_CONNECTIVITY_PARTIAL", "LANG_HIBY_WIFI_STARTUP", "LANG_ON", "LANG_OFF", "LANG_SHUTTINGDOWN",
    "LANG_ACCESSIBILITY_TOUCH_ON", "LANG_ACCESSIBILITY_TOUCH_OFF",
    "LANG_ACCESSIBILITY_LIST_START", "LANG_ACCESSIBILITY_LIST_END",
    "LANG_ACCESSIBILITY_TOGGLE_ESPEAK", "LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES",
    "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON",
    "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON",
    "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF", "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING",
)))
LIMITATIONS = (
    "No physical R1, touchscreen/gesture, RF, NVDA/UIA or human-audibility acceptance.",
    "Live tap/log/PCM settling is not a firmware or hardware speech-completion receipt; full SDL disk PCM is validated offline.",
    "The buffered stdio tap omits paused/no-data device silence and uses independent offsets; converted branches record converted data.",
    "Simulator unavailable/partial radio states are required, never evidence of real radio operation.",
    "Simulator unavailable Bluetooth cannot establish busy native enable responsiveness or repeated-activation safety; native controller regressions and a physical retest are separate requirements.",
    "Saved next-start config snapshots are checked after graceful exit; live restart and flash durability are not established.",
    "Menu evidence is ordered spoken navigation plus frozen source layout, not OCR or visual pixel recognition.",
    "New gesture/action selectors are browsed and canceled only; mapped date/summary/touch-toggle effects and touch repeats remain untested.",
    "Physical profile menus are browsed without edits; seeded asymmetric mappings exercise WPS versus background-music menus, not mapping trials, physical timing or device acceptance.",
    "Typing menus are browsed only; actual typing echo/capital/deletion effects, sensitivity and lock policies rely on separate C fixtures, not this service GUI.",
    "The empty-feedback picker is traversed and returned to its sound-only default without saving a profile; actual empty touch feedback relies on separate compiled/PCM tests.",
    "Service fixtures explicitly disable keyclick for PCM isolation; fresh Moderate defaults require the independent positive compilation regression.",
)
PRESS_ACK_TIMEOUT = 0.24
PRESS_MAX_DOWN = 0.28
RAPID_NAVIGATION_MAX_SPACING = 0.2


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def bluetooth_layout_action_count():
    return (1 + len(BLUETOOTH_ROOT_ROWS) + 5 + 1 + len(BLUETOOTH_PREFERENCE_ROWS) +
            sum(1 + len(choices) + 1 + (index > 0) for index, choices in enumerate(BLUETOOTH_CHOICES)) + 2)


def session_action_budget(scenario, timeout=25):
    require(scenario in ("services", "missing-voice", "layout-connectivity", "music"), "Unknown GUI scenario")
    require(10 <= timeout <= 60, "Invalid bounded action timeout")
    if scenario == "layout-connectivity":
        return 3600 + bluetooth_layout_action_count() * (2 * timeout + PRESS_MAX_DOWN + 0.4)
    return 600


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def sha256_value(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value)) and value != "0" * 64


def relative_name(value):
    require(isinstance(value, str) and "\\" not in value and ":" not in value,
            "Freeze names must be relative POSIX paths")
    path = PurePosixPath(value)
    require(value == path.as_posix() and not path.is_absolute() and bool(path.parts) and
            all(part not in (".", "..") for part in path.parts), "Unsafe freeze path")
    return value


def validate_freeze_shape(freeze, exe_sha256):
    require(freeze.get("scope") == SCOPE, "Freeze belongs to another stage")
    require(sha256_value(exe_sha256) and freeze.get("exe_sha256") == exe_sha256,
            "Explicit EXE hash must match the parent's freeze")
    require(freeze.get("version") == EXPECTED_VERSION, "The newly frozen alpha17-20261021 version is required")
    require(freeze.get("with_music") is True, "Parent's final plan requires with_music=true and eight sessions")
    for field in ("sources", "build_files"):
        require(isinstance(freeze.get(field), dict) and freeze[field], "Missing frozen " + field)
        names = []
        for name, checksum in freeze[field].items():
            names.append(relative_name(name).casefold())
            require(sha256_value(checksum), "Invalid input hash: " + name)
        require(len(names) == len(set(names)), "Case-colliding freeze names")
    require(set(SOURCE_PATHS) <= set(freeze["sources"]), "Freeze omits required source/helper inputs")
    require(set(METADATA_FILES) <= set(freeze["build_files"]), "Freeze omits compiled metadata")
    require(freeze["build_files"].get("rockboxui.exe") == exe_sha256, "Unbound EXE in build inputs")


def enum_values(text, name):
    found = re.search(r"enum\s+" + re.escape(name) + r"\s*\{([^}]+)\}", text, re.DOTALL)
    require(found is not None, "Missing source enum: " + name)
    values, number = {}, 0
    for row in found[1].split(","):
        parts = [part.strip() for part in row.strip().split("=")]
        if not parts[0]:
            continue
        require(len(parts) <= 2 and re.fullmatch(r"[A-Z_0-9]+", parts[0]), "Unsupported enum declaration")
        if len(parts) == 2:
            number = values[parts[1]] if parts[1] in values else int(parts[1], 0)
        values[parts[0]] = number
        number += 1
    return values


def input_button_contract():
    header = (ROOT / "firmware/target/hosted/hiby/r1/button-target.h").read_text(encoding="utf-8")
    mapping = (ROOT / "uisimulator/buttonmap/hiby-r1.c").read_text(encoding="utf-8")
    masks = {}
    for key, sdl, field, expected in (("Left", "LEFT", "PLAY", 8), ("Right", "RIGHT", "NEXT", 4),
                                      ("Up", "UP", "VOL_UP", 16), ("Down", "DOWN", "VOL_DOWN", 32),
                                      ("Insert", "INSERT", "POWER", 1)):
        values = re.findall(r"^#define\s+BUTTON_" + field + r"\s+(0x[0-9a-fA-F]+)\b", header, re.MULTILINE)
        found = re.search(r"case SDLK_" + sdl + r":(?:(?!return).)*?return (BUTTON_\w+);", mapping, re.DOTALL)
        require(len(values) == 1 and int(values[0], 16) == expected and found is not None and
                found[1] == "BUTTON_" + field, "Frozen physical SDL button mapping changed: " + key)
        masks[key] = int(values[0], 16)
    driver = (ROOT / "firmware/drivers/button.c").read_text(encoding="utf-8")
    tick = (ROOT / "firmware/kernel/include/tick.h").read_text(encoding="utf-8")
    require(re.search(r"^#define\s+REPEAT_START\s+\(30\*HZ/100\)", driver, re.MULTILINE) and
            re.search(r"^#define\s+HZ\s+100\b", tick, re.MULTILINE) and PRESS_MAX_DOWN < 0.3,
            "Cannot establish the frozen 300ms first-repeat boundary")
    return masks


def input_symbol_layout(executable, nm_output):
    from test_tts_recorder_gui import pe_layout
    layout = pe_layout(executable)
    matches = re.findall(r"^\s*([0-9a-fA-F]+)\s+([A-Za-z])\s+lastbtn\s*$", nm_output, re.MULTILINE)
    require(len(matches) == 1 and matches[0][1] in "bB", "Expected exactly one BSS lastbtn symbol")
    address = int(matches[0][0], 16)
    rva = address - layout["preferred_base"]
    sections = [section for section in layout["sections"] if section["name"] == ".bss" and
                section["rva"] <= rva and rva + 4 <= section["rva"] + section["size"] and
                section["flags"] & 0xc0000000 == 0xc0000000]
    require(rva >= 0 and address % 4 == 0 and rva + 4 <= layout["image_size"] and len(sections) == 1,
            "lastbtn is outside one aligned readable/writable BSS range")
    return dict(layout, sha256=digest(executable), button_masks=input_button_contract(),
                nm_symbol_line=f"{address:016x} {matches[0][1]} lastbtn",
                symbols={"lastbtn": {"preferred_address": address, "rva": rva, "size": 4, "section": ".bss"}})


def prepare_input_layout(executable, expected_hash):
    require(digest(executable) == expected_hash, "EXE changed before input-symbol preparation")
    tool = shutil.which("x86_64-w64-mingw32-nm") or shutil.which("nm")
    if tool:
        command = [tool, "--defined-only", "--numeric-sort", str(executable)]
    else:
        require(shutil.which("wsl.exe") is not None, "Input acknowledgement requires nm or WSL nm before loan")
        converted = subprocess.run(["wsl.exe", "--exec", "wslpath", "-a", str(executable)],
                                   capture_output=True, text=True, timeout=15, check=True)
        command = ["wsl.exe", "--exec", "x86_64-w64-mingw32-nm", "--defined-only", "--numeric-sort",
                   converted.stdout.strip()]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    layout = input_symbol_layout(executable, result.stdout)
    require(layout["sha256"] == expected_hash and digest(executable) == expected_hash,
            "EXE changed while resolving input symbols")
    return layout


def mapping_contract():
    source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
    actions = enum_values(source, "accessibility_action")
    slots = enum_values((ROOT / "apps/accessibility_buttons.h").read_text(), "accessibility_button_slot")
    strokes = enum_values((ROOT / "apps/accessibility_gesture.h").read_text(), "accessibility_stroke")
    require('#define ACCESSIBILITY_HEADER "RBACCESSIBILITY:11\\n"' in source and
            '#define ACCESSIBILITY_V10_HEADER "RBACCESSIBILITY:10\\n"' in source and
            '#define ACCESSIBILITY_V9_HEADER "RBACCESSIBILITY:9\\n"' in source and
            '#define ACCESSIBILITY_V8_HEADER "RBACCESSIBILITY:8\\n"' in source and
            '#define ACCESSIBILITY_V7_HEADER "RBACCESSIBILITY:7\\n"' in source,
            "This stage requires the v11 writer and retained v10/v9/v8/v7 compatibility readers")
    require(actions["ACCESSIBILITY_ACTION_TOGGLE_ESPEAK"] == 17 and
            actions["ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES"] == 18 and
            actions["ACCESSIBILITY_ACTION_TOGGLE_TOUCH"] == 19 and
            actions["ACCESSIBILITY_ACTION_DATE"] == 20 and
            actions["ACCESSIBILITY_ACTION_SUMMARY"] == 21 and
            actions["ACCESSIBILITY_ACTION_FIRST"] == 22 and
            actions["ACCESSIBILITY_ACTION_LAST"] == 23 and
            actions["ACCESSIBILITY_ACTION_PAGE_FIRST"] == 24 and
            actions["ACCESSIBILITY_ACTION_PAGE_LAST"] == 25 and
            actions["ACCESSIBILITY_ACTION_SHORTCUT"] == 26 and
            actions["ACCESSIBILITY_ACTION_SYSTEM"] == 27, "Service/list action IDs changed")
    require(strokes["ACCESSIBILITY_STROKE_COUNT"] == 17 and
            '#define ACCESSIBILITY_SLOT_COUNT (ACCESSIBILITY_STROKE_COUNT + 4)' in source,
            "Reviewed gesture slot layout changed")
    return {"actions": actions, "slots": slots, "gesture_count": strokes["ACCESSIBILITY_STROKE_COUNT"] + 3,
            "source_version": 11, "profile_version": 11}


def mapping_profile(contract):
    actions, slots = contract["actions"], contract["slots"]
    lines = ["RBACCESSIBILITY:11", "enabled:0", "click:7", "hold:700", "touch_hold:900", "stroke_repeat:0",
             "empty_pitch:1", "empty_semitones:-4"]
    lines += [f"gesture:{slot}:0:0" for slot in range(1, contract["gesture_count"] + 1)]
    lines += [f"playback_gesture:{slot}:0:0" for slot in range(1, contract["gesture_count"] + 1)]
    for button in range(5):
        for slot in range(slots["ACCESSIBILITY_BUTTON_SLOT_COUNT"]):
            action = actions["ACCESSIBILITY_ACTION_SYSTEM"]
            if slot == slots["ACCESSIBILITY_BUTTON_DOUBLE"] and button in (1, 2):
                action = actions["ACCESSIBILITY_ACTION_TOGGLE_ESPEAK" if button == 2 else
                                 "ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES"]
            lines.append(f"button:{button}:{slot}:{action}:0")
    for button in range(5):
        for slot in range(slots["ACCESSIBILITY_BUTTON_SLOT_COUNT"]):
            action = actions["ACCESSIBILITY_ACTION_SYSTEM"]
            if button == 1 and slot == slots["ACCESSIBILITY_BUTTON_SINGLE"]:
                action = actions["ACCESSIBILITY_ACTION_TOGGLE_ESPEAK"]
            elif slot == slots["ACCESSIBILITY_BUTTON_DOUBLE"]:
                if button == 1:
                    action = actions["ACCESSIBILITY_ACTION_TOGGLE_VOICE_FILES"]
                elif button == 2:
                    action = actions["ACCESSIBILITY_ACTION_NONE"]
            lines.append(f"playback_button:{button}:{slot}:{action}:0")
    lines += [f"target:{target}:" for target in range(4)]
    return "\n".join(lines) + "\n"


def parse_mapping_profile(data):
    from test_hiby_accessibility_gui import parse_accessibility_config
    parsed = parse_accessibility_config(data)
    require(parsed["version"] == 11, "Services profile must use the current v11 format")
    return parsed


def session_mapping_profile(contract, scenario):
    profile = mapping_profile(contract)
    if scenario == "services":
        for prefix in ("button", "playback_button"):
            profile = profile.replace(prefix + ":0:1:27:0\n", prefix + ":0:1:19:0\n", 1)
            profile = profile.replace(prefix + ":0:2:27:0\n", prefix + ":0:2:26:0\n", 1)
    if scenario == "missing-voice":
        profile = re.sub(r'^playback_button:.*\n', '', profile, flags=re.MULTILINE)
        profile = re.sub(r'^playback_gesture:.*\n', '', profile, flags=re.MULTILINE)
        profile = profile.replace("RBACCESSIBILITY:11\n", "RBACCESSIBILITY:8\n", 1)
        profile = re.sub(r'^(button:[0-4]:[0-3]:)27:', r'\g<1>22:', profile, flags=re.MULTILINE)
    return profile


def mapping_file_identity(path):
    from test_hiby_accessibility_gui import parse_accessibility_config
    data = path.read_bytes()
    parsed = parse_accessibility_config(data)
    metadata = path.stat()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "mtime_ns": metadata.st_mtime_ns,
            "version": parsed["version"], "profiles_equal": parsed["buttons"] == parsed["playback_buttons"] and
            parsed["button_launch"] == parsed["playback_button_launch"]}


def verify_mapping_read_only(path, before):
    require(mapping_file_identity(path) == before, "Read-only profile loading/navigation rewrote accessibility.cfg")
    return dict(before, unchanged=True, scope="Synthetic profile hash/size/mtime preserved; legacy v8 read must not save v11 eagerly")


def menu_items(source, name):
    found = re.search(r"MAKE_MENU\(\s*" + re.escape(name) + r"\s*,(.*?)\);", source, re.DOTALL)
    require(found is not None, "Missing menu declaration: " + name)
    return re.findall(r"&([a-zA-Z_][a-zA-Z_0-9]*)", found[1])


def source_layout():
    settings = (ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
    main = (ROOT / "apps/menus/main_menu.c").read_text(encoding="utf-8")
    display = (ROOT / "apps/menus/display_menu.c").read_text(encoding="utf-8")
    accessibility = menu_items(settings, "voice_settings_menu")
    require(accessibility == list(ACCESSIBILITY_BASELINE),
            "Accessibility must keep Talkbox first, exactly one grouped shortcut and no physical button menu")
    require(len(re.findall(r'\bMAKE_MENU\(accessibility_shortcut_menu,', settings)) == 1,
            "Duplicate accessibility shortcut menu")
    menus = {"settings": menu_items(main, "main_menu_"),
             "general": menu_items(settings, "settings_menu_item"),
             "system": menu_items(settings, "system_menu"), "accessibility": accessibility,
             "talkbox": menu_items(settings, "talkbox_settings_menu"),
             "espeak": menu_items(settings, "tts_settings_menu"),
             "reader": menu_items(settings, "tts_reader_settings_menu"),
             "information": menu_items(main, "info_menu"),
             "screen_state": menu_items(settings, "accessibility_screen_menu"),
             "accessibility_display": menu_items(settings, "accessibility_display_menu"),
             "shortcut": menu_items(settings, "accessibility_shortcut_menu"),
             "shortcut_services": menu_items(settings, "accessibility_shortcut_services_menu"),
             "touchscreen": menu_items(display, "touchscreen_menu")}
    require(menus["talkbox"] == list(TALKBOX_BASELINE),
            "Talkbox must contain engine, enable switch, ducking, reader and its existing accessibility subgroups")
    require(menus["espeak"] == list(ESPEAK_BASELINE),
            "eSpeak must contain exactly the nine synthesis parameters")
    require(menus["reader"] == ["tts_reader_unit_item", "tts_reader_page_lines_item"],
            "Text reader settings must retain navigation unit and lines per page")
    require(menus["shortcut"] == ["accessibility_shortcut_enabled_item", "accessibility_shortcut_services_menu"],
            "Grouped shortcut must have one enable switch and its service selection")
    require(menus["shortcut_services"] == ["accessibility_shortcut_espeak_item", "accessibility_shortcut_voice_files_item",
            "accessibility_shortcut_touch_item", "accessibility_shortcut_curtain_item"],
            "Grouped shortcut service choices are missing, duplicated or reordered")
    require(menus["screen_state"] == ["accessibility_screen_unlock_item", "accessibility_screen_lock_item"],
            "Screen state announcements must contain exactly unlock and lock announcements, not canonical control aliases")
    require(menus["accessibility_display"] == ["accessibility_curtain_item", "accessibility_screen_menu"],
            "Accessibility screen settings must group curtain and state announcements without hardware aliases")
    require(menus["touchscreen"] == ['touch_mode', 'touch_enable_flick_shortcuts', 'list_line_padding',
        'touchscreen_menu_calibrate', 'touchscreen_menu_reset_calibration', 'touchscreen_sensitivity_item',
        'touchscreen_unlock_any_button_item', 'touchscreen_locked_buttons_item', 'touchscreen_autolock_item',
        'touchscreen_wake_item'],
        'System touchscreen settings must retain the timer followed by touch wake settings')
    require([item for item in menus["system"] if item not in ("touchscreen_menu", "accessibility_buttons_item")] ==
            list(SYSTEM_BASELINE), "Existing System settings order changed")
    keyclick = menus["system"].index("keyclick_menu")
    require(menus["system"][keyclick - 2:keyclick] == ["touchscreen_menu", "accessibility_buttons_item"] and
            menus["system"].count("touchscreen_menu") == menus["system"].count("accessibility_buttons_item") == 1,
            "System must have touchscreen and physical button settings immediately before Keyclick")
    require(menus["settings"].count("connectivity_item") == 1, "Connectivity must be directly in Settings")
    require([item for item in menus["settings"] if item != "connectivity_item"] ==
            ["sound_settings", "playback_settings", "settings_menu_item", "theme_menu",
             "recording_settings", "timedate_item", "main_menu_config_item", "manage_settings"],
            "Existing Settings order changed")
    require(menus["general"] == ["wps_settings", "playlist_settings", "file_menu", "tagcache_menu",
            "display_menu", "system_menu", "startup_shutdown_menu", "bookmark_settings_menu",
            "autoresume_menu", "browse_langs", "voice_settings_menu"], "Existing General settings order changed")
    for name in ("general", "system", "information"):
        require(not any("bluetooth" in item or "wifi" in item or "connectivity" in item
                        for item in menus[name]), "Old/duplicate connectivity row remains in " + name)
    require(not any(name in menu_items(settings, "keyclick_menu") for name in
                    ("keyclick_empty_pitch", "keyclick_empty_semitones")),
            "Empty exploration pitch controls must not remain aliased in System interface sounds")
    for name, items in menus.items():
        require(len(items) == len(set(items)), "Duplicate menu reference: " + name)
    return menus


def system_input_rows(rows, labels):
    positions = []
    for identifier in ("LANG_TOUCHSCREEN_SETTINGS", "LANG_ACCESSIBILITY_BUTTONS", "LANG_KEYCLICK"):
        matches = [index for index, row in enumerate(rows) if speech_contains(row, (labels[identifier],))]
        require(len(matches) == 1, "Missing or duplicate System input setting: " + identifier)
        positions.append(matches[0])
    require(positions == list(range(positions[0], positions[0] + 3)),
            "System input settings must immediately precede Keyclick in the reviewed order")
    return positions


def phrases(text, prefix="TTS utterance"):
    return [phrase.rstrip("\r") for phrase in re.findall(
        r"^" + re.escape(prefix) + r": (.*)$", text, re.MULTILINE)]


def normalized(text):
    return " ".join(text.casefold().split())


def speech_contains(text, labels):
    return all(normalized(label) in normalized(" ".join(phrases(text, prefix)))
               for label in labels for prefix in ("TTS", "TTS utterance"))


def speech_ordered(text, labels):
    for prefix in ("TTS", "TTS utterance"):
        spoken, cursor = normalized(" ".join(phrases(text, prefix))), 0
        for label in labels:
            phrase = normalized(label)
            position = spoken.find(phrase, cursor)
            if position < 0:
                return False
            cursor = position + len(phrase)
    return True


def require_list_position(text, label, labels, position, total, enabled=True):
    require(type(position) is int and type(total) is int and 1 <= position <= total,
            "Invalid expected list position")
    suffix = f" {position} {labels['VOICE_OF']} {total}" if enabled else ""
    for prefix in ("TTS", "TTS utterance"):
        require(normalized(" ".join(phrases(text, prefix))) == normalized(label + suffix),
                "Unexpected label or list position suffix in " + prefix)


def strip_list_position(spoken, of_label=None):
    if of_label is not None:
        suffix = re.search(r" (\d+) " + re.escape(normalized(of_label)) + r" (\d+)$", spoken)
        if suffix:
            require(1 <= int(suffix[1]) <= int(suffix[2]), "Invalid list position suffix")
            return spoken[:suffix.start()]
    return spoken


def require_position_presence(text, labels, enabled, position=None):
    connector = re.escape(normalized(labels.get("VOICE_OF", "of")))
    for prefix in ("TTS", "TTS utterance"):
        spoken = normalized(" ".join(phrases(text, prefix)))
        suffix = re.search(r" (\d+) " + connector + r" (\d+)$", spoken)
        require(bool(suffix) == enabled, "Unexpected list position presence in " + prefix)
        if suffix:
            require(1 <= int(suffix[1]) <= int(suffix[2]), "Invalid list position suffix")
            if position is not None:
                require(int(suffix[1]) == position, "Wrong selected list position")


def validate_status(text, label):
    utterances = phrases(text)
    require(utterances and all(normalized(utterance) == normalized(label) for utterance in utterances),
            "Status missing, interrupted or followed by automatic interface speech")
    require(speech_contains(text, (label,)), "Missing synthesized status segment")


def group_status_matches(text, labels):
    if not labels or len(labels) > 8 or any(not label or '\n' in label or '\r' in label for label in labels):
        return False
    text = text.replace('\r\n', '\n')
    body = '\n'.join(labels) + '\n'
    for prefix in ('TTS', 'TTS utterance'):
        if re.search(r'^' + re.escape(prefix + ': ' + body), text, flags=re.MULTILINE) is None:
            return False
    return phrases(text) == [labels[0]]


def validate_group_status(text, labels):
    require(group_status_matches(text, labels),
            "Missing, reordered, interrupted or duplicated combined service status")


def verify_group_mapping_transition(before, after, enabled):
    from test_hiby_accessibility_gui import parse_accessibility_config
    original = parse_accessibility_config(before)
    changed = parse_accessibility_config(after)
    require(original['version'] == changed['version'] == 11,
            'Grouped service GUI must use its explicitly reviewed V11 profile')
    require(changed['enabled'] is enabled, 'Grouped shortcut did not persist the actual touch service state')
    differences = sorted(name for name in original if original[name] != changed[name])
    require(not (set(differences) - {'enabled'}),
            'Service toggling changed gesture/button maps, launch references or shared preferences')
    return dict(before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(after).hexdigest(),
                changed_fields=differences, actual_touch_enabled=changed['enabled'])


def parse_settings(text):
    settings = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        require(bool(separator) and key.strip() not in settings, "Malformed/duplicate saved setting")
        settings[key.strip()] = value.strip()
    return settings


def effective_settings(text):
    source = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
    defaults = {}
    for field, name in (("tts_enabled", "tts enabled"), ("talk_menu", "talk menu")):
        found = re.search(r"OFFON_SETTING\([^,]*,\s*" + field + r",\s*LANG_\w+,\s*(true|false)\s*,", source)
        require(found is not None, "Cannot establish frozen boolean default: " + field)
        defaults[name] = "on" if found[1] == "true" else "off"
    for field, name in (("talk_mixer_amp", "talk mixer level"), ("tts_volume", "tts volume")):
        found = re.search(r"INT_SETTING\([^,]*,\s*" + field + r",\s*LANG_\w+,\s*(\d+)\s*,", source)
        require(found is not None, "Cannot establish frozen volume default: " + field)
        defaults[name] = found[1]
    return dict(defaults, **parse_settings(text))


def saved_settings_snapshot(resources, language, expected, report):
    require(not (resources / "fixed.cfg").exists(), "Unexpected fixed.cfg overrides the saved snapshot")
    pending = (resources / "config.cfg.new").exists()
    path = resources / ("config.cfg.new" if pending else "config.cfg")
    require(path.is_file(), "Missing saved config snapshot: " + str(path))
    data = path.read_bytes()
    report["settings_snapshot"] = {
        "path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
        "pending_promotion": pending, "restart_verified": False, "flash_durability_established": False,
    }
    text = data.decode("utf-8")
    if pending:
        header = f"# .cfg file created by rockbox {EXPECTED_VERSION} - http://www.rockbox.org"
        lines = text.splitlines()
        require(len(lines) >= 3 and lines[:2] == [header, ""] and text.endswith("\n"),
                "Pending config lacks the expected complete application/version header")
        fields = parse_settings(text)
        markers = {"volume": "-25", "talk mixer level": "0", "lang": f"/.rockbox/langs/{language}.lng"}
        require(all(fields.get(name) == value for name, value in markers.items()),
                "Pending config lacks the intentional nondefault profile markers")
        require(all(name and value for name, value in fields.items()), "Empty saved setting in pending config")
    settings = effective_settings(text)
    require(all(settings.get(name) == value for name, value in expected.items()),
            "Actual saved flags/volume do not match service effects: " + repr(settings))
    return settings


def connectivity_preferences(data):
    found = re.fullmatch(rb"RBCONNECTIVITY:1\nwifi:([01])\nbluetooth:([01])\nairplane:([01])\n", data)
    require(found is not None, "Invalid actual connectivity preference file")
    return tuple(int(value) for value in found.groups())


def synthetic_config(language, talk_menu, music=False):
    require(language in LANGUAGES, "Unsupported fixture language")
    return (f"lang: /.rockbox/langs/{language}.lng\nstart in screen: root\n"
            f"talk menu: {'on' if talk_menu else 'off'}\n"
            "talk dir: off\ntalk file: off\ntalk dir clip: off\ntalk file clip: off\n"
            "talk mixer level: 0\ntts enabled: on\ntts language: system\ntts rate: 175\n"
            "tts pitch: 50\ntts volume: 100\ntts range: 50\ntts wordgap: 0\n"
            "tts ducking: on\ntts ducking level: 25\nvolume: -25\nkeyclick: off\n"
            "backlight timeout: on\nbacklight timeout plugged: on\n"
            "backlight filters first keypress: off\nshow files: all\nsort case: off\n"
            + ("repeat: one\nshuffle: off\n" if music else ""))


def pcm_statistics(data):
    require(len(data) % 2 == 0, "Partial PCM sample")
    samples = array.array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    return {"bytes": len(data), "nonzero_samples": sum(value != 0 for value in samples),
            "peak": max((abs(value) for value in samples), default=0)}


def quiet_pcm_tail(data, music=False):
    require(len(data) % 4 == 0, "Quiet-tail analysis requires complete stereo S16 frames")
    if len(data) < 65536:
        return False
    data = data[-65536:]
    if not music:
        return not any(data)
    samples = array.array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    size = 2048
    cosines = tuple(math.cos(2 * math.pi * 997 * index / 44100) for index in range(size))
    sines = tuple(math.sin(2 * math.pi * 997 * index / 44100) for index in range(size))
    cosine_energy = sum(value * value for value in cosines)
    sine_energy = sum(value * value for value in sines)
    cross = sum(cosine * sine for cosine, sine in zip(cosines, sines))
    determinant = cosine_energy * sine_energy - cross * cross
    amplitudes = []
    for channel in range(2):
        mono = samples[channel::2]
        for offset in range(0, len(mono), size):
            block = mono[offset:offset + size]
            cosine_projection = sum(value * cosine for value, cosine in zip(block, cosines))
            sine_projection = sum(value * sine for value, sine in zip(block, sines))
            cosine_gain = (cosine_projection * sine_energy - sine_projection * cross) / determinant
            sine_gain = (sine_projection * cosine_energy - cosine_projection * cross) / determinant
            amplitude = math.hypot(cosine_gain, sine_gain)
            residual = math.sqrt(max(0, (sum(value * value for value in block) -
                                       cosine_gain * cosine_projection - sine_gain * sine_projection) / size))
            if amplitude <= 1 or residual > max(2, amplitude * 0.02):
                return False
            amplitudes.append(amplitude)
    return min(amplitudes) >= max(amplitudes) * 0.95


def observation_format(text):
    require(not re.search(r"Audio debug file (?:open|write|close) failed", text), "Audio observation tap failed")
    formats = re.findall(r"^Audio debug format: rate=(\d+) format=(\d+) channels=(\d+) frame_bytes=(\d+)\r?$",
                         text, re.MULTILINE)
    for values in formats:
        require(tuple(map(int, values)) == (44100, 32784, 2, 4),
                "Actual observation format is not 44100 Hz stereo S16LE: " + repr(values))
    return {"rate": 44100, "format": 32784, "channels": 2, "frame_bytes": 4} if formats else None


def validate_trace_features(freeze, executable):
    for name, checksum in TRACE_SOURCES.items():
        require(freeze["sources"].get(name) == checksum and digest(ROOT / name) == checksum,
                "Frozen audio trace source revision changed: " + name)
    binary = executable.read_bytes()
    require(all(feature in binary for feature in TRACE_FEATURES), "Frozen EXE lacks the qualified optional audio trace")
    return dict(TRACE_SOURCES)


class PrivateDesktop:
    access = 0x00c7

    def __init__(self):
        require(sys.platform == "win32" and ctypes.sizeof(ctypes.c_void_p) == 8,
                "Execution requires native 64-bit Windows Python")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for library, name, result, parameters in (
            (self.user, "CreateDesktopW", wintypes.HANDLE,
             [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]),
            (self.user, "CloseDesktop", wintypes.BOOL, [wintypes.HANDLE]),
            (self.user, "OpenInputDesktop", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            (self.user, "GetThreadDesktop", wintypes.HANDLE, [wintypes.DWORD]),
            (self.user, "GetUserObjectInformationW", wintypes.BOOL,
             [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]),
            (self.user, "GetWindowThreadProcessId", wintypes.DWORD, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
            (self.kernel, "GetCurrentThreadId", wintypes.DWORD, []),
            (self.kernel, "CreateEventW", wintypes.HANDLE,
             [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]),
            (self.kernel, "SetHandleInformation", wintypes.BOOL, [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]),
            (self.kernel, "SetEvent", wintypes.BOOL, [wintypes.HANDLE]),
            (self.kernel, "WaitForSingleObject", wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD]),
            (self.kernel, "CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
        ):
            function = getattr(library, name)
            function.restype, function.argtypes = result, parameters

    @staticmethod
    def checked(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def name(self, handle):
        buffer, needed = ctypes.create_unicode_buffer(256), wintypes.DWORD()
        self.checked(self.user.GetUserObjectInformationW(handle, 2, buffer, ctypes.sizeof(buffer),
                                                         ctypes.byref(needed)))
        return buffer.value

    def current(self):
        return self.name(self.checked(self.user.GetThreadDesktop(self.kernel.GetCurrentThreadId())))

    def input(self):
        handle = self.checked(self.user.OpenInputDesktop(0, False, 1))
        try:
            return self.name(handle)
        finally:
            self.checked(self.user.CloseDesktop(handle))

    def assert_private(self, expected):
        require(self.current() == expected and self.input() != expected,
                "GUI worker must be on its undisplayed private desktop")

    def owns(self, pid, window, desktop):
        self.assert_private(desktop)
        owner = wintypes.DWORD()
        thread = self.user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        require(thread and owner.value == pid and self.name(self.user.GetThreadDesktop(thread)) == desktop,
                "HWND ownership/private desktop changed; refusing input")

    def inherited_startup(self, handle):
        self.checked(self.kernel.SetHandleInformation(handle, 1, 1))
        return subprocess.STARTUPINFO(lpAttributeList={"handle_list": [int(handle)]})


class JobBasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                ("active_limit", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]


class JobLimits(ctypes.Structure):
    _fields_ = [("basic", JobBasicLimits), ("io", ctypes.c_uint64 * 6), ("memory", ctypes.c_size_t * 4)]


class OwnedJob:
    def __init__(self, native):
        self.native, self.handle = native, None
        for name, result, parameters in (
            ("CreateJobObjectW", wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR]),
            ("SetInformationJobObject", wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]),
            ("AssignProcessToJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]),
        ):
            function = getattr(native.kernel, name)
            function.restype, function.argtypes = result, parameters
        self.handle = native.checked(native.kernel.CreateJobObjectW(None, None))
        limits = JobLimits()
        limits.basic.flags = 0x2000
        try:
            native.checked(native.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        except BaseException:
            self.close()
            raise

    def assign(self, process):
        self.native.checked(self.native.kernel.AssignProcessToJobObject(self.handle, int(process._handle)))

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            self.native.checked(self.native.kernel.CloseHandle(handle))


def rapid_navigation_timing(records, key, clicks, mask):
    require(key in ("Up", "Down") and type(clicks) is int and clicks in (2, 3) and len(records) == clicks,
            "Incomplete rapid navigation acknowledgement plan")
    down_times = []
    for record in records:
        require(record.get("passed") is True and record.get("release_sent") is True and
                record.get("key") == key and record.get("mask") == mask and
                0.08 - 1e-12 <= record.get("hold_seconds", -1) < PRESS_MAX_DOWN and
                record["hold_seconds"] <= record.get("sampled_release_seconds", -1) < PRESS_MAX_DOWN,
                "Rapid navigation requires complete bounded press/release acknowledgements")
        samples = record.get("samples", [])
        require(samples and all(isinstance(sample.get("monotonic"), (int, float)) and
                math.isfinite(sample["monotonic"]) for sample in samples) and
                all(earlier["monotonic"] <= later["monotonic"] for earlier, later in zip(samples, samples[1:])),
                "Invalid rapid acknowledgement timestamps")
        matched = {phase: [(index, sample["monotonic"]) for index, sample in enumerate(samples)
                          if sample.get("phase") == phase and sample.get("lastbtn") == expected]
                   for phase, expected in (("before-down", 0), ("down", mask), ("released", 0))}
        require(all(len(items) == 1 for items in matched.values()) and
                matched["before-down"][0][0] < matched["down"][0][0] < matched["released"][0][0] and
                matched["down"][0][1] <= matched["released"][0][1],
                "Missing or reordered rapid down/release acknowledgements")
        down_times.append(matched["down"][0][1])
    spacings = [later - earlier for earlier, later in zip(down_times, down_times[1:])]
    require(all(0 < spacing < RAPID_NAVIGATION_MAX_SPACING - 1e-12 for spacing in spacings),
            "Rapid wrap timing not exercised: down acknowledgements must be less than 200 ms apart")
    return dict(down_ack_monotonic=down_times, down_ack_spacing_seconds=spacings,
                maximum_down_ack_spacing_seconds=RAPID_NAVIGATION_MAX_SPACING)


class ServicesProbe:
    def __init__(self, native, desktop, runtime, directory, report, labels, timeout):
        from test_tts_bookmarks_gui import GuiProbe
        self.base = GuiProbe(runtime, directory, report, timeout)
        self.native, self.desktop = native, desktop
        self.labels, self.status_labels = labels["voice"], labels["display"]
        self.directory, self.timeout, self.report = directory, timeout, report
        self.process, self.window = None, None
        self.log, self.pcm = runtime / "simulator.log", directory / "audio.raw"
        self.observation = runtime / "audiodebug.raw"
        self.latest = ""
        self.started = None
        self.music_expected = False
        self.memory = None

    def text(self, start=0):
        return self.base.text(start)

    def mark(self):
        return self.base.mark()

    def alive(self):
        self.native.assert_private(self.desktop)
        require(self.process is not None and self.process.poll() is None, "Owned simulator exited unexpectedly")
        require(time.perf_counter() - self.started < self.report.get("action_budget_seconds", 600), "Session exceeded its bounded action budget")

    def launch(self, desktop_handle):
        from test_tts_simulator import windows_backend
        self.native.assert_private(self.desktop)
        executable = self.base.runtime / "rockboxui.exe"
        require(not self.observation.exists(), "Previous session observation was not preserved")
        windows_backend().ensure_unused(executable)
        environment = dict(os.environ, SDL_VIDEODRIVER="windows", SDL_AUDIODRIVER="disk",
                           SDL_DISKAUDIOFILE=str(self.pcm), SDL_DISKAUDIODELAY="12")
        self.started = time.perf_counter()
        self.process = subprocess.Popen(
            [str(executable), "--root", str(self.base.runtime / "simdisk"), "--audiodev", str(self.pcm),
             "--debugaudio", "--debugbuttons"],
            cwd=self.base.runtime, env=environment, startupinfo=self.native.inherited_startup(desktop_handle),
            close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        self.base.process = self.process
        deadline = time.perf_counter() + self.timeout
        while time.perf_counter() < deadline:
            self.alive()
            window = windows_backend().find_window(self.process.pid)
            if window:
                self.native.owns(self.process.pid, window, self.desktop)
                self.window = window
                self.report["pid"], self.report["hwnd"] = self.process.pid, int(window)
                from test_tts_recorder_gui import RecorderMemoryProbe
                self.memory = RecorderMemoryProbe(self.process, executable, self.report["input_layout"],
                                                   self.report.setdefault("input_memory", {}))
                return
            time.sleep(0.05)
        raise AssertionError("Missing SDL window on the private desktop")

    def key(self, key, pressed):
        from test_tts_simulator import windows_backend
        self.native.owns(self.process.pid, self.window, self.desktop)
        self.report["raw_input"].append({"monotonic": time.perf_counter(), "key": key, "pressed": pressed,
                                         "pid": self.process.pid, "hwnd": int(self.window), "desktop": self.desktop})
        windows_backend().key_event(self.process.pid, self.window, key, pressed)

    def wait_button_state(self, expected, deadline, record, phase):
        while time.perf_counter() < deadline:
            self.alive()
            self.native.owns(self.process.pid, self.window, self.desktop)
            symbol = self.report["input_layout"]["symbols"]["lastbtn"]
            value = int.from_bytes(self.memory.read_image(symbol["rva"], 4), "little")
            record["samples"].append({"monotonic": time.perf_counter(), "phase": phase, "lastbtn": value})
            if value == expected:
                return
            time.sleep(0.002)
        raise AssertionError("Missing sampled button acknowledgement: " + phase)

    def press(self, key, hold=0.08, clicks=1):
        require(key in ("Up", "Down", "Left", "Right", "Insert"), "Unapproved private key")
        require(hold <= 0.15 and (1 <= clicks <= 2 or (key == "Insert" and clicks == 3)),
                "Only bounded short presses and the explicit triple-Power control are allowed")
        self._press_sequence(key, hold, clicks)

    def _press_sequence(self, key, hold, clicks):
        records = []
        for click in range(clicks):
            self.alive()
            require(self.memory is not None, "Validated owned input memory is required")
            mask = self.report["input_layout"]["button_masks"][key]
            record = {"key": key, "mask": mask, "minimum_seconds": max(hold, 0.08),
                      "maximum_seconds": PRESS_MAX_DOWN, "samples": [], "passed": False,
                      "raw_input_start": len(self.report["raw_input"]), "release_sent": False}
            self.report.setdefault("press_acknowledgements", []).append(record)
            records.append(record)
            started, held = None, False
            try:
                self.wait_button_state(0, time.perf_counter() + PRESS_ACK_TIMEOUT, record, "before-down")
                started, held = time.perf_counter(), True
                self.key(key, True)
                self.wait_button_state(mask, started + PRESS_ACK_TIMEOUT, record, "down")
                remaining = record["minimum_seconds"] - (time.perf_counter() - started)
                if remaining > 0:
                    time.sleep(remaining)
            except BaseException as error:
                record["error"] = f"{type(error).__name__}: {error}"
                raise
            finally:
                if held:
                    try:
                        if self.process.poll() is None:
                            self.key(key, False)
                            record["release_sent"] = True
                        record["hold_seconds"] = time.perf_counter() - started
                        require(record["release_sent"], "Owned process exited before sampled release")
                        self.wait_button_state(0, started + PRESS_MAX_DOWN, record, "released")
                        record["sampled_release_seconds"] = time.perf_counter() - started
                        require(record["hold_seconds"] < PRESS_MAX_DOWN, "Acknowledged press exceeded its hold bound")
                    except BaseException as error:
                        record["release_error"] = f"{type(error).__name__}: {error}"
                        record["raw_input_end"] = len(self.report["raw_input"])
                        if "error" not in record:
                            raise
                record["raw_input_end"] = len(self.report["raw_input"])
            record["passed"] = True
            if click + 1 < clicks:
                time.sleep(0.08)
        time.sleep(0.4)
        return records

    def rapid_navigation(self, key, clicks):
        require(key in ("Up", "Down") and type(clicks) is int and clicks in (2, 3),
                "Rapid navigation requires exactly two or three Up/Down presses")
        start = len(self.report.get("press_acknowledgements", []))
        result = dict(key=key, clicks=clicks, passed=False, timing_exercised=False,
                      maximum_down_ack_spacing_seconds=RAPID_NAVIGATION_MAX_SPACING)
        self.report.setdefault("rapid_navigation_bursts", []).append(result)
        try:
            records = self._press_sequence(key, 0.08, clicks)
            result.update(rapid_navigation_timing(records, key, clicks,
                                                 self.report["input_layout"]["button_masks"][key]))
            result.update(passed=True, timing_exercised=True)
            return result
        except BaseException as error:
            result["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            records = self.report.get("press_acknowledgements", [])[start:]
            result["press_acknowledgement_indices"] = list(range(start, start + len(records)))
            result["down_ack_monotonic"] = [sample["monotonic"] for record in records
                for sample in record["samples"] if sample["phase"] == "down" and sample["lastbtn"] == record["mask"]]
            result["down_ack_spacing_seconds"] = [later - earlier for earlier, later in
                zip(result["down_ack_monotonic"], result["down_ack_monotonic"][1:])]

    def chord(self, modifier, key):
        require((modifier, key) == ("Insert", "Left"), "Unapproved private chord")
        self.alive()
        require(self.memory is not None, "Validated owned input memory is required")
        masks = self.report["input_layout"]["button_masks"]
        record = {"key": modifier + "+" + key, "minimum_combined_seconds": 0.1,
                  "maximum_seconds": PRESS_MAX_DOWN, "samples": [], "passed": False,
                  "pid": self.process.pid, "hwnd": int(self.window), "desktop": self.desktop,
                  "raw_input_start": len(self.report["raw_input"])}
        self.report.setdefault("chord_acknowledgements", []).append(record)
        held = []
        try:
            self.wait_button_state(0, time.perf_counter() + PRESS_ACK_TIMEOUT, record, "before-chord")
            started = time.perf_counter()
            held.append(modifier)
            self.key(modifier, True)
            self.wait_button_state(masks[modifier], started + PRESS_ACK_TIMEOUT, record, "modifier-down")
            held.append(key)
            self.key(key, True)
            self.wait_button_state(masks[modifier] | masks[key], started + PRESS_ACK_TIMEOUT, record, "combined-down")
            require(time.perf_counter() + 0.1 < started + PRESS_MAX_DOWN, "Insufficient chord time before first repeat")
            time.sleep(0.1)
            self.key(key, False)
            held.remove(key)
            self.wait_button_state(masks[modifier], started + PRESS_MAX_DOWN, record, "key-released")
            self.key(modifier, False)
            held.remove(modifier)
            self.wait_button_state(0, started + PRESS_MAX_DOWN, record, "all-released")
            record["sampled_release_seconds"] = time.perf_counter() - started
            require(record["sampled_release_seconds"] < PRESS_MAX_DOWN, "Chord exceeded its hold bound")
            record["passed"] = True
        except BaseException as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            errors = []
            for button in reversed(held):
                try:
                    require(self.process.poll() is None, "Owned process exited before chord cleanup")
                    self.key(button, False)
                except BaseException as error:
                    errors.append(f"{button}: {type(error).__name__}: {error}")
            record["cleanup_errors"] = errors
            record["raw_input_end"] = len(self.report["raw_input"])
            if errors and "error" not in record:
                record["passed"] = False
                raise AssertionError("Owned chord release failed: " + repr(errors))
        time.sleep(0.4)

    def settle(self, marker, begin, master_begin):
        deadline = time.perf_counter() + self.timeout
        cursor, tail = begin, b""
        previous_log, previous_utterances = None, ()
        previous_end, previous_master = begin, master_begin
        quiet_since = last_progress = last_master_progress = None
        pending_speech, speech_samples = False, 0
        while time.perf_counter() < deadline:
            self.alive()
            now, log_end = time.perf_counter(), self.mark()
            text = self.text()
            metadata = observation_format(text)
            events = re.findall(r"^Audio debug file (open|closed)\r?$", text, re.MULTILINE)
            state = events[-1] if events else None
            utterances = tuple(phrases(self.text(marker)))
            if log_end != previous_log:
                previous_log, quiet_since = log_end, None
            if utterances != previous_utterances:
                previous_utterances = utterances
                pending_speech, speech_samples = bool(utterances), 0
            master_end = self.pcm.stat().st_size if self.pcm.exists() else 0
            require(master_end >= previous_master, "Master PCM capture shrank")
            master_progress = master_end > previous_master
            previous_master = master_end
            if master_progress:
                last_master_progress = now
            size = self.observation.stat().st_size if self.observation.exists() else 0
            require(size >= cursor, "Observation PCM capture shrank")
            end = size - size % 4
            new_frames, previous_end = end > previous_end, end
            if new_frames:
                last_progress = now
            progressed = end > cursor
            if progressed:
                with self.observation.open("rb") as stream:
                    stream.seek(cursor)
                    data = stream.read(min(end - cursor, 1048576))
                require(data and len(data) % 4 == 0, "Incomplete PCM read during observation")
                cursor += len(data)
                if pending_speech:
                    speech_samples += pcm_statistics(data)["nonzero_samples"]
                    pending_speech = speech_samples < 128
                tail = (tail + data)[-65536:]
            closed = state == "closed" and not self.music_expected and cursor == size
            fresh = last_progress is not None and now - last_progress <= 0.3
            quiet = (closed or (state == "open" and fresh and quiet_pcm_tail(tail, self.music_expected)))
            master_fresh = last_master_progress is not None and now - last_master_progress <= 0.3
            if metadata and not pending_speech and cursor == end and quiet and master_fresh:
                if quiet_since is None:
                    quiet_since = now
            else:
                quiet_since = None
            if master_progress and quiet_since is not None and now - quiet_since >= 1.2:
                return {"observation_start": begin, "observation_end": cursor,
                        "master_start": master_begin, "master_end": master_end,
                        "quiet_seconds": now - quiet_since, "format": metadata, "tap_state": state,
                        "quiet_basis": "observed sink close/flush" if closed else "fresh PCM quiet tail",
                        "tail": pcm_statistics(tail), "music_expected": self.music_expected,
                        "utterances": list(utterances)}
            time.sleep(0.1)
        raise AssertionError(f"Speech/PCM did not settle before the bounded deadline: "
                             f"bytes={cursor - begin}, pending_speech={pending_speech}, "
                             f"last_progress={last_progress}")

    def capture(self, name, action=None, expected=(), silent=False, status=False, initial=False, optional=False, grouped=False):
        self.alive()
        require(not grouped or (status and not silent and not optional and bool(expected)),
                "Combined status needs explicit, audible ordered status expectations")
        marker = 0 if initial else self.mark()
        begin = 0 if initial or not self.pcm.exists() else self.pcm.stat().st_size
        observation_begin = 0 if initial or not self.observation.exists() else self.observation.stat().st_size
        record = {"name": name, "log_start": marker, "pcm_start": begin,
                  "observation_start": observation_begin,
                  "expected": list(expected), "silent": silent, "status_only": status,
                  "grouped_status": grouped, "passed": False}
        self.report["checks"].append(record)
        try:
            if action:
                action()
            deadline = time.perf_counter() + self.timeout
            if not silent and not optional:
                while time.perf_counter() < deadline:
                    self.alive()
                    text = self.text(marker)
                    ready = group_status_matches(text, expected) if grouped else speech_contains(text, expected) and phrases(text)
                    if ready:
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("Missing expected speech: " + repr(expected))
            record["settle"] = self.settle(marker, observation_begin, begin)
            text = self.text(marker)
            require("TTS: synthesis failed" not in text, "Actual synthesis failed")
            if silent:
                require(not phrases(text) and not phrases(text, "TTS"), "Ordinary interface spoke while disabled")
            if status:
                if grouped:
                    validate_group_status(text, expected)
                else:
                    validate_status(text, expected[0])
            self.latest = text
            record["passed"] = True
            return text
        finally:
            record.update(log_end=self.mark(), pcm_end=self.pcm.stat().st_size if self.pcm.exists() else 0,
                          observation_end=self.observation.stat().st_size if self.observation.exists() else 0,
                          utterances=phrases(self.text(marker)), segments=phrases(self.text(marker), "TTS"))

    def row(self, name, key="Down", expected=()):
        return self.capture(name, lambda: self.press(key), expected)

    def seek(self, identifier, maximum=45):
        label = self.labels[identifier]
        for attempt in range(maximum):
            if (normalized(label) in {normalized(segment) for segment in phrases(self.latest, "TTS")}
                    and speech_contains(self.latest, (label,))):
                return
            self.row(f"Seek {identifier} {attempt + 1}")
        raise AssertionError("Spoken row not found: " + identifier)

    def enter(self, identifier, expected=()):
        self.seek(identifier)
        return self.row("Enter " + identifier, "Right", expected)

    def cycle(self, name, forbidden=(), expected_order=None, key="Down"):
        require(bool(phrases(self.latest)), "Cycle needs an observed initial row")
        anchor = normalized(" | ".join(phrases(self.latest)))
        rows = [self.latest]
        for index in range(60):
            observed = self.row(f"{name} row {index + 1}", key)
            if normalized(" | ".join(phrases(observed))) == anchor:
                break
            require(normalized(" | ".join(phrases(observed))) not in
                    [normalized(" | ".join(phrases(row))) for row in rows], "Duplicate spoken menu row")
            rows.append(observed)
        else:
            raise AssertionError("Menu did not wrap within its row budget")
        for identifier in forbidden:
            require(not any(speech_contains(row, (self.labels[identifier],)) for row in rows),
                    "Removed/duplicate menu entry remains: " + identifier)
        if expected_order:
            require(len(rows) == len(expected_order), "Unexpected number of Accessibility rows")
            require(all(speech_ordered(row, tuple(str(identifier) if type(identifier) is int else self.labels[identifier] for identifier in
                                                  ((identifiers,) if isinstance(identifiers, str) else identifiers)))
                        for row, identifiers in zip(rows, expected_order)), "Accessibility menu order changed")
        self.report.setdefault("menu_cycles", {})[name] = [phrases(row) for row in rows]
        return rows

    def close(self, long_hold=False):
        memory = getattr(self, "memory", None)
        if memory is not None:
            self.memory = None
            memory.close()
        if self.process is None:
            return
        if self.process.poll() is not None:
            text = self.text()
            shutdown = self.report.setdefault("shutdown", {"log_excerpt": text[-4096:]})
            shutdown["exit_code"] = self.process.returncode
            shutdown["defects"] = [phrase for phrase in ("queue_post ovf", "PANIC", "TTS: synthesis failed")
                                   if phrase in text]
            require(self.process.returncode == 0 and not shutdown["defects"],
                    "Graceful owned shutdown failed: " + repr(shutdown))
            return
        if self.window is None:
            self.process.terminate()
            self.process.wait(timeout=12)
            return
        self.native.owns(self.process.pid, self.window, self.desktop)
        marker, started = self.mark(), time.perf_counter()
        shutdown = {"log_start": marker, "release_sent": False, "observed": False, "passed": False,
                    "style": "long-hold-until-exit" if long_hold else "bounded-cue-release",
                    "max_hold_seconds": 12 if long_hold else 3,
                    "raw_input_start": len(self.report.get("raw_input", []))}
        self.report["shutdown"] = shutdown
        self.report.setdefault("shutdown_attempts", []).append(shutdown)
        try:
            self.key("Insert", True)
            try:
                while (self.process.poll() is None and
                       time.perf_counter() - started < shutdown["max_hold_seconds"]):
                    text = self.text(marker)
                    if speech_contains(text, (self.labels["LANG_SHUTTINGDOWN"],)):
                        shutdown["observed"] = True
                        if not long_hold:
                            break
                    time.sleep(0.02)
            finally:
                shutdown["hold_seconds"] = time.perf_counter() - started
                shutdown["hold_end"] = ("owned-process-exit" if self.process.poll() is not None else
                                        "shutdown-cue-release" if not long_hold and shutdown["observed"] else
                                        "hold-limit-release")
                if self.process.poll() is None:
                    self.key("Insert", False)
                    shutdown["release_sent"] = True
            self.process.wait(timeout=12)
        finally:
            shutdown["exit_code"] = self.process.poll()
            text = self.text(marker)
            shutdown["observed"] = shutdown["observed"] or (
                speech_contains(text, (self.labels["LANG_SHUTTINGDOWN"],)))
            shutdown["raw_input_end"] = len(self.report.get("raw_input", []))
            shutdown["log_end"], shutdown["log_excerpt"] = self.mark(), text[-4096:]
            shutdown["defects"] = [phrase for phrase in ("queue_post ovf", "PANIC", "TTS: synthesis failed")
                                   if phrase in text]
        require(self.process.returncode == 0 and not shutdown["defects"],
                "Graceful owned shutdown failed: " + repr(shutdown))
        shutdown["passed"] = True


def runtime_assets(build):
    assets = list(build.glob("*.dll")) + [build / "UI256.bmp"]
    resources = build / "simdisk/.rockbox"
    for directory in RESOURCE_DIRECTORIES:
        root = confined_path(resources / directory, build)
        require(root.is_dir(), "Missing fullinstall directory: " + str(root))
        for path in root.rglob("*"):
            confined_path(path, build)
            if path.is_file() and path.suffix.casefold() != ".voice":
                assets.append(path)
    assets += [resources / name for name in RESOURCE_FILES]
    for path in assets:
        confined_path(path, build)
        require(path.is_file() and path.suffix.casefold() != ".exe", "Unsupported runtime asset")
    return sorted(set(assets))


def bound_checks(root, bindings, borrowed=None):
    for name, expected in bindings.items():
        path = borrowed if name == "rockboxui.exe" and borrowed is not None else root / relative_name(name)
        confined_path(path, root if borrowed is None or path != borrowed else borrowed.parent)
        require(path.is_file() and digest(path) == expected, "Frozen input changed: " + str(path))


def validate_authorization(arguments, borrowed=None):
    require(arguments.build_ready and sha256_value(arguments.exe_sha256) and
            arguments.freeze is not None and sha256_value(arguments.freeze_sha256),
            "Explicit parent build-ready, freeze/hash and EXE hash are required before build use")
    central = project_materials_root(ROOT)
    freeze_path = confined_path(arguments.freeze, central)
    require(digest(freeze_path) == arguments.freeze_sha256, "Parent freeze hash changed")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    validate_freeze_shape(freeze, arguments.exe_sha256)
    build = confined_path(Path(freeze["build"]), central)
    require(build.is_dir(), "Frozen development build is unavailable")
    bound_checks(ROOT, freeze["sources"])
    bound_checks(build, freeze["build_files"], borrowed)
    validate_trace_features(freeze, borrowed if borrowed is not None else build / "rockboxui.exe")
    if (build / "manifest.json").exists():
        require("manifest.json" in freeze["build_files"], "Existing manifest must be frozen")
    for path in runtime_assets(build):
        name = path.relative_to(build).as_posix()
        require(freeze["build_files"].get(name) == digest(path), "Unbound runtime asset: " + name)
    for name in ("rockbox-info.txt", "simdisk/.rockbox/rockbox-info.txt"):
        information = (build / name).read_text(encoding="utf-8")
        require(re.search(r"^Target: hibyr1\s*$", information, re.MULTILINE), "Wrong Windows target")
        require(re.search(r"^Version: " + re.escape(freeze["version"]) + r"\s*$", information, re.MULTILINE),
                "Frozen version does not match fullinstall")
    source_layout()
    mapping_contract()
    return freeze, build


def compiled_labels(build):
    from test_tts_recorder_gui import display_labels
    from test_tts_simulator import catalog_labels
    result = {}
    for language in LANGUAGES:
        display, voice = display_labels(build, language), catalog_labels(build, language)
        require(all(display.get(name) and voice.get(name) for name in REQUIRED_IDS),
                "Incomplete compiled PL/EN display or speech catalog: " + language)
        require(all(voice.get(name) for name in VOICE_ONLY_IDS), "Incomplete compiled numeric-unit voice catalog: " + language)
        for extension in ("lng", "vstrings"):
            require(digest(build / f"apps/lang/{language}.{extension}") ==
                    digest(build / f"simdisk/.rockbox/langs/{language}.{extension}"), "Stale installed catalog")
        result[language] = {"display": {name: display[name] for name in REQUIRED_IDS},
                            "voice": {name: voice[name] for name in REQUIRED_IDS + VOICE_ONLY_IDS}}
    return result


def new_results(kind):
    central = project_materials_root(ROOT)
    ensure_ignored_directories(central.parent, (central.name,))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    results = confined_path(central / SCOPE / (kind + "-" + stamp), central)
    results.mkdir(parents=True, exist_ok=False)
    return results


def prepare_runtime(build, results, report):
    runtime = results / "fixture"
    runtime.mkdir()
    (runtime / "simdisk/.rockbox").mkdir(parents=True)
    plans = []
    for source in runtime_assets(build):
        relative = source.relative_to(build)
        destination = confined_path(runtime / relative, runtime)
        plans.append({"source": str(source), "destination": str(destination), "sha256": digest(source),
                      "purpose": "Single immutable asset set for private PL/EN service and menu tests",
                      "retained_after_test": True})
    print("Before copying: immutable DLL/UI/runtime resources only; no user profile or .voice files. "
          "These named test assets will remain in Workspace. EXE is moved/restored, never copied.", flush=True)
    for plan in plans:
        print(plan["source"] + " -> " + plan["destination"], flush=True)
    write_json(results / "copy-plan.json", plans)
    for plan in plans:
        source, destination = Path(plan["source"]), Path(plan["destination"])
        require(not destination.exists(), "Refusing runtime asset overwrite")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        require(digest(source) == plan["sha256"] == digest(destination), "Runtime copy integrity failure")
    report["copies"] = plans
    write_json(runtime / ".accessibility-services-gui-fixture.json",
               {"scope": SCOPE, "synthetic_profiles_only": True, "source_build": str(build)})
    return runtime


def regular_files(root):
    result = {}
    if root.exists():
        for path in root.rglob("*"):
            confined_path(path, root)
            if path.is_file():
                result[path.relative_to(root).as_posix()] = digest(path)
    return result


def configure_session(runtime, directory, language, scenario):
    resources = runtime / "simdisk/.rockbox"
    for name in ("config.cfg.new", "fixed.cfg"):
        require(not (resources / name).exists(), "Fresh session contains unexpected " + name)
    legacy_enabled, legacy_service = {
        "services": (0, 0), "missing-voice": (0, 1), "layout-connectivity": (1, 0), "music": (1, 1),
    }[scenario]
    profile = {
        "config.cfg": synthetic_config(language, scenario == "missing-voice", scenario == "music"),
        "accessibility.cfg": session_mapping_profile(mapping_contract(), scenario),
        "accessibility-shortcut.cfg": (f"RBACCESSIBILITY-SHORTCUT:1\nenabled:{legacy_enabled}\n"
                                       f"service:{legacy_service}\n"),
        "connectivity.cfg": "RBCONNECTIVITY:1\nwifi:1\nbluetooth:1\nairplane:0\n",
    }
    for name, text in profile.items():
        path = resources / name
        require(not path.exists(), "Previous session profile was not preserved")
        path.write_bytes(text.encode("utf-8"))
    write_json(directory / "initial-profile.json", {name: text for name, text in profile.items()})
    require(not list(resources.rglob("*.voice")), "Missing-voice fixture contains a prerecorded voice file")


def preserve_runtime_changes(runtime, directory, original, unchanged=None):
    after = regular_files(runtime)
    changed = [name for name, checksum in original.items() if after.get(name) != checksum]
    require(not changed, "Immutable fixture assets changed: " + repr(changed))
    require(all(after.get(name) == checksum for name, checksum in (unchanged or {}).items()),
            "Obsolete accessibility-shortcut.cfg was changed or removed")
    for name in sorted(set(after) - set(original)):
        source = confined_path(runtime / name, runtime)
        destination = confined_path(directory / "runtime" / name, directory)
        require(not destination.exists(), "Evidence destination collision")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        require(digest(destination) == after[name], "Evidence move changed bytes")


def verify_pcm(directory, report):
    pcm = (directory / "audio.raw").read_bytes()
    require(len(pcm) % 4 == 0, "Expected complete stereo S16 PCM frames")
    require(pcm_statistics(pcm)["nonzero_samples"] >= 128, "Session has no meaningful mixer PCM")
    report["pcm_sha256"] = hashlib.sha256(pcm).hexdigest()
    for check in report["checks"]:
        start, end = check["pcm_start"], check["pcm_end"]
        require(0 <= start <= end <= len(pcm), "Invalid action PCM interval")
        statistics = pcm_statistics(pcm[start:end])
        check["pcm"] = statistics
        if check["silent"] and not report["music"]:
            require(statistics["nonzero_samples"] == 0, "Disabled ordinary interface emitted nonzero PCM")
        elif not report["music"]:
            require(statistics["nonzero_samples"] >= 128, "Logged speech has no nonzero action PCM")
        require(check["passed"], "An action observation did not pass")


def status(probe, identifier, key):
    return probe.capture(identifier, lambda: probe.press(key, clicks=2),
                         (probe.status_labels[identifier],), status=True)


def grouped_service_case(probe, runtime):
    labels = probe.labels
    path = runtime / "simdisk/.rockbox/accessibility.cfg"
    original = path.read_bytes()
    require(not parse_mapping_profile(original)['enabled'], 'Mixed group fixture must start with exploration off')
    probe.capture('Initial grouped shortcut interface', initial=True)
    probe.enter('LANG_SETTINGS')
    probe.enter('LANG_GENERAL_SETTINGS')
    probe.enter('LANG_VOICE', (labels['LANG_TALKBOX_SETTINGS'],))
    probe.enter('LANG_ACCESSIBILITY_SHORTCUT', (labels[SHORTCUT_ROWS[0]],))
    probe.cycle('Grouped accessibility shortcut', expected_order=SHORTCUT_ROWS)
    probe.enter('LANG_ACCESSIBILITY_SHORTCUT_ENABLED', (labels['LANG_SET_BOOL_YES'],))
    probe.row('Cancel unchanged group enable switch', 'Left', (labels[SHORTCUT_ROWS[0]],))
    probe.enter('LANG_ACCESSIBILITY_SHORTCUT_SERVICES', (labels[SHORTCUT_SERVICE_ROWS[0]],))
    probe.cycle('Included accessibility services', expected_order=SHORTCUT_SERVICE_ROWS)
    for identifier, enabled in zip(SHORTCUT_SERVICE_ROWS, (True, False, True, False)):
        probe.enter(identifier, (labels['LANG_SET_BOOL_YES' if enabled else 'LANG_SET_BOOL_NO'],))
        probe.row('Cancel unchanged included service ' + identifier, 'Left', (labels[identifier],))
    probe.row('Back to grouped shortcut', 'Left', (labels[SHORTCUT_ROWS[1]],))
    probe.row('Back to Accessibility for grouped shortcut', 'Left', (labels['LANG_ACCESSIBILITY_SHORTCUT'],))
    require(path.read_bytes() == original, 'Merely browsing group services rewrote input assignments')
    transitions = []
    for index, enabled in enumerate((True, False, True), 1):
        before = path.read_bytes()
        identifiers = ('LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON', 'LANG_ACCESSIBILITY_TOUCH_ON') if enabled else (
            'LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF', 'LANG_ACCESSIBILITY_TOUCH_OFF')
        expected = tuple(probe.status_labels[identifier] for identifier in identifiers)
        probe.capture('Grouped shortcut ' + str(index), lambda: probe.press('Insert', clicks=3),
                      expected, status=True, grouped=True)
        transitions.append(verify_group_mapping_transition(before, path.read_bytes(), enabled))
        if not enabled:
            probe.capture('Ordinary navigation silent after grouped disable', lambda: probe.press('Down'), silent=True)
    before = path.read_bytes()
    probe.capture('Independent touch toggle restores mixed group fixture', lambda: probe.press('Insert', clicks=2),
                  (labels['LANG_ACCESSIBILITY_ENABLED'], labels['LANG_OFF']))
    transitions.append(verify_group_mapping_transition(before, path.read_bytes(), False))
    require(path.read_bytes() == original, 'Group operations did not restore the exact canonical input profile')
    probe.report['grouped_shortcut'] = dict(passed=True, transitions=transitions, mapping_restored=True,
        default_selected_services=['Talkbox', 'touch exploration'], input='Private acknowledged triple Power',
        scope='Real standard group/inclusion menus and single-job ordered status with settled PCM; no physical device acceptance')


def service_case(probe, scenario, capture_initial=True):
    if capture_initial:
        probe.capture("Initial ordinary interface", initial=True)
    if scenario == "services":
        status(probe, "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "Right")
        probe.capture("Ordinary navigation silent with eSpeak off", lambda: probe.press("Down"), silent=True)
        status(probe, "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON", "Right")
        probe.row("Normal interface resumes", "Up")
        status(probe, "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON", "Left")
        probe.row("Voice preference cannot mute eSpeak", "Down")
        return {"tts enabled": "on", "talk menu": "on", "talk mixer level": "0", "tts volume": "100"}
    status(probe, "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF", "Left")
    probe.row("Voice-file disable leaves synthesis active", "Down")
    status(probe, "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "Right")
    probe.capture("Ordinary navigation remains silent", lambda: probe.press("Up"), silent=True)
    status(probe, "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING", "Left")
    probe.capture("Missing voice file does not enable ordinary speech", lambda: probe.press("Down"), silent=True)
    return {"tts enabled": "off", "talk menu": "off", "talk mixer level": "0", "tts volume": "100"}


def browse_typing_settings(probe, runtime):
    directory = runtime / "simdisk/.rockbox"
    private_names = ("accessibility-typing.cfg", "accessibility-typing-echo.cfg")
    require(not any((directory / name).exists() for name in private_names),
            "Typing menu fixture is not a fresh default profile")
    probe.enter("LANG_ACCESSIBILITY_TYPING_SETTINGS", (probe.labels[TYPING_ROWS[0]],))
    probe.cycle("Typing settings", expected_order=TYPING_ROWS)
    for identifier, choices in TYPING_CHOICES:
        probe.enter(identifier, (probe.labels[choices[0]],))
        probe.cycle("Typing choices " + identifier, expected_order=choices, key="Up")
        probe.row("Return from " + identifier, "Left", (probe.labels[identifier],))
    probe.row("Back to Talkbox from Typing", "Left", (probe.labels["LANG_ACCESSIBILITY_TYPING_SETTINGS"],))
    require(not any((directory / name).exists() for name in private_names),
            "Read-only typing menu navigation changed default preferences")
    probe.report["typing_settings_scope"] = (
        "Five PL/EN rows and all mode/echo/capital/deletion choices with defaults retained; "
        "pitch title only, no typing-edit or physical touch acceptance")


def require_seconds_speech(text, seconds, unit, of_label=None):
    for prefix in ('TTS', 'TTS utterance'):
        spoken = strip_list_position(normalized(' '.join(phrases(text, prefix))), of_label)
        require(re.search(r'(?<!\d)' + str(seconds) + r'(?!\d)', spoken) is not None and
                normalized(unit) in spoken, 'Missing actual numeric seconds speech: ' + str(seconds))


def browse_touchscreen_settings(probe, runtime):
    policy = runtime / 'simdisk/.rockbox/accessibility-lock.cfg'
    require(not policy.exists(), 'System touchscreen fixture is not a clean legacy lock policy')
    labels = probe.labels
    probe.enter('LANG_TOUCHSCREEN_SETTINGS', (labels[SYSTEM_TOUCH_ROWS[0]],))
    probe.cycle('System touchscreen settings', expected_order=SYSTEM_TOUCH_ROWS)
    probe.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', (labels['LANG_ACCESSIBILITY_AUTOLOCK_LEGACY'],))
    probe.cycle('Automatic screen lock choices', expected_order=AUTOLOCK_CHOICES, key='Up')
    probe.row('Cancel unchanged fresh automatic lock selector', 'Left', (labels['LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT'],))
    require(not policy.exists(), 'Merely opening the fresh lock selector wrote a private profile')
    probe.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', (labels['LANG_ACCESSIBILITY_AUTOLOCK_LEGACY'],))
    selected = probe.row('Select 600 seconds', 'Down', ('600', labels['VOICE_SECONDS']))
    require_seconds_speech(selected, 600, labels['VOICE_SECONDS'], labels.get('VOICE_OF'))
    probe.row('Save 600 second policy', 'Right', (labels['LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT'],))
    prefix = b'RBACCESSIBILITY-LOCK:2\nunlock-button:0\nphysical-buttons:0\ntimeout:'
    require(policy.read_bytes() == prefix + b'600\n', '600-second policy did not persist or changed existing lock booleans')
    selected = probe.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', ('600', labels['VOICE_SECONDS']))
    require_seconds_speech(selected, 600, labels['VOICE_SECONDS'], labels.get('VOICE_OF'))
    probe.row('Restore legacy automatic lock policy', 'Up', (labels['LANG_ACCESSIBILITY_AUTOLOCK_LEGACY'],))
    probe.row('Save legacy automatic lock policy', 'Right', (labels['LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT'],))
    require(policy.read_bytes() == prefix + b'-1\n', 'Restored policy is not legacy -1 or changed existing booleans')
    probe.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', (labels['LANG_ACCESSIBILITY_AUTOLOCK_LEGACY'],))
    probe.row('Keep restored legacy automatic lock policy', 'Left', (labels['LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT'],))
    require(policy.read_bytes() == prefix + b'-1\n', 'Unchanged reopened policy changed persisted preferences')
    wake_preferences = runtime / 'simdisk/.rockbox/touch-wake.cfg'
    require(not wake_preferences.exists(), 'Touch wake fixture is not factory-disabled')
    probe.enter('LANG_TOUCH_WAKE_SETTINGS', (labels[TOUCH_WAKE_ROWS[0]], labels['LANG_OFF']))
    probe.cycle('Touch wake gestures', expected_order=TOUCH_WAKE_ROWS)
    for identifier in TOUCH_WAKE_ROWS:
        probe.enter(identifier, (labels['LANG_OFF'],))
        probe.cycle('Touch wake actions ' + identifier, expected_order=TOUCH_WAKE_CHOICES, key='Up')
        probe.row('Cancel unchanged touch wake action ' + identifier, 'Left', (labels[identifier], labels['LANG_OFF']))
    probe.row('Back to System touchscreen from Touch wake', 'Left', (labels['LANG_TOUCH_WAKE_SETTINGS'],))
    require(not wake_preferences.exists(), 'Read-only touch wake choices saved or enabled a policy')
    probe.row('Back to General System from Touchscreen', 'Left', (labels['LANG_TOUCHSCREEN_SETTINGS'],))
    probe.report['autolock_selector_scope'] = 'Ten System touch rows, twelve choices, actual 600-second numeric/unit speech and persistence; restored legacy -1 with both booleans unchanged; no physical timer acceptance'
    probe.report['touch_wake_selector_scope'] = 'Three tap counts and Off/light/unlock choices, unchanged factory-disabled profile; hardware wake/unlock not established by GUI navigation'


def browse_empty_feedback(probe, runtime):
    directory = runtime / "simdisk/.rockbox"
    names = ("empty-feedback.cfg", "empty-feedback.cfg.tmp")
    require(not any((directory / name).exists() for name in names), "Empty feedback fixture is not a fresh default profile")
    probe.enter("LANG_ACCESSIBILITY_EMPTY_FEEDBACK", (probe.labels[EMPTY_FEEDBACK_CHOICES[0]],))
    probe.cycle("Empty-place feedback choices", expected_order=EMPTY_FEEDBACK_CHOICES, key="Up")
    probe.row("Confirm original sound-only empty feedback", "Right",
              (probe.labels["LANG_ACCESSIBILITY_EMPTY_FEEDBACK"], probe.labels[EMPTY_FEEDBACK_CHOICES[0]]))
    require(not any((directory / name).exists() for name in names), "Default-restoring empty feedback navigation saved a private profile")
    probe.report["empty_feedback_picker_scope"] = (
        "Three PL/EN choices spoken in order; sound-only default restored before confirmation; "
        "no saved empty-feedback profile, actual touch-feedback effect not established by this GUI")


def require_numeric_speech(text, number, of_label=None):
    pattern = r'(?<![\d+\-.])' + re.escape(str(number)) + r'(?![\d.])'
    for prefix in ("TTS", "TTS utterance"):
        spoken = strip_list_position(normalized(" ".join(phrases(text, prefix))), of_label)
        require(re.search(pattern, spoken) is not None, "Missing exact synthesized numeric value: " + str(number))
        require(re.findall(r'[+\-]?\d+(?:\.\d+)?', spoken)[-1] == str(number),
                "Numeric setting ended with a different value: " + str(number))
        require(re.search(r'\brockbox\b', spoken) is None, "Numeric setting incorrectly announces Rockbox")


def browse_empty_pitch(probe, runtime):
    config = runtime / "simdisk/.rockbox/accessibility.cfg"
    before = config.read_bytes()
    parsed = parse_mapping_profile(before)
    require(parsed["empty_pitch"] and parsed["empty_semitones"] == -4,
            "Pitch picker fixture lacks the original enabled/-4 defaults")
    labels = probe.labels
    probe.enter("LANG_KEYCLICK_EMPTY_PITCH", (labels["LANG_SET_BOOL_YES"],))
    probe.row("Preview empty pitch disabled", "Down", (labels["LANG_SET_BOOL_NO"],))
    probe.row("Restore empty pitch enabled", "Up", (labels["LANG_SET_BOOL_YES"],))
    probe.row("Cancel unchanged empty pitch switch", "Left", (labels["LANG_KEYCLICK_EMPTY_PITCH"], labels["LANG_ON"]))
    observed = probe.enter("LANG_KEYCLICK_EMPTY_SEMITONES", ("-4",))
    require_numeric_speech(observed, -4, labels.get("VOICE_OF"))
    observed = probe.row("Preview empty pitch minus three", "Up", ("-3",))
    require_numeric_speech(observed, -3, labels.get("VOICE_OF"))
    observed = probe.row("Restore empty pitch minus four", "Down", ("-4",))
    require_numeric_speech(observed, -4, labels.get("VOICE_OF"))
    probe.row("Cancel unchanged empty pitch value", "Left", (labels["LANG_KEYCLICK_EMPTY_SEMITONES"], "-4"))
    require(config.read_bytes() == before, "Unchanged empty pitch selectors rewrote or changed either physical profile")
    probe.report["empty_pitch_picker_scope"] = (
        "Touch-only pitch switch and exact -4/-3/-4 numeric speech, original bytes preserved; "
        "selection preview is not actual empty-target sound-frequency acceptance")


def browse_physical_profiles(probe):
    labels = probe.labels
    probe.enter("LANG_ACCESSIBILITY_BUTTONS", (labels[BUTTON_ROOT_ROWS[0]],))
    probe.cycle("Physical button settings", expected_order=BUTTON_ROOT_ROWS)
    for identifier, rows in (("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", BUTTON_ROWS),
                             ("LANG_ACCESSIBILITY_PLAYBACK_ACTIONS", PLAYBACK_BUTTON_ROWS)):
        probe.enter(identifier, tuple(labels[value] for value in rows[0]))
        probe.cycle(identifier, expected_order=rows)
        probe.row("Back to physical settings from " + identifier, "Left", (labels[identifier],))
    for identifier, rows in zip(GUIDE_CONTEXT_ROWS, GUIDE_ROWS):
        probe.enter("LANG_ACCESSIBILITY_CONTROLS_GUIDE", (labels[GUIDE_CONTEXT_ROWS[0]],))
        probe.cycle("Controls guide contexts " + identifier, expected_order=GUIDE_CONTEXT_ROWS)
        probe.enter(identifier, tuple(labels[value] for value in rows[0]))
        probe.cycle("Default controls " + identifier, expected_order=rows)
        probe.row("Back from controls guide " + identifier, "Left", (labels["LANG_ACCESSIBILITY_CONTROLS_GUIDE"],))
    probe.row("Back to General System from Physical buttons", "Left", (labels["LANG_ACCESSIBILITY_BUTTONS"],))
    probe.report["controls_guide_scope"] = (
        "Four guide contexts and exact 20 compound default rows for menus and WPS; "
        "guide return path checked, no configured mapping edits or device acceptance")


def browse_brightness(probe):
    labels = probe.labels
    probe.enter("LANG_LCD_MENU")
    observed = probe.enter("LANG_BRIGHTNESS", ("100",))
    require_numeric_speech(observed, 100, labels.get("VOICE_OF"))
    for key, values in (("Down", range(99, 0, -1)), ("Up", range(2, 101))):
        for value in values:
            observed = probe.row("Brightness " + str(value), key, (str(value),))
            require_numeric_speech(observed, value, labels.get("VOICE_OF"))
            if value == 1:
                probe.capture("Brightness lower boundary silent with sound disabled",
                              lambda: probe.press("Down"), silent=True)
    probe.capture("Brightness upper boundary silent with sound disabled",
                  lambda: probe.press("Up"), silent=True)
    for key, value in (("Down", 99), ("Up", 100)):
        observed = probe.row("Brightness boundary " + str(value), key, (str(value),))
        require_numeric_speech(observed, value, labels.get("VOICE_OF"))
    probe.row("Cancel unchanged brightness", "Left", (labels["LANG_BRIGHTNESS"],))
    browse_backlight_timeout(probe)
    probe.row("Back to Display from LCD settings", "Left", (labels["LANG_LCD_MENU"],))
    probe.report["brightness_speech_scope"] = "Exact 100 through 50 to 1 and back through 50 to 100 synthesized levels in both traces; upper bound checked; restored original setting, no physical LCD acceptance"


def browse_boundary_settings(probe):
    labels = probe.labels
    probe.enter("LANG_ACCESSIBILITY_LIST_BOUNDARY", (labels[BOUNDARY_CHOICES[1]],))
    probe.cycle("List boundary feedback", expected_order=BOUNDARY_CHOICES[1:] + BOUNDARY_CHOICES[:1], key="Down")
    probe.row("Cancel unchanged list boundary feedback", "Left", (labels["LANG_ACCESSIBILITY_LIST_BOUNDARY"],))
    probe.report["list_boundary_menu"] = dict(passed=True, choices=list(BOUNDARY_CHOICES),
                                              default=BOUNDARY_CHOICES[1], restored=True,
                                              scope="Actual selector and speech; compiled core tests cover edge actions")


def browse_backlight_timeout(probe):
    labels = probe.labels
    observed = probe.enter("LANG_BACKLIGHT", (labels["LANG_ALWAYS"],))
    require_setting_label(observed, labels["LANG_ALWAYS"], labels.get("VOICE_OF"))
    observed = probe.row("Backlight timeout never", "Up", (labels["LANG_NEVER"],))
    require_setting_label(observed, labels["LANG_NEVER"], labels.get("VOICE_OF"))
    observed = probe.row("Backlight timeout always", "Down", (labels["LANG_ALWAYS"],))
    require_setting_label(observed, labels["LANG_ALWAYS"], labels.get("VOICE_OF"))
    for key, seconds in tuple(("Down", value) for value in (*range(1, 11), 15)) + tuple(("Up", value) for value in range(10, 0, -1)):
        unit = labels["VOICE_SECOND" if seconds == 1 else "VOICE_SECONDS"]
        observed = probe.row("Backlight timeout " + str(seconds), key, (str(seconds), unit))
        require_seconds_speech(observed, seconds, unit, labels.get("VOICE_OF"))
        require_numeric_speech(observed, seconds, labels.get("VOICE_OF"))
    observed = probe.row("Backlight timeout returns to always on", "Up", (labels["LANG_ALWAYS"],))
    require_setting_label(observed, labels["LANG_ALWAYS"], labels.get("VOICE_OF"))
    probe.row("Cancel unchanged backlight timeout", "Left", (labels["LANG_BACKLIGHT"],))
    probe.report["backlight_timeout_speech_scope"] = (
        "Never/Always and exact 1 through 10 and 15 seconds, returning to 1; both traces and units, no stray Rockbox; "
        "selector returned to simulator default zero, no physical backlight acceptance")


def require_setting_label(text, label, of_label=None):
    for prefix in ("TTS", "TTS utterance"):
        spoken = strip_list_position(normalized(" ".join(phrases(text, prefix))), of_label)
        require(not re.search(r'\brockbox\b', spoken),
                "Special numeric setting incorrectly announces Rockbox")
        require(spoken == normalized(label), "Missing exact setting label: " + label)


def require_connectivity_first_row(text, labels):
    for prefix in ("TTS", "TTS utterance"):
        spoken = phrases(text, prefix)
        row_indices = [index for index, value in enumerate(spoken)
                       if normalized(value).startswith(normalized(labels["LANG_HIBY_WIFI"]))]
        require(row_indices, "First Connectivity speech must include its Wi-Fi row")
        allowed_diagnostics = {normalized(labels[name]) for name in (
            "LANG_HIBY_CONNECTIVITY_UNAVAILABLE", "LANG_HIBY_CONNECTIVITY_PARTIAL",
            "LANG_HIBY_CONNECTIVITY_FAILED", "LANG_HIBY_BT_WORKING",
            "LANG_HIBY_CONNECTIVITY_STORAGE_ERROR", "LANG_HIBY_BT_CANCELLED", "LANG_HIBY_BT_TIMEOUT",
            "LANG_HIBY_BT_BUSY", "LANG_HIBY_BT_AIRPLANE_MODE")}
        require(all(normalized(value) in allowed_diagnostics for value in spoken[:row_indices[0]]),
                "First Connectivity speech must be the Wi-Fi row")
        require(not any(normalized(value) == normalized(labels["LANG_HIBY_BT_DONE"]) for value in spoken),
                "Connectivity entry must not replace its first row with Done")


def require_percent_speech(text, number, unit, of_label=None):
    for prefix in ("TTS", "TTS utterance"):
        spoken = strip_list_position(normalized(" ".join(phrases(text, prefix))), of_label)
        require(re.search(r"(?<!\d)" + str(number) + r"(?!\d)", spoken) is not None
                and normalized(unit) in spoken, "Missing spoken percent value or unit")
        require(not re.search(r"\brockbox\b", spoken), "Percent value incorrectly announces Rockbox")
        require(spoken == normalized(f"{number} {unit}"), "Unexpected percent value, unit or suffix")


def browse_synthesis_percent_settings(probe):
    labels = probe.labels
    rows = []
    for identifier, default in (("LANG_TTS_PITCH", 50), ("LANG_TTS_VOLUME", 100), ("LANG_TTS_RANGE", 50)):
        expected = (str(default), labels["VOICE_PERCENT"])
        observed = probe.enter(identifier, expected)
        require_percent_speech(observed, default, labels["VOICE_PERCENT"], labels.get("VOICE_OF"))
        require_position_presence(observed, labels, False)
        observed = probe.row("Preview percent " + identifier, "Up", (str(default + 1), labels["VOICE_PERCENT"]))
        require_percent_speech(observed, default + 1, labels["VOICE_PERCENT"], labels.get("VOICE_OF"))
        require_position_presence(observed, labels, False)
        observed = probe.row("Restore percent " + identifier, "Down", expected)
        require_percent_speech(observed, default, labels["VOICE_PERCENT"], labels.get("VOICE_OF"))
        require_position_presence(observed, labels, False)
        probe.row("Cancel unchanged percent " + identifier, "Left", (labels[identifier],))
        rows.append(dict(identifier=identifier, default=default, preview=default + 1, restored=True))
    probe.report["percent_units"] = dict(passed=True, restored=True, rows=rows,
        scope="Actual PL/EN selector navigation and both speech traces with PCM; unchanged stored defaults, not frequency ratios or physical audio acceptance")


def browse_position_choice_defaults(probe):
    labels = probe.labels
    for identifier, first in (("LANG_TTS_LANGUAGE", "LANG_TTS_SYSTEM"),
                              ("LANG_TTS_VARIANT", "LANG_TTS_DEFAULT_VARIANT")):
        text = probe.enter(identifier, (labels[first],))
        require_position_presence(text, labels, True, position=1)
        probe.row("Cancel unchanged " + identifier, "Left", (labels[identifier],))
    probe.report["position_choice_defaults"] = dict(passed=True, language=True, variant=True,
        scope="Fresh default language/variant selectors retain indices in both speech traces")


def browse_talkbox_settings(probe):
    labels = probe.labels
    probe.enter("LANG_TALKBOX_SETTINGS", (labels[TALKBOX_ROWS[0]],))
    rows = probe.cycle("Talkbox settings", expected_order=TALKBOX_ROWS)
    require(len(rows) == len(TALKBOX_ROWS), "Missing Talkbox position observations")
    for position, (identifier, text) in enumerate(zip(TALKBOX_ROWS, rows), 1):
        require_list_position(text, labels[identifier], labels, position, len(TALKBOX_ROWS))
    probe.enter("LANG_TTS", (labels[ESPEAK_ROWS[0]],))
    probe.cycle("eSpeak settings", expected_order=ESPEAK_ROWS)
    browse_position_choice_defaults(probe)
    browse_synthesis_percent_settings(probe)
    probe.row("Back to Talkbox from eSpeak", "Left", (labels["LANG_TTS"],))
    text = probe.enter("LANG_TTS_ENABLED", (labels["LANG_SET_BOOL_YES"],))
    require_list_position(text, labels["LANG_SET_BOOL_YES"], labels, 2, 2)
    probe.row("Cancel unchanged Talkbox enable switch", "Left", (labels["LANG_TTS_ENABLED"],))
    probe.enter("LANG_TTS_READER_SETTINGS", (labels[READER_ROWS[0]],))
    probe.cycle("Text reading settings", expected_order=READER_ROWS)
    probe.row("Back to Talkbox from Text reading settings", "Left", (labels["LANG_TTS_READER_SETTINGS"],))
    browse_announcement_settings(probe)
    return dict(talkbox_rows=list(TALKBOX_ROWS), espeak_rows=list(ESPEAK_ROWS), reader_rows=list(READER_ROWS))


def browse_announcement_settings(probe):
    labels = probe.labels
    settings = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
    rows = []
    identifier = "LANG_TALKBOX_ANNOUNCE_POSITION"
    require(re.search(r"CHOICE_SETTING\(0,\s*tts_announce_position,\s*" + identifier +
                      r",\s*TTS_POSITION_EXCEPT_SLIDERS\s*,", settings),
            "Position preference must default to everywhere except sliders")
    transitions = (
        ("LANG_TALKBOX_POSITION_EXCEPT_SLIDERS", ("Down",), "LANG_OFF", "disabled", False),
        ("LANG_OFF", ("Up", "Up"), "LANG_TALKBOX_POSITION_FILES", "files-only", False),
        ("LANG_TALKBOX_POSITION_FILES", ("Up",), "LANG_TALKBOX_POSITION_INTERFACE", "interface-only", True),
        ("LANG_TALKBOX_POSITION_INTERFACE", ("Up",), "LANG_TALKBOX_POSITION_EVERYWHERE", "everywhere", True),
        ("LANG_TALKBOX_POSITION_EVERYWHERE", ("Down", "Down", "Down"),
         "LANG_TALKBOX_POSITION_EXCEPT_SLIDERS", "enabled", True),
    )
    for initial, keys, destination, name, enabled in transitions:
        probe.enter(identifier, (labels[initial],))
        index = POSITION_CHOICES.index(initial)
        for step, key in enumerate(keys):
            index += -1 if key == "Up" else 1
            probe.row("Choose position mode " + name + " " + str(step), key, (labels[POSITION_CHOICES[index]],))
        require(POSITION_CHOICES[index] == destination, "Wrong position mode navigation plan")
        text = probe.row("Confirm " + name + " " + identifier, "Right", (labels[identifier],))
        require_list_position(text, labels[identifier], labels, TALKBOX_ROWS.index(identifier) + 1,
                              len(TALKBOX_ROWS), enabled=enabled)
    rows.append(dict(identifier=identifier, default="except-sliders", modes=5, disabled=True, restored=True))
    for field, identifier in (("tts_announce_dynamic", "LANG_TALKBOX_ANNOUNCE_DYNAMIC"),):
        require(re.search(r"OFFON_SETTING\(0,\s*" + field + r",\s*" + identifier + r",\s*true\s*,", settings),
                "Announcement preference must default on: " + field)
        probe.enter(identifier, (labels["LANG_SET_BOOL_YES"],))
        probe.row("Disable " + identifier, "Down", (labels["LANG_SET_BOOL_NO"],))
        text = probe.row("Confirm disabled " + identifier, "Right", (labels[identifier],))
        require_list_position(text, labels[identifier], labels, TALKBOX_ROWS.index(identifier) + 1,
                              len(TALKBOX_ROWS), enabled=field != "tts_announce_position")
        probe.enter(identifier, (labels["LANG_SET_BOOL_NO"],))
        probe.row("Restore enabled " + identifier, "Up", (labels["LANG_SET_BOOL_YES"],))
        text = probe.row("Confirm enabled " + identifier, "Right", (labels[identifier],))
        require_list_position(text, labels[identifier], labels, TALKBOX_ROWS.index(identifier) + 1, len(TALKBOX_ROWS))
        rows.append(dict(identifier=identifier, default=True, disabled=True, restored=True))
    probe.report["announcement_settings"] = dict(passed=True, restored=True, rows=rows,
        scope="Five position modes on actual interface rows in both traces; dynamic selector changes only, no automatic content event acceptance")


RAPID_WRAP_CASES = (("Up", 2), ("Down", 2), ("Up", 3), ("Down", 3))


def rapid_wrap_plan(key, clicks):
    require((key, clicks) in RAPID_WRAP_CASES and type(clicks) is int and len(TALKBOX_ROWS) == 11,
            "Unapproved rapid Talkbox wrap case")
    start = 1 if key == "Up" else len(TALKBOX_ROWS) - 2
    step = -1 if key == "Up" else 1
    return dict(case=key.lower() + "-" + str(clicks), key=key, clicks=clicks,
                start_row=TALKBOX_ROWS[start], wrapped_row=TALKBOX_ROWS[-1 if key == "Up" else 0],
                final_row=TALKBOX_ROWS[(start + step * clicks) % len(TALKBOX_ROWS)])


def rapid_wrap_speech(text, labels, key, clicks):
    plan = rapid_wrap_plan(key, clicks)
    observed = {}
    for prefix, name in (("TTS", "request_rows"), ("TTS utterance", "synthesized_rows")):
        segments = phrases(text, prefix)
        rows, positions = [], []
        for index, segment in enumerate(segments):
            matches = [identifier for identifier in TALKBOX_ROWS if normalized(segment) == normalized(labels[identifier]) or
                       prefix == "TTS utterance" and normalized(segment).startswith(normalized(labels[identifier]) + " ")]
            if matches:
                rows.append(max(matches, key=lambda identifier: len(normalized(labels[identifier]))))
                positions.append(index)
        require(rows and rows[-1] == plan["final_row"] and rows.count(plan["final_row"]) == 1,
                "Rapid wrap final row is missing, duplicated or not last in " + prefix)
        expected_final = (f"{labels[plan['final_row']]} {TALKBOX_ROWS.index(plan['final_row']) + 1} "
                          f"{labels['VOICE_OF']} {len(TALKBOX_ROWS)}")
        require(normalized(" ".join(segments[positions[-1]:])) == normalized(expected_final),
                "Unexpected speech after rapid wrap final row in " + prefix)
        observed[name] = rows
    required = [plan["wrapped_row"]] + ([plan["final_row"]] if clicks == 3 else [])
    preceding = TALKBOX_ROWS[0 if key == "Up" else -1]
    require(observed["request_rows"] in (required, [preceding] + required),
            "Rapid wrap must request its wrapped row before any following row")
    cursor = 0
    for identifier in observed["synthesized_rows"]:
        require(identifier in observed["request_rows"][cursor:], "Synthesized rapid rows contradict request order")
        cursor = observed["request_rows"].index(identifier, cursor) + 1
    return dict(observed, requests=phrases(text, "TTS"), utterances=phrases(text))


def rapid_wrap_profile(data):
    parsed = parse_mapping_profile(data)
    source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
    declaration = re.search(r'physical_buttons\[ACCESSIBILITY_BUTTON_COUNT\]\s*=\s*\{([^}]+)\}', source)
    require(declaration is not None and re.findall(r'BUTTON_\w+', declaration[1]) ==
            ["BUTTON_POWER", "BUTTON_PLAY", "BUTTON_NEXT", "BUTTON_VOL_UP", "BUTTON_VOL_DOWN"],
            "Actual rapid navigation physical button indexes changed")
    masks = input_button_contract()
    for profile in ("buttons", "playback_buttons"):
        for button in (3, 4):
            for slot in range(4):
                require(parsed[profile][(button, slot)] == 27 and
                        parsed["button_launch" if profile == "buttons" else "playback_button_launch"][(button, slot)] == 0,
                        "Rapid wrap cannot use a physical volume multitap override")
    return dict(up=dict(mask=masks["Up"], button_index=3), down=dict(mask=masks["Down"], button_index=4),
                profiles=["buttons", "playback_buttons"], slots=[0, 1, 2, 3], action=27,
                scope="Physical volume keys; all slots SYSTEM, native release navigation; no virtual touch arrows or profile remapping")


def browse_rapid_wrap(probe, runtime):
    boundary = probe.report.get("list_boundary_menu", {})
    require(boundary.get("passed") is True and boundary.get("restored") is True and
            boundary.get("default") == BOUNDARY_CHOICES[1] and boundary.get("choices") == list(BOUNDARY_CHOICES),
            "Rapid wrap requires the observed unchanged Sound-only boundary default")
    anchor = "LANG_ACCESSIBILITY_LIST_BOUNDARY"
    require(speech_contains(probe.latest, (probe.labels[anchor],)), "Rapid wrap caller position is not the restored boundary row")
    require_list_position(probe.latest, probe.labels[anchor], probe.labels, TALKBOX_ROWS.index(anchor) + 1, len(TALKBOX_ROWS))
    profile_path = runtime / "simdisk/.rockbox/accessibility.cfg"
    profile_before = mapping_file_identity(profile_path)
    navigation_profile = rapid_wrap_profile(profile_path.read_bytes())
    report = dict(schema="services-rapid-wrap:1", passed=False, timing_exercised=False, restored=False,
                  language=probe.report.get("language"),
                  menu_rows=list(TALKBOX_ROWS), feedback=BOUNDARY_CHOICES[1], keyclick="off",
                  caller_row_before=anchor, caller_row_after=None, cases=[],
                  navigation_profile=navigation_profile, profile_before=profile_before,
                  scope="Actual private HWND navigation, request order and final speech/PCM; intermediate speech may be canceled; no physical audio acceptance")
    probe.report["rapid_wrap"] = report
    for key, clicks in RAPID_WRAP_CASES:
        case = dict(rapid_wrap_plan(key, clicks), passed=False, timing_exercised=False)
        report["cases"].append(case)
        probe.seek(case["start_row"])
        require(speech_contains(probe.latest, (probe.labels[case["start_row"]],)), "Rapid wrap start row was not observed")
        check_index = len(probe.report["checks"])
        burst_index = len(probe.report.get("rapid_navigation_bursts", []))

        def navigate():
            try:
                probe.rapid_navigation(key, clicks)
            finally:
                bursts = probe.report.get("rapid_navigation_bursts", [])
                if len(bursts) > burst_index:
                    case["input"] = bursts[burst_index]

        expected = (probe.labels[case["final_row"]],)
        text = probe.capture("Rapid Talkbox wrap " + case["case"], navigate, expected)
        require(case.get("input", {}).get("passed") is True and case["input"].get("timing_exercised") is True,
                "Rapid navigation timing did not actually pass")
        case.update(rapid_wrap_speech(text, probe.labels, key, clicks), check_index=check_index,
                    passed=True, timing_exercised=True)
    probe.seek(anchor)
    require(speech_contains(probe.latest, (probe.labels[anchor],)), "Rapid wrap failed to restore the caller row")
    require_list_position(probe.latest, probe.labels[anchor], probe.labels, TALKBOX_ROWS.index(anchor) + 1, len(TALKBOX_ROWS))
    report["profile_after"] = verify_mapping_read_only(profile_path, profile_before)
    report.update(passed=True, timing_exercised=True, restored=True, caller_row_after=anchor)


def browse_bluetooth_layout(probe, runtime):
    labels = probe.labels
    directory = runtime / "simdisk/.rockbox"
    files = ("bluetooth.cfg", "bluetooth.cfg.tmp", "connectivity.cfg", "accessibility.cfg")

    def snapshot():
        result = {}
        for name in files:
            try:
                result[name] = (directory / name).read_bytes()
            except FileNotFoundError:
                result[name] = None
        return result

    def check_row(observed, identifiers, position, total, indices=True):
        require_list_position(observed, " ".join(labels[identifier] for identifier in identifiers),
                              labels, position, total, enabled=indices)

    before = snapshot()
    observed = probe.enter("LANG_HIBY_BT_TITLE", tuple(labels[identifier] for identifier in BLUETOOTH_ROOT_ROWS[0]))
    check_row(observed, BLUETOOTH_ROOT_ROWS[0], 1, 7)
    root = probe.cycle("Bluetooth root", expected_order=BLUETOOTH_ROOT_ROWS)
    require(len(root) == 7, "Bluetooth root must have seven rows")
    for index, observed in enumerate(root):
        check_row(observed, BLUETOOTH_ROOT_ROWS[index], index + 1, 7)
    observed = probe.enter("LANG_HIBY_BT_SETTINGS", tuple(labels[identifier] for identifier in BLUETOOTH_PREFERENCE_ROWS[0]))
    check_row(observed, BLUETOOTH_PREFERENCE_ROWS[0], 1, 5)
    preferences = probe.cycle("Bluetooth preferences", expected_order=BLUETOOTH_PREFERENCE_ROWS)
    require(len(preferences) == 5, "Bluetooth preferences must have five rows")
    for index, observed in enumerate(preferences):
        check_row(observed, BLUETOOTH_PREFERENCE_ROWS[index], index + 1, 5)
    for index, choices in enumerate(BLUETOOTH_CHOICES):
        identifier, default = BLUETOOTH_PREFERENCE_ROWS[index]
        selection = choices.index(default)
        indices = identifier != "LANG_HIBY_BT_RETRY_WINDOW"
        observed = probe.enter(identifier, (labels[default],))
        check_row(observed, (default,), selection + 1, len(choices), indices)
        rotated = choices[selection:] + choices[:selection]
        rows = probe.cycle("Bluetooth choices " + identifier, expected_order=rotated)
        require(len(rows) == len(choices), "Unexpected Bluetooth choice count")
        for offset, observed in enumerate(rows):
            check_row(observed, (rotated[offset],), (selection + offset) % len(choices) + 1, len(choices), indices)
        observed = probe.row("Cancel unchanged Bluetooth choice " + identifier, "Left", (labels[identifier], labels[default]))
        check_row(observed, (identifier, default), index + 1, 5)
    observed = probe.row("Back to Bluetooth root from preferences", "Left", (labels["LANG_HIBY_BT_SETTINGS"],))
    check_row(observed, ("LANG_HIBY_BT_SETTINGS",), 6, 7)
    observed = probe.row("Back to Connectivity from Bluetooth", "Left",
                         (labels["LANG_HIBY_BT_TITLE"], labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]))
    returned_row = []
    for prefix in ("TTS", "TTS utterance"):
        segments = phrases(observed, prefix)
        if segments and normalized(segments[0]) == normalized(labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]):
            segments = segments[1:]
        returned_row.extend(f"{prefix}: {segment}\n" for segment in segments)
    check_row("".join(returned_row), ("LANG_HIBY_BT_TITLE", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE"), 2, 3)
    after = snapshot()
    require(after == before, "Read-only Bluetooth navigation changed preference/profile bytes or file presence")
    probe.report["bluetooth_layout"] = {
        "root_rows": 7, "preference_rows": 5, "choice_counts": [len(choices) for choices in BLUETOOTH_CHOICES],
        "numeric_retry_indices": False, "other_choice_indices": True, "choices_cancelled": 4,
        "action_count": bluetooth_layout_action_count(), "restored": True,
        "files": {name: hashlib.sha256(data).hexdigest() if data is not None else None for name, data in before.items()},
        "scope": "Unavailable simulator menu traversal only; no radio operation, preference edits, busy/native or hardware acceptance",
    }


def layout_case(probe, runtime):
    labels = probe.labels
    private_config = runtime / "simdisk/.rockbox/accessibility.cfg"
    private_before = private_config.read_bytes()
    probe.capture("Initial root", initial=True)
    probe.enter("LANG_SETTINGS")
    settings = probe.cycle("Settings")
    require(sum(speech_contains(row, (labels["LANG_CONNECTIVITY"],)) for row in settings) == 1,
            "Settings must contain exactly one direct Connectivity entry")
    probe.enter("LANG_GENERAL_SETTINGS")
    probe.cycle("General settings", ("LANG_CONNECTIVITY", "LANG_HIBY_BT_TITLE"))
    probe.enter("LANG_SYSTEM")
    system_rows = probe.cycle("General System", ("LANG_HIBY_WIFI_STARTUP", "LANG_HIBY_BT_TITLE", "LANG_CONNECTIVITY"))
    probe.report["system_input_positions"] = system_input_rows(system_rows, labels)
    browse_touchscreen_settings(probe, runtime)
    browse_physical_profiles(probe)
    require(private_config.read_bytes() == private_before,
            "Read-only physical button menu navigation changed private config")
    probe.report["physical_button_menu_scope"] = (
        "Five ordered root rows and two independent 21-row profiles; "
        "private profile unchanged; no mapping edit, physical timing or hardware acceptance")
    probe.row("Back to General", "Left")
    probe.enter("LANG_DISPLAY")
    probe.cycle("Display", ("LANG_TOUCHSCREEN_SETTINGS", "LANG_ACCESSIBILITY_BUTTONS"))
    browse_brightness(probe)
    probe.row("Back to General from Display", "Left")
    probe.enter("LANG_VOICE", (labels["LANG_TALKBOX_SETTINGS"],))
    probe.cycle("Accessibility", expected_order=ACCESSIBILITY_ROWS)
    hierarchy = browse_talkbox_settings(probe)
    browse_typing_settings(probe, runtime)
    browse_boundary_settings(probe)
    browse_rapid_wrap(probe, runtime)
    probe.enter("LANG_ACCESSIBILITY_DISPLAY_SETTINGS", (labels[ACCESSIBILITY_DISPLAY_ROWS[0]],))
    probe.cycle("Accessibility screen settings", expected_order=ACCESSIBILITY_DISPLAY_ROWS)
    probe.enter("LANG_ACCESSIBILITY_SCREEN_STATE", (labels[SCREEN_STATE_ROWS[0]],))
    probe.cycle("Screen state announcements", expected_order=SCREEN_STATE_ROWS)
    probe.row("Back to Screen settings from Screen announcements", "Left", (labels["LANG_ACCESSIBILITY_SCREEN_STATE"],))
    probe.row("Back to Talkbox from Screen settings", "Left", (labels["LANG_ACCESSIBILITY_DISPLAY_SETTINGS"],))
    probe.enter("LANG_ACCESSIBILITY", (labels["LANG_ACCESSIBILITY_ENABLED"],))
    probe.cycle("Touch submenu", expected_order=TOUCH_ROWS)
    browse_empty_feedback(probe, runtime)
    browse_empty_pitch(probe, runtime)
    probe.enter("LANG_ACCESSIBILITY_GESTURES", (labels["LANG_ACCESSIBILITY_INTERFACE_ACTIONS"],))
    gesture_profiles = BUTTON_ROOT_ROWS[:2]
    probe.cycle("Gesture assignment profiles", expected_order=gesture_profiles)
    for identifier in gesture_profiles:
        probe.enter(identifier, (labels["LANG_ACCESSIBILITY_SWIPE_LEFT"], labels["LANG_ACCESSIBILITY_UNASSIGNED"]))
        probe.cycle("Gesture assignments " + identifier, expected_order=GESTURE_ROWS + ("LANG_RESET",))
        probe.enter("LANG_ACCESSIBILITY_SWIPE_LEFT", (labels["LANG_ACCESSIBILITY_UNASSIGNED"],))
        probe.cycle("Gesture action selector " + identifier, expected_order=GESTURE_ACTION_ROWS, key="Up")
        probe.row("Cancel action selector to Gesture assignments " + identifier, "Left",
                  (labels["LANG_ACCESSIBILITY_SWIPE_LEFT"], labels["LANG_ACCESSIBILITY_UNASSIGNED"]))
        probe.row("Back to Gesture profiles from " + identifier, "Left", (labels[identifier],))
    probe.row("Back to Touch submenu from Gesture profiles", "Left", (labels["LANG_ACCESSIBILITY_GESTURES"],))
    for index in range(4):
        probe.row(f"Back to Settings {index + 1}", "Left")
    require(private_config.read_bytes() == private_before, "Read-only gesture menu navigation changed private config")
    probe.report["talkbox_hierarchy"] = dict(passed=True, restored=True,
                                             accessibility_rows=list(ACCESSIBILITY_ROWS), **hierarchy)
    probe.report["gesture_menu_scope"] = "8 touch rows, two independent 21-row gesture profiles and 27 action labels/order; selector canceled and private profile unchanged; no mapped new-action or touch acceptance"
    observed = probe.enter("LANG_CONNECTIVITY", (labels["LANG_HIBY_WIFI"], labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]))
    require_connectivity_first_row(observed, labels)
    probe.report["connectivity_first_row_scope"] = "First selected row is Wi-Fi in both traces; only explicit working/unavailable/failure/partial diagnostics may precede it, never generic Done; no RF acceptance"
    probe.row("Connectivity Bluetooth unavailable", expected=(labels["LANG_HIBY_BT_TITLE"],
                                                              labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]))
    browse_bluetooth_layout(probe, runtime)
    probe.row("Connectivity airplane initially off", expected=(labels["LANG_HIBY_AIRPLANE_MODE"], labels["LANG_OFF"]))
    preferences = runtime / "simdisk/.rockbox/connectivity.cfg"
    probe.row("Airplane ON reports unavailable/partial", "Right",
              (labels["LANG_HIBY_AIRPLANE_MODE"], labels["LANG_HIBY_CONNECTIVITY_PARTIAL"],
               labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]))
    require(connectivity_preferences(preferences.read_bytes()) == (1, 1, 1), "Airplane lost prior requested states")
    probe.row("Airplane OFF retains prior requests and unavailable state", "Right",
              (labels["LANG_HIBY_AIRPLANE_MODE"], labels["LANG_OFF"], labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]))
    require(connectivity_preferences(preferences.read_bytes()) == (1, 1, 0), "Airplane OFF did not preserve restore preferences")
    probe.row("Wi-Fi still unavailable", "Down", (labels["LANG_HIBY_WIFI"], labels["LANG_HIBY_CONNECTIVITY_UNAVAILABLE"]))
    for index in range(2):
        probe.row(f"Back to root {index + 1}", "Left")
    probe.enter("LANG_SYSTEM")
    probe.cycle("Root System information", ("LANG_HIBY_WIFI_STARTUP", "LANG_CONNECTIVITY", "LANG_HIBY_BT_TITLE"))
    probe.report["airplane_scope"] = "SIM UI/preferences only; no actual RF restoration acceptance"
    return {"tts enabled": "on", "talk menu": "off", "talk mixer level": "0", "tts volume": "100"}


def make_tone(path):
    tone = array.array("h", (int(6000 * math.sin(2 * math.pi * 997 * sample / 44100))
                            for sample in range(44100)))
    if sys.byteorder != "little":
        tone.byteswap()
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        for second in range(45):
            stream.writeframesraw(tone.tobytes())


def music_case(probe):
    probe.capture("Initial music case root", initial=True)
    probe.enter("LANG_DIR_BROWSER")
    for attempt in range(12):
        if "001 service music" in normalized(" ".join(phrases(probe.latest))):
            break
        probe.row(f"Find synthetic music {attempt + 1}")
    else:
        raise AssertionError("Synthetic music filename not found")
    require_position_presence(probe.latest, probe.labels, True)
    probe.music_expected = True
    probe.capture("Start synthetic music", lambda: probe.press("Right"), optional=True)
    probe.capture("WPS playback profile consumes unassigned Next double", lambda: probe.press("Right", clicks=2), silent=True)
    for identifier in ("LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON"):
        observed = probe.capture("WPS playback profile " + identifier, lambda: probe.press("Left"),
                                 (probe.status_labels[identifier],), status=True)
        require("TTS audio playback: 1" in observed and "TTS audio playback: 0" not in observed,
                "Playback profile service action interrupted the actual music stream")
        probe.capture("Music recovery after WPS playback profile " + identifier, silent=True)
    probe.capture("Menu during continuing music", lambda: probe.chord("Insert", "Left"))
    probe.capture("Music baseline", silent=True)
    for identifier in ("LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON"):
        observed = status(probe, identifier, "Right")
        require("TTS audio playback: 1" in observed and "TTS audio playback: 0" not in observed,
                "Actual music playback did not continue during service status")
        probe.capture("Music recovery after " + identifier, silent=True)
    probe.report["physical_profile_effect_scope"] = (
        "Asymmetric v9 mappings: WPS Next-double NONE is silent, Play-single toggles eSpeak; "
        "menus with continuing music use interface Next-double toggles. Actual status/audio/PCM required; no physical hardware acceptance")
    return {"tts enabled": "on", "talk menu": "off", "talk mixer level": "0", "tts volume": "100"}


def tone_windows(data):
    require(len(data) % 4 == 0, "Tone analysis requires stereo S16 frames")
    samples = array.array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    mono = samples[::2]
    size = 2048
    bases = [(tuple(math.cos(2 * math.pi * frequency * index / 44100) for index in range(size)),
              tuple(math.sin(2 * math.pi * frequency * index / 44100) for index in range(size)))
             for frequency in (911, 997, 1103)]
    amplitudes = []
    for offset in range(0, len(mono) - size + 1, size):
        block = mono[offset:offset + size]
        powers = [2 * math.hypot(sum(value * cosine for value, cosine in zip(block, cosines)),
                                sum(value * sine for value, sine in zip(block, sines))) / size
                  for cosines, sines in bases]
        if powers[1] > 3 * max(powers[0], powers[2], 0.1):
            amplitudes.append(powers[1])
    return amplitudes


def verify_music(directory, report):
    data = (directory / "audio.raw").read_bytes()
    baseline = next(check for check in report["checks"] if check["name"] == "Music baseline")
    levels = tone_windows(data[baseline["pcm_start"]:baseline["pcm_end"]])
    require(levels and max(levels) > 1, "No selective 997 Hz background baseline at 44100 Hz")
    reference = sorted(levels)[len(levels) // 2]
    transitions = []
    for check in report["checks"]:
        if not check["status_only"]:
            continue
        levels = tone_windows(data[check["pcm_start"]:check["pcm_end"]])
        require(levels and min(levels) < reference * 0.7, "No actual background-tone attenuation during status")
        recovery = next(item for item in report["checks"] if item["name"] == "Music recovery after " + check["name"])
        restored = tone_windows(data[recovery["pcm_start"]:recovery["pcm_end"]])
        require(restored and max(restored) > reference * 0.8, "Background tone did not recover after status")
        transitions.append({"status": check["name"], "baseline": reference, "minimum": min(levels),
                            "recovered": max(restored)})
    identifiers = ("LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF", "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON")
    require([item["status"] for item in transitions] ==
            ["WPS playback profile " + identifier for identifier in identifiers] + list(identifiers),
            "Incomplete or aliased WPS/interface music toggle coverage")
    report["ducking_pcm"] = transitions
    report["music_pcm_scope"] = "Measured tone attenuation/recovery; speech-only sessions establish nonzero status PCM separately"


def run_session(native, desktop, desktop_handle, runtime, results, language, scenario, labels, timeout, input_layout=None):
    directory = results / (language + "-" + scenario)
    directory.mkdir()
    report = {"language": language, "scenario": scenario, "desktop": desktop,
              "action_budget_seconds": session_action_budget(scenario, timeout),
              "passed": False, "raw_input": [],
              "checks": [], "sessions": [], "music": scenario == "music", "input_layout": input_layout}
    configure_session(runtime, directory, language, scenario)
    resources = runtime / "simdisk/.rockbox"
    mapping_before = mapping_file_identity(resources / "accessibility.cfg")
    require(mapping_before["version"] == (8 if scenario == "missing-voice" else 11),
            "Actual session did not receive the reviewed legacy/current profile")
    if scenario == "music":
        music = runtime / "simdisk/001 Service music.wav"
        if not music.exists():
            make_tone(music)
        report["synthetic_music"] = {"path": str(music), "sha256": digest(music),
                                     "purpose": "Shared generated 997 Hz background for PL/EN ducking measurements",
                                     "retained_after_test": True}
    immutable = regular_files(runtime)
    legacy_name = "simdisk/.rockbox/accessibility-shortcut.cfg"
    unchanged = {legacy_name: immutable[legacy_name]}
    report["legacy_shortcut_profile"] = {"sha256": immutable[legacy_name], "unchanged": False,
                                         "scope": "Synthetic obsolete private policy, ignored by the new standard group preferences"}
    for name in ("config.cfg", "accessibility.cfg", "accessibility-shortcut.cfg", "connectivity.cfg"):
        immutable.pop("simdisk/.rockbox/" + name)
    probe = ServicesProbe(native, desktop, runtime, directory, report, labels, timeout)
    try:
        probe.launch(desktop_handle)
        read_only_before = mapping_before
        if scenario == 'services':
            grouped_service_case(probe, runtime)
            read_only_before = mapping_file_identity(resources / 'accessibility.cfg')
            require(read_only_before['sha256'] == mapping_before['sha256'] and
                    read_only_before['bytes'] == mapping_before['bytes'],
                    'Group changes left the canonical profile modified')
            report['grouped_shortcut'].update(input_before=mapping_before, input_after=read_only_before)
        if scenario == "layout-connectivity":
            expected = layout_case(probe, runtime)
        elif scenario == "music":
            expected = music_case(probe)
        else:
            expected = service_case(probe, scenario, capture_initial=scenario != 'services')
        probe.close(long_hold=language == "polski" and scenario == "services")
        report["mapping_read_only"] = verify_mapping_read_only(resources / "accessibility.cfg", read_only_before)
        observation = probe.observation.read_bytes()
        require(len(observation) % 4 == 0, "Observation tap ended with a partial stereo frame")
        report["observation_pcm"] = {
            "path": str(directory / "runtime/audiodebug.raw"),
            "sha256": hashlib.sha256(observation).hexdigest(), "pcm": pcm_statistics(observation),
            "format": observation_format(probe.text()), "sources": TRACE_SOURCES,
            "role": "Buffered optional observation; independent offsets, excludes no-data device silence; not final master PCM",
        }
        settings = saved_settings_snapshot(resources, language, expected, report)
        report["saved_settings"] = {name: settings[name] for name in expected}
        verify_pcm(directory, report)
        if scenario == "music":
            verify_music(directory, report)
        report["passed"] = True
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["primary_traceback"] = traceback.format_exc()
        raise
    finally:
        try:
            probe.close()
            require(probe.process is None or probe.process.poll() is not None, "Owned process still running")
            preserve_runtime_changes(runtime, directory, immutable, unchanged)
            report["legacy_shortcut_profile"]["unchanged"] = True
        except BaseException as error:
            report["passed"] = False
            report["cleanup_error"] = f"{type(error).__name__}: {error}"
            report["cleanup_traceback"] = traceback.format_exc()
            if "error" not in report:
                raise
        finally:
            report["acceptance_touch"] = report["acceptance_hardware"] = report["acceptance_nvda"] = False
            write_json(directory / "session.json", report)
    return report


def long_power_stress_receipt(sessions):
    expected = {(language, scenario) for language in LANGUAGES
                for scenario in ("services", "missing-voice", "layout-connectivity", "music")}
    require(len(sessions) == 8 and {(item["language"], item["scenario"]) for item in sessions} == expected,
            "Long-Power receipt requires the unchanged eight-session contract")
    stressed = [item for item in sessions if item.get("shutdown", {}).get("style") == "long-hold-until-exit"]
    require(len(stressed) == 1, "Exactly one actual long-Power shutdown is required")
    session = stressed[0]
    shutdown = session["shutdown"]
    require(session["language"] == "polski" and session["scenario"] == "services" and session["passed"] and
            shutdown["passed"] and shutdown["exit_code"] == 0 and not shutdown["defects"] and shutdown["observed"] and
            shutdown["max_hold_seconds"] == 12 and 0 < shutdown["hold_seconds"] <= 12.1,
            "Declared long-Power shutdown did not pass")
    require(all(item is session or item.get("shutdown", {}).get("style") == "bounded-cue-release" for item in sessions),
            "Other sessions must retain normal bounded shutdown")
    inputs = session["raw_input"][shutdown["raw_input_start"]:shutdown["raw_input_end"]]
    require(inputs and inputs[0]["key"] == "Insert" and inputs[0]["pressed"] is True and len(inputs) <= 2,
            "Missing actual owned Power keydown")
    require(session["pid"] > 0 and session["hwnd"] > 0 and
            re.fullmatch(r"RBServices_[a-f0-9]{32}", session["desktop"]) and
            all(item["pid"] == session["pid"] and item["hwnd"] == session["hwnd"] and
                item["desktop"] == session["desktop"] for item in inputs), "Long-Power input ownership changed")
    if shutdown["hold_end"] == "owned-process-exit":
        require(len(inputs) == 1 and not shutdown["release_sent"], "Long-Power stress released before process exit")
    else:
        require(shutdown["hold_end"] == "hold-limit-release" and shutdown["release_sent"] and len(inputs) == 2 and
                inputs[1]["key"] == "Insert" and inputs[1]["pressed"] is False and
                inputs[1]["monotonic"] - inputs[0]["monotonic"] >= 11.95 and shutdown["hold_seconds"] >= 11.95,
                "Long-Power stress released before its hold bound")
    return dict(shutdown, session="polski-services", pid=session["pid"], hwnd=session["hwnd"], desktop=session["desktop"])


def worker(arguments):
    require(not getattr(arguments, 'keyclick_private', False), 'Private PCM mode requires the separately reviewed central worker')
    native = PrivateDesktop()
    require(re.fullmatch(r"RBServices_[a-f0-9]{32}", arguments.desktop or ""), "Invalid private desktop name")
    native.assert_private(arguments.desktop)
    require(native.kernel.WaitForSingleObject(arguments.gate, 30000) == 0, "Parent job-start gate was not released")
    results = confined_path(arguments.results, project_materials_root(ROOT) / SCOPE)
    runtime = confined_path(results / "fixture", results)
    freeze, build = validate_authorization(arguments, runtime / "rockboxui.exe")
    layout_path = results / "input-layout.json"
    require(sha256_value(arguments.input_layout_sha256) and digest(layout_path) == arguments.input_layout_sha256,
            "Parent input-layout binding changed")
    input_layout = json.loads(layout_path.read_text(encoding="utf-8"))
    require(input_layout["sha256"] == arguments.exe_sha256 and input_layout == input_symbol_layout(
        runtime / "rockboxui.exe", input_layout["nm_symbol_line"]), "Invalid frozen input layout")
    labels = compiled_labels(build)
    desktop_handle = native.checked(native.user.GetThreadDesktop(native.kernel.GetCurrentThreadId()))
    report = {"passed": False, "scope": SCOPE, "sessions": [], "limitations": LIMITATIONS,
              "input_desktop_before": native.input(), "source_layout": source_layout(), "labels": labels}
    try:
        for language in LANGUAGES:
            for scenario in ("services", "missing-voice", "layout-connectivity"):
                report["sessions"].append(run_session(native, arguments.desktop, desktop_handle, runtime, results,
                                                       language, scenario, labels[language], arguments.timeout, input_layout))
        for language in LANGUAGES:
            report["sessions"].append(run_session(native, arguments.desktop, desktop_handle, runtime, results,
                                                   language, "music", labels[language], arguments.timeout, input_layout))
        report["long_power_stress"] = long_power_stress_receipt(report["sessions"])
        bound_checks(ROOT, freeze["sources"])
        bound_checks(build, freeze["build_files"], runtime / "rockboxui.exe")
        report["input_desktop_after"] = native.input()
        require(report["input_desktop_before"] == report["input_desktop_after"], "User input desktop changed")
        report["passed"] = all(session["passed"] for session in report["sessions"]) and len(report["sessions"]) == 8
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["primary_traceback"] = traceback.format_exc()
    finally:
        write_json(results / "worker.json", report)
    return 0 if report["passed"] else 1


def execute(arguments):
    from test_tts_recorder_gui import ExecutableLoan
    from test_tts_simulator import windows_backend
    freeze, build = validate_authorization(arguments)
    native = PrivateDesktop()
    compiled_labels(build)
    keyclick_private = getattr(arguments, 'keyclick_private', False)
    results = new_results("keyclick" if keyclick_private else "run")
    report = {"scope": SCOPE, "passed": False, "gui_acceptance_complete": False,
              "long_power_stress": {"passed": False, "session": "polski-services"},
              "freeze": str(arguments.freeze), "freeze_sha256": arguments.freeze_sha256,
              "exe_sha256": arguments.exe_sha256, "version": freeze["version"], "limitations": LIMITATIONS,
              "acceptance_touch": False, "acceptance_hardware": False, "acceptance_nvda": False,
              "keyclick_private": keyclick_private, "keyclick_pcm_acceptance_complete": False,
              "input_desktop_before": native.input(), "no_global_input": True, "desktop_switched": False}
    before = regular_files(build / "simdisk")
    input_layout = prepare_input_layout(build / "rockboxui.exe", arguments.exe_sha256)
    write_json(results / "input-layout.json", input_layout)
    report["input_layout_sha256"] = digest(results / "input-layout.json")
    runtime = prepare_runtime(build, results, report)
    loan = ExecutableLoan(build, results, report)
    process = job = desktop_handle = gate = None
    desktop = "RBServices_" + uuid.uuid4().hex
    def stop_worker():
        if process is not None and process.poll() is None:
            process.terminate()
        if process is not None:
            process.wait(timeout=15)

    def restore_loan():
        if loan.attempted and loan.destination is not None:
            deadline = time.monotonic() + 10
            while True:
                try:
                    windows_backend().ensure_unused(loan.destination)
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
        loan.restore(process)

    try:
        windows_backend().ensure_unused(build / "rockboxui.exe")
        loan.move_to(runtime)
        require(loan.original_hash == arguments.exe_sha256, "EXE changed before the loan")
        desktop_handle = native.checked(native.user.CreateDesktopW(desktop, None, None, 0, native.access, None))
        gate = native.checked(native.kernel.CreateEventW(None, True, False, None))
        native.checked(native.kernel.SetHandleInformation(gate, 1, 1))
        startup = native.inherited_startup(desktop_handle)
        startup.lpAttributeList["handle_list"].append(int(gate))
        job = OwnedJob(native)
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", "--desktop", desktop,
                   "--gate", str(int(gate)), "--results", str(results), "--build-ready",
                   "--freeze", str(arguments.freeze), "--freeze-sha256", arguments.freeze_sha256,
                   "--exe-sha256", arguments.exe_sha256, "--timeout", str(arguments.timeout),
                   "--input-layout-sha256", report["input_layout_sha256"]]
        if keyclick_private:
            command.append('--keyclick-private')
        with (results / "worker.log").open("x", encoding="utf-8") as output:
            process = subprocess.Popen(command, cwd=results, startupinfo=startup, close_fds=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW, stdout=output, stderr=subprocess.STDOUT)
            report["worker_pid"] = process.pid
            job.assign(process)
            native.checked(native.kernel.SetEvent(gate))
            process.wait(timeout=arguments.overall_timeout)
        report["worker_exit_code"] = process.returncode
        report["worker"] = json.loads((results / "worker.json").read_text(encoding="utf-8"))
        report["long_power_stress"] = report["worker"].get("long_power_stress", report["long_power_stress"])
        if keyclick_private:
            require(not report['worker']['passed'] or report['worker'].get('keyclick_pcm_acceptance_complete') is True,
                    'Missing actual separate private physical-keyclick PCM receipt')
        else:
            require(process.returncode != 0 or not report["worker"]["passed"] or report["long_power_stress"]["passed"],
                    "Missing actual long-Power stress receipt")
        report['passed'] = process.returncode == 0 and report['worker']['passed']
        report['gui_acceptance_complete'] = report['passed'] and not keyclick_private
        report['keyclick_pcm_acceptance_complete'] = report['passed'] and keyclick_private
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["primary_traceback"] = traceback.format_exc()
    finally:
        for name, action in (
            ("owned_job_close", lambda: job.close() if job else None),
            ("worker_exit", stop_worker),
            ("exe_restore", restore_loan),
            ("gate_close", lambda: native.checked(native.kernel.CloseHandle(gate)) if gate else None),
            ("private_desktop_close", lambda: native.checked(native.user.CloseDesktop(desktop_handle)) if desktop_handle else None),
        ):
            try:
                action()
                report[name] = "complete"
            except BaseException as error:
                report["passed"] = report["gui_acceptance_complete"] = False
                report['keyclick_pcm_acceptance_complete'] = False
                report[name + "_error"] = str(error)
                report[name + "_traceback"] = traceback.format_exc()
        try:
            report["input_desktop_after"] = native.input()
            require(report["input_desktop_before"] == report["input_desktop_after"], "User input desktop changed")
            require(regular_files(build / "simdisk") == before, "Original build profile/assets changed")
            bound_checks(ROOT, freeze["sources"])
            bound_checks(build, freeze["build_files"])
            require(loan.record["restored"], "EXE was not restored")
        except BaseException as error:
            report["passed"] = report["gui_acceptance_complete"] = False
            report['keyclick_pcm_acceptance_complete'] = False
            report["final_integrity_error"] = str(error)
            report["final_integrity_traceback"] = traceback.format_exc()
        write_json(results / "report.json", report)
        print("Services GUI evidence: " + str(results), flush=True)
    return 0 if report["passed"] else 1


def readiness():
    missing = {}
    for language in ("english", "polski"):
        catalog = (ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8")
        identifiers = set(re.findall(r"^\s*id:\s*(LANG_\w+)", catalog, re.MULTILINE))
        missing[language] = sorted(set(REQUIRED_IDS) - identifiers)
    return {"scope": SCOPE, "expected_version": EXPECTED_VERSION, "gui_ready": False, "simulator_launched": False,
            "reason": "Parent build-ready plus newly frozen source/build/EXE hashes are still required",
            "required_sources": list(SOURCE_PATHS), "required_build_metadata": list(METADATA_FILES),
            "required_compiled_ids": REQUIRED_IDS, "missing_source_ids": missing,
            "required_voice_only_ids": VOICE_ONLY_IDS,
            "mapping_contract": mapping_contract(), "source_layout": source_layout(),
            "context_controls": {"button_root_rows": BUTTON_ROOT_ROWS, "interface_rows": BUTTON_ROWS,
                                 "playback_rows": PLAYBACK_BUTTON_ROWS, "touch_rows": TOUCH_ROWS,
                                 "gesture_profile_roots": BUTTON_ROOT_ROWS[:2],
                                 "gesture_profile_rows": GESTURE_ROWS + ("LANG_RESET",),
                                 "screen_settings_rows": ACCESSIBILITY_DISPLAY_ROWS,
                                 "system_touch_rows": SYSTEM_TOUCH_ROWS,
                                 "touch_wake_rows": TOUCH_WAKE_ROWS, "touch_wake_choices": TOUCH_WAKE_CHOICES,
                                 "guide_context_rows": GUIDE_CONTEXT_ROWS, "guide_rows": GUIDE_ROWS,
                                 "brightness_values": [100, 50, 1, 50, 100],
                                 "backlight_values": [-1, 0, 1, 15, 1, 0],
                                 "music_status_pcm_count": 4,
                                 "legacy_read_only_sessions": [language + "-missing-voice" for language in LANGUAGES],
                                 "pitch_effect": "GUI selection previews only; actual beep frequency remains a separate compiled/PCM requirement",
                                 "bluetooth_root_rows": BLUETOOTH_ROOT_ROWS,
                                 "bluetooth_preference_rows": BLUETOOTH_PREFERENCE_ROWS,
                                 "bluetooth_choices": BLUETOOTH_CHOICES,
                                 "bluetooth_layout_actions": bluetooth_layout_action_count(),
                                 "bluetooth_retry_role_gate": "Parent must tag only numeric retry choices LIST_POSITION_SLIDER before actual GUI; other enums retain interface indices",
                                 "bluetooth_busy": "Not covered by unavailable simulator; native controller and physical retest required"},
            "input_acknowledgement": {"button_masks": input_button_contract(), "symbol": "lastbtn",
                                      "bytes": 4, "minimum_seconds": 0.08, "maximum_seconds": PRESS_MAX_DOWN,
                                      "nm_before_loan": True, "read_only_owned_memory": True},
            "copy_plan": {"directories": RESOURCE_DIRECTORIES, "files": RESOURCE_FILES,
                          "root_files": ["*.dll", "UI256.bmp"], "excluded": ["EXE copies", "user profiles", "*.voice"],
                          "dll_policy": "Zero DLLs is valid for static SDL; every actual DLL asset must be frozen and copy-verified"},
            "with_music": True,
            "long_power_stress": {"session": "polski-services", "style": "long-hold-until-exit", "max_hold_seconds": 12,
                                  "others": "Normal bounded cue-release; cleanup after an earlier failure never starts stress"},
            "audio_trace": {"required_source_sha256": TRACE_SOURCES,
                            "required_exe_features": [feature.decode("ascii").rstrip("\0") for feature in TRACE_FEATURES],
                            "observation": "Separate generated audiodebug.raw retained per session; no user data copied",
                            "master": "Exclusive audio.raw read after shutdown; all offline acceptance assertions retained"},
            "sessions": [language + "-" + scenario for language in LANGUAGES for scenario in
                         ("services", "missing-voice", "layout-connectivity", "music")],
            "music": "Two PL/EN sessions with shared generated 997 Hz WAV and measured attenuation/recovery; no music result yet",
            "limitations": LIMITATIONS}


class HarnessTests(unittest.TestCase):
    def test_slider_default_requires_indices_for_choices_and_none_for_numeric_ranges(self):
        for connector in ("of", "z"):
            labels = {"VOICE_OF": connector}
            for name, enabled in (("100 percent", False), ("Yes", True), ("Polish", True), ("file.txt", True)):
                suffix = " 2 " + connector + " 8" if enabled else ""
                text = "TTS: " + name + suffix + "\nTTS utterance: " + name + suffix + "\n"
                require_position_presence(text, labels, enabled)
                for prefix in ("TTS", "TTS utterance"):
                    changed = text.replace(prefix + ": " + name + suffix,
                        prefix + ": " + name + ("" if enabled else " 2 " + connector + " 8"))
                    with self.subTest(connector=connector, name=name, prefix=prefix), self.assertRaises(AssertionError):
                        require_position_presence(changed, labels, enabled)

    def test_announcement_preferences_use_real_shared_mode_and_dynamic_fields(self):
        settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        menu = (ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
        for field in ("tts_announce_position", "tts_announce_dynamic"):
            with self.subTest(field=field):
                self.assertRegex(settings, r"\b" + ("int" if field == "tts_announce_position" else "bool") +
                                 r"\s+" + field + r"\s*;")
                self.assertRegex(menu, r"MENUITEM_SETTING\(" + field + r"_item,\s*&global_settings\." + field + r",\s*NULL\)")
        self.assertEqual(len(TALKBOX_BASELINE), 11)
        self.assertEqual(TALKBOX_BASELINE[-2:], ("tts_announce_position_item", "tts_announce_dynamic_item"))
        self.assertEqual(TALKBOX_ROWS[-2:], ("LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TALKBOX_ANNOUNCE_DYNAMIC"))
        self.assertIn("apps/plugin.h", SOURCE_PATHS)

    def test_announcement_toggles_require_effective_position_off_and_restored_suffix(self):
        for connector in ("of", "z"):
            for failure in (None, "position-still-on", "position-not-restored", "dynamic-silences-position"):
                probe = mock.Mock()
                probe.labels = {identifier: identifier for identifier in REQUIRED_IDS + VOICE_ONLY_IDS}
                probe.labels["VOICE_OF"] = connector
                probe.report = {}
                def row(name, key="Down", expected=()):
                    parts = expected
                    if name.startswith("Confirm "):
                        identifier = expected[0]
                        enabled = name not in ("Confirm disabled LANG_TALKBOX_ANNOUNCE_POSITION",
                                               "Confirm files-only LANG_TALKBOX_ANNOUNCE_POSITION")
                        if failure == "position-still-on" and not enabled:
                            enabled = True
                        if failure == "position-not-restored" and name == "Confirm enabled LANG_TALKBOX_ANNOUNCE_POSITION":
                            enabled = False
                        if failure == "dynamic-silences-position" and identifier == TALKBOX_ROWS[-1]:
                            enabled = False
                        if enabled:
                            parts += (str(TALKBOX_ROWS.index(identifier) + 1), connector, "11")
                    return "".join("TTS: " + part + "\n" for part in parts) + "TTS utterance: " + " ".join(parts) + "\n"
                probe.row.side_effect = row
                with self.subTest(connector=connector, failure=failure):
                    if failure:
                        with self.assertRaisesRegex(AssertionError, "list position suffix"):
                            browse_announcement_settings(probe)
                        self.assertNotIn("announcement_settings", probe.report)
                    else:
                        browse_announcement_settings(probe)
                        self.assertTrue(probe.report["announcement_settings"]["passed"])
                        self.assertTrue(probe.report["announcement_settings"]["restored"])
                        self.assertEqual(probe.enter.call_args_list, [
                            mock.call(TALKBOX_ROWS[-2], (identifier,)) for identifier in (
                                "LANG_TALKBOX_POSITION_EXCEPT_SLIDERS", "LANG_OFF", "LANG_TALKBOX_POSITION_FILES",
                                "LANG_TALKBOX_POSITION_INTERFACE", "LANG_TALKBOX_POSITION_EVERYWHERE")] + [
                            mock.call(TALKBOX_ROWS[-1], ("LANG_SET_BOOL_YES",)),
                            mock.call(TALKBOX_ROWS[-1], ("LANG_SET_BOOL_NO",))])

    def test_numeric_and_special_values_keep_exact_assertions_with_position_suffixes(self):
        for connector in ("of", "z"):
            for value in ("-4", "1 second", "15 seconds", "100 percent", "Never", "Always"):
                parts = (value, "3", connector, "201")
                valid = "".join("TTS: " + part + "\n" for part in parts) + "TTS utterance: " + " ".join(parts) + "\n"
                if value in ("Never", "Always"):
                    validate = lambda text: require_setting_label(text, value, connector)
                else:
                    validate = lambda text: require_numeric_speech(text, int(value.split()[0]), connector)
                with self.subTest(connector=connector, value=value):
                    validate(valid)
                    for invalid in (valid.replace(" 201", " 2"), valid.replace(value, "wrong value"),
                                    valid + "TTS: 999\nTTS utterance: 999\n"):
                        with self.assertRaises(AssertionError):
                            validate(invalid)

    def test_position_suffix_preserves_exact_label_number_connector_and_total_in_both_traces(self):
        for language, connector in (("english", "of"), ("polski", "z")):
            labels = dict(VOICE_OF=connector)
            for position, label in enumerate(TALKBOX_ROWS, 1):
                parts = (label, str(position), connector, "11")
                valid = "".join("TTS: " + part + "\n" for part in parts)
                valid += "TTS utterance: " + " ".join(parts) + "\n"
                with self.subTest(language=language, position=position):
                    require_list_position(valid, label, labels, position, 11)
                    for changed in (valid.replace(" 11", " 9"), valid.replace(connector, "wrong connector"),
                                    valid + "TTS: On\nTTS utterance: On\n",
                                    valid.replace("TTS: " + str(position) + "\n", ""),
                                    valid.replace("TTS utterance:", "ignored:")):
                        with self.assertRaises(AssertionError):
                            require_list_position(changed, label, labels, position, 11)
                    absent = f"TTS: {label}\nTTS utterance: {label}\n"
                    require_list_position(absent, label, labels, position, 11, enabled=False)
                    with self.assertRaises(AssertionError):
                        require_list_position(absent, label, labels, position, 11)
                    with self.assertRaises(AssertionError):
                        require_list_position(valid, label, labels, position, 11, enabled=False)

    def test_rapid_wrap_requires_new_final_position_without_accepting_setting_values(self):
        for connector in ("of", "z"):
            labels = {identifier: identifier for identifier in TALKBOX_ROWS}
            labels["VOICE_OF"] = connector
            for key, clicks in RAPID_WRAP_CASES:
                plan = rapid_wrap_plan(key, clicks)
                requested = [plan["wrapped_row"]] + ([plan["final_row"]] if clicks == 3 else [])
                position = TALKBOX_ROWS.index(plan["final_row"]) + 1
                text = "".join("TTS: " + identifier + "\n" for identifier in requested)
                text += f"TTS: {position}\nTTS: {connector}\nTTS: 11\n"
                text += f"TTS utterance: {plan['final_row']} {position} {connector} 11\n"
                with self.subTest(key=key, clicks=clicks, connector=connector):
                    result = rapid_wrap_speech(text, labels, key, clicks)
                    self.assertEqual(result["request_rows"], requested)
                    self.assertEqual(result["synthesized_rows"], [plan["final_row"]])
                    for invalid in (text.replace(f" {position} {connector} 11", ""),
                                    text.replace(" 11", " 9"),
                                    text + "TTS: On\nTTS utterance: On\n",
                                    text.replace(f"TTS: {position}\n", "TTS: 0\n")):
                        with self.assertRaises(AssertionError):
                            rapid_wrap_speech(invalid, labels, key, clicks)

    def test_percent_suffix_cannot_substitute_for_the_percent_value_or_unit(self):
        for unit, connector in (("percent", "of"), ("procent", "z")):
            for value in (50, 51, 100, 101):
                valid = f"TTS: {value}\nTTS: {unit}\nTTS: 50\nTTS: {connector}\nTTS: 201\n"
                valid += f"TTS utterance: {value} {unit} 50 {connector} 201\n"
                require_percent_speech(valid, value, unit, connector)
                for invalid in (valid.replace(f"{value} {unit}", f"150 {unit}"),
                                valid.replace(f"TTS: {value}\n", ""), valid.replace(unit, "hertz"),
                                valid.replace(f"50 {connector} 201", f"0 {connector} 201"),
                                valid + "TTS: On\nTTS utterance: On\n"):
                    with self.subTest(value=value, invalid=invalid), self.assertRaises(AssertionError):
                        require_percent_speech(invalid, value, unit, connector)

    def test_percent_speech_requires_exact_number_and_unit_in_both_traces(self):
        for unit in ("percent", "procent"):
            valid = f"TTS: 50\nTTS: {unit}\nTTS utterance: 50 {unit}\n"
            require_percent_speech(valid, 50, unit)
            for invalid in (
                f"TTS: 50\nTTS utterance: 50 {unit}\n",
                f"TTS: 50\nTTS: {unit}\nTTS utterance: 50\n",
                valid.replace("50", "150"),
                valid.replace(unit, "hertz"),
                valid + "TTS: Rockbox\nTTS utterance: Rockbox\n",
            ):
                with self.subTest(unit=unit, invalid=invalid), self.assertRaises(AssertionError):
                    require_percent_speech(invalid, 50, unit)

    def test_percent_selectors_restore_defaults_and_cancel_without_silencing_speech(self):
        probe = mock.Mock()
        identifiers = ("LANG_TTS_PITCH", "LANG_TTS_VOLUME", "LANG_TTS_RANGE")
        probe.labels = {identifier: identifier for identifier in identifiers}
        probe.labels["VOICE_PERCENT"] = "percent"
        probe.report = {}
        spoken = lambda values: "".join("TTS: " + value + "\n" for value in values) + "TTS utterance: " + " ".join(values) + "\n"
        probe.enter.side_effect = lambda identifier, expected: spoken(expected)
        probe.row.side_effect = lambda name, key, expected: spoken(expected)
        browse_synthesis_percent_settings(probe)
        expected_rows = [dict(identifier=identifier, default=default, preview=default + 1, restored=True)
                         for identifier, default in zip(identifiers, (50, 100, 50))]
        self.assertEqual(probe.report["percent_units"]["rows"], expected_rows)
        self.assertTrue(probe.report["percent_units"]["passed"])
        self.assertTrue(probe.report["percent_units"]["restored"])
        self.assertEqual(probe.enter.call_args_list, [mock.call(identifier, (str(default), "percent"))
                         for identifier, default in zip(identifiers, (50, 100, 50))])
        self.assertEqual(probe.row.call_args_list, [call for identifier, default in zip(identifiers, (50, 100, 50))
                         for call in (mock.call("Preview percent " + identifier, "Up", (str(default + 1), "percent")),
                                      mock.call("Restore percent " + identifier, "Down", (str(default), "percent")),
                                      mock.call("Cancel unchanged percent " + identifier, "Left", (identifier,)))])

    def test_percent_selector_missing_unit_cannot_publish_a_success_receipt(self):
        probe = mock.Mock()
        probe.labels = {"VOICE_PERCENT": "percent"}
        probe.report = {}
        probe.enter.return_value = "TTS: 50\nTTS utterance: 50\n"
        with self.assertRaises(AssertionError):
            browse_synthesis_percent_settings(probe)
        probe.row.assert_not_called()
        self.assertNotIn("percent_units", probe.report)

    def menu_seek_fixture(self, label, observed):
        probe = ServicesProbe.__new__(ServicesProbe)
        probe.labels = {"target": label}
        probe.latest = observed
        probe.row = mock.Mock()
        return probe

    def test_menu_seek_rejects_longer_labels_containing_the_target(self):
        for label, other in (("Ekran", "Ekran bieżącego odtwarzania"),
                             ("Settings", "eSpeak settings")):
            with self.subTest(label=label):
                probe = self.menu_seek_fixture(label, f"TTS: {other}\nTTS utterance: {other}\n")
                def next_row(*arguments):
                    probe.latest = f"TTS: {label}\nTTS utterance: {label}\n"
                probe.row.side_effect = next_row
                probe.seek("target")
                probe.row.assert_called_once_with("Seek target 1")

    def test_menu_seek_accepts_the_exact_label_with_a_separate_value(self):
        probe = self.menu_seek_fixture("Wi-Fi", "TTS: Wi-Fi\nTTS: Off\nTTS utterance: Wi-Fi Off\n")
        probe.seek("target")
        probe.row.assert_not_called()

    def test_menu_seek_does_not_join_adjacent_segments_into_a_label(self):
        probe = self.menu_seek_fixture("Screen settings", "TTS: Screen\nTTS: settings\nTTS utterance: Screen settings\n")
        with self.assertRaisesRegex(AssertionError, "Spoken row not found: target"):
            probe.seek("target", maximum=2)
        self.assertEqual(probe.row.call_count, 2)

    def test_menu_seek_keeps_its_bound_when_only_a_partial_label_exists(self):
        probe = self.menu_seek_fixture("Display", "TTS: Display mode\nTTS utterance: Display mode\n")
        with self.assertRaisesRegex(AssertionError, "Spoken row not found: target"):
            probe.seek("target", maximum=3)
        self.assertEqual(probe.row.call_count, 3)

    def test_menu_seek_still_requires_the_synthesized_label_to_be_uttered(self):
        probe = self.menu_seek_fixture("Display", "TTS: Display\nTTS utterance: Other\n")
        with self.assertRaisesRegex(AssertionError, "Spoken row not found: target"):
            probe.seek("target", maximum=2)
        self.assertEqual(probe.row.call_count, 2)

    def test_each_session_keeps_an_explicit_finite_action_budget(self):
        self.assertEqual(bluetooth_layout_action_count(), 43)
        for timeout in (10, 25, 60):
            self.assertAlmostEqual(session_action_budget("layout-connectivity", timeout),
                                   3600 + 43 * (2 * timeout + 0.28 + 0.4))
        for scenario in ("services", "missing-voice", "music"):
            self.assertEqual(session_action_budget(scenario), 600)
        with self.assertRaisesRegex(AssertionError, "Unknown GUI scenario"):
            session_action_budget("unknown")
        for timeout in (9, 61, float("inf"), float("nan")):
            with self.assertRaisesRegex(AssertionError, "Invalid bounded action timeout"):
                session_action_budget("layout-connectivity", timeout)

    def test_expanded_layout_budget_still_rejects_expiration_without_input(self):
        for scenario in ("services", "layout-connectivity"):
            budget = session_action_budget(scenario)
            for elapsed, accepted in ((budget - 0.01, True), (budget, False), (budget + 1, False)):
                with self.subTest(scenario=scenario, elapsed=elapsed):
                    probe = ServicesProbe.__new__(ServicesProbe)
                    probe.native = mock.Mock(spec=["assert_private"])
                    probe.desktop = "private-test-desktop"
                    probe.process = mock.Mock()
                    probe.process.poll.return_value = None
                    probe.started = 100
                    probe.report = {"action_budget_seconds": budget}
                    with mock.patch(__name__ + ".time.perf_counter", return_value=100 + elapsed):
                        if accepted:
                            probe.alive()
                        else:
                            with self.assertRaisesRegex(AssertionError, "bounded action budget"):
                                probe.alive()
                    probe.native.assert_private.assert_called_once_with(probe.desktop)

    def test_full_workflow_timeout_is_finite_without_relaxing_action_timeout(self):
        for overall in (9600, 10800):
            with self.subTest(overall=overall), mock.patch(__name__ + '.readiness', return_value={}), \
                    mock.patch('sys.stdout', io.StringIO()):
                self.assertEqual(main(['--readiness', '--timeout', '25', '--overall-timeout', str(overall)]), 0)
        for overall in ('59', '10801', 'inf', 'nan'):
            with self.subTest(overall=overall), self.assertRaisesRegex(AssertionError, 'Invalid bounded timeout'):
                main(['--readiness', '--overall-timeout', overall])
        for timeout in ('9', '61', 'inf', 'nan'):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(AssertionError, 'Invalid bounded timeout'):
                main(['--readiness', '--timeout', timeout, '--overall-timeout', '9600'])

    def chord_fixture(self, delay=0, missing=None, release_error=False, ownership_error=False):
        probe = object.__new__(ServicesProbe)
        probe.process, probe.native, probe.memory = mock.Mock(), mock.Mock(), mock.Mock()
        probe.process.pid, probe.process.poll.return_value = 123, None
        probe.window, probe.desktop = 456, "Private"
        probe.alive = mock.Mock()
        masks = input_button_contract()
        probe.report = {"raw_input": [], "input_layout": {
            "button_masks": masks, "symbols": {"lastbtn": {"rva": 64, "size": 4}}}}
        clock, state = [0.0], {"mask": 0, "sampled": 0, "ready": 0, "edge": 0}
        backend = mock.Mock()
        def send(pid, window, key, pressed):
            self.assertEqual((pid, window), (123, 456))
            if release_error and key == "Left" and not pressed:
                raise OSError("Chord release transport failed")
            state["mask"] = state["mask"] | masks[key] if pressed else state["mask"] & ~masks[key]
            state["ready"] = clock[0] + delay
            state["edge"] += 1
        backend.key_event.side_effect = send
        def read_image(rva, size):
            self.assertEqual((rva, size), (64, 4))
            if clock[0] >= state["ready"]:
                state["sampled"] = state["mask"]
            value = (8, 0, 1, 9, 1)[missing] if missing is not None and state["edge"] == missing else state["sampled"]
            return value.to_bytes(4, "little")
        probe.memory.read_image.side_effect = read_image
        if ownership_error:
            probe.native.owns.side_effect = AssertionError("Wrong owned HWND")
        def advance(seconds):
            clock[0] += seconds
        with mock.patch("test_tts_simulator.windows_backend", return_value=backend), \
             mock.patch.object(time, "perf_counter", side_effect=lambda: clock[0]), \
             mock.patch.object(time, "sleep", side_effect=advance):
            try:
                probe.chord("Insert", "Left")
            finally:
                self.last_chord_probe, self.last_chord_backend, self.last_chord_state = probe, backend, state
        return probe

    def test_chord_samples_modifier_before_combined_and_reverse_release(self):
        for delay in (0, 0.01):
            with self.subTest(delay=delay):
                probe = self.chord_fixture(delay=delay)
                record = probe.report["chord_acknowledgements"][0]
                self.assertTrue(record["passed"])
                self.assertLess(record["sampled_release_seconds"], PRESS_MAX_DOWN)
                self.assertGreaterEqual(record["sampled_release_seconds"], 0.1)
                phases = ("before-chord", "modifier-down", "combined-down", "key-released", "all-released")
                self.assertEqual([next(sample["lastbtn"] for sample in reversed(record["samples"])
                                       if sample["phase"] == phase) for phase in phases], [0, 1, 9, 1, 0])
                self.assertEqual([(event["key"], event["pressed"]) for event in probe.report["raw_input"]],
                                 [("Insert", True), ("Left", True), ("Left", False), ("Insert", False)])
                self.assertEqual((record["pid"], record["hwnd"], record["desktop"]), (123, 456, "Private"))
                self.assertEqual(self.last_chord_state["mask"], 0)
                probe.native.owns.assert_called()

    def test_each_chord_ack_timeout_releases_all_pressed_keys_without_retry(self):
        phases = ("before-chord", "modifier-down", "combined-down", "key-released", "all-released")
        for missing, phase in enumerate(phases):
            with self.subTest(phase=phase), self.assertRaisesRegex(AssertionError, "acknowledgement: " + phase):
                self.chord_fixture(missing=missing)
            self.assertEqual(self.last_chord_state["mask"], 0)
            record = self.last_chord_probe.report["chord_acknowledgements"][0]
            self.assertFalse(record["passed"])
            self.assertFalse(record["cleanup_errors"])
            downs = [event["key"] for event in self.last_chord_probe.report["raw_input"] if event["pressed"]]
            self.assertEqual(len(downs), len(set(downs)))

    def test_chord_rejects_insufficient_hold_budget_before_first_repeat(self):
        with self.assertRaisesRegex(AssertionError, "Insufficient chord time"):
            self.chord_fixture(delay=0.1)
        self.assertEqual(self.last_chord_state["mask"], 0)
        self.assertFalse(self.last_chord_probe.report["chord_acknowledgements"][0]["passed"])

    def test_chord_cleanup_attempts_both_releases_and_preserves_primary(self):
        with self.assertRaisesRegex(AssertionError, "acknowledgement: combined-down"):
            self.chord_fixture(missing=2, release_error=True)
        record = self.last_chord_probe.report["chord_acknowledgements"][0]
        self.assertIn("combined-down", record["error"])
        self.assertTrue(any("Chord release transport failed" in error for error in record["cleanup_errors"]))
        self.assertEqual([(event["key"], event["pressed"]) for event in self.last_chord_probe.report["raw_input"]][-2:],
                         [("Left", False), ("Insert", False)])

    def test_chord_keeps_owned_hwnd_guard_before_input_and_memory(self):
        with self.assertRaisesRegex(AssertionError, "Wrong owned HWND"):
            self.chord_fixture(ownership_error=True)
        self.last_chord_backend.key_event.assert_not_called()
        self.last_chord_probe.memory.read_image.assert_not_called()
        self.assertEqual(self.last_chord_probe.report["raw_input"], [])

    def test_music_home_uses_chord_instead_of_raw_simultaneous_keys(self):
        probe = mock.Mock(latest="TTS: 001 Service music 1 of 1\nTTS utterance: 001 Service music 1 of 1\n")
        probe.labels = {"VOICE_OF": "of"}
        probe.report = {}
        probe.status_labels = {"LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF": "off",
                               "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON": "on"}
        def capture(name, action=None, *arguments, **keywords):
            if action:
                action()
            return "TTS audio playback: 1\n"
        probe.capture.side_effect = capture
        music_case(probe)
        probe.chord.assert_called_once_with("Insert", "Left")
        probe.key.assert_not_called()

    def press_fixture(self, delay=0, initial=0, missing_down=False, stuck_release=False, release_delay=0,
                      read_error=False, release_error=False, overshoot=False, clicks=1, key_name="Left",
                      rapid=False, gap_delay=0, clock_read=lambda elapsed: elapsed, clock_origin=0.0):
        probe = object.__new__(ServicesProbe)
        probe.process, probe.native, probe.memory = mock.Mock(), mock.Mock(), mock.Mock()
        probe.process.pid, probe.process.poll.return_value = 123, None
        probe.window, probe.desktop = 456, "Private"
        probe.alive = mock.Mock()
        probe.report = {"raw_input": [], "input_layout": {
            "button_masks": input_button_contract(), "symbols": {"lastbtn": {"rva": 64, "size": 4}}}}
        mask = input_button_contract()[key_name]
        clock, state = [clock_origin], {"pressed": None, "released": None, "read_error": read_error}
        def key(name, pressed):
            probe.report["raw_input"].append({"key": name, "pressed": pressed, "monotonic": time.perf_counter()})
            state["pressed" if pressed else "released"] = clock[0]
            if pressed:
                state["released"] = None
            elif release_error:
                raise OSError("Release transport failed")
        probe.key = key
        def read_image(rva, size):
            self.assertEqual((rva, size), (64, 4))
            if state["pressed"] is None:
                value = initial
            elif state["released"] is not None:
                value = mask if stuck_release or clock[0] - state["released"] < release_delay else 0
            else:
                if state["read_error"]:
                    state["read_error"] = False
                    raise OSError("Owned memory read failed")
                if overshoot:
                    clock[0] += 0.29
                value = 0 if missing_down or clock[0] - state["pressed"] < delay else mask
            return value.to_bytes(4, "little")
        probe.memory.read_image.side_effect = read_image
        def advance(seconds):
            clock[0] += seconds
            if seconds == 0.08 and state["released"] is not None:
                clock[0] += gap_delay
        with mock.patch.object(time, "perf_counter", side_effect=lambda: clock_read(clock[0])), \
             mock.patch.object(time, "sleep", side_effect=advance):
            try:
                if rapid:
                    probe.rapid_navigation(key_name, clicks)
                else:
                    probe.press(key_name, clicks=clicks)
            finally:
                self.last_press_probe = probe
        return probe

    def test_press_waits_for_sampled_down_and_zero_with_minimum_hold(self):
        for delay in (0, 0.16):
            with self.subTest(delay=delay):
                probe = self.press_fixture(delay=delay)
                record = probe.report["press_acknowledgements"][0]
                self.assertTrue(record["passed"])
                self.assertTrue(record["release_sent"])
                self.assertGreaterEqual(record["hold_seconds"], max(0.08, delay))
                self.assertLess(record["hold_seconds"], PRESS_MAX_DOWN)
                self.assertEqual([sample["phase"] for sample in record["samples"] if sample["phase"] != "down"],
                                 ["before-down", "released"])
                self.assertTrue(any(sample["phase"] == "down" and sample["lastbtn"] == 8
                                    for sample in record["samples"]))
                probe.native.owns.assert_called()

    def test_missing_down_ack_fails_without_retry_and_always_posts_release(self):
        with self.assertRaisesRegex(AssertionError, "acknowledgement: down"):
            self.press_fixture(missing_down=True, clicks=2)
        inputs = self.last_press_probe.report["raw_input"]
        self.assertEqual([item["pressed"] for item in inputs], [True, False])
        record = self.last_press_probe.report["press_acknowledgements"][0]
        self.assertFalse(record["passed"])
        self.assertTrue(record["release_sent"])
        self.assertLess(record["hold_seconds"], PRESS_MAX_DOWN)

    def test_stale_initial_state_never_posts_another_press(self):
        with self.assertRaisesRegex(AssertionError, "acknowledgement: before-down"):
            self.press_fixture(initial=8)
        self.assertEqual(self.last_press_probe.report["raw_input"], [])

    def test_missing_release_ack_prevents_following_click(self):
        with self.assertRaisesRegex(AssertionError, "acknowledgement: released"):
            self.press_fixture(stuck_release=True, clicks=2)
        self.assertEqual([item["pressed"] for item in self.last_press_probe.report["raw_input"]], [True, False])

    def test_memory_read_failure_releases_and_keeps_primary_error(self):
        with self.assertRaisesRegex(OSError, "Owned memory read failed"):
            self.press_fixture(read_error=True)
        record = self.last_press_probe.report["press_acknowledgements"][0]
        self.assertTrue(record["release_sent"])
        self.assertIn("Owned memory read failed", record["error"])
        with self.assertRaisesRegex(AssertionError, "acknowledgement: down"):
            self.press_fixture(missing_down=True, release_error=True)
        record = self.last_press_probe.report["press_acknowledgements"][0]
        self.assertIn("Release transport failed", record["release_error"])

    def test_scheduling_overshoot_is_released_and_rejected(self):
        with self.assertRaisesRegex(AssertionError, "acknowledgement: released"):
            self.press_fixture(overshoot=True)
        self.assertEqual([item["pressed"] for item in self.last_press_probe.report["raw_input"]], [True, False])

    def test_sampled_release_must_arrive_inside_same_subrepeat_bound(self):
        probe = self.press_fixture(release_delay=0.03)
        record = probe.report["press_acknowledgements"][0]
        self.assertGreater(record["sampled_release_seconds"], record["hold_seconds"])
        self.assertLess(record["sampled_release_seconds"], PRESS_MAX_DOWN)
        with self.assertRaisesRegex(AssertionError, "acknowledgement: released"):
            self.press_fixture(release_delay=0.24, clicks=2)
        self.assertEqual([item["pressed"] for item in self.last_press_probe.report["raw_input"]], [True, False])

    def test_intentional_double_click_has_two_complete_sampled_releases(self):
        probe = self.press_fixture(clicks=2)
        records = probe.report["press_acknowledgements"]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record["passed"] and record["samples"][-1]["phase"] == "released" for record in records))
        inputs = probe.report["raw_input"]
        self.assertEqual([item["pressed"] for item in inputs], [True, False, True, False])
        self.assertLess(inputs[2]["monotonic"] - inputs[1]["monotonic"], 0.3)

    def test_only_explicit_triple_power_can_use_three_acknowledged_short_presses(self):
        probe = self.press_fixture(clicks=3, key_name="Insert")
        self.assertEqual(len(probe.report["press_acknowledgements"]), 3)
        self.assertEqual([item["pressed"] for item in probe.report["raw_input"]], [True, False] * 3)
        self.assertTrue(all(record["passed"] for record in probe.report["press_acknowledgements"]))
        for key in ("Left", "Right", "Up", "Down"):
            with self.subTest(key=key), self.assertRaisesRegex(AssertionError, "explicit triple-Power"):
                self.press_fixture(clicks=3, key_name=key)
            self.assertEqual(self.last_press_probe.report["raw_input"], [])

    def test_physical_masks_come_from_r1_header_and_sdl_map_not_arrow_aliases(self):
        self.assertEqual(input_button_contract(), {"Left": 8, "Right": 4, "Up": 16, "Down": 32, "Insert": 1})
        original = Path.read_text
        def changed(path, *arguments, **keywords):
            text = original(path, *arguments, **keywords)
            return text.replace("return BUTTON_PLAY;", "return BUTTON_LEFT;") if path.name == "hiby-r1.c" else text
        with mock.patch.object(Path, "read_text", autospec=True, side_effect=changed), \
             self.assertRaisesRegex(AssertionError, "mapping changed: Left"):
            input_button_contract()

    def test_input_symbol_requires_unique_aligned_four_byte_writable_bss(self):
        base = 0x140000000
        layout = {"preferred_base": base, "image_size": 0x3000,
                  "sections": [{"name": ".bss", "rva": 0x1000, "size": 0x1000, "flags": 0xc0000000}]}
        valid = f"{base + 0x1000:016x} b lastbtn\n"
        with mock.patch("test_tts_recorder_gui.pe_layout", return_value=layout), \
             mock.patch(__name__ + ".digest", return_value="a" * 64):
            result = input_symbol_layout(Path("unlaunched.exe"), valid)
            self.assertEqual(result["symbols"]["lastbtn"]["size"], 4)
            for text in ("", valid + valid, valid.replace(" b ", " T "), valid.replace(" b ", " d "),
                         f"{base + 0x1001:016x} b lastbtn\n", f"{base + 0x1ffc + 4:016x} b lastbtn\n"):
                with self.subTest(text=text), self.assertRaises(AssertionError):
                    input_symbol_layout(Path("unlaunched.exe"), text)
            layout["sections"][0]["flags"] = 0x40000000
            with self.assertRaises(AssertionError):
                input_symbol_layout(Path("unlaunched.exe"), valid)

    def test_input_symbol_preparation_rejects_hash_change_before_nm_or_loan(self):
        with mock.patch(__name__ + ".digest", return_value="b" * 64), \
             mock.patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(AssertionError, "EXE changed before"):
                prepare_input_layout(Path("unlaunched.exe"), "a" * 64)
            run.assert_not_called()

    def test_input_symbol_preparation_rejects_exe_change_during_nm(self):
        with mock.patch(__name__ + ".digest", side_effect=["a" * 64, "b" * 64]), \
             mock.patch.object(shutil, "which", return_value="nm"), \
             mock.patch.object(subprocess, "run", return_value=argparse.Namespace(stdout="unused")), \
             mock.patch(__name__ + ".input_symbol_layout", return_value={"sha256": "a" * 64}), \
             self.assertRaisesRegex(AssertionError, "EXE changed while"):
            prepare_input_layout(Path("unlaunched.exe"), "a" * 64)

    def settle_fixture(self, data, size_at, log_at=lambda elapsed: "", music=False, timeout=4,
                       trace_at=None, master_size_at=None, observation_begin=0, master_begin=0):
        clock = [0.0]
        probe = object.__new__(ServicesProbe)
        probe.timeout, probe.pcm, probe.music_expected = timeout, Path("exclusive-master.raw"), music
        probe.observation = Path("shared-observation.raw")
        probe.alive = mock.Mock()
        default_trace = "Audio debug format: rate=44100 format=32784 channels=2 frame_bytes=4\nAudio debug file open\n"
        def text():
            return (default_trace if trace_at is None else trace_at(clock[0])) + log_at(clock[0])
        probe.mark = lambda: len(text())
        probe.text = lambda marker=0: text()[marker:]
        def advance(seconds):
            clock[0] += seconds
        def size():
            return min(len(data), size_at(clock[0])) // 4 * 4
        def stat(path):
            count = size() if path == probe.observation else (
                master_size_at(clock[0]) if master_size_at is not None else size())
            return argparse.Namespace(st_size=count)
        def open_observation(path, mode):
            if path != probe.observation:
                raise PermissionError("Exclusive master cannot be read during live observation")
            self.assertEqual(mode, "rb")
            return io.BytesIO(data[:size()])
        with mock.patch.object(time, "perf_counter", side_effect=lambda: clock[0]), \
             mock.patch.object(time, "sleep", side_effect=advance), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(Path, "stat", autospec=True, side_effect=stat), \
             mock.patch.object(Path, "open", autospec=True, side_effect=open_observation):
            result = probe.settle(0, observation_begin, master_begin)
        return result, clock[0]

    def test_continuously_written_zero_pcm_can_settle(self):
        result, elapsed = self.settle_fixture(b"\0" * 3000000, lambda elapsed: int((elapsed + 0.1) * 655360))
        self.assertGreaterEqual(elapsed, 1.2)
        self.assertEqual(result["tail"]["peak"], 0)
        self.assertGreater(result["observation_end"], 65536)

    def test_closed_tap_without_zero_tail_can_settle_only_with_independent_master_progress(self):
        data = b"\1\0" * 16384
        trace = lambda elapsed: ("Audio debug format: rate=44100 format=32784 channels=2 frame_bytes=4\n"
                                 "Audio debug file open\n" + ("Audio debug file closed\n" if elapsed >= 0.3 else ""))
        result, elapsed = self.settle_fixture(data, lambda elapsed: len(data),
                                              lambda elapsed: "TTS utterance: Files\n", trace_at=trace,
                                              master_size_at=lambda elapsed: int((elapsed + 0.1) * 655360))
        self.assertEqual(result["quiet_basis"], "observed sink close/flush")
        self.assertEqual(result["observation_end"], len(data))
        self.assertGreater(result["master_end"], result["observation_end"])
        self.assertGreater(result["tail"]["nonzero_samples"], 128)
        with self.assertRaisesRegex(AssertionError, "did not settle"):
            self.settle_fixture(data, lambda elapsed: len(data), trace_at=trace,
                                master_size_at=lambda elapsed: 1000000)

    def test_arbitrary_open_tap_stall_is_not_a_close_receipt(self):
        with self.assertRaisesRegex(AssertionError, "did not settle"):
            self.settle_fixture(b"\0" * 65536, lambda elapsed: 65536,
                                master_size_at=lambda elapsed: int((elapsed + 0.1) * 655360))

    def test_observation_and_master_offsets_are_never_interchanged(self):
        data = b"\0" * 8192
        trace = lambda elapsed: ("Audio debug format: rate=44100 format=32784 channels=2 frame_bytes=4\n"
                                 "Audio debug file open\nAudio debug file closed\n")
        result, elapsed = self.settle_fixture(data, lambda elapsed: len(data), trace_at=trace,
                                              observation_begin=len(data), master_begin=9000000,
                                              master_size_at=lambda elapsed: 9000000 + int((elapsed + 0.1) * 655360))
        self.assertEqual(result["observation_start"], len(data))
        self.assertEqual(result["observation_end"], len(data))
        self.assertEqual(result["master_start"], 9000000)
        self.assertGreater(result["master_end"], 9000000)

    def test_observation_failures_or_unqualified_actual_formats_are_rejected(self):
        for reason in ("open", "write", "close"):
            with self.subTest(reason=reason), self.assertRaisesRegex(AssertionError, "tap failed"):
                observation_format(f"Audio debug file {reason} failed\n")
        for values in ((48000, 32784, 2, 4), (44100, 16, 2, 4), (44100, 32784, 1, 2)):
            with self.subTest(values=values), self.assertRaisesRegex(AssertionError, "Actual observation format"):
                observation_format("Audio debug format: rate=%d format=%d channels=%d frame_bytes=%d\n" % values)
        self.assertIsNone(observation_format("TTS utterance: Files\n"))
        with self.assertRaisesRegex(AssertionError, "did not settle"):
            self.settle_fixture(b"\0" * 3000000, lambda elapsed: int((elapsed + 0.1) * 655360),
                                trace_at=lambda elapsed: "Audio debug file open\n")

    def test_trace_sources_and_executable_features_are_explicitly_bound_before_launch(self):
        freeze = {"sources": dict(TRACE_SOURCES)}
        binary = b"|".join(TRACE_FEATURES)
        with mock.patch(__name__ + ".digest", side_effect=lambda path: TRACE_SOURCES[path.relative_to(ROOT).as_posix()]), \
             mock.patch.object(Path, "read_bytes", return_value=binary):
            self.assertEqual(validate_trace_features(freeze, Path("unlaunched.exe")), TRACE_SOURCES)
            for name in TRACE_SOURCES:
                self.assertEqual(SOURCE_PATHS.count(name), 1)
                changed = {"sources": dict(TRACE_SOURCES, **{name: "a" * 64})}
                with self.subTest(source=name), self.assertRaisesRegex(AssertionError, "source revision changed"):
                    validate_trace_features(changed, Path("unlaunched.exe"))
        for feature in TRACE_FEATURES:
            with self.subTest(feature=feature), \
                 mock.patch(__name__ + ".digest", side_effect=lambda path: TRACE_SOURCES[path.relative_to(ROOT).as_posix()]), \
                 mock.patch.object(Path, "read_bytes", return_value=binary.replace(feature, b"")), \
                 self.assertRaisesRegex(AssertionError, "lacks the qualified optional audio trace"):
                validate_trace_features(freeze, Path("unlaunched.exe"))

    def test_logged_speech_needs_real_activity_before_quiet_tail(self):
        data = b"\1\0" * 32768 + b"\0" * 3000000
        result, elapsed = self.settle_fixture(data, lambda elapsed: int((elapsed + 0.1) * 655360),
                                              lambda elapsed: "TTS utterance: Files\n")
        self.assertEqual(result["utterances"], ["Files"])
        self.assertEqual(result["tail"]["nonzero_samples"], 0)
        with self.assertRaisesRegex(AssertionError, "pending_speech=True"):
            self.settle_fixture(b"\0" * 3000000, lambda elapsed: int((elapsed + 0.1) * 655360),
                                lambda elapsed: "TTS utterance: Files\n")

    def test_continuing_waveform_never_settles(self):
        with self.assertRaisesRegex(AssertionError, "did not settle"):
            self.settle_fixture(b"\1\0" * 1500000, lambda elapsed: int((elapsed + 0.1) * 655360))

    def test_missing_or_stalled_pcm_progress_cannot_settle(self):
        for data in (b"", b"\0" * 65536, b"\0" * 4000000):
            with self.subTest(bytes=len(data)), self.assertRaisesRegex(AssertionError, "did not settle"):
                self.settle_fixture(data, lambda elapsed: len(data))

    def test_late_utterance_resets_quiet_and_requires_its_audio(self):
        data = b"\1\0" * 32768 + b"\0" * (12 * 65536) + b"\1\0" * 32768 + b"\0" * 3000000
        logs = lambda elapsed: "TTS utterance: First\n" + ("TTS utterance: Later\n" if elapsed >= 1.1 else "")
        result, elapsed = self.settle_fixture(data, lambda elapsed: int((elapsed + 0.1) * 655360), logs)
        self.assertGreaterEqual(elapsed, 2.5)
        self.assertEqual(result["utterances"], ["First", "Later"])
        with self.assertRaisesRegex(AssertionError, "pending_speech=True"):
            self.settle_fixture(b"\1\0" * 32768 + b"\0" * 3000000,
                                lambda elapsed: int((elapsed + 0.1) * 655360), logs)

    def test_music_quiet_tail_requires_clean_stable_997hz_in_both_channels(self):
        def waveform(extra=0, second_channel=True, changing=False):
            samples = array.array("h", (int((1200 if not changing or frame < 8192 else 600) *
                                            math.sin(2 * math.pi * 997 * frame / 44100) +
                                            extra * math.sin(2 * math.pi * 911 * frame / 44100))
                                        if channel == 0 or second_channel else 0
                                        for frame in range(16384) for channel in range(2)))
            if sys.byteorder != "little":
                samples.byteswap()
            return samples.tobytes()
        self.assertTrue(quiet_pcm_tail(waveform(), music=True))
        for data in (b"\0" * 65536, waveform(extra=300), waveform(second_channel=False), waveform(changing=True)):
            with self.subTest(sha256=hashlib.sha256(data).hexdigest()):
                self.assertFalse(quiet_pcm_tail(data, music=True))
        self.assertFalse(quiet_pcm_tail(b"\0" * 65532))
        with self.assertRaises(AssertionError):
            quiet_pcm_tail(b"\0" * 65535)

    def test_expected_music_cannot_settle_on_continuing_silence(self):
        with self.assertRaisesRegex(AssertionError, "did not settle"):
            self.settle_fixture(b"\0" * 3000000, lambda elapsed: int((elapsed + 0.1) * 655360), music=True)

    def test_continuing_clean_music_can_settle_with_real_pcm_progress(self):
        samples = array.array("h", (int(1200 * math.sin(2 * math.pi * 997 * frame / 44100))
                                    for frame in range(44100 * 4) for channel in range(2)))
        if sys.byteorder != "little":
            samples.byteswap()
        result, elapsed = self.settle_fixture(samples.tobytes(), lambda elapsed: int((elapsed + 0.1) * 176400),
                                              music=True)
        self.assertTrue(result["music_expected"])
        self.assertGreater(result["tail"]["nonzero_samples"], 128)

    def shutdown_fixture(self, exit_code=0, log="TTS: Shutting down\nTTS utterance: Shutting down\n", wait_error=None,
                         long_hold=False, exit_at=None, log_at=0.3):
        clock, keys = [0.0], []
        probe = object.__new__(ServicesProbe)
        probe.process = mock.Mock()
        probe.process.returncode = None
        def poll():
            if exit_at is not None and clock[0] >= exit_at:
                probe.process.returncode = exit_code
            return probe.process.returncode
        probe.process.poll.side_effect = poll
        def wait(timeout):
            if wait_error:
                raise wait_error
            probe.process.returncode = exit_code
        probe.process.wait.side_effect = wait
        probe.window, probe.desktop, probe.native = 456, "Private", mock.Mock()
        probe.report, probe.labels = {}, {"LANG_SHUTTINGDOWN": "Shutting down"}
        probe.text = lambda marker=0: log if clock[0] >= log_at else ""
        probe.mark = lambda: len(probe.text())
        probe.key = lambda key, pressed: keys.append((key, pressed, clock[0]))
        def advance(seconds):
            clock[0] += seconds
        with mock.patch.object(time, "perf_counter", side_effect=lambda: clock[0]), \
             mock.patch.object(time, "sleep", side_effect=advance):
            try:
                probe.close(long_hold=long_hold)
            finally:
                self.last_shutdown, self.last_shutdown_keys = probe.report["shutdown"], keys
                self.last_shutdown_probe = probe
        return probe.report["shutdown"], keys

    def test_long_power_shutdown_ignores_early_cue_until_owned_exit(self):
        report, keys = self.shutdown_fixture(long_hold=True, exit_at=1)
        self.assertTrue(report["passed"])
        self.assertTrue(report["observed"])
        self.assertEqual(report["style"], "long-hold-until-exit")
        self.assertEqual(report["max_hold_seconds"], 12)
        self.assertGreaterEqual(report["hold_seconds"], 1)
        self.assertEqual(report["hold_end"], "owned-process-exit")
        self.assertFalse(report["release_sent"])
        self.assertEqual([(key, pressed) for key, pressed, elapsed in keys], [("Insert", True)])

    def test_long_power_nonzero_exit_and_log_defects_still_fail(self):
        for code, log in ((7, "Writing system_status to disk\n"), (0, "queue_post ovf q=0x123\n")):
            with self.subTest(code=code), self.assertRaisesRegex(AssertionError, "Graceful owned shutdown failed"):
                self.shutdown_fixture(code, log, long_hold=True, exit_at=1)
            self.assertFalse(self.last_shutdown["passed"])
            self.assertEqual(self.last_shutdown["exit_code"], code)
            self.assertGreaterEqual(self.last_shutdown["hold_seconds"], 1)

    def test_long_power_timeout_releases_at_twelve_seconds_and_remains_failure(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.shutdown_fixture(long_hold=True, wait_error=subprocess.TimeoutExpired("owned simulator", 12))
        self.assertFalse(self.last_shutdown["passed"])
        self.assertTrue(self.last_shutdown["release_sent"])
        self.assertGreaterEqual(self.last_shutdown["hold_seconds"], 12)
        self.assertLess(self.last_shutdown["hold_seconds"], 12.1)
        self.assertEqual(self.last_shutdown_keys[-1][1], False)
        self.assertGreaterEqual(self.last_shutdown_keys[-1][2], 12)

    def stress_receipt_fixture(self):
        sessions = [{"language": language, "scenario": scenario, "passed": True,
                     "shutdown": {"style": "bounded-cue-release"}}
                    for language in LANGUAGES for scenario in ("services", "missing-voice", "layout-connectivity", "music")]
        session = sessions[0]
        session.update(pid=123, hwnd=456, desktop="RBServices_" + "a" * 32,
                       raw_input=[{"key": "Insert", "pressed": True, "pid": 123, "hwnd": 456,
                                   "desktop": "RBServices_" + "a" * 32, "monotonic": 100}])
        session["shutdown"] = {"style": "long-hold-until-exit", "max_hold_seconds": 12, "hold_seconds": 2,
                               "passed": True, "exit_code": 0, "defects": [], "observed": True,
                               "hold_end": "owned-process-exit", "release_sent": False,
                               "raw_input_start": 0, "raw_input_end": 1}
        return sessions

    def test_exactly_one_declared_stress_receipt_within_existing_eight_sessions(self):
        sessions = self.stress_receipt_fixture()
        receipt = long_power_stress_receipt(sessions)
        self.assertEqual(receipt["session"], "polski-services")
        self.assertEqual(receipt["pid"], 123)
        self.assertEqual(receipt["exit_code"], 0)
        self.assertTrue(receipt["passed"])
        shutdown = sessions[0]["shutdown"]
        shutdown.update(hold_end="hold-limit-release", release_sent=True, hold_seconds=12, raw_input_end=2)
        sessions[0]["raw_input"].append(dict(sessions[0]["raw_input"][0], pressed=False, monotonic=112))
        self.assertTrue(long_power_stress_receipt(sessions)["passed"])

    def test_stress_receipt_rejects_missing_duplicate_early_release_or_wrong_owner(self):
        for fault in ("missing", "duplicate", "ninth", "early-release", "wrong-owner", "failed-shutdown"):
            sessions = self.stress_receipt_fixture()
            session = sessions[0]
            if fault == "missing":
                session["shutdown"]["style"] = "bounded-cue-release"
            elif fault == "duplicate":
                sessions[1]["shutdown"]["style"] = "long-hold-until-exit"
            elif fault == "ninth":
                sessions.append(sessions[-1])
            elif fault == "early-release":
                session["shutdown"].update(hold_end="hold-limit-release", release_sent=True, raw_input_end=2)
                session["raw_input"].append(dict(session["raw_input"][0], pressed=False, monotonic=100.3))
            elif fault == "wrong-owner":
                session["raw_input"][0]["hwnd"] = 457
            else:
                session["shutdown"]["passed"] = False
            with self.subTest(fault=fault), self.assertRaises(AssertionError):
                long_power_stress_receipt(sessions)

    def test_shutdown_releases_power_promptly_on_spoken_shutdown(self):
        report, keys = self.shutdown_fixture()
        self.assertTrue(report["observed"])
        self.assertTrue(report["release_sent"])
        self.assertLessEqual(keys[1][2], 0.34)
        self.assertEqual([(key, pressed) for key, pressed, elapsed in keys], [("Insert", True), ("Insert", False)])
        self.assertEqual(report["exit_code"], 0)

    def test_shutdown_status_save_does_not_release_power_early_or_count_as_a_cue(self):
        for log_at in (0.3, 3):
            with self.subTest(log_at=log_at):
                report, keys = self.shutdown_fixture(log="Writing system_status to disk\n", log_at=log_at)
                self.assertFalse(report["observed"])
                self.assertTrue(report["release_sent"])
                self.assertGreaterEqual(report["hold_seconds"], 3)
                self.assertLessEqual(report["hold_seconds"], 3.03)
                self.assertEqual(report["hold_end"], "hold-limit-release")
                self.assertEqual([(key, pressed) for key, pressed, elapsed in keys], [("Insert", True), ("Insert", False)])
                self.assertGreaterEqual(keys[1][2], 3)
                self.assertEqual(report["exit_code"], 0)

    def test_failed_shutdown_attempt_survives_successful_cleanup(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.shutdown_fixture(log="Writing system_status to disk\n",
                                  wait_error=subprocess.TimeoutExpired("owned simulator", 12))
        probe = self.last_shutdown_probe
        first = probe.report["shutdown"]
        first_snapshot = dict(first)
        probe.text = lambda marker=0: "TTS: Shutting down\nTTS utterance: Shutting down\n"
        probe.key = mock.Mock()
        def wait(timeout):
            self.assertEqual(timeout, 12)
            probe.process.returncode = 0
        probe.process.wait.side_effect = wait
        with mock.patch.object(time, "perf_counter", return_value=4), \
             mock.patch.object(time, "sleep", side_effect=AssertionError("Spoken cleanup cue must remain prompt")):
            probe.close()
            probe.close()
        attempts = probe.report.get("shutdown_attempts", [])
        self.assertEqual(len(attempts), 2)
        self.assertIs(attempts[0], first)
        self.assertEqual(first, first_snapshot)
        self.assertFalse(first["passed"])
        self.assertFalse(first["observed"])
        self.assertIsNone(first["exit_code"])
        self.assertTrue(first["release_sent"])
        self.assertGreaterEqual(first["hold_seconds"], 3)
        self.assertIn("Writing system_status to disk", first["log_excerpt"])
        self.assertIs(attempts[1], probe.report["shutdown"])
        self.assertIsNot(attempts[1], first)
        self.assertTrue(attempts[1]["passed"])
        self.assertTrue(attempts[1]["observed"])
        self.assertEqual(attempts[1]["exit_code"], 0)
        self.assertEqual(attempts[1]["defects"], [])
        probe.key.assert_has_calls([mock.call("Insert", True), mock.call("Insert", False)])
        self.assertEqual(probe.key.call_count, 2)
        self.assertEqual(probe.native.owns.call_count, 2)

    def test_shutdown_hold_remains_bounded_without_any_log(self):
        report, keys = self.shutdown_fixture(log="")
        self.assertFalse(report["observed"])
        self.assertLessEqual(report["hold_seconds"], 3.03)
        self.assertEqual(keys[-1][1], False)

    def test_nonzero_shutdown_or_queue_overflow_stays_a_recorded_failure(self):
        for exit_code, log in ((7, "queue_post ovf q=0x123\n"), (0, "queue_post ovf q=0x123\n")):
            with self.subTest(exit_code=exit_code), self.assertRaisesRegex(AssertionError, "Graceful owned shutdown failed"):
                self.shutdown_fixture(exit_code, log)
            self.assertEqual(self.last_shutdown["exit_code"], exit_code)
            self.assertEqual(self.last_shutdown["defects"], ["queue_post ovf"])
            self.assertIn(log.strip(), self.last_shutdown["log_excerpt"])

    def test_shutdown_timeout_keeps_release_and_actual_live_exit_state(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.shutdown_fixture(wait_error=subprocess.TimeoutExpired("owned simulator", 12))
        self.assertTrue(self.last_shutdown["release_sent"])
        self.assertIsNone(self.last_shutdown["exit_code"])

    def test_already_exited_process_records_actual_failure_without_input(self):
        probe = object.__new__(ServicesProbe)
        probe.process, probe.native, probe.key = mock.Mock(), mock.Mock(), mock.Mock()
        probe.process.poll.return_value = probe.process.returncode = 7
        probe.report = {}
        probe.text = lambda: "queue_post ovf q=0x123\n"
        with self.assertRaisesRegex(AssertionError, "Graceful owned shutdown failed"):
            probe.close()
        self.assertEqual(probe.report["shutdown"]["exit_code"], 7)
        self.assertEqual(probe.report["shutdown"]["defects"], ["queue_post ovf"])
        probe.key.assert_not_called()
        probe.native.owns.assert_not_called()

    def mock_window_backend(self):
        from test_tts_simulator import WindowsBackend
        backend = object.__new__(WindowsBackend)
        backend.window_callback = lambda callback: callback
        backend.user32 = mock.Mock()
        backend.owns_window = mock.Mock(return_value=True)
        return backend

    def test_empty_desktop_poll_clears_stale_last_error(self):
        backend = self.mock_window_backend()
        for stale in (0, 18, 5):
            with self.subTest(stale=stale):
                errors = [stale]
                def enumerate_windows(callback, parameter):
                    self.assertEqual(errors[0], 0)
                    return False
                backend.user32.EnumWindows.side_effect = enumerate_windows
                with mock.patch.object(ctypes, "set_last_error", create=True,
                                       side_effect=lambda value: errors.__setitem__(0, value)), \
                     mock.patch.object(ctypes, "get_last_error", create=True, side_effect=lambda: errors[0]):
                    self.assertIsNone(backend.find_window(123))

    def test_enum_windows_access_denied_is_not_empty_desktop(self):
        backend = self.mock_window_backend()
        backend.user32.EnumWindows.return_value = False
        denied = OSError("Access denied")
        denied.winerror = 5
        with mock.patch.object(ctypes, "set_last_error", create=True), \
             mock.patch.object(ctypes, "get_last_error", create=True, return_value=5), \
             mock.patch.object(ctypes, "WinError", create=True, return_value=denied) as windows_error:
            with self.assertRaises(OSError) as raised:
                backend.find_window(123)
        self.assertIs(raised.exception, denied)
        windows_error.assert_called_once_with(5)

    def test_window_callback_exception_is_preserved(self):
        backend = self.mock_window_backend()
        original = RuntimeError("Ownership callback failed")
        backend.owns_window.side_effect = original
        backend.user32.EnumWindows.side_effect = lambda callback, parameter: callback(456, parameter)
        with mock.patch.object(ctypes, "set_last_error", create=True), \
             mock.patch.object(ctypes, "get_last_error", create=True, return_value=5):
            with self.assertRaises(RuntimeError) as raised:
                backend.find_window(123)
        self.assertIs(raised.exception, original)

    def test_owned_window_class_api_error_is_preserved(self):
        backend = self.mock_window_backend()
        backend.user32.GetClassNameW.return_value = 0
        backend.user32.EnumWindows.side_effect = lambda callback, parameter: callback(456, parameter)
        denied = OSError("Access denied")
        denied.winerror = 5
        with mock.patch.object(ctypes, "set_last_error", create=True), \
             mock.patch.object(ctypes, "get_last_error", create=True, return_value=5), \
             mock.patch.object(ctypes, "WinError", create=True, return_value=denied) as windows_error:
            with self.assertRaises(OSError) as raised:
                backend.find_window(123)
        self.assertIs(raised.exception, denied)
        windows_error.assert_called_once_with(5)

    def test_enum_stop_after_callback_without_error_is_not_empty(self):
        backend = self.mock_window_backend()
        backend.owns_window.return_value = False
        def enumerate_windows(callback, parameter):
            self.assertTrue(callback(456, parameter))
            return False
        backend.user32.EnumWindows.side_effect = enumerate_windows
        with mock.patch.object(ctypes, "set_last_error", create=True), \
             mock.patch.object(ctypes, "get_last_error", create=True, return_value=0):
            with self.assertRaisesRegex(RuntimeError, "stopped after a callback"):
                backend.find_window(123)

    def test_window_selection_keeps_pid_class_and_unique_window_checks(self):
        backend = self.mock_window_backend()
        backend.owns_window.side_effect = lambda pid, window: pid == 123 and window != 456
        def class_name(window, output, length):
            output.value = "STATIC" if window == 457 else "SDL_app"
            return len(output.value)
        backend.user32.GetClassNameW.side_effect = class_name
        def enumerate_windows(callback, parameter):
            return all(callback(window, parameter) for window in windows)
        backend.user32.EnumWindows.side_effect = enumerate_windows
        with mock.patch.object(ctypes, "set_last_error", create=True), \
             mock.patch.object(ctypes, "get_last_error", create=True, return_value=0):
            windows = (456, 457)
            self.assertIsNone(backend.find_window(123))
            windows = (456, 457, 458)
            self.assertEqual(backend.find_window(123), 458)
            windows = (458, 459)
            with self.assertRaisesRegex(RuntimeError, "Multiple SDL windows"):
                backend.find_window(123)
        self.assertNotIn(456, [call.args[0] for call in backend.user32.GetClassNameW.call_args_list])

    def test_close_without_window_terminates_only_owned_process_without_input(self):
        probe = object.__new__(ServicesProbe)
        probe.process = mock.Mock()
        probe.process.poll.return_value = None
        probe.window = None
        probe.native = mock.Mock()
        probe.key = mock.Mock()
        probe.close()
        probe.process.terminate.assert_called_once_with()
        probe.process.wait.assert_called_once_with(timeout=12)
        probe.native.owns.assert_not_called()
        probe.key.assert_not_called()

    def test_close_with_window_keeps_ownership_guard(self):
        probe = object.__new__(ServicesProbe)
        probe.process = mock.Mock()
        probe.process.poll.return_value = None
        probe.window, probe.desktop = 456, "Private"
        probe.native = mock.Mock()
        probe.native.owns.side_effect = AssertionError("Wrong HWND owner")
        probe.key = mock.Mock()
        with self.assertRaisesRegex(AssertionError, "Wrong HWND owner"):
            probe.close()
        probe.key.assert_not_called()
        probe.process.terminate.assert_not_called()

    def test_cleanup_failure_keeps_primary_exception_and_separate_tracebacks(self):
        original = ValueError("Original launch failure")
        probe = mock.Mock()
        probe.launch.side_effect = original
        probe.close.side_effect = RuntimeError("Secondary cleanup failure")
        immutable = {"simdisk/.rockbox/" + name: "unused" for name in
                     ("config.cfg", "accessibility.cfg", "accessibility-shortcut.cfg", "connectivity.cfg")}
        with mock.patch.object(Path, "mkdir"), \
             mock.patch(__name__ + ".configure_session"), \
             mock.patch(__name__ + ".mapping_file_identity", return_value={"version": 11}), \
             mock.patch(__name__ + ".regular_files", return_value=immutable), \
             mock.patch(__name__ + ".ServicesProbe", return_value=probe), \
             mock.patch(__name__ + ".write_json") as write_report:
            with self.assertRaises(ValueError) as raised:
                run_session(None, "Private", 1, Path("runtime"), Path("results"), "english", "services", {}, 25)
        self.assertIs(raised.exception, original)
        report = write_report.call_args.args[1]
        self.assertFalse(report["passed"])
        self.assertEqual(report["error"], "ValueError: Original launch failure")
        self.assertEqual(report["cleanup_error"], "RuntimeError: Secondary cleanup failure")
        self.assertIn("ValueError: Original launch failure", report["primary_traceback"])
        self.assertNotIn("Secondary cleanup failure", report["primary_traceback"])
        self.assertIn("RuntimeError: Secondary cleanup failure", report["cleanup_traceback"])

    def mock_runtime_assets(self, libraries=(), directories_present=True):
        build = Path("synthetic-fullinstall")
        with mock.patch.object(Path, "glob", return_value=[build / name for name in libraries]), \
             mock.patch.object(Path, "rglob", return_value=[]), \
             mock.patch.object(Path, "is_dir", return_value=directories_present), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch(__name__ + ".confined_path", side_effect=lambda path, root: path):
            return runtime_assets(build)

    def test_static_sdl_fullinstall_accepts_zero_dlls_and_empty_present_directories(self):
        assets = self.mock_runtime_assets()
        build = Path("synthetic-fullinstall")
        self.assertEqual(set(assets), {build / "UI256.bmp"} |
                         {build / "simdisk/.rockbox" / name for name in RESOURCE_FILES})
        self.assertFalse(any(path.suffix.casefold() == ".dll" for path in assets))

    def test_actual_dll_assets_remain_in_the_frozen_copy_set(self):
        assets = self.mock_runtime_assets(("runtime.dll", "SDL2.dll"))
        self.assertEqual({path.name for path in assets if path.suffix == ".dll"}, {"runtime.dll", "SDL2.dll"})

    def test_missing_fullinstall_directory_is_still_rejected(self):
        with self.assertRaisesRegex(AssertionError, "Missing fullinstall directory"):
            self.mock_runtime_assets(directories_present=False)

    def test_authorization_missing_flags_never_reads_a_build(self):
        arguments = argparse.Namespace(build_ready=False, exe_sha256=None, freeze=None, freeze_sha256=None)
        with mock.patch.object(Path, "open", side_effect=AssertionError("Unexpected read")):
            with self.assertRaisesRegex(AssertionError, "Explicit parent"):
                validate_authorization(arguments)

    def test_hash_rejects_placeholders_and_uppercase(self):
        for value in (None, "", "a" * 63, "A" * 64, "0" * 64, "g" * 64):
            with self.subTest(value=value):
                self.assertFalse(sha256_value(value))
        self.assertTrue(sha256_value("a" * 64))

    def test_relative_names_reject_escapes(self):
        for value in ("../profile", "/absolute", "C:/release", "a\\b", "a/../b", "a//b", ".", ""):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                relative_name(value)

    def test_freeze_requires_complete_binding(self):
        freeze = {"scope": SCOPE, "version": EXPECTED_VERSION, "exe_sha256": "a" * 64,
                  "with_music": True, "sources": {name: "b" * 64 for name in SOURCE_PATHS},
                  "build_files": {name: "c" * 64 for name in METADATA_FILES}}
        freeze["build_files"]["rockboxui.exe"] = "a" * 64
        validate_freeze_shape(freeze, "a" * 64)
        for field, replacement in (("scope", "old-stage"), ("version", "r34-alpha8"),
                                   ("scope", "r1-percent-network-review-20261019/services-gui"),
                                   ("version", "0ed3734e5e-espeak-r34-hibyr1-win-alpha10-20261016"),
                                   ("version", "0ed3734e5e-espeak-r34-hibyr1-win-alpha11-20261017"),
                                   ("version", "0ed3734e5e-espeak-r34-hibyr1-win-alpha15-20261019"),
                                   ("with_music", 0), ("sources", {}), ("exe_sha256", "b" * 64)):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate_freeze_shape(dict(freeze, **{field: replacement}), "a" * 64)

    def test_source_action_contract_and_v11_profile(self):
        contract = mapping_contract()
        profile = mapping_profile(contract)
        self.assertEqual((contract["source_version"], contract["profile_version"]), (11, 11))
        self.assertTrue(profile.startswith("RBACCESSIBILITY:11\nenabled:0\n"))
        parsed = parse_mapping_profile(profile.encode("ascii"))
        self.assertEqual(parsed["version"], 11)
        self.assertFalse(parsed["enabled"])
        self.assertEqual(parsed["click_sources"], 7)
        self.assertTrue(parsed["empty_pitch"])
        self.assertEqual(parsed["empty_semitones"], -4)
        self.assertEqual(parsed["touch_hold_ms"], 900)
        self.assertFalse(parsed["stroke_repeat"])
        self.assertEqual(contract["gesture_count"], 20)
        self.assertEqual(len(profile.splitlines()), 92)
        self.assertEqual(profile.splitlines()[5:8], ["stroke_repeat:0", "empty_pitch:1", "empty_semitones:-4"])
        self.assertIn("button:2:1:17:0\n", profile)
        self.assertIn("button:1:1:18:0\n", profile)
        self.assertEqual(len(re.findall(r"^button:", profile, re.MULTILINE)), 20)
        self.assertEqual(len(re.findall(r"^playback_button:", profile, re.MULTILINE)), 20)
        self.assertEqual(parsed["playback_buttons"][(1, 0)], 17)
        self.assertEqual(parsed["playback_buttons"][(2, 1)], 0)
        self.assertEqual(parsed["buttons"][(1, 0)], 27)
        self.assertEqual(parsed["buttons"][(2, 1)], 17)
        self.assertEqual(len(re.findall(r"^gesture:", profile, re.MULTILINE)), 20)
        self.assertEqual(set(parsed["gestures"]), set(range(1, 21)))
        self.assertFalse(any(parsed["gestures"].values()))
        self.assertFalse(any(parsed["gesture_launch"].values()))
        self.assertFalse(any(parsed["button_launch"].values()))
        self.assertFalse(any(parsed["launch_paths"].values()))
        self.assertNotIn("button:0:1:17:", profile)

    def test_default_single_hold_and_other_buttons_are_system(self):
        contract = mapping_contract()
        system = contract["actions"]["ACCESSIBILITY_ACTION_SYSTEM"]
        profile = mapping_profile(contract)
        custom = []
        for button, slot, action in re.findall(r"^button:(\d+):(\d+):(\d+):0$", profile, re.MULTILINE):
            if int(action) != system:
                custom.append((int(button), int(slot), int(action)))
        self.assertEqual(custom, [(1, 1, 18), (2, 1, 17)])

    def test_mapping_contract_rejects_stale_format_slots_and_action_ids(self):
        source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        button_source = (ROOT / "apps/accessibility_buttons.h").read_text(encoding="utf-8")
        gesture_source = (ROOT / "apps/accessibility_gesture.h").read_text(encoding="utf-8")
        for old, new in (
                ('ACCESSIBILITY_HEADER "RBACCESSIBILITY:11\\n"', 'ACCESSIBILITY_HEADER "RBACCESSIBILITY:9\\n"'),
                ('ACCESSIBILITY_V9_HEADER "RBACCESSIBILITY:9\\n"', 'ACCESSIBILITY_V9_HEADER "RBACCESSIBILITY:8\\n"'),
                ('ACCESSIBILITY_V8_HEADER "RBACCESSIBILITY:8\\n"', 'ACCESSIBILITY_V8_HEADER "RBACCESSIBILITY:7\\n"'),
                ('ACCESSIBILITY_V7_HEADER "RBACCESSIBILITY:7\\n"', 'ACCESSIBILITY_V7_HEADER "RBACCESSIBILITY:6\\n"'),
                ("ACCESSIBILITY_SLOT_COUNT (ACCESSIBILITY_STROKE_COUNT + 4)",
                 "ACCESSIBILITY_SLOT_COUNT (ACCESSIBILITY_STROKE_COUNT + 2)"),
                ("ACCESSIBILITY_ACTION_TOGGLE_ESPEAK,", "ACCESSIBILITY_ACTION_TOGGLE_ESPEAK = 18,"),
                ("ACCESSIBILITY_ACTION_TOGGLE_TOUCH,", "ACCESSIBILITY_ACTION_TOGGLE_TOUCH = 20,"),
                ("ACCESSIBILITY_ACTION_DATE,", "ACCESSIBILITY_ACTION_DATE = 21,"),
                ("ACCESSIBILITY_ACTION_SUMMARY,", "ACCESSIBILITY_ACTION_SUMMARY = 22,"),
                ("ACCESSIBILITY_ACTION_SYSTEM = ACCESSIBILITY_ACTION_COUNT",
                 "ACCESSIBILITY_ACTION_SYSTEM = 23")):
            changed = source.replace(old, new)
            self.assertNotEqual(changed, source)
            with self.subTest(replacement=new), \
                 mock.patch.object(Path, "read_text", side_effect=[changed, button_source, gesture_source]), \
                 self.assertRaises(AssertionError):
                mapping_contract()

    def test_v11_services_profile_is_not_silently_accepted_as_an_older_format(self):
        profile = mapping_profile(mapping_contract())
        for invalid in (profile.replace("RBACCESSIBILITY:11", "RBACCESSIBILITY:9"),
                        profile.replace("RBACCESSIBILITY:11", "RBACCESSIBILITY:8"),
                        profile.replace("touch_hold:900\n", ""),
                        profile.replace("stroke_repeat:0\n", ""),
                        profile.replace("empty_pitch:1\n", ""),
                        profile.replace("empty_semitones:-4\n", ""),
                        profile.replace("empty_pitch:1\nempty_semitones:-4\n", "empty_semitones:-4\nempty_pitch:1\n"),
                        profile.replace("gesture:20:0:0\n", "")):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                parse_mapping_profile(invalid.encode("ascii"))

    def test_v9_profile_validates_all_source_masks_pitch_choices_and_semitone_bounds(self):
        profile = mapping_profile(mapping_contract())
        for sources in range(8):
            for pitch in (0, 1):
                for semitones in (-12, -4, 0, 12):
                    trial = (profile.replace("click:7\n", f"click:{sources}\n")
                             .replace("empty_pitch:1\n", f"empty_pitch:{pitch}\n")
                             .replace("empty_semitones:-4\n", f"empty_semitones:{semitones}\n"))
                    with self.subTest(sources=sources, pitch=pitch, semitones=semitones):
                        parsed = parse_mapping_profile(trial.encode("ascii"))
                        self.assertEqual((parsed["click_sources"], parsed["empty_pitch"], parsed["empty_semitones"]),
                                         (sources, bool(pitch), semitones))
        for field, values in (("click:7", ("click:8", "click:-1", "click:07")),
                              ("empty_pitch:1", ("empty_pitch:2", "empty_pitch:-1", "empty_pitch:01")),
                              ("empty_semitones:-4", ("empty_semitones:-13", "empty_semitones:13",
                                                      "empty_semitones:-0", "empty_semitones:04", "empty_semitones:+4"))):
            for invalid in values:
                with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                    parse_mapping_profile(profile.replace(field + "\n", invalid + "\n").encode("ascii"))

    def test_v9_profile_calls_shared_parser_with_original_bytes(self):
        from test_hiby_accessibility_gui import parse_accessibility_config
        profile = mapping_profile(mapping_contract()).encode("ascii")
        expected = parse_accessibility_config(profile)
        with mock.patch("test_hiby_accessibility_gui.parse_accessibility_config", return_value=expected) as parser:
            self.assertIs(parse_mapping_profile(profile), expected)
        parser.assert_called_once_with(profile)

    def test_services_profile_rejects_valid_legacy_input_without_losing_shared_compatibility(self):
        from test_hiby_accessibility_gui import parse_accessibility_config
        profile = (session_mapping_profile(mapping_contract(), "missing-voice")
                   .replace("RBACCESSIBILITY:8\n", "RBACCESSIBILITY:7\n", 1)
                   .replace("click:7\n", "click:3\n", 1)
                   .replace("empty_pitch:1\nempty_semitones:-4\n", "", 1)).encode("ascii")
        self.assertEqual(parse_accessibility_config(profile)["version"], 7)
        with self.assertRaisesRegex(AssertionError, "Services profile must use the current v11 format"):
            parse_mapping_profile(profile)

    def test_frozen_menu_structure_preserves_accessibility_and_system_order(self):
        layout = source_layout()
        self.assertEqual(layout["accessibility"], list(ACCESSIBILITY_BASELINE))
        self.assertEqual(layout["talkbox"], list(TALKBOX_BASELINE))
        self.assertEqual(layout["espeak"], list(ESPEAK_BASELINE))
        position = layout["system"].index("keyclick_menu")
        self.assertEqual(layout["system"][position - 2:position], ["touchscreen_menu", "accessibility_buttons_item"])
        self.assertEqual(layout["screen_state"], ["accessibility_screen_unlock_item", "accessibility_screen_lock_item"])

    def test_touchscreen_relocation_is_conditional_and_keeps_display_siblings(self):
        settings = (ROOT / "apps/menus/settings_menu.c").read_text(encoding="utf-8")
        display = (ROOT / "apps/menus/display_menu.c").read_text(encoding="utf-8")
        self.assertRegex(settings, r'#if defined\(HAVE_TOUCHSCREEN\) && defined\(HAVE_ESPEAK\)\s*'
                         r'&touchscreen_menu,\s*#ifdef HIBY_R1\s*&accessibility_buttons_item,\s*#endif\s*#endif')
        self.assertEqual(menu_items(display, "display_menu"), [
            "lcd_settings", "lcd_remote_settings", "scroll_settings_menu", "peak_meter_menu", "codepage_setting",
            "touchscreen_menu"])
        declaration = re.search(r'MAKE_MENU\(display_menu,.*?\);', display, re.DOTALL)
        self.assertIsNotNone(declaration)
        self.assertRegex(declaration[0], r'#if defined\(HAVE_TOUCHSCREEN\) && !defined\(HAVE_ESPEAK\)\s*'
                         r'&touchscreen_menu,\s*#endif')

    def layout_source_fixture(self, accessibility=ACCESSIBILITY_BASELINE, system=None, shortcut=False,
                              screen_state=("accessibility_screen_unlock_item", "accessibility_screen_lock_item"),
                              talkbox=TALKBOX_BASELINE, espeak=ESPEAK_BASELINE,
                              reader=("tts_reader_unit_item", "tts_reader_page_lines_item")):
        if system is None:
            position = SYSTEM_BASELINE.index("keyclick_menu")
            system = SYSTEM_BASELINE[:position] + ("touchscreen_menu", "accessibility_buttons_item") + SYSTEM_BASELINE[position:]
        general = ("wps_settings", "playlist_settings", "file_menu", "tagcache_menu", "display_menu", "system_menu",
                   "startup_shutdown_menu", "bookmark_settings_menu", "autoresume_menu", "browse_langs", "voice_settings_menu")
        settings = "\n".join("MAKE_MENU(" + name + ", 0, 0, 0, " + ", ".join("&" + item for item in items) + ");"
                             for name, items in (("voice_settings_menu", accessibility), ("system_menu", system),
                                                 ("talkbox_settings_menu", talkbox), ("tts_settings_menu", espeak),
                                                 ("tts_reader_settings_menu", reader),
                                                 ("settings_menu_item", general), ("accessibility_screen_menu", screen_state),
                                                 ("accessibility_display_menu", ("accessibility_curtain_item", "accessibility_screen_menu")),
                                                 ("accessibility_shortcut_menu", ("accessibility_shortcut_enabled_item", "accessibility_shortcut_services_menu")),
                                                 ("accessibility_shortcut_services_menu", ("accessibility_shortcut_espeak_item", "accessibility_shortcut_voice_files_item",
                                                                                       "accessibility_shortcut_touch_item", "accessibility_shortcut_curtain_item")),
                                                 ("keyclick_menu", ("keyclick", "keyclick_repeats", "keyclick_sources"))))
        if shortcut:
            settings += "\nMAKE_MENU(accessibility_shortcut_menu, 0, 0, 0, &obsolete_item);"
        main = (ROOT / "apps/menus/main_menu.c").read_text(encoding="utf-8")
        display = (ROOT / "apps/menus/display_menu.c").read_text(encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=[settings, main, display]):
            return source_layout()

    def test_menu_contract_rejects_duplicate_shortcut_buttons_and_reordered_siblings(self):
        layout = self.layout_source_fixture()
        self.assertEqual(layout["accessibility"][0], "talkbox_settings_menu")
        for accessibility in (
                ("accessibility_touch_item", "talkbox_settings_menu") + ACCESSIBILITY_BASELINE[2:],
                ACCESSIBILITY_BASELINE[:1] + ("accessibility_shortcut_menu",) + ACCESSIBILITY_BASELINE[1:],
                ACCESSIBILITY_BASELINE[:4] + ("accessibility_buttons_item",) + ACCESSIBILITY_BASELINE[4:],
                ACCESSIBILITY_BASELINE + ACCESSIBILITY_BASELINE[-1:]):
            with self.subTest(accessibility=accessibility), self.assertRaises(AssertionError):
                self.layout_source_fixture(accessibility=accessibility)
        with self.assertRaisesRegex(AssertionError, "Duplicate accessibility shortcut menu"):
            self.layout_source_fixture(shortcut=True)
        system = tuple(layout["system"])
        position = system.index("touchscreen_menu")
        for invalid in (
                system[:position] + system[position + 1:position + 2] + system[position:position + 1] + system[position + 2:],
                system[:position] + system[position + 1:], system + ("accessibility_buttons_item",),
                system[:position] + system[position + 2:position + 3] + system[position:position + 2] + system[position + 3:],
                (system[1], system[0]) + system[2:]):
            with self.subTest(system=invalid), self.assertRaises(AssertionError):
                self.layout_source_fixture(system=invalid)

    def test_talkbox_contract_rejects_engine_leaks_duplicate_controls_and_reader_changes(self):
        for espeak in (ESPEAK_BASELINE[:-1], ESPEAK_BASELINE[::-1], ESPEAK_BASELINE + ESPEAK_BASELINE[:1],
                       *(ESPEAK_BASELINE + (item,) for item in TALKBOX_BASELINE[1:]),
                       ESPEAK_BASELINE + ("accessibility_shortcut_menu", "talk_menu_item")):
            with self.subTest(espeak=espeak), self.assertRaisesRegex(AssertionError, "nine synthesis parameters"):
                self.layout_source_fixture(espeak=espeak)
        for talkbox in (TALKBOX_BASELINE[:-1], TALKBOX_BASELINE[::-1], TALKBOX_BASELINE + TALKBOX_BASELINE[:1],
                        TALKBOX_BASELINE + ("accessibility_shortcut_menu",), TALKBOX_BASELINE + ("talk_menu_item",)):
            with self.subTest(talkbox=talkbox), self.assertRaisesRegex(AssertionError, "Talkbox must contain"):
                self.layout_source_fixture(talkbox=talkbox)
        for reader in (("tts_reader_unit_item",), ("tts_reader_page_lines_item", "tts_reader_unit_item"),
                       ("tts_reader_unit_item", "tts_reader_page_lines_item", "tts_reader_unit_item")):
            with self.subTest(reader=reader), self.assertRaisesRegex(AssertionError, "Text reader settings must retain"):
                self.layout_source_fixture(reader=reader)

    def test_screen_announcements_reject_control_aliases_missing_duplicate_and_reordered_rows(self):
        expected = ("accessibility_screen_unlock_item", "accessibility_screen_lock_item")
        for invalid in (expected[:1], expected[::-1], expected + expected[:1],
                        expected + ("sel_softlock",), expected + ("backlight_timeout",),
                        expected + ("backlight_timeout_plugged",)):
            with self.subTest(rows=invalid), self.assertRaisesRegex(AssertionError, 'exactly unlock and lock'):
                self.layout_source_fixture(screen_state=invalid)

    def test_system_spoken_input_rows_require_unique_adjacent_order_and_synthesis(self):
        labels = {identifier: identifier for identifier in REQUIRED_IDS}
        expected = ("LANG_TOUCHSCREEN_SETTINGS", "LANG_ACCESSIBILITY_BUTTONS", "LANG_KEYCLICK")
        rows = [f"TTS: {identifier}\nTTS utterance: {identifier}\n" for identifier in expected]
        self.assertEqual(system_input_rows(["Other row"] + rows, labels), [1, 2, 3])
        for invalid in (rows[:-1], rows + rows[:1], rows[::-1], rows[:1] + ["Other row"] + rows[1:],
                        [rows[0], "TTS: LANG_ACCESSIBILITY_BUTTONS\n", rows[2]],
                        [rows[0], "TTS utterance: LANG_ACCESSIBILITY_BUTTONS\n", rows[2]]):
            with self.subTest(rows=invalid), self.assertRaises(AssertionError):
                system_input_rows(invalid, labels)

    def test_physical_button_rows_match_source_buttons_slots_and_reset_tail(self):
        source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        for name, expected in (("button_labels", tuple(row[0] for row in BUTTON_ROWS[:20:4])),
                               ("press_labels", tuple(row[1] for row in BUTTON_ROWS[:4]))):
            declaration = re.search(r'static const int ' + name + r'\[[^]]*\]\s*=\s*\{(.*?)\};', source, re.DOTALL)
            self.assertIsNotNone(declaration)
            self.assertEqual(tuple(re.findall(r'LANG_[A-Z_0-9]+', declaration[1])), expected)
        self.assertIn('LANG_ACCESSIBILITY_INTERFACE_ACTIONS', source)
        self.assertIn('LANG_ACCESSIBILITY_PLAYBACK_ACTIONS', source)
        self.assertEqual(len(BUTTON_ROWS), 21)
        self.assertEqual(BUTTON_ROWS[5][-1], "LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES")
        self.assertEqual(BUTTON_ROWS[9][-1], "LANG_ACCESSIBILITY_TOGGLE_ESPEAK")
        self.assertEqual(BUTTON_ROWS[20:], (("LANG_RESET",),))
        self.assertEqual(BUTTON_ROOT_ROWS, ("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", "LANG_ACCESSIBILITY_PLAYBACK_ACTIONS",
                                          "LANG_ACCESSIBILITY_HOLD_TIME", "LANG_RESET", "LANG_ACCESSIBILITY_CONTROLS_GUIDE"))

    def test_reviewed_touch_gesture_and_action_menu_orders_match_source(self):
        source = (ROOT / "apps/accessibility.c").read_text(encoding="utf-8")
        for name, expected in (("menu_labels", TOUCH_ROWS), ("empty_feedback_labels", EMPTY_FEEDBACK_CHOICES),
                               ("stroke_labels", GESTURE_ROWS[:16]),
                               ("action_labels", GESTURE_ACTION_ROWS)):
            declaration = re.search(r'static const int ' + name + r'\[[^]]*\]\s*=\s*\{(.*?)\};',
                                    source, re.DOTALL)
            self.assertIsNotNone(declaration)
            self.assertEqual(tuple(re.findall(r'LANG_[A-Z_0-9]+', declaration[1])), expected)
        for slot, label in zip(("DOUBLE", "HOLD", "TRIPLE", "DOUBLE_HOLD"), GESTURE_ROWS[16:]):
            declaration = re.search(r'if \(slot == ACCESSIBILITY_' + slot + r'_SLOT\)\s*return (LANG_\w+);',
                                    source)
            self.assertIsNotNone(declaration)
            self.assertEqual(declaration[1], label)
        self.assertEqual(tuple(map(len, (TOUCH_ROWS, GESTURE_ROWS, GESTURE_ACTION_ROWS))), (8, 20, 27))
        self.assertEqual(TOUCH_ROWS[4:], ("LANG_ACCESSIBILITY_EMPTY_FEEDBACK", "LANG_KEYCLICK_EMPTY_PITCH",
                                        "LANG_KEYCLICK_EMPTY_SEMITONES", "LANG_RESET"))
        self.assertEqual(GESTURE_ROWS[-2:], ("LANG_ACCESSIBILITY_TRIPLE_TAP", "LANG_ACCESSIBILITY_DOUBLE_TAP_HOLD"))
        self.assertEqual(GESTURE_ACTION_ROWS[-5:], ("LANG_ACCESSIBILITY_ACTION_FIRST", "LANG_ACCESSIBILITY_ACTION_LAST",
                                                   "LANG_ACCESSIBILITY_ACTION_PAGE_FIRST", "LANG_ACCESSIBILITY_ACTION_PAGE_LAST",
                                                   "LANG_ACCESSIBILITY_SHORTCUT_ACTION"))

    def menu_cycle_fixture(self, identifiers, observations=None):
        probe = object.__new__(ServicesProbe)
        probe.labels = {identifier: identifier for identifier in REQUIRED_IDS + VOICE_ONLY_IDS}
        if observations is None:
            observations = ["".join(f"TTS: {identifier}\nTTS utterance: {identifier}\n" for identifier in
                                    ((row,) if isinstance(row, str) else row)) for row in identifiers]
        probe.latest, probe.report = observations[0], {}
        probe.row = mock.Mock(side_effect=observations[1:] + observations[:1])
        return probe

    def test_menu_cycles_verify_eight_touch_three_empty_two_screen_twenty_gesture_and_twenty_two_action_rows(self):
        for name, expected in (("Touch submenu", TOUCH_ROWS), ("Gesture assignments", GESTURE_ROWS),
                               ("Gesture action selector", GESTURE_ACTION_ROWS), ("Physical button settings", BUTTON_ROWS),
                               ("Physical profile root", BUTTON_ROOT_ROWS), ("Playback physical profile", PLAYBACK_BUTTON_ROWS),
                               ("Empty feedback choices", EMPTY_FEEDBACK_CHOICES), ("Screen announcements", SCREEN_STATE_ROWS),
                               ("System touchscreen", SYSTEM_TOUCH_ROWS), ("Autolock choices", AUTOLOCK_CHOICES)):
            with self.subTest(menu=name):
                probe = self.menu_cycle_fixture(expected)
                rows = probe.cycle(name, expected_order=expected)
                self.assertEqual(len(rows), len(expected))
                self.assertEqual(probe.row.call_count, len(expected))
                self.assertEqual(probe.report["menu_cycles"][name],
                                 [[str(part) for part in ((row,) if isinstance(row, str) else row)] for row in expected])

    def test_physical_menu_cycle_rejects_missing_swapped_or_incomplete_compound_speech(self):
        for invalid in (BUTTON_ROWS[:-1], (BUTTON_ROWS[1], BUTTON_ROWS[0]) + BUTTON_ROWS[2:],
                        BUTTON_ROWS[:9] + (BUTTON_ROWS[9][:2] + ("LANG_ACCESSIBILITY_SYSTEM_DEFAULT",),) + BUTTON_ROWS[10:]):
            probe = self.menu_cycle_fixture(invalid)
            with self.subTest(rows=invalid), self.assertRaises(AssertionError):
                probe.cycle("Physical button settings", expected_order=BUTTON_ROWS)
        observations = ["".join(f"TTS: {identifier}\nTTS utterance: {identifier}\n" for identifier in row)
                        for row in BUTTON_ROWS]
        for prefix in ("TTS", "TTS utterance"):
            invalid = observations[:]
            invalid[5] = invalid[5].replace(prefix + ": LANG_ACCESSIBILITY_TOGGLE_VOICE_FILES\n", "")
            probe = self.menu_cycle_fixture(BUTTON_ROWS, invalid)
            with self.subTest(prefix=prefix), self.assertRaises(AssertionError):
                probe.cycle("Physical button settings", expected_order=BUTTON_ROWS)

    def test_menu_cycles_reject_missing_reordered_duplicate_or_unsynthesized_new_rows(self):
        for expected, new_indices in ((TOUCH_ROWS, (2, 3, 4, 5, 6)), (BUTTON_ROOT_ROWS, (0, 1)),
                                      (EMPTY_FEEDBACK_CHOICES, (0, 1, 2)),
                                      (SCREEN_STATE_ROWS, (0, 1)), (GESTURE_ROWS, (18, 19)),
                                      (GESTURE_ACTION_ROWS, (19, 20, 21))):
            cases = [expected[:-1], expected[:-2] + expected[-1:] + expected[-2:-1],
                     expected[:-1] + expected[-2:-1]]
            for actual in cases:
                probe = self.menu_cycle_fixture(actual)
                with self.subTest(actual=actual), self.assertRaises(AssertionError):
                    probe.cycle("Incorrect menu", expected_order=expected)
            for index in new_indices:
                for prefix in ("TTS", "TTS utterance"):
                    observations = [f"TTS: {identifier}\nTTS utterance: {identifier}\n" for identifier in expected]
                    observations[index] = f"{prefix}: {expected[index]}\n"
                    probe = self.menu_cycle_fixture(expected, observations)
                    with self.subTest(label=expected[index], prefix=prefix), self.assertRaises(AssertionError):
                        probe.cycle("Incomplete speech", expected_order=expected)

    def test_option_selector_uses_increasing_up_direction_without_reordering_expected_rows(self):
        probe = self.menu_cycle_fixture(GESTURE_ACTION_ROWS)
        rows = probe.cycle("Gesture action selector", expected_order=GESTURE_ACTION_ROWS, key="Up")
        self.assertEqual(len(rows), 27)
        self.assertEqual(probe.row.call_count, 27)
        self.assertTrue(all(call.args[1] == "Up" for call in probe.row.call_args_list))
        descending = GESTURE_ACTION_ROWS[:1] + tuple(reversed(GESTURE_ACTION_ROWS[1:]))
        probe = self.menu_cycle_fixture(descending)
        with self.assertRaisesRegex(AssertionError, "menu order changed"):
            probe.cycle("Wrong selector direction", expected_order=GESTURE_ACTION_ROWS)

    def selector_probe_fixture(self, values, default, render):
        probe = object.__new__(ServicesProbe)
        probe.labels = {identifier: identifier for identifier in REQUIRED_IDS + VOICE_ONLY_IDS}
        probe.report = {}
        selected = [values.index(default)]
        def speech(parts):
            return "".join(f"TTS: {part}\nTTS utterance: {part}\n" for part in parts)
        probe.latest = speech(render(default))
        def enter(identifier, expected=()):
            self.assertTrue(speech_ordered(probe.latest, expected))
            return probe.latest
        def row(name, key="Down", expected=()):
            if key == "Left":
                self.assertEqual(values[selected[0]], default)
                probe.latest = speech(expected)
            else:
                selected[0] = (selected[0] + {"Up": -1, "Down": 1}[key]) % len(values)
                probe.latest = speech(render(values[selected[0]]))
                self.assertTrue(speech_ordered(probe.latest, expected), name)
            return probe.latest
        probe.enter = mock.Mock(side_effect=enter)
        probe.row = mock.Mock(side_effect=row)
        return probe, selected

    def test_backlight_table_navigation_matches_source_values_and_restores_zero(self):
        settings = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
        selector = (ROOT / "apps/gui/option_select.c").read_text(encoding="utf-8")
        declaration = re.search(r'static const int timeout_sec_common\[\] = \{([^}]+)\}', settings)
        self.assertIsNotNone(declaration)
        values = tuple(int(value) for value in re.findall(r'-?\d+', declaration[1]))[:23]
        self.assertEqual(values[:13], (-1, 0, *range(1, 11), 15))
        self.assertRegex(settings, re.compile(r'TABLE_SETTING_LIST\(F_TIME_SETTING \| F_ALLOW_ARBITRARY_VALS,\s*'
                                             r'backlight_timeout,.*?23, timeout_sec_common\)', re.DOTALL))
        self.assertIn("return info->values[selection];", selector)
        def render(value):
            if value in (-1, 0):
                return ("LANG_NEVER" if value == -1 else "LANG_ALWAYS",)
            return (str(value), "VOICE_SECOND" if value == 1 else "VOICE_SECONDS")
        probe, selected = self.selector_probe_fixture(values, 0, render)
        browse_backlight_timeout(probe)
        self.assertEqual(values[selected[0]], 0)
        self.assertEqual(probe.row.call_count, 25)
        self.assertEqual(probe.row.call_args_list[-1],
                         mock.call("Cancel unchanged backlight timeout", "Left", ("LANG_BACKLIGHT",)))
        self.assertIn("both traces and units", probe.report["backlight_timeout_speech_scope"])

    def test_boundary_choice_navigation_matches_source_order_and_restores_sound(self):
        settings = (ROOT / "apps/settings_list.c").read_text(encoding="utf-8")
        selector = (ROOT / "apps/gui/option_select.c").read_text(encoding="utf-8")
        declaration = re.search(r'CHOICE_SETTING\(0, list_boundary_feedback, LANG_ACCESSIBILITY_LIST_BOUNDARY, (\d+),'
                                r'(.*?)\),\s*OFFON_SETTING', settings, re.DOTALL)
        self.assertIsNotNone(declaration)
        choices = tuple(re.findall(r'ID2P\((LANG_[A-Z_]+)\)', declaration[2]))
        default = int(declaration[1])
        self.assertEqual(default, 1)
        self.assertEqual(choices, BOUNDARY_CHOICES)
        self.assertRegex(selector, re.compile(r'HASFLAG\(setting, F_CHOICE_SETTING\)\)\s*\{\s*return selection;'))
        probe, selected = self.selector_probe_fixture(choices, choices[default], lambda value: (value,))
        browse_boundary_settings(probe)
        self.assertEqual(selected[0], default)
        self.assertEqual(probe.row.call_args_list, [
            *[mock.call("List boundary feedback row " + str(index), "Down") for index in range(1, 5)],
            mock.call("Cancel unchanged list boundary feedback", "Left", ("LANG_ACCESSIBILITY_LIST_BOUNDARY",))])
        self.assertTrue(probe.report["list_boundary_menu"]["restored"])

    def bluetooth_layout_fixture(self, present=False, mutate=None, trace_change=None):
        probe = ServicesProbe.__new__(ServicesProbe)
        probe.labels = {identifier: identifier for identifier in REQUIRED_IDS + VOICE_ONLY_IDS}
        probe.report = {}
        runtime = Path("synthetic-bluetooth")
        directory = runtime / "simdisk/.rockbox"
        contents = {
            "connectivity.cfg": b"RBCONNECTIVITY:1\nwifi:1\nbluetooth:1\nairplane:0\n",
            "accessibility.cfg": b"synthetic private input bytes\r\n",
        }
        if present:
            contents["bluetooth.cfg"] = b"RBBLUETOOTH:1\nauto:2\nretry:120\npause:1\nannounce:1\nlast:\n"
        original = dict(contents)
        state = ["connectivity", 1]
        actions = []

        def spoken():
            menu, selected = state
            if menu == "root":
                identifiers, count, indices = BLUETOOTH_ROOT_ROWS[selected], 7, True
            elif menu == "preferences":
                identifiers, count, indices = BLUETOOTH_PREFERENCE_ROWS[selected], 5, True
            elif type(menu) is int:
                identifiers, count = (BLUETOOTH_CHOICES[menu][selected],), len(BLUETOOTH_CHOICES[menu])
                indices = menu != 1
            else:
                identifiers, count, indices = ("LANG_HIBY_BT_TITLE", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE"), 3, True
            parts = identifiers + ((str(selected + 1), "VOICE_OF", str(count)) if indices else ())
            result = ''.join(f'{prefix}: {value}\n' for prefix in ("TTS", "TTS utterance") for value in parts)
            return trace_change(menu, selected, result) if trace_change else result

        def row(name, key="Down", expected=()):
            actions.append((name, key, expected))
            menu, selected = state
            if key == "Down":
                count = 7 if menu == "root" else 5 if menu == "preferences" else len(BLUETOOTH_CHOICES[menu])
                state[1] = (selected + 1) % count
            elif key == "Right":
                if menu == "connectivity":
                    state[:] = ["root", 0]
                elif menu == "root":
                    self.assertEqual(selected, 5, "Must not activate Bluetooth power/pair/connect/disconnect/status")
                    state[:] = ["preferences", 0]
                else:
                    self.assertEqual(menu, "preferences", "Must cancel choices, never accept")
                    self.assertLess(selected, 4, "Last-device row is read-only")
                    default = BLUETOOTH_PREFERENCE_ROWS[selected][1]
                    state[:] = [selected, BLUETOOTH_CHOICES[selected].index(default)]
            elif key == "Left":
                if type(menu) is int:
                    self.assertEqual(BLUETOOTH_CHOICES[menu][selected], BLUETOOTH_PREFERENCE_ROWS[menu][1])
                    state[:] = ["preferences", menu]
                elif menu == "preferences":
                    state[:] = ["root", 5]
                else:
                    self.assertEqual(menu, "root")
                    state[:] = ["connectivity", 1]
                    if mutate:
                        mutate(contents)
            else:
                self.fail("Unexpected Bluetooth key: " + key)
            probe.latest = spoken()
            self.assertTrue(speech_contains(probe.latest, expected))
            return probe.latest

        def read_bytes(path):
            self.assertEqual(path.parent, directory)
            if path.name not in contents:
                raise FileNotFoundError(str(path))
            return contents[path.name]

        probe.latest = spoken()
        probe.row = mock.Mock(side_effect=row)
        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes), \
             mock.patch.object(Path, "write_bytes", side_effect=AssertionError("Bluetooth browse cannot write")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("Bluetooth browse cannot write")):
            browse_bluetooth_layout(probe, runtime)
        self.assertEqual(contents, original)
        self.assertEqual(state, ["connectivity", 1])
        return probe, actions

    def test_bluetooth_layout_actual_seek_cycle_cancel_order_and_action_count(self):
        probe, actions = self.bluetooth_layout_fixture()
        expected = [("Enter LANG_HIBY_BT_TITLE", "Right", BLUETOOTH_ROOT_ROWS[0])]
        expected += [(f"Bluetooth root row {index}", "Down", ()) for index in range(1, 8)]
        expected += [(f"Seek LANG_HIBY_BT_SETTINGS {index}", "Down", ()) for index in range(1, 6)]
        expected += [("Enter LANG_HIBY_BT_SETTINGS", "Right", BLUETOOTH_PREFERENCE_ROWS[0])]
        expected += [(f"Bluetooth preferences row {index}", "Down", ()) for index in range(1, 6)]
        for index, (identifier, default) in enumerate(BLUETOOTH_PREFERENCE_ROWS[:4]):
            if index:
                expected.append(("Seek " + identifier + " 1", "Down", ()))
            expected.append(("Enter " + identifier, "Right", (default,)))
            expected += [(f"Bluetooth choices {identifier} row {offset}", "Down", ())
                         for offset in range(1, (3, 4, 2, 2)[index] + 1)]
            expected.append(("Cancel unchanged Bluetooth choice " + identifier, "Left", (identifier, default)))
        expected += [("Back to Bluetooth root from preferences", "Left", ("LANG_HIBY_BT_SETTINGS",)),
                     ("Back to Connectivity from Bluetooth", "Left", ("LANG_HIBY_BT_TITLE", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE"))]
        self.assertEqual(actions, expected)
        self.assertEqual(len(actions), 43)
        self.assertEqual(len(actions), bluetooth_layout_action_count())
        self.assertEqual([len(rows) for rows in probe.report["menu_cycles"].values()], [7, 5, 3, 4, 2, 2])
        self.assertEqual(probe.report["bluetooth_layout"]["choices_cancelled"], 4)
        self.assertEqual(probe.report["bluetooth_layout"]["choice_counts"], [3, 4, 2, 2])
        self.assertTrue(probe.report["bluetooth_layout"]["restored"])
        self.assertIsNone(probe.report["bluetooth_layout"]["files"]["bluetooth.cfg"])
        self.assertIsNone(probe.report["bluetooth_layout"]["files"]["bluetooth.cfg.tmp"])

    def test_bluetooth_layout_preserves_existing_bytes_and_rejects_changes_creation_and_removal(self):
        probe, _ = self.bluetooth_layout_fixture(present=True)
        self.assertRegex(probe.report["bluetooth_layout"]["files"]["bluetooth.cfg"], r"^[a-f0-9]{64}$")
        for name in ("bluetooth.cfg", "bluetooth.cfg.tmp", "connectivity.cfg", "accessibility.cfg"):
            for present in (False, True):
                with self.subTest(name=name, present=present), self.assertRaisesRegex(AssertionError, "changed preference/profile bytes or file presence"):
                    self.bluetooth_layout_fixture(present=present, mutate=lambda contents: contents.update({name: b"unexpected"}))
        with self.assertRaisesRegex(AssertionError, "changed preference/profile bytes or file presence"):
            self.bluetooth_layout_fixture(present=True, mutate=lambda contents: contents.pop("bluetooth.cfg"))

    def test_bluetooth_layout_rejects_wrong_indices_in_either_trace_for_every_row(self):
        for menu, count in (("root", 7), ("preferences", 5), (0, 3), (1, 4), (2, 2), (3, 2)):
            for selected in range(count):
                for prefix in ("TTS", "TTS utterance"):
                    def changed(current_menu, current_selected, text):
                        if (type(current_menu) is type(menu) and current_menu == menu and current_selected == selected):
                            suffix = f"{prefix}: {selected + 1}\n{prefix}: VOICE_OF\n{prefix}: {count}\n"
                            return text + suffix if type(menu) is int and menu == 1 else text.replace(suffix, "")
                        return text
                    with self.subTest(menu=menu, selected=selected, prefix=prefix), self.assertRaises(AssertionError):
                        self.bluetooth_layout_fixture(trace_change=changed)

    def test_bluetooth_return_allows_one_unavailable_refresh_diagnostic_but_not_done_or_duplicate(self):
        for prefix in ("TTS", "TTS utterance"):
            def unavailable(menu, selected, text):
                return f"{prefix}: LANG_HIBY_CONNECTIVITY_UNAVAILABLE\n" + text if menu == "connectivity" else text
            with self.subTest(prefix=prefix):
                self.bluetooth_layout_fixture(trace_change=unavailable)
            for diagnostic in ("LANG_HIBY_BT_DONE", "LANG_HIBY_CONNECTIVITY_FAILED",
                               "LANG_HIBY_CONNECTIVITY_UNAVAILABLE\n" + prefix + ": LANG_HIBY_CONNECTIVITY_UNAVAILABLE"):
                def invalid(menu, selected, text):
                    return f"{prefix}: {diagnostic}\n" + text if menu == "connectivity" else text
                with self.subTest(prefix=prefix, diagnostic=diagnostic), self.assertRaises(AssertionError):
                    self.bluetooth_layout_fixture(trace_change=invalid)

    def test_bluetooth_layout_source_matches_simulator_entry_order_defaults_and_cancel_guard(self):
        source = (ROOT / "apps/hiby_bluetooth.c").read_text(encoding="utf-8")
        for name, expected in (("main_labels", [row[0] for row in BLUETOOTH_ROOT_ROWS]),
                               ("preference_labels", [row[0] for row in BLUETOOTH_PREFERENCE_ROWS]),
                               ("reconnect_labels", BLUETOOTH_CHOICES[0]), ("retry_labels", BLUETOOTH_CHOICES[1]),
                               ("loss_labels", BLUETOOTH_CHOICES[2]), ("boolean_labels", BLUETOOTH_CHOICES[3])):
            block = re.search(r"static const int " + name + r"\[\]\s*=\s*\{([^}]+)\}", source).group(1)
            self.assertEqual(re.findall(r"LANG_\w+", block), list(expected))
        entry = source[source.index("int hiby_bluetooth_menu(void)"):]
        native_start, native_end = entry.index("#ifndef SIMULATOR"), entry.index("#endif")
        self.assertLess(native_start, entry.index("hiby_bluetooth_init()"))
        self.assertLess(entry.index("run_operation(HIBY_BT_REFRESH"), native_end)
        self.assertLess(native_end, entry.index("selected = choose_main(selected)"))
        self.assertIn("if (choice >= 0 && hiby_bt_preferences_set(preference, value))", source)
        self.assertIn("case 5: result = bluetooth_preferences_menu(); break;", source)
        defaults = (ROOT / "apps/hiby_bluetooth_settings.c").read_text(encoding="utf-8")
        block = re.search(r"static const struct hiby_bt_preferences defaults = \{([^}]+)\}", defaults).group(1)
        for value in (".auto_mode = BLUETOOTH_RECONNECT_STARTUP_AND_LOSS", ".retry_seconds = 120",
                      ".pause_on_loss = true", ".announce = true"):
            self.assertIn(value, block)

    def test_bluetooth_layout_readiness_keeps_actual_gui_and_native_gates_open(self):
        result = readiness()
        self.assertFalse(result["gui_ready"])
        self.assertFalse(result["simulator_launched"])
        controls = result["context_controls"]
        self.assertEqual(controls["bluetooth_root_rows"], BLUETOOTH_ROOT_ROWS)
        self.assertEqual(controls["bluetooth_preference_rows"], BLUETOOTH_PREFERENCE_ROWS)
        self.assertEqual(controls["bluetooth_choices"], BLUETOOTH_CHOICES)
        self.assertEqual(controls["bluetooth_layout_actions"], 43)
        self.assertIn("Parent must tag only numeric retry choices LIST_POSITION_SLIDER", controls["bluetooth_retry_role_gate"])
        self.assertIn("physical retest required", controls["bluetooth_busy"])
        self.assertEqual(result["missing_source_ids"], {"english": [], "polski": []})
        self.assertEqual(len(result["sessions"]), 8)

    def layout_case_fixture(self, private_changed=False, buttons_changed=False):
        probe = mock.Mock()
        probe.labels = {identifier: identifier for identifier in REQUIRED_IDS + VOICE_ONLY_IDS}
        probe.report = {}
        spoken = lambda expected: ''.join(f'TTS: {value}\nTTS utterance: {value}\n' for value in expected)
        def row(name, key='Down', expected=()):
            parts = expected
            if name.startswith("Confirm ") and expected and expected[0] in TALKBOX_ROWS[-2:]:
                if name not in ("Confirm disabled LANG_TALKBOX_ANNOUNCE_POSITION",
                                "Confirm files-only LANG_TALKBOX_ANNOUNCE_POSITION"):
                    parts += (str(TALKBOX_ROWS.index(expected[0]) + 1), "VOICE_OF", "11")
            return spoken(parts)
        probe.row.side_effect = row
        def enter(name, expected=()):
            if name in ("LANG_TTS_LANGUAGE", "LANG_TTS_VARIANT"):
                return spoken(expected + ("1", "VOICE_OF", "4" if name == "LANG_TTS_LANGUAGE" else "2"))
            if name == "LANG_TTS_ENABLED":
                return spoken(expected + ("2", "VOICE_OF", "2"))
            return spoken(expected)
        probe.enter.side_effect = enter
        cycle_rows = {"Settings": ("LANG_CONNECTIVITY",),
                      "General System": ("LANG_TOUCHSCREEN_SETTINGS", "LANG_ACCESSIBILITY_BUTTONS", "LANG_KEYCLICK"),
                      "Talkbox settings": TALKBOX_ROWS}
        probe.cycle.side_effect = lambda name, *arguments, **keywords: [
            spoken((identifier, str(index + 1), "VOICE_OF", "11") if name == "Talkbox settings" else (identifier,))
            for index, identifier in enumerate(cycle_rows.get(name, ()))]
        runtime = Path("synthetic-layout")
        private_config = runtime / "simdisk/.rockbox/accessibility.cfg"
        preferences = runtime / "simdisk/.rockbox/connectivity.cfg"
        profile = mapping_profile(mapping_contract()).encode("ascii")
        reads = {"private": 0, "connectivity": 0, "autolock": 0}
        def read_bytes(path):
            if path == private_config:
                reads["private"] += 1
                changed = buttons_changed and reads["private"] > 1 or private_changed and reads["private"] > 4
                return profile + b"unexpected\n" if changed else profile
            if path == runtime / 'simdisk/.rockbox/accessibility-lock.cfg':
                reads['autolock'] += 1
                return b'RBACCESSIBILITY-LOCK:2\nunlock-button:0\nphysical-buttons:0\ntimeout:' + (
                    b'600\n' if reads['autolock'] == 1 else b'-1\n')
            self.assertEqual(path, preferences)
            reads["connectivity"] += 1
            return (b"RBCONNECTIVITY:1\nwifi:1\nbluetooth:1\nairplane:" +
                    (b"1\n" if reads["connectivity"] == 1 else b"0\n"))
        self.last_layout_probe, self.last_layout_reads = probe, reads
        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes), \
             mock.patch.object(Path, "write_bytes", side_effect=AssertionError("Layout cannot write profiles")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("Layout cannot write profiles")), \
             mock.patch(__name__ + ".browse_rapid_wrap") as rapid_wrap, \
             mock.patch(__name__ + ".browse_bluetooth_layout", autospec=True) as bluetooth_layout:
            probe.attach_mock(bluetooth_layout, "bluetooth_layout")
            result = layout_case(probe, runtime)
            rapid_wrap.assert_called_once_with(probe, runtime)
            bluetooth_layout.assert_called_once_with(probe, runtime)
        return probe, reads, result

    def test_layout_case_only_browses_new_menus_cancels_and_preserves_original_return_route(self):
        probe, reads, result = self.layout_case_fixture()
        expected = [
            mock.call.enter("LANG_ACCESSIBILITY_BUTTONS", (BUTTON_ROOT_ROWS[0],)),
            mock.call.cycle("Physical button settings", expected_order=BUTTON_ROOT_ROWS),
            mock.call.enter("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", BUTTON_ROWS[0]),
            mock.call.cycle("LANG_ACCESSIBILITY_INTERFACE_ACTIONS", expected_order=BUTTON_ROWS),
            mock.call.row("Back to physical settings from LANG_ACCESSIBILITY_INTERFACE_ACTIONS", "Left",
                          ("LANG_ACCESSIBILITY_INTERFACE_ACTIONS",)),
            mock.call.enter("LANG_ACCESSIBILITY_PLAYBACK_ACTIONS", PLAYBACK_BUTTON_ROWS[0]),
            mock.call.cycle("LANG_ACCESSIBILITY_PLAYBACK_ACTIONS", expected_order=PLAYBACK_BUTTON_ROWS),
            mock.call.row("Back to physical settings from LANG_ACCESSIBILITY_PLAYBACK_ACTIONS", "Left",
                          ("LANG_ACCESSIBILITY_PLAYBACK_ACTIONS",)),
            *[call for identifier, rows in zip(GUIDE_CONTEXT_ROWS, GUIDE_ROWS) for call in (
                mock.call.enter("LANG_ACCESSIBILITY_CONTROLS_GUIDE", (GUIDE_CONTEXT_ROWS[0],)),
                mock.call.cycle("Controls guide contexts " + identifier, expected_order=GUIDE_CONTEXT_ROWS),
                mock.call.enter(identifier, rows[0]),
                mock.call.cycle("Default controls " + identifier, expected_order=rows),
                mock.call.row("Back from controls guide " + identifier, "Left", ("LANG_ACCESSIBILITY_CONTROLS_GUIDE",)))],
            mock.call.row("Back to General System from Physical buttons", "Left", ("LANG_ACCESSIBILITY_BUTTONS",)),
            mock.call.row("Back to General", "Left"),
            mock.call.enter("LANG_DISPLAY"),
            mock.call.cycle("Display", ("LANG_TOUCHSCREEN_SETTINGS", "LANG_ACCESSIBILITY_BUTTONS")),
            mock.call.enter("LANG_LCD_MENU"),
            mock.call.enter("LANG_BRIGHTNESS", ("100",)),
            *[call for key, values in (("Down", range(99, 0, -1)), ("Up", range(2, 101))) for value in values
              for call in ([mock.call.row("Brightness " + str(value), key, (str(value),))] +
                           ([mock.call.capture("Brightness lower boundary silent with sound disabled", mock.ANY, silent=True)] if value == 1 else []))],
            mock.call.capture("Brightness upper boundary silent with sound disabled", mock.ANY, silent=True),
            *[mock.call.row("Brightness boundary " + str(value), key, (str(value),))
              for key, value in (("Down", 99), ("Up", 100))],
            mock.call.row("Cancel unchanged brightness", "Left", ("LANG_BRIGHTNESS",)),
            mock.call.enter("LANG_BACKLIGHT", ("LANG_ALWAYS",)),
            mock.call.row("Backlight timeout never", "Up", ("LANG_NEVER",)),
            mock.call.row("Backlight timeout always", "Down", ("LANG_ALWAYS",)),
            *[mock.call.row("Backlight timeout " + str(value), key,
                           (str(value), "VOICE_SECOND" if value == 1 else "VOICE_SECONDS"))
              for key, values in (("Down", (*range(1, 11), 15)), ("Up", range(10, 0, -1))) for value in values],
            mock.call.row("Backlight timeout returns to always on", "Up", ("LANG_ALWAYS",)),
            mock.call.row("Cancel unchanged backlight timeout", "Left", ("LANG_BACKLIGHT",)),
            mock.call.row("Back to Display from LCD settings", "Left", ("LANG_LCD_MENU",)),
            mock.call.row("Back to General from Display", "Left"),
            mock.call.enter("LANG_VOICE", ("LANG_TALKBOX_SETTINGS",)),
            mock.call.cycle("Accessibility", expected_order=ACCESSIBILITY_ROWS),
            mock.call.enter("LANG_TALKBOX_SETTINGS", (TALKBOX_ROWS[0],)),
            mock.call.cycle("Talkbox settings", expected_order=TALKBOX_ROWS),
            mock.call.enter("LANG_TTS", (ESPEAK_ROWS[0],)),
            mock.call.cycle("eSpeak settings", expected_order=ESPEAK_ROWS),
            mock.call.enter("LANG_TTS_LANGUAGE", ("LANG_TTS_SYSTEM",)),
            mock.call.row("Cancel unchanged LANG_TTS_LANGUAGE", "Left", ("LANG_TTS_LANGUAGE",)),
            mock.call.enter("LANG_TTS_VARIANT", ("LANG_TTS_DEFAULT_VARIANT",)),
            mock.call.row("Cancel unchanged LANG_TTS_VARIANT", "Left", ("LANG_TTS_VARIANT",)),
            *[call for identifier, default in (("LANG_TTS_PITCH", 50), ("LANG_TTS_VOLUME", 100), ("LANG_TTS_RANGE", 50))
              for call in (
                  mock.call.enter(identifier, (str(default), "VOICE_PERCENT")),
                  mock.call.row("Preview percent " + identifier, "Up", (str(default + 1), "VOICE_PERCENT")),
                  mock.call.row("Restore percent " + identifier, "Down", (str(default), "VOICE_PERCENT")),
                  mock.call.row("Cancel unchanged percent " + identifier, "Left", (identifier,)))],
            mock.call.row("Back to Talkbox from eSpeak", "Left", ("LANG_TTS",)),
            mock.call.enter("LANG_TTS_ENABLED", ("LANG_SET_BOOL_YES",)),
            mock.call.row("Cancel unchanged Talkbox enable switch", "Left", ("LANG_TTS_ENABLED",)),
            mock.call.enter("LANG_TTS_READER_SETTINGS", (READER_ROWS[0],)),
            mock.call.cycle("Text reading settings", expected_order=READER_ROWS),
            mock.call.row("Back to Talkbox from Text reading settings", "Left", ("LANG_TTS_READER_SETTINGS",)),
            mock.call.enter("LANG_TALKBOX_ANNOUNCE_POSITION", ("LANG_TALKBOX_POSITION_EXCEPT_SLIDERS",)),
            mock.call.row("Choose position mode disabled 0", "Down", ("LANG_OFF",)),
            mock.call.row("Confirm disabled LANG_TALKBOX_ANNOUNCE_POSITION", "Right", ("LANG_TALKBOX_ANNOUNCE_POSITION",)),
            mock.call.enter("LANG_TALKBOX_ANNOUNCE_POSITION", ("LANG_OFF",)),
            mock.call.row("Choose position mode files-only 0", "Up", ("LANG_TALKBOX_POSITION_EXCEPT_SLIDERS",)),
            mock.call.row("Choose position mode files-only 1", "Up", ("LANG_TALKBOX_POSITION_FILES",)),
            mock.call.row("Confirm files-only LANG_TALKBOX_ANNOUNCE_POSITION", "Right", ("LANG_TALKBOX_ANNOUNCE_POSITION",)),
            mock.call.enter("LANG_TALKBOX_ANNOUNCE_POSITION", ("LANG_TALKBOX_POSITION_FILES",)),
            mock.call.row("Choose position mode interface-only 0", "Up", ("LANG_TALKBOX_POSITION_INTERFACE",)),
            mock.call.row("Confirm interface-only LANG_TALKBOX_ANNOUNCE_POSITION", "Right", ("LANG_TALKBOX_ANNOUNCE_POSITION",)),
            mock.call.enter("LANG_TALKBOX_ANNOUNCE_POSITION", ("LANG_TALKBOX_POSITION_INTERFACE",)),
            mock.call.row("Choose position mode everywhere 0", "Up", ("LANG_TALKBOX_POSITION_EVERYWHERE",)),
            mock.call.row("Confirm everywhere LANG_TALKBOX_ANNOUNCE_POSITION", "Right", ("LANG_TALKBOX_ANNOUNCE_POSITION",)),
            mock.call.enter("LANG_TALKBOX_ANNOUNCE_POSITION", ("LANG_TALKBOX_POSITION_EVERYWHERE",)),
            mock.call.row("Choose position mode enabled 0", "Down", ("LANG_TALKBOX_POSITION_INTERFACE",)),
            mock.call.row("Choose position mode enabled 1", "Down", ("LANG_TALKBOX_POSITION_FILES",)),
            mock.call.row("Choose position mode enabled 2", "Down", ("LANG_TALKBOX_POSITION_EXCEPT_SLIDERS",)),
            mock.call.row("Confirm enabled LANG_TALKBOX_ANNOUNCE_POSITION", "Right", ("LANG_TALKBOX_ANNOUNCE_POSITION",)),
            *[call for identifier in TALKBOX_ROWS[-1:] for call in (
                mock.call.enter(identifier, ("LANG_SET_BOOL_YES",)),
                mock.call.row("Disable " + identifier, "Down", ("LANG_SET_BOOL_NO",)),
                mock.call.row("Confirm disabled " + identifier, "Right", (identifier,)),
                mock.call.enter(identifier, ("LANG_SET_BOOL_NO",)),
                mock.call.row("Restore enabled " + identifier, "Up", ("LANG_SET_BOOL_YES",)),
                mock.call.row("Confirm enabled " + identifier, "Right", (identifier,)))],
            mock.call.enter("LANG_ACCESSIBILITY_TYPING_SETTINGS", (TYPING_ROWS[0],)),
            mock.call.cycle("Typing settings", expected_order=TYPING_ROWS),
            *[call for identifier, choices in TYPING_CHOICES for call in (
                mock.call.enter(identifier, (choices[0],)),
                mock.call.cycle("Typing choices " + identifier, expected_order=choices, key="Up"),
                mock.call.row("Return from " + identifier, "Left", (identifier,)))],
            mock.call.row("Back to Talkbox from Typing", "Left", ("LANG_ACCESSIBILITY_TYPING_SETTINGS",)),
            mock.call.enter("LANG_ACCESSIBILITY_LIST_BOUNDARY", (BOUNDARY_CHOICES[1],)),
            mock.call.cycle("List boundary feedback", expected_order=BOUNDARY_CHOICES[1:] + BOUNDARY_CHOICES[:1], key="Down"),
            mock.call.row("Cancel unchanged list boundary feedback", "Left", ("LANG_ACCESSIBILITY_LIST_BOUNDARY",)),
            mock.call.enter("LANG_ACCESSIBILITY_DISPLAY_SETTINGS", (ACCESSIBILITY_DISPLAY_ROWS[0],)),
            mock.call.cycle("Accessibility screen settings", expected_order=ACCESSIBILITY_DISPLAY_ROWS),
            mock.call.enter("LANG_ACCESSIBILITY_SCREEN_STATE", (SCREEN_STATE_ROWS[0],)),
            mock.call.cycle("Screen state announcements", expected_order=SCREEN_STATE_ROWS),
            mock.call.row("Back to Screen settings from Screen announcements", "Left", ("LANG_ACCESSIBILITY_SCREEN_STATE",)),
            mock.call.row("Back to Talkbox from Screen settings", "Left", ("LANG_ACCESSIBILITY_DISPLAY_SETTINGS",)),
            mock.call.enter("LANG_ACCESSIBILITY", ("LANG_ACCESSIBILITY_ENABLED",)),
            mock.call.cycle("Touch submenu", expected_order=TOUCH_ROWS),
            mock.call.enter("LANG_ACCESSIBILITY_EMPTY_FEEDBACK", (EMPTY_FEEDBACK_CHOICES[0],)),
            mock.call.cycle("Empty-place feedback choices", expected_order=EMPTY_FEEDBACK_CHOICES, key="Up"),
            mock.call.row("Confirm original sound-only empty feedback", "Right",
                          ("LANG_ACCESSIBILITY_EMPTY_FEEDBACK", EMPTY_FEEDBACK_CHOICES[0])),
            mock.call.enter("LANG_KEYCLICK_EMPTY_PITCH", ("LANG_SET_BOOL_YES",)),
            mock.call.row("Preview empty pitch disabled", "Down", ("LANG_SET_BOOL_NO",)),
            mock.call.row("Restore empty pitch enabled", "Up", ("LANG_SET_BOOL_YES",)),
            mock.call.row("Cancel unchanged empty pitch switch", "Left", ("LANG_KEYCLICK_EMPTY_PITCH", "LANG_ON")),
            mock.call.enter("LANG_KEYCLICK_EMPTY_SEMITONES", ("-4",)),
            mock.call.row("Preview empty pitch minus three", "Up", ("-3",)),
            mock.call.row("Restore empty pitch minus four", "Down", ("-4",)),
            mock.call.row("Cancel unchanged empty pitch value", "Left", ("LANG_KEYCLICK_EMPTY_SEMITONES", "-4")),
            mock.call.enter("LANG_ACCESSIBILITY_GESTURES", ("LANG_ACCESSIBILITY_INTERFACE_ACTIONS",)),
            mock.call.cycle("Gesture assignment profiles", expected_order=BUTTON_ROOT_ROWS[:2]),
            *[call for identifier in BUTTON_ROOT_ROWS[:2] for call in (
                mock.call.enter(identifier, ("LANG_ACCESSIBILITY_SWIPE_LEFT", "LANG_ACCESSIBILITY_UNASSIGNED")),
                mock.call.cycle("Gesture assignments " + identifier, expected_order=GESTURE_ROWS + ("LANG_RESET",)),
                mock.call.enter("LANG_ACCESSIBILITY_SWIPE_LEFT", ("LANG_ACCESSIBILITY_UNASSIGNED",)),
                mock.call.cycle("Gesture action selector " + identifier, expected_order=GESTURE_ACTION_ROWS, key="Up"),
                mock.call.row("Cancel action selector to Gesture assignments " + identifier, "Left",
                              ("LANG_ACCESSIBILITY_SWIPE_LEFT", "LANG_ACCESSIBILITY_UNASSIGNED")),
                mock.call.row("Back to Gesture profiles from " + identifier, "Left", (identifier,)))],
            mock.call.row("Back to Touch submenu from Gesture profiles", "Left", ("LANG_ACCESSIBILITY_GESTURES",)),
            mock.call.row("Back to Settings 1", "Left"),
            mock.call.row("Back to Settings 2", "Left"),
            mock.call.row("Back to Settings 3", "Left"),
            mock.call.row("Back to Settings 4", "Left"),
            mock.call.enter("LANG_CONNECTIVITY", ("LANG_HIBY_WIFI", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE")),
            mock.call.row("Connectivity Bluetooth unavailable", expected=("LANG_HIBY_BT_TITLE", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE")),
            mock.call.bluetooth_layout(probe, Path("synthetic-layout")),
            mock.call.row("Connectivity airplane initially off", expected=("LANG_HIBY_AIRPLANE_MODE", "LANG_OFF")),
            mock.call.row("Airplane ON reports unavailable/partial", "Right",
                          ("LANG_HIBY_AIRPLANE_MODE", "LANG_HIBY_CONNECTIVITY_PARTIAL", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE")),
            mock.call.row("Airplane OFF retains prior requests and unavailable state", "Right",
                          ("LANG_HIBY_AIRPLANE_MODE", "LANG_OFF", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE")),
            mock.call.row("Wi-Fi still unavailable", "Down", ("LANG_HIBY_WIFI", "LANG_HIBY_CONNECTIVITY_UNAVAILABLE")),
            mock.call.row("Back to root 1", "Left"),
            mock.call.row("Back to root 2", "Left"),
            mock.call.enter("LANG_SYSTEM"),
            mock.call.cycle("Root System information", ("LANG_HIBY_WIFI_STARTUP", "LANG_CONNECTIVITY", "LANG_HIBY_BT_TITLE")),
        ]
        start = probe.method_calls.index(expected[0])
        self.assertEqual(probe.method_calls[start:], expected)
        self.assertEqual(reads, {"private": 5, "connectivity": 2, "autolock": 3})
        self.assertEqual(result, {"tts enabled": "on", "talk menu": "off", "talk mixer level": "0", "tts volume": "100"})
        self.assertEqual(probe.report["talkbox_hierarchy"], dict(
            passed=True, restored=True, accessibility_rows=list(ACCESSIBILITY_ROWS),
            talkbox_rows=list(TALKBOX_ROWS), espeak_rows=list(ESPEAK_ROWS), reader_rows=list(READER_ROWS)))
        probe.press.assert_not_called()
        probe.chord.assert_not_called()
        self.assertFalse(any(call.args[0] == "LANG_ACCESSIBILITY_SHORTCUT" for call in probe.enter.call_args_list))
        self.assertEqual(probe.report["system_input_positions"], [0, 1, 2])
        self.assertIn("no mapping edit, physical timing or hardware acceptance", probe.report["physical_button_menu_scope"])
        self.assertIn("selector canceled and private profile unchanged", probe.report["gesture_menu_scope"])
        self.assertIn("no mapped new-action or touch acceptance", probe.report["gesture_menu_scope"])

    def test_system_touchscreen_selector_traverses_twelve_choices_persists_600_and_restores_legacy(self):
        probe, reads, _ = self.layout_case_fixture()
        expected = [
            mock.call.enter('LANG_TOUCHSCREEN_SETTINGS', (SYSTEM_TOUCH_ROWS[0],)),
            mock.call.cycle('System touchscreen settings', expected_order=SYSTEM_TOUCH_ROWS),
            mock.call.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', ('LANG_ACCESSIBILITY_AUTOLOCK_LEGACY',)),
            mock.call.cycle('Automatic screen lock choices', expected_order=AUTOLOCK_CHOICES, key='Up'),
            mock.call.row('Cancel unchanged fresh automatic lock selector', 'Left', ('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT',)),
            mock.call.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', ('LANG_ACCESSIBILITY_AUTOLOCK_LEGACY',)),
            mock.call.row('Select 600 seconds', 'Down', ('600', 'VOICE_SECONDS')),
            mock.call.row('Save 600 second policy', 'Right', ('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT',)),
            mock.call.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', ('600', 'VOICE_SECONDS')),
            mock.call.row('Restore legacy automatic lock policy', 'Up', ('LANG_ACCESSIBILITY_AUTOLOCK_LEGACY',)),
            mock.call.row('Save legacy automatic lock policy', 'Right', ('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT',)),
            mock.call.enter('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', ('LANG_ACCESSIBILITY_AUTOLOCK_LEGACY',)),
            mock.call.row('Keep restored legacy automatic lock policy', 'Left', ('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT',)),
            mock.call.enter('LANG_TOUCH_WAKE_SETTINGS', (TOUCH_WAKE_ROWS[0], 'LANG_OFF')),
            mock.call.cycle('Touch wake gestures', expected_order=TOUCH_WAKE_ROWS),
            *[call for identifier in TOUCH_WAKE_ROWS for call in (
                mock.call.enter(identifier, ('LANG_OFF',)),
                mock.call.cycle('Touch wake actions ' + identifier, expected_order=TOUCH_WAKE_CHOICES, key='Up'),
                mock.call.row('Cancel unchanged touch wake action ' + identifier, 'Left', (identifier, 'LANG_OFF')))],
            mock.call.row('Back to System touchscreen from Touch wake', 'Left', ('LANG_TOUCH_WAKE_SETTINGS',)),
            mock.call.row('Back to General System from Touchscreen', 'Left', ('LANG_TOUCHSCREEN_SETTINGS',)),
        ]
        start = probe.method_calls.index(expected[0])
        self.assertEqual(probe.method_calls[start:start + len(expected)], expected)
        self.assertEqual(reads['autolock'], 3)
        self.assertIn('restored legacy -1', probe.report['autolock_selector_scope'])

    def test_autolock_numeric_unit_speech_requires_both_traces_and_exact_number(self):
        good = 'TTS: 600\nTTS: sekund\nTTS utterance: 600 sekund\n'
        require_seconds_speech(good, 600, 'sekund')
        for text in (good.replace('600', '1600'), good.replace('sekund', 'minutes'),
                     'TTS: 600 sekund\n', 'TTS utterance: 600 sekund\n'):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                require_seconds_speech(text, 600, 'sekund')

    def test_timer_choices_and_ten_system_rows_match_final_source_contract(self):
        source = (ROOT / 'apps/accessibility_screen.c').read_text(encoding='utf-8')
        match = re.search(r'static const int durations\[\]\s*=\s*\{([^}]+)\}', source)
        self.assertIsNotNone(match)
        self.assertEqual(tuple(int(value.strip()) for value in match[1].split(',')), AUTOLOCK_DURATIONS)
        self.assertEqual(len(AUTOLOCK_CHOICES), 12)
        self.assertEqual(len(SYSTEM_TOUCH_ROWS), 10)
        self.assertEqual(AUTOLOCK_CHOICES[0], 'LANG_ACCESSIBILITY_AUTOLOCK_LEGACY')
        self.assertNotIn('LANG_ACCESSIBILITY_AUTOLOCK_TIMEOUT', TOUCH_ROWS)

    def test_private_pcm_flag_never_enters_default_eight_session_worker(self):
        arguments = argparse.Namespace(keyclick_private=True)
        with mock.patch(__name__ + '.PrivateDesktop', side_effect=AssertionError('Must fail before native API')) as native:
            with self.assertRaisesRegex(AssertionError, 'separately reviewed central worker'):
                worker(arguments)
        native.assert_not_called()

    def test_private_pcm_option_is_separate_and_default_services_contract_is_unchanged(self):
        self.assertFalse(parser().parse_args(['--self-test']).keyclick_private)
        self.assertTrue(parser().parse_args(['--execute', '--keyclick-private']).keyclick_private)
        self.assertEqual(len(readiness()['sessions']), 8)

    def test_layout_case_fails_if_cancel_only_navigation_changes_private_profile(self):
        with self.assertRaisesRegex(AssertionError, "Read-only gesture menu navigation changed private config"):
            self.layout_case_fixture(private_changed=True)
        self.assertEqual(self.last_layout_reads, {"private": 5, "connectivity": 0, "autolock": 3})
        self.assertNotIn("gesture_menu_scope", self.last_layout_probe.report)
        self.assertNotIn("talkbox_hierarchy", self.last_layout_probe.report)
        self.assertFalse(any(call.args[0] == "LANG_CONNECTIVITY" for call in self.last_layout_probe.enter.call_args_list))

    def test_layout_case_rejects_physical_menu_changes_before_later_navigation(self):
        with self.assertRaisesRegex(AssertionError, "Read-only physical button menu navigation changed private config"):
            self.layout_case_fixture(buttons_changed=True)
        self.assertEqual(self.last_layout_reads, {"private": 2, "connectivity": 0, "autolock": 3})
        self.assertNotIn("physical_button_menu_scope", self.last_layout_probe.report)
        self.assertNotIn("talkbox_hierarchy", self.last_layout_probe.report)
        self.assertFalse(any(call.args[0] in ("LANG_DISPLAY", "LANG_VOICE", "LANG_CONNECTIVITY")
                             for call in self.last_layout_probe.enter.call_args_list))

    def test_empty_feedback_picker_restores_default_and_never_creates_private_configuration(self):
        probe = mock.Mock()
        probe.labels = {identifier: identifier for identifier in REQUIRED_IDS}
        probe.report = {}
        with mock.patch.object(Path, 'exists', return_value=False), \
             mock.patch.object(Path, 'write_bytes', side_effect=AssertionError('Harness cannot save preferences')), \
             mock.patch.object(Path, 'write_text', side_effect=AssertionError('Harness cannot save preferences')):
            browse_empty_feedback(probe, Path('synthetic'))
        self.assertEqual(probe.method_calls, [
            mock.call.enter('LANG_ACCESSIBILITY_EMPTY_FEEDBACK', (EMPTY_FEEDBACK_CHOICES[0],)),
            mock.call.cycle('Empty-place feedback choices', expected_order=EMPTY_FEEDBACK_CHOICES, key='Up'),
            mock.call.row('Confirm original sound-only empty feedback', 'Right',
                          ('LANG_ACCESSIBILITY_EMPTY_FEEDBACK', EMPTY_FEEDBACK_CHOICES[0])),
        ])
        self.assertIn('actual touch-feedback effect not established', probe.report['empty_feedback_picker_scope'])

    def test_empty_feedback_picker_rejects_existing_or_newly_saved_profile_and_temporary_file(self):
        for filename in ('empty-feedback.cfg', 'empty-feedback.cfg.tmp'):
            for existing in (True, False):
                probe = mock.Mock()
                probe.labels = {identifier: identifier for identifier in REQUIRED_IDS}
                probe.report = {}
                def exists(path):
                    return path.name == filename and (existing or probe.row.called)
                with self.subTest(filename=filename, existing=existing), \
                     mock.patch.object(Path, 'exists', autospec=True, side_effect=exists), self.assertRaises(AssertionError):
                    browse_empty_feedback(probe, Path('synthetic'))
                self.assertNotIn('empty_feedback_picker_scope', probe.report)
                if existing:
                    probe.enter.assert_not_called()

    def test_obsolete_shortcut_config_seeds_all_legacy_choices_without_affecting_mappings(self):
        choices = set()
        for scenario in ("services", "missing-voice", "layout-connectivity", "music"):
            with self.subTest(scenario=scenario):
                with mock.patch.object(Path, "exists", return_value=False), \
                     mock.patch.object(Path, "rglob", return_value=[]), mock.patch.object(Path, "write_bytes"), \
                     mock.patch(__name__ + ".write_json") as receipt:
                    configure_session(Path("runtime"), Path("evidence"), "polski", scenario)
                    profile = receipt.call_args.args[1]
                self.assertEqual(profile["accessibility.cfg"], session_mapping_profile(mapping_contract(), scenario))
                legacy = profile["accessibility-shortcut.cfg"].splitlines()
                self.assertEqual(legacy[0], "RBACCESSIBILITY-SHORTCUT:1")
                choices.add(tuple(legacy[1:]))
        self.assertEqual(choices, {(f"enabled:{enabled}", f"service:{service}")
                                  for enabled in (0, 1) for service in (0, 1)})

    def test_obsolete_shortcut_config_changes_and_removal_fail_before_evidence_moves(self):
        legacy = "simdisk/.rockbox/accessibility-shortcut.cfg"
        for after in ({legacy: "changed"}, {}):
            with self.subTest(after=after), mock.patch(__name__ + ".regular_files", return_value=after), \
                 mock.patch.object(Path, "rename") as rename, self.assertRaisesRegex(AssertionError, "Obsolete"):
                preserve_runtime_changes(Path("runtime"), Path("evidence"), {}, {legacy: "original"})
            rename.assert_not_called()

    def test_obsolete_shortcut_config_is_preserved_with_unchanged_bytes_in_session_evidence(self):
        legacy = "simdisk/.rockbox/accessibility-shortcut.cfg"
        runtime, evidence = Path("runtime"), Path("evidence")
        with mock.patch(__name__ + ".regular_files", return_value={legacy: "original"}), \
             mock.patch(__name__ + ".confined_path", side_effect=lambda path, root: path), \
             mock.patch(__name__ + ".digest", return_value="original"), \
             mock.patch.object(Path, "exists", return_value=False), mock.patch.object(Path, "mkdir"), \
             mock.patch.object(Path, "rename", autospec=True) as rename:
            preserve_runtime_changes(runtime, evidence, {}, {legacy: "original"})
        rename.assert_called_once_with(runtime / legacy, evidence / "runtime" / legacy)

    def test_status_requires_synthesis_and_rejects_auto_redraw(self):
        good = "TTS: eSpeak off\nTTS utterance: eSpeak off\n"
        validate_status(good, "eSpeak off")
        for text in ("TTS: eSpeak off\n", good + "TTS utterance: Settings\n", "TTS utterance: eSpeak on\n"):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                validate_status(text, "eSpeak off")

    def test_saved_flags_and_volume_parser(self):
        settings = parse_settings("# generated\ntts enabled: off\ntalk menu: off\ntalk mixer level: 0\n")
        self.assertEqual(settings["talk mixer level"], "0")
        with self.assertRaises(AssertionError):
            parse_settings("tts enabled: on\ntts enabled: off\n")

    def test_saved_defaults_omitted_by_changed_only_writer_are_resolved(self):
        settings = effective_settings("talk menu: off\ntalk mixer level: 0\n")
        self.assertEqual(settings, {"tts enabled": "on", "talk menu": "off",
                                   "talk mixer level": "0", "tts volume": "100"})

    def generated_settings(self, language="polski", extra=""):
        return (f"# .cfg file created by rockbox {EXPECTED_VERSION} - http://www.rockbox.org\n\n"
                f"volume: -25\ntalk mixer level: 0\nlang: /.rockbox/langs/{language}.lng\n" + extra)

    def settings_snapshot_fixture(self, pending, expected=None, seed=None, language="polski", fixed=False,
                                  missing=False):
        resources, report = Path("synthetic-settings"), {}
        expected = expected if expected is not None else {
            "tts enabled": "on", "talk menu": "on", "talk mixer level": "0", "tts volume": "100"}
        files = {} if missing else {resources / "config.cfg": (
            synthetic_config(language, False) if seed is None else seed).encode("utf-8")}
        if pending is not None:
            files[resources / "config.cfg.new"] = pending.encode("utf-8") if isinstance(pending, str) else pending
        if fixed:
            files[resources / "fixed.cfg"] = b"talk menu: off\n"
        with mock.patch.object(Path, "exists", autospec=True, side_effect=lambda path: path in files), \
             mock.patch.object(Path, "is_file", autospec=True, side_effect=lambda path: path in files), \
             mock.patch.object(Path, "read_bytes", autospec=True, side_effect=lambda path: files[path]):
            settings = saved_settings_snapshot(resources, language, expected, report)
        return settings, report["settings_snapshot"]

    def test_pending_snapshot_replaces_seed_and_resolves_omitted_default_on_flags(self):
        for language in LANGUAGES:
            for ending in ("\n", "\r\n"):
                text = self.generated_settings(language).replace("\n", ending)
                with self.subTest(language=language, ending=repr(ending)):
                    settings, receipt = self.settings_snapshot_fixture(text, language=language)
                    self.assertEqual(settings["talk menu"], "on")
                    self.assertEqual(settings["tts enabled"], "on")
                    self.assertEqual(settings["tts volume"], "100")
                    self.assertEqual(receipt["path"], str(Path("synthetic-settings/config.cfg.new")))
                    self.assertEqual(receipt["sha256"], hashlib.sha256(text.encode("utf-8")).hexdigest())
                    self.assertEqual(receipt["bytes"], len(text.encode("utf-8")))
                    self.assertTrue(receipt["pending_promotion"])
                    self.assertFalse(receipt["restart_verified"])
                    self.assertFalse(receipt["flash_durability_established"])

    def test_no_pending_snapshot_uses_existing_config_without_claiming_promotion(self):
        expected = {"tts enabled": "on", "talk menu": "off", "talk mixer level": "0", "tts volume": "100"}
        settings, receipt = self.settings_snapshot_fixture(None, expected)
        self.assertEqual(settings["talk menu"], "off")
        self.assertEqual(receipt["path"], str(Path("synthetic-settings/config.cfg")))
        self.assertFalse(receipt["pending_promotion"])

    def test_missing_saved_snapshot_cannot_pass_via_defaults(self):
        with self.assertRaisesRegex(AssertionError, "Missing saved config"):
            self.settings_snapshot_fixture(None, missing=True)
        with self.assertRaisesRegex(AssertionError, "Actual saved flags/volume"):
            self.settings_snapshot_fixture(None)

    def test_pending_empty_malformed_or_wrong_version_never_falls_back_to_valid_seed(self):
        valid = self.generated_settings()
        seed = synthetic_config("polski", True)
        for text in ("", "# generated\n", valid.split("\n\n")[0] + "\n\n",
                     valid.replace(EXPECTED_VERSION, "old-version"), seed, valid.rstrip("\n"),
                     valid + "malformed\n", valid + "tts enabled: on\ntts enabled: off\n",
                     valid + "unknown setting:\n", valid + ": value\n", b"\xff\n"):
            with self.subTest(text=repr(text)), self.assertRaises((AssertionError, UnicodeError)):
                self.settings_snapshot_fixture(text, seed=seed)

    def test_pending_snapshot_requires_all_nondefault_markers_with_correct_language(self):
        valid = self.generated_settings()
        for line in ("volume: -25\n", "talk mixer level: 0\n", "lang: /.rockbox/langs/polski.lng\n"):
            with self.subTest(missing=line), self.assertRaisesRegex(AssertionError, "profile markers"):
                self.settings_snapshot_fixture(valid.replace(line, ""))
        for text in (valid.replace("volume: -25", "volume: -24"), valid.replace("polski.lng", "english.lng"),
                     valid.replace("talk mixer level: 0", "talk mixer level: 100")):
            with self.subTest(text=text), self.assertRaisesRegex(AssertionError, "profile markers"):
                self.settings_snapshot_fixture(text)

    def test_explicit_pending_wrong_flags_or_gain_still_fail_saved_state_assertion(self):
        for line in ("talk menu: off\n", "tts enabled: off\n", "tts volume: 0\n"):
            with self.subTest(line=line), self.assertRaisesRegex(AssertionError, "Actual saved flags/volume"):
                self.settings_snapshot_fixture(self.generated_settings(extra=line),
                                               seed=synthetic_config("polski", True))
        expected = {"tts enabled": "off", "talk menu": "off", "talk mixer level": "0", "tts volume": "100"}
        settings, receipt = self.settings_snapshot_fixture(
            self.generated_settings(extra="tts enabled: off\ntalk menu: off\n"), expected)
        self.assertEqual(settings["tts enabled"], "off")
        self.assertTrue(receipt["pending_promotion"])

    def test_omitted_default_cannot_inherit_old_seed_off_value(self):
        with self.assertRaisesRegex(AssertionError, "Actual saved flags/volume"):
            self.settings_snapshot_fixture(self.generated_settings(), {"talk menu": "off"})

    def test_unexpected_fixed_config_cannot_override_either_selected_snapshot(self):
        for pending in (None, self.generated_settings()):
            with self.subTest(pending=pending is not None), self.assertRaisesRegex(AssertionError, "fixed.cfg"):
                self.settings_snapshot_fixture(pending, fixed=True)

    def test_fresh_session_rejects_pending_or_fixed_config_before_writing_profiles(self):
        for name in ("config.cfg.new", "fixed.cfg"):
            with self.subTest(name=name), \
                 mock.patch.object(Path, "exists", autospec=True, side_effect=lambda path: path.name == name), \
                 mock.patch.object(Path, "write_bytes") as write_profile, \
                 mock.patch(__name__ + ".write_json") as write_report:
                with self.assertRaisesRegex(AssertionError, "Fresh session contains unexpected " + re.escape(name)):
                    configure_session(Path("runtime"), Path("results"), "polski", "services")
                write_profile.assert_not_called()
                write_report.assert_not_called()

    def test_status_core_label_is_independent_of_voice_catalog_wording(self):
        text = "TTS: eSpeak disabled\nTTS utterance: eSpeak disabled\n"
        validate_status(text, "eSpeak disabled")
        with self.assertRaises(AssertionError):
            validate_status(text, "Pronunciation from the normal voice catalog")

    def test_synthetic_music_spectrum_measures_amplitude(self):
        tone = array.array("h", (int(1200 * math.sin(2 * math.pi * 997 * frame / 44100))
                                for frame in range(4096) for channel in range(2)))
        if sys.byteorder != "little":
            tone.byteswap()
        levels = tone_windows(tone.tobytes())
        self.assertEqual(len(levels), 2)
        self.assertTrue(all(1150 < level < 1250 for level in levels))

    def test_all_required_source_inputs_exist(self):
        self.assertEqual([name for name in SOURCE_PATHS if not (ROOT / name).is_file()], [])

    def test_input_refinements_scope_binds_current_gui_dependencies(self):
        self.assertEqual(SCOPE, "publication-position-20261021/services-gui")
        self.assertEqual(EXPECTED_VERSION, "0ed3734e5e-espeak-r34-hibyr1-win-alpha17-20261021")
        self.assertEqual(len(SOURCE_PATHS), len(set(SOURCE_PATHS)))
        self.assertTrue({
            "apps/accessibility_typing.c", "apps/accessibility_typing.h",
            "apps/accessibility_touch.c", "apps/accessibility_touch.h",
            "apps/accessibility_screen.c", "apps/accessibility_screen.h",
            "apps/menus/settings_menu.c", "apps/menus/display_menu.c", "apps/menus/exported_menus.h",
            "docs/ACCESSIBILITY-BUTTONS.md", "docs/ACCESSIBILITY-BUTTONS-PL.md",
        } <= set(SOURCE_PATHS))

    def test_connectivity_preferences_are_not_rf_evidence(self):
        for airplane in range(2):
            self.assertEqual(connectivity_preferences(
                f"RBCONNECTIVITY:1\nwifi:1\nbluetooth:1\nairplane:{airplane}\n".encode()), (1, 1, airplane))
        with self.assertRaises(AssertionError):
            connectivity_preferences(b"RBCONNECTIVITY:1\nwifi:1\nbluetooth:1\nairplane:2\n")

    def test_disabled_voice_file_profile_keeps_synthesis_volume(self):
        for language in LANGUAGES:
            settings = parse_settings(synthetic_config(language, False))
            self.assertEqual(settings["talk menu"], "off")
            self.assertEqual(settings["talk mixer level"], "0")
            self.assertEqual(settings["tts enabled"], "on")
            self.assertEqual(settings["tts volume"], "100")

    def test_pcm_rejects_partial_and_distinguishes_silence(self):
        self.assertEqual(pcm_statistics(b"\0" * 512)["nonzero_samples"], 0)
        self.assertEqual(pcm_statistics(b"\x01\0" * 256)["nonzero_samples"], 256)
        with self.assertRaises(AssertionError):
            pcm_statistics(b"\0")

    def test_pcm_evidence_rejects_logged_speech_without_audio(self):
        check = {"name": "Status", "pcm_start": 512, "pcm_end": 1024, "silent": False, "passed": True}
        with mock.patch.object(Path, "read_bytes", return_value=b"\1\0" * 256 + b"\0" * 512), self.assertRaises(AssertionError):
            verify_pcm(Path("unused"), {"music": False, "checks": [check]})

    def test_pcm_evidence_rejects_audio_in_an_ordinary_off_interval(self):
        check = {"name": "Silent navigation", "pcm_start": 0, "pcm_end": 512, "silent": True, "passed": True}
        with mock.patch.object(Path, "read_bytes", return_value=b"\1\0" * 256), self.assertRaises(AssertionError):
            verify_pcm(Path("unused"), {"music": False, "checks": [check]})

    def test_private_desktop_guard_rejects_input_desktop(self):
        desktop = object.__new__(PrivateDesktop)
        for current, active in (("Default", "Default"), ("Private", "Private")):
            with mock.patch.object(desktop, "current", return_value=current), \
                 mock.patch.object(desktop, "input", return_value=active), self.assertRaises(AssertionError):
                desktop.assert_private("Private")
        with mock.patch.object(desktop, "current", return_value="Private"), \
             mock.patch.object(desktop, "input", return_value="Default"):
            desktop.assert_private("Private")

    def test_no_forbidden_native_calls_or_legacy_central_imports(self):
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"SetForegroundWindow", "SetCursorPos", "SendInput", "SwitchDesktop", "SetThreadDesktop",
                     "keybd_event", "mouse_event", "AttachThreadInput", "WriteProcessMemory"}
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(calls & forbidden)
        self.assertNotIn("screen_gui_", " ".join(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)))

    def test_readiness_is_not_gui_acceptance(self):
        result = readiness()
        self.assertFalse(result["gui_ready"])
        self.assertFalse(result["simulator_launched"])
        self.assertEqual(len(result["sessions"]), 8)
        self.assertEqual(result["missing_source_ids"], {"english": [], "polski": []})
        self.assertTrue(set(TOUCH_ROWS + GESTURE_ROWS + GESTURE_ACTION_ROWS) <= set(result["required_compiled_ids"]))


class RapidNavigationTests(unittest.TestCase):
    def run_burst(self, **keywords):
        self.fixture = HarnessTests()
        return self.fixture.press_fixture(rapid=True, key_name=keywords.pop("key", "Up"),
                                          clicks=keywords.pop("clicks", 3), **keywords)

    def test_two_and_three_arrows_reuse_all_acknowledged_release_loops(self):
        for key in ("Up", "Down"):
            for clicks in (2, 3):
                with self.subTest(key=key, clicks=clicks):
                    probe = self.run_burst(key=key, clicks=clicks)
                    burst = probe.report["rapid_navigation_bursts"][0]
                    self.assertTrue(burst["passed"])
                    self.assertTrue(burst["timing_exercised"])
                    self.assertEqual(burst["press_acknowledgement_indices"], list(range(clicks)))
                    self.assertEqual(len(burst["down_ack_monotonic"]), clicks)
                    self.assertEqual([item["pressed"] for item in probe.report["raw_input"]], [True, False] * clicks)
                    for spacing in burst["down_ack_spacing_seconds"]:
                        self.assertAlmostEqual(spacing, 0.16)
                    self.assertTrue(all(record["passed"] and record["release_sent"] and
                        record["sampled_release_seconds"] < PRESS_MAX_DOWN for record in probe.report["press_acknowledgements"]))
                    probe.native.owns.assert_called()

    def test_rapid_method_rejects_unapproved_keys_counts_and_types_before_input(self):
        for key, clicks in (("Left", 2), ("Right", 3), ("Insert", 3), ("Up", 1), ("Down", 4),
                            ("Up", True), ("Up", 2.0), ("Down", "3"), ("Up", None)):
            with self.subTest(key=key, clicks=clicks), self.assertRaisesRegex(AssertionError, "exactly two or three"):
                self.run_burst(key=key, clicks=clicks)
            self.assertEqual(self.fixture.last_press_probe.report["raw_input"], [])

    def test_slow_acknowledgements_and_gap_at_200ms_cannot_pass_as_exercised(self):
        for keywords in (dict(gap_delay=0.04), dict(gap_delay=0.05), dict(delay=0.16)):
            with self.subTest(keywords=keywords), self.assertRaisesRegex(AssertionError, "timing not exercised"):
                self.run_burst(**keywords)
            burst = self.fixture.last_press_probe.report["rapid_navigation_bursts"][0]
            self.assertFalse(burst["passed"])
            self.assertFalse(burst["timing_exercised"])
            self.assertEqual(len(burst["down_ack_monotonic"]), 3)
            self.assertTrue(all(record["release_sent"] for record in self.fixture.last_press_probe.report["press_acknowledgements"]))

    def test_missing_or_stale_acks_prevent_more_input_and_keep_failure_receipt(self):
        for keywords, expected_inputs in ((dict(initial=16), []), (dict(missing_down=True), [True, False]),
                                         (dict(stuck_release=True), [True, False]), (dict(overshoot=True), [True, False])):
            with self.subTest(keywords=keywords), self.assertRaises(AssertionError):
                self.run_burst(**keywords)
            probe = self.fixture.last_press_probe
            self.assertEqual([item["pressed"] for item in probe.report["raw_input"]], expected_inputs)
            self.assertFalse(probe.report["rapid_navigation_bursts"][0]["passed"])

    def test_memory_and_release_errors_preserve_finally_release_and_original_error(self):
        for keywords, message in ((dict(read_error=True), "Owned memory read failed"),
                                  (dict(missing_down=True, release_error=True), "acknowledgement: down")):
            with self.subTest(keywords=keywords), self.assertRaisesRegex((AssertionError, OSError), message):
                self.run_burst(**keywords)
            record = self.fixture.last_press_probe.report["press_acknowledgements"][0]
            self.assertIn(message, record["error"])
            self.assertEqual([item["pressed"] for item in self.fixture.last_press_probe.report["raw_input"]], [True, False])

    def test_timing_validator_uses_sampled_down_times_and_rejects_missing_reordered_or_nonfinite_samples(self):
        records = self.run_burst(clicks=2).report["press_acknowledgements"]
        self.assertAlmostEqual(rapid_navigation_timing(records, "Up", 2, 16)["down_ack_spacing_seconds"][0], 0.16)
        for mutation in ("missing", "reordered", "nonfinite", "duplicate", "mask", "hold", "release"):
            changed = json.loads(json.dumps(records))
            if mutation == "missing":
                changed[0]["samples"] = [sample for sample in changed[0]["samples"] if sample["phase"] != "down"]
            elif mutation == "reordered":
                changed[0]["samples"].reverse()
            elif mutation == "nonfinite":
                changed[0]["samples"][1]["monotonic"] = float("nan")
            elif mutation == "duplicate":
                changed[0]["samples"].insert(2, dict(changed[0]["samples"][1]))
            elif mutation == "mask":
                changed[0]["mask"] = 32
            elif mutation == "hold":
                changed[0]["hold_seconds"] = PRESS_MAX_DOWN
            else:
                changed[0]["release_sent"] = False
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                rapid_navigation_timing(changed, "Up", 2, 16)

    def test_quantized_input_clock_fails_rapid_gate_without_reclassifying_press_receipts(self):
        with self.assertRaisesRegex(AssertionError, "complete bounded press/release acknowledgements"):
            self.run_burst(clock_read=lambda elapsed: math.floor(elapsed * 64) / 64)
        probe = self.fixture.last_press_probe
        records = probe.report["press_acknowledgements"]
        self.assertEqual(len(records), 3)
        self.assertAlmostEqual(records[0]["hold_seconds"], 0.078125)
        self.assertTrue(all(record["passed"] and record["release_sent"] for record in records))
        burst = probe.report["rapid_navigation_bursts"][0]
        self.assertFalse(burst["passed"])
        self.assertFalse(burst["timing_exercised"])

    def test_rapid_input_uses_high_resolution_clock_with_a_separate_monotonic_origin(self):
        with mock.patch.object(time, "monotonic",
                               side_effect=lambda: 1000000.0 + math.floor(time.perf_counter() * 64) / 64) as coarse_clock:
            probe = self.run_burst(clock_origin=16.0)
        coarse_clock.assert_not_called()
        self.assertTrue(probe.report["rapid_navigation_bursts"][0]["passed"])
        for record in probe.report["press_acknowledgements"]:
            self.assertAlmostEqual(record["hold_seconds"], 0.08)
            self.assertGreaterEqual(record["hold_seconds"], 0.08 - 1e-12)
            self.assertLess(record["sampled_release_seconds"], 0.28)
            self.assertTrue(all(16 <= sample["monotonic"] < 17 for sample in record["samples"]))
        self.assertTrue(all(16 <= event["monotonic"] < 17 for event in probe.report["raw_input"]))

    def test_chord_input_uses_the_same_high_resolution_timestamp_domain(self):
        fixture = HarnessTests()
        with mock.patch.object(time, "monotonic",
                               side_effect=lambda: 1000000.0 + math.floor(time.perf_counter() * 64) / 64) as coarse_clock:
            probe = fixture.chord_fixture(delay=0.01)
        coarse_clock.assert_not_called()
        record = probe.report["chord_acknowledgements"][0]
        self.assertTrue(record["passed"])
        self.assertTrue(all(0 <= sample["monotonic"] < 0.28 for sample in record["samples"]))
        self.assertTrue(all(0 <= event["monotonic"] < 0.28 for event in probe.report["raw_input"]))

    def test_high_resolution_clock_preserves_strict_hold_release_and_spacing_limits(self):
        records = self.run_burst(clicks=2).report["press_acknowledgements"]
        self.assertEqual((PRESS_ACK_TIMEOUT, PRESS_MAX_DOWN, RAPID_NAVIGATION_MAX_SPACING), (0.24, 0.28, 0.2))
        for hold in (0.078, 0.079999, 0.28, 0.281):
            changed = json.loads(json.dumps(records))
            changed[0]["hold_seconds"] = hold
            with self.subTest(hold=hold), self.assertRaises(AssertionError):
                rapid_navigation_timing(changed, "Up", 2, 16)
        for released in (0.079999, 0.28, 0.281):
            changed = json.loads(json.dumps(records))
            changed[0]["sampled_release_seconds"] = released
            with self.subTest(released=released), self.assertRaises(AssertionError):
                rapid_navigation_timing(changed, "Up", 2, 16)
        for spacing in (0, 0.2, 0.200001):
            changed = json.loads(json.dumps(records))
            for sample in changed[1]["samples"]:
                sample["monotonic"] += spacing - 0.16
            with self.subTest(spacing=spacing), self.assertRaises(AssertionError):
                rapid_navigation_timing(changed, "Up", 2, 16)

    def test_ordinary_press_still_refuses_triple_arrows_and_delegates_original_burst(self):
        for key in ("Up", "Down"):
            with self.subTest(key=key), self.assertRaisesRegex(AssertionError, "explicit triple-Power"):
                HarnessTests().press_fixture(key_name=key, clicks=3)
        probe = ServicesProbe.__new__(ServicesProbe)
        probe._press_sequence = mock.Mock()
        self.assertIsNone(probe.press("Up", clicks=2))
        probe._press_sequence.assert_called_once_with("Up", 0.08, 2)


def parser():
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", "--selftest", action="store_true")
    mode.add_argument("--readiness", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--build-ready", action="store_true")
    result.add_argument("--freeze", type=Path)
    result.add_argument("--freeze-sha256")
    result.add_argument("--exe-sha256")
    result.add_argument("--timeout", type=float, default=25)
    result.add_argument("--overall-timeout", type=float, default=9600)
    result.add_argument("--desktop", help=argparse.SUPPRESS)
    result.add_argument("--gate", type=int, help=argparse.SUPPRESS)
    result.add_argument("--results", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--input-layout-sha256", help=argparse.SUPPRESS)
    result.add_argument('--keyclick-private', action='store_true', help=argparse.SUPPRESS)
    return result


def main(argv=None):
    arguments = parser().parse_args(argv)
    require(10 <= arguments.timeout <= 60 and 60 <= arguments.overall_timeout <= 10800, "Invalid bounded timeout")
    if arguments.self_test:
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("Selftest cannot launch any process")), \
             mock.patch.object(ctypes, "WinDLL", create=True, side_effect=AssertionError("Selftest cannot load native APIs")):
            stream = io.StringIO()
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HarnessTests))
        report = {"scope": SCOPE, "mode": "self-test", "passed": result.wasSuccessful(), "tests": result.testsRun,
                  "output": stream.getvalue(), "simulator_launched": False, "gui_acceptance_complete": False,
                  "source_sha256": digest(Path(__file__)), "limitations": LIMITATIONS}
        directory = new_results("selftest")
        write_json(directory / "selftest.json", report)
        print(stream.getvalue() + "Selftest evidence: " + str(directory))
        return 0 if result.wasSuccessful() else 1
    if arguments.readiness:
        print(json.dumps(readiness(), indent=2, ensure_ascii=False))
        return 0
    return worker(arguments) if arguments.worker else execute(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
