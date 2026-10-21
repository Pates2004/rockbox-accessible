"""Exercise WLAN sysfs fallback and both workers with the actual R1 runtime."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_materials import confined_path, project_materials_root
from test_hiby_power_control import WRAPPED


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "firmware/target/hosted/hiby/power-control-hiby.c"
SYSFS_FIXTURE = ROOT / "tools/tests/fixtures/hiby_wifi_sysfs_fixture.c"
BT_FIXTURE = ROOT / "tools/tests/fixtures/hiby_bluetooth_stack_fixture.c"
CONNECTIVITY_FIXTURE = ROOT / "tools/tests/fixtures/hiby_connectivity_fixture.c"
CASES = ("normal", "none", "bt-only", "missing", "directory-denied", "directory-storm",
         "directory-read-error", "directory-read-storm", "directory-close-error", "too-many",
         "attribute-missing", "attribute-symlink", "bad-soft", "bad-hard", "bad-type",
         "overlong", "read-eintr", "read-storm", "read-short", "write-eintr", "write-storm",
         "short-write", "write-denied", "stale", "hard-blocked", "junk")


def disable_core_dump():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


@unittest.skipUnless(sys.platform.startswith("linux"), "Requires Linux compiler; run under WSL")
class HibyRadioCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("gcc")
        if not cls.compiler:
            raise unittest.SkipTest("gcc unavailable")
        central = project_materials_root(ROOT)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.evidence = confined_path(central / "r1-input-refinements-20261017/connectivity/compatibility" / stamp, central)
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.inputs = (BACKEND, BACKEND.with_suffix(".h"), SYSFS_FIXTURE, BT_FIXTURE,
                      CONNECTIVITY_FIXTURE, SYSFS_FIXTURE.with_name("hiby_power_control_fixture.c"),
                      ROOT / "apps/hiby_connectivity.c", ROOT / "apps/hiby_connectivity.h",
                      ROOT / "apps/hiby_bluetooth.c", ROOT / "apps/hiby_bluetooth.h",
                      ROOT / "firmware/target/hosted/hiby/bluetooth-hiby.h", Path(__file__).resolve())
        cls.before = cls.hashes()
        cls.commands = []
        cls.cases = []
        cls.test_runs = []
        cls.runtime_inputs = {}
        cls.addClassCleanup(cls.report)
        cls.headers = cls.evidence / "headers"
        cls.headers.mkdir()
        for name in ("config.h", "file.h", "action.h", "kernel.h", "lang.h", "language.h",
                     "list.h", "menu.h", "misc.h", "splash.h", "talk.h"):
            (cls.headers / name).write_text("#pragma once\n", encoding="utf-8")
        (cls.headers / "rbpaths.h").write_text('#define ROCKBOX_DIR "/.rockbox"\n', encoding="utf-8")
        labels = sorted(set(re.findall(r"\bLANG_[A-Z_]+", (ROOT / "apps/hiby_connectivity.c").read_text(encoding="utf-8"))))
        definitions = "\n".join(f"#define {label} {1000 + index}" for index, label in enumerate(labels))
        definitions += f"\n#define CONNECTIVITY_LABEL_COUNT {len(labels)}\n"
        definitions += "static const char *const connectivity_labels[] = {\n"
        definitions += ",\n".join(json.dumps(label) for label in labels) + "\n};\n"
        (cls.headers / "connectivity-labels.h").write_text(definitions, encoding="utf-8")
        (cls.headers / "stack-minimum.h").write_text(
            "#include <errno.h>\n#include <limits.h>\n#include <pthread.h>\n"
            "#undef PTHREAD_STACK_MIN\n#define PTHREAD_STACK_MIN 131072\n"
            "static inline int checked_stack_size(pthread_attr_t *attributes, size_t size)\n"
            "{\n    return size < PTHREAD_STACK_MIN ? EINVAL : pthread_attr_setstacksize(attributes, size);\n}\n"
            "#define pthread_attr_setstacksize checked_stack_size\n", encoding="utf-8")
        cls.binaries = {}
        for variant in ("strict", "fortified", "ubsan"):
            cls.binaries[variant] = cls.compile_sysfs(cls.compiler, variant)
        cls.sdk = central / "toolchains/hiby-r1-20261010"
        cls.vendor = central / "r1-device-release-20261014/vendor-runtime"
        print("Radio compatibility evidence:", cls.evidence, flush=True)

    @classmethod
    def hashes(cls):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}

    @classmethod
    def command(cls, arguments, expected=0):
        environment = {key: value for key, value in os.environ.items() if not key.startswith(("LD_", "QEMU_"))}
        environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        result = subprocess.run(list(map(str, arguments)), cwd=cls.evidence, capture_output=True, text=True,
                                timeout=30, env=environment, preexec_fn=disable_core_dump)
        cls.commands.append({"arguments": list(map(str, arguments)), "exit": result.returncode,
                             "expected": expected, "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode != expected:
            raise AssertionError(" ".join(map(str, arguments)) + "\n" + result.stdout + result.stderr)
        return result

    @classmethod
    def compile_sysfs(cls, compiler, variant):
        binary = cls.evidence / ("sysfs-" + variant)
        arguments = [compiler, "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                     "-DHIBY_SYSFS_TEST_ENTRY_BOUND=256", "-I", BACKEND.parent, BACKEND, SYSFS_FIXTURE]
        arguments += ["-Wl,--wrap=" + name for name in WRAPPED]
        if variant == "fortified":
            arguments += ["-O2", "-D_FORTIFY_SOURCE=2"]
        if variant == "ubsan":
            arguments += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        cls.command(arguments + ["-o", binary])
        cls.assert_safe_imports(binary, "nm" if variant != "vendor" else cls.sdk / "prefix/bin/mipsel-rockbox-linux-gnu-nm")
        return binary

    @classmethod
    def assert_safe_imports(cls, binary, nm):
        symbols = {line.split()[-1].split("@")[0] for line in cls.command([nm, "-u", binary]).stdout.splitlines() if line.split()}
        forbidden = symbols.intersection(WRAPPED) | symbols.intersection(("system", "execve", "fork"))
        if forbidden:
            raise AssertionError(f"Unmocked system/radio imports: {forbidden}")

    @classmethod
    def report(cls):
        after = cls.hashes()
        passed = bool(cls.cases) and cls.before == after and all(case["passed"] for case in cls.cases)
        passed = passed and all(command["exit"] == command["expected"] for command in cls.commands)
        passed = passed and bool(cls.test_runs) and all(test["passed"] for test in cls.test_runs)
        (cls.evidence / "report.json").write_text(json.dumps({"passed": passed, "inputs_before": cls.before,
            "inputs_after": after, "commands": cls.commands, "cases": cls.cases, "test_runs": cls.test_runs,
            "vendor_runtime_inputs": cls.runtime_inputs,
            "scope": "Actual C modules with all radio/process/storage effects intercepted; actual vendor pthread for MIPS workers",
            "physical_R1_tested": False, "host_radio_used": False, "host_audio_used": False}, indent=2) + "\n", encoding="utf-8")
        if cls.before != after:
            raise AssertionError("Owned sources changed while compatibility tests were running")

    def run(self, result=None):
        result = result if result is not None else self.defaultTestResult()
        before = len(result.failures) + len(result.errors)
        returned = super().run(result)
        if hasattr(self.__class__, "test_runs"):
            self.test_runs.append({"name": self.id(), "passed": len(result.failures) + len(result.errors) == before})
        return returned

    def run_matrix(self, variant, prefix):
        for operation in ("enable", "disable", "query"):
            for scenario in CASES:
                with self.subTest(variant=variant, operation=operation, scenario=scenario):
                    passed = False
                    try:
                        result = self.command([*prefix, operation, scenario])
                        self.assertIn(f"PASS sysfs {operation} {scenario}", result.stdout)
                        passed = True
                    finally:
                        self.cases.append({"variant": variant, "operation": operation, "scenario": scenario, "passed": passed})

    def test_sysfs_strict_fortified_and_ubsan(self):
        for variant, binary in self.binaries.items():
            self.run_matrix(variant, [binary])

    def vendor_prefix(self):
        compiler = self.sdk / "prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        qemu = self.sdk / "host/usr/bin/qemu-mipsel-static"
        loader = self.vendor / "lib/ld.so.1"
        if not all(path.is_file() for path in (compiler, qemu, loader)):
            self.skipTest("Pinned MIPS compiler/QEMU/vendor runtime unavailable")
        for path in (compiler, qemu, loader, self.vendor / "lib/libc.so.6", self.vendor / "lib/libpthread.so.0"):
            self.runtime_inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return compiler, [qemu, "-L", self.vendor, loader, "--inhibit-cache", "--library-path", self.vendor / "lib"]

    def test_sysfs_actual_vendor_runtime(self):
        compiler, prefix = self.vendor_prefix()
        binary = self.compile_sysfs(compiler, "vendor")
        self.run_matrix("vendor", [*prefix, binary])

    def compile_worker(self, compiler, worker, variant, forced_minimum, source=None):
        binary = self.evidence / (worker + "-" + variant)
        arguments = [compiler, "-std=gnu99", "-O1", "-Wall", "-Wextra", "-Werror", "-pthread",
                     "-I", self.headers, "-I", ROOT / "apps", "-I", BACKEND.parent]
        if forced_minimum:
            arguments += ["-include", self.headers / "stack-minimum.h"]
        if worker == "bluetooth":
            arguments += ["-DHIBY_BT_HOST_TEST", "-DHIBY_BT_NO_UI", source or ROOT / "apps/hiby_bluetooth.c", BT_FIXTURE]
        else:
            arguments += ["-DHIBY_LINUX", "-DHIBY_CONNECTIVITY_BT_WAIT_MS=100",
                          "-DHIBY_CONNECTIVITY_SETTLE_MS=100", CONNECTIVITY_FIXTURE]
            if source:
                arguments += ['-DCONNECTIVITY_TEST_SOURCE="' + str(source) + '"']
        self.command(arguments + ["-o", binary])
        self.assert_safe_imports(binary, "nm" if forced_minimum else self.sdk / "prefix/bin/mipsel-rockbox-linux-gnu-nm")
        return binary

    def test_both_workers_with_128k_minimum_and_actual_vendor_pthread(self):
        compiler, vendor_prefix = self.vendor_prefix()
        for variant, toolchain, prefix, forced_minimum in (
                ("host-minimum", self.compiler, [], True), ("vendor", compiler, vendor_prefix, False)):
            for worker in ("connectivity", "bluetooth"):
                binary = self.compile_worker(toolchain, worker, variant, forced_minimum)
                arguments = ["policy", "restore-both"] if worker == "connectivity" else []
                result = self.command([*prefix, binary, *arguments])
                self.assertIn("PASS", result.stdout)
                if worker == "bluetooth":
                    self.assertIn("minimum=131072", result.stdout)
                self.cases.append({"variant": variant, "worker": worker, "passed": True})

    def test_old_64k_stacks_fail_with_actual_vendor_pthread(self):
        compiler, prefix = self.vendor_prefix()
        for worker in ("connectivity", "bluetooth"):
            source = ROOT / ("apps/hiby_" + worker + ".c")
            production = source.read_text(encoding="utf-8")
            call = "pthread_attr_setstacksize(&attributes, stack_size)"
            self.assertEqual(production.count(call), 1)
            mutation = self.evidence / (worker + "-old-stack.c")
            mutation.write_text(production.replace(call, "pthread_attr_setstacksize(&attributes, 65536)", 1), encoding="utf-8")
            binary = self.compile_worker(compiler, worker, "old-stack", False, mutation)
            arguments = ["policy", "restore-both"] if worker == "connectivity" else []
            result = self.command([*prefix, binary, *arguments], expected=-signal.SIGABRT)
            self.assertIn("hiby_" + worker, result.stderr)
            self.cases.append({"variant": "vendor-old-stack-negative-control", "worker": worker, "passed": True})


if __name__ == "__main__":
    unittest.main()
