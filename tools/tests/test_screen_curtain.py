"""Execute actual backlight, R1 input, native framebuffer and SDL display sources."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
from firmware_fixture_support import CONFIG, curtain_configuration

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tools/tests"


class ScreenCurtainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable; run with WSL")
        cls.evidence = project_materials_root(ROOT) / "r1-hardening-20261015/typing-curtain/curtain" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.evidence.mkdir(parents=True)
        cls.headers = cls.evidence / "headers"
        cls.headers.mkdir()
        for name in ("settings.h", "action.h", "cpu.h", "kernel.h", "thread.h",
                     "i2c.h", "debug.h", "rtc.h", "usb.h", "power.h", "system.h", "button.h",
                     "timer.h", "lcd.h", "screendump.h", "backlight-target.h", "backlight-sim.h",
                     "lcd-target.h", "sysfs.h", "panic.h", "mutex.h", "hibylinux_codec.h"):
            (cls.headers / name).write_text("#pragma once\n", encoding="utf-8")
        (cls.headers / "config.h").write_text(curtain_configuration(), encoding="utf-8")
        (cls.headers / "touchscreen.h").write_text(
            (ROOT / "firmware/export/touchscreen.h").read_text(encoding="utf-8"), encoding="utf-8")
        cls.executables = {}
        cls.runs = []
        cls.source_hashes = {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                ROOT / "firmware/backlight.c", ROOT / "firmware/export/backlight.h",
                CONFIG, ROOT / "firmware/export/touchscreen.h",
                TESTS / "firmware_fixture_support.py",
                ROOT / "firmware/backlight-sw-fading.c",
                ROOT / "firmware/target/hosted/lcd-linuxfb.c",
                ROOT / "firmware/target/hosted/backlight-unix.c",
                ROOT / "firmware/target/hosted/sdl/lcd-bitmap.c",
                ROOT / "firmware/target/hosted/sdl/lcd-sdl.c",
                ROOT / "uisimulator/common/backlight-sim.c",
                ROOT / "firmware/target/hosted/hiby/r1/button-r1.c",
                TESTS / "screen_curtain_fixture.h", TESTS / "test_screen_curtain.c",
                TESTS / "test_screen_curtain.py", TESTS / "test_screen_curtain_unsupported.c",
            )
        }

    @classmethod
    def tearDownClass(cls):
        (cls.evidence / "results.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_hashes": cls.source_hashes, "runs": cls.runs,
        }, indent=2), encoding="utf-8")
        print(f"Screen curtain evidence: {cls.evidence}", flush=True)

    def build(self, mode):
        if mode in self.executables:
            return self.executables[mode]
        executable = self.evidence / mode
        command = self.compiler + [
            "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-pthread",
            "-Wno-implicit-fallthrough",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            "-I", str(self.headers), "-I", str(ROOT / "firmware/export"),
            "-I", str(ROOT / "firmware/target/hosted/hiby/r1"),
            "-include", str(TESTS / "screen_curtain_fixture.h"),
            str(TESTS / "test_screen_curtain.c"), "-o", str(executable),
        ]
        if mode == "sdl":
            command += ["-DSIMULATOR", "-Wl,--wrap=SDL_UpdateTexture"] + shlex.split(subprocess.check_output(
                ["pkg-config", "--cflags", "--libs", "sdl2"], text=True))
        else:
            command += [f"-Wl,--wrap={name}" for name in ("open", "close", "ioctl", "mmap", "munmap")]
            if mode == "native-fading":
                command += ["-DCONFIG_BACKLIGHT_FADING=1"]
            if mode == "native-stride":
                command += ["-DFB_STRIDE_MISMATCH=64"]
        built = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (self.evidence / f"{mode}-build.log").write_text(
            shlex.join(command) + "\n" + built.stdout + built.stderr, encoding="utf-8")
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        self.executables[mode] = executable
        return executable

    def run_harness(self, mode, scenario):
        executable = self.build(mode)
        environment = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
        process = subprocess.run([str(executable), scenario], capture_output=True,
                                 text=True, env=environment, timeout=45)
        self.runs.append({"mode": mode, "scenario": scenario, "returncode": process.returncode,
                          "stdout": process.stdout, "stderr": process.stderr})
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_native_queue_touch_settings_and_sleep(self):
        self.run_harness("native", "policy")

    def test_native_fading_cannot_blank_touch_or_reveal_pixels(self):
        self.run_harness("native-fading", "policy")

    def test_native_strided_framebuffer_blacks_padding_and_unused_pages(self):
        self.run_harness("native-stride", "policy")

    def test_native_concurrent_refresh_and_toggles(self):
        self.run_harness("native", "stress")

    def test_native_fading_concurrent_refresh_and_toggles(self):
        self.run_harness("native-fading", "stress")

    def test_native_simultaneous_callers_get_explicit_replies(self):
        self.run_harness("native-fading", "callers")

    def test_simulator_actual_sdl_main_lcd_black_and_skin_unchanged(self):
        self.run_harness("sdl", "policy")

    def test_simulator_concurrent_refresh_and_toggles(self):
        self.run_harness("sdl", "stress")

    def test_simulator_simultaneous_callers_get_explicit_replies(self):
        self.run_harness("sdl", "callers")

    def test_unsupported_espeak_targets_execute_safe_stubs(self):
        for backlight in (True, False):
            with self.subTest(backlight=backlight):
                executable = self.evidence / f"unsupported-{backlight}"
                command = self.compiler + [
                    "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-Wno-implicit-fallthrough", "-ffunction-sections", "-fdata-sections",
                    "-Wl,--gc-sections", "-DCURTAIN_UNSUPPORTED",
                    "-I", str(self.headers), "-I", str(ROOT / "firmware/export"),
                    "-include", str(TESTS / "screen_curtain_fixture.h"),
                    str(TESTS / "test_screen_curtain_unsupported.c"), "-o", str(executable),
                ]
                if not backlight:
                    command.append("-DCURTAIN_NO_BACKLIGHT")
                built = subprocess.run(command, capture_output=True, text=True, timeout=30)
                (self.evidence / f"unsupported-{backlight}-build.log").write_text(
                    shlex.join(command) + "\n" + built.stdout + built.stderr, encoding="utf-8")
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                self.runs.append({"mode": f"unsupported-{backlight}", "returncode": run.returncode,
                                  "stdout": run.stdout, "stderr": run.stderr})
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_capability_is_absent_without_espeak_or_inside_bootloader(self):
        source = '#include "backlight.h"\n#ifdef HAVE_SCREEN_CURTAIN\n#error Unexpected capability\n#endif\n'
        for definition in ("CURTAIN_NO_ESPEAK", "BOOTLOADER"):
            with self.subTest(definition=definition):
                command = self.compiler + [
                    "-E", "-x", "c", "-", f"-D{definition}",
                    "-I", str(self.headers), "-I", str(ROOT / "firmware/export"),
                    "-include", str(TESTS / "screen_curtain_fixture.h"),
                ]
                result = subprocess.run(command, input=source, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
