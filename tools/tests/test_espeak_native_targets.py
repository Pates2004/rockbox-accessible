"""Check eSpeak admission without building firmware (run on a POSIX host)."""

import datetime
import os
from pathlib import Path
import re
import runpy
import shlex
import shutil
import subprocess
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]
CONFIGURE = ROOT / "tools/configure"
THUMB_WRAPPER = ROOT / "tools/thumb-cc.py"
NATIVE_TARGETS = ("sansaclipplus", "sansaclipzip")
POSIX_SHELL = os.name == "posix" and shutil.which("sh")


class CompilerDelegated(Exception):
    pass


def invoke_thumb_wrapper(arguments, returncode=0):
    process = mock.Mock(returncode=returncode)
    process.communicate.return_value = (b"", b"")
    with mock.patch.object(sys, "argv", [str(THUMB_WRAPPER), *arguments]), \
            mock.patch("subprocess.Popen", return_value=process) as compiler, \
            mock.patch("os.execv", side_effect=CompilerDelegated) as delegate:
        try:
            runpy.run_path(str(THUMB_WRAPPER), run_name="__main__")
        except CompilerDelegated:
            pass
    return compiler, delegate


class ThumbCompilerTests(unittest.TestCase):
    def test_thumb_success_and_arm_fallback_preserve_compiler_arguments(self):
        for compiler_name, source_name in (("gcc", "fixture.c"), ("g++", "fixture.cpp")):
            for interwork in (False, True):
                for returncode in (0, 1):
                    with self.subTest(compiler=compiler_name, interwork=interwork,
                                      returncode=returncode):
                        arguments = [f"/synthetic/arm-none-eabi-{compiler_name}",
                                     "-mcpu=arm926ej-s", "-Os", "-c", source_name,
                                     "-o", "fixture.o"]
                        if interwork:
                            arguments.append("-mthumb-interwork")
                        expected = arguments if interwork else [*arguments, "-mthumb-interwork"]
                        compiler, delegate = invoke_thumb_wrapper(arguments, returncode)
                        compiler.assert_called_once_with(
                            [*expected, "-mthumb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        )
                        compiler.return_value.communicate.assert_called_once_with()
                        if returncode:
                            delegate.assert_called_once_with(expected[0], expected)
                        else:
                            delegate.assert_not_called()

    def test_link_and_query_invocations_bypass_thumb_compilation(self):
        invocations = [["-mcpu=arm926ej-s", option, "fixture.c"]
                       for option in ("-E", "-MM", "-v", "--version")]
        invocations.append(["-mcpu=arm926ej-s", "-mthumb-interwork", "-nostdlib",
                            "-o", "rockbox.elf", "fixture.o", "-lm", "-lgcc"])
        for options in invocations:
            with self.subTest(options=options):
                arguments = ["/synthetic/arm-none-eabi-gcc", *options]
                compiler, delegate = invoke_thumb_wrapper(arguments)
                compiler.assert_not_called()
                delegate.assert_called_once_with(arguments[0], arguments)


@unittest.skipUnless(POSIX_SHELL, "Run with a POSIX shell, for example in WSL")
class EspeakAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = CONFIGURE.read_text(encoding="utf-8")
        start = source.index("\nespeak_define=\n")
        end = source.index("\ncat > autoconf.h.new <<EOF", start)
        cls.guard = source[start:end]
        cls.models = sorted(set(re.findall(r'^\s+modelname="([a-z0-9_]+)"', source, re.M)))
        if not set(NATIVE_TARGETS).issubset(cls.models):
            raise AssertionError("Could not discover the native eSpeak targets")

    def admission(self, model, app_type="", apps="apps", enabled=True, windows=False):
        script = (
            'ARG_ESPEAK=$1; modelname=$2; app_type=$3; apps=$4; winbuild=$5\n'
            'LDOPTS="-lm -mconsole"\n' + self.guard
            + '\nprintf "%s\\n" "$espeak_define" "LDOPTS=$LDOPTS"\n'
        )
        return subprocess.run(
            ["sh", "-c", script, "espeak-admission", "1" if enabled else "",
             model, app_type, apps, "yes" if windows else ""],
            capture_output=True, text=True, timeout=10, check=False,
        )

    def assert_allowed(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("#define HAVE_ESPEAK 1", result.stdout)
        self.assertIn("#define TARGET_EXTRA_THREADS 1", result.stdout)

    def assert_rejected(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Integrated eSpeak supports", result.stdout)
        self.assertNotIn("#define HAVE_ESPEAK", result.stdout)
        self.assertNotIn("#define TARGET_EXTRA_THREADS", result.stdout)

    def test_native_clipplus_and_clipzip_are_allowed(self):
        for model in NATIVE_TARGETS:
            with self.subTest(model=model):
                self.assert_allowed(self.admission(model))

    def test_hosted_hiby_r1_is_allowed_only_in_application_builds(self):
        self.assert_allowed(self.admission("hibyr1", app_type="hibyos"))
        self.assert_rejected(self.admission("hibyr1", app_type="hibyos", apps="bootloader"))
        self.assert_rejected(self.admission("hibyr3proii", app_type="hibyos"))
        self.assert_rejected(self.admission("sansaclipplus", app_type="hibyos"))

    def test_simulator_bootloader_does_not_enable_synthesis(self):
        self.assert_rejected(self.admission("hibyr1", app_type="sdl-sim", apps="bootloader"))

    def test_all_other_native_targets_are_rejected(self):
        for model in [*self.models, "", "unknown", "sansaclipzip-extra"]:
            if model not in NATIVE_TARGETS:
                with self.subTest(model=model):
                    self.assert_rejected(self.admission(model))

    def test_bootloaders_are_rejected(self):
        for model in self.models:
            with self.subTest(model=model):
                self.assert_rejected(self.admission(model, apps="bootloader"))

    def test_applications_and_auxiliary_tools_are_rejected(self):
        for model in (*NATIVE_TARGETS, "sdlapp", "unknown"):
            for app_type in ("sdl-app", "checkwps", "database-sdl", "warble", "other-app"):
                with self.subTest(model=model, app_type=app_type):
                    self.assert_rejected(self.admission(model, app_type=app_type))

    def test_sdl_simulator_is_not_limited_to_native_allowlist(self):
        for model in self.models:
            with self.subTest(model=model):
                self.assert_allowed(self.admission(model, app_type="sdl-sim"))

    def test_without_opt_in_guard_does_not_enable_or_reject(self):
        for model in (*NATIVE_TARGETS, "sansafuzev2", "sdlapp"):
            for app_type, apps in (("", "apps"), ("", "bootloader"),
                                   ("sdl-app", "apps"), ("sdl-sim", "apps")):
                with self.subTest(model=model, app_type=app_type, apps=apps):
                    result = self.admission(model, app_type, apps, enabled=False, windows=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertNotIn("#define", result.stdout)
                    self.assertIn("LDOPTS=-lm -mconsole", result.stdout)

    def test_windows_simulator_keeps_gui_subsystem(self):
        result = self.admission("sansaclipzip", app_type="sdl-sim", windows=True)
        self.assert_allowed(result)
        self.assertIn("LDOPTS=-lm -mwindows", result.stdout)
        self.assertNotIn("-mconsole", result.stdout)

    def test_native_linker_options_are_unchanged(self):
        for model in NATIVE_TARGETS:
            with self.subTest(model=model):
                result = self.admission(model)
                self.assert_allowed(result)
                self.assertIn("LDOPTS=-lm -mconsole", result.stdout)


@unittest.skipUnless(POSIX_SHELL, "Run with a POSIX shell, for example in WSL")
class EspeakConfigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = ("gcc", "cpp", "ld", "make", "sdl2-config")
        missing = [tool for tool in required if not shutil.which(tool)]
        cls.arm_prefix = next(
            (prefix for prefix in ("arm-elf-eabi-", "arm-none-eabi-")
             if all(shutil.which(prefix + tool) for tool in ("gcc", "cpp", "ld"))), None,
        )
        if missing or cls.arm_prefix is None:
            raise unittest.SkipTest(
                "Full configure checks need GCC, SDL2 development tools and an ARM GCC toolchain; "
                f"missing: {missing}, ARM prefix: {cls.arm_prefix}"
            )
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.results = _project_materials_root(ROOT) / "espeak-native-targets" / timestamp
        cls.results.mkdir(parents=True)
        print(f"Configure-only eSpeak regression evidence (not firmware): {cls.results}", flush=True)

    def configure(self, target, build_type="N", enabled=True, thumb=None):
        mode = "" if thumb is None else "-thumb" if thumb else "-no-thumb"
        directory = self.results / self._testMethodName / f"{target}-{build_type}-{enabled}{mode}"
        temporary = directory / "tmp"
        temporary.mkdir(parents=True)
        command = ["sh", str(CONFIGURE), f"--target={target}", f"--type={build_type}",
                   "--no-ccache", "--lcdwidth=320", "--lcdheight=240"]
        if enabled:
            command.append("--integrated-espeak")
        if target != "sdlapp" and build_type in ("N", "B", "ab"):
            command.append(f"--compiler-prefix={self.arm_prefix}")
        if thumb is not None:
            command.append("--thumb" if thumb else "--no-thumb")
        environment = {"PATH": os.environ["PATH"], "LC_ALL": "C",
                       "HOME": str(directory), "TMPDIR": str(temporary)}
        result = subprocess.run(command, cwd=directory, env=environment, input="",
                                capture_output=True, text=True, timeout=60, check=False)
        (directory / "configure.log").write_text(
            "Command: " + " ".join(command) + f"\nExit: {result.returncode}\n"
            + result.stdout + result.stderr, encoding="utf-8",
        )
        return directory, result

    def configured(self, target, build_type="N", enabled=True, thumb=None):
        directory, result = self.configure(target, build_type, enabled, thumb)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        header = (directory / "autoconf.h").read_text(encoding="utf-8")
        makefile = (directory / "Makefile").read_text(encoding="utf-8")
        if enabled:
            self.assertIn("#define HAVE_ESPEAK 1", header)
            self.assertIn("#define TARGET_EXTRA_THREADS 1", header)
            self.assertRegex(makefile, r"(?m)^export ESPEAK=1$")
        else:
            self.assertNotIn("HAVE_ESPEAK", header)
            self.assertNotIn("TARGET_EXTRA_THREADS", header)
            self.assertRegex(makefile, r"(?m)^export ESPEAK=$")
        return header, makefile

    def engine_configuration(self, makefile):
        exports, separator, remainder = makefile.partition("\ninclude $(TOOLSDIR)/root.make")
        self.assertTrue(separator, "Could not isolate configure exports from firmware build rules")
        variables = ("CC", "CXX", "GCCOPTS", "EXTRA_DEFINES", "ESPEAK_HOST_FLAGS",
                     "ESPEAK_CXXFLAGS", "ESPEAK_CFLAGS")
        probe = exports + "\ninclude $(ROOTDIR)/lib/espeak/espeak.make\n"
        probe += "".join(f"$(info {name}=$({name}))\n" for name in variables)
        probe += ".PHONY: espeak-flag-probe\nespeak-flag-probe:;\n"
        result = subprocess.run(
            ["make", "--no-print-directory", "--no-builtin-rules", "--no-builtin-variables",
             "--dry-run", "--file=-", "espeak-flag-probe"],
            input=probe, cwd=self.results, env={"PATH": os.environ["PATH"], "LC_ALL": "C"},
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        configuration = dict(line.split("=", 1) for line in result.stdout.splitlines()
                             if line.split("=", 1)[0] in variables)
        self.assertEqual(set(configuration), set(variables), result.stdout)
        return {name: shlex.split(value) for name, value in configuration.items()}

    def rejected(self, target, build_type="N"):
        directory, result = self.configure(target, build_type)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Integrated eSpeak supports", result.stdout)
        for filename in ("autoconf.h", "autoconf.h.new", "Makefile"):
            self.assertFalse((directory / filename).exists(), filename)

    def test_native_names_and_menu_selectors_keep_architecture_and_ids(self):
        for model, selector, target_id, model_number in (
                ("sansaclipplus", "62", 66, 66), ("sansaclipzip", "65", 68, 79)):
            for target in (model, selector):
                with self.subTest(target=target):
                    header, makefile = self.configured(target)
                    for definition in ("#define ARCH arch_arm", "#define ARCH_VERSION 5",
                                       "#define ROCKBOX_LITTLE_ENDIAN 1"):
                        self.assertIn(definition, header)
                    for export in (f"MODELNAME={model}", f"TARGET_ID={target_id}",
                                   "ARCH=arch_arm", "ARCH_VERSION=5", "CPU=arm",
                                   "MANUFACTURER=as3525", "MEMORYSIZE=8", "APP_TYPE=",
                                   "APPLICATION=", "BINARY=rockbox.sansa"):
                        self.assertRegex(makefile, rf"(?m)^export {re.escape(export)}$")
                    self.assertIn("-mcpu=arm926ej-s", makefile)
                    self.assertRegex(makefile, rf"(?m)^export CC=.*{re.escape(self.arm_prefix)}gcc$")
                    self.assertNotIn("thumb-cc.py", makefile)
                    self.assertNotIn("-mthumb-interwork", makefile)
                    self.assertNotIn("-DUSE_THUMB", makefile)
                    hardware = (ROOT / f"firmware/export/config/{model}.h").read_text(encoding="utf-8")
                    self.assertRegex(hardware, rf"(?m)^#define MODEL_NUMBER {model_number}$")
                    self.assertRegex(hardware, r"(?m)^#define CONFIG_CPU AS3525v2$")

    def test_native_thumb_preserves_cpp_wrapper_flags_and_arm_fallback(self):
        for target in NATIVE_TARGETS:
            for thumb in (False, True):
                with self.subTest(target=target, thumb=thumb):
                    header, makefile = self.configured(target, thumb=thumb)
                    configuration = self.engine_configuration(makefile)
                    compiler = configuration["CC"]
                    cpp_compiler = configuration["CXX"]
                    self.assertTrue(compiler[-1].endswith(self.arm_prefix + "gcc"), compiler)
                    self.assertEqual(cpp_compiler,
                                     [*compiler[:-1], compiler[-1].removesuffix("gcc") + "g++"])
                    self.assertEqual(compiler[:-1], [str(THUMB_WRAPPER)] if thumb else [])
                    self.assertIn("-mcpu=arm926ej-s", configuration["GCCOPTS"])
                    self.assertNotIn("-mthumb", configuration["GCCOPTS"])
                    self.assertEqual("-DUSE_THUMB" in configuration["EXTRA_DEFINES"], thumb)
                    host_flags = configuration["ESPEAK_HOST_FLAGS"]
                    self.assertIn("-mcpu=arm926ej-s", host_flags)
                    self.assertIn("-DRB_ESPEAK_NATIVE=1", host_flags)
                    self.assertIn("-std=c++11", host_flags)
                    self.assertNotIn("-std=gnu11", host_flags)
                    self.assertNotIn("-Wstrict-prototypes", host_flags)
                    for flags in (configuration["GCCOPTS"], host_flags):
                        self.assertEqual("-mthumb-interwork" in flags, thumb)
                    self.assertEqual(configuration["ESPEAK_CXXFLAGS"], ["-Os", "-g"])
                    self.assertEqual(configuration["ESPEAK_CFLAGS"], ["-Os", "-g"])
                    if thumb:
                        arguments = [*cpp_compiler[1:], *host_flags,
                                     *configuration["ESPEAK_CXXFLAGS"], "-MMD", "-MP", "-c",
                                     str(ROOT / "lib/espeak/rb_espeak.cpp"), "-o", "rb_espeak.o"]
                        for returncode in (0, 1):
                            with self.subTest(returncode=returncode):
                                attempted, delegate = invoke_thumb_wrapper(arguments, returncode)
                                attempted.assert_called_once_with(
                                    [*arguments, "-mthumb"], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                )
                                if returncode:
                                    delegate.assert_called_once_with(arguments[0], arguments)
                                else:
                                    delegate.assert_not_called()

    def test_other_native_firmware_is_rejected_even_with_shared_cpu_or_id(self):
        for target in ("sansaclip", "sansaclipv2", "sansafuzev2", "ipodvideo"):
            with self.subTest(target=target):
                self.rejected(target)

    def test_native_bootloaders_are_rejected(self):
        for target in NATIVE_TARGETS:
            for build_type in ("B", "ab"):
                with self.subTest(target=target, build_type=build_type):
                    self.rejected(target, build_type)

    def test_sdl_application_is_rejected(self):
        self.rejected("sdlapp")

    def test_auxiliary_tools_are_rejected(self):
        for target in NATIVE_TARGETS:
            for build_type in ("C", "D", "W"):
                with self.subTest(target=target, build_type=build_type):
                    self.rejected(target, build_type)

    def test_sdl_simulators_still_configure(self):
        for target in (*NATIVE_TARGETS, "sansafuzev2", "iriverh300"):
            with self.subTest(target=target):
                header, makefile = self.configured(target, "S")
                self.assertIn("#define ARCH arch_none", header)
                self.assertRegex(makefile, r"(?m)^export APP_TYPE=sdl-sim$")
                self.assertIn("-DSIMULATOR", makefile)
                configuration = self.engine_configuration(makefile)
                self.assertEqual(configuration["ESPEAK_CXXFLAGS"], ["-O2", "-g"])
                self.assertEqual(configuration["ESPEAK_CFLAGS"], ["-O2", "-g"])
                self.assertNotIn("-mthumb-interwork", configuration["ESPEAK_HOST_FLAGS"])
                self.assertNotIn(str(THUMB_WRAPPER), configuration["CXX"])

    def test_ordinary_builds_without_espeak_are_unchanged(self):
        for target, build_type in (
                ("sansaclipplus", "N"), ("sansaclipzip", "N"), ("sansafuzev2", "N"),
                ("sansaclipplus", "B"), ("sansaclipzip", "B"), ("sdlapp", "N"),
                ("sansaclipzip", "S")):
            with self.subTest(target=target, build_type=build_type):
                self.configured(target, build_type, enabled=False)


class NativeDocumentationTests(unittest.TestCase):
    def test_native_reconstruction_preserves_thumb_cpp_wrapper(self):
        for name in ("ESPEAK-CLIPPLUS.md", "ESPEAK-CLIPPLUS-PL.md",
                     "ESPEAK-CLIPZIP.md", "ESPEAK-CLIPZIP-PL.md"):
            with self.subTest(document=name):
                source = (ROOT / "docs" / name).read_text(encoding="utf-8")
                self.assertIn("--integrated-espeak --thumb --compiler-prefix=arm-none-eabi-", source)
                self.assertIn("make -j4 zip\n", source)
                self.assertNotRegex(source, r"CXX\s*=\s*arm-none-eabi-g\+\+")


if __name__ == "__main__":
    unittest.main(verbosity=2)
