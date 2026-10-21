import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
WORKSPACE = _project_materials_root(ROOT) / "tts-coverage-tests" / RUN


def extract_block(source, signature):
    start = source.index(signature)
    masked = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        lambda match: " " * len(match.group()), source, flags=re.DOTALL)
    opening = masked.index("{", start)
    depth = 1
    closing = opening + 1
    while depth:
        if masked[closing] == "{":
            depth += 1
        elif masked[closing] == "}":
            depth -= 1
        closing += 1
    return source[start:closing] + "\n"


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.list_source = (ROOT / "apps/gui/list.c").read_text(encoding="utf-8")
        cls.yesno_source = (ROOT / "apps/gui/yesno.c").read_text(encoding="utf-8")
        cls.splash_source = (ROOT / "apps/gui/splash.c").read_text(encoding="utf-8")
        menu_source = (ROOT / "apps/menu.c").read_text(encoding="utf-8")
        playlist_source = (ROOT / "apps/playlist.c").read_text(encoding="utf-8")
        root_source = (ROOT / "apps/root_menu.c").read_text(encoding="utf-8")
        cls.playlist_viewer_source = (ROOT / "apps/playlist_viewer.c").read_text(encoding="utf-8")
        plugin_source = (ROOT / "apps/plugin.c").read_text(encoding="utf-8")
        WORKSPACE.mkdir(parents=True)
        settings_source = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        helpers = ("talk_tts_enabled", "talk_menus_enabled", "talk_dynamic_enabled")
        policy = "\n".join(extract_block(settings_source, "static inline bool " + name + "(")
                           for name in helpers)
        fixture = (ROOT / "tools/tests/test_tts_coverage.c").read_text(encoding="utf-8")
        declaration = "static struct { bool talk_menu; } global_settings;"
        if fixture.count(declaration) != 1:
            raise AssertionError("Shared coverage settings mock changed; coordinate its named policy struct")
        fixture = fixture.replace(declaration, """struct user_settings {
    bool talk_menu, talk_filetype;
    int talk_file, talk_dir;
#ifdef HAVE_ESPEAK
    bool tts_enabled;
    int tts_announce_position;
    bool tts_announce_dynamic;
#endif
};
static struct user_settings global_settings;
""" + "#ifdef HAVE_ESPEAK\n" + "\n".join(extract_block(text, signature).rstrip() + ";" for text, signature in (
            (settings_source, "enum tts_position_mode\n"),
            ((ROOT / "apps/gui/list.h").read_text(encoding="utf-8"), "enum list_position_source\n"))) +
            extract_block(settings_source, "static inline bool talk_list_position_enabled(") + "#endif\n" + policy)
        fixture = fixture.replace("list->talk_menu = global_settings.talk_menu;",
                                  "list->talk_menu = talk_menus_enabled(&global_settings);")
        fixture = fixture.replace("if (global_settings.talk_menu) talk_id(identifier, false);",
                                  "if (talk_menus_enabled(&global_settings)) talk_id(identifier, false);")
        fixture = fixture.replace("    current_tick = 1000;", """    current_tick = 1000;
#ifdef HAVE_ESPEAK
    global_settings.tts_enabled = false;
#endif""", 1)
        (WORKSPACE / "coverage_fixture.c").write_text(fixture, encoding="utf-8")
        sources = ("apps/settings.h", "apps/gui/list.c", "apps/gui/yesno.c", "apps/gui/splash.c",
                   "apps/menu.c", "apps/playlist.c", "apps/root_menu.c", "apps/playlist_viewer.c", "apps/plugin.c",
                   "tools/tests/test_tts_coverage.py", "tools/tests/test_tts_coverage.c")
        (WORKSPACE / "provenance.json").write_text(json.dumps({
            "source_project": str(ROOT), "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
            "scope": "Actual extracted UI functions and settings policy with mocked backends",
            "fixture": "Shared C fixture copied only to apply a named settings mock; source fixture unchanged",
        }, indent=2) + "\n", encoding="utf-8")
        pieces = ["#ifdef HAVE_ESPEAK\n", extract_block(
            cls.list_source, "static void gui_synclist_clear_boundary_speech("), extract_block(
            cls.list_source, "static void gui_synclist_talk_text("), extract_block(
            cls.list_source, "static void gui_synclist_talk_position("), "#endif\n"]
        for signature in (
            "static void _gui_synclist_speak_item(",
            "void gui_synclist_speak_item(",
            "static void gui_synclist_select_item_internal(",
            "void gui_synclist_select_item(",
            "void gui_synclist_set_nb_items(",
            "int  gui_synclist_get_sel_pos(",
            "void gui_synclist_set_voice_callback(",
        ):
            pieces.append(extract_block(cls.list_source, signature))
        pieces.append(cls.list_source[
            cls.list_source.index("static int simplelist_line_count"):
            cls.list_source.index("bool simplelist_show_list(")])
        pieces.append(extract_block(cls.list_source, "bool simplelist_show_list("))
        pieces.append(extract_block(cls.list_source, "void simplelist_info_init("))
        pieces.append(extract_block(cls.yesno_source, "static void talk_text_message("))
        pieces.append("static void coverage_dialog_tick(const struct text_message *main_message, "
                      "bool talk_menu, bool *repeat, long *next_tick)\n"
                      "{\n bool repeat_question = *repeat; long talked_tick = *next_tick;\n")
        pieces.append(extract_block(cls.yesno_source, "if (talk_menu && repeat_question"))
        pieces.append("*repeat = repeat_question; *next_tick = talked_tick;\n}\n")
        pieces.append(cls.splash_source[
            cls.splash_source.index("static long progress_next_tick"):
            cls.splash_source.index("#define MAXLINES")])
        pieces.extend(["#ifdef HAVE_ESPEAK\n", extract_block(
            cls.splash_source, "static void splash_talk("), "#endif\n"])
        for signature in ("static void splashvf(", "void splashf(", "void splashf_silent("):
            pieces.append(extract_block(cls.splash_source, signature))
        pieces.append(extract_block(cls.splash_source, "void splash_progress_set_delay("))
        pieces.append(extract_block(cls.splash_source, "static void splash_progress_talk("))
        pieces.append(extract_block(menu_source, "static int get_menu_selection("))
        pieces.append(extract_block(menu_source, "static int talk_menu_item(int selected_item, void *data)\n{"))
        pieces.append(extract_block(playlist_source, "static void display_playlist_count("))
        pieces.append("#ifdef HAVE_ESPEAK\n"
                      "static void coverage_database_progress(int entries, int commit_step)\n{\n"
                      "    static long talked_tick;\n"
                      "    struct { int processed_entries, commit_step; } state = {entries, commit_step}, *stat = &state;\n")
        pieces.append(extract_block(root_source, "if(talk_dynamic_enabled(&global_settings)"))
        pieces.append("}\nstatic void coverage_search_progress(int found_indicies_count)\n{\n"
                      "    static long talked_tick;\n    static int last_found_count = -1;\n")
        pieces.append(extract_block(cls.playlist_viewer_source, "if (found_indicies_count != last_found_count)"))
        pieces.append("}\n#endif\n")
        pieces.append("static int coverage_plugin_open_error(void)\n{\n"
                      "const char *plugin = \"missing-plugin.rock\";\n"
                      "void *current_plugin_handle = NULL;\n")
        pieces.append(extract_block(plugin_source, "if (current_plugin_handle == NULL)"))
        pieces.append("return 0;\n}\n")
        (WORKSPACE / "coverage_functions.h").write_text("\n".join(pieces), encoding="utf-8")

    def run_harness(self, espeak, sanitize, tts_only=False):
        mode = ("espeak" if espeak else "legacy") + ("-ubsan" if sanitize else "")
        if tts_only:
            mode += "-tts-only"
        output = WORKSPACE / mode
        output.mkdir()
        executable = output / "coverage-test"
        source = WORKSPACE / "coverage_fixture.c"
        if tts_only:
            source = output / "tts-only.c"
            source.write_text(r'''
#define main coverage_baseline_main
#include "coverage_fixture.c"
#undef main
static void enable_tts_only(void)
{
    reset();
    global_settings.talk_menu = false;
    global_settings.tts_enabled = true;
}
int main(void)
{
    enable_tts_only();
    struct gui_synclist list = make_list();
    assert(list.talk_menu);
    gui_synclist_speak_item(&list);
    assert(speech_count == 1 && strcmp(utterances[0], "Polski katalog") == 0);
    list.talk_menu = false;
    current_tick += HZ;
    _gui_synclist_speak_item(&list, false);
    assert(speech_count == 1);
    list.talk_menu = true;
    available = false;
    _gui_synclist_speak_item(&list, false);
    assert(speech_count == 1);
    available = true;
    global_settings.tts_enabled = false;
    _gui_synclist_speak_item(&list, false);
    assert(speech_count == 1);

    enable_tts_only();
    const char *strings[] = {"TTS-only menu"};
    struct menu_item_ex menu = { .flags = MT_RETURN_ID, .strings = strings };
    talk_menu_item(0, &menu);
    assert(speech_count == 1 && strcmp(utterances[0], strings[0]) == 0);

    enable_tts_only();
    splashf(0, "TTS-only notice %d", 17);
    assert(speech_count == 1 && strcmp(utterances[0], "TTS-only notice 17") == 0);

    enable_tts_only();
    progress(5, 10, "%s", "TTS-only progress");
    assert(speech_count == 1 && strstr(utterances[0], "50%"));

    enable_tts_only();
    display_playlist_count(3, (const unsigned char *)ID2P(LANG_PLAYLIST_INSERT_COUNT), true);
    assert(speech_count == 1 && strcmp(utterances[0], "3 tracks Cancel") == 0);

    enable_tts_only();
    const char *lines[] = {"TTS-only question"};
    struct text_message message = {lines, 1};
    bool repeat = true;
    long tick = current_tick - 1;
    coverage_dialog_tick(&message, talk_menus_enabled(&global_settings), &repeat, &tick);
    assert(speech_count == 1 && !repeat && strcmp(utterances[0], lines[0]) == 0);

    enable_tts_only();
    assert(coverage_plugin_open_error() == -1);
    assert(speech_count == 1 && strcmp(utterances[0], "Cannot open missing-plugin.rock") == 0);
    puts("PASS TTS-only UI independent of legacy menu setting, with local opt-out and readiness gates");
    return 0;
}
''', encoding="utf-8")
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-I", str(WORKSPACE), str(source),
            "-o", str(executable),
        ]
        if espeak:
            command.append("-DHAVE_ESPEAK")
        if sanitize:
            command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / "compile.log").write_text(
            shlex.join(command) + "\n" + compiled.stdout + compiled.stderr, encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        tested = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        (output / "result.json").write_text(json.dumps({
            "mode": mode, "returncode": tested.returncode,
            "stdout": tested.stdout, "stderr": tested.stderr,
        }, indent=2), encoding="utf-8")
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_espeak(self):
        self.run_harness(espeak=True, sanitize=False)

    def test_legacy(self):
        self.run_harness(espeak=False, sanitize=False)

    def test_espeak_ubsan(self):
        self.run_harness(espeak=True, sanitize=True)

    def test_espeak_tts_only_without_legacy_menu(self):
        self.run_harness(espeak=True, sanitize=False, tts_only=True)

    def test_espeak_tts_only_without_legacy_menu_ubsan(self):
        self.run_harness(espeak=True, sanitize=True, tts_only=True)

    def test_legacy_ubsan(self):
        self.run_harness(espeak=False, sanitize=True)

    def test_rendering_does_not_trigger_list_speech(self):
        rendering = extract_block(self.list_source, "void gui_synclist_draw(")
        self.assertNotIn("speak_item", rendering)
        self.assertNotIn("talk_text", rendering)
        self.assertNotIn("talk_spell", rendering)

    def test_progress_hook_uses_resolved_format_after_visual_throttle(self):
        progress = extract_block(self.splash_source, "void splash_progress(")
        self.assertLess(progress.index("TIME_BEFORE"), progress.index("splash_progress_talk"))
        self.assertLess(progress.index("P2STR"), progress.index("splash_progress_talk"))
        self.assertLess(progress.index("splash_progress_talk"), progress.index("FOR_NB_SCREENS"))

    def test_search_completion_remains_outside_dynamic_intermediate_gate(self):
        search = extract_block(self.playlist_viewer_source, "bool search_playlist(")
        updates = extract_block(search, "if (found_indicies_count != last_found_count)")
        self.assertIn("splashf_silent(", updates)
        self.assertNotRegex(updates, r"\bsplashf\(")
        self.assertLess(search.index(updates), search.index("cond_talk_ids_fq(LANG_ALL,"))
        self.assertNotIn("cond_talk_ids_fq(LANG_ALL,", updates)

    def test_talk_spell_sends_whole_text_before_legacy_spelling(self):
        source = (ROOT / "apps/talk.c").read_text(encoding="utf-8")
        spelling = extract_block(source, "static int _talk_spell(")
        tts = extract_block(spelling, "if (tts_is_available())")
        self.assertIn("length < len && spell[length]", tts)
        self.assertIn("tts_speak(spell, length, true)", tts)
        self.assertIn("return result;", tts)
        self.assertLess(spelling.index("tts_speak("), spelling.index("utf8decode("))

    def test_native_spelling_length_is_bounded_without_libc_strnlen(self):
        source = (ROOT / "apps/talk.c").read_text(encoding="utf-8")
        spelling = extract_block(source, "static int _talk_spell(")
        branch = extract_block(spelling, "if (tts_is_available())")
        body = branch[branch.index("{"):]
        harness = WORKSPACE / "bounded-spelling.c"
        executable = WORKSPACE / "bounded-spelling"
        harness.write_text(r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
static bool force_enqueue_next, need_shutup;
static size_t spoken_length;
static int tts_speak(const char *text, size_t length, bool enqueue)
{ (void)text; (void)enqueue; spoken_length = length; return 0; }
static int speak(const char *spell, size_t len)
''' + body + r'''
int main(void)
{
    const char bounded[] = {'a', 'b', 'c'};
    if (speak(bounded, sizeof(bounded)) || spoken_length != 3) return 1;
    if (speak("abc", 2) || spoken_length != 2) return 2;
    if (speak("abc", SIZE_MAX) || spoken_length != 3) return 3;
    if (speak("", SIZE_MAX) || spoken_length != 0) return 4;
    if (speak(bounded, 0) || spoken_length != 0) return 5;
    if (force_enqueue_next || !need_shutup) return 6;
    return 0;
}
''', encoding="utf-8")
        compiler = shlex.split(os.environ.get("CC", "cc"))
        subprocess.run(compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror",
                                  "-fsanitize=address,undefined", str(harness),
                                  "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    print(f"Coverage evidence: {WORKSPACE}", flush=True)
    unittest.main(verbosity=2)
