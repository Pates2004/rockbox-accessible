import datetime
import os
from pathlib import Path
import shutil
import unittest

from test_espeak_native_runtime import build_runtime, command, ROOT, NATIVE
from project_materials import project_materials_root


PROBE = r"""
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include "native_runtime.h"

static unsigned int counter;
static unsigned int protected_value;
static unsigned int ready_value;

static void *exercise(void *context)
{
    (void)context;
    for (unsigned int iteration = 0; iteration < 50000; ++iteration)
    {
        while (!rb_espeak_engine_acquire())
            sched_yield();
        assert(counter == protected_value);
        ++counter;
        sched_yield();
        protected_value = counter;
        assert(!rb_espeak_engine_acquire());
        rb_espeak_engine_release();
    }
    return NULL;
}

static void *publish(void *context)
{
    (void)context;
    ready_value = 1234567;
    rb_espeak_engine_mark_ready();
    return NULL;
}

int main(void)
{
    pthread_t workers[4];
    assert(!rb_espeak_engine_ready());
    for (unsigned int index = 0; index < 4; ++index)
        assert(!pthread_create(&workers[index], NULL, exercise, NULL));
    for (unsigned int index = 0; index < 4; ++index)
        assert(!pthread_join(workers[index], NULL));
    assert(counter == 200000 && protected_value == counter);
    assert(!pthread_create(&workers[0], NULL, publish, NULL));
    while (!rb_espeak_engine_ready())
        sched_yield();
    assert(ready_value == 1234567);
    assert(!pthread_join(workers[0], NULL));
    assert(rb_espeak_engine_acquire());
    rb_espeak_engine_release();
    puts("PASS hosted exclusion, reentry and readiness publication");
    return 0;
}
"""


@unittest.skipUnless(os.name == "posix" and shutil.which("gcc"), "Run under WSL/POSIX")
class HostedRuntimeTests(unittest.TestCase):
    def test_hosted_guard_serializes_actual_parallel_threads(self):
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        build = project_materials_root(ROOT) / "espeak-hosted-runtime" / timestamp
        flags = ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        objects = build_runtime(build, flags, hosted=True)
        (build / "probe.c").write_text(PROBE, encoding="utf-8")
        executable = build / "hosted-runtime-probe"
        command(["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", *flags,
                 "-I" + str(NATIVE), build / "probe.c", *objects,
                 "-Wl,--gc-sections", "-pthread", "-lm", "-o", executable], build, "link")
        result = command([executable], build, "result")
        self.assertIn("PASS hosted exclusion, reentry and readiness publication", result)
        print(f"Hosted atomic guard evidence: {build}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
