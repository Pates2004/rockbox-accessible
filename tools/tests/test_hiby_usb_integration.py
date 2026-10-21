"""Compile actual USB acknowledgement/recovery paths without device operations."""

from datetime import datetime, timezone
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
from project_materials import ensure_ignored_directories, project_materials_root
from test_accessibility_integration import balanced_definition, function, without_includes


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    "firmware/usb.c", "firmware/export/usb.h", "firmware/SOURCES",
    "firmware/target/hosted/hiby/usb-storage-hiby.h",
    "apps/gui/usb_screen.c", "apps/lang/english.lang", "apps/lang/polski.lang",
    "tools/tests/test_hiby_usb_integration.py",
)


HARNESS = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include "usb-storage-hiby.h"
#define BOOTLOADER
#define HAVE_USB_POWER
#define NORETURN_ATTR
#define DEBUGF(...) ((void)0)
#define USB_ENABLE_STORAGE
#define USB_DRIVER_MASS_STORAGE 1
#define USBPOWER_BTN_IGNORE 0
#define USB_MODE_MASS_STORAGE 0
#define USB_MODE_CHARGE 1
#define USB_EXTRACTED 0
#define USB_INSERTED 1
#define USB_POWERED 2
#define USB_SCREENDUMP 3
#define SYS_USB_CONNECTED 10
#define SYS_USB_CONNECTED_ACK 11
#define SYS_USB_DISCONNECTED 12
#define CONFIG_STORAGE 0
#define STORAGE_MMC 1
#define HZ 100
struct queue_event { long id; intptr_t data; };
struct event_queue { int unused; };
static struct event_queue usb_queue;
static bool exclusive_storage_enabled, exclusive_storage_requested;
#ifdef HIBY_R1
static bool exclusive_storage_recovery;
#endif
static bool usb_host_present;
static int usb_num_acks_to_expect;
static uint32_t usb_broadcast_seqnum = 0x80000000;
static int usb_state = USB_EXTRACTED;
static int usb_mode = USB_MODE_MASS_STORAGE;
static bool usb_power_only;
static int acknowledgers, connected, disconnected, notified;
static int prepared, exported, restored, legacy_unmount, legacy_mount;
static int legacy_enable, legacy_init, legacy_idle, legacy_reset, panics;
static bool prepare_success = true, export_success = true;
static bool restore_success = true, safe_to_resume = true;
static struct queue_event events[8];
static unsigned int event_count, event_cursor, checks;
static jmp_buf thread_done;
#define CHECK(value) do { ++checks; if (!(value)) { \
    fprintf(stderr, "check failed at %d: %s\n", __LINE__, #value); return 1; } } while (0)
static struct hiby_usb_storage_status result(bool success)
{
    struct hiby_usb_storage_status status = {0};
    status.success = success;
    status.safe_to_resume = safe_to_resume;
    return status;
}
struct hiby_usb_storage_status hiby_usb_storage_target_prepare(void)
{ ++prepared; return result(prepare_success); }
struct hiby_usb_storage_status hiby_usb_storage_target_export(void)
{ ++exported; return result(export_success); }
struct hiby_usb_storage_status hiby_usb_storage_target_restore(void)
{ ++restored; return result(restore_success); }
bool hiby_usb_storage_target_safe_to_resume(void) { return safe_to_resume; }
int queue_broadcast(long id, intptr_t data)
{
    (void)data;
    if (id == SYS_USB_CONNECTED) ++connected;
    if (id == SYS_USB_DISCONNECTED) ++disconnected;
    return 1 + acknowledgers;
}
void usb_signal_class_notify(int driver, int value)
{ (void)driver; (void)value; ++notified; }
void disk_unmount_all(void) { ++legacy_unmount; }
int disk_mount_all(void) { ++legacy_mount; return 1; }
int storage_init(void) { ++legacy_init; return 0; }
void storage_soft_reset(void) { ++legacy_reset; }
void storage_enable(bool enabled) { (void)enabled; ++legacy_enable; }
void usb_enable(bool enabled) { (void)enabled; ++legacy_enable; }
void cpu_idle_mode(bool enabled) { (void)enabled; ++legacy_idle; }
void sleep(int ticks) { (void)ticks; }
void panicf(const char *message, int value) { (void)message; (void)value; ++panics; }
void reset_poweroff_timer(void) {}
static bool usb_do_screendump(void) { return false; }
static void usb_stack_enable(bool enabled) { (void)enabled; }
int button_status(void) { return 0; }
void queue_wait(struct event_queue *queue, struct queue_event *event)
{
    (void)queue;
    if (event_cursor == event_count) longjmp(thread_done, 1);
    *event = events[event_cursor++];
}
void usb_request_exclusive_storage(void);
void usb_release_exclusive_storage(void);
"""


SCENARIOS = r"""
static void run_events(void)
{
    event_cursor = 0;
    if (!setjmp(thread_done)) usb_thread();
}
static void acknowledge(uint32_t sequence)
{
    event_count = 1;
    events[0].id = SYS_USB_CONNECTED_ACK;
    events[0].data = sequence;
    run_events();
}
#ifdef HIBY_R1
static void cable_event(long event)
{
    event_count = 1;
    events[0].id = event;
    events[0].data = 0;
    run_events();
}
#endif
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    usb_host_present = true;
    if (!strcmp(argv[1], "ack"))
    {
        acknowledgers = 2;
        usb_request_exclusive_storage();
        CHECK(connected == 1 && !exclusive_storage_enabled && !prepared);
        acknowledge(usb_broadcast_seqnum - 1);
        CHECK(usb_num_acks_to_expect == 2 && !prepared);
        acknowledge(usb_broadcast_seqnum);
        CHECK(usb_num_acks_to_expect == 1 && !prepared);
        acknowledge(usb_broadcast_seqnum);
        CHECK(exclusive_storage_enabled && notified == 1);
#ifdef HIBY_R1
        CHECK(prepared == 1 && exported == 1 && !exclusive_storage_recovery);
#else
        CHECK(legacy_unmount == 1 && !prepared && !exported);
#endif
        acknowledge(usb_broadcast_seqnum);
        CHECK(notified == 1);
        usb_release_exclusive_storage();
        CHECK(!exclusive_storage_enabled && !exclusive_storage_requested && disconnected == 1);
        CHECK(!panics);
    }
    else if (!strcmp(argv[1], "zero"))
    {
        usb_request_exclusive_storage();
        CHECK(exclusive_storage_enabled && notified == 1 && connected == 1);
        usb_request_exclusive_storage();
        CHECK(connected == 1 && notified == 1);
        usb_release_exclusive_storage();
        usb_release_exclusive_storage();
        CHECK(disconnected == 1 && !exclusive_storage_requested);
        usb_request_exclusive_storage();
        CHECK(connected == 2 && notified == 2 && exclusive_storage_enabled);
    }
#ifdef HIBY_R1
    else if (!strcmp(argv[1], "unsafe-release-charge-cycle") ||
             !strcmp(argv[1], "unsafe-entry-charge-cycle"))
    {
        bool entry_failed = !strcmp(argv[1], "unsafe-entry-charge-cycle");
        usb_host_present = false;
        export_success = !entry_failed;
        safe_to_resume = !entry_failed;
        cable_event(USB_INSERTED);
        CHECK(exclusive_storage_requested && !disconnected);
        CHECK(exclusive_storage_enabled == !entry_failed);
        safe_to_resume = restore_success = false;
        cable_event(USB_EXTRACTED);
        CHECK(restored == 1 && exclusive_storage_requested && !disconnected);
        usb_mode = USB_MODE_CHARGE;
        cable_event(USB_INSERTED);
        CHECK(usb_power_only && exclusive_storage_requested && !disconnected);
        CHECK(exclusive_storage_enabled == !entry_failed);
        restore_success = safe_to_resume = true;
        cable_event(USB_EXTRACTED);
        CHECK(restored == 2 && disconnected == 1 && !exclusive_storage_requested);
        CHECK(!exclusive_storage_enabled && !exclusive_storage_recovery);
    }
    else if (!strcmp(argv[1], "prepare-failure"))
    {
        prepare_success = false;
        usb_request_exclusive_storage();
        CHECK(prepared == 1 && exported == 0 && notified == 0);
        CHECK(!exclusive_storage_requested && !exclusive_storage_enabled);
        CHECK(!exclusive_storage_recovery && disconnected == 1);
        acknowledge(usb_broadcast_seqnum);
        usb_release_exclusive_storage();
        CHECK(prepared == 1 && !restored && disconnected == 1);
        CHECK(!legacy_unmount && !legacy_enable && !legacy_init);
    }
    else if (!strcmp(argv[1], "export-failure"))
    {
        acknowledgers = 1;
        export_success = false;
        usb_request_exclusive_storage();
        acknowledge(usb_broadcast_seqnum);
        CHECK(prepared == 1 && exported == 1 && !notified && disconnected == 1);
        CHECK(!exclusive_storage_requested && !exclusive_storage_recovery);
        CHECK(!exclusive_storage_enabled && !legacy_unmount);
    }
    else if (!strcmp(argv[1], "unsafe-entry"))
    {
        export_success = false;
        safe_to_resume = false;
        usb_request_exclusive_storage();
        CHECK(exclusive_storage_requested && !exclusive_storage_enabled);
        CHECK(exclusive_storage_recovery && !disconnected && !notified);
        restore_success = false;
        usb_release_exclusive_storage();
        CHECK(restored == 1 && exclusive_storage_requested && exclusive_storage_recovery);
        CHECK(!disconnected && !notified);
        restore_success = true;
        safe_to_resume = true;
        usb_release_exclusive_storage();
        CHECK(restored == 2 && !exclusive_storage_recovery && !exclusive_storage_requested);
        CHECK(disconnected == 1 && !exclusive_storage_enabled);
    }
    else if (!strcmp(argv[1], "unsafe-release"))
    {
        usb_request_exclusive_storage();
        restore_success = false;
        safe_to_resume = false;
        usb_release_exclusive_storage();
        CHECK(exclusive_storage_requested && exclusive_storage_enabled && !disconnected);
        restore_success = true;
        safe_to_resume = true;
        usb_release_exclusive_storage();
        CHECK(!exclusive_storage_requested && !exclusive_storage_enabled && disconnected == 1);
        CHECK(restored == 2 && !legacy_mount && !panics);
    }
#endif
    else if (!strcmp(argv[1], "disconnect-before-ack"))
    {
        acknowledgers = 2;
        usb_request_exclusive_storage();
        uint32_t first = usb_broadcast_seqnum;
        usb_release_exclusive_storage();
        CHECK(!exclusive_storage_requested && !usb_num_acks_to_expect && disconnected == 1);
        acknowledge(first);
        CHECK(!notified && !prepared && !legacy_unmount);
        usb_request_exclusive_storage();
        acknowledge(first);
        CHECK(usb_num_acks_to_expect == 2 && !notified);
        acknowledge(usb_broadcast_seqnum);
        acknowledge(usb_broadcast_seqnum);
        CHECK(exclusive_storage_enabled && notified == 1);
    }
    else return 3;
    printf("{\"checks\":%u}\n", checks);
    return 0;
}
"""


def slave_functions(text):
    sections = text.split("static inline bool usb_slave_mode(bool on)")
    if len(sections) != 3:
        raise AssertionError("Expected software-stack and hardware-stack slave functions")
    return [balanced_definition("static inline bool usb_slave_mode(bool on)" + section,
                                r"^static inline bool usb_slave_mode\(bool on\)\s*\{")
            for section in sections[1:]]


class HibyUsbIntegrationTests(unittest.TestCase):
    def run(self, result=None):
        actual_result = result if result is not None else self.defaultTestResult()
        failures_before = len(actual_result.failures) + len(actual_result.errors)
        returned = super().run(actual_result)
        if hasattr(type(self), "events"):
            self.events.append(dict(kind="unittest", name=self.id(),
                passed=len(actual_result.failures) + len(actual_result.errors) == failures_before))
        return returned

    @classmethod
    def setUpClass(cls):
        cls.inputs = {path: (ROOT / path).read_text(encoding="utf-8") for path in INPUTS}
        cls.before = cls.hashes()
        materials = project_materials_root(ROOT)
        ensure_ignored_directories(materials.parent, (materials.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.workspace = materials / "r1-usb-integration-20261011" / stamp
        cls.workspace.mkdir(parents=True, exist_ok=False)
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        cls.compiled = {}
        cls.events = []

    @classmethod
    def hashes(cls):
        return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in INPUTS}

    @classmethod
    def tearDownClass(cls):
        after = cls.hashes()
        report = dict(project=str(ROOT), before=cls.before, after=after,
                      source_unchanged=cls.before == after, runs=cls.events,
                      checks=sum(event.get("checks", 0) for event in cls.events),
                      expectations_passed=all(event["passed"] for event in cls.events),
                      device_operations=False, hardware_tested=False,
                      limitations="Actual extracted generic USB paths; target calls are mocks")
        (cls.workspace / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if cls.before != after:
            raise AssertionError("USB integration inputs changed during tests")

    def compiled_case(self, target, stack, mode, scenario, *, mutation=False):
        key = (target, stack, mode, "old-charge-reset" if mutation else "current")
        if key not in self.compiled:
            name = "-".join(key)
            text = self.inputs["firmware/usb.c"]
            functions = slave_functions(text)
            harness = HARNESS + functions[0 if stack == "software" else 1]
            harness += function(text, "usb_enter_exclusive_storage")
            configure = text[text.index("#else  /* !HAVE_USBSTACK */"):]
            configure = function(configure, "usb_configure_drivers")
            if mutation:
                guard = "#if defined(HIBY_R1)\n        if (exclusive_storage_enabled || exclusive_storage_recovery)\n            break;\n#endif\n"
                self.assertEqual(configure.count(guard), 1)
                configure = configure.replace(guard, "", 1)
            harness += configure
            for selected in ("usb_set_host_present", "usb_thread", "usb_request_exclusive_storage",
                             "usb_release_exclusive_storage"):
                if selected == "usb_thread":
                    harness += balanced_definition(text, r"^static void NORETURN_ATTR usb_thread\(void\)\s*\{")
                else:
                    harness += function(text, selected)
            harness += SCENARIOS
            path = self.workspace / (name + ".c")
            binary = self.workspace / (name + (".exe" if os.name == "nt" else ""))
            path.write_text(harness, encoding="utf-8")
            command = self.compiler + ["-std=" + ("c11" if mode == "ubsan" else mode),
                "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I" + str(ROOT / "firmware/target/hosted/hiby"), str(path), "-o", str(binary)]
            if target == "r1":
                command += ["-DHIBY_R1"]
            if mode == "ubsan":
                command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
            result = subprocess.run(command, text=True, capture_output=True, timeout=90)
            (self.workspace / (name + "-compile.log")).write_text(
                shlex.join(command) + "\n" + result.stdout + result.stderr, encoding="utf-8")
            self.events.append(dict(kind="compile", name=name, passed=result.returncode == 0))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.compiled[key] = binary
        result = subprocess.run([str(self.compiled[key]), scenario], text=True,
                                capture_output=True, timeout=20,
                                env={**os.environ, "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"})
        name = "-".join(key) + "-" + scenario
        (self.workspace / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        expected = (result.returncode != 0 and "check failed" in result.stderr
                    if mutation else result.returncode == 0)
        event = dict(kind="mutation" if mutation else "runtime", name=name, passed=expected)
        if result.returncode == 0:
            event.update(json.loads(result.stdout))
        self.events.append(event)
        self.assertTrue(expected, result.stdout + result.stderr)

    def test_r1_acknowledgements_and_recovery_paths(self):
        for stack in ("software", "hardware"):
            for mode in ("c99", "c11", "ubsan"):
                for scenario in ("ack", "zero", "prepare-failure", "export-failure",
                                 "unsafe-entry", "unsafe-release", "disconnect-before-ack",
                                 "unsafe-entry-charge-cycle", "unsafe-release-charge-cycle"):
                    with self.subTest(stack=stack, mode=mode, scenario=scenario):
                        self.compiled_case("r1", stack, mode, scenario)

    def test_other_targets_preserve_storage_paths(self):
        for stack in ("software", "hardware"):
            for mode in ("c99", "c11", "ubsan"):
                for scenario in ("ack", "zero", "disconnect-before-ack"):
                    with self.subTest(stack=stack, mode=mode, scenario=scenario):
                        self.compiled_case("other", stack, mode, scenario)

    def test_charge_reconnect_regression_rejects_old_reset(self):
        for stack in ("software", "hardware"):
            for scenario in ("unsafe-entry-charge-cycle", "unsafe-release-charge-cycle"):
                with self.subTest(stack=stack, scenario=scenario):
                    self.compiled_case("r1", stack, "c11", scenario, mutation=True)

    def test_default_mode_is_only_changed_for_native_r1_app(self):
        header = without_includes(self.inputs["firmware/export/usb.h"])
        for defines, expected in (([], "USB_MODE_MASS_STORAGE"),
                (["HIBY_R1"], "USB_MODE_CHARGE"),
                (["HIBY_R1", "SIMULATOR"], "USB_MODE_MASS_STORAGE"),
                (["HIBY_R1", "BOOTLOADER"], "USB_MODE_MASS_STORAGE")):
            result = subprocess.run(self.compiler + ["-E", "-P", "-x", "c", "-",
                "-DHAVE_USB_POWER"] + ["-D" + define for define in defines],
                input=header + "\nUSBMODE_DEFAULT\n", text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip().splitlines()[-1], expected)

    def test_usb_screen_snapshots_error_before_settings_and_announces_after_recovery(self):
        text = function(self.inputs["apps/gui/usb_screen.c"], "gui_usb_screen_run")
        self.assertLess(text.index("handle_usb_events(title)"), text.index("hiby_usb_storage_target_status()"))
        self.assertLess(text.index("hiby_usb_storage_target_status()"), text.index("settings_apply(true)"))
        self.assertLess(text.index("viewportmanager_theme_undo"), text.index("storage_status.safe_to_resume"))
        for label in ("LANG_HIBY_USB_UNVERIFIED", "LANG_HIBY_USB_BUSY", "LANG_HIBY_USB_FAILED"):
            self.assertIn(label, text)
            for language in ("english", "polski"):
                catalog = self.inputs["apps/lang/" + language + ".lang"]
                block = re.search(r"<phrase>\s*id: " + label + r"\b.*?</phrase>", catalog, re.DOTALL)
                self.assertIsNotNone(block)
                self.assertEqual(block.group().count("hibyr1:"), 3)
                self.assertEqual(block.group().count("*: none"), 3)


if __name__ == "__main__":
    unittest.main()
