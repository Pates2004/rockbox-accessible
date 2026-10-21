import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import unittest

from test_tts_coverage import extract_block
from test_tts_plugin_policy import with_menu_policy


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
PREFIX = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define MAX_DICES 12
#define PRINT_BUFFER_LENGTH (MAX_DICES * 4 + 1)
#define LANG_DICE_RESULTS 1
#define LANG_DICE_TOTAL 2
struct dices { int values[12]; int total; int nb_dices; int nb_sides; };
struct user_settings { bool talk_menu, tts_enabled; };
static struct user_settings settings;
static int speech[32], calls;
static bool queued[32];
static int speak_id(int identifier, bool enqueue)
{
    assert(calls < 32);
    speech[calls] = -identifier;
    queued[calls++] = enqueue;
    return 0;
}
static int speak_number(long value, bool enqueue)
{
    assert(calls < 32);
    speech[calls] = value;
    queued[calls++] = enqueue;
    return 0;
}
static struct {
    __typeof__(settings) *global_settings;
    int (*talk_id)(int, bool);
    int (*talk_number)(long, bool);
    int (*snprintf)(char *, size_t, const char *, ...);
} api = { &settings, speak_id, speak_number, snprintf };
static __typeof__(api) *rb = &api;
"""
SUFFIX = r"""
int main(void)
{
    struct dices results = { .total = 1200, .nb_dices = 12, .nb_sides = 100 };
    for (int index = 0; index < 12; index++)
        results.values[index] = 100;
    settings.talk_menu = true;
    dice_speak(&results);
    assert(calls == 15 && speech[0] == -LANG_DICE_RESULTS && !queued[0]);
    for (int index = 1; index <= 12; index++)
        assert(speech[index] == 100 && queued[index]);
    assert(speech[13] == -LANG_DICE_TOTAL && speech[14] == 1200 && queued[14]);
    settings.talk_menu = false;
    dice_speak(&results);
    assert(calls == 15);
    struct { char text[PRINT_BUFFER_LENGTH]; unsigned char guard[8]; } output;
    memset(&output, 0x5a, sizeof(output));
    dice_print_string_buffer(&results, output.text, 0, 12);
    assert(strlen(output.text) == 48);
    for (size_t index = 0; index < sizeof(output.guard); index++)
        assert(output.guard[index] == 0x5a);
    dice_print_string_buffer(&results, output.text, 0, 0);
    assert(output.text[0] == '\0');
    dice_print_string_buffer(&results, output.text, 5, 7);
    assert(strcmp(output.text, " 100 100") == 0);
    puts("dice speech, disabled policy, maximum formatting and guards: PASS");
    return 0;
}
"""


class DiceSpeechTests(unittest.TestCase):
    def test_real_speech_and_bounded_formatting(self):
        source = (ROOT / "apps/plugins/dice.c").read_text(encoding="utf-8")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        results = _project_materials_root(ROOT) / "tts-plugin-dice-tests" / stamp
        results.mkdir(parents=True)
        harness = results / "dice.c"
        harness.write_text(with_menu_policy(PREFIX) + extract_block(source, "static void dice_speak(const struct dices *results)\n{") +
                           extract_block(source, "static void dice_print_string_buffer(") + SUFFIX,
                           encoding="utf-8")
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu99", "-O1", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
            "-fno-sanitize-recover=all", str(harness), "-o", str(results / "dice-test")]
        subprocess.run(command, check=True)
        completed = subprocess.run([str(results / "dice-test")], capture_output=True, text=True)
        (results / "report.json").write_text(json.dumps(dict(command=command,
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr), indent=2),
            encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_speech_is_roll_driven_and_configuration_bounded(self):
        source = (ROOT / "apps/plugins/dice.c").read_text(encoding="utf-8")
        entry = extract_block(source, "enum plugin_status plugin_start(")
        self.assertEqual(entry.count("dice_speak(&dice)"), 2)
        rendering = extract_block(source, "static void dice_print(struct dices* dice, struct screen* display){")
        self.assertNotIn("talk_", rendering)
        self.assertNotIn("dice_speak", rendering)
        self.assertIn("sides_index >= (int)ARRAYLEN(nb_sides_values)", entry)
        self.assertIn("dice.nb_dices > MAX_DICES", entry)
        self.assertIn("return PLUGIN_USB_CONNECTED", entry)
        self.assertIn("int selection = 0;", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
