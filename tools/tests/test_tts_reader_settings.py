"""Exercise the actual private preference parser/writer with fault-injected I/O."""
import ctypes
from datetime import datetime, timezone
import errno
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
INPUTS = ("apps/tts_reader_settings.c", "apps/tts_reader_settings.h",
          "tools/tests/test_tts_reader_settings.py")
PREFIX = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#define ROCKBOX_DIR "/synthetic-reader"
static unsigned char primary[128], temporary[128];
static size_t primary_size, temporary_size, offset;
static bool primary_exists, temporary_exists, primary_open, temporary_open;
static unsigned int fault;
static int read_chunk, write_chunk, open_calls, read_calls, write_calls;
static int sync_calls, close_calls, rename_calls, remove_calls;
enum { F_PRIMARY_OPEN=1, F_TEMP_OPEN=2, F_READ=4, F_WRITE=8, F_SYNC=16,
       F_CLOSE=32, F_RENAME=64, F_REMOVE=128, F_ZERO_WRITE=256,
       F_READ_EINTR=512, F_WRITE_EINTR=1024, F_SYNC_EINTR=2048,
       F_OPEN_EINTR=4096 };
static int fail_io(int error) { errno = error; return -1; }
static int fixture_open(const char *path, int flags, int mode)
{
    ++open_calls;
    if (fault & F_OPEN_EINTR) return fail_io(EINTR);
    if (strstr(path, ".tmp"))
    {
        assert(flags == (O_WRONLY | O_CREAT | O_EXCL) && mode == 0600);
        if (fault & F_TEMP_OPEN) return fail_io(EACCES);
        if (temporary_exists) return fail_io(EEXIST);
        temporary_exists = temporary_open = true;
        temporary_size = 0;
        return 4;
    }
    assert(flags == O_RDONLY);
    if (fault & F_PRIMARY_OPEN) return fail_io(EACCES);
    if (!primary_exists) return fail_io(ENOENT);
    assert(!primary_open);
    primary_open = true;
    offset = 0;
    return 3;
}
static ssize_t fixture_read(int descriptor, void *data, size_t count)
{
    assert(descriptor == 3 && primary_open);
    ++read_calls;
    if (fault & F_READ_EINTR) return fail_io(EINTR);
    if (fault & F_READ) return fail_io(EIO);
    if (count > primary_size - offset) count = primary_size - offset;
    if (read_chunk && count > (size_t)read_chunk) count = read_chunk;
    memcpy(data, primary + offset, count);
    offset += count;
    return count;
}
static ssize_t fixture_write(int descriptor, const void *data, size_t count)
{
    assert(descriptor == 4 && temporary_open);
    ++write_calls;
    if (fault & F_WRITE_EINTR) return fail_io(EINTR);
    if (fault & F_WRITE) return fail_io(EIO);
    if (fault & F_ZERO_WRITE) return 0;
    if (write_chunk && count > (size_t)write_chunk) count = write_chunk;
    assert(temporary_size + count <= sizeof(temporary));
    memcpy(temporary + temporary_size, data, count);
    temporary_size += count;
    return count;
}
static int fixture_sync(int descriptor)
{
    assert(descriptor == 4 && temporary_open);
    ++sync_calls;
    if (fault & F_SYNC_EINTR) return fail_io(EINTR);
    return fault & F_SYNC ? fail_io(EIO) : 0;
}
static int fixture_close(int descriptor)
{
    assert(descriptor == 3 ? primary_open : descriptor == 4 && temporary_open);
    if (descriptor == 3) primary_open = false;
    else temporary_open = false;
    ++close_calls;
    return fault & F_CLOSE ? fail_io(EINTR) : 0;
}
static int fixture_rename(const char *source, const char *destination)
{
    assert(strstr(source, ".tmp") && !strstr(destination, ".tmp"));
    assert(temporary_exists && !temporary_open && !primary_open);
    ++rename_calls;
    if (fault & F_RENAME) return fail_io(EIO);
    memcpy(primary, temporary, temporary_size);
    primary_size = temporary_size;
    primary_exists = true;
    temporary_exists = false;
    return 0;
}
static int fixture_remove(const char *path)
{
    assert(strstr(path, ".tmp") && temporary_exists && !temporary_open);
    ++remove_calls;
    if (fault & F_REMOVE) return fail_io(EACCES);
    temporary_exists = false;
    return 0;
}
#define open fixture_open
#define read fixture_read
#define write fixture_write
#define fsync fixture_sync
#define close fixture_close
#define rename fixture_rename
#define remove fixture_remove
"""
SUFFIX = r"""
void probe_reset(void)
{
    memset(&current_preferences, 0, sizeof(current_preferences));
    preferences_loaded = primary_exists = temporary_exists = false;
    primary_open = temporary_open = false;
    primary_size = temporary_size = offset = 0;
    read_chunk = write_chunk = open_calls = read_calls = write_calls = 0;
    sync_calls = close_calls = rename_calls = remove_calls = 0;
    fault = 0;
}
void probe_restart(void)
{
    memset(&current_preferences, 0, sizeof(current_preferences));
    preferences_loaded = false;
}
void probe_primary(const char *data, size_t length)
{
    assert(length <= sizeof(primary));
    memcpy(primary, data, length);
    primary_size = length;
    primary_exists = true;
}
void probe_temporary(const char *data, size_t length)
{
    assert(length <= sizeof(temporary));
    memcpy(temporary, data, length);
    temporary_size = length;
    temporary_exists = true;
}
void probe_fault(unsigned int mask, int read_size, int write_size)
{ fault = mask; read_chunk = read_size; write_chunk = write_size; }
int probe_get(int field)
{
    struct tts_reader_preferences value;
    int error = tts_reader_preferences_get(&value);
    return field == 0 ? error : field == 1 ? value.match_case :
        field == 2 ? (int)value.wrap : value.cleanup_error;
}
int probe_set(int preference, int value)
{ return tts_reader_preferences_set((enum tts_reader_preference)preference, value); }
const char *probe_primary_data(void) { primary[primary_size] = 0; return (char *)primary; }
const char *probe_temp_data(void) { temporary[temporary_size] = 0; return (char *)temporary; }
int probe_stat(int field)
{
    int values[] = {primary_exists, temporary_exists, open_calls, read_calls,
        write_calls, sync_calls, close_calls, rename_calls, remove_calls,
        primary_open || temporary_open};
    assert(field >= 0 && field < (int)(sizeof(values)/sizeof(values[0])));
    return values[field];
}
"""


class ReaderPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = project_materials_root(ROOT) / "tts-reader-settings-tests" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.inputs = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                      for name in INPUTS}
        header = re.sub(r'^#include[^\n]*\n', '',
                        (ROOT / INPUTS[1]).read_text(encoding="utf-8"), flags=re.MULTILINE)
        source = re.sub(r'^#include[^\n]*\n', '',
                        (ROOT / INPUTS[0]).read_text(encoding="utf-8"), flags=re.MULTILINE)
        harness = cls.workspace / "preferences.c"
        harness.write_text(PREFIX + header + source + SUFFIX, encoding="utf-8")
        output = cls.workspace / ("preferences.dll" if os.name == "nt" else "preferences.so")
        cls.command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
            str(harness), "-o", str(output)]
        if os.environ.get("TTS_READER_SANITIZE"):
            cls.command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        completed = subprocess.run(cls.command, capture_output=True, text=True)
        (cls.workspace / "compile.log").write_text(
            shlex.join(cls.command) + "\n" + completed.stdout + completed.stderr, encoding="utf-8")
        cls.actual_exit = completed.returncode
        if completed.returncode:
            raise RuntimeError(completed.stderr)
        cls.lib = ctypes.CDLL(str(output))
        cls.lib.probe_primary.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        cls.lib.probe_temporary.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        cls.lib.probe_primary_data.restype = ctypes.c_char_p
        cls.lib.probe_temp_data.restype = ctypes.c_char_p

    @classmethod
    def tearDownClass(cls):
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                 for name in INPUTS}
        (cls.workspace / "provenance.json").write_text(json.dumps({
            "inputs_before": cls.inputs, "inputs_after": after,
            "source_stable": after == cls.inputs, "command": cls.command,
            "compiler_exit": cls.actual_exit, "actual_production_parser_writer": True,
            "filesystem_faults_stubbed": True, "real_simulator_restart_verified": False,
        }, indent=2) + "\n", encoding="utf-8")

    def setUp(self):
        self.lib.probe_reset()

    def seed(self, data):
        self.lib.probe_primary(data, len(data))

    def pair(self):
        return self.lib.probe_get(1), self.lib.probe_get(2)

    def test_absent_defaults_and_all_choices_survive_module_restart(self):
        self.assertEqual(self.pair(), (0, 0))
        self.assertFalse(self.lib.probe_stat(0))
        for case in range(2):
            for wrap in range(3):
                self.assertEqual(self.lib.probe_set(0, case), 0)
                self.assertEqual(self.lib.probe_set(1, wrap), 0)
                expected = f"RBTTSREADER:1\ncase:{case}\nwrap:{wrap}\n".encode()
                self.assertEqual(self.lib.probe_primary_data(), expected)
                self.assertFalse(self.lib.probe_stat(1))
                self.assertFalse(self.lib.probe_stat(9))
                self.lib.probe_restart()
                self.assertEqual(self.pair(), (case, wrap))

    def test_unknown_primary_is_preserved_and_never_replaced(self):
        values = [b"", b"unknown", b"RBTTSREADER:2\ncase:0\nwrap:0\n",
                  b"RBTTSREADER:1\r\ncase:0\r\nwrap:0\r\n",
                  b"RBTTSREADER:1\ncase:2\nwrap:0\n",
                  b"RBTTSREADER:1\ncase:0\nwrap:3\n",
                  b"RBTTSREADER:1\ncase:0\nwrap:0\n\x00", b"x" * 100]
        for value in values:
            with self.subTest(value=value):
                self.lib.probe_reset()
                self.seed(value)
                self.assertEqual(self.lib.probe_get(0), errno.EINVAL)
                self.assertEqual(self.pair(), (0, 0))
                self.assertEqual(self.lib.probe_set(0, 1), errno.EINVAL)
                # Raw lengths are retained even when a fixture display contains NUL.
                self.assertEqual(self.lib.probe_primary_data(), value.split(b"\x00")[0])
                self.assertFalse(self.lib.probe_stat(1))
                self.assertEqual(self.lib.probe_stat(7), 0)

    def test_exclusive_temp_collision_is_preserved_without_cleanup(self):
        self.lib.probe_temporary(b"owned elsewhere", 15)
        self.assertEqual(self.lib.probe_set(0, 1), errno.EEXIST)
        self.assertEqual(self.lib.probe_temp_data(), b"owned elsewhere")
        self.assertEqual(self.lib.probe_stat(8), 0)
        self.assertEqual(self.pair(), (0, 0))

    def test_short_io_and_observed_external_primary_revalidation(self):
        self.seed(b"RBTTSREADER:1\ncase:0\nwrap:2\n")
        self.lib.probe_fault(0, 1, 1)
        self.assertEqual(self.lib.probe_get(0), 0)
        self.seed(b"future data")
        self.assertEqual(self.lib.probe_set(0, 1), errno.EINVAL)
        self.assertEqual(self.pair(), (0, 2))
        self.assertEqual(self.lib.probe_primary_data(), b"future data")
        self.seed(b"RBTTSREADER:1\ncase:0\nwrap:2\n")
        self.assertEqual(self.lib.probe_set(0, 1), 0)
        self.assertEqual(self.pair(), (1, 2))
        self.assertGreater(self.lib.probe_stat(4), 1)

    def test_write_sync_close_rename_failure_preserves_pair_and_primary(self):
        for fault in (2, 8, 16, 32, 64, 256, 1024, 2048):
            with self.subTest(fault=fault):
                self.lib.probe_reset()
                self.assertEqual(self.pair(), (0, 0))
                self.lib.probe_fault(fault, 0, 0)
                self.assertNotEqual(self.lib.probe_set(0, 1), 0)
                self.assertEqual(self.pair(), (0, 0))
                self.assertFalse(self.lib.probe_stat(0))
                self.assertFalse(self.lib.probe_stat(1))
                self.assertFalse(self.lib.probe_stat(9))
                self.assertLessEqual(self.lib.probe_stat(4), 4)
                self.assertLessEqual(self.lib.probe_stat(5), 4)
                self.assertLessEqual(self.lib.probe_stat(6), 1)

    def test_read_open_interruptions_and_cleanup_failure_are_bounded_and_disclosed(self):
        for fault in (1, 4, 512, 4096):
            with self.subTest(fault=fault):
                self.lib.probe_reset()
                self.seed(b"RBTTSREADER:1\ncase:1\nwrap:2\n")
                self.lib.probe_fault(fault, 0, 0)
                self.assertNotEqual(self.lib.probe_get(0), 0)
                self.assertEqual(self.pair(), (0, 0))
                self.assertLessEqual(self.lib.probe_stat(2), 4)
                self.assertLessEqual(self.lib.probe_stat(3), 4)
        self.lib.probe_reset()
        self.lib.probe_fault(8 | 128, 0, 0)
        self.assertNotEqual(self.lib.probe_set(0, 1), 0)
        self.assertEqual(self.lib.probe_get(3), errno.EACCES)
        self.assertTrue(self.lib.probe_stat(1))  # owned cleanup failed, disclosed.

    def test_invalid_enum_never_opens_or_creates_files(self):
        for preference, value in ((-1, 0), (0, -1), (0, 2), (1, 3), (2, 0)):
            self.assertEqual(self.lib.probe_set(preference, value), errno.EINVAL)
        self.assertEqual(self.lib.probe_stat(2), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
