"""Validate the actual private Bluetooth preferences using isolated real files."""

import errno
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/hiby_bluetooth_settings.c"
HEADER = SOURCE.with_suffix(".h")
FIXTURE = ROOT / "tools/tests/fixtures/hiby_bluetooth_settings_fixture.c"
DEFAULTS = b"RBBLUETOOTH:1\nauto:2\nretry:120\npause:1\nannounce:1\nlast:\n"
PEER = "AA:BB:CC:DD:EE:FF"


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX fault-injection fixture; run under WSL")
class HibyBluetoothSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable")
        central = project_materials_root(ROOT)
        cls.area = confined_path(central / "r1-bluetooth-completion-20261020/capabilities-audit/policy-implementation" /
                                 ("preferences-" + uuid.uuid4().hex), central)
        cls.area.mkdir(parents=True)
        cls.commands = []
        cls.case_results = []
        cls.addClassCleanup(cls.report)
        cls.executables = {}
        for variant in ("native", "simulator", "ubsan"):
            binary = cls.area / variant
            arguments = [*cls.compiler, "-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic-errors",
                         "-O1", "-g", "-pthread", "-DHIBY_BT_SETTINGS_HOST_TEST", '-DROCKBOX_DIR="."',
                         "-I", str(ROOT / "apps"), str(FIXTURE), "-o", str(binary)]
            if variant == "simulator":
                arguments += ["-DSIMULATOR"]
            if variant == "ubsan":
                arguments += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            cls.command(arguments, cls.area)
            cls.executables[variant] = binary
            symbols = cls.command(["nm", "-u", str(binary)], cls.area).stdout
            imports = {line.split()[-1].split("@")[0] for line in symbols.splitlines() if line.split()}
            forbidden = imports & {"system", "fork", "execve", "posix_spawn", "socket", "ioctl"}
            if forbidden:
                raise AssertionError(f"Forbidden radio/process imports: {forbidden}")
        print("Bluetooth preferences evidence:", cls.area, flush=True)

    @classmethod
    def command(cls, arguments, directory):
        result = subprocess.run(arguments, cwd=directory, capture_output=True, text=True, timeout=45)
        cls.commands.append(dict(argv=arguments, cwd=str(directory), returncode=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result

    @classmethod
    def report(cls):
        (cls.area / "report.json").write_text(json.dumps(dict(
            commands=cls.commands, cases=cls.case_results, hardware_tested=False,
            inputs={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (SOURCE, HEADER, FIXTURE, Path(__file__), ROOT / "apps/bluetooth_policy.h")}),
            indent=2), encoding="utf-8")

    def runtime(self, content=None):
        directory = self.area / (self._testMethodName + "-" + uuid.uuid4().hex[:8])
        directory.mkdir()
        if content is not None:
            (directory / "bluetooth.cfg").write_bytes(content)
        return directory

    def execute(self, directory, *arguments, variant="native"):
        result = self.command([str(self.executables[variant]), *map(str, arguments)], directory)
        observed = json.loads(result.stdout)
        self.case_results.append(dict(test=self.id(), variant=variant, directory=str(directory), result=observed))
        return observed

    def assert_defaults(self, observed, error=0):
        self.assertEqual({key: observed[key] for key in ("error", "auto", "retry", "pause", "announce", "peer")},
                         dict(error=error, auto=2, retry=120, pause=1, announce=1, peer=""))

    def test_missing_file_defaults_and_nulls(self):
        for variant in self.executables:
            directory = self.runtime()
            self.assert_defaults(self.execute(directory, "read", variant=variant))
            self.assert_defaults(self.execute(directory, "null", variant=variant))
            self.assertFalse((directory / "bluetooth.cfg").exists())

    def test_actual_persistence_merge_remember_forget_and_generation(self):
        for variant in self.executables:
            directory = self.runtime()
            result = self.execute(directory, "set", 0, 1, variant=variant)
            self.assertEqual((result["error"], result["auto"], result["generation"]), (0, 1, 1))
            self.execute(directory, "set", 1, 300, variant=variant)
            self.execute(directory, "set", 2, 0, variant=variant)
            self.execute(directory, "set", 3, 0, variant=variant)
            result = self.execute(directory, "remember", PEER.lower(), variant=variant)
            self.assertEqual((result["auto"], result["retry"], result["pause"], result["announce"], result["peer"]),
                             (1, 300, 0, 0, PEER))
            persisted = (directory / "bluetooth.cfg").read_bytes()
            self.assertEqual(persisted, b"RBBLUETOOTH:1\nauto:1\nretry:300\npause:0\nannounce:0\nlast:" + PEER.encode() + b"\n")
            result = self.execute(directory, "forget", "11:22:33:44:55:66", variant=variant)
            self.assertEqual(result["peer"], PEER)
            self.assertEqual((directory / "bluetooth.cfg").read_bytes(), persisted)
            result = self.execute(directory, "forget", PEER.lower(), variant=variant)
            self.assertEqual(result["peer"], "")
            self.assertEqual((result["auto"], result["retry"], result["pause"], result["announce"]), (1, 300, 0, 0))
            self.assertEqual(result["requested_mode"], 0o600)

    def test_strict_corruption_rejects_without_repairing(self):
        corruptions = [b"", DEFAULTS[:-1], DEFAULTS + b"x", DEFAULTS + b"\x00", b"x" * 200,
                       DEFAULTS.replace(b":1\n", b":2\n", 1), DEFAULTS.replace(b"auto:2", b"auto:3"),
                       DEFAULTS.replace(b"auto:2", b"auto:-1"), DEFAULTS.replace(b"auto:2", b"auto:02"),
                       DEFAULTS.replace(b"retry:120", b"retry:121"), DEFAULTS.replace(b"retry:120", b"retry:42949672960"),
                       DEFAULTS.replace(b"pause:1", b"pause:2"), DEFAULTS.replace(b"announce:1", b"announce:2"),
                       DEFAULTS.replace(b"last:\n", b"last:aa:bb:cc:dd:ee:ff\n"),
                       DEFAULTS.replace(b"last:\n", b"last:GG:BB:CC:DD:EE:FF\n"),
                       DEFAULTS.replace(b"last:\n", b"last:AA:BB:CC:DD:EE\n"),
                       DEFAULTS.replace(b"\n", b"\r\n"), DEFAULTS.replace(b"auto:2", b"auto: 2"),
                       DEFAULTS.replace(b"auto:2", b"auto:2\x00")]
        for variant in ("native", "ubsan"):
            for content in corruptions:
                with self.subTest(content=content, variant=variant):
                    directory = self.runtime(content)
                    self.assert_defaults(self.execute(directory, "read", variant=variant), errno.EINVAL)
                    self.assertEqual(self.execute(directory, "set", 0, 1, variant=variant)["error"], errno.EINVAL)
                    self.assertEqual((directory / "bluetooth.cfg").read_bytes(), content)
                    self.assertFalse((directory / "bluetooth.cfg.tmp").exists())

    def test_values_and_addresses_validate_before_writing(self):
        directory = self.runtime(DEFAULTS)
        for preference, value in ((-1, 1), (4, 1), (0, -1), (0, 3), (1, 0), (1, 121), (2, 2), (3, -1)):
            self.assertEqual(self.execute(directory, "set", preference, value)["error"], errno.EINVAL)
        for address in ("", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:FFx", "AA-BB-CC-DD-EE-FF", "ZZ:BB:CC:DD:EE:FF"):
            for operation in ("remember", "forget"):
                self.assertEqual(self.execute(directory, operation, address)["error"], errno.EINVAL)
        self.assertEqual((directory / "bluetooth.cfg").read_bytes(), DEFAULTS)

    def test_failures_preserve_prior_file_and_memory(self):
        original = DEFAULTS.replace(b"retry:120", b"retry:30")
        failures = [(operation, 1, 0, errno.EIO) for operation in range(1, 9)]
        failures += [(operation, 2, 10, errno.EINTR) for operation in range(1, 8)]
        failures += [(4, 3, 0, errno.EIO), (3, 3, 0, errno.EINVAL), (4, 5, 0, errno.EIO)]
        for operation, mode, budget, expected in failures:
            with self.subTest(operation=operation, mode=mode, budget=budget):
                directory = self.runtime()
                result = self.execute(directory, "fault", operation, mode, budget)
                self.assertEqual(result["error"], expected)
                self.assertEqual((directory / "bluetooth.cfg").read_bytes(), original)
                self.assertFalse((directory / "bluetooth.cfg.tmp").exists())
                if mode == 2:
                    self.assertLessEqual(result["fault_calls"], 4)

    def test_short_io_and_bounded_interruption_recovery(self):
        for operation, mode, budget in ((3, 4, 0), (4, 4, 0), (1, 2, 1), (2, 2, 1),
                                        (3, 2, 1), (4, 2, 1), (5, 2, 1)):
            directory = self.runtime()
            result = self.execute(directory, "fault", operation, mode, budget)
            self.assertEqual(result["error"], 0)
            self.assertEqual(result["announce"], 0)
            self.assertEqual(self.execute(directory, "read")["announce"], 0)

    def test_stale_temp_is_never_deleted_and_owned_cleanup_error_is_reported(self):
        directory = self.runtime(DEFAULTS)
        (directory / "bluetooth.cfg.tmp").write_bytes(b"unowned-stale-content")
        result = self.execute(directory, "set", 3, 0)
        self.assertEqual(result["error"], errno.EEXIST)
        self.assertEqual((directory / "bluetooth.cfg").read_bytes(), DEFAULTS)
        self.assertEqual((directory / "bluetooth.cfg.tmp").read_bytes(), b"unowned-stale-content")
        directory = self.runtime()
        self.assertEqual(self.execute(directory, "noop-remove-fault")["error"], errno.EIO)
        self.assertTrue((directory / "bluetooth.cfg.tmp").exists())
        self.assertEqual(self.execute(directory, "set", 3, 0)["error"], errno.EEXIST)

    def test_concurrent_option_and_peer_changes_remain_merged(self):
        for variant in ("native", "ubsan"):
            result = self.execute(self.runtime(), "concurrent", variant=variant)
            self.assertEqual((result["error"], result["auto"], result["retry"], result["peer"]), (0, 1, 300, PEER))
            self.assertEqual((result["pause"], result["announce"]), (0, 0))

    def test_storage_error_survives_reads_until_a_successful_explicit_save(self):
        for variant in self.executables:
            for scenario in ("sticky-read-error", "sticky-remember-error"):
                with self.subTest(variant=variant, scenario=scenario):
                    directory = self.runtime()
                    result = self.execute(directory, scenario, variant=variant)
                    self.assertEqual(result["error"], 0)
                    self.assertEqual(self.execute(directory, "read", variant=variant)["retry"], 30)

    def test_one_initial_load_then_one_thousand_memory_only_getters(self):
        for variant in self.executables:
            for content in (None, DEFAULTS, b"malformed"):
                with self.subTest(variant=variant, content=content):
                    result = self.execute(self.runtime(content), "cached-get", variant=variant)
                    self.assertEqual(result["error"], errno.EINVAL if content == b"malformed" else 0)
                    self.assertEqual(result["read_opens"], 1)
                    self.assertEqual(result["read_closes"], 0 if content is None else 1)
                    self.assertEqual(result["reads"], 0 if content is None else 2)

    def test_explicit_update_merges_fresh_disk_without_polling_external_edits(self):
        for variant in self.executables:
            result = self.execute(self.runtime(), "cached-external-edit", variant=variant)
            self.assertEqual((result["error"], result["auto"], result["retry"], result["peer"]), (0, 1, 30, PEER))
            self.assertEqual((result["pause"], result["announce"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
