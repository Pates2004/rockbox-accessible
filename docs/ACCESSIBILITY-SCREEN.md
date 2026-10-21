# Screen state announcements and current time

## Touchscreen lock and physical buttons

Settings → General Settings → System → Touchscreen settings adds two independent
options, both initially Off: Unlocking with any physical button, and Allow
physical buttons while the screen is locked. Neither duplicates the existing autolock
timer or changes the selective-softlock preference.

Unlocking requires a fresh physical press; touching, old repeats/releases and
system events do not unlock through this physical-button policy. The unlocking contact is consumed so it cannot also
activate an item. Firmware-generated shutdown/USB events and curtain recovery
remain available. With only the second option enabled, physical controls retain
their normal mappings while touch and accessibility gestures remain locked; the
screen is not announced as unlocked. If both are enabled, any-button unlocking
takes precedence. Policies persist atomically in `/.rockbox/accessibility-lock.cfg`,
separately from the existing announcement preferences.

## Touch wake and unlock

System → Touchscreen settings → Wake and unlock screen has independent One tap,
Two taps and Three taps assignments. Each defaults to Off and offers Only turn
on backlight or Wake and unlock screen. This works independently of touch
exploration and speech. It applies only while the backlight is off or the
Rockbox touchscreen is locked; ordinary lit, unlocked interaction is unchanged.

The complete tap sequence is consumed without activating the element underneath.
Single and double taps wait for a 320 ms inter-tap gap so a higher tap count can
take precedence. An Off double/triple action does nothing; it does not fall back
to a lower count's action. Movement beyond the sensitivity-adjusted tap margin,
a hold over 300 ms, physical input or a screen context change cancels the sequence.
Only turn on backlight retains the lock. Wake and unlock uses the normal lock
transition and configured notice. Neither action turns off the screen curtain;
its physical recovery chord remains available.

`/.rockbox/touch-wake.cfg` stores the three choices atomically and separately
from reading/gesture and lock-announcement settings. Invalid settings fail safe
to Off. Off preserves the existing touch/backlight policy. Enabling a wake
assignment keeps touch input available while locked, which can cost battery;
no power-saving estimate is claimed. Pending taps need a brief timer, but an
idle screen or a held/lost contact adds no wake-policy polling timer.

This is application-level backlight/softlock handling, not power-on from a fully
switched-off player or a promise of kernel deep-sleep wake. Kernel touch delivery,
pocket behavior, physical timing and battery impact still require an R1 test.

## Announcements

Open **Settings → General Settings → Accessibility → Talkbox settings → Screen settings → Screen state announcements**.
Screen settings groups curtain and state announcements, not brightness or
hardware lock controls. Talkbox settings is the first Accessibility entry;
eSpeak settings is its synthesis-only child. Screen settings stays beside it
inside Talkbox settings.

This submenu is available on builds with integrated eSpeak and software keylock
(`HAVE_ESPEAK` without `HAS_BUTTON_HOLD`), including targets without a touchscreen.
A hardware Hold switch is outside this software-lock feature. This submenu
contains only the two announcement choices. Physical-button settings and general
touchscreen settings belong to System. Advanced Key Lock remains in System;
backlight durations remain in Display → LCD Settings. They were shared links,
not separate settings, and removing those links does not discard their values.

## Choose what to announce

**On screen unlock** has six choices. The index is the value stored in the private
screen-policy file; the default is 0.

| Index | Choice | Announcement |
| --- | --- | --- |
| 0 | Say screen unlocked | Screen unlocked (default) |
| 1 | Announce current time | Current time |
| 2 | Speak battery status | Battery level |
| 3 | Announce time and battery level | Current time, then battery level |
| 4 | Announce screen state, time and battery level | Screen unlocked, then current time and battery level |
| 5 | Say nothing | No unlock announcement |

**On screen lock** has two choices:

| Index | Choice | Announcement |
| --- | --- | --- |
| 0 | Say screen locked | Screen locked (default) |
| 1 | Say nothing | No lock announcement |

These choices apply to actual software-lock transitions. Dimming, turning the
backlight off and toggling the screen curtain do not constitute a lock or unlock.
The notices use the normal interface speech mechanism. **Say nothing** disables
the corresponding transition notice without disabling other interface speech.

**Announce current time** is also available in the existing gesture and physical
button assignment editors on targets that offer those editors. It uses the
existing clock and 12/24-hour preference and does not announce the date. A missing
or invalid clock is announced as **Unknown**; an unavailable battery level is also
announced as **Unknown**. No value is invented.

The assignment editors also offer **Speak the current date** and **Speak playback
and device summary**. Summary reads the track title (or its filename), current
time, date, then battery level. It takes one clock snapshot for both time and
date. With no playing track or valid clock it says **Unknown** for that part.
During rapid track changes, the playback selection can already identify the next
track; this is not a sample-accurate announcement of the audible buffer.
These actions use the normal interface speech gate, not forced service-toggle
announcements. They do not change playback, the clock or the battery state.

If an announcement interrupts a text file, the canceled chunk is not treated
as fully read. The reader retains the audible position and resumes there after
the announcement; the last word may repeat. A reader paused by the user remains
paused. A bookmark created after the announcement also uses the retained
position, not the end of the canceled chunk.

## Automatic lock after inactivity

On integrated-eSpeak touchscreen builds without a hardware Hold switch, open
**Settings → General Settings → System → Touchscreen settings → Automatic screen
lock after inactivity**. This is separate from brightness or backlight duration.
There is one lock deadline, with these mutually exclusive policies:

- **Use advanced keylock settings** (`-1`, the default): preserves the legacy
  behavior described below. Existing disabled legacy defaults remain disabled.
- **Off** (`0`): disables automatic locking even if legacy autolock flags are set.
  Manual screen lock remains available.
- **5, 10, 15, 30, 45, 60, 120, 180, 300 or 600 seconds**: uses that inactivity
  interval, armed automatically without enabling either hidden legacy flag.
  Backlight, charging and curtain changes do not change this interval. A custom
  saved duration from 1 through 600 seconds is also retained in the selector.

Explicit intervals replace the legacy lock deadline; they do not add a second
thread, periodic timer or competing lock. Accepted physical input and touch
contacts restart the interval. System events, redraw, music, speech, idle gesture
polls, orphan releases and rejected input do not. Repeat bookkeeping retains its
own timestamp. A successful interval change starts a fresh interval on the next
action poll; an already locked screen stays locked. Failed saves and USB menu
interruption do not change the active policy. A known physical unlock combination
is required before an explicit timer can lock; unsupported contexts are not
silently made lockable. Selective action exceptions remain available, but their
legacy arming flags cannot arm/disarm or run a second timer in explicit/Off mode.

For **Use advanced keylock settings**, open **Settings → General Settings →
System → Advanced Key Lock**:

1. Set **Enabled** to **Yes**.
2. Open **Settings** and select **Autolock On** (`SEL_ACTION_AUTOLOCK`).
3. Select **Always Autolock** (`SEL_ACTION_ALWAYSAUTOLOCK`) so automatic locking is
   armed without having to prime it manually with the lock command. Leave the
   advanced-lock menu to apply the choices. Without this flag, the normal lock
   command arms or disarms automatic locking.
4. Go to **Display → LCD Settings** and select a positive duration in
   **Backlight**. If available, configure
   **Backlight (While Plugged In)** too: the active plugged-in setting overrides
   the ordinary duration while external power is connected.

The existing `global_settings.backlight_timeout` and
`global_settings.backlight_timeout_plugged` settings remain available
under **Display → LCD Settings**. Only the legacy policy uses their active
duration for the existing automatic-lock mechanism; it measures action inactivity,
not the actual moment at which the light fades or turns off.
**Off** (negative timeout) and **On** / always on (zero timeout) disable the
inactivity lock timer. Select a positive number of seconds to use it.

Software lock protects input. It is separate from the screen curtain and display
brightness, and does not itself promise a black display or energy savings. On
HiBy R1, the physical **Power + Volume +** chord locks or unlocks the screen. A
reader gesture can lock but cannot unlock an already locked touchscreen.
The curtain's **Power + Next** recovery chord has a different purpose: restoring
visible output.

Automatic locking applies in core contexts that use the shared action API with
`ALLOW_SOFTLOCK`. Raw-input plugins, contexts without that flag and hardware Hold
switches are outside this coverage; this is not a device-wide inactivity lock.

## Storage, migration and validation

The two announcement choices persist independently in
`/.rockbox/accessibility-screen.cfg`, with the header
`RBACCESSIBILITY-SCREEN:1` and the `unlock` and `lock` indices above. In the Windows
simulator, the path is `simdisk/.rockbox/accessibility-screen.cfg` within the program directory. Saving uses a temporary
sibling file, checks writes, sync and close, then atomically renames it. A failed
save retains the previous choices and reports a configuration-write error.
Missing or invalid policy data uses the default state announcements. No new
global settings fields or plugin ABI layout are needed.

The independent lock-policy file `/.rockbox/accessibility-lock.cfg` now writes
`RBACCESSIBILITY-LOCK:2`, preserving `unlock-button` and `physical-buttons` and
adding `timeout` (`-1`, `0`, or 1–600 seconds). Version1 files are read without
rewriting them and use legacy timeout mode; changing an option writes version2
atomically. Invalid or truncated policy data falls back to both button policies
Off and legacy timeout mode. Loading a valid custom duration does not round it
or write it back merely because the selector was opened. Announcement preferences
in `accessibility-screen.cfg` and legacy global settings are not migrated or reset.

Gesture and button assignments remain in the separate `accessibility.cfg` file.
The current-time action introduced input format `RBACCESSIBILITY:5`.
Older v1–v4 assignments keep their meanings, including the old v4 **Default
Rockbox controls** sentinel (16), which must not become the newly appended
current-time action (also 16). The service-toggle extension introduced v6;
the gesture extension introduced v7; v8 added input feedback, v9 physical
profiles and v10 separate gesture profiles. See the current touch/button guides.
Both v5's
system sentinel (17) and v6's (19) retain their original meaning rather than
becoming eSpeak or touch-browsing toggles. Changing announcement policies does
not reset assignments. See [service controls](ACCESSIBILITY-SHORTCUT.md) and
[touchscreen settings](ACCESSIBILITY-TOUCH.md).

For manual recovery, stop Rockbox before editing or renaming either configuration
file, and preserve any settings you need to restore.

The label, persistence and action regression tests cover translations, menu
ownership, version1/version2 migration, atomic failures, single-deadline modes,
accepted/rejected activity, held contacts, wraparound and settings boundaries.
They do not establish physical R1 button
timing, touchscreen behavior, battery accuracy, NVDA/UI Automation access or
energy savings. Native builds, real spoken simulator tests and physical-device
acceptance are separate validation steps.
