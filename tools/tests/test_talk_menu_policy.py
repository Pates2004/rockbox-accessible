"""Compile actual settings speech policy and core gates without a speech backend."""

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
from test_tts_coverage import extract_block


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ("talk_tts_enabled", "talk_menus_enabled", "talk_file_names_enabled",
           "talk_directory_names_enabled", "talk_file_types_enabled")
EXCLUDED = {"talk.c", "tree.c", "filetree.c", "filetypes.c", "playlist_viewer.c",
            "radio/presets.c", "radio/radio.c", "settings_list.c", "menus/settings_menu.c",
            "root_menu.c", "pcmbuf.c", "voice_thread.c", "tts.c", "tts_reader.c",
            "accessibility_shortcut.c", "accessibility_services.c"}


def policy_source(settings_source):
    return "\n".join(extract_block(settings_source, "static inline bool " + name + "(")
                     for name in HELPERS)


def settings_fixture(settings_source, extra_fields=()):
    fields = ("talk_menu", "talk_file", "talk_dir", "talk_filetype", *extra_fields)
    declarations = []
    for name in (*fields, "tts_enabled"):
        matches = re.findall(r"^\s*(?:bool|int)\s+" + re.escape(name) + r"\s*;", settings_source, re.M)
        if len(matches) != 1:
            raise AssertionError(f"Expected one actual settings declaration for {name}")
        declaration = matches[0].strip()
        if name == "tts_enabled":
            declaration = "#ifdef HAVE_ESPEAK\n" + declaration + "\n#endif"
        declarations.append(declaration)
    return "struct user_settings {\n" + "\n".join(declarations) + "\n};\n"


MATRIX = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    unsigned int cases = 0;
#ifdef HAVE_ESPEAK
    const int backend_states = 2;
#else
    const int backend_states = 1;
    assert(!talk_tts_enabled(NULL));
#endif
    for (int enabled = 0; enabled < backend_states; ++enabled)
        for (int menus = 0; menus < 2; ++menus)
            for (int files = 0; files < 3; ++files)
                for (int directories = 0; directories < 3; ++directories)
                    for (int types = 0; types < 2; ++types)
                    {
                        struct user_settings settings = {0};
                        settings.talk_menu = menus != 0;
                        settings.talk_file = files;
                        settings.talk_dir = directories;
                        settings.talk_filetype = types != 0;
#ifdef HAVE_ESPEAK
                        settings.tts_enabled = enabled != 0;
#endif
                        unsigned char before[sizeof(settings)];
                        memcpy(before, &settings, sizeof(settings));
                        const struct user_settings *policy = &settings;
                        assert(talk_tts_enabled(policy) == (enabled != 0));
                        assert(talk_menus_enabled(policy) == (enabled || menus));
                        assert(talk_file_names_enabled(policy) == (enabled || files));
                        assert(talk_directory_names_enabled(policy) == (enabled || directories));
                        assert(talk_file_types_enabled(policy) == (enabled || types));
                        assert(!memcmp(before, &settings, sizeof(settings)));
                        ++cases;
                    }
    printf("PASS policy matrix: %u cases\n", cases);
    return 0;
}
"""


class TalkMenuPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("Run under WSL/POSIX with an existing C compiler")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.workspace = confined_path(central / "talk-menu-policy" / stamp, central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        cls.header = "#include <stdbool.h>\n" + settings_fixture(cls.settings) + policy_source(cls.settings)
        sources = ("apps/settings.h", "apps/talk.h", "apps/gui/list.c", "apps/recorder/recording.c",
                   "apps/accessibility_shortcut.c", "apps/accessibility_shortcut.h",
                   "tools/tests/test_talk_menu_policy.py")
        cls.inputs = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
        cls.write_json(cls.workspace / "provenance.json", {
            "source_project": str(ROOT), "source_sha256": cls.inputs,
            "compiler": cls.compiler, "argv": sys.argv, "platform": sys.platform,
            "scope": "Actual extracted C policy/gates with synthetic fields; no synthesis or player execution",
            "retention": "Generated source, binaries and logs retained as regression evidence; no checkout copied",
        })
        cls.addClassCleanup(cls.verify_sources)
        print(f"Speech policy C evidence: {cls.workspace}", flush=True)

    @staticmethod
    def write_json(path, value):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")

    @classmethod
    def verify_sources(cls):
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in cls.inputs}
        cls.write_json(cls.workspace / "inputs-after.json", {
            "source_sha256": after, "sources_stable": cls.inputs == after})
        if cls.inputs != after:
            raise AssertionError("Policy sources changed during strict C validation")

    def compile_run(self, label, body, espeak=False, standard="c99", sanitize=False, header=None):
        directory = self.workspace / label
        directory.mkdir(exist_ok=False)
        source = directory / "policy.c"
        source.write_text((header or self.header) + "\n" + body, encoding="utf-8")
        executable = directory / "policy-test"
        flags = ["-std=" + standard, "-O0", "-g", "-Wall", "-Wextra", "-Werror", "-Wstrict-prototypes"]
        if not standard.startswith("gnu"):
            flags.append("-pedantic-errors")
        if espeak:
            flags.append("-DHAVE_ESPEAK=1")
        if sanitize:
            flags += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        for stage, command in (("compile", self.compiler + flags + [str(source), "-o", str(executable)]),
                               ("run", [str(executable)])):
            self.write_json(directory / (stage + "-command.json"), {"argv": command, "cwd": str(directory)})
            result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=60)
            (directory / (stage + ".log")).write_text(
                shlex.join(command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
            self.write_json(directory / (stage + "-result.json"), {"returncode": result.returncode})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_actual_helpers_complete_flag_matrix(self):
        for espeak in (False, True):
            for standard in ("c99", "c11"):
                with self.subTest(espeak=espeak, standard=standard):
                    label = ("espeak-" if espeak else "stock-") + standard
                    output = self.compile_run(label, MATRIX, espeak, standard, sanitize=True)
                    self.assertIn(f"PASS policy matrix: {72 if espeak else 36} cases", output)

    def test_actual_conditional_talk_macros(self):
        source = (ROOT / "apps/talk.h").read_text(encoding="utf-8")
        macros = source[source.index("#define TALK_IDARRAY("):source.index("struct talk_debug_data")]
        body = r"""
#include <assert.h>
static struct user_settings global_settings;
static int spoken, forced;
#define TALK_FINAL_ID -1
static int talk_idarray(const long *identifiers, bool enqueue)
{
    assert(!enqueue && identifiers[0] == 1 && identifiers[1] == 2 && identifiers[2] == TALK_FINAL_ID);
    ++spoken;
    return 0;
}
static void talk_force_enqueue_next(void) { ++forced; }
""" + macros + r"""
int main(void)
{
    for (int menus = 0; menus < 2; ++menus)
        for (int enabled = 0; enabled < 2; ++enabled)
        {
            global_settings.talk_menu = menus != 0;
#ifdef HAVE_ESPEAK
            global_settings.tts_enabled = enabled != 0;
            const bool expected = enabled || menus;
#else
            const bool expected = menus != 0;
#endif
            spoken = forced = 0;
            const long identifiers[] = {1, 2, TALK_FINAL_ID};
            cond_talk_ids(1, 2);
            cond_talk_idarray(identifiers);
            cond_talk_ids_fq(1, 2);
            assert(spoken == (expected ? 3 : 0));
            assert(forced == (expected ? 1 : 0));
        }
    return 0;
}
"""
        for espeak in (False, True):
            with self.subTest(espeak=espeak):
                self.compile_run("macros-espeak" if espeak else "macros-stock", body,
                                 espeak, "gnu99", sanitize=True)

    def test_actual_list_initialization_uses_flag_policy(self):
        fields = ("scrollbar", "show_icons", "scroll_paginated", "keyclick", "list_wraparound", "cursor_style")
        header = "#include <stdbool.h>\n" + settings_fixture(self.settings, fields) + policy_source(self.settings)
        source = (ROOT / "apps/gui/list.c").read_text(encoding="utf-8")
        body = r"""
#include <assert.h>
static struct user_settings global_settings;
struct gui_synclist {
    int scrollbar, cursor_style;
    bool show_icons, scroll_paginated, keyclick, talk_menu, wraparound, boundary_speech_pending;
};
""" + extract_block(source, "static void gui_synclist_init_display_settings(") + r"""
int main(void)
{
    for (int menus = 0; menus < 2; ++menus)
        for (int enabled = 0; enabled < 2; ++enabled)
        {
            global_settings.talk_menu = menus != 0;
#ifdef HAVE_ESPEAK
            global_settings.tts_enabled = enabled != 0;
#endif
            struct gui_synclist list = {0};
            gui_synclist_init_display_settings(&list);
#ifdef HAVE_ESPEAK
            assert(list.talk_menu && list.keyclick && list.wraparound);
#else
            assert(list.talk_menu == talk_menus_enabled(&global_settings));
#endif
        }
    return 0;
}
"""
        for espeak in (False, True):
            with self.subTest(espeak=espeak):
                self.compile_run("list-espeak" if espeak else "list-stock", body,
                                 espeak, sanitize=True, header=header)

    def test_actual_recording_gate_uses_runtime_availability_only(self):
        source = (ROOT / "apps/recorder/recording.c").read_text(encoding="utf-8")
        body = r"""
#include <assert.h>
static bool backend_ready;
static bool tts_is_available(void) { return backend_ready; }
""" + extract_block(source, "static bool recording_speech_available(") + r"""
int main(void)
{
    backend_ready = false;
    assert(!recording_speech_available());
    backend_ready = true;
    assert(recording_speech_available());
    return 0;
}
"""
        self.compile_run("recording-availability", body, espeak=True, sanitize=True)

    def test_in_scope_core_reads_all_use_policy(self):
        remaining = []
        for path in (ROOT / "apps").rglob("*"):
            relative = path.relative_to(ROOT / "apps").as_posix()
            if (not path.is_file() or path.suffix not in (".c", ".h")
                    or relative.startswith("plugins/") or relative in EXCLUDED):
                continue
            source = path.read_text(encoding="utf-8")
            if re.search(r"\bglobal_settings\s*\.\s*talk_menu\b", source):
                remaining.append(relative)
        self.assertEqual(remaining, [])

    def test_shortcut_raw_preference_is_confined_to_direct_toggle_and_rollback(self):
        source = (ROOT / "apps/accessibility_shortcut.c").read_text(encoding="utf-8")
        voice_files = extract_block(source, "static bool shortcut_set_voice_files(")
        raw_preference = r'\bglobal_settings\s*\.\s*talk_menu\b'
        self.assertEqual(len(re.findall(raw_preference, source)), 5)
        self.assertEqual(len(re.findall(raw_preference, voice_files)), 3)
        remainder = source.replace(voice_files, "", 1)
        for name in ("accessibility_shortcut_toggle_voice_files", "accessibility_shortcut_set_voice_files"):
            wrapper = extract_block(source, "bool " + name + "(")
            self.assertEqual(len(re.findall(raw_preference, wrapper)), 1)
            remainder = remainder.replace(wrapper, "", 1)
        self.assertNotRegex(remainder, raw_preference)
        self.assertRegex(voice_files, r'\bbool\s+previous\s*=\s*' + raw_preference + r'\s*;')
        self.assertEqual(re.findall(raw_preference + r'\s*=\s*([^;]+);', voice_files),
                         ["enabled", "previous"])
        rollback = extract_block(voice_files, "if (!talk_get_debug_data(&data))")
        self.assertRegex(rollback, raw_preference + r'\s*=\s*previous\s*;')
        self.assertIn("return false;", rollback)
        self.assertNotRegex(voice_files, r'\b(?:' + '|'.join(HELPERS) + r')\s*\(')

    def test_actual_shortcut_changes_raw_voice_preference_not_effective_ui_policy(self):
        source = (ROOT / "apps/accessibility_shortcut.c").read_text(encoding="utf-8")
        voice_files = extract_block(source, "static bool shortcut_set_voice_files(") + "\n" + \
            extract_block(source, "bool accessibility_shortcut_toggle_voice_files(")
        header = (ROOT / "apps/accessibility_shortcut.h").read_text(encoding="utf-8")
        labels = sorted(set(re.findall(r'\bLANG_[A-Z0-9_]+', voice_files)))
        definitions = '\n'.join(f"#define {label} {index + 1}" for index, label in enumerate(labels))
        body = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
""" + header + '\n' + definitions + r"""
static struct user_settings global_settings;
static bool voice_ready;
static int voice_inits, saved_settings, announcements, announced_label, tts_changes;
struct talk_debug_data { int unused; };
static void talk_init(void) { ++voice_inits; }
static bool talk_get_debug_data(struct talk_debug_data *data) { (void)data; return voice_ready; }
static void settings_save(void) { ++saved_settings; }
static void shortcut_announce(int32_t label) { ++announcements; announced_label = label; }
""" + voice_files + r"""
int main(void)
{
    unsigned int cases = 0;
    for (int enabled = 0; enabled < 2; ++enabled)
        for (int menus = 0; menus < 2; ++menus)
            for (int available = 0; available < 2; ++available)
            {
                global_settings.tts_enabled = enabled != 0;
                global_settings.talk_menu = menus != 0;
                voice_ready = available != 0;
                voice_inits = saved_settings = announcements = announced_label = tts_changes = 0;
                const bool failed = !menus && !enabled && !available;
                const bool preference = failed ? menus != 0 : menus == 0;
                const bool result = accessibility_shortcut_toggle_voice_files();
                assert(result == !failed);
                assert(global_settings.talk_menu == preference);
                assert(global_settings.tts_enabled == (enabled != 0));
                assert(talk_menus_enabled(&global_settings) == (enabled || preference));
                assert(tts_changes == 0);
                assert(voice_inits == (!menus && !enabled));
                assert(saved_settings == !failed);
                assert(announcements == 1);
                assert(announced_label == (failed ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILE_MISSING :
                    menus ? LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF :
                            LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON));
                ++cases;
            }
    printf("PASS raw voice preference: %u cases\n", cases);
    return 0;
}
"""
        for standard in ("c99", "c11"):
            with self.subTest(standard=standard):
                output = self.compile_run("shortcut-raw-" + standard, body, espeak=True,
                                          standard=standard, sanitize=True)
                self.assertIn("PASS raw voice preference: 8 cases", output)


if __name__ == "__main__":
    program = unittest.main(verbosity=2, exit=False)
    if hasattr(TalkMenuPolicyTests, "workspace"):
        TalkMenuPolicyTests.write_json(TalkMenuPolicyTests.workspace / "result.json", {
            "tests_run": program.result.testsRun, "passed": program.result.wasSuccessful(),
            "failures": [test.id() for test, unused in program.result.failures],
            "errors": [test.id() for test, unused in program.result.errors],
            "skipped": [{"name": test.id(), "reason": reason} for test, reason in program.result.skipped],
        })
    sys.exit(not program.result.wasSuccessful())
