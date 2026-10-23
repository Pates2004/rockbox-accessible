"""Future HiBy R1 reader GUI acceptance on an undisplayed private desktop.

Default/readiness never launches a process. Execute only after a new reader
source generation, native/Windows qualification and a reviewed fresh freeze.
No ordinary GuiProbe.launch or global keyboard/mouse/focus API is used.
"""
import argparse
import ast
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import unittest
from unittest import mock
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root
import test_accessibility_services_gui as services
from test_tts_bookmarks_gui import READER_ROWS, tone_amplitude, bookmark_entries
from test_tts_recorder_gui import ExecutableLoan, display_labels
from test_tts_simulator import catalog_labels, windows_backend

ROOT = Path(__file__).resolve().parents[2]
SCOPE = "reader-tr01-tr05/private-gui-v1"
READER_PATCH = "cda6bf858f750080e23d6d6b461afac94737c152105efa0b03d1d7b340a5e852"
STAGES = (("A", 0, 0, 1, 1), ("B", 1, 1, 0, 2),
          ("C", 0, 2, 1, 0), ("D", 1, 0, None, None))
READER_IDS = (
    "LANG_TTS_FIND", "LANG_TTS_FIND_NEXT", "LANG_TTS_FIND_PREVIOUS",
    "LANG_TTS_GOTO_LINE", "LANG_TTS_GOTO_PAGE", "LANG_TTS_GOTO_PERCENT",
    "LANG_TTS_SEARCH_CASE", "LANG_TTS_IGNORE_CASE", "LANG_TTS_MATCH_CASE",
    "LANG_TTS_SEARCH_WRAP", "LANG_TTS_WRAP_STOP", "LANG_TTS_WRAP_ASK",
    "LANG_TTS_WRAP_AUTO", "LANG_TTS_WRAP_QUESTION", "LANG_TTS_FOUND",
    "LANG_TTS_FOUND_WRAPPED", "LANG_TTS_NO_MORE_MATCHES",
    "LANG_TTS_QUERY_REQUIRED", "LANG_TTS_QUERY_INVALID", "LANG_TTS_DESTINATION_INVALID",
    "LANG_TTS_READER_STORAGE_ERROR", "LANG_TTS_OPERATION_FAILED",
    "LANG_TTS_READER_BUSY", "LANG_TTS_READER_TEMP_ERROR")
EXTRA_IDS = ("LANG_DIR_BROWSER", "LANG_SHUTTINGDOWN", "VOICE_OF", "VOICE_EDIT",
    "VOICE_BLANK", "LANG_KBD_OK", "LANG_KBD_CANCEL", "LANG_TTS_READER_MENU",
    "LANG_BOOKMARK_MENU_CREATE", "LANG_BOOKMARK_MENU_LIST", "LANG_TTS_TEXT_BOOKMARK",
    "LANG_TTS_POSITION", "LANG_TTS_BYTES", "LANG_TTS_PAUSED", "LANG_TTS_FINISHED",
    "LANG_READ_FAILED", "LANG_TTS_INVALID_TEXT", "LANG_TTS_BOOKMARK_CHANGED",
    "LANG_SETTINGS", "LANG_GENERAL_SETTINGS", "LANG_VOICE", "LANG_TALKBOX_SETTINGS",
    "LANG_TALKBOX_ANNOUNCE_POSITION", "LANG_TALKBOX_POSITION_EXCEPT_SLIDERS", "LANG_OFF",
    "LANG_BOOKMARK_CREATE_SUCCESS")
SOURCE_PATHS = tuple(sorted(set(services.SOURCE_PATHS) | {
    "apps/tts_reader.c", "apps/tts_reader_settings.c", "apps/tts_reader_settings.h",
    "apps/keyboard.h", "apps/recorder/keyboard.c",
    "uisimulator/common/sim_tasks.c", "tools/tests/test_tts_reader_services_gui.py",
    "tools/tests/test_tts_bookmarks_gui.py", "tools/tests/test_tts_simulator.py",
    "tools/tests/test_tts_recorder_gui.py", "tools/tests/test_accessibility_services_gui.py"}))
CASE_NAME = "001 Reader case.txt"
LINE_NAME = "002 Reader lines.txt"
EMPTY_NAME = "003 Reader empty.txt"
BOM_NAME = "004 Reader BOM.txt"
CACHE_NAME = "005 Reader cache.txt"
MUSIC_NAME = "006 Reader music.wav"
CASE_TEXT = ("żółć ŻÓŁĆ zolc\nąćęłńóśźż ĄĆĘŁŃÓŚŹŻ\nababa\r\nsolo\n" +
             "".join("padding line %02d with ordinary text\n" % n for n in range(40)))
CASE_BYTES = b"\xef\xbb\xbf" + CASE_TEXT.encode("utf-8")
LINE_BYTES = b"\xef\xbb\xbf" + "a\r\n\rż\nb\x85c\u2028d\u2029e\n".encode("utf-8")
CACHE_BYTES = b"\xef\xbb\xbf" + b"x" * 763 + "Żółć end\n".encode("utf-8")
CASE_LOWER = 3
CASE_UPPER = 3 + len("żółć ".encode("utf-8"))
SOLO = CASE_BYTES.index(b"solo")
OVERLAP = CASE_BYTES.index(b"ababa")
LINE_STARTS = (3, 6, 7, 10, 13, 17, 21)
LIMITATIONS = [
    "Prepared driver code requires a fresh reader generation and future helper bindings; it has not been executed.",
    "Disk PCM/logs establish simulator output, not human hearing, NVDA/UIA, physical R1/touch/RF or flash durability.",
    "No GUI seam injects short I/O, fsync/close/rename failures, queue rejection or exact descriptor-close counts.",
    "Those faults and deterministic checkpoint cancellation remain real-C fixture obligations.",
    "No reliable scan-entry observation exists for deterministic USB during a long scan; that GUI case is not claimed.",
    "USB trigger logs prove queued events; actual browser return/new reader checks separately establish unwind and no observed commit.",
    "A missing keyboard focus/layout trace fails the case; no memory writes or direct query/preferences injection is a fallback."]


def require(condition, message):
    services.require(condition, message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    services.write_json(path, value)


def canonical(case, wrap):
    require(type(case) is int and case in (0, 1) and type(wrap) is int and wrap in (0, 1, 2),
            "Invalid canonical reader choices")
    return f"RBTTSREADER:1\ncase:{case}\nwrap:{wrap}\n".encode("ascii")


def sidecar(runtime, expected=None, absent=False):
    resources = runtime / "simdisk/.rockbox"
    primary, temporary = resources / "tts-reader.cfg", resources / "tts-reader.cfg.tmp"
    require(not temporary.exists(), "Owned reader temporary remains")
    if absent:
        require(not primary.exists(), "Fresh fixture already contains reader preferences")
        return None
    require(primary.is_file() and primary.read_bytes() == canonical(*expected),
            "Canonical saved choices differ from actual menu acceptance")
    return {"bytes": 28, "sha256": digest(primary), "case": expected[0], "wrap": expected[1]}


def keyboard_rows():
    source = (ROOT / "apps/recorder/keyboard.c").read_text(encoding="utf-8")
    start = source.index('p = "1234567890\\n"')
    end = source.index("pm->default_lines = 8;", start)
    rows = "".join(ast.literal_eval(token) for token in re.findall(
        r'"(?:[^"\\]|\\.)*"', source[start:end])).split("\n")
    require(len(rows) == 24 and all(len(row) == 10 for row in rows),
            "Unreviewed point-mode keyboard geometry")
    return tuple(tuple(rows[page * 8:(page + 1) * 8]) for page in range(3))


def current_file_selection(text, of_label, indices_enabled):
    """Read one complete current selection, requiring both ordered speech traces."""
    connector = services.normalized(of_label)
    require(connector and type(indices_enabled) is bool, "Invalid file-selection policy")
    selections = []
    for prefix in ("TTS", "TTS utterance"):
        segments = services.phrases(text, prefix)
        require(segments and all(segment.strip() for segment in segments),
                "Missing current file-selection trace: " + prefix)
        spoken = services.normalized(" ".join(segments))
        suffix = re.search(r" ([0-9]+) " + re.escape(connector) + r" ([0-9]+)$", spoken)
        require(bool(suffix) == indices_enabled, "Unexpected file-selection index suffix in " + prefix)
        if suffix:
            position, total = int(suffix[1]), int(suffix[2])
            require(1 <= position <= total and suffix[1] == str(position) and suffix[2] == str(total),
                    "Invalid file-selection index range")
            name = spoken[:suffix.start()]
        else:
            name = spoken
        require(name, "File-selection trace has no name")
        selections.append((spoken, name))
    require(selections[0] == selections[1], "Current file-selection traces disagree")
    return selections[0][1]


def spoken_position(text, labels, indices_enabled):
    """Validate the exact fourth Properties row and its five-row list policy."""
    connector = services.normalized(labels["VOICE_OF"])
    require(connector and type(indices_enabled) is bool, "Invalid Properties index policy")
    pattern = (re.escape(services.normalized(labels["LANG_TTS_POSITION"])) +
               r": ([0-9]+)%, ([0-9]+) / ([0-9]+) " +
               re.escape(services.normalized(labels["LANG_TTS_BYTES"])))
    values, complete_rows = [], []
    for prefix in ("TTS", "TTS utterance"):
        spoken = services.normalized(" ".join(services.phrases(text, prefix)))
        complete_rows.append(spoken)
        suffix = re.search(r" ([0-9]+) " + re.escape(connector) + r" ([0-9]+)$", spoken)
        require(bool(suffix) == indices_enabled, "Unexpected Properties index suffix in " + prefix)
        if suffix:
            require(suffix[1] == "4" and suffix[2] == "5",
                    "Position must be exactly row 4 of 5 in Properties")
            spoken = spoken[:suffix.start()]
        match = re.fullmatch(pattern, spoken)
        require(match is not None, "Malformed current spoken Position row in " + prefix)
        percent, offset, size = map(int, match.groups())
        require(0 <= percent <= 100 and 0 <= offset <= size, "Invalid spoken Position range")
        values.append((percent, offset, size))
    require(complete_rows[0] == complete_rows[1] and values[0] == values[1],
            "Current spoken Position traces disagree")
    return values[0][1:]


def require_abort_observation(log, properties_text, labels, origin, size, indices_enabled):
    require(type(origin) is int and 0 <= origin <= size, "Missing abort origin")
    require("TTS reader cursor:" not in log, "Aborted keyboard published a cursor commit")
    require(spoken_position(properties_text, labels, indices_enabled) == (origin, size),
            "Fresh spoken Properties shows a cursor change after abort")


def compiled_labels(build):
    result = {}
    required = tuple(dict.fromkeys(tuple(READER_ROWS) + READER_IDS + EXTRA_IDS))
    require(len(READER_ROWS) == 15, "Apply the reviewed reader row inventory first")
    for language in ("polski", "english"):
        voice, display = catalog_labels(build, language), display_labels(build, language)
        require(all(voice.get(name) and display.get(name) for name in required if not name.startswith("VOICE_")),
                "Incomplete compiled reader PL/EN labels")
        require(all(voice.get(name) for name in required), "Missing reader spoken labels")
        for extension in ("lng", "vstrings"):
            require(digest(build / f"apps/lang/{language}.{extension}") ==
                    digest(build / f"simdisk/.rockbox/langs/{language}.{extension}"),
                    "Compiled/fullinstall catalog mismatch")
        result[language] = {"voice": {name: voice[name] for name in required},
                            "display": {name: display.get(name, voice[name]) for name in required}}
    return result


def validate_authorization(arguments):
    require(arguments.execute and arguments.build_ready and services.sha256_value(arguments.freeze_sha256)
            and services.sha256_value(arguments.exe_sha256), "Parent execute/build-ready and exact hashes required")
    central = project_materials_root(ROOT)
    path = confined_path(arguments.freeze, central)
    require(digest(path) == arguments.freeze_sha256, "Reader freeze identity changed")
    freeze = json.loads(path.read_text(encoding="utf-8"))
    require(freeze.get("scope") == SCOPE and freeze.get("reader_patch_sha256") == READER_PATCH and
            freeze.get("with_music") is True and freeze.get("exe_sha256") == arguments.exe_sha256,
            "Wrong reader generation, music contract or executable binding")
    require(isinstance(freeze.get("version"), str) and freeze["version"] == services.EXPECTED_VERSION,
            "New reader freeze must match the proper services harness version after its coordinated update")
    for field in ("sources", "build_files"):
        require(isinstance(freeze.get(field), dict) and freeze[field], "Missing frozen " + field)
        folded = []
        for name, checksum in freeze[field].items():
            folded.append(services.relative_name(name).casefold())
            require(services.sha256_value(checksum), "Malformed frozen hash")
        require(len(folded) == len(set(folded)), "Case-colliding frozen inputs")
    require(set(SOURCE_PATHS) <= set(freeze["sources"]), "Reader freeze lacks source dependencies")
    require(set(services.METADATA_FILES) <= set(freeze["build_files"]), "Reader freeze lacks compiled metadata")
    require(freeze["build_files"].get("rockboxui.exe") == arguments.exe_sha256, "Unbound executable")
    build = confined_path(Path(freeze["build"]), central)
    services.bound_checks(ROOT, freeze["sources"])
    services.bound_checks(build, freeze["build_files"])
    for path in services.runtime_assets(build):
        require(freeze["build_files"].get(path.relative_to(build).as_posix()) == digest(path),
                "Unbound immutable runtime asset")
    # New-generation pins come from this reviewed freeze, never old-generation constants.
    for name in services.TRACE_SOURCES:
        require(freeze["sources"].get(name) == digest(ROOT / name), "Unbound current audio trace source")
    require(all(token in (build / "rockboxui.exe").read_bytes() for token in services.TRACE_FEATURES),
            "New reader EXE lacks the qualified optional observation tap")
    for name in ("rockbox-info.txt", "simdisk/.rockbox/rockbox-info.txt"):
        text = (build / name).read_text(encoding="utf-8")
        require(re.search(r"^Target: hibyr1\s*$", text, re.M) and re.search(
            r"^Version: " + re.escape(freeze["version"]) + r"\s*$", text, re.M), "Wrong new target/version")
    for path in (build / "simdisk").rglob("*"):
        require(not any(path.name.casefold() == base or path.name.casefold().startswith(base + ".")
                        for base in ("tts-reader.cfg", "bluetooth.cfg")),
                "Development runtime contains reader/Bluetooth state")
    require(windows_backend() is not None, "Native Windows execution required")
    return freeze, build


def prepare_language(build, directory, language, labels, report):
    # Exactly one preparation per language. No call to configure_session/preserve_runtime_changes.
    runtime = services.prepare_runtime(build, directory, report)
    resources = runtime / "simdisk/.rockbox"
    # The synthetic 300ms recognizer matches the bounded .42s context hold.
    # Keep production defaults and the <.8s input/release bound unchanged.
    profile = (services.mapping_profile(services.mapping_contract())
               .replace("enabled:0\n", "enabled:1\n", 1)
               .replace("hold:700\n", "hold:300\n", 1))
    seed = {
        "config.cfg": services.synthetic_config(language, True, True) +
            "list wraparound: off\nshow filename exts: on\ntouchscreen mode: point\n"
            "tts announce position: except-sliders\n"
            "tts reader unit: word\ntts reader page lines: 2\n"
            "use most-recent-bookmarks: on\nautoload bookmarks: off\nautocreate bookmarks: off\n",
        "accessibility.cfg": profile,
        "accessibility-typing.cfg": "RBACCESSIBILITY-TYPING:1\nmode:2\n"}
    for name, text in seed.items():
        target = resources / name
        require(not target.exists(), "Refusing synthetic profile overwrite")
        target.write_bytes(text.encode("utf-8"))
    documents = {CASE_NAME: CASE_BYTES, LINE_NAME: LINE_BYTES, EMPTY_NAME: b"",
                 BOM_NAME: b"\xef\xbb\xbf", CACHE_NAME: CACHE_BYTES}
    for name, data in documents.items():
        target = runtime / "simdisk" / name
        require(not target.exists(), "Synthetic document collision")
        target.write_bytes(data)
    services.make_tone(runtime / "simdisk" / MUSIC_NAME)
    sidecar(runtime, absent=True)
    report["seeded_once"] = {"language": language, "profiles": seed,
        "documents": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                      for name, data in documents.items()},
        "query_injection": False, "reader_preferences_injection": False}
    write_json(directory / "initial-profile.json", report["seeded_once"])
    return runtime


class ReaderProbe(services.ServicesProbe):
    """Services ownership/input/PCM with explicit restart and handle collection."""
    def launch(self, desktop_handle):
        require(not self.log.exists() and not self.observation.exists() and not self.pcm.exists(),
                "Prior complete log/PCM must be retained before a new launch")
        self.native.assert_private(self.desktop)
        super().launch(desktop_handle)
        self.report["launch"] = {"pid": self.process.pid, "hwnd": int(self.window),
            "desktop": self.desktop, "new_process": True, "handle_collected": False}
        self.capture("Startup language " + self.report["language"], initial=True)
        expected = "pl" if self.report["language"] == "polski" else "en"
        require("TTS parameters: language=" + expected + " " in self.text(), "Wrong live synthesis language")

    def capture(self, *args, **kwargs):
        first = len(self.report["checks"])
        try:
            return super().capture(*args, **kwargs)
        finally:
            for record in self.report["checks"][first:]:
                record["optional_speech"] = bool(kwargs.get("optional", False))
                record["music_at_capture"] = self.music_expected

    def hold_context(self):
        self.alive()
        record = {"key": "Right", "purpose": "reader context first repeat", "samples": [],
                  "release_sent": False, "passed": False}
        self.report.setdefault("context_holds", []).append(record)
        mask = self.report["input_layout"]["button_masks"]["Right"]
        self.wait_button_state(0, time.perf_counter() + services.PRESS_ACK_TIMEOUT, record, "before-down")
        started = time.perf_counter()
        try:
            self.key("Right", True)
            self.wait_button_state(mask, started + services.PRESS_ACK_TIMEOUT, record, "down")
            time.sleep(max(0, 0.42 - (time.perf_counter() - started)))
        finally:
            require(self.process.poll() is None, "Owned child exited during context hold")
            self.key("Right", False)
            record["release_sent"] = True
            self.wait_button_state(0, started + 0.8, record, "released")
            record["hold_seconds"] = time.perf_counter() - started
        require(0.3 <= record["hold_seconds"] < 0.8, "Context hold left its explicit first-repeat bound")
        record["passed"] = True

    def keyboard_chord(self, first, second):
        require((first, second) in (("Insert", "Right"), ("Insert", "Left"),
            ("Insert", "Down"), ("Left", "Right")), "Unapproved reader keyboard chord")
        record = {"keys": [first, second], "samples": [], "passed": False, "released": []}
        self.report.setdefault("keyboard_chords", []).append(record)
        masks = self.report["input_layout"]["button_masks"]
        held = []
        self.wait_button_state(0, time.perf_counter() + services.PRESS_ACK_TIMEOUT, record, "before-chord")
        started = time.perf_counter()
        try:
            self.key(first, True)
            held.append(first)
            self.wait_button_state(masks[first], started + services.PRESS_ACK_TIMEOUT, record, "first-down")
            self.key(second, True)
            held.append(second)
            self.wait_button_state(masks[first] | masks[second], started + services.PRESS_ACK_TIMEOUT, record, "both-down")
            time.sleep(0.04)
        finally:
            for key in reversed(held):
                require(self.process.poll() is None, "Child exited before chord release")
                self.key(key, False)
                record["released"].append(key)
            self.wait_button_state(0, started + services.PRESS_MAX_DOWN, record, "released")
            record["seconds"] = time.perf_counter() - started
        require(record["seconds"] < services.PRESS_MAX_DOWN, "Keyboard chord reached first-repeat timing")
        record["passed"] = True
        time.sleep(0.4)

    def usb_toggle(self, inserted):
        self.alive()
        marker = self.mark()
        acknowledgement = {"samples": []}
        self.wait_button_state(0, time.perf_counter() + services.PRESS_ACK_TIMEOUT,
                               acknowledgement, "before-usb-key")
        started = time.perf_counter()
        try:
            self.key("c", True)
            time.sleep(0.08)
        finally:
            require(self.process.poll() is None, "Child exited before USB-key release")
            self.key("c", False)
        require(time.perf_counter() - started < 0.28, "Unbounded USB-key press")
        expected = "USB inserted. Waiting for " if inserted else "USB removed."
        deadline = time.perf_counter() + self.timeout
        while expected not in self.text(marker):
            self.alive()
            require(time.perf_counter() < deadline, "No actual simulator USB toggle evidence")
            time.sleep(0.05)
        self.report.setdefault("usb_events", []).append({"inserted": inserted, "log_start": marker,
            "log_end": self.mark(), "evidence": self.text(marker), "scoped_c_release": True,
            "evidence_kind": "queued insertion trigger" if inserted else "removal trigger"})

    def close(self, long_hold=False):
        if self.report.get("launch", {}).get("handle_collected"):
            return
        try:
            super().close(long_hold=False)
        finally:
            if self.memory is not None:
                self.memory.close()
                self.memory = None
        require(self.process is not None, "No owned simulator process to collect")
        code = self.process.wait(timeout=12)
        self.report["actual_exit_code"] = code
        require(type(code) is int and code == 0, "Owned simulator did not exit normally")
        handle = self.process._handle
        require(handle is not None, "Owned process handle was already lost")
        handle.Close()
        self.report["launch"]["handle_collected"] = True
        self.report["memory_handle_closed"] = self.memory is None
        require(self.report.get("shutdown", {}).get("passed"), "Missing bounded graceful-shutdown receipt")


class ReaderUI:
    def __init__(self, probe):
        self.p = probe
        self.labels = probe.labels
        self.accepted_query = ""
        self.in_menu = False
        self.rows = keyboard_rows()
        self.page = self.x = self.y = 0
        self.document = CASE_NAME
        self.in_browser = False
        self.indices_enabled = True

    def observed(self, name, action=None, expected=(), optional=False):
        return self.p.capture(name, action, tuple(expected), optional=optional)

    def wait_log(self, marker, predicate, description):
        deadline = time.perf_counter() + self.p.timeout
        while not predicate(self.p.text(marker)):
            self.p.alive()
            require(time.perf_counter() < deadline, "Missing " + description)
            time.sleep(0.05)
        return self.p.text(marker)

    def open_document(self, name=CASE_NAME):
        self.document = name
        self.accepted_query = ""
        if not self.in_browser:
            self.observed("Home root menu", lambda: [self.p.press("Up") for unused in range(20)], optional=True)
            self.p.row("Observe root selection after homing", "Down")
            self.p.row("Return to first root selection", "Up")
            self.p.enter("LANG_DIR_BROWSER")
            self.in_browser = True
        self.observed("Home synthetic file list",
            lambda: [self.p.press("Up") for unused in range(12)], optional=True)
        self.p.row("Observe file selection after homing", "Down")
        self.p.row("Return to first file selection", "Up")
        for attempt in range(15):
            current = current_file_selection(self.p.latest, self.labels["VOICE_OF"], self.indices_enabled)
            if services.normalized(name) == current:
                break
            self.p.row("Find synthetic file " + name)
        else:
            raise AssertionError("Synthetic document was not reached")
        if name.endswith(".wav"):
            # Homing/selection must settle against the current silent state.
            # The capture below starts the WAV before waiting for a music tail.
            self.p.music_expected = True
            self.observed("Open synthetic music", lambda: self.p.press("Right"), optional=True)
            self.in_menu = False
        else:
            marker = self.p.mark()
            def open_and_pause():
                self.p.press("Right")
                self.wait_log(marker, lambda text: "TTS reader state:" in text, "real reader entry")
                self.p.hold_context()
            # Stop continuous reading before asking the PCM observer to settle.
            self.observed("Open and pause " + name, open_and_pause, (self.labels["LANG_TTS_RESUME"],))
            self.in_menu = True
            self.leave_menu()

    def open_menu(self):
        require(not self.in_menu, "Reader menu already open")
        text = self.observed("Reader context", self.p.hold_context, (self.labels["LANG_TTS_RESUME"],))
        services.require_list_position(text, self.labels["LANG_TTS_RESUME"], self.labels, 1, 15, enabled=self.indices_enabled)
        self.in_menu = True

    def row(self, identifier):
        require(self.in_menu and identifier in READER_ROWS, "Unknown reader row")
        index = READER_ROWS.index(identifier)
        # Every call starts in a freshly opened context menu at Resume.
        for position in range(1, index + 1):
            text = self.p.row("Reader row " + READER_ROWS[position], expected=(self.labels[READER_ROWS[position]],))
            services.require_list_position(text, self.labels[READER_ROWS[position]], self.labels, position + 1, 15, enabled=self.indices_enabled)

    def leave_menu(self):
        if self.in_menu:
            self.observed("Leave reader menu paused", lambda: self.p.press("Left"), optional=True)
            self.in_menu = False

    def preference(self, kind, stored, choose=None, cancel_moved=False):
        identifier = "LANG_TTS_SEARCH_CASE" if kind == "case" else "LANG_TTS_SEARCH_WRAP"
        choices = ("LANG_TTS_IGNORE_CASE", "LANG_TTS_MATCH_CASE") if kind == "case" else (
            "LANG_TTS_WRAP_STOP", "LANG_TTS_WRAP_ASK", "LANG_TTS_WRAP_AUTO")
        self.open_menu()
        self.row(identifier)
        text = self.observed("Open saved " + kind, lambda: self.p.press("Right"), (self.labels[choices[stored]],))
        services.require_list_position(text, self.labels[choices[stored]], self.labels, stored + 1, len(choices), enabled=self.indices_enabled)
        destination = ((stored + 1) % len(choices)) if cancel_moved else stored if choose is None else choose
        position = stored
        while position != destination:
            key = "Down" if destination > position else "Up"
            position += 1 if destination > position else -1
            text = self.p.row("Move " + kind + " choice", key, (self.labels[choices[position]],))
            services.require_list_position(text, self.labels[choices[position]], self.labels, position + 1, len(choices), enabled=self.indices_enabled)
        self.observed("Cancel " + kind if cancel_moved or choose is None else "Accept " + kind,
            lambda: self.p.press("Left" if cancel_moved or choose is None else "Right"),
            (self.labels[identifier],))
        self.leave_menu()

    def menu_inventory(self):
        self.open_menu()
        for position in range(1, len(READER_ROWS)):
            text = self.p.row("Ordered reader inventory " + str(position),
                expected=(self.labels[READER_ROWS[position]],))
            services.require_list_position(text, self.labels[READER_ROWS[position]], self.labels, position + 1, 15)
        self.leave_menu()

    def cursor(self, text=None):
        text = self.p.text() if text is None else text
        matches = re.findall(r"TTS reader cursor: (\d+)|TTS reader state: (?:paused|finished) offset=(\d+)", text)
        require(matches, "No actual reader cursor/state observation")
        return int(next(value for value in matches[-1] if value))

    def keyboard_home(self, numeric=False):
        def home():
            for unused in range(12):
                self.p.press("Up")
            self.p.press("Down")
            for unused in range(32):
                self.p.press("Left")
        self.observed("Home real on-screen picker", home, ("U+0030" if numeric else "U+0031",))
        self.page = self.x = self.y = 0

    def picker_character(self, character, numeric=False):
        pages = (("0123456789",),) if numeric else self.rows
        matches = [(page, row, column) for page, rows in enumerate(pages)
            for row, text in enumerate(rows) for column, value in enumerate(text) if value == character]
        require(matches, "Character absent from real on-screen keyboard: " + repr(character))
        page, y, x = matches[0]
        def navigate():
            while self.y:
                self.p.press("Up")
                self.y -= 1
            while self.page != page:
                self.p.keyboard_chord("Left", "Right")
                self.page = (self.page + 1) % len(pages)
            while self.x != x:
                direction = 1 if x > self.x else -1
                self.p.press("Right" if direction > 0 else "Left")
                self.x += direction
            while self.y != y:
                self.p.press("Down")
                self.y += 1
        token = "U+%04x" % ord(character)
        if (self.page, self.y, self.x) != (page, y, x):
            self.observed("Speak actual picker target " + repr(character), navigate, (token,))
        self.observed("Insert real picker character " + repr(character),
                      lambda: self.p.press("Insert"), (token,))

    def edit(self, value, previous="", numeric=False):
        self.keyboard_home(numeric)
        for unused in previous:
            self.observed("Delete prior accepted query character",
                lambda: self.p.keyboard_chord("Insert", "Down"), optional=True)
        for character in value:
            self.picker_character(character, numeric)

    def operation(self, identifier, value=None, expected=None, offset=None,
                  wrap_answer=None, abort=False):
        try:
            origin = self.cursor()
        except AssertionError:
            origin = None
        self.open_menu()
        self.row(identifier)
        if value is not None:
            self.observed("Enter " + identifier, lambda: self.p.press("Right"), (self.labels[identifier],))
            numeric = identifier.startswith("LANG_TTS_GOTO_")
            self.edit(value, "" if numeric else self.accepted_query, numeric)
            if abort:
                require(origin is not None, "Abort requires an observed starting cursor")
                abort_marker = self.p.mark()
                self.observed("Abort actual keyboard", lambda: self.p.keyboard_chord("Insert", "Left"),
                    (self.labels[identifier],))
                self.leave_menu()
                # Observe fresh spoken position before any Go-to can mask a jump.
                position_text = self.properties(origin, len(self.document_bytes()))
                require_abort_observation(self.p.text(abort_marker), position_text, self.p.status_labels,
                                          origin, len(self.document_bytes()), self.indices_enabled)
                return None
            trigger = lambda: self.p.keyboard_chord("Insert", "Right")
        else:
            trigger = lambda: self.p.press("Right")
        if wrap_answer is not None:
            self.observed("Ask before wrapping", trigger, (self.labels["LANG_TTS_WRAP_QUESTION"],))
            trigger = lambda: self.p.press("Right" if wrap_answer == "yes" else "Left")
        text = self.observed("Actual result " + identifier, trigger, (self.labels[expected],))
        success = expected in ("LANG_TTS_FOUND", "LANG_TTS_FOUND_WRAPPED") or identifier.startswith("LANG_TTS_GOTO_") and expected == identifier
        if success:
            self.in_menu = False
            require(self.cursor(text) == offset, "Result committed the wrong byte offset")
            require("TTS reader state: reading" not in text, "Successful operation resumed continuous reading")
            after = self.p.mark()
            self.observed("Result remains paused after PCM drain", optional=True)
            require("TTS reader cursor:" not in self.p.text(after), "Paused feedback advanced the document cursor")
            if identifier == "LANG_TTS_FIND":
                self.accepted_query = value
        else:
            self.leave_menu()
            if origin is not None:
                require(self.cursor() == origin, "Failed operation moved the observed cursor")
        return text

    def document_bytes(self):
        return {CASE_NAME: CASE_BYTES, LINE_NAME: LINE_BYTES, EMPTY_NAME: b"",
                BOM_NAME: b"\xef\xbb\xbf", CACHE_NAME: CACHE_BYTES}[self.document]

    def go(self, percent):
        data = self.document_bytes()
        target = len(data) if percent == 100 else (3 if data.startswith(b"\xef\xbb\xbf") else 0)
        return self.operation("LANG_TTS_GOTO_PERCENT", str(percent), "LANG_TTS_GOTO_PERCENT", target)

    def close_document(self):
        self.leave_menu()
        self.observed("Close current reader", lambda: self.p.chord("Insert", "Left"), optional=True)
        self.accepted_query = ""

    def properties(self, expected_offset, size):
        self.open_menu()
        self.row("LANG_PROPERTIES")
        self.observed("Open spoken properties", lambda: self.p.press("Right"))
        for unused in range(3):
            self.p.row("Next spoken property")
        position_text = self.p.latest
        require(spoken_position(position_text, self.p.status_labels, self.indices_enabled) == (expected_offset, size),
                "Spoken Properties disagrees with expected byte position")
        self.observed("Leave properties", lambda: self.p.press("Left"), (self.labels["LANG_PROPERTIES"],))
        self.leave_menu()
        return position_text

    def resume_from(self, offset):
        marker = self.p.mark()
        def resume_and_pause():
            self.p.press("Insert")
            text = self.wait_log(marker, lambda text:
                re.search(r"TTS reader state: reading offset=" + str(offset) + r"\s", text) and
                any(int(value) > offset for value in re.findall(r"TTS reader cursor: (\d+)", text)),
                "tracked resume from selected offset")
            require("TTS: synthesis failed" not in text, "Resume failed synthesis")
            self.p.hold_context()
        self.observed("Resume tracked text then pause at heard progress", resume_and_pause,
                      (self.labels["LANG_TTS_RESUME"],))
        self.in_menu = True
        self.leave_menu()

    def new_session_query_required(self):
        self.go(0)
        self.operation("LANG_TTS_FIND_NEXT", expected="LANG_TTS_QUERY_REQUIRED")

    def case_and_wrap_effects(self, case, wrap):
        self.go(0)
        found = CASE_UPPER if case else CASE_LOWER
        self.operation("LANG_TTS_FIND", "ŻÓŁĆ", "LANG_TTS_FOUND", found)
        self.properties(found, len(CASE_BYTES))
        nine = CASE_BYTES.index(("ĄĆĘŁŃÓŚŹŻ" if case else "ąćęłńóśźż").encode("utf-8"))
        self.go(0)
        self.operation("LANG_TTS_FIND", "ĄĆĘŁŃÓŚŹŻ", "LANG_TTS_FOUND", nine)
        self.go(0)
        self.operation("LANG_TTS_FIND", "zolc" if case else "ZOLC",
                       "LANG_TTS_FOUND", CASE_BYTES.index(b"zolc"))
        self.go(100)
        if wrap == 0:
            self.operation("LANG_TTS_FIND", "solo", "LANG_TTS_NO_MORE_MATCHES")
            self.go(0)
            self.operation("LANG_TTS_FIND", "solo", "LANG_TTS_FOUND", SOLO)
            self.operation("LANG_TTS_FIND_NEXT", expected="LANG_TTS_NO_MORE_MATCHES")
        elif wrap == 1:
            self.operation("LANG_TTS_FIND", "solo", "LANG_TTS_NO_MORE_MATCHES", wrap_answer="no")
            self.operation("LANG_TTS_FIND", "solo", "LANG_TTS_FOUND_WRAPPED", SOLO, wrap_answer="yes")
            self.operation("LANG_TTS_FIND_NEXT", expected="LANG_TTS_NO_MORE_MATCHES", wrap_answer="no")
        else:
            self.operation("LANG_TTS_FIND", "solo", "LANG_TTS_FOUND_WRAPPED", SOLO)
            self.operation("LANG_TTS_FIND_NEXT", expected="LANG_TTS_FOUND_WRAPPED", offset=SOLO)
        self.resume_from(SOLO)

    def reader_regressions(self):
        self.go(0)
        self.operation("LANG_TTS_FIND", "aba", "LANG_TTS_FOUND", OVERLAP)
        self.operation("LANG_TTS_FIND_NEXT", expected="LANG_TTS_FOUND", offset=OVERLAP + 2)
        self.operation("LANG_TTS_FIND_PREVIOUS", expected="LANG_TTS_FOUND", offset=OVERLAP)
        self.operation("LANG_TTS_FIND", "QQQ", "LANG_TTS_NO_MORE_MATCHES")
        self.go(0)
        self.operation("LANG_TTS_FIND_NEXT", expected="LANG_TTS_FOUND", offset=OVERLAP)
        self.operation("LANG_TTS_FIND", "solo", abort=True)
        self.go(0)
        self.operation("LANG_TTS_FIND_NEXT", expected="LANG_TTS_FOUND", offset=OVERLAP)
        self.operation("LANG_TTS_FIND", "", "LANG_TTS_QUERY_INVALID")
        self.bookmark_and_boundaries()
        self.close_document()
        self.open_document(LINE_NAME)
        self.go(0)
        for ordinal, target in enumerate(LINE_STARTS, 1):
            self.operation("LANG_TTS_GOTO_LINE", str(ordinal), "LANG_TTS_GOTO_LINE", target)
        for value in ("", "0", "8", "18446744073709551616"):
            self.operation("LANG_TTS_GOTO_LINE", value, "LANG_TTS_DESTINATION_INVALID")
        for ordinal, target in ((1, 3), (2, 7), (4, 21)):
            self.operation("LANG_TTS_GOTO_PAGE", str(ordinal), "LANG_TTS_GOTO_PAGE", target)
        self.operation("LANG_TTS_GOTO_PAGE", "5", "LANG_TTS_DESTINATION_INVALID")
        self.operation("LANG_TTS_GOTO_PERCENT", "22", "LANG_TTS_GOTO_PERCENT", 4)
        self.operation("LANG_TTS_GOTO_PERCENT", "35", "LANG_TTS_GOTO_PERCENT", 7)
        self.operation("LANG_TTS_GOTO_PERCENT", "101", "LANG_TTS_DESTINATION_INVALID")
        self.operation("LANG_TTS_GOTO_LINE", "3", abort=True)
        self.go(100)
        self.go(0)
        self.close_document()
        self.open_document(CACHE_NAME)
        self.go(0)
        self.operation("LANG_TTS_FIND", "Żółć", "LANG_TTS_FOUND", 766)
        self.close_document()
        for name, first in ((EMPTY_NAME, 0), (BOM_NAME, 3)):
            self.open_document(name)
            self.operation("LANG_TTS_GOTO_LINE", "1", "LANG_TTS_DESTINATION_INVALID")
            self.operation("LANG_TTS_GOTO_PAGE", "1", "LANG_TTS_DESTINATION_INVALID")
            self.go(0)
            self.go(100)
            self.close_document()
        self.open_document(CASE_NAME)
        self.go(0)

    def bookmark_and_boundaries(self):
        saved = self.cursor()
        self.open_menu()
        self.row("LANG_BOOKMARK_MENU")
        self.observed("Open shared text bookmarks", lambda: self.p.press("Right"),
                      (self.labels["LANG_BOOKMARK_MENU_CREATE"],))
        marker = self.p.mark()
        self.observed("Create real text bookmark", lambda: self.p.press("Right"),
                      (self.labels["LANG_BOOKMARK_CREATE_SUCCESS"],))
        require(re.search(r"TTS reader bookmark saved: 1 offset=" + str(saved) + r"\s",
                          self.p.text(marker)), "Bookmark did not save the actual paused position")
        entries = bookmark_entries(self.p.base.runtime / "simdisk" / (CASE_NAME + ".bmark"))
        require(len(entries) == 1 and entries[0]["offset"] == saved and entries[0]["size"] == len(CASE_BYTES),
                "Actual T1 bookmark differs from the selected document position")
        self.observed("Leave bookmark submenu", lambda: self.p.press("Left"), (self.labels["LANG_BOOKMARK_MENU"],))
        self.leave_menu()
        for identifier, offset in (("LANG_TTS_BEGINNING", 3), ("LANG_TTS_END", len(CASE_BYTES))):
            self.open_menu()
            self.row(identifier)
            self.observed("Use existing " + identifier, lambda: self.p.press("Right"), optional=True)
            self.in_menu = False
            self.properties(offset, len(CASE_BYTES))
        self.open_menu()
        self.row("LANG_BOOKMARK_MENU")
        self.observed("Reopen shared bookmarks", lambda: self.p.press("Right"),
                      (self.labels["LANG_BOOKMARK_MENU_CREATE"],))
        self.p.row("Select existing bookmark list", expected=(self.labels["LANG_BOOKMARK_MENU_LIST"],))
        self.observed("Open actual local T1 list", lambda: self.p.press("Right"),
                      (self.labels["LANG_TTS_TEXT_BOOKMARK"],))
        marker = self.p.mark()
        self.observed("Restore actual local T1 position", lambda: self.p.press("Right"),
                      (self.labels["LANG_BOOKMARK_MENU"],))
        require(re.search(r"TTS reader bookmark restored: " + str(saved) + r"\s", self.p.text(marker)),
                "Existing bookmark restore did not report the saved byte position")
        self.leave_menu()
        self.properties(saved, len(CASE_BYTES))

    def list_indices_setting(self, enabled):
        self.close_document()
        self.observed("Return to root menu", lambda: self.p.press("Left"), (self.labels["LANG_DIR_BROWSER"],))
        self.in_browser = False
        for identifier in ("LANG_SETTINGS", "LANG_GENERAL_SETTINGS", "LANG_VOICE", "LANG_TALKBOX_SETTINGS"):
            self.p.enter(identifier)
        self.p.enter("LANG_TALKBOX_ANNOUNCE_POSITION")
        identifier = "LANG_TALKBOX_POSITION_EXCEPT_SLIDERS" if enabled else "LANG_OFF"
        # The previous accepted choice is Off or Except sliders; only one step.
        self.p.row("Choose actual list-position policy", "Up" if enabled else "Down",
                   (self.labels[identifier],))
        self.observed("Accept list-position policy", lambda: self.p.press("Right"))
        self.indices_enabled = enabled
        for unused in range(4):
            self.observed("Return towards root after list policy", lambda: self.p.press("Left"), optional=True)
        self.open_document(CASE_NAME)
        self.go(0)

    def usb_case(self, location, pair):
        self.go(0)
        if location == "ask":
            self.go(100)
        self.open_menu()
        identifier = {"query": "LANG_TTS_FIND", "numeric": "LANG_TTS_GOTO_LINE",
            "case": "LANG_TTS_SEARCH_CASE", "wrap": "LANG_TTS_SEARCH_WRAP",
            "ask": "LANG_TTS_FIND"}[location]
        self.row(identifier)
        self.observed("USB site " + location, lambda: self.p.press("Right"),
            (self.labels[identifier],) if location not in ("case", "wrap") else ())
        if location in ("query", "numeric", "ask"):
            self.edit("solo" if location == "ask" else "2" if location == "numeric" else "QQQ",
                      "" if location == "numeric" else self.accepted_query, location == "numeric")
        if location == "ask":
            self.observed("USB at actual Ask confirmation",
                lambda: self.p.keyboard_chord("Insert", "Right"), (self.labels["LANG_TTS_WRAP_QUESTION"],))
        elif location in ("case", "wrap"):
            # Move, but do not accept, the ordinary chooser.
            self.p.row("Move unaccepted choice before USB", "Up" if pair[0 if location == "case" else 1] else "Down")
        before = canonical(*pair)
        marker = self.p.mark()
        self.p.usb_toggle(True)
        self.wait_log(marker, lambda text: "USB inserted. Waiting for " in text, "queued USB connection")
        time.sleep(0.3)
        self.p.usb_toggle(False)
        self.observed("Observe return after simulator USB triggers", optional=True)
        require("TTS reader cursor:" not in self.p.text(marker), "USB interaction published a cursor commit")
        require((self.p.base.runtime / "simdisk/.rockbox/tts-reader.cfg").read_bytes() == before,
                "USB persisted a moved or edited choice")
        sidecar(self.p.base.runtime, pair)
        self.in_menu = False
        self.in_browser = True
        self.open_document(CASE_NAME)
        self.new_session_query_required()
        self.p.report.setdefault("usb_reader_cases", []).append({
            "site": location, "passed": True, "exact_close_count_observed": False,
            "query_reset_after_new_reader": True, "no_observed_commit": True,
            "trigger_logs_only": True, "browser_return_and_new_reader_observed": True})

    def music_case(self):
        self.close_document()
        self.p.report["music"] = True
        self.open_document(MUSIC_NAME)
        self.observed("Return from WPS to files", lambda: self.p.keyboard_chord("Left", "Right"), optional=True)
        self.in_browser = True
        self.open_document(CASE_NAME)
        self.go(0)
        start = len(self.p.report["checks"])
        self.operation("LANG_TTS_FIND", "ŻÓŁĆ", "LANG_TTS_FOUND", CASE_UPPER)
        self.go(100)
        for record in self.p.report["checks"][start:]:
            if record["name"].startswith("Actual result"):
                text = self.p.log.read_bytes()[record["log_start"]:record["log_end"]].decode("utf-8", errors="replace")
                require("TTS audio playback: 1" in text and "TTS audio playback: 0" not in text,
                        "Background playback stopped during a reader result")
                record["reader_music_continuity_required"] = True


def verify_session_pcm(probe, report):
    # The exclusive master is inspected only after this owned child exits.
    data = probe.pcm.read_bytes()
    require(len(data) % 4 == 0 and services.pcm_statistics(data)["nonzero_samples"] >= 128,
            "Missing complete nonzero master PCM")
    report["pcm_sha256"] = hashlib.sha256(data).hexdigest()
    for record in report["checks"]:
        start, end = record["pcm_start"], record["pcm_end"]
        require(0 <= start <= end <= len(data) and record["passed"], "Incomplete action observation")
        record["pcm"] = services.pcm_statistics(data[start:end])
        if not record.get("optional_speech") and not record["silent"]:
            require(record["pcm"]["nonzero_samples"] >= 128, "Spoken action has no nonzero actual PCM")
        if record["silent"] and not record["music_at_capture"]:
            require(record["pcm"]["nonzero_samples"] == 0, "Silent action emitted unexpected speech PCM")


def run_four_processes(native, desktop, desktop_handle, runtime, directory, language, labels, layout, timeout, budget):
    report = {"language": language, "prepared_once": True, "sessions": [],
              "restart_verified": False, "passed": False}
    pids = []
    for stage, case, wrap, next_case, next_wrap in STAGES:
        destination = directory / stage
        destination.mkdir()
        session = {"language": language, "stage": stage, "desktop": desktop,
            "checks": [], "raw_input": [], "sessions": [], "music": False,
            "input_layout": layout, "action_budget_seconds": budget,
            "restart_verified": False, "passed": False, "expected_start": [case, wrap]}
        report["sessions"].append(session)
        probe = ReaderProbe(native, desktop, runtime, destination, session, labels, timeout)
        try:
            if stage == "A":
                sidecar(runtime, absent=True)
            else:
                session["canonical_before_launch"] = sidecar(runtime, (case, wrap))
            probe.launch(desktop_handle)
            require(probe.process.pid not in pids, "A restart did not produce a distinct PID")
            pids.append(probe.process.pid)
            ui = ReaderUI(probe)
            ui.open_document()
            ui.new_session_query_required()
            ui.menu_inventory()
            ui.preference("case", case)
            ui.preference("wrap", wrap)
            before = None if stage == "A" else canonical(case, wrap)
            ui.preference("case", case, cancel_moved=True)
            require((runtime / "simdisk/.rockbox/tts-reader.cfg").read_bytes() == before
                    if before is not None else not (runtime / "simdisk/.rockbox/tts-reader.cfg").exists(),
                    "Cancel accepted a moved preference")
            ui.case_and_wrap_effects(case, wrap)
            session["restart_verified"] = stage != "A"
            session["preferences_after_effects"] = sidecar(runtime, (case, wrap), absent=stage == "A")
            if next_case is not None:
                ui.preference("case", case, choose=next_case)
                session["case_save"] = sidecar(runtime, (next_case, wrap))
                ui.preference("wrap", wrap, choose=next_wrap)
                session["wrap_save_existing_primary"] = sidecar(runtime, (next_case, next_wrap))
            else:
                ui.reader_regressions()
                ui.list_indices_setting(False)
                ui.preference("case", case)
                ui.preference("wrap", wrap)
                ui.list_indices_setting(True)
                ui.preference("case", case)
                ui.preference("wrap", wrap)
                ui.preference("wrap", wrap, choose=1)
                sidecar(runtime, (case, 1))
                for location in ("query", "numeric", "case", "wrap", "ask"):
                    ui.usb_case(location, (case, 1))
                ui.preference("wrap", 1, choose=0)
                sidecar(runtime, (case, 0))
                ui.music_case()
            probe.close()
            verify_session_pcm(probe, session)
            for record in session["checks"]:
                if record.get("reader_music_continuity_required"):
                    record["tone_997_amplitude"] = tone_amplitude(probe.pcm, record["pcm_start"], record["pcm_end"])
                    require(record["tone_997_amplitude"] > 1, "No actual 997 Hz music during reader result")
            session["passed"] = True
        except BaseException as error:
            session.update(error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
            raise
        finally:
            unwinding = sys.exc_info()[0] is not None
            cleanup_errors = []
            if probe.process is not None and probe.process.poll() is None:
                try:
                    probe.close()
                except BaseException as error:
                    session["graceful_cleanup_error"] = f"{type(error).__name__}: {error}"
                    try:
                        if probe.process.poll() is None:
                            probe.process.terminate()
                        probe.process.wait(timeout=12)
                    except BaseException as terminate_error:
                        cleanup_errors.append("terminate: " + str(terminate_error))
            # A child can exit during launch or an action, before close() runs.
            # Always release its read-only process-memory handle independently.
            if probe.memory is not None:
                try:
                    probe.memory.close()
                    probe.memory = None
                except BaseException as error:
                    cleanup_errors.append("memory: " + str(error))
            session["memory_handle_closed"] = probe.memory is None
            child_exited = probe.process is None or probe.process.poll() is not None
            if probe.process is not None:
                try:
                    require(child_exited, "Child remains alive; parent job must end it")
                    if not session.get("launch", {}).get("handle_collected"):
                        handle = getattr(probe.process, "_handle", None)
                        require(handle is not None, "Missing owned process handle")
                        handle.Close()
                        session.setdefault("launch", {})["handle_collected"] = True
                except BaseException as error:
                    cleanup_errors.append("process-handle: " + str(error))
            if child_exited:
                for source, name in ((probe.log, "simulator.log"), (probe.observation, "observation.raw")):
                    try:
                        if source.exists():
                            target = destination / name
                            require(not target.exists(), "Refusing prior evidence overwrite")
                            source.rename(target)
                            session.setdefault("retained_evidence", {})[name] = {
                                "path": str(target), "sha256": digest(target)}
                    except BaseException as error:
                        cleanup_errors.append("evidence " + name + ": " + str(error))
            session["cleanup_errors"] = cleanup_errors
            session["passed"] = session["passed"] and not cleanup_errors
            write_json(destination / "session.json", session)
            if not unwinding:
                require(not cleanup_errors, "Child cleanup failed: " + repr(cleanup_errors))
    report["restart_verified"] = len(pids) == len(set(pids)) == 4 and all(
        session["restart_verified"] and session["passed"] for session in report["sessions"][1:])
    report["passed"] = report["restart_verified"] and all(session["passed"] for session in report["sessions"])
    write_json(directory / "language-result.json", report)
    return report



def worker(arguments):
    native = services.PrivateDesktop()
    require(re.fullmatch(r"RBReader_[0-9a-f]{32}", arguments.desktop or "") and arguments.gate,
            "Missing private worker desktop/start gate")
    native.assert_private(arguments.desktop)
    require(native.kernel.WaitForSingleObject(arguments.gate, 30000) == 0, "Parent job gate was not released")
    native.checked(native.kernel.CloseHandle(arguments.gate))
    central = project_materials_root(ROOT) / SCOPE
    descriptor_path = confined_path(arguments.descriptor, central)
    require(services.sha256_value(arguments.descriptor_sha256) and
            digest(descriptor_path) == arguments.descriptor_sha256, "Worker descriptor changed")
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    require(descriptor["scope"] == SCOPE and descriptor["exe_sha256"] == arguments.exe_sha256 and
            descriptor["freeze_sha256"] == arguments.freeze_sha256 and descriptor["reader_patch_sha256"] == READER_PATCH,
            "Private worker authorization changed")
    require(descriptor["input_layout"]["sha256"] == arguments.exe_sha256, "Unbound input layout")
    directory = confined_path(Path(descriptor["directory"]), central)
    runtime = confined_path(Path(descriptor["runtime"]), directory)
    language = descriptor["language"]
    require(language in ("polski", "english") and runtime == directory / "fixture", "Wrong language runtime")
    desktop_handle = native.checked(native.user.GetThreadDesktop(native.kernel.GetCurrentThreadId()))
    report = {"scope": SCOPE, "passed": False, "language": language, "desktop": arguments.desktop,
        "input_desktop_before": native.input(), "limitations": LIMITATIONS}
    try:
        report["result"] = run_four_processes(native, arguments.desktop, desktop_handle, runtime,
            directory, language, descriptor["labels"], descriptor["input_layout"],
            arguments.timeout, arguments.session_budget)
        report["input_desktop_after"] = native.input()
        require(report["input_desktop_before"] == report["input_desktop_after"], "User input desktop changed")
        report["passed"] = report["result"]["passed"]
    except BaseException as error:
        report.update(error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
    finally:
        write_json(directory / "worker.json", report)
    return 0 if report["passed"] else 1


def execute(arguments):
    require(sys.platform == "win32", "Run with native Windows Python only")
    require(10 <= arguments.timeout <= 60 and 60 <= arguments.session_budget <= 3600 and
            120 <= arguments.overall_timeout <= 10800, "Invalid explicit timeout bounds")
    freeze, build = validate_authorization(arguments)
    native = services.PrivateDesktop()
    labels = compiled_labels(build)
    layout = services.prepare_input_layout(build / "rockboxui.exe", arguments.exe_sha256)
    central = project_materials_root(ROOT)
    results = confined_path(central / SCOPE /
        (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]), central)
    results.mkdir(parents=True, exist_ok=False)
    report = {"scope": SCOPE, "passed": False, "restart_verified": False, "languages": [],
        "version": freeze["version"], "freeze_sha256": arguments.freeze_sha256,
        "exe_sha256": arguments.exe_sha256, "reader_patch_sha256": READER_PATCH,
        "source_bindings": freeze["sources"], "no_global_input": True,
        "private_desktop_only": True, "input_desktop_before": native.input(),
        "limitations": LIMITATIONS, "deterministic_long_scan_usb": "not_supported_by_current_gui_seam"}
    overall_deadline = time.monotonic() + arguments.overall_timeout
    try:
        for language in ("polski", "english"):
            require(time.monotonic() < overall_deadline, "Overall reader GUI budget expired")
            directory = results / language
            directory.mkdir()
            item = {"language": language, "checks": [], "copies": [], "passed": False,
                    "worker_handle_closed": False, "gate_closed": False, "desktop_closed": False}
            report["languages"].append(item)
            runtime = prepare_language(build, directory, language, labels[language], item)
            descriptor = {"scope": SCOPE, "language": language, "directory": str(directory),
                "runtime": str(runtime), "labels": labels[language], "input_layout": layout,
                "exe_sha256": arguments.exe_sha256, "freeze_sha256": arguments.freeze_sha256,
                "reader_patch_sha256": READER_PATCH, "prepared_once": True}
            descriptor_path = directory / "worker-descriptor.json"
            write_json(descriptor_path, descriptor)
            descriptor_sha = digest(descriptor_path)
            loan = ExecutableLoan(build, directory, item)
            desktop = "RBReader_" + uuid.uuid4().hex
            process = job = desktop_handle = gate = None
            cleanup = []
            try:
                loan.move_to(runtime)
                require(loan.original_hash == arguments.exe_sha256, "EXE changed before owned loan")
                desktop_handle = native.checked(native.user.CreateDesktopW(
                    desktop, None, None, 0, native.access, None))
                gate = native.checked(native.kernel.CreateEventW(None, True, False, None))
                native.checked(native.kernel.SetHandleInformation(gate, 1, 1))
                startup = native.inherited_startup(desktop_handle)
                startup.lpAttributeList["handle_list"].append(int(gate))
                job = services.OwnedJob(native)
                command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker",
                    "--desktop", desktop, "--gate", str(int(gate)), "--descriptor", str(descriptor_path),
                    "--descriptor-sha256", descriptor_sha, "--exe-sha256", arguments.exe_sha256,
                    "--freeze-sha256", arguments.freeze_sha256, "--timeout", str(arguments.timeout),
                    "--session-budget", str(arguments.session_budget)]
                with (directory / "worker.log").open("x", encoding="utf-8") as output:
                    process = subprocess.Popen(command, cwd=directory, startupinfo=startup, close_fds=True,
                        creationflags=subprocess.CREATE_NO_WINDOW, stdout=output, stderr=subprocess.STDOUT)
                    item["worker_pid"] = process.pid
                    job.assign(process)
                    native.checked(native.kernel.SetEvent(gate))
                    process.wait(timeout=max(1, overall_deadline - time.monotonic()))
                item["worker_exit_code"] = process.returncode
                item["worker"] = json.loads((directory / "worker.json").read_text(encoding="utf-8"))
                require(type(process.returncode) is int and process.returncode == 0 and item["worker"]["passed"],
                        "Private reader worker failed")
                item["passed"] = True
            except BaseException as error:
                item.update(error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
                raise
            finally:
                # Terminate the owned job/collect worker, then close all parent
                # native handles BEFORE restoring the executable loan.
                if job is not None:
                    try:
                        job.close()
                        item["owned_job_closed"] = True
                    except BaseException as error:
                        cleanup.append("job: " + str(error))
                if process is not None:
                    try:
                        if process.poll() is None:
                            process.terminate()
                        process.wait(timeout=15)
                        item["worker_actual_exit"] = process.returncode
                        process._handle.Close()
                        item["worker_handle_closed"] = True
                    except BaseException as error:
                        cleanup.append("worker: " + str(error))
                if gate is not None:
                    try:
                        native.checked(native.kernel.CloseHandle(gate))
                        item["gate_closed"] = True
                    except BaseException as error:
                        cleanup.append("gate: " + str(error))
                if desktop_handle is not None:
                    try:
                        native.checked(native.user.CloseDesktop(desktop_handle))
                        item["desktop_closed"] = True
                    except BaseException as error:
                        cleanup.append("desktop: " + str(error))
                if not cleanup:
                    try:
                        loan.restore(process)
                        require(loan.record["restored"], "Executable loan was not restored")
                    except BaseException as error:
                        cleanup.append("restore: " + str(error))
                item["cleanup_errors"] = cleanup
                item["passed"] = item["passed"] and not cleanup
                write_json(directory / "parent-language.json", item)
                require(not cleanup, "Owned cleanup failed; loan retained for diagnosis: " + repr(cleanup))
        report["input_desktop_after"] = native.input()
        require(report["input_desktop_before"] == report["input_desktop_after"], "User input desktop changed")
        # These whole-build checks occur only after BOTH language loans restore.
        services.bound_checks(ROOT, freeze["sources"])
        services.bound_checks(build, freeze["build_files"])
        report["restart_verified"] = all(item["worker"]["result"]["restart_verified"] for item in report["languages"])
        report["passed"] = len(report["languages"]) == 2 and report["restart_verified"] and all(
            item["passed"] for item in report["languages"])
    except BaseException as error:
        report.update(error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
    finally:
        write_json(results / "report.json", report)
    print(json.dumps({"passed": report["passed"], "restart_verified": report["restart_verified"],
        "results": str(results), "error": report.get("error")}), flush=True)
    return 0 if report["passed"] else 1


class ReaderDriverContracts(unittest.TestCase):
    def test_prepare_language_seeds_context_hold_profile_once(self):
        from tempfile import TemporaryDirectory

        documents = {CASE_NAME: CASE_BYTES, LINE_NAME: LINE_BYTES, EMPTY_NAME: b"",
                     BOM_NAME: b"\xef\xbb\xbf", CACHE_NAME: CACHE_BYTES}
        central = project_materials_root(ROOT).resolve()
        with TemporaryDirectory(prefix="reader-seed-contract-", dir=central) as temporary:
            temporary = Path(temporary).resolve()
            self.assertEqual(temporary.parent, central)
            for language in ("polski", "english"):
                with self.subTest(language=language):
                    directory = temporary / language
                    runtime = directory / "fixture"
                    resources = runtime / "simdisk/.rockbox"
                    resources.mkdir(parents=True)
                    build, report = temporary / "unread-build", {}
                    with mock.patch.object(services, "prepare_runtime", return_value=runtime) as prepare, \
                            mock.patch.object(services, "make_tone") as tone:
                        result = prepare_language(build, directory, language, {}, report)
                        self.assertEqual(result, runtime)
                        prepare.assert_called_once_with(build, directory, report)
                        tone.assert_called_once_with(runtime / "simdisk" / MUSIC_NAME)

                        profile = (resources / "accessibility.cfg").read_bytes()
                        parsed = services.parse_mapping_profile(profile)
                        original = services.parse_mapping_profile(
                            services.mapping_profile(services.mapping_contract()).encode("utf-8"))
                        self.assertEqual(parsed, dict(original, enabled=True, hold_ms=300))
                        seeded = report["seeded_once"]
                        self.assertEqual(seeded["language"], language)
                        self.assertIs(seeded["query_injection"], False)
                        self.assertIs(seeded["reader_preferences_injection"], False)
                        self.assertEqual(set(seeded["profiles"]),
                                         {"config.cfg", "accessibility.cfg", "accessibility-typing.cfg"})
                        for name, text in seeded["profiles"].items():
                            self.assertEqual((resources / name).read_bytes(), text.encode("utf-8"))
                        config = seeded["profiles"]["config.cfg"]
                        self.assertTrue(config.startswith(services.synthetic_config(language, True, True)))
                        self.assertEqual(seeded["profiles"]["accessibility-typing.cfg"],
                                         "RBACCESSIBILITY-TYPING:1\nmode:2\n")
                        self.assertEqual(seeded["documents"], {
                            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                            for name, data in documents.items()})
                        for name, data in documents.items():
                            self.assertEqual((runtime / "simdisk" / name).read_bytes(), data)
                        self.assertEqual(
                            {path.relative_to(runtime).as_posix()
                             for path in runtime.rglob("*") if path.is_file()},
                            {"simdisk/.rockbox/" + name for name in seeded["profiles"]} |
                            {"simdisk/" + name for name in documents})
                        self.assertEqual(json.loads((directory / "initial-profile.json").read_text(
                            encoding="utf-8")), seeded)

                        before = {path.relative_to(directory).as_posix(): path.read_bytes()
                                  for path in directory.rglob("*") if path.is_file()}
                        with self.assertRaisesRegex(AssertionError, "Refusing synthetic profile overwrite"):
                            prepare_language(build, directory, language, {}, report)
                        self.assertEqual(
                            {path.relative_to(directory).as_posix(): path.read_bytes()
                             for path in directory.rglob("*") if path.is_file()}, before)
                        tone.assert_called_once_with(runtime / "simdisk" / MUSIC_NAME)

    def test_music_expectation_changes_at_actual_wav_launch_capture(self):
        # Exercise music_case through its real open_document selection/capture.
        # The observer models the existing settle contract: music may be
        # expected only after the action has actually started the WAV.
        probe = mock.Mock()
        probe.music_expected = False
        probe.labels = {"VOICE_OF": "of"}
        probe.report = {"checks": []}
        probe.latest = ("TTS: " + MUSIC_NAME + " 6 of 6\n" +
                        "TTS utterance: " + MUSIC_NAME + " 6 of 6\n")
        probe.log.read_bytes.return_value = b"TTS audio playback: 1\n"
        ui = object.__new__(ReaderUI)
        ui.p, ui.labels, ui.in_browser = probe, probe.labels, True
        ui.in_menu, ui.indices_enabled = False, True
        started, observations = [False], []

        def capture(name, action=None, *unused, **kwargs):
            if name == "Home synthetic file list":
                self.assertFalse(started[0])
                self.assertFalse(probe.music_expected)
            if action:
                action()
            self.assertEqual(probe.music_expected, started[0])
            observations.append((name, probe.music_expected))
            return probe.latest

        def press(key):
            if key == "Right":
                started[0] = True
            else:
                self.assertEqual(key, "Up")

        probe.capture.side_effect = capture
        probe.row.side_effect = lambda *unused, **kwargs: probe.latest
        probe.press.side_effect = press
        actual_open = ui.open_document

        def open_document(name=CASE_NAME):
            if name == MUSIC_NAME:
                actual_open(name)
            else:
                self.assertEqual(name, CASE_NAME)
                self.assertTrue(started[0])
                self.assertTrue(probe.music_expected)

        def actual_result(*unused, **kwargs):
            probe.report["checks"].append({"name": "Actual result ordering fixture",
                                          "log_start": 0, "log_end": 22})

        ui.open_document = mock.Mock(side_effect=open_document)
        ui.close_document = mock.Mock()
        ui.go = mock.Mock(side_effect=actual_result)
        ui.operation = mock.Mock(side_effect=actual_result)
        ui.music_case()
        self.assertLess(observations.index(("Home synthetic file list", False)),
                        observations.index(("Open synthetic music", True)))
        self.assertTrue(probe.report["music"])
        self.assertTrue(all(check.get("reader_music_continuity_required")
                            for check in probe.report["checks"][1:]))

    def test_four_launches_cover_real_restart_choices(self):
        self.assertEqual([(row[1], row[2]) for row in STAGES], [(0, 0), (1, 1), (0, 2), (1, 0)])
        self.assertEqual([row[0] for row in STAGES], list("ABCD"))
        self.assertEqual([row[3:5] for row in STAGES[:-1]], [(1, 1), (0, 2), (1, 0)])

    def test_canonical_choices_are_exact_and_bounded(self):
        self.assertEqual(canonical(0, 0), b"RBTTSREADER:1\ncase:0\nwrap:0\n")
        self.assertEqual(len(canonical(1, 2)), 28)
        for pair in ((2, 0), (0, 3), (-1, 0)):
            with self.assertRaises(AssertionError):
                canonical(*pair)

    def test_independent_utf8_fixture_offsets(self):
        self.assertEqual(CASE_LOWER, 3)
        self.assertEqual(CASE_UPPER, 12)
        self.assertEqual(CASE_BYTES[CASE_UPPER:CASE_UPPER + 8], "ŻÓŁĆ".encode())
        self.assertEqual([LINE_BYTES[start:].decode("utf-8")[0] for start in LINE_STARTS],
                         ["a", "\r", "ż", "b", "c", "d", "e"])
        self.assertEqual(CACHE_BYTES[766:774], "Żółć".encode())

    def test_file_selection_joins_both_ordered_traces_in_pl_and_en(self):
        for connector in ("z", "of"):
            for name in (CASE_NAME, MUSIC_NAME):
                suffix = f"3 {connector} 6"
                for split_prefix in ("TTS", "TTS utterance"):
                    with self.subTest(connector=connector, name=name, split_prefix=split_prefix):
                        traces = []
                        for prefix in ("TTS", "TTS utterance"):
                            if prefix == split_prefix:
                                traces.extend((f"{prefix}: {name}", f"{prefix}: {suffix}"))
                            else:
                                traces.append(f"{prefix}: {name} {suffix}")
                        self.assertEqual(current_file_selection("\n".join(traces), connector, True),
                                         services.normalized(name))

    def test_file_selection_without_indices_keeps_txt_and_wav_extensions(self):
        for connector in ("z", "of"):
            for name in (CASE_NAME, MUSIC_NAME):
                text = f"TTS: {name}\nTTS utterance: {name}\n"
                self.assertEqual(current_file_selection(text, connector, False), services.normalized(name))
                shorter = name.rsplit(".", 1)[0]
                missing_ext = f"TTS: {shorter}\nTTS utterance: {shorter}\n"
                self.assertNotEqual(current_file_selection(missing_ext, connector, False),
                                    services.normalized(name))

    def test_file_selection_rejects_missing_wrong_and_disabled_indices(self):
        for connector, wrong in (("z", "of"), ("of", "z")):
            suffixes = ("", f" 0 {connector} 6", f" 7 {connector} 6",
                        f" 1 {connector} 0", f" 01 {connector} 6",
                        f" 3 {wrong} 6", f" 3 {connector} 6 trailing")
            for suffix in suffixes:
                with self.subTest(connector=connector, suffix=suffix):
                    text = f"TTS: {CASE_NAME}{suffix}\nTTS utterance: {CASE_NAME}{suffix}\n"
                    with self.assertRaises(AssertionError):
                        current_file_selection(text, connector, True)
            text = f"TTS: {CASE_NAME} 3 {connector} 6\nTTS utterance: {CASE_NAME} 3 {connector} 6\n"
            with self.assertRaises(AssertionError):
                current_file_selection(text, connector, False)

    def test_file_selection_rejects_missing_and_disagreeing_traces(self):
        for connector in ("z", "of"):
            cases = (
                f"TTS: {CASE_NAME} 3 {connector} 6\n",
                f"TTS utterance: {CASE_NAME} 3 {connector} 6\n",
                f"TTS: {CASE_NAME} 3 {connector} 6\nTTS utterance: {MUSIC_NAME} 3 {connector} 6\n",
                f"TTS: {CASE_NAME} 3 {connector} 6\nTTS utterance: {CASE_NAME} 4 {connector} 6\n",
                f"TTS: {CASE_NAME} 3 {connector} 6\nTTS utterance: {CASE_NAME} 3 {connector} 7\n",
                f"TTS: 3 {connector} 6\nTTS: {CASE_NAME}\n"
                f"TTS utterance: 3 {connector} 6 {CASE_NAME}\n")
            for text in cases:
                with self.subTest(connector=connector, text=text):
                    with self.assertRaises(AssertionError):
                        current_file_selection(text, connector, True)

    def test_spoken_position_accepts_pl_en_segmented_and_merged_four_of_five(self):
        for title, unit, connector in (("Pozycja", "bajtów", "z"), ("Position", "bytes", "of")):
            labels = {"LANG_TTS_POSITION": title, "LANG_TTS_BYTES": unit, "VOICE_OF": connector}
            row, suffix = f"{title}: 12%, 12 / 100 {unit}", f"4 {connector} 5"
            for split_prefix in ("TTS", "TTS utterance"):
                traces = []
                for prefix in ("TTS", "TTS utterance"):
                    if prefix == split_prefix:
                        traces.extend((f"{prefix}: {row}", f"{prefix}: {suffix}"))
                    else:
                        traces.append(f"{prefix}: {row} {suffix}")
                with self.subTest(connector=connector, split_prefix=split_prefix):
                    self.assertEqual(spoken_position("\n".join(traces), labels, True), (12, 100))

    def test_spoken_position_off_requires_no_suffix_in_both_languages(self):
        for title, unit, connector in (("Pozycja", "bajtów", "z"), ("Position", "bytes", "of")):
            labels = {"LANG_TTS_POSITION": title, "LANG_TTS_BYTES": unit, "VOICE_OF": connector}
            row = f"{title}: 12%, 12 / 100 {unit}"
            text = f"TTS: {row}\nTTS utterance: {row}\n"
            self.assertEqual(spoken_position(text, labels, False), (12, 100))
            indexed = f"TTS: {row} 4 {connector} 5\nTTS utterance: {row} 4 {connector} 5\n"
            with self.assertRaises(AssertionError):
                spoken_position(indexed, labels, False)

    def test_spoken_position_rejects_missing_wrong_and_noncanonical_suffix(self):
        for title, unit, connector, wrong in (
                ("Pozycja", "bajtów", "z", "of"), ("Position", "bytes", "of", "z")):
            labels = {"LANG_TTS_POSITION": title, "LANG_TTS_BYTES": unit, "VOICE_OF": connector}
            row = f"{title}: 12%, 12 / 100 {unit}"
            for suffix in ("", f" 4 {connector} 6", f" 3 {connector} 5",
                           f" 04 {connector} 5", f" 4 {connector} 05",
                           f" 4 {wrong} 5", f" 4 {connector} 5 trailing"):
                with self.subTest(connector=connector, suffix=suffix):
                    text = f"TTS: {row}{suffix}\nTTS utterance: {row}{suffix}\n"
                    with self.assertRaises(AssertionError):
                        spoken_position(text, labels, True)

    def test_spoken_position_rejects_missing_trace_and_offset_size_disagreement(self):
        for title, unit, connector in (("Pozycja", "bajtów", "z"), ("Position", "bytes", "of")):
            labels = {"LANG_TTS_POSITION": title, "LANG_TTS_BYTES": unit, "VOICE_OF": connector}
            row = f"{title}: 12%, 12 / 100 {unit} 4 {connector} 5"
            for other in (
                    f"{title}: 12%, 13 / 100 {unit} 4 {connector} 5",
                    f"{title}: 12%, 12 / 101 {unit} 4 {connector} 5",
                    f"{title}: 13%, 12 / 100 {unit} 4 {connector} 5",
                    f"{title}: 12%, 12 / 100 {unit}"):
                with self.subTest(connector=connector, other=other):
                    with self.assertRaises(AssertionError):
                        spoken_position(f"TTS: {row}\nTTS utterance: {other}\n", labels, True)
            for text in (f"TTS: {row}\n", f"TTS utterance: {row}\n"):
                with self.assertRaises(AssertionError):
                    spoken_position(text, labels, True)

    def test_aborted_keyboard_rejects_fresh_position_jump_or_new_commit(self):
        labels = {"LANG_TTS_POSITION": "Position", "LANG_TTS_BYTES": "bytes", "VOICE_OF": "of"}
        def properties(offset, size=100, indexed=False):
            suffix = " 4 of 5" if indexed else ""
            value = f"Position: {offset * 100 // size}%, {offset} / {size} bytes{suffix}"
            return f"TTS: {value}\nTTS utterance: {value}\n"
        for indexed in (False, True):
            with self.subTest(indexed=indexed):
                require_abort_observation("", properties(12, indexed=indexed), labels, 12, 100, indexed)
                with self.assertRaises(AssertionError):
                    require_abort_observation("", properties(13, indexed=indexed), labels, 12, 100, indexed)
                with self.assertRaises(AssertionError):
                    require_abort_observation("", properties(112, 200, indexed), labels, 12, 200, indexed)
                with self.assertRaises(AssertionError):
                    require_abort_observation("TTS reader cursor: 13\n",
                                              properties(12, indexed=indexed), labels, 12, 100, indexed)
                with self.assertRaises(AssertionError):
                    require_abort_observation("", properties(12, indexed=not indexed),
                                              labels, 12, 100, indexed)

    def test_usb_key_uses_only_an_owned_hwnd(self):
        from test_tts_simulator import WindowsBackend
        backend = object.__new__(WindowsBackend)
        backend.owns_window = mock.Mock(return_value=True)
        backend.user32 = mock.Mock()
        backend.user32.PostMessageW.return_value = 1
        backend.key_event(123, 456, "c", True)
        backend.key_event(123, 456, "c", False)
        calls = backend.user32.PostMessageW.call_args_list
        self.assertEqual(calls[0].args[:3], (456, 0x0100, 0x43))
        self.assertEqual(calls[1].args[:3], (456, 0x0101, 0x43))
        self.assertTrue(calls[1].args[3] & (1 << 31))
        self.assertEqual(backend.owns_window.call_args_list, [mock.call(123, 456), mock.call(123, 456)])

    def test_usb_key_rejects_a_changed_window_owner(self):
        from test_tts_simulator import WindowsBackend
        backend = object.__new__(WindowsBackend)
        backend.owns_window = mock.Mock(return_value=False)
        backend.user32 = mock.Mock()
        with self.assertRaises(RuntimeError):
            backend.key_event(123, 456, "c", False)
        backend.user32.PostMessageW.assert_not_called()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    modes = result.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    modes.add_argument("--readiness", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    result.add_argument("--build-ready", action="store_true")
    result.add_argument("--freeze", type=Path)
    result.add_argument("--freeze-sha256")
    result.add_argument("--exe-sha256")
    result.add_argument("--timeout", type=float, default=45)
    result.add_argument("--session-budget", type=float, default=3600)
    result.add_argument("--overall-timeout", type=float, default=10800)
    result.add_argument("--desktop", help=argparse.SUPPRESS)
    result.add_argument("--gate", type=int, help=argparse.SUPPRESS)
    result.add_argument("--descriptor", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--descriptor-sha256", help=argparse.SUPPRESS)
    return result


def main(argv=None):
    arguments = parser().parse_args(argv)
    if arguments.worker:
        return worker(arguments)
    if arguments.self_test:
        # Resolve the real central workspace before blocking test processes.
        # WSL drive discovery uses read-only Windows volume queries.
        project_materials_root(ROOT)
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("Contract tests cannot launch processes")):
            result = unittest.TextTestRunner(verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(ReaderDriverContracts))
        return 0 if result.wasSuccessful() else 1
    if not arguments.execute:
        print(json.dumps({"scope": SCOPE, "executed": False, "reader_patch_sha256": READER_PATCH,
            "required_sources": SOURCE_PATHS, "stages_per_language": STAGES,
            "version_requirement": "match services.EXPECTED_VERSION after the proper harness update",
            "required_freeze": ["scope", "version", "reader_patch_sha256", "with_music",
                                "exe_sha256", "build", "sources", "build_files"],
            "limitations": LIMITATIONS}, indent=2))
        return 0
    return execute(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
