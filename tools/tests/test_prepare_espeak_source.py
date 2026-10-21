import datetime
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from project_materials import project_materials_root

SPEC = importlib.util.spec_from_file_location("prepare_espeak_source", ROOT / "tools/prepare_espeak_source.py")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class PrepareEspeakSourceTests(unittest.TestCase):
    def setUp(self):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.workspace = project_materials_root(ROOT) / "prepare-espeak-tests" / (stamp + "-" + uuid.uuid4().hex[:12])
        self.workspace.mkdir(parents=True)
        self.destination = self.workspace / "source"

    def test_existing_directory_is_never_modified(self):
        self.destination.mkdir()
        with mock.patch.object(PREPARE.subprocess, "run") as runner:
            with self.assertRaisesRegex(ValueError, "already exists"):
                PREPARE.prepare(self.destination)
            runner.assert_not_called()

    def test_test_workspaces_remain_unique_with_a_fixed_clock(self):
        with mock.patch.object(datetime, "datetime") as clock:
            clock.now.return_value.strftime.return_value = "fixed-clock"
            first = PrepareEspeakSourceTests()
            second = PrepareEspeakSourceTests()
            first.setUp()
            second.setUp()
        self.assertNotEqual(first.workspace, second.workspace)
        self.assertTrue(first.workspace.is_dir())
        self.assertTrue(second.workspace.is_dir())

    def test_existing_file_is_never_modified(self):
        self.destination.write_bytes(b"user data")
        with self.assertRaisesRegex(ValueError, "already exists"):
            PREPARE.prepare(self.destination)
        self.assertEqual(self.destination.read_bytes(), b"user data")

    def test_check_only_never_invokes_git_or_writes(self):
        with mock.patch.object(PREPARE.PROVENANCE, "validate_supplied_data", return_value={"checked": True}) as validate:
            with mock.patch.object(PREPARE.subprocess, "run") as runner:
                self.assertEqual(PREPARE.prepare(self.destination, True), {"checked": True})
                runner.assert_not_called()
                validate.assert_called_once_with(self.destination)
                self.assertFalse(self.destination.exists())

    def test_exact_bytes_are_not_rewritten(self):
        self.destination.write_bytes(b"exact\r\n")
        digest = hashlib.sha256(self.destination.read_bytes()).hexdigest()
        with mock.patch.object(Path, "write_bytes") as writer:
            PREPARE.restore_exact_bytes(self.destination, digest)
            writer.assert_not_called()

    def test_restore_expected_crlf(self):
        self.destination.write_bytes(b"alpha\nbeta\n")
        expected = b"alpha\r\nbeta\r\n"
        PREPARE.restore_exact_bytes(self.destination, hashlib.sha256(expected).hexdigest())
        self.assertEqual(self.destination.read_bytes(), expected)

    def test_restore_expected_lf(self):
        self.destination.write_bytes(b"alpha\r\nbeta\r\n")
        expected = b"alpha\nbeta\n"
        PREPARE.restore_exact_bytes(self.destination, hashlib.sha256(expected).hexdigest())
        self.assertEqual(self.destination.read_bytes(), expected)

    def test_unknown_content_is_rejected_without_rewrite(self):
        self.destination.write_bytes(b"different\n")
        digest = hashlib.sha256(b"expected\n").hexdigest()
        with self.assertRaisesRegex(ValueError, "beyond line endings"):
            PREPARE.restore_exact_bytes(self.destination, digest)
        self.assertEqual(self.destination.read_bytes(), b"different\n")

    def test_fetch_failure_stops_before_patch_and_validation(self):
        def run(arguments, check):
            self.assertTrue(check)
            if "fetch" in arguments:
                raise subprocess.CalledProcessError(1, arguments)

        with mock.patch.object(PREPARE.subprocess, "run", side_effect=run) as runner:
            with mock.patch.object(PREPARE.PROVENANCE, "validate_supplied_data") as validate:
                with self.assertRaises(subprocess.CalledProcessError):
                    PREPARE.prepare(self.destination)
                validate.assert_not_called()
                self.assertFalse(any("apply" in call.args[0] for call in runner.call_args_list))

    def test_pinned_sequence_checks_patch_then_validates_all_bytes(self):
        expected = {"src/engine.cpp": "engine", "dictsource/pl_list": "dictionary"}
        with mock.patch.object(PREPARE.subprocess, "run") as runner:
            with mock.patch.object(PREPARE.PROVENANCE, "read_hashes", side_effect=[
                    {"src/engine.cpp": "engine"}, {"dictsource/pl_list": "dictionary"}]):
                with mock.patch.object(PREPARE, "restore_exact_bytes") as restore:
                    with mock.patch.object(PREPARE.PROVENANCE, "validate_supplied_data", return_value={"accepted": True}) as validate:
                        self.assertEqual(PREPARE.prepare(self.destination), {"accepted": True})
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertEqual(len(commands), 7)
        self.assertEqual(commands[1][-3:], ["config", "core.autocrlf", "false"])
        self.assertEqual(commands[3][-4:], ["fetch", "--depth=1", "origin", "a14831fd3af6b3df77ef23b854cd05ee05b12851"])
        self.assertIn("--check", commands[5])
        self.assertIn("--binary", commands[6])
        self.assertEqual(restore.call_args_list, [mock.call(self.destination / name, digest) for name, digest in expected.items()])
        validate.assert_called_once_with(self.destination)

    def test_provenance_failure_is_not_accepted(self):
        with mock.patch.object(PREPARE.PROVENANCE, "validate_supplied_data", side_effect=ValueError("mismatch")):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                PREPARE.prepare(self.destination, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
