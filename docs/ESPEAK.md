# Integrated eSpeak: Clip+ simulator milestone

Current R1 continuation (2026-10-11) uses the supplied r34 engine and a separate
Windows simulator. See `ESPEAK-HIBYR1.md` for its current scope and limitations.
Sansa releases remain unchanged on r29. The milestone narrative below is
historical; it is not acceptance of current R1 hardware, Bluetooth or touch.

Refresh dated 2026-10-10: Clip+ alpha6 and Clip Zip alpha7, matching
the native pair `r29-alpha6-20261010` / `r29-alpha7-20261010`. Validate each
package separately; acceptance is recorded in
`Workspace/speech-backends-r1-20261010/final-release-review.json`.
Earlier results describe historical versions, not acceptance of this refresh.

Short paths `Workspace/...`, `Forme/...`, `snapshots/...` and `trash/...`
refer respectively to `D:\work\Workspace\rockbox`, `D:\work\Forme\rockbox`,
`D:\work\Snapshots\rockbox` and `D:\work\Trash\rockbox` (under `/mnt/d/work` in WSL).
Current `installfiles/...` belongs in `D:\Rockbox\rockbox\installfiles`.
Sources remain at `D:\Rockbox\rockbox` (`/mnt/d/Rockbox/rockbox` in WSL), and
the supplied engine/data at `D:\Rockbox\espeak-1.44.05-source`.
Paths such as `simdisk` and `.rockbox` remain relative to the application/device.

The opt-in `--integrated-espeak` build links the supplied eSpeak 1.44.05 r29
engine into an SDL simulator, with Clip+ as the current Windows release target.
It invokes neither a host TTS service nor
SAPI and does not pre-generate speech clips. This is not native Clip+ firmware.

The separate experimental device build is described in `ESPEAK-CLIPPLUS.md`.
Its ARM firmware and the Windows simulator are different release artifacts.
The additional Clip Zip device build and separate Windows simulator are described
in `ESPEAK-CLIPZIP.md`. Clip+ and Clip Zip firmware are not interchangeable.

The native Windows x64 package is `installfiles/simwindows/rockboxui.exe`;
it does not require WSL at runtime. See `ESPEAK-WINDOWS.md` in the source tree
or `README.md` in the portable Windows package; its Polish guide is `CZYTAJ.md`.
That package also includes `ESPEAK.md`, `ESPEAK-PL.md`, `ESPEAK-TARGETS.md`
and `ESPEAK-TARGETS-PL.md`. Previous Linux/WSL releases are archived in
`snapshots`; Linux builds are optional development aids.

Engine provenance and build rules live in `lib/espeak`. `apps/tts.c` owns
a bounded text queue and single synthesis worker. PCM feeds the existing
voice DSP/mixer, preserving playback ducking. The original Speex path remains.
`talk.c` resolves spoken IDs using generated `.vstrings`; arbitrary UTF-8
names bypass recorded voice files. Persistent settings include language,
variant, percent/WPM rate scale, pitch, volume, modulation, word gap,
punctuation and configurable playback ducking. New labels are English/Polish.
The default System voice follows UI language with English fallback; an
explicit voice can be selected independently. Other UI translations fall
back to English for new labels. SAPI, Vario and MBROLA are not included.

eSpeak is controlled by its own Enable speech synthesis setting. Use voice
files to read the interface, Voice file volume and directory/file reading
modes control prerecorded speech only. They may be disabled, including voice
file volume at zero, without silencing eSpeak. With synthesis enabled, names
are spoken naturally rather than numbered or read from `.talk` clips. The
eSpeak Speech volume setting controls synthesis; the player's main output
volume still applies to all sound. Temporary speech suppression and explicitly
optional plugin announcements remain effective for both backends.

The default rate scale is signed relative percent: `(WPM - 175) / 175 * 100`.
Examples, rounded to one decimal when needed: `0% = 175 WPM`, `-54.3% = 80 WPM`,
`-0.6% = 174 WPM`, `+100% = 350 WPM`, `+157.1% = 450 WPM`,
`+671.4% = 1350 WPM`. The canonical stored rate remains an integer in WPM,
with a 1 WPM step in either scale. Switching scales changes only the
presentation, not the saved rate or audio: `tts rate: 450` means 450 WPM and
displays as `+157.1%`, without replacing WPM storage with a rounded percentage.
New releases ship clean defaults (175 WPM / 0%, Polish UI, System voice), not
the user's previous profile. Archive the old installation and its data in
`snapshots` for recovery; do not restore them into the new package automatically.
Punctuation uses eSpeak's native symbol reading: None, Some, Most or All;
symbol names depend on the selected language's dictionary.

The range is 80–1350 WPM. Above 450 WPM, the supplied engine's native preparation
and the bundled Sonic library produce time-compressed speech. Sonic is bypassed
at 80–450 WPM; the ordinary regression corpus remains byte-identical. The change
of articulation method at 450/451 can cause a small duration difference, so the
nominal WPM value is not a promise of exact phrase duration. Backend tests cover
all supplied languages and variants, actual audio duration, pitch, retimed word
events, cancellation and error recovery. See `lib/espeak/README.md` in the source
tree for provenance and measured limitations; no physical-player performance
or human listening validation is implied.

The streaming UTF-8 `.txt` reader preserves its PCM buffers on pause/resume,
tracks the audible word, and navigates characters, words, logical lines,
paragraphs and pages in both directions. It reports invalid encoding explicitly.
The original viewer
remains accessible through Open With. Persistent text bookmarks reuse Rockbox's
bookmark list and recent-bookmark list. Hold Select (Space in the Sansa simulator)
for the spoken text context menu, bookmark submenu, properties,
beginning/end and settings. Up changes the navigation unit; short Select
still pauses/resumes. See `ESPEAK-BOOKMARKS.md`. PDF/EPUB/DOCX are not implemented.

On Linux/WSL install build-essential, libsdl2-dev, libsdl2-image-dev, zip and
unzip, then run from the source tree:

```sh
cd /mnt/d/Rockbox/rockbox
python3 -B tools/build_espeak_simulator.py --platform linux --target sansaclipplus \
  --espeak-source /mnt/d/Rockbox/espeak-1.44.05-source --jobs 12
```

The planned Linux Clip+ identifier is `0ed3734e5e-espeak-r29-alpha6-20261010`.
For Clip Zip, select `--target sansaclipzip`; its planned Linux identifier is
`0ed3734e5e-espeak-r29-clipzip-alpha7-20261010` and its separate release is
`installfiles/clipzip-espeak-simulator`. Matching Windows identifiers are in
`ESPEAK-WINDOWS.md`. The exact engine checkout stays at the supplied location.
Logs/builds go to central `Workspace`; the Clip+ simulator goes to
`installfiles/clipplus-espeak-simulator`. Its executable is moved, not copied.
Existing installations containing user data are not overwritten automatically.
`--build-only` keeps the development executable and snapshots its predecessor.

Run `bash launch.sh` from the package or `Uruchom.cmd` on Windows with
Ubuntu-24.04/WSLg. Rockbox data remains in adjacent `simdisk`; the launcher
writes `simulator.log` and directs graphics/audio library data into adjacent
`runtime`. This affects only the simulator process, not global WSL settings.
The program directory must be writable; there is no user-profile fallback.
Arrows navigate, Space selects, Left goes back, Insert maps Home,
Page Up/Down map volume keys, and held Escape maps power-off.
In the Clip+ reader, Space pauses/resumes without restarting the interrupted
word. Up/Down changes the navigation unit; Left/Right moves by that unit; a short
Escape exits. Changing unit or navigating pauses continuous reading and speaks
the selection (a first-line preview for larger units); Space then reads from the
new cursor. There are no automatic start/pause announcements. The display shows
state, byte position and text starting at the current word. Position follows
consumed voice PCM, with approximately one mixer-buffer timing precision.
During some spoken punctuation names, the old engine supplies no usable word
position, so the cursor stays at the preceding word until the next valid event.
Character navigation uses Unicode codepoints, not grapheme clusters; CRLF is one
line break. Known character names use native eSpeak character mode independently
of punctuation settings, structural newlines have a localized label, and unnamed
characters fall back to their decimal Unicode number. A paragraph is separated
by blank logical lines. Pages contain a configurable number of logical lines,
20 by default (1–100); this is not visual screen wrapping. Unit/page settings
live under Accessibility → Talkbox settings → Text reading settings, separately
from the eSpeak engine parameters. Long scans can be cancelled;
page lookup scans from the document start without a whole-file index.

The SDL framebuffer does not expose native Windows controls to NVDA.
Self-voicing does not demonstrate native screen-reader accessibility.
Recorder controls and labels are self-voicing, but recording, pause and resume
cannot execute in SDL: simulator builds exclude recording initialization,
command dispatch and status support. SDL recording DMA is also stubbed and
cannot capture microphone audio. Adding the speech engine does not provide
a working recorder. Start announces `Recording is unavailable in the simulator`
without changing recording state or creating a recording file. Polish and
English tests verify spoken feedback and responsive navigation/exit.
Recording and speech on a physical player need separate
audio-routing, memory and performance tests. See `ESPEAK-WINDOWS.md` in the
source tree or `README.md` in the Windows package for recorder limitations.
Host performance/memory do not demonstrate fitness for 8 MB RAM/AS3525.
Native libc/stdio/locale/allocation adaptation is implemented for the experimental
Clip+/Clip Zip ARM builds. Physical memory, performance and audio validation still
remain required. Do not flash this simulator onto a player.

See `ESPEAK-PL.md` for the Polish guide.
eSpeak is GPL-3.0-or-later; see `lib/espeak/License.txt` in the source tree
or `eSpeak-LICENSE.txt` in the portable package.
See `ESPEAK-TARGETS.md` for exact model/revision mapping. The native build guides
describe the bounded license review, independently implemented number conversions,
runtime notices and corresponding-source delivery. They do not certify a complete
legal review of every dependency or asset for wider public distribution.
