"""Run native R1 power/radio C with every OS operation intercepted."""

from datetime import datetime, timezone
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
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/target/hosted/hiby/power-control-hiby.c"
HEADER = SOURCE.with_suffix(".h")
FIXTURE = ROOT / "tools/tests/fixtures/hiby_power_control_fixture.c"
WRAPPED = (
    "opendir", "readdir", "closedir", "dirfd", "openat", "__openat_2",
    "open", "__open_2", "fstat", "__fxstat", "fstatat", "__fxstatat", "close", "read", "__read_chk", "write", "socket", "ioctl", "posix_spawn",
    "posix_spawnattr_init", "posix_spawnattr_destroy", "posix_spawnattr_setflags",
    "posix_spawnattr_setpgroup", "waitpid", "kill", "clock_nanosleep", "sync", "reboot",
)
WIFI_CASES = (
    "blocked", "unblocked", "missing", "denied", "write-denied", "write-short",
    "write-zero", "read-short", "read-zero", "read-error", "endless", "overflow",
    "invalid", "invalid-soft", "invalid-type", "change-missing", "changes", "hard-only",
    "no-radio", "bt-only", "multi-radio", "transient-no-wlan", "interface-denied",
    "interface-stuck", "interface-missing", "socket-failure", "socket-eintr",
    "ioctl-eintr", "open-eintr", "write-eintr", "read-eintr", "fstat-eintr",
    "fstat-failure", "regular", "symlink", "close-eintr", "repeated", "read-open-denied",
    "open-interrupt-storm", "write-interrupt-storm", "read-interrupt-storm",
    "socket-interrupt-storm", "ioctl-interrupt-storm", "fstat-interrupt-storm",
    "already-blocked-write-denied", "already-down", "two-interfaces",
    "interface-set-failure", "interface-readback-failure",
    "write-denied-read-missing", "write-missing-read-blocked",
    "write-missing-read-unblocked", "read-only-missing",
)
OBSERVATION_FAULTS = (
    "missing", "denied", "read-open-denied", "read-only-missing", "read-short",
    "read-zero", "read-error", "endless", "overflow", "invalid", "invalid-soft",
    "invalid-hard", "invalid-type", "change-missing", "regular", "symlink",
    "read-eintr", "open-eintr", "fstat-eintr", "socket-eintr", "ioctl-eintr",
    "fstat-failure", "read-interrupt-storm", "open-interrupt-storm",
    "fstat-interrupt-storm", "socket-interrupt-storm", "ioctl-interrupt-storm",
    "read-close-failure", "interface-close-failure", "socket-failure",
    "interface-denied", "interface-readback-failure", "close-eintr",
)
CONTROL_FAULTS = OBSERVATION_FAULTS + (
    "write-denied", "write-short", "write-zero", "write-eintr", "write-interrupt-storm",
    "write-close-failure", "write-error-read-error", "write-denied-read-missing",
    "write-missing-read-blocked", "write-missing-read-unblocked",
    "interface-set-failure", "interface-set-and-read-failure", "interface-stuck",
    "stale-interface",
)
CONTROL_STATES = (
    "hard-blocked", "hard-and-soft", "hard-clears", "hard-appears", "no-radio",
    "bt-only", "bt-events", "mixed-radios", "two-interfaces", "mixed-interfaces",
    "interface-missing", "interface-late-appears", "interface-disappears",
    "changed-state", "deleted-radio", "repeated",
)
ENABLE_CASES = CONTROL_STATES + CONTROL_FAULTS + (
    "enabled", "already-enabled", "already-enabled-write-denied", "stale-blocked",
)
DISABLE_CASES = CONTROL_STATES + CONTROL_FAULTS + (
    "blocked", "already-blocked-write-denied", "stale-unblocked",
)
QUERY_CASES = OBSERVATION_FAULTS + (
    "enabled", "blocked", "hard-blocked", "hard-and-soft", "hard-clears", "hard-appears",
    "no-radio", "bt-only", "bt-events", "mixed-radios", "two-interfaces",
    "mixed-interfaces", "interface-missing", "interface-down", "changed-state",
    "deleted-radio", "refresh", "repeated",
)
POWER_CASES = (
    "normal", "normal-failed", "child-signal", "hang", "stubborn", "kill-failure",
    "kill-eintr", "kill-interrupt-storm", "spawn-failure", "spawn-badpid",
    "attribute-init", "attribute-flags", "attribute-group", "attribute-destroy",
    "wait-eintr", "wait-interrupt-storm", "wait-echild", "sleep-eintr", "sleep-failure",
    "sleep-failure-hang", "sleep-interrupt-storm", "sleep-invalid", "reboot-eintr",
    "reboot-interrupt-storm", "reboot-returned-success", "power-repeated",
)
OPERATIONS = (("wifi", WIFI_CASES), ("enable", ENABLE_CASES),
              ("disable", DISABLE_CASES), ("query", QUERY_CASES), ("power", POWER_CASES))


@unittest.skipUnless(sys.platform.startswith("linux"), "Requires Linux host compiler; run under WSL")
class HibyPowerControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc")
        if not compiler:
            raise unittest.SkipTest("gcc is unavailable")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        evidence_root = confined_path(Path(os.environ.get("HIBY_RADIO_TEST_ROOT",
            central / "r1-empty-radio-20261017/wifi-handoff")), central, allow_root=True)
        cls.evidence = confined_path(evidence_root / "generic-power" / stamp, central)
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands = []
        cls.cases = []
        cls.runs = []
        cls.inputs = (SOURCE, HEADER, FIXTURE, Path(__file__).resolve())
        cls.before = cls.hashes()
        cls.addClassCleanup(cls.report)
        print("R1 power evidence:", cls.evidence, flush=True)
        cls.binaries = {}
        for variant in ("strict", "fortified", "ubsan"):
            binary = cls.evidence / ("power-" + variant)
            arguments = [compiler, "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                         "-I", str(HEADER.parent), str(SOURCE), str(FIXTURE)]
            arguments.extend("-Wl,--wrap=" + name for name in WRAPPED)
            if variant == "ubsan":
                arguments.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
            elif variant == "fortified":
                arguments.extend(["-O2", "-D_FORTIFY_SOURCE=2"])
            arguments.extend(["-o", str(binary)])
            result = cls.command(arguments)
            if result.returncode:
                raise AssertionError("Actual backend fixture compilation failed:\n" + result.stderr)
            result = cls.command(["nm", "-u", str(binary)])
            if result.returncode:
                raise AssertionError("Cannot inspect fixture imports: " + result.stderr)
            symbols = {line.split()[-1].split("@")[0] for line in result.stdout.splitlines() if line.split()}
            forbidden = symbols.intersection(WRAPPED) | symbols.intersection(("system", "execve", "fork"))
            forbidden.update(name for name in symbols if re.fullmatch(
                r"(?:__)?(?:open|openat|fxstat|fstat|fxstatat|fstatat|read|write|close|socket|ioctl|reboot|kill|sync)"
                r"(?:64)?(?:_2|_chk|_nocancel)?", name))
            if forbidden:
                raise AssertionError("Dangerous unmocked fixture imports: " + str(forbidden))
            cls.binaries[variant] = binary

    @classmethod
    def hashes(cls):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in cls.inputs}

    @classmethod
    def command(cls, arguments, **options):
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=60,
                                cwd=cls.evidence, **options)
        cls.commands.append({"arguments": arguments, "cwd": str(cls.evidence),
                             "returncode": result.returncode, "stdout": result.stdout,
                             "stderr": result.stderr})
        return result

    @classmethod
    def report(cls):
        after = cls.hashes()
        report = {
            "source_project": str(ROOT), "source_before": cls.before, "source_after": after,
            "sources_unchanged": after == cls.before,
            "scope": "Actual power-control-hiby.c; every radio, network, spawn, wait, signal, timing, sync and reboot syscall mocked",
            "limitations": "No physical radio, service ownership, shutdown/PMIC, battery, real waits or network acceptance",
            "commands": cls.commands, "runs": cls.runs, "cases": cls.cases,
            "passed": bool(cls.cases) and after == cls.before and all(case["passed"] for case in cls.cases),
        }
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
        if after != cls.before:
            raise AssertionError("Backend inputs changed during tests")

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id()
                     for test, unused in result.failures + result.errors)
        self.cases.append({"name": self.id(), "passed": not failed})

    def run_case(self, operation, scenario):
        for variant, binary in self.binaries.items():
            with self.subTest(variant=variant):
                result = self.command([str(binary), operation, scenario],
                    env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
                self.runs.append({"variant": variant, "operation": operation,
                                  "scenario": scenario, "returncode": result.returncode})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS " + operation + " " + scenario, result.stdout)

    def test_backend_contains_no_shell_exit_service_or_credential_commands(self):
        source = SOURCE.read_text(encoding="utf-8")
        for name in ("system", "exit", "_exit", "execve", "fork", "malloc", "calloc", "realloc"):
            self.assertIsNone(re.search(r"\b" + name + r"\s*\(", source), name)
        for prohibited in ("killall", "wpa_supplicant", "udhcpc", "RFKILL_TYPE_ALL,",
                           "rfkill block all", "modprobe", "rmmod", "wpa_supplicant.conf"):
            self.assertNotIn(prohibited, source)

    def test_mips_strict_compile(self):
        compiler = project_materials_root(ROOT) / (
            "toolchains/hiby-r1-20261010/prefix/bin/mipsel-rockbox-linux-gnu-gcc")
        if not compiler.is_file():
            self.skipTest("Pinned R1 compiler is unavailable")
        result = self.command([str(compiler), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                               "-O1", "-I", str(HEADER.parent), "-c", str(SOURCE),
                               "-o", str(self.evidence / "power-control-hiby-mips.o")])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mips_fixture_under_actual_vendor_glibc(self):
        central = project_materials_root(ROOT)
        sdk = central / "toolchains/hiby-r1-20261010"
        compiler = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        nm = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-nm"
        readelf = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-readelf"
        qemu = sdk / "host/usr/bin/qemu-mipsel-static"
        vendor = central / "r1-device-release-20261014/vendor-runtime"
        loader = vendor / "lib/ld.so.1"
        if not all(path.is_file() for path in (compiler, nm, readelf, qemu, loader)):
            self.skipTest("Pinned compiler/QEMU/actual vendor runtime is unavailable")
        shared = self.evidence / "power-control-production-mips.so"
        result = self.command([str(compiler), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                               "-O1", "-shared", "-fPIC", "-Wl,-z,defs", str(SOURCE),
                               "-o", str(shared), "-lrt"])
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.command([str(readelf), "--version-info", str(shared)])
        self.assertEqual(result.returncode, 0, result.stderr)
        versions = {tuple(map(int, value.split("."))) for value in
                    re.findall(r"GLIBC_([0-9]+(?:\.[0-9]+)+)", result.stdout)}
        self.assertTrue(versions and max(versions) <= (2, 22), str(versions))
        binary = self.evidence / "power-mips"
        arguments = [str(compiler), "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                     "-march=mips32r2", "-mabi=32", "-EL", "-mhard-float", "-mfp32",
                     "-I", str(HEADER.parent), str(SOURCE), str(FIXTURE)]
        arguments.extend("-Wl,--wrap=" + name for name in WRAPPED)
        arguments.extend(["-o", str(binary)])
        result = self.command(arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.command([str(nm), "-u", str(binary)])
        self.assertEqual(result.returncode, 0, result.stderr)
        symbols = {line.split()[-1].split("@")[0] for line in result.stdout.splitlines() if line.split()}
        forbidden = symbols.intersection(WRAPPED) | {
            name for name in symbols if re.fullmatch(
                r"(?:__)?(?:open|openat|fxstat|fstat|fxstatat|fstatat|read|write|close|socket|ioctl|reboot|kill|sync)"
                r"(?:64)?(?:_2|_chk|_nocancel)?", name)}
        self.assertFalse(forbidden, "Dangerous unmocked MIPS imports: " + str(forbidden))
        result = self.command([str(readelf), "--version-info", str(binary)])
        self.assertEqual(result.returncode, 0, result.stderr)
        versions = {tuple(map(int, value.split("."))) for value in
                    re.findall(r"GLIBC_([0-9]+(?:\.[0-9]+)+)", result.stdout)}
        self.assertTrue(versions and max(versions) <= (2, 22), str(versions))
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("LD_", "QEMU_"))}
        prefix = [str(qemu), "-L", str(vendor), str(loader), "--inhibit-cache",
                  "--library-path", str(vendor / "lib"), str(binary)]
        for operation, scenarios in OPERATIONS:
            for scenario in scenarios:
                with self.subTest(operation=operation, scenario=scenario):
                    result = self.command(prefix + [operation, scenario], env=environment)
                    self.runs.append({"variant": "mips-vendor-glibc-2.22", "operation": operation,
                                      "scenario": scenario, "returncode": result.returncode})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("PASS " + operation + " " + scenario, result.stdout)


def make_case(operation, scenario):
    def test(self):
        self.run_case(operation, scenario)
    return test


for operation, scenarios in OPERATIONS:
    for scenario in scenarios:
        setattr(HibyPowerControlTests, "test_" + operation + "_" + scenario.replace("-", "_"),
                make_case(operation, scenario))


if __name__ == "__main__":
    unittest.main()
