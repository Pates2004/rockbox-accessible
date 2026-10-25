"""Run the real CFG loader's private touch-setting bridge with faultable I/O."""
import ctypes as c
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root
from test_keyclick_pcm import definition
import build_espeak_clipplus as builder

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ("apps/settings.c", "apps/misc.c", "docs/profiles/Accessible-Polish.cfg",
          "tools/build_espeak_clipplus.py", "tools/tests/test_release_profiles.py")
HOST = r'''
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#define HAVE_TOUCHSCREEN
#define HAVE_ESPEAK
#define O_RDONLY 0
#define OPEN_PLUGIN_CFGNAME "open_plugin"
#define logf(...) ((void)0)
static FILE *input;
static int touch_calls, touch_state, fault, saves, applies, forwarded, closed;
static int open_utf8(const char *path, int flags)
{ (void)flags; input = fopen(path, "rb"); return input ? 3 : -1; }
static int close(int fd) { (void)fd; ++closed; return fclose(input); }
static int read(int fd, void *data, size_t size)
{ (void)fd; return (int)fread(data, 1, size, input); }
static int read_line(int fd, char *line, size_t size)
{
    (void)fd;
    if (!fgets(line, (int)size, input)) return 0;
    return (int)strlen(line);
}
static char *skip_whitespace(char *text)
{ while (*text && isspace((unsigned char)*text)) ++text; return text; }
static bool string_to_cfg(const char *name, char *value, bool *theme)
{ (void)name; (void)value; (void)theme; ++forwarded; return true; }
static bool accessibility_set_enabled(bool enabled)
{ ++touch_calls; if (fault) return false; touch_state = enabled; return true; }
static void open_plugin_import(const char *path) { (void)path; }
static int settings_save(void) { ++saves; return 0; }
static void settings_apply(bool read_disk) { (void)read_disk; ++applies; }
static void settings_apply_skins(void) {}
'''
TAIL = r'''
void profile_probe_reset(int failure)
{ touch_calls = touch_state = saves = applies = forwarded = closed = 0; fault = failure; }
int profile_probe_get(unsigned int field)
{
    int values[] = {touch_calls, touch_state, saves, applies, forwarded, closed};
    return field < 6 ? values[field] : -1;
}
'''


class ReleaseProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = project_materials_root(ROOT) / "release-profile-tests" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.area.mkdir(parents=True, exist_ok=False)
        cls.inputs = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
        source = HOST + definition((ROOT / "apps/misc.c").read_text(encoding="utf-8"),
                                   "bool settings_parseline(char* line, char** name, char** value)")
        source += definition((ROOT / "apps/settings.c").read_text(encoding="utf-8"),
                              "bool settings_load_config(const char* file, bool apply)") + TAIL
        harness = cls.area / "loader.c"
        harness.write_text(source, encoding="utf-8")
        binary = cls.area / ("loader.dll" if os.name == "nt" else "loader.so")
        cls.command = shlex.split(os.environ.get("CC", "cc")) + ["-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-O1", "-shared"] + ([] if os.name == "nt" else ["-fPIC"]) + [str(harness), "-o", str(binary)]
        completed = subprocess.run(cls.command, capture_output=True, text=True)
        (cls.area / "compile.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        cls.exit = completed.returncode
        if cls.exit:
            raise AssertionError(completed.stderr)
        cls.lib = c.CDLL(str(binary))
        cls.lib.settings_load_config.argtypes = [c.c_char_p, c.c_bool]
        cls.lib.settings_load_config.restype = c.c_bool
        cls.addClassCleanup(cls.report)
        print("Release-profile evidence:", cls.area, flush=True)

    @classmethod
    def report(cls):
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}
        (cls.area / "provenance.json").write_text(json.dumps(dict(inputs_before=cls.inputs,
            inputs_after=after, source_stable=after == cls.inputs, command=cls.command, compiler_exit=cls.exit,
            scope="Actual CFG loader/parser; private setter and standard setting engine are hosts, real setters/GUI tested separately"), indent=2) + "\n", encoding="utf-8")

    def setUp(self):
        self.lib.profile_probe_reset(0)

    def load(self, content, apply=True):
        path = self.area / "fixture.cfg"
        path.write_text(content, encoding="utf-8")
        return self.lib.settings_load_config(os.fsencode(path), apply)

    def values(self):
        return [self.lib.profile_probe_get(n) for n in range(6)]

    def test_ordinary_config_does_not_override_private_touch_preference(self):
        self.assertTrue(self.load("tts enabled: off\nlang: /.rockbox/langs/english.lng\n"))
        self.assertEqual(self.values(), [0, 0, 1, 1, 2, 1])

    def test_optional_profile_reaches_private_setter_once_after_parse(self):
        content = (ROOT / "docs/profiles/Accessible-Polish.cfg").read_text(encoding="utf-8")
        self.assertTrue(self.load(content))
        self.assertEqual(self.values()[:4], [1, 1, 1, 1])
        self.assertEqual(self.values()[5], 1)

    def test_touch_values_and_last_valid_duplicate(self):
        for value, expected in (("on", 1), ("off", 0), ("ON", 1)):
            self.lib.profile_probe_reset(0)
            self.assertTrue(self.load("accessibility touch enabled: " + value + "\n"))
            self.assertEqual(self.values(), [1, expected, 1, 1, 0, 1])
        self.assertTrue(self.load("accessibility touch enabled: on\naccessibility touch enabled: off\n"))
        self.assertEqual(self.values()[1], 0)

    def test_invalid_value_and_private_save_failure_close_input_and_do_not_apply(self):
        for value in ("true", "", "2", "on then off"):
            self.lib.profile_probe_reset(0)
            self.assertFalse(self.load("accessibility touch enabled: " + value + "\n"))
            self.assertEqual(self.values(), [0, 0, 0, 0, 0, 1])
        self.lib.profile_probe_reset(1)
        self.assertFalse(self.load("accessibility touch enabled: on\n"))
        self.assertEqual(self.values(), [1, 0, 0, 0, 0, 1])

    def test_apply_false_keeps_existing_loader_semantics(self):
        self.assertTrue(self.load("accessibility touch enabled: on\n", apply=False))
        self.assertEqual(self.values(), [1, 1, 0, 0, 0, 1])

    def test_declared_new_and_legacy_packaged_profiles_are_distinct(self):
        current = builder.manifest_default_config({"default_profile": "standard-en"})
        legacy = builder.manifest_default_config({})
        self.assertIn(b"langs/english.lng\n", current)
        self.assertIn(b"tts enabled: off\n", current)
        self.assertIn(b"accessibility shortcut enabled: on\n", current)
        self.assertNotIn(b"accessibility touch enabled:", current)
        self.assertIn(b"langs/polski.lng\n", legacy)
        self.assertIn(b"tts enabled: on\n", legacy)
        self.assertIn(b"volume: -250\n", builder.manifest_default_config({"default_profile": "standard-en"}, True))
        with self.assertRaises(RuntimeError):
            builder.manifest_default_config({"default_profile": "unknown"})


if __name__ == "__main__":
    unittest.main()
