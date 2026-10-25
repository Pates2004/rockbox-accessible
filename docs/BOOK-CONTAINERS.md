# Book containers

[Polski](BOOK-CONTAINERS-PL.md)

`apps/book_archive.[ch]` is the second foundation stage. It reads a classic ZIP
directory on demand, finds an exact member and streams STORE or DEFLATE content
through callbacks. It extracts no files and builds no whole-book tree. This is
container access, **not an EPUB/DOCX/ODT/DAISY reader**; XML and format adapters
are still required. PDF rendering and OCR are outside this stage.

The layout follows [PKWARE APPNOTE 6.3.10](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT).
Initial limits are single-disk classic ZIP, at most 65,534 entries, an archive
no larger than `UINT32_MAX`, names below 1024 bytes, and no encryption or ZIP64.
Other compression methods return unsupported when streaming that member.
Names are exact case-sensitive ZIP bytes. Adapters own Unicode/URI interpretation,
publication identity, revision checks and file-path resolution.

Open validates the directory layout without loading it. Enumeration/finding
retain bounded metadata; duplicate requested names are rejected. Reading checks
the local header against fresh directory metadata, optional signed/unsigned data
descriptors, output limits, decoded length and CRC. Output chunks are provisional
until the entire member succeeds: discard them after any error. The existing
raw inflater does not expose exact final bit consumption; readahead bytes within
its last input block are not independently classified as trailing padding.

The caller supplies immutable random-access I/O, an optional cancellation
callback, a sink and aligned inflater workspace. DEFLATE needs 71,448 bytes on
the measured hosts, independent of document length; use the size/alignment API
rather than hard-coding it. STORE needs no inflater workspace. These synchronous
worker APIs do not suspend/resume as UI jobs: I/O must yield, and callers must
keep them off the UI thread. A bounded workspace is not a measured R1 process
memory budget. The 15 MiB core arena and plugin ABI are unchanged.

The shared inflater now accepts short final Huffman symbols without reading past
raw EOF. Checksum-byte assembly uses unsigned shifts; gzip also verifies its size
trailer. Tests cover raw/zlib/gzip wrappers, ZIP generated independently by Python,
Unicode member names, short reads, cancellation, limits and metadata errors.
Run `tools/tests/test_book_archive.py`; `BOOK_ARCHIVE_SANITIZE=1` and, on Linux,
`BOOK_ARCHIVE_ASAN=1` enable instrumentation. These checks are not format
conformance, physical playback or NVDA acceptance.
