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

from test_tts_coverage import extract_block

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "apps/radio/presets.c", "apps/radio/radio.c", "apps/radio/radio.h",
    "apps/settings.h", "apps/lang/english.lang", "apps/lang/polski.lang",
    "apps/menus/radio_menu.c", "apps/root_menu.h", "apps/menu.c", "apps/gui/list.c", "apps/talk.c",
    "tools/tests/test_radio_dynamic.py", "tools/tests/fixtures/radio_dynamic_fixture.c",
)
SCAN_SCENARIOS = (
    "found", "pause-resume", "release-ok", "unknown-toggle", "enter-mute",
    "dynamic-off", "voice-fallback", "all-speech-off", "cancel", "cancel-repeat",
    "usb", "power", "reboot", "filesystem", "system-update", "redraw",
    "multimedia", "no-stations", "capacity", "busy", "reset", "allocation", "decline",
    "unknown-hold", "duplicate-press", "tick-wrap",
    "paused-radio", "stopped-radio", "usb-empty",
    "completion-menu", "completion-startup",
    "menu-normal", "menu-usb",
)
RDS_SCENARIOS = ("rds-data", "rds-empty", "rds-off", "rds-missing", "rds-long", "rds-refresh", "rds-partial", "rds-usb")
RADIO_LABELS = ("LANG_FM_SCAN_COMPLETE", "LANG_FM_RDS_INFO", "LANG_FM_RDS_NAME",
                "LANG_FM_RDS_TEXT", "LANG_FM_RDS_NO_DATA")


def catalog_label(catalog, identifier, section):
    phrase = re.search(r"<phrase>\s*id: " + re.escape(identifier) + r"\s.*?</phrase>", catalog, re.DOTALL)
    if not phrase:
        raise AssertionError("Missing actual radio label: " + identifier)
    block = re.search(r"<" + section + r">(.*?)</" + section + r">", phrase[0], re.DOTALL)
    label = re.search(r'\*: "([^"\n]+)"', block[1]) if block else None
    if not label:
        raise AssertionError("Missing actual radio " + section + ": " + identifier)
    return label[1]


class RadioDynamicSourceTests(unittest.TestCase):
    def test_scan_has_only_silent_visual_progress_and_explicit_completion(self):
        source = (ROOT / "apps/radio/presets.c").read_text(encoding="utf-8")
        scan = extract_block(source, "int presets_scan(")
        self.assertIn("splashf_silent(0, str(LANG_FM_SCANNING)", scan)
        self.assertNotRegex(scan, r"\bsplashf\(")
        self.assertIn("talk_id(LANG_FM_SCAN_COMPLETE, false)", scan)
        self.assertNotIn("tts_pause", source)
        self.assertNotIn("button_clear_queue", scan)

    def test_completed_label_has_actual_polish_and_english_voice_text(self):
        for language, expected in (("english", "Scan complete"), ("polski", "Skanowanie zakończone")):
            with self.subTest(language=language):
                source = (ROOT / "apps/lang" / (language + ".lang")).read_text(encoding="utf-8")
                phrase = re.search(r"<phrase>\s*id: LANG_FM_SCAN_COMPLETE\s.*?</phrase>", source, re.DOTALL)
                self.assertIsNotNone(phrase)
                self.assertRegex(phrase[0], r'<voice>\s*\*: "' + re.escape(expected) + '"')

    def test_rds_is_capability_gated_and_manual(self):
        source = (ROOT / "apps/radio/radio.c").read_text(encoding="utf-8")
        start = source.index("#ifdef HAVE_RDS_CAP\nstruct radio_rds_info")
        stop = source.index("\n#endif", start)
        self.assertIn("int radio_show_info(void)", source[start:stop])
        self.assertNotIn("tts_pause", source[start:stop])
        self.assertIn("action == ACTION_STD_OK", extract_block(source, "static int radio_info_action("))

    def test_actual_radio_labels_have_polish_english_display_and_voice_parity(self):
        expected = {
            "english": ("Scan complete", "RDS information", "Station name", "Radio text", "No RDS data"),
            "polski": ("Skanowanie zakończone", "Informacje RDS", "Nazwa stacji", "Tekst RDS", "Brak danych RDS"),
        }
        for language, labels in expected.items():
            catalog = (ROOT / "apps/lang" / (language + ".lang")).read_text(encoding="utf-8")
            for identifier, label, source_label in zip(RADIO_LABELS, labels, expected["english"]):
                with self.subTest(language=language, identifier=identifier):
                    self.assertEqual(catalog_label(catalog, identifier, "dest"), label)
                    self.assertEqual(catalog_label(catalog, identifier, "voice"), label)
                    self.assertEqual(catalog_label(catalog, identifier, "source"), source_label)


class RadioDynamicBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("A host C compiler is required for the isolated radio fixture")
        cls.area = project_materials_root(ROOT) / "radio-dynamic-tests" / uuid.uuid4().hex
        cls.area.mkdir(parents=True)
        cls.results = []
        cls.inputs = {name: (ROOT / name).read_bytes() for name in INPUTS}
        presets = cls.inputs["apps/radio/presets.c"].decode("utf-8")
        radio = cls.inputs["apps/radio/radio.c"].decode("utf-8")
        settings = cls.inputs["apps/settings.h"].decode("utf-8")
        talk = cls.inputs["apps/talk.c"].decode("utf-8")
        enqueue = "\n".join(extract_block(talk, signature) for signature in (
            "void talk_shutup(", "static void do_enqueue(",
            "void talk_force_enqueue_next(", "void talk_cancel_enqueue_next("))
        row = extract_block(cls.inputs["apps/gui/list.c"].decode("utf-8"), "static void _gui_synclist_speak_item(")
        menu_start = radio.index("            case ACTION_FM_MENU:")
        menu_end = radio.index("\n#ifdef FM_PRESET", menu_start)
        startup_start = radio.index("    if(radio_preset_count() < 1 && yesno_pop(")
        startup_end = radio.index("    preset_set_current(preset_find(curr_freq));", startup_start)
        policy = "\n".join(extract_block(settings, "static inline bool " + name + "(")
                           for name in ("talk_tts_enabled", "talk_menus_enabled", "talk_dynamic_enabled"))
        scan = extract_block(presets, "struct presets_scan_speech\n") + ";\n"
        scan += "\n".join(extract_block(presets, signature) for signature in (
            "static void presets_scan_stop_speech(", "static void presets_scan_speech_action(",
            "static int presets_scan_action(", "static void presets_scan_speak(", "int presets_scan("))
        rds = extract_block(radio, "struct radio_rds_info\n") + ";\n"
        rds += "\n".join(extract_block(radio, signature) for signature in (
            "static void radio_read_info(", "static const char *radio_info_get_name(",
            "static int radio_info_speak(", "static int radio_info_action(", "int radio_show_info("))
        fixture = cls.inputs["tools/tests/fixtures/radio_dynamic_fixture.c"].decode("utf-8")
        labels = []
        for language in ("english", "polski"):
            catalog = cls.inputs["apps/lang/" + language + ".lang"].decode("utf-8")
            labels.append(("Clear presets", "Scanning %d.%02d", *(
                catalog_label(catalog, identifier, "dest") for identifier in RADIO_LABELS)))
        label_source = "{" + ", ".join("{" + ", ".join(json.dumps(label, ensure_ascii=False)
                                                     for label in row) + "}" for row in labels) + "}"
        fixture = (fixture.replace("ACTUAL_POLICY_SOURCE", policy)
                   .replace("ACTUAL_SCAN_SOURCE", scan).replace("ACTUAL_RDS_SOURCE", rds)
                   .replace("ACTUAL_RADIO_LABELS", label_source)
                   .replace("ACTUAL_ENQUEUE_SOURCE", enqueue).replace("ACTUAL_LIST_ROW_SOURCE", row)
                   .replace("ACTUAL_RADIO_MENU_CASE", radio[menu_start:menu_end])
                   .replace("ACTUAL_STARTUP_SCAN_SOURCE", radio[startup_start:startup_end]))
        cls.fixture = fixture
        source = cls.area / "radio.c"
        source.write_text(fixture, encoding="utf-8")
        cls.binaries = {}
        for mode, mode_flags in (("ordinary", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"])):
            for target, flags in (("tts-rds", ["-DHAVE_ESPEAK", "-DHAVE_RDS_CAP"]),
                                  ("voice-rds", ["-DHAVE_RDS_CAP"]), ("tts-no-rds", ["-DHAVE_ESPEAK"])):
                binary = cls.area / (mode + "-" + target + (".exe" if os.name == "nt" else ".bin"))
                command = cls.compiler + ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror",
                                          *mode_flags, *flags, str(source), "-o", str(binary)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=60,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                cls.results.append(dict(command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
                if result.returncode:
                    cls.write_report()
                    raise AssertionError(result.stderr)
                cls.binaries[mode, target] = binary

    @classmethod
    def write_report(cls):
        (cls.area / "report.json").write_text(json.dumps({
            "source_project": str(ROOT), "platform": sys.platform, "compiler": cls.compiler,
            "passed": all(result["exit"] == (101 if result.get("expected_failure") else 0)
                          for result in cls.results),
            "inputs": {name: hashlib.sha256(data).hexdigest()
                                                     for name, data in cls.inputs.items()},
            "results": cls.results,
            "scope": "Isolated production functions and mocked tuner/input/speech boundaries; no firmware, GUI or physical acceptance",
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.write_report()

    def run_scenarios(self, scenarios, rds=False):
        for (mode, target), binary in self.binaries.items():
            if rds and target == "tts-no-rds":
                continue
            for scenario in scenarios:
                for language in ("english", "polski"):
                    with self.subTest(mode=mode, target=target, scenario=scenario, language=language):
                        result = subprocess.run([str(binary), scenario, language], capture_output=True, text=True, timeout=10,
                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                        self.results.append(dict(mode=mode, target=target, scenario=scenario, language=language,
                                                 exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_preset_callback_is_independent_of_scan_speech_state(self):
        callback = extract_block(self.inputs["apps/radio/presets.c"].decode("utf-8"),
                                 "static int radio_preset_callback(")
        source = self.area / "preset-callback.c"
        source.write_text(
            "struct menu_item_ex; struct gui_synclist;\n"
            "enum { ACTION_STD_OK=1, ACTION_EXIT_AFTER_THIS_MENUITEM=2 };\n" + callback +
            "\nint main(void) {\n"
            " if (radio_preset_callback(ACTION_STD_OK, 0, 0) != ACTION_EXIT_AFTER_THIS_MENUITEM) return 1;\n"
            " if (radio_preset_callback(17, 0, 0) != 17) return 2;\n"
            " return 0;\n}\n", encoding="utf-8")
        binary = self.area / ("preset-callback.exe" if os.name == "nt" else "preset-callback.bin")
        command = self.compiler + ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror",
                                   str(source), "-o", str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.results.append(dict(kind="preset-callback-compile", command=command,
                                 exit=compiled.returncode, stdout=compiled.stdout, stderr=compiled.stderr))
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.results.append(dict(kind="preset-callback-run", exit=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_rds_labels_accept_unsigned_catalog_strings(self):
        radio = self.inputs["apps/radio/radio.c"].decode("utf-8")
        source = self.area / "rds-catalog-types.c"
        source.write_text(
            "#include <stdio.h>\n#include <string.h>\n" +
            extract_block(radio, "struct radio_rds_info\n") + ";\n"
            "enum { LANG_FM_RDS_NAME, LANG_FM_RDS_TEXT, LANG_FM_RDS_NO_DATA };\n"
            "static unsigned char *str(int label) {\n"
            " static unsigned char labels[3][16] = {\"Station\", \"Text\", \"No data\"};\n"
            " return labels[label];\n}\n" +
            extract_block(radio, "static const char *radio_info_get_name(") +
            "\nint main(void) {\n"
            " struct radio_rds_info info = {0}; char buffer[256];\n"
            " if (radio_info_get_name(0, &info, buffer, sizeof(buffer)) != buffer) return 1;\n"
            " if (strcmp(buffer, \"Station: No data\")) return 2;\n"
            " strcpy(info.name, \"Alpha\"); strcpy(info.text, \"Now playing\");\n"
            " radio_info_get_name(0, &info, buffer, sizeof(buffer));\n"
            " if (strcmp(buffer, \"Station: Alpha\")) return 3;\n"
            " radio_info_get_name(1, &info, buffer, sizeof(buffer));\n"
            " if (strcmp(buffer, \"Text: Now playing\")) return 4;\n"
            " memset(buffer, 1, sizeof(buffer));\n"
            " radio_info_get_name(1, &info, buffer, 4);\n"
            " if (buffer[3] || buffer[4] != 1) return 5;\n"
            " return 0;\n}\n", encoding="utf-8")
        binary = self.area / ("rds-catalog-types.exe" if os.name == "nt" else "rds-catalog-types.bin")
        command = self.compiler + ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror",
                                   str(source), "-o", str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.results.append(dict(kind="rds-catalog-types-compile", command=command,
                                 exit=compiled.returncode, stdout=compiled.stdout, stderr=compiled.stderr))
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.results.append(dict(kind="rds-catalog-types-run", exit=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_scan_lifecycle_controls_and_policy(self):
        self.run_scenarios(SCAN_SCENARIOS)

    def test_rds_snapshot_navigation_and_explicit_refresh(self):
        self.run_scenarios(RDS_SCENARIOS, rds=True)

    def test_actual_radio_menu_hook_is_present_only_with_rds(self):
        source = self.inputs["apps/menus/radio_menu.c"].decode("utf-8")
        source = re.sub(r"^\s*#include[^\n]*", "", source, flags=re.MULTILINE)
        path = self.area / "radio-menu-preprocess.c"
        path.write_text(source, encoding="utf-8")
        root_header = self.inputs["apps/root_menu.h"].decode("utf-8")
        self.assertRegex(root_header, r"\bMENU_ATTACHED_USB\s*=\s*-10\b")
        for rds in (False, True):
            for rtc in (False, True):
                with self.subTest(rds=rds, rtc=rtc):
                    flags = (["-DHAVE_RDS_CAP"] if rds else []) + (["-DCONFIG_RTC=1"] if rtc else [])
                    command = self.compiler + ["-E", "-P", "-x", "c", *flags, str(path)]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    self.results.append(dict(kind="preprocess", command=command, rds=rds, rtc=rtc,
                                             exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if rds:
                        self.assertRegex(result.stdout, r"MENUITEM_FUNCTION\(rds_info_item,\s*MENU_FUNC_CHECK_RETVAL,\s*ID2P\(LANG_FM_RDS_INFO\),\s*radio_show_info,")
                        self.assertRegex(result.stdout, r"&rds_info_item,\s*&scan_presets_item\)")
                    else:
                        self.assertNotRegex(result.stdout, r"\brds_info_item\b|\bradio_show_info\b|\bLANG_FM_RDS_INFO\b")

    def test_regressions_reject_duplicate_splash_muted_completion_and_backlog(self):
        completion = "if (scan_action == ACTION_NONE && talk_menus_enabled(&global_settings))"
        mutations = (
            ("automatic-splash", "splashf_silent(0,", "splashf(0,", "found"),
            ("muted-completion", completion,
             "if (scan_action == ACTION_NONE && !speech.silenced && talk_menus_enabled(&global_settings))", "enter-mute"),
            ("dynamic-completion", completion,
             "if (scan_action == ACTION_NONE && talk_dynamic_enabled(&global_settings))", "dynamic-off"),
            ("dynamic-mute", "!talk_dynamic_enabled(&global_settings)",
             "!talk_menus_enabled(&global_settings)", "dynamic-off"),
            ("repeat-toggle", "if (button & BUTTON_REPEAT)\n    {", "if (false)\n    {", "unknown-hold"),
            ("usb-retune", "if (!IS_SYSEVENT(scan_action) && get_radio_status() == FMRADIO_PLAYING)",
             "if (get_radio_status() == FMRADIO_PLAYING)", "usb"),
            ("backlog", "talk_value_decimal(speech->pending_frequency, UNIT_INT, 6, false)",
             "talk_value_decimal(speech->pending_frequency, UNIT_INT, 6, true)", "found"),
            ("usb-bool-return", "return simplelist_show_list(&list) ? MENU_ATTACHED_USB : 0;",
             "return simplelist_show_list(&list);", "rds-usb"),
            ("radio-ignore-usb", "if (do_menu(&radio_settings_menu, NULL, NULL, false) == MENU_ATTACHED_USB)",
             "if (do_menu(&radio_settings_menu, NULL, NULL, false) == 1)", "menu-usb"),
            ("completion-prefix", "talk_id(LANG_FM_SCAN_COMPLETE, false);\n            talk_force_enqueue_next();",
             "talk_id(LANG_FM_SCAN_COMPLETE, false);", "completion-menu"),
            ("startup-prefix-leak", "presets_scan(NULL);\n        talk_cancel_enqueue_next();",
             "presets_scan(NULL);", "completion-startup"),
        )
        for name, before, after, scenario in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(self.fixture.count(before), 1)
                source = self.area / (name + ".c")
                source.write_text(self.fixture.replace(before, after), encoding="utf-8")
                binary = self.area / (name + (".exe" if os.name == "nt" else ".bin"))
                command = self.compiler + ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror",
                                          "-DHAVE_ESPEAK", "-DHAVE_RDS_CAP", str(source), "-o", str(binary)]
                compiled = subprocess.run(command, capture_output=True, text=True, timeout=60,
                                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self.results.append(dict(mutation=name, command=command, exit=compiled.returncode,
                                         stdout=compiled.stdout, stderr=compiled.stderr))
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                for language in ("english", "polski"):
                    result = subprocess.run([str(binary), scenario, language], capture_output=True, text=True, timeout=10,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    self.results.append(dict(mutation=name, scenario=scenario, language=language, exit=result.returncode,
                                             stdout=result.stdout, stderr=result.stderr, expected_failure=True))
                    self.assertEqual(result.returncode, 101, result.stdout + result.stderr)
                    self.assertIn("CHECK_FAILED", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
