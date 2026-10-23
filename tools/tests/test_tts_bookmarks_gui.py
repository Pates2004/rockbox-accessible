"""Exercise text bookmarks through the actual native Windows Sansa simulator UI.

Run only after the owner supplies a stable updated build/fullinstall, for example:
  python -B tools/tests/test_tts_bookmarks_gui.py --build D:/work/Workspace/rockbox/build-espeak-windows --language polski --build-ready
  python -B tools/tests/test_tts_bookmarks_gui.py --build D:/work/Workspace/rockbox/build-espeak-windows-clipzip --language english --build-ready --with-music

No build, installed release or existing profile is modified. Following the recorder
GUI fixture, the development EXE is temporarily renamed into a marked synthetic
fixture and restored with its original identity and hash. It is never copied.
Immutable runtime copies, synthetic documents/profile, PCM, complete session logs
and the requirement/evidence report remain under Workspace for reproduction.
The report distinguishes logged synthesis, verified mixer PCM and untested human
listening/NVDA behavior. Menu titles are identified from compiled catalogs and
the ordered spoken rows; this test does not read pixels or require spoken titles.
"""

import argparse
import array
import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import wave

from test_tts_recorder_gui import (
    ExecutableLoan, RUNTIME_DIRECTORIES, contained, digest, display_labels, pcm_summary,
)
from test_tts_simulator import catalog_labels, find_window, send_key, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = "001 Bookmark document.txt"
MUSIC = "002 Bookmark music.wav"
READER_ROWS = (
    "LANG_TTS_RESUME", "LANG_BOOKMARK_MENU", "LANG_PROPERTIES", "LANG_TTS_BEGINNING",
    "LANG_TTS_END", "LANG_TTS_READER_SETTINGS", "LANG_TTS",
    "LANG_TTS_FIND", "LANG_TTS_FIND_NEXT", "LANG_TTS_FIND_PREVIOUS",
    "LANG_TTS_GOTO_LINE", "LANG_TTS_GOTO_PAGE", "LANG_TTS_GOTO_PERCENT",
    "LANG_TTS_SEARCH_CASE", "LANG_TTS_SEARCH_WRAP",
)
REQUIRED_LABELS = READER_ROWS + (
    "LANG_DIR_BROWSER", "LANG_TTS_READER_MENU", "LANG_BOOKMARK_MENU_CREATE",
    "LANG_BOOKMARK_MENU_LIST", "LANG_TTS_TEXT_BOOKMARK", "LANG_BOOKMARK_CONTEXT_RESUME",
    "LANG_DELETE", "LANG_REALLY_DELETE", "LANG_BOOKMARK_MENU_RECENT_BOOKMARKS",
    "LANG_TTS_BOOKMARK_CHANGED", "LANG_PROPERTIES_FILENAME", "LANG_PROPERTIES_PATH",
    "LANG_PROPERTIES_SIZE", "LANG_TTS_POSITION", "LANG_TTS_BYTES",
    "LANG_TTS_READER_UNIT", "LANG_TTS_UNIT_WORD", "LANG_NOTHING_TO_RESUME",
    "LANG_TTS_IGNORE_CASE", "LANG_TTS_MATCH_CASE", "LANG_TTS_WRAP_STOP",
    "LANG_TTS_WRAP_ASK", "LANG_TTS_WRAP_AUTO", "LANG_TTS_WRAP_QUESTION",
    "LANG_TTS_FOUND", "LANG_TTS_FOUND_WRAPPED", "LANG_TTS_NO_MORE_MATCHES",
)
KEYS = ("Up", "Down", "Left", "Right", "space", "Insert", "Escape")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def phrases(text, prefix="TTS"):
    return [phrase.removesuffix("\r") for phrase in
            re.findall(r"^" + re.escape(prefix) + r": (.*)$", text, re.MULTILINE)]


def has_speech(text, fragments):
    segments = " ".join(phrases(text))
    utterances = " ".join(phrases(text, "TTS utterance"))
    return bool(utterances) and all(fragment in segments and fragment in utterances
                                   for fragment in fragments)


def bookmark_entries(path):
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        fields = line.split(";", 5)
        require(len(fields) == 6 and fields[0] == "T1", f"Unexpected bookmark record: {line!r}")
        require(all(re.fullmatch(r"[0-9]+", field) for field in fields[1:5]),
                f"Nondecimal bookmark field: {line!r}")
        offset, size, unit, signature = map(int, fields[1:5])
        require(0 <= offset <= size and 0 <= unit <= 4 and signature <= 0xffffffff,
                f"Invalid text bookmark fields: {line!r}")
        entries.append(dict(offset=offset, size=size, unit=unit, signature=signature,
                            path=fields[5], line=line))
    return entries


def prepare_fixture(build, results, language, report, target_name=None, voice_files_disabled=False):
    information = contained(build / "rockbox-info.txt", build).read_text(encoding="utf-8")
    targets = "hibyr1" if target_name == "hibyr1" else "sansaclipplus|sansaclipzip"
    target = re.search(r"^Target: (" + targets + r")\s*$", information, re.MULTILINE)
    require(target is not None, "The selected Windows development target does not match the fixture")
    report["target"] = target.group(1)
    executable = contained(build / "rockboxui.exe", build)
    with executable.open("rb") as source:
        require(source.read(2) == b"MZ", "Expected a native Windows executable")
    windows_backend().ensure_unused(executable)
    voice = catalog_labels(build, language)
    displayed = display_labels(build, language)
    labels = {}
    for identifier in REQUIRED_LABELS:
        require(bool(displayed.get(identifier)), f"Missing compiled display label: {identifier}")
        labels[identifier] = voice.get(identifier) or displayed[identifier]
    expected_title = "Opcje tekstu" if language == "polski" else "Text options"
    require(displayed["LANG_TTS_READER_MENU"] == expected_title, "Unexpected text menu title")
    report.update(labels=labels, display_labels={name: displayed[name] for name in REQUIRED_LABELS},
                  menu_title=expected_title, menu_title_evidence="compiled catalog plus ordered spoken rows")
    report["catalog_inputs"] = [
        {"source": str(contained(path, build)), "sha256": digest(path)}
        for path in (build / "lang_enum.h", build / "apps/lang" / f"{language}.lng",
                     build / "apps/lang" / f"{language}.vstrings")]
    runtime = results / "fixture"
    runtime.mkdir()
    resources = runtime / "simdisk/.rockbox"
    resources.mkdir(parents=True)
    report["fixture"] = str(runtime)

    def copy_asset(source, destination):
        source = contained(source, build)
        if source.is_dir():
            destination.mkdir()
            for child in sorted(source.iterdir()):
                copy_asset(child, destination / child.name)
            return
        require(source.is_file() and source.suffix.lower() != ".exe",
                f"Unsupported runtime asset (EXE must never be copied): {source}")
        require(not destination.exists() and runtime in destination.resolve().parents,
                f"Unsafe copy destination: {destination}")
        before = digest(source)
        shutil.copy2(source, destination)
        require(digest(source) == before == digest(destination), f"Runtime asset changed: {source}")
        report["copies"].append(dict(source=str(source), destination=str(destination), sha256=before,
                                     purpose="isolated text bookmark GUI reproduction",
                                     retained_after_test=True))

    print(f"Copying immutable runtime assets to {runtime}; no existing profile is copied. "
          "The EXE will be moved and restored, never copied. Assets, synthetic profile, "
          "documents, logs and PCM remain in Workspace as regression evidence.", flush=True)
    for library in sorted(build.glob("*.dll")):
        copy_asset(library, runtime / library.name)
    copy_asset(build / "UI256.bmp", runtime / "UI256.bmp")
    source_resources = contained(build / "simdisk/.rockbox", build)
    for name in RUNTIME_DIRECTORIES:
        copy_asset(source_resources / name, resources / name)
    for name in ("viewers.config", "tagnavi.config", "rockbox-info.txt"):
        copy_asset(source_resources / name, resources / name)
    for extension in ("lng", "vstrings"):
        installed = resources / "langs" / f"{language}.{extension}"
        compiled = build / "apps/lang" / f"{language}.{extension}"
        require(installed.is_file() and digest(installed) == digest(compiled),
                f"Installed {language}.{extension} is stale; refresh fullinstall before testing")
    write_json(runtime / ".tts-bookmarks-gui-fixture.json", dict(
        purpose="Synthetic text bookmark GUI fixture; no user data", source_build=str(build),
        language=language, retained_after_test=True))
    recorded_voice = ("talk menu: off\ntalk dir: off\ntalk file: off\ntalk mixer level: 0\n"
                      if voice_files_disabled else
                      "talk menu: on\ntalk dir: spell\ntalk file: spell\n")
    report["voice_files_disabled"] = voice_files_disabled
    (resources / "config.cfg").write_text(
        f"lang: /.rockbox/langs/{language}.lng\n"
        "start in screen: root\nshow files: all\nsort case: off\n"
        + recorded_voice +
        "talk dir clip: off\ntalk file clip: off\n"
        "tts enabled: on\ntts language: system\ntts variant: \n"
        "tts rate: 175\ntts pitch: 50\ntts volume: 100\ntts range: 50\n"
        "tts wordgap: 0\ntts reader unit: word\ntts reader page lines: 20\n"
        "use most-recent-bookmarks: on\nautoload bookmarks: off\nautocreate bookmarks: off\n"
        "volume: -25\nrepeat: one\nshuffle: off\nbacklight filters first keypress: off\n",
        encoding="utf-8")
    sentence = ("Próba zakładek. Żółw czyta długi dokument i zapamiętuje pozycję. "
                if language == "polski" else
                "Bookmark exercise. The reader speaks a long document and remembers its position. ")
    document = sentence * 240 + "\n"
    (runtime / "simdisk" / DOCUMENT).write_bytes(document.encode("utf-8"))
    report["synthetic_document"] = dict(path=DOCUMENT, bytes=len(document.encode("utf-8")),
                                         sha256=digest(runtime / "simdisk" / DOCUMENT))
    return runtime, labels, displayed, document.encode("utf-8")


class GuiProbe:
    def __init__(self, runtime, results, report, timeout):
        self.runtime = runtime
        self.results = results
        self.report = report
        self.timeout = timeout
        self.log = runtime / "simulator.log"
        self.process = None
        self.window = None
        self.environment = None
        self.session = None
        self.held = set()
        self.music = False

    def text(self, start=0):
        return self.log.read_bytes()[start:].decode("utf-8", errors="replace") if self.log.exists() else ""

    def mark(self):
        return self.log.stat().st_size if self.log.exists() else 0

    def check_alive(self):
        require(self.process is not None and self.process.poll() is None,
                f"Owned simulator exited unexpectedly: {self.process.returncode if self.process else None}")

    def launch(self, name):
        require(self.process is None or self.process.poll() is not None, "Previous owned process is still running")
        require(not self.log.exists(), "Previous complete simulator log must be preserved before restart")
        require((self.runtime / ".tts-bookmarks-gui-fixture.json").is_file(), "Missing synthetic fixture marker")
        executable = contained(self.runtime / "rockboxui.exe", self.results)
        windows_backend().ensure_unused(executable)
        self.environment = dict(os.environ, SDL_VIDEODRIVER="windows", SDL_AUDIODRIVER="disk",
                                SDL_DISKAUDIOFILE=str(self.runtime / f"{name}-audio.raw"),
                                SDL_DISKAUDIODELAY="12")
        self.session = dict(name=name, pcm=self.environment["SDL_DISKAUDIOFILE"], checks=[])
        self.report["sessions"].append(self.session)
        self.process = subprocess.Popen(
            [str(executable), "--root", str(self.runtime / "simdisk"), "--audiodev",
             self.environment["SDL_DISKAUDIOFILE"], "--debugbuttons"],
            cwd=self.runtime, env=self.environment, stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        self.session["pid"] = self.process.pid
        self.window = find_window(self.process.pid, self.environment)

    def press(self, key, hold=0.12):
        self.check_alive()
        self.held.add(key)
        try:
            send_key(self.process.pid, self.window, key, True, self.environment)
            time.sleep(hold)
        finally:
            if self.process.poll() is None:
                send_key(self.process.pid, self.window, key, False, self.environment)
            self.held.discard(key)

    def wait(self, predicate, start, description):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            self.check_alive()
            text = self.text(start)
            require("TTS: synthesis failed" not in text, "Speech synthesis failed")
            if predicate(text):
                return text
            time.sleep(0.1)
        raise AssertionError(f"Missing {description}; session log tail:\n{self.text(start)[-2200:]}")

    def settle(self):
        deadline = time.monotonic() + self.timeout
        last_change = time.monotonic()
        previous = self.mark()
        while time.monotonic() < deadline:
            self.check_alive()
            current = self.mark()
            if current != previous:
                previous = current
                last_change = time.monotonic()
            utterances = phrases(self.text(), "TTS utterance")
            duration = 0.8 + len(utterances[-1]) / 8 if utterances else 0.8
            if time.monotonic() - last_change >= duration:
                return
            time.sleep(0.1)
        raise AssertionError("UI speech did not settle; reader may have resumed accidentally")

    def capture(self, name, action, predicate, speech=True, initial=False, settle=True, start=None):
        marker = (0 if initial else self.mark()) if start is None else start
        pcm = Path(self.session["pcm"])
        pcm_start = 0 if initial or not pcm.exists() else pcm.stat().st_size
        observation = dict(name=name, status="in_progress", session=self.session["name"],
                           log_start=marker, pcm_start=pcm_start,
                           speech_required=speech, music_required=self.music)
        self.report["checks"].append(observation)
        self.session["checks"].append(name)
        try:
            if action is not None:
                action()
            self.wait(predicate, marker, name)
            if settle:
                self.settle()
            observation["status"] = "logged_pending_pcm" if speech else "passed"
        except (Exception, KeyboardInterrupt) as error:
            observation.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            text = self.text(marker)
            observation.update(log_end=self.mark(), segments=phrases(text),
                               utterances=phrases(text, "TTS utterance"),
                               pcm_end=pcm.stat().st_size if pcm.exists() else 0)
            if self.music and speech and observation["status"] == "logged_pending_pcm":
                if "TTS audio playback: 1" not in text or "TTS audio playback: 0" in text:
                    observation.update(status="failed", error="Background playback stopped during UI speech")
                    raise AssertionError(observation["error"])
        return observation

    def speech(self, name, action, *fragments, initial=False):
        return self.capture(name, action, lambda text: has_speech(text, fragments), initial=initial)

    def seek(self, label, start=0, maximum=35):
        for attempt in range(maximum):
            segments = phrases(self.text(start))
            if segments and label in segments[-1]:
                return
            start = self.mark()
            self.capture(f"seek {label}: Down {attempt + 1}", lambda: self.press("Down"),
                         lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
        raise AssertionError(f"Cannot find spoken row: {label!r}")

    def cancel(self, name):
        self.capture(name, lambda: self.press("Escape"), lambda text: True, speech=False, settle=False)
        time.sleep(0.4)

    def open_reader_menu(self, labels, key="space"):
        observation = self.speech(f"long {key} opens text options", lambda: self.press(key, 1.2),
                                  labels["LANG_TTS_RESUME"])
        self.assert_menu_stayed_open(observation["log_start"])
        return observation["log_start"]

    def assert_menu_stayed_open(self, start):
        text = self.text(start)
        require("TTS reader unit:" not in text, "Long press changed the reader unit")
        require("TTS reader state: reading" not in text, "Key release accidentally resumed reading")
        require("TTS reader bookmark saved:" not in text, "Key release accidentally created a bookmark")

    def reader_row(self, labels, index):
        for row in range(1, index + 1):
            self.speech(f"text options row {row}", lambda: self.press("Down"), labels[READER_ROWS[row]])

    def local_list(self, labels):
        self.open_reader_menu(labels)
        self.reader_row(labels, 1)
        self.speech("open bookmark submenu", lambda: self.press("space"), labels["LANG_BOOKMARK_MENU_CREATE"])
        self.speech("bookmark submenu row 1 List", lambda: self.press("Down"), labels["LANG_BOOKMARK_MENU_LIST"])
        self.speech("open existing shared local bookmark list", lambda: self.press("space"),
                    labels["LANG_TTS_TEXT_BOOKMARK"])

    def close(self, graceful=True):
        if self.process is None:
            return
        errors = []
        try:
            if self.process.poll() is None:
                for key in KEYS:
                    try:
                        if self.window is not None:
                            send_key(self.process.pid, self.window, key, False, self.environment)
                    except (OSError, RuntimeError) as error:
                        errors.append(str(error))
                self.held.clear()
                if graceful and self.window is not None:
                    try:
                        shutdown(self.process, self.window, self.environment)
                    except Exception as error:
                        errors.append(str(error))
                if self.process.poll() is None:
                    self.session["forced_owned_process_cleanup"] = True
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=8)
        finally:
            self.session["exit_code"] = self.process.poll()
            if errors:
                self.session["cleanup_errors"] = errors
            if self.process.poll() is not None and self.log.exists():
                destination = self.results / f"{self.session['name']}-simulator.log"
                require(not destination.exists(), f"Refusing to overwrite log: {destination}")
                self.log.rename(destination)
                self.session.update(log=str(destination), log_sha256=digest(destination))
            if self.process.poll() is not None:
                self.window = None
        if graceful:
            require(not errors and self.process.returncode == 0 and
                    not self.session.get("forced_owned_process_cleanup"), "Graceful simulator shutdown failed")


def startup(probe, language):
    speech_language = "pl" if language == "polski" else "en"
    probe.capture("startup speech with isolated language/profile", None,
                  lambda text: bool(phrases(text, "TTS utterance")) and
                  f"TTS parameters: language={speech_language} " in text and
                  "volume=100" in text, initial=True)


def open_document(probe, labels):
    probe.seek(labels["LANG_DIR_BROWSER"])
    start = probe.mark()
    probe.capture("enter Files", lambda: probe.press("space"),
                  lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    probe.seek(DOCUMENT.removesuffix(".txt"), start)
    probe.capture("read document with advancing audible cursor", lambda: probe.press("space"),
                  lambda text: len(set(re.findall(r"TTS reader cursor: (\d+)", text))) >= 3 and
                  bool(phrases(text, "TTS utterance")), settle=False)


def properties(probe, labels, displayed, offset, document_size):
    probe.open_reader_menu(labels)
    probe.reader_row(labels, 2)
    expected = (
        (displayed["LANG_PROPERTIES_FILENAME"] + ":", DOCUMENT),
        (displayed["LANG_PROPERTIES_PATH"] + ":", "/" + DOCUMENT),
        (displayed["LANG_PROPERTIES_SIZE"] + ":", str(document_size), displayed["LANG_TTS_BYTES"]),
        (displayed["LANG_TTS_POSITION"] + ":", f"{offset} / {document_size}", displayed["LANG_TTS_BYTES"]),
        (displayed["LANG_TTS_READER_UNIT"] + ":", displayed["LANG_TTS_UNIT_WORD"]),
    )
    for index, fragments in enumerate(expected):
        key = "space" if index == 0 else "Down"
        probe.speech(f"property {index}: {fragments[0]}", lambda key=key: probe.press(key), *fragments)
    probe.cancel("leave properties")
    probe.cancel("leave text options after properties")


def local_bookmarks(probe, labels, displayed, document_bytes, report):
    probe.launch("create-and-restore")
    startup(probe, report["language"])
    open_document(probe, labels)
    navigation = probe.capture("holding Up changes units instead of opening a menu",
        lambda: probe.press("Up", 1.2), lambda text: "TTS reader unit:" in text)
    require(labels["LANG_TTS_RESUME"] not in navigation["segments"],
            "Up unexpectedly opened the text context menu")
    for attempt in range(5):
        units = re.findall(r"TTS reader unit: (\d+)", probe.text())
        if units and int(units[-1]) == 1:
            break
        probe.capture(f"restore word unit after Up hold {attempt + 1}", lambda: probe.press("Up"),
                      lambda text: "TTS reader unit:" in text)
    else:
        raise AssertionError("Cannot restore word navigation after Up hold")
    menu_start = probe.open_reader_menu(labels)
    for index in range(1, len(READER_ROWS)):
        probe.speech(f"ordered text options row {index}", lambda: probe.press("Down"), labels[READER_ROWS[index]])
    for index in range(len(READER_ROWS) - 2, -1, -1):
        probe.speech(f"text options return to row {index}", lambda: probe.press("Up"), labels[READER_ROWS[index]])
    probe.assert_menu_stayed_open(menu_start)
    cursor_matches = re.findall(r"TTS reader cursor: (\d+)", probe.text())
    require(bool(cursor_matches), "No audible cursor evidence before saving")
    audible_offset = int(cursor_matches[-1])
    require(0 < audible_offset < len(document_bytes), "Audible cursor was not inside the document")
    probe.reader_row(labels, 1)
    probe.speech("Bookmarks contains Create at index 0", lambda: probe.press("space"),
                 labels["LANG_BOOKMARK_MENU_CREATE"])
    saved = probe.capture("create bookmark at interrupted audible cursor", lambda: probe.press("space"),
                          lambda text: re.search(r"TTS reader bookmark saved: 1 offset=\d+", text) is not None,
                          speech=False)
    saved_offset = int(re.search(r"TTS reader bookmark saved: 1 offset=(\d+)",
                                 probe.text(saved["log_start"])).group(1))
    require(saved_offset == audible_offset, "Saved position differs from the final playback-linked cursor")
    local = probe.runtime / "simdisk" / (DOCUMENT + ".bmark")
    recent = probe.runtime / "simdisk/.rockbox/most-recent.bmark"
    entries = bookmark_entries(local)
    require(len(entries) == 1, "Expected exactly one persistent local text bookmark")
    bookmark = entries[0]
    require(bookmark["offset"] == saved_offset and bookmark["size"] == len(document_bytes) and
            bookmark["unit"] == 1 and bookmark["path"] == "/" + DOCUMENT,
            "Persistent T1 fields differ from the synthetic reader state")
    require(bookmark_entries(recent) == entries, "usemrb=on did not persist the same T1 recent bookmark")
    document_bytes[:saved_offset].decode("utf-8")
    document_bytes[saved_offset:].decode("utf-8")
    report["saved_bookmark"] = dict(bookmark, local_sha256=digest(local), recent_sha256=digest(recent))
    probe.cancel("leave bookmark submenu after Create")
    probe.cancel("leave text options after Create")
    probe.open_reader_menu(labels, "space")
    probe.speech("long Select leaves bookmark choice reachable", lambda: probe.press("Down"),
                 labels["LANG_BOOKMARK_MENU"])
    probe.cancel("leave text options after long Select")
    properties(probe, labels, displayed, saved_offset, len(document_bytes))
    for attempt in range(3):
        probe.capture(f"navigate away from bookmark {attempt + 1}", lambda: probe.press("Right"),
                      lambda text: re.search(r"TTS reader cursor: (\d+)", text) is not None)
    displaced = int(re.findall(r"TTS reader cursor: (\d+)", probe.text())[-1])
    require(displaced > saved_offset, "Navigation did not move away from the bookmark")
    probe.capture("change unit before restore", lambda: probe.press("Up"),
                  lambda text: "TTS reader unit: 2 " in text)
    probe.local_list(labels)
    probe.speech("shared bookmark context row 0 Resume", lambda: probe.press("space", 1.2),
                 labels["LANG_BOOKMARK_CONTEXT_RESUME"])
    probe.speech("shared bookmark context row 1 Delete", lambda: probe.press("Down"), labels["LANG_DELETE"])
    probe.speech("shared bookmark context return to Resume", lambda: probe.press("Up"),
                 labels["LANG_BOOKMARK_CONTEXT_RESUME"])
    probe.capture("restore local bookmark through shared context Resume", lambda: probe.press("space"),
                  lambda text: re.search(r"TTS reader bookmark restored: " + str(saved_offset) + r"\s", text)
                  is not None, speech=False)
    probe.cancel("leave text options after restoring local bookmark")
    properties(probe, labels, displayed, saved_offset, len(document_bytes))
    probe.close()
    require(bookmark_entries(local) == entries == bookmark_entries(recent), "Bookmarks changed during shutdown")
    configuration = (probe.runtime / "simdisk/.rockbox/config.cfg").read_text(encoding="utf-8")
    require("use most-recent-bookmarks: on" in configuration and "tts reader unit: word" in configuration,
            "Bookmark policy or restored unit did not survive shutdown")
    report["checks"].append(dict(name="persistent local and recent T1 records after clean shutdown", status="passed"))
    return bookmark


def recent_list(probe, labels):
    probe.seek(labels["LANG_BOOKMARK_MENU_RECENT_BOOKMARKS"])
    probe.speech("open shared global recent bookmark list", lambda: probe.press("space"),
                 labels["LANG_TTS_TEXT_BOOKMARK"])


def restart_and_delete(probe, labels, bookmark, report):
    probe.launch("restart-and-delete")
    startup(probe, report["language"])
    recent_list(probe, labels)
    offset = bookmark["offset"]
    restored = probe.capture("restart restores exact position from global recent list", lambda: probe.press("space"),
                             lambda text: re.search(r"TTS reader bookmark restored: " + str(offset) + r"\s", text)
                             is not None and "TTS reader state: reading" in text and
                             bool(phrases(text, "TTS utterance")), settle=False)
    probe.capture("restored reading cursor continues after restart", None,
                  lambda text: any(int(value) > offset for value in re.findall(r"TTS reader cursor: (\d+)", text)),
                  speech=False, settle=False, start=restored["log_start"])
    probe.capture("pause restarted reader", lambda: probe.press("space"),
                  lambda text: "TTS reader state: paused" in text, speech=False, settle=False)
    require("TTS reader unit:" not in probe.text(restored["log_start"]), "Restore unexpectedly changed the saved unit")
    probe.local_list(labels)
    probe.speech("open shared context for local deletion", lambda: probe.press("space", 1.2),
                 labels["LANG_BOOKMARK_CONTEXT_RESUME"])
    probe.speech("select shared context Delete", lambda: probe.press("Down"), labels["LANG_DELETE"])
    probe.speech("deletion asks for confirmation", lambda: probe.press("space"), labels["LANG_REALLY_DELETE"])
    local = probe.runtime / "simdisk" / (DOCUMENT + ".bmark")
    probe.capture("confirm Delete removes persistent local T1 entry", lambda: probe.press("space"),
                  lambda text: not bookmark_entries(local), speech=False)
    recent = probe.runtime / "simdisk/.rockbox/most-recent.bmark"
    require(bookmark_entries(recent) == [dict(bookmark)], "Deleting a local entry unexpectedly changed recent history")
    probe.close()
    require(not bookmark_entries(local), "Deleted local bookmark returned after shutdown")


def reject_changed_document(probe, labels, document_bytes, report):
    document = contained(probe.runtime / "simdisk" / DOCUMENT, probe.results)
    require(digest(document) == report["synthetic_document"]["sha256"], "Synthetic source text changed unexpectedly")
    changed = bytes([ord("X")]) + document_bytes[1:]
    require(len(changed) == len(document_bytes) and changed != document_bytes, "Invalid mismatch fixture")
    document.write_bytes(changed)
    report["mismatch_fixture"] = dict(path=str(document), original_sha256=report["synthetic_document"]["sha256"],
                                      changed_sha256=digest(document), same_byte_length=True,
                                      mutation="replace first ASCII byte; invalidate stored context signature")
    probe.launch("changed-document-rejection")
    startup(probe, report["language"])
    recent_list(probe, labels)
    rejected = probe.speech("changed same-size document is rejected with spoken error", lambda: probe.press("space"),
                            labels["LANG_TTS_BOOKMARK_CHANGED"])
    require("TTS reader bookmark restored:" not in probe.text(rejected["log_start"]),
            "Changed document was restored despite identity mismatch")
    require("TTS reader state: reading" not in probe.text(rejected["log_start"]),
            "Changed document began reading despite bookmark rejection")
    probe.close()
    require(bookmark_entries(probe.runtime / "simdisk/.rockbox/most-recent.bmark")[0]["line"] ==
            report["saved_bookmark"]["line"], "Rejecting a changed document damaged the stored bookmark")


def music_properties(probe, labels, displayed, document_bytes, report):
    document = contained(probe.runtime / "simdisk" / DOCUMENT, probe.results)
    document.write_bytes(document_bytes)
    tone = array.array("h", (int(6000 * math.sin(2 * math.pi * 997 * sample / 44100))
                              for sample in range(44100)))
    if sys.byteorder != "little":
        tone.byteswap()
    with wave.open(str(probe.runtime / "simdisk" / MUSIC), "wb") as output:
        output.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        for second in range(30):
            output.writeframesraw(tone.tobytes())
    report["synthetic_music"] = dict(path=MUSIC, frequency_hz=997, repeat="one", duration_seconds=30)
    probe.launch("background-music-properties")
    startup(probe, report["language"])
    probe.seek(labels["LANG_DIR_BROWSER"])
    start = probe.mark()
    probe.capture("enter Files for synthetic WAV", lambda: probe.press("space"),
                  lambda text: bool(phrases(text)) and bool(phrases(text, "TTS utterance")))
    probe.seek(MUSIC.removesuffix(".wav"), start)
    probe.capture("start synthetic WAV through normal player", lambda: probe.press("space"),
                  lambda text: True, speech=False, settle=False)
    time.sleep(1)
    probe.music = True
    probe.capture("return to main menu with ongoing playback", lambda: probe.press("Insert"),
                  lambda text: "TTS audio playback: 1" in text and bool(phrases(text, "TTS utterance")))
    open_document(probe, labels)
    probe.open_reader_menu(labels)
    cursor = int(re.findall(r"TTS reader cursor: (\d+)", probe.text())[-1])
    probe.cancel("leave text options before music property checks")
    properties(probe, labels, displayed, cursor, len(document_bytes))
    probe.close()
    probe.music = False


def tone_amplitude(path, start, stop):
    amplitudes = []
    with path.open("rb") as source:
        source.seek(start - start % 4)
        while source.tell() + 16384 <= stop:
            samples = array.array("h", source.read(16384))
            if sys.byteorder != "little":
                samples.byteswap()
            mono = samples[::2]
            peaks = []
            for frequency in (911, 997, 1103):
                real = sum(value * math.cos(2 * math.pi * frequency * index / 44100)
                           for index, value in enumerate(mono))
                imaginary = sum(value * math.sin(2 * math.pi * frequency * index / 44100)
                                for index, value in enumerate(mono))
                peaks.append(2 * math.hypot(real, imaginary) / len(mono))
            if peaks[1] > 3 * max(peaks[0], peaks[2], 0.1):
                amplitudes.append(peaks[1])
    return max(amplitudes, default=0)


def verify_evidence(report):
    changed = [item["source"] for item in report["copies"] + report.get("catalog_inputs", [])
               if not Path(item["source"]).is_file() or digest(Path(item["source"])) != item["sha256"]]
    report["changed_source_assets"] = changed
    require(not changed, "Immutable source runtime assets changed during the test")
    session_errors = []
    for session in report["sessions"]:
        pcm = Path(session["pcm"])
        session["clean_exit"] = session.get("exit_code") == 0 and not session.get("forced_owned_process_cleanup")
        if not session["clean_exit"]:
            session_errors.append(f"Session did not exit cleanly: {session['name']}")
        require(bool(session.get("log")), f"Complete session log missing: {session['name']}")
        text = Path(session["log"]).read_text(encoding="utf-8", errors="replace")
        require("TTS: synthesis failed" not in text, f"Synthesis failed during session: {session['name']}")
        empty_wps_label = report.get("labels", {}).get("LANG_NOTHING_TO_RESUME")
        session["unexpected_empty_wps"] = bool(empty_wps_label and empty_wps_label in " ".join(phrases(text)))
        if session["unexpected_empty_wps"]:
            session_errors.append(f"Text bookmark returned to empty audio WPS: {session['name']}")
        session["pcm_summary"] = pcm_summary(pcm)
        require(session["pcm_summary"]["nonzero_samples"] >= 128, "Session contains no meaningful mixer audio")
        for check in report["checks"]:
            if check.get("session") != session["name"] or not check.get("speech_required"):
                continue
            statistics = pcm_summary(pcm, check["pcm_start"], check["pcm_end"])
            check["pcm"] = statistics
            if statistics["nonzero_samples"] < 128 or statistics["peak"] < 32:
                check.update(status="failed", error="Logged speech lacks meaningful mixer PCM in its action interval")
            elif check["status"] == "logged_pending_pcm":
                check["status"] = "passed"
            if check.get("music_required"):
                amplitude = tone_amplitude(pcm, check["pcm_start"], check["pcm_end"])
                check["background_997hz_amplitude"] = amplitude
                if amplitude < 5:
                    check.update(status="failed", error="Background 997 Hz music missing from the mixed action interval")
    require(not session_errors, "; ".join(session_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", type=Path, required=True, help="Stable fullinstalled development build inside Workspace")
    parser.add_argument("--language", choices=("polski", "english"), default="polski")
    parser.add_argument("--build-ready", action="store_true", help="Owner has finished and released the updated build for testing")
    parser.add_argument("--with-music", action="store_true", help="Also check property speech over repeating synthetic WAV playback")
    parser.add_argument("--voice-files-disabled", action="store_true", help="Require eSpeak speech with recorded interface/name speech disabled and recorded volume zero")
    parser.add_argument("--timeout", type=float, default=30, help="Per-observation timeout, between 10 and 60 seconds")
    arguments = parser.parse_args()
    if not arguments.build_ready:
        parser.error("Do not launch until the build owner authorizes testing; then pass --build-ready")
    if sys.platform != "win32":
        parser.error("Use native Windows Python, not WSL or Wine")
    if not 10 <= arguments.timeout <= 60:
        parser.error("--timeout must be between 10 and 60 seconds")
    workspace = contained(_project_materials_root(ROOT), ROOT)
    build = contained(arguments.build, workspace)
    test_root = workspace / "tts-bookmarks-gui-tests"
    if test_root.exists():
        contained(test_root, workspace)
    else:
        test_root.mkdir()
    results = test_root / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    results.mkdir()
    report = dict(passed=False, language=arguments.language, source_build=str(build), checks=[], sessions=[], copies=[],
                  requirements={"long_centre_select": "not_run", "audible_cursor_and_T1": "not_run",
                                "spoken_properties": "not_run", "local_restore": "not_run",
                                "restart_recent_restore": "not_run", "shared_context_delete": "not_run",
                                "changed_document_rejected": "not_run",
                                "music_continues": "not_run" if arguments.with_music else "not_requested"},
                  limitations=[
                      "Results apply only to the explicitly supplied updated build and the sessions recorded here.",
                      "Disk PCM validates mixer output, not WASAPI/human listening, NVDA/UIA or physical player hardware.",
                      "Each invocation exercises one UI language; run both polski and english for bilingual coverage.",
                      "Title text is checked in compiled catalogs; actual menu identity uses all seven ordered spoken choices.",
                      "Speech settling uses log quiescence and conservative text timing; PCM is verified only after process exit.",
                      "Changed-file rejection uses a same-path, same-size content mutation; cross-path forged records are not exercised.",
                      "Beginning, End, Reading settings and eSpeak rows are reached and spoken; their effects are outside this test.",
                      "Mixed music PCM cannot independently prove intelligibility of every property utterance; the earlier session verifies speech without music.",
                  ], artifact_cleanup=dict(trash=[], workspace=str(results), pending_user_decisions=[]))
    if not arguments.with_music:
        report["limitations"].append("Background music continuity is not requested; use --with-music to exercise it.")
    print(f"Text bookmark GUI evidence: {results}", flush=True)
    loan = ExecutableLoan(build, results, report)
    probe = GuiProbe(results / "fixture", results, report, arguments.timeout)
    try:
        runtime, labels, displayed, document_bytes = prepare_fixture(
            build, results, arguments.language, report, voice_files_disabled=arguments.voice_files_disabled)
        probe.runtime = runtime
        probe.log = runtime / "simulator.log"
        write_json(results / "report.json", report)
        loan.move_to(runtime)
        bookmark = local_bookmarks(probe, labels, displayed, document_bytes, report)
        for name in ("long_centre_select", "audible_cursor_and_T1", "spoken_properties", "local_restore"):
            report["requirements"][name] = "logged_pending_pcm"
        restart_and_delete(probe, labels, bookmark, report)
        report["requirements"].update(restart_recent_restore="logged_pending_pcm", shared_context_delete="logged_pending_pcm")
        reject_changed_document(probe, labels, document_bytes, report)
        report["requirements"]["changed_document_rejected"] = "logged_pending_pcm"
        if arguments.with_music:
            music_properties(probe, labels, displayed, document_bytes, report)
            report["requirements"]["music_continues"] = "logged_pending_pcm"
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            try:
                probe.close(graceful=False)
            except Exception as error:
                report["cleanup_error"] = str(error)
            try:
                loan.restore(probe.process)
            except Exception as error:
                report["executable_restore_error"] = str(error)
                loan.record.update(state="restore_failed", error=str(error))
                try:
                    loan.save_record()
                except Exception as record_error:
                    report["transfer_record_error"] = str(record_error)
        finally:
            signal.signal(signal.SIGINT, previous_handler)
        try:
            verify_evidence(report)
        except Exception as error:
            report["evidence_error"] = str(error)
        failed = [check["name"] for check in report["checks"] if check["status"] != "passed"]
        report["failed_checks"] = failed
        errors = any(name in report for name in ("error", "cleanup_error", "executable_restore_error", "evidence_error"))
        report["passed"] = bool(report["sessions"]) and not failed and not errors and loan.record["restored"] and all(
            status == "logged_pending_pcm" for name, status in report["requirements"].items()
            if name != "music_continues" or arguments.with_music)
        for name, status in report["requirements"].items():
            if status == "logged_pending_pcm":
                report["requirements"][name] = "passed" if report["passed"] else "partial_see_checks"
        write_json(results / "report.json", report)
    print(json.dumps(dict(passed=report["passed"], error=report.get("error"),
                          failed_checks=report["failed_checks"], executable_restored=loan.record["restored"],
                          report=str(results / "report.json")), indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
