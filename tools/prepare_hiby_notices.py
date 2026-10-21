import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import subprocess
import tarfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "7d090f24b990ef54e3f9dc7eb2edba4865605471"
TARGET = "mipsel-rockbox-linux-gnu"
GCC_VERSION = "9.5.0"
GLIBC_FLAGS = "--enable-kernel=3.2 --enable-oldest-abi=2.16 --disable-werror"
RECIPE_FILES = {
    "official/tools/rockboxdev.sh": "5a20d7c7b2100d2b63c5ac6306659a0d9e883fb8b2e48822e002d4af8bc9e323",
    "official/tools/toolchain-patches/binutils-c23.patch": "25ca694d8612ccdb731d0fb4964f77f7ef1c3e4fd9e10fcc468a0feeeb556abd",
    "official/tools/toolchain-patches/glibc-227-make44.patch": "81eed79adf06f03ac519cdc1eb324685b8665604309b5fbffb24084a1a52acd1",
    "official/tools/toolchain-patches/glibc-227-texinfo.patch": "ee4c0c622e289f248f10740079cd365b9aeb4055c68079e37fd213beb2edaaa4",
    "official/tools/toolchain-patches/linux-c23.patch": "822e45c89ef5a2228f2dc9dee5ab4ebcc8b5a6c493b534e85e9f808acda46100",
}
SOURCES = {
    "binutils-2.38.tar.xz": ("https://ftp.gnu.org/gnu/binutils/binutils-2.38.tar.xz", "e316477a914f567eccc34d5d29785b8b0f5a10208d36bbacedcc39048ecfe024"),
    "gcc-9.5.0.tar.xz": ("https://ftp.gnu.org/gnu/gcc/gcc-9.5.0/gcc-9.5.0.tar.xz", "27769f64ef1d4cd5e2be8682c0c93f9887983e6cfd1a927ce5a0a2915a95cf8f"),
    "linux-3.10.108.tar.gz": ("https://www.kernel.org/pub/linux/kernel/v3.x/linux-3.10.108.tar.gz", "aff93454b2df33a0394253c8977c6d36c7205a423af6d8d4e3e1d67dfc9e07f8"),
    "glibc-2.27.tar.xz": ("https://ftp.gnu.org/gnu/glibc/glibc-2.27.tar.xz", "5172de54318ec0b7f2735e5a91d908afe1c9ca291fec16b5374d9faadfc1fc72"),
    "alsa-lib-1.0.26.tar.bz2": ("https://www.alsa-project.org/files/pub/lib/alsa-lib-1.0.26.tar.bz2", "8c9f8161603cc3db640619650401292c3e110da63429ab6938aac763319f6e7d"),
    "libffi-3.2.1.tar.gz": ("https://sourceware.org/pub/libffi/libffi-3.2.1.tar.gz", "d06ebb8e1d9a22d19e38d63fdb83954253f39bedc5d46232a05645685722ca37"),
    "zlib-1.2.13.tar.gz": ("https://www.zlib.net/fossils/zlib-1.2.13.tar.gz", "b3a24de97a8fdbc835b9833169501030b8977031bcb54b3b3ac13740f846ab30"),
    "glib-2.46.2.tar.xz": ("https://download.gnome.org/sources/glib/2.46/glib-2.46.2.tar.xz", "5031722e37036719c1a09163cc6cf7c326e4c4f1f1e074b433c156862bd733db"),
    "expat-2.1.0.tar.gz": ("https://src.fedoraproject.org/repo/pkgs/expat/expat-2.1.0.tar.gz/dd7dab7a5fea97d2a6a43f511449b7cd/expat-2.1.0.tar.gz", "823705472f816df21c8f6aa026dd162b280806838bb55b3432b0fb1fcca7eb86"),
    "dbus-1.10.2.tar.gz": ("https://dbus.freedesktop.org/releases/dbus/dbus-1.10.2.tar.gz", "aef3f49595df09b0824433ee993cda748ede93693a719a831562ae1616b6bb9e"),
}
ALSA_COPYING = "alsa-lib-1.0.26/COPYING"
ALSA_COPYING_SHA256 = "a190dc9c8043755d90f8b0a75fa66b9e42d4af4c980bf5ddc633f0124db3cee7"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 200000
MAX_EXPANDED_BYTES = 4 * 1024 * 1024 * 1024
MAX_NOTICE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_NOTICE_BYTES = 8 * 1024 * 1024


def checked_path(path):
    path = Path(path).absolute()
    for component in (path, *path.parents):
        if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
            raise ValueError(f"Linked path or ancestor is not supported: {component}")
    return path.resolve()


def file_hash(path):
    path = checked_path(path)
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Expected a regular input file: {path}")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def overlaps(first, second):
    return first == second or first in second.parents or second in first.parents


def locations(sdk_root, output):
    sdk = checked_path(sdk_root)
    output = checked_path(output)
    if not sdk.is_dir():
        raise ValueError("SDK root must be an existing directory")
    protected = [ROOT, *(sdk / name for name in ("downloads", "official", "prefix"))]
    if output == sdk or output in sdk.parents or any(overlaps(output, checked_path(path)) for path in protected):
        raise ValueError("Notice output overlaps source or SDK inputs")
    return sdk, output


def input_hashes(sdk):
    inputs = {}
    for name, expected in {**RECIPE_FILES, **{"downloads/" + name: record[1] for name, record in SOURCES.items()}}.items():
        path = checked_path(sdk / name)
        if name.startswith("downloads/") and path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError(f"Source archive exceeds compressed-size limit: {name}")
        actual = file_hash(path)
        if actual != expected:
            raise ValueError(f"Pinned input SHA-256 mismatch: {name}")
        inputs[name] = actual
    inputs[f"prefix/bin/{TARGET}-gcc"] = file_hash(sdk / "prefix/bin" / (TARGET + "-gcc"))
    return inputs


def archive_name(name):
    if (not name or len(name) > 1024 or "\\" in name or ":" in name or
            name.startswith("/") or any(ord(character) < 32 for character in name)):
        raise ValueError(f"Unsafe archive path: {name!r}")
    parts = name.rstrip("/").split("/")
    if any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts):
        raise ValueError(f"Unsafe archive path: {name!r}")
    return PurePosixPath(*parts)


def select_notices(path, root):
    selected = {}
    count = 0
    expanded = 0
    seen = set()
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            count += 1
            expanded += member.size
            if count > MAX_MEMBERS or member.size < 0 or expanded > MAX_EXPANDED_BYTES:
                raise ValueError("Archive exceeds member/expanded-size limit")
            relative = archive_name(member.name)
            if relative.parts[0] != root or member.mode & 0o6000 or not (
                    member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError(f"Unsafe archive entry: {member.name}")
            key = relative.as_posix()
            if key in seen:
                raise ValueError(f"Duplicate archive path: {member.name}")
            seen.add(key)
            if member.issym() or member.islnk():
                target = member.linkname
                if not target or "\\" in target or ":" in target or target.startswith("/") or any(
                        ord(character) < 32 for character in target):
                    raise ValueError(f"Unsafe archive link: {member.name}")
                resolved = posixpath.normpath(str(relative.parent / target) if member.issym() else target)
                if resolved != root and not resolved.startswith(root + "/"):
                    raise ValueError(f"Escaping archive link: {member.name}")
            wanted = len(relative.parts) == 2 and (relative.name.startswith(("COPYING", "LICENSE", "LICENCE"))
                                                  or root.startswith("zlib-") and relative.name == "README")
            if not wanted:
                continue
            if not member.isfile() or member.size == 0 or member.size > MAX_NOTICE_BYTES:
                raise ValueError(f"License must be a bounded nonempty regular file: {member.name}")
            with archive.extractfile(member) as stream:
                content = stream.read(MAX_NOTICE_BYTES + 1)
            if len(content) != member.size:
                raise ValueError(f"Incomplete or oversized license: {member.name}")
            content.decode("utf-8")
            selected[relative.as_posix()] = content
            if sum(map(len, selected.values())) > MAX_TOTAL_NOTICE_BYTES:
                raise ValueError("Selected notices exceed total-size limit")
    if not selected:
        raise ValueError(f"No original root license notices in {path.name}")
    return selected


def inspect_compiler(sdk):
    compiler = checked_path(sdk / "prefix/bin" / (TARGET + "-gcc"))
    outputs = {}
    for option in ("-dumpfullversion", "-dumpmachine", "-v"):
        result = subprocess.run([str(compiler), option], check=True, capture_output=True, text=True,
                                encoding="utf-8", errors="strict", timeout=30)
        outputs[option] = (result.stdout + result.stderr).strip()
    if outputs["-dumpfullversion"] != GCC_VERSION or outputs["-dumpmachine"] != TARGET or not outputs["-v"]:
        raise ValueError("Expected actual hosted mipsel-rockbox-linux-gnu GCC 9.5.0 configuration")
    return {"path": str(compiler), "sha256": file_hash(compiler), "version": GCC_VERSION,
            "target": TARGET, "configuration": outputs["-v"]}


def collect(sdk):
    payloads = {}
    records = {}
    for name, (url, expected) in SOURCES.items():
        root = re.sub(r"\.tar\.(?:xz|gz|bz2)$", "", name)
        notices = select_notices(checked_path(sdk / "downloads" / name), root)
        payloads.update(notices)
        if sum(map(len, payloads.values())) > MAX_TOTAL_NOTICE_BYTES:
            raise ValueError("Selected notices exceed total-size limit")
        records[name] = {"archive_sha256": expected,
                         "original_files": {relative: hashlib.sha256(content).hexdigest() for relative, content in notices.items()},
                         "source_provenance": {"file": name, "url": url, "sha256": expected,
                                               "size": (sdk / "downloads" / name).stat().st_size,
                                               "verification": "pinned-sha256; signatures not checked by this generator"}}
    if hashlib.sha256(payloads.get(ALSA_COPYING, b"")).hexdigest() != ALSA_COPYING_SHA256:
        raise ValueError("Original ALSA COPYING SHA-256 mismatch")
    compiler = inspect_compiler(sdk)
    metadata = {"recipe": {"upstream_commit": UPSTREAM_COMMIT, "files": RECIPE_FILES},
                "sources": records, "compiler": compiler, "compiler_configuration": compiler["configuration"],
                "glibc_configure_flags": GLIBC_FLAGS,
                "glibc_configuration_evidence": "Options in the pinned recipe; installed libc configuration not independently measured",
                "scope": "Offline original notices from pinned source archives and actual compiler inspection; not proof the installed SDK was built from these sources, runtime acceptance or signature verification"}
    payloads["provenance.json"] = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8")
    text = "\n".join(content.decode("utf-8") for name, content in payloads.items() if name != "provenance.json")
    for required in ("GNU GENERAL PUBLIC LICENSE", "GNU LESSER GENERAL PUBLIC LICENSE",
                     "GCC RUNTIME LIBRARY EXCEPTION", "Version 3.1"):
        if required not in text:
            raise ValueError(f"Required original license text is missing: {required}")
    return payloads


def verify_notices(directory, expected=None):
    directory = checked_path(directory)
    files = {}
    for path in directory.rglob("*"):
        path = checked_path(path)
        if path.is_dir():
            continue
        relative = path.relative_to(directory).as_posix()
        archive_name(relative)
        if path.stat().st_size > MAX_NOTICE_BYTES * 2:
            raise ValueError("Notice payload exceeds verification-size limit")
        files[relative] = file_hash(path)
    manifest = directory / "SHA256SUMS"
    sums = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match[2] in sums:
            raise ValueError("Invalid or duplicate SHA256SUMS entry")
        archive_name(match[2])
        sums[match[2]] = match[1]
    if not sums or sums != {name: value for name, value in files.items() if name != "SHA256SUMS"}:
        raise ValueError("Notice SHA256SUMS mismatch or unlisted payload")
    if expected is not None and sums != {name: hashlib.sha256(content).hexdigest() for name, content in expected.items()}:
        raise ValueError("Notices differ from current pinned source/compiler provenance")
    metadata = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if metadata["recipe"] != {"upstream_commit": UPSTREAM_COMMIT, "files": RECIPE_FILES} or set(metadata["sources"]) != set(SOURCES):
        raise ValueError("Notice recipe/source schema mismatch")
    originals = {}
    for name, (url, checksum) in SOURCES.items():
        record = metadata["sources"][name]
        if (record["archive_sha256"] != checksum or record["source_provenance"]["sha256"] != checksum or
                record["source_provenance"]["url"] != url or not record["original_files"]):
            raise ValueError("Notice source provenance mismatch")
        originals.update(record["original_files"])
    if originals != {name: value for name, value in sums.items() if name != "provenance.json"} or originals.get(ALSA_COPYING) != ALSA_COPYING_SHA256:
        raise ValueError("Original notice hashes/schema mismatch")
    return {"output": str(directory), "notice_files": len(originals),
            "manifest_sha256": file_hash(manifest), "provenance_sha256": files["provenance.json"]}


def write_payloads(directory, payloads):
    for name, content in sorted(payloads.items()):
        path = checked_path(directory / name)
        path.parent.mkdir(parents=True, exist_ok=True)
        checked_path(path)
        with path.open("xb") as stream:
            stream.write(content)
    sums = "".join(hashlib.sha256(content).hexdigest() + "  " + name + "\n" for name, content in sorted(payloads.items()))
    with (directory / "SHA256SUMS").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(sums)


def prepare(sdk_root, output, check_only=False):
    sdk, output = locations(sdk_root, output)
    if not check_only and output.exists():
        raise ValueError("Notice output already exists; refusing to overwrite it")
    before = input_hashes(sdk)
    payloads = collect(sdk)
    if input_hashes(sdk) != before:
        raise ValueError("SDK inputs changed during notice collection")
    if check_only:
        return verify_notices(output, payloads)
    checked_path(output.parent).mkdir(parents=True, exist_ok=True)
    staging = output.parent / ("." + output.name + ".staging-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        write_payloads(staging, payloads)
        verify_notices(staging, payloads)
        if input_hashes(sdk) != before:
            raise ValueError("SDK inputs changed before notice publication")
        locations(sdk, output)
        output.mkdir()
        write_payloads(output, payloads)
        result = verify_notices(output, payloads)
        if input_hashes(sdk) != before:
            raise ValueError("SDK inputs changed during notice publication; output must not be used")
    except Exception as error:
        raise RuntimeError(f"Notice preparation failed; retained staging for diagnosis: {staging}: {error}") from error
    if checked_path(staging).parent != output.parent or not staging.name.startswith("." + output.name + ".staging-"):
        raise ValueError("Unsafe notice staging cleanup path")
    shutil.rmtree(staging)
    return result


def main():
    parser = argparse.ArgumentParser(description="Prepare original HiBy hosted SDK notices offline from pinned inputs.")
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true", help="Verify existing notices against current SDK inputs without writing")
    arguments = parser.parse_args()
    try:
        result = prepare(arguments.sdk_root, arguments.output, arguments.check_only)
    except (OSError, ValueError, RuntimeError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Notice preparation failed: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
