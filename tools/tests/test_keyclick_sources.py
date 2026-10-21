"""Compile the real shared keyclick implementation and exercise input routing."""

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
PREAMBLE = r"""
#include <stdbool.h>
#include <stdlib.h>
#define BUTTON_NONE 0
#define BUTTON_REL 0x10000
#define BUTTON_REPEAT 0x20000
#define BUTTON_TOUCHSCREEN 0x100
#define BUTTON_MULTIMEDIA 0x40000
#define SYS_EVENT 0x80000
#define SOUND_KEYCLICK 1
#define ACTION_NONE 0
#define ACTION_TOUCHSCREEN 999
#define ACTION_UNKNOWN 1000
#define ACTION_WPS_STOPSEEK 1001
#define KEYCLICK_SOURCE_PHYSICAL 1
#define KEYCLICK_SOURCE_GESTURE 2
#define KEYCLICK_SOURCE_NONE 0
#define KEYCLICK_SOURCE_EXPLORATION 4
#define KEYCLICK_DURATION 2
typedef bool (*keyclick_callback)(int action, void *data);
static struct { int keyclick; bool keyclick_repeats, keyclick_hardware; } global_settings;
static unsigned int sources = 3;
static bool accessible = true;
static int sounds, piezo, strength, status_button, callbacks, callback_action;
static unsigned int last_frequency, last_duration, last_amplitude;
static int empty_pitch = -4;
static bool empty_sound = true;
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
static unsigned int accessibility_keyclick_sources(void) { return sources; }
static bool accessibility_enabled(void) { return accessible; }
static int accessibility_keyclick_empty_pitch(void) { return empty_pitch; }
static bool accessibility_empty_sound_enabled(void) { return empty_sound; }
#endif
static void beep_play(unsigned int frequency, unsigned int duration, unsigned int amplitude)
{ ++sounds; last_frequency = frequency; last_duration = duration; last_amplitude = amplitude; }
static void get_action_statuscode(int *button) { *button = status_button; }
static void system_sound_play(int sound) { if (sound == SOUND_KEYCLICK) ++sounds; strength = global_settings.keyclick; }
#if defined(HAVE_HARDWARE_CLICK) && !defined(SIMULATOR)
static void piezo_button_beep(bool force, bool blocking) { (void)force; (void)blocking; ++piezo; }
#endif
static bool veto(int action, void *data) { ++callbacks; callback_action = action; return data != NULL; }
static bool reject_none(int action, void *data) { (void)data; return action != ACTION_NONE; }
#define CHECK(condition) do { if (!(condition)) return __LINE__; } while (0)
"""
CASES = r"""
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    int scenario = atoi(argv[1]);
    (void)accessible;
    (void)empty_pitch;
    (void)empty_sound;
    global_settings.keyclick = 2;
    if (scenario == 0)
    {
        for (sources = 0; sources <= 7; ++sources)
        {
            sounds = 0;
            keyclick_click(true, 1);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
            CHECK(sounds == ((sources & 1) != 0));
            sounds = 0;
            keyclick_click_gesture(7);
            CHECK(sounds == ((sources & 2) != 0));
#else
            CHECK(sounds == 1);
            keyclick_click_gesture(7);
            CHECK(sounds == 1);
#endif
        }
    }
    else if (scenario == 1)
    {
        keyclick_click(true, BUTTON_TOUCHSCREEN);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
        CHECK(sounds == 0);
        keyclick_click_gesture(0);
        CHECK(sounds == 1);
        accessible = false;
        keyclick_click(true, BUTTON_TOUCHSCREEN);
        CHECK(sounds == 2);
#else
        CHECK(sounds == 1);
#endif
    }
    else if (scenario == 2)
    {
        global_settings.keyclick = 0;
        keyclick_click(true, 1);
        keyclick_click_gesture(8);
        CHECK(sounds == 0 && piezo == 0);
        global_settings.keyclick = 3;
        keyclick_click(true, 1);
        CHECK(sounds == 1 && strength == 3);
    }
    else if (scenario == 3)
    {
        keyclick_set_callback(veto, NULL);
        status_button = 1;
        keyclick_click(false, 42);
        CHECK(sounds == 0 && callbacks == 1 && callback_action == 42);
        keyclick_click(false, 42);
        CHECK(sounds == 1 && callbacks == 1);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
        keyclick_set_callback(veto, NULL);
        keyclick_click_gesture(51);
        CHECK(sounds == 1 && callbacks == 2 && callback_action == 51);
        keyclick_click_gesture(51);
        CHECK(sounds == 2 && callbacks == 2);
#endif
    }
    else if (scenario == 4)
    {
        keyclick_click(true, 1);
        keyclick_click(true, 1 | BUTTON_REPEAT);
        keyclick_click(true, 1 | BUTTON_REPEAT);
        CHECK(sounds == 2);
        global_settings.keyclick_repeats = true;
        keyclick_click(true, 1 | BUTTON_REPEAT);
        CHECK(sounds == 3);
    }
    else if (scenario == 5)
    {
        keyclick_click(true, BUTTON_NONE);
        keyclick_click(true, 1 | BUTTON_REL);
        keyclick_click(true, SYS_EVENT | 1);
        keyclick_click(true, BUTTON_MULTIMEDIA | 1);
        CHECK(sounds == 0);
    }
    else if (scenario == 6)
    {
#ifdef HAVE_HARDWARE_CLICK
        global_settings.keyclick = 0;
        global_settings.keyclick_hardware = true;
        keyclick_click(true, 1);
#if !defined(SIMULATOR)
        CHECK(piezo == 1 && sounds == 0);
#else
        CHECK(piezo == 0 && sounds == 0);
#endif
        keyclick_click_gesture(9);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK) && !defined(SIMULATOR)
        CHECK(piezo == 2 && sounds == 0);
#endif
#endif
    }
    else if (scenario == 7)
    {
        for (sources = 1; sources <= 3; ++sources)
        {
            sounds = 0;
            keyclick_click_physical(7, false);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
            CHECK(sounds == ((sources & 1) != 0));
#else
            CHECK(sounds == 1);
#endif
        }
        sources = 3;
        sounds = 0;
        keyclick_click_physical(7, true);
        CHECK(sounds == 0);
        global_settings.keyclick_repeats = true;
        keyclick_click_physical(7, true);
        CHECK(sounds == 1);
    }
    else if (scenario == 8)
    {
        status_button = 1;
        keyclick_click(false, ACTION_NONE);
#ifdef HIBY_R1
        CHECK(sounds == 0);
#else
        CHECK(sounds == 1);
#endif
        sounds = 0;
        status_button = 1 | BUTTON_REL;
        keyclick_click(false, 42);
#ifdef HIBY_R1
        CHECK(sounds == 1);
        keyclick_click(false, ACTION_UNKNOWN);
        keyclick_click(false, ACTION_WPS_STOPSEEK);
        CHECK(sounds == 1);
        status_button = 1 | BUTTON_REPEAT;
        keyclick_click(false, 42);
        CHECK(sounds == 2);
        keyclick_click(false, 42);
        CHECK(sounds == 2);
        global_settings.keyclick_repeats = true;
        keyclick_click(false, 42);
        CHECK(sounds == 3);
        keyclick_set_callback(veto, NULL);
        status_button = 1 | BUTTON_REL;
        keyclick_click(false, 42);
        CHECK(sounds == 3 && callbacks == 1);
#else
        CHECK(sounds == 0);
#endif
    }
    else if (scenario == 9)
    {
        keyclick_set_callback(reject_none, NULL);
        keyclick_click_physical(ACTION_NONE, false);
        CHECK(sounds == 1);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
        keyclick_set_callback(reject_none, NULL);
        keyclick_click_gesture(ACTION_NONE);
        CHECK(sounds == 2);
        keyclick_set_callback(veto, NULL);
        keyclick_click_gesture(ACTION_NONE);
        CHECK(sounds == 2 && callbacks == 1 && callback_action == ACTION_TOUCHSCREEN);
#else
        (void)reject_none;
#endif
    }
    else if (scenario == 10)
    {
        for (sources = 0; sources <= 7; ++sources)
        {
            sounds = 0;
            keyclick_click_exploration(false);
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
            CHECK(sounds == ((sources & 4) != 0));
            if (sounds)
                CHECK(last_frequency == 3175 && last_duration == 2 && last_amplitude == 5000);
            sounds = 0;
            keyclick_click_touch_target(false, true);
            CHECK(sounds == ((sources & 4) != 0));
            sounds = 0;
            keyclick_click_touch_target(true, true);
            CHECK(sounds == ((sources & 6) != 0));
#else
            CHECK(sounds == 0);
            keyclick_click_touch_target(false, true);
            CHECK(sounds == 0);
#endif
        }
    }
    else if (scenario == 11)
    {
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
        sources = 7;
        keyclick_set_callback(veto, NULL);
        keyclick_click_exploration(false);
        CHECK(sounds == 0 && callbacks == 1);
        for (empty_pitch = -12; empty_pitch <= 12; ++empty_pitch)
        {
            int before = sounds;
            keyclick_click_exploration(false);
            CHECK(sounds == before + 1);
        }
        keyclick_click_exploration(true);
        CHECK(strength == 2);
        global_settings.keyclick = 0;
        int before = sounds;
        keyclick_click_exploration(false);
        CHECK(sounds == before);
#endif
    }
    else if (scenario == 12)
    {
#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)
        empty_sound = false;
        sources = 7;
        keyclick_set_callback(veto, NULL);
        keyclick_click_touch_target(false, true);
        CHECK(sounds == 0 && piezo == 0 && callbacks == 0);
        keyclick_click_exploration(true);
        CHECK(sounds == 1 && callbacks == 0);
        keyclick_click_physical(ACTION_NONE, false);
        CHECK(sounds == 2);
        keyclick_click_gesture(ACTION_NONE);
        CHECK(sounds == 3);
#endif
    }
    else return 2;
    return 0;
}
"""


class KeyclickSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which(shlex.split(os.environ.get("CC", "cc"))[0]):
            raise unittest.SkipTest("C compiler unavailable; run compiled tests under WSL")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = project_materials_root(ROOT) / "r1-empty-radio-20261017" / "empty-feedback" / "keyclick-tests" / stamp
        cls.workspace.mkdir(parents=True)
        source = (ROOT / "apps/misc.c").read_text(encoding="utf-8")
        start = source.index("static keyclick_callback keyclick_current_callback")
        end = source.index("/* Return the ReplayGain mode", start)
        harness = cls.workspace / "keyclick.c"
        cls.harness_text = PREAMBLE + source[start:end] + CASES
        harness.write_text(cls.harness_text, encoding="utf-8")
        configurations = {
            "touch": ["HAVE_TOUCHSCREEN", "HAVE_ESPEAK"],
            "hibyr1": ["HIBY_R1", "HAVE_TOUCHSCREEN", "HAVE_ESPEAK"],
            "legacy": [],
            "touch_without_espeak": ["HAVE_TOUCHSCREEN"],
            "hardware": ["HAVE_TOUCHSCREEN", "HAVE_ESPEAK", "HAVE_HARDWARE_CLICK"],
            "hardware_simulator": ["HAVE_TOUCHSCREEN", "HAVE_ESPEAK", "HAVE_HARDWARE_CLICK", "SIMULATOR"],
        }
        cls.executables = {}
        for name, defines in configurations.items():
            executable = cls.workspace / (name + (".exe" if os.name == "nt" else ""))
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                "-fno-sanitize-recover=all", *["-D" + value for value in defines],
                str(harness), "-o", str(executable),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            cls.executables[name] = executable
        (cls.workspace / "source.json").write_text(json.dumps({
            "misc_sha256": hashlib.sha256((ROOT / "apps/misc.c").read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
            "configurations": configurations,
        }, indent=2), encoding="utf-8")

    def check_scenario(self, scenario):
        for name, executable in self.executables.items():
            with self.subTest(configuration=name):
                result = subprocess.run([str(executable), str(scenario)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_each_source_and_both(self):
        self.check_scenario(0)

    def test_touch_exploration_has_no_raw_click_duplicate(self):
        self.check_scenario(1)

    def test_off_and_strength(self):
        self.check_scenario(2)

    def test_callbacks_remain_one_shot_and_receive_action(self):
        self.check_scenario(3)

    def test_existing_repeat_setting(self):
        self.check_scenario(4)

    def test_release_and_system_events_are_silent(self):
        self.check_scenario(5)

    def test_hardware_feedback_and_simulator_guards(self):
        self.check_scenario(6)

    def test_delayed_physical_actions_respect_source_and_repeat_settings(self):
        self.check_scenario(7)

    def test_release_based_actions_click_once_without_legacy_changes(self):
        self.check_scenario(8)

    def test_consumed_semantic_actions_are_not_mistaken_for_idle_input(self):
        self.check_scenario(9)

    def test_all_eight_source_subsets_and_single_tap_deduplication(self):
        self.check_scenario(10)

    def test_empty_pitch_occupied_sound_strength_off_and_callback(self):
        self.check_scenario(11)

    def test_speech_only_empty_feedback_keeps_occupied_and_other_sources(self):
        self.check_scenario(12)

    def test_regression_detects_missing_gesture_scope_filter(self):
        self.check_mutation("gesture-scope", "keyclick_source_enabled(KEYCLICK_SOURCE_GESTURE)", "true", 0)

    def test_regression_detects_raw_touch_click_duplicates(self):
        self.check_mutation("raw-touch", "if ((button & BUTTON_TOUCHSCREEN) && accessibility_enabled())",
                            "if (false && (button & BUTTON_TOUCHSCREEN) && accessibility_enabled())", 1)

    def check_mutation(self, name, original, replacement, scenario):
        self.assertEqual(self.harness_text.count(original), 1)
        harness = self.workspace / (name + ".c")
        harness.write_text(self.harness_text.replace(original, replacement), encoding="utf-8")
        executable = self.workspace / (name + (".exe" if os.name == "nt" else ""))
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c11", "-Wall", "-Wextra", "-Werror", "-DHAVE_TOUCHSCREEN", "-DHAVE_ESPEAK",
            str(harness), "-o", str(executable),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([str(executable), str(scenario)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, "Regression test accepted the defective implementation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
