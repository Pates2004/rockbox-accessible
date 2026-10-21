# Experimental eSpeak firmware for Sansa Clip+

## Release: r29-alpha7-20261011

Native files in `D:\Rockbox\rockbox\installfiles\clipplus`:

- `rockbox-clipplus-espeak-r29-alpha7-20261011.zip`.
- `rockbox-clipplus-espeak-r29-alpha7-20261011-source.tar.gz` and `SHA256SUMS`.

Paired Sansa release: Clip Zip `r29-alpha8-20261011`. Corresponding simulator versions are
listed in `ESPEAK-WINDOWS.md`. The package and corresponding-source manifests
identify this build; previous release reports do not validate it.
Bookmark writes preserve stale temporary files and try bounded free names;
the reader distinguishes local success from a failed recent-bookmark update.
See `ESPEAK-BOOKMARKS.md` for details and limitations.
No hardware test pass is claimed.
Older identifiers, measurements and results below remain historical. Obtain
new sizes, hashes and inventories from the new package's own validation.

Short paths `Workspace/...`, `Forme/...`, `snapshots/...` and `trash/...`
refer respectively to `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` and `D:\work\Trash\rockbox` (under `/mnt/d/work` in WSL).
Current `installfiles/...` belongs in `D:\Rockbox\rockbox\installfiles`.
Sources remain at `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` in WSL), and
the supplied engine/data at `D:\Rockbox\espeak-1.44.05-source`.
Paths such as `simdisk` and `.rockbox` remain relative to the application/device.

## Previous centre-button and accessibility update: r29-alpha4-20261009

Hold the centre Select/Enter button for the text menu, matching music;
Up remains navigation. A shared mixer fix addresses the idle-tail speech
restart race. Useful utility plugins gain focused speech; see
ESPEAK-PLUGINS.md for coverage and limits. This is experimental firmware
requiring hardware trials; physical rapid-settings crackling is not certified
fixed. Paired Sansa release: alpha5. Identifiers and results below
record earlier milestones; current files are described by manifest/SHA256SUMS.

## Previous bookmark update: r29-alpha3-20261009

That earlier firmware added persistent bookmarks and a spoken long-Play text menu;
see `ESPEAK-BOOKMARKS.md`. Paired Clip Zip release: alpha4. Later alpha2
identifiers, sizes and results document the preceding recorder milestone;
consult the included manifest and SHA256SUMS for current files/checksums.
New firmware needs hardware trials. Rapid-settings crackling and physical
recorder validation remain open; this update does not claim either fixed.

## Previous recorder milestone

Native firmware for **Sansa Clip+ only**, not Clip, Clip v2, Clip Zip, a Windows
simulator or a bootloader. The supplied eSpeak 1.44.05 r29 fork runs inside
Rockbox. No external speech service, eSpeak NG or stock prerecorded `.voice`
or `.talk` files are used.

Release identifier: **`r29-alpha2-20261009`**, paired with Clip Zip
**`r29-alpha3-20261009`**. For exact archive validation, check the release's
`manifest.json` and `SHA256SUMS`. The manifest describes archive checks, not
physical recorder validation; physical recorder testing remains pending.

**Experimental, untested on physical hardware, not certified stable.** Package
validation does not establish booting, speech, playback, recording, USB, battery
behavior or accessibility. No hardware or screen-reader test is claimed. Keep a
known-working firmware and recovery route. This build uses ARM GCC 13 rather
than Rockbox's recommended GCC 9.5.0; configure's toolchain warning is significant.

## Historical recorder release files

Historical recorder-milestone filenames; previous releases are archived
under central `snapshots`, while the planned package uses the filenames
at the start of this guide:

- `rockbox-clipplus-espeak-r29-alpha2-20261009.zip`
- `rockbox-clipplus-espeak-r29-alpha2-20261009-source.tar.gz`
- `SHA256SUMS`

Keep the firmware, matching sources and checksums together. New image sizes
and module counts must come from the new manifest/validation, not alpha1.

## Install without flashing

1. Confirm the model is Clip+ and a working **Rockbox bootloader is already
   installed**. This package never installs or updates a bootloader. If Rockbox
   does not already boot, stop and consult the official Clip+ installation
   instructions separately. Do not flash any file from this package.
2. Connect by USB in a mode exposing the storage. Identify **internal storage**,
   not microSD. Back up all device files, the entire existing `.rockbox`, settings,
   recordings and firmware files used for recovery to a separate safe location.
   Show hidden files if necessary. Verify the backup is readable. Read this guide
   on the computer before disconnecting; charge the player and initially remove
   headphones from your ears.
3. Verify the firmware ZIP and source archive against `SHA256SUMS`. These hashes
   detect corruption; they are not digital signatures or publisher authentication.
4. After the backup, move the old `.rockbox` off the player's root. **Do not merge
   installations.** Integrated eSpeak uses plugin ABI `0xe003`; stock and
   simulator plugins/overlays are incompatible. Every bundled module must be
   rebuilt for this firmware.
5. Extract the ZIP's whole `.rockbox` directly to the **root of INTERNAL
   storage**. Required paths include `/.rockbox/rockbox.sansa`,
   `/.rockbox/espeak-data/phondata`, `/.rockbox/langs/polski.vstrings`.
   Do not create `.rockbox/.rockbox`, install on microSD or copy the source
   archive to the player. Safely eject and restart through the existing bootloader.
6. The package starts with clean Polish defaults: menu speech, natural reading
   of file/directory names, eSpeak on, system language, 175 WPM (0% rate display), ducking to
   25%, playback volume -25 dB. It never imports user settings, resume state or files.
   Do not restore an old `config.cfg`, `.voice`, `.talk`, `.rock`, `.ovl` or `.codec`.
   English display and speech catalogs are included; select English using the
   Rockbox language setting. Normal physical controls remain the intended UI.
7. If speech fails, the player hangs or playback misbehaves, stop and restore
   your backup. Do not rely on this build as your only accessible player. These
   plain-text instructions can be read with NVDA on a computer; that is not proof
   of tested player accessibility.

## Revert without flashing

Reconnect over USB using your known-working recovery procedure. If this build
does not expose USB, use the original firmware/bootloader's documented recovery
route; this package does not supply one. Move the experimental `.rockbox` off
the player, restore the **whole known-working `.rockbox` backup** to the internal
storage root, safely eject and restart. Do not flash `rockbox.sansa`, replace a
bootloader or mix module versions. The packager never accesses your player or
cleans device data/backups.

## Recorder speech: source and hardware status

On the paired Clip Zip's historical alpha2, the user confirmed physical boot,
speech and TXT reading alongside music, but the recorder opened silently.
The simulator-only recorder TTS guard and the mixer's recording exclusion
were confirmed source limitations in our integration. That report does not
validate Clip+ or either new release. Occasional crackling during rapid
settings changes remains unresolved; its cause and any fix are unconfirmed.

The recorder source now includes native-capability speech callbacks for the
initial row, navigation, levels, filename, time/size and state changes, plus
quiescing voice and playback DMA before recording initialization, closure and
option/clock changes. Voice PCM follows the current mixer rate and updates its
DSP, avoiding a stale tail rate after Stop that could speed up the first recorder
words. The AS3525v2 backend switches output DMA away from input-monitor
loopback while voice plays. Recording stays active; speech temporarily replaces
the live headphone monitor. The monitor returns after the speech tail and
roughly three idle mixer frames (a few milliseconds, not measured on hardware).
Capture is not paused to speak. Digital mixing of TTS into microphone capture
is not intended, but still needs the WAV check below.

The paired backend uses the narrow **`HAVE_PCM_RECORDING_VOICE`** capability,
restricted to native AS3525v2 recording targets such as Clip+ and Clip Zip.
It does not grant general full-duplex music playback/capture support. The
source path and host tests do not establish physical recorder behavior.
Host regression coverage includes capability guards, spoken rows/states,
transition ordering and C runtime rate cases from 16 to 96 kHz, with
AddressSanitizer and UndefinedBehaviorSanitizer checks. Host coverage does not
validate physical DMA timing or microphone capture; consult the release's
manifest and validation evidence for actual artifact results.
Native recorder speech, monitor restoration and the saved input on
**Clip+ alpha2** and **Clip Zip alpha3** still require physical tests.
SDL recording remains unavailable.

## Staged first-device test

This is a proposed manual checklist, **not a report of physical-device tests**.
Use low volume and expendable test files. Complete one stage before proceeding;
if speech fails, the player hangs or audio breaks up, stop and use the backup
and reversion procedure above rather than continuing into recording.

1. Boot, navigate a few menus, then browse a short list of directories/files.
   Check menu speech and spoken/spelled names; note the delay to the first speech.
2. Play a short known-good MP3. Trigger a menu announcement and check that music
   ducks during speech and returns afterward, without stuttering or dropouts.
3. Open a short UTF-8 text in the integrated reader. Try text navigation and
   pause/resume; check the spoken position and continuity after resuming.
4. Only after the earlier stages are satisfactory, follow the recorder test
   below. Persistent text bookmarks and a full book-reader plugin remain later
   work; this release does not add them.

For each stage, record the firmware version, action/file, result, startup or
speech-start delay, pause/resume delay, stuttering/dropouts and any other symptoms.
Distinguish observations on your device from successful compilation or host tests.

### Manual recorder test on the player

These keys come from `apps/keymaps/keymap-clip.c` (`CONTEXT_RECSCREEN` and its
standard fallback), not a hardware test. Up/Play and Down/Menu select rows;
Right or Vol+ increases the selected level, Left or Vol- decreases it.
**Left is not Back here; the volume keys adjust the selected level.** Select
starts from idle, then pauses/resumes. Home on release starts a new file while
recording. Short Power stops a recording; short Power when stopped exits.
Hold Down/Menu for recording settings **only when stopped**. Do not hold Power.

1. Use headphones at low volume and a short, noncritical sample. In recording
   settings select microphone, WAV, trigger off and prerecording time zero.
   Enter the recorder; check that the initial Volume row speaks without a key
   press. Navigate up/down through gain, filename, time and size; check each
   label/value. Optional AGC/channel rows depend on settings.
2. On Volume and microphone gain, change one small step and reverse it using
   Right/Left or Vol+/Vol-. Confirm both the spoken value and audible level
   effect, without clipping; these controls have different purposes.
3. Press Select to start. Check the recording announcement and filename; speak
   a recognizable input sample while navigating time/size and provoking TTS.
   Verify that time/size progress, capture stays active during TTS and live
   monitoring returns after each phrase; note any delayed or missing return.
4. Press Select to pause, then Select to resume. Check both announcements,
   time/size behavior and the resumed input; note delays, gaps or lost speech.
5. While recording, press/release Home and check the new filename. Press short
   Power to stop; verify stopped feedback and completion of both WAV files.
6. While stopped, hold Down/Menu to open settings; return with short Power.
   Check recorder speech/initial row again and that levels remain correct.
7. Exit with short Power while stopped. Replay every test WAV, retaining it
   for review: it should contain the microphone input, without digitally mixed
   TTS or unexplained input gaps. Keep headphones away from the microphone;
   acoustic pickup is still possible and no acoustic-feedback immunity is promised.
8. Play the known-good MP3 again, then trigger menu speech and TXT reading.
   Check playback, volume, ducking recovery and restored output/monitor routing.
   Record the exact version, language, actions and failures; test PL and EN.

## Contents and validation

One final firmware ZIP lives in `installfiles/clipplus`. It contains normal
`make zip` files, exact supplied `espeak-data`, all freshly generated
`apps/lang/*.vstrings`, clean settings, and `.rockbox/espeak-clipplus/` with
PL/EN guides, license texts, credits, provenance and `manifest.json`. Stock
`.voice` and `.talk` recordings, including `langs/InvalidVoice_english.talk`,
are omitted from the base `make zip` archive when creating the TTS-only firmware
package. The manifest records omitted files; the final ZIP validator still
rejects any `.voice` or `.talk` file, even if listed in its manifest. Speech
catalogs are text for live synthesis, not recordings. Retained upstream MBROLA
resources do not imply MBROLA support.

The manifest records version, toolchain, source inventory hash, ELF hash,
Clip+ `cli+`/66 header/checksum, payload hash, ABI, runtime/catalog inventories,
and hashes of every other ZIP file. The ZIP hash in `SHA256SUMS` also covers the
manifest itself. Validation checks ARM ELF architecture and defined
`rb_espeak_synth_tracked`, `rb_espeak_synth_character`, `espeak_Synth`,
`tts_speak`, `reclist_speak` and `audio_set_pcm_output`, compares firmware
payload with `rockbox.bin` and an
independent ELF reconstruction, checks all plugin/overlay/codec headers,
PL/EN catalogs, required assets and per-entry hashes. This is **structural
validation, not execution on a player**.

The last two required ELF symbols reject a native build missing recorder TTS
or its PCM output-routing backend; engine symbols alone are insufficient.

Both paired targets use compact ARM/Thumb builds and native eSpeak `-Os`
(the simulator keeps `-O2`), with all bundled plugins, overlays and codecs
rebuilt for ABI `0xe003`. The builder and verifier enforce a **1 MiB
(1,048,576-byte) raw-image bound on both targets**: `rockbox.bin` and the
`rockbox.sansa` payload excluding its 8-byte header, regardless of ZIP size.
Record the new measured size, ARM/Thumb mode and module inventories in the
new manifest/validation; no old build metrics certify this release.

The native linker uses `--gc-sections`: it may legitimately remove the unused
plain `rb_espeak_synth` wrapper. Validation requires the tracked/character
entrypoints actually called by the core, not that unused wrapper.
Image-decoder `.ovl` files use IMGDEC API 1 and a separate embedded plugin ABI
field; that field must still be `0xe003`. Ordinary plugin overlays use the
normal plugin header. Both forms are checked, without accepting stock ABI modules.

The separate `*-source.tar.gz` is corresponding-source delivery, not another
firmware copy. It includes actual working-tree Rockbox files (tracked and
nonignored untracked, including native integration), supplied eSpeak sources
and data, build scripts and a per-file manifest. `.git`, Git credentials,
internal audits, toolchains, builds, installations and snapshots are excluded.
The inventory, not just a Git commit, identifies local changes. Copies of source
and runtime data have distinct rebuild/runtime purposes. No duplicate final ZIP
or unpacked final release is retained on the host.

Rockbox's license inventory/GPLv2 text, eSpeak's GPLv3, Sonic's Apache-2.0 and
provenance accompany the binary; per-file notices remain in source. Their
inclusion is not certification of a complete third-party license review. Review
redistribution obligations before publication.

### Native libc provenance and bounded review

The replacement `firmware/libc/strtol.c`, `firmware/libc/strtoul.c` and
`tools/tests/test_libc_strto.c` were independently authored for this integration
from integer-conversion semantics, not copied from a third-party libc or made
by relabeling the old dietlibc license. Their original APIs/behavior were
inspected; this is not a legally certified clean-room claim. These **new
implementations and their focused test are designated GPL-2.0-or-later**,
permitting GPLv3 selection for the combination. This grant does not relicense
the superseded code or other contributors' work. This paragraph travels with
both firmware and source, without shipping the internal audit. The new Clip+
packaging script, focused packaging tests and these guides are also provided
under GPL-2.0-or-later; existing per-file grants remain unchanged.

Native linking uses Ubuntu newlib `libm.a` and GCC `libgcc.a`, not a full hosted
libc/libstdc++ runtime. For the inspected linked math members, the release
supplies the newlib notice collection and the additional complete Arm Ltd
BSD-3-Clause notices for `math_err.c` (2018) and `math_config.h` (2017-2018).
The latter are in `newlib-Arm-BSD-3-Clause.txt`, reproduced from the verified
official newlib 4.4.0.20231231 source archive; its URL and archive/source hashes
are recorded there. The Ubuntu newlib notice collection alone omits these Arm
notices. The canonical project file is `docs/NEWLIB-ARM-NOTICES.txt`, outside
the generated runtime-notice directory to avoid a source-packaging collision.
These BSD math notices do not themselves require bundling the entire newlib
or toolchain source tree.

GCC 13 notices with the **GCC Runtime Library Exception 3.1**, the separate ARM
compiler packaging notice, and LGPL-2.1 are also supplied. The ARM packaging
notice alone does not license GCC runtime code; the bounded review found no
additional libgcc source-bundling requirement for this ordinary GCC compilation
route under the supplied exception. GPLv3 is supplied as `eSpeak-LICENSE.txt`.
These runtime notices also appear under `rockbox/docs/native-runtime-licenses/`
in the source archive. The Arm notice's canonical source copy is retained too,
because the delivered packaging script reads it when rebuilding; the generated
copy groups the linked-runtime notices. The manifest records runtime archive
hashes, package/source versions and a link-map hash, not a legal certification.

The bounded review treats the Berkeley advertising clause as rescinded on
22 July 1999, including the UC Regents qsort code; retain its source notice and
the rescission record already shipped in Rockbox's `LICENSES`. It is not an
outstanding incompatibility. The reviewed TLSF grant/linking exception and
generic GPL notices likewise did not establish a new GPLv2-only runtime blocker.

For the linked LGPL components, including `strstr`, `strcasestr` and OMA
metadata, retain their notices and names, supply LGPL-2.1, and deliver the
complete matching application/library sources and build scripts. Together
these provide the practical **LGPL-2.1 section 6(a) relinking route**; the handoff
does not restrict modification/relinking or reverse engineering for that purpose.
No relabeling of those sources is needed for this experiment. Keep the firmware
ZIP, matching source archive and `SHA256SUMS` together: an unrelated upstream
Git revision is not a substitute for the actual corresponding source.

Historical provenance research and broader public-release review of all assets
are not newly established blockers to private experimental use or this bounded
binary/source handoff. The final archives must still actually contain the
matching sources and notices, including Arm's supplement; supplying binaries
to another recipient carries applicable obligations even without public release.
This bounded review is not comprehensive legal certification or hardware acceptance.

The new bridge, native adapter and TTS/build/test integration grant is recorded
in `eSpeak-PROVENANCE.md` (source: `lib/espeak/README.md`); it does not replace
the imported components' original license notices.

## Build and verify this release

Prerequisites: Linux/WSL, Python 3.9+, Git, GNU make, Bash, Perl, zip/unzip, host C
tools and `arm-none-eabi-gcc`/`arm-none-eabi-g++` **13.x** with matching binutils
in PATH. Toolchain installation/native compatibility fixes are separate work.
The checked environment is Ubuntu 24.04 with `gcc-arm-none-eabi`,
`libnewlib-dev`, `libnewlib-arm-none-eabi`, `gcc-13-base` and `base-files` license
texts. Keep the corresponding Ubuntu source packages/versions identified in
the manifest available for toolchain reproduction. The script reads
`/usr/share/doc/libnewlib-dev/copyright`,
`/usr/share/doc/gcc-arm-none-eabi/copyright`,
`/usr/share/doc/gcc-13-base/copyright` and
`/usr/share/common-licenses/LGPL-2.1`; absent notices stop packaging rather than
silently dropping required text. Other distributions require checking their
actual runtime packages/notices, not substituting arbitrary copyright files.
The exact data directory was checked at
`D:/Rockbox/espeak-1.44.05-source/espeak-data`; under WSL it is
`/mnt/d/Rockbox/espeak-1.44.05-source/espeak-data`. The engine revision is
`2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f`.

Use the release identifier below and keep sources unchanged throughout
building and packaging:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipplus \
  --source-frozen --version r29-alpha7-20261011 \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source --jobs 4
```

The script uses `--target=sansaclipplus --type=n --integrated-espeak
--thumb --compiler-prefix=arm-none-eabi-`, the automatic C++ wrapper, a fresh
`Workspace/build-espeak-clipplus`, and `make zip`. All modules rebuild. Source
changes during build/packaging abort publication. Older builds/releases move,
never overwrite, into unique `snapshots` after contained-path, content/hash and
process/open-file checks. An in-use artifact or unavailable required check
stops the operation. Process checks cover the current Linux user and, under
WSL, visible Windows processes and exclusive file opens. These checks cannot
exclude use by other host users.

Logs, frozen hashes, ELF/symbol evidence and `validation.json` remain in the
central build directory. `elf-payload-validation.bin` deliberately retains a
diagnostic reconstruction for independent comparison, not a user release.
The normal `make zip` ZIP is retained as diagnostic build input, not another
installed release. Simulator files are untouched. Failed staging is not a
published release. Final read-only verification in WSL (after packaging):

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipplus --verify \
  /mnt/d/Rockbox/rockbox/installfiles/clipplus/rockbox-clipplus-espeak-r29-alpha7-20261011.zip
```

Windows PowerShell:

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
python -B tools/build_espeak_clipplus.py --target=sansaclipplus --verify 'D:\Rockbox\rockbox\installfiles\clipplus\rockbox-clipplus-espeak-r29-alpha7-20261011.zip'
```

To rebuild delivered source without Git metadata, extract the archive's sibling
`rockbox` and `espeak-1.44.05-source` directories into
`/mnt/d/work/Workspace/rockbox/source-rebuild-clipplus-r29-alpha7-20261011`.
The original engine checkout at `D:\Rockbox\espeak-1.44.05-source` stays in place.
Set the version from `source-manifest.json`; this example is for the upcoming
release. The build directory must be new; preserve prior builds in central `snapshots`:

```sh
set -eu
cd /mnt/d/work/Workspace/rockbox/source-rebuild-clipplus-r29-alpha7-20261011/rockbox
source_dir="$PWD"
export VERSION=r29-alpha7-20261011
build_dir=/mnt/d/work/Workspace/rockbox/build-espeak-clipplus-source-r29-alpha7-20261011
mkdir "$build_dir"
cd "$build_dir"
bash "$source_dir/tools/configure" --target=sansaclipplus --type=n \
  --integrated-espeak --thumb --compiler-prefix=arm-none-eabi-
make -j4 zip
```

Do not override `CXX` in native builds: that bypasses the Thumb wrapper and
can exceed the bootloader's safe image-size limit again.

That raw `rockbox.zip` is **not** a complete eSpeak installation. It still needs
exact sibling `espeak-data`, generated `.vstrings`, defaults and validation.
Run the packager from a Git working checkout for the complete release workflow;
never install the raw manual ZIP as though it included all runtime assets.
