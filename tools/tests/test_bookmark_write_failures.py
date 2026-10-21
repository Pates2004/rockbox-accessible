import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest

import test_text_bookmarks as bookmarks
from test_tts_coverage import extract_block


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = bookmarks._project_materials_root(ROOT) / "bookmark-failure-20261011"


CASES = r'''
static const struct text_bookmark retry_position = { 25, 100, 7, 2 };

static void test_collision_recovery(void)
{
    const char *target = "/books/retry.txt.bmark";
    const char *stale = "/books/retry.txt.bmark.tmp";
    put(target, "original\r\n");
    put(stale, "interrupted save\n");
    global_settings.usemrb = BOOKMARK_NO;
    assert(bookmark_text_create_ex("/books/retry.txt", &retry_position) == TEXT_BOOKMARK_SAVED);
    assert(bookmark_text_create("/books/retry.txt", &retry_position));
    char buffer[4096];
    get(target, buffer, sizeof(buffer));
    assert(!strcmp(buffer, "T1;25;100;2;7;/books/retry.txt\noriginal\r\n"));
    unchanged(stale, "interrupted save\n", 17);
    assert(bookmark_text_create("/books/retry.txt", &retry_position));
    unchanged(stale, "interrupted save\n", 17);
    assert(get_bookmark_count(target) == 2);
    assert(!file_exists("/books/retry.txt.bmark.t01"));
    assert(mock_remove(stale) == 0);
    puts("text sidecar stale temporary recovery and repeated save passed");

    put(RECENT_BOOKMARK_FILE, "recent original\n");
    put(RECENT_BOOKMARK_FILE ".tmp", "recent interrupted\n");
    global_settings.usemrb = BOOKMARK_YES;
    assert(bookmark_text_create_ex("/books/retry.txt", &retry_position) == TEXT_BOOKMARK_SAVED);
    assert(bookmark_text_create("/books/retry.txt", &retry_position));
    assert(bookmark_text_create("/books/retry.txt", &retry_position));
    unchanged(RECENT_BOOKMARK_FILE ".tmp", "recent interrupted\n", 19);
    get(RECENT_BOOKMARK_FILE, buffer, sizeof(buffer));
    assert(!strcmp(buffer, "T1;25;100;2;7;/books/retry.txt\nrecent original\n"));
    assert(!file_exists(RECENT_BOOKMARK_FILE ".t01"));
    assert(mock_remove(RECENT_BOOKMARK_FILE ".tmp") == 0);
    puts("recent-list stale temporary recovery and mixed preservation passed");
}

static void test_slot_exhaustion(void)
{
    const char *target = "/books/full.txt.bmark";
    put(target, "keep original\n");
    for (unsigned int slot = 0; slot < 16; slot++)
    {
        char temporary[MAX_PATH];
        if (!slot) snprintf(temporary, sizeof(temporary), "%s.tmp", target);
        else snprintf(temporary, sizeof(temporary), "%s.t%02x", target, slot);
        put(temporary, "keep recovery\n");
    }
    global_settings.usemrb = BOOKMARK_NO;
    assert(bookmark_text_create_ex("/books/full.txt", &retry_position) == TEXT_BOOKMARK_FAILED);
    assert(!bookmark_text_create("/books/full.txt", &retry_position));
    unchanged(target, "keep original\n", 14);
    for (unsigned int slot = 0; slot < 16; slot++)
    {
        char temporary[MAX_PATH];
        if (!slot) snprintf(temporary, sizeof(temporary), "%s.tmp", target);
        else snprintf(temporary, sizeof(temporary), "%s.t%02x", target, slot);
        unchanged(temporary, "keep recovery\n", 14);
        assert(mock_remove(temporary) == 0);
    }
    assert(bookmark_text_create("/books/full.txt", &retry_position));
    puts("bounded exhausted-slot failure preserves all originals and recovers passed");
}

static void test_first_save_partial_result(void)
{
    const char *paths[] = { "/books/new-ex.txt", "/books/new-legacy.txt" };
    for (unsigned int api = 0; api < 2; api++)
    {
        char filename[MAX_PATH];
        assert(text_bookmark_file_name(filename, sizeof(filename), paths[api]));
        assert(!file_exists(filename));
        put(RECENT_BOOKMARK_FILE, "recent original\n");
        global_settings.usemrb = BOOKMARK_YES;
        scoped_failure_path = RECENT_BOOKMARK_FILE;
        scoped_failure_write = true;
        scoped_failure_errno = EACCES;
        scoped_open_calls = 0;
        if (api)
            assert(!bookmark_text_create(paths[api], &retry_position));
        else
            assert(bookmark_text_create_ex(paths[api], &retry_position) ==
                   TEXT_BOOKMARK_SAVED_LOCAL_ONLY);
        assert(scoped_open_calls == 1 && !open_descriptors);
        scoped_failure_path = NULL;
        assert(get_bookmark_count(filename) == 1);
        unchanged(RECENT_BOOKMARK_FILE, "recent original\n", 16);
        assert(bookmark_text_create_ex(paths[api], &retry_position) == TEXT_BOOKMARK_SAVED);
        assert(get_bookmark_count(filename) == 1);
        assert(get_bookmark_count(RECENT_BOOKMARK_FILE) == 2);
    }
    puts("first-save partial status, legacy false and lossless full-save retry passed");
}

static void test_error_scope_and_retry(void)
{
    const int errors[] = { EACCES, EROFS, ENOSPC, EMFILE, EIO };
    for (unsigned int scope = 0; scope < 4; scope++)
    for (unsigned int fault = 0; fault < sizeof(errors) / sizeof(errors[0]); fault++)
    {
        const char *local = "/books/scoped.txt.bmark";
        put(local, "local original\n");
        put(RECENT_BOOKMARK_FILE, "recent original\n");
        global_settings.usemrb = BOOKMARK_YES;
        scoped_failure_path = scope >= 2 ? RECENT_BOOKMARK_FILE : local;
        scoped_failure_errno = errors[fault];
        scoped_failure_write = scope % 2 != 0;
        scoped_open_calls = 0;
        assert(bookmark_text_create_ex("/books/scoped.txt", &retry_position) ==
               (scope < 2 ? TEXT_BOOKMARK_FAILED : TEXT_BOOKMARK_SAVED_LOCAL_ONLY));
        assert(scoped_open_calls == 1);
        scoped_open_calls = 0;
        assert(!bookmark_text_create("/books/scoped.txt", &retry_position));
        assert(scoped_open_calls == 1);
        scoped_failure_path = NULL;
        char buffer[4096];
        if (scope < 2) unchanged(local, "local original\n", 15);
        else
        {
            get(local, buffer, sizeof(buffer));
            assert(!strcmp(buffer,
                "T1;25;100;2;7;/books/scoped.txt\nlocal original\n"));
        }
        unchanged(RECENT_BOOKMARK_FILE, "recent original\n", 16);
        assert(!file_exists("/books/scoped.txt.bmark.tmp"));
        assert(!file_exists(RECENT_BOOKMARK_FILE ".tmp"));
        assert(bookmark_text_create("/books/scoped.txt", &retry_position));
        assert(bookmark_text_create_ex("/books/scoped.txt", &retry_position) == TEXT_BOOKMARK_SAVED);
        assert(get_bookmark_count(local) == 2);
        assert(get_bookmark_count(RECENT_BOOKMARK_FILE) == 2);
    }
    puts("20 scoped permission/read-only/full/descriptor/I-O errors and retry passed");
}

static void test_descriptor_budget(void)
{
    const char *local = "/books/descriptors.txt.bmark";
    for (unsigned int scope = 0; scope < 2; scope++)
    {
        global_settings.usemrb = scope ? BOOKMARK_YES : BOOKMARK_NO;
        for (unsigned int budget = 0; budget < 2; budget++)
        {
            put(local, "local original\n");
            put(RECENT_BOOKMARK_FILE, "recent original\n");
            limited_descriptors = true;
            descriptor_budget = budget;
            assert(bookmark_text_create_ex("/books/descriptors.txt", &retry_position) == TEXT_BOOKMARK_FAILED);
            assert(!bookmark_text_create("/books/descriptors.txt", &retry_position));
            assert(!open_descriptors);
            limited_descriptors = false;
            unchanged(local, "local original\n", 15);
            unchanged(RECENT_BOOKMARK_FILE, "recent original\n", 16);
        }
        limited_descriptors = true;
        descriptor_budget = 2;
        peak_descriptors = 0;
        assert(bookmark_text_create_ex("/books/descriptors.txt", &retry_position) == TEXT_BOOKMARK_SAVED);
        assert(bookmark_text_create("/books/descriptors.txt", &retry_position));
        assert(peak_descriptors == 2 && !open_descriptors);
        limited_descriptors = false;
    }
    puts("two-descriptor ceiling, exhaustion cleanup and retry passed");
}

static void test_recent_post_open_failures(void)
{
    const char *local = "/books/recent-errors.txt.bmark";
    for (unsigned int fault = 0; fault < 4; fault++)
    {
        put(local, "local original\n");
        put(RECENT_BOOKMARK_FILE, "recent original\n");
        global_settings.usemrb = BOOKMARK_YES;
        recent_io_fault = fault + 1;
        recent_io_hits = 0;
        assert(bookmark_text_create_ex("/books/recent-errors.txt", &retry_position) ==
               TEXT_BOOKMARK_SAVED_LOCAL_ONLY);
        assert(recent_io_hits == 1 && !open_descriptors);
        recent_io_hits = 0;
        assert(!bookmark_text_create("/books/recent-errors.txt", &retry_position));
        assert(recent_io_hits == 1 && !open_descriptors);
        recent_io_fault = 0;
        char buffer[4096];
        get(local, buffer, sizeof(buffer));
        assert(!strcmp(buffer,
            "T1;25;100;2;7;/books/recent-errors.txt\nlocal original\n"));
        unchanged(RECENT_BOOKMARK_FILE, "recent original\n", 16);
        assert(!file_exists(RECENT_BOOKMARK_FILE ".tmp"));
        assert(bookmark_text_create("/books/recent-errors.txt", &retry_position));
        assert(bookmark_text_create_ex("/books/recent-errors.txt", &retry_position) == TEXT_BOOKMARK_SAVED);
        assert(get_bookmark_count(local) == 2);
        assert(get_bookmark_count(RECENT_BOOKMARK_FILE) == 2);
    }
    puts("four recent read/write/close/rename errors preserve local success and retry passed");
}

static void test_native_path_and_recent_selection(void)
{
    const char *paths[] = { "/root.txt", "/books/nested/book.txt", "/books/Zażółć;世界.txt" };
    assert(mkdir("disk/books/nested", 0700) == 0);
    for (unsigned int index = 0; index < sizeof(paths) / sizeof(paths[0]); index++)
    {
        struct text_bookmark selected = { 0 };
        global_settings.usemrb = BOOKMARK_YES;
        assert(bookmark_text_create(paths[index], &retry_position));
        action(ACTION_STD_OK, 0, ACTION_STD_CANCEL);
        assert(bookmark_text_select(paths[index], &selected) == BOOKMARK_SUCCESS);
        assert(selected.offset == retry_position.offset && selected.size == retry_position.size);
        assert(selected.signature == retry_position.signature && selected.unit == retry_position.unit);
    }
    char path[MAX_PATH];
    memset(path, 'x', sizeof(path));
    memcpy(path, "/books/nested/", sizeof("/books/nested/") - 1);
    path[MAX_PATH - 11] = '\0';
    char filename[MAX_PATH], temporary[MAX_PATH];
    assert(text_bookmark_file_name(filename, sizeof(filename), path));
    assert(snprintf(temporary, sizeof(temporary), "%s.tmp", filename) == MAX_PATH - 1);
    put(temporary, "long path recovery\n");
    assert(bookmark_text_create_ex(path, &retry_position) == TEXT_BOOKMARK_SAVED);
    assert(bookmark_text_create(path, &retry_position));
    unchanged(temporary, "long path recovery\n", 19);
    assert(mock_remove(temporary) == 0);
    path[MAX_PATH - 11] = 'x';
    path[MAX_PATH - 10] = '\0';
    assert(bookmark_text_create_ex(path, &retry_position) == TEXT_BOOKMARK_FAILED);
    assert(!bookmark_text_create(path, &retry_position));
    puts("root, nested, UTF-8/semicolon and exact MAX_PATH sidecar/recent saves passed");
}

static void test_recovered_temp_failure_cleanup(void)
{
    const char *target = "/books/recovered.txt.bmark";
    put(target, "keep old\n");
    put("/books/recovered.txt.bmark.tmp", "recovery data\n");
    global_settings.usemrb = BOOKMARK_NO;
    for (unsigned int fault = 0; fault < 6; fault++)
    {
        reset_faults();
        if (fault == 0) fail_read = 1;
        if (fault == 1) fail_write = 1;
        if (fault == 2) { fail_write = 1; short_write = true; }
        if (fault == 3) { fail_write = 1; zero_write = true; }
        if (fault == 4) fail_close = 2;
        if (fault == 5) fail_rename = 1;
        assert(!bookmark_text_create("/books/recovered.txt", &retry_position));
        reset_faults();
        unchanged(target, "keep old\n", 9);
        unchanged("/books/recovered.txt.bmark.tmp", "recovery data\n", 14);
        assert(!file_exists("/books/recovered.txt.bmark.t01"));
        assert(!open_descriptors);
    }
    assert(bookmark_text_create("/books/recovered.txt", &retry_position));
    assert(mock_remove("/books/recovered.txt.bmark.tmp") == 0);
    puts("six recovered-temp read/write/close/rename failures preserve recovery passed");
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise AssertionError(f"Harness integration marker changed: {old}")
    return text.replace(old, new, 1)


class BookmarkWriteFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.output = WORKSPACE / stamp
        cls.output.mkdir(parents=True)
        source = (ROOT / "apps/bookmark.c").read_text(encoding="utf-8")
        settings = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        policy = "\n".join(extract_block(settings, signature) for signature in (
            "static inline bool talk_tts_enabled(", "static inline bool talk_menus_enabled("))
        identifiers = sorted(set(re.findall(r"\b(?:LANG|VOICE)_[A-Z_]+\b", source)) |
                             {"LANG_TTS_TEXT_BOOKMARK", "LANG_TTS_POSITION"})
        source = re.sub(r'^#include "[^\"]+"\s*$', "", source, flags=re.MULTILINE)
        harness = bookmarks.HARNESS.replace("@LANGUAGE_ENUM@", "enum { " + ", ".join(identifiers) + " };")
        harness = harness.replace("@TALK_POLICY@", policy).replace("@BOOKMARK_SOURCE@", source)
        harness = replace_once(harness, "static int original_removes;", """
static int original_removes;
static const char *scoped_failure_path;
static int scoped_failure_errno;
static bool scoped_failure_write;
static unsigned int scoped_open_calls;
static bool limited_descriptors;
static unsigned int descriptor_budget, open_descriptors, peak_descriptors;
static bool recent_descriptors[1024];
static unsigned int recent_io_fault, recent_io_hits;
""")
        harness = replace_once(harness, "    int kind = flags & O_CREAT ? 2 : 1;", """
    if (limited_descriptors && open_descriptors >= descriptor_budget)
    { errno = EMFILE; return -1; }
    if (scoped_failure_path)
    {
        char wanted[MAX_PATH];
        if (scoped_failure_write)
            assert(snprintf(wanted, sizeof(wanted), "%s.tmp", scoped_failure_path) < MAX_PATH);
        else strcpy(wanted, scoped_failure_path);
        if (!strcmp(wanted, path))
        { scoped_open_calls++; errno = scoped_failure_errno; return -1; }
    }
    int kind = flags & O_CREAT ? 2 : 1;
""")
        harness = replace_once(harness,
            "    if (file >= 0) { assert(file < 1024); descriptor_kind[file] = kind; }", """
    if (file >= 0)
    {
        assert(file < 1024); descriptor_kind[file] = kind;
        recent_descriptors[file] = !strncmp(path, ROCKBOX_DIR "/most-recent.bmark",
                                           strlen(ROCKBOX_DIR "/most-recent.bmark"));
        open_descriptors++;
        if (open_descriptors > peak_descriptors) peak_descriptors = open_descriptors;
    }
""")
        harness = replace_once(harness, "    int result = close(file);", """
    assert(open_descriptors);
    open_descriptors--;
    int result = close(file);
    bool recent = recent_descriptors[file];
    recent_descriptors[file] = false;
    if (recent && kind == 2 && recent_io_fault == 3)
    { recent_io_hits++; errno = EIO; return -1; }
""")
        harness = replace_once(harness, "    if (++read_calls == fail_read)", """
    if (recent_descriptors[file] && recent_io_fault == 1)
    { recent_io_hits++; errno = EIO; return -1; }
    if (++read_calls == fail_read)""")
        harness = replace_once(harness, "    if (++write_calls == fail_write)", """
    if (recent_descriptors[file] && recent_io_fault == 2)
    { recent_io_hits++; errno = ENOSPC; return -1; }
    if (++write_calls == fail_write)""")
        harness = replace_once(harness, "    if (fail_rename)", """
    if (recent_io_fault == 4 && !strcmp(new_path, ROCKBOX_DIR "/most-recent.bmark"))
    { recent_io_hits++; errno = EIO; return -1; }
    if (fail_rename)""")
        original_main = extract_block(harness, "int main(void)")
        harness = replace_once(harness, original_main, CASES + r'''
int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    assert(mkdir("disk", 0700) == 0);
    assert(mkdir("disk/books", 0700) == 0);
    assert(mkdir("disk/.rockbox", 0700) == 0);
    test_collision_recovery();
    test_slot_exhaustion();
    test_first_save_partial_result();
    test_error_scope_and_retry();
    test_descriptor_budget();
    test_recent_post_open_failures();
    test_native_path_and_recent_selection();
    test_recovered_temp_failure_cleanup();
    assert(!open_descriptors && !original_removes);
    for (unsigned int index = 0; index < 1024; index++) assert(!descriptor_kind[index]);
    return 0;
}
''')
        cls.harness = cls.output / "bookmark_write_host.c"
        cls.harness.write_text(harness, encoding="utf-8")
        cls.hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            "apps/bookmark.c", "apps/bookmark.h", "apps/settings.h",
            "tools/tests/test_text_bookmarks.py", "tools/tests/test_bookmark_write_failures.py")}

    def run_harness(self, mode, standard="gnu99", defines=(), sanitizer=None,
                    source=None, expected_failure=None):
        output = self.output / mode
        output.mkdir()
        executable = output / "bookmark-write-test"
        harness = self.harness
        if source is not None:
            harness = output / "negative_control.c"
            harness.write_text(source, encoding="utf-8")
        command = shlex.split(os.environ.get("CC", "cc")) + [
            f"-std={standard}", "-Os", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-unused-variable", "-I", str(ROOT / "apps"),
            str(harness), "-o", str(executable), "-DHAVE_ESPEAK",
        ] + ["-D" + define for define in defines]
        if sanitizer:
            command += [f"-fsanitize={sanitizer}", "-fno-sanitize-recover=all"]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / "compile.log").write_text(shlex.join(command) + "\n" + compiled.stdout + compiled.stderr,
                                            encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        tested = subprocess.run([str(executable)], cwd=output, capture_output=True,
                                text=True, timeout=30)
        (output / "result.json").write_text(json.dumps({
            "source_sha256": self.hashes, "returncode": tested.returncode,
            "stdout": tested.stdout, "stderr": tested.stderr,
            "expected_failure": expected_failure,
            "limitations": ["POSIX host filesystem, not native FAT or physical Sansa",
                            "reader signature stage covered by separate reader suite"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        if expected_failure:
            self.assertNotEqual(tested.returncode, 0)
            self.assertIn(expected_failure, tested.stderr)
        else:
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_gnu99(self):
        self.run_harness("gnu99")

    def test_gnu11(self):
        self.run_harness("gnu11", "gnu11")

    def test_native_32_bit_offsets_ubsan(self):
        self.run_harness("offset32-ubsan", defines=("TEST_OFF32",), sanitizer="undefined")

    def test_pitch_and_64_bit_offsets_ubsan(self):
        self.run_harness("pitch-ubsan", defines=("HAVE_PITCHCONTROL",), sanitizer="undefined")

    def test_large_file_32_bit_sizes_ubsan(self):
        self.run_harness("size32-offset64-ubsan", defines=("TEST_SIZE32",), sanitizer="undefined")

    def test_original_single_temp_behavior_fails_regression(self):
        source = self.harness.read_text(encoding="utf-8")
        block = extract_block(source, "static int open_temp_bookmark(")
        original = r'''
static int open_temp_bookmark(char *buffer, size_t capacity, int flags, const char *filename)
{
    if (!filename || !*filename) return -1;
    int length = snprintf(buffer, capacity, "%s.tmp", filename);
    if (length < 0 || (size_t)length >= capacity) return -1;
    return open(buffer, flags, 0666);
}
'''
        self.run_harness("negative-control-single-temp", source=replace_once(source, block, original),
                         expected_failure='bookmark_text_create_ex("/books/retry.txt", &retry_position) == TEXT_BOOKMARK_SAVED')

    def test_legacy_bool_must_not_mask_partial_failure(self):
        source = self.harness.read_text(encoding="utf-8")
        block = extract_block(source, "bool bookmark_text_create(")
        masked = r'''
bool bookmark_text_create(const char *path, const struct text_bookmark *bookmark)
{
    return bookmark_text_create_ex(path, bookmark);
}
'''
        self.run_harness("negative-control-masked-partial", source=replace_once(source, block, masked),
                         expected_failure='!bookmark_text_create(paths[api], &retry_position)')


if __name__ == "__main__":
    unittest.main(verbosity=2)
