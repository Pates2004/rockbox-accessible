"""Exercise real setting descriptors, numeric speech and self-voicing time IDs."""

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

from test_polish_translation import parse_language
from test_tts_coverage import extract_block

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
CALLBACKS = (
    "getlang_time_unit_0_is_always", "getlang_time_unit_0_is_off",
    "getlang_time_unit_0_is_skip_track", "getlang_time_unit_0_is_eternal",
)
INPUTS = (
    "apps/settings_list.c", "apps/settings_list.h", "apps/gui/option_select.c",
    "apps/talk.c", "apps/talk.h", "apps/misc.c", "apps/misc.h",
    "apps/lang/english.lang", "apps/lang/polski.lang",
    "firmware/export/config/hibyr1.h", "firmware/export/config/sansaclipzip.h",
    "firmware/export/config/sansaclipplus.h",
)
PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "apps/talk.h"
#include "apps/settings_list.h"
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #condition); exit(1); } } while (0)
#define ARRAYLEN(values) (sizeof(values) / sizeof((values)[0]))
#define HASFLAG(setting, flag) (((setting)->flags & (flag)) == (flag))
#define INT(value) { .int_ = (value) }
#define P2ID(value) ((intptr_t)(value))
#define LIST_ORDER_DESCENDING 1
#define SOUND_VOLUME 1
static struct {
    int brightness, backlight_timeout, backlight_timeout_plugged;
    int remote_backlight_timeout, remote_backlight_timeout_plugged;
    int list_order, volume_limit;
} global_settings;
static int table_setting_oldval, table_setting_array_position;
static int language, talk_handle = 1, index_handle = 1;
static bool disabled;
#ifdef HAVE_ESPEAK
static bool available = true;
#endif
static unsigned int cases, hardware_calls;
static int hardware_value;
static char spoken[2048];
static long numbers[16];
static size_t number_count;
static unsigned int rockbox_count;
static bool talk_is_disabled(void) { return disabled; }
#ifdef HAVE_ESPEAK
static bool tts_is_available(void) { return available; }
#endif
static bool lang_units_first(void) { return false; }
static int open_voicefile(void) { return -1; }
static bool load_voicefile_index(int descriptor) { (void)descriptor; return false; }
static void load_voicefile_data(int descriptor) { (void)descriptor; }
static int fixture_close(int descriptor) { (void)descriptor; return 0; }
#define close fixture_close
static void do_enqueue(bool enqueue)
{
    if (!enqueue) { spoken[0] = '\0'; number_count = 0; }
}
static void append(const char *text)
{
    if (*spoken) strncat(spoken, "|", sizeof(spoken) - strlen(spoken) - 1);
    strncat(spoken, text, sizeof(spoken) - strlen(spoken) - 1);
}
int talk_number(long number, bool enqueue)
{
    if (disabled) return -1;
    do_enqueue(enqueue);
    CHECK(number_count < ARRAYLEN(numbers));
    numbers[number_count++] = number;
    char buffer[48];
    snprintf(buffer, sizeof(buffer), "%ld", number);
    append(buffer);
    return 0;
}
static int talk_year(long number, bool enqueue)
{ (void)number; (void)enqueue; CHECK(false); return -1; }
void talk_fractional(char *buffer, int value, int unit)
{ (void)buffer; (void)value; (void)unit; CHECK(false); }
static void backlight_set_brightness(int value)
{ ++hardware_calls; hardware_value = value; }
static void backlight_set_timeout(int value) { (void)value; }
static void backlight_set_timeout_plugged(int value) { (void)value; }
static void remote_backlight_set_timeout(int value) { (void)value; }
static void remote_backlight_set_timeout_plugged(int value) { (void)value; }
static const char *sound_unit(int setting) { (void)setting; return "dB"; }
static int sound_numdecimals(int setting) { (void)setting; return 0; }
static int sound_val2phys(int setting, int value) { (void)setting; return value; }
static int sound_steps(int setting) { (void)setting; return 1; }
static int sound_min(int setting) { (void)setting; return -100; }
static int sound_max(int setting) { (void)setting; return 100; }
static void (*sound_get_fn(int setting))(int)
{ (void)setting; return NULL; }
'''
SUFFIX = r'''
static void reset(void)
{
    disabled = false;
#ifdef HAVE_ESPEAK
    available = true;
#endif
    talk_handle = index_handle = 1;
    spoken[0] = '\0';
    number_count = rockbox_count = 0;
}
static void no_rockbox(void)
{
    if (rockbox_count || strstr(spoken, "Rockbox"))
    {
        fprintf(stderr, "Unexpected Rockbox after numeric setting: %s\n", spoken);
        exit(1);
    }
}
static struct settings_list with_callback(int32_t (*callback)(int, int), int unit)
{
    static struct int_setting info;
    info = (struct int_setting){ .unit = unit, .get_talk_id = callback };
    return (struct settings_list){ .flags = F_INT_SETTING | F_TIME_SETTING,
                                  .int_setting = &info };
}
static void check_special(int32_t (*callback)(int, int), int value, int identifier)
{
    reset();
    struct settings_list setting = with_callback(callback, UNIT_SEC);
    option_talk_value(&setting, value, false);
    no_rockbox();
    CHECK(!strcmp(spoken, voice_text(identifier)) && number_count == 0);
    ++cases;
}
static void test_callbacks(void)
{
    int32_t (*callbacks[])(int, int) = {
        getlang_time_unit_0_is_always, getlang_time_unit_0_is_off,
        getlang_time_unit_0_is_skip_track, getlang_time_unit_0_is_eternal,
    };
    const int durations[] = {1, 2, 15, 59, 60, 61, 900, 3600, 3661, 7200};
    const int units[] = {UNIT_MS, UNIT_SEC, UNIT_MIN, UNIT_HOUR};
    for (size_t callback = 0; callback < ARRAYLEN(callbacks); ++callback)
        for (size_t unit = 0; unit < ARRAYLEN(units); ++unit)
            for (size_t duration = 0; duration < ARRAYLEN(durations); ++duration)
            {
                reset();
                struct settings_list setting = with_callback(callbacks[callback], units[unit]);
                option_talk_value(&setting, durations[duration], false);
                no_rockbox();
                CHECK(number_count > 0 && spoken[0]);
                char expected[sizeof(spoken)];
                strcpy(expected, spoken);
                reset();
                CHECK(callbacks[callback](durations[duration], units[unit]) == -1);
                CHECK(!strcmp(expected, spoken));
                reset();
                disabled = true;
                option_talk_value(&setting, durations[duration], false);
                CHECK(!spoken[0] && !rockbox_count);
                reset();
#ifdef HAVE_ESPEAK
                available = false;
#endif
                talk_handle = index_handle = 0;
                option_talk_value(&setting, durations[duration], false);
                CHECK(!spoken[0] && !rockbox_count);
                CHECK(callbacks[callback](durations[duration], units[unit]) == -1);
                ++cases;
            }
    check_special(getlang_time_unit_0_is_always, -1, LANG_NEVER);
    check_special(getlang_time_unit_0_is_always, 0, LANG_ALWAYS);
    check_special(getlang_time_unit_0_is_off, 0, LANG_OFF);
    check_special(getlang_time_unit_0_is_skip_track, -1, LANG_SKIP_OUTRO);
    check_special(getlang_time_unit_0_is_skip_track, 0, LANG_SKIP_TRACK);
    check_special(getlang_time_unit_0_is_eternal, 0, LANG_PM_ETERNAL);
}
static void test_descriptors(void)
{
    for (size_t descriptor = 0; descriptor < ARRAYLEN(display_settings); ++descriptor)
    {
        const struct settings_list *setting = &display_settings[descriptor];
        int count = 0, selected = 0;
        void (*apply)(int) = NULL;
        bool brightness = !strcmp(setting->cfg_name, "brightness");
        for (int order = 0; order <= LIST_ORDER_DESCENDING; ++order)
        {
            global_settings.list_order = order;
            int initial = brightness ? DEFAULT_BRIGHTNESS_SETTING : 15;
            val_to_selection(setting, initial, &count, &selected, &apply);
            CHECK(count > 1 && selected >= 0 && selected < count && apply);
            CHECK(selection_to_val(setting, selected) == initial);
            for (int position = 0; position < count; ++position)
            {
                int value = selection_to_val(setting, position);
                reset();
                CHECK(option_talk(position, (void *)setting) == 0);
                no_rockbox();
                if (brightness)
                {
                    CHECK(number_count == 1 && numbers[0] == value);
                    CHECK(setting->int_setting->unit == UNIT_INT);
                    CHECK(value >= MIN_BRIGHTNESS_SETTING && value <= MAX_BRIGHTNESS_SETTING);
                    unsigned int previous = hardware_calls;
                    apply(value);
                    CHECK(hardware_calls == previous + 1 && hardware_value == value);
                }
                else if (value == -1 || value == 0)
                    CHECK(!strcmp(spoken, voice_text(value == -1 ? LANG_NEVER : LANG_ALWAYS)));
                else
                    CHECK(number_count > 0);
                ++cases;
            }
        }
    }
}
static void test_numeric_units_and_status(void)
{
    const int values[] = {0, 1, 50, 100};
    for (size_t index = 0; index < ARRAYLEN(values); ++index)
    {
        struct int_setting info = { .unit = UNIT_PERCENT };
        struct settings_list setting = { .flags = F_INT_SETTING, .int_setting = &info };
        reset();
        option_talk_value(&setting, values[index], false);
        no_rockbox();
        CHECK(number_count == 1 && numbers[0] == values[index]);
        CHECK(strstr(spoken, voice_text(VOICE_PERCENT)));
        ++cases;
    }
    reset();
    CHECK(talk_time_intervals(15, UNIT_SEC, false) == 0);
    CHECK(number_count == 1 && numbers[0] == 15);
    reset();
    disabled = true;
    CHECK(talk_time_intervals(15, UNIT_SEC, false) == -1 && !spoken[0]);
    reset();
#ifdef HAVE_ESPEAK
    available = false;
#endif
    talk_handle = index_handle = 0;
    CHECK(talk_time_intervals(15, UNIT_SEC, false) == -1 && !spoken[0]);
    cases += 3;
}
int main(int argc, char **argv)
{
    CHECK(argc == 2);
    language = atoi(argv[1]);
    CHECK(language == 0 || language == 1);
    CHECK(LANG_ROCKBOX_TITLE == 0);
    test_callbacks();
    test_descriptors();
    test_numeric_units_and_status();
    printf("{\"cases\":%u,\"language\":%d,\"status\":\"passed\"}\n", cases, language);
    return 0;
}
'''


def macro_definition(source, name):
    found = []
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("#define " + name + "("):
            definition = line
            while definition.rstrip().endswith("\\"):
                index += 1
                definition += lines[index]
            found.append(definition)
    if not found:
        raise AssertionError("Missing production macro: " + name)
    return found[-1]


def setting_declaration(source, name):
    match = re.search(r"\b(?:INT_SETTING|TABLE_SETTING_LIST)\(\s*[^,]+,\s*"
                      + re.escape(name) + r"\s*,", source)
    if match is None:
        raise AssertionError("Missing production setting: " + name)
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|[()]', source[match.start():])
    depth = 0
    for token in tokens:
        if token.group() == "(":
            depth += 1
        elif token.group() == ")":
            depth -= 1
            if depth == 0:
                return source[match.start():match.start() + token.end()]
    raise AssertionError("Unclosed production setting: " + name)


class BacklightSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or shutil.which(cls.compiler[0]) is None:
            raise unittest.SkipTest("A native GCC-compatible C compiler is required")
        version = subprocess.run([cls.compiler[0], "--version"], capture_output=True, text=True, timeout=30)
        if version.returncode:
            raise RuntimeError(version.stderr)
        cls.compiler_version = version.stdout
        central = project_materials_root(ROOT)
        evidence_root = Path(os.environ.get("ROCKBOX_BACKLIGHT_TEST_ROOT", str(central / "backlight-speech-tests")))
        cls.area = confined_path(evidence_root, central) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.area.mkdir(parents=True)
        cls.sources = {name: (ROOT / name).read_text(encoding="utf-8") for name in INPUTS}
        cls.inputs = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
        cls.catalogs = [parse_language(cls.sources["apps/lang/" + name + ".lang"])
                        for name in ("english", "polski")]
        cls.runs = []

    @classmethod
    def tearDownClass(cls):
        stable_inputs = ("apps/settings_list.c", "apps/gui/option_select.c", "apps/talk.c",
                         "apps/talk.h", "apps/settings_list.h", "apps/misc.c", "apps/misc.h")
        report = {
            "runs": cls.runs, "inputs_sha256": cls.inputs,
            "compiler_version": cls.compiler_version,
            "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "compiled_inputs_stable": all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                          == cls.inputs[name] for name in stable_inputs),
            "boundaries": ["voice queue/ID output", "hardware brightness callback", "sound settings",
                           "disabled/engine availability", "voicefile loading failure"],
            "limitations": ["No live synthesis, PCM, GUI, physical R1, radios or backlight hardware",
                            "Catalog-derived symbolic IDs are not target-generated ABI headers"],
        }
        report["status"] = "passed" if len(cls.runs) == 40 and report["compiled_inputs_stable"] and all(
            entry["exit"] == (1 if entry["intentional_old_callback"] else 0)
            and (not entry["intentional_old_callback"] or "Unexpected Rockbox after numeric setting" in entry["stderr"])
            for entry in cls.runs) else "failed"
        (cls.area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def harness(self, target, mutated_callback=None):
        settings = self.sources["apps/settings_list.c"]
        talk = self.sources["apps/talk.c"]
        options = self.sources["apps/gui/option_select.c"]
        callbacks = [extract_block(settings, "static int32_t " + name + "(") for name in CALLBACKS]
        if mutated_callback is not None:
            index = CALLBACKS.index(mutated_callback)
            old = callbacks[index]
            callbacks[index], count = re.subn(
                r"talk_time_intervals\(value, unit, false\);\s*return -1;",
                "return talk_time_intervals(value, unit, false);", old,
            )
            self.assertEqual(count, 1, "The causal mutation must restore only the old status return")
        identifiers = list(self.catalogs[0])
        self.assertEqual(identifiers[0], "LANG_ROCKBOX_TITLE")
        enum = "enum {\n" + ",\n".join(identifiers) + "\n};\n"
        labels = []
        for identifier in identifiers:
            if identifier.startswith("VOICE_") or identifier in {
                    "LANG_ROCKBOX_TITLE", "LANG_NEVER", "LANG_ALWAYS", "LANG_OFF",
                    "LANG_SKIP_OUTRO", "LANG_SKIP_TRACK", "LANG_PM_ETERNAL", "LANG_MEBIBYTE"}:
                texts = [catalog[identifier]["voice"]["*"] for catalog in self.catalogs]
                if all(text.startswith('"') for text in texts):
                    labels.append("case " + identifier + ": return language ? "
                                  + texts[1] + " : " + texts[0] + ";")
        labels_source = "static const char *voice_text(int identifier) { switch(identifier) {\n" \
            + "\n".join(labels) + '\ndefault: return ""; } }\n'
        labels_source += r'''
#define str(identifier) voice_text(identifier)
int talk_id(int32_t identifier, bool enqueue)
{
    if (identifier == -1 || disabled) return -1;
    do_enqueue(enqueue);
    if (identifier == LANG_ROCKBOX_TITLE) ++rockbox_count;
    append(voice_text(identifier));
    return 0;
}
'''
        declarations = []
        for name in ("brightness", "backlight_timeout", "backlight_timeout_plugged",
                     "remote_backlight_timeout", "remote_backlight_timeout_plugged"):
            declarations.append(setting_declaration(settings, name))
        config = self.sources["firmware/export/config/" + target + ".h"]
        constants = []
        for name in ("MIN_BRIGHTNESS_SETTING", "MAX_BRIGHTNESS_SETTING", "DEFAULT_BRIGHTNESS_SETTING"):
            constants.append(re.search(r"(?m)^#define\s+" + name + r"\s+\d+", config).group())
        timeout_table = re.search(r"static const int timeout_sec_common\[\] =[^;]+;", settings).group()
        parts = [PREFIX, enum, labels_source,
                 extract_block(self.sources["apps/misc.h"], "enum e_fmt_time_auto_idx") + ";",
                 re.search(r"(?m)^#define UNIT_IDX_MASK[^\n]*", self.sources["apps/misc.h"]).group(),
                 extract_block(self.sources["apps/misc.c"], "unsigned int time_split_units("),
                 extract_block(talk, "static inline int load_voicefile_failure("),
                 extract_block(talk, "static int talk_time_unit("),
                 extract_block(talk, "int talk_value(long n,"),
                 extract_block(talk, "int talk_value_decimal("),
                 extract_block(talk, "static inline void talk_time_value("),
                 extract_block(talk, "int talk_time_intervals("), *callbacks,
                 extract_block(settings, "static const char* formatter_time_unit_0_is_always("),
                 macro_definition(settings, "INT_SETTING"), macro_definition(settings, "TABLE_SETTING_LIST"),
                 "\n".join(constants), "#define DEFAULT_BACKLIGHT_TIMEOUT 15", timeout_table,
                 'static const char off_on[] = "off,on";',
                 "static const struct settings_list display_settings[] = {\n"
                 + ",\n".join(declarations) + "\n};",
                 "static int selection_to_val(const struct settings_list *, int);",
                 extract_block(options, "void option_talk_value("),
                 extract_block(options, "static int option_talk("),
                 extract_block(options, "static int selection_to_val(const struct settings_list *setting, int selection)\n{"),
                 extract_block(options, "static void (*boolfunction)"),
                 extract_block(options, "static void val_to_selection("), SUFFIX]
        return "\n".join(parts)

    def run_fixture(self, target, espeak, sanitize, mutated_callback=None):
        name = "-".join((target, "espeak" if espeak else "legacy", "ubsan" if sanitize else "plain",
                         mutated_callback or "production"))
        directory = self.area / name
        directory.mkdir()
        harness = directory / "host.c"
        harness.write_text(self.harness(target, mutated_callback), encoding="utf-8")
        executable = directory / ("host.exe" if os.name == "nt" else "host")
        command = self.compiler + ["-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                                   "-Wno-override-init",
                                   "-I" + str(ROOT), str(harness), "-o", str(executable)]
        if "clang" not in self.compiler_version.lower():
            command.append("-Wimplicit-fallthrough=1")
        if espeak:
            command.append("-DHAVE_ESPEAK")
        if sanitize:
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
        built = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        (directory / "build.json").write_text(json.dumps(dict(command=command, exit=built.returncode,
                                                               stdout=built.stdout, stderr=built.stderr), indent=2), encoding="utf-8")
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        for language in (0, 1):
            result = subprocess.run([str(executable), str(language)], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=30,
                                    env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
            report = dict(name=name, language=language, exit=result.returncode,
                          stdout=result.stdout, stderr=result.stderr,
                          intentional_old_callback=mutated_callback,
                          harness_sha256=hashlib.sha256(harness.read_bytes()).hexdigest())
            self.runs.append(report)
            (directory / (str(language) + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.assertNotIn("runtime error:", result.stderr)
            if mutated_callback:
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("Unexpected Rockbox after numeric setting", result.stderr)
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertGreater(json.loads(result.stdout)["cases"], 300)

    def test_real_descriptors_espeak_plain(self):
        for target in ("hibyr1", "sansaclipzip", "sansaclipplus"):
            with self.subTest(target=target):
                self.run_fixture(target, True, False)

    def test_real_descriptors_legacy_plain(self):
        for target in ("hibyr1", "sansaclipzip", "sansaclipplus"):
            with self.subTest(target=target):
                self.run_fixture(target, False, False)

    def test_real_descriptors_espeak_ubsan(self):
        for target in ("hibyr1", "sansaclipzip", "sansaclipplus"):
            with self.subTest(target=target):
                self.run_fixture(target, True, True)

    def test_real_descriptors_legacy_ubsan(self):
        for target in ("hibyr1", "sansaclipzip", "sansaclipplus"):
            with self.subTest(target=target):
                self.run_fixture(target, False, True)

    def test_old_status_returns_are_rejected_espeak_ubsan(self):
        for callback in CALLBACKS:
            with self.subTest(callback=callback):
                self.run_fixture("hibyr1", True, True, callback)

    def test_old_status_returns_are_rejected_legacy_ubsan(self):
        for callback in CALLBACKS:
            with self.subTest(callback=callback):
                self.run_fixture("hibyr1", False, True, callback)


if __name__ == "__main__":
    unittest.main()
