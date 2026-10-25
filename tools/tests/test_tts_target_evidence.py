from datetime import datetime, timezone
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

from materials_fixtures import materials_resolver
import test_tts_targets as targets


class ExperimentalTargetOptInTests(unittest.TestCase):
    def test_configuration_command_forwards_only_explicit_confirmation(self):
        for platform in ("windows", "linux"):
            for target in ("sansaclipplus", "hibyr1", "ipod6g", "shanlingq1"):
                for allowed in (False, True):
                    with self.subTest(platform=platform, target=target, allowed=allowed):
                        command = targets.configuration_command(target, platform, allowed)
                        self.assertEqual("--allow-experimental-espeak" in command, allowed)
                        self.assertIn("--target=" + target, command)
                        self.assertIn("--integrated-espeak", command)
                        self.assertEqual("--sdl-threads" in command, platform == "linux")

    def test_unconfirmed_target_fails_before_build_or_dependency_changes(self):
        for target in ("ipod6g", "shanlingq1"):
            with self.subTest(target=target), \
                    mock.patch.object(sys, "argv", ["test_tts_targets.py", "--targets", target]), \
                    mock.patch.object(targets, "build_targets") as build, \
                    contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as result:
                    targets.main()
                self.assertEqual(result.exception.code, 2)
                self.assertIn("--allow-experimental-espeak", error.getvalue())
                build.assert_not_called()

    def test_explicit_confirmation_reaches_builder(self):
        with mock.patch.object(sys, "argv", ["test_tts_targets.py", "--targets", "ipod6g",
                                           "--allow-experimental-espeak"]), \
                mock.patch.object(targets, "build_targets", return_value=True) as build:
            self.assertEqual(targets.main(), 0)
            arguments, = build.call_args.args
            self.assertTrue(arguments.allow_experimental_espeak)
            self.assertEqual(arguments.targets, ["ipod6g"])

    def test_reference_target_requires_no_additional_confirmation(self):
        with mock.patch.object(sys, "argv", ["test_tts_targets.py", "--targets", "sansaclipplus"]), \
                mock.patch.object(targets, "build_targets", return_value=True) as build:
            self.assertEqual(targets.main(), 0)
            self.assertFalse(build.call_args.args[0].allow_experimental_espeak)

    def test_listing_requires_no_confirmation_or_build(self):
        with mock.patch.object(sys, "argv", ["test_tts_targets.py", "--list-targets"]), \
                mock.patch.object(targets, "build_targets") as build, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(targets.main(), 0)
            self.assertIn("shanlingq1", output.getvalue())
            build.assert_not_called()


class TargetEvidencePathTests(unittest.TestCase):
    def setUp(self):
        workspace = targets._project_materials_root(targets.ROOT)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.area = workspace / "target-evidence-path-tests" / stamp / self._testMethodName
        self.source = self.area / "source"
        self.source.mkdir(parents=True)
        self.resolver = materials_resolver(self.source, self.area / "work")
        patcher = mock.patch.object(targets, "_project_materials_root", side_effect=self.resolver)
        patcher.start()
        self.addCleanup(patcher.stop)

    def artifact(self, category, relative):
        path = self.resolver(self.source, category) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Synthetic diagnostic evidence; not an executable.")
        return path

    def test_historic_workspace_reference_is_resolved_without_rewriting(self):
        path = self.artifact("Workspace", "tts-target-tests/run/stdout.log")
        record = {"path": "Workspace/tts-target-tests/run/stdout.log", "sha256": targets.digest(path)}
        original = dict(record)
        self.assertEqual(targets.verify_evidence(record), path)
        self.assertEqual(record, original)

    def test_historic_snapshot_reference_is_resolved_without_rewriting(self):
        path = self.artifact("Snapshots", "previous/rockboxui.exe")
        record = {"path": "snapshots/previous/rockboxui.exe", "sha256": targets.digest(path)}
        original = dict(record)
        self.assertEqual(targets.verify_evidence(record), path)
        self.assertEqual(record, original)

    def test_relocated_historic_receipt_retains_its_original_bytes_and_hash(self):
        original = self.area / "historical-report.json"
        content = b'{ "snapshot": "snapshots/previous/rockboxui.exe", "passed": false }\r\n'
        original.write_bytes(content)
        record = {"path": "Workspace/history/report.json", "sha256": targets.digest(original)}
        original_record = dict(record)
        relocated = self.resolver(self.source) / "history/report.json"
        relocated.parent.mkdir(parents=True)
        original.rename(relocated)
        self.assertEqual(targets.verify_evidence(record), relocated)
        self.assertEqual(relocated.read_bytes(), content)
        self.assertEqual(record, original_record)

    def test_cross_category_references_round_trip(self):
        for category in ("Workspace", "Snapshots"):
            with self.subTest(category=category):
                path = self.artifact(category, "round/rockboxui.exe")
                reference = targets.evidence_reference(path)
                self.assertEqual(reference, category + "/round/rockboxui.exe")
                self.assertEqual(targets.resolve_evidence_path(reference), path)

    def test_workspace_guard_still_rejects_snapshot_artifacts(self):
        path = self.artifact("Snapshots", "previous/rockboxui.exe")
        with self.assertRaisesRegex(RuntimeError, "outside Workspace"):
            targets.contained(path)

    def test_snapshot_hash_is_still_checked(self):
        path = self.artifact("Snapshots", "previous/rockboxui.exe")
        record = {"path": "snapshots/previous/rockboxui.exe", "sha256": targets.digest(path)}
        path.write_bytes(b"Changed evidence")
        with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
            targets.verify_evidence(record)

    def test_links_in_artifacts_and_ancestors_are_rejected_before_hashing(self):
        for category in ("Workspace", "Snapshots"):
            path = self.artifact(category, "history/result.log")
            record = {"path": category + "/history/result.log", "sha256": targets.digest(path)}
            for detector in ("is_symlink", "is_junction"):
                for linked in (path, path.parent, self.resolver(self.source, category)):
                    with self.subTest(category=category, detector=detector, linked=linked), \
                            mock.patch.object(Path, detector, lambda candidate: candidate == linked, create=True), \
                            mock.patch.object(targets, "digest") as read_hash:
                        with self.assertRaisesRegex(RuntimeError, "Artifact path is a link"):
                            targets.verify_evidence(record)
                        read_hash.assert_not_called()

    def test_unsafe_and_unrelated_categories_are_rejected(self):
        for reference in ("Forme/audit.md", "Trash/result.log", "installfiles/release.zip",
                          "../outside", "Workspace/../Snapshots/previous/rockboxui.exe",
                          "Workspace/../../another-project/result.log", "/absolute/result.log",
                          "D:/work/Workspace/source/result.log", "Workspace\\result.log",
                          "Workspace//result.log", "Workspace/./result.log", "Workspace"):
            with self.subTest(reference=reference), self.assertRaises(RuntimeError):
                targets.resolve_evidence_path(reference)

    def test_unrelated_paths_cannot_be_serialized_as_evidence(self):
        path = self.area / "unrelated.txt"
        path.write_bytes(b"Unrelated fixture")
        with self.assertRaisesRegex(RuntimeError, "outside project diagnostic directories"):
            targets.evidence_reference(path)

    def test_evidence_from_another_project_is_rejected(self):
        path = self.area / "work/Workspace/other-project/result.log"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"Another project")
        with self.assertRaisesRegex(RuntimeError, "outside project diagnostic directories"):
            targets.evidence_reference(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
