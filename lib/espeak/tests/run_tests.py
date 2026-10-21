import argparse
from datetime import datetime, timezone
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
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                env=environment, check=False)
    if result.returncode:
        print(log.read_text(encoding="utf-8", errors="replace"))
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_parent", type=Path)
    parser.add_argument("--sanitize", choices=("none", "address", "undefined"), default="none")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--without-sonic", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    data_parent = arguments.data_parent.resolve(strict=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    materials = project_materials_root(root)
    workspace = confined_path(arguments.workspace or materials / "espeak-tests" / stamp,
                              materials)
    check_dependency(root / "lib/espeak")
    workspace.mkdir(parents=True, exist_ok=True)
    build = workspace / {"none": "normal", "address": "asan", "undefined": "ubsan"}[arguments.sanitize]
    if arguments.without_sonic:
        build = build.with_name(build.name + "-without-sonic")
    build.mkdir(exist_ok=False)
    flags = ["-O2", "-g"]
    sanitizer_flags = []
    if arguments.sanitize != "none":
        flags = ["-O1", "-g"]
        sanitizer_flags = ["-fsanitize=" + arguments.sanitize, "-fno-omit-frame-pointer"]
        flags += sanitizer_flags
    run(["make", "-B", "-s", "-f", str(root / "lib/espeak/espeak.make"),
         "ROOTDIR=" + str(root), "BUILDDIR=" + str(build), "APP_TYPE=sdl-sim", "ESPEAK=1",
         "CXX=g++", "AR=ar", "ESPEAK_CXXFLAGS=" + " ".join(flags),
         "ESPEAK_SONIC=" + str(int(not arguments.without_sonic)), "-j4", "espeak"],
        build / "build.log")
    run(["gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *sanitizer_flags,
         "-I" + str(root / "lib/espeak"), "-c", str(root / "lib/espeak/tests/test_backend.c"),
         "-o", str(build / "test_backend.o")], build / "build-test.log")
    executable = build / "test_backend"
    run(["g++", *sanitizer_flags, str(build / "test_backend.o"),
         str(build / "lib/libespeak.a"), "-lm", "-o", str(executable)], build / "link-test.log")
    environment = os.environ.copy()
    environment["ASAN_OPTIONS"] = "detect_leaks=1:halt_on_error=1"
    environment["UBSAN_OPTIONS"] = "print_stacktrace=1:halt_on_error=1"
    catalog = build / "test_catalog"
    run(["gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *sanitizer_flags,
         "-I" + str(root / "lib/espeak"), "-c", str(root / "lib/espeak/tests/test_catalog.c"),
         "-o", str(build / "test_catalog.o")], build / "build-catalog.log")
    run(["g++", *sanitizer_flags, str(build / "test_catalog.o"),
         str(build / "lib/libespeak.a"), "-lm", "-o", str(catalog)], build / "link-catalog.log")
    catalog_data = prepare_catalog_fixture(data_parent, build / "catalog")
    run([str(catalog), str(catalog_data)], build / "catalog.log", environment)
    print((build / "catalog.log").read_text(encoding="utf-8").strip())
    run_sonic_checks(run, str(root / "lib/espeak"), str(build), build, data_parent,
                     flags=sanitizer_flags, enabled=not arguments.without_sonic,
                     environment=environment)
    check_pcm(run, root, executable, data_parent, build, environment)
    run([str(executable), str(data_parent), str(build)], build / "result.log", environment)
    print((build / "result.log").read_text(encoding="utf-8").splitlines()[-1])
    run([str(executable), str(data_parent), str(build), "buffers"],
        build / "buffers.log", environment)
    print((build / "buffers.log").read_text(encoding="utf-8").strip())
    for mode in ("punctuation-native", "punctuation"):
        log = build / (mode + ".log")
        run([str(executable), str(data_parent), str(build), mode], log, environment)
        print(log.read_text(encoding="utf-8").splitlines()[-1])
    for name, invalid_parent in (("missing-root", workspace / "nonexistent"),
                                 ("wrong-level", data_parent / "espeak-data")):
        run([str(executable), str(invalid_parent), str(build), "reject"],
            build / (name + ".log"), environment)
    fixture = build / "invalid-data"
    fixture_data = fixture / "espeak-data"
    fixture_files = ("phondata", "phonindex", "phontab", "intonations", "pl_dict", "voices/pl")
    if fixture.exists():
        existing_files = {item.relative_to(fixture_data).as_posix()
                          for item in fixture_data.rglob("*") if item.is_file()}
        if fixture.is_symlink() or fixture_data.is_symlink() or existing_files != set(fixture_files) or any(
                item.is_symlink() for item in fixture_data.rglob("*")):
            raise SystemExit("Refusing to overwrite an unrecognized fault-injection fixture: " + str(fixture))
    (fixture_data / "voices").mkdir(parents=True, exist_ok=True)
    for filename in fixture_files:
        shutil.copyfile(data_parent / "espeak-data" / filename, fixture_data / filename)
    with (fixture_data / "phondata").open("r+b") as stream:
        stream.write(b"\x00\x00\x00\x00")
    run([str(executable), str(fixture), str(build), "reject"], build / "wrong-version.log", environment)
    shutil.copyfile(data_parent / "espeak-data/phondata", fixture_data / "phondata")
    (fixture_data / "phontab").write_bytes(b"\x01\x00\x00\x00")
    run([str(executable), str(fixture), str(build), "reject"], build / "truncated-table.log", environment)
    symbols = subprocess.check_output(["nm", "-u", str(build / "lib/libespeak.a")], text=True)
    (build / "undefined-symbols.txt").write_text(symbols, encoding="utf-8")
    forbidden = ("pthread_", "Pa_", "SDL_", "dlopen", "fork", "execvp", "execlp", "waitpid", "mkstemp")
    for line in symbols.splitlines():
        if any(line.split()[-1].startswith(prefix) for prefix in forbidden if line.split()):
            raise SystemExit("Unexpected host backend dependency: " + line)
    print("PASS: invalid roots, version, truncated table, C ABI and no audio/thread backend symbols")
    print("Results and deliberate fault-injection copies retained in " + str(build))


if __name__ == "__main__":
    main()
