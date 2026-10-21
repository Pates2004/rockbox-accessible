"""Discoverable Python controls for the MIPS harness; no cross compiler or QEMU runs."""

import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import unittest
from unittest import mock

from materials_fixtures import materials_resolver
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/tests"))
import project_materials
import test_espeak_hiby_mips as harness


class MipsHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        central = project_materials.project_materials_root(ROOT)
        project_materials.ensure_ignored_directories(central.parent, (central.name,))
        cls.central = central
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.workspace = project_materials.confined_path(
            central / "espeak-hiby-mips-harness" / stamp, central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.input_sources = [Path(__file__).resolve(), Path(harness.__file__).resolve(),
                             ROOT / "tools/project_materials.py",
                             ROOT / "tools/tests/test_espeak_native_runtime.py",
                             ROOT / "tools/tests/test_espeak_hosted_runtime.py"]
        cls.inputs_before = harness.fingerprint(cls.input_sources, ROOT)
        harness.write_json(cls.workspace / "provenance.json", {
            "source_project": str(ROOT), "test_module": str(Path(__file__).resolve()),
            "harness_module": str(Path(harness.__file__).resolve()),
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version, "platform": sys.platform, "argv": sys.argv,
            "pid": os.getpid(), "scope": "Python harness controls; no MIPS compiler or QEMU execution",
            "retention": "Generated fixtures and logs are retained for regression diagnosis; no checkout copied",
            "source_fingerprints": cls.inputs_before,
        })
        cls.addClassCleanup(cls.seal_workspace)
        print(f"MIPS harness Python test evidence: {cls.workspace}", flush=True)

    @classmethod
    def seal_workspace(cls):
        try:
            after = harness.fingerprint(cls.input_sources, ROOT)
            harness.write_json(cls.workspace / "inputs-after.json", after)
            harness.write_json(cls.workspace / "source-stability.json", {
                "sources_stable": cls.inputs_before == after,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "Input stability only; unittest reports assertion outcomes",
            })
        finally:
            harness.Evidence(cls.workspace, dict(os.environ), 10).seal()
        if cls.inputs_before != after:
            raise AssertionError("Harness test sources changed during validation")

    def setUp(self):
        self.directory = self.workspace / self._testMethodName
        self.directory.mkdir(exist_ok=False)
        self.transcript = io.StringIO()
        harness.write_json(self.directory / "provenance.json", {
            "test_id": self.id(), "source_project": str(ROOT),
            "suite_provenance": "../provenance.json",
            "scope": "Synthetic ELF/data, optional read-only official sysroot ELF inspection and mocked compiler/main; only Python subprocesses execute",
        })
        self.addCleanup(self.seal_fixtures)
        self.enterContext(contextlib.redirect_stdout(self.transcript))
        self.enterContext(contextlib.redirect_stderr(self.transcript))

    def seal_fixtures(self):
        with (self.directory / "diagnostics.log").open("x", encoding="utf-8") as stream:
            stream.write(self.transcript.getvalue())
        harness.Evidence(self.directory, dict(os.environ), 10).seal()

    @staticmethod
    def elf_image(abi=None, flags=0x70001007):
        abi = abi or (0, 32, 2, 1, 1, 0, 1, 0, 0, 1, 0)
        section_offset = 52
        program_offset = section_offset + 2 * 40
        abi_offset = program_offset + 32
        interpreter_offset = abi_offset + 24
        identification = b"\x7fELF\x01\x01\x01" + bytes(9)
        header = struct.pack("<HHIIIIIHHHHHH", 2, 8, 1, 0x400000, program_offset,
                             section_offset, flags, 52, 32, 1, 40, 2, 0)
        section = struct.pack("<IIIIIIIIII", 0, 0x7000002a, 0, 0, abi_offset, 24, 0, 0, 8, 0)
        interpreter = b"/lib/ld.so.1\0"
        program = struct.pack("<IIIIIIII", 3, interpreter_offset, 0, 0,
                              len(interpreter), len(interpreter), 4, 1)
        return (identification + header + bytes(40) + section + program
                + struct.pack("<HBBBBBBIIII", *abi) + interpreter)

    def write_elf(self, name, image):
        path = self.directory / (name + ".elf")
        with path.open("xb") as stream:
            stream.write(image)
        return path

    @staticmethod
    def engine_output():
        rows = [f"PCM {language} {rate} {punctuation} 100 {rate + punctuation}"
                for language in ("pl", "en") for rate in (80, 175, 450, 451, 1350)
                for punctuation in range(4)]
        return "\n".join(rows + ["HEAP capacity=1572864 used=10000 peak=1500000 failures=1",
                                 harness.PASS_ENGINE])

    def test_elf_rejects_wrong_architecture_float_and_loader(self):
        valid = self.elf_image()
        self.assertEqual(harness.elf_abi(self.write_elf("valid", valid))["interpreter"], "/lib/ld.so.1")
        mutations = {}
        for name, flags in (("mips16", 0x74001007), ("wrong-isa", 0x50001007),
                            ("wrong-o32", 0x70002007), ("micromips", 0x72001007)):
            image = bytearray(valid)
            struct.pack_into("<I", image, 36, flags)
            mutations[name] = image
        for name, offset, value in (("big-endian", 5, 2), ("wrong-machine", 18, 3),
                                    ("wrong-loader", 188, 88)):
            image = bytearray(valid)
            image[offset] = value
            mutations[name] = image
        mutations.update({"soft-float": self.elf_image((0, 32, 2, 1, 0, 0, 3, 0, 0, 1, 0)),
                          "fp64": self.elf_image((0, 32, 2, 1, 2, 0, 6, 0, 0, 1, 0)),
                          "truncated": valid[:100]})
        for name, image in mutations.items():
            with self.subTest(case=name), self.assertRaises((RuntimeError, struct.error)):
                harness.elf_abi(self.write_elf(name, image))
        fpxx = self.write_elf("fpxx", self.elf_image((0, 32, 2, 1, 0, 0, 5, 0, 0, 1, 0)))
        harness.elf_abi(fpxx, executable=False)
        with self.assertRaises(RuntimeError):
            harness.elf_abi(fpxx)

    def test_runtime_accepts_compatible_isa_without_relaxing_application(self):
        for architecture, flags, level, revision in (("MIPS1", 0x1007, 1, 0),
                                                     ("MIPS32", 0x50001007, 32, 1),
                                                     ("MIPS32r2", 0x70001007, 32, 2)):
            for fp_abi, cpr1 in ((1, 1), (5, 0), (5, 1)):
                with self.subTest(architecture=architecture, fp_abi=fp_abi, cpr1=cpr1):
                    abi = (0, level, revision, 1, cpr1, 0, fp_abi, 0, 0, 0, 0)
                    path = self.write_elf(f"{architecture}-fp{fp_abi}-cpr{cpr1}",
                                          self.elf_image(abi, flags))
                    result = harness.elf_abi(path, executable=False)
                    self.assertTrue(result["architecture"].startswith(architecture + " "))
                    self.assertEqual(result["abi_contract"], "runtime-compatible")
                    self.assertEqual(result["mips_abi_flags"], list(abi))
                    if architecture == "MIPS32r2" and fp_abi == 1:
                        self.assertEqual(harness.elf_abi(path)["abi_contract"], "application-exact")
                    else:
                        with self.assertRaises(RuntimeError):
                            harness.elf_abi(path)

    def test_runtime_rejects_incompatible_elf_and_float_abis(self):
        valid_abi = (0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0)
        valid = self.elf_image(valid_abi, 0x1007)
        mutations = {}
        for name, flags in (("mips64", 0x60001007), ("mips64r2", 0x80001007),
                            ("mips32r6", 0x90001007), ("abi2", 0x1027),
                            ("missing-o32", 7), ("n64", 0x2007),
                            ("mips16", 0x04001007), ("micromips", 0x02001007),
                            ("fp64-flag", 0x1207), ("nan2008", 0x1407),
                            ("header-isa-mismatch", 0x70001007)):
            image = bytearray(valid)
            struct.pack_into("<I", image, 36, flags)
            mutations[name] = image
        for name, offset, value in (("elf64", 4, 2), ("big-endian", 5, 2),
                                    ("wrong-machine", 18, 3)):
            image = bytearray(valid)
            image[offset] = value
            mutations[name] = image
        for name, index, value in (("abi-version", 0, 1), ("abi-isa-mismatch", 1, 32),
                                   ("abi-revision-mismatch", 2, 2), ("gpr64", 3, 2),
                                   ("cpr64", 4, 2), ("missing-cpr1", 4, 0),
                                   ("cpr2", 5, 1), ("unspecified-float", 6, 0),
                                   ("single-float", 6, 2), ("soft-float", 6, 3),
                                   ("old-fp64", 6, 4), ("fp64", 6, 6), ("fp64a", 6, 7),
                                   ("isa-extension", 7, 1), ("mips16-ase", 8, 0x400),
                                   ("micromips-ase", 8, 0x800)):
            abi = list(valid_abi)
            abi[index] = value
            mutations[name] = self.elf_image(abi, 0x1007)
        for name, image in mutations.items():
            with self.subTest(case=name), self.assertRaises(RuntimeError):
                harness.elf_abi(self.write_elf(name, image), executable=False)

    def test_official_sysroot_loader_is_read_only_and_runtime_compatible(self):
        sysroot = (self.central / "toolchains/hiby-r1-20261010/prefix"
                   / "mipsel-rockbox-linux-gnu/sysroot")
        loader = sysroot / "lib/ld-2.27.so"
        if not loader.is_file():
            self.skipTest("Official provisioned sysroot is unavailable; synthetic ABI controls still run")
        records = {}
        try:
            for name in ("ld-2.27.so", "libc-2.27.so", "libm-2.27.so", "libpthread-2.27.so"):
                with self.subTest(library=name):
                    path = (sysroot / "lib" / name).resolve(strict=True)
                    self.assertIn(sysroot.resolve(), path.parents)
                    before = harness.digest(path)
                    result = harness.elf_abi(path, executable=False)
                    records[name] = {"path": str(path), "sha256_before": before,
                                     "sha256_after": harness.digest(path), "abi": result,
                                     "scope": "Read-only actual official sysroot; no compiler/QEMU execution"}
                    self.assertEqual(before, records[name]["sha256_after"])
                    self.assertEqual(result["sha256"], before)
                    self.assertEqual(result["elf_flags"], "0x1007")
                    self.assertEqual(result["mips_abi_flags"], [0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0])
                    self.assertEqual(result["abi_contract"], "runtime-compatible")
                    self.assertTrue(result["architecture"].startswith("MIPS1 "))
                    with self.assertRaisesRegex(RuntimeError, "Expected MIPS32r2 O32"):
                        harness.elf_abi(path)
        finally:
            harness.write_json(self.directory / "read-only-sysroot.json", records)

    def test_pcm_requires_all_unique_cases_and_valid_heap(self):
        good = self.engine_output()
        self.assertEqual(len(harness.parse_engine(good)["pcm"]), 40)
        invalid = {
            "missing-case": good.replace("PCM pl 80 0 100 80\n", ""),
            "duplicate-case": good + "\nPCM pl 80 0 100 80",
            "empty-pcm": good.replace("PCM pl 80 0 100", "PCM pl 80 0 0"),
            "missing-pass": good.replace(harness.PASS_ENGINE, ""),
            "impossible-heap": good.replace("capacity=1572864", "capacity=1"),
            "no-allocation-failure": good.replace("failures=1", "failures=0"),
        }
        harness.write_json(self.directory / "pcm-fixtures.json", {"valid": good, **invalid})
        for name, output in invalid.items():
            with self.subTest(case=name), self.assertRaises(RuntimeError):
                harness.parse_engine(output)

    def test_dependency_and_version_requirements(self):
        path = self.write_elf("inspection", self.elf_image())
        dependencies = ["libc.so.6", "libm.so.6"]
        requirement = "GLIBC_2.16"
        symbols = ""
        records = []

        def readelf(arguments, **kwargs):
            output = ""
            if "-d" in arguments:
                output = "\n".join(f" (NEEDED) Shared library: [{name}]" for name in dependencies)
            elif "-V" in arguments:
                output = ("Version definition section\n Name: GLIBC_2.27\n"
                          "Version needs section\n Name: " + requirement)
            elif "-s" in arguments:
                output = symbols
            records.append({"argv": list(map(str, arguments)), "label": kwargs["label"],
                            "stdout": output, "executed": False})
            return output

        evidence = mock.Mock(command=mock.Mock(side_effect=readelf))
        result = harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "fixture")
        self.assertEqual(result["glibc_requirements"], ["GLIBC_2.16"])
        for requirement in ("GLIBC_2.17", "GLIBC_PRIVATE"):
            with self.subTest(requirement=requirement), self.assertRaises(RuntimeError):
                harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "fixture")
        requirement = "GLIBC_2.16"
        for dependency in ("libstdc++.so.6", "libatomic.so.1"):
            dependencies = ["libc.so.6", dependency]
            with self.subTest(dependency=dependency), self.assertRaises(RuntimeError):
                harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "fixture")
        dependencies = ["libc.so.6"]
        symbols = " 1: 0 0 FUNC GLOBAL DEFAULT UND __atomic_exchange_4"
        with self.assertRaises(RuntimeError):
            harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "fixture")
        symbols = " 1: 0 0 FUNC WEAK DEFAULT UND __cxa_finalize@GLIBC_2.16"
        harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "fixture")
        path = self.write_elf("runtime-inspection", self.elf_image(
            (0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0), 0x1007))
        requirement = "GLIBC_2.16\n Name: GLIBC_PRIVATE"
        result = harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "runtime", library=True)
        self.assertEqual(result["glibc_requirements"], ["GLIBC_2.16", "GLIBC_PRIVATE"])
        requirement = "GLIBC_2.17\n Name: GLIBC_PRIVATE"
        with self.assertRaisesRegex(RuntimeError, "GLIBC requirements exceed 2.16"):
            harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "runtime", library=True)
        requirement = "GLIBC_2.16\n Name: GLIBC_PRIVATE"
        for dependency in ("libstdc++.so.6", "libatomic.so.1"):
            dependencies = ["libc.so.6", dependency]
            with self.subTest(runtime_dependency=dependency), self.assertRaises(RuntimeError):
                harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "runtime", library=True)
        dependencies = ["libc.so.6"]
        for symbol in ("__atomic_exchange_4", "__cxa_throw", "__gxx_personality_v0", "_Znwm"):
            symbols = " 1: 0 0 FUNC GLOBAL DEFAULT UND " + symbol
            with self.subTest(runtime_symbol=symbol), self.assertRaises(RuntimeError):
                harness.inspect_elf(evidence, {"readelf": "readelf"}, path, "runtime", library=True)
        harness.write_json(self.directory / "readelf-fixtures.json", records)

    def test_gcc_only_and_shared_hosted_builder(self):
        runtime = harness.load_test("test_espeak_native_runtime")
        with mock.patch.dict(sys.modules, test_espeak_native_runtime=runtime):
            hosted = harness.load_test("test_espeak_hosted_runtime")
        evidence = mock.Mock()
        compiler = self.directory / "mipsel-rockbox-linux-gnu-gcc"
        with mock.patch.object(harness, "load_test", side_effect=(runtime, hosted)), \
                mock.patch.object(runtime, "build_runtime", return_value=[self.directory / "mock.o"]) as builder:
            probes = harness.build_probes(evidence, {"gcc": compiler}, self.directory)
            builder.assert_called_once_with(self.directory / "runtime", harness.FLAGS,
                                            compiler=compiler, hosted=True)
        self.assertEqual(set(probes), {"runtime", "hosted", "engine"})
        commands = [invocation.args[0] for invocation in evidence.command.call_args_list]
        harness.write_json(self.directory / "compiler-fixtures.json", {
            "executed": False, "commands": [list(map(str, command)) for command in commands]})
        for arguments in commands:
            self.assertEqual(arguments[0], compiler)
            for flag in harness.FLAGS:
                self.assertIn(flag, arguments)
        generated = (self.directory / "runtime-probe.c").read_text(encoding="utf-8")
        self.assertIn("mock_irq_transitions == 0", generated)
        self.assertNotIn("mock_irq_transitions == 8", generated)
        self.assertTrue(any("-x" in command and "c++" in command for command in commands))
        self.assertTrue(any("-pthread" in command for command in commands))
        native_commands = [command for command in commands if "-DRB_ESPEAK_NATIVE=1" in command]
        self.assertEqual(len(native_commands), len(harness.ENGINE_NAMES) + 2)
        for arguments in native_commands:
            self.assertIn("-I" + str(harness.ESPEAK / "native/include"), arguments)
            self.assertIn("-DRB_ESPEAK_HAVE_SONIC=1", arguments)
        self.assertTrue(any(harness.ESPEAK / "sonic/sonic.c" in command for command in native_commands))

    def test_missing_tools_never_launch_a_process(self):
        arguments = mock.Mock(toolchain_bin=self.directory, qemu=sys.executable)
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(harness.shutil, "which", return_value=str(Path(sys.executable).resolve())), \
                mock.patch.object(harness.subprocess, "run") as process:
            with self.assertRaisesRegex(RuntimeError, "Missing executable gcc"):
                harness.available_tools(arguments)
            process.assert_not_called()

    def test_command_failure_timeout_and_integrity(self):
        directory = self.directory / "python-commands"
        directory.mkdir()
        evidence = harness.Evidence(directory, dict(os.environ), 10)
        output = evidence.command([sys.executable, "-B", "-c",
                                   'import sys; print("output"); print("error", file=sys.stderr)'],
                                  label="python-io")
        self.assertEqual(output, "output\n")
        self.assertEqual((directory / "commands/0001-python-io/stderr.log").read_text(), "error\n")
        with self.assertRaises(RuntimeError):
            evidence.command([sys.executable, "-B", "-c", "raise SystemExit(7)"], label="python-fail")
        evidence.timeout = 0.1
        with self.assertRaises(RuntimeError):
            evidence.command([sys.executable, "-B", "-c", "import time; time.sleep(5)"], label="python-timeout")
        failed = directory / "commands/0002-python-fail/result.json"
        self.assertEqual(json.loads(failed.read_text())["returncode"], 7)
        self.assertIn("error", json.loads((directory / "commands/0003-python-timeout/result.json").read_text()))
        with self.assertRaises(FileExistsError):
            harness.write_json(failed, {})
        evidence.seal()
        manifest = json.loads((directory / "integrity.json").read_text())
        for name, details in manifest.items():
            self.assertEqual(harness.digest(directory / name), details["sha256"])
        self.assertFalse((directory / "integrity.json").stat().st_mode & stat.S_IWUSR)

    def test_freeze_failure_and_failed_build_are_sealed(self):
        data_parent = self.directory / "synthetic-data"
        data = data_parent / "espeak-data"
        data.mkdir(parents=True)
        for name in ("phondata", "phonindex", "phontab", "intonations"):
            with (data / name).open("xb") as stream:
                stream.write(b"Python control fixture; not usable synthesis data.\n")
        for changed in (False, True):
            with self.subTest(changed=changed):
                central = self.directory / ("changed-inputs" if changed else "failed-build")
                central.mkdir()
                resolver = materials_resolver(self.directory / "source", central)
                before = {"sources": {"fixture": {"sha256": "before"}}}
                after = {"sources": {"fixture": {"sha256": "after" if changed else "before"}}}

                def simulate(evidence, tools, parent, report):
                    self.assertEqual(parent, data_parent.resolve())
                    report["sysroot"] = str(central)
                    report["scope"] = "PYTHON HARNESS CONTROL FIXTURE; NO MIPS EXECUTION"
                    harness.write_json(evidence.directory / "inputs-before.json", before)
                    if not changed:
                        raise RuntimeError("simulated build failure")
                    report["passed"] = True

                tools = {name: Path(sys.executable) for name in ("gcc", "readelf", "qemu")}
                with mock.patch.object(harness, "available_tools", return_value=tools), \
                        mock.patch.object(harness, "execute_smoke", side_effect=simulate), \
                        mock.patch.object(harness, "input_fingerprint", return_value=after), \
                        mock.patch.object(project_materials, "project_materials_root", side_effect=resolver), \
                        mock.patch.object(project_materials, "ensure_ignored_directories"), \
                        mock.patch.object(sys, "dont_write_bytecode", sys.dont_write_bytecode), \
                        mock.patch.object(sys, "path", list(sys.path)):
                    result = harness.main(["--toolchain-bin", str(central), "--data-parent", str(data_parent)])
                self.assertEqual(result, 1)
                runs = list((resolver(ROOT) / "espeak-hiby-mips").iterdir())
                self.assertEqual(len(runs), 1)
                directory = runs[0]
                report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
                self.assertFalse(report["passed"])
                self.assertEqual(report["sources_frozen"], not changed)
                self.assertTrue((directory / "inputs-after.json").is_file())
                self.assertTrue((directory / "integrity.json").is_file())
                if changed:
                    self.assertEqual(report["changed_inputs"]["sources"], ["fixture"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
