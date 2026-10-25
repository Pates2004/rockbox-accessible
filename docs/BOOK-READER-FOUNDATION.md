# Shared book-reader foundation

[Polski](BOOK-READER-FOUNDATION-PL.md)

This is the first implementation stage for structured books. It provides a
format-independent C core in `apps/book_reader.[ch]`. **It does not yet open
DAISY, EPUB, PDF, MOBI or office documents.** There are no new book menu options
until a format adapter can supply working content. Existing TXT reading,
search defaults, button assignments and text/audio bookmarks continue to use
their existing implementation.

The core is compiled with integrated eSpeak on every admitted player target;
it has no HiBy-specific input, display, audio or filesystem dependency. An
unused core may be removed by the linker until a reader adapter calls it.
This stage does not change the plugin ABI or certify another player.

## Publication and positions

A `book_source` supplies immutable publication metadata and a callback that
fetches one normalized navigation entry on demand. The adapter owns the index
and can keep it on storage; the core allocates no heap and stores no whole-book
tree. Resource IDs and entries belong to one publication revision. Entries are
ordered for reading, with parents preceding children. Labels and page numbers
are adapter data, not generated from entry indexes.

A position contains a logical resource/anchor, a decoded UTF-8 byte offset and,
when present, a separate audio resource and absolute media time in milliseconds.
Text and narration may reside in different resources. Flags distinguish text,
audio and visual content, including combinations. An image-only PDF page can
be visual without text. **OCR is deferred; PDF images are intended to be shown
on screen.** A PDF parser/renderer still has to be implemented. A visual flag
does not render a page or create a spoken text layer.

The adapter must assign stable IDs for one revision, validate anchor/file/clip
bounds and UTF-8 boundaries, and change the revision whenever content, index
schema, ID assignment or decoded-offset rules change. The 32-byte identity
identifies the publication; the separate 32-byte revision identifies the exact
interpreted content/index. Use deterministic fingerprints, for example SHA-256.
This detects stale positions, not the authenticity of a publication.

## Bounded navigation

`book_nav_begin` selects a supported unit, optional exact heading level,
direction and stop/wrap behavior. Units are publication headings, publisher
pages, authored phrases, paragraphs, sentences, words and characters. The
adapter advertises only units it can actually resolve. Unsupported units return
`BOOK_UNSUPPORTED`; an audio recording alone does not supply word boundaries.

After a successful begin (`BOOK_AGAIN` or `BOOK_END`), call `book_nav_step` with
a positive callback budget. `BOOK_AGAIN` yields to the UI; cancellation is
explicit. Callback `BOOK_AGAIN` retries the same index on the next step. Neither
the call budget nor the fixed job size proves a hard time or memory bound for
the adapter. Callback I/O and parsing must themselves be bounded/cancellable.

An origin entry is excluded even when wrapping. `BOOK_ID_NONE` starts before
the first or after the last entry. Results are published only on `BOOK_OK`;
end, errors, cancellation and source changes leave output arguments untouched.
A changed identity, revision, count, unit mask, callback or context invalidates
a job before another result is exposed. Source and context must remain alive
until the job ends. Calls use one owning UI thread; no concurrent mutation or
re-entry is supported. The caller resolves a reading position to an origin
entry; this core does not infer that association from timestamps or text offsets.

## Position record version 1

This separate record does not reinterpret or migrate legacy bookmarks. Its
108 bytes have no C-structure padding. Integer fields use little endian:

| Byte | Field |
| --- | --- |
| 0 | `RBKP`, four bytes |
| 4 | version, uint16 = 1 |
| 6 | record size, uint16 = 108 |
| 8 | publication identity, 32 bytes |
| 40 | content/index revision, 32 bytes |
| 72 | logical resource, uint32 |
| 76 | anchor, uint32 (`UINT32_MAX` means resource root) |
| 80 | decoded local text offset, uint64 |
| 88 | audio resource, uint32 (`UINT32_MAX` when absent) |
| 92 | absolute audio milliseconds, uint64 |
| 100 | text/audio/visual flags, uint32 |
| 104 | CRC-32/ISO-HDLC of the preceding 104 bytes, uint32 |

Absent text requires offset zero; absent audio requires the sentinel resource
and time zero. Resource IDs must fit the publication. Decode requires exactly
108 bytes, verifies CRC/version/identity/revision and leaves the output unchanged
on error. Encode writes only a validated complete record. This is a serializer;
atomic storage, resume selection and integration with the bookmark UI remain
later work. It does not write user data by itself.

## Validation and next stages

Run `python3 -B tools/tests/test_book_reader.py -v` with a host C compiler.
Set `BOOK_READER_SANITIZE=1` for undefined-behavior instrumentation and
`BOOK_READER_ASAN=1` on Linux for an additional native executable with address
and undefined-behavior sanitizers. Tests run production core and CRC code,
synthetic large publications, an independent navigation oracle and a Python
`struct`/`zlib` record oracle. Evidence is retained in the central project
workspace. These are core tests, not format conformance or physical tests.

The [container stage](BOOK-CONTAINERS.md) supplies classic ZIP/DEFLATE access.
Next come bounded XML access, format adapters, reading-order/text
delivery, audio clip scheduling, links/return and skip/escape semantics, then
spoken book menus and global/per-book preferences. Full DAISY includes audio,
text and synchronized profiles; a TOC and MP3 playlist alone do not complete it.
EPUB, PDF and other document adapters require their own validation.
