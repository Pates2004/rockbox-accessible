# Accessible touch

This shared feature requires both a touchscreen and the integrated eSpeak.
It defaults to enabled on HiBy R1 and disabled on other supported targets.
Its entry is Settings → General Settings → Accessibility → Talkbox settings → Touch exploration settings.
Talkbox settings are the first Accessibility entry; physical buttons have their
own section on R1, described in `ACCESSIBILITY-BUTTONS.md`.
Physical buttons remain available, including during changes to gestures.

General touchscreen settings now live in Settings → General Settings → System
→ Touchscreen settings; gesture assignments remain inside Talkbox's touch exploration settings. The
general menu includes software Touch gesture sensitivity (50–200%, initially
100%). Larger values require less travel for a gesture; this scales the gesture
and typing movement thresholds, not the capacitive sensor's hardware sensitivity
or touch pressure. The existing input driver exposes no pressure-sensitivity
control. Changes take effect after saving and do not move screen hit targets.

System → Interface sounds offers all eight subsets of physical buttons, recognized
gestures and exploration. A new profile selects All inputs; older explicitly
saved masks keep their original button/gesture meanings. Shared sound strength
Off still silences every source. Exploration clicks when reaching another item
or starting a new contact, not on coordinate jitter. Empty space can use a
different pitch (enabled initially): -4 semitones, two tones below the normal
sound. The amount is adjustable from -12 to +12 semitones, and switching the
pitch difference off restores the ordinary sound rather than muting empty space.
The input configuration writes v11; v1–v10 mappings remain readable.
Touch exploration settings lists Explore by touch, Gesture assignments, Touch hold
time, Repeat gesture actions while holding, Report empty areas during touch
exploration, Different sound pitch on empty space, Sound pitch for empty areas,
then Reset Settings, in that order. The empty-area feedback mode and both pitch
controls are together here, not duplicated in System → Interface sounds.

## Interface and playback profiles

Gesture assignments opens two profiles: Interface actions and Playback screen
actions. Each has 20 assignments followed by Reset Settings for that profile.
Only the active music playback screen uses the second profile. Music playing
behind menus does not switch their gestures. Exploration, empty-area feedback,
touch hold time and held-stroke repeat remain shared settings.

Loading v1–v9 copies their gesture assignments and launch references to both
profiles in memory without rewriting the file. Later edits are independent.
Resetting one profile preserves the other and its plugin references; the main
Touch exploration reset restores both gesture profiles while preserving both
physical-button profiles. Changing screen cancels an unfinished gesture rather
than applying the next screen's assignment to it.

## Default gestures

| Gesture | Logical action |
| --- | --- |
| Right | Down / next list item |
| Left | Up / previous list item |
| Up | Left / back |
| Down | Right / enter |
| Double tap anywhere | Activate the currently focused item |
| Triple tap anywhere | Unassigned: consume the triple without activation |
| Double tap and hold the second contact | Context menu on the current focus |
| Hold a single contact | Unassigned |
| Left, then right without lifting | Back |
| Right, then left without lifting | Main menu |

The editor has 20 assignments: all four single directions, all twelve ordered
pairs of different directions, double tap, standalone hold, triple tap and
double tap and hold. Every slot can select
Unassigned, Up, Down, Left, Right, Activate, Back, Main menu, Context menu, Increase
volume or Decrease volume, Speak battery status, Open shortcut or application,
Shut down device, Lock or unlock screen, Announce current time, Toggle Talkbox,
Toggle interface voice files, Turn touch browsing on or off, Speak the current
date and Speak playback and device summary. Screen curtain is selectable where
the display backend supports it. The remaining pairs and standalone hold are
initially Unassigned. A screen-reader gesture can lock, but never unlock; use
Power + Volume + or an assigned physical unlock button.
Optional System touch-wake assignments are separate from these reader gestures;
see [screen policies](ACCESSIBILITY-SCREEN.md).
An unassigned recognized gesture is consumed without an action. It never
falls through to stock touch handling or becomes a tap/activation. Ordinary
single-tap reading and intentional exploration remain separate interactions,
not fallback actions for unassigned strokes or double taps.

Touch hold time defaults to 900 ms and allows 300–2000 ms in 100 ms steps. It
controls assigned standalone hold, double tap and hold, and the endpoint dwell
for stroke repetition; the physical-button hold time is independent. Leaving
standalone hold Unassigned disables that gesture without disabling double tap
and hold.
With hold assigned, a stationary finger waits for that gesture; move the finger
to begin exploration instead of keeping it still.

A short single tap reads/selects the touched item, not activates it. Its
announcement is deferred until the next-tap window closes, 320 ms after release.
A qualifying next press may arrive anywhere on screen within that gap. After
the second short release, double-tap activation waits for a further 320 ms gap
so a third tap can take priority. This third-tap window is always reserved,
even when Triple tap is Unassigned: three taps then do nothing, with no earlier
double activation. A double tap acts on the existing focus, even if the second
tap is elsewhere.

For double tap and hold, release the first tap, press again within the same
320 ms gap, and keep the second contact still for Touch hold time. It executes
once and consumes the release, without also activating a double or triple tap.
Its default Context menu opens the focused list, music or text-reader context
menu where supported. In the keyboard, yes/no dialogs and unsupported custom
screens, this gesture's Context menu is consumed without deleting a character
or confirming/cancelling a dialog. Existing explicit Context menu assignments
on other gestures and buttons retain their earlier meaning.

To explore, keep a finger on the screen for about 220 ms, then move without
lifting. Exploration does not activate items. Empty regions can
announce “No item here” where the screen supplies semantic hit testing.

Logical actions are context-aware: in music Left/Right skip tracks and
Activate pauses/resumes; Up/Down adjust volume. In the text reader Up/Down
select the previous/next reading unit, Left/Right move within that unit,
Activate pauses/resumes, and Context menu opens the text menu. Settings map
Up/Down to increase/decrease and Left/Right to previous/next field. In the
keyboard directions move the character cursor, Activate selects, Back aborts,
Main menu finishes input, and Context menu deletes a character.

## Repeating a held stroke

Repeat gesture actions while holding defaults to Off. When enabled, draw a
complete one- or two-direction stroke, then keep its endpoint still. After
the configured touch hold dwell, an eligible stroke can commit its first
action while the finger remains down, then repeat at a fixed 160 ms interval.
Releasing stops repetition without another action. Moving away after commit,
changing screen/context, physical input, locking or disabling touch browsing
cancels it. A double-tap-hold contact cannot also start stroke repetition.

Repetition is limited to audited actions: Up/Down list navigation, all four
reader directions, Up/Down volume in music playback, directional numeric
adjustment/field navigation in equalizer, colour and time settings, and explicit
volume actions. Generic settings, quickscreen, keyboard, yes/no and unknown
custom screens do not gain repeated directional actions. Activation, Back,
Main menu, Context menu, launch, shutdown, lock, curtain, service/touch toggles
and spoken announcements remain one-shot. An ineligible stroke keeps ordinary
release/exploration behavior; holding it does not make it repeat-safe.

## Editing safely

Choose Gesture assignments, a gesture, then its action. A change is a live,
unpersisted trial for 20 seconds. Confirm “Keep them?” to save it. Cancellation,
timeout, USB entry or a saving error restores the previous mapping and cancels
pending input. The same protection covers enabling/disabling through the menu,
Touch hold time, the repeat setting and Reset Settings. Touch reset restores
the default gestures, 900 ms touch hold and repeat Off while preserving button
assignments, physical hold time, click-source choice and plugin paths still
referenced by buttons. After confirmation it also restores Sound only for empty
areas. These are two separate private files: if only the second save fails, the
touch controls stay reset, the previous empty-area mode remains active, and a
partial-reset warning explains the result. No cross-file transaction is implied.
Physical buttons can confirm or cancel even if touch actions were removed.

Custom/raw-key plugin screens do not automatically expose touch targets. Custom plugin
action contexts consume accessible touch rather than guessing a mapping;
use physical buttons to leave these screens.

Gesture Unassigned consumes the gesture without executing an assigned action.
For physical buttons, Unassigned on a double/triple press reserves that sequence
and consumes it without native or lower-click actions. Unassigned on a single
press/hold retains the intrinsic role, including volume-only behavior. Default
Rockbox controls retains native accessible behavior without adding a multi-click
wait. These settings are separate from the Key Remap plugin.

Turn touch browsing on or off is assignable to gestures and physical buttons.
It saves the change directly and atomically, without a 20-second trial; a save
error leaves the previous state intact. It is suppressed during a live mapping
trial so unconfirmed mappings cannot be saved by toggling. When browsing is
Off, all accessibility gestures and touch-typing modes are bypassed and ordinary
Rockbox touch mode is restored. A gesture can turn browsing off; re-enable it
with a physical assignment or the menu. Physical controls and recovery chords
remain available even with touch browsing and speech off.

Speak the current date uses the localized date format. Speak playback and
device summary announces the current track, time, date and battery, in that
order. It uses the track title, falling back to its filename; unavailable fields
are announced as Unknown and the remaining fields continue. Time, date, battery
and summary share the ordinary speech gate; they do not turn speech on.

Open shortcut or application selects its destination before confirmation.
Each assignment retains its own target: a selected plugin, the Shortcuts menu
or System screens menu, or directly Files, Database, Resume Playback, Settings
or Playlists. Four different plugin paths may be assigned, with multiple
gestures/buttons sharing a path. The editor announces the destination.
Individual shortcuts and arbitrary system screens are not directly bindable.
Direct destinations leave supported core list/menu, playback, reader and
settings contexts through their normal return paths. They do not force their
way out of raw plugins, the keyboard, yes/no dialogs or unknown custom contexts.
An unsupported destination/context, including Database without database support,
reports “This screen is unavailable here”.

System → Interface sounds → Interface sounds for offers any combination of
physical buttons, gestures and exploration: eight choices including None and
All inputs. A fresh profile uses All inputs with moderate strength; previous
saved source/strength choices keep their meanings. Off silences every source.
A recognized gesture produces one click; exploration clicks on a new stable
target or contact, not every coordinate update. Repeated physical/gesture input
obeys the repeat-sound option. Unassigned gestures may still give optional feedback.

Touch exploration settings adds **Report empty areas during touch exploration**:
**Sound only** (default), **Sound and speech**, or **Speech only**. Sound still
requires enabled interface sounds and exploration selected as a sound source.
Sound only with sounds disabled is silent; a speech mode does not enable a
disabled eSpeak service. Jitter on the same empty target does not repeat the
announcement. Occupied targets retain their normal speech. **Sound pitch for
empty areas** is adjustable in the same Touch exploration settings menu; its default
difference is four semitones down when pitch distinction is enabled.

## Storage and limitations

Configuration is separate from ordinary Rockbox settings, at
`/.rockbox/accessibility.cfg` on the player (beside the simulator's own
`.rockbox` data). These development sources use plugin ABI `0xe006`; use their
matching bundled modules. The bounded typed format writes `RBACCESSIBILITY:11`, enabled/click/physical-hold/touch-hold/repeat
fields, separate interface/playback gesture and physical assignments and four
bounded launch paths and empty-target pitch distinction. A separate
`empty-feedback.cfg` stores empty-target feedback mode without rewriting button
assignments. Older v1–v10 files
are migrated on the next confirmed edit. Unknown versions, malformed, oversized, incomplete
or out-of-range values use clean target defaults, never partial mappings.
The complete current R1 configuration fits the 4096-byte limit even with four
maximum-length plugin paths.
Old system-default button values retain their meaning rather than becoming
time, curtain, service-toggle or touch-toggle actions. Loading an older file does
not itself rewrite it. Older global physical assignments are copied into both
physical profiles in memory, retaining their previous behavior until edited.
V9 already has independent physical profiles; those remain unchanged on load.
See [service controls](ACCESSIBILITY-SHORTCUT.md) for the
independent speech/voice-file actions. Confirmed edits and the direct touch
toggle write a temporary sibling file, check write, sync and close, then
atomically rename it. A failed save leaves the old file intact.

Older applications do not understand v11. When rolling back, restore a matching
older configuration or preserve the v11 file by renaming it and use defaults;
there is no silent conversion that discards independent profiles.

If manual recovery is needed, stop Rockbox and rename `accessibility.cfg` to
keep it as a backup; the next launch uses defaults. Do not edit the file while
Rockbox is running. Disabling accessibility restores the ordinary Rockbox
touch mode. While enabled, point mode is required for semantic exploration.

V11 includes four independent actions for the first/last item of a whole list
or its current visible page. Factory Up then Down and Down then Up select the
whole-list endpoints. Saved assignments are not replaced. See `ACCESSIBILITY-LISTS.md`.

This describes the current v11 sources, not acceptance of a particular release.
It is shared core functionality, not Android TalkBack or NVDA/UI Automation.
Compiled host tests are separate from native builds, spoken GUI acceptance and
physical touchscreen tuning. A custom-drawn screen without semantic targets cannot
be made explorable by the recognizer alone. Physical R1 usability, latency and
thresholds are not established by host tests.
