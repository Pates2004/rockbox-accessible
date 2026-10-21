"""Real spawn/file-descriptor handoff, confined to new regular evidence files."""

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
from project_materials import confined_path, project_materials_root

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware/target/hosted/hiby/power-control-hiby.c"
HEADER = SOURCE.with_suffix(".h")
FIXTURE = ROOT / "tools/tests/fixtures/hiby_wifi_child_descriptors_fixture.c"


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux procfs descriptor fixture; run under WSL")
class HibyWifiChildDescriptorTests(unittest.TestCase):
    def test_actual_vendor_glibc_and_busybox_descriptor_handoff(self):
        central = project_materials_root(ROOT)
        sdk = central / "toolchains/hiby-r1-20261010"
        compiler = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        nm = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-nm"
        readelf = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-readelf"
        qemu = sdk / "host/usr/bin/qemu-mipsel-static"
        vendor = central / "r1-device-release-20261014/vendor-runtime"
        image = central / "r1-device-release-20261014/rootfs.squashfs"
        loader = vendor / "lib/ld.so.1"
        if not all(path.is_file() for path in (compiler, nm, readelf, qemu, loader, image)):
            self.skipTest("Pinned MIPS compiler/QEMU/actual vendor runtime unavailable")
        area = confined_path(central / "r1-empty-radio-20261017/wifi-handoff", central)
        area.mkdir(parents=True, exist_ok=True)
        busybox = area / "vendor-bin/busybox"
        busybox.parent.mkdir(exist_ok=True)
        extracted = subprocess.run(["unsquashfs", "-cat", str(image), "bin/busybox"],
                                  capture_output=True, timeout=30, check=True).stdout
        self.assertTrue(extracted.startswith(b"\x7fELF\x01\x01"))
        self.assertEqual(extracted[18:20], b"\x08\x00")
        if busybox.exists():
            self.assertEqual(busybox.read_bytes(), extracted, "Refuse conflicting vendor BusyBox")
        else:
            with busybox.open("xb") as stream:
                stream.write(extracted)
            busybox.chmod(0o755)
        private_libraries = area / "vendor-libraries"
        private_libraries.mkdir(exist_ok=True)
        resolver = private_libraries / "libresolv.so.2"
        resolver_data = subprocess.run(["unsquashfs", "-cat", str(image), "lib/libresolv-2.22.so"],
            capture_output=True, timeout=30, check=True).stdout
        if resolver.exists():
            self.assertEqual(resolver.read_bytes(), resolver_data, "Refuse conflicting vendor resolver")
        else:
            with resolver.open("xb") as stream:
                stream.write(resolver_data)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        evidence = area / ("vendor-descriptors-" + stamp)
        evidence.mkdir(exist_ok=False)
        inputs = (SOURCE, HEADER, FIXTURE, Path(__file__).resolve())
        before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        report = {"source_before": before, "commands": [], "runs": [], "passed": False,
            "scope": "Actual MIPS glibc2.22 posix_spawn file actions; host Python validates fd9 inode before exec of actual vendor BusyBox dd under nested QEMU",
            "host_radio_used": False, "host_audio_used": False, "physical_R1_tested": False,
            "runtime_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (loader, vendor / "lib/libc.so.6", busybox, resolver, qemu)},
            "busybox_origin": str(image) + ":bin/busybox", "busybox_retained_single_copy": str(busybox),
            "resolver_origin": str(image) + ":lib/libresolv-2.22.so", "resolver_retained_single_copy": str(resolver)}
        checker = evidence / "check_owned_descriptor.py"
        checker.write_text('''import fcntl
import json
import os
import stat
import sys

filename, qemu, vendor, loader, libraries, busybox = sys.argv[1:]
if not filename.startswith("controlled-") or "/" in filename or "\\\\" in filename:
    raise SystemExit(70)
def fail(code, reason):
    with open(filename + ".fd9.json", "x") as stream:
        json.dump({"passed": False, "code": code, "reason": reason}, stream)
    raise SystemExit(code)
try:
    inherited = os.fstat(9)
    expected = os.stat(filename, follow_symlinks=False)
except OSError as error:
    fail(71, str(error))
if not stat.S_ISREG(inherited.st_mode) or not stat.S_ISREG(expected.st_mode):
    fail(72, "not regular")
if (inherited.st_dev, inherited.st_ino) != (expected.st_dev, expected.st_ino):
    fail(73, "wrong inode")
if fcntl.fcntl(9, fcntl.F_GETFD) & fcntl.FD_CLOEXEC:
    fail(74, "CLOEXEC still set")
with open(filename + ".fd9.json", "x") as stream:
    json.dump({"passed": True, "fd9_inode": inherited.st_ino}, stream)
os.execve(qemu, [qemu, "-L", vendor, loader, "--library-path", libraries,
    busybox, "dd", "of=/proc/self/fd/9", "bs=64", "count=1"], dict(os.environ))
''', encoding="utf-8")
        print("R1 vendor child descriptor evidence:", evidence, flush=True)

        def disable_core_dump():
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        environment = {key: value for key, value in os.environ.items() if not key.startswith(("LD_", "QEMU_"))}

        def command(arguments):
            result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True,
                cwd=evidence, timeout=30, env=environment, preexec_fn=disable_core_dump)
            report["commands"].append({"arguments": list(map(str, arguments)), "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr})
            return result

        try:
            binary = evidence / "descriptors-mips"
            result = command([compiler, "-DHIBY_R1", "-DHIBY_VENDOR_DESCRIPTORS_TEST", "-std=gnu99",
                "-Wall", "-Wextra", "-Werror", "-O1", "-g", "-ffunction-sections", "-fdata-sections",
                "-Wl,--gc-sections", "-Wl,--wrap=posix_spawn", FIXTURE, "-o", binary])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = command([nm, "-u", binary])
            self.assertEqual(result.returncode, 0, result.stderr)
            for forbidden in ("socket", "ioctl", "reboot", "sync", "opendir", "openat", "read"):
                self.assertIsNone(re.search(r"\b" + forbidden + r"(?:@|\s|$)", result.stdout), forbidden)
            result = command([readelf, "--version-info", binary])
            self.assertEqual(result.returncode, 0, result.stderr)
            versions = {tuple(map(int, item.split("."))) for item in re.findall(r"GLIBC_([0-9]+(?:\.[0-9]+)+)", result.stdout)}
            self.assertTrue(versions and max(versions) <= (2, 22), repr(versions))
            libraries = str(vendor / "lib") + ":" + str(vendor / "usr/lib") + ":" + str(private_libraries)
            prefix = [qemu, "-L", vendor, loader, "--library-path", libraries]
            for topology in range(4):
                with self.subTest(topology=topology):
                    filename = "controlled-vendor-" + str(topology)
                    result = command(prefix + [binary, filename, str(topology), checker,
                        qemu, vendor, loader, libraries, busybox])
                    data = (evidence / filename).read_bytes() if (evidence / filename).exists() else None
                    passed = result.returncode == 0 and data == b"mmc0:0001:2\n"
                    report["runs"].append({"variant": "mips-glibc2.22-vendor-busybox", "topology": topology,
                        "returncode": result.returncode, "target_bytes_hex": data.hex() if data is not None else None,
                        "passed": passed})
                    self.assertTrue(passed, result.stdout + result.stderr + repr(data))
            report["passed"] = len(report["runs"]) == 4 and all(run["passed"] for run in report["runs"])
        finally:
            after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
            report["source_after"] = after
            report["sources_unchanged"] = before == after
            report["passed"] = report["passed"] and before == after
            (evidence / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.assertEqual(before, after)

    def test_actual_file_actions_keep_only_the_owned_regular_target(self):
        compiler = shutil.which("gcc")
        if not compiler or not Path("/bin/dd").is_file():
            self.skipTest("gcc and the controlled dd fixture executable are required")
        central = project_materials_root(ROOT)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        evidence = confined_path(central / "r1-empty-radio-20261017/wifi-handoff" / ("descriptors-" + stamp), central)
        evidence.mkdir(parents=True, exist_ok=False)
        inputs = (SOURCE, HEADER, FIXTURE, Path(__file__).resolve())
        before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        report = {"source_before": before, "commands": [], "runs": [], "passed": False,
                  "scope": "Actual production static child helper and real posix_spawn file actions; fixed dd writes only owned regular files in evidence cwd",
                  "host_radio_used": False, "host_audio_used": False, "physical_R1_tested": False}
        print("R1 child descriptor evidence:", evidence, flush=True)

        def command(arguments):
            result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True,
                                    cwd=evidence, timeout=30, env=dict(os.environ,
                                    UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
            report["commands"].append({"arguments": list(map(str, arguments)), "returncode": result.returncode,
                                       "stdout": result.stdout, "stderr": result.stderr})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result

        try:
            for variant in ("strict", "fortified", "ubsan"):
                binary = evidence / ("descriptors-" + variant)
                arguments = [compiler, "-DHIBY_R1", "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                    "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", "-Wl,--wrap=posix_spawn", str(FIXTURE)]
                if variant == "fortified":
                    arguments.extend(["-O2", "-D_FORTIFY_SOURCE=2"])
                elif variant == "ubsan":
                    arguments.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
                command(arguments + ["-o", binary])
                symbols = command(["nm", "-u", binary]).stdout
                for forbidden in ("socket", "ioctl", "reboot", "sync", "opendir", "openat", "read"):
                    self.assertIsNone(re.search(r"\b" + forbidden + r"(?:@|\s|$)", symbols), forbidden)
                for topology in range(4):
                    filename = "controlled-" + variant + "-" + str(topology)
                    command([binary, filename, str(topology)])
                    self.assertEqual((evidence / filename).read_bytes(), b"mmc0:0001:2\n")
                    report["runs"].append({"variant": variant, "topology": topology, "passed": True})
            report["passed"] = True
        finally:
            after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
            report["source_after"] = after
            report["sources_unchanged"] = before == after
            report["passed"] = report["passed"] and before == after
            (evidence / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
