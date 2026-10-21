"""Exercise the production touch sensitivity policy and atomic persistence."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <fcntl.h>
#define HAVE_TOUCHSCREEN
#define HAVE_ESPEAK
#define ROCKBOX_DIR "/.rockbox"
#define HZ 100
#define UNIT_PERCENT 1
#define MENU_ATTACHED_USB 313
#define LANG_TOUCH_GESTURE_SENSITIVITY 1
#define LANG_ERROR_WRITING_CONFIG 2
#define ID2P(value) (value)
static char input[256], staged[256], committed[256];
static size_t read_offset, write_offset;
static int fault, choice = 100, errors, resets, reads, writes, removed;
static bool usb;
static const char *str(int identifier) { (void)identifier; return "label"; }
static void splash(int ticks, int label) { (void)ticks; (void)label; ++errors; }
static void accessibility_init(void) { ++resets; }
static bool set_int(const unsigned char *label, const char *unit, int kind,
                    int *value, void *callback, int step, int minimum, int maximum,
                    void *formatter)
{
    (void)label; (void)callback; (void)formatter;
    assert(!strcmp(unit, "%") && kind == UNIT_PERCENT);
    assert(step == 25 && minimum == 50 && maximum == 200);
    *value = choice;
    return usb;
}
static int fixture_open(const char *path, int flags, ...)
{
    assert(strstr(path, "/.rockbox/touch-sensitivity.cfg") == path);
    if (flags & O_WRONLY)
    {
        if (fault == 1) return -1;
        write_offset = 0;
        memset(staged, 0, sizeof(staged));
        return 11;
    }
    read_offset = 0;
    ++reads;
    return input[0] ? 10 : -1;
}
static ssize_t fixture_read(int descriptor, void *data, size_t size)
{
    assert(descriptor == 10);
    if (fault == 6) return -1;
    size_t available = strlen(input) - read_offset;
    if (size > available) size = available;
    if (size > 2) size = 2;
    memcpy(data, input + read_offset, size);
    read_offset += size;
    return size;
}
static ssize_t fixture_write(int descriptor, const void *data, size_t size)
{
    assert(descriptor == 11);
    ++writes;
    if (fault == 2) return 0;
    if (size > 2) size = 2;
    assert(write_offset + size < sizeof(staged));
    memcpy(staged + write_offset, data, size);
    write_offset += size;
    return size;
}
static int fixture_fsync(int descriptor) { assert(descriptor == 11); return fault == 3 ? -1 : 0; }
static int fixture_close(int descriptor)
{ return fault == 4 || (fault == 7 && descriptor == 10) ? -1 : 0; }
static int fixture_remove(const char *path) { (void)path; ++removed; return 0; }
static int fixture_rename(const char *from, const char *to)
{
    assert(strstr(from, ".tmp") && !strstr(to, ".tmp"));
    if (fault == 5) return -1;
    strcpy(committed, staged);
    return 0;
}
#define open fixture_open
#define read fixture_read
#define write fixture_write
#define fsync fixture_fsync
#define close fixture_close
#define remove fixture_remove
#define rename fixture_rename
'''
SUFFIX = r'''
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    if (!strcmp(scenario, "defaults"))
    {
        assert(accessibility_touch_distance(8) == 8);
        assert(accessibility_touch_distance(24) == 24);
        assert(reads == 1);
    }
    else if (!strcmp(scenario, "persisted"))
    {
        strcpy(input, TOUCH_SETTINGS_HEADER "200\n");
        assert(accessibility_touch_distance(8) == 4);
        assert(accessibility_touch_distance(25) == 13);
        assert(accessibility_touch_distance(0) == 1);
        assert(accessibility_touch_distance(1) == 1);
        assert(reads == 1);
    }
    else if (!strcmp(scenario, "corrupt"))
    {
        const char *invalid[] = { "", "garbage", TOUCH_SETTINGS_HEADER "0\n",
            TOUCH_SETTINGS_HEADER "201\n", TOUCH_SETTINGS_HEADER "75\nx",
            TOUCH_SETTINGS_HEADER "100", TOUCH_SETTINGS_HEADER "+75\n",
            TOUCH_SETTINGS_HEADER "999999999999999999999999999999999999\n" };
        for (size_t index = 0; index < sizeof(invalid) / sizeof(invalid[0]); ++index)
        {
            sensitivity_loaded = false;
            sensitivity = 100;
            strcpy(input, invalid[index]);
            assert(accessibility_touch_distance(24) == 24);
        }
    }
    else if (!strcmp(scenario, "saturation"))
    {
        strcpy(input, TOUCH_SETTINGS_HEADER "50\n");
        assert(accessibility_touch_distance(8) == 16);
        assert(accessibility_touch_distance(UINT_MAX) == UINT_MAX);
        assert(accessibility_touch_distance(UINT_MAX / 2) == UINT_MAX - 1);
    }
    else if (!strcmp(scenario, "menu"))
    {
        choice = 175;
        assert(accessibility_touch_sensitivity_menu() == 0);
        assert(!strcmp(committed, TOUCH_SETTINGS_HEADER "175\n"));
        assert(sensitivity == 175 && resets == 1 && !errors && writes > 1);
        assert(accessibility_touch_distance(28) == 16);
        assert(accessibility_touch_sensitivity_menu() == 0 && resets == 1);
        usb = true;
        choice = 50;
        assert(accessibility_touch_sensitivity_menu() == MENU_ATTACHED_USB);
        assert(sensitivity == 175 && resets == 1);
    }
    else if (!strcmp(scenario, "failures"))
    {
        for (fault = 1; fault <= 5; ++fault)
        {
            choice = 200;
            assert(accessibility_touch_sensitivity_menu() == 0);
            assert(sensitivity == 100 && resets == 0 && !committed[0]);
        }
        assert(errors == 5 && removed == 4);
        fault = 0;
        choice = 49;
        assert(accessibility_touch_sensitivity_menu() == 0 && sensitivity == 100);
        choice = 101;
        assert(accessibility_touch_sensitivity_menu() == 0 && sensitivity == 100);
    }
    else if (!strcmp(scenario, "read-failure"))
    {
        strcpy(input, TOUCH_SETTINGS_HEADER "200\n");
        for (fault = 6; fault <= 7; ++fault)
        {
            sensitivity_loaded = false;
            assert(accessibility_touch_distance(8) == 8);
        }
    }
    else assert(false);
    return 0;
}
'''


@unittest.skipIf(sys.platform == "win32", "POSIX behavioral host is exercised under WSL")
class TouchSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = project_materials_root(ROOT, "Workspace") / "touch-sensitivity-tests" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.area.mkdir(parents=True)
        source_path = ROOT / "apps/accessibility_touch.c"
        source = re.sub(r'^#include[^\n]*\n', '\n', source_path.read_text(encoding="utf-8"), flags=re.M)
        harness = cls.area / "host.c"
        harness.write_text(PREAMBLE + source + SUFFIX, encoding="utf-8")
        cls.executable = cls.area / "host"
        command = shlex.split(os.environ.get("CC", "cc")) + ["-std=c99", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all", str(harness), "-o", str(cls.executable)]
        result = subprocess.run(command, text=True, capture_output=True)
        (cls.area / "build.json").write_text(json.dumps(dict(command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr, source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest()), indent=2), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stderr)

    def real_header_probe(self, target):
        central = project_materials_root(ROOT, "Workspace")
        build = central / ("build-espeak-windows-hibyr1" if target == "windows" else "build-espeak-hibyr1")
        makefile = build / "Makefile"
        if not all(path.is_file() for path in (makefile, build / "autoconf.h", build / "lang_enum.h", build / "rbversion.h")):
            self.skipTest("Generate the actual R1 target headers before running this integration gate")
        configuration = makefile.read_text(encoding="utf-8")

        def exported(name):
            matched = re.search(r"^export " + re.escape(name) + r"=(.*)$", configuration, re.MULTILINE)
            self.assertIsNotNone(matched, "Configured variable missing: " + name)
            return matched[1].strip()

        self.assertEqual(exported("MODELNAME"), "hibyr1")
        self.assertEqual(exported("TARGET_ID"), "124")
        compiler = shutil.which(exported("CC"))
        self.assertIsNotNone(compiler, "Actual configured compiler is unavailable")
        directories = [build, build / "lang"] + [ROOT / relative for relative in (
            "firmware", "firmware/export", "firmware/drivers", "firmware/include", "firmware/kernel/include",
            "apps", "apps/gui", "apps/recorder", "apps/radio", "lib/rbcodec", "lib/rbcodec/dsp",
            "lib/rbcodec/metadata", "lib/rbcodec/codecs", "lib/skin_parser", "lib/fixedpoint",
            "uisimulator/common", "firmware/target/hosted/hiby/r1", "firmware/target/hosted/hiby",
            "firmware/target/hosted", "firmware/target/hosted/sdl")]
        arguments = [compiler] + ["-I" + str(path) for path in directories]
        arguments += ["-DROCKBOX", "-DHIBY_R1", "-DMEMORYSIZE=" + exported("MEMORYSIZE"),
                      "-DTARGET_ID=124", '-DTARGET_NAME="hibyr1"']
        if target == "windows":
            arguments += ["-DSIMULATOR"]
        arguments += shlex.split(exported("EXTRA_DEFINES"))
        arguments += shlex.split(exported("GCCOPTS").replace("$(SIMDIR)", str(ROOT / "uisimulator/sdl")))
        arguments += ["-Werror", "-Werror=implicit-function-declaration"]
        destination = self.area / (target + "-real-headers")
        destination.mkdir()
        source_path = ROOT / "apps/accessibility_touch.c"
        inputs = [source_path, ROOT / "apps/talk.h", makefile, build / "autoconf.h",
                  build / "lang_enum.h", build / "rbversion.h"]
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        report = dict(passed=False, inputs_before=before, commands=[], physical_hardware_tested=False)

        def run(command, name):
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
            (destination / name).write_text(result.stdout + result.stderr, encoding="utf-8")
            report["commands"].append(dict(command=command, exit=result.returncode, log=name))
            return result

        try:
            dependency = destination / "positive.d"
            positive = run(arguments + ["-MMD", "-MF", str(dependency), "-c", str(source_path),
                                        "-o", str(destination / "positive.o")], "positive.log")
            self.assertEqual(positive.returncode, 0, positive.stdout + positive.stderr)
            self.assertIn(str(ROOT / "apps/talk.h"), dependency.read_text(encoding="utf-8"))
            mutated, replacements = re.subn(r'^\s*#\s*include\s+"talk.h"[^\n]*\n?', "",
                source_path.read_text(encoding="utf-8"), flags=re.MULTILINE)
            self.assertEqual(replacements, 1, "Negative control must remove exactly the real provider")
            negative_path = destination / "without_talk.c"
            negative_path.write_text(mutated, encoding="utf-8")
            negative = run(arguments + ["-iquote", str(ROOT / "apps"), "-c", str(negative_path),
                                        "-o", str(destination / "negative.o")], "negative.log")
            self.assertNotEqual(negative.returncode, 0, "Missing percent-unit provider unexpectedly compiled")
            self.assertIn("UNIT_PERCENT", negative.stderr)
            report["passed"] = True
        finally:
            report["inputs_after"] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
            report["sources_stable"] = before == report["inputs_after"]
            report["passed"] = report["passed"] and report["sources_stable"]
            (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        self.assertTrue(report["sources_stable"])

    def test_windows_real_headers_supply_percent_unit(self):
        self.real_header_probe("windows")

    def test_native_real_headers_supply_percent_unit(self):
        self.real_header_probe("native")

    def test_all_persistence_and_distance_cases(self):
        for scenario in ("defaults", "persisted", "corrupt", "saturation", "menu", "failures", "read-failure"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.executable), scenario], capture_output=True, text=True)
                (self.area / (scenario + ".json")).write_text(json.dumps(dict(exit=result.returncode, stdout=result.stdout, stderr=result.stderr)), encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_without_touchscreen_or_espeak_has_no_dependencies(self):
        source = re.sub(r'^#include[^\n]*\n', '\n', (ROOT / "apps/accessibility_touch.c").read_text(encoding="utf-8"), flags=re.M)
        harness = self.area / "unsupported.c"
        harness.write_text(source + '\nint main(void) { return accessibility_touch_distance(24) != 24 || accessibility_touch_sensitivity_menu(); }\n', encoding="utf-8")
        executable = self.area / "unsupported"
        command = shlex.split(os.environ.get("CC", "cc")) + ["-std=c99", "-Wall", "-Wextra", "-Werror", str(harness), "-o", str(executable)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(subprocess.run([str(executable)]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
