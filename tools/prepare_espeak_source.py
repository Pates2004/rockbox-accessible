import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ESPEAK = ROOT / "lib" / "espeak"
SPEC = importlib.util.spec_from_file_location("espeak_data_provenance", ESPEAK / "data_provenance.py")
PROVENANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVENANCE)


def restore_exact_bytes(path, expected):
    original = path.read_bytes()
    if hashlib.sha256(original).hexdigest() == expected:
        return
    normalized = original.replace(b"\r\n", b"\n")
    for candidate in (normalized, normalized.replace(b"\n", b"\r\n")):
        if hashlib.sha256(candidate).hexdigest() == expected:
            path.write_bytes(candidate)
            return
    raise ValueError(f"Pinned eSpeak input differs beyond line endings: {path}")


def prepare(destination, check_only=False):
    destination = Path(destination).absolute()
    for component in (destination, *destination.parents):
        if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
            raise ValueError(f"Linked eSpeak destination is not supported: {component}")
    if check_only:
        return PROVENANCE.validate_supplied_data(destination)
    if destination.exists():
        raise ValueError("Destination already exists; refusing to modify it. Use --check-only to validate it.")
    metadata = json.loads((ESPEAK / "DATA-PROVENANCE.json").read_text(encoding="utf-8"))
    remote = metadata["source_repository"]
    revision = metadata["engine_revision"]
    if remote != "https://github.com/Pates2004/espeak-1.44.05-x64" or not (
            len(revision) == 40 and all(character in "0123456789abcdef" for character in revision)):
        raise ValueError("Invalid pinned eSpeak source provenance")
    subprocess.run(["git", "init", "--", str(destination)], check=True)
    commands = (
        ["config", "core.autocrlf", "false"],
        ["remote", "add", "origin", remote + ".git"],
        ["fetch", "--depth=1", "origin", revision],
        ["checkout", "--detach", revision],
        ["apply", "--check", "--", str(ESPEAK / "supplied-r34-data.patch")],
        ["apply", "--binary", "--", str(ESPEAK / "supplied-r34-data.patch")],
    )
    for arguments in commands:
        subprocess.run(["git", "-C", str(destination), *arguments], check=True)
    expected = {
        **PROVENANCE.read_hashes(ESPEAK / "UPSTREAM.sha256"),
        **PROVENANCE.read_hashes(ESPEAK / "DATA.sha256"),
    }
    for relative, digest in expected.items():
        restore_exact_bytes(destination / relative, digest)
    return PROVENANCE.validate_supplied_data(destination)


def main():
    parser = argparse.ArgumentParser(description="Prepare the exact public eSpeak r34 source/data dependency.")
    parser.add_argument("--destination", type=Path, default=ROOT.parent / "espeak-1.44.05-source")
    parser.add_argument("--check-only", action="store_true")
    arguments = parser.parse_args()
    result = prepare(arguments.destination, arguments.check_only)
    print(json.dumps({"engine_revision": result["engine_revision"],
                      "runtime_files": len(result["runtime_data"]),
                      "dictionary_sources": len(result["dictsource"]),
                      "data_manifest_sha256": result["data_manifest_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
