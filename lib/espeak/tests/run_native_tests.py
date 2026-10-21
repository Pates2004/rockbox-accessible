import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from catalog_checks import prepare_catalog_fixture
from sonic_checks import check_dependency, run_sonic_checks


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from project_materials import project_materials_root as _project_materials_root, confined_path



ROOT = Path(__file__).resolve().parents[3]
ESPEAK = ROOT / "lib/espeak"


def execute(command, output, environment=None):
    with output.open("w", encoding="utf-8") as stream:
        result = subprocess.run([str(value) for value in command], stdout=stream,
                                stderr=subprocess.STDOUT, env=environment, timeout=300)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {output}")


def integration_sources():
    sources = sorted(path for path in ESPEAK.rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts)
    sources.extend((ROOT / "tools/tests/test_espeak_native_runtime.py",
                    ROOT / "lib/tlsf/src/tlsf.c", ROOT / "lib/tlsf/src/tlsf.h"))
    return sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_parent", type=Path)
    parser.add_argument("--sanitize", choices=("none", "undefined", "address"), default="none")
    parser.add_argument("--runtime", choices=("native", "hosted"), default="native")
    parser.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    local_patches = check_dependency(ESPEAK, arguments.data_parent.resolve())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    materials = _project_materials_root(ROOT)
    output = confined_path(arguments.workspace or materials / "espeak-native-integration" / stamp,
                           materials)
    output.mkdir(parents=True)
    specification = importlib.util.spec_from_file_location(
        "native_runtime_tests", ROOT / "tools/tests/test_espeak_native_runtime.py")
    runtime = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(runtime)
    flags = []
    if arguments.sanitize != "none":
        flags = ["-fsanitize=" + arguments.sanitize, "-fno-omit-frame-pointer",
                 "-fno-sanitize-recover=all"]
        if arguments.sanitize == "address":
            flags += ["-fno-pie", "-no-pie"]
    sources = integration_sources()
    fingerprints = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sources}
    objects = runtime.build_runtime(output / "runtime", flags, hosted=arguments.runtime == "hosted")
    names = ("speak_lib", "compiledict", "dictionary", "intonation", "readclause",
             "setlengths", "numbers", "synth_mbrola", "synthdata", "synthesize",
             "translate", "tr_languages", "voices", "wavegen", "phonemelist", "klatt")
    engine_sources = [ESPEAK / "rb_espeak.cpp"] + [ESPEAK / "engine" / (name + ".cpp") for name in names]
    for source in engine_sources + [ESPEAK / "sonic/sonic.c"]:
        destination = output / (source.stem + ".o")
        compiler = "gcc" if source.suffix == ".c" else "g++"
        language_flags = ["-std=c11"] if compiler == "gcc" else [
            "-std=c++11", "-nostdinc++", "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics"]
        execute([compiler, "-O2", "-g", "-ffunction-sections", "-fdata-sections",
                 "-DRB_ESPEAK_NATIVE=1", "-DRB_ESPEAK_HAVE_SONIC=1",
                 "-I" + str(ESPEAK / "native/include"), "-I" + str(ESPEAK),
                 *language_flags, *flags, "-c", source, "-o", destination],
                output / (source.stem + "-compile.log"))
        objects.append(destination)
    probe = output / "probe.o"
    execute(["gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *flags,
             "-DRB_ESPEAK_NATIVE_TEST_STATS=1", "-I" + str(ESPEAK),
             "-c", ESPEAK / "tests/test_native_backend.c", "-o", probe], output / "probe-compile.log")
    executable = output / "native-engine-test"
    execute(["g++", *flags, probe, *objects, "-Wl,--gc-sections", "-lm", "-o", executable], output / "link.log")
    environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                       UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
    execute([executable, arguments.data_parent.resolve()], output / "result.log", environment)
    log = (output / "result.log").read_text(encoding="utf-8")
    if "PASS: native services" not in log or len([line for line in log.splitlines() if line.startswith("PCM ")]) != 40:
        raise RuntimeError("Incomplete native adapter integration result")
    ownership_probe = output / "ownership.o"
    execute(["gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *flags,
             "-I" + str(ESPEAK), "-c", ESPEAK / "tests/test_native_ownership.c",
             "-o", ownership_probe], output / "ownership-compile.log")
    ownership_executable = output / "ownership-test"
    execute(["g++", *flags, ownership_probe, *objects, "-Wl,--gc-sections",
             "-Wl,--wrap=rb_espeak_malloc", "-Wl,--wrap=_Z13DoVoiceChangeP7voice_t",
             "-Wl,--wrap=rb_espeak_realloc",
             "-lm", "-o", ownership_executable], output / "ownership-link.log")
    execute([ownership_executable, arguments.data_parent.resolve()],
            output / "ownership-result.log", environment)
    host = output / "host-reference"
    host.mkdir()
    execute(["make", "-s", "-f", ESPEAK / "espeak.make", "ROOTDIR=" + str(ROOT),
             "BUILDDIR=" + str(host), "APP_TYPE=sdl-sim", "ESPEAK=1", "CXX=g++",
             "CC=gcc", "AR=ar", "ESPEAK_CXXFLAGS=-O2 -g " + " ".join(flags),
             "-j4", "espeak"], output / "host-build.log")
    print("Complete sanitized host library:", host / "lib/libespeak.a", flush=True)
    minus_probe = host / "minus.o"
    execute(["gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *flags,
             "-I" + str(ESPEAK), "-c", ESPEAK / "tests/test_polish_minus.c",
             "-o", minus_probe], output / "minus-compile.log")
    minus_executable = host / "minus-test"
    execute(["g++", *flags, minus_probe, host / "lib/libespeak.a", "-lm", "-o", minus_executable],
            output / "minus-link.log")
    execute([minus_executable, arguments.data_parent.resolve(), output / "minus.trace"],
            output / "minus-result.log", environment)
    minus_log = (output / "minus-result.log").read_text(encoding="utf-8")
    minus_rows = [line for line in minus_log.splitlines() if "\t" in line]
    if len(minus_rows) != 9 or "PASS: Polish minus" not in minus_log:
        raise RuntimeError("Incomplete hosted Polish minus regression")
    dictionary_probe = host / "dictionary-source.o"
    execute(["g++", "-std=c++11", "-g", "-Wall", "-Wextra", "-Werror", *flags,
             "-DESPEAK_DICTIONARY_WINDOWS_CASE_COMPAT",
             "-I" + str(ESPEAK), "-c", ESPEAK / "tests/test_dictionary_source.cpp",
             "-o", dictionary_probe], output / "dictionary-compile.log")
    dictionary_executable = host / "dictionary-source-test"
    execute(["g++", *flags, dictionary_probe, host / "lib/libespeak.a", "-Wl,--wrap=iswupper", "-lm", "-o",
             dictionary_executable], output / "dictionary-link.log")
    dictionary_output = output / "compiled-dictionary"
    dictionary_output.mkdir()
    execute([sys.executable, ESPEAK / "tests/test_dictionary_ownership.py", dictionary_executable,
             arguments.data_parent.resolve(), dictionary_output, "--sanitize", arguments.sanitize],
            output / "dictionary-result.log", environment)
    compiled_dictionary = (dictionary_output / "pl_dict").read_bytes()
    supplied_dictionary = (arguments.data_parent / "espeak-data/pl_dict").read_bytes()
    if compiled_dictionary != supplied_dictionary:
        raise RuntimeError("Source-compiled Polish dictionary differs from supplied pl_dict")
    dictionary_hash = hashlib.sha256(compiled_dictionary).hexdigest()
    print("PASS: 9 hosted Polish minus cases; source-compiled pl_dict SHA256", dictionary_hash, flush=True)
    host_probe = host / "probe.o"
    execute(["gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *flags,
             "-I" + str(ESPEAK), "-c", ESPEAK / "tests/test_native_backend.c",
             "-o", host_probe], output / "host-probe-compile.log")
    host_executable = host / "host-engine-test"
    execute(["g++", *flags, host_probe, host / "lib/libespeak.a", "-lm", "-o", host_executable],
            output / "host-link.log")
    execute([host_executable, arguments.data_parent.resolve()], output / "host-result.log", environment)
    reference = (output / "host-result.log").read_text(encoding="utf-8")
    run_sonic_checks(execute, str(ESPEAK), str(host), host, arguments.data_parent.resolve(),
                     flags=flags, enabled=True, environment=environment)
    catalog_probe = output / "catalog.o"
    execute(["gcc", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror", *flags,
             "-DRB_ESPEAK_NATIVE_TEST_STATS=1", "-I" + str(ESPEAK), "-c",
             ESPEAK / "tests/test_catalog.c", "-o", catalog_probe], output / "catalog-compile.log")
    catalog_executable = output / "catalog-test"
    execute(["g++", *flags, catalog_probe, *objects, "-Wl,--gc-sections", "-lm", "-o", catalog_executable],
            output / "catalog-link.log")
    catalog_data = prepare_catalog_fixture(arguments.data_parent.resolve(), output / "catalog")
    execute([catalog_executable, catalog_data], output / "catalog-result.log", environment)
    actual_pcm = [line for line in log.splitlines() if line.startswith("PCM ")]
    expected_pcm = [line for line in reference.splitlines() if line.startswith("PCM ")]
    if actual_pcm != expected_pcm:
        raise RuntimeError("Native adapter changes tested PL/EN PCM relative to the host backend")
    if any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
           for name, digest in fingerprints.items()):
        raise RuntimeError("Native integration sources changed during validation")
    report = {"passed": True, "sanitize": arguments.sanitize, "runtime": arguments.runtime,
              "source_sha256": fingerprints,
              "matching_host_pcm_cases": len(actual_pcm),
              "ownership_failure_regressions": 6, "ownership_cancellation_cycles": 96,
              "polish_minus_cases": 9, "source_compiled_pl_dict_sha256": dictionary_hash,
              "dictionary_compiler_ownership_regression": True,
              "dictionary_compiler_leak_check": arguments.sanitize == "address",
              "dictionary_test_windows_case_compatibility": True,
              "local_memory_safety_patches": local_patches,
              "dynamic_catalog_voices": 201, "catalog_lifecycles": 12,
              "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "scope": "Native bounded heap/Unicode/file adapter on host; not ARM or player execution"}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(log.splitlines()[-2:])
    print("Native engine integration evidence:", output)


if __name__ == "__main__":
    main()
