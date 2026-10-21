# HiBy R1 connectivity

## Bootloader-suspended drivers

The supplied modified 1.8b2 firmware detaches the WLAN SDIO function before
starting Rockbox and may also suspend the Bluetooth controller. Missing WLAN
interfaces after this handoff do not mean Wi-Fi was compiled out. The previous
backend did not distinguish that state and tried BlueZ commands against a
Bluetooth controller that could already be rfkill-blocked.

The new **Wi-Fi driver suspended** state requires positive identification of
the supported device/driver layout. Query and Disable do not wake it. Only an
explicit Enable request may reattach the verified WLAN function, without
reloading the shared combo module or joining a remembered network. Unknown
hardware revisions or inconsistent evidence require a device report rather
than guessing a bus function. This does not require another firmware flash.

The captured R1 startup report identifies both SDIO functions as
`02d0:a9a6`, with function 1 on `bcmsdh_sdmmc` and function 2 detached.
The reported module-link read was unavailable; that alone does not prove a
built-in driver or an absent link. For this exact device only, the backend can
recognize the handoff without module linkage after independently confirming
that the link itself is absent. Dangling links, access errors, mismatched
identities and unexpected drivers still fail the checks. Other device IDs
continue to require the original module identity check.

A complete, consistent blocked Bluetooth-type rfkill snapshot can establish
the disabled administrative state without a BlueZ controller. Missing entries
or read errors cannot. Enable still requires real resume and fresh controller
readback; selecting On is not itself confirmation. Wired routing restoration,
operation failures and cancellation remain effective.

Radio mutations have a bounded wait and track their owned helper process. An
unsettled child cannot count as a completed transition or permit premature
Bluetooth re-enabling, including after an incomplete airplane-mode operation.
The startup handoff above is observed on a physical R1. Reattaching WLAN,
Bluetooth pairing/streaming and physical power behavior still require device
testing; controlled probes and Windows simulation do not establish acceptance.

Detached drivers, interface-down and software rfkill states are not electrical
RF-off or battery measurements. Off below refers to observed administrative
state, not a guarantee of zero RF emissions. The simulator never controls host
radios.

Settings → Connectivity groups Wi-Fi, Bluetooth and Airplane mode. The former
General Settings Bluetooth entry and System startup Wi-Fi entry are removed.
The startup WLAN diagnostic remains available in System → Debug. This is an
experimental application interface to the supplied HiBy Linux firmware, not a
replacement radio driver. Windows simulation never controls the PC's radios.

This edition corrects both radio workers to respect the platform's pthread
minimum stack (128 KiB on the supplied R1 runtime). The old 64 KiB request could
fail before either worker started. Connectivity remains browsable after a
worker initialization failure, displaying unknown/error states and allowing
explicit retry rather than making the whole menu inaccessible.

## Preferences and observed state

On a clean profile both radios and airplane mode are initially disabled.
`/.rockbox/connectivity.cfg` stores requested radio states and airplane mode,
separately from the shared Rockbox settings layout. Startup enforces the requested
states; Bluetooth policy is applied only after audio initialization. Early WLAN
disable is retained before preferences can be loaded. An initial zero in a
cache is never proof that a vendor radio was powered off.

Turning airplane mode on requests both radios off and rejects Bluetooth enable,
scan and connect requests. Turning it off restores the previous requested
Wi-Fi/Bluetooth states. The user's two radio preferences are retained during
airplane mode, rather than overwritten by temporary off states. A failed radio
operation, cancellation, incomplete readback or storage failure is not presented
as a fully successful transition. Reopen state/status or retry after a failure;
do not assume that a failed operation left every component unchanged.

Operations use bounded workers and explicit state reads, not continuous idle
polling. Cancelling an operation requests cleanup; another power transition must
wait for the earlier operation to settle, or report busy/timeout. A late enable
must not escape an airplane-mode admission gate. Some vendor commands may have
already changed persistent pairing state before cancellation.

## Wi-Fi

The initial submenu only controls the administrative WLAN enabled state. Enable
unblocks WLAN-specific rfkill entries and raises the WLAN interfaces; disable
blocks those entries and lowers the interfaces, followed by fresh readback.
If the character-device rfkill API is missing, a bounded sysfs fallback reads
and writes WLAN entries only. It never writes Bluetooth attributes or hard-block
state. Each radio directory is held open while checking its type and accessing
attributes, avoiding redirection to a reused rfkill name.
It does not block Bluetooth or unload the shared combo driver. Missing rfkill
entries, read errors and hardware blocks are not treated as confirmed success.

This does not configure a network, validate credentials, join an access point or
provide a NAS/radio/podcast/YouTube client. Those are separate work. Existing
vendor services may also affect the interfaces. In the inspected firmware the
WLAN rfkill callback stores a software flag; an acknowledged block is not proof
of electrical power removal, zero RF activity or a particular battery saving.
An interface confirmed down without radio readback is explicitly announced as
“Wi-Fi interface down; radio state unconfirmed”, not as confirmed radio Off.
Actual control errors have a separate failure announcement. The startup notice
describes the early startup snapshot; use Connectivity for a fresh observation.

## Bluetooth

One on/off choice replaces the separate enable/disable commands. Paired devices,
pairing a new device, disconnect and status are grouped below it. Scanning and
connecting require explicitly enabled Bluetooth; passive refresh never silently
powers it on. Power readback must be complete, not an old cached flag.

Temporary inhibition during startup, cancellation or cleanup is reported as a
connectivity restriction, not as proof that airplane mode is enabled. The
instruction to disable airplane mode applies only when that mode is actually on.

Music and speech share the Rockbox mixer and PCM route. See
[Bluetooth and audio](ESPEAK-BLUETOOTH.md) for cancellation, PIN, routing, vendor
tool requirements and limitations. No promise of a usable microphone, headset
buttons, selectable codecs or multipoint is added by this settings organization.

## Startup state and Bluetooth waiting

Disabled in software is an observed administrative state, not an installation
failure. The supplied launcher normally suspends Bluetooth and a clean Rockbox
profile requests it off. The former Administratively disabled described this
same state, not a permanent inability to enable Bluetooth.

Successful passive refresh on entering Connectivity no longer announces Done
over its first Wi-Fi row. Real unavailable/error states remain spoken. Bluetooth
power changes leave the menu browsable while the bounded worker runs. Another
activation while busy reports Busy instead of starting a second change.
Cancellation requests cleanup and preserves settling/admission checks. Navigation
can interrupt status speech, but is not discarded by a silent modal wait.

The inspected Broadcom branch of the vendor resume script has explicit waits
totalling about ten seconds plus controller/service work. Enabling has been
reported to finish on an R1 after at least several seconds, not a controlled
timing benchmark or proof of pairing/audio. This revision skips the doomed
pre-resume power command only after positive suspension readback. It avoids
redundant refresh after a successful, available, known-power result, except
when an active connected audio route still needs checking. Vendor safety waits
remain; physical timing and speech continuity need another device test.

## Acceptance limits

A separate passive diagnostic kit is provided in
`installfiles/diagnostics/hibyr1-connectivity`; its source and instructions live
in `tools/diagnostics/hiby_r1_connectivity`. Check is the default and reads the
explicitly identified card without modifying it. Enable and Restore require
confirmation; do not nest it with the older alpha8 audio logger. The kit accepts
only the recognized alpha8/alpha9 applications and matched ALSA runtime, not an
arbitrary new build. It collects a bounded startup hardware/service snapshot,
not passwords, the user profile or proof of working Bluetooth. Use the matching
instructions and restore the launcher before updating the application.

Mocked host tests can check state policy, restoration, errors and resources;
Windows can check navigation and spoken unavailable states. Neither verifies
physical R1 Wi-Fi/Bluetooth, full vendor startup, actual RF power, headset audio
or energy consumption. Until tested on the player, airplane mode is a best-effort
administrative policy, not a certified radio-silence or aviation guarantee.
