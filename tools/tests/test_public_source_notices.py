"""Verify dated notices without changing imported behavior or pinned inputs."""

import hashlib
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
ESPEAK = ROOT / "lib/espeak"
NOTICE_DATE = "2026-10-21"
ENGINE_NOTICE = (
    b"/* Modified for Rockbox Accessible integration; change notice dated 2026-10-21.\n"
    b" * Local integration changes are described in ../README.md.\n"
    b" */\n\n"
)
SONIC_NOTICE = (
    b"/* Modified for Rockbox Accessible; change notice dated 2026-10-21.\r\n"
    b" * Preserve owned input/output buffers and capacities when realloc fails.\r\n"
    b" */\r\n\r\n"
)
ENGINE_BEFORE_NOTICES = {
    "speak_lib.cpp": "9c45538c01f9f1a71eef3bf010cd2b39ca77639b8275f47b8217851e5f20a213",
    "compiledict.cpp": "9b0a0f21b0d2ba47345e62644b5b7c020139a5489f4ebe437c41215352d4ddce",
    "dictionary.cpp": "a53cbe3c715f759b05c8604e082945504d76e5ba2789030378ee57621c9f8adf",
    "intonation.cpp": "c9a2374ba190614d109fc2c87bec0afb68671accfa318faa539ccdbe2b3b3d99",
    "readclause.cpp": "456bdc1d15375a539e3b74e421bdec75d04c63bf748a7b5652ffa264d9c3c4e6",
    "synthdata.cpp": "035b39ae8f164eefc8fcff46287bf116ffa18a55b4133ee772b2ea62da7f932a",
    "translate.cpp": "88d4ed72c132780a5021958cdd439fef772f4d1192d864e06cf8b4109c8835a7",
    "tr_languages.cpp": "1bb14dd187f9199de2846d64512f2167a3e824d45f3ed982ad615d0c3897386b",
    "voices.cpp": "c8a843eb12a60bf931255a1c612874c0f8b14d4403aff2247ca85983d8fe912a",
    "wavegen.cpp": "2989747811cc953ba1dfc074708869d8e7db4356ae0e218d8d29a3b81e26dfdc",
    "klatt.cpp": "2dbb6158f404b188e07e1ff8a12d9d6cb33a01b997b19aa56fc585c59ab902bb",
    "speech.h": "d51b0cf7575195f673541a14a736d93ab1fa922d8b83e790673c6878ef51ed31"
}
# Subsequent ordinary-text fixes keep the dated notices and original history.
# Pin their reviewed current bodies separately from the notice-only baseline.
ENGINE_AFTER_STABILITY_FIX = {
    "dictionary.cpp": "7c53cfe027c9bbd061c7e861ae66463f53be881177b6981f7fc6b58350f78184",
    "translate.cpp": "04928658baf6ae6ea7aef0d819a02a9bdbc35d8f1a98558bf8fb4b25e20a37c8",
}
PINNED_INPUTS = {
    "DATA.sha256": "8ed383e197973f4699c4f6499c20eed3d34e725d044b97531098d84ba2055132",
    "DATA-PROVENANCE.json": "928a9694079ce80771b576ea882bdb6ce3f988be8ef4807b0c95326876f200a6",
    "UPSTREAM.sha256": "b980492ecd8fc75ad954752b70986f1daf09dbeb9cafed897d30d61bd585f584",
    "SONIC.sha256": "e624eb0dc42b097472821e757519351813621142548b24dcb2c4423975a49056",
    "supplied-r34-data.patch": "f5ae1afcf0e56f55d5e39db70f9a65eb191c68f03dda82a33bdd5a39f25d5364"
}
NOTICED_PATCH_HASHES = {
    "engine/compiledict.cpp": "84849dae24db09a93995fc9f207ec3b3c593723324bb3243535d01bf0a343f22",
    "engine/dictionary.cpp": "bdaa52af9dbf35ae16942ea5d66741fae91e6e92f9a07430f90e214297502b15",
    "engine/translate.cpp": "18c8c91d36f6ca2c24e904dbaa8015e512f5321f106bfa1f02abe42a5fef0b72",
    "engine/tr_languages.cpp": "d29137d5cc2a2af4a44edfd37751752bd5fbe665d42dab68de89ddceffdbd8cc",
    "sonic/sonic.c": "9c1fe2a380bad7c9953859cbd43f267bce68d90bf95394c51f808372e905c34f"
}
SONIC_BEFORE_NOTICE = "fd4aeff267d1c971ec7b1c23bd0add262f267de57fd14e3e7f67b0e22b15daae"
LICENSE_HASHES = {
    "License.txt": "d45163f51088e4ed8497c25d6acb9ceeae6cd5e1d4f176a921222b4c8bab409b",
    "sonic/LICENSE": "3ddf9be5c28fe27dad143a5dc76eea25222ad1dd68934a047064e56ed2fa40c5",
}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def read_manifest(name):
    return {
        relative: checksum
        for checksum, relative in (
            line.split(None, 1)
            for line in (ESPEAK / name).read_text(encoding="utf-8").splitlines()
        )
    }


def validate_notice(content, notice, previous_digest):
    if not content.startswith(notice):
        raise ValueError("Missing or changed dated modification notice")
    original = content[len(notice):]
    if digest(original) != previous_digest:
        raise ValueError("Source bytes changed beyond the modification notice")
    return original


def effective_git_attributes(paths, autocrlf):
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=" + autocrlf, "-C", str(ROOT),
         "check-attr", "--all", "-z", "--", *paths],
        capture_output=True, check=True,
    )
    fields = result.stdout.split(b"\0")
    if fields.pop() != b"" or len(fields) % 3:
        raise ValueError("Invalid git check-attr output")
    attributes = {path: {} for path in paths}
    for offset in range(0, len(fields), 3):
        path, name, value = (field.decode("utf-8") for field in fields[offset:offset + 3])
        attributes[path][name] = value
    return attributes


class PublicSourceNoticeTests(unittest.TestCase):
    def test_effective_git_attributes_keep_engine_sources_lf(self):
        paths = ["lib/espeak/engine/" + relative.removeprefix("src/")
                 for relative in read_manifest("UPSTREAM.sha256")
                 if relative.startswith("src/")]
        self.assertEqual(len(paths), 30)
        expected = {path: {"text": "set", "eol": "lf", "whitespace": "-blank-at-eol,-blank-at-eof,-space-before-tab"} for path in paths}
        for autocrlf in ("false", "true"):
            with self.subTest(autocrlf=autocrlf):
                self.assertEqual(effective_git_attributes(paths, autocrlf), expected)

    def test_effective_git_attributes_keep_pinned_inputs_lf(self):
        paths = ["lib/espeak/" + relative for relative in PINNED_INPUTS]
        expected = {path: {"text": "set", "eol": "lf"} for path in paths}
        expected["lib/espeak/supplied-r34-data.patch"]["whitespace"] = "-blank-at-eof"
        for autocrlf in ("false", "true"):
            with self.subTest(autocrlf=autocrlf):
                self.assertEqual(effective_git_attributes(paths, autocrlf), expected)

    def test_effective_git_attributes_preserve_sonic_bytes(self):
        paths = ["lib/espeak/" + relative for relative in read_manifest("SONIC.sha256")]
        self.assertEqual(len(paths), 4)
        expected = {path: {"text": "unset"} for path in paths}
        for name in ("sonic.c", "sonic.h", "LICENSE"):
            expected["lib/espeak/sonic/" + name]["whitespace"] = "cr-at-eol"
        for autocrlf in ("false", "true"):
            with self.subTest(autocrlf=autocrlf):
                self.assertEqual(effective_git_attributes(paths, autocrlf), expected)

    def test_modified_engine_files_keep_notices_and_recorded_source_bytes(self):
        for name, checksum in ENGINE_BEFORE_NOTICES.items():
            with self.subTest(source=name):
                content = (ESPEAK / "engine" / name).read_bytes()
                original = validate_notice(content, ENGINE_NOTICE,
                                           ENGINE_AFTER_STABILITY_FIX.get(name, checksum))
                self.assertIn(b"GNU General Public License", original)

    def test_import_whitespace_exceptions_do_not_cover_integration_or_project_sources(self):
        paths = ["apps/tts.c", "lib/espeak/rb_espeak.cpp", "lib/espeak/native/native_runtime.c",
                 "lib/espeak/README.md", "tools/prepare_espeak_source.py",
                 "tools/tests/test_public_source_notices.py"]
        for attributes in effective_git_attributes(paths, "false").values():
            self.assertNotIn("whitespace", attributes)
        self.assertEqual(effective_git_attributes(["lib/espeak/License.txt"], "false"),
                         {"lib/espeak/License.txt": {"text": "set", "eol": "lf", "whitespace": "-blank-at-eol,-blank-at-eof"}})

    def test_espeak_license_checkout_keeps_its_pinned_lf_on_windows(self):
        expected = {"lib/espeak/License.txt": {"text": "set", "eol": "lf",
                    "whitespace": "-blank-at-eol,-blank-at-eof"}}
        for autocrlf in ("false", "true"):
            with self.subTest(autocrlf=autocrlf):
                self.assertEqual(effective_git_attributes(["lib/espeak/License.txt"], autocrlf), expected)

    def test_unix_build_entry_points_keep_lf_with_windows_autocrlf(self):
        paths = ["tools/configure", "tools/genlang", "tools/langstatus", "tools/langv1tov2",
                 "tools/updatelang", "tools/rockboxdev.sh", "tools/run-espeak-simulator.sh",
                 "tools/buildzip.pl", "tools/prepare_hiby_notices.py"]
        expected = {path: {"text": "set", "eol": "lf"} for path in paths}
        for autocrlf in ("false", "true"):
            with self.subTest(autocrlf=autocrlf):
                self.assertEqual(effective_git_attributes(paths, autocrlf), expected)

    def test_only_substantively_modified_engine_imports_have_notices(self):
        changed = set()
        for relative, checksum in read_manifest("UPSTREAM.sha256").items():
            if not relative.startswith("src/"):
                continue
            name = relative.removeprefix("src/")
            content = (ESPEAK / "engine" / name).read_bytes()
            if content.startswith(ENGINE_NOTICE):
                content = content[len(ENGINE_NOTICE):]
            if digest(content) != checksum:
                changed.add(name)
        self.assertEqual(changed, set(ENGINE_BEFORE_NOTICES))
        self.assertEqual(len(changed), 12)

    def test_unchanged_imports_match_original_manifest(self):
        unchanged = 0
        for relative, checksum in read_manifest("UPSTREAM.sha256").items():
            if not relative.startswith("src/"):
                continue
            name = relative.removeprefix("src/")
            if name in ENGINE_BEFORE_NOTICES:
                continue
            with self.subTest(source=name):
                content = (ESPEAK / "engine" / name).read_bytes()
                self.assertFalse(content.startswith(ENGINE_NOTICE))
                self.assertEqual(digest(content), checksum)
            unchanged += 1
        self.assertEqual(unchanged, 18)

    def test_sonic_notice_preserves_attribution_and_previous_bytes(self):
        content = (ESPEAK / "sonic/sonic.c").read_bytes()
        original = validate_notice(content, SONIC_NOTICE, SONIC_BEFORE_NOTICE)
        self.assertTrue(original.startswith(b"/* Sonic library\r\n"))
        self.assertIn(b"Bill Cox\r\n", original)
        self.assertIn(b"This file is licensed under the Apache 2.0 license.", original)

    def test_sonic_retains_only_crlf_line_endings(self):
        content = (ESPEAK / "sonic/sonic.c").read_bytes()
        self.assertGreater(content.count(b"\r\n"), 0)
        self.assertEqual(content.count(b"\r\n"), content.count(b"\n"))
        self.assertNotIn(b"\r", content.replace(b"\r\n", b""))

    def test_integrated_patch_hashes_include_the_notices(self):
        patches = json.loads((ESPEAK / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        self.assertEqual(set(patches["patches"]), set(NOTICED_PATCH_HASHES))
        for relative, checksum in NOTICED_PATCH_HASHES.items():
            with self.subTest(source=relative):
                self.assertEqual(patches["patches"][relative]["integrated_sha256"], checksum)
                self.assertEqual(digest((ESPEAK / relative).read_bytes()), checksum)

    def test_original_patch_provenance_is_retained(self):
        patches = json.loads((ESPEAK / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        self.assertEqual(patches["original_manifests"], {
            "UPSTREAM.sha256": PINNED_INPUTS["UPSTREAM.sha256"],
            "SONIC.sha256": PINNED_INPUTS["SONIC.sha256"],
        })
        upstream = read_manifest("UPSTREAM.sha256")
        sonic = read_manifest("SONIC.sha256")
        expected_previous = {
            "engine/compiledict.cpp": upstream["src/compiledict.cpp"],
            "engine/dictionary.cpp": "399da9a17624f44abf776baa642eaf66367f6a6945223119407b4ef7962dc84e",
            "engine/translate.cpp": "231876951f48ad9b71e40ee91d2b21d151dfd06150e3e797e40d1cca6808a453",
            "engine/tr_languages.cpp": "5522cc826e3e584e35b3941a14d60fb8f6b6941d6f8c11c7da41f45bc8b18794",
            "sonic/sonic.c": sonic["sonic/sonic.c"],
        }
        for relative, previous in expected_previous.items():
            with self.subTest(source=relative):
                entry = patches["patches"][relative]
                expected_original = (
                    upstream["src/" + Path(relative).name]
                    if relative.startswith("engine/") else sonic[relative]
                )
                self.assertEqual(entry["supplied_sha256"], expected_original)
                self.assertEqual(entry["previous_integrated_sha256"], previous)

    def test_pinned_data_and_original_manifests_are_unchanged(self):
        for relative, checksum in PINNED_INPUTS.items():
            with self.subTest(source=relative):
                self.assertEqual(digest((ESPEAK / relative).read_bytes()), checksum)

    def test_original_license_texts_are_unchanged(self):
        for relative, checksum in LICENSE_HASHES.items():
            with self.subTest(source=relative):
                self.assertEqual(digest((ESPEAK / relative).read_bytes()), checksum)

    def test_documentation_change_has_a_separate_exact_pin(self):
        provenance = json.loads((ESPEAK / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
        self.assertEqual(set(provenance["documentation_changes"]), {"sonic/README.md"})
        entry = provenance["documentation_changes"]["sonic/README.md"]
        original = read_manifest("SONIC.sha256")["sonic/README.md"]
        content = (ESPEAK / "sonic/README.md").read_bytes()
        self.assertEqual(entry["supplied_sha256"], original)
        self.assertEqual(digest(content[:217]), original)
        self.assertEqual(entry["notice_date"], NOTICE_DATE)
        self.assertEqual(entry["integrated_sha256"], digest(content))
        self.assertEqual(entry["integrated_sha256"],
                         "ab9b8f73bf36483bd69e7350cd24ea9d41621ed77ba5b993ab25bc71825e08fc")

    def test_missing_and_wrong_date_notices_are_rejected(self):
        cases = (
            (ESPEAK / "engine/speak_lib.cpp", ENGINE_NOTICE,
             ENGINE_BEFORE_NOTICES["speak_lib.cpp"]),
            (ESPEAK / "sonic/sonic.c", SONIC_NOTICE, SONIC_BEFORE_NOTICE),
        )
        for path, notice, checksum in cases:
            content = path.read_bytes()
            for altered in (
                content[len(notice):],
                content.replace(b"2026-10-21", b"2026-10-20", 1),
            ):
                with self.subTest(source=path.name):
                    with self.assertRaisesRegex(ValueError, "dated modification notice"):
                        validate_notice(altered, notice, checksum)

    def test_correct_notice_cannot_hide_a_source_body_change(self):
        for name, checksum in ENGINE_BEFORE_NOTICES.items():
            with self.subTest(source=name):
                altered = (ESPEAK / "engine" / name).read_bytes() + b"\n"
                with self.assertRaisesRegex(ValueError, "beyond the modification notice"):
                    validate_notice(altered, ENGINE_NOTICE, checksum)
        altered_sonic = (ESPEAK / "sonic/sonic.c").read_bytes() + b"\r\n"
        with self.assertRaisesRegex(ValueError, "beyond the modification notice"):
            validate_notice(altered_sonic, SONIC_NOTICE, SONIC_BEFORE_NOTICE)

    def test_notices_make_no_new_copyright_claim(self):
        for notice in (ENGINE_NOTICE, SONIC_NOTICE):
            self.assertNotIn(b"copyright", notice.lower())
            self.assertIn(NOTICE_DATE.encode("ascii"), notice)
            self.assertIn(b"Modified for Rockbox Accessible", notice)

    def test_documentation_identifies_dated_integration_scope(self):
        readme = (ESPEAK / "README.md").read_text(encoding="utf-8")
        sonic_readme = (ESPEAK / "sonic/README.md").read_text(encoding="utf-8")
        self.assertIn(NOTICE_DATE, readme)
        self.assertIn(NOTICE_DATE, sonic_readme)
        for name in ENGINE_BEFORE_NOTICES:
            with self.subTest(source=name):
                self.assertIn("`" + name + "`", readme)
        self.assertIn("GPL-3.0-or-later", readme)
        self.assertIn("Apache License 2.0", sonic_readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
