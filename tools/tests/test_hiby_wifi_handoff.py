"""Execute the real native R1 SDIO handoff and type-specific rfkill reader safely."""

from datetime import datetime, timezone
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/target/hosted/hiby/power-control-hiby.c"
HEADER = SOURCE.with_suffix(".h")
FIXTURE = ROOT / "tools/tests/fixtures/hiby_wifi_handoff_fixture.c"
WRAPPED = (
    "open", "__open_2", "openat", "__openat_2", "fstat", "__fxstat", "fstatat", "__fxstatat", "read", "__read_chk",
    "write", "close", "socket", "ioctl", "opendir", "readdir", "closedir", "dirfd", "pipe2", "fcntl", "fcntl64",
    "posix_spawn", "posix_spawnattr_init", "posix_spawnattr_destroy", "posix_spawnattr_setflags",
    "posix_spawnattr_setpgroup", "posix_spawn_file_actions_init", "posix_spawn_file_actions_destroy",
    "posix_spawn_file_actions_adddup2", "posix_spawn_file_actions_addclose", "posix_spawn_file_actions_addopen",
    "waitpid", "kill", "clock_nanosleep", "sync", "reboot",
)
IDENTITY = (
    "suspended", "short-attributes", "missing-driver", "missing-module", "missing-function1",
    "missing-function2", "wrong-module", "wrong-driver", "wrong-vendor", "wrong-class",
    "different-device", "zero-device", "ffff-device", "already-bound", "driver-denied",
    "detach-denied", "open-storm", "stat-storm", "attribute-symlink", "nonregular-attribute",
    "bad-hex", "overlong", "read-storm", "attribute-close",
)
CONTROLS = (
    "bind-denied", "bind-symlink", "nonregular-bind", "pipe-failed", "pipe-write-storm",
    "pipe-write-short", "spawn-failed", "child-failed", "hang", "stubborn", "kill-failed",
    "cancel", "wait-storm", "wait-eintr", "sleep-failed", "action-failed", "attribute-destroy",
    "actions-destroy",
    "cancel-before-spawn", "cancel-before-bind", "cancel-after-bind", "late-bind-timeout", "late-bind-cancel",
    "target-nine", "dup-failed", "dup-storm", "dup-eintr",
)
BT = (
    "null", "blocked", "hard", "both", "unblocked", "mixed", "mixed-reasons", "empty", "none",
    "wlan-only", "deleted", "missing", "denied", "symlink", "regular-radio", "read-error",
    "read-eof", "read-short", "read-storm", "invalid-soft", "invalid-hard", "invalid-type",
    "invalid-op", "overflow", "endless", "sysfs-blocked", "sysfs-unblocked", "sysfs-hard",
    "sysfs-mixed", "sysfs-empty", "sysfs-bad-value", "sysfs-missing-attribute",
    "sysfs-read-error", "sysfs-close-error",
)
LEGACY_FAULTS = ("legacy-interface-read-error", "legacy-interface-set-error",
                 "legacy-rfkill-read-error", "legacy-rfkill-write-error")


DEVICE_FIXTURE = ROOT / "tools/tests/fixtures/hiby_wifi_device_handoff_fixture.c"
DEVICE_POSITIVE = (
    "device-no-module-link", "device-no-module-directory", "device-existing-cywdhd",
    "device-unknown-cywdhd", "device-module-stat-eintr", "device-f2-stat-eintr",
)
DEVICE_NEGATIVE = (
    "device-unknown-no-module", "device-module-link-denied", "device-module-link-io",
    "device-module-link-loop", "device-module-link-enodev", "device-module-link-enxio",
    "device-module-link-regular", "device-module-link-dangling", "device-module-wrong-owner",
    "device-module-directory-missing", "device-module-directory-denied", "device-module-stat-denied",
    "device-module-stat-io", "device-module-stat-storm", "device-f1-driver-wrong", "device-f1-driver-missing",
    "device-canonical-driver-symlink", "device-wrong-vendor", "device-wrong-class", "device-different-f2-id",
    "device-zero-id", "device-ffff-id", "device-attribute-missing", "device-f2-driver-present",
    "device-f2-driver-dangling", "device-f2-driver-denied", "device-f2-stat-denied", "device-f2-stat-io",
    "device-f2-stat-storm",
)
DEVICE_OPERATIONS = ("query", "disable", "legacy-disable", "enable")


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux syscall wrappers; run under WSL")
class HibyWifiHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc")
        if not compiler:
            raise unittest.SkipTest("gcc unavailable")
        central = project_materials_root(ROOT)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        evidence_root = confined_path(Path(os.environ.get("HIBY_RADIO_TEST_ROOT",
            central / "r1-empty-radio-20261017/wifi-handoff")), central, allow_root=True)
        cls.evidence = confined_path(evidence_root / stamp, central)
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.inputs = (SOURCE, HEADER, FIXTURE, DEVICE_FIXTURE, Path(__file__).resolve(),
            ROOT / "tools/tests/test_hiby_radio_compatibility.py",
            ROOT / "tools/tests/test_hiby_power_control.py",
            ROOT / "tools/tests/fixtures/hiby_wifi_sysfs_fixture.c",
            ROOT / "tools/tests/fixtures/hiby_power_control_fixture.c")
        cls.before = cls.hashes()
        cls.commands = []
        cls.runs = []
        cls.mutations = []
        cls.cases = []
        cls.addClassCleanup(cls.report)
        print("R1 Wi-Fi handoff evidence:", cls.evidence, flush=True)
        cls.binaries = {}
        for variant in ("strict", "fortified", "ubsan"):
            binary = cls.evidence / ("handoff-" + variant)
            arguments = [compiler, "-DHIBY_R1", "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                         "-I", str(HEADER.parent), str(SOURCE), str(FIXTURE)]
            arguments.extend("-Wl,--wrap=" + name for name in WRAPPED)
            if variant == "fortified":
                arguments.extend(["-O2", "-D_FORTIFY_SOURCE=2"])
            elif variant == "ubsan":
                arguments.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
            arguments.extend(["-o", str(binary)])
            result = cls.command(arguments)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            cls.check_imports(["nm", "-u", str(binary)])
            cls.binaries[variant] = binary

    @classmethod
    def hashes(cls):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.inputs}

    @classmethod
    def command(cls, arguments, **options):
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=90,
                                cwd=cls.evidence, **options)
        cls.commands.append({"arguments": list(map(str, arguments)), "returncode": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        return result

    @classmethod
    def check_imports(cls, arguments):
        result = cls.command(arguments)
        if result.returncode:
            raise AssertionError(result.stderr)
        symbols = {line.split()[-1].split("@")[0] for line in result.stdout.splitlines() if line.split()}
        forbidden = symbols.intersection(WRAPPED) | symbols.intersection(("system", "fork", "execve", "popen"))
        forbidden.update(name for name in symbols if re.fullmatch(
            r"(?:__)?(?:open|openat|fxstat|fstat|fxstatat|fstatat|read|write|close|socket|ioctl|reboot|kill|sync|pipe|fcntl)"
            r"(?:64)?(?:_2|_chk|_nocancel)?", name))
        if forbidden:
            raise AssertionError("Unmocked OS effects: " + repr(forbidden))

    @classmethod
    def report(cls):
        after = cls.hashes()
        report = {"source_project": str(ROOT), "source_before": cls.before, "source_after": after,
                  "sources_unchanged": cls.before == after, "commands": cls.commands, "runs": cls.runs, "mutations": cls.mutations, "cases": cls.cases,
                  "passed": bool(cls.runs) and cls.before == after and all(run["returncode"] == 0 for run in cls.runs)
                  and bool(cls.cases) and all(case["passed"] for case in cls.cases)
                  and all(item["detected"] for item in cls.mutations),
                  "scope": "Actual HIBY_R1 production source, all OS I/O mocked; no host rfkill/SDIO/network/process actions",
                  "limitations": "Not physical R1, kernel driver probe, RF electrical-off, service/controller, timing or battery acceptance"}
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if cls.before != after:
            raise AssertionError("Backend inputs changed during suite")

    def run_case(self, operation, scenario):
        for variant, binary in self.binaries.items():
            with self.subTest(variant=variant):
                result = self.command([str(binary), operation, scenario],
                    env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
                self.runs.append({"variant": variant, "operation": operation, "scenario": scenario,
                                  "returncode": result.returncode})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS handoff " + operation + " " + scenario, result.stdout)

    def test_mips_actual_vendor_glibc(self):
        central = project_materials_root(ROOT)
        sdk = central / "toolchains/hiby-r1-20261010"
        compiler = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        nm = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-nm"
        readelf = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-readelf"
        qemu = sdk / "host/usr/bin/qemu-mipsel-static"
        vendor = central / "r1-device-release-20261014/vendor-runtime"
        if not all(path.is_file() for path in (compiler, nm, readelf, qemu, vendor / "lib/ld.so.1")):
            self.skipTest("Pinned MIPS/vendor runtime unavailable")
        arguments = [str(compiler), "-DHIBY_R1", "-std=gnu99", "-O1", "-Wall", "-Wextra", "-Werror",
                     "-I", str(HEADER.parent), str(SOURCE), str(FIXTURE)]
        binary = self.evidence / "handoff-mips"
        arguments.extend("-Wl,--wrap=" + name for name in WRAPPED)
        arguments.extend(["-o", str(binary)])
        result = self.command(arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.check_imports([str(nm), "-u", str(binary)])
        result = self.command([str(readelf), "--version-info", str(binary)])
        self.assertEqual(result.returncode, 0, result.stderr)
        versions = {tuple(map(int, item.split("."))) for item in re.findall(r"GLIBC_([0-9]+(?:\.[0-9]+)+)", result.stdout)}
        self.assertTrue(versions and max(versions) <= (2, 22), repr(versions))
        environment = {key: value for key, value in os.environ.items() if key not in ("LD_PRELOAD", "LD_LIBRARY_PATH")}
        prefix_command = [str(qemu), "-L", str(vendor), str(vendor / "lib/ld.so.1"),
                          "--library-path", str(vendor / "lib") + ":" + str(vendor / "usr/lib"), str(binary)]
        for operation, scenarios in OPERATIONS:
            for scenario in scenarios:
                with self.subTest(operation=operation, scenario=scenario):
                    result = self.command(prefix_command + [operation, scenario], env=environment)
                    self.runs.append({"variant": "mips-vendor-glibc-2.22", "operation": operation,
                                      "scenario": scenario, "returncode": result.returncode})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generic_wlan_sysfs_regression_matrix(self):
        def constant(path, identifier):
            for statement in ast.parse(path.read_text()).body:
                if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and
                        target.id == identifier for target in statement.targets):
                    return ast.literal_eval(statement.value)
            raise AssertionError("Missing existing matrix constant: " + identifier)

        scenarios = constant(ROOT / "tools/tests/test_hiby_radio_compatibility.py", "CASES")
        wrapped = constant(ROOT / "tools/tests/test_hiby_power_control.py", "WRAPPED")
        fixture = ROOT / "tools/tests/fixtures/hiby_wifi_sysfs_fixture.c"
        for variant in ("strict", "fortified", "ubsan"):
            binary = self.evidence / ("legacy-sysfs-" + variant)
            arguments = [shutil.which("gcc"), "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-DHIBY_SYSFS_TEST_ENTRY_BOUND=256", "-I", str(HEADER.parent), str(SOURCE), str(fixture)]
            arguments.extend("-Wl,--wrap=" + name for name in wrapped)
            if variant == "fortified":
                arguments.extend(["-O2", "-D_FORTIFY_SOURCE=2"])
            elif variant == "ubsan":
                arguments.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
            result = self.command(arguments + ["-o", str(binary)])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.check_imports(["nm", "-u", str(binary)])
            for operation in ("query", "enable", "disable"):
                for scenario in scenarios:
                    with self.subTest(variant=variant, operation=operation, scenario=scenario):
                        result = self.command([str(binary), operation, scenario],
                            env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
                        self.runs.append({"variant": "legacy-sysfs-" + variant,
                            "operation": operation, "scenario": scenario, "returncode": result.returncode})
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def compile_device(self, variant, source=SOURCE, name="device"):
        central = project_materials_root(ROOT)
        sdk = central / "toolchains/hiby-r1-20261010"
        vendor = central / "r1-device-release-20261014/vendor-runtime"
        compiler = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-gcc" if variant == "mips" else shutil.which("gcc")
        nm = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-nm" if variant == "mips" else "nm"
        readelf = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-readelf"
        qemu = sdk / "host/usr/bin/qemu-mipsel-static"
        loader = vendor / "lib/ld.so.1"
        if variant == "mips" and not all(path.is_file() for path in (compiler, nm, readelf, qemu, loader)):
            self.skipTest("Pinned MIPS/vendor runtime unavailable")
        binary = self.evidence / (name + "-" + variant)
        arguments = [str(compiler), "-DHIBY_R1", "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                     "-I", str(HEADER.parent), str(source), str(DEVICE_FIXTURE)]
        arguments.extend("-Wl,--wrap=" + symbol for symbol in WRAPPED)
        if variant == "fortified":
            arguments.extend(["-O2", "-D_FORTIFY_SOURCE=2"])
        elif variant == "ubsan":
            arguments.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
        result = self.command(arguments + ["-o", str(binary)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.check_imports([str(nm), "-u", str(binary)])
        if variant != "mips":
            return [str(binary)]
        result = self.command([str(readelf), "--version-info", str(binary)])
        self.assertEqual(result.returncode, 0, result.stderr)
        versions = {tuple(map(int, item.split("."))) for item in re.findall(r"GLIBC_([0-9]+(?:\.[0-9]+)+)", result.stdout)}
        self.assertTrue(versions and max(versions) <= (2, 22), repr(versions))
        return [str(qemu), "-L", str(vendor), str(loader), "--inhibit-cache",
                "--library-path", str(vendor / "lib") + ":" + str(vendor / "usr/lib"), str(binary)]

    def run_device_matrix(self, variants):
        environment = {key: value for key, value in os.environ.items() if not key.startswith(("LD_", "QEMU_"))}
        environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        for variant in variants:
            prefix = self.compile_device(variant)
            for operation in DEVICE_OPERATIONS:
                for scenario in DEVICE_POSITIVE + DEVICE_NEGATIVE:
                    with self.subTest(variant=variant, operation=operation, scenario=scenario):
                        result = self.command(prefix + [operation, scenario], env=environment)
                        self.runs.append({"variant": "device-" + variant, "operation": operation,
                                          "scenario": scenario, "returncode": result.returncode})
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn("PASS device " + operation + " " + scenario, result.stdout)

    def test_device_handoff_host_matrix(self):
        self.run_device_matrix(("strict", "fortified", "ubsan"))

    def test_device_handoff_actual_vendor_glibc(self):
        self.run_device_matrix(("mips",))

    def run_device_mutations(self, variants):
        import resource

        def no_core():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        source = SOURCE.read_text(encoding="utf-8")
        negative_assertion = "result.state != HIBY_WIFI_DRIVER_SUSPENDED"
        mutations = (
            ("drop-a9a6-gate", "first_device != 0xa9a6", "first_device == 0",
             "device-unknown-no-module", negative_assertion),
            ("accept-dangling-link", "if (!fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW))\n            return ENODEV;",
             "if (!fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW))\n            return 0;",
             "device-module-link-dangling", negative_assertion),
            ("drop-f1-identity", "error = sdio_same_directory(descriptors[0], descriptors[5]);", "error = 0;",
             "device-f1-driver-wrong", negative_assertion),
            ("remove-fallback", "module_link_missing && first_device != 0xa9a6", "module_link_missing",
             "device-no-module-link", "result.state == HIBY_WIFI_DRIVER_SUSPENDED"),
        )
        environment = {key: value for key, value in os.environ.items() if not key.startswith(("LD_", "QEMU_"))}
        environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        for name, original, replacement, scenario, expected_assertion in mutations:
            self.assertEqual(source.count(original), 1, name)
            mutant = source.replace(original, replacement, 1)
            path = self.evidence / (name + ".c")
            if path.exists():
                self.assertEqual(path.read_text(encoding="utf-8"), mutant)
            else:
                with path.open("x", encoding="utf-8") as stream:
                    stream.write(mutant)
            for variant in variants:
                with self.subTest(mutation=name, variant=variant):
                    prefix = self.compile_device(variant, path, name)
                    result = self.command(prefix + ["query", scenario], env=environment, preexec_fn=no_core)
                    detected = result.returncode != 0 and expected_assertion in result.stderr and "Assertion" in result.stderr
                    self.mutations.append({"name": name, "variant": variant, "scenario": scenario,
                        "returncode": result.returncode, "detected": detected,
                        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("Assertion", result.stderr)
                    self.assertIn(expected_assertion, result.stderr)
                    self.assertNotIn("runtime error:", result.stderr)

    def test_device_handoff_host_causal_mutations(self):
        self.run_device_mutations(("strict", "ubsan"))

    def test_device_handoff_vendor_causal_mutations(self):
        self.run_device_mutations(("mips",))

    def test_import_guard_rejects_unwrapped_statat(self):
        for symbol in ("fstatat", "fstatat64", "__fxstatat", "__fxstatat64"):
            with self.subTest(symbol=symbol):
                with self.assertRaisesRegex(AssertionError, "Unmocked OS effects"):
                    self.check_imports([sys.executable, "-c", "print(' U " + symbol + "')"])

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id()
                     for test, unused in result.failures + result.errors)
        self.cases.append({"name": self.id(), "passed": not failed})


OPERATIONS = (("query", IDENTITY), ("disable", IDENTITY), ("legacy-disable", IDENTITY),
              ("enable", IDENTITY + CONTROLS), ("bt", BT), ("legacy-disable", LEGACY_FAULTS))


def make_case(operation, scenario):
    def test(self):
        self.run_case(operation, scenario)
    return test


for operation, scenarios in OPERATIONS:
    for scenario in scenarios:
        setattr(HibyWifiHandoffTests, "test_" + operation.replace("-", "_") + "_" + scenario.replace("-", "_"),
                make_case(operation, scenario))


if __name__ == "__main__":
    unittest.main()
