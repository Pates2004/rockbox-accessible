# HiBy R1: USB storage safety

## Current status

This project has not been tested on a physical R1. The user's future factory
firmware, automounter and service configuration are unknown. The default R1
build therefore **refuses writable USB mass-storage export**. This is a safety
restriction, not a successfully working USB transfer feature. There is no
"enable anyway" setting.

The inherited implementation kept the Linux filesystem mounted while exposing
its raw device to the computer. It also assigned the LUN before Rockbox threads
had acknowledged USB. Concurrent filesystem ownership can corrupt data. The
R1-specific guard no longer assigns the raw card device during mode setup or
ordinary USB enable calls. Other player targets are unchanged.

File-level transfer through ADB may eventually avoid repeated card removal,
but this change does not implement or validate an ADB updater. Do not replace
libraries or modules in a running Rockbox process without an established safe
update procedure. Keep recovery media and backups.

## Transaction contract

The native adapter currently implements checked gadget detachment and a
conservative local-card-directory readiness check only. Its configuration is
hardcoded as unverified; it has no real unmount/remount or automounter lease
adapter. The reusable, allocation-free transaction engine is exercised using
mocked operations, not the player's kernel.

Enabling the real capability requires a reviewed vendor-specific adapter that:

- Acquires continuous exclusive control over all relevant automounters,
  processes/namespaces and gadget reconfiguration, and retains it through
  export and restoration. A mount snapshot is not such a lease.
- Captures the actual block identity, complete filesystem mount options and
  mount location; rejects ambiguous observations and overlapping/bind mounts.
- Closes local resources, synchronizes and performs a normal unmount. Never
  use lazy/forced unmount, or share a writable filesystem with the USB host.
- Verifies detachment, LUN writes and UDC binding, including write/read/close
  failures and readback. Rechecks the lease and overlapping mounts.
- Detaches the host and releases the LUN before restoring the exact saved
  filesystem/options. Unsafe recovery must keep Rockbox file users suspended.

The loader copies the application to `/tmp`, but its pinned version searches
the SD card for libraries. Hosted codecs/plugins also use dynamic loading.
Those mappings may prevent a normal unmount; an executable in RAM is not
proof that the card is free. A verified deployment may need reviewed RAM
staging of dependencies or a different update method.

## Parent integration API

Header: `firmware/target/hosted/hiby/usb-storage-hiby.h`.

`hiby_usb_storage_target_prepare()`, `hiby_usb_storage_target_export()`,
`hiby_usb_storage_target_restore()` and `hiby_usb_storage_target_status()`
return a `struct hiby_usb_storage_status` value. Fields are `success`,
`safe_to_resume`, `error`, `system_error`, `recovery_error`, `state` and
`configuration_verified`. `hiby_usb_storage_target_safe_to_resume()` returns
the current local-resume safety result. `system_error` and `recovery_error`
contain positive errno values; `error` identifies the failing transaction stage.

The default preparation fails with `HIBY_USB_STORAGE_ERROR_UNVERIFIED`.
`safe_to_resume` is true only after checked detach and local readiness, never
because preparation failed. A successful restore means local recovery, **not**
a successful USB transfer. The target status getter retains the last failure
across successful cleanup/settings reapplication until the next preparation.

The coordinator must wire the private USB transition, both ACK/zero-ACK callers,
disconnect/recovery handling and an accessible PL/EN application message.
Exclusive success must not be advertised after a failure. Safe failure can
release waiting threads; unsafe recovery cannot emit a mount-ready broadcast.
Snapshot the retained target status immediately after `handle_usb_events`,
before `settings_apply`. Report that error only after fonts/settings have
been safely restored.
Firmware must not invoke TTS. An error during unsafe recovery cannot depend
on files from the unavailable card.

## Validation limits

Mock tests validate the transaction and R1 gadget guards without mounting,
writing sysfs or touching a player. They do not establish actual USB transfer,
vendor quiescence, filesystem power-loss safety or physical accessibility.
No bootloader or factory firmware modification is part of this change.
