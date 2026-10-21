"""Causal controller/service integration using original kernel queue/thread code."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tools/tests/fixtures"
INPUTS = (
    "apps/hiby_bluetooth.c", "apps/hiby_bluetooth.h",
    "apps/hiby_bluetooth_service.c", "apps/hiby_bluetooth_service.h",
    "apps/hiby_connectivity.c", "apps/hiby_connectivity.h",
    "apps/hiby_bluetooth_settings.c", "apps/hiby_bluetooth_settings.h",
    "apps/bluetooth_policy.c", "apps/bluetooth_policy.h",
    "apps/playback.c", "apps/audio_thread.h", "firmware/export/audio.h",
    "firmware/target/hosted/hiby/bluetooth-hiby.c",
    "firmware/kernel/thread.c", "firmware/kernel/thread-common.c",
    "firmware/kernel/queue.c", "firmware/asm/thread-unix.c",
    "firmware/common/linked_list.c",
    "tools/tests/fixtures/hiby_bluetooth_integration_fixture.c",
    "tools/tests/fixtures/hiby_bluetooth_integration_connectivity.c",
    "tools/tests/fixtures/hiby_bluetooth_command_fixture.c",
    "tools/tests/fixtures/hiby_bluetooth_service_framework.h",
    "tools/tests/test_hiby_bluetooth_integration.py",
)

CONFIG = """#pragma once
#define NUM_CORES 1
#define CPU 0
#define CURRENT_CORE 0
#define PLATFORM_HOSTED 2
#define PLATFORM_NATIVE 1
#define PLATFORM_GAME_CONSOLE 4
#define CONFIG_PLATFORM PLATFORM_HOSTED
#define HAVE_SIGALTSTACK_THREADS
#define HAVE_PRIORITY_SCHEDULING
#define HAVE_EXTENDED_MESSAGING_AND_NAME
#define IF_COP(...)
#define IF_COP_VOID(...) void
#define IF_COP_CORE(core) 0
#define INIT_ATTR
#define IBSS_ATTR
#define SHAREDBSS_ATTR
#define IDATA_ATTR
#define ICODE_ATTR
#define ICONST_ATTR
#define DATA_ATTR
#define HIBY_BT_HOST_TEST
#define HIBY_BT_SERVICE_HOST_TEST
#define HIBY_BT_SETTINGS_HOST_TEST
#define HIBY_CONNECTIVITY_HOST_TEST
#define HIBY_BT_NO_UI
#define HIBY_BT_REAL_FRAMEWORK_TEST
#define ROCKBOX_DIR "."
"""

SYSTEM = """#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include "config.h"
#include "gcc_extensions.h"
#define disable_irq() ((void)0)
#define enable_irq() ((void)0)
#define disable_irq_save() 0
#define restore_irq(level) ((void)(level))
#define ASSERT_CPU_MODE(...)
#define CPU_MODE_THREAD_CONTEXT 0
#define TIME_AFTER(first,second) ((long)((second)-(first)) < 0)
#define TIME_BEFORE(first,second) TIME_AFTER(second,first)
#define TIME_AFTER_EQ(first,second) ((long)((first)-(second)) >= 0)
#define TIME_BEFORE_EQ(first,second) TIME_AFTER_EQ(second,first)
#define ALIGN_UP(value,alignment) (((value)+(alignment)-1)&~((alignment)-1))
#define ALIGN_DOWN(value,alignment) ((value)&~((alignment)-1))
#define ARRAYLEN(array) (sizeof(array)/sizeof((array)[0]))
#define MIN(first,second) ((first)<(second)?(first):(second))
#define MAX(first,second) ((first)>(second)?(first):(second))
#define MIN_STACK_ALIGN 16
#define ALIGN_BUFFER(buffer,size,alignment) do { \\
    uintptr_t aligned = ALIGN_UP((uintptr_t)(buffer), alignment); \\
    (size) -= aligned - (uintptr_t)(buffer); \\
    (buffer) = (void *)aligned; (size) = ALIGN_DOWN(size, alignment); \\
} while (0)
#define container_of(pointer,type,member) ((type *)((char *)(pointer)-offsetof(type,member)))
static inline unsigned int find_first_set_bit(unsigned int value) { return __builtin_ctz(value); }
void fixture_core_idle(void);
static inline void core_sleep(void) { fixture_core_idle(); }
"""


def hashes():
    return {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in INPUTS}


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("gcc"),
                     "requires isolated Linux compiler and hosted context scheduler")
class BluetoothIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        central = project_materials_root(ROOT)
        requested = Path(os.environ.get("HIBY_BT_INTEGRATION_ROOT", central /
            "publication-position-20261021/service-review/integration"))
        area = confined_path(requested, central)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.area = area / (stamp + "-" + uuid.uuid4().hex[:8])
        cls.area.mkdir(parents=True)
        cls.commands = []
        cls.before = hashes()
        cls.addClassCleanup(cls.report)
        headers = cls.area / "headers"
        headers.mkdir()
        (headers / "config.h").write_text(CONFIG, encoding="ascii")
        (headers / "system.h").write_text(SYSTEM, encoding="ascii")
        (headers / "cpu.h").write_text('#include "system.h"\n', encoding="ascii")
        (headers / "core_alloc.h").write_text("#pragma once\n", encoding="ascii")
        (headers / "general.h").write_text('''#include "system.h"
static inline void **find_array_ptr(void **array, void *value)
{
    while (*array && *array != value) ++array;
    return array;
}
static inline void remove_array_ptr(void **array, void *value)
{
    array = find_array_ptr(array, value);
    if (*array) do { *array = *(array + 1); ++array; } while (*array);
}
''', encoding="ascii")
        (headers / "debug.h").write_text("#pragma once\n#define DEBUGF(...) ((void)0)\n", encoding="ascii")
        (headers / "panic.h").write_text("#pragma once\nvoid panicf(const char *format, ...) __attribute__((noreturn));\n", encoding="ascii")
        (headers / "file.h").write_text("#include <fcntl.h>\n#include <unistd.h>\n", encoding="ascii")
        (headers / "rbpaths.h").write_text('#define ROCKBOX_DIR "."\n', encoding="ascii")
        (headers / "audio-pause-test.h").write_text(
            "#define logf(...) ((void)0)\n#define LOGFQUEUE(...) ((void)0)\n", encoding="ascii")
        (headers / "hiby-bluetooth-service-test.h").write_text(
            '#include "hiby_bluetooth_service_framework.h"\n', encoding="ascii")
        (headers / "hiby_bluetooth_service_language.h").write_text(
            "enum { LANG_HIBY_BT_CONNECTED, LANG_HIBY_BT_CONNECTION_LOST, "
            "LANG_HIBY_BT_RECONNECT_FAILED, SERVICE_LANGUAGE_COUNT };\n", encoding="ascii")
        binaries = cls.area / "bin"
        binaries.mkdir()
        cls.run_command(["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                         str(FIXTURES / "hiby_bluetooth_command_fixture.c"),
                         "-o", str(binaries / "bluetoothctl")])
        includes = [headers, ROOT / "apps", ROOT / "firmware/kernel/include",
                    ROOT / "firmware/kernel", ROOT / "firmware/include",
                    ROOT / "firmware", ROOT / "firmware/target/hosted/hiby",
                    ROOT / "firmware/export", FIXTURES]
        sources = [FIXTURES / "hiby_bluetooth_integration_fixture.c",
                   FIXTURES / "hiby_bluetooth_integration_connectivity.c",
                   ROOT / "apps/hiby_bluetooth.c", ROOT / "apps/bluetooth_policy.c",
                   ROOT / "apps/hiby_bluetooth_settings.c",
                   ROOT / "firmware/target/hosted/hiby/bluetooth-hiby.c",
                   ROOT / "firmware/kernel/thread.c", ROOT / "firmware/kernel/thread-common.c",
                   ROOT / "firmware/kernel/queue.c", ROOT / "firmware/common/linked_list.c"]
        cls.binaries = []
        for sanitized in (False, True):
            binary = cls.area / ("integration-ubsan" if sanitized else "integration")
            arguments = ["gcc", "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                         "-Wno-override-init", "-pthread",
                         "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                         "-include", str(headers / "config.h"),
                         '-DHIBY_BT_BIN_DIRECTORY="' + str(binaries) + '"']
            if sanitized:
                arguments += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            for directory in includes:
                arguments += ["-I", str(directory)]
            arguments += list(map(str, sources))
            for symbol in ("hiby_bt_backend_execute", "hiby_bluetooth_service_completed",
                           "hiby_bluetooth_service_observe", "fsync"):
                arguments += ["-Wl,--wrap=" + symbol]
            arguments += ["-o", str(binary)]
            cls.run_command(arguments)
            cls.binaries.append(binary)

    @classmethod
    def run_command(cls, arguments, cwd=None, expect_failure=False):
        def disable_core():
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        result = subprocess.run(arguments, cwd=cwd or cls.area, capture_output=True,
                                text=True, timeout=40, preexec_fn=disable_core,
                                env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"})
        import signal
        accepted = result.returncode == 0 if not expect_failure else (
            result.returncode == -signal.SIGABRT and "pauses == (unsigned int)valid_loss" in result.stderr)
        cls.commands.append({"argv": list(map(str, arguments)), "cwd": str(cwd or cls.area),
                             "returncode": result.returncode, "stdout": result.stdout,
                             "stderr": result.stderr, "expected_failure": expect_failure,
                             "accepted": accepted})
        (cls.area / "commands.json").write_text(json.dumps(cls.commands, indent=2), encoding="utf-8")
        if (result.returncode != 0) != expect_failure:
            raise AssertionError(result.stdout + result.stderr)
        if expect_failure:
            if result.returncode != -signal.SIGABRT or "pauses == (unsigned int)valid_loss" not in result.stderr:
                raise AssertionError("Negative control failed for an unrelated reason: " + result.stderr)
        return result

    @classmethod
    def report(cls):
        after = hashes()
        accepted = all(command["accepted"] for command in cls.commands)
        (cls.area / "report.json").write_text(json.dumps({
            "source_project": str(ROOT), "inputs_before": cls.before, "inputs_after": after,
            "unchanged": cls.before == after, "commands": cls.commands,
            "accepted_command_outcomes": accepted,
            "actual": ["controller", "service policy/pause guard", "preferences", "connectivity",
                       "backend REFRESH for IT10-IT13", "kernel queue/thread", "hosted sigaltstack contexts",
                       "playback guarded sender and state-commit handler"],
            "mocked": ["monitor", "PCM status/device", "IAP/fade", "speech",
                       "backend outside IT10-IT13", "audio dispatch surrounding shared guarded handler"],
            "source_copies": [], "host_audio": False, "host_radio": False,
            "device_access": False, "full_product_build": False,
        }, indent=2), encoding="utf-8")
        print("Controller/service integration evidence:", cls.area, flush=True)

    def test_fifteen_causal_interleavings(self):
        for binary in self.binaries:
            for case in range(1, 16):
                with self.subTest(binary=binary.name, case=case):
                    directory = self.area / (binary.name + f"-IT{case:02d}")
                    directory.mkdir()
                    arguments = [str(binary), str(case)]
                    if case == 14:
                        arguments.append("route")
                    self.run_command(arguments, cwd=directory)
            for variant in ("idle", "paused", "resume", "duplicate", "play-after-enqueue",
                            "resume-before-capture", "play-before-capture",
                            "resume-ready-before-capture", "play-ready-before-capture"):
                with self.subTest(binary=binary.name, case=14, variant=variant):
                    directory = self.area / (binary.name + "-IT14-" + variant)
                    directory.mkdir()
                    self.run_command([str(binary), "14", variant], cwd=directory)
            for case in (1, 4):
                with self.subTest(binary=binary.name, case=case, negative=True):
                    directory = self.area / (binary.name + f"-negative-IT{case:02d}")
                    directory.mkdir()
                    self.run_command([str(binary), str(case), "unsafe-pause"], cwd=directory,
                                     expect_failure=True)
        self.assertEqual(self.before, hashes())

    def test_original_audio_dispatch_and_guard_contract(self):
        source = (ROOT / "apps/playback.c").read_text(encoding="utf-8")
        self.assertIn("case Q_AUDIO_PAUSE_GUARDED:", source)
        self.assertIn("audio_on_pause_guarded((struct guarded_pause_request *)ev->data);", source)
        body = source.split("static void audio_on_pause_guarded(", 1)[1].split("\n}", 1)[0]
        self.assertLess(body.index("request->begin(request->context)"), body.index("play_status = PLAY_PAUSED;"))
        self.assertLess(body.index("play_status = PLAY_PAUSED;"), body.index("request->end(request->context);"))
        self.assertLess(body.index("request->end(request->context);"), body.index("audio_apply_pause(true);"))
        self.assertNotIn("audio_queue_send", body)


if __name__ == "__main__":
    unittest.main()
