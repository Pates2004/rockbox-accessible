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

from test_talk_menu_policy import policy_source, settings_fixture
from test_tts_coverage import extract_block

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
MATRIX = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "CHECK_FAILED line %d: %s\n", __LINE__, #condition); \
    return 101; } } while (0)
int main(void)
{
    unsigned int cases = 0;
#ifdef HAVE_ESPEAK
    const int flag_states = 2;
    const int position_states = 5;
#else
    const int flag_states = 1;
    const int position_states = 1;
    CHECK(!talk_tts_enabled(NULL));
#endif
    for (int enabled = 0; enabled < flag_states; ++enabled)
    for (int dynamic = 0; dynamic < flag_states; ++dynamic)
    for (int position = 0; position < position_states; ++position)
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
        settings.tts_announce_dynamic = dynamic != 0;
        settings.tts_announce_position = position;
#endif
        unsigned char before[sizeof(settings)];
        memcpy(before, &settings, sizeof(settings));
        const struct user_settings *policy = &settings;
        CHECK(talk_dynamic_enabled(policy) == (enabled ? dynamic != 0 : menus != 0));
        CHECK(talk_menus_enabled(policy) == (enabled || menus));
        CHECK(talk_file_names_enabled(policy) == (enabled || files));
        CHECK(talk_directory_names_enabled(policy) == (enabled || directories));
        CHECK(talk_file_types_enabled(policy) == (enabled || types));
        CHECK(!memcmp(before, &settings, sizeof(settings)));
        ++cases;
    }
    printf("PASS dynamic policy: %u cases\n", cases);
    return 0;
}
"""


class TalkboxDynamicPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable")
        cls.inputs = {name: (ROOT / name).read_bytes() for name in (
            "apps/settings.h", "apps/settings_list.c", "tools/tests/test_talkbox_dynamic_policy.py",
            "tools/tests/test_talk_menu_policy.py", "apps/settings.c", "apps/settings_list.h")}
        settings = cls.inputs["apps/settings.h"].decode("utf-8")
        fields = []
        for name in ("tts_announce_position", "tts_announce_dynamic"):
            matches = re.findall(r"^\s*(?:bool|int)\s+" + name + r"\s*;", settings, re.MULTILINE)
            if len(matches) != 1:
                raise AssertionError("Expected one actual settings declaration for " + name)
            fields.append(matches[0].strip())
        declarations = settings_fixture(settings).replace("bool tts_enabled;",
            "bool tts_enabled;\n" + "\n".join(fields), 1)
        cls.helper = extract_block(settings, "static inline bool talk_dynamic_enabled(")
        cls.header = "#include <stdbool.h>\n" + declarations + policy_source(settings) + cls.helper
        cls.area = project_materials_root(ROOT) / "talkbox-dynamic-policy" / uuid.uuid4().hex
        cls.area.mkdir(parents=True)
        cls.results = []
        cls.case_results = []
        cls.addClassCleanup(cls.write_report)
        print("Dynamic policy evidence:", cls.area, flush=True)

    def compile_run(self, name, espeak, sanitize=False, helper=None, fails=False, fixture=None, success=None):
        source = self.area / (name + ".c")
        header = self.header if helper is None else self.header.replace(self.helper, helper, 1)
        source.write_text(header + MATRIX if fixture is None else fixture, encoding="utf-8")
        executable = self.area / (name + (".exe" if os.name == "nt" else ".bin"))
        flags = ["-std=c11" if fixture is not None else "-std=c99", "-O1", "-Wall", "-Wextra", "-Werror", "-pedantic-errors", "-UNDEBUG", "-I", str(ROOT)]
        if espeak:
            flags.append("-DHAVE_ESPEAK=1")
        if sanitize:
            flags.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
        command = self.compiler + flags + [str(source), "-o", str(executable)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.results.append(dict(stage="compile", command=command, exit=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr, passed=result.returncode == 0))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        command = [str(executable)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15,
            env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        passed = result.returncode == (101 if fails else 0)
        if fails:
            passed = passed and "CHECK_FAILED " in result.stderr
        else:
            passed = passed and (success or f"PASS dynamic policy: {720 if espeak else 36} cases") in result.stdout
        self.results.append(dict(stage="run", command=command, exit=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr, expected_failure=fails, passed=passed))
        self.assertTrue(passed, result.stdout + result.stderr)

    def test_dynamic_flag_and_unchanged_voicefile_controls(self):
        for espeak in (False, True):
            for sanitize in (False, True):
                with self.subTest(espeak=espeak, sanitize=sanitize):
                    self.compile_run(f"matrix-{espeak}-{sanitize}", espeak, sanitize)

    def test_causal_mutants_reject_ignored_flag_and_silenced_voicefiles(self):
        for name, replacement in (
            ("ignored-flag", "return talk_menus_enabled(settings);"),
            ("silenced-voicefiles", "return settings->tts_announce_dynamic && talk_menus_enabled(settings);"),
        ):
            with self.subTest(mutant=name):
                helper = "static inline bool talk_dynamic_enabled(const struct user_settings *settings)\n{\n"
                self.compile_run(name, True, helper=helper + replacement + "\n}\n", fails=True)

    def test_position_default_excludes_values_and_dynamic_remains_on(self):
        source = self.inputs["apps/settings_list.c"].decode("utf-8")
        self.assertRegex(source, r"CHOICE_SETTING\(0,\s*tts_announce_position,\s*"
            r"LANG_TALKBOX_ANNOUNCE_POSITION,\s*TTS_POSITION_EXCEPT_SLIDERS,")
        self.assertRegex(source, r"OFFON_SETTING\(0,\s*tts_announce_dynamic,\s*"
            r"LANG_TALKBOX_ANNOUNCE_DYNAMIC,\s*true,")

    def config_fixture(self):
        registration = self.inputs["apps/settings_list.c"].decode("utf-8")
        entry = re.search(r"    CHOICE_SETTING\(0, tts_announce_position,.*?ID2P\(LANG_OFF\)\),\n", registration, re.S).group()
        macro_lines = registration[registration.index("#define CHOICE_SETTING"):].splitlines()
        last_line = 0
        while macro_lines[last_line].endswith("\\"):
            last_line += 1
        macro = "\n".join(macro_lines[:last_line + 1])
        settings = self.inputs["apps/settings.h"].decode("utf-8")
        modes = extract_block(settings, "enum tts_position_mode\n").rstrip() + ";\n"
        parser = self.inputs["apps/settings.c"].decode("utf-8")
        functions = "\n".join(extract_block(parser, signature) for signature in (
            "const char* setting_get_cfgvals(", "bool cfg_string_to_int(", "bool copy_filename_setting(",
            "bool string_to_cfg(", "bool cfg_int_to_string(", "void cfg_to_string(", "void reset_setting("))
        return r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "apps/settings_list.h"
#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "CHECK_FAILED line %d: %s\n", __LINE__, #condition); return 101; } } while (0)
#define INT(value) {.int_ = value}
#define ID2P(value) ((const unsigned char *)(uintptr_t)(value))
#define logf(...) ((void)0)
enum { LANG_TALKBOX_ANNOUNCE_POSITION, LANG_TALKBOX_POSITION_EVERYWHERE,
       LANG_TALKBOX_POSITION_INTERFACE, LANG_TALKBOX_POSITION_FILES,
       LANG_TALKBOX_POSITION_EXCEPT_SLIDERS, LANG_OFF };
struct { unsigned int before; int tts_announce_position; unsigned int after;
         bool tts_announce_dynamic; } global_settings;
''' + modes + macro + "\nconst struct settings_list settings[] = {\n" + entry + r'''
};
static const struct settings_list *find_setting_by_cfgname(const char *name)
{ return strcmp(name, settings[0].cfg_name) ? NULL : &settings[0]; }
static void itoa_buf(char *buffer, int length, int value)
{ snprintf(buffer, length, "%d", value); }
static char *strmemccpy(char *destination, const char *source, size_t length)
{ if (length) snprintf(destination, length, "%s", source); return destination; }
static int sound_default(int setting) { (void)setting; return 0; }
''' + functions + r'''
int main(void)
{
    static const char *const tokens[] = { "on", "interface", "files", "except-sliders", "off" };
    static const int expected[] = { TTS_POSITION_EVERYWHERE, TTS_POSITION_INTERFACE,
        TTS_POSITION_FILES, TTS_POSITION_EXCEPT_SLIDERS, TTS_POSITION_OFF };
    global_settings.before = 0x12345678;
    global_settings.after = 0x87654321;
    global_settings.tts_announce_dynamic = true;
    bool theme_changed = false;
    CHECK((settings[0].flags & F_T_MASK) == F_T_INT);
    CHECK(settings[0].choice_setting->count == 5);
    for (unsigned int index = 0; index < 5; ++index)
    {
        char token[32], written[64];
        snprintf(token, sizeof(token), "%s", tokens[index]);
        reset_setting(&settings[0], settings[0].setting);
        CHECK(global_settings.tts_announce_position == TTS_POSITION_EXCEPT_SLIDERS);
        CHECK(string_to_cfg("tts announce position", token, &theme_changed));
        CHECK(global_settings.tts_announce_position == expected[index]);
        cfg_to_string(&settings[0], written, sizeof(written));
        CHECK(!strcmp(written, tokens[index]));
        CHECK(global_settings.before == 0x12345678 && global_settings.after == 0x87654321);
        CHECK(global_settings.tts_announce_dynamic && !theme_changed);
    }
    static const char *const invalid[] = { "true", "false", "0", "1", "everywhere", "files-extra", "ON", "" };
    for (unsigned int index = 0; index < sizeof(invalid) / sizeof(invalid[0]); ++index)
    {
        char token[32];
        snprintf(token, sizeof(token), "%s", invalid[index]);
        reset_setting(&settings[0], settings[0].setting);
        CHECK(!string_to_cfg("tts announce position", token, &theme_changed));
        CHECK(global_settings.tts_announce_position == TTS_POSITION_EXCEPT_SLIDERS);
    }
    reset_setting(&settings[0], settings[0].setting);
    CHECK(global_settings.tts_announce_position == TTS_POSITION_EXCEPT_SLIDERS);
    char old_on[] = "on", old_off[] = "off";
    CHECK(string_to_cfg("tts announce position", old_on, &theme_changed));
    CHECK(global_settings.tts_announce_position == TTS_POSITION_EVERYWHERE);
    CHECK(string_to_cfg("tts announce position", old_off, &theme_changed));
    CHECK(global_settings.tts_announce_position == TTS_POSITION_OFF);
    reset_setting(&settings[0], settings[0].setting);
    CHECK(global_settings.tts_announce_position == TTS_POSITION_EXCEPT_SLIDERS);
    puts("PASS position config roundtrip legacy defaults invalid");
    return 0;
}
'''

    def test_actual_position_config_roundtrip_legacy_boolean_and_reset_default(self):
        fixture = self.config_fixture()
        for sanitize in (False, True):
            with self.subTest(sanitize=sanitize):
                self.compile_run("position-config-" + str(sanitize), True, sanitize, fixture=fixture,
                                 success="PASS position config roundtrip legacy defaults invalid")

    def test_config_causal_mutants_reject_old_ordinal_aliases_and_changed_default(self):
        fixture = self.config_fixture()
        for name, before, after in (
            ("legacy-on-mapped-to-off", '"on,interface,files,except-sliders,off"',
             '"off,interface,files,except-sliders,on"'),
            ("default-everywhere", 'TTS_POSITION_EXCEPT_SLIDERS, "tts announce position"',
             'TTS_POSITION_EVERYWHERE, "tts announce position"'),
            ("boolean-width", "flags|F_CHOICE_SETTING|F_T_INT", "flags|F_CHOICE_SETTING|F_T_BOOL"),
        ):
            with self.subTest(mutant=name):
                self.assertEqual(fixture.count(before), 1)
                self.compile_run(name, True, fixture=fixture.replace(before, after, 1), fails=True)

    def tearDown(self):
        result = self._outcome.result
        failed = [detail for case, detail in result.failures + result.errors
                  if case is self or getattr(case, "test_case", None) is self]
        self.case_results.append(dict(test=self.id(), passed=not failed, failures=failed))

    @classmethod
    def write_report(cls):
        unchanged = all((ROOT / name).read_bytes() == data for name, data in cls.inputs.items())
        report = dict(source_project=str(ROOT), platform=sys.platform, compiler=cls.compiler,
            source_sha256={name: hashlib.sha256(data).hexdigest() for name, data in cls.inputs.items()},
            inputs_unchanged=unchanged, cases=cls.results, test_results=cls.case_results,
            passed=unchanged and bool(cls.results) and bool(cls.case_results) and
                all(result["passed"] for result in cls.results + cls.case_results),
            limitations=["Actual extracted settings policy with controlled settings; no speech backend or GUI"])
        (cls.area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not unchanged:
            raise AssertionError("Dynamic policy inputs changed during validation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
