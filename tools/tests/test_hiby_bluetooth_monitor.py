"""Bounded native monitor tests using a compiled private fake, never a host bus."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/target/hosted/hiby/bluetooth-monitor-hiby.c"
HEADER = SOURCE.with_suffix(".h")
FIXTURES = Path(__file__).with_name("fixtures")
SCENARIOS = (
    "parser", "inactive", "wake", "wake-eintr", "wake-race", "init-failure",
    "spawn-failures", "clock-failure", "reap-retention", "blocked-signal",
    "closed-stdio", "descendant", "cycles", "event", "read-eintr", "split",
    "coalesce", "wake-priority", "payload", "name-acquired", "zero-idle",
    "stderr", "poll-eintr", "read-failure", "ignoreterm", "exit", "closeoutput",
    "flood", "wake-eagain", "external-reap", "reap-eintr", "parent-exit",
    "auto-reap-refused", "eventflood", "inherited-high", "forged-name",
    "profile-recovery", "no-subscription", "relocate-failure",
)
VARIANTS = {
    "normal": [],
    "asan": ["-fsanitize=address", "-fno-omit-frame-pointer"],
    "ubsan": ["-fsanitize=undefined", "-fno-sanitize-recover=all"],
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def evidence_directory(prefix):
    workspace = project_materials_root(ROOT)
    destination = confined_path(workspace / "r1-bluetooth-completion-20261020" /
                               "monitor-implementation", workspace)
    directory = confined_path(destination / (prefix + uuid.uuid4().hex[:12]), destination)
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def input_hashes():
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (SOURCE, HEADER, Path(__file__),
                         FIXTURES / "hiby_bluetooth_monitor_fake.c",
                         FIXTURES / "hiby_bluetooth_monitor_fixture.c",
                         FIXTURES / "hiby_bluetooth_monitor_parser_fixture.c")}


class HiByBluetoothMonitorPortableTests(unittest.TestCase):
    def test_profile_invocation_and_filter_contract(self):
        source = SOURCE.read_text(encoding="utf-8")
        arguments = source.split("static const char *const monitor_arguments[] =", 1)[1]
        arguments = arguments.split("};", 1)[0]
        literals = re.findall(r'"([^"\n]*)"', arguments)
        self.assertEqual(literals[:2], ["--system", "--profile"])
        rules = literals[2:]
        self.assertEqual(len(rules), 8)
        self.assertEqual(len(set(rules)), 8)
        expected = []
        for interface in ("Device1", "Adapter1"):
            expected.append("type='signal',sender='org.bluez',path_namespace='/org/bluez',"
                            "interface='org.freedesktop.DBus.Properties',"
                            f"member='PropertiesChanged',arg0='org.bluez.{interface}'")
        for sender, path in (("org.bluez", "/"), ("org.bluealsa", "/org/bluealsa")):
            for member in ("InterfacesAdded", "InterfacesRemoved"):
                expected.append(f"type='signal',sender='{sender}',path='{path}',"
                                "interface='org.freedesktop.DBus.ObjectManager',"
                                f"member='{member}'")
        for service in ("org.bluez", "org.bluealsa"):
            expected.append("type='signal',sender='org.freedesktop.DBus',"
                            "path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',"
                            f"member='NameOwnerChanged',arg0='{service}'")
        self.assertEqual(rules, expected)
        self.assertNotRegex(source, r"\b(?:system|popen|execlp|execvp|pthread_create)\s*\(")

    def test_real_parser_with_native_compiler(self):
        directory = evidence_directory("portable-")
        before = input_hashes()
        if sys.platform == "win32":
            compiler = project_materials_root(ROOT) / "toolchains/llvm-mingw-20240619" / (
                "llvm-mingw-20240619-ucrt-x86_64/bin/x86_64-w64-mingw32-gcc.exe")
            self.assertTrue(compiler.is_file(), f"Required Windows test compiler: {compiler}")
            variants = {"normal": []}
        else:
            compiler = shutil.which("gcc")
            if not compiler:
                self.skipTest("GCC is required for the native parser fixture")
            variants = VARIANTS
        source = SOURCE.read_text(encoding="utf-8")
        state = source.split("static char monitor_line[", 1)[1].split(
            "static const char *const monitor_arguments", 1)[0]
        reset = source.split("static void reset_parser(void)", 1)[1].split(
            "static int64_t monotonic_ms(void)", 1)[0]
        parser = source.split("static bool consume(", 1)[1].split(
            "static bool reap_child(void)", 1)[0]
        translation = (
            "#include <stdbool.h>\n#include <stdint.h>\n#include <stdio.h>\n"
            "#include <stdlib.h>\n#include <string.h>\n" +
            re.search(r"^#define MONITOR_LINE_SIZE [0-9]+$", source, re.MULTILINE)[0] +
            "\nstatic char monitor_line[" + state +
            "static void reset_parser(void)" + reset +
            "static bool consume(" + parser +
            '#define CHECK(expression) do { if (!(expression)) { fprintf(stderr, '
            '"assertion at line %d: %s\\n", __LINE__, #expression); exit(90); } } while (0)\n'
            '#include "hiby_bluetooth_monitor_parser_fixture.c"\n'
            "int main(void) { parser_tests(); return 0; }\n")
        records = []
        environment = dict(os.environ)
        environment["ASAN_OPTIONS"] = "detect_leaks=1:halt_on_error=1:abort_on_error=1"
        environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        try:
            for variant, sanitizer in variants.items():
                executable = directory / (variant + (".exe" if sys.platform == "win32" else ""))
                command = [str(compiler), "-std=c11", "-O1", "-g", "-Wall", "-Wextra",
                           "-Werror", "-Wshadow", "-Wformat=2", "-Wstrict-prototypes"]
                if sys.platform != "win32":
                    command += ["-no-pie"] + sanitizer
                command += ["-I", str(FIXTURES), "-x", "c", "-", "-o", str(executable)]
                for stage, argv in (("compile", command), ("execute", [str(executable)])):
                    result = subprocess.run(argv, input=translation if stage == "compile" else None,
                                            capture_output=True, text=True, encoding="utf-8",
                                            timeout=60, cwd=directory, env=environment)
                    record = {"variant": variant, "stage": stage, "argv": argv,
                              "returncode": result.returncode, "stdout": result.stdout,
                              "stderr": result.stderr}
                    records.append(record)
                    write_json(directory / f"{variant}-{stage}.json", record)
                    self.assertEqual(result.returncode, 0, str(record))
                    self.assertEqual(result.stderr, "", str(record))
        finally:
            write_json(directory / "report.json", {
                "schema": "hiby-bluetooth-monitor-portable-parser:1", "inputs": before,
                "unchanged_inputs": before == input_hashes(), "results": records,
                "translation_sha256": hashlib.sha256(translation.encode()).hexdigest(),
                "source_copies": 0, "host_bus_invocations": 0,
                "scope": "exact production parser spans compiled from stdin, shared parser fixture",
                "passed": len(records) == len(variants) * 2 and before == input_hashes()
                          and all(item["returncode"] == 0 and not item["stderr"] for item in records),
                "posix_lifecycle_tested": False, "hardware_acceptance": False,
            })
        self.assertEqual(before, input_hashes(), "Monitor inputs changed during portable tests")


@unittest.skipUnless(sys.platform.startswith("linux"), "Native POSIX monitor requires Linux")
class HiByBluetoothMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc")
        if not compiler:
            raise unittest.SkipTest("GCC is required for native monitor fixtures")
        cls.directory = evidence_directory("run-")
        cls.executables = {}
        cls.results = []
        cls.inputs = input_hashes()
        write_json(cls.directory / "inputs.json", cls.inputs)
        write_json(cls.directory / "environment.json", {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version, "platform": platform.platform(),
            "compiler": compiler, "host_bus_invocations": 0,
            "scope": "private fake executable and POSIX process/pipe lifecycle only",
        })
        flags = [compiler, "-std=c11", "-O1", "-g3", "-Wall", "-Wextra",
                 "-Werror", "-Wshadow", "-Wformat=2", "-Wstrict-prototypes",
                 "-pthread", "-no-pie"]
        for variant, sanitizer in VARIANTS.items():
            directory = confined_path(cls.directory / variant, cls.directory)
            directory.mkdir()
            fake = directory / "dbus-monitor-fake"
            common = [f'-DTEST_DIRECTORY="{directory}"',
                      f'-DTEST_EXECUTABLE="{fake}"']
            commands = [
                flags + common + [str(FIXTURES / "hiby_bluetooth_monitor_fake.c"),
                                  "-o", str(fake)],
                flags + sanitizer + common + ["-I", str(SOURCE.parent),
                    str(FIXTURES / "hiby_bluetooth_monitor_fixture.c"),
                    "-o", str(directory / "monitor-test")],
                flags + sanitizer + ["-c", str(SOURCE), "-o",
                                     str(directory / "monitor-production.o")],
            ]
            for position, command in enumerate(commands):
                result = subprocess.run(command, capture_output=True, text=True,
                                        timeout=60, cwd=ROOT)
                write_json(directory / f"build-{position}.json", {
                    "argv": command, "returncode": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr,
                })
                if result.returncode:
                    raise RuntimeError(f"{variant} monitor fixture build failed: {result.stderr}")
            cls.executables[variant] = directory / "monitor-test"

    @classmethod
    def tearDownClass(cls):
        unchanged = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                        for name, digest in cls.inputs.items())
        write_json(cls.directory / "report.json", {
            "schema": "hiby-bluetooth-monitor-test:1", "inputs": cls.inputs,
            "unchanged_inputs": unchanged, "results": cls.results,
            "passed": unchanged and len(cls.results) == len(SCENARIOS) * len(VARIANTS)
                      and all(item["passed"] for item in cls.results),
            "hardware_acceptance": False, "host_bus_invocations": 0,
        })
        if not unchanged:
            raise RuntimeError("Monitor input changed during fixture run")

    def exercise(self, variant, scenario):
        environment = dict(os.environ)
        environment["ASAN_OPTIONS"] = "detect_leaks=1:halt_on_error=1:abort_on_error=1"
        environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        command = [str(self.executables[variant]), scenario]
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=15, cwd=self.directory, env=environment,
                                start_new_session=True)
        record = {"variant": variant, "scenario": scenario, "argv": command,
                  "returncode": result.returncode, "stdout": result.stdout,
                  "stderr": result.stderr,
                  "passed": result.returncode == 0 and not result.stderr}
        self.results.append(record)
        write_json(self.directory / variant / f"case-{scenario}.json", record)
        self.assertEqual(result.returncode, 0, f"{variant}/{scenario}: {result.stderr}")
        self.assertEqual(result.stderr, "", f"Unexpected sanitizer/fixture diagnostics: {record}")


def register_case(variant, scenario):
    def test_case(self):
        self.exercise(variant, scenario)
    test_case.__name__ = f"test_{variant}_{scenario.replace('-', '_')}"
    setattr(HiByBluetoothMonitorTests, test_case.__name__, test_case)


for variant_name in VARIANTS:
    for scenario_name in SCENARIOS:
        register_case(variant_name, scenario_name)


if __name__ == "__main__":
    unittest.main()
