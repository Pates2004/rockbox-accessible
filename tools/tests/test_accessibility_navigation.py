"""Run exact root navigation, dispatcher and resume C with bounded platform mocks."""

from datetime import datetime, timezone
import hashlib
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
FIXTURE = "tools/tests/fixtures/accessibility_navigation_fixture.c"
INPUTS = ("apps/root_menu.c", "apps/root_menu.h", "tools/project_materials.py",
          "tools/tests/test_accessibility_navigation.py", FIXTURE)
VARIANTS = {
    "database": ("HAVE_TOUCHSCREEN", "HAVE_ESPEAK", "HAVE_TAGCACHE"),
    "files": ("HAVE_TOUCHSCREEN", "HAVE_ESPEAK"),
    "no-touch": ("HAVE_ESPEAK",),
    "no-espeak": ("HAVE_TOUCHSCREEN",),
}


def exact_function(source, name):
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                    lambda match: re.sub(r'[^\n]', ' ', match[0]), source, flags=re.DOTALL)
    matches = list(re.finditer(r'^(?:static\s+)?(?:inline\s+)?(?:void|bool|int)\s+' +
                              re.escape(name) + r'\s*\([^;{}]*\)\s*\{', masked, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError("Expected one production definition: " + name)
    match = matches[0]
    depth, cursor = 1, match.end()
    while depth:
        depth += (masked[cursor] == "{") - (masked[cursor] == "}")
        cursor += 1
    return source[match.start():cursor]


def replace_once(source, original, replacement):
    if source.count(original) != 1:
        raise AssertionError("Expected one bounded negative-control site: " + original)
    return source.replace(original, replacement, 1)


class AccessibilityNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "gcc"))
        if not compiler or not shutil.which(compiler[0]):
            raise unittest.SkipTest("Host C compiler unavailable; run the fixture in WSL")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.workspace = confined_path(central / "r1-gesture-extensions-20261016/navigation" / stamp, central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.inputs = {name: (ROOT / name).read_bytes() for name in INPUTS}
        cls.commands, cls.runs, cls.cases = [], [], []
        cls.binaries, cls.extractions = {}, {}
        cls.addClassCleanup(cls.report)
        source = cls.inputs["apps/root_menu.c"].decode("utf-8")
        fixture = cls.inputs[FIXTURE].decode("utf-8")
        parts = {}
        parts["NAVIGATION_API"] = source[source.index("#if defined(HAVE_TOUCHSCREEN) && defined(HAVE_ESPEAK)\nstatic int accessibility_destination"):
                                         source.index("static inline int load_screen")].strip()
        for name, token in (("wpsscrn", "WPS_FUNCTION"), ("load_screen", "LOAD_SCREEN_FUNCTION"),
                            ("ignore_back_button_stub", "IGNORE_BACK_FUNCTION"),
                            ("root_menu_setup_screens", "SETUP_FUNCTION"), ("root_menu", "ROOT_FUNCTION")):
            parts[token] = exact_function(source, name)
        match = re.search(r'^struct root_items\s*\{.*?^\};', source, re.MULTILINE | re.DOTALL)
        if match is None:
            raise AssertionError("Missing production dispatch item type")
        parts["ROOT_ITEMS_TYPE"] = match[0]
        parts["ROOT_STATE"] = "\n".join(re.search(r'^static int ' + name + r' = [^;]+;', source, re.MULTILINE)[0]
                                          for name in ("next_screen", "last_screen", "previous_music"))
        match = re.search(r'^static const struct root_items items\[\] = \{.*?^#define NUM_ITEMS[^\n]+',
                          source, re.MULTILINE | re.DOTALL)
        if match is None:
            raise AssertionError("Missing production dispatch table and count")
        parts["DISPATCH_TABLE"] = match[0]
        for token, value in parts.items():
            cls.extractions[token] = {"sha256": hashlib.sha256(value.encode()).hexdigest(),
                                      "source_line": source[:source.index(value)].count("\n") + 1
                                      if value in source else None, "bytes": len(value.encode())}
            fixture = replace_once(fixture, token, value)
        if any(token in fixture for token in parts):
            raise AssertionError("Unresolved production extraction marker")
        variants = {"actual": fixture}
        take = exact_function(source, "root_menu_take_navigation")
        variants["take-not-cleared"] = replace_once(fixture, take,
            replace_once(take, "root_menu_cancel_navigation();", ";"))
        request = exact_function(source, "root_menu_request_screen")
        variants["duplicate-overwrite"] = replace_once(fixture, request,
            replace_once(request, "if (root_menu_navigation_pending())\n        return false;", ""))
        variants["unsupported-plugin"] = replace_once(fixture, request,
            replace_once(request, "screen != GO_TO_PLAYLISTS_SCREEN", "screen != GO_TO_PLAYLISTS_SCREEN && screen != GO_TO_PLUGIN"))
        variants["loop-ignores-request"] = replace_once(fixture,
            "        if (root_menu_navigation_pending())\n            next_screen = root_menu_take_navigation();", "")
        cls.modes = ("strict", "ubsan") if sys.platform.startswith("linux") else ("strict",)
        for profile, definitions in VARIANTS.items():
            directory = cls.workspace / profile
            directory.mkdir()
            (directory / "config.h").write_text("#pragma once\n#define CONFIG_TUNER 0\n"
                "#define CONFIG_PLATFORM 0\n#define PLATFORM_ANDROID 1\n" +
                "".join("#define " + name + " 1\n" for name in definitions), encoding="utf-8")
            (directory / "gcc_extensions.h").write_text('#define NORETURN_ATTR __attribute__((noreturn))\n', encoding="utf-8")
            (directory / "root_menu.h").write_text('#include "' + (ROOT / "apps/root_menu.h").as_posix() + '"\n', encoding="utf-8")
            for mode in cls.modes:
                selected = variants if profile == "database" else {"actual": fixture}
                for mutation, content in selected.items():
                    path = directory / (mutation + ".c")
                    if not path.exists():
                        path.write_text(content, encoding="utf-8")
                    binary = directory / (mutation + "-" + mode + (".exe" if os.name == "nt" else ""))
                    arguments = compiler + ["-std=c11" if mode == "ubsan" else "-std=c99", "-O2", "-g",
                        "-Wall", "-Wextra", "-Werror", "-Wstrict-prototypes", "-Wno-unused-function", "-pedantic",
                        "-I", str(directory), str(path), "-o", str(binary)]
                    if mode == "ubsan":
                        arguments += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
                    result = cls.command(arguments)
                    if result.returncode:
                        raise AssertionError(profile + "/" + mode + "/" + mutation + ": " + result.stderr)
                    cls.binaries[(profile, mode, mutation)] = binary
        print("Navigation evidence:", cls.workspace, flush=True)

    @classmethod
    def command(cls, arguments):
        result = subprocess.run(arguments, cwd=cls.workspace, capture_output=True, text=True, timeout=30,
            env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"})
        cls.commands.append({"arguments": arguments, "returncode": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        return result

    @classmethod
    def report(cls):
        before = {name: hashlib.sha256(value).hexdigest() for name, value in cls.inputs.items()}
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
        report = {"source_project": str(ROOT), "inputs_before": before, "inputs_after": after,
            "sources_stable": before == after, "commands": cls.commands, "runs": cls.runs, "cases": cls.cases,
            "extractions": cls.extractions, "platform": sys.platform,
            "passed": before == after and bool(cls.cases) and all(case["passed"] for case in cls.cases),
            "scope": "Exact request/pending/cancel/take block, complete root_menu/setup/load_screen/wpsscrn and items table",
            "limitations": ["UI/audio/playlist/file/status/activity/event callbacks are bounded mocks, not actual screens or sound",
                "Loop exits via longjmp from the mock root menu; production loop is not patched or reimplemented",
                "No GUI, application process, radio, hardware, release build, resume IO or physical acceptance",
                "Input forbidden-context/lock/trial/cancellation integration belongs to parent tests",
                "Single UI-thread API contract; no concurrent request/consume proof",
                "UBSan runs on Linux/WSL only; native Windows requires an existing CC"]}
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if before != after:
            raise AssertionError("Navigation production/test inputs changed during checks")

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id()
                     for test, detail in result.failures + result.errors)
        self.cases.append({"name": self.id(), "passed": not failed})

    def run_case(self, scenario, profiles=("database", "files"), mutation="actual", expect_failure=False):
        for profile in profiles:
            for mode in self.modes:
                with self.subTest(profile=profile, mode=mode, scenario=scenario, mutation=mutation):
                    result = self.command([str(self.binaries[(profile, mode, mutation)]), scenario])
                    passed = result.returncode == 1 if expect_failure else result.returncode == 0
                    self.runs.append({"profile": profile, "mode": mode, "scenario": scenario,
                                      "mutation": mutation, "expected_failure": expect_failure, "passed": passed})
                    self.assertTrue(passed, result.stdout + result.stderr)
                    self.assertNotIn("runtime error:", result.stderr)
                    if expect_failure:
                        self.assertIn("fixture check failed at line", result.stderr)

    def test_exact_api_allowlist_capability_duplicate_take_cancel_and_bounds(self):
        self.run_case("api")

    def test_pending_request_overrides_root_and_normal_table_dispatches_once(self):
        self.run_case("dispatch")

    def test_consumed_request_allows_next_request_without_replaying_old_target(self):
        self.run_case("chain")

    def test_cancelled_request_does_not_dispatch(self):
        self.run_case("cancel")

    def test_previous_usb_and_exit_follow_real_return_to_root_paths(self):
        for scenario in ("previous", "usb", "exit"):
            self.run_case(scenario)

    def test_requested_wps_uses_real_play_paused_resume_missing_and_failed_resume_control(self):
        self.run_case("resume")

    def test_startup_previous_browser_and_missing_resume_are_not_reimplemented(self):
        self.run_case("startup", profiles=tuple(VARIANTS))

    def test_negative_controls_detect_take_replay_duplicate_allowlist_and_lost_consume(self):
        for mutation, scenario in (("take-not-cleared", "api"), ("duplicate-overwrite", "api"),
                                   ("unsupported-plugin", "api"), ("loop-ignores-request", "dispatch")):
            self.run_case(scenario, profiles=("database",), mutation=mutation, expect_failure=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
