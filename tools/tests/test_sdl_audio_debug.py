"""Exercise actual optional SDL audio tracing C with intercepted I/O and SDL calls."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
PCM = ROOT / "firmware/target/hosted/sdl/pcm-sdl.c"
SYSTEM = ROOT / "firmware/target/hosted/sdl/system-sdl.c"
FIXTURE = ROOT / "tools/tests/fixtures/sdl_audio_debug_fixture.c"


def guarded_block(source, marker):
    position = source.index(marker)
    start = source.rfind("#if", 0, position)
    depth = 0
    for match in re.finditer(r"^#\s*(if\w*|endif)\b[^\n]*", source[start:], re.MULTILINE):
        depth += -1 if match.group(1) == "endif" else 1
        if depth == 0:
            return source[start:start + match.end()] + "\n"
    raise AssertionError("Unterminated source guard: " + marker)


def extracted_headers(pcm, system):
    structure_start = pcm.index("static struct pcm_udata")
    structure_end = pcm.index("} udata;", structure_start) + len("} udata;")
    functions = []
    for signature in ("static void sink_set_freq_nolock(", "static void sink_dma_stop(",
                      "static void write_to_soundcard(", "static void sink_dma_init("):
        start = pcm.index(signature)
        functions.append(pcm[start:pcm.index("\n}\n", start) + 3])
    header = (guarded_block(system, "bool debug_audio = false;") +
              pcm[structure_start:structure_end] + "\n" +
              guarded_block(pcm, "static void audio_debug_open(") + "\n".join(functions))
    option = guarded_block(system, 'if (!strcmp("--debugaudio", argv[x]))')
    return header, option.replace("argv[x]", "arguments[argument_index]")


class AudioDebugTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("Host C compiler required; Windows SDK sharing proof is separate")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.directory = project_materials_root(ROOT) / "r1-connectivity-shortcut-20261016/audio-debug-tests" / stamp
        cls.directory.mkdir(parents=True)
        cls.pcm, cls.system = PCM.read_text(encoding="utf-8"), SYSTEM.read_text(encoding="utf-8")
        cls.records, cls.executables = [], []
        for sanitizer in (False, True):
            for mode, definitions in (("simulator-posix", ["-DSIMULATOR"]),
                                      ("simulator-windows", ["-DSIMULATOR", "-DWIN32"]),
                                      ("debug-posix", ["-DDEBUG"]), ("disabled", [])):
                directory = cls.directory / (mode + ("-ubsan" if sanitizer else "-ordinary"))
                executable = cls.build(directory, cls.pcm, cls.system, definitions, sanitizer)
                cls.executables.append((mode, executable))

    @classmethod
    def build(cls, directory, pcm, system, definitions, sanitizer):
        directory.mkdir()
        header, option = extracted_headers(pcm, system)
        (directory / "actual_audio_debug.h").write_text(header, encoding="utf-8")
        (directory / "actual_audio_option.h").write_text(option, encoding="utf-8")
        executable = directory / "fixture"
        command = cls.compiler + ["-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                                  "-I", str(directory), *definitions, str(FIXTURE), "-o", str(executable)]
        if sanitizer:
            command += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (directory / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stderr)
        return executable

    @classmethod
    def tearDownClass(cls):
        report = {"sources": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (PCM, SYSTEM, FIXTURE, Path(__file__))},
                  "runs": cls.records, "scope": "Actual extracted C; all SDL, stdio and power operations intercepted"}
        (cls.directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("SDL audio debug evidence: " + str(cls.directory), flush=True)

    def scenario(self, name):
        for mode, executable in self.executables:
            with self.subTest(mode=mode, executable=executable.name, scenario=name):
                result = subprocess.run([str(executable), name], capture_output=True, text=True, timeout=5)
                self.records.append({"executable": str(executable.relative_to(self.directory)), "scenario": name,
                                     "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_disabled_by_default_has_no_trace_io_or_log(self):
        self.scenario("default")

    def test_optional_flag_and_platform_open_modes(self):
        self.scenario("enabled")

    def test_reopen_appends_after_checked_close(self):
        self.scenario("reopen")

    def test_open_failure_disables_without_callback_retries_or_false_success(self):
        self.scenario("open-failure")

    def test_append_failure_disables_without_retries(self):
        self.scenario("append-failure")

    def test_short_write_disables_and_closes(self):
        self.scenario("short-write")

    def test_stream_error_disables_and_closes(self):
        self.scenario("stream-error")

    def test_close_failure_never_reports_success(self):
        self.scenario("close-failure")

    def test_converted_branch_records_converted_pcm(self):
        self.scenario("converted")

    def test_conversion_fallback_records_all_stereo_u8_bytes(self):
        self.scenario("fallback-u8")

    def test_conversion_fallback_records_all_stereo_s16_bytes(self):
        self.scenario("fallback-s16")

    def test_negative_controls_reject_old_modes_guards_and_byte_count(self):
        mutants = {
            "windows-mode": self.pcm.replace('append ? "abN" : "wbN"', 'append ? "abe" : "wbe"'),
            "byte-count": self.pcm.replace("wr * pcm_sample_bytes);", "wr);"),
            "close-result": self.pcm.replace("if (fclose(stream) != 0)", "if (fclose(stream) == 12345)"),
            "retry-open": self.pcm.replace("debug_audio = false;\n        DEBUGF(\"Audio debug file open failed", "DEBUGF(\"Audio debug file open failed"),
        }
        for name, source in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(source, self.pcm)
                executable = self.build(self.directory / ("mutant-" + name), source, self.system,
                                        ["-DSIMULATOR", "-DWIN32"], True)
                scenario = {"windows-mode": "enabled", "byte-count": "fallback-s16",
                            "close-result": "close-failure", "retry-open": "open-failure"}[name]
                result = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=5)
                self.records.append({"mutant": name, "scenario": scenario, "exit_code": result.returncode,
                                     "stdout": result.stdout, "stderr": result.stderr})
                self.assertNotEqual(result.returncode, 0, "Negative control escaped the actual-C fixture")
        system = self.system.replace(
            '#if defined(DEBUG) || defined(SIMULATOR)\n            if (!strcmp("--debugaudio", argv[x]))',
            '#ifdef DEBUG\n            if (!strcmp("--debugaudio", argv[x]))')
        self.assertNotEqual(system, self.system)
        executable = self.build(self.directory / "mutant-option-guard", self.pcm, system, ["-DSIMULATOR"], True)
        result = subprocess.run([str(executable), "enabled"], capture_output=True, text=True, timeout=5)
        self.records.append({"mutant": "option-guard", "exit_code": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
