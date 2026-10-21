"""Validate the exact supplied eSpeak working-tree data before packaging."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


ROOT = Path(__file__).resolve().parent


def read_hashes(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        relative = PurePosixPath(name)
        if (len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
                or relative.is_absolute() or ".." in relative.parts or "\\" in name
                or ":" in name or name != relative.as_posix() or name in result):
            raise ValueError(f"Invalid eSpeak provenance entry: {name}")
        result[name] = digest
    return result


def validate_supplied_data(source):
    source = Path(source).resolve(strict=True)
    sidecar = ROOT / "DATA-PROVENANCE.json"
    provenance = json.loads(sidecar.read_text(encoding="utf-8"))
    manifest = ROOT / "DATA.sha256"
    manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if manifest_hash != provenance["data_manifest_sha256"]:
        raise ValueError("eSpeak data manifest differs from its provenance sidecar")
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != provenance["engine_revision"]:
        raise ValueError(f"Unexpected supplied eSpeak revision: {revision}")
    expected = read_hashes(manifest)
    actual_names = set()
    for directory in ("espeak-data", "dictsource"):
        tree = source / directory
        if tree.is_symlink() or not tree.is_dir():
            raise ValueError(f"Invalid supplied eSpeak data directory: {tree}")
        for path in tree.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError(f"Linked supplied eSpeak data: {path}")
            if path.is_file():
                actual_names.add(path.relative_to(source).as_posix())
    if actual_names != set(expected):
        raise ValueError("Supplied eSpeak runtime/dictsource file inventory changed")
    upstream = ROOT / "UPSTREAM.sha256"
    if hashlib.sha256(upstream.read_bytes()).hexdigest() != provenance["upstream_manifest_sha256"]:
        raise ValueError("eSpeak engine provenance manifest changed")
    for name, digest in {**read_hashes(upstream), **expected}.items():
        path = source / name
        if source not in path.resolve(strict=True).parents:
            raise ValueError(f"Supplied eSpeak path escapes checkout: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Supplied eSpeak working-tree bytes changed: {name}")
    return {
        "engine_revision": revision,
        "data_manifest_sha256": manifest_hash,
        "data_provenance_sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
        "runtime_data": {name.removeprefix("espeak-data/"): digest
                         for name, digest in expected.items() if name.startswith("espeak-data/")},
        "dictsource": {name.removeprefix("dictsource/"): digest
                       for name, digest in expected.items() if name.startswith("dictsource/")},
    }


def validate_packaged_data(provenance, runtime_data, source_inventory=None):
    if provenance.get("runtime_data") != runtime_data:
        raise ValueError("Packaged eSpeak runtime differs from supplied-data provenance")
    entries = {"espeak-data/" + name: digest for name, digest in runtime_data.items()}
    entries.update({"dictsource/" + name: digest
                    for name, digest in provenance.get("dictsource", {}).items()})
    for name, digest in entries.items():
        relative = PurePosixPath(name)
        if (".." in relative.parts or "\\" in name or ":" in name
                or relative.as_posix() != name or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)):
            raise ValueError("Invalid packaged eSpeak data provenance")
    manifest = "".join(digest + "  " + name + "\n" for name, digest in sorted(entries.items()))
    if hashlib.sha256(manifest.encode("utf-8")).hexdigest() != provenance.get("data_manifest_sha256"):
        raise ValueError("Packaged eSpeak data hashes differ from their provenance manifest")
    if source_inventory is not None:
        for directory, expected in (("espeak-data", runtime_data), ("dictsource", provenance.get("dictsource", {}))):
            prefix = "espeak-1.44.05-source/" + directory + "/"
            actual = {name.removeprefix(prefix): digest for name, digest in source_inventory.items()
                      if name.startswith(prefix)}
            if actual != expected:
                raise ValueError(f"Corresponding-source eSpeak {directory} differs from provenance")
        for name, field in (("DATA.sha256", "data_manifest_sha256"),
                            ("DATA-PROVENANCE.json", "data_provenance_sha256")):
            if source_inventory.get("rockbox/lib/espeak/" + name) != provenance.get(field):
                raise ValueError(f"Corresponding-source eSpeak provenance file mismatch: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(validate_supplied_data(arguments.source), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
