"""Exercise the real registered-context Bluetooth service without radio or audio."""

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
SOURCE = ROOT / "apps/hiby_bluetooth_service.c"
FIXTURE = ROOT / "tools/tests/fixtures/hiby_bluetooth_service_fixture.c"
FRAMEWORK = FIXTURE.with_name("hiby_bluetooth_service_framework.h")
PHASE = "r1-bluetooth-completion-20261020/service-tests"
IDENTIFIERS = ("LANG_HIBY_BT_CONNECTED", "LANG_HIBY_BT_CONNECTION_LOST",
               "LANG_HIBY_BT_RECONNECT_FAILED")
SOURCES = (
    SOURCE, SOURCE.with_suffix(".h"), ROOT / "apps/hiby_bluetooth.c",
    ROOT / "apps/hiby_bluetooth.h", ROOT / "apps/bluetooth_policy.c",
    ROOT / "apps/bluetooth_policy.h", ROOT / "apps/hiby_bluetooth_settings.c",
    ROOT / "apps/hiby_bluetooth_settings.h",
    ROOT / "firmware/target/hosted/hiby/bluetooth-hiby.h",
    ROOT / "firmware/target/hosted/hiby/bluetooth-monitor-hiby.h",
    ROOT / "firmware/target/hosted/hiby/pcm-hiby.h",
    ROOT / "apps/lang/english.lang", ROOT / "apps/lang/polski.lang",
    ROOT / "apps/action.c", ROOT / "apps/misc.c", ROOT / "apps/main.c",
    ROOT / "apps/hiby_connectivity.c", ROOT / "apps/SOURCES",
    FIXTURE, FRAMEWORK, Path(__file__).resolve(),
)


def source_hashes():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SOURCES}


def language_labels(language):
    content = (ROOT / "apps/lang" / (language + ".lang")).read_text(encoding="utf-8")
    phrases = re.findall(r"<phrase>(.*?)</phrase>", content, re.DOTALL)
    result = {}
    for identifier in IDENTIFIERS:
        matches = [phrase for phrase in phrases if re.search(
            r"(?m)^\s*id:\s*" + re.escape(identifier) + r"\s*$", phrase)]
        if len(matches) != 1:
            raise AssertionError(f"{language}: {identifier}: expected exactly one phrase")
        result[identifier] = {}
        for section in ("dest", "voice"):
            matched = re.search("<" + section + ">(.*?)</" + section + ">", matches[0], re.DOTALL)
            if not matched:
                raise AssertionError(f"{language}: {identifier}: missing {section}")
            definitions = dict(re.findall(r"(?m)^\s*([^\s:]+):\s*(.*?)\s*$", matched[1]))
            value = definitions.get("hibyr1", definitions.get("*", "none"))
            if value in ("none", '""'):
                raise AssertionError(f"{language}: {identifier}: empty {section}")
            result[identifier][section] = json.loads(value)
    return result


def function_body(source, name):
    matched = re.search(r"(?m)^\w[^;\n]*\b" + re.escape(name) + r"\([^;]*?\)\s*\{", source)
    if not matched:
        raise AssertionError(f"Missing function: {name}")
    opening = source.index("{", matched.start())
    depth = 1
    for position in range(opening + 1, len(source)):
        depth += source[position] == "{"
        depth -= source[position] == "}"
        if not depth:
            return source[opening + 1:position]
    raise AssertionError(f"Unclosed function: {name}")


@unittest.skipUnless(os.name == "posix" and shutil.which("gcc"),
                     "requires the isolated POSIX C service fixture")
class BluetoothServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        central = project_materials_root(ROOT)
        requested = Path(os.environ.get("HIBY_BT_SERVICE_TEST_ROOT", central / PHASE))
        area = confined_path(requested, central)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.evidence = area / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True)
        cls.hashes = source_hashes()
        cls.builds = []
        cls.executions = []
        cls.binaries = []
        cls.addClassCleanup(cls.report)
        cls.languages = {language: language_labels(language) for language in ("english", "polski")}
        (cls.evidence / "hiby-bluetooth-service-test.h").write_text(
            '#include "hiby_bluetooth_service_framework.h"\n', encoding="ascii")
        for language, labels in cls.languages.items():
            directory = cls.evidence / language
            directory.mkdir()
            definitions = "enum { " + ", ".join(IDENTIFIERS) + ", SERVICE_LANGUAGE_COUNT };\n"
            for symbol, section in (("service_language", "dest"), ("service_voice_language", "voice")):
                definitions += "static const char *const " + symbol + "[] = {\n"
                definitions += ",\n".join(json.dumps(labels[identifier][section], ensure_ascii=False)
                                         for identifier in IDENTIFIERS) + "\n};\n"
            (directory / "hiby_bluetooth_service_language.h").write_text(definitions, encoding="utf-8")
            for sanitized in (False, True):
                executable = directory / ("service-sanitized" if sanitized else "service")
                arguments = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wformat=2",
                             "-Wshadow", "-Wconversion", "-pedantic-errors", "-O1", "-g", "-pthread",
                             "-DHIBY_BT_SERVICE_HOST_TEST", "-DHIBY_BT_SETTINGS_HOST_TEST", '-DROCKBOX_DIR="."',
                             "-I", str(ROOT / "apps"), "-I", str(ROOT / "firmware/target/hosted/hiby"),
                             "-I", str(FIXTURE.parent), "-I", str(directory), "-I", str(cls.evidence)]
                if sanitized:
                    arguments += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                                  "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
                arguments += [str(FIXTURE), str(ROOT / "apps/bluetooth_policy.c"),
                              str(ROOT / "apps/hiby_bluetooth_settings.c"),
                              "-Wl,--wrap=open", "-Wl,--wrap=fsync", "-o", str(executable)]
                before = source_hashes()
                result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
                after = source_hashes()
                cls.builds.append(dict(language=language, sanitized=sanitized, argv=arguments,
                                       returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
                                       inputs_before=before, inputs_after=after, source_unchanged=before == after))
                (cls.evidence / "builds.json").write_text(json.dumps(cls.builds, indent=2), encoding="utf-8")
                if result.returncode or before != after:
                    raise AssertionError(result.stderr or "Source changed during fixture compilation")
                cls.binaries.append((language, sanitized, executable))
        print("Bluetooth service evidence:", cls.evidence, flush=True)

    @classmethod
    def report(cls):
        after = source_hashes()
        report = dict(
            source_project=str(ROOT), source_sha256=cls.hashes, source_sha256_after=after,
            source_unchanged=cls.hashes == after, builds=cls.builds, executions=cls.executions,
            runtime_passed=bool(cls.executions) and all(item["returncode"] == 0 for item in cls.executions),
            hardware_tested=False, registered_scheduler="deterministic framework mock",
            real_sources=["apps/hiby_bluetooth_service.c", "apps/bluetooth_policy.c",
                          "apps/hiby_bluetooth_settings.c"],
            mocked=["controller", "monitor", "PCM status", "Rockbox scheduler", "playback", "speech"],
            host_radio_calls=False, host_audio=False, global_input=False,
            clock_changes=False, firmware_or_card_access=False,
        )
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Bluetooth service report:", cls.evidence / "report.json", flush=True)

    def check_scenarios(self, *scenarios):
        for scenario in scenarios:
            for language, sanitized, executable in self.binaries:
                with self.subTest(scenario=scenario, language=language, sanitized=sanitized):
                    directory = self.evidence / "cases" / scenario / (language + ("-sanitized" if sanitized else ""))
                    directory.mkdir(parents=True)
                    environment = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1",
                                   "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}
                    result = subprocess.run([str(executable), scenario], cwd=directory, env=environment,
                                            capture_output=True, text=True, timeout=30)
                    record = dict(scenario=scenario, language=language, sanitized=sanitized,
                                  returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                    self.executions.append(record)
                    (directory / "execution.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("verified-service=" + scenario + "\n", result.stdout)

    def test_real_private_defaults(self):
        self.check_scenarios("defaults")

    def test_startup_modes_and_missing_peer_never_enable_or_pair(self):
        self.check_scenarios("startup_off", "startup_only", "startup_loss", "startup_no_peer")

    def test_finite_retry_backoff_and_remaining_command_budget(self):
        self.check_scenarios("backoff", "remaining_budget", "window_30", "window_60", "window_120", "window_300")

    def test_accidental_loss_pauses_only_active_music_and_never_resumes(self):
        self.check_scenarios("loss_default", "loss_idle", "loss_already_paused", "loss_keep_playing")

    def test_loss_between_backend_commit_and_first_service_poll_is_not_missed(self):
        self.check_scenarios("loss_before_first_poll")

    def test_manual_connect_success_before_first_poll_does_not_start_redundant_auto_connect(self):
        self.check_scenarios("manual_success_before_startup_poll")

    def test_loss_respects_startup_only_and_off_modes(self):
        self.check_scenarios("loss_startup_only", "loss_disabled")

    def test_verified_link_loss_without_pcm_loss_is_observed(self):
        self.check_scenarios("verified_loss")

    def test_cancel_and_scan_suppress_retry_without_disabling_passive_loss_protection(self):
        self.check_scenarios("suppressed_loss_scan", "suppressed_loss_cancel")

    def test_manual_disconnect_forget_and_off_suppress_retries_and_loss_actions(self):
        self.check_scenarios("manual_disconnect", "manual_forget", "manual_off", "suppression_reset_radio_cycle")

    def test_cancel_and_airplane_suppress_pending_automatic_work(self):
        self.check_scenarios("cancel_pending", "airplane_pending", "airplane_loss")

    def test_manual_wired_rate_change_transient_and_stale_loss_are_not_disconnect(self):
        self.check_scenarios("pcm_manual_wired", "pcm_rate_change", "pcm_transient", "pcm_unknown",
                             "pcm_old_loss_intent", "stale_loss_after_new_peer")

    def test_event_bursts_coalesce_and_idle_never_periodically_runs_controller_commands(self):
        self.check_scenarios("monitor_idle", "monitor_burst")

    def test_monitor_failure_has_bounded_three_start_budget_and_backoff(self):
        self.check_scenarios("monitor_failures", "monitor_exit")

    def test_off_unknown_and_disabled_radio_do_not_spawn_monitor_or_cli(self):
        self.check_scenarios("monitor_off", "monitor_unknown", "monitor_disabled")

    def test_pl_en_automatic_speech_and_manual_operations_do_not_duplicate(self):
        self.check_scenarios("notify_connected", "notify_spell", "notify_manual_success")

    def test_notification_mute_input_priority_and_newer_manual_intent(self):
        self.check_scenarios("notify_dynamic_off", "notify_menus_off", "notify_pref_off",
                             "notify_defer_input", "notify_new_manual")

    def test_real_storage_read_failure_corruption_and_remember_failure_are_visible(self):
        self.check_scenarios("storage_read_error", "storage_corrupt", "storage_remember_failure")

    def test_clock_failure_and_rejected_request_do_not_consume_attempts_or_continue_work(self):
        self.check_scenarios("clock_failure", "request_rejected")

    def test_hard_retry_window_expires_during_busy_unknown_worker_without_stuck_status(self):
        self.check_scenarios("expiry_busy", "expiry_unknown")

    def test_disabling_auto_mode_cancels_only_auto_and_never_fabricates_manual_intent(self):
        self.check_scenarios("config_off_auto_busy", "config_off_manual_busy")

    def test_service_creation_failure_and_lifecycle_are_bounded(self):
        self.check_scenarios("create_failure", "idempotent_start_stop", "shutdown_pending")

    def test_actual_thread_loop_and_main_timeout_bound_do_not_busy_spin(self):
        self.check_scenarios("loop_active", "loop_off", "timeout_cap")

    def test_real_settings_reads_do_not_leak_file_descriptors(self):
        self.check_scenarios("fd_cycles")


class BluetoothServiceBoundaryTests(unittest.TestCase):
    def test_callback_and_foreign_worker_never_use_scheduler_playback_or_speech(self):
        controller = (ROOT / "apps/hiby_bluetooth.c").read_text(encoding="utf-8").split("#ifndef HIBY_BT_NO_UI", 1)[0]
        forbidden = r"\b(?:audio_pause|audio_resume|queue_send|queue_post|button_queue_post|talk_id|talk_spell|tts_speak)\s*\("
        self.assertNotRegex(controller, forbidden)
        service = SOURCE.read_text(encoding="utf-8")
        for name in ("hiby_bluetooth_service_requested", "hiby_bluetooth_service_completed",
                     "hiby_bluetooth_service_cancelled", "hiby_bluetooth_service_allow"):
            with self.subTest(callback=name):
                self.assertNotRegex(function_body(service, name), forbidden)
        thread = function_body(service, "bluetooth_service_thread")
        self.assertIn("service_poll();", thread)
        self.assertRegex(function_body(service, "hiby_bluetooth_service_start"),
                         r"create_thread\(bluetooth_service_thread,")
        self.assertIn("audio_pause_guarded(playback_generation, begin_loss_pause, end_loss_pause, &loss)",
                      function_body(service, "service_poll"))
        self.assertNotIn("audio_resume(", service)

    def test_framework_header_never_substitutes_product_interfaces(self):
        header = FRAMEWORK.read_text(encoding="utf-8")
        self.assertNotRegex(header, r"\b(?:struct hiby_bt_snapshot|enum hiby_bt_operation|struct hiby_pcm_output_status)\s*\{")
        fixture = FIXTURE.read_text(encoding="utf-8")
        self.assertIn('#include "hiby_bluetooth_service.c"', fixture)
        test = Path(__file__).read_text(encoding="utf-8")
        self.assertIn('str(ROOT / "apps/hiby_bluetooth_settings.c")', test)
        self.assertIn('str(ROOT / "apps/bluetooth_policy.c")', test)

    def test_pl_en_dest_and_voice_messages_are_complete(self):
        for language in ("polski", "english"):
            with self.subTest(language=language):
                labels = language_labels(language)
                self.assertEqual(set(labels), set(IDENTIFIERS))
                for parts in labels.values():
                    self.assertTrue(parts["dest"].strip())
                    self.assertTrue(parts["voice"].strip())

    def test_real_startup_shutdown_connectivity_and_main_input_hooks_remain(self):
        main = (ROOT / "apps/main.c").read_text(encoding="utf-8")
        self.assertLess(main.index("audio_init();"), main.index("hiby_bluetooth_service_start();"))
        misc = (ROOT / "apps/misc.c").read_text(encoding="utf-8")
        self.assertLess(misc.index("hiby_bluetooth_service_shutdown();"), misc.index("hiby_pcm_shutdown();"))
        action = (ROOT / "apps/action.c").read_text(encoding="utf-8")
        self.assertIn("hiby_bluetooth_service_adjust_timeout(cur->timeout)", action)
        self.assertIn("hiby_bluetooth_service_process_notifications();", action)
        self.assertIn("hiby_bluetooth_service_process_notifications();", misc)
        self.assertIn("hiby_bluetooth_service_allow(", (ROOT / "apps/hiby_connectivity.c").read_text(encoding="utf-8"))
        sources = (ROOT / "apps/SOURCES").read_text(encoding="utf-8")
        self.assertIn("hiby_bluetooth_service.c", sources)
        self.assertIn("bluetooth_policy.c", sources)


if __name__ == "__main__":
    unittest.main()
