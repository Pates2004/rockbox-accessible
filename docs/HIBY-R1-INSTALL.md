# HiBy R1: installation, updates, removal and accessibility status

Our-port update, 2026-10-11: the shared core has a gesture editor and exploration
of standard lists and the text reader; host validation is not physical R1
acceptance. Bluetooth requires a separate device test. Native R1 defaults to
charge-only USB and refuses writable card export with an unverified vendor
automounter. See `ACCESSIBILITY-TOUCH.md`, `ESPEAK-BLUETOOTH.md` and
`ESPEAK-HIBY-USB.md`. The card-file replacement procedure below is not an
already-working live Rockbox updater or instructions for installing a Windows EXE.

Checked: 2026-10-14. [Polska wersja](HIBY-R1-INSTALL-PL.md).

This is a source-verified procedure with explicit prerequisites, **not a tested
installation on your player**. Check the exact model and installed firmware
for the specific unit. Complete section 2 before writing anything to the device.
The modified firmware was downloaded and inspected, but no device flashing,
patcher execution, firmware modification or hardware test was performed.

## Current packages and startup without OS selection

Our native first-test package is in `installfiles/hibyr1`; the downloaded
Bahusoid firmware is in `installfiles/fw-rockbox`. Short guide: `ESPEAK-HIBYR1.md`.
The former supplies the complete card `.rockbox`, while the latter supplies
the one-time internal `r1.upt` update. Do not install the Windows program on R1.
The image installs modified HiBy OS **1.8b2**. Safe transitions from every other
version are not established; downloading an image is not an update test.

The supplied `.rockbox` seeds Rockbox as the default: four binary bytes
`00 00 00 00` in `rb_bl_mode.txt`, not the text "0". The inspected loader reads
this choice and automatically launches it after about one idle second. No OS
confirmation is required at each boot. Without the file, the first countdown
is ten seconds and still defaults to Rockbox. Zero-delay or invisible selection
is not promised.

To choose HiBy Player from saved Rockbox, briefly press **Volume Down** during
the selector, then **Next** to confirm. Do not hold Next while powering on:
that selects a different production mode. The HiBy Player choice persists for
future boots; choose Rockbox again to restore its automatic startup. This map
comes from the inspected loader, not a physical-device test.

If the short selector is difficult to intercept, change the card choice from
Windows with the player powered off. For this specific loader, the following
PowerShell command selects HiBy Player. **Replace `E:` with the card's real drive**;
do not run it against an unidentified drive or while the player is running:

```powershell
[IO.File]::WriteAllBytes('E:\.rockbox\rb_bl_mode.txt', [byte[]](2,0,0,0))
```

The same command with `[byte[]](0,0,0,0)` restores Rockbox. This selects an
application only; it does not recover or restore the original firmware, and
does not change other `.rockbox` data.

## 1. Which software this guide describes

| Software | Verified status |
| --- | --- |
| Original HiBy OS | Manufacturer's Linux firmware and player application. |
| Official Rockbox `hibyr1` | Existing hosted Linux target, listed as unstable. It is not our TTS build and does not include Bahusoid's Bluetooth integration. |
| Bahusoid's Rockbox Audiobook Mod | Existing third-party R1 release with a different physical keymap, touch gestures and Bluetooth code. It is not our integrated eSpeak build. |
| Our R1 with shared TTS | The separate Windows prototype and hosted HiBy adaptation are described in `ESPEAK-HIBYR1.md`. This is not a hardware-accepted build with TalkBack gestures or Bluetooth; do not install the Windows executable on the player. |

The checked fork is [bahusoid/rockbox](https://github.com/bahusoid/rockbox).
Its default branch `Mod25.12.07` points to
`059809d123a5b2d4ff1d65b571e99cf56b35dd51` (2026-10-01).
The latest published R1 release is [26.09.17 / `x1600_hiby_v2`](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2),
commit `94c69704e9cf8bae77240a98a8eb7bd5c576f426` (2026-09-17).
Branch HEAD and release are different revisions. We use only the modified
firmware and loader from that pinned release. Our separate eSpeak package
supplies the card application, not Bahusoid's application archive.

Official upstream was checked at
`7d090f24b990ef54e3f9dc7eb2edba4865605471`.
Its [target registry](https://github.com/Rockbox/rockbox/blob/7d090f24b990ef54e3f9dc7eb2edba4865605471/tools/builds.pm)
marks R1 unstable. Support for the ordinary port does not certify our future TTS.

## 2. Before installation: information and recovery gate

1. Identify the exact player and firmware in the original player's **About**
   screen. Record the full version/build, model variant and any existing mod.
   Do not use R3, R3 Pro II, R2 or R1 MIDI images on an assumed-compatible R1.
2. Confirm compatibility of that specific starting firmware with the selected
   patch/release, including any version change. The fork's supplied system image
   is described as **1.8b2**. Its availability does not prove safe upgrades or
   downgrades from every other firmware. No universal compatibility matrix was
   established. If this is unresolved, stop before flashing.
3. Obtain an appropriate **unmodified official R1 update** for restoration from
   [HiBy support](https://store.hiby.com/apps/help-center). Record the first-party
   download chain, version, size and SHA-256. Confirm that it is a normal card
   update, not a factory/burn image. A locally calculated hash records your file;
   it does not authenticate it without a trusted reference. If HiBy supplies no
   digest, obtain confirmation rather than inventing one.
4. Establish the forced-update method for that unit/firmware before relying on
   it. The manufacturer's manual is internally inconsistent; see section 7.
   Confirm access to the normal updater, a working card reader and support if
   recovery fails. A downloadable file alone is not a tested recovery plan.
5. Back up music, settings, bookmarks and other irreplaceable card/device data.
   A card backup does not back up internal firmware. In this project, recovery
   backups and previous releases belong in central `Snapshots`, with date,
   provenance and hashes. These copies have a recovery purpose.
6. Use a charged player, reliable card, reader and power supply. Follow the
   firmware's own power requirements; no universal minimum percentage is claimed
   here. Do not format your only data copy. Verify the card is readable and has
   enough space. Stock filesystem support does not prove every format works in
   the bootloader's recovery updater.
7. Arrange assistance if you cannot independently operate the stock updater or
   boot menu. Neither is confirmed self-voicing. Windows/NVDA can help prepare
   card files, but does not make the player's firmware screens accessible.

HiBy's [warranty policy](https://store.hiby.com/pages/warranty) states that
unauthorized software modifications end its warranty. Stock restoration does
not establish warranty reinstatement or an undetectable modification.

## 3. Files, integrity and actual installation paths

The maintainer publishes these assets on the pinned release page:

**For this project choose our**
`installfiles/hibyr1/rockbox-hibyr1-espeak-r34-alpha12-20261019-hardware-test.zip`
**and the firmware** `installfiles/fw-rockbox/hibyr1_1.8b2_bahusoid_rb_26.09.17.zip`.
The following table describes the loader author's materials. His application
and prerecorded voice archives do not replace our eSpeak package; do not overlay them.

| File | Purpose | SHA-256 reported by GitHub release API |
| --- | --- | --- |
| `rockbox_hibyr1_bahusoid_26.09.17.zip` | Complete Rockbox card package | `db4473d351c3a0065ff03cbd529b0198be50c788ce6a0a8e0bd937527710f1c9` |
| `hibyr1_1.8b2_bahusoid_rb_26.09.17.zip` | Modified internal-system update, described as firmware 1.8b2 with loader | `770fd83626b7899a254628670856408f07415061589820ac2991d685aa9443d9` |
| `voice_en_hibyr1_bahusoid_26.09.17.zip` | Optional matching English prerecorded menu voice | `7fd5f1f8b901ebc0a662190b12f49f3613c110fe02db6e2cc0e2cf41c2460dd7` |

The modified firmware was downloaded and its38540535 bytes matched that digest.
The other two archives retain metadata-only hashes and are not our TTS package.
The firmware ZIP contains only `r1.upt`,42113024 bytes, SHA256
`19231b97e19c429da101b1fa2ed670a79a74408ba45e29de446f9fd249410dc6`.
ZIP CRC, chunk checksum chains, complete kernel/rootfs MD5, startup scripts and
the embedded launcher's release-asset hash were checked. This is not a device
image test or proof of a safe downgrade. Check downloaded bytes before use;
stop on mismatch. Vendor components in a patched UPT
are not automatically licensed for redistribution under Rockbox's GPL. No
vendor-blob redistribution permission was established. Hashes do not supply it.

The release specifies this card layout, with no extra enclosing ZIP directory:

```text
card root/
    .rockbox/
        rockbox.r1
        ...matching codecs, plugins, libraries and resources...
    r1.upt             (verified modified update, for initial installation only)
```

Show hidden files when checking `.rockbox`. Do not create
`.rockbox/.rockbox`, copy ZIPs in place of their contents, or mix another
device's plugins/codecs with this build. The separate `bootloader.r1` asset
is an input for preparing a patched UPT, not a substitute for `r1.upt`.

The [R1 configuration](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/firmware/export/config/hibyr1.h)
and [hosted loader](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/bootloader/hibyos_linux.c)
establish the paths:

| Location | Meaning |
| --- | --- |
| Card `/.rockbox/rockbox.r1` | Rockbox application, seen on the R1 as `/data/mnt/sd_0/.rockbox/rockbox.r1`. |
| R1 `/tmp/rockbox.r1` | Runtime copy launched by the loader; not an installation destination for the user. |
| R1 `/usr/bin/bootloader.rb` | Loader installed in internal rootfs by the patcher. |
| R1 `/usr/bin/hiby_player.sh` | Patched startup script invoking that loader. |
| R1 `/usr/bin/hiby_player_orig.sh` | Original startup script preserved by Bahusoid's patcher for launching the original application. |

The checked path is `/data/mnt/sd_0`, not the `/usr/data/mnt/sd_0` path appearing
in a different fork's README. On the computer, use the card's actual drive,
not a Linux pathname. Do not edit internal files manually.

The [patcher](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/tools/r1_patcher/r1_patcher.sh)
rebuilds the root filesystem and hotplug handling while retaining the input
kernel content. The generated UPT includes kernel and rootfs update data.
Initial installation therefore writes internal flash; it is not card-only.
The patcher has destructive working-directory cleanup and was not executed.
Preparing your own UPT requires a separately reviewed, isolated workflow.

## 4. Initial installation, after all gates pass

1. Check both release archives' provenance, notices, hashes and the selected
   firmware compatibility. Preserve the verified official restoration package
   separately. Put only the intended update UPT on the installation card.
2. Extract our complete
   `rockbox-hibyr1-espeak-r34-alpha12-20261019-hardware-test.zip` from `installfiles/hibyr1`
   to the card root. Separately extract the verified firmware
   `hibyr1_1.8b2_bahusoid_rb_26.09.17.zip` from `installfiles/fw-rockbox` so its
   update is at the root as `r1.upt`. Confirm the layout above. If the actual archive differs,
   stop and investigate instead of guessing which file to rename or flash.
3. Safely eject the card/USB storage and insert the card in the powered-off R1.
4. Prefer the normal, visible stock update path: boot HiBy OS and select
   **System → Firmware update → TF/SD-card update**, check the offered image and
   confirm only the intended update. This menu-based route is documented by
   [HiBy](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/);
   exact translated labels may differ. Its use with the selected mod still
   requires the compatibility gate. Forced boot combinations are not needed
   for a working stock menu; see section 7 if it cannot be reached.
5. Let the update and restart finish. Do not interrupt power, remove the card,
   or repeatedly press buttons during writing. On a reported error, retain its
   exact message; do not cycle through arbitrary images or recovery commands.
6. At the Rockbox boot selector, check the selected application. Bahusoid's
   loader uses Volume +/− to move and Next or Power to select.
   Play is not Back in the main selector; Back applies to its nested screens.
   It remembers the previous selection and can start it after a short timeout;
   do not depend on a long opportunity to intervene. The initial default is
   Rockbox. This selector has not been tested without sight.
7. Start Rockbox at a safe listening level with wired headphones. Check
   version, card browsing, a short audio file, pause, both navigation directions,
   volume, lock/unlock and ordinary shutdown. Then select **HIBY PLAYER** on
   a subsequent boot and check the original application and update menu.
8. After a successful update, move the installation UPT off the card into the
   dated recovery archive. Keep one identified current release and its manifest;
   avoid an update file accidentally triggering a later forced upgrade.

The optional English voice archive provides prerecorded prompts for this exact
fork. It does not synthesize arbitrary filenames/books, supply our Polish TTS,
or prove complete speech coverage. In that fork, do not disable menu speech
merely to obtain the release's shutdown beep. No Polish voice asset was listed
in this release. Our prototype has independent eSpeak synthesis; its voice-file
interface setting does not control synthesis.

## 5. Booting HiBy OS and updating Rockbox

Selecting **HIBY PLAYER** runs the retained original player through the modified
system. It does **not** remove the loader or restore pristine internal firmware.
If the selector is too brief, use its physical navigation immediately during
startup; do not invent a special dualboot key combination.

For an ordinary Rockbox-only update:

1. Read that release's loader/firmware requirements. Stop if it needs a system
   change not covered by this guide. Never substitute a Sansa package.
2. Shut down cleanly. Archive the entire previous `.rockbox`, including settings,
   bookmarks and custom maps, with version/date and hashes. Move rather than
   retain purposeless duplicate releases. Preserve music and other user data.
3. Install the complete matching new `.rockbox` package on the card. A fresh
   directory avoids old plugins/codecs surviving an overlay. Restore only
   settings explicitly compatible with the new version; keep the backup.
4. Safely eject, boot Rockbox, check its version and repeat wired playback,
   controls, speech-if-installed and HiBy-player selection checks.

The release says normal Rockbox updates replace card files without another UPT
flash. This is conditional on unchanged loader/system requirements. Updating
HiBy OS is a separate internal-firmware operation and may replace the modified
startup/loader. Check compatibility again before any stock OTA or local update.
Do not update by replacing only `rockbox.r1` across unrelated builds: codecs,
plugins, libraries, resources and voice formats must match. Our TTS also uses
a separate plugin ABI; stock modules must not be imported into a future TTS build.

## 6. Complete removal and return to the original player

1. Back up user data and record the installed mod/version before starting.
   Select **HIBY PLAYER** and reach its normal firmware-update menu.
2. Recheck the official restoration UPT's exact model, provenance, hash and
   version-transition rules. Use an unmodified official card-update package,
   not the Bahusoid image and not a factory/burn image. If the appropriate
   package/version rules remain unknown, stop here.
3. Put only that intended official UPT in the card root. Apply it through the
   stock TF/SD-card updater, observe its confirmation, and allow writing and
   restart to complete uninterrupted. If the stock application cannot start,
   use only a recovery procedure confirmed for your unit; see section 7.
4. Confirm normal stock boot without the Rockbox selector, the expected firmware
   version, working card/audio/controls, and another ordinary restart. These
   checks are the acceptance criteria; we have not performed them on an R1.
5. Only after successful stock restoration, archive the previous `.rockbox` and
   remove it and leftover installation UPTs from the active card. Preserve
   music and any other needed data. Restore stock settings only if compatible.

Reflashing the appropriate official system update is the source-supported
restoration route. Merely removing `.rockbox`, choosing HiBy Player, or resetting
settings does not uninstall the internal modification. This process is not a
claim of a byte-for-byte factory image, erasure of all traces, a guaranteed
unbrick, or automatic warranty restoration.

## 7. Recovery: verified facts and stopping points

| Situation | Next safe step |
| --- | --- |
| Rockbox fails but the boot selector works | Select HiBy Player; check card layout and restore a complete known matching `.rockbox` from the computer. |
| HiBy Player works | Use the documented normal updater with the verified restoration image. |
| The normal updater cannot be reached | Confirm the forced-update sequence for the exact firmware/model with HiBy or the maintainer before attempting it. |
| Update hangs, USB boot is required, or no known recovery image exists | Preserve the exact symptom/version and contact support; do not use unrelated recovery files or production tools. |

There is a real documentation conflict: the [release](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2)
says **Power + Volume Up**; HiBy's [manual](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/)
also assigns Volume Up at startup to forced update in section 2, but section 9
says **Play/Pause + Power**. These are attributed source statements, not two
interchangeable instructions to try. We cannot settle their applicability
without the unit/firmware and confirmation. The manual describes a long Power
hold of at least ten seconds as hardware reset; this is not firmware restoration
and must not be used to interrupt an update deliberately.

Current upstream has [X1600 USB recovery code](https://github.com/Rockbox/rockbox/blob/7d090f24b990ef54e3f9dc7eb2edba4865605471/utils/jztool/src/x1600.c),
but its package loader expects a stage-1 payload, `bootloader2.ucl` and
`bootloader-info.txt`. Bahusoid's hosted `bootloader.r1` is not established as
that recovery package. The `.r1` suffix alone proves no compatibility. The
generic jztool README mainly documents X1000 players and is not a complete R1
recovery recipe. No jztool, Zadig, NAND or factory-flash commands are recommended
here. Hardware recovery and accessibility of recovery screens remain untested.

## 8. Physical controls and the existing mapping editor

The [manufacturer's layout](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/guide/)
has Power, Volume +, Volume −, Play/Pause and Next on the right side; there is
**no physical Previous**. The local/upstream source declares `BUTTON_PREV` for
a shared mapping, which does not create a real button. Bahusoid uses a dedicated
R1 map. Do not apply its symbolic button names to the upstream R3 Pro II map.

Our package uses a different keymap from Bahusoid's application. See
`HIBY-R1-CONTROLS.md` for current bindings, chords and safe Power handling.
Summary for our clean default settings:

| Physical key | Lists/menus | While Playing Screen (WPS) |
| --- | --- | --- |
| Volume + / − | Short: previous / next item; hold adjusts volume. | Short and held presses adjust volume. |
| Play/Pause | Back; hold for main menu | Previous track; hold for rewind. |
| Next | Activate; hold for context menu | Next track; hold for fast forward. |
| Power | Activate / OK | Play/pause; holding does not open a menu and can request shutdown. |
| Power + Next | Do not use instead of plain Next. | Playback context menu; use briefly. |
| Power + Volume + | Lock/unlock | Lock/unlock; volume keys adjust volume directly while locked. |

These are source/documentation and host-test checks, not ergonomic hardware
validation. The historical [fork keymap](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/docs/mods/hibyr1-keymap.md)
describes its application, not our package. Our text reader has a separate
map in the controls guide. Avoid accidental long Power holds.

The existing [keyremap plugin](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/apps/plugins/keyremap.c)
already supports editing, testing, import/export, persistence and spoken list
callbacks. In the fork, use **Plugins → Applications → keyremap**, import a
text map prepared for that exact target, and test with **Temp Core Remap**
before **Set Core Remap**. The latter saves the active core mapping;
**Remove Core Remap** returns to the built-in mapping. Spoken callbacks do not
prove every edit/error path is accessible.

If a saved map makes navigation impossible, power off cleanly if possible and
use the card reader to move `/.rockbox/keyremap.kmf` into the dated backup, then
restart. Preserve its contents for diagnosis. Do not modify internal firmware
to undo a card remap. This source-supported fallback has not been tried on R1.
Physical remapping does not automatically remap boot/recovery menus, raw-button
plugins or all touchscreen gestures. Our package has separate spoken editors
under **System → Physical button settings** and
**Accessibility → Touch exploration settings → Gesture assignments**.
See `ACCESSIBILITY-BUTTONS.md` and `ACCESSIBILITY-TOUCH.md` for their behavior,
timed confirmation/rollback and recovery. Do not confuse their configuration
files with `keyremap.kmf`. They have not yet been accepted on a physical R1.

## 9. Our accessible gestures and validation limits

The fork's [touch controls](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/docs/mods/touch-controls.md)
include taps, scrolling and edge swipes. They do not establish TalkBack-like
exploration without activation, spoken focus, or global double-tap activation.
R1 runs Linux, not Android; installing TalkBack is not this implementation path.

Our package extends the shared core with exploration and configurable gestures.
Default bindings follow; see `ACCESSIBILITY-TOUCH.md` for details and limits:

| Gesture | Default semantic action |
| --- | --- |
| Swipe left | Up |
| Swipe right | Down |
| Swipe downward | Right |
| Swipe upward | Left |
| Double tap | Activate current focus |
| One continuous left-then-right stroke | Back |
| One continuous right-then-left stroke | Home |

Exploration announces the focused item in standard lists and the text reader
without activating it. The editor includes Unassigned and a twenty-second
confirmation/rollback trial. These are host-tested implementation features,
not acceptance of physical touch, gesture thresholds or global accessibility
of every plugin. No multitouch or completed TalkBack-style keyboard is assumed.
Retain physical-button access and the documented control-recovery procedure.

## 10. RAM, shared TTS and Bluetooth: realistic next steps

HiBy [specifies 64 MB RAM](https://guide.hiby.com/en/docs/products/audio_player/hiby_r1/spec/).
A developer's [physical R1 capture](https://github.com/ZanHZANG/hiby-r1-native-development/blob/e8b37d471d5caae5cc0548664f3576682c8c21d6/BUILD.md#memory)
reports `MemTotal=56936 kB` (55.60 MiB), `MemAvailable=37020 kB` (36.15 MiB),
`MemFree=14232 kB` (13.90 MiB) and no swap. This is another person's measurement
of one unspecified workload, not our measurement or guaranteed TTS headroom.
Available memory already accounts for reclaimable memory; do not add it to free
memory again. Rockbox's configured `memory=16` means a 15 MiB shared core arena,
not a 16 MiB limit on the Linux process or 64 MiB free for synthesis.

Shared `tts`, `talk`, voice queue/mixer, text navigation and bookmarks now
underpin the R1 prototype; see `ESPEAK-HIBYR1.md` for milestone details.
`tools/configure` permits integrated synthesis for the hosted R1 application,
and `lib/espeak/espeak.make` supports `APP_TYPE=hibyos`. Hosted atomic guards
replace reliance on Linux's no-op interrupt-disabling helpers. This does not
complete MIPS Linux validation: ABI, runtime, allocator, file paths, stack and
mixed wired PCM still need appropriate tests. The R1 SDL simulator checks UI
logic, not the actual hosted binary, RAM, radio, physical buttons or installation.
The whole fork was not merged into the working Sansa source tree.

Bahusoid's [Bluetooth notes](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/docs/mods/bluetooth-hiby-x1600.md)
and [implementation](https://github.com/bahusoid/rockbox/blob/94c69704e9cf8bae77240a98a8eb7bd5c576f426/apps/hiby_bluetooth.c)
use `bluetoothctl`, BlueALSA routing and vendor services, derived from
[bidhata's patches](https://github.com/bidhata/hiby-r1-rockbox-bt).
They include pairing/status/headset controls, but explicitly warn that powering
off headphones during playback crashes Rockbox and live codec switching is
unstable. The checked current branch retains these warnings. Device/codec
lists also lack speech callbacks in the examined code. No stable Bluetooth,
particular codec, accessible pairing or TTS over Bluetooth is promised.

Development order: confirm unit/firmware/recovery; pin individual backend
changes; validate shared wired TTS and the implemented physical mapping,
gestures and editors on the device; then investigate BT failures with real
hardware. Start BT validation with SBC and actual music-plus-speech routing,
spoken discovery/errors, headset power loss, reconnection, lock, reboot and
wired/wireless switching. Measure peak RSS/PSS, available RAM and battery under
the real workload before increasing the arena or claiming runtime benefits.

**Still required on a real R1:** installation/removal/recovery round trip,
both boot choices, every physical gesture/lock transition, synthesis and
cancel/pause/resume while music plays, PL/EN speech coverage, failure handling,
memory pressure, Bluetooth disconnect/reconnect and battery tests. These are
acceptance gates, not completed tests. Exact model/firmware and access to a test
device remain questions for the user before hardware-specific instructions.
