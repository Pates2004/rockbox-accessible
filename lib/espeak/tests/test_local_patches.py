import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sonic_checks import check_dependency


SOURCE = Path(__file__).resolve().parents[1]
SUPPLIED = SOURCE.parents[2] / "espeak-1.44.05-source"


class LocalPatchProvenanceTests(unittest.TestCase):
    def test_exact_approved_local_sources(self):
        provenance = check_dependency(SOURCE)
        expected = {
            "engine/compiledict.cpp": "84849dae24db09a93995fc9f207ec3b3c593723324bb3243535d01bf0a343f22",
            "engine/tr_languages.cpp": "d29137d5cc2a2af4a44edfd37751752bd5fbe665d42dab68de89ddceffdbd8cc",
            "sonic/sonic.c": "9c1fe2a380bad7c9953859cbd43f267bce68d90bf95394c51f808372e905c34f",
        }
        self.assertEqual({name: entry["integrated_sha256"] for name, entry in
                          provenance["patches"].items()}, expected)
        sonic = (SOURCE / "sonic/sonic.c").read_bytes()
        self.assertEqual(sonic.count(b"\r\n"), sonic.count(b"\n"))

    def test_supplied_sources_still_match_original_manifests(self):
        if not SUPPLIED.is_dir():
            self.skipTest("Original supplied checkout unavailable")
        check_dependency(SOURCE, SUPPLIED)

    def test_changed_local_source_is_rejected(self):
        original_read = Path.read_bytes
        for relative in ("engine/compiledict.cpp", "engine/tr_languages.cpp", "sonic/sonic.c"):
            target = SOURCE / relative

            def altered_read(path):
                original = original_read(path)
                return original + b"\n" if path == target else original

            with self.subTest(source=relative), patch.object(Path, "read_bytes", altered_read):
                with self.assertRaises(SystemExit):
                    check_dependency(SOURCE)

    def test_changed_supplied_source_is_rejected(self):
        if not SUPPLIED.is_dir():
            self.skipTest("Original supplied checkout unavailable")
        original_read = Path.read_bytes
        for relative in ("src/compiledict.cpp", "src/tr_languages.cpp", "platforms/windows/third_party/sonic/sonic.c"):
            target = SUPPLIED / relative

            def altered_read(path):
                original = original_read(path)
                return original + b"\n" if path == target else original

            with self.subTest(source=relative), patch.object(Path, "read_bytes", altered_read):
                with self.assertRaises(SystemExit):
                    check_dependency(SOURCE, SUPPLIED)

    def test_original_manifests_remain_pinned(self):
        expected = {
            "UPSTREAM.sha256": "b980492ecd8fc75ad954752b70986f1daf09dbeb9cafed897d30d61bd585f584",
            "SONIC.sha256": "e624eb0dc42b097472821e757519351813621142548b24dcb2c4423975a49056",
        }
        provenance = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["original_manifests"], expected)
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest(), digest)

    def check_readme_mutation(self, content, *, provenance=None, error):
        original_read = Path.read_bytes
        target = SOURCE / "sonic/README.md"

        def altered_read(path):
            return content if path == target else original_read(path)

        with patch.object(Path, "read_bytes", altered_read):
            with self.assertRaisesRegex(SystemExit, error):
                if provenance is None:
                    check_dependency(SOURCE)
                else:
                    with patch("sonic_checks.json.loads", return_value=provenance):
                        check_dependency(SOURCE)

    def test_approved_readme_change_is_exactly_pinned(self):
        provenance = check_dependency(SOURCE)
        entry = provenance["documentation_changes"]["sonic/README.md"]
        self.assertEqual(set(provenance["documentation_changes"]), {"sonic/README.md"})
        self.assertEqual(entry["supplied_sha256"],
                         "fb015d72a022a6d86aaaa129fa25e2eb7f544c1345ffe6c8687e9447ecb06dad")
        self.assertEqual(entry["integrated_sha256"],
                         "ab9b8f73bf36483bd69e7350cd24ea9d41621ed77ba5b993ab25bc71825e08fc")
        self.assertEqual(entry["notice_date"], "2026-10-21")

    def test_missing_documentation_metadata_is_rejected(self):
        provenance = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        del provenance["documentation_changes"]
        with patch("sonic_checks.json.loads", return_value=provenance):
            with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                check_dependency(SOURCE)

    def test_malformed_documentation_containers_are_rejected(self):
        baseline = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        for malformed in (None, False, 1, "sonic/README.md", [], {}):
            with self.subTest(documentation=malformed):
                provenance = copy.deepcopy(baseline)
                provenance["documentation_changes"] = malformed
                with patch("sonic_checks.json.loads", return_value=provenance):
                    with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                        check_dependency(SOURCE)

    def test_unknown_documentation_paths_are_rejected(self):
        baseline = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        for relative in ("sonic/LICENSE", "sonic/sonic.h", "engine/speech.h", "../README.md",
                         "sonic/../README.md", "sonic\\README.md", "/sonic/README.md",
                         "SONIC/README.md", "sonic/readme.md"):
            for retain_approved in (False, True):
                with self.subTest(path=relative, retain_approved=retain_approved):
                    provenance = copy.deepcopy(baseline)
                    entry = provenance["documentation_changes"]["sonic/README.md"]
                    provenance["documentation_changes"] = {
                        **({"sonic/README.md": entry} if retain_approved else {}),
                        relative: entry,
                    }
                    with patch("sonic_checks.json.loads", return_value=provenance):
                        with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                            check_dependency(SOURCE)

    def test_malformed_documentation_entries_are_rejected(self):
        baseline = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        for malformed in (None, False, 1, "notice", [], {}):
            with self.subTest(entry=malformed):
                provenance = copy.deepcopy(baseline)
                provenance["documentation_changes"]["sonic/README.md"] = malformed
                with patch("sonic_checks.json.loads", return_value=provenance):
                    with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                        check_dependency(SOURCE)

    def test_missing_extra_and_malformed_entry_fields_are_rejected(self):
        baseline = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        for field in baseline["documentation_changes"]["sonic/README.md"]:
            for malformed in (None, False, 1, [], {}, ""):
                with self.subTest(field=field, value=malformed):
                    provenance = copy.deepcopy(baseline)
                    provenance["documentation_changes"]["sonic/README.md"][field] = malformed
                    with patch("sonic_checks.json.loads", return_value=provenance):
                        with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                            check_dependency(SOURCE)
            provenance = copy.deepcopy(baseline)
            del provenance["documentation_changes"]["sonic/README.md"][field]
            with self.subTest(missing=field), patch("sonic_checks.json.loads", return_value=provenance):
                with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                    check_dependency(SOURCE)
        provenance = copy.deepcopy(baseline)
        provenance["documentation_changes"]["sonic/README.md"]["original_prefix_bytes"] = 218
        with patch("sonic_checks.json.loads", return_value=provenance):
            with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                check_dependency(SOURCE)

    def test_unapproved_documentation_hash_date_and_description_are_rejected(self):
        baseline = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        replacements = {"supplied_sha256": "0" * 64, "integrated_sha256": "0" * 64,
                        "notice_date": "2026-10-20", "change": "Different documentation change"}
        for field, value in replacements.items():
            with self.subTest(field=field):
                provenance = copy.deepcopy(baseline)
                provenance["documentation_changes"]["sonic/README.md"][field] = value
                with patch("sonic_checks.json.loads", return_value=provenance):
                    with self.assertRaisesRegex(SystemExit, "Unrecognized local Sonic documentation"):
                        check_dependency(SOURCE)

    def test_changed_or_truncated_original_readme_prefix_is_rejected(self):
        content = (SOURCE / "sonic/README.md").read_bytes()
        for altered in (b"!" + content[1:], content[:216], b""):
            with self.subTest(length=len(altered)):
                self.check_readme_mutation(altered, error="Original Sonic README prefix mismatch")

    def test_missing_wrong_date_and_misplaced_readme_notice_are_rejected(self):
        content = (SOURCE / "sonic/README.md").read_bytes()
        for altered in (content[:217], content.replace(b"2026-10-21", b"2026-10-20"),
                        content[:217] + b"\n" + content[217:]):
            with self.subTest(length=len(altered)):
                self.check_readme_mutation(altered, error="Missing dated Sonic README modification notice")

    def test_changed_readme_body_is_rejected(self):
        content = (SOURCE / "sonic/README.md").read_bytes()
        for altered in (content + b"\n", content.replace(b"reallocation", b"REALLOCATION")):
            with self.subTest(length=len(altered)):
                self.check_readme_mutation(altered, error="Vendored Sonic byte mismatch: sonic/README.md")

    def test_recomputed_readme_hash_cannot_authorize_tampering(self):
        content = (SOURCE / "sonic/README.md").read_bytes()
        baseline = json.loads((SOURCE / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        for altered in (content + b"\n", b"!" + content[1:]):
            with self.subTest(length=len(altered)):
                provenance = copy.deepcopy(baseline)
                entry = provenance["documentation_changes"]["sonic/README.md"]
                entry["integrated_sha256"] = hashlib.sha256(altered).hexdigest()
                entry["supplied_sha256"] = hashlib.sha256(altered[:217]).hexdigest()
                self.check_readme_mutation(altered, provenance=provenance,
                                          error="Unrecognized local Sonic documentation")

    def test_supplied_original_readme_is_still_pinned(self):
        if not SUPPLIED.is_dir():
            self.skipTest("Original supplied checkout unavailable")
        original_read = Path.read_bytes
        target = SUPPLIED / "platforms/windows/third_party/sonic/README.md"

        def altered_read(path):
            content = original_read(path)
            return content + b"\n" if path == target else content

        with patch.object(Path, "read_bytes", altered_read):
            with self.assertRaisesRegex(SystemExit, "Original supplied Sonic byte mismatch: sonic/README.md"):
                check_dependency(SOURCE, SUPPLIED)

    def test_other_original_sonic_files_remain_pinned(self):
        original_read = Path.read_bytes
        for relative in ("sonic/sonic.h", "sonic/LICENSE"):
            target = SOURCE / relative

            def altered_read(path):
                content = original_read(path)
                return content + b"\n" if path == target else content

            with self.subTest(source=relative), patch.object(Path, "read_bytes", altered_read):
                with self.assertRaisesRegex(SystemExit, "Vendored Sonic byte mismatch"):
                    check_dependency(SOURCE)

    def test_substituted_original_readme_manifest_record_is_rejected(self):
        original_read = Path.read_text
        target = SOURCE / "SONIC.sha256"

        def altered_read(path, *arguments, **keywords):
            content = original_read(path, *arguments, **keywords)
            if path == target:
                return content.replace(
                    "fb015d72a022a6d86aaaa129fa25e2eb7f544c1345ffe6c8687e9447ecb06dad",
                    "0" * 64,
                )
            return content

        with patch.object(Path, "read_text", altered_read):
            with self.assertRaisesRegex(SystemExit, "Original Sonic documentation provenance changed"):
                check_dependency(SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
