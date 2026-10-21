from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'tools/diagnostics/hiby_r1_audio/r1_audio_trace.c'
PROGRAM = r'''
#define _GNU_SOURCE 1
#include <assert.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#define open diagnostic_test_open
#include "SOURCE_PATH"
#undef open

static const char *fixture_library;

int __wrap_dladdr(const void *address, Dl_info *details)
{
    (void)address;
    if (!fixture_library)
        return 0;
    details->dli_fname = fixture_library;
    return 1;
}

int main(int count, char **arguments)
{
    assert(count == 3);
    char path[4096];
    char library[4096];
    snprintf(path, sizeof(path), "%s/r1-audio-diagnostic.log", arguments[2]);
    snprintf(library, sizeof(library), "%s/test.so", arguments[2]);
    fixture_library = library;
    if (!strcmp(arguments[1], "full"))
    {
        FILE *stream = fopen(path, "wb");
        assert(stream);
        for (int offset = 0; offset < 65536; offset++)
            assert(fputc('x', stream) == 'x');
        assert(!fclose(stream));
    }
    if (!strcmp(arguments[1], "directory"))
        assert(!mkdir(path, 0700));
    if (!strcmp(arguments[1], "symlink"))
    {
        char target[4096];
        snprintf(target, sizeof(target), "%s/protected.txt", arguments[2]);
        FILE *stream = fopen(target, "wb");
        assert(stream && fputs("safe", stream) >= 0 && !fclose(stream));
        assert(!symlink(target, path));
    }
    if (!strcmp(arguments[1], "relative"))
        fixture_library = "test.so";
    errno = ERANGE;
    if (!strcmp(arguments[1], "truncate"))
    {
        char long_message[4096];
        memset(long_message, 'z', sizeof(long_message) - 1);
        long_message[sizeof(long_message) - 1] = 0;
        trace_event("%s", long_message);
    }
    else
        trace_event("unit diagnostic message");
    assert(errno == ERANGE);
    struct stat details;
    if (!strcmp(arguments[1], "relative"))
        assert(stat(path, &details) < 0 && errno == ENOENT);
    else if (!strcmp(arguments[1], "full"))
        assert(!stat(path, &details) && details.st_size == 65536);
    else if (!strcmp(arguments[1], "directory"))
        assert(!stat(path, &details) && S_ISDIR(details.st_mode));
    else if (!strcmp(arguments[1], "symlink"))
        assert(!stat(path, &details) && details.st_size == 4);
    else
    {
        char output[1024];
        FILE *stream = fopen(path, "rb");
        assert(stream);
        size_t bytes = fread(output, 1, sizeof(output) - 1, stream);
        assert(bytes && bytes < 768 && !fclose(stream));
        output[bytes] = 0;
        assert(output[bytes - 1] == '\n');
        if (!strcmp(arguments[1], "regular"))
            assert(strstr(output, "unit diagnostic message"));
    }
    puts("PASS");
    return 0;
}
'''


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('gcc'), 'Linux host compiler/ALSA headers required')
class AudioTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = project_materials_root(ROOT) / 'hiby-audio-trace-tests' / (
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        cls.records = []
        program = cls.evidence / 'trace-policy.c'
        program.write_text(PROGRAM.replace('SOURCE_PATH', SOURCE.as_posix()), encoding='utf-8')
        cls.binary = cls.evidence / 'trace-policy'
        command = ['gcc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wformat=2',
            '-fsanitize=undefined', '-fno-sanitize-recover=all', str(program), '-Wl,--wrap=dladdr',
            '-ldl', '-pthread', '-lasound', '-o', str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        cls.records.append(dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise RuntimeError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        after = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        (cls.evidence / 'report.json').write_text(json.dumps(dict(
            passed=all(record['exit_code'] == 0 for record in cls.records) and cls.before == after,
            source_sha256_before=cls.before, source_sha256_after=after, commands=cls.records,
            scope='Actual trace policy with dladdr redirected into owned fixtures; UBSan, not physical audio'), indent=2), encoding='utf-8')

    def check_case(self, mode):
        directory = self.evidence / mode
        directory.mkdir()
        command = [str(self.binary), mode, str(directory)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.records.append(dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'PASS\n')

    def test_regular_log_and_errno_preservation(self):
        self.check_case('regular')

    def test_full_log_is_not_extended(self):
        self.check_case('full')

    def test_directory_cannot_be_overwritten(self):
        self.check_case('directory')

    def test_symlink_target_is_not_modified(self):
        self.check_case('symlink')

    def test_long_messages_are_bounded(self):
        self.check_case('truncate')

    def test_non_absolute_library_does_not_redirect_logging(self):
        self.check_case('relative')


if __name__ == '__main__':
    unittest.main(verbosity=2)
