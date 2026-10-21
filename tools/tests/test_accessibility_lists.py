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
import uuid

from test_tts_coverage import extract_block

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ("apps/gui/list.c", "apps/gui/list.h", "apps/misc.c", "apps/misc.h", "apps/action.h", "apps/settings.h", "apps/talk.h", "apps/talk.c",
          "apps/tts.c", "apps/tts.h",
          "apps/settings_list.c", "apps/settings_list.h", "apps/menus/settings_menu.c", "apps/plugin.h",
          "apps/lang/english.lang", "apps/lang/polski.lang",
          "apps/gui/option_select.c", "apps/tree.c", "apps/gui/folder_select.c", "apps/gui/mask_select.c",
          "apps/plugins/db_folder_select.c", "apps/plugins/random_folder_advance_config.c",
          "apps/plugins/puzzles/rockbox.c",
          "tools/tests/fixtures/accessibility_lists_fixture.c", "tools/tests/test_accessibility_lists.py")
SCENARIOS = ("blocked-every-press", "wrapped-order", "arrival-is-not-crossing", "modes",
             "source-masks", "repeat-policy", "list-local-policy", "empty-and-single",
             "multi-line-and-overflow", "endpoints", "page-endpoints", "keyclick-veto")
SCENARIOS += ("live-preferences",)
SCENARIOS += ("boundary-to-row",)
SCENARIOS += ("boundary-to-muted-row",)
SCENARIOS += ("voice-only-row", "visual-label-row", "literal-and-empty-rows",
              "deferred-boundary-idle", "deferred-wrap-cancel", "deferred-wrap-idle", "wrapped-silent-row",
              "wrapped-failing-row", "deferred-sound-wrap", "cross-list-prefix")
RAPID_SCENARIOS = tuple("rapid-wrap-" + direction + suffix
                        for direction in ("up", "down")
                        for suffix in ("", "-labels", "-cancel", "-taps", "-loss"))
POSITION_SCENARIOS = ("position-callback-enabled", "position-callback-disabled",
                      "position-fallback-enabled", "position-fallback-disabled",
                      "position-groups", "position-partial-group-labels",
                      "position-empty-invalid", "position-failed-callback",
                      "position-wrapped-failed-callback", "position-voicefiles-only",
                      "position-local-mute", "position-unlabelled-row",
                      "position-missing-connector", "position-oversized-connector")
POSITION_RAPID_SCENARIOS = tuple("position-rapid-" + direction + suffix
                               for direction in ("up", "down")
                               for suffix in ("", "-labels", "-cancel", "-new-request"))


def disable_core_dumps():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class AccessibilityListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable")
        cls.inputs = {name: (ROOT / name).read_bytes() for name in INPUTS}
        cls.area = project_materials_root(ROOT) / "accessibility-list-tests" / uuid.uuid4().hex
        cls.area.mkdir(parents=True)
        source = cls.inputs["apps/gui/list.c"].decode("utf-8")
        functions = "\n".join(extract_block(source, signature) for signature in (
            "static void gui_synclist_init_display_settings(", "void gui_synclist_init(",
            "void simplelist_info_init(", "static void edge_beep(",
            "static void gui_synclist_clear_boundary_speech(",
            "static void gui_synclist_talk_text(",
            "static void gui_synclist_talk_position(",
            "static void _gui_synclist_speak_item(", "void gui_synclist_speak_item(",
            "static void gui_synclist_select_item_internal(",
            "void gui_synclist_select_item(", "static void gui_list_select_at_offset(",
            "static void gui_synclist_select_endpoint(", "bool gui_synclist_keyclick_callback("))
        misc = cls.inputs["apps/misc.c"].decode("utf-8")
        routing = misc[misc.index("static keyclick_callback keyclick_current_callback"):
                       misc.index("/* Return the ReplayGain mode")]
        fixture = cls.inputs["tools/tests/fixtures/accessibility_lists_fixture.c"].decode("utf-8")
        settings = cls.inputs["apps/settings.h"].decode("utf-8")
        position_enums = "\n".join(extract_block(text, signature).rstrip() + ";" for text, signature in (
            (settings, "enum tts_position_mode\n"),
            (cls.inputs["apps/gui/list.h"].decode("utf-8"), "enum list_position_source\n")))
        position_policy = extract_block(settings, "static inline bool talk_list_position_enabled(")
        pointer_end = re.search(r"^#define P2ID[^\n]*", settings, re.MULTILINE)
        if not pointer_end:
            raise AssertionError("Actual language-pointer provider is missing")
        pointers = settings[settings.index("#define VIRT_SIZE"):pointer_end.end()]
        timer = re.search(r"    if\(lists->scheduled_talk_tick\n.*?    return false;", source, re.DOTALL)
        if not timer or source.count(timer[0]) != 1:
            raise AssertionError("Actual deferred list dispatch tail is missing or ambiguous")
        pending = "static bool fixture_speak_pending(struct gui_synclist *lists)\n{\n" + timer[0] + "\n}\n"
        talk = cls.inputs["apps/talk.c"].decode("utf-8")
        enqueue = "\n".join(extract_block(talk, signature) for signature in (
            "void talk_force_shutup(", "void talk_shutup(", "static void do_enqueue(",
            "void talk_force_enqueue_next(", "void talk_cancel_enqueue_next("))
        talk_id = extract_block(talk, "int talk_id(")
        talk_id_tts = extract_block(talk_id, "if (tts_is_available())")
        spelling = extract_block(talk, "static int _talk_spell(")
        spelling_tts = extract_block(spelling, "if (tts_is_available())")
        tts = cls.inputs["apps/tts.c"].decode("utf-8")
        getter_source = "\n".join(extract_block(tts, signature) for signature in (
            "static int voice_index(", "const char *tts_get_voice_text("))
        voice_wrapper = extract_block(tts, "int tts_speak_id(").replace(
            "int tts_speak_id(", "static int fixture_actual_tts_speak_id(", 1)
        navigation = source[source.index("        case ACTION_STD_PREVREPEAT:"):
                            source.index("        case ACTION_TREE_PGRIGHT:")]
        navigation = ("static bool fixture_do_navigation(struct gui_synclist *lists, int *actionptr)\n"
                      "{\n    bool allow_wrap = lists->wraparound;\n"
                      "    int next_item_modifier = 1;\n    switch (*actionptr)\n    {\n" + navigation +
                      "    default: return false;\n    }\n}\n")
        boundary_labels = []
        row_labels = []
        position_labels = []
        for language in ("english", "polski"):
            catalog = cls.inputs["apps/lang/" + language + ".lang"].decode("utf-8")
            def voice_text(identifier):
                phrase = re.search(r'<phrase>\s*id: ' + identifier + r'\s.*?</phrase>', catalog, re.DOTALL)
                if not phrase:
                    raise AssertionError("Missing actual language phrase: " + identifier)
                voice = re.search(r'<voice>\s*\*: "([^"]*)"', phrase[0])
                if not voice or not voice[1]:
                    raise AssertionError("Missing actual spoken label: " + identifier)
                return voice[1]
            boundary_labels.append([voice_text(identifier) for identifier in (
                "LANG_ACCESSIBILITY_LIST_START", "LANG_ACCESSIBILITY_LIST_END")])
            row_labels.append([voice_text(identifier) for identifier in ("LANG_PLAYLISTS", "LANG_SETTINGS")])
            position_labels.append([voice_text("VOICE_OF")])
        def c_strings(table):
            return "{" + ", ".join("{" + ", ".join(json.dumps(label, ensure_ascii=False)
                                    for label in row) + "}" for row in table) + "}"
        cls.fixture = (fixture.replace("ACTUAL_KEYCLICK_SOURCE", routing)
                       .replace("ACTUAL_SIMPLELIST_STRUCT", extract_block(
                           cls.inputs["apps/gui/list.h"].decode("utf-8"), "struct simplelist_info {").rstrip() + ";")
                       .replace("ACTUAL_CONSTRUCTION_SOURCE", cls.construction_source(source))
                       .replace("ACTUAL_POSITION_ENUMS", position_enums)
                       .replace("ACTUAL_POSITION_POLICY", position_policy)
                       .replace("ACTUAL_LANGUAGE_POINTER_SOURCE", pointers)
                       .replace("ACTUAL_ENQUEUE_SOURCE", enqueue)
                       .replace("ACTUAL_TALK_ID_TTS_SOURCE", talk_id_tts)
                       .replace("ACTUAL_TALK_SPELL_TTS_SOURCE", spelling_tts)
                       .replace("ACTUAL_VOICE_TEXT_SOURCE", getter_source)
                       .replace("ACTUAL_VOICE_ID_WRAPPER", voice_wrapper)
                       .replace("ACTUAL_BOUNDARY_LABELS", c_strings(boundary_labels))
                       .replace("ACTUAL_ROW_LABELS", c_strings(row_labels))
                       .replace("ACTUAL_POSITION_LABELS", c_strings(position_labels))
                       .replace("ACTUAL_LIST_SOURCE", functions + "\n" + pending + "\n" + navigation))
        cls.results = []
        cls.case_results = []
        cls.binaries = {}
        for name, flags in (("ordinary", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"])):
            cls.binaries[name] = cls.compile(name, cls.fixture, flags)

    @classmethod
    def construction_source(cls, source):
        show = extract_block(source, "bool simplelist_show_list(")
        prefix = show[show.index("{\n") + 2:show.index("    if (info->title)")]
        pieces = ["static struct gui_synclist fixture_simplelist_construct(struct simplelist_info *info)\n{\n" +
            prefix + "    (void)action; (void)old_line_count; (void)line_count; (void)ret;\n    return lists;\n}\n", r'''
#define value_setting_get_name_cb name_row
#define tree_get_filename name_row
#define list_get_name_cb name_row
#define config_choices_formatter name_row
#define LANG_SELECT_FOLDER 1
struct settings_list { unsigned int flags; };
ACTUAL_OPTION_FLAGS
static int count_items(void *root) { (void)root; return 1; }
static const struct {
    void (*gui_synclist_init)(struct gui_synclist *, list_get_name *, void *, bool, int, struct viewport *);
    void (*simplelist_info_init)(struct simplelist_info *, char *, int, void *);
} construction_api = {gui_synclist_init, simplelist_info_init};
#define rb (&construction_api)
''']
        cases = (
            ("option", "apps/gui/option_select.c", "gui_synclist_init(&lists, value_setting_get_name_cb",
             "struct settings_list item = {.flags = flags}; const struct settings_list *setting = &item; "
             "struct viewport *parent = NULL; struct gui_synclist lists;", "lists"),
            ("tree", "apps/tree.c", "gui_synclist_init(list, &tree_get_filename",
             "int tc = 0; struct gui_synclist lists; struct gui_synclist *list = &lists; (void)id3db;", "lists"),
            ("folder", "apps/gui/folder_select.c", "simplelist_info_init(&info, str(LANG_SELECT_FOLDER)",
             "struct simplelist_info info; void *root = NULL;", "fixture_simplelist_construct(&info)"),
            ("mask", "apps/gui/mask_select.c", "simplelist_info_init(&info, P2STR(headermsg)",
             "struct simplelist_info info; int root = 0; const unsigned char *headermsg = ID2P(1);", "fixture_simplelist_construct(&info)"),
            ("plugin_folder", "apps/plugins/db_folder_select.c", "rb->simplelist_info_init(&info, header_text",
             "struct simplelist_info info; void *root = NULL; char *header_text = NULL;", "fixture_simplelist_construct(&info)"),
            ("random_folder", "apps/plugins/random_folder_advance_config.c", "rb->gui_synclist_init(&lists, list_get_name_cb",
             "struct gui_synclist lists; void *scan = NULL;", "lists"),
            ("puzzle", "apps/plugins/puzzles/rockbox.c", "rb->gui_synclist_init(&list, &config_choices_formatter",
             "struct gui_synclist list; const char *list_str = NULL;", "list"),
        )
        for name, path, marker, declarations, result in cases:
            text = cls.inputs[path].decode("utf-8")
            start = text.index(marker)
            end = text.index(";\n", start) + 2
            if text[end:].startswith("#ifdef HAVE_ESPEAK\n"):
                end = text.index("#endif\n", end) + len("#endif\n")
            parameters = "bool id3db" if name == "tree" else "unsigned int flags" if name == "option" else "void"
            fragment = text[start:end]
            if name == "folder":
                fragment = fragment.replace("str(LANG_SELECT_FOLDER)", "(char *)str(LANG_SELECT_FOLDER)")
            pieces.append("static struct gui_synclist fixture_construct_" + name + "(" + parameters + ")\n{\n" +
                          declarations + "\n" + fragment + "    return " + result + ";\n}\n")
        pieces.append("#undef rb\n")
        flags = cls.inputs["apps/settings_list.h"].decode("utf-8")
        flags = re.sub(r"/\*.*?\*/", "", flags, flags=re.S)
        definitions = "\n".join(re.search(r"^#define " + name + r"\s+[^\n]*", flags, re.M).group()
            for name in ("F_T_INT", "F_T_BOOL", "F_CHOICE_SETTING", "F_T_SOUND", "F_INT_SETTING", "F_TABLE_SETTING", "F_BOOL_SETTING"))
        return "\n".join(pieces).replace("ACTUAL_OPTION_FLAGS", definitions)

    @classmethod
    def compile(cls, name, content, flags=()):
        source = cls.area / (name + ".c")
        source.write_text(content, encoding="utf-8")
        binary = cls.area / (name + (".exe" if os.name == "nt" else ".bin"))
        command = cls.compiler + ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror",
            "-UNDEBUG", *flags, str(source), "-o", str(binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        cls.results.append(dict(kind="compile", name=name, command=command, exit=result.returncode,
                                stdout=result.stdout, stderr=result.stderr, passed=result.returncode == 0))
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    @classmethod
    def run_case(cls, binary, scenario, fails=False):
        command = [str(binary), scenario]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15,
                env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"),
                preexec_fn=disable_core_dumps if os.name != "nt" else None,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except BaseException as error:
            cls.results.append(dict(kind="run-exception", command=command, scenario=scenario,
                                    error=repr(error), expected_failure=fails, passed=False))
            raise
        passed = (result.returncode == 101 and "CHECK_FAILED " in result.stderr) if fails else result.returncode == 0
        cls.results.append(dict(kind="run", binary=str(binary), scenario=scenario, exit=result.returncode,
                                stdout=result.stdout, stderr=result.stderr, expected_failure=fails, passed=passed))
        if not passed:
            raise AssertionError(scenario + "\n" + result.stdout + result.stderr)

    def test_real_list_movement_speech_order_and_feedback(self):
        for mode, binary in self.binaries.items():
            for scenario in SCENARIOS:
                with self.subTest(mode=mode, scenario=scenario):
                    self.run_case(binary, scenario)

    def test_rapid_wrap_speaks_destination_and_keeps_later_selection(self):
        for mode, binary in self.binaries.items():
            for scenario in RAPID_SCENARIOS:
                with self.subTest(mode=mode, scenario=scenario):
                    self.run_case(binary, scenario)

    def test_position_gates_group_counts_and_unsuccessful_rows(self):
        for mode, binary in self.binaries.items():
            for scenario in POSITION_SCENARIOS:
                with self.subTest(mode=mode, scenario=scenario):
                    self.run_case(binary, scenario)

    def test_all_position_modes_and_real_list_construction_roles(self):
        for mode, binary in self.binaries.items():
            for scenario in ("position-mode-matrix", "construction-roles"):
                with self.subTest(mode=mode, scenario=scenario):
                    self.run_case(binary, scenario)

    def test_semantic_role_causal_mutants(self):
        for name in ("option", "tree", "folder", "plugin_folder", "random_folder"):
            block = extract_block(self.fixture, "static struct gui_synclist fixture_construct_" + name + "(")
            modified, count = re.subn(r"^.*position_source = .*;\n", "    (void)0;\n", block, count=1, flags=re.M)
            self.assertEqual(count, 1)
            with self.subTest(mutant=name):
                self.run_case(self.compile("role-" + name, self.fixture.replace(block, modified, 1)),
                              "construction-roles", fails=True)
        for name, before, after, scenario in (
            ("simplelist-role-forwarding", "lists.position_source = info->position_source;", "", "construction-roles"),
            ("list-role-default", "gui_list->position_source = LIST_POSITION_INTERFACE;", "", "construction-roles"),
            ("simplelist-role-default", "info->position_source = LIST_POSITION_INTERFACE;", "", "construction-roles"),
            ("interface-includes-sliders", "return source != LIST_POSITION_FILE;", "return source == LIST_POSITION_INTERFACE;", "position-mode-matrix"),
            ("default-speaks-sliders", "return source != LIST_POSITION_SLIDER;", "return true;", "position-mode-matrix"),
            ("enum-treated-as-slider", "!(setting->flags & F_CHOICE_SETTING) &&", "true &&", "construction-roles"),
        ):
            self.assertEqual(self.fixture.count(before), 1)
            with self.subTest(mutant=name):
                self.run_case(self.compile(name, self.fixture.replace(before, after, 1)), scenario, fails=True)

    def test_position_rapid_wrap_order_and_new_request_cancellation(self):
        for mode, binary in self.binaries.items():
            for scenario in POSITION_RAPID_SCENARIOS:
                with self.subTest(mode=mode, scenario=scenario):
                    self.run_case(binary, scenario)

    def test_actual_voice_text_lookup_and_speak_wrapper(self):
        for mode, binary in self.binaries.items():
            with self.subTest(mode=mode):
                self.run_case(binary, "voice-text-lookup")
        self.assertIn("const char *tts_get_voice_text(int32_t id);", self.inputs["apps/tts.h"].decode("utf-8"))
        helper = extract_block(self.fixture, "static void gui_synclist_talk_position(")
        self.assertNotIn("talk_number(", helper)
        self.assertNotIn("talk_id(", helper)
        self.assertEqual(helper.count("talk_spell("), 1)

    def test_position_causal_mutants(self):
        mutations = (
            ("position-disabled-gate", "!talk_list_position_enabled(&global_settings, lists->position_source) ||",
             "", "position-callback-disabled"),
            ("position-readiness-gate", " ||\n        !tts_is_available()",
             "", "position-voicefiles-only"),
            ("position-zero-based", "lists->selected_item / item_size + 1, connector,",
             "lists->selected_item / item_size, connector,", "position-callback-enabled"),
            ("position-raw-row", "lists->selected_item / item_size + 1, connector,",
             "lists->selected_item + 1, connector,", "position-groups"),
            ("position-truncated-total", "(lists->nb_items - 1) / item_size + 1",
             "lists->nb_items / item_size", "position-groups"),
            ("position-zero-size", "int item_size = MAX(1, lists->selected_size);",
             "int item_size = lists->selected_size > 0 ? lists->selected_size : 2;", "position-groups"),
            ("position-replaces-row", "talk_spell(text, true);",
             "talk_spell(text, false);", "position-callback-enabled"),
            ("position-failed-row", "if (speech_result >= 0)",
             "if (speech_result >= -1)", "position-failed-callback"),
            ("position-missing-of", "tts_get_voice_text(VOICE_OF)",
             "tts_get_voice_text(VOICE_BLANK)", "position-fallback-enabled"),
            ("position-local-mute", "!lists->talk_menu ||\n        ", "", "position-local-mute"),
            ("position-truncated-phrase", "length >= 0 && (size_t)length < sizeof(text)",
             "length >= 0", "position-oversized-connector"),
            ("position-empty-connector", "!connector || !*connector",
             "!connector", "position-missing-connector"),
        )
        helper = extract_block(self.fixture, "static void gui_synclist_talk_position(")
        for name, before, after, scenario in mutations:
            with self.subTest(mutant=name, scenario=scenario):
                target = self.fixture if name == "position-failed-row" else helper
                self.assertEqual(target.count(before), 1)
                modified = target.replace(before, after, 1)
                content = modified if target is self.fixture else self.fixture.replace(helper, modified, 1)
                self.run_case(self.compile(name + "-mutant", content),
                              scenario, fails=True)

    def test_causal_mutant_rejects_deferred_wrap_destination(self):
        condition = "if (!immediate && ((lists->scheduled_talk_tick &&"
        self.assertEqual(self.fixture.count(condition), 1)
        delayed = self.fixture.replace(condition,
            "(void)immediate;\n    if ((lists->scheduled_talk_tick &&", 1)
        delayed = delayed.replace("lists->last_talked_tick + HZ/5))))",
                                  "lists->last_talked_tick + HZ/5)))", 1)
        binary = self.compile("deferred-wrap-mutant", delayed)
        for scenario in RAPID_SCENARIOS:
            with self.subTest(scenario=scenario):
                self.run_case(binary, scenario, fails=True)

    def test_causal_mutant_rejects_stale_row_before_sound_only_wrap(self):
        cancellation = "gui_synclist_clear_boundary_speech(gui_list);\n            talk_shutup();"
        self.assertEqual(self.fixture.count(cancellation), 1)
        stale = self.fixture.replace(cancellation, "gui_synclist_clear_boundary_speech(gui_list);", 1)
        binary = self.compile("stale-sound-wrap-mutant", stale)
        for scenario in RAPID_SCENARIOS:
            if scenario.endswith("-loss"):
                continue
            with self.subTest(scenario=scenario):
                self.run_case(binary, scenario, fails=True)

    def test_causal_mutants_reject_bounce_cooldown_and_missing_feedback(self):
        signature = "static void edge_beep(struct gui_synclist * gui_list, bool wrap, bool at_end)\n{"
        self.assertEqual(self.fixture.count(signature), 1)
        cooldown = self.fixture.replace(signature, signature + "\n"
            "static long last_bounce_tick;\n"
            "if (!wrap && current_tick < last_bounce_tick + HZ / 4) return;\n"
            "last_bounce_tick = current_tick;", 1)
        self.run_case(self.compile("cooldown-mutant", cooldown), "blocked-every-press", fails=True)
        before = "edge_beep(gui_list, allow_wrap, at_end);"
        self.assertEqual(self.fixture.count(before), 1)
        missing = self.fixture.replace(before, "if (0) edge_beep(gui_list, allow_wrap, at_end);", 1)
        self.run_case(self.compile("missing-boundary-mutant", missing), "wrapped-order", fails=True)

    def test_settings_use_existing_wrap_and_distinct_feedback_option(self):
        settings = self.inputs["apps/settings_list.c"].decode("utf-8")
        menu = self.inputs["apps/menus/settings_menu.c"].decode("utf-8")
        self.assertEqual(settings.count('"list boundary feedback"'), 1)
        self.assertIn('list_boundary_feedback, LANG_ACCESSIBILITY_LIST_BOUNDARY, 1,', settings)
        self.assertRegex(menu, r'&list_boundary_feedback_item\b')
        self.assertIn('global_settings.list_wraparound', self.fixture)
        self.assertIn('#define PLUGIN_API_VERSION 0xe006', self.inputs["apps/plugin.h"].decode("utf-8"))
        for language in ("english", "polski"):
            text = self.inputs["apps/lang/" + language + ".lang"].decode("utf-8")
            for label in ("LANG_ACCESSIBILITY_LIST_START", "LANG_ACCESSIBILITY_LIST_END",
                          "LANG_ACCESSIBILITY_ACTION_PAGE_FIRST", "LANG_ACCESSIBILITY_ACTION_PAGE_LAST"):
                self.assertEqual(text.count("id: " + label + "\n"), 1)

    def test_causal_mutants_reject_unsafe_virtual_rows_and_stale_boundary_state(self):
        identifiers = ("int identifier = P2ID((const unsigned char *)text);\n"
                       "            if (identifier >= 0)\n"
                       "                talk_id(identifier, true);\n"
                       "            else if (*text != '\\0')")
        self.assertEqual(self.fixture.count(identifiers), 1)
        unsafe = self.fixture.replace(identifiers,
            "text = P2STR((const unsigned char *)text);\n            if (*text != '\\0')", 1)
        self.run_case(self.compile("unsafe-voice-row-mutant", unsafe), "voice-only-row", fails=True)
        timer = "gui_list->boundary_speech_pending = true;\n            gui_list->scheduled_talk_tick = 0;"
        self.assertEqual(self.fixture.count(timer), 2)
        stale = self.fixture.replace(timer, "gui_list->boundary_speech_pending = true;")
        self.run_case(self.compile("stale-row-timer-mutant", stale), "deferred-boundary-idle", fails=True)
        scope = "if (preserve_boundary)\n        {\n            talk_cancel_enqueue_next();"
        self.assertEqual(self.fixture.count(scope), 1)
        leaked = self.fixture.replace(scope, "if (preserve_boundary)\n        {", 1)
        self.run_case(self.compile("leaked-enqueue-mutant", leaked), "wrapped-silent-row", fails=True)
        selection = "gui_synclist_select_item_internal(gui_list, new_selection, wrapping);"
        self.assertEqual(self.fixture.count(selection), 1)
        lost = self.fixture.replace(selection,
            "gui_synclist_select_item_internal(gui_list, new_selection, false);", 1)
        self.run_case(self.compile("lost-wrap-prefix-mutant", lost), "wrapped-order", fails=True)

    def test_list_speech_calls_are_declared_in_real_public_headers(self):
        source = self.inputs["apps/gui/list.c"].decode("utf-8")
        public = self.inputs["apps/talk.h"].decode("utf-8") + self.inputs["apps/settings.h"].decode("utf-8")
        calls = set(re.findall(r'\btalk_[a-z_]+(?=\s*\()', re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)))
        declarations = set(re.findall(r'\btalk_[a-z_]+(?=\s*\()', public))
        self.assertFalse(calls - declarations, "List fixtures must not invent private talk APIs: " + repr(calls - declarations))

    def tearDown(self):
        result = self._outcome.result
        failed = [detail for case, detail in result.failures + result.errors
                  if case is self or getattr(case, "test_case", None) is self]
        self.case_results.append(dict(test=self.id(), passed=not failed, failures=failed))

    @classmethod
    def tearDownClass(cls):
        unchanged = all((ROOT / name).read_bytes() == data for name, data in cls.inputs.items())
        report = dict(source_project=str(ROOT), platform=sys.platform, inputs_unchanged=unchanged,
            source_sha256={name: hashlib.sha256(data).hexdigest() for name, data in cls.inputs.items()},
            rapid_scenarios=RAPID_SCENARIOS,
            position_scenarios=POSITION_SCENARIOS + POSITION_RAPID_SCENARIOS,
            rapid_matrix=dict(languages=["english", "polski"], feedback_modes=list(range(4)),
                              wraparound=[False, True], repeat=[False, True], sound=[False, True],
                              gaps_ticks=list(range(22)), hz=100),
            cases=cls.results, test_results=cls.case_results,
            passed=unchanged and bool(cls.results) and bool(cls.case_results) and
                all(item["passed"] for item in cls.results + cls.case_results),
            limitations=["Extracted real list, navigation cases, keyclick and talk cancellation/enqueue C; controlled TTS/drawing/time",
                         "Not physical audio, actual eSpeak, full GUI or private custom plugin acceptance"])
        (cls.area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("List evidence:", cls.area, flush=True)
        if not unchanged:
            raise AssertionError("List inputs changed during validation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
