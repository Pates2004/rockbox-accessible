import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
WORKSPACE = project_materials_root(ROOT) / "tts-plugin-policy-tests" / RUN


def extract_block(source, signature):
    start = source.index(signature)
    masked = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        lambda match: " " * len(match.group()), source, flags=re.DOTALL)
    opening = masked.index("{", start)
    while ";" in masked[start:opening]:
        start = source.index(signature, start + len(signature))
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


def with_menu_policy(source):
    declaration = re.search(r"struct user_settings \{[^\n]+\};", source)
    if declaration is None:
        raise ValueError("The fixture must declare struct user_settings on one line")
    settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
    policy = extract_block(settings, "static inline bool talk_tts_enabled(")
    policy += extract_block(settings, "static inline bool talk_menus_enabled(")
    return source[:declaration.end()] + "\n" + policy + source[declaration.end():]


PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#define HZ 100
#define LCD_WIDTH 320
#define MAX_PATH 260
#define MIN(first, second) ((first) < (second) ? (first) : (second))
#define UNIT_TIME 1
#define ACTION_GET 1
#define NOICON 0
#define NUM_FILE_PROPERTIES 5
#define NUM_PLAYLIST_PROPERTIES 6
#define NUM_DIR_PROPERTIES 4
#define ID2P(identifier) ((const unsigned char *)(intptr_t)(-(identifier) - 1))
#define P2ID(pointer) ((intptr_t)(pointer) < 0 ? -(intptr_t)(pointer) - 1 : -1)
struct user_settings { bool talk_menu; ESPEAK_FIELD int talk_file, talk_dir, talk_mixer_amp; bool talk_file_clip, talk_dir_clip, talk_filetype; };
static struct user_settings settings;
static int calls, stop_calls, filename_calls, directory_calls;
static bool last_enqueue, disable_menu_after_spell, disable_tts_after_spell;
static char spoken[2048], line[2048];
static int speak_id(int32_t identifier, bool enqueue)
{
    (void)identifier;
    last_enqueue = enqueue;
    calls++;
    return 0;
}
static int speak_number(long value, bool enqueue)
{
    (void)value;
    return speak_id(0, enqueue);
}
static int speak_value(long value, int unit, int decimals, bool enqueue)
{
    assert(unit == UNIT_TIME && decimals == 0);
    return speak_number(value, enqueue);
}
static int speak_text(const char *text, bool enqueue)
{
    assert(text && strlen(spoken) + strlen(text) < sizeof(spoken));
    strcat(spoken, text);
    if (disable_menu_after_spell)
        settings.talk_menu = false;
#ifdef HAVE_ESPEAK
    if (disable_tts_after_spell)
        settings.tts_enabled = false;
#endif
    return speak_id(0, enqueue);
}
static void speak_time(const struct tm *value, bool enqueue)
{
    assert(value && value->tm_hour == 12 && value->tm_min == 34);
    speak_id(0, enqueue);
}
static void speak_date(const struct tm *value, bool enqueue)
{
    assert(value);
    speak_id(0, enqueue);
}
static int speak_file(const char *directory, const char *filename,
                      const long *prefix, bool enqueue)
{
    assert(directory && !strcmp(directory, "/Music"));
    assert(filename && !strcmp(filename, "natural-name.mp3") && !prefix);
    filename_calls++;
    return speak_text(filename, enqueue);
}
static int speak_path(const char *path, bool enqueue)
{
    assert(path && !strcmp(path, "/Music"));
    directory_calls++;
    return speak_text(path, enqueue);
}
static void stop_speech(void) { stop_calls++; }
struct gui_synclist { int (*voice)(int, void *); int count; };
static void list_init(struct gui_synclist *list,
                      const char *(*name)(int, void *, char *, size_t),
                      void *data, bool scroll, int selection_size, void *viewport)
{
    assert(name && data && !scroll && selection_size == 2 && !viewport);
    memset(list, 0, sizeof(*list));
}
static void list_title(struct gui_synclist *list, const char *title, int icon)
{
    assert(list && title && icon == NOICON);
}
static void list_voice(struct gui_synclist *list, int (*voice)(int, void *))
{
    list->voice = voice;
}
static void list_count(struct gui_synclist *list, int count) { list->count = count; }
static const char *language_string(int identifier) { (void)identifier; return "Properties"; }
static size_t copy_string(char *destination, const char *source, size_t size)
{
    size_t length = strlen(source);
    if (size) {
        size_t copied = MIN(length, size - 1);
        memcpy(destination, source, copied);
        destination[copied] = 0;
    }
    return length;
}
static char *do_action(int action, char *value, int index)
{
    assert(action == ACTION_GET && !value && index == 0);
    return line;
}
static struct {
    struct user_settings *global_settings;
    int (*talk_id)(int32_t, bool);
    int (*talk_number)(long, bool);
    int (*talk_value_decimal)(long, int, int, bool);
    int (*talk_spell)(const char *, bool);
    int (*talk_file_or_spell)(const char *, const char *, const long *, bool);
    int (*talk_fullpath)(const char *, bool);
    void (*talk_time)(const struct tm *, bool);
    void (*talk_date)(const struct tm *, bool);
    void (*talk_shutup)(void);
    size_t (*strlen)(const char *);
    void *(*memcpy)(void *, const void *, size_t);
    size_t (*strlcpy)(char *, const char *, size_t);
    const char *(*str)(int);
    void (*gui_synclist_init)(struct gui_synclist *, const char *(*)(int, void *, char *, size_t),
                              void *, bool, int, void *);
    void (*gui_synclist_set_title)(struct gui_synclist *, const char *, int);
    void (*gui_synclist_set_voice_callback)(struct gui_synclist *, int (*)(int, void *));
    void (*gui_synclist_set_nb_items)(struct gui_synclist *, int);
} api = {
    &settings, speak_id, speak_number, speak_value, speak_text, speak_file,
    speak_path, speak_time, speak_date, stop_speech, strlen, memcpy,
    copy_string, language_string, list_init, list_title, list_voice, list_count
};
static __typeof__(api) *rb = &api;
struct dices { int values[12]; int total, nb_dices, nb_sides; };
static int current, alarms[2] = {12, 34}, line_count = 1;
static int props_type;
enum { PROPS_FILE, PROPS_PLAYLIST, PROPS_DIR };
struct dir_stats { int dir_count, file_count; };
static struct gui_synclist properties_lists;
static struct tm tm;
static unsigned long display_size;
static int32_t lang_size_unit;
static char str_dirname[MAX_PATH] = "/Music";
static char str_filename[MAX_PATH] = "natural-name.mp3";
static const unsigned char *props_file[] = {
    ID2P(LANG_PROPERTIES_PATH), (const unsigned char *)str_dirname,
    ID2P(LANG_PROPERTIES_FILENAME), (const unsigned char *)str_filename
};
static const unsigned char *props_dir[] = {
    ID2P(LANG_PROPERTIES_PATH), (const unsigned char *)str_dirname
};
static const char *p2str(const unsigned char *text) { return (const char *)text; }
#define ARRAY_SIZE(values) (sizeof(values) / sizeof((values)[0]))
static struct { bool separator, talk; int col_width, hidecol_flags; } gConfig;
struct printcell_data_t { int view_lastcol; };
static int printcell_get_column_selected(void) { return 2; }
static char *printcell_get_title_text(int column, char *buffer, size_t size)
{
    assert(column == 2);
    copy_string(buffer, "Title", size);
    return buffer;
}
static char *printcell_get_column_text(int column, char *buffer, size_t size)
{
    assert(column == 2);
    copy_string(buffer, "Natural track name", size);
    return buffer;
}
'''


SUFFIX = r'''
static void reset_speech(void)
{
    calls = stop_calls = filename_calls = directory_calls = 0;
    spoken[0] = 0;
    disable_menu_after_spell = disable_tts_after_spell = false;
}
int main(void)
{
    int rows = 0;
    for (int menu = 0; menu <= 1; menu++) {
        for (int tts = 0; tts <= 1; tts++) {
            for (int files = 0; files <= 2; files++) {
                for (int directories = 0; directories <= 2; directories++) {
                    for (int clips = 0; clips <= 1; clips++) {
                        for (int types = 0; types <= 1; types++) {
                            for (int volume = 0; volume <= 1; volume++) {
                                settings.talk_menu = menu;
#ifdef HAVE_ESPEAK
                                settings.tts_enabled = tts;
                                bool enabled = menu || tts;
#else
                                (void)tts;
                                bool enabled = menu;
#endif
                                settings.talk_file = files;
                                settings.talk_dir = directories;
                                settings.talk_file_clip = clips;
                                settings.talk_dir_clip = !clips;
                                settings.talk_filetype = types;
                                settings.talk_mixer_amp = volume ? 65536 : 0;
                                assert(talk_menus_enabled(&settings) == enabled);
                                reset_speech();
                                struct dices dice = { .values = {3, 4}, .total = 7, .nb_dices = 2 };
                                dice_speak(&dice);
                                assert(calls == (enabled ? 5 : 0));
                                reset_speech();
                                timer_ctx_t timer = { .set_minutes = 2, .set_seconds = 34,
                                                      .state = STATE_SETUP };
                                countdown_talk_selection(&timer);
                                countdown_talk_state(&timer);
                                countdown_cleanup();
                                assert(calls == (enabled ? 6 : 0));
                                assert(stop_calls == enabled);
                                reset_speech();
                                alarm_talk_field();
                                alarm_talk_time(false);
                                assert(calls == (enabled ? 7 : 0));
                                reset_speech();
                                strcpy(line, "Natural editor line");
                                assert(speak_editor_line(0, NULL) == 0);
                                assert(calls == enabled);
                                assert(!enabled || !strcmp(spoken, line));
                                assert(speak_editor_line(-1, NULL) == 0);
                                assert(speak_editor_line(1, NULL) == 0);
                                assert(calls == enabled);
                                reset_speech();
                                struct dir_stats stats = {0};
                                props_type = PROPS_FILE;
                                setup_properties_list(&stats);
                                assert(properties_lists.count == 10);
                                assert(!!properties_lists.voice == enabled);
                                if (properties_lists.voice) {
                                    assert(properties_lists.voice(0, &stats) == 0);
                                    assert(properties_lists.voice(2, &stats) == 0);
                                }
                                assert(filename_calls == enabled && directory_calls == enabled);
                                assert(!enabled || !strcmp(spoken, "/Musicnatural-name.mp3"));
                                reset_speech();
                                config_set_defaults();
                                assert(gConfig.talk == enabled);
                                struct printcell_data_t cell = { .view_lastcol = 2 };
                                assert(list_voice_cb(0, &cell) == (enabled ? 0 : -1));
                                assert(calls == enabled);
                                gConfig.talk = false;
                                reset_speech();
                                assert(list_voice_cb(0, &cell) == -1 && calls == 0);
                                rows++;
                            }
                        }
                    }
                }
            }
        }
    }
#ifdef HAVE_ESPEAK
    settings.talk_menu = false;
    settings.tts_enabled = true;
    memset(line, 'a', sizeof(line) - 1);
    line[sizeof(line) - 1] = 0;
    reset_speech();
    assert(speak_editor_line(0, NULL) == 0 && calls == 3);
    assert(!strcmp(spoken, line) && last_enqueue);
    settings.talk_menu = true;
    reset_speech();
    disable_menu_after_spell = true;
    assert(speak_editor_line(0, NULL) == 0 && calls == 3);
    assert(!settings.talk_menu && !strcmp(spoken, line));
    reset_speech();
    disable_tts_after_spell = true;
    assert(speak_editor_line(0, NULL) == 0 && calls == 1);
    assert(strlen(spoken) == 768);
#endif
    printf("PASS: %d policy rows; dice, countdown, alarm, editor, properties, Last.fm opt-out\n", rows);
    return 0;
}
'''


class PluginPolicyTests(unittest.TestCase):
    def test_actual_plugin_policy_matrix(self):
        selected = {
            "dice.c": ("static void dice_speak(",),
            "countdown_timer.c": ("static void countdown_talk_selection(",
                                  "static void countdown_talk_state(",
                                  "static void countdown_cleanup("),
            "alarmclock.c": ("static void alarm_talk_field(", "static void alarm_talk_time("),
            "text_editor.c": ("static int speak_editor_line(",),
            "properties.c": ("static const char * get_props(",
                             "static int speak_property_selection(",
                             "static void setup_properties_list("),
            "lastfm_scrobbler_viewer.c": ("static void config_set_defaults(",
                                          "static int list_voice_cb("),
        }
        sources = {name: (ROOT / "apps/plugins" / name).read_text(encoding="utf-8")
                   for name in selected}
        functions = "\n".join(extract_block(sources[name], signature)
                              for name, signatures in selected.items() for signature in signatures)
        countdown = sources["countdown_timer.c"]
        declarations = countdown[countdown.index("typedef enum {"):
                                 countdown.index("static void countdown_talk_selection(")]
        labels = sorted(set(re.findall(r"\b(?:LANG|VOICE)_[A-Z0-9_]+\b", PREFIX + functions)))
        labels = "enum { " + ", ".join(labels) + " };\n"
        paths = [ROOT / "apps/settings.h"]
        paths.extend(ROOT / "tools/tests" / name for name in (
            "test_tts_plugin_policy.py", "test_tts_plugin_dice.py", "test_tts_plugin_lists.py",
            "test_tts_plugin_timers.py", "test_tts_plugin_utilities.py"))
        paths.extend(sorted((ROOT / "apps/plugins").rglob("*.c")))
        provenance = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in paths}
        WORKSPACE.mkdir(parents=True)
        (WORKSPACE / "inputs.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        for espeak in (False, True):
            for sanitize in (False, True):
                mode = ("espeak" if espeak else "legacy") + ("-ubsan" if sanitize else "")
                with self.subTest(mode=mode):
                    output = WORKSPACE / mode
                    output.mkdir()
                    source = output / "policy.c"
                    prefix = PREFIX.replace("ESPEAK_FIELD", "bool tts_enabled;" if espeak else "")
                    source.write_text(labels + with_menu_policy(prefix) + declarations + functions + SUFFIX,
                                      encoding="utf-8")
                    executable = output / "policy-test"
                    command = shlex.split(os.environ.get("CC", "cc")) + [
                        "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-pointer-sign", str(source), "-o", str(executable)]
                    if espeak:
                        command.append("-DHAVE_ESPEAK")
                    if sanitize:
                        command.extend(["-fsanitize=undefined", "-fno-sanitize-recover=all"])
                    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    (output / "compile.log").write_text(shlex.join(command) + "\n" + compiled.stdout +
                                                        compiled.stderr, encoding="utf-8")
                    self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                    tested = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
                    (output / "result.json").write_text(json.dumps({
                        "mode": mode, "returncode": tested.returncode,
                        "stdout": tested.stdout, "stderr": tested.stderr,
                        "harness_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                    }, indent=2), encoding="utf-8")
                    self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
                    self.assertEqual(tested.stderr, "")
        for name, expected in provenance.items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected, name)

    def test_no_recorded_menu_gate_remains_in_plugins(self):
        for suffix in ("*.c", "*.h", "*.lua"):
            for path in (ROOT / "apps/plugins").rglob(suffix):
                with self.subTest(path=str(path.relative_to(ROOT))):
                    source = path.read_text(encoding="utf-8", errors="replace")
                    self.assertNotRegex(source, r"global_settings\s*->\s*talk_menu\b")
                    self.assertNotRegex(source, r"global_settings\s*->\s*talk_(?:(?:file|dir)(?:_clip)?|filetype|mixer_amp)\b")

    def test_filename_api_calls_and_local_choice_are_preserved(self):
        filenames = {
            "properties.c": ("rb->talk_fullpath(str_dirname, true)",
                             "rb->talk_file_or_spell(str_dirname, str_filename, NULL, true)"),
            "open_plugins.c": ("rb->talk_fullpath(op_entry.path, true)",
                               "rb->talk_fullpath(op_entry.param, true)"),
            "mikmod/mikmod.c": ("rb->talk_file_or_spell(NULL, filename, NULL, true)",),
            "text_viewer/text_viewer.c": ("rb->talk_file_or_spell(NULL, file, NULL, true)",),
        }
        for name, calls in filenames.items():
            source = (ROOT / "apps/plugins" / name).read_text(encoding="utf-8")
            for call in calls:
                with self.subTest(plugin=name, call=call):
                    self.assertIn(call, source)
        lastfm = (ROOT / "apps/plugins/lastfm_scrobbler_viewer.c").read_text(encoding="utf-8")
        self.assertIn("if (!gConfig.talk)", extract_block(lastfm, "static int list_voice_cb("))
        self.assertIn("configfile_load(", lastfm)
        self.assertIn("&gConfig.talk", lastfm)


if __name__ == "__main__":
    unittest.main(verbosity=2)
