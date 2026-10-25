/* Shared book-reader foundation.
 * Copyright (C) 2026 Patryk (Pates2004)
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "book_reader.h"
#include "crc32.h"
#include <string.h>

static bool info_valid(const struct book_info *info)
{
    return info && info->resource_count && !(info->units & ~BOOK_UNITS_ALL);
}

bool book_position_valid(const struct book_info *info,
                         const struct book_position *p)
{
    const uint32_t flags = BOOK_POSITION_TEXT | BOOK_POSITION_AUDIO |
                           BOOK_POSITION_VISUAL;
    return info_valid(info) && p && p->resource < info->resource_count &&
        p->flags && !(p->flags & ~flags) &&
        ((p->flags & BOOK_POSITION_TEXT) || p->text_offset == 0) &&
        ((p->flags & BOOK_POSITION_AUDIO) ?
            p->audio_resource < info->resource_count :
            (p->audio_resource == BOOK_ID_NONE && p->audio_ms == 0));
}

static bool source_unchanged(const struct book_nav_job *job)
{
    const struct book_source *a = job->source, *b = &job->snapshot;
    return a->context == b->context && a->read_entry == b->read_entry &&
        a->info.resource_count == b->info.resource_count &&
        a->info.entry_count == b->info.entry_count &&
        a->info.units == b->info.units &&
        !memcmp(a->info.identity, b->info.identity, BOOK_FINGERPRINT_SIZE) &&
        !memcmp(a->info.revision, b->info.revision, BOOK_FINGERPRINT_SIZE);
}

static bool entry_valid(const struct book_info *info, uint32_t index,
                         const struct book_nav_entry *entry)
{
    return (entry->parent == BOOK_ID_NONE || entry->parent < index) &&
        !(entry->units & ~info->units) &&
        ((entry->units & BOOK_UNIT_HEADING) ? entry->heading_level > 0 :
                                             entry->heading_level == 0) &&
        book_position_valid(info, &entry->position);
}

enum book_result book_nav_begin(struct book_nav_job *job,
                                const struct book_source *source,
                                uint32_t from, uint32_t unit,
                                uint16_t heading_level,
                                enum book_direction direction,
                                enum book_edge edge)
{
    if (!job || !source || !info_valid(&source->info) || !source->read_entry ||
        !unit || (unit & (unit - 1)) || (unit & ~BOOK_UNITS_ALL) ||
        (heading_level && unit != BOOK_UNIT_HEADING) ||
        (from != BOOK_ID_NONE && from >= source->info.entry_count) ||
        (direction != BOOK_NEXT && direction != BOOK_PREVIOUS) ||
        (edge != BOOK_EDGE_STOP && edge != BOOK_EDGE_WRAP))
        return BOOK_INVALID;
    if (!(source->info.units & unit))
        return BOOK_UNSUPPORTED;

    struct book_nav_job next = {0};
    next.source = source;
    next.snapshot = *source;
    next.unit = unit;
    next.heading_level = heading_level;
    next.direction = direction;
    next.edge = edge;
    next.remaining = source->info.entry_count;
    next.status = BOOK_AGAIN;
    if (from == BOOK_ID_NONE)
        next.candidate = direction == BOOK_NEXT ? 0 :
                         (next.remaining ? next.remaining - 1 : 0);
    else
    {
        --next.remaining; /* Wrapping never returns the starting entry. */
        if (direction == BOOK_NEXT)
        {
            next.candidate = from + 1;
            if (next.candidate == source->info.entry_count)
            {
                next.candidate = 0;
                if (edge == BOOK_EDGE_STOP)
                    next.remaining = 0;
            }
        }
        else if (from)
            next.candidate = from - 1;
        else
        {
            next.candidate = source->info.entry_count - 1;
            if (edge == BOOK_EDGE_STOP)
                next.remaining = 0;
        }
    }
    if (!next.remaining)
        next.status = BOOK_END;
    *job = next;
    return next.status;
}

static void advance(struct book_nav_job *job)
{
    if (!--job->remaining)
        return;
    if (job->direction == BOOK_NEXT)
    {
        if (++job->candidate == job->snapshot.info.entry_count)
        {
            job->candidate = 0;
            if (job->edge == BOOK_EDGE_STOP)
                job->remaining = 0;
        }
    }
    else if (job->candidate)
        --job->candidate;
    else
    {
        job->candidate = job->snapshot.info.entry_count - 1;
        if (job->edge == BOOK_EDGE_STOP)
            job->remaining = 0;
    }
}

enum book_result book_nav_step(struct book_nav_job *job, uint32_t budget,
                               uint32_t *index, struct book_nav_entry *entry)
{
    if (!job || !job->source || !budget || !index || !entry)
        return BOOK_INVALID;
    if (job->status == BOOK_CANCELLED)
        return job->status;
    if (!source_unchanged(job))
        job->status = BOOK_STALE;
    while (job->status == BOOK_AGAIN && budget--)
    {
        struct book_nav_entry candidate = {0};
        enum book_result result = job->snapshot.read_entry(
            job->snapshot.context, job->candidate, &candidate);
        if (!source_unchanged(job))
            job->status = BOOK_STALE;
        else if (result == BOOK_AGAIN)
            return BOOK_AGAIN;
        else if (result != BOOK_OK)
            job->status = result == BOOK_IO_ERROR ? BOOK_IO_ERROR : BOOK_CORRUPT;
        else if (!entry_valid(&job->snapshot.info, job->candidate, &candidate))
            job->status = BOOK_CORRUPT;
        else if ((candidate.units & job->unit) &&
                 (!job->heading_level ||
                  candidate.heading_level == job->heading_level))
        {
            job->found_index = job->candidate;
            job->found = candidate;
            job->status = BOOK_OK;
        }
        else
        {
            advance(job);
            if (!job->remaining)
                job->status = BOOK_END;
        }
    }
    if (job->status == BOOK_OK)
    {
        *index = job->found_index;
        *entry = job->found;
    }
    return job->status;
}

void book_nav_cancel(struct book_nav_job *job)
{
    if (job)
        job->status = BOOK_CANCELLED;
}

static void put32(unsigned char *p, uint32_t value)
{
    for (unsigned int i = 0; i < 4; ++i)
        p[i] = value >> (8 * i);
}

static uint32_t get32(const unsigned char *p)
{
    uint32_t value = 0;
    for (unsigned int i = 0; i < 4; ++i)
        value |= (uint32_t)p[i] << (8 * i);
    return value;
}

static void put64(unsigned char *p, uint64_t value)
{
    put32(p, (uint32_t)value);
    put32(p + 4, (uint32_t)(value >> 32));
}

static uint64_t get64(const unsigned char *p)
{
    return get32(p) | ((uint64_t)get32(p + 4) << 32);
}

enum book_result book_position_encode(const struct book_info *info,
                                      const struct book_position *position,
                                      unsigned char *record, size_t size)
{
    if (!record || size < BOOK_POSITION_RECORD_SIZE ||
        !book_position_valid(info, position))
        return BOOK_INVALID;
    unsigned char data[BOOK_POSITION_RECORD_SIZE] = { 'R', 'B', 'K', 'P',
                                                     1, 0, 108, 0 };
    memcpy(data + 8, info->identity, BOOK_FINGERPRINT_SIZE);
    memcpy(data + 40, info->revision, BOOK_FINGERPRINT_SIZE);
    put32(data + 72, position->resource);
    put32(data + 76, position->anchor);
    put64(data + 80, position->text_offset);
    put32(data + 88, position->audio_resource);
    put64(data + 92, position->audio_ms);
    put32(data + 100, position->flags);
    put32(data + 104, crc_32r(data, 104, UINT32_MAX) ^ UINT32_MAX);
    memcpy(record, data, sizeof(data));
    return BOOK_OK;
}

enum book_result book_position_decode(const struct book_info *info,
                                      const unsigned char *record, size_t size,
                                      struct book_position *position)
{
    if (!info_valid(info) || !record || !position)
        return BOOK_INVALID;
    if (size != BOOK_POSITION_RECORD_SIZE || memcmp(record, "RBKP", 4) ||
        record[6] != BOOK_POSITION_RECORD_SIZE || record[7] ||
        get32(record + 104) != (crc_32r(record, 104, UINT32_MAX) ^ UINT32_MAX))
        return BOOK_CORRUPT;
    if (record[4] != 1 || record[5])
        return BOOK_UNSUPPORTED;
    if (memcmp(record + 8, info->identity, BOOK_FINGERPRINT_SIZE) ||
        memcmp(record + 40, info->revision, BOOK_FINGERPRINT_SIZE))
        return BOOK_STALE;
    struct book_position result = {
        .resource = get32(record + 72), .anchor = get32(record + 76),
        .text_offset = get64(record + 80), .audio_resource = get32(record + 88),
        .audio_ms = get64(record + 92), .flags = get32(record + 100)
    };
    if (!book_position_valid(info, &result))
        return BOOK_CORRUPT;
    *position = result;
    return BOOK_OK;
}
