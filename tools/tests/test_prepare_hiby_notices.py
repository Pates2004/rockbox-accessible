import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from project_materials import project_materials_root

SPEC = importlib.util.spec_from_file_location("prepare_hiby_notices", ROOT / "tools/prepare_hiby_notices.py")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class PrepareHibyNoticesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("ROCKBOX_NOTICE_TEST_WORKSPACE")
        base = Path(configured) if configured else project_materials_root(ROOT) / "prepare-hiby-notices-tests"
        if not base.is_absolute():
            raise ValueError("Test workspace must be absolute")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = base / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.workspace.mkdir(parents=True)

    def setUp(self):
        self.directory = self.workspace / self._testMethodName
        self.directory.mkdir()
        self.sdk = self.directory / "sdk"
        self.output = self.directory / "notices"
        self.sources = {}
        self.members = {}
        for name, (url, checksum) in PREPARE.SOURCES.items():
            root = name.split(".tar.", 1)[0]
            notice_name = "LICENSE" if root.startswith(("libffi-", "zlib-")) else "COPYING"
            entries = [(root + "/" + notice_name, b"GNU GENERAL PUBLIC LICENSE\nGNU LESSER GENERAL PUBLIC LICENSE\nSynthetic test-only license fixture.\n")]
            if root.startswith("gcc-"):
                entries.append((root + "/COPYING.RUNTIME", b"GCC RUNTIME LIBRARY EXCEPTION\nVersion 3.1\nSynthetic fixture.\n"))
            if root.startswith("zlib-"):
                entries.append((root + "/README", b"Synthetic zlib README notice fixture.\n"))
            entries.append((root + "/src/unselected.c", b"Synthetic source; never extracted.\n"))
            self.members[name] = entries
            self.rewrite_archive(name)
            self.sources[name] = (url, self.hash(self.sdk / "downloads" / name))
        self.recipes = {}
        for name in PREPARE.RECIPE_FILES:
            path = self.sdk / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"Synthetic recipe fixture: " + name.encode())
            self.recipes[name] = self.hash(path)
        compiler = self.sdk / "prefix/bin" / (PREPARE.TARGET + "-gcc")
        compiler.parent.mkdir(parents=True)
        compiler.write_bytes(b"Synthetic compiler metadata fixture; never executed")
        copying = next(content for name, content in self.members["alsa-lib-1.0.26.tar.bz2"] if name == PREPARE.ALSA_COPYING)
        self.enterContext(mock.patch.object(PREPARE, "SOURCES", self.sources))
        self.enterContext(mock.patch.object(PREPARE, "RECIPE_FILES", self.recipes))
        self.enterContext(mock.patch.object(PREPARE, "ALSA_COPYING_SHA256", hashlib.sha256(copying).hexdigest()))
        self.runner = self.enterContext(mock.patch.object(PREPARE.subprocess, "run", side_effect=self.compiler_result))

    @staticmethod
    def hash(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def compiler_result(arguments, **options):
        outputs = {"-dumpfullversion": "9.5.0\n", "-dumpmachine": "mipsel-rockbox-linux-gnu\n",
                   "-v": "Target: mipsel-rockbox-linux-gnu\nConfigured with: synthetic-test-only\ngcc version 9.5.0\n"}
        return subprocess.CompletedProcess(arguments, 0, outputs[arguments[-1]], "")

    def rewrite_archive(self, name, entries=None):
        path = self.sdk / "downloads" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w:" + name.rsplit(".", 1)[1]
        with tarfile.open(path, mode) as archive:
            for entry in entries if entries is not None else self.members[name]:
                if isinstance(entry, tarfile.TarInfo):
                    archive.addfile(entry)
                else:
                    relative, content = entry
                    member = tarfile.TarInfo(relative)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
        if name in self.sources:
            self.sources[name] = (self.sources[name][0], self.hash(path))
        return path

    def generated(self):
        return PREPARE.prepare(self.sdk, self.output)

    def reseal(self):
        entries = [(path.relative_to(self.output).as_posix(), self.hash(path))
                   for path in self.output.rglob("*") if path.is_file() and path.name != "SHA256SUMS"]
        (self.output / "SHA256SUMS").write_text("".join(checksum + "  " + name + "\n" for name, checksum in sorted(entries)), encoding="utf-8")

    def test_complete_schema_and_original_license_selection(self):
        result = self.generated()
        metadata = json.loads((self.output / "provenance.json").read_text())
        self.assertEqual(metadata["recipe"], {"upstream_commit": PREPARE.UPSTREAM_COMMIT, "files": self.recipes})
        self.assertEqual(set(metadata["sources"]), set(self.sources))
        self.assertEqual(metadata["compiler"]["version"], "9.5.0")
        self.assertIn("synthetic-test-only", metadata["compiler_configuration"])
        self.assertEqual(metadata["glibc_configure_flags"], PREPARE.GLIBC_FLAGS)
        self.assertEqual(result["notice_files"], 12)
        self.assertTrue((self.output / "zlib-1.2.13/README").is_file())
        self.assertFalse(any(self.output.rglob("*.c")))
        self.assertEqual([call.args[0][-1] for call in self.runner.call_args_list], ["-dumpfullversion", "-dumpmachine", "-v"])
        for name, record in metadata["sources"].items():
            self.assertEqual(record["archive_sha256"], self.sources[name][1])
            self.assertEqual(record["source_provenance"]["sha256"], self.sources[name][1])
            self.assertIn("signatures not checked", record["source_provenance"]["verification"])
            self.assertNotIn("signature_verified", record["source_provenance"])

    def test_check_only_compares_real_inputs_without_writes(self):
        self.generated()
        before = {path.relative_to(self.directory).as_posix(): self.hash(path)
                  for path in self.directory.rglob("*") if path.is_file()}
        with mock.patch.object(PREPARE, "write_payloads") as writer:
            PREPARE.prepare(self.sdk, self.output, check_only=True)
            writer.assert_not_called()
        self.assertEqual(before, {path.relative_to(self.directory).as_posix(): self.hash(path)
                                  for path in self.directory.rglob("*") if path.is_file()})

    def test_existing_directory_is_untouched_before_input_reads(self):
        self.output.mkdir()
        (self.output / "user.txt").write_bytes(b"user data")
        with mock.patch.object(PREPARE, "input_hashes") as inputs:
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.generated()
            inputs.assert_not_called()
        self.assertEqual((self.output / "user.txt").read_bytes(), b"user data")

    def test_existing_file_is_untouched(self):
        self.output.write_bytes(b"user data")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.generated()
        self.assertEqual(self.output.read_bytes(), b"user data")

    def test_source_and_input_output_overlaps_are_rejected(self):
        for output in (self.sdk, self.sdk.parent, self.sdk / "downloads/notices",
                       self.sdk / "official/notices", self.sdk / "prefix/notices", ROOT / "notices-test-output"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "overlaps"):
                PREPARE.prepare(self.sdk, output)
        self.runner.assert_not_called()

    def test_linked_ancestor_is_rejected(self):
        alias = self.directory / "alias"
        try:
            alias.symlink_to(self.sdk, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Creating test symlinks is unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "Linked path or ancestor"):
            PREPARE.prepare(alias / "child", self.output)

    def test_junction_ancestor_detection(self):
        with mock.patch.object(Path, "is_junction", autospec=True, side_effect=lambda path: path == self.sdk):
            with self.assertRaisesRegex(ValueError, "Linked path or ancestor"):
                self.generated()

    def test_recipe_drift_stops_before_compiler_or_output(self):
        (self.sdk / next(iter(self.recipes))).write_bytes(b"changed recipe")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.generated()
        self.runner.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_source_drift_stops_before_selection(self):
        (self.sdk / "downloads" / next(iter(self.sources))).write_bytes(b"changed source")
        with mock.patch.object(PREPARE, "select_notices") as select:
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self.generated()
            select.assert_not_called()

    def test_input_drift_during_collection_is_rejected(self):
        original = PREPARE.inspect_compiler

        def inspect(sdk):
            result = original(sdk)
            (sdk / next(iter(self.recipes))).write_bytes(b"concurrent change")
            return result

        with mock.patch.object(PREPARE, "inspect_compiler", side_effect=inspect):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self.generated()
        self.assertFalse(self.output.exists())

    def test_wrong_actual_compiler_version_and_target_are_rejected(self):
        for option in ("-dumpfullversion", "-dumpmachine", "-v"):
            def result(arguments, **options):
                returned = self.compiler_result(arguments, **options)
                if arguments[-1] == option:
                    returned.stdout = "" if option == "-v" else "wrong"
                return returned

            with self.subTest(option=option), mock.patch.object(PREPARE.subprocess, "run", side_effect=result):
                with self.assertRaisesRegex(ValueError, "actual hosted"):
                    self.generated()
        self.assertFalse(self.output.exists())

    def test_compiler_failure_is_not_provenance(self):
        self.runner.side_effect = subprocess.CalledProcessError(1, ["synthetic-gcc", "-v"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.generated()
        self.assertFalse(self.output.exists())

    def test_missing_original_notice_is_rejected(self):
        name = next(iter(self.sources))
        self.rewrite_archive(name, [(name.split(".tar.")[0] + "/src/unselected.c", b"source")])
        with self.assertRaisesRegex(ValueError, "No original root license"):
            self.generated()

    def test_alsa_copying_pin_is_independent_of_archive_pin(self):
        name = "alsa-lib-1.0.26.tar.bz2"
        self.rewrite_archive(name, [(PREPARE.ALSA_COPYING, b"changed license")])
        with self.assertRaisesRegex(ValueError, "ALSA COPYING"):
            self.generated()

    def test_required_runtime_exception_text_is_not_invented(self):
        name = "gcc-9.5.0.tar.xz"
        self.rewrite_archive(name, [(relative, b"No exception here" if relative.endswith("COPYING.RUNTIME") else content)
                                    for relative, content in self.members[name]])
        with self.assertRaisesRegex(ValueError, "Required original license"):
            self.generated()

    def test_unsafe_archive_paths_even_when_unselected(self):
        name = "alsa-lib-1.0.26.tar.bz2"
        for relative in ("../escape", "/absolute", "C:/absolute", "alsa-lib-1.0.26/../escape",
                         "alsa-lib-1.0.26\\escape", "alsa-lib-1.0.26/bad\nname"):
            with self.subTest(relative=relative):
                path = self.rewrite_archive(name, [*self.members[name], (relative, b"unsafe")])
                with self.assertRaisesRegex(ValueError, "Unsafe archive"):
                    PREPARE.select_notices(path, "alsa-lib-1.0.26")

    def test_escaping_symlink_and_hardlink_are_rejected(self):
        name = "alsa-lib-1.0.26.tar.bz2"
        for kind, target in ((tarfile.SYMTYPE, "../../outside"), (tarfile.SYMTYPE, "/outside"),
                             (tarfile.LNKTYPE, "../outside")):
            member = tarfile.TarInfo("alsa-lib-1.0.26/link")
            member.type = kind
            member.linkname = target
            with self.subTest(kind=kind, target=target):
                path = self.rewrite_archive(name, [*self.members[name], member])
                with self.assertRaisesRegex(ValueError, "archive link"):
                    PREPARE.select_notices(path, "alsa-lib-1.0.26")

    def test_safe_unselected_links_are_never_extracted(self):
        name = "alsa-lib-1.0.26.tar.bz2"
        member = tarfile.TarInfo("alsa-lib-1.0.26/safe-link")
        member.type = tarfile.SYMTYPE
        member.linkname = "src/unselected.c"
        path = self.rewrite_archive(name, [*self.members[name], member])
        selected = PREPARE.select_notices(path, "alsa-lib-1.0.26")
        self.assertEqual(set(selected), {PREPARE.ALSA_COPYING})

    def test_linked_license_is_rejected(self):
        member = tarfile.TarInfo(PREPARE.ALSA_COPYING)
        member.type = tarfile.SYMTYPE
        member.linkname = "src/unselected.c"
        path = self.rewrite_archive("alsa-lib-1.0.26.tar.bz2", [member])
        with self.assertRaisesRegex(ValueError, "regular file"):
            PREPARE.select_notices(path, "alsa-lib-1.0.26")

    def test_special_entries_and_setid_are_rejected(self):
        for kind, mode in ((tarfile.FIFOTYPE, 0o644), (tarfile.CHRTYPE, 0o644), (tarfile.REGTYPE, 0o4755)):
            member = tarfile.TarInfo("alsa-lib-1.0.26/special")
            member.type = kind
            member.mode = mode
            with self.subTest(kind=kind, mode=mode):
                path = self.rewrite_archive("alsa-lib-1.0.26.tar.bz2", [*self.members["alsa-lib-1.0.26.tar.bz2"], member])
                with self.assertRaisesRegex(ValueError, "Unsafe archive entry"):
                    PREPARE.select_notices(path, "alsa-lib-1.0.26")

    def test_duplicate_paths_are_rejected(self):
        name = "alsa-lib-1.0.26.tar.bz2"
        path = self.rewrite_archive(name, self.members[name] * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate archive path"):
            PREPARE.select_notices(path, "alsa-lib-1.0.26")

    def test_unselected_linux_case_variants_are_supported(self):
        name = "alsa-lib-1.0.26.tar.bz2"
        path = self.rewrite_archive(name, [*self.members[name], ("alsa-lib-1.0.26/src/Case.h", b"one"),
                                          ("alsa-lib-1.0.26/src/case.h", b"two")])
        self.assertEqual(set(PREPARE.select_notices(path, "alsa-lib-1.0.26")), {PREPARE.ALSA_COPYING})

    def test_archive_and_notice_size_limits(self):
        name = "alsa-lib-1.0.26.tar.bz2"
        path = self.sdk / "downloads" / name
        for constant in ("MAX_MEMBERS", "MAX_EXPANDED_BYTES", "MAX_NOTICE_BYTES", "MAX_TOTAL_NOTICE_BYTES"):
            with self.subTest(constant=constant), mock.patch.object(PREPARE, constant, 1):
                with self.assertRaisesRegex(ValueError, "limit|bounded"):
                    PREPARE.select_notices(path, "alsa-lib-1.0.26")
        with mock.patch.object(PREPARE, "MAX_ARCHIVE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "compressed-size limit"):
                self.generated()

    def test_payload_tampering_and_unlisted_files_are_rejected(self):
        self.generated()
        (self.output / PREPARE.ALSA_COPYING).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA256SUMS mismatch"):
            PREPARE.verify_notices(self.output)
        with self.assertRaisesRegex(ValueError, "SHA256SUMS mismatch"):
            PREPARE.prepare(self.sdk, self.output, check_only=True)

    def test_unlisted_file_is_rejected(self):
        self.generated()
        (self.output / "unexpected").write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "unlisted payload"):
            PREPARE.verify_notices(self.output)

    def test_resealed_provenance_recipe_forgery_is_rejected(self):
        self.generated()
        path = self.output / "provenance.json"
        metadata = json.loads(path.read_text())
        metadata["recipe"]["files"] = {}
        path.write_text(json.dumps(metadata), encoding="utf-8")
        self.reseal()
        with self.assertRaisesRegex(ValueError, "recipe/source schema"):
            PREPARE.verify_notices(self.output)

    def test_resealed_original_notice_forgery_is_rejected(self):
        self.generated()
        (self.output / PREPARE.ALSA_COPYING).write_bytes(b"forged")
        self.reseal()
        with self.assertRaisesRegex(ValueError, "Original notice hashes"):
            PREPARE.verify_notices(self.output)

    def test_manifest_duplicate_and_path_traversal_are_rejected(self):
        self.generated()
        manifest = self.output / "SHA256SUMS"
        original = manifest.read_text()
        for addition in (original.splitlines()[0] + "\n", "a" * 64 + "  ../escape\n"):
            manifest.write_text(original + addition, encoding="utf-8")
            with self.subTest(addition=addition), self.assertRaisesRegex(ValueError, "duplicate|Unsafe archive path"):
                PREPARE.verify_notices(self.output)

    def test_output_created_midflight_is_preserved(self):
        original = PREPARE.inspect_compiler

        def inspect(sdk):
            result = original(sdk)
            self.output.mkdir()
            (self.output / "user.txt").write_bytes(b"concurrent user data")
            return result

        with mock.patch.object(PREPARE, "inspect_compiler", side_effect=inspect):
            with self.assertRaisesRegex(RuntimeError, "retained staging"):
                self.generated()
        self.assertEqual((self.output / "user.txt").read_bytes(), b"concurrent user data")
        self.assertEqual(len(list(self.directory.glob(".notices.staging-*"))), 1)

    def test_staged_validation_failure_never_publishes(self):
        with mock.patch.object(PREPARE, "verify_notices", side_effect=ValueError("staging tampered")):
            with self.assertRaisesRegex(RuntimeError, "staging tampered"):
                self.generated()
        self.assertFalse(self.output.exists())
        self.assertEqual(len(list(self.directory.glob(".notices.staging-*"))), 1)

    def test_cli_requires_explicit_paths_and_reports_success(self):
        with mock.patch.object(sys, "argv", ["prepare_hiby_notices.py"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                PREPARE.main()
            self.assertEqual(error.exception.code, 2)
        with mock.patch.object(sys, "argv", ["prepare_hiby_notices.py", "--sdk-root", str(self.sdk), "--output", str(self.output)]):
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                PREPARE.main()
            self.assertEqual(json.loads(captured.getvalue())["notice_files"], 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
