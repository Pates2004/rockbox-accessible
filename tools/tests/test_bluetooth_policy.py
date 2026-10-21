"""Run the actual portable reconnect policy and its integer boundary cases."""

import ctypes
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
SOURCE = ROOT / "apps/bluetooth_policy.c"
HEADER = SOURCE.with_suffix(".h")
FIXTURE = ROOT / "tools/tests/fixtures/bluetooth_policy_fixture.c"
MAXIMUM = (1 << 63) - 1


class Policy(ctypes.Structure):
    _fields_ = [("active", ctypes.c_bool), ("attempts", ctypes.c_uint),
                ("deadline_ms", ctypes.c_int64), ("next_attempt_ms", ctypes.c_int64),
                ("last_now_ms", ctypes.c_int64)]


class BluetoothPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable")
        central = project_materials_root(ROOT)
        cls.area = confined_path(central / "r1-bluetooth-completion-20261020/capabilities-audit/policy-implementation" /
                                 ("policy-" + uuid.uuid4().hex), central)
        cls.area.mkdir(parents=True)
        cls.commands = []
        cls.results = []
        cls.addClassCleanup(cls.report)
        binary = cls.area / ("policy.dll" if os.name == "nt" else "policy.so")
        cls.flags = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic-errors", "-O1", "-g",
                     "-I", str(ROOT / "apps")]
        platform_flags = [] if os.name == "nt" else ["-fPIC"]
        cls.run_command([*cls.compiler, *cls.flags, "-shared", *platform_flags, str(SOURCE), "-o", str(binary)])
        cls.library = ctypes.CDLL(str(binary))
        cls.begin = cls.library.bluetooth_reconnect_begin
        cls.begin.argtypes = [ctypes.POINTER(Policy), ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_int64]
        cls.begin.restype = None
        cls.stop = cls.library.bluetooth_reconnect_stop
        cls.stop.argtypes = [ctypes.POINTER(Policy)]
        cls.stop.restype = None
        cls.due = cls.library.bluetooth_reconnect_due
        cls.due.argtypes = [ctypes.POINTER(Policy), ctypes.c_int64]
        cls.due.restype = ctypes.c_bool
        cls.remaining = cls.library.bluetooth_reconnect_remaining
        cls.remaining.argtypes = cls.due.argtypes
        cls.remaining.restype = ctypes.c_int
        cls.attempted = cls.library.bluetooth_reconnect_attempted
        cls.attempted.argtypes = [ctypes.POINTER(Policy), ctypes.c_int64, ctypes.c_bool]
        cls.attempted.restype = None
        print("Bluetooth policy evidence:", cls.area, flush=True)

    @classmethod
    def run_command(cls, arguments):
        result = subprocess.run(arguments, cwd=cls.area, capture_output=True, text=True, timeout=45)
        cls.commands.append(dict(argv=arguments, returncode=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result

    @classmethod
    def report(cls):
        (cls.area / "report.json").write_text(json.dumps(dict(
            commands=cls.commands, cases=cls.results, hardware_tested=False,
            inputs={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (SOURCE, HEADER, FIXTURE, Path(__file__))}), indent=2), encoding="utf-8")

    def tearDown(self):
        self.results.append(self.id())

    def fresh(self, reason=0, mode=2, seconds=120, now=100):
        policy = Policy()
        self.begin(ctypes.byref(policy), reason, mode, seconds, now)
        return policy

    def test_mode_reason_matrix_and_finite_windows(self):
        for mode in range(3):
            for reason in range(2):
                for seconds in (30, 60, 120, 300):
                    with self.subTest(mode=mode, reason=reason, seconds=seconds):
                        policy = self.fresh(reason, mode, seconds)
                        allowed = mode == 2 or mode == 1 and reason == 0
                        self.assertEqual(policy.active, allowed)
                        self.assertEqual(self.due(ctypes.byref(policy), 100), allowed)
                        self.assertEqual(self.remaining(ctypes.byref(policy), 100), seconds * 1000 if allowed else 0)

    def test_exact_backoff_and_eight_attempt_cap(self):
        policy = self.fresh(seconds=300, now=0)
        expected = (0, 2000, 6000, 14000, 30000, 60000, 90000, 120000)
        for count, now in enumerate(expected, 1):
            self.assertTrue(self.due(ctypes.byref(policy), now))
            self.attempted(ctypes.byref(policy), now, False)
            self.assertEqual(policy.attempts, count)
            if count < 8:
                self.assertEqual(policy.next_attempt_ms, expected[count])
                self.assertFalse(self.due(ctypes.byref(policy), expected[count] - 1))
        self.assertFalse(policy.active)
        self.assertFalse(self.due(ctypes.byref(policy), 200000))

    def test_deadline_boundary_and_late_success(self):
        policy = self.fresh(seconds=30, now=0)
        self.assertEqual(self.remaining(ctypes.byref(policy), 29999), 1)
        self.attempted(ctypes.byref(policy), 30000, True)
        self.assertFalse(policy.active)
        self.assertEqual(policy.attempts, 0)
        self.assertEqual(self.remaining(ctypes.byref(policy), 30001), 0)

    def test_repeated_begin_does_not_extend_or_reset(self):
        policy = self.fresh(now=0)
        self.attempted(ctypes.byref(policy), 0, False)
        self.begin(ctypes.byref(policy), 1, 2, 300, 1000)
        self.assertEqual((policy.deadline_ms, policy.next_attempt_ms, policy.attempts), (120000, 2000, 1))
        self.begin(ctypes.byref(policy), 0, 2, 120, 120000)
        self.assertFalse(policy.active)
        self.assertEqual(policy.deadline_ms, 120000)

    def test_clock_failure_backwards_on_every_entry(self):
        for operation in (self.due, self.remaining, self.attempted, self.begin):
            for invalid in (-1, 99, -(1 << 63)):
                with self.subTest(operation=operation.__name__, invalid=invalid):
                    policy = self.fresh(now=100)
                    if operation is self.attempted:
                        operation(ctypes.byref(policy), invalid, False)
                    elif operation is self.begin:
                        operation(ctypes.byref(policy), 0, 2, 120, invalid)
                    else:
                        operation(ctypes.byref(policy), invalid)
                    self.assertFalse(policy.active)

    def test_success_stop_no_early_duplicate_attempt(self):
        policy = self.fresh(now=0)
        self.attempted(ctypes.byref(policy), 0, False)
        self.attempted(ctypes.byref(policy), 1, False)
        self.assertEqual(policy.attempts, 1)
        self.attempted(ctypes.byref(policy), 2000, True)
        self.assertFalse(policy.active)
        self.assertEqual(policy.attempts, 2)
        self.assertEqual(self.remaining(ctypes.byref(policy), 2001), 0)
        self.stop(ctypes.byref(policy))

    def test_invalid_parameters_stop_without_integer_wrap(self):
        for reason, mode, seconds in ((-1, 2, 120), (2, 2, 120), (0, -1, 120),
                                       (0, 3, 120), (0, 2, 0), (0, 2, 31), (0, 2, (1 << 32) - 1)):
            with self.subTest(reason=reason, mode=mode, seconds=seconds):
                policy = self.fresh(now=0)
                self.begin(ctypes.byref(policy), reason, mode, seconds, 0)
                self.assertFalse(policy.active)

    def test_saturation_near_int64_max_and_null_safety(self):
        policy = self.fresh(seconds=300, now=MAXIMUM - 10)
        self.assertEqual(policy.deadline_ms, MAXIMUM)
        self.assertEqual(self.remaining(ctypes.byref(policy), MAXIMUM - 10), 10)
        self.attempted(ctypes.byref(policy), MAXIMUM - 10, False)
        self.assertEqual(policy.next_attempt_ms, MAXIMUM)
        self.assertFalse(self.due(ctypes.byref(policy), MAXIMUM))
        self.assertFalse(self.fresh(now=MAXIMUM).active)
        self.begin(None, 0, 2, 120, 0)
        self.stop(None)
        self.attempted(None, 0, False)
        self.assertFalse(self.due(None, 0))
        self.assertEqual(self.remaining(None, 0), 0)

    def test_waiting_never_moves_deadline_or_implicitly_starts_again(self):
        policy = self.fresh(seconds=30, now=0)
        for now in (0, 2000, 6000, 14000):
            self.attempted(ctypes.byref(policy), now, False)
        self.assertTrue(policy.active)
        self.assertEqual(policy.next_attempt_ms, 30000)
        self.assertEqual(self.remaining(ctypes.byref(policy), 29999), 1)
        self.assertFalse(self.due(ctypes.byref(policy), 30000))
        self.assertFalse(self.due(ctypes.byref(policy), 30001))
        self.assertEqual(policy.deadline_ms, 30000)

    @unittest.skipUnless(sys.platform.startswith("linux"), "UBSan fixture requires Linux compiler")
    def test_sanitized_real_timeline_stress(self):
        executable = self.area / "policy-ubsan"
        self.run_command([*self.compiler, *self.flags, "-fsanitize=undefined", "-fno-sanitize-recover=all",
                          str(SOURCE), str(FIXTURE), "-o", str(executable)])
        result = self.run_command([str(executable)])
        self.assertIn("PASS policy sanitizer timelines", result.stdout)


if __name__ == "__main__":
    unittest.main()
