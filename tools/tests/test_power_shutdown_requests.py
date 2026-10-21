"""Test actual shutdown and queue functions without hardware or a full kernel."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, ensure_ignored_directories, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "tools/tests/fixtures/power_shutdown_requests_fixture.c"
INPUTS = (
    "firmware/powermgmt.c", "firmware/export/powermgmt.h",
    "firmware/kernel/queue.c", "firmware/kernel/include/queue.h",
    "firmware/kernel/kernel-internal.h", "firmware/kernel/include/corelock.h",
    "firmware/kernel/thread-internal.h",
    "firmware/kernel/include/tick.h", "firmware/export/audio.h",
    "firmware/export/button.h", "firmware/drivers/button_queue.c",
    "firmware/target/hosted/hiby/r1/button-target.h", "firmware/export/config/hibyr1.h",
    "tools/tests/test_power_shutdown_requests.py", FIXTURE,
)
LEGACY_BUTTON_FUNCTION_SHA256 = "a12e8adba8156d195ae3e9fd38e33b2b150ab6c45cabfd3406855ce1db47c594"
CONFIGURATIONS = {
    "hosted": (),
    "hosted-recording": ("HAVE_RECORDING",),
    "hosted-nano": ("HAVE_RECORDING", "IPOD_NANO2G"),
    "hosted-simulator": ("SIMULATOR", "IAUDIO_X5"),
    "native": ("FIXTURE_NATIVE", "HAVE_RECORDING", "IAUDIO_X5"),
    "native-dual": ("FIXTURE_NATIVE", "FIXTURE_DUALCORE", "HAVE_RECORDING", "IAUDIO_M5"),
    "native-cowon": ("FIXTURE_NATIVE", "COWON_D2"),
    "non-touch": ("FIXTURE_NO_TOUCH",),
    "bootloader": ("FIXTURE_NATIVE", "BOOTLOADER", "IAUDIO_X5"),
}


def without_includes(source):
    return re.sub(r'^\s*#include[^\n]*', '', source, flags=re.MULTILINE)


def actual_function(source, name, occurrence=0):
    pattern = re.compile(r'^(?:static\s+)?(?:inline\s+)?(?:void|bool|int)\s+(?:INIT_ATTR\s+)?'
                         + re.escape(name) + r'\([^;{}]*\)\s*\{.*?^\}', re.MULTILINE | re.DOTALL)
    matches = list(pattern.finditer(source))
    if len(matches) <= occurrence:
        raise AssertionError("Missing actual function: " + name)
    return matches[occurrence][0]


@unittest.skipUnless(sys.platform.startswith("linux"), "Requires Linux C fixture compiler; run in WSL")
class PowerShutdownRequestsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc")
        if compiler is None:
            raise unittest.SkipTest("gcc unavailable")
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.evidence = confined_path(central / "r1-connectivity-shortcut-final-20261016/power" / stamp, central)
        cls.evidence.mkdir(parents=True, exist_ok=False)
        cls.commands = []
        cls.cases = []
        cls.runs = []
        cls.extractions = {}
        cls.binaries = {}
        cls.setup_complete = False
        cls.before = cls.hashes()
        cls.addClassCleanup(cls.report)
        print("Shutdown request evidence:", cls.evidence, flush=True)
        sources = {name: (ROOT / name).read_text(encoding="utf-8") for name in INPUTS}
        cls.sources = sources
        harness = cls.harness(sources)
        harness_path = cls.evidence / "shutdown-actual-extracted.c"
        harness_path.write_text(harness, encoding="utf-8")
        condition = "if (sys_shutdown_common(SHUTDOWN_REQUEST_POWEROFF))"
        if harness.count(condition) != 1:
            raise AssertionError("Expected one actual poweroff coalescing condition")
        mutant = harness.replace(condition, "sys_shutdown_common(SHUTDOWN_REQUEST_POWEROFF);")
        mutant_path = cls.evidence / "shutdown-unconditional-broadcast-mutant.c"
        mutant_path.write_text(mutant, encoding="utf-8")
        button_body = cls.extract("firmware/drivers/button_queue.c", "button_queue_try_post")
        legacy_body, replacement_count = re.subn(
            r'        if \(force_post\)\n        \{\n#if defined\(HAVE_TOUCHSCREEN\).*?^        \}',
            "        if (force_post)\n            queue_remove_from_head(&button_queue, button);",
            button_body, count=1, flags=re.MULTILINE | re.DOTALL)
        if replacement_count != 1 or hashlib.sha256(legacy_body.encode()).hexdigest() != LEGACY_BUTTON_FUNCTION_SHA256:
            raise AssertionError("Negative control must reconstruct the exact reviewed old button function")
        cls.extractions["legacy_button_queue_try_post"] = LEGACY_BUTTON_FUNCTION_SHA256
        legacy_path = cls.evidence / "shutdown-legacy-button-function.c"
        legacy_path.write_text(harness.replace(button_body, legacy_body), encoding="utf-8")
        builds = [(name, harness_path, definitions) for name, definitions in CONFIGURATIONS.items()]
        builds += [("mutant", mutant_path, ()), ("legacy-button", legacy_path, ()),
                   ("legacy-button-native", legacy_path, ("FIXTURE_NATIVE", "FIXTURE_DUALCORE"))]
        for mode in ("strict", "ubsan"):
            for name, source_path, definitions in builds:
                binary = cls.evidence / (name + "-" + mode)
                command = [compiler, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                           "-pthread", "-g", str(source_path), "-o", str(binary)]
                command.extend("-D" + item for item in definitions)
                if mode == "ubsan":
                    command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
                result = cls.command(command)
                if result.returncode:
                    raise AssertionError(name + ": " + result.stderr)
                cls.check_imports(binary)
                cls.binaries[(name, mode)] = binary
        cls.setup_complete = True

    @classmethod
    def extract(cls, source_name, name, occurrence=0):
        body = actual_function(cls.sources[source_name], name, occurrence)
        cls.extractions[source_name + ":" + name + ":" + str(occurrence)] = hashlib.sha256(body.encode()).hexdigest()
        return body

    @classmethod
    def harness(cls, sources):
        queue_source = sources["firmware/kernel/queue.c"]
        registry = queue_source[queue_source.index("static struct\n{"):
                                queue_source.index("} all_queues SHAREDBSS_ATTR;") + len("} all_queues SHAREDBSS_ATTR;")]
        parts = [registry, "#ifdef HAVE_EXTENDED_MESSAGING_AND_NAME"]
        for name in ("queue_release_sender_inner", "queue_release_sender", "queue_release_all_senders",
                     "queue_enable_queue_send", "queue_do_unblock_sender", "queue_do_auto_reply", "queue_do_fetch_sender"):
            parts.append(cls.extract("firmware/kernel/queue.c", name))
        parts += ["#else", "#define queue_release_all_senders(queue)",
                  "#define queue_do_unblock_sender(sender, index)", "#define queue_do_auto_reply(sender)",
                  "#define queue_do_fetch_sender(sender, index)", "#endif"]
        for name in ("queue_wake_waiter_inner", "queue_wake_waiter"):
            parts.append(cls.extract("firmware/kernel/queue.c", name))
        for name in ("queue_init", "queue_post", "queue_empty", "queue_clear", "queue_count",
                     "queue_broadcast", "init_queues"):
            parts.append(cls.extract("firmware/kernel/queue.c", name))
        parts += ["#ifdef HAVE_EXTENDED_MESSAGING_AND_NAME",
                  cls.extract("firmware/kernel/queue.c", "queue_peek_ex"),
                  cls.extract("firmware/kernel/queue.c", "queue_remove_from_head"),
                  "#else", cls.extract("firmware/kernel/queue.c", "queue_remove_from_head", 1), "#endif"]
        power = sources["firmware/powermgmt.c"]
        state = power[power.index("static int shutdown_timeout"):power.index("void handle_auto_poweroff(void);")]
        requests = power[power.index("#ifndef BOOTLOADER\nstatic bool sys_shutdown_common"):
                         power.index("void set_sleeptimer_duration")]
        cls.extractions["firmware/powermgmt.c:state_and_guard"] = hashlib.sha256(state.encode()).hexdigest()
        cls.extractions["firmware/powermgmt.c:requests_and_cancel"] = hashlib.sha256(requests.encode()).hexdigest()
        kernel = sources["firmware/kernel/kernel-internal.h"]
        assertion = kernel[kernel.index("#if defined(DEBUG) || defined(SIMULATOR)"):
                           kernel.index("static inline void kernel_init(void)")]
        constants = []
        for name, source_name in (
                ("HZ", "firmware/kernel/include/tick.h"),
                ("POWER_THREAD_STEP_TICKS", "firmware/export/powermgmt.h"),
                ("AUDIO_STATUS_RECORD", "firmware/export/audio.h"),
                ("AUDIO_STATUS_PAUSE", "firmware/export/audio.h"),
                ("BUTTON_POWER", "firmware/target/hosted/hiby/r1/button-target.h"),
                ("BUTTON_VOL_UP", "firmware/target/hosted/hiby/r1/button-target.h"),
                ("BUTTON_VOL_DOWN", "firmware/target/hosted/hiby/r1/button-target.h"),
                ("BUTTON_TOUCHSCREEN", "firmware/export/button.h"),
                ("BUTTON_REPEAT", "firmware/export/button.h"),
                ("BUTTON_REL", "firmware/export/button.h")):
            match = re.search(r'^#define ' + name + r'\s+[^\n]+', sources[source_name], re.MULTILINE)
            if match is None:
                raise AssertionError("Missing actual constant: " + name)
            constants.append(match[0])
        buttons = "static struct event_queue button_queue SHAREDBSS_ATTR;\n"
        buttons += cls.extract("firmware/drivers/button_queue.c", "button_queue_try_post") + "\n"
        buttons += cls.extract("firmware/drivers/button_queue.c", "button_queue_init")
        thread = sources["firmware/kernel/thread-internal.h"]
        wakeup = re.search(r'^enum wakeup_thread_protocol\s*\{.*?^\};', thread, re.MULTILINE | re.DOTALL)
        if wakeup is None:
            raise AssertionError("Missing actual wakeup protocol")
        replacements = {
            "CONSTANTS": "\n".join(constants),
            "CORELOCK_HEADER": without_includes(sources["firmware/kernel/include/corelock.h"]),
            "QUEUE_HEADER": without_includes(sources["firmware/kernel/include/queue.h"]),
            "QUEUE_ASSERT": assertion,
            "WAKEUP_PROTOCOL": wakeup[0],
            "QUEUE_SOURCE": "\n".join(parts),
            "POWER_STATE": state,
            "POWER_REQUESTS": requests,
            "BUTTON_SOURCE": buttons,
        }
        harness = sources[FIXTURE]
        for name, value in replacements.items():
            harness = harness.replace("@" + name + "@", value)
        if re.search(r'@[A-Z_]+@', harness):
            raise AssertionError("Unexpanded fixture placeholder")
        return harness

    @classmethod
    def hashes(cls):
        return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in INPUTS}

    @classmethod
    def command(cls, arguments):
        try:
            result = subprocess.run(arguments, cwd=cls.evidence, capture_output=True, text=True,
                                    timeout=30, env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
        except subprocess.TimeoutExpired:
            cls.commands.append({"arguments": [str(item) for item in arguments], "timed_out": True})
            raise
        cls.commands.append({"arguments": [str(item) for item in arguments], "returncode": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        return result

    @classmethod
    def check_imports(cls, binary):
        result = cls.command(["nm", "-u", str(binary)])
        if result.returncode:
            raise AssertionError(result.stderr)
        imports = {line.split()[-1].split("@")[0] for line in result.stdout.splitlines() if line.split()}
        forbidden = imports.intersection({"reboot", "system", "sync", "socket", "ioctl", "open",
                                         "open64", "kill", "execve", "fork", "posix_spawn"})
        forbidden.update(name for name in imports if name.startswith(("__atomic_", "__sync_")))
        if forbidden:
            raise AssertionError("Unmocked external operations: " + str(forbidden))

    @classmethod
    def report(cls):
        after = cls.hashes()
        report = {
            "schema": "power-shutdown-requests:1", "source_before": cls.before, "source_after": after,
            "sources_unchanged": cls.before == after, "extracted_body_sha256": cls.extractions,
            "setup_complete": cls.setup_complete, "commands": cls.commands, "cases": cls.cases, "runs": cls.runs,
            "passed": cls.setup_complete and bool(cls.cases) and all(item["passed"] for item in cls.cases)
                      and cls.before == after,
            "scope": "Actual shutdown state/guard/request/cancel, extracted real queue init/post/broadcast/peek/head removal, sender release/mapping and wakeup helpers; actual button_queue_try_post; actual 32-slot layout and kernel overflow assertion",
            "limitations": "Not full kernel/scheduler, native ARM corelock assembly, physical IRQ/hardware, GUI, SDL or full native/Windows build validation. Corelocks are modeled by distinct pthread mutexes and per-core IRQ exclusion; hosted IRQ macros are no-op models.",
            "delivery_boundary": "Cancellation does not retract already queued or in-flight notifications. Producer-side reboot escalation cannot change a poweroff event already being handled by clean_shutdown.",
            "mixed_raw_hazard_expected": False,
            "legacy_button_function_sha256": LEGACY_BUTTON_FUNCTION_SHA256,
            "repeat_coalescing_boundary": "Existing protected queue_peek_ex removes exact repeat IDs and queue_post appends latest data. The pair is not one atomic transaction; multiple simultaneous producers may retain transient duplicate repeats. Nonmatching events and kernel overflow assertions remain intact.",
            "acceptance_complete": False,
            "pending_acceptance": ["Fresh full native build", "Fresh full Windows build",
                                   "Arranged private live long-Power stress with the final binary"],
            "hardware_calls_mocked": True, "simulator_launched": False,
        }
        (cls.evidence / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if cls.before != after:
            raise AssertionError("Fixture input changed during tests")

    def tearDown(self):
        result = self._outcome.result
        failed = any(getattr(test, "test_case", test).id() == self.id()
                     for test, unused in result.failures + result.errors)
        skipped = [reason for test, reason in result.skipped if test.id() == self.id()]
        self.cases.append({"name": self.id(), "passed": not failed, "skipped": skipped})

    def run_case(self, scenario, *, configurations=None, expected=0):
        configurations = configurations or [name for name in CONFIGURATIONS if name != "bootloader"]
        for (name, mode), binary in self.binaries.items():
            if name not in configurations:
                continue
            with self.subTest(configuration=name, mode=mode):
                result = self.command([str(binary), scenario])
                self.runs.append({"configuration": name, "mode": mode, "scenario": scenario,
                                  "expected_returncode": expected, "returncode": result.returncode})
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertNotIn("runtime error:", result.stderr)
                if expected == 0:
                    self.assertIn("PASS " + scenario, result.stdout)
                else:
                    self.assertIn("queue_post ovf: depth=33 capacity=32", result.stderr)

    def test_poweroff_repeats_coalesce(self):
        self.run_case("repeat-poweroff")

    def test_reboot_repeats_coalesce(self):
        self.run_case("repeat-reboot")

    def test_reboot_upgrades_without_resetting_deadline(self):
        self.run_case("upgrade")

    def test_poweroff_never_downgrades_reboot(self):
        self.run_case("no-downgrade")

    def test_cancel_rearms_and_preserves_pmu_resets(self):
        self.run_case("cancel-rearm")

    def test_inactive_cancel_is_idempotent(self):
        self.run_case("cancel-inactive")

    def test_cancel_during_publication_allows_a_new_request(self):
        self.run_case("cancel-in-flight")

    def test_recording_and_nano_deadlines(self):
        self.run_case("recording")

    def test_repeats_do_not_extend_deadline(self):
        self.run_case("deadline")

    def test_reboot_timeout_still_forces_poweroff(self):
        self.run_case("expiry")

    def test_cancel_before_expiry(self):
        self.run_case("cancel-before-expiry")

    def test_broadcast_preserves_other_events_and_queues(self):
        self.run_case("preserve-events")

    def test_irq_restore_is_nested(self):
        self.run_case("nested-irq")

    def test_hosted_guard_does_not_change_sdl_global_irq_mask(self):
        self.run_case("guard-irq-boundary")

    def test_concurrent_duplicate_requests(self):
        self.run_case("concurrent-repeat")

    def test_concurrent_request_type_upgrade(self):
        self.run_case("concurrent-upgrade")

    def test_concurrent_cancel_and_countdown(self):
        self.run_case("concurrent-cancel-step")

    def test_bootloader_remains_noop(self):
        self.run_case("bootloader", configurations=["bootloader"])

    def test_actual_queue_capacity(self):
        self.run_case("queue-capacity")

    def test_real_queue_asserts_on_post_33(self):
        self.run_case("queue-overflow", configurations=["hosted"], expected=86)

    def test_unconditional_broadcast_mutant_overflows_on_post_33(self):
        self.run_case("repeat-poweroff", configurations=["mutant"], expected=86)

    def test_mixed_system_head_and_raw_repeats_are_bounded(self):
        self.run_case("mixed-raw", configurations=["hosted", "native-dual"])

    def test_exact_old_button_function_still_overflows_on_post_33(self):
        self.run_case("mixed-raw", configurations=["legacy-button", "legacy-button-native"], expected=86)

    def test_raw_repeat_only_queue_stays_bounded(self):
        self.run_case("raw-only", configurations=["hosted", "native-dual"])

    def test_draining_system_head_allows_repeat_coalescing(self):
        self.run_case("mixed-drained", configurations=["hosted", "native-dual"])

    def test_only_matching_button_repeat_ids_are_coalesced(self):
        self.run_case("exact-repeat-ids", configurations=["hosted", "native-dual"])

    def test_all_pending_exact_matches_are_removed(self):
        self.run_case("many-matching-repeats", configurations=["hosted", "native-dual"])

    def test_press_release_and_system_event_order_and_data_survive(self):
        self.run_case("repeat-edges", configurations=["hosted", "native-dual"])

    def test_system_ids_with_repeat_bit_are_not_coalesced(self):
        self.run_case("system-repeat-bit", configurations=["hosted", "native-dual"])

    def test_touch_repeat_coordinates_are_updated(self):
        self.run_case("touch-coordinates", configurations=["hosted", "native-dual"])

    def test_full_queue_matching_repeat_is_replaced(self):
        self.run_case("full-matching-repeat", configurations=["hosted", "native-dual"])

    def test_full_queue_without_matching_repeat_still_asserts(self):
        self.run_case("full-nonmatching-repeat", configurations=["hosted", "native-dual"], expected=86)

    def test_non_touch_posting_policy_is_unchanged(self):
        self.run_case("non-touch-policy", configurations=["non-touch"])

    def test_coalesced_repeat_still_wakes_a_waiter(self):
        self.run_case("repeat-wakeup", configurations=["hosted", "native-dual"])

    def test_removed_repeat_sender_is_released_other_senders_preserved(self):
        self.run_case("repeat-senders", configurations=["hosted", "native-dual"])

    def test_native_dualcore_repeat_producers_use_protected_queue_apis(self):
        self.run_case("concurrent-button-repeats", configurations=["native-dual"])

    def test_real_power_thread_uses_guarded_timeout_helpers(self):
        power = self.sources["firmware/powermgmt.c"]
        step = actual_function(power.replace("static inline void", "static void"), "power_thread_step")
        self.assertIn("shutdown_timeout_step();", step)
        self.assertNotIn("shutdown_timeout -=", step)
        self.assertEqual(power.count("!shutdown_timeout_active() && query_force_shutdown()"), 2)
        self.assertIn("static int shutdown_timeout SHAREDBSS_ATTR", power)
        self.assertIn("shutdown_request SHAREDBSS_ATTR", power)
        self.assertIn("#define HAVE_TOUCHSCREEN", self.sources["firmware/export/config/hibyr1.h"])

    def test_mips_hosted_strict_compile_and_lock_free_guard(self):
        compiler = project_materials_root(ROOT) / (
            "toolchains/hiby-r1-20261010/prefix/bin/mipsel-rockbox-linux-gnu-gcc")
        if not compiler.is_file():
            self.skipTest("Pinned R1 compiler unavailable; full native build remains parent-owned")
        output = self.evidence / "shutdown-hosted-mips.o"
        result = self.command([str(compiler), "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                               "-pthread", "-DHAVE_RECORDING", "-c",
                               str(self.evidence / "shutdown-actual-extracted.c"), "-o", str(output)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.check_imports(output)


if __name__ == "__main__":
    unittest.main()
