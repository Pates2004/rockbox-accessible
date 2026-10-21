"""Windows UI/PCM regression for six spoken list/text plugins on both Sansas.

Do not launch until the parent explicitly releases this exact target build:
  python -B tools/tests/test_tts_plugin_lists_gui.py --target sansaclipplus --language polski --build-ready
  python -B tools/tests/test_tts_plugin_lists_gui.py --target sansaclipzip --language english --build-ready

Repeat both languages for both targets. --self-test checks synthetic data and
oracles without opening a GUI, borrowing an EXE or inspecting an active build.
--voice-files-disabled keeps eSpeak on while disabling recorded menu/file/
directory speech and muting recorded voices in the clean fixture.
The utility GUI framework, resource copier, process ownership checks, PCM checks
and move/restore EXE loan are reused without modifying their implementation.
All profiles and plugin data are synthetic. Retained immutable resource copies
and root plugin aliases are intentional diagnostic copies, not new releases.
Speech completion is observed through validated read-only process symbols;
no process memory, production source or development profile is modified.
Disk PCM is not a human listening, NVDA/UIA, WASAPI or physical-device test.
"""

import argparse
from contextlib import redirect_stderr
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import sys
import time
import wave
from unittest.mock import patch

from test_tts_plugins_gui import (
    PluginDriver, close_session, logged_phrases, numeric_values,
    prepare_plugins_fixture, require, requirements_complete, synthetic_config,
    verify_pcm_checks, write_json,
)
from test_tts_recorder_gui import (
    ExecutableLoan, RecorderMemoryProbe, TARGETS, contained, digest,
    display_labels, prepare_memory_diagnostics,
)
from test_tts_simulator import find_window, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ("text_editor", "dict", "stats", "calendar", "shortcuts_view",
           "random_folder_advance_config")
MONTHS = tuple("LANG_MONTH_" + month for month in (
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
    "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"))
STAT_LABELS = (
    "LANG_PROPERTIES_FILES", "LANG_PROPERTIES_SIZE", "LANG_TRACKS", "LANG_PLAYLISTS",
    "LANG_PLUGIN_STATS_IMAGES", "LANG_PLUGIN_STATS_VIDEOS", "LANG_PROPERTIES_SUBDIRS",
    "LANG_PLUGIN_STATS_MAX_FILES",
)
SIZE_LABELS = ("LANG_BYTE", "LANG_KIBIBYTE", "LANG_MEBIBYTE", "LANG_GIBIBYTE")
REQUIRED_LABELS = STAT_LABELS + SIZE_LABELS + MONTHS + ("LANG_DELETED",)
SOURCE_INPUTS = (
    "apps/plugins/text_editor.c", "apps/plugins/dict.c", "apps/plugins/stats.c",
    "apps/plugins/calendar.c", "apps/plugins/shortcuts/shortcuts_view.c",
    "apps/plugins/shortcuts/shortcuts_common.c", "apps/plugins/shortcuts/shortcuts.h",
    "apps/plugins/random_folder_advance_config.c", "apps/plugins/lib/mul_id3.c",
    "apps/keymaps/keymap-clip.c", "uisimulator/buttonmap/sansa-clip.c",
    "apps/filetypes.c", "apps/filetree.c", "apps/tts.c", "apps/talk.c",
    "apps/voice_thread.c", "apps/recorder/keyboard.c",
    "tools/tests/test_tts_plugins_gui.py", "tools/tests/test_tts_recorder_gui.py",
    "tools/tests/test_tts_simulator.py", "tools/tests/test_tts_plugin_lists_gui.py",
)
TEXT = {
    "english": {
        "start": "Editor start ", "middle": " Editor middle ", "end": " Editor end",
        "unit": " accessible naïve € 🙂 words ",
        "second": "Second editor line", "third": "Third editor line",
        "definition": "Definition start. A dictionary explains a selected word in readable pieces. ",
        "definition_unit": "Useful descriptions include naïve words, € symbols and clear navigation. ",
        "event_first": "First calendar event", "event_second": "Second calendar event",
        "shortcut_first": "First shortcut", "shortcut_second": "Second shortcut",
    },
    "polski": {
        "start": "Początek edytora ", "middle": " Środek edytora ", "end": " Koniec edytora",
        "unit": " dostępny żółw € 🙂 słowa ",
        "second": "Drugi wiersz edytora", "third": "Trzeci wiersz edytora",
        "definition": "Początek definicji. Słownik wyjaśnia wybrane słowo w czytelnych fragmentach. ",
        "definition_unit": "Przydatne opisy zawierają polskie słowa, symbole € i wygodną nawigację. ",
        "event_first": "Pierwsze wydarzenie", "event_second": "Drugie wydarzenie",
        "shortcut_first": "Pierwszy skrót", "shortcut_second": "Drugi skrót",
    },
}


def fill_bytes(unit, length):
    result = unit * (length // len(unit.encode("utf-8")))
    for character in unit:
        if len(result.encode("utf-8")) + len(character.encode("utf-8")) > length:
            break
        result += character
    return result + " " * (length - len(result.encode("utf-8")))


def editor_line(language):
    words = TEXT[language]
    first = words["start"] + fill_bytes(words["unit"], 900 - len(words["start"].encode("utf-8")))
    remaining = 2047 - len((first + words["middle"] + words["end"]).encode("utf-8"))
    result = first + words["middle"] + fill_bytes(words["unit"], remaining) + words["end"]
    require(len(result.encode("utf-8")) == 2047 and "\n" not in result, "Invalid long editor fixture")
    return result


def utf8_chunks(text, maximum=768):
    payload = text.encode("utf-8")
    result = []
    while payload:
        length = min(maximum, len(payload))
        while length < len(payload) and payload[length] & 0xc0 == 0x80:
            length -= 1
        require(length > 0, "Chunk cannot fit one UTF-8 codepoint")
        result.append(payload[:length].decode("utf-8"))
        payload = payload[length:]
    return result


def definition_rows(text):
    payload = text.encode("utf-8").strip()
    rows = []
    while payload:
        length = min(180, len(payload))
        if length < len(payload):
            while payload[length] & 0xc0 == 0x80:
                length -= 1
            space = payload.rfind(b" ", 0, length + 1)
            if space > 0:
                length = space
        require(length > 0, "Empty dictionary fixture row")
        rows.append(payload[:length].decode("utf-8").rstrip())
        payload = payload[length:].lstrip()
    return rows


def verify_editor_observation(observation, expected):
    chunks = utf8_chunks(expected)
    require(observation["segments"] == chunks,
            "Editor did not submit every UTF-8 byte exactly once in bounded, ordered chunks")
    spoken = re.sub(r"\s+", "", "".join(observation["utterances"]))
    require(spoken == re.sub(r"\s+", "", expected),
            "Editor synthesis lost, repeated or reordered long-line content")
    observation["long_line"] = {
        "utf8_bytes": len(expected.encode("utf-8")),
        "sha256": hashlib.sha256(expected.encode("utf-8")).hexdigest(),
        "input_chunk_bytes": [len(chunk.encode("utf-8")) for chunk in chunks],
        "complete_ordered_synthesis": True,
        "whitespace_policy": "Engine coalescing may insert whitespace at chunk boundaries",
    }


def add_fixture_files(disk, language, report, today=None):
    today = today or datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    words = TEXT[language]
    generated = report.setdefault("generated_fixtures", [])

    def write(relative, payload):
        path = disk / relative
        require(not os.path.lexists(path) and disk.resolve() in path.resolve().parents,
                f"Refusing occupied or escaping generated fixture: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        generated.append({"path": str(path), "bytes": len(payload), "sha256": digest(path),
                          "purpose": "Synthetic plugin GUI input; no user data", "retained_after_test": True})

    long_line = editor_line(language)
    editor = "000 editor.ted"
    write(editor, (long_line + "\n" + words["second"] + "\n" + words["third"] + "\n").encode("utf-8"))
    write(".rockbox/plugin-lists.kbd", b"aa\n")
    definition = words["definition"] + words["definition_unit"] * 7
    dictionary_prefix = b"Unused dictionary fixture entry.\n"
    write(".rockbox/rocks/apps/dict.index", b"a" + bytes(31) + struct.pack(">I", len(dictionary_prefix)))
    write(".rockbox/rocks/apps/dict.desc", dictionary_prefix + (definition + "\n").encode("utf-8"))
    memo_prefix = tomorrow.strftime("%d%m%Y") + str(tomorrow.weekday()) + "3"
    write(".rockbox/rocks/apps/.memo", (memo_prefix + words["event_first"] + "\n" +
                                        memo_prefix + words["event_second"] + "\n").encode("utf-8"))
    paths = ("/FixtureData/alpha", "/FixtureData/alphabet", "/FixtureData/alpha/child")
    for path in paths:
        (disk / path.lstrip("/")).mkdir(parents=True, exist_ok=True)
    folder_data = struct.pack("<i", len(paths)) + b"".join(
        path.encode("utf-8").ljust(260, b"\0") for path in paths)
    write(".rockbox/folder_advance_list.dat", folder_data)
    shortcuts = "".join(path + "/\t" + words[label] + "\n" for path, label in (
        (paths[0], "shortcut_first"), (paths[1], "shortcut_second")))
    write("shortcuts.link", shortcuts.encode("utf-8"))
    write("FixtureData/sample.m3u8", b"#EXTM3U\n/FixtureData/sample.wav\n")
    write("FixtureData/sample.mpg", b"Synthetic extension classification fixture; never played.\n")
    wave_path = disk / "FixtureData/sample.wav"
    with wave.open(str(wave_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(bytes(1600))
    generated.append({"path": str(wave_path), "bytes": wave_path.stat().st_size, "sha256": digest(wave_path),
                      "purpose": "Synthetic silent WAV for extension statistics; never played",
                      "retained_after_test": True})
    fixtures = {"editor": editor, "long_line": long_line, "definition_rows": definition_rows(definition),
                "dictionary_offset": len(dictionary_prefix),
                "calendar_today": today.isoformat(), "calendar_tomorrow": tomorrow.isoformat(),
                "paths": paths, "shortcuts_initial": shortcuts, "folder_initial_sha256": digest(
                    disk / ".rockbox/folder_advance_list.dat")}
    report["plugin_fixtures"] = fixtures
    return fixtures


def install_editor_viewer(disk, report):
    viewers = disk / ".rockbox/viewers.config"
    before = viewers.read_bytes()
    require(not re.search(rb"(?m)^\s*ted\s*,", before), "Custom ted fixture extension is already assigned")
    viewers.write_bytes(before.rstrip(b"\r\n") + b"\nted,apps/text_editor,11\n")
    report.setdefault("fixture_mutations", []).append({
        "path": str(viewers), "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": digest(viewers),
        "purpose": "Isolated ted viewer passes file parameter to editor, not the core TXT reader",
    })


def inventory(disk):
    result = []
    for path in sorted(disk.rglob("*")):
        require(not path.is_symlink() and not getattr(path.lstat(), "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
                "Statistics fixture must not follow symlinks or reparse points")
        result.append({"path": path.relative_to(disk).as_posix(), "directory": path.is_dir(),
                       "bytes": path.stat().st_size if path.is_file() else 0})
    return result


def expected_statistics(entries, filetype_source):
    audio = re.search(r"inbuilt_audio_filetypes\[\]\s*=\s*\{(.*?)\};", filetype_source, re.DOTALL)
    require(audio is not None, "Cannot resolve source audio extensions")
    audio_extensions = set(re.findall(r'"([a-z0-9]+)"', audio.group(1)))
    playlists = set(re.findall(r'\{\s*"([a-z0-9]+)"\s*,\s*FILE_ATTR_M3U\s*\}', filetype_source))
    require({"wav", "mp3"} <= audio_extensions and {"m3u", "m3u8"} <= playlists,
            "Unexpected core statistics file classification")
    files = [entry for entry in entries if not entry["directory"]]
    extensions = [Path(entry["path"]).suffix[1:].lower() for entry in files]
    counts = {}
    for entry in files:
        parent = Path(entry["path"]).parent.as_posix()
        counts[parent] = counts.get(parent, 0) + 1
    size = sum(entry["bytes"] for entry in files)
    unit = 0
    while size >= 10240 and unit < 3:
        size >>= 10
        unit += 1
    values = (len(files), size, sum(extension in audio_extensions for extension in extensions),
              sum(extension in playlists for extension in extensions),
              sum(extension in {"bmp", "jpg", "jpe", "jpeg", "png", "ppm"} for extension in extensions),
              sum(extension in {"mpg", "mpeg", "mpv", "m2v"} for extension in extensions),
              sum(entry["directory"] for entry in entries), max(counts.values(), default=0))
    return values, SIZE_LABELS[unit]


class ListPluginDriver(PluginDriver):
    def __init__(self, *arguments, memory, disk, fixtures, **keywords):
        super().__init__(*arguments, **keywords)
        self.memory = memory
        self.disk = disk
        self.fixtures = fixtures
        self.pcm_attribution = "speech_only"
        self.drain_timeout = self.timeout

    def drain(self, phase=None):
        deadline = time.monotonic() + self.drain_timeout
        stable_since = None
        previous_log = None
        last_values = None
        while time.monotonic() < deadline:
            self.check_process()
            text = self.text()
            require("TTS: synthesis failed" not in text, "Synthesizer reported a failure")
            values = self.memory.values()
            idle = all(values[name] == 0 for name in (
                "pending_count", "synthesizing", "voice_playing", "voice_pcm_paused"))
            now = time.monotonic()
            if idle and previous_log == len(text):
                stable_since = now if stable_since is None else stable_since
                if now - stable_since >= 0.8:
                    self.report.setdefault("speech_drains", []).append({
                        "plugin": self.plugin, "phase": phase, "monotonic": now,
                        "values": values, "stable_seconds": now - stable_since,
                        "access": "read_only; stable polling is not an atomic snapshot",
                    })
                    return
            else:
                stable_since = None
            previous_log, last_values = len(text), values
            time.sleep(0.05)
        raise AssertionError(f"Speech failed to become idle: {self.plugin}: {last_values}")

    def navigate(self, labels):
        self.speech("startup", initial=True)
        language = "pl" if self.report["language"] == "polski" else "en"
        require(f"TTS parameters: language={language} " in self.text(), "Unexpected startup voice language")
        native = windows_backend()
        native.set_hidden(self.process.pid, self.window, True)
        require(not native.user32.IsWindowVisible(self.window), "Cannot hide owned SDL test window")
        self.seek(labels["LANG_DIR_BROWSER"])
        self.speech("enter Files", lambda: self.press("space"))
        entry = (self.fixtures["editor"] if self.plugin == "text_editor" else
                 "shortcuts.link" if self.plugin == "shortcuts_view" else self.report["aliases"][self.plugin])
        self.seek(Path(entry).name, maximum=45)
        return lambda: self.press("space")

    def row(self, name, action, expected, requirement="functional_action"):
        observation = self.speech(name, action, fragments=(expected,), requirement=requirement)
        if observation["segments"].count(expected) != 1:
            observation.update(status="failed", error=f"Missing or repeated selected-row input: {name}")
            raise AssertionError(observation["error"])
        return observation

    def state(self, name, condition, **evidence):
        observation = {"plugin": self.plugin, "suite": "plugin_lists", "name": self.plugin + ": " + name,
                       "status": "passed" if condition else "failed", "speech_required": False, **evidence}
        self.report["checks"].append(observation)
        require(condition, name)

    def return_root(self, labels, action):
        def leave():
            action()
            time.sleep(0.4)
            self.press("Left")

        self.speech("exit plugin and return to root Files", leave,
                    fragments=(labels["LANG_DIR_BROWSER"],), requirement="exit_root")


def exercise_editor(probe, labels, activate, words):
    previous_timeout = probe.timeout
    probe.timeout = probe.drain_timeout = max(240, previous_timeout)
    try:
        observation = probe.speech("initial complete 2047-byte UTF-8 line", activate,
                                   fragments=(words["start"].strip(), words["middle"].strip(), words["end"].strip()),
                                   requirement="initial_focus")
        try:
            verify_editor_observation(observation, probe.fixtures["long_line"])
        except AssertionError as error:
            observation.update(status="failed", error=str(error))
            raise
    finally:
        probe.timeout = probe.drain_timeout = previous_timeout
    probe.row("next editor line", lambda: probe.press("Down"), words["second"])
    probe.row("delete second line and speak replacement at same index",
               lambda: probe.press("space", 0.75), words["third"])
    probe.row("open changed-file menu", lambda: probe.press("Left"), "Return", requirement=None)
    for label in ("Playback Control", "Save Changes", "Save As...", "Save and Exit", "Ignore Changes and Exit"):
        probe.row("select exit option " + label, lambda: probe.press("Down"), label, requirement=None)
    probe.return_root(labels, lambda: probe.press("space"))
    expected = probe.fixtures["long_line"] + "\n" + words["second"] + "\n" + words["third"] + "\n"
    probe.state("Ignore Changes preserves original editor file",
                (probe.disk / probe.fixtures["editor"]).read_text(encoding="utf-8") == expected)


def exercise_dictionary(probe, labels, activate, words):
    def open_keyboard():
        activate()
        time.sleep(0.4)
        probe.press("Right")

    probe.row("dictionary keyboard picker is ready", open_keyboard, "a", requirement=None)
    probe.row("enter indexed word a", lambda: probe.press("space"), "a", requirement=None)
    rows = probe.fixtures["definition_rows"]
    probe.row("initial dictionary definition chunk", lambda: probe.press("space", 0.75),
               rows[0], requirement="initial_focus")
    probe.row("second dictionary definition chunk", lambda: probe.press("Down"), rows[1])
    probe.row("previous dictionary definition chunk", lambda: probe.press("Up"), rows[0])
    probe.return_root(labels, lambda: probe.press("Left"))


def exercise_statistics(probe, labels, activate, words):
    before = inventory(probe.disk)
    values, unit = expected_statistics(before, (ROOT / "apps/filetypes.c").read_text(encoding="utf-8"))
    expected = [f"{labels[label]}: {value}" for label, value in zip(STAT_LABELS, values)]
    expected[1] += " " + labels[unit]
    observation = probe.row("initial scan result Files", activate, expected[0], requirement="initial_focus")
    probe.state("Filesystem remains stable during statistics oracle interval", inventory(probe.disk) == before)
    probe.state("Statistics scan does not flood speech", len(observation["segments"]) <= 8,
                input_count=len(observation["segments"]))
    probe.report["statistics_oracle"] = {"inventory": before, "rows": expected,
                                          "scope": "Entire isolated root including immutable .rockbox assets"}
    probe.row("navigate size and unit", lambda: probe.press("Down"), expected[1])
    probe.row("repeat current size without leaving results", lambda: probe.press("space"), expected[1])
    for index in range(2, len(expected)):
        probe.row("navigate statistics row " + str(index), lambda: probe.press("Down"), expected[index])
    probe.return_root(labels, lambda: probe.press("Left"))


def exercise_calendar(probe, labels, activate, words):
    today = datetime.date.fromisoformat(probe.fixtures["calendar_today"])
    tomorrow = datetime.date.fromisoformat(probe.fixtures["calendar_tomorrow"])
    require(datetime.date.today() == today, "Calendar fixture crossed local midnight; recreate this run")

    def date_speech(name, action, date, event=None, requirement="functional_action"):
        fragments = (labels[MONTHS[date.month - 1]],) + ((event,) if event else ())
        observation = probe.speech(name, action, fragments=fragments, numbers=(date.day, date.year),
                                   requirement=requirement)
        require(datetime.date.today() == today, "Calendar run crossed local midnight")
        if event:
            require(observation["segments"].count(event) == 1, "Calendar first event duplicated")
        return observation

    date_speech("initial current calendar date", activate, today, requirement="initial_focus")
    date_speech("next day and first event", lambda: probe.press("Right"), tomorrow, words["event_first"])
    probe.row("open selected-day event list", lambda: probe.press("space"), words["event_first"])
    probe.row("navigate second event", lambda: probe.press("Down"), words["event_second"])
    date_speech("return from events to selected date", lambda: probe.press("Left"), tomorrow, words["event_first"])
    probe.return_root(labels, lambda: probe.press("Escape"))


def exercise_shortcuts(probe, labels, activate, words):
    probe.row("initial editable shortcut", activate, words["shortcut_first"], requirement="initial_focus")
    probe.row("select last shortcut", lambda: probe.press("Down"), words["shortcut_second"])
    probe.row("delete last shortcut and clamp to surviving row", lambda: probe.press("Insert"), words["shortcut_first"])
    saved = (probe.disk / "shortcuts.link").read_text(encoding="utf-8")
    entries = [line for line in saved.splitlines() if line.startswith("/")]
    probe.state("Shortcut deletion persists exactly the surviving entry",
                entries == [probe.fixtures["paths"][0] + "/\t" + words["shortcut_first"]], saved_entries=entries)
    probe.return_root(labels, lambda: probe.press("Left"))


def exercise_folders(probe, labels, activate, words):
    probe.row("initial folder main menu", activate, "Play Shuffled", requirement=None)
    probe.row("select Scan Folders without scanning", lambda: probe.press("Down"), "Scan Folders", requirement=None)
    probe.row("select Edit", lambda: probe.press("Down"), "Edit", requirement=None)
    paths = probe.fixtures["paths"]
    probe.row("initial editable folder path", lambda: probe.press("space"), paths[0], requirement="initial_focus")
    probe.row("disable selected folder", lambda: probe.press("space"), labels["LANG_DELETED"])
    probe.row("next folder remains enabled", lambda: probe.press("Down"), paths[1])
    probe.row("open save decision", lambda: probe.press("Left"), "Save", requirement=None)
    probe.row("select Ignore Changes", lambda: probe.press("Down"), "Ignore Changes", requirement=None)
    probe.row("return to main menu Edit", lambda: probe.press("space"), "Edit", requirement=None)
    probe.state("Ignoring folder changes preserves persistent data",
                digest(probe.disk / ".rockbox/folder_advance_list.dat") == probe.fixtures["folder_initial_sha256"])
    probe.return_root(labels, lambda: probe.press("Left"))


EXERCISES = dict(zip(PLUGINS, (exercise_editor, exercise_dictionary, exercise_statistics,
                              exercise_calendar, exercise_shortcuts, exercise_folders)))


def stop_owned(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=8)


def run_session(plugin, runtime, disk, results, report, arguments, labels, fixtures, layout, ownership):
    session = {"plugin": plugin, "status": "in_progress"}
    report["sessions"].append(session)
    process = probe = memory = None
    interrupted = False
    try:
        require(not (runtime / "simulator.log").exists(), "Previous session log was not preserved")
        (disk / ".rockbox/config.cfg").write_text(synthetic_config(arguments.language, arguments.voice_files_disabled) +
                                                 "kbd: plugin-lists\nkeyclick: off\nbeep: off\n", encoding="utf-8")
        environment = dict(os.environ, SDL_VIDEODRIVER="windows", SDL_AUDIODRIVER="disk",
                           SDL_DISKAUDIOFILE=str(runtime / f"{plugin}-audio.raw"), SDL_DISKAUDIODELAY="12")
        executable = runtime / "rockboxui.exe"
        windows_backend().ensure_unused(executable)
        process = subprocess.Popen([str(executable), "--root", str(disk), "--audiodev",
                                    environment["SDL_DISKAUDIOFILE"], "--debugbuttons"],
                                   cwd=runtime, env=environment, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        ownership["process"] = process
        session.update(pid=process.pid, pcm_file=environment["SDL_DISKAUDIOFILE"])
        window = find_window(process.pid, environment)
        memory = RecorderMemoryProbe(process, executable, layout, report["memory_diagnostics"])
        probe = ListPluginDriver(process, window, environment, runtime, report, arguments.timeout,
                                  plugin, report["keyboard_map"], memory=memory, disk=disk, fixtures=fixtures)
        activate = probe.navigate(labels)
        EXERCISES[plugin](probe, labels, activate, TEXT[arguments.language])
        session["status"] = "logged_pending_pcm"
    except (Exception, KeyboardInterrupt) as error:
        session.update(status="failed", error=f"{type(error).__name__}: {error}")
        interrupted = isinstance(error, KeyboardInterrupt)
    finally:
        previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            try:
                if probe is not None:
                    close_session(probe, session, results, session["status"] == "logged_pending_pcm")
                else:
                    stop_owned(process)
                    session["forced_owned_process_cleanup"] = process is not None
            except Exception as error:
                session.update(cleanup_error=f"{type(error).__name__}: {error}")
                stop_owned(process)
            finally:
                if memory is not None:
                    try:
                        memory.close()
                    except Exception as error:
                        session["cleanup_error"] = f"Memory handle close: {type(error).__name__}: {error}"
            if process is not None:
                session["exit_code"] = process.returncode
            log = runtime / "simulator.log"
            if log.exists() and process is not None and process.poll() is not None:
                destination = results / f"{plugin}-simulator.log"
                require(not destination.exists(), "Refusing to overwrite failed-session log")
                log.rename(destination)
                session.update(log=str(destination), log_sha256=digest(destination))
            selected = [check for check in report["checks"] if check.get("plugin") == plugin]
            verify_pcm_checks(selected)
            session["passed"] = (session["status"] == "logged_pending_pcm" and
                                 requirements_complete(report["checks"], plugin) and
                                 session.get("exit_code") == 0 and not session.get("cleanup_error") and
                                 not session.get("forced_owned_process_cleanup"))
            session["status"] = "passed" if session["passed"] else "failed"
            configuration = disk / ".rockbox/config.cfg"
            if configuration.is_file():
                session["synthetic_profile_after"] = configuration.read_text(encoding="utf-8", errors="replace")
            write_json(results / "report.json", report)
        finally:
            signal.signal(signal.SIGINT, previous_handler)
    return interrupted


def offline_driver_checks(results, voice_files_disabled=False):
    class FakeClock:
        def __init__(self):
            self.current = 0.0

        def monotonic(self):
            return self.current

        def sleep(self, duration):
            self.current += duration

    class FakeMemory:
        def __init__(self, always_busy=False):
            self.reads = 0
            self.always_busy = always_busy

        def values(self):
            self.reads += 1
            names = ("pending_count", "synthesizing", "voice_playing", "voice_pcm_paused")
            values = dict.fromkeys(names, 0)
            if self.always_busy:
                values["pending_count"] = 1
            elif self.reads <= 4:
                values[names[self.reads - 1]] = 1
            return values

    driver = object.__new__(ListPluginDriver)
    driver.plugin = "offline_fixture"
    driver.report = {}
    driver.drain_timeout = 3
    driver.memory = FakeMemory()
    driver.check_process = lambda: None
    driver.text = lambda: ""
    clock = FakeClock()
    with patch.object(time, "monotonic", clock.monotonic), patch.object(time, "sleep", clock.sleep):
        driver.drain("fixture completion")
    require(driver.memory.reads > 4 and clock.current >= 1,
            "Speech drain did not wait for every busy state and a stable idle interval")
    driver.memory = FakeMemory(always_busy=True)
    clock = FakeClock()
    with patch.object(time, "monotonic", clock.monotonic), patch.object(time, "sleep", clock.sleep):
        try:
            driver.drain("fixture timeout")
        except AssertionError:
            pass
        else:
            raise AssertionError("Speech drain accepted a permanently busy engine")
    pcm_path = results / "synthetic-pcm.raw"
    pcm_path.write_bytes(struct.pack("<512h", *([120, -120] * 256)))
    silence_path = results / "synthetic-silence.raw"
    silence_path.write_bytes(bytes(1024))
    checks = [{"name": "synthetic " + attribution, "speech_required": True, "pcm_file": str(pcm_path),
               "pcm_start": 0, "pcm_end": 1024, "status": "passed", "pcm_attribution": attribution}
              for attribution in ("speech_only", "mixed")]
    checks.append({"name": "invalid bounds", "speech_required": True, "pcm_file": str(pcm_path),
                   "pcm_start": 0, "pcm_end": 2048, "status": "passed", "pcm_attribution": "speech_only"})
    checks.append({"name": "silent action window", "speech_required": True, "pcm_file": str(silence_path),
                   "pcm_start": 0, "pcm_end": 1024, "status": "passed", "pcm_attribution": "speech_only"})
    verify_pcm_checks(checks)
    require([check["status"] for check in checks] == ["passed", "partial", "failed", "failed"],
            "Shared PCM validation accepted mixed sources, invalid bounds or silence as speech proof")

    class FakeProcess:
        def __init__(self):
            self.pid = 777
            self.returncode = None
            self.terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def wait(self, timeout):
            return self.returncode

    class FakeBackend:
        def ensure_unused(self, executable):
            pass

    navigation = object.__new__(ListPluginDriver)
    navigation.plugin = "shortcuts_view"
    navigation.report = {"language": "english", "aliases": {"shortcuts_view": "005 shortcuts_view.rock"}}
    navigation.fixtures = {"editor": "000 editor.ted"}
    navigation.process = FakeProcess()
    navigation.window = 1
    navigation.text = lambda: "TTS parameters: language=en "
    navigation.speech = lambda *arguments, **keywords: None
    navigation.press = lambda key: None
    sought = []
    navigation.seek = lambda label, **keywords: sought.append(label)
    with patch(__name__ + ".windows_backend") as backend:
        backend.return_value.user32.IsWindowVisible.return_value = False
        navigation.navigate({"LANG_DIR_BROWSER": "Files"})()
    require(sought == ["Files", "shortcuts.link"] and
            sought[-1] not in navigation.report["aliases"]["shortcuts_view"],
            "Parameter-file navigation must not match the root plugin alias instead")

    failed_runtime = results / "failed-launch-fixture"
    (failed_runtime / "simdisk/.rockbox").mkdir(parents=True)
    process = FakeProcess()

    def launch(*arguments, **keywords):
        (failed_runtime / "simulator.log").write_text("Synthetic launch failure, not a real simulator log.\n", encoding="utf-8")
        return process

    report = {"sessions": [], "checks": []}
    ownership = {}
    arguments = argparse.Namespace(language="english", timeout=10, voice_files_disabled=voice_files_disabled)
    with patch(__name__ + ".windows_backend", return_value=FakeBackend()), \
            patch.object(subprocess, "Popen", side_effect=launch), \
            patch.object(subprocess, "CREATE_NO_WINDOW", 0, create=True), \
            patch(__name__ + ".find_window", side_effect=AssertionError("Synthetic window discovery failure")):
        run_session("dict", failed_runtime, failed_runtime / "simdisk", results, report, arguments,
                    {}, {}, {}, ownership)
    expected_config = synthetic_config("english", voice_files_disabled) + "kbd: plugin-lists\nkeyclick: off\nbeep: off\n"
    require((failed_runtime / "simdisk/.rockbox/config.cfg").read_text(encoding="utf-8") == expected_config,
            "List session did not preserve the requested clean voice-file fixture mode")
    require(process.terminated and ownership["process"].poll() is not None and
            report["sessions"][0]["status"] == "failed" and
            "Synthetic window discovery failure" in report["sessions"][0]["error"] and
            (results / "dict-simulator.log").is_file(),
            "Failed-launch cleanup lost ownership, error evidence or complete log")
    gates = []
    for target in TARGETS:
        for language in TEXT:
            stderr = io.StringIO()
            with redirect_stderr(stderr), patch(__name__ + ".contained", side_effect=AssertionError("GUI gate bypassed")):
                try:
                    main(["--target", target, "--language", language])
                except SystemExit as error:
                    require(error.code == 2, "Missing build authorization must fail closed with CLI error 2")
                else:
                    raise AssertionError("CLI accepted an unauthorized GUI launch")
            gates.append({"target": target, "language": language, "exit_code": 2,
                          "active_build_access": False, "stderr": stderr.getvalue()})
    write_json(results / "offline-driver-report.json", {"passed": True, "gui_launched": False,
                                                         "voice_files_disabled": voice_files_disabled,
                                                         "speech_drains": driver.report["speech_drains"],
                                                         "synthetic_pcm_checks": checks,
                                                         "synthetic_failed_launch": report, "cli_gates": gates})


def self_test(voice_files_disabled=False):
    results = _project_materials_root(ROOT) / "tts-plugin-lists-gui-tests" / datetime.datetime.now(
        datetime.timezone.utc).strftime("selftest-%Y%m%dT%H%M%S%fZ")
    results.mkdir(parents=True)
    checks = []
    for language in TEXT:
        disk = results / language
        disk.mkdir()
        report = {}
        fixtures = add_fixture_files(disk, language, report, datetime.date(2026, 12, 31))
        line = fixtures["long_line"]
        chunks = utf8_chunks(line)
        require(len(chunks) == 3 and "".join(chunks) == line, "Long-line fixture roundtrip failed")
        require(all(len(chunk.encode("utf-8")) <= 768 for chunk in chunks), "Oversized input chunk")
        require(any(len(character.encode("utf-8")) == 4 for character in line), "Missing four-byte UTF-8 coverage")
        verify_editor_observation({"segments": chunks, "utterances": chunks}, line)
        verify_editor_observation({"segments": chunks, "utterances": [chunks[0], " ".join(chunks[1:])]}, line)
        for invalid in (chunks[::-1], chunks[:-1], chunks + chunks[:1]):
            try:
                verify_editor_observation({"segments": invalid, "utterances": invalid}, line)
            except AssertionError:
                continue
            raise AssertionError("Long-line oracle accepted incomplete, duplicate or reversed speech")
        index_record = (disk / ".rockbox/rocks/apps/dict.index").read_bytes()
        require(len(index_record) == 36 and index_record[:32] == b"a" + bytes(31) and
                struct.unpack_from(">I", index_record, 32)[0] == fixtures["dictionary_offset"] > 0 and
                struct.unpack_from("<I", index_record, 32)[0] != fixtures["dictionary_offset"],
                "Invalid dictionary disk record or endian-insensitive fixture offset")
        require(all(len(row.encode("utf-8")) <= 180 for row in fixtures["definition_rows"]), "Oversized dictionary row")
        require(len(fixtures["definition_rows"]) >= 3, "Dictionary fixture lacks navigation rows")
        require((disk / ".rockbox/plugin-lists.kbd").read_bytes() == b"aa\n",
                "Dictionary readiness key must move between two identical real character cells")
        memo = (disk / ".rockbox/rocks/apps/.memo").read_text(encoding="utf-8")
        require(len(memo.splitlines()) == 2 and all(row.startswith("0101202743") for row in memo.splitlines()),
                "Calendar year/week boundary fixture is invalid")
        folder = (disk / ".rockbox/folder_advance_list.dat").read_bytes()
        require(len(folder) == 784 and struct.unpack_from("<i", folder)[0] == 3, "Invalid native folder record")
        require([folder[4 + index * 260:4 + (index + 1) * 260].split(b"\0", 1)[0].decode("utf-8")
                 for index in range(3)] == list(fixtures["paths"]), "Folder path records failed roundtrip")
        write_json(disk / "fixture-report.json", report)
        checks.append({"language": language, "passed": True, "long_line_bytes": 2047,
                       "chunks": [len(chunk.encode("utf-8")) for chunk in chunks]})
    filetypes = (ROOT / "apps/filetypes.c").read_text(encoding="utf-8")
    values, unit = expected_statistics([
        {"path": "folder", "directory": True, "bytes": 0},
        {"path": "folder/sample.wav", "directory": False, "bytes": 10240},
        {"path": "list.m3u8", "directory": False, "bytes": 1},
        {"path": "image.png", "directory": False, "bytes": 1},
        {"path": "video.mpg", "directory": False, "bytes": 1},
    ], filetypes)
    require(values == (4, 10, 1, 1, 1, 1, 1, 3) and unit == "LANG_KIBIBYTE", "Statistics oracle mismatch")
    offline_driver_checks(results, voice_files_disabled)
    write_json(results / "report.json", {"passed": True, "gui_launched": False, "checks": checks,
                                         "voice_files_disabled": voice_files_disabled,
                                         "source_inputs": [{"source": str(ROOT / name), "sha256": digest(ROOT / name)}
                                                           for name in SOURCE_INPUTS],
                                         "limitations": "Pure fixture/oracle checks only; Windows PCM is not run"})
    print(f"Fixture/oracle self-test passed; no GUI launched: {results}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--language", choices=TEXT)
    parser.add_argument("--build-ready", action="store_true", help="Parent authorization for this completed target build")
    parser.add_argument("--voice-files-disabled", action="store_true",
                        help="Disable recorded menu/file/directory speech and mute recorded voices in the clean TTS fixture")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--self-test", action="store_true", help="Validate fixtures/oracles without GUI or active-build access")
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        if arguments.build or arguments.build_ready or arguments.target or arguments.language:
            parser.error("--self-test must not be combined with build or GUI arguments")
        return self_test(arguments.voice_files_disabled)
    if not arguments.target or not arguments.language or not arguments.build_ready:
        parser.error("Wait for parent authorization, then provide --target, --language and --build-ready")
    if sys.platform != "win32":
        parser.error("Actual GUI/PCM smoke requires native Windows Python, not WSL or Wine")
    if not 10 <= arguments.timeout <= 300:
        parser.error("--timeout must be between 10 and 300 seconds")
    workspace = contained(_project_materials_root(ROOT), ROOT)
    build = contained(arguments.build or workspace / TARGETS[arguments.target], workspace)
    test_root = workspace / "tts-plugin-lists-gui-tests"
    if test_root.exists():
        test_root = contained(test_root, workspace)
    else:
        test_root.mkdir()
    results = test_root / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    results.mkdir()
    report = dict(suite="plugin_lists", passed=False, target=arguments.target, language=arguments.language,
                  voice_files_disabled=arguments.voice_files_disabled,
                  source_build=str(build), checks=[], sessions=[], copies=[],
                  source_inputs=[{"source": str(contained(ROOT / name, ROOT)), "sha256": digest(ROOT / name)}
                                 for name in SOURCE_INPUTS],
                  limitations=[
                      "Run both languages on both targets; this invocation covers one target/language.",
                      "Disk PCM proves speech-only mixer output, not human intelligibility, WASAPI, NVDA/UIA or hardware.",
                      "Read-only speech-idle samples are non-atomic and require stable log/state for 0.8 seconds.",
                      "Long editor input observation and speech drain each allow at least 240 seconds.",
                      "Dictionary keyboard readiness is demonstrated by spoken picker/input, not a delay alone.",
                      "Dictionary definition paging, calendar date/events and final statistics are bounded smoke coverage.",
                      "Scan/import/export, full text editing and legacy recorded voice-file playback are untested.",
                      "Existing English plugin menus are upstream strings; fixture content is localized EN/PL.",
                  ], artifact_cleanup={"trash": [], "workspace": str(results), "pending_user_decisions": []})
    loan = ExecutableLoan(build, results, report)
    ownership = {"process": None}
    print(f"Native Windows plugin-list evidence: {results}", flush=True)
    try:
        layout = prepare_memory_diagnostics(build / "rockboxui.exe", report)
        runtime, disk, labels = prepare_plugins_fixture(build, results, arguments.language, report, loan,
                                                         arguments.target, PLUGINS, REQUIRED_LABELS,
                                                         voice_files_disabled=arguments.voice_files_disabled)
        displayed = display_labels(build, arguments.language)
        for label in STAT_LABELS + SIZE_LABELS + ("LANG_DELETED",):
            require(displayed.get(label), f"Missing compiled display label used by plugin text: {label}")
            labels[label] = displayed[label]
        report["label_origins"] = {
            "display_catalog": list(STAT_LABELS + SIZE_LABELS + ("LANG_DELETED",)),
            "voice_catalog": list(MONTHS) + ["LANG_DIR_BROWSER"],
            "reason": "Statistics and folder rows call rb->str; property display labels include brackets",
        }
        fixtures = add_fixture_files(disk, arguments.language, report)
        install_editor_viewer(disk, report)
        write_json(results / "report.json", report)
        for plugin in PLUGINS:
            if run_session(plugin, runtime, disk, results, report, arguments, labels, fixtures, layout, ownership):
                break
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            try:
                stop_owned(ownership["process"])
                loan.restore(ownership["process"])
            except Exception as error:
                report["executable_restore_error"] = f"{type(error).__name__}: {error}"
                loan.record.update(state="restore_failed", error=str(error))
                loan.save_record()
            inputs = report.get("copies", []) + report["source_inputs"] + [
                {"source": item["path"], "sha256": item["sha256"]} for item in report.get("catalog_inputs", [])]
            report["changed_source_assets"] = [item["source"] for item in inputs if not Path(item["source"]).is_file()
                                               or digest(Path(item["source"])) != item["sha256"]]
            report["failed_checks"] = [check["name"] for check in report["checks"] if check["status"] != "passed"]
            report["passed"] = (len(report["sessions"]) == len(PLUGINS) and
                                all(session.get("passed") for session in report["sessions"]) and
                                not report["failed_checks"] and not report["changed_source_assets"] and
                                not report.get("error") and not report.get("executable_restore_error") and
                                loan.record["restored"])
        except Exception as error:
            report["evidence_error"] = f"{type(error).__name__}: {error}"
            report["passed"] = False
        finally:
            write_json(results / "report.json", report)
            signal.signal(signal.SIGINT, previous_handler)
    print(json.dumps({"suite": "plugin_lists", "passed": report["passed"],
                      "failed_checks": report.get("failed_checks"), "executable_restored": loan.record["restored"],
                      "report": str(results / "report.json")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
