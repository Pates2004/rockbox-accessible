"""Compile and execute the actual connectivity controller with isolated services."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/hiby_connectivity.c"
HEADER = SOURCE.with_suffix(".h")
FIXTURE = ROOT / "tools/tests/fixtures/hiby_connectivity_fixture.c"
INPUTS = (SOURCE, HEADER, FIXTURE, Path(__file__).resolve(), ROOT / "apps/hiby_bluetooth.h",
          ROOT / "apps/hiby_bluetooth_service.h",
          ROOT / "firmware/target/hosted/hiby/bluetooth-hiby.h",
          ROOT / "firmware/target/hosted/hiby/power-control-hiby.h")
STORAGE_CASES = ("none", "open", "write", "zero", "short", "write-eintr", "write-storm",
                 "fsync", "close", "rename", "stale-temp", "read-open", "read-error",
                 "read-short", "read-eintr", "read-storm", "read-close")
INVALID_CASES = ("version", "trailing", "truncated", "nul", "value", "space", "empty", "oversized")
POLICY_CASES = ("defaults", "restore-both", "restore-wifi", "restore-bt", "restore-neither",
                "saved-airplane")
RADIO_CASES = ("none", "mixed-soft", "hard-any", "interface-up", "no-wlan", "no-bt",
               "wifi-write", "wifi-interface-write", "wifi-write-read", "wifi-state-error",
               "wifi-read", "wifi-interface-read", "bt-reject", "bt-write", "bt-read",
               "bt-unknown", "bt-hang", "bt-timeout", "bt-reject-ok", "bt-stale",
               "bt-available-false", "bt-thread", "wifi-counts", "wifi-suspended",
               "wifi-driver-error", "wifi-unsettled")
CANCEL_CASES = ("queued", "active", "airplane", "existing", "preempt", "shutdown", "unsettled")
RACE_CASES = ("cancel", "airplane", "shutdown")
SERVICE_GATE_CASES = ("enabled", "startup", "disabled", "airplane", "storage", "error",
                      "unknown", "stale", "unavailable", "wifi-unsettled", "transition",
                      "pending-airplane", "cancel", "shutdown", "unsettled",
                      "race-cancel", "race-airplane", "race-shutdown")


def disable_core_dump():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


@unittest.skipUnless(sys.platform.startswith("linux"), "Requires Linux compiler; run under WSL")
class HibyConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("gcc")
        if not cls.compiler:
            raise unittest.SkipTest("gcc unavailable")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        evidence_root = confined_path(Path(os.environ.get("HIBY_RADIO_TEST_ROOT", central)), central, allow_root=True)
        cls.evidence = confined_path(evidence_root / "hiby-connectivity-tests" / stamp, central)
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands = []
        cls.cases = []
        cls.test_runs = []
        cls.native_probe = None
        cls.before = cls.hashes()
        cls.addClassCleanup(cls.report)
        cls.headers = cls.evidence / "headers"
        cls.headers.mkdir()
        for name in ("config.h", "file.h", "action.h", "kernel.h", "lang.h", "language.h",
                     "list.h", "menu.h", "misc.h", "splash.h", "talk.h"):
            (cls.headers / name).write_text("#pragma once\n", encoding="utf-8")
        (cls.headers / "rbpaths.h").write_text('#define ROCKBOX_DIR "/.rockbox"\n', encoding="utf-8")
        cls.labels = sorted(set(re.findall(r"\bLANG_[A-Z_]+", SOURCE.read_text(encoding="utf-8"))))
        definitions = "\n".join(f"#define {label} {1000 + index}" for index, label in enumerate(cls.labels))
        definitions += f"\n#define CONNECTIVITY_LABEL_COUNT {len(cls.labels)}\n"
        definitions += "static const char *const connectivity_labels[] = {\n"
        definitions += ",\n".join(json.dumps(label) for label in cls.labels) + "\n};\n"
        (cls.headers / "connectivity-labels.h").write_text(definitions, encoding="utf-8")
        cls.executables = {}
        serialized = """        if (enabled)
        {
            LOCK();
            if (!operation_cancelled() && !state.airplane_mode && !stopping)
                hiby_bluetooth_set_inhibited(false);
            UNLOCK();
        }"""
        unlocked = """        if (enabled && !operation_cancelled())
            hiby_bluetooth_set_inhibited(false);"""
        production = SOURCE.read_text(encoding="utf-8")
        if production.count(serialized) != 1:
            raise AssertionError("Cannot build the exact pre-fix uninhibit mutation")
        mutation = cls.evidence / "unlocked-connectivity.c"
        mutation.write_text(production.replace(serialized, unlocked, 1), encoding="utf-8")
        cls.mutation = {
            "file": str(mutation), "sha256": hashlib.sha256(mutation.read_bytes()).hexdigest(),
            "production_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "change": "Only the serialized check/uninhibit block reverted to the pre-fix implementation",
            "purpose": "Retained negative control proving that real pthread races detect stale uninhibition",
        }
        reuse = """    enum hiby_bt_error observed = HIBY_BT_OK;
    if (!change || changed != HIBY_BT_OK || !snapshot.available || !snapshot.power_known ||
        snapshot.connected_address[0])
        observed = snapshot.busy ? HIBY_BT_TIMEOUT :
            bluetooth_operation(HIBY_BT_REFRESH, &snapshot, cleanup);"""
        redundant = """    enum hiby_bt_error observed = snapshot.busy ? HIBY_BT_TIMEOUT :
        bluetooth_operation(HIBY_BT_REFRESH, &snapshot, cleanup);"""
        asynchronous_entry = """    struct connectivity_menu menu = { .wifi_only = wifi_only };
    if (!wifi_only)
        request_menu_refresh(&menu);"""
        modal_entry = """    struct connectivity_menu menu = { .wifi_only = wifi_only };
    if (!wifi_only)
    {
        request_menu_refresh(&menu);
        show_result(LANG_HIBY_BT_DONE);
    }"""
        cls.radio_mutations = {}
        for name, old, new in (("duplicate-refresh", reuse, redundant),
                               ("entry-done", asynchronous_entry, modal_entry)):
            if production.count(old) != 1:
                raise AssertionError(f"Cannot build exact radio mutation: {name}")
            path = cls.evidence / (name + ".c")
            path.write_text(production.replace(old, new, 1), encoding="utf-8")
            cls.radio_mutations[name] = {"file": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        gate = re.search(r"    hiby_bluetooth_service_allow\(!state\.inhibited.*?;", production, re.DOTALL)
        if gate is None or production.count(gate[0]) != 1:
            raise AssertionError("Cannot identify the unique final Bluetooth service gate")
        for name, replacement in (("service-ungated", "    hiby_bluetooth_service_allow(true);"),
                                   ("service-missing", "    hiby_bluetooth_service_allow(false);")):
            path = cls.evidence / (name + ".c")
            path.write_text(production.replace(gate[0], replacement, 1), encoding="utf-8")
            cls.radio_mutations[name] = {"file": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        early = """        if (enabled)
            hiby_bluetooth_service_allow(true);
"""
        path = cls.evidence / "service-early.c"
        path.write_text(production.replace(serialized, early + serialized, 1), encoding="utf-8")
        cls.radio_mutations["service-early"] = {"file": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for variant in ("native", "ubsan", "simulator", "simulator-ubsan", "unlocked", "unlocked-ubsan",
                        "duplicate-refresh", "duplicate-refresh-ubsan", "entry-done", "entry-done-ubsan",
                        "service-ungated", "service-ungated-ubsan", "service-missing", "service-missing-ubsan",
                        "service-early", "service-early-ubsan"):
            binary = cls.evidence / variant
            arguments = [cls.compiler, "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                         "-pthread", "-DHIBY_LINUX", "-DHIBY_CONNECTIVITY_BT_WAIT_MS=100",
                         "-DHIBY_CONNECTIVITY_SETTLE_MS=100", "-I", str(cls.headers),
                         "-I", str(ROOT / "apps"), "-I", str(ROOT / "firmware/target/hosted/hiby"),
                         str(FIXTURE), "-o", str(binary)]
            if "simulator" in variant:
                arguments += ["-DSIMULATOR", "-DHIBY_CONNECTIVITY_HOST_TEST"]
            if "ubsan" in variant:
                arguments += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            if "unlocked" in variant:
                arguments += ['-DCONNECTIVITY_TEST_SOURCE="' + str(mutation) + '"']
            for name, details in cls.radio_mutations.items():
                if variant == name or variant == name + "-ubsan":
                    arguments += ['-DCONNECTIVITY_TEST_SOURCE="' + details["file"] + '"']
            cls.command(arguments)
            symbols = cls.command(["nm", "-u", str(binary)]).stdout
            imports = {line.split()[-1].split("@")[0] for line in symbols.splitlines() if line.split()}
            forbidden = imports.intersection({"open", "open64", "read", "write", "close", "fsync",
                "rename", "remove", "socket", "ioctl", "system", "fork", "posix_spawn", "execve"})
            if forbidden:
                raise AssertionError(f"Unmocked radio/storage/process imports: {forbidden}")
            cls.executables[variant] = binary
        print("Connectivity evidence:", cls.evidence, flush=True)

    @classmethod
    def hashes(cls):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in INPUTS}

    @classmethod
    def command(cls, arguments, expected_returncode=0):
        result = subprocess.run(arguments, cwd=cls.evidence, capture_output=True, text=True,
                                timeout=45, preexec_fn=disable_core_dump,
                                env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"})
        cls.commands.append({"arguments": arguments, "returncode": result.returncode,
                             "expected_returncode": expected_returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode != expected_returncode:
            raise AssertionError(shlex.join(arguments) + "\n" + result.stdout + result.stderr)
        return result

    @classmethod
    def report(cls):
        after = cls.hashes()
        report = {"source_project": str(ROOT), "inputs_before": cls.before, "inputs_after": after,
                  "sources_unchanged": cls.before == after, "commands": cls.commands, "cases": cls.cases,
                  "native_probe": cls.native_probe,
                  "mutation": getattr(cls, "mutation", None),
                  "radio_mutations": getattr(cls, "radio_mutations", None),
                  "test_runs": cls.test_runs,
                  "scope": "Actual production connectivity C module, real pthread worker and race barriers, strict fake storage/WLAN/BT/UI, plus labelled pre-fix mutation controls",
                  "limitations": "No physical radios, RF power/energy, physical R1, live NVDA/TalkBack or complete package",
                  "passed": bool(cls.cases) and cls.before == after and
                            all(case["passed"] for case in cls.cases) and
                            all(test["passed"] for test in cls.test_runs) and
                            all(command["returncode"] == command["expected_returncode"] for command in cls.commands)}
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("Connectivity report:", cls.evidence / "report.json", flush=True)
        if cls.before != after:
            raise AssertionError("Owned source files changed during tests")

    def run(self, result=None):
        result = result if result is not None else self.defaultTestResult()
        before = len(result.failures) + len(result.errors)
        returned = super().run(result)
        if hasattr(self.__class__, "test_runs"):
            self.test_runs.append({"name": self.id(),
                "passed": len(result.failures) + len(result.errors) == before})
        return returned

    def run_cases(self, family, cases, variants=("native", "ubsan")):
        for variant in variants:
            for mode in cases:
                with self.subTest(variant=variant, family=family, mode=mode):
                    passed = False
                    try:
                        self.command([str(self.executables[variant]), family, mode])
                        passed = True
                    finally:
                        self.cases.append({"variant": variant, "family": family, "mode": mode, "passed": passed})

    def test_storage_atomicity_errors_and_bounded_interrupts(self):
        self.run_cases("storage", STORAGE_CASES)

    def test_strict_versioned_config(self):
        self.run_cases("invalid", INVALID_CASES)

    def test_startup_and_airplane_restore_preferences(self):
        self.run_cases("policy", POLICY_CASES)

    def test_actual_readback_errors_and_partial_states(self):
        self.run_cases("radio", RADIO_CASES)

    def test_successful_observed_mutations_avoid_duplicate_refresh_but_failures_do_not(self):
        self.run_cases("observed-transaction", ("enable", "disable", "refresh", "connected-route", "bt-unknown",
                       "bt-write", "bt-read", "bt-available-false", "bt-stale"))

    def test_radio_negative_controls_reproduce_duplicate_refresh_and_entry_done(self):
        for name, family, modes in (("duplicate-refresh", "observed-transaction", ("enable", "disable")),
                                    ("entry-done", "ui", ("entry-success",))):
            for variant in (name, name + "-ubsan"):
                for mode in modes:
                    with self.subTest(variant=variant, mode=mode):
                        result = self.command([str(self.executables[variant]), family, mode],
                                              expected_returncode=-signal.SIGABRT)
                        self.assertIn("Assertion", result.stderr)
                        self.cases.append({"variant": variant, "family": family, "mode": mode,
                                           "expected_abort": True, "passed": True})

    def test_cancel_preemption_settlement_and_shutdown(self):
        self.run_cases("cancel", CANCEL_CASES)

    def test_repeated_busy_requests_do_not_change_preference_or_conflict(self):
        self.run_cases("busy-activation", ("repeat", "error", "fast-disable"))

    def test_uninhibit_serializes_against_cancel_airplane_shutdown(self):
        self.run_cases("race", RACE_CASES)

    def test_unlocked_mutation_reproduces_the_race(self):
        for variant in ("unlocked", "unlocked-ubsan"):
            for mode in RACE_CASES:
                with self.subTest(variant=variant, mode=mode):
                    result = self.command([str(self.executables[variant]), "race", mode],
                                          expected_returncode=-signal.SIGABRT)
                    self.assertIn("stale_uninhibits=1", result.stdout)
                    self.assertIn("race_stale_uninhibits == 0", result.stderr)
                    self.cases.append({"variant": variant, "family": "race", "mode": mode,
                                       "expected_abort": True, "passed": True})

    def test_idle_worker_does_not_poll(self):
        self.run_cases("idle", ("none",))

    def test_service_only_allowed_after_confirmed_committed_uninhibited_bluetooth_on(self):
        self.run_cases("service-gate", SERVICE_GATE_CASES)

    def test_service_gate_negative_controls_reject_early_unconditional_and_missing_allow(self):
        for mutation, mode in (("service-ungated", "disabled"), ("service-ungated", "storage"),
                               ("service-missing", "enabled"), ("service-early", "transition")):
            for variant in (mutation, mutation + "-ubsan"):
                with self.subTest(variant=variant, mode=mode):
                    result = self.command([str(self.executables[variant]), "service-gate", mode],
                                          expected_returncode=-signal.SIGABRT)
                    self.assertIn("Assertion", result.stderr)
                    self.cases.append({"variant": variant, "family": "service-gate", "mode": mode,
                                       "expected_abort": True, "passed": True})

    def test_worker_creation_failure_and_recovery(self):
        self.run_cases("thread", ("create-failure", "restart-failure"))

    def test_menu_switch_speech_child_and_cancel(self):
        self.run_cases("ui", ("menu", "cancel", "usb", "child-usb", "list-usb", "thread-failed", "unknown", "interface-down", "driver-suspended"))

    def test_passive_menu_entry_speaks_wifi_without_done_and_retains_errors(self):
        self.run_cases("ui", ("entry-success", "entry-failed"))

    def test_passive_refresh_keeps_selected_navigation_and_speech_while_busy(self):
        self.run_cases("ui", ("entry-live",))

    def test_simulator_exposes_preferences_without_backend_calls(self):
        self.run_cases("policy", POLICY_CASES, ("simulator", "simulator-ubsan"))
        self.run_cases("storage", STORAGE_CASES, ("simulator", "simulator-ubsan"))
        self.run_cases("ui", ("menu",), ("simulator", "simulator-ubsan"))

    def test_native_r1_translation_unit_with_actual_headers(self):
        central = project_materials_root(ROOT)
        build = Path(os.environ.get("HIBY_CONNECTIVITY_NATIVE_BUILD", central / "build-espeak-hibyr1"))
        makefile = build / "Makefile"
        if not makefile.is_file():
            self.skipTest("Configure native R1 or set HIBY_CONNECTIVITY_NATIVE_BUILD")
        configuration = makefile.read_text(encoding="utf-8")

        def exported(name):
            matched = re.search(r"^export " + re.escape(name) + r"=(.*)$", configuration, re.MULTILINE)
            self.assertIsNotNone(matched, name)
            return matched[1].strip()

        self.assertEqual(exported("MODELNAME"), "hibyr1")
        compiler = exported("CC")
        native = self.evidence / "native-tu"
        native.mkdir()
        native_inputs = [makefile, build / "autoconf.h", build / "lang_enum.h", build / "rbversion.h"]
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in native_inputs}
        lang_header = (build / "lang_enum.h").read_text(encoding="utf-8")
        absent = [label for label in self.labels if not re.search(r"\b" + label + r"\b", lang_header)]
        missing = native / "pending-language-ids.h"
        missing.write_text("\n".join(f"#define {label} {30000 + index}" for index, label in enumerate(absent)) + "\n",
                           encoding="utf-8")
        directories = [build, build / "lang"] + [ROOT / relative for relative in (
            "firmware", "firmware/export", "firmware/drivers", "firmware/include", "firmware/kernel/include",
            "apps", "apps/gui", "apps/recorder", "apps/radio", "lib/rbcodec", "lib/rbcodec/dsp",
            "lib/rbcodec/metadata", "lib/rbcodec/codecs", "lib/skin_parser", "lib/fixedpoint",
            "uisimulator/common", "firmware/target/hosted/hiby/r1", "firmware/target/hosted/hiby",
            "firmware/target/hosted")]
        arguments = [compiler] + ["-I" + str(path) for path in directories]
        arguments += ["-DROCKBOX", "-DHIBY_R1", "-DMEMORYSIZE=" + exported("MEMORYSIZE"),
                      "-DTARGET_ID=" + exported("TARGET_ID"), '-DTARGET_NAME="hibyr1"']
        arguments += shlex.split(exported("EXTRA_DEFINES")) + shlex.split(exported("GCCOPTS"))
        arguments += ["-Werror", "-Werror=implicit-function-declaration", "-include", str(missing),
                      "-c", str(SOURCE), "-o", str(native / "hiby_connectivity.o")]
        self.command(arguments)
        after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in native_inputs}
        self.assertEqual(before, after, "Native build configuration changed during translation-unit probe")
        self.__class__.native_probe = {"compiler": compiler, "build": str(build), "actual_headers": True,
                             "inputs_before": before, "inputs_after": after,
                             "pending_language_id_shim": absent, "object_executed": False,
                             "sha256": hashlib.sha256((native / "hiby_connectivity.o").read_bytes()).hexdigest()}


if __name__ == "__main__":
    unittest.main(verbosity=2)
