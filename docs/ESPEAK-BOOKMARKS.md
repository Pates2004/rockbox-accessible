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

## Search and typed destinations

Text options adds Find, Find next and Find previous. Search keeps the last
successful query only for this open reader session (up to 128 UTF-8 bytes).
Cancel, USB, no match, invalid text or a rejected speech enqueue preserves the
previous query and the paused audible position. Repeated Next excludes the
current character start; Previous selects the last earlier start, including
overlapping matches.

Search case sensitivity is a separate saved choice, default Ignore case.
It uses Unicode simple lowercase, including all Polish case pairs; accents
remain distinct. It does not normalize composed/decomposed text or expand
multi-character folds such as SS/ß. Search at document boundary offers Stop and
announce (default), Ask to wrap and Wrap automatically. A wrap scans the other
range once and is announced with the result; it never joins the end to the start.

Go to line and Go to page use one-based logical content positions. CRLF counts
as one separator; CR, LF, NEL, U+2028 and U+2029 also separate lines. Blank lines
count, while a final separator does not create a phantom line/page. An empty or
BOM-only document has no content line/page. Pages use the current lines-per-page
setting. Invalid, zero, overflowing or beyond-end line/page numbers are rejected.

Go to percent accepts decimal 0 through 100. It uses byte offsets, aligns inside
a UTF-8 character backwards to its start, and aligns the LF of CRLF before CR.
0 selects the first content byte after an initial BOM; 100 selects EOF. Successful
Find and Go to announce the result and stay paused. Synchronous queue acceptance
does not prove that later synthesis/output succeeded or that a listener heard it.

The private saved choices live in /.rockbox/tts-reader.cfg. Fresh packages include
neither that file nor its exclusive temporary sibling. Storage failures are
announced; unknown/future files and existing temporaries are preserved. A write
flushes, closes once and renames before changing the effective choices. This
does not promise arbitrary power-loss durability. Documents remain UTF-8 only;
bookmark formats, background playlists and the plugin settings ABI are unchanged.
