"""Exercise production empty-target policy, atomic persistence and disk-only PCM."""

from datetime import datetime, timezone
import ctypes
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root
from test_keyclick_pcm import PREAMBLE as PCM_PREAMBLE, definition, without_includes
import test_accessibility_settings as settings_fixture


ROOT = Path(__file__).resolve().parents[2]
IO_FIXTURE = r'''
#include <assert.h>
#include <fcntl.h>
#include <sys/types.h>
#define ROCKBOX_DIR "/.rockbox"
#define HZ 100
#define MENU_ATTACHED_USB 313
#define ID2P(value) (value)
#define STR(value) ((const unsigned char *)(uintptr_t)(value)), (value)
#define ARRAYLEN(values) (sizeof(values) / sizeof((values)[0]))
#define LANG_ACCESSIBILITY_EMPTY_FEEDBACK 1
#define LANG_ACCESSIBILITY_EMPTY_SOUND_ONLY 2
#define LANG_ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH 3
#define LANG_ACCESSIBILITY_EMPTY_SPEECH_ONLY 4
#define LANG_ERROR_WRITING_CONFIG 5
#define LANG_ACCESSIBILITY_EMPTY 6
enum optiontype { RB_INT };
struct opt_items { const unsigned char *string; int32_t voice_id; };
static unsigned char stored[256], staged[256];
static size_t stored_size, staged_size, input_offset;
static bool stored_exists, staged_exists, staged_synced, staged_closed, fixture_usb;
static int fixture_fault, fixture_choice, fixture_errors, fixture_spoken;
static int fixture_reads, fixture_writes, fixture_opens, fixture_removes;
static int fixture_read_closes, fixture_write_closes, fixture_syncs, fixture_renames;
static int fixture_option_initial, fixture_option_count;
static bool point_pending, point_force, point_single_tap, exploring, have_context;
static int recognizer;
static void accessibility_typing_cancel_touch(void) {}
static void accessibility_gesture_reset(int *value) { *value = 0; }
static const char *str(int label) { (void)label; return "label"; }
static void splash(int ticks, int label)
{ assert(ticks == HZ * 2 && label == LANG_ERROR_WRITING_CONFIG); ++fixture_errors; }
static void talk_id(int label, bool enqueue)
{ assert(label == LANG_ACCESSIBILITY_EMPTY && !enqueue); ++fixture_spoken; }
static bool set_option(const char *title, const void *value, enum optiontype type,
                       const struct opt_items *options, int count, void (*callback)(int))
{
    assert(title && type == RB_INT && count == 3 && !callback);
    assert(options[0].voice_id == LANG_ACCESSIBILITY_EMPTY_SOUND_ONLY);
    assert(options[1].voice_id == LANG_ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH);
    assert(options[2].voice_id == LANG_ACCESSIBILITY_EMPTY_SPEECH_ONLY);
    fixture_option_count = count;
    fixture_option_initial = *(const int *)value;
    *(int *)value = fixture_choice;
    return fixture_usb;
}
static int fixture_open(const char *path, int flags, ...)
{
    ++fixture_opens;
    if (flags == O_RDONLY)
    {
        assert(!strcmp(path, ROCKBOX_DIR "/empty-feedback.cfg"));
        if (!stored_exists || fixture_fault == 8) return -1;
        input_offset = 0;
        return 13;
    }
    assert(flags == (O_WRONLY | O_CREAT | O_TRUNC));
    assert(!strcmp(path, ROCKBOX_DIR "/empty-feedback.cfg.tmp"));
    if (fixture_fault == 1) return -1;
    staged_size = 0;
    staged_exists = true;
    staged_synced = staged_closed = false;
    return 14;
}
static ssize_t fixture_read(int descriptor, void *data, size_t size)
{
    assert(descriptor == 13);
    ++fixture_reads;
    if (fixture_fault == 9 || (fixture_fault == 11 && input_offset)) return -1;
    size_t available = stored_size - input_offset;
    if (size > available) size = available;
    if (size > 2) size = 2;
    memcpy(data, stored + input_offset, size);
    input_offset += size;
    return size;
}
static ssize_t fixture_write(int descriptor, const void *data, size_t size)
{
    assert(descriptor == 14 && staged_exists && !staged_closed);
    ++fixture_writes;
    if (fixture_fault == 2 || (fixture_fault == 4 && staged_size)) return -1;
    if (fixture_fault == 3) return 0;
    if (size > 2) size = 2;
    assert(staged_size + size <= sizeof(staged));
    memcpy(staged + staged_size, data, size);
    staged_size += size;
    return size;
}
static int fixture_fsync(int descriptor)
{
    assert(descriptor == 14 && staged_exists && !staged_closed);
    ++fixture_syncs;
    staged_synced = fixture_fault != 5;
    return staged_synced ? 0 : -1;
}
static int fixture_close(int descriptor)
{
    assert(descriptor == 13 || descriptor == 14);
    if (descriptor == 13)
    {
        ++fixture_read_closes;
        return fixture_fault == 10 ? -1 : 0;
    }
    ++fixture_write_closes;
    staged_closed = true;
    return fixture_fault == 6 ? -1 : 0;
}
static int fixture_rename(const char *from, const char *to)
{
    assert(!strcmp(from, ROCKBOX_DIR "/empty-feedback.cfg.tmp"));
    assert(!strcmp(to, ROCKBOX_DIR "/empty-feedback.cfg"));
    assert(staged_exists && staged_synced && staged_closed);
    ++fixture_renames;
    if (fixture_fault == 7) return -1;
    memcpy(stored, staged, staged_size);
    stored_size = staged_size;
    stored_exists = true;
    staged_exists = false;
    return 0;
}
static int fixture_remove(const char *path)
{
    assert(!strcmp(path, ROCKBOX_DIR "/empty-feedback.cfg.tmp"));
    ++fixture_removes;
    staged_exists = false;
    return 0;
}
#define open fixture_open
#define read fixture_read
#define write fixture_write
#define fsync fixture_fsync
#define close fixture_close
#define rename fixture_rename
#define remove fixture_remove
'''

CASES = r'''
static void fixture_install(const void *data, size_t size)
{
    assert(size <= sizeof(stored));
    memcpy(stored, data, size);
    stored_size = size;
    stored_exists = true;
    empty_feedback_loaded = false;
    empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
}
static void fixture_mode(int mode)
{
    char data[] = ACCESSIBILITY_EMPTY_HEADER "0\n";
    data[sizeof(ACCESSIBILITY_EMPTY_HEADER) - 1] = '0' + mode;
    fixture_install(data, sizeof(data) - 1);
    assert((int)accessibility_empty_feedback_mode() == mode);
}
static void fixture_report(uintptr_t owner, int target, bool occupied, bool force, bool single_tap)
{
    feedback_pending = true;
    point_force = force;
    point_single_tap = single_tap;
    accessibility_explore_feedback((void *)owner, target, occupied);
    accessibility_speak_empty();
}
static void fixture_wave(unsigned int frequency, int strength)
{
    size_t frames = (48000 / 1000) * KEYCLICK_DURATION;
    assert(captured_size == frames * 2 * sizeof(int16_t));
    const int16_t *samples = (const int16_t *)(const void *)captured;
    uint32_t step = (uint64_t)frequency * (UINT64_C(1) << 32) / 48000;
    for (size_t index = 0; index < frames; ++index)
    {
        uint32_t phase = (uint32_t)index * step;
        int16_t expected = 2500 * strength * (phase > UINT32_C(0x7fffffff) ? -1 : 1);
        assert(samples[index * 2] == expected && samples[index * 2 + 1] == expected);
    }
}
int main(int argc, char **argv)
{
    assert(argc >= 2);
    const char *scenario = argv[1];
    sources = 7;
    empty_pitch = -4;
    global_settings.keyclick = 2;
    if (!strcmp(scenario, "defaults"))
    {
        assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_ONLY);
        assert(accessibility_empty_sound_enabled() && !accessibility_empty_speech_enabled());
        fixture_report(1, -1, false, true, false);
        fixture_wave(3175, 2);
        assert(!fixture_spoken && fixture_opens == 1 && !fixture_writes);
        for (int index = 0; index < 1000; ++index)
            assert(accessibility_empty_sound_enabled());
        assert(fixture_opens == 1);
    }
    else if (!strcmp(scenario, "valid"))
    {
        for (int mode = 0; mode <= 2; ++mode)
        {
            fixture_mode(mode);
            assert(accessibility_empty_sound_enabled() == (mode != 2));
            assert(accessibility_empty_speech_enabled() == (mode != 0));
        }
        assert(fixture_read_closes == 3 && fixture_reads > 3 && !fixture_writes);
    }
    else if (!strcmp(scenario, "corrupt"))
    {
        const char *invalid[] = { "", "garbage", ACCESSIBILITY_EMPTY_HEADER "3\n",
            ACCESSIBILITY_EMPTY_HEADER "-1\n", ACCESSIBILITY_EMPTY_HEADER "01\n",
            ACCESSIBILITY_EMPTY_HEADER "1", ACCESSIBILITY_EMPTY_HEADER "1\nx",
            ACCESSIBILITY_EMPTY_HEADER "1\r\n", ACCESSIBILITY_EMPTY_HEADER " 1\n",
            ACCESSIBILITY_EMPTY_HEADER "+1\n", "RBEMPTY-FEEDBACK:2\nmode:1\n",
            "RBEMPTY-FEEDBACK:1\nmode:99999999999999999999999999999999999999999\n" };
        for (size_t index = 0; index < ARRAYLEN(invalid); ++index)
        {
            fixture_install(invalid[index], strlen(invalid[index]));
            assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_ONLY);
        }
        const char nul_tail[] = ACCESSIBILITY_EMPTY_HEADER "1\n\0";
        fixture_install(nul_tail, sizeof(nul_tail) - 1);
        assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_ONLY);
        char nul_header[] = ACCESSIBILITY_EMPTY_HEADER "1\n";
        nul_header[4] = '\0';
        fixture_install(nul_header, sizeof(nul_header) - 1);
        assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_ONLY);
        assert(!fixture_writes && !fixture_removes && !fixture_renames);
    }
    else if (!strcmp(scenario, "menu"))
    {
        for (fixture_choice = 1; fixture_choice <= 2; ++fixture_choice)
        {
            assert(accessibility_empty_feedback_menu() == 0);
            assert(fixture_option_count == 3 && fixture_option_initial == fixture_choice - 1);
            assert((int)accessibility_empty_feedback_mode() == fixture_choice);
            assert(!memcmp(stored, ACCESSIBILITY_EMPTY_HEADER, sizeof(ACCESSIBILITY_EMPTY_HEADER) - 1));
            assert(stored_size == sizeof(ACCESSIBILITY_EMPTY_HEADER) + 1);
            assert(stored[sizeof(ACCESSIBILITY_EMPTY_HEADER) - 1] == '0' + fixture_choice);
            empty_feedback_loaded = false;
            empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
            assert((int)accessibility_empty_feedback_mode() == fixture_choice);
        }
        assert(fixture_syncs == 2 && fixture_write_closes == 2 && fixture_renames == 2);
        assert(fixture_writes > 2 && !fixture_errors && !staged_exists);
        fixture_choice = 2;
        int old_writes = fixture_writes;
        assert(accessibility_empty_feedback_menu() == 0 && fixture_writes == old_writes);
        fixture_usb = true;
        fixture_choice = 0;
        assert(accessibility_empty_feedback_menu() == MENU_ATTACHED_USB);
        assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SPEECH_ONLY);
        assert(fixture_writes == old_writes);
    }
    else if (!strcmp(scenario, "invalid-menu"))
    {
        fixture_mode(1);
        for (fixture_choice = -1; fixture_choice <= 3; fixture_choice += 4)
        {
            assert(accessibility_empty_feedback_menu() == 0);
            assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH);
        }
        assert(fixture_errors == 2 && !fixture_writes && !fixture_renames);
    }
    else if (!strcmp(scenario, "save-failure"))
    {
        assert(argc == 3);
        fixture_mode(1);
        unsigned char before[sizeof(stored)];
        memcpy(before, stored, sizeof(stored));
        size_t before_size = stored_size;
        fixture_fault = atoi(argv[2]);
        fixture_choice = 2;
        assert(accessibility_empty_feedback_menu() == 0 && fixture_errors == 1);
        assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH);
        assert(stored_size == before_size && !memcmp(before, stored, sizeof(stored)));
        assert(!staged_exists && fixture_removes == (fixture_fault != 1));
        fixture_fault = 0;
        empty_feedback_loaded = false;
        empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
        assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH);
    }
    else if (!strcmp(scenario, "read-failure"))
    {
        assert(argc == 3);
        fixture_mode(2);
        fixture_fault = atoi(argv[2]);
        empty_feedback_loaded = false;
        empty_feedback_mode = ACCESSIBILITY_EMPTY_SOUND_ONLY;
        assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_ONLY);
        int old_opens = fixture_opens;
        assert(accessibility_empty_sound_enabled() && !accessibility_empty_speech_enabled());
        assert(fixture_opens == old_opens && !fixture_writes);
        assert(fixture_read_closes == (fixture_fault == 8 ? 1 : 2));
    }
    else if (!strcmp(scenario, "matrix"))
    {
        for (int mode = 0; mode <= 2; ++mode)
            for (sources = 0; sources <= 7; ++sources)
                for (int strength = 0; strength <= 3; ++strength)
                    for (int occupied = 0; occupied <= 1; ++occupied)
                        for (int single_tap = 0; single_tap <= 1; ++single_tap)
                        {
                            fixture_mode(mode);
                            accessibility_cancel_touch();
                            captured_size = 0;
                            fixture_spoken = 0;
                            global_settings.keyclick = strength;
                            fixture_report(1, occupied ? 3 : -1, occupied, true, single_tap);
                            bool expect_sound = strength && (sources & (single_tap && occupied ? 6 : 4)) &&
                                (occupied || mode != ACCESSIBILITY_EMPTY_SPEECH_ONLY);
                            if (expect_sound) fixture_wave(occupied ? 4000 : 3175, strength);
                            else assert(!captured_size);
                            assert(fixture_spoken == (!occupied && mode != ACCESSIBILITY_EMPTY_SOUND_ONLY));
                            captured_size = 0;
                            int old_spoken = fixture_spoken;
                            for (int index = 0; index < 100; ++index)
                            {
                                fixture_report(1, occupied ? 3 : -1, occupied, false, single_tap);
                                accessibility_speak_empty();
                            }
                            assert(!captured_size && fixture_spoken == old_spoken);
                        }
    }
    else if (!strcmp(scenario, "stable"))
    {
        fixture_mode(1);
        fixture_report(1, -1, false, false, false);
        assert(fixture_spoken == 1);
        for (int index = 0; index < 1000; ++index)
            fixture_report(1, -1, false, false, false);
        assert(fixture_spoken == 1);
        fixture_report(1, 2, true, false, false);
        assert(fixture_spoken == 1);
        fixture_report(1, -1, false, false, false);
        assert(fixture_spoken == 2);
        fixture_report(2, -1, false, false, false);
        assert(fixture_spoken == 3);
        fixture_report(2, -2, false, false, false);
        assert(fixture_spoken == 4);
        fixture_report(2, -2, false, true, true);
        assert(fixture_spoken == 5);
        accessibility_cancel_touch();
        fixture_report(2, -2, false, false, false);
        assert(fixture_spoken == 6);
    }
    else if (!strcmp(scenario, "cancel"))
    {
        fixture_mode(1);
        feedback_pending = true;
        accessibility_explore_feedback((void *)(uintptr_t)1, -1, false);
        point_pending = exploring = have_context = true;
        accessibility_cancel_touch();
        assert(!point_pending && !exploring && !have_context);
        accessibility_speak_empty();
        assert(!fixture_spoken);
        fixture_accessible = false;
        fixture_report(1, -1, false, true, false);
        assert(!fixture_spoken);
        fixture_accessible = true;
        accessibility_speak_empty();
        assert(!fixture_spoken);
    }
    else assert(false);
    return 0;
}
'''


class EmptyFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            raise unittest.SkipTest("C compiler unavailable; compiled policy tests run under WSL")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.area = project_materials_root(ROOT) / "r1-empty-radio-20261017" / "empty-feedback" / stamp
        cls.area.mkdir(parents=True, exist_ok=False)
        paths = ("apps/accessibility.c", "apps/accessibility.h", "apps/misc.c", "apps/misc.h",
                 "apps/settings.h", "apps/beep.c", "firmware/asm/beep.c",
                 "tools/tests/test_keyclick_pcm.py", "tools/tests/test_accessibility_empty_feedback.py")
        cls.inputs = {path: (ROOT / path).read_bytes() for path in paths}
        sources = {path: content.decode("utf-8") for path, content in cls.inputs.items()}
        manager = sources["apps/accessibility.c"]
        enum_values = definition(sources["apps/accessibility.h"], "enum accessibility_empty_feedback\n") + ";\n"
        header = enum_values + "bool accessibility_empty_sound_enabled(void);\n"
        definitions = "\n".join(re.findall(r'^#define ACCESSIBILITY_EMPTY_[^\n]+', manager, re.M))
        definitions += "\n" + re.search(r'^static const int empty_feedback_labels\[\].*?^};',
                                         manager, re.M | re.S)[0]
        variables = "\n".join(re.findall(r'^static (?:bool (?:empty_[a-z_]+|feedback_[a-z_]+)|'
            r'const void \*feedback_owner|int feedback_target|'
            r'enum accessibility_empty_feedback empty_feedback_mode)[^\n]*', manager, re.M))
        production = "\n".join(definition(manager, signature) for signature in (
            "static void accessibility_empty_load(", "static bool accessibility_empty_save(",
            "enum accessibility_empty_feedback accessibility_empty_feedback_mode(",
            "bool accessibility_empty_sound_enabled(", "bool accessibility_empty_speech_enabled(",
            "int accessibility_empty_feedback_menu(", "void accessibility_cancel_touch(",
            "static void accessibility_feedback(", "void accessibility_explore_feedback(",
            "void accessibility_speak_empty("))
        base = PCM_PREAMBLE.replace("static bool accessibility_enabled(void) { return true; }",
            "static bool fixture_accessible = true;\nstatic bool accessibility_enabled(void) { return fixture_accessible; }")
        base = base.replace("static bool accessibility_empty_sound_enabled(void) { return empty_sound; }", "")
        base = base.replace("static bool empty_sound = true;", "")
        duration = re.search(r'^#define KEYCLICK_DURATION\s+(\d+)', sources["apps/settings.h"], re.M)[1]
        routing = sources["apps/misc.c"]
        begin = routing.index("static keyclick_callback keyclick_current_callback")
        end = routing.index("/* Return the ReplayGain mode", begin)
        harness = base + IO_FIXTURE + header + definitions + "\n" + variables + "\n"
        harness += definition(sources["apps/misc.h"], "enum system_sound") + ";\n"
        harness += definition(sources["apps/misc.h"], "enum keyclick_source") + ";\n"
        harness += f"#define KEYCLICK_DURATION {duration}\n"
        harness += without_includes(sources["firmware/asm/beep.c"])
        harness += without_includes(sources["apps/beep.c"])
        harness += definition(routing, "void system_sound_play(") + routing[begin:end]
        harness += production + CASES
        host = cls.area / "host.c"
        host.write_text(harness, encoding="utf-8")
        cls.executables = {}
        for name, flags in (("normal", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"])):
            executable = cls.area / (name + (".exe" if os.name == "nt" else ""))
            cls.compile(compiler, name, host, executable, flags)
            cls.executables[name] = executable
        stub_host = cls.area / "unsupported.c"
        stub_host.write_text("#include <stdbool.h>\n#define ACTION_NONE 0\n" +
            without_includes(sources["apps/accessibility.h"]) +
            without_includes(manager) + r'''
#include <assert.h>
int main(void)
{
    assert(accessibility_empty_feedback_mode() == ACCESSIBILITY_EMPTY_SOUND_ONLY);
    assert(!accessibility_empty_sound_enabled() && !accessibility_empty_speech_enabled());
    assert(accessibility_empty_feedback_menu() == 0);
    accessibility_speak_empty();
    return 0;
}
''', encoding="utf-8")
        for name, flags in (("unsupported", []), ("no-espeak", ["-DHAVE_TOUCHSCREEN"]),
                            ("no-touchscreen", ["-DHAVE_ESPEAK"])):
            executable = cls.area / (name + (".exe" if os.name == "nt" else ""))
            cls.compile(compiler, name, stub_host, executable, flags)
            cls.executables[name] = executable
        (cls.area / "provenance.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_sha256": {path: hashlib.sha256(content).hexdigest()
                for path, content in cls.inputs.items()},
            "harness_sha256": hashlib.sha256(harness.encode()).hexdigest(),
            "scope": "production atomic policy, stable-target feedback, keyclick routing and beep PCM; "
                "faultable private-file/UI/mixer fixture, no device/host audio or input",
        }, indent=2), encoding="utf-8")

    @classmethod
    def compile(cls, compiler, name, host, executable, flags):
        command = compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", *flags,
                              str(host), "-o", str(executable)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=60)
        (cls.area / (name + "-build.json")).write_text(json.dumps({
            "command": command, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }, indent=2), encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stderr)
        imports = subprocess.run(["nm", "-u", str(executable)], text=True, capture_output=True, timeout=30)
        (cls.area / (name + "-imports.log")).write_text(imports.stdout + imports.stderr, encoding="utf-8")
        if imports.returncode:
            raise AssertionError(imports.stderr)
        symbols = {line.split()[-1].split("@")[0] for line in imports.stdout.splitlines() if line.split()}
        forbidden = {"open", "open64", "read", "write", "close", "fsync", "rename", "remove",
                     "system", "execve", "fork", "socket", "ioctl", "reboot", "kill"}
        if symbols & forbidden:
            raise AssertionError("Unmocked core operations: " + repr(symbols & forbidden))

    def scenario(self, name, *arguments):
        for configuration in ("normal", "ubsan"):
            with self.subTest(configuration=configuration, scenario=name, arguments=arguments):
                command = [str(self.executables[configuration]), name, *map(str, arguments)]
                result = subprocess.run(command, text=True, capture_output=True, timeout=15)
                with (self.area / "runs.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(dict(command=command, returncode=result.returncode,
                                                 stdout=result.stdout, stderr=result.stderr)) + "\n")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sound_only_is_default_and_reads_are_cached(self):
        self.scenario("defaults")

    def test_exact_three_modes_load_with_partial_reads(self):
        self.scenario("valid")

    def test_invalid_truncated_oversized_and_binary_input_cannot_enable_speech(self):
        self.scenario("corrupt")

    def test_menu_order_atomic_persistence_reload_unchanged_and_usb(self):
        self.scenario("menu")

    def test_invalid_menu_selection_is_rejected_without_io(self):
        self.scenario("invalid-menu")

    def test_each_atomic_save_failure_retains_previous_disk_and_active_value(self):
        for fault in range(1, 8):
            with self.subTest(fault=fault):
                self.scenario("save-failure", fault)

    def test_open_read_partial_read_and_close_failures_keep_safe_default(self):
        for fault in range(8, 12):
            with self.subTest(fault=fault):
                self.scenario("read-failure", fault)

    def test_all_modes_masks_strengths_occupied_and_single_tap_actual_pcm(self):
        self.scenario("matrix")

    def test_target_owner_occupancy_contact_transitions_and_no_jitter_chatter(self):
        self.scenario("stable")

    def test_cancel_and_disabled_exploration_do_not_leak_pending_speech(self):
        self.scenario("cancel")

    def test_unsupported_espeak_and_touchscreen_stubs_are_inert(self):
        for configuration in ("unsupported", "no-espeak", "no-touchscreen"):
            with self.subTest(configuration=configuration):
                result = subprocess.run([str(self.executables[configuration])],
                                        text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        changed = [path for path, content in cls.inputs.items() if (ROOT / path).read_bytes() != content]
        if changed:
            raise AssertionError("Empty-feedback sources changed during bounded tests: " + ", ".join(changed))


@unittest.skipIf(sys.platform == "win32", "POSIX full-manager integration runs under WSL")
class EmptyFeedbackMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = {}
        original_root = settings_fixture.project_materials_root
        original_sanitize = os.environ.get("ACCESSIBILITY_SETTINGS_SANITIZE")
        area = project_materials_root(ROOT) / "r1-empty-radio-20261017" / "empty-feedback" / "menu-integration"
        try:
            settings_fixture.project_materials_root = lambda *args, **kwargs: area
            for name in ("normal", "ubsan"):
                fixture = type("EmptyMenu" + name.title(), (), {})
                if name == "ubsan":
                    os.environ["ACCESSIBILITY_SETTINGS_SANITIZE"] = "1"
                else:
                    os.environ.pop("ACCESSIBILITY_SETTINGS_SANITIZE", None)
                settings_fixture.AccessibilitySettingsTests.setUpClass.__func__(fixture)
                fixture.library.probe_empty_disk_content.restype = ctypes.c_char_p
                cls.fixtures[name] = fixture
        finally:
            settings_fixture.project_materials_root = original_root
            if original_sanitize is None:
                os.environ.pop("ACCESSIBILITY_SETTINGS_SANITIZE", None)
            else:
                os.environ["ACCESSIBILITY_SETTINGS_SANITIZE"] = original_sanitize

    def test_actual_exploration_menu_row_opens_three_choice_picker_and_announces_mode(self):
        for name, fixture in self.fixtures.items():
            with self.subTest(configuration=name):
                library = fixture.library
                library.input_reset()
                script = (ctypes.c_int * 2)(4, -1)
                library.probe_script(script, len(script), 0)
                self.assertEqual(library.accessibility_touch_menu(), 0)
                self.assertEqual(library.probe_option_count(), 3)
                self.assertEqual(library.probe_option_initial_choice(), 0)
                expected = [fixture.constants[label] for label in (
                    "LANG_ACCESSIBILITY_EMPTY_SOUND_ONLY", "LANG_ACCESSIBILITY_EMPTY_SOUND_AND_SPEECH",
                    "LANG_ACCESSIBILITY_EMPTY_SPEECH_ONLY")]
                self.assertEqual([library.probe_option_voice(index) for index in range(3)], expected)
                spoken = [library.probe_spoken(index) for index in range(library.probe_stat(6))]
                label = fixture.constants["LANG_ACCESSIBILITY_EMPTY_FEEDBACK"]
                self.assertIn((label, expected[0]), list(zip(spoken, spoken[1:])))
                self.assertEqual(library.probe_stat(2), 0)

    def test_reset_is_last_row_and_preserves_mapping_migration(self):
        for name, fixture in self.fixtures.items():
            with self.subTest(configuration=name):
                library = fixture.library
                library.input_reset()
                library.probe_assign(1, 8)
                script = (ctypes.c_int * 2)(7, -1)
                library.probe_script(script, len(script), 0)
                self.assertEqual(library.accessibility_touch_menu(), 0)
                self.assertEqual(library.probe_mapping(1), 1)
                self.assertTrue(library.probe_disk_content().startswith(b"RBACCESSIBILITY:11\n"))
                self.assertEqual(library.accessibility_empty_feedback_mode(), 0)

    def test_picker_usb_return_reaches_actual_exploration_menu_without_saving(self):
        for name, fixture in self.fixtures.items():
            with self.subTest(configuration=name):
                library = fixture.library
                library.input_reset()
                script = (ctypes.c_int * 2)(4, -1)
                library.probe_script(script, len(script), -313)
                self.assertEqual(library.accessibility_touch_menu(), 313)
                self.assertEqual(library.probe_stat(2), 0)

    def prepare_reset(self, fixture):
        library = fixture.library
        library.input_reset()
        library.probe_assign(1, 8)
        library.probe_click_sources(2)
        library.probe_button_assign(4, 0, 0)
        script = (ctypes.c_int * 2)(4, -1)
        library.probe_script(script, len(script), 2)
        self.assertEqual(library.accessibility_touch_menu(), 0)
        self.assertEqual(library.accessibility_empty_feedback_mode(), 2)
        self.assertEqual(library.probe_empty_disk_content(), b"RBEMPTY-FEEDBACK:1\nmode:2\n")
        return library

    def reset_menu(self, library):
        script = (ctypes.c_int * 2)(7, -1)
        library.probe_script(script, len(script), 0)
        return library.accessibility_touch_menu()

    def test_confirmed_reset_restores_empty_sound_only_and_preserves_physical_and_source_scope(self):
        for name, fixture in self.fixtures.items():
            with self.subTest(configuration=name):
                library = self.prepare_reset(fixture)
                self.assertEqual(self.reset_menu(library), 0)
                self.assertEqual(library.probe_mapping(1), 1)
                self.assertEqual(library.probe_button_mapping(4, 0), 0)
                self.assertEqual(library.accessibility_keyclick_sources(), 2)
                self.assertEqual(library.accessibility_empty_feedback_mode(), 0)
                self.assertEqual(library.probe_empty_disk_content(), b"RBEMPTY-FEEDBACK:1\nmode:0\n")
                library.probe_empty_reload()
                self.assertEqual(library.accessibility_empty_feedback_mode(), 0)
                self.assertEqual(library.probe_stat(3), 3)

    def test_reset_reports_partial_commit_and_keeps_prior_empty_mode_on_each_second_file_failure(self):
        for name, fixture in self.fixtures.items():
            for fault in range(1, 8):
                with self.subTest(configuration=name, fault=fault):
                    library = self.prepare_reset(fixture)
                    library.probe_chunks(0, 2)
                    library.probe_empty_fault(fault)
                    self.assertEqual(self.reset_menu(library), 0)
                    self.assertEqual(library.probe_stat(7), fixture.constants["LANG_ACCESSIBILITY_RESET_PARTIAL"])
                    self.assertEqual(library.probe_mapping(1), 1)
                    self.assertEqual(library.probe_button_mapping(4, 0), 0)
                    self.assertEqual(library.accessibility_keyclick_sources(), 2)
                    self.assertEqual(library.accessibility_empty_feedback_mode(), 2)
                    self.assertEqual(library.probe_empty_disk_content(), b"RBEMPTY-FEEDBACK:1\nmode:2\n")
                    library.probe_empty_fault(0)
                    library.probe_reload()
                    library.probe_empty_reload()
                    self.assertEqual(library.probe_mapping(1), 1)
                    self.assertEqual(library.accessibility_empty_feedback_mode(), 2)

    def test_reset_cancel_usb_timeout_expiry_and_first_file_failure_do_not_reset_empty_mode(self):
        for name, fixture in self.fixtures.items():
            for failure in ("cancel", "usb", "timeout", "expiry", "write"):
                with self.subTest(configuration=name, failure=failure):
                    library = self.prepare_reset(fixture)
                    if failure in ("cancel", "usb", "timeout"):
                        library.probe_confirmation({"cancel": 1, "usb": 2, "timeout": 3}[failure])
                    elif failure == "expiry":
                        library.probe_confirmation_elapsed(2001)
                    else:
                        library.probe_fault(5)
                    self.assertEqual(self.reset_menu(library), 313 if failure == "usb" else 0)
                    self.assertEqual(library.probe_mapping(1), 8)
                    self.assertEqual(library.accessibility_empty_feedback_mode(), 2)
                    self.assertEqual(library.probe_empty_disk_content(), b"RBEMPTY-FEEDBACK:1\nmode:2\n")

    def test_reset_with_only_empty_mode_changed_still_requires_confirmation(self):
        for name, fixture in self.fixtures.items():
            with self.subTest(configuration=name):
                library = fixture.library
                library.input_reset()
                script = (ctypes.c_int * 2)(4, -1)
                library.probe_script(script, len(script), 2)
                self.assertEqual(library.accessibility_touch_menu(), 0)
                library.probe_confirmation(1)
                self.assertEqual(self.reset_menu(library), 0)
                self.assertEqual(library.probe_mapping(1), 1)
                self.assertEqual(library.accessibility_empty_feedback_mode(), 2)
                library.probe_confirmation(0)
                self.assertEqual(self.reset_menu(library), 0)
                self.assertEqual(library.probe_mapping(1), 1)
                self.assertEqual(library.accessibility_empty_feedback_mode(), 0)
                self.assertEqual(library.probe_empty_disk_content(), b"RBEMPTY-FEEDBACK:1\nmode:0\n")

    @classmethod
    def tearDownClass(cls):
        for fixture in cls.fixtures.values():
            settings_fixture.AccessibilitySettingsTests.tearDownClass.__func__(fixture)


if __name__ == "__main__":
    unittest.main(verbosity=2)
