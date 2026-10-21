"""Controlled fork/exec regressions for the isolated PCM test runner."""

import ctypes
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import select
import selectors
import shutil
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_hiby_pcm as pcm


PROGRAM = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <unistd.h>

int main(int argument_count, char **arguments)
{
    struct rlimit limit = {0, 0};
    assert(setrlimit(RLIMIT_CORE, &limit) == 0);
    if (argument_count == 4 && !strcmp(arguments[1], "--helper"))
    {
        if (getpgrp() != getpid())
            assert(setpgid(0, 0) == 0);
        assert(signal(SIGTERM, SIG_IGN) != SIG_ERR);
        char temporary[4096];
        assert(snprintf(temporary, sizeof(temporary), "%s.new", arguments[2]) < (int)sizeof(temporary));
        FILE *marker = fopen(temporary, "w");
        assert(marker);
        fprintf(marker, "{\"leader\":%ld,\"pid\":%ld,\"group\":%ld,\"session\":%ld}\n",
                strtol(arguments[3], NULL, 10), (long)getpid(), (long)getpgrp(), (long)getsid(0));
        assert(fclose(marker) == 0);
        assert(rename(temporary, arguments[2]) == 0);
        close(0); close(1); close(2);
        for (;;) pause();
    }
    assert(argument_count == 3);
    char leader[32];
    snprintf(leader, sizeof(leader), "%ld", (long)getpid());
    pid_t helper = fork();
    assert(helper >= 0);
    if (!helper)
    {
        execl(arguments[0], arguments[0], "--helper", arguments[2], leader, NULL);
        _exit(91);
    }
    for (unsigned int attempt = 0; access(arguments[2], F_OK) != 0; ++attempt)
    {
        assert(attempt < 200);
        usleep(5000);
    }
    assert(fputs("fixture-ready\n", stdout) >= 0 && fflush(stdout) == 0);
    assert(fputs("fixture-stderr\n", stderr) >= 0 && fflush(stderr) == 0);
    if (!strcmp(arguments[1], "success")) return 0;
    if (!strcmp(arguments[1], "failure")) return 7;
    if (!strcmp(arguments[1], "abort")) abort();
    if (!strcmp(arguments[1], "ignore-term"))
        assert(signal(SIGTERM, SIG_IGN) != SIG_ERR);
    for (;;) pause();
}
'''


def stop_owned_fixture(binary, marker):
    if not marker.exists():
        return
    identity = json.loads(marker.read_text())
    for pid in (identity["pid"], identity["leader"]):
        descriptor = None
        try:
            descriptor = os.pidfd_open(pid)
            state = pcm.process_state(pid)
            if Path(f"/proc/{pid}/exe").resolve() != binary.resolve() or state["session"] != identity["session"]:
                continue
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            if not select.select([descriptor], [], [], 2)[0]:
                raise RuntimeError("Controlled helper did not exit after SIGKILL")
            try:
                os.waitid(os.P_PIDFD, descriptor, os.WEXITED | os.WNOHANG)
            except ChildProcessError:
                pass
        except (FileNotFoundError, ProcessLookupError):
            pass
        finally:
            if descriptor is not None:
                os.close(descriptor)


def controlled_worker(binary, directory, scenario):
    library = ctypes.CDLL(None, use_errno=True)
    library.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    library.prctl.restype = ctypes.c_int
    if library.prctl(36, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), "prctl subreaper")
    marker, sentinel_marker = directory / "helper.json", directory / "sentinel.json"
    report = {"passed": False, "scenario": scenario, "record": {}, "controller_pid": os.getpid()}
    sentinel = None
    try:
        if scenario == "sentinel":
            sentinel = subprocess.Popen([str(binary), "--helper", str(sentinel_marker), str(os.getpid())],
                                        start_new_session=True, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 2
            while not sentinel_marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert sentinel_marker.exists()
        mode = scenario if scenario in ("success", "failure", "abort", "ignore-term") else "hang"
        command = [str(binary), mode, str(marker)]
        if scenario == "old-timeout":
            try:
                subprocess.run(command, capture_output=True, timeout=0.6, start_new_session=True, cwd=directory)
            except subprocess.TimeoutExpired:
                identity = json.loads(marker.read_text())
                state = pcm.process_state(identity["pid"])
                assert state["state"] != "Z" and state["group"] == identity["pid"]
                report["old_behavior_left_live_helper"] = identity
            else:
                raise AssertionError("Old timeout behavior did not time out")
        else:
            original_select = selectors.DefaultSelector.select
            original_selector = selectors.DefaultSelector
            original_signal = signal.pidfd_send_signal
            injected = {"read": False, "cleanup": False}
            def select(instance, timeout=None):
                result = original_select(instance, timeout)
                if scenario in ("read-exception", "primary-cleanup-error") and marker.exists() and not injected["read"]:
                    injected["read"] = True
                    raise OSError("capture-probe failure")
                return result
            def send(descriptor, signum, *arguments):
                if scenario in ("primary-cleanup-error", "cleanup-error-success") and not injected["cleanup"]:
                    injected["cleanup"] = True
                    raise OSError(errno.EIO, "cleanup-probe failure")
                return original_signal(descriptor, signum, *arguments)
            def selector():
                if scenario == "setup-exception":
                    deadline = time.monotonic() + 2
                    while not marker.exists() and time.monotonic() < deadline:
                        time.sleep(0.005)
                    assert marker.exists()
                    raise OSError("setup-probe failure")
                return original_selector()
            original_communicate = subprocess.Popen.communicate
            def communicate(process, *arguments, **keywords):
                if scenario == "drain-exception":
                    raise OSError("drain-probe failure")
                return original_communicate(process, *arguments, **keywords)
            if scenario == "cleanup-error-success":
                command[1] = "success"
            with mock.patch.object(selectors.DefaultSelector, "select", select), \
                 mock.patch.object(selectors, "DefaultSelector", selector), \
                 mock.patch.object(signal, "pidfd_send_signal", send), \
                 mock.patch.object(subprocess.Popen, "communicate", communicate):
                try:
                    result = pcm.run_isolated_case(command, timeout=0.6, record=report["record"], cwd=directory)
                except BaseException as error:
                    report["exception"] = type(error).__name__
                    report["exception_text"] = str(error)
                    report["notes"] = getattr(error, "__notes__", [])
                    if scenario == "setup-exception":
                        assert isinstance(error, OSError) and "setup-probe" in str(error)
                    elif scenario == "drain-exception":
                        assert isinstance(error, subprocess.TimeoutExpired)
                        assert any("drain-probe" in note for note in report["notes"])
                    elif scenario in ("read-exception", "primary-cleanup-error"):
                        assert isinstance(error, OSError) and "capture-probe" in str(error)
                        if scenario == "primary-cleanup-error":
                            assert any("cleanup-probe" in note for note in report["notes"])
                    elif scenario == "cleanup-error-success":
                        assert isinstance(error, RuntimeError) and "cleanup-probe" in str(error)
                    else:
                        assert isinstance(error, subprocess.TimeoutExpired)
                        assert b"fixture-ready" in error.output and b"fixture-stderr" in error.stderr
                else:
                    expected = {"success": 0, "failure": 7, "abort": -signal.SIGABRT}
                    assert scenario in expected and result.returncode == expected[scenario]
                    assert b"fixture-ready" in result.stdout and b"fixture-stderr" in result.stderr
            identity = json.loads(marker.read_text())
            assert identity["session"] == report["record"]["owned_session"]["pid"]
            assert identity["group"] == identity["pid"] != identity["leader"]
            assert not Path(f"/proc/{identity['pid']}").exists(), "Owned helper was not killed and reaped"
            assert not Path(f"/proc/{identity['leader']}").exists(), "Owned leader was not reaped"
            report["helper_gone"] = identity
            if scenario == "sentinel":
                assert sentinel.poll() is None
                report["unrelated_session_untouched"] = json.loads(sentinel_marker.read_text())
        report["passed"] = True
    finally:
        stop_owned_fixture(binary, marker)
        stop_owned_fixture(binary, sentinel_marker)
        if sentinel is not None:
            sentinel.wait(timeout=2)
        with (directory / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)


@unittest.skipUnless(sys.platform.startswith("linux") and hasattr(os, "P_PIDFD") and hasattr(os, "pidfd_open") and
                     hasattr(signal, "pidfd_send_signal") and shutil.which("gcc"), "requires Linux pidfds and gcc")
class PcmCaseCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = pcm.project_materials_root(pcm.ROOT) / "r1-gesture-extensions-20261016/pcm-timeout/cleanup-tests" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8])
        cls.evidence.mkdir(parents=True)
        cls.hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(pcm.__file__), Path(__file__))}
        source = cls.evidence / "descendant.c"
        source.write_text(PROGRAM, encoding="utf-8")
        cls.binaries, cls.results = [], []
        for sanitized in (False, True):
            binary = cls.evidence / ("descendant-ubsan" if sanitized else "descendant-ordinary")
            command = ["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", str(source), "-o", str(binary)]
            if sanitized:
                command += ["-fsanitize=undefined", "-fno-sanitize-recover=undefined"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            cls.binaries.append(binary)

    def scenario(self, scenario):
        for binary in self.binaries:
            with self.subTest(binary=binary.name):
                directory = self.evidence / (scenario + "-" + binary.name)
                directory.mkdir()
                try:
                    result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--controlled-worker",
                                             str(binary), str(directory), scenario],
                                            capture_output=True, text=True, timeout=8)
                finally:
                    stop_owned_fixture(binary, directory / "helper.json")
                    stop_owned_fixture(binary, directory / "sentinel.json")
                record = json.loads((directory / "report.json").read_text())
                record["controller_returncode"] = result.returncode
                record["passed"] = record["passed"] and result.returncode == 0
                self.results.append(record)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(record["passed"])

    def test_timeout_kills_exec_helper_in_separate_group(self):
        self.scenario("timeout")

    def test_success_and_failure_also_clean_leftover_helpers(self):
        for scenario in ("success", "failure", "abort"):
            self.scenario(scenario)

    def test_ignored_term_escalates_to_kill(self):
        self.scenario("ignore-term")

    def test_capture_exception_still_cleans_session(self):
        self.scenario("read-exception")

    def test_selector_setup_exception_still_cleans_session(self):
        self.scenario("setup-exception")

    def test_drain_exception_preserves_timeout_and_reaps_leader(self):
        self.scenario("drain-exception")

    def test_primary_error_survives_cleanup_error(self):
        self.scenario("primary-cleanup-error")

    def test_cleanup_failure_without_primary_is_not_success(self):
        self.scenario("cleanup-error-success")

    def test_same_executable_in_unrelated_session_is_not_signalled(self):
        self.scenario("sentinel")

    def test_old_timeout_negative_control_is_independently_cleaned(self):
        self.scenario("old-timeout")

    @classmethod
    def tearDownClass(cls):
        after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(pcm.__file__), Path(__file__))}
        report = {"source_sha256": cls.hashes, "source_sha256_after": after, "sources_unchanged": cls.hashes == after,
                  "results": cls.results, "passed": cls.hashes == after and len(cls.results) == 24 and
                  all(record["passed"] for record in cls.results), "no_hardware_or_radios": True}
        with (cls.evidence / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print("PCM cleanup evidence:", cls.evidence)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--controlled-worker"]:
        controlled_worker(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    else:
        unittest.main(verbosity=2)
