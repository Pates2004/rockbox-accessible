/* Shared book-reader foundation, independent of format and target.
 * Copyright (C) 2026 Patryk (Pates2004)
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef BOOK_READER_H
#define BOOK_READER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BOOK_ID_NONE UINT32_MAX
#define BOOK_FINGERPRINT_SIZE 32
#define BOOK_POSITION_RECORD_SIZE 108

enum book_result
{
    BOOK_OK = 0,
    BOOK_AGAIN = 1,
    BOOK_END = 2,
    BOOK_INVALID = -1,
    BOOK_UNSUPPORTED = -2,
    BOOK_CORRUPT = -3,
    BOOK_IO_ERROR = -4,
    BOOK_STALE = -5,
    BOOK_CANCELLED = -6
};

/* A heading's level comes from the publication, not a fixed chapter taxonomy. */
enum book_unit
{
    BOOK_UNIT_HEADING = 1u << 0,
    BOOK_UNIT_PAGE = 1u << 1,
    BOOK_UNIT_PHRASE = 1u << 2,
    BOOK_UNIT_PARAGRAPH = 1u << 3,
    BOOK_UNIT_SENTENCE = 1u << 4,
    BOOK_UNIT_WORD = 1u << 5,
    BOOK_UNIT_CHARACTER = 1u << 6,
    BOOK_UNITS_ALL = (1u << 7) - 1
};

enum book_position_flags
{
    BOOK_POSITION_TEXT = 1u << 0,
    BOOK_POSITION_AUDIO = 1u << 1,
    BOOK_POSITION_VISUAL = 1u << 2
};

/* IDs belong to a specific publication revision. resource/anchor identify the
 * logical location even in an audio-only book. text_offset counts decoded UTF-8
 * bytes within that anchor, never compressed input bytes. audio_ms is an
 * absolute media-resource time, not wall time or time since a UI action.
 * An image-only PDF page can have VISUAL without TEXT. No OCR is implied.
 */
struct book_position
{
    uint32_t resource;
    uint32_t anchor; /* BOOK_ID_NONE if the resource itself is the anchor */
    uint64_t text_offset;
    uint32_t audio_resource;
    uint64_t audio_ms;
    uint32_t flags;
};

struct book_info
{
    unsigned char identity[BOOK_FINGERPRINT_SIZE];
    unsigned char revision[BOOK_FINGERPRINT_SIZE];
    uint32_t resource_count;
    uint32_t entry_count;
    uint32_t units;
};

/* Normalized entries are in reading/preorder sequence; a parent precedes its
 * children. Zero units denotes a structural entry, not a navigation target.
 * A page label or spoken title is fetched by the adapter using the entry ID;
 * there are no transient string pointers or whole-book arrays in this model.
 */
struct book_nav_entry
{
    uint32_t parent; /* BOOK_ID_NONE for top-level entries */
    uint32_t units;
    uint16_t heading_level; /* positive only when HEADING is present */
    struct book_position position;
};

/* Return OK, AGAIN (retry this index), IO_ERROR or CORRUPT. Each call must do
 * bounded work and release temporary buffers before returning. The adapter
 * owns storage, resource/anchor bounds, decoded text boundaries and clip bounds.
 */
typedef enum book_result (*book_read_entry)(void *context, uint32_t index,
                                          struct book_nav_entry *out);
struct book_source
{
    struct book_info info;
    book_read_entry read_entry;
    void *context;
};

enum book_direction { BOOK_PREVIOUS = -1, BOOK_NEXT = 1 };
enum book_edge { BOOK_EDGE_STOP, BOOK_EDGE_WRAP };

/* Caller-owned, allocation-free job. Treat fields as private. A source and its
 * context must outlive the job. Single UI-thread ownership; no concurrent edits
 * or recursive calls. Revision/count/callback changes invalidate the job.
 */
struct book_nav_job
{
    const struct book_source *source;
    struct book_source snapshot;
    uint32_t candidate;
    uint32_t remaining;
    uint32_t unit;
    uint16_t heading_level;
    enum book_direction direction;
    enum book_edge edge;
    enum book_result status;
    uint32_t found_index;
    struct book_nav_entry found;
};

bool book_position_valid(const struct book_info *info,
                         const struct book_position *position);

/* from == NONE starts before the first / after the last entry. Otherwise find
 * a strictly different entry, including on wrap. heading_level == 0 accepts all
 * levels. It must be zero for non-heading units. Unsupported units fail without
 * silently selecting another unit. Invalid begin leaves the job unchanged.
 */
enum book_result book_nav_begin(struct book_nav_job *job,
                                const struct book_source *source,
                                uint32_t from, uint32_t unit,
                                uint16_t heading_level,
                                enum book_direction direction,
                                enum book_edge edge);
/* At most budget callback invocations; AGAIN yields to the caller. Outputs are
 * written only on OK. A zero budget is INVALID and leaves the job unchanged.
 * END/errors are terminal; a completed OK result is repeatable until cancelled
 * or invalidated by a changed source. Budget bounds calls, not elapsed I/O time.
 */
enum book_result book_nav_step(struct book_nav_job *job, uint32_t budget,
                               uint32_t *index, struct book_nav_entry *entry);
void book_nav_cancel(struct book_nav_job *job);

/* New record format, independent of legacy TXT/audio bookmarks. All integers
 * are little endian with CRC-32/ISO-HDLC. Exact size required on decode; output
 * remains untouched on error. This serializes a record, not an atomic file save.
 */
enum book_result book_position_encode(const struct book_info *info,
                                      const struct book_position *position,
                                      unsigned char *record, size_t size);
enum book_result book_position_decode(const struct book_info *info,
                                      const unsigned char *record, size_t size,
                                      struct book_position *position);

#endif
