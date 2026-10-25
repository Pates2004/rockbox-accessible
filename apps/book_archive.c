/* On-demand classic ZIP book containers.
 * Copyright (C) 2026 Patryk (Pates2004)
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Format reference: PKWARE APPNOTE 6.3.10.
 */
#include "book_archive.h"
#include "crc32.h"
#include "inflate.h"
#include <string.h>

static uint16_t get16(const unsigned char *p)
{
    return (uint16_t)p[0] | (uint16_t)((uint16_t)p[1] << 8);
}

static uint32_t get32(const unsigned char *p)
{
    return get16(p) | ((uint32_t)get16(p + 2) << 16);
}

static bool cancelled(const struct book_archive_io *io)
{
    return io->cancelled && io->cancelled(io->context);
}

static enum book_result read_exact(const struct book_archive_io *io,
                                   uint64_t offset, void *data, size_t size)
{
    if (offset > io->size || size > io->size - offset)
        return BOOK_CORRUPT;
    if (cancelled(io))
        return BOOK_CANCELLED;
    unsigned char *out = data;
    while (size)
    {
        if (cancelled(io))
            return BOOK_CANCELLED;
        int64_t count = io->read_at(io->context, offset, out, size);
        if (cancelled(io) || count == BOOK_CANCELLED)
            return BOOK_CANCELLED;
        if (count < 0)
            return BOOK_IO_ERROR;
        if (!count || (uint64_t)count > size)
            return BOOK_CORRUPT;
        size -= (size_t)count;
        offset += (uint64_t)count;
        out += (size_t)count;
    }
    return BOOK_OK;
}

static enum book_result directory_layout(const struct book_archive_io *io,
                                         uint32_t offset, uint32_t length,
                                         uint32_t entries)
{
    uint64_t cursor = offset, end = (uint64_t)offset + length;
    unsigned char header[46];
    for (uint32_t index = 0; index < entries; ++index)
    {
        if (end - cursor < sizeof(header))
            return BOOK_CORRUPT;
        enum book_result result = read_exact(io, cursor, header, sizeof(header));
        if (result != BOOK_OK)
            return result;
        if (get32(header) != UINT32_C(0x02014b50))
            return BOOK_CORRUPT;
        uint64_t size = sizeof(header) + (uint64_t)get16(header + 28) +
                        get16(header + 30) + get16(header + 32);
        if (size > end - cursor)
            return BOOK_CORRUPT;
        cursor += size;
    }
    return cursor == end ? BOOK_OK : BOOK_CORRUPT;
}

enum book_result book_archive_open(struct book_archive *archive,
                                   const struct book_archive_io *io)
{
    if (!archive || !io || !io->read_at)
        return BOOK_INVALID;
    if (cancelled(io))
        return BOOK_CANCELLED;
    if (io->size > UINT32_MAX)
        return BOOK_UNSUPPORTED;
    if (io->size < 22)
        return BOOK_CORRUPT;
    uint64_t last = io->size - 22;
    uint64_t first = last > UINT16_MAX ? last - UINT16_MAX : 0;
    enum book_result failure = BOOK_CORRUPT;
    unsigned char block[512 + 21];
    for (;;)
    {
        uint64_t start = last - first >= 511 ? last - 511 : first;
        size_t count = (size_t)(last - start + 1);
        enum book_result result = read_exact(io, start, block, count + 21);
        if (result != BOOK_OK)
            return result;
        for (size_t i = count; i-- > 0;)
        {
            const unsigned char *p = block + i;
            if (get32(p) != UINT32_C(0x06054b50) ||
                start + i + 22 + get16(p + 20) != io->size)
                continue;
            uint32_t entries = get16(p + 10), length = get32(p + 12);
            uint32_t offset = get32(p + 16);
            if (get16(p + 4) || get16(p + 6) || get16(p + 8) != entries ||
                entries == UINT16_MAX || length == UINT32_MAX || offset == UINT32_MAX)
            {
                failure = BOOK_UNSUPPORTED;
                continue;
            }
            if ((uint64_t)offset + length != start + i ||
                (uint64_t)entries * 46 > length || (!entries && (length || offset)))
                continue;
            result = directory_layout(io, offset, length, entries);
            if (result == BOOK_IO_ERROR || result == BOOK_CANCELLED)
                return result;
            if (result != BOOK_OK)
                continue;
            struct book_archive found = { .io = *io, .directory_offset = offset,
                                          .directory_size = length, .entries = entries };
            if (cancelled(io))
                return BOOK_CANCELLED;
            *archive = found;
            return BOOK_OK;
        }
        if (start == first)
            return failure;
        last = start - 1;
    }
}

static bool archive_valid(const struct book_archive *archive)
{
    return archive && archive->io.read_at &&
        (uint64_t)archive->directory_offset + archive->directory_size <= archive->io.size;
}

static enum book_result entry_at(const struct book_archive *archive, uint32_t offset,
                                 struct book_archive_entry *entry, uint32_t *next)
{
    unsigned char header[46];
    if (offset > archive->directory_size || archive->directory_size - offset < sizeof(header))
        return BOOK_CORRUPT;
    enum book_result result = read_exact(&archive->io,
        (uint64_t)archive->directory_offset + offset, header, sizeof(header));
    if (result != BOOK_OK)
        return result;
    if (get32(header) != UINT32_C(0x02014b50))
        return BOOK_CORRUPT;
    uint32_t name_size = get16(header + 28);
    uint64_t end = (uint64_t)offset + sizeof(header) + name_size +
                   get16(header + 30) + get16(header + 32);
    if (!name_size || end > archive->directory_size)
        return BOOK_CORRUPT;
    if (name_size >= BOOK_ARCHIVE_NAME_MAX)
        return BOOK_LIMIT;
    struct book_archive_entry found = {
        .directory_position = offset, .local_offset = get32(header + 42),
        .compressed_size = get32(header + 20), .size = get32(header + 24),
        .crc = get32(header + 16), .flags = get16(header + 8),
        .method = get16(header + 10), .version = get16(header + 6)
    };
    if (get16(header + 34) || found.local_offset == UINT32_MAX ||
        found.compressed_size == UINT32_MAX || found.size == UINT32_MAX)
        return BOOK_UNSUPPORTED;
    result = read_exact(&archive->io, (uint64_t)archive->directory_offset + offset + sizeof(header),
                        found.name, name_size);
    if (result != BOOK_OK)
        return result;
    if (memchr(found.name, 0, name_size))
        return BOOK_CORRUPT;
    found.name[name_size] = 0;
    *entry = found;
    *next = (uint32_t)end;
    return BOOK_OK;
}

enum book_result book_archive_next(const struct book_archive *archive,
                                   struct book_archive_cursor *cursor,
                                   struct book_archive_entry *entry)
{
    if (!archive_valid(archive) || !cursor || !entry || cursor->index > archive->entries)
        return BOOK_INVALID;
    if (cancelled(&archive->io))
        return BOOK_CANCELLED;
    if (cursor->index == archive->entries)
        return cursor->offset == archive->directory_size ? BOOK_END : BOOK_CORRUPT;
    struct book_archive_entry found;
    uint32_t next;
    enum book_result result = entry_at(archive, cursor->offset, &found, &next);
    if (result != BOOK_OK)
        return result;
    *entry = found;
    cursor->offset = next;
    ++cursor->index;
    return BOOK_OK;
}

enum book_result book_archive_find(const struct book_archive *archive,
                                   const char *name, struct book_archive_entry *entry)
{
    if (!archive_valid(archive) || !name || !entry)
        return BOOK_INVALID;
    size_t length = 0;
    while (length < BOOK_ARCHIVE_NAME_MAX && name[length])
        ++length;
    if (!length || length == BOOK_ARCHIVE_NAME_MAX)
        return BOOK_INVALID;
    struct book_archive_cursor cursor = {0, 0};
    struct book_archive_entry candidate, found;
    bool matched = false;
    enum book_result result;
    while ((result = book_archive_next(archive, &cursor, &candidate)) == BOOK_OK)
        if (!strcmp(candidate.name, name))
        {
            if (matched)
                return BOOK_CORRUPT;
            matched = true;
            found = candidate;
        }
    if (result != BOOK_END)
        return result;
    if (!matched)
        return BOOK_END;
    *entry = found;
    return BOOK_OK;
}

struct stream_context
{
    const struct book_archive *archive;
    uint64_t offset;
    uint32_t remaining, written, expected, crc;
    enum book_result error;
    book_archive_sink sink;
    void *context;
};

static uint32_t stream_read(void *data, uint32_t size, void *context)
{
    struct stream_context *stream = context;
    if (size > stream->remaining)
        size = stream->remaining;
    if (stream->error != BOOK_OK)
        return 0;
    stream->error = read_exact(&stream->archive->io, stream->offset, data, size);
    if (stream->error != BOOK_OK)
        return 0;
    stream->remaining -= size;
    stream->offset += size;
    return size;
}

static uint32_t stream_write(const void *data, uint32_t size, void *context)
{
    struct stream_context *stream = context;
    if (stream->error != BOOK_OK)
        return 0;
    if (cancelled(&stream->archive->io))
        stream->error = BOOK_CANCELLED;
    else if (size > stream->expected - stream->written)
        stream->error = BOOK_CORRUPT;
    else if (size)
    {
        enum book_result result = stream->sink(stream->context, data, size);
        if (result != BOOK_OK)
            stream->error = result == BOOK_CANCELLED ? BOOK_CANCELLED : BOOK_IO_ERROR;
        else if (cancelled(&stream->archive->io))
            stream->error = BOOK_CANCELLED;
    }
    if (stream->error != BOOK_OK)
        return 0;
    stream->written += size;
    stream->crc = crc_32r(data, size, stream->crc);
    return size;
}

size_t book_archive_workspace_size(void) { return inflate_size; }
size_t book_archive_workspace_align(void) { return inflate_align; }

static enum book_result check_descriptor(const struct book_archive *archive,
                                         uint64_t offset, const struct book_archive_entry *entry)
{
    unsigned char data[16];
    if (offset > archive->directory_offset || archive->directory_offset - offset < 12)
        return BOOK_CORRUPT;
    enum book_result result = read_exact(&archive->io, offset, data, 12);
    if (result != BOOK_OK)
        return result;
    if (get32(data) == entry->crc && get32(data + 4) == entry->compressed_size &&
        get32(data + 8) == entry->size)
        return BOOK_OK;
    if (get32(data) != UINT32_C(0x08074b50) || archive->directory_offset - offset < 16)
        return BOOK_CORRUPT;
    result = read_exact(&archive->io, offset + 12, data + 12, 4);
    if (result != BOOK_OK)
        return result;
    return get32(data + 4) == entry->crc && get32(data + 8) == entry->compressed_size &&
           get32(data + 12) == entry->size ? BOOK_OK : BOOK_CORRUPT;
}

enum book_result book_archive_stream(const struct book_archive *archive,
                                     const struct book_archive_entry *entry,
                                     void *workspace, size_t workspace_size,
                                     uint64_t output_limit,
                                     book_archive_sink sink, void *context)
{
    if (!archive_valid(archive) || !entry || !sink)
        return BOOK_INVALID;
    struct book_archive_entry current;
    uint32_t next;
    enum book_result result = entry_at(archive, entry->directory_position, &current, &next);
    if (result != BOOK_OK)
        return result;
    /* Revalidate the directory record rather than trusting a caller-owned copy. */
    if (current.local_offset != entry->local_offset || current.compressed_size != entry->compressed_size ||
        current.size != entry->size || current.crc != entry->crc || current.flags != entry->flags ||
        current.method != entry->method || current.version != entry->version ||
        memcmp(current.name, entry->name, sizeof(current.name)))
        return BOOK_STALE;
    if ((current.flags & ~UINT16_C(0x080e)) || current.version > 20 ||
        (current.method != 0 && current.method != 8))
        return BOOK_UNSUPPORTED;
    if (current.size > output_limit)
        return BOOK_LIMIT;
    if (current.method == 8 && (!workspace || workspace_size < inflate_size ||
        (uintptr_t)workspace % inflate_align))
        return BOOK_INVALID;
    unsigned char header[30];
    if ((uint64_t)current.local_offset + sizeof(header) > archive->directory_offset)
        return BOOK_CORRUPT;
    result = read_exact(&archive->io, current.local_offset, header, sizeof(header));
    if (result != BOOK_OK)
        return result;
    size_t name_size = strlen(current.name);
    if (get32(header) != UINT32_C(0x04034b50) || get16(header + 4) != current.version ||
        get16(header + 6) != current.flags || get16(header + 8) != current.method ||
        get16(header + 26) != name_size)
        return BOOK_CORRUPT;
    bool descriptor = (current.flags & 8) != 0;
    if (descriptor ?
        ((get32(header + 14) && get32(header + 14) != current.crc) ||
         (get32(header + 18) && get32(header + 18) != current.compressed_size) ||
         (get32(header + 22) && get32(header + 22) != current.size)) :
        (get32(header + 14) != current.crc || get32(header + 18) != current.compressed_size ||
         get32(header + 22) != current.size))
        return BOOK_CORRUPT;
    uint64_t data_offset = (uint64_t)current.local_offset + sizeof(header) + name_size + get16(header + 28);
    if (data_offset > archive->directory_offset || current.compressed_size > archive->directory_offset - data_offset)
        return BOOK_CORRUPT;
    char local_name[128];
    for (size_t offset = 0; offset < name_size;)
    {
        size_t size = name_size - offset;
        if (size > sizeof(local_name))
            size = sizeof(local_name);
        result = read_exact(&archive->io, (uint64_t)current.local_offset + sizeof(header) + offset,
                            local_name, size);
        if (result != BOOK_OK)
            return result;
        if (memcmp(local_name, current.name + offset, size))
            return BOOK_CORRUPT;
        offset += size;
    }
    if (descriptor)
    {
        result = check_descriptor(archive, data_offset + current.compressed_size, &current);
        if (result != BOOK_OK)
            return result;
    }
    struct stream_context stream = { .archive = archive, .offset = data_offset,
        .remaining = current.compressed_size, .expected = current.size,
        .crc = UINT32_MAX, .error = BOOK_OK, .sink = sink, .context = context };
    if (current.method == 8)
    {
        int inflated = inflate(workspace, INFLATE_RAW, stream_read, &stream, stream_write, &stream);
        if (stream.error != BOOK_OK)
            return stream.error;
        if (inflated != 0)
            return BOOK_CORRUPT;
    }
    else
    {
        if (current.size != current.compressed_size)
            return BOOK_CORRUPT;
        unsigned char block[512];
        while (stream.remaining && stream.error == BOOK_OK)
        {
            uint32_t size = stream_read(block, sizeof(block), &stream);
            if (stream.error == BOOK_OK)
                stream_write(block, size, &stream);
        }
        if (stream.error != BOOK_OK)
            return stream.error;
    }
    if (cancelled(&archive->io))
        return BOOK_CANCELLED;
    return stream.written == current.size && (stream.crc ^ UINT32_MAX) == current.crc ?
           BOOK_OK : BOOK_CORRUPT;
}
