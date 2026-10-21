# Rockbox Clip+ / Clip Zip with eSpeak — native Windows x64 simulators

## Releases dated 2026-10-11

- Clip+: `0ed3734e5e-espeak-r29-win-alpha7-20261011`.
- Clip Zip: `0ed3734e5e-espeak-r29-clipzip-win-alpha8-20261011`.

These match native firmware `r29-alpha7-20261011` / `r29-alpha8-20261011`.
The package manifests identify each target and executable separately.
Earlier results remain historical and do not validate the upcoming releases.

Short paths `Workspace/...`, `Forme/...`, `snapshots/...` and `trash/...`
refer respectively to `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` and `D:\work\Trash\rockbox` (under `/mnt/d/work` in WSL).
Current `installfiles/...` belongs in `D:\Rockbox\rockbox\installfiles`.
Sources remain at `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` in WSL), and
the supplied engine/data at `D:\Rockbox\espeak-1.44.05-source`.
Paths such as `simdisk` and `.rockbox` remain relative to the application/device.

See `ESPEAK-BOOKMARKS.md` for the new spoken text menu and persistent bookmarks.
Hold Space (the centre Select/Enter button); Up only changes the navigation unit.
Text positions reuse the existing Rockbox bookmark list.

See `ESPEAK-PLUGINS.md` for extended utilities and accessibility boundaries.
The earlier Clip+ alpha4 / Clip Zip alpha5 update repaired the terminal-silence
mixer stall reproduced in the recorder speech test.

Run `rockboxui.exe` from the package for the intended model. Keep the whole folder:

- Clip+: `installfiles/simwindows` (the Clip+ release).
- Clip Zip: `installfiles/simwindows-clipzip` (a separate release).

Adding Clip Zip must not replace or migrate the Clip+ installation. Each has its
own `simdisk`, settings and log; do not mix their executables, modules or data.
The executable includes SDL2 and the supplied eSpeak engine; WSL, Python,
.NET and a system TTS installation are not required at runtime.
These are simulators, not firmware or bootloaders for either physical player.

In either portable Windows package, this guide is `README.md` and the Polish
guide is `CZYTAJ.md`. The package also includes `ESPEAK.md`, `ESPEAK-PL.md`,
`ESPEAK-TARGETS.md` and `ESPEAK-TARGETS-PL.md`.

The features below describe the shared implementation. Earlier Clip+ package
and shared-core test results are historical evidence, not test results for
the upcoming Clip+ or Clip Zip packages. Validate each target/version separately for startup,
PL/EN speech, playback/ducking, reader navigation, keyboard and recorder rejection.
Package acceptance for both upcoming versions and physical-player/NVDA tests
remains pending.

## Data and speech

Put UTF-8 `.txt` files and music under adjacent `simdisk`; preserve
`simdisk/.rockbox`. Settings and runtime data remain under that directory.
The executable locates its own directory regardless of the working directory.
It writes adjacent `simulator.log`, replacing it on launch. The program folder
must be writable; there is no AppData fallback for application data.
Use a reasonably short installation path: this eSpeak version limits the
complete `espeak-data` path to 149 UTF-8 bytes. Unicode and spaces are supported,
but some characters occupy more than one byte.

The default UI is Polish and the voice language is Follow system language.
General Settings → Accessibility → Talkbox settings contains reader controls;
its eSpeak settings child contains synthesis parameters only. The voice follows
Rockbox's UI language, including runtime changes, and falls back to English
when no matching voice exists. An explicit language overrides this behavior;
the variant remains independent. New strings are available in Polish and English.

Use voice files to read the interface, Voice file volume and directory/file
reading modes control prerecorded speech only. eSpeak continues speaking when
those switches are off or voice file volume is zero. Its own Enable speech
synthesis and Speech volume settings control synthesis; the main output volume
still affects all sound. Names use natural synthesis, not numbered modes or
`.talk` clips. This policy is shared with the native player builds.

- Rate scale defaults to signed relative percent: `(WPM - 175) / 175 * 100`.
  `0% = 175 WPM`, `-54.3% = 80 WPM`, `-0.6% = 174 WPM`,
  `+100% = 350 WPM`, `+157.1% = 450 WPM`, `+671.4% = 1350 WPM`.
  Percentages are rounded to one decimal when needed. The canonical stored
  rate remains an integer in WPM; each edit changes 1 WPM in either scale.
  Switching scales changes only the presentation, not the saved rate or audio.
- Pitch and modulation: 0–99% of eSpeak's control scale, default 50%. Stored
  values and audio are unchanged; these are not percentages of frequency
  in hertz. Modulation controls intonation/pitch range.
- Speech volume: 0–200%; word gap: 0–100 engine units.
- Punctuation: None, Some, Most or All, using eSpeak's native symbol reading.
  Symbol names depend on the selected language's dictionary.
- Audio ducking defaults on. Audio level during speech is the remaining
  playback volume, default 25%; 0% mutes music and 100% does not attenuate it.
  Normal volume returns after speech finishes or is interrupted. Turning
  ducking off does not disable speech.

The range is 80–1350 WPM. Above 450 WPM, the supplied engine prepares clear
articulation and the bundled Sonic library compresses its timing without an
intentional pitch change. Native 80–450 WPM bypasses Sonic; earlier shared-engine
tests found the ordinary corpus byte-identical, not a new Clip Zip package result.
At the 450/451 boundary the articulation method
changes, so a small duration difference is possible; WPM is the engine's nominal
rate, not an exact measurement for every phrase. This does not introduce SAPI,
Vario or MBROLA. Sonic's license and provenance accompany this package.

Each new release ships a clean profile: Polish UI, System voice and
175 WPM / 0%. Previous user settings, resume state and files are not included.
A replaced installation of the same target is archived in `snapshots` for recovery
only; adding Clip Zip leaves the existing Clip+ release in place.
Within an installation, `tts rate: 450` means 450 WPM and displays as `+157.1%`;
switching scales does not replace the saved WPM with the rounded percentage.
Speech covers connected menus, lists and messages, not arbitrary graphics or
every custom screen in every plugin.
Bundled plugins are rebuilt for this integration's ABI. Stock Rockbox and
previous-release plugins are rejected with a version error; do not replace
the new package's modules with them.

## Keyboard

Both targets use `uisimulator/buttonmap/sansa-clip.c` (including its
`SANSA_CLIPZIP` branch) and the shared `apps/keymaps/keymap-clip.c` actions.
These source mappings depend on screen context; they do not replace tests of
the delivered package.

- In ordinary lists, Up/Down selects an item, Space or Right confirms,
  Left or short Escape cancels and Insert emulates Home/menu.
- Page Up/Page Down emulates Vol+/Vol-: volume on the playback screen,
  alternate unit selection in the reader; other screens may use them differently.
- On the playback screen, Up toggles play/pause, Left/Right skips tracks
  (hold to seek) and short Escape stops playback.
- Hold Escape: shut down and save state.
- Text reader: Space or Insert pauses/resumes retained audio without repeating the block.
  Up/Down selects characters, words, lines, paragraphs or pages; Left/Right moves
  by that unit. Short Escape closes the reader. Navigation pauses continuous
  reading and previews the selection; Space continues from the new cursor.
  Unit and logical lines per page are saved under eSpeak → Text reading settings.

Numeric keypad alternatives: 8/2/4/6 = Up/Down/Left/Right, 5 = Select,
multiply (`*`) = Home, 9/3 = Vol+/Vol-, 1 = Power. These are not top-row digits.
Space, not Enter, maps Select; Insert, not the computer's Home key, maps Home.
Escape emulates Power, so its short/held actions differ by context.

The cursor follows audible words, not synthesis running ahead of playback.
Start/pause are silent; errors and end of text are announced. See `ESPEAK.md`
for Unicode, logical-page and preview semantics, and `ESPEAK-TARGETS.md` for
the device matrix. Persistent document bookmarks use the shared Rockbox list;
see `ESPEAK-BOOKMARKS.md`.

Prefer held Escape over forcibly terminating the process. Do not run two
instances against the same simdisk. The SDL framebuffer is self-voicing but
has no native Windows control tree for NVDA. UTF-8 with optional BOM is
supported; PDF, DOCX, EPUB and UTF-16 are not.

## Recorder And Plugins

The simulator recording screen speaks selected settings/values, the filename,
elapsed time and size. Time and size are selectable list items, not only
graphical indicators. These self-voicing controls and labels do not make the
recorder functional: recording, pause and resume cannot execute in the SDL
simulator. Simulator builds exclude recording initialization, command dispatch
and status support; SDL recording DMA is also stubbed and cannot capture a
microphone. This is not merely an unverified microphone test or a limitation
fixed by adding a speech engine.

The Start action announces
`Recording is unavailable in the simulator` and leaves controls and exit
responsive. Earlier Polish/English tests of the shared recorder path verified
this rejection, unchanged recording state, no new file and continued navigation.
These are historical results, not newly completed Clip Zip package tests.
No successful recording state transitions are claimed for either simulator.
Recording, signal levels, AGC and speech during recording on a physical player
require separate audio-routing, memory and performance validation.

Shared plugin menus/lists use the speech core. Plugins drawing custom interfaces
without those widgets do not become accessible automatically: their messages and
navigation need explicit integration. Universal speech for every game, graphical
viewer and custom screen is not claimed.

## Rebuild

Build under WSL Ubuntu with `build-essential`, `g++-mingw-w64-x86-64`,
`zip` and `unzip`. Fetch the official SDL2 2.32.10 MinGW development archive
from `libsdl-org/SDL`, extract its `SDL2-2.32.10/x86_64-w64-mingw32` subtree
and `SDL2-2.32.10/LICENSE.txt` into `/mnt/d/work/Workspace/rockbox/toolchains`.
Archive SHA-256: `83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2`.
Windows uses Rockbox's default Win32 Fibers threading backend. Do not use
SDL 2.30.0: its Windows event-wait bug terminates this simulator.

From the Rockbox source directory in WSL, choose **one target**. Clip+ remains
the default; no Clip+ rebuild is required just to add Clip Zip. Wait for a
coordinated source freeze before release builds.

Clip+ (only when intentionally rebuilding that preserved release):

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_simulator.py --platform windows --target sansaclipplus \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 12
```

Clip Zip:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_simulator.py --platform windows --target sansaclipzip \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source \
  --sdl-sdk /mnt/d/work/Workspace/rockbox/toolchains/SDL2-2.32.10/x86_64-w64-mingw32 \
  --jobs 12
```

Clip+ uses `Workspace/build-espeak-windows` and `installfiles/simwindows`;
Clip Zip uses `Workspace/build-espeak-windows-clipzip` and
`installfiles/simwindows-clipzip`. Native firmware is built separately; do not
install simulator output as `rockbox.sansa`.

Keep the supplied eSpeak revision `2b8dc7aa0fb3f69291a587835e63b7dd8d1c292f`
at `/mnt/d/Rockbox/espeak-1.44.05-source` (`D:\Rockbox\espeak-1.44.05-source`
on Windows). Existing installations are not overwritten;
before repackaging the selected target, move its entire earlier release,
including its data, to a unique `snapshots` location after verifying paths,
contents and that it is not in use. Preserve previous builds there too before
replacement. Do not move the other target's release just to add Clip Zip.
Leave the new package at its clean defaults; do not copy the old
profile, resume state or user files into it. The optional
`tools/migrate_espeak_simulator.py` recovery utility is not part of packaging
and must only be run on explicit request to restore old data. Both simulators
must be closed before moving a release or restoring data.
Windows is the build script's default platform. `--build-only` produces a
development build. See `lib/espeak` for engine
provenance, integration patches and licensing.
