# HiBy R1: Wi-Fi, shutdown and energy

[Polski](HIBY-R1-POWER-PL.md)

## Wi-Fi

This build explicitly requests a Linux `rfkill` transmitter block for **WLAN**
and takes `wlan0` and `wlan1` down when present. It checks state by readback.
This happens once at main-application startup, not in each audio-helper
instance; there is no periodic network scan.

It does not block Bluetooth or all radio types, unload the combined Wi-Fi/BT
driver, or cut the shared chip supply. It does not run a blanket `killall` or
delete manufacturer Wi-Fi credentials/configuration. Merely having Linux or
no network client in Rockbox did not establish that inherited Wi-Fi was off.

Radio controls are in **Settings → Connectivity**:
[preferences, observed state and airplane mode](HIBY-R1-CONNECTIVITY.md).
The startup diagnostic remains in **System → Debug → Wi-Fi status at startup**.
This self-voicing screen is a **startup snapshot**, not continuous monitoring
or a current measurement. It shows the block result, WLAN entry count,
confirmed inactive interfaces and control error codes:

- **Confirmed:** observed WLAN entries reported a transmitter block.
- **No radio entry; block unconfirmed:** no WLAN entry appeared in `rfkill`.
  This does not prove missing hardware or removal of its supply.
- **Wi-Fi disable not confirmed:** control failed or the driver provided no
  confirmation. A startup message also reports this condition.
- **Unavailable in this build:** the simulator does not control computer radios
  or present zero values as hardware measurements.

Error code `0` means no recorded error from that operation, not independent
proof of power removal. Report every row when the state is unconfirmed.
Rockbox still starts; missing confirmation is not hidden. Another privileged
program may later change the block, which this snapshot cannot detect.
There is no NAS client. Connectivity can enable WLAN administratively; this
does not mean a network connection. The inspected driver rfkill callback stores
a software flag, so a block does not establish electrical radio power removal.

A transmitter block is not a current measurement or a promise to physically
disconnect the complete chip. [Linux rfkill documentation](https://www.kernel.org/doc/html/latest/driver-api/rfkill.html).

## Whole-device shutdown

Shutdown follows normal Rockbox cleanup: save settings/state, stop playback
and finish owned services. On R1 it must not merely exit the application or
blank the screen.

The backend synchronizes filesystems and starts `/sbin/poweroff` without a
shell. The manufacturer's `init` gets up to 30 seconds to finish services and
unmount filesystems. If the device is still running, the backend synchronizes
again and requests kernel poweroff through `RB_POWER_OFF`. Waiting is bounded;
it no longer uses the old endless one-millisecond CPU wake loop. The child
is tracked and cleaned up within available OS operations.
Concurrent requests from the main thread and shutdown watchdog do not start
a second procedure: poweroff is serialized.
R1 also leaves `SIGTERM` at its normal termination action: the manufacturer's
shutdown must not be mistaken for a crash and redirected into a panic/reboot.
This bounds application loops: a blocked kernel call, such as a broken driver
or filesystem synchronization, can still prevent completion within that time.

If kernel poweroff also returns with an error, the display is restored and a
`Power off failed` panic presents codes. The device is not falsely reported
as off. Record the codes; hardware force-off remains device-dependent.
Display recovery also disables curtain. This fatal message may no longer have
speech because normal cleanup already closed audio; post-audio-close panic
speech is not promised.
The R1 panic button-wait loop sleeps between reads rather than spinning at
full CPU speed. It is still an error screen, not a successful shutdown.
[reboot(2) reference](https://www.man7.org/linux/man-pages/man2/reboot.2.html).

Default longer Power holding remains firmware-controlled. In the keyboard,
the first hold finishes typing: release then unless you intend to continue
requesting shutdown. The accessibility Power off action uses the same cleanup
route. Curtain, keylock and backlight-off are not device poweroff.

No new UPT flash is required. Update `.rockbox` on the card of an already
modified R1, following the installation guide.

## Tests and limits

Tests replace OS operations with controlled fakes: failures, short I/O,
interruptions, descriptor/child cleanup, preservation of Bluetooth, bounded
waiting and failed-poweroff reporting. They do not shut down the computer,
alter its networks or measure a physical R1.

The keyboard avoids needless full-screen redraws every 50 ms while idle;
visible caret blinking and active input still update. Dark colors do not
guarantee LCD savings. Curtain retains touch and does not promise panel power
removal. No invented runtime improvement or whole-device zero-leak result
is reported.

Hardware acceptance must separately check startup, Wi-Fi state, BT, audio
with speech, lock/curtain, poweroff and subsequent startup. Also test shutdown
without USB: charging and power-triggered wake can change hardware behavior.
A black screen or LED is not a current measurement. Compare runtime under
matching conditions. See `HIBY-R1-CONTROLS.md`, `INTERFACE-APPEARANCE.md`
and `HIBY-R1-NETWORK-EMULATION.md`.
