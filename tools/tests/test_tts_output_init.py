"""Fault-inject the actual voice/TTS initialization code with explicit host mocks."""

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
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root
from test_tts_coverage import extract_block


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_FAILURES = ("allocation", "allocation-zero", "buffer-data", "voice-thread")

PREFIX = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "voice_thread.h"

#define logf(...) ((void)0)
#define DEBUGF(...) ((void)0)
#define MAX_PATH 260
#define ROCKBOX_DIR "/.rockbox"
#define TIMEOUT_BLOCK -1
#define Q_VOICE_PLAY_PCM 1
#define PRIORITY_VOICE 5
#define PRIORITY_PLAYBACK 4
#define CPU 0
#ifdef TEST_FEATURE_ARGUMENTS
#define IF_PRIO(...) __VA_ARGS__
#define IF_COP(...) __VA_ARGS__
#define THREAD_ARGUMENTS , int priority, int core
#else
#define IF_PRIO(...)
#define IF_COP(...)
#define THREAD_ARGUMENTS
#endif

enum failure {
    FAIL_NONE, FAIL_ALLOCATION, FAIL_ALLOCATION_ZERO, FAIL_DATA,
    FAIL_OUTPUT_THREAD, FAIL_WORKER, FAIL_ENGINE, FAIL_INITIALIZER,
    FAIL_CATALOG, FAIL_LANGUAGE
};
static enum failure fault;
struct event_queue { bool active, enabled; unsigned int owner; };
static struct event_queue voice_queue;
static int voice_queue_sender_list, ops;
static unsigned int voice_thread_id;
static int voice_buf_hid;
static struct voice_buffer { int frame[8]; } *voice_buf;
static long voice_stack[16];
static const char voice_thread_name[] = "voice";
static void *allocated_buffer;
static int allocated_handle, allocations, frees, output_creations, enables;
static void voice_thread(void) {}

#ifdef HAVE_ESPEAK
struct mutex { bool initialized; };
static struct mutex tts_mutex, tts_request_mutex;
static struct event_queue tts_wakeup;
static bool initialized, catalog_ready, voice_pcm_paused;
static uint64_t voice_pcm_elapsed_us;
static unsigned int sample_rate, worker_id;
static long tts_stack[(128 * 1024) / sizeof(long)];
static uint32_t voice_offsets[2];
static const char *last_error = "";
static struct { bool tts_enabled; char tts_language[40], tts_variant[40]; }
    global_settings = { .tts_enabled = true };
static int worker_creations, engine_initializations, initializer_creations;
static void tts_worker(void) {}
#ifdef SIMULATOR
static const char *sim_root_dir = "/simdisk";
#else
struct semaphore { int count; };
static struct semaphore initialization_done;
static int initialization_frequency, boost_balance, joins;
static void initialize_native_engine(void);
static void cpu_boost(bool enabled) { boost_balance += enabled ? 1 : -1; }
static void semaphore_init(struct semaphore *semaphore, int maximum, int count)
{ assert(maximum == 1); semaphore->count = count; }
static void semaphore_release(struct semaphore *semaphore) { ++semaphore->count; }
static int semaphore_wait(struct semaphore *semaphore, int timeout)
{ assert(timeout == TIMEOUT_BLOCK && semaphore->count == 1); --semaphore->count; return 0; }
static void thread_wait(unsigned int identifier) { assert(identifier == 11); ++joins; }
static void thread_exit(void) {}
#endif
static void mutex_init(struct mutex *mutex) { mutex->initialized = true; }
static int rb_espeak_init(const char *path)
{
    assert(strstr(path, ROCKBOX_DIR));
    ++engine_initializations;
    return fault == FAIL_ENGINE ? -1 : 22050;
}
static bool resolve_voice(char *language, char *variant)
{
    strcpy(language, "en");
    variant[0] = '\0';
    return fault != FAIL_LANGUAGE;
}
static const char *system_language_name(void) { return "english"; }
static bool load_voice_strings(const char *catalog)
{ assert(!strcmp(catalog, "english")); return fault != FAIL_CATALOG; }
static intptr_t queue_send(struct event_queue *queue, int message, intptr_t data)
{
    assert(queue == &voice_queue && queue->active && queue->enabled);
    assert(queue->owner != 0 && message == Q_VOICE_PLAY_PCM && data != 0);
    return 1;
}
#endif

static int core_alloc_ex(size_t size, const void *callbacks)
{
    assert(callbacks == &ops && allocated_buffer == NULL);
    if (fault == FAIL_ALLOCATION || fault == FAIL_ALLOCATION_ZERO)
        return fault == FAIL_ALLOCATION ? -1 : 0;
    allocated_buffer = malloc(size);
    assert(allocated_buffer);
    allocated_handle = ++allocations;
    return allocated_handle;
}
static void *core_get_data(int handle)
{
    assert(handle == allocated_handle && allocated_buffer);
    return fault == FAIL_DATA ? NULL : allocated_buffer;
}
static int core_free(int handle)
{
    assert(handle > 0 && handle == allocated_handle && allocated_buffer);
    free(allocated_buffer);
    allocated_buffer = NULL;
    ++frees;
    return 0;
}
static void queue_init(struct event_queue *queue, bool registered)
{
    assert(!registered && !queue->active);
    queue->active = true;
    queue->enabled = false;
    queue->owner = 0;
}
static void queue_delete(struct event_queue *queue)
{
    assert(queue->active);
    queue->active = queue->enabled = false;
    queue->owner = 0;
}
static void queue_enable_queue_send(struct event_queue *queue, void *senders,
                                    unsigned int owner)
{
    assert(queue == &voice_queue && senders == &voice_queue_sender_list);
    assert(queue->active && !queue->enabled && owner != 0 && owner == voice_thread_id);
    queue->enabled = true;
    queue->owner = owner;
    ++enables;
}
static unsigned int create_thread(void (*function)(void), void *stack, size_t size,
                                  unsigned int flags, const char *name THREAD_ARGUMENTS)
{
    assert(flags == 0);
#ifdef TEST_FEATURE_ARGUMENTS
    assert(core == CPU && (priority == PRIORITY_VOICE || priority == PRIORITY_PLAYBACK));
#endif
    if (!strcmp(name, "voice"))
    {
        assert(function == voice_thread && stack == voice_stack && size == sizeof(voice_stack));
        assert(allocated_buffer && voice_buf && voice_queue.active && !voice_queue.enabled);
        ++output_creations;
        return fault == FAIL_OUTPUT_THREAD ? 0 : 17;
    }
#ifdef HAVE_ESPEAK
    assert(stack == tts_stack && size == sizeof(tts_stack));
    if (!strcmp(name, "espeak init"))
    {
        ++initializer_creations;
        if (fault == FAIL_INITIALIZER)
            return 0;
#ifndef SIMULATOR
        assert(function == initialize_native_engine);
        function();
#endif
        return 11;
    }
    assert(!strcmp(name, "espeak") && function == tts_worker && voice_thread_id != 0);
    assert(tts_wakeup.active && tts_mutex.initialized && tts_request_mutex.initialized);
    ++worker_creations;
    return fault == FAIL_WORKER ? 0 : 23;
#else
    assert(false);
    return 0;
#endif
}
"""

SUFFIX = r"""
static bool initialize_output(void)
{
#ifdef HAVE_ESPEAK
    return tts_init();
#else
    return voice_thread_init();
#endif
}
static void check_output_failure(void)
{
    assert(!initialize_output());
    assert(voice_thread_id == 0 && voice_buf_hid == 0 && voice_buf == NULL);
    assert(allocated_buffer == NULL && allocations == frees);
    assert(!voice_queue.active && enables == 0);
#ifdef HAVE_ESPEAK
    assert(!initialized && !catalog_ready && !tts_is_available() && worker_id == 0);
    assert(!tts_wakeup.active && worker_creations == 0);
    assert(!strcmp(last_error, "Cannot initialize speech output"));
    const int16_t sample = 1;
    assert(!voice_play_pcm(&sample, 1, 22050, 0));
#endif
}
static void check_recovery(void)
{
    fault = FAIL_NONE;
    assert(initialize_output());
    assert(voice_thread_id == 17 && voice_buf_hid > 0 && voice_buf == allocated_buffer);
    assert(allocations == frees + 1 && enables == 1 && voice_queue.owner == 17);
    int saved_allocations = allocations, saved_creations = output_creations;
#ifdef HAVE_ESPEAK
    assert(initialized && catalog_ready && tts_is_available() && worker_id == 23);
    assert(sample_rate == 22050 && !*last_error);
    int saved_workers = worker_creations, saved_engines = engine_initializations;
    const int16_t sample = 1;
    assert(voice_play_pcm(&sample, 1, 22050, 0));
    global_settings.tts_enabled = false;
    assert(!tts_is_available() && initialized && catalog_ready);
    global_settings.tts_enabled = true;
    assert(tts_is_available());
#endif
    assert(initialize_output());
    assert(allocations == saved_allocations && output_creations == saved_creations && enables == 1);
    voice_thread_init();
    assert(allocations == saved_allocations);
#ifdef HAVE_ESPEAK
    assert(worker_creations == saved_workers && engine_initializations == saved_engines);
#ifndef SIMULATOR
    assert(boost_balance == 0 && joins <= initializer_creations);
#endif
#endif
}
static void cleanup_fixture(void)
{
#ifdef HAVE_ESPEAK
    if (tts_wakeup.active)
        queue_delete(&tts_wakeup);
#endif
    if (voice_queue.active)
        queue_delete(&voice_queue);
    if (allocated_buffer)
        core_free(voice_buf_hid);
    voice_buf_hid = 0;
    voice_buf = NULL;
    voice_thread_id = 0;
    assert(allocated_buffer == NULL && allocations == frees);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    if (!strcmp(scenario, "allocation")) fault = FAIL_ALLOCATION;
    else if (!strcmp(scenario, "allocation-zero")) fault = FAIL_ALLOCATION_ZERO;
    else if (!strcmp(scenario, "buffer-data")) fault = FAIL_DATA;
    else if (!strcmp(scenario, "voice-thread")) fault = FAIL_OUTPUT_THREAD;
#ifdef HAVE_ESPEAK
    else if (!strcmp(scenario, "worker")) fault = FAIL_WORKER;
    else if (!strcmp(scenario, "engine")) fault = FAIL_ENGINE;
    else if (!strcmp(scenario, "initializer")) fault = FAIL_INITIALIZER;
    else if (!strcmp(scenario, "catalog")) fault = FAIL_CATALOG;
    else if (!strcmp(scenario, "language")) fault = FAIL_LANGUAGE;
#endif
    else assert(false);

    if (fault <= FAIL_OUTPUT_THREAD)
    {
        check_output_failure();
        check_output_failure();
        fault = FAIL_OUTPUT_THREAD;
        check_output_failure();
    }
#ifdef HAVE_ESPEAK
    else if (fault == FAIL_WORKER)
    {
        for (int attempt = 0; attempt < 2; ++attempt)
        {
            assert(!tts_init() && !initialized && !catalog_ready && !tts_is_available());
            assert(worker_id == 0 && voice_thread_id == 17 && allocations == 1 && frees == 0);
            assert(!tts_wakeup.active && enables == 1 && output_creations == 1);
            assert(!strcmp(last_error, "Cannot create the synthesis thread"));
        }
    }
    else if (fault == FAIL_ENGINE || fault == FAIL_INITIALIZER)
    {
        assert(!tts_init() && !initialized && !catalog_ready && !tts_is_available());
        assert(allocations == 0 && output_creations == 0 && worker_creations == 0);
        assert(!voice_queue.active && !tts_wakeup.active && *last_error);
    }
    else
    {
        for (int attempt = 0; attempt < 2; ++attempt)
        {
            assert(!tts_init() && initialized && !catalog_ready && !tts_is_available());
            assert(worker_id == 23 && voice_thread_id == 17 && allocations == 1 && frees == 0);
            assert(worker_creations == 1 && enables == 1 && *last_error);
        }
    }
#endif
    check_recovery();
    cleanup_fixture();
    printf("PASS %s: failure/repeated failure/failed retry/recovery/idempotence, no buffer leak\n", scenario);
    return 0;
}
"""


class TtsOutputInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("An existing host C compiler is required; run under WSL")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.workspace = confined_path(central / "tts-output-init-tests" / stamp, central)
        cls.workspace.mkdir(parents=True, exist_ok=False)
        voice = (ROOT / "apps/voice_thread.c").read_text(encoding="utf-8")
        tts = (ROOT / "apps/tts.c").read_text(encoding="utf-8")
        body = extract_block(voice, "bool voice_thread_init(")
        body += "\n#ifdef HAVE_ESPEAK\n#ifndef SIMULATOR\n"
        body += extract_block(tts, "static void initialize_native_engine(") + "\n#endif\n"
        body += extract_block(tts, "bool tts_init(")
        body += extract_block(tts, "bool tts_is_available(")
        body += extract_block(voice, "struct voice_pcm_info\n") + ";\n"
        body += extract_block(voice, "bool voice_play_pcm(") + "\n#endif\n"
        cls.source = cls.workspace / "output-init.c"
        cls.source.write_text(PREFIX + body + SUFFIX, encoding="utf-8")
        (cls.workspace / "config.h").write_text("", encoding="utf-8")
        sources = ("apps/voice_thread.c", "apps/voice_thread.h", "apps/tts.c",
                   "tools/tests/test_tts_output_init.py", "tools/tests/test_tts_coverage.py")
        cls.inputs = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
        cls.write_json(cls.workspace / "provenance.json", {
            "source_project": str(ROOT), "source_sha256": cls.inputs, "argv": sys.argv,
            "fixture_sha256": hashlib.sha256(cls.source.read_bytes()).hexdigest(),
            "scope": "Actual initializer/readiness/PCM entry functions with allocation/thread/engine mocks",
            "retention": "Central fault-injection source/binaries/logs retained; no product or checkout copies",
        })
        cls.compiled = {}
        cls.addClassCleanup(cls.verify_sources)
        print("TTS output initialization evidence:", cls.workspace, flush=True)

    @staticmethod
    def write_json(path, value):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")

    @classmethod
    def verify_sources(cls):
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in cls.inputs}
        cls.write_json(cls.workspace / "inputs-after.json", {
            "source_sha256": after, "sources_stable": cls.inputs == after})
        if after != cls.inputs:
            raise AssertionError("Output initialization sources changed during validation")

    def execute(self, directory, label, command):
        self.write_json(directory / (label + "-command.json"), {"argv": command, "cwd": str(directory)})
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=60,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=1"))
        (directory / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        self.write_json(directory / (label + "-result.json"), {"returncode": result.returncode})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def variant(self, espeak, simulator=False, standard="c99", sanitizer="undefined", clang=False):
        label = ("espeak" if espeak else "stock") + ("-simulator" if simulator else "-native")
        label += "-" + standard + "-" + sanitizer.replace(",", "-") + ("-clang" if clang else "")
        if label not in self.compiled:
            directory = self.workspace / (label + "-" + uuid.uuid4().hex[:8])
            directory.mkdir(exist_ok=False)
            executable = directory / ("output-test.exe" if os.name == "nt" else "output-test")
            compiler = [shutil.which("clang")] if clang else self.compiler
            command = compiler + ["-std=" + standard, "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                                  "-Wstrict-prototypes", "-pedantic-errors", "-fsanitize=" + sanitizer,
                                  "-fno-sanitize-recover=all", "-I", str(self.workspace),
                                  "-I", str(ROOT / "apps"), str(self.source), "-o", str(executable)]
            if espeak:
                command.append("-DHAVE_ESPEAK")
            if simulator:
                command.append("-DSIMULATOR")
            if standard == "c11":
                command.extend(["-DTEST_FEATURE_ARGUMENTS", "-DHAVE_PRIORITY_SCHEDULING"])
            if "address" in sanitizer and os.name != "nt":
                command.extend(["-fno-pie", "-no-pie"])
            self.execute(directory, "compile", command)
            self.compiled[label] = directory, executable
        return self.compiled[label]

    def run_scenarios(self, variant, scenarios):
        directory, executable = variant
        for scenario in scenarios:
            with self.subTest(variant=directory.name, scenario=scenario):
                self.execute(directory, "run-" + scenario, [str(executable), scenario])

    def test_stock_output_failures_retry_without_leaks(self):
        for standard in ("c99", "c11"):
            self.run_scenarios(self.variant(False, standard=standard), OUTPUT_FAILURES)

    def test_tts_output_failures_prevent_availability_and_recover(self):
        for simulator in (False, True):
            for standard in ("c99", "c11"):
                self.run_scenarios(self.variant(True, simulator, standard), OUTPUT_FAILURES)

    def test_worker_failure_retains_one_output_buffer_and_recovers(self):
        for simulator in (False, True):
            self.run_scenarios(self.variant(True, simulator), ("worker",))

    def test_engine_catalog_and_initializer_failure_flags(self):
        for simulator in (False, True):
            cases = ("engine", "catalog", "language") + (() if simulator else ("initializer",))
            self.run_scenarios(self.variant(True, simulator), cases)

    def test_address_and_undefined_sanitizers(self):
        for espeak, simulator in ((False, False), (True, False), (True, True)):
            cases = OUTPUT_FAILURES + (("worker", "catalog") if espeak else ())
            self.run_scenarios(self.variant(espeak, simulator, "c11", "address,undefined"), cases)

    def test_clang_output_initializer_contract(self):
        if not shutil.which("clang"):
            self.skipTest("Clang is not installed; no installation attempted")
        for espeak in (False, True):
            cases = OUTPUT_FAILURES + (("worker", "engine", "initializer", "catalog", "language") if espeak else ())
            self.run_scenarios(self.variant(espeak, standard="c11", clang=True), cases)


if __name__ == "__main__":
    unittest.main(verbosity=2)
