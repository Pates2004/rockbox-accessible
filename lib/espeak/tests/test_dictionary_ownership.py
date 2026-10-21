import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from project_materials import confined_path, project_materials_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("data_parent", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sanitize", choices=("none", "address", "undefined"), default="none")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    output = confined_path(arguments.output.absolute(), project_materials_root(root))
    executable = arguments.executable.resolve(strict=True)
    supplied = arguments.data_parent.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "pl_dict").exists():
        raise RuntimeError("Refusing to overwrite an existing compiled dictionary")
    inputs = [supplied / name for name in ("dictsource/pl_list", "dictsource/pl_rules", "espeak-data/pl_dict")]
    fingerprints = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    if arguments.sanitize == "address":
        symbols = subprocess.check_output(["nm", "-u", str(executable)], text=True)
        if "__asan_init" not in symbols:
            raise RuntimeError("Dictionary ownership regression requires an ASan-instrumented executable")
    environment = dict(os.environ)
    environment["ASAN_OPTIONS"] = "detect_leaks=1:halt_on_error=1:abort_on_error=1"
    environment["LSAN_OPTIONS"] = "leak_check_at_exit=1:exitcode=23"
    environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
    result = subprocess.run([str(executable), str(supplied), str(supplied / "dictsource") + "/",
                             str(output)], capture_output=True, text=True, env=environment,
                            cwd=output, timeout=300)
    (output / "compiler-process.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    report = {"passed": result.returncode == 0, "sanitize": arguments.sanitize,
              "leak_check_enabled": arguments.sanitize == "address", "returncode": result.returncode,
              "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "input_sha256": fingerprints}
    for path in inputs:
        if hashlib.sha256(path.read_bytes()).hexdigest() != fingerprints[str(path)]:
            raise RuntimeError("Dictionary compiler changed a supplied input: " + str(path))
    if (output / "pl_dict").is_file():
        report["compiled_pl_dict_sha256"] = hashlib.sha256((output / "pl_dict").read_bytes()).hexdigest()
    (output / "ownership-result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise SystemExit(1)
    if "compiled_pl_dict_sha256" not in report:
        raise RuntimeError("Dictionary compiler produced no output")
    print("PASS: dictionary compiler process cleanup; sanitizer=" + arguments.sanitize)


if __name__ == "__main__":
    main()
