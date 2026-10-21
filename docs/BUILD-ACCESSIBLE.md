# Building Rockbox Accessible

[Polski](BUILD-ACCESSIBLE-PL.md)

This is development source, not a universal firmware package. Start with an SDL
simulator before installing anything on hardware. Target limitations and known
unfinished work are listed in the [project overview](../README.md).

## 1. Source and exact speech data

Use Git and Python 3.12 or newer. Keep the checkout named `rockbox` to match the
examples; commands are run from its root. Do not substitute distribution eSpeak
data: engine and binary-data versions must agree.

```sh
git clone --branch accessible https://github.com/Pates2004/rockbox-accessible.git rockbox
cd rockbox
python3 -B tools/prepare_espeak_source.py
```

The helper fetches public eSpeak commit
`a14831fd3af6b3df77ef23b854cd05ee05b12851`, applies the included exact-data patch
and validates the supplied engine plus all 283 runtime and 88 dictionary-source
files against the checked-in hashes. It recreates required input line endings
only when their exact final hash matches. The patch also preserves mixed-line-
ending Polish inputs byte for byte. No dictionary is silently recompiled.

Default destination: the **sibling** `espeak-1.44.05-source`. An existing directory
is never overwritten. Use `--destination /absolute/new/path` to prepare another
location, then pass the same `--espeak-source /absolute/new/path` to builders.
For an existing dependency, use `--check-only --destination /absolute/path`.
A failed preparation leaves its directory for diagnosis; it does not delete or
repair a user's checkout. Network access is required for initial acquisition,
not for speech at runtime. The integrated modified engine itself is already in
`lib/espeak/engine`; the sibling supplies original sources and matching data.

### Existing Windows checkout with a license hash mismatch

New checkouts pin the integrated eSpeak license to LF. An older Windows checkout
may retain its previous CRLF bytes even after updating the attributes. Do not
disable the hash check. From that checkout's root in a Linux/WSL shell, this
optional repair changes only line endings and refuses other local modifications:

```sh
python3 -B - <<'PY'
from pathlib import Path
import subprocess
license_path = Path("lib/espeak/License.txt")
canonical = subprocess.check_output(["git", "show", "HEAD:lib/espeak/License.txt"])
current = license_path.read_bytes()
if license_path.is_symlink() or current.replace(b"\r\n", b"\n") != canonical:
    raise SystemExit("Local license changes detected; no file was written")
if current != canonical:
    license_path.write_bytes(canonical)
print("The eSpeak license matches its tracked Git bytes")
PY
```

Then rerun the original validation. This does not reset the checkout or change
speech data, settings, other sources or the license text.

## 2. Build/output locations

Build helpers keep current packages in this checkout's `installfiles` and working
materials outside it. On Windows and WSL they use `D:/work` when D: exists,
otherwise `C:/work`, with `Workspace/<checkout-name>`, `Snapshots/<checkout-name>`
and other categories. On native Linux set an absolute, writable external root:

```sh
export ROCKBOX_WORK_ROOT="$HOME/rockbox-work"
```

Changing the checkout directory name changes its category subfolder. Build
helpers refuse unsafe links/path overlaps and refuse replacing an installed
simulator. Move an existing package deliberately before repackaging; never
overwrite a running simulator or lose settings/bookmarks. Old archival builds
need not be retained indefinitely. Some upstream host tools are still generated
under `tools`; do not mistake these ignored build products for source changes.

## 3. Linux simulator

Install the usual Rockbox host prerequisites: C/C++ compiler, make, Perl, Python,
pkg-config, zip/unzip and SDL2 development files (for Debian/Ubuntu:
`build-essential perl python3 git pkg-config zip unzip libsdl2-dev`). Then, from the root:

```sh
python3 -B tools/build_espeak_simulator.py --platform linux --target hibyr1 --jobs 4
```

Supported target choices: `hibyr1`, `sansaclipplus`, `sansaclipzip`. The resulting
simulator uses an adjacent `simdisk` for its own data. A new package contains
clean test defaults, not the previous user's configuration. See the target
guides for keys and controls.

## 4. Native Windows x64 simulator, built under Linux/WSL

In addition to host prerequisites install MinGW-w64 C/C++. Obtain the official
SDL2 [2.32.10 MinGW development SDK](https://github.com/libsdl-org/SDL/releases/tag/release-2.32.10), retaining its `LICENSE.txt` beside the
`x86_64-w64-mingw32` directory. Pass the absolute SDK directory explicitly:

Archive: `SDL2-devel-2.32.10-mingw.tar.gz`, SHA-256
`83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2`
(official release asset digest, also checked against the local SDK archive).
Verify it with `sha256sum` before extracting it with `tar -xzf`.

```sh
python3 -B tools/build_espeak_simulator.py --platform windows --target hibyr1 \
  --sdl-sdk /absolute/SDL2-2.32.10/x86_64-w64-mingw32 --jobs 4
```

Output: `installfiles/simwindows-hibyr1/rockboxui.exe` and its complete adjacent
runtime. The EXE runs natively on Windows; Python, WSL and a system synthesizer
are not runtime requirements. Do not distribute the EXE alone or mix its modules
with a stock release. See [Windows operation](ESPEAK-WINDOWS.md).

The full `espeak-data` path must fit the legacy engine's 149-byte UTF-8 limit.
Keep test/install paths reasonably short. Unicode characters may occupy more
than one byte. Simulator Bluetooth does not operate the computer's radio.

## 5. Native player builds

The detailed English [native HiBy R1 guide](BUILD-ACCESSIBLE-NATIVE.md) covers
SDK inputs, host preparation, application compilation, independent checks and
the additional provenance/notices contract for complete packaging. Application
compilation has a public recipe; `tools/prepare_hiby_notices.py` prepares the
packaging notices offline from its pinned SDK inputs. It does not build the SDK
or prove that an installed SDK was built from those sources. Do not mistake a
staging command for a proven end-to-end or byte-identical release reproduction.

- Sansa: [Clip+](ESPEAK-CLIPPLUS.md), [Clip Zip](ESPEAK-CLIPZIP.md),
  `python3 -B tools/build_espeak_clipplus.py --help`.
- HiBy R1: [native port](ESPEAK-HIBYR1.md),
  `python3 -B tools/build_espeak_hiby.py --help`. The builder requires explicit
  compatible MIPS toolchain, runtime notices and ALSA source inputs. Its
  `--stage-hardware-test --source-frozen` path creates a candidate for validation,
  not proof of successful full device startup.

Generic distro MIPS output is not automatically compatible with the HiBy vendor
userspace. No added HiBy vendor firmware image, shared library or toolchain binary
is hosted here. The unchanged upstream tree does contain Marvell firmware blobs
under their separate retained license; these are not HiBy installation images.
Installation/recovery is separate from compiling the shared
application. Read [R1 installation](HIBY-R1-INSTALL.md) before a device operation;
do not use a recipe for another player or flash merely to update `.rockbox`.

Every settings/plugin-layout change requires the matching integrated plugin ABI
and rebuilt bundled modules. Never copy old/stock plugins into an integrated
build. Existing historical package versions in guides describe those particular
packages, not acceptance of the current branch.

Known development-label limitation: some Sansa builder version strings still say
r29 although this shared source uses r34. Check the manifest's engine revision,
not that legacy label. This does not update or revalidate the preserved Sansa
releases. HiBy R1 uses its separately versioned current build path.

## 6. Tests and reporting

The dependency helper has small cross-platform tests:

```sh
python3 -B -m unittest discover -s tools/tests -p test_prepare_espeak_source.py -v
python3 -B -m unittest discover -s tools/tests -p test_accessibility_lists.py -v
```

For broader tests read each suite's prerequisites. Some require completed native
and Windows target headers, pinned diagnostic artifacts or Windows itself;
running every GUI/hardware test indiscriminately is not a basic build check.
No physical-device result is implied by a skipped platform test or mocked service.
Include target, exact Git revision, error text and reproduction steps when
reporting a problem. Do not publish credentials or private audio captures.
