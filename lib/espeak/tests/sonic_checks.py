import hashlib
import json
from pathlib import Path
import sys
import subprocess


APPROVED_DOCUMENTATION_CHANGES = {
    "sonic/README.md": {
        "supplied_sha256": "fb015d72a022a6d86aaaa129fa25e2eb7f544c1345ffe6c8687e9447ecb06dad",
        "integrated_sha256": "ab9b8f73bf36483bd69e7350cd24ea9d41621ed77ba5b993ab25bc71825e08fc",
        "notice_date": "2026-10-21",
        "change": "Append the dated local modification notice; retain the original provenance text",
    }
}
ORIGINAL_SONIC_README_BYTES = 217


def check_dependency(source, supplied=None):
    provenance = json.loads((source / "LOCAL-PATCHES.json").read_text(encoding="utf-8"))
    paths = {"engine/compiledict.cpp": "src/compiledict.cpp",
             "engine/dictionary.cpp": "src/dictionary.cpp",
             "engine/translate.cpp": "src/translate.cpp",
             "engine/tr_languages.cpp": "src/tr_languages.cpp",
             "sonic/sonic.c": "platforms/windows/third_party/sonic/sonic.c"}
    if (provenance["schema_version"] != 1 or set(provenance["patches"]) != set(paths) or
            set(provenance["original_manifests"]) != {"UPSTREAM.sha256", "SONIC.sha256"}):
        raise SystemExit("Unrecognized local eSpeak memory safety patches")
    documentation = provenance.get("documentation_changes")
    if documentation != APPROVED_DOCUMENTATION_CHANGES:
        raise SystemExit("Unrecognized local Sonic documentation changes")
    for name, digest in provenance["original_manifests"].items():
        if name not in ("UPSTREAM.sha256", "SONIC.sha256") or hashlib.sha256(
                (source / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Original eSpeak provenance manifest changed: " + name)
    upstream = dict(line.split(None, 1)[::-1] for line in
                    (source / "UPSTREAM.sha256").read_text(encoding="utf-8").splitlines())
    original_sonic = dict(line.split(None, 1)[::-1] for line in
                          (source / "SONIC.sha256").read_text(encoding="utf-8").splitlines())
    for relative, supplied_path in paths.items():
        patch = provenance["patches"][relative]
        expected = upstream[supplied_path] if relative.startswith("engine/") else original_sonic[relative]
        if patch["supplied_path"] != supplied_path or patch["supplied_sha256"] != expected:
            raise SystemExit("Local patch no longer identifies the original supplied source: " + relative)
        if hashlib.sha256((source / relative).read_bytes()).hexdigest() != patch["integrated_sha256"]:
            raise SystemExit("Local memory safety source mismatch: " + relative)
        if supplied is not None and hashlib.sha256(
                (supplied / supplied_path).read_bytes()).hexdigest() != expected:
            raise SystemExit("Original supplied memory safety input changed: " + supplied_path)
    for relative, original in original_sonic.items():
        content = (source / relative).read_bytes()
        expected = (provenance["patches"][relative]["integrated_sha256"]
                    if relative in provenance["patches"] else original)
        if relative in documentation:
            change = documentation[relative]
            if change["supplied_sha256"] != original:
                raise SystemExit("Original Sonic documentation provenance changed: " + relative)
            if (len(content) < ORIGINAL_SONIC_README_BYTES or hashlib.sha256(
                    content[:ORIGINAL_SONIC_README_BYTES]).hexdigest() != original):
                raise SystemExit("Original Sonic README prefix mismatch: " + relative)
            notice = ("\n## Local modification notice, " + change["notice_date"] + "\n\n").encode("ascii")
            if not content[ORIGINAL_SONIC_README_BYTES:].startswith(notice):
                raise SystemExit("Missing dated Sonic README modification notice: " + relative)
            expected = change["integrated_sha256"]
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected:
            raise SystemExit("Vendored Sonic byte mismatch: " + relative)
        if supplied is not None and hashlib.sha256(
                (supplied / "platforms/windows/third_party" / relative).read_bytes()).hexdigest() != original:
            raise SystemExit("Original supplied Sonic byte mismatch: " + relative)
    return provenance


def run_sonic_checks(run, source, target, build, data_parent, prefix=(),
                     compiler_prefix="", flags=(), enabled=True,
                     windows=False, environment=None):
    common = ["espeak_SetSonicRate", "espeak_SetSynthCallback", "espeak_Synth"]
    sonic = ["sonicCreateStream", "sonicDestroyStream", "sonicWriteShortToStream",
             "sonicReadShortFromStream", "sonicFlushStream"] if enabled else []
    wrapped = ["-Wl,--wrap=" + symbol for symbol in common + sonic]
    run([*prefix, compiler_prefix + "gcc", "-std=c11", "-g", "-O1", "-Wall", "-Wextra",
         "-Werror", *flags, "-DRB_ESPEAK_HAVE_SONIC=" + str(int(enabled)), "-I" + source,
         "-c", source + "/tests/test_sonic.c", "-o", target + "/test_sonic.o"],
        build / "build-sonic-test.log")
    platform_flags = ["-static", "-municode"] if windows else []
    executable = build / ("test_sonic.exe" if windows else "test_sonic")
    run([*prefix, compiler_prefix + "g++", *flags, *platform_flags, *wrapped,
         target + "/test_sonic.o", target + "/lib/libespeak.a", "-lm", "-o",
         target + "/" + executable.name], build / "link-sonic-test.log")
    run([str(executable), str(data_parent)], build / "sonic.log", environment)
    print((build / "sonic.log").read_text(encoding="utf-8").splitlines()[-1])
    if enabled:
        check_chunks(executable, data_parent, build, environment)


def check_chunks(executable, data_parent, build, environment=None):
    references = {
        451: (744572, "db96c5cff16c00f009b5f77d1f7019d39d5d06bb1413db1691ba6e808011024d"),
        1350: (245342, "40fda00923e0ea22dca6359f5614f274dd55506ac65dcdc550211b97ff0ab883"),
    }
    reports = []
    for rate, (byte_count, digest) in references.items():
        result = subprocess.run([str(executable), str(data_parent), "--chunk-check", str(rate)],
                                capture_output=True, env=environment, check=False)
        diagnostics = result.stderr.decode("utf-8", errors="replace")
        (build / ("chunks-" + str(rate) + ".log")).write_text(diagnostics, encoding="utf-8")
        if result.returncode:
            raise SystemExit("Chunk regression failed: " + diagnostics)
        report = json.loads(diagnostics)
        report.update(bytes=len(result.stdout), sha256=hashlib.sha256(result.stdout).hexdigest())
        if report["bytes"] != byte_count or report["sha256"] != digest:
            raise SystemExit("Chunking changed the pre-fix high-rate PCM: " + repr(report))
        if (report["blocks"] != (report["samples"] + 440) // 441 or
                report["normal_partial_blocks"] != 0 or report["partial_blocks"] > 1):
            raise SystemExit("Fragmented high-rate output: " + repr(report))
        reports.append(report)
    (build / "chunks.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    print("PASS: full441-sample callbacks, final partial only; pre-fix451/1350 PCM SHA-256 unchanged")


def check_pcm(run, root, executable, data_parent, build, environment=None):
    expected_hash = ("405c9cc6ef2173475c6f37303e4a5b25e293c405ff440d9734743b1be8524a25"
                     if sys.platform == "win32" else
                     "1a2ade4051947d592063dad58586bd6cfe9fddf5b152e9b30d13984d95fd22bc")
    expected = {"bytes": 14678750, "sha256": expected_hash}
    for attempt in ("pcm-first", "pcm-repeat"):
        output = build / attempt
        run([sys.executable, str(root / "lib/espeak/tests/hash_pcm.py"), str(executable),
             str(data_parent), str(output)], build / (attempt + ".log"), environment)
        actual = json.loads((output / "pcm.sha256.json").read_text(encoding="utf-8"))
        if actual != expected:
            raise SystemExit("Ordinary PCM regression: " + repr(actual))
    print("PASS: two ordinary corpus runs are byte-identical to supplied r34 " + expected_hash)
