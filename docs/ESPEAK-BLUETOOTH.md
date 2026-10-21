# HiBy Bluetooth and shared speech audio

## Routing and reconnection

A successful explicit **Connect** switches the entire Rockbox mix, including
music and Talkbox, to the selected Bluetooth headphones even if the wired jack
is inserted. It is one selected PCM route, not separate speech/music outputs.
Connecting by BlueZ alone does not prove that the matching BlueALSA endpoint
or Rockbox audio route is ready. Failed switching preserves the previous route.

Automatic PCM recovery captures the route-intent generation together with its
target and checks it under the routing/state locks before opening an output.
A stale retry cannot overwrite a newer accepted manual selection, including
the wired fallback after a failed Bluetooth recovery. This protects output
selection; it is not automatic headset reconnection.

Bluetooth settings provide automatic connection Off, When Bluetooth starts, or
When Bluetooth starts and after connection loss. The last option is the default;
the radio itself still defaults to off. Only a successfully manually selected
device is remembered. Automatic attempts require that BlueZ still confirms that
exact device as paired and trusted; they never pair, acquire trust, scan or turn
on the radio. An incoming manufacturer-service connection is not automatically
adopted as a different Rockbox output.

The retry time limit is 30, 60, 120 or 300 seconds, initially 120. There are at
most eight attempts, with increasing delays and a maximum 15-second budget for
each automatic operation, also capped by the remaining window. A failed attempt
does not restart the window. Disconnect, Forget, cancellation, airplane mode,
radio off and shutdown stop automatic recovery. After manual Disconnect, use an
explicit connection or turn Bluetooth off and on to permit a new session.

After an unexpected connection/output loss the default is to pause music and
restore the shared wired output, allowing Talkbox to speak there. The alternative
is to continue on wired output. Reconnection does not automatically resume paused
music. There can be a short buffer on wired output before the registered policy
thread pauses music; this is not a zero-sample privacy guarantee. Wired output
can itself fail. Physical handover and reconnection still require R1 tests.

## Current acceptance status

The HiBy R1 Bluetooth controller and vendor-command adapter are implemented,
but native R1 Bluetooth is **diagnostic, not hardware-accepted**. The current
version has not passed physical headset/routing acceptance. Host tests exercise the actual C adapter against compiled
command fixtures and the actual worker against controlled backend operations;
they do not demonstrate a radio, headphone connection, battery life or sound.
The Windows simulator explicitly reports Bluetooth unavailable. It does not
pretend to pair or use the computer's Bluetooth stack.

Routing acceptance is a separate requirement. A BlueZ connection alone is not
success: the backend verifies the connected property, the matching BlueALSA
source endpoint and the shared PCM route before reporting success. The R1/eSpeak
build selects a separate, isolated PCM driver; other hosted targets retain their
existing driver. Host verification is not vendor-plugin or hardware acceptance.
`SND_PCM_NONBLOCK` alone does not bound plugin open, configuration or close.

## Controls and speech

Settings → Connectivity → Bluetooth provides one power switch, Paired devices,
Pair a new device, Disconnect, Status, Bluetooth settings and Connect last selected
device. Forget requires confirmation, with Keep paired device selected first.
The settings include retry behavior, loss behavior and optional connection-change
announcements, plus the remembered address. Preferences are stored separately in
`.rockbox/bluetooth.cfg`, not the shared plugin-visible settings structure.
The paired list is refreshed separately;
new pairing shows unpaired scan results. Device actions offer the appropriate
connect/remove operations. Scan, connect and refresh never silently power on
Bluetooth. Names and
paired status are spoken; operation results, cancellation and errors use the
same localized interface speech as Rockbox. Search is bounded; use Back to
cancel an operation. A cancellation request returns control to the menu while
the worker finishes cancellation; a second request is rejected while busy.

Startup policy explicitly applies the saved radio preference after audio is
initialized; the clean default is disabled. Airplane mode disables both radios;
leaving it restores earlier preferences. Saving a request does not establish
its effect: [requested versus observed state](HIBY-R1-CONNECTIVITY.md).
Disabling verifies that BlueZ reports the controller powered
off. Pairing uses the firmware's existing BlueZ agent. Interactive PIN/passkey
entry or confirmation is not implemented; such prompts fail explicitly instead
of being accepted silently. Pairing/trust changes already made by BlueZ may
persist if a later connection or routing step fails or is cancelled. Check the
device list; Forget removes a stored device. Connecting a second headset can
also affect the first headset at the vendor-service level; seamless handover
has not been established.

Status refreshes BlueZ power and connection properties even when the previously
cached radio state was disabled. A confirmed external power-off or headphone
disconnect attempts wired output before clearing the connected status. Failed
or cancelled output restoration reports its error and retains the connection
record for a later retry. Failed or incomplete BlueZ queries report an error;
they do not establish a disconnection. Refresh is explicit, with no background
radio polling. A persistent, owned `dbus-monitor` subscription supplies change
hints. The serialized worker confirms power and the selected peer before acting;
an event or a monitor failure alone is not proof of disconnection. Monitor restart
attempts are bounded. Status reports when monitoring is unavailable. Cheap memory
and pipe checks do not repeatedly run discovery or enumerate all paired devices.
UI notifications respect both their own setting and optional dynamic-content
announcements; explicit operation errors remain spoken.

Disconnect, switching power off and Forget for the active device first attempt wired
output. A missing `bluealsa-cli` does not prevent these BlueZ operations. If
`bluetoothctl` itself is missing, wired restoration is still attempted, but the
operation reports unavailable and the radio's connection record is retained
because disconnection could not be confirmed.

The implemented path is music + eSpeak + voice files → existing Rockbox mixer
and ducking → one PCM helper → ALSA → headphones or wired output. There is no
separate speech stream. Bluetooth master volume applies bounded stereo software
attenuation to that mixed output; the analog DAC mixer alone cannot adjust it.
No selectable codec, microphone, Bluetooth recording, headset buttons, multipoint
or absolute-volume guarantee is included in this phase.

## Isolated PCM and lifecycle

All PCM ALSA calls execute in a helper launched by `execve("/proc/self/exe", ...)`,
not in the GUI, mixer callback, or a multithreaded post-fork child. The early
`--hiby-pcm-helper <route> <rate> 3` entry returns before Rockbox/TTS initialization.
It does not initialize the core arena or speech engine. It still maps the same
application/libraries; helper RSS and total available memory need R1 measurement.

A bounded Unix `SOCK_SEQPACKET` socket transfers at most one 1024-frame stereo
chunk awaiting acknowledgement. Partial ALSA writes retain their remaining data.
The mixer obtains another buffer only after acknowledgement; this tracks ALSA
acceptance, not the exact instant sound leaves Bluetooth headphones. Audio and
cursor clocks still have hardware/transport buffering latency. Natural completion
drains the tail in the helper; explicit Stop cancels a nonblocking drain and drops
queued audio. A hung vendor drain, write, open or close cannot hold the GUI lock.

Route opens have a two-second deadline and are cancellable. A new route is
committed only after the helper acknowledges successful ALSA configuration at
the requested rate. Failed/cancelled opens preserve the previous route. A stalled
acknowledgement or missing heartbeat after 1.5 seconds retires the helper and
attempts wired output without panic. Heartbeats do not mask a stalled write.
The helper uses a 250 ms idle poll; the parent also waits up to 250 ms when idle,
instead of keeping a fast audio poll running with no audio. Neither that design
nor Linux's presence establishes negligible battery overhead.

Repeated wired-open failures use monotonic exponential retry backoff, starting
at 250 ms and capped at four seconds. Successful open, an explicit route request,
rate change or a new playback request resets it; automatic recovery does not.
Failed DATA submission preserves the unsubmitted source chunk and reconciles
recovery with the actual shared PCM/mixer state rather than privately stopping
the driver and leaving the core playing. Output already accepted by ALSA can
still be lost on a route failure; lossless Bluetooth handover is not promised.

Retirement closes IPC, sends SIGKILL and uses nonblocking child reaping. Idle
maintenance revisits retired owned children; shutdown uses a bounded final reap
window rather than assuming a single WNOHANG query completed cleanup. Condition
waits use the monotonic clock, matching the recovery and heartbeat deadlines. A
fixed eight-process budget prevents unlimited helpers if a vendor/kernel call
cannot be reaped promptly. SIGKILL cannot guarantee immediate death of a process
in uninterruptible kernel I/O; budget exhaustion is an error, not a reason to
spawn more processes. Physical disconnect, kernel behavior and power use remain
acceptance gates. Wired fallback can itself fail and is not a hardware guarantee.

Shutdown ordering is final speech and `voice_wait` → stop registered Bluetooth
policy/monitor → cancel/join connectivity and Bluetooth workers
→ `hiby_pcm_shutdown` → codec/hardware close. Do not call PCM shutdown while
holding its lock or from its callback. Radio startup remains lazy and optional;
no codec/runtime ABI or USB safety claim follows from the helper's host tests.

## Runtime requirements

The adapter invokes absolute executable paths, without a shell:

- `/usr/bin/bluetoothctl`: BlueZ controller, discovery, pairing and connection.
- `/usr/bin/bluealsa-cli`: availability of the specific A2DP source PCM endpoint.
- `/usr/bin/bt_resume`: vendor service startup fallback when powering on fails.
- `/usr/bin/dbus-monitor`: passive BlueZ/BlueALSA change hints, without discovery.
- A running compatible BlueZ/BlueALSA service and ALSA `bluealsa` PCM plugin with
  its configuration, shared-library dependencies and firmware-compatible ABI.

The local route is `plughw:0,0`. The Bluetooth route is
`bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp`, with the corresponding endpoint
`/org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/a2dpsrc/sink`. Addresses must be exactly
six hexadecimal octets. Device names and lists are bounded and sanitized; they
are never interpolated into commands. CLI commands have deadlines, output
limits, cancellation and child reaping. Missing helpers, unsupported commands,
unconfirmed pairing/connection and missing endpoints produce errors.

The inspected stock 1.6 and modified 1.8b2 images contain BlueZ 5.54 and
BlueALSA 4.1.1 markers and the monitor executables. Reading these image members
does not establish the running firmware, D-Bus permissions, successful event
delivery or codec interoperability on a particular player. A build-time ALSA library is not proof of compatible target
libraries or an installed BlueALSA plugin. The earlier diagnostic R1 package's
runtime manifest records linked-library provenance; it contains no `.so`
payloads and does not install the Bluetooth services/plugin. Do not copy an
arbitrary desktop GLib/DBus stack onto the player.

The inspected fork also uses an optional proprietary socket command
`BT:ABSVOL:<underscore-address> <0..127>` at `/var/run/sys_server`. This is not
the pairing API, is not a standard BlueZ command and is not required by this
adapter. Its behavior must be measured before it is integrated off the UI and
PCM threads.

## Safe installation and updates

Do not treat the existing live Rockbox USB mass-storage mode as a safe updater.
The inspected baseline gadget exports the raw SD block device while the Linux filesystem
remains mounted. Simultaneous computer/Linux access can corrupt the filesystem.
USB remediation and verification are separate publication gates.

The release loader executes a copy at `/tmp/rockbox.r1`, but retains
`LD_LIBRARY_PATH=/data/mnt/sd_0/.rockbox`. Libraries, codecs, plugins and open
files can still depend on the card. Copying the executable to RAM is not an
unmount protocol. A future file-level ADB updater needs verified complete-package
staging, clean application shutdown, atomic replacement/rollback and failure
tests. Stock-OS USB after a clean Rockbox shutdown is an alternative only once
that firmware's behavior has been verified. Neither is claimed as a completed
updater. The inspected loader disables Wi-Fi; no Wi-Fi updater is demonstrated.

## Verification

Run on a POSIX host with GCC:

```sh
python3 -B tools/tests/test_hiby_bluetooth.py
python3 -B tools/tests/test_hiby_pcm.py
```

The suite compiles real project sources with strict warnings, exercises malformed
addresses, long Unicode names, command failures/deadlines/PIN prompts, closed
pipes, cancellation of child process groups, bounded device lists, worker
serialization/shutdown, explicit simulator unavailability, and AddressSanitizer
+ UndefinedBehaviorSanitizer. Evidence goes to central project Workspace, not
the source tree. PCM tests run the actual exec helper with controlled ALSA faults,
real host ALSA `null`, strict native MIPS compilation and ASan/UBSan. Extracted
unchanged core PCM/mixer functions verify simultaneous music/voice and amplitude
ducking through the helper; this is not a real eSpeak/DSP/headphone test. Cases
cover partial writes, acknowledgement ordering, natural tail/explicit stop,
open/configuration/write/drain hangs, cancellation, helper death, finite reaping,
route/rate churn, closed standard descriptors and target/early-entry guards.
Actual-core regression cases inject fatal DATA-send failure after the receive
check and verify exact retained samples, wired recovery and subsequent music and
voice playback; a separate case verifies transient send backpressure. Persistent
local-open failure counts launches while playing and verifies retry bounds plus
explicit route/rate/playback reset. These extend, not retroactively validate,
the earlier test receipt that missed these two defects.
These tests do not replace physical wired/Bluetooth music and
speech, master-volume, headphone-power-off, lock/unlock, resume, shutdown, ABI,
service restart and battery tests.

Further host regressions cover concurrent shutdown callers waiting for the same
worker, external BlueZ power/connection changes, output restoration errors and
cancellation, missing CLIs, and incomplete property replies. A CLI that closes
its output pipe and remains alive still observes the command deadline without
busy polling the closed pipe. Host process CPU timing for that case is not a
measurement of R1 battery use.

## Controller and guarded-pause contract

Each issued request carries an immutable ID, manual-intent generation and
permission epoch through completion. Automatic admission checks its previously
captured expectation before clearing cancellation. Final snapshot and service
mailboxes publish under controller-then-service lock ordering; consumers use
the coherent observation accessor. Preference writes follow committed worker
order outside those locks. A known powered radio remains usable when its audio
endpoint fails, while the endpoint error remains visible.

The native R1 TTS-only `audio_pause_guarded` API takes the playback generation
captured at the loss observation, not a fresh generation at the later call.
Normal play, stop, pause and resume advance that generation. Its registered
caller must not be the audio receiver, a foreign pthread, ISR or another CPU,
and must hold no resource needed to complete the synchronous queue operation.
The stack-owned request remains alive until the queue replies or discards it.
Other targets do not acquire this event, counter or interface.

The receiver's `begin` callback must not yield, invoke speech/audio/queue APIs
or acquire controller/connectivity locks. False leaves no guard held; true
retains its short service guard across only the scalar playback-state commit.
The paired `end` releases it before IAP, fades or PCM effects. A newer manual
intent, permission revocation or playback command rejects a stale loss pause.

PCM route checks are snapshots under their own lock, not an atomic transaction
with the service guard and playback commit. A direct PCM route change between
that snapshot and the commit is not excluded. This contract is not a zero-sample
privacy guarantee or proof of physical handover. The monitor's started-process
status likewise does not confirm subscription readiness or delivered events.

## Source basis

- [Pinned bahusoid Bluetooth implementation and limitations](https://github.com/bahusoid/rockbox/blob/059809d123a5b2d4ff1d65b571e99cf56b35dd51/docs/mods/bluetooth-hiby-x1600.md).
- [Inspected x1600_hiby_v2 release](https://github.com/bahusoid/rockbox/releases/tag/x1600_hiby_v2).
- [BlueZ Device API and pairing-agent requirement](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Device.rst).
- [BlueALSA ALSA plugin requirements](https://github.com/arkq/bluez-alsa/blob/master/doc/bluealsa-plugins.7.rst).
- [ALSA PCM I/O and device-removal errors](https://www.alsa-project.org/alsa-doc/alsa-lib/pcm.html).

Current upstream documentation explains the interfaces, not the unmeasured
versions installed by a particular R1 vendor firmware.
