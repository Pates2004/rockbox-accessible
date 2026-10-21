"""Compile production widget hit tests against bounded pixel and speech fixtures."""

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
from test_keyclick_pcm import definition


ROOT = Path(__file__).resolve().parents[2]
COMMON = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#ifndef TEST_NO_ESPEAK
#define HAVE_ESPEAK
#endif
#define NB_SCREENS 1
#define SCREEN_MAIN 0
#define ACTION_NONE 0
#define ACTION_UNKNOWN 99
#define BUTTON_NONE 0
#define BUTTON_TOUCHSCREEN 1
#define BUTTON_REL 2
#define ACTION_STD_OK 3
#define ACTION_STD_CANCEL 4
#define LANG_SET_BOOL_YES 10
#define LANG_SET_BOOL_NO 11
#define LANG_COLOR_RGB_LABELS 12
#define UNIT_INT 1
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define P2STR(text) ((const char *)(text))
#define CHECK(condition) do { if (!(condition)) return __LINE__; } while (0)
struct viewport { int x, y, width, height; };
struct screen {
    int screen_type, depth;
    int (*getcharheight)(void);
    struct viewport *(*set_viewport)(struct viewport *);
    int (*getstringsize)(const char *, int *, int *);
};
static int point_x, point_y, point_ready, reports, reported_target, spoken, value_calls;
static int values = -1;
static bool point_force = true, reported_occupied;
static const void *reported_owner;
static struct viewport original_viewport, default_viewport = {20, 30, 200, 160};
static struct viewport *active_viewport = &original_viewport;
static int old_button;
bool accessibility_enabled(void) { return true; }
bool accessibility_explore_point(int *position_x, int *position_y, bool *force)
{
    if (!point_ready) return false;
    point_ready = false;
    *position_x = point_x; *position_y = point_y; *force = point_force;
    return true;
}
void accessibility_explore_feedback(const void *owner, int target, bool occupied)
{ ++reports; reported_owner = owner; reported_target = target; reported_occupied = occupied; }
void accessibility_speak_empty(void) { spoken = -1; }
bool viewport_point_within_vp(const struct viewport *viewport, int position_x, int position_y)
{
    return position_x >= viewport->x && position_y >= viewport->y &&
        position_x - viewport->x < viewport->width && position_y - viewport->y < viewport->height;
}
void talk_id(int label, bool enqueue) { (void)enqueue; spoken = label; }
void talk_spell(const char *text, bool enqueue) { (void)enqueue; spoken = text && *text ? 20 : -1; }
void talk_value(int value, int unit, bool enqueue)
{ (void)unit; (void)enqueue; ++value_calls; values = value; }
const char *str(int label) { (void)label; return "RGB"; }
int font_height(void) { return 10; }
struct viewport *set_viewport(struct viewport *viewport)
{ struct viewport *previous = active_viewport; active_viewport = viewport; return previous; }
int getstringsize(const char *text, int *width, int *height)
{ if (width) *width = (int)strlen(text) * 6; if (height) *height = 10; return 0; }
void viewport_set_defaults(struct viewport *viewport, int screen)
{ (void)screen; *viewport = default_viewport; }
int action_get_touchscreen_press_in_vp(short *position_x, short *position_y, struct viewport *viewport)
{ (void)viewport; *position_x = point_x; *position_y = point_y; return old_button; }
int get_icon_width(int screen) { (void)screen; return 8; }
static void point(int position_x, int position_y)
{ point_x = position_x; point_y = position_y; point_ready = true; }
"""

YESNO = r"""
struct text_message { const char **message_lines; int nb_lines; };
struct gui_yesno { struct viewport vp; const struct text_message *main_message;
                   struct screen *display; int vp_lines; };
"""
YESNO_CASES = r"""
int main(void)
{
    struct screen display = {.getcharheight = font_height};
    const char *lines[] = {"Question", "", "Details"};
    struct text_message message = {lines, 3};
    struct gui_yesno dialog = {{20, 30, 200, 100}, &message, &display, 10};
    point(30, 45); gui_yesno_explore(&dialog);
    CHECK(reported_owner == &dialog && reported_target == 0 && reported_occupied);
    CHECK(spoken == 20 && value_calls == 0 && values == -1);
    point(30, 55); gui_yesno_explore(&dialog);
    CHECK(reported_target == -1 && !reported_occupied && spoken == -1);
    point(30, 90); gui_yesno_explore(&dialog);
    CHECK(reported_target == 3 && spoken == LANG_SET_BOOL_YES);
    point(120, 90); gui_yesno_explore(&dialog);
    CHECK(reported_target == 4 && spoken == LANG_SET_BOOL_NO);
    point(220, 90); gui_yesno_explore(&dialog);
    CHECK(!reported_occupied);
    int previous = reports;
    gui_yesno_explore(&dialog);
    CHECK(reports == previous);
    CHECK(value_calls == 0 && values == -1);
    return 0;
}
"""

QUICKSCREEN = r"""
#define FOR_QS_ITEMS(index) for (int index = 0; index < QUICKSCREEN_ITEM_COUNT; ++index)
#define CENTER_ICONAREA_SIZE 26
#define QS_ICON_WIDTH 7
#define QS_ICON_HEIGHT 8
enum quickscreen_item { QUICKSCREEN_TOP, QUICKSCREEN_LEFT, QUICKSCREEN_RIGHT,
                        QUICKSCREEN_BOTTOM, QUICKSCREEN_ITEM_COUNT };
struct settings_list { int lang_id, value; };
struct quickscreen { const struct settings_list *items[4]; struct viewport parent[1];
                     struct viewport vps[1][4]; struct viewport vp_icons[1]; };
int option_value_as_int(const struct settings_list *setting) { return setting->value; }
void option_talk_value(const struct settings_list *setting, int value, bool enqueue)
{ (void)setting; (void)enqueue; ++value_calls; values = value; }
"""
QUICKSCREEN_CASES = r"""
int main(void)
{
    struct settings_list setting = {30, 4};
    struct quickscreen quick = {0};
    quick.parent[0] = (struct viewport){20, 30, 200, 160};
    quick.vps[0][QUICKSCREEN_LEFT] = (struct viewport){20, 90, 60, 20};
    quick.vp_icons[0] = (struct viewport){90, 70, 60, 60};
    quick.items[QUICKSCREEN_LEFT] = &setting;
    point(25, 95); quickscreen_explore(&quick);
    CHECK(reported_target == QUICKSCREEN_LEFT && reported_occupied && spoken == 30 && values == 4);
    CHECK(reported_owner == &quick && value_calls == 1);
    point(91, 98); quickscreen_explore(&quick);
    CHECK(reported_target == QUICKSCREEN_LEFT && reported_occupied);
    CHECK(value_calls == 2 && values == 4);
    point(120, 98); quickscreen_explore(&quick);
    CHECK(!reported_occupied && spoken == -1);
    point(25, 45); quickscreen_explore(&quick);
    CHECK(!reported_occupied);
    point_force = false;
    int previous = reports;
    point(121, 99); quickscreen_explore(&quick);
    CHECK(reports == previous + 1 && !reported_occupied);
    CHECK(reported_owner == &quick && value_calls == 2);
    return 0;
}
"""

COLOR = r"""
struct rgb_pick { unsigned int color; unsigned char rgb_val[3]; };
static const unsigned char rgb_max[] = {255, 255, 255};
int label_get_max_width(struct screen *display) { (void)display; return 6; }
void pack_rgb(struct rgb_pick *rgb) { rgb->color = 0; }
"""
COLOR_CASES = r"""
int main(void)
{
    struct screen display = {0, 24, font_height, set_viewport, getstringsize};
    struct rgb_pick rgb = {0x123456, {18, 52, 86}};
    int slider = 0;
    point(50, 69);
    touchscreen_slider(&display, &rgb, &slider);
#ifdef HAVE_ESPEAK
    CHECK(reported_target == 1 && reported_occupied && slider == 1 && values == 52);
    CHECK(reported_owner == &rgb && spoken == 20 && value_calls == 1);
    CHECK(rgb.color == 0x123456 && rgb.rgb_val[1] == 52);
    point(50, 69); point_force = false;
    int previous = reports;
    touchscreen_slider(&display, &rgb, &slider);
    CHECK(reports == previous + 1);
    CHECK(value_calls == 1 && values == 52);
    point(220, 69); touchscreen_slider(&display, &rgb, &slider);
    CHECK(!reported_occupied && active_viewport == &original_viewport);
    point(50, 35); touchscreen_slider(&display, &rgb, &slider);
    CHECK(!reported_occupied);
    point(50, 115); touchscreen_slider(&display, &rgb, &slider);
    CHECK(!reported_occupied);
    CHECK(spoken == -1 && value_calls == 1);
#else
    CHECK(active_viewport == &original_viewport && rgb.color == 0x123456);
    old_button = BUTTON_REL;
    point(30, 5);
    CHECK(touchscreen_slider(&display, &rgb, &slider) == ACTION_STD_CANCEL);
    CHECK(reports == 0 && reported_owner == NULL && reported_target == 0 && !reported_occupied);
    CHECK(spoken == 0 && value_calls == 0 && values == -1);
#endif
    CHECK(active_viewport == &original_viewport);
    return 0;
}
"""

SKIN = r"""
#define VP_DRAW_HIDDEN 1
#define ACTION_TOUCH_SOFTLOCK 100
#define SKINOFFSETTOPTR(buffer, pointer) ((void)(buffer), (pointer))
struct skin_viewport { int hidden_flags; struct viewport vp; };
struct touchregion { struct skin_viewport *wvp; int x, y, width, height, wpad, hpad;
                     int action; bool allow_while_locked; };
struct wps_token { struct { struct touchregion *data; } value; };
struct skin_token_list { struct wps_token *token; struct skin_token_list *next; };
struct wps_data { struct skin_token_list *touchregions; bool touchscreen_locked; };
struct gui_wps { struct wps_data *data; };
char *get_skin_buffer(struct wps_data *data) { (void)data; return NULL; }
"""
SKIN_CASES = r"""
int main(void)
{
    struct skin_viewport viewport = {0, {20, 30, 200, 160}};
    struct touchregion region = {&viewport, 10, 20, 30, 40, 2, 3, 4, false};
    struct wps_token token = {{&region}};
    struct skin_token_list entry = {&token, NULL};
    struct wps_data data = {&entry, false};
    struct gui_wps wps = {&data};
    point(30, 55); skin_accessibility_explore(&wps);
    CHECK(reported_target == 0 && reported_occupied && reported_owner == &wps);
    CHECK(reports == 1 && spoken == 0 && value_calls == 0 && values == -1);
    point(28, 48); skin_accessibility_explore(&wps);
    CHECK(reported_occupied);
    point(27, 48); skin_accessibility_explore(&wps);
    CHECK(!reported_occupied);
    CHECK(spoken == -1);
    viewport.hidden_flags = VP_DRAW_HIDDEN;
    point(30, 55); skin_accessibility_explore(&wps);
    CHECK(!reported_occupied);
    CHECK(spoken == -1 && value_calls == 0 && values == -1);
    viewport.hidden_flags = 0; data.touchscreen_locked = true;
    point(30, 55); skin_accessibility_explore(&wps);
    CHECK(!reported_occupied);
    region.allow_while_locked = true;
    point(30, 55); skin_accessibility_explore(&wps);
    CHECK(reported_occupied);
    region.width = 0;
    point(30, 55); skin_accessibility_explore(&wps);
    CHECK(!reported_occupied);
    return 0;
}
"""


class KeyclickExplorationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(compiler[0]):
            raise unittest.SkipTest("C compiler unavailable; run compiled tests under WSL")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = project_materials_root(ROOT) / "r1-input-refinements-20261017" / "widget-exploration" / stamp
        cls.workspace.mkdir(parents=True, exist_ok=False)
        paths = {"yesno": "apps/gui/yesno.c", "quickscreen": "apps/gui/quickscreen.c",
                 "color": "apps/gui/color_picker.c", "skin": "apps/gui/skin_engine/skin_touchsupport.c"}
        cls.inputs = {path: (ROOT / path).read_bytes() for path in paths.values()}
        functions = {"yesno": (YESNO, "static void gui_yesno_explore(", YESNO_CASES),
                     "quickscreen": (QUICKSCREEN, "static void quickscreen_explore(", QUICKSCREEN_CASES),
                     "color": (COLOR, "static int touchscreen_slider(", COLOR_CASES),
                     "skin": (SKIN, "static void skin_accessibility_explore(", SKIN_CASES)}
        cls.executables = {}
        for name in ("yesno", "quickscreen", "color", "skin", "color_without_espeak"):
            selected = "color" if name == "color_without_espeak" else name
            prefix, signature, cases = functions[selected]
            source = cls.inputs[paths[selected]].decode("utf-8")
            if selected == "color":
                prefix += "\n".join(re.findall(r"^#define (?:MARGIN_TOP|TITLE_MARGIN_BOTTOM|SELECTOR_TB_MARGIN|"
                    r"SELECTOR_WIDTH|SLIDER_TEXT_MARGIN|SWATCH_TOP_MARGIN|MARGIN_BOTTOM)\b[^\n]*", source, re.MULTILINE))
            harness = COMMON + prefix + "\n" + definition(source, signature) + cases
            path = cls.workspace / (name + ".c")
            path.write_text(harness, encoding="utf-8")
            executable = cls.workspace / (name + (".exe" if os.name == "nt" else ""))
            command = compiler + ["-std=c99", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                "-fno-sanitize-recover=all", str(path), "-o", str(executable)]
            if name == "color_without_espeak":
                command += ["-DTEST_NO_ESPEAK"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            (cls.workspace / (name + ".log")).write_text(shlex.join(command) + "\n" + result.stdout + result.stderr,
                                                        encoding="utf-8")
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            cls.executables[name] = executable
        (cls.workspace / "provenance.json").write_text(json.dumps({
            "source_root": str(ROOT), "source_sha256": {path: hashlib.sha256(value).hexdigest()
                for path, value in cls.inputs.items()}, "scope": "production widget hit-test functions, mocked pixels and speech; no UI, input injection or audio",
        }, indent=2), encoding="utf-8")

    def check_widget(self, name):
        result = subprocess.run([str(self.executables[name])], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_yes_no_message_buttons_blank_and_outside_pixels(self):
        self.check_widget("yesno")

    def test_quickscreen_settings_icons_and_empty_pixels(self):
        self.check_widget("quickscreen")

    def test_color_exploration_keeps_values_and_restores_viewport(self):
        self.check_widget("color")

    def test_color_without_espeak_preserves_legacy_touch_and_restores_viewport(self):
        self.check_widget("color_without_espeak")

    def test_skin_padding_hidden_locked_and_zero_size_regions(self):
        self.check_widget("skin")

    @classmethod
    def tearDownClass(cls):
        changed = [path for path, value in cls.inputs.items() if (ROOT / path).read_bytes() != value]
        if changed:
            raise AssertionError("Widget inputs changed during bounded tests: " + ", ".join(changed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
