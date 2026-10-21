"""Windows Sansa recorder speech smoke test, using a new disposable test profile.

Run only after the parent finishes the Windows build and fullinstall, with
--build-ready. The development EXE is moved into the fixture and restored after
process exit, including failed runs. Runtime data copies, logs and the synthetic
profile remain in Workspace; no installed or source-build profile is consumed.
This tests synthesized UI output, not microphone capture or human listening.
Use --voice-files-disabled to keep eSpeak enabled while disabling recorded
menu, directory and file speech and setting recorded voice volume to zero.
"""

import argparse
import array
import ctypes
from ctypes import wintypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time

from test_tts_simulator import catalog_labels, find_window, send_key, shutdown, windows_backend


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root, confined_path



ROOT = Path(__file__).resolve().parents[2]
TARGETS = {"sansaclipplus": "build-espeak-windows",
           "sansaclipzip": "build-espeak-windows-clipzip"}
RUNTIME_DIRECTORIES = ("backdrops", "codecs", "codepages", "docs", "eqs", "espeak-data",
                       "fonts", "icons", "langs", "rocks", "themes", "wps")
RECORDER_SYMBOL_SIZES = {"rec_status": 4, "codec_type": 4, "rec_errors": 4,
                         "record_state": 4, "record_status": 4, "path_buffer": 260}
MEMORY_SYMBOL_SIZES = dict(RECORDER_SYMBOL_SIZES, voice_pcm_paused=1, voice_playing=1,
                           quiet_counter=4, pending_count=4, synthesizing=1, generation=4,
                           pcm_playing=1, next_size=8, idle_counter=4)
SOURCE_FACTS = (
    ("apps/recorder/recording.c", "defined(SIMULATOR) || defined(HAVE_PCM_RECORDING_VOICE)",
     "Recorder speech is enabled for SDL UI tests and explicitly duplex-capable native backends. "
     "This Windows test does not validate the native backend."),
    ("apps/voice_thread.c", "mixer_channel_play_data(PCM_MIXER_CHAN_VOICE",
     "Synthesized voice PCM is played through the ordinary PCM voice mixer channel."),
    ("apps/recorder/pcm_record.c", "pcm_set_frequency(pcm_sampr | SAMPR_TYPE_REC)",
     "Recorder configuration changes the PCM rate, then selects the recording source "
     "for monitoring and applies the PCM settings."),
    ("firmware/pcm.c", "void pcm_set_frequency(",
     "Playback and recording rate requests update the current sink's pending frequency; "
     "pcm_apply_settings applies that frequency to the sink."),
    ("firmware/target/arm/as3525/audio-as3525.c", "bool loopback = source != AUDIO_SRC_PLAYBACK",
     "The AS3525 audio output selector enables I2S input-FIFO loopback for non-playback "
     "sources. Its mono exception is conditional on AS3525, not the Clip+ AS3525v2. "
     "Duplex voice temporarily overrides monitoring output, not capture input; "
     "this Windows test does not exercise those registers."),
    ("firmware/export/config/sansaclipplus.h", "#define CONFIG_CPU AS3525v2",
     "The native Clip+ configuration selects AS3525v2; the AS3525-only mono loopback exception "
     "does not apply to that CPU selection."),
    ("apps/recorder/pcm_record.c", "talk_buffer_set_policy(TALK_BUFFER_LOOSE)",
     "Recorder initialization changes talk-buffer policy and allocates the largest available "
     "core buffer. This alone does not establish voice-buffer corruption or incompatibility."),
    ("apps/audio_path.c", "/** Sim stubs **/",
     "The hosted audio output-source selector is a no-op, unlike native monitoring routing."),
    ("firmware/target/hosted/sdl/pcm-sdl.c", "void pcm_rec_dma_start(",
     "SDL recording DMA start/stop are stubs; the recording peak-buffer accessor returns NULL. "
     "This test cannot validate microphone capture, signal levels, AGC or useful recorded audio."),
    ("apps/recorder/pcm_record.c", "static void on_record_pause(",
     "Recorder start/pause/resume handlers maintain engine state separately from incoming PCM. "
     "Their existence does not establish that the simulator dispatcher enables them."),
    ("apps/audio_thread.h", "#if defined(HAVE_RECORDING) && !defined(SIMULATOR)",
     "AUDIO_HAVE_RECORDING excludes simulators. This smoke test expects an explicit unavailable "
     "message, unchanged recorder state/path and continued navigation, not recording transitions."),
)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def contained(path, root):
    workspace = _project_materials_root(ROOT) if root == ROOT else None
    roots = (root, workspace) if workspace is not None else (root,)
    allow_root = workspace is not None and Path(path).absolute() == workspace.absolute()
    resolved = confined_path(path, *roots, allow_root=allow_root,
                             error=f"Path escapes the required root {root}",
                             link_error="Reparse points are not accepted in a test fixture").resolve(strict=True)
    attributes = getattr(path.lstat(), 'st_file_attributes', 0)
    if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise RuntimeError(f"Reparse points are not accepted in a test fixture: {path}")
    return resolved


def source_facts():
    facts = []
    for relative, anchor, fact in SOURCE_FACTS:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        position = text.find(anchor)
        facts.append({"path": relative, "line": text.count("\n", 0, position) + 1
                      if position >= 0 else None, "anchor_present": position >= 0,
                      "sha256": digest(path), "fact": fact})
    return facts


def pe_layout(executable):
    with executable.open("rb") as source:
        header = source.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError("Memory diagnostics require a PE executable")
        pe_offset = struct.unpack_from("<I", header, 60)[0]
        source.seek(pe_offset)
        coff = source.read(24)
        if len(coff) != 24 or coff[:4] != b"PE\0\0":
            raise ValueError("Invalid PE signature")
        machine, section_count = struct.unpack_from("<HH", coff, 4)
        optional_size = struct.unpack_from("<H", coff, 20)[0]
        optional = source.read(optional_size)
        if machine != 0x8664 or len(optional) < 112 or optional[:2] != b"\x0b\x02":
            raise ValueError("Memory diagnostics support only x64 PE32+ executables")
        preferred_base = struct.unpack_from("<Q", optional, 24)[0]
        image_size = struct.unpack_from("<I", optional, 56)[0]
        if not 0 < section_count <= 96 or not image_size or not preferred_base:
            raise ValueError("Invalid PE image dimensions")
        sections = []
        for index in range(section_count):
            section = source.read(40)
            if len(section) != 40:
                raise ValueError("Truncated PE section table")
            virtual_size, rva, raw_size = struct.unpack_from("<III", section, 8)
            size = max(virtual_size, raw_size)
            flags = struct.unpack_from("<I", section, 36)[0]
            if rva + size > image_size:
                raise ValueError("PE section extends beyond the image")
            sections.append({"name": section[:8].rstrip(b"\0").decode("ascii"),
                             "rva": rva, "size": size, "flags": flags})
    return {"preferred_base": preferred_base, "image_size": image_size,
            "pe_offset": pe_offset, "sections": sections}


def recorder_symbol_layout(executable, nm_output):
    layout = pe_layout(executable)
    symbols = {}
    for name, size in MEMORY_SYMBOL_SIZES.items():
        matches = re.findall(r"^\s*([0-9a-fA-F]+)\s+(?:[0-9a-fA-F]+\s+)?"
                             r"([A-Za-z])\s+" + re.escape(name) + r"\s*$", nm_output, re.MULTILINE)
        if len(matches) != 1 or matches[0][1] not in "bBdD":
            raise ValueError(f"Expected exactly one data symbol: {name}; found {matches}")
        preferred_address = int(matches[0][0], 16)
        rva = preferred_address - layout["preferred_base"]
        sections = [section for section in layout["sections"]
                    if section["rva"] <= rva and rva + size <= section["rva"] + section["size"]
                    and section["flags"] & 0xc0000000 == 0xc0000000]
        if rva < 0 or rva + size > layout["image_size"] or len(sections) != 1:
            raise ValueError(f"Symbol is outside one readable writable image section: {name}")
        symbols[name] = {"preferred_address": preferred_address, "rva": rva,
                         "size": size, "section": sections[0]["name"]}
    ranges = sorted((symbol["rva"], symbol["rva"] + symbol["size"], name)
                    for name, symbol in symbols.items())
    if any(previous[1] > current[0] for previous, current in zip(ranges, ranges[1:])):
        raise ValueError("Recorder symbol ranges overlap")
    return dict(layout, symbols=symbols, sha256=digest(executable))


def recorder_enum_meanings():
    excerpts = []
    specifications = (
        ("apps/recorder/recording.c", r"enum rec_status_flags\s*\{[^}]*\}"),
        ("apps/recorder/pcm_record.c", r"enum record_status\s*\{[^}]*\}"),
        ("apps/recorder/pcm_record.c", r"enum record_state\s*\{[^}]*\}"),
        ("apps/recorder/pcm_record.h", r"^#define PCMREC_E_.*$"),
        ("firmware/export/audio.h", r"^#define AUDIO_STATUS_.*$"),
        ("lib/rbcodec/metadata/metadata.h", r"^.*(?:AFMT_UNKNOWN =|CODEC_TYPE_ENCODER =).*$"),
    )
    for relative, pattern in specifications:
        text = (ROOT / relative).read_text(encoding="utf-8")
        matches = list(re.finditer(pattern, text, re.MULTILINE))
        if not matches:
            raise ValueError(f"Missing source enum evidence: {relative}: {pattern}")
        excerpts.extend({"path": relative, "line": text.count("\n", 0, match.start()) + 1,
                         "sha256": digest(ROOT / relative), "excerpt": match.group()}
                        for match in matches)
    combined = "\n".join(item["excerpt"] for item in excerpts)
    required = (r"RCSTAT_HAVE_RECORDED\s*=\s*0x0*8\b", r"AFMT_UNKNOWN\s*=\s*0\b",
                r"AUDIO_STATUS_RECORD\s+0x0*4\b", r"CODEC_TYPE_ENCODER\s*=\s*\(1 << 12\)")
    if not all(re.search(pattern, combined) for pattern in required):
        raise ValueError("Recorder diagnostic interpretation no longer matches source enums")
    return {"sources": excerpts, "rec_status_start_flag": 8, "recording_status_flag": 4,
            "codec_unknown": 0, "codec_encoder_flag": 4096,
            "record_state": {"0": "REC_STATE_IDLE", "1": "REC_STATE_MONITOR", "2": "REC_STATE_FLUSH"}}


def prepare_memory_diagnostics(executable, report):
    diagnostics = {"access_mask": 0x410, "access": "PROCESS_VM_READ | PROCESS_QUERY_INFORMATION",
                   "snapshots": [], "setup_attempts": [], "enum_meanings": recorder_enum_meanings()}
    report["memory_diagnostics"] = diagnostics
    before_hash = digest(executable)
    native_nm = shutil.which("x86_64-w64-mingw32-nm") or shutil.which("nm")
    commands = [[native_nm, "--defined-only", "--numeric-sort", str(executable)]] if native_nm else []
    if shutil.which("wsl.exe"):
        converted = subprocess.run(["wsl.exe", "--exec", "wslpath", "-a", str(executable)],
                                   capture_output=True, text=True, timeout=30)
        diagnostics["wsl_path_conversion"] = {"returncode": converted.returncode,
                                               "stderr": converted.stderr}
        if converted.returncode == 0:
            commands.append(["wsl.exe", "--exec", "x86_64-w64-mingw32-nm", "--defined-only",
                             "--numeric-sort", converted.stdout.strip()])
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            attempt = {"command": command, "returncode": result.returncode, "stderr": result.stderr}
            diagnostics["setup_attempts"].append(attempt)
            if result.returncode:
                continue
            layout = recorder_symbol_layout(executable, result.stdout)
            if layout["sha256"] != before_hash:
                raise ValueError("EXE changed while reading PE headers and symbols")
            diagnostics["image"] = layout
            return layout
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            diagnostics["setup_attempts"].append({"command": command, "error": str(error)})
    raise RuntimeError("Cannot resolve unique recorder data symbols before EXE loan; see memory_diagnostics")


class ReadOnlyWindowsMemory:
    def __init__(self):
        if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError("Recorder memory reads require native 64-bit Windows Python")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = (
            ("OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            ("CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
            ("K32EnumProcessModules", wintypes.BOOL,
             [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]),
            ("K32GetModuleFileNameExW", wintypes.DWORD,
             [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]),
            ("ReadProcessMemory", wintypes.BOOL,
             [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]),
        )
        for name, result, arguments in signatures:
            function = getattr(self.kernel, name)
            function.restype = result
            function.argtypes = arguments

    def open(self, pid):
        handle = self.kernel.OpenProcess(0x410, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def close(self, handle):
        if not self.kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def modules(self, handle):
        count = 128
        for attempt in range(4):
            modules = (wintypes.HMODULE * count)()
            needed = wintypes.DWORD()
            if not self.kernel.K32EnumProcessModules(handle, modules, ctypes.sizeof(modules), ctypes.byref(needed)):
                raise ctypes.WinError(ctypes.get_last_error())
            count = needed.value // ctypes.sizeof(wintypes.HMODULE)
            if needed.value <= ctypes.sizeof(modules):
                result = []
                for base in modules[:count]:
                    path = ctypes.create_unicode_buffer(32768)
                    length = self.kernel.K32GetModuleFileNameExW(handle, base, path, len(path))
                    if not length or length >= len(path):
                        raise OSError("Cannot resolve a complete process module path")
                    result.append((base, Path(path.value).resolve(strict=True)))
                return result
        raise RuntimeError("Process module list did not stabilize")

    def read(self, handle, address, size):
        buffer = ctypes.create_string_buffer(size)
        copied = ctypes.c_size_t()
        if not self.kernel.ReadProcessMemory(handle, address, buffer, size, ctypes.byref(copied)):
            raise ctypes.WinError(ctypes.get_last_error())
        if copied.value != size:
            raise OSError(f"Partial process read at {address:#x}: {copied.value}/{size}")
        return buffer.raw


def interpret_start_snapshots(snapshots):
    usable = [sample for sample in snapshots if sample.get("consistent") and "values" in sample]
    baseline = next((sample["values"] for sample in usable if sample["phase"] == "before_start"), None)
    later = [sample for sample in usable if sample["phase"] != "before_start"]
    result = {"classification": "insufficient_memory_evidence", "observed": [],
              "not_proven": "Global snapshots alone do not prove an executed early return or a blocked consumer."}
    if baseline is None or not later:
        result["next_probe"] = "Resolve memory-read errors or obtain a consistent before/after pair."
        return result
    after = later[-1]["values"]
    if after["record_status"] & 4:
        result.update(classification="recording_engine_state_observed",
                      next_probe="If speech is missing, inspect the UI thread and recording_speak_state polling.")
    elif not baseline["rec_status"] & 8 and after["rec_status"] & 8:
        result["observed"].append("RCSTAT_HAVE_RECORDED became set; a recording start/status path was reached.")
        if after["rec_errors"]:
            result.update(classification="start_path_with_recorder_errors",
                          next_probe="Resolve rec_errors and inspect the audio consumer before concluding it returned.")
        elif after["codec_type"] == 0:
            result.update(classification="start_path_with_unknown_codec",
                          next_probe="Inspect encoder configuration/unload and the audio consumer to distinguish rejection from waiting.")
        else:
            result.update(classification="start_path_without_engine_transition",
                          next_probe="Inspect audio_queue and audio-thread/fiber PC; globals cannot distinguish pending work from blocking.")
    else:
        result.update(classification="no_new_start_path_observed",
                      next_probe="Inspect action/button delivery and UI-thread/fiber PC; this does not prove an OS key was dropped.")
    result["observed"].append({"before": baseline, "after": after, "after_phase": later[-1]["phase"]})
    return result


def verify_unavailable_start(diagnostics):
    samples = diagnostics["snapshots"]
    required = ("before_start", "start_after_one_second", "start_speech_completed")
    selected = {}
    for phase in required:
        matches = [sample for sample in samples if sample["phase"] == phase]
        if len(matches) != 1 or not matches[0].get("consistent") or matches[0].get("error"):
            raise AssertionError(f"Unavailable Start lacks a trustworthy {phase} memory snapshot")
        values = matches[0]["values"]
        if not set(RECORDER_SYMBOL_SIZES).issubset(values):
            raise AssertionError("Unavailable Start snapshot omits required recorder fields")
        selected[phase] = {name: values[name] for name in RECORDER_SYMBOL_SIZES}
    before = selected["before_start"]
    if before["rec_status"] & 8 or before["path_buffer"] or any(
            before[name] != 0 for name in ("codec_type", "rec_errors", "record_state", "record_status")):
        raise AssertionError("Unsupported recorder fixture did not begin in a clean inactive state")
    if any(values != before for values in selected.values()):
        raise AssertionError("Unavailable Start changed recording state or generated a path")
    diagnostics["interpretation"] = {
        "classification": "unsupported_start_rejected_without_recording_side_effects",
        "before": before, "after": selected["start_speech_completed"],
        "state_transitions": "not tested; simulator recording backend is unavailable",
    }
    return {"name": "unavailable Start preserves recorder state and path", "status": "passed",
            "values": before, "verified_phases": list(required)}


class RecorderMemoryProbe:
    def __init__(self, process, executable, layout, diagnostics, api=None):
        self.process = process
        self.layout = layout
        self.report = diagnostics
        self.api = api if api is not None else ReadOnlyWindowsMemory()
        self.handle = None
        try:
            if process.poll() is not None or digest(executable) != layout["sha256"]:
                raise RuntimeError("Memory target exited or its EXE changed")
            self.handle = self.api.open(process.pid)
            modules = self.api.modules(self.handle)
            expected = executable.resolve(strict=True)
            matches = [base for base, path in modules if path == expected]
            if len(matches) != 1 or not modules or modules[0] != (matches[0], expected):
                raise RuntimeError("Memory target main module does not match the borrowed EXE path")
            self.base = matches[0]
            if self.base <= 0 or self.base + layout["image_size"] > 1 << 64:
                raise ValueError("Invalid loaded image bounds")
            signature = self.read_image(0, 64)
            pe_offset = struct.unpack_from("<I", signature, 60)[0]
            if signature[:2] != b"MZ" or pe_offset != layout["pe_offset"]:
                raise ValueError("Loaded DOS header does not match the symbol image")
            loaded_pe = self.read_image(pe_offset, 84)
            if loaded_pe[:4] != b"PE\0\0" or struct.unpack_from("<I", loaded_pe, 80)[0] != layout["image_size"]:
                raise ValueError("Loaded PE image size does not match the symbol image")
            diagnostics.update(pid=process.pid, validated_executable=str(expected), loaded_base=self.base,
                               addresses={name: self.base + symbol["rva"] for name, symbol in layout["symbols"].items()})
        except Exception:
            try:
                self.close()
            except Exception as error:
                diagnostics["handle_cleanup_error"] = str(error)
            raise

    def read_image(self, rva, size):
        if rva < 0 or size <= 0 or rva + size > self.layout["image_size"]:
            raise ValueError("Refusing process read outside the validated image")
        return self.api.read(self.handle, self.base + rva, size)

    def values(self, values=None):
        values = {} if values is None else values
        for name, symbol in self.layout["symbols"].items():
            raw = self.read_image(symbol["rva"], symbol["size"])
            if name == "path_buffer":
                if b"\0" not in raw:
                    raise ValueError("Recorder path_buffer is not NUL-terminated within its symbol range")
                values[name] = raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")
            else:
                values[name] = int.from_bytes(raw, "little", signed=name == "codec_type")
        return values

    def snapshot(self, phase):
        sample = {"phase": phase, "monotonic": time.monotonic(),
                  "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "non_atomic": True}
        self.report["snapshots"].append(sample)
        try:
            if self.process.poll() is not None:
                raise RuntimeError("Memory target exited before snapshot")
            sample["values"] = {}
            self.values(sample["values"])
            sample["verification_values"] = {}
            self.values(sample["verification_values"])
            sample["speech_consistent"] = sample["values"] == sample["verification_values"]
            sample["consistent"] = all(sample["values"][name] == sample["verification_values"][name]
                                       for name in RECORDER_SYMBOL_SIZES)
        except Exception as error:
            sample.update(error=f"{type(error).__name__}: {error}", consistent=False)
        sample["finished_monotonic"] = time.monotonic()
        self.report["interpretation"] = interpret_start_snapshots(self.report["snapshots"])
        return sample

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            self.api.close(handle)


class ExecutableLoan:
    def __init__(self, build, results, report):
        self.workspace = contained(_project_materials_root(ROOT), ROOT)
        self.build = contained(build, self.workspace)
        self.results = contained(results, self.workspace)
        self.source = self.build / "rockboxui.exe"
        self.destination = None
        self.original_hash = None
        self.original_identity = None
        self.attempted = False
        self.record = {"source": str(self.source), "mode": "move_then_restore",
                       "state": "not_moved", "restored": False}
        report["executable_transfer"] = self.record

    def save_record(self):
        (self.results / "executable-transfer.json").write_text(
            json.dumps(self.record, indent=2) + "\n", encoding="utf-8")

    def verify_original(self, path):
        information = path.stat()
        if (information.st_dev, information.st_ino) != self.original_identity:
            raise RuntimeError(f"The borrowed executable was replaced: {path}")
        if digest(path) != self.original_hash:
            raise RuntimeError(f"The borrowed executable hash changed: {path}")

    def move_to(self, runtime):
        source = contained(self.source, self.build)
        runtime = contained(runtime, self.results)
        destination = runtime / source.name
        if os.path.lexists(destination):
            raise RuntimeError(f"Refusing to overwrite a fixture executable: {destination}")
        information = source.stat()
        if information.st_dev != runtime.stat().st_dev:
            raise RuntimeError("The executable loan requires a same-volume rename, never a copy")
        windows_backend().ensure_unused(source)
        self.destination = destination
        self.original_hash = digest(source)
        self.original_identity = information.st_dev, information.st_ino
        self.record.update(destination=str(destination), sha256=self.original_hash,
                           identity=list(self.original_identity), state="move_pending")
        self.save_record()
        self.verify_original(source)
        self.attempted = True
        os.rename(source, destination)
        self.verify_original(destination)
        if os.path.lexists(source):
            raise RuntimeError("The development executable path was recreated during the loan")
        self.record["state"] = "in_fixture"
        self.save_record()

    def restore(self, process):
        if not self.attempted:
            return
        if process is not None and process.poll() is None:
            raise RuntimeError("Cannot restore the executable until the fixture process exits")
        contained(self.build, self.workspace)
        contained(self.destination.parent, self.results)
        if os.path.lexists(self.source):
            if os.path.lexists(self.destination):
                raise RuntimeError(f"Restore destination is occupied; no file was overwritten. "
                                   f"Original test executable: {self.destination}; "
                                   f"occupied path: {self.source}")
            contained(self.source, self.build)
            self.verify_original(self.source)
        else:
            contained(self.destination, self.results)
            windows_backend().ensure_unused(self.destination)
            self.verify_original(self.destination)
            os.rename(self.destination, self.source)
            self.verify_original(self.source)
            if os.path.lexists(self.destination):
                raise RuntimeError("The fixture still contains an executable after restoration")
        self.record.update(state="restored", restored=True, restored_sha256=digest(self.source))
        self.save_record()


def display_labels(build, language):
    identifiers = {name: int(number) for name, number in re.findall(
        r"\b(LANG_\w+), /\* (\d+) \*/", (build / "lang_enum.h").read_text())}
    data = (build / "apps/lang" / f"{language}.lng").read_bytes()
    position = int.from_bytes(data[8:10], "big")
    phrases = {}
    for entry in range(int.from_bytes(data[4:6], "big")):
        identifier = int.from_bytes(data[position:position + 2], "big")
        position += 2
        end = data.index(0, position)
        phrases[identifier] = data[position:end].decode("utf-8")
        position = end + 1
    return {name: phrases[number] for name, number in identifiers.items() if number in phrases}


def validate_build_target(information, target):
    if target not in TARGETS or not re.search(
            r"^Target: " + re.escape(target) + r"\s*$", information, re.MULTILINE):
        raise RuntimeError("The recorder GUI smoke test requires the selected Sansa development build")


def voice_file_settings(voice_files_disabled=False, directory="off", filename="off"):
    if voice_files_disabled:
        return "talk menu: off\ntalk dir: off\ntalk file: off\ntalk mixer level: 0\n"
    return f"talk menu: on\ntalk dir: {directory}\ntalk file: {filename}\n"


def synthetic_recorder_config(language, voice_files_disabled=False):
    return (
        f"lang: /.rockbox/langs/{language}.lng\n"
        "start in screen: root\n"
        + voice_file_settings(voice_files_disabled)
        + "talk dir clip: off\ntalk file clip: off\ntts enabled: on\ntts language: system\n"
        "tts variant: \ntts rate: 175\ntts pitch: 50\ntts volume: 100\ntts range: 50\n"
        "tts wordgap: 0\nvolume: -25\nrec source: mic\nrec channels: mono\n"
        "rec format: wave\nrec frequency: 44\nrec mic gain: 0\n"
        "prerecording time: 0\ntrigger mode: off\nrec path: /Recordings\n"
    )


def prepare_fixture(build, results, language, report, loan, target="sansaclipplus", *,
                    voice_files_disabled=False):
    workspace = contained(_project_materials_root(ROOT), ROOT)
    build = contained(build, workspace)
    information = (build / "rockbox-info.txt").read_text(encoding="utf-8")
    validate_build_target(information, target)
    executable = contained(build / "rockboxui.exe", build)
    with executable.open("rb") as source:
        if source.read(2) != b"MZ":
            raise RuntimeError("Expected a native Windows simulator executable")
    windows_backend().ensure_unused(executable)
    labels = catalog_labels(build, language)
    displayed = display_labels(build, language)
    report["build_features"] = (build / "apps/genlang-features").read_text().strip().split(":")
    label_inputs = (build / "lang_enum.h", build / "apps/lang" / f"{language}.vstrings",
                    build / "apps/lang" / f"{language}.lng")
    report["catalog_inputs"] = [{"path": str(path), "sha256": digest(contained(path, build))}
                                for path in label_inputs]
    required = ("LANG_RECORDING", "LANG_VOLUME", "LANG_GAIN", "LANG_RECORDING_FILENAME",
                "LANG_RECORDING_TIME", "LANG_RECORDING_SIZE", "LANG_RECORD_PRERECORD",
                "LANG_BYTE", "LANG_PAUSE", "LANG_OFF", "LANG_TTS_RECORDER_UNAVAILABLE",
                "LANG_SHUTTINGDOWN")
    report["empty_voice_labels"] = {identifier: displayed.get(identifier)
                                    for identifier in required if not labels.get(identifier)}
    for identifier in required:
        if not labels.get(identifier):
            labels[identifier] = displayed.get(identifier)
        if not labels.get(identifier):
            raise RuntimeError(f"No compiled voice or display phrase for {identifier}")
    runtime = results / "fixture"
    runtime.mkdir()
    disk = runtime / "simdisk"
    resources = disk / ".rockbox"
    resources.mkdir(parents=True)
    report["fixture"] = str(runtime)
    report["voice_files_disabled"] = voice_files_disabled
    report["copies"] = []

    def copy_file(source, destination):
        source = contained(source, build)
        if source.suffix.lower() == ".exe":
            raise RuntimeError("Executable files must be moved through the loan, never copied")
        if destination.exists() or runtime not in destination.resolve().parents:
            raise RuntimeError(f"Unsafe fixture destination: {destination}")
        before = digest(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if digest(source) != before or digest(destination) != before:
            raise RuntimeError(f"Build changed while copying runtime file: {source}")
        report["copies"].append({"source": str(source), "destination": str(destination),
                                 "sha256": before, "purpose": "isolated recorder GUI regression",
                                 "retained_after_test": True})

    def copy_directory(source, destination):
        source = contained(source, build)
        destination.mkdir()
        for child in sorted(source.iterdir()):
            child = contained(child, build)
            if child.is_dir():
                copy_directory(child, destination / child.name)
            elif child.is_file():
                copy_file(child, destination / child.name)
            else:
                raise RuntimeError(f"Unsupported runtime asset: {child}")

    print(f"Copying runtime data from {build} into {runtime}; profiles are excluded. "
          "The development EXE will be moved, not copied, and restored after process exit. "
          "Runtime data, logs and the synthetic profile remain for regression reproduction.", flush=True)
    for library in sorted(build.glob("*.dll")):
        copy_file(library, runtime / library.name)
    copy_file(build / "UI256.bmp", runtime / "UI256.bmp")
    source_resources = contained(build / "simdisk/.rockbox", build)
    for name in RUNTIME_DIRECTORIES:
        copy_directory(source_resources / name, resources / name)
    for name in ("viewers.config", "tagnavi.config", "rockbox-info.txt"):
        copy_file(source_resources / name, resources / name)
    for name in (f"{language}.lng", f"{language}.vstrings"):
        if not (resources / "langs" / name).is_file():
            raise RuntimeError(f"Missing installed language asset: {name}; run fullinstall first")
    if digest(resources / "langs" / f"{language}.vstrings") != report["catalog_inputs"][1]["sha256"]:
        raise RuntimeError("The installed voice catalog does not match the compiled build; refresh fullinstall")
    if not (resources / "codecs/wav_enc.codec").is_file():
        raise RuntimeError("The WAV encoder codec is missing; run fullinstall first")
    (disk / "Recordings").mkdir()
    (runtime / ".tts-recorder-gui-fixture.json").write_text(json.dumps({
        "purpose": "Synthetic recorder GUI test; no user profile copied",
        "source_build": str(build), "language": language,
        "voice_files_disabled": voice_files_disabled,
    }, indent=2), encoding="utf-8")
    (resources / "config.cfg").write_text(
        synthetic_recorder_config(language, voice_files_disabled),
        encoding="utf-8")
    loan.move_to(runtime)
    return runtime, disk, labels


def pcm_summary(path, start=0, end=None):
    if not path.exists():
        return {"bytes": 0, "nonzero_samples": 0, "peak": 0}
    stop = path.stat().st_size if end is None else end
    start -= start % 2
    stop -= stop % 2
    nonzero = peak = size = 0
    with path.open("rb") as source:
        source.seek(start)
        while source.tell() < stop:
            chunk = source.read(min(65536, stop - source.tell()))
            if not chunk:
                break
            chunk = chunk[:len(chunk) // 2 * 2]
            samples = array.array("h", chunk)
            if sys.byteorder != "little":
                samples.byteswap()
            nonzero += sum(value != 0 for value in samples)
            peak = max(peak, max((abs(value) for value in samples), default=0))
            size += len(chunk)
    return {"bytes": size, "nonzero_samples": nonzero, "peak": peak}


class RecorderProbe:
    def __init__(self, process, window, environment, runtime, report, timeout, memory=None):
        self.process = process
        self.window = window
        self.environment = environment
        self.log = runtime / "simulator.log"
        self.pcm = runtime / "recorder-audio.raw"
        self.report = report
        self.timeout = timeout
        self.memory = memory

    def text(self):
        return self.log.read_text(encoding="utf-8", errors="replace") if self.log.exists() else ""

    def mark(self):
        return len(self.text()), self.pcm.stat().st_size if self.pcm.exists() else 0

    def check_process(self):
        if self.process.poll() is not None:
            raise RuntimeError(f"Recorder simulator exited unexpectedly: {self.process.returncode}")

    def press(self, key):
        self.check_process()
        send_key(self.process.pid, self.window, key, True, self.environment)
        try:
            time.sleep(0.10)
        finally:
            if self.process.poll() is None:
                send_key(self.process.pid, self.window, key, False, self.environment)

    def drain(self, phase=None):
        text = self.text()
        log_position = len(text)
        utterances = re.findall(r"^TTS utterance: (.*)$", text, re.MULTILINE)
        settle_time = 0.8 + len(utterances[-1]) / 8 if utterances else 0.8
        last_activity = time.monotonic()
        deadline = last_activity + self.timeout
        next_snapshot = last_activity
        while time.monotonic() < deadline:
            self.check_process()
            if phase and self.report.get("trace_speech") and time.monotonic() >= next_snapshot:
                self.memory.snapshot(phase)
                next_snapshot = time.monotonic() + 0.25
            text = self.text()
            recent = text[log_position:]
            if "TTS:" in recent or "TTS utterance:" in recent:
                last_activity = time.monotonic()
                utterances = re.findall(r"^TTS utterance: (.*)$", text, re.MULTILINE)
                settle_time = 0.8 + len(utterances[-1]) / 8 if utterances else 0.8
            log_position = len(text)
            if time.monotonic() - last_activity >= settle_time:
                return
            time.sleep(0.1)
        raise AssertionError("Recorder speech did not become idle before the next action")

    def capture(self, name, action, predicate, initial=False, continue_on_failure=False, timeout=None,
                probe_start=False):
        if not initial:
            self.drain()
        marker = (0, 0) if initial else self.mark()
        observation = {"name": name, "status": "in_progress", "log_start": marker[0],
                       "pcm_start": marker[1]}
        self.report["checks"].append(observation)
        sampled_after_start = False
        sampled_timeout = False
        try:
            if probe_start:
                self.memory.snapshot("before_start")
            if self.report.get("trace_speech"):
                self.memory.snapshot(f"{name}: before action")
            if action:
                observation["action_monotonic"] = time.monotonic()
                action()
                observation["action_finished_monotonic"] = time.monotonic()
            action_finished = time.monotonic()
            deadline = action_finished + (self.timeout if timeout is None else timeout)
            while time.monotonic() < deadline:
                if probe_start and not sampled_after_start and time.monotonic() >= action_finished + 1:
                    self.memory.snapshot("start_after_one_second")
                    sampled_after_start = True
                text = self.text()[marker[0]:]
                segments = re.findall(r"^TTS: (.*)$", text, re.MULTILINE)
                utterances = re.findall(r"^TTS utterance: (.*)$", text, re.MULTILINE)
                if predicate(segments) and utterances and (not probe_start or sampled_after_start):
                    break
                if "TTS: synthesis failed" in text:
                    raise AssertionError("The synthesizer reported a failure")
                self.check_process()
                time.sleep(0.1)
            else:
                if probe_start:
                    self.memory.snapshot("start_timeout")
                    sampled_timeout = True
                raise AssertionError(f"Missing recorder speech for {name}; "
                                     "a timeout is not evidence that SDL stubs caused it")
            self.drain(f"{name}: speech drain")
            if "TTS: synthesis failed" in self.text()[marker[0]:]:
                raise AssertionError(f"The synthesizer reported a failure during {name}")
            observation.update(status="passed")
            if probe_start:
                self.memory.snapshot("start_speech_completed")
        except Exception as error:
            observation.update(status="failed", error=str(error))
            if probe_start and not sampled_timeout:
                self.memory.snapshot("start_failure")
            if not continue_on_failure or not isinstance(error, AssertionError):
                raise
        finally:
            text = self.text()[marker[0]:]
            observation.update(segments=re.findall(r"^TTS: (.*)$", text, re.MULTILINE),
                               utterances=re.findall(r"^TTS utterance: (.*)$", text, re.MULTILINE),
                               log_end=len(self.text()), pcm_end=self.mark()[1],
                               pcm_status="pending_process_exit")
        return observation

    def quiet(self, name, duration=1.2):
        self.drain()
        marker = self.mark()
        time.sleep(duration)
        self.check_process()
        segments = re.findall(r"^TTS: (.*)$", self.text()[marker[0]:], re.MULTILINE)
        observation = {"name": name, "seconds": duration, "segments": segments,
                       "status": "failed" if segments else "passed"}
        self.report["checks"].append(observation)
        if segments:
            raise AssertionError(f"Idle recorder redraws produced speech: {segments}")

    def seek_row(self, name, label, maximum=20):
        for index in range(maximum):
            observation = self.capture(f"{name}: navigation {index + 1}",
                                       lambda: self.press("Down"), bool)
            if any(label in segment for segment in observation["segments"]):
                if label not in " ".join(observation["utterances"]):
                    raise AssertionError(f"Selected row never reached synthesis: {label}")
                return observation
        raise AssertionError(f"Recorder row not found: {label}")


def exercise_recorder(probe, labels):
    startup = probe.capture("startup speech", None, bool, initial=True)
    native = windows_backend()
    if native.user32.IsWindowVisible(probe.window):
        native.set_hidden(probe.process.pid, probe.window, True)
    probe.report["window_hidden"] = not bool(native.user32.IsWindowVisible(probe.window))
    probe.report["window_hide_stage"] = "after_startup_speech"
    segments = startup["segments"]
    for index in range(24):
        if segments and segments[-1] == labels["LANG_RECORDING"]:
            break
        segments = probe.capture(f"root menu navigation {index + 1}",
                                 lambda: probe.press("Down"), bool)["segments"]
    else:
        raise AssertionError("Recording was not found in the root menu")
    volume_label = labels["LANG_VOLUME"]
    entry = probe.capture("recorder initial volume selection", lambda: probe.press("space"),
                          lambda phrases: any(volume_label in phrase for phrase in phrases))
    initial_volume = next(phrase for phrase in entry["segments"] if volume_label in phrase)
    probe.capture("volume adjustment speaks changed value", lambda: probe.press("Right"),
                  lambda phrases: any(volume_label in phrase and phrase != initial_volume
                                      for phrase in phrases))
    probe.capture("volume adjustment restores original value", lambda: probe.press("Left"),
                  lambda phrases: initial_volume in phrases)
    for cycle in range(1, probe.report.get("volume_cycles", 1)):
        probe.capture(f"volume stress cycle {cycle}: changed value", lambda: probe.press("Right"),
                      lambda phrases: any(volume_label in phrase and phrase != initial_volume
                                          for phrase in phrases))
        probe.capture(f"volume stress cycle {cycle}: restored value", lambda: probe.press("Left"),
                      lambda phrases: initial_volume in phrases)
    gain = probe.seek_row("microphone gain selection", labels["LANG_GAIN"])
    original_gain = next(phrase for phrase in gain["segments"] if labels["LANG_GAIN"] in phrase)
    probe.capture("gain adjustment speaks changed value", lambda: probe.press("Right"),
                  lambda phrases: any(labels["LANG_GAIN"] in phrase and phrase != original_gain
                                      for phrase in phrases))
    probe.capture("gain adjustment restores original value", lambda: probe.press("Left"),
                  lambda phrases: original_gain in phrases)
    if "agc" in probe.report["build_features"]:
        for name in ("AGC preset", "AGC maximum gain"):
            probe.capture(name, lambda: probe.press("Down"), bool)
    probe.report["row_navigation_basis"] = (
        "Clip+ recording layout: volume, microphone gain, optional AGC rows, filename, time, size; "
        "synthetic configuration selects microphone, mono and no prerecording")
    probe.capture("filename selection", lambda: probe.press("Down"),
                  lambda phrases: labels["LANG_RECORDING_FILENAME"] in phrases,
                  continue_on_failure=True, timeout=6)
    probe.capture("elapsed time", lambda: probe.press("Down"),
                  lambda phrases: labels["LANG_RECORDING_TIME"] in phrases and len(phrases) >= 2,
                  continue_on_failure=True, timeout=6)
    expected_size = f'{labels["LANG_RECORDING_SIZE"]} 0{labels["LANG_BYTE"]}'
    probe.capture("recorded size", lambda: probe.press("Down"),
                  lambda phrases: expected_size in phrases,
                  continue_on_failure=True, timeout=6)
    probe.quiet("idle time/size redraws do not repeat speech")
    probe.report["row_check_count"] = len(probe.report["checks"])
    probe.report["row_speech_passed"] = all(check["status"] == "passed" for check in probe.report["checks"])
    probe.report["state_controls"] = "unavailable; start/pause/resume/stop transitions not tested"
    probe.report["availability_feedback"] = "in_progress"
    unavailable = labels["LANG_TTS_RECORDER_UNAVAILABLE"]
    rejected = probe.capture("unsupported Start speaks unavailable", lambda: probe.press("space"),
                  lambda phrases: phrases.count(unavailable) == 1,
                  probe_start=True)
    if unavailable not in " ".join(rejected["utterances"]):
        raise AssertionError("Unavailable Start message did not reach synthesis")
    if labels["LANG_RECORDING"] in rejected["segments"] or any("/Recordings/" in phrase for phrase in rejected["segments"]):
        raise AssertionError("Unavailable Start announced a recording state or filename")
    probe.report["checks"].append(verify_unavailable_start(probe.report["memory_diagnostics"]))
    probe.capture("navigation after unavailable Start speaks time", lambda: probe.press("Up"),
                  lambda phrases: labels["LANG_RECORDING_TIME"] in phrases and len(phrases) >= 2)
    probe.capture("navigation after unavailable Start speaks size", lambda: probe.press("Down"),
                  lambda phrases: expected_size in phrases)
    probe.quiet("unavailable Start does not repeat on redraw")
    recordings = probe.pcm.parent / "simdisk/Recordings"
    if any(path.is_file() for path in recordings.rglob("*")):
        raise AssertionError("Unavailable Start created a recording file")
    probe.report["checks"].append({"name": "unavailable Start creates no recording file", "status": "passed"})
    probe.report["availability_feedback"] = "passed"
    probe.capture("leave recorder returns to the root menu", lambda: probe.press("Escape"),
                  lambda phrases: labels["LANG_RECORDING"] in phrases)
    probe.drain()
    marker = probe.mark()
    shutdown(probe.process, probe.window, probe.environment, timeout=20)
    text = probe.text()[marker[0]:]
    phrases = re.findall(r"^TTS: (.*)$", text, re.MULTILINE)
    utterances = re.findall(r"^TTS utterance: (.*)$", text, re.MULTILINE)
    statistics = pcm_summary(probe.pcm, marker[1])
    if phrases.count(labels["LANG_SHUTTINGDOWN"]) != 1:
        raise AssertionError("Graceful shutdown did not produce exactly one shutdown speech segment")
    if labels["LANG_SHUTTINGDOWN"] not in " ".join(utterances) or statistics["nonzero_samples"] < 128:
        raise AssertionError("Shutdown speech did not reach synthesized PCM output")
    probe.report["checks"].append({"name": "graceful shutdown speaks once", "status": "passed",
                                   "segments": phrases, "utterances": utterances, "pcm": statistics})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, default="sansaclipplus")
    parser.add_argument("--build", type=Path)
    parser.add_argument("--language", choices=("polski", "english"), default="polski")
    parser.add_argument("--build-ready", action="store_true",
                        help="Confirm that the parent build/fullinstall is finished and stable")
    parser.add_argument("--voice-files-disabled", action="store_true",
                        help="Disable recorded menu/file/directory speech and mute recorded voices in the clean TTS fixture")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--volume-cycles", type=int, default=1,
                        help="Verify each changed/restored volume utterance and its PCM repeatedly")
    parser.add_argument("--trace-speech", action="store_true",
                        help="Read validated speech-state symbols during each PCM observation")
    arguments = parser.parse_args()
    if not arguments.build_ready:
        parser.error("Wait for the parent build/fullinstall, then explicitly pass --build-ready")
    if sys.platform != "win32":
        parser.error("Run with native Windows Python, not WSL or Wine")
    if not 5 <= arguments.timeout <= 60:
        parser.error("--timeout must be between 5 and 60 seconds")
    if not 1 <= arguments.volume_cycles <= 50:
        parser.error("--volume-cycles must be between 1 and 50")
    workspace = contained(_project_materials_root(ROOT), ROOT)
    build = contained(arguments.build or workspace / TARGETS[arguments.target], workspace)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    test_root = workspace / "tts-recorder-gui-tests"
    if test_root.exists():
        test_root = contained(test_root, workspace)
    else:
        test_root.mkdir()
    results = test_root / timestamp
    results.mkdir()
    report = {"passed": False, "row_speech_passed": False, "state_controls": "not_run",
              "availability_feedback": "not_run",
              "language": arguments.language, "target": arguments.target,
              "volume_cycles": arguments.volume_cycles,
              "trace_speech": arguments.trace_speech,
              "voice_files_disabled": arguments.voice_files_disabled,
              "source_build": str(build), "checks": [],
              "source_facts": source_facts(), "limitations": [
                  "The Windows UI test does not exercise the duplex-capable native recorder backend.",
                  "SDL capture DMA is stubbed; a filename/state announcement does not prove audio was captured or saved.",
                  "PCM evidence is little-endian signed 16-bit SDL output, not microphone input or a listening test.",
                  "SDL locks its output file while running; per-action PCM ranges are verified after exit.",
                  "Action spacing uses log quiescence plus a conservative text-length delay, not measured voice completion.",
                  "Window hiding occurs after startup speech; hidden-at-start is not validated by this smoke test.",
                  "No physical-player, native-monitoring, live-level, AGC, clipping-warning or NVDA/UIA validation.",
                  "Recording transitions are unavailable; this validates explicit rejection, not simulated success.",
                  "Missing unavailable feedback or unresponsive navigation remains a failed test.",
              ]}
    process = probe = runtime = memory = None
    loan = ExecutableLoan(build, results, report)
    print(f"Native recorder GUI evidence: {results}", flush=True)
    try:
        memory_layout = prepare_memory_diagnostics(build / "rockboxui.exe", report)
        runtime, disk, labels = prepare_fixture(build, results, arguments.language, report, loan,
                                               arguments.target,
                                               voice_files_disabled=arguments.voice_files_disabled)
        executable = runtime / "rockboxui.exe"
        environment = dict(os.environ, SDL_VIDEODRIVER="windows", SDL_AUDIODRIVER="disk",
                           SDL_DISKAUDIOFILE=str(runtime / "recorder-audio.raw"), SDL_DISKAUDIODELAY="12")
        process = subprocess.Popen([str(executable), "--root", str(disk), "--audiodev",
                                    environment["SDL_DISKAUDIOFILE"], "--debugbuttons"],
                                   cwd=runtime, env=environment, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        report["pid"] = process.pid
        window = find_window(process.pid, environment)
        memory = RecorderMemoryProbe(process, executable, memory_layout, report["memory_diagnostics"])
        probe = RecorderProbe(process, window, environment, runtime, report, arguments.timeout, memory)
        exercise_recorder(probe, labels)
        report["failed_checks"] = [check["name"] for check in report["checks"] if check["status"] != "passed"]
        report["passed"] = not report["failed_checks"]
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if report["availability_feedback"] == "in_progress":
            report["availability_feedback"] = "failed"
    finally:
        previous_interrupt_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            if process is not None and process.poll() is None:
                report["forced_test_process_cleanup"] = True
                report["passed"] = False
                try:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=8)
                except Exception as error:
                    report["cleanup_error"] = str(error)
            if process is not None:
                report["exit_code"] = process.returncode
            if memory is not None:
                try:
                    memory.close()
                except Exception as error:
                    report["memory_diagnostics"]["handle_cleanup_error"] = str(error)
                    report["passed"] = False
            try:
                loan.restore(process)
            except Exception as error:
                report["passed"] = False
                report["executable_restore_error"] = str(error)
                loan.record.update(state="restore_failed", error=str(error))
                print(f"EXECUTABLE RESTORATION FAILED: {error}", file=sys.stderr, flush=True)
                try:
                    loan.save_record()
                except Exception as record_error:
                    report["transfer_record_error"] = str(record_error)
        finally:
            signal.signal(signal.SIGINT, previous_interrupt_handler)
        try:
            inputs = report.get("copies", []) + [dict(source=item["path"], sha256=item["sha256"])
                                                for item in report.get("catalog_inputs", [])]
            changed = [item["source"] for item in inputs
                       if not Path(item["source"]).is_file() or digest(Path(item["source"])) != item["sha256"]]
            report["changed_source_assets"] = changed
            if changed:
                report["passed"] = False
            if runtime is not None:
                recordings = runtime / "simdisk/Recordings"
                report["recording_artifacts"] = [
                    {"path": str(path.relative_to(runtime)), "bytes": path.stat().st_size,
                     "sha256": digest(path), "is_capture_success_evidence": False}
                    for path in recordings.glob("*") if path.is_file()]
                report["pcm"] = pcm_summary(runtime / "recorder-audio.raw")
                for check in report["checks"]:
                    if check.get("pcm_status") != "pending_process_exit":
                        continue
                    statistics = pcm_summary(runtime / "recorder-audio.raw",
                                             check["pcm_start"], check["pcm_end"])
                    check.update(pcm=statistics, pcm_status="verified_after_exit")
                    if statistics["nonzero_samples"] < 128 or statistics["peak"] < 64:
                        check["pcm_status"] = "failed"
                        if check["status"] == "passed":
                            check.update(status="failed", error="Speech was logged but no meaningful mixer PCM followed")
                row_count = report.get("row_check_count", 0)
                report["row_speech_passed"] = bool(row_count) and all(
                    check["status"] == "passed" for check in report["checks"][:row_count])
                if any(check["status"] != "passed" for check in report["checks"]
                       if check["name"] == "unsupported Start speaks unavailable" or
                       check["name"].startswith("navigation after unavailable Start")):
                    report["availability_feedback"] = "failed"
                report["failed_checks"] = [check["name"] for check in report["checks"] if check["status"] != "passed"]
                if report["failed_checks"]:
                    report["passed"] = False
        except Exception as error:
            report["passed"] = False
            report["evidence_error"] = str(error)
        (results / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "row_speech_passed": report["row_speech_passed"],
                      "state_controls": report["state_controls"], "availability_feedback": report["availability_feedback"],
                      "error": report.get("error"),
                      "failed_checks": report.get("failed_checks"),
                      "executable_restored": loan.record["restored"],
                      "executable_transfer_state": loan.record["state"],
                      "executable_restore_error": report.get("executable_restore_error"),
                      "report": str(results / "report.json")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
