HiBy R1 passive connectivity diagnostics

This standalone kit is separate from the alpha8 audio diagnostic kit. It is
not a firmware update or an application release. Keep the existing audio kit
matched to its original application.

Use after the card is connected and identified. The R1 must be completely off
before removing its card. Keep the kit on a writable computer drive, outside
the card. Reports stay beside this script in Reports. Do not use an old drive
letter without checking the newly connected card. No card backup is needed.

Windows PowerShell 5.1, keyboard and NVDA

Start.cmd opens a plain text menu: type a number and Enter. Enter alone selects
Check; 0 exits. No mouse, global input injection, focus switching or host radio
operation is used. For English, start: Start.cmd -Language en
The default language is Polish. To run commands directly in PowerShell:

  .\Connectivity-diagnostics.ps1 -Language en -CardRoot F:\
  .\Connectivity-diagnostics.ps1 -Language en -Mode Enable -CardRoot F:\
  .\Connectivity-diagnostics.ps1 -Language en -Mode Collect -CardRoot F:\
  .\Connectivity-diagnostics.ps1 -Language en -Mode Restore -CardRoot F:\

Replace F:\ with the identified removable card root. UNC paths, subfolders,
the system drive, linked paths and junctions are rejected. Fixed USB drives
are deliberately rejected; do not work around this with a link. Enable and
Restore require typing exactly YES (TAK in Polish). Other input cancels.
The PowerShell script uses UTF-8 with a BOM so Windows PowerShell 5.1 reads
Polish characters correctly. Preserve the BOM when editing or relocating it.
Menus, confirmations, errors and report warnings follow -Language pl or en.

Check (default) only reads the card, writes a small report in the kit Reports,
and lists application/runtime hashes and audio-diagnostic conflicts. It does
not read settings, resumes, credentials, bookmarks or paired devices.

If audio logging is active, Check remains useful, but Enable refuses. First
run Restore using the existing MATCHED alpha8 AUDIO kit. Never stack these
launchers or rebind that audio kit to alpha9. Reconnect and Check again.

Enable recognizes these original applications only:
alpha8: 7d82d50b88e0bfc3f0fe7bc6882843d047128d5504fc10bbdc72664119058390
alpha9: a536942c7cc6caa68c6dae24c2128e9d623562e2e26e7df10fdb51539684e122
ALSA:   e7dd65afbb4209ffda6edea998cd0f4116fe166eb859939553ac6840f964f8ed

The alpha9 app hash was streamed from the current native archive with SHA256
5ff3a5767695e7750ee74792ecd802da9c80399ca2d50478816967e36a1fcda3.
Other versions require a reviewed future kit. No arbitrary hash override exists
for any card. The strict test environment seam only changes drive-root policy,
confined to the central radio-diagnostics/tests area and a matching script,
card directory and marker. Tests use real published application/runtime bytes.

The original is MOVED on the SAME card from .rockbox/rockbox.r1 to
.rockbox/rockbox.r1.connectivity-original, never backed up or copied to the PC.
The validated shell launcher replaces rockbox.r1 after staging. Diagnostic
state records the full original hash and every adjacent .so runtime hash.
No profile, gain, autostart, rb_bt_on.txt, firmware or radio setting is changed.
Existing unexpected diagnostic files cause refusal, never overwrite.

Boot once, allow Rockbox to start, then shut the R1 down normally. The bootloader
copies the launcher to /tmp with only LD_LIBRARY_PATH; therefore it cannot
locate itself via $0. The launcher uses the known card directory. It validates
the original hash, copies the actual original into a unique private /tmp
directory, checks the staged hash and executes it, allowing a noexec card.
This temporary runtime copy is necessary for execution and survives until
reboot after successful exec. Startup failures remove only their own private
staging files. Application output is not redirected into diagnostic logs.

The passive snapshot is taken ONCE, before the application, and only if no
r1-connectivity.log already exists. It is capped at 64 KiB; individual field
reads are at most 256 bytes. It checks up to 16 actual rfkill entries and their
type/name/soft/hard/state, fixed SDIO functions mmc0:0001:1 and mmc0:0001:2
(vendor/device/class/driver/module link targets), wlan0/wlan1 existence and
flags, up to 256 process comm names filtered to Bluetooth services, hciattach
and brcm_patchram, /run/r1_wireless_type and /dev/rfkill metadata. The inspected
rootfs has no stat utility, so metadata uses bounded numeric ls -ldn (a stat
operation, never opening the radio device). No device
rfkill stream or ioctl is read. No CLI radio control is invoked. Optional
bluetoothctl show runs only through the fixed rootfs BusyBox timeout with a
3-second SIGKILL limit and at most 4096 output bytes, when both tools exist.
Otherwise the log explicitly records the skipped query. The inspected vendor
BusyBox 1.31.1 has no timeout applet, so that query is skipped on this rootfs.
The dd options were checked using actual vendor help and private files.
Missing hardware is recorded as unavailable,
not as successful power-off. There is no background poller.

The confirmed vendor 1.8b2 bootloader calls wifi_down, unbinds SDIO function 2
and suspends Bluetooth unless .rockbox/rb_bt_on.txt exists. This pre-application
snapshot can reveal that handoff and hardware identity, but does not establish
electrical RF power, successful recovery or physical radio operation.

Collect copies ONLY the existing diagnostic log (maximum 64 KiB) into a fresh
Reports subdirectory, verifies hashes, and leaves the card unchanged. This
useful extra log copy remains for diagnosis; no card/profile copy is created.

Restore verifies the original, launcher, state and complete captured runtime
file set before changing anything. It moves the launcher, log and state into
a fresh Reports folder and moves the original back to rockbox.r1. Move failures
roll back completed operations; never manually delete an unexpected file to
force restoration. Staged interruptions on either side of the original move
can also be restored with the recorded state. A power failure or filesystem
damage can still require manual review; retain all evidence and report errors.

Validation covers actual PowerShell 5.1 on synthetic card directories and the
shell with confined fake utilities and synthetic sysfs/process data. Hardware
R1, real bootloader startup, physical radios and live NVDA reading remain
unverified. Never interpret host tests as physical acceptance.
