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
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ("apps/accessibility_services.c", "apps/accessibility_services.h",
          "apps/accessibility_shortcut.c", "apps/accessibility_shortcut.h", "apps/tts.h",
          "apps/settings.h", "apps/settings_list.c", "apps/menus/settings_menu.c",
          "tools/tests/test_accessibility_service_group.py")


def without_includes(text):
    return re.sub(r'^#include[^\n]*\n', '\n', text, flags=re.MULTILINE)


def disable_core_dumps():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#endif
#undef assert
#define assert(condition) do { if (!(condition)) { \
    fprintf(stderr, "CHECK_FAILED %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(101); } } while (0)
#define HZ 100
static struct user_settings {
    bool tts_enabled, talk_menu, accessibility_shortcut_enabled,
        accessibility_shortcut_espeak, accessibility_shortcut_voice_files,
        accessibility_shortcut_touch, accessibility_shortcut_curtain;
} global_settings;
static bool touch_enabled, curtain_enabled, engine_ready, voice_ready, touch_save_ready;
static int status_calls, group_calls, splashes, saves, changes;
static int curtain_off_calls, curtain_on_calls;
static bool curtain_active_at_tts_off;
static int32_t group_labels[8];
static size_t group_count;
static bool forced_ready = true;
struct talk_debug_data { int unused; };
static void talk_init(void) {}
static bool talk_get_debug_data(struct talk_debug_data *data) { (void)data; return voice_ready; }
static void settings_save(void) { ++saves; }
static void tts_settings_changed(void)
{
    ++changes;
    if (!global_settings.tts_enabled)
        curtain_active_at_tts_off = curtain_enabled;
}
static bool tts_is_available(void) { return global_settings.tts_enabled && engine_ready; }
static int tts_speak_status(int32_t label) { (void)label; ++status_calls; return 0; }
static int tts_speak_status_ids(const int32_t *labels, size_t count)
{
    assert(labels && count && count <= 8);
    ++group_calls;
    group_count = count;
    memcpy(group_labels, labels, count * sizeof(labels[0]));
    return forced_ready ? 0 : -1;
}
static void splashf_silent(int ticks, const char *format, const char *message)
{ (void)ticks; (void)format; (void)message; ++splashes; }
#define str(label) "localized status"
#ifdef HAVE_TOUCHSCREEN
static bool accessibility_enabled(void) { return touch_enabled; }
static bool accessibility_set_enabled(bool enabled)
{
    if (!touch_save_ready && enabled != touch_enabled) return false;
    touch_enabled = enabled; return true;
}
#ifdef HAVE_SCREEN_CURTAIN
static bool backlight_screen_curtain_active(void) { return curtain_enabled; }
static bool accessibility_set_curtain_state(bool enabled, bool announce)
{
    assert(!announce);
    if (enabled) ++curtain_on_calls;
    else ++curtain_off_calls;
    if (enabled == curtain_enabled) return true;
    if (enabled && !tts_is_available()) return false;
    curtain_enabled = enabled; return true;
}
#endif
#endif
'''

HELPERS = r'''
static void reset(unsigned int selected, unsigned int state)
{
    global_settings.accessibility_shortcut_enabled = true;
    global_settings.accessibility_shortcut_espeak = !!(selected & 1);
    global_settings.accessibility_shortcut_voice_files = !!(selected & 2);
    global_settings.accessibility_shortcut_touch = !!(selected & 4);
    global_settings.accessibility_shortcut_curtain = !!(selected & 8);
    global_settings.tts_enabled = !!(state & 1);
    global_settings.talk_menu = !!(state & 2);
    touch_enabled = !!(state & 4); curtain_enabled = !!(state & 8);
    engine_ready = voice_ready = touch_save_ready = forced_ready = true;
    group_count = status_calls = group_calls = splashes = saves = changes = 0;
    curtain_off_calls = curtain_on_calls = 0;
    curtain_active_at_tts_off = false;
}
static unsigned int actual_state(void)
{
    return (global_settings.tts_enabled ? 1 : 0) | (global_settings.talk_menu ? 2 : 0) |
           (touch_enabled ? 4 : 0) | (curtain_enabled ? 8 : 0);
}
static void check_labels(unsigned int selected, unsigned int actual, bool partial)
{
    const int32_t on[] = {LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_ON,
        LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_ON, LANG_ACCESSIBILITY_TOUCH_ON,
        LANG_ACCESSIBILITY_CURTAIN_ON};
    const int32_t off[] = {LANG_ACCESSIBILITY_SHORTCUT_ESPEAK_OFF,
        LANG_ACCESSIBILITY_SHORTCUT_VOICE_FILES_OFF, LANG_ACCESSIBILITY_TOUCH_OFF,
        LANG_ACCESSIBILITY_CURTAIN_OFF};
    size_t position = 0;
    if (partial) assert(group_labels[position++] == LANG_ACCESSIBILITY_SHORTCUT_PARTIAL);
    for (unsigned int service = 0; service < 4; ++service)
        if (selected & (1u << service))
            assert(group_labels[position++] == (actual & (1u << service) ? on[service] : off[service]));
    assert(position == group_count && group_calls == 1 && !status_calls);
}
'''

MAIN = r'''
static void check_curtain_calls(unsigned int selected, unsigned int previous,
                                unsigned int supported, bool enabled,
                                int previous_off_calls, int previous_on_calls)
{
    bool supported_curtain = (supported & 8) != 0;
    bool selected_curtain = (selected & 8) ||
        (!enabled && (selected & 1) && (previous & 8));
    assert(curtain_off_calls == previous_off_calls +
           (supported_curtain && selected_curtain && !enabled));
    assert(curtain_on_calls == previous_on_calls +
           (supported_curtain && selected_curtain && enabled));
}

int main(void)
{
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
#endif
    unsigned int supported = 3;
#ifdef HAVE_TOUCHSCREEN
    supported |= 4;
#ifdef HAVE_SCREEN_CURTAIN
    supported |= 8;
#endif
#endif
    unsigned int cases = 0;
    for (unsigned int selected = 0; selected < 16; ++selected)
        for (unsigned int state = 0; state < 16; ++state)
        {
            reset(selected, state);
            unsigned int mask = selected & supported;
            bool enabled = (state & mask) != mask;
            bool possible = !enabled || !(mask & 8) || (state & 8) || (state & 1) || (mask & 1);
            bool success = accessibility_services_activate();
            assert(success == (mask && possible));
            check_curtain_calls(mask, state, supported, enabled, 0, 0);
            unsigned int expected = enabled ? state | mask : state & ~mask;
            if (!enabled && (mask & 1) && (supported & 8)) expected &= ~8u;
            if (!possible) expected &= ~8u;
            if (actual_state() != expected)
                fprintf(stderr, "matrix selected=%u state=%u expected=%u actual=%u\n",
                        selected, state, expected, actual_state());
            assert(actual_state() == expected);
            if (!enabled && (mask & 1) && (supported & 8))
                assert(!curtain_active_at_tts_off);
            unsigned int reported = mask | ((state ^ expected) & supported & 8u);
            if (!mask)
            {
                assert(group_count == 1 && group_labels[0] == LANG_ACCESSIBILITY_SHORTCUT_EMPTY);
                assert(!status_calls && !saves && !changes);
            }
            else check_labels(reported, expected, !possible);
            if (mask && possible)
            {
                group_calls = 0;
                bool next_possible = enabled || !(mask & 8) || (expected & 8) || (expected & 1) || (mask & 1);
                int previous_off_calls = curtain_off_calls;
                int previous_on_calls = curtain_on_calls;
                assert(accessibility_services_activate() == next_possible);
                unsigned int previous = expected;
                check_curtain_calls(mask, previous, supported, !enabled,
                                    previous_off_calls, previous_on_calls);
                expected = enabled ? expected & ~mask : expected | mask;
                if (enabled && (mask & 1) && (supported & 8)) expected &= ~8u;
                if (!next_possible) expected &= ~8u;
                assert(actual_state() == expected);
                if (enabled && (mask & 1) && (supported & 8))
                    assert(!curtain_active_at_tts_off);
                reported = mask | ((previous ^ expected) & supported & 8u);
                check_labels(reported, expected, !next_possible);
            }
            ++cases;
        }
    reset(15, 15);
    global_settings.accessibility_shortcut_enabled = false;
    assert(!accessibility_services_activate());
    assert(actual_state() == 15 && !saves && !changes);
    assert(group_count == 1 && group_labels[0] == LANG_ACCESSIBILITY_SHORTCUT_DISABLED);
    reset(1, 0); engine_ready = false;
    assert(!accessibility_services_activate());
    check_labels(1, 0, true);
    assert(!global_settings.tts_enabled && !saves && changes == 2);
    reset(2, 0); voice_ready = false;
    assert(!accessibility_services_activate());
    check_labels(2, 0, true);
    assert(!global_settings.talk_menu);
#ifdef HAVE_TOUCHSCREEN
    reset(5, 0); touch_save_ready = false;
    assert(!accessibility_services_activate());
    check_labels(5, 1, true);
    assert(actual_state() == 1);
#endif
    reset(1, 1); forced_ready = false;
    assert(accessibility_services_activate());
    assert(!global_settings.tts_enabled && splashes == 1 && group_calls == 1 && !status_calls);
    printf("PASS grouped services %u state/selection cases and failure controls\n", cases);
    return 0;
}
'''

DEPENDENCY_MAIN = r'''
int main(void)
{
    reset(1, 15);
    assert(accessibility_services_activate());
    assert(actual_state() == 6);
    assert(!curtain_active_at_tts_off && curtain_off_calls == 1 && !curtain_on_calls);
    check_labels(9, 6, false);
    group_calls = 0;
    assert(accessibility_services_activate());
    assert(actual_state() == 7 && curtain_off_calls == 1 && !curtain_on_calls);
    check_labels(1, 7, false);

    reset(9, 9);
    assert(accessibility_services_activate());
    assert(actual_state() == 0 && !curtain_active_at_tts_off);
    check_labels(9, 0, false);
    group_calls = 0;
    assert(accessibility_services_activate());
    assert(actual_state() == 9 && curtain_off_calls == 1 && curtain_on_calls == 1);
    check_labels(9, 9, false);

    reset(1, 9); engine_ready = false;
    assert(accessibility_services_activate());
    assert(actual_state() == 0 && !curtain_active_at_tts_off);
    check_labels(9, 0, false);
    group_calls = 0;
    assert(!accessibility_services_activate());
    assert(actual_state() == 0 && curtain_off_calls == 1 && !curtain_on_calls);
    check_labels(1, 0, true);

    reset(9, 0); engine_ready = false;
    assert(!accessibility_services_activate());
    assert(actual_state() == 0 && !curtain_off_calls && curtain_on_calls == 1);
    check_labels(9, 0, true);

    reset(5, 13); touch_save_ready = false;
    assert(!accessibility_services_activate());
    assert(actual_state() == 4 && !curtain_active_at_tts_off);
    check_labels(13, 4, true);
    assert(curtain_off_calls == 1 && !curtain_on_calls);

    reset(1, 9); forced_ready = false;
    assert(accessibility_services_activate());
    assert(actual_state() == 0 && splashes == 1 && !curtain_active_at_tts_off);
    check_labels(9, 0, false);
    assert(curtain_off_calls == 1 && !curtain_on_calls);

    reset(1, 0); forced_ready = false;
    assert(accessibility_services_activate());
    assert(actual_state() == 1 && splashes == 1 && !curtain_off_calls && !curtain_on_calls);
    check_labels(1, 1, false);

    reset(2, 8); voice_ready = false;
    assert(!accessibility_services_activate());
    assert(actual_state() == 8 && !curtain_off_calls && !curtain_on_calls);
    check_labels(2, 8, true);

    reset(4, 8); touch_save_ready = false;
    assert(!accessibility_services_activate());
    assert(actual_state() == 8 && !curtain_off_calls && !curtain_on_calls);
    check_labels(4, 8, true);

    reset(0, 15); forced_ready = false;
    assert(!accessibility_services_activate());
    assert(actual_state() == 15 && splashes == 1 && group_calls == 1 && !status_calls);
    assert(group_labels[0] == LANG_ACCESSIBILITY_SHORTCUT_EMPTY);
    assert(!saves && !changes && !curtain_off_calls && !curtain_on_calls);

    reset(1, 15); forced_ready = false;
    global_settings.accessibility_shortcut_enabled = false;
    assert(!accessibility_services_activate());
    assert(actual_state() == 15 && splashes == 1 && group_calls == 1 && !status_calls);
    assert(group_labels[0] == LANG_ACCESSIBILITY_SHORTCUT_DISABLED);
    assert(!saves && !changes && !curtain_off_calls && !curtain_on_calls);
    puts("PASS synchronous dependent curtain, bounded enable, combined status and failure controls");
    return 0;
}
'''


class AccessibilityServiceGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable")
        cls.inputs = {name: (ROOT / name).read_bytes() for name in INPUTS}
        workspace = project_materials_root(ROOT)
        evidence_root = os.environ.get("ACCESSIBILITY_GROUP_EVIDENCE_ROOT")
        cls.area = confined_path(Path(evidence_root) if evidence_root else
                                workspace / "accessibility-group-tests", workspace) / uuid.uuid4().hex
        cls.area.mkdir(parents=True)
        code = '\n'.join(without_includes(cls.inputs[name].decode("utf-8")) for name in
                        ("apps/accessibility_shortcut.c", "apps/accessibility_services.c"))
        labels = sorted(set(re.findall(r'\bLANG_[A-Z0-9_]+\b', code)))
        cls.fixture = PREAMBLE + "\nenum {" + ','.join(labels) + "};\n" + code + HELPERS
        cls.code = cls.fixture + MAIN
        cls.results = []
        cls.case_results = []

    @classmethod
    def run_source(cls, name, content, defines=(), sanitize=False, failure=False):
        source = cls.area / (name + ".c")
        source.write_text(content, encoding="utf-8")
        binary = cls.area / (name + (".exe" if os.name == "nt" else ".bin"))
        flags = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-O1", "-UNDEBUG"]
        if sanitize:
            flags += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        command = cls.compiler + flags + ["-D" + define for define in defines] + [str(source), "-o", str(binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        cls.results.append(dict(name=name, kind="compile", command=command, exit=result.returncode,
                                stdout=result.stdout, stderr=result.stderr, passed=result.returncode == 0))
        if result.returncode:
            raise AssertionError(result.stderr)
        try:
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15,
                env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"),
                preexec_fn=disable_core_dumps if os.name != "nt" else None,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except BaseException as error:
            cls.results.append(dict(name=name, kind="run-exception", error=repr(error),
                                    expected_failure=failure, passed=False))
            raise
        passed = (result.returncode == 101 and "CHECK_FAILED " in result.stderr) if failure else result.returncode == 0
        cls.results.append(dict(name=name, kind="run", exit=result.returncode,
                                stdout=result.stdout, stderr=result.stderr, passed=passed, expected_failure=failure))
        if not passed:
            raise AssertionError(result.stdout + result.stderr)

    def test_actual_group_and_quiet_setters_all_service_states(self):
        for suffix, defines in (("physical", ("HAVE_ESPEAK",)),
                ("curtain-without-touch", ("HAVE_ESPEAK", "HAVE_SCREEN_CURTAIN")),
                ("touch", ("HAVE_ESPEAK", "HAVE_TOUCHSCREEN")),
                ("curtain", ("HAVE_ESPEAK", "HAVE_TOUCHSCREEN", "HAVE_SCREEN_CURTAIN"))):
            for sanitize in (False, True):
                with self.subTest(configuration=suffix, sanitize=sanitize):
                    self.run_source(suffix + ("-ubsan" if sanitize else "-ordinary"), self.code, defines, sanitize)

    def test_dependent_curtain_is_synchronous_and_bounded_with_failures(self):
        for sanitize in (False, True):
            with self.subTest(sanitize=sanitize):
                self.run_source("dependency" + ("-ubsan" if sanitize else "-ordinary"),
                                self.fixture + DEPENDENCY_MAIN,
                                ("HAVE_ESPEAK", "HAVE_TOUCHSCREEN", "HAVE_SCREEN_CURTAIN"), sanitize)

    def test_mixed_state_mutant_is_rejected(self):
        old = "& selected) != selected"
        self.assertEqual(self.code.count(old), 1)
        mutant = self.code.replace(old, "& selected) == 0", 1)
        self.run_source("mixed-state-mutant", mutant, ("HAVE_ESPEAK", "HAVE_TOUCHSCREEN"), failure=True)

    def test_non_espeak_stub_needs_no_service_dependencies(self):
        code = without_includes(self.inputs["apps/accessibility_services.c"].decode("utf-8"))
        self.run_source("no-espeak", "#include <stdbool.h>\n" + code +
                        "\nint main(void) { return accessibility_services_activate() ? 1 : 0; }\n")

    def test_preferences_and_menu_have_one_group_and_keep_individual_actions(self):
        settings = self.inputs["apps/settings_list.c"].decode("utf-8")
        menu = self.inputs["apps/menus/settings_menu.c"].decode("utf-8")
        self.assertEqual(menu.count("MAKE_MENU(accessibility_shortcut_menu,"), 1)
        self.assertEqual(menu.count("&accessibility_shortcut_menu,"), 1)
        self.assertIn("&accessibility_shortcut_services_menu", menu)
        for service, default in (("enabled", "true"), ("espeak", "true"), ("voice_files", "false"),
                                 ("touch", "true"), ("curtain", "false")):
            self.assertRegex(settings, r'OFFON_SETTING\(0, accessibility_shortcut_' + service +
                             r', [A-Z_]+, ' + default + r',')
        self.assertNotIn("RBACCESSIBILITY-SHORTCUT", settings + menu)

    def tearDown(self):
        result = self._outcome.result
        failed = [detail for case, detail in result.failures + result.errors
                  if case is self or getattr(case, "test_case", None) is self]
        self.case_results.append(dict(test=self.id(), passed=not failed, failures=failed))

    @classmethod
    def tearDownClass(cls):
        unchanged = all((ROOT / name).read_bytes() == data for name, data in cls.inputs.items())
        report = dict(passed=unchanged and bool(cls.results) and bool(cls.case_results) and
            all(item["passed"] for item in cls.results + cls.case_results),
            inputs_unchanged=unchanged, platform=sys.platform,
            source_sha256={name: hashlib.sha256(data).hexdigest() for name, data in cls.inputs.items()},
            cases=cls.results, test_results=cls.case_results,
            scope="Real complete group and direct setter C; mocked backend/settings storage",
            limitations=["Touch-file persistence belongs to manager tests; forced PCM belongs to reader notice tests",
                         "No physical player, actual engine, GUI or NVDA acceptance"])
        (cls.area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Group evidence:", cls.area, flush=True)
        if not unchanged:
            raise AssertionError("Group sources changed during validation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
