"""Exercise actual curtain recovery before core filters and through plugin APIs."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest

from test_accessibility_integration import INPUTS, ROOT, action_harness, balanced_definition
from project_materials import project_materials_root


CASES = r'''
static void reset_curtain(void)
{
    reset_action(true);
    actual_curtain = true;
    curtain_release_mask = 0;
    curtain_wait_for_press = false;
    physical_action = ACTION_STD_NEXT;
}

static int core_cases(void)
{
    const int chord = BUTTON_POWER | BUTTON_NEXT;
    for (int order = 0; order < 2; ++order)
    {
        int first = order ? BUTTON_POWER : BUTTON_NEXT;
        int second = order ? BUTTON_NEXT : BUTTON_POWER;
        reset_curtain();
        action_last.wait_for_release = true;
        action_last.button = BUTTON_POWER;
        action_last.context = CONTEXT_STD;
        action_last.keys_locked = true;
        custom_buttons = true;
        custom_launch = true;
        CHECK(event(chord, CONTEXT_KEYBOARD | ALLOW_SOFTLOCK) == ACTION_NONE);
        CHECK(!actual_curtain && curtain_release_mask == chord);
        CHECK(!action_last.wait_for_release && action_last.keys_locked);
        CHECK(event(first | BUTTON_REL, CONTEXT_LIST | ALLOW_SOFTLOCK) == ACTION_NONE);
        CHECK(curtain_release_mask == second);
        CHECK(event(BUTTON_NONE, CONTEXT_STD) == ACTION_NONE);
        CHECK(event(second | BUTTON_REPEAT, CONTEXT_STD) == ACTION_NONE);
        CHECK(event(second | BUTTON_REL, CONTEXT_KEYBOARD) == ACTION_NONE);
        CHECK(!curtain_release_mask && physical_calls == 0 && custom_clicks == 0);
        CHECK(!queued_launch && pending_launch_calls == 0);
        action_last.keys_locked = false;
        custom_buttons = false;
        CHECK(event(BUTTON_NEXT, CONTEXT_LIST) == ACTION_STD_NEXT);
    }
    return 0;
}

static int plugin_cases(void)
{
    const int chord = BUTTON_POWER | BUTTON_NEXT;
    reset_curtain();
    int keys[] = {chord, BUTTON_NEXT | BUTTON_REL, BUTTON_POWER | BUTTON_REL, BUTTON_PLAY};
    raw_feed(keys, NULL, 4);
    CHECK(plugin_button_get(true) == BUTTON_PLAY && last_block && raw_offset == 4);
    CHECK(!actual_curtain && !curtain_release_mask);
    raw_one(SYS_EVENT | 8);
    CHECK(plugin_button_get_w_tmo(23) == (SYS_EVENT | 8) && last_timeout == 23);
    reset_curtain();
    raw_one(chord);
    CHECK(plugin_button_get(false) == BUTTON_NONE && !last_block);
    raw_one(BUTTON_NEXT | BUTTON_REL);
    CHECK(plugin_button_get_w_tmo(0) == BUTTON_NONE && last_timeout == 0);
    raw_one(BUTTON_POWER | BUTTON_REL);
    CHECK(plugin_button_get(false) == BUTTON_NONE && !curtain_release_mask);
    raw_one(chord);
    CHECK(plugin_button_get(false) == chord);
    CHECK(plugin_button_filter(BUTTON_REDRAW) == BUTTON_REDRAW);
    CHECK(plugin_button_filter(BUTTON_NONE) == BUTTON_NONE);
    return 0;
}

static int deadline_cases(void)
{
    const int chord = BUTTON_POWER | BUTTON_NEXT;
    int keys[] = {chord, BUTTON_NEXT | BUTTON_REL, BUTTON_POWER | BUTTON_REL, BUTTON_PLAY};
    int advance[] = {10, 10, 10, 10};
    reset_curtain();
    raw_feed(keys, advance, 4);
    CHECK(plugin_button_get_w_tmo(100) == BUTTON_PLAY);
    CHECK(raw_offset == 4 && raw_waits[0] == 100 && raw_waits[1] == 90 &&
          raw_waits[2] == 80 && raw_waits[3] == 70);
    reset_curtain();
    current_tick = (long)UINT32_MAX - 5;
    raw_feed(keys, advance, 4);
    CHECK(plugin_button_get_w_tmo(15) == BUTTON_NONE);
    CHECK(raw_offset == 2 && raw_waits[0] == 15 && raw_waits[1] == 5);
    reset_curtain();
    raw_feed(keys, advance, 4);
    CHECK(plugin_button_get_w_tmo(TIMEOUT_BLOCK) == BUTTON_PLAY && raw_offset == 4);
    return 0;
}

static int flush_cases(void)
{
    const int chord = BUTTON_POWER | BUTTON_NEXT;
    int keys[] = {BUTTON_POWER | BUTTON_REPEAT, chord, BUTTON_POWER | BUTTON_REL,
                  BUTTON_NEXT | BUTTON_REL, BUTTON_PLAY};
    reset_curtain();
    raw_one(chord);
    CHECK(plugin_button_get(false) == BUTTON_NONE && curtain_release_mask == chord);
    plugin_button_clear_queue();
    CHECK(raw_clears == 1 && !curtain_release_mask && curtain_wait_for_press);
    raw_feed(keys, NULL, 5);
    CHECK(plugin_button_get(true) == BUTTON_PLAY && raw_offset == 5);
    CHECK(!curtain_release_mask && !curtain_wait_for_press);
    plugin_button_clear_queue();
    raw_one(BUTTON_POWER);
    CHECK(plugin_button_get(true) == BUTTON_POWER && !curtain_wait_for_press);
    return 0;
}

static int handoff_cases(void)
{
    const int chord = BUTTON_POWER | BUTTON_NEXT;
    reset_curtain();
    raw_one(chord);
    CHECK(plugin_button_get(false) == BUTTON_NONE);
    action_last.wait_for_release = true;
    action_last.button = BUTTON_POWER;
    CHECK(event(BUTTON_POWER | BUTTON_REL, CONTEXT_KEYBOARD) == ACTION_NONE);
    CHECK(event(BUTTON_NEXT | BUTTON_REL, CONTEXT_STD) == ACTION_NONE);
    CHECK(!curtain_release_mask);
    CHECK(event(BUTTON_PLAY, CONTEXT_LIST) == ACTION_STD_NEXT);
    reset_curtain();
    CHECK(event(chord, CONTEXT_STD) == ACTION_NONE);
    raw_one(BUTTON_NEXT | BUTTON_REL);
    CHECK(plugin_button_get(false) == BUTTON_NONE);
    raw_one(BUTTON_POWER | BUTTON_REL);
    CHECK(plugin_button_get(false) == BUTTON_NONE && !curtain_release_mask);
    return 0;
}

int main(void)
{
    int result = core_cases();
    if (!result) result = plugin_cases();
    if (!result) result = deadline_cases();
    if (!result) result = flush_cases();
    if (!result) result = handoff_cases();
    if (!result) printf("{\"checks\":%d}\n", checks);
    return result;
}
'''


def production_function(source, name):
    return balanced_definition(source, r'^[ \t]*(?:static\s+)?(?:bool|long|void)\s+\b' +
                               name + r'\s*\([^;{}]*\)\n\{')


class CurtainRecoveryTests(unittest.TestCase):
    def test_actual_early_filter_and_plugin_callbacks(self):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            self.skipTest("C host compiler unavailable; run under WSL")
        paths = (*INPUTS, "apps/accessibility.c", "apps/plugin.c", __file__)
        inputs = {str(path): (ROOT / path).read_bytes() for path in paths}
        decoded = {path: content.decode("utf-8") for path, content in inputs.items()}
        plugin = decoded["apps/plugin.c"]
        self.assertRegex(plugin, r'#if defined\(HIBY_R1\) && defined\(HAVE_ESPEAK\)\s+'
                                r'plugin_button_get,\s+plugin_button_get_w_tmo,\s+#else\s+'
                                r'button_get,\s+button_get_w_tmo,')
        generated = action_harness(decoded)
        old = "bool accessibility_curtain_escape(int button)\n{ (void)button; return recover_curtain; }"
        self.assertEqual(generated.count(old), 1)
        replacement = r'''
#define HIBY_R1
static int curtain_release_mask;
static bool curtain_wait_for_press;
static bool actual_curtain;
static bool backlight_screen_curtain_active(void) { return actual_curtain; }
static bool accessibility_set_curtain(bool enabled) { actual_curtain = enabled; return true; }
''' + production_function(decoded["apps/accessibility.c"], "accessibility_curtain_escape") + \
            production_function(decoded["apps/accessibility.c"], "accessibility_curtain_clear_queue") + "\n#undef HIBY_R1\n"
        generated = generated.replace(old, replacement, 1)
        generated = generated.replace("int main(int argc, char **argv)",
                                      "int previous_cases(int argc, char **argv)", 1)
        generated += r'''
static bool last_block;
static int raw_keys[32], raw_advances[32], raw_waits[32], raw_count, raw_offset, raw_clears;
static void raw_feed(const int *keys, const int *advance, int count)
{
    memcpy(raw_keys, keys, sizeof(int) * count);
    memset(raw_advances, 0, sizeof(raw_advances));
    if (advance) memcpy(raw_advances, advance, sizeof(int) * count);
    raw_count = count;
    raw_offset = 0;
}
static void raw_one(int button) { raw_feed(&button, NULL, 1); }
static long raw_next(int timeout)
{
    if (raw_offset == raw_count) return BUTTON_NONE;
    raw_waits[raw_offset] = timeout;
    current_tick = (long)((uint32_t)current_tick + (uint32_t)raw_advances[raw_offset]);
    return raw_keys[raw_offset++];
}
static long raw_get(bool block) { last_block = block; return raw_next(-1); }
static long raw_get_w_tmo(int timeout) { last_timeout = timeout; return raw_next(timeout); }
static void raw_clear(void) { ++raw_clears; raw_count = raw_offset = 0; }
#define button_get raw_get
#define button_get_w_tmo raw_get_w_tmo
#define button_clear_queue raw_clear
'''
        generated += "\n".join(production_function(plugin, name) for name in (
            "plugin_button_filter", "plugin_button_get", "plugin_button_get_w_tmo", "plugin_button_clear_queue"))
        generated += CASES
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        area = project_materials_root(ROOT) / "r1-accessibility-20261015/curtain-recovery" / stamp
        area.mkdir(parents=True, exist_ok=False)
        unit = area / "recovery.c"
        unit.write_text(generated, encoding="utf-8")
        records = []
        try:
            for variant, flags in (("strict", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"])):
                executable = area / (variant + (".exe" if os.name == "nt" else ".bin"))
                command = compiler + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                                      *flags, str(unit), "-o", str(executable)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                (area / (variant + ".compile.log")).write_text(result.stdout + result.stderr, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=20)
                (area / (variant + ".run.log")).write_text(run.stdout + run.stderr, encoding="utf-8")
                records.append(dict(variant=variant, command=command, exit_code=run.returncode, output=run.stdout))
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertGreaterEqual(json.loads(run.stdout)["checks"], 40)
        finally:
            unchanged = all((ROOT / path).read_bytes() == content for path, content in inputs.items())
            (area / "report.json").write_text(json.dumps(dict(
                passed=len(records) == 2 and all(record["exit_code"] == 0 for record in records) and unchanged,
                scope="Actual action filter, manager recovery latch and plugin callback bodies; mocked core services",
                hardware_tested=False, source_unchanged=unchanged,
                source_sha256={path: hashlib.sha256(content).hexdigest() for path, content in inputs.items()},
                runs=records), indent=2), encoding="utf-8")
        self.assertTrue(unchanged)


if __name__ == "__main__":
    unittest.main(verbosity=2)
