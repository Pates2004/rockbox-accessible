# Text bookmarks and context menu

The core UTF-8 reader reuses Rockbox's bookmark screen, spoken list, deletion
confirmation and recent bookmarks. Existing audio entries retain their format.
Opening/restoring text does not replace the concurrently playing playlist.

On Clip+ and Clip Zip hold the centre Select/Enter button, as in music.
In the Windows simulator hold Space. Short Select pauses/resumes.
Up/Down change the navigation unit; Left/Right navigate. Holding Up does
not open the text menu.
Volume buttons retain the reader's previous unit-changing behavior.

Text options contains Resume reading, Bookmarks (Create/List), Properties,
Go to beginning/end, Text reading settings and eSpeak settings. Properties
speaks filename, path, byte size, byte/percentage position and navigation unit.

Opening the menu pauses at the audible word, not the end of queued text.
Closing it stays paused; select Resume reading or press Select. Menus use
normal voice mixing/audio ducking without stopping background music. Returning
from menus resynthesizes from the saved word; ordinary pause/resume without a
menu still preserves its PCM buffers.

`book.txt.bmark` beside `book.txt` stores typed text entries: UTF-8 byte offset
and navigation unit rather than audio time. The location must be writable.
Writes check errors and replace the old file only after completing the temporary
file. Existing temporary files are preserved: when `.tmp` already exists,
the writer tries the bounded alternative names `.t01` through `.t0f` without
overwriting them. Saving fails if all these names are occupied or another
file operation fails. A recent-list write can fail after the local bookmark
was saved successfully; the reader explicitly reports this partial result.
Open the book's own bookmark list to restore that local position.
With the existing recent-bookmark setting enabled, text and audio share the
recent list. Text restore does not alter shuffle, playlist or audio speed.
Hold Select on the shared bookmark list for Resume/Delete and confirmation.
Local restore returns to the text menu; global recent restore opens the text.
Entries are manual: no new automatic-on-close behavior, custom names or
migration of Text Viewer plugin bookmarks. Recreate bookmarks after moving
or renaming the book.

File size and sampled signatures at the beginning, end and around the saved
position detect many document changes. This is not a full-file checksum:
same-length edits outside the sampled regions may go undetected. Invalid
UTF-8 positions or detected changes are reported instead of silently seeking.
Keep documents unchanged while reading. TXT UTF-8 is supported, not EPUB/PDF/DOCX.

The reader, TTS and bookmark logic are shared core code. New targets still need
their own build, input/audio/memory adaptation and real-device tests. Spoken
new screens do not prove all plugins accessible or provide native NVDA/UIA
controls in the SDL simulator. Hardware validation remains separate.
