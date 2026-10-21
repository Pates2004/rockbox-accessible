# Accessible list navigation

## Item position and content changes

Settings → General Settings → Accessibility → Talkbox settings includes two
preferences:

- **Announce list item position** appends e.g. “Files, 1 of 10” to the selected
  item's name. This covers core menus, files, settings, bookmarks and plugins
  using core lists. Counts describe the current list, not the whole tree;
  a selectable group of several display rows counts as one item. Empty lists
  have no position announcement.
- **Announce dynamic content changes** controls automatic progress speech,
  including database building, playlist insertion/search and FM scanning.
  Explicit navigation, errors, alarms and final task completion remain audible.
  This does not automatically add speech to every custom plugin interface.

Position announcement offers five modes:

- Everywhere.
- Interface only, including numeric range controls.
- Files only, including filesystem folder browsers and pickers.
- Everywhere except sliders, the default for fresh or reset settings.
- Off.

Sliders are numeric ranges such as volume, bass, speech rate and timeout values.
Rockbox presents these controls as native option lists, including numeric tables
of range steps. Boolean and enum choices, voice language/variant selection and
the bitmask editor retain positions by default. Menus of setting names,
properties, bookmarks, playlists, cue tracks and database navigation are
interface lists; a displayed number or label/value pair does not make a row a
slider. Known folder-selector plugins carry explicit file roles. Other bespoke
common-list selectors retain the interface role until explicitly tagged. Raw
custom plugin interfaces remain outside this mechanism.

Existing `tts announce position: on` retains Everywhere; `off` retains Off.
The five saved values are `on,interface,files,except-sliders,off`. The dynamic
content preference remains enabled by default and independent of position mode.

Turning positions off does not affect boundary feedback. A new selection
interrupts the previous name and position rather than queuing every passed row.
“1 of 10” is one synthesis request, not three separate utterances; its connector
comes from the current interface language catalog.
These are Talkbox preferences, independent of prerecorded voice preferences.
These development sources require matching ABI `0xe006` plugins; preserved Sansa
packages are not updated merely by editing shared sources.

## Boundaries and navigation

Wrapping submits the destination name immediately after any boundary message,
without the ordinary navigation delay. Previous row speech is cancelled before
the boundary sound. Later movement can still interrupt that speech: rapid
navigation does not accumulate every intermediate row for later playback.

These controls originated in integrated ABI `0xe004`; the current shared settings
require matching `0xe006` modules. Older alpha10/Windows13 packages
do not contain them.
Talkbox is the reader's interface name; the supplied eSpeak engine and its
licensing remain unchanged.

Settings → General Settings → Display → Scrolling → List Wraparound controls
the existing shared preference. No second wrap switch has been added. Turning
it off stops at the first/last row; turning it on wraps to the other endpoint.
Per-list restrictions, including nonwrapping EQ value lists, still apply.

Settings → General Settings → Accessibility → Talkbox settings → List boundary feedback offers:

- Sound and speech.
- Sound only, initially selected.
- Speech only.
- Off.

Reaching the last or first row does not itself produce boundary feedback. Trying
to move beyond it does. With wrapping off, every separate press against the
edge requests feedback again, including rapid presses. With wrapping on, the
boundary is announced before the newly selected wrapped row. A page/accelerated
move from inside a list first stops at the endpoint rather than announcing or
skipping it prematurely. Held repeats keep the existing no-wrap behavior.

Sound respects Interface sounds strength and the input-source selection;
physical buttons and recognized gestures can be enabled separately. Sound
strength Off overrides the boundary sound. Repeated-action sound follows the
existing repeat preference; this does not suppress separate presses. Speech
respects speech availability, volume and per-list speech suppression. Audio
queues and sound mixing have finite capacity; arbitrary input rates cannot
guarantee that every complete utterance has finished playing.
Moving to another row cancels queued old boundary speech so rapid edge presses
do not delay the newly focused item.
An older delayed row announcement must not replace a boundary announcement
while you remain at that edge. When a wrapped row is delayed, moving again
cancels its old boundary prefix; a silent row callback does not reserve the
speech queue for a later unrelated action. Lists returning voice-only labels
use their speech identifiers rather than indexing the visual translation table.

Four independent actions are available for gesture/button assignments in either
Interface actions or Playback screen actions:

- Go to start of list.
- Go to end of list.
- Go to start of current page.
- Go to end of current page.

Factory Up then Down selects the start of the whole list; Down then Up selects
its end. Page actions target visible rows on the applicable main/remote screen,
not the preceding or following page. Endpoint jumps speak their selected item,
not a boundary-crossing warning. They do not reinterpret music playback,
keyboard editing or the text reader as a file list.

The common list engine covers menus, settings/value dialogs, file browsers,
bookmark lists and plugins using core synclists. Private plugin interfaces,
games and raw custom drawing/input loops are not automatically covered. Use
the complete matching build and bundled plugins: the new integrated ABI is
`0xe006`; previous Sansa packages retain `0xe003` and are not changed by this work.
