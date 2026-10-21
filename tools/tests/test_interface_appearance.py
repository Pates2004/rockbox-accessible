"""Execute core color presets and actual settings serialization with real metadata."""

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
SOURCE = ROOT / "apps/menus/theme_menu.c"
SETTINGS = ROOT / "apps/settings.c"
METADATA = ROOT / "apps/settings_list.c"
FIXTURE = ROOT / "tools/tests/interface_appearance_fixture.c"


def function_source(source, name):
    matched = re.search(r"^(?:static )?[\w *]+\b" + re.escape(name) + r"\([^;]*?\)\n\{", source, re.M)
    if not matched:
        raise RuntimeError(f"Production function not found: {name}")
    opened = source.index("{", matched.start())
    depth = 1
    cursor = opened + 1
    while depth and cursor < len(source):
        if source[cursor] == "{":
            depth += 1
        elif source[cursor] == "}":
            depth -= 1
        cursor += 1
    if depth:
        raise RuntimeError(f"Unbalanced production function: {name}")
    return source[matched.start():cursor] + "\n"


def contrast(first, second):
    def luminance(channels):
        linear = [channel / 255 / 12.92 if channel / 255 <= .04045
                  else ((channel / 255 + .055) / 1.055) ** 2.4 for channel in channels]
        return sum(weight * channel for weight, channel in zip((.2126, .7152, .0722), linear))
    brighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (brighter + .05) / (darker + .05)


class InterfaceAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable; run with WSL")
        cls.evidence = project_materials_root(ROOT) / "r1-hardening-20261015/appearance" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.evidence.mkdir(parents=True)
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.metadata = METADATA.read_text(encoding="utf-8")
        cls.executables = {}
        cls.runs = []
        cls.hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (SOURCE, SETTINGS, METADATA, FIXTURE, Path(__file__),
                                   ROOT / "apps/settings_list.h", ROOT / "firmware/export/lcd.h",
                                   ROOT / "firmware/common/strmemccpy.c",
                                   ROOT / "firmware/common/itoa_buf.c", ROOT / "apps/misc.c")}
        cls.prepare_sources()

    @classmethod
    def tearDownClass(cls):
        (cls.evidence / "results.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_hashes": cls.hashes, "runs": cls.runs,
            "limits": "Production functions with mocked save/apply hooks; no GUI or physical display acceptance.",
        }, indent=2), encoding="utf-8")
        print(f"Interface appearance evidence: {cls.evidence}", flush=True)

    @classmethod
    def prepare_sources(cls):
        colors_start = cls.source.index("enum Colors {")
        colors_end = cls.source.index("\n};", cls.source.index("} colors[COLOR_COUNT]")) + 4
        appearance_start = cls.source.index("enum interface_appearance\n{")
        appearance_end = cls.source.index("\n};", appearance_start) + 4
        lang_ids = re.findall(r"LANG_\w+", cls.source[colors_start:colors_end])
        generated = "\n".join(f"#define {name} {index}" for index, name in enumerate(lang_ids))
        generated += "\n" + cls.source[colors_start:colors_end]
        generated += "\n" + cls.source[appearance_start:appearance_end]
        generated += "\n" + function_source(cls.source, "apply_interface_appearance")
        (cls.evidence / "actual_appearance.h").write_text(generated, encoding="utf-8")

        defaults = re.findall(r"^#define DEFAULT_THEME_\w+[^\n]+", cls.metadata, re.M)
        entries = re.findall(r"\{F_T_INT\|F_RGB\|F_THEMESETTING\s*,&global_settings\.\w+,-1,\s*"
                             r"INT\(DEFAULT_THEME_\w+\),\"[^\"]+\",UNUSED\}", cls.metadata)
        if len(defaults) != 6 or len(entries) != 6:
            raise RuntimeError("Expected the six actual RGB settings/defaults")
        cursor_default = re.search(r"cursor_style, LANG_INVERT_CURSOR,\s*#ifdef HAVE_LCD_COLOR\s*(\d+),",
                                   cls.metadata).group(1)
        generated = "\n".join(defaults) + f"\n#define ACTUAL_CURSOR_DEFAULT {cursor_default}\n"
        generated += "#define ACTUAL_COLOR_SETTINGS \\\n" + ", \\\n".join(entry.replace("\n", " ") for entry in entries) + ",\n"
        (cls.evidence / "actual_color_settings.h").write_text(generated, encoding="utf-8")

        lcd = (ROOT / "firmware/export/lcd.h").read_text(encoding="utf-8")
        opened = lcd.index("#if LCD_PIXELFORMAT == RGB565 || LCD_PIXELFORMAT == RGB565SWAPPED")
        ended = lcd.index("\n#elif LCD_DEPTH > 1 /* greyscale */", opened)
        (cls.evidence / "actual_lcd_colors.h").write_text(lcd[opened:ended] + "\n", encoding="utf-8")

        settings = SETTINGS.read_text(encoding="utf-8")
        misc = (ROOT / "apps/misc.c").read_text(encoding="utf-8")
        generated = function_source(misc, "hex2dec") + function_source(misc, "hex_to_rgb")
        generated += function_source((ROOT / "firmware/common/strmemccpy.c").read_text(encoding="utf-8"),
                                     "strmemccpy")
        generated += function_source((ROOT / "firmware/common/itoa_buf.c").read_text(encoding="utf-8"),
                                     "itoa_buf")
        for name in ("setting_get_cfgvals", "find_setting", "find_setting_by_cfgname", "reset_setting",
                     "cfg_string_to_int", "copy_filename_setting", "string_to_cfg", "cfg_int_to_string",
                     "cfg_to_string"):
            generated += function_source(settings, name)
        (cls.evidence / "actual_settings_functions.h").write_text(generated, encoding="utf-8")

    def build(self, mode):
        if mode in self.executables:
            return self.executables[mode]
        executable = self.evidence / mode
        pixel_format = {"rgb888": 3, "rgb565": 1, "rgb565swapped": 2, "no-backdrop": 3}[mode]
        command = self.compiler + ["-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                                   "-fsanitize=undefined", "-fno-sanitize-recover=all",
                                   f"-DLCD_PIXELFORMAT={pixel_format}", "-I", str(self.evidence),
                                   "-I", str(ROOT / "apps"), str(FIXTURE), "-o", str(executable)]
        if mode != "no-backdrop":
            command.append("-DHAVE_BACKDROP_IMAGE")
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (self.evidence / f"{mode}-build.log").write_text(
            shlex.join(command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.executables[mode] = executable
        return executable

    def run_scenario(self, scenario):
        for mode in ("rgb888", "rgb565", "rgb565swapped", "no-backdrop"):
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.build(mode)), scenario], capture_output=True,
                                        text=True, timeout=10)
                self.runs.append({"mode": mode, "scenario": scenario, "returncode": result.returncode,
                                  "stdout": result.stdout, "stderr": result.stderr})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                if scenario in ("dark", "light"):
                    colors = json.loads(result.stdout)
                    self.assertGreaterEqual(contrast(colors["foreground"], colors["background"]), 12)
                    self.assertGreaterEqual(contrast(colors["selected_text"], colors["selection"]), 7)
                    self.assertGreaterEqual(contrast(colors["separator"], colors["background"]), 3)

    def test_dark_palette_and_contrast(self):
        self.run_scenario("dark")

    def test_light_palette_and_contrast(self):
        self.run_scenario("light")

    def test_compiled_default_colors_not_factory_reset(self):
        self.run_scenario("default")

    def test_unrelated_settings_and_ordinary_apply_hooks(self):
        self.run_scenario("scope")

    def test_invalid_choice_has_no_side_effects(self):
        self.run_scenario("invalid")

    def test_repeated_application_is_bounded_and_idempotent(self):
        self.run_scenario("repeat")

    def test_dark_settings_roundtrip_actual_config_functions(self):
        self.run_scenario("dark-persistence")

    def test_light_settings_roundtrip_actual_config_functions(self):
        self.run_scenario("light-persistence")

    def test_default_settings_roundtrip_actual_config_functions(self):
        self.run_scenario("default-persistence")

    def test_menu_actions_have_separate_localized_names_and_color_capability(self):
        section = self.source[self.source.index("enum interface_appearance\n{"):
                              self.source.index("MENUITEM_FUNCTION_W_PARAM(set_bg_col")]
        for suffix in ("DARK", "LIGHT", "DEFAULT"):
            self.assertIn(f"ID2P(LANG_INTERFACE_APPEARANCE_{suffix})", section)
            self.assertIn(f"(void*)INTERFACE_APPEARANCE_{suffix}", section)
        self.assertIn("MAKE_MENU(interface_appearance_menu, ID2P(LANG_INTERFACE_APPEARANCE)", section)
        self.assertRegex(self.source, r"MAKE_MENU\(colors_settings,[\s\S]*?&interface_appearance_menu")
        self.assertLess(self.source.index("#ifdef HAVE_LCD_COLOR\n\nenum Colors"),
                        self.source.index("enum interface_appearance"))
        self.assertGreater(self.source.index("#endif /* HAVE_LCD_COLOR */"),
                           self.source.index("MAKE_MENU(interface_appearance_menu"))

    def test_text_fields_are_existing_saved_theme_settings(self):
        for field in ("sbs_file", "colors_file", "backdrop_file"):
            self.assertRegex(self.metadata, r"TEXT_SETTING\(F_THEMESETTING\|F_NEEDAPPLY,\s*"
                             + field + r"\s*,")
        self.assertIn('VIEWPORT_SETTING(ui_vp_config, "ui viewport")', self.metadata)
        self.assertRegex(self.metadata, r"#define VIEWPORT_SETTING[^\n]+\\\n\s*"
                         r"TEXT_SETTING\(F_THEMESETTING\|F_NEEDAPPLY")
        self.assertRegex(self.metadata, r'"pointer,bar \(inverse\),bar \(color\),bar \(gradient\)"')


if __name__ == "__main__":
    unittest.main()
