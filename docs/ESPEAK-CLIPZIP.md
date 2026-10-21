# Experimental eSpeak firmware for Sansa Clip Zip

## Release: r29-alpha8-20261011

Native files in `D:\Rockbox\rockbox\installfiles\clipzip`:

- `rockbox-clipzip-espeak-r29-alpha8-20261011.zip`.
- `rockbox-clipzip-espeak-r29-alpha8-20261011-source.tar.gz` and `SHA256SUMS`.

Paired Sansa release: Clip+ `r29-alpha7-20261011`. Corresponding simulator versions are
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

## Previous centre-button and accessibility update: r29-alpha5-20261009

Hold the centre Select/Enter button for the text menu, matching music;
Up remains navigation. A shared mixer fix addresses the idle-tail speech
restart race. Useful utility plugins gain focused speech; see
ESPEAK-PLUGINS.md for coverage and limits. This is experimental firmware
requiring hardware trials; physical rapid-settings crackling is not certified
fixed. Paired Sansa release: alpha4. Identifiers and results below
record earlier milestones; current files are described by manifest/SHA256SUMS.

## Previous bookmark update: r29-alpha4-20261009

That earlier firmware added persistent bookmarks and a spoken long-Play text menu;
see `ESPEAK-BOOKMARKS.md`. Paired Clip+ release: alpha3. Later alpha3
identifiers, sizes and results document the preceding recorder milestone;
consult the included manifest and SHA256SUMS for current files/checksums.
New firmware needs hardware trials. Rapid-settings crackling and physical
recorder validation remain open; this update does not claim either fixed.

## Previous recorder milestone

Native firmware for **Sansa Clip Zip only**, not Clip, Clip v2, Clip+, a Windows
simulator or a bootloader. The supplied eSpeak 1.44.05 r29 fork runs inside
Rockbox; it does not use eSpeak NG, an external speech service or prerecorded
`.voice`/`.talk` files. The identifier for this release is
**`r29-alpha3-20261009`**, paired with Clip+ **`r29-alpha2-20261009`**.
For exact archive validation, check the release's `manifest.json` and
`SHA256SUMS`. The manifest describes archive checks, not physical recorder
validation; physical recorder testing remains pending.

**Experimental, not certified stable; alpha3 hardware testing is pending.**
For the historical alpha2 milestone, the user physically booted the player
and confirmed speech and TXT reading alongside music. The recorder opened
silently; occasional crackling during rapid settings changes remains unresolved.
This is a user report, not an assistant-run or comprehensive hardware test.
It supersedes the old alpha2 "boot not retested" status, but does not validate
alpha3, native recorder speech/capture, USB, battery or screen-reader access.
Archive checks cannot prove these work.
Keep a known-working installation and recovery procedure. The native build
uses ARM GCC 13 rather than Rockbox's recommended GCC 9.5.0; the configure
warning is a real compatibility limitation, not hardware approval.

## Historical alpha1 panic and the continuing image bound

The alpha1 panic's cause was confirmed by analysis of the official 2019
bootloader binary, `9de8993af6-190809`: the reported PC `0x3080f01c` matches
that loader exactly. Its BSS starts at `0x30100000`, leaving **1 MiB** for
raw payload staging from `0x30000000`. The loader's `ata/sd` stack occupies
`0x301114d0..0x30111ed0`. Alpha1's **1,243,156-byte** raw image crossed this
boundary and overwrote the loader's BSS and stack, causing the panic before
the new firmware could start. A 2 MiB staging assumption does not apply to
this bootloader; changing the application's stack does not fix this cause.

The mandatory compatibility ceiling for **both Clip Zip alpha3 and Clip+ alpha2**
is **raw image ≤ 1 MiB (1,048,576 bytes)**.
Build/packaging and archive verification must reject larger images. The limit
applies to `rockbox.bin` and the `rockbox.sansa` payload without its 8-byte header,
not the compressed ZIP size or total RAM. Read the new package's measured size
from `firmware.payload_bytes` in `.rockbox/espeak-clipzip/manifest.json` after
building. The alpha1 size above is historical diagnosis, not an alpha3 metric;
new sizes and module counts require the new manifest/validation.

Both paired native targets use ARM/Thumb compilation and eSpeak's `-Os` size
optimization; the simulator retains `-O2`. The builder sets `--thumb` for both
targets and rebuilds all bundled modules for ABI `0xe003`. No flashing or
bootloader replacement is required. Binary analysis established alpha1's
failure cause; the later user report established alpha2 boot on that player's
hardware. Neither is a physical alpha3 recorder test.

The same 1 MiB image limit applies to the Clip Zip alpha8 / Clip+ alpha7
pair. Its actual image sizes and results require a new build.

## Identify the target first

The checked source definitions deliberately use two different numeric IDs:

| Property | Clip Zip value and source |
| --- | --- |
| Configure target | `sansaclipzip`, `tools/configure` |
| Configure/catalog ID | `target_id=68`; language catalogs and `rockbox-info.txt` |
| Firmware model number | `MODEL_NUMBER=79`, `firmware/export/config/sansaclipzip.h` |
| Firmware container | `rockbox.sansa`, marker `clzp`, checksum seeded with model 79 (`tools/scramble.c`) |
| Plugin/codec target ID | `TARGET_ID=68`, from configure; header/loader contracts in `apps/plugin.h`, `apps/plugin.c`, `lib/rbcodec/codecs/codecs.h` |
| Configured RAM | `memory=8` in `tools/configure`: 8 MiB, not 8 MiB free for speech |
| Native CPU | AS3525v2 / ARM926EJ-S |
| Controls | `SANSA_CLIP_PAD`; Clip Zip button header and `apps/keymaps/keymap-clip.c` |

Do not change 68 to 79 in catalogs or module headers. The firmware checksum is
seeded with 79. This is the upstream distinction, not a packaging typo. The RAM value
is the build configuration, not a physical measurement or proof that speech
and playback fit every workload. Core code, stacks, speech and audio buffers
share that budget. Clip+ uses `cli+`/66: **neither its firmware nor its modules
are interchangeable with Clip Zip**, even though both images are named
`rockbox.sansa` and the players share a keymap.

## Historical recorder release files

Historical recorder-milestone filenames; previous releases are archived
under central `snapshots`, while the planned package uses the filenames
at the start of this guide:

- `rockbox-clipzip-espeak-r29-alpha3-20261009.zip`
- `rockbox-clipzip-espeak-r29-alpha3-20261009-source.tar.gz`
- `SHA256SUMS`

Use the firmware ZIP only with its matching source archive and checksums.
The source archive is for rebuilding and license compliance, not installation
on the player. The expected ZIP documentation directory is
`.rockbox/espeak-clipzip/`: `CZYTAJ.md` (Polish), `README.md` (English),
`manifest.json`, licenses, credits and provenance. These are the packaged copies
of this guide and `docs/ESPEAK-CLIPZIP-PL.md`, not additional firmware releases.
Windows simulator files belong separately in `installfiles/simwindows-clipzip/`.

## Install without flashing

**Alpha8 test, after package validation:** first back up and verify the
existing `.rockbox` and user data. Replace the **entire contents of `.rockbox`**
with the validated alpha8 ZIP's contents, without merging the old installation,
and use a clean configuration.
Preserve music, books, recordings and other user files; keep data from the old
`.rockbox` in the recovery backup. **Do not flash or change the bootloader.**
Then follow the staged tests below; their hardware outcome remains unknown.

1. Confirm the physical player is a **Sansa Clip Zip** and already boots through
   an installed, working **Clip Zip Rockbox bootloader**. This package neither
   installs nor modifies the bootloader. If this prerequisite is not met, stop
   and consult the official Rockbox installation manual for Clip Zip separately.
   Do not flash `rockbox.sansa` or borrow bootloader files/button combinations
   from Clip+ or another model. This guide supplies no bootloader procedure.
2. Charge the player, read this guide on the computer and identify your known
   recovery route before testing. Start at low volume with headphones initially
   out of your ears. Connect USB using a known-working storage mode; identify
   the **internal storage**, not the microSD card.
3. Back up all device files, the entire current `.rockbox`, settings, recordings
   and any firmware/recovery files to a separate safe location. Show hidden
   files if needed and verify the backup is readable and complete. This is an
   intentional recovery copy: retain it after testing. **Keep existing backups
   on the device too**; do not erase, overwrite or reformat them to obtain clean
   defaults. Leave music, books and recordings intact. If there is insufficient
   space, stop and resolve it without deleting unverified user data.
4. Verify both archives against `SHA256SUMS` before extracting. On Linux/WSL run
   `sha256sum -c SHA256SUMS` in the release directory; on Windows compare
   `Get-FileHash -Algorithm SHA256` for each archive with the corresponding
   entry. Hashes detect corruption, not publisher identity or authenticity.
5. Only after the backup, move the active old `.rockbox` off the player's root
   to a separate, clearly labelled recovery location without overwriting an
   existing backup. **Do not merge installations.** Integrated eSpeak uses
   plugin ABI `0xe003`; stock and simulator plugins/overlays are incompatible.
   All bundled plugins, overlays and codecs must be rebuilt for this Clip Zip
   firmware. Do not copy modules from Clip+, even from another eSpeak build.
6. Extract the ZIP's whole `.rockbox` to the **root of internal storage**.
   Required paths include `/.rockbox/rockbox.sansa`,
   `/.rockbox/espeak-data/phondata`, `/.rockbox/langs/polski.vstrings` and
   `/.rockbox/espeak-clipzip/manifest.json`. Do not create `.rockbox/.rockbox`,
   install this package on microSD or put a Windows simulator on the player.
   Safely eject and restart through the existing working bootloader.
7. Start with the package's clean Polish defaults: menu speech, natural reading
   of file/directory names, eSpeak enabled, system speech language, 175 WPM
   (displayed as 0% in percent mode), ducking music to 25%, playback volume
   -25 dB. No previous settings, resume state or user files are imported.
   Do not restore an old `config.cfg`, `.voice`, `.talk`, `.rock`, `.ovl` or
   `.codec` into this test installation. Retain them in the recovery backup.
   PL/EN display and speech catalogs are required; select English in Rockbox's
   language setting when testing English. Physical buttons remain the UI.
8. If speech fails, the player hangs or audio breaks up, stop testing and
   restore the previous installation. Do not depend on this experimental build
   as your only accessible player. Reading this guide with NVDA on a computer
   is not evidence of tested accessibility on the player.

## Revert without flashing

Reconnect over USB through your known-working recovery procedure. If this
firmware cannot expose storage, use the documented recovery route for your
existing Clip Zip firmware/bootloader; this package does not supply one, and
no unverified power-on button combination is prescribed here.

Move the experimental `.rockbox` off the player, preserving any new files you
need. Restore the **whole verified previous `.rockbox`** to the internal storage
root, safely eject and restart. Do not mix old/new modules, flash the image,
replace the bootloader or delete on-device backups. The host packager does not
access the player or clean its data; its host-side archival policy is not a
device-cleanup instruction.

## Physical controls and the text reader

These are source-derived mappings, not a report of button tests on hardware.
`firmware/target/arm/as3525/sansa-clipzip/button-target.h` defines the buttons;
`apps/keymaps/keymap-clip.c` supplies context-dependent actions:

- In ordinary lists, Up/Down moves, Select on release or Right confirms,
  Left or a short Power cancels; Home on release opens the menu.
- On the playback screen, Up/Play on release toggles play/pause, Left/Right
  skips tracks (hold to seek), Vol+/Vol- changes volume and short Power stops.
- With eSpeak available, opening a UTF-8 `.txt` in the file browser invokes the
  integrated reader, not a separate book-reader plugin. The original text
  viewer remains available through Open With.
- In the reader, Select on release or Home on release pauses/resumes;
  Left/Right moves backward/forward by the chosen unit. Up/Down or Vol+/Vol-
  changes that unit: character, word, logical line, paragraph or page.
  **Volume buttons select units here, not volume.** Short Power exits; Left
  navigates text rather than leaving the reader. Do not hold Power to exit it.

The reader implements a playback-linked cursor and buffered pause/resume;
check their actual behavior in the staged test below. Navigation/unit changes
pause continuous reading and speak the selection; Select resumes from there.
Pages count logical lines (20 by default, configurable 1-100), not screen wraps.
Characters are Unicode codepoints, not grapheme clusters. Persistent document
bookmarks and PDF/EPUB/DOCX parsing are not implemented. Invalid UTF-8 must be
reported rather than treated as a supported document.

## Staged device retest

This is a proposed checklist, **not completed hardware validation**. Use low
volume and short, expendable test files, retaining any generated recordings
until reviewed. Finish each stage before proceeding. If speech fails, the
player hangs or sound breaks up, stop and use the recovery procedure instead
of proceeding to recording.

1. **Startup and speech:** boot, navigate menus and a short file/directory list.
   Check focus/selection, spoken menu labels, names and spelling where selected,
   error feedback and the delay before the first speech. Test Polish and
   English UI/speech explicitly; changing a setting alone does not prove its
   audible effect. Record missing or incorrect announcements.
2. **Playback with speech:** play a known-good short MP3. Check play/pause,
   volume and track navigation, then trigger menu speech during playback.
   Music should duck during speech and return afterward without dropouts,
   stuttering or a stuck low level. Note speech-start and recovery delays.
3. **Reader:** open a short UTF-8 `.txt` with Polish/English words and blank
   lines. Try all five navigation units in both directions, pause/resume and
   exiting. Listen for skipped/repeated text and compare the spoken position
   with resumed reading. Try an empty file and an invalid-UTF-8 test file;
   errors must leave navigation/exit responsive. Save important reading for a
   later, validated build; persistent bookmarks are not available.
4. **Recording, only after the preceding stages succeed:** follow the manual
   recorder procedure below. The native header declares microphone/FM capture;
   this does **not** prove working capture or simultaneous recorder speech.
   Stop on an unavailable-recording message or other failure. FM recording
   needs its own later physical test.

For every stage record the exact firmware version, language/settings,
action/file, result, startup/speech latency, pause/resume delay and audio errors.
USB recovery, battery behavior, long sessions and worst-case memory/CPU load
remain separate hardware checks; the four short stages are not certification
of stability or accessibility.

### Recorder speech: source and hardware status

The historical alpha2 silence was a confirmed integration limitation: recorder
TTS was simulator-only and the mixer excluded output during recording.
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
**Clip Zip alpha3** and **Clip+ alpha2** still require physical tests.
SDL recording remains unavailable. Rapid
settings crackling has no confirmed cause or fix; it is not established as RAM
exhaustion or a steady-state playback fault. Persistent bookmarks and a full
book-reader plugin remain later work.

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

## Build and verify this release

The commands below use the target-aware
`tools/build_espeak_clipplus.py`. **Always pass `--target=sansaclipzip`: Clip+
remains the default.** Use a fixed source tree and keep source, scripts,
tests and guides unchanged throughout building and packaging.

Prerequisites: Linux/WSL, Python 3.9+, Git, GNU make, Bash, Perl, zip/unzip,
host C tools, and `arm-none-eabi-gcc`/`arm-none-eabi-g++` **13.x** with matching
binutils in PATH. This is the GCC 13 experimental route, not validation with
the upstream-recommended GCC 9.5.0. The existing packaging environment is
Ubuntu 24.04 with `gcc-arm-none-eabi`, `libnewlib-dev`, `libnewlib-arm-none-eabi`,
`gcc-13-base` and `base-files`. Keep the matching toolchain/package versions
identified in the manifest available for reproduction.

The packager requires `/usr/share/doc/libnewlib-dev/copyright`,
`/usr/share/doc/gcc-arm-none-eabi/copyright`,
`/usr/share/doc/gcc-13-base/copyright`, `/usr/share/common-licenses/LGPL-2.1`
and the project's `docs/NEWLIB-ARM-NOTICES.txt`. Missing notices must stop
packaging; another distribution's arbitrary copyright file is not a substitute.
The supplied engine checkout is `D:/Rockbox/espeak-1.44.05-source`
(`/mnt/d/Rockbox/espeak-1.44.05-source` in WSL), with its exact `espeak-data`
subdirectory and revision `2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f`.

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipzip \
  --source-frozen --version r29-alpha8-20261011 \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source --jobs 4
```

The Clip Zip route uses `--target=sansaclipzip --type=n --integrated-espeak
--thumb --compiler-prefix=arm-none-eabi-`, the automatic C++ wrapper, a fresh
`Workspace/build-espeak-clipzip` and `make zip`. The builder sets configure's
`--thumb`; the ARM/Thumb build must preserve correct ARM/Thumb interworking
and enforce the 1 MiB raw-image limit. It must rebuild all modules,
use the Clip Zip docs/manifest directory and publish only the complete native
release to `installfiles/clipzip`. Source changes during packaging must abort
publication. Clip+ and Windows simulator output directories are separate.

Older Clip Zip builds/releases belong in unique central `snapshots` directories
before replacement, never overwritten. The packager's contained-path,
content/hash and process/open-file checks must succeed first; an in-use artifact
or unavailable required check stops replacement. Under WSL the checks include
visible Windows processes and exclusive file opens, but cannot exclude use by
other host users. This policy preserves prior host releases, not
copies to merge into a clean installation.

Logs, frozen hashes, ELF/symbol evidence and `validation.json` belong in the
central build directory. The raw `make zip` archive and
`elf-payload-validation.bin` are purposeful diagnostic build inputs/results,
not additional final releases. A failed staging directory is not a release.
After packaging, perform read-only verification of the actual archives:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_clipplus.py --target=sansaclipzip --verify \
  /mnt/d/Rockbox/rockbox/installfiles/clipzip/rockbox-clipzip-espeak-r29-alpha8-20261011.zip
```

Windows PowerShell (read-only verification):

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
python -B tools/build_espeak_clipplus.py --target=sansaclipzip --verify 'D:\Rockbox\rockbox\installfiles\clipzip\rockbox-clipzip-espeak-r29-alpha8-20261011.zip'
```

Keep the matching source archive and `SHA256SUMS` alongside the ZIP. Success
here is structural validation, not a test on ARM hardware or in Windows SDL.

### Rebuild the delivered source without Git metadata

Extract the archive's sibling `rockbox` and `espeak-1.44.05-source` directories into
`/mnt/d/work/Workspace/rockbox/source-rebuild-clipzip-r29-alpha8-20261011`.
The original engine checkout at `D:\Rockbox\espeak-1.44.05-source` stays in place.
Use the version recorded in `source-manifest.json`; this example is for the
upcoming release. The build directory must be new; preserve prior builds
in central `snapshots` before replacement.

```sh
set -eu
cd /mnt/d/work/Workspace/rockbox/source-rebuild-clipzip-r29-alpha8-20261011/rockbox
source_dir="$PWD"
export VERSION=r29-alpha8-20261011
build_dir=/mnt/d/work/Workspace/rockbox/build-espeak-clipzip-source-r29-alpha8-20261011
mkdir "$build_dir"
cd "$build_dir"
bash "$source_dir/tools/configure" --target=sansaclipzip --type=n \
  --integrated-espeak --thumb --compiler-prefix=arm-none-eabi-
make -j4 zip
```

Do not override `CXX` in native builds: that bypasses the Thumb wrapper and
can exceed the bootloader's safe image-size limit again.

This raw `rockbox.zip` is **not a complete eSpeak installation**: it still needs
the exact sibling `espeak-data`, generated `.vstrings`, clean defaults, notices
and validation. Use a Git working checkout and the target-aware packager for
the complete release workflow; never install the raw manual ZIP as though it
contained all runtime assets.

## Package contents and required validation

The complete package must combine native `make zip` output, the exact supplied
`espeak-data`, freshly generated `apps/lang/*.vstrings`, clean defaults and
`.rockbox/espeak-clipzip/` documentation/notices/manifest. Speech catalogs are
text for live synthesis, not audio recordings. Remove stock `.voice`/`.talk`
entries, including `langs/InvalidVoice_english.talk`, from the base archive
when packaging; the manifest records omissions and the final validator must
reject any such recording even if it is listed in the manifest. Retained
upstream MBROLA resources do not mean MBROLA is supported.

Release acceptance must check the actual files, not just a successful compiler
exit or this document:

- Native ARM ELF architecture and defined `rb_espeak_synth_tracked`,
  `rb_espeak_synth_character`, `espeak_Synth`, `tts_speak`, `reclist_speak` and
  `audio_set_pcm_output` symbols; the last two reject builds missing recorder
  TTS or its PCM output-routing backend. Engine symbols alone are insufficient. Compare
  the `.sansa` payload with `rockbox.bin` and an independent ELF reconstruction.
  With `--gc-sections`, removal of the unused plain `rb_espeak_synth` wrapper
  is legitimate; it is not the entrypoint required by the core.
- Raw image no larger than **1,048,576 bytes**, regardless of ZIP compression;
  the builder and validator must reject larger images. Record the measured
  size and ARM/Thumb mode in validation evidence. A smaller image removes the
  confirmed loader-memory overlap but does not prove successful boot.
- `clzp` firmware marker/checksum seeded with 79, but plugin/codec headers and
  configure/catalog/`rockbox-info.txt` ID **68**. Check the PL/EN catalogs,
  matching version and target. Do not normalize these different IDs.
- Plugin ABI `0xe003` and codec API 50. Image-decoder `.ovl` uses IMGDEC API 1
  with a separate embedded plugin ABI field that must be `0xe003`; ordinary
  plugin overlays use the regular plugin header. No stock or simulator modules.
- Required runtime data/notices, clean settings, archive paths, file inventory
  and per-file hashes. `manifest.json` records version, toolchain, source
  inventory, ELF/payload/link-map hashes and runtime-library provenance.
  `SHA256SUMS` covers both archives and therefore the firmware manifest itself.
- The matching source archive, its inventory and its relationship to this
  exact firmware; an unrelated upstream commit does not identify local changes.

These checks are **structural, not execution on the player**. Record actual
results separately after building; do not label the proposed tests as passed.

## Corresponding source and licenses

Deliver the ZIP, matching `*-source.tar.gz` and `SHA256SUMS` together. The source
archive must contain the actual working-tree Rockbox files (tracked and
nonignored untracked integration files), supplied eSpeak source/data, build
scripts and `source-manifest.json`. It excludes `.git`, credentials, internal
audits, toolchains, build outputs, installations and snapshots. Runtime data
and corresponding-source copies have distinct execution/rebuild purposes;
retain only one final native ZIP, not an additional unpacked host release.

Preserve Rockbox's license inventory/GPLv2 text, the supplied eSpeak GPLv3 text,
Sonic's Apache-2.0 license, credits, provenance and original per-file notices.
The following obligations and bounded-review findings are inherited from the
existing native Clip+ documentation; they are **not a new comprehensive legal
review of Clip Zip**:

- The replacement `firmware/libc/strtol.c`, `firmware/libc/strtoul.c` and
  `tools/tests/test_libc_strto.c` were independently written from conversion
  semantics, not copied from another libc or merely relabeled from dietlibc.
  Prior APIs/behavior were inspected; this is not a certified clean-room claim.
  These new implementations/test are GPL-2.0-or-later, allowing GPLv3 selection
  for the combination without relicensing superseded code or others' work.
  The new packaging helper, focused tests and these guides use GPL-2.0-or-later;
  existing third-party grants remain unchanged. The new bridge/native adapter
  and TTS/build/test grant is in `eSpeak-PROVENANCE.md`, sourced from
  `lib/espeak/README.md`, not a replacement for imported notices.
- Native linking uses newlib `libm.a` and GCC `libgcc.a`, not the full hosted
  libc/libstdc++ runtime. Preserve `newlib-COPYRIGHT.txt` and the complete Arm
  BSD-3-Clause supplement `newlib-Arm-BSD-3-Clause.txt` for `math_err.c` (2018)
  and `math_config.h` (2017-2018). Ubuntu's newlib notice collection alone omits
  those Arm notices. The supplement's canonical source is
  `docs/NEWLIB-ARM-NOTICES.txt`, with the official newlib 4.4.0.20231231 URL and
  archive/source hashes. These BSD notices alone do not require the whole
  newlib/toolchain source tree.
- Preserve `GCC13-COPYRIGHT-and-RUNTIME-EXCEPTION.txt`, including **GCC Runtime
  Library Exception 3.1**, and the separate `GCC-ARM-PACKAGING-COPYRIGHT.txt`.
  The ARM package notice alone is not the GCC runtime license. The existing
  bounded review found no additional libgcc source-bundling requirement for
  the ordinary GCC compilation route under that exception.
- Supply `LGPL-2.1.txt`, preserve notices/names of linked LGPL components
  (including `strstr`, `strcasestr` and OMA metadata), and deliver the complete
  matching application/library sources and build scripts. These provide the
  **LGPL-2.1 section 6(a) relinking route**; do not restrict modification,
  relinking or reverse engineering for that purpose. No relabeling of these
  sources is needed.
- Retain source notices and the Berkeley advertising-clause rescission record
  (22 July 1999) already in Rockbox's `LICENSES`, including for UC Regents
  qsort. The existing review does not treat that clause as an outstanding
  incompatibility; reviewed TLSF linking/generic GPL notices likewise did not
  establish a new GPLv2-only runtime blocker.

Runtime notices also belong under `rockbox/docs/native-runtime-licenses/` in
the source archive. Keep the canonical Arm supplement too: the delivered build
script reads it, while the generated copy groups linked-runtime notices.
The manifest's package/source versions and archive hashes provide provenance,
not legal certification. Broader asset/provenance review remains distinct from
this bounded handoff. The delivered pair of archives must include all matching
sources and notices; obligations apply when binaries go to another recipient even
without public publication. Review redistribution obligations before release.

## Separate Windows Clip Zip simulator

The Windows Clip Zip simulator belongs in
`installfiles/simwindows-clipzip/`, separate from native `installfiles/clipzip/`
and the existing Clip+ simulator in `installfiles/simwindows/`. Run it only on
the computer from its own writable directory with its own clean settings/data.
Never copy its executable, plugins or simulated `.rockbox` onto a player.
Neither native ZIP validation nor this guide asserts that a Windows package
has been built or tested.

The following keyboard mappings come from
`uisimulator/buttonmap/sansa-clip.c`, including its `SANSA_CLIPZIP` branch
(selected by `uisimulator/buttonmap/SOURCES`), not guessed Clip+ instructions:

| Computer key | Emulated Clip Zip button |
| --- | --- |
| Left / numeric keypad 4 | Left |
| Right / numeric keypad 6 | Right |
| Up / numeric keypad 8 | Up / Play |
| Down / numeric keypad 2 | Down / Menu |
| Space / numeric keypad 5 | Select |
| Insert / numeric keypad multiply (`*`) | Home |
| Page Up / numeric keypad 9 | Vol+ |
| Page Down / numeric keypad 3 | Vol- |
| Escape / numeric keypad 1 | Power |

Numeric keypad keys are not the top-row digits. Space, not Enter, is the
documented Select key; Insert, not the computer's Home key, emulates Home.
Actions depend on context just as on the player: in the reader Space toggles
pause/resume, Left/Right navigates, Up/Down or Page Up/Down selects the unit,
and short Escape exits. Held Escape represents held Power, not an ordinary
Back action. Verify actual keyboard behavior on the delivered Windows build.

SDL drawing does not expose native Windows controls to NVDA; self-voicing is
not proof of NVDA accessibility. In the simulator, recording is unavailable:
recording initialization/commands/status are excluded and recording DMA is
stubbed. A visible recording screen or spoken controls cannot capture a real
microphone; test rejection/feedback there, not successful recording. Native
Clip Zip microphone/FM capability must be tested on physical hardware.
