import argparse
import array
import base64
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import signal
import subprocess
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root, confined_path



ROOT = Path(__file__).resolve().parents[2]
TARGETS = (
    "sansaclipplus", "sansaclipzip", "xduoox3", "xduoox3ii", "xduoox20",
    "shanlingq1", "ipod6g", "fiiom3k", "fiiom3klinux", "aigoerosq",
    "erosqnative", "iriverh300",
)
DEFAULT_TARGETS = ("xduoox3", "shanlingq1")
SOURCE_FILES = (
    "tools/configure", "tools/root.make", "tools/genlang", "apps/tts.c", "apps/tts.h", "apps/tts_reader.c",
    "apps/bookmark.c", "apps/bookmark.h",
    "apps/misc.c", "apps/recorder/recording.c",
    "apps/settings.h", "apps/settings_list.c", "apps/menus/settings_menu.c",
    "apps/lang/english.lang", "apps/lang/polski.lang", "apps/talk.c",
    "apps/voice_thread.c", "apps/pcmbuf.c", "apps/pcmbuf.h", "apps/plugin.h",
    "lib/espeak/rb_espeak.cpp", "lib/espeak/rb_espeak.h",
    "lib/espeak/espeak_file.h", "lib/espeak/espeak_locale.h",
    "lib/espeak/espeak.make", "lib/espeak/engine/speak_lib.cpp",
    "lib/espeak/engine/speak_lib.h", "lib/espeak/engine/synthesize.h",
    "lib/espeak/engine/setlengths.cpp", "lib/espeak/engine/translate.h",
    "lib/espeak/engine/translate.cpp", "lib/espeak/engine/readclause.cpp",
    "lib/espeak/engine/dictionary.cpp", "lib/espeak/engine/wavegen.cpp",
    "lib/espeak/sonic/sonic.c", "lib/espeak/sonic/sonic.h",
    "lib/espeak/sonic/LICENSE", "lib/espeak/sonic/README.md", "lib/espeak/SONIC.sha256",
    "lib/espeak/sonic/.gitattributes",
    "firmware/target/hosted/sdl/system-sdl.c",
    "firmware/target/hosted/sdl/system-sdl.h",
    "firmware/target/hosted/sdl/kernel-sdl.c",
)
REQUIRED_SYMBOLS = (
    "rb_espeak_synth", "espeak_Synth", "tts_speak", "tts_read_file",
    "rb_espeak_synth_character", "voice_play_pcm", "voice_pause_pcm",
    "pcmbuf_update_voice_volume",
)
SONIC_SYMBOLS = (
    "espeak_SetSonicRate", "sonicCreateStream", "sonicSetSpeed",
    "sonicWriteShortToStream", "sonicReadShortFromStream", "sonicFlushStream", "sonicDestroyStream",
)
SMOKE_FILES = ("simulator.log", "stdout.log", "startup-audio.raw")
CATALOG_FILES = ("english.list", "english.lng", "english.vstrings", "polski.lng", "polski.vstrings")
CATALOG_LOGS = ("catalog-english.log", "catalog-polski.log")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(path):
    return confined_path(path, _project_materials_root(ROOT),
                         error="Diagnostic path is outside Workspace")


def evidence_reference(path):
    for category in ("Workspace", "Snapshots"):
        root = _project_materials_root(ROOT, category)
        if Path(path).is_relative_to(root):
            resolved = confined_path(path, root,
                                     error="Evidence is outside project diagnostic directories")
            return (Path(category) / resolved.relative_to(root)).as_posix()
    raise RuntimeError(f"Evidence is outside project diagnostic directories: {path}")


def resolve_evidence_path(reference):
    if (not isinstance(reference, str) or "\\" in reference or ":" in reference
            or PurePosixPath(reference).is_absolute() or PureWindowsPath(reference).drive
            or any(part in ("", ".", "..") for part in reference.split("/"))):
        raise RuntimeError(f"Unsafe diagnostic evidence reference: {reference}")
    category, separator, relative = reference.partition("/")
    if not separator or category.casefold() not in ("workspace", "snapshots"):
        raise RuntimeError(f"Unsupported diagnostic evidence category: {reference}")
    root = _project_materials_root(ROOT, category)
    return confined_path(root / relative, root,
                         error="Evidence is outside project diagnostic directories")


def save_report(path, report):
    temporary = contained(path.with_suffix(".json.tmp"))
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def report_lock(path):
    path = contained(path.resolve(strict=True))
    lock = contained(path.with_suffix(".json.lock"))
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}\n")
    try:
        yield path
    finally:
        lock.unlink()


def run(command, directory, log, environment, timeout):
    print("Running:", " ".join(map(str, command)), flush=True)
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=directory, env=environment,
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            raise
    if returncode:
        raise RuntimeError(f"Command failed ({returncode}); see {log}")
    return round(time.monotonic() - started, 3)


def startup_fixture(build):
    config = contained(build / "simdisk/.rockbox/config.cfg")
    if config != build / "simdisk/.rockbox/config.cfg":
        raise RuntimeError("Startup config must not redirect outside its runtime")
    try:
        text = config.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise RuntimeError("Startup config is not valid UTF-8") from error
    rates = re.findall(r"^tts rate:[ \t]*([^\r\n]*)", text, re.M)
    scales = re.findall(r"^tts rate scale:[ \t]*([^\r\n]*)", text, re.M)
    if (len(rates) != 1 or not re.fullmatch(r"\d+", rates[0].strip())
            or len(scales) != 1 or scales[0].strip() not in ("percent", "wpm")):
        raise RuntimeError("Startup config requires one canonical WPM rate and display scale")
    rate = int(rates[0].strip())
    if not 80 <= rate <= 1350:
        raise RuntimeError("Startup canonical rate is outside 80..1350 WPM")
    difference = rate - 175
    percent = (abs(difference) * 1000 + 87) // 175
    return {"rate_wpm": rate, "rate_scale": scales[0].strip(),
            "expected_percent_tenths": -percent if difference < 0 else percent,
            "config": {"path": evidence_reference(config), "sha256": digest(config)}}


def catalog_strings(path, target_id):
    data = path.read_bytes()
    cookie = 0x9a if path.suffix == ".vstrings" else 0x1a
    if len(data) < 10 or data[:3] != bytes((cookie, 0x06, target_id)):
        raise RuntimeError(f"Invalid target-specific language catalog: {path}")
    count = int.from_bytes(data[4:6], "big")
    size = int.from_bytes(data[6:8], "big")
    offset = int.from_bytes(data[8:10], "big")
    if offset != 10 or size != len(data) - offset:
        raise RuntimeError(f"Invalid core catalog size/offset: {path}")
    values = {}
    while offset < len(data):
        end = data.find(b"\0", offset + 2)
        identifier = int.from_bytes(data[offset:offset + 2], "big")
        if end < 0 or identifier in values:
            raise RuntimeError(f"Truncated or duplicate catalog entry: {path}")
        try:
            values[identifier] = data[offset + 2:end].decode("utf-8")
        except UnicodeError as error:
            raise RuntimeError(f"Invalid UTF-8 catalog entry: {path}") from error
        offset = end + 1
    if len(values) != count:
        raise RuntimeError(f"Invalid core catalog count: {path}")
    return values


def stage_catalogs(build, target, environment, logs):
    languages = contained(build / "simdisk/.rockbox/langs")
    if languages != build / "simdisk/.rockbox/langs":
        raise RuntimeError("Catalog directory must not redirect outside its runtime")
    languages.mkdir(parents=True, exist_ok=True)
    if any(languages.iterdir()):
        raise RuntimeError("Refusing to overwrite existing or partial language catalogs")
    makefile = (build / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^export TARGET_ID=(\d+)$", makefile, re.M)
    if match is None or not 0 <= int(match.group(1)) <= 255:
        raise RuntimeError("Missing or invalid target ID for catalog generation")
    target_id = int(match.group(1))
    features = (build / "apps/genlang-features").read_text(encoding="utf-8").strip()
    for language in ("english", "polski"):
        log = contained(logs / ("catalog-" + language + ".log"))
        if log != logs / ("catalog-" + language + ".log") or log.exists():
            raise RuntimeError("Catalog log already exists or redirects to another file")
        run([
            "perl", "-s", str(ROOT / "tools/genlang"),
            "-e=" + str(ROOT / "apps/lang/english.lang"),
            "-t=" + target + ":" + features, "-i=" + str(target_id),
            "-b=" + str(languages / (language + ".lng")),
            "-c=" + str(languages / (language + ".vstrings")),
            str(ROOT / "apps/lang" / (language + ".lang")),
        ], build, log, environment, 60)
    if {path.name for path in languages.iterdir()} != set(CATALOG_FILES):
        raise RuntimeError("Incomplete or unexpected generated language catalogs")
    identifiers = {}
    try:
        index = (languages / "english.list").read_text(encoding="utf-8")
    except UnicodeError as error:
        raise RuntimeError("Generated catalog index is not valid UTF-8") from error
    for line in index.splitlines():
        match = re.fullmatch(r"core:(LANG_TTS(?:_\w+)?):(\d+)", line)
        if match:
            name, value = match.groups()
            if name in identifiers or int(value) in identifiers.values():
                raise RuntimeError("Duplicate generated TTS identifier")
            identifiers[name] = int(value)
    unavailable = "LANG_TTS_RECORDER_UNAVAILABLE"
    if len(identifiers) != 38 or unavailable not in identifiers:
        raise RuntimeError("Expected all 38 TTS identifiers including recorder-unavailable")
    recorder_labels = {}
    for name in CATALOG_FILES[1:]:
        values = catalog_strings(languages / name, target_id)
        if any(not values.get(identifier, "").strip() for identifier in identifiers.values()):
            raise RuntimeError(f"Missing display/speech text for a TTS identifier in {name}")
        recorder_labels[name] = values[identifiers[unavailable]]
    return {"target_id": target_id, "catalogs": {
                name: digest(languages / name) for name in CATALOG_FILES},
            "tts_catalog_ids": identifiers, "recorder_unavailable_labels": recorder_labels}


def stage_runtime(build, target, source, environment, logs=None):
    runtime = build / "simdisk/.rockbox"
    runtime.mkdir(parents=True, exist_ok=True)
    data = runtime / "espeak-data"
    print(f"Required isolated runtime copy: {source / 'espeak-data'} -> {data}", flush=True)
    shutil.copytree(source / "espeak-data", data)
    original = {path.relative_to(source / "espeak-data").as_posix(): digest(path)
                for path in (source / "espeak-data").rglob("*") if path.is_file()}
    copied = {path.relative_to(data).as_posix(): digest(path)
              for path in data.rglob("*") if path.is_file()}
    if original != copied:
        raise RuntimeError("Copied engine data failed integrity verification")
    catalogs = stage_catalogs(build, target, environment, logs or build)
    (runtime / "config.cfg").write_text(
        "lang: /.rockbox/langs/polski.lng\ntalk menu: on\n"
        "tts enabled: on\ntts language: system\ntts variant: \n"
        "tts rate: 175\ntts rate scale: percent\ntts punctuation: none\n"
        "tts ducking: on\ntts ducking level: 25\n"
        "tts pitch: 50\ntts volume: 100\ntts range: 50\ntts wordgap: 0\n"
        "volume: -25\nstart in screen: root\n", encoding="utf-8")
    return {"data_files": len(copied), "engine_data_sha256": copied,
            "fixture": startup_fixture(build), **catalogs}


def build_targets(arguments):
    if os.name == "nt":
        raise RuntimeError("Run the build phase under WSL; native Windows runs only --smoke-report")
    source = arguments.espeak_source.resolve(strict=True)
    sdk = arguments.sdl_sdk.resolve()
    environment = dict(os.environ, VERSION="tts-cross-target-diagnostic",
                       OMP_NUM_THREADS=str(arguments.jobs))
    windows = arguments.platform == "windows"
    if windows:
        version = subprocess.check_output([str(sdk / "bin/sdl2-config"), "--version"], text=True).strip()
        if version != "2.32.10":
            raise RuntimeError(f"Expected the verified SDL 2.32.10 SDK, found {version}")
        environment["PATH"] = str(sdk / "bin") + os.pathsep + environment["PATH"]
        environment["CXX"] = "x86_64-w64-mingw32-g++"
    else:
        version = subprocess.check_output(["sdl2-config", "--version"], text=True).strip()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    workspace = contained(_project_materials_root(ROOT) / "tts-target-tests" / timestamp)
    workspace.mkdir(parents=True)
    report_path = workspace / "report.json"
    report = {
        "platform": arguments.platform, "sdl_version": version,
        "engine_data_revision": subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
        "scope": "SDL simulator core only; no device firmware, plugins, codecs or user package",
        "hardware_validated": False, "targets": [],
        "build_state": "in_progress",
    }
    save_report(report_path, report)
    print("Target evidence:", workspace, flush=True)
    for target in arguments.targets:
        build = contained(workspace / target)
        build.mkdir()
        entry = {"target": target, "directory": evidence_reference(build),
                 "compiled": False, "smoke": "not run"}
        report["targets"].append(entry)
        save_report(report_path, report)
        try:
            entry["sources_before"] = {name: digest(ROOT / name) for name in SOURCE_FILES}
            configure = ["bash", str(ROOT / "tools/configure"), "--target=" + target,
                         "--type=as6" if windows else "--type=s", "--integrated-espeak"]
            if not windows:
                configure.append("--sdl-threads")
            entry["configure_seconds"] = run(configure, build, build / "configure.log", environment, 120)
            entry["build_seconds"] = run(["make", f"-j{arguments.jobs}", "bin"], build,
                                         build / "build.log", environment, arguments.timeout)
            executable = build / ("rockboxui.exe" if windows else "rockboxui")
            entry["executable_sha256"] = digest(executable)
            entry["executable_bytes"] = executable.stat().st_size
            prefix = "x86_64-w64-mingw32-" if windows else ""
            symbols = subprocess.check_output([prefix + "nm", str(executable)], text=True)
            entry["integrated_symbols"] = {
                name: bool(re.search(r"\b" + name + r"$", symbols, re.M)) for name in REQUIRED_SYMBOLS}
            if not all(entry["integrated_symbols"].values()):
                raise RuntimeError("The core is missing an integrated speech symbol")
            entry["sonic_symbols"] = {
                name: bool(re.search(r"\b" + name + r"$", symbols, re.M)) for name in SONIC_SYMBOLS}
            if not all(entry["sonic_symbols"].values()):
                raise RuntimeError("The core is missing a linked Sonic symbol")
            if windows:
                headers = subprocess.check_output([prefix + "objdump", "-p", str(executable)], text=True)
                (build / "pe-headers.txt").write_text(headers, encoding="utf-8")
                entry["imports"] = re.findall(r"DLL Name: (\S+)", headers)
                if not re.search(r"Subsystem\s+00000002", headers):
                    raise RuntimeError("Expected the native Windows GUI subsystem")
                if any("espeak" in name.lower() for name in entry["imports"]):
                    raise RuntimeError("Unexpected external eSpeak DLL dependency")
            entry["sources_after"] = {name: digest(ROOT / name) for name in SOURCE_FILES}
            entry["sources_changed_during_build"] = [
                name for name in SOURCE_FILES if entry["sources_before"][name] != entry["sources_after"][name]]
            if entry["sources_changed_during_build"]:
                raise RuntimeError("Shared sources changed during this diagnostic build")
            entry["compiled"] = True
            if not arguments.build_only:
                entry["runtime"] = stage_runtime(build, target, source, environment)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            entry["error"] = str(error)
            print(f"{target}: {error}", flush=True)
        save_report(report_path, report)
    report["build_state"] = "completed"
    save_report(report_path, report)
    print("Report:", report_path, flush=True)
    return all(entry["compiled"] and "error" not in entry for entry in report["targets"])


def smoke_report(path, video_driver=None, repeat=False):
    with report_lock(path) as locked_path:
        return smoke_locked_report(locked_path, video_driver, repeat)


def smoke_locked_report(path, video_driver=None, repeat=False):
    from test_tts_simulator import ensure_unused, windows_backend

    path = contained(path.resolve(strict=True))
    report = json.loads(path.read_text(encoding="utf-8"))
    if (report.get("build_state", "completed") != "completed"
            or report.get("refresh_round", {}).get("state", "passed") != "passed"):
        raise RuntimeError("Cannot smoke an ongoing or failed build/refresh round")
    if not report["targets"] or any(not entry["compiled"] or entry.get("error")
                                    or entry.get("abi_refresh_error") for entry in report["targets"]):
        raise RuntimeError("Smoke requires a completely compiled, error-free target group")
    missing_runtime = [entry["target"] for entry in report["targets"]
                       if entry["compiled"] and "runtime" not in entry]
    if missing_runtime:
        raise RuntimeError("Runtime was not staged for " + ", ".join(missing_runtime)
                           + "; build the selected targets without --build-only before smoke testing")
    windows = report["platform"] == "windows"
    video_driver = video_driver or ("windows" if windows else "dummy")
    if windows != (os.name == "nt"):
        raise RuntimeError("Run smoke on the native host corresponding to the build platform")
    if video_driver == "windows" and not windows:
        raise RuntimeError("The Windows video driver requires a native Windows build")
    native = windows_backend()
    for entry in report["targets"]:
        build = contained(resolve_evidence_path(entry["directory"]))
        if build.parent != path.parent or build.name != entry["target"] or entry["target"] not in TARGETS:
            raise RuntimeError("Unexpected diagnostic target directory")
        executable = contained(build / ("rockboxui.exe" if windows else "rockboxui"))
        if executable.parent != build or digest(executable) != entry["executable_sha256"]:
            raise RuntimeError("Diagnostic executable path or hash changed since validation")
        if any(digest(ROOT / name) != checksum for name, checksum in entry["sources_after"].items()):
            raise RuntimeError("Shared sources changed since compilation; refresh before new smoke")
        fixture = startup_fixture(build)
        if "fixture" in entry["runtime"] and fixture != entry["runtime"]["fixture"]:
            raise RuntimeError("Startup fixture changed since runtime staging")
        if set(entry["runtime"]["catalogs"]) != set(CATALOG_FILES):
            raise RuntimeError("Startup requires the complete recorded catalog set")
        for name, checksum in entry["runtime"]["catalogs"].items():
            if name not in CATALOG_FILES:
                raise RuntimeError("Unexpected startup catalog path")
            artifact = verify_evidence({"path": evidence_reference(build / "simdisk/.rockbox/langs" / name),
                                        "sha256": checksum})
            if artifact != build / "simdisk/.rockbox/langs" / name:
                raise RuntimeError("Startup catalog redirects outside its runtime")
        ensure_unused(executable, native)
    for entry in report["targets"]:
        if not entry["compiled"] or "runtime" not in entry:
            continue
        build = contained(resolve_evidence_path(entry["directory"]))
        executable = build / ("rockboxui.exe" if windows else "rockboxui")
        fixture = startup_fixture(build)
        if "fixture" in entry["runtime"] and fixture != entry["runtime"]["fixture"]:
            raise RuntimeError("Startup fixture changed before smoke")
        parameter_pattern = rf"TTS parameters: language=pl variant= rate={fixture['rate_wpm']}(?:\s|$)"
        if digest(executable) != entry["executable_sha256"]:
            raise RuntimeError("Diagnostic executable changed since validation")
        ensure_unused(executable, native)
        if entry["smoke"] != "not run":
            if not repeat:
                raise RuntimeError("Use --repeat-smoke to archive existing smoke evidence before retrying")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            archive = contained(build / "smoke-history" / timestamp)
            archive.mkdir(parents=True)
            previous = dict(entry["smoke"], artifacts={})
            for name in ("simulator.log", "stdout.log", "startup-audio.raw"):
                original = contained(build / name)
                if not original.exists():
                    continue
                checksum = digest(original)
                destination = contained(archive / name)
                original.rename(destination)
                if digest(destination) != checksum:
                    raise RuntimeError(f"Archived smoke evidence failed integrity verification: {destination}")
                previous["artifacts"][name] = {"path": evidence_reference(destination),
                                                "sha256": checksum}
            entry.setdefault("smoke_history", []).append(previous)
            entry["smoke"] = "not run"
            save_report(path, report)
        log = build / ("simulator.log" if windows else "stdout.log")
        if any((build / name).exists() for name in ("simulator.log", "stdout.log", "startup-audio.raw")):
            raise RuntimeError("Refusing to overwrite existing smoke evidence")
        audio = build / "startup-audio.raw"
        runtime = build / "runtime"
        runtime.mkdir(exist_ok=True)
        environment = dict(os.environ, SDL_VIDEODRIVER=video_driver, SDL_AUDIODRIVER="disk",
                           SDL_DISKAUDIODELAY="8", SDL_RENDER_DRIVER="software")
        if not windows:
            environment.update(HOME=str(runtime), XDG_CONFIG_HOME=str(runtime / "config"),
                               XDG_CACHE_HOME=str(runtime / "cache"), XDG_DATA_HOME=str(runtime / "data"))
        command = [str(executable), "--nobackground", "--root", str(build / "simdisk"),
                   "--audiodev", str(audio)]
        entry["smoke"] = {"started": True, "headless": video_driver == "dummy", "passed": False,
                          "video_driver": video_driver, "window_hidden": False,
                          "fixture": fixture,
                          "started_utc": datetime.now(timezone.utc).isoformat(),
                          "command": command, "scope": "startup TTS only; no GUI, input, playback or graceful-shutdown test"}
        save_report(path, report)
        process = None
        try:
            with (build / "stdout.log").open("wb") as stream:
                process = subprocess.Popen(command, cwd=build, env=environment, stdout=stream,
                                           stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW if windows else 0)
                entry["smoke"]["pid"] = process.pid
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"Simulator exited during startup: {process.returncode}")
                    if native is not None and video_driver == "windows" and not entry["smoke"]["window_hidden"]:
                        window = native.find_window(process.pid)
                        if window is not None:
                            native.set_hidden(process.pid, window, True)
                            entry["smoke"]["window_hidden"] = True
                    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
                    if re.search(parameter_pattern, text) and audio.exists() and audio.stat().st_size > 8192:
                        if video_driver == "windows" and not entry["smoke"]["window_hidden"]:
                            raise RuntimeError("Startup speech began without a hidden PID-owned window")
                        time.sleep(1)
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("No bounded startup speech/audio evidence within 30 seconds")
                if process.poll() is not None:
                    raise RuntimeError(f"Simulator exited after startup speech: {process.returncode}")
                process.terminate()
                process.wait(timeout=10)
            samples = array.array("h")
            samples.frombytes(audio.read_bytes()[:audio.stat().st_size // 2 * 2])
            nonzero = sum(sample != 0 for sample in samples)
            text = log.read_text(encoding="utf-8", errors="replace")
            if nonzero < 100:
                raise RuntimeError("The audio file contains no meaningful startup PCM")
            if "TTS: synthesis failed" in text or "Cannot initialize" in text or "Unable to open audio" in text:
                raise RuntimeError("The startup log reports a synthesis/audio failure")
            entry["smoke"].update(passed=True, audio_samples=len(samples), nonzero_samples=nonzero,
                                  audio_sha256=digest(audio), log_sha256=digest(log),
                                  speech=re.findall(r"^TTS: (.+)$", text, re.M),
                                  parameters=re.findall(r"^TTS parameters: (.+)$", text, re.M),
                                  shutdown="explicit process termination after startup-only evidence")
            print(f"{entry['target']}: startup TTS passes, {nonzero} nonzero PCM samples", flush=True)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            entry["smoke"]["error"] = str(error)
            print(f"{entry['target']}: {error}", flush=True)
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            if process:
                entry["smoke"]["exit_code"] = process.returncode
                entry["smoke"]["exit_hex"] = f"0x{process.returncode & 0xffffffff:08x}"
            entry["smoke"]["artifacts"] = {
                name: {"path": evidence_reference(build / name),
                       "sha256": digest(build / name), "bytes": (build / name).stat().st_size}
                for name in ("simulator.log", "stdout.log", "startup-audio.raw") if (build / name).exists()}
            save_report(path, report)
    return all(isinstance(entry["smoke"], dict) and entry["smoke"].get("passed") for entry in report["targets"])


def source_hashes():
    return {name: digest(ROOT / name) for name in SOURCE_FILES}


def verify_evidence(record):
    path = resolve_evidence_path(record["path"])
    if digest(path) != record["sha256"]:
        raise RuntimeError(f"Evidence hash mismatch: {path}")
    return path


def ensure_refresh_unused(executable, windows):
    if windows:
        script = "$ErrorActionPreference = 'Stop'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process -Filter \"Name = 'rockboxui.exe'\" | ForEach-Object { if (-not $_.ExecutablePath) { throw 'Cannot inspect simulator executable path' }; $_.ExecutablePath }"
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        running = subprocess.check_output([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded,
        ], text=True, encoding="utf-8")
        native_path = subprocess.check_output(["wslpath", "-w", str(executable)], text=True).strip()
        if not native_path:
            raise RuntimeError("Cannot resolve the Windows executable path for process checks")
        if native_path.casefold() in {line.strip().casefold() for line in running.splitlines()}:
            raise RuntimeError("The diagnostic simulator is running; no files were moved")
        if executable.read_bytes()[:2] != b"MZ":
            raise RuntimeError("The diagnostic artifact is not a Windows executable")
    else:
        for process in Path("/proc").glob("[0-9]*/exe"):
            try:
                if process.resolve(strict=True) == executable:
                    raise RuntimeError("The diagnostic simulator is running; no files were moved")
            except (FileNotFoundError, PermissionError):
                continue


def validate_refresh_entry(path, report, entry, arguments):
    before = entry.get("sources_before")
    after = entry.get("sources_after")
    if not isinstance(before, dict) or not before or not isinstance(after, dict) or before.keys() != after.keys():
        raise RuntimeError("Refresh requires complete before/after source evidence")
    changed = {name for name in before if before[name] != after[name]}
    source_drift = (not entry["compiled"]
                    and entry.get("error") == "Shared sources changed during this diagnostic build"
                    and bool(changed) and set(entry.get("sources_changed_during_build", [])) == changed
                    and not any(entry.get(name) for name in (
                        "abi_refreshed", "prior_executable", "smoke_history"))
                    and entry.get("smoke") == "not run")
    if (entry.get("abi_refresh_error") or not source_drift and (
            not entry["compiled"] or entry.get("error") or changed
            or entry.get("sources_changed_during_build")
            or bool(entry.get("prior_executable")) != bool(entry.get("abi_refreshed")))):
        raise RuntimeError("Refresh rejects failed, partial or ongoing builds; inspect existing evidence")
    if not all(entry.get("integrated_symbols", {}).get(name) for name in REQUIRED_SYMBOLS):
        raise RuntimeError("Refresh requires all integrated speech symbols")
    smoke = entry.get("smoke")
    if smoke != "not run":
        if (not isinstance(smoke, dict) or not smoke.get("passed") or smoke.get("error")
                or "exit_code" not in smoke or not smoke.get("artifacts")):
            raise RuntimeError("Refresh rejects failed or unfinished smoke tests")
        for artifact in smoke["artifacts"].values():
            verify_evidence(artifact)
    for previous in entry.get("smoke_history", []):
        for artifact in previous.get("artifacts", {}).values():
            verify_evidence(artifact)
    for artifact in entry.get("refresh_artifacts", {}).values():
        verify_evidence(artifact)
    build = contained(resolve_evidence_path(entry["directory"]))
    if build.parent != path.parent or build.name != entry["target"] or entry["target"] not in TARGETS:
        raise RuntimeError("Unexpected diagnostic target directory")
    executable = contained(build / ("rockboxui.exe" if report["platform"] == "windows" else "rockboxui"))
    if executable != build / ("rockboxui.exe" if report["platform"] == "windows" else "rockboxui"):
        raise RuntimeError("Diagnostic executable resolves outside its target directory")
    if isinstance(smoke, dict):
        expected = SMOKE_FILES if report["platform"] == "windows" else ("stdout.log", "startup-audio.raw")
        for name in expected:
            if name not in smoke["artifacts"] or verify_evidence(smoke["artifacts"][name]) != build / name:
                raise RuntimeError("Completed smoke lacks the expected target-local evidence")
    verify_evidence({"path": evidence_reference(executable), "sha256": entry["executable_sha256"]})
    if entry.get("prior_executable"):
        previous = entry["prior_executable"]
        verify_evidence({"path": previous["snapshot"] + "/" + executable.name, "sha256": previous["sha256"]})
    if smoke == "not run" and any((build / name).exists() for name in SMOKE_FILES):
        raise RuntimeError("Unrecorded smoke files require investigation before refresh")
    source = None
    if "runtime" in entry:
        runtime = entry["runtime"]
        if (not runtime.get("engine_data_sha256")
                or runtime.get("data_files") != len(runtime["engine_data_sha256"])
                or set(runtime.get("catalogs", {})) != set(CATALOG_FILES)):
            raise RuntimeError("Runtime evidence is incomplete")
        languages = contained(build / "simdisk/.rockbox/langs")
        if (languages != build / "simdisk/.rockbox/langs"
                or {artifact.name for artifact in languages.iterdir()} != set(CATALOG_FILES)):
            raise RuntimeError("Unrecorded or redirected language catalogs require investigation")
        fixture = startup_fixture(build)
        if "fixture" in runtime and fixture != runtime["fixture"]:
            raise RuntimeError("Startup fixture changed since runtime staging")
        for directory, records in (("espeak-data", runtime["engine_data_sha256"]), ("langs", runtime["catalogs"])):
            for name, checksum in records.items():
                artifact = contained(build / "simdisk/.rockbox" / directory / name)
                if (build not in artifact.parents
                        or artifact != build / "simdisk/.rockbox" / directory / name):
                    raise RuntimeError("Runtime evidence is outside its target directory")
                verify_evidence({"path": evidence_reference(artifact), "sha256": checksum})
    else:
        if (build / "simdisk").exists():
            raise RuntimeError("Unrecorded runtime files require investigation before refresh")
        source = arguments.espeak_source.resolve(strict=True)
        revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if revision != report["engine_data_revision"]:
            raise RuntimeError("Engine data revision changed; use the original source checkout for runtime staging")
    ensure_refresh_unused(executable, report["platform"] == "windows")
    return build, executable, source, source_drift


def refresh_abi(arguments):
    if os.name == "nt":
        raise RuntimeError("Run incremental rebuilding under WSL")
    with report_lock(arguments.refresh_report) as path:
        return refresh_locked_report(path, arguments)


def refresh_locked_report(path, arguments):
    original = path.read_bytes()
    report = json.loads(original)
    if (path.name != "report.json" or path.parent.parent != _project_materials_root(ROOT) / "tts-target-tests"
            or report.get("platform") not in ("windows", "linux")):
        raise RuntimeError("Unexpected target report path or platform")
    if (report.get("build_state", "completed") != "completed"
            or report.get("refresh_round", {}).get("state", "passed") != "passed"):
        raise RuntimeError("Refresh rejects ongoing or failed rounds; inspect preserved evidence")
    targets = [entry["target"] for entry in report["targets"]]
    if not targets or len(targets) != len(set(targets)):
        raise RuntimeError("Refresh requires a nonempty, unique target group")
    for history in report.get("refresh_history", []):
        verify_evidence(history["report"])
        manifest = json.loads(verify_evidence(history["manifest"]).read_text(encoding="utf-8"))
        for artifact in manifest["moves"]:
            verify_evidence({"path": artifact["archived_path"], "sha256": artifact["sha256"]})
    header = (ROOT / "apps/plugin.h").read_text(encoding="utf-8")
    if not re.search(r"#define\s+PLUGIN_API_VERSION\s+0xe006\b", header):
        raise RuntimeError("The requested integrated-eSpeak plugin ABI guard is not present")
    baseline = source_hashes()
    plans = [validate_refresh_entry(path, report, entry, arguments) for entry in report["targets"]]
    fixtures = {entry["target"]: startup_fixture(build)
                for entry, (build, executable, source, source_drift) in zip(report["targets"], plans)
                if "runtime" in entry}
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = contained(path.parent / "refresh-history" / timestamp)
    if archive != path.parent / "refresh-history" / timestamp or archive.exists():
        raise RuntimeError("Refresh history already exists; refusing to overwrite it")
    moves = []
    for entry, (build, executable, source, source_drift) in zip(report["targets"], plans):
        snapshot = confined_path(_project_materials_root(ROOT, "Snapshots") / ("tts-target-before-abi-validation-" + entry["target"] + "-" + timestamp),
                                 _project_materials_root(ROOT, "Snapshots"))
        if snapshot.exists():
            raise RuntimeError("Snapshot is outside the project or already exists")
        logs = contained(build / "refresh-rounds" / timestamp)
        if logs != build / "refresh-rounds" / timestamp or logs.exists():
            raise RuntimeError("Refresh log directory is unsafe or already exists")
        names = SMOKE_FILES + CATALOG_LOGS + ("build-abi-refresh.log", "pe-headers-abi-refresh.txt", "plugin-loader-abi.txt")
        if any(contained(build / name) != build / name for name in names if (build / name).exists()):
            raise RuntimeError("Diagnostic log paths must not redirect to other files")
        artifacts = [(executable, snapshot / executable.name)] + [
            (contained(build / name), contained(archive / entry["target"] / name))
            for name in names if (build / name).exists()]
        if "runtime" in entry:
            artifacts.extend((contained(build / "simdisk/.rockbox/langs" / name),
                              contained(archive / entry["target"] / "simdisk/.rockbox/langs" / name))
                             for name in CATALOG_FILES)
        for old_path, new_path in artifacts:
            if build not in old_path.parents:
                raise RuntimeError("Diagnostic artifact resolves outside its target directory")
            moves.append({"target": entry["target"], "path": evidence_reference(old_path),
                          "archived_path": evidence_reference(new_path), "sha256": digest(old_path)})
    windows = report["platform"] == "windows"
    environment = dict(os.environ, VERSION="tts-cross-target-diagnostic", OMP_NUM_THREADS=str(arguments.jobs))
    if windows:
        environment["PATH"] = str(arguments.sdl_sdk.resolve() / "bin") + os.pathsep + environment["PATH"]
        environment["CXX"] = "x86_64-w64-mingw32-g++"
    report["refresh_round"] = {"id": timestamp, "state": "in_progress", "sources_before": baseline,
                               "started_utc": datetime.now(timezone.utc).isoformat()}
    save_report(path, report)
    active_entry = None
    try:
        archive.mkdir(parents=True)
        print(f"Required immutable report history: {path} -> {archive / 'report.json'}", flush=True)
        with (archive / "report.json").open("xb") as stream:
            stream.write(original)
        if digest(archive / "report.json") != hashlib.sha256(original).hexdigest():
            raise RuntimeError("Archived report hash mismatch")
        with (archive / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump({"moves": moves}, stream, indent=2)
        report.setdefault("refresh_history", []).append({"round": timestamp, **{
            name: {"path": evidence_reference(archive / (name + ".json")),
                   "sha256": digest(archive / (name + ".json"))} for name in ("report", "manifest")}})
        save_report(path, report)
        for entry, (build, executable, source, source_drift) in zip(report["targets"], plans):
            active_entry = entry
            if source_hashes() != baseline:
                raise RuntimeError("Shared sources changed between refresh targets")
            ensure_refresh_unused(executable, windows)
            previous_smoke = deepcopy(entry["smoke"])
            for artifact in (item for item in moves if item["target"] == entry["target"]):
                old_path = verify_evidence(artifact)
                new_path = resolve_evidence_path(artifact["archived_path"])
                new_path.parent.mkdir(parents=True, exist_ok=True)
                if new_path.exists():
                    raise RuntimeError("Archive destination appeared during refresh")
                print(f"Preserving diagnostic artifact: {old_path} -> {new_path}", flush=True)
                shutil.move(str(old_path), str(new_path))
                verify_evidence({"path": artifact["archived_path"], "sha256": artifact["sha256"]})
                if old_path == executable:
                    entry["prior_executable"] = {"snapshot": evidence_reference(new_path.parent),
                                                 "sha256": artifact["sha256"]}
                elif isinstance(previous_smoke, dict):
                    for record in previous_smoke["artifacts"].values():
                        if resolve_evidence_path(record["path"]) == old_path:
                            record["path"] = artifact["archived_path"]
            if isinstance(previous_smoke, dict):
                entry.setdefault("smoke_history", []).append(previous_smoke)
            if source_drift:
                entry["prior_build_failure"] = {name: deepcopy(entry[name]) for name in (
                    "error", "sources_changed_during_build", "sources_before", "sources_after")}
            entry.update(compiled=False, abi_refreshed=False, smoke="not run", sources_before=dict(baseline))
            for name in ("plugin_api_version", "plugin_abi_comparison", "abi_refresh_seconds", "refresh_artifacts"):
                entry.pop(name, None)
            logs = contained(build / "refresh-rounds" / timestamp)
            logs.mkdir(parents=True)
            entry["refresh_log_directory"] = evidence_reference(logs)
            save_report(path, report)
            entry["abi_refresh_seconds"] = run(["make", f"-j{arguments.jobs}", "bin"], build,
                                                logs / "build.log", environment, arguments.timeout)
            prefix = "x86_64-w64-mingw32-" if windows else ""
            symbols = subprocess.check_output([prefix + "nm", str(executable)], text=True)
            (logs / "linked-symbols.txt").write_text(symbols, encoding="utf-8")
            for name in REQUIRED_SYMBOLS + SONIC_SYMBOLS:
                if not re.search(r"\b" + name + r"$", symbols, re.M):
                    raise RuntimeError(f"Refreshed executable is missing {name}")
            entry["sonic_symbols"] = {name: True for name in SONIC_SYMBOLS}
            if windows:
                headers = subprocess.check_output([prefix + "objdump", "-p", str(executable)], text=True)
                (logs / "pe-headers.txt").write_text(headers, encoding="utf-8")
                entry["imports"] = re.findall(r"DLL Name: (\S+)", headers)
                if not re.search(r"Subsystem\s+00000002", headers):
                    raise RuntimeError("Refreshed executable is not Windows GUI subsystem")
                if any("espeak" in name.lower() for name in entry["imports"]):
                    raise RuntimeError("Unexpected external eSpeak DLL dependency")
                loader = subprocess.check_output([
                    prefix + "objdump", "-d", "--disassemble=plugin_load", str(executable),
                ], text=True)
                (logs / "plugin-loader-abi.txt").write_text(loader, encoding="utf-8")
                entry["plugin_abi_comparison"] = [
                    line.strip() for line in loader.splitlines() if "cmp" in line and "$0xe006" in line]
                if not entry["plugin_abi_comparison"]:
                    raise RuntimeError("The linked plugin loader does not compare the requested eSpeak ABI")
            if source_hashes() != baseline:
                raise RuntimeError("Shared sources changed during ABI refresh")
            if "runtime" not in entry:
                entry["runtime"] = stage_runtime(build, entry["target"], source, environment, logs)
            else:
                catalogs = stage_catalogs(build, entry["target"], environment, logs)
                if catalogs["target_id"] != entry["runtime"]["target_id"]:
                    raise RuntimeError("Regenerated catalogs changed their target ID")
                fixture = startup_fixture(build)
                if fixture != fixtures[entry["target"]]:
                    raise RuntimeError("Startup fixture changed during refresh")
                entry["runtime"].update(catalogs, fixture=fixture)
            entry["sources_after"] = source_hashes()
            if entry["sources_after"] != baseline:
                raise RuntimeError("Shared sources changed during ABI refresh or runtime staging")
            entry["executable_sha256"] = digest(executable)
            entry["executable_bytes"] = executable.stat().st_size
            entry["compiled"] = entry["abi_refreshed"] = True
            entry["plugin_api_version"] = "0xe006"
            entry["refresh_artifacts"] = {
                name: {"path": evidence_reference(logs / name), "sha256": digest(logs / name)}
                for name in ("build.log", "linked-symbols.txt", "pe-headers.txt", "plugin-loader-abi.txt") + CATALOG_LOGS
                if (logs / name).exists()}
            if source_drift:
                entry.pop("error")
                entry["sources_changed_during_build"] = []
            save_report(path, report)
        report["refresh_round"]["sources_after"] = source_hashes()
        if report["refresh_round"]["sources_after"] != baseline:
            raise RuntimeError("Shared sources changed before refresh completion")
        report["refresh_round"].update(state="passed", finished_utc=datetime.now(timezone.utc).isoformat())
        save_report(path, report)
        return True
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        if active_entry is not None:
            active_entry.update(compiled=False, abi_refreshed=False, abi_refresh_error=str(error))
        report["refresh_round"].update(state="failed", error=str(error),
                                       finished_utc=datetime.now(timezone.utc).isoformat())
        save_report(path, report)
        print(f"Refresh stopped; inspect preserved evidence: {error}", flush=True)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Build selected integrated-eSpeak SDL simulator cores, not device firmware.")
    parser.add_argument("--platform", choices=("windows", "linux"), default="windows")
    parser.add_argument("--targets", nargs="+", choices=TARGETS,
                        help="Configure names to build (default: xduoox3 shanlingq1); report modes use their saved targets")
    parser.add_argument("--build-only", action="store_true",
                        help="Check the linked core without copying engine data or staging a smoke runtime")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--espeak-source", type=Path, default=ROOT.parent / "espeak-1.44.05-source")
    parser.add_argument("--sdl-sdk", type=Path, default=_project_materials_root(ROOT) / "toolchains/SDL2-2.32.10/x86_64-w64-mingw32")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list-targets", action="store_true",
                      help="Print supported configure names and exit without building or copying files")
    mode.add_argument("--smoke-report", type=Path)
    mode.add_argument("--refresh-report", type=Path)
    parser.add_argument("--video-driver", choices=("dummy", "windows"))
    parser.add_argument("--repeat-smoke", action="store_true")
    arguments = parser.parse_args()
    if arguments.targets is not None and len(set(arguments.targets)) != len(arguments.targets):
        parser.error("Select each target only once")
    if (arguments.list_targets or arguments.smoke_report or arguments.refresh_report) and (
            arguments.targets is not None or arguments.build_only):
        parser.error("--targets and --build-only apply only to new builds, not list/report modes")
    if not 1 <= arguments.jobs <= 16 or not 30 <= arguments.timeout <= 1800:
        parser.error("Use 1..16 jobs and a per-target timeout of 30..1800 seconds")
    if (arguments.repeat_smoke or arguments.video_driver is not None) and not arguments.smoke_report:
        parser.error("--repeat-smoke and --video-driver require --smoke-report")
    if arguments.list_targets:
        print("\n".join(TARGETS))
        return 0
    if arguments.targets is None:
        arguments.targets = list(DEFAULT_TARGETS)
    if arguments.refresh_report:
        successful = refresh_abi(arguments)
    elif arguments.smoke_report:
        successful = smoke_report(arguments.smoke_report, arguments.video_driver, arguments.repeat_smoke)
    else:
        successful = build_targets(arguments)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
