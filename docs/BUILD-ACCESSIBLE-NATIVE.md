# Building the native HiBy R1 application

This guide covers the hosted Linux **HiBy R1 application**, compiled on Linux or
inside WSL. It does not build a Windows simulator, a bootloader, a Linux kernel
or a vendor firmware update. Start with [the main build guide](BUILD-ACCESSIBLE.md)
for the public source checkout and exact eSpeak preparation. The source branch
is experimental; its publication does not accept a new binary release.

There are three different outcomes:

| Outcome | Available path | What it establishes |
| --- | --- | --- |
| Compile and inspect the application and bundled modules | `--build-only`, with the exact hosted SDK and prepared eSpeak input | Diagnostic compilation and structural ELF/module checks |
| Produce a candidate ZIP with matching source and notices | `--stage-hardware-test --source-frozen`, with the additional packaging inputs below | Package/source integrity; no native startup or device acceptance |
| Recreate a previously delivered release byte for byte | Not established by this guide | Requires that release's exact inputs, environment, metadata and validation evidence |

**Public notice preparation:** `tools/prepare_hiby_notices.py` now generates the
package builder's notice/provenance input offline from the pinned SDK inputs.
Section 7 gives its explicit setup and verification commands. SDK provisioning
in sections 2–5 remains a separate prerequisite; this is not an end-to-end
clean-clone bootstrap or byte-identical release rebuild claim.

## 1. Host, source and locations

Use Bash, Git, Python 3.12 or newer, GNU Make, a host C/C++ compiler, Perl,
pkg-config, zip/unzip and the usual Unix archive tools. Building the SDK also
requires patch, makeinfo, autoconf, automake, libtool, flex, bison, m4, gawk,
GMP/MPFR/MPC development libraries, and the gettext/gtk-doc dependencies used
when regenerating the old GLib build system.

For Debian/Ubuntu, the relevant package names are:

```text
build-essential git python3 perl pkg-config zip unzip curl ca-certificates
tar xz-utils bzip2 gzip patch texinfo autoconf automake autotools-dev
libtool libtool-bin libltdl-dev flex bison m4 gawk
libgmp-dev libmpfr-dev libmpc-dev gettext autopoint gtk-doc-tools
python3-lxml python3-pygments
```

Check/install these in your chosen Linux build environment before continuing.
This list is not a pinned host image. The existing SDK was built with an
isolated Ubuntu 24.04 host-tool environment; copying its private environment
file is not a portable setup procedure. QEMU is an additional prerequisite for
the optional cross-runtime test in section 6, not for compilation alone.

After completing exact eSpeak preparation in the main guide, open a fresh Bash
session and set the paths below. Replace the first path with your real source
root. Use absolute paths without spaces for this legacy Make/toolchain setup.

```bash
set -e
set -o pipefail
cd /absolute/path/to/rockbox
export ROCKBOX_SRC="$(pwd -P)"
export ESPEAK_SRC="$(dirname "$ROCKBOX_SRC")/espeak-1.44.05-source"
export JOBS=4
export VERSION="r34-native-local-$(date -u +%Y%m%dT%H%M%SZ)"
```

If you prepared eSpeak elsewhere, change `ESPEAK_SRC` to that same location.
Do not repeat preparation into an existing dependency or replace the exact
data with distribution eSpeak, eSpeak NG or regenerated dictionaries.

On **native Linux**, set an absolute writable work root outside the source
checkout, preferably on a Linux filesystem:

```bash
export ROCKBOX_WORK_ROOT=/absolute/external/rockbox-work
```

On **WSL**, the builder selects the Windows work drive itself: D: when that
drive exists, otherwise C:. `ROCKBOX_WORK_ROOT` does not override WSL's drive
selection. Derive the effective project workspace with the same resolver used
by the builders, instead of embedding another person's disk paths:

```bash
export PROJECT_WORKSPACE="$(python3 -B -c 'from pathlib import Path; from tools.project_materials import project_materials_root; print(project_materials_root(Path.cwd()))')"
export SDK_ROOT="$PROJECT_WORKSPACE/toolchains/hibyr1-native"
export TOOLCHAIN_BIN="$SDK_ROOT/prefix/bin"
export BUILD_DIR="$PROJECT_WORKSPACE/build-espeak-hibyr1"
export STAGING_DIR="$BUILD_DIR/release-staging"
```

For an existing compatible SDK, set `SDK_ROOT` to its actual root and recompute
`TOOLCHAIN_BIN`. A different checkout directory name produces a different
project workspace. The application builder has one fixed build directory per
checkout; different version strings do not isolate simultaneous builds.

Current final packages belong in the checkout's `installfiles/hibyr1`, retaining
an existing `Installfiles` spelling if present. Keep it ignored by Git. Build
helpers refuse tracked output directories, links/junctions and overlapping
source/work paths. Some inherited host tools are still generated under `tools`.

Before rebuilding, deliberately classify any previous build or package and
preserve needed settings/evidence. The existing helper moves an occupied build
or release directory into `Snapshots`; it does not decide whether indefinite
retention is useful. Keep only needed comparison/recovery snapshots and retire
ordinary obsolete artifacts according to your workspace policy. Never rebuild
against an SDK being installed or resealed by another process.

## 2. Exact SDK contract

The native builder requires **GCC and G++ 9.5.0**, targeting exactly
`mipsel-rockbox-linux-gnu`. It also requires matching `readelf`, `nm`, `objcopy`
and `ld` executables. A generic distribution `mipsel-linux-gnu` compiler, the
bare-metal `mipsel-elf` toolchain and the ARM Sansa SDK are not interchangeable.

The pinned official hosted recipe uses:

| Component | Version |
| --- | --- |
| binutils | 2.38 |
| GCC, including its C++ front end | 9.5.0 |
| Linux headers | 3.10.108 |
| glibc | 2.27 |
| ALSA library | 1.0.26 |
| libffi / zlib / GLib / Expat / D-Bus | 3.2.1 / 1.2.13 / 2.46.2 / 2.1.0 / 1.10.2 |

Select **`rockboxdev.sh --target=y`**, the hosted MIPS Linux recipe. `--target=i`
builds the bare-metal toolchain. The hosted recipe's glibc options include
`--enable-kernel=3.2 --enable-oldest-abi=2.16 --disable-werror`; these are build
options, not proof that every resulting library imports only GLIBC_2.16.
The existing recipe-built GLib imports newer symbols, including GLIBC_2.19.

The R1 application is ELF32, little endian, MIPS32r2, O32 and hard float, using
`/lib/ld.so.1`. The official runtime loader/libc may use the older MIPS1 ISA.
Do not reject those libraries solely for differing from the application's ISA,
or infer vendor ABI compatibility from the SDK version alone.

## 3. Public recipe inputs for a fresh SDK

Skip this section when consuming an already provisioned compatible SDK. It
describes the pinned upstream invocation and known host requirements, not a
freshly validated universal bootstrap. In particular, WSL build-filesystem
setup and host package versions remain prerequisites.

Use a **new** SDK directory. Keep its original recipe, verified downloads and
logs: they are inputs for diagnosis and corresponding-source packaging. The
five recipe files are intentionally retained separately from the project
checkout so subsequent project edits do not change the pinned SDK recipe.
There is no need for a second complete Rockbox checkout.

The recipe is pinned to official Rockbox commit
`7d090f24b990ef54e3f9dc7eb2edba4865605471`:

```bash
test ! -e "$SDK_ROOT"
mkdir -p "$SDK_ROOT/official/tools/toolchain-patches" "$SDK_ROOT/downloads" "$SDK_ROOT/logs"
export RECIPE_URL=https://raw.githubusercontent.com/Rockbox/rockbox/7d090f24b990ef54e3f9dc7eb2edba4865605471/tools
curl --fail --location "$RECIPE_URL/rockboxdev.sh" --output "$SDK_ROOT/official/tools/rockboxdev.sh"
for patch_name in binutils-c23.patch glibc-227-make44.patch glibc-227-texinfo.patch linux-c23.patch; do
    curl --fail --location "$RECIPE_URL/toolchain-patches/$patch_name" --output "$SDK_ROOT/official/tools/toolchain-patches/$patch_name"
done
(
    cd "$SDK_ROOT"
    sha256sum --check <<'SHA256'
5a20d7c7b2100d2b63c5ac6306659a0d9e883fb8b2e48822e002d4af8bc9e323  official/tools/rockboxdev.sh
25ca694d8612ccdb731d0fb4964f77f7ef1c3e4fd9e10fcc468a0feeeb556abd  official/tools/toolchain-patches/binutils-c23.patch
81eed79adf06f03ac519cdc1eb324685b8665604309b5fbffb24084a1a52acd1  official/tools/toolchain-patches/glibc-227-make44.patch
ee4c0c622e289f248f10740079cd365b9aeb4055c68079e37fd213beb2edaaa4  official/tools/toolchain-patches/glibc-227-texinfo.patch
822e45c89ef5a2228f2dc9dee5ab4ebcc8b5a6c493b534e85e9f808acda46100  official/tools/toolchain-patches/linux-c23.patch
SHA256
)
```

Fetch the ten source archives selected by this pinned recipe. These URLs come
from the existing SDK's recorded provenance; their present availability has
not been rechecked for this documentation change. Do not rerun this download
block over existing files after a partial failure: inspect and verify those
files first, retaining the original failure for diagnosis.

```bash
while read -r archive_name archive_url; do
    test ! -e "$SDK_ROOT/downloads/$archive_name"
    curl --fail --location "$archive_url" --output "$SDK_ROOT/downloads/$archive_name"
done <<'SOURCES'
binutils-2.38.tar.xz https://ftp.gnu.org/gnu/binutils/binutils-2.38.tar.xz
gcc-9.5.0.tar.xz https://ftp.gnu.org/gnu/gcc/gcc-9.5.0/gcc-9.5.0.tar.xz
linux-3.10.108.tar.gz https://www.kernel.org/pub/linux/kernel/v3.x/linux-3.10.108.tar.gz
glibc-2.27.tar.xz https://ftp.gnu.org/gnu/glibc/glibc-2.27.tar.xz
alsa-lib-1.0.26.tar.bz2 https://www.alsa-project.org/files/pub/lib/alsa-lib-1.0.26.tar.bz2
libffi-3.2.1.tar.gz https://sourceware.org/pub/libffi/libffi-3.2.1.tar.gz
zlib-1.2.13.tar.gz https://www.zlib.net/fossils/zlib-1.2.13.tar.gz
glib-2.46.2.tar.xz https://download.gnome.org/sources/glib/2.46/glib-2.46.2.tar.xz
expat-2.1.0.tar.gz https://src.fedoraproject.org/repo/pkgs/expat/expat-2.1.0.tar.gz/dd7dab7a5fea97d2a6a43f511449b7cd/expat-2.1.0.tar.gz
dbus-1.10.2.tar.gz https://dbus.freedesktop.org/releases/dbus/dbus-1.10.2.tar.gz
SOURCES
```

Keep exact filenames and verify all ten archives **before** running the recipe:

```bash
(
    cd "$SDK_ROOT/downloads"
    sha256sum --check <<'SHA256'
e316477a914f567eccc34d5d29785b8b0f5a10208d36bbacedcc39048ecfe024  binutils-2.38.tar.xz
27769f64ef1d4cd5e2be8682c0c93f9887983e6cfd1a927ce5a0a2915a95cf8f  gcc-9.5.0.tar.xz
aff93454b2df33a0394253c8977c6d36c7205a423af6d8d4e3e1d67dfc9e07f8  linux-3.10.108.tar.gz
5172de54318ec0b7f2735e5a91d908afe1c9ca291fec16b5374d9faadfc1fc72  glibc-2.27.tar.xz
8c9f8161603cc3db640619650401292c3e110da63429ab6938aac763319f6e7d  alsa-lib-1.0.26.tar.bz2
d06ebb8e1d9a22d19e38d63fdb83954253f39bedc5d46232a05645685722ca37  libffi-3.2.1.tar.gz
b3a24de97a8fdbc835b9833169501030b8977031bcb54b3b3ac13740f846ab30  zlib-1.2.13.tar.gz
5031722e37036719c1a09163cc6cf7c326e4c4f1f1e074b433c156862bd733db  glib-2.46.2.tar.xz
823705472f816df21c8f6aa026dd162b280806838bb55b3432b0fb1fcca7eb86  expat-2.1.0.tar.gz
aef3f49595df09b0824433ee993cda748ede93693a719a831562ae1616b6bb9e  dbus-1.10.2.tar.gz
SHA256
)
```

These are the source hashes recorded for the existing SDK. A successful hash
check establishes matching bytes; it does not create a signature-verification
record. Preserve actual source URLs and any real signature/checksum verification
results for your own SDK. Do not copy another build's signature log or compiler
configuration as evidence of your build.

Choose a source-build directory on a filesystem supporting Linux symlinks,
hardlinks and source filename semantics. On native Linux that can be
`$SDK_ROOT/build`. With WSL, a Windows-mounted download/prefix directory does
not establish that its source-build directory has those semantics: the existing
SDK needed a Linux ext4 build area. Provision such an area first and set
`SDK_BUILD` to its absolute path; this guide does not provide a portable mount
or private-namespace bootstrap. Do not overwrite an existing source-build tree.

```bash
export SDK_BUILD=/absolute/linux-filesystem/hibyr1-toolchain-build
test ! -e "$SDK_BUILD"
```

Two host details from the existing SDK matter:

- The recipe's in-tree `cp -r` resets generated ALSA file timestamps. This caused
  unwanted regeneration with unavailable automake/aclocal 1.11. A private
  timestamp-preserving `cp` wrapper fixed that setup without changing the
  pinned source/recipe or pretending modern Automake is version 1.11.
- GLib needs target-only pkg-config lookup. Point it at the SDK sysroot, clearing
  host `PKG_CONFIG_PATH`; otherwise a successful detection may select host
  libraries. Host GMP/MPFR/MPC include paths must not leak into target builds.

For a normally installed Debian/Ubuntu host, the following wrappers express
those two measured adjustments. Verify the `/usr/bin` tool locations first.
They do not reproduce the separate extracted host overlay used for the existing
SDK, and have not been exercised here as a fresh full SDK build.

```bash
test -x /usr/bin/cp
test -x /usr/bin/pkg-config
mkdir -p "$SDK_ROOT/host/bin"
cat > "$SDK_ROOT/host/bin/cp" <<'SH'
#!/bin/sh
exec /usr/bin/cp --preserve=timestamps "$@"
SH
cat > "$SDK_ROOT/host/bin/mipsel-rockbox-linux-gnu-pkg-config" <<'SH'
#!/bin/sh
set -eu
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PKG_CONFIG_SYSROOT_DIR=$(CDPATH= cd -- "$script_directory/../../prefix/mipsel-rockbox-linux-gnu/sysroot" && pwd)
export PKG_CONFIG_LIBDIR="$PKG_CONFIG_SYSROOT_DIR/usr/lib/pkgconfig:$PKG_CONFIG_SYSROOT_DIR/usr/share/pkgconfig"
unset PKG_CONFIG_PATH
exec /usr/bin/pkg-config "$@"
SH
chmod +x "$SDK_ROOT/host/bin/cp" "$SDK_ROOT/host/bin/mipsel-rockbox-linux-gnu-pkg-config"
```

Once the host, filesystem and verified archives are ready, the pinned upstream
SDK invocation is:

```bash
(
    unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH
    unset GCC_EXEC_PREFIX COMPILER_PATH PKG_CONFIG_PATH MAKEFLAGS MFLAGS MAKEOVERRIDES
    export PATH="$SDK_ROOT/host/bin:$SDK_ROOT/prefix/bin:$PATH"
    export PKG_CONFIG="$SDK_ROOT/host/bin/mipsel-rockbox-linux-gnu-pkg-config"
    export GNU_MIRROR=https://ftp.gnu.org/gnu
    bash "$SDK_ROOT/official/tools/rockboxdev.sh" --target=y \
        --prefix="$SDK_ROOT/prefix" --dlwhere="$SDK_ROOT/downloads" \
        --builddir="$SDK_BUILD" --makeflags="-j$JOBS" \
        2>&1 | tee "$SDK_ROOT/logs/rockboxdev.log"
)
```

The script also passes its own `-j` based on `nproc`; `--makeflags=-j4` alone is
not a dependable four-job cap. Choose the available CPUs in your build
environment before launching it. Do not run this against a shared active SDK.
It removes intermediate source/build directories as part of its own recipe;
use only the dedicated scratch path, keeping verified archives and logs.

Require the whole invocation to exit successfully, including ALSA and the
auxiliary library stages. Inspect stage logs on failure. Do not add an arbitrary
`--restart` against already patched/extracted sources or replace the runtime
with modern distribution libraries to get past a failure. The original
private repair/restart helpers are not public bootstrap commands.

## 4. Check the SDK before compiling

Run these against the SDK you will actually use, after provisioning has stopped:

```bash
for tool in gcc g++ readelf nm objcopy ld; do
    test -x "$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-$tool"
done
"$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-gcc" -dumpfullversion
"$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-g++" -dumpfullversion
"$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-gcc" -dumpmachine
"$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-g++" -dumpmachine
export ROCKBOX_SYSROOT="$("$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-gcc" -print-sysroot)"
test -d "$ROCKBOX_SYSROOT"
"$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-gcc" -print-file-name=libasound.so
"$TOOLCHAIN_BIN/mipsel-rockbox-linux-gnu-gcc" -print-file-name=libgcc.a
```

Both compiler versions must print `9.5.0`, both target strings must print
`mipsel-rockbox-linux-gnu`, and the sysroot must be the installed SDK's actual
sysroot. Library lookups must resolve real SDK files, not just echo their input
names. Version strings alone do not establish a complete or compatible SDK.

Use a clean application-build session: remove inherited host/other-target
`CC`, `CXX`, `CROSS_COMPILE`, include/library overrides and loader injections.
The builder prepends `--toolchain-bin`, removes inherited Make overrides and
checks the exact compiler versions, but does not sanitize every environment
variable a user could export.

```bash
unset CC CXX CROSS_COMPILE CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH
unset GCC_EXEC_PREFIX COMPILER_PATH LD_PRELOAD LD_LIBRARY_PATH
```

## 5. Compile the application without release packaging

This path does **not** require the packaging notice/provenance input:

```bash
cd "$ROCKBOX_SRC"
python3 -B tools/build_espeak_hiby.py --build-only \
    --version "$VERSION" --jobs "$JOBS" \
    --toolchain-bin "$TOOLCHAIN_BIN" --espeak-source "$ESPEAK_SRC"
```

Internally it configures `--target=hibyr1 --type=N --integrated-espeak` with
`--compiler-prefix=mipsel-rockbox-linux-gnu-`, then runs `make zip` with your
version. Configure menu number **301** selects `hibyr1`; the generated target ID
is **124**. These numbers serve different purposes. The build is `APP_TYPE=hibyos`,
with a 16 MiB memory setting and a 15 MiB core audio arena; it does not claim
all physical device RAM for Rockbox. The hosted make rules produce a linked
`rockbox.elf` and copy the application to `rockbox.r1`, not a bare-metal image.

Inspect these outputs in `$BUILD_DIR`:

- `configure.log`, `build-zip.log`, `Makefile`, `autoconf.h`, `rockbox-info.txt`;
- `rockbox.elf`, `rockbox.r1`, `rockbox.map` and the base `rockbox.zip`;
- `elf-verification/` and `diagnostic-build.json`.

The builder checks the configured model/type/memory, integrated speech symbols,
ELF ABI, interpreter and dynamic/version dependencies. It compares the linked
ELF's allocated sections with `rockbox.r1` and verifies freshly built plugin,
codec and overlay contents/headers. A successful diagnostic report explicitly
says `source_frozen=false` and `publishable=false`.

The base `make zip` is an intermediate output. It has not gone through the
integrated release-data/catalog/notices/source packaging step. Do not rename
it into a delivered hardware package. Do not mix its modules with stock or
older integrated builds. These development sources use plugin ABI `0xe006`;
use the actual source/package ABI if it changes again.

## 6. Independent checks and their limits

The package-builder regression suite can exercise synthetic ELF/ZIP metadata
and rejection paths without publishing a package:

```bash
python3 -B -m unittest discover -s tools/tests -p test_espeak_hiby_package.py -v
```

For an additional cross-runtime check, provide an existing Linux-host QEMU
MIPSel executable. This harness compiles bounded test programs with the real
SDK and runs the integrated speech engine against the prepared dictionaries:

```bash
export QEMU_MIPSEL=/absolute/path/to/qemu-mipsel-static
python3 -B tools/tests/test_espeak_hiby_mips.py \
    --toolchain-bin "$TOOLCHAIN_BIN" --data-parent "$ESPEAK_SRC" \
    --qemu "$QEMU_MIPSEL"
```

Its reports are retained under `$PROJECT_WORKSPACE/espeak-hiby-mips`. Keep the
SDK and inputs unchanged for its before/after fingerprints. This test uses
mocked Rockbox files/headers; it does not start the full application, play
through R1 ALSA, load all application modules or test Bluetooth. Its success
therefore cannot supply the full-application `--runtime-evidence` acceptance
required by `--publish`.

Read broader suites' prerequisites first. Some consume real completed native
and Windows headers, Windows-specific runners or a locally pinned historical
binary fixture that a public clone does not contain. Do not create fake headers
or report a skipped platform/device case as passing. Compilation, package
integrity, bounded QEMU execution and physical acceptance are separate results.

## 7. Prepare and verify the additional packaging inputs

The public offline generator requires the ten original source archives and
five recipe files pinned in section 3, plus the installed hosted GCC 9.5.0.
It reads those inputs, selects original root license files and records actual
compiler inspection. It does not download, install or compile anything.

Choose a **new** output directory outside the source checkout and SDK input
trees. Preserve an existing frozen notice tree. The generator refuses existing
output, linked paths/ancestors and source/input overlaps; there is no force or
overwrite mode. With the variables from section 1:

```bash
export TOOLCHAIN_NOTICES="$PROJECT_WORKSPACE/hibyr1-notices-$VERSION"
export ALSA_SOURCE="$SDK_ROOT/downloads/alsa-lib-1.0.26.tar.bz2"
python3 -B tools/prepare_hiby_notices.py \
    --sdk-root "$SDK_ROOT" --output "$TOOLCHAIN_NOTICES"
python3 -B tools/prepare_hiby_notices.py \
    --sdk-root "$SDK_ROOT" --output "$TOOLCHAIN_NOTICES" --check-only
```

`--check-only` verifies an output produced by this generator against the current
pinned archives, recipe and compiler, without writing. It is not a migration
command for a differently structured historical notice tree. Both modes print
the notice count and provenance/manifest hashes on success and exit nonzero on
failure. The SDK must be quiescent throughout both calls.

The expected source-input and generated-output layout is:

```text
SDK_ROOT/
  prefix/bin/mipsel-rockbox-linux-gnu-gcc
  prefix/mipsel-rockbox-linux-gnu/sysroot/
  downloads/alsa-lib-1.0.26.tar.bz2
  official/tools/rockboxdev.sh
  official/tools/toolchain-patches/binutils-c23.patch
  official/tools/toolchain-patches/glibc-227-make44.patch
  official/tools/toolchain-patches/glibc-227-texinfo.patch
  official/tools/toolchain-patches/linux-c23.patch
TOOLCHAIN_NOTICES/
  provenance.json
  SHA256SUMS
  alsa-lib-1.0.26/COPYING
  ...original toolchain source license files...
```

`--alsa-source` must name the **original archive**, not its extracted directory
or a repacked copy. The builder derives `SDK_ROOT` from that file's grandparent,
so the `downloads/<archive>` and `official/tools/...` relationship is mandatory.
The five recipe hashes must match section 3 exactly, even if your project copy
of `tools/rockboxdev.sh` contains later modifications or notice comments.

The contract enforced by `tools/build_espeak_hiby.py` includes:

| Input | Required content |
| --- | --- |
| ALSA source archive | Exact filename `alsa-lib-1.0.26.tar.bz2` and SHA-256 `8c9f8161603cc3db640619650401292c3e110da63429ab6938aac763319f6e7d` |
| ALSA original license | `notices/alsa-lib-1.0.26/COPYING`, SHA-256 `a190dc9c8043755d90f8b0a75fa66b9e42d4af4c980bf5ddc633f0124db3cee7` |
| `provenance.json` → `recipe.files` | Exactly the five `official/tools/...` path/hash entries in section 3 |
| `provenance.json` → `sources["alsa-lib-1.0.26.tar.bz2"]` | Matching `archive_sha256`, `source_provenance.sha256` and `original_files["alsa-lib-1.0.26/COPYING"]` |
| Actual notice files | Nonempty original files including the GPL, LGPL and GCC Runtime Library Exception version 3.1 |

The generator records source URLs, pinned hashes, archive sizes and selected
original notice hashes for all ten archives. It checks the actual compiler's
version and target and records its real `gcc -v` output and executable hash.
The glibc flags are identified as options from the pinned recipe; the tool does
not independently measure how an installed libc was configured or prove the
installed SDK was built from these particular source archives.

Verification is explicitly **pinned SHA-256**, not newly verified upstream
signatures. The tool does not copy private historical signature/smoke logs or
invent successful signature records. Keep any separately obtained genuine
signature evidence separately. `SHA256SUMS` covers every generated payload,
including `provenance.json`; check it independently before packaging:

```bash
(
    cd "$TOOLCHAIN_NOTICES"
    sha256sum --check SHA256SUMS
)
```

This hash check alone neither creates provenance nor proves that it describes
your actual SDK. An arbitrary directory of license text, an empty JSON object
or invented successful signature records is not a substitute.

Archive inspection is bounded by compressed/expanded sizes, member count and
selected notice sizes. Unsafe member paths, escaping links, special files,
setuid/setgid entries and duplicate paths are rejected, including unsafe entries
that are not selected. Only bounded regular license files are written; full
SDK sources are never extracted by this generator. It includes zlib's original
README notice as well as its license. Input hashes are rechecked for drift.

A temporary sibling staging directory holds the selected notices/provenance
for verification before the new output is created exclusively. On success that
temporary staging is removed. If later placement fails, diagnostic staging and
possibly incomplete new output remain with an explicit error; inspect those
paths and the cause before choosing another output. No existing output is
silently repaired or overwritten. The original archives, SDK runtime and any
existing frozen notices remain inputs only.

The generator has a focused regression suite:

```bash
python3 -B -m unittest discover -s tools/tests -p test_prepare_hiby_notices.py -v
```

This makes notice-input generation public without depending on private
collection/sealing utilities or historical smoke-run paths. Keep the builder's
strict source, recipe and notice checks enabled. Fresh SDK provisioning, full
application runtime evidence and physical hardware acceptance remain separate
requirements; this tool does not make those claims.

## 8. Stage and verify a complete candidate, conditionally

With section 7 satisfied, stop all writers to the Rockbox source, prepared
eSpeak input, SDK and notices. `--source-frozen` is your assertion that this has
happened; it does not stop other processes. Review the exact source state and
required licenses before producing a redistributable candidate.

The following command performs a fresh build, so it also replaces the occupied
diagnostic build directory through the preservation behavior described above:

```bash
cd "$ROCKBOX_SRC"
python3 -B tools/build_espeak_hiby.py --stage-hardware-test --source-frozen \
    --version "$VERSION" --jobs "$JOBS" \
    --toolchain-bin "$TOOLCHAIN_BIN" --espeak-source "$ESPEAK_SRC" \
    --toolchain-notices "$TOOLCHAIN_NOTICES" --alsa-source "$ALSA_SOURCE"
```

Expected staging files:

```text
release-staging/
  rockbox-hibyr1-espeak-VERSION-hardware-test.zip
  rockbox-hibyr1-espeak-VERSION-source.tar.gz
  SHA256SUMS
```

Here `VERSION` means your chosen variable's value. The builder adds exact
speech data, generated language catalogs, documentation, a clean Polish test
profile, autostart seed and the actual linked/validated SDK ALSA library.
It intentionally includes the runtime data/notices in both the application
and corresponding-source deliveries for their distinct roles. It includes
the original ALSA archive and five build-recipe files in the source delivery.
Do not import an existing user profile or distribute only `rockbox.r1`.

The build directory also gains `source-freeze.json` and
`package-verification.json`. Check the actual logs/reports and independently
verify the completed pair:

```bash
python3 -B tools/build_espeak_hiby.py \
    --verify "$STAGING_DIR/rockbox-hibyr1-espeak-$VERSION-hardware-test.zip" \
    --source-archive "$STAGING_DIR/rockbox-hibyr1-espeak-$VERSION-source.tar.gz"
(
    cd "$STAGING_DIR"
    sha256sum --check SHA256SUMS
)
```

Verification checks archive paths, manifests, payload/source hashes, module
headers, catalogs, runtime data, notices and corresponding ALSA source/recipe.
It is read-only and does not need to rebuild the application. Retain the ZIP,
matching source archive and checksum file together. It does not establish
successful device startup, speech output or firmware compatibility.

## 9. Local publication and device boundary

After reviewing the verified staging result, the explicit local publication
mode is `--publish-hardware-test --staged "$STAGING_DIR" --source-frozen`,
with the same version and all four explicit input paths used for staging.
It rechecks the build/toolchain/source binding and **moves** the staged set to
the checkout's `installfiles/hibyr1`; it does not upload to GitHub or write a
card. An existing release is preserved before replacement. Publication requires
staging and destination to share a filesystem; choose the native Linux work
root accordingly. Cross-filesystem publication is rejected before replacing
the existing release. Do not bypass it with ad hoc duplicate final packages.

The separate `--publish --runtime-evidence ...` mode requires real, hashed,
build-bound evidence of full native startup, synthesis and module loading,
with the exact application/source inventory. It is not satisfied by compiling,
the bounded engine harness or copying a previous report. No public turnkey
generator for that full-application evidence is promised here.

Building the application uses the open SDK libraries. Physical operation and
some integration checks additionally depend on the device's vendor userspace,
ALSA plugins/services, loader and firmware. No added proprietary HiBy firmware
image, vendor shared library or prebuilt SDK is supplied by this repository.
Do not substitute those into the public source tree or infer redistribution
permission from local availability. The candidate bundles SDK ALSA, not a
replacement vendor operating system or proof of working Bluetooth.

For an already modified R1, a card application update and a firmware flash
are different operations. Read [R1 installation/recovery](HIBY-R1-INSTALL.md)
and [the native port's limitations](ESPEAK-HIBYR1.md) separately before any device
operation. This build guide performs neither. Full physical startup, audio,
touchscreen/keyboard accessibility, Bluetooth, battery and screen-reader
acceptance require their own evidence. Historical Sansa and Windows package
names in other guides still describe those packages, not a new release of
these development sources.
