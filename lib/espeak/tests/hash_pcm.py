import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("data_parent", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--compare", type=Path)
    arguments = parser.parse_args()
    executable = arguments.executable.resolve(strict=True)
    data_parent = arguments.data_parent.resolve(strict=True)
    output = arguments.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    byte_count = 0
    log = output / "pcm.log"
    with log.open("w", encoding="utf-8") as diagnostics:
        with subprocess.Popen([str(executable), str(data_parent), str(output), "pcm"],
                              stdout=subprocess.PIPE, stderr=diagnostics) as process:
            while True:
                block = process.stdout.read(65536)
                if not block:
                    break
                digest.update(block)
                byte_count += len(block)
            status = process.wait()
    if status:
        print(log.read_text(encoding="utf-8", errors="replace"))
        raise SystemExit(status)
    result = {"bytes": byte_count, "sha256": digest.hexdigest()}
    (output / "pcm.sha256.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    if arguments.compare:
        reference = json.loads(arguments.compare.read_text(encoding="utf-8"))
        if result != reference:
            raise SystemExit("PCM regression mismatch: " + str(arguments.compare))
        print("PASS: exact PCM stream length and SHA-256 match")


if __name__ == "__main__":
    main()
