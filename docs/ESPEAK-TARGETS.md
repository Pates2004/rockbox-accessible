# Integrated eSpeak: target inventory and simulator tests

## Portable Talkbox workflow, 2026-10-20

[Polska wersja](ESPEAK-TARGETS-PL.md)

Talkbox is the interface name for the shared, in-process eSpeak integration.
Future Sansa and iPod Classic work should reuse that core and adapt the target's
input and platform services. A touchscreen or HiBy service is a separate
capability, not a prerequisite for synthesized menus or text reading.
This section documents the new phase; it adds no build or physical-test result.

The closed R1 native alpha12 / Windows alpha15 software acceptance, its source
freeze, reports, packages and checksums remain evidence of that release only.
New source changes
require a new freeze and fresh validation. Preserve the existing Sansa releases;
their r29 engines and plugin ABI do not become current r34 builds through a
documentation update. The dated inventories below retain their original scope.

### Shared architecture and target boundaries

| Layer | Shared responsibility | Target-specific responsibility |
| --- | --- | --- |
| Synthesis | `lib/espeak`, `apps/tts.c`, `apps/talk.c` and `apps/voice_thread.c`: supplied engine, speech policy, cancellation and queued PCM | Bounded memory/stack budget, filesystem roots, threading and audio output integration |
| Lists and interface speech | `apps/gui/list.c`, shared menus, settings and PL/EN catalogs: selected names, positions, boundaries, questions and errors | Physical actions/keymaps and supported display/input capabilities |
| Text and bookmarks | `apps/tts_reader.c` and `apps/bookmark.c`: character/word/line/paragraph/page navigation, playback-linked cursor, pause/resume and typed text bookmarks alongside audio bookmarks | Mapping navigation, select and context actions; storage/error behavior on that target |
| Plugins | Shared `talk_*` APIs, core synclists and explicit plugin announcements | Target build, plugin keymaps, available plugin features and matching ABI |
| Touch accessibility | Reusable gesture, exploration and typing logic when enabled by capability gates | Touch contacts, coordinates, wake/lock behavior and target-specific button assignments |
| Platform services | Common speech/mixer contracts and announcement policy | Native PCM drivers or hosted ALSA; HiBy vendor Bluetooth, Wi-Fi, power and USB interfaces |

Keep the speech engine, reader and bookmark formats in shared code. Do not
duplicate them for each player. Synthesized interface/name speech remains
independent of prerecorded voice-file settings; keep explicit local verbosity
choices and temporary speech suppression effective. Shared lists do not make
private plugin drawing/input loops accessible. See [plugin coverage](ESPEAK-PLUGINS.md)
and [text bookmarks](ESPEAK-BOOKMARKS.md).

The shared preferences are under Settings → General Settings → Accessibility →
Talkbox settings:

- **Announce list item position** (`tts_announce_position`): shared lists append
  the localized item index and total to the selected item's speech. Test grouped
  rows as logical items, empty lists and rapid movement; retain the item name
  when the optional position is disabled. Five modes are available: Everywhere,
  Interface only, Files only, Everywhere except sliders (fresh default), and Off.
  Only numeric-range controls are sliders; ordinary language, variant and On/Off
  choices retain indices by default. Existing saved On/Off values keep their
  meanings. See [list settings](ACCESSIBILITY-LISTS.md).
- **Announce dynamic content changes** (`tts_announce_dynamic`): automatic radio
  updates use the shared `talk_dynamic_enabled()` policy. Keep explicit
  navigation/queries, completion, errors and safety warnings independent of
  this optional feedback. FM/RDS announcements still require the actual target
  capabilities; this preference does not supply a tuner or RDS decoder. This
  separate preference remains On by default.

These preferences belong to `HAVE_ESPEAK`, not `HAVE_TOUCHSCREEN` or `HIBY_R1`.
They are new-phase source behavior requiring fresh tests, not results covered
by the closed alpha12/Windows15 acceptance. The new plugin-visible fields in
`user_settings` and list-role fields require integrated plugin ABI **`0xe006`**.
Preserved Sansa releases remain **`0xe003`**; prior R1 generations used `0xe004`
and `0xe005`. Their accepted packages do not accept the new source layout.
Rebuild every bundled plugin for the chosen target and matching core ABI in
each future native package and simulator release. Reject stock, older-ABI and
other-target modules; never reuse them merely because their filenames match.

### Capability gates and actual support

Check `tools/configure`, the exact target header in `firmware/export/config/`,
generated `autoconf.h`, `apps/SOURCES`, `firmware/SOURCES` and the menu guards.
Source presence and an upstream stable-target label do not establish Talkbox
support. These are the important existing boundaries:

| Gate | Meaning for a port |
| --- | --- |
| `--integrated-espeak` / `HAVE_ESPEAK` | Configure currently permits SDL simulators, native `sansaclipplus`/`sansaclipzip`, and the `hibyos:hibyr1` application; it rejects bootloaders and other device ports, including native `ipod6g`. |
| `HAVE_ESPEAK` without `HAVE_TOUCHSCREEN` | Shared synthesis, lists, reader, bookmarks and plugin speech remain the core path. Physical input still needs the target's action/keymap integration. |
| `HAVE_ESPEAK` with `HAVE_TOUCHSCREEN` | Enables touch accessibility source/menu paths. `accessibility_buttons.c` is currently inside this source gate despite its name; it is not automatically a generic Sansa/iPod input backend. |
| `HAS_BUTTON_HOLD`, `HAVE_SCREEN_CURTAIN` | Hold-switch, software-lock and curtain controls follow their existing guards. Inspect the combined menu conditions rather than exposing R1 controls everywhere. An iPod click wheel is not a touchscreen. |
| `HIBY_R1` with `HAVE_ESPEAK` | Selects the R1 connectivity/Bluetooth application integration. Native vendor backends additionally require the device path rather than `SIMULATOR`; R1 PCM uses its guarded HiBy backend. |
| `CONFIG_TUNER`, `HAVE_RECORDING` and tuner-specific capabilities | Control FM, recording and related announcements. Check the tuner driver for RDS separately; a generic FM flag proves neither RDS nor working microphone/FM capture. |

HiBy R1 Bluetooth/Wi-Fi service protocols and ALSA routing must not be assumed
on Sansa or iPod Classic. Those targets need their own verified platform
capabilities; a shared menu or an external Bluetooth transmitter does not port
the R1 vendor service. A different HiBy-hosted model also needs explicit review.
SDL simulation exercises a host backend, not the native radio, PCM or recording
hardware. Keep platform code behind its guards and unsupported controls absent.

| Target | Recorded state and next gate |
| --- | --- |
| `sansaclipplus`, `sansaclipzip` | Preserved native r29 releases and matching Windows simulators are described in [Clip+](ESPEAK-CLIPPLUS.md), [Clip Zip](ESPEAK-CLIPZIP.md) and [Windows](ESPEAK-WINDOWS.md). They do not validate the new shared preferences, r34 source or ABI `0xe006`; a return to Sansa needs a separately authorized build/test phase. Physical acceptance is not claimed. |
| `ipod6g` | Historical Windows core linking/startup evidence exists below. Native integrated eSpeak remains blocked by configure; there is no current native Talkbox package or new-phase full simulator acceptance established here. |
| `hibyr1` | Closed native alpha12 / Windows alpha15 software results remain valid for their recorded inputs only. Physical R1, touchscreen accessibility, Bluetooth/RF, battery and NVDA acceptance remain open. See [R1](ESPEAK-HIBYR1.md). |
| Other touchscreen or hosted targets | A capability macro permits relevant code selection; it does not transfer R1 acceptance or vendor-service compatibility. Establish a separate target-specific build and test record. |

### Onboarding and build sequence

1. Identify the exact model/revision, Rockbox selector, CPU/ABI, memory budget,
   storage modifications, bootloader and vendor firmware. Use `ipod6g` for the
   identified Classic family, not `ipodvideo`; distinguish Clip+, Clip Zip and
   Clip. Retain the hardware-identification cautions below. Installation and
   firmware operations require a separate, device-specific procedure.
2. Map capabilities and actions before enabling features: list/reader navigation,
   context menus, pause/resume, back/exit, hold/lock and any touch/curtain paths.
   Preserve the Sansa reader convention: short centre Select pauses/resumes,
   holding it opens the context menu, and Up remains navigation. Verify the
   Classic wheel/button mapping rather than copying R1 touch gestures.
3. Record dependencies and runtime-data provenance. Reuse the supplied eSpeak
   1.44.05 r34 working-tree data and its manifests for new r34 work, preserving
   supplied dictionary changes. Keep the original checkout intact. Measure the
   native allocator, stacks, dictionary and concurrent playback buffers; host
   RAM and `MEMORYSIZE` do not justify increasing an arena or prove device fit.
4. Coordinate shared-source workers, finish their edits, review the combined
   change and create a fresh source/data/toolchain freeze before building.
   Record target, feature gates, plugin ABI `0xe006`, versions and hashes.
   Use Linux/WSL with the actual device toolchain for native builds; Windows
   cross-builds use MinGW and the checked SDL2 SDK described below. Do not run
   host suites against target headers while clean-build setup is replacing them.
5. Choose the existing entry point below. A new native target needs reviewed
   build/runtime/packaging support and an intentional configure-gate change;
   deleting a rejection or defining `HAVE_ESPEAK` by hand is not that work.

| Purpose | Existing entry point and limits |
| --- | --- |
| Inventory / selected simulator core | `tools/tests/test_tts_targets.py --list-targets` is read-only. Fresh `--platform windows --targets ipod6g` or selected Sansa runs build diagnostic SDL cores, not device firmware or a complete plugin release. `--build-only` omits runtime assets; omit it when preparing a new startup-smoke report. Full examples remain below. |
| Maintained simulator builder | `tools/build_espeak_simulator.py --platform windows --target ... --build-only` accepts only `sansaclipplus`, `sansaclipzip`, `hibyr1`. `--package-only` packages an existing matching build; packaging is a separate release action, not another test. This builder does not accept `ipod6g`. |
| Native Sansa | `tools/build_espeak_clipplus.py --target sansaclipplus` or `--target sansaclipzip`, with `--source-frozen` and a unique `--version`, builds and packages for that target. It has no `--build-only` staging mode; do not treat it as a harmless core probe against preserved releases. |
| Native R1 | `tools/build_espeak_hiby.py --build-only` produces diagnostics. `--stage-hardware-test` requires `--source-frozen`, a unique `--version`, actual `--toolchain-notices` and `--alsa-source`. Later `--staged ... --publish-hardware-test` is explicitly experimental; `--publish` instead requires build-bound `--runtime-evidence`. Neither mode establishes physical acceptance. |
| Native Classic / other new ports | No supported native integrated recipe is supplied here. First implement and review target enablement, bounded runtime/audio integration, complete plugin/package builds and corresponding-source validation; then run fresh target checks. |

### Test and release gates

1. After configurations are complete and stable, run focused synthesis, voice
   policy, list, reader, bookmark and plugin checks, then the appropriate host
   regression suites using real generated target headers. Existing examples
   include `test_tts_voice_policy.py`, `test_accessibility_lists.py`,
   `test_tts_reader.py`, `test_text_bookmarks.py` and the plugin-policy/list
   tests in `tools/tests/`. Rebuild the full core/codecs/plugins as well:
   `make bin` and linked symbols alone do not validate that package.
2. Exercise PL and EN with clean, isolated settings. Check startup and actual
   request → synthesis → nonzero PCM, interruption/recovery, rapid first/last
   navigation, empty/grouped lists, both new preferences On/Off and persistence.
   Verify optional announcements do not silence names, explicit operations,
   errors or safety warnings. Check reader navigation, cursor/pause/resume,
   text/audio bookmark compatibility and failed writes without disturbing
   concurrent music. Exercise plugin launch/data-error paths and ABI rejection.
3. Check the target-specific input and audio boundary independently. Use physical
   button/wheel mappings for Sansa/Classic; test touch, exploration, typing and
   wake/lock only on applicable targets. Check playback mixing and PCM restart,
   cancellation, radio state/errors and supported FM/RDS/recording behavior.
   SDL recording stubs cannot validate capture. Hosted fixtures or MIPS/QEMU
   probes cannot validate a whole player, vendor radio service or battery life.
4. Bind each report to the fresh inputs, executable/package hashes, actual exit
   status, skipped cases and limits. Perform Windows simulator checks in a
   private fixture without the user's profile, foreground/global input or host
   radio/audio changes. Check keyboard operation and spoken names/states; record
   NVDA testing separately because SDL self-voicing is not a native accessible
   control tree. Report physical listening, touch, RF and energy tests as
   untested until actually performed. Never promote an old FAIL or attach an
   old PASS to changed sources.
5. Before release, verify the complete target package, rebuilt matching plugins,
   exact runtime data, PL/EN catalogs/docs, corresponding source, notices and
   checksums. Use the existing native builders' read-only `--verify` with
   `--source-archive` and the correct `--target` for Sansa; verify the actual
   final Windows package separately, including clean defaults and relocation.
   Keep existing accepted releases until the new candidate passes its gates.
   Deliver one current copy in project-local `installfiles`: existing Sansa
   paths are `clipplus`, `clipzip`, `simwindows`, `simwindows-clipzip`; R1 uses
   `hibyr1`, `simwindows-hibyr1`. A future Classic packager must define its own
   target path. Keep application data beside the program. Useful diagnostics
   belong in central `Workspace`, audit/provenance in `Forme`; retain snapshots
   only for a documented current use and move confirmed obsolete artifacts to
   central `Trash` after path/process/integrity checks. Do not delete old proof
   or make unneeded duplicate releases.

## Earlier inventory and reproduction details

HiBy R1 development now has an explicit hosted eSpeak build path and a separate
Windows simulator target. See `ESPEAK-HIBYR1.md`, `HIBY-R1-CONTROLS.md` and
`HIBY-R1-INSTALL.md`. This addition does not establish physical R1 acceptance,
Bluetooth stability or accessible touch exploration. Older tables below are
historical simulator results, not measurements of the new R1 application.

Update 2026-10-10: the native pair is Clip+ `r29-alpha6-20261010`
and Clip Zip `r29-alpha7-20261010`, with matching simulators documented in
`ESPEAK-WINDOWS.md`. Their separate acceptance is recorded in
`Workspace/speech-backends-r1-20261010/final-release-review.json`.
The measurement tables and reports below retain their historical
versions and dates.

Short paths `Workspace/...`, `Forme/...`, `snapshots/...` and `trash/...`
refer respectively to `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` and `D:\work\Trash\rockbox` (under `/mnt/d/work` in WSL).
Current `installfiles/...` belongs in `D:\Rockbox\rockbox\installfiles`.
Sources remain at `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` in WSL), and
the supplied engine/data at `D:\Rockbox\espeak-1.44.05-source`.
Paths such as `simdisk` and `.rockbox` remain relative to the application/device.

Directory relocation is recorded in
`D:\work\Forme\rockbox\CENTRAL-MATERIALS-2026-10-10.md` and its integrity
receipts. Short artifact paths below use the category mapping above. Old paths
embedded in immutable reports describe the original runs; use the migration
audit to locate the moved evidence, without rewriting reports or treating old
hashes as new test results.

[Polska wersja](ESPEAK-TARGETS-PL.md)

Update 2026-10-09: the tables below document historical simulator validation,
not acceptance of the new recorder/bookmark changes on every target. Current
Sansa firmware is described in `ESPEAK-CLIPPLUS.md` and `ESPEAK-CLIPZIP.md`;
text bookmarks in `ESPEAK-BOOKMARKS.md`. Historical complete builds/reports A/B/C
are now preserved in the linked `snapshots` locations, without modifying their
contents or hashes. Their embedded paths describe the original run. Do not
refresh archived reports in place: create a fresh build with `--targets`.

Research date: 2026-10-04. Source baseline: Rockbox commit
`0ed3734e5e34ea6c47ece2ef2c7c8a0fe0fcf325` plus the local, uncommitted
eSpeak integration. This is an inventory of this checkout, not a promise of
support for every device sold under these names. Windows build/startup results
are recorded below; no device firmware or player writes were performed.

## Exact target matrix

Update, 2026-10-07: the October 4 results below are historical simulator results,
not a current native-build inventory. The experimental Clip+ release now exists;
Clip Zip has a separate native packaging target and Windows release path. See
`ESPEAK-CLIPPLUS.md` and `ESPEAK-CLIPZIP.md` for current device instructions,
source/license delivery and untested-hardware limitations. Neither build is a
physical-device validation. Later native license remediation is described there;
the October 4 libc findings below describe the earlier sources.

`tools/configure` supplies the selector, menu number and `memory` value;
`firmware/export/config/<target>.h` supplies CPU and recording capabilities.
The number before each selector is a **configure menu number**, not a
`MODEL_NUMBER` or voice-catalog target ID.

RAM below is the configured `MEMORYSIZE`, in MiB, not free memory for eSpeak.
For Linux-hosted ports it is a Rockbox memory/buffer budget, **not physical
installed RAM**. Physical RAM on those variants was not established here.
Native values describe Rockbox's memory configuration, not a new measurement.
Recording means the native/hosted Rockbox target defines `HAVE_RECORDING`,
not that vendor firmware records or that recording has been tested with TTS.

| Requested player | Configure number / exact selector | Device execution / architecture | RAM configuration | Rockbox recording | Simulator evidence |
| --- | --- | --- | --- | --- | --- |
| Sansa Clip+ | 62 / `sansaclipplus` | Native; AS3525v2, ARM926EJ-S, little-endian | 8 | Yes: microphone, FM | Existing Windows package and broader PL/EN regression evidence |
| Sansa Clip Zip | 65 / `sansaclipzip` | Native; AS3525v2, ARM926EJ-S, little-endian | 8; configure retains a `not sure` comment | Yes: microphone, FM | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| xDuoo X3 | 241 / `xduoox3` | Native; Ingenic JZ4760B, MIPS32, little-endian | 64 | No | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| xDuoo X3 II | 242 / `xduoox3ii` | Linux/HiBy-hosted; MIPS32r2, little-endian, hard-float build ABI | 8 budget; physical RAM unverified | No | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| xDuoo X20 | 243 / `xduoox20` | Linux/HiBy-hosted; MIPS32r2, little-endian, hard-float build ABI | 8 budget; physical RAM unverified | No | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| Shanling Q1 | 260 / `shanlingq1` | Native; Ingenic X1000, MIPS32r2, little-endian | 64 | No | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| iPod Classic | 29 / `ipod6g` | Native; Samsung S5L8702, ARM926EJ-S, little-endian | 64 | Yes: microphone and line-in capability; requires suitable input/accessory, not a built-in microphone claim | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| FiiO M3K, native port | 246 / `fiiom3k` | Native; Ingenic X1000, MIPS32r2, little-endian | 64 | Yes: microphone; `HAVE_RECORDING_WITHOUT_MONITORING` | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| FiiO M3K, older hosted port | 244 / `fiiom3klinux` | Linux-hosted; MIPS32r2, little-endian, hard-float build ABI | 16 budget; physical RAM unverified | No | Skipped in this Windows run: deprecated hosted port; build registry marks it unusable |
| Aigo Eros Q/K; HiFi Walker H2; Surfans F20, native family | 247 / `erosqnative` | Native; Ingenic X1000, MIPS32r2, little-endian | 32 | No | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| Same Q/K/H2/F20 family, hosted port | 245 / `aigoerosq` (configure also accepts `erosq`) | Linux/HiBy-hosted; MIPS32r2, little-endian, hard-float build ABI | 8 budget; physical RAM unverified | No | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |
| iRiver H320 and H340 | 11 / `iriverh300` | Native; Motorola/Freescale MCF5249 ColdFire, big-endian | 32 | Yes: microphone, line-in, FM | Final E003 + Sonic linking / Windows startup PASS; see fifth refresh |

The simulator UI/keymaps exist for these selectors, including the older M3K
port, but source presence is not successful compilation. In `tools/builds.pm`,
`fiiom3klinux` has status 1 (unusable; no default advertised simulator),
`aigoerosq` status 2 (unstable), and the other listed main targets status 3
(stable). These upstream labels do **not** certify integrated eSpeak.
The harness deliberately accepts canonical names, not the `erosq` alias or
retail names such as `hifiwalkerh2`, `surfansf20`, `iriverh320` or `iriverh340`.

## Identify the exact hardware before any firmware work

"Aigo Eros" is insufficient: this mapping covers **Eros Q/K and the identified
clones**, not every Eros-branded player. Ask for the full model and the original
firmware version. Ask H2/F20 owners for those details too; never infer the
revision from a sales listing or case appearance alone.

The following ranges are copied from this checkout's `utils/rbutilqt/rbutil.ini`.
They are local installer metadata, not a guarantee for later vendor revisions.

| Native installer hardware family | Aigo Eros Q vendor version | HiFi Walker H2 vendor version | Surfans F20 vendor version | Bootloader configure selector |
| --- | --- | --- | --- | --- |
| hw1/hw2 | 1.8-2.0 | 1.1-1.2, 1.4-1.6; **1.3 uses a different update package** | 2.2-2.7 | 247 / `erosqnative` |
| hw3 | 2.1 | 1.7-1.8 | 3.0-3.3 | 248 / `erosqnative_v3` |
| hw4 | 2.2-2.3 | 1.9-2.3 | 3.4-3.5 | 249 / `erosqnative_v4` |

The v3/v4 selectors are **bootloader-only**, enforced by `tools/configure`;
they are not additional firmware/simulator targets and are excluded from the
harness. All rows use the main `erosqnative` Rockbox target. In particular,
H2 1.3 selects `erosqnative-hw1hw2-eros_h2.upt`, not the otherwise common
`erosqnative-hw1hw2-erosq.upt`. The Eros K and unlisted vendor-version mappings
remain to be confirmed; do not extrapolate the Q ranges. Hosted H2/F20 installer
entries are marked disabled and also name version-specific packages. Do not
treat the hosted selector as a revision-independent installation workaround.

The Classic selector covers the Classic family, including later models often
called 6.5G/7G; it is not `ipodvideo` or an arbitrary older iPod. The local
`utils/mks5lboot/README` identifies 80/160 GB late-2007, 120 GB late-2008,
160 GB late-2009 and late-2012 variants, with different Apple firmware versions.
Confirm the actual device, firmware and any storage modifications before
installation. X3 and X3 II are different ports, not interchangeable revisions.
Clip+, Clip Zip and the original Clip likewise have distinct selectors.

## What a simulator can and cannot establish

`--integrated-espeak` supports SDL simulators, experimental native Clip+/Clip Zip
builds and the HiBy R1 Linux application. Other native and Linux/HiBy targets
remain disabled. See
`ESPEAK-CLIPPLUS.md` for the separate firmware package and its validation limits;
the simulator executable itself must never be installed as player firmware.

All Windows simulators here run x86-64 host code, not the player's ARM/MIPS/
ColdFire instructions. `firmware/export/config/sim.h` resets `CONFIG_CPU` and
selects the SDL platform. Host allocation, threads, libc and performance cannot
prove device RAM fit, stack depth, endian correctness, CPU cost or battery life.
The 8 MiB Clips in particular require measured engine, dictionary, stack and
playback-buffer budgets before any firmware claim. The native MIPS configure
toolchains use soft-float flags; hosted variants use different Linux APIs/ABI.

Recording is **not simulated as real input**: recording functions in
`firmware/target/hosted/sdl/pcm-sdl.c` are stubs. A recording menu or target
capability bit therefore cannot validate microphone/FM recording, recording
while speaking or microphone feedback on a device.

The diagnostic reports below prove core linking and bounded startup PCM only, not
complete playback, plugins, input, recording, graceful shutdown or accessibility.
The SDL UI lacks a native NVDA control tree; self-voicing is not proof of NVDA
accessibility. No physical-player or NVDA test was run for this inventory.

## Final Windows target results, 2026-10-05 (fifth refresh)

**10/10 incremental core refreshes and 10/10 native Windows startup tests passed**
with the final Sonic chunk fix and five corrected Polish semantic labels.
All ten x64 GUI PE executables contain eight speech and seven Sonic symbols,
compare plugin ABI `0xe003` in the linked loader and import no eSpeak/Sonic DLL.
This validates simulator compilation/linkage and Polish startup, not hardware
compatibility or complete per-target application acceptance.

- A: `snapshots/historical-target-validation-20261004T191216472833Z-20261009T145217378144Z/Workspace/tts-target-tests/20261004T191216472833Z/report.json`; SHA-256 `6908d00a566ec58cdad82c5b0e1b2eb2af36b7d2fdbd15cca5b1545224f82fd2`; refresh `20261004T220142333946Z`.
- B: `snapshots/historical-target-validation-20261004T191216434977Z-20261009T145732427896Z/Workspace/tts-target-tests/20261004T191216434977Z/report.json`; SHA-256 `f0e07ef3bce4379ff6687fd2ba8a18ea7cfa66008d43a5b84a1a06b417d51b74`; refresh `20261004T220203759458Z`.
- C: `snapshots/historical-target-validation-20261004T191216433147Z-20261009T150905061939Z/Workspace/tts-target-tests/20261004T191216433147Z/report.json`; SHA-256 `125a5adec8a4c2cfb66c00c294d64956bc2f02a48f2d0349059be967caa3fffb`; refresh `20261004T220206076166Z`.

| Target | Group | E003 refresh / Windows startup | Refresh make seconds | Nonzero PCM samples | Fifth-round EXE SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `sansaclipzip` | A | PASS / PASS | 25.154 | 30704 | `a3e5bde7f148660e5a0a5a59d1cc1b406d319021ec602c7ba1fe6588325ff577` |
| `xduoox3` | B | PASS / PASS | 21.676 | 30704 | `8e4f2bb462e09ef4af7f68eefe8cca7347490a6a9859b62fa50a698caf96ffda` |
| `xduoox3ii` | B | PASS / PASS | 21.651 | 30704 | `f7e2eaccc05530268d6a631b3c0ae8cca7b8bd61bc507cf9b42e8ee42f5d2246` |
| `xduoox20` | B | PASS / PASS | 21.311 | 30704 | `1b5e6aa0c0cc6e194f1254fac43877acc04154e3fd6b77152e0b30c6ec9c68be` |
| `shanlingq1` | B | PASS / PASS | 22.306 | 30906 | `c3efa55dc31ba15131710352056a56c3f75ce9dab7b6b0ddec210d1c3af64cc9` |
| `ipod6g` | A | PASS / PASS | 23.039 | 30704 | `4738e1a700bd968215765c6189eacdead5773ff23c7cdc87cc7fbc29c2bf21aa` |
| `fiiom3k` | C | PASS / PASS | 23.070 | 30906 | `3c38a0a4fc35abe7e9c08ab54827acb731bb24010bc8a39406c10d330b1ffcbc` |
| `erosqnative` | C | PASS / PASS | 22.813 | 147242 | `bbf63bad918058c33593cc2d91e7f359526c9bd875df41b68c27a46d1e77d681` |
| `aigoerosq` | C | PASS / PASS | 21.663 | 30704 | `fc3c57ac32ce9d499ea104d1831b1eb59325dc1fc22227b5ef3f38313c833746` |
| `iriverh300` | A | PASS / PASS | 23.660 | 30704 | `735b50f8bd04afb2d3816b73f49af1fbcebd001a2df26ec95db7e8a2cad032cf` |

All 41 before/after source hashes match across all ten targets and the source
at independent closeout. Canonical source-dictionary SHA-256 (sorted JSON keys,
separators `(',', ':')`, UTF-8):
`b8eccced0995394ee231d147d5c7d825eb5316819656fd2bab34303c75fdaee6`.
Key source hashes:
- `lib/espeak/rb_espeak.cpp`: `3e0c3c8087776497a26a29422ed05bc79cdf1fdc62683fe875243f3985e435f4`.
- `apps/lang/polski.lang`: `39e8fab5231ee26dea135dfbed3122ca56471ef38866a8e9cf1a0c9d78c6d1d8`.

Full source hashes, EXE sizes, catalog/audio/log hashes, warnings and preservation
checks: `Workspace/tts-target-tests/final-sonic-pl-round5-20261005.json`,
SHA-256 `ae2882360353de113bc56880a9a2b41f865dbf77c66ded8549e6487bffc09749`.
The 51 source hashes in
`Workspace/espeak-sonic-chunks-20261004/source-freeze.json` also match;
that file's SHA-256 is `f0aeb7ec6cf1414a185338b390bbea266d3c923dd7857a393056be8d5544d70b`.
Its normal, ASan, UBSan, Windows and no-Sonic backend result logs record PASS.

Every refresh regenerated `english.list` and both PL/EN display/voice catalogs:
50 files total. All four binary catalogs per target have all 38 nonempty TTS
labels, including recorder-unavailable. All ten Polish display/voice catalog
pairs contain `Wymuś` and `Wyjątek: przewijanie/pomijanie/odtwarzanie/głośność`
as five separate labels; corresponding English labels also match. This is
catalog evidence, not a recorder-operation or complete language-runtime test.

Refresh used WSL Ubuntu-24.04, incremental `make bin`, `--jobs 4 --timeout 1800`
per group. Native smoke ran sequentially on **2026-10-05 CEST**:
A 00:03:09.692-00:03:17.680, C 00:03:41.613-00:03:49.627,
B 00:04:22.082-00:04:32.995. All refresh/smoke commands exited 0. Video was
Windows, not dummy; audio went to disk, only each test's PID-owned window was
hidden, and no keys were sent. Each fixture retained 175 WPM (signed scale 0%)
and spoke `Pliki`. Simulator exit 1 is deliberate termination after startup,
not a graceful-shutdown test. Native Eros's PCM count includes residual -1
samples and must not be interpreted as longer speech.

Separate Clip+ high-rate evidence is retained in
`Workspace/sonic-simulator-tests/20261004T214738084909Z/report.json`:
451 WPM took 22.430476 s, 1350 WPM 8.219864 s, ratio 0.3664596273, with
pause/cursor/resume/navigation/mixer/shutdown checks recorded as passing.
That run uses EXE SHA-256
`28b12ef3da4f3bf85ce5a2ae19def2765e368f120dd5d9e726c4bbfbe618675c`.
It supersedes the earlier starvation baseline's 1.018181818 ratio; it is **not**
a high-rate GUI test of these ten targets or a claim about a later package.

No warning/error lines occurred in the fifth-round make logs. This incremental
run does not clear earlier MinGW intrinsic or Win64 pointer-width warnings.
SYSFONT and missing optional icon/backdrop messages remain in startup logs
(optional asset messages absent for X3); SDL disk-driver `CRITICAL` notices
identify the intentional capture destination. No hardware, NVDA, full UI,
English runtime, per-target high-rate reader, recording, mixing or bundled
plugin acceptance is established by these ten startup tests.

Fourth-round builds passed but were superseded by the final Polish catalog
change; they remain in the fifth-round history snapshots. No report or earlier
failure was discarded. Independent checks verified 12 archived group reports,
348 manifest moves across four history rounds, 50 refresh EXE snapshots, the
two original X3/Q1 snapshots, 2,830 engine-data files and 50 current catalogs.
Old EXEs are in `snapshots`; reports/logs/catalog history remain in `Workspace`.
The ten isolated runtimes are retained for reproducible diagnostic tests, not
as user releases. The historical report links below point to immutable versions.

## Historical Sonic Windows baseline, 2026-10-04 (third refresh)

**10/10 E003 core refreshes and 10/10 native Windows startup checks passed**
on the source snapshot identified here. This is a completed diagnostic baseline,
**not final Sonic feature acceptance**. High-rate reader/cursor throughput had a
reported issue in this baseline and was not tested in this target matrix.
The later fix and separate Clip+ evidence are described in the final results above. These results do
not validate subsequent backend changes or establish physical-player support.

All ten PE x64 GUI cores contain eight speech and seven Sonic symbols, with
linked loader ABI `0xe003` and no external eSpeak/Sonic DLL. All five catalog
files per target were regenerated; PL/EN display and voice catalogs contain
all 38 TTS IDs, including the recorder-unavailable label. Label presence does
not prove the recorder guard's runtime behavior. Startup uses Polish and
canonical 175 WPM (0% in the signed display scale), not the 1350-WPM Sonic path.

- A: `snapshots/historical-target-validation-20261004T191216472833Z-20261009T145217378144Z/Workspace/tts-target-tests/20261004T191216472833Z/refresh-history/20261004T215250603457Z/report.json`; SHA-256 `3b1b930f603b5d10bb000cd595db6bf5420deb9f56b7472006ed0ba06051ad45`; refresh `20261004T212619264801Z`.
- B: `snapshots/historical-target-validation-20261004T191216434977Z-20261009T145732427896Z/Workspace/tts-target-tests/20261004T191216434977Z/refresh-history/20261004T215308757558Z/report.json`; SHA-256 `79335446220c8dcd2e3064a065da5a490d4315c30036004d12a1f5d5859436a2`; refresh `20261004T212637090837Z`.
- C: `snapshots/historical-target-validation-20261004T191216433147Z-20261009T150905061939Z/Workspace/tts-target-tests/20261004T191216433147Z/refresh-history/20261004T215358448847Z/report.json`; SHA-256 `43f237f8bdb6c1c26c42b901c24c897bee296938f631e00dae524784c68bd131`; refresh `20261004T212845522206Z`.

| Target | Group | E003 refresh / Windows startup | Refresh make seconds | Nonzero PCM samples | Round-three EXE SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `sansaclipzip` | A | PASS / PASS | 63.868 | 30704 | `b5ddde138e72e47034883db358cc6e66be555e42e8acc09aad6a4cc82f29df90` |
| `xduoox3` | B | PASS / PASS | 55.072 | 30704 | `61f32a63383c41c89cc506b238eb35eb932c2ea6a243abcf2d0d5d76e0dc8e4d` |
| `xduoox3ii` | B | PASS / PASS | 62.051 | 30704 | `25430e53a1f62809d463e3bf691260d523fe8fdc1d66efe849e14e19048c9177` |
| `xduoox20` | B | PASS / PASS | 70.908 | 30704 | `0f9950b67a06e7fad00b2d3902d333ee10b575a02d7ea026fa2da35896c8e77f` |
| `shanlingq1` | B | PASS / PASS | 60.722 | 30906 | `a27600f52ae5f83978b0d0a8fc3e03114e6c10b1f320d5fd4d228b13d35cd386` |
| `ipod6g` | A | PASS / PASS | 69.567 | 30704 | `a448954fa96e4f4b3f0d4b791d1d44d0bf907af4fd48371afa88f8a449b7931b` |
| `fiiom3k` | C | PASS / PASS | 74.979 | 30906 | `3544e470190fa72394dfae38f254955cedfa77817b67a4d9d07fc87460399d9f` |
| `erosqnative` | C | PASS / PASS | 57.250 | 134954 | `8914f45ccd829e8fbbd849cc80febe6b849b36fffc75f269a2a3856e7b02f1aa` |
| `aigoerosq` | C | PASS / PASS | 48.166 | 30704 | `7b04749c0be8890f3e15e4621ba9459aeb7d498b557f31620d2ce5cbb8426ede` |
| `iriverh300` | A | PASS / PASS | 78.086 | 30704 | `023c1b43527e943503f850386c5d00098690700cec3c21fbad08df3af89d63f0` |

All 41 before/after source hashes matched across the ten targets and the source
snapshot at independent verification (21:35:08 UTC). Their canonical JSON SHA-256
(sorted keys, separators `(',', ':')`, UTF-8) is
`62565adcf4c242a9e119dd170123fafc3b34d6ccb859917bd84fc82e5450e9f9`.
All 51 backend handoff hashes also matched. Full input hashes and independent
EXE/catalog/data/history checks are retained in
`Workspace/tts-target-tests/sonic-baseline-round3-20261004.json`, SHA-256
`b96a3da33a80edb46c905c2dd64c048606dfeccbc9b16049ddd9b90b2b1d5038`.

Smoke ran sequentially with Windows video (not dummy), disk audio and PID-owned
window hiding, without keyboard input: A 23:31:07-23:31:15, B 23:31:55-23:32:06,
C 23:32:52-23:33:00 CEST. All refresh/smoke commands exited 0; each simulator
was deliberately terminated with exit 1. This does not test graceful shutdown.

The ten previous EXEs moved to
`snapshots/tts-target-before-abi-validation-<target>-<round>/rockboxui.exe`.
Prior reports, smoke, catalogs and catalog logs are retained through the
`refresh-history/<round>/manifest.json` mappings: 110 moves in this round,
168 across both recorded history rounds. Independent checks verified those
artifacts, 2,830 engine-data files and 50 current catalog files. No prior failure
or report version was discarded; the preceding baseline's report links below now
point to its immutable history snapshots.

Eight make warning lines remain: four future-timestamp/clock-skew pairs for
Clip Zip (0.19 s), iPod (0.043 s), X3 (0.36 s) and native Eros (0.25 s).
The affected generated headers and relevant rebuilt objects were inspected;
objects follow their sources/headers and linked EXEs follow those objects.
Warnings are retained, not suppressed. No C/C++ warning diagnostic appeared in
these incremental logs; this is not a clean-build warning clearance. Earlier
Win64 pointer-width warnings remain a rendering risk. SYSFONT and missing
optional icon/backdrop warnings remain; PCM counts include residual values and
are not speech-duration measurements. The broader limitations below still apply.

## Historical Windows results, 2026-10-04 (second refresh)

These results apply only to the completed second refresh, before the signed
speech-speed scale, Sonic integration, Polish punctuation-label change and
further PL/EN catalog corrections. They are retained historical evidence, not
validation of those later changes. References to final results in this section
mean the final results of round two.

**10/10 final E003 refreshes and 10/10 native Windows startup checks passed**
after the recorder-label and SDL startup-order fixes. Clip+ has separate package
and regression coverage; it is not an eleventh result here. Deprecated/unusable
`fiiom3klinux` is deliberately skipped; retail aliases and bootloader-only
`erosqnative_v3`/`erosqnative_v4` are not additional simulator targets.

Each Windows x64 GUI PE uses SDL 2.32.10, has all eight required speech symbols,
and compares `0xe003` in linked `plugin_load`, without an external eSpeak DLL.
These are core-only diagnostics, not full plugin/codec/user packages. Evidence:

- A: `snapshots/historical-target-validation-20261004T191216472833Z-20261009T145217378144Z/Workspace/tts-target-tests/20261004T191216472833Z/refresh-history/20261004T212619264801Z/report.json`; SHA-256 `1a3d6c610a66da1ba7396a24a7a7524a08d4798ef914462c80e12a1fedcb9450`; refresh `20261004T202259171769Z`.
- B: `snapshots/historical-target-validation-20261004T191216434977Z-20261009T145732427896Z/Workspace/tts-target-tests/20261004T191216434977Z/refresh-history/20261004T212637090837Z/report.json`; SHA-256 `4a2d3346fd45aab8bf55c1dbb3de17dfd1d5552daeb3f2cfb1b69f3966fe68f6`; refresh `20261004T202456612777Z`.
- C: `snapshots/historical-target-validation-20261004T191216433147Z-20261009T150905061939Z/Workspace/tts-target-tests/20261004T191216433147Z/refresh-history/20261004T212845522206Z/report.json`; SHA-256 `25144507faca1c220732a290ce1a14c3c408e56e01592c544111f80a0095e0f2`; refresh `20261004T202500354544Z`.

| Target | Group | E003 refresh / Windows startup | Refresh make seconds | Nonzero PCM samples | Round-two EXE SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `sansaclipzip` | A | PASS / PASS | 97.943 | 30704 | `11930609806af5e85949ac3edb5fefb306b95a5cc27141def1dce9c87a28c513` |
| `xduoox3` | B | PASS / PASS | 125.246 | 30704 | `7424e5f8b1486a8797fb79e1012d964b2858354a7aa2de436166c3a9ac124d7d` |
| `xduoox3ii` | B | PASS / PASS | 117.699 | 30704 | `19c25da84aedb2e4864e1a456969813b35ab2b461470112e4b41e43e915315fc` |
| `xduoox20` | B | PASS / PASS | 89.177 | 30704 | `0246f89f171b1bc4b3780913e3fe44e9f3105e71949323db64c5da1e260bdc64` |
| `shanlingq1` | B | PASS / PASS | 96.583 | 30906 | `590f87362d2705e0f4f5526ab92d9f84a6f13f7c953d863e894602d0ff2ab657` |
| `ipod6g` | A | PASS / PASS | 136.054 | 30704 | `14db8b8466ca2676787ae2437e6a05a49881b0e9ca3caacb0434be1369e0fad4` |
| `fiiom3k` | C | PASS / PASS | 139.583 | 30906 | `edad8c82ba396177bf68c5ced9c474aa5d4571d12d0c0ec1c4c8d2b65f19f135` |
| `erosqnative` | C | PASS / PASS | 130.819 | 134954 | `6d96a37b715a8a66a24b64ea4b3c7581381f64e6fbaf60b77dc93b76a1086350` |
| `aigoerosq` | C | PASS / PASS | 88.877 | 30704 | `ae2ebc0fcafbbcc60106b190dcdf959f0ab5bf48f27cb368c20e86f340e42ada` |
| `iriverh300` | A | PASS / PASS | 135.927 | 30704 | `305bb95b5f2d87f338bb44cac8b7447c7d2658ec663571e060edb538c71e310d` |

At verification, all ten before/after source dictionaries matched each other
and the then-frozen working tree. Their canonical JSON SHA-256 (sorted keys, separators `(',', ':')`, UTF-8)
is `df914b7021f3f3b21c06ed02fab3e7473a39d99358dab59743d04c308daf3ca5`. Reports retain the 30 individual
source hashes, EXE sizes, imports, ABI comparisons, 283 engine-data file hashes
per target, PL/EN catalog hashes, initial/refresh durations and PCM/log hashes.
Independent post-smoke checks verified final source/EXE/PCM/log hashes and all
58 moved artifacts in the three refresh-history manifests.

Smoke used native Windows Python, `SDL_VIDEODRIVER=windows`, software rendering,
disk audio and PID-owned window hiding, not dummy video. No keys were sent.
CEST intervals: A 22:30:09-22:30:18, C 22:31:57-22:32:06, B 22:32:15-22:32:27;
exact UTC starts are in the reports. Every raw log has `TTS utterance: Pliki`,
Polish, rate 175 and punctuation 0. Every PCM capture has at least 30,228 samples
with absolute magnitude above 1. Processes were intentionally terminated;
recorded exit `0x00000001` does not establish graceful shutdown. This validates
captured synthesis, not listening quality or physical speaker output.

### Warnings and limits

- Six initial source-drift-only failures remain in `prior_build_failure`. The
  first refresh and six successful smoke runs were superseded after further
  source fixes; immutable history retains them. Round two has no source
  drift, compile/ABI failure or startup synthesis failure.
- Round-two logs retain MinGW's `__readgsqword`/`GetFiberData` array-bounds warning
  in `intrin-impl.h:838`. X3 II, X20 and hosted Eros retain eight pointer/integer
  width warnings each in `firmware/drivers/lcd-24bit.c`. Its conversions through
  `long` remain a Windows x64 rendering risk; startup without full backdrop
  assets does not exercise all affected paths or fix this issue.
- Initial logs also contain the `lib/skin_parser/skin_debug.c:45` integer-to-pointer
  warning and configure's assumed little-endian message. H300 initially reports
  a 0.0072-second future timestamp and clock skew; no round-two refresh log has clock skew.
- All targets log SYSFONT viewport warnings; all except X3 also log missing
  optional icon/backdrop BMPs. SDL disk-driver `CRITICAL` lines announce the
  intentional capture, not failed synthesis. Minimal runtimes are not full UI packages.
- Native Eros logs `verify_device_dataTTS: Pliki` without a separating newline,
  leaving the line-anchored `speech` summary empty despite raw utterance/parameter
  evidence. Its nonzero count includes many residual `-1` samples; amplitude is
  -731..728 and 30,228 samples have absolute magnitude above 1. A larger count
  is not more spoken content or better quality.
- English runtime, full reader/keyboard navigation, playback mixing, recording,
  plugins/codecs, NVDA, graceful shutdown, repeated-startup stress and physical
  players were not tested here. English catalogs are not English runtime proof;
  broader Clip+ results do not transfer. **Hardware fit/compatibility, full
  accessibility and distribution/license clearance are not established.**

### Archived earlier X3/Q1 executables

After replacements passed, E002 EXEs moved from
`Workspace/tts-target-tests/20261004T175730583982Z/<target>/rockboxui.exe` to
`snapshots/Workspace/tts-target-tests/20261004T175730583982Z/<target>/rockboxui.exe`.
Provenance, PE contents/size, contained paths, exclusive access and running-process
checks preceded the moves; these SHA-256 values remained unchanged:

- `xduoox3`: `e37687b0259f0d2cc6248f69ab1b178c96e8e2c1125c1fdb9fa13893f2595e2a`
- `shanlingq1`: `f4360a2840e46e87146c34c8fa918ed30f11360d0ca8c4d25ce687a9ac03944f`

The historical report and 23 logs remain unchanged in Workspace. Its `directory`
fields describe old build locations, not current EXE paths; use this mapping,
not a new smoke against that retired report. Current diagnostic EXEs, isolated
runtimes and logs stay in Workspace, not `installfiles`. Earlier refresh EXEs
remain in report-listed snapshots. No duplicate EXE/user release was created
and nothing was deleted from trash.

## Selection and build cost

Listing is read-only and works in Windows PowerShell without WSL or an SDK:

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
python -B tools/tests/test_tts_targets.py --list-targets
python -B tools/tests/test_tts_targets.py --help
```

The following are **future build examples**, not completed test results.
Run the build phase under WSL from the repository root. To stage all 11 main
Windows targets for startup testing, use the explicit selection without
`--build-only`:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/tests/test_tts_targets.py --platform windows \
  --targets sansaclipplus sansaclipzip xduoox3 xduoox3ii xduoox20 shanlingq1 \
    ipod6g fiiom3k aigoerosq erosqnative iriverh300 \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 4 --timeout 1800
```

For an optional single-target compile-only check, without startup assets:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/tests/test_tts_targets.py --platform windows --targets sansaclipzip \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --build-only --jobs 4 --timeout 1800
```

- Default selection remains `xduoox3 shanlingq1`; it does not silently expand
  into twelve fresh builds. `--targets` selects one or more unique names.
- `--build-only` skips dictionaries, voice catalogs and simulated-disk staging.
  Ordinary builds stage isolated runtime data only after the core passes link
  checks; each such copy is announced and hash-verified for later smoke tests.
  These useful diagnostic copies remain under `Workspace/tts-target-tests`.
- A build-only report cannot be smoked directly. Omit `--build-only` for targets
  needing startup tests. The guarded refresh mode can stage missing runtime only
  after rebuilding and validating the core, with matching engine provenance;
  it is not a standalone asset-copy mode. Unrecorded partial runtime is rejected.
- The harness runs `make bin`, not the complete codecs/plugins/package build.
  Targets are sequential; `--jobs` controls make within each target. Start with
  2-4 jobs on a constrained host; use the existing verified SDK rather than
  installing twelve device toolchains. Windows cross-builds require the checked
  SDL 2.32.10 MinGW SDK plus the host tools; Linux needs its SDL development SDK.
- Existing X3/Q1 Windows records show 285.172 s and 456.857 s for the initial
  core builds, excluding staging and later ABI refresh. These are historical
  observations, not estimates for all targets or current machine load. Inspect
  per-target logs before raising a timeout (allowed range: 30-1800 seconds).
- The ten initial cores took 710.746-1067.643 seconds each; final incremental
  round-two make runs took 88.877-139.583 seconds, excluding preflight/staging. These are
  observations under concurrent host load, not a performance guarantee. Use the
  demonstrated 1800-second bound and inspect failures.
- Every new build uses a timestamped evidence directory; it is not incremental
  reuse of a previous run. Select only needed targets and keep shared source
  unchanged during the run; before/after hashes detect some concurrent edits.

For the staged Windows report, run the startup check on native Windows. At the
prompt, enter the timestamp of a newly built report still in central `Workspace`,
rather than an archived report. The explicit video driver
keeps this run distinct from a headless/dummy-video test:

```powershell
Set-Location -LiteralPath 'D:\Rockbox\rockbox'
$runId = Read-Host 'Timestamp of the new report in central Workspace'
python -B tools/tests/test_tts_targets.py --smoke-report "D:\work\Workspace\rockbox\tts-target-tests\$runId\report.json" --video-driver windows
```

Report modes use the report's targets, not `--targets` filtering. The smoke
check captures startup audio and terminates the process; it is not a complete
application acceptance test. `--refresh-report` rebuilds a completed group
incrementally and checks the integrated plugin ABI in both source and linked
loader. For new-phase sources both must match `0xe006`; historical reports keep
their original ABI and do not validate this generation. Review the current
validator before use and refresh only a fresh report, never closed evidence.
Keep source files unchanged throughout the refresh and subsequent native smoke.
Invoke the refresh under WSL, then run a new native smoke:

```sh
cd /mnt/d/Rockbox/rockbox
read -r -p 'Timestamp of the new report in central Workspace: ' run_id
python3 -B tools/tests/test_tts_targets.py \
  --refresh-report "/mnt/d/work/Workspace/rockbox/tts-target-tests/$run_id/report.json" \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 4 --timeout 1800
```

Repeated refresh preserves the previous report byte-for-byte in
`<group>/refresh-history/<round>/report.json`. Its `manifest.json` maps old paths
to hash-verified archived evidence; historical reports are not rewritten to
pretend they describe the new executable. Old EXEs move to `snapshots`, while
old smoke and legacy refresh logs move into the history directory. All five
staged PL/EN catalog files and original catalog-generation logs are also archived
before regeneration. New build, symbol, PE, loader and catalog-generation logs
use `<target>/refresh-rounds/<round>/`. These diagnostic
histories and isolated engine-data copies remain useful regression evidence.

The whole group is checked before artifact moves. A report lock excludes
concurrent refresh/smoke. Active failures, unfinished rounds, incomplete smoke,
changed hashes, running executables and unsafe paths are rejected, not reset.
The special initial source-drift-only recovery retains the original failure.
A mid-round failure stops further work and requires inspection; do not delete
lock/error/history fields to force a retry. A successful refresh needs fresh
smoke, and smoke rejects sources changed since compilation. Fingerprints include
the reader, recorder, bridge/engine and all three SDL system/header/kernel files;
they are a bounded source list, not an exhaustive build dependency manifest.

### Catalog and rate checks

Each refresh regenerates both PL/EN display and speech catalogs plus
`english.list`, using the rebuilt target's features. The harness validates target
headers, payload sizes, counts and all 38 TTS identifiers, including nonempty
`LANG_TTS_RECORDER_UNAVAILABLE` display/speech text. Existing catalog hashes and
paths must pass preflight; incomplete or failed regeneration is preserved and
blocks automatic retry. Catalog presence alone does not test recorder behavior.

The fixture stores canonical WPM, not a signed percentage: `tts rate: 175` with
`tts rate scale: percent` corresponds to 0%; an existing value of 450 remains
450 WPM. Smoke checks the configured WPM parameter and records the config hash
and expected signed percentage. These are fixture-consistency checks, not proof
of the displayed scale. Neutral startup does not establish high-rate Sonic
behavior or PCM identity with Sonic bypassed.

The current 41-file fingerprint includes engine rate hooks, `wavegen.cpp`,
SDL startup files, the eSpeak makefile and Sonic sources/headers/provenance files.
New builds and refreshes require seven linked Sonic symbols as well as the eight
speech symbols. Historical reports retain their own source lists and hashes;
they do not establish coverage of later Sonic sources.

## Distribution boundary

eSpeak engine headers grant GPL-3.0-or-later; many Rockbox core headers grant
GPL-2.0-or-later, but that does not establish the license of every linked file.
The dietlibc-derived `firmware/libc/strtol.c` and `strtoul.c` state GPL version 2
without an "or later" grant. Native builds select those sources. Existing
Windows linker maps instead resolve these functions through the host CRT, so
that specific native concern is not proof that the Windows core contains them.
Do not blanket-relicense Rockbox or assume source-only publication automatically
solves incompatible linking. A complete per-artifact source/license inventory
is still needed before releasing the integrated work. Preserve the original
notices and license texts; resolve uncertain grants before distribution.
This document does not grant new licensing permissions or certify a release.
