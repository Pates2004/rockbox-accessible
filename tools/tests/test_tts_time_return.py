"""Exercise extracted time speech code with mocked queue/file/voice boundaries."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import unittest

from test_tts_coverage import extract_block


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
EVIDENCE = _project_materials_root(ROOT) / "tts-time-return-tests" / STAMP

PREFIX = r"""
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #condition); exit(1); } } while (0)
#define ARRAYLEN(values) (sizeof(values) / sizeof((values)[0]))
enum {
    VOICE_MILLISECOND = 1000, VOICE_MILLISECONDS,
    VOICE_SECOND, VOICE_SECONDS, VOICE_MINUTE, VOICE_MINUTES,
    VOICE_HOUR, VOICE_HOURS, VOICE_KHZ, VOICE_DB, VOICE_PERCENT,
    VOICE_MILLIAMPHOURS, VOICE_PIXEL, VOICE_PER_SEC, VOICE_HERTZ,
    LANG_MEBIBYTE, VOICE_KBIT_PER_SEC, VOICE_PM_UNITS_PER_TICK,
    VOICE_PLUS, VOICE_MINUS
};
enum event_kind { EVENT_OPEN, EVENT_INDEX, EVENT_DATA, EVENT_CLOSE,
                  EVENT_ENQUEUE, EVENT_NUMBER, EVENT_ID };
struct event { enum event_kind kind; long value; bool enqueue; };
static struct event events[64];
static long queued[64];
static size_t event_count, queued_count;
static unsigned int case_count;
static bool disabled, available, index_ok, units_first;
static int talk_handle, index_handle, opened_fd;

static void record(enum event_kind kind, long value, bool enqueue)
{
    CHECK(event_count < ARRAYLEN(events));
    events[event_count++] = (struct event){kind, value, enqueue};
}

static bool talk_is_disabled(void) { return disabled; }
#ifdef HAVE_ESPEAK
static bool tts_is_available(void) { return available; }
#endif
static bool lang_units_first(void) { return units_first; }
static int open_voicefile(void)
{
    record(EVENT_OPEN, opened_fd, false);
    return opened_fd;
}
static bool load_voicefile_index(int descriptor)
{
    record(EVENT_INDEX, descriptor, false);
    return index_ok;
}
static void load_voicefile_data(int descriptor)
{
    record(EVENT_DATA, descriptor, false);
}
static int mock_close(int descriptor)
{
    record(EVENT_CLOSE, descriptor, false);
    return 0;
}
#define close mock_close
static void do_enqueue(bool enqueue)
{
    record(EVENT_ENQUEUE, 0, enqueue);
    if (!enqueue)
        queued_count = 0;
}
static int talk_id(int identifier, bool enqueue)
{
    record(EVENT_ID, identifier, enqueue);
    CHECK(queued_count < ARRAYLEN(queued));
    queued[queued_count++] = identifier;
    return 0;
}
static int talk_number(long number, bool enqueue)
{
    record(EVENT_NUMBER, number, enqueue);
    CHECK(queued_count < ARRAYLEN(queued));
    queued[queued_count++] = number;
    return 0;
}
static int talk_year(long number, bool enqueue)
{
    (void)number;
    (void)enqueue;
    CHECK(false);
    return -1;
}
static void talk_fractional(char *buffer, int value, int unit)
{
    (void)buffer;
    (void)value;
    (void)unit;
    CHECK(false);
}
int talk_time_intervals(long time, int unit_idx, bool enqueue);
int talk_value_decimal(long number, int unit, int decimals, bool enqueue);
"""

HARNESS = r"""
struct spoken_value { long number; int identifier; };
struct time_case {
    long duration;
    int unit;
    size_t count;
    struct spoken_value values[4];
};
static const struct time_case samples[] = {
    {0, UNIT_SEC, 1, {{0, VOICE_SECONDS}}},
    {0, UNIT_MS, 1, {{0, VOICE_MILLISECONDS}}},
    {0, UNIT_MIN, 1, {{0, VOICE_MINUTES}}},
    {0, UNIT_HOUR, 1, {{0, VOICE_HOURS}}},
    {1, UNIT_SEC, 1, {{1, VOICE_SECOND}}},
    {-1, UNIT_SEC, 1, {{1, VOICE_SECOND}}},
    {60, UNIT_SEC, 1, {{1, VOICE_MINUTE}}},
    {3600, UNIT_SEC, 1, {{1, VOICE_HOUR}}},
    {3661, UNIT_SEC, 3, {{1, VOICE_HOUR}, {1, VOICE_MINUTE}, {1, VOICE_SECOND}}},
    {7325, UNIT_SEC, 3, {{2, VOICE_HOURS}, {2, VOICE_MINUTES}, {5, VOICE_SECONDS}}},
    {-7325, UNIT_SEC, 3, {{2, VOICE_HOURS}, {2, VOICE_MINUTES}, {5, VOICE_SECONDS}}},
    {3602003, UNIT_MS, 3, {{1, VOICE_HOUR}, {2, VOICE_SECONDS}, {3, VOICE_MILLISECONDS}}},
    {-3602003, UNIT_MS, 3, {{1, VOICE_HOUR}, {2, VOICE_SECONDS}, {3, VOICE_MILLISECONDS}}},
    {125, UNIT_MIN, 2, {{2, VOICE_HOURS}, {5, VOICE_MINUTES}}},
    {-125, UNIT_MIN, 2, {{2, VOICE_HOURS}, {5, VOICE_MINUTES}}},
    {2, UNIT_HOUR, 1, {{2, VOICE_HOURS}}},
    {999, UNIT_MS, 1, {{999, VOICE_MILLISECONDS}}},
    {1000, UNIT_MS, 1, {{1, VOICE_SECOND}}}
};

static void reset(void)
{
    event_count = 0;
    queued_count = 1;
    queued[0] = -4242;
    disabled = false;
    available = true;
    index_ok = true;
    units_first = false;
    talk_handle = 12;
    index_handle = 13;
    opened_fd = 7;
}

static int invoke(unsigned int entry, long duration, int unit, bool enqueue)
{
    switch (entry)
    {
        case 0: return talk_time_intervals(duration, unit, enqueue);
        case 1: CHECK(unit == UNIT_SEC); return talk_time_unit(duration, enqueue);
        case 2: CHECK(unit == UNIT_SEC); return talk_value_decimal(duration, UNIT_TIME, 0, enqueue);
        case 3: CHECK(unit == UNIT_SEC); return talk_value(duration, UNIT_TIME, enqueue);
        default: CHECK(false); return -99;
    }
}

static void expect_event(size_t position, enum event_kind kind, long value, bool enqueue)
{
    CHECK(position < event_count);
    CHECK(events[position].kind == kind);
    CHECK(events[position].value == value);
    CHECK(events[position].enqueue == enqueue);
}

static void expect_speech(size_t offset, const struct time_case *sample, bool enqueue)
{
    size_t cursor = offset;
    expect_event(cursor++, EVENT_ENQUEUE, 0, enqueue);
    if (sample->duration < 0)
        expect_event(cursor++, EVENT_ID, VOICE_MINUS, true);
    for (size_t value_index = 0; value_index < sample->count; ++value_index)
    {
        const struct spoken_value *value = &sample->values[value_index];
        if (units_first)
            expect_event(cursor++, EVENT_ID, value->identifier, true);
        expect_event(cursor++, EVENT_NUMBER, value->number, true);
        if (!units_first)
            expect_event(cursor++, EVENT_ID, value->identifier, true);
    }
    CHECK(cursor == event_count);
    CHECK(queued_count == event_count - offset - 1 + (enqueue ? 1 : 0));
    if (enqueue)
        CHECK(queued[0] == -4242);
    for (size_t queue_index = enqueue ? 1 : 0; queue_index < queued_count; ++queue_index)
        CHECK(queued[queue_index] == events[offset + 1 + queue_index - (enqueue ? 1 : 0)].value);
}

static void test_durations_and_entry_points(void)
{
    for (unsigned int entry = 0; entry < 4; ++entry)
    for (size_t sample_index = 0; sample_index < ARRAYLEN(samples); ++sample_index)
    for (unsigned int enqueue = 0; enqueue < 2; ++enqueue)
    for (unsigned int order = 0; order < 2; ++order)
    {
        const struct time_case *sample = &samples[sample_index];
        if (entry != 0 && sample->unit != UNIT_SEC)
            continue;
        reset();
        units_first = order != 0;
#ifdef HAVE_ESPEAK
        talk_handle = index_handle = 0;
#endif
        int result = invoke(entry, sample->duration, sample->unit, enqueue != 0);
        CHECK(result == 0);
        expect_speech(0, sample, enqueue != 0);
        ++case_count;
    }
}

static void test_disabled(void)
{
    for (unsigned int entry = 0; entry < 4; ++entry)
    for (unsigned int enqueue = 0; enqueue < 2; ++enqueue)
    for (unsigned int engine = 0; engine < 2; ++engine)
    {
        reset();
        disabled = true;
        available = engine != 0;
        talk_handle = index_handle = 0;
        CHECK(invoke(entry, -3661, UNIT_SEC, enqueue != 0) == -1);
        CHECK(event_count == 0);
        CHECK(queued_count == 1 && queued[0] == -4242);
        ++case_count;
    }
}

static void test_voicefile_reload_and_failures(void)
{
    static const int handles[][2] = {{0, 13}, {12, 0}, {0, 0}, {-1, 13}, {12, -1}};
    for (unsigned int entry = 0; entry < 4; ++entry)
    for (unsigned int enqueue = 0; enqueue < 2; ++enqueue)
    for (size_t handle_index = 0; handle_index < ARRAYLEN(handles); ++handle_index)
    for (unsigned int failure = 0; failure < 3; ++failure)
    {
        reset();
#ifdef HAVE_ESPEAK
        available = false;
#endif
        talk_handle = handles[handle_index][0];
        index_handle = handles[handle_index][1];
        if (failure == 1)
            opened_fd = -9;
        if (failure == 2)
            index_ok = false;
        int result = invoke(entry, 7325, UNIT_SEC, enqueue != 0);
        expect_event(0, EVENT_OPEN, opened_fd, false);
        if (failure == 1)
        {
            CHECK(result == -1);
            CHECK(event_count == 1);
        }
        else
        {
            expect_event(1, EVENT_INDEX, 7, false);
            if (failure == 2)
            {
                CHECK(result == -1);
                expect_event(2, EVENT_CLOSE, 7, false);
                CHECK(event_count == 3);
            }
            else
            {
                CHECK(result == 0);
                expect_event(2, EVENT_DATA, 7, false);
                expect_event(3, EVENT_CLOSE, 7, false);
                expect_speech(4, &samples[9], enqueue != 0);
            }
        }
        if (failure != 0)
            CHECK(queued_count == 1 && queued[0] == -4242);
        ++case_count;
    }
}

static void test_available_engine_and_loaded_voice(void)
{
    for (unsigned int entry = 0; entry < 4; ++entry)
    for (unsigned int enqueue = 0; enqueue < 2; ++enqueue)
    for (unsigned int engine = 0; engine < 2; ++engine)
    {
        reset();
        available = engine != 0;
        opened_fd = -9;
        CHECK(invoke(entry, 7325, UNIT_SEC, enqueue != 0) == 0);
        expect_speech(0, &samples[9], enqueue != 0);
        ++case_count;
    }
#ifdef HAVE_ESPEAK
    for (unsigned int entry = 0; entry < 4; ++entry)
    for (unsigned int enqueue = 0; enqueue < 2; ++enqueue)
    {
        reset();
        talk_handle = index_handle = -1;
        opened_fd = -9;
        CHECK(invoke(entry, 7325, UNIT_SEC, enqueue != 0) == 0);
        expect_speech(0, &samples[9], enqueue != 0);
        ++case_count;
    }
#endif
}

static void test_zero_component_suppression(void)
{
    reset();
    talk_time_value(0, UNIT_SEC, false);
    CHECK(event_count == 0 && queued_count == 1);
    ++case_count;
}

int main(void)
{
    test_durations_and_entry_points();
    test_disabled();
    test_voicefile_reload_and_failures();
    test_available_engine_and_loaded_voice();
    test_zero_component_suppression();
    printf("{\"cases\": %u, \"status\": \"passed\"}\n", case_count);
    return 0;
}
"""


class TimeReturnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CC", "cc"))
        if not compiler or shutil.which(compiler[0]) is None:
            raise unittest.SkipTest("A GCC-compatible C compiler is required; run under WSL")
        cls.compiler = compiler
        cls.sources = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in ("apps/talk.c", "apps/talk.h", "apps/misc.c", "apps/misc.h")
        }
        talk = cls.sources["apps/talk.c"]
        cls.intervals = extract_block(talk, "int talk_time_intervals(")
        cls.parts = [
            extract_block(cls.sources["apps/talk.h"], "enum {") + ";\n",
            extract_block(cls.sources["apps/misc.h"], "enum e_fmt_time_auto_idx") + ";\n",
            re.search(r"(?m)^#define UNIT_IDX_MASK[^\n]*", cls.sources["apps/misc.h"]).group() + "\n",
            PREFIX,
            extract_block(cls.sources["apps/misc.c"], "unsigned int time_split_units("),
            extract_block(talk, "static inline int load_voicefile_failure("),
            extract_block(talk, "static int talk_time_unit("),
            extract_block(talk, "int talk_value(long n,"),
            extract_block(talk, "int talk_value_decimal("),
            extract_block(talk, "static inline void talk_time_value("),
        ]
        EVIDENCE.mkdir(parents=True)
        cls.provenance = {
            "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in cls.sources
            },
            "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "actual_functions": ["time_split_units", "load_voicefile_failure", "talk_time_unit",
                                 "talk_value", "talk_value_decimal", "talk_time_value", "talk_time_intervals"],
            "mocked_boundaries": ["speech IDs/numbers and queue", "voicefile open/index/data/close",
                                  "disabled/engine availability", "language unit order"],
            "limits": ["No actual synthesis, audio queue backend, voicefiles, GUI or hardware",
                       "LONG_MIN/labs overflow and fractional/year dispatch are outside this regression"],
        }
        (EVIDENCE / "provenance.json").write_text(json.dumps(cls.provenance, indent=2), encoding="utf-8")

    def run_harness(self, espeak, old_return=False):
        mode = ("espeak" if espeak else "legacy") + ("-old-return" if old_return else "")
        output = EVIDENCE / mode
        output.mkdir()
        intervals = self.intervals
        if old_return:
            intervals, replacements = re.subn(r"return 0;(\s*}\s*)$", r"return -1;\1", intervals)
            self.assertEqual(replacements, 1, "Baseline must change only the final success return")
        source = output / "time-return.c"
        source.write_text("\n".join(self.parts + [intervals, HARNESS]), encoding="utf-8")
        executable = output / "time-return"
        command = self.compiler + [
            "-std=gnu99", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-override-init",
            "-Wimplicit-fallthrough=1",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
            "-fno-pie", "-no-pie", str(source), "-o", str(executable),
        ]
        if espeak:
            command.append("-DHAVE_ESPEAK")
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / "compile.log").write_text(shlex.join(command) + "\n" + compiled.stdout + compiled.stderr,
                                            encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
                           UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        tested = subprocess.run([str(executable)], env=environment, capture_output=True, text=True, timeout=30)
        report = {
            "mode": mode, "sanitizers": ["address", "undefined"],
            "returncode": tested.returncode, "stdout": tested.stdout, "stderr": tested.stderr,
            "expected_old_return_failure": old_return,
            "extracted_harness_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            **self.provenance,
        }
        if not old_return and tested.returncode == 0:
            report["harness"] = json.loads(tested.stdout)
        report["status"] = "passed" if (
            (old_return and tested.returncode == 1 and "result == 0" in tested.stderr) or
            (not old_return and tested.returncode == 0)) else "failed"
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.assertNotIn("AddressSanitizer", tested.stderr)
        self.assertNotIn("runtime error:", tested.stderr)
        if old_return:
            self.assertEqual(tested.returncode, 1, tested.stdout + tested.stderr)
            self.assertIn("result == 0", tested.stderr)
        else:
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertGreater(report["harness"]["cases"], 300)

    def test_espeak_return_and_error_paths_asan_ubsan(self):
        self.run_harness(espeak=True)

    def test_legacy_return_and_error_paths_asan_ubsan(self):
        self.run_harness(espeak=False)

    def test_old_return_is_rejected_espeak_asan_ubsan(self):
        self.run_harness(espeak=True, old_return=True)

    def test_old_return_is_rejected_legacy_asan_ubsan(self):
        self.run_harness(espeak=False, old_return=True)


if __name__ == "__main__":
    unittest.main()
