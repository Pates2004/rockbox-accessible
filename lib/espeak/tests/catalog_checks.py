import hashlib
import json
from pathlib import Path
import shutil


def prepare_catalog_fixture(data_parent, output):
    output = Path(output)
    data = output / "espeak-data"
    voices = data / "voices"
    voices.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in ("phondata", "phonindex", "phontab", "intonations", "en_dict"):
        source = Path(data_parent) / "espeak-data" / name
        shutil.copyfile(source, data / name)
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    for index in range(200):
        (voices / f"r{index:04d}").write_text(
            f"name Catalog {index:03d}\nlanguage en\ngender male\n", encoding="utf-8")
    (voices / "en").write_text("name English\nlanguage en\ngender male\n", encoding="utf-8")
    (output / "fixture.json").write_text(json.dumps({
        "purpose": "r34 dynamic catalog and lifecycle regression; deliberately generated voices",
        "source_data_parent": str(data_parent), "data_sha256": hashes,
        "synthetic_voice_count": 201,
    }, indent=2) + "\n", encoding="utf-8")
    return output
