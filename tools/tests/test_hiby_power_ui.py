"""Execute HiBy power UI and shutdown wiring without any hardware side effects."""

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
from firmware_fixture_support import CONFIG, curtain_configuration

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import confined_path, project_materials_root


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/hiby_power.c"
SYSTEM = ROOT / "firmware/target/hosted/system-hosted.c"
FIXTURE = ROOT / "tools/tests/test_hiby_power_ui.c"
INPUTS = (
    SOURCE, SOURCE.with_suffix(".h"), SYSTEM, FIXTURE,
    ROOT / "firmware/target/hosted/hiby/power-control-hiby.h",
    ROOT / "apps/main.c", ROOT / "apps/SOURCES", ROOT / "firmware/SOURCES",
    ROOT / "firmware/export/config/hibylinux.h", Path(__file__),
    ROOT / "firmware/export/backlight.h", CONFIG,
    ROOT / "tools/tests/firmware_fixture_support.py",
    ROOT / "firmware/export/config/hibyr1.h",
    ROOT / "apps/lang/english.lang", ROOT / "apps/lang/polski.lang",
    ROOT / "apps/settings.h",
)
WRAPPED = ("malloc", "calloc", "realloc", "free", "strdup", "reboot", "ioctl",
           "posix_spawn", "posix_spawnp", "system", "sync", "usleep", "pthread_mutex_lock", "sigaction")


def extract_function(source, name):
    matched = re.search(r"^[\w *]+\b" + re.escape(name) + r"\([^;]*?\n\{.*?^\}",
                        source, flags=re.MULTILINE | re.DOTALL)
    if not matched:
        raise AssertionError(f"Production function not found: {name}")
    return matched[0] + "\n"


def disable_core_dump():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class HiByPowerUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if os.name != "posix" or not cls.compiler or not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("Linux host C fixture required; run with WSL")
        central = project_materials_root(ROOT)
        cls.evidence = confined_path(central / "r1-input-refinements-20261017/connectivity/power-ui" /
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"), central)
        cls.evidence.mkdir(parents=True)
        cls.headers = cls.evidence / "headers"
        cls.headers.mkdir()
        for name in ("kernel.h", "lang.h", "language.h", "list.h",
                     "menu.h", "splash.h", "talk.h"):
            (cls.headers / name).write_text("#pragma once\n", encoding="utf-8")
        (cls.headers / "config.h").write_text(curtain_configuration(), encoding="utf-8")
        (cls.headers / "backlight.h").write_text(
            (ROOT / "firmware/export/backlight.h").read_text(encoding="utf-8"), encoding="utf-8")
        cls.hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in INPUTS}
        cls.commands = []
        cls.test_results = []
        cls.native_probes = []
        cls.executables = {}
        cls.labels = sorted(set(re.findall(r"\bLANG_HIBY_WIFI_[A-Z_]+", SOURCE.read_text(encoding="utf-8"))))
        definitions = "\n".join(f"#define {label} {1000 + index}"
                                for index, label in enumerate(cls.labels))
        definitions += f"\n#define POWER_UI_LABEL_COUNT {len(cls.labels)}\n"
        definitions += "static const char *const power_ui_labels[] __attribute__((unused)) = {\n"
        definitions += ",\n".join(json.dumps(label) for label in cls.labels) + "\n};\n"
        (cls.headers / "power-ui-labels.h").write_text(definitions, encoding="utf-8")
        settings_source = (ROOT / "apps/settings.h").read_text(encoding="utf-8")
        provider_start = settings_source.index("#define VIRT_SIZE")
        provider_end = re.search(r"^#define P2ID[^\n]*", settings_source, flags=re.MULTILINE)
        if not provider_end:
            raise AssertionError("Actual settings virtual-pointer macro provider not found")
        (cls.headers / "settings.h").write_text(
            "#pragma once\n#ifndef CONFIG_CPU\n#define CONFIG_CPU (-1)\n#endif\n" +
            settings_source[provider_start:provider_end.end()] + "\n", encoding="utf-8")
        (cls.headers / "power-ui-shutdown-body.h").write_text(
            extract_function(SYSTEM.read_text(encoding="utf-8"), "power_off"), encoding="utf-8")
        (cls.headers / "power-ui-system-init-body.h").write_text(
            extract_function(SYSTEM.read_text(encoding="utf-8"), "system_init"), encoding="utf-8")
        (cls.headers / "power-ui-exception-wait-body.h").write_text(
            extract_function(SYSTEM.read_text(encoding="utf-8"), "system_exception_wait"), encoding="utf-8")
        system_source = SYSTEM.read_text(encoding="utf-8")
        start = system_source.index("#if defined(HIBY_R1) && !defined(BOOTLOADER)")
        stop = system_source.index("/* to make thread-internal")
        environment = re.sub(r'^\s*#\s*include\s+([^\n]+)',
            lambda matched: matched[0] if matched[1].strip() in
                ('"backlight.h"', "<pthread.h>") else "",
            system_source[start:stop], flags=re.MULTILINE)
        if not re.search(r"static pthread_mutex_t poweroff_mutex\s*=\s*PTHREAD_MUTEX_INITIALIZER;", environment):
            raise AssertionError("Actual native R1 file-scope poweroff mutex not found")
        (cls.headers / "power-ui-shutdown-environment.h").write_text(environment, encoding="utf-8")
        (cls.headers / "power-ui-app-body.h").write_text(re.sub(
            r"^\s*#\s*include\s+([^\n]+)",
            lambda matched: matched[0] if matched[1].strip() == '"settings.h"' else "",
            SOURCE.read_text(encoding="utf-8"), flags=re.MULTILINE), encoding="utf-8")
        cls.addClassCleanup(cls.report)

    @classmethod
    def report(cls):
        after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in INPUTS}
        (cls.evidence / "report.json").write_text(json.dumps({
            "source_project": str(ROOT), "inputs_before": cls.hashes, "inputs_after": after,
            "sources_stable": cls.hashes == after, "commands": cls.commands,
            "test_results": cls.test_results,
            "passed": all(record["passed"] for record in cls.test_results) and cls.hashes == after,
            "real_app_source_executed": True, "real_power_off_body_executed": True,
            "backend_and_syscalls_strict_fakes": True,
            "app_includes_replaced_with_host_services": True,
            "settings_provider_include_and_actual_macro_definitions_preserved": True,
            "native_translation_unit_probes": cls.native_probes,
            "real_shutdown_mutex_declaration_and_pthread_operations": True,
            "shutdown_curtain_capability_derived_from_actual_header_order": True,
            "test_only_mutex_cleanup_after_caught_noreturn_panic": True,
            "signal_assignments_captured_without_real_sigaction": True,
            "exception_input_and_usleep_are_strict_fakes": True,
            "physical_hardware_tested": False, "global_input_used": False,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"HiBy power UI evidence: {cls.evidence}", flush=True)
        if cls.hashes != after:
            raise AssertionError("Power UI integration input changed during test run")

    def run(self, result=None):
        result = result if result is not None else self.defaultTestResult()
        before = len(result.failures) + len(result.errors)
        returned = super().run(result)
        if hasattr(self.__class__, "test_results"):
            self.test_results.append({"name": self.id(),
                "passed": len(result.failures) + len(result.errors) == before})
        return returned

    def command(self, arguments, *, name, input_text=None, environment=None, expect_success=True):
        process = subprocess.run(arguments, input=input_text, capture_output=True,
                                 text=True, timeout=90, env=environment,
                                 preexec_fn=disable_core_dump)
        self.commands.append({"argv": arguments, "returncode": process.returncode,
                              "log": name, "expected_success": expect_success,
                              "passed": (process.returncode == 0) == expect_success})
        (self.evidence / name).write_text(shlex.join(arguments) + "\n" +
            process.stdout + process.stderr, encoding="utf-8")
        if expect_success:
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        else:
            self.assertNotEqual(process.returncode, 0, "Negative compile unexpectedly succeeded")
        return process.stdout

    def executable(self, mode, sanitizer):
        key = mode + "-" + sanitizer
        if key not in self.executables:
            output = self.evidence / key
            arguments = self.compiler + ["-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-function", "-Wno-unused-variable", "-fno-pie", "-no-pie", "-pthread",
                "-I", str(self.headers), "-I", str(ROOT / "apps"),
                "-I", str(ROOT / "firmware/export"),
                "-I", str(ROOT / "firmware/target/hosted/hiby"), str(FIXTURE), "-o", str(output)]
            arguments += [f"-Wl,--wrap={symbol}" for symbol in WRAPPED]
            if mode not in ("shutdown-other", "init-other", "wait-other", "wait-other-data"):
                arguments += ["-DHIBY_R1"]
            if mode != "shutdown-native-no-curtain":
                arguments += ["-DHAVE_ESPEAK"]
            arguments += ["-DHAVE_BACKLIGHT", "-DINIT_ATTR="]
            target = (ROOT / "firmware/export/config/hibyr1.h").read_text(encoding="utf-8")
            brightness = re.search(r"^#define DEFAULT_BRIGHTNESS_SETTING\s+(\d+)", target, flags=re.MULTILINE)
            if not brightness:
                raise AssertionError("Actual R1 default brightness missing")
            arguments += ["-DDEFAULT_BRIGHTNESS_SETTING=" + brightness[1]]
            if mode.endswith("-data"):
                arguments += ["-DHAVE_BUTTON_DATA"]
            if mode in ("simulator", "simulator-boot"):
                arguments += ["-DSIMULATOR"]
            if mode in ("boot", "simulator-boot", "shutdown-boot"):
                arguments += ["-DBOOTLOADER"]
            if mode.startswith("shutdown"):
                arguments += ["-DPOWER_UI_SHUTDOWN"]
            if mode.startswith("init"):
                arguments += ["-DPOWER_UI_INIT"]
                arguments += ["-Wno-dangling-pointer"]
            if mode.startswith("wait"):
                arguments += ["-DPOWER_UI_WAIT"]
            if sanitizer != "strict":
                arguments += ["-fsanitize=" + ("address,undefined" if sanitizer == "asan" else "undefined"),
                              "-fno-sanitize-recover=all"]
            self.command(arguments, name=key + "-build.log")
            self.executables[key] = output
        return self.executables[key]

    def run_case(self, mode, scenario):
        for sanitizer in ("strict", "ubsan", "asan"):
            with self.subTest(mode=mode, scenario=scenario, sanitizer=sanitizer):
                environment = dict(os.environ,
                    ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
                    UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                self.command([str(self.executable(mode, sanitizer)), scenario],
                    name=f"{mode}-{sanitizer}-{scenario}-run.log", environment=environment)

    def preprocess(self, relative, mode):
        source = (ROOT / relative).read_text(encoding="utf-8")
        source = re.sub(r"^\s*#\s*include[^\n]*", "", source, flags=re.MULTILINE)
        definitions = ["PLATFORM_HOSTED=1", "PLATFORM_NATIVE=2", "PLATFORM_ANDROID=4",
                       "PLATFORM_SDL=8", "CONFIG_PLATFORM=1", "CONFIG_CPU=-1"]
        if mode != "other":
            definitions += ["HIBY_R1", "HIBY_LINUX"]
        if mode in ("simulator", "simulator-boot"):
            definitions += ["SIMULATOR", "CONFIG_PLATFORM=9"]
        if mode in ("boot", "simulator-boot"):
            definitions += ["BOOTLOADER"]
        if mode == "bare-native":
            definitions = [item for item in definitions if not item.startswith("CONFIG_PLATFORM=")]
            definitions += ["CONFIG_PLATFORM=2"]
        if mode in ("simulator", "simulator-boot"):
            definitions.remove("CONFIG_PLATFORM=1")
        command = self.compiler + ["-E", "-P", "-x", "c", "-"]
        command += ["-D" + definition for definition in definitions]
        key = relative.replace("/", "-") + "-" + mode
        return self.command(command, name=key + "-preprocess.log", input_text=source)

    def test_actual_native_translation_unit_requires_real_settings_macro_provider(self):
        central = project_materials_root(ROOT)
        build = Path(os.environ.get("HIBY_POWER_NATIVE_BUILD", central / "build-espeak-hibyr1"))
        makefile = build / "Makefile"
        if not makefile.is_file():
            self.skipTest("Configure a native R1 build or set HIBY_POWER_NATIVE_BUILD for the real-header gate")
        configuration = makefile.read_text(encoding="utf-8")

        def exported(name):
            matched = re.search(r"^export " + re.escape(name) + r"=(.*)$", configuration, re.MULTILINE)
            if not matched:
                raise AssertionError(f"Native build variable missing: {name}")
            return matched[1].strip()

        self.assertEqual(exported("MODELNAME"), "hibyr1")
        self.assertEqual(exported("TARGET_ID"), "124")
        compiler = Path(exported("CC"))
        self.assertTrue(compiler.is_file(), f"Configured native compiler missing: {compiler}")
        native = self.evidence / "native-tu"
        native.mkdir()
        input_paths = [SOURCE, ROOT / "apps/settings.h", makefile, build / "autoconf.h",
                       build / "lang_enum.h", build / "rbversion.h"]
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in input_paths}
        directories = [build, build / "lang"] + [ROOT / relative for relative in (
            "firmware", "firmware/export", "firmware/drivers", "firmware/include", "firmware/kernel/include",
            "apps", "apps/gui", "apps/recorder", "apps/radio", "lib/rbcodec", "lib/rbcodec/dsp",
            "lib/rbcodec/metadata", "lib/rbcodec/codecs", "lib/skin_parser", "lib/fixedpoint",
            "uisimulator/common", "firmware/target/hosted/hiby/r1", "firmware/target/hosted/hiby",
            "firmware/target/hosted")]
        arguments = [str(compiler)] + ["-I" + str(path) for path in directories]
        arguments += ["-DROCKBOX", "-DHIBY_R1", "-DMEMORYSIZE=" + exported("MEMORYSIZE"),
                      "-DTARGET_ID=" + exported("TARGET_ID"), '-DTARGET_NAME="hibyr1"']
        arguments += shlex.split(exported("EXTRA_DEFINES"))
        arguments += shlex.split(exported("GCCOPTS")) + ["-Werror", "-Werror=implicit-function-declaration"]
        machine = self.command([str(compiler), "-dumpmachine"], name="native-compiler-target.log")
        self.assertIn("mipsel", machine)
        self.command(arguments + ["-MMD", "-MF", str(native / "positive.d"),
            "-c", str(SOURCE), "-o", str(native / "positive.o")], name="native-real-headers-build.log")
        dependency_text = (native / "positive.d").read_text(encoding="utf-8")
        self.assertIn(str(ROOT / "apps/settings.h"), dependency_text)
        macros = self.command(arguments + ["-E", "-dM", str(SOURCE)], name="native-real-header-macros.log")
        self.assertRegex(macros, r"(?m)^#define ID2P\(id\) \(VIRT_PTR \+ id\)$")
        symbols = self.command([str(compiler.with_name(compiler.name[:-3] + "nm")),
            "-u", str(native / "positive.o")], name="native-object-undefined-symbols.log")
        self.assertNotRegex(symbols, r"\bID2P\b")
        mutated, replacements = re.subn(r'^\s*#\s*include\s+"settings.h"[^\n]*\n?', "",
            SOURCE.read_text(encoding="utf-8"), flags=re.MULTILINE)
        self.assertEqual(replacements, 1, "Negative probe must remove exactly the actual provider include")
        negative = native / "hiby_power_without_settings.c"
        negative.write_text(mutated, encoding="utf-8")
        self.command(arguments + ["-iquote", str(ROOT / "apps"), "-c", str(negative),
            "-o", str(native / "negative.o")], name="native-missing-provider-negative-build.log",
            expect_success=False)
        negative_log = (self.evidence / "native-missing-provider-negative-build.log").read_text(encoding="utf-8")
        self.assertRegex(negative_log, r"implicit declaration of function[^\n]*ID2P")
        after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in input_paths}
        self.assertEqual(before, after, "Native configuration/source changed during the actual TU probe")
        self.native_probes.append({"build": str(build), "compiler": str(compiler),
            "inputs_before": before, "inputs_after": after, "stable": before == after,
            "strict_actual_tu_passed": True, "real_macro_provider_present": True,
            "negative_provider_removal_rejected": True,
            "undefined_id2p_symbol_absent": True, "native_object_executed": False,
            "object_sha256": hashlib.sha256((native / "positive.o").read_bytes()).hexdigest()})

    def test_native_unknown_before_initialization_is_not_reported_blocked(self):
        self.run_case("native", "unknown")

    def test_native_blocked_state_counts_and_speech(self):
        self.run_case("native", "blocked")

    def test_native_no_radio_does_not_claim_verified_block(self):
        self.run_case("native", "no-radio")

    def test_native_interface_down_preserves_unconfirmed_radio_notice_and_speech(self):
        self.run_case("native", "interface-down")

    def test_native_unconfirmed_negative_errors_are_preserved(self):
        self.run_case("native", "unconfirmed")

    def test_native_error_state_does_not_claim_verified_block(self):
        self.run_case("native", "error")

    def test_native_extreme_signed_errors_are_displayed_and_spoken(self):
        self.run_case("native", "extreme")

    def test_simulator_has_one_unavailable_row_and_no_backend_calls(self):
        self.run_case("simulator", "blocked")

    def test_bootloader_has_one_unavailable_row_and_no_backend_calls(self):
        self.run_case("boot", "blocked")

    def test_simulator_bootloader_has_one_unavailable_row(self):
        self.run_case("simulator-boot", "blocked")

    def test_simulator_unknown_state_never_reports_numeric_rf_information(self):
        self.run_case("simulator", "unknown")

    def test_r1_shutdown_restores_backlight_and_reports_backend_errors(self):
        self.run_case("shutdown-native", "negative")

    def test_r1_shutdown_zero_errors_still_cannot_silently_return(self):
        self.run_case("shutdown-native", "zero")

    def test_r1_shutdown_signed_error_extremes_do_not_overflow(self):
        self.run_case("shutdown-native", "extreme")

    def test_r1_shutdown_concurrent_callers_enter_backend_serially(self):
        self.run_case("shutdown-native", "concurrent")

    def test_r1_shutdown_lock_error_restores_screen_without_backend_call(self):
        self.run_case("shutdown-native", "lock-error")

    def test_r1_without_curtain_still_serializes_and_reports_failure(self):
        self.run_case("shutdown-native-no-curtain", "negative")

    def test_r1_without_curtain_concurrent_callers_are_serialized(self):
        self.run_case("shutdown-native-no-curtain", "concurrent")

    def test_native_shutdown_resolves_curtain_capability_from_real_header_order(self):
        environment = (self.headers / "power-ui-shutdown-environment.h").read_text(encoding="utf-8")
        body = (self.headers / "power-ui-shutdown-body.h").read_text(encoding="utf-8")
        arguments = self.compiler + ["-E", "-P", "-x", "c", "-", "-DHIBY_R1", "-DHAVE_ESPEAK",
            "-DHAVE_BACKLIGHT", "-DINIT_ATTR=", "-I", str(self.headers),
            "-I", str(ROOT / "firmware/export")]
        source = self.command(arguments, name="actual-native-curtain-header-order.log",
                              input_text=environment + body)
        shutdown = extract_function(source, "power_off")
        reset = re.search(r"\bbacklight_set_screen_curtain\(\s*(?:false|0)\s*\);", shutdown)
        self.assertIsNotNone(reset,
            "The real config.h guard must expose screen curtain before the shutdown body is compiled")
        self.assertLess(shutdown.index("hiby_poweroff();"), reset.start())
        self.assertLess(reset.start(), shutdown.index("backlight_hw_on();"))

    def test_other_target_shutdown_keeps_legacy_order_without_real_system_calls(self):
        self.run_case("shutdown-other", "negative")

    def test_r1_bootloader_shutdown_keeps_legacy_order(self):
        self.run_case("shutdown-boot", "negative")

    def test_r1_system_init_uses_default_sigterm_and_keeps_fatal_handlers(self):
        self.run_case("init-native", "signals")

    def test_other_system_init_preserves_siginfo_handler_including_sigterm(self):
        self.run_case("init-other", "signals")

    def test_r1_exception_wait_yields_in_each_of_four_input_phases(self):
        for mode in ("wait-native", "wait-native-data"):
            self.run_case(mode, "phases")

    def test_other_exception_wait_preserves_no_sleep_behavior(self):
        for mode in ("wait-other", "wait-other-data"):
            self.run_case(mode, "phases")

    def test_r1_exception_wait_does_not_sleep_when_all_phases_complete_immediately(self):
        self.run_case("wait-native-data", "immediate")

    def test_real_hosted_r1_init_calls_backend_once_after_kernel_before_storage(self):
        header = (ROOT / "firmware/export/config/hibylinux.h").read_text(encoding="utf-8")
        self.assertRegex(header, r"#define CONFIG_PLATFORM\s+\(PLATFORM_HOSTED\)")
        source = self.preprocess("apps/main.c", "native")
        initialization = extract_function(source, "init")
        self.assertEqual(len(re.findall(r"\bhiby_power_init\s*\(", initialization)), 1,
                         "R1 uses hosted init; a call in non-hosted #else is dead wiring")
        self.assertLess(initialization.index("kernel_init();"), initialization.index("hiby_power_init();"))
        storage = min(initialization.index(marker) for marker in ("storage_init();", "filesystem_init();")
                      if marker in initialization)
        self.assertLess(initialization.index("hiby_power_init();"), storage)

    def test_startup_notice_follows_init_and_tree_and_is_native_r1_only(self):
        source = self.preprocess("apps/main.c", "native")
        self.assertEqual(len(re.findall(r"\bhiby_power_startup_notice\s*\(", source)), 1)
        self.assertLess(source.index("    init();"), source.index("hiby_power_startup_notice();"))
        self.assertLess(source.index("tree_init();"), source.index("hiby_power_startup_notice();"))
        for mode in ("simulator", "boot", "simulator-boot", "other"):
            with self.subTest(mode=mode):
                selected = self.preprocess("apps/main.c", mode)
                self.assertNotRegex(selected, r"\bhiby_power_init\s*\(")
                self.assertNotRegex(selected, r"\bhiby_power_startup_notice\s*\(")

    def test_backend_source_selected_only_for_native_r1_non_boot(self):
        for mode in ("native", "simulator", "boot", "simulator-boot", "other"):
            with self.subTest(mode=mode):
                source = self.preprocess("firmware/SOURCES", mode)
                self.assertEqual(source.split().count("target/hosted/hiby/power-control-hiby.c"),
                                 1 if mode == "native" else 0)

    def test_app_source_selected_only_for_r1(self):
        for mode in ("native", "simulator", "boot", "other"):
            with self.subTest(mode=mode):
                source = self.preprocess("apps/SOURCES", mode)
                self.assertEqual(source.split().count("hiby_power.c"), 0 if mode == "other" else 1)

    def test_simulator_and_boot_preprocessor_remove_all_backend_invocations(self):
        for mode in ("simulator", "boot", "simulator-boot"):
            with self.subTest(mode=mode):
                source = self.preprocess("apps/hiby_power.c", mode)
                self.assertNotRegex(source, r"\bhiby_wifi_disable\s*\(")
                self.assertNotIn("startup_wifi", source)
                self.assertNotIn("startup_checked", source)

    def test_power_ui_language_labels_have_matching_pl_en_sources_and_voice(self):
        catalogs = {}
        for language in ("english", "polski"):
            phrases = re.findall(r"<phrase>.*?</phrase>",
                (ROOT / f"apps/lang/{language}.lang").read_text(encoding="utf-8"), flags=re.DOTALL)
            entries = {}
            for phrase in phrases:
                matched = re.search(r"\bid:\s+(LANG_HIBY_WIFI_[A-Z_]+)", phrase)
                if matched:
                    entries[matched[1]] = phrase
            catalogs[language] = entries
        for label in self.labels:
            with self.subTest(label=label):
                sources = []
                for language in ("english", "polski"):
                    self.assertIn(label, catalogs[language])
                    phrase = catalogs[language][label]
                    for section in ("source", "dest", "voice"):
                        content = re.search(f"<{section}>(.*?)</{section}>", phrase, flags=re.DOTALL)
                        self.assertIsNotNone(content)
                        self.assertRegex(content[1], r':\s*"[^"\n]+"')
                        if section == "source":
                            sources.append(content[1].strip())
                self.assertEqual(sources[0], sources[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
