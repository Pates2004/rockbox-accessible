import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest

from test_tts_coverage import extract_block


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
WORKSPACE = _project_materials_root(ROOT) / "tts-recorder-tests" / RUN


def language_text(source, identifier, section="dest"):
    phrase = re.search(r"<phrase>\s*id: " + identifier + r"\s.*?</phrase>",
                       source, re.DOTALL).group()
    destination = re.search(f"<{section}>(.*?)</{section}>", phrase, re.DOTALL).group(1)
    entries = re.findall(r'^\s*([^:\n]+): "(.*)"', destination, re.MULTILINE)
    for target in ("recording", "agc", "*"):
        for targets, value in entries:
            if target in targets.split(","):
                return value
    raise AssertionError(f"No recording {section} translation for {identifier}")


class RecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recorder = (ROOT / "apps/recorder/recording.c").read_text(encoding="utf-8")
        cls.screen = extract_block(cls.recorder, "bool recording_screen(")
        shutdown = (ROOT / "apps/misc.c").read_text(encoding="utf-8")
        header = (ROOT / "apps/recorder/recording.h").read_text(encoding="utf-8")
        pieces = [extract_block(header, "enum recording_command") + ";",
                  extract_block(cls.recorder, "enum rec_status_flags") + ";"]
        pieces.append(cls.recorder[cls.recorder.index("enum rec_list_items_stereo"):
                                   cls.recorder.index("static void recording_step_levels(")])
        for signature in ("static void set_gain(", "static void recording_step_levels(",
                          "int rec_create_directory(", "static bool recording_start_available(",
                          "void rec_command(",
                          "static void trigger_listener("):
            pieces.append(extract_block(cls.recorder, signature))
        pieces.append(extract_block(shutdown, "static bool clean_shutdown("))
        pieces.insert(0, "#ifdef HAVE_RECORDING_TTS\n" +
                      extract_block(shutdown, "char *output_dyn_value(") + "\n#endif")
        cls.extracted = "\n".join(pieces)
        identifiers = sorted(set(re.findall(r"\bLANG_[A-Z_]+\b", cls.extracted)) |
                             {"LANG_BYTE", "LANG_KIBIBYTE", "LANG_MEBIBYTE", "LANG_GIBIBYTE"})
        definitions = ["enum { " + ", ".join(identifiers) + ", LANGUAGE_COUNT };\n"]
        for language in ("english", "polski"):
            source = (ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8")
            for section, suffix in (("dest", ""), ("voice", "_voice")):
                definitions.append(f"static const char *const {language}{suffix}[LANGUAGE_COUNT] = {{")
                for identifier in identifiers:
                    value = json.dumps(language_text(source, identifier, section), ensure_ascii=False)
                    definitions.append(f"[{identifier}] = {value},")
                definitions.append("};")
        WORKSPACE.mkdir(parents=True)
        settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        policy = "\n".join(extract_block(settings, "static inline bool " + name + "(")
                           for name in ("talk_tts_enabled", "talk_menus_enabled"))
        (WORKSPACE / "recorder_policy.h").write_text(policy, encoding="utf-8")
        (WORKSPACE / "recorder_functions.h").write_text(cls.extracted, encoding="utf-8")
        (WORKSPACE / "recorder_language.h").write_text("\n".join(definitions), encoding="utf-8")
        sources = ("apps/settings.h", "apps/recorder/recording.c", "apps/recorder/recording.h",
                   "apps/misc.c", "apps/lang/english.lang", "apps/lang/polski.lang",
                   "tools/tests/test_tts_recorder.py", "tools/tests/test_tts_recorder.c")
        (WORKSPACE / "provenance.json").write_text(json.dumps({
            "source_project": str(ROOT), "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
            "scope": "Actual extracted recorder/shutdown and settings policy with mocked backends",
        }, indent=2) + "\n", encoding="utf-8")

    def run_harness(self, mode, defines, sanitizer=None, mutation=None, failure_test=None):
        output = WORKSPACE / mode
        output.mkdir()
        include = WORKSPACE
        if mutation:
            include = output
            original, replacement = mutation
            self.assertIn(original, self.extracted)
            (output / "recorder_functions.h").write_text(
                self.extracted.replace(original, replacement, 1), encoding="utf-8")
        executable = output / "recorder-test"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-I", str(include), "-I", str(WORKSPACE),
            str(ROOT / "tools/tests/test_tts_recorder.c"), "-o", str(executable),
        ] + ["-D" + define for define in defines]
        if sanitizer:
            command += [f"-fsanitize={sanitizer}", "-fno-sanitize-recover=all"]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / "compile.log").write_text(
            shlex.join(command) + "\n" + compiled.stdout + compiled.stderr, encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=0")
        tested = subprocess.run([str(executable)], capture_output=True, text=True,
                                timeout=30, env=environment)
        (output / "result.json").write_text(json.dumps({
            "returncode": tested.returncode, "stdout": tested.stdout,
            "stderr": tested.stderr, "expected_failure": mutation is not None,
        }, indent=2), encoding="utf-8")
        if mutation:
            self.assertNotEqual(tested.returncode, 0)
            expected = failure_test or ("test_trigger" if "trigger" in mode else "test_shutdown")
            self.assertIn(expected, tested.stderr)
        else:
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_espeak_simulator_callbacks_and_shutdown(self):
        self.run_harness("espeak-simulator", ["HAVE_ESPEAK", "SIMULATOR"])

    def test_espeak_simulator_address_and_undefined_sanitizers(self):
        self.run_harness("espeak-simulator-sanitized", ["HAVE_ESPEAK", "SIMULATOR"],
                         "address,undefined")

    def test_legacy_simulator(self):
        self.run_harness("legacy-simulator", ["SIMULATOR"], "undefined")

    def test_hardware_keeps_recording_speech_guard(self):
        self.run_harness("hardware-guard", ["HAVE_ESPEAK"], "undefined")

    def test_duplex_hardware_speaks_recording_controls_and_states(self):
        self.run_harness("hardware-duplex", ["HAVE_ESPEAK", "HAVE_PCM_RECORDING_VOICE",
                                             "AUDIO_HAVE_RECORDING"], "address,undefined")

    def test_no_monitoring_layout(self):
        self.run_harness("no-monitoring", ["HAVE_ESPEAK", "SIMULATOR",
                                          "HAVE_RECORDING_WITHOUT_MONITORING"], "undefined")

    def test_available_backend_preserves_recording_commands(self):
        self.run_harness("available-backend", ["HAVE_ESPEAK", "SIMULATOR", "AUDIO_HAVE_RECORDING"],
                         "undefined")

    def test_unavailable_start_guard_mutation_is_detected(self):
        self.run_harness("unavailable-start-mutation", ["HAVE_ESPEAK", "SIMULATOR"],
                         mutation=('splash(HZ, ID2P(LANG_TTS_RECORDER_UNAVAILABLE));\n    return false;',
                                   'splash(HZ, ID2P(LANG_TTS_RECORDER_UNAVAILABLE));\n    return true;'),
                         failure_test="test_unavailable_start")

    def test_shutdown_duplicate_mutation_is_detected(self):
        self.run_harness("duplicate-shutdown-mutation", ["HAVE_ESPEAK", "SIMULATOR"],
                         mutation=('splashf_silent(0, "%s", str(LANG_SHUTTINGDOWN))',
                                   'splashf(0, "%s", str(LANG_SHUTTINGDOWN))'))

    def test_missing_trigger_start_mutation_is_detected(self):
        self.run_harness("missing-trigger-start-mutation", ["HAVE_ESPEAK", "SIMULATOR", "AUDIO_HAVE_RECORDING"],
                         mutation=("rec_command(RECORDING_CMD_START);", "(void)0;"))

    def test_empty_catalog_label_mutations_are_detected(self):
        mutations = (
            ("filename-row", 'talk_spell(str(LANG_RECORDING_FILENAME), false);',
             'talk_id(LANG_RECORDING_FILENAME, false);', "test_callbacks"),
            ("time-row", 'talk_spell(str(prerecord ? LANG_RECORD_PRERECORD : LANG_RECORDING_TIME), false);',
             'talk_id(prerecord ? LANG_RECORD_PRERECORD : LANG_RECORDING_TIME, false);', "test_callbacks"),
            ("filename-state", 'talk_spell(str(LANG_RECORDING_FILENAME), enqueue);',
             'talk_id(LANG_RECORDING_FILENAME, enqueue);', "test_state_feedback"),
            ("prerecord-state", 'talk_spell(str(LANG_RECORD_PRERECORD), true);',
             'talk_id(LANG_RECORD_PRERECORD, true);', "test_state_feedback"),
            ("size-unit", '        default:\n        {\n            char buffer[MAX_PATH];',
             '        case ITEM_SIZE:\n'
             '            talk_spell(str(LANG_RECORDING_SIZE), false);\n'
             '            output_dyn_value(NULL, 0, audio_num_recorded_bytes(), byte_units, 4, true);\n'
             '            break;\n'
             '        default:\n        {\n            char buffer[MAX_PATH];', "test_callbacks"),
        )
        for name, original, replacement, failure_test in mutations:
            with self.subTest(producer=name):
                self.run_harness("empty-catalog-" + name, ["HAVE_ESPEAK", "SIMULATOR"],
                                 mutation=(original, replacement), failure_test=failure_test)

    def test_required_recorder_voice_catalog_entries_are_empty(self):
        for language in ("english", "polski"):
            source = (ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8")
            for identifier in ("LANG_RECORDING_FILENAME", "LANG_RECORDING_TIME",
                               "LANG_RECORDING_SIZE", "LANG_RECORD_PRERECORD", "LANG_BYTE"):
                with self.subTest(language=language, identifier=identifier):
                    self.assertEqual(language_text(source, identifier, "voice"), "")
                    self.assertTrue(language_text(source, identifier))

    def test_screen_wires_callbacks_without_repaint_speech(self):
        initialization = extract_block(self.screen, "if(done < 0)")
        self.assertIn("gui_synclist_set_voice_callback(&lists, reclist_speak)", initialization)
        self.assertLess(initialization.rindex("gui_synclist_set_nb_items"),
                        initialization.index("gui_synclist_speak_item"))
        self.assertEqual(initialization.count("listid_to_enum[listi++] = ITEM_TIME"), 2)
        self.assertEqual(initialization.count("listid_to_enum[listi++] = ITEM_SIZE"), 2)
        actions = self.screen[self.screen.index("switch(button)"):]
        for first, last in (("case ACTION_SETTINGS_INC:", "case ACTION_SETTINGS_DEC:"),
                            ("case ACTION_SETTINGS_DEC:", "case ACTION_STD_CANCEL:")):
            adjustment = actions[actions.index(first):actions.index(last)]
            self.assertLess(adjustment.index("set_gain();"),
                            adjustment.index("gui_synclist_speak_item(&lists)"))
        repaint = extract_block(self.screen, "if(update_list)")
        self.assertNotIn("speak", repaint)
        poll = self.screen[self.screen.index("button = peak_meter_draw_get_btn"):
                           self.screen.index("if (last_audio_stat != audio_stat)")]
        self.assertLess(poll.index("audio_stat = audio_status()"),
                        poll.index("recording_speak_state"))

    def test_start_rejection_precedes_screen_and_trigger_side_effects(self):
        self.assertIn('#include "audio_thread.h"', self.recorder)
        availability = extract_block(self.recorder, "static bool recording_start_available(")
        self.assertIn("#if defined(HAVE_RECORDING_TTS) && !defined(AUDIO_HAVE_RECORDING)", availability)
        self.assertIn("splash(HZ, ID2P(LANG_TTS_RECORDER_UNAVAILABLE))", availability)
        request = self.screen[self.screen.index("case ACTION_REC_PAUSE:"):
                              self.screen.index("case ACTION_STD_MENU:")]
        rejection = request.index("if (!recording_start_available())")
        for effect in ("rec_status |= RCSTAT_HAVE_RECORDED", "rec_command(RECORDING_CMD_START)",
                       "peak_meter_trigger(true)"):
            self.assertLess(rejection, request.index(effect))
        trigger = extract_block(self.recorder, "static void trigger_listener(")
        self.assertLess(trigger.index("if (!recording_start_available())"),
                        trigger.index("rec_status |= RCSTAT_HAVE_RECORDED"))

    def test_error_closes_recorder_before_restoring_speech(self):
        error = extract_block(self.screen, "if (audio_stat & AUDIO_STATUS_ERROR)")
        self.assertLess(error.index("audio_close_recording()"), error.index("talk_disable(false)"))
        self.assertLess(error.index("talk_disable(false)"), error.index("splashf("))
        self.assertIn("talk_suppressed = false", error)
        self.assertIn("ID2P(LANG_ERROR_FORMATSTR)", error)
        self.assertNotIn("LANG_DISK_FULL", error)
        self.assertIn("if (talk_suppressed)\n        talk_disable(false)", self.screen)

    def test_simulator_does_not_claim_microphone_capture(self):
        source = (ROOT / "firmware/target/hosted/sdl/pcm-sdl.c").read_text(encoding="utf-8")
        capture = extract_block(source, "void pcm_rec_dma_start(")
        self.assertRegex(capture, r"\{\s*\(void\)start;\s*\(void\)size;\s*\}")
        peak = extract_block(source, "const void * pcm_rec_dma_get_peak_buffer(")
        self.assertIn("return NULL;", peak)
        self.assertIn("#if defined(HAVE_ESPEAK) && (defined(SIMULATOR) || defined(HAVE_PCM_RECORDING_VOICE))",
                      self.recorder)

    def test_recording_clock_transitions_cancel_speech_before_dispatch(self):
        source = (ROOT / "apps/recorder/pcm_record.c").read_text(encoding="utf-8")
        for signature in ("void audio_init_recording(", "void audio_close_recording(",
                          "void audio_set_recording_options("):
            with self.subTest(signature=signature):
                operation = extract_block(source, signature)
                self.assertLess(operation.index("voice_stop();"),
                                operation.index("audio_queue_send("))
                self.assertIn("#if defined(HAVE_ESPEAK) && defined(HAVE_PCM_RECORDING_VOICE)",
                              operation)
        options = extract_block(self.recorder, "void rec_set_recording_options(")
        self.assertLess(options.index("talk_force_shutup();"),
                        options.index("rec_set_source("))
        handler = extract_block(source, "static void on_recording_options(")
        self.assertNotIn("queue_reply(", handler)


if __name__ == "__main__":
    print(f"Recorder evidence: {WORKSPACE}", flush=True)
    unittest.main(verbosity=2)
