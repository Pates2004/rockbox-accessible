"""Reject stale supplied data even when the eSpeak Git commit is unchanged."""

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib/espeak"))
sys.path.insert(0, str(ROOT / "lib/espeak/tests"))
from data_provenance import read_hashes, validate_supplied_data
from run_data_tests import compare


class SuppliedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.supplied = ROOT.parent / "espeak-1.44.05-source"
        if not (cls.supplied / ".git").exists():
            raise unittest.SkipTest("Supplied eSpeak checkout unavailable")

    def reject_mutated_bytes(self, relative, pattern):
        original = Path.read_bytes
        target = (self.supplied / relative).resolve()

        def altered(path):
            content = original(path)
            return content + b"\nchanged\n" if path.resolve() == target else content

        with mock.patch.object(Path, "read_bytes", altered):
            with self.assertRaisesRegex(ValueError, pattern):
                validate_supplied_data(self.supplied)

    def test_exact_runtime_and_corresponding_source(self):
        provenance = validate_supplied_data(self.supplied)
        self.assertEqual(len(provenance["runtime_data"]), 283)
        self.assertEqual(len(provenance["dictsource"]), 88)
        self.assertEqual(provenance["runtime_data"]["pl_dict"],
                         "4ba408bc999a1a63e68ce610dbecd956fd989467c2202e58f4a6dae03def5217")
        self.assertEqual(provenance["dictsource"]["pl_list"],
                         "c401e56f6467d9fb51b253b333a6da5ff3de4c9425a6cef43e4eb7915d594180")

    def test_dictionary_change_at_same_commit_is_rejected(self):
        self.reject_mutated_bytes("espeak-data/pl_dict", "working-tree bytes changed: espeak-data/pl_dict")

    def test_corresponding_rules_change_at_same_commit_is_rejected(self):
        self.reject_mutated_bytes("dictsource/pl_rules", "working-tree bytes changed: dictsource/pl_rules")

    def test_source_list_change_at_same_commit_is_rejected(self):
        self.reject_mutated_bytes("dictsource/pl_list", "working-tree bytes changed: dictsource/pl_list")

    def test_unrelated_engine_change_cannot_claim_data_only_update(self):
        self.reject_mutated_bytes("src/synthdata.cpp", "working-tree bytes changed: src/synthdata.cpp")

    def test_manifest_corruption_is_rejected(self):
        original = Path.read_bytes
        manifest = ROOT / "lib/espeak/DATA.sha256"

        def altered(path):
            content = original(path)
            return content + b"\n" if path == manifest else content

        with mock.patch.object(Path, "read_bytes", altered):
            with self.assertRaisesRegex(ValueError, "manifest differs"):
                validate_supplied_data(self.supplied)

    def test_missing_dictionary_is_rejected(self):
        original = Path.rglob

        def missing(path, pattern):
            return (entry for entry in original(path, pattern) if entry.name != "pl_dict")

        with mock.patch.object(Path, "rglob", missing):
            with self.assertRaisesRegex(ValueError, "file inventory changed"):
                validate_supplied_data(self.supplied)


class DataRegressionGuardTests(unittest.TestCase):
    def test_same_phonemes_cannot_hide_pcm_regression(self):
        previous = {"singiel:175": {"language": "pl", "samples": 100, "pcm": 5, "phonemes": "s'iNg;El_"}}
        current = {"singiel:175": dict(previous["singiel:175"], pcm=6)}
        with self.assertRaisesRegex(ValueError, "Unexpected supplied-data effect"):
            compare(previous, current)

    def test_intended_change_must_affect_phonemes_and_pcm(self):
        previous = {"ziscic:175": {"language": "pl", "samples": 100, "pcm": 5, "phonemes": "Z;'iS;ts;its;"}}
        current = {"ziscic:175": dict(previous["ziscic:175"], phonemes="z_'iS;ts;its;")}
        with self.assertRaisesRegex(ValueError, "Unexpected supplied-data effect"):
            compare(previous, current)

    def test_manifest_rejects_duplicate_or_escaping_paths(self):
        digest = "0" * 64
        for entries in (f"{digest}  ../pl_dict\n", f"{digest}  C:/pl_dict\n",
                        f"{digest}  espeak-data/pl_dict\n{digest}  espeak-data/pl_dict\n"):
            with self.subTest(entries=entries):
                with mock.patch.object(Path, "read_text", return_value=entries):
                    with self.assertRaisesRegex(ValueError, "Invalid eSpeak provenance entry"):
                        read_hashes(Path("test-manifest"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
