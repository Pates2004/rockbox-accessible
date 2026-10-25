/* Host ABI probes and a real file-backed sanitizer exercise. */
#include "book_archive.h"
#include "inflate.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

size_t book_archive_test_size(unsigned int type)
{
    switch (type)
    {
        case 0: return sizeof(struct book_archive_io);
        case 1: return sizeof(struct book_archive);
        case 2: return sizeof(struct book_archive_cursor);
        default: return sizeof(struct book_archive_entry);
    }
}

int book_archive_test_inflate(void *workspace, int kind, const void *input, size_t input_size,
                             void *output, size_t output_size, size_t *written)
{
    struct inflate_bufferctx in = { .buf = (void *)input, .end = (char *)input + input_size };
    struct inflate_bufferctx out = { .buf = output, .end = (char *)output + output_size };
    int result = inflate(workspace, kind, inflate_buffer_reader, &in, inflate_buffer_writer, &out);
    *written = (char *)out.buf - (char *)output;
    return result;
}

#ifdef BOOK_ARCHIVE_TEST_EXECUTABLE
static int64_t file_read(void *context, uint64_t offset, void *data, size_t size)
{
    FILE *file = context;
    if (fseek(file, (long)offset, SEEK_SET))
        return BOOK_IO_ERROR;
    size_t count = fread(data, 1, size, file);
    return ferror(file) ? BOOK_IO_ERROR : (int64_t)count;
}

static enum book_result file_write(void *context, const void *data, size_t size)
{
    return fwrite(data, 1, size, context) == size ? BOOK_OK : BOOK_IO_ERROR;
}

int main(int argc, char **argv)
{
    assert(argc == 4);
    FILE *input = fopen(argv[1], "rb"), *output = fopen(argv[3], "wb");
    assert(input && output && !fseek(input, 0, SEEK_END));
    long size = ftell(input);
    assert(size >= 0);
    struct book_archive_io io = { .size = (uint64_t)size, .read_at = file_read,
                                   .context = input };
    struct book_archive archive;
    struct book_archive_entry entry;
    assert(book_archive_open(&archive, &io) == BOOK_OK);
    assert(book_archive_find(&archive, argv[2], &entry) == BOOK_OK);
    void *workspace = malloc(book_archive_workspace_size());
    assert(workspace);
    assert(book_archive_stream(&archive, &entry, workspace, book_archive_workspace_size(),
                               2 * 1024 * 1024, file_write, output) == BOOK_OK);
    free(workspace);
    assert(!fclose(output) && !fclose(input));
    return 0;
}
#endif
