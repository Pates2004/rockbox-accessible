"""Run the supplied native eSpeak integration on MIPSel Linux under QEMU.

This is a command-line harness, not an automatically collected hardware test.
It needs an already provisioned official Rockbox hosted GCC 9.5.0 toolchain.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[2]
ESPEAK = ROOT / "lib/espeak"
PREFIX = "mipsel-rockbox-linux-gnu-"
FLAGS = ["-march=mips32r2", "-mabi=32", "-EL", "-mhard-float", "-mfp32",
         "-mno-mips16", "-fPIC", "-fno-strict-overflow"]
ENGINE_NAMES = ("speak_lib", "compiledict", "dictionary", "intonation", "readclause",
                "setlengths", "numbers", "synth_mbrola", "synthdata", "synthesize",
                "translate", "tr_languages", "voices", "wavegen", "phonemelist", "klatt")
RUNTIME_CASES = ("heap", "files", "errors", "unicode", "buffered-seek", "numbers", "flags")
PASS_ENGINE = ("PASS: native services, 54 languages, 105 variants, rates, punctuation, "
               "events, cancellation and reentry")
SCOPE = ("QEMU MIPS32r2 little-endian O32 hard-float native eSpeak, Sonic, TLSF and "
         "utf8proc with mocked Rockbox files/headers; no physical X1600, application "
         "startup, ALSA playback, Bluetooth, accessibility, battery or RAM acceptance")


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def fingerprint(files, base):
    return {path.relative_to(base).as_posix(): {"bytes": path.stat().st_size,
                                              "sha256": digest(path)}
            for path in sorted(set(files))}


def tree_files(directory):
    return [path for path in directory.rglob("*") if path.is_file()
            and "__pycache__" not in path.parts]


def source_fingerprint():
    files = list(itertools.chain.from_iterable(tree_files(ROOT / name) for name in
                 ("lib/espeak", "lib/tlsf", "lib/utf8proc")))
    files += [Path(__file__).resolve(), ROOT / "tools/project_materials.py",
              ROOT / "tools/tests/test_espeak_hiby_mips_harness.py",
              ROOT / "tools/tests/test_espeak_native_runtime.py",
              ROOT / "tools/tests/test_espeak_hosted_runtime.py", ROOT / "tools/configure"]
    return fingerprint(files, ROOT)


def input_fingerprint(tools, data_parent, sysroot):
    return {"sources": source_fingerprint(),
            "data": fingerprint(tree_files(data_parent / "espeak-data"), data_parent),
            "sysroot": fingerprint(tree_files(sysroot), sysroot),
            "tools": {name: {"path": str(path), "sha256": digest(path)} for name, path in tools.items()}}


def manifest_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def load_test(name):
    specification = importlib.util.spec_from_file_location(
        name, ROOT / "tools/tests" / (name + ".py"))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class Evidence:
    def __init__(self, directory, environment, timeout):
        self.directory = directory
        self.environment = environment
        self.timeout = timeout
        self.count = 0

    def command(self, arguments, build=None, label="command", environment=None):
        self.count += 1
        arguments = list(map(str, arguments))
        working = build or self.directory
        record = self.directory / "commands" / (f"{self.count:04d}-" + label)
        record.mkdir(parents=True, exist_ok=False)
        write_json(record / "command.json", {"argv": arguments, "cwd": str(working),
                   "command": shlex.join(arguments), "timeout_seconds": self.timeout,
                   "started_utc": datetime.now(timezone.utc).isoformat()})
        print(f"[{self.count:04d}] {label}", flush=True)
        outcome = {}
        with (record / "stdout.log").open("xb") as stdout, (record / "stderr.log").open("xb") as stderr:
            try:
                result = subprocess.run(arguments, cwd=working, env=environment or self.environment,
                                        stdout=stdout, stderr=stderr, timeout=self.timeout, check=False)
                outcome["returncode"] = result.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                outcome["error"] = str(error)
            finally:
                outcome["finished_utc"] = datetime.now(timezone.utc).isoformat()
                write_json(record / "result.json", outcome)
        if outcome.get("returncode") != 0:
            raise RuntimeError(f"{label} failed: {outcome}; logs: {record}")
        return (record / "stdout.log").read_text(encoding="utf-8", errors="replace")

    def seal(self):
        write_json(self.directory / "integrity.json", fingerprint(tree_files(self.directory), self.directory))
        for path in tree_files(self.directory):
            path.chmod(0o444)
        for path in sorted((path for path in self.directory.rglob("*") if path.is_dir()),
                           key=lambda path: len(path.parts), reverse=True):
            path.chmod(0o555)
        self.directory.chmod(0o555)


def available_tools(arguments):
    if sys.platform != "linux":
        raise RuntimeError("Run inside Linux/WSL with the provisioned hosted toolchain")
    directory = arguments.toolchain_bin.resolve(strict=True)
    if not directory.is_dir():
        raise RuntimeError("--toolchain-bin must name the actual toolchain bin directory")
    tools = {name: directory / (PREFIX + name) for name in ("gcc", "readelf")}
    qemu = shutil.which(str(arguments.qemu))
    if qemu is None:
        raise RuntimeError(f"Missing QEMU: {arguments.qemu}; supply --qemu with an existing executable")
    tools["qemu"] = Path(qemu).resolve(strict=True)
    for name, path in tools.items():
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Missing executable {name}: {path}; wait for toolchain provisioning")
    return tools


def elf_abi(path, executable=True):
    image = path.read_bytes()
    if len(image) < 52 or image[:7] != b"\x7fELF\x01\x01\x01":
        raise RuntimeError(f"Expected ELF32 little-endian: {path}")
    (kind, machine, version, entry, program_offset, section_offset, flags, header_size,
     program_size, program_count, section_size, section_count, section_names) = struct.unpack_from(
         "<HHIIIIIHHHHHH", image, 16)
    isa_contracts = {0x70000000: (32, 2)}
    if not executable:
        isa_contracts.update({0x00000000: (1, 0), 0x50000000: (32, 1)})
    isa = isa_contracts.get(flags & 0xf0000000)
    contract = "MIPS32r2" if executable else "MIPS1/MIPS32/MIPS32r2 runtime"
    if (machine != 8 or version != 1 or header_size != 52 or kind not in (2, 3)
            or isa is None or flags & 0xf000 != 0x1000 or flags & 0x06000620):
        raise RuntimeError(f"Expected {contract} O32 without MIPS16/microMIPS/ABI2/FP64/NaN2008: {path}")
    if section_size != 40 or not section_count or section_offset + section_count * 40 > len(image):
        raise RuntimeError(f"Malformed ELF section table: {path}")
    sections = [struct.unpack_from("<IIIIIIIIII", image, section_offset + index * 40)
                for index in range(section_count)]
    abi_sections = [section for section in sections if section[1] == 0x7000002a]
    if len(abi_sections) != 1 or abi_sections[0][5] != 24:
        raise RuntimeError(f"Missing MIPS ABI flags: {path}")
    section = abi_sections[0]
    abi = struct.unpack("<HBBBBBBIIII", image[section[4]:section[4] + 24])
    compatible = (abi[0] == 0 and abi[1:3] == isa and abi[3] == 1 and abi[5] == 0
                  and (abi[6] == 1 and abi[4] == 1 or abi[6] == 5 and abi[4] in (0, 1)))
    if (not compatible or abi[7] or abi[8]
            or executable and abi[:7] != (0, 32, 2, 1, 1, 0, 1)):
        raise RuntimeError(f"Expected {contract} O32 FP32-compatible hard-float double ABI: {path}: {abi}")
    if program_size != 32 or not program_count or program_offset + program_count * 32 > len(image):
        raise RuntimeError(f"Malformed ELF program table: {path}")
    programs = [struct.unpack_from("<IIIIIIII", image, program_offset + index * 32)
                for index in range(program_count)]
    interpreters = [image[program[1]:program[1] + program[4]]
                    for program in programs if program[0] == 3]
    if executable and (not entry or interpreters != [b"/lib/ld.so.1\0"]):
        raise RuntimeError(f"Unexpected executable entry/interpreter: {path}")
    architecture = {(1, 0): "MIPS1", (32, 1): "MIPS32", (32, 2): "MIPS32r2"}[isa]
    return {"sha256": digest(path), "bytes": len(image), "elf_flags": hex(flags),
            "mips_abi_flags": list(abi), "interpreter": "/lib/ld.so.1" if interpreters else None,
            "abi_contract": "application-exact" if executable else "runtime-compatible",
            "architecture": architecture + " little-endian O32 hard-float (FP32-compatible)"}


def inspect_elf(evidence, tools, executable, label, library=False):
    report = elf_abi(executable, executable=not library)
    evidence.command([tools["readelf"], "-h", "-A", "-l", "-W", executable], label=label + "-abi")
    dynamic = evidence.command([tools["readelf"], "-d", "-W", executable], label=label + "-dynamic")
    versions = evidence.command([tools["readelf"], "-V", "-W", executable], label=label + "-versions")
    symbols = evidence.command([tools["readelf"], "-s", "-W", executable], label=label + "-symbols")
    needed = re.findall(r"\(NEEDED\).*\[([^\]]+)\]", dynamic)
    allowed = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libgcc_s.so.1", "ld.so.1"}
    if (not library and "libc.so.6" not in needed) or not set(needed) <= allowed:
        raise RuntimeError(f"Unexpected dependencies in {label}: {needed}")
    if re.search(r"\((?:RPATH|RUNPATH)\)", dynamic):
        raise RuntimeError(f"Unexpected library search path in {label}")
    needs_section = versions.partition("Version needs section")[2]
    requirements = sorted(set(re.findall(r"Name: (GLIBC_[\w.]+)", needs_section)))
    public_requirements = [name for name in requirements if not library or name != "GLIBC_PRIVATE"]
    if (not library and not requirements) or any(not re.fullmatch(r"GLIBC_\d+(?:\.\d+)+", name)
                                                or tuple(map(int, name[6:].split("."))) > (2, 16)
                                                for name in public_requirements):
        raise RuntimeError(f"GLIBC requirements exceed 2.16 in {label}: {requirements}")
    undefined = [line for line in symbols.splitlines() if re.search(r"\bUND\b", line)]
    if any(re.search(r"\b(?:__atomic_\w*|__cxa_(?:throw|guard_\w*|allocate_exception)|__gxx_\w*|_Zn\w*|_Zd\w*)", line)
           for line in undefined):
        raise RuntimeError(f"Unexpected atomic/C++ runtime imports in {label}")
    report.update(needed=needed, glibc_requirements=requirements)
    return report


def inspect_libraries(evidence, tools, sysroot, artifacts):
    pending = {name for artifact in artifacts.values() for name in artifact["needed"]} | {"ld.so.1"}
    libraries = {}
    while pending:
        name = sorted(pending)[0]
        pending.remove(name)
        if name in libraries:
            continue
        candidates = [sysroot / directory / name for directory in ("lib", "usr/lib", "lib32", "usr/lib32")]
        if name == "libgcc_s.so.1":
            candidates.append(tools[name])
        path = next((path.resolve(strict=True) for path in candidates if path.is_file()), None)
        if path is None:
            raise RuntimeError(f"Missing runtime dependency in actual sysroot: {name}")
        if sysroot not in path.parents and path != tools.get("libgcc_s.so.1"):
            raise RuntimeError(f"Runtime dependency escapes actual sysroot: {path}")
        result = inspect_elf(evidence, tools, path, "library-" + name, library=True)
        result["path"] = str(path)
        libraries[name] = result
        pending.update(set(result["needed"]) - set(libraries))
    return libraries


def parse_engine(output):
    rows = {}
    for line in output.splitlines():
        if not line.startswith("PCM "):
            continue
        match = re.fullmatch(r"PCM (pl|en) (\d+) ([0-3]) (\d+) (\d+)", line)
        if not match:
            raise RuntimeError(f"Malformed PCM result: {line}")
        language, rate, punctuation, samples, pcm_hash = match.groups()
        key = f"{language}/{rate}/{punctuation}"
        if key in rows or int(samples) < 1 or not 0 <= int(pcm_hash) < 2 ** 64:
            raise RuntimeError(f"Invalid or repeated PCM case: {line}")
        rows[key] = {"samples": int(samples), "fnv1a_u16": int(pcm_hash)}
    expected = {f"{language}/{rate}/{punctuation}" for language in ("pl", "en")
                for rate in (80, 175, 450, 451, 1350) for punctuation in range(4)}
    if set(rows) != expected or PASS_ENGINE not in output.splitlines():
        raise RuntimeError("Incomplete 54-language/105-variant/40-PCM engine probe")
    heap = re.findall(r"^HEAP capacity=(\d+) used=(\d+) peak=(\d+) failures=(\d+)$", output, re.M)
    if len(heap) != 1 or int(heap[0][3]) < 1:
        raise RuntimeError("Missing engine heap exhaustion/recovery evidence")
    capacity, used, peak, failures = map(int, heap[0])
    if not 0 < used <= peak <= capacity:
        raise RuntimeError("Invalid engine heap accounting")
    return {"pcm": rows, "heap": dict(capacity=capacity, used=used, peak=peak, failures=failures)}


def build_probes(evidence, tools, build):
    runtime = load_test("test_espeak_native_runtime")
    with mock.patch.dict(sys.modules, test_espeak_native_runtime=runtime):
        hosted = load_test("test_espeak_hosted_runtime")
    compiler = tools["gcc"]
    with mock.patch.object(runtime, "command", evidence.command):
        objects = runtime.build_runtime(build / "runtime", FLAGS, compiler=compiler, hosted=True)
    irq_expectation = "mock_irq_transitions == 8"
    if runtime.RUNTIME_PROBE.count(irq_expectation) != 1:
        raise RuntimeError("Shared IRQ probe changed; review its hosted expectation before running")
    runtime_probe = runtime.RUNTIME_PROBE.replace(irq_expectation, "mock_irq_transitions == 0")
    probes = {}
    for name, source, extra in (("runtime", runtime_probe, []),
                                ("hosted", hosted.PROBE, ["-pthread"])):
        source_path = build / (name + "-probe.c")
        source_path.write_text(source, encoding="utf-8")
        executable = build / (name + "-probe")
        evidence.command([compiler, *FLAGS, "-std=gnu11", "-O2", "-g", "-Wall", "-Wextra", "-Werror",
                          "-I" + str(ESPEAK / "native"), source_path, *objects,
                          "-Wl,--gc-sections", *extra, "-lm", "-no-pie", "-o", executable],
                         label="link-" + name)
        probes[name] = executable
    (build / "fixture.dat").write_bytes(b"abc\n" + b"q" * 1532 + b"xyz")
    for source in [ESPEAK / "rb_espeak.cpp", *(ESPEAK / "engine" / (name + ".cpp")
                                              for name in ENGINE_NAMES), ESPEAK / "sonic/sonic.c"]:
        destination = build / (source.stem + ".o")
        language = (["-x", "c", "-std=c11"] if source.suffix == ".c" else
                    ["-x", "c++", "-std=c++11", "-nostdinc++", "-fno-exceptions", "-fno-rtti",
                     "-fno-threadsafe-statics", "-fno-use-cxa-atexit"])
        evidence.command([compiler, *FLAGS, *language, "-O2", "-g", "-ffunction-sections",
                          "-fdata-sections", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
                          "-DRB_ESPEAK_NATIVE=1", "-DRB_ESPEAK_HAVE_SONIC=1",
                          "-I" + str(ESPEAK / "native/include"), "-I" + str(ESPEAK / "native"),
                          "-I" + str(ESPEAK), "-I" + str(ESPEAK / "engine"),
                          "-c", source, "-o", destination], label="compile-" + source.stem)
        objects.append(destination)
    probe = build / "backend-probe.o"
    evidence.command([compiler, *FLAGS, "-std=c11", "-O2", "-g", "-Wall", "-Wextra", "-Werror",
                      "-DRB_ESPEAK_NATIVE_TEST_STATS=1", "-I" + str(ESPEAK), "-c",
                      ESPEAK / "tests/test_native_backend.c", "-o", probe], label="compile-backend-probe")
    executable = build / "native-engine-test"
    evidence.command([compiler, *FLAGS, probe, *objects, "-Wl,--gc-sections",
                      "-Wl,-Map=" + str(build / "engine-link.map"), "-lm", "-no-pie", "-o", executable],
                     label="link-engine")
    probes["engine"] = executable
    return probes


def execute_smoke(evidence, tools, data_parent, report):
    compiler = tools["gcc"]
    machine = evidence.command([compiler, "-dumpmachine"], label="gcc-target").strip()
    version = evidence.command([compiler, "-dumpfullversion"], label="gcc-version").strip()
    if machine != PREFIX[:-1] or version != "9.5.0":
        raise RuntimeError(f"Expected official hosted {PREFIX[:-1]} GCC 9.5.0; found {machine} {version}")
    evidence.command([compiler, "-v"], label="gcc-configuration")
    evidence.command([tools["qemu"], "--version"], label="qemu-version")
    evidence.command([tools["readelf"], "--version"], label="readelf-version")
    sysroot_text = evidence.command([compiler, "-print-sysroot"], label="gcc-sysroot").strip()
    if not sysroot_text or not Path(sysroot_text).is_absolute():
        raise RuntimeError("Compiler did not report an absolute actual sysroot")
    sysroot = Path(sysroot_text).resolve(strict=True)
    if not sysroot.is_dir() or not (sysroot / "lib/ld.so.1").is_file():
        raise RuntimeError(f"Missing actual MIPSel sysroot/loader: {sysroot}")
    for name in ("cc1", "cc1plus", "as", "ld"):
        location = evidence.command([compiler, "-print-prog-name=" + name], label="gcc-program-" + name).strip()
        path = shutil.which(location, path=evidence.environment["PATH"])
        if not path:
            raise RuntimeError(f"Missing compiler component {name}: {location}; provisioning is incomplete")
        tools[name] = Path(path).resolve(strict=True)
    for name in ("libgcc.a", "libgcc_s.so.1", "crtbegin.o", "crtend.o"):
        location = evidence.command([compiler, *FLAGS, "-print-file-name=" + name],
                                    label="gcc-file-" + name.replace(".", "-")).strip()
        if not Path(location).is_absolute() or not Path(location).is_file():
            raise RuntimeError(f"Missing compiler link input {name}: {location}")
        tools[name] = Path(location).resolve(strict=True)
    report.update(compiler_target=machine, compiler_version=version, sysroot=str(sysroot),
                  qemu_cpu="24Kf (MIPS32r2 FP32 surrogate, not an X1600 device model)")
    before = input_fingerprint(tools, data_parent, sysroot)
    write_json(evidence.directory / "inputs-before.json", before)
    report["input_fingerprint_sha256"] = manifest_digest(before)
    macros = evidence.command([compiler, *FLAGS, "-dM", "-E", "-x", "c", "-include", "features.h",
                               "/dev/null"], label="gcc-libc-and-abi-macros")
    definitions = dict(re.findall(r"^#define (\w+) (.+)$", macros, re.M))
    expected = {"__GLIBC__": "2", "__GLIBC_MINOR__": "27", "__SIZEOF_POINTER__": "4",
                "__mips_isa_rev": "2", "__MIPSEL__": "1", "__mips_hard_float": "1"}
    if any(definitions.get(name) != value for name, value in expected.items()):
        raise RuntimeError("Expected glibc 2.27 headers and MIPS32r2 LE O32 hard-float compiler macros")
    report["compiler_abi_macros"] = {name: definitions[name] for name in expected}
    build = evidence.directory / "build"
    build.mkdir()
    probes = build_probes(evidence, tools, build)
    report["artifacts"] = {name: inspect_elf(evidence, tools, path, name) for name, path in probes.items()}
    report["runtime_libraries"] = inspect_libraries(evidence, tools, sysroot, report["artifacts"])
    runner = [tools["qemu"], "-cpu", "24Kf", "-L", sysroot]
    for case in RUNTIME_CASES:
        output = evidence.command([*runner, probes["runtime"], case, build / "fixture.dat", build],
                                  label="run-runtime-" + case)
        if "PASS native runtime" not in output.splitlines():
            raise RuntimeError(f"Missing native runtime success marker: {case}")
    output = evidence.command([*runner, probes["hosted"]], label="run-hosted-threads")
    if "PASS hosted exclusion, reentry and readiness publication" not in output.splitlines():
        raise RuntimeError("Hosted concurrency probe did not complete")
    results = [parse_engine(evidence.command([*runner, probes["engine"], data_parent],
                                             label=f"run-engine-{iteration}")) for iteration in (1, 2)]
    report["engine_runs"] = results
    if results[0] != results[1]:
        raise RuntimeError("Repeated MIPS runs changed PCM/heap fingerprints")
    report.update(passed=True, runtime_cases=list(RUNTIME_CASES), hosted_threads=4,
                  languages=54, variants=105, pcm_cases=40, repeatable_mips_pcm=True,
                  x86_pcm_equality="Not tested or claimed; floating-point results may differ across architectures")


def main(argv=None):
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain-bin", type=Path, required=True,
                        help="Actual provisioned official mipsel-rockbox-linux-gnu GCC 9.5.0 bin directory")
    parser.add_argument("--data-parent", type=Path, required=True,
                        help="Parent of espeak-data in the supplied eSpeak 1.44.05 checkout (read only)")
    parser.add_argument("--qemu", default="qemu-mipsel", help="Existing qemu-mipsel or qemu-mipsel-static executable")
    parser.add_argument("--timeout", type=int, default=900, help="Positive per-command timeout in seconds")
    arguments = parser.parse_args(argv)
    evidence = None
    report = {"passed": False, "sources_frozen": False, "scope": SCOPE,
              "source_project": str(ROOT), "publication": False,
              "flags": FLAGS, "started_utc": datetime.now(timezone.utc).isoformat()}
    try:
        if arguments.timeout < 1:
            raise RuntimeError("--timeout must be positive")
        tools = available_tools(arguments)
        data_parent = arguments.data_parent.resolve(strict=True)
        for name in ("phondata", "phonindex", "phontab", "intonations"):
            if not (data_parent / "espeak-data" / name).is_file():
                raise RuntimeError(f"Missing supplied eSpeak data: {data_parent / 'espeak-data' / name}")
        sys.path.insert(0, str(ROOT / "tools"))
        from project_materials import confined_path, ensure_ignored_directories, project_materials_root
        central = project_materials_root(ROOT)
        ensure_ignored_directories(central.parent, (central.name,))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        directory = confined_path(central / "espeak-hiby-mips" / stamp, central)
        directory.mkdir(parents=True, exist_ok=False)
        environment = dict(os.environ)
        for name in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "GCC_EXEC_PREFIX",
                     "COMPILER_PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG_OUTPUT",
                     "LD_PROFILE", "LD_PROFILE_OUTPUT", *(name for name in environment if name.startswith("QEMU_"))):
            environment.pop(name, None)
        temporary = directory / "tmp"
        temporary.mkdir()
        environment.update(LC_ALL="C", LANG="C", TMPDIR=str(temporary),
                           PATH=str(arguments.toolchain_bin.resolve()) + os.pathsep + environment.get("PATH", ""))
        evidence = Evidence(directory, environment, arguments.timeout)
        report["data_parent"] = str(data_parent)
        report["environment"] = {name: environment[name] for name in ("PATH", "LC_ALL", "LANG", "TMPDIR")}
        print(f"Evidence (retained diagnostics, not a release): {directory}", flush=True)
        try:
            execute_smoke(evidence, tools, data_parent, report)
        finally:
            baseline = directory / "inputs-before.json"
            if baseline.is_file():
                before = json.loads(baseline.read_text(encoding="utf-8"))
                after = input_fingerprint(tools, data_parent, Path(report["sysroot"]))
                write_json(directory / "inputs-after.json", after)
                report["sources_frozen"] = before == after
                if before != after:
                    report["passed"] = False
                    report["changed_inputs"] = {group: sorted(name for name in set(before[group]) | set(after[group])
                                                              if before[group].get(name) != after[group].get(name))
                                                for group in before}
                    raise RuntimeError("Source/data/toolchain fingerprints changed; rerun after main's freeze")
    except (OSError, RuntimeError, AssertionError, ValueError, struct.error) as error:
        report["passed"] = False
        report["error"] = str(error)
        print(f"FAIL: {error}", file=sys.stderr)
    except KeyboardInterrupt:
        report["passed"] = False
        report["error"] = "Interrupted; this run is not acceptance evidence"
        print("FAIL: interrupted", file=sys.stderr)
    finally:
        if evidence is not None:
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(evidence.directory / "report.json", report)
            evidence.seal()
            print(f"Sealed evidence: {evidence.directory}", flush=True)
    if report["passed"]:
        print("PASS: MIPS/QEMU integration smoke; " + SCOPE)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
