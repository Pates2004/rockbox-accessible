# Talkbox and eSpeak settings

Open **Settings → General Settings → Accessibility → Talkbox settings**.
Talkbox is the screen reader. Its **eSpeak settings** child contains only the
synthesis engine's parameters, in this order:

1. Speech language
2. Voice variant
3. Speech rate
4. Speech rate scale
5. Pitch
6. Speech volume
7. Modulation
8. Word gap
9. Punctuation

The language can follow the interface language or be chosen independently.
Changing the rate scale changes its presentation, not the stored speed.
Pitch and modulation are displayed and spoken as 0–99%, default 50%.
These label eSpeak's control scale, not a percentage of frequency in hertz
or a relative change from the default voice. Volume ranges from 0–200%,
default 100%. Configuration keys, stored numbers and resulting audio are unchanged.
The engine remains the integrated eSpeak 1.44.05 fork; the Talkbox name does not
replace its attribution or change its API.

The Talkbox group contains these rows, in order:

1. eSpeak settings
2. Speech synthesis — enables or disables Talkbox
3. Audio ducking
4. Audio level during speech
5. Text reading settings — Navigation unit and Lines per page
6. Touch exploration settings — including gesture assignment profiles
7. Screen settings — Screen curtain and Screen state announcements
8. Typing settings — mode, echo, capitals and deletion feedback
9. List boundary feedback

Touch exploration and typing require a touchscreen. Screen options depend on
the target's curtain and software-lock support. Existing submenus retain their
own choices. See the [touch](ACCESSIBILITY-TOUCH.md),
[screen](ACCESSIBILITY-SCREEN.md), [curtain](ACCESSIBILITY-CURTAIN.md) and
[typing](ACCESSIBILITY-TYPING.md) guides.

**Accessibility shortcut** remains directly in **Accessibility** because it
controls a selection of independent services. Prerecorded interface voice,
directory/file name and voice-file volume controls also stay at that level.
They are separate from Talkbox's synthesized speech and its engine volume.
See [service controls](ACCESSIBILITY-SHORTCUT.md).

Physical button settings, general touchscreen settings and interface sounds
remain in **General Settings → System**. Brightness and backlight durations
remain in **Display**; connectivity menus retain their existing locations.
This reorganization preserves saved configuration keys and values, private
input profiles and the plugin settings layout. Menu labels have both display
and spoken translations in English and Polish. Runtime speech, PCM and actual
keyboard navigation still require validation against a newly built product.

## Text-reader commands

The shared reader provides **Find**, **Find next**, **Find previous**,
**Go to line**, **Go to page** and **Go to percent** in the reader's
**Text options** context menu. Navigation unit and Lines per page remain in
Text reading settings.

Two separate choices in Text options are saved between runs:
**Search case sensitivity** offers **Ignore case** (default) and **Match case**;
**Search at document boundary** offers **Stop and announce** (default),
**Ask to wrap** and **Wrap automatically**. Search includes Polish case pairs;
accents remain distinct. The last successful query is kept only while that
reader session is open. Successful search and typed navigation leave reading
paused; resume when ready.

See [text reading and bookmarks](ESPEAK-BOOKMARKS.md) for input limits,
logical line/page numbering, byte-based percentages and cancellation behavior.
Availability depends on the package; dated release descriptions retain their
original scope.
