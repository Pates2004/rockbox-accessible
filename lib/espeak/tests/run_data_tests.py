"""Compare real PL/EN PCM and phonemes with one engine and two data sets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_provenance import validate_supplied_data


CHANGED = {
    "singer", "singera", "singerem", "singerowi", "singing", "singingu",
    "ziscic", "zisci", "ziscil", "ziscila", "ziscilo", "ziscili", "ziscily",
    "zisc", "ziscmy", "zisccie", "ziszczac", "ziszcza", "ziszczony",
    "ziszczenie", "ziszczenia", "ziszczeniu",
}


def runtime_hashes(parent):
    data = parent / "espeak-data"
    return {path.relative_to(data).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(data.rglob("*")) if path.is_file()}


def capture(executable, data, output, label):
    cases = subprocess.check_output([str(executable), "--list"], text=True).splitlines()
    if len(cases) != 48 or len(set(cases)) != 48 or not CHANGED.issubset(cases):
        raise ValueError("Incomplete Polish data corpus case list")
    lines = []
    diagnostics = []
    for identifier in cases:
        for rate in (175, 451, 1350):
            result = subprocess.run(
                [str(executable), str(data), str(output / (label + ".trace")), identifier, str(rate)],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
                env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
            lines.append(result.stdout)
            diagnostics.append(result.stderr)
            if result.returncode:
                raise ValueError(f"Data synthesis failed ({result.returncode}): {label}/{identifier}/{rate}: {result.stderr}")
    result_text = "".join(lines)
    (output / (label + ".tsv")).write_text(result_text, encoding="utf-8")
    (output / (label + ".log")).write_text("".join(diagnostics), encoding="utf-8")
    records = {}
    for line in result_text.splitlines():
        identifier, language, rate, samples, checksum, phonemes = line.split("\t")
        key = identifier + ":" + rate
        if key in records or int(samples) <= 0 or not phonemes.strip():
            raise ValueError(f"Invalid corpus result: {line}")
        records[key] = {"language": language, "samples": int(samples), "pcm": int(checksum),
                        "phonemes": phonemes.strip()}
    if len(records) != 144:
        raise ValueError(f"Incomplete data corpus: {len(records)}")
    return records


def compare(previous, current):
    if set(previous) != set(current):
        raise ValueError("Data corpus cases changed between runs")
    differences = []
    for key, actual in current.items():
        identifier, rate = key.split(":")
        reference = previous[key]
        phonemes_changed = actual["phonemes"] != reference["phonemes"]
        pcm_changed = (actual["samples"], actual["pcm"]) != (reference["samples"], reference["pcm"])
        expected = identifier in CHANGED
        if phonemes_changed != expected or pcm_changed != expected:
            raise ValueError(f"Unexpected supplied-data effect: {key}: {reference} -> {actual}")
        if expected:
            if identifier.startswith("zi") and not actual["phonemes"].startswith("z"):
                raise ValueError(f"Expected hard z in {key}: {actual['phonemes']}")
            if identifier.startswith("sing") and not actual["phonemes"].startswith("S;"):
                raise ValueError(f"Expected soft s in {key}: {actual['phonemes']}")
            differences.append({"case": key, "previous": reference, "current": actual})
    return differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--native-executable", type=Path)
    arguments = parser.parse_args()
    source = arguments.source.resolve(strict=True)
    baseline = arguments.baseline.resolve(strict=True)
    executable = arguments.executable.resolve(strict=True)
    provenance = validate_supplied_data(source)
    old_hashes = runtime_hashes(baseline)
    new_hashes = provenance["runtime_data"]
    if set(old_hashes) != set(new_hashes):
        raise ValueError("Baseline/current runtime inventories differ")
    changed = {name for name, digest in new_hashes.items() if old_hashes[name] != digest}
    if changed != {"pl_dict"} or old_hashes["pl_dict"] != "649be6f9ea09b231939f7e15271459c5331c6d176dec2feb4c2a62820ec1bb8e":
        raise ValueError(f"Baseline does not isolate the previous r34 Polish dictionary: {changed}")
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    previous = capture(executable, baseline, output, "previous")
    current = capture(executable, source, output, "current")
    repeated = capture(executable, source, output, "repeat")
    if current != repeated:
        raise ValueError("Supplied-data synthesis is not deterministic")
    differences = compare(previous, current)
    native_matches = None
    if arguments.native_executable:
        native = capture(arguments.native_executable.resolve(strict=True), source, output, "native")
        if set(native) != set(current) or any(
                (native[key]["samples"], native[key]["pcm"]) != (value["samples"], value["pcm"])
                for key, value in current.items()):
            raise ValueError("Native bounded adapter changed supplied-data PCM")
        native_matches = len(native)
    if validate_supplied_data(source) != provenance or runtime_hashes(baseline) != old_hashes:
        raise ValueError("Data changed during synthesis validation")
    report = {
        "passed": True, "provenance": provenance,
        "engine_executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "baseline_parent": str(baseline), "supplied_parent": str(source),
        "baseline_dictionary_sha256": old_hashes["pl_dict"],
        "current_dictionary_sha256": new_hashes["pl_dict"],
        "cases": len(current), "changed_cases": len(differences),
        "unchanged_cases": len(current) - len(differences), "repeat_identical": True,
        "isolated_process_per_utterance": True,
        "native_matching_cases": native_matches, "differences": differences,
        "scope": "Isolated synthesis into callbacks; no audio device, foreground input or player execution",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(current)} data cases; {len(differences)} expected changes; "
          f"{len(current) - len(differences)} preserved; repeat identical; native={native_matches}")
    print(output)


if __name__ == "__main__":
    main()
