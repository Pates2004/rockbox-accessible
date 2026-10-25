/* On-demand book-container access. Copyright (C) 2026 Patryk (Pates2004)
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef BOOK_ARCHIVE_H
#define BOOK_ARCHIVE_H
#include "book_reader.h"

#define BOOK_ARCHIVE_NAME_MAX 1024

/* Read at an absolute offset: positive byte count, zero EOF, or BOOK_IO_ERROR /
 * BOOK_CANCELLED. Short reads are supported. Source bytes/size and callbacks
 * must remain stable for this archive's lifetime. No filesystem is assumed.
 */
typedef int64_t (*book_archive_read_at)(void *context, uint64_t offset,
                                      void *data, size_t count);
struct book_archive_io
{
    uint64_t size;
    book_archive_read_at read_at;
    bool (*cancelled)(void *context);
    void *context;
};

struct book_archive
{
    struct book_archive_io io;
    uint32_t directory_offset, directory_size, entries;
};

/* Initialize a cursor to {0,0}. Entry names are exact case-sensitive ZIP bytes;
 * URI decoding, legacy name encodings and path resolution belong to adapters.
 */
struct book_archive_cursor { uint32_t index, offset; };
struct book_archive_entry
{
    uint32_t directory_position, local_offset;
    uint32_t compressed_size, size, crc;
    uint16_t flags, method, version;
    char name[BOOK_ARCHIVE_NAME_MAX];
};

/* Synchronous worker APIs, not UI-thread jobs. Read callbacks must do bounded
 * I/O and yield as needed. Cancellation is checked around I/O and sink calls.
 * Metadata outputs/cursor are unchanged on errors or END.
 */
enum book_result book_archive_open(struct book_archive *archive,
                                   const struct book_archive_io *io);
enum book_result book_archive_next(const struct book_archive *archive,
                                   struct book_archive_cursor *cursor,
                                   struct book_archive_entry *entry);
enum book_result book_archive_find(const struct book_archive *archive,
                                   const char *name, struct book_archive_entry *entry);

/* Sink output is provisional until the complete member returns OK (CRC and
 * size verified). A consumer must discard provisional output on any error.
 * No files are extracted. STORE needs no workspace; DEFLATE uses the existing
 * Rockbox inflater in caller-owned aligned memory, not the UI thread stack.
 */
typedef enum book_result (*book_archive_sink)(void *context,
                                            const void *data, size_t count);
size_t book_archive_workspace_size(void);
size_t book_archive_workspace_align(void);
enum book_result book_archive_stream(const struct book_archive *archive,
                                     const struct book_archive_entry *entry,
                                     void *workspace, size_t workspace_size,
                                     uint64_t output_limit,
                                     book_archive_sink sink, void *context);
#endif
