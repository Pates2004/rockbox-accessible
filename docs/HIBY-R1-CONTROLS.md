# HiBy R1 physical controls

[Polski](HIBY-R1-CONTROLS-PL.md)

New factory profiles reserve triple Power for the grouped accessibility shortcut
in both interface and playback screens. Saved mappings remain unchanged.
This adds the existing 300 ms multi-click wait to shorter Power sequences;
choose Default Rockbox controls in the triple slot to restore immediate native
input. The tables below describe native actions, not custom assignments.
See `ACCESSIBILITY-SHORTCUT.md` and `ACCESSIBILITY-LISTS.md`.

## On-device default-action descriptions

In Settings → General Settings → System → Physical button settings,
default and unassigned rows also display and speak their effective profile
action. Unassigned volume describes actual volume adjustment, not list arrows.
The last item is **Default button guide**: choose menus, music, text or keyboard.
Each press has a description derived from that context's real target map,
without changing bindings.

Double and triple presses have no separate system function; the guide names
the ordinary button function. Custom multi-press bindings can group input and
delay a single action. This is a baseline-control guide, not a description of
every custom map or plugin. Longer Power in menus requests shutdown; the first
Power hold in the keyboard finishes typing. See `HIBY-R1-POWER.md` for energy
and shutdown, and `INTERFACE-APPEARANCE.md` for colors.

This profile uses the five physical keys: Power, Play, Next, Volume + and
Volume -. The R1 has no physical Previous key. The controls below describe the
new R1 core keymap; they do not establish that a firmware package has been
installed or tested on a player.

A short press means press and release. A hold reaches Rockbox's first repeat
event. For a chord, press the first named key, add the second, then release
the second key before the first. Use Power chords briefly: continuing to hold
Power, including in a chord, can request shutdown. Releasing both keys promptly
in the opposite order also suppresses their short-press actions; keeping a
remaining key held can start its ordinary repeat action.

## Lists, menus, file browser and bookmarks

| Key | Action |
| --- | --- |
| Short Volume + / Volume - | Previous / next item, on release |
| Hold Volume + / Volume - | Increase / decrease listening volume; no list movement |
| Next | Activate the selected item |
| Hold Next | Context menu; in a setting choice list, reset to default |
| Play | Back / cancel |
| Hold Play | Main menu |
| Power | Activate / OK, like short Next |
| Power + Play | Home / main menu |
| Power + Volume + | Lock / unlock |
| Power + Volume - | Quickscreen |

Volume taps navigate only when released without a hold. Each repeat of a held
volume key changes actual listening volume instead: neither the initial press
nor release moves the selection. This works through the core action APIs in
lists, the reader and specialized editors, subject to lock/backlight filtering,
native remapping and explicit modifier chords. Ordinary setting choice lists
use short Volume + / Volume - to select values, Next or Power to save, and Play
to cancel. Use the main menu's playback entry to reach the playback screen.

The exact response to a semantic action belongs to the screen: for example,
the bookmark context menu offers its existing bookmark operations. A Home
action does not force arbitrary plugins or dialogs to jump to the main menu.

## Playback screen

Mappings follow the current screen, not merely whether audio is playing.
Volume keys therefore adjust volume here, Play and Next change tracks, and
Power toggles play/pause. Back in a menu, short volume presses navigate the
list even while music continues in the background. Assigned generic arrows
also resolve to the current screen's semantic actions. Physical button settings
now separates Interface actions from Playback screen actions; each has its own
single/double/triple/hold assignments. The second profile applies only to the
active WPS, not menus over background music. Existing older global mappings
are preserved in both profiles during migration and can be changed independently.
The timing threshold remains shared. Emergency shutdown, lock chords and
curtain recovery keep their existing behavior.

| Key | Action |
| --- | --- |
| Play | Previous track / restart, using existing playback rules |
| Hold Play | Seek backward; release ends seeking without skipping a track |
| Next | Next track |
| Hold Next | Seek forward; release ends seeking without skipping a track |
| Power | Play / pause |
| Volume + / Volume - | Volume up / down; hold to repeat |
| Power + Play | Main menu |
| Power + Next | Playback context menu |
| Play + Next | Browse files |
| Play + Volume + | Pitch / speed screen |
| Play + Volume - | Stop playback |
| Power + Volume + | Lock / unlock |
| Power + Volume - | Quickscreen |

Next is a media key here; holding it seeks. Use Power + Next for the playback
context menu. Power hold has no menu or play/pause binding.

## Shared spoken text reader

| Key | Action |
| --- | --- |
| Play / Next | Move backward / forward by the selected text unit |
| Hold Play | Repeat backward text navigation |
| Short Volume + / Volume - | Select the previous / next text unit |
| Hold Volume + / Volume - | Increase / decrease listening volume; no cursor or unit change |
| Power | Pause / resume reading |
| Hold Next | Reader context menu |
| Power + Play | Close the reader and return to its caller |
| Power + Volume + | Lock / unlock |

Units are character, word, line, paragraph and page. The existing reader
settings determine navigation step size. Its spoken context menu provides
bookmarks, properties, beginning/end navigation, reader settings and speech
settings. In that menu the normal list controls apply. The horizontal text and
vertical unit axes match the Sansa reader. Unit taps change once on release;
held volume keys do not navigate text or units. Releasing a held Next does not
move forward. The exit chord does not also navigate text or toggle speech.

These are input bindings for the existing shared reader. Host keymap tests
check the resulting semantic actions; they do not validate audible synthesis,
audio routing, bookmark storage or physical player behavior.

## Multi-field settings, quickscreen and pitch

In time, EQ, color and other value editors: short Volume + / Volume - increase /
decrease the value on release. Play / Next select the previous / next field;
Power confirms or performs the editor's existing OK operation. Hold Play to
cancel or exit without a second field change on release. Holding a volume key
changes listening volume, not the edited value. EQ uses OK to cycle its editing
mode. A setting choice list instead uses the list controls above. Semantic Home
does not force a specialized editor that lacks that action to close.

In the quickscreen, short Volume + / Volume - operate the top / bottom setting,
Play / Next the left / right setting, and short Power exits. In the pitch
screen, short Volume + / Volume - adjust pitch; Play / Next
decrease / increase speed, Power + Play resets, Power + Next changes mode, and
short Power exits. Speed changes follow the existing timestretch mode/settings.
In both screens, held volume keys adjust listening volume instead of settings
or pitch. Existing specialized editor/chord actions remain context-specific.

Confirmation dialogs accept a short Next or Power press. Play cancels.
Holding Next or Power never confirms a dialog when the key is released.

## Text-entry keyboard

The accessible typing modes are described in `ACCESSIBILITY-TYPING.md`.
Holding Power (the default Enter key) finishes text entry at the first repeat,
without inserting a character on release. Release it promptly: continued holding
still reaches the original emergency-shutdown threshold.

| Key | Action |
| --- | --- |
| Short Volume + / Volume - | Move up / down in the character grid, on release |
| Hold Volume + / Volume - | Increase / decrease listening volume; no grid movement |
| Play / Next | Move left / right in the character grid |
| Hold Play / Hold Next | Move the text cursor left / right |
| Power | Insert the selected character |
| Play + Next | Next keyboard page |
| Power + Volume - | Backspace |
| Power + Next | Finish and accept text |
| Power + Play | Abort text entry |
| Power + Volume + | Lock / unlock |

Rockbox's line-edit mode retains its existing interpretation of cursor and
selection actions. The text-entry keyboard has no ordinary context menu:
held Play / Next retain their specialized text-cursor actions, rather than the
menu/reader hold bindings. A held cursor key does not also move the grid on
release. Explicit Power chords retain Backspace, Done and Abort instead of
their ordinary navigation meanings.

## Lock and emergency power

Press Power first, add Volume + briefly, then release both. The same chord
unlocks. The shared softlock disables touch with its standard policy and
filters ordinary actions; advanced lock settings can permit selected actions.
If the backlight is off, the existing lock handler may first wake the screen;
release and repeat the chord if needed. Do not remap away the recovery chord.

The existing button driver and `POWEROFF_BUTTON = BUTTON_POWER`,
`POWEROFF_COUNT = 25` are preserved. Holding Power requests shutdown after the
driver's repeat threshold; it does not open a context menu or toggle playback
on release. This is not a measured duration or a hardware-reset guarantee.

## Windows simulator keys

The separately maintained R1 SDL input map uses:

| Computer key | R1 physical key |
| --- | --- |
| Up / keypad 8 | Volume + |
| Down / keypad 2 | Volume - |
| Right / Enter / keypad Enter | Next |
| Left / Backspace | Play |
| Space / Insert / Escape | Power |

Use Space or Insert as the Power modifier. Holding Escape also follows the
Power shutdown path. Keypad 0 remains the screenshot shortcut. The R1-specific
touch simulator routing must let mapped physical keys pass through instead of
turning arrows into virtual 3-by-3 touchscreen buttons. Keymap host tests do
not establish that a particular simulator executable contains that wiring.

## Integration and limitations

- In `apps/SOURCES`, choose `keymaps/keymap-hibyr1.c` under `#ifdef HIBY_R1`
  inside the existing `HIBY_R3PROII_PAD` branch; other targets keep their map.
  Keep `CONFIG_KEYPAD HIBY_R3PROII_PAD` for existing plugins. No new keypad ID,
  configure edit or `keymaps.make` change is needed for this core map.
- Retain `keymap-touchscreen.c`. This map exports
  `target_get_context_mapping`; its physical fallbacks use `CONTEXT_CUSTOM2`.
  The R1 reader uses shared `get_action` with
  `CONTEXT_CUSTOM | CONTEXT_CUSTOM2 | CONTEXT_STD`, allowing the existing core
  action-remap mechanism to override its semantic actions as well. Other
  targets retain the existing reader callback.
- R1 alone consumes existing `ACTION_LIST_VOLUP` / `ACTION_LIST_VOLDOWN` after
  shared softlock and backlight handling in both `get_action` and
  `get_custom_action`. Each surviving action calls `adjust_volume` once and
  returns `ACTION_NONE`, so the list GUI cannot change volume a second time.
  WPS volume actions remain immediate and use the existing playback handler.
  No action, plugin API or settings layout is added; native remapping still
  precedes default physical bindings.
- Each screen offering lock must pass `ALLOW_SOFTLOCK` to the shared action
  API. The R1 callers now do so in `apps/recorder/keyboard.c`,
  `apps/gui/quickscreen.c`, `apps/gui/color_picker.c`, `apps/menus/eq_menu.c`,
  `apps/screens.c`, `apps/gui/yesno.c` and `apps/plugins/pitch_screen.c`.
  A keymap binding alone cannot enable lock in a caller without that flag.
  The R1 reader also passes it. Host tests compile the actual caller expressions
  for R1, Sansa and R3 Pro II, preserving the other targets' contexts/timeouts,
  and verify lock, action filtering and unlock with the R1 caller arguments.
- Raw-button plugins can still demand the nonexistent Previous key. They need
  individual audits/adaptations; the core map does not establish their
  accessibility. Shared accessibility input supplies the gesture editor separately
  from this hardware keymap; see `ACCESSIBILITY-TOUCH.md`.
- The current shared gesture preset is:
  right swipe = Down, left swipe = Up, upward = Left, downward = Right,
  double tap = OK, left-then-right = Back, right-then-left = Home.
  Additional configurable two-segment paths include up-down, down-up,
  left-up, right-up, up-left, up-right, left-down and further combinations.
  Additional paths start unassigned. Exploration and the gesture editor belong
  to shared accessibility code, not this keymap. Screen curtain and its recovery
  boundary are described in `ACCESSIBILITY-CURTAIN.md`; typing modes are in
  `ACCESSIBILITY-TYPING.md`.
- Physical chords, shutdown timing, advanced lock/backlight behavior,
  real speech output and NVDA need separate runtime/device validation.

Run the host regression tests from WSL or a POSIX environment with Python 3
and a C compiler:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/tests/test_hiby_r1_keymap.py
HIBY_R1_KEYMAP_SANITIZE=1 PYTHONDONTWRITEBYTECODE=1 python3 tools/tests/test_hiby_r1_keymap.py
```

Native Unix additionally requires an absolute external `ROCKBOX_WORK_ROOT`.
Generated C harnesses and compiler logs stay in the project's central
`Workspace/hiby-r1-keymap-tests`, outside the source tree. Tests execute the
actual R1 and touchscreen mappings, shared polling/lookup/softlock/backlight
code and both action entry points with mocked platform services. They check
ordered tap/hold/chord events, global volume consumption and native remapping,
and execute actual keyboard grid movement, time-field and reader-dispatch code.
Point-mode support is enabled. Non-R1 entry-point probes verify that global
consumption is R1-only. They do not build a simulator or firmware release.
