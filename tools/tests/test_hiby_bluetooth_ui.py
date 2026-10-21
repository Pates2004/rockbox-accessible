"""Run the actual Bluetooth menu with isolated radio, controller and input mocks."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/hiby_bluetooth.c"
FIXTURE = Path(__file__).with_name("fixtures") / "hiby_bluetooth_ui_fixture.c"


def read_labels(language, identifiers):
    text = (ROOT / "apps/lang" / (language + ".lang")).read_text(encoding="utf-8")
    phrases = re.findall(r"<phrase>(.*?)</phrase>", text, re.DOTALL)
    labels = {}
    for identifier in identifiers:
        matching = [phrase for phrase in phrases if re.search(r"(?m)^\s*id:\s*" + re.escape(identifier) + r"\s*$", phrase)]
        if len(matching) != 1:
            raise AssertionError(f"{language}: expected one {identifier}, found {len(matching)}")
        labels[identifier] = {}
        for section in ("dest", "voice"):
            matched = re.search("<" + section + ">(.*?)</" + section + ">", matching[0], re.DOTALL)
            if not matched:
                raise AssertionError(f"{language}: missing {section} for {identifier}")
            targets = dict(re.findall(r"(?m)^\s*([^\s:]+):\s*(.*?)\s*$", matched[1]))
            value = targets.get("hibyr1", targets.get("*", "none"))
            if value in ("none", '""'):
                raise AssertionError(f"{language}: empty {section} for {identifier}")
            labels[identifier][section] = json.loads(value)
    return labels


@unittest.skipUnless(os.name == "posix" and shutil.which("gcc"), "requires the isolated POSIX C fixture")
class BluetoothUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        central = project_materials_root(ROOT)
        evidence_root = confined_path(Path(os.environ.get("HIBY_RADIO_TEST_ROOT", central)), central, allow_root=True)
        cls.evidence = evidence_root / "bluetooth-ui" / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True)
        cls.builds = []
        cls.executions = []
        cls.binaries = []
        cls.test_runs = []
        cls.import_checks = []
        ui_source = SOURCE.read_text(encoding="utf-8")
        ui_source = ui_source[ui_source.index("enum bluetooth_ui_result"):].rsplit("#endif", 1)[0]
        (cls.evidence / "bluetooth-ui-source.inc").write_text(ui_source, encoding="utf-8")
        (cls.evidence / "config.h").write_text("", encoding="ascii")
        cls.identifiers = sorted(set(re.findall(r"\bLANG_[A-Z0-9_]+\b", ui_source + FIXTURE.read_text(encoding="utf-8"))))
        cls.languages = {language: read_labels(language, cls.identifiers) for language in ("english", "polski")}
        cls.paths = (SOURCE, SOURCE.with_suffix(".h"), ROOT / "apps/hiby_connectivity.h",
                     ROOT / "apps/hiby_bluetooth_settings.h", ROOT / "apps/hiby_bluetooth_service.h",
                     ROOT / "apps/bluetooth_policy.h",
                     ROOT / "apps/lang/english.lang", ROOT / "apps/lang/polski.lang",
                     ROOT / "firmware/target/hosted/hiby/bluetooth-hiby.h", FIXTURE, Path(__file__).resolve())
        cls.hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.paths}
        cls.addClassCleanup(cls.report)
        for language, labels in cls.languages.items():
            directory = cls.evidence / language
            directory.mkdir()
            definitions = "enum { " + ", ".join(cls.identifiers) + " };\n"
            for symbol, section in (("test_language", "dest"), ("test_voice_language", "voice")):
                definitions += "static const char *const " + symbol + "[] = {\n"
                definitions += ",\n".join(json.dumps(labels[identifier][section]) for identifier in cls.identifiers) + "\n};\n"
            (directory / "bluetooth-ui-language.h").write_text(definitions, encoding="utf-8")
            for variant in ("native", "native-sanitized", "simulator", "simulator-sanitized"):
                simulator = variant.startswith("simulator")
                sanitized = variant.endswith("sanitized")
                executable = directory / variant
                arguments = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wformat=2", "-Wshadow", "-Wconversion", "-O1", "-g",
                             "-I", str(ROOT / "apps"), "-I", str(ROOT / "firmware/target/hosted/hiby"), "-I", str(directory), "-I", str(cls.evidence)]
                if sanitized:
                    arguments += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
                if simulator:
                    arguments += ["-DSIMULATOR", "-DHIBY_BT_NO_UI", str(SOURCE)]
                arguments += [str(FIXTURE), "-o", str(executable)]
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
                cls.builds.append({"language": language, "arguments": arguments, "returncode": result.returncode,
                                   "stdout": result.stdout, "stderr": result.stderr})
                (cls.evidence / "builds.json").write_text(json.dumps(cls.builds, indent=2), encoding="utf-8")
                if result.returncode:
                    raise RuntimeError(result.stderr)
                symbols = subprocess.run(["nm", "-u", str(executable)], capture_output=True, text=True, timeout=10)
                imports = {line.split()[-1].split("@")[0] for line in symbols.stdout.splitlines() if line.split()}
                forbidden = sorted(imports.intersection({"open", "open64", "read", "write", "close", "fsync",
                    "rename", "remove", "socket", "ioctl", "system", "fork", "posix_spawn", "execve", "popen"}))
                cls.import_checks.append({"executable": str(executable), "returncode": symbols.returncode,
                    "imports": sorted(imports), "forbidden": forbidden, "stderr": symbols.stderr})
                if symbols.returncode or forbidden:
                    raise AssertionError(f"UI fixture imports unmocked host operations: {forbidden}; {symbols.stderr}")
                cls.binaries.append((language, sanitized, simulator, executable))

    @classmethod
    def report(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.paths}
        languages_after = {language: read_labels(language, cls.identifiers) for language in cls.languages}
        report = {"source_project": str(ROOT), "hardware_tested": False, "host_radio_calls": False,
                  "global_input": False, "source_sha256": cls.hashes, "source_sha256_after": after,
                  "source_unchanged": cls.hashes == after, "builds": cls.builds, "executions": cls.executions,
                  "languages": cls.languages, "languages_unchanged": cls.languages == languages_after,
                  "test_runs": cls.test_runs,
                  "import_checks": cls.import_checks,
                  "scope": "Actual UI functions with isolated effective preference and controller mocks, PL/EN, normal and ASan/UBSan; not the preferences storage or Bluetooth service implementation",
                  "passed": bool(cls.executions) and len(cls.builds) == 8 and
                            all(item["returncode"] == 0 for item in cls.builds) and
                            len(cls.import_checks) == 8 and all(item["returncode"] == 0 and not item["forbidden"] for item in cls.import_checks) and
                            bool(cls.test_runs) and all(item["passed"] for item in cls.test_runs) and
                            cls.hashes == after and cls.languages == languages_after and all(item["returncode"] == 0 for item in cls.executions)}
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Bluetooth UI evidence:", cls.evidence)
        if cls.hashes != after or cls.languages != languages_after:
            raise AssertionError("UI source or PL/EN labels changed during the test run")

    def run(self, result=None):
        result = result if result is not None else self.defaultTestResult()
        before = len(result.failures) + len(result.errors)
        returned = super().run(result)
        if hasattr(self.__class__, "test_runs"):
            self.test_runs.append({"name": self.id(),
                "passed": len(result.failures) + len(result.errors) == before})
        return returned

    def check_scenario(self, scenario, *, simulator=False):
        for language, sanitized, binary_simulator, executable in self.binaries:
            if binary_simulator != simulator:
                continue
            with self.subTest(language=language, sanitized=sanitized):
                result = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=10,
                                        env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1"})
                self.executions.append({"scenario": scenario, "language": language, "sanitized": sanitized, "returncode": result.returncode,
                                        "simulator": simulator,
                                        "stdout": result.stdout, "stderr": result.stderr})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "verified-bluetooth-ui=" + scenario + "\n")

    def test_seven_entries_preserve_first_five_and_unknown_power_label(self):
        self.check_scenario("menu_unknown")

    def test_switch_text_and_speech_distinguish_requested_and_actual_state(self):
        for scenario in ("requested_on_actual_off", "requested_off_actual_on", "requested_on_unknown",
                         "requested_off_failure", "requested_on_airplane_unknown"):
            self.check_scenario(scenario)

    def test_status_refresh_replaces_stale_controller_on_without_changing_preference(self):
        for scenario in ("status_on_to_off", "status_on_to_unknown", "status_on_to_error"):
            self.check_scenario(scenario)

    def test_sole_switch_uses_controller_both_directions(self):
        for scenario in ("switch_on", "switch_off"):
            self.check_scenario(scenario)

    def test_airplane_persists_requested_enable_without_radio_enable(self):
        self.check_scenario("airplane")

    def test_storage_failure_is_not_success(self):
        for scenario in ("storage_failure", "switch_storage_state"):
            self.check_scenario(scenario)

    def test_unconfirmed_switch_readback_is_not_success(self):
        for scenario in ("switch_partial", "switch_unsettled", "switch_rejected", "switch_inhibited_state"):
            self.check_scenario(scenario)

    def test_paired_devices_refresh_filter_connect_and_remove(self):
        for scenario in ("paired_connect", "paired_remove"):
            self.check_scenario(scenario)

    def test_pair_new_scans_then_only_lists_unpaired(self):
        self.check_scenario("pair_new")

    def test_empty_filtered_lists_never_show_cached_devices(self):
        for scenario in ("paired_empty", "unpaired_empty"):
            self.check_scenario(scenario)

    def test_failed_refresh_and_scan_never_show_devices_or_success(self):
        for scenario in ("refresh_failure", "scan_failure", "scan_powered_off", "scan_inhibited"):
            self.check_scenario(scenario)

    def test_missing_device_and_list_cancel_are_not_success(self):
        for scenario in ("missing_device", "device_cancel"):
            self.check_scenario(scenario)

    def test_nameless_device_uses_address(self):
        self.check_scenario("nameless_device")

    def test_scan_cancel_and_usb_wait_for_settlement(self):
        for scenario in ("cancel_scan", "usb_scan", "late_scan_success"):
            self.check_scenario(scenario)

    def test_scan_timeout_is_bounded_and_leaves_inhibit(self):
        self.check_scenario("timeout_scan")

    def test_controller_cancel_and_usb_wait_for_settlement(self):
        for scenario in ("cancel_power", "usb_power", "late_power_success"):
            self.check_scenario(scenario)

    def test_controller_timeout_is_bounded_and_leaves_inhibit(self):
        self.check_scenario("timeout_power")

    def test_power_change_keeps_navigation_self_voicing_and_rejects_conflicting_activations(self):
        for scenario in ("live_power_navigation", "live_power_repeat", "live_power_fast_disable", "live_power_scan_conflict",
                         "live_power_failure", "live_power_timeout", "live_power_cancel", "live_power_usb"):
            self.check_scenario(scenario)

    def test_rejected_request_without_error_is_not_success(self):
        self.check_scenario("rejected_without_error")

    def test_disconnect_reports_actual_result(self):
        for scenario in ("disconnect", "disconnect_failure"):
            self.check_scenario(scenario)

    def test_unavailable_menu_never_attempts_radio_operations(self):
        for scenario in ("unavailable", "native_thread_failure"):
            self.check_scenario(scenario)

    def test_actual_simulator_stub_exposes_menu_and_preferences_without_radio_success(self):
        for scenario in ("sim_menu", "sim_switch", "sim_scan", "sim_paired"):
            self.check_scenario(scenario, simulator=True)

    def test_settings_default_values_and_last_device_are_visible_spoken_and_read_only(self):
        for scenario in ("prefs_defaults", "prefs_last", "prefs_read_error"):
            self.check_scenario(scenario)
            self.check_scenario(scenario, simulator=True)

    def test_every_settings_choice_changes_only_the_requested_effective_preference(self):
        for preference, count in (("auto", 3), ("retry", 4), ("loss", 2), ("announce", 2)):
            for choice in range(count):
                scenario = f"prefs_{preference}_{choice}"
                self.check_scenario(scenario)
                self.check_scenario(scenario, simulator=True)

    def test_only_numeric_retry_choices_use_the_slider_position_role(self):
        for scenario in ("prefs_defaults", "prefs_auto_0", "prefs_retry_0",
                         "prefs_retry_cancel", "prefs_loss_0", "prefs_announce_0"):
            self.check_scenario(scenario)
            self.check_scenario(scenario, simulator=True)

    def test_settings_cancel_usb_and_persistence_errors_do_not_change_preferences(self):
        for preference in ("auto", "retry", "loss", "announce"):
            for outcome in ("cancel", "usb", "writeerror"):
                scenario = f"prefs_{preference}_{outcome}"
                self.check_scenario(scenario)
                self.check_scenario(scenario, simulator=True)

    def test_connect_last_requires_saved_peer_and_never_implicitly_powers_or_pairs(self):
        for scenario in ("last_missing", "last_read_error", "last_connect", "last_powered_off",
                         "last_inhibited", "last_unpaired"):
            self.check_scenario(scenario)

    def test_forget_requires_explicit_confirmation_and_safe_initial_selection(self):
        for scenario in ("forget_keep", "forget_cancel", "forget_usb", "forget_accept", "forget_failure"):
            self.check_scenario(scenario)

    def test_settings_remain_accessible_during_automatic_work_without_cancelling_it(self):
        for scenario in ("prefs_busy", "prefs_connectivity_busy"):
            self.check_scenario(scenario)

    def test_modal_operation_wait_rejects_settings_activation_without_entering_preferences(self):
        self.check_scenario("modal_settings_busy")

    def test_power_off_cancels_automatic_not_manual_work_and_read_callbacks_are_pure(self):
        for scenario in ("auto_power_off", "manual_power_busy"):
            self.check_scenario(scenario)

    def test_status_speaks_observed_service_capability_and_errors_without_fake_monitor_success(self):
        for status in ("active", "unavailable", "reconnecting", "storage_error", "stopped",
                       "inhibited", "off", "backend_error", "connected"):
            self.check_scenario("status_service_" + status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
