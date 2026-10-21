import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.dont_write_bytecode = True
from sonic_checks import check_dependency, check_pcm, run_sonic_checks
from catalog_checks import prepare_catalog_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from project_materials import project_materials_root, confined_path


def run(command, log, environment=None):
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run([str(argument) for argument in command], stdout=output,
                                stderr=subprocess.STDOUT, env=environment, check=False)
    if result.returncode:
        raise SystemExit(f"Command failed ({result.returncode}); see {log}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_parent", type=Path)
    parser.add_argument("--distribution", default="Ubuntu-24.04")
    parser.add_argument("--without-sonic", action="store_true")
    parser.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Run this harness with native Windows Python and the WSL MinGW toolchain.")
    sys.stdout.reconfigure(errors="backslashreplace")
    root = Path(__file__).resolve().parents[3]
    check_dependency(root / "lib/espeak")
    data_parent = arguments.data_parent.resolve(strict=True)
    materials = project_materials_root(root)
    workspace = confined_path(arguments.workspace or materials / "espeak-windows-tests",
                              materials)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    build = workspace / stamp
    build.mkdir(parents=True)
    wsl = ["wsl.exe", "-d", arguments.distribution, "-u", "root", "--exec"]

    def linux_path(path):
        return subprocess.check_output([*wsl, "wslpath", "-u", str(path)],
                                       text=True, encoding="utf-8").strip()

    source = linux_path(root / "lib" / "espeak")
    target = linux_path(build)
    prefix = "x86_64-w64-mingw32-"
    environment = os.environ.copy()
    environment.pop("CXX", None)
    run([*wsl, prefix + "g++", "-v"], build / "compiler.log")
    run([*wsl, "env", "-u", "CXX", "make", "-f", source + "/espeak.make",
         "ROOTDIR=" + linux_path(root), "BUILDDIR=" + target, "APP_TYPE=sdl-sim",
         "ESPEAK=1", "ESPEAK_SONIC=" + str(int(not arguments.without_sonic)),
         "CROSS_COMPILE=" + prefix, "AR=" + prefix + "ar", "-j4", "espeak"],
        build / "build.log", environment)
    run([*wsl, prefix + "gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror",
         "-I" + source, "-c", source + "/tests/test_backend.c", "-o", target + "/test_backend.o"],
        build / "build-test.log")
    run([*wsl, prefix + "g++", "-static", "-municode", target + "/test_backend.o",
         target + "/lib/libespeak.a", "-lm", "-o", target + "/test_backend.exe"],
        build / "link-test.log")
    run([*wsl, prefix + "g++", "-std=c++11", "-O2", "-g", "-fno-exceptions", "-fno-rtti",
         "-Wall", "-Wextra", "-Werror", "-static", "-municode", "-I" + source,
         source + "/tests/test_windows_platform.cpp", target + "/lib/libespeak.a",
         "-lm", "-o", target + "/test_windows_platform.exe"], build / "build-platform.log")
    executable = build / "test_backend.exe"
    run([*wsl, prefix + "gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror",
         "-I" + source, "-c", source + "/tests/test_catalog.c", "-o", target + "/test_catalog.o"],
        build / "build-catalog.log")
    run([*wsl, prefix + "g++", "-static", target + "/test_catalog.o",
         target + "/lib/libespeak.a", "-lm", "-o", target + "/test_catalog.exe"],
        build / "link-catalog.log")
    catalog_data = prepare_catalog_fixture(data_parent, build / "catalog")
    run([build / "test_catalog.exe", catalog_data], build / "catalog.log")
    run_sonic_checks(run, source, target, build, data_parent, prefix=wsl,
                     compiler_prefix=prefix, enabled=not arguments.without_sonic, windows=True)
    check_pcm(run, root, executable, data_parent, build)
    run([executable, data_parent, build], build / "result.log")
    run([executable, data_parent, build, "buffers"], build / "buffers.log")
    for mode in ("punctuation-native", "punctuation"):
        run([executable, data_parent, build, mode], build / (mode + ".log"))
    run([build / "test_windows_platform.exe", data_parent, build], build / "platform.log")
    unicode_parent = build / "Zażółć gęślą 中文"
    unicode_data = unicode_parent / "espeak-data"
    source_data = data_parent / "espeak-data"
    print("Retaining a verified full data copy for Unicode-path regression: " + str(unicode_data))
    shutil.copytree(source_data, unicode_data)
    hashes = {}
    for original in sorted(source_data.rglob("*")):
        if original.is_file():
            relative = original.relative_to(source_data)
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            if hashlib.sha256((unicode_data / relative).read_bytes()).hexdigest() != digest:
                raise SystemExit("Data copy differs: " + str(relative))
            hashes[relative.as_posix()] = digest
    (build / "unicode-data.sha256.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    if len(str(unicode_data).encode("utf-8")) >= 150:
        raise SystemExit("Unicode fixture exceeds the backend's documented 150-byte buffer.")
    run([executable, unicode_parent, build], build / "unicode-result.log")
    run([executable, unicode_parent, build, "buffers"], build / "unicode-buffers.log")
    run([executable, unicode_parent, build, "punctuation"], build / "unicode-punctuation.log")
    run([build / "test_windows_platform.exe", unicode_parent, build], build / "unicode-platform.log")
    for name, invalid in (("missing-root", build / "nonexistent"), ("wrong-level", source_data)):
        run([executable, invalid, build, "reject"], build / (name + ".log"))
    fixture = build / "invalid-data"
    fixture_data = fixture / "espeak-data"
    (fixture_data / "voices").mkdir(parents=True)
    for filename in ("phondata", "phonindex", "phontab", "intonations", "pl_dict", "voices/pl"):
        shutil.copyfile(source_data / filename, fixture_data / filename)
    with (fixture_data / "phondata").open("r+b") as output:
        output.write(b"\x00\x00\x00\x00")
    run([executable, fixture, build, "reject"], build / "wrong-version.log")
    shutil.copyfile(source_data / "phondata", fixture_data / "phondata")
    (fixture_data / "phontab").write_bytes(b"\x01\x00\x00\x00")
    run([executable, fixture, build, "reject"], build / "truncated-table.log")
    run([*wsl, prefix + "nm", "-u", target + "/lib/libespeak.a"], build / "undefined-symbols.txt")
    forbidden = ("pthread_", "Pa_", "SDL_", "fork", "execvp", "execlp", "waitpid", "mkstemp",
                 "CoCreateInstance", "CreateThread", "_beginthread")
    for line in (build / "undefined-symbols.txt").read_text(encoding="utf-8").splitlines():
        symbol = line.split()[-1] if line.split() else ""
        if any(symbol.removeprefix("__imp_").startswith(prefix) for prefix in forbidden):
            raise SystemExit("Unexpected backend dependency: " + line)
    run([*wsl, prefix + "objdump", "-p", target + "/test_backend.exe"], build / "pe-imports.txt")
    imports = [line.split(":", 1)[1].strip() for line in
               (build / "pe-imports.txt").read_text(encoding="utf-8").splitlines() if "DLL Name:" in line]
    if any(name.lower() not in {"kernel32.dll", "msvcrt.dll", "advapi32.dll"} for name in imports):
        raise SystemExit("Unexpected diagnostic executable dependency: " + repr(imports))
    summary = {"status": "PASS", "languages": 54, "variants_including_default": 105,
               "unicode_fixture_files": len(hashes), "diagnostic_dll_imports": imports,
               "source_hashes": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted((root / "lib" / "espeak").rglob("*")) if path.is_file()}}
    (build / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("PASS: Windows corpus, Unicode paths, locale isolation, negative cases and dependencies")
    print("Diagnostic binaries, logs and intentional fixtures retained in " + str(build))


if __name__ == "__main__":
    main()
