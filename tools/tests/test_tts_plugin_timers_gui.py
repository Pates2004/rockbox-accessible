"""Native Windows GUI/PCM scenarios for the three shared timer plugins.

Only run after the parent grants the exact completed target build, for example:
  python -B tools/tests/test_tts_plugin_timers_gui.py --target sansaclipplus --language polski --build-ready
  python -B tools/tests/test_tts_plugin_timers_gui.py --target sansaclipzip --language english --build-ready

Repeat both languages on both targets. The shared utility-plugin runner owns
fixture copying, executable loans, HWND-scoped keys, complete session logs,
post-exit PCM checks and executable restoration. No user profile is imported.
Pass --voice-files-disabled to disable recorded menu/file/directory speech
and mute recorded voices while keeping eSpeak enabled in the clean fixture.
The alarm prerequisite is a real generated WAV played and paused through WPS,
not an injected playlist or fake clock. Its tone and paused silence are checked
after process exit; no hours-long wakeup or physical RTC test is attempted.
"""

import array
import datetime
import math
from pathlib import Path
import re
import sys
import time
import unittest
from unittest import mock
import wave

from test_tts_bookmarks_gui import tone_amplitude
from test_tts_plugins_gui import (
    contained, digest, logged_phrases, numeric_values, pcm_summary, require,
    run_suite, speech_matches,
)


ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ("countdown_timer", "chessclock", "alarmclock")
MUSIC = "004 Timer diagnostic.wav"
REQUIRED_LABELS = (
    "LANG_DIR_BROWSER", "LANG_COUNTDOWN_TIMER_SET", "LANG_COUNTDOWN_TIMER_RUNNING",
    "LANG_COUNTDOWN_TIMER_PAUSED", "LANG_COUNTDOWN_TIMER_FINISHED", "LANG_EDIT",
    "LANG_ALARMCLOCK", "LANG_ALARMCLOCK_ARMED", "LANG_ALARMCLOCK_WAKEUP",
    "LANG_NUMBER_OF_PLAYERS", "LANG_CHESSCLOCK_PLAYER", "LANG_CHESSCLOCK_TOTAL_TIME",
    "LANG_CHESSCLOCK_MAX_ROUND_TIME", "LANG_CHESSCLOCK_ROUND_TIME",
    "LANG_CHESSCLOCK_DELETE_PLAYER", "LANG_CHESSCLOCK_RESTART_ROUND",
    "LANG_CHESSCLOCK_SET_ROUND_TIME", "LANG_CHESSCLOCK_SET_TOTAL_TIME",
    "LANG_PLAYBACK_CONTROL", "VOICE_HOURS", "VOICE_MINUTES", "VOICE_MINUTE",
    "VOICE_SECONDS", "VOICE_SECOND",
)
SOURCE_INPUTS = (
    "apps/plugins/countdown_timer.c", "apps/plugins/chessclock.c",
    "apps/plugins/alarmclock.c", "apps/talk.c", "apps/keymaps/keymap-clip.c",
    "tools/tests/test_tts_plugin_timers_gui.py", "tools/tests/test_tts_bookmarks_gui.py",
)


def repeat_key(probe, key, count):
    require(0 <= count <= 24, "Unbounded timer setting key sequence")
    for count_index in range(count):
        probe.press(key)
        if count_index + 1 < count:
            time.sleep(0.05)


def require_initial_countdown_focus(observation, labels):
    for field in ("segments", "utterances"):
        phrases = observation[field]
        require(numeric_values(phrases).count("10") >= 2,
                "Initial countdown did not announce duration and selected minutes separately")
        require(" ".join(phrases).count(labels["VOICE_MINUTES"]) >= 2,
                "Initial countdown omitted its focused minutes field")


def countdown(probe, labels, activate):
    key = probe.keyboard
    initial = probe.speech("initial duration and minutes focus", activate,
                           fragments=(labels["LANG_COUNTDOWN_TIMER_SET"], labels["VOICE_MINUTES"]),
                           numbers=(10,), requirement="initial_focus")
    require_initial_countdown_focus(initial, labels)
    probe.speech("focus seconds", lambda: probe.press(key["BUTTON_RIGHT"]),
                 fragments=(labels["VOICE_SECONDS"],), numbers=(0,), requirement="functional_action")
    probe.speech("set one second", lambda: probe.press(key["BUTTON_UP"]),
                 fragments=(labels["VOICE_SECONDS"],), numbers=(1,), requirement="functional_action")
    probe.speech("start configured duration", activate,
                 fragments=(labels["LANG_COUNTDOWN_TIMER_RUNNING"], labels["VOICE_MINUTES"],
                            labels["VOICE_SECOND"]), numbers=(10, 1), requirement="functional_action")
    probe.quiet("countdown: running redraws do not restart speech", duration=1.3)
    probe.speech("pause countdown", activate,
                 fragments=(labels["LANG_COUNTDOWN_TIMER_PAUSED"],), requirement="functional_action")
    probe.quiet("countdown: paused redraws remain silent", duration=1.3)
    probe.speech("resume countdown", activate,
                 fragments=(labels["LANG_COUNTDOWN_TIMER_RUNNING"],), requirement="functional_action")
    probe.exit_to_root(labels)


def chess(probe, labels, activate):
    key = probe.keyboard
    probe.speech("initial player count", activate,
                 fragments=(labels["LANG_NUMBER_OF_PLAYERS"],), numbers=(1,), requirement="initial_focus")
    probe.speech("select two players", lambda: probe.press(key["BUTTON_RIGHT"]),
                 fragments=(labels["LANG_NUMBER_OF_PLAYERS"],), numbers=(2,), requirement="functional_action")
    probe.speech("enter total-time setting", activate,
                 fragments=(labels["LANG_CHESSCLOCK_TOTAL_TIME"], labels["VOICE_SECONDS"]), numbers=(10,))
    probe.speech("set two-minute total", lambda: repeat_key(probe, key["BUTTON_RIGHT"], 11),
                 fragments=(labels["LANG_CHESSCLOCK_TOTAL_TIME"], labels["VOICE_MINUTES"]),
                 numbers=(2,), requirement="functional_action")
    probe.speech("enter maximum-round setting", activate,
                 fragments=(labels["LANG_CHESSCLOCK_MAX_ROUND_TIME"], labels["VOICE_MINUTES"]), numbers=(2,))
    probe.speech("set one-minute round", lambda: repeat_key(probe, key["BUTTON_LEFT"], 6),
                 fragments=(labels["LANG_CHESSCLOCK_MAX_ROUND_TIME"], labels["VOICE_MINUTE"]),
                 numbers=(1,), requirement="functional_action")
    timer_fragments = (labels["LANG_CHESSCLOCK_PLAYER"], labels["LANG_COUNTDOWN_TIMER_PAUSED"],
                       labels["LANG_CHESSCLOCK_ROUND_TIME"], labels["LANG_CHESSCLOCK_TOTAL_TIME"])
    probe.speech("player one paused round and total", activate,
                 fragments=timer_fragments, numbers=(1, 2), requirement="functional_action")
    probe.speech("next turn selects player two", lambda: probe.press(key["BUTTON_RIGHT"]),
                 fragments=timer_fragments, numbers=(2,), requirement="functional_action")
    probe.speech("start player two", activate,
                 fragments=(labels["LANG_CHESSCLOCK_PLAYER"], labels["LANG_COUNTDOWN_TIMER_RUNNING"],
                            labels["LANG_CHESSCLOCK_ROUND_TIME"], labels["LANG_CHESSCLOCK_TOTAL_TIME"]),
                 numbers=(2,), requirement="functional_action")
    probe.speech("pause player two", activate,
                 fragments=timer_fragments, numbers=(2,), requirement="functional_action")
    probe.quiet("chessclock: paused redraws do not announce ticks", duration=1.3)
    menu_rows = ("LANG_CHESSCLOCK_DELETE_PLAYER", "LANG_CHESSCLOCK_RESTART_ROUND",
                 "LANG_CHESSCLOCK_SET_ROUND_TIME", "LANG_CHESSCLOCK_SET_TOTAL_TIME",
                 "LANG_PLAYBACK_CONTROL")
    probe.speech("open timer actions", lambda: probe.press(key["BUTTON_UP"]),
                 fragments=(labels[menu_rows[0]],), requirement="functional_action")
    for row in menu_rows[1:]:
        probe.speech(f"timer actions focus {row}", lambda: probe.press(key["BUTTON_DOWN"]),
                     fragments=(labels[row],), requirement="functional_action")
    probe.speech("cancel actions without changing player", lambda: probe.press(key["BUTTON_LEFT"]),
                 fragments=timer_fragments, numbers=(2,), requirement="functional_action")
    probe.exit_to_root(labels)


def diagnostic_music(probe):
    disk = contained(probe.log.parent / "simdisk", probe.log.parent)
    destination = disk / MUSIC
    require(not destination.exists(), "Refusing to replace an existing music fixture")
    tone = array.array("h", (int(6000 * math.sin(2 * math.pi * 997 * sample / 44100))
                              for sample in range(44100)))
    if sys.byteorder != "little":
        tone.byteswap()
    with wave.open(str(destination), "wb") as output:
        output.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        for second in range(60):
            output.writeframesraw(tone.tobytes())
    music = dict(path=str(destination), sha256=digest(destination), frequency_hz=997,
                 duration_seconds=60, creation="generated synthetic PCM WAV, no user files")
    probe.report.setdefault("timer_music", []).append(music)
    return music


def start_and_pause_music(probe, labels, music):
    key = probe.keyboard
    probe.seek(MUSIC.removesuffix(".wav"))
    probe.drain()
    before = probe.mark()
    probe.press(key["BUTTON_SELECT"])
    time.sleep(1.8)
    playing_end = probe.mark()
    probe.press(key["BUTTON_UP"])
    time.sleep(1.2)
    paused_start = probe.mark()
    quiet_started = time.monotonic()
    time.sleep(1.2)
    quiet_seconds = time.monotonic() - quiet_started
    paused_end = probe.mark()
    music.update(playing_pcm_start=before[1], playing_pcm_end=playing_end[1],
                  paused_pcm_start=paused_start[1], paused_pcm_end=paused_end[1],
                  paused_interval_seconds=quiet_seconds,
                  pcm_file=str(probe.pcm), status="pending_process_exit")
    probe.report["checks"].append(dict(
        name="alarmclock: real diagnostic music plays and WPS pause removes tone",
        plugin=probe.plugin, suite="plugin_timers", speech_required=False,
        status="pending_process_exit", requirement="real_music_prerequisite",
        music=music))
    probe.speech("return from paused WPS to menu", lambda: probe.press("Insert"))
    require("TTS audio playback: 1" in probe.text()[before[0]:],
            "No real resumable playback state was observed before entering alarm")
    probe.seek(labels["LANG_DIR_BROWSER"])
    probe.speech("reenter Files with paused resumable track", lambda: probe.press(key["BUTTON_SELECT"]))
    probe.seek(probe.report["aliases"][probe.plugin].removesuffix(".rock"))


def alarm(probe, labels, activate, music):
    key = probe.keyboard
    start_and_pause_music(probe, labels, music)
    probe.speech("initial alarm time and hour field", activate,
                 fragments=(labels["LANG_ALARMCLOCK"], labels["LANG_EDIT"], labels["VOICE_HOURS"]),
                 numbers=(0,), requirement="initial_focus")
    probe.speech("focus alarm minutes", lambda: probe.press(key["BUTTON_RIGHT"]),
                 fragments=(labels["VOICE_MINUTES"],), numbers=(0,), requirement="functional_action")
    probe.speech("edit alarm minute", lambda: probe.press(key["BUTTON_UP"]),
                 fragments=(labels["VOICE_MINUTES"],), numbers=(1,), requirement="functional_action")
    probe.speech("focus alarm hours", lambda: probe.press(key["BUTTON_LEFT"]),
                 fragments=(labels["VOICE_HOURS"],), numbers=(0,), requirement="functional_action")
    host_now = datetime.datetime.now()
    alarm_hour = (host_now.hour + 2) % 24
    probe.report["timer_alarm_schedule"] = dict(
        real_host_time=host_now.isoformat(), target_hour=alarm_hour, target_minute=1,
        purpose="choose a safely future time, then cancel; no clock injection or wakeup claim")
    if alarm_hour:
        probe.speech("set a safely future alarm hour", lambda: repeat_key(probe, key["BUTTON_UP"], alarm_hour),
                     fragments=(labels["VOICE_HOURS"],), numbers=(alarm_hour,), requirement="functional_action")
    probe.speech("arm alarm with selected real time", activate,
                 fragments=(labels["LANG_ALARMCLOCK_ARMED"],), numbers=(alarm_hour, 1),
                 requirement="functional_action")
    probe.quiet("alarmclock: armed refresh is silent", duration=1.3)
    probe.exit_to_root(labels)
    require(labels["LANG_ALARMCLOCK_WAKEUP"] not in " ".join(logged_phrases(probe.text())),
            "Alarm cancellation unexpectedly announced wakeup")
    probe.quiet("alarmclock: cancellation leaves no pending alarm voice", duration=1.3)


def exercise(probe, labels):
    first_check = len(probe.report["checks"])
    probe.pcm_attribution = "speech_only"
    probe.report["suite"] = "plugin_timers"
    if not probe.report.get("timer_limitations"):
        probe.report["timer_limitations"] = [
            "Countdown expiry and paused-music preservation are covered by the C harness, not this long-duration GUI run.",
            "Alarm wakeup, RTC accuracy, power-off wakeup and USB hardware are not tested or simulated.",
            "Chess clock tests its timer and menus, not the separate chessboard game.",
            "Diagnostic music is played and paused through WPS before alarm speech; PCM calibration is post-exit.",
            "PCM verifies mixer activity, not intelligibility, human listening, NVDA/UIA or device hardware.",
        ]
    keyboard_source = (ROOT / "uisimulator/buttonmap/sansa-clip.c").read_text(encoding="utf-8")
    require(re.search(r"case SDLK_INSERT:\s*case SDLK_KP_MULTIPLY:\s*new_btn = BUTTON_HOME;",
                      keyboard_source), "Unverified Insert-to-Home mapping for the music prerequisite")
    music = diagnostic_music(probe) if probe.plugin == "alarmclock" else None
    try:
        activate = probe.navigate_to_alias(labels)
        if probe.plugin == "countdown_timer":
            countdown(probe, labels, activate)
        elif probe.plugin == "chessclock":
            chess(probe, labels, activate)
        elif probe.plugin == "alarmclock":
            alarm(probe, labels, activate, music)
        else:
            raise AssertionError(f"Unexpected timer plugin: {probe.plugin}")
    finally:
        for check in probe.report["checks"][first_check:]:
            check.update(plugin=probe.plugin, suite="plugin_timers")
            if check.get("speech_required"):
                check["pcm_attribution_detail"] = (
                    "speech only; diagnostic track paused through WPS and checked after process exit"
                    if music else "speech only; no music or timer-expiry beep during this action")


def after_session(probe, session, results):
    for check in probe.report["checks"]:
        if check.get("plugin") != probe.plugin or check.get("requirement") != "real_music_prerequisite":
            continue
        music = check["music"]
        try:
            path = contained(Path(music["pcm_file"]), results)
            require(digest(Path(music["path"])) == music["sha256"], "Diagnostic WAV changed during test")
            playing = tone_amplitude(path, music["playing_pcm_start"], music["playing_pcm_end"])
            paused = pcm_summary(path, music["paused_pcm_start"], music["paused_pcm_end"])
            paused_tone = tone_amplitude(path, music["paused_pcm_start"], music["paused_pcm_end"])
            require(playing >= 20, "Real playback did not produce the diagnostic tone")
            require(music["paused_interval_seconds"] >= 1 and
                    paused["peak"] < 64 and paused_tone < 5,
                    "Music was not silent after the real WPS pause action; alarm PCM attribution is unsafe")
            check.update(status="passed", playing_tone_amplitude=playing,
                         paused_tone_amplitude=paused_tone, paused_pcm=paused,
                         paused_device_idle=paused["bytes"] == 0)
            music["status"] = "passed"
        except Exception as error:
            check.update(status="failed", error=f"{type(error).__name__}: {error}")
            music["status"] = "failed"
            raise


def main(argv=None):
    return run_suite(plugins=PLUGINS, exercise=exercise, required_labels=REQUIRED_LABELS,
                     argv=argv, extra_sources=SOURCE_INPUTS, after_session=after_session)


class TimerGuiHelperTests(unittest.TestCase):
    def test_initial_focus_must_include_field_after_duration(self):
        labels = {"VOICE_MINUTES": "minutes"}
        complete = {"segments": ["Set timer", "10", "minutes", "minutes", "10"],
                    "utterances": ["Set timer 10 minutes minutes 10"]}
        require_initial_countdown_focus(complete, labels)
        missing = {"segments": ["Set timer", "10", "minutes"],
                   "utterances": ["Set timer 10 minutes"]}
        with self.assertRaisesRegex(AssertionError, "duration and selected minutes"):
            require_initial_countdown_focus(missing, labels)

    def test_repeat_keys_are_bounded_and_hwnd_driver_scoped(self):
        probe = mock.Mock()
        with mock.patch("test_tts_plugin_timers_gui.time.sleep"):
            repeat_key(probe, "Right", 11)
        self.assertEqual(probe.press.call_args_list, [mock.call("Right")] * 11)
        with self.assertRaisesRegex(AssertionError, "Unbounded"):
            repeat_key(probe, "Right", 25)
        self.assertEqual(probe.press.call_count, 11)

    def test_suite_delegates_to_shared_framework_without_launching(self):
        command = ["--target", "sansaclipzip", "--language", "english", "--voice-files-disabled"]
        with mock.patch("test_tts_plugin_timers_gui.run_suite", return_value=0) as runner:
            self.assertEqual(main(command), 0)
        arguments = runner.call_args.kwargs
        self.assertEqual(arguments["argv"], command)
        self.assertEqual(arguments["plugins"], PLUGINS)
        self.assertIs(arguments["exercise"], exercise)
        self.assertIs(arguments["after_session"], after_session)
        self.assertIn("apps/talk.c", arguments["extra_sources"])


if __name__ == "__main__":
    raise SystemExit(main())
