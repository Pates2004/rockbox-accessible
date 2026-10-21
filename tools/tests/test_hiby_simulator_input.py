import datetime
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
PROBE = r"""
#include <assert.h>
#include <SDL.h>
#include "button.h"
#include "buttonmap.h"
#include "touchscreen.h"

static int mode = TOUCHSCREEN_POINT;
int touchscreen_get_mode(void) { return mode; }

int main(void)
{
    const int keys[] = {SDLK_UP, SDLK_DOWN, SDLK_RIGHT, SDLK_LEFT,
        SDLK_RETURN, SDLK_BACKSPACE, SDLK_SPACE, SDLK_INSERT, SDLK_ESCAPE,
        SDLK_KP_8, SDLK_KP_2, SDLK_KP_ENTER};
    const int expected[] = {BUTTON_VOL_UP, BUTTON_VOL_DOWN, BUTTON_NEXT,
        BUTTON_PLAY, BUTTON_NEXT, BUTTON_PLAY, BUTTON_POWER, BUTTON_POWER,
        BUTTON_POWER, BUTTON_VOL_UP, BUTTON_VOL_DOWN, BUTTON_NEXT};
    for (unsigned int index = 0; index < sizeof(keys) / sizeof(keys[0]); ++index)
    {
        assert(key_to_button(keys[index]) == expected[index]);
#ifdef HIBY_R1
        assert(key_to_touch(keys[index], 0) == BUTTON_NONE);
#endif
        assert(expected[index] != BUTTON_PREV);
    }
#ifndef HIBY_R1
    assert(key_to_touch(SDLK_UP, 0) == BUTTON_TOPMIDDLE);
    assert(key_to_touch(SDLK_DOWN, 0) == BUTTON_BOTTOMMIDDLE);
    assert(key_to_touch(SDLK_LEFT, 0) == BUTTON_MIDLEFT);
    assert(key_to_touch(SDLK_RIGHT, 0) == BUTTON_MIDRIGHT);
#endif
    assert(key_to_button(SDLK_z) == BUTTON_NONE);
    assert(key_to_button(SDLK_KP_0) == BUTTON_NONE);
    assert(key_to_touch(SDLK_7, 0) == BUTTON_TOPLEFT);
    assert(key_to_touch(BUTTON_TOUCHSCREEN, 0) == BUTTON_TOUCHSCREEN);
    mode = TOUCHSCREEN_BUTTON;
    assert(key_to_touch(BUTTON_TOUCHSCREEN, (10u << 16) | 10u) == BUTTON_TOPLEFT);
    return 0;
}
"""


@unittest.skipUnless(os.name == "posix" and shutil.which("sdl2-config"), "Needs POSIX SDL2 headers")
class HibySimulatorInputTests(unittest.TestCase):
    def test_physical_key_priority_without_breaking_other_touch_targets(self):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        build = project_materials_root(ROOT) / "hiby-simulator-input" / stamp
        build.mkdir(parents=True)
        (build / "config.h").write_text("#define LCD_WIDTH 480\n#define LCD_HEIGHT 800\n", encoding="utf-8")
        (build / "button.h").write_text(
            '#include "button-target.h"\n#define BUTTON_NONE 0\n'
            '#define BUTTON_TOUCHSCREEN 0x2000000\n', encoding="utf-8")
        (build / "touchscreen.h").write_text(
            '#define TOUCHSCREEN_POINT 0\n#define TOUCHSCREEN_BUTTON 1\n'
            'int touchscreen_get_mode(void);\n', encoding="utf-8")
        (build / "probe.c").write_text(PROBE, encoding="utf-8")
        includes = subprocess.check_output(["sdl2-config", "--cflags"], text=True).split()
        for target in ("r1", "generic"):
            executable = build / target
            arguments = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DSIMULATOR", "-DHAVE_TOUCHSCREEN",
                         "-I" + str(build), "-I" + str(ROOT / "firmware/target/hosted/hiby/r1"),
                         "-I" + str(ROOT / "firmware/target/hosted/sdl"), *includes,
                         build / "probe.c", ROOT / "uisimulator/buttonmap/hiby-r1.c",
                         ROOT / "firmware/target/hosted/sdl/key_to_touch-sdl.c", "-o", executable]
            if target == "r1":
                arguments.insert(1, "-DHIBY_R1")
            result = subprocess.run(arguments, capture_output=True, text=True)
            (build / f"{target}-compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([executable], capture_output=True, text=True)
            (build / f"{target}-result.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
        print(f"Actual SDL physical/touch mapping evidence: {build}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
