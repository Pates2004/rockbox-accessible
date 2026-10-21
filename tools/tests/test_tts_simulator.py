import argparse
import array
from contextlib import nullcontext
import ctypes
from ctypes import wintypes
import datetime
from functools import cache
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import wave


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root, confined_path



ROOT = Path(__file__).resolve().parents[2]


class WindowsBackend:
    def __init__(self):
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.window_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        class ProcessEntry(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        self.process_entry = ProcessEntry
        for library, name, result, parameters in (
            (self.kernel32, "CreateToolhelp32Snapshot", wintypes.HANDLE, [wintypes.DWORD, wintypes.DWORD]),
            (self.kernel32, "Process32FirstW", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]),
            (self.kernel32, "Process32NextW", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]),
            (self.kernel32, "OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            (self.kernel32, "CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
            (self.kernel32, "QueryFullProcessImageNameW", wintypes.BOOL,
                [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]),
            (self.user32, "EnumWindows", wintypes.BOOL, [self.window_callback, wintypes.LPARAM]),
            (self.user32, "GetWindowThreadProcessId", wintypes.DWORD,
                [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
            (self.user32, "GetClassNameW", ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
            (self.user32, "IsWindowVisible", wintypes.BOOL, [wintypes.HWND]),
            (self.user32, "ShowWindowAsync", wintypes.BOOL, [wintypes.HWND, ctypes.c_int]),
            (self.user32, "PostMessageW", wintypes.BOOL,
                [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
        ):
            function = getattr(library, name)
            function.restype = result
            function.argtypes = parameters

    def ensure_unused(self, executable):
        snapshot = self.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = self.process_entry()
            entry.dwSize = ctypes.sizeof(entry)
            available = self.kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while available:
                if entry.szExeFile.casefold() == executable.name.casefold():
                    handle = self.kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)
                    if not handle:
                        error = ctypes.get_last_error()
                        if error != 87:
                            raise RuntimeError(f"Cannot verify simulator PID {entry.th32ProcessID}: "
                                               f"{ctypes.WinError(error)}")
                    else:
                        try:
                            image = ctypes.create_unicode_buffer(32768)
                            size = wintypes.DWORD(len(image))
                            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
                                raise ctypes.WinError(ctypes.get_last_error())
                            if Path(image.value).resolve() == executable:
                                raise RuntimeError(f"A simulator is already using this development build "
                                                   f"(PID {entry.th32ProcessID})")
                        finally:
                            self.kernel32.CloseHandle(handle)
                available = self.kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            error = ctypes.get_last_error()
            if error != 18:
                raise ctypes.WinError(error)
        finally:
            self.kernel32.CloseHandle(snapshot)

    def owns_window(self, pid, window):
        owner = wintypes.DWORD()
        return (self.user32.GetWindowThreadProcessId(window, ctypes.byref(owner)) != 0 and
                owner.value == pid)

    def find_window(self, pid):
        windows = []
        callback_count = 0
        callback_errors = []

        @self.window_callback
        def collect(window, parameter):
            nonlocal callback_count
            callback_count += 1
            try:
                if self.owns_window(pid, window):
                    class_name = ctypes.create_unicode_buffer(256)
                    if not self.user32.GetClassNameW(window, class_name, len(class_name)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if class_name.value == "SDL_app":
                        windows.append(window)
            except BaseException as error:
                callback_errors.append(error)
                return False
            return True

        ctypes.set_last_error(0)
        enumerated = self.user32.EnumWindows(collect, 0)
        error = ctypes.get_last_error()
        if callback_errors:
            raise callback_errors[0]
        if not enumerated:
            if error:
                raise ctypes.WinError(error)
            if callback_count:
                raise RuntimeError("EnumWindows stopped after a callback without an error code")
            return None
        if len(windows) > 1:
            raise RuntimeError(f"Multiple SDL windows for simulator PID {pid}")
        return windows[0] if windows else None

    def set_hidden(self, pid, window, hidden):
        if not self.owns_window(pid, window):
            raise RuntimeError("Simulator window no longer belongs to the test process")
        if not self.user32.ShowWindowAsync(window, 0 if hidden else 4):
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self.owns_window(pid, window):
                raise RuntimeError("Simulator window disappeared while changing visibility")
            if bool(self.user32.IsWindowVisible(window)) != hidden:
                return
            time.sleep(0.05)
        raise RuntimeError("Simulator window did not change visibility")

    def key_event(self, pid, window, key, pressed):
        if not self.owns_window(pid, window):
            raise RuntimeError("Refusing keyboard input to a window not owned by the test process")
        virtual_key, scan_code, extended = {
            "Down": (0x28, 0x50, True), "Up": (0x26, 0x48, True),
            "Left": (0x25, 0x4B, True), "Right": (0x27, 0x4D, True),
            "Insert": (0x2D, 0x52, True), "space": (0x20, 0x39, False),
            "Escape": (0x1B, 0x01, False),
        }[key]
        flags = 1 | (scan_code << 16) | (int(extended) << 24)
        if not pressed:
            flags |= (1 << 30) | (1 << 31)
        if not self.user32.PostMessageW(window, 0x0100 if pressed else 0x0101, virtual_key, flags):
            raise ctypes.WinError(ctypes.get_last_error())


@cache
def windows_backend():
    return WindowsBackend() if sys.platform == "win32" else None


def ensure_unused(executable, native):
    if native is not None:
        native.ensure_unused(executable)
        return
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "exe").resolve(strict=True) == executable:
                raise RuntimeError("A simulator is already using this development build")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue


def find_window(pid, environment, timeout=15):
    """Wait for the PID-owned SDL window without requiring a title or changing focus."""
    native = windows_backend()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if native is not None:
            window = native.find_window(pid)
            if window is not None:
                return window
        else:
            found = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)],
                capture_output=True, text=True, env=environment)
            if found.returncode == 0:
                return found.stdout.splitlines()[0]
        time.sleep(0.1)
    raise RuntimeError(f"No simulator window for PID {pid}")


def send_key(pid, window, key, pressed, environment):
    """Send one HWND-scoped key-down/up event, never global input or focus changes."""
    native = windows_backend()
    if native is not None:
        native.key_event(pid, window, key, pressed)
    else:
        subprocess.run(["xdotool", "keydown" if pressed else "keyup", "--window", str(window), key],
            check=True, env=environment)


def shutdown(process, window, environment, hold=3, timeout=20):
    """Hold Escape on the owned window and require a clean exit without terminate/kill."""
    if process.poll() is None:
        send_key(process.pid, window, "Escape", True, environment)
        try:
            time.sleep(hold)
        finally:
            if process.poll() is None:
                try:
                    send_key(process.pid, window, "Escape", False, environment)
                except (RuntimeError, OSError, subprocess.CalledProcessError):
                    process.wait(timeout=timeout)
    process.wait(timeout=timeout)
    if process.returncode != 0:
        raise AssertionError(f"Simulator PID {process.pid} shutdown status {process.returncode}")


def catalog_labels(build, language):
    identifiers = {name: int(number, 0) for name, number in re.findall(
        r"\b((?:LANG|VOICE)_\w+), /\* (0x[0-9a-fA-F]+|\d+) \*/", (build / "lang_enum.h").read_text())}
    data = (build / "apps" / "lang" / f"{language}.vstrings").read_bytes()
    position = int.from_bytes(data[8:10], "big")
    phrases = {}
    for entry in range(int.from_bytes(data[4:6], "big")):
        identifier = int.from_bytes(data[position:position + 2], "big")
        position += 2
        end = data.index(0, position)
        phrases[identifier] = data[position:end].decode("utf-8")
        position = end + 1
    return {name: phrases[number] for name, number in identifiers.items() if number in phrases}


def main():
    native = windows_backend()
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, default=_project_materials_root(ROOT) /
                        ("build-espeak-windows" if native is not None else "build-espeak"))
    parser.add_argument("--language", choices=("polski", "english"), default="polski")
    parser.add_argument("--legacy-plugin", type=Path)
    arguments = parser.parse_args()
    speech_language = "en" if arguments.language == "english" else "pl"
    build = confined_path(arguments.build, _project_materials_root(ROOT))
    if _project_materials_root(ROOT) not in build.parents:
        raise RuntimeError("UI tests must use an isolated development build inside Workspace")
    executable = confined_path(build / ("rockboxui.exe" if native is not None else "rockboxui"), build).resolve(strict=True)
    if executable.parent != build:
        raise RuntimeError("The simulator executable must reside in the development build")
    ensure_unused(executable, native)
    disk = confined_path(build / "simdisk", build).resolve(strict=True)
    if _project_materials_root(ROOT) not in disk.parents:
        raise RuntimeError("The test disk must remain inside Workspace")
    labels = catalog_labels(build, arguments.language)
    configuration = disk / ".rockbox/config.cfg"
    marker = disk / ".tts-test-profile"
    if configuration.exists() and not marker.exists():
        raise RuntimeError("Refusing to replace a non-test profile")
    marker.write_text("Synthetic integration test profile. Not user data.\n")
    if arguments.legacy_plugin:
        legacy_plugin = arguments.legacy_plugin.resolve(strict=True)
        fixture = disk / "007 Legacy plugin.rock"
        shutil.copy2(legacy_plugin, fixture)
        if fixture.read_bytes() != legacy_plugin.read_bytes():
            raise RuntimeError("Legacy plugin fixture integrity failure")
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    results = _project_materials_root(ROOT) / "simulator-tests" / timestamp
    results.mkdir(parents=True)
    if configuration.exists():
        shutil.copy2(configuration, results / "previous-test-config.cfg")
    for name in ("config.cfg.new", ".resume.cfg", ".resume.cfg.new"):
        pending = disk / ".rockbox" / name
        if pending.exists():
            pending.rename(results / name)
    configuration.write_text(f"lang: /.rockbox/langs/{arguments.language}.lng\n"
        "talk menu: on\ntalk dir: spell\ntalk file: spell\ntalk dir clip: off\n"
        "talk file clip: off\ntts enabled: on\ntts language: system\ntts variant: \n"
        "tts rate: 175\ntts pitch: 50\ntts volume: 100\ntts range: 50\n"
        "tts wordgap: 0\nvolume: -25\n", encoding="utf-8")
    (disk / "001 Czytanie próbne.txt").write_text(
        "Test zintegrowanej syntezy mowy. Druciana siatka, bociana, starcia i tarcia. " * 80,
        encoding="utf-8")
    (disk / "002 Błędne kodowanie.txt").write_bytes(b"\xff\xfeA\x00")
    (disk / "003 Koniec.txt").write_text("Koniec próby.", encoding="utf-8")
    tone = array.array("h", (int(6000 * math.sin(2 * math.pi * 997 * sample / 44100))
                            for sample in range(44100)))
    with wave.open(str(disk / "004 Muzyka testowa.wav"), "wb") as music:
        music.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        for second in range(60):
            music.writeframesraw(tone.tobytes())
    environment = dict(os.environ, SDL_AUDIODRIVER="disk",
                       SDL_VIDEODRIVER="windows" if native is not None else "x11",
                       SDL_DISKAUDIOFILE=str(results / "mixed-audio.raw"), SDL_DISKAUDIODELAY="12")
    log = (build if native is not None else results) / "simulator.log"

    def preserve_native_log(name):
        ensure_unused(executable, native)
        if log.exists():
            if log.resolve().parent != build:
                raise RuntimeError("The native simulator log must reside beside the executable")
            destination = results / name
            if destination.exists():
                raise RuntimeError(f"Refusing to overwrite preserved log: {destination}")
            log.rename(destination)

    if native is not None:
        preserve_native_log("previous-simulator.log")
    report = {"language": arguments.language, "checks": [], "passed": False}
    print(f"UI/PCM test evidence: {results}", flush=True)
    output_context = nullcontext(subprocess.DEVNULL) if native is not None else log.open("w", encoding="utf-8")
    with output_context as output:
        def launch(process_environment, debug=False):
            ensure_unused(executable, native)
            command = [str(executable), "--root", str(disk)]
            if native is not None and process_environment.get("SDL_AUDIODRIVER") == "disk":
                command.extend(["--audiodev", process_environment["SDL_DISKAUDIOFILE"]])
            if debug:
                command.append("--debugbuttons")
            return subprocess.Popen(command, cwd=build, env=process_environment,
                stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if native is not None else 0)

        process = None
        native_log_name = "simulator.log"
        try:
            process = launch(environment, debug=True)
            window = find_window(process.pid, environment)
            if native is None:
                subprocess.run(["xdotool", "windowfocus", window], check=True, env=environment)
            cursor = 0

            def recent():
                nonlocal cursor
                try:
                    text = log.read_text(encoding="utf-8", errors="replace")
                except FileNotFoundError:
                    return ""
                part = text[cursor:]
                cursor = len(text)
                return part

            def expect(fragment, timeout=15):
                collected = ""
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    collected += recent()
                    if fragment in collected:
                        return collected
                    if process.poll() is not None:
                        raise RuntimeError(f"Simulator exited: {process.returncode}")
                    time.sleep(0.1)
                raise AssertionError(f"Missing {fragment!r}. Recent log: {collected[-2000:]}")

            def press(key, pause=0.4):
                recent()
                if process.poll() is not None:
                    raise RuntimeError(f"Simulator exited: {process.returncode}")
                send_key(process.pid, window, key, True, environment)
                try:
                    time.sleep(0.12)
                finally:
                    if process.poll() is None:
                        send_key(process.pid, window, key, False, environment)
                time.sleep(pause)

            def select(fragment, maximum=30, exact=False):
                for attempt in range(maximum):
                    text = recent()
                    lines = re.findall(r"^TTS: (.*)$", text, re.MULTILINE)
                    if lines and (fragment == lines[-1] if exact else fragment in lines[-1]):
                        press("space")
                        return
                    press("Down")
                raise AssertionError(f"Menu option not found: {fragment!r}")

            expect("TTS:")
            report["checks"].append("startup voice without .voice")
            startup = log.read_text(encoding="utf-8", errors="replace")
            if f"TTS parameters: language={speech_language}" not in startup:
                raise AssertionError("System voice does not match the UI language at startup")
            report["checks"].append("System voice resolves the actual Polish/English UI language")
            if native is not None:
                native.set_hidden(process.pid, window, True)
            press("Down")
            if native is not None:
                navigation_cursor = cursor
                try:
                    expect("TTS:", timeout=5)
                    report["native_window_hidden"] = True
                except AssertionError:
                    native.set_hidden(process.pid, window, False)
                    press("Down")
                    navigation_cursor = cursor
                    expect("TTS:")
                    report["native_window_hidden"] = False
                cursor = navigation_cursor
            select(labels["LANG_DIR_BROWSER"])
            if arguments.legacy_plugin:
                select("007 Legacy plugin")
                expect(labels["LANG_PLUGIN_WRONG_VERSION"])
                time.sleep(2.2)
                report["checks"].append("old plugin ABI rejected with a spoken error before plugin execution")
                select(labels["LANG_DIR_BROWSER"])
            select("001 Czytanie")
            expect("Test zintegrowanej syntezy mowy")
            report["checks"].append("natural UTF-8 filename and streaming text")
            time.sleep(2)
            before_pause = log.read_text(encoding="utf-8", errors="replace")
            utterances = before_pause.count("TTS utterance:")
            positions = re.findall(r"TTS reader cursor: (\d+)", before_pause)
            if not positions or int(positions[-1]) <= 0:
                raise AssertionError("Text cursor did not advance with audible playback")
            press("space")
            expect("TTS reader state: paused")
            pause_start = (results / "mixed-audio.raw").stat().st_size
            paused_text = log.read_text(encoding="utf-8", errors="replace")
            paused_positions = re.findall(r"TTS reader cursor: (\d+)", paused_text)
            time.sleep(1.2)
            pause_end = (results / "mixed-audio.raw").stat().st_size
            paused_end = log.read_text(encoding="utf-8", errors="replace")
            if re.findall(r"TTS reader cursor: (\d+)", paused_end) != paused_positions:
                raise AssertionError("Text cursor advanced during pause")
            press("space")
            expect("TTS reader state: reading")
            time.sleep(1)
            resumed_text = log.read_text(encoding="utf-8", errors="replace")
            if resumed_text.count("TTS utterance:") != utterances:
                raise AssertionError("Pause/resume re-synthesized text instead of retaining PCM")
            resumed_positions = re.findall(r"TTS reader cursor: (\d+)", resumed_text)
            if not resumed_positions or int(resumed_positions[-1]) <= int(paused_positions[-1]):
                raise AssertionError("Text cursor did not continue after resume")
            report["checks"].append("playback-linked UTF-8 cursor freezes and resumes without re-synthesis")
            press("Down")
            expect("TTS:")
            press("Up")
            expect("TTS:")
            press("Left")
            expect("TTS:")
            press("Right")
            expect("TTS:")
            press("Escape")
            report["checks"].append("granularity selection, forward/backward navigation and exit")
            press("Down")
            select("002 Błędne")
            expect(labels["LANG_TTS_INVALID_TEXT"])
            press("Escape")
            press("Down")
            select("003 Koniec")
            expect(labels["LANG_TTS_FINISHED"])
            press("Escape")
            report["checks"].append("invalid encoding and EOF announcements")
            press("Down")
            select("004 Muzyka")
            music_start = (results / "mixed-audio.raw").stat().st_size
            press("Insert")
            expect("TTS audio playback: 1")
            time.sleep(1)
            music_end = (results / "mixed-audio.raw").stat().st_size
            report["checks"].append("speech synthesis while Rockbox plays a WAV through its codec")
            select(labels["LANG_SETTINGS"])
            select(labels["LANG_GENERAL_SETTINGS"])
            other_language = "english" if arguments.language == "polski" else "polski"
            for ui_language in (other_language, "japanese", arguments.language):
                select(labels["LANG_LANGUAGE"])
                select(ui_language, maximum=65, exact=True)
                expected_voice = "pl" if ui_language == "polski" else "en"
                expect(f"TTS parameters: language={expected_voice}")
                labels = catalog_labels(build, ui_language)
                time.sleep(1.3)
            report["checks"].append("runtime UI-language changes follow System voice; Japanese falls back to English")
            select(labels["LANG_VOICE"])
            select(labels["LANG_TTS"])
            select(labels["LANG_TTS_RATE"])
            expect("TTS: 0")
            press("Down")
            expect(f'TTS: {labels["VOICE_MINUS"]}')
            press("Up")
            expect("TTS: 0")
            press("Up")
            expect(f'TTS: {labels["VOICE_PLUS"]}')
            press("Down")
            press("Down")
            expect(f'TTS: {labels["VOICE_MINUS"]}')
            report["checks"].append("zero-centered percentages speak negative, neutral and positive values")
            press("space")
            select(labels["LANG_TTS_RATE_SCALE"])
            press("Down")
            press("space")
            select(labels["LANG_TTS_RATE"])
            expect(labels["LANG_TTS_RATE_WPM_UNIT"])
            press("Left")
            report["checks"].append("percent-default rate edits retain canonical WPM across scale changes")
            select(labels["LANG_TTS_RANGE"])
            press("Down")
            press("space")
            select(labels["LANG_TTS_PUNCTUATION"])
            for attempt in range(3):
                press("Down")
            press("space")
            select(labels["LANG_TTS_DUCKING_LEVEL"])
            press("Down")
            press("space")
            report["checks"].append("keyboard changes to modulation, punctuation and ducking level")
            select(labels["LANG_TTS_READER_SETTINGS"])
            select(labels["LANG_TTS_READER_UNIT"])
            for attempt in range(3):
                press("Down")
            press("space")
            select(labels["LANG_TTS_READER_PAGE_LINES"])
            press("Down")
            press("space")
            press("Left")
            report["checks"].append("keyboard changes to text navigation unit and logical page length")
            select(labels["LANG_TTS_VARIANT"])
            press("Down")
            press("space")
            report["checks"].append("keyboard changes to speech rate and variant")
            select(labels["LANG_TTS_LANGUAGE"])
            press("Down")
            press("space")
            changed = expect("TTS parameters:")
            chosen = re.search(r"TTS parameters: language=(\S+)", changed)
            if not chosen or chosen.group(1) == speech_language:
                raise AssertionError("Language selection did not reach the synthesizer")
            speech_language = chosen.group(1)
            report["selected_speech_language"] = speech_language
            report["checks"].append("keyboard language selection reaches the actual synthesizer")
            select(labels["LANG_TTS_ENABLED"])
            press("Down")
            press("space")
            time.sleep(0.8)
            recent()
            press("Down")
            if "TTS:" in recent():
                raise AssertionError("Disabled synthesis still announces the next menu item")
            press("Up")
            press("space")
            press("Up")
            press("space")
            expect("TTS:")
            report["checks"].append("disable and re-enable synthesis without restart")
            for attempt in range(12):
                press("Down", pause=0.02)
            report["checks"].append("repeated interruptions remain responsive")
            recent()
            shutdown(process, window, environment)
            shutdown_log = log.read_text(encoding="utf-8", errors="replace")
            shutdown_label = labels["LANG_SHUTTINGDOWN"]
            shutdown_lines = re.findall(r"^TTS: (.*)$", shutdown_log, re.MULTILINE)
            if shutdown_lines.count(shutdown_label) != 1:
                raise AssertionError("Shutdown was not announced exactly once")
            report["checks"].append("shutdown announced exactly once")
            pending = configuration.with_name("config.cfg.new")
            saved = (pending if pending.exists() else configuration).read_text(encoding="utf-8")
            (results / "saved-config.cfg").write_text(saved, encoding="utf-8")
            if ("tts rate: 174" not in saved or "tts variant: adam" not in saved or
                    f"tts language: {speech_language}" not in saved):
                raise AssertionError("Speech settings were not saved as changed")
            for setting in ("tts rate scale: wpm", "tts range: 49", "tts punctuation: all",
                            "tts ducking level: 20", "tts reader unit: page",
                            "tts reader page lines: 19"):
                if setting not in saved:
                    raise AssertionError(f"Speech setting was not persisted: {setting}")
            report["checks"].append("graceful shutdown and persisted speech settings")
            recent()
            if native is not None:
                preserve_native_log(native_log_name)
                native_log_name = "restart-simulator.log"
                cursor = 0
            window = None
            restart_environment = dict(environment, SDL_DISKAUDIOFILE=str(results / "restart-audio.raw"))
            process = launch(restart_environment)
            expect(f"TTS parameters: language={speech_language} variant=adam rate=174")
            restarted = log.read_text(encoding="utf-8", errors="replace")
            if "range=49 wordgap=0 punctuation=3" not in restarted:
                raise AssertionError("Modulation/punctuation did not reach synthesis after restart")
            window = find_window(process.pid, restart_environment)
            if native is not None and report["native_window_hidden"]:
                native.set_hidden(process.pid, window, True)
            recent()
            shutdown(process, window, restart_environment)
            report["checks"].append("saved parameters reach the synthesizer after process restart")
            samples = array.array("h", (results / "mixed-audio.raw").read_bytes())
            paused_samples = samples[pause_start // 2:pause_end // 2]
            if not paused_samples or any(paused_samples):
                raise AssertionError("Voice output was not silent during the stable pause interval")
            report["checks"].append("actual mixer PCM is silent while text reading is paused")
            nonzero = sum(sample != 0 for sample in samples)
            report.update(pcm_samples=len(samples), nonzero_samples=nonzero)
            if nonzero < 1000:
                raise AssertionError("No meaningful non-silent audio from the Rockbox mixer")
            report["checks"].append("non-silent PCM from the SDL output of the Rockbox mixer")
            amplitudes = []
            for start in range(music_start // 2, min(music_end // 2, len(samples)) - 8192, 8192):
                window_samples = samples[start:start + 8192:2]
                real = sum(value * math.cos(2 * math.pi * 997 * index / 44100)
                           for index, value in enumerate(window_samples))
                imaginary = sum(value * math.sin(2 * math.pi * 997 * index / 44100)
                                for index, value in enumerate(window_samples))
                amplitudes.append(2 * math.hypot(real, imaginary) / len(window_samples))
            report["background_tone_amplitude"] = max(amplitudes, default=0)
            if report["background_tone_amplitude"] < 5:
                raise AssertionError("The background music tone was not found in mixed PCM")
            report["checks"].append("997 Hz background music remains present in mixed PCM during speech")
            report["passed"] = True
        except Exception as error:
            report["error"] = str(error)
            raise
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            try:
                if native is not None:
                    preserve_native_log(native_log_name)
            except Exception as error:
                report["passed"] = False
                report["log_preservation_error"] = str(error)
                raise
            finally:
                (results / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
