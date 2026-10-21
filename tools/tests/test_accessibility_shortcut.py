"""Compile direct speech toggles with faultable availability, status and settings hosts."""

from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "apps/accessibility_shortcut.c", "apps/accessibility_shortcut.h", "apps/tts.h",
    "apps/talk.h", "apps/settings.h", "tools/tests/test_accessibility_shortcut.py",
    "tools/tests/fixtures/accessibility_shortcut_fixture.c",
)
LABELS = (
    "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON", "LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF",
    "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON", "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF",
    "LANG_ACCESSIBILITY_SHORTCUT_FAILED", "LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING",
)
COUNTERS = ("TALK_INIT", "DEBUG", "CHANGED", "AVAILABLE", "STATUS", "SAVE", "SPLASH")

HOST = r'''
#ifndef SHORTCUT_TEST_HOST_H
#define SHORTCUT_TEST_HOST_H
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lang.h"
#include "accessibility_shortcut.h"
#include "tts.h"
#define HZ 100
const unsigned char *str(int label);
void splashf_silent(int ticks, const char *format, ...);
void talk_init(void);
int settings_save(void);
'''


def scenarios():
    cases = []
    for previous, menu, engine, catalog, status, volume in itertools.product(
            range(2), range(2), range(2), range(2), (0, -1), (0, 37)):
        cases.append((f"direct_espeak_{previous}_voice_{menu}_engine_{engine}_"
                      f"catalog_{catalog}_status_{status}_volume_{volume}", "espeak",
                      (previous, menu, engine, catalog, status, volume, 0)))
    for tts, previous, present, status, volume in itertools.product(
            range(2), range(2), range(2), (0, -1), (0, 37)):
        cases.append((f"direct_voice_tts_{tts}_previous_{previous}_file_{present}_"
                      f"status_{status}_volume_{volume}", "voice",
                      (tts, previous, present, status, volume, 0)))
    for save_result in (-1, 1):
        for previous in range(2):
            cases.append((f"espeak_deferred_save_return_{save_result}_previous_{previous}",
                          "espeak", (previous, 0, 1, 1, 0, 37, save_result)))
            for tts in range(2):
                cases.append((f"voice_deferred_save_return_{save_result}_"
                              f"tts_{tts}_previous_{previous}", "voice",
                              (tts, previous, 1, 0, 37, save_result)))
    for voice, tts in itertools.product(range(2), repeat=2):
        cases.append((f"repeated_direct_toggle_voice_{voice}_tts_{tts}", "repeat", (voice, tts)))
    for voice in range(2):
        cases.append((f"failed_toggle_can_retry_voice_{voice}", "retry", (voice,)))
    return cases


def production_declaration(source, pattern):
    matches = re.findall(pattern, source, re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise AssertionError(f"Expected one production declaration: {pattern}")
    return matches[0]


def build_hosts(workspace, variants):
    includes = workspace / "include"
    includes.mkdir()
    (includes / "config.h").write_text("#pragma once\n", encoding="utf-8")
    labels = "#pragma once\nenum {" + ",".join(LABELS) + ",LANG_TEST_COUNT};\n"
    (includes / "lang.h").write_text(labels, encoding="utf-8")
    for header in ("accessibility_shortcut.h", "tts.h"):
        path = (ROOT / "apps" / header).as_posix()
        (includes / header).write_text(f'#include "{path}"\n', encoding="utf-8")
    settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
    host = HOST + "\nstruct user_settings {\n"
    for field in ("tts_enabled", "talk_menu", "talk_mixer_amp", "tts_volume", "talk_dir",
                  "talk_file", "talk_dir_clip", "talk_file_clip", "tts_ducking",
                  "tts_ducking_level"):
        host += production_declaration(settings, r"^\s*((?:bool|int)\s+" + field + r"\s*;)") + "\n"
    host += "};\nextern struct user_settings global_settings;\n"
    talk = (ROOT / "apps/talk.h").read_text(encoding="utf-8")
    host += production_declaration(talk, r"(enum talk_status\s*\{.*?\};)") + "\n"
    host += production_declaration(talk, r"(struct talk_debug_data\s*\{.*?\};)") + "\n"
    host += "bool talk_get_debug_data(struct talk_debug_data *data);\n"
    host += "enum {" + ",".join("C_" + name for name in COUNTERS) + ",C_COUNT};\n#endif\n"
    (includes / "host.h").write_text(host, encoding="utf-8")
    for header in ("kernel.h", "settings.h", "splash.h", "talk.h"):
        (includes / header).write_text('#include "host.h"\n', encoding="utf-8")
    module = workspace / "production-accessibility-shortcut.c"
    module.write_bytes((ROOT / INPUTS[0]).read_bytes())
    inputs = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
    manifest = {
        "source_project": str(ROOT), "inputs": inputs, "builds": {},
        "copy_purpose": "One unchanged production translation unit for isolated mock includes; retained for reproduction.",
        "scope": "Complete direct-toggle module; mocked TTS/settings. No legacy file or menu headers/hosts, hardware or real audio.",
    }
    binaries = {}
    for variant in variants:
        windows = variant == "windows"
        compiler = shlex.split(os.environ.get("SHORTCUT_WINDOWS_CC" if windows else "CC",
                                             "x86_64-w64-mingw32-gcc" if windows else "cc"))
        if not compiler or not shutil.which(compiler[0]):
            raise unittest.SkipTest(f"Compiler unavailable: {compiler}")
        binary = workspace / ("shortcut-" + variant + (".exe" if windows else ""))
        command = compiler + ["-std=c99", "-O2", "-g", "-Wall", "-Wextra", "-Werror",
                              "-DHAVE_ESPEAK", "-I", str(includes), str(module),
                              str(ROOT / "tools/tests/fixtures/accessibility_shortcut_fixture.c"),
                              "-o", str(binary)]
        if variant == "ubsan":
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
        manifest["builds"][variant] = {
            "command": command, "returncode": compiled.returncode,
            "stdout": compiled.stdout, "stderr": compiled.stderr,
        }
        (workspace / "build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if compiled.returncode:
            raise AssertionError(f"{variant} build failed:\n{compiled.stdout}{compiled.stderr}")
        manifest["builds"][variant]["sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        binaries[variant] = binary
    stub = workspace / "without-espeak.c"
    stub.write_text('''#include <assert.h>
#include "accessibility_shortcut.h"
int main(void)
{
    assert(!accessibility_shortcut_toggle_espeak());
    assert(!accessibility_shortcut_toggle_voice_files());
    assert(!accessibility_shortcut_toggle_espeak());
    assert(!accessibility_shortcut_toggle_voice_files());
    return 0;
}
''', encoding="utf-8")
    compiler = shlex.split(os.environ.get("CC", "cc"))
    stub_binary = workspace / "shortcut-without-espeak"
    command = compiler + ["-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(includes),
                          str(module), str(stub), "-o", str(stub_binary)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
    manifest["builds"]["without-espeak"] = {
        "command": command, "returncode": compiled.returncode,
        "stdout": compiled.stdout, "stderr": compiled.stderr,
    }
    if compiled.returncode == 0:
        manifest["builds"]["without-espeak"]["sha256"] = hashlib.sha256(stub_binary.read_bytes()).hexdigest()
    (workspace / "build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if compiled.returncode:
        raise AssertionError(f"Non-eSpeak build failed:\n{compiled.stderr}")
    return binaries, stub_binary


class AccessibilityShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        variants = os.environ.get("SHORTCUT_VARIANTS", "plain,ubsan").split(",")
        if not variants or any(item not in ("plain", "ubsan", "windows") for item in variants):
            raise AssertionError("SHORTCUT_VARIANTS must select plain,ubsan,windows")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.workspace = confined_path(central / "r1-input-refinements-20261017" / "shortcut" / stamp, central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.outcomes = []
        cls.interface_checks = []
        cls.expected_execution_count = len(scenarios()) * len(variants) + 1
        cls.addClassCleanup(cls.report)
        print(f"Shortcut evidence: {cls.workspace}", flush=True)
        cls.binaries, cls.stub_binary = build_hosts(cls.workspace, variants)

    @classmethod
    def report(cls):
        report = {
            "source_project": str(ROOT), "executions": cls.outcomes,
            "execution_count": len(cls.outcomes),
            "expected_execution_count": cls.expected_execution_count,
            "interface_checks": cls.interface_checks,
            "passed": len(cls.outcomes) == cls.expected_execution_count and
                      len(cls.interface_checks) == 2 and
                      all(item["returncode"] == 0 for item in cls.outcomes),
            "limitations": [
                "TTS/status enqueue and settings persistence are mocked; no measured PCM, flash durability or physical R1/NVDA acceptance.",
                "Parent owns menu/catalog/docs integration. Current maps stay unchanged; public-only triple Power is outside this module.",
                "While eSpeak is selected globally, voice-file activation changes the inactive preference without validating or reloading its catalog.",
                "If status synthesis fails, only silent visual status is available; user TTS volume is never raised.",
                "settings_save schedules deferred persistence; its synthetic return values are not a storage durability or error-reporting contract.",
            ],
        }
        (cls.workspace / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def run_scenario(self, name, scenario, parameters):
        for variant, binary in self.binaries.items():
            with self.subTest(variant=variant):
                command = [str(binary), scenario, *map(str, parameters)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.outcomes.append({"case": name, "variant": variant, "returncode": result.returncode,
                                      "stdout": result.stdout, "stderr": result.stderr})
                self.assertEqual(result.returncode, 0,
                                 f"{name}/{variant}:\n{result.stdout}{result.stderr}")

    def test_public_api_contains_only_direct_toggles(self):
        header = (ROOT / "apps/accessibility_shortcut.h").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"\bbool\s+(\w+)\s*\(void\)\s*;", header), [
            "accessibility_shortcut_toggle_espeak", "accessibility_shortcut_toggle_voice_files"])
        self.assertNotRegex(header, r"\benum\b|\b(?:void|int)\s+accessibility_shortcut_")
        self.interface_checks.append("only_two_direct_toggle_declarations")

    def test_no_legacy_policy_file_or_menu_dependency(self):
        source = (ROOT / "apps/accessibility_shortcut.c").read_text(encoding="utf-8")
        header = (ROOT / "apps/accessibility_shortcut.h").read_text(encoding="utf-8")
        self.assertNotRegex(source + header,
                            r"\baccessibility_shortcut_(?:init|load|enabled|service|activate)\w*\b|"
                            r"\bshortcut_activate_service\b|accessibility-shortcut\.cfg|"
                            r"RBACCESSIBILITY-SHORTCUT|\bSHORTCUT_(?:FILE|TEMP|PREFIX|SERVICE)\b")
        self.assertNotRegex(source, r'#include\s+"(?:file|menu|rbpaths)\.h"')
        self.assertNotRegex(source, r"\b(?:open|read|write|fsync|close|rename|remove|set_option)\s*\(")
        self.interface_checks.append("no_legacy_policy_file_or_menu_dependency")

    def test_without_espeak_build_links_without_speech_dependencies(self):
        result = subprocess.run([str(self.stub_binary)], capture_output=True, text=True, timeout=15)
        self.outcomes.append({"case": "without_espeak", "variant": "stub", "returncode": result.returncode,
                              "stdout": result.stdout, "stderr": result.stderr})
        self.assertEqual(result.returncode, 0, result.stderr)


def scenario_test(name, scenario, parameters):
    def test(self):
        self.run_scenario(name, scenario, parameters)
    return test


for scenario_name, fixture_scenario, fixture_parameters in scenarios():
    setattr(AccessibilityShortcutTests, "test_" + scenario_name,
            scenario_test(scenario_name, fixture_scenario, fixture_parameters))


if __name__ == "__main__":
    unittest.main(verbosity=2)
