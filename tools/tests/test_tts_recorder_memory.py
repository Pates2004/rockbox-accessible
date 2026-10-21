import ctypes
import datetime
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import test_tts_recorder_gui as recorder


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



RUN = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
WORKSPACE = _project_materials_root(recorder.ROOT) / "tts-recorder-memory-tests" / RUN


class MemoryDiagnosticTests(unittest.TestCase):
    def test_recorder_source_facts_match_current_code(self):
        for fact in recorder.source_facts():
            with self.subTest(path=fact["path"]):
                self.assertTrue(fact["anchor_present"], fact)

    def test_recorder_gui_requires_selected_target(self):
        for target in recorder.TARGETS:
            recorder.validate_build_target("Target: " + target + "\n", target)
            for actual in ("sansafuze", "", "sansaclipplus" if target == "sansaclipzip" else "sansaclipzip"):
                with self.subTest(expected=target, actual=actual), self.assertRaises(RuntimeError):
                    recorder.validate_build_target("Target: " + actual + "\n", target)

    @classmethod
    def setUpClass(cls):
        WORKSPACE.mkdir(parents=True)
        cls.executable = WORKSPACE / "synthetic-pe.bin"
        cls.preferred_base = 0x140000000
        cls.loaded_base = 0x180000000
        image = bytearray(0x3000)
        image[:2] = b"MZ"
        struct.pack_into("<I", image, 60, 0x80)
        image[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HH", image, 0x84, 0x8664, 1)
        struct.pack_into("<H", image, 0x94, 0xf0)
        struct.pack_into("<H", image, 0x98, 0x20b)
        struct.pack_into("<Q", image, 0xb0, cls.preferred_base)
        struct.pack_into("<I", image, 0xd0, len(image))
        section = 0x188
        image[section:section + 8] = b".data\0\0\0"
        struct.pack_into("<III", image, section + 8, 0x2000, 0x1000, 0x2000)
        struct.pack_into("<I", image, section + 36, 0xc0000040)
        cls.image = bytes(image)
        cls.executable.write_bytes(cls.image)
        cls.symbols = {name: 0x1000 + index * 0x200
                       for index, name in enumerate(recorder.MEMORY_SYMBOL_SIZES)}
        cls.nm = "\n".join(f"{cls.preferred_base + address:016x} b {name}"
                           for name, address in cls.symbols.items())
        cls.layout = recorder.recorder_symbol_layout(cls.executable, cls.nm)

    def make_probe(self, modules=None):
        api = mock.Mock()
        api.open.return_value = 23
        api.modules.return_value = modules if modules is not None else [(self.loaded_base, self.executable.resolve())]
        api.read.side_effect = lambda handle, address, size: self.image[
            address - self.loaded_base:address - self.loaded_base + size]
        report = {"snapshots": []}
        process = SimpleNamespace(pid=1234, poll=lambda: None)
        probe = recorder.RecorderMemoryProbe(process, self.executable, self.layout, report, api)
        return probe, api, report

    def test_aslr_mapping_and_consistent_snapshot(self):
        probe, api, report = self.make_probe()
        try:
            sample = probe.snapshot("before_start")
            self.assertTrue(sample["consistent"])
            self.assertEqual(sample["values"]["codec_type"], 0)
            self.assertEqual(sample["values"]["path_buffer"], "")
            self.assertEqual(report["addresses"]["rec_status"], self.loaded_base + self.symbols["rec_status"])
            self.assertNotEqual(report["addresses"]["rec_status"], self.preferred_base + self.symbols["rec_status"])
            api.open.assert_called_once_with(1234)
        finally:
            probe.close()
        api.close.assert_called_once_with(23)

    def test_duplicate_or_missing_exact_symbols_are_rejected(self):
        for content in (self.nm + "\n" + self.nm.splitlines()[0], self.nm.replace("rec_status", "other_status")):
            with self.subTest(content=content), self.assertRaises(ValueError):
                recorder.recorder_symbol_layout(self.executable, content)

    def test_symbol_outside_image_or_overlapping_is_rejected(self):
        original = f"{self.preferred_base + self.symbols['rec_status']:016x} b rec_status"
        for address in (self.preferred_base - 4, self.preferred_base + 0x3000,
                        self.preferred_base + self.symbols["codec_type"]):
            with self.subTest(address=address), self.assertRaises(ValueError):
                recorder.recorder_symbol_layout(self.executable, self.nm.replace(original, f"{address:016x} b rec_status"))

    def test_wrong_main_module_closes_handle_without_reading(self):
        api = mock.Mock()
        api.open.return_value = 23
        api.modules.return_value = [(self.loaded_base, self.executable.with_name("wrong.bin"))]
        process = SimpleNamespace(pid=1234, poll=lambda: None)
        with self.assertRaisesRegex(RuntimeError, "main module"):
            recorder.RecorderMemoryProbe(process, self.executable, self.layout, {}, api)
        api.read.assert_not_called()
        api.close.assert_called_once_with(23)

    def test_changed_executable_is_rejected_before_open(self):
        api = mock.Mock()
        process = SimpleNamespace(pid=1234, poll=lambda: None)
        with self.assertRaisesRegex(RuntimeError, "EXE changed"):
            recorder.RecorderMemoryProbe(process, self.executable, dict(self.layout, sha256="wrong"), {}, api)
        api.open.assert_not_called()

    def test_read_bounds_are_checked_before_api_call(self):
        probe, api, report = self.make_probe()
        api.read.reset_mock()
        try:
            for rva, size in ((-1, 4), (0x3000, 4), (0, 0)):
                with self.subTest(rva=rva, size=size), self.assertRaises(ValueError):
                    probe.read_image(rva, size)
            api.read.assert_not_called()
        finally:
            probe.close()

    def test_read_failure_preserves_partial_values_and_error(self):
        probe, api, report = self.make_probe()
        api.read.side_effect = [b"\x08\0\0\0", OSError("synthetic denied read")]
        try:
            sample = probe.snapshot("start_timeout")
            self.assertFalse(sample["consistent"])
            self.assertEqual(sample["values"], {"rec_status": 8})
            self.assertIn("synthetic denied read", sample["error"])
        finally:
            probe.close()

    def test_inconsistent_snapshot_is_not_interpreted_as_stable(self):
        probe, api, report = self.make_probe()
        def changed_values(values):
            values["rec_status"] = 8 if changed_values.calls else 0
            changed_values.calls += 1
        changed_values.calls = 0
        try:
            with mock.patch.object(probe, "values", side_effect=changed_values):
                sample = probe.snapshot("before_start")
            self.assertFalse(sample["consistent"])
            self.assertEqual(report["interpretation"]["classification"], "insufficient_memory_evidence")
        finally:
            probe.close()

    def test_interpretation_does_not_invent_consumer_or_keyboard_cause(self):
        before = dict(rec_status=1, codec_type=4101, rec_errors=0,
                      record_state=0, record_status=0, path_buffer="")
        cases = (({}, "no_new_start_path_observed"),
                 ({"rec_status": 9}, "start_path_without_engine_transition"),
                 ({"rec_status": 9, "codec_type": 0}, "start_path_with_unknown_codec"),
                 ({"rec_status": 9, "rec_errors": 0x80020000}, "start_path_with_recorder_errors"),
                 ({"rec_status": 9, "record_status": 4}, "recording_engine_state_observed"))
        for changes, expected in cases:
            snapshots = [{"phase": "before_start", "consistent": True, "values": before},
                         {"phase": "start_timeout", "consistent": True, "values": dict(before, **changes)}]
            with self.subTest(expected=expected):
                result = recorder.interpret_start_snapshots(snapshots)
                self.assertEqual(result["classification"], expected)
                self.assertIn("do not prove", result["not_proven"])
                self.assertTrue(result["next_probe"])

    def test_enum_meanings_have_current_source_evidence(self):
        meanings = recorder.recorder_enum_meanings()
        self.assertEqual(meanings["codec_unknown"], 0)
        self.assertEqual(meanings["recording_status_flag"], 4)
        self.assertTrue(all(item["line"] > 0 and item["sha256"] for item in meanings["sources"]))

    def test_capture_snapshots_before_one_second_and_timeout_or_success(self):
        for succeeds in (False, True):
            clock = SimpleNamespace(current=0.0)
            phases = []
            probe = recorder.RecorderProbe.__new__(recorder.RecorderProbe)
            probe.report = {"checks": []}
            probe.timeout = 1.4
            probe.memory = mock.Mock()
            probe.memory.snapshot.side_effect = lambda phase: phases.append((phase, clock.current))
            probe.drain = mock.Mock()
            probe.mark = mock.Mock(return_value=(0, 2048))
            probe.check_process = mock.Mock()
            probe.text = mock.Mock(return_value="TTS: Recording\nTTS utterance: Recording\n" if succeeds else "")
            def advance(seconds):
                clock.current += seconds
            with self.subTest(succeeds=succeeds), \
                    mock.patch.object(recorder.time, "monotonic", side_effect=lambda: clock.current), \
                    mock.patch.object(recorder.time, "sleep", side_effect=advance):
                if succeeds:
                    probe.capture("start", mock.Mock(), bool, probe_start=True)
                else:
                    with self.assertRaisesRegex(AssertionError, "Missing recorder speech"):
                        probe.capture("start", mock.Mock(), bool, probe_start=True)
                self.assertEqual([phase for phase, moment in phases],
                                 ["before_start", "start_after_one_second",
                                  "start_speech_completed" if succeeds else "start_timeout"])
                self.assertGreaterEqual(phases[1][1], 1.0)

    def test_process_access_is_read_only(self):
        api = recorder.ReadOnlyWindowsMemory.__new__(recorder.ReadOnlyWindowsMemory)
        api.kernel = SimpleNamespace(OpenProcess=mock.Mock(return_value=23))
        self.assertEqual(api.open(1234), 23)
        api.kernel.OpenProcess.assert_called_once_with(0x410, False, 1234)

    def test_unavailable_start_requires_unchanged_inactive_state(self):
        values = dict(rec_status=1, codec_type=0, rec_errors=0, record_state=0,
                      record_status=0, path_buffer="")
        phases = ("before_start", "start_after_one_second", "start_speech_completed")
        diagnostics = {"snapshots": [{"phase": phase, "consistent": True, "values": dict(values)}
                                     for phase in phases]}
        result = recorder.verify_unavailable_start(diagnostics)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(diagnostics["interpretation"]["classification"],
                         "unsupported_start_rejected_without_recording_side_effects")
        for name in values:
            for changed_phase in (1, 2):
                changed = {"snapshots": [{"phase": phase, "consistent": True, "values": dict(values)}
                                        for phase in phases]}
                changed["snapshots"][changed_phase]["values"][name] = "/unexpected.wav" if name == "path_buffer" else 9
                with self.subTest(field=name, phase=changed_phase), self.assertRaises(AssertionError):
                    recorder.verify_unavailable_start(changed)

    def test_unavailable_start_allows_speech_state_changes_but_not_recording_changes(self):
        recorder_values = dict(rec_status=1, codec_type=0, rec_errors=0, record_state=0,
                               record_status=0, path_buffer="")
        phases = ("before_start", "start_after_one_second", "start_speech_completed")
        snapshots = []
        for index, phase in enumerate(phases):
            values = dict(recorder_values, generation=index, synthesizing=int(index == 1),
                          pending_count=0, voice_playing=int(index == 1), quiet_counter=index,
                          voice_pcm_paused=0)
            snapshots.append(dict(phase=phase, consistent=True, values=values))
        result = recorder.verify_unavailable_start(dict(snapshots=snapshots))
        self.assertEqual(result["status"], "passed")
        del snapshots[1]["values"]["record_state"]
        with self.assertRaisesRegex(AssertionError, "required recorder fields"):
            recorder.verify_unavailable_start(dict(snapshots=snapshots))

    def test_unavailable_start_rejects_missing_or_failed_snapshots(self):
        values = dict(rec_status=1, codec_type=0, rec_errors=0, record_state=0,
                      record_status=0, path_buffer="")
        for missing in (False, True):
            snapshots = [{"phase": phase, "consistent": True, "values": dict(values)} for phase in
                         ("before_start", "start_after_one_second", "start_speech_completed")]
            if missing:
                snapshots.pop()
            else:
                snapshots[-1].update(consistent=False, error="synthetic denied read")
            with self.subTest(missing=missing), self.assertRaises(AssertionError):
                recorder.verify_unavailable_start({"snapshots": snapshots})

    @unittest.skipUnless(sys.platform == "win32" and ctypes.sizeof(ctypes.c_void_p) == 8,
                         "Native Windows API self-check only")
    def test_windows_api_reads_only_own_python_process(self):
        api = recorder.ReadOnlyWindowsMemory()
        handle = api.open(os.getpid())
        try:
            modules = api.modules(handle)
            self.assertEqual(modules[0][1], Path(sys.executable).resolve())
            self.assertEqual(api.read(handle, modules[0][0], 2), b"MZ")
        finally:
            api.close(handle)


if __name__ == "__main__":
    print(f"Memory diagnostic self-check evidence: {WORKSPACE}", flush=True)
    program = unittest.main(verbosity=2, exit=False)
    result = program.result
    (WORKSPACE / "result.json").write_text(json.dumps({
        "tests": result.testsRun, "successful": result.wasSuccessful(),
        "failures": [(str(test), text) for test, text in result.failures],
        "errors": [(str(test), text) for test, text in result.errors],
        "skipped": [(str(test), reason) for test, reason in result.skipped],
    }, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if result.wasSuccessful() else 1)
