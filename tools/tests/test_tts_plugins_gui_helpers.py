import contextlib
import datetime
import hashlib
import importlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from materials_fixtures import materials_resolver


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root, confined_path



ROOT = Path(__file__).resolve().parents[2]
RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
EVIDENCE = _project_materials_root(ROOT) / "plugin-utilities-gui-helper-tests" / RUN
original_path = list(sys.path)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    gui = importlib.import_module("test_tts_plugins_gui")
finally:
    sys.path[:] = original_path


class PluginGuiHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EVIDENCE.mkdir(parents=True)

    def test_default_profiles_are_unchanged_and_disabled_mode_only_changes_recorded_voice_settings(self):
        recorder = sys.modules["test_tts_recorder_gui"]
        expected_hashes = {
            "recorder": {
                "polski": "3eadbaac6ca2452e3bd66fbffd85ce1990491a3eaafe608bf636d52e811dd5f2",
                "english": "c8c8e7ff0badcddb7ca57c926214555cfb6872585d6d0d5afa21163cd6eb14bf",
            },
            "plugins": {
                "polski": "07a037cf96c6c47f77eb0288bb648a287fecf05d7bc683281807c89ca7bdb3ca",
                "english": "1a9798a47d5cb0b5076debcbc19ea7c52226ef3e79d22c57ba546df12de56698",
            },
        }
        changed_keys = {"talk menu", "talk dir", "talk file", "talk mixer level"}
        for name, configuration in (("recorder", recorder.synthetic_recorder_config),
                                    ("plugins", gui.synthetic_config)):
            for language in ("polski", "english"):
                with self.subTest(suite=name, language=language):
                    default = configuration(language)
                    self.assertEqual(hashlib.sha256(default.encode("utf-8")).hexdigest(),
                                     expected_hashes[name][language])
                    self.assertEqual(configuration(language, False), default)
                    disabled = configuration(language, True)
                    settings = dict(line.split(":", 1) for line in disabled.splitlines())
                    settings = {key: value.strip() for key, value in settings.items()}
                    self.assertEqual({key: settings[key] for key in changed_keys},
                                     {"talk menu": "off", "talk dir": "off", "talk file": "off",
                                      "talk mixer level": "0"})
                    self.assertEqual(settings["tts enabled"], "on")
                    self.assertEqual(settings["tts volume"], "100")
                    self.assertEqual(settings["volume"], "-25")
                    self.assertEqual(settings["talk dir clip"], "off")
                    self.assertEqual(settings["talk file clip"], "off")
                    remaining = lambda text: [line for line in text.splitlines()
                                              if line.partition(":")[0] not in changed_keys]
                    self.assertEqual(remaining(disabled), remaining(default))

    def test_fixture_mode_preserves_catalog_selection_without_an_executable_loan(self):
        recorder = sys.modules["test_tts_recorder_gui"]
        identifiers = (
            "LANG_RECORDING", "LANG_VOLUME", "LANG_GAIN", "LANG_RECORDING_FILENAME",
            "LANG_RECORDING_TIME", "LANG_RECORDING_SIZE", "LANG_RECORD_PRERECORD",
            "LANG_BYTE", "LANG_PAUSE", "LANG_OFF", "LANG_TTS_RECORDER_UNAVAILABLE",
            "LANG_SHUTTINGDOWN", "LANG_DIR_BROWSER",
        )
        records = []
        for language in ("polski", "english"):
            for disabled in (False, True):
                with self.subTest(language=language, voice_files_disabled=disabled):
                    root = EVIDENCE / f"catalog-{language}-{disabled}"
                    build = root / "build"
                    results = root / "results"
                    results.mkdir(parents=True)
                    resources = build / "simdisk/.rockbox"
                    for directory in recorder.RUNTIME_DIRECTORIES:
                        (resources / directory).mkdir(parents=True)
                    (build / "apps/lang").mkdir(parents=True)
                    (build / "rockboxui.exe").write_bytes(b"MZ synthetic fixture, not an executable")
                    (build / "UI256.bmp").write_bytes(b"synthetic bitmap fixture")
                    (build / "rockbox-info.txt").write_text("Target: sansaclipplus\n", encoding="utf-8")
                    (build / "apps/genlang-features").write_text("agc:recording", encoding="utf-8")
                    (build / "lang_enum.h").write_text("synthetic catalog identifiers", encoding="utf-8")
                    for extension in ("lng", "vstrings"):
                        payload = f"synthetic {language} {extension} catalog".encode("utf-8")
                        (build / "apps/lang" / f"{language}.{extension}").write_bytes(payload)
                        (resources / "langs" / f"{language}.{extension}").write_bytes(payload)
                    for filename in ("viewers.config", "tagnavi.config", "rockbox-info.txt"):
                        (resources / filename).write_text("synthetic resource", encoding="utf-8")
                    (resources / "codecs/wav_enc.codec").write_bytes(b"synthetic encoder")
                    (resources / "rocks/calculator.rock").write_bytes(b"MZ synthetic fixture, not a usable plugin")
                    voices = {identifier: f"Voice {language} {identifier}" for identifier in identifiers}
                    displayed = {identifier: f"Display {language} {identifier}" for identifier in identifiers}
                    loan = SimpleNamespace(move_to=mock.Mock())
                    report = {}
                    with contextlib.ExitStack() as patches:
                        patches.enter_context(mock.patch.object(recorder, "windows_backend"))
                        patches.enter_context(mock.patch.object(recorder, "catalog_labels", return_value=voices.copy()))
                        patches.enter_context(mock.patch.object(recorder, "display_labels", return_value=displayed))
                        patches.enter_context(mock.patch.object(gui, "catalog_labels", return_value=voices.copy()))
                        patches.enter_context(mock.patch.object(gui, "display_labels", return_value=displayed))
                        patches.enter_context(contextlib.redirect_stdout(io.StringIO()))
                        runtime, disk, labels = gui.prepare_plugins_fixture(
                            build, results, language, report, loan, "sansaclipplus",
                            plugins=("calculator",), required_labels=("LANG_VOLUME",),
                            voice_files_disabled=disabled)
                    loan.move_to.assert_called_once_with(runtime)
                    self.assertTrue((build / "rockboxui.exe").is_file())
                    self.assertEqual(labels["LANG_VOLUME"], voices["LANG_VOLUME"])
                    self.assertEqual(labels["LANG_DIR_BROWSER"], voices["LANG_DIR_BROWSER"])
                    self.assertEqual(report["voice_files_disabled"], disabled)
                    self.assertEqual((disk / ".rockbox/config.cfg").read_text(encoding="utf-8"),
                                     recorder.synthetic_recorder_config(language, disabled))
                    for marker in (".tts-recorder-gui-fixture.json", ".tts-plugins-gui-fixture.json"):
                        metadata = json.loads((runtime / marker).read_text(encoding="utf-8"))
                        self.assertEqual(metadata["voice_files_disabled"], disabled)
                    for item in report["catalog_inputs"]:
                        self.assertEqual(gui.digest(Path(item["path"])), item["sha256"])
                    records.append(dict(language=language, voice_files_disabled=disabled,
                                        labels=labels, catalog_inputs=report["catalog_inputs"],
                                        executable_loan="mocked; no executable moved or launched"))
        (EVIDENCE / "voice-file-fixtures.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    def test_both_target_keyboard_maps_follow_actual_sources(self):
        for target in ("sansaclipplus", "sansaclipzip"):
            mapping = gui.target_keyboard_map(target)
            self.assertEqual(mapping["BUTTON_SELECT"], "space")
            self.assertEqual(mapping["BUTTON_POWER"], "Escape")
            self.assertEqual(mapping["BUTTON_RIGHT"], "Right")

    def test_changed_source_key_mapping_is_rejected(self):
        source = (ROOT / "uisimulator/buttonmap/sansa-clip.c").read_text(encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "SDLK_SPACE"):
            gui.parse_keyboard_map(source.replace("case SDLK_SPACE:", "case SDLK_RETURN:"))

    def test_spoken_numbers_require_whole_numeric_tokens(self):
        self.assertTrue(gui.speech_matches(["Result 6"], ("Result",), (6,)))
        self.assertFalse(gui.speech_matches(["Result 16"], ("Result",), (6,)))
        self.assertFalse(gui.speech_matches(["Result 6.5"], ("Result",), (6,)))
        self.assertTrue(gui.speech_matches(["Volume -24 dB"], ("Volume",), (-24,)))
        self.assertFalse(gui.speech_matches(["Volume -24 dB"], ("Volume",), (24,)))

    def test_default_die_bounds_and_total_are_both_checked(self):
        labels = {"LANG_DICE_RESULTS": "Results", "LANG_DICE_TOTAL": "Total"}
        self.assertEqual(gui.validate_dice_result(["Results", "4", "Total", "4"], labels)["total"], 4)
        for phrases in (["Results", "7", "Total", "7"], ["Results", "4", "Total", "5"],
                        ["Results", "4", "2", "Total", "6"], ["Results", "-1", "Total", "-1"]):
            with self.subTest(phrases=phrases), self.assertRaises(AssertionError):
                gui.validate_dice_result(phrases, labels)

    def test_post_exit_pcm_rejects_silence_bounds_and_preserves_prior_failure(self):
        raw = EVIDENCE / "action-pcm.raw"
        raw.write_bytes(bytes(512) + struct.pack("<h", 500) * 256)
        checks = [
            {"name": "silence", "status": "passed", "speech_required": True,
             "pcm_file": str(raw), "pcm_start": 0, "pcm_end": 512},
            {"name": "speech", "status": "passed", "speech_required": True,
             "pcm_file": str(raw), "pcm_start": 512, "pcm_end": 1024},
            {"name": "past EOF", "status": "passed", "speech_required": True,
             "pcm_file": str(raw), "pcm_start": 512, "pcm_end": 1026},
            {"name": "prior semantic failure", "status": "failed", "speech_required": True,
             "pcm_file": str(raw), "pcm_start": 512, "pcm_end": 1024},
        ]
        for check in checks:
            check["pcm_attribution"] = "speech_only"
        gui.verify_pcm_checks(checks)
        self.assertEqual([check["status"] for check in checks], ["failed", "passed", "failed", "failed"])
        (EVIDENCE / "pcm-policy-result.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")

    def test_scope_requires_initial_two_actions_and_root_not_empty_success(self):
        self.assertFalse(gui.requirements_complete([], "calculator"))
        checks = [{"plugin": "calculator", "status": "passed", "requirement": requirement}
                  for requirement in ("initial_focus", "functional_action", "functional_action", "exit_root")]
        self.assertTrue(gui.requirements_complete(checks, "calculator"))
        checks[1]["status"] = "failed"
        self.assertFalse(gui.requirements_complete(checks, "calculator"))
        checks[1]["status"] = "passed"
        self.assertFalse(gui.requirements_complete(checks[:-1], "calculator"))

    def test_driver_rejects_logged_only_text_without_expected_synthesis(self):
        driver = gui.PluginDriver.__new__(gui.PluginDriver)
        driver.report = {"checks": []}
        driver.plugin = "calculator"
        driver.pcm = EVIDENCE / "not-running.raw"
        driver.pcm_attribution = "unattributed"

        def fake_capture(instance, name, action, predicate, initial=False):
            observation = {"name": name, "segments": ["Result 6"], "utterances": ["Result 5"], "status": "passed"}
            instance.report["checks"].append(observation)
            return observation

        with mock.patch.object(gui.RecorderProbe, "capture", fake_capture):
            with self.assertRaisesRegex(AssertionError, "not submitted"):
                driver.speech("result", fragments=("Result",), numbers=(6,))
        self.assertEqual(driver.report["checks"][0]["status"], "failed")
        self.assertEqual(driver.report["checks"][0]["suite"], "plugins")

    def test_mixed_pcm_is_explicitly_partial_and_unicode_is_not_simplified(self):
        raw = EVIDENCE / "mixed-pcm.raw"
        raw.write_bytes(struct.pack("<h", 500) * 256)
        checks = [{"name": policy, "status": "passed", "speech_required": True,
                   "pcm_file": str(raw), "pcm_start": 0, "pcm_end": raw.stat().st_size,
                   "pcm_attribution": policy} for policy in ("mixed", "unattributed")]
        gui.verify_pcm_checks(checks)
        self.assertTrue(all(check["status"] == "partial" for check in checks))
        self.assertTrue(all(check["pcm_status"] == "nonzero_not_attributed" for check in checks))
        text = "TTS: Żółw: zażółć gęślą jaźń\nTTS utterance: Żółw: zażółć gęślą jaźń\n"
        self.assertTrue(gui.speech_matches(gui.logged_phrases(text), ("zażółć gęślą jaźń",)))
        self.assertFalse(gui.speech_matches(gui.logged_phrases(text), ("zazolc gesla jazn",)))

    def test_alias_names_are_safe_and_extensions_keep_stable_contract(self):
        aliases = gui.plugin_aliases(("calculator", "countdown_timer", "stats"))
        self.assertEqual(aliases["countdown_timer"], "002 countdown_timer.rock")
        for names in ((), ("../bad",), ("same", "same")):
            with self.assertRaises(AssertionError):
                gui.plugin_aliases(names)
        for name in ("navigate_to_alias", "speech", "press", "seek", "exit_to_root"):
            self.assertTrue(callable(getattr(gui.PluginDriver, name)))
        self.assertTrue(callable(gui.run_suite))
        self.assertTrue(callable(gui.prepare_plugins_fixture))
        self.assertTrue(callable(gui.verify_pcm_checks))

    def run_mocked_after_session(self, mode, voice_files_disabled=False):
        root = EVIDENCE / f"hook-{mode}-{voice_files_disabled}"
        source = root / "source/rockbox"
        source.mkdir(parents=True)
        resolver = materials_resolver(source, root / "materials")
        materials = resolver(source)
        build = materials / gui.TARGETS["sansaclipplus"]
        build.mkdir(parents=True)
        materials_root = mock.Mock(side_effect=resolver)
        events = []
        reports = []
        hidden = []

        def fake_fixture(build, results, language, report, loan, target, plugins, required_labels, *,
                         voice_files_disabled=False):
            runtime = results / "fixture"
            disk = runtime / "simdisk"
            (disk / ".rockbox").mkdir(parents=True)
            report["keyboard_map"] = {"BUTTON_SELECT": "space"}
            self.assertEqual(voice_files_disabled, report["voice_files_disabled"])
            reports.append(report)
            return runtime, disk, {}

        def fake_contained(path, parent):
            roots = (source, materials) if parent == source else (parent,)
            allow_root = parent == source and path == materials
            return confined_path(path, *roots, allow_root=allow_root).resolve(strict=True)

        def fake_loan(build, results, report):
            loan = SimpleNamespace(record={"restored": False}, save_record=lambda: None)

            def restore(process):
                self.assertIsNotNone(process.poll())
                loan.record["restored"] = True
                events.append(("restored", None))

            loan.restore = restore
            return loan

        def fake_process(*arguments, **keywords):
            self.assertEqual(keywords["env"]["SDL_AUDIODRIVER"], "disk")
            self.assertEqual(keywords["env"]["SDL_DISKAUDIODELAY"], "12")
            configuration = Path(keywords["cwd"]) / "simdisk/.rockbox/config.cfg"
            self.assertEqual(configuration.read_text(encoding="utf-8"),
                             gui.synthetic_config("english", voice_files_disabled))
            return mock.Mock(pid=123, poll=mock.Mock(return_value=None))

        def fake_probe(process, window, environment, runtime, report, timeout, plugin, keyboard):
            return SimpleNamespace(process=process, report=report, plugin=plugin,
                                   pcm=Path(environment["SDL_DISKAUDIOFILE"]))

        def exercise(probe, labels):
            self.assertTrue(probe.report["sessions"][-1]["native_window_hidden"])
            for index, requirement in enumerate(("initial_focus", "functional_action", "functional_action", "exit_root")):
                probe.report["checks"].append({
                    "name": f"{probe.plugin} action {index}", "plugin": probe.plugin,
                    "status": "passed", "requirement": requirement, "speech_required": True,
                    "pcm_file": str(probe.pcm), "pcm_start": 0, "pcm_end": 512,
                    "pcm_attribution": "speech_only",
                })
            probe.report["checks"].append({
                "name": f"{probe.plugin} calibration", "plugin": probe.plugin,
                "status": "pending_process_exit", "requirement": "real_music_prerequisite",
            })
            if mode == "exercise_error" and probe.plugin == "calculator":
                probe.report["checks"][-2]["status"] = "failed"
                raise AssertionError("Action failed before calibration")

        def close(probe, session, results, graceful):
            probe.process.poll.return_value = 0
            probe.pcm.write_bytes(struct.pack("<h", 500) * 256)
            log = results / f"{probe.plugin}-simulator.log"
            log.write_text("Synthetic closed log for hook-order regression\n", encoding="utf-8")
            session.update(log=str(log), exit_code=0)
            events.append(("closed", probe.plugin))

        def after_session(probe, session, results):
            self.assertIsNotNone(probe.process.poll())
            self.assertTrue(Path(session["log"]).is_file())
            self.assertNotIn("passed", session)
            checks = [check for check in probe.report["checks"] if check["plugin"] == probe.plugin]
            self.assertTrue(all("pcm_status" not in check for check in checks))
            events.append(("hook", probe.plugin))
            if not checks:
                return
            checks[-1]["status"] = "failed" if mode == "failed_check" and probe.plugin == "calculator" else "passed"
            if mode == "raised_error" and probe.plugin == "calculator":
                raise RuntimeError("Post-exit music calibration failed")

        actual_verify = gui.verify_pcm_checks

        def verify(checks):
            plugin = reports[0]["sessions"][-1]["plugin"]
            self.assertEqual(events[-1], ("hook", plugin))
            events.append(("pcm", plugin))
            actual_verify(checks)

        def hide(pid, window, requested):
            self.assertEqual((pid, window, requested), (123, 456, True))
            hidden.append((pid, window, requested))
            if mode == "hide_error" and len(hidden) == 1:
                raise RuntimeError("Owned SDL window hide failed")

        with contextlib.ExitStack() as patches:
            patches.enter_context(mock.patch.multiple(
                gui, ROOT=source, _project_materials_root=materials_root,
                SOURCE_INPUTS=(), prepare_plugins_fixture=fake_fixture,
                ExecutableLoan=fake_loan, PluginDriver=fake_probe, find_window=lambda *arguments: 456,
                close_session=close, verify_pcm_checks=verify, contained=fake_contained,
                windows_backend=lambda: SimpleNamespace(set_hidden=hide)))
            patches.enter_context(mock.patch.object(gui.subprocess, "Popen", fake_process))
            patches.enter_context(mock.patch.object(gui.subprocess, "CREATE_NO_WINDOW", 0, create=True))
            patches.enter_context(mock.patch.object(gui.sys, "platform", "win32"))
            output = patches.enter_context(contextlib.redirect_stdout(io.StringIO()))
            command = ["--target", "sansaclipplus", "--language", "english", "--build-ready"]
            if voice_files_disabled:
                command.append("--voice-files-disabled")
            result = gui.run_suite(
                plugins=("calculator", "stopwatch"), exercise=exercise, required_labels=(),
                argv=command,
                after_session=after_session)
        (root / "runner-output.log").write_text(output.getvalue(), encoding="utf-8")
        materials_root.assert_called_once_with(source)
        self.assertEqual(Path(reports[0]["source_build"]), build)
        results = Path(reports[0]["artifact_cleanup"]["workspace"])
        self.assertTrue(results.is_relative_to(materials))
        self.assertTrue((results / "report.json").is_file())
        self.assertEqual(list(source.iterdir()), [])
        self.assertEqual(hidden, [(123, 456, True), (123, 456, True)])
        return result, reports[0], events

    def test_after_session_calibration_precedes_pcm_and_verdict(self):
        result, report, events = self.run_mocked_after_session("passed")
        self.assertEqual(result, 0)
        self.assertTrue(report["passed"])
        self.assertEqual(events, [("closed", "calculator"), ("hook", "calculator"), ("pcm", "calculator"),
                                  ("closed", "stopwatch"), ("hook", "stopwatch"), ("pcm", "stopwatch"),
                                  ("restored", None)])

    def test_disabled_voice_files_mode_reaches_every_plugin_session_and_report(self):
        result, report, events = self.run_mocked_after_session("voice-files-disabled", True)
        self.assertEqual(result, 0)
        self.assertTrue(report["passed"])
        self.assertTrue(report["voice_files_disabled"])
        self.assertEqual(len(report["sessions"]), 2)
        self.assertEqual(events[-1], ("restored", None))

    def test_after_session_failed_check_prevents_success_and_keeps_next_session(self):
        result, report, events = self.run_mocked_after_session("failed_check")
        self.assertEqual(result, 1)
        self.assertFalse(report["passed"])
        self.assertEqual([session["passed"] for session in report["sessions"]], [False, True])
        self.assertIn("calculator calibration", report["failed_checks"])
        self.assertEqual(events[-1], ("restored", None))

    def test_after_session_exception_remains_visible_without_discarding_next_session(self):
        result, report, events = self.run_mocked_after_session("raised_error")
        self.assertEqual(result, 1)
        self.assertFalse(report["passed"])
        self.assertIn("Post-exit music calibration failed", report["sessions"][0]["after_session_error"])
        self.assertEqual([session["passed"] for session in report["sessions"]], [False, True])
        self.assertEqual(events[-1], ("restored", None))

    def test_after_session_success_does_not_promote_prior_action_failure(self):
        result, report, events = self.run_mocked_after_session("exercise_error")
        self.assertEqual(result, 1)
        self.assertFalse(report["passed"])
        self.assertIn("Action failed before calibration", report["sessions"][0]["error"])
        self.assertEqual([session["passed"] for session in report["sessions"]], [False, True])
        self.assertEqual(events[-1], ("restored", None))

    def test_owned_window_must_hide_before_actions_and_failure_is_retained(self):
        result, report, events = self.run_mocked_after_session("hide_error")
        self.assertEqual(result, 1)
        self.assertFalse(report["passed"])
        self.assertIn("Owned SDL window hide failed", report["sessions"][0]["error"])
        self.assertNotIn("native_window_hidden", report["sessions"][0])
        self.assertEqual([session["passed"] for session in report["sessions"]], [False, True])
        self.assertEqual(events[-1], ("restored", None))

    def test_module_alias_copy_is_deliberate_hashed_and_refuses_overwrite(self):
        build = EVIDENCE / "alias-build"
        runtime = EVIDENCE / "alias-fixture"
        build.mkdir()
        runtime.mkdir()
        source = build / "calculator.rock"
        source.write_bytes(b"MZ synthetic unit fixture, not a usable plugin")
        destination = runtime / "001 calculator.rock"
        report = {"copies": []}
        with mock.patch.object(gui, "contained", lambda path, root: path.resolve(strict=True)):
            gui.copy_alias(source, destination, build, runtime, report)
            self.assertEqual(gui.digest(source), gui.digest(destination))
            self.assertTrue(report["copies"][0]["retained_after_test"])
            with self.assertRaises(AssertionError):
                gui.copy_alias(source, destination, build, runtime, report)

    def test_cli_requires_explicit_readiness_before_any_gui_or_fixture(self):
        command = [sys.executable, "-B", str(ROOT / "tools/tests/test_tts_plugins_gui.py"),
                   "--target", "sansaclipzip", "--language", "english"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, cwd=EVIDENCE)
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit parent authorization", result.stderr)
        self.assertNotIn("GUI evidence:", result.stdout)

    def test_disabled_voice_files_cli_preserves_build_readiness_guards(self):
        for filename in ("test_tts_recorder_gui.py", "test_tts_plugins_gui.py",
                         "test_tts_plugin_lists_gui.py", "test_tts_plugin_timers_gui.py"):
            with self.subTest(harness=filename):
                command = [sys.executable, "-B", str(ROOT / "tools/tests" / filename),
                           "--target", "sansaclipplus", "--language", "english", "--voice-files-disabled"]
                help_result = subprocess.run(command + ["--help"], capture_output=True, text=True,
                                             timeout=20, cwd=EVIDENCE)
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertIn("--voice-files-disabled", help_result.stdout)
                blocked = subprocess.run(command, capture_output=True, text=True, timeout=20, cwd=EVIDENCE)
                self.assertEqual(blocked.returncode, 2, blocked.stderr)
                self.assertNotIn("unrecognized arguments", blocked.stderr)
                self.assertIn("parent", blocked.stderr)
                self.assertNotIn("GUI evidence:", blocked.stdout)

    def test_standalone_report_and_source_compile_without_execution(self):
        source = (ROOT / "tools/tests/test_tts_plugins_gui.py").read_text(encoding="utf-8")
        compile(source, "test_tts_plugins_gui.py", "exec")
        self.assertIn('suite="plugins"', source)
        self.assertNotIn("recorder.main", source)
        self.assertNotIn("exercise_recorder(", source)
        self.assertIn("Metronome remains paused", source)


if __name__ == "__main__":
    unittest.main()
