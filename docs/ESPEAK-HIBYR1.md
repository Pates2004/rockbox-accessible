# Integrated eSpeak on HiBy R1 — development build

Source update 2026-10-21: the public development branch includes the five list
position modes and ongoing Bluetooth hardening, with plugin ABI `0xe006`.
Publishing source is not a new accepted native/Windows binary release. The dated
alpha12 and earlier sections below are historical package descriptions; use
the exact manifest/ABI of any installed package, never mix its modules with a
new build. Public compilation starts with [Build instructions](BUILD-ACCESSIBLE.md).

The `r34-alpha12-20261019` test edition consistently presents pitch, modulation
and volume as percentages, includes the new Polish dictionary, and corrects
eSpeak/Sonic allocation-failure handling and bounded Bluetooth command retries.
Stored parameter values and basic controls remain unchanged. The separate
[network review](HIBY-R1-NETWORK-EMULATION.md) describes internet radio,
podcasts and library services as planned work, not working features of this
edition.

It retains the earlier Connectivity/Bluetooth worker stack corrections and
audio initialization fix:
the R1 system library rejected a 64 KiB stack because it requires at least
128 KiB. The backend now respects the platform minimum. A clean native R1
package also starts at actual -25 dB (`volume: -250`), rather than -2.5 dB.
This update does not require reflashing firmware or formatting the card.
Library/build checks do not replace listening on the physical device.

The edition retains the extended gesture editor with triple tap
(unassigned by default), double tap and hold (Context menu), configurable touch
hold time and optional safe held-stroke repetition. Unassigned triple taps never
activate the double-tap action. Date, playback/device summary, touch-browsing
toggle and direct core-screen destinations are assignable too. See
[touchscreen settings](ACCESSIBILITY-TOUCH.md) and [buttons](ACCESSIBILITY-BUTTONS.md).
The existing radio controls remain under
Settings → Connectivity and restore prior radio preferences after airplane mode,
and adds separately assignable eSpeak/voice-file toggles with synthesized status.
See [connectivity](HIBY-R1-CONNECTIVITY.md) and
[service controls](ACCESSIBILITY-SHORTCUT.md). This test edition retains Polish
and speech on; English/speech-off and default triple Power are for a later public
release. Physical touchscreen timing and usability still require device tests.

This target reuses our shared eSpeak 1.44.05 r34, speech queue, text reader and
text/audio bookmark integration. It is not a rewritten reader or a substitute
system synthesizer. The R1 build is a Linux application, not bare-metal firmware.

Battery life and available RAM have not been measured on the native device
by this project. A successful MIPS build or Windows simulator is not hardware
acceptance. The core arena remains 15 MiB; the device's nominal 64 MB is not a
promise of 64 MB for Rockbox. The engine uses the existing bounded 1.5 MiB pool
and Unicode/file adapter without requiring a device UTF-8 locale or libstdc++.

Current hardening adds a WLAN-only startup block/readback, bounded whole-device
shutdown, default-button descriptions/guide, and dark/light core color presets.
See `HIBY-R1-POWER.md`, `HIBY-R1-CONTROLS.md` and `INTERFACE-APPEARANCE.md` for
behavior and explicit physical-test/skin limits. Keyboard idle redraws and
specific Bluetooth/framebuffer lifetime failures are also corrected.

The `r34-alpha5-20261015` release adds assignable time speech and configurable
lock/unlock announcements. See `ACCESSIBILITY-SCREEN.md` for the choices and
the existing shared automatic-lock/backlight timeout. It is an experimental package for device
tests, not acceptance of every hardware feature. The firmware installed on
your unit is unknown; arbitrary firmware transitions and Bluetooth/USB vendor
service compatibility are not guaranteed.

See `HIBY-R1-CONTROLS.md` for the physical profile and Windows keys, and
`HIBY-R1-INSTALL.md` for installation and removal boundaries. The Windows release
belongs to `D:\Rockbox\rockbox\installfiles\simwindows-hibyr1`; it is **not** a
file to install on the player. Sansa builds remain in their separate locations.

## Updating after Cannot open ctl

The first alpha1 hardware attempt panicked with `Cannot open ctl` while opening
the mixer, before speech. Bundled ALSA 1.0.26 does not accept the `hint` field
in the hardware-control configuration shipped by newer HiBy firmware. Alpha2
opens card 0 controls with a private minimal in-memory configuration, without
changing the vendor system or disabling hardware volume controls. Any further
open failure reports the device, ALSA error code and description. This is a
fix for retesting, not acceptance of the complete physical player.

If the loader already starts Rockbox, **do not reflash firmware**: switch off
the player and extract the whole new `.rockbox` package into the card root,
replacing matching program files. Back up your settings and bookmarks first;
the package contains clean defaults, not your profile. Do not copy `r1.upt`
to the card or downgrade to 1.6 for this fix.

For a **clean-settings test**, overwriting files alone is insufficient:
`config.cfg.new` and private accessibility settings may remain. With Rockbox
stopped, retain the whole previous `.rockbox`, for example by renaming it to an
unused `.rockbox-backup`, then extract the package into a new `.rockbox`.
Do not merge those folders or restore the previous profile for a clean test.
Keep bookmarks and personal files backed up; never remove or change files on
the mounted card while Rockbox is using it.

## First installation and automatic startup

1. Only for the original **HiBy R1**, not R1 MIDI or R3. Back up the card and
   obtain an appropriate original recovery firmware before the first flash.
2. Extract our `rockbox-hibyr1-espeak-r34-alpha12-20261019-hardware-test.zip` into
   the card root, directly creating `.rockbox/rockbox.r1`.
3. Separately extract `installfiles/fw-rockbox/hibyr1_1.8b2_bahusoid_rb_26.09.17.zip`.
   Put its `r1.upt` in the same card root. This installs the modified **1.8b2**
   system; it is not a speech update or a promise to preserve your current version.
4. After checking the update transition, use stock
   **System → Firmware update → TF/SD-card update**. Do not turn off the player
   or remove the card during flashing. Our eSpeak cannot voice the stock updater;
   assistance may be necessary for the first installation.
5. No OS selection is needed after restarting. The package seeds a fresh binary
   Rockbox choice in `.rockbox/rb_bl_mode.txt`; the inspected loader counts down
   about one second before launching the application. That is the selector delay,
   not total power-on-to-speech time. The selector may appear briefly. We do not
   modify the UPT merely to hide it.
6. After a successful flash remove `r1.upt` from the card, retaining the original
   downloaded ZIP on the computer. Later `.rockbox` updates normally need no UPT
   reflash. Do not mix modules from unrelated builds.

Original-player selection, recovery and exact checksums: `HIBY-R1-INSTALL.md`.
The device package belongs in `installfiles/hibyr1`; Windows EXE stays on the PC.

## Windows simulator and sources

The Windows release also includes `SOURCE-hibyr1-windows-espeak-r34-alpha15-20261019.tar.gz`
with the corresponding Rockbox patches, supplied eSpeak sources/data and build
helpers. Keep it with the binary when redistributing; it is not a device image.

The optional `--debugaudio` simulator argument writes an additional
`audiodebug.raw` beside the program; no trace is created without that argument.
It contains played music and speech, so share it deliberately. The trace omits
idle output spans and does not share byte offsets with the complete SDL disk
driver output. It is not a recording from the physical player.

Enable speech synthesis and Speech volume are the eSpeak controls. Use voice
files to read the interface, Voice file volume and directory/file reading
modes affect prerecorded speech only, including when disabled or set to zero.
The Windows prototype uses the same shared speech policy as the Sansa builds.

Do not copy Sansa, stock or Bahusoid plugins/codecs into this build. Our plugin
ABI for these development sources is `0xe006`; the R1 target ID is 124. Replace the complete matching card
package for an update, not only the application executable.

The shared core now implements semantic gestures and non-activating exploration
for standard lists and the text reader. The gesture editor includes Unassigned,
atomic private configuration and a twenty-second confirmation/rollback trial.
See `ACCESSIBILITY-TOUCH.md` for mappings, recovery and raw-plugin limitations.
Unassigned gestures execute no assigned action. The separate physical editor
is described in `ACCESSIBILITY-BUTTONS.md`: single, double and triple press,
plus hold with one shared hold time. Unassigned restores the button's intrinsic
role, especially volume control; a separate choice retains default Rockbox
navigation. Neither option is Key Remap's consumed ACTION_NONE.
Host tests do not establish physical touchscreen thresholds or usability.

The HiBy-specific Bluetooth controller is separate from the speech engine;
its real ALSA/service compatibility and headset behavior need device tests.
Windows explicitly reports Bluetooth unavailable rather than simulating a
successful connection. Do not infer native Bluetooth support from SDL speech.

Native R1 defaults to charge-only USB. The new guard refuses writable card
export until exclusive ownership of the vendor automounter and safe unmount
and recovery have been verified. The inherited code exported a card still
mounted by Linux; it is not a safe alternative. Refusal does not establish
working USB transfer. See `ESPEAK-HIBY-USB.md` for details and test limits.
ADB/file-level updates are a separate possible route, not an already-tested
updater. The installation guide remains conditional. Initial installation needs
firmware containing the loader; our preference file then suffices for autostart.
No further loader or UPT modification is required to avoid manually choosing
an OS. This does not promise that the selector itself disappears.

This build does not add a recorder to hardware with no supported recording
path. Installation still needs a compatible loader and stock restoration plan;
no loader/UPT flashing is performed by our build tools.

Accessibility begins with Talkbox settings, whose eSpeak settings child contains
only engine parameters. Reader, touch, typing and display controls are alongside
it under Talkbox. Physical button settings remain in System. Voice language “Follow system language” follows Rockbox's
interface language, retaining the English fallback for unavailable voices.

Settings → General Settings → System → Interface sounds includes “Interface sounds for”:
any subset of buttons, gestures and exploration, including None and All inputs
(fresh default). A fresh profile uses moderate strength; saved silence is not
overridden. Shared strength Off silences all sources. Explicit old source
choices retain their meanings. Exploration clicks on a new target or contact,
not on coordinate jitter. Empty-target pitch is separately adjustable. Touch
exploration settings adds three empty-target modes: sound only (default), sound
and speech, or speech only. Sound only with interface sounds disabled is silent.

General Touchscreen settings and Physical button settings are now System
children. The former adds gesture sensitivity, any-button unlocking and physical
controls while touch is locked. The two lock policies default Off. Typing
settings adds character/word echo, capital announcements and deletion echo.
There is no separate accessibility-shortcut submenu; map the direct speech
toggle actions in button or gesture assignments.

If the card still has the alpha8 audio diagnostic launcher, restore that launcher
with its matching alpha8 tool before replacing the application. Do not use a
newer manifest to restore an older wrapped application. No card is modified by
building this edition; no new UPT flash is needed for an already working loader.

## Typing, curtain and this update

Accessibility → Talkbox settings offers **Typing settings** and, under its
**Screen settings** child, **Screen curtain**.
`ACCESSIBILITY-TYPING.md` explains lift-to-type, double-tap and arrow navigation;
`ACCESSIBILITY-CURTAIN.md` explains the temporary black screen and recovery.
Assignment choices explicitly say **Up/Down/Left/Right arrow**, separately from
the names of finger gestures. The curtain starts off after every restart.

This update retains the alpha2 private mixer configuration fix, adds checked
mixer allocation failures and Bluetooth status/timeout/recovery hardening, and
uses the latest supplied Polish dictionary data. These changes do not require
another `r1.upt` update. Hardware testing is still required; Windows does not
provide a physical Bluetooth adapter for this port.

`HIBY-R1-NETWORK-EMULATION.md` separates researched NAS/Wi-Fi and emulator
possibilities from implemented functions. This package does not add a NAS client,
GBA/DS/3DS/Wii emulators or an automatic accessible Pokémon Lua adapter.
