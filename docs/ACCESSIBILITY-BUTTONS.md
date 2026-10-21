# Physical button settings on HiBy R1

Settings → General Settings → System → Physical button settings.
System lists Touchscreen settings, Physical button settings and Interface sounds in that
order. Touchscreen settings moves from Display for builds with touch and eSpeak;
builds without eSpeak retain its original Display location. Talkbox remains the
first Accessibility entry; touch browsing and gesture assignments are inside
Talkbox settings → Touch exploration settings. Its eSpeak settings child
contains only synthesis parameters; the physical button editor stays in System.
This editor uses the five real buttons: Power, Play, Next, Volume + and Volume -.
No nonexistent Previous button is exposed.

The menu separates **Interface actions** and **Playback screen actions**.
The second profile applies only while the playback screen (WPS) is active;
music continuing behind a menu does not change that menu's button profile.
Each submenu contains the same 20 button/press rows and a reset for that profile.
The physical hold time, reset of both profiles and native controls guide remain
in the parent menu. The hold time is shared, so entering another screen does
not change the threshold halfway through a press. Pending input is canceled
when its context changes; it is never completed with the next screen's mapping.

Each button has single press, double press, triple press and hold assignments.
The physical hold time defaults to 700 ms and allows 300–2000 ms in 100 ms
steps. It is independent of the 900 ms default touch hold time. The physical
multi-click window is 300 ms. A custom double/triple assignment, including an
explicit Unassigned choice, reserves the corresponding click count; a lower
action waits while that sequence can still continue. Default Rockbox controls
on a higher-click slot does not add this wait.

- Default Rockbox controls preserves the compiled, context-aware accessible
  profile in `HIBY-R1-CONTROLS.md`, including native hold/release behavior.
- Unassigned on a double or triple press reserves and consumes that sequence
  without a native action or the action of a lower click count. It does not
  activate the focused item or change volume as a fallback.
- Unassigned on a single press or hold keeps the intrinsic button role. For a
  volume button this means volume adjustment, not list movement; other buttons
  retain their native mapping. With higher-click slots at Default Rockbox
  controls, ordinary volume presses keep their immediate native behavior.
- Directions, Activate, Back, Main menu and Context menu use the current screen's
  semantic actions, rather than guessing arbitrary plugin keymaps.
- Speak battery status announces percent or Unknown when unavailable.
- Announce current time and Speak the current date use the shared speech gate
  and localized clock/date formats. Speak playback and device summary announces
  the current track, time, date and battery in that order, using the track title
  or, when absent, its filename. Unavailable fields are Unknown; the remaining
  fields continue. These actions do not turn speech on.
- Turn touch browsing on or off can restore browsing from a physical button,
  even with touch browsing and speech off. Off bypasses all accessibility
  gestures and touch-typing modes and restores ordinary Rockbox touch mode.
- Open shortcut or application retains a selected plugin, Shortcuts menu or
  System screens menu per assignment, or directly Files, Database, Resume
  Playback, Settings or Playlists. Four distinct plugin paths may be stored;
  repeated use of a path shares it without changing other assignments. Individual
  shortcuts and arbitrary system screens are not directly bindable. Direct
  destinations use normal return paths from supported core list/menu, playback,
  reader and settings contexts. Raw plugins, keyboard, yes/no and unknown custom
  contexts are not forcibly exited. Unavailable destinations/contexts, including
  Database in a build without database support, report “This screen is unavailable
  here”.
- Shut down device uses normal Rockbox shutdown; physical Power hold is retained.
- Lock or unlock screen may unlock through a physical button. A gesture may
  only lock; it cannot bypass an already-locked touchscreen.

Custom hold assignments may repeat audited navigation as well as explicit
volume actions: Up/Down in lists, all four reader directions, Up/Down volume in
music playback, and directional numeric adjustment/field navigation in
equalizer, colour and time settings. Generic settings, quickscreen, keyboard,
yes/no and unknown custom screens do not gain repeated directional actions.
Activation, Back, Main menu, Context menu, launch, shutdown, lock, curtain,
service/touch toggles and announcements stay one-shot. These physical hold
repeats are independent of the touchscreen repeat option, which defaults to Off.
Default Rockbox controls and Unassigned single/hold retain their native repeat
and release behavior, including native seek/stop-seek mappings where present.

Power + Volume + remains the recovery lock/unlock chord. Existing modifier chords
and hardware shutdown are not replaced by the editor. Chords cancel a pending
custom multi-click sequence and suppress accidental component-release actions.
Context changes, USB entry and shutdown also cancel pending input; battery and
charger status updates alone do not. Physical input cancels pending accessible
touch gestures through the core input dispatcher.

The two service actions Toggle Talkbox and Toggle interface voice files can be
assigned directly and independently to buttons or gestures. There is no separate
Accessibility shortcut menu or service selection. The obsolete
`/.rockbox/accessibility-shortcut.cfg` is ignored and left untouched; its old
enabled/service values have no effect on these actions. They run once per recognition,
never on held repeats, and announce the resulting state even when ordinary
eSpeak is off. See [service controls](ACCESSIBILITY-SHORTCUT.md) for missing
voice-file errors, independent preferences and the later public shortcut policy.

Changes in the editor are live 20-second trials, saved only after confirmation. Cancellation,
timeout, USB entry and write failure restore the old configuration. Button Reset
restores compiled assignments without resetting gestures or click scope. Touch
Reset restores touch mappings, 900 ms touch hold and repeat Off, preserving
button assignments, physical hold time, click scope and plugin paths still
referenced by buttons.

The assigned Turn touch browsing on or off action instead commits directly and
atomically, without a confirmation trial. A write error keeps the old state.
During an active mapping trial it does not run or save unconfirmed assignments.
The touch gesture can turn browsing off, while a physical assignment or the
menu can enable it again; physical recovery remains available.

System → Interface sounds controls the shared strength/repeats. Physical buttons,
recognized gestures and touch exploration can be selected independently,
including none or all three. A fresh profile selects all three; existing source
choices are preserved.
Off silences feedback regardless of source.
See `ACCESSIBILITY-TOUCH.md` for the separate touch timing/repeat settings and
feedback. Private `accessibility.cfg` now uses `RBACCESSIBILITY:11`; v1–v10 files
keep their mappings and historical system-default meaning, with defaults for
missing fields/slots. Existing source masks 1/2/3 keep their original meaning;
v8 introduced masks 0–7 and empty-space pitch settings, enabled by default
with a change of -4 semitones. Loading alone does not rewrite the file; the next
confirmed edit or direct touch-toggle commit writes v11 atomically. V9 introduced
interface and playback button assignments separately, while sharing the hold
time and four plugin-path slots. Pre-v9 button mappings and their launch targets
are copied to both profiles in memory, preserving their previous global behavior;
the two copies can then be edited independently. Resetting touch preserves both
button profiles and their live plugin references.
Stop Rockbox and rename that file for manual recovery; do not modify it live.

V10 also stores two independent gesture profiles. V9 physical profiles remain
independent when loaded; only v1–v8 physical mappings need copying to both.

V11 adds the grouped accessibility shortcut and four list/page endpoint actions.
Factory triple Power invokes the enabled group in both profiles; saved mappings
remain unchanged. The group initially includes Talkbox and touch exploration.
See `ACCESSIBILITY-SHORTCUT.md` and `ACCESSIBILITY-LISTS.md`. A reserved triple
press delays shorter Power sequences by the existing 300 ms multi-click window.

This describes current v11 sources, not acceptance of a particular release.
It is shared-core input support, not universal raw-plugin remapping. Plugins
reading raw buttons may still need individual adapters. Windows keyboard/PCM and
host tests do not establish physical button timing, touchscreen usability,
Bluetooth, NVDA/UI Automation or battery performance on an actual R1.
