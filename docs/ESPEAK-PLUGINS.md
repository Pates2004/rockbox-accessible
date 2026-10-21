# Plugin speech

Plugins use Rockbox's shared `talk_*` interface and integrated eSpeak, not a
second speech engine. Enable Talkbox in Accessibility -> Talkbox settings for synthesized speech.
Use voice files to read the interface affects prerecorded speech only; turning
it off does not disable these plugins' eSpeak announcements. Plugin-specific
optional verbosity settings remain independent and are not forced on.
New labels have complete English and Polish versions.

## Extended utilities

| Plugin | Spoken interaction |
| --- | --- |
| Calculator | Selected key, operation and result, including scientific exponents; basic and scientific functions. |
| Stopwatch | Start, pause, elapsed time, reset, new lap and split; scrolling announces the top visible lap. |
| Metronome | State and manual tempo, meter, volume and part changes. Fast changes are coalesced; beats are not continually spoken. |
| Dice | Individual dice, total and roll settings. |
| Text Editor | Selected line, including blank lines, and changed content after editing/deletion. Supported lines up to 2047 bytes are split into bounded UTF-8 speech chunks. |
| Dictionary | Definitions as selectable chunks; use arrows for previous/next. Requires compatible user-provided dictionary files. |
| Stats | Eight selectable results: files, size, tracks, playlists, images, videos, subdirectories and maximum files per directory. Select repeats the current result. |
| Calendar | Selected date and first event; the event list exposes the remaining events for that day. |
| Shortcuts | Initial and subsequent selected links, with corrected selection after deletion. |
| Random Folder Advance Configuration | Folders in the list editor and a deleted-folder label. |
| Countdown Timer | Duration selection, start, pause, resume and one completion announcement. |
| Alarm Clock | Edited hours/minutes, alarm time, armed state and wakeup. This is the existing music-resume alarm: a resumable track is required; it does not power on a switched-off player. |
| Chess Clock | Setup, player, start/pause, remaining time on actions, round completion and action menu. This does not make the separate chessboard game accessible. |

Find these in Plugins, mainly Applications. Dice is a game; Shortcuts and
Text Editor can also be invoked through Open With. Folder names and some
pre-existing plugin menus remain English. Plugins keep their existing keymaps;
the exit button is not identical everywhere.

## “Empty list” and plugin errors

With list speech enabled, the shared list code in `apps/gui/list.c:391`
announces `VOICE_EMPTY_LIST` (“Empty list”) when `nb_items == 0`.
This reports zero items, without establishing why the list is empty or whether
the plugin has a bug. Text Editor launched from Plugins -> Applications starts
with a new document containing zero lines, so this message is expected there.
Use its confirm action (OK/Enter) to type the first line, or use Insert Above /
Insert Below in the editor menu. This does not establish a cause for reports
about other, unidentified plugins.

Other examples of data prerequisites:

- Random Folder Advance Configuration: use Scan Folders or Import from Text File
  to prepare the folder list before Edit; it uses `.rockbox/folder_advance_list.dat`.
- Dictionary: provide compatible `dict.index` and `dict.desc` files.
- Shortcuts: the selected shortcuts file must contain entries.

Fresh releases intentionally do not import previous user data. Some plugin
viewers require a file parameter supplied through Open With rather than a
standalone launch. Shortcuts without that parameter reports
`No parameter specified!`; an empty shortcuts file reports
`No shortcuts in the file!`. A missing Dictionary index reports
`Failed to open index.`. These are different messages, not `VOICE_EMPTY_LIST`;
missing data must not automatically be described as “Empty list”.

For investigation, record the plugin name/file, exact launch route, target and
release version, exact message and relevant data files. Keep empty-list feedback;
dummy entries or suppressing the message would hide the state.

## TXT reading and recording

Opening TXT normally invokes the shared reader, not Text Editor. On Sansa,
**hold centre Select/Enter** for text bookmarks, properties and settings.
Short Select pauses/resumes; Up/Down change navigation units.
See `ESPEAK-BOOKMARKS.md`.

Recording is a core feature, not a plugin, and is available only on targets
that support recording. Windows can exercise spoken recorder controls but
**cannot capture the microphone**. The shared mixer fix prevents voice from
stalling at the final silent frame between utterances. It does not establish
a fix for reported crackling on physical Sansa hardware.

## Accessibility boundaries

Shared lists, menus, questions and notices use core speech. Other plugins'
custom graphics need separate work: games, boards, pictures, visualizations
and oscilloscopes do not become accessible simply by enabling eSpeak.
This is not a claim that all plugins are accessible.

Dictionary definitions retain their existing buffer limit. Text Editor does
not gain a full screen reader for every cursor operation. Folder/statistics
scans do not speak every step. The alarm does not promise operation after
power-off. Source, build and PCM tests do not replace device testing or human
listening. The simulator is self-voicing, not a complete NVDA-native control tree.

Use only matching bundled plugins: current R1 sources use ABI `0xe006`, while
preserved Sansa releases still use `0xe003`. Do not mix these generations. Stock Rockbox
modules and modules for a different target are incompatible.
